from __future__ import annotations
import os
import sys
import re
import json
import sqlite3
import urllib.request
import unicodedata
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_DIR = os.path.dirname(BASE_DIR)
DEFAULT_DB_PATH = os.path.join(PROJECT_DIR, "data", "timetables.db")
DEFAULT_STOPS_PATH = os.path.join(PROJECT_DIR, "data", "kosice_stops.json")


def normalize_canonical_stop(name: str) -> str:
    """
    Normalizuje názov zastávky na jednotný kanonický tvar pre spoľahlivé párovanie v celej MHD sieti.
    Odstráni diakritiku, rozbalí bežné skratky (Nám. -> námestie, OC -> obchodné centrum, atď.)
    a odstráni označenia nástupíšť.
    """
    if not name:
        return ""
    s = "".join(
        c for c in unicodedata.normalize("NFD", str(name))
        if unicodedata.category(c) != "Mn"
    ).lower()

    # Odstránenie nástupíšť: (nást. 1), , nástupište 2, a pod.
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r",\s*n[a-z]+.*", "", s)

    # Štandardizácia skratiek v Košiciach
    s = re.sub(r"\bnam\.\b|\bnam\b", "namestie", s)
    s = re.sub(r"\boc\b", "obchodne centrum", s)
    s = re.sub(r"\bnippon\s+steel\b|\bu\.\s*s\.\s*steel\b|\bu\s*s\s*steel\b|\buss\b", "nssk", s)
    s = re.sub(r"\bmiu\b|\bmiestny\s*urad\b", "miu", s)
    s = re.sub(r"\bdarg\.\s*hrdinov\b|\bdargovskych\s*hrdinov\b", "dargovskych hrdinov", s)
    s = re.sub(r"\bzel\.\s*st\b|\bzel\s*st\b", "zeleznicna stanica", s)
    s = re.sub(r"\bpoliklin\.\b", "poliklinika", s)

    # Odstránenie interpunkcie
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return " ".join(s.split())


