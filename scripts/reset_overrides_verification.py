"""
Skript pre hromadne zrusenie statusu overenia v overrides.json a synchronizaciu pamate.
Zachovava vsetky doterajsie manualne upravy (model, SPZ, evidencne cislo, poznamky),
iba nastavi verified: false a is_verified: false.
"""
import os
import json
import subprocess
from typing import Dict, Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OVERRIDES_PATH = os.path.join(PROJECT_ROOT, "data", "overrides.json")

def load_base_overrides() -> Dict[str, Dict[str, Any]]:
    current_data = {}
    if os.path.exists(OVERRIDES_PATH):
        try:
            with open(OVERRIDES_PATH, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    current_data = json.loads(content)
        except Exception as e:
            print(f"[VAROVANIE] Chyba pri citani existujuceho overrides.json: {e}")

    # Ak je subor prazdny (po predoslom premazani), nacitame perzistentne zaznamy z git historie
    if not current_data:
        try:
            cmd = ["git", "show", "7a84146:data/overrides.json"]
            res = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, check=True)
            if res.stdout.strip():
                current_data = json.loads(res.stdout)
                print(f"[INFO] Obnovenych {len(current_data)} povodnych manualnych zaznamov z git historie.")
        except Exception as e:
            print(f"[VAROVANIE] Nepodarilo sa nacitat zaznamy z git show: {e}")

    return current_data

def reset_verification_status():
    data = load_base_overrides()
    print(f"\n=======================================================")
    print(f"HROMADNA UPRAVA: Zrusenie statusu overenia (verified -> false)")
    print(f"Celkovy pocet nacitanych zaznamov: {len(data)}")
    print(f"=======================================================\n")

    updated_count = 0
    clean_overrides: Dict[str, Dict[str, Any]] = {}

    for k, v in data.items():
        clean_k = str(k).strip().replace("#", "")
        if not clean_k or not isinstance(v, dict):
            continue

        item = dict(v)
        # Cistenie cisiel od mriezok ak tam boli
        if "evidencne_cislo" in item and item["evidencne_cislo"] is not None:
            item["evidencne_cislo"] = str(item["evidencne_cislo"]).strip().replace("#", "")

        # KROK 2 & 3: Reset statusu na false pri zachovani vsetkych ostatnych dat
        item["verified"] = False
        item["is_verified"] = False

        clean_overrides[clean_k] = item
        updated_count += 1

    # Ulozenie do data/overrides.json
    os.makedirs(os.path.dirname(OVERRIDES_PATH), exist_ok=True)
    with open(OVERRIDES_PATH, "w", encoding="utf-8") as f:
        json.dump(clean_overrides, f, indent=2, ensure_ascii=False)

    print(f"[OK] Subezne ulozene zmeny do: {OVERRIDES_PATH}")
    print(f"[OK] Upravenych zaznamov: {updated_count}")

    # Synchronizacia backend pamate
    import sys
    sys.path.insert(0, PROJECT_ROOT)
    from app.services.fleet_service import FleetService
    from app.main import LAST_SEEN_CACHE

    fleet_service = FleetService()
    # Aktualizacia triednej aj instancnej MANUAL_OVERRIDES
    FleetService.MANUAL_OVERRIDES = clean_overrides
    fleet_service.MANUAL_OVERRIDES = clean_overrides
    fleet_service._sync_overrides_into_indices()

    print(f"[OK] FleetService pamät zosynchronizovana ({len(fleet_service.MANUAL_OVERRIDES)} zaznamov v MANUAL_OVERRIDES).")

    # Synchronizacia LAST_SEEN_CACHE
    synchronized_cache_count = 0
    for v in LAST_SEEN_CACHE:
        fleet_service.match_live_vehicle(v)
        synchronized_cache_count += 1

    print(f"[OK] LAST_SEEN_CACHE zosynchronizovany ({synchronized_cache_count} vozidiel).")

    # KROK 4: Validacia a potvrdenie
    print(f"\n=======================================================")
    print(f"OVERENIE VYSLEDKU (Kontrola zachovania identit a resetu overenia)")
    print(f"=======================================================")

    all_false = all(
        item.get("verified") is False and item.get("is_verified") is False
        for item in clean_overrides.values()
    )
    print(f"1. Vsetky zaznamy v overrides.json maju verified == False: {all_false}")

    # Testovacie vozidla z overrides
    test_vids = ["1276703", "1276317", "1403388", "1276522", "1276497"]
    print(f"\n2. Test sparovania live telemetrie pre vybrane vozidla:")
    print(f"{'VEHICLE ID':<12} | {'EV. CISLO':<10} | {'SPZ':<12} | {'MODEL':<24} | {'IS_VERIFIED':<11} | {'MATCHED'}")
    print("-" * 80)

    for vid in test_vids:
        raw_test = {"vehicle_id": vid, "line": "19"}
        matched = fleet_service.match_live_vehicle(raw_test)
        ev = matched.get("evidencne_cislo")
        spz = matched.get("spz") or "-"
        model = matched.get("model")
        is_ver = matched.get("is_verified")
        is_match = matched.get("matched")
        print(f"{vid:<12} | {ev:<10} | {spz:<12} | {model:<24} | {str(is_ver):<11} | {str(is_match)}")

        assert is_ver is False, f"Chyba: Vozidlo {vid} ma stale is_verified=True!"
        assert is_match is True, f"Chyba: Vozidlo {vid} sa nesparovalo s manualnou identitou!"

    print("-" * 80)
    print(f"[USPECH] Vsetky testovane vozidla si ZACHOVALI manualnu identitu a stratili status overenia (is_verified = False)!\n")

if __name__ == "__main__":
    reset_verification_status()
