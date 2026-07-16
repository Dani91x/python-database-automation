"""THETA SCALPER in-play (BACK Under O/U) — gemella di SniperStrategy.

FILOSOFIA (spec utente confermata 15/07, verdetto backtest +0.257/scalp):
il bot compra "theta" (decadimento naturale dell'Under col passare dei minuti
senza gol) SOLO nei momenti in cui l'Atlante Hazard dice che il gol imminente
e' improbabile. Linea LONTANA dal punteggio (Under gol correnti + 2.5): il
decadimento e' lento ma il rischio-gol per singolo scalp e' minimo.

VERDETTO S4 (griglia 16/07: 19 celle x 26 raw, fill conservativo):
il theta CLASSICO e' EV− in TUTTE le 18 varianti (miglior cella C7 −22.07)
→ il default C7 gira in PAPER solo per RACCOLTA DATI, non per profitto;
UNICA pista EV+ l'OVERSHOOT post-gol (C17 +2.12, 7/9 eventi, n=15<40):
preset 'overshoot' DA CAMPIONARE fino a n>=40, NON promosso.

SEMAFORO D'INGRESSO (tutte le condizioni insieme):
  * HAZARD: lookup su ``Betfair/omega/data/hazard_atlas_v1.json`` con catena
    squadre→lega→globale (meta.lookup del JSON); p_goal_next_3min <= soglia
    (default 0.085). Atlante assente o cella ignota = ROSSO (fail-closed).
  * QUIETE: nessuna sospensione in-play recente (EventRiskSemaphore, 120s).
  * MICROSTRUTTURA: spread <= 2 tick, liquidita' best-back >= 20 EUR.
  * OROLOGIO: minuto REALE fuori dalle zone rosse 40-45' e 80-90' (recupero
    incluso: piu' gol = piu' hazard, Atlante §ZONE).
  * PREZZO: best back Under in [1.05, 3.5].

ESECUZIONE — COPPIA ATOMICA:
  la coppia (entry BACK al best + green LAY a -1 tick, size compute_green
  spalmata sui 2 esiti) e' PRE-CALCOLATA prima dell'ingresso; al fill la close
  parte IMMEDIATA coi numeri REALI matchati (mai il piano teorico — bug 1).
  Scratch timer (120s classico / 240s overshoot, publish_time) → flatten;
  post-gol
  (sospensione in-play) → chiusura al riprezzo via flatten. Il verde si
  contabilizza SEMPRE col net reale ricalcolato (_real_net, fix bug 1).

KILL-SWITCH: max colpi/partita (default 10), stop-loss theta per evento
(default 5 EUR, riusa il meccanismo event_loss_cap dello sniper); il cap
GLOBALE evento resta al heartbeat di sessione (event_global_cap).

MODALITA' MANUALE (theta_confirm_mode): il bot PROPONE (entry/scratch/postgol)
su ``theta_confirm_requests`` via ThetaConfirmBus e attende la conferma con
poll. TIMEOUT SCADUTO → la PROTEZIONE (scratch/postgol) si esegue COMUNQUE
(mai posizione nuda); l'ENTRY scaduta/rifiutata si scarta. La conferma e' solo
un via-libera: i prezzi si ricalcolano SEMPRE freschi al momento del fuoco.

``dry_run`` (= scalper_control.dry_run) e' l'interruttore paper/live: in dry
il bot emette solo ``theta_dry_fire`` (demo del cervello, nessun ordine).
"""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from flumine.utils import get_nearest_price, get_price, get_size, price_ticks_away

from .risk_semaphore import notice_suspension
from .scalper_bot import compute_green, ticks_between
from .sniper_bot import SniperStrategy, _Pos

logger = logging.getLogger(__name__)
_EPS = 1e-9

# percorso di default dell'Atlante Hazard (repo-relative, v1 15/07)
ATLAS_DEFAULT_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "omega", "data",
    "hazard_atlas_v1.json"))

# zone rosse dell'orologio (Atlante §ZONE: recupero = zona rossa)
ZONE_RED = ((40.0, 46.0), (80.0, 1e9))


@dataclass
class _ThetaPos(_Pos):
    """_Pos + campi del ciclo theta, DICHIARATI sul dataclass (fix S6:
    prima erano attributi dinamici — sarebbero esplosi con slots=True)."""

    entry_placed_pt: Optional[float] = None   # ancora del TTL entry
    pending_protect: Optional[int] = None     # proposta protezione in corso
    # ---- STEP 1 (cecchino): ciclo pre-match PERSIST ----
    prematch: bool = False                    # posizione nata pre-match
    prematch_taken: bool = False              # escalation: cancel richiesto
    prematch_take_placed: bool = False        # escalation: taker gia' piazzato
    prematch_exit_placed: bool = False        # target adattivo gia' piazzato
    prematch_deadline_ms: Optional[float] = None  # KO + timeout adattivo
    # scratch per-ingresso (STEP 3: overshoot 240s / 120s se hazard alto;
    # None = scratch_s della strategia)
    scratch_override_s: Optional[float] = None

# ---------------------------------------------------------------------------
# PRESET S4 (griglia 16/07) — pacchetti raccomandati per il PAPER.
#   'classico'  = cella C7: quiete pre-gol, finestre 0-35'/46-70', g<=1,
#                 scratch 120s, linea +2.5, maker, green 1 tick. VERDETTO:
#                 EV− su 26 raw → gira in paper per RACCOLTA DATI.
#   'overshoot' = cella C17: back Under (gol+2.5) 30-90s DOPO il gol (quota
#                 gonfiata dal riprezzo), hazard_max 0.10, scratch 240s.
#                 Unica pista EV+ (+2.12, n=15<40): DA CAMPIONARE, non promossa.
# I parametri ESPLICITI in theta_params vincono SEMPRE sul preset.
# ---------------------------------------------------------------------------
THETA_PRESETS: Dict[str, Dict[str, Any]] = {
    "classico": {
        "entry_windows": ((0.0, 35.0), (46.0, 70.0)),
        "max_goals": 1,
        "scratch_s": 120.0,
        "line_offset": 2,
        "entry_mode": "maker",
        "green_ticks": 1,
        "postgol_wait_s": 0.0,
        "hazard_max": 0.085,
        "overshoot_only": False,
    },
    "overshoot": {
        "overshoot_only": True,
        "overshoot_min_s": 30.0,
        "overshoot_max_s": 90.0,
        "entry_windows": None,      # tutta la partita (zone rosse SEMPRE on)
        "max_goals": None,          # si entra DOPO il gol: nessun cap gol
        "scratch_s": 240.0,
        "line_offset": 2,
        # MAKER: identita' della cella CERTIFICATA C17 — il backtest che ha
        # promosso questa pista e' stato misurato con fill maker; il taker
        # "caccia liquidita'" e' del CECCHINO (override per-ingresso), mai un
        # cambio silenzioso della cella campionata (review 16/07)
        "entry_mode": "maker",
        "green_ticks": 1,
        "hazard_max": 0.10,
    },
    # CECCHINO (spec utente 16/07) — i 3 momenti in un bot solo:
    #   STEP 1 pre-match: back Under 2.5 a KO-5' in PERSIST, target adattivo
    #           al fischio (in profitto → tick guadagnati+2; in loss → 1 tick),
    #           esposizione max 5' dal KO accorciata dall'hazard Atlante.
    #   STEP 2 in-play:   scalp da 1 tick nella quiete (gate C7).
    #   STEP 3 post-gol:  overshoot 30-90s dopo il gol, taker sulla liquidita',
    #           scratch accorciato se l'Atlante teme il secondo gol rapido.
    # Filo rosso: presi target_greens verdi, si ferma per la partita.
    "cecchino": {
        "prematch": True,
        "entry_windows": ((0.0, 35.0), (46.0, 70.0)),
        "max_goals": 1,             # (bypass per gli ingressi overshoot)
        "scratch_s": 120.0,
        "line_offset": 2,
        "entry_mode": "maker",      # quiete: maker; overshoot: taker forzato
        "green_ticks": 1,
        "hazard_max": 0.085,
        "overshoot_only": False,
        "overshoot_combo": True,    # quiete E post-gol nella stessa sessione
        "overshoot_min_s": 30.0,
        "overshoot_max_s": 90.0,
        "target_greens": 3,         # cecchino: presi 3 verdi, stop partita
    },
}

