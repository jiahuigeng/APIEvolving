from packaging.version import parse as parse_version, Version
import math

def get_major(v):
    return v.release[0] if v.release else 0

def get_version_candidates(data):
    versions = []
    for entry in data:
        for key in ['deprecated_in', 'removed_in']:
            v_str = entry.get(key)
            if v_str:
                try:
                    v = parse_version(v_str)
                    if not v.is_prerelease:
                        versions.append(v)
                except:
                    pass
    
    if not versions:
        return []

    by_major = {}
    for v in versions:
        major = get_major(v)
        if major not in by_major:
            by_major[major] = []
        by_major[major].append(v)
    
    candidates = set()
    
    for major, group in by_major.items():
        if not group: continue
        min_v = min(group)
        max_v = max(group)
        
        print(f"Major {major}: min={min_v}, max={max_v}")

        # 1. Smaller than min
        pre_min = None
        if min_v.release:
            parts = list(min_v.release)
            # Strategy: find last non-zero component and decrement it.
            # 1.2.3 -> 1.2.2
            # 1.2.0 -> 1.1.0
            # 1.0.0 -> 0.9.0 (if we allow major change? likely yes for pre-min)
            found = False
            for i in range(len(parts)-1, -1, -1):
                if parts[i] > 0:
                    parts[i] -= 1
                    # Fill subsequent with 0? Or just truncate?
                    # 1.2.0 -> 1.1.0. Good.
                    # 1.2.3 -> 1.2.2. Good.
                    # 1.0.0 -> 0.0.0.
                    # 2.0.0 -> 1.0.0.
                    pre_min_parts = parts[:i+1]
                    # If we shortened it (e.g. 1.2.0 -> 1.1), we might want to keep length or use standard form
                    # Let's just use what we have.
                    pre_min = ".".join(map(str, parts)) # Use full parts with decremented value
                    found = True
                    break
            
            if not found:
                # 0.0.0 case?
                pass
        
        if pre_min:
            candidates.add(pre_min)
            
        # 2. Equal to max
        candidates.add(str(max_v))
        
        # 3. Between
        if min_v < max_v:
            # Interpolate
            # We want a version V such that min_v < V < max_v
            # Normalize lengths
            len_max = max(len(min_v.release), len(max_v.release))
            min_parts = list(min_v.release) + [0]*(len_max - len(min_v.release))
            max_parts = list(max_v.release) + [0]*(len_max - len(max_v.release))
            
            mid_parts = []
            diff_index = -1
            for i in range(len_max):
                if min_parts[i] != max_parts[i]:
                    diff_index = i
                    break
            
            if diff_index != -1:
                # 1.2.0 vs 1.6.0. diff at 1. values 2 and 6. mid = 4. -> 1.4.0
                # 1.2.0 vs 1.3.0. diff at 1. values 2 and 3. mid = 2. -> 1.2... wait, equals min.
                # If mid == min_part, we need to look at next components.
                
                # Construct mid parts
                current_parts = min_parts[:]
                
                # Try to find a midpoint at diff_index
                val_min = min_parts[diff_index]
                val_max = max_parts[diff_index]
                
                if val_max - val_min > 1:
                    current_parts[diff_index] = (val_min + val_max) // 2
                    # Reset lower parts to 0
                    for k in range(diff_index+1, len_max):
                        current_parts[k] = 0
                    mid_ver = ".".join(map(str, current_parts))
                    candidates.add(mid_ver)
                else:
                    # diff is 1. e.g. 1.2 vs 1.3
                    # We need to look deeper.
                    # 1.2.0 vs 1.3.0.
                    # Effectively 1.2.0 vs 1.2.infinite? No.
                    # We can pick 1.2.5 (add a component).
                    # 1.2.0 -> 1.2.5.
                    # 1.2.0 vs 1.2.1? -> 1.2.0.5? No.
                    
                    # Heuristic: Append a '5' or similar to min_parts if strictly less
                    # 1.2 vs 1.3 -> 1.2.5
                    # 1.2.5 vs 1.2.6 -> 1.2.5.5 -> 1.2.5.5
                    
                    # Create a new part
                    # Take min_parts (which is 1.2.0 effectively).
                    # Change to 1.2.5
                    # Verify 1.2.5 < 1.3.0? Yes.
                    
                    # Check if min_parts is effectively equal to min_v
                    # We want > min_v.
                    
                    # Let's just try appending a 5 to the first diff level?
                    # 1.2 vs 1.3. diff at index 1.
                    # Keep index 1 as is (2).
                    # Add/Set index 2 to 5.
                    # Result 1.2.5.
                    
                    temp_parts = list(min_v.release)
                    # Extend if needed
                    if len(temp_parts) <= diff_index + 1:
                        temp_parts.extend([0] * (diff_index + 2 - len(temp_parts)))
                    
                    # Set the component after diff_index to 5 (or average if max has it?)
                    # If max is 1.3, it effectively has 0 at diff_index+1.
                    # So 1.2.5 is between 1.2.0 and 1.3.0.
                    
                    # What if max is 1.2.1?
                    # min=1.2.0. diff at index 2 (0 vs 1).
                    # val_max - val_min = 1.
                    # Recursive?
                    
                    # Let's just hardcode a safe bet:
                    # If gap is > 1, take average.
                    # If gap is 1, take lower + append .5 (as integer 5).
                    
                    target_idx = diff_index
                    if val_max - val_min > 1:
                        current_parts[target_idx] = (val_min + val_max) // 2
                        for k in range(target_idx+1, len(current_parts)):
                            current_parts[k] = 0
                    else:
                        # Gap is 1.
                        # e.g. 1.2 vs 1.3
                        # Use 1.2.5
                        # Need to ensure we don't exceed max if max has lower components?
                        # 1.3 is 1.3.0. 1.2.5 is < 1.3.0. Safe.
                        # What if 1.2.9 vs 1.3.0? 
                        # 1.2.9 < 1.3.0.
                        # gap at index 1 is 1 (2 vs 3).
                        # We use 1.2.5. 
                        # 1.2.5 < 1.2.9? Yes. Wait, min is 1.2.9.
                        # diff index is 1 (2 vs 3)? No.
                        # 1.2.9 vs 1.3.0.
                        # min_parts: 1, 2, 9
                        # max_parts: 1, 3, 0
                        # diff at index 1? 2 vs 3. Yes.
                        # Logic says: use 1.2.5.
                        # 1.2.5 < 1.2.9. FAILS. 1.2.5 is NOT > min.
                        
                        # Correct logic:
                        # We need something between min_v and max_v.
                        # Why not just average the version as a float? 
                        # No, versions are tuples.
                        
                        # How about checking the list of ALL versions in the group?
                        # User said "calculate min and max... then ... pick one in between".
                        # Maybe I should pick an *existing* version from the file that is between min and max?
                        # If no existing version, then generate?
                        
                        pass # Will implement in main logic
            
            # Fallback if logic above is complex:
            # Just collect all unique versions in this major group.
            # Sort them.
            # Pick one from the middle of the sorted list.
            # If list has only 2 elements (min and max), then we MUST generate.
            
            # This seems safer and more compliant with "one in between".
            # If I have [1.2, 1.3, 1.4, 1.6], min=1.2, max=1.6.
            # Middle of list is 1.3 or 1.4.
            # If [1.2, 1.6], I need to generate 1.4.
            
    return sorted(list(candidates))

# Test data
data = [
    {'deprecated_in': '1.2.0', 'removed_in': '1.6.0'},
    {'deprecated_in': '1.3.0', 'removed_in': '1.6.0'},
    {'deprecated_in': '2.0.0', 'removed_in': '2.1.0'},
    {'deprecated_in': '1.2.0', 'removed_in': '1.2.0'}, # min==max case
]

# Run
print(get_version_candidates(data))
