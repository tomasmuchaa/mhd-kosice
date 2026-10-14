from __future__ import annotations
import os
import urllib.request
import json
import re
import time
import unicodedata
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional, Union

class DpmkLiveFeed:
    UBIAN_BASE_URL = os.getenv("UBIAN_BASE_URL", "https://www.ubian.sk")
    UBIAN_URL = os.getenv("UBIAN_VEHICLES_URL", f"{UBIAN_BASE_URL}/navigation/vehicles/nearby")
    KOSICE_CITY_ID = int(os.getenv("UBIAN_CITY_ID", "18024"))
    KOSICE_COORDS = (48.7164, 21.2611)  # Stred mesta Košice

    # Centrá mestských častí pre kompletné pokrytie Košíc (vrátane okrajových častí ako Šaca, Furča, KVP, Ťahanovce)
    SCAN_CENTERS = [
        (48.716, 21.261),  # Centrum
        (48.755, 21.260),  # Sever / Ťahanovce
        (48.718, 21.215),  # Západ / Terasa / KVP
        (48.685, 21.285),  # Juh / Nad jazerom / Krásna
        (48.635, 21.175),  # Šaca
        (48.735, 21.290),  # Dargovských hrdinov / Furča
        (48.745, 21.230),  # Myslava / Kavečany
        (48.670, 21.250)   # Barca
    ]

    def __init__(self, radius_km: int = 15, fleet_service: Optional[Any] = None):
        self.radius_km = radius_km
        self.fleet_service = fleet_service
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{self.UBIAN_BASE_URL}/"
        }

    def set_fleet_service(self, fleet_service: Any):
        """Prepojí live feed so službou FleetService pre okamžité aplikovanie overených prepisov."""
        self.fleet_service = fleet_service
        # In-memory TTL cache pre live vozidlá (ochrana pred DoS a preťažením upstreamu)
        self._live_cache: List[Dict[str, Any]] = []
        self._live_cache_ts: float = 0.0
        self._live_cache_ttl: float = float(os.getenv("LIVE_FEED_CACHE_SECONDS", "3.0"))

        # Pamäť posledného stavu meškania pre výpočet nárastu (delay_delta)
        # vehicle_id -> {"delay_minutes": int, "latitude": float, "longitude": float, "timestamp": float}
        self.last_seen_delays: Dict[Any, Dict[str, Any]] = {}

        # Zoznam zaznamenaných ohnísk vzniku a nárastu meškania (hotspoty)
        # Každý hotspot: {"lat": float, "lng": float, "delta": int, "timestamp": float, "line": str}
        self.delay_hotspots: List[Dict[str, Any]] = []

        # In-memory TTL vyrovnávacia pamäť pre reálne dispečerské dáta jázd (tripID -> ŠPZ / stav)
        # Umožňuje získať skutočnú ŠPZ z /navigation/vehicles/get_real bez opakovanej záťaže
        self._trip_real_cache: Dict[Any, Dict[str, Any]] = {}

    def _fetch_real_vehicle_state(
        self,
        trip_id: Any,
        firma_id: Any = 1000,
        line: Any = None,
        trip_number: Any = None
    ) -> Optional[Dict[str, Any]]:
        """
        Stiahne detailné dispečerské dáta vozidla (vrátane reálnej ŠPZ / čísla električky)
        priamo z Ubian endpointu /navigation/vehicles/get_real.
        """
        if not trip_id:
            return None
        url = f"{self.UBIAN_BASE_URL}/navigation/vehicles/get_real?tripID={trip_id}"
        if firma_id:
            url += f"&firmaID={firma_id}"
        if line:
            url += f"&line={line}"
        if trip_number:
            url += f"&tripNumber={trip_number}"

        req = urllib.request.Request(url, headers=self.headers)
        try:
            with urllib.request.urlopen(req, timeout=3.5) as response:
                data = json.loads(response.read().decode("utf-8"))
                return data.get("vehicle")
        except Exception:
            try:
                # Fallback na dpmk-odchody.ubian.sk
                alt_url = url.replace("www.ubian.sk", "dpmk-odchody.ubian.sk")
                req_alt = urllib.request.Request(alt_url, headers=self.headers)
                with urllib.request.urlopen(req_alt, timeout=3.5) as response:
                    data = json.loads(response.read().decode("utf-8"))
                    return data.get("vehicle")
            except Exception:
                return None

    def _fetch_center_vehicles(self, center: tuple) -> List[Dict[str, Any]]:
        """Stiahne vozidlá pre jeden geografický bod/centrum."""
        lat, lng = center
        url = f"{self.UBIAN_URL}?lat={lat}&lng={lng}&radius={self.radius_km}&cityID={self.KOSICE_CITY_ID}"
        req = urllib.request.Request(url, headers=self.headers)
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
                return data.get("vehicles", [])
        except Exception:
            return []

    def get_live_vehicles(self) -> List[Dict[str, Any]]:
        """
        Stiahne všetky aktuálne sa pohybujúce vozidlá DPMK pomocou viacbodového skenovania
        všetkých mestských častí Košíc (odstraňuje duplicity a vyťahuje priame Ubian dáta).
        """
        now_ts = time.time()
        # Rýchla TTL vyrovnávacia pamäť (chráni server a Ubian pred preťažením)
        if self._live_cache and (now_ts - self._live_cache_ts < self._live_cache_ttl):
            return self._live_cache

        now_iso = datetime.now().astimezone().isoformat()

        # Paralelné viacbodové stiahnutie pre bleskovú odozvu
        with ThreadPoolExecutor(max_workers=len(self.SCAN_CENTERS)) as executor:
            center_results = list(executor.map(self._fetch_center_vehicles, self.SCAN_CENTERS))

        unique_vehicles: Dict[Any, Dict[str, Any]] = {}

        for vehicle_list in center_results:
            for raw in vehicle_list:
                trip = raw.get("timeTableTrip") or {}
                line_info = trip.get("timeTableLine") or {}

                # Filtrujeme len DPMK (operatorID 18024)
                if trip.get("operatorID") != self.KOSICE_CITY_ID:
                    continue

                vid = raw.get("vehicleID")
                tid = trip.get("tripID")
                dedup_key = vid if vid is not None else tid
                if not dedup_key or dedup_key in unique_vehicles:
                    continue

                last_comm = raw.get("lastCommunication")
                if not last_comm or str(last_comm).startswith("0001-01-01"):
                    last_comm = now_iso

                # Extrakcia ŠPZ/EČV z Ubianu (podpora všetkých možných kľúčov v telemetrii)
                ubian_spz = (
                    raw.get("licenseNumber")
                    or raw.get("plateNumber")
                    or raw.get("ecv")
                    or raw.get("spz")
                    or trip.get("licenseNumber")
                    or trip.get("plateNumber")
                    or trip.get("ecv")
                    or trip.get("spz")
                )

                # Extrakcia modelu / typu z Ubianu
                ubian_model = (
                    raw.get("vehicleName")
                    or raw.get("vehicleType")
                    or raw.get("model")
                    or trip.get("vehicleName")
                    or trip.get("vehicleType")
                    or trip.get("model")
                )

                # Extrakcia názvu aktuálnej / nasledujúcej zastávky (timeTableTrip / raw / tooltip)
                current_stop = (
                    trip.get("currentStopName")
                    or trip.get("nextStopName")
                    or trip.get("currentStop")
                    or trip.get("nextStop")
                    or trip.get("stopName")
                    or trip.get("lastStopName")
                    or raw.get("currentStopName")
                    or raw.get("nextStopName")
                    or raw.get("stopName")
                    or raw.get("lastStopName")
                )
                if not current_stop:
                    tooltip = raw.get("tooltip") or ""
                    if tooltip:
                        base_tooltip = tooltip.split(";")[0].strip()
                        parts = re.split(r"→|->", base_tooltip)
                        if len(parts) >= 2:
                            left = parts[0].strip()
                            if "," in left:
                                left = left.split(",", 1)[1].strip()
                            if left:
                                current_stop = left

                unique_vehicles[dedup_key] = {
                    "vehicle_id": vid,
                    "license_number": ubian_spz,
                    "model": ubian_model,
                    "vehicle_vin": raw.get("vehicleIdentificationNumber"),
                    "line": line_info.get("line"),
                    "line_type": line_info.get("ezVehicleType") or line_info.get("ezLineType"),
                    "line_name": line_info.get("lineName"),
                    "destination": trip.get("destinationStopName"),
                    "destination_full": trip.get("destination"),
                    "latitude": raw.get("latitude"),
                    "longitude": raw.get("longitude"),
                    "delay_minutes": raw.get("delayMinutes", 0),
                    "trip_id": tid,
                    "trip_number": trip.get("trip"),
                    "is_on_stop": raw.get("isOnStop", False),
                    "current_stop_name": current_stop,
                    "last_stop_order": raw.get("lastStopOrder"),
                    "last_communication": last_comm,
                    "low_floor": trip.get("lowFloor", True),
                    "wifi": trip.get("wifi", False),
                    "bicycle": trip.get("bicycle", False)
                }

        # Obohatenie o reálne ŠPZ a ev. čísla priamo z dispečerského endpointu /navigation/vehicles/get_real
        now_time = time.time()
        missing_real_trips = []
        for dedup_key, veh in unique_vehicles.items():
            tid = veh.get("trip_id")
            if not veh.get("license_number") and tid:
                cached_real = self._trip_real_cache.get(tid)
                if cached_real and (now_time - cached_real.get("timestamp", 0) < 600):  # 10 min TTL
                    real_veh = cached_real.get("vehicle") or {}
                    real_lic = real_veh.get("licenseNumber")
                    if real_lic:
                        veh["license_number"] = str(real_lic).strip()
                        if real_veh.get("lastStopOrder") is not None and not veh.get("last_stop_order"):
                            veh["last_stop_order"] = real_veh["lastStopOrder"]
                else:
                    missing_real_trips.append((dedup_key, tid, veh.get("line"), veh.get("trip_number")))

        if missing_real_trips:
            def fetch_single(item):
                dkey, tid, line, trip_num = item
                res = self._fetch_real_vehicle_state(trip_id=tid, firma_id=1000, line=line, trip_number=trip_num)
                return dkey, tid, res

            with ThreadPoolExecutor(max_workers=min(10, len(missing_real_trips))) as executor:
                for dkey, tid, real_veh in executor.map(fetch_single, missing_real_trips):
                    if real_veh:
                        self._trip_real_cache[tid] = {"timestamp": now_time, "vehicle": real_veh}
                        real_lic = real_veh.get("licenseNumber")
                        if real_lic and dkey in unique_vehicles:
                            unique_vehicles[dkey]["license_number"] = str(real_lic).strip()
                            if real_veh.get("lastStopOrder") is not None and not unique_vehicles[dkey].get("last_stop_order"):
                                unique_vehicles[dkey]["last_stop_order"] = real_veh["lastStopOrder"]

        # Automatické prečistenie starých záznamov v _trip_real_cache
        if len(self._trip_real_cache) > 200:
            cutoff = now_time - 1800
            self._trip_real_cache = {k: v for k, v in self._trip_real_cache.items() if v.get("timestamp", 0) > cutoff}

        # Spracovanie nárastu meškania (delay_delta) a zaznamenanie ohnísk vzniku zápch
        now_ts = time.time()
        for v in unique_vehicles.values():
            vid = v.get("vehicle_id") or v.get("trip_id")
            if not vid:
                continue

            cur_delay = int(v.get("delay_minutes") or 0)
            cur_lat = v.get("latitude")
            cur_lng = v.get("longitude")
            cur_line = v.get("line")

            if cur_lat is None or cur_lng is None:
                continue

            if vid in self.last_seen_delays:
                prev = self.last_seen_delays[vid]
                prev_delay = prev.get("delay_minutes", 0)
                delta = cur_delay - prev_delay

                # Ak vozidlu stúplo meškanie (napr. z +2 na +5 min, delta = 3)
                if delta > 0:
                    self.delay_hotspots.append({
                        "lat": round(float(cur_lat), 5),
                        "lng": round(float(cur_lng), 5),
                        "delta": delta,
                        "timestamp": now_ts,
                        "line": cur_line
                    })
            else:
                # Prvé zachytenie vozidla: ak už v tomto momente naberá meškanie (>= 2 min)
                if cur_delay >= 2:
                    self.delay_hotspots.append({
                        "lat": round(float(cur_lat), 5),
                        "lng": round(float(cur_lng), 5),
                        "delta": min(cur_delay, 3),
                        "timestamp": now_ts,
                        "line": cur_line
                    })

            # Aktualizácia pamäte pre dané vozidlo
            self.last_seen_delays[vid] = {
                "delay_minutes": cur_delay,
                "latitude": cur_lat,
                "longitude": cur_lng,
                "timestamp": now_ts
            }

        # Automatické prečistenie starých hotspotov (starších ako 30 minút = 1800 sekúnd)
        cutoff = now_ts - 1800
        self.delay_hotspots = [h for h in self.delay_hotspots if h.get("timestamp", 0) >= cutoff]

        result_list = list(unique_vehicles.values())

        # Trvalá aplikácia Overrides na prichádzajúce objekty pred uložením do cache alebo odoslaním na frontend
        if self.fleet_service:
            for veh in result_list:
                self.fleet_service.apply_override_to_live_vehicle(veh)

        self._live_cache = result_list
        self._live_cache_ts = now_ts

        return result_list

    def get_active_hotspots(self, max_age_seconds: int = 1500) -> List[Dict[str, Any]]:
        """
        Vráti aktívne ohniská meškania s aplikovaným postupným chladnutím (decay).
        Hotspoty staršie ako max_age_seconds (štandardne 25 minút) postupne slabnú a po limite zanikajú.
        """
        now = time.time()
        active = []
        retained = []

        for h in self.delay_hotspots:
            age = now - h.get("timestamp", now)
            if age < max_age_seconds:
                retained.append(h)
                # Váha podľa nárastu meškania (delta): delta 1 -> 0.35, delta 2 -> 0.65, delta >= 3 -> 0.95
                delta = h.get("delta", 1)
                base_intensity = min(1.0, 0.2 + 0.25 * delta)
                # Lineárne chladnutie v čase (1.0 hneď po vzniku, 0.0 po uplynutí max_age_seconds)
                decay_factor = max(0.0, 1.0 - (age / max_age_seconds))
                current_intensity = round(base_intensity * decay_factor, 3)

                if current_intensity > 0.05:
                    active.append({
                        "lat": h["lat"],
                        "lng": h["lng"],
                        "intensity": current_intensity,
                        "delta": delta,
                        "age_minutes": round(age / 60, 1),
                        "line": h.get("line")
                    })

        self.delay_hotspots = retained
        return active

    def get_heat_points(self, max_age_seconds: int = 1500) -> List[List[float]]:
        """
        Vráti pole bodov vo formáte [lat, lng, intensity] priamo pre knižnicu Leaflet.heat.
        """
        active = self.get_active_hotspots(max_age_seconds=max_age_seconds)
        return [[h["lat"], h["lng"], h["intensity"]] for h in active]

    def get_trip_polyline_and_stops(self, trip_id: int) -> Dict[str, Any]:
        """Stiahne kompletnú trasu (shape polyline) a zoznam zastávok pre konkrétnu jazdu s in-memory TTL vyrovnávacou pamäťou."""
        if not hasattr(self, "_trip_routes_cache"):
            self._trip_routes_cache = {}
        now = time.time()
        cached = self._trip_routes_cache.get(trip_id)
        if cached and (now - cached.get("timestamp", 0) < 7200):  # 2 hodiny TTL
            return cached.get("data", {})

        url = f"{self.UBIAN_BASE_URL}/navigation/vehicles/trip_stops?tripID={trip_id}&withRoute=1"
        req = urllib.request.Request(url, headers=self.headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            if len(self._trip_routes_cache) > 500:
                cutoff = now - 7200
                self._trip_routes_cache = {k: v for k, v in self._trip_routes_cache.items() if v.get("timestamp", 0) > cutoff}
            self._trip_routes_cache[trip_id] = {"timestamp": now, "data": data}
            return data

    def _ensure_stops_loaded(self):
        """Načíta zastávky z lokálneho JSON súboru alebo ich dynamicky stiahne z Ubianu."""
        if hasattr(self, "_stops_cache") and self._stops_cache:
            return

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        stops_file = os.path.join(os.path.dirname(base_dir), "data", "kosice_stops.json")

        if os.path.exists(stops_file):
            try:
                with open(stops_file, "r", encoding="utf-8") as f:
                    self._stops_cache = json.load(f)
                    self._stops_by_id = {}
                    for s in self._stops_cache:
                        self._stops_by_id[s["stop_id"]] = s
                        parent_id = s.get("parent_stop_id")
                        if parent_id is not None and parent_id not in self._stops_by_id:
                            self._stops_by_id[parent_id] = s
                    return
            except Exception:
                pass

        # Dynamické skenovanie viacerých mestských častí Košíc bez zlučovania
        all_stops = {}
        for lat, lng in self.SCAN_CENTERS:
            url = f"https://www.ubian.sk/navigation/stops/nearby?lat={lat}&lng={lng}&radius=8"
            req = urllib.request.Request(url, headers=self.headers)
            try:
                with urllib.request.urlopen(req, timeout=8) as response:
                    data = json.loads(response.read().decode("utf-8"))
                    for raw in data.get("stops", []):
                        sid = raw.get("stopID")
                        if not sid:
                            continue
                        platforms = raw.get("platforms") or []
                        base_name = raw.get("stopName") or f"Zastávka #{sid}"
                        city = raw.get("stopCity", "Košice")
                        ez_lines = [l for l in (raw.get("ezLines") or []) if l and l.strip() != "-"]
                        is_urban = raw.get("forUrbanPublicTransport", True)

                        if len(platforms) > 1:
                            for p in platforms:
                                p_num = p.get("platformNumber")
                                plat_lat = p.get("latitude")
                                plat_lng = p.get("longitude")
                                if not plat_lat or not plat_lng:
                                    continue
                                p_id = f"{sid}_{p_num}" if p_num is not None else f"{sid}_{len(all_stops)}"
                                plat_name = f"{base_name} (Nást. {p_num})" if p_num is not None else base_name
                                all_stops[p_id] = {
                                    "stop_id": p_id,
                                    "parent_stop_id": sid,
                                    "platform": p_num,
                                    "name": plat_name,
                                    "base_name": base_name,
                                    "city": city,
                                    "latitude": plat_lat,
                                    "longitude": plat_lng,
                                    "lines": ez_lines,
                                    "for_urban": is_urban
                                }
                        else:
                            plat_lat = raw.get("latitude")
                            plat_lng = raw.get("longitude")
                            p_num = None
                            if platforms:
                                plat_lat = platforms[0].get("latitude") or plat_lat
                                plat_lng = platforms[0].get("longitude") or plat_lng
                                p_num = platforms[0].get("platformNumber")
                            if not plat_lat or not plat_lng:
                                continue
                            all_stops[sid] = {
                                "stop_id": sid,
                                "parent_stop_id": sid,
                                "platform": p_num,
                                "name": base_name,
                                "base_name": base_name,
                                "city": city,
                                "latitude": plat_lat,
                                "longitude": plat_lng,
                                "lines": ez_lines,
                                "for_urban": is_urban
                            }
            except Exception:
                pass

        self._stops_cache = sorted(all_stops.values(), key=lambda s: s.get("name") or "")
        self._stops_by_id = {}
        for s in self._stops_cache:
            self._stops_by_id[s["stop_id"]] = s
            parent_id = s.get("parent_stop_id")
            if parent_id is not None and parent_id not in self._stops_by_id:
                self._stops_by_id[parent_id] = s

        # Uloženie do súboru
        try:
            os.makedirs(os.path.dirname(stops_file), exist_ok=True)
            with open(stops_file, "w", encoding="utf-8") as f:
                json.dump(self._stops_cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get_stops(self, radius_km: int = 20) -> List[Dict[str, Any]]:
        """Získa zoznam všetkých zastávok v Košiciach s ich GPS súradnicami a linkami."""
        self._ensure_stops_loaded()
        return self._stops_cache

    def get_stop_name(self, stop_id: Any) -> str:
        """Vráti názov zastávky podľa jej stopID."""
        self._ensure_stops_loaded()
        if hasattr(self, "_stops_by_id"):
            if stop_id in self._stops_by_id:
                return self._stops_by_id[stop_id].get("name") or f"Zastávka #{stop_id}"
            if isinstance(stop_id, str) and "_" in stop_id:
                try:
                    base_id = int(stop_id.split("_")[0])
                    plat = stop_id.split("_")[1]
                    if base_id in self._stops_by_id:
                        base = self._stops_by_id[base_id].get("base_name") or self._stops_by_id[base_id].get("name")
                        return f"{base} (Nást. {plat})"
                except Exception:
                    pass
        return f"Zastávka #{stop_id}"

    @staticmethod
    def normalize_stop_name(name: str) -> str:
        """Normalizuje názov zastávky (odstráni diakritiku, interpunkciu a viacnásobné medzery)."""
        if not name:
            return ""
        s = unicodedata.normalize("NFD", name)
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
        s = re.sub(r"[^a-zA-Z0-9]", " ", s).lower()
        return re.sub(r"\s+", " ", s).strip()

    def _fetch_single_stop_departures_raw(
        self,
        stop_id: Any,
        date: Optional[str] = None,
        time: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Stiahne surové plánované odchody pre jedno konkrétne stop_id z Ubianu."""
        url = f"{self.UBIAN_BASE_URL}/navigation/stops/planned_departures?stopID={stop_id}"
        if date and time:
            if "T" in str(date):
                url += f"&date={date}"
            else:
                t_str = str(time).strip()
                if len(t_str) == 5:
                    t_str += ":00"
                url += f"&date={date}T{t_str}"
        elif date:
            url += f"&date={date}"
        elif time:
            today_iso = datetime.now().strftime("%Y-%m-%d")
            t_str = str(time).strip()
            if len(t_str) == 5:
                t_str += ":00"
            url += f"&date={today_iso}T{t_str}"

        req = urllib.request.Request(url, headers=self.headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
                return data.get("departures", [])
        except Exception:
            return []

    def get_stop_departures(
        self,
        stop_id: Any,
        date: Optional[str] = None,
        time: Optional[str] = None,
        platform: Optional[Any] = None,
        aggregate: bool = False
    ) -> Dict[str, Any]:
        """
        Stiahne odchody výlučne pre jedno konkrétne stop_id (alebo konkrétne nástupište)
        bez akejkoľvek agregácie iných zastávok s rovnakým názvom.
        """
        self._ensure_stops_loaded()

        actual_sid = stop_id
        target_platform = str(platform).strip() if platform is not None else None

        if isinstance(stop_id, str) and "_" in stop_id:
            parts = stop_id.split("_")
            try:
                actual_sid = int(parts[0])
                if not target_platform:
                    target_platform = parts[1].strip()
            except ValueError:
                pass
        else:
            try:
                actual_sid = int(stop_id)
            except (ValueError, TypeError):
                pass

        stop_name = self.get_stop_name(stop_id)

        # Výlučne jedno kliknuté stop_id bez agregácie okolitých nástupíšť s rovnakým názvom
        raw_list = self._fetch_single_stop_departures_raw(actual_sid, date, time)

        now_ts = int(datetime.now().timestamp())
        unique_departures: Dict[str, Dict[str, Any]] = {}

        for d in raw_list:
            trip = d.get("timeTableTrip") or {}
            line_info = trip.get("timeTableLine") or {}
            trip_id = trip.get("tripID")

            plat = d.get("platformNumber")
            if plat is None or str(plat).strip() == "":
                plat = d.get("platformName") or None
            else:
                plat = str(plat).strip()

            # Ak je zvolené konkrétne fyzické nástupište, filtrujeme odchody len pre toto nástupište
            if target_platform and plat and plat != target_platform:
                continue

            planned_ts = d.get("plannedDepartureTimestamp") or d.get("plannedDepartureTime") or 0
            delay = d.get("delayMinutes") or 0
            expected_ts = planned_ts + (delay * 60)

            planned_str = datetime.fromtimestamp(planned_ts).strftime("%H:%M") if planned_ts else "--:--"
            expected_str = datetime.fromtimestamp(expected_ts).strftime("%H:%M") if expected_ts else planned_str

            diff_min = max(0, int((expected_ts - now_ts) / 60))

            dest_name = trip.get("destinationStopName") or trip.get("destination") or ""
            if dest_name.startswith("Košice, "):
                dest_name = dest_name[len("Košice, "):].strip()

            dep_item = {
                "line": line_info.get("line"),
                "destination": dest_name,
                "platform": plat,
                "planned_time": planned_str,
                "expected_time": expected_str,
                "planned_timestamp": planned_ts,
                "expected_timestamp": expected_ts,
                "delay_minutes": delay,
                "minutes_left": diff_min,
                "low_floor": trip.get("lowFloor", True),
                "air_conditioning": True,
                "wifi": trip.get("wifi", False),
                "trip_id": trip_id,
                "vehicle_id": d.get("plannedOrRealVehicleID"),
                "license_number": d.get("plannedOrRealLicenceNumber")
            }

            if trip_id:
                dedup_key = f"trip_{trip_id}"
            else:
                dedup_key = f"{dep_item['line']}_{planned_ts}_{plat}_{dest_name}"

            if dedup_key not in unique_departures:
                unique_departures[dedup_key] = dep_item
            else:
                existing = unique_departures[dedup_key]
                if not existing.get("platform") and plat:
                    existing["platform"] = plat
                if not existing.get("vehicle_id") and dep_item.get("vehicle_id"):
                    existing["vehicle_id"] = dep_item["vehicle_id"]
                if not existing.get("license_number") and dep_item.get("license_number"):
                    existing["license_number"] = dep_item["license_number"]

        departures = list(unique_departures.values())
        departures.sort(key=lambda x: (x.get("expected_timestamp") or x.get("planned_timestamp") or 0, str(x.get("line") or "")))

        return {
            "stop_id": stop_id,
            "stop_name": stop_name,
            "platform": target_platform,
            "total_departures": len(departures),
            "departures": departures
        }

