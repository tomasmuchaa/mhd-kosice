import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STOPS_PATH = os.path.join(PROJECT_DIR, 'data', 'kosice_stops.json')
BACKUP_PATH = os.path.join(PROJECT_DIR, 'data', 'kosice_stops.json.bak')
SCRATCH_DIR = os.path.join(PROJECT_DIR, 'scratch')

TRAM_LINES = {'1', '2', '3', '4', '5', '6', '7', '9', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'R7', 'R8'}

def is_dpmk_line(line) -> bool:
    if line is None:
        return False
    l = str(line).strip().upper()
    if not l:
        return False
    # Exclude trains
    if any(l.startswith(p) for p in ("OS ", "REX ", "EX ", "EN ", "RJ ", "SC ", "R ")):
        return False
    # 1 - 72 (MHD električky a autobusy)
    if l.isdigit():
        val = int(l)
        return 1 <= val <= 72
    # 26P
    if l == "26P":
        return True
    # R1-R8, RA1-RA8, N1-N7, Š1-Š3
    if re.match(r"^(?:R[1-8]|RA[1-8]|N[1-7]|Š[1-3])$", l):
        return True
    return False

def sort_line_key(l):
    if l.isdigit():
        return (0, int(l), '')
    m = re.match(r'^(\d+)([A-Z]+)$', l)
    if m:
        return (0, int(m.group(1)), m.group(2))
    return (1, 0, l)

def main():
    print("Načítavam dáta zastávok DPMK...")
    
    with open(BACKUP_PATH, 'r', encoding='utf-8') as f:
        raw_backup = json.load(f)

    trip_platforms = {}
    trip_platforms_file = os.path.join(SCRATCH_DIR, 'dpmk_trip_platforms.json')
    if os.path.exists(trip_platforms_file):
        with open(trip_platforms_file, 'r', encoding='utf-8') as f:
            trip_platforms = json.load(f)

    scraped_plats = {}
    scraped_plats_file = os.path.join(SCRATCH_DIR, 'ubian_scraped_platforms.json')
    if os.path.exists(scraped_plats_file):
        with open(scraped_plats_file, 'r', encoding='utf-8') as f:
            scraped_plats = json.load(f)

    final_stops = {}

    for s in raw_backup:
        pid = s.get('parent_stop_id')
        if not pid or not str(pid).startswith('100000'):
            continue  # Vylúčenie Eurobus, SAD a ŽSR
        
        sid = str(s.get('stop_id'))
        plat = s.get('platform')
        plat_str = str(plat).strip() if plat is not None and str(plat).strip() != '' else '1'
        base_name = s.get('base_name') or s.get('name')
        if ' (Nást' in base_name:
            base_name = base_name.split(' (Nást')[0].strip()
        
        lat = float(s.get('latitude') or 0)
        lng = float(s.get('longitude') or 0)
        if not (48.55 <= lat <= 48.85 and 21.10 <= lng <= 21.40):
            continue

        parent_lines = [l for l in s.get('lines', []) if is_dpmk_line(l)]
        
        final_stops[sid] = {
            'stop_id': sid,
            'parent_stop_id': int(pid),
            'platform': plat_str,
            'base_name': base_name,
            'name': f"{base_name} (Nást. {plat_str})" if plat_str and plat_str != 'None' else base_name,
            'city': s.get('city', 'Košice'),
            'latitude': round(lat, 6),
            'longitude': round(lng, 6),
            'lines': set(parent_lines),
            'for_urban': True
        }

    # Zlúčenie novoobjavených zastávok z trás spojov (Kavečany, ZOO, Budanova, atď.)
    for sid, tp in trip_platforms.items():
        pid = tp.get('parent_stop_id')
        lat = float(tp.get('latitude') or 0)
        lng = float(tp.get('longitude') or 0)
        plat_str = str(tp.get('platform') or '1').strip()
        base_name = tp.get('base_name')
        if ' (Nást' in base_name:
            base_name = base_name.split(' (Nást')[0].strip()

        tp_lines = [l for l in tp.get('lines', []) if is_dpmk_line(l)]

        if sid in final_stops:
            final_stops[sid]['lines'].update(tp_lines)
            if lat and lng:
                final_stops[sid]['latitude'] = round(lat, 6)
                final_stops[sid]['longitude'] = round(lng, 6)
        else:
            final_stops[sid] = {
                'stop_id': sid,
                'parent_stop_id': int(pid) if pid else sid,
                'platform': plat_str,
                'base_name': base_name,
                'name': f"{base_name} (Nást. {plat_str})" if plat_str and plat_str != 'None' else base_name,
                'city': tp.get('city', 'Košice'),
                'latitude': round(lat, 6),
                'longitude': round(lng, 6),
                'lines': set(tp_lines),
                'for_urban': True
            }

    # Rafinácia liniek podľa odchodov z Ubianu
    for sid, sobj in final_stops.items():
        pid_str = str(sobj['parent_stop_id'])
        plat_str = str(sobj['platform'])
        
        scraped_parent = scraped_plats.get(pid_str, {})
        if plat_str in scraped_parent:
            p_lines = [l for l in scraped_parent[plat_str].get('lines', []) if is_dpmk_line(l)]
            if p_lines:
                sobj['lines'] = set(p_lines)
        elif 'default' in scraped_parent and len(scraped_parent) == 1:
            p_lines = [l for l in scraped_parent['default'].get('lines', []) if is_dpmk_line(l)]
            if p_lines:
                sobj['lines'] = set(p_lines)

    # Výpočet stop_type (tram, bus, mixed)
    clean_list = []
    tram_cnt = bus_cnt = mixed_cnt = 0
    for sid, sobj in final_stops.items():
        clean_lines = sorted(list(sobj['lines']), key=sort_line_key)
        if not clean_lines:
            continue

        name_lower = (sobj.get('base_name') or sobj.get('name') or '').lower()
        if 'autobusová stanica' in name_lower or 'železničná stanica' in name_lower or 'nást. as' in name_lower:
            continue

        has_tram = any(l in TRAM_LINES for l in clean_lines)
        has_bus = any(l not in TRAM_LINES for l in clean_lines)
        
        if has_tram and has_bus:
            st_type = 'mixed'
            mixed_cnt += 1
        elif has_tram:
            st_type = 'tram'
            tram_cnt += 1
        else:
            st_type = 'bus'
            bus_cnt += 1

        clean_item = {
            'stop_id': sobj['stop_id'],
            'parent_stop_id': sobj['parent_stop_id'],
            'platform': sobj['platform'],
            'name': sobj['name'],
            'base_name': sobj['base_name'],
            'city': sobj['city'],
            'latitude': sobj['latitude'],
            'longitude': sobj['longitude'],
            'lines': clean_lines,
            'stop_type': st_type,
            'for_urban': True
        }
        clean_list.append(clean_item)

    clean_list.sort(key=lambda x: (x['base_name'], str(x.get('platform') or '')))

    print(f"Výsledný stav: {len(clean_list)} zastávok ({tram_cnt} električkových, {bus_cnt} autobusových, {mixed_cnt} zmiešaných)")

    with open(STOPS_PATH, 'w', encoding='utf-8') as f:
        json.dump(clean_list, f, ensure_ascii=False, indent=2)

    print(f"Uložené do {STOPS_PATH}!")

if __name__ == '__main__':
    main()
