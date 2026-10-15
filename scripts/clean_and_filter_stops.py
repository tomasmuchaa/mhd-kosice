import json, sys, math, os, re

sys.stdout.reconfigure(encoding='utf-8')

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STOPS_PATH = os.path.join(PROJECT_DIR, 'data', 'kosice_stops.json')
BACKUP_PATH = os.path.join(PROJECT_DIR, 'data', 'kosice_stops.json.bak')

def is_dpmk_line(line) -> bool:
    if line is None:
        return False
    l = str(line).strip().upper()
    if not l:
        return False
    # Exclude trains
    if any(l.startswith(p) for p in ("OS ", "REX ", "EX ", "EN ", "RJ ", "SC ", "R ")):
        return False
    # 1 - 99
    if l.isdigit():
        val = int(l)
        return 1 <= val <= 99
    # 20L, 26P etc
    m = re.match(r"^(\d{1,2})([A-Z])$", l)
    if m:
        val = int(m.group(1))
        return 1 <= val <= 99
    # R1-R8, RA1-RA8, N1-N7, Š1-Š3, S1-S3, X1-X9, H, A, V1-V4
    if re.match(r"^(?:R[1-8]|RA[1-8]|N[1-7]|[ŠS][1-3]|X\d?|[HA]\d?|V[1-4])$", l):
        return True
    return False

def haversine(p1, p2):
    R = 6371000
    lat1, lon1 = math.radians(p1[0]), math.radians(p1[1])
    lat2, lon2 = math.radians(p2[0]), math.radians(p2[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def sort_line_key(l):
    if l.isdigit():
        return (0, int(l), '')
    m = re.match(r'^(\d+)([A-Z]+)$', l)
    if m:
        return (0, int(m.group(1)), m.group(2))
    return (1, 0, l)

# Load stops
with open(STOPS_PATH, 'r', encoding='utf-8') as f:
    raw_stops = json.load(f)

print(f"Pôvodný počet zastávok: {len(raw_stops)}")

# 1. Filtrovanie DPMK a GPS ohraničenia Košíc
dpmk_stops = []
for s in raw_stops:
    lat = float(s.get('latitude') or 0)
    lng = float(s.get('longitude') or 0)
    # Bounding box širších Košíc
    if not (48.55 <= lat <= 48.85 and 21.10 <= lng <= 21.40):
        continue

    raw_lines = s.get('lines', [])
    mhd_lines = [l for l in raw_lines if is_dpmk_line(l)]
    if not mhd_lines:
        continue # Ignorujeme manipulačné body a Eurobusy

    s_clean = dict(s)
    s_clean['latitude'] = lat
    s_clean['longitude'] = lng
    s_clean['lines'] = sorted(list(set(mhd_lines)), key=sort_line_key)
    dpmk_stops.append(s_clean)

print(f"Po očistení od Eurobusov, SAD a prázdnych bodov: {len(dpmk_stops)} zastávok")

# 2. Zhlukovanie platforiem patriacich pod rovnaký parent_stop_id do vzdialenosti 45 m
by_parent = {}
for s in dpmk_stops:
    pid = s.get('parent_stop_id') or s['stop_id']
    by_parent.setdefault(pid, []).append(s)

clustered_stops = []

for pid, plist in by_parent.items():
    clusters = []
    for p in plist:
        coord_p = [p['latitude'], p['longitude']]
        assigned = False
        for c in clusters:
            coord_c = [c['latitude'], c['longitude']]
            if haversine(coord_p, coord_c) <= 45.0:
                c['items'].append(p)
                c['latitude'] = sum(x['latitude'] for x in c['items']) / len(c['items'])
                c['longitude'] = sum(x['longitude'] for x in c['items']) / len(c['items'])
                assigned = True
                break
        if not assigned:
            clusters.append({
                'latitude': coord_p[0],
                'longitude': coord_p[1],
                'items': [p]
            })

    for c in clusters:
        items = c['items']
        primary = items[0]
        all_lines = set()
        for it in items:
            all_lines.update(it.get('lines', []))

        platforms = [str(it.get('platform')) for it in items if it.get('platform') is not None and str(it.get('platform')).strip() != '']
        plat_str = ", ".join(sorted(set(platforms), key=lambda x: (x.isdigit() and int(x) or 999, x))) if platforms else None

        base_name = primary.get('base_name') or primary.get('name')
        if ' (' in base_name and 'Nást' in base_name:
            base_name = base_name.split(' (')[0].strip()

        display_name = f"{base_name} (Nást. {plat_str})" if plat_str else base_name

        clustered_stops.append({
            'stop_id': primary['stop_id'],
            'parent_stop_id': pid,
            'platform': plat_str,
            'platforms_included': [it['stop_id'] for it in items],
            'name': display_name,
            'base_name': base_name,
            'city': primary.get('city', 'Košice'),
            'latitude': round(c['latitude'], 6),
            'longitude': round(c['longitude'], 6),
            'lines': sorted(list(all_lines), key=sort_line_key),
            'for_urban': True
        })

# Zoradenie podľa názvu
clustered_stops.sort(key=lambda x: x.get('name', ''))

print(f"Výsledný počet fyzických zastávok po zlúčení duplicít: {len(clustered_stops)}")

# Záloha pôvodného súboru ak ešte neexistuje
if not os.path.exists(BACKUP_PATH):
    import shutil
    shutil.copy2(STOPS_PATH, BACKUP_PATH)
    print(f"Pôvodný súbor zálohovaný do {BACKUP_PATH}")

# Uloženie očisteného súboru
with open(STOPS_PATH, 'w', encoding='utf-8') as f:
    json.dump(clustered_stops, f, ensure_ascii=False, indent=2)

print(f"Očistený dataset úspešne uložený do {STOPS_PATH}!")

# Kontrola Moskovskej
mosk = [s for s in clustered_stops if 'Moskovsk' in s['name']]
print(f"\nStav Moskovská ({len(mosk)} zastávky):")
for m in mosk:
    print(f"  {m['stop_id']}: {m['name']} | Nástupištia: {m['platform']} | Linky: {m['lines']} | GPS: {m['latitude']}, {m['longitude']}")
