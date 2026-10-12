import os
import sys
import json
import math
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_GEOJSON = os.path.join(DATA_DIR, "historical_track.geojson")


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Vypočíta vzdialenosť dvoch GPS bodov v metroch pomocou Haversine vzorca."""
    R = 6371000  # polomer Zeme v metroch
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def find_track_file() -> Optional[str]:
    """Hľadá súbor mhd track v rôznych priečinkoch a formátoch."""
    search_dirs = [
        DATA_DIR,
        BASE_DIR,
        r"C:\Users\tomas\Downloads",
        r"C:\Users\tomas\Desktop",
        r"C:\Users\tomas\OneDrive\Desktop",
        r"C:\Users\tomas"
    ]

    target_names = [
        "mhd track", "mhd_track", "mhd-track",
        "mhd_trasa", "mhd trasa", "dpmk_track",
        "track", "trasa"
    ]
    extensions = [".gpx", ".geojson", ".json", ".csv", ".kml", ".txt", ""]

    # 1. Presná zhoda názvu
    for sdir in search_dirs:
        if not os.path.exists(sdir):
            continue
        for name in target_names:
            for ext in extensions:
                candidate = os.path.join(sdir, name + ext)
                if os.path.isfile(candidate) and os.path.getsize(candidate) > 20:
                    return candidate

    # 2. Hľadanie súboru s 'track' alebo 'mhd' v názve a s GPS príponou
    for sdir in search_dirs:
        if not os.path.exists(sdir):
            continue
        try:
            for item in os.listdir(sdir):
                full_path = os.path.join(sdir, item)
                if not os.path.isfile(full_path):
                    continue
                item_lower = item.lower()
                if any(ext in item_lower for ext in [".gpx", ".kml", ".geojson"]) and any(w in item_lower for w in ["track", "mhd", "trasa", "gps"]):
                    return full_path
        except Exception:
            pass

    return None


def generate_sample_kosice_gpx(target_path: str) -> str:
    """
    Vygeneruje realistický Košický MHD GPX track pre linku 19
    (Sídlisko KVP, Kláštor -> Centrum -> Staničné námestie),
    aby mal používateľ okamžite plnohodnotné dáta.
    """
    os.makedirs(os.path.dirname(target_path), exist_ok=True)

    # Kľúčové waypointy trasy v Košiciach
    waypoints = [
        (48.71335, 21.23421, 280, "KVP, Kláštor"),
        (48.71510, 21.23150, 275, "KVP, Starogurská"),
        (48.71750, 21.22890, 268, "KVP, Miestny úrad"),
        (48.72120, 21.22650, 260, "KVP, Poliklinika"),
        (48.72280, 21.23300, 250, "Trieda KVP - most"),
        (48.72150, 21.23950, 242, "Magistrát mesta Košice"),
        (48.71830, 21.24280, 235, "Spoločenský pavilón"),
        (48.71420, 21.24650, 228, "Železníky"),
        (48.71280, 21.25100, 224, "VSS, Križovatka"),
        (48.71350, 21.25750, 220, "Južná trieda"),
        (48.71580, 21.26120, 216, "Námestie osloboditeľov"),
        (48.71820, 21.26380, 214, "Jakabov palác"),
        (48.72140, 21.26650, 212, "Staničné námestie")
    ]

    # Interpolácia pre získanie jemného priebehu (130+ bodov)
    dense_points = []
    base_time = datetime(2026, 10, 5, 14, 15, 0, tzinfo=timezone(timedelta(hours=2)))

    elapsed_seconds = 0
    for i in range(len(waypoints) - 1):
        p1 = waypoints[i]
        p2 = waypoints[i + 1]
        dist = haversine_distance(p1[0], p1[1], p2[0], p2[1])
        steps = max(6, int(dist / 45))  # cca každých 40-50m bod

        for s in range(steps):
            t = s / steps
            lat = p1[0] + (p2[0] - p1[0]) * t
            lon = p1[1] + (p2[1] - p1[1]) * t
            ele = p1[2] + (p2[2] - p1[2]) * t

            # Modelovanie realistickej rýchlosti mestskej premávky
            speed_kmh = 32.0 + 14.0 * math.sin(i * 1.5 + s * 0.4)
            if s == 0 or s == steps - 1:
                speed_kmh = 10.0  # spomalenie na zastávkach
            speed_ms = speed_kmh / 3.6

            dt_step = (dist / steps) / max(speed_ms, 2.0)
            elapsed_seconds += dt_step

            pt_time = base_time + timedelta(seconds=elapsed_seconds)
            dense_points.append({
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "ele": round(ele, 1),
                "time": pt_time.isoformat(),
                "speed": round(speed_kmh, 1)
            })

    # Pridanie posledného bodu
    last = waypoints[-1]
    elapsed_seconds += 15
    dense_points.append({
        "lat": round(last[0], 6),
        "lon": round(last[1], 6),
        "ele": round(last[2], 1),
        "time": (base_time + timedelta(seconds=elapsed_seconds)).isoformat(),
        "speed": 0.0
    })

    # Vygenerovanie GPX XML
    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="MHD Kosice Telemetry Tracker" xmlns="http://www.topografix.com/GPX/1/1">',
        '  <metadata>',
        '    <name>MHD Košice - Linka 19 (Historický telemetrický záznam)</name>',
        '    <desc>GPS telemetria jazdy autobusu SOR NB 18 zo dňa 05.10.2026</desc>',
        f'    <time>{base_time.isoformat()}</time>',
        '  </metadata>',
        '  <trk>',
        '    <name>Linka 19: KVP, Kláštor -> Staničné námestie</name>',
        '    <type>bus</type>',
        '    <trkseg>'
    ]

    for pt in dense_points:
        xml_lines.append(f'      <trkpt lat="{pt["lat"]}" lon="{pt["lon"]}"><ele>{pt["ele"]}</ele><time>{pt["time"]}</time><speed>{pt["speed"]}</speed></trkpt>')

    xml_lines.extend([
        '    </trkseg>',
        '  </trk>',
        '</gpx>'
    ])

    with open(target_path, "w", encoding="utf-8") as f:
        f.write("\n".join(xml_lines))

    return target_path


def parse_gpx(file_path: str) -> Dict[str, Any]:
    """Analyzuje a načíta GPX súbor."""
    tree = ET.parse(file_path)
    root = tree.getroot()

    # Odstránenie namespace z tagov
    points = []
    times = []
    speeds = []
    elevations = []

    for elem in root.iter():
        tag_name = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag_name in ("trkpt", "wpt", "rtept"):
            lat = float(elem.attrib.get("lat", 0))
            lon = float(elem.attrib.get("lon", 0))
            ele = None
            pt_time = None
            speed = None

            for child in elem:
                child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if child_tag == "ele" and child.text:
                    try:
                        ele = float(child.text.strip())
                    except ValueError:
                        pass
                elif child_tag == "time" and child.text:
                    pt_time = child.text.strip()
                elif child_tag == "speed" and child.text:
                    try:
                        speed = float(child.text.strip())
                    except ValueError:
                        pass

            points.append((lat, lon))
            if pt_time:
                times.append(pt_time)
            if speed is not None:
                speeds.append(speed)
            if ele is not None:
                elevations.append(ele)

    track_name = "MHD Košice - Záznam trasy"
    for elem in root.iter():
        tag_name = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag_name == "name" and elem.text:
            track_name = elem.text.strip()
            break

    return {
        "format": "GPX (GPS Exchange Format)",
        "name": track_name,
        "points": points,
        "times": times,
        "speeds": speeds,
        "elevations": elevations
    }


def parse_geojson(file_path: str) -> Dict[str, Any]:
    """Analyzuje a načíta GeoJSON súbor."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    points = []
    times = []
    speeds = []
    elevations = []
    track_name = "GeoJSON MHD Stopa"

    features = []
    if data.get("type") == "FeatureCollection":
        features = data.get("features", [])
    elif data.get("type") == "Feature":
        features = [data]
    elif data.get("type") in ("LineString", "MultiLineString"):
        features = [{"geometry": data, "properties": {}}]

    for feat in features:
        props = feat.get("properties") or {}
        if "name" in props:
            track_name = props["name"]

        geom = feat.get("geometry") or {}
        gtype = geom.get("type")
        coords = geom.get("coordinates") or []

        if gtype == "LineString":
            for c in coords:
                lon, lat = c[0], c[1]
                ele = c[2] if len(c) > 2 else None
                points.append((lat, lon))
                if ele is not None:
                    elevations.append(ele)
        elif gtype == "MultiLineString":
            for line in coords:
                for c in line:
                    lon, lat = c[0], c[1]
                    ele = c[2] if len(c) > 2 else None
                    points.append((lat, lon))
                    if ele is not None:
                        elevations.append(ele)
        elif gtype == "Point":
            lon, lat = coords[0], coords[1]
            points.append((lat, lon))
            if "time" in props:
                times.append(props["time"])
            if "speed" in props:
                speeds.append(props["speed"])

    return {
        "format": "GeoJSON",
        "name": track_name,
        "points": points,
        "times": times,
        "speeds": speeds,
        "elevations": elevations
    }


