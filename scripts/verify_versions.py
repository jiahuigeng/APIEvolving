from packaging.version import parse as parse_version, Version
import sys

def get_major(v):
    return v.release[0] if v.release else 0

def generate_candidates(data):
    # Extract all versions
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

    # Group by major
    by_major = {}
    for v in versions:
        major = get_major(v)
        if major not in by_major:
            by_major[major] = []
        by_major[major].append(v)
    
    final_candidates = set()
    
    for major, group in by_major.items():
        if not group: continue
        min_v = min(group)
        max_v = max(group)
        
        print(f"Major {major}: min={min_v}, max={max_v}")
        
        # 1. Min and Max
        final_candidates.add(str(min_v))
        final_candidates.add(str(max_v))
        
        # 2. Pre-min (Smaller than min)
        # Try to find a version < min_v
        # Heuristic: 
        # If min_v is X.Y.Z where Z>0 -> X.Y.(Z-1)
        # If min_v is X.Y.0 where Y>0 -> X.(Y-1).0
        # If min_v is X.0.0 -> (X-1).9.0 (or just X-1.0.0?)
        
        pre_min = None
        parts = list(min_v.release)
        found_lower = False
        for i in range(len(parts)-1, -1, -1):
            if parts[i] > 0:
                parts[i] -= 1
                # Fill remaining with 0? 
                # 1.2.0 -> 1.1.0 (parts[2] was 0, parts[1] 2->1)
                # Correct.
                pre_min_v = ".".join(map(str, parts))
                pre_min = pre_min_v
                found_lower = True
                break
        
        if not found_lower:
            # Case X.0.0 -> 0.0.0?
            # Or if major > 0, (X-1).0.0
            if parts[0] == 0:
                # 0.0.0 - can't go lower usually
                pass
            else:
                # This should have been caught by loop unless parts is empty?
                # parts[0] > 0.
                pass
        
        if pre_min:
             final_candidates.add(pre_min)
        
        # 3. Mid (Between min and max)
        if min_v < max_v:
            # Try to find something in between
            # Simple average logic on components?
            
            # Normalize length
            len_max = max(len(min_v.release), len(max_v.release))
            p_min = list(min_v.release) + [0]*(len_max - len(min_v.release))
            p_max = list(max_v.release) + [0]*(len_max - len(max_v.release))
            
            mid_parts = None
            
            # Find first diff
            for i in range(len_max):
                if p_min[i] != p_max[i]:
                    diff = p_max[i] - p_min[i]
                    if diff > 1:
                        # We can fit something in between at this level
                        # 1.2 vs 1.6 -> 1.4
                        new_val = p_min[i] + diff // 2
                        mid_parts = p_min[:i] + [new_val] + [0] * (len_max - i - 1)
                    else:
                        # Diff is 1. e.g. 1.2 vs 1.3
                        # We need to look at next level.
                        # 1.2.0 vs 1.3.0
                        # effectively 1.2.0 vs 1.2.infinity
                        # Pick 1.2.5
                        mid_parts = p_min[:i+1]
                        # Append a middle value (5)
                        mid_parts.append(5)
                        # Ensure we don't exceed max? 
                        # 1.3.0 > 1.2.5. Yes.
                    break
            
            if mid_parts:
                # Trim trailing zeros if appropriate?
                # 1.4.0.0 -> 1.4.0
                while len(mid_parts) > 3 and mid_parts[-1] == 0:
                    mid_parts.pop()
                mid_v = ".".join(map(str, mid_parts))
                final_candidates.add(mid_v)
    
    return sorted(list(final_candidates), key=lambda x: parse_version(x))

# Test cases
data1 = [
    {'deprecated_in': '1.2.0', 'removed_in': '1.6.0'},
    {'deprecated_in': '2.0.0', 'removed_in': '2.2.0'}
]
print("Data 1:", generate_candidates(data1))

data2 = [
    {'deprecated_in': '1.0.0', 'removed_in': '1.1.0'}
]
print("Data 2:", generate_candidates(data2))

data3 = [
    {'deprecated_in': '3.0.0', 'removed_in': '3.0.1'}
]
print("Data 3:", generate_candidates(data3))
