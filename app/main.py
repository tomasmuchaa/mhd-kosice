import os
import json
import time
import uuid
import unicodedata
import asyncio
import random
import requests
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Union, Tuple
from fastapi import FastAPI, Query, HTTPException, Request, Form, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel

from app.services.fleet_service import FleetService
from app.services.live_feed_service import DpmkLiveFeed
from app.services.routing_engine import RoutingEngine
from app.services.imhd_scraper import get_imhd_vehicle_history
from app.services.occupancy_service import occupancy_service
from app.services.telemetry_db import telemetry_db

def strip_accents(text: str) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize('NFKD', text)
    cleaned = "".join(c for c in nfkd if not unicodedata.combining(c)).lower()
    return " ".join(cleaned.replace(',', ' ').replace('-', ' ').replace('.', ' ').split())

# Bezpečnostná a produkčná konfigurácia z premenných prostredia
DEBUG_MODE = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")
ADMIN_SECRET_KEY = os.getenv("ADMIN_SECRET_KEY", "dpmkadmin")
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))
FEEDBACK_LIMIT_PER_5MIN = int(os.getenv("FEEDBACK_LIMIT_PER_5MIN", "5"))
DISCORD_WEBHOOK_URL = os.getenv(
    "DISCORD_WEBHOOK_URL",
    "https://discord.com/api/webhooks/1559217074398568599/fnOJCLsrS85Jrd2lce_fWjSh0gCJayXWWf-fn95d38XrvRHhFo9Yd_lxPQFAlH21DEe8"
)

# Cesty k súborom
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
CSV_PATH = os.path.join(PROJECT_DIR, "data", "dpmk_autobusy_komplet.csv")
MAP_PATH = os.path.join(PROJECT_DIR, "mapa.html")
HISTORICAL_TRACK_PATH = os.path.join(PROJECT_DIR, "data", "historical_track.geojson")
MANIFEST_PATH = os.path.join(PROJECT_DIR, "manifest.json")
SERVICE_WORKER_PATH = os.path.join(PROJECT_DIR, "service-worker.js")
ROBOTS_PATH = os.path.join(PROJECT_DIR, "robots.txt")
SITEMAP_PATH = os.path.join(PROJECT_DIR, "sitemap.xml")
ICONS_DIR = os.path.join(PROJECT_DIR, "data", "icons")
STATIC_ICONS_DIR = os.path.join(PROJECT_DIR, "static", "icons")
FEEDBACK_DIR = os.path.join(PROJECT_DIR, "data", "feedback")
FEEDBACK_FILE = os.path.join(FEEDBACK_DIR, "feedback.json")
FEEDBACK_LEGACY_FILE = os.path.join(PROJECT_DIR, "data", "feedback.json")
FEEDBACK_IMAGES_DIR = os.path.join(FEEDBACK_DIR, "images")
os.makedirs(FEEDBACK_DIR, exist_ok=True)
os.makedirs(FEEDBACK_IMAGES_DIR, exist_ok=True)
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

# FastAPI aplikácia s vypnutým Swagger/Docs na produkcii (ochrana pred odhalením endpointov)
app = FastAPI(
    title="MHD Košice - Inteligentný Backend",
    description="Pokročilý systém pre sledovanie, vyhľadávanie a analýzu MHD v Košiciach.",
    version="1.0.0",
    docs_url="/docs" if DEBUG_MODE else None,
    redoc_url="/redoc" if DEBUG_MODE else None,
    openapi_url="/openapi.json" if DEBUG_MODE else None
)

# In-memory sliding-window pamäť pre rate limiting
RATE_LIMIT_STORE: Dict[str, List[float]] = {}
FEEDBACK_LIMIT_STORE: Dict[str, List[float]] = {}

def get_client_ip(request: Request) -> str:
    """Zistí skutočnú IP adresu klienta aj za Cloudflare alebo Render proxy."""
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip.strip()
    x_forwarded = request.headers.get("x-forwarded-for")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"

def verify_admin_token(request: Request):
    """
    Overí tajný administrátorský token z HTTP hlavičky (X-Admin-Token alebo Authorization: Bearer <token>).
    Ochraňuje citlivé zásahy do vozového parku (Developer Mode).
    """
    token = request.headers.get("X-Admin-Token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        elif auth_header:
            token = auth_header.strip()

    if not token or token != ADMIN_SECRET_KEY:
        raise HTTPException(
            status_code=403,
            detail="Prístup odoprený: Neplatný alebo chýbajúci administrátorský token (X-Admin-Token)."
        )

# Základný Rate Limiting Middleware (Ochrana pred DoS a zaspamovaním)
@app.middleware("http")
async def rate_limiting_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/"):
        client_ip = get_client_ip(request)
        now = time.time()

        if path == "/api/v1/feedback" and request.method == "POST":
            window_start = now - 300.0  # 5 minút
            FEEDBACK_LIMIT_STORE.setdefault(client_ip, [])
            FEEDBACK_LIMIT_STORE[client_ip] = [t for t in FEEDBACK_LIMIT_STORE[client_ip] if t > window_start]
            if len(FEEDBACK_LIMIT_STORE[client_ip]) >= FEEDBACK_LIMIT_PER_5MIN:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Príliš veľa odoslaných správ. Skúste to prosím o chvíľu."},
                    headers={"Retry-After": "60"}
                )
            FEEDBACK_LIMIT_STORE[client_ip].append(now)
        else:
            window_start = now - 60.0  # 1 minúta
            RATE_LIMIT_STORE.setdefault(client_ip, [])
            RATE_LIMIT_STORE[client_ip] = [t for t in RATE_LIMIT_STORE[client_ip] if t > window_start]
            if len(RATE_LIMIT_STORE[client_ip]) >= RATE_LIMIT_PER_MINUTE:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Príliš veľa požiadaviek (Rate limit prekročený). Skúste to prosím o chvíľu."},
                    headers={"Retry-After": "10"}
                )
            RATE_LIMIT_STORE[client_ip].append(now)

    return await call_next(request)

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
live_feed = DpmkLiveFeed(fleet_service=fleet_service)
routing_engine = RoutingEngine(live_feed=live_feed, fleet_service=fleet_service)

