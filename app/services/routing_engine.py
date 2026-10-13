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

        self.stops: List[Dict[str, Any]] = []
        self.stops_by_id: Dict[Any, Dict[str, Any]] = {}
        self.stops_by_name: Dict[str, List[Dict[str, Any]]] = {}
        self.stops_by_canonical_name: Dict[str, List[Dict[str, Any]]] = {}
        self.lines_to_stops: Dict[str, List[Any]] = {}

        self.walking_graph: Optional[Dict[str, Any]] = None
        self.adjacency_list: Dict[Any, List[Dict[str, Any]]] = {}

        # Vyrovnávacia pamäť pre reálnu geometriu ciest (shape polyline) a detaily jázd
        self._trip_details_cache: Dict[int, Dict[str, Any]] = {}
        self._route_geometry_cache: Dict[Any, Tuple[List[List[float]], List[str]]] = {}
        self._osrm_cache: Dict[str, List[List[float]]] = {}
        self._stop_departures_cache: Dict[Any, List[Dict[str, Any]]] = {}

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
            parent_id = s.get("parent_stop_id")
            if parent_id is not None:
                if parent_id not in self.stops_by_id:
                    self.stops_by_id[parent_id] = s
                if str(parent_id) not in self.stops_by_id:
                    self.stops_by_id[str(parent_id)] = s

        self.stops_by_name = {}
        self.stops_by_canonical_name = {}
        self.lines_to_stops = {}

        for s in self.stops:
            raw_name = s.get("name", "")
            self.stops_by_name.setdefault(raw_name, []).append(s)
            cname = self.get_canonical_name(s)
            self.stops_by_canonical_name.setdefault(cname, []).append(s)
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

    def get_osrm_road_geometry(
        self,
        waypoint_stops: List[Dict[str, Any]],
        mode: str = "driving"
    ) -> List[List[float]]:
        """
        Získa detailnú geometriu ulíc (stovky bodov) pomocou OSRM routingu pozdĺž zadaných zastávok.
        mode: 'driving' (pre MHD trasy) alebo 'foot' (pre pešie presuny po chodníkoch).
        """
        if not waypoint_stops or len(waypoint_stops) < 2:
            return []

        # Obmedzíme počet prechodných bodov na max 12 (pre stabilitu a rýchlosť OSRM API)
        if len(waypoint_stops) > 12:
            step = (len(waypoint_stops) - 1) / 10.0
            sampled = [waypoint_stops[0]]
            for i in range(1, 10):
                idx = int(round(i * step))
                if 0 < idx < len(waypoint_stops) - 1 and waypoint_stops[idx] not in sampled:
                    sampled.append(waypoint_stops[idx])
            sampled.append(waypoint_stops[-1])
            stops_to_route = sampled
        else:
            stops_to_route = waypoint_stops

        coords_param = ";".join(
            f"{float(s['longitude']):.6f},{float(s['latitude']):.6f}"
            for s in stops_to_route
        )

        cache_key = f"osrm_{mode}_{coords_param}"
        if cache_key in self._osrm_cache:
            return self._osrm_cache[cache_key]

        url = f"https://router.project-osrm.org/route/v1/{mode}/{coords_param}?overview=full&geometries=geojson"
        req = urllib.request.Request(url, headers={"User-Agent": "MHD-Kosice-Routing/2.0"})

        try:
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("code") == "Ok" and data.get("routes"):
                    geojson_coords = data["routes"][0]["geometry"]["coordinates"]
                    # GeoJSON má [lon, lat], Leaflet vyžaduje [lat, lon]
                    leaflet_coords = [[float(c[1]), float(c[0])] for c in geojson_coords]
                    if len(leaflet_coords) >= 2:
                        self._osrm_cache[cache_key] = leaflet_coords
                        return leaflet_coords
        except Exception:
            pass

        return [[float(s["latitude"]), float(s["longitude"])] for s in waypoint_stops]

    def get_transit_segment_geometry(
        self,
        line: str,
        u_stop: Dict[str, Any],
        v_stop: Dict[str, Any],
        trip_id: Optional[int] = None
    ) -> Tuple[List[List[float]], List[str]]:
        """
        Získa reálnu geometriu ulíc (shape polyline z modelRoutePoints alebo OSRM routing) a zoznam nácestných zastávok
        pre úsek jazdy linkou 'line' medzi nástupnou (u_stop) a výstupnou (v_stop) zastávkou.
        Využíva Ubian modelRoutePoints a ako spoľahlivý fallback OSRM routing, čím garantuje stovky detailných bodov.
        """
        u_id = u_stop["stop_id"]
        v_id = v_stop["stop_id"]
        cache_key = (str(line), u_id, v_id, trip_id or 0)
        if cache_key in self._route_geometry_cache:
            return self._route_geometry_cache[cache_key]

        u_pt = [float(u_stop["latitude"]), float(u_stop["longitude"])]
        v_pt = [float(v_stop["latitude"]), float(v_stop["longitude"])]
        u_name_clean = strip_accents(u_stop.get("name", "")).lower().strip()
        v_name_clean = strip_accents(v_stop.get("name", "")).lower().strip()

        # 1. Zozbieranie kandidátnych jázd (trip_id) pre danú linku z Ubianu
        candidate_trip_ids: List[int] = []
        if trip_id and trip_id not in candidate_trip_ids:
            candidate_trip_ids.append(trip_id)

        if self.live_feed:
            # A. Zo živých vozidiel v premávke
            try:
                live_vehicles = self.get_live_vehicles_cached() or []
                for veh in live_vehicles:
                    if str(veh.get("line")) == str(line) and veh.get("trip_id"):
                        tid = veh["trip_id"]
                        if tid not in candidate_trip_ids:
                            candidate_trip_ids.append(tid)
            except Exception:
                pass

            # B. Z odchodov na nástupnej zastávke u_stop
            try:
                cached_deps = self.get_stop_departures_cached(u_id, datetime.now(), allow_network=False) or []
                for dep in cached_deps:
                    if str(dep.get("line")) == str(line) and dep.get("trip_id"):
                        tid = dep["trip_id"]
                        if tid not in candidate_trip_ids:
                            candidate_trip_ids.append(tid)
            except Exception:
                pass

        # 2. Hľadanie jazdy v správnom smere (u_idx < v_idx) a extrakcia modelRoutePoints
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

            # Nájdenie indexu nástupnej zastávky (u) a výstupnej zastávky (v)
            u_idx = None
            v_idx = None

            for i, st in enumerate(trip_stops):
                st_id = st.get("stopID")
                st_name_clean = strip_accents(st.get("stopName", "")).lower().strip()

                if u_idx is None:
                    if st_id == u_id or (u_name_clean and st_name_clean == u_name_clean):
                        u_idx = i
                        continue
                    if st.get("latitude") and st.get("longitude"):
                        if self.haversine_distance(st["latitude"], st["longitude"], u_pt[0], u_pt[1]) < 90:
                            u_idx = i
                            continue

                if u_idx is not None and v_idx is None:
                    if st_id == v_id or (v_name_clean and st_name_clean == v_name_clean):
                        v_idx = i
                        break
                    if st.get("latitude") and st.get("longitude"):
                        if self.haversine_distance(st["latitude"], st["longitude"], v_pt[0], v_pt[1]) < 90:
                            v_idx = i
                            break

            # Ak sme našli jazdu v správnom smere
            if u_idx is not None and v_idx is not None and u_idx < v_idx:
                sub_stops = trip_stops[u_idx : v_idx + 1]
                raw_names = [s.get("stopName") for s in sub_stops[1:-1] if s.get("stopName")]
                seen_n = set()
                intermediate_names = []
                for sn in raw_names:
                    cn = strip_accents(sn).lower().strip()
                    if cn and cn not in seen_n:
                        seen_n.add(cn)
                        intermediate_names.append(sn)

                u_order = sub_stops[0].get("stopOrder")
                v_order = sub_stops[-1].get("stopOrder")

                route_segs = trip_data.get("route") or []
                matching_segs = []

                if u_order is not None and v_order is not None:
                    matching_segs = [s for s in route_segs if u_order <= s.get("tripStopOrder", 0) < v_order]
                if not matching_segs:
                    matching_segs = route_segs[u_idx:v_idx]

                # Extrakcia detailných modelRoutePoints pozdĺž ulíc
                road_coords: List[List[float]] = []
                for seg in matching_segs:
                    for pt in seg.get("modelRoutePoints") or []:
                        lat = pt.get("latitude")
                        lng = pt.get("longitude")
                        if lat is not None and lng is not None:
                            lat_f = float(lat)
                            lng_f = float(lng)
                            if not road_coords or (
                                abs(road_coords[-1][0] - lat_f) > 1e-6 or
                                abs(road_coords[-1][1] - lng_f) > 1e-6
                            ):
                                road_coords.append([lat_f, lng_f])

                if len(road_coords) >= 2:
                    if abs(road_coords[0][0] - u_pt[0]) > 0.0001 or abs(road_coords[0][1] - u_pt[1]) > 0.0001:
                        road_coords.insert(0, u_pt)
                    if abs(road_coords[-1][0] - v_pt[0]) > 0.0001 or abs(road_coords[-1][1] - v_pt[1]) > 0.0001:
                        road_coords.append(v_pt)

                    self._route_geometry_cache[cache_key] = (road_coords, intermediate_names)
                    return road_coords, intermediate_names

        # 3. ROBUSTNÝ FALLBACK: OSRM Routing (garantuje reálnu geometriu ulíc po cestách)
        corridor = []
        try:
            corridor = self.get_corridor_stops(line, u_stop, v_stop)
        except Exception:
            corridor = [u_stop, v_stop]

        raw_inter = [s.get("name") for s in corridor[1:-1] if s.get("name")] if corridor else []
        seen_ci = set()
        inter_names = []
        for iname in raw_inter:
            c_iname = self.get_canonical_name({"name": iname}) if isinstance(iname, str) else str(iname)
            if c_iname not in seen_ci:
                seen_ci.add(c_iname)
                inter_names.append(iname)

        waypoints = corridor if (corridor and len(corridor) >= 2) else [u_stop, v_stop]

        osrm_road = self.get_osrm_road_geometry(waypoints, mode="driving")
        if len(osrm_road) >= 2:
            self._route_geometry_cache[cache_key] = (osrm_road, inter_names)
            return osrm_road, inter_names

        # Záložný plán pri úplnej nedostupnosti internetu
        fallback_coords = [[float(s["latitude"]), float(s["longitude"])] for s in waypoints]
        self._route_geometry_cache[cache_key] = (fallback_coords, inter_names)
        return fallback_coords, inter_names

    def get_corridor_stops(
        self,
        line: str,
        u_stop: Dict[str, Any],
        v_stop: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Nájde a zoradí všetky zastávky na linke 'line' ležiace pozdĺž koridoru
        medzi počiatočnou (u_stop) a cieľovou (v_stop) zastávkou s deduplikáciou nástupíšť.
        """
        du = (v_stop["latitude"] - u_stop["latitude"], v_stop["longitude"] - u_stop["longitude"])
        mag_sq = du[0] ** 2 + du[1] ** 2
        if mag_sq < 1e-10:
            return [u_stop, v_stop]

        line_stop_ids = self.lines_to_stops.get(line, [])
        stops_on_line = [self.stops_by_id[sid] for sid in line_stop_ids if sid in self.stops_by_id]

        corridor = []
        seen_names = {self.get_canonical_name(u_stop), self.get_canonical_name(v_stop)}
        for s in stops_on_line:
            vec = (s["latitude"] - u_stop["latitude"], s["longitude"] - u_stop["longitude"])
            t = (vec[0] * du[0] + vec[1] * du[1]) / mag_sq
            perp = math.sqrt(max(0.0, (vec[0] ** 2 + vec[1] ** 2) - (t ** 2 * mag_sq)))
            if 0.01 <= t <= 0.99 and perp < 0.018:
                cname = self.get_canonical_name(s)
                if cname not in seen_names:
                    seen_names.add(cname)
                    corridor.append((t, s))

        corridor.sort(key=lambda x: x[0])
        res = [s for _, s in corridor]
        if not res or res[0]["stop_id"] != u_stop["stop_id"]:
            res.insert(0, u_stop)
        if res[-1]["stop_id"] != v_stop["stop_id"]:
            res.append(v_stop)
        return res

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

    @staticmethod
    def get_line_schedule_window(line: str, dt: datetime) -> Tuple[bool, int, int]:
        """
        Vyhodnotí prevádzkový režim linky MHD v danom čase a vráti:
        (is_operating_now, seconds_until_next_run, typical_headway_seconds).
        Ak linka v danom čase nepremáva (napr. denná linka 55 neskoro večer alebo v noci),
        vráti is_operating_now=False a presný počet sekúnd čakania do začiatku najbližšej premávky.
        """
        line_str = str(line).strip()
        if not RoutingEngine.is_mhd_line(line_str):
            # Ak to nie je mestská linka MHD Košice (napr. prímestský Eurobus alebo vlak), pre MHD plánovač nepremáva
            return False, 86400, 86400

        hour = dt.hour
        minute = dt.minute
        time_min = hour * 60 + minute
        weekday = dt.weekday()  # 0=Pondelok, 6=Nedeľa
        line_upper = line_str.upper()

        # 1. Nočné linky N1 - N7
        if line_upper.startswith("N"):
            # Nočné linky premávajú výhradne v nočných hodinách od 23:00 do 04:30
            is_operating = (time_min >= 23 * 60) or (time_min <= 4 * 60 + 30)
            if is_operating:
                mins_left = (60 - (minute % 60)) if minute % 60 != 0 else 60
                return True, max(180, mins_left * 60), 3600
            else:
                # Cez deň nočné linky nepremávajú; najbližší odchod o 23:00 večer
                target = dt.replace(hour=23, minute=0, second=0, microsecond=0)
                wait_sec = max(180, int((target - dt).total_seconds()))
                return False, wait_sec, 3600

        # 2. Účelová / špičková linka 55
        if line_str == "55":
            if weekday >= 5:  # Víkend - linka 55 cez víkendy vôbec nepremáva
                days_to_mon = (7 - weekday)
                target = (dt + timedelta(days=days_to_mon)).replace(hour=5, minute=45, second=0, microsecond=0)
                return False, max(180, int((target - dt).total_seconds())), 900

            # Pracovné dni: ranná špička 05:45 - 08:45, popoludňajšia 13:30 - 17:15
            in_morn = (5 * 60 + 45) <= time_min <= (8 * 60 + 45)
            in_aft = (13 * 60 + 30) <= time_min <= (17 * 60 + 15)
            if in_morn or in_aft:
                return True, 600, 900
            elif time_min < (5 * 60 + 45):
                target = dt.replace(hour=5, minute=45, second=0, microsecond=0)
                return False, max(180, int((target - dt).total_seconds())), 900
            elif time_min < (13 * 60 + 30):
                target = dt.replace(hour=13, minute=30, second=0, microsecond=0)
                return False, max(180, int((target - dt).total_seconds())), 900
            else:
                # Po 17:15 (večer / v noci) najbližší spoj až na druhý deň ráno o 05:45
                days_add = 3 if weekday == 4 else 1  # V piatok večer až v pondelok
                target = (dt + timedelta(days=days_add)).replace(hour=5, minute=45, second=0, microsecond=0)
                return False, max(180, int((target - dt).total_seconds())), 900

        # 3. Zmenové linky RA1 - RA8 (U. S. Steel)
        if line_upper.startswith("RA"):
            s1 = (5 * 60) <= time_min <= (6 * 60 + 15)
            s2 = (13 * 60) <= time_min <= (14 * 60 + 15)
            s3 = (21 * 60) <= time_min <= (22 * 60 + 15)
            if s1 or s2 or s3:
                return True, 480, 1200
            elif time_min < 5 * 60:
                target = dt.replace(hour=5, minute=0, second=0, microsecond=0)
            elif time_min < 13 * 60:
                target = dt.replace(hour=13, minute=0, second=0, microsecond=0)
            elif time_min < 21 * 60:
                target = dt.replace(hour=21, minute=0, second=0, microsecond=0)
            else:
                target = (dt + timedelta(days=1)).replace(hour=5, minute=0, second=0, microsecond=0)
            return False, max(180, int((target - dt).total_seconds())), 1200

        # 4. Štandardné denné linky (električky 1-9, R1-R7 a autobusy 10-54, 71, 72)
        # Premávajú cca od 04:30 do 23:15
        is_operating = (4 * 60 + 30) <= time_min <= (23 * 60 + 15)
        if is_operating:
            return True, 480, 720
        else:
            # V noci nepremávajú; najbližší ranný spoj cca o 04:45
            if time_min > (23 * 60 + 15):
                target = (dt + timedelta(days=1)).replace(hour=4, minute=45, second=0, microsecond=0)
            else:
                target = dt.replace(hour=4, minute=45, second=0, microsecond=0)
            return False, max(180, int((target - dt).total_seconds())), 720

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
        Ak spoj v danom čase nepremáva (alebo ide až o niekoľko hodín / na druhý deň),
        vráti plnú dobu čakania, čím ju Dijkstrov algoritmus prirodzene vyradí ako neefektívnu.
        Pri is_future=True ignoruje živé meškania dnešných vozidiel a telemetriu, vychádza z plánovaného poriadku.
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

        is_op, sched_wait_sec, headway = self.get_line_schedule_window(line_str, current_dt)
        if not is_op:
            return {
                "wait_seconds": sched_wait_sec,
                "wait_minutes": round(sched_wait_sec / 60.0, 1),
                "delay_minutes": 0,
                "expected_timestamp": current_ts + sched_wait_sec,
                "trip_id": None,
                "vehicle_info": None,
                "license_number": None,
                "is_live": False
            }

        # 1. Kontrola Ubian odchodov na danej zastávke
        deps = self.get_stop_departures_cached(stop_id, current_dt, allow_network=allow_network)
        matching_deps = [
            d for d in deps
            if str(d.get("line")).strip() == line_str
        ]

        if matching_deps:
            valid_deps = []
            for d in matching_deps:
                if is_future:
                    # Pre budúce spoje ignorujeme aktuálne live meškanie dnešných vozidiel
                    pl_ts = d.get("planned_timestamp") or d.get("expected_timestamp") or 0
                    exp_ts = pl_ts
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
                        spz_str = fleet.get("spz") or (f"ev. č. {fleet.get('evidencne_cislo')}" if fleet.get("evidencne_cislo") else None)
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

        # Ak zastávka vrátila odchody iných liniek, ale táto linka medzi nimi nie je:
        if deps and len(deps) >= 5:
            # Ak je linka v prevádzke podľa statického harmonogramu, použijeme statický headway,
            # aby uzly nezostali izolované pri výpadku živých dát.
            if is_op:
                stat_wait = max(sched_wait_sec, headway)
                return {
                    "wait_seconds": stat_wait,
                    "wait_minutes": round(stat_wait / 60.0, 1),
                    "delay_minutes": 0,
                    "expected_timestamp": current_ts + stat_wait,
                    "trip_id": None,
                    "vehicle_info": None,
                    "license_number": None,
                    "is_live": False
                }
            else:
                big_wait = max(9000, sched_wait_sec)
                return {
                    "wait_seconds": big_wait,
                    "wait_minutes": round(big_wait / 60.0, 1),
                    "delay_minutes": 0,
                    "expected_timestamp": current_ts + big_wait,
                    "trip_id": None,
                    "vehicle_info": None,
                    "license_number": None,
                    "is_live": False
                }

        # 2. Ak odchody z Ubianu neboli dostupné:
        # Pre budúci čas ignorujeme live feed telemetriu dnešných vozidiel!
        if not is_future:
            telem = self.get_live_line_telemetry(line_str, stop_id)
            if telem.get("is_live"):
                return {
                    "wait_seconds": telem["wait_seconds"],
                    "wait_minutes": telem["wait_minutes"],
                    "delay_minutes": telem["delay_minutes"],
                    "expected_timestamp": current_ts + telem["wait_seconds"],
                    "trip_id": None,
                    "vehicle_info": telem["vehicle_info"],
                    "license_number": telem["license_number"],
                    "is_live": True
                }

        # 3. Statický fallback: Plánované odchody a štandardný headway v rámci premávky
        stat_wait = sched_wait_sec if is_op else max(9000, sched_wait_sec)
        return {
            "wait_seconds": stat_wait,
            "wait_minutes": round(stat_wait / 60.0, 1),
            "delay_minutes": 0,
            "expected_timestamp": current_ts + stat_wait,
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

            # 2. Jazda MHD - výlučne klasické mestské linky DPMK (bez Eurobusov)
            u_lines = [l for l in u_stop.get("lines", []) if self.is_mhd_line(l)]
            for line in u_lines:
                cand_stops = self.lines_to_stops.get(str(line), [])
                wait_key = (u_str, line)
                if wait_key not in wait_cache:
                    wait_cache[wait_key] = self.calculate_transit_edge_wait(
                        u, line, current_node_dt, allow_network=False, is_future=is_future
                    )
                wait_info = wait_cache[wait_key]
                wait_sec = wait_info["wait_seconds"]
                delay_min = wait_info["delay_minutes"]
                trip_id = wait_info.get("trip_id")
                veh_info = wait_info.get("vehicle_info")

                for v in cand_stops:
                    v_str = str(v)
                    if v == u or v_str == u_str or v in visited or v_str in visited:
                        continue

                    v_stop = self.stops_by_id.get(v) or self.stops_by_id.get(v_str)
                    if not v_stop:
                        continue
                    v_lat = v_stop.get("latitude")
                    v_lon = v_stop.get("longitude")
                    if v_lat is None or v_lon is None:
                        continue

                    dx = (v_lon - u_lon) * 73400.0
                    dy = (v_lat - u_lat) * 111200.0
                    d2 = dx * dx + dy * dy
                    if d2 > 144000000:  # 12 km
                        continue

                    dist_m = math.sqrt(d2)
                    ride_sec = max(75, int(dist_m * 0.1923))

                    # Transfer penalty: aplikuje sa výlučne ak už cestujúci použil predchádzajúci spoj a prestupuje
                    is_transfer = has_prior_transit and (mode != f"transit_{line}")
                    if direct_only and is_transfer:
                        continue
                    transfer_penalty = TRANSFER_PENALTY_SECONDS if is_transfer else 0

                    new_cost = cost_metric + wait_sec + ride_sec + transfer_penalty
                    new_real_time = real_time_sec + wait_sec + ride_sec

                    if new_cost >= best_cost.get(v, float("inf")) or new_cost >= best_cost.get(v_str, float("inf")):
                        continue
                    best_cost[v] = new_cost
                    best_cost[v_str] = new_cost
                    try:
                        best_cost[int(v)] = new_cost
                    except (ValueError, TypeError):
                        pass

                    action = {
                        "type": "transit",
                        "line": line,
                        "from_id": u,
                        "to_id": v,
                        "distance_meters": round(dist_m, 1),
                        "wait_seconds": wait_sec,     # Čistý reálny čas bez penalizácie
                        "wait_minutes": wait_info.get("wait_minutes", round(wait_sec / 60.0, 1)),
                        "ride_seconds": ride_sec,     # Čistý reálny čas bez penalizácie
                        "delay_minutes": delay_min,
                        "trip_id": trip_id,
                        "vehicle_info": veh_info,
                        "expected_timestamp": wait_info.get("expected_timestamp"),
                        "is_live": wait_info.get("is_live", False)
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
                "color": "#10b981",
                "dash_array": "4, 8",
                "weight": 4,
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
            from_stop = self.resolve_stop(from_id)
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

        final_reached_platform = to_stop

        for act in path_actions:
            if act["type"] == "walk":
                # Nulový presun medzi stĺpikmi v rámci rovnakého uzla ignorujeme ako samostatný peší krok
                if act.get("is_platform_transfer") or act.get("duration_seconds", 0) == 0:
                    final_reached_platform = self.stops_by_id.get(act["to_id"], final_reached_platform)
                    continue

                u_s = self.stops_by_id[act["from_id"]]
                v_s = self.stops_by_id[act["to_id"]]
                final_reached_platform = v_s
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
                    "color": "#10b981",
                    "dash_array": "4, 8",
                    "weight": 4,
                    "coords": coords,
                    "points_count": len(coords),
                    "label": f"🚶 Pešo {w_min} min ({dist_m:.0f} m)"
                })

            elif act["type"] == "transit":
                line = act["line"]
                if line not in lines_used:
                    lines_used.append(line)

                u_s = self.stops_by_id[act["from_id"]]
                v_s = self.stops_by_id[act["to_id"]]
                final_reached_platform = v_s

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

                u_canon = self.get_canonical_name(u_s)
                v_canon = self.get_canonical_name(v_s)

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
                    "coords": [u_s["latitude"], u_s["longitude"]],
                    "wait_seconds": wait_sec,
                    "wait_minutes": wait_min,
                    "delay_minutes": delay_min,
                    "vehicle_info": veh_info,
                    "trip_id": trip_id,
                    "instruction": wait_instr,
                    "icon": "⏳"
                })
                step_idx += 1
                current_time_dt += timedelta(seconds=wait_sec)

                polyline_coords, intermediate_names = self.get_transit_segment_geometry(line, u_s, v_s, trip_id=trip_id)

                ride_sec = act["ride_seconds"]
                ride_min = round(ride_sec / 60.0, 1)
                dist_m = act["distance_meters"]
                total_ride_sec += ride_sec
                current_time_dt += timedelta(seconds=ride_sec)

                if intermediate_names:
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
                    "from_coords": [u_s["latitude"], u_s["longitude"]],
                    "to_coords": [v_s["latitude"], v_s["longitude"]],
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
                    "coords": [v_s["latitude"], v_s["longitude"]],
                    "instruction": f"Vystúp na zastávke {v_canon}",
                    "icon": "🚪"
                })
                step_idx += 1

                map_segments.append({
                    "type": "transit",
                    "line": line,
                    "color": "#0284c7",
                    "weight": 6,
                    "coords": polyline_coords,
                    "points_count": len(polyline_coords),
                    "label": f"🚌 Linka {line} ({ride_min} min)"
                })

        steps.append({
            "step_index": step_idx,
            "type": "arrival",
            "stop_id": final_reached_platform["stop_id"],
            "stop_name": to_canonical,
            "coords": [final_reached_platform["latitude"], final_reached_platform["longitude"]],
            "instruction": f"Cieľová zastávka: {to_canonical}",
            "icon": "🏁"
        })

        total_duration_sec = int((current_time_dt - now_dt).total_seconds())
        total_duration_min = round(total_duration_sec / 60.0, 1)
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
