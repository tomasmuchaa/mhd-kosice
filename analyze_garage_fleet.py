#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Skript na analýzu vozidiel aktuálne odstavených v garáži DPMK.
- Načíta dáta z dpmk_autobusy_komplet.csv
- Vyfiltruje len aktívne vozidlá (stĺpec vyradenia je prázdny)
- Získa live vozidlá z Ubian streamu
- Odpočíta premávajúce vozidlá a zoskupí vozidlá v garáži podľa modelu (typ)
"""

import sys
import os
import pandas as pd

# Nastavenie kódovania pre konzolu
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Pridanie koreňového adresára projektu do sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from app.services.live_feed_service import DpmkLiveFeed
from app.services.fleet_service import FleetService

CSV_PATH = os.path.join(BASE_DIR, "data", "dpmk_autobusy_komplet.csv")

def analyze_garage():
    if not os.path.exists(CSV_PATH):
        print(f"CHYBA: CSV súbor {CSV_PATH} neexistuje.")
        return

    # 1. Načítanie CSV
    df = pd.read_csv(CSV_PATH)
    ret_col = next((c for c in df.columns if any(w in c.lower() for w in ["vyradenie", "likvid", "odstavenie"])), "(odstavenie) vyradenie [likvidácia]")
    model_col = next((c for c in df.columns if "typ" in c.lower()), "typ")
    ev_col = next((c for c in df.columns if "ev." in c.lower() or "číslo" in c.lower()), "ev. číslo")
    spz_col = next((c for c in df.columns if "EČV" in c or "ŠPZ" in c), "EČV / ŠPZ")

    # 2. Aplikovanie filtra: vyradenie neaktívnych vozidiel
    is_active = df[ret_col].isna() | df[ret_col].astype(str).str.strip().isin(["", "nan", "None", "NaN"])
    active_df = df[is_active].copy()

    # Normalizácia evidenčných čísel a ŠPZ
    active_df["ev_clean"] = active_df[ev_col].fillna("").astype(str).str.replace(".0", "", regex=False).str.strip()
    active_df["spz_clean"] = active_df[spz_col].fillna("").astype(str).str.replace(" ", "", regex=False).str.replace("-", "", regex=False).str.upper()

    # 3. Získanie aktuálne jazdiacich vozidiel z live feedu
    lf = DpmkLiveFeed()
    fs = FleetService(CSV_PATH)
    live_vehicles = lf.get_live_vehicles() or []

    active_ev_set = set()
    active_spz_set = set()

    for v in live_vehicles:
        is_tram = fs.is_tram(
            vehicle_id=v.get("vehicle_id"),
            line=v.get("line"),
            line_type=v.get("line_type"),
            raw_vehicle=v
        )
        if is_tram:
            continue

        spz = v.get("license_number")
        if spz:
            active_spz_set.add(spz.replace(" ", "").replace("-", "").upper())

        matched = fs.match_live_vehicle(
            vehicle_id=v.get("vehicle_id"),
            license_number=spz,
            line=v.get("line"),
            line_type=v.get("line_type"),
            raw_vehicle=v
        )
        if matched:
            if matched.get("evidencne_cislo"):
                active_ev_set.add(str(matched["evidencne_cislo"]).strip())
            if matched.get("spz"):
                active_spz_set.add(matched["spz"].replace(" ", "").replace("-", "").upper())
        elif v.get("vehicle_id"):
            s_vid = str(v.get("vehicle_id")).strip()
            active_ev_set.add(s_vid)
            if len(s_vid) >= 4:
                active_ev_set.add(s_vid[-4:])

    # 4. Odčítanie live vozidiel
    def check_in_service(row):
        ev = row["ev_clean"]
        spz = row["spz_clean"]
        return (ev in active_ev_set) or (bool(spz) and spz in active_spz_set)

    active_df["in_service"] = active_df.apply(check_in_service, axis=1)
    garage_df = active_df[~active_df["in_service"]].copy()

    # 5. Zoskupenie a výpis
    counts = garage_df[model_col].value_counts()

    print("=" * 60)
    print("STAV VOZOVÉHO PARKU V GARÁŽI DPMK (LIVE ANALÝZA)")
    print("=" * 60)
    print(f"Aktívne autobusy v databáze CSV: {len(active_df)} ks")
    print(f"Autobusy aktuálne v premávke na linkách: {len(active_df) - len(garage_df)} ks")
    print(f"Autobusy aktuálne odstavené v garáži: {len(garage_df)} ks")
    print("-" * 60)
    print("PREHĽAD MODELOV V GARÁŽI:")
    print("-" * 60)
    for model, count in counts.items():
        print(f"{model} - {count} ks")
    print("=" * 60)

if __name__ == "__main__":
    analyze_garage()
