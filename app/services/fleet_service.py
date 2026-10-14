from __future__ import annotations
import os
import json
import csv
import time
import uuid
from datetime import datetime
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

    def __init__(self, csv_path: str, overrides_path: Optional[str] = None, pending_requests_path: Optional[str] = None):
        self.csv_path = csv_path
        self.overrides_path = overrides_path or os.path.join(os.path.dirname(self.csv_path), "overrides.json")
        self.pending_requests_path = pending_requests_path or os.path.join(os.path.dirname(self.csv_path), "pending_requests.json")
        self.MANUAL_OVERRIDES = self._load_overrides()
        self.pending_requests = self._load_pending_requests()
        self.spz_index = {}
        self.ev_index = {}
        self.vin_prod_index = {
            "394": "4743",  # SOR NB 18 City (KE-095JE)
            "395": "4732",  # SOR NB 18 City (KE-008JE)
            "396": "4721",  # SOR NB 18 City (AA-741PJ)
        }
        self._load_data()

    def _find_overrides_file(self) -> str:
        """Nájde skutočnú absolútnu cestu k súboru data/overrides.json na disku."""
        candidates = []
        if self.overrides_path:
            candidates.append(self.overrides_path)
        if self.csv_path:
            candidates.append(os.path.join(os.path.dirname(self.csv_path), "overrides.json"))
        # Cesta v rámci projektu
        base_dir = os.path.dirname(os.path.abspath(__file__))
        proj_dir = os.path.dirname(os.path.dirname(base_dir))
        candidates.append(os.path.join(proj_dir, "data", "overrides.json"))
        candidates.append(os.path.join(os.getcwd(), "data", "overrides.json"))
        candidates.append(os.path.abspath("data/overrides.json"))

        for c in candidates:
            if c and os.path.exists(c):
                return os.path.abspath(c)
        return self.overrides_path or os.path.abspath("data/overrides.json")

    def _load_overrides(self) -> Dict[str, Dict[str, Any]]:
        """Dynamicky načíta manuálne pravidlá zo súboru data/overrides.json pri štarte servera s čistými kľúčmi bez '#'."""
        path = self._find_overrides_file()
        self.overrides_path = path
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        clean_dict: Dict[str, Dict[str, Any]] = {}
                        for k, v in data.items():
                            clean_k = str(k).strip().replace("#", "")
                            if clean_k and isinstance(v, dict):
                                clean_item = dict(v)
                                if "evidencne_cislo" in clean_item and clean_item["evidencne_cislo"] is not None:
                                    clean_item["evidencne_cislo"] = str(clean_item["evidencne_cislo"]).strip().replace("#", "")
                                clean_dict[clean_k] = clean_item
                        FleetService.MANUAL_OVERRIDES = clean_dict
                        print(f"[FleetService] Uspesne nacitanych {len(clean_dict)} overrides zo suboru: {path}")
                        return clean_dict
            except Exception as e:
                print(f"[FleetService] Chyba pri nacitani overrides zo suboru {path}: {e}")
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
        """Uloží aktuálne MANUAL_OVERRIDES do súboru data/overrides.json s čistými kľúčmi bez '#'."""
        try:
            os.makedirs(os.path.dirname(self.overrides_path), exist_ok=True)
            clean_dict: Dict[str, Dict[str, Any]] = {}
            for k, v in self.MANUAL_OVERRIDES.items():
                clean_k = str(k).strip().replace("#", "")
                if clean_k and isinstance(v, dict):
                    clean_item = dict(v)
                    if "evidencne_cislo" in clean_item and clean_item["evidencne_cislo"] is not None:
                        clean_item["evidencne_cislo"] = str(clean_item["evidencne_cislo"]).strip().replace("#", "")
                    clean_dict[clean_k] = clean_item
            self.MANUAL_OVERRIDES = clean_dict
            FleetService.MANUAL_OVERRIDES = clean_dict
            with open(self.overrides_path, "w", encoding="utf-8") as f:
                json.dump(clean_dict, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Chyba pri ukladani overrides do {self.overrides_path}: {e}")
            return False

    def _load_pending_requests(self) -> List[Dict[str, Any]]:
        """Dynamicky načíta čakajúce komunitné požiadavky zo súboru data/pending_requests.json."""
        if os.path.exists(self.pending_requests_path):
            try:
                with open(self.pending_requests_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
            except Exception as e:
                print(f"Chyba pri nacitani pending requests zo suboru {self.pending_requests_path}: {e}")
        return []

    def save_pending_requests(self) -> bool:
        """Uloží zoznam čakajúcich požiadaviek do súboru data/pending_requests.json."""
        try:
            os.makedirs(os.path.dirname(self.pending_requests_path), exist_ok=True)
            with open(self.pending_requests_path, "w", encoding="utf-8") as f:
                json.dump(self.pending_requests, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Chyba pri ukladani pending requests do {self.pending_requests_path}: {e}")
            return False

    def add_fan_suggestion(
        self,
        suggested_model: str,
        evidencne_cislo: Optional[str] = None,
        vehicle_id: Optional[str] = None,
        current_model: Optional[str] = None,
        current_spz: Optional[str] = None,
        suggested_spz: Optional[str] = None,
        note: Optional[str] = None
    ) -> Dict[str, Any]:
        """Uloží nový komunitný návrh od fanúšika na schválenie moderátorom."""
        self.pending_requests = self._load_pending_requests()
        req_id = f"req_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        record = {
            "id": req_id,
            "created_at": datetime.now().isoformat(),
            "vehicle_id": str(vehicle_id).strip() if vehicle_id is not None and str(vehicle_id).strip() else None,
            "evidencne_cislo": str(evidencne_cislo).strip() if evidencne_cislo is not None and str(evidencne_cislo).strip() else None,
            "current_model": str(current_model).strip() if current_model else None,
            "current_spz": str(current_spz).strip() if current_spz else None,
            "suggested_model": str(suggested_model).strip(),
            "suggested_spz": str(suggested_spz).strip().upper() if suggested_spz and str(suggested_spz).strip() else None,
            "note": str(note).strip() if note else "",
            "status": "pending"
        }
        self.pending_requests.insert(0, record)
        self.save_pending_requests()
        return record

    def get_pending_requests(self, status: Optional[str] = "pending") -> List[Dict[str, Any]]:
        """Vráti zoznam čakajúcich požiadaviek (alebo podľa statusu)."""
        self.pending_requests = self._load_pending_requests()
        if not status:
            return self.pending_requests
        return [r for r in self.pending_requests if r.get("status") == status]

    def approve_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        """Schváli požiadavku, zapíše ju do perzistentných prepisov (MANUAL_OVERRIDES) a uloží."""
        self.pending_requests = self._load_pending_requests()
        target = None
        for r in self.pending_requests:
            if str(r.get("id")) == str(request_id):
                target = r
                break

        if not target:
            return None

        target["status"] = "approved"
        target["reviewed_at"] = datetime.now().isoformat()

        # Vyriešenie prípadnej kolízie evidenčného čísla pred schválením
        if target.get("evidencne_cislo"):
            self.resolve_evidencne_cislo_conflict(
                target_vehicle_id=target.get("vehicle_id"),
                new_ev_cislo=target.get("evidencne_cislo")
            )

        # Aplikujeme schválené údaje priamo do existujúceho systému perzistentných prepisov
        self.add_override(
            model=target.get("suggested_model", "Autobus DPMK"),
            evidencne_cislo=target.get("evidencne_cislo"),
            vehicle_id=target.get("vehicle_id"),
            spz=target.get("suggested_spz"),
            verified=True,
            note=target.get("note")
        )

        self.save_pending_requests()
        return target

    def reject_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        """Zamietne požiadavku a zmení jej status na 'rejected'."""
        self.pending_requests = self._load_pending_requests()
        target = None
        for r in self.pending_requests:
            if str(r.get("id")) == str(request_id):
                target = r
                break

        if not target:
            return None

        target["status"] = "rejected"
        target["reviewed_at"] = datetime.now().isoformat()
        self.save_pending_requests()
        return target

    def _get_next_free_reassign_ev(self) -> str:
        """
        Nájde najnižšie voľné číslo v rozsahu 90000 až 99999 (napr. 90001, 90002...),
        ktoré zatiaľ nie je priradené žiadnemu vozidlu v systéme.
        """
        used_numbers = set()
        for ev in self.ev_index.keys():
            used_numbers.add(str(ev).strip())
        for ev in self.TRANSDATA_MAPPING.values():
            used_numbers.add(str(ev).strip())
        for k, ov in self.MANUAL_OVERRIDES.items():
            used_numbers.add(str(k).strip())
            if isinstance(ov, dict):
                ev_val = ov.get("evidencne_cislo")
                if ev_val:
                    used_numbers.add(str(ev_val).strip())

        for n in range(90001, 100000):
            cand = str(n)
            if cand not in used_numbers:
                return cand
        return "99999"

    def resolve_evidencne_cislo_conflict(
        self,
        target_vehicle_id: Optional[str],
        new_ev_cislo: Optional[str],
        original_evidencne_cislo: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Deteguje a automaticky vyrieši kolíziu evidenčných čísel vozidiel.
        Ak new_ev_cislo už patrí inému vozidlu v systéme (v MANUAL_OVERRIDES,
        TRANSDATA_MAPPING alebo v načítanej flotile z CSV/ev_index), ktorého
        vehicle_id != target_vehicle_id:
        1. Nájde najnižšie voľné náhradné číslo v rozsahu 90000–99999 (napr. 90001, 90002...).
        2. Pôvodnému kolíznemu vozidlu nastaví toto náhradné číslo (90xxx)
           a zapíše ho do MANUAL_OVERRIDES pod jeho pôvodným vehicle_id
           s poznámkou 'kolízne prečíslovanie'.
        3. Uloží zmeny do data/overrides.json.
        Vráti zoznam vyriešených kolízií.
        """
        if not new_ev_cislo:
            return []

        target_ev = str(new_ev_cislo).strip()
        if not target_ev:
            return []

        target_vid = str(target_vehicle_id).strip() if target_vehicle_id is not None and str(target_vehicle_id).strip() else None
        orig_ev = str(original_evidencne_cislo).strip() if original_evidencne_cislo is not None and str(original_evidencne_cislo).strip() else None

        # Ak cieľové vozidlo nemení evidenčné číslo (alebo ide o úpravu modelu/ŠPZ vozidla v garáži), nejde o kolíziu
        if (orig_ev and orig_ev == target_ev) or (not orig_ev and not target_vid):
            return []

        conflicts = []
        seen_keys = set()

        # 1. Kontrola MANUAL_OVERRIDES
        for k, ov in list(self.MANUAL_OVERRIDES.items()):
            if not isinstance(ov, dict):
                continue
            ov_ev = str(ov.get("evidencne_cislo") or k).strip()
            if ov_ev == target_ev:
                # Ak kľúč je samotné evidenčné číslo alebo pôvodné ev. číslo, nejde o kolíziu iného vozidla
                if k == target_ev or (orig_ev and orig_ev == k):
                    continue
                # Ak ide o samotné cieľové vehicle_id, preskočíme
                if target_vid and k == target_vid:
                    continue
                # Ak kľúč patrí k tomu istému vozidlu cez TRANSDATA_MAPPING
                if self.TRANSDATA_MAPPING.get(k) == target_ev:
                    continue
                # Ak ide o TransData kandidáta tohto istého vozidla
                if len(k) == 7 and k.isdigit() and target_ev in self._decode_transdata_candidates(k):
                    continue
                conflicts.append((k, ov))
                seen_keys.add(k)

        # 2. Kontrola TRANSDATA_MAPPING
        for tid, mapped_ev in list(self.TRANSDATA_MAPPING.items()):
            if str(mapped_ev).strip() == target_ev:
                # Ak nemáme target_vid (úprava v garáži) alebo ide o cieľové vozidlo / jeho kandidáta
                if not target_vid or tid == target_vid:
                    continue
                if len(tid) == 7 and tid.isdigit() and target_ev in self._decode_transdata_candidates(tid):
                    continue
                if tid in seen_keys:
                    continue
                # Ak už má v MANUAL_OVERRIDES iné evidenčné číslo, už bolo prečíslované
                if tid in self.MANUAL_OVERRIDES:
                    curr_ev = str(self.MANUAL_OVERRIDES[tid].get("evidencne_cislo", "")).strip()
                    if curr_ev and curr_ev != target_ev:
                        continue
                conflicts.append((tid, None))
                seen_keys.add(tid)

        # 3. Kontrola načítanej flotily z CSV (ev_index)
        if target_ev in self.ev_index:
            is_target_self = False
            if target_vid:
                if target_vid == target_ev:
                    is_target_self = True
                elif self.TRANSDATA_MAPPING.get(target_vid) == target_ev:
                    is_target_self = True
                elif target_vid in self.MANUAL_OVERRIDES and str(self.MANUAL_OVERRIDES[target_vid].get("evidencne_cislo", "")).strip() == target_ev:
                    is_target_self = True
            elif not target_vid and (not orig_ev or orig_ev == target_ev):
                is_target_self = True

            if not is_target_self:
                mapped_vids = [tid for tid, mev in self.TRANSDATA_MAPPING.items() if str(mev).strip() == target_ev]
                already_covered = any(v in seen_keys for v in mapped_vids) or (target_ev in seen_keys)
                if not already_covered:
                    if target_ev in self.MANUAL_OVERRIDES:
                        curr_ev = str(self.MANUAL_OVERRIDES[target_ev].get("evidencne_cislo", "")).strip()
                        if curr_ev and curr_ev != target_ev:
                            already_covered = True

                    if not already_covered:
                        conflicts.append((target_ev, self.ev_index.get(target_ev)))
                        seen_keys.add(target_ev)

        if not conflicts:
            return []

        resolved_conflicts = []

        for conf_key, existing_data in conflicts:
            replacement_ev = self._get_next_free_reassign_ev()

            # Zistenie modelu a ŠPZ kolízneho vozidla
            model = "Autobus DPMK"
            spz = None
            verified = False

            if existing_data and isinstance(existing_data, dict):
                model = existing_data.get("model") or model
                spz = existing_data.get("spz")
                verified = existing_data.get("verified", False)
            elif conf_key in self.MANUAL_OVERRIDES:
                ov = self.MANUAL_OVERRIDES[conf_key]
                model = ov.get("model") or model
                spz = ov.get("spz")
                verified = ov.get("verified", False)
            elif conf_key in self.ev_index:
                base = self.ev_index[conf_key]
                model = base.get("model") or model
                spz = base.get("spz")

            # Priradenie náhradného čísla (90xxx) s poznámkou "kolízne prečíslovanie"
            entry = {
                "model": model,
                "evidencne_cislo": replacement_ev,
                "spz": spz,
                "verified": verified,
                "note": "kolízne prečíslovanie"
            }

            # Ak conf_key je hardware vehicle_id (alebo ľubovoľný kľúč odlišný od target_ev):
            if conf_key != target_ev:
                self.MANUAL_OVERRIDES[conf_key] = entry
                if conf_key in self.TRANSDATA_MAPPING:
                    self.TRANSDATA_MAPPING[conf_key] = replacement_ev
            else:
                # Vozidlo z CSV bez samostatného hardware vehicle_id
                self.MANUAL_OVERRIDES[replacement_ev] = entry
                if target_ev in self.MANUAL_OVERRIDES:
                    del self.MANUAL_OVERRIDES[target_ev]

            # Aktualizácia indexov v pamäti
            self.ev_index[replacement_ev] = {
                "evidencne_cislo": replacement_ev,
                "spz": spz,
                "model": model
            }
            if spz:
                clean_spz = spz.replace("-", "").replace(" ", "").upper()
                if clean_spz in self.spz_index:
                    self.spz_index[clean_spz]["evidencne_cislo"] = replacement_ev

            resolved_item = {
                "vehicle_id": conf_key,
                "old_evidencne_cislo": target_ev,
                "new_evidencne_cislo": replacement_ev,
                "note": "kolízne prečíslovanie"
            }
            resolved_conflicts.append(resolved_item)
            print(f"[FleetService] Kolizia evidencneho cisla {target_ev}: vozidlo '{conf_key}' bolo automaticky precislonavane na '{replacement_ev}' (kolizne precitlovanie).")

        self.save_overrides()
        return resolved_conflicts

    def add_override(
        self,
        model: str,
        evidencne_cislo: Optional[str] = None,
        vehicle_id: Optional[str] = None,
        spz: Optional[str] = None,
        original_evidencne_cislo: Optional[str] = None,
        verified: Optional[bool] = None,
        note: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Dynamicky pridá alebo aktualizuje override pre model, evidenčné číslo vozidla a ŠPZ,
        uloží do data/overrides.json a okamžite aktualizuje indexy v pamäti.
        Dôsledne izoluje vozidlá podľa ich unikátneho hardvérového vehicle_id,
        čím zabraňuje duplicite a nechcenému prepisovaniu iných vozidiel.
        Podporuje príznak 'verified' (overené vozidlo v Developer Mode).
        Automaticky deteguje a rieši kolízie evidenčných čísel prečíslovaním pôvodného vozidla na 90xxx.
        """
        vid = str(vehicle_id).strip().replace("#", "") if vehicle_id else None
        ev = str(evidencne_cislo).strip().replace("#", "") if evidencne_cislo else None
        orig_ev = str(original_evidencne_cislo).strip().replace("#", "") if original_evidencne_cislo else None
        clean_spz = spz.strip().replace("#", "").upper() if spz and str(spz).strip() else None

        final_ev = ev or (orig_ev if orig_ev else (vid if vid else ""))

        # Automatické riešenie kolízií evidenčného čísla:
        # Ak final_ev už patrí inému vozidlu, pôvodné vozidlo je automaticky prečíslované na 90000–99999
        if final_ev:
            self.resolve_evidencne_cislo_conflict(
                target_vehicle_id=vid,
                new_ev_cislo=final_ev,
                original_evidencne_cislo=orig_ev
            )

        # Automaticky nastavíme verified: True pri administrátorskom uložení
        final_verified = True if verified is None else bool(verified)

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
        if note is not None and str(note).strip():
            entry["note"] = str(note).strip()
        elif vid and vid in self.MANUAL_OVERRIDES and self.MANUAL_OVERRIDES[vid].get("note"):
            entry["note"] = self.MANUAL_OVERRIDES[vid]["note"]

        # 1. Ak ide o reálne vozidlo z live telemetrie s vlastným vehicle_id:
        if vid:
            clean_key = str(vid).strip().replace("#", "")
            self.MANUAL_OVERRIDES[clean_key] = entry
            if f"#{clean_key}" in self.MANUAL_OVERRIDES:
                del self.MANUAL_OVERRIDES[f"#{clean_key}"]

            if final_ev:
                clean_ev_key = str(final_ev).strip().replace("#", "")
                self.MANUAL_OVERRIDES[clean_ev_key] = entry
                if f"#{clean_ev_key}" in self.MANUAL_OVERRIDES:
                    del self.MANUAL_OVERRIDES[f"#{clean_ev_key}"]
                self.TRANSDATA_MAPPING[clean_key] = clean_ev_key
                if clean_ev_key not in self.ev_index:
                    self.ev_index[clean_ev_key] = {
                        "evidencne_cislo": clean_ev_key,
                        "spz": clean_spz,
                        "model": entry["model"],
                        "verified": final_verified,
                        "is_verified": final_verified
                    }
                else:
                    self.ev_index[clean_ev_key]["model"] = entry["model"]
                    self.ev_index[clean_ev_key]["verified"] = final_verified
                    self.ev_index[clean_ev_key]["is_verified"] = final_verified
                    if clean_spz:
                        self.ev_index[clean_ev_key]["spz"] = clean_spz

            # Bezpečnostné čistenie: ak v minulosti existoval chybný záznam pod pôvodným ev číslom,
            # ktorý ukazoval na iné vozidlo (cross-kontaminácia), odstránime ho.
            if orig_ev:
                clean_old = str(orig_ev).strip().replace("#", "")
                if clean_old in self.MANUAL_OVERRIDES and self.MANUAL_OVERRIDES[clean_old].get("evidencne_cislo") != clean_old:
                    del self.MANUAL_OVERRIDES[clean_old]

        # 2. Ak ide o statické vozidlo bez vehicle_id (napr. úprava vozidla priamo v depe/garáži):
        elif final_ev:
            clean_key = str(final_ev).strip().replace("#", "")
            self.MANUAL_OVERRIDES[clean_key] = entry
            if f"#{clean_key}" in self.MANUAL_OVERRIDES:
                del self.MANUAL_OVERRIDES[f"#{clean_key}"]

            # Obojsmerné prepojenie so všetkými známymi hardware vehicle_id pre toto evidenčné číslo:
            mapped_vids = [t_vid for t_vid, mev in self.TRANSDATA_MAPPING.items() if str(mev).strip().replace("#", "") == clean_key]
            for t_vid in mapped_vids:
                clean_tvid = str(t_vid).strip().replace("#", "")
                self.MANUAL_OVERRIDES[clean_tvid] = entry
                if f"#{clean_tvid}" in self.MANUAL_OVERRIDES:
                    del self.MANUAL_OVERRIDES[f"#{clean_tvid}"]
            for k_ov, v_ov in list(self.MANUAL_OVERRIDES.items()):
                if isinstance(v_ov, dict) and str(v_ov.get("evidencne_cislo", "")).strip().replace("#", "") == clean_key:
                    self.MANUAL_OVERRIDES[k_ov] = entry

            if clean_key in self.ev_index:
                self.ev_index[clean_key]["model"] = entry["model"]
                self.ev_index[clean_key]["verified"] = final_verified
                self.ev_index[clean_key]["is_verified"] = final_verified
                if clean_spz:
                    self.ev_index[clean_key]["spz"] = clean_spz
            else:
                self.ev_index[clean_key] = {
                    "evidencne_cislo": clean_key,
                    "spz": clean_spz,
                    "model": entry["model"],
                    "verified": final_verified,
                    "is_verified": final_verified
                }

        # Aktualizácia indexu pre vyhľadávanie podľa ŠPZ
        if clean_spz:
            clean_search_spz = clean_spz.replace("-", "").replace(" ", "").upper()
            if clean_search_spz in self.spz_index:
                self.spz_index[clean_search_spz]["model"] = entry["model"]
                if final_ev:
                    self.spz_index[clean_search_spz]["evidencne_cislo"] = final_ev
            elif final_ev and final_ev in self.ev_index:
                self.spz_index[clean_search_spz] = self.ev_index[final_ev]

        FleetService.MANUAL_OVERRIDES = self.MANUAL_OVERRIDES
        self.save_overrides()
        return entry

    def set_override(
        self,
        model: str,
        evidencne_cislo: Optional[str] = None,
        vehicle_id: Optional[str] = None,
        spz: Optional[str] = None,
        original_evidencne_cislo: Optional[str] = None,
        verified: Optional[bool] = None,
        note: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Nastaví manuálny override pre vozidlo.
        Automaticky deteguje a rieši kolízie evidenčných čísel prečíslovaním pôvodného vozidla na 90xxx.
        """
        return self.add_override(
            model=model,
            evidencne_cislo=evidencne_cislo,
            vehicle_id=vehicle_id,
            spz=spz,
            original_evidencne_cislo=original_evidencne_cislo,
            verified=verified,
            note=note
        )

    def set_verified(
        self,
        vehicle_id: Optional[str] = None,
        ev_cislo: Optional[str] = None,
        verified: bool = True
    ) -> bool:
        """Nastaví príznak overenia (verified) pre vozidlo v overrides.json pod čistým kľúčom bez '#'."""
        vid = str(vehicle_id).strip().replace("#", "") if vehicle_id else None
        ev = str(ev_cislo).strip().replace("#", "") if ev_cislo else None
        target_keys = []
        if vid:
            if vid in self.MANUAL_OVERRIDES:
                target_keys.append(vid)
            elif f"#{vid}" in self.MANUAL_OVERRIDES:
                target_keys.append(f"#{vid}")
        if ev:
            if ev in self.MANUAL_OVERRIDES:
                target_keys.append(ev)
            elif f"#{ev}" in self.MANUAL_OVERRIDES:
                target_keys.append(f"#{ev}")

        if not target_keys:
            key = vid or ev
            if key:
                clean_key = str(key).strip().replace("#", "")
                model = "Autobus DPMK"
                spz = None
                if ev and ev in self.ev_index:
                    model = self.ev_index[ev].get("model", model)
                    spz = self.ev_index[ev].get("spz")
                self.MANUAL_OVERRIDES[clean_key] = {
                    "model": model,
                    "evidencne_cislo": ev or clean_key,
                    "spz": spz,
                    "verified": bool(verified)
                }
                if f"#{clean_key}" in self.MANUAL_OVERRIDES:
                    del self.MANUAL_OVERRIDES[f"#{clean_key}"]
                self.save_overrides()
                return True
            return False

        for k in target_keys:
            clean_k = str(k).strip().replace("#", "")
            val = self.MANUAL_OVERRIDES[k]
            val["verified"] = bool(verified)
            if k != clean_k:
                self.MANUAL_OVERRIDES[clean_k] = val
                if k in self.MANUAL_OVERRIDES:
                    del self.MANUAL_OVERRIDES[k]
            else:
                self.MANUAL_OVERRIDES[clean_k] = val
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

        # Synchronizácia všetkých manuálnych prepisov a overení do indexov flotily
        self._sync_overrides_into_indices()

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

        # 6. Električky DPMK (Vario LF2+, Tatra KT8D5.RN2, Tatra T6A5)
        # Vario LF2+ (evid. čísla 801 - 846)
        for num in range(801, 847):
            ev_str = str(num)
            if ev_str not in self.ev_index:
                self.ev_index[ev_str] = {
                    "evidencne_cislo": ev_str,
                    "spz": None,
                    "model": "Vario LF2+"
                }
        # Tatra KT8D5.RN2 (zmodernizované trojčlánkové obojsmerné električky s NP stredom)
        for num in [500, 508, 509, 512, 513, 517, 521, 522, 523, 525, 528, 529, 531, 534, 536, 537, 538]:
            ev_str = str(num)
            if ev_str not in self.ev_index:
                self.ev_index[ev_str] = {
                    "evidencne_cislo": ev_str,
                    "spz": None,
                    "model": "Tatra KT8D5.RN2"
                }
        # Tatra T6A5 (evid. čísla 600 - 629)
        for num in range(600, 630):
            ev_str = str(num)
            if ev_str not in self.ev_index:
                self.ev_index[ev_str] = {
                    "evidencne_cislo": ev_str,
                    "spz": None,
                    "model": "Tatra T6A5"
                }

    def _sync_overrides_into_indices(self):
        """
        Synchronizuje všetky perzistentné manuálne prepisy (MANUAL_OVERRIDES) do
        indexov ev_index, spz_index a TRANSDATA_MAPPING.
        Tým garantuje, že pri štarte servera sú všetky ručne opravené vozidlá
        okamžite dostupné vo všetkých vyhľadávacích indexoch.
        """
        for k, ov in list(self.MANUAL_OVERRIDES.items()):
            if not isinstance(ov, dict):
                continue
            clean_k = str(k).strip().replace("#", "")
            ev = ov.get("evidencne_cislo")
            clean_ev = str(ev).strip().replace("#", "") if ev else clean_k
            spz = ov.get("spz")
            model = ov.get("model")
            verified = bool(ov.get("verified", False))

            # Ak je kľúč hardware vehicle_id (napr. 7-miestne číslo TransData), namapujeme ho
            if len(clean_k) == 7 and clean_k.isdigit() and clean_ev:
                self.TRANSDATA_MAPPING[clean_k] = clean_ev

            # Aktualizácia ev_index
            if clean_ev:
                if clean_ev in self.ev_index:
                    if model:
                        self.ev_index[clean_ev]["model"] = model
                    if spz:
                        self.ev_index[clean_ev]["spz"] = spz
                    self.ev_index[clean_ev]["verified"] = verified
                    self.ev_index[clean_ev]["is_verified"] = verified
                else:
                    self.ev_index[clean_ev] = {
                        "evidencne_cislo": clean_ev,
                        "spz": spz,
                        "model": model or "Autobus DPMK",
                        "verified": verified,
                        "is_verified": verified
                    }

            # Aktualizácia spz_index
            if spz:
                clean_spz = spz.replace("-", "").replace(" ", "").upper()
                if clean_ev and clean_ev in self.ev_index:
                    self.spz_index[clean_spz] = self.ev_index[clean_ev]

    def _decode_transdata_candidates(self, s_vid: str) -> List[str]:
        """Vygeneruje zoznam kandidátskych evidenčných čísel pre 7-miestne TransData ID."""
        if len(s_vid) != 7 or not s_vid.isdigit():
            return [s_vid[-4:]] if len(s_vid) >= 4 else []

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
        elif prefix6 == "127649":
            candidates.append(f"490{last_dig}")
        elif s_vid[-3:] in getattr(self, "vin_prod_index", {}):
            candidates.append(self.vin_prod_index[s_vid[-3:]])
        elif prefix5 == "12761":
            candidates.extend(["47" + last2, "57" + last2])
        elif prefix5 == "12762":
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

        if s_vid[-4:] not in candidates:
            candidates.append(s_vid[-4:])

        return candidates

    def get_override(
        self,
        vehicle_id: Any = None,
        ev_cislo: Any = None,
        license_number: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Skontroluje, či pre dané vehicle_id, evidenčné číslo alebo ŠPZ existuje záznam v MANUAL_OVERRIDES.
        Slúži ako najvyššia autorita pravdy pre opravu hardvérových anomálií DPMK
        a zabezpečuje korektné prebudenie vozidla z garáže (offline) do aktívnej premávky.
        """
        s_vid = str(vehicle_id).strip().replace("#", "") if vehicle_id is not None and str(vehicle_id).strip() else None
        s_ev = str(ev_cislo).strip().replace("#", "") if ev_cislo is not None and str(ev_cislo).strip() else None
        clean_lic = license_number.replace("-", "").replace(" ", "").upper() if license_number and str(license_number).strip() else None

        # 1. Prvoradá autorita: konkrétny hardvérový terminál vozidla (vehicle_id)
        if s_vid:
            if s_vid in self.MANUAL_OVERRIDES:
                return self.MANUAL_OVERRIDES[s_vid]

            # 1b. Kontrola cez TRANSDATA_MAPPING (známe prepojenie hardware ID -> evidenčné číslo)
            if s_vid in self.TRANSDATA_MAPPING:
                mapped_ev = str(self.TRANSDATA_MAPPING[s_vid]).strip().replace("#", "")
                if mapped_ev in self.MANUAL_OVERRIDES:
                    return self.MANUAL_OVERRIDES[mapped_ev]

            # 1c. Kontrola TransData kandidátov (prebudenie z garáže: vozidlo v Ubiane posiela 7-miestne ID)
            if len(s_vid) == 7 and s_vid.isdigit():
                candidates = self._decode_transdata_candidates(s_vid)
                for cand in candidates:
                    clean_cand = str(cand).strip().replace("#", "")
                    if clean_cand in self.MANUAL_OVERRIDES:
                        ov = self.MANUAL_OVERRIDES[clean_cand]
                        self.TRANSDATA_MAPPING[s_vid] = clean_cand
                        self.MANUAL_OVERRIDES[s_vid] = ov
                        return ov

            # 1d. Posledné 4 číslice s_vid ako evidenčné číslo
            if len(s_vid) >= 4:
                suffix4 = s_vid[-4:]
                if suffix4 in self.MANUAL_OVERRIDES:
                    ov = self.MANUAL_OVERRIDES[suffix4]
                    self.TRANSDATA_MAPPING[s_vid] = suffix4
                    self.MANUAL_OVERRIDES[s_vid] = ov
                    return ov

        # 2. Druhotná autorita: konkrétne evidenčné číslo (napr. úprava v depe/garáži)
        if s_ev:
            if s_ev in self.MANUAL_OVERRIDES:
                ov = self.MANUAL_OVERRIDES[s_ev]
                if not isinstance(ov, dict) or str(ov.get("evidencne_cislo", "")).strip().replace("#", "") == s_ev:
                    return ov

            # Kontrola, či niektorý záznam v MANUAL_OVERRIDES nemá toto evidencne_cislo
            for k, ov in self.MANUAL_OVERRIDES.items():
                if isinstance(ov, dict) and str(ov.get("evidencne_cislo", "")).strip().replace("#", "") == s_ev:
                    return ov

        # 3. Kontrola podľa ŠPZ (ak vozidlo v premávke vysiela ŠPZ, pre ktorú existuje uložený override)
        if clean_lic:
            for k, ov in self.MANUAL_OVERRIDES.items():
                if isinstance(ov, dict):
                    ov_spz = ov.get("spz")
                    if ov_spz and ov_spz.replace("-", "").replace(" ", "").upper() == clean_lic:
                        return ov

        # 4. Ak bolo zadané krátke vehicle_id (3-4 cifry), môže ísť priamo o evidenčné číslo
        if s_vid and len(s_vid) <= 4:
            for k, ov in self.MANUAL_OVERRIDES.items():
                if isinstance(ov, dict) and str(ov.get("evidencne_cislo", "")).strip().replace("#", "") == s_vid:
                    return ov

        return None

    def is_vehicle_verified(
        self,
        vehicle_id: Any = None,
        ev_cislo: Any = None,
        license_number: Optional[str] = None
    ) -> bool:
        """
        Zistí, či je vozidlo overené (nachádza sa v MANUAL_OVERRIDES resp. má verified: true).
        Ostatné vozidlá majú is_verified = False.
        """
        ov = self.get_override(vehicle_id=vehicle_id, ev_cislo=ev_cislo, license_number=license_number)
        if not ov:
            return False
        if "verified" in ov:
            return bool(ov["verified"])
        return True

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
        is_ver = self.is_vehicle_verified(ev_cislo=clean_ev)
        if override:
            res = dict(item) if item else {"evidencne_cislo": clean_ev}
            res.update(override)
            res["is_verified"] = is_ver
            res["verified"] = is_ver
            return res
        if only_active and item:
            if not self.is_active_model(item.get("model")):
                return None
        if item:
            res = dict(item)
            res["is_verified"] = is_ver
            res["verified"] = is_ver
            return res
        return None

    def get_by_spz(self, spz: str, only_active: bool = False) -> Optional[Dict[str, Any]]:
        clean = spz.replace(" ", "").replace("-", "").upper()
        item = self.spz_index.get(clean)

        # Ak sa ŠPZ nenachádza v lokálnom CSV indexe, skúsime online vyhľadanie cez evidencia-dopravcov.eu
        if not item:
            try:
                from app.services.evidencia_scraper import evidencia_scraper
                scraped = evidencia_scraper.lookup_by_spz(clean)
                if scraped:
                    ev_num = scraped.get("evidencne_cislo")
                    model = scraped.get("model") or "Autobus DPMK"
                    item = {
                        "evidencne_cislo": ev_num,
                        "spz": spz,
                        "model": model,
                        "rok_vyroby": scraped.get("rok_vyroby"),
                        "vin": scraped.get("vin")
                    }
                    if clean:
                        self.spz_index[clean] = item
                    if ev_num:
                        self.ev_index[ev_num] = item
            except Exception:
                pass

        if item:
            override = self.get_override(ev_cislo=item.get("evidencne_cislo"))
            is_ver = self.is_vehicle_verified(ev_cislo=item.get("evidencne_cislo"))
            if override:
                res = dict(item)
                res.update(override)
                res["is_verified"] = is_ver
                res["verified"] = is_ver
                return res
            if only_active and not self.is_active_model(item.get("model")):
                return None
            res = dict(item)
            res["is_verified"] = is_ver
            res["verified"] = is_ver
            return res
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
        1. MANUAL_OVERRIDES má absolútne najvyššiu prioritu a bezpodmienečne prepisuje raw Ubian telemetriu.
        2. Izoláciu električiek (žiadne miešanie s autobusmi, SPZ = None).
        3. Autoritu offline CSV pre aktívny vozový park.
        4. Mutuje objekt raw_vehicle in-place, takže opravená identita prežije offline/online cykly.
        """
        # Podpora odovzdania celého slovníka ako prvý argument
        if isinstance(vehicle_id, dict):
            if not raw_vehicle:
                raw_vehicle = vehicle_id
            line = line or vehicle_id.get("line")
            line_type = line_type or vehicle_id.get("line_type")
            license_number = license_number or vehicle_id.get("license_number")
            vehicle_id = vehicle_id.get("vehicle_id")

        s_vid = str(vehicle_id).strip().replace("#", "") if vehicle_id is not None and str(vehicle_id).strip() else ""
        raw_ev = ""
        if isinstance(raw_vehicle, dict):
            raw_ev = str(
                raw_vehicle.get("evidencne_cislo")
                or raw_vehicle.get("vehicleNumber")
                or (raw_vehicle.get("fleet_info", {}).get("evidencne_cislo") if isinstance(raw_vehicle.get("fleet_info"), dict) else None)
                or ""
            ).strip().replace("#", "")

        is_tram_veh = self.is_tram(
            vehicle_id=s_vid,
            line=line,
            line_type=line_type,
            ez_vehicle_type=ez_vehicle_type,
            raw_vehicle=raw_vehicle
        )

        # =====================================================================
        # 0. NAJVYŠŠIA AUTORITA: Ak máme manuálny override pre toto vozidlo
        #    (podľa vehicle_id alebo evidencne_cislo priamo v MANUAL_OVERRIDES),
        #    okamžite aplikujeme tieto overené hodnoty (model, ŠPZ, ev. číslo,
        #    is_verified: true) a zablokujeme akýkoľvek ďalší fallback na Ubian alebo CSV!
        # =====================================================================
        override = None
        if s_vid and s_vid in self.MANUAL_OVERRIDES:
            override = self.MANUAL_OVERRIDES[s_vid]
        elif raw_ev and raw_ev in self.MANUAL_OVERRIDES:
            override = self.MANUAL_OVERRIDES[raw_ev]
        else:
            override = self.get_override(vehicle_id=s_vid, ev_cislo=raw_ev, license_number=license_number)

        if override:
            final_ev = str(override.get("evidencne_cislo") or raw_ev or s_vid).strip().replace("#", "")
            final_model = override.get("model") or ("Električka DPMK" if is_tram_veh else "Autobus DPMK")
            final_spz = None if is_tram_veh else override.get("spz")
            final_rok = override.get("rok_vyroby")
            final_vin = override.get("vin")

            # Uistíme sa, že TRANSDATA_MAPPING a MANUAL_OVERRIDES sú obojsmerne prepojené
            if s_vid and s_vid not in self.MANUAL_OVERRIDES:
                self.MANUAL_OVERRIDES[s_vid] = override
            if s_vid and final_ev:
                self.TRANSDATA_MAPPING[s_vid] = final_ev

            res = {
                "evidencne_cislo": final_ev,
                "spz": final_spz,
                "model": final_model,
                "rok_vyroby": final_rok,
                "vin": final_vin,
                "is_verified": True,
                "verified": True,
            }

            # In-place bezpodmienečný prepis surových Ubian dát priamo v telemetrickom objekte
            if raw_vehicle and isinstance(raw_vehicle, dict):
                raw_vehicle["model"] = final_model
                raw_vehicle["evidencne_cislo"] = final_ev
                if is_tram_veh:
                    raw_vehicle["license_number"] = None
                else:
                    raw_vehicle["license_number"] = final_spz
                raw_vehicle["is_verified"] = True
                raw_vehicle["verified"] = True
                if final_vin:
                    raw_vehicle["vehicle_vin"] = final_vin
                raw_vehicle["fleet_info"] = {
                    "spz": final_spz,
                    "evidencne_cislo": final_ev,
                    "model": final_model,
                    "rok_vyroby": final_rok,
                    "vin": final_vin,
                    "low_floor": raw_vehicle.get("low_floor", True),
                    "air_conditioning": True,
                    "wifi": raw_vehicle.get("wifi", False),
                    "is_verified": True,
                    "verified": True,
                }

            # ZABLOKOVANÝ akýkoľvek ďalší fallback na Ubian alebo CSV:
            return res

        # =====================================================================
        # 1. IZOLÁCIA ELEKTRIČIEK: Kontrola trakcie
        # =====================================================================
        if is_tram_veh:
            raw = raw_vehicle if isinstance(raw_vehicle, dict) else {}

            raw_ev = raw.get("evidencne_cislo") or raw.get("vehicleNumber")
            # Ubian v dispečerskom get_real posiela číslo električky v poli license_number (napr. "824")
            clean_lic = str(license_number or raw.get("license_number") or "").strip().replace("#", "")
            if not raw_ev and clean_lic.isdigit():
                raw_ev = clean_lic

            if raw_ev and str(raw_ev).strip():
                tram_ev = str(raw_ev).strip().replace("#", "")
            else:
                tram_ev = s_vid if s_vid else None

            # Hľadanie modelu električky v našom vozovom parku (Vario LF2+, Tatra KT8D5.RN2, Tatra T6A5)
            fleet_item = self.ev_index.get(str(tram_ev).strip()) if tram_ev else None

            raw_model = (
                raw.get("vehicleName")
                or raw.get("model")
                or raw.get("vehicleType")
                or raw.get("vehicleTypeName")
                or kwargs.get("model")
            )

            if fleet_item and fleet_item.get("model"):
                tram_model = fleet_item["model"]
            elif raw_model and str(raw_model).strip() and str(raw_model).strip().upper() != "TRAM":
                tram_model = str(raw_model).strip()
            else:
                tram_model = "Električka DPMK"

            tram_vin = raw.get("vehicle_vin") or raw.get("vehicleIdentificationNumber") or (s_vid if s_vid else None)

            tram_res = {
                "evidencne_cislo": str(tram_ev) if tram_ev else None,
                "spz": None,
                "model": tram_model,
                "rok_vyroby": fleet_item.get("rok_vyroby") if fleet_item else None,
                "vin": str(tram_vin) if tram_vin else None
            }
            ov = self.get_override(vehicle_id=s_vid, ev_cislo=tram_ev)
            if ov:
                tram_res.update(ov)
                if not ov.get("spz"):
                    tram_res["spz"] = None
            is_ver = self.is_vehicle_verified(vehicle_id=s_vid, ev_cislo=tram_res.get("evidencne_cislo") or tram_ev)
            tram_res["is_verified"] = is_ver
            tram_res["verified"] = is_ver

            if raw_vehicle and isinstance(raw_vehicle, dict):
                raw_vehicle["model"] = tram_res["model"]
                raw_vehicle["evidencne_cislo"] = tram_res["evidencne_cislo"]
                raw_vehicle["license_number"] = None
                raw_vehicle["is_verified"] = is_ver
                raw_vehicle["verified"] = is_ver

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
            candidates = self._decode_transdata_candidates(s_vid)
            for cand in candidates:
                cand_match = self.get_by_ev_cislo(cand, only_active=True)
                if cand_match:
                    match = cand_match
                    break

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
                match = {
                    "evidencne_cislo": suffix,
                    "spz": None,
                    "model": "Autobus DPMK",
                    "rok_vyroby": None,
                    "vin": None
                }

        # NAJVYŠŠIA AUTORITA PRAVDY: Kontrola MANUAL_OVERRIDES tesne pred vrátením dát
        matched_ev = match.get("evidencne_cislo") if match else (s_vid[-4:] if len(s_vid) >= 4 else None)
        override = self.get_override(vehicle_id=s_vid, ev_cislo=matched_ev, license_number=license_number)
        is_ver = self.is_vehicle_verified(vehicle_id=s_vid, ev_cislo=matched_ev, license_number=license_number)
        if override:
            res = dict(match) if match else {
                "evidencne_cislo": override.get("evidencne_cislo", s_vid),
                "spz": override.get("spz"),
                "model": override.get("model"),
                "rok_vyroby": override.get("rok_vyroby"),
                "vin": override.get("vin"),
            }
            res.update(override)
            res["is_verified"] = is_ver
            res["verified"] = is_ver
        elif match:
            res = dict(match)
            res["is_verified"] = is_ver
            res["verified"] = is_ver
        else:
            res = {
                "evidencne_cislo": s_vid,
                "spz": license_number,
                "model": "Autobus DPMK",
                "is_verified": False,
                "verified": False
            }

        # In-place prepis surových Ubian dát
        if raw_vehicle and isinstance(raw_vehicle, dict):
            if res.get("model"):
                raw_vehicle["model"] = res["model"]
            if res.get("evidencne_cislo"):
                raw_vehicle["evidencne_cislo"] = res["evidencne_cislo"]
            if is_tram_veh:
                raw_vehicle["license_number"] = None
            elif res.get("spz"):
                raw_vehicle["license_number"] = res["spz"]
            raw_vehicle["is_verified"] = res.get("is_verified", False)
            raw_vehicle["verified"] = res.get("verified", False)

        return res

    def apply_override_to_live_vehicle(self, v: Dict[str, Any]) -> Dict[str, Any]:
        """
        Bezpodmienečne aplikuje MANUAL_OVERRIDES na prichádzajúci objekt live vozidla
        z telemetrie ešte pred jeho uložením do LAST_SEEN_CACHE alebo odoslaním na frontend.
        Mutuje objekt in-place a vracia ho.
        """
        if not v or not isinstance(v, dict):
            return v
        self.match_live_vehicle(v)
        return v

    def sync_override_to_caches(
        self,
        override: Dict[str, Any],
        live_cache: Optional[List[Dict[str, Any]]] = None,
        last_seen_cache: Optional[List[Dict[str, Any]]] = None
    ):
        """
        Okamžite premietne zmenu override do in-memory live vyrovnávacích pamätí (live_cache a LAST_SEEN_CACHE),
        takže používateľ na mape a frontend vidí zmenu ihneď bez čakania na ďalší interval.
        """
        if not override or not isinstance(override, dict):
            return

        target_ev = str(override.get("evidencne_cislo") or "").strip().replace("#", "")
        target_vid = str(override.get("vehicle_id") or "").strip().replace("#", "")
        target_model = override.get("model")
        target_spz = override.get("spz")
        target_verified = bool(override.get("verified", True))

        def _matches_override(cand_vid: str, cand_ev: str) -> bool:
            if target_vid and cand_vid == target_vid:
                return True
            if target_ev:
                if cand_ev == target_ev or cand_vid == target_ev:
                    return True
                if cand_vid in self.TRANSDATA_MAPPING and self.TRANSDATA_MAPPING[cand_vid] == target_ev:
                    return True
                if len(cand_vid) == 7 and cand_vid.isdigit() and target_ev in self._decode_transdata_candidates(cand_vid):
                    return True
                if len(cand_vid) >= 4 and cand_vid[-4:] == target_ev:
                    return True
            return False

        # 1. Synchronizácia live_cache v live_feed
        if live_cache and isinstance(live_cache, list):
            for veh in live_cache:
                if not isinstance(veh, dict):
                    continue
                v_ev = str(veh.get("evidencne_cislo") or "").strip().replace("#", "")
                v_vid = str(veh.get("vehicle_id") or "").strip().replace("#", "")
                if _matches_override(v_vid, v_ev):
                    if target_model:
                        veh["model"] = target_model
                    if target_ev:
                        veh["evidencne_cislo"] = target_ev
                    is_tram_veh = self.is_tram(vehicle_id=v_vid, line=veh.get("line"), line_type=veh.get("line_type"), raw_vehicle=veh)
                    if is_tram_veh:
                        veh["license_number"] = None
                    elif target_spz:
                        veh["license_number"] = target_spz
                    veh["is_verified"] = target_verified
                    veh["verified"] = target_verified

        # 2. Synchronizácia LAST_SEEN_CACHE
        if last_seen_cache and isinstance(last_seen_cache, list):
            for item in last_seen_cache:
                if not isinstance(item, dict):
                    continue
                fi = item.get("fleet_info") or {}
                i_ev = str(fi.get("evidencne_cislo") or item.get("evidencne_cislo") or "").strip().replace("#", "")
                i_vid = str(item.get("vehicle_id") or "").strip().replace("#", "")
                if _matches_override(i_vid, i_ev):
                    if target_model:
                        item["model"] = target_model
                        fi["model"] = target_model
                    if target_ev:
                        item["evidencne_cislo"] = target_ev
                        fi["evidencne_cislo"] = target_ev
                    is_tram_veh = self.is_tram(vehicle_id=i_vid, line=item.get("line"), line_type=item.get("line_type"), raw_vehicle=item)
                    if is_tram_veh:
                        item["license_number"] = None
                        fi["spz"] = None
                    elif target_spz:
                        item["license_number"] = target_spz
                        fi["spz"] = target_spz
                    item["is_verified"] = target_verified
                    item["verified"] = target_verified
                    fi["is_verified"] = target_verified
                    fi["verified"] = target_verified
                    item["fleet_info"] = fi

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
            is_ver = self.is_vehicle_verified(ev_cislo=ev)
            v["is_verified"] = is_ver
            v["verified"] = is_ver
            vehicles.append(v)

        def sort_key(x):
            ev_str = str(x.get("evidencne_cislo", ""))
            try:
                return (0, int(ev_str))
            except ValueError:
                return (1, ev_str)

        vehicles.sort(key=sort_key)
        return vehicles
