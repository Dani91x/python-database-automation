"""omega_advisor — "CONSULENTE DATI" per le proposte lay Correct Score (MISSIONI).

Arricchisce le suggestion CS (HT/FT) con segnali PURAMENTE INFORMATIVI presi
dai NOSTRI dati; l'utente decide, il consulente non blocca mai nulla:

1. ``poisson_prob``  — probabilità del punteggio proposto secondo il motore
   Poisson interno (``fixture_predictions.db_json_analisi.inputs``: lambda_home/
   away, dc_rho, ht_ratio_*). La griglia è la STESSA matematica del motore
   (Prediction/today_predictions_backfill.py: griglia Poisson indipendente +
   correzione Dixon-Coles sulle 4 celle basse + rinormalizzazione), reimplementata
   in puro Python per non trascinare numpy/scipy nel servizio. Probabilità
   PRE-MATCH: non condizionata al punteggio live (dichiarato in sources).
2. ``freq_league``   — frequenza storica del punteggio nella lega via RPC
   ``get_market_frequency`` (exact_ft / exact_ht, ultime 300 settlate).
3. ``h2h``           — distribuzione dei punteggi negli scontri diretti dal
   blocco ``h2h_hint`` di ``data/hazard_atlas_v2.json`` (coppie con >=3 scontri).

MATCHING evento Betfair -> fixture: riusa il matcher MONEY-CRITICAL
``Betfair/betfair_match.resolve_matches`` (fuzzy + gate temporale). Se il
matching non è affidabile l'advisor resta ``None`` DICHIARATO: mai un match
forzato, mai numeri su una partita sbagliata.

INVARIANTI (money-critical):
- SOLO letture DB (fixture_predictions + RPC read-only); nessun ordine.
- L'advisor NON tocca mai market_id/selection_id/prezzi della suggestion.
- BEST-EFFORT con cache per evento: qualunque errore/mancanza dati -> None,
  la proposta esce comunque; budget di tempo ~1s per non rallentare il ciclo.
"""
from __future__ import annotations

import json
import logging
import math
import os
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from Betfair.omega import omega_engine as E

logger = logging.getLogger("omega.advisor")

# Budget di tempo (secondi) per il calcolo advisor di UNA suggestion: oltre,
# i campi rimanenti restano None (best-effort, mai rallentare il ciclo).
BUDGET_S = 1.0

# Finestra di ricerca fixture attorno al kickoff (il gate duro del matcher è
# comunque 360 min: qui si limita solo la query).
_FIXTURE_WINDOW_H = 12

_ATLAS_PATH = os.path.join(os.path.dirname(__file__), "data", "hazard_atlas_v2.json")

# ---------------------------------------------------------------------------
# CACHE (per-processo). Chiavi separate per stadio così i ricicli del loop
# missioni costano ~0 dopo il primo calcolo. reset_caches() per i test.
# ---------------------------------------------------------------------------
_MATCH_CACHE: dict[str, Optional[dict]] = {}          # event_id -> fixture "light" o None
_ANALYSIS_CACHE: dict[int, Optional[dict]] = {}       # fixture_id -> db_json_analisi
_FREQ_CACHE: dict[tuple, Optional[dict]] = {}         # (league, market, sel) -> freq
_ADVISOR_CACHE: dict[tuple, Optional[dict]] = {}      # (event, mtype, runner) -> advisor
_H2H_CACHE: Optional[dict] = None                     # h2h_hint dell'atlante (lazy)
_CACHE_MAX = 512


def reset_caches() -> None:
    """Svuota tutte le cache (test / riavvio logico)."""
    global _H2H_CACHE
    _MATCH_CACHE.clear()
    _ANALYSIS_CACHE.clear()
    _FREQ_CACHE.clear()
    _ADVISOR_CACHE.clear()
    _H2H_CACHE = None


def _bound(cache: dict) -> None:
    """Cintura anti-crescita: oltre _CACHE_MAX si riparte (uso raro, per-giornata)."""
    if len(cache) > _CACHE_MAX:
        cache.clear()


# ---------------------------------------------------------------------------
# 1) POISSON — stessa matematica del motore (copia fedele, puro Python)
# ---------------------------------------------------------------------------
def _poisson_pmf(lmbda: float, k: int) -> float:
    """PMF Poisson scalare. Contratto storico del motore: lambda<=0 -> 0.0."""
    if lmbda <= 0:
        return 0.0
    return math.exp(-lmbda) * lmbda ** k / math.factorial(k)


