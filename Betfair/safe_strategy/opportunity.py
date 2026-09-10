"""opportunity.py — OPPORTUNITA' REALI in-play: modello di probabilita' per i
mercati principali confrontato con PREZZI e LIQUIDITA' del book live.

Domanda dell'utente (09/09/2026): "per ogni partita in corso, quali mercati in
relazione a TEMPO e PUNTEGGIO offrono un'opportunita' REALE?" — es. "Under 7.5
@1.10 sull'1-1 al 65' con X EUR abbinabili subito in back".

Risposta = tre pezzi che devono valere TUTTI insieme:
  1. P(esito | minuto, punteggio, rossi, forze pre-match) dal modello gia'
     CERTIFICATO dello stack (nessuna matematica nuova):
       · λ pre-match: fixture del DB (tactical_engine / Poisson xG-DC) oppure
         quote 1X2 pre-KO congelate dallo scanner (``omega_model.lambdas_from_pre_ko``);
       · λ RESIDUI live: ``live_engine.inplay_residual_rates`` (CDF reale del
         tempo, stato di gioco, cartellini, intensita' per lega);
       · griglia Poisson+Dixon-Coles sui GOL RESIDUI
         (``omega_model.residual_grid``, ρ per lega da ``live_engine_pro.rho_for_league``)
         traslata sul punteggio corrente, max_goals=12 (serve per le code di O/U 7.5);
       · aggregazione mercati con ``live_engine_pro._markets_from_residual``
         (1X2 / Over-Under / BTTS), piu' HT 1X2, celle CORRECT_SCORE e
         HALF_TIME_SCORE calcolate qui sulla STESSA griglia.
  2. PREZZO: il best back/lay del feed unico (``safe_strategy_scan``), de-viggato
     in modo moltiplicativo sui runner dello stesso mercato per la probabilita'
     implicita "pulita".
  3. LIQUIDITA': la size abbinabile SUBITO a quel prezzo (best offers, livello 0).
     Senza soldi abbinabili non e' un'opportunita', e' un grafico.

Si segnalano SOLO i casi estremamente a nostro favore: back con p_model molto
alta (default >= 0.85) ed edge >= min_edge, lay con p_model molto bassa (default
<= 0.15). Ogni segnale porta una CONFIDENZA che tiene conto di distanza dalla
soglia, profondita' del book, freschezza del prezzo e del CONTROINCROCIO con
l'Atlante Hazard (se il rischio-gol del modello diverge troppo dal dato storico
reale, la confidenza si dimezza o il segnale cade).

Tutto PURO: nessuna rete, nessun DB, orologio e atlante iniettabili.

ONESTA' (limiti dichiarati, vedi anche tools/validate_opportunity.py):
  · il modello e' Poisson/DC su λ residui: NON conosce infortuni, formazioni,
    xG live, meteo, motivazione; l'unico stato live e' minuto/punteggio/rossi;
  · la calibrazione in-play di ``dynamic_cal`` e' SPENTA nello stack (vedi
    live_engine_pro._CALIBRATION_ENABLED): le probabilita' NON sono ricalibrate
    su esiti reali in-play;
  · di conseguenza gli edge qui non sono un ROI garantito: vanno validati sulle
    registrazioni (``tools/validate_opportunity.py``) prima di rischiare soldi.
"""
from __future__ import annotations

import math
import re
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from Betfair.omega import omega_model as M

# ---------------------------------------------------------------------------
# Parametri (tutti sovrascrivibili dal chiamante)
# ---------------------------------------------------------------------------
DEFAULT_OPP_PARAMS: Dict[str, Any] = {
    # soglie di segnalazione
    "min_edge": 0.02,          # edge minimo (p_model - 1/quota) per segnalare
    "min_prob_back": 0.85,     # back solo su esiti quasi certi
    "max_prob_lay": 0.15,      # lay solo su esiti quasi impossibili
    "max_lay_price": 5.0,      # oltre: liability sproporzionata, mai lay
    "min_size": 20.0,          # EUR abbinabili SUBITO al best price
    # economia
    "commission": 0.05,        # commissione Betfair sul profitto netto
    # confidenza
    "ref_size": 200.0,         # size di riferimento per la profondita' del book
    "stale_price_s": 15.0,     # sotto: prezzo fresco; sopra: penalita' crescente
    "max_stale_s": 60.0,       # oltre: prezzo considerato morto (peso 0)
    # gate di contesto
    "post_goal_cooldown_s": 90.0,   # dopo un gol i prezzi sono instabili
    "hazard_horizon_min": 3.0,      # orizzonte del controincrocio con l'atlante
    "hazard_warn": 0.30,            # divergenza > 30% -> confidenza dimezzata
    "hazard_drop": 0.60,            # divergenza > 60% -> segnale scartato
    "min_confidence": 0.0,          # taglio finale sulla confidenza
    "default_lambda_confidence": 0.6,  # λ generici (nessuna fonte pre-match): confidenza x0.6
    # forma
    "max_per_event": 8,
    "max_goals_grid": 12,      # code alte: serve per Over/Under 7.5
    "ou_lines": (0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5),
    "cs_max_goals": 3,         # celle esplicite del CORRECT_SCORE Betfair
    "hts_max_goals": 2,        # celle esplicite del HALF_TIME_SCORE Betfair
}

