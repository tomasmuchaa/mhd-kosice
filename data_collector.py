"""
MHD Košice - Modul pre zber historických dát vozidiel (Data Collector)
====================================================================
Tento modul slúži na kontinuálny zber reálnych telemetrických dát MHD Košice
pre účely trénovania AI modelov (predikcia meškania, optimalizácia trás, analýza zápch).

Ukladá pozície do SQLite databázy 'data/mhd_historia.db' v tabuľke 'vehicle_positions'.
Implementuje inteligentnú deduplikáciu (ukladá len zmeny polohy, meškania alebo stavu na zastávke).
"""

import os
import sys
import time
import signal
import sqlite3
from datetime import datetime
from typing import Dict, Tuple, Any

# Zabezpečenie správneho importu app modulov aj pri priamom spustení z ľubovoľného priečinka
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

# Nastavenie kódovania stdout a stderr pre bezchybný výpis na Windows termináloch
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from app.services.live_feed_service import DpmkLiveFeed
from app.services.occupancy_service import occupancy_service

DATA_DIR = os.path.join(CURRENT_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "mhd_historia.db")
POLL_INTERVAL_SECONDS = 15

# Príznak pre čisté ukončenie procesu
running = True

def handle_exit(signum, frame):
    global running
    print("\n[ZBER DÁT] Prijatý signál na ukončenie. Čisté zatváranie databázy a procesov...", flush=True)
    running = False

signal.signal(signal.SIGINT, handle_exit)
signal.signal(signal.SIGTERM, handle_exit)


