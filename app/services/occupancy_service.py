"""
MHD Košice - Správa obsadenosti vozidiel (Crowdsourcing / Waze pre MHD)
======================================================================
Uchováva v pamäti a synchronizuje nahlásenú úroveň zaplnenosti vozidiel.
Implementuje inteligentnú expiráciu:
- Expirácia po 5 minútach (300 sekúnd)
- Expirácia pri príchode na novú zastávku (zmena current_stop_name)
"""

import os
import json
import time
from datetime import datetime
from typing import Optional, Dict, Any, Union

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OCCUPANCY_CACHE_FILE = os.path.join(BASE_DIR, "data", "live_occupancy.json")

OCCUPANCY_LABELS = {
    1: "Prázdny",
    2: "Poloplný",
    3: "Plný"
}

OCCUPANCY_ICONS = {
    1: "🟢",
    2: "🟡",
    3: "🔴"
}

OCCUPANCY_COLORS = {
    1: "#10b981",  # emerald green
    2: "#f59e0b",  # amber yellow
    3: "#ef4444"   # rose red
}

EXPIRATION_SECONDS = 300  # 5 minút


class OccupancyService:
    def __init__(self, cache_file: str = OCCUPANCY_CACHE_FILE):
        self.cache_file = cache_file
        self._memory_store: Dict[str, Dict[str, Any]] = {}
        self._last_file_mtime = 0.0
        self._load_cache()

    def _normalize_stop(self, stop_name: Optional[str]) -> str:
        if not stop_name:
            return ""
        import unicodedata
        nfkd = unicodedata.normalize('NFKD', str(stop_name))
        cleaned = "".join(c for c in nfkd if not unicodedata.combining(c)).lower()
        return " ".join(cleaned.replace(',', ' ').replace('-', ' ').replace('.', ' ').split())

    def _load_cache(self):
        try:
            if os.path.exists(self.cache_file):
                mtime = os.path.getmtime(self.cache_file)
                if mtime > self._last_file_mtime:
                    with open(self.cache_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, dict):
                            self._memory_store.update(data)
                    self._last_file_mtime = mtime
        except Exception:
            pass

    def _save_cache(self):
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self._memory_store, f, ensure_ascii=False, indent=2)
            self._last_file_mtime = os.path.getmtime(self.cache_file)
        except Exception:
            pass

    def set_occupancy(
        self,
        vehicle_id: Union[int, str],
        level: int,
        current_stop_name: Optional[str] = None,
        line: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Zaznamená novú úroveň obsadenosti od cestujúceho:
        level: 1 = Prázdny, 2 = Poloplný, 3 = Plný
        """
        self._load_cache()
        vid = str(vehicle_id).strip()
        now_ts = time.time()
        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        record = {
            "vehicle_id": vid,
            "level": int(level),
            "label": OCCUPANCY_LABELS.get(int(level), "Neznáme"),
            "icon": OCCUPANCY_ICONS.get(int(level), "⚪"),
            "color": OCCUPANCY_COLORS.get(int(level), "#94a3b8"),
            "reported_at": now_ts,
            "reported_at_iso": now_iso,
            "stop_name": current_stop_name.strip() if current_stop_name else None,
            "line": str(line).strip() if line else None
        }

        self._memory_store[vid] = record
        self._save_cache()
        return record

    def get_occupancy(
        self,
        vehicle_id: Union[int, str],
        live_stop_name: Optional[str] = None,
        live_is_on_stop: Optional[bool] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Vráti aktívnu obsadenosť vozidla alebo None, ak vyexpirovala (čas > 5 min alebo príchod na novú zastávku).
        """
        self._load_cache()
        vid = str(vehicle_id).strip()
        record = self._memory_store.get(vid)
        if not record:
            return None

        now_ts = time.time()
        reported_at = record.get("reported_at", 0)
        age_seconds = now_ts - reported_at

        # 1. Pravidlo: expirácia po 5 minútach (300 s)
        if age_seconds > EXPIRATION_SECONDS:
            self._expire_record(vid)
            return None

        # 2. Pravidlo: príchod na novú zastávku (zmena current_stop_name a is_on_stop = true)
        rec_stop = record.get("stop_name")
        if rec_stop and live_stop_name:
            norm_rec = self._normalize_stop(rec_stop)
            norm_live = self._normalize_stop(live_stop_name)
            if norm_live and norm_rec and norm_live != norm_rec:
                # Ak dorazilo na novú zastávku
                if live_is_on_stop is None or bool(live_is_on_stop):
                    self._expire_record(vid)
                    return None
        elif not rec_stop and live_stop_name:
            # Ak v čase nahlásenia nebola známa zastávka, uložíme prvú zachytenú
            record["stop_name"] = live_stop_name.strip()
            self._save_cache()

        age_sec_int = max(0, int(age_seconds))
        if age_sec_int < 60:
            age_text = "pred chvíľou"
        else:
            mins = age_sec_int // 60
            if mins == 1:
                age_text = "pred 1 min"
            elif mins in (2, 3, 4):
                age_text = f"pred {mins} min"
            else:
                age_text = f"pred {mins} min"

        return {
            "level": record["level"],
            "label": record["label"],
            "icon": record["icon"],
            "color": record.get("color", "#94a3b8"),
            "stop_name": record.get("stop_name"),
            "line": record.get("line"),
            "reported_at": reported_at,
            "reported_at_iso": record.get("reported_at_iso"),
            "age_seconds": age_sec_int,
            "age_text": age_text
        }

    def _expire_record(self, vid: str):
        if vid in self._memory_store:
            del self._memory_store[vid]
            self._save_cache()

    def get_all_active(self) -> Dict[str, Dict[str, Any]]:
        self._load_cache()
        active = {}
        for vid in list(self._memory_store.keys()):
            occ = self.get_occupancy(vid)
            if occ:
                active[vid] = occ
        return active


occupancy_service = OccupancyService()
