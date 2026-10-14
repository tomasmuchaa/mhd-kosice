import os
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from app.services.fleet_service import FleetService
from app.services.live_feed_service import DpmkLiveFeed

def run_tests():
    print("--- 1. TEST NACITANIA OVERRIDES ZO SUBORU data/overrides.json PRI STARTE ---")
    fs = FleetService(csv_path="data/dpmk_autobusy_komplet.csv")
    feed = DpmkLiveFeed(fleet_service=fs)
    
    assert len(fs.MANUAL_OVERRIDES) >= 140, f"Ocakavalo sa aspon 140 overrides, nacitanych: {len(fs.MANUAL_OVERRIDES)}"
    print(f"OK: Nacitanych {len(fs.MANUAL_OVERRIDES)} zaznamov v MANUAL_OVERRIDES.")
    
    # Skontrolujeme, či existuje overené vozidlo 1276703 / 6703
    ov_6703 = fs.get_override(vehicle_id="1276703", ev_cislo="6703")
    assert ov_6703 is not None, "Override pre 6703/1276703 musi existovat!"
    assert ov_6703["model"] == "SOR NB 18 City", f"Model 6703 nesedi: {ov_6703['model']}"
    assert ov_6703["spz"] == "KE-090IY", f"SPZ 6703 nesedi: {ov_6703['spz']}"
    print("OK: Override pre 1276703/6703 nacitany spravne.")

    print("\n--- 2. TEST UPRAVY V GARAZI (OFFLINE MOD BEZ vehicle_id) ---")
    # Dispečer v garáži upraví vozidlo #5799, ktoré momentálne nie je v premávke
    test_ev = "5799"
    test_vid = "1276399"  # Simulované TransData ID pre sériu 57xx
    fs.TRANSDATA_MAPPING[test_vid] = test_ev

    fs.add_override(
        evidencne_cislo=test_ev,
        model="SOR NB 12 City Overridden",
        spz="KE-579YY",
        verified=True,
        note="Test garage override"
    )
    
    # Overíme, že override je zapísaný
    ov_check = fs.get_override(ev_cislo=test_ev)
    assert ov_check is not None, "Override pre 5799 musi byt v pamati!"
    assert ov_check["model"] == "SOR NB 12 City Overridden"
    assert ov_check["spz"] == "KE-579YY"
    assert ov_check["verified"] is True
    print("OK: Uprava v garazi pod evidencnym cislom 5799 uspesne ulozena.")

    print("\n--- 3. TEST PREBUDENIA VOZIDLA (OFFLINE -> PREMAVKA) ---")
    # Vozidlo sa prebudí a pošle surové, poškodené Ubian dáta:
    raw_ubian_vehicle = {
        "vehicle_id": test_vid,
        "line": "15",
        "license_number": "KE-CHYBNA-SPZ",
        "model": "Chybny Ubian Model",
        "latitude": 48.716,
        "longitude": 21.261,
        "delay_minutes": 2
    }

    # Aplikujeme spracovanie prichádzajúceho live objektu (apply_override_to_live_vehicle)
    feed.fleet_service.apply_override_to_live_vehicle(raw_ubian_vehicle)
    
    print("Vozidlo po prebudeni a spracovani live feedom:", raw_ubian_vehicle)
    assert raw_ubian_vehicle["model"] == "SOR NB 12 City Overridden", f"Chybny model po prebudeni: {raw_ubian_vehicle['model']}"
    assert raw_ubian_vehicle["license_number"] == "KE-579YY", f"Chybna SPZ po prebudeni: {raw_ubian_vehicle['license_number']}"
    assert raw_ubian_vehicle["evidencne_cislo"] == "5799", f"Chybne ev. cislo po prebudeni: {raw_ubian_vehicle['evidencne_cislo']}"
    assert raw_ubian_vehicle["is_verified"] is True, "Vozidlo musi byt overene (is_verified: True)!"
    print("OK: Prebudenie vozidla bezpodmienecne prepisalo surove Ubian data a zachovalo overenie!")

    print("\n--- 4. TEST ODPOJENIA A ZNOVUPRIPOJENIA DO SIETE (OFFLINE -> ONLINE CYKLUS) ---")
    # Vozidlo ide opäť do garáže (zmizne zo siete) a znova sa pripojí
    raw_second_wakeup = {
        "vehicle_id": test_vid,
        "line": "15",
        "license_number": "KE-STARY-TERMINAL",
        "model": "Karosa B 952",
        "latitude": 48.720,
        "longitude": 21.250,
        "delay_minutes": 0
    }
    match_res = fs.match_live_vehicle(
        vehicle_id=test_vid,
        license_number=raw_second_wakeup["license_number"],
        raw_vehicle=raw_second_wakeup
    )
    print("Druhy navrat do premavky:", raw_second_wakeup)
    assert raw_second_wakeup["model"] == "SOR NB 12 City Overridden"
    assert raw_second_wakeup["license_number"] == "KE-579YY"
    assert raw_second_wakeup["evidencne_cislo"] == "5799"
    assert raw_second_wakeup["is_verified"] is True
    print("OK: Identita vozidla uspesne prezila opakovane odpojenie a opatovny navrat do siete!")

    print("\n--- 5. TEST ELEKTRICIEK A IZOLACIE SPZ ---")
    raw_tram = {
        "vehicle_id": "1276824",
        "line": "9",
        "line_type": "TRAM",
        "license_number": "824",
        "model": "TRAM"
    }
    fs.match_live_vehicle(raw_tram)
    assert raw_tram["license_number"] is None, "Elektricka nesmie mat SPZ!"
    assert raw_tram["model"] == "Vario LF2+", f"Model elektricky nesedi: {raw_tram['model']}"
    assert raw_tram["evidencne_cislo"] == "824", f"Evidencne cislo elektricky nesedi: {raw_tram['evidencne_cislo']}"
    print("OK: Elektricka spracovana so spravnym modelom a izolovanou SPZ.")

    print("\n--- 6. TEST ENDPOINTU get_live_vehicles A LAST_SEEN_CACHE (GARAZ / OFFLINE PAUZA) ---")
    import app.main as main_module
    
    # Pridáme testovacie overené vozidlo 5799 do fleet_service
    main_module.fleet_service.add_override(
        evidencne_cislo="5799",
        vehicle_id="1276399",
        model="SOR NB 12 City Overridden",
        spz="KE-579YY",
        verified=True
    )
    
    # Simulácia 1: Vozidlo je online
    fake_live = [{
        "vehicle_id": "1276399",
        "line": "15",
        "line_type": "BUS",
        "license_number": "PO-CHYBA",
        "model": "Surovy Ubian Model",
        "latitude": 48.71,
        "longitude": 21.25,
        "delay_minutes": 1
    }]
    # Mockujeme live_feed.get_live_vehicles
    orig_get_live = main_module.live_feed.get_live_vehicles
    main_module.live_feed.get_live_vehicles = lambda: [dict(fake_live[0])]
    
    resp_online = main_module.get_live_vehicles(include_fallback=True)
    veh_online = next(x for x in resp_online["vehicles"] if str(x["vehicle_id"]) == "1276399")
    assert veh_online["model"] == "SOR NB 12 City Overridden"
    assert veh_online["license_number"] == "KE-579YY"
    assert veh_online["evidencne_cislo"] == "5799"
    assert veh_online["is_verified"] is True
    print("OK: Vozidlo online v get_live_vehicles ma spravne overeny model a SPZ.")

    # Simulácia 2: Vozidlo odide do garaze / nocna pauza (0 vozidiel v live feede)
    main_module.live_feed.get_live_vehicles = lambda: []
    resp_offline = main_module.get_live_vehicles(include_fallback=True)
    assert resp_offline["is_live"] is False
    veh_fallback = next(x for x in resp_offline["vehicles"] if str(x["vehicle_id"]) == "1276399")
    assert veh_fallback["model"] == "SOR NB 12 City Overridden"
    assert veh_fallback["license_number"] == "KE-579YY"
    assert veh_fallback["evidencne_cislo"] == "5799"
    assert veh_fallback["is_verified"] is True
    print("OK: Pocas offline pauzy / garaze fallback vracia 100% overene udaje.")

    # Simulácia 3: Vozidlo sa vrati spat do premavky s novou chybou z Ubianu
    fake_live_wakeup = [{
        "vehicle_id": "1276399",
        "line": "15",
        "line_type": "BUS",
        "license_number": None,
        "model": "BUS",
        "latitude": 48.72,
        "longitude": 21.26,
        "delay_minutes": 0
    }]
    main_module.live_feed.get_live_vehicles = lambda: [dict(fake_live_wakeup[0])]
    resp_wakeup = main_module.get_live_vehicles(include_fallback=True)
    veh_woke = next(x for x in resp_wakeup["vehicles"] if str(x["vehicle_id"]) == "1276399")
    assert veh_woke["model"] == "SOR NB 12 City Overridden"
    assert veh_woke["license_number"] == "KE-579YY"
    assert veh_woke["evidencne_cislo"] == "5799"
    assert veh_woke["is_verified"] is True
    print("OK: Po prebudeni do premavky vozidlo stale nesie overene udaje v LAST_SEEN_CACHE aj odpovedi!")

    # Vratime spat povodnu funkciu
    main_module.live_feed.get_live_vehicles = orig_get_live

    print("\n--- 7. TEST KONZISTENCIE KLUCOV V data/overrides.json ---")
    import json
    with open("data/overrides.json", "r", encoding="utf-8") as f:
        stored_overrides = json.load(f)
    hash_keys = [k for k in stored_overrides.keys() if "#" in k]
    assert len(hash_keys) == 0, f"Najdene kluce s mriezou '#': {hash_keys}"
    print(f"OK: Vsetkych {len(stored_overrides)} klucov v data/overrides.json je cistych bez '#'.")

    # Vyčistíme testovacie vozidlo
    for k in [test_ev, test_vid]:
        fs.MANUAL_OVERRIDES.pop(k, None)
        fs.TRANSDATA_MAPPING.pop(k, None)
        main_module.fleet_service.MANUAL_OVERRIDES.pop(k, None)
        main_module.fleet_service.TRANSDATA_MAPPING.pop(k, None)
    fs.save_overrides()
    main_module.fleet_service.save_overrides()
    print("\n>>> VSETKY TESTY ZIVOTNEHO CYKLU VOZIDIEL BOLI USPESNE! <<<")

if __name__ == "__main__":
    run_tests()
