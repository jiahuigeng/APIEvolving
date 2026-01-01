import os
import json
import glob
import argparse
import sys
import re

# Add the project root directory to sys.path to allow importing utils_llm
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from utils_llm import prompt_llm
except ImportError:
    print("Warning: Could not import utils_llm. Make sure you are running the script from the correct directory.")
    def prompt_llm(model, prompt, system_prompt=None):
        raise NotImplementedError("utils_llm not available")

def count_valid_entries():
    base_dir = "APIEvoBench"
    languages = ["Python", "Java", "C++", "JavaScript", "Ruby", "Scala"]
    
    total_valid = 0
    lib_stats = {}
    lang_stats = {lang: 0 for lang in languages}
    lang_2025_stats = {lang: 0 for lang in languages}
    lang_2020_2023_stats = {lang: 0 for lang in languages}
    total_2025 = 0
    total_2020_2023 = 0

    for lang in languages:
        lang_dir = os.path.join(base_dir, lang)
        if not os.path.exists(lang_dir):
            continue
            
        pattern = os.path.join(lang_dir, "*_examples.json")
        files = glob.glob(pattern)
        
        for file_path in files:
            library_name = os.path.basename(file_path).replace("_examples.json", "")
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                count = 0
                count_2025 = 0
                count_2020_2023 = 0
                for entry in data:
                    # Condition: has replaced_by and date is not null
                    replaced_by = entry.get("replaced_by")
                    date = entry.get("date")
                    
                    if replaced_by and date is not None:
                        count += 1
                        date_str = str(date)
                        if date_str.startswith("2025"):
                            count_2025 += 1
                        elif any(date_str.startswith(y) for y in ["2020", "2021", "2022", "2023"]):
                            count_2020_2023 += 1
                
                lib_stats[library_name] = count
                lang_stats[lang] += count
                lang_2025_stats[lang] += count_2025
                lang_2020_2023_stats[lang] += count_2020_2023
                total_valid += count
                total_2025 += count_2025
                total_2020_2023 += count_2020_2023
                
            except Exception as e:
                print(f"Error reading {file_path}: {e}")

    # Print Library stats
    print(f"{'Library':<30} | {'Valid Entries':<15}")
    print("-" * 50)
    for lib, count in sorted(lib_stats.items(), key=lambda x: x[1], reverse=True):
        print(f"{lib:<30} | {count:<15}")
    print("-" * 50)
    
    # Print Language stats
    print("\n" + "="*80)
    print(f"{'Language':<30} | {'Valid Entries':<15} | {'2025 Entries':<15} | {'2020-2023 Entries':<18}")
    print("-" * 80)
    for lang, count in sorted(lang_stats.items(), key=lambda x: x[1], reverse=True):
        count_2025 = lang_2025_stats[lang]
        count_2020_2023 = lang_2020_2023_stats[lang]
        print(f"{lang:<30} | {count:<15} | {count_2025:<15} | {count_2020_2023:<18}")
    print("-" * 80)
    
    print(f"{'Total':<30} | {total_valid:<15} | {total_2025:<15} | {total_2020_2023:<18}")

def extract_json_from_response(response):
    """
    Extracts JSON from the LLM response.
    Handles code blocks and raw JSON.
    """
    try:
        # Try finding JSON block
        match = re.search(r"```json\s*(.*?)```", response, re.DOTALL)
        if match:
            json_str = match.group(1)
        else:
            # Try finding list or dict start/end
            match = re.search(r"(\[.*\]|\{.*\})", response, re.DOTALL)
            if match:
                json_str = match.group(1)
            else:
                json_str = response
        
        return json.loads(json_str)
    except Exception as e:
        print(f"Error parsing JSON: {e}")
        print(f"Response content: {response[:200]}...") # Print first 200 chars
        return None

