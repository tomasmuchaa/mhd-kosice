import os
from app.services.fleet_service import FleetService

fs = FleetService(csv_path="data/dpmk_autobusy_komplet.csv")

print(f"Total overrides loaded: {len(fs.MANUAL_OVERRIDES)}")

# Test 1: Check tram override for 1276381 (#819)
tram_res = fs.match_live_vehicle(
    vehicle_id="1276381",
    line="9",
    line_type="TRAM"
)
print("Tram 1276381 match:", tram_res)
assert tram_res["model"] == "Vario LF2+", f"Expected Vario LF2+, got {tram_res['model']}"
assert tram_res["evidencne_cislo"] == "819", f"Expected 819, got {tram_res['evidencne_cislo']}"
assert tram_res["spz"] is None, "Tram SPZ must be None"

# Test 2: Check distinct terminals (e.g. 4905 vs 4906)
res_4905 = fs.match_live_vehicle(vehicle_id="1403385", line="19")
res_4906 = fs.match_live_vehicle(vehicle_id="1403386", line="19")
print("Bus 1403385 match:", res_4905)
print("Bus 1403386 match:", res_4906)
assert res_4905["evidencne_cislo"] == "4905", f"Expected 4905, got {res_4905['evidencne_cislo']}"
assert res_4906["evidencne_cislo"] == "4906", f"Expected 4906, got {res_4906['evidencne_cislo']}"

# Test 3: Verify test terminal override doesn't mutate other vehicles
test_vid = "9999991"
fs.add_override(vehicle_id=test_vid, model="Test Model Express", evidencne_cislo="7777")
res_test = fs.match_live_vehicle(vehicle_id=test_vid, line="10")
res_other = fs.match_live_vehicle(vehicle_id="1276312", line="10")
print("Test terminal match:", res_test)
print("Other terminal match (1276312):", res_other)
assert res_test["evidencne_cislo"] == "7777"
assert res_test["model"] == "Test Model Express"
assert res_other["evidencne_cislo"] == "5753"
assert res_other["model"] == "SOR NB 18 City"

# Test 4: Verify SPZ preservation when adding override without SPZ
test_vid2 = "9999992"
fs.add_override(vehicle_id=test_vid2, model="Model One", evidencne_cislo="8888", spz="KE-888AA")
res_test2 = fs.match_live_vehicle(vehicle_id=test_vid2, line="10")
assert res_test2["spz"] == "KE-888AA"
# Update model only, no spz passed
fs.add_override(vehicle_id=test_vid2, model="Model Two", evidencne_cislo="8888")
res_test2_updated = fs.match_live_vehicle(vehicle_id=test_vid2, line="10")
print("Updated model with preserved plate:", res_test2_updated)
assert res_test2_updated["model"] == "Model Two"
assert res_test2_updated["spz"] == "KE-888AA", f"Plate should be preserved! Got {res_test2_updated['spz']}"

# Clean up test overrides
for tv in [test_vid, test_vid2, "7777", "8888", "90001"]:
    if tv in fs.MANUAL_OVERRIDES:
        del fs.MANUAL_OVERRIDES[tv]
    if tv in fs.TRANSDATA_MAPPING:
        del fs.TRANSDATA_MAPPING[tv]
fs.save_overrides()

print("\n>>> ALL TESTS PASSED SUCCESSFULLY! <<<")
