import os
import sys
import json
import shutil

# Pridanie koreňového adresára do sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app.services.fleet_service import FleetService

def test_collision_resolution():
    print("=" * 70)
    print("TEST: Automatické riešenie kolízií evidenčných čísel vo FleetService")
    print("=" * 70)

    # Záloha existujúceho overrides.json
    overrides_file = os.path.join(BASE_DIR, "data", "overrides.json")
    backup_file = os.path.join(BASE_DIR, "data", "overrides.json.bak")
    if os.path.exists(overrides_file):
        shutil.copyfile(overrides_file, backup_file)

    try:
        service = FleetService()
        
        # 1. Overíme, že pôvodné vozidlo 5802 existuje v ev_index (SOR NSG 12, AA-355EV)
        orig_veh = service.ev_index.get("5802")
        print(f"[1] Pôvodné vozidlo v ev_index (5802): {orig_veh}")
        assert orig_veh is not None, "Vozidlo 5802 musí existovať v ev_index!"
        orig_spz = orig_veh.get("spz")
        assert orig_spz == "AA-355EV", f"Očakávaná ŠPZ AA-355EV, získané: {orig_spz}"

        # 2. Vyvoláme kolíziu: Nové vozidlo 'NEW_DISPATCH_99' chce dostať číslo '5802'
        print("\n[2] Vyvolávame kolíziu: priradenie 5802 novému vozidlu 'NEW_DISPATCH_99'...")
        collisions = service.resolve_ev_collision(
            new_ev_cislo="5802",
            target_identifier="NEW_DISPATCH_99"
        )
        print(f"[2] Výsledok resolve_ev_collision: {collisions}")
        assert len(collisions) >= 1, "Mala byť detegovaná aspoň 1 kolízia!"
        col = collisions[0]
        assert col["new_evidencne_cislo"] == "90001", f"Očakávané nové ev. číslo 90001, získané: {col['new_evidencne_cislo']}"
        assert col["override_key"] == "AA355EV", f"Očakávaný kľúč v overrides AA355EV, získané: {col['override_key']}"
        assert col["note"] == "kolízne prečíslovanie"

        # 3. Overíme, že v MANUAL_OVERRIDES vznikol záznam pre pôvodné vozidlo pod kľúčom AA355EV
        assert "AA355EV" in service.MANUAL_OVERRIDES, "Kľúč AA355EV musí byť v MANUAL_OVERRIDES!"
        ov_entry = service.MANUAL_OVERRIDES["AA355EV"]
        print(f"\n[3] Overenie v MANUAL_OVERRIDES['AA355EV']: {ov_entry}")
        assert ov_entry["evidencne_cislo"] == "90001"
        assert ov_entry["note"] == "kolízne prečíslovanie"

        # 4. Overíme in-memory indexy (ev_index a spz_index)
        assert "90001" in service.ev_index, "Číslo 90001 musí byť v ev_index!"
        assert service.spz_index["AA355EV"]["evidencne_cislo"] == "90001", "spz_index pre AA355EV musí ukazovať na 90001!"
        print(f"[4] spz_index['AA355EV']: {service.spz_index['AA355EV']}")

        # 5. Cieľové vozidlo teraz bezpečne získa 5802
        new_res = service.set_override(
            model="Nový autobus",
            evidencne_cislo="5802",
            vehicle_id="NEW_DISPATCH_99",
            spz="AA-999ZZ"
        )
        print(f"\n[5] Cieľové vozidlo po uložení: {new_res}")
        assert service.ev_index["5802"]["model"] == "Nový autobus"
        assert service.ev_index["5802"]["spz"] == "AA-999ZZ"

        # 6. Kontrola perzistencie v data/overrides.json na disku
        with open(overrides_file, "r", encoding="utf-8") as f:
            disk_data = json.load(f)
        assert "AA355EV" in disk_data, "data/overrides.json musí obsahovať prečíslované vozidlo!"
        assert disk_data["AA355EV"]["evidencne_cislo"] == "90001"
        print(f"\n[6] Údaje na disku v overrides.json úspešne overené: AA355EV -> {disk_data['AA355EV']}")

        # 7. Test idempotencie: opakované volanie resolve_ev_collision pre to isté cieľové vozidlo nesmie hlásiť kolíziu
        repeat_cols = service.resolve_ev_collision(new_ev_cislo="5802", target_identifier="NEW_DISPATCH_99")
        print(f"\n[7] Test idempotencie (opätovné overenie cieľového vozidla): {repeat_cols}")
        assert len(repeat_cols) == 0, "Opakované volanie pre vlastné vozidlo nesmie hlásiť kolíziu!"

        # 8. Test endpointu create_or_update_override priamo
        from app.main import create_or_update_override, OverrideRequest

        print("\n[8] Test cez endpoint funkciu create_or_update_override...")
        class DummyRequest:
            def __init__(self, headers):
                self.headers = headers

        dummy_req = DummyRequest({"X-Admin-Token": "dpmkadmin"})
        payload = OverrideRequest(
            vehicle_id="NEW_FASTAPI_BUS_77",
            evidencne_cislo="5803",  # 5803 patrí SOR NSG 12 AA-362EV
            model="Testovací autobus",
            spz="AA-777TT"
        )
        res_api = create_or_update_override(payload, dummy_req)
        print(f"[8] Response endpointu: {res_api}")
        assert res_api["status"] == "ok"
        assert len(res_api.get("resolved_collisions", [])) >= 1
        col_api = res_api["resolved_collisions"][0]
        # Pôvodné vozidlo 5803 (AA-362EV) muselo byť prečíslované
        assert col_api["old_evidencne_cislo"] == "5803"
        assert col_api["new_evidencne_cislo"] in ("90001", "90002")
        print(f"[8] Kolízia cez API úspešne vyriešená: pôvodné 5803 prečíslované na {col_api['new_evidencne_cislo']}")

        print("\n" + "=" * 70)
        print("VŠETKY TESTY (SERVICE + FASTAPI API) PREBEHLI NA 100 % ÚSPEŠNE!")
        print("=" * 70)

    finally:
        # Obnovenie pôvodného overrides.json zo zálohy
        if os.path.exists(backup_file):
            shutil.copyfile(backup_file, overrides_file)
            os.remove(backup_file)
            print("[CLEANUP] Pôvodný overrides.json bol obnovený zo zálohy.")

if __name__ == "__main__":
    test_collision_resolution()