def generate_data(library, num_samples, output_dir, limit):
    base_dir = "APIEvoBench"
    languages = ["Python", "Java", "C++", "JavaScript", "Ruby", "Scala"]
    
    # If library is "all", process all libraries
    if library == "all":
        for lang in languages:
            lang_dir = os.path.join(base_dir, lang)
            if not os.path.exists(lang_dir):
                continue
            
            pattern = os.path.join(lang_dir, "*_examples.json")
            files = glob.glob(pattern)
            
            for file_path in files:
                lib_name = os.path.basename(file_path).replace("_examples.json", "")
                generate_single_library(lib_name, lang, file_path, num_samples, output_dir, limit)
        return

    # Single library processing
    target_file = None
    target_lang = None
    
    for lang in languages:
        lang_dir = os.path.join(base_dir, lang)
        if not os.path.exists(lang_dir):
            continue
        possible_file = os.path.join(lang_dir, f"{library}_examples.json")
        if os.path.exists(possible_file):
            target_file = possible_file
            target_lang = lang
            break
            
    if not target_file:
        print(f"Error: Could not find library '{library}' in APIEvoBench.")
        return

    generate_single_library(library, target_lang, target_file, num_samples, output_dir, limit)

def generate_single_library(library, target_lang, target_file, num_samples, output_dir, limit):
    print(f"Processing library: {library} (Language: {target_lang})")
    
    with open(target_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    # Filter entries: 2020-2023, has replaced_by
    valid_entries = []
    for entry in data:
        replaced_by = entry.get("replaced_by")
        date = entry.get("date")
        if replaced_by and date:
            date_str = str(date)
            if any(date_str.startswith(y) for y in ["2020", "2021", "2022", "2023"]):
                valid_entries.append(entry)
                
    if not valid_entries:
        print(f"No valid entries found for {library} (2020-2023 with replaced_by field).")
        return
        
    # Limit entries
    entries_to_process = valid_entries[:limit]
    print(f"Found {len(valid_entries)} valid entries for {library}. Processing first {len(entries_to_process)}.")
    
    # Output path: output_dir/vanilla/{Lang}/{library}_dataset.jsonl
    lang_output_dir = os.path.join(output_dir, "vanilla", target_lang)
    os.makedirs(lang_output_dir, exist_ok=True)
    
    output_file = os.path.join(lang_output_dir, f"{library}_dataset.jsonl")
    gt_file = os.path.join(lang_output_dir, f"{library}_gt_solution.jsonl")
    
    # Process each entry
    processed_count = 0
    with open(output_file, 'w', encoding='utf-8') as out_f, \
         open(gt_file, 'w', encoding='utf-8') as gt_f:
        for entry in entries_to_process:
            processed_count += 1
            print(f"Processing entry {processed_count}/{len(entries_to_process)}: {entry.get('api')} -> {entry.get('replaced_by')}")
            
            # Construct Prompt
            prompt = f"""
You are an expert {target_lang} developer. I need you to generate coding problems and solutions based on an API deprecation case.

Input Data:
Library: {entry.get('package')}
Language: {target_lang}
Deprecated API: {entry.get('api')}
Deprecated In Version: {entry.get('deprecated_in')}
Removed In Version: {entry.get('removed_in')}
Replaced By: {entry.get('replaced_by')}
Reason: {entry.get('reason')}

Task:
Generate {num_samples} distinct coding problems. For EACH problem, you must provide TWO scenarios:
1. "Old Scenario": Uses the Deprecated API.
2. "New Scenario": Uses the Replaced API.

CRITICAL VERSION CONSTRAINT:
- You must select ONE specific version for all "Old Scenario" cases (let's call it V_old). V_old must be strictly older than '{entry.get('deprecated_in')}'.
- You must select ONE specific version for all "New Scenario" cases (let's call it V_new). V_new must be newer than or equal to '{entry.get('removed_in')}' (or appropriate new version).
- ALL generated "Old Scenario" objects MUST have "version": "V_old".
- ALL generated "New Scenario" objects MUST have "version": "V_new".
- Similarly, ensure the "python_version" is consistent and compatible for the chosen V_old and V_new respectively.

So in total, you will generate {num_samples * 2} JSON objects ({num_samples} pairs).

Output Format:
Return a JSON list of objects. Each object must have exactly these keys:
- "language": "{target_lang}"
- "library": "{entry.get('package')}"
- "version": <The specific library version used in this example. It MUST be in format 'x.y.z' (e.g., '1.16.5'). Do not use comparison operators like '>=1.20'.>
- "python_version": <Compatible python version, e.g. "3.8.10"> (Only if language is Python, else appropriate runtime version)
- "problem": <Description of the functional task (e.g. 'Calculate the dot product'). DO NOT mention the specific API names ('{entry.get('api')}' or '{entry.get('replaced_by')}') in this description.>
- "starting_code": <Code snippet setup. Mark solution area with comments like # SOLUTION_START / # SOLUTION_END>
- "solution": <The correct code to fill in the starting_code to solve the problem.>
- "test": <A standalone test function/script that verifies the solution. It should use assertions.>
- "example_id": <Unique ID in format "{entry.get('package')}-{{version}}-{{old|new}}-{{index}}". Use 'old' if using deprecated API, 'new' if using replacement.>
- "expected_output_contains": <List of strings expected in stdout/stderr when running the test>. Should never be empty.

Guidelines:
- The "problem" description must NOT contain the names of the deprecated or replacement APIs. It should be a generic functional description.
- Ensure the "Old Scenario" uses the deprecated API '{entry.get('api')}' and fails/warns or behaves as expected in the old version.
- Ensure the "New Scenario" uses the replacement API '{entry.get('replaced_by')}' and works in the new version.
- The "solution" should be just the code that goes into the gap, or full code if starting_code is empty (prefer gap filling).
- "test" code should import the necessary libraries and the code under test (if applicable) or re-implement the setup to test the logic.
- Make sure the versions specified are realistic single versions (e.g., "1.16.5"), NOT ranges or constraints.
- REMEMBER: All "Old" examples must share the exact same version string. All "New" examples must share the exact same version string.
            """
            
            system_prompt = "You are a helpful coding assistant specialized in generating dataset samples for API evolution."
            
            try:
                response = prompt_llm("gpt-4o", prompt, system_prompt=system_prompt)
                generated_data = extract_json_from_response(response)
                
                if generated_data and isinstance(generated_data, list):
                    for item in generated_data:
                        # Inject metadata
                        item["old_api"] = entry.get("api")
                        item["new_api"] = entry.get("replaced_by")
                        item["deprecated_in"] = entry.get("deprecated_in")
                        item["removed_in"] = entry.get("removed_in")

                        # Write full generated data
                        json.dump(item, out_f)
                        out_f.write('\n')
                        
                        # Write ground truth data
                        gt_item = {
                            "example_id": item.get("example_id"),
                            "solution": item.get("solution")
                        }
                        json.dump(gt_item, gt_f)
                        gt_f.write('\n')
                        
                    print(f"  Generated {len(generated_data)} examples.")
                else:
                    print(f"  Failed to parse valid JSON list from LLM response.")
            except Exception as e:
                print(f"  Error calling LLM or processing response: {e}")

    print(f"Done for {library}. Output saved to {output_file} and {gt_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="APIEvoBench Data Generator & Stats")
    parser.add_argument("--mode", choices=["stats", "gen"], default="stats", help="Mode: stats (statistics) or gen (generation)")
    parser.add_argument("--library", type=str, help="Library name for generation (e.g., numpy)")
    parser.add_argument("--num_samples", type=int, default=3, help="Number of sample pairs to generate per entry")
    parser.add_argument("--limit", type=int, default=6, help="Limit number of entries to process")
    parser.add_argument("--output_dir", type=str, default="tmpOutput", help="Output directory")
    
    args = parser.parse_args()
    
    if args.mode == "stats":
        count_valid_entries()
    elif args.mode == "gen":
        if not args.library:
            print("Error: --library is required for generation mode.")
        else:
            generate_data(args.library, args.num_samples, args.output_dir, args.limit)
