import sys, json
sys.stdout.reconfigure(encoding='utf-8')

with open('data/overrides.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

vids = {}
for k, v in d.items():
    if len(str(k)) >= 7 and str(k).isdigit():
        ev = v.get('evidencne_cislo')
        vids.setdefault(ev, []).append((k, v.get('model'), v.get('spz')))

print("Duplicate fleet numbers assigned to multiple TransData IDs:")
found_dup = False
for ev, list_v in sorted(vids.items(), key=lambda x: str(x[0])):
    if len(list_v) > 1:
        found_dup = True
        print(f"Fleet #{ev}:")
        for vid, model, spz in list_v:
            print(f"   VID: {vid} | Model: {model} | SPZ: {spz}")

if not found_dup:
    print("None! Every TransData ID has a unique fleet number.")
