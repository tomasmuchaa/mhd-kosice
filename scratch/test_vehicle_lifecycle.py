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

    # Vyčistíme testovacie vozidlo
    for k in [test_ev, test_vid]:
        fs.MANUAL_OVERRIDES.pop(k, None)
        fs.TRANSDATA_MAPPING.pop(k, None)
    fs.save_overrides()
    print("\n>>> VSETKY TESTY ZIVOTNEHO CYKLU VOZIDIEL BOLI USPESNE! <<<")

if __name__ == "__main__":
    run_tests()
