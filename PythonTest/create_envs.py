import json
import shutil
import subprocess
import sys
import glob
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR
ENV_BASE = BASE_DIR / "envs"


def read_dataset_lines(path: Path):
    lines = []
    if not path.exists():
        return lines
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            lines.append(json.loads(line))
    return lines


def sanitize_dirname(name: str) -> str:
    # Replace invalid characters for Windows paths
    for char in '<>:"/\\|?*':
        name = name.replace(char, '-')
    return name


def env_dir_for(entry: dict) -> Path:
    python_version = entry.get("python_version", "3.9.13")
    library = sanitize_dirname(entry.get("library"))
    version = entry.get("version")
    return ENV_BASE / f"py-{python_version}-{library}-{version}"


def create_venv(env_dir: Path, python_version: str):
    """
    Create a virtual environment using pyenv to select the python version.
    Assumes `pyenv` is installed and configured on Windows (pyenv-win).
    
    If specific python version is not installed, user must install it via `pyenv install <version>`.
    Here we try to use `pyenv exec python -m venv ...` or find the python executable from pyenv.
    
    However, a simpler robust way on Windows with pyenv-win is:
    1. Check if version is installed: `pyenv versions`
    2. Find path to that python: `pyenv which python` (after setting local version or shell)
    
    To simplify, we will try to find the python executable for the requested version.
    """
    
    # Check if env already exists with valid python
    if (env_dir / "Scripts" / "python.exe").exists():
        return

    print(f"Creating venv for {python_version} in {env_dir}...")
    
    # Try to find python executable using pyenv
    # We use `pyenv root` to guess where versions are, or use `pyenv prefix <version>`
    try:
        # Check if version is installed
        res = subprocess.run(["pyenv", "prefix", python_version], capture_output=True, text=True)
        if res.returncode != 0:
            print(f"[Warning] Python {python_version} not found in pyenv. Trying to install or fallback to system python...")
            # Optional: subprocess.run(["pyenv", "install", python_version], check=True)
            # For now, if not found, we might fail or fallback. Let's try to proceed only if found.
            raise RuntimeError(f"Python version {python_version} not managed by pyenv. Please run 'pyenv install {python_version}' first.")
        
        python_exec = Path(res.stdout.strip()) / "python.exe"
        if not python_exec.exists():
             # Sometimes prefix points to the dir, executable is inside
             python_exec = Path(res.stdout.strip()) / "python.exe" # pyenv-win root usually has python.exe
             if not python_exec.exists():
                 # Maybe user is on linux/mac logic? But env says windows.
                 pass

    except FileNotFoundError:
        # pyenv not in path? Fallback to sys.executable if version matches?
        print("[Warning] `pyenv` command not found. Using current python interpreter as fallback.")
        python_exec = sys.executable

    # Create venv
    subprocess.run([str(python_exec), "-m", "venv", str(env_dir)], check=True)


def install_library(env_dir: Path, library: str, version: str):
    pip_cmd = env_dir / "Scripts" / "pip.exe"
    pkg_spec = f"{library}=={version}"
    print(f"Installing {pkg_spec} in {env_dir}...")
    
    # Special handling for pandas 1.3.x which needs older numpy to avoid binary incompatibility on Python 3.10+
    # "ValueError: numpy.dtype size changed" usually means numpy is too new for the pandas wheel.
    # For pandas 1.3.5, numpy<2 is generally required, but specifically for this error, try pinning numpy.
    if library == "pandas" and version.startswith("1.3"):
        subprocess.run([str(pip_cmd), "install", "numpy<2"], check=True)
        
    subprocess.run([str(pip_cmd), "install", pkg_spec], check=True)
    # Also install pytest for testing
    subprocess.run([str(pip_cmd), "install", "pytest"], check=True)


def write_main_stub(env_dir: Path, entry: dict):
    starting_code = entry.get("starting_code", "")
    src_dir = env_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "main.py").write_text(starting_code, encoding="utf-8")


def ensure_env(entry: dict):
    env_dir = env_dir_for(entry)
    env_dir.mkdir(parents=True, exist_ok=True)
    
    python_version = entry.get("python_version", "3.9.13")
    library = entry.get("library")
    version = entry.get("version")

    create_venv(env_dir, python_version)
    install_library(env_dir, library, version)
    write_main_stub(env_dir, entry)
    return env_dir


def main():
    ENV_BASE.mkdir(parents=True, exist_ok=True)
    
    dataset_files = list(DATA_DIR.glob("*_dataset.jsonl"))
    if (BASE_DIR / "dataset.jsonl").exists():
        dataset_files.append(BASE_DIR / "dataset.jsonl")
        
    if not dataset_files:
        print(f"No dataset files found in {DATA_DIR}")
        return

    all_entries = []
    for ds_path in dataset_files:
        print(f"Loading entries from {ds_path}...")
        all_entries.extend(read_dataset_lines(ds_path))

    for entry in all_entries:
        try:
            ensure_env(entry)
        except Exception as e:
            print(f"Failed to create env for {entry.get('example_id')}: {e}")


if __name__ == "__main__":
    main()
