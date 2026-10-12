import os
import json
import unicodedata
from datetime import datetime
from typing import Optional, List, Dict, Any, Union, Tuple
from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

from app.services.fleet_service import FleetService
from app.services.live_feed_service import DpmkLiveFeed
from app.services.routing_engine import RoutingEngine
from app.services.imhd_scraper import get_imhd_vehicle_history
from app.services.occupancy_service import occupancy_service

def strip_accents(text: str) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize('NFKD', text)
    cleaned = "".join(c for c in nfkd if not unicodedata.combining(c)).lower()
    return " ".join(cleaned.replace(',', ' ').replace('-', ' ').replace('.', ' ').split())

# Cesty k súborom
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
CSV_PATH = os.path.join(PROJECT_DIR, "data", "dpmk_autobusy_komplet.csv")
MAP_PATH = os.path.join(PROJECT_DIR, "mapa.html")
HISTORICAL_TRACK_PATH = os.path.join(PROJECT_DIR, "data", "historical_track.geojson")
MANIFEST_PATH = os.path.join(PROJECT_DIR, "manifest.json")
SERVICE_WORKER_PATH = os.path.join(PROJECT_DIR, "service-worker.js")
ICONS_DIR = os.path.join(PROJECT_DIR, "data", "icons")
STATIC_ICONS_DIR = os.path.join(PROJECT_DIR, "static", "icons")

app = FastAPI(
    title="MHD Košice - Inteligentný Backend",
    description="Pokročilý systém pre sledovanie, vyhľadávanie a analýzu MHD v Košiciach.",
    version="1.0.0"
)

# Povolenie CORS pre volania z lokálneho HTML a mobilných aplikácií
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicializácia služieb
fleet_service = FleetService(csv_path=CSV_PATH)
live_feed = DpmkLiveFeed()
routing_engine = RoutingEngine(live_feed=live_feed, fleet_service=fleet_service)

# Vyrovnávacia pamäť pre posledné zaznamenané polohy (užitočné počas nočnej pauzy medzi 00:35 a 03:40)
LAST_SEEN_CACHE: List[Dict[str, Any]] = [
    {"vehicle_id": 1276522, "line": "N3", "line_type": "BUS", "line_name": "Staničné námestie - Nemocnica Šaca", "destination": "Nemocnica Šaca", "destination_full": "Košice, Nemocnica Šaca", "latitude": 48.71660, "longitude": 21.24988, "delay_minutes": 0, "is_on_stop": False, "trip_id": 1003257873, "last_stop_order": 7, "last_communication": "2026-10-06T00:25:00+02:00"},
    {"vehicle_id": 1276320, "line": "N7", "line_type": "BUS", "line_name": "Staničné námestie - Važecká", "destination": "Važecká", "destination_full": "Košice, Važecká", "latitude": 48.71059, "longitude": 21.27873, "delay_minutes": 2, "is_on_stop": False, "trip_id": 1003273574, "last_stop_order": 14, "last_communication": "2026-10-06T00:25:00+02:00"},
    {"vehicle_id": 1276562, "line": "N2", "line_type": "BUS", "line_name": "Staničné námestie - Podhradová", "destination": "Podhradová", "destination_full": "Košice, Podhradová", "latitude": 48.72143, "longitude": 21.23718, "delay_minutes": 0, "is_on_stop": False, "trip_id": 1003257854, "last_stop_order": 10, "last_communication": "2026-10-06T00:25:00+02:00"},
    {"vehicle_id": 1276436, "line": "N6", "line_type": "BUS", "line_name": "Staničné námestie - KVP, kláštor", "destination": "KVP,  kláštor", "destination_full": "Košice, KVP,  kláštor", "latitude": 48.71335, "longitude": 21.23421, "delay_minutes": 3, "is_on_stop": False, "trip_id": 1003257905, "last_stop_order": 8, "last_communication": "2026-10-06T00:25:00+02:00"},
    {"vehicle_id": 1276317, "line": "N4", "line_type": "BUS", "line_name": "Staničné námestie - Ryba", "destination": "Ryba", "destination_full": "Košice, Ryba", "latitude": 48.70371, "longitude": 21.23617, "delay_minutes": 0, "is_on_stop": True, "trip_id": 1003273592, "last_stop_order": 15, "last_communication": "2026-10-06T00:25:00+02:00"},
    {"vehicle_id": 1276507, "line": "N5", "line_type": "BUS", "line_name": "Staničné námestie - Lingov", "destination": "Lingov", "destination_full": "Košice, Lingov", "latitude": 48.73935, "longitude": 21.25376, "delay_minutes": 0, "is_on_stop": False, "trip_id": 1003270799, "last_stop_order": 9, "last_communication": "2026-10-06T00:25:00+02:00"},
    {"vehicle_id": 1277917, "line": "N1", "line_type": "BUS", "line_name": "Staničné námestie - Madridská", "destination": "Madridská", "destination_full": "Košice, Madridská", "latitude": 48.74553, "longitude": 21.27290, "delay_minutes": 0, "is_on_stop": False, "trip_id": 1003263809, "last_stop_order": 11, "last_communication": "2026-10-06T00:25:00+02:00"},
]


