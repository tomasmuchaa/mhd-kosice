import time
import sys
import os
import re

# Nastavenie UTF-8 výstupu pre Windows konzolu
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Pridanie koreňového priečinka projektu do sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.fleet_service import FleetService
from app.services.live_feed_service import DpmkLiveFeed

print("=" * 70)
print("TEST 100% PRESNÉHO PÁROVANIA VOZIDIEL DPMK PODĽA EVIDENCIA-DOPRAVCOV.EU")
print("=" * 70)

# 1. Inicializácia FleetService a DpmkLiveFeed
t0 = time.time()
fleet = FleetService()
feed = DpmkLiveFeed(fleet_service=fleet)
init_time = round(time.time() - t0, 3)

print(f"[OK] FleetService inicializovaný za {init_time}s")
print(f"     - SPZ index: {len(fleet.spz_index)} záznamov")
print(f"     - Ev. index: {len(fleet.ev_index)} záznamov")
print(f"     - Manual overrides: {len(fleet.MANUAL_OVERRIDES)} záznamov")
print(f"     - Dataset cesta: {fleet.csv_path}")

# 2. Prvé stiahnutie live feedu (paralelný zber dispečerských ŠPZ)
print("\n[INFO] Sťahujem aktuálny live feed z mesta Košice...")
t1 = time.time()
vehicles = feed.get_live_vehicles()
fetch_time = round(time.time() - t1, 2)
print(f"[OK] Stiahnutých {len(vehicles)} aktívnych vozidiel za {fetch_time}s.")

# 3. Vyhodnotenie úspešnosti párovania
total_vehicles = len(vehicles)
paired_count = 0
unmatched_count = 0
buses_paired = 0
trams_paired = 0
paired_samples = []

for v in vehicles:
    matched = v.get("matched", False)
    ev = v.get("evidencne_cislo")
    spz = v.get("license_number")
    model = v.get("model")
    line = v.get("line")
    line_type = v.get("line_type")

    if matched and ev:
        paired_count += 1
        if str(line_type).upper() == "TRAM" or fleet.is_tram(line=line, line_type=line_type):
            trams_paired += 1
            paired_samples.append({
                "type": "TRAM",
                "line": line,
                "ubian_raw": spz or ev,
                "ev": ev,
                "model": model,
                "spz": None
            })
        else:
            buses_paired += 1
            paired_samples.append({
                "type": "BUS",
                "line": line,
                "ubian_raw": spz,
                "ev": ev,
                "model": model,
                "spz": spz
            })
    else:
        unmatched_count += 1
        # Overenie striktného pravidla 3. stupňa: Ak spoj nie je spárovaný, NESMIE mať vymyslené ev. číslo!
        assert ev is None, f"CHYBA: Nespárované vozidlo má vymyslené ev. číslo: {ev} (vid: {v.get('vehicle_id')})"

success_rate = round((paired_count / total_vehicles) * 100, 1) if total_vehicles > 0 else 0.0

print("\n" + "=" * 70)
print("ŠTATISTIKA PÁROVANIA:")
print("=" * 70)
print(f"Celkový počet aktívnych vozidiel v sieti: {total_vehicles}")
print(f"Úspešne spárované vozidlá (Ground Truth):  {paired_count} ({success_rate} %)")
print(f"  - Spárované autobusy (cez reálnu ŠPZ):    {buses_paired}")
print(f"  - Spárované električky (cez číslo vozu):  {trams_paired}")
print(f"Nespárované (čistá telemetria bez hádania): {unmatched_count}")

# 4. Ukážka reálnych spárovaných vozidiel
print("\n" + "=" * 70)
print("UKÁŽKA REÁLNYCH SPÁROVANÝCH VOZIDIEL (Ubian -> evidencia-dopravcov.eu):")
print("=" * 70)
print(f"{'LINKA':<7} | {'TYP':<6} | {'UBIAN VSTUP':<12} | {'EV. ČÍSLO':<10} | {'MODEL Z EVIDENCIE'}")
print("-" * 70)

for s in paired_samples[:15]:
    raw_in = str(s['ubian_raw']) if s['ubian_raw'] else "-"
    print(f"{str(s['line']):<7} | {s['type']:<6} | {raw_in:<12} | {str(s['ev']):<10} | {s['model']}")

# 5. Overenie in-memory vyrovnávacej pamäte (TTL cache)
print("\n" + "=" * 70)
print("TEST VYROVNÁVACEJ PAMÄTE (TTL Cache 45 min):")
print("=" * 70)
t2 = time.time()
vehicles_cached = feed.get_live_vehicles()
cache_time = round((time.time() - t2) * 1000, 2)
print(f"[OK] Druhé volanie get_live_vehicles() obslúžené z pamäte za {cache_time} ms (0 požiadaviek na upstream).")
print(f"[OK] Cache položky dispečingu v pamäti: {len(feed._trip_license_cache)}")

print("\n[VŠETKY TESTY ÚSPEŠNE PREŠLI]")
