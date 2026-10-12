# 🚌 MHD Košice – Inteligentný systém pre sledovanie a plánovanie dopravy

Komplexný webový a backendový systém pre reálny čas, plánovanie ciest a crowdsourcing mestskej hromadnej dopravy (DPMK) v Košiciach.

---

## ✨ Kľúčové funkcie

- **🗺️ Živá interaktívna mapa (`mapa.html`):**
  - Reálne GPS polohy vozidiel DPMK s plynulou animáciou pohybu.
  - Špecifické 2D vektorové SVG ikony pre jednotlivé modely vozového parku (SOR NB 12/18, SOR NS 12/18, plynový SOR NSG 18, električky Tatra KT8D5, T6A5, Vario LF, Solaris, Karosa atď.).
  - Farebné kódovanie meškaní a stavov (státie na zastávke, nočná pauza).

- **🛣️ Multimodálny plánovač trás (Ubian-style):**
  - Pokročilý Dijkstrov algoritmus s prepojením na pešiu sieť prestupov (`walking_transfers.json`).
  - Penalizácia za prestupy a dlhé pešie presuny (prioritizácia priamych spojov).
  - Moderné vizuálne karty trás s vertikálnou časovou osou, meškaniami v reálnom čase a interaktívnym vykreslením trasy na mape.

- **👥 Crowdsourcing obsadenosti („Waze pre MHD“):**
  - Rýchle nahlásenie obsadenosti priamo v bubline vozidla (🟢 Prázdny, 🟡 Poloplný, 🔴 Plný).
  - **Inteligentná expirácia:** Automatické vypršanie údajov po 5 minútach alebo po dorazení vozidla na novú zastávku.

- **🤖 AI Data Collector (`data_collector.py`):**
  - Kontinuálny zber telemetrie (pozície, meškania, obsadenosť) do SQLite databázy s WAL žurnálom pre trénovanie predikčných AI modelov.

- **📊 Virtuálne digitálne odchodové tabule & História vozidiel:**
  - Odchody zo zastávok obohatené o dáta vozového parku (ŠPZ, klimatizácia, nízkopodlažnosť).
  - Prepojenie s profilmi vozidiel na imhd.sk.

---

## 🛠️ Technológie

- **Backend:** Python 3.10+, [FastAPI](https://fastapi.tiangolo.com/), Uvicorn, SQLite3, Pydantic
- **Frontend:** Vanilla JavaScript (ES6+), [Leaflet.js](https://leafletjs.com/), SVG grafika, PWA (Service Worker + Manifest)
- **Dáta:** Ubian / DPMK Live Feed, OpenStreetMap, imhd.sk

---

## 🚀 Spustenie projektu lokálne

### 1. Inštalácia závislostí
```bash
pip install -r requirements.txt
```

### 2. Spustenie FastAPI servera
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Po spustení je aplikácia dostupná na:
- **Webová mapa:** [http://localhost:8000/mapa](http://localhost:8000/mapa)
- **API Dokumentácia (Swagger):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Katalóg SVG modelov:** [http://localhost:8000/ikonky](http://localhost:8000/ikonky)

### 3. Spustenie AI Data Collectora (voliteľné)
```bash
python data_collector.py
```

---

## 📂 Štruktúra projektu

```
mhd_kosice/
├── app/
│   ├── main.py                     # FastAPI aplikácia a REST endpointy
│   └── services/
│       ├── fleet_service.py        # Párovanie vozového parku DPMK a manuálne overrides
│       ├── live_feed_service.py    # Spracovanie Ubian / DPMK živého telemetrického feedu
│       ├── routing_engine.py       # Dijkstrov plánovač trás s pešou sieťou
│       ├── occupancy_service.py    # Crowdsourcing správa obsadenosti a expirácia
│       └── imhd_scraper.py         # Získavanie histórie vozidiel z imhd.sk
├── data/
│   ├── dpmk_autobusy_komplet.csv   # Databáza vozidiel DPMK
│   ├── kosice_stops.json           # Databáza zastávok MHD Košice
│   ├── walking_transfers.json      # Graf peších prestupov medzi zastávkami
│   └── mhd_historia.db             # SQLite historická databáza telemetrie
├── mapa.html                       # Hlavná interaktívna aplikácia (Leaflet)
├── ikonky.html                     # Prehliadač a katalóg SVG modelov vozidiel
├── data_collector.py               # Zberateľ historických dát pre AI
├── requirements.txt                # Python závislosti
└── README.md
```
