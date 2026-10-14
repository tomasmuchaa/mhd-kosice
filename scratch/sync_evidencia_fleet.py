import requests
import sys
import re
import csv
import os

def sync_evidencia(output_csv="data/evidencia_fleet.csv"):
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    })

    all_rows = []
    fieldnames = [
        "trakcia",
        "ECV / SPZ",
        "ev. cislo",
        "vyrobne cislo (VIN)",
        "typ",
        "rok vyroby (dodanie) [zaradenie]",
        "(odstavenie) vyradenie [likvidacia]",
        "url"
    ]

    for trakce in ["autobus", "tramvaj"]:
        page = 1
        while True:
            if page > 1:
                url = f"https://evidencia-dopravcov.eu/zoznam/strana-{page}?iddopravce=184&trakce={trakce}"
            else:
                url = f"https://evidencia-dopravcov.eu/zoznam?iddopravce=184&trakce={trakce}"
            
            print(f"Fetching {trakce} page {page} ({url})...")
            try:
                resp = session.get(url, timeout=12)
            except Exception as e:
                print(f"  Chyba pri stahovani {url}: {e}")
                break

            if resp.status_code != 200:
                print(f"  Status code: {resp.status_code}")
                break

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            table = soup.find("table")
            if not table:
                print("  Nenajdena tabulka na stranke.")
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
                    all_rows.append({
                        "trakcia": trakce,
                        "ECV / SPZ": spz,
                        "ev. cislo": ev,
                        "vyrobne cislo (VIN)": vin,
                        "typ": typ,
                        "rok vyroby (dodanie) [zaradenie]": rok,
                        "(odstavenie) vyradenie [likvidacia]": vyradenie,
                        "url": voz_url
                    })
                    page_rows += 1

            print(f"  Ziskanych {page_rows} zaznamov.")
            if page_rows == 0:
                break
            
            # Check if strana-(page+1) exists in links
            has_next = any(f"strana-{page+1}" in (a.get("href") or "") for a in soup.find_all("a", href=True))
            if not has_next and page_rows < 100:
                break
            page += 1

    print(f"Celkovo ziskanych {len(all_rows)} zaznamov.")

    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    with open(output_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"Ulozene do {output_csv}.")
    return all_rows

if __name__ == "__main__":
    sync_evidencia()
