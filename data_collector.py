"""
MHD Košice - Modul pre zber historických dát vozidiel (Data Collector)
====================================================================
Tento modul slúži na kontinuálny zber reálnych telemetrických dát MHD Košice
pre účely trénovania AI modelov (predikcia meškania, optimalizácia trás, analýza zápch).

Ukladá pozície do SQLite databázy 'data/mhd_historia.db' v tabuľke 'vehicle_positions'
a crowdsourcingové hlásenia do 'occupancy_reports'.
Implementuje inteligentnú deduplikáciu (ukladá len zmeny polohy, meškania, stavu na zastávke alebo obsadenosti).
"""

import os
import sys
import time
import signal
from datetime import datetime
from typing import Dict, Tuple, Any

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from app.services.live_feed_service import DpmkLiveFeed
from app.services.occupancy_service import occupancy_service
from app.services.telemetry_db import telemetry_db

POLL_INTERVAL_SECONDS = 15
running = True


def handle_exit(signum, frame):
    global running
    print("\n[ZBER DÁT] Prijatý signál na ukončenie. Čisté zatváranie databázy a procesov...", flush=True)
    running = False


signal.signal(signal.SIGINT, handle_exit)
signal.signal(signal.SIGTERM, handle_exit)


def main():
    global running
    print("=" * 70, flush=True)
    print("🚀 MHD KOŠICE - ZBERATEĽ HISTORICKÝCH DÁT PRE AI MODELY", flush=True)
    print(f"📁 Databáza: {telemetry_db.db_path}", flush=True)
    print(f"⏱️ Interval dopytovania: {POLL_INTERVAL_SECONDS} sekúnd", flush=True)
    print("=" * 70, flush=True)

    feed = DpmkLiveFeed()
    last_seen: Dict[Any, Tuple[float, float, int, int, Any]] = {}
    total_inserted_all_time = 0

    try:
        conn = telemetry_db._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM vehicle_positions;")
        current_db_total = cur.fetchone()[0]
        conn.close()
        print(f"ℹ️ Aktuálny počet existujúcich záznamov v DB: {current_db_total:,}", flush=True)

        while running:
            loop_start = time.time()
            now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            inserted, ignored = telemetry_db.collect_telemetry_batch(feed, occupancy_service, last_seen)
            total_inserted_all_time += inserted
            current_db_total += inserted

            print(
                f"[{now_iso}] Zápis do DB: {inserted} nových polôh, "
                f"{ignored} stojacich ignorovaných | "
                f"Spolu v DB: {current_db_total:,}",
                flush=True
            )

            elapsed = time.time() - loop_start
            sleep_time = max(1.0, POLL_INTERVAL_SECONDS - elapsed)
            sleep_until = time.time() + sleep_time
            while running and time.time() < sleep_until:
                time.sleep(0.5)

    except KeyboardInterrupt:
        pass
    finally:
        print(f"\nZber dát ukončený. Celkovo zapísaných v tejto relácii: {total_inserted_all_time} záznamov.", flush=True)


if __name__ == "__main__":
    main()