_EPS = 1e-9

# aggregati dei mercati "punteggio" (mai una scoreline: mai celle singole)
_ANY_OTHER_HOME = re.compile(r"any\s*other.*home", re.IGNORECASE)
_ANY_OTHER_AWAY = re.compile(r"any\s*other.*away", re.IGNORECASE)
_ANY_OTHER_DRAW = re.compile(r"any\s*other.*draw", re.IGNORECASE)
_ANY_UNQUOTED = re.compile(r"any\s*(other|unquoted)", re.IGNORECASE)
_GOAL_TYPE = re.compile(r"goal", re.IGNORECASE)
_NOT_A_GOAL = re.compile(r"cancel|attempt|miss|disallow|chance|kick", re.IGNORECASE)


@dataclass(frozen=True)
class Opportunity:
    """Una singola opportunita' AZIONABILE (prezzo + size gia' verificati)."""

    market_type: str
    market_name: str
    line: Optional[float]
    market_id: Optional[str]
    selection_id: Optional[int]
    selection_name: str
    side: str               # 'back' | 'lay'
    price: float
    size_available: float
    p_model: float
    p_implied: float        # de-viggata sui runner dello stesso mercato
    edge: float             # back: p_model - 1/back ; lay: 1/lay - p_model
    ev: float               # profitto atteso per 1 EUR di STAKE, netto commissione
    confidence: float       # 0..1
    rationale: str
    minute: Optional[int]
    score: str


# ---------------------------------------------------------------------------
# λ: fixture del DB, altrimenti quote pre-KO congelate
# ---------------------------------------------------------------------------
def _pos_float(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) and f > 0 else None


def _fixture_inputs(fixture: Optional[dict]) -> Dict[str, Any]:
    """``db_json_analisi`` (o gia' il suo nodo ``inputs``) → dict degli input."""
    if not isinstance(fixture, dict):
        return {}
    inner = fixture.get("inputs")
    if isinstance(inner, dict):
        merged = dict(inner)
        for k in ("league_id", "dc_rho"):
            if k in fixture and k not in merged:
                merged[k] = fixture[k]
        return merged
    return fixture


def resolve_lambdas(
    payload: dict, *, fixture: Optional[dict]
) -> Optional[Tuple[float, float, Optional[int], str]]:
    """(λ_casa, λ_trasferta, league_id, fonte) — 'fixture' o 'pre_ko'.

    Stessa CATENA di Omega (``omega_service._prematch_lambdas``): prima i λ
    per-squadra della fixture abbinata (tactical_engine / Poisson xG-DC), poi il
    fallback sulle quote 1X2 pre-KO CONGELATE dallo scanner. None = nessun
    modello possibile: si sta zitti, mai stimare a occhi chiusi.
    """
    inputs = _fixture_inputs(fixture)
    league_id = inputs.get("league_id")
    try:
        league_id = int(league_id) if league_id is not None else None
    except (TypeError, ValueError):
        league_id = None
    lh = _pos_float(inputs.get("lambda_home"))
    la = _pos_float(inputs.get("lambda_away"))
    if lh is not None and la is not None:
        return lh, la, league_id, "fixture"
    pre = M.lambdas_from_pre_ko((payload or {}).get("pre_ko"))
    if pre is not None:
        return float(pre[0]), float(pre[1]), league_id, "pre_ko"
    return None


def ht_ratio_from_fixture(fixture: Optional[dict]) -> Optional[Tuple[float, float]]:
    """(ht_ratio_casa, ht_ratio_trasferta) dagli input della fixture, se ci sono.
    E' la quota di gol che quella squadra segna nel 1T secondo il motore: corregge
    la scala dei λ sull'orizzonte HT. None quando il dato non esiste."""
    inputs = _fixture_inputs(fixture)
    rh = _pos_float(inputs.get("ht_ratio_home"))
    ra = _pos_float(inputs.get("ht_ratio_away"))
    if rh is None or ra is None:
        return None
    return rh, ra


