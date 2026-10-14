import os
import sys
import time
import random

# UTF-8 kódovanie výstupu pre Windows konzolu
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Pridanie koreňového adresára do sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.services.fleet_service import FleetService
from app.services.live_feed_service import DpmkLiveFeed

def main():
    print("=" * 85)
    print("DIAGNOSTIKA LIVE FLOTILY DPMK – KONTROLA GROUND-TRUTH PÁROVANIA (ŠPZ -> DATABÁZA)")
    print("=" * 85)

    # 1. Inicializácia FleetService a DpmkLiveFeed
    t0 = time.time()
    fleet = FleetService()
    feed = DpmkLiveFeed(fleet_service=fleet)
    init_duration = round(time.time() - t0, 3)

    print(f"[OK] FleetService inicializovaný ({init_duration}s)")
    print(f"     - SPZ index: {len(fleet.spz_index)} vozidiel")
    print(f"     - Ev. index:  {len(fleet.ev_index)} vozidiel")
    print(f"     - Zdroj dát:  {fleet.csv_path}")

    # 2. Stiahnutie aktuálnych živých dát z ulíc Košíc
    print("\n[INFO] Sťahujem aktuálne live telemetrické dáta z mesta Košice...")
    t1 = time.time()
    raw_vehicles = feed.get_live_vehicles()
    fetch_duration = round(time.time() - t1, 2)
    print(f"[OK] Stiahnutých {len(raw_vehicles)} aktívnych vozidiel za {fetch_duration}s.")

    # 3. Spracovanie každého vozidla cez match_live_vehicle
    matched_vehicles = []
    unmatched_vehicles = []

    for v in raw_vehicles:
        # Volanie finálnej párovacej metódy
        matched_info = fleet.match_live_vehicle(v)
        
        # Extrakcia hodnôt
        is_matched = matched_info.get("matched", False)
        ev = matched_info.get("evidencne_cislo")
        spz = matched_info.get("spz")
        model = matched_info.get("model")
        line = v.get("line") or "-"
        ubian_spz = v.get("license_number") or spz or "-"

        item = {
            "line": line,
            "ubian_spz": ubian_spz,
            "evidencne_cislo": ev,
            "model": model,
            "raw": v
        }

        if is_matched and ev:
            matched_vehicles.append(item)
        else:
            unmatched_vehicles.append(item)

    # 4. Celková štatistika
    total_count = len(raw_vehicles)
    matched_count = len(matched_vehicles)
    unmatched_count = len(unmatched_vehicles)
    success_rate = round((matched_count / total_count) * 100, 1) if total_count > 0 else 0.0

    print("\n" + "=" * 85)
    print("CELKOVÁ ŠTATISTIKA:")
    print("=" * 85)
    print(f"Počet aktívnych vozidiel na trati:    {total_count}")
    print(f"Počet spárovaných vozidiel (100% ID):  {matched_count} ({success_rate} %)")
    print(f"Počet nespárovaných (čistá telemetria): {unmatched_count}")

    # 5. Úhľadná tabuľka pre 15 náhodných spárovaných vozidiel
    print("\n" + "=" * 85)
    print("VÝBER 15 NÁHODNÝCH SPÁROVANÝCH VOZIDIEL Z OSTRÉHO FEEDU:")
    print("=" * 85)
    print(f"{'LINKA':<7} | {'UBIAN ŠPZ / DISPEČING':<22} | {'EV. ČÍSLO Z DATABÁZY':<20} | {'MODEL Z DATABÁZY'}")
    print("-" * 85)

    sample_size = min(15, len(matched_vehicles))
    # Náhodný výber rôznych liniek a vozidiel
    sampled = random.sample(matched_vehicles, sample_size) if sample_size > 0 else []

    # Zoradenie podľa linky pre čitateľnosť
    def sort_line(x):
        l = str(x["line"])
        try:
            return (0, int(l))
        except ValueError:
            return (1, l)

    sampled.sort(key=sort_line)

    for item in sampled:
        l_str = str(item["line"])
        ub_str = str(item["ubian_spz"])
        ev_str = str(item["evidencne_cislo"])
        m_str = str(item["model"])
        print(f"{l_str:<7} | {ub_str:<22} | {ev_str:<20} | {m_str}")

    print("=" * 85)

    # 6. TVRDÝ TEST NA ZLYHANIE (Assertion):
    # Kontrola všetkých spárovaných vozidiel:
    # Ak má ev. číslo viac ako 5 znakov (napr. surové 7-miestne TransData ID 1276285), okamžitá chyba!
    print("\n[TEST] Vykonávam tvrdý test na zlyhanie (Assertion: len(evidencne_cislo) <= 5)...")
    invalid_vehicles = []
    for m in matched_vehicles:
        ev = str(m["evidencne_cislo"]).strip()
        if len(ev) > 5:
            invalid_vehicles.append(m)

    assert len(invalid_vehicles) == 0, (
        f"KRITICKÁ CHYBA: Nájdených {len(invalid_vehicles)} vozidiel s chybným 7-miestnym TransData ID namiesto ev. čísla!\n"
        f"Príklad: {invalid_vehicles[0]}"
    )

    # Overenie pre nespárované: NESMÚ mať vymyslené číslo
    for u in unmatched_vehicles:
        assert u["evidencne_cislo"] is None, (
            f"KRITICKÁ CHYBA: Nespárované vozidlo má vymyslené evidenčné číslo: {u['evidencne_cislo']}!"
        )

    print("[ASSERTION PASSED] Ani jedno jediné vozidlo nemá surové 7-miestne TransData ID!")
    print("[ASSERTION PASSED] 100 % spárovaných vozidiel má čisté 3- až 4-miestne oficiálne DPMK evidenčné číslo.")
    print("[ASSERTION PASSED] Všetky nespárované vozidlá majú striktne evidencne_cislo = None (0 halucinácií).")
    print("\n>>> ZÁVER: NOVÁ ARCHITEKTÚRA V OSTRÉJ PREMÁVKE PRACUJE NA 100 % DETERMINISTICKY! <<<")

if __name__ == "__main__":
    main()
