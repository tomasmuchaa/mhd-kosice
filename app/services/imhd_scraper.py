import re
import requests
from typing import Dict, Any, Optional, List
from bs4 import BeautifulSoup

# In-memory vyrovnávacia pamäť pre zrýchlenie opakovaných požiadaviek (1ms namiesto opakovaného scrapovania)
_HISTORY_CACHE: Dict[str, Dict[str, Any]] = {}

def get_imhd_vehicle_history(evidencne_cislo: str) -> Dict[str, Any]:
    """
    Vyhľadá a načíta profil daného košického vozidla z portálu imhd.sk.
    Vyextrahuje rok výroby, zaradenie do premávky, technické špecifikácie
    a časovú os (timeline) životopisu vozidla (zmeny depa, reklamy, nehody, úpravy).
    """
    clean_ev = str(evidencne_cislo).strip()
    if not clean_ev:
        return {
            "status": "error",
            "message": "Nezadané evidenčné číslo vozidla.",
            "evidencne_cislo": clean_ev
        }

    # Kontrola vyrovnávacej pamäte
    if clean_ev in _HISTORY_CACHE:
        return _HISTORY_CACHE[clean_ev]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "sk,cs,en;q=0.9"
    }

    try:
        # 1. Krok: Vyhľadanie vozidla cez interný vyhľadávač imhd.sk
        search_url = f"https://imhd.sk/ke/vyhladavanie?q={clean_ev}"
        search_resp = requests.get(search_url, headers=headers, timeout=6)
        if search_resp.status_code != 200:
            return {
                "status": "not_found",
                "message": f"imhd.sk vyhľadávanie vrátilo chybový stav HTTP {search_resp.status_code}.",
                "evidencne_cislo": clean_ev
            }

        soup = BeautifulSoup(search_resp.text, "html.parser")
        vehicle_links: List[tuple] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            txt = a.get_text(strip=True)
            if "/vozidlo/" in href:
                vehicle_links.append((href, txt))

        if not vehicle_links:
            # Ak sa nenašiel žiadny odkaz na profil
            return {
                "status": "not_found",
                "message": f"Pre evidenčné číslo #{clean_ev} sa na imhd.sk nenašiel profil.",
                "evidencne_cislo": clean_ev
            }

        # Nájdenie najpresnejšieho odkazu (zodpovedá číslu vozidla)
        target_link = None
        for href, txt in vehicle_links:
            if f"#{clean_ev}" in txt or f"-{clean_ev}" in href or href.endswith(f"-{clean_ev}"):
                target_link = href
                break
        if not target_link:
            target_link = vehicle_links[0][0]

        profile_url = f"https://imhd.sk{target_link}"

        # 2. Krok: Stiahnutie a parsovanie profilu vozidla
        prof_resp = requests.get(profile_url, headers=headers, timeout=6)
        if prof_resp.status_code != 200:
            return {
                "status": "not_found",
                "message": f"Profil vozidla na imhd.sk nebolo možné načítať (HTTP {prof_resp.status_code}).",
                "evidencne_cislo": clean_ev
            }

        prof_soup = BeautifulSoup(prof_resp.text, "html.parser")
        table = prof_soup.find("table")
        if not table:
            return {
                "status": "not_found",
                "message": f"V profile vozidla #{clean_ev} chýba tabuľka technických parametrov.",
                "evidencne_cislo": clean_ev
            }

        specs: Dict[str, str] = {}
        for row in table.find_all("tr"):
            cells = [c.get_text(strip=True) for c in row.find_all(["th", "td"])]
            if len(cells) >= 2:
                key = cells[0].rstrip(":").strip()
                val = cells[1].strip()
                if key and val:
                    specs[key] = val

        # 3. Krok: Extrakcia kľúčových parametrov
        rok_vyroby = specs.get("Rok výroby")
        zaradenie = specs.get("Sprevádzkovanie") or specs.get("Zaradenie do premávky")
        odstavenie = specs.get("Odstavenie z premávky")
        vyradenie = specs.get("Vyradenie")
        model = specs.get("Typ")
        vyrobca = specs.get("Výrobca")
        vin = specs.get("VIN")
        spz = specs.get("Štátne evidenčné číslo vozidla (EČV/ŠPZ)")
        depo = specs.get("Depo")
        reklamy = specs.get("Reklamy")
        nehody = specs.get("Nehody")
        upravy = specs.get("Rekonštrukcie a úpravy") or specs.get("Opravy")
        ine_udaje = specs.get("Iné údaje")

        # Kontrola MANUAL_OVERRIDES (najvyššia autorita pravdy pri hardvérových anomáliách)
        try:
            from app.services.fleet_service import FleetService
            override = FleetService.MANUAL_OVERRIDES.get(clean_ev)
            if override:
                if "model" in override:
                    model = override["model"]
                if "spz" in override:
                    spz = override["spz"]
        except Exception:
            pass

        # 4. Krok: Zostavenie časovej osi (Timeline)
        timeline: List[Dict[str, Any]] = []

        # a) Výroba
        if rok_vyroby:
            timeline.append({
                "date": str(rok_vyroby),
                "type": "manufacture",
                "icon": "🏭",
                "title": "Výroba vozidla",
                "description": f"Vyrobené v závode {vyrobca or 'výrobcu'} v roku {rok_vyroby}."
            })

        # b) Dodanie do Košíc
        if ine_udaje and ("prišiel" in ine_udaje.lower() or "dodan" in ine_udaje.lower()):
            timeline.append({
                "date": "Dodanie",
                "type": "delivery",
                "icon": "🚚",
                "title": "Dodanie do Košíc",
                "description": ine_udaje
            })

        # c) Zaradenie do premávky
        if zaradenie:
            timeline.append({
                "date": zaradenie,
                "type": "commissioning",
                "icon": "🚀",
                "title": "Zaradenie do premávky",
                "description": f"Vozidlo zaradené do pravidelnej prevádzky MHD v Košiciach ({zaradenie})."
            })

        # d) Depá (rozpad na záznamy podľa zátvoriek, ak existujú)
        if depo:
            depot_matches = re.findall(r"([^\(\)]+?)\s*\(([^\)]+)\)", depo)
            if depot_matches:
                for d_name, d_period in depot_matches:
                    timeline.append({
                        "date": d_period.strip(),
                        "type": "depot",
                        "icon": "🏢",
                        "title": f"Depo {d_name.strip()}",
                        "description": f"Dislokácia vozidla: {d_name.strip()} ({d_period.strip()})"
                    })
            else:
                timeline.append({
                    "date": "Dislokácia",
                    "type": "depot",
                    "icon": "🏢",
                    "title": "Dislokácia v depách",
                    "description": depo
                })

        # e) Reklamy a celovozové polepy
        if reklamy:
            ad_matches = re.findall(r"([^\(\)]+?)\s*\(([^\)]+)\)", reklamy)
            if ad_matches:
                for ad_name, ad_period in ad_matches:
                    timeline.append({
                        "date": ad_period.strip(),
                        "type": "ad",
                        "icon": "🎨",
                        "title": "Reklamný polep",
                        "description": f"{ad_name.strip()} ({ad_period.strip()})"
                    })
            else:
                timeline.append({
                    "date": "Reklamy",
                    "type": "ad",
                    "icon": "🎨",
                    "title": "História reklám a polepov",
                    "description": reklamy
                })

        # f) Dopravné nehody
        if nehody:
            # Skúsime nájsť dátum v zátvorke na konci textu (napr. (22.12.2009))
            date_match = re.search(r"\(([0-9]{1,2}\.[0-9]{1,2}\.[0-9]{4})\)", nehody)
            n_date = date_match.group(1) if date_match else "Nehoda"
            timeline.append({
                "date": n_date,
                "type": "accident",
                "icon": "⚠️",
                "title": "Záznam o nehode",
                "description": nehody
            })

        # g) Rekonštrukcie a opravy
        if upravy:
            timeline.append({
                "date": "Rekonštrukcia",
                "type": "repair",
                "icon": "🔧",
                "title": "Rekonštrukcie a úpravy",
                "description": upravy
            })

        # h) Odstavenie z premávky
        if odstavenie:
            desc = f"Vozidlo odstavené z bežnej premávky k dátumu {odstavenie}."
            if vyradenie:
                desc += f" Úradné vyradenie: {vyradenie}."
            timeline.append({
                "date": odstavenie,
                "type": "retirement",
                "icon": "🛑",
                "title": "Odstavenie z premávky",
                "description": desc
            })

        result = {
            "status": "ok",
            "evidencne_cislo": clean_ev,
            "url": profile_url,
            "model": model,
            "rok_vyroby": rok_vyroby,
            "zaradenie_do_premavky": zaradenie,
            "odstavenie_z_premavky": odstavenie,
            "vyradenie": vyradenie,
            "spz": spz,
            "vin": vin,
            "vyrobca": vyrobca,
            "specs": specs,
            "timeline": timeline
        }

        # Uloženie do vyrovnávacej pamäte
        _HISTORY_CACHE[clean_ev] = result
        return result

    except Exception as e:
        return {
            "status": "error",
            "message": f"Chyba pri získavaní histórie z imhd.sk: {str(e)}",
            "evidencne_cislo": clean_ev
        }