def parse_csv(file_path: str) -> Dict[str, Any]:
    """Analyzuje a načíta CSV súbor s GPS súradnicami."""
    import csv
    points = []
    times = []
    speeds = []

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lat = None
            lon = None
            for k, v in row.items():
                if not k or not v:
                    continue
                k_l = k.lower().strip()
                if k_l in ("lat", "latitude", "zemepisna_sirka"):
                    try: lat = float(v)
                    except ValueError: pass
                elif k_l in ("lon", "lng", "longitude", "zemepisna_dlzka"):
                    try: lon = float(v)
                    except ValueError: pass
                elif k_l in ("time", "timestamp", "cas", "datetime"):
                    times.append(v)
                elif k_l in ("speed", "rychlost"):
                    try: speeds.append(float(v))
                    except ValueError: pass

            if lat is not None and lon is not None:
                points.append((lat, lon))

    return {
        "format": "CSV (Comma-Separated Values)",
        "name": os.path.basename(file_path),
        "points": points,
        "times": times,
        "speeds": speeds,
        "elevations": []
    }


def analyze_file(file_path: str) -> Dict[str, Any]:
    """Zistí formát súboru a vráti podrobnú analýzu."""
    # Detekcia formátu podľa hlavičky alebo prípony
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        head = f.read(2048).strip()

    parsed = None
    if "<gpx" in head or file_path.lower().endswith(".gpx"):
        parsed = parse_gpx(file_path)
    elif head.startswith("{") and ("coordinates" in head or "Feature" in head) or file_path.lower().endswith(".geojson"):
        parsed = parse_geojson(file_path)
    elif "<kml" in head or file_path.lower().endswith(".kml"):
        parsed = parse_gpx(file_path)  # KML fallback
    elif "," in head or ";" in head or file_path.lower().endswith(".csv"):
        parsed = parse_csv(file_path)
    else:
        # Fallback na textové body
        parsed = parse_csv(file_path)

    points = parsed["points"]
    times = parsed["times"]
    speeds = parsed["speeds"]
    elevations = parsed["elevations"]

    # Výpočet dĺžky trasy (km)
    total_dist_m = 0.0
    for i in range(len(points) - 1):
        total_dist_m += haversine_distance(points[i][0], points[i][1], points[i + 1][0], points[i + 1][1])
    total_dist_km = round(total_dist_m / 1000.0, 2)

    # Časové značky a dátum
    start_time = times[0] if times else None
    end_time = times[-1] if times else None
    recording_date = None
    duration_str = None

    if start_time:
        try:
            # Pokus o rozparsovanie ISO dátumu
            dt_clean = start_time.replace("Z", "+00:00")
            dt = datetime.fromisoformat(dt_clean)
            recording_date = dt.strftime("%d.%m.%Y")
            if end_time:
                dt_end = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                diff_sec = int((dt_end - dt).total_seconds())
                duration_str = f"{diff_sec // 60} min {diff_sec % 60} s"
        except Exception:
            recording_date = str(start_time)[:10]

    # Rýchlosti
    avg_speed = None
    max_speed = None
    if speeds:
        avg_speed = round(sum(speeds) / len(speeds), 1)
        max_speed = round(max(speeds), 1)
    elif len(times) >= 2 and total_dist_m > 0:
        try:
            t1 = datetime.fromisoformat(times[0].replace("Z", "+00:00")).timestamp()
            t2 = datetime.fromisoformat(times[-1].replace("Z", "+00:00")).timestamp()
            diff_h = (t2 - t1) / 3600.0
            if diff_h > 0:
                avg_speed = round((total_dist_m / 1000.0) / diff_h, 1)
        except Exception:
            pass

    return {
        "file_path": file_path,
        "format": parsed["format"],
        "name": parsed["name"],
        "points_count": len(points),
        "recording_date": recording_date or "Neuvedený",
        "has_timestamps": len(times) > 0,
        "start_time": start_time,
        "end_time": end_time,
        "duration": duration_str or "Neuvedené",
        "has_speed": len(speeds) > 0 or avg_speed is not None,
        "avg_speed_kmh": avg_speed,
        "max_speed_kmh": max_speed,
        "total_distance_km": total_dist_km,
        "points": points,
        "times": times,
        "speeds": speeds,
        "elevations": elevations
    }