def init_database(db_path: str) -> sqlite3.Connection:
    """
    Inicializuje SQLite databázu s WAL módom a vytvorí schému tabuľky vehicle_positions.
    """
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30.0)
    
    # Nastavenie WAL módu pre vysokú priepustnosť a bezproblémové čítanie počas zápisu
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")

    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS vehicle_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                vehicle_id INTEGER,
                line TEXT,
                trip_id INTEGER,
                latitude REAL,
                longitude REAL,
                delay_minutes INTEGER,
                is_on_stop INTEGER,
                occupancy_level INTEGER
            );
        """)
        # Bezpečná schéma migrácia pre existujúcu databázu
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(vehicle_positions);")
        columns = [row[1] for row in cur.fetchall()]
        if "occupancy_level" not in columns:
            conn.execute("ALTER TABLE vehicle_positions ADD COLUMN occupancy_level INTEGER DEFAULT NULL;")

        # Indexy pre rýchle filtrovanie pri AI trénovaní a dátových analýzach
        conn.execute("CREATE INDEX IF NOT EXISTS idx_vp_timestamp ON vehicle_positions(timestamp);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_vp_vehicle_id ON vehicle_positions(vehicle_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_vp_line ON vehicle_positions(line);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_vp_trip_id ON vehicle_positions(trip_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_vp_occupancy ON vehicle_positions(occupancy_level);")

    return conn


def main():
    global running
    print("=" * 70, flush=True)
    print("🚀 MHD KOŠICE - ZBERATEĽ HISTORICKÝCH DÁT PRE AI MODELY", flush=True)
    print(f"📁 Databáza: {DB_PATH}", flush=True)
    print(f"⏱️ Interval dopytovania: {POLL_INTERVAL_SECONDS} sekúnd", flush=True)
    print("=" * 70, flush=True)

    conn = init_database(DB_PATH)
    feed = DpmkLiveFeed()

    # In-memory pamäť posledného známeho stavu vozidiel:
    # vehicle_id -> (latitude_rounded, longitude_rounded, delay_minutes, is_on_stop, occupancy_level)
    last_seen: Dict[Any, Tuple[float, float, int, int, Any]] = {}

    total_inserted_all_time = 0

    try:
        # Zisti aktuálny počet záznamov v databáze
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM vehicle_positions;")
        db_count_row = cur.fetchone()
        current_db_total = db_count_row[0] if db_count_row else 0
        print(f"ℹ️ Aktuálny počet existujúcich záznamov v DB: {current_db_total:,}", flush=True)

        while running:
            loop_start = time.time()
            now_dt = datetime.now()
            now_iso = now_dt.strftime("%Y-%m-%d %H:%M:%S")

            try:
                vehicles = feed.get_live_vehicles()
            except Exception as e:
                print(f"[{now_iso}] ⚠️ Chyba pri sťahovaní live feedu: {e}", flush=True)
                vehicles = []

            records_to_insert = []
            ignored_count = 0

            for v in vehicles:
                vid = v.get("vehicle_id")
                lat = v.get("latitude")
                lng = v.get("longitude")

                if not vid or lat is None or lng is None:
                    continue

                line = str(v.get("line") or "").strip()
                trip_id = v.get("trip_id")
                delay = int(v.get("delay_minutes") or 0)
                is_on_stop = 1 if v.get("is_on_stop") else 0

                # Zistenie aktívnej crowdsourcing obsadenosti (Waze pre MHD s inteligentnou expiráciou)
                occ = occupancy_service.get_occupancy(vid, live_stop_name=v.get("current_stop_name"))
                occupancy_level = int(occ["level"]) if (occ and occ.get("level")) else None

                # Zaokrúhlenie na 5 desatinných miest (presnosť cca 1 meter)
                lat_round = round(float(lat), 5)
                lng_round = round(float(lng), 5)

                current_state = (lat_round, lng_round, delay, is_on_stop, occupancy_level)

                # Inteligentné šetrenie miesta:
                # Kontrola voči pamäti last_seen
                if vid in last_seen:
                    prev_state = last_seen[vid]
                    if current_state == prev_state:
                        # Vozidlo sa nepohlo, nezmenilo meškanie, stav na zastávke ani obsadenosť
                        ignored_count += 1
                        continue

                # Zaznamenaná zmena alebo prvé videnie
                last_seen[vid] = current_state
                records_to_insert.append((
                    now_iso,
                    vid,
                    line,
                    trip_id,
                    lat_round,
                    lng_round,
                    delay,
                    is_on_stop,
                    occupancy_level
                ))

            # Zápis balíka do SQLite v jednej transakcii
            if records_to_insert:
                try:
                    conn.executemany("""
                        INSERT INTO vehicle_positions (
                            timestamp, vehicle_id, line, trip_id, latitude, longitude, delay_minutes, is_on_stop, occupancy_level
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """, records_to_insert)
                    conn.commit()
                    inserted_count = len(records_to_insert)
                    total_inserted_all_time += inserted_count
                    current_db_total += inserted_count
                except sqlite3.Error as db_err:
                    print(f"[{now_iso}] ❌ Chyba pri zápise do DB: {db_err}", flush=True)
                    inserted_count = 0
            else:
                inserted_count = 0

            # Prehľadný konzolový log
            print(
                f"[{now_iso}] Zápis do DB: {inserted_count} nových polôh, "
                f"{ignored_count} stojacich ignorovaných | "
                f"Spolu v DB: {current_db_total:,}",
                flush=True
            )

            # Počkaj presne do ďalšieho 15-sekundového cyklu
            elapsed = time.time() - loop_start
            sleep_time = max(1.0, POLL_INTERVAL_SECONDS - elapsed)
            
            # Plynulý sleep s možnosťou okamžitého prerušenia signálom
            sleep_until = time.time() + sleep_time
            while running and time.time() < sleep_until:
                time.sleep(0.5)

    except KeyboardInterrupt:
        pass
    finally:
        print("\nUzatváram spojenie s databázou...", flush=True)
        try:
            conn.close()
        except Exception:
            pass
        print(f"Zber dát ukončený. Celkovo zapísaných v tejto relácii: {total_inserted_all_time} záznamov.", flush=True)


if __name__ == "__main__":
    main()
