# -*- coding: utf-8 -*-
import urllib.request
import json
import sys

# Nastavenie UTF-8 výstupu pre Windows konzolu
sys.stdout.reconfigure(encoding='utf-8')

url = "http://127.0.0.1:8000/api/v1/vehicles/live"
try:
    with urllib.request.urlopen(url) as response:
        data = json.loads(response.read().decode('utf-8'))
        vehicles = data.get("vehicles", [])
        print(f"Počet live vozidiel: {len(vehicles)}")
        models = {}
        for v in vehicles:
            m = (v.get("fleet_info") or {}).get("model") or v.get("model") or "Neznámy"
            models[m] = models.get(m, 0) + 1
        for m, cnt in sorted(models.items(), key=lambda x: -x[1]):
            print(f"  - {m}: {cnt}x")
except Exception as e:
    print(f"Chyba: {e}")
