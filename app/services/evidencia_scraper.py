import os
import re
import json
import requests
from typing import Dict, Any, Optional
from bs4 import BeautifulSoup

class EvidenciaDopravcovScraper:
    """
    Služba pre automatické vyhľadávanie a parsovanie údajov o vozidlách DPMK
    z portálu https://evidencia-dopravcov.eu na základe ŠPZ (EČV).
    Umožňuje podľa ŠPZ získať reálne evidenčné číslo, presný model vozidla,
    rok výroby a VIN číslo.
    Výsledky perzistentne cachuje do data/evidencia_cache.json pre bleskovú odozvu.
    """

    BASE_URL = "https://evidencia-dopravcov.eu"

    def __init__(self, cache_file: Optional[str] = None):
        if cache_file:
            self.cache_file = cache_file
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.cache_file = os.path.join(base_dir, "data", "evidencia_cache.json")

        self.cache: Dict[str, Dict[str, Any]] = self._load_cache()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "sk,cs,en;q=0.9",
            "Referer": f"{self.BASE_URL}/",
            "Origin": self.BASE_URL
        })
        self._initialized = False

    def _load_cache(self) -> Dict[str, Dict[str, Any]]:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except Exception as e:
                print(f"[EvidenciaScraper] Varovanie pri načítaní cache: {e}")
        return {}

    def _save_cache(self):
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[EvidenciaScraper] Varovanie pri ukladaní cache: {e}")

    def _ensure_session(self):
        """Získa vstupné session cookies z domovskej stránky."""
        if not self._initialized:
            try:
                self.session.get(f"{self.BASE_URL}/", timeout=8)
                self._initialized = True
            except Exception as e:
                print(f"[EvidenciaScraper] Chyba inicializácie session: {e}")

    @staticmethod
    def normalize_spz(spz: str) -> str:
        """Normalizuje ŠPZ (odstráni medzery, pomlčky a prevedie na veľké písmená)."""
        if not spz:
            return ""
        return re.sub(r"[^A-Za-z0-9]", "", str(spz)).upper()

    def lookup_by_spz(self, spz: str) -> Optional[Dict[str, Any]]:
        """
        Vyhľadá vozidlo na evidencia-dopravcov.eu podľa ŠPZ.
        Vráti slovník s údajmi (evidencne_cislo, model, rok_vyroby, vin) alebo None.
        """
        clean_spz = self.normalize_spz(spz)
        if not clean_spz or len(clean_spz) < 4:
            return None

        # 1. Kontrola v pamäťovej cache
        if clean_spz in self.cache:
            return self.cache[clean_spz]

        self._ensure_session()

        form_data = {
            "search": clean_spz,
            "_submit": "vyhľadať",
            "_do": "header-combinedSearch-search-submit"
        }

        try:
            resp = self.session.post(f"{self.BASE_URL}/", data=form_data, timeout=8)
            if resp.status_code != 200:
                return None

            target_html = resp.text
            final_url = resp.url

            # A) Priame presmerovanie na podstránku vozidla (/voz/{id})
            if "/voz/" in final_url:
                parsed = self._parse_vehicle_page(target_html, clean_spz, final_url)
                if parsed:
                    self.cache[clean_spz] = parsed
                    self._save_cache()
                    return parsed

            # B) Výsledok vyhľadávania vrátil zoznam (/zoznam)
            elif "/zoznam" in final_url:
                soup = BeautifulSoup(target_html, "html.parser")
                vehicle_links = []
                for tr in soup.find_all("tr"):
                    txt = tr.get_text()
                    if "Košice" in txt or "DPMK" in txt:
                        a_tag = tr.find("a", href=re.compile(r"/voz/\d+"))
                        if a_tag:
                            vehicle_links.append(a_tag["href"])

                if not vehicle_links:
                    # Skúsime všeobecne nájsť prvý /voz/ odkaz
                    for a_tag in soup.find_all("a", href=re.compile(r"/voz/\d+")):
                        vehicle_links.append(a_tag["href"])

                if vehicle_links:
                    first_link = vehicle_links[0]
                    if not first_link.startswith("http"):
                        first_link = f"{self.BASE_URL}{first_link}"
                    detail_resp = self.session.get(first_link, timeout=8)
                    if detail_resp.status_code == 200:
                        parsed = self._parse_vehicle_page(detail_resp.text, clean_spz, first_link)
                        if parsed:
                            self.cache[clean_spz] = parsed
                            self._save_cache()
                            return parsed

        except Exception as e:
            print(f"[EvidenciaScraper] Chyba pri dopyte pre ŠPZ {clean_spz}: {e}")

        return None

    def _parse_vehicle_page(self, html: str, spz: str, url: str) -> Optional[Dict[str, Any]]:
        """Extrahuje údaje o vozidle z HTML stránky detailu vozidla."""
        soup = BeautifulSoup(html, "html.parser")

        # 1. Extrakcia z H1 alebo Title
        # Typický formát: 'Vozidlo DP mesta Košice #4755 (SOR NB 18 City)'
        h1 = soup.find("h1")
        h1_text = h1.get_text(strip=True) if h1 else ""
        if not h1_text:
            title = soup.find("title")
            h1_text = title.get_text(strip=True) if title else ""

        ev_match = re.search(r"#(\d+)", h1_text)
        model_match = re.search(r"\(([^)]+)\)", h1_text)

        ev_num = ev_match.group(1).strip() if ev_match else None
        model = model_match.group(1).strip() if model_match else None

        # 2. Extrakcia parametrov z tabuľky car-details
        details: Dict[str, str] = {}
        table = soup.find("table", class_="car-details")
        if table:
            for tr in table.find_all("tr"):
                th = tr.find("th")
                td = tr.find("td")
                if th and td:
                    key = th.get_text(strip=True).lower()
                    val = td.get_text(" ", strip=True)
                    details[key] = val

        # Interné evidenčné číslo z tabuľky ako fallback
        if not ev_num:
            for k, val in details.items():
                if "eviden" in k:
                    m = re.search(r"\b(\d{3,5})\b", val)
                    if m:
                        ev_num = m.group(1)
                        break

        # Model / typ z tabuľky
        if not model:
            for k in ["typ", "model"]:
                if k in details:
                    model = details[k]
                    break

        # Doplňujúce údaje
        vin = None
        for k, v in details.items():
            if "vin" in k:
                vin = v.split()[0].strip() if v else None
                break

        rok_vyroby = None
        for k, v in details.items():
            if "rok" in k and "výrob" in k:
                m = re.search(r"\b(19\d{2}|20\d{2})\b", v)
                if m:
                    rok_vyroby = m.group(1)
                    break

        if not ev_num and not model:
            return None

        result = {
            "spz": spz,
            "evidencne_cislo": ev_num,
            "model": model or "Autobus DPMK",
            "rok_vyroby": rok_vyroby,
            "vin": vin,
            "url": url,
            "source": "evidencia-dopravcov.eu"
        }
        return result

# Globálny singleton
evidencia_scraper = EvidenciaDopravcovScraper()
