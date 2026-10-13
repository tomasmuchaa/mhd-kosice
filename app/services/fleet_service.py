from __future__ import annotations
import os
import json
import csv
from typing import Optional, Dict, Any, List, Union

class FleetService:
    # Manuálny filter anomálií (najvyššia autorita pravdy):
    # Preložené palubné jednotky z vyradených vozidiel vysielajúce starú identitu v Ubiane
    MANUAL_OVERRIDES: Dict[str, Dict[str, Any]] = {}

    # Známe mapovanie TransData interných vehicleID na evidenčné čísla DPMK
    # (Tieto ID TransData prideľuje palubným jednotkám vozidiel)
    TRANSDATA_MAPPING = {
        "1276320": "5720",  # SOR NB 12 City (KE-704IY)
        "1276507": "5707",  # SOR NB 18 City (KE-716IY)
        "1276522": "5722",  # SOR NB 18 City (KE-071JD)
        "1276562": "4762",  # SOR NB 18 City
        "1276317": "5717",  # SOR NB 12 City (KE-955KK)
        "1276436": "4736",  # SOR NB 18 City
        "1277917": "3917",  # Solaris Urbino 18 III
        "1276394": "4743",  # SOR NB 18 City (KE-095JE - v.č. 394)
        "1276395": "4732",  # SOR NB 18 City (KE-008JE - v.č. 395)
        "1276396": "4721",  # SOR NB 18 City (AA-741PJ - v.č. 396)
        "1276500": "5701",  # SOR NB 12 City (KE-055IY)
        "1276596": "5901",  # Iveco Rošero First FCLLI (KE-219HG)
        "1403196": "4801",  # SOR NSG 18 (AA-403EV)
        "1402220": "3920",  # Solaris Urbino 18,75 III (AA-267TY)
    }

    def __init__(self, csv_path: str, overrides_path: Optional[str] = None):
        self.csv_path = csv_path
        self.overrides_path = overrides_path or os.path.join(os.path.dirname(self.csv_path), "overrides.json")
        self.MANUAL_OVERRIDES = self._load_overrides()
        self.spz_index = {}
        self.ev_index = {}
        self.vin_prod_index = {
            "394": "4743",  # SOR NB 18 City (KE-095JE)
            "395": "4732",  # SOR NB 18 City (KE-008JE)
            "396": "4721",  # SOR NB 18 City (AA-741PJ)
        }
        self._load_data()

    def _load_overrides(self) -> Dict[str, Dict[str, Any]]:
        """Dynamicky načíta manuálne pravidlá zo súboru data/overrides.json."""
        if os.path.exists(self.overrides_path):
            try:
                with open(self.overrides_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except Exception as e:
                print(f"Chyba pri načítaní overrides zo súboru {self.overrides_path}: {e}")
        return {
            "6703": {
                "model": "SOR NB 18 City",
                "evidencne_cislo": "6703",
                "spz": "KE-090IY",
            },
            "1276703": {
                "model": "SOR NB 18 City",
                "evidencne_cislo": "6703",
                "spz": "KE-090IY",
            }
        }

    def save_overrides(self) -> bool:
        """Uloží aktuálne MANUAL_OVERRIDES do súboru data/overrides.json."""
        try:
            os.makedirs(os.path.dirname(self.overrides_path), exist_ok=True)
            with open(self.overrides_path, "w", encoding="utf-8") as f:
                json.dump(self.MANUAL_OVERRIDES, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Chyba pri ukladaní overrides do {self.overrides_path}: {e}")
            return False

    def add_override(
        self,
        model: str,
        evidencne_cislo: Optional[str] = None,
        vehicle_id: Optional[str] = None,
        spz: Optional[str] = None,
        original_evidencne_cislo: Optional[str] = None,
        verified: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        Dynamicky pridá alebo aktualizuje override pre model, evidenčné číslo vozidla a ŠPZ,
        uloží do data/overrides.json a okamžite aktualizuje indexy v pamäti.
        Dôsledne izoluje vozidlá podľa ich unikátneho hardvérového vehicle_id,
        čím zabraňuje duplicite a nechcenému prepisovaniu iných vozidiel.
        Podporuje príznak 'verified' (overené vozidlo v Developer Mode).
        """
        vid = str(vehicle_id).strip() if vehicle_id else None
        ev = str(evidencne_cislo).strip() if evidencne_cislo else None
        clean_spz = spz.strip().upper() if spz and str(spz).strip() else None

        final_ev = ev or (str(original_evidencne_cislo).strip() if original_evidencne_cislo else (vid if vid else ""))

        # Zistenie predchádzajúceho stavu overenia
        prev_verified = False
        if vid and vid in self.MANUAL_OVERRIDES:
            prev_verified = self.MANUAL_OVERRIDES[vid].get("verified", False)
        elif final_ev and final_ev in self.MANUAL_OVERRIDES:
            prev_verified = self.MANUAL_OVERRIDES[final_ev].get("verified", False)

        final_verified = bool(verified) if verified is not None else prev_verified

        # Ak používateľ nezadal novú ŠPZ, zachováme existujúcu ŠPZ z predchádzajúceho záznamu alebo CSV
        if not clean_spz:
            if vid and vid in self.MANUAL_OVERRIDES and self.MANUAL_OVERRIDES[vid].get("spz"):
                clean_spz = self.MANUAL_OVERRIDES[vid]["spz"]
            elif final_ev and final_ev in self.ev_index and self.ev_index[final_ev].get("spz"):
                clean_spz = self.ev_index[final_ev]["spz"]

        entry = {
            "model": model.strip(),
            "evidencne_cislo": final_ev,
            "spz": clean_spz,
            "verified": final_verified
        }

        # 1. Ak ide o reálne vozidlo z live telemetrie s vlastným vehicle_id:
        if vid:
            # Override sa viaže VÝLUČNE na konkrétne hardware vehicle_id tohto terminálu!
            self.MANUAL_OVERRIDES[vid] = entry
            if final_ev:
                self.TRANSDATA_MAPPING[vid] = final_ev

            # Bezpečnostné čistenie: ak v minulosti existoval chybný záznam pod pôvodným ev číslom,
            # ktorý ukazoval na iné vozidlo (cross-kontaminácia), odstránime ho.
            if original_evidencne_cislo:
                old_ev = str(original_evidencne_cislo).strip()
                if old_ev in self.MANUAL_OVERRIDES and self.MANUAL_OVERRIDES[old_ev].get("evidencne_cislo") != old_ev:
                    del self.MANUAL_OVERRIDES[old_ev]

        # 2. Ak ide o statické vozidlo bez vehicle_id (napr. úprava vozidla priamo v depe/garáži):
        elif final_ev:
            self.MANUAL_OVERRIDES[final_ev] = entry
            if final_ev in self.ev_index:
                self.ev_index[final_ev]["model"] = entry["model"]
                if clean_spz:
                    self.ev_index[final_ev]["spz"] = clean_spz

        # Aktualizácia indexu pre vyhľadávanie podľa ŠPZ
        if clean_spz:
            clean_search_spz = clean_spz.replace("-", "").replace(" ", "").upper()
            if clean_search_spz in self.spz_index:
                self.spz_index[clean_search_spz]["model"] = entry["model"]
                if final_ev:
                    self.spz_index[clean_search_spz]["evidencne_cislo"] = final_ev
            elif final_ev and final_ev in self.ev_index:
                self.spz_index[clean_search_spz] = self.ev_index[final_ev]

        self.save_overrides()
        return entry

    def set_verified(
        self,
        vehicle_id: Optional[str] = None,
        ev_cislo: Optional[str] = None,
        verified: bool = True
    ) -> bool:
        """Nastaví príznak overenia (verified) pre vozidlo v overrides.json."""
        vid = str(vehicle_id).strip() if vehicle_id else None
        ev = str(ev_cislo).strip() if ev_cislo else None
        target_keys = []
        if vid and vid in self.MANUAL_OVERRIDES:
            target_keys.append(vid)
        if ev and ev in self.MANUAL_OVERRIDES:
            target_keys.append(ev)

        if not target_keys:
            key = vid or ev
            if key:
                model = "Autobus DPMK"
                spz = None
                if ev and ev in self.ev_index:
                    model = self.ev_index[ev].get("model", model)
                    spz = self.ev_index[ev].get("spz")
                self.MANUAL_OVERRIDES[key] = {
                    "model": model,
                    "evidencne_cislo": ev or key,
                    "spz": spz,
                    "verified": bool(verified)
                }
                self.save_overrides()
                return True
            return False

        for k in target_keys:
            self.MANUAL_OVERRIDES[k]["verified"] = bool(verified)
        self.save_overrides()
        return True

    def _load_data(self):
        if not os.path.exists(self.csv_path):
            raise FileNotFoundError(f"Súbor datasetu {self.csv_path} nebol nájdený.")

        with open(self.csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []

            # Normalizácia názvov stĺpcov
            spz_col = next((c for c in fieldnames if "EČV" in c or "ŠPZ" in c), "EČV / ŠPZ")
            ev_col = next((c for c in fieldnames if "ev." in c.lower() or "číslo" in c.lower()), "ev. číslo")
            model_col = next((c for c in fieldnames if "typ" in c.lower()), "typ")
            ret_col = next((c for c in fieldnames if any(w in c.lower() for w in ["vyradenie", "likvid", "odstavenie"])), None)

            for row in reader:
                # Prísne vyfiltrovanie vyradených / zlikvidovaných historických vozidiel z celej histórie podniku.
                # Ponechávame výlučne prevádzkyschopné vozidlá, kde stĺpec vyradenia je prázdny.
                if ret_col:
                    ret_val = (row.get(ret_col) or "").strip()
                    if ret_val and ret_val.lower() not in ("", "nan", "none"):
                        continue

                model_raw = (row.get(model_col) or "").strip()
                # Dodatočný filter: vyradenie historických modelov (Karosa, Ikarus, Škoda a pod.)
                if not self.is_active_model(model_raw):
                    continue

                ev_raw = (row.get(ev_col) or "").strip().replace(".0", "")
                spz_raw = (row.get(spz_col) or "").strip()

                spz_clean = spz_raw.replace(" ", "").replace("-", "").upper()
                ev_clean = ev_raw

                # V pamäti držíme iba potrebné stĺpce (spz, evidencne_cislo, model)
                item = {
                    "evidencne_cislo": ev_clean,
                    "spz": spz_raw if spz_raw else None,
                    "model": model_raw if model_raw else None,
                }
                if ev_clean:
                    self.ev_index[ev_clean] = item
                if spz_clean:
                    self.spz_index[spz_clean] = item

        # Doplnenie najnovšieho vozového parku DPMK (elektrobusy a nové série)
        self._inject_modern_fleet()

    def _inject_modern_fleet(self):
        """
        Dopĺňa moderné a novododané vozidlá (SOR NS 18 Electric, SOR EBN, Solaris Urbino 18,75),
        ktoré neboli v pôvodnom CSV exporte.
        """
        # 1. SOR NS 18 Electric (4901 - 4911) - dodané 2026, linky 19 a 71
        ns18_plates = {
            "4901": "EL-748CC", "4902": "EL-734CC", "4903": "EL-739CC",
            "4904": "EL-729CC", "4905": "EL-737CC", "4906": "EL-715CC",
            "4907": "EL-713CC", "4908": "EL-513CB", "4909": "EL-746CC",
            "4910": "EL-736CC", "4911": "EL-735CC"
        }
        for ev, spz in ns18_plates.items():
            item = {
                "evidencne_cislo": ev,
                "spz": spz,
                "model": "SOR NS 18 Electric",
            }
            self.ev_index[ev] = item
            self.spz_index[spz.replace("-", "").replace(" ", "").upper()] = item

        # 2. SOR EBN 10.5 (6801 - 6805)
        ebn10_plates = {
            "6801": "P-03083", "6802": "KE-485JH", "6803": "KE-991JH",
            "6804": "KE-268JI", "6805": "KE-270JI"
        }
        for ev, spz in ebn10_plates.items():
            item = {
                "evidencne_cislo": ev,
                "spz": spz,
                "model": "SOR EBN 10.5",
            }
            self.ev_index[ev] = item
            self.spz_index[spz.replace("-", "").replace(" ", "").upper()] = item

        # 3. SOR EBN 11 (6901 - 6918)
        ebn11_plates = {
            "6901": "KE-975OT", "6902": "KE-732KF", "6903": "KE-001KG",
            "6904": "KE-721KF", "6905": "KE-360KH", "6906": "KE-395KH",
            "6907": "KE-454KI", "6908": "KE-180KI", "6909": "KE-442KI",
            "6910": "KE-310LH", "6911": "KE-340LH", "6912": "KE-256LH",
            "6913": "KE-952LG", "6914": "KE-909LG", "6915": "KE-885LG",
            "6916": "KE-122LH", "6917": "KE-262LH", "6918": "KE-030LH"
        }
        for ev, spz in ebn11_plates.items():
            item = {
                "evidencne_cislo": ev,
                "spz": spz,
                "model": "SOR EBN 11",
            }
            self.ev_index[ev] = item
            self.spz_index[spz.replace("-", "").replace(" ", "").upper()] = item

        # 4. Solaris Urbino 18,75 III (3906 - 3920)
        sol1875_plates = {
            "3906": "AA-086UO", "3907": "AA-135UO", "3908": "AA-156TY",
            "3909": "AA-136UO", "3910": "AA-278TY", "3911": "AA-104TY",
            "3912": "AA-963SL", "3913": "AA-930SL", "3914": "AA-727UU",
            "3915": "AA-223TY", "3916": "AA-728UU", "3917": "AA-161UO",
            "3918": "AA-205UO", "3919": "AA-265TY", "3920": "AA-267TY"
        }
        for ev, spz in sol1875_plates.items():
            item = {
                "evidencne_cislo": ev,
                "spz": spz,
                "model": "Solaris Urbino 18,75 III",
            }
            self.ev_index[ev] = item
            self.spz_index[spz.replace("-", "").replace(" ", "").upper()] = item

        # 5. SOR NSG 18 a SOR NSG 12
        nsg_plates = {
            "4801": ("AA-403EV", "SOR NSG 18"),
            "5802": ("AA-355EV", "SOR NSG 12"),
            "5803": ("AA-362EV", "SOR NSG 12")
        }
        for ev, (spz, model) in nsg_plates.items():
            item = {
                "evidencne_cislo": ev,
                "spz": spz,
                "model": model,
            }
            self.ev_index[ev] = item
            self.spz_index[spz.replace("-", "").replace(" ", "").upper()] = item

    def get_override(self, vehicle_id: Any = None, ev_cislo: Any = None) -> Optional[Dict[str, Any]]:
        """
        Skontroluje, či pre dané vehicle_id alebo evidenčné číslo existuje záznam v MANUAL_OVERRIDES.
        Slúži ako najvyššia autorita pravdy pre opravu hardvérových anomálií DPMK.
        """
        # 1. Prvoradá a striktná autorita: konkrétny hardvérový terminál vozidla (vehicle_id)
        if vehicle_id is not None:
            s_vid = str(vehicle_id).strip()
            if s_vid in self.MANUAL_OVERRIDES:
                return self.MANUAL_OVERRIDES[s_vid]

        # 2. Druhotná autorita: konkrétne evidenčné číslo (len pre vozidlá bez vlastného vehicle_id alebo v garáži)
        if ev_cislo is not None:
            s_ev = str(ev_cislo).strip()
            if s_ev in self.MANUAL_OVERRIDES:
                ov = self.MANUAL_OVERRIDES[s_ev]
                # Prísna ochrana pred cross-kontamináciou:
                # Override pod kľúčom s_ev musí patriť výhradne tomuto evidenčnému číslu!
                if str(ov.get("evidencne_cislo", "")).strip() == s_ev:
                    return ov

        return None

    RETIRED_MODELS = (
        "Karosa", "Ikarus", "Škoda", "Jelcz", "Chavdar", "TAM", 
        "Novoplan", "Iveco Citelis", "Tedom"
    )

    def is_active_model(self, model: Optional[str]) -> bool:
        """Overí, či daný model patrí k aktívnemu vozovému parku DPMK (vyradí historické modely z predošlých dekád)."""
        if not model:
            return False
        for ret in self.RETIRED_MODELS:
            if model.startswith(ret):
                return False
        return True

    def get_by_ev_cislo(self, ev_cislo: str, only_active: bool = False) -> Optional[Dict[str, Any]]:
        clean_ev = str(ev_cislo).strip()
        item = self.ev_index.get(clean_ev)
        override = self.get_override(ev_cislo=clean_ev)
        if override:
            res = dict(item) if item else {"evidencne_cislo": clean_ev}
            res.update(override)
            return res
        if only_active and item:
            if not self.is_active_model(item.get("model")):
                return None
        return item

    def get_by_spz(self, spz: str, only_active: bool = False) -> Optional[Dict[str, Any]]:
        clean = spz.replace(" ", "").replace("-", "").upper()
        item = self.spz_index.get(clean)
        if item:
            override = self.get_override(ev_cislo=item.get("evidencne_cislo"))
            if override:
                res = dict(item)
                res.update(override)
                return res
            if only_active and not self.is_active_model(item.get("model")):
                return None
        return item

    TRAM_LINES = {
        "1", "2", "3", "4", "5", "6", "7", "9",
        "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"
    }

    def is_tram(
        self,
        vehicle_id: Any = None,
        line: Optional[Any] = None,
        line_type: Optional[str] = None,
        ez_vehicle_type: Optional[str] = None,
        raw_vehicle: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Zistí, či vozidlo spĺňa podmienky pre električku:
        - ezVehicleType == 'TRAM'
        - line_type == 'tram' / 'TRAM'
        - číslo linky patrí medzi ['1','2','3','4','5','6','7','9','R1','R2','R3','R4','R5','R6','R7','R8']
        """
        # 1. Kontrola line_type / ezVehicleType parametrov
        types_to_check = [line_type, ez_vehicle_type]
        if raw_vehicle and isinstance(raw_vehicle, dict):
            types_to_check.extend([
                raw_vehicle.get("line_type"),
                raw_vehicle.get("ezVehicleType"),
                raw_vehicle.get("ezLineType"),
                raw_vehicle.get("vehicleType"),
            ])
            trip = raw_vehicle.get("timeTableTrip") or {}
            line_info = trip.get("timeTableLine") or {}
            types_to_check.extend([
                line_info.get("ezVehicleType"),
                line_info.get("ezLineType"),
            ])

        for t in types_to_check:
            if t and str(t).strip().upper() == "TRAM":
                return True

        # 2. Kontrola čísla linky
        lines_to_check = [line]
        if raw_vehicle and isinstance(raw_vehicle, dict):
            lines_to_check.extend([
                raw_vehicle.get("line"),
                raw_vehicle.get("line_name"),
            ])
            trip = raw_vehicle.get("timeTableTrip") or {}
            line_info = trip.get("timeTableLine") or {}
            lines_to_check.append(line_info.get("line"))

        for l in lines_to_check:
            if l:
                clean_line = str(l).strip().upper()
                if clean_line in self.TRAM_LINES:
                    return True

        return False

    def match_live_vehicle(
        self,
        vehicle_id: Any,
        license_number: Optional[str] = None,
        line: Optional[Any] = None,
        line_type: Optional[str] = None,
        ez_vehicle_type: Optional[str] = None,
        raw_vehicle: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        Pokúsi sa spárovať live vozidlo z telemetrie s vozovým parkom DPMK.
        Striktne dodržiava:
        1. Izoláciu električiek (žiadne miešanie s autobusmi, SPZ = None).
        2. Autoritu offline CSV pre aktívny vozový park.
        3. Zamedzenie hádania modelov: ak dekódované evidenčné číslo nie je v CSV,
           alebo by malo patriť vyradenému historickému autobusu, bezpečne nastaví 'Autobus DPMK'.
        4. MANUAL_OVERRIDES má absolútne najvyššiu prioritu.
        """
        # Podpora odovzdania celého slovníka ako prvý argument
        if isinstance(vehicle_id, dict):
            if not raw_vehicle:
                raw_vehicle = vehicle_id
            line = line or vehicle_id.get("line")
            line_type = line_type or vehicle_id.get("line_type")
            license_number = license_number or vehicle_id.get("license_number")
            vehicle_id = vehicle_id.get("vehicle_id")

        s_vid = str(vehicle_id).strip() if vehicle_id is not None else ""

        # =====================================================================
        # 0. NAJVYŠŠIA AUTORITA: Ak máme manuálny override pre tento konkrétny
        #    hardvérový terminál (vehicle_id), okamžite ho aplikujeme a vrátime.
        # =====================================================================
        if s_vid and s_vid in self.MANUAL_OVERRIDES:
            ov = self.MANUAL_OVERRIDES[s_vid]
            ev = ov.get("evidencne_cislo")
            base = self.ev_index.get(str(ev).strip()) if ev else None
            res = dict(base) if base else {
                "evidencne_cislo": ev or s_vid,
                "spz": ov.get("spz"),
                "model": ov.get("model", "Autobus DPMK"),
                "rok_vyroby": ov.get("rok_vyroby"),
                "vin": ov.get("vin"),
            }
            res.update(ov)
            if self.is_tram(
                vehicle_id=vehicle_id,
                line=line,
                line_type=line_type,
                ez_vehicle_type=ez_vehicle_type,
                raw_vehicle=raw_vehicle
            ) and not ov.get("spz"):
                res["spz"] = None
            return res

        # =====================================================================
        # 1. IZOLÁCIA ELEKTRIČIEK: Kontrola trakcie
        # =====================================================================
        if self.is_tram(
            vehicle_id=vehicle_id,
            line=line,
            line_type=line_type,
            ez_vehicle_type=ez_vehicle_type,
            raw_vehicle=raw_vehicle
        ):
            raw = raw_vehicle if isinstance(raw_vehicle, dict) else {}

            # Hľadanie skutočného názvu električky v Ubian dátach
            raw_model = (
                raw.get("vehicleName")
                or raw.get("model")
                or raw.get("vehicleType")
                or raw.get("vehicleTypeName")
                or kwargs.get("model")
            )

            if raw_model and str(raw_model).strip() and str(raw_model).strip().upper() != "TRAM":
                tram_model = str(raw_model).strip()
            else:
                tram_model = "Električka DPMK"

            tram_ev = (
                raw.get("evidencne_cislo")
                or raw.get("vehicleNumber")
                or (s_vid[-3:] if len(s_vid) >= 3 else (s_vid or None))
            )

            tram_vin = raw.get("vehicle_vin") or raw.get("vehicleIdentificationNumber") or (s_vid if s_vid else None)

            tram_res = {
                "evidencne_cislo": str(tram_ev) if tram_ev else None,
                "spz": None,
                "model": tram_model,
                "rok_vyroby": None,
                "vin": str(tram_vin) if tram_vin else None
            }
            ov = self.get_override(vehicle_id=s_vid, ev_cislo=tram_ev)
            if ov:
                tram_res.update(ov)
                if not ov.get("spz"):
                    tram_res["spz"] = None
            return tram_res
        match = None

        # 1. Ak telemetria priamo obsahuje ŠPZ (len pre aktívne autobusy)
        if license_number:
            match = self.get_by_spz(license_number, only_active=True)

        # 2. Ak máme záznam v TRANSDATA_MAPPING
        if not match and s_vid in self.TRANSDATA_MAPPING:
            target_ev = self.TRANSDATA_MAPPING[s_vid]
            match = self.get_by_ev_cislo(target_ev, only_active=True)
            if not match:
                match = {
                    "evidencne_cislo": target_ev,
                    "spz": None,
                    "model": "Autobus DPMK",
                    "rok_vyroby": None,
                    "vin": None
                }

        # 3. Priamy match na ev. číslo (ak by bolo identické a patrí aktívnemu vozidlu)
        if not match:
            direct_match = self.get_by_ev_cislo(s_vid, only_active=True)
            if direct_match:
                match = direct_match

        # 4. Inteligentné TransData ID dekódovanie na evidenčné čísla DPMK
        if not match and len(s_vid) == 7 and s_vid.isdigit():
            candidates = []
            prefix5 = s_vid[:5]
            prefix6 = s_vid[:6]
            last2 = s_vid[-2:]
            last_dig = s_vid[-1]
            vid_int = int(s_vid)

            # Nová séria SOR NS 18 Electric (1403381 - 1403391) -> 4901 - 4911
            if 1403381 <= vid_int <= 1403391:
                num = vid_int - 1403380
                candidates.append(f"49{num:02d}")

            # Nová séria SOR NS 18 Electric (1276491 - 1276499) -> 4901 - 4909
            elif prefix6 == "127649":
                candidates.append(f"490{last_dig}")

            # Výrobné čísla SOR NB (posledné 3 cifry)
            elif s_vid[-3:] in getattr(self, "vin_prod_index", {}):
                candidates.append(self.vin_prod_index[s_vid[-3:]])

            # Dekódovacie vzorce pre TransData 7-miestne prefixy aktívnych autobusov
            elif prefix5 == "12761":
                candidates.extend(["47" + last2, "57" + last2])
            elif prefix5 == "12762":
                # Len moderné SOR NB (47xx/57xx). Nikdy nepriraďovať vyradené Karosy 62xx!
                candidates.extend(["47" + last2, "57" + last2])
            elif prefix5 == "12763":
                candidates.extend(["57" + last2, "47" + last2])
            elif prefix5 == "12764":
                candidates.extend(["47" + last2, "57" + last2])
            elif prefix5 == "12765":
                candidates.extend(["57" + last2, "47" + last2])
            elif prefix5 == "12766":
                candidates.extend(["47" + last2, "57" + last2])
            elif prefix5 == "12767":
                candidates.extend(["47" + last2, "67" + last2])
            elif prefix5 == "12770":
                candidates.extend(["47" + last2, "57" + last2])
            elif prefix5 == "12775":
                candidates.extend(["47" + last2, "57" + last2])
            elif prefix5 == "12778":
                candidates.extend(["33" + last2, "47" + last2])
            elif prefix5 == "12779":
                candidates.extend(["39" + last2, "47" + last2, "57" + last2])
            elif prefix5 == "12781":
                candidates.extend(["47" + last2, "57" + last2, "39" + last2])
            elif prefix5 == "12782":
                candidates.extend(["47" + last2, "57" + last2, "69" + last2])
            elif s_vid.startswith("1402"):
                candidates.extend(["39" + last2, "47" + last2, "57" + last2])

            for cand in candidates:
                cand_match = self.get_by_ev_cislo(cand, only_active=True)
                if cand_match:
                    match = cand_match
                    break

            # Ak prekladač vygeneroval evidenčné číslo, ale v CSV sa nenachádza:
            # Zamedzenie hádania modelov: zakáž priradiť náhodný model z iných záznamov.
            if not match and candidates:
                calculated_ev = candidates[0]
                match = {
                    "evidencne_cislo": calculated_ev,
                    "spz": None,
                    "model": "Autobus DPMK",
                    "rok_vyroby": None,
                    "vin": None
                }

        # 5. Match podľa posledných 4 cifier (ak predchádzajúce zlyhalo)
        if not match and len(s_vid) >= 4:
            suffix = s_vid[-4:]
            cand_match = self.get_by_ev_cislo(suffix, only_active=True)
            if cand_match:
                match = cand_match
            else:
                # Ak číslo nie je v CSV, bezpečne označíme ako 'Autobus DPMK'
                match = {
                    "evidencne_cislo": suffix,
                    "spz": None,
                    "model": "Autobus DPMK",
                    "rok_vyroby": None,
                    "vin": None
                }

        # NAJVYŠŠIA AUTORITA PRAVDY: Kontrola MANUAL_OVERRIDES tesne pred vrátením dát
        matched_ev = match.get("evidencne_cislo") if match else (s_vid[-4:] if len(s_vid) >= 4 else None)
        override = self.get_override(vehicle_id=s_vid, ev_cislo=matched_ev)
        if override:
            res = dict(match) if match else {
                "evidencne_cislo": override.get("evidencne_cislo", s_vid),
                "spz": override.get("spz"),
                "model": override.get("model"),
                "rok_vyroby": override.get("rok_vyroby"),
                "vin": override.get("vin"),
            }
            res.update(override)
            return res

        return match

    def get_all_vehicles(self, only_active: bool = False) -> List[Dict[str, Any]]:
        """
        Vráti kompletný zoznam všetkých vozidiel evidovaných v lokálnej databáze/CSV,
        vrátane manuálnych prepisov a dodatočne dodaných moderných vozidiel.
        """
        vehicles = []
        for ev, item in self.ev_index.items():
            if only_active and not self.is_active_model(item.get("model")):
                continue
            v = dict(item)
            override = self.get_override(ev_cislo=ev)
            if override:
                v.update(override)
            vehicles.append(v)

        def sort_key(x):
            ev_str = str(x.get("evidencne_cislo", ""))
            try:
                return (0, int(ev_str))
            except ValueError:
                return (1, ev_str)

        vehicles.sort(key=sort_key)
        return vehicles
