import argparse
import json
import os
import sys


def normalize_lib(lib):
    group = lib.get("group", "").strip()
    name = lib.get("name", "").strip()
    version = lib.get("version", "").strip()
    scope = lib.get("scope", "Compile").strip()
    return {"group": group, "name": name, "version": version, "scope": scope}


def resolve_coords(name):
    mapping = {
        "cats-core": ("org.typelevel", "cats-core"),
        "scalatest": ("org.scalatest", "scalatest"),
        "akka-actor": ("com.typesafe.akka", "akka-actor"),
    }
    return mapping.get(name, (None, name))


def build_env_name(scala_version, libraries):
    parts = [f"scala-{scala_version}"]
    for lib in libraries:
        if lib.get("scope", "Compile") == "Test":
            continue
        parts.append(f'{lib["name"]}-{lib["version"]}')
    return "-".join(parts)


def sbt_dependency_line(lib, cross_module=True):
    group = lib["group"]
    name = lib["name"]
    version = lib["version"]
    scope = lib["scope"]
    cross = "%%" if cross_module else "%"
    scope_suffix = f' % "{scope}"' if scope and scope != "Compile" else ""
    return f'"{group}" {cross} "{name}" % "{version}"{scope_suffix}'


def write_build_sbt(path, scala_version, libraries):
    deps_lines = []
    for lib in libraries:
        deps_lines.append(sbt_dependency_line(lib, cross_module=True))
    deps_str = ",\n      ".join(deps_lines) if deps_lines else ""
    content = (
        f'ThisBuild / scalaVersion := "{scala_version}"\n\n'
        'lazy val root = (project in file("."))\n'
        '  .settings(\n'
        '    name := "EvalEnv",\n'
        f'    libraryDependencies ++= Seq(\n      {deps_str}\n    )\n'
        '  )\n'
    )
    with open(os.path.join(path, "build.sbt"), "w", encoding="utf-8") as f:
        f.write(content)


def write_build_properties(path, sbt_version="1.10.2"):
    proj_dir = os.path.join(path, "project")
    os.makedirs(proj_dir, exist_ok=True)
    with open(os.path.join(proj_dir, "build.properties"), "w", encoding="utf-8") as f:
        f.write(f"sbt.version={sbt_version}\n")


def ensure_src_dirs(path):
    for p in [
        os.path.join(path, "src", "main", "scala"),
        os.path.join(path, "src", "test", "scala"),
    ]:
        os.makedirs(p, exist_ok=True)


def create_envs(dataset_path, base_path):
    os.makedirs(base_path, exist_ok=True)
    env_map = {}
    with open(dataset_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
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
            env_dir = os.path.join(base_path, env_name)
            if env_name in env_map:
                continue
            os.makedirs(env_dir, exist_ok=True)
            write_build_properties(env_dir)
            write_build_sbt(env_dir, scala_version, libraries)
            ensure_src_dirs(env_dir)
            env_map[env_name] = {"path": env_dir, "scala_version": scala_version, "libraries": libraries}
    return env_map


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--base_path", default="ScalaTest/envs")
    args = parser.parse_args()
    env_map = create_envs(args.dataset, args.base_path)
    print(json.dumps(env_map, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(str(e))
        sys.exit(1)
