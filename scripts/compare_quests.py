# scripts/compare_quests.py
# Compare quest JSON files between two output directories.

import json, os, sys

OLD_DIR = os.path.join(os.path.dirname(__file__), 'out')
NEW_DIR = os.path.join(os.path.dirname(__file__), 'out_new')

def load(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def compare(filename):
    old_path = os.path.join(OLD_DIR, filename)
    new_path = os.path.join(NEW_DIR, filename)
    
    if not os.path.exists(old_path):
        print(f'[SKIP] {filename}: not in old dir')
        return True
    if not os.path.exists(new_path):
        print(f'[SKIP] {filename}: not in new dir')
        return True
    
    old = load(old_path)
    new = load(new_path)
    
    diffs = 0
    for qid in set(old.keys()) | set(new.keys()):
        if qid not in new:
            print(f'  -{qid} (REMOVED)')
            diffs += 1
        elif qid not in old:
            print(f'  +{qid} (ADDED)')
            diffs += 1
        elif old[qid] != new[qid]:
            ov, nv = old[qid], new[qid]
            all_keys = set(ov.keys()) | set(nv.keys())
            for k in sorted(all_keys):
                if ov.get(k) != nv.get(k):
                    print(f'  {qid}.{k}: {ov.get(k)} → {nv.get(k)}')
                    diffs += 1
    
    if diffs == 0:
        print(f'[OK] {filename}: no differences')
        return True
    else:
        print(f'[FAIL] {filename}: {diffs} differences')
        return False

if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else None
    all_ok = True
    
    # Only process quest JSON files
    files = sorted(f for f in os.listdir(OLD_DIR) if f.endswith('.json') and f != 'config.json')
    if target:
        files = [f for f in files if target in f]
        if not files:
            print(f'No files matching "{target}"')
            sys.exit(1)
    
    for f in files:
        if not compare(f):
            all_ok = False
        print()
    
    if all_ok:
        print('=== ALL PASS ===')
    else:
        print('=== SOME FAILURES ===')
        sys.exit(1)
