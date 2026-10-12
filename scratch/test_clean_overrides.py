import sys, json
sys.stdout.reconfigure(encoding='utf-8')

with open('data/overrides.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

cleaned = {}
removed_mismatched = []
removed_invalid = []

for k, v in d.items():
    ev = str(v.get('evidencne_cislo', '')).strip()
    model = v.get('model', '').strip()
    spz = v.get('spz')

    # Remove invalid ? entries
    if ev == '?' or not ev or not model:
        removed_invalid.append((k, ev, model))
        continue

    # If key is 7-digit TransData ID, it's a hardware override - ALWAYS KEEP!
    if len(str(k)) >= 7 and str(k).isdigit():
        cleaned[str(k)] = {
            "model": model,
            "evidencne_cislo": ev,
            "spz": spz
        }
    else:
        # It's a short key (fleet number)
        # If key != ev, it was a hijacked orig_ev entry -> REMOVE!
        if str(k).strip() != ev:
            removed_mismatched.append((k, ev, model))
            continue
        # If key == ev: check if it's already represented by a TransData ID
        # Only keep static fleet overrides that don't collide
        cleaned[str(k)] = {
            "model": model,
            "evidencne_cislo": ev,
            "spz": spz
        }

print(f"Original entries: {len(d)}")
print(f"Removed mismatched hijacked keys: {len(removed_mismatched)}")
print(f"Removed invalid (?) keys: {len(removed_invalid)}")
print(f"Cleaned entries count: {len(cleaned)}")

# Check duplicate fleet numbers in hardware overrides
hardware_evs = {}
for k, v in cleaned.items():
    if len(k) >= 7:
        hardware_evs.setdefault(v['evidencne_cislo'], []).append((k, v['model'], v['spz']))

print("\nHardware terminal mappings by fleet number:")
for ev, list_v in sorted(hardware_evs.items()):
    if len(list_v) > 1:
        print(f"Fleet #{ev} has multiple terminals (independent hardware units):")
        for vid, m, s in list_v:
            print(f"   {vid} -> {m} (SPZ: {s})")