@app.get("/")
def root(request: Request):
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return RedirectResponse(url="/mapa")
    return {
        "service": "MHD Košice API",
        "status": "online",
        "endpoints": {
            "live_vehicles": "/api/v1/vehicles/live",
            "fleet": "/api/v1/fleet",
            "stops": "/api/v1/stops",
            "stop_departures": "/api/v1/stops/{stop_id}/departures",
            "search_by_spz": "/api/v1/vehicle/search?spz=KE-704IY",
            "vehicle_occupancy": "/api/v1/vehicle/{vehicle_id}/occupancy",
            "historical_track": "/api/v1/track/historical",
            "walking_transfers": "/api/v1/routing/transfers",
            "journey_planner": "/api/v1/routing/journey?from_id=1000000178&to_id=1000000030",
            "mapa": "/mapa",
            "ikonky": "/ikonky",
            "manifest": "/manifest.json",
            "docs": "/docs"
        }
    }

@app.get("/mapa", response_class=FileResponse)
def get_mapa_view():
    """Zobrazí interaktívnu Leaflet mapu s live vozidlami."""
    if os.path.exists(MAP_PATH):
        return FileResponse(MAP_PATH)
    raise HTTPException(status_code=404, detail="Súbor mapa.html nebol nájdený.")

@app.get("/ikonky", response_class=FileResponse)
def get_ikonky_view():
    """Zobrazí kompletnú interaktívnu galériu a katalóg všetkých SVG modelov vozidiel."""
    icon_path = os.path.join(PROJECT_DIR, "ikonky.html")
    if os.path.exists(icon_path):
        return FileResponse(icon_path)
    raise HTTPException(status_code=404, detail="Súbor ikonky.html nebol nájdený.")

@app.get("/manifest.json")
def get_manifest():
    """PWA Web App Manifest."""
    if os.path.exists(MANIFEST_PATH):
        return FileResponse(MANIFEST_PATH, media_type="application/manifest+json")
    raise HTTPException(status_code=404, detail="manifest.json nebol nájdený.")

@app.get("/service-worker.js")
def get_service_worker():
    """PWA Service Worker."""
    if os.path.exists(SERVICE_WORKER_PATH):
        return FileResponse(SERVICE_WORKER_PATH, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="service-worker.js nebol nájdený.")

@app.get("/data/icons/{icon_name}")
def get_icon(icon_name: str):
    """PWA Ikony aplikácie."""
    icon_path = os.path.join(ICONS_DIR, icon_name)
    if os.path.exists(icon_path):
        return FileResponse(icon_path, media_type="image/png")
    raise HTTPException(status_code=404, detail="Ikona nebola nájdená.")

@app.get("/static/icons/{icon_name}")
def get_static_icon(icon_name: str):
    """PWA Ikony aplikácie v static/icons/."""
    icon_path = os.path.join(STATIC_ICONS_DIR, icon_name)
    if os.path.exists(icon_path):
        return FileResponse(icon_path, media_type="image/png")
    raise HTTPException(status_code=404, detail="Ikona nebola nájdená.")

@app.get("/api/v1/trip/{trip_id}")
def get_trip_details(trip_id: int):
    """
    Vráti kompletnú trasu (polyline koordináty) a zoznam zastávok pre daný spoj.
    """
    try:
        data = live_feed.get_trip_polyline_and_stops(trip_id)
        return data
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Chyba pri sťahovaní detailov trasy: {str(e)}")


