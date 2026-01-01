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
    # Find the language for the library
    languages = ["Python", "Java", "C++", "JavaScript", "Ruby", "Scala"]
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
        print("No valid entries found for 2020-2023 with replaced_by field.")
        return
        
    # Limit entries
    entries_to_process = valid_entries[:limit]
    print(f"Found {len(valid_entries)} valid entries. Processing first {len(entries_to_process)}.")
    
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{library}_generated.jsonl")
    
    # Process each entry
    processed_count = 0
    with open(output_file, 'w', encoding='utf-8') as out_f:
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
1. "Old Scenario": Uses the Deprecated API. The library version must be older than '{entry.get('deprecated_in')}'.
2. "New Scenario": Uses the Replaced API. The library version must be newer than or equal to '{entry.get('removed_in')}' (or appropriate new version).

So in total, you will generate {num_samples * 2} JSON objects ({num_samples} pairs).

Output Format:
Return a JSON list of objects. Each object must have exactly these keys:
- "language": "{target_lang}"
- "library": "{entry.get('package')}"
- "version": <The specific library version used in this example>
- "python_version": <Compatible python version, e.g. "3.8.10"> (Only if language is Python, else appropriate runtime version)
- "problem": <Description of the task. Mention the API context if relevant.>
- "starting_code": <Code snippet setup. Mark solution area with comments like # SOLUTION_START / # SOLUTION_END>
- "solution": <The correct code to fill in the starting_code to solve the problem.>
- "test": <A standalone test function/script that verifies the solution. It should use assertions.>
- "example_id": <Unique ID, e.g. "{entry.get('package')}-{{version}}-{{index}}">
- "expected_output_contains": <List of strings expected in stdout/stderr when running the test>

Guidelines:
- Ensure the "Old Scenario" uses the deprecated API '{entry.get('api')}' and fails/warns or behaves as expected in the old version.
- Ensure the "New Scenario" uses the replacement API '{entry.get('replaced_by')}' and works in the new version.
- The "solution" should be just the code that goes into the gap, or full code if starting_code is empty (prefer gap filling).
- "test" code should import the necessary libraries and the code under test (if applicable) or re-implement the setup to test the logic.
- Make sure the versions specified are realistic.
            """
            
            system_prompt = "You are a helpful coding assistant specialized in generating dataset samples for API evolution."
            
            try:
                response = prompt_llm("gpt-4o", prompt, system_prompt=system_prompt)
                generated_data = extract_json_from_response(response)
                
                if generated_data and isinstance(generated_data, list):
                    for item in generated_data:
                        json.dump(item, out_f)
                        out_f.write('\n')
                    print(f"  Generated {len(generated_data)} examples.")
                else:
                    print(f"  Failed to parse valid JSON list from LLM response.")
            except Exception as e:
                print(f"  Error calling LLM or processing response: {e}")

    print(f"Done. Output saved to {output_file}")

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