# STEP 1 — timeout adattivo dell'esposizione pre-match→in-play: hazard
# Atlante del bucket 0-5' a 0 gol (lega/squadre) → secondi massimi in
# posizione dal KO. Fasce ESPLICITE e testabili (mai formule opache).
PREMATCH_TIMEOUT_STEPS: Tuple[Tuple[float, float], ...] = (
    (0.05, 300.0),   # rischio basso: tutta la finestra (5')
    (0.08, 240.0),
    (0.12, 180.0),
)
PREMATCH_TIMEOUT_FLOOR_S = 120.0   # rischio alto/atlante muto: 2' e fuori


def prematch_timeout_s(p3: Optional[float]) -> float:
    """Secondi massimi di esposizione dal KO per lo STEP 1 (puro)."""
    if p3 is None:
        return PREMATCH_TIMEOUT_FLOOR_S
    for cap, secs in PREMATCH_TIMEOUT_STEPS:
        if p3 <= cap:
            return secs
    return PREMATCH_TIMEOUT_FLOOR_S


def prematch_exit_ticks(entry_price: float, price_at_ko: Optional[float],
                        bonus_ticks: int = 2) -> int:
    """STEP 1 — target ADATTIVO deciso al fischio d'inizio (puro).

    Confronta prezzo d'ingresso e prezzo al KO:
      * gia' in PROFITTO (quota scesa) → si tiene: tick guadagnati + bonus;
      * in pari o in LOSS → ci si accontenta: 1 tick dal prezzo d'ingresso.
    Ritorna il numero di tick SOTTO il prezzo d'ingresso a cui mettere il lay.
    """
    if price_at_ko is None or price_at_ko >= entry_price:
        return 1
    gained = ticks_between(price_at_ko, entry_price)
    if gained is None or gained <= 0:
        return 1
    return int(gained) + max(0, int(bonus_ticks))


# ---------------------------------------------------------------------------
# ATLANTE HAZARD — lookup PURO (testabile senza file/flumine)
# ---------------------------------------------------------------------------
def load_hazard_atlas(path: Optional[str] = None) -> Dict[str, Any]:
    """Carica l'Atlante Hazard dal JSON (2.8MB, una volta per processo)."""
    p = path or ATLAS_DEFAULT_PATH
    with open(p, "r", encoding="utf-8") as fh:
        return json.load(fh)


