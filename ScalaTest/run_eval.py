import argparse
import json
import os
import subprocess
import sys
import time
import platform
import shutil

from create_envs import create_envs, normalize_lib, build_env_name, resolve_coords


def write_source(env_dir, case_id, code_str):
    src_dir = os.path.join(env_dir, "src", "main", "scala")
    os.makedirs(src_dir, exist_ok=True)
    file_path = os.path.join(src_dir, f"{case_id}.scala")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(code_str)
    return file_path


def write_test(env_dir, case_id, code_str):
    test_dir = os.path.join(env_dir, "src", "test", "scala")
    os.makedirs(test_dir, exist_ok=True)
    file_path = os.path.join(test_dir, f"{case_id}Spec.scala")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(code_str)
    return file_path


def run_sbt_test(env_dir, sbt_cmds):
    last_err = None
    proc = None
    for cmd in sbt_cmds:
        try:
            proc = subprocess.Popen(
                [cmd, "-batch", "test"],
                cwd=env_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
            )
            break
        except FileNotFoundError as e:
            last_err = e
            continue
    if proc is None:
        raise RuntimeError(f"sbt 可执行文件未找到，已尝试：{', '.join(sbt_cmds)}。请安装 sbt 或提供 --sbt_cmd 的绝对路径。")
    output_lines = []
    while True:
        line = proc.stdout.readline()
        if not line and proc.poll() is not None:
            break
        if line:
            output_lines.append(line.rstrip("\n"))
    return_code = proc.wait()
    output = "\n".join(output_lines)
    success = return_code == 0
    return success, output


def load_ground_truth(path):
    mapping = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            mapping[item["id"]] = item["solution_code"]
    return mapping


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--solutions", required=True)
    parser.add_argument("--env_base", default="ScalaTest/envs")
    parser.add_argument("--sbt_cmd", default="sbt")
    parser.add_argument("--results", default="ScalaTest/eval_results.jsonl")
    args = parser.parse_args()

    env_map = create_envs(args.dataset, args.env_base)
    solutions = load_ground_truth(args.solutions)
    os.makedirs(os.path.dirname(args.results), exist_ok=True)

    candidates = []
    if args.sbt_cmd:
        candidates.append(args.sbt_cmd)
    if platform.system().lower().startswith("win"):
        candidates.extend(["sbt.bat", "sbt.cmd", "sbt"])
        common_paths = [
            r"C:\Program Files\sbt\bin\sbt.bat",
            r"C:\Program Files (x86)\sbt\bin\sbt.bat",
        ]
        for p in common_paths:
            if os.path.exists(p):
                candidates.insert(0, p)
    else:
        candidates.extend(["sbt"])
    candidates = [c for c in candidates if shutil.which(c) or os.path.isabs(c)]

    with open(args.dataset, "r", encoding="utf-8") as df, open(args.results, "w", encoding="utf-8") as out:
        for line in df:
            if not line.strip():
                continue
            item = json.loads(line)
            case_id = item.get("id") or item.get("example_id")
            scala_version = item["scala_version"]
            libraries = []
            if "libraries" in item and item["libraries"]:
                libraries = [normalize_lib(l) for l in item["libraries"]]
            else:
                lib_name = item.get("library")
                lib_version = item.get("version")
                group = item.get("group")
                if not group:
                    g, n = resolve_coords(lib_name)
                    group = g or ""
                    lib_name = n
                libraries = [normalize_lib({"group": group, "name": lib_name, "version": lib_version, "scope": "Compile"})]
                if not any(l["name"] == "scalatest" for l in libraries):
                    libraries.append(normalize_lib({"group": "org.scalatest", "name": "scalatest", "version": "3.2.18", "scope": "Test"}))
            env_name = build_env_name(scala_version, libraries)
            env_info = env_map[env_name]
            env_dir = env_info["path"]

            solution_code = solutions.get(case_id, item.get("solution", item.get("main_code", item.get("starting_code", ""))))
            test_code = item.get("test") or item.get("test_code", "")

            src_path = write_source(env_dir, case_id, solution_code)
            test_path = write_test(env_dir, case_id, test_code)

            start = time.time()
            success, output = run_sbt_test(env_dir, candidates or [args.sbt_cmd])
            duration = time.time() - start

            result = {
                "id": case_id,
                "env_dir": env_dir,
                "src_path": src_path,
                "test_path": test_path,
                "success": success,
                "duration_sec": duration,
            }
            out.write(json.dumps(result, ensure_ascii=False) + "\n")
            out.flush()

    print(args.results)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(str(e))
        sys.exit(1)