# ---------------------------------------------------------------------------
# Adattatore griglia dict (omega_model) → interfaccia numpy-like
# ---------------------------------------------------------------------------
class _GridView:
    """La griglia dict di ``omega_model.residual_grid`` esposta con la stessa
    interfaccia (``.shape``, ``g[i, j]``) che ``_markets_from_residual`` usa:
    cosi' l'aggregazione dei mercati resta QUELLA certificata, non una copia."""

    __slots__ = ("_g", "shape")

    def __init__(self, grid: Dict[Tuple[int, int], float], n: int) -> None:
        self._g = grid
        self.shape = (n, n)

    def __getitem__(self, key: Tuple[int, int]) -> float:
        return self._g.get(key, 0.0)


def _line_key(line: float) -> str:
    """2.5 → '2_5' (stessa convenzione di ``_markets_from_residual``)."""
    return str(float(line)).replace(".", "_")


# ---------------------------------------------------------------------------
# Il modello
# ---------------------------------------------------------------------------
class OpportunityModel:
    """Prezza i mercati principali sullo stato live e li confronta col book."""

    def __init__(
        self,
        params: Optional[dict] = None,
        *,
        atlas: Optional[dict] = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.params: Dict[str, Any] = {**DEFAULT_OPP_PARAMS, **(params or {})}
        self.atlas = atlas
        self.clock = clock
        # cache del book per (stato live + λ): il tick dello scanner ricalcola
        # la stessa griglia decine di volte al minuto per lo stesso evento
        self._book_cache: Dict[Tuple[Any, ...], Dict[str, float]] = {}

    # ------------------------------------------------------------------ book
    def book(
        self,
        payload: dict,
        *,
        lambdas: Tuple[float, float],
        league_id: Optional[int],
        ht_ratio: Optional[Tuple[float, float]] = None,
    ) -> Dict[str, float]:
        """P di TUTTI gli esiti che sappiamo prezzare, condizionate a
        (minuto, punteggio, rossi).

        Chiavi: ``home|draw|away``, ``over_X_Y|under_X_Y``, ``btts_yes|btts_no``,
        ``ht_home|ht_draw|ht_away`` (solo nel 1T), ``cs_H_A`` + ``cs_any_other_*``,
        ``hts_H_A`` + ``hts_any_unquoted`` (solo nel 1T).
        """
        p = self.params
        minute = payload.get("minute")
        m = 0 if minute is None else max(0, int(minute))
        sh = int(payload.get("score_home") or 0)
        sa = int(payload.get("score_away") or 0)
        rh = int(payload.get("red_home") or 0)
        ra = int(payload.get("red_away") or 0)
        lh_pre, la_pre = float(lambdas[0]), float(lambdas[1])

        key = (m, sh, sa, rh, ra, round(lh_pre, 4), round(la_pre, 4), league_id,
               None if ht_ratio is None else (round(ht_ratio[0], 4), round(ht_ratio[1], 4)))
        cached = self._book_cache.get(key)
        if cached is not None:
            return cached

        from Betfair.stream.engine.live_engine import inplay_residual_rates
        from Betfair.stream.engine.live_engine_pro import (
            _markets_from_residual, rho_for_league,
        )

        lam_h, lam_a = inplay_residual_rates(
            lh_pre, la_pre, m, sh, sa, red_home=rh, red_away=ra, league_id=league_id,
        )
        rho = rho_for_league(league_id)
        max_goals = int(p["max_goals_grid"])
        dc = (sh == 0 and sa == 0)
        grid = M.residual_grid(lam_h, lam_a, rho, max_goals, dixon_coles=dc)
        lines = [float(x) for x in p["ou_lines"]]
        out: Dict[str, float] = dict(
            _markets_from_residual(_GridView(grid, max_goals + 1), sh, sa, lines)
        )
        # gli esiti GIA' DECISI non si stimano: si sanno (P esatta 0/1)
        total_now = sh + sa
        for ln in lines:
            k = _line_key(ln)
            if total_now > ln:
                out[f"over_{k}"], out[f"under_{k}"] = 1.0, 0.0
        if sh >= 1 and sa >= 1:
            out["btts_yes"], out["btts_no"] = 1.0, 0.0

        out.update(self._score_cells(grid, sh, sa, "cs_", int(p["cs_max_goals"])))

        # ---- orizzonte PRIMO TEMPO (HT 1X2 + HALF_TIME_SCORE)
        if m < 45:
            lam_hh, lam_ha = self._ht_lambdas(lam_h, lam_a, m, ht_ratio)
            grid_ht = M.residual_grid(
                lam_hh, lam_ha, rho, M.MAX_GOALS_GRID_HT, dixon_coles=dc,
            )
            ht = _markets_from_residual(
                _GridView(grid_ht, M.MAX_GOALS_GRID_HT + 1), sh, sa, [0.5],
            )
            out["ht_home"], out["ht_draw"], out["ht_away"] = ht["home"], ht["draw"], ht["away"]
            out.update(self._score_cells(grid_ht, sh, sa, "hts_", int(p["hts_max_goals"])))

        if len(self._book_cache) > 512:
            self._book_cache.clear()
        self._book_cache[key] = out
        return out

    @staticmethod
    def _ht_lambdas(
        lam_h: float, lam_a: float, minute: int,
        ht_ratio: Optional[Tuple[float, float]],
    ) -> Tuple[float, float]:
        """λ residui RISCALATI all'orizzonte del 45' con la CDF gol reale.

        ``inplay_residual_rates`` da' i gol residui fino al 90'; la quota che
        cade entro il 45' e' (gol residui del 1T)/(gol residui della partita) =
        remaining_frac(t,45)*first_half_share / remaining_frac(t,90).
        """
        from value_engine.goal_timing import first_half_share, remaining_frac

        rem_ft = remaining_frac(float(minute), 90.0)
        if rem_ft <= _EPS:
            return 0.001, 0.001
        share = remaining_frac(float(minute), 45.0) * first_half_share() / rem_ft
        share = max(0.0, min(1.0, share))
        kh = ka = 1.0
        if ht_ratio is not None:
            # ht_ratio e' la quota di gol-squadra attesa nel 1T: normalizzata sulla
            # media (0.45) e clampata, non stravolge mai la scala
            kh = max(0.5, min(1.5, ht_ratio[0] / 0.45))
            ka = max(0.5, min(1.5, ht_ratio[1] / 0.45))
        return max(0.001, lam_h * share * kh), max(0.001, lam_a * share * ka)

    @staticmethod
    def _score_cells(
        grid: Dict[Tuple[int, int], float], sh: int, sa: int, prefix: str, max_goals: int,
    ) -> Dict[str, float]:
        """Celle di un mercato "punteggio" + aggregati, dalla griglia RESIDUA."""
        out: Dict[str, float] = {}
        quoted = 0.0
        any_home = any_away = any_draw = 0.0
        for (dh, da), p in grid.items():
            fh, fa = sh + dh, sa + da
            if fh <= max_goals and fa <= max_goals:
                out[f"{prefix}{fh}_{fa}"] = out.get(f"{prefix}{fh}_{fa}", 0.0) + p
                quoted += p
            elif fh > fa:
                any_home += p
            elif fh < fa:
                any_away += p
            else:
                any_draw += p
        # celle raggiungibili ma a probabilita' nulla: esistono comunque nel book
        for fh in range(sh, max_goals + 1):
            for fa in range(sa, max_goals + 1):
                out.setdefault(f"{prefix}{fh}_{fa}", 0.0)
        out[f"{prefix}any_other_home"] = any_home
        out[f"{prefix}any_other_away"] = any_away
        out[f"{prefix}any_other_draw"] = any_draw
        out[f"{prefix}any_unquoted"] = max(0.0, 1.0 - quoted)
        return out

    # -------------------------------------------------------------- evaluate
    def evaluate(
        self,
        payload: dict,
        *,
        sport: str,
        lambdas: Optional[Tuple[float, float]],
        league_id: Optional[int],
        now_ts: float,
        ht_ratio: Optional[Tuple[float, float]] = None,
        lambda_source: Optional[str] = None,
    ) -> List[dict]:
        """Opportunita' ordinate per ``ev*confidenza`` (dict = asdict(Opportunity)).

        [] — mai eccezioni — quando: sport != calcio, evento non in-play, minuto
        o punteggio assenti, λ non risolvibili, cooldown post-gol attivo.

        ``lambda_source == 'default'`` = il chiamante non ha trovato NESSUNA
        fonte pre-match e usa λ generici: ogni confidenza viene moltiplicata per
        ``default_lambda_confidence`` e la rationale lo dichiara.
        """
        if sport != "calcio" or not isinstance(payload, dict):
            return []
        if not payload.get("inplay"):
            return []
        minute = payload.get("minute")
        if minute is None or payload.get("score_home") is None or payload.get("score_away") is None:
            return []
        if lambdas is None or len(tuple(lambdas)) < 2:
            return []
        if _pos_float(lambdas[0]) is None or _pos_float(lambdas[1]) is None:
            return []
        p = self.params
        m = max(0, int(minute))
        sh = int(payload.get("score_home") or 0)
        sa = int(payload.get("score_away") or 0)

        cool = self._goal_cooldown_left(payload, m, now_ts)
        if cool > 0.0:
            return []

        try:
            probs = self.book(payload, lambdas=(float(lambdas[0]), float(lambdas[1])),
                              league_id=league_id, ht_ratio=ht_ratio)
        except Exception:  # noqa: BLE001 - un modello che esplode non ferma lo scanner
            return []

        hazard = self._hazard_check(payload, lambdas=lambdas, league_id=league_id, minute=m)
        if lambda_source == "default":
            hazard = dict(hazard)
            hazard["penalty"] = float(hazard.get("penalty") or 0.0) * float(p["default_lambda_confidence"])
            hazard["note"] = f"{hazard.get('note')}, lambda di default (nessuna fonte pre-match)"

        found: List[Opportunity] = []
        for spec in self._market_specs(payload, m):
            found.extend(self._scan_market(spec, probs, payload, now_ts, hazard, m, sh, sa))
        found.sort(key=lambda o: (o.ev * o.confidence, o.edge), reverse=True)
        return [asdict(o) for o in found[: int(p["max_per_event"])]]

    # ------------------------------------------------------ gate: cooldown gol
    def _goal_cooldown_left(self, payload: dict, minute: int, now_ts: float) -> float:
        """Secondi di cooldown ancora attivi dopo l'ultimo gol della timeline.

        La timeline IPS porta il MINUTO dell'evento (non il timestamp): la
        distanza si misura in minuti di gioco (60 s ciascuno). Se un evento porta
        ``ts_ms``, quello ha la precedenza (piu' preciso)."""
        cooldown = float(self.params["post_goal_cooldown_s"])
        if cooldown <= 0:
            return 0.0
        best = 0.0
        for ev in (payload.get("timeline") or []):
            if not isinstance(ev, dict):
                continue
            t = str(ev.get("type") or "")
            if not _GOAL_TYPE.search(t) or _NOT_A_GOAL.search(t):
                continue
            ts_ms = ev.get("ts_ms")
            if isinstance(ts_ms, (int, float)):
                elapsed = now_ts - float(ts_ms) / 1000.0
            else:
                gm = ev.get("minute")
                if not isinstance(gm, int):
                    continue
                elapsed = (minute - gm) * 60.0
            if elapsed < 0:
                elapsed = 0.0
            best = max(best, cooldown - elapsed)
        return max(0.0, best)

    # ------------------------------------------- controincrocio Atlante Hazard
    def _hazard_check(
        self, payload: dict, *, lambdas: Tuple[float, float],
        league_id: Optional[int], minute: int,
    ) -> Dict[str, Any]:
        """Confronta l'hazard-gol del MODELLO con quello STORICO dell'Atlante.

        Divergenza relativa > hazard_warn → confidenza dimezzata; > hazard_drop →
        segnale scartato (il modello sta dicendo qualcosa che i dati reali non
        confermano). Senza atlante il controllo e' semplicemente assente: mai
        inventare un via libera, ma neanche punire un dato che non abbiamo."""
        out: Dict[str, Any] = {"ok": True, "drop": False, "penalty": 1.0,
                               "note": "hazard non verificato (atlante assente)",
                               "divergence": None, "source": "none"}
        if not self.atlas:
            return out
        try:
            from Betfair.stream.engine.live_engine_pro import event_goal_hazard
            from Betfair.stream.scalper.theta_bot import hazard_lookup
        except Exception:  # noqa: BLE001
            return out
        sh = int(payload.get("score_home") or 0)
        sa = int(payload.get("score_away") or 0)
        horizon = float(self.params["hazard_horizon_min"])
        model = event_goal_hazard(
            score_home=sh, score_away=sa, minute=minute,
            prematch_lambda_home=float(lambdas[0]), prematch_lambda_away=float(lambdas[1]),
            league_id=league_id,
            red_home=int(payload.get("red_home") or 0),
            red_away=int(payload.get("red_away") or 0),
            horizon_min=horizon,
        )
        p_atlas, source = hazard_lookup(
            self.atlas, minute, sh + sa, league_id,
            home_team=payload.get("home"), away_team=payload.get("away"),
        )
        if model is None or p_atlas is None or p_atlas <= 0:
            return out
        p_model = float(model.get("p_next") or 0.0)
        div = abs(p_model - float(p_atlas)) / float(p_atlas)
        out["divergence"] = div
        out["source"] = source
        if div > float(self.params["hazard_drop"]):
            out.update(ok=False, drop=True, penalty=0.0,
                       note=f"hazard modello {p_model * 100:.1f}% vs atlante "
                            f"{float(p_atlas) * 100:.1f}%: divergenza {div * 100:.0f}%")
        elif div > float(self.params["hazard_warn"]):
            out.update(penalty=0.5,
                       note=f"hazard divergente dall'atlante ({div * 100:.0f}%)")
        else:
            out.update(note="hazard coerente con l'atlante")
        return out

    # ------------------------------------------------------- mercati del feed
    def _market_specs(self, payload: dict, minute: int) -> List[Dict[str, Any]]:
        """Mercati prezzabili presenti nel payload → spec uniformi
        {market_type, market_name, market_id, status, line, ts_ms, runners}
        dove runner = {selection_id, name, back, lay, back_size, lay_size,
        runner_status, prob_key}."""
        specs: List[Dict[str, Any]] = []

        # 1X2 (MATCH_ODDS) — dal blocco `odds` storico del feed
        odds = payload.get("odds")
        if isinstance(odds, dict):
            names = {"home": payload.get("home") or "Casa",
                     "draw": "The Draw",
                     "away": payload.get("away") or "Trasferta"}
            runners = []
            for side in ("home", "draw", "away"):
                pair = odds.get(side)
                if not isinstance(pair, dict):
                    continue
                runners.append({**pair, "name": names[side], "prob_key": side,
                                "runner_status": "ACTIVE"})
            if runners:
                specs.append({
                    "market_type": "MATCH_ODDS", "market_name": "1X2",
                    "market_id": payload.get("mo_market_id"),
                    "status": payload.get("mo_status"), "line": None,
                    "ts_ms": payload.get("odds_ts_ms"), "runners": runners,
                })

        # OVER/UNDER (blocchi `ou`)
        for blk in (payload.get("ou") or []):
            if not isinstance(blk, dict):
                continue
            line = blk.get("line")
            if line is None:
                continue
            k = _line_key(float(line))
            runners = []
            for s in (blk.get("selections") or []):
                nm = str(s.get("name") or "").lower()
                if "over" in nm:
                    runners.append({**s, "prob_key": f"over_{k}"})
                elif "under" in nm:
                    runners.append({**s, "prob_key": f"under_{k}"})
            if runners:
                specs.append({
                    "market_type": "OVER_UNDER", "market_name": f"Over/Under {line}",
                    "market_id": blk.get("market_id"), "status": blk.get("status"),
                    "line": float(line), "ts_ms": blk.get("ts_ms"), "runners": runners,
                })

        # BTTS
        blk = payload.get("btts")
        if isinstance(blk, dict):
            runners = []
            for s in (blk.get("selections") or []):
                nm = str(s.get("name") or "").strip().lower()
                if nm in ("yes", "si", "sì"):
                    runners.append({**s, "prob_key": "btts_yes"})
                elif nm == "no":
                    runners.append({**s, "prob_key": "btts_no"})
            if runners:
                specs.append({
                    "market_type": "BOTH_TEAMS_TO_SCORE", "market_name": "Gol/NoGol",
                    "market_id": blk.get("market_id"), "status": blk.get("status"),
                    "line": None, "ts_ms": blk.get("ts_ms"), "runners": runners,
                })

        # 1X2 primo tempo (HALF_TIME) — solo finche' il 1T e' in corso
        blk = payload.get("ht_result")
        if isinstance(blk, dict) and minute < 45:
            runners = self._sides_1x2(blk.get("selections") or [], payload, "ht_")
            if runners:
                specs.append({
                    "market_type": "HALF_TIME", "market_name": "1X2 primo tempo",
                    "market_id": blk.get("market_id"), "status": blk.get("status"),
                    "line": None, "ts_ms": blk.get("ts_ms"), "runners": runners,
                })

        # CORRECT SCORE e HALF TIME SCORE (blocchi gia' pubblicati per Omega)
        for key, mtype, mname, prefix, only_first_half in (
            ("cs", "CORRECT_SCORE", "Risultato esatto", "cs_", False),
            ("ht", "HALF_TIME_SCORE", "Risultato esatto 1T", "hts_", True),
        ):
            blk = payload.get(key)
            if not isinstance(blk, dict):
                continue
            if only_first_half and minute >= 45:
                continue
            runners = []
            for s in (blk.get("selections") or []):
                pk = self._score_prob_key(str(s.get("name") or ""), prefix)
                if pk:
                    runners.append({**s, "prob_key": pk})
            if runners:
                specs.append({
                    "market_type": mtype, "market_name": mname,
                    "market_id": blk.get("market_id"), "status": blk.get("status"),
                    "line": None, "ts_ms": blk.get("ts_ms"), "runners": runners,
                })
        return specs

    @staticmethod
    def _sides_1x2(selections: List[dict], payload: dict, prefix: str) -> List[dict]:
        """Runner 1X2 → prob_key. Il pareggio dal nome; casa/trasferta per nome
        squadra e, se i nomi non combaciano, per ordine (sortPriority Betfair:
        1=casa, 2=trasferta)."""
        home_name = str(payload.get("home") or "").strip().lower()
        away_name = str(payload.get("away") or "").strip().lower()
        out: List[dict] = []
        others: List[dict] = []
        for s in selections:
            nm = str(s.get("name") or "").strip().lower()
            if "draw" in nm or "pareggio" in nm:
                out.append({**s, "prob_key": f"{prefix}draw"})
            elif home_name and nm == home_name:
                out.append({**s, "prob_key": f"{prefix}home"})
            elif away_name and nm == away_name:
                out.append({**s, "prob_key": f"{prefix}away"})
            else:
                others.append(s)
        assigned = {r["prob_key"] for r in out}
        for s in others:
            for key in (f"{prefix}home", f"{prefix}away"):
                if key not in assigned:
                    out.append({**s, "prob_key": key})
                    assigned.add(key)
                    break
        return out

    @staticmethod
    def _score_prob_key(name: str, prefix: str) -> Optional[str]:
        """Nome del runner di un mercato "punteggio" → chiave del book."""
        from Betfair.omega.omega_engine import parse_scoreline

        parsed = parse_scoreline(name)
        if parsed is not None:
            return f"{prefix}{parsed[0]}_{parsed[1]}"
        if _ANY_OTHER_HOME.search(name):
            return f"{prefix}any_other_home"
        if _ANY_OTHER_AWAY.search(name):
            return f"{prefix}any_other_away"
        if _ANY_OTHER_DRAW.search(name):
            return f"{prefix}any_other_draw"
        if _ANY_UNQUOTED.search(name):
            return f"{prefix}any_unquoted"
        return None

    # --------------------------------------------------------- scan di 1 mercato
    def _scan_market(
        self, spec: Dict[str, Any], probs: Dict[str, float], payload: dict,
        now_ts: float, hazard: Dict[str, Any], minute: int, sh: int, sa: int,
    ) -> List[Opportunity]:
        if spec.get("status") != "OPEN":
            return []                    # sospeso/chiuso: nulla e' abbinabile
        runners = [
            r for r in spec["runners"]
            if r.get("prob_key") in probs
            and (r.get("runner_status") in (None, "ACTIVE"))
        ]
        if not runners:
            return []
        implied = self._devig(runners)
        age = self._price_age(spec.get("ts_ms"), now_ts)
        out: List[Opportunity] = []
        for r in runners:
            pm = float(probs[r["prob_key"]])
            p_imp = implied.get(id(r), None)
            for side in ("back", "lay"):
                opp = self._try_side(
                    side, r, pm, p_imp, spec, payload, hazard, age, minute, sh, sa,
                )
                if opp is not None:
                    out.append(opp)
        return out

    @staticmethod
    def _devig(runners: List[dict]) -> Dict[int, float]:
        """P implicite de-viggate (normalizzazione moltiplicativa dell'overround)
        sui runner dello STESSO mercato che hanno un back valido."""
        inv: Dict[int, float] = {}
        for r in runners:
            b = r.get("back")
            if isinstance(b, (int, float)) and b > 1.0:
                inv[id(r)] = 1.0 / float(b)
        s = sum(inv.values())
        if s <= 0:
            return {}
        if len(inv) < 2:
            return dict(inv)          # un solo prezzo: niente da normalizzare
        return {k: v / s for k, v in inv.items()}

    def _price_age(self, ts_ms: Any, now_ts: float) -> Optional[float]:
        if not isinstance(ts_ms, (int, float)):
            return None
        return max(0.0, now_ts - float(ts_ms) / 1000.0)

    def _staleness_weight(self, age: Optional[float]) -> float:
        if age is None:
            return 1.0                  # nessun timestamp: nessuna penalita' finta
        p = self.params
        fresh, dead = float(p["stale_price_s"]), float(p["max_stale_s"])
        if age <= fresh:
            return 1.0
        if age >= dead or dead <= fresh:
            return 0.0
        return max(0.0, 1.0 - (age - fresh) / (dead - fresh))

    def _try_side(
        self, side: str, runner: dict, p_model: float, p_implied: Optional[float],
        spec: Dict[str, Any], payload: dict, hazard: Dict[str, Any],
        age: Optional[float], minute: int, sh: int, sa: int,
    ) -> Optional[Opportunity]:
        p = self.params
        price = runner.get("back") if side == "back" else runner.get("lay")
        size = runner.get("back_size") if side == "back" else runner.get("lay_size")
        if not isinstance(price, (int, float)) or price <= 1.0:
            return None
        size_f = float(size) if isinstance(size, (int, float)) else 0.0
        if size_f < float(p["min_size"]):
            return None
        price = float(price)
        if side == "back":
            if p_model < float(p["min_prob_back"]):
                return None
            edge = p_model - 1.0 / price
            head = (p_model - float(p["min_prob_back"])) / max(_EPS, 1.0 - float(p["min_prob_back"]))
        else:
            if p_model > float(p["max_prob_lay"]) or price > float(p["max_lay_price"]):
                return None
            edge = 1.0 / price - p_model
            head = (float(p["max_prob_lay"]) - p_model) / max(_EPS, float(p["max_prob_lay"]))
        if edge < float(p["min_edge"]):
            return None
        if hazard.get("drop"):
            return None

        comm = float(p["commission"])
        if side == "back":
            ev = p_model * (price - 1.0) * (1.0 - comm) - (1.0 - p_model)
        else:
            ev = (1.0 - p_model) * (1.0 - comm) - p_model * (price - 1.0)
        if ev <= 0:
            return None

        c_edge = min(1.0, edge / max(_EPS, 2.0 * float(p["min_edge"])))
        c_head = max(0.0, min(1.0, head))
        c_depth = min(1.0, size_f / max(_EPS, float(p["ref_size"])))
        c_fresh = self._staleness_weight(age)
        conf = (0.35 * c_edge + 0.25 * c_head + 0.20 * c_depth + 0.20 * c_fresh)
        conf *= float(hazard.get("penalty") or 0.0)
        conf = max(0.0, min(1.0, conf))
        if conf < float(p["min_confidence"]):
            return None

        name = str(runner.get("name") or "")
        return Opportunity(
            market_type=str(spec["market_type"]),
            market_name=str(spec["market_name"]),
            line=spec.get("line"),
            market_id=spec.get("market_id"),
            selection_id=(int(runner["selection_id"])
                          if runner.get("selection_id") is not None else None),
            selection_name=name,
            side=side,
            price=round(price, 4),
            size_available=round(size_f, 2),
            p_model=round(p_model, 6),
            p_implied=round(float(p_implied), 6) if p_implied is not None else round(1.0 / price, 6),
            edge=round(edge, 6),
            ev=round(ev, 6),
            confidence=round(conf, 4),
            rationale=self._rationale(side, spec, name, price, size_f, p_model, edge,
                                      minute, sh, sa, hazard),
            minute=minute,
            score=f"{sh}-{sa}",
        )

    # ------------------------------------------------------------- rationale
    @staticmethod
    def _prob_label(spec: Dict[str, Any], name: str) -> str:
        mt = spec.get("market_type")
        if mt == "OVER_UNDER" and spec.get("line") is not None:
            ln = float(spec["line"])
            if "under" in name.lower():
                return f"P(<={int(ln)} gol)"
            return f"P(>={int(ln) + 1} gol)"
        if mt == "BOTH_TEAMS_TO_SCORE":
            return f"P(Gol/NoGol {name})"
        if mt == "HALF_TIME":
            return f"P(1T {name})"
        if mt == "HALF_TIME_SCORE":
            return f"P(1T {name})"
        if mt == "CORRECT_SCORE":
            return f"P({name})"
        return f"P({name})"

    @staticmethod
    def _pct(p: float) -> str:
        """Percentuale a 1 decimale, senza MAI arrotondare a '100.0%' una
        probabilità che non è certezza (o a '0.0%' una che non è impossibile)."""
        s = f"{p * 100:.1f}"
        if s == "100.0" and p < 1.0:
            return "99.9"
        if s == "0.0" and p > 0.0:
            return "0.1"
        return s

    def _rationale(
        self, side: str, spec: Dict[str, Any], name: str, price: float, size: float,
        p_model: float, edge: float, minute: int, sh: int, sa: int,
        hazard: Dict[str, Any],
    ) -> str:
        """Frase corta in italiano, SOLO ASCII (console Windows cp1252)."""
        head = f"{name} @{price:.2f}" if side == "back" else f"LAY {name} @{price:.2f}"
        return (
            f"{head} sul {sh}-{sa} al {minute}': "
            f"{self._prob_label(spec, name)}={self._pct(p_model)}%, "
            f"edge {self._pct(edge)}%, {size:.0f} EUR abbinabili, "
            f"{hazard.get('note')}"
        )