def _dc_tau(hg: int, ag: int, lh: float, la: float, rho: float) -> float:
    """Correzione Dixon-Coles sulle 4 celle basse — COPIA FEDELE di
    Prediction/today_predictions_backfill.py::_dc_tau (tenere allineata)."""
    if hg == 0 and ag == 0:
        return 1.0 - lh * la * rho
    if hg == 1 and ag == 0:
        return max(0.0, 1.0 + la * rho)
    if hg == 0 and ag == 1:
        return max(0.0, 1.0 + lh * rho)
    if hg == 1 and ag == 1:
        return 1.0 - rho
    return 1.0


def score_grid_prob(lh: float, la: float, rho: float,
                    hg: int, ag: int, max_goals: int) -> Optional[float]:
    """P(punteggio esatto hg-ag) dalla griglia Poisson+DC rinormalizzata.

    Identica al motore: griglia troncata a ``max_goals`` (FT=10, HT=4), tau
    sulle celle (0,0)(1,0)(0,1)(1,1), rinormalizzazione sul totale griglia."""
    if hg < 0 or ag < 0 or hg > max_goals or ag > max_goals:
        return None
    if lh <= 0 or la <= 0:
        return None
    total = 0.0
    target = 0.0
    for h in range(max_goals + 1):
        ph = _poisson_pmf(lh, h)
        for a in range(max_goals + 1):
            p = ph * _poisson_pmf(la, a)
            if h <= 1 and a <= 1:
                p *= _dc_tau(h, a, lh, la, rho)
            total += p
            if h == hg and a == ag:
                target = p
    if total <= 0:
        return None
    return target / total


def poisson_score_prob(inputs: dict, hg: int, ag: int, *, half: bool) -> Optional[float]:
    """Probabilità del punteggio proposto dagli input del motore Poisson.

    ``half=True`` -> griglia PRIMO TEMPO: lambda_ht = lambda * ht_ratio (stessa
    costruzione del motore, max_goals=4). ``half=False`` -> FT, max_goals=10."""
    try:
        lh = float(inputs["lambda_home"])
        la = float(inputs["lambda_away"])
        rho = float(inputs.get("dc_rho", -0.13))
        if half:
            lh *= float(inputs["ht_ratio_home"])
            la *= float(inputs["ht_ratio_away"])
            return score_grid_prob(lh, la, rho, hg, ag, max_goals=4)
        return score_grid_prob(lh, la, rho, hg, ag, max_goals=10)
    except (KeyError, TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 2) FREQUENZA DI LEGA — mapping punteggio -> selezione RPC get_market_frequency
# ---------------------------------------------------------------------------
def freq_selection(hg: int, ag: int, *, half: bool) -> Optional[tuple[str, str]]:
    """(p_market, p_selection) per la RPC; None se il punteggio è fuori dalla
    griglia della RPC (exact_ft: 0..3, exact_ht: 0..2) — meglio nessun numero
    che l'aggregato 'other' spacciato per il punteggio proposto."""
    if half:
        if 0 <= hg <= 2 and 0 <= ag <= 2:
            return "exact_ht", f"{hg}-{ag}"
        return None
    if 0 <= hg <= 3 and 0 <= ag <= 3:
        return "exact_ft", f"{hg}-{ag}"
    return None


def _league_frequency(db: Any, league_id: int, market: str, selection: str) -> Optional[dict]:
    """Baseline storica dalla RPC (cache per chiave). {'p':.., 'n':..} o None."""
    key = (int(league_id), market, selection)
    if key in _FREQ_CACHE:
        return _FREQ_CACHE[key]
    fn: Optional[Callable] = getattr(db, "market_frequency", None)
    out: Optional[dict] = None
    if callable(fn):
        try:
            res = fn(league_id, market, selection)
            meta = (res or {}).get("meta") or {}
            baseline = meta.get("baseline")
            n_eff = meta.get("n_effective")
            if baseline is not None and n_eff:
                out = {"p": float(baseline), "n": int(n_eff)}
        except Exception as ex:  # noqa: BLE001 — best-effort dichiarato
            logger.debug("[advisor] freq lega %s %s/%s KO: %s", league_id, market, selection, ex)
    _FREQ_CACHE[key] = out
    _bound(_FREQ_CACHE)
    return out