def hazard_bucket(minute: float) -> str:
    """Bucket 5' dell'Atlante ('0-5' .. '85-90') dal minuto reale."""
    m = max(0, min(89, int(minute)))
    lo = (m // 5) * 5
    return f"{lo}-{lo + 5}"


def hazard_goals_key(goals: int) -> str:
    """Chiave gol dell'Atlante: '0' | '1' | '2' | '3+'."""
    g = max(0, int(goals))
    return "3+" if g >= 3 else str(g)


def _find_team(by_team: Dict[str, Any], name: Optional[str]) -> Optional[dict]:
    """Cerca la squadra PER NOME (case-insensitive). None = fallback lega."""
    if not name:
        return None
    n = str(name).strip().lower()
    for t in by_team.values():
        if str(t.get("team_name", "")).strip().lower() == n:
            return t
    return None


def hazard_lookup(
    atlas: Optional[Dict[str, Any]],
    minute: float,
    goals: int,
    league_id: Optional[Any] = None,
    home_team: Optional[str] = None,
    away_team: Optional[str] = None,
    horizon: str = "p_goal_next_3min",
) -> Tuple[Optional[float], str]:
    """P(gol nei prossimi 3') per lo stato (minuto, gol) — catena meta.lookup.

    1) SQUADRE: entrambe in by_team + lega in by_league →
       f_att(T,b)=att_rate(T,b)/side_rate(lega,b), f_def analogo;
       M(b)=0.5*[fA_att*fB_def + fB_att*fA_def];
       P = 1 - (1 - P_lega(b,g))^M.
    2) LEGA: by_league[league_id].grid (gia' shrinkata).
    3) GLOBALE: atlas['global'].
    Ritorna (p, fonte) con fonte in {'team','league','global','none'};
    (None, 'none') = semaforo ROSSO (fail-closed).
    """
    if not atlas:
        return None, "none"
    b = hazard_bucket(minute)
    gk = hazard_goals_key(goals)
    by_league = atlas.get("by_league") or {}
    lg = by_league.get(str(league_id)) if league_id is not None else None

    # 1) livello SQUADRE (blend moltiplicativo sull'hazard di lega)
    if lg is not None:
        by_team = atlas.get("by_team") or {}
        ta = _find_team(by_team, home_team)
        tb = _find_team(by_team, away_team)
        cell = ((lg.get("grid") or {}).get(b) or {}).get(gk)
        sr = ((lg.get("meta") or {}).get("side_rate_per_bucket") or {}).get(b)
        if ta and tb and cell and sr:
            p_lega = cell.get(horizon)
            if p_lega is not None:
                try:
                    fa_att = float(ta["att_goals_per_match_by_bucket"].get(b, sr)) / sr
                    fa_def = float(ta["def_goals_per_match_by_bucket"].get(b, sr)) / sr
                    fb_att = float(tb["att_goals_per_match_by_bucket"].get(b, sr)) / sr
                    fb_def = float(tb["def_goals_per_match_by_bucket"].get(b, sr)) / sr
                    mult = 0.5 * (fa_att * fb_def + fb_att * fa_def)
                    p = 1.0 - (1.0 - float(p_lega)) ** max(0.0, mult)
                    return p, "team"
                except (KeyError, TypeError, ValueError, ZeroDivisionError):
                    pass  # fallback dichiarato: lega
        # 2) livello LEGA
        if cell is not None and cell.get(horizon) is not None:
            return float(cell[horizon]), "league"

    # 3) livello GLOBALE
    cell = ((atlas.get("global") or {}).get(b) or {}).get(gk)
    if cell is not None and cell.get(horizon) is not None:
        return float(cell[horizon]), "global"
    return None, "none"


def theta_pair(stake: float, entry_price: float,
               green_ticks: int = 1) -> Optional[Dict[str, float]]:
    """Pre-calcolo della COPPIA ATOMICA: entry BACK al best + green LAY a
    -green_ticks tick (default 1) con size compute_green (profitto spalmato
    sui 2 esiti).

    Ritorna None se la coppia non e' costruibile (prezzo al fondo ladder,
    locked non positivo): in quel caso NON si entra (mai gamba senza uscita).
    """
    pe = get_nearest_price(entry_price)
    if not pe or pe <= 1.0:
        return None
    px = price_ticks_away(pe, -max(1, int(green_ticks)))
    if not px or px <= 1.0 or px >= pe:
        return None
    g = compute_green(stake * (pe - 1.0), -stake, px)
    if g is None:
        return None
    side, size, locked = g
    if side != "LAY" or locked <= 0:
        return None
    return {"entry_price": pe, "exit_price": px,
            "exit_size": round(size, 2), "locked": round(locked, 4)}


def in_red_zone(minute: Optional[float]) -> bool:
    """True se il minuto REALE cade nelle zone rosse 40-45' / 80-90'+."""
    if minute is None:
        return True  # orologio ignoto = fail-closed
    m = float(minute)
    return any(lo <= m < hi for lo, hi in ZONE_RED)


# ---------------------------------------------------------------------------
# BUS CONFERME MANUALI (thread-safe, logica pura; il DB lo tocca la sessione)
# ---------------------------------------------------------------------------
@dataclass
class _Proposal:
    local_id: int
    kind: str                     # 'entry' | 'scratch' | 'postgol'
    payload: Dict[str, Any] = field(default_factory=dict)
    status: str = "awaiting"      # awaiting/confirmed/rejected/expired/executed
    db_id: Optional[int] = None
    deadline_ms: float = 0.0
    sent: bool = False            # inserita nel DB dal watcher
    dirty: bool = False           # stato finale da sincronizzare sul DB


class ThetaConfirmBus:
    """Ponte strategia (thread flumine) ↔ watcher DB (thread sessione).

    La strategia PROPONE e POLLA; il watcher fa l'I/O su
    ``theta_confirm_requests``. Il TIMEOUT lo decide il BOT (deadline in ms di
    publish_time): scaduto, la protezione si esegue comunque.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._seq = 0
        self._props: Dict[int, _Proposal] = {}

    # ---- lato STRATEGIA -------------------------------------------------
    def propose(self, kind: str, payload: Dict[str, Any],
                now_ms: float, ttl_s: float) -> int:
        with self._lock:
            self._seq += 1
            self._props[self._seq] = _Proposal(
                local_id=self._seq, kind=str(kind), payload=dict(payload),
                deadline_ms=float(now_ms) + max(1.0, float(ttl_s)) * 1000.0)
            return self._seq

    def check(self, local_id: int, now_ms: float) -> str:
        """Stato corrente; oltre la deadline 'awaiting' diventa 'expired'
        (autorita' del bot, anche se il watcher/DB tace)."""
        with self._lock:
            p = self._props.get(local_id)
            if p is None:
                return "expired"
            if p.status == "awaiting" and float(now_ms) > p.deadline_ms:
                p.status = "expired"
                p.dirty = True
            return p.status

    def finalize(self, local_id: int) -> None:
        """Marca ESEGUITA (il bot ha agito: fuoco o protezione)."""
        with self._lock:
            p = self._props.get(local_id)
            if p is not None:
                p.status = "executed"
                p.dirty = True

    # ---- lato WATCHER (sessione) ----------------------------------------
    def take_unsent(self) -> List[Dict[str, Any]]:
        with self._lock:
            out = []
            for p in self._props.values():
                if not p.sent:
                    p.sent = True
                    out.append({"local_id": p.local_id, "kind": p.kind,
                                "payload": dict(p.payload),
                                "deadline_ms": p.deadline_ms})
            return out

    def attach_db_id(self, local_id: int, db_id: Optional[int]) -> None:
        with self._lock:
            p = self._props.get(local_id)
            if p is not None:
                p.db_id = db_id

    def awaiting_db(self) -> List[Tuple[int, int]]:
        with self._lock:
            return [(p.local_id, p.db_id) for p in self._props.values()
                    if p.status == "awaiting" and p.db_id is not None]

    def apply_db_status(self, local_id: int, status: str) -> None:
        """Applica la decisione UI (confirmed/rejected/expired) se in attesa."""
        if status not in ("confirmed", "rejected", "expired"):
            return
        with self._lock:
            p = self._props.get(local_id)
            if p is not None and p.status == "awaiting":
                p.status = status

    def take_dirty(self) -> List[Tuple[Optional[int], str]]:
        """(db_id, stato finale) da riportare sul DB (expired/executed)."""
        with self._lock:
            out = []
            for p in self._props.values():
                if p.dirty:
                    p.dirty = False
                    out.append((p.db_id, p.status))
            return out


# ---------------------------------------------------------------------------
# STRATEGIA
# ---------------------------------------------------------------------------
class ThetaStrategy(SniperStrategy):
    """BACK Under (gol+2.5) col semaforo Atlante — coppia atomica, poi fuori.

    Gemella di SniperStrategy: EREDITA tutta l'esecuzione certificata live
    (_place/_place_exact/submin, _matched dedup by-identity, _begin/_drive_
    flatten con residuo accettato, riconciliazione ledger↔ordini, _real_net/
    _book_locked del fix bug 1) e SOSTITUISCE cervello e ciclo.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        c = dict(kwargs.pop("theta_params", {}) or {})
        # PRESET S4 ('classico' C7 default | 'overshoot' C17): imposta il
        # pacchetto raccomandato; ogni chiave ESPLICITA in theta_params vince.
        _preset = str(c.get("preset") or "classico").strip().lower()
        self.theta_preset: str = (
            _preset if _preset in THETA_PRESETS else "classico")
        for _k, _v in THETA_PRESETS[self.theta_preset].items():
            c.setdefault(_k, _v)
        # parametri theta → base sniper (esecuzione condivisa). I gate S16
        # dello sniper NON contano: process_market_book e' riscritto qui.
        sniper_params = {
            "stake": max(2.0, min(500.0, float(c.get("stake", 25.0)))),
            "dry_run": bool(c.get("dry_run", True)),
            "exact_exits": bool(c.get("exact_exits", False)),
            "size_step": float(c.get("size_step", 0.0)),
            "live_min_bet": float(c.get("live_min_bet", 0.0)),
            # stop-loss THETA per evento: riusa il cap certificato sniper
            "event_loss_cap": float(c.get("loss_cap", 5.0)),
            # niente missione "primo verde e stop": il tetto e' max_shots
            "profit_target": 0.0,
            "lines": [],
        }
        kwargs["sniper_params"] = sniper_params
        super().__init__(*args, **kwargs)

        # ---- semaforo ----
        self.atlas: Optional[Dict[str, Any]] = c.get("atlas")
        self.hazard_max: float = float(c.get("hazard_max", 0.085))
        self.league_id = c.get("league_id")
        self.home_team: Optional[str] = c.get("home_team")
        self.away_team: Optional[str] = c.get("away_team")
        self.theta_max_spread_ticks: int = int(c.get("max_spread_ticks", 2))
        self.min_back_size: float = float(c.get("min_back_size", 20.0))
        self.theta_price_min: float = float(c.get("price_min", 1.05))
        self.theta_price_max: float = float(c.get("price_max", 3.5))
        # ---- taratura semaforo (S4): SOLO restringono il default ----
        # offset della linea: Under (gol correnti + offset).5 — default 2
        self.theta_line_offset: int = max(1, int(c.get("line_offset", 2)))
        # gol correnti massimi ammessi all'ingresso (None = qualsiasi)
        _mg = c.get("max_goals")
        self.theta_max_goals: Optional[int] = (
            None if _mg is None else max(0, int(_mg)))
        # finestre minuti ammesse all'ingresso, es. [(0,35),(46,70)];
        # None/[] = tutta la partita (le zone rosse restano SEMPRE attive)
        self.theta_entry_windows: Optional[Tuple[Tuple[float, float], ...]] = (
            tuple((float(lo), float(hi))
                  for lo, hi in (c.get("entry_windows") or []))
            or None)
        # green target in tick (default 1 = comportamento certificato)
        self.theta_green_ticks: int = max(1, int(c.get("green_ticks", 1)))
        # modalita' d'ingresso: 'maker' (BACK al best, default) o 'taker'
        # (limite a -taker_ticks dal best: tollera il movimento nel betDelay
        # e matcha al prezzo DISPONIBILE reale, size cap alla liquidita')
        self.theta_entry_mode: str = str(c.get("entry_mode", "maker")).lower()
        self.theta_taker_ticks: int = max(1, int(c.get("taker_ticks", 3)))
        # attesa post-gol prima dell'hedge (0 = immediato, comportamento
        # certificato): T1 dice che l'Under esagera al gol e rientra
        self.theta_postgol_wait_s: float = float(c.get("postgol_wait_s", 0.0))
        self._postgol_seen_ms: Dict[str, float] = {}
        # modalita' OVERSHOOT (cella a se'): ingresso SOLO nella finestra
        # [min_s, max_s] dopo un gol (quota Under gonfiata dal riprezzo,
        # mappa ritardi T1) — in questa modalita' il gate di quiete e'
        # DISATTIVATO by-design (si entra apposta nel post-gol)
        self.theta_overshoot_only: bool = bool(c.get("overshoot_only", False))
        self.theta_overshoot_min_s: float = float(c.get("overshoot_min_s", 30.0))
        self.theta_overshoot_max_s: float = float(c.get("overshoot_max_s", 90.0))
        # CECCHINO: quiete E overshoot nella stessa sessione (STEP 2+3)
        self.theta_overshoot_combo: bool = bool(c.get("overshoot_combo", False))
        # STEP 3: sopra questa soglia di hazard post-gol (secondo gol rapido,
        # Atlante per lega/squadre/stato) lo scratch dell'overshoot si accorcia
        self.theta_overshoot_fast_hazard: float = float(
            c.get("overshoot_fast_hazard", 0.06))
        self.theta_overshoot_scratch_s: float = float(
            c.get("overshoot_scratch_s", 240.0))
        # ---- STEP 1 (cecchino): ingresso PRE-MATCH PERSIST ----
        self.theta_prematch: bool = bool(c.get("prematch", False))
        self.prematch_entry_s: float = float(c.get("prematch_entry_s", 300.0))
        self.prematch_take_s: float = float(c.get("prematch_take_s", 210.0))
        self.prematch_bonus_ticks: int = max(0, int(c.get("prematch_bonus_ticks", 2)))
        self.prematch_price_min: float = float(c.get("prematch_price_min", 1.2))
        self.prematch_price_max: float = float(c.get("prematch_price_max", 4.0))
        self._prematch_done: bool = False
        # ---- filo rosso del cecchino: presi N verdi, stop partita ----
        self.theta_target_greens: int = max(0, int(c.get("target_greens", 0)))
        self._last_goal_ms: Optional[float] = None
        self._now_ms: Optional[float] = None
        # ---- ciclo ----
        # scratch: il preset lo fissa (120s classico / 240s overshoot)
        self.scratch_s: float = float(c.get("scratch_s", 120.0))
        self.theta_max_shots: int = max(1, int(c.get("max_shots", 10)))
        # TTL dell'entry NON fillata (secondi di publish_time): un bid
        # stantio al best e' adverse selection pura (viene preso solo quando
        # il prezzo gli corre contro) → si cancella e lo slot si riarma.
        self.entry_ttl_s: float = float(c.get("entry_ttl_s", 60.0))
        # ---- conferme manuali ----
        self.confirm_mode: bool = bool(c.get("confirm_mode", False))
        self.confirm_ttl_s: float = float(c.get("confirm_ttl_s", 60.0))
        self.confirm_bus = ThetaConfirmBus()
        self._entry_prop: Optional[int] = None
        self._entry_prop_block_ms: float = 0.0   # cooldown post reject/expire
        # ---- stato punteggio/linea ----
        # punteggio: dal watcher di sessione (live) o dalla timeline scores
        # (backtest). None = linea ignota = NIENTE ingressi (fail-closed).
        self.total_goals: Optional[int] = None
        self._inferred_goals: int = 0            # fallback da chiusure OU
        self._closed_ou: set = set()
        # nomi runner dal catalogo (live): {(market_id, selection_id): nome}.
        # L'Under si riconosce PER NOME; fallback sort_priority=1 (replay).
        self._runner_names: Dict[Tuple[str, int], str] = {
            (str(m), int(s)): str(n)
            for (m, s), n in dict(c.get("runner_names") or {}).items()}
        # timeline punteggi per il BACKTEST: [(ts_ms, minute, sh, sa)] sorted
        self._timeline: List[Tuple[int, Optional[int], int, int]] = sorted(
            [tuple(r) for r in (c.get("scores_timeline") or [])],
            key=lambda r: r[0])
        self._timeline_i: int = 0
        # cache hazard per (bucket, gol): l'Atlante cambia solo con lo stato
        self._hazard_cache: Dict[Tuple[str, str], Tuple[Optional[float], str]] = {}
        # mercati con sospensione in-play vista mentre la posizione era aperta
        self._postgol_mids: set = set()

        self.stats.update({
            "shots": 0, "scratches": 0, "postgol_closes": 0,
            "hazard_blocks": 0, "proposals": 0, "confirm_timeouts": 0,
            # STEP 1 (cecchino): telemetria del ciclo pre-match
            "prematch_shots": 0, "prematch_greens": 0, "prematch_scratches": 0,
            "target_greens_hits": 0,
            # --- AUDIT S4-bis: contatori PER-GATE (pura strumentazione, in
            # ordine di cascata; unita' = book-tick del runner target sulla
            # linea target, in-play, senza posizione aperta) ---
            "gate_done": 0, "gate_shots_cap": 0, "gate_no_prices": 0,
            "gate_red_zone": 0, "gate_window": 0, "gate_price": 0,
            "gate_spread": 0, "gate_liquidity": 0, "gate_overshoot_win": 0,
            "gate_quiet": 0, "gate_max_goals": 0, "gate_pair": 0,
            "gate_pass": 0,
        })

    # ------------------------------------------------------------ posizioni
    def _p(self, mid: str, sid: int) -> _ThetaPos:
        """Come SniperStrategy._p ma con _ThetaPos (campi theta dichiarati)."""
        key = (mid, int(sid))
        v = self._pos.get(key)
        if v is None:
            v = _ThetaPos()
            self._pos[key] = v
        return v

    # ------------------------------------------------------------ punteggio
    def set_goals(self, total: Optional[int]) -> None:
        """Punteggio TOTALE dal watcher di sessione (live_now)."""
        if total is None:
            return
        t = int(total)
        if t != self.total_goals:
            # ancora temporale del GOL (per la finestra overshoot): solo
            # incrementi reali, mai l'inizializzazione del punteggio
            if self.total_goals is not None and t > self.total_goals:
                self._last_goal_ms = self._now_ms
            self.total_goals = t
            self._emit("theta_line", goals=t, line=self._target_line())

    def _advance_timeline(self, now_ms: float) -> None:
        """Backtest: applica gli score con ts <= publish_time (no look-ahead)."""
        while (self._timeline_i < len(self._timeline)
               and self._timeline[self._timeline_i][0] <= now_ms):
            _ts, minute, sh, sa = self._timeline[self._timeline_i]
            self._timeline_i += 1
            if minute is not None:
                self.live_minute = float(minute)
            self.set_goals(int(sh) + int(sa))

    def _goals(self) -> Optional[int]:
        if self.total_goals is not None:
            return self.total_goals
        # fallback (solo replay senza timeline): inferenza dalle chiusure OU
        return self._inferred_goals if self._closed_ou else None

    def _target_line(self) -> Optional[str]:
        """Linea d'ingresso: Under (gol correnti + offset).5 — mai oltre
        la 8.5. L'offset (default 2) e' parametrico (taratura S4)."""
        g = self._goals()
        if g is None:
            return None
        n = g + self.theta_line_offset
        return f"OVER_UNDER_{n}5" if n <= 8 else None

    def _match_minute(self, el: Optional[float]) -> Optional[float]:
        """Minuto REALE: live_now.minute (watcher/timeline) se disponibile;
        fallback elapsed-KO con correzione intervallo (bug 6 noto: marketTime
        conta anche l'HT → oltre il 45' si sottraggono ~15')."""
        if self.live_minute is not None:
            return float(self.live_minute)
        if el is None:
            return None
        m = el / 60.0
        return m if m <= 45.0 else max(45.0, m - 15.0)

    def _hazard(self, minute: float, goals: int) -> Tuple[Optional[float], str]:
        key = (hazard_bucket(minute), hazard_goals_key(goals))
        hit = self._hazard_cache.get(key)
        if hit is None:
            hit = hazard_lookup(self.atlas, minute, goals, self.league_id,
                                self.home_team, self.away_team)
            self._hazard_cache[key] = hit
        return hit

    def _is_under(self, mb: Any, runner: Any) -> bool:
        """Under PER NOME dal catalogo; fallback sort_priority=1 (replay)."""
        name = self._runner_names.get(
            (str(mb.market_id), int(runner.selection_id)))
        if name:
            return name.strip().lower().startswith("under")
        return self._is_target(mb, runner)

    # -------------------------------------------------------------- flumine
    def check_market_book(self, market: Any, market_book: Any) -> bool:
        st = getattr(market_book, "status", None)
        if st != "OPEN":
            # gol → tutti i mercati SUSPENDED: arma il semaforo condiviso e
            # marca il post-gol per le posizioni aperte su questo mercato
            notice_suspension(self.risk_sem, market_book)
            if (st == "SUSPENDED" and getattr(market_book, "inplay", False)
                    and self._has_exposure(market_book.market_id)):
                self._postgol_mids.add(str(market_book.market_id))
                # prima sospensione vista: ancora dell'attesa postgol_wait_s
                self._postgol_seen_ms.setdefault(
                    str(market_book.market_id),
                    float(getattr(market_book, "publish_time_epoch", 0) or 0))
            return False
        if not getattr(market_book, "runners", None):
            return False
        md = getattr(market_book, "market_definition", None)
        mtype = (getattr(md, "market_type", None)
                 or getattr(market, "market_type", None))
        # tutti gli OU passano: la linea target si sposta coi gol e le
        # posizioni residue su linee vecchie restano gestite fino al flat
        return str(mtype or "").startswith("OVER_UNDER")

    def _has_exposure(self, market_id: str) -> bool:
        for (mid, _sid), pos in self._pos.items():
            if mid != market_id:
                continue
            if pos.entries or pos.flattening or pos.submins:
                return True
        return False

    def process_closed_market(self, market: Any, market_book: Any) -> None:
        # inferenza gol di FALLBACK (replay senza timeline): la chiusura
        # in-play di OVER_UNDER_n5 implica >= n+1 gol. A fine partita tutto
        # chiude insieme: irrilevante, non si entra piu' comunque.
        md = getattr(market_book, "market_definition", None)
        mtype = str(getattr(md, "market_type", "") or "")
        if (mtype.startswith("OVER_UNDER") and len(mtype) >= 12
                and market_book.market_id not in self._closed_ou):
            self._closed_ou.add(market_book.market_id)
            try:
                n = int(mtype.rsplit("_", 1)[1][:-1])  # 'OVER_UNDER_25' -> 2
                self._inferred_goals = max(self._inferred_goals, n + 1)
            except (ValueError, IndexError):
                pass
        super().process_closed_market(market, market_book)

    # ------------------------------------------------------------- processo
    def process_market_book(self, market: Any, market_book: Any) -> None:  # noqa: C901
        now = getattr(market_book, "publish_time_epoch", None)
        if now is None:
            return
        self._now_ms = float(now)
        self._advance_timeline(float(now))
        mid = market_book.market_id
        md = getattr(market_book, "market_definition", None)
        mtype = getattr(md, "market_type", None)
        inplay = bool(getattr(market_book, "inplay", False))
        ko = self._ko_epoch_ms(market_book)
        el = (now - ko) / 1000.0 if ko else None
        target = self._target_line()
        postgol_here = str(mid) in self._postgol_mids

        for runner in market_book.runners:
            if getattr(runner, "status", None) != "ACTIVE":
                continue
            if not self._is_under(market_book, runner):
                continue
            ex = getattr(runner, "ex", None)
            if ex is None:
                continue
            bb = get_price(ex.available_to_back, 0)
            bl = get_price(ex.available_to_lay, 0)
            sb = get_size(ex.available_to_back, 0)
            pos = self._p(mid, int(runner.selection_id))
            # sequenze exact (park-trim-replace) SEMPRE avanti per prime
            self._drive_submins(market, pos)

            # RICONCILIAZIONE ledger↔ordini (rete certificata sniper 11/07)
            if not pos.entries and not pos.flattening and not pos.submins:
                sb0, ob0, sl0, ol0 = self._matched(pos.flatten_orders)
                nw0 = sb0 * (ob0 - 1.0) - sl0 * (ol0 - 1.0)
                nl0 = sl0 - sb0
                if abs(nw0 - nl0) > max(0.30, pos.residual_accepted + 0.02):
                    self.stats["ledger_divergences"] += 1
                    self._emit("ledger_divergence", level="CRITICAL",
                               nw=round(nw0, 2), nl=round(nl0, 2),
                               n=int(self.stats["ledger_divergences"]))
                    if (self.stats["ledger_divergences"] >= 3
                            and not self.force_flat):
                        self._emit("recon_freeze", level="CRITICAL",
                                   msg="divergenze ledger ripetute: FREEZE "
                                       "sessione theta (force-flat)")
                        self.force_flat = True
                    self._begin_flatten(market, pos)
                    self._drive_flatten(market, pos, bb, bl, now)
                    continue

            if pos.flattening:
                self._drive_flatten(market, pos, bb, bl, now)
                if not pos.flattening and postgol_here:
                    self._postgol_mids.discard(str(mid))
                    self._postgol_seen_ms.pop(str(mid), None)
                continue

            if pos.entries:
                if pos.prematch:
                    self._manage_prematch(market, market_book, runner, pos,
                                          bb, bl, float(now), ko, inplay,
                                          postgol_here)
                else:
                    self._manage_open(market, market_book, runner, pos,
                                      bb, bl, float(now), el, postgol_here)
                continue

            # ---- NESSUNA posizione ----
            if not inplay:
                # STEP 1 (cecchino): finestra PRE-MATCH KO-5' su Under 2.5
                if (self.theta_prematch and not self._prematch_done
                        and str(mtype or "") == "OVER_UNDER_25"
                        and ko is not None):
                    self._prematch_entry_tick(market, runner, pos, bb, bl,
                                              float(sb or 0.0), float(now),
                                              float(ko))
                continue
            # ---- semaforo d'ingresso in-play (STEP 2 quiete / STEP 3 post-gol)
            if mtype != target or target is None:
                continue  # spara SOLO la linea target (gol correnti + 2.5)
            if (self.force_flat or self._event_done or self._loss_capped()):
                self.stats["gate_done"] += 1
                continue
            if self.stats["shots"] >= self.theta_max_shots:
                self.stats["gate_shots_cap"] += 1
                continue
            if bb is None or bl is None:
                self.stats["gate_no_prices"] += 1
                continue
            minute = self._match_minute(el)
            if in_red_zone(minute):
                self.stats["gate_red_zone"] += 1
                continue
            # finestra OVERSHOOT (STEP 3): sempre calcolata — nel combo un
            # ingresso post-gol bypassa finestre/quiete/max_goals by-design
            # (si compra il riprezzo, non la quiete)
            in_overshoot = False
            if self._last_goal_ms is not None:
                dt_s = (float(now) - self._last_goal_ms) / 1000.0
                in_overshoot = (self.theta_overshoot_min_s <= dt_s
                                <= self.theta_overshoot_max_s)
            overshoot_entry = in_overshoot and (
                self.theta_overshoot_only or self.theta_overshoot_combo)
            if self.theta_overshoot_only and not in_overshoot:
                self.stats["gate_overshoot_win"] += 1
                continue
            # finestra minuti parametrica (S4): fuori finestra = rosso
            if (self.theta_entry_windows is not None and not overshoot_entry
                    and not any(lo <= float(minute) < hi
                                for lo, hi in self.theta_entry_windows)):
                self.stats["gate_window"] += 1
                continue
            if not (self.theta_price_min <= bb <= self.theta_price_max):
                self.stats["gate_price"] += 1
                continue
            spr = ticks_between(bb, bl)
            if spr is None or spr > self.theta_max_spread_ticks:
                self.stats["gate_spread"] += 1
                continue
            if (sb or 0.0) < self.min_back_size:
                self.stats["gate_liquidity"] += 1
                continue
            # QUIETE: nessuna sospensione recente (semaforo condiviso evento)
            # — un ingresso overshoot la bypassa (entra APPOSTA nel post-gol)
            if (not overshoot_entry and self.risk_sem is not None
                    and self.risk_sem.entries_halted(now)):
                self.stats["gate_quiet"] += 1
                continue
            # HAZARD Atlante (fail-closed: cella ignota = rosso)
            g = self._goals()
            # gol correnti massimi parametrici (S4): oltre = rosso (gli
            # ingressi overshoot non lo contano: il gol e' appena arrivato)
            if (not overshoot_entry and self.theta_max_goals is not None
                    and int(g) > self.theta_max_goals):
                self.stats["gate_max_goals"] += 1
                continue
            p3, src = self._hazard(minute, int(g))
            if p3 is None or p3 > self.hazard_max:
                self.stats["hazard_blocks"] += 1
                continue
            # COPPIA ATOMICA pre-calcolata: senza uscita valida NON si entra
            pair = theta_pair(self.stake, bb, self.theta_green_ticks)
            if pair is None:
                self.stats["gate_pair"] += 1
                continue
            self.stats["gate_pass"] += 1
            # STEP 3: entry TAKER sulla liquidita' per l'overshoot; scratch
            # accorciato se l'Atlante teme il secondo gol rapido (post-gol
            # l'hazard e' gia' calcolato sullo stato NUOVO del punteggio)
            entry_mode = "taker" if overshoot_entry else self.theta_entry_mode
            scratch_override = None
            if overshoot_entry:
                # _EPS: 1-(1-p)^1 in float puo' superare p di 1e-17 — mai
                # accorciare lo scratch per un errore di rappresentazione
                scratch_override = (
                    120.0 if float(p3) > self.theta_overshoot_fast_hazard + _EPS
                    else self.theta_overshoot_scratch_s)
            ctx = {"price": pair["entry_price"],
                   "size": (round(min(self.stake, float(sb or 0.0)), 2)
                            if entry_mode == "taker"
                            else self.stake),
                   "exit_price": pair["exit_price"],
                   "exit_size": pair["exit_size"],
                   "locked": pair["locked"], "line": target,
                   "minute": round(float(minute), 1),
                   "hazard_p3": round(float(p3), 4), "hazard_src": src,
                   "entry_mode": entry_mode,
                   "overshoot": bool(overshoot_entry),
                   "scratch_s": scratch_override}
            if not self._entry_go(float(now), ctx):
                continue
            self._fire_theta(market, runner, pos, ctx, float(now))

    # ------------------------------------------------------ gestione ciclo
    def _manage_open(self, market: Any, market_book: Any, runner: Any,
                     pos: _ThetaPos, bb: Optional[float], bl: Optional[float],
                     now: float, el: Optional[float],
                     postgol_here: bool) -> None:
        filled = sum(float(getattr(o, "size_matched", 0.0) or 0.0)
                     for o in pos.entries)
        if filled <= 0:
            # entry non ancora toccata: post-gol/force-flat → via subito
            if postgol_here or self.force_flat:
                self._begin_flatten(market, pos)
                self._postgol_mids.discard(str(market_book.market_id))
                self._postgol_seen_ms.pop(str(market_book.market_id), None)
                return
            # TTL entry: un bid al best rimasto scoperto oltre entry_ttl_s
            # si cancella (adverse selection: verrebbe preso solo quando il
            # prezzo gli corre contro). Slot riarmabile appena confermato
            # che nulla e' vivo/matchato.
            placed = pos.entry_placed_pt
            if placed is not None and now - placed > self.entry_ttl_s * 1000.0:
                for o in pos.entries:
                    self._cancel_if_live(market, o)
                if (not any(self._has_live(o) for o in pos.entries)
                        and sum(float(getattr(o, "size_matched", 0.0) or 0.0)
                                for o in pos.entries) <= 0):
                    self._emit("theta_entry_ttl",
                               ttl_s=round((now - placed) / 1000.0, 1))
                    pos.entries = []
                    pos.entry_odds = None
            return
        if pos.entry_fill_pt is None:
            pos.entry_fill_pt = now
        # COPPIA ATOMICA: al primo fill il residuo entry si cancella (mai
        # esposizione oltre il matchato) e il green parte IMMEDIATO
        for o in pos.entries:
            self._cancel_if_live(market, o)

        # ---- VERDE: close morta con matched -> net REALE (fix bug 1) ----
        if (pos.close is not None and not self._has_live(pos.close)
                and float(getattr(pos.close, "size_matched", 0.0) or 0.0) > 0
                and not pos.submins):
            nw_r, nl_r = self._real_net(pos)
            if abs(nw_r - nl_r) > max(0.02, pos.residual_accepted + 0.02):
                # close PARZIALE (es. LAPSE a sospensione-gol): NON e' verde
                self._emit("theta_close_partial", level="WARN",
                           nw=round(nw_r, 3), nl=round(nl_r, 3))
                self._begin_flatten(market, pos)
                self._drive_flatten(market, pos, bb, bl, now)
                return
            locked = self._book_locked(pos, nw_r, nl_r)
            self.stats["greens"] += 1
            self.stats["pnl_locked"] += locked
            self._close_cycle_clock(pos, now)
            self._emit("theta_green", locked=round(locked, 3),
                       minute=self._minute(el))
            for o_t in pos.entries:
                self._track(pos, o_t)
            self._track(pos, pos.close)
            pos.entries = []
            pos.close = None
            pos.close_locked = 0.0
            pos.entry_odds = None
            pos.pending_protect = None
            pos.scratch_override_s = None
            self._loss_capped()
            self._check_target_greens()
            return

        # ---- POST-GOL: chiusura al riprezzo (protezione, confermabile) ----
        if postgol_here or self.force_flat:
            # FIX S6 (review 15/07): la close resting e' al prezzo PRE-gol,
            # dopo il riprezzo e' irraggiungibile = copertura FINTA. Si
            # cancella SUBITO, a prescindere da confirm_mode/attesa T1; la
            # protezione a conferma/timeout resta INVARIATA e l'attesa a
            # posizione scoperta finisce in telemetria esplicita.
            stale_close = pos.close is not None and self._has_live(pos.close)
            if stale_close:
                self._cancel_if_live(market, pos.close)
            # attesa parametrica del rientro dall'overshoot (T1): l'hedge
            # parte solo dopo postgol_wait_s dalla sospensione-gol
            if not self.force_flat and self.theta_postgol_wait_s > 0:
                seen = self._postgol_seen_ms.get(
                    str(market_book.market_id))
                if (seen is not None and now - seen
                        < self.theta_postgol_wait_s * 1000.0):
                    if stale_close:
                        self._emit("theta_exposed_awaiting", level="WARN",
                                   reason="postgol_wait: close pre-gol "
                                          "cancellata, posizione scoperta",
                                   best_back=bb, best_lay=bl)
                    return
            if self.force_flat or self._protect_go(pos, "postgol", now, {
                    "reason": "sospensione in-play (gol)",
                    "best_back": bb, "best_lay": bl}):
                self.stats["postgol_closes"] += 1
                self._emit("theta_postgol_flat", best_back=bb, best_lay=bl)
                self._begin_flatten(market, pos)
                self._drive_flatten(market, pos, bb, bl, now)
                self._postgol_mids.discard(str(market_book.market_id))
                self._postgol_seen_ms.pop(str(market_book.market_id), None)
            elif stale_close:
                self._emit("theta_exposed_awaiting", level="WARN",
                           reason="attesa conferma manuale: close pre-gol "
                                  "cancellata, posizione scoperta",
                           best_back=bb, best_lay=bl)
            return

        # ---- SCRATCH TIMER (secondi di publish_time, mai conteggi book) ----
        # per-ingresso (STEP 3): l'overshoot ha il suo scratch, accorciato se
        # l'Atlante teme il secondo gol rapido; default = scratch_s strategia
        scratch_s = pos.scratch_override_s or self.scratch_s
        if (pos.entry_fill_pt is not None
                and now - pos.entry_fill_pt > scratch_s * 1000.0):
            if self._protect_go(pos, "scratch", now, {
                    "pos_s": round((now - pos.entry_fill_pt) / 1000.0, 1),
                    "best_back": bb, "best_lay": bl}):
                self.stats["scratches"] += 1
                self._emit("theta_scratch",
                           pos_s=round((now - pos.entry_fill_pt) / 1000.0, 1))
                self._begin_flatten(market, pos)
                self._drive_flatten(market, pos, bb, bl, now)
            return

        # ---- GREEN IMMEDIATO al fill: LAY a -1 tick dal prezzo REALE ----
        if pos.close is None:
            sb_m, ob, sl_m, ol = self._matched(pos.entries)
            if ob and ob > 1.0:
                price = price_ticks_away(get_nearest_price(ob),
                                         -self.theta_green_ticks)
                if price and price > 1.0:
                    nw = sb_m * (ob - 1.0) - sl_m * (ol - 1.0)
                    nl = sl_m - sb_m
                    g = compute_green(nw, nl, price)
                    if g is not None:
                        side, size, locked = g
                        o = self._place(market, runner.selection_id, side,
                                        price, size, floor=False, pos=pos)
                        if o is not None:
                            pos.close = o
                            pos.close_locked = locked

    # ------------------------------------------------------------- conferme
    def _entry_go(self, now: float, ctx: Dict[str, Any]) -> bool:
        """AUTO: sempre True. MANUALE: propone e attende; confermata → True
        (prezzi FRESCHI del tick corrente); rifiutata/scaduta → scarta."""
        if not self.confirm_mode:
            return True
        if self._entry_prop is None:
            if now < self._entry_prop_block_ms:
                return False
            self._entry_prop = self.confirm_bus.propose(
                "entry", ctx, now, self.confirm_ttl_s)
            self.stats["proposals"] += 1
            self._emit("theta_proposal", action="entry", **ctx)
            return False
        st = self.confirm_bus.check(self._entry_prop, now)
        if st == "awaiting":
            return False
        if st == "confirmed":
            self.confirm_bus.finalize(self._entry_prop)
            self._entry_prop = None
            return True
        # rejected/expired: l'ENTRY si scarta (non e' una protezione)
        if st == "expired":
            self.stats["confirm_timeouts"] += 1
        self._emit("theta_entry_dropped", status=st)
        self._entry_prop = None
        self._entry_prop_block_ms = now + 30_000.0
        return False

    def _protect_go(self, pos: _ThetaPos, kind: str, now: float,
                    ctx: Dict[str, Any]) -> bool:
        """PROTEZIONE (scratch/post-gol). AUTO: subito. MANUALE: propone e
        attende MAX confirm_ttl_s; POI SI ESEGUE COMUNQUE (mai posizione
        nuda) — anche su reject: la conferma e' solo un via-libera."""
        if not self.confirm_mode:
            return True
        pending = pos.pending_protect
        if pending is None:
            pos.pending_protect = self.confirm_bus.propose(
                kind, ctx, now, self.confirm_ttl_s)
            self.stats["proposals"] += 1
            self._emit("theta_proposal", action=kind, **ctx)
            return False
        st = self.confirm_bus.check(pending, now)
        if st == "awaiting":
            return False
        if st == "expired":
            self.stats["confirm_timeouts"] += 1
        if st == "rejected":
            self._emit("theta_protect_override", level="WARN", action=kind,
                       msg="reject ignorato: la protezione si esegue comunque")
        self.confirm_bus.finalize(pending)
        pos.pending_protect = None
        return True

    # -------------------------------------------------- filo rosso cecchino
    def _check_target_greens(self) -> None:
        """Presi ``target_greens`` verdi (tutti gli step), STOP partita:
        il cecchino ha fatto i suoi tick — niente overtrading (spec 16/07)."""
        if (self.theta_target_greens > 0 and not self._event_done
                and int(self.stats.get("greens", 0)) >= self.theta_target_greens):
            self._event_done = True
            self.stats["target_greens_hits"] += 1
            self._emit("theta_target_greens_hit",
                       greens=int(self.stats.get("greens", 0)),
                       pnl_locked=round(float(self.stats.get("pnl_locked", 0.0)), 3))

    # ------------------------------------------- STEP 1: pre-match PERSIST
    @staticmethod
    def _reset_prematch(pos: _ThetaPos) -> None:
        """Chiude il CICLO pre-match sulla posizione (backtest 16/07: senza
        questo reset il flag restava e i cicli standard successivi sullo
        stesso runner finivano nel gestore pre-match — timeout gia' scaduto
        → flatten immediato a ripetizione + divergenze ledger)."""
        pos.prematch = False
        pos.prematch_exit_placed = False
        pos.prematch_deadline_ms = None
        pos.prematch_taken = False
        pos.prematch_take_placed = False

    def _prematch_entry_tick(self, market: Any, runner: Any, pos: _ThetaPos,
                             bb: Optional[float], bl: Optional[float],
                             sb: float, now: float, ko_ms: float) -> None:
        """Ingresso PRE-MATCH (spec cecchino 16/07): a KO−prematch_entry_s
        back Under 2.5 in PERSIST (regge il turn in-play); se a
        KO−prematch_take_s non e' fillato, escalation TAKER (attraversa lo
        spread); il target e il timeout si decidono al KO (_manage_prematch).
        UNA sola finestra per partita (_prematch_done)."""
        left_s = (ko_ms - now) / 1000.0
        if left_s <= 0 or left_s > self.prematch_entry_s:
            return
        if self.force_flat or self._event_done or self._loss_capped():
            return
        if bb is None or bl is None:
            return
        if not (self.prematch_price_min <= bb <= self.prematch_price_max):
            return
        spr = ticks_between(bb, bl)
        if spr is None or spr > self.theta_max_spread_ticks:
            return
        if sb < self.min_back_size:
            return
        if self.dry_run:
            # demo del cervello: UN solo annuncio per finestra
            self._prematch_done = True
            self.stats["dry_fires"] += 1
            self._emit("theta_prematch_dry", price=bb, size=self.stake,
                       left_s=round(left_s, 1))
            return
        o = self._place(market, runner.selection_id, "BACK", bb, self.stake,
                        pos=pos, persistence="PERSIST")
        if o is not None:
            pos.entries.append(o)
            pos.prematch = True
            pos.entry_odds = bb
            pos.entry_placed_pt = now
            self._prematch_done = True
            self.stats["prematch_shots"] += 1
            self.stats["shots"] += 1
            self.stats["entries"] += 1
            self._emit("theta_prematch_fire", price=bb, size=self.stake,
                       left_s=round(left_s, 1))

    def _manage_prematch(self, market: Any, market_book: Any, runner: Any,
                         pos: _ThetaPos, bb: Optional[float],
                         bl: Optional[float], now: float,
                         ko_ms: Optional[float], inplay: bool,
                         postgol_here: bool) -> None:
        """Ciclo STEP 1 dopo il fuoco pre-match (review 16/07 incorporata).

        PRE-KO:  kill-switch attivo ANCHE qui (force_flat/event_done/loss_cap
                 → cancel/flat, mai nuovi ordini); se non fillato a
                 KO−prematch_take_s → escalation in DUE FASI (prima cancel,
                 poi — a cancel confermato e zero matched — taker SOTTO il
                 best back: un limite basso matcha al prezzo disponibile).
        AL KO:   residuo PERSIST ri-cancellato a OGNI book; DEADLINE armata
                 SUBITO col primo fill (mai posizione senza timeout); col
                 matched si calcola il TARGET ADATTIVO (prematch_exit_ticks)
                 e si piazza il lay; se la close muore senza matched (LAPSE a
                 una sospensione ignorata) si RIPIAZZA.
        GOL:     FAIL-CLOSED — l'unica sospensione ignorabile e' il turn
                 in-play (entro 45s dal KO e punteggio NOTO 0-0); punteggio
                 ignoto o sospensione tardiva → flat al riprezzo.
        """
        filled = sum(float(getattr(o, "size_matched", 0.0) or 0.0)
                     for o in pos.entries)

        # ---- PRE-KO ------------------------------------------------------
        if not inplay:
            # kill-switch anche pre-KO (review 16/07: prima il force-flat era
            # ignorato e l'escalation piazzava PERSIST NUOVI dopo lo stop)
            if self.force_flat or self._event_done or self._loss_capped():
                for o in pos.entries:
                    self._cancel_if_live(market, o)
                if filled > 0:
                    self._begin_flatten(market, pos)
                    self._drive_flatten(market, pos, bb, bl, now)
                    self._reset_prematch(pos)
                elif not any(self._has_live(o) for o in pos.entries):
                    pos.entries = []
                    pos.entry_odds = None
                    self._reset_prematch(pos)
                return
            if filled <= 0 and ko_ms is not None:
                left_s = (ko_ms - now) / 1000.0
                if left_s <= self.prematch_take_s:
                    # ESCALATION IN DUE FASI (review: cancel+place nello
                    # stesso tick = rischio doppio fill sul PERSIST)
                    if not pos.prematch_taken:
                        for o in pos.entries:
                            self._cancel_if_live(market, o)
                        pos.prematch_taken = True
                        return
                    if pos.prematch_take_placed:
                        return
                    if any(self._has_live(o) for o in pos.entries):
                        return          # cancel non ancora confermato
                    f2 = sum(float(getattr(o, "size_matched", 0.0) or 0.0)
                             for o in pos.entries)
                    if f2 > 0:
                        return          # fillato durante il cancel: piano al KO
                    if bb is None:
                        return
                    # TAKE vero: BACK con limite SOTTO il best back → matcha
                    # subito al prezzo DISPONIBILE (review: al best lay
                    # restava maker sopra il book, il contrario di un take)
                    px = price_ticks_away(get_nearest_price(bb),
                                          -self.theta_taker_ticks)
                    if not px or px <= 1.0:
                        return
                    pos.entries = []
                    o = self._place(market, runner.selection_id, "BACK", px,
                                    self.stake, pos=pos, persistence="PERSIST")
                    if o is not None:
                        pos.entries.append(o)
                        pos.entry_odds = bb
                        pos.prematch_take_placed = True
                        self._emit("theta_prematch_take", price=px, ref_bb=bb,
                                   left_s=round(left_s, 1))
            return

        # ---- IN-PLAY -------------------------------------------------------
        # kill-switch PRIMA di ogni piano (review): in force-flat non si
        # piazzano close, si smonta e basta
        if self.force_flat:
            for o in pos.entries:
                self._cancel_if_live(market, o)
            if pos.close is not None and self._has_live(pos.close):
                self._cancel_if_live(market, pos.close)
            self._begin_flatten(market, pos)
            self._drive_flatten(market, pos, bb, bl, now)
            self._reset_prematch(pos)
            return

        # residuo PERSIST ri-cancellato a OGNI book (review: un singolo
        # cancel puo' fallire/racere e il PERSIST continuerebbe a matchare)
        for o in pos.entries:
            self._cancel_if_live(market, o)

        if filled <= 0:
            # nessun fill pre-match: finestra chiusa, niente inseguimenti
            if not any(self._has_live(o) for o in pos.entries):
                self._emit("theta_prematch_unfilled")
                pos.entries = []
                pos.entry_odds = None
                self._reset_prematch(pos)
            return
        if pos.entry_fill_pt is None:
            pos.entry_fill_pt = now

        # DEADLINE ARMATA SUBITO col fill (review: prima nasceva solo con la
        # close piazzata — una close impossibile = posizione senza timeout)
        if pos.prematch_deadline_ms is None:
            p3, src = self._hazard(0.0, 0)
            timeout = prematch_timeout_s(p3)
            base = float(ko_ms) if ko_ms is not None else now
            pos.prematch_deadline_ms = base + timeout * 1000.0
            self._emit("theta_prematch_deadline", timeout_s=timeout,
                       hazard_p3=(round(float(p3), 4) if p3 is not None
                                  else None), hazard_src=src)

        # ---- VERDE: close morta con matched → net REALE (fix bug 1) ----
        if pos.close is not None and not self._has_live(pos.close):
            close_matched = float(
                getattr(pos.close, "size_matched", 0.0) or 0.0)
            if close_matched > 0 and not pos.submins:
                nw_r, nl_r = self._real_net(pos)
                if abs(nw_r - nl_r) > max(0.02, pos.residual_accepted + 0.02):
                    self._emit("theta_close_partial", level="WARN",
                               nw=round(nw_r, 3), nl=round(nl_r, 3))
                    self._begin_flatten(market, pos)
                    self._drive_flatten(market, pos, bb, bl, now)
                    self._reset_prematch(pos)
                    return
                locked = self._book_locked(pos, nw_r, nl_r)
                self.stats["greens"] += 1
                self.stats["prematch_greens"] += 1
                self.stats["pnl_locked"] += locked
                self._close_cycle_clock(pos, now)
                self._emit("theta_prematch_green", locked=round(locked, 3))
                for o_t in pos.entries:
                    self._track(pos, o_t)
                self._track(pos, pos.close)
                pos.entries = []
                pos.close = None
                pos.close_locked = 0.0
                pos.entry_odds = None
                self._reset_prematch(pos)
                self._loss_capped()
                self._check_target_greens()
                return
            if close_matched <= 0:
                # close morta SENZA matched (LAPSE a sospensione ignorata):
                # il piano si RIPIAZZA (review: mai posizione senza uscita)
                self._emit("theta_prematch_close_dead")
                pos.close = None
                pos.close_locked = 0.0
                pos.prematch_exit_placed = False

        # GOL: FAIL-CLOSED (review). Ignorabile SOLO il turn in-play: entro
        # 45s dal KO e punteggio NOTO 0-0. Feed muto/in ritardo o sospensione
        # tardiva (VAR/rosso) → flat al riprezzo, come il ciclo certificato.
        if postgol_here:
            g = self._goals()
            in_ko_grace = (ko_ms is not None
                           and now - float(ko_ms) <= 45_000.0)
            if g is not None and int(g) == 0 and in_ko_grace:
                self._postgol_mids.discard(str(market_book.market_id))
                self._postgol_seen_ms.pop(str(market_book.market_id), None)
            else:
                if pos.close is not None and self._has_live(pos.close):
                    self._cancel_if_live(market, pos.close)
                self.stats["postgol_closes"] += 1
                self._emit("theta_prematch_postgol_flat",
                           best_back=bb, best_lay=bl)
                self._begin_flatten(market, pos)
                self._drive_flatten(market, pos, bb, bl, now)
                self._postgol_mids.discard(str(market_book.market_id))
                self._postgol_seen_ms.pop(str(market_book.market_id), None)
                self._reset_prematch(pos)
                return

        # TIMEOUT: esposizione massima dal KO raggiunta → si esce al meglio
        if (pos.prematch_deadline_ms is not None
                and now > pos.prematch_deadline_ms):
            if pos.close is not None and self._has_live(pos.close):
                self._cancel_if_live(market, pos.close)
            self.stats["scratches"] += 1
            self.stats["prematch_scratches"] += 1
            self._emit("theta_prematch_timeout")
            self._begin_flatten(market, pos)
            self._drive_flatten(market, pos, bb, bl, now)
            self._reset_prematch(pos)
            return

        # ---- PIANO: target adattivo (si (ri)piazza finche' manca) ----
        if not pos.prematch_exit_placed:
            sb_m, ob, sl_m, ol = self._matched(pos.entries)
            if not ob or ob <= 1.0:
                return
            # TARGET ADATTIVO al fischio: riferimento = best back attuale
            # (il prezzo a cui il mercato ci ricomprerebbe subito)
            t_ticks = prematch_exit_ticks(ob, bb, self.prematch_bonus_ticks)
            price = price_ticks_away(get_nearest_price(ob), -t_ticks)
            if not price or price <= 1.0:
                # fondo ladder: si esce al meglio (mai posizione senza piano)
                self._begin_flatten(market, pos)
                self._drive_flatten(market, pos, bb, bl, now)
                self._reset_prematch(pos)
                return
            nw = sb_m * (ob - 1.0) - sl_m * (ol - 1.0)
            nl = sl_m - sb_m
            g2 = compute_green(nw, nl, price)
            if g2 is None:
                self._begin_flatten(market, pos)
                self._drive_flatten(market, pos, bb, bl, now)
                self._reset_prematch(pos)
                return
            side, size, locked = g2
            o = self._place(market, runner.selection_id, side, price, size,
                            floor=False, pos=pos)
            if o is None:
                return  # riprova al prossimo book (la DEADLINE e' gia' armata)
            pos.close = o
            pos.close_locked = locked
            pos.prematch_exit_placed = True
            self._emit("theta_prematch_exit_plan",
                       entry=ob, target_price=price, target_ticks=t_ticks,
                       ref_bb=bb)
            return

    # ----------------------------------------------------------------- fuoco
    def _fire_theta(self, market: Any, runner: Any, pos: _ThetaPos,
                    ctx: Dict[str, Any], now: float) -> None:
        price = ctx["price"]
        if self.dry_run:
            key = (market.market_id, int(runner.selection_id))
            if now - self._dry_last_fire.get(key, 0.0) < 120_000.0:
                return
            self._dry_last_fire[key] = now
            self.stats["dry_fires"] += 1
            self._emit("theta_dry_fire", **ctx)
            return
        size = max(0.0, float(ctx.get("size") or self.stake))
        if size <= 0.0:
            return
        # modalita' PER-INGRESSO (cecchino: quiete=maker, overshoot=taker)
        entry_mode = str(ctx.get("entry_mode") or self.theta_entry_mode)
        if entry_mode == "taker":
            # TAKER: limite a -taker_ticks dal best → tollera il movimento
            # nel betDelay e matcha al prezzo DISPONIBILE (best execution)
            lp = price_ticks_away(get_nearest_price(price),
                                  -self.theta_taker_ticks)
            if lp and lp > 1.0:
                price = lp
        o = self._place(market, runner.selection_id, "BACK", price, size)
        if o is not None:
            self._track(pos, o)         # anti-orfani: entry sotto blanket-cancel
            pos.entries.append(o)
            pos.entry_odds = price
            pos.entry_placed_pt = now   # ancora del TTL entry
            pos.pending_protect = None
            # STEP 3: scratch accorciato per l'overshoot col rischio 2° gol
            pos.scratch_override_s = (
                float(ctx["scratch_s"]) if ctx.get("scratch_s") else None)
            self.stats["shots"] += 1
            self.stats["entries"] += 1
            self._emit("theta_fire", **ctx)