@app.get("/api/v1/track/historical")
def get_historical_track():
    """
    Vráti analyzovanú historickú stopu (GeoJSON) zaznamenanú z GPS telemetrie.
    """
    if not os.path.exists(HISTORICAL_TRACK_PATH):
        try:
            import analyze_and_convert_track
            analyze_and_convert_track.main()
        except Exception as e:
            pass

    if os.path.exists(HISTORICAL_TRACK_PATH):
        try:
            with open(HISTORICAL_TRACK_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Chyba pri načítavaní GeoJSON stopy: {str(e)}")

    raise HTTPException(status_code=404, detail="Historická stopa nebola nájdená.")


@app.get("/api/v1/routing/transfers")
def get_walking_transfers_summary():
    """
    Vráti štatistiku siete peších prestupov (Walking Graph).
    """
    graph = routing_engine.load_walking_graph()
    return {
        "status": "ok",
        "metadata": graph.get("metadata"),
        "total_transfers": len(graph.get("transfers", []))
    }


@app.get("/api/v1/routing/transfers/{stop_id}")
def get_stop_transfers(stop_id: str):
    """
    Vráti všetky pešie prestupy z konkrétnej zastávky do 500 metrov.
    """
    try:
        base_stop_id = int(str(stop_id).split("_")[0])
    except ValueError:
        base_stop_id = stop_id
    transfers = routing_engine.get_transfers_from_stop(base_stop_id)
    stop_data = routing_engine.stops_by_id.get(stop_id) or routing_engine.stops_by_id.get(base_stop_id, {})
    return {
        "status": "ok",
        "stop_id": stop_id,
        "stop_name": stop_data.get("name", f"Zastávka #{stop_id}"),
        "total_transfers": len(transfers),
        "transfers": transfers
    }


@app.get("/api/v1/routing/journey")
def plan_transit_journey(
    from_id: Optional[str] = Query(None, description="Stop ID počiatočnej zastávky alebo GPS súradnice vo formáte 'lat,lon'"),
    to_id: str = Query(..., description="Stop ID cieľovej zastávky"),
    from_lat: Optional[float] = Query(None, description="GPS zemepisná šírka štartu (voliteľné)"),
    from_lon: Optional[float] = Query(None, description="GPS zemepisná dĺžka štartu (voliteľné)"),
    time: Optional[str] = Query(None, description="Čas odchodu vo formáte HH:MM (voliteľné)")
):
    """
    Multimodálny vyhľadávač trás MHD Košice (Journey Planner):
    Nájde najrýchlejšiu trasu medzi počiatočnou (alebo GPS polohou) a cieľovou zastávkou pomocou Dijkstrovho algoritmu,
    využíva sieť peších prestupov a živé/plánované dáta o spojoch a meškaniach.
    """
    parsed_from_id: Optional[Union[int, str]] = None
    from_coords: Optional[Tuple[float, float]] = None

    if from_lat is not None and from_lon is not None:
        from_coords = (float(from_lat), float(from_lon))
    elif from_id is not None:
        from_id_str = str(from_id).strip()
        if "," in from_id_str and not any(c.isalpha() for c in from_id_str):
            parts = [p.strip() for p in from_id_str.split(",")]
            try:
                from_coords = (float(parts[0]), float(parts[1]))
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Neplatný formát GPS súradníc v parametri from_id: '{from_id_str}'")
        else:
            if from_id_str.isdigit():
                parsed_from_id = int(from_id_str)
            else:
                parsed_from_id = from_id_str
    else:
        raise HTTPException(status_code=400, detail="Musíte zadať buď from_id alebo GPS súradnice (from_lat, from_lon).")

    to_id_str = str(to_id).strip()
    if to_id_str.isdigit():
        parsed_to_id: Union[int, str] = int(to_id_str)
    else:
        parsed_to_id = to_id_str

    try:
        result = routing_engine.plan_multiple_journeys(
            from_id=parsed_from_id,
            to_id=parsed_to_id,
            from_coords=from_coords,
            departure_time_str=time,
            target_count=6
        )
        if result.get("status") in ("not_found", "error") or not result.get("journeys"):
            raise HTTPException(status_code=404, detail=result.get("message") or "Trasa nebola nájdená.")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chyba pri plánovaní trasy: {str(e)}")


@app.get("/api/v1/stops")
def get_stops_list(
    q: Optional[str] = Query(None, description="Vyhľadávanie zastávky podľa názvu"),
    urban_only: bool = Query(False, description="Filtrovať len mestské zastávky MHD")
):
    """
    Vráti zoznam všetkých zastávok v Košiciach s ich GPS súradnicami a obsluhovanými linkami.
    """
    stops = live_feed.get_stops()
    if urban_only:
        stops = [s for s in stops if s.get("for_urban", True)]

    # Očistíme linky každej zastávky od Eurobusov a mimomestských liniek
    clean_stops = []
    for s in stops:
        item = dict(s)
        item["lines"] = [l for l in s.get("lines", []) if routing_engine.is_mhd_line(l)]
        clean_stops.append(item)
    stops = clean_stops

    if q:
        q_clean = strip_accents(q.strip())
        stops = [s for s in stops if q_clean in strip_accents(s.get("name") or "")]
    return {
        "status": "ok",
        "total_stops": len(stops),
        "stops": stops
    }


@app.get("/api/v1/stops/{stop_id}/departures")
def get_stop_departures_board(
    stop_id: str,
    platform: Optional[str] = Query(None, description="Číslo konkrétneho nástupišťa")
):
    """
    Vráti virtuálnu digitálnu odchodovú tabuľu pre konkrétne fyzické nástupište/stĺpik zastávky
    s meškaniami a obohatenú o dáta z databázy DPMK (ŠPZ, model, nízkopodlažnosť, klimatizácia).
    """
    try:
        data = live_feed.get_stop_departures(stop_id, platform=platform)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Chyba pri sťahovaní odchodov: {str(e)}")

    # Aktívne vozidlá pre prípadné spárovanie cez trip_id
    active_vehicles = []
    try:
        active_vehicles = live_feed.get_live_vehicles() or LAST_SEEN_CACHE
    except Exception:
        active_vehicles = LAST_SEEN_CACHE

    active_by_trip = {v.get("trip_id"): v for v in active_vehicles if v.get("trip_id")}

    enriched_departures = []
    for dep in data.get("departures", []):
        line = dep.get("line")
        # Filtrujeme výlučne mestské linky MHD Košice (DPMK), ignorujeme Eurobus a regionálne spoje
        if not routing_engine.is_mhd_line(line):
            continue

        v_id = dep.get("vehicle_id")
        lic = dep.get("license_number")
        trip_id = dep.get("trip_id")

        matched_fleet = None

        if v_id or lic:
            matched_fleet = fleet_service.match_live_vehicle(
                vehicle_id=v_id,
                license_number=lic,
                line=dep.get("line"),
                line_type=dep.get("line_type") or dep.get("ezVehicleType"),
                raw_vehicle=dep
            )

        if not matched_fleet and trip_id and trip_id in active_by_trip:
            active_v = active_by_trip[trip_id]
            dep["vehicle_id"] = active_v.get("vehicle_id")
            matched_fleet = fleet_service.match_live_vehicle(
                vehicle_id=active_v.get("vehicle_id"),
                license_number=active_v.get("license_number"),
                line=active_v.get("line") or dep.get("line"),
                line_type=active_v.get("line_type") or dep.get("line_type"),
                raw_vehicle=active_v
            )

        is_low_floor = dep.get("low_floor", True)
        is_ac = True  # Všetky novšie vozidlá DPMK (SOR NB, Solaris) disponujú celovozovou klimatizáciou

        fleet_dict = None
        if matched_fleet:
            is_low_floor = True
            is_ac = True
            fleet_dict = {
                "spz": matched_fleet.get("spz"),
                "evidencne_cislo": matched_fleet.get("evidencne_cislo"),
                "model": matched_fleet.get("model"),
                "rok_vyroby": matched_fleet.get("rok_vyroby"),
                "vin": matched_fleet.get("vin"),
            }

        override = fleet_service.get_override(vehicle_id=dep.get("vehicle_id"), ev_cislo=matched_fleet.get("evidencne_cislo") if matched_fleet else None)
        if override:
            if not fleet_dict:
                fleet_dict = {}
            for k, val in override.items():
                if k == "spz" and not val and fleet_dict.get("spz"):
                    continue
                fleet_dict[k] = val
            matched_fleet = fleet_dict

        dep_item = {
            **dep,
            "matched": matched_fleet is not None,
            "fleet_info": fleet_dict,
            "low_floor": is_low_floor,
            "air_conditioning": is_ac,
        }
        enriched_departures.append(dep_item)

    return {
        "status": "ok",
        "stop_id": data.get("stop_id"),
        "stop_name": data.get("stop_name"),
        "platform": data.get("platform"),
        "timestamp": datetime.now().isoformat(),
        "total_departures": len(enriched_departures),
        "departures": enriched_departures
    }


@app.get("/api/v1/network/stats")
def get_network_stats():
    """
    Vráti živé agregované dispečerské štatistiky celej mestskej siete MHD Košice:
    - Celkový počet vozidiel v premávke
    - Počet a podiel meškajúcich vozidiel (> 3 minúty)
    - Priemerné a maximálne meškanie celej siete
    - TOP 3 najproblémovejšie linky (zoradené zostupne podľa najvyššieho meškania)
    - Zoznam najviac meškajúcich konkrétnych vozidiel
    """
    global LAST_SEEN_CACHE
    raw_vehicles = []
    try:
        raw_vehicles = live_feed.get_live_vehicles()
        if raw_vehicles:
            LAST_SEEN_CACHE = raw_vehicles
    except Exception:
        raw_vehicles = []

    if len(raw_vehicles) == 0 and len(LAST_SEEN_CACHE) > 0:
        raw_vehicles = LAST_SEEN_CACHE

    total_vehicles = len(raw_vehicles)
    delays = [int(v.get("delay_minutes") or 0) for v in raw_vehicles]

    delayed_gt3 = [v for v in raw_vehicles if (v.get("delay_minutes") or 0) > 3]
    delayed_vehicles_count = len(delayed_gt3)
    on_time_vehicles_count = total_vehicles - delayed_vehicles_count
    delayed_percentage = round((delayed_vehicles_count / total_vehicles) * 100, 1) if total_vehicles > 0 else 0.0

    avg_delay = round(sum(delays) / total_vehicles, 1) if total_vehicles > 0 else 0.0
    max_delay = max(delays) if delays else 0

    # Agregácia podľa liniek
    by_line = {}
    for v in raw_vehicles:
        l = v.get("line")
        if not l:
            continue
        l_str = str(l).strip()
        by_line.setdefault(l_str, []).append(v)

    lines_stats = []
    for l_name, v_list in by_line.items():
        l_delays = [int(x.get("delay_minutes") or 0) for x in v_list]
        l_max = max(l_delays) if l_delays else 0
        l_avg = round(sum(l_delays) / len(l_delays), 1) if l_delays else 0.0
        l_delayed_count = sum(1 for d in l_delays if d > 3)
        lines_stats.append({
            "line": l_name,
            "total_vehicles": len(v_list),
            "max_delay_minutes": l_max,
            "average_delay_minutes": l_avg,
            "delayed_vehicles_count": l_delayed_count,
            "sample_destination": (v_list[0].get("destination") or "") if v_list else ""
        })

    # TOP 3 najproblémovejšie linky (zoradené zostupne podľa najvyššieho meškania)
    lines_stats.sort(key=lambda x: (x["max_delay_minutes"], x["average_delay_minutes"]), reverse=True)
    top_3_delayed_lines = lines_stats[:3]

    # TOP 5 najviac meškajúcich konkrétnych vozidiel
    sorted_delayed_vehicles = sorted(raw_vehicles, key=lambda x: int(x.get("delay_minutes") or 0), reverse=True)
    top_delayed_vehicles = []
    for v in sorted_delayed_vehicles[:5]:
        d_min = int(v.get("delay_minutes") or 0)
        if d_min > 0:
            top_delayed_vehicles.append({
                "vehicle_id": v.get("vehicle_id"),
                "line": v.get("line"),
                "destination": v.get("destination"),
                "delay_minutes": d_min,
                "model": v.get("model") or "Vozidlo DPMK",
                "license_number": v.get("license_number"),
                "current_stop_name": v.get("current_stop_name")
            })

    # Distribúcia meškania
    delay_dist = {
        "on_time": sum(1 for d in delays if d <= 3),
        "minor": sum(1 for d in delays if 4 <= d <= 6),
        "heavy": sum(1 for d in delays if d > 6)
    }

    # Body vzniku a nárastu meškania pre Leaflet.heat
    heat_points = live_feed.get_heat_points()

    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "total_vehicles": total_vehicles,
        "delayed_vehicles_count": delayed_vehicles_count,
        "on_time_vehicles_count": on_time_vehicles_count,
        "delayed_percentage": delayed_percentage,
        "average_delay_minutes": avg_delay,
        "max_delay_minutes": max_delay,
        "top_delayed_lines": top_3_delayed_lines,
        "all_problematic_lines": lines_stats[:10],
        "top_delayed_vehicles": top_delayed_vehicles,
        "delay_distribution": delay_dist,
        "delay_hotspots": heat_points,
        "total_hotspots": len(heat_points)
    }


