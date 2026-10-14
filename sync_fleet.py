"""
sync_fleet.py - Skript pre kompletnú synchronizáciu vozového parku DPMK
z portálu https://evidencia-dopravcov.eu do lokálnej databázy:
  - data/kompletna_evidencia.json (štruktúrovaný JSON s rýchlym indexom ŠPZ -> Ev. číslo -> Model)
  - data/kompletna_evidencia.csv (prehľadná tabuľka)

Použitie:
  python sync_fleet.py
"""

from __future__ import annotations
import os
import sys
import re
import csv
import json
import time
from typing import Dict, Any, List, Optional
import requests
from bs4 import BeautifulSoup

# Nastavenie UTF-8 výstupu pre Windows konzolu
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_JSON = os.path.join(DATA_DIR, "kompletna_evidencia.json")
OUTPUT_CSV = os.path.join(DATA_DIR, "kompletna_evidencia.csv")

def normalize_spz(spz: Optional[str]) -> str:
    """Normalizuje ŠPZ (odstráni medzery, pomlčky, prevedie na veľké písmená)."""
    if not spz:
        return ""
    return re.sub(r"[^A-Za-z0-9]", "", str(spz)).upper()

def normalize_model(raw_model: Optional[str], trakcia: str = "") -> str:
    """Normalizuje názvy modelov vozidiel DPMK pre čisté zobrazenie v aplikácii."""
    if not raw_model:
        return "Električka DPMK" if trakcia == "tramvaj" else "Autobus DPMK"
    m = str(raw_model).strip()
    if "VarioLF2+" in m or "Vario LF2+" in m:
        return "Vario LF2+"
    if "Vario LFR" in m:
        return "Vario LFR.S"
    if "KT8D5" in m:
        return "Tatra KT8D5.RN2"
    if "T6A5" in m:
        return "Tatra T6A5"
    if "EBN 10,5" in m or "EBN 10.5" in m:
        return "SOR EBN 10.5"
    if "EBN 11" in m:
        return "SOR EBN 11"
    if "NS 18 Electric" in m:
        return "SOR NS 18 Electric"
    if "NSG 18" in m:
        return "SOR NSG 18"
    if "NSG 12" in m:
        return "SOR NSG 12"
    if "NB 18" in m:
        return "SOR NB 18 City"
    if "NB 12" in m:
        return "SOR NB 12 City"
    if "18.75" in m or "18,75" in m:
        return "Solaris Urbino 18,75 III"
    if "Urbino 18" in m and "18," not in m and "18." not in m:
        return "Solaris Urbino 18 III"
    if "Urbino 15" in m:
        return "Solaris Urbino 15"
    # Desatinná čiarka v označeniach SOR (napr. SOR BN 9,5 -> SOR BN 9.5)
    m = m.replace(",5", ".5")
    return m

def parse_year(raw_val: Optional[str]) -> Optional[str]:
    """Extrahuje 4-ciferný rok výroby."""
    if not raw_val:
        return None
    match = re.search(r"\b(19\d\d|20\d\d)\b", str(raw_val))
    return match.group(1) if match else None

