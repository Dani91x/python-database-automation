"""
betfair_match.py — abbinamento Betfair event <-> fixture DB (MONEY-CRITICAL).

PERCHE' ESISTE
--------------
betfair_full_odds.py agganciava gli eventi Betfair alle fixture con una semplice
intersezione di token (norm() a frozenset): matching DEBOLE che produceva FALSI
POSITIVI. Caso reale (run 2026-06-25): quattro partite kuwaitiane diverse
("Al Fahaheel", "Al Nasar", "Al Tadhamon", "Al Salmiyah") finivano tutte sulla
STESSA fixture 1553794 — perche' condividevano il token "al" — e, con il
delete+insert per fixture_id, si sovrascrivevano a vicenda. Quote sbagliate =
gli utenti perdono soldi.

COSA GARANTISCE
---------------
1) NORMALIZZAZIONE IDENTICA a betfair_report_manager.normalize_name (stesso set
   di stopword + traduzioni) -> full_odds affidabile quanto il foglio
   "Match Events".
2) FUZZY thefuzz.token_set_ratio, soglia 70 per lato (diretto + invertito),
   identica al report. Accettazione "debole" (score medio >= 65) ammessa SOLO se
   gli orari di inizio coincidono (anti falso-positivo).
3) GATE TEMPORALE: openDate Betfair vs kickoff fixture; esclude abbinamenti
   grossolanamente fuori orario/giorno.
4) ASSEGNAZIONE 1:1 GLOBALE (greedy per forza/score/Δt): ogni fixture_id va ad
   UN SOLO evento. Niente collisioni, niente sovrascritture.

NOTA MANUTENZIONE: normalize_name e' una COPIA FEDELE di
betfair_report_manager.normalize_name. Se quella cambia, aggiornare anche qui.
"""
from __future__ import annotations

import json
import os
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from thefuzz import fuzz

MAPPING_FILE = os.path.join(os.path.dirname(__file__), "betfair_name_map.json")

MATCH_THRESHOLD = 70       # soglia "forte" per singolo lato (identica al report)
WEAK_ACCEPT = 65           # score medio minimo per accettazione "debole"
TIME_TOLERANCE_MIN = 360   # gate temporale difensivo (6h): esclude errori grossolani
WEAK_TIME_MIN = 90         # per i match "deboli" gli orari devono ~coincidere

# --- COPIA FEDELE di BetfairReportManager.normalize_name (tenere allineata) ---
_TO_REMOVE = {
    "fc", "united", "as", "ac", "sc", "cf", "u23", "u20", "u19",
    "women", "real", "atletico", "de", "sporting", "st", "saint",
    "rn", "mt", "mg", "pr", "sp", "rj", "rs", "go", "ba", "pa", "ce", "pe",
    "sports", "club", "ec", "se", "afc", "utd",
}
_TRANSLATIONS = {
    "lp": "la plata", "gimnasia": "gimnasia", "petersburg": "petrograd",
    "vd": "virgin islands", "vi": "virgin islands",
}