@app.get("/api/v1/network/hotspots")
def get_delay_hotspots(
    max_age_minutes: int = Query(25, description="Maximálny vek hotspotov vzniku meškania v minútach (predvolené 25 min)")
):
    """
    Vráti dynamické ohniská vzniku a nárastu meškania (delay hotspots) priamo formátované
    pre Leaflet.heat ako pole [latitude, longitude, intensity] s aplikovaným chladnutím (decay).
    """
    max_age_sec = max_age_minutes * 60
    heat_points = live_feed.get_heat_points(max_age_seconds=max_age_sec)
    hotspots_detail = live_feed.get_active_hotspots(max_age_seconds=max_age_sec)

    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "max_age_minutes": max_age_minutes,
        "total_hotspots": len(heat_points),
        "heat_points": heat_points,
        "hotspots_detail": hotspots_detail
    }


@app.get("/api/v1/vehicles/live")
def get_live_vehicles(
    only_matched: bool = Query(False, description="Filtrovať len vozidlá so spárovanou ŠPZ a modelom"),
    include_fallback: bool = Query(True, description="Vrátiť posledné známe pozície, ak je nočná pauza (0 vozidiel na trase)")
):
    """
    Získa aktuálne polohy vozidiel DPMK z live feedu a obohatí ich o dáta z databázy (ŠPZ, model, ev. číslo).
    """
    global LAST_SEEN_CACHE
    raw_vehicles = []
    is_live = True

    try:
        raw_vehicles = live_feed.get_live_vehicles()
        if raw_vehicles:
            LAST_SEEN_CACHE = raw_vehicles
    except Exception as e:
        # Ak by Ubian zlyhal, použijeme cache
        raw_vehicles = []

    # Ak je práve nočná pauza (0 vozidiel online) a máme povolený fallback
    if len(raw_vehicles) == 0 and include_fallback and len(LAST_SEEN_CACHE) > 0:
        raw_vehicles = LAST_SEEN_CACHE
        is_live = False

    enriched_vehicles = []
    matched_count = 0

    for v in raw_vehicles:
        # 1. Priame dáta z Ubianu majú najvyššiu prioritu (ŠPZ, model, VIN)
        ubian_spz = v.get("license_number")
        ubian_model = v.get("model")
        ubian_vin = v.get("vehicle_vin")

        # 2. Kontrola trakcie a lokálne CSV fleet_info ako autorita pre autobusy
        is_tram = fleet_service.is_tram(
            vehicle_id=v.get("vehicle_id"),
            line=v.get("line"),
            line_type=v.get("line_type"),
            raw_vehicle=v
        )

        fleet_data = None
        if not is_tram and ubian_spz:
            fleet_data = fleet_service.get_by_spz(ubian_spz, only_active=True)

        if not fleet_data:
            fleet_data = fleet_service.match_live_vehicle(
                vehicle_id=v["vehicle_id"],
                license_number=ubian_spz if not is_tram else None,
                line=v.get("line"),
                line_type=v.get("line_type"),
                raw_vehicle=v
            )

        # Autorita lokálnej databázy (CSV):
        # Ak sa nám podarí spárovať vozidlo s naším CSV (či už cez ŠPZ, alebo dekódované ev. číslo),
        # model z nášho CSV musí vždy prepísať model získaný z Ubianu.
        final_spz = None if is_tram else (ubian_spz or (fleet_data.get("spz") if fleet_data else None))
        final_ev = fleet_data.get("evidencne_cislo") if fleet_data else None
        final_rok = fleet_data.get("rok_vyroby") if fleet_data else None
        final_vin = ubian_vin or (fleet_data.get("vin") if fleet_data else None)

        if is_tram:
            final_spz = None
            final_model = (fleet_data.get("model") if fleet_data else None) or ubian_model or "Električka DPMK"
            if str(final_model).strip().upper() == "TRAM":
                final_model = "Električka DPMK"
        else:
            # Pre autobusy: autorita lokálnej offline databázy (CSV)
            if fleet_data and fleet_data.get("model"):
                final_model = fleet_data["model"]
            elif ubian_model and str(ubian_model).strip().upper() not in ["BUS", "AUTOBUS"]:
                final_model = ubian_model
            else:
                final_model = "Autobus DPMK"

        # 3. NAJVYŠŠIA AUTORITA PRAVDY: MANUAL_OVERRIDES bezpodmienečne prepisuje Ubian aj CSV!
        is_verified = False
        override = fleet_service.get_override(vehicle_id=v["vehicle_id"], ev_cislo=final_ev)
        if override:
            if override.get("model"):
                final_model = override["model"]
            if override.get("spz") and not is_tram:
                final_spz = override["spz"]
            if override.get("evidencne_cislo"):
                final_ev = override["evidencne_cislo"]
            if override.get("rok_vyroby"):
                final_rok = override["rok_vyroby"]
            if override.get("vin"):
                final_vin = override["vin"]
            if override.get("verified") is not None:
                is_verified = bool(override["verified"])

        # Typ vozidla - fallback ak nie je konkrétny model
        line_type = str(v.get("line_type") or "").upper()
        if not final_model:
            if is_tram or line_type == "TRAM" or v.get("line") in ["1", "2", "3", "4", "5", "6", "7", "9", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"]:
                final_model = "Električka DPMK"
                if not final_ev:
                    final_ev = str(v["vehicle_id"])[-3:] if v.get("vehicle_id") else None
            elif line_type == "BUS":
                final_model = "Autobus DPMK"

        # Výbava vozidla
        low_floor = v.get("low_floor", True)
        air_conditioning = True if (fleet_data or line_type == "BUS") else False
        wifi = v.get("wifi", False)

        is_matched = bool(
            (final_model and final_model not in ["Autobus DPMK", "Električka DPMK"])
            or final_spz
            or override
        )

        # Získanie platnej obsadenosti vozidla s inteligentnou expiráciou (5 min / nová zastávka)
        occ = occupancy_service.get_occupancy(
            vehicle_id=v["vehicle_id"],
            live_stop_name=v.get("current_stop_name")
        )

        item = {
            "vehicle_id": v["vehicle_id"],
            "line": v.get("line"),
            "line_type": v.get("line_type"),
            "line_name": v.get("line_name"),
            "destination": v.get("destination"),
            "destination_full": v.get("destination_full"),
            "latitude": v.get("latitude"),
            "longitude": v.get("longitude"),
            "delay_minutes": v.get("delay_minutes", 0),
            "is_on_stop": v.get("is_on_stop", False),
            "current_stop_name": v.get("current_stop_name"),
            "occupancy": occ,
            "trip_id": v.get("trip_id"),
            "last_stop_order": v.get("last_stop_order"),
            "last_communication": v.get("last_communication"),
            "matched": is_matched,
            "is_verified": is_verified,
            "fleet_info": {
                "spz": final_spz,
                "evidencne_cislo": final_ev,
                "model": final_model,
                "rok_vyroby": final_rok,
                "vin": final_vin,
                "low_floor": low_floor,
                "air_conditioning": air_conditioning,
                "wifi": wifi,
                "is_verified": is_verified,
                "verified": is_verified
            }
        }

        if is_matched:
            matched_count += 1

        if not only_matched or is_matched:
            enriched_vehicles.append(item)

    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "is_live": is_live,
        "note": "Živé vysielanie" if is_live else "Nočná pauza DPMK (zobrazená posledná známa telemetria)",
        "total_active": len(enriched_vehicles),
        "total_matched": matched_count,
        "vehicles": enriched_vehicles
    }