# Vynútené uvoľnenie pamäte po načítaní datasetov (optimalizácia RAM pre Northflank)
import gc
gc.collect()

# Background Collector pre kontinuálny zber telemetrie a obsadenosti (interval 15s)
BACKGROUND_COLLECTOR_TASK: Optional[asyncio.Task] = None

async def telemetry_collector_loop():
    """
    Asynchrónny zberateľ telemetrických dát a obsadenosti bežiaci na pozadí FastAPI servera.
    Dopytuje live feed každých 15 sekúnd a ukladá zmeny do SQLite (data/mhd_historia.db)
    s inteligentnou deduplikáciou (šetrenie pamäte a disku).
    """
    last_seen: Dict[Any, Tuple[float, float, int, int, Any]] = {}
    print("[Telemetry Collector] Kontinuálny zber dát na pozadí spustený (interval 15s).", flush=True)
    while True:
        try:
            # Spustenie v threadpoole, aby operácie nad SQLite a sieťou neblokovali async event loop
            await asyncio.to_thread(
                telemetry_db.collect_telemetry_batch,
                live_feed,
                occupancy_service,
                last_seen
            )
        except asyncio.CancelledError:
            print("[Telemetry Collector] Prijatý signál na ukončenie zberu dát.", flush=True)
            break
        except Exception as e:
            print(f"[Telemetry Collector] Chyba pri zbere dát: {e}", flush=True)

        try:
            await asyncio.sleep(15)
        except asyncio.CancelledError:
            break

@app.on_event("startup")
async def on_startup():
    """Uvoľnenie prebytočnej pamäte, synchronizácia cache a spustenie background collectora."""
    import gc
    gc.collect()

    global LAST_SEEN_CACHE
    for item in LAST_SEEN_CACHE:
        fleet_service.match_live_vehicle(item)

    global BACKGROUND_COLLECTOR_TASK
    if BACKGROUND_COLLECTOR_TASK is None or BACKGROUND_COLLECTOR_TASK.done():
        BACKGROUND_COLLECTOR_TASK = asyncio.create_task(telemetry_collector_loop())

