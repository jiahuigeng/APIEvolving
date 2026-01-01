import json
import subprocess
import os
import platform
import shutil
import urllib.request
import zipfile
import tarfile
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).parent.resolve()
DATASET_PATH = BASE_DIR / "dataset.jsonl"
ENV_BASE = BASE_DIR / "envs"
TOOLS_DIR = BASE_DIR / "tools"

def wsl_path(path: Path) -> str:
    # If we are already on Linux/WSL, return the path as is
    if platform.system() != "Windows":
        return str(path.resolve())

    # Convert Windows path to WSL path
    # e.g. C:\Users\Foo -> /mnt/c/Users/Foo
    drive = path.drive.lower().replace(':', '')
    # as_posix() returns C:/Users/Foo
    posix_path = path.as_posix()
    # Remove drive letter (C:) from the beginning
    if ':' in posix_path:
        _, rest = posix_path.split(':', 1)
    else:
        rest = posix_path
    
    return f"/mnt/{drive}{rest}"

def run_command(cmd, cwd=None):
    print(f"Running: {cmd} (cwd: {cwd})")
    if isinstance(cmd, str):
        subprocess.run(cmd, cwd=cwd, check=True, shell=True)
    else:
        subprocess.run(cmd, cwd=cwd, check=True)

def download_file(url, dest):
    print(f"Downloading {url} to {dest}...")
    with urllib.request.urlopen(url) as response, open(dest, 'wb') as out_file:
        shutil.copyfileobj(response, out_file)

def unzip_file(zip_path, extract_to):
    print(f"Unzipping {zip_path} to {extract_to}...")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)

def extract_tar_gz(tar_path, extract_to):
    print(f"Extracting {tar_path} to {extract_to}...")
    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(path=extract_to)

def ensure_cmake():
    # Check if cmake is in PATH
    if shutil.which("cmake"):
        print("cmake found in PATH.")
        return

    print("cmake not found. Checking local tools...")
    cmake_dir = TOOLS_DIR / "cmake"
    cmake_bin = cmake_dir / "bin" / "cmake"
    
    if cmake_bin.exists():
        print(f"Using local cmake at {cmake_bin}")
        os.environ["PATH"] = str(cmake_bin.parent) + os.pathsep + os.environ["PATH"]
        return

    print("Local cmake not found. Downloading...")
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Download portable cmake
    version = "3.28.3"
    filename = f"cmake-{version}-linux-x86_64.tar.gz"
    url = f"https://github.com/Kitware/CMake/releases/download/v{version}/{filename}"
    tar_path = TOOLS_DIR / filename
    
    try:
        download_file(url, tar_path)
        extract_tar_gz(tar_path, TOOLS_DIR)
        
        # Rename extracted dir to 'cmake' for simpler access
        extracted_name = f"cmake-{version}-linux-x86_64"
        if (TOOLS_DIR / extracted_name).exists():
            if cmake_dir.exists():
                shutil.rmtree(cmake_dir)
            shutil.move(str(TOOLS_DIR / extracted_name), str(cmake_dir))
            
        # Update PATH
        if cmake_bin.exists():
            print(f"Installed cmake to {cmake_dir}")
            os.environ["PATH"] = str(cmake_bin.parent) + os.pathsep + os.environ["PATH"]
        else:
            print("Failed to verify cmake installation.")
            
    except Exception as e:
        print(f"Failed to setup cmake: {e}")
        # Clean up
        if tar_path.exists():
            os.remove(tar_path)

def setup_fmt(env_dir: Path, version: str):
    # This function should run inside the environment (WSL/Linux)
    
    install_dir = env_dir / "install"
    if install_dir.exists():
        print(f"fmt {version} already installed in {install_dir}")
        return

    print(f"Setting up fmt {version} in {env_dir}...")
    env_dir.mkdir(parents=True, exist_ok=True)
    
    zip_name = f"fmt-{version}.zip"
    zip_path = env_dir / zip_name
    src_dir_name = f"fmt-{version}"
    src_dir = env_dir / src_dir_name
    
    # Download
    url = f"https://github.com/fmtlib/fmt/releases/download/{version}/{zip_name}"
    if not zip_path.exists():
        try:
            download_file(url, zip_path)
        except Exception as e:
            print(f"Failed to download {url}: {e}")
            return

    # Unzip
    if not src_dir.exists():
        unzip_file(zip_path, env_dir)

    # Build
    build_dir = src_dir / "build"
    build_dir.mkdir(exist_ok=True)
    
    # Configure cmake
    install_prefix = install_dir.resolve()
    
    cmd_cmake = [
        "cmake", "..",
        f"-DCMAKE_INSTALL_PREFIX={install_prefix}",
        "-DCMAKE_CXX_STANDARD=17",
        "-DFMT_TEST=OFF",
        "-DCMAKE_POSITION_INDEPENDENT_CODE=ON"
    ]
    
    try:
        run_command(cmd_cmake, cwd=build_dir)
        
        # Build
        nproc = os.cpu_count() or 1
        run_command(["make", f"-j{nproc}"], cwd=build_dir)
        
        # Install
        run_command(["make", "install"], cwd=build_dir)
        
        print(f"Setup complete for fmt {version}")
        
    except subprocess.CalledProcessError as e:
        print(f"Build failed for fmt {version}: {e}")
        if install_dir.exists():
            shutil.rmtree(install_dir)
        raise

def create_env(library, version):
    env_name = f"cpp-{library}-{version}"
    env_dir = ENV_BASE / env_name
    
    if library == "fmt":
        setup_fmt(env_dir, version)
    else:
        print(f"Unknown library {library}, skipping setup.")

def main():
    if platform.system() == "Windows":
        print("Please run this script inside WSL or Linux to set up the environment.")
        print("Usage: python3 CPPTest/create_envs.py")
        return

    # Ensure cmake is available
    ensure_cmake()

    if not DATASET_PATH.exists():
        print(f"Dataset not found at {DATASET_PATH}")
        return

    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        seen = set()
        for line in f:
            if not line.strip(): continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
                
            lib = data.get("library")
            ver = data.get("version")
            if lib and ver and (lib, ver) not in seen:
                seen.add((lib, ver))
                print(f"Creating env for {lib} {ver}...")
                create_env(lib, ver)

if __name__ == "__main__":
    main()