class OccupancyReportRequest(BaseModel):
    level: int  # 1 = Prázdny, 2 = Poloplný, 3 = Plný
    current_stop_name: Optional[str] = None


@app.post("/api/v1/vehicle/{vehicle_id}/occupancy")
def report_vehicle_occupancy(vehicle_id: str, req: OccupancyReportRequest):
    """
    Crowdsourcing endpoint pre nahlásenie zaplnenosti vozidla (1 = Prázdny, 2 = Poloplný, 3 = Plný).
    Hodnota sa uloží do pamäte k danému vozidlu spolu s časom nahlásenia a aktuálnou zastávkou.
    Expiruje automaticky po 5 minútach alebo po príchode na novú zastávku.
    """
    if req.level not in (1, 2, 3):
        raise HTTPException(
            status_code=400,
            detail="Neplatná úroveň zaplnenosti. Povolené hodnoty: 1 (Prázdny), 2 (Poloplný), 3 (Plný)."
        )

    clean_vid = str(vehicle_id).strip()
    stop_name = req.current_stop_name.strip() if req.current_stop_name else None

    # Ak frontend neposlal názov zastávky, pokúsime sa ho zistiť z aktuálneho live feedu
    if not stop_name:
        try:
            active_list = live_feed.get_live_vehicles() or LAST_SEEN_CACHE
            for v in active_list:
                if str(v.get("vehicle_id")) == clean_vid:
                    stop_name = v.get("current_stop_name")
                    break
        except Exception:
            pass

    recorded = occupancy_service.set_occupancy(
        vehicle_id=clean_vid,
        level=req.level,
        current_stop_name=stop_name
    )

    return {
        "status": "ok",
        "message": f"Ďakujeme za nahlásenie! Úroveň obsadenosti: {recorded['label']}.",
        "vehicle_id": clean_vid,
        "occupancy": recorded
    }