@app.on_event("shutdown")
async def on_shutdown():
    """Čisté ukončenie zberateľa telemetrie pri vypínaní servera."""
    global BACKGROUND_COLLECTOR_TASK
    if BACKGROUND_COLLECTOR_TASK and not BACKGROUND_COLLECTOR_TASK.done():
        BACKGROUND_COLLECTOR_TASK.cancel()
        try:
            await BACKGROUND_COLLECTOR_TASK
        except asyncio.CancelledError:
            pass


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

    endpoints = {
        "live_vehicles": "/api/v1/vehicles/live",
        "fleet": "/api/v1/fleet",
        "stops": "/api/v1/stops",
        "stop_departures": "/api/v1/stops/{stop_id}/departures",
        "search_by_spz": "/api/v1/vehicle/search?spz=KE-704IY",
        "vehicle_occupancy": "/api/v1/vehicle/{vehicle_id}/occupancy",
        "vehicle_assignment_stats": "/api/v1/vehicle/{vehicle_id}/assignment-stats",
        "feedback": "/api/v1/feedback",
        "mapa": "/mapa",
        "ikonky": "/ikonky",
        "manifest": "/manifest.json",
        "robots": "/robots.txt",
        "sitemap": "/sitemap.xml"
    }
    if DEBUG_MODE:
        endpoints["docs"] = "/docs"
        endpoints["historical_track"] = "/api/v1/track/historical"
        endpoints["walking_transfers"] = "/api/v1/routing/transfers"
        endpoints["journey_planner"] = "/api/v1/routing/journey?from_id=1000000178&to_id=1000000030"

    return {
        "service": "MHD Košice API",
        "status": "online",
        "endpoints": endpoints
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

@app.get("/favicon.ico")
@app.get("/favicon.png")
def get_favicon():
    """Hlavná favicona aplikácie Nexigo."""
    fav_path = os.path.join(STATIC_ICONS_DIR, "favicon.png")
    if os.path.exists(fav_path):
        return FileResponse(fav_path, media_type="image/png", headers={"Cache-Control": "no-cache"})
    raise HTTPException(status_code=404, detail="Favicon nebola nájdená.")

@app.get("/static/icons/{icon_name}")
def get_static_icon(icon_name: str):
    """PWA Ikony aplikácie v static/icons/."""
    icon_path = os.path.join(STATIC_ICONS_DIR, icon_name)
    if os.path.exists(icon_path):
        return FileResponse(icon_path, media_type="image/png", headers={"Cache-Control": "no-cache"})
    raise HTTPException(status_code=404, detail="Ikona nebola nájdená.")

@app.get("/robots.txt", response_class=FileResponse)
def get_robots():
    """robots.txt pre indexáciu vyhľadávačmi (Google, Bing)."""
    if os.path.exists(ROBOTS_PATH):
        return FileResponse(ROBOTS_PATH, media_type="text/plain")
    raise HTTPException(status_code=404, detail="robots.txt nebol nájdený.")

@app.get("/sitemap.xml", response_class=FileResponse)
def get_sitemap():
    """sitemap.xml pre vyhľadávače."""
    if os.path.exists(SITEMAP_PATH):
        return FileResponse(SITEMAP_PATH, media_type="application/xml")
    raise HTTPException(status_code=404, detail="sitemap.xml nebol nájdený.")

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
    time: Optional[str] = Query(None, description="Čas odchodu vo formáte HH:MM (spätná kompatibilita)"),
    departure_time: Optional[str] = Query(None, description="Čas odchodu alebo príchodu (ISO reťazec alebo HH:MM)"),
    time_type: str = Query("departure", description="Typ času: 'departure' (odchod o...) alebo 'arrival' (príchod do...)"),
    direct_only: bool = Query(False, description="Vyhľadať iba priame spojenia bez prestupu")
):
    """
    Multimodálny vyhľadávač trás MHD Košice (Journey Planner):
    Nájde najrýchlejšiu trasu medzi počiatočnou (alebo GPS polohou) a cieľovou zastávkou pomocou Dijkstrovho algoritmu,
    využíva sieť peších prestupov a živé/plánované dáta o spojoch a meškaniach.
    Podporuje voľbu času (teraz, odchod o..., príchod do...) a filter iba priamych spojov (direct_only).
    """
    parsed_from_id: Optional[Union[int, str]] = None
    from_coords: Optional[Tuple[float, float]] = None

    if isinstance(from_lat, (int, float)) and isinstance(from_lon, (int, float)):
        from_coords = (float(from_lat), float(from_lon))
    elif from_id is not None and not hasattr(from_id, "default"):
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

    effective_dep_time = departure_time if isinstance(departure_time, str) else (time if isinstance(time, str) else None)
    is_direct = direct_only if isinstance(direct_only, bool) else False
    t_type = time_type if isinstance(time_type, str) else "departure"

    try:
        result = routing_engine.plan_multiple_journeys(
            from_id=parsed_from_id,
            to_id=parsed_to_id,
            from_coords=from_coords,
            departure_time_str=effective_dep_time,
            direct_only=is_direct,
            time_type=str(t_type).lower(),
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

        dep_delay = int(dep.get("delay_minutes", 0) or 0)
        dep_item = {
            **dep,
            "delay_minutes": dep_delay,
            "ai_predicted_delay": max(0, dep_delay + random.randint(-1, 2)),
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
    raw_vehicles = []
    try:
        raw_vehicles = live_feed.get_live_vehicles()
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

    # TOP najviac meškajúcich konkrétnych vozidiel (obohatené o model a ev. číslo z fleet_service)
    sorted_delayed_vehicles = sorted(raw_vehicles, key=lambda x: int(x.get("delay_minutes") or 0), reverse=True)
    top_delayed_vehicles = []
    for v in sorted_delayed_vehicles[:10]:
        d_min = int(v.get("delay_minutes") or 0)
        if d_min > 0:
            matched_fleet = fleet_service.match_live_vehicle(
                vehicle_id=v.get("vehicle_id"),
                license_number=v.get("license_number"),
                line=v.get("line"),
                line_type=v.get("line_type"),
                raw_vehicle=v
            ) or {}
            top_delayed_vehicles.append({
                "vehicle_id": v.get("vehicle_id"),
                "line": v.get("line"),
                "line_type": v.get("line_type"),
                "destination": v.get("destination"),
                "delay_minutes": d_min,
                "evidencne_cislo": matched_fleet.get("evidencne_cislo") or v.get("evidencne_cislo"),
                "model": matched_fleet.get("model") or v.get("model") or "Autobus DPMK",
                "license_number": matched_fleet.get("spz") or v.get("license_number"),
                "current_stop_name": v.get("current_stop_name"),
                "fleet_info": matched_fleet
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
    except Exception as e:
        # Ak by Ubian zlyhal, použijeme cache
        raw_vehicles = []

    # Ak je práve nočná pauza (0 vozidiel online) a máme povolený fallback
    if len(raw_vehicles) == 0 and include_fallback and len(LAST_SEEN_CACHE) > 0:
        sanitized_fallback = []
        for x in LAST_SEEN_CACHE:
            item_copy = dict(x)
            s_vid = str(item_copy.get("vehicle_id") or "").strip().replace("#", "")
            raw_ev = str(item_copy.get("evidencne_cislo") or (item_copy.get("fleet_info") or {}).get("evidencne_cislo") or "").strip().replace("#", "")
            ov = fleet_service.get_override(vehicle_id=s_vid, ev_cislo=raw_ev)
            is_ver = fleet_service.is_vehicle_verified(vehicle_id=s_vid, ev_cislo=raw_ev)
            if ov or is_ver:
                matched_ov = ov or {}
                if matched_ov.get("model"):
                    item_copy["model"] = matched_ov["model"]
                    if item_copy.get("fleet_info"):
                        item_copy["fleet_info"]["model"] = matched_ov["model"]
                if matched_ov.get("evidencne_cislo"):
                    item_copy["evidencne_cislo"] = matched_ov["evidencne_cislo"]
                    if item_copy.get("fleet_info"):
                        item_copy["fleet_info"]["evidencne_cislo"] = matched_ov["evidencne_cislo"]
                is_tram_item = fleet_service.is_tram(vehicle_id=s_vid, line=item_copy.get("line"), line_type=item_copy.get("line_type"), raw_vehicle=item_copy)
                if is_tram_item:
                    item_copy["license_number"] = None
                    if item_copy.get("fleet_info"):
                        item_copy["fleet_info"]["spz"] = None
                elif matched_ov.get("spz"):
                    item_copy["license_number"] = matched_ov["spz"]
                    if item_copy.get("fleet_info"):
                        item_copy["fleet_info"]["spz"] = matched_ov["spz"]
                item_copy["is_verified"] = True
                item_copy["verified"] = True
                if item_copy.get("fleet_info"):
                    item_copy["fleet_info"]["is_verified"] = True
                    item_copy["fleet_info"]["verified"] = True
            sanitized_fallback.append(item_copy)

        return {
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "is_live": False,
            "note": "Nočná pauza DPMK (zobrazená posledná známa telemetria s overenou identitou)",
            "total_active": len(sanitized_fallback),
            "total_matched": sum(1 for x in sanitized_fallback if x.get("matched")),
            "vehicles": sanitized_fallback
        }

    enriched_vehicles = []
    matched_count = 0

    for v in raw_vehicles:
        s_vid = str(v.get("vehicle_id") or "").strip().replace("#", "")
        ubian_spz = v.get("license_number")
        ubian_model = v.get("model")
        ubian_vin = v.get("vehicle_vin")
        ubian_ev = v.get("evidencne_cislo")

        # 1. Kontrola trakcie
        is_tram = fleet_service.is_tram(
            vehicle_id=s_vid,
            line=v.get("line"),
            line_type=v.get("line_type"),
            raw_vehicle=v
        )

        # 2. VŽDY prioritne voláme match_live_vehicle, kde MANUAL_OVERRIDES bezpodmienečne prepisuje raw dáta
        fleet_data = fleet_service.match_live_vehicle(
            vehicle_id=s_vid,
            license_number=ubian_spz,
            line=v.get("line"),
            line_type=v.get("line_type"),
            raw_vehicle=v
        )

        # 3. NAJVYŠŠIA AUTORITA PRAVDY: Overenie a získanie overrides s absolútnou prioritou
        final_ev = (fleet_data.get("evidencne_cislo") if fleet_data else None) or ubian_ev
        override = fleet_service.get_override(vehicle_id=s_vid, ev_cislo=final_ev, license_number=ubian_spz)
        is_verified = bool(fleet_service.is_vehicle_verified(vehicle_id=s_vid, ev_cislo=final_ev, license_number=ubian_spz) or (fleet_data and fleet_data.get("is_verified")))

        if override or is_verified:
            ov = override or fleet_data or {}
            final_ev = ov.get("evidencne_cislo") or final_ev
            final_rok = ov.get("rok_vyroby") or (fleet_data.get("rok_vyroby") if fleet_data else None)
            final_vin = ov.get("vin") or ubian_vin or (fleet_data.get("vin") if fleet_data else None)
            if is_tram:
                final_spz = None
                final_model = ov.get("model") or "Električka DPMK"
            else:
                final_model = ov.get("model") or (fleet_data.get("model") if fleet_data else "Autobus DPMK")
                final_spz = ov.get("spz") if ov.get("spz") is not None else (fleet_data.get("spz") if fleet_data else None)
            is_verified = True
        else:
            final_rok = fleet_data.get("rok_vyroby") if fleet_data else None
            final_vin = ubian_vin or (fleet_data.get("vin") if fleet_data else None)
            if is_tram:
                final_spz = None
                final_model = (fleet_data.get("model") if fleet_data else None) or ubian_model or "Električka DPMK"
                if str(final_model).strip().upper() == "TRAM":
                    final_model = "Električka DPMK"
            else:
                if fleet_data and fleet_data.get("model"):
                    final_model = fleet_data["model"]
                elif ubian_model and str(ubian_model).strip().upper() not in ["BUS", "AUTOBUS"]:
                    final_model = ubian_model
                else:
                    final_model = "Autobus DPMK"

                final_spz = (fleet_data.get("spz") if fleet_data else None) or ubian_spz

        # Typ vozidla - fallback ak nie je konkrétny model
        line_type = str(v.get("line_type") or "").upper()
        if not final_model:
            if is_tram or line_type == "TRAM" or v.get("line") in ["1", "2", "3", "4", "5", "6", "7", "9", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"]:
                final_model = "Električka DPMK"
                if not final_ev:
                    final_ev = str(v["vehicle_id"]) if v.get("vehicle_id") else None
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

        # Staleness calculation pre jednotný stav vozidla
        is_inactive = False
        last_comm = v.get("last_communication")
        if last_comm:
            try:
                comm_str = str(last_comm).replace("Z", "+00:00")
                comm_dt = datetime.fromisoformat(comm_str)
                now = datetime.now(comm_dt.tzinfo) if comm_dt.tzinfo else datetime.now()
                if (now - comm_dt).total_seconds() >= 180:
                    is_inactive = True
            except Exception:
                pass
        elif not v.get("latitude"):
            is_inactive = True

        status_text = "neaktívne (v garáži/pauza)" if is_inactive else "v premávke"

        # AI Beta Predikcia meškania (placeholder pred nasadením reálneho AI modelu z Data Collectora)
        cur_delay = int(v.get("delay_minutes", 0) or 0)
        ai_delta = random.randint(-1, 2)
        ai_predicted_delay = max(0, cur_delay + ai_delta)

        item = {
            "vehicle_id": v["vehicle_id"],
            "license_number": final_spz,
            "model": final_model,
            "evidencne_cislo": final_ev,
            "line": v.get("line"),
            "line_type": v.get("line_type"),
            "line_name": v.get("line_name"),
            "destination": v.get("destination"),
            "destination_full": v.get("destination_full"),
            "latitude": v.get("latitude"),
            "longitude": v.get("longitude"),
            "delay_minutes": cur_delay,
            "ai_predicted_delay": ai_predicted_delay,
            "is_on_stop": v.get("is_on_stop", False),
            "current_stop_name": v.get("current_stop_name"),
            "status": status_text,
            "status_text": status_text,
            "is_inactive": is_inactive,
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

    if is_live and enriched_vehicles:
        LAST_SEEN_CACHE = enriched_vehicles

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
    level: Optional[int] = None  # 1 = Prázdny, 2 = Poloplný, 3 = Plný
    occupancy_level: Optional[int] = None
    current_stop_name: Optional[str] = None
    line: Optional[str] = None


@app.post("/api/v1/vehicle/{vehicle_id}/occupancy")
def report_vehicle_occupancy(vehicle_id: str, req: OccupancyReportRequest):
    """
    Crowdsourcing endpoint pre nahlásenie zaplnenosti vozidla (1 = Prázdny, 2 = Poloplný, 3 = Plný).
    Hodnota sa perzistentne zapíše do databázy (occupancy_reports) aj do in-memory pamäte
    k danému vozidlu spolu s časom nahlásenia a aktuálnou zastávkou.
    Expiruje automaticky po 5 minútach alebo po príchode na novú zastávku.
    """
    eff_level = req.occupancy_level if req.occupancy_level is not None else req.level
    if eff_level not in (1, 2, 3):
        raise HTTPException(
            status_code=400,
            detail="Neplatná úroveň zaplnenosti. Povolené hodnoty: 1 (Prázdny), 2 (Poloplný), 3 (Plný)."
        )

    clean_vid = str(vehicle_id).strip()
    stop_name = req.current_stop_name.strip() if req.current_stop_name else None
    line = req.line.strip() if req.line else None

    # Ak frontend neposlal názov zastávky alebo linku, pokúsime sa ich zistiť z aktuálneho live feedu
    if not stop_name or not line:
        try:
            active_list = live_feed.get_live_vehicles() or LAST_SEEN_CACHE
            for v in active_list:
                if str(v.get("vehicle_id")) == clean_vid:
                    if not stop_name:
                        stop_name = v.get("current_stop_name")
                    if not line:
                        line = str(v.get("line") or "").strip()
                    break
        except Exception:
            pass

    # 1. Okamžitý perzistentný zápis do SQLite tabuľky occupancy_reports
    telemetry_db.log_occupancy_report(
        vehicle_id=clean_vid,
        level=eff_level,
        line=line,
        stop_name=stop_name
    )

    # 2. Uloženie do in-memory pamäte vozidla s časovou pečiatkou pre okamžité zobrazenie v UI
    recorded = occupancy_service.set_occupancy(
        vehicle_id=clean_vid,
        level=eff_level,
        current_stop_name=stop_name,
        line=line
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
        cur_d = int(live_info.get("delay_minutes", 0) or 0)
        live_info["ai_predicted_delay"] = max(0, cur_d + random.randint(-1, 2))

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


@app.get("/api/v1/vehicle/{vehicle_id}/assignment-stats")
def get_vehicle_assignment_stats(
    vehicle_id: str,
    ev_cislo: Optional[str] = Query(None, description="Voliteľné evidenčné číslo vozidla pre presné párovanie"),
    days: int = Query(14, ge=1, le=90, description="Počet dní do minulosti pre štatistiku (predvolene 14)"),
    min_records: int = Query(10, ge=1, description="Minimálny počet vzoriek pre zobrazenie štatistiky (inak has_data: false)")
):
    """
    Vráti reálnu štatistiku nasadzovania vozidla na linky za posledných N dní (napr. 14 dní).
    Prepojí zadané vehicle_id / evidenčné číslo s historickými polohami v SQLite databáze.
    """
    v_clean = str(vehicle_id).strip()
    if hasattr(ev_cislo, 'default'):
        ev_clean = None
    elif ev_cislo is not None:
        ev_clean = str(ev_cislo).strip()
    else:
        ev_clean = None
    days_val = int(days.default) if hasattr(days, 'default') else int(days)
    min_rec_val = int(min_records.default) if hasattr(min_records, 'default') else int(min_records)

    candidate_ids = set()
    if v_clean.isdigit():
        candidate_ids.add(int(v_clean))
    if ev_clean and ev_clean.isdigit():
        candidate_ids.add(int(ev_clean))

    # 1. Mapovanie cez TRANSDATA_MAPPING
    for tid, ev in fleet_service.TRANSDATA_MAPPING.items():
        if v_clean == str(tid) or (ev_clean and ev_clean == str(tid)):
            if str(ev).isdigit():
                candidate_ids.add(int(ev))
        if v_clean == str(ev) or (ev_clean and ev_clean == str(ev)):
            if str(tid).isdigit():
                candidate_ids.add(int(tid))

    # 2. Mapovanie cez match_live_vehicle
    if v_clean.isdigit():
        m = fleet_service.match_live_vehicle(vehicle_id=v_clean)
        if m and m.get("evidencne_cislo") and str(m["evidencne_cislo"]).isdigit():
            candidate_ids.add(int(m["evidencne_cislo"]))

    # 3. MANUAL_OVERRIDES
    for k, ov in fleet_service.MANUAL_OVERRIDES.items():
        ov_ev = str(ov.get("evidencne_cislo") or "")
        if v_clean in (str(k), ov_ev) or (ev_clean and ev_clean in (str(k), ov_ev)):
            if str(k).isdigit():
                candidate_ids.add(int(k))
            if ov_ev.isdigit():
                candidate_ids.add(int(ov_ev))

    # 4. Ak bolo zadané evidenčné číslo (napr. 5720, 4743), vyhľadáme možné TransData 7-miestne ID
    target_ev = ev_clean or (v_clean if len(v_clean) <= 4 and v_clean.isdigit() else None)
    if target_ev and 2 <= len(target_ev) <= 4 and target_ev.isdigit():
        last2 = target_ev[-2:]
        for prefix in ('12761', '12762', '12763', '12764', '12765', '12766', '12767', '12770', '12775', '12778', '12779', '12781', '12782'):
            tid = prefix + last2
            matched = fleet_service.match_live_vehicle(vehicle_id=tid)
            if matched and str(matched.get("evidencne_cislo")) == target_ev:
                candidate_ids.add(int(tid))

    # Identifikátor pre zobrazenie v odpovedi
    display_id = target_ev if target_ev else (int(v_clean) if v_clean.isdigit() else v_clean)

    return telemetry_db.get_vehicle_assignment_stats(
        vehicle_ids=sorted(list(candidate_ids)),
        days=days_val,
        min_records=min_rec_val,
        display_id=display_id
    )


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
        item["status"] = "v premávke" if is_in_service else "neaktívne (v garáži/pauza)"
        item["status_text"] = "v premávke" if is_in_service else "neaktívne (v garáži/pauza)"
        enriched.append(item)
        if not is_in_service:
            parked.append(item)

    result_vehicles = parked if only_parked else enriched
    return {
        "status": "ok",
        "total_fleet": len(all_vehicles),
        "total_in_service": len(all_vehicles) - len(parked),
        "total_parked": len(parked),
        "total_verified": sum(1 for x in all_vehicles if x.get("is_verified")),
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
    note: Optional[str] = None


@app.post("/api/v1/admin/override")
def create_or_update_override(req: OverrideRequest, request: Request):
    """
    Developer Mode endpoint pre manuálnu korekciu priradeného modelu, evidenčného čísla a ŠPZ vozidla.
    Zabezpečený tajným administrátorským tokenom (X-Admin-Token).
    Automaticky vyrieši kolízie evidenčných čísel prečíslovaním pôvodného vozidla na 90xxx.
    """
    verify_admin_token(request)

    clean_vid = str(req.vehicle_id).strip().replace("#", "") if req.vehicle_id is not None and str(req.vehicle_id).strip() else None
    clean_ev = str(req.evidencne_cislo).strip().replace("#", "") if req.evidencne_cislo is not None and str(req.evidencne_cislo).strip() else None
    clean_orig_ev = str(req.original_evidencne_cislo).strip().replace("#", "") if req.original_evidencne_cislo is not None and str(req.original_evidencne_cislo).strip() else None
    clean_spz = req.spz.strip().replace("#", "").upper() if req.spz and str(req.spz).strip() else None

    if not clean_ev and not clean_vid and not clean_orig_ev:
        raise HTTPException(status_code=400, detail="Je potrebné zadať evidencne_cislo alebo vehicle_id.")
    if not req.model or not req.model.strip():
        raise HTTPException(status_code=400, detail="Model nesmie byť prázdny.")

    res = fleet_service.set_override(
        model=req.model.strip(),
        evidencne_cislo=clean_ev,
        original_evidencne_cislo=clean_orig_ev,
        vehicle_id=clean_vid,
        spz=clean_spz,
        verified=True if req.verified is None else bool(req.verified),
        note=req.note.strip() if req.note else None
    )

    fleet_service.sync_override_to_caches(
        override=res,
        live_cache=getattr(live_feed, "_live_cache", []),
        last_seen_cache=LAST_SEEN_CACHE
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
def verify_vehicle_endpoint(req: VerifyRequest, request: Request):
    """
    Developer Mode endpoint na rýchle označenie vozidla ako 'overené' (alebo zrušenie overenia).
    Zabezpečený tajným administrátorským tokenom (X-Admin-Token).
    """
    verify_admin_token(request)

    clean_vid = str(req.vehicle_id).strip().replace("#", "") if req.vehicle_id is not None and str(req.vehicle_id).strip() else None
    clean_ev = str(req.evidencne_cislo).strip().replace("#", "") if req.evidencne_cislo is not None and str(req.evidencne_cislo).strip() else None

    success = fleet_service.set_verified(
        vehicle_id=clean_vid,
        ev_cislo=clean_ev,
        verified=req.verified
    )

    ov = fleet_service.get_override(vehicle_id=clean_vid, ev_cislo=clean_ev)
    if ov:
        fleet_service.sync_override_to_caches(
            override=ov,
            live_cache=getattr(live_feed, "_live_cache", []),
            last_seen_cache=LAST_SEEN_CACHE
        )

    return {
        "status": "ok",
        "success": success,
        "verified": req.verified
    }


@app.get("/api/v1/admin/overrides")
def get_all_overrides(request: Request):
    """Zoznam všetkých aktívnych manuálnych prepisov flotily (vyžaduje X-Admin-Token)."""
    verify_admin_token(request)
    return {
        "status": "ok",
        "overrides": fleet_service.MANUAL_OVERRIDES
    }


class FanSuggestOverrideRequest(BaseModel):
    vehicle_id: Optional[Any] = None
    evidencne_cislo: Optional[str] = None
    current_model: Optional[str] = None
    current_spz: Optional[str] = None
    suggested_model: str
    suggested_spz: Optional[str] = None
    note: Optional[str] = None


@app.post("/api/v1/fan/suggest-override")
def suggest_fan_override(req: FanSuggestOverrideRequest):
    """
    Verejný endpoint pre fanúšikov dopravy a cestujúcich na navrhnutie opravy údajov vozidla.
    Požiadavka sa uloží do čakajúceho zoznamu (pending) na overenie dispečerom v Developer móde.
    """
    if not req.suggested_model or not req.suggested_model.strip():
        raise HTTPException(status_code=400, detail="Navrhovaný model nesmie byť prázdny.")
    if not req.vehicle_id and not req.evidencne_cislo:
        raise HTTPException(status_code=400, detail="Je potrebné zadať aspoň vehicle_id alebo evidenčné číslo vozidla.")

    record = fleet_service.add_fan_suggestion(
        suggested_model=req.suggested_model.strip(),
        evidencne_cislo=str(req.evidencne_cislo).strip() if req.evidencne_cislo is not None and str(req.evidencne_cislo).strip() else None,
        vehicle_id=str(req.vehicle_id).strip() if req.vehicle_id is not None and str(req.vehicle_id).strip() else None,
        current_model=req.current_model,
        current_spz=req.current_spz,
        suggested_spz=req.suggested_spz,
        note=req.note
    )

    return {
        "status": "ok",
        "message": "Ďakujeme! Váš návrh bol odoslaný dispečerom na overenie.",
        "request": record
    }


@app.get("/api/v1/admin/requests")
def get_admin_pending_requests(request: Request, status: Optional[str] = "pending"):
    """
    Developer Mode endpoint: vráti zoznam čakajúcich požiadaviek od fanúšikov dopravy.
    Vyžaduje X-Admin-Token.
    """
    verify_admin_token(request)
    pending = fleet_service.get_pending_requests(status=status)
    return {
        "status": "ok",
        "count": len(pending),
        "requests": pending
    }


@app.post("/api/v1/admin/requests/{request_id}/approve")
def approve_admin_request(request_id: str, request: Request):
    """
    Developer Mode endpoint: Schváli čakajúcu požiadavku od fanúšika,
    automaticky zapíše schválený model a ŠPZ do existujúceho systému perzistentných prepisov (overrides.json)
    a okamžite aktualizuje pamäť servera a live dáta vozidiel.
    """
    verify_admin_token(request)
    req = fleet_service.approve_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail=f"Požiadavka s ID '{request_id}' nebola nájdená.")

    ov = fleet_service.get_override(vehicle_id=req.get("vehicle_id"), ev_cislo=req.get("evidencne_cislo"))
    if ov:
        fleet_service.sync_override_to_caches(
            override=ov,
            live_cache=getattr(live_feed, "_live_cache", []),
            last_seen_cache=LAST_SEEN_CACHE
        )

    return {
        "status": "ok",
        "message": "Požiadavka bola úspešne schválená a zmeny boli zapísané do flotily.",
        "request": req
    }


@app.post("/api/v1/admin/requests/{request_id}/reject")
def reject_admin_request(request_id: str, request: Request):
    """
    Developer Mode endpoint: Zamietne čakajúcu požiadavku od fanúšika (nastaví status na 'rejected').
    """
    verify_admin_token(request)
    req = fleet_service.reject_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail=f"Požiadavka s ID '{request_id}' nebola nájdená.")

    return {
        "status": "ok",
        "message": "Požiadavka bola zamietnutá.",
        "request": req
    }


class FeedbackRequest(BaseModel):
    message: str
    category: Optional[str] = "Iné"
    contact: Optional[str] = None
    screen_width: Optional[str] = None
    screen_height: Optional[str] = None
    user_agent: Optional[str] = None


@app.post("/api/v1/feedback")
async def submit_feedback(
    request: Request,
    message: str = Form(...),
    category: Optional[str] = Form("Iné"),
    contact: Optional[str] = Form(None),
    screen_width: Optional[str] = Form(None),
    screen_height: Optional[str] = Form(None),
    user_agent: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None)
):
    """
    Verejný endpoint pre zber spätnej väzby a hlásenie chýb od používateľov imhd.sk.
    Odosiela štruktúrovaný Discord Embed so screenshotom priamo na dispečerský Discord webhook.
    Záznam sa zároveň zálohuje lokálne do súboru data/feedback/feedback.json.
    """
    msg = (message or "").strip()
    if not msg or len(msg) < 3:
        raise HTTPException(status_code=400, detail="Správa musí obsahovať aspoň 3 znaky.")
    if len(msg) > 3000:
        raise HTTPException(status_code=400, detail="Správa je príliš dlhá (max 3000 znakov).")

    image_filename = None
    image_content = None
    image_mime = "image/png"
    image_url = None

    if image and image.filename:
        ext = os.path.splitext(image.filename)[1].lower()
        if ext not in ALLOWED_IMAGE_EXTS:
            raise HTTPException(
                status_code=400,
                detail=f"Nepodporovaný formát obrázka. Povolené formáty: {', '.join(sorted(ALLOWED_IMAGE_EXTS))}"
            )

        image_content = await image.read()
        if len(image_content) > MAX_IMAGE_SIZE:
            raise HTTPException(
                status_code=400,
                detail="Priložený obrázok presahuje maximálnu povolenú veľkosť 5 MB."
            )

        if ext in (".jpg", ".jpeg"):
            image_mime = "image/jpeg"
        elif ext == ".webp":
            image_mime = "image/webp"

        image_filename = f"feedback_{int(time.time())}_{uuid.uuid4().hex[:6]}{ext}"

        # Uložíme kópiu lokálne pre archiváciu
        saved_path = os.path.join(FEEDBACK_IMAGES_DIR, image_filename)
        try:
            with open(saved_path, "wb") as f:
                f.write(image_content)
            image_url = f"/api/v1/feedback/images/{image_filename}"
        except Exception as e:
            print(f"Warning: lokálne uloženie obrázka zlyhalo: {e}")

    client_ip = get_client_ip(request)
    browser_ua = (user_agent or "").strip() or request.headers.get("user-agent", "")

    s_w = None
    s_h = None
    if screen_width and str(screen_width).isdigit():
        s_w = int(screen_width)
    if screen_height and str(screen_height).isdigit():
        s_h = int(screen_height)

    clean_category = (category or "Iné").strip()

    # Príprava farebného akcentu embedu podľa kategórie
    color_map = {
        "Nesprávny model / ŠPZ": 0xef4444,  # Červená
        "Chyba plánovača trás": 0x3b82f6,   # Modrá
        "Chyba mapy alebo GPS": 0x10b981,   # Smaragdová
        "Nápad na vylepšenie": 0xf59e0b,    # Jantárová
        "Iné": 0x64748b                      # Bridlicová
    }
    embed_color = color_map.get(clean_category, 0x0ea5e9)

    contact_val = contact.strip() if (contact and contact.strip()) else "Anonym / Neuvedený"
    resolution_val = f"{s_w} × {s_h} px" if (s_w and s_h) else "Neuvedené"
    device_val = browser_ua if browser_ua else "Neuvedené"

    embed = {
        "title": f"💬 Nová spätná väzba: {clean_category}",
        "color": embed_color,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fields": [
            {
                "name": "👤 Používateľ / Kontakt",
                "value": contact_val,
                "inline": True
            },
            {
                "name": "📱 Rozlíšenie obrazovky",
                "value": resolution_val,
                "inline": True
            },
            {
                "name": "📝 Popis chyby",
                "value": msg[:1024],
                "inline": False
            },
            {
                "name": "🌐 Prehliadač / Zariadenie",
                "value": f"`{device_val[:350]}`" if len(device_val) <= 350 else f"`{device_val[:350]}...`",
                "inline": False
            }
        ],
        "footer": {
            "text": f"MHD Košice • Klient IP: {client_ip}"
        }
    }

    if image_content and image_filename:
        embed["image"] = {
            "url": f"attachment://{image_filename}"
        }

    discord_payload = {
        "username": "MHD Košice Dispečing",
        "embeds": [embed]
    }

    # 1. Odoslanie na Discord Webhook
    discord_sent = False
    discord_error = None
    if DISCORD_WEBHOOK_URL:
        try:
            if image_content and image_filename:
                files = {
                    "files[0]": (image_filename, image_content, image_mime)
                }
                data = {
                    "payload_json": json.dumps(discord_payload)
                }
                resp = requests.post(DISCORD_WEBHOOK_URL, data=data, files=files, timeout=12)
            else:
                resp = requests.post(DISCORD_WEBHOOK_URL, json=discord_payload, timeout=10)

            if resp.status_code in (200, 204):
                discord_sent = True
            else:
                discord_error = f"HTTP {resp.status_code}: {resp.text}"
                print(f"Discord webhook error: {discord_error}")
        except Exception as e:
            discord_error = str(e)
            print(f"Chyba pri odosielaní na Discord Webhook: {e}")

    # 2. Lokálne zálohovanie do feedback.json
    entry = {
        "id": f"fb_{int(time.time())}_{uuid.uuid4().hex[:6]}",
        "timestamp": datetime.now().isoformat(),
        "category": clean_category,
        "message": msg,
        "contact": contact.strip() if contact else None,
        "client_ip": client_ip,
        "user_agent": browser_ua,
        "screen_width": s_w,
        "screen_height": s_h,
        "screen_resolution": f"{s_w}x{s_h}" if (s_w and s_h) else None,
        "image_filename": image_filename,
        "image_url": image_url,
        "discord_sent": discord_sent
    }

    try:
        feedback_list = []
        target_file = FEEDBACK_FILE
        if os.path.exists(target_file):
            try:
                with open(target_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        feedback_list = data
            except Exception:
                feedback_list = []

        feedback_list.append(entry)
        with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
            json.dump(feedback_list, f, ensure_ascii=False, indent=2)
        with open(FEEDBACK_LEGACY_FILE, "w", encoding="utf-8") as f:
            json.dump(feedback_list, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Chyba pri lokálnom zápise feedback.json: {e}")

    return {
        "status": "ok",
        "message": "Ďakujeme za vašu spätnú väzbu! Pomáha nám zlepšovať systém MHD Košice.",
        "discord_sent": discord_sent,
        "image_uploaded": bool(image_filename),
        "image_url": image_url
    }


@app.get("/api/v1/feedback/images/{filename}")
def get_feedback_image(filename: str):
    """Bezpečné zobrazenie priloženého screenshotu zo spätnej väzby."""
    safe_filename = os.path.basename(filename)
    file_path = os.path.join(FEEDBACK_IMAGES_DIR, safe_filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Obrázok nebol nájdený.")
    return FileResponse(file_path)


@app.get("/api/v1/admin/feedback")
def get_all_feedback(request: Request):
    """Zoznam doručenej spätnej väzby (vyžaduje X-Admin-Token)."""
    verify_admin_token(request)
    feedback_list = []
    target_file = FEEDBACK_FILE if os.path.exists(FEEDBACK_FILE) else FEEDBACK_LEGACY_FILE
    if os.path.exists(target_file):
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    feedback_list = data
        except Exception:
            pass
    return {
        "status": "ok",
        "total": len(feedback_list),
        "feedback": feedback_list
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    # Uvicorn beží s 1 workerom na šetrenie pamäte (Northflank 256MB limit)
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, workers=1)
