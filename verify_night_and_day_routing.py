import sys
import time
from datetime import datetime
from app.services.routing_engine import RoutingEngine

sys.stdout.reconfigure(encoding="utf-8")

print("=================================================================")
print("          TESTOVANIE STRIKTNÉHO PLÁNOVAČA TRÁS MHD KOŠICE        ")
print("=================================================================")

engine = RoutingEngine()

# TEST 1: Nočná trasa o 01:00 (Staničné námestie -> Madridská)
print("\n[TEST 1] Nočná trasa o 01:00: Staničné námestie -> Madridská")
t0 = time.time()
res1 = engine.plan_journey("Staničné námestie", "Madridská", departure_time_str="01:00")
duration_ms = (time.time() - t0) * 1000
print(f"Status: {res1.get('status')} (čas hľadania: {duration_ms:.1f} ms)")
assert res1.get("status") == "ok", "Status must be ok"
summary1 = res1.get("summary", {})
print(f"  Odchod zadaný: {summary1.get('departure_time')}")
print(f"  Príchod do cieľa: {summary1.get('arrival_time')}")
print(f"  Celkové trvanie: {summary1.get('total_duration_minutes')} min")
print(f"  Použité linky: {summary1.get('lines_used')}")

# Overenie, že odchod nie je vymyslený o 01:10, ale reálny o 03:45
wait_step = [s for s in res1.get("steps", []) if s.get("type") == "wait"][0]
print(f"  Inštrukcia čakania: {wait_step.get('instruction')}")
print(f"  Čas odchodu spoja: {wait_step.get('departure_time_str')}")
assert wait_step.get("departure_time_str") == "03:45", f"Očakávaný odchod 03:45, získaný {wait_step.get('departure_time_str')}"
assert summary1.get("arrival_time") == "04:01", f"Očakávaný príchod 04:01, získaný {summary1.get('arrival_time')}"
print("  >>> TEST 1 PREŠIEL: Systém neponúka neexistujúce nočné spoje o 01:xx, striktne dodržiava grafikon (odchod 03:45).")

# TEST 2: Nočná trasa o 02:00 (Staničné námestie -> Madridská)
print("\n[TEST 2] Nočná trasa o 02:00: Staničné námestie -> Madridská")
t0 = time.time()
res2 = engine.plan_journey("Staničné námestie", "Madridská", departure_time_str="02:00")
duration_ms = (time.time() - t0) * 1000
print(f"Status: {res2.get('status')} (čas hľadania: {duration_ms:.1f} ms)")
assert res2.get("status") == "ok", "Status must be ok"
summary2 = res2.get("summary", {})
print(f"  Odchod zadaný: {summary2.get('departure_time')}")
print(f"  Príchod do cieľa: {summary2.get('arrival_time')}")
print(f"  Celkové trvanie: {summary2.get('total_duration_minutes')} min")
wait_step2 = [s for s in res2.get("steps", []) if s.get("type") == "wait"][0]
print(f"  Inštrukcia čakania: {wait_step2.get('instruction')}")
print(f"  Čas odchodu spoja: {wait_step2.get('departure_time_str')}")
assert wait_step2.get("departure_time_str") == "03:45", f"Očakávaný odchod 03:45, získaný {wait_step2.get('departure_time_str')}"
assert summary2.get("arrival_time") == "04:01", f"Očakávaný príchod 04:01, získaný {summary2.get('arrival_time')}"
print("  >>> TEST 2 PREŠIEL: Systém neponúka vymyslené spoje o 02:xx, čaká na skutočný nočný spoj o 03:45.")

# TEST 3: Denná trasa o 08:00 (Staničné námestie -> Madridská)
print("\n[TEST 3] Denná trasa o 08:00: Staničné námestie -> Madridská")
t0 = time.time()
res3 = engine.plan_journey("Staničné námestie", "Madridská", departure_time_str="08:00")
duration_ms = (time.time() - t0) * 1000
print(f"Status: {res3.get('status')} (čas hľadania: {duration_ms:.1f} ms)")
assert res3.get("status") == "ok", "Status must be ok"
summary3 = res3.get("summary", {})
print(f"  Odchod: {summary3.get('departure_time')}, Príchod: {summary3.get('arrival_time')}, Trvanie: {summary3.get('total_duration_minutes')} min")
print(f"  Použité linky: {summary3.get('lines_used')}")
for s in res3.get("steps", []):
    print(f"    • [{s['type']}] {s.get('instruction')}")
assert summary3.get("lines_used") == ["27"], f"Očakávaná priama linka 27, získané {summary3.get('lines_used')}"
print("  >>> TEST 3 PREŠIEL: Denná linka 27 funguje plynule s reálnym časom jazdy a odchodu.")

# TEST 4: Viacero alternatívnych trás (plan_multiple_journeys) o 08:00
print("\n[TEST 4] Generovanie viacerých alternatívnych spojení (target_count=3) o 08:00")
t0 = time.time()
res4 = engine.plan_multiple_journeys("Staničné námestie", "Madridská", departure_time_str="08:00", target_count=3)
duration_ms = (time.time() - t0) * 1000
print(f"Nájdených trás: {len(res4.get('journeys', []))} (čas hľadania: {duration_ms:.1f} ms)")
assert len(res4.get("journeys", [])) >= 2, "Musí vrátiť aspoň 2 reálne alternatívy"
for idx, j in enumerate(res4.get("journeys", [])):
    s = j.get("summary", {})
    print(f"  Alternatíva #{idx+1}: Nástup o {s.get('board_time') or s.get('departure_time')} -> Príchod {s.get('arrival_time')} (Linka: {s.get('lines_used')})")

print("\n=================================================================")
print("   VŠETKY TESTY ÚSPEŠNE PREŠLI! PLÁNOVAČ JE 100% STRIKTNÝ!       ")
print("=================================================================")