@app.get("/api/v1/vehicle/{vehicle_id}/occupancy")
def get_vehicle_occupancy(vehicle_id: str):
    """
    Vráti aktuálnu platnú obsadenosť vozidla (alebo null ak vyexpirovala / nebola nahlásená).
    """
    clean_vid = str(vehicle_id).strip()
    occ = occupancy_service.get_occupancy(clean_vid)
    return {
        "status": "ok",
        "vehicle_id": clean_vid,
        "occupancy": occ
    }


@app.get("/api/v1/vehicle/search")
def search_vehicle_by_spz(spz: str = Query(..., description="EČV / ŠPZ autobusu (napr. KE-704IY)")):
    """
    Vyhľadá autobus podľa ŠPZ a zistí, či je aktuálne na linke v premávke (ak áno, vráti aj GPS).
    """
    fleet_record = fleet_service.get_by_spz(spz)
    if not fleet_record:
        # Kontrola, či ŠPZ nepatrí manuálne opravenému vozidlu
        clean_target_spz = spz.replace(" ", "").replace("-", "").upper()
        for k, ov in fleet_service.MANUAL_OVERRIDES.items():
            if ov.get("spz") and ov["spz"].replace(" ", "").replace("-", "").upper() == clean_target_spz:
                fleet_record = dict(ov)
                break
    if not fleet_record:
        raise HTTPException(status_code=404, detail=f"Vozidlo so ŠPZ '{spz}' sa v databáze nenašlo.")

    override = fleet_service.get_override(ev_cislo=fleet_record.get("evidencne_cislo"))
    if override:
        for k, val in override.items():
            if k == "spz" and not val and fleet_record.get("spz"):
                continue
            fleet_record[k] = val

    # Skontrolujeme, či vozidlo práve premáva
    live_info = None
    try:
        active_list = live_feed.get_live_vehicles() or LAST_SEEN_CACHE
        for v in active_list:
            v_spz = v.get("license_number")
            if v_spz and v_spz.replace(" ", "").replace("-", "").upper() == spz.replace(" ", "").replace("-", "").upper():
                live_info = v
                break
            matched = fleet_service.match_live_vehicle(
                vehicle_id=v["vehicle_id"],
                license_number=v.get("license_number"),
                line=v.get("line"),
                line_type=v.get("line_type"),
                raw_vehicle=v
            )
            if matched and matched.get("evidencne_cislo") == fleet_record.get("evidencne_cislo"):
                live_info = v
                break
    except Exception:
        pass

    if live_info:
        occ = occupancy_service.get_occupancy(
            vehicle_id=live_info.get("vehicle_id"),
            live_stop_name=live_info.get("current_stop_name")
        )
        live_info = dict(live_info)
        live_info["occupancy"] = occ

    return {
        "status": "ok",
        "vehicle": fleet_record,
        "is_currently_in_service": live_info is not None,
        "live_telemetry": live_info
    }