def load_name_map() -> Dict[str, str]:
    """Carica gli alias Betfair->DB (betfair_name_map.json). {} se assente/rotto."""
    if os.path.exists(MAPPING_FILE):
        try:
            with open(MAPPING_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def normalize_name(name: Optional[str]) -> str:
    """Normalizza un nome squadra: rimuove accenti/punteggiatura/stopword e
    ORDINA i token (gestisce inversioni). Identica al report."""
    if not name:
        return ""
    name = "".join(
        c for c in unicodedata.normalize("NFD", name)
        if unicodedata.category(c) != "Mn"
    )
    n = name.lower().replace("-", " ").replace(".", "").replace("&", " and ")
    words: List[str] = []
    for w in n.split():
        w = "".join(c for c in w if c.isalnum())
        if not w:
            continue
        w = _TRANSLATIONS.get(w, w)
        if w not in _TO_REMOVE:
            words.append(w)
    return " ".join(sorted(words))


def split_event_name(name: Optional[str]) -> Optional[Tuple[str, str]]:
    """'Home v Away' -> ('Home', 'Away'); None se il formato non e' valido."""
    if not name or " v " not in name:
        return None
    h, a = name.split(" v ", 1)
    h, a = h.strip(), a.strip()
    if not h or not a:
        return None
    return h, a


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    """Parsa un timestamp ISO (con 'Z' o offset) in datetime UTC. None se invalido."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, AttributeError):
        return None


def _score(n_bf_home: str, n_bf_away: str, n_db_home: str, n_db_away: str) -> Tuple[float, bool]:
    """Ritorna (score_migliore, strong_ok).
    strong_ok = entrambi i lati >= MATCH_THRESHOLD (diretto OPPURE invertito)."""
    shd = fuzz.token_set_ratio(n_bf_home, n_db_home)
    sad = fuzz.token_set_ratio(n_bf_away, n_db_away)
    avg_d = (shd + sad) / 2.0
    shi = fuzz.token_set_ratio(n_bf_home, n_db_away)
    sai = fuzz.token_set_ratio(n_bf_away, n_db_home)
    avg_i = (shi + sai) / 2.0
    strong = (shd >= MATCH_THRESHOLD and sad >= MATCH_THRESHOLD) or \
             (shi >= MATCH_THRESHOLD and sai >= MATCH_THRESHOLD)
    return max(avg_d, avg_i), strong


def resolve_matches(
    events: List[Dict[str, Any]],
    fixtures: List[Dict[str, Any]],
    name_map: Optional[Dict[str, str]] = None,
    time_tolerance_min: int = TIME_TOLERANCE_MIN,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Abbina eventi Betfair a fixture DB con assegnazione 1:1.

    events:   [{"id","name"="Home v Away","openDate"(opz)}]
    fixtures: [{"fixture_id","home_team_name","away_team_name","fixture_date"(opz), ...}]

    Ritorna (matched, unmatched):
      matched   = [{"event","fixture","score","strong","dt_min"}]
      unmatched = [{"event","reason","best_score"}]

    GARANZIA: ogni fixture_id compare in AL PIU' una coppia (used_fx); ogni evento
    in AL PIU' una coppia (used_ev). Priorita' greedy: prima i match "forti", poi
    score piu' alto, poi Δt minore.
    """
    name_map = name_map or {}

    # 1) Dedup fixture per fixture_id + pre-normalizzazione
    seen_fx: set = set()
    norm_fx: List[Dict[str, Any]] = []
    for f in fixtures:
        fid = f.get("fixture_id")
        if fid is None or fid in seen_fx:
            continue
        dh = f.get("home_team_name") or ""
        da = f.get("away_team_name") or ""
        if not dh or not da:
            continue
        seen_fx.add(fid)
        norm_fx.append({
            "f": f,
            "nh": normalize_name(dh),
            "na": normalize_name(da),
            "dt": _parse_dt(f.get("fixture_date")),
        })

    # 2) Genera tutti i candidati validi (evento x fixture)
    candidates: List[Tuple[float, bool, float, int, int]] = []  # (score, strong, dt_key, ei, fi)
    best_per_event: Dict[int, float] = {}
    # eventi che avevano un near-match (score>=WEAK_ACCEPT) ma scartato per orario:
    # serve a NON nascondere drop "silenziosi" nel log degli unmatched.
    weak_time_blocked: Dict[int, float] = {}
    for ei, ev in enumerate(events):
        parts = split_event_name(ev.get("name", ""))
        if not parts:
            continue
        bf_home, bf_away = parts
        bf_home = name_map.get(bf_home, bf_home)
        bf_away = name_map.get(bf_away, bf_away)
        nbh, nba = normalize_name(bf_home), normalize_name(bf_away)
        ev_dt = _parse_dt(ev.get("openDate"))

        for fi, nf in enumerate(norm_fx):
            dt_min: Optional[float] = None
            if ev_dt is not None and nf["dt"] is not None:
                dt_min = abs((ev_dt - nf["dt"]).total_seconds()) / 60.0
                # gate temporale duro: fuori finestra -> nemmeno candidato
                if dt_min > time_tolerance_min:
                    continue

            score, strong = _score(nbh, nba, nf["nh"], nf["na"])
            best_per_event[ei] = max(best_per_event.get(ei, 0.0), score)

            # accettazione: forte sempre; debole solo se gli orari ~coincidono
            # (money-safe: un match 65-69 senza conferma oraria e' troppo rischioso).
            weak_ok = (
                score >= WEAK_ACCEPT
                and dt_min is not None
                and dt_min <= WEAK_TIME_MIN
            )
            if strong or weak_ok:
                # dt_key: Δt noto (ordina i pari-score per orario piu' vicino);
                # 1e9 => orario ignoto, deprioritizzato (sorta in coda nel tier).
                dt_key = dt_min if dt_min is not None else 1e9
                candidates.append((score, strong, dt_key, ei, fi))
            elif score >= WEAK_ACCEPT and not strong:
                # near-match scartato SOLO per il gate orario: registralo per il log.
                weak_time_blocked[ei] = max(weak_time_blocked.get(ei, 0.0), score)

    # 3) Assegnazione greedy 1:1 (strong first, poi score desc, poi Δt asc)
    candidates.sort(key=lambda c: (0 if c[1] else 1, -c[0], c[2]))
    used_ev: set = set()
    used_fx: set = set()
    matched: List[Dict[str, Any]] = []
    for score, strong, dt_key, ei, fi in candidates:
        if ei in used_ev or fi in used_fx:
            continue
        used_ev.add(ei)
        used_fx.add(fi)
        matched.append({
            "event": events[ei],
            "fixture": norm_fx[fi]["f"],
            "score": round(score, 1),
            "strong": strong,
            "dt_min": None if dt_key >= 1e9 else round(dt_key, 1),
        })

    # 4) Eventi non matchati (con motivo)
    unmatched: List[Dict[str, Any]] = []
    for ei, ev in enumerate(events):
        if ei in used_ev:
            continue
        if not split_event_name(ev.get("name", "")):
            unmatched.append({"event": ev, "reason": "nome non 'Home v Away'", "best_score": 0.0})
        else:
            best = best_per_event.get(ei, 0.0)
            if ei in weak_time_blocked:
                reason = (f"near-match score={weak_time_blocked[ei]:.0f} scartato: "
                          f"orario non confrontabile/oltre {WEAK_TIME_MIN}min")
            elif best >= WEAK_ACCEPT:
                reason = f"near-match score={best:.0f} ma fixture gia' assegnata (conteso 1:1)"
            else:
                reason = "nessuna fixture sopra soglia"
            unmatched.append({"event": ev, "reason": reason, "best_score": round(best, 1)})
    return matched, unmatched
