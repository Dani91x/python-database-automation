"""
poisson_calibrator.py — modulo CONDIVISO di calibrazione Poisson (DB-first).

Centralizza in un solo punto la logica che oggi vive duplicata in money_management
(_apply_calibration) + il file dynamic_cal.json. Sorgente dei fattori, in ordine:
  1. tabella DB  public.poisson_calibration   (gemella di ml_post_calibration)
  2. fallback    dynamic_cal.json              (file git, finche' la tabella non e' popolata)

Espone:
  PoissonCalibrator(source="auto"|"db"|"json")
    .calibrate_markets(markets_raw, league_id) -> markets_calibrated
        Per ogni mercato applica per-classe il fattore (bin della prob grezza,
        lega -> globale -> 1.0) e RINORMALIZZA la distribuzione a somma 1, come fa
        l'ML in post-calibration. Preserva eventuali sotto-chiavi (es. "details").

I 'cal_key' codificano mercato+lato e sono identici a update_poisson_calibration.py /
generate_dynamic_cal.py, cosi' i fattori prodotti dall'action settimanale sono riusati 1:1.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Dict, Optional

# Import del client DB a livello di modulo (pattern del progetto). Guardato: in ambienti
# senza db_client/credenziali il modulo resta usabile in modalita' "json".
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from db_client import get_supabase_client as _get_supabase_client
except Exception:  # pragma: no cover
    _get_supabase_client = None

# cal_key -> (json_market in db_json_analisi.markets, json_class)
# IDENTICA a MARKET_CONFIG di update_poisson_calibration.py
MARKET_CONFIG = {
    "H":       ("1x2", "H"),
    "D":       ("1x2", "D"),
    "A":       ("1x2", "A"),
    "O15":     ("over_1_5", "True"),
    "U15":     ("over_1_5", "False"),
    "O25":     ("over_2_5", "True"),
    "U25":     ("over_2_5", "False"),
    "O35":     ("over_3_5", "True"),
    "U35":     ("over_3_5", "False"),
    "BTTS":    ("btts", "True"),
    "BTTS_NO": ("btts", "False"),
    "HT05":    ("first_half_over_0_5", "True"),
    "HT_U05":  ("first_half_over_0_5", "False"),
    "HT_H":    ("ht_1x2", "H"),
    "HT_D":    ("ht_1x2", "D"),
    "HT_A":    ("ht_1x2", "A"),
}

# reverse: json_market -> {json_class -> cal_key}
_MARKET_TO_KEYS: Dict[str, Dict[str, str]] = {}
for _ck, (_mk, _cls) in MARKET_CONFIG.items():
    _MARKET_TO_KEYS.setdefault(_mk, {})[_cls] = _ck

_DYNAMIC_CAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dynamic_cal.json")


def _bin_idx(prob: float) -> int:
    return min(int(float(prob) * 10), 9)


def _lookup_cf(corr: dict, cal_key: str, bin_idx: int) -> Optional[float]:
    """Cerca il correction factor in una tabella {cal_key: {bin: cf}}.
    Le chiavi-bin possono essere int o str (DB JSONB le serializza come stringhe)."""
    mkt = (corr or {}).get(cal_key)
    if not isinstance(mkt, dict):
        return None
    cf = mkt.get(bin_idx, mkt.get(str(bin_idx)))
    try:
        return float(cf) if cf is not None else None
    except (TypeError, ValueError):
        return None


class PoissonCalibrator:
    """Carica i fattori una volta e calibra in memoria. league_id come str nelle tabelle."""

    def __init__(self, source: str = "auto"):
        self._by_league: Dict[str, dict] = {}
        self._global: dict = {}
        self.source: str = "none"
        if source in ("auto", "db"):
            if self._load_from_db():
                self.source = "db"
        if self.source == "none" and source in ("auto", "json"):
            if self._load_from_json():
                self.source = "json"

    # ------------------------------------------------------------------ loaders
    def _load_from_db(self) -> bool:
        if _get_supabase_client is None:
            return False
        try:
            sb = _get_supabase_client()
            rows = sb.table("poisson_calibration").select(
                "league_id,corrections").execute().data or []
            if not rows:
                return False
            for r in rows:
                lid = str(r.get("league_id"))
                corr = r.get("corrections") or {}
                if lid == "0":
                    self._global = corr
                else:
                    self._by_league[lid] = corr
            return bool(self._global or self._by_league)
        except Exception as e:
            # Non fatale: scivola sul fallback json. Ma logga il perche' (diagnostica),
            # cosi' un DB irraggiungibile non resta invisibile.
            print(f"  [WARN] poisson_calibration DB non leggibile "
                  f"({type(e).__name__}: {e}) -> fallback dynamic_cal.json", file=sys.stderr)
            return False

    def _load_from_json(self) -> bool:
        try:
            with open(_DYNAMIC_CAL_PATH, encoding="utf-8") as f:
                d = json.load(f)
            self._global = d.get("global", {}) or {}
            self._by_league = d.get("by_league", {}) or {}
            return bool(self._global or self._by_league)
        except Exception:
            return False

    # ------------------------------------------------------------------ core
    def _cf(self, cal_key: str, bin_idx: int, league_id) -> float:
        """Chain: lega -> globale -> 1.0.

        money_management._apply_calibration ha un 3o livello (CALIBRATION_TABLE statica
        dentro il modulo Betfair). Qui e' OMESSO DI PROPOSITO: la riga globale del DB
        (league_id=0) e' il fallback centralizzato che sostituisce quella tabella (stessa
        derivazione dallo storico). 1.0 = nessuna correzione, usato solo per i bin che
        NEMMENO il globale copre (campioni insufficienti) — degradazione onesta, non un bug.
        """
        lid = str(league_id) if league_id is not None else None
        if lid is not None:
            cf = _lookup_cf(self._by_league.get(lid, {}), cal_key, bin_idx)
            if cf is not None:
                return cf
        cf = _lookup_cf(self._global, cal_key, bin_idx)
        return cf if cf is not None else 1.0

    def calibrate_market(self, market_key: str, classes: dict, league_id) -> dict:
        """Calibra un singolo mercato {classe: prob} -> {classe: prob_calibrata} (somma 1).
        Preserva le chiavi non-classe (es. 'details') invariate.

        SCELTA DI DESIGN — RENORMALIZZAZIONE (deliberata): applico cf per-classe e poi
        rinormalizzo a somma 1, ESATTAMENTE come fa l'ML in post-calibration (multi-classe:
        corregge ogni classe e rinormalizza). E' il comportamento giusto qui perche'
        l'obiettivo del progetto e' rendere Poisson COERENTE con l'ML nel DB e mostrare
        una distribuzione valida in dashboard.
        NB: money_management._apply_calibration NON rinormalizza (corregge una singola prob
        per volta per il calcolo dell'edge di una singola scommessa — consumer diverso). Quindi
        sui mercati ternari (1x2, ht_1x2) i valori calibrati qui possono differire da quelli
        usati dall'edge nei Sheets: e' atteso, sono due consumer con semantiche diverse."""
        keymap = _MARKET_TO_KEYS.get(market_key)
        if not keymap:
            return dict(classes)  # mercato non calibrabile: copia identica

        corrected: Dict[str, float] = {}
        passthrough: Dict[str, object] = {}
        for cls, val in classes.items():
            cal_key = keymap.get(str(cls))
            if cal_key is None or not isinstance(val, (int, float)):
                passthrough[cls] = val  # es. "details" o classe ignota
                continue
            cf = self._cf(cal_key, _bin_idx(val), league_id)
            corrected[cls] = float(val) * cf

        total = sum(corrected.values())
        if total > 0:
            corrected = {k: v / total for k, v in corrected.items()}
        else:
            # degenere (impossibile coi cf cappati [0.2,3.0], ma difensivo): torna al grezzo
            corrected = {k: float(classes[k]) for k in corrected}

        corrected.update(passthrough)
        return corrected

    def calibrate_markets(self, markets_raw: dict, league_id) -> dict:
        """Calibra l'intero blocco markets di db_json_analisi -> markets_calibrated."""
        out: Dict[str, dict] = {}
        for market_key, classes in (markets_raw or {}).items():
            if isinstance(classes, dict):
                out[market_key] = self.calibrate_market(market_key, classes, league_id)
            else:
                out[market_key] = classes
        return out


# self-test rapido: confronta grezzo vs calibrato su un fixture reale
if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    cal = PoissonCalibrator()
    print(f"Sorgente calibrazione: {cal.source}  "
          f"(leghe={len(cal._by_league)}, global_keys={len(cal._global)})")
    demo = {
        "1x2": {"H": 0.4707, "D": 0.3225, "A": 0.2068},
        "over_2_5": {"True": 0.339, "False": 0.661},
        "over_3_5": {"True": 0.1535, "False": 0.8465},
        "first_half_over_0_5": {"True": 0.6911, "False": 0.3089, "details": {"freq": 0.75}},
    }
    out = cal.calibrate_markets(demo, league_id=358)
    for mk in demo:
        print(f"\n{mk}")
        print("  grezzo   :", {k: round(v, 4) for k, v in demo[mk].items() if isinstance(v, (int, float))})
        print("  calibrato:", {k: round(v, 4) for k, v in out[mk].items() if isinstance(v, (int, float))})