@app.get("/api/v1/vehicle/{evidencne_cislo}/history")
def get_vehicle_history(evidencne_cislo: str):
    """
    Získa podrobný profil, rok výroby, zaradenie a časovú os (timeline) histórie vozidla z portálu imhd.sk.
    """
    return get_imhd_vehicle_history(evidencne_cislo)


@app.get("/api/v1/fleet/all")
def get_fleet_all():
    """Vráti kompletný zoznam prevádzkyschopného vozového parku DPMK (v premávke aj v garáži)."""
    return get_fleet(only_active=True, only_parked=False)


@app.get("/api/v1/fleet")
def get_fleet(
    only_active: bool = Query(True, description="Filtrovať len aktívne prevádzkyschopné modely"),
    only_parked: bool = Query(True, description="Vrátiť výlučne vozidlá odstavené v depe/garáži (nie v live premávke)")
):
    """
    Vráti čistý zoznam vozového parku DPMK.
    Podľa požiadavky vracia výlučne 100% aktívne a prevádzkyschopné vozidlá,
    ktoré momentálne nevysielajú live GPS polohu (stoja v depe medzi zmenami),
    pričom zamedzuje akejkoľvek duplicite s vozidlami v premávke (Ubian API).
    """
    all_vehicles = fleet_service.get_all_vehicles(only_active=only_active)

    # Získanie aktuálne premávajúcich vozidiel z live telemetrie
    active_evs = set()
    active_spzs = set()
    try:
        active_list = live_feed.get_live_vehicles() or LAST_SEEN_CACHE
        for v in (active_list or []):
            is_tram = fleet_service.is_tram(
                vehicle_id=v.get("vehicle_id"),
                line=v.get("line"),
                line_type=v.get("line_type"),
                raw_vehicle=v
            )
            if is_tram:
                continue

            spz = v.get("license_number")
            if spz:
                active_spzs.add(spz.replace(" ", "").replace("-", "").upper())

            matched = fleet_service.match_live_vehicle(
                vehicle_id=v.get("vehicle_id"),
                license_number=spz,
                line=v.get("line"),
                line_type=v.get("line_type"),
                raw_vehicle=v
            )
            if matched:
                if matched.get("evidencne_cislo"):
                    active_evs.add(str(matched["evidencne_cislo"]).strip())
                if matched.get("spz"):
                    active_spzs.add(matched["spz"].replace(" ", "").replace("-", "").upper())
            elif v.get("vehicle_id"):
                s_vid = str(v.get("vehicle_id")).strip()
                active_evs.add(s_vid)
                if len(s_vid) >= 4:
                    active_evs.add(s_vid[-4:])
    except Exception:
        pass

    enriched = []
    parked = []
    for v in all_vehicles:
        item = dict(v)
        ev = str(item.get("evidencne_cislo") or "").strip()
        spz_clean = (item.get("spz") or "").replace(" ", "").replace("-", "").upper()

        is_in_service = (ev in active_evs) or (bool(spz_clean) and spz_clean in active_spzs)
        item["is_in_service"] = is_in_service
        enriched.append(item)
        if not is_in_service:
            parked.append(item)

    result_vehicles = parked if only_parked else enriched
    return {
        "status": "ok",
        "total_fleet": len(all_vehicles),
        "total_in_service": len(all_vehicles) - len(parked),
        "total_parked": len(parked),
        "total": len(result_vehicles),
        "vehicles": result_vehicles
    }