def sync_fleet(
    output_json: str = OUTPUT_JSON,
    output_csv: str = OUTPUT_CSV
) -> Dict[str, Any]:
    """
    Stiahne kompletný vozový park DPMK (dopravca 184) z evidencia-dopravcov.eu,
    rozparsuje autobusy aj električky a uloží ich do lokálnej databázy.
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    })

    print("=" * 70)
    print("SYNCHRONIZÁCIA VOZOVÉHO PARKU DPMK (evidencia-dopravcov.eu)")
    print("=" * 70)

    raw_records: List[Dict[str, Any]] = []

    for trakcia in ["autobus", "tramvaj", "elektrobus"]:
        page = 1
        print(f"\n[INFO] Sťahujem kategóriu: {trakcia.upper()}...")
        while True:
            if page > 1:
                url = f"https://evidencia-dopravcov.eu/zoznam/strana-{page}?iddopravce=184&trakce={trakcia}"
            else:
                url = f"https://evidencia-dopravcov.eu/zoznam?iddopravce=184&trakce={trakcia}"

            print(f"  -> Strana {page} ({url})...", end=" ", flush=True)
            try:
                resp = session.get(url, timeout=15)
            except Exception as e:
                print(f"[CHYBA]: {e}")
                break

            if resp.status_code != 200:
                print(f"[HTTP {resp.status_code}] - koniec stránkovania.")
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            table = soup.find("table")
            if not table:
                print("[Tabuľka nenájdená] - koniec stránkovania.")
                break

            trs = table.find_all("tr")
            page_rows = 0
            for tr in trs:
                tds = [td.get_text(strip=True) for td in tr.find_all("td")]
                if len(tds) >= 7:
                    spz = tds[1]
                    ev = tds[2]
                    vin = tds[3]
                    typ = tds[4]
                    rok = tds[5]
                    vyradenie = tds[6]
                    a_tag = tr.find("a", href=re.compile(r"/voz/\d+"))
                    voz_url = f"https://evidencia-dopravcov.eu{a_tag['href']}" if a_tag else ""

                    clean_ev = str(ev).strip().replace(".0", "").replace("#", "")
                    clean_spz = normalize_spz(spz)
                    norm_typ = normalize_model(typ, trakcia=trakcia)
                    year = parse_year(rok)
                    is_active = not bool(vyradenie and str(vyradenie).lower() not in ("", "nan", "none"))

                    raw_records.append({
                        "trakcia": "elektricka" if trakcia == "tramvaj" else ("elektrobus" if trakcia == "elektrobus" else "autobus"),
                        "spz": spz if spz else None,
                        "clean_spz": clean_spz if clean_spz else None,
                        "evidencne_cislo": clean_ev if clean_ev else None,
                        "vyrobne_cislo_vin": vin if vin else None,
                        "model": norm_typ,
                        "rok_vyroby": year,
                        "vyradenie": vyradenie if vyradenie else None,
                        "is_active": is_active,
                        "url": voz_url
                    })
                    page_rows += 1

            print(f"OK ({page_rows} záznamov)")
            if page_rows == 0:
                break

            has_next = any(f"strana-{page+1}" in (a.get("href") or "") for a in soup.find_all("a", href=True))
            if not has_next and page_rows < 100:
                break
            page += 1

    print(f"\n[OK] Celkovo stiahnutých {len(raw_records)} vozidiel z webu.")

    # 1. Zostavenie indexov (aktívne vozidlá a novšie ročníky majú prednosť)
    by_spz: Dict[str, Dict[str, Any]] = {}
    by_ev: Dict[str, Dict[str, Any]] = {}

    for r in raw_records:
        clean_spz = r.get("clean_spz")
        ev = r.get("evidencne_cislo")
        is_active = r.get("is_active", False)

        item = {
            "spz": r.get("spz"),
            "clean_spz": clean_spz,
            "evidencne_cislo": ev,
            "model": r.get("model"),
            "rok_vyroby": r.get("rok_vyroby"),
            "vin": r.get("vyrobne_cislo_vin"),
            "trakcia": r.get("trakcia"),
            "is_active": is_active,
            "url": r.get("url")
        }

        # Indexovanie podľa ŠPZ
        if clean_spz:
            existing = by_spz.get(clean_spz)
            if not existing:
                by_spz[clean_spz] = item
            elif is_active and not existing.get("is_active"):
                by_spz[clean_spz] = item
            elif is_active == existing.get("is_active"):
                ey = int(existing.get("rok_vyroby") or 0)
                ny = int(item.get("rok_vyroby") or 0)
                if ny >= ey:
                    by_spz[clean_spz] = item

        # Indexovanie podľa evidenčného čísla
        if ev:
            existing = by_ev.get(ev)
            if not existing:
                by_ev[ev] = item
            elif is_active and not existing.get("is_active"):
                by_ev[ev] = item
            elif is_active == existing.get("is_active"):
                ey = int(existing.get("rok_vyroby") or 0)
                ny = int(item.get("rok_vyroby") or 0)
                if ny >= ey:
                    by_ev[ev] = item

    # 2. Doplnenie a garancia najnovších moderných vozidiel DPMK
    modern_additions = [
        # SOR NS 18 Electric (4901 - 4911)
        ("4901", "EL-748CC", "SOR NS 18 Electric", "2026", "elektrobus"),
        ("4902", "EL-734CC", "SOR NS 18 Electric", "2026", "elektrobus"),
        ("4903", "EL-739CC", "SOR NS 18 Electric", "2026", "elektrobus"),
        ("4904", "EL-729CC", "SOR NS 18 Electric", "2026", "elektrobus"),
        ("4905", "EL-737CC", "SOR NS 18 Electric", "2026", "elektrobus"),
        ("4906", "EL-715CC", "SOR NS 18 Electric", "2026", "elektrobus"),
        ("4907", "EL-713CC", "SOR NS 18 Electric", "2026", "elektrobus"),
        ("4908", "EL-513CB", "SOR NS 18 Electric", "2026", "elektrobus"),
        ("4909", "EL-746CC", "SOR NS 18 Electric", "2026", "elektrobus"),
        ("4910", "EL-736CC", "SOR NS 18 Electric", "2026", "elektrobus"),
        ("4911", "EL-735CC", "SOR NS 18 Electric", "2026", "elektrobus"),
        # SOR NSG 18 (4801) & SOR NSG 12 (5802, 5803)
        ("4801", "AA-403EV", "SOR NSG 18", "2024", "autobus"),
        ("5802", "AA-355EV", "SOR NSG 12", "2024", "autobus"),
        ("5803", "AA-362EV", "SOR NSG 12", "2024", "autobus"),
        # SOR EBN 10.5 (6801 - 6805)
        ("6801", "KE-260JI", "SOR EBN 10.5", "2014", "elektrobus"),
        ("6802", "KE-485JH", "SOR EBN 10.5", "2014", "elektrobus"),
        ("6803", "KE-991JH", "SOR EBN 10.5", "2014", "elektrobus"),
        ("6804", "KE-268JI", "SOR EBN 10.5", "2014", "elektrobus"),
        ("6805", "KE-270JI", "SOR EBN 10.5", "2014", "elektrobus"),
        # SOR EBN 11 (6901 - 6918)
        ("6901", "KE-975OT", "SOR EBN 11", "2016", "elektrobus"),
        ("6902", "KE-732KF", "SOR EBN 11", "2016", "elektrobus"),
        ("6903", "KE-001KG", "SOR EBN 11", "2016", "elektrobus"),
        ("6904", "KE-721KF", "SOR EBN 11", "2016", "elektrobus"),
        ("6905", "KE-360KH", "SOR EBN 11", "2016", "elektrobus"),
        ("6906", "KE-395KH", "SOR EBN 11", "2016", "elektrobus"),
        ("6907", "KE-454KI", "SOR EBN 11", "2016", "elektrobus"),
        ("6908", "KE-180KI", "SOR EBN 11", "2016", "elektrobus"),
        ("6909", "KE-442KI", "SOR EBN 11", "2016", "elektrobus"),
        ("6910", "KE-310LH", "SOR EBN 11", "2016", "elektrobus"),
        ("6911", "KE-340LH", "SOR EBN 11", "2016", "elektrobus"),
        ("6912", "KE-256LH", "SOR EBN 11", "2016", "elektrobus"),
        ("6913", "KE-952LG", "SOR EBN 11", "2016", "elektrobus"),
        ("6914", "KE-909LG", "SOR EBN 11", "2016", "elektrobus"),
        ("6915", "KE-885LG", "SOR EBN 11", "2016", "elektrobus"),
        ("6916", "KE-122LH", "SOR EBN 11", "2016", "elektrobus"),
        ("6917", "KE-262LH", "SOR EBN 11", "2016", "elektrobus"),
        ("6918", "KE-030LH", "SOR EBN 11", "2016", "elektrobus"),
        # Solaris Urbino 18,75 III (3906 - 3920)
        ("3906", "AA-086UO", "Solaris Urbino 18,75 III", "2014", "autobus"),
        ("3907", "AA-135UO", "Solaris Urbino 18,75 III", "2014", "autobus"),
        ("3908", "AA-156TY", "Solaris Urbino 18,75 III", "2014", "autobus"),
        ("3909", "AA-136UO", "Solaris Urbino 18,75 III", "2014", "autobus"),
        ("3910", "AA-278TY", "Solaris Urbino 18,75 III", "2014", "autobus"),
        ("3911", "AA-104TY", "Solaris Urbino 18,75 III", "2014", "autobus"),
        ("3912", "AA-963SL", "Solaris Urbino 18,75 III", "2014", "autobus"),
        ("3913", "AA-930SL", "Solaris Urbino 18,75 III", "2014", "autobus"),
        ("3914", "AA-727UU", "Solaris Urbino 18,75 III", "2014", "autobus"),
        ("3915", "AA-223TY", "Solaris Urbino 18,75 III", "2014", "autobus"),
        ("3916", "AA-728UU", "Solaris Urbino 18,75 III", "2014", "autobus"),
        ("3917", "AA-161UO", "Solaris Urbino 18,75 III", "2014", "autobus"),
        ("3918", "AA-205UO", "Solaris Urbino 18,75 III", "2014", "autobus"),
        ("3919", "AA-265TY", "Solaris Urbino 18,75 III", "2014", "autobus"),
        ("3920", "AA-267TY", "Solaris Urbino 18,75 III", "2014", "autobus"),
        # Solaris Urbino 18 III (3901 - 3905)
        ("3901", "KE-069EU", "Solaris Urbino 18 III", "2010", "autobus"),
        ("3902", "KE-074EU", "Solaris Urbino 18 III", "2010", "autobus"),
        ("3903", "KE-084EU", "Solaris Urbino 18 III", "2010", "autobus"),
        ("3904", "KE-086EU", "Solaris Urbino 18 III", "2010", "autobus"),
        ("3905", "KE-088EU", "Solaris Urbino 18 III", "2010", "autobus"),
    ]
    for ev, spz, model, rok, trak in modern_additions:
        clean_spz = normalize_spz(spz)
        item = {
            "spz": spz,
            "clean_spz": clean_spz,
            "evidencne_cislo": ev,
            "model": model,
            "rok_vyroby": rok,
            "vin": None,
            "trakcia": trak,
            "is_active": True,
            "url": None
        }
        by_spz[clean_spz] = item
        by_ev[ev] = item

    # Zostavenie výsledného JSON balíka
    dataset = {
        "metadata": {
            "synced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source": "https://evidencia-dopravcov.eu/zoznam?iddopravce=184",
            "total_records": len(raw_records),
            "indexed_spz": len(by_spz),
            "indexed_ev": len(by_ev),
            "active_vehicles": sum(1 for r in raw_records if r.get("is_active")),
        },
        "by_spz": by_spz,
        "by_ev": by_ev,
        "vehicles": raw_records
    }

    # Zápis do JSON
    os.makedirs(os.path.dirname(output_json), exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)
    print(f"\n[OK] Lokálna databáza uložená do: {output_json}")

    # Zápis do CSV
    fieldnames = [
        "trakcia",
        "spz",
        "clean_spz",
        "evidencne_cislo",
        "vyrobne_cislo_vin",
        "model",
        "rok_vyroby",
        "vyradenie",
        "is_active",
        "url"
    ]
    with open(output_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(raw_records)
    print(f"[OK] Tabuľkový CSV export uložený do: {output_csv}")

    print("\n" + "=" * 70)
    print("VÝSLEDOK SYNCHRONIZÁCIE:")
    print("=" * 70)
    print(f"Celkový počet stiahnutých vozidiel: {len(raw_records)}")
    print(f"Počet aktívnych vozidiel:            {dataset['metadata']['active_vehicles']}")
    print(f"Počet unikátnych ŠPZ v indexe:       {len(by_spz)}")
    print(f"Počet unikátnych ev. čísel v indexe: {len(by_ev)}")
    print("=" * 70)

    return dataset

if __name__ == "__main__":
    sync_fleet()
