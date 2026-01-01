import json
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


def sanitize_path_component(s: str) -> str:
    if s is None:
        return "unknown"
    invalid = '<>:"/\\|?*'
    return "".join((c if c not in invalid else "-") for c in s).replace(" ", "_")


def env_dir_for(entry: dict) -> Path:
    java_version = entry.get("java_version", "system")
    library = sanitize_path_component(entry.get("library"))
    version = sanitize_path_component(entry.get("version"))
    return ENV_BASE / f"java-{java_version}-{library}-{version}"


def which(cmd: str):
    return shutil.which(cmd)


def run(cmd, cwd: Path = None, check=True):
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=check)


def parse_maven_coord(coord: str):
    # "groupId:artifactId"
    parts = coord.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid Maven coordinate: {coord}")
    return parts[0], parts[1]


def write_pom(env_dir: Path, entry: dict):
    java_version = entry.get("java_version", "11")
    library_coord = entry.get("library")
    lib_version = entry.get("version")
    group_id, artifact_id = parse_maven_coord(library_coord)

    pom = f"""
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>java-test-{artifact_id}</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>{java_version}</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <junit.jupiter.version>5.10.1</junit.jupiter.version>
    <exec.mainClass>Main</exec.mainClass>
  </properties>
  <dependencies>
    <dependency>
      <groupId>{group_id}</groupId>
      <artifactId>{artifact_id}</artifactId>
      <version>{lib_version}</version>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter-api</artifactId>
      <version>${{junit.jupiter.version}}</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter-engine</artifactId>
      <version>${{junit.jupiter.version}}</version>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.11.0</version>
        <configuration>
          <release>${{maven.compiler.release}}</release>
        </configuration>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.2.5</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.1.0</version>
        <configuration>
          <mainClass>${{exec.mainClass}}</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
""".strip()
    (env_dir / "pom.xml").write_text(pom, encoding="utf-8")


def write_main_stub(env_dir: Path, entry: dict):
    starting_code = entry.get("starting_code", "")
    src_dir = env_dir / "src" / "main" / "java"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "Main.java").write_text(starting_code, encoding="utf-8")


def ensure_env(entry: dict):
    env_dir = env_dir_for(entry)
    env_dir.mkdir(parents=True, exist_ok=True)
    write_pom(env_dir, entry)
    write_main_stub(env_dir, entry)
    return env_dir


def main():
    ENV_BASE.mkdir(parents=True, exist_ok=True)
    entries = read_dataset_lines(DATASET_PATH)
    for entry in entries:
        ensure_env(entry)


if __name__ == "__main__":
    mvn = which("mvn") or which("mvn.cmd")
    if not mvn:
        print("[提示] 未检测到 Maven (mvn)。请先安装 Maven 并确保其在 PATH 中。")
    main()
