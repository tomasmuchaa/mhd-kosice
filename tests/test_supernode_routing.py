import sys
import requests

sys.stdout.reconfigure(encoding='utf-8')

def p(text):
    print(text, flush=True)

def run_tests():
    p("--- TEST 1: Journey from Námestie osloboditeľov (1000000064_3) to Staničné námestie (1000000030_1) ---")
    r1 = requests.get('http://127.0.0.1:8000/api/v1/routing/journey', params={'from_id': '1000000064_3', 'to_id': '1000000030_1'})
    p(f"HTTP status: {r1.status_code}")
    d1 = r1.json()
    p(f"Status: {d1.get('status')} | Total journeys: {d1.get('total_journeys')}")
    if d1.get('journeys'):
        j = d1['journeys'][0]
        p(f"From: {j['from_stop']['name']} -> To: {j['to_stop']['name']}")
        p(f"Lines used: {j['summary']['lines_used']} | Duration: {j['summary']['total_duration_minutes']} min")
        for s in j['steps'][:4]:
            p(f"  • [{s.get('icon', '*')}] {s.get('instruction')}")

    p("\n--- TEST 2: Journey using canonical text names ('Námestie osloboditeľov' -> 'Staničné námestie') ---")
    r2 = requests.get('http://127.0.0.1:8000/api/v1/routing/journey', params={'from_id': 'Námestie osloboditeľov', 'to_id': 'Staničné námestie'})
    p(f"HTTP status: {r2.status_code}")
    d2 = r2.json()
    p(f"Status: {d2.get('status')} | Total journeys: {d2.get('total_journeys')}")
    if d2.get('journeys'):
        j2 = d2['journeys'][0]
        p(f"From: {j2['from_stop']['name']} -> To: {j2['to_stop']['name']}")
        p(f"Lines used: {j2['summary']['lines_used']} | Duration: {j2['summary']['total_duration_minutes']} min")

    p("\n--- TEST 3: Platforms within the SAME hub ('1000000064_1' -> '1000000064_3') ---")
    r3 = requests.get('http://127.0.0.1:8000/api/v1/routing/journey', params={'from_id': '1000000064_1', 'to_id': '1000000064_3'})
    p(f"HTTP status: {r3.status_code}")
    d3 = r3.json()
    p(f"Status: {d3.get('status')} | Journeys: {d3.get('total_journeys')}")
    if d3.get('journeys'):
        p(f"Message: {d3['journeys'][0].get('message')}")
        p(f"Steps: {[s['instruction'] for s in d3['journeys'][0].get('steps', [])]}")

    p("\n--- TEST 4: GPS coordinates to hub ('48.716, 21.260' -> 'Staničné námestie') ---")
    r4 = requests.get('http://127.0.0.1:8000/api/v1/routing/journey', params={'from_lat': 48.716, 'from_lon': 21.260, 'to_id': '1000000030_1'})
    p(f"HTTP status: {r4.status_code}")
    d4 = r4.json()
    p(f"Status: {d4.get('status')} | Total journeys: {d4.get('total_journeys')}")
    if d4.get('journeys'):
        j4 = d4['journeys'][0]
        p(f"From: {j4['from_stop']['name']} -> To: {j4['to_stop']['name']}")
        for s in j4['steps'][:3]:
            p(f"  • [{s.get('icon', '*')}] {s.get('instruction')}")

    p("\nALL TESTS COMPLETED SUCCESSFULLY!")

if __name__ == '__main__':
    run_tests()