# ---------------------------------------------------------------------------
# 3) H2H — blocco h2h_hint dell'atlante (chiavi 'idA-idB' con idA<idB,
#    punteggi orientati come gol_A-gol_B)
# ---------------------------------------------------------------------------
def _h2h_atlas() -> dict:
    """Carica (una volta) il blocco h2h_hint dell'atlante. {} se assente/rotto."""
    global _H2H_CACHE
    if _H2H_CACHE is None:
        try:
            with open(_ATLAS_PATH, "r", encoding="utf-8") as f:
                _H2H_CACHE = json.load(f).get("h2h_hint") or {}
        except Exception as ex:  # noqa: BLE001 — l'atlante non deve mai bloccare
            logger.warning("[advisor] hazard_atlas_v2 non leggibile: %s", str(ex)[:120])
            _H2H_CACHE = {}
    return _H2H_CACHE


def h2h_score_stats(home_id: int, away_id: int, hg: int, ag: int,
                    *, half: bool, atlas: Optional[dict] = None) -> Optional[dict]:
    """Occorrenze del punteggio proposto negli scontri diretti.

    Orientamento (h2h_hint_policy): chiave 'idA-idB' con idA<idB e punteggi
    gol_A-gol_B -> se la squadra di CASA è idB il punteggio va invertito.
    None se la coppia non è nell'atlante (<3 scontri) — fallback pulito."""
    try:
        a, b = int(home_id), int(away_id)
    except (TypeError, ValueError):
        return None
    atlas = _h2h_atlas() if atlas is None else atlas
    key = f"{min(a, b)}-{max(a, b)}"
    entry = atlas.get(key)
    if not entry:
        return None
    scores = entry.get("ht_scores_a_b" if half else "ft_scores_a_b") or {}
    # punteggio proposto è HOME-AWAY: se home è l'id maggiore, inverti in A-B
    score_key = f"{hg}-{ag}" if a < b else f"{ag}-{hg}"
    n_meetings = int(entry.get("n_meetings") or 0)
    if n_meetings <= 0:
        return None
    return {"n_meetings": n_meetings, "n_score": int(scores.get(score_key, 0))}


