import sys, json, pandas as pd
sys.stdout.reconfigure(encoding='utf-8')

with open('data/overrides.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

df = pd.read_csv('data/dpmk_autobusy_komplet.csv')
fleet_evs = set(str(x).strip() for x in df['ev. číslo'].dropna())

print("TransData 7-digit overrides verification:")
for k, v in sorted(d.items(), key=lambda x: str(x[0])):
    if len(str(k)) >= 7 and str(k).isdigit():
        ev = str(v.get('evidencne_cislo', '')).strip()
        model = v.get('model', '')
        spz = v.get('spz', '')
        in_csv = ev in fleet_evs
        print(f"VID {k}: ev={ev:6} | in_bus_csv={str(in_csv):5} | model={model:30} | spz={spz}")
