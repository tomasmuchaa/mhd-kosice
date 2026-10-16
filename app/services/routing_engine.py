from __future__ import annotations
import os
import sys
import json
import math
import heapq
import unicodedata
import urllib.request
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple, Union, Set
from app.services.timetable_manager import get_timetable_manager, TimetableManager, normalize_canonical_stop

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_DIR = os.path.dirname(BASE_DIR)
DEFAULT_STOPS_PATH = os.path.join(PROJECT_DIR, "data", "kosice_stops.json")
DEFAULT_TRANSFERS_PATH = os.path.join(PROJECT_DIR, "data", "walking_transfers.json")


def strip_accents(text: str) -> str:
    """Odstráni diakritiku z textu pre spoľahlivé párovanie názvov zastávok."""
    if not text:
        return ""
    return "".join(
        c for c in unicodedata.normalize("NFD", str(text))
        if unicodedata.category(c) != "Mn"
    )


class RoutingEngine:
    """
    Smerovací a plánovací modul pre MHD Košice (Journey Planner).
    Spravuje sieť zastávok a buduje graf peších prestupov (Walking Graph)
    pre inteligentné prestupy medzi linkami a nástupišťami.
    Implementuje multimodálny Dijkstrov algoritmus kombinujúci pešie presuny a jazdy MHD
    s dynamickými meškaniami a odchodovými časmi.
    """

    def __init__(
        self,
        stops_path: Optional[str] = None,
        walking_speed_kmh: float = 5.0,
        max_transfer_distance_m: float = 500.0,
        live_feed: Optional[Any] = None,
        fleet_service: Optional[Any] = None
    ):
        self.stops_path = stops_path or DEFAULT_STOPS_PATH
        self.walking_speed_kmh = walking_speed_kmh
        # 5.0 km/h = 5000 m / 3600 s = 1.388889 m/s (1 km trvá presne 12 minút)
        self.walking_speed_ms = (walking_speed_kmh * 1000.0) / 3600.0
        self.max_transfer_distance_m = max_transfer_distance_m
        self.live_feed = live_feed
        self.fleet_service = fleet_service
        self.timetable_manager = get_timetable_manager()

        self.stops: List[Dict[str, Any]] = []
        self.stops_by_id: Dict[Any, Dict[str, Any]] = {}
        self.stops_by_name: Dict[str, List[Dict[str, Any]]] = {}
        self.stops_by_canonical_name: Dict[str, List[Dict[str, Any]]] = {}
        self.stops_by_norm_canonical: Dict[str, List[Dict[str, Any]]] = {}
        self.lines_to_stops: Dict[str, List[Any]] = {}

        self.walking_graph: Optional[Dict[str, Any]] = None
        self.adjacency_list: Dict[Any, List[Dict[str, Any]]] = {}

        # Vyrovnávacia pamäť pre reálnu geometriu ciest (shape polyline) a detaily jázd
        self._trip_details_cache: Dict[int, Dict[str, Any]] = {}
        self._route_geometry_cache: Dict[Any, Tuple[List[List[float]], List[str]]] = {}
        self._osrm_cache: Dict[str, List[List[float]]] = {}
        self._stop_departures_cache: Dict[Any, List[Dict[str, Any]]] = {}
        self._trip_downstream_cache: Dict[Tuple[str, int], List[Dict[str, Any]]] = {}
        self._routing_transit_cache: Dict[Tuple[str, str, str, int, bool], List[Dict[str, Any]]] = {}

        self.load_stops()
        try:
            self.load_walking_graph()
        except Exception:
            pass

    @staticmethod
    def is_mhd_line(line: Any) -> bool:
        """
        Filtruje výlučne klasické mestské linky MHD Košice (DPMK).
        Prísne vyraďuje prímestské a regionálne autobusy (Eurobus, Arriva, SAD s dlhými číslami ako 802422, 102516 a pod.)
        a vlakové spojenia (Os, REX, Ex, R, EN, RJ, SC...).

        Klasické MHD linky DPMK v Košiciach:
        - Električky: 1 - 9, R1 - R8
        - Denné autobusy: 10 - 72 (aj s písmenom ako 20L, 26P)
        - Nočné linky: N1 - N7
        - Zmenové spoje U. S. Steel: RA1 - RA8
        - Školské a mimoriadne linky: Š1 - Š3, S1 - S3, X, X1 - X9, H, A
        """
        if line is None:
            return False
        l = str(line).strip().upper()
        if not l:
            return False

        # 1. Vyradenie vlakov (Os, REX, Ex, R, EN, RJ, SC...)
        if any(l.startswith(p) for p in ("OS ", "REX ", "EX ", "EN ", "RJ ", "SC ", "R ")):
            return False

        # 2. Rýdzo číselné linky: v MHD Košice sú čísla liniek od 1 do 99 (1-9 električky, 10-72 autobusy).
        # Linky s 3 a viac ciframi (napr. 866, 902, 1262, 802401, 802422) sú regionálne Eurobusy!
        if l.isdigit():
            val = int(l)
            return 1 <= val <= 99

        # 3. Číslo s jednopísmenovým variantom (napr. 20L, 26P)
        m = re.match(r"^(\d{1,2})([A-Z])$", l)
        if m:
            val = int(m.group(1))
            return 1 <= val <= 99

        # 4. Oficiálne písmenové linky DPMK:
        # - R1 až R8 (rýchlodráha U. S. Steel)
        # - RA1 až RA8 (zmenové autobusy U. S. Steel)
        # - N1 až N7 (nočné autobusy - prímestské majú dlhé čísla ako N1253, N866)
        # - Š1 až Š3, S1 až S3 (školské spoje)
        # - X, X1 až X9 (náhradná doprava)
        # - H, A (historické/mimoriadne)
        if re.match(r"^(?:R[1-8]|RA[1-8]|N[1-7]|[ŠS][1-3]|X\d?|[HA]\d?)$", l):
            return True

        return False

    @staticmethod
    def get_canonical_name(stop_or_name: Any) -> str:
        """
        Získa čistý kanonický názov zastávky bez prívlastkov nástupíšť (napr. ' (Nást. 3)').
        Umožňuje zlúčiť všetky fyzické stĺpiky s rovnakým názvom do jedného logického super-uzla.
        """
        if isinstance(stop_or_name, dict):
            base = stop_or_name.get("base_name")
            if base and str(base).strip():
                name = str(base).strip()
            else:
                name = str(stop_or_name.get("name") or "").strip()
        else:
            name = str(stop_or_name or "").strip()

        cleaned = re.sub(
            r"\s*\((?:Nást\.|Nástupište|Stanovište|Nást|Platforma|Stĺpik)\s*[^)]*\)",
            "",
            name,
            flags=re.IGNORECASE
        )
        cleaned = re.sub(r",\s*(?:Nást\.|Nástupište|Stanovište|Nást|Platforma|Stĺpik)[^,]*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned or name

    def resolve_stop(self, identifier: Any) -> Optional[Dict[str, Any]]:
        """
        Vyhľadá zastávku podľa stop_id (int/str), parent_stop_id, kanonického názvu alebo reťazca.
        Podporuje zhodu bez diakritiky a flexibilnú normalizáciu medzier a interpunkcie.
        """
        if identifier is None:
            return None
        # 1. Priame vyhľadanie v stops_by_id
        if identifier in self.stops_by_id:
            return self.stops_by_id[identifier]
        s_id = str(identifier).strip()
        if s_id in self.stops_by_id:
            return self.stops_by_id[s_id]

        # 2. Skúška čísla alebo bázy pred podtržníkom (napr. 1000000064_3 -> 1000000064)
        base = s_id.split("_")[0]
        if base in self.stops_by_id:
            return self.stops_by_id[base]
        try:
            int_b = int(base)
            if int_b in self.stops_by_id:
                return self.stops_by_id[int_b]
            if str(int_b) in self.stops_by_id:
                return self.stops_by_id[str(int_b)]
        except ValueError:
            pass

        # 3. Kanonický názov zastávky
        cname = self.get_canonical_name(s_id)
        if cname in self.stops_by_canonical_name:
            return self.stops_by_canonical_name[cname][0]

        norm_canon = normalize_canonical_stop(cname)
        if norm_canon in self.stops_by_norm_canonical:
            return self.stops_by_norm_canonical[norm_canon][0]

        # 4. Zhoda bez diakritiky a interpunkcie s tokenizáciou
        def clean_search_str(txt: str) -> str:
            t = strip_accents(txt.lower())
            t = re.sub(r"[,.\-/]", " ", t)
            return " ".join(t.split())

        norm_q = clean_search_str(cname)
        q_tokens = norm_q.split()

        for cn, stops in self.stops_by_canonical_name.items():
            if clean_search_str(cn) == norm_q:
                return stops[0]

        for cn, stops in self.stops_by_canonical_name.items():
            norm_cn = clean_search_str(cn)
            if norm_q in norm_cn or (q_tokens and all(tok in norm_cn for tok in q_tokens)):
                return stops[0]

        for s in self.stops:
            s_name = clean_search_str(s.get("name") or "")
            if norm_q in s_name or (q_tokens and all(tok in s_name for tok in q_tokens)):
                return s

        return None

    def load_stops(self) -> None:
        """Načíta existujúce zastávky z kosice_stops.json a indexuje super-uzly a linky."""
        if not os.path.exists(self.stops_path):
            raise FileNotFoundError(f"Súbor so zastávkami nebol nájdený: {self.stops_path}")

        with open(self.stops_path, "r", encoding="utf-8") as f:
            raw_stops = json.load(f)

        # Filtrovanie zastávok s platnými GPS súradnicami
        self.stops = [
            s for s in raw_stops
            if s.get("latitude") is not None and s.get("longitude") is not None
        ]

        self.stops_by_id = {}
        for s in self.stops:
            sid = s["stop_id"]
            self.stops_by_id[sid] = s
            self.stops_by_id[str(sid)] = s
            for p_id in s.get("platforms_included", []):
                if p_id not in self.stops_by_id:
                    self.stops_by_id[p_id] = s
                if str(p_id) not in self.stops_by_id:
                    self.stops_by_id[str(p_id)] = s
            parent_id = s.get("parent_stop_id")
            if parent_id is not None:
                if parent_id not in self.stops_by_id:
                    self.stops_by_id[parent_id] = s
                if str(parent_id) not in self.stops_by_id:
                    self.stops_by_id[str(parent_id)] = s

        self.stops_by_name = {}
        self.stops_by_canonical_name = {}
        self.stops_by_norm_canonical = {}
        self.lines_to_stops = {}

        for s in self.stops:
            raw_name = s.get("name", "")
            self.stops_by_name.setdefault(raw_name, []).append(s)
            cname = self.get_canonical_name(s)
            self.stops_by_canonical_name.setdefault(cname, []).append(s)
            norm_cname = normalize_canonical_stop(cname)
            self.stops_by_norm_canonical.setdefault(norm_cname, []).append(s)
            s["canonical_norm"] = norm_cname

            # Prísny filter: pre plánovanie trás zaradíme výhradne linky mestskej dopravy DPMK (odstraňujeme Eurobusy a vlaky)
            clean_lines = [l for l in s.get("lines", []) if self.is_mhd_line(l)]
            s["lines"] = clean_lines
            for line in clean_lines:
                self.lines_to_stops.setdefault(str(line), []).append(s["stop_id"])

    @staticmethod
    def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Vypočíta vzdušnú vzdialenosť medzi dvoma GPS bodmi v metroch
        pomocou štandardného Haversine vzorca.
        """
        R = 6371000.0  # Polomer Zeme v metroch
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = (
            math.sin(delta_phi / 2.0) ** 2
            + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
        )
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return R * c

    def calculate_walking_time(self, distance_meters: float) -> Tuple[int, float]:
        """
        Vypočíta čas pešieho presunu na základe vzdialenosti.
        Pri rýchlosti 5 km/h: 1 meter = 0.72 sekundy (1 000 m = 720 s = 12 min).
        Vráti (sekundy, minúty).
        """
        seconds = int(round(distance_meters / self.walking_speed_ms))
        minutes = round(seconds / 60.0, 1)
        return seconds, minutes

    def build_walking_graph(
        self,
        max_distance_m: Optional[float] = None,
        save_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Vypočíta vzdušné vzdialenosti medzi všetkými zastávkami navzájom (každá s každou).
        Pre každú dvojicu so vzdialenosťou < max_distance_m vytvorí pešiu hranu.
        Výsledok uloží do JSON súboru.
        """
        max_dist = max_distance_m if max_distance_m is not None else self.max_transfer_distance_m
        target_file = save_path or DEFAULT_TRANSFERS_PATH

        transfers: List[Dict[str, Any]] = []
        adjacency: Dict[int, List[Dict[str, Any]]] = {}

        n_stops = len(self.stops)

        # Výpočet vzdialeností každá s každou
        for i in range(n_stops):
            s1 = self.stops[i]
            id1 = s1["stop_id"]
            lat1, lon1 = s1["latitude"], s1["longitude"]
            name1 = s1.get("name", f"Zastávka #{id1}")

            if id1 not in adjacency:
                adjacency[id1] = []

            for j in range(n_stops):
                if i == j:
                    continue  # Pešia hrana do tej istej zastávky sa nevytvára

                s2 = self.stops[j]
                id2 = s2["stop_id"]
                lat2, lon2 = s2["latitude"], s2["longitude"]
                name2 = s2.get("name", f"Zastávka #{id2}")

                dist_m = self.haversine_distance(lat1, lon1, lat2, lon2)

                if dist_m < max_dist:
                    walk_sec, walk_min = self.calculate_walking_time(dist_m)

                    transfer_edge = {
                        "from_stop_id": id1,
                        "from_stop_name": name1,
                        "to_stop_id": id2,
                        "to_stop_name": name2,
                        "distance_meters": round(dist_m, 1),
                        "walk_time_seconds": walk_sec,
                        "walk_time_minutes": walk_min,
                        "from_coords": [lat1, lon1],
                        "to_coords": [lat2, lon2]
                    }

                    transfers.append(transfer_edge)
                    adjacency[id1].append({
                        "to_stop_id": id2,
                        "to_stop_name": name2,
                        "distance_meters": round(dist_m, 1),
                        "walk_time_seconds": walk_sec,
                        "walk_time_minutes": walk_min,
                        "to_coords": [lat2, lon2],
                        "from_coords": [lat1, lon1]
                    })

        # Zotriedenie hrán pre každú zastávku podľa vzdialenosti (od najbližšej)
        for stop_id in adjacency:
            adjacency[stop_id].sort(key=lambda x: x["distance_meters"])

        # Prehľadné štatistiky
        distances = [t["distance_meters"] for t in transfers]
        avg_dist = round(sum(distances) / len(distances), 1) if distances else 0.0
        min_dist = min(distances) if distances else 0.0
        max_found_dist = max(distances) if distances else 0.0

        graph_result = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "total_stops_analyzed": n_stops,
                "total_transfers_directed": len(transfers),
                "total_stop_pairs_undirected": len(transfers) // 2,
                "max_threshold_distance_meters": max_dist,
                "walking_speed_kmh": self.walking_speed_kmh,
                "walking_speed_pace": "12.0 min / km (5.0 km/h)",
                "distance_stats_meters": {
                    "min": min_dist,
                    "avg": avg_dist,
                    "max": max_found_dist
                }
            },
            "transfers": transfers,
            "adjacency_list": {str(k): v for k, v in adjacency.items()}
        }

        # Uloženie do JSON súboru
        os.makedirs(os.path.dirname(target_file), exist_ok=True)
        with open(target_file, "w", encoding="utf-8") as f:
            json.dump(graph_result, f, ensure_ascii=False, indent=2)

        self.walking_graph = graph_result
        self.adjacency_list = {}
        for k, v in adjacency.items():
            self.adjacency_list[k] = v
            self.adjacency_list[str(k)] = v
        self._inject_zero_cost_platform_edges()

        return graph_result

    def _inject_zero_cost_platform_edges(self):
        """Vygeneruje bezplatné nulové prestupy (0 m, 0 s) medzi nástupišťami s rovnakým kanonickým názvom, ak sú fyzicky blízko (<= 250 m)."""
        for cname, platforms in self.stops_by_canonical_name.items():
            if len(platforms) > 1:
                for p1 in platforms:
                    id1 = p1["stop_id"]
                    id1_str = str(id1)
                    if id1 not in self.adjacency_list:
                        self.adjacency_list[id1] = []
                    if id1_str not in self.adjacency_list:
                        self.adjacency_list[id1_str] = self.adjacency_list[id1]

                    existing_targets = {edge.get("to_stop_id") for edge in self.adjacency_list[id1]}
                    lat1 = p1.get("latitude")
                    lon1 = p1.get("longitude")
                    if lat1 is None or lon1 is None:
                        continue

                    for p2 in platforms:
                        id2 = p2["stop_id"]
                        lat2 = p2.get("latitude")
                        lon2 = p2.get("longitude")
                        if lat2 is None or lon2 is None:
                            continue

                        if id1 != id2 and id2 not in existing_targets:
                            dist_m = self.haversine_distance(float(lat1), float(lon1), float(lat2), float(lon2))
                            if dist_m <= 250.0:
                                zero_edge = {
                                    "to_stop_id": id2,
                                    "to_stop_name": p2.get("name"),
                                    "distance_meters": round(dist_m, 1),
                                    "walk_time_seconds": 0,
                                    "walk_time_minutes": 0.0,
                                    "from_coords": [float(lat1), float(lon1)],
                                    "to_coords": [float(lat2), float(lon2)],
                                    "is_platform_transfer": True
                                }
                                self.adjacency_list[id1].append(zero_edge)
                                existing_targets.add(id2)

    def load_walking_graph(self, file_path: Optional[str] = None) -> Dict[str, Any]:
        """Načíta už vygenerovanú sieť peších prestupov zo súboru a pridá nulové hrany medzi nástupištia."""
        target_file = file_path or DEFAULT_TRANSFERS_PATH
        if not os.path.exists(target_file):
            return self.build_walking_graph(save_path=target_file)

        with open(target_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.walking_graph = data
        self.adjacency_list = {}
        for k, v in data.get("adjacency_list", {}).items():
            self.adjacency_list[k] = v
            try:
                self.adjacency_list[int(k)] = v
            except ValueError:
                pass
        self._inject_zero_cost_platform_edges()
        return data

    def get_transfers_from_stop(self, stop_id: int) -> List[Dict[str, Any]]:
        """Vráti všetky dostupné pešie prestupy z danej zastávky."""
        if not self.adjacency_list:
            self.load_walking_graph()
        items = self.adjacency_list.get(stop_id, [])
        # Obohatenie o súradnice, ak by v staršom JSON chýbali
        from_stop = self.stops_by_id.get(stop_id, {})
        from_c = [from_stop.get("latitude"), from_stop.get("longitude")] if from_stop else None

        for item in items:
            if "from_coords" not in item and from_c:
                item["from_coords"] = from_c
            if "to_coords" not in item:
                target_stop = self.stops_by_id.get(item.get("to_stop_id"), {})
                if target_stop and target_stop.get("latitude"):
                    item["to_coords"] = [target_stop["latitude"], target_stop["longitude"]]
        return items

    def find_nearest_stops(
        self,
        latitude: float,
        longitude: float,
        limit: int = 5,
        max_distance_m: float = 800.0
    ) -> List[Dict[str, Any]]:
        """Nájde najbližšie zastávky k ľubovoľným GPS súradniciam (užitočné pre štart/cieľ cesty)."""
        nearby = []
        for s in self.stops:
            dist = self.haversine_distance(latitude, longitude, s["latitude"], s["longitude"])
            if dist <= max_distance_m:
                sec, mins = self.calculate_walking_time(dist)
                nearby.append({
                    "stop_id": s["stop_id"],
                    "name": s.get("name"),
                    "distance_meters": round(dist, 1),
                    "walk_time_seconds": sec,
                    "walk_time_minutes": mins,
                    "latitude": s["latitude"],
                    "longitude": s["longitude"],
                    "lines": s.get("lines", [])
                })

        nearby.sort(key=lambda x: x["distance_meters"])
        return nearby[:limit]

    def clear_geometry_caches(self) -> None:
        """Vymaže vyrovnávaciu pamäť geometrií trás a OSRM dopytov."""
        self._route_geometry_cache.clear()
        self._osrm_cache.clear()

    @staticmethod
    def _calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
        """Vypočíta kompasový azimut (0-359 stupňov) z bodu 1 do bodu 2."""
        phi1, lam1 = math.radians(lat1), math.radians(lon1)
        phi2, lam2 = math.radians(lat2), math.radians(lon2)
        dlam = lam2 - lam1
        x = math.sin(dlam) * math.cos(phi2)
        y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlam)
        return int(round((math.degrees(math.atan2(x, y)) + 360.0) % 360.0)) % 360

    def _slice_polyline_between_endpoints(
        self,
        coords: List[List[float]],
        u_pt: List[float],
        v_pt: List[float]
    ) -> List[List[float]]:
        """
        Pravidlo 2 (TVRDÉ OREZANIE KRIVKY / Polyline Slicing):
        Nájde na krivke index bodu (start_idx) najbližšie k nástupnej zastávke u_pt
        a index bodu (end_idx) najbližšie k výstupnej zastávke v_pt.
        Ak start_idx < end_idx, vyreže striktne len podúsek coords[start_idx : end_idx + 1].
        """
        if not coords or len(coords) < 2:
            return []

        start_idx = min(
            range(len(coords)),
            key=lambda i: self.haversine_distance(coords[i][0], coords[i][1], u_pt[0], u_pt[1])
        )
        end_idx = min(
            range(len(coords)),
            key=lambda i: self.haversine_distance(coords[i][0], coords[i][1], v_pt[0], v_pt[1])
        )

        # Ak by kvôli slučke bol najbližší bod cieľa pred štartom, hľadáme end_idx striktne za start_idx
        if start_idx >= end_idx and start_idx < len(coords) - 1:
            end_idx_after = min(
                range(start_idx + 1, len(coords)),
                key=lambda i: self.haversine_distance(coords[i][0], coords[i][1], v_pt[0], v_pt[1])
            )
            if self.haversine_distance(coords[end_idx_after][0], coords[end_idx_after][1], v_pt[0], v_pt[1]) <= 220.0:
                end_idx = end_idx_after

        if start_idx >= end_idx:
            return []

        start_dist = self.haversine_distance(coords[start_idx][0], coords[start_idx][1], u_pt[0], u_pt[1])
        end_dist = self.haversine_distance(coords[end_idx][0], coords[end_idx][1], v_pt[0], v_pt[1])
        if start_dist > 220.0 or end_dist > 220.0:
            return []

        sliced = [list(pt) for pt in coords[start_idx : end_idx + 1]]

        # Presné ukotvenie prvého a posledného bodu na súradnice smerového stĺpika (ak je v tesnej blízkosti <= 80 m)
        d0 = self.haversine_distance(sliced[0][0], sliced[0][1], u_pt[0], u_pt[1])
        if d0 <= 2.0:
            sliced[0] = [float(u_pt[0]), float(u_pt[1])]
        elif d0 <= 80.0:
            sliced.insert(0, [float(u_pt[0]), float(u_pt[1])])

        d1 = self.haversine_distance(sliced[-1][0], sliced[-1][1], v_pt[0], v_pt[1])
        if d1 <= 2.0:
            sliced[-1] = [float(v_pt[0]), float(v_pt[1])]
        elif d1 <= 80.0:
            sliced.append([float(v_pt[0]), float(v_pt[1])])

        return sliced

    def _has_geometry_jump(self, coords: List[List[float]], max_step_meters: float = 250.0) -> bool:
        """
        Pravidlo 3 (DETEKCIA TRHLÍN A SKOKOV / Jump Guard):
        Skontroluje vzdialenosť medzi všetkými po sebe idúcimi bodmi [i] a [i+1].
        Ak je medzi ktorýmikoľvek dvoma susednými bodmi medzera > 250 m, vráti True.
        """
        if not coords or len(coords) < 2:
            return True
        for i in range(len(coords) - 1):
            d = self.haversine_distance(
                coords[i][0], coords[i][1],
                coords[i + 1][0], coords[i + 1][1]
            )
            if d > max_step_meters:
                return True
        return False

    def select_directional_platform(
        self,
        line: str,
        norm_canonical: str,
        prev_pt: Optional[Tuple[float, float]],
        next_pt: Optional[Tuple[float, float]],
        fallback_stop: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Pravidlo 1 (Správny smerový stĺpik zastávky):
        Vyberie zo super-uzla presne ten fyzický stĺpik (nástupište), ktorý obsluhuje linku `line`
        a leží na správnej (pravej) strane vozovky v smere jazdy z `prev_pt` do `next_pt`.
        """
        candidates = self.stops_by_norm_canonical.get(norm_canonical, [])
        if not candidates and fallback_stop:
            cname = self.get_canonical_name(fallback_stop)
            candidates = self.stops_by_canonical_name.get(cname, [fallback_stop])
        if not candidates:
            return fallback_stop

        line_str = str(line).strip()
        line_cands = [c for c in candidates if line_str in [str(x).strip() for x in c.get("lines", [])]]
        pool = line_cands if line_cands else candidates

        if len(pool) == 1:
            return pool[0]

        p_from = prev_pt
        p_to = next_pt
        if p_from is None and p_to is None:
            return pool[0]

        # Ťažisko kandidátnych stĺpikov v danom uzle
        c_lat = sum(float(c["latitude"]) for c in pool) / len(pool)
        c_lon = sum(float(c["longitude"]) for c in pool) / len(pool)

        if p_from is None:
            p_from = (c_lat, c_lon)
        if p_to is None:
            p_to = (c_lat, c_lon)

        # Smerový vektor jazdy v lokálnych metrických súradniciach (x = Východ, y = Sever)
        dx = (float(p_to[1]) - float(p_from[1])) * 73400.0
        dy = (float(p_to[0]) - float(p_from[0])) * 111320.0
        mag = math.hypot(dx, dy)
        if mag < 1.0:
            return pool[0]

        tx, ty = dx / mag, dy / mag
        # Pravostranná normála v smere jazdy: n_right = (ty, -tx)
        nx, ny = ty, -tx

        best_cand = pool[0]
        best_score = -float("inf")
        for cand in pool:
            px = (float(cand["longitude"]) - c_lon) * 73400.0
            py = (float(cand["latitude"]) - c_lat) * 111320.0
            right_proj = px * nx + py * ny
            fwd_proj = px * tx + py * ty
            score = right_proj + 0.35 * fwd_proj
            if score > best_score:
                best_score = score
                best_cand = cand

        return best_cand

    def get_ordered_subpath_stops(
        self,
        line: str,
        u_stop: Dict[str, Any],
        v_stop: Dict[str, Any],
        trip_id: Optional[Any] = None,
        sub_path_canonical: Optional[List[str]] = None,
        intermediate_stops: Optional[List[str]] = None
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Pravidlo 1 (PRESNÝ ZOZNAM ZASTÁVOK ÚSEKU / Sub-path):
        Vráti (ordered_directional_stops, intermediate_stop_names) striktne len medzi nástupnou (u_stop)
        a výstupnou (v_stop) zastávkou v presnom poradí jazdy spoja, pričom pre každú zastávku vyberie
        smerovo správny fyzický stĺpik.
        """
        line_str = str(line).strip()
        u_norm = normalize_canonical_stop(self.get_canonical_name(u_stop))
        v_norm = normalize_canonical_stop(self.get_canonical_name(v_stop))

        ordered_norms: List[str] = []
        ordered_names: List[str] = []

        # 1. Ak už máme presný zoznam kanonických zastávok úseku priamo z Dijkstru (pre dané trip_id)
        if sub_path_canonical and len(sub_path_canonical) >= 2:
            for cn in sub_path_canonical:
                if not ordered_norms or ordered_norms[-1] != cn:
                    ordered_norms.append(cn)
            if intermediate_stops is not None:
                ordered_names = list(intermediate_stops)

        # 2. Dopyt do timetables.db podľa trip_id alebo route_stops pre danú linku a smer (u_seq < v_seq)
        if len(ordered_norms) < 2 and hasattr(self, "timetable_manager") and self.timetable_manager:
            try:
                conn = self.timetable_manager._ensure_connection()
                cur = conn.cursor()

                if trip_id:
                    cur.execute(
                        "SELECT stop_sequence, canonical_stop_name, stop_name FROM stop_departures WHERE trip_id = ? ORDER BY stop_sequence ASC",
                        (str(trip_id),)
                    )
                    t_rows = cur.fetchall()
                    u_seq_idx = next((idx for idx, r in enumerate(t_rows) if r["canonical_stop_name"] == u_norm), None)
                    v_seq_idx = next(
                        (idx for idx, r in enumerate(t_rows) if u_seq_idx is not None and idx > u_seq_idx and r["canonical_stop_name"] == v_norm),
                        None
                    )
                    if u_seq_idx is not None and v_seq_idx is not None:
                        sub_rows = t_rows[u_seq_idx : v_seq_idx + 1]
                        ordered_norms = [r["canonical_stop_name"] for r in sub_rows]
                        ordered_names = [r["stop_name"] for r in sub_rows[1:-1] if r["stop_name"]]

                if len(ordered_norms) < 2:
                    cur.execute(
                        "SELECT DISTINCT route_id FROM route_stops WHERE line = ?",
                        (line_str,)
                    )
                    route_ids = [r[0] for r in cur.fetchall()]
                    for rid in route_ids:
                        cur.execute(
                            "SELECT stop_sequence, canonical_stop_name, stop_name FROM route_stops WHERE route_id = ? ORDER BY stop_sequence ASC",
                            (rid,)
                        )
                        r_rows = cur.fetchall()
                        u_seq_idx = next((idx for idx, r in enumerate(r_rows) if r["canonical_stop_name"] == u_norm), None)
                        v_seq_idx = next(
                            (idx for idx, r in enumerate(r_rows) if u_seq_idx is not None and idx > u_seq_idx and r["canonical_stop_name"] == v_norm),
                            None
                        )
                        if u_seq_idx is not None and v_seq_idx is not None:
                            sub_rows = r_rows[u_seq_idx : v_seq_idx + 1]
                            ordered_norms = [r["canonical_stop_name"] for r in sub_rows]
                            ordered_names = [r["stop_name"] for r in sub_rows[1:-1] if r["stop_name"]]
                            break
            except Exception:
                pass

        if len(ordered_norms) < 2:
            ordered_norms = [u_norm, v_norm]

        # Odstránenie prípadných duplikátov za sebou
        clean_norms: List[str] = []
        for cn in ordered_norms:
            if not clean_norms or clean_norms[-1] != cn:
                clean_norms.append(cn)
        ordered_norms = clean_norms

        # Výpočet hrubých ťažiskových súradníc jednotlivých uzlov na určenie vektora jazdy
        centroids: List[Tuple[float, float]] = []
        for idx, cn in enumerate(ordered_norms):
            cands = self.stops_by_norm_canonical.get(cn, [])
            line_cands = [c for c in cands if line_str in [str(x).strip() for x in c.get("lines", [])]]
            pool = line_cands if line_cands else cands
            if pool:
                clat = sum(float(c["latitude"]) for c in pool) / len(pool)
                clon = sum(float(c["longitude"]) for c in pool) / len(pool)
                centroids.append((clat, clon))
            elif idx == 0:
                centroids.append((float(u_stop["latitude"]), float(u_stop["longitude"])))
            else:
                centroids.append((float(v_stop["latitude"]), float(v_stop["longitude"])))

        # Výber smerovo správneho stĺpika pre každú zastávku v úseku
        directional_stops: List[Dict[str, Any]] = []
        n_total = len(ordered_norms)
        for i, cn in enumerate(ordered_norms):
            prev_pt = centroids[i - 1] if i > 0 else centroids[0]
            next_pt = centroids[i + 1] if i < n_total - 1 else centroids[-1]
            fb = u_stop if i == 0 else (v_stop if i == n_total - 1 else None)
            chosen = self.select_directional_platform(line_str, cn, prev_pt, next_pt, fallback_stop=fb)
            if chosen:
                directional_stops.append(chosen)
            elif fb:
                directional_stops.append(fb)

        if not ordered_names and len(directional_stops) > 2:
            seen_n = set()
            for s in directional_stops[1:-1]:
                cname = self.get_canonical_name(s)
                if cname and cname not in seen_n:
                    seen_n.add(cname)
                    ordered_names.append(cname)

        return directional_stops, ordered_names

    def _select_osrm_key_waypoints(self, ordered_stops: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Pravidlo 4 (OPRAVA OSRM FALLBACKU - Zákaz slučiek v protismere):
        Neposiela do OSRM všetky medzizastávky. Vyberie len nástupný stĺpik, výstupný stĺpik
        a maximálne 1-2 kľúčové smerové rázcestia (iba ak trasa reálne odbočuje mimo priamu spojnicu o >= 350 m).
        """
        if not ordered_stops or len(ordered_stops) <= 2:
            return ordered_stops or []

        u_s = ordered_stops[0]
        v_s = ordered_stops[-1]
        u_lat, u_lon = float(u_s["latitude"]), float(u_s["longitude"])
        v_lat, v_lon = float(v_s["latitude"]), float(v_s["longitude"])

        def perp_dist_meters(pt_stop: Dict[str, Any], a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
            ax, ay = 0.0, 0.0
            bx = (b_lon - a_lon) * 73400.0
            by = (b_lat - a_lat) * 111320.0
            px = (float(pt_stop["longitude"]) - a_lon) * 73400.0
            py = (float(pt_stop["latitude"]) - a_lat) * 111320.0
            seg_len_sq = bx * bx + by * by
            if seg_len_sq < 1.0:
                return math.hypot(px, py)
            t = max(0.0, min(1.0, (px * bx + py * by) / seg_len_sq))
            proj_x, proj_y = t * bx, t * by
            return math.hypot(px - proj_x, py - proj_y)

        # Nájdi najväčšiu kolmú odchýlku spomedzi medzizastávok
        best_idx = None
        max_dev = 0.0
        for i in range(1, len(ordered_stops) - 1):
            dev = perp_dist_meters(ordered_stops[i], u_lat, u_lon, v_lat, v_lon)
            if dev > max_dev:
                max_dev = dev
                best_idx = i

        # Ak trasa neodbočuje o viac ako 350 m od hlavného ťahu, routujeme priamo medzi nástupom a výstupom!
        if best_idx is None or max_dev < 350.0:
            return [u_s, v_s]

        pivots = [best_idx]
        pivot_stop = ordered_stops[best_idx]
        p_lat, p_lon = float(pivot_stop["latitude"]), float(pivot_stop["longitude"])

        # Skontrolujeme, či v prvej alebo druhej polovici nie je ešte jedno výrazné rázcestie (>= 400 m)
        best_idx_2 = None
        max_dev_2 = 0.0
        for i in range(1, len(ordered_stops) - 1):
            if i == best_idx:
                continue
            if i < best_idx:
                dev = perp_dist_meters(ordered_stops[i], u_lat, u_lon, p_lat, p_lon)
            else:
                dev = perp_dist_meters(ordered_stops[i], p_lat, p_lon, v_lat, v_lon)
            if dev > max_dev_2:
                max_dev_2 = dev
                best_idx_2 = i

        if best_idx_2 is not None and max_dev_2 >= 400.0:
            pivots.append(best_idx_2)
            pivots.sort()

        return [u_s] + [ordered_stops[idx] for idx in pivots] + [v_s]

    def get_osrm_road_geometry(
        self,
        waypoint_stops: List[Dict[str, Any]],
        mode: str = "driving"
    ) -> List[List[float]]:
        """
        Získa detailnú geometriu ulíc pomocou OSRM routingu.
        Pre mode='driving' aplikuje ochranu proti protismerným slučkám a otočkám (Pravidlo 4):
        - Používa continue_straight=true a obmedzený počet kľúčových smerových bodov.
        - Ak medzizastávka spôsobí v OSRM protismernú otočku (predĺženie trasy > 1.85x),
          automaticky prepočíta priamu trasu medzi nástupom a výstupom so smerovým azimutom (bearings).
        """
        if not waypoint_stops or len(waypoint_stops) < 2:
            return []

        if mode == "driving" and len(waypoint_stops) > 4:
            stops_to_route = self._select_osrm_key_waypoints(waypoint_stops)
        else:
            stops_to_route = list(waypoint_stops)

        u_pt = [float(stops_to_route[0]["latitude"]), float(stops_to_route[0]["longitude"])]
        v_pt = [float(stops_to_route[-1]["latitude"]), float(stops_to_route[-1]["longitude"])]

        coords_param = ";".join(
            f"{float(s['longitude']):.6f},{float(s['latitude']):.6f}"
            for s in stops_to_route
        )

        cache_key = f"osrm_v2_{mode}_{coords_param}"
        if cache_key in self._osrm_cache:
            return self._osrm_cache[cache_key]

        def fetch_osrm(pts_list: List[Dict[str, Any]], use_bearings: bool = False) -> Tuple[List[List[float]], float]:
            c_str = ";".join(
                f"{float(s['longitude']):.6f},{float(s['latitude']):.6f}"
                for s in pts_list
            )
            extra_params = "&continue_straight=true" if mode == "driving" else ""
            if mode == "driving" and use_bearings:
                b_list = []
                r_list = []
                for idx_p in range(len(pts_list)):
                    p_a = pts_list[idx_p - 1] if idx_p > 0 else pts_list[idx_p]
                    p_b = pts_list[idx_p + 1] if idx_p < len(pts_list) - 1 else pts_list[idx_p]
                    ang = self._calculate_bearing(
                        float(p_a["latitude"]), float(p_a["longitude"]),
                        float(p_b["latitude"]), float(p_b["longitude"])
                    )
                    b_list.append(f"{ang},65")
                    r_list.append("55")
                extra_params += f"&bearings={';'.join(b_list)}&radiuses={';'.join(r_list)}"

            url = f"https://router.project-osrm.org/route/v1/{mode}/{c_str}?overview=full&geometries=geojson{extra_params}"
            req = urllib.request.Request(url, headers={"User-Agent": "MHD-Kosice-Routing/3.0"})
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("code") == "Ok" and data.get("routes"):
                    route_obj = data["routes"][0]
                    geojson_coords = route_obj["geometry"]["coordinates"]
                    l_coords = [[float(c[1]), float(c[0])] for c in geojson_coords]
                    return l_coords, float(route_obj.get("distance") or 0.0)
            return [], 0.0

        direct_chord_sum = sum(
            self.haversine_distance(
                float(stops_to_route[i]["latitude"]), float(stops_to_route[i]["longitude"]),
                float(stops_to_route[i + 1]["latitude"]), float(stops_to_route[i + 1]["longitude"])
            )
            for i in range(len(stops_to_route) - 1)
        )

        try:
            leaflet_coords, osrm_dist = fetch_osrm(stops_to_route, use_bearings=False)

            # Ak medzibod prichytil protismerný pruh a vytvoril otočku (predĺženie > 1.85x),
            # routujeme priamo medzi nástupnou a výstupnou zastávkou
            if mode == "driving" and len(stops_to_route) > 2 and direct_chord_sum > 100.0:
                if not leaflet_coords or osrm_dist > direct_chord_sum * 1.85:
                    direct_pair = [stops_to_route[0], stops_to_route[-1]]
                    alt_coords, alt_dist = fetch_osrm(direct_pair, use_bearings=False)
                    if len(alt_coords) >= 2 and (not leaflet_coords or alt_dist < osrm_dist):
                        leaflet_coords, osrm_dist = alt_coords, alt_dist

            # Ak by aj pri 2 bodoch OSRM chytil protismer na štvorprúdovke, vynútime smerový azimut (bearings)
            end_to_end_m = self.haversine_distance(u_pt[0], u_pt[1], v_pt[0], v_pt[1])
            if mode == "driving" and end_to_end_m > 150.0 and osrm_dist > end_to_end_m * 2.05:
                try:
                    b_coords, b_dist = fetch_osrm([stops_to_route[0], stops_to_route[-1]], use_bearings=True)
                    if len(b_coords) >= 2 and b_dist < osrm_dist:
                        leaflet_coords, osrm_dist = b_coords, b_dist
                except Exception:
                    pass

            if len(leaflet_coords) >= 2:
                if mode == "driving":
                    sliced = self._slice_polyline_between_endpoints(leaflet_coords, u_pt, v_pt)
                    if len(sliced) >= 2:
                        leaflet_coords = sliced
                self._osrm_cache[cache_key] = leaflet_coords
                return leaflet_coords
        except Exception:
            pass

        return [[float(s["latitude"]), float(s["longitude"])] for s in stops_to_route]

    def get_transit_segment_geometry(
        self,
        line: str,
        u_stop: Dict[str, Any],
        v_stop: Dict[str, Any],
        trip_id: Optional[Any] = None,
        sub_path_canonical: Optional[List[str]] = None,
        intermediate_stops: Optional[List[str]] = None,
        return_directional_stops: bool = False
    ) -> Union[Tuple[List[List[float]], List[str]], Tuple[List[List[float]], List[str], Dict[str, Any], Dict[str, Any]]]:
        """
        Získa presnú geometriu ulíc a zoznam medzizastávok pre úsek jazdy linkou `line`
        medzi nástupnou (`u_stop`) a výstupnou (`v_stop`) zastávkou podľa 4 striktných pravidiel:
        1. Presný zoznam zastávok úseku (Sub-path) a smerovo správny stĺpik (pravá strana vozovky v smere jazdy).
        2. Tvrdé orezanie Ubian krivky (Polyline Slicing: coords[start_idx : end_idx + 1] kde start_idx < end_idx).
        3. Detekcia trhlín a skokov (Jump Guard: ak susedné body > 250 m, Ubian krivka sa zahodí).
        4. Čistý OSRM fallback bez slučiek v protismere (iba kľúčové smerové body + kontrola otočiek).
        """
        line_str = str(line).strip()

        # PRAVIDLO 1: Presný zoznam zastávok úseku (Sub-path) a výber smerových stĺpikov
        ordered_stops, inter_names = self.get_ordered_subpath_stops(
            line_str,
            u_stop,
            v_stop,
            trip_id=trip_id,
            sub_path_canonical=sub_path_canonical,
            intermediate_stops=intermediate_stops
        )
        u_dir_stop = dict(ordered_stops[0]) if ordered_stops else dict(u_stop)
        v_dir_stop = dict(ordered_stops[-1]) if ordered_stops else dict(v_stop)

        u_id = u_dir_stop["stop_id"]
        v_id = v_dir_stop["stop_id"]
        u_base_id = str(u_id).split("_")[0]
        v_base_id = str(v_id).split("_")[0]
        u_norm = normalize_canonical_stop(self.get_canonical_name(u_dir_stop))
        v_norm = normalize_canonical_stop(self.get_canonical_name(v_dir_stop))

        cache_key = ("v2", line_str, u_id, v_id, str(trip_id or 0))
        if cache_key in self._route_geometry_cache:
            cached_coords, cached_inter = self._route_geometry_cache[cache_key]
            if cached_coords:
                u_dir_stop["latitude"], u_dir_stop["longitude"] = cached_coords[0][0], cached_coords[0][1]
                v_dir_stop["latitude"], v_dir_stop["longitude"] = cached_coords[-1][0], cached_coords[-1][1]
            if return_directional_stops:
                return cached_coords, cached_inter, u_dir_stop, v_dir_stop
            return cached_coords, cached_inter

        u_pt = [float(u_dir_stop["latitude"]), float(u_dir_stop["longitude"])]
        v_pt = [float(v_dir_stop["latitude"]), float(v_dir_stop["longitude"])]

        # 1. Zozbieranie kandidátnych Ubian jázd (numerické trip_id) pre danú linku
        candidate_trip_ids: List[int] = []
        if trip_id is not None and str(trip_id).strip().isdigit():
            tid_int = int(str(trip_id).strip())
            if tid_int not in candidate_trip_ids:
                candidate_trip_ids.append(tid_int)

        if self.live_feed:
            # A. Zo živých vozidiel v premávke
            try:
                live_vehicles = self.get_live_vehicles_cached() or []
                for veh in live_vehicles:
                    if str(veh.get("line")).strip() == line_str and veh.get("trip_id"):
                        tid = veh["trip_id"]
                        if str(tid).isdigit() and int(tid) not in candidate_trip_ids:
                            candidate_trip_ids.append(int(tid))
            except Exception:
                pass

            # B. Z odchodov na nástupnej zastávke
            try:
                cached_deps = self.get_stop_departures_cached(u_id, datetime.now(), allow_network=False) or []
                if not cached_deps and u_stop["stop_id"] != u_id:
                    cached_deps = self.get_stop_departures_cached(u_stop["stop_id"], datetime.now(), allow_network=False) or []
                for dep in cached_deps:
                    if str(dep.get("line")).strip() == line_str and dep.get("trip_id"):
                        tid = dep["trip_id"]
                        if str(tid).isdigit() and int(tid) not in candidate_trip_ids:
                            candidate_trip_ids.append(int(tid))
            except Exception:
                pass

        # 2. Hľadanie jazdy v správnom smere (u_idx < v_idx), tvrdé orezanie krivky (Pravidlo 2) a Jump Guard (Pravidlo 3)
        for tid in candidate_trip_ids:
            trip_data = None
            if tid in self._trip_details_cache:
                trip_data = self._trip_details_cache[tid]
            elif self.live_feed:
                try:
                    trip_data = self.live_feed.get_trip_polyline_and_stops(tid)
                    if trip_data and "tripStops" in trip_data:
                        self._trip_details_cache[tid] = trip_data
                except Exception:
                    pass

            if not trip_data:
                continue

            trip_stops = trip_data.get("tripStops") or []
            if not trip_stops:
                continue

            u_idx = None
            v_idx = None

            for i, st in enumerate(trip_stops):
                st_id_str = str(st.get("stopID") or "").split("_")[0]
                st_norm = normalize_canonical_stop(st.get("stopName") or "")

                if u_idx is None:
                    if (st_id_str and st_id_str == u_base_id) or (u_norm and st_norm == u_norm):
                        u_idx = i
                        continue
                    if st.get("latitude") is not None and st.get("longitude") is not None:
                        if self.haversine_distance(float(st["latitude"]), float(st["longitude"]), u_pt[0], u_pt[1]) < 95.0:
                            u_idx = i
                            continue

                if u_idx is not None and v_idx is None:
                    if (st_id_str and st_id_str == v_base_id) or (v_norm and st_norm == v_norm):
                        v_idx = i
                        break
                    if st.get("latitude") is not None and st.get("longitude") is not None:
                        if self.haversine_distance(float(st["latitude"]), float(st["longitude"]), v_pt[0], v_pt[1]) < 95.0:
                            v_idx = i
                            break

            if u_idx is not None and v_idx is not None and u_idx < v_idx:
                sub_stops = trip_stops[u_idx : v_idx + 1]

                # Presné smerové GPS súradnice nástupného a výstupného stĺpika priamo z danej jazdy Ubianu (Pravidlo 1)
                u_st_obj = sub_stops[0]
                v_st_obj = sub_stops[-1]
                ubian_u_pt = [
                    float(u_st_obj["latitude"]) if u_st_obj.get("latitude") is not None else u_pt[0],
                    float(u_st_obj["longitude"]) if u_st_obj.get("longitude") is not None else u_pt[1]
                ]
                ubian_v_pt = [
                    float(v_st_obj["latitude"]) if v_st_obj.get("latitude") is not None else v_pt[0],
                    float(v_st_obj["longitude"]) if v_st_obj.get("longitude") is not None else v_pt[1]
                ]

                if u_st_obj.get("stopID") and u_st_obj.get("platformNumber"):
                    cand_uid = f"{u_st_obj['stopID']}_{u_st_obj['platformNumber']}"
                    if cand_uid in self.stops_by_id:
                        u_dir_stop = dict(self.stops_by_id[cand_uid])
                if v_st_obj.get("stopID") and v_st_obj.get("platformNumber"):
                    cand_vid = f"{v_st_obj['stopID']}_{v_st_obj['platformNumber']}"
                    if cand_vid in self.stops_by_id:
                        v_dir_stop = dict(self.stops_by_id[cand_vid])

                u_dir_stop["latitude"], u_dir_stop["longitude"] = ubian_u_pt[0], ubian_u_pt[1]
                v_dir_stop["latitude"], v_dir_stop["longitude"] = ubian_v_pt[0], ubian_v_pt[1]

                # Presný zoznam medzizastávok z podúseku jazdy
                ubian_inter_names: List[str] = []
                seen_n = set()
                for s_item in sub_stops[1:-1]:
                    sn = s_item.get("stopName")
                    if sn:
                        cn = normalize_canonical_stop(sn)
                        if cn and cn not in seen_n:
                            seen_n.add(cn)
                            ubian_inter_names.append(sn)

                final_inter_names = ubian_inter_names if ubian_inter_names else inter_names

                # Zostavenie bodov krivky z Ubian route segmentov
                u_order = u_st_obj.get("stopOrder")
                v_order = v_st_obj.get("stopOrder")
                route_segs = trip_data.get("route") or []

                matching_segs = []
                if u_order is not None and v_order is not None:
                    matching_segs = [s for s in route_segs if u_order <= s.get("tripStopOrder", 0) < v_order]
                if not matching_segs:
                    matching_segs = route_segs

                raw_road_coords: List[List[float]] = []
                for seg in matching_segs:
                    for pt in seg.get("modelRoutePoints") or []:
                        lat = pt.get("latitude")
                        lng = pt.get("longitude")
                        if lat is not None and lng is not None:
                            lat_f = float(lat)
                            lng_f = float(lng)
                            if not raw_road_coords or (
                                abs(raw_road_coords[-1][0] - lat_f) > 1e-6 or
                                abs(raw_road_coords[-1][1] - lng_f) > 1e-6
                            ):
                                raw_road_coords.append([lat_f, lng_f])

                # PRAVIDLO 2: Tvrdé orezanie Ubian krivky (Polyline Slicing: coords[start_idx : end_idx + 1])
                sliced_coords = self._slice_polyline_between_endpoints(raw_road_coords, ubian_u_pt, ubian_v_pt)

                # PRAVIDLO 3: Detekcia trhlín a skokov (Jump Guard: susedné body nesmú byť ďalej ako 250 m)
                if len(sliced_coords) >= 2 and not self._has_geometry_jump(sliced_coords, max_step_meters=250.0):
                    u_dir_stop["latitude"], u_dir_stop["longitude"] = sliced_coords[0][0], sliced_coords[0][1]
                    v_dir_stop["latitude"], v_dir_stop["longitude"] = sliced_coords[-1][0], sliced_coords[-1][1]
                    self._route_geometry_cache[cache_key] = (sliced_coords, final_inter_names)
                    if return_directional_stops:
                        return sliced_coords, final_inter_names, u_dir_stop, v_dir_stop
                    return sliced_coords, final_inter_names

        # 3. PRAVIDLO 4: Čistý OSRM Fallback bez slučiek v protismere (iba kľúčové smerové body)
        waypoints = self._select_osrm_key_waypoints(ordered_stops) if len(ordered_stops) >= 2 else [u_dir_stop, v_dir_stop]
        osrm_road = self.get_osrm_road_geometry(waypoints, mode="driving")

        if len(osrm_road) >= 2:
            u_dir_stop["latitude"], u_dir_stop["longitude"] = osrm_road[0][0], osrm_road[0][1]
            v_dir_stop["latitude"], v_dir_stop["longitude"] = osrm_road[-1][0], osrm_road[-1][1]
            self._route_geometry_cache[cache_key] = (osrm_road, inter_names)
            if return_directional_stops:
                return osrm_road, inter_names, u_dir_stop, v_dir_stop
            return osrm_road, inter_names

        # Záložný plán pri úplnej nedostupnosti internetu
        fallback_coords = [[float(s["latitude"]), float(s["longitude"])] for s in ordered_stops] if len(ordered_stops) >= 2 else [u_pt, v_pt]
        self._route_geometry_cache[cache_key] = (fallback_coords, inter_names)
        if return_directional_stops:
            return fallback_coords, inter_names, u_dir_stop, v_dir_stop
        return fallback_coords, inter_names

    def get_corridor_stops(
        self,
        line: str,
        u_stop: Dict[str, Any],
        v_stop: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Vráti presne zoradené zastávky úseku medzi u_stop a v_stop so smerovo správnymi stĺpikmi.
        """
        ordered_stops, _ = self.get_ordered_subpath_stops(line, u_stop, v_stop)
        return ordered_stops if len(ordered_stops) >= 2 else [u_stop, v_stop]

    def get_live_vehicles_cached(self, max_age_seconds: float = 30.0) -> List[Dict[str, Any]]:
        """Získa živé vozidlá z pamäte alebo stiahne čerstvé z Ubianu (s TTL vyrovnávacou pamäťou)."""
        now = datetime.now().timestamp()
        if hasattr(self, "_live_vehicles_cache") and self._live_vehicles_cache is not None:
            if (now - getattr(self, "_live_vehicles_cache_ts", 0)) < max_age_seconds:
                return self._live_vehicles_cache

        if not self.live_feed:
            return []

        try:
            vehs = self.live_feed.get_live_vehicles() or []
            self._live_vehicles_cache = vehs
            self._live_vehicles_cache_ts = now
            return vehs
        except Exception:
            return getattr(self, "_live_vehicles_cache", []) or []

    def get_live_line_telemetry(self, line: str, stop_id: int) -> Dict[str, Any]:
        """
        Získa reálne meškanie a odhadovaný čas čakania na linku na danej zastávke
        pomocou živého feedu alebo naplánovaných odchodov.
        """
        default_result = {
            "wait_seconds": 180,
            "wait_minutes": 3.0,
            "delay_minutes": 0,
            "vehicle_info": None,
            "license_number": None,
            "is_live": False
        }

        if not self.live_feed:
            return default_result

        # 1. Kontrola živých vozidiel na linke
        try:
            live_vehicles = self.get_live_vehicles_cached() or []
        except Exception:
            live_vehicles = []

        matching_vehicles = [v for v in live_vehicles if str(v.get("line")) == str(line)]
        
        target_stop = self.stops_by_id.get(stop_id)
        if matching_vehicles and target_stop:
            best_v = None
            min_dist = float("inf")
            for v in matching_vehicles:
                v_lat = v.get("latitude")
                v_lon = v.get("longitude")
                if v_lat and v_lon:
                    d = self.haversine_distance(v_lat, v_lon, target_stop["latitude"], target_stop["longitude"])
                    if d < min_dist:
                        min_dist = d
                        best_v = v

            if best_v:
                delay = int(best_v.get("delay_minutes", 0))
                est_wait = max(60, min(900, int(min_dist / 6.0) + (delay * 60)))
                v_id = best_v.get("vehicle_id")
                lic = best_v.get("license_number")
                fleet_info = None
                if self.fleet_service:
                    fleet = self.fleet_service.match_live_vehicle(
                        vehicle_id=v_id,
                        license_number=lic,
                        line=best_v.get("line"),
                        line_type=best_v.get("line_type"),
                        raw_vehicle=best_v
                    )
                    if fleet:
                        spz_str = fleet.get("spz") or (f"ev. č. {fleet.get('evidencne_cislo')}" if fleet.get("evidencne_cislo") else None)
                        model_name = fleet.get("model") or ("Električka DPMK" if best_v.get("line_type") == "TRAM" else "Autobus DPMK")
                        fleet_info = f"{model_name} ({spz_str})" if spz_str else model_name

                return {
                    "wait_seconds": est_wait,
                    "wait_minutes": round(est_wait / 60.0, 1),
                    "delay_minutes": delay,
                    "vehicle_info": fleet_info,
                    "license_number": lic,
                    "is_live": True
                }

        return default_result

    def get_live_delay_for_departure(
        self,
        line: str,
        destination_stop: Optional[str] = None,
        trip_id: Optional[str] = None,
        is_future: bool = False
    ) -> Tuple[int, Optional[str], Optional[str], bool]:
        """
        Vyhľadá živé vozidlo na danej linke a vráti:
        (delay_minutes, vehicle_info, license_number, is_live)
        Pre is_future=True ignoruje aktuálne live meškanie a vracia (0, None, None, False).
        """
        if is_future:
            return 0, None, None, False

        vehicles = []
        if self.live_feed:
            try:
                vehicles = self.get_live_vehicles_cached(max_age_seconds=15.0) or []
            except Exception:
                vehicles = []
        if not vehicles:
            try:
                from app.main import LAST_SEEN_CACHE
                vehicles = LAST_SEEN_CACHE or []
            except Exception:
                vehicles = []

        if not vehicles:
            return 0, None, None, False

        line_str = str(line).strip()
        norm_dest = normalize_canonical_stop(destination_stop) if destination_stop else ""

        matched_veh = None
        for v in vehicles:
            if str(v.get("line")).strip() == line_str:
                v_dest = normalize_canonical_stop(v.get("destination") or v.get("destination_full") or "")
                if norm_dest:
                    if v_dest and (norm_dest in v_dest or v_dest in norm_dest):
                        matched_veh = v
                        break
                else:
                    matched_veh = v
                    break

        if matched_veh:
            delay = int(matched_veh.get("delay_minutes", 0) or 0)
            vid = matched_veh.get("vehicle_id")
            lic = matched_veh.get("license_number")
            fleet_info = None
            if self.fleet_service and (vid or lic):
                fleet = self.fleet_service.match_live_vehicle(
                    vehicle_id=vid,
                    license_number=lic,
                    line=line_str,
                    line_type=matched_veh.get("line_type"),
                    raw_vehicle=matched_veh
                )
                if fleet:
                    spz_str = fleet.get("spz") or (f"ev. č. {fleet.get('evidencne_cislo')}" if fleet.get('evidencne_cislo') else None)
                    model_name = fleet.get("model") or ("Električka DPMK" if matched_veh.get("line_type") == "TRAM" else "Autobus DPMK")
                    fleet_info = f"{model_name} ({spz_str})" if spz_str else model_name

            return delay, fleet_info, lic, True

        return 0, None, None, False

    def get_transit_departures_for_routing(
        self,
        canonical_stop: str,
        line: str,
        current_dt: datetime,
        is_future: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Získa najbližšie oficiálne naplánované odchody a ich následné zastávky pre linku zo zastávky.
        Striktne stavia na SQLite databáze grafikónov (timetables.db).
        K plánovanému času pripočíta meškanie zo živého feedu, ak spoj aktuálne premáva.
        """
        c_stop = normalize_canonical_stop(canonical_stop)
        if not c_stop or not self.timetable_manager:
            return []

        line_str = str(line).strip()
        day_type = "weekend" if current_dt.weekday() >= 5 else "workday"
        cur_sec = current_dt.hour * 3600 + current_dt.minute * 60 + current_dt.second

        cache_key = (c_stop, line_str, day_type, cur_sec // 60, is_future)
        if cache_key in self._routing_transit_cache:
            return self._routing_transit_cache[cache_key]

        conn = self.timetable_manager._ensure_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT trip_id, route_id, line, direction, departure_seconds, departure_time_str, stop_sequence, destination_stop
            FROM stop_departures
            WHERE canonical_stop_name = ? AND line = ? AND day_type = ? AND departure_seconds >= ?
            ORDER BY departure_seconds ASC
            LIMIT 6
        """, (c_stop, line_str, day_type, cur_sec))
        rows = cur.fetchall()

        day_offset = 0
        if not rows:
            next_dt = current_dt + timedelta(days=1)
            next_day_type = "weekend" if next_dt.weekday() >= 5 else "workday"
            cur.execute("""
                SELECT trip_id, route_id, line, direction, departure_seconds, departure_time_str, stop_sequence, destination_stop
                FROM stop_departures
                WHERE canonical_stop_name = ? AND line = ? AND day_type = ? AND departure_seconds >= 0
                ORDER BY departure_seconds ASC
                LIMIT 6
            """, (c_stop, line_str, next_day_type))
            rows = cur.fetchall()
            day_offset = 86400

        if not rows:
            self._routing_transit_cache[cache_key] = []
            return []

        earliest_by_dir: Dict[str, Any] = {}
        for r in rows:
            dest_norm = normalize_canonical_stop(r["destination_stop"])
            if c_stop == dest_norm:
                continue
            d_key = r["direction"]
            if d_key not in earliest_by_dir:
                earliest_by_dir[d_key] = r

        results = []
        for d in earliest_by_dir.values():
            wait_sec = (d["departure_seconds"] + day_offset) - cur_sec
            if wait_sec > 18000:
                continue

            # Live delay overlay iba ak je spoj v rozumnom okne živého sledovania (<= 40 min / 2400 s)
            if not is_future and wait_sec <= 2400:
                delay_min, veh_info, lic, is_live = self.get_live_delay_for_departure(
                    line_str, destination_stop=d["destination_stop"], trip_id=d["trip_id"], is_future=is_future
                )
            else:
                delay_min, veh_info, lic, is_live = 0, None, None, False
            eff_wait_sec = max(0, wait_sec + (delay_min * 60))

            ds_key = (d["trip_id"], d["stop_sequence"])
            if ds_key not in self._trip_downstream_cache:
                cur.execute("""
                    SELECT canonical_stop_name, departure_seconds, departure_time_str, stop_sequence, stop_name
                    FROM stop_departures
                    WHERE trip_id = ? AND stop_sequence > ?
                    ORDER BY stop_sequence ASC
                """, (d["trip_id"], d["stop_sequence"]))
                downstream = cur.fetchall()

                downstream_list = []
                for ds in downstream:
                    ride_sec = ds["departure_seconds"] - d["departure_seconds"]
                    if ride_sec < 0:
                        ride_sec += 86400
                    seq_diff = max(1, ds["stop_sequence"] - d["stop_sequence"])
                    if ride_sec < 60:
                        ride_sec = max(60, seq_diff * 60)

                    arr_sec = (d["departure_seconds"] + ride_sec) % 86400
                    arr_time_str = f"{arr_sec // 3600:02d}:{(arr_sec % 3600) // 60:02d}"

                    downstream_list.append({
                        "canonical_stop_name": ds["canonical_stop_name"],
                        "stop_name": ds["stop_name"],
                        "departure_time_str": arr_time_str,
                        "ride_seconds": ride_sec
                    })
                self._trip_downstream_cache[ds_key] = downstream_list

            results.append({
                "line": d["line"],
                "direction": d["direction"],
                "destination_stop": d["destination_stop"],
                "trip_id": d["trip_id"],
                "departure_seconds": d["departure_seconds"],
                "departure_time_str": d["departure_time_str"],
                "wait_seconds": wait_sec,
                "effective_wait_seconds": eff_wait_sec,
                "delay_minutes": delay_min,
                "vehicle_info": veh_info,
                "is_live": is_live,
                "downstream_stops": self._trip_downstream_cache[ds_key]
            })

        self._routing_transit_cache[cache_key] = results
        return results

    def get_line_schedule_window(self, line: str, dt: datetime) -> Tuple[bool, int, int]:
        """
        Vyhodnotí prevádzkový režim linky MHD v danom čase podľa timetables.db a vráti:
        (is_operating_now, seconds_until_next_run, typical_headway_seconds).
        Ak linka v danom čase nepremáva, vráti is_operating_now=False a presný počet sekúnd čakania do začiatku najbližšej premávky.
        """
        line_str = str(line).strip()
        if not self.is_mhd_line(line_str):
            return False, 86400, 86400

        try:
            day_type = "weekend" if dt.weekday() >= 5 else "workday"
            cur_sec = dt.hour * 3600 + dt.minute * 60 + dt.second
            conn = self.timetable_manager._ensure_connection()
            cur = conn.cursor()
            cur.execute("""
                SELECT departure_seconds FROM stop_departures
                WHERE line = ? AND day_type = ? AND departure_seconds >= ?
                ORDER BY departure_seconds ASC LIMIT 2
            """, (line_str, day_type, cur_sec))
            rows = cur.fetchall()
            if rows:
                wait_sec = rows[0][0] - cur_sec
                headway = (rows[1][0] - rows[0][0]) if len(rows) > 1 else 900
                headway = max(300, min(3600, headway))
                is_operating = wait_sec <= 3600
                return is_operating, wait_sec, headway

            next_dt = dt + timedelta(days=1)
            next_day_type = "weekend" if next_dt.weekday() >= 5 else "workday"
            cur.execute("""
                SELECT departure_seconds FROM stop_departures
                WHERE line = ? AND day_type = ? AND departure_seconds >= 0
                ORDER BY departure_seconds ASC LIMIT 1
            """, (line_str, next_day_type))
            r_next = cur.fetchone()
            if r_next:
                wait_sec = (r_next[0] + 86400) - cur_sec
                return False, wait_sec, 900
        except Exception:
            pass

        return False, 86400, 86400

    def get_stop_departures_cached(
        self,
        stop_id: int,
        dt: datetime,
        allow_network: bool = True
    ) -> List[Dict[str, Any]]:
        """Získa plánované a reálne odchody zo zastávky z vyrovnávacej pamäte alebo z Ubian API."""
        if not self.live_feed:
            return []

        date_str = dt.strftime("%Y-%m-%d")
        cache_key = (stop_id, date_str, dt.hour)
        if cache_key in self._stop_departures_cache:
            return self._stop_departures_cache[cache_key]

        if not allow_network:
            return []

        try:
            now_dt = datetime.now()
            diff_from_now = abs((dt - now_dt).total_seconds())
            if diff_from_now < 180:
                data = self.live_feed.get_stop_departures(stop_id)
            else:
                data = self.live_feed.get_stop_departures(stop_id, date=date_str, time=dt.strftime("%H:%M"))
            deps = data.get("departures", [])
            # Filtrujeme výlučne klasické mestské linky DPMK (odstraňujeme Eurobusy a vlaky)
            deps = [d for d in deps if self.is_mhd_line(d.get("line"))]
            self._stop_departures_cache[cache_key] = deps
            return deps
        except Exception:
            self._stop_departures_cache[cache_key] = []
            return []

    def parse_departure_time(self, departure_time_str: Optional[str]) -> Tuple[datetime, bool]:
        """
        Parsuje zadaný reťazec času odchodu:
        - Môže byť None, "", "now", "teraz" -> aktuálny datetime, is_future = False
        - Formát HH:MM -> dnešný deň v zadanom čase
        - ISO reťazec YYYY-MM-DDTHH:MM, YYYY-MM-DD HH:MM atď.
        Vráti (dt, is_future).
        is_future je True, ak cieľový čas je o viac ako 10 minút (600 s) v budúcnosti voči terajšku,
        alebo ak je dátum v budúcom dni.
        """
        now = datetime.now()
        if not departure_time_str or str(departure_time_str).strip().lower() in ("now", "teraz", "none"):
            return now, False

        val = str(departure_time_str).strip()
        dt = None

        # 1. Skúsime ISO formát s dátumom
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                dt = datetime.strptime(val, fmt)
                break
            except ValueError:
                pass

        # 2. Skúsime jednoduchý čas HH:MM(:SS)
        if dt is None:
            try:
                parts = val.split(":")
                hh = int(parts[0])
                mm = int(parts[1])
                ss = int(parts[2]) if len(parts) > 2 else 0
                dt = now.replace(hour=hh, minute=mm, second=ss, microsecond=0)
            except Exception:
                dt = now

        time_diff_sec = (dt - now).total_seconds()
        is_future = (time_diff_sec > 600) or (dt.date() > now.date())
        return dt, is_future

    def calculate_transit_edge_wait(
        self,
        stop_id: int,
        line: str,
        current_dt: datetime,
        allow_network: bool = False,
        is_future: bool = False
    ) -> Dict[str, Any]:
        """
        Vypočíta presný reálny čas čakania na linku na danej zastávke v danom čase s ohľadom na meškanie.
        Vychádza striktne z databázy cestovných poriadkov (timetables.db) a živého feedu.
        """
        line_str = str(line).strip()
        current_ts = int(current_dt.timestamp())

        if not self.is_mhd_line(line_str):
            return {
                "wait_seconds": 86400,
                "wait_minutes": 1440.0,
                "delay_minutes": 0,
                "expected_timestamp": current_ts + 86400,
                "trip_id": None,
                "vehicle_info": None,
                "license_number": None,
                "is_live": False
            }

        stop_obj = self.stops_by_id.get(stop_id) or self.stops_by_id.get(str(stop_id))
        stop_norm = normalize_canonical_stop(self.get_canonical_name(stop_obj)) if stop_obj else ""

        # 1. Kontrola Ubian odchodov na danej zastávke (ak povolené a dostupné)
        if allow_network:
            deps = self.get_stop_departures_cached(stop_id, current_dt, allow_network=True)
            matching_deps = [d for d in deps if str(d.get("line")).strip() == line_str]
            if matching_deps:
                valid_deps = []
                for d in matching_deps:
                    if is_future:
                        exp_ts = d.get("planned_timestamp") or d.get("expected_timestamp") or 0
                    else:
                        exp_ts = d.get("expected_timestamp")
                        if not exp_ts:
                            pl_ts = d.get("planned_timestamp") or 0
                            del_min = d.get("delay_minutes", 0)
                            exp_ts = pl_ts + (del_min * 60)
                    if exp_ts and exp_ts >= (current_ts - 30):
                        valid_deps.append((exp_ts, d))

                if valid_deps:
                    valid_deps.sort(key=lambda x: x[0])
                    best_exp_ts, best_d = valid_deps[0]
                    wait_sec = max(60, int(best_exp_ts - current_ts))
                    del_min = 0 if is_future else best_d.get("delay_minutes", 0)
                    tid = best_d.get("trip_id")
                    vid = None if is_future else best_d.get("vehicle_id")
                    lic = None if is_future else best_d.get("license_number")
                    fleet_info = None

                    if not is_future and self.fleet_service and (vid or lic):
                        fleet = self.fleet_service.match_live_vehicle(
                            vehicle_id=vid,
                            license_number=lic,
                            line=line_str,
                            line_type="TRAM" if best_d.get("line_type") == "TRAM" else "BUS",
                            raw_vehicle=best_d
                        )
                        if fleet:
                            spz_str = fleet.get("spz") or (f"ev. č. {fleet.get('evidencne_cislo')}" if fleet.get('evidencne_cislo') else None)
                            model_name = fleet.get("model") or ("Električka DPMK" if best_d.get("line_type") == "TRAM" else "Autobus DPMK")
                            fleet_info = f"{model_name} ({spz_str})" if spz_str else model_name

                    return {
                        "wait_seconds": wait_sec,
                        "wait_minutes": round(wait_sec / 60.0, 1),
                        "delay_minutes": del_min,
                        "expected_timestamp": best_exp_ts,
                        "trip_id": tid,
                        "vehicle_info": fleet_info,
                        "license_number": lic,
                        "is_live": False if is_future else bool(vid or lic)
                    }

        # 2. Striktný oficiálny odchod z timetables.db s live meškaním
        if stop_norm:
            tt_deps = self.get_transit_departures_for_routing(stop_norm, line_str, current_dt, is_future=is_future)
            if tt_deps:
                dep = tt_deps[0]
                return {
                    "wait_seconds": dep["effective_wait_seconds"],
                    "wait_minutes": round(dep["effective_wait_seconds"] / 60.0, 1),
                    "delay_minutes": dep["delay_minutes"],
                    "expected_timestamp": current_ts + dep["effective_wait_seconds"],
                    "trip_id": dep["trip_id"],
                    "vehicle_info": dep.get("vehicle_info"),
                    "license_number": None,
                    "is_live": dep.get("is_live", False)
                }

        # 3. Ak spoj v grafikone vôbec neexistuje / nepremáva na danej zastávke:
        return {
            "wait_seconds": 86400,
            "wait_minutes": 1440.0,
            "delay_minutes": 0,
            "expected_timestamp": current_ts + 86400,
            "trip_id": None,
            "vehicle_info": None,
            "license_number": None,
            "is_live": False
        }

    def dijkstra_search(
        self,
        from_id: Any,
        to_id: Any,
        departure_dt: Optional[datetime] = None,
        direct_only: bool = False,
        is_future: bool = False
    ) -> Tuple[Optional[int], List[Dict[str, Any]]]:
        """
        Multimodálny Dijkstrov algoritmus so super-uzlami:
        - Štartuje z úplne všetkých nástupíšť so zhodným počiatočným názvom (s cenou 0).
        - Flexibilný cieľ: končí v momente dosiahnutia ktoréhokoľvek nástupišťa so zhodným cieľovým názvom.
        - Uzly sú zastávky/nástupištia, hrany sú bezplatné prestupy na nástupišti, chôdza alebo jazda MHD.
        - direct_only=True: zakazuje prestupy medzi linkami a vracia len priame spojenia.
        - is_future=True: prehľadáva graf podľa plánovaných cestovných poriadkov bez live meškaní.
        """
        from_stop = self.resolve_stop(from_id)
        to_stop = self.resolve_stop(to_id)
        if not from_stop or not to_stop:
            return None, []

        from_canonical = self.get_canonical_name(from_stop)
        to_canonical = self.get_canonical_name(to_stop)

        if from_canonical == to_canonical:
            return 0, []

        # 1. Flexibilný cieľ: všetky fyzické nástupištia so zhodným cieľovým názvom
        target_platforms = self.stops_by_canonical_name.get(to_canonical, [to_stop])
        target_ids = set()
        for tp in target_platforms:
            t_sid = tp["stop_id"]
            target_ids.add(t_sid)
            target_ids.add(str(t_sid))
            t_base = str(t_sid).split("_")[0]
            target_ids.add(t_base)
            try:
                target_ids.add(int(t_base))
            except ValueError:
                pass
            if tp.get("parent_stop_id") is not None:
                target_ids.add(tp["parent_stop_id"])
                target_ids.add(str(tp["parent_stop_id"]))

        if not self.adjacency_list:
            self.load_walking_graph()

        dep_dt = departure_dt or datetime.now()

        # 2. Počiatočný stav: vložíme do prioritnej fronty s cenou 0 úplne všetky nástupištia so zhodným počiatočným názvom
        start_platforms = self.stops_by_canonical_name.get(from_canonical, [from_stop])
        counter = 0
        pq: List[Tuple[int, int, int, Any, Optional[str], List[Dict[str, Any]]]] = []
        best_cost: Dict[Any, int] = {}
        for sp in start_platforms:
            if not sp or not isinstance(sp, dict):
                continue
            s_sid = sp.get("stop_id")
            if not s_sid:
                continue
            counter += 1
            best_cost[s_sid] = 0
            best_cost[str(s_sid)] = 0
            try:
                best_cost[int(s_sid)] = 0
            except (ValueError, TypeError):
                pass
            # Prioritná fronta: (cost_metric, real_time_sec, counter, u, mode, path)
            heapq.heappush(pq, (0, 0, counter, s_sid, None, []))

        visited: Set[Any] = set()
        wait_cache: Dict[Tuple[Any, str], Dict[str, Any]] = {}
        transit_cache: Dict[Tuple[str, str, int], List[Dict[str, Any]]] = {}
        max_pops = 15000
        pop_count = 0

        # Masívna penalizácia za prestup (10 minút / 600 sekúnd), aby algoritmus preferoval priame spoje
        TRANSFER_PENALTY_SECONDS = 600

        while pq:
            pop_count += 1
            if pop_count > max_pops:
                break

            cost_metric, real_time_sec, _, u, mode, path = heapq.heappop(pq)

            u_str = str(u)
            if u in visited or u_str in visited:
                continue
            visited.add(u)
            visited.add(u_str)
            try:
                visited.add(int(u))
            except (ValueError, TypeError):
                pass

            if u in target_ids or u_str in target_ids:
                # Vrátime čistý reálny čas bez umelých prirážok
                return real_time_sec, path

            # Reálny čas na danom uzle bez umelých penalizácií pre korektný dopyt do cestovných poriadkov
            current_node_dt = dep_dt + timedelta(seconds=real_time_sec)

            if u not in self.stops_by_id and u_str not in self.stops_by_id:
                continue

            u_stop = self.stops_by_id.get(u) or self.stops_by_id.get(u_str)
            u_lat = u_stop.get("latitude")
            u_lon = u_stop.get("longitude")
            if u_lat is None or u_lon is None:
                continue

            has_prior_transit = any(act["type"] == "transit" for act in path)

            # 1. Pešie presuny a nulové prestupy na nástupišti
            u_edges = self.adjacency_list.get(u) or self.adjacency_list.get(u_str) or []
            for w in u_edges:
                v = w["to_stop_id"]
                v_str = str(v)
                if (v not in self.stops_by_id and v_str not in self.stops_by_id) or v in visited or v_str in visited:
                    continue

                # Ak je direct_only=True a cestujúci už raz cestoval spojom MHD:
                # peší presun je povolený len na cieľovú zastávku (výstup a príchod do cieľa).
                # Prestup pešo na inú zastávku za účelom prestupu na ďalšiu linku je zakázaný.
                if direct_only and has_prior_transit:
                    if not (v in target_ids or v_str in target_ids):
                        continue

                w_sec = w["walk_time_seconds"]
                is_platform_transfer = (w_sec == 0 or w.get("is_platform_transfer", False))

                # Zablokovanie viacnásobného reťazenia nulových prestupov: z nástupišťa A na B v rovnakom uzle stačí 1 krok
                if is_platform_transfer and mode == "platform_transfer":
                    continue
                # Obmedzenie: maximálne 1 samostatný peší presun za sebou (nulové presuny medzi stĺpikmi super-uzla sú povolené vždy)
                if (mode and mode.startswith("walk")) and not is_platform_transfer:
                    continue

                # Walk Penalty: multiplikátor 1.5x pre prestupovú chôdzu medzi linkami (okrem prvého príchodu a posledného odchodu)
                is_first_walk = not has_prior_transit
                is_last_walk = (v in target_ids or v_str in target_ids)
                if (not is_first_walk) and (not is_last_walk) and (not is_platform_transfer):
                    walk_cost = int(round(w_sec * 1.5))
                else:
                    walk_cost = w_sec

                new_cost = cost_metric + walk_cost
                new_real_time = real_time_sec + w_sec

                if new_cost >= best_cost.get(v, float("inf")) or new_cost >= best_cost.get(v_str, float("inf")):
                    continue
                best_cost[v] = new_cost
                best_cost[v_str] = new_cost
                try:
                    best_cost[int(v)] = new_cost
                except (ValueError, TypeError):
                    pass

                action = {
                    "type": "walk",
                    "from_id": u,
                    "to_id": v,
                    "distance_meters": w["distance_meters"],
                    "duration_seconds": w_sec,  # Čistý reálny čas bez penalizácie
                    "duration_minutes": w["walk_time_minutes"],
                    "is_platform_transfer": is_platform_transfer
                }
                counter += 1
                next_mode = "platform_transfer" if is_platform_transfer else "walk"
                heapq.heappush(pq, (new_cost, new_real_time, counter, v, next_mode, path + [action]))

            # 2. Jazda MHD - výlučne podľa oficiálnych grafikonov z timetables.db s live meškaniami
            u_norm = normalize_canonical_stop(self.get_canonical_name(u_stop))
            u_lines = [l for l in u_stop.get("lines", []) if self.is_mhd_line(l)]

            for line in u_lines:
                if mode == f"transit_{line}":
                    continue

                t_cache_key = (u_norm, str(line).strip(), int(current_node_dt.timestamp()) // 60)
                if t_cache_key not in transit_cache:
                    transit_cache[t_cache_key] = self.get_transit_departures_for_routing(
                        u_norm, line, current_node_dt, is_future=is_future
                    )
                departures = transit_cache[t_cache_key]

                for dep in departures:
                    wait_sec = dep["wait_seconds"]
                    eff_wait_sec = dep["effective_wait_seconds"]
                    delay_min = dep["delay_minutes"]
                    trip_id = dep["trip_id"]
                    direction = dep["direction"]
                    dest_stop = dep["destination_stop"]
                    veh_info = dep.get("vehicle_info")
                    is_live = dep.get("is_live", False)

                    downstream_all = dep["downstream_stops"]
                    for ds_idx, ds in enumerate(downstream_all):
                        to_ds_norm = ds["canonical_stop_name"]
                        ride_sec = ds["ride_seconds"]
                        arr_time_str = ds["departure_time_str"]

                        target_cand_stops = self.stops_by_norm_canonical.get(to_ds_norm, [])
                        if not target_cand_stops:
                            continue

                        # Smerovo správny výber stĺpika na výstupnej zastávke
                        prev_norm = downstream_all[ds_idx - 1]["canonical_stop_name"] if ds_idx > 0 else u_norm
                        prev_cands = self.stops_by_norm_canonical.get(prev_norm, [u_stop])
                        prev_pt = (
                            (float(prev_cands[0]["latitude"]), float(prev_cands[0]["longitude"]))
                            if prev_cands else (float(u_lat), float(u_lon))
                        )
                        next_pt = None
                        if ds_idx + 1 < len(downstream_all):
                            next_norm = downstream_all[ds_idx + 1]["canonical_stop_name"]
                            next_cands = self.stops_by_norm_canonical.get(next_norm, [])
                            if next_cands:
                                next_pt = (float(next_cands[0]["latitude"]), float(next_cands[0]["longitude"]))

                        matched_v_stop = self.select_directional_platform(
                            line, to_ds_norm, prev_pt, next_pt, fallback_stop=target_cand_stops[0]
                        ) or target_cand_stops[0]

                        v = matched_v_stop["stop_id"]
                        v_str = str(v)

                        if v == u or v_str == u_str or v in visited or v_str in visited:
                            continue

                        is_transfer = has_prior_transit and (mode != f"transit_{line}")
                        if direct_only and is_transfer:
                            continue
                        transfer_penalty = TRANSFER_PENALTY_SECONDS if is_transfer else 0

                        new_cost = cost_metric + eff_wait_sec + ride_sec + transfer_penalty
                        new_real_time = real_time_sec + eff_wait_sec + ride_sec

                        if new_cost >= best_cost.get(v, float("inf")) or new_cost >= best_cost.get(v_str, float("inf")):
                            continue

                        best_cost[v] = new_cost
                        best_cost[v_str] = new_cost
                        try:
                            best_cost[int(v)] = new_cost
                        except (ValueError, TypeError):
                            pass

                        v_lat = matched_v_stop.get("latitude")
                        v_lon = matched_v_stop.get("longitude")
                        dist_m = self.haversine_distance(u_lat, u_lon, v_lat, v_lon) if (v_lat is not None and v_lon is not None) else 0.0

                        # Presný podúsek zastávok (Sub-path) iba medzi nástupnou a výstupnou zastávkou z daného trip_id
                        sub_path_canonical = [u_norm] + [
                            s_item["canonical_stop_name"] for s_item in downstream_all[: ds_idx + 1]
                        ]
                        inter_stop_names = [
                            s_item["stop_name"] for s_item in downstream_all[:ds_idx] if s_item.get("stop_name")
                        ]

                        action = {
                            "type": "transit",
                            "line": line,
                            "from_id": u,
                            "to_id": v,
                            "distance_meters": round(dist_m, 1),
                            "wait_seconds": eff_wait_sec,
                            "planned_wait_seconds": wait_sec,
                            "wait_minutes": round(eff_wait_sec / 60.0, 1),
                            "ride_seconds": ride_sec,
                            "ride_minutes": round(ride_sec / 60.0, 1),
                            "departure_time_str": dep["departure_time_str"],
                            "arrival_time_str": arr_time_str,
                            "direction": direction,
                            "destination_stop": dest_stop,
                            "delay_minutes": delay_min,
                            "trip_id": trip_id,
                            "vehicle_info": veh_info,
                            "expected_timestamp": int(current_node_dt.timestamp()) + eff_wait_sec,
                            "is_live": is_live,
                            "sub_path_canonical": sub_path_canonical,
                            "intermediate_stops": inter_stop_names
                        }
                        counter += 1
                        heapq.heappush(
                            pq,
                            (new_cost, new_real_time, counter, v, f"transit_{line}", path + [action])
                        )

        return None, []

    def find_nearest_stop(self, lat: float, lon: float) -> Tuple[Dict[str, Any], float]:
        """
        Nájde najbližšiu fyzickú zastávku v Košiciach k zadaným GPS súradniciam.
        Vráti (stop_objekt, vzdialenost_v_metroch).
        """
        if not self.stops:
            raise ValueError("V databáze nie sú načítané žiadne zastávky.")

        best_stop = None
        best_dist = float("inf")
        for s in self.stops:
            lat_s = s.get("latitude")
            lon_s = s.get("longitude")
            if lat_s is not None and lon_s is not None:
                d = self.haversine_distance(lat, lon, float(lat_s), float(lon_s))
                if d < best_dist:
                    best_dist = d
                    best_stop = s

        if best_stop is None:
            raise ValueError("Nepodarilo sa nájsť žiadnu platnú zastávku v okolí zadaných súradníc.")

        return best_stop, best_dist

    def plan_journey(
        self,
        from_id: Optional[Union[int, str]] = None,
        to_id: Union[int, str] = None,
        from_coords: Optional[Tuple[float, float]] = None,
        departure_time_str: Optional[str] = None,
        direct_only: bool = False,
        time_type: str = "departure"
    ) -> Dict[str, Any]:
        """
        Vyhľadá optimálnu trasu a vygeneruje podrobný štruktúrovaný zoznam krokov
        (chôdza, čakanie na zastávke, jazda linkou, výstup) a segmenty trasy pre Leaflet mapu.
        Podporuje štart z konkrétneho stop_id/názvu aj zo surových GPS súradníc používateľa (from_coords=(lat, lon)).
        """
        to_stop = self.resolve_stop(to_id)
        if not to_stop:
            raise ValueError(f"Cieľová zastávka s ID/názvom '{to_id}' nebola nájdená.")
        to_canonical = self.get_canonical_name(to_stop)

        now_dt, is_future = self.parse_departure_time(departure_time_str)

        step_zero: Optional[Dict[str, Any]] = None
        step_zero_segment: Optional[Dict[str, Any]] = None
        walk_to_first_dist = 0.0
        walk_to_first_sec = 0
        walk_to_first_min = 0.0

        if from_coords is not None:
            origin_lat, origin_lon = from_coords
            nearest_stop, walk_to_first_dist = self.find_nearest_stop(origin_lat, origin_lon)
            walk_to_first_sec, walk_to_first_min = self.calculate_walking_time(walk_to_first_dist)
            nearest_canonical = self.get_canonical_name(nearest_stop)

            walk_coords = self.get_osrm_road_geometry(
                [{"latitude": origin_lat, "longitude": origin_lon}, nearest_stop],
                mode="foot"
            ) if walk_to_first_dist >= 35 else []
            if not walk_coords or len(walk_coords) < 2:
                walk_coords = [
                    [float(origin_lat), float(origin_lon)],
                    [float(nearest_stop["latitude"]), float(nearest_stop["longitude"])]
                ]

            from_stop = {
                "stop_id": "gps",
                "name": f"Moja poloha (pri {nearest_canonical})",
                "latitude": float(origin_lat),
                "longitude": float(origin_lon),
                "nearest_stop_name": nearest_canonical,
                "nearest_stop_id": nearest_stop["stop_id"]
            }

            step_zero = {
                "step_index": 0,
                "type": "walk_to_stop",
                "from_name": "Moja aktuálna poloha",
                "to_stop_id": nearest_stop["stop_id"],
                "to_stop_name": nearest_canonical,
                "duration_seconds": walk_to_first_sec,
                "duration_minutes": walk_to_first_min,
                "distance_meters": round(walk_to_first_dist, 1),
                "from_coords": [float(origin_lat), float(origin_lon)],
                "to_coords": [float(nearest_stop["latitude"]), float(nearest_stop["longitude"])],
                "polyline": walk_coords,
                "coords": walk_coords,
                "points_count": len(walk_coords),
                "instruction": f"Peší presun z aktuálnej polohy na zastávku {nearest_canonical} ({walk_to_first_dist:.0f} m, cca {walk_to_first_min} min)",
                "icon": "🚶"
            }

            step_zero_segment = {
                "type": "walk",
                "color": "#22c55e",
                "dash_array": "3, 6",
                "weight": 3,
                "coords": walk_coords,
                "points_count": len(walk_coords),
                "label": f"🚶 Peší presun z polohy na zastávku {nearest_canonical} ({walk_to_first_min} min)"
            }

            effective_from_id = nearest_stop["stop_id"]
            from_canonical = nearest_canonical
            search_start_dt = now_dt + timedelta(seconds=walk_to_first_sec)
        else:
            if from_id is None:
                raise ValueError("Musíte zadať buď počiatočnú zastávku (from_id) alebo GPS súradnice (from_coords).")
            from_stop = dict(self.resolve_stop(from_id) or {})
            if not from_stop:
                raise ValueError(f"Počiatočná zastávka s ID/názvom '{from_id}' nebola nájdená.")
            from_canonical = self.get_canonical_name(from_stop)
            effective_from_id = from_stop["stop_id"]
            search_start_dt = now_dt

        # Ak počiatočná a cieľová zastávka patria pod rovnaký super-uzol
        if from_coords is None and from_canonical == to_canonical:
            time_now_str = now_dt.strftime("%H:%M")
            return {
                "status": "ok",
                "message": f"Počiatočná a cieľová zastávka sú totožné ({to_canonical}).",
                "from_stop": {
                    "stop_id": from_stop["stop_id"],
                    "name": from_canonical,
                    "latitude": from_stop["latitude"],
                    "longitude": from_stop["longitude"]
                },
                "to_stop": {
                    "stop_id": to_stop["stop_id"],
                    "name": to_canonical,
                    "latitude": to_stop["latitude"],
                    "longitude": to_stop["longitude"]
                },
                "summary": {
                    "total_duration_seconds": 0,
                    "total_duration_minutes": 0,
                    "departure_time": time_now_str,
                    "arrival_time": time_now_str,
                    "total_distance_meters": 0,
                    "transfers_count": 0,
                    "walking_duration_minutes": 0,
                    "walking_distance_meters": 0,
                    "transit_duration_minutes": 0,
                    "lines_used": [],
                    "is_future": is_future,
                    "direct_only": direct_only,
                    "time_type": time_type
                },
                "steps": [
                    {
                        "step_index": 1,
                        "type": "arrival",
                        "stop_id": to_stop["stop_id"],
                        "stop_name": to_canonical,
                        "coords": [to_stop["latitude"], to_stop["longitude"]],
                        "instruction": f"Už sa nachádzate na cieľovej zastávke {to_canonical}.",
                        "icon": "🏁"
                    }
                ],
                "map_polyline_segments": []
            }

        # Ak používateľ kráča z GPS a najbližšia zastávka patrí pod cieľový uzol
        if from_coords is not None and from_canonical == to_canonical:
            time_now_str = now_dt.strftime("%H:%M")
            arr_time_str = (now_dt + timedelta(seconds=walk_to_first_sec)).strftime("%H:%M")
            return {
                "status": "ok",
                "from_stop": from_stop,
                "to_stop": {
                    "stop_id": to_stop["stop_id"],
                    "name": to_canonical,
                    "latitude": to_stop["latitude"],
                    "longitude": to_stop["longitude"]
                },
                "summary": {
                    "total_duration_seconds": walk_to_first_sec,
                    "total_duration_minutes": walk_to_first_min,
                    "departure_time": time_now_str,
                    "arrival_time": arr_time_str,
                    "total_distance_meters": round(walk_to_first_dist, 1),
                    "transfers_count": 0,
                    "walking_duration_minutes": walk_to_first_min,
                    "walking_distance_meters": round(walk_to_first_dist, 1),
                    "transit_duration_minutes": 0,
                    "lines_used": [],
                    "is_future": is_future,
                    "direct_only": direct_only,
                    "time_type": time_type
                },
                "steps": [
                    step_zero,
                    {
                        "step_index": 1,
                        "type": "arrival",
                        "stop_id": to_stop["stop_id"],
                        "stop_name": to_canonical,
                        "coords": [to_stop["latitude"], to_stop["longitude"]],
                        "instruction": f"Cieľová zastávka: {to_canonical}",
                        "icon": "🏁"
                    }
                ],
                "map_polyline_segments": [step_zero_segment] if step_zero_segment else []
            }

        # Prednačítanie reálnych odchodov zo štartovacieho super-uzla (pre všetky jeho nástupištia)
        start_platforms = self.stops_by_canonical_name.get(from_canonical, [from_stop])
        for sp in start_platforms:
            sp_id = sp.get("stop_id") if isinstance(sp, dict) else None
            if sp_id is not None:
                try:
                    self.get_stop_departures_cached(sp_id, search_start_dt, allow_network=True)
                except Exception:
                    pass

        cost_sec, path_actions = self.dijkstra_search(
            effective_from_id,
            to_stop["stop_id"],
            departure_dt=search_start_dt,
            direct_only=direct_only,
            is_future=is_future
        )

        if cost_sec is None or not path_actions:
            return {
                "status": "not_found",
                "message": f"Nenašlo sa žiadne spojenie medzi {from_canonical} a {to_canonical}.",
                "from_stop": from_stop,
                "to_stop": to_stop,
                "journeys": [],
                "steps": [],
                "map_polyline_segments": []
            }

        steps: List[Dict[str, Any]] = []
        map_segments: List[Dict[str, Any]] = []

        total_walk_sec = walk_to_first_sec
        total_walk_meters = walk_to_first_dist
        total_ride_sec = 0
        lines_used = []
        current_time_dt = search_start_dt
        step_idx = 1

        if step_zero is not None:
            steps.append(step_zero)
            if step_zero_segment:
                map_segments.append(step_zero_segment)

        final_reached_platform = dict(to_stop)
        has_updated_origin_pin = (from_coords is not None)
        last_alight_coords: Optional[List[float]] = None

        for act in path_actions:
            if act["type"] == "walk":
                # Nulový presun medzi stĺpikmi v rámci rovnakého uzla ignorujeme ako samostatný peší krok
                if act.get("is_platform_transfer") or act.get("duration_seconds", 0) == 0:
                    final_reached_platform = dict(self.stops_by_id.get(act["to_id"], final_reached_platform))
                    continue

                u_s = dict(self.stops_by_id[act["from_id"]])
                v_s = dict(self.stops_by_id[act["to_id"]])
                if last_alight_coords is not None:
                    u_s["latitude"], u_s["longitude"] = last_alight_coords[0], last_alight_coords[1]

                final_reached_platform = dict(v_s)
                w_sec = act["duration_seconds"]
                w_min = round(w_sec / 60.0, 1)
                dist_m = act["distance_meters"]

                total_walk_sec += w_sec
                total_walk_meters += dist_m
                current_time_dt += timedelta(seconds=w_sec)

                walk_coords = self.get_osrm_road_geometry([u_s, v_s], mode="foot") if dist_m >= 35 else []
                if not walk_coords or len(walk_coords) < 2:
                    walk_coords = [
                        [float(u_s["latitude"]), float(u_s["longitude"])],
                        [float(v_s["latitude"]), float(v_s["longitude"])]
                    ]
                coords = walk_coords

                if not has_updated_origin_pin:
                    from_stop["stop_id"] = u_s["stop_id"]
                    from_stop["latitude"], from_stop["longitude"] = coords[0][0], coords[0][1]
                    has_updated_origin_pin = True

                u_canon = self.get_canonical_name(u_s)
                v_canon = self.get_canonical_name(v_s)

                steps.append({
                    "step_index": step_idx,
                    "type": "walk",
                    "from_stop_id": u_s["stop_id"],
                    "from_stop_name": u_canon,
                    "to_stop_id": v_s["stop_id"],
                    "to_stop_name": v_canon,
                    "duration_seconds": w_sec,
                    "duration_minutes": w_min,
                    "distance_meters": dist_m,
                    "from_coords": coords[0],
                    "to_coords": coords[-1],
                    "polyline": coords,
                    "coords": coords,
                    "points_count": len(coords),
                    "instruction": f"Kráčaj pešo {w_min} min na zastávku {v_canon} ({dist_m:.0f} m)",
                    "icon": "🚶"
                })
                step_idx += 1

                map_segments.append({
                    "type": "walk",
                    "color": "#22c55e",
                    "dash_array": "3, 6",
                    "weight": 3,
                    "coords": coords,
                    "points_count": len(coords),
                    "label": f"🚶 Pešo {w_min} min ({dist_m:.0f} m)"
                })

            elif act["type"] == "transit":
                line = act["line"]
                if line not in lines_used:
                    lines_used.append(line)

                u_s = dict(self.stops_by_id[act["from_id"]])
                v_s = dict(self.stops_by_id[act["to_id"]])

                wait_sec = act.get("wait_seconds", 180)
                wait_min = act.get("wait_minutes", round(wait_sec / 60.0, 1))
                delay_min = 0 if is_future else act.get("delay_minutes", 0)
                veh_info = None if is_future else act.get("vehicle_info")
                trip_id = act.get("trip_id")

                if not act.get("is_live") and not trip_id:
                    try:
                        fresh_wait = self.calculate_transit_edge_wait(
                            u_s["stop_id"], line, current_time_dt, allow_network=True, is_future=is_future
                        )
                        if fresh_wait.get("wait_seconds") is not None and fresh_wait["wait_seconds"] < 7200:
                            wait_sec = fresh_wait["wait_seconds"]
                            wait_min = fresh_wait["wait_minutes"]
                            delay_min = 0 if is_future else fresh_wait["delay_minutes"]
                            veh_info = None if is_future else (fresh_wait.get("vehicle_info") or veh_info)
                            trip_id = fresh_wait.get("trip_id") or trip_id
                    except Exception:
                        pass

                # Najprv vypočítame presnú smerovú geometriu a stĺpiky (Pravidlá 1-4),
                # aby oranžový bod čakania/nástupu, začiatok čiary a prípadný predchádzajúci peší presun
                # ležali na 100 % identickej súradnici!
                polyline_coords, intermediate_names, u_dir_stop, v_dir_stop = self.get_transit_segment_geometry(
                    line,
                    u_s,
                    v_s,
                    trip_id=trip_id,
                    sub_path_canonical=act.get("sub_path_canonical"),
                    intermediate_stops=act.get("intermediate_stops"),
                    return_directional_stops=True
                )

                u_s = u_dir_stop
                v_s = v_dir_stop
                final_reached_platform = dict(v_s)

                board_coords = (
                    [float(polyline_coords[0][0]), float(polyline_coords[0][1])]
                    if polyline_coords else [float(u_s["latitude"]), float(u_s["longitude"])]
                )
                alight_coords = (
                    [float(polyline_coords[-1][0]), float(polyline_coords[-1][1])]
                    if polyline_coords else [float(v_s["latitude"]), float(v_s["longitude"])]
                )
                last_alight_coords = alight_coords

                # Ak je toto prvý krok trasy, ukotvíme štartovací bod presne na začiatok čiary
                if not has_updated_origin_pin:
                    from_stop["stop_id"] = u_s["stop_id"]
                    from_stop["latitude"], from_stop["longitude"] = board_coords[0], board_coords[1]
                    has_updated_origin_pin = True

                # Ak pred týmto nástupom predchádzal peší presun, napojíme jeho koniec presne na nástupný stĺpik
                if steps and steps[-1]["type"] in ("walk", "walk_to_stop"):
                    prev_w = steps[-1]
                    prev_w["to_stop_id"] = u_s["stop_id"]
                    prev_w["to_coords"] = board_coords
                    if prev_w.get("coords") and len(prev_w["coords"]) >= 2:
                        if self.haversine_distance(
                            prev_w["coords"][-1][0], prev_w["coords"][-1][1],
                            board_coords[0], board_coords[1]
                        ) <= 180.0:
                            prev_w["coords"][-1] = list(board_coords)
                            prev_w["polyline"] = prev_w["coords"]
                            if map_segments and map_segments[-1]["type"] == "walk":
                                map_segments[-1]["coords"] = prev_w["coords"]

                u_canon = self.get_canonical_name(u_s)
                v_canon = self.get_canonical_name(v_s)
                dep_time_str = act.get("departure_time_str")
                arr_time_str = act.get("arrival_time_str")

                if dep_time_str:
                    wait_instr = f"Počkaj na linku {line} na zastávke {u_canon} (odchod {dep_time_str}, čakacia doba cca {wait_min} min"
                else:
                    wait_instr = f"Počkaj na linku {line} na zastávke {u_canon} (čakacia doba cca {wait_min} min"

                if not is_future and delay_min > 0:
                    wait_instr += f", meškanie +{delay_min} min"
                if not is_future and veh_info:
                    wait_instr += f", {veh_info}"
                wait_instr += ")"

                steps.append({
                    "step_index": step_idx,
                    "type": "wait",
                    "line": line,
                    "stop_id": u_s["stop_id"],
                    "stop_name": u_canon,
                    "coords": board_coords,
                    "wait_seconds": wait_sec,
                    "wait_minutes": wait_min,
                    "delay_minutes": delay_min,
                    "vehicle_info": veh_info,
                    "trip_id": trip_id,
                    "departure_time_str": dep_time_str,
                    "instruction": wait_instr,
                    "icon": "⏳"
                })
                step_idx += 1
                current_time_dt += timedelta(seconds=wait_sec)

                ride_sec = max(60, int(act.get("ride_seconds", 60)))
                ride_min = max(1.0, round(ride_sec / 60.0, 1))
                dist_m = act.get("distance_meters", 0.0)
                total_ride_sec += ride_sec
                current_time_dt += timedelta(seconds=ride_sec)

                if intermediate_names is not None:
                    stops_count = max(1, len(intermediate_names) + 1)
                else:
                    stops_count = max(1, round(ride_min / 1.9))
                stops_count_str = f" ({stops_count} zastávok, cca {ride_min} min)"
                steps.append({
                    "step_index": step_idx,
                    "type": "ride",
                    "line": line,
                    "from_stop_id": u_s["stop_id"],
                    "from_stop_name": u_canon,
                    "to_stop_id": v_s["stop_id"],
                    "to_stop_name": v_canon,
                    "duration_seconds": ride_sec,
                    "duration_minutes": ride_min,
                    "distance_meters": dist_m,
                    "stops_count": stops_count,
                    "intermediate_stops": intermediate_names,
                    "departure_time_str": dep_time_str,
                    "arrival_time_str": arr_time_str,
                    "direction": act.get("direction"),
                    "destination_stop": act.get("destination_stop"),
                    "from_coords": board_coords,
                    "to_coords": alight_coords,
                    "polyline": polyline_coords,
                    "coords": polyline_coords,
                    "points_count": len(polyline_coords),
                    "instruction": f"Nastúp na linku {line} a cestuj na zastávku {v_canon}{stops_count_str}",
                    "icon": "🚌"
                })
                step_idx += 1

                steps.append({
                    "step_index": step_idx,
                    "type": "alight",
                    "line": line,
                    "stop_id": v_s["stop_id"],
                    "stop_name": v_canon,
                    "coords": alight_coords,
                    "instruction": f"Vystúp na zastávke {v_canon}",
                    "icon": "🚪"
                })
                step_idx += 1

                map_segments.append({
                    "type": "transit",
                    "line": line,
                    "color": "#d946ef",
                    "weight": 4.5,
                    "coords": polyline_coords,
                    "points_count": len(polyline_coords),
                    "label": f"🚌 Linka {line} ({ride_min} min)"
                })

        final_coords = [float(final_reached_platform["latitude"]), float(final_reached_platform["longitude"])]
        if map_segments and map_segments[-1].get("coords"):
            final_coords = list(map_segments[-1]["coords"][-1])
            final_reached_platform["latitude"], final_reached_platform["longitude"] = final_coords[0], final_coords[1]

        steps.append({
            "step_index": step_idx,
            "type": "arrival",
            "stop_id": final_reached_platform["stop_id"],
            "stop_name": to_canonical,
            "coords": final_coords,
            "instruction": f"Cieľová zastávka: {to_canonical}",
            "icon": "🏁"
        })

        total_duration_sec = int((current_time_dt - now_dt).total_seconds())
        if total_duration_sec < 60:
            total_duration_sec = max(60, sum(s.get("duration_seconds", 0) for s in steps) + sum(s.get("wait_seconds", 0) for s in steps))
        total_duration_min = max(1.0, round(total_duration_sec / 60.0, 1))
        transfers_count = max(0, len(lines_used) - 1)

        summary = {
            "total_duration_seconds": total_duration_sec,
            "total_duration_minutes": total_duration_min,
            "departure_time": now_dt.strftime("%H:%M"),
            "arrival_time": current_time_dt.strftime("%H:%M"),
            "total_distance_meters": round(total_walk_meters + sum(a.get("distance_meters", 0) for a in path_actions if a["type"] == "transit"), 1),
            "transfers_count": transfers_count,
            "walking_duration_minutes": round(total_walk_sec / 60.0, 1),
            "walking_distance_meters": round(total_walk_meters, 1),
            "transit_duration_minutes": round(total_ride_sec / 60.0, 1),
            "lines_used": lines_used,
            "is_future": is_future,
            "direct_only": direct_only,
            "time_type": time_type
        }

        return {
            "status": "ok",
            "from_stop": {
                "stop_id": from_stop["stop_id"],
                "name": from_canonical if from_coords is None else from_stop.get("name"),
                "latitude": from_stop["latitude"],
                "longitude": from_stop["longitude"]
            },
            "to_stop": {
                "stop_id": final_reached_platform["stop_id"],
                "name": to_canonical,
                "latitude": final_reached_platform["latitude"],
                "longitude": final_reached_platform["longitude"]
            },
            "summary": summary,
            "steps": steps,
            "map_polyline_segments": map_segments
        }

    def plan_multiple_journeys(
        self,
        from_id: Optional[Union[int, str]] = None,
        to_id: Union[int, str] = None,
        from_coords: Optional[Tuple[float, float]] = None,
        departure_time_str: Optional[str] = None,
        direct_only: bool = False,
        time_type: str = "departure",
        target_count: int = 6
    ) -> Dict[str, Any]:
        """
        Vyhľadá primárnu najrýchlejšiu trasu a automaticky dopočíta ďalšie nasledujúce spojenia.
        Podporuje:
        - departure_time_str: "now", "HH:MM", alebo ISO dátum a čas
        - direct_only=True: vyradí trasy vyžadujúce prestup a vráti len priame spojenia
        - time_type: 'departure' (odchod o...) alebo 'arrival' (príchod do...)
        """
        def get_departure_clock(j: Dict[str, Any], search_clock_str: str) -> str:
            # Zistí reálny čas nástupu na prvý spoj
            try:
                if ":" in search_clock_str:
                    time_part = search_clock_str.split("T")[-1]
                    parts = time_part.split(":")
                    base_dt = datetime.now().replace(hour=int(parts[0]), minute=int(parts[1]), second=0, microsecond=0)
                else:
                    base_dt = datetime.now()
            except Exception:
                base_dt = datetime.now()

            elapsed = 0
            for st in j.get("steps", []):
                if st.get("type") in ("walk", "walk_to_stop"):
                    elapsed += st.get("duration_seconds", 0)
                elif st.get("type") == "wait":
                    elapsed += st.get("wait_seconds", 0)
                    return (base_dt + timedelta(seconds=elapsed)).strftime("%H:%M")
                elif st.get("type") == "ride":
                    return (base_dt + timedelta(seconds=elapsed)).strftime("%H:%M")

            return j.get("summary", {}).get("departure_time") or search_clock_str[-5:]

        base_dt, is_future = self.parse_departure_time(departure_time_str)

        # REŽIM 1: PRÍCHOD DO (time_type == "arrival")
        if time_type == "arrival":
            target_arrival_dt = base_dt
            cand_offsets = [15, 25, 35, 45, 60, 75, 90, 105, 120]
            valid_arrival_journeys = []
            seen_signatures = set()

            for offset_min in cand_offsets:
                test_dt = target_arrival_dt - timedelta(minutes=offset_min)
                try:
                    cand = self.plan_journey(
                        from_id=from_id,
                        to_id=to_id,
                        from_coords=from_coords,
                        departure_time_str=test_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                        direct_only=direct_only,
                        time_type=time_type
                    )
                except Exception:
                    continue

                if cand.get("status") != "ok":
                    continue

                c_sum = cand.get("summary", {})
                if direct_only and (c_sum.get("transfers_count", 0) > 0 or len(c_sum.get("lines_used", [])) > 1):
                    continue

                arr_str = c_sum.get("arrival_time")
                if not arr_str:
                    continue

                try:
                    arr_h, arr_m = [int(p) for p in arr_str.split(":")[:2]]
                    arr_dt = test_dt.replace(hour=arr_h, minute=arr_m, second=0, microsecond=0)
                    if arr_dt < test_dt:
                        arr_dt += timedelta(days=1)
                except Exception:
                    continue

                # Spoj musí doraziť do cieľa najneskôr v požadovanom čase (tolerancia +1 min)
                if arr_dt <= target_arrival_dt + timedelta(minutes=1):
                    board_clock = get_departure_clock(cand, test_dt.strftime("%H:%M"))
                    sig = (board_clock, arr_str, tuple(c_sum.get("lines_used", [])))
                    if sig not in seen_signatures:
                        seen_signatures.add(sig)
                        cand["summary"]["board_time"] = board_clock
                        diff_sec = (target_arrival_dt - arr_dt).total_seconds()
                        valid_arrival_journeys.append((diff_sec, cand))

            if valid_arrival_journeys:
                # Zoradíme podľa najmenšieho rozdielu voči cieľovému času príchodu
                valid_arrival_journeys.sort(key=lambda x: x[0])
                journeys = [item[1] for item in valid_arrival_journeys[:target_count]]
                for idx, j in enumerate(journeys):
                    j["journey_index"] = idx
                return {
                    "status": "ok",
                    "total_journeys": len(journeys),
                    "journeys": journeys,
                    "from_stop": journeys[0]["from_stop"],
                    "to_stop": journeys[0]["to_stop"],
                    "summary": journeys[0]["summary"],
                    "steps": journeys[0]["steps"],
                    "map_polyline_segments": journeys[0]["map_polyline_segments"]
                }

        # REŽIM 2: ODCHOD O / TERAZ (alebo fallback pre arrival)
        primary = self.plan_journey(
            from_id=from_id,
            to_id=to_id,
            from_coords=from_coords,
            departure_time_str=base_dt.strftime("%Y-%m-%dT%H:%M:%S") if is_future else departure_time_str,
            direct_only=direct_only,
            time_type=time_type
        )

        if primary.get("status") != "ok":
            return {
                "status": primary.get("status", "not_found"),
                "message": primary.get("message", "Nenašlo sa žiadne spojenie."),
                "from_stop": primary.get("from_stop"),
                "to_stop": primary.get("to_stop"),
                "journeys": [],
                "steps": [],
                "map_polyline_segments": []
            }

        if direct_only and (primary.get("summary", {}).get("transfers_count", 0) > 0 or len(primary.get("summary", {}).get("lines_used", [])) > 1):
            return {
                "status": "not_found",
                "message": "Nenašlo sa žiadne priame spojenie bez prestupu medzi vybranými zastávkami.",
                "from_stop": primary.get("from_stop"),
                "to_stop": primary.get("to_stop"),
                "journeys": [],
                "steps": [],
                "map_polyline_segments": []
            }

        # Ak sú zastávky totožné alebo ide o rýdzo peší presun bez MHD, nie je čo posúvať
        if not primary.get("summary", {}).get("lines_used"):
            primary["journey_index"] = 0
            return {
                "status": "ok",
                "total_journeys": 1,
                "journeys": [primary],
                "from_stop": primary.get("from_stop"),
                "to_stop": primary.get("to_stop"),
                "summary": primary.get("summary"),
                "steps": primary.get("steps", []),
                "map_polyline_segments": primary.get("map_polyline_segments", [])
            }

        journeys = []
        primary["journey_index"] = 0
        board_time = get_departure_clock(primary, base_dt.strftime("%H:%M"))
        primary["summary"]["board_time"] = board_time
        journeys.append(primary)

        seen_signatures = {
            (board_time, primary["summary"].get("arrival_time"), tuple(primary["summary"].get("lines_used", [])))
        }

        # Posunieme čas hľadania: čas odchodu predchádzajúcej trasy + 1 minúta (so zachovaním dátumu)
        try:
            b_h, b_m = [int(p) for p in board_time.split(":")[:2]]
            curr_dt = base_dt.replace(hour=b_h, minute=b_m, second=0, microsecond=0) + timedelta(minutes=1)
            if curr_dt < base_dt:
                curr_dt += timedelta(days=1)
        except Exception:
            curr_dt = base_dt + timedelta(minutes=1)

        attempts = 0
        max_attempts = target_count * 3
        consecutive_fails = 0

        while len(journeys) < target_count and attempts < max_attempts:
            attempts += 1
            curr_iso_str = curr_dt.strftime("%Y-%m-%dT%H:%M:%S")

            try:
                alt = self.plan_journey(
                    from_id=from_id,
                    to_id=to_id,
                    from_coords=from_coords,
                    departure_time_str=curr_iso_str,
                    direct_only=direct_only,
                    time_type=time_type
                )
            except Exception:
                consecutive_fails += 1
                if consecutive_fails >= 2:
                    break
                curr_dt += timedelta(minutes=5)
                continue

            if alt.get("status") != "ok":
                consecutive_fails += 1
                if consecutive_fails >= 2:
                    break
                curr_dt += timedelta(minutes=5)
                continue

            if direct_only and (alt.get("summary", {}).get("transfers_count", 0) > 0 or len(alt.get("summary", {}).get("lines_used", [])) > 1):
                curr_dt += timedelta(minutes=5)
                continue

            consecutive_fails = 0

            alt_board = get_departure_clock(alt, curr_dt.strftime("%H:%M"))
            sig = (alt_board, alt["summary"].get("arrival_time"), tuple(alt["summary"].get("lines_used", [])))

            if sig not in seen_signatures:
                seen_signatures.add(sig)
                alt["journey_index"] = len(journeys)
                alt["summary"]["board_time"] = alt_board
                journeys.append(alt)
                # Ďalšie hľadanie: odchod tohto spoja + 1 minúta (s korektným posunom cez polnoc)
                try:
                    ab_h, ab_m = [int(p) for p in alt_board.split(":")[:2]]
                    next_dt = curr_dt.replace(hour=ab_h, minute=ab_m, second=0, microsecond=0) + timedelta(minutes=1)
                    if next_dt < curr_dt:
                        next_dt += timedelta(days=1)
                    curr_dt = next_dt
                except Exception:
                    curr_dt += timedelta(minutes=3)
            else:
                curr_dt += timedelta(minutes=2)

        return {
            "status": "ok",
            "total_journeys": len(journeys),
            "journeys": journeys,
            "from_stop": journeys[0]["from_stop"],
            "to_stop": journeys[0]["to_stop"],
            "summary": journeys[0]["summary"],
            "steps": journeys[0]["steps"],
            "map_polyline_segments": journeys[0]["map_polyline_segments"]
        }


def run_walking_graph_builder():
    """Spustí výpočet a vypíše podrobnú správu do konzoly."""
    print("=" * 70)
    print("   MHD KOŠICE - VYHĽADÁVAČ TRÁS (JOURNEY PLANNER): PEŠÍ GRAF   ")
    print("=" * 70)

    engine = RoutingEngine()
    print(f"[*] Načítaných {len(engine.stops)} platných zastávok z kosice_stops.json.")
    print(f"[*] Rýchlosť chôdze: {engine.walking_speed_kmh} km/h (1 km trvá 12 minút).")
    print(f"[*] Prahová vzdialenosť: menej ako {engine.max_transfer_distance_m:.0f} metrov.")
    print("[*] Prepočítavam vzdušné vzdialenosti medzi všetkými zastávkami navzájom...")

    result = engine.build_walking_graph()

    meta = result["metadata"]
    transfers = result["transfers"]

    print("\n--- VÝSLEDKY VÝPOČTU PEŠIEHO GRAFU ---")
    print(f" • Celkový počet peších skratiek (orientované hrany):  {meta['total_transfers_directed']}")
    print(f" • Počet unikátnych dvojíc prepojených zastávok:       {meta['total_stop_pairs_undirected']}")
    print(f" • Najkratšia pešia spojka:                          {meta['distance_stats_meters']['min']} m ({int(round(meta['distance_stats_meters']['min'] * 0.72))} s)")
    print(f" • Priemerná vzdialenosť pešieho prestupu:           {meta['distance_stats_meters']['avg']} m ({round(meta['distance_stats_meters']['avg'] * 0.72 / 60, 1)} min)")
    print(f" • Maximálna vzdialenosť pešieho prestupu:           {meta['distance_stats_meters']['max']} m ({round(meta['distance_stats_meters']['max'] * 0.72 / 60, 1)} min)")
    print(f" • Výsledný súbor uložený do:                         data/walking_transfers.json")

    # Ukážka najrýchlejších prestupov (rôzne nástupištia a križovatky)
    print("\n--- UKÁŽKA NAJBLIŽŠÍCH PEŠÍCH PRESTUPOV (< 100 m) ---")
    closest = sorted(transfers, key=lambda t: t["distance_meters"])[:8]
    for c in closest:
        print(f" • {c['from_stop_name']} → {c['to_stop_name']}: {c['distance_meters']} m (pešo {c['walk_time_seconds']} s / {c['walk_time_minutes']} min)")

    # Ukážka prestupov v kľúčových uzloch (Námestie osloboditeľov, Staničné námestie)
    key_hubs = ["Námestie osloboditeľov", "Staničné námestie", "Amfiteáter", "Spoločenský pavilón"]
    print("\n--- PRESTUPNÉ MOŽNOSTI V KĽÚČOVÝCH UZLOCH ---")
    for hub_name in key_hubs:
        hub_stops = engine.stops_by_name.get(hub_name, [])
        if hub_stops:
            s_id = hub_stops[0]["stop_id"]
            transfers_from_hub = engine.get_transfers_from_stop(s_id)
            print(f" • Zastávka '{hub_name}': {len(transfers_from_hub)} peších spojení do 500 m")
            for t in transfers_from_hub[:3]:
                print(f"    - do {t['to_stop_name']}: {t['distance_meters']} m ({t['walk_time_minutes']} min)")

    print("=" * 70)
    return result


if __name__ == "__main__":
    run_walking_graph_builder()