# ---------------------------------------------------------------------------
# MATCHING evento Betfair -> fixture (riuso del matcher money-critical)
# ---------------------------------------------------------------------------
def _match_fixture(mission: dict, db: Any, now: datetime) -> Optional[dict]:
    """Fixture 'light' abbinata all'evento della missione (o None DICHIARATO).

    Riusa Betfair/betfair_match.resolve_matches (fuzzy + gate temporale +
    alias name_map): stesse garanzie del runner/watchlist. Cache per evento."""
    eid = str(mission.get("event_id") or "")
    if eid in _MATCH_CACHE:
        return _MATCH_CACHE[eid]
    result: Optional[dict] = None
    fn: Optional[Callable] = getattr(db, "fixtures_for_window", None)
    name = mission.get("event_name") or ""
    if callable(fn) and name:
        try:
            from Betfair.betfair_match import load_name_map, resolve_matches

            kick = mission.get("kickoff")
            center = None
            if kick:
                try:
                    center = datetime.fromisoformat(str(kick).replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    center = None
            center = center or now
            start = (center - timedelta(hours=_FIXTURE_WINDOW_H)).isoformat()
            end = (center + timedelta(hours=_FIXTURE_WINDOW_H)).isoformat()
            fixtures = fn(start, end) or []
            events = [{"id": eid, "name": name, "openDate": kick}]
            matched, _ = resolve_matches(events, fixtures, name_map=load_name_map())
            if matched:
                result = matched[0]["fixture"]
        except Exception as ex:  # noqa: BLE001 — matching fallito => advisor None
            logger.debug("[advisor] matching fixture KO per %s: %s", eid, str(ex)[:160])
            result = None
    _MATCH_CACHE[eid] = result
    _bound(_MATCH_CACHE)
    return result


def _fixture_analysis(db: Any, fixture_id: int) -> Optional[dict]:
    """db_json_analisi della fixture (cache). None se assente/errore."""
    fid = int(fixture_id)
    if fid in _ANALYSIS_CACHE:
        return _ANALYSIS_CACHE[fid]
    out: Optional[dict] = None
    fn: Optional[Callable] = getattr(db, "fixture_analysis", None)
    if callable(fn):
        try:
            raw = fn(fid)
            if isinstance(raw, str):
                raw = json.loads(raw)
            out = raw if isinstance(raw, dict) else None
        except Exception as ex:  # noqa: BLE001
            logger.debug("[advisor] db_json_analisi KO per %s: %s", fid, str(ex)[:120])
    _ANALYSIS_CACHE[fid] = out
    _bound(_ANALYSIS_CACHE)
    return out


# ---------------------------------------------------------------------------
# ENTRY POINT — chiamato da omega_service._cs_suggestion
# ---------------------------------------------------------------------------
def advisor_for_suggestion(*, mission: dict, market_type: str, runner_name: str,
                           db: Any, now: datetime) -> Optional[dict]:
    """Blocco ``advisor`` per la suggestion CS, o None (best-effort dichiarato).

    Struttura: {poisson_prob, freq_league, h2h, matched_fixture_id, sources}.
    - matching fallito / punteggio non parsabile / errore qualsiasi -> None;
    - dato singolo mancante -> quel campo None, gli altri restano;
    - MAI tocca id/prezzi della suggestion; MAI solleva verso il chiamante.
    """
    try:
        if db is None:
            return None
        half = market_type == "HALF_TIME_SCORE"
        parsed = E.parse_scoreline(runner_name or "")
        if parsed is None:
            return None  # aggregati ("Any Other...") non hanno un punteggio
        hg, ag = parsed
        cache_key = (str(mission.get("event_id")), market_type, f"{hg}-{ag}")
        if cache_key in _ADVISOR_CACHE:
            return _ADVISOR_CACHE[cache_key]

        t0 = time.monotonic()
        fixture = _match_fixture(mission, db, now)
        if fixture is None:
            # matching non affidabile: advisor NULL dichiarato, mai match forzato
            _ADVISOR_CACHE[cache_key] = None
            _bound(_ADVISOR_CACHE)
            return None

        fixture_id = fixture.get("fixture_id")
        league_id = fixture.get("league_id")
        home_id = fixture.get("home_team_id")
        away_id = fixture.get("away_team_id")

        sources: dict[str, str] = {
            "match": (f"betfair_match fixture {fixture_id} "
                      f"({fixture.get('home_team_name')} - {fixture.get('away_team_name')})"),
        }

        # --- 1) Poisson (pre-match, non condizionato al punteggio live) ------
        poisson_prob: Optional[float] = None
        if fixture_id is not None and time.monotonic() - t0 < BUDGET_S:
            analysis = _fixture_analysis(db, fixture_id)
            inputs = (analysis or {}).get("inputs") or {}
            p = poisson_score_prob(inputs, hg, ag, half=half)
            if p is not None:
                poisson_prob = round(p, 6)
                sources["poisson"] = (
                    f"fixture_predictions.db_json_analisi ({(analysis or {}).get('model', '?')}, "
                    "pre-match, non condizionata al live)")

        # --- 2) frequenza storica nella lega --------------------------------
        freq_league: Optional[dict] = None
        sel = freq_selection(hg, ag, half=half)
        if league_id and sel and time.monotonic() - t0 < BUDGET_S:
            market, selection = sel
            freq_league = _league_frequency(db, int(league_id), market, selection)
            if freq_league is not None:
                sources["freq_league"] = (
                    f"RPC get_market_frequency {market} '{selection}' lega {league_id} "
                    f"(ultime {freq_league['n']} settlate)")

        # --- 3) H2H dall'atlante ---------------------------------------------
        h2h = None
        if home_id and away_id:
            h2h = h2h_score_stats(int(home_id), int(away_id), hg, ag, half=half)
            if h2h is not None:
                sources["h2h"] = (
                    f"hazard_atlas_v2.h2h_hint ({h2h['n_meetings']} scontri, "
                    f"punteggi {'HT' if half else 'FT'} ufficiali)")

        advisor = {
            "matched_fixture_id": fixture_id,
            "poisson_prob": poisson_prob,
            "freq_league": freq_league,
            "h2h": h2h,
            "sources": sources,
        }
        _ADVISOR_CACHE[cache_key] = advisor
        _bound(_ADVISOR_CACHE)
        return advisor
    except Exception as ex:  # noqa: BLE001 — MAI bloccare la proposta
        logger.debug("[advisor] advisor KO per %s: %s",
                     mission.get("event_id"), str(ex)[:160])
        return None
