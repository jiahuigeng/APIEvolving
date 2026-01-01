import json
import shutil
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
DATASET_PATH = BASE_DIR / "dataset.jsonl"
ENV_BASE = BASE_DIR / "envs"
GROUND_TRUTH_PATH = BASE_DIR / "ground_truth_solutions.jsonl"


def read_dataset_lines(path: Path):
    lines = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            lines.append(json.loads(line))
    return lines


def read_ground_truth(path: Path):
    mapping = {}
    if not path.exists():
        return mapping
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            mapping[obj.get("example_id")] = obj.get("answer")
    return mapping


def _get_system_node_version() -> str:
    try:
        result = subprocess.run(["node", "-v"], capture_output=True, text=True, check=True)
        v = result.stdout.strip()
        return v[1:] if v.startswith("v") else v
    except Exception:
        return "unknown"


def env_dir_for(entry: dict) -> Path:
    version = entry.get("version")
    library = entry.get("library")
    node_version = entry.get("node_version")
    if not node_version or node_version == "system":
        node_version = _get_system_node_version()
    return ENV_BASE / f"node-{node_version}-{library}-{version}"


def write_js(env_dir: Path, filename: str, code: str):
    target = env_dir / filename
    target.write_text(code, encoding="utf-8")
    return target


def run_node(env_dir: Path, entrypoint: str):
    node_bin = shutil.which("node") or "node"
    proc = subprocess.run([node_bin, entrypoint], cwd=str(env_dir), capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def main():
    entries = read_dataset_lines(DATASET_PATH)
    ground_truth = read_ground_truth(GROUND_TRUTH_PATH)
    results = []
    for entry in entries:
        env_dir = env_dir_for(entry)
        if not env_dir.exists():
            results.append({
                "example_id": entry.get("example_id"),
                "status": "env_missing",
                "message": f"Environment missing at {env_dir}. Run create_venvs.py first."
            })
            continue

        # Run ground truth answer (fallback to starting_code + solution if missing)
        example_id = entry.get("example_id")
        answer_code = ground_truth.get(example_id)
        if not answer_code:
            answer_code = entry.get("starting_code", "") + "\n" + entry.get("solution", "")

        write_js(env_dir, "index.js", answer_code)
        a_code, a_out, a_err = run_node(env_dir, "index.js")
        expected = entry.get("expected_output_contains", [])
        answer_ok = a_code == 0 and all(s in a_out for s in expected)

        # Run test code if available
        test_code = entry.get("test")
        if test_code:
            write_js(env_dir, "test.js", test_code)
            t_code, t_out, t_err = run_node(env_dir, "test.js")
            test_ok = t_code == 0
        else:
            t_code, t_out, t_err = None, "", ""
            test_ok = False

        results.append({
            "example_id": example_id,
            "answer_status": "passed" if answer_ok else "failed",
            "answer_returncode": a_code,
            "answer_stdout": a_out.strip(),
            "answer_stderr": a_err.strip(),
            "test_status": "passed" if test_ok else "failed",
            "test_returncode": t_code,
            "test_stdout": t_out.strip(),
            "test_stderr": t_err.strip(),
        })

    print(json.dumps({"results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()