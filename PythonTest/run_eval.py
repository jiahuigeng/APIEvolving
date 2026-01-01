import json
import shutil
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR
ENV_BASE = BASE_DIR / "envs"


def read_jsonl(path: Path):
    items = []
    if not path.exists():
        return items
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    return items


def sanitize_dirname(name: str) -> str:
    for char in '<>:"/\\|?*':
        name = name.replace(char, '-')
    return name


def env_dir_for(entry: dict) -> Path:
    python_version = entry.get("python_version", "3.9.13")
    library = sanitize_dirname(entry.get("library"))
    version = entry.get("version")
    return ENV_BASE / f"py-{python_version}-{library}-{version}"


def which(cmd: str):
    return shutil.which(cmd)


def run(cmd, cwd: Path = None, check=True, capture=False):
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        check=check,
        capture_output=capture,
        text=True,
    )


def ensure_env_created(entry: dict):
    env_dir = env_dir_for(entry)
    # Simple check: if python executable exists
    if not (env_dir / "Scripts" / "python.exe").exists():
        print(f"Environment missing for {entry.get('example_id')}, creating...")
        subprocess.run(["python", str(BASE_DIR / "create_envs.py")], check=True)
    return env_dir


def write_answer_main(env_dir: Path, starting_code: str, solution: str):
    # Intelligent replacement preserving indentation
    lines = starting_code.splitlines()
    new_lines = []
    for line in lines:
        if "# SOLUTION_START" in line:
            # Calculate indentation of the marker line
            indent = line[:line.find("# SOLUTION_START")]
            # Only keep whitespace
            if not indent.strip():
                # Apply indentation to each line of the solution
                # Note: The solution in dataset might or might not have indentation. 
                # Usually solution is a block of code starting at indentation 0 relative to itself.
                # We strip common leading whitespace from solution just in case, then apply target indent.
                import textwrap
                dedented_sol = textwrap.dedent(solution)
                for sol_line in dedented_sol.splitlines():
                    new_lines.append(indent + sol_line)
            else:
                # If there's code before the marker on the same line (rare), just replace
                new_lines.append(line.replace("# SOLUTION_START", solution))
        elif "# SOLUTION_END" in line:
            continue
        else:
            new_lines.append(line)
            
    content = "\n".join(new_lines)
    src_dir = env_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "main.py").write_text(content, encoding="utf-8")


def write_pytest_test(env_dir: Path, test_body: str):
    src_dir = env_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    # Create a test file
    (src_dir / "test_main.py").write_text(test_body, encoding="utf-8")


def evaluate_entry(entry: dict, ground_truth_map: dict):
    env_dir = ensure_env_created(entry)
    python_exec = env_dir / "Scripts" / "python.exe"
    pytest_exec = env_dir / "Scripts" / "pytest.exe"

    starting_code = entry.get("starting_code", "")
    example_id = entry.get("example_id")
    solution = ground_truth_map.get(example_id, entry.get("solution", ""))
    test_body = entry.get("test", "")
    expected = entry.get("expected_output_contains", [])

    # Write answer and test
    write_answer_main(env_dir, starting_code, solution)
    write_pytest_test(env_dir, test_body)

    # Run main code
    src_dir = env_dir / "src"
    ans_res = run([str(python_exec), "main.py"], cwd=src_dir, check=False, capture=True)
    stdout = ans_res.stdout or ""
    stderr = ans_res.stderr or ""
    
    answer_ok = ans_res.returncode == 0 and all(s in stdout for s in expected)
    
    # Run tests using pytest
    test_res = run([str(pytest_exec), "test_main.py"], cwd=src_dir, check=False, capture=True)
    test_ok = test_res.returncode == 0

    return {
        "example_id": example_id,
        "answer_status": "pass" if answer_ok else "fail",
        "test_status": "pass" if test_ok else "fail",
        "answer_output": stdout.strip(),
        "answer_error": stderr.strip() if ans_res.returncode != 0 else "",
        "test_output": test_res.stdout.strip() if not test_ok else ""
    }


def main():
    dataset_files = list(DATA_DIR.glob("*_dataset.jsonl"))
    gt_files = list(DATA_DIR.glob("*_gt_solution.jsonl"))

    if (BASE_DIR / "dataset.jsonl").exists():
        dataset_files.append(BASE_DIR / "dataset.jsonl")
    if (BASE_DIR / "ground_truth_solution.jsonl").exists():
        gt_files.append(BASE_DIR / "ground_truth_solution.jsonl")

    entries = []
    for ds in dataset_files:
        print(f"Loading dataset: {ds}")
        entries.extend(read_jsonl(ds))
        
    gt_map = {}
    for gt in gt_files:
        print(f"Loading ground truth: {gt}")
        items = read_jsonl(gt)
        for item in items:
            gt_map[item["example_id"]] = item.get("solution", "")

    results = []
    for entry in entries:
        print(f"Evaluating {entry.get('example_id')}...")
        try:
            res = evaluate_entry(entry, gt_map)
            results.append(res)
            print(f"  Result: answer={res['answer_status']}, test={res['test_status']}")
            if res['answer_status'] == 'fail':
                print(f"  [Output]: {res['answer_output']}")
                if res['answer_error']:
                     print(f"  [Error]: {res['answer_error']}")
        except Exception as e:
            print(f"Error evaluating {entry.get('example_id')}: {e}")

if __name__ == "__main__":
    main()