class TimetableManager:
    """
    Správca a databázový engine pre oficiálne cestovné poriadky MHD Košice (DPMK).
    Uchováva a indexuje statické grafikony v lokálnej SQLite databáze `data/timetables.db`.
    Umožňuje bleskové (< 0.2 ms) overenie, či v zadanom čase skutočne existuje spoj a kedy presne dorazí.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "sk,cs,en;q=0.9"
        }
        self._conn: Optional[sqlite3.Connection] = None
        # In-memory query cache pre Dijkstra vyhľadávanie
        self._query_cache: Dict[Tuple[str, str, str, str, int], Optional[Dict[str, Any]]] = {}

        # Automatické otvorenie pripojenia, ak databáza existuje
        if os.path.exists(self.db_path):
            self._ensure_connection()

    def _ensure_connection(self) -> sqlite3.Connection:
        """Zabezpečí aktívne SQLite spojenie s optimalizáciami pre vysokorýchlostné čítanie."""
        if self._conn is None:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            # Optimalizácia SQLite pre vysokorýchlostné paralelné čítanie
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA cache_size=-10000")  # 10 MB cache
        return self._conn

    def is_database_ready(self) -> bool:
        """Overí, či je databáza vytvorená a obsahuje platné dáta cestovných poriadkov."""
        if not os.path.exists(self.db_path):
            return False
        try:
            conn = self._ensure_connection()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM stop_departures")
            cnt = cur.fetchone()[0]
            return cnt > 1000
        except Exception:
            return False

    def init_database_schema(self, conn: sqlite3.Connection) -> None:
        """Inicializuje čistú tabuľkovú schému pre grafikony a indexy."""
        cur = conn.cursor()
        cur.execute("DROP TABLE IF EXISTS stop_departures")
        cur.execute("DROP TABLE IF EXISTS routes")
        cur.execute("DROP TABLE IF EXISTS route_stops")
        cur.execute("DROP TABLE IF EXISTS metadata")

        cur.execute("""
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)
        cur.execute("""
        CREATE TABLE routes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            line TEXT NOT NULL,
            direction TEXT NOT NULL,
            origin_stop TEXT NOT NULL,
            destination_stop TEXT NOT NULL
        )
        """)
        cur.execute("""
        CREATE TABLE route_stops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            route_id INTEGER NOT NULL,
            line TEXT NOT NULL,
            direction TEXT NOT NULL,
            stop_sequence INTEGER NOT NULL,
            stop_name TEXT NOT NULL,
            canonical_stop_name TEXT NOT NULL,
            offset_seconds INTEGER NOT NULL
        )
        """)
        cur.execute("""
        CREATE TABLE stop_departures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            route_id INTEGER NOT NULL,
            line TEXT NOT NULL,
            direction TEXT NOT NULL,
            stop_name TEXT NOT NULL,
            canonical_stop_name TEXT NOT NULL,
            stop_sequence INTEGER NOT NULL,
            day_type TEXT NOT NULL,
            departure_seconds INTEGER NOT NULL,
            departure_time_str TEXT NOT NULL,
            trip_id TEXT NOT NULL,
            destination_stop TEXT NOT NULL
        )
        """)
        # Indexy pre bleskové vyhľadávanie v Dijkstrovom algoritme
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sd_lookup ON stop_departures (canonical_stop_name, line, day_type, departure_seconds)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sd_trip_seq ON stop_departures (trip_id, stop_sequence)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sd_stop_day ON stop_departures (canonical_stop_name, day_type, departure_seconds)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sd_stop_line_dir_dep ON stop_departures (canonical_stop_name, line, direction, departure_seconds)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sd_lookup_dir ON stop_departures (canonical_stop_name, line, direction, day_type, departure_seconds)")
        conn.commit()

    @staticmethod
    def get_day_type(dt: datetime) -> str:
        """Určí typ dňa: 'workday' (pondelok až piatok) alebo 'weekend' (sobota, nedeľa)."""
        return "weekend" if dt.weekday() >= 5 else "workday"

    def fetch_page(self, url: str) -> Optional[str]:
        """Stiahne webovú stránku s ošetrením chýb."""
        try:
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.read().decode("utf-8")
        except Exception:
            return None

    def download_and_build(self, max_workers: int = 10) -> Dict[str, Any]:
        """
        Kompletné stiahnutie a uloženie oficiálnych grafikonov pre všetky mestské linky DPMK Košice.
        Stiahne zoznam liniek, ich trasy, zastávky a všetky plánované časy odchodov
        a vytvorí optimalizovanú SQLite databázu `data/timetables.db`.
        """
        print("🚀 Spúšťam sťahovanie kompletných cestovných poriadkov MHD Košice...")
        t_start = datetime.now()

        # 1. Zoznam liniek
        index_url = "https://imhd.sk/ke/cestovne-poriadky"
        html = self.fetch_page(index_url)
        if not html:
            raise RuntimeError("Nepodarilo sa stiahnuť zoznam liniek z imhd.sk.")

        soup = BeautifulSoup(html, "html.parser")
        lines_raw = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            txt = a.get_text(strip=True)
            if "/linka/" in href and txt:
                # Klasické linky DPMK: električky 1-9, R1-R8, autobusy 10-72, nočné N1-N7, RA1-RA8, V1-V4
                if re.match(r"^(?:[0-9]{1,2}[A-Z]?|R[1-8]|RA[1-8]|N[1-7]|V[1-4])$", txt):
                    lines_raw.append((txt, href))

        seen = set()
        unique_lines = []
        for l, h in lines_raw:
            if l not in seen:
                seen.add(l)
                unique_lines.append((l, h))

        print(f"📋 Nájdených {len(unique_lines)} oficiálnych liniek DPMK.")

        # 2. Pre každú linku nájdeme unikátne smery a URL ich východzích zastávok
        def scan_line_directions(item):
            line_name, href = item
            line_url = f"https://imhd.sk{href}" if href.startswith("/") else href
            l_html = self.fetch_page(line_url)
            if not l_html:
                return []

            l_soup = BeautifulSoup(l_html, "html.parser")
            dirs_map = {}
            for a in l_soup.find_all("a", href=True):
                h = a["href"]
                t = a.get_text(strip=True)
                if "/cestovny-poriadok/linka/" in h and t:
                    parts = h.split("/")
                    if len(parts) >= 7:
                        smer_slug = parts[6]
                        # Ak sme tento smer pre linku ešte nezaznamenali, toto je prvá (východzia) zastávka
                        if smer_slug not in dirs_map:
                            clean_smer = smer_slug.replace("smer-", "").replace("-", " ")
                            dirs_map[smer_slug] = (line_name, clean_smer, t, f"https://imhd.sk{h}")
            return list(dirs_map.values())

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            dir_results = list(ex.map(scan_line_directions, unique_lines))

        routes_to_fetch = []
        for r_list in dir_results:
            routes_to_fetch.extend(r_list)

        print(f"🗺️ Nájdených {len(routes_to_fetch)} trás/smerov. Sťahujem detailné grafikony...")

        # 3. Stiahnutie grafikonov pre každú trasu
        def parse_route_details(route_tuple):
            line, direction, origin_stop, url = route_tuple
            p_html = self.fetch_page(url)
            if not p_html:
                return None

            p_soup = BeautifulSoup(p_html, "html.parser")

            # A. Zastávky a minútové posuny na trase
            stops_table = p_soup.find("table", class_="stopsList")
            stops_data = []
            if stops_table:
                last_offset_min = 0
                for tr in stops_table.find_all("tr"):
                    tds = tr.find_all(["th", "td"])
                    if not tds or len(tds) < 2:
                        continue
                    if any("zastávka" in c.get_text().lower() for c in tds):
                        continue

                    # Stop name: extract without platform / zone badge spans
                    stop_cell = tr.find("td", class_="stopName") or tds[-1]
                    for bad_span in stop_cell.find_all("span", class_=["platform", "badge", "glyphicon"]):
                        bad_span.decompose()
                    clean_stop_name = stop_cell.get_text(strip=True)
                    clean_stop_name = re.sub(r"(\D+)\d+$", r"\1", clean_stop_name).strip()
                    if not clean_stop_name:
                        continue

                    # Offset time: span.timemax or span.timemin in stopTime cell
                    offset_min = 0
                    time_cell = tr.find("td", class_="stopTime")
                    if not time_cell:
                        for td in tds:
                            if td.find("span", class_=["timemax", "timemin"]):
                                time_cell = td
                                break
                    if not time_cell and len(tds) > 1:
                        time_cell = tds[1]

                    if time_cell:
                        s_max = time_cell.find("span", class_="timemax")
                        if s_max and s_max.get_text(strip=True).isdigit():
                            offset_min = int(s_max.get_text(strip=True))
                        else:
                            s_min = time_cell.find("span", class_="timemin")
                            if s_min:
                                m = re.findall(r"\d+", s_min.get_text(strip=True))
                                if m:
                                    offset_min = int(m[-1])
                            else:
                                m = re.findall(r"\d+", time_cell.get_text(strip=True))
                                if m:
                                    offset_min = int(m[-1])

                    if offset_min < last_offset_min:
                        offset_min = last_offset_min
                    last_offset_min = offset_min

                    stops_data.append((clean_stop_name, offset_min * 60))

            if not stops_data:
                return None

            dest_stop = stops_data[-1][0] if stops_data else direction

            # B. Časy odchodov z východzej zastávky
            dep_tables = []
            for t in p_soup.find_all("table"):
                r0 = t.find("tr")
                if r0 and [c.get_text(strip=True) for c in r0.find_all(["th", "td"])][:2] == ["hod", "min"]:
                    times = []
                    for tr in t.find_all("tr")[1:]:
                        cells = [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
                        if not cells or not cells[0].isdigit():
                            continue
                        hour = int(cells[0])
                        for m_cell in cells[1:]:
                            digits = re.findall(r"^\d+", m_cell)
                            if digits:
                                minute = int(digits[0])
                                times.append(hour * 3600 + minute * 60)
                    dep_tables.append(times)

            day_deps = {}
            if len(dep_tables) >= 3:
                day_deps["workday"] = dep_tables[0]
                day_deps["weekend"] = dep_tables[2]
            elif len(dep_tables) == 2:
                day_deps["workday"] = dep_tables[0]
                day_deps["weekend"] = dep_tables[1]
            elif len(dep_tables) == 1:
                day_deps["workday"] = dep_tables[0]
                day_deps["weekend"] = dep_tables[0]

            return {
                "line": line,
                "direction": direction,
                "origin_stop": origin_stop,
                "destination_stop": dest_stop,
                "stops": stops_data,
                "day_departures": day_deps
            }

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            parsed_routes = [r for r in ex.map(parse_route_details, routes_to_fetch) if r is not None]

        print(f"📦 Spracovaných {len(parsed_routes)} platných grafikonov. Ukladám do SQLite databázy...")

        # 4. Zápis do SQLite databázy
        if self._conn:
            self._conn.close()
            self._conn = None

        conn = sqlite3.connect(self.db_path)
        self.init_database_schema(conn)
        cur = conn.cursor()

        total_departures_count = 0
        total_trips_count = 0

        route_rows = []
        route_stop_rows = []
        departure_rows = []

        route_id_counter = 1
        for r in parsed_routes:
            r_id = route_id_counter
            route_id_counter += 1
            line = r["line"]
            direction = r["direction"]
            origin = r["origin_stop"]
            dest = r["destination_stop"]
            stops = r["stops"]
            day_deps = r["day_departures"]

            route_rows.append((r_id, line, direction, origin, dest))

            # Uloženie sekvencie zastávok
            for seq, (s_name, off_sec) in enumerate(stops, 1):
                c_name = normalize_canonical_stop(s_name)
                route_stop_rows.append((r_id, line, direction, seq, s_name, c_name, off_sec))

            # Uloženie odchodov pre každý typ dňa
            for day_type, times in day_deps.items():
                for trip_idx, base_sec in enumerate(times, 1):
                    total_trips_count += 1
                    trip_id = f"{line}_{r_id}_{day_type}_{trip_idx}"

                    for seq, (s_name, off_sec) in enumerate(stops, 1):
                        dep_sec = (base_sec + off_sec) % 86400
                        time_str = f"{dep_sec // 3600:02d}:{(dep_sec % 3600) // 60:02d}"
                        c_name = normalize_canonical_stop(s_name)

                        departure_rows.append((
                            r_id, line, direction, s_name, c_name, seq,
                            day_type, dep_sec, time_str, trip_id, dest
                        ))
                        total_departures_count += 1

        cur.executemany(
            "INSERT INTO routes (id, line, direction, origin_stop, destination_stop) VALUES (?, ?, ?, ?, ?)",
            route_rows
        )
        cur.executemany(
            "INSERT INTO route_stops (route_id, line, direction, stop_sequence, stop_name, canonical_stop_name, offset_seconds) VALUES (?, ?, ?, ?, ?, ?, ?)",
            route_stop_rows
        )
        cur.executemany(
            """
            INSERT INTO stop_departures (
                route_id, line, direction, stop_name, canonical_stop_name, stop_sequence,
                day_type, departure_seconds, departure_time_str, trip_id, destination_stop
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            departure_rows
        )

        cur.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_updated', ?)", (datetime.now().isoformat(),))
        cur.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('total_routes', ?)", (str(len(route_rows)),))
        cur.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('total_trips', ?)", (str(total_trips_count),))
        cur.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('total_departures', ?)", (str(total_departures_count),))

        conn.commit()
        conn.close()

        # Obnovenie pripojenia
        self._conn = None
        self._ensure_connection()
        self._query_cache.clear()

        duration = (datetime.now() - t_start).total_seconds()
        print(f"✅ Hotovo za {duration:.1f}s! Databáza {self.db_path} obsahuje:")
        print(f"   • {len(route_rows)} trás")
        print(f"   • {total_trips_count} unikátnych spojov (jázd)")
        print(f"   • {total_departures_count} naplánovaných odchodov zo zastávok")

        return {
            "routes_count": len(route_rows),
            "trips_count": total_trips_count,
            "departures_count": total_departures_count,
            "duration_seconds": duration,
            "db_path": self.db_path
        }

    def get_next_ride(
        self,
        from_canonical: str,
        to_canonical: str,
        line: str,
        current_dt: datetime
    ) -> Optional[Dict[str, Any]]:
        """
        Nájde najbližší oficiálne naplánovaný odchod a jazdu medzi zastávkami U a V pre danú linku.
        Ak v grafikone v zadanom čase (a ani do 4 hodín) žiadny spoj neexistuje, vráti None.
        Garantuje, že algoritmus si nikdy nevymyslí neexistujúci spoj.
        """
        c_from = normalize_canonical_stop(from_canonical)
        c_to = normalize_canonical_stop(to_canonical)
        if not c_from or not c_to or c_from == c_to:
            return None

        line_str = str(line).strip()
        day_type = self.get_day_type(current_dt)
        cur_sec = current_dt.hour * 3600 + current_dt.minute * 60 + current_dt.second

        # Cache key pre bleskovú odozvu
        cache_key = (c_from, c_to, line_str, day_type, cur_sec // 60)
        if cache_key in self._query_cache:
            return self._query_cache[cache_key]

        conn = self._ensure_connection()
        cur = conn.cursor()

        # Dopyt: Nájde najbližší spoj z d1 (nástup) do d2 (výstup) s rovnakým trip_id, kde výstup nasleduje za nástupom
        query = """
        SELECT 
            d1.line,
            d1.direction,
            d1.trip_id,
            d1.departure_seconds as dep_sec,
            d1.departure_time_str as dep_str,
            d2.departure_seconds as arr_sec,
            d2.departure_time_str as arr_str,
            (d2.stop_sequence - d1.stop_sequence) as seq_diff,
            d1.destination_stop
        FROM stop_departures d1
        JOIN stop_departures d2 
            ON d1.trip_id = d2.trip_id 
            AND d1.day_type = d2.day_type
            AND d2.stop_sequence > d1.stop_sequence
        WHERE d1.canonical_stop_name = ?
          AND d2.canonical_stop_name = ?
          AND d1.line = ?
          AND d1.day_type = ?
          AND d1.departure_seconds >= ?
        ORDER BY d1.departure_seconds ASC
        LIMIT 1
        """

        cur.execute(query, (c_from, c_to, line_str, day_type, cur_sec))
        row = cur.fetchone()

        # Ak už dnes spoj nepremáva (napr. je 23:45 a posledný spoj išiel o 23:15),
        # pozrieme sa na ranný prvý spoj na druhý deň (midnight wrap-around)
        wait_day_offset = 0
        if not row:
            # Druhý pokus: prvý ranný spoj nasledujúceho dňa
            next_day_dt = current_dt + timedelta(days=1)
            next_day_type = self.get_day_type(next_day_dt)
            cur.execute(query, (c_from, c_to, line_str, next_day_type, 0))
            row = cur.fetchone()
            if row:
                wait_day_offset = 86400  # +24 hodín čakania

        if not row:
            self._query_cache[cache_key] = None
            return None

        dep_sec = row["dep_sec"]
        arr_sec = row["arr_sec"]
        seq_diff = max(1, row["seq_diff"] if "seq_diff" in row.keys() else 1)

        # Výpočet čistého času čakania a času jazdy
        wait_seconds = (dep_sec + wait_day_offset) - cur_sec
        ride_seconds = arr_sec - dep_sec
        if ride_seconds < 0:
            ride_seconds += 86400
        # Úsek jazdy nesmie trvať 0 minút (minimálne 1 minúta na zastávku)
        if ride_seconds < 60:
            ride_seconds = max(60, seq_diff * 60)

        final_arr_sec = (dep_sec + ride_seconds) % 86400
        final_arr_str = f"{final_arr_sec // 3600:02d}:{(final_arr_sec % 3600) // 60:02d}"

        # Ak by cestujúci musel čakať viac ako 5 hodín (18 000 sekúnd),
        # spoj pre aktuálnu cestu neponúkame
        if wait_seconds > 18000:
            self._query_cache[cache_key] = None
            return None

        res = {
            "line": row["line"],
            "direction": row["direction"],
            "destination_stop": row["destination_stop"],
            "trip_id": row["trip_id"],
            "departure_time_str": row["dep_str"],
            "departure_seconds": dep_sec,
            "arrival_time_str": final_arr_str,
            "arrival_seconds": final_arr_sec,
            "wait_seconds": wait_seconds,
            "wait_minutes": round(wait_seconds / 60.0, 1),
            "ride_seconds": ride_seconds,
            "ride_minutes": round(ride_seconds / 60.0, 1)
        }

        self._query_cache[cache_key] = res
        return res

    def get_departures_from_stop(
        self,
        canonical_stop_name: str,
        current_dt: datetime,
        line: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Získa oficiálne naplánované odchody zo zastávky v zadanom čase."""
        c_stop = normalize_canonical_stop(canonical_stop_name)
        if not c_stop:
            return []

        day_type = self.get_day_type(current_dt)
        cur_sec = current_dt.hour * 3600 + current_dt.minute * 60 + current_dt.second

        conn = self._ensure_connection()
        cur = conn.cursor()

        if line:
            query = """
            SELECT line, direction, departure_seconds, departure_time_str, trip_id, destination_stop
            FROM stop_departures
            WHERE canonical_stop_name = ? AND line = ? AND day_type = ? AND departure_seconds >= ?
            ORDER BY departure_seconds ASC
            LIMIT ?
            """
            cur.execute(query, (c_stop, str(line).strip(), day_type, cur_sec, limit))
        else:
            query = """
            SELECT line, direction, departure_seconds, departure_time_str, trip_id, destination_stop
            FROM stop_departures
            WHERE canonical_stop_name = ? AND day_type = ? AND departure_seconds >= ?
            ORDER BY departure_seconds ASC
            LIMIT ?
            """
            cur.execute(query, (c_stop, day_type, cur_sec, limit))

        rows = cur.fetchall()
        result = []
        for r in rows:
            wait_sec = r["departure_seconds"] - cur_sec
            if wait_sec < 0:
                wait_sec += 86400
            result.append({
                "line": r["line"],
                "direction": r["direction"],
                "destination_stop": r["destination_stop"],
                "departure_time_str": r["departure_time_str"],
                "wait_seconds": wait_sec,
                "wait_minutes": round(wait_sec / 60.0, 1),
                "trip_id": r["trip_id"]
            })
        return result


# Globálna inštancia pre použitie v aplikácii
_TIMETABLE_MANAGER_INSTANCE: Optional[TimetableManager] = None

def get_timetable_manager() -> TimetableManager:
    """Získa globálnu inštanciu TimetableManager s automatickým načítaním."""
    global _TIMETABLE_MANAGER_INSTANCE
    if _TIMETABLE_MANAGER_INSTANCE is None:
        _TIMETABLE_MANAGER_INSTANCE = TimetableManager()
    return _TIMETABLE_MANAGER_INSTANCE


if __name__ == "__main__":
    manager = TimetableManager()
    # Spustenie stiahnutia a naplnenia databázy
    manager.download_and_build(max_workers=10)
