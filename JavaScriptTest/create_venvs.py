import json
import os
import shutil
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
DATASET_PATH = BASE_DIR / "dataset.jsonl"
ENV_BASE = BASE_DIR / "envs"


def read_dataset_lines(path: Path):
    lines = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            lines.append(json.loads(line))
    return lines


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
    # New naming: node-{vnode}-{library}-{vlibrary}
    return ENV_BASE / f"node-{node_version}-{library}-{version}"


def run(cmd, cwd: Path):
    subprocess.run(cmd, check=True, cwd=str(cwd))


def resolve_npm_path():
    # Try to find npm using PATH
    npm_path = shutil.which("npm") or shutil.which("npm.cmd") or shutil.which("npm.exe")
    if npm_path:
        return npm_path

    # Common Windows locations
    candidates = []
    program_files = os.environ.get("ProgramFiles")
    if program_files:
        candidates.append(Path(program_files) / "nodejs" / "npm.cmd")
        candidates.append(Path(program_files) / "nodejs" / "npm.exe")
    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        candidates.append(Path(userprofile) / "AppData" / "Roaming" / "npm" / "npm.cmd")

    for c in candidates:
        if c.exists():
            return str(c)

    raise FileNotFoundError(
        "未找到 npm 可执行文件。请安装 Node.js 并确保 npm 在 PATH 中，"
        "或将 npm 所在目录添加到 PATH。常见位置例如 'C\\\Program Files\\\nodejs\\\npm.cmd'。"
    )


def ensure_env(entry: dict):
    env_dir = env_dir_for(entry)
    version = entry["version"]
    library = entry["library"]
    npm_bin = resolve_npm_path()
    env_dir.mkdir(parents=True, exist_ok=True)

    pkg_json = env_dir / "package.json"
    if not pkg_json.exists():
        run([npm_bin, "init", "-y"], cwd=env_dir)

    run([npm_bin, "install", f"react@{version}", f"react-dom@{version}"], cwd=env_dir)

    # Normalize package.json scripts for convenience
    try:
        pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
        scripts = pkg.get("scripts", {})
        scripts["start"] = "node index.js"
        scripts["test"] = "node index.js"
        pkg["scripts"] = scripts
        pkg.setdefault("type", "commonjs")
        pkg_json.write_text(json.dumps(pkg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        # If package.json editing fails, continue without blocking
        pass

    return env_dir


def main():
    ENV_BASE.mkdir(parents=True, exist_ok=True)
    entries = read_dataset_lines(DATASET_PATH)
    for entry in entries:
        ensure_env(entry)


if __name__ == "__main__":
    main()