class OverrideRequest(BaseModel):
    evidencne_cislo: Optional[str] = None
    original_evidencne_cislo: Optional[str] = None
    vehicle_id: Optional[Any] = None
    model: str
    spz: Optional[str] = None
    verified: Optional[bool] = None


@app.post("/api/v1/admin/override")
def create_or_update_override(req: OverrideRequest):
    """
    Developer Mode endpoint pre manuálnu korekciu priradeného modelu, evidenčného čísla a ŠPZ vozidla.
    Zapisuje sa dynamicky do pamäte a do lokálneho súboru data/overrides.json.
    """
    if not req.evidencne_cislo and not req.vehicle_id and not req.original_evidencne_cislo:
        raise HTTPException(status_code=400, detail="Je potrebné zadať evidencne_cislo alebo vehicle_id.")
    if not req.model or not req.model.strip():
        raise HTTPException(status_code=400, detail="Model nesmie byť prázdny.")

    res = fleet_service.add_override(
        model=req.model.strip(),
        evidencne_cislo=str(req.evidencne_cislo).strip() if req.evidencne_cislo is not None and str(req.evidencne_cislo).strip() else None,
        original_evidencne_cislo=str(req.original_evidencne_cislo).strip() if req.original_evidencne_cislo is not None and str(req.original_evidencne_cislo).strip() else None,
        vehicle_id=str(req.vehicle_id).strip() if req.vehicle_id is not None and str(req.vehicle_id).strip() else None,
        spz=req.spz.strip() if req.spz else None,
        verified=req.verified
    )
    return {
        "status": "ok",
        "message": "Override úspešne uložený a aplikovaný.",
        "override": res
    }


class VerifyRequest(BaseModel):
    vehicle_id: Optional[Any] = None
    evidencne_cislo: Optional[str] = None
    verified: bool = True


@app.post("/api/v1/admin/verify")
def verify_vehicle_endpoint(req: VerifyRequest):
    """
    Developer Mode endpoint na rýchle označenie vozidla ako 'overené' (alebo zrušenie overenia).
    """
    success = fleet_service.set_verified(
        vehicle_id=str(req.vehicle_id).strip() if req.vehicle_id else None,
        ev_cislo=str(req.evidencne_cislo).strip() if req.evidencne_cislo else None,
        verified=req.verified
    )
    return {
        "status": "ok",
        "success": success,
        "verified": req.verified
    }


@app.get("/api/v1/admin/overrides")
def get_all_overrides():
    """Zoznam všetkých aktívnych manuálnych prepisov flotily."""
    return {
        "status": "ok",
        "overrides": fleet_service.MANUAL_OVERRIDES
    }



