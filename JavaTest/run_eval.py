import json
import shutil
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
DATASET_PATH = BASE_DIR / "dataset.jsonl"
GROUND_TRUTH_PATH = BASE_DIR / "ground_truth_solution.jsonl"
ENV_BASE = BASE_DIR / "envs"


def read_jsonl(path: Path):
    items = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    return items


def sanitize_dirname(name: str) -> str:
    # 替换 Windows 路径非法字符: < > : " / \ | ? *
    for char in '<>:"/\\|?*':
        name = name.replace(char, '-')
    return name


def env_dir_for(entry: dict) -> Path:
    java_version = entry.get("java_version", "system")
    library = sanitize_dirname(entry.get("library"))
    version = entry.get("version")
    return ENV_BASE / f"java-{java_version}-{library}-{version}"


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
    # Call create_envs.py to scaffold env if not present
    env_dir = env_dir_for(entry)
    if not env_dir.exists():
        subprocess.run([which("python") or "python", str(BASE_DIR / "create_envs.py")], check=True)
    return env_dir


def write_answer_main(env_dir: Path, starting_code: str, solution: str):
    # Replace SOLUTION_START .. SOLUTION_END with solution content
    content = starting_code.replace("// SOLUTION_START", solution).replace("// SOLUTION_END", "")
    src_dir = env_dir / "src" / "main" / "java"
    (src_dir / "Main.java").write_text(content, encoding="utf-8")


def write_junit_test(env_dir: Path, test_body: str):
    test_src = env_dir / "src" / "test" / "java"
    test_src.mkdir(parents=True, exist_ok=True)
    test_cls = f"""
import org.junit.jupiter.api.Test;

public class MainTest {{
  @Test
  void testBehavior() {{
    {test_body}
  }}
}}
""".strip()
    (test_src / "MainTest.java").write_text(test_cls, encoding="utf-8")


def evaluate_entry(entry: dict, ground_truth_map: dict):
    mvn = which("mvn") or which("mvn.cmd")
    if not mvn:
        return {
            "example_id": entry.get("example_id"),
            "answer_status": "error",
            "test_status": "error",
            "error": "Maven (mvn) 未安装或不在 PATH 中",
        }

    env_dir = ensure_env_created(entry)
    starting_code = entry.get("starting_code", "")
    example_id = entry.get("example_id")
    solution = ground_truth_map.get(example_id, entry.get("solution", ""))
    test_body = entry.get("test", "")
    expected = entry.get("expected_output_contains", [])

    # Write answer and test
    write_answer_main(env_dir, starting_code, solution)
    write_junit_test(env_dir, test_body)

    # Run main via exec-maven-plugin
    ans_res = run([mvn, "-q", "-DskipTests", "exec:java"], cwd=env_dir, check=False, capture=True)
    stdout = ans_res.stdout or ""
    answer_ok = ans_res.returncode == 0 and all(s in stdout for s in expected)

    # Run tests
    test_res = run([mvn, "-q", "test"], cwd=env_dir, check=False, capture=True)
    test_ok = test_res.returncode == 0

    return {
        "example_id": example_id,
        "answer_status": "pass" if answer_ok else "fail",
        "test_status": "pass" if test_ok else "fail",
        "answer_output": stdout.strip(),
    }


def main():
    entries = read_jsonl(DATASET_PATH)
    gts = read_jsonl(GROUND_TRUTH_PATH)
    gt_map = {item["example_id"]: item.get("solution", "") for item in gts}

    results = []
    for entry in entries:
        results.append(evaluate_entry(entry, gt_map))

    # Print summary
    for r in results:
        print(f"{r['example_id']}: answer={r['answer_status']}, test={r['test_status']}")


if __name__ == "__main__":
    main()