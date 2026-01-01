import json
import subprocess
import os
import platform
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).parent.resolve()
DATASET_PATH = BASE_DIR / "dataset.jsonl"
ENV_BASE = BASE_DIR / "envs"

def run_command(cmd, cwd=None, capture=False):
    if capture:
        return subprocess.run(cmd, cwd=cwd, check=False, capture_output=True, text=True)
    else:
        subprocess.run(cmd, cwd=cwd, check=True)

def evaluate_entry(entry):
    example_id = entry.get("example_id")
    language = entry.get("language")
    library = entry.get("library")
    version = entry.get("version")
    
    if language != "C++":
        print(f"Skipping non-C++ entry {example_id}")
        return "SKIP"

    env_name = f"cpp-{library}-{version}"
    env_dir = ENV_BASE / env_name
    install_dir = env_dir / "install"
    
    if not install_dir.exists():
        print(f"Environment for {library} {version} not found (expected at {install_dir})")
        return "ERROR"

    print(f"Evaluating {example_id} on {library} {version}...")
    
    # Prepare source code
    starting_code = entry.get("starting_code", "")
    solution = entry.get("solution", "")
    
    # Simple substitution of solution
    # Note: real world usage might need more sophisticated replacement
    code = starting_code.replace("// SOLUTION_START", "").replace("// SOLUTION_END", "")
    # Insert solution before return 0; or inside main
    # The starting code provided in dataset.jsonl:
    # int main() {
    #   // SOLUTION_START
    #   // SOLUTION_END
    #   return 0;
    # }
    # We should inject solution between START and END tags if they exist
    
    if "// SOLUTION_START" in starting_code and "// SOLUTION_END" in starting_code:
        # Re-do replacement properly
        parts = starting_code.split("// SOLUTION_START")
        prefix = parts[0]
        suffix = parts[1].split("// SOLUTION_END")[1]
        full_code = prefix + "\n" + solution + "\n" + suffix
    else:
        # Fallback: just append solution? No, that's unsafe. 
        # Assume tags are present as per dataset convention.
        full_code = starting_code.replace("// SOLUTION_START", solution).replace("// SOLUTION_END", "")

    # Write source file
    src_file = env_dir / "test.cpp"
    with open(src_file, "w", encoding="utf-8") as f:
        f.write(full_code)

    # Compile
    # g++ -std=c++17 test.cpp -o test -I install/include -L install/lib -lfmt
    exe_file = env_dir / "test_runner"
    
    include_dir = install_dir / "include"
    lib_dir = install_dir / "lib"
    # Sometimes lib is in lib64
    if not lib_dir.exists() and (install_dir / "lib64").exists():
        lib_dir = install_dir / "lib64"
        
    cmd_compile = [
        "g++", "-std=c++17", str(src_file), "-o", str(exe_file),
        f"-I{include_dir}", f"-L{lib_dir}", f"-l{library}",
        "-Wl,-rpath," + str(lib_dir) # Set RPATH so we don't need LD_LIBRARY_PATH
    ]
    
    try:
        res = run_command(cmd_compile, cwd=env_dir, capture=True)
        if res and res.returncode != 0:
            print(f"Compilation failed for {example_id}:")
            print(res.stderr)
            return "FAIL_COMPILE"
    except subprocess.CalledProcessError as e:
        print(f"Compilation error: {e}")
        return "FAIL_COMPILE"

    # Run
    try:
        res = run_command([str(exe_file)], cwd=env_dir, capture=True)
        output = res.stdout.strip() if res.stdout else ""
        print(f"Output for {example_id}: {output}")
        
        expected_list = entry.get("expected_output_contains", [])
        passed = True
        for exp in expected_list:
            if exp not in output:
                passed = False
                print(f"FAIL: Expected '{exp}' not found in output.")
        
        if passed:
            print(f"PASS: {example_id}")
            return "PASS"
        else:
            return "FAIL_OUTPUT"
            
    except subprocess.CalledProcessError as e:
        print(f"Runtime error for {example_id}: {e}")
        return "FAIL_RUNTIME"

def main():
    if platform.system() == "Windows":
        print("Please run this script inside WSL or Linux.")
        return

    if not DATASET_PATH.exists():
        print(f"Dataset not found at {DATASET_PATH}")
        return

    results = {
        "PASS": 0,
        "FAIL_COMPILE": 0,
        "FAIL_RUNTIME": 0,
        "FAIL_OUTPUT": 0,
        "SKIP": 0,
        "ERROR": 0
    }
    
    total = 0
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            try:
                entry = json.loads(line)
                status = evaluate_entry(entry)
                results[status] = results.get(status, 0) + 1
                total += 1
            except json.JSONDecodeError:
                continue

    print("\n" + "="*30)
    print("Evaluation Summary")
    print("="*30)
    print(f"Total: {total}")
    print(f"Passed: {results['PASS']}")
    print(f"Failed (Compile): {results['FAIL_COMPILE']}")
    print(f"Failed (Runtime): {results['FAIL_RUNTIME']}")
    print(f"Failed (Output): {results['FAIL_OUTPUT']}")
    if results['SKIP'] > 0:
        print(f"Skipped: {results['SKIP']}")
    if results['ERROR'] > 0:
        print(f"Errors (Env missing): {results['ERROR']}")
    print("="*30)

if __name__ == "__main__":
    main()