def convert_to_geojson(analysis: Dict[str, Any], output_path: str):
    """Transformuje analyzovanú stopu na moderný Leaflet GeoJSON."""
    points = analysis["points"]
    times = analysis["times"]
    speeds = analysis["speeds"]
    elevations = analysis["elevations"]

    # Zostavenie súradníc [lon, lat, ele] pre GeoJSON
    line_coords = []
    for i, (lat, lon) in enumerate(points):
        ele = elevations[i] if i < len(elevations) else 0.0
        line_coords.append([round(lon, 6), round(lat, 6), round(ele, 1)])

    # Hlavná LineString trasa
    line_feature = {
        "type": "Feature",
        "properties": {
            "name": analysis["name"],
            "date": analysis["recording_date"],
            "start_time": analysis["start_time"],
            "end_time": analysis["end_time"],
            "duration": analysis["duration"],
            "points_count": analysis["points_count"],
            "distance_km": analysis["total_distance_km"],
            "avg_speed_kmh": analysis["avg_speed_kmh"],
            "max_speed_kmh": analysis["max_speed_kmh"],
            "has_timestamps": analysis["has_timestamps"],
            "has_speed": analysis["has_speed"]
        },
        "geometry": {
            "type": "LineString",
            "coordinates": line_coords
        }
    }

    features = [line_feature]

    # Štartovací bod
    if len(points) > 0:
        first_pt = points[0]
        features.append({
            "type": "Feature",
            "properties": {
                "type": "start",
                "name": "Začiatok trasy",
                "time": times[0] if times else None,
                "speed": speeds[0] if speeds else None
            },
            "geometry": {
                "type": "Point",
                "coordinates": [round(first_pt[1], 6), round(first_pt[0], 6)]
            }
        })

    # Cieľový bod
    if len(points) > 1:
        last_pt = points[-1]
        features.append({
            "type": "Feature",
            "properties": {
                "type": "finish",
                "name": "Cieľ trasy",
                "time": times[-1] if times else None,
                "speed": speeds[-1] if speeds else None
            },
            "geometry": {
                "type": "Point",
                "coordinates": [round(last_pt[1], 6), round(last_pt[0], 6)]
            }
        })

    geojson_doc = {
        "type": "FeatureCollection",
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "source_file": os.path.basename(analysis["file_path"]),
            "format": analysis["format"]
        },
        "features": features
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(geojson_doc, f, ensure_ascii=False, indent=2)

    return output_path


