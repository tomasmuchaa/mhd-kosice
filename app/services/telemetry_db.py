"""
MHD Košice - Databázová vrstva pre telemetriu a obsadenosť (SQLite WAL)
========================================================================
Spravuje perzistentné ukladanie polôh vozidiel a crowdsourcingových
hlásení obsadenosti do 'data/mhd_historia.db'.

Používa SQLite WAL mód (PRAGMA journal_mode = WAL) pre bezproblémový
paralelný zápis popri čítaní bez uzamykania.
"""

import os
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Dict, Tuple, List, Optional, Any, Union

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "data", "mhd_historia.db")


class TelemetryDB:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def _init_db(self):
        """Inicializuje schému a migruje potrebné stĺpce a indexy."""
        conn = self._get_connection()
        try:
            with conn:
                # 1. Tabuľka histórie polôh
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
                        current_stop_name TEXT,
                        occupancy_level INTEGER,
                        occupancy_reported_at TEXT
                    );
                """)

                # Migrácia chýbajúcich stĺpcov vo vehicle_positions
                cur = conn.cursor()
                cur.execute("PRAGMA table_info(vehicle_positions);")
                existing_cols = {row[1] for row in cur.fetchall()}

                if "current_stop_name" not in existing_cols:
                    conn.execute("ALTER TABLE vehicle_positions ADD COLUMN current_stop_name TEXT DEFAULT NULL;")
                if "occupancy_level" not in existing_cols:
                    conn.execute("ALTER TABLE vehicle_positions ADD COLUMN occupancy_level INTEGER DEFAULT NULL;")
                if "occupancy_reported_at" not in existing_cols:
                    conn.execute("ALTER TABLE vehicle_positions ADD COLUMN occupancy_reported_at TEXT DEFAULT NULL;")

                # Indexy pre rýchle analytické dopyty a AI trénovanie
                conn.execute("CREATE INDEX IF NOT EXISTS idx_vp_timestamp ON vehicle_positions(timestamp);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_vp_vehicle_id ON vehicle_positions(vehicle_id);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_vp_line ON vehicle_positions(line);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_vp_trip_id ON vehicle_positions(trip_id);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_vp_occupancy ON vehicle_positions(occupancy_level);")

                # 2. Nová dedikovaná tabuľka pre crowdsourcingové hlásenia obsadenosti
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS occupancy_reports (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        vehicle_id INTEGER,
                        line TEXT,
                        stop_name TEXT,
                        occupancy_level INTEGER
                    );
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_or_vehicle_time ON occupancy_reports(vehicle_id, timestamp);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_or_timestamp ON occupancy_reports(timestamp);")
        finally:
            conn.close()

    def log_occupancy_report(
        self,
        vehicle_id: Any,
        level: int,
        line: Optional[str] = None,
        stop_name: Optional[str] = None,
        timestamp: Optional[str] = None
    ) -> bool:
        """
        Okamžite zapíše nové nahlásenie zaplnenosti do tabuľky occupancy_reports.
        """
        now_iso = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            vid_int = int(vehicle_id)
        except (ValueError, TypeError):
            vid_int = None

        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    conn.execute("""
                        INSERT INTO occupancy_reports (timestamp, vehicle_id, line, stop_name, occupancy_level)
                        VALUES (?, ?, ?, ?, ?);
                    """, (now_iso, vid_int, str(line).strip() if line else None, str(stop_name).strip() if stop_name else None, int(level)))
                return True
            except Exception as e:
                print(f"[TelemetryDB] Chyba pri zápise occupancy_report: {e}")
                return False
            finally:
                conn.close()

    def insert_vehicle_positions(self, records: List[Tuple]) -> int:
        """
        Zapíše dávku nových zmenených polôh do tabuľky vehicle_positions.
        """
        if not records:
            return 0

        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    conn.executemany("""
                        INSERT INTO vehicle_positions (
                            timestamp, vehicle_id, line, trip_id, latitude, longitude,
                            delay_minutes, is_on_stop, current_stop_name, occupancy_level, occupancy_reported_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """, records)
                return len(records)
            except Exception as e:
                print(f"[TelemetryDB] Chyba pri zápise vehicle_positions: {e}")
                return 0
            finally:
                conn.close()

    def collect_telemetry_batch(
        self,
        live_feed: Any,
        occupancy_service: Any,
        last_seen: Dict[Any, Tuple[float, float, int, int, Any]]
    ) -> Tuple[int, int]:
        """
        Stiahne aktuálny feed, porovná voči last_seen pamäti a zapíše iba zmenené záznamy.
        Vráti tuple (inserted_count, ignored_count).
        """
        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            vehicles = live_feed.get_live_vehicles() or []
        except Exception as e:
            print(f"[TelemetryDB] Chyba pri sťahovaní live feedu: {e}")
            return 0, 0

        records_to_insert = []
        ignored_count = 0

        for v in vehicles:
            vid = v.get("vehicle_id")
            lat = v.get("latitude")
            lng = v.get("longitude")

            if not vid or lat is None or lng is None:
                continue

            try:
                vid_int = int(vid)
            except (ValueError, TypeError):
                vid_int = None

            line = str(v.get("line") or "").strip()
            trip_id = v.get("trip_id")
            try:
                trip_id_int = int(trip_id) if trip_id is not None else None
            except (ValueError, TypeError):
                trip_id_int = None

            delay = int(v.get("delay_minutes") or 0)
            is_on_stop = 1 if v.get("is_on_stop") else 0
            current_stop = v.get("current_stop_name")

            # Aktívna obsadenosť s inteligentným starnutím (5 min alebo nová zastávka)
            occ = occupancy_service.get_occupancy(vid, live_stop_name=current_stop, live_is_on_stop=bool(is_on_stop))
            occupancy_level = int(occ["level"]) if (occ and occ.get("level")) else None
            occupancy_reported_at = occ.get("reported_at_iso") if occ else None

            # Zaokrúhlenie polohy na 5 desatinných miest (cca 1 meter)
            lat_round = round(float(lat), 5)
            lng_round = round(float(lng), 5)

            current_state = (lat_round, lng_round, delay, is_on_stop, occupancy_level)

            # Inteligentná deduplikácia: zapíšeme LEN pri zmene stavu
            if vid in last_seen and last_seen[vid] == current_state:
                ignored_count += 1
                continue

            last_seen[vid] = current_state
            records_to_insert.append((
                now_iso,
                vid_int,
                line,
                trip_id_int,
                lat_round,
                lng_round,
                delay,
                is_on_stop,
                current_stop,
                occupancy_level,
                occupancy_reported_at
            ))

        if records_to_insert:
            inserted = self.insert_vehicle_positions(records_to_insert)
        else:
            inserted = 0

        return inserted, ignored_count

    def get_vehicle_assignment_stats(
        self,
        vehicle_ids: List[int],
        days: int = 14,
        min_records: int = 10,
        display_id: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Agreguje nasadzovanie vozidla na linky za posledných N dní (predvolene 14 dní).
        Vráti percentuálne zastúpenie TOP 3 liniek (+ 'Ostatné' ak existujú viac ako 4 linky).
        """
        out_vid = display_id
        if out_vid is None and vehicle_ids:
            out_vid = vehicle_ids[0]
        if isinstance(out_vid, str) and out_vid.isdigit():
            out_vid = int(out_vid)

        if not vehicle_ids:
            return {
                "vehicle_id": out_vid,
                "period_days": days,
                "total_records": 0,
                "has_data": False,
                "lines": []
            }

        since_iso = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        placeholders = ",".join("?" for _ in vehicle_ids)
        query = f"""
            SELECT line, COUNT(*) as samples_count
            FROM vehicle_positions
            WHERE vehicle_id IN ({placeholders})
              AND timestamp >= ?
              AND line IS NOT NULL AND line != ''
            GROUP BY line
            ORDER BY samples_count DESC;
        """

        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute(query, (*vehicle_ids, since_iso))
                rows = cur.fetchall()
            except Exception as e:
                print(f"[TelemetryDB] Chyba pri get_vehicle_assignment_stats: {e}")
                rows = []
            finally:
                conn.close()

        total_samples = sum(r[1] for r in rows)
        if total_samples < min_records or not rows:
            return {
                "vehicle_id": out_vid,
                "period_days": days,
                "total_records": total_samples,
                "has_data": False,
                "lines": []
            }

        lines_res = []
        if len(rows) <= 4:
            target_items = rows
            others_count = 0
        else:
            target_items = rows[:3]
            others_count = sum(r[1] for r in rows[3:])

        for line_name, count in target_items:
            pct = round((count / total_samples) * 100)
            lines_res.append({
                "line": str(line_name),
                "percentage": int(pct),
                "count": int(count)
            })

        if others_count > 0:
            others_pct = round((others_count / total_samples) * 100)
            lines_res.append({
                "line": "Ostatné",
                "percentage": int(others_pct),
                "count": int(others_count)
            })

        return {
            "vehicle_id": out_vid,
            "period_days": days,
            "total_records": total_samples,
            "has_data": True,
            "lines": lines_res
        }


# Globálna inštancia pripravená na použitie v celej aplikácii
telemetry_db = TelemetryDB()
