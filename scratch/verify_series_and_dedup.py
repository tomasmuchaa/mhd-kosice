"""
scratch/verify_series_and_dedup.py
Overovací skript pre testovanie opravy modelov (47xx = SOR NB 18 City atď.)
a striktnej deduplikácie vozidiel v reálnom čase.
"""

import sys
import os
import json

# Uisti sa, že koreň projektu je v sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.fleet_service import FleetService
from app.services.live_feed_service import DpmkLiveFeed
from app.main import get_live_vehicles

def main():
    print("=" * 80)
    print("TEST A OVERENIE MODELOV DPMK A DEDUPLIKÁCIE")
    print("=" * 80)

    fs = FleetService()

    # 1. Záznam pre #4709 (ŠPZ KE-705IY)
    print("\n--- 1. OVERENIE ZÁZNAMU PRE #4709 (ŠPZ KE-705IY) ---")
    rec_by_ev = fs.get_by_ev_cislo("4709")
    rec_by_spz = fs.get_by_spz("KE705IY")
    matched = fs.match_live_vehicle(vehicle_id="1276409", license_number="KE-705IY", line="17", line_type="BUS")

    print(f"Pred opravou (v starom overrides.json): 'Solaris Urbino 18,75 III'")
    print(f"Po oprave (get_by_ev_cislo('4709')):    model = '{rec_by_ev.get('model')}', SPZ = '{rec_by_ev.get('spz')}'")
    print(f"Po oprave (get_by_spz('KE705IY')):      model = '{rec_by_spz.get('model')}', ev = '{rec_by_spz.get('evidencne_cislo')}'")
    print(f"Po oprave (match_live_vehicle):         model = '{matched.get('model')}', ev = '{matched.get('evidencne_cislo')}'")

    assert matched.get("model") == "SOR NB 18 City", f"Chyba: model pre 4709 je {matched.get('model')}, ocakavany SOR NB 18 City"
    assert matched.get("evidencne_cislo") == "4709", f"Chyba: ev_cislo je {matched.get('evidencne_cislo')}"
    print("[OK] Test pre #4709 uspesny: SOR NB 18 City!")

    # 2. Zoznam vsetkych aktivnych 47xx v zivej premavke a ich modely
    print("\n--- 2. ZOZNAM VŠETKÝCH AKTÍVNYCH 47xx V ŽIVEJ PREMÁVKE ---")
    live_response = get_live_vehicles()
    vehicles = live_response.get("vehicles", [])
    print(f"Celkovo vozidiel na mape: {len(vehicles)}")

    active_47xx = []
    for v in vehicles:
        ev = str(v.get("evidencne_cislo") or "").strip()
        if ev.startswith("47") and len(ev) == 4:
            active_47xx.append(v)

    print(f"Nájdených {len(active_47xx)} aktívnych autobusov série 47xx:")
    print(f"{'LINKA':<8} | {'EV. ČÍSLO':<10} | {'ŠPZ':<12} | {'MODEL'}")
    print("-" * 55)
    for v in sorted(active_47xx, key=lambda x: x.get("evidencne_cislo") or ""):
        line = v.get("line") or "?"
        ev = v.get("evidencne_cislo") or "?"
        spz = v.get("license_number") or "---"
        model = v.get("model") or "?"
        print(f"{line:<8} | #{ev:<9} | {spz:<12} | {model}")
        assert model == "SOR NB 18 City", f"Chyba: Vozidlo #{ev} ma nespravny model {model}"

    print(f"[OK] Všetkých {len(active_47xx)} aktívnych vozidiel série 47xx má 100% správny model 'SOR NB 18 City'!")

    # 3. Kontrola ostatných sérií v databáze (57xx, 39xx, 35xx, 48xx, 49xx, 68xx, 69xx)
    print("\n--- 3. KONTROLA MODELOV PODĽA OFICIÁLNYCH SÉRIÍ DPMK ---")
    test_cases = [
        ("4701", "SOR NB 18 City"),
        ("4764", "SOR NB 18 City"),
        ("5701", "SOR NB 12 City"),
        ("5750", "SOR NB 12 City"),
        ("3901", "Solaris Urbino 18 III"),
        ("3912", "Solaris Urbino 18,75 III"),
        ("3501", "Solaris Urbino 15"),
        ("4801", "SOR NSG 18"),
        ("4901", "SOR NS 18 Electric"),
        ("6801", "SOR EBN 10.5"),
        ("6901", "SOR EBN 11"),
        ("810", "Vario LF2+"),
        ("525", "Tatra KT8D5.RN2"),
        ("612", "Tatra T6A5"),
    ]
    for ev_test, expected_m in test_cases:
        series_m = fs.get_series_model(ev_test)
        db_item = fs.get_by_ev_cislo(ev_test)
        db_m = db_item.get("model") if db_item else None
        print(f"#{ev_test:<6}: series_model = '{series_m}' | db_model = '{db_m}' (očakávané: '{expected_m}')")
        assert series_m == expected_m, f"Chyba series_m pre {ev_test}: {series_m} != {expected_m}"

    print("[OK] Všetky série DPMK sú overené!")

    # 4. Tvrdý test na deduplikáciu: assertion confirmation len(ev_cisla) == len(set(ev_cisla))
    print("\n--- 4. STRIKTNÝ TEST DEDUPLIKÁCIE (ASSERTION CONFIRMATION) ---")
    ev_cisla = [str(v.get("evidencne_cislo")).strip() for v in vehicles if v.get("evidencne_cislo")]
    print(f"Počet vozidiel s prideleným ev. číslom: {len(ev_cisla)}")
    print(f"Počet unikátnych ev. čísel:            {len(set(ev_cisla))}")

    # Nájdi prípadné duplicity
    counts = {}
    for ev in ev_cisla:
        counts[ev] = counts.get(ev, 0) + 1
    dups = {k: v for k, v in counts.items() if v > 1}

    if dups:
        print(f"[ZLYHANIE] Nájdené duplicity: {dups}")
    else:
        print("[ÚSPECH] Žiadne duplicity evidenčných čísel sa na mape nenachádzajú!")

    assert len(ev_cisla) == len(set(ev_cisla)), f"Deduplikácia zlyhala! Nájdené duplicity: {dups}"
    print(f"[POTVRDENÉ] Assertion úspešný: len(ev_cisla) == len(set(ev_cisla)) ({len(ev_cisla)} == {len(set(ev_cisla))})")
    print("=" * 80)

if __name__ == "__main__":
    main()
