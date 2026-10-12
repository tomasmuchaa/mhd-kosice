import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.ubian.sk/"
}

url = "https://www.ubian.sk/navigation/vehicles/nearby?lat=48.7164&lng=21.2611&radius=25&cityID=18024"
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as resp:
    data = json.loads(resp.read().decode("utf-8"))

vehicles = data.get("vehicles", [])
print(f"Total vehicles: {len(vehicles)}")

# Let's inspect the first 5 vehicles
for i, v in enumerate(vehicles[:5]):
    print(f"\n--- VEHICLE #{i+1} (ID: {v.get('vehicleID')}) ---")
    print(f"licenseNumber: {repr(v.get('licenseNumber'))}")
    print(f"vehicleIdentificationNumber: {repr(v.get('vehicleIdentificationNumber'))}")
    print(f"tooltip: {repr(v.get('tooltip'))}")
    trip = v.get("timeTableTrip") or {}
    print(f"timeTableTrip keys: {list(trip.keys())}")
    for k in ["tripID", "trip", "destination", "destinationStopName", "operatorID", "lowFloor", "vehicleType", "vehicleDescription", "model", "note", "spz", "plateNumber"]:
        if k in trip:
            print(f" trip.{k}: {repr(trip[k])}")
    line = trip.get("timeTableLine") or {}
    print(f"timeTableLine keys: {list(line.keys())}")
    for k in ["line", "lineName", "ezLineType", "ezVehicleType", "vehicleType", "vehicleTypeName"]:
        if k in line:
            print(f" line.{k}: {repr(line[k])}")

# Let's check statistics on keys across ALL vehicles
keys_summary = {}
license_numbers = []
vins = []
tooltips = []
for v in vehicles:
    for k in v.keys():
        keys_summary[k] = keys_summary.get(k, 0) + 1
    if v.get("licenseNumber"):
        license_numbers.append(v.get("licenseNumber"))
    if v.get("vehicleIdentificationNumber"):
        vins.append(v.get("vehicleIdentificationNumber"))
    if v.get("tooltip"):
        tooltips.append(v.get("tooltip"))

print("\n--- ALL RAW VEHICLE ROOT KEYS COUNT ---")
for k, count in keys_summary.items():
    print(f"  {k}: {count}/{len(vehicles)}")

print(f"\nTotal with licenseNumber: {len(license_numbers)}")
print(f"Sample licenseNumbers: {license_numbers[:10]}")

print(f"\nTotal with vehicleIdentificationNumber: {len(vins)}")
print(f"Sample VINs: {vins[:5]}")

print(f"\nSample tooltips: {tooltips[:5]}")
