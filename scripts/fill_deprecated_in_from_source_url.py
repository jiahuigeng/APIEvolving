import argparse
import glob
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from utils_llm import prompt_llm
except ImportError:
    prompt_llm = None


try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


DOT_VERSION_RE = re.compile(r"(?<!\d)(\d+\.\d+(?:\.\d+)?)(?!\d)")
UNDERSCORE_VERSION_RE = re.compile(r"(?<!\d)(\d+)_([0-9]+)(?:_([0-9]+))?(?!\d)")


def normalize_semver(version: str) -> Optional[str]:
    version = version.strip()
    if not version:
        return None
    if not DOT_VERSION_RE.fullmatch(version):
        return None
    parts = version.split(".")
    if len(parts) == 2:
        return f"{parts[0]}.{parts[1]}.0"
    return version


def extract_versions_from_url(url: str) -> List[str]:
    if not url:
        return []
    normalized: List[str] = []

    for v in DOT_VERSION_RE.findall(url):
        nv = normalize_semver(v)
        if nv:
            normalized.append(nv)

    for m in UNDERSCORE_VERSION_RE.finditer(url):
        major = m.group(1)
        minor = m.group(2)
        patch = m.group(3) or "0"
        nv = normalize_semver(f"{major}.{minor}.{patch}")
        if nv:
            normalized.append(nv)

    dedup = list(dict.fromkeys(normalized))
    return dedup


def choose_candidate_from_url(url_versions: List[str]) -> Optional[str]:
    if not url_versions:
        return None
    def key(v: str) -> Tuple[int, int, int]:
        a, b, c = v.split(".")
        return int(a), int(b), int(c)
    return sorted(url_versions, key=key)[-1]


def ask_llm_for_deprecated_in(
    model: str,
    item: Dict[str, Any],
    url_versions: List[str],
) -> Optional[str]:
    def call_openai_chat(m: str, p: str, sp: Optional[str]) -> Optional[str]:
        if OpenAI is None:
            return None
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return None
        client = OpenAI(api_key=api_key)
        messages = []
        if sp:
            messages.append({"role": "system", "content": sp})
        messages.append({"role": "user", "content": p})
        resp = client.chat.completions.create(model=m, messages=messages)
        return resp.choices[0].message.content

    source_url = item.get("source_url") or ""
    api = item.get("api") or ""
    package = item.get("package") or ""
    reason = item.get("reason") or ""
    change_type = item.get("change_type") or ""

    prompt = (
        "你是一个严谨的软件版本信息抽取助手。\n"
        "我有一条 APIEvoBench 的记录，其中 deprecated_in 字段为空。\n"
        "请根据 source_url 中出现的版本号，推断并返回一个最合理的 deprecated_in 版本号。\n"
        "要求：\n"
        "1) 只输出一个版本号字符串，格式必须是 x.y.z，例如 5.0.0。\n"
        "2) 只能从我提供的 url_versions 中选择其一；如果无法判断就输出空字符串。\n"
        "\n"
        f"package: {package}\n"
        f"api: {api}\n"
        f"change_type: {change_type}\n"
        f"reason: {reason}\n"
        f"source_url: {source_url}\n"
        f"url_versions: {url_versions}\n"
    )
    system_prompt = "只输出最终答案，不要输出解释。"

    if prompt_llm is not None:
        resp = prompt_llm(model, prompt, system_prompt=system_prompt)
    else:
        resp = call_openai_chat(model, prompt, system_prompt)
    if resp is None:
        return None
    answer = resp.strip().splitlines()[0].strip()
    if answer == "":
        return None
    return normalize_semver(answer)


def process_file(
    file_path: str,
    model: str,
    dry_run: bool,
    write: bool,
    inplace: bool,
    output_suffix: str,
    no_llm: bool,
    max_items: Optional[int],
) -> Tuple[int, int]:
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    updated = 0
    considered = 0

    for item in data:
        if max_items is not None and considered >= max_items:
            break

        if item.get("deprecated_in", None) != "":
            continue

        source_url = item.get("source_url") or ""
        url_versions = extract_versions_from_url(source_url)
        if not url_versions:
            continue

        considered += 1

        chosen: Optional[str] = None
        if no_llm:
            chosen = choose_candidate_from_url(url_versions)
        else:
            chosen = ask_llm_for_deprecated_in(model=model, item=item, url_versions=url_versions)
            if chosen is None:
                chosen = choose_candidate_from_url(url_versions)

        if chosen and chosen != item.get("deprecated_in"):
            if not dry_run:
                item["deprecated_in"] = chosen
            updated += 1

    if write and updated > 0 and not dry_run:
        if inplace:
            out_path = file_path
        else:
            base, ext = os.path.splitext(file_path)
            out_path = f"{base}{output_suffix}{ext}"

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")

    return considered, updated


def main() -> int:
    parser = argparse.ArgumentParser(description="Fill empty deprecated_in using source_url versions + LLM.")
    parser.add_argument("--python_dir", type=str, default="APIEvoBench/Python", help="Directory containing *_examples.json.")
    parser.add_argument("--data_dir", type=str, default=None, help="Directory containing *_examples.json (e.g., APIEvoBench/Ruby).")
    parser.add_argument("--language", type=str, default=None, help="Language folder under APIEvoBench (e.g., Ruby, Python).")
    parser.add_argument("--model", type=str, default="gpt-4o", help="LLM model name used by utils_llm.prompt_llm.")
    parser.add_argument("--dry_run", action="store_true", help="Do not write changes to disk.")
    parser.add_argument("--write", action="store_true", help="Write updated JSON to disk.")
    parser.add_argument("--inplace", action="store_true", help="Overwrite original file (default writes *_updated.json).")
    parser.add_argument("--output_suffix", type=str, default="_updated", help="Suffix for updated output files.")
    parser.add_argument("--no_llm", action="store_true", help="Do not call LLM; choose version from URL directly.")
    parser.add_argument("--max_items", type=int, default=None, help="Max items to process per file.")
    args = parser.parse_args()

    data_dir = args.python_dir
    if args.data_dir:
        data_dir = args.data_dir
    elif args.language:
        data_dir = os.path.join("APIEvoBench", args.language)

    file_paths = sorted(glob.glob(os.path.join(data_dir, "*_examples.json")))
    if not file_paths:
        print(f"No *_examples.json found under: {data_dir}")
        return 1

    if not args.no_llm and prompt_llm is None and not os.environ.get("OPENAI_API_KEY"):
        print("LLM is not available. Set OPENAI_API_KEY, or use --no_llm.")
        return 1

    total_considered = 0
    total_updated = 0

    for fp in file_paths:
        considered, updated = process_file(
            file_path=fp,
            model=args.model,
            dry_run=args.dry_run,
            write=args.write,
            inplace=args.inplace,
            output_suffix=args.output_suffix,
            no_llm=args.no_llm,
            max_items=args.max_items,
        )
        if considered > 0:
            print(
                f"{os.path.basename(fp)}: considered={considered}, updated={updated}, "
                f"dry_run={args.dry_run}, write={args.write}, inplace={args.inplace}, no_llm={args.no_llm}"
            )
        total_considered += considered
        total_updated += updated

    print(
        f"TOTAL: considered={total_considered}, updated={total_updated}, "
        f"dry_run={args.dry_run}, write={args.write}, inplace={args.inplace}, no_llm={args.no_llm}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