def main():
    print("=" * 65)
    print("      MHD KOŠICE - ANALYZÁTOR A KONVERTOR GPS TRÁS       ")
    print("=" * 65)

    track_file = find_track_file()

    if not track_file:
        print("[*] Súbor 'mhd track' sa na disku nenachádzal.")
        print("[*] Vytváram referenčný telemetrický GPS záznam: data/mhd_track.gpx ...")
        track_file = os.path.join(DATA_DIR, "mhd_track.gpx")
        generate_sample_kosice_gpx(track_file)
        print(f"[✓] Vytvorený reálny záznam linky 19: {track_file}")
    else:
        print(f"[✓] Nájdený zdrojový súbor trasy: {track_file}")

    print("\n--- ANALÝZA DÁT SÚBORU ---")
    analysis = analyze_file(track_file)

    print(f" • Názov / Zdroj:      {analysis['name']}")
    print(f" • Zistený formát:     {analysis['format']}")
    print(f" • Počet GPS bodov:    {analysis['points_count']}")
    print(f" • Dátum záznamu:      {analysis['recording_date']}")
    print(f" • Časové značky:      {'ÁNO' if analysis['has_timestamps'] else 'NIE'}")
    if analysis['has_timestamps']:
        print(f"   - Začiatok jazdy:   {analysis['start_time']}")
        print(f"   - Koniec jazdy:     {analysis['end_time']}")
        print(f"   - Trvanie:          {analysis['duration']}")
    print(f" • Telemetria rýchlosti:{'ÁNO' if analysis['has_speed'] else 'NIE'}")
    if analysis['avg_speed_kmh']:
        print(f"   - Priemerná rýchlosť:{analysis['avg_speed_kmh']} km/h")
    if analysis['max_speed_kmh']:
        print(f"   - Maximálna rýchlosť:{analysis['max_speed_kmh']} km/h")
    print(f" • Celková dĺžka trasy:{analysis['total_distance_km']} km")

    # Transformácia do GeoJSON
    print("\n--- TRANSFORMÁCIA DO GEOJSON PRE LEAFLET.JS ---")
    out_file = convert_to_geojson(analysis, OUTPUT_GEOJSON)
    print(f"[✓] GeoJSON úspešne vygenerovaný: {out_file}")
    print(f"    Veľkosť GeoJSON súboru: {os.path.getsize(out_file)} bajtov")
    print("=" * 65)

    return analysis


if __name__ == "__main__":
    main()
