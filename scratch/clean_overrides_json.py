import sys, json
sys.stdout.reconfigure(encoding='utf-8')

with open('data/overrides.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

# Specific fixes for duplicate TransData IDs:
# 1276364 is bus 4764 (was corrupted to 4778)
# 1276668 is bus 4768 (was corrupted to 3920)
# 1403386 is bus 4906 (EL-737CC) (was corrupted to 4905)
# 1276406 is tram 806 (was corrupted to 837, which is 1276750)
fixed_vids = {
    "1276364": {"model": "SOR NB 18 City", "evidencne_cislo": "4764", "spz": None},
    "1276668": {"model": "Solaris Urbino 18,75 III", "evidencne_cislo": "4768", "spz": None},
    "1403386": {"model": "SOR NS 18 Electric", "evidencne_cislo": "4906", "spz": "EL-737CC"},
    "1276406": {"model": "Vario LF2+", "evidencne_cislo": "806", "spz": None},
}

cleaned = {}
for k, v in d.items():
    s_k = str(k).strip()
    ev = str(v.get('evidencne_cislo', '')).strip()
    model = str(v.get('model', '')).strip()
    spz = v.get('spz')
    if spz is not None:
        spz = str(spz).strip()
        if not spz:
            spz = None

    # Skip ? and empty
    if ev == '?' or not ev or not model:
        continue

    # Hardware TransData ID (7-digit)
    if len(s_k) >= 7 and s_k.isdigit():
        if s_k in fixed_vids:
            cleaned[s_k] = fixed_vids[s_k]
        else:
            cleaned[s_k] = {
                "model": model,
                "evidencne_cislo": ev,
                "spz": spz
            }
    else:
        # Fleet number key
        # If key != ev, this was a corrupted hijacked key from the orig_ev bug -> PURGE!
        if s_k != ev:
            continue
        
        # Only keep fleet number keys that have real custom overrides (not default empty overrides)
        cleaned[s_k] = {
            "model": model,
            "evidencne_cislo": ev,
            "spz": spz
        }

with open('data/overrides.json', 'w', encoding='utf-8') as f:
    json.dump(cleaned, f, ensure_ascii=False, indent=2)

print(f"Successfully cleaned overrides.json! Remaining entries: {len(cleaned)}")
