"""engine — logica PURA del bot Mike (COSTITUZIONE_MIKE.md §2).

Zero I/O: nessun DB, nessuna rete, nessun flumine (solo la ladder ufficiale
per i tick). Tutto cio' che decide il bot passa da ``decide(ctx, snap, params)``:
riceve lo stato della partita (``MatchCtx``), una fotografia del mercato e del
feed (``Snapshot``) e i parametri risolti; restituisce una ``Decision`` con le
azioni (place/cancel) e il nuovo stato. E' il chiamante (strategy.py) a
tradurre le azioni in ordini flumine e a riportare i fill sulle ``Leg``.

Convenzioni money-critical:
  - esposizioni SOLO dai fill (``Leg.matched`` / ``Leg.avg_price``), mai dalla size chiesta;
  - green-up / cash-out con ``compute_greenup`` (stessa aritmetica del ladder);
  - commissione applicata per MERCATO sul netto positivo (come execution.settle_group);
  - nessun numero inventato: prezzo mancante -> nessuna azione, ``complete=False``.

Mercati: ``OU35`` (Under 3.5 = selezione UNDER) e ``OU45`` (Over 4.5 = OVER,
Under 4.5 = UNDER per il re-ingresso). Esiti per gol totali T:
  Under 3.5 vince se T <= 3; Over 4.5 vince se T >= 5; Under 4.5 vince se T <= 4.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Tuple

from Betfair.stream.live_order_build import round_to_tick, ticks_away
from Betfair.stream.scalper.scalper_bot import ticks_between
from Betfair.stream.trading.greenup import GreenupPlan, compute_greenup

MARKET_OU35 = "OU35"
MARKET_OU45 = "OU45"
SEL_UNDER = "UNDER"
SEL_OVER = "OVER"

LINE = {MARKET_OU35: 3.5, MARKET_OU45: 4.5}

STATES = (
    "WATCH", "PRE_ENTRY_PENDING", "PRE_OPEN", "PRE_GREEN_PENDING", "HOLD",
    "PRE_LAST_ENTRY_PENDING", "IDLE_LIVE", "LIVE_KO_GREEN", "LIVE_SECOND_ENTRY",
    "LIVE_UNCOVERED", "LIVE_COVER_PENDING",
    "LIVE_COVERED", "LIVE_CLOSING", "FLAT", "REENTRY_PENDING", "REENTRY_OPEN",
    "REENTRY_GREEN_PENDING", "SETTLING", "SETTLED", "ERROR", "SKIPPED",
)
TERMINAL_STATES = ("SETTLED", "ERROR", "SKIPPED")

ROLES = (
    "under_entry", "under_green", "under_last", "under_second", "ko_green",
    "over_cover", "under_close", "over_close", "reentry", "reentry_green", "manual_close",
)
OPENING_ROLES = ("under_entry", "under_last", "under_second", "over_cover", "reentry")
# gambe di CHIUSURA: sul DB portano ``closes_trade_id`` = riga dell'apertura (H4)
CLOSING_ROLES = ("under_green", "ko_green", "under_close", "over_close", "reentry_green",
                 "manual_close")

# BACK di apertura che compongono la posizione Under 3.5 portata in gioco:
# l'ingresso del ciclo, l'ultimo ingresso PERSIST e la SECONDA PUNTATA dopo un
# gol precoce. Il prezzo medio di queste gambe e' il "punto di ingresso" su cui
# si calcola l'uscita a +N tick.
UNDER_ROLES = ("under_entry", "under_last", "under_second")

# status della gamba il cui ordine ha esito IGNOTO (C3)
STATUS_RECONCILE = "pending_reconcile"

# meta.exit_kind ammessi sulle righe di chiusura (contratto con la UI, H4)
EXIT_KINDS = ("greenup", "profit", "loss", "time", "forced", "manual", "other")

IT_BACK_MIN = 2.0
IT_BACK_STEP = 0.5
# Floor ASSOLUTO di un ordine, col place-and-trim: un centesimo. Sotto il minimo
# di PIAZZAMENTO (IT_BACK_MIN) l'ordine esiste comunque — si parcheggia il minimo
# a una quota non abbinabile, si taglia e si riprezza. Vedi
# ``omega_market.place_submin_live`` e ``Betfair/stream/trading/submin.py``.
SUBMIN_FLOOR = 0.01
_EPS = 1e-9
_FLAT_EPS = 0.01


# ---------------------------------------------------------------------------
# Dati
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Book:
    """Best price/size di UNA selezione (livello 0 del ladder) + stato mercato."""

    best_back: Optional[float]
    back_size: float = 0.0
    best_lay: Optional[float] = None
    lay_size: float = 0.0
    status: str = "OPEN"
    inplay: bool = False
    bet_delay: int = 0


@dataclass
class Leg:
    """Un ordine del bot (pending) o una posizione (matched > 0).

    CONTRATTO con il chiamante (service/strategy), money-critical:
      - ``status='pending'`` finche' l'ordine e' VIVO sull'exchange, anche se
        parzialmente abbinato (``matched`` cresce, ``remaining`` > 0): cosi' i
        percorsi di cancellazione (``is_live``) lo vedono sempre;
      - ``status='open'`` SOLO quando non e' piu' vivo: abbinato per intero
        oppure residuo cancellato con ``matched`` > 0;
      - ``status='cancelled'`` = mai abbinato e ritirato; ``'settled'`` a fine mercato;
      - ``status='pending_reconcile'`` (C3) = ordine il cui esito e' IGNOTO
        (eccezione REST dopo l'invio): NON e' vivo per il bot (niente cancel,
        niente riprezzo) ma conta SEMPRE nel rischio (peggior caso: abbinato per
        intero) e blocca ogni nuovo ingresso sulla partita finche' non si
        riconcilia contro Betfair. MAI 'cancelled'/'error' per scadenza del TTL;
      - ``archived=True`` = gamba di un ciclo pre-match gia' CHIUSO in green: resta
        per la contabilita' (settle) ma NON conta piu' come capitale a rischio
        (``position``/``invested``/``exposure``);
      - ``closes_ref`` = ref della gamba di APERTURA che questa gamba chiude
        (H4: sul DB diventa ``closes_trade_id``; lo storico conta i CICLI, non le gambe).
    """

    role: str
    market: str
    selection: str
    side: str                       # 'back' | 'lay'
    price: float
    size: float
    matched: float = 0.0
    avg_price: Optional[float] = None
    ref: str = ""
    status: str = "pending"          # pending | pending_reconcile | open | cancelled | settled
    placed_at: float = 0.0
    persistence: str = "LAPSE"
    cycle_no: int = 0
    final: bool = False
    archived: bool = False
    closes_ref: Optional[str] = None

    @property
    def remaining(self) -> float:
        return max(0.0, float(self.size) - float(self.matched))

    @property
    def is_live(self) -> bool:
        return self.status == "pending"

    @property
    def needs_reconcile(self) -> bool:
        """Ordine a esito IGNOTO: puo' esistere davvero su Betfair (C3)."""
        return self.status == STATUS_RECONCILE

    @property
    def filled(self) -> bool:
        return float(self.matched) >= float(self.size) - 0.005 or (
            self.status == "open" and float(self.matched) > 0.0
        )

    @property
    def fill_price(self) -> float:
        return float(self.avg_price if self.avg_price else self.price)


@dataclass(frozen=True)
class Snapshot:
    """Fotografia di mercato + feed al momento della decisione."""

    now: float
    ko_at: float
    books: Dict[Tuple[str, str], Book]
    inplay: bool = False
    minute: Optional[int] = None
    goals: Optional[int] = None
    ht_active: bool = False
    feed_fresh: bool = True
    hazard: Optional[float] = None
    p4_market: Optional[float] = None
    p4_model: Optional[float] = None
    last_goal_ts: Optional[float] = None
    market_status: str = "OPEN"
    final_total: Optional[int] = None
    # scambiato totale sul mercato 3.5 (dal feed): DIAGNOSTICA mostrata sulla
    # card (``live.total_matched``), nessun gate — vedi config.REMOVED_PARAMS.
    total_matched: Optional[float] = None
    # risparmio atteso (%) sulla copertura se si aspetta cover_wait_step_min senza gol
    cover_gain_pct: Optional[float] = None
    # pressione (corner/cartellini dal feed): moltiplicatore >= 1.0, 1.0 = neutra
    pressure: float = 1.0
    # probabilita' di MODELLO per le selezioni (u35/o45/u45) in tre scenari:
    # "_now" (adesso), "_goal" (subito dopo un gol), "_later" (fra cover_wait_step_min
    # minuti senza gol). Servono al cash-out intelligente (valore atteso dell'attesa).
    model_probs: Optional[Dict[str, float]] = None
    # distribuzione dei GOL TOTALI a fine gara {0..8, 8 = 8+}: dal modello (griglia
    # residua Omega) e dalla tabella empirica HT->FT (solo finche' il punteggio e'
    # quello dell'intervallo). Servono all'uscita in perdita "a modello".
    p_total_model: Optional[Dict[int, float]] = None
    p_total_emp: Optional[Dict[int, float]] = None
    # CERTIFICAZIONE 12/09 — distribuzione dei totali implicita nel MERCATO
    # (tre classi: <=3 / 4 / >=5, da ``feed.market_totals``). Si usa SOLO come
    # ripiego, quando modello ed empirico mancano: e' pur sempre il consenso di
    # chi scommette, ed e' molto meglio di una soglia percentuale fissa.
    p_total_market: Optional[Dict[int, float]] = None

    def book(self, market: str, selection: str) -> Optional[Book]:
        return self.books.get((market, selection))


@dataclass
class MatchCtx:
    state: str = "WATCH"
    legs: List[Leg] = field(default_factory=list)
    cycle_no: int = 0
    entry_price_initial: Optional[float] = None
    last_green_at: Optional[float] = None
    last_action_at: Optional[float] = None
    attempts: int = 0
    reentry_allowed: bool = False
    reentry_done: bool = False
    close_reason: Optional[str] = None
    cover_skipped: bool = False
    seq: int = 0
    settled_pnl: Optional[float] = None
    # C2 — chiusura MANUALE in corso (cash out / flatten dalla UI): finche' e'
    # attiva nessun ordine di APERTURA e nessuna lay di green-up riappoggiata
    # (senza questo flag, in pre-match con ``pre_exit_mode='resting'`` il ciclo
    # cancellava la lay e la riappoggiava subito: cash out impossibile).
    flatten_pending: bool = False
    # C3 — dopo un cash out manuale pre-KO il bot NON rientra da solo: solo
    # "Riprendi" dalla UI riabilita gli ingressi su questa partita.
    no_reentry: bool = False
    # CERT. 13/09 — PREZZO UNDER AL FISCHIO D'INIZIO, registrato UNA volta sola.
    # Serve a misurare quanto il mercato si muove fra il nostro ingresso
    # pre-match e l'apertura del gioco: e' la domanda "di quanti tick siamo
    # sotto/sopra appena si parte", e fino a oggi NESSUNA fonte lo conservava
    # (il primo ordine Under in gioco arriva al 27' nel caso piu' precoce,
    # mediana 54': sui 111 ingressi storici non c'e' una sola osservazione
    # vicina al fischio). None = non ancora entrata in gioco, o prezzo assente.
    ko_price_under: Optional[float] = None
    # ---- FLUSSO DAL FISCHIO D'INIZIO (specifica utente 13/09) --------------
    # Momento in cui la partita e' stata VISTA in gioco con una posizione Under
    # aperta: da qui partono i ``ko_green_window_s`` dell'ordine di uscita.
    live_since: Optional[float] = None
    # Gol sul tabellone al fischio: la baseline contro cui si riconosce il "gol
    # precoce". None = il feed non li dava ancora (nessun confronto possibile).
    ko_goals: Optional[int] = None
    # Momento del gol precoce: da qui partono i minuti di attesa della PRIMA
    # tranche di copertura.
    early_goal_at: Optional[float] = None
    # La seconda puntata Under 3.5 e' gia' stata tentata: MAI due volte.
    second_entry_done: bool = False
    # Copertura a tranche dopo un gol precoce:
    #   0 = copertura normale (in una volta)
    #   1 = prima tranche da comprare / sul book
    #   2 = prima tranche abbinata, si aspettano i minuti prima della seconda
    #   3 = seconda tranche (il RESIDUO, ricalcolato al prezzo del momento)
    cover_stage: int = 0
    # Momento in cui la prima tranche si e' abbinata: da qui partono i minuti
    # di attesa della seconda.
    cover_stage1_at: Optional[float] = None
    # La copertura e' stata ORDINATA dal flusso (finestra di uscita scaduta, gol
    # precoce): l'attesa "intelligente" di ``cover_timing`` non si applica piu'.
    cover_forced: bool = False


@dataclass(frozen=True)
class Action:
    kind: str                       # 'place' | 'cancel'
    role: Optional[str] = None
    market: Optional[str] = None
    selection: Optional[str] = None
    side: Optional[str] = None
    price: Optional[float] = None
    size: Optional[float] = None
    persistence: str = "LAPSE"
    ref: Optional[str] = None        # cancel: ref della gamba
    final: bool = False
    note: str = ""
    closes_ref: Optional[str] = None   # place di chiusura: ref della gamba di apertura (H4)


@dataclass
class Decision:
    state: str
    actions: List[Action] = field(default_factory=list)
    reason: str = ""
    updates: Dict[str, Any] = field(default_factory=dict)
    telemetry: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CashoutValue:
    net: float
    gross: float
    per_selection: Dict[Tuple[str, str], float]        # LORDO per selezione
    plans: Dict[Tuple[str, str], GreenupPlan]
    complete: bool
    # selezioni il cui esito e' GIA' deciso (linea superata): valgono 0/1 senza
    # prezzo e non rendono il cash-out incompleto (C2)
    decided: Tuple[Tuple[str, str], ...] = ()
    per_selection_net: Dict[Tuple[str, str], float] = field(default_factory=dict)


@dataclass(frozen=True)
class SettleResult:
    per_leg: List[Tuple[str, str, float]]     # (ref, status, pnl NETTO commissione) — H4
    per_market: Dict[str, float]               # netto per mercato (commissione applicata)
    net: float
    per_leg_gross: List[Tuple[str, str, float]] = field(default_factory=list)
    commission_by_market: Dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Matematica pura
# ---------------------------------------------------------------------------
def green_target(entry_price: float, ticks: int) -> float:
    """Prezzo di chiusura a ``ticks`` tick SOTTO il prezzo d'ingresso (back)."""
    return float(ticks_away(float(entry_price), -int(ticks)))


def locked_pnl_back(stake: float, entry_price: float, close_price: float) -> float:
    """P&L lordo bloccato su entrambi gli esiti chiudendo un back S@Pe con lay a p."""
    return float(stake) * (float(entry_price) / float(close_price) - 1.0)


def cover_size(stake_under: float, price_over: float, commission: float, factor: float) -> float:
    """Stake sull'Over 4.5 tale che, se vince, il netto sia (factor-1)*stake_under."""
    if price_over is None or price_over <= 1.0:
        raise ValueError(f"price_over non valido: {price_over!r}")
    return float(factor) * float(stake_under) / ((float(price_over) - 1.0) * (1.0 - float(commission)))


def cover_residual(liability_under: float, price_over: float, commission: float, factor: float,
                   already: float) -> float:
    """Stake RESIDUO sull'Over 4.5 dato il netto ``already`` GIA' garantito dalle
    coperture abbinate (somma di m·(p−1)·(1−c) su OGNI gamba over_cover):
    il resto porta il netto con 5+ gol a (factor−1)·liability_under. Mai negativo."""
    if price_over is None or price_over <= 1.0:
        raise ValueError(f"price_over non valido: {price_over!r}")
    target = float(factor) * float(liability_under)
    residual = (target - float(already)) / ((float(price_over) - 1.0) * (1.0 - float(commission)))
    return max(0.0, residual)


def cover_size_residual(stake_under: float, price_over: float, commission: float, factor: float, *,
                        matched: float, matched_price: float) -> float:
    """Stake RESIDUO sull'Over 4.5 dopo un fill parziale ``matched`` @ ``matched_price``:
    la parte abbinata rende gia' m·(p_old−1)·(1−c); il resto porta il netto a (factor-1)·S."""
    already = float(matched) * (float(matched_price) - 1.0) * (1.0 - float(commission))
    return cover_residual(stake_under, price_over, commission, factor, already)


def cover_matched_value(legs: List[Leg], commission: float) -> float:
    """Netto GIA' garantito con 5+ gol dal mercato Over/Under 4.5, dai soli fill.

    Conta TUTTE le gambe vive del mercato OU45 (piu' coperture ``over_cover``
    parzialmente abbinate, eventuali lay di chiusura, un re-ingresso Under 4.5),
    non solo l'ultima: con due coperture abbinate dimensionare il residuo sulla
    sola ultima gamba comprerebbe Over gia' comprato (test dedicato).
    La commissione e' per MERCATO sul netto positivo, quindi si applica alla
    somma del mercato, non gamba per gamba."""
    gross = _market_pnl_by_total(active_legs(legs), MARKET_OU45, 5)
    return round(_net(gross, float(commission)), 6)


def under_liability(legs: List[Leg]) -> float:
    """Euro persi sull'Under 3.5 se l'Under PERDE, dalla posizione NETTA (back
    abbinati meno eventuali lay parziali di green): e' la base della copertura.
    Con una lay parziale abbinata la liability e' minore dello stake back: coprire
    lo stake intero comprerebbe piu' Over del necessario (perdita maggiore con 0-3 gol)."""
    _w, l = exposure(legs, MARKET_OU35, SEL_UNDER)
    return round(max(0.0, -float(l)), 2)


def legalize_back_size(size: float, rounding: str = "ceil",
                       min_stake: float = IT_BACK_MIN, step: float = IT_BACK_STEP) -> Tuple[float, float]:
    """Size BACK legale .it (min 2.00, passo 0.50) + overshoot % rispetto alla size chiesta."""
    x = float(size)
    if x <= 0 or not math.isfinite(x):
        return (0.0, 0.0)
    n = x / step
    if rounding == "floor":
        k = math.floor(n + _EPS)
    elif rounding == "nearest":
        k = math.floor(n + 0.5)
    else:
        k = math.ceil(n - _EPS)
    legal = max(min_stake, round(k * step, 2))
    overshoot = (legal / x - 1.0) * 100.0
    return (legal, round(overshoot, 4))


def cover_legal_size(x: float, params: Dict[str, Any]) -> Tuple[float, float]:
    """Size effettiva della copertura: ESATTA al centesimo (``exact_sizes``, il
    default) oppure legalizzata .it (min 2.00 / passo 0.50) se si sceglie cosi'.
    Ritorna (size, overshoot %).

    13/09 — L'IMPORTO ESATTO E' L'IMPORTO GIUSTO, e da oggi e' anche piazzabile.
    Il minimo di Betfair riguarda il place DIRETTO, non l'ordine in se': col
    place-and-trim (parcheggio a quota non abbinabile, taglio parziale,
    riprezzo) si piazza qualunque cifra fino al centesimo. Vedi
    ``omega_market.place_submin_live`` e ``Betfair/stream/trading/submin.py``.

    Il rialzo al minimo era un ripiego del 12/09, nato da un caso vero (Koper v
    Olimpija: copertura da 1,91 EUR rifiutata 172 volte, partita finita a 4 gol
    e -16,16 EUR senza copertura). Quel ripiego non serve piu': adesso 1,91 EUR
    e' un ordine valido, e comprare 2,00 di Over quando ne servono 1,35 e' solo
    sovracopertura pagata.
    """
    x = float(x)
    if params.get("exact_sizes", True):
        return (round(x, 2), 0.0)
    return legalize_back_size(x, str(params.get("cover_rounding", "ceil")))


def needs_submin(side: str, size: float, min_stake: float = IT_BACK_MIN, step: float = IT_BACK_STEP) -> bool:
    """True se un ordine BACK di apertura con questa size richiede il place-and-trim (.it)."""
    if side != "back":
        return False
    s = round(float(size), 2)
    if s < min_stake - _EPS:
        return True
    return abs(round(s / step) * step - s) > 0.005


def cycle_label(cycle_no: int) -> int:
    """Numero di ciclo COME LO LEGGE IL TRADER, 1-based.

    ``ctx.cycle_no`` conta i cicli GIA' CHIUSI (0 = primo ciclo in corso): e' il
    dato strutturato che finiscono sul DB (``mike_events.cycle_no``,
    ``pre_cycle.cycle``, il ``ref``/``signal_key`` delle gambe) e NON si tocca —
    la UI lo converte con ``lib/mike.ts::cycleNumber``. I testi dei ``reason``,
    invece, arrivano GREZZI nella scheda Attivita' (``state.reason``) e sulla
    card (``ctx.last_reason``): devono usare la stessa numerazione della pagina,
    altrimenti la stessa partita mostra "ciclo 0" e "ciclo 1" per lo stesso ciclo.
    Unica convenzione: nei testi si scrive sempre ``cycle_label(cycle_no)``.
    """
    n = int(cycle_no)
    return n + 1 if n >= 0 else 1


def price_ok(price: Optional[float]) -> bool:
    """Prezzo utilizzabile: presente, finito e > 1.0.

    Il feed puo' consegnare ``None``, ``NaN`` o 0 su una riga potata/sospesa: senza
    questo controllo ``NaN > 1.0`` e' False ma ``NaN is not None`` e' True, e il
    prezzo finiva in ``round_to_tick``/``cover_size`` producendo size NaN oppure
    un'eccezione che congelava la partita (COSTITUZIONE §4.6: prezzo mancante =
    nessuna azione, mai numeri inventati).
    """
    if price is None:
        return False
    try:
        p = float(price)
    except (TypeError, ValueError):
        return False
    return math.isfinite(p) and p > 1.0


def size_ok(size: Optional[float]) -> bool:
    """Size piazzabile: finita e >= 1 centesimo (mai ordini-fantasma da 0,00 EUR)."""
    if size is None:
        return False
    try:
        s = float(size)
    except (TypeError, ValueError):
        return False
    return math.isfinite(s) and s >= 0.01


def selection_wins(market: str, selection: str, total_goals: int) -> bool:
    line = LINE[market]
    if selection == SEL_UNDER:
        return total_goals < line
    return total_goals > line


def selection_decided(market: str, selection: str, goals: Optional[int]) -> Optional[bool]:
    """Esito GIA' CERTO della selezione con ``goals`` gol segnati (C2).

    I gol non si togliono: appena la linea e' superata l'Over ha VINTO e l'Under
    ha PERSO, qualunque cosa faccia il mercato (la linea viene potata dal feed).
    Sotto la linea nulla e' deciso. Ritorna True (vinta), False (persa) o None.
    """
    if goals is None:
        return None
    if int(goals) > LINE[market]:
        return selection == SEL_OVER
    return None


def exposure(legs: List[Leg], market: str, selection: str) -> Tuple[float, float]:
    """(W, L) = profit se la selezione vince / perde, dai soli fill."""
    w = l = 0.0
    for leg in legs:
        if leg.market != market or leg.selection != selection or leg.matched <= 0:
            continue
        if leg.archived:
            continue  # ciclo pre-match gia' chiuso in green: non e' capitale a rischio
        s = float(leg.matched)
        p = leg.fill_price
        if leg.side == "back":
            w += s * (p - 1.0)
            l -= s
        else:
            w -= s * (p - 1.0)
            l += s
    return (round(w, 4), round(l, 4))


def open_selections(legs: List[Leg]) -> List[Tuple[str, str]]:
    """Selezioni con esposizione non piatta (ordine deterministico)."""
    out = []
    for key in ((MARKET_OU35, SEL_UNDER), (MARKET_OU45, SEL_OVER), (MARKET_OU45, SEL_UNDER)):
        w, l = exposure(legs, *key)
        if abs(w - l) >= _FLAT_EPS:
            out.append(key)
    return out


def live_open_selections(legs: List[Leg], goals: Optional[int] = None) -> List[Tuple[str, str]]:
    """Selezioni aperte ANCORA IN GIOCO: quelle il cui esito e' gia' deciso
    (linea superata) non sono piu' gestibili — nessun prezzo, nessuna azione (C2)."""
    return [k for k in open_selections(legs) if selection_decided(k[0], k[1], goals) is None]


def position(legs: List[Leg], market: str, selection: str, roles: Tuple[str, ...]) -> Tuple[float, Optional[float]]:
    """(stake abbinato, prezzo medio) dei back di apertura su una selezione."""
    tot = 0.0
    wsum = 0.0
    for leg in legs:
        if leg.market != market or leg.selection != selection or leg.role not in roles:
            continue
        if leg.side != "back" or leg.matched <= 0 or leg.archived:
            continue
        tot += float(leg.matched)
        wsum += float(leg.matched) * leg.fill_price
    if tot <= 0:
        return (0.0, None)
    return (round(tot, 2), round(wsum / tot, 4))


def invested(legs: List[Leg]) -> float:
    """Capitale investito nei back di apertura ancora abbinati (base del cash-out)."""
    return round(sum(float(l.matched) for l in legs
                     if l.side == "back" and l.role in OPENING_ROLES and l.matched > 0
                     and not l.archived), 2)


def _market_pnl_by_total(legs: List[Leg], market: str, total: int) -> float:
    pnl = 0.0
    for leg in legs:
        if leg.market != market or leg.matched <= 0:
            continue
        win = selection_wins(market, leg.selection, total)
        s = float(leg.matched)
        p = leg.fill_price
        if leg.side == "back":
            pnl += s * (p - 1.0) if win else -s
        else:
            pnl += -s * (p - 1.0) if win else s
    return pnl


def _net(value: float, commission: float) -> float:
    return value * (1.0 - commission) if value > 0 else value


def net_pnl_by_total(legs: List[Leg], commission: float, max_total: int = 8) -> Dict[int, float]:
    """P&L NETTO complessivo per ogni somma gol 0..max_total (commissione per mercato)."""
    out: Dict[int, float] = {}
    for t in range(0, max_total + 1):
        tot = 0.0
        for market in (MARKET_OU35, MARKET_OU45):
            tot += _net(_market_pnl_by_total(legs, market, t), commission)
        out[t] = round(tot, 2)
    return out


def cashout_value(legs: List[Leg], books: Dict[Tuple[str, str], Book], commission: float,
                  place_at_ticks: int = 0, goals: Optional[int] = None) -> CashoutValue:
    """Valore di cash-out globale: somma dei P&L bloccati chiudendo OGNI selezione ora.

    C2 — dopo il 4o gol la linea 3.5 viene potata dal feed: una selezione il cui
    esito e' GIA' deciso (``selection_decided``) vale 0/1 SENZA prezzo (W se ha
    vinto, L se ha perso) e NON rende il cash-out incompleto. ``complete`` dice
    solo se tutte le selezioni ancora VIVE hanno un prezzo: sono quelle su cui
    si puo' davvero agire.
    """
    per: Dict[Tuple[str, str], float] = {}
    plans: Dict[Tuple[str, str], GreenupPlan] = {}
    decided: List[Tuple[str, str]] = []
    complete = True
    gross = 0.0
    gross_market: Dict[str, float] = {}
    pos_market: Dict[str, float] = {}
    for key in open_selections(legs):
        w, l = exposure(legs, *key)
        won = selection_decided(key[0], key[1], goals)
        if won is not None:
            locked = float(w if won else l)
            decided.append(key)
        else:
            bk = books.get(key)
            plan = compute_greenup(
                matched_if_win=w, matched_if_lose=l,
                best_back_price=bk.best_back if bk else None,
                best_lay_price=bk.best_lay if bk else None,
                fraction=1.0, place_at_ticks=int(place_at_ticks),
            )
            plans[key] = plan
            if not plan.actionable:
                complete = False
                continue
            locked = float(min(plan.expected_if_win, plan.expected_if_lose))
        per[key] = round(locked, 2)
        gross += locked
        gross_market[key[0]] = gross_market.get(key[0], 0.0) + locked
        if locked > 0:
            pos_market[key[0]] = pos_market.get(key[0], 0.0) + locked
    # Commissione per MERCATO sul netto positivo (docstring del modulo, COSTITUZIONE
    # §4.4): su OU45 possono convivere OVER (copertura) e UNDER (re-ingresso) e
    # applicare il 5% a ogni selezione in utile avrebbe tassato un lordo che il
    # mercato non paga. La commissione del mercato viene ripartita PRO-RATA sulle
    # selezioni in utile, cosi' sum(per_selection_net) == net.
    per_net: Dict[Tuple[str, str], float] = {}
    comm_market: Dict[str, float] = {m: (v * float(commission) if v > 0 else 0.0)
                                     for m, v in gross_market.items()}
    for key, locked in per.items():
        share = 0.0
        pos = pos_market.get(key[0], 0.0)
        if locked > 0 and pos > 0 and comm_market.get(key[0], 0.0) > 0:
            share = comm_market[key[0]] * (locked / pos)
        per_net[key] = round(locked - share, 2)
    net = sum(_net(v, commission) for v in gross_market.values())
    return CashoutValue(net=round(net, 2), gross=round(gross, 2), per_selection=per,
                        plans=plans, complete=complete, decided=tuple(decided),
                        per_selection_net=per_net)


# Quante gambe ANNULLATE e mai abbinate si tengono per ruolo nello stato
# dell'evento. Servono solo a leggere "l'ultimo tentativo": oltre sono zavorra.
MAX_CANCELLED_PER_ROLE = 5


def prune_dead_legs(legs: List[Leg], max_per_role: int = MAX_CANCELLED_PER_ROLE) -> List[Leg]:
    """Toglie le gambe ANNULLATE e MAI ABBINATE oltre le ultime ``max_per_role``
    per ruolo. L'ordine relativo delle superstiti non cambia.

    CERT. 13/09 — perche' esiste. La scheda dell'evento porta con se' TUTTE le
    gambe mai create, comprese quelle annullate. Il difetto della copertura
    corretto il 12/09 (size sotto il minimo Betfair, ritentata a ogni giro) ne
    ha lasciate 180 su una sola partita: Koper v Olimpija pesava **60 KB**, di
    cui 56 di sole gambe annullate. ``get_mike_state`` ne aggrega fino a 200 di
    eventi: la RPC arrivava a 7,6 secondi, contro un timeout di 8 — da cui gli
    alert «canceling statement due to statement timeout» sulla pagina Mike.

    Cosa NON si tocca mai:
      * ogni gamba con ``matched > 0`` — sono soldi veri, entrano nel P&L;
      * ogni gamba non annullata (pending, aperta, da riconciliare, regolata).
    Una gamba annullata con abbinato zero non entra in nessun conto
    (``_market_pnl_by_total`` salta ``matched <= 0``) e il suo ``ref`` non serve
    piu': la numerazione viene da ``ctx.seq``, non dalla lunghezza della lista.
    Se ne tengono comunque le ultime per ruolo, cosi' chi legge "l'ultimo
    tentativo" continua a trovarlo.
    """
    if max_per_role < 0:
        return list(legs)
    morte_per_ruolo: Dict[str, int] = {}
    tenere: List[bool] = []
    # si scorre dal fondo: le ULTIME per ruolo sono quelle da conservare
    for leg in reversed(legs):
        morta = (str(getattr(leg, "status", "")) == "cancelled"
                 and float(getattr(leg, "matched", 0.0) or 0.0) <= 0.0)
        if not morta:
            tenere.append(True)
            continue
        r = str(getattr(leg, "role", ""))
        n = morte_per_ruolo.get(r, 0)
        tenere.append(n < max_per_role)
        morte_per_ruolo[r] = n + 1
    tenere.reverse()
    return [l for l, ok in zip(legs, tenere) if ok]


def drift_ticks(prezzo_ingresso: Optional[float], prezzo_ko: Optional[float]) -> Optional[int]:
    """Tick fra il nostro prezzo d'ingresso e quello al fischio d'inizio.

    NEGATIVO = il prezzo e' SCESO, cioe' a nostro favore su un back Under
    (l'ordine di chiusura a due tick sotto e' piu' vicino).
    POSITIVO = il prezzo e' SALITO, quindi siamo sotto.
    None se manca un prezzo o la scala non li collega.

    ``ticks_between`` accetta solo (basso, alto): il segno lo mettiamo qui.
    """
    try:
        a = float(prezzo_ingresso) if prezzo_ingresso is not None else None
        b = float(prezzo_ko) if prezzo_ko is not None else None
    except (TypeError, ValueError):
        return None
    if not a or not b or a <= 1.0 or b <= 1.0:
        return None
    if a == b:
        return 0
    t = ticks_between(min(a, b), max(a, b))
    if t is None:
        return None
    return -t if b < a else t


def active_legs(legs: List[Leg]) -> List[Leg]:
    """Gambe che portano ancora rischio: i cicli archiviati sono chiusi e bloccati."""
    return [l for l in legs if not l.archived]


def _assume_matched(legs: List[Leg]) -> List[Leg]:
    """Copia delle gambe con gli ordini a esito IGNOTO considerati ABBINATI per
    intero: un ordine che POTREBBE essere vivo su Betfair conta sempre nel
    rischio (C3, mai una posizione invisibile)."""
    out: List[Leg] = []
    for l in legs:
        if l.needs_reconcile and float(l.matched) <= 0:
            out.append(replace(l, matched=float(l.size), avg_price=float(l.price), status="open"))
        else:
            out.append(l)
    return out


def event_liability(legs: List[Leg], commission: float) -> float:
    """Rischio VERO della partita (M4): la perdita peggiore possibile sulle
    posizioni NETTE ancora aperte, non la somma delle gambe. Un back di apertura
    coperto da una lay ha come rischio il residuo, non back + lay. Gli ordini a
    esito ignoto contano come abbinati (peggior caso)."""
    act = _assume_matched(active_legs(legs))
    if not any(float(l.matched) > 0 for l in act):
        return 0.0
    dist = net_pnl_by_total(act, commission)
    return round(max(0.0, -min(dist.values())), 2) if dist else 0.0


def locked_pnl(legs: List[Leg], commission: float) -> Optional[float]:
    """P&L NETTO gia' BLOCCATO: identico su ogni somma gol perche' non c'e' piu'
    esposizione aperta (ciclo greenato o chiuso, mercato non ancora pagato).
    ``None`` se qualche selezione e' ancora viva (nulla e' deciso). L3: lo stop
    giornaliero deve vedere anche questo, non solo il regolato."""
    if open_selections(legs) or any(l.needs_reconcile for l in legs):
        return None
    dist = net_pnl_by_total(legs, commission)
    return round(min(dist.values()), 2) if dist else None


def exit_kind_for(role: str, close_reason: Optional[str]) -> str:
    """``meta.exit_kind`` della riga di chiusura (H4, contratto UI).

    greenup = take-profit di un ciclo (lay a +N tick sull'apertura);
    profit   = cash-out globale a profitto; loss = uscita HT/2T a perdita
    tollerata; forced = cap di perdita evento; time = chiusura forzata a minuto;
    manual = cash out/flatten dalla UI; other = tutto il resto.
    """
    reason = str(close_reason or "")
    if role == "manual_close" or reason == "manual":
        return "manual"
    if role in ("under_green", "ko_green", "reentry_green"):
        return "time" if reason == "reentry_time" else "greenup"
    if reason == "profit":
        return "profit"
    if reason.startswith("loss_"):
        return "forced" if reason == "loss_cap" else "loss"
    if reason == "reentry_time":
        return "time"
    return "other"


def opening_ref(legs: List[Leg], market: str, selection: str) -> Optional[str]:
    """``ref`` della gamba di APERTURA che una chiusura su questa selezione sta
    chiudendo: l'ultima abbinata e non archiviata (H4)."""
    cands = [l for l in legs if l.market == market and l.selection == selection
             and l.role in OPENING_ROLES and l.side == "back"]
    live = [l for l in cands if float(l.matched) > 0 and not l.archived]
    if live:
        return live[-1].ref
    return cands[-1].ref if cands else None


def should_cashout(value_net: float, base: float, pct: float) -> bool:
    if base <= 0:
        return False
    return value_net >= base * float(pct) / 100.0 - _EPS


def loss_exit_ok(value_net: float, base: float, pct: float, *, goals: Optional[int],
                 gmin: int, gmax: int) -> bool:
    """Chiudi comunque se la perdita bloccabile e' entro pct% della base (o in profitto)."""
    if goals is None or base <= 0 or goals < gmin or goals > gmax:
        return False
    return value_net >= -base * float(pct) / 100.0 - _EPS


_PROB_KEY = {(MARKET_OU35, SEL_UNDER): "u35", (MARKET_OU45, SEL_OVER): "o45", (MARKET_OU45, SEL_UNDER): "u45"}
_DEAD_PRICE = 1000.0


def projected_books(books: Dict[Tuple[str, str], Book], model_probs: Optional[Dict[str, float]],
                    scenario: str) -> Optional[Dict[Tuple[str, str], Book]]:
    """Book PROIETTATI nello scenario ``goal`` | ``later``.

    La quota equa e' proporzionale a 1/P: la quota di MERCATO viene scalata per
    P_now/P_scenario, cosi' si conserva il margine reale del book. P_scenario ~ 0
    (selezione morta, es. Under 3.5 dopo il 4o gol) -> quota 1000. None se manca un dato.
    """
    if not model_probs:
        return None
    out: Dict[Tuple[str, str], Book] = {}
    for key, bk in books.items():
        k = _PROB_KEY.get(key)
        if k is None:
            continue
        p_now, p_new = model_probs.get(f"{k}_now"), model_probs.get(f"{k}_{scenario}")
        if p_now is None or p_new is None or float(p_now) <= 0:
            return None
        ratio = _DEAD_PRICE if float(p_new) <= 1e-6 else float(p_now) / float(p_new)

        def _sc(x: Optional[float]) -> Optional[float]:
            return None if x is None else max(1.01, min(_DEAD_PRICE, float(x) * ratio))

        out[key] = replace(bk, best_back=_sc(bk.best_back), best_lay=_sc(bk.best_lay))
    return out


def smart_cashout(*, cv_net: float, base: float, legs: List[Leg], books: Dict[Tuple[str, str], Book],
                  commission: float, params: Dict[str, Any], hazard: Optional[float], pressure: float,
                  goals: Optional[int], model_probs: Optional[Dict[str, float]],
                  place_at_ticks: int = 0) -> Tuple[bool, str, Dict[str, Any]]:
    """Cash-out INTELLIGENTE: chiude prima della soglia quando tenere la posizione
    non vale il rischio. Mai sotto ``cashout_smart_min_pct`` della base (profitto
    minimo garantito). Ordine dei criteri:
      1. punteggio caldo: gol >= cashout_smart_goals_hot (il prossimo gol e' il 4o);
      2. vicino alla soglia (entro cashout_smart_tolerance_pct) E fase calda
         (hazard 3' >= cashout_smart_hazard_hot O pressione >= cashout_smart_pressure_hot);
      3. valore atteso dell'attesa (modello): EV_hold = h*V_gol + (1-h)*V_dopo con
         h = P(gol entro cover_wait_step_min) dall'hazard 3'. Vicino alla soglia
         basta EV_hold < V_ora; lontano serve EV_hold < V_ora - cashout_smart_ev_margin_pct.
    Ritorna (chiudi, motivo, telemetria)."""
    tele: Dict[str, Any] = {"enabled": bool(params.get("cashout_smart_enabled", False))}
    if not tele["enabled"] or base <= 0:
        return False, "", tele
    target = base * float(params["cashout_profit_pct"]) / 100.0
    floor = base * float(params["cashout_smart_min_pct"]) / 100.0
    tol = base * float(params["cashout_smart_tolerance_pct"]) / 100.0
    near = cv_net >= target - tol - _EPS
    tele.update({"floor": round(floor, 2), "near": near, "hazard": hazard, "pressure": round(float(pressure), 3)})
    if cv_net < floor - _EPS:
        return False, "", tele
    g = int(goals or 0)
    if g >= int(params["cashout_smart_goals_hot"]):
        tele["trigger"] = "goals_hot"
        return True, f"punteggio caldo ({g} gol) sopra il profitto minimo", tele
    hot = (hazard is not None and float(hazard) >= float(params["cashout_smart_hazard_hot"])) or \
        float(pressure) >= float(params["cashout_smart_pressure_hot"])
    tele["hot"] = hot
    if near and hot:
        tele["trigger"] = "hot_near"
        return True, "fase calda (hazard/pressione) a un passo dalla soglia", tele
    if model_probs and hazard is not None:
        bg = projected_books(books, model_probs, "goal")
        bl = projected_books(books, model_probs, "later")
        if bg and bl:
            # ``goals``: gli scenari proiettati devono valutare le selezioni GIA'
            # decise come 0/1 esattamente come ``cv_net`` (C2), altrimenti si
            # confrontano due grandezze diverse e una linea potata rende
            # ``complete=False`` spegnendo il criterio del valore atteso.
            cv_goal = cashout_value(legs, bg, commission, place_at_ticks, goals=goals)
            cv_later = cashout_value(legs, bl, commission, place_at_ticks, goals=goals)
            if cv_goal.complete and cv_later.complete:
                step = max(1.0, float(params.get("cover_wait_step_min", 5)))
                h_step = 1.0 - (1.0 - min(1.0, max(0.0, float(hazard)))) ** (step / 3.0)
                ev_hold = h_step * cv_goal.net + (1.0 - h_step) * cv_later.net
                tele.update({"cv_goal": cv_goal.net, "cv_later": cv_later.net,
                             "h_step": round(h_step, 4), "ev_hold": round(ev_hold, 2)})
                margin = base * float(params["cashout_smart_ev_margin_pct"]) / 100.0
                if near and ev_hold < cv_net - _EPS:
                    tele["trigger"] = "ev_near"
                    return True, f"aspettare vale {ev_hold:.2f} < {cv_net:.2f} a un passo dalla soglia", tele
                if ev_hold < cv_net - margin - _EPS:
                    tele["trigger"] = "ev_margin"
                    return True, f"attesa a valore atteso {ev_hold:.2f} << {cv_net:.2f}", tele
    return False, "", tele


def blend_totals(*dists: Optional[Dict[int, float]]) -> Optional[Dict[int, float]]:
    """Media delle distribuzioni disponibili dei gol totali (None ignorati), normalizzata."""
    ok = [d for d in dists if d]
    if not ok:
        return None
    keys = sorted({int(k) for d in ok for k in d})
    out = {k: sum(float(d.get(k, 0.0)) for d in ok) / len(ok) for k in keys}
    tot = sum(out.values())
    return {k: v / tot for k, v in out.items()} if tot > 0 else None


def hold_expectation(pnl_by_total: Dict[int, float], p_total: Dict[int, float],
                     p4_floor: Optional[float] = None) -> Tuple[float, float]:
    """(EV a fine gara tenendo tutto, P(4) usata). Con ``p4_floor`` la P(4) viene
    alzata (mai abbassata) e il resto della distribuzione riscalato: e' la scelta
    PRUDENTE (fra modello, empirico e mercato comanda il piu' pessimista sui 4 gol)."""
    dist = {int(k): float(v) for k, v in p_total.items()}
    p4 = dist.get(4, 0.0)
    # una probabilita' dal feed/mercato puo' arrivare sporca (NaN, >1, negativa):
    # senza clamp il riscalamento produce probabilita' NEGATIVE, un EV fuori dal
    # range dei P&L possibili e una "P(4) 150%" in UI.
    floor = None
    if p4_floor is not None and math.isfinite(float(p4_floor)):
        floor = max(0.0, min(1.0, float(p4_floor)))
    if floor is not None and floor > p4:
        rest = 1.0 - p4
        scale = (1.0 - floor) / rest if rest > 0 else 0.0
        dist = {k: (floor if k == 4 else v * scale) for k, v in dist.items()}
        p4 = floor
    max_t = max(pnl_by_total) if pnl_by_total else 8
    ev = 0.0
    for t, p in dist.items():
        ev += p * float(pnl_by_total.get(min(t, max_t), 0.0))
    return round(ev, 4), round(p4, 4)


def loss_exit_model(*, cv_net: float, base: float, pnl_by_total: Dict[int, float],
                    p_total_model: Optional[Dict[int, float]], p_total_emp: Optional[Dict[int, float]],
                    p4_market: Optional[float], params: Dict[str, Any],
                    p_total_market: Optional[Dict[int, float]] = None
                    ) -> Tuple[Optional[bool], str, Dict[str, Any]]:
    """Uscita in perdita A MODELLO: confronta il valore CERTO di chiudere ora (cv_net)
    con il valore ATTESO di tenere fino alla fine (EV = sum P(tot) * P&L(tot)), meno un
    premio al rischio proporzionale alla P(4 gol): premio = risk_premium% * P(4) * base.
    Chiude se cv_net >= EV - premio. P(4) prudente = max(modello/empirico, mercato).
    Ritorna (None, ...) quando i dati mancano (il chiamante usa la regola fissa)."""
    tele: Dict[str, Any] = {"mode": "model"}
    dist = blend_totals(p_total_model, p_total_emp)
    if dist is None and p_total_market:
        # CERT. 12/09 — senza modello si decide sul MERCATO, non su una soglia
        # fissa: la regola percentuale chiudeva posizioni ancora favorite
        # (caso reale: chiusa sullo 0-2 al 46', la partita e' finita 3 gol e
        # l'Under 3.5 avrebbe VINTO; la chiusura e' costata 5,02 EUR).
        dist = dict(p_total_market)
        tele["mode"] = "market"
    if dist is None or base <= 0 or not pnl_by_total:
        tele["missing"] = True
        return None, "", tele
    p4_floor = None
    if params.get("loss_exit_p4_prudent", True) and p4_market is not None:
        p4_floor = float(p4_market)
    ev_hold, p4 = hold_expectation(pnl_by_total, dist, p4_floor)
    premium = base * float(params["loss_exit_risk_premium_pct"]) / 100.0 * p4
    threshold = ev_hold - premium
    tele.update({"ev_hold": round(ev_hold, 2), "p4": p4, "p4_model": (p_total_model or {}).get(4),
                 "p4_emp": (p_total_emp or {}).get(4), "p4_market": p4_market,
                 "premium": round(premium, 2), "threshold": round(threshold, 2),
                 "sources": [n for n, d in (("model", p_total_model), ("emp", p_total_emp)) if d]})
    cap = float(params.get("loss_exit_max_pct") or 0.0)
    if cap > 0 and cv_net < -base * cap / 100.0 - _EPS:
        tele["beyond_cap"] = True
        return False, f"perdita {cv_net:.2f} oltre il tetto {cap}%: si tiene", tele
    if cv_net >= threshold - _EPS:
        return True, f"chiudere ({cv_net:.2f}) vale piu' di tenere ({ev_hold:.2f} - premio {premium:.2f}, P4 {p4:.0%})", tele
    return False, f"tenere vale {ev_hold:.2f} - premio {premium:.2f} > {cv_net:.2f}", tele


def cover_timing(*, goals: Optional[int], minute: Optional[int], hazard: Optional[float],
                 p4_market: Optional[float], last_goal_ts: Optional[float], now: float,
                 params: Dict[str, Any], price_over: Optional[float] = None,
                 cover_gain_pct: Optional[float] = None) -> str:
    """'cover' | 'wait' | 'skip' per la copertura sull'Over 4.5.

    Regola "intelligente ma non lenta": si ASPETTA solo se TUTTE valgono:
      0 gol · minuto < cover_wait_max_min · hazard 3' ≤ cover_wait_hazard_max ·
      P(4) mercato ≤ cover_wait_p4_max · quota Over < cover_good_price ·
      risparmio atteso ≥ cover_wait_min_gain_pct (se stimabile).
    Ogni dato mancante = si copre (mai attesa al buio). Dopo un gol: attesa del
    solo riprezzo (cover_postgoal_delay_s), poi copertura.
    """
    g = int(goals or 0)
    if g > int(params["cover_max_goals"]):
        return "skip"
    policy = params.get("cover_policy", "auto")
    if policy == "immediate":
        return "cover"
    if g >= 1:
        if last_goal_ts is not None and now - float(last_goal_ts) < float(params["cover_postgoal_delay_s"]):
            return "wait"
        return "cover"
    if minute is None:
        return "cover"
    if int(minute) >= int(params["cover_wait_max_min"]):
        return "cover"
    if policy == "wait":
        return "wait"
    if hazard is None or p4_market is None:
        return "cover"
    if float(hazard) > float(params["cover_wait_hazard_max"]):
        return "cover"
    if float(p4_market) > float(params["cover_wait_p4_max"]):
        return "cover"
    if price_over is not None and float(price_over) >= float(params.get("cover_good_price", 7.0)):
        return "cover"          # la quota e' gia' buona: aspettare non paga il rischio
    if cover_gain_pct is not None and float(cover_gain_pct) < float(params.get("cover_wait_min_gain_pct", 8.0)):
        return "cover"          # il risparmio atteso non vale il rischio di un gol
    return "wait"


def winners_from_total(total_goals: int) -> Dict[str, str]:
    """Selezione vincente di OGNI mercato dato il totale gol."""
    return {m: (SEL_UNDER if int(total_goals) < LINE[m] else SEL_OVER)
            for m in (MARKET_OU35, MARKET_OU45)}


def settle_legs(legs: List[Leg], total_goals: int, commission: float) -> SettleResult:
    """Esito per gamba dato il totale gol finale (caso normale)."""
    return settle_legs_by_market(legs, winners_from_total(int(total_goals)), commission)


def settle_legs_by_market(legs: List[Leg], winners: Dict[str, Optional[str]],
                          commission: float) -> SettleResult:
    """Esito per gamba con il vincitore di OGNI MERCATO (C4).

    ``winners[market]`` = ``SEL_UNDER``/``SEL_OVER`` oppure ``None`` = mercato
    ANNULLATO (void): solo le gambe di QUEL mercato valgono zero. Prima un solo
    mercato illeggibile o annullato azzerava il P&L di tutta la partita — con 4
    gol la perdita reale sull'Under 3.5 diventava 0.

    H4: il P&L di OGNI riga e' NETTO commissione. La commissione Betfair e' per
    MERCATO sul netto positivo: viene ripartita PRO-RATA sulle gambe in utile di
    quel mercato, cosi' ``sum(per_leg) == net``.
    """
    raw: List[Tuple[Leg, str, float]] = []
    gross_market: Dict[str, float] = {}
    pos_market: Dict[str, float] = {}
    for leg in legs:
        winner = winners.get(leg.market, "__missing__")
        if leg.matched <= 0 or winner is None:
            raw.append((leg, "void", 0.0))
            continue
        if winner == "__missing__":
            raise ValueError(f"vincitore non dichiarato per il mercato {leg.market}")
        win = leg.selection == winner
        s = float(leg.matched)
        p = leg.fill_price
        if leg.side == "back":
            pnl = s * (p - 1.0) if win else -s
            status = "won" if win else "lost"
        else:
            pnl = -s * (p - 1.0) if win else s
            status = "lost" if win else "won"
        raw.append((leg, status, pnl))
        gross_market[leg.market] = gross_market.get(leg.market, 0.0) + pnl
        if pnl > 0:
            pos_market[leg.market] = pos_market.get(leg.market, 0.0) + pnl
    comm_market: Dict[str, float] = {}
    for m, v in gross_market.items():
        comm_market[m] = round(max(0.0, v) * float(commission), 2) if v > 0 else 0.0
    per_leg: List[Tuple[str, str, float]] = []
    per_leg_gross: List[Tuple[str, str, float]] = []
    by_market: Dict[str, List[int]] = {}
    for leg, status, pnl in raw:
        share = 0.0
        pos = pos_market.get(leg.market, 0.0)
        if pnl > 0 and pos > 0 and comm_market.get(leg.market, 0.0) > 0:
            share = comm_market[leg.market] * (pnl / pos)
        per_leg_gross.append((leg.ref, status, round(pnl, 2)))
        per_leg.append((leg.ref, status, round(pnl - share, 2)))
        if leg.market in gross_market and leg.matched > 0:
            by_market.setdefault(leg.market, []).append(len(per_leg) - 1)
    per_market = {m: round(_net(v, commission), 2) for m, v in gross_market.items()}
    # §4.15 — la somma dei P&L delle RIGHE deve fare ESATTAMENTE il P&L della
    # partita: arrotondare ogni riga al centesimo in modo indipendente lasciava
    # fino a 0,02 EUR di scarto fra ``sum(mike_trades.pnl)`` e ``settled_pnl``
    # (tabella Trade che non torna con la partita, e lo storico che eredita lo
    # scarto). Il residuo va sulla riga di PESO maggiore del mercato (in utile se
    # ce n'e' una): e' un centesimo, e cade dove si nota di meno.
    for market, idxs in by_market.items():
        target = per_market.get(market)
        if target is None or not idxs:
            continue
        diff = round(target - sum(per_leg[i][2] for i in idxs), 2)
        if abs(diff) < 0.005:
            continue
        winners = [i for i in idxs if per_leg[i][2] > 0]
        pick = max(winners or idxs, key=lambda i: (abs(per_leg[i][2]), -i))
        ref, status, val = per_leg[pick]
        per_leg[pick] = (ref, status, round(val + diff, 2))
    net = round(sum(per_market.values()), 2)
    return SettleResult(per_leg=per_leg, per_market=per_market, net=net,
                        per_leg_gross=per_leg_gross, commission_by_market=comm_market)


# ---------------------------------------------------------------------------
# Helper di stato
# ---------------------------------------------------------------------------
def _legs(ctx: MatchCtx, role: Optional[str] = None, live: Optional[bool] = None) -> List[Leg]:
    out = []
    for leg in ctx.legs:
        if role is not None and leg.role != role:
            continue
        if live is True and not leg.is_live:
            continue
        if live is False and leg.is_live:
            continue
        out.append(leg)
    return out


def _last(ctx: MatchCtx, role: str) -> Optional[Leg]:
    legs = _legs(ctx, role)
    return legs[-1] if legs else None


def _cancel_live(ctx: MatchCtx, roles: Optional[Tuple[str, ...]] = None) -> List[Action]:
    return [Action(kind="cancel", ref=l.ref, role=l.role, market=l.market, selection=l.selection)
            for l in ctx.legs if l.is_live and (roles is None or l.role in roles)]


def _place(role: str, market: str, selection: str, side: str, price: float, size: float,
           persistence: str = "LAPSE", final: bool = False, note: str = "") -> Action:
    return Action(kind="place", role=role, market=market, selection=selection, side=side,
                  price=float(round_to_tick(price)), size=round(float(size), 2),
                  persistence=persistence, final=final, note=note)


def _under_position(ctx: MatchCtx) -> Tuple[float, Optional[float]]:
    return position(ctx.legs, MARKET_OU35, SEL_UNDER, UNDER_ROLES)


def cashout_base(ctx: MatchCtx, params: Dict[str, Any]) -> float:
    """Base percentuale del cash-out: capitale investito (``total``) o solo
    l'Under (``under``). Pubblica: la usa anche il servizio per la card."""
    if params.get("cashout_base") == "under":
        return _under_position(ctx)[0]
    return invested(ctx.legs)


_cashout_base = cashout_base       # retro-compatibilita' interna


def cover_place_price(best_back: Optional[float], params: Dict[str, Any]) -> Optional[float]:
    """Prezzo a cui PIAZZARE la copertura: ``cover_place_at_ticks`` sotto il best.

    CERT. 12/09 — con il ritardo di piazzamento in gioco un ordine al prezzo
    esatto muore (misurati 188 tentativi per 13 coperture abbinate). Qualche
    tick di quota in meno e' il prezzo per entrare davvero. La size si
    dimensiona SU QUESTO prezzo, mai sul best: e' qui che la copertura entra.
    """
    if best_back is None or not price_ok(best_back):
        return None
    n = int(params.get("cover_place_at_ticks") or 0)
    if n <= 0:
        return float(best_back)
    try:
        cand = float(ticks_away(float(best_back), -n))
    except Exception:  # noqa: BLE001 - prezzo fuori scala: si resta al best
        return float(best_back)
    return cand if (price_ok(cand) and cand > 1.0) else float(best_back)


def liability_room(ctx: MatchCtx, params: Dict[str, Any]) -> float:
    """Capitale ancora piazzabile sulla partita sotto ``max_liability_per_match``
    (0 = nessun tetto → inf). Clamp DIFENSIVO dentro l'engine: vale anche se il
    livello esterno e' mal configurato (review F0, HIGH #3)."""
    cap = float(params.get("max_liability_per_match") or 0.0)
    if cap <= 0:
        return float("inf")
    return max(0.0, cap - invested(ctx.legs))


def size_chiudibile(size: Optional[float]) -> bool:
    """La size di una CHIUSURA e' abbastanza grande da essere accettata?

    Betfair rifiuta gli ordini sotto ``IT_BACK_MIN`` (2 EUR). Su una quota molto
    salita la size che chiude la posizione puo' scendere sotto quella soglia:
    quel residuo NON e' chiudibile, e continuare a provarci produce solo righe
    in errore. Una posizione con un residuo cosi' piccolo vale meno del minimo
    piazzabile: la si porta al regolamento.
    """
    if not size_ok(size):
        return False
    return float(size) >= IT_BACK_MIN - 0.005


def _close_actions(ctx: MatchCtx, cv: CashoutValue, params: Dict[str, Any],
                   role_map: Optional[Dict[Tuple[str, str], str]] = None) -> List[Action]:
    role_map = role_map or {
        (MARKET_OU35, SEL_UNDER): "under_close",
        (MARKET_OU45, SEL_OVER): "over_close",
        (MARKET_OU45, SEL_UNDER): "reentry_green",
    }
    acts = []
    for key, plan in cv.plans.items():
        if not plan.actionable:
            continue
        # CERTIFICAZIONE 12/09 — RESIDUO NON CHIUDIBILE.
        # Su una quota salita molto, la size che chiude la posizione scende sotto
        # il minimo Betfair (2 EUR): l'exchange rifiuta l'ordine. Prima si
        # tentava lo stesso a OGNI ciclo, e ogni tentativo lasciava una riga
        # 'error' sul DB (osservato dal vivo: 64 righe fallite sulla stessa
        # posizione, e il residuo non si chiudeva comunque). Non si tenta:
        # la posizione resta aperta fino al regolamento, che e' l'unico esito
        # possibile, e il servizio lo dichiara una volta sola.
        if not size_chiudibile(plan.size):
            continue
        acts.append(_place(role_map[key], key[0], key[1], plan.side, plan.price, plan.size,
                           note=plan.note))
    return acts


MANUAL_ROLE_MAP = {(MARKET_OU35, SEL_UNDER): "manual_close",
                   (MARKET_OU45, SEL_OVER): "manual_close",
                   (MARKET_OU45, SEL_UNDER): "manual_close"}


def force_flat_plan(ctx: MatchCtx, books: Dict[Tuple[str, str], Book],
                    params: Dict[str, Any], goals: Optional[int] = None,
                    role_map: Optional[Dict[Tuple[str, str], str]] = None
                    ) -> Tuple[List[Action], List[Action]]:
    """(cancel, close) per una chiusura forzata (cash out / flatten dalla UI).

    H1: i due gruppi sono SEPARATI perche' vanno eseguiti in ORDINE — prima si
    cancellano gli ordini vivi (una lay di green-up appoggiata che resta sul
    book lascerebbe una posizione netta lay SCOPERTA), solo dopo si chiude la
    posizione netta. C2: le selezioni con esito gia' deciso non hanno prezzo e
    non vengono chiuse (non serve: valgono 0/1).
    """
    c = float(params["commission_pct"]) / 100.0
    cv = cashout_value(ctx.legs, books, c, int(params["cashout_place_at_ticks"]), goals=goals)
    return (_cancel_live(ctx), _close_actions(ctx, cv, params, role_map))


def force_flat_actions(ctx: MatchCtx, books: Dict[Tuple[str, str], Book],
                       params: Dict[str, Any], goals: Optional[int] = None) -> List[Action]:
    """Chiusura al best di ogni selezione aperta (richiesta manuale / stop)."""
    cancels, closes = force_flat_plan(ctx, books, params, goals)
    return cancels + closes


def _pending_closings(ctx: MatchCtx) -> List[Leg]:
    return [l for l in ctx.legs if l.is_live and l.role in ("under_close", "over_close", "manual_close")]


# ---------------------------------------------------------------------------
# decide
# ---------------------------------------------------------------------------
def has_unknown_orders(ctx: MatchCtx) -> bool:
    """True se una gamba ha esito IGNOTO: nessun nuovo ingresso sulla partita (C3)."""
    return any(l.needs_reconcile for l in ctx.legs)


def _strip_openings(d: Decision, why: str) -> Decision:
    """Toglie da una decisione le APERTURE, lasciando cancel e chiusure (H8).

    Con un ordine a esito IGNOTO l'esposizione reale non e' nota: si continua a
    valutare tutto cio' che RIDUCE il rischio (annulli, cash-out, uscite, cap di
    perdita) e si bloccano solo gli ordini che ne aggiungono.
    """
    kept = [a for a in d.actions if not (a.kind == "place" and a.role in OPENING_ROLES)]
    if len(kept) == len(d.actions):
        return d
    return Decision(state=d.state, actions=kept, reason=f"{d.reason} ({why})",
                    updates=dict(d.updates), telemetry=dict(d.telemetry))


def _decide_flatten(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any]) -> Decision:
    """Chiusura MANUALE in corso (C2): prima si annullano gli ordini vivi, poi si
    chiude la posizione netta delle selezioni ancora VIVE, poi si chiude il ciclo.

    In pre-match si torna a WATCH con il ciclo ARCHIVIATO (il capitale non e' piu'
    a rischio) e ``no_reentry`` attivo: il bot non rientra finche' l'utente non
    riabilita la partita con "Riprendi". In-play si va in FLAT.
    """
    cancels, closes = force_flat_plan(ctx, snap.books, params, snap.goals, MANUAL_ROLE_MAP)
    st_close = "LIVE_CLOSING" if snap.inplay else "PRE_GREEN_PENDING"
    # H1 — si annullano PRIMA gli ordini vivi che aggiungono/lasciano rischio, ma
    # MAI la chiusura manuale gia' al lavoro: ``_cancel_live`` la prendeva dentro e
    # ogni ciclo la cancellava per poi riappoggiarla (place/cancel all'infinito, cash
    # out mai completato quando il fill non e' immediato — coda flumine, REST, fill
    # parziale). La chiusura manuale si riprezza SOLO dopo ``close_retry_s``.
    cancels = [a for a in cancels if a.role != "manual_close"]
    if cancels:
        return Decision(ctx.state, cancels, "chiusura manuale: annullo gli ordini vivi",
                        updates={"close_reason": "manual"})
    working = [l for l in ctx.legs if l.is_live and l.role == "manual_close"]
    if working:
        stale = [l for l in working
                 if snap.now - l.placed_at >= float(params["close_retry_s"])]
        if not stale or ctx.attempts >= int(params["close_max_attempts"]):
            return Decision(st_close, [], "chiusura manuale: attendo il fill",
                            telemetry={"close_retries_exhausted": True,
                                       "attempts": ctx.attempts} if stale else {})
        acts = [Action(kind="cancel", ref=l.ref, role=l.role, market=l.market,
                       selection=l.selection) for l in stale]
        # ``closes`` e' gia' dimensionato sull'esposizione NETTA (la parte abbinata
        # della gamba pending e' dentro ``exposure``): si riprezza il solo residuo.
        return Decision(st_close, acts + closes, "chiusura manuale: riprezzo",
                        updates={"close_reason": "manual", "attempts": ctx.attempts + 1})
    if closes:
        return Decision(st_close, closes,
                        "chiusura manuale: chiudo la posizione",
                        updates={"close_reason": "manual", "attempts": 0})
    if live_open_selections(ctx.legs, snap.goals):
        # posizione ancora VIVA ma nessun prezzo con cui chiuderla: si ASPETTA.
        # Chiudere il ciclo qui archivierebbe una posizione aperta (capitale a
        # rischio invisibile) — mai.
        return Decision(ctx.state, [], "chiusura manuale: prezzi non disponibili, attendo")
    if snap.inplay:
        return Decision("FLAT", [], "chiusura manuale completata",
                        updates={"flatten_pending": False, "reentry_allowed": False,
                                 "reentry_done": True, "_archive_legs": True})
    return Decision("WATCH", [], "chiusura manuale completata (pre-match)",
                    updates={"flatten_pending": False, "no_reentry": True,
                             "cycle_no": ctx.cycle_no + 1, "last_green_at": snap.now,
                             "attempts": 0, "_archive_legs": True})


def decide(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any]) -> Decision:
    st = ctx.state
    if st in TERMINAL_STATES:
        return Decision(st, [], "terminale")

    # mercato chiuso: il regolamento ha sempre la precedenza su tutto
    if snap.market_status != "CLOSED" and st != "SETTLING":
        # C2 — chiusura manuale in corso: nessuna riappoggiata, nessuna apertura
        if ctx.flatten_pending:
            return _decide_flatten(ctx, snap, params)
        # C3 — cash out manuale pre-KO: ingressi disabilitati finche' l'utente
        # non riabilita la partita ("Riprendi")
        if ctx.no_reentry:
            params = dict(params, pre_enabled=False, reentry_enabled=False,
                          last_entry_persist=False)

    d = _dispatch(ctx, snap, params)
    if has_unknown_orders(ctx):
        # H8 — ordine a esito ignoto: via le APERTURE, restano le riduzioni di rischio
        d = _strip_openings(d, "ordine a esito ignoto: nessuna apertura")
    return d


def _dispatch(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any]) -> Decision:
    st = ctx.state
    c = float(params["commission_pct"]) / 100.0

    # -- mercato chiuso: regolamento -------------------------------------------------
    if snap.market_status == "CLOSED" or st == "SETTLING":
        if st != "SETTLING":
            return Decision("SETTLING", _cancel_live(ctx), "mercato chiuso")
        if snap.final_total is None:
            return Decision("SETTLING", [], "attesa punteggio finale")
        res = settle_legs(ctx.legs, int(snap.final_total), c)
        return Decision("SETTLED", [], f"regolato T={snap.final_total}",
                        updates={"settled_pnl": res.net},
                        telemetry={"settle": {"per_leg": res.per_leg, "per_market": res.per_market,
                                              "net": res.net, "per_leg_gross": res.per_leg_gross,
                                              "commission_by_market": res.commission_by_market}})

    if st in ("WATCH", "PRE_ENTRY_PENDING", "PRE_OPEN", "PRE_GREEN_PENDING", "HOLD",
              "PRE_LAST_ENTRY_PENDING"):
        return _decide_prematch(ctx, snap, params, c)
    if st == "IDLE_LIVE":
        if not ctx.legs:
            # mai operata (KO arrivato senza ingresso, o armata a partita gia' iniziata):
            # nulla potra' piu' succedere → chiusa subito, senza P&L
            return Decision("SETTLED", [], "nessuna operazione", updates={"settled_pnl": 0.0})
        return Decision(st, [], "nessuna posizione")
    if st == "LIVE_KO_GREEN":
        return _decide_ko_green(ctx, snap, params, c)
    if st == "LIVE_SECOND_ENTRY":
        return _decide_second_entry(ctx, snap, params, c)
    if st == "LIVE_UNCOVERED":
        return _decide_uncovered(ctx, snap, params, c)
    if st == "LIVE_COVER_PENDING":
        return _decide_cover_pending(ctx, snap, params, c)
    if st == "LIVE_COVERED":
        return _decide_covered(ctx, snap, params, c)
    if st == "LIVE_CLOSING":
        return _decide_closing(ctx, snap, params, c)
    if st == "FLAT":
        return _decide_flat(ctx, snap, params, c)
    if st == "REENTRY_PENDING":
        return _decide_reentry_pending(ctx, snap, params, c)
    if st == "REENTRY_OPEN":
        return _decide_reentry_open(ctx, snap, params, c)
    if st == "REENTRY_GREEN_PENDING":
        return _decide_reentry_green_pending(ctx, snap, params, c)
    return Decision("ERROR", _cancel_live(ctx), f"stato sconosciuto {st}")


# ---- pre-match -------------------------------------------------------------------
def _entry_guard(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any]) -> Optional[str]:
    """None se si puo' entrare, altrimenti il motivo."""
    if ctx.no_reentry:
        # C3: cash out manuale su questa partita → nessun nuovo ingresso
        return "rientro disabilitato (chiusura manuale): premi Riprendi"
    if ctx.flatten_pending:
        return "chiusura manuale in corso"
    if not params["pre_enabled"]:
        return "pre_disabilitato"
    if not snap.feed_fresh:
        return "feed stantio"
    window_from = snap.ko_at - float(params["entry_hours_before_ko"]) * 3600.0
    if snap.now < window_from:
        return "fuori finestra"
    if snap.now >= snap.ko_at - float(params["pre_last_entry_min"]) * 60.0:
        return "finestra pre-match chiusa"
    if ctx.cycle_no >= int(params["pre_max_cycles"]):
        return "max cicli"
    if ctx.last_green_at is not None and snap.now - ctx.last_green_at < float(params["pre_reentry_cooldown_s"]):
        return "cooldown"
    bk = snap.book(MARKET_OU35, SEL_UNDER)
    if bk is None or not price_ok(bk.best_back) or bk.status != "OPEN" or bk.inplay:
        return "book assente"
    if bk.best_back < float(params["pre_entry_price_min"]) or bk.best_back > float(params["pre_entry_price_max"]):
        return f"prezzo {bk.best_back} fuori banda"
    need = float(params["stake"]) * float(params["pre_min_back_size_factor"])
    if float(bk.back_size) < need:
        return f"liquidita {bk.back_size:.2f} < {need:.2f}"
    # Nota M3: ``min_total_matched`` NON e' un gate (vedi config.REMOVED_PARAMS):
    # ore prima del KO lo scambiato e' fisiologicamente basso. Quello che conta
    # per un fill e' la liquidita' al BEST, appena verificata.
    if bk.best_lay is not None:
        t = ticks_between(bk.best_back, bk.best_lay)
        if t is None or t > int(params["pre_max_spread_ticks"]):
            return f"spread {t} tick"
    if float(params["stake"]) > liability_room(ctx, params) + _EPS:
        return "cap liability partita"
    return None


def _decide_prematch(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any], c: float) -> Decision:
    st = ctx.state
    stake = float(params["stake"])
    bk = snap.book(MARKET_OU35, SEL_UNDER)
    S, Pe = _under_position(ctx)
    last_entry_at = snap.ko_at - float(params["pre_last_entry_min"]) * 60.0

    # -- KO arrivato: si passa al live con quello che c'e' ----------------------------
    if snap.inplay:
        acts = []
        for leg in ctx.legs:
            if not leg.is_live:
                continue
            if leg.persistence == "PERSIST" and leg.role == "under_last":
                if snap.now - snap.ko_at < float(params["cancel_unmatched_after_ko_s"]):
                    continue           # grazia: il residuo PERSIST puo' ancora abbinarsi
            acts.append(Action(kind="cancel", ref=leg.ref, role=leg.role, market=leg.market,
                               selection=leg.selection))
        if S > 0:
            upd: Dict[str, Any] = {"entry_price_initial": ctx.entry_price_initial or Pe}
            # il prezzo del fischio si scrive UNA volta: i giri successivi non
            # devono sovrascriverlo col prezzo del 10' o del 40'
            if ctx.ko_price_under is None and bk is not None and price_ok(bk.best_back):
                upd["ko_price_under"] = float(bk.best_back)
            # FLUSSO 13/09 — l'orologio della finestra di uscita parte QUI, alla
            # prima volta che vediamo la partita in gioco con la posizione aperta
            # (non al ``ko_at`` di calendario, che puo' essere anticipato o
            # posticipato rispetto al fischio vero).
            if ctx.live_since is None:
                upd["live_since"] = snap.now
                if snap.goals is not None:
                    upd["ko_goals"] = int(snap.goals)
            if params.get("ko_green_enabled", True) and price_ok(Pe):
                return Decision("LIVE_KO_GREEN", acts,
                                "in gioco: provo l'uscita a +%d tick" % int(params["ko_green_ticks"]),
                                updates=upd)
            upd["cover_forced"] = True
            return Decision("LIVE_UNCOVERED", acts, "in-play con posizione Under", updates=upd)
        return Decision("IDLE_LIVE", acts, "in-play senza posizione")

    if st == "WATCH":
        why = _entry_guard(ctx, snap, params)
        if why:
            return Decision("WATCH", [], why)
        return Decision("PRE_ENTRY_PENDING",
                        [_place("under_entry", MARKET_OU35, SEL_UNDER, "back", bk.best_back, stake)],
                        f"ingresso ciclo {cycle_label(ctx.cycle_no)}")

    if st == "PRE_ENTRY_PENDING":
        leg = _last(ctx, "under_entry")
        if leg is None:
            return Decision("WATCH", [], "gamba assente")
        if not leg.is_live and leg.matched <= 0:
            return Decision("WATCH", [], "ingresso non abbinato")
        if leg.filled and not leg.is_live:
            return _after_entry_fill(ctx, snap, params, leg)
        if leg.is_live and snap.now - leg.placed_at >= float(params["pre_entry_ttl_s"]):
            if leg.matched > 0:
                return Decision("PRE_OPEN", [Action(kind="cancel", ref=leg.ref, role=leg.role)],
                                "ttl: tengo la parte abbinata")
            return Decision("WATCH", [Action(kind="cancel", ref=leg.ref, role=leg.role)], "ttl scaduto")
        if leg.filled:
            return _after_entry_fill(ctx, snap, params, leg)
        return Decision(st, [], "attesa fill ingresso")

    if st == "PRE_OPEN":
        if S <= 0:
            return Decision("WATCH", _cancel_live(ctx), "posizione assente")
        green = _last(ctx, "under_green")
        # ESPOSIZIONE NETTA della selezione (ingresso + eventuali fill PARZIALI della
        # green): e' l'unica base coerente per size di chiusura e P&L bloccato
        w, l = exposure(ctx.legs, MARKET_OU35, SEL_UNDER)
        flat = abs(w - l) < _FLAT_EPS
        # ultimo ingresso: KO - pre_last_entry_min
        if snap.now >= last_entry_at:
            acts = _cancel_live(ctx, ("under_green",))
            if flat:
                return _cycle_done(ctx, snap, S, Pe, green, w)
            if bk is None or bk.best_lay is None:
                return Decision("HOLD", acts, "ultimo ingresso: prezzo lay assente, tengo")
            plan = compute_greenup(matched_if_win=w, matched_if_lose=l, best_back_price=bk.best_back,
                                   best_lay_price=bk.best_lay, fraction=1.0)
            locked = min(plan.expected_if_win, plan.expected_if_lose) if plan.actionable else 0.0
            if plan.actionable and locked > _FLAT_EPS:
                acts.append(_place("under_green", MARKET_OU35, SEL_UNDER, "lay", plan.price,
                                   plan.size, final=True, note="ultimo ingresso: chiusura in profitto"))
                return Decision("PRE_GREEN_PENDING", acts, f"ultimo ingresso: locked {locked:.2f} > 0",
                                telemetry={"last_entry_locked": round(locked, 2)})
            return Decision("HOLD", acts, f"ultimo ingresso: locked {locked:.2f} <= 0, tengo")
        # esposizione piatta (green abbinata per intero) -> ciclo chiuso
        if flat and (green is None or not green.is_live):
            return _cycle_done(ctx, snap, S, Pe, green, w)
        if params["pre_exit_mode"] == "resting":
            # nessuna green viva sul book (mai appoggiata, ritirata, o abbinata SOLO in
            # parte e ritirata): si (ri)appoggia una lay per il RESIDUO al target
            if green is None or not green.is_live:
                target = green_target(Pe, int(params["pre_green_ticks"]))
                plan = compute_greenup(matched_if_win=w, matched_if_lose=l, best_back_price=None,
                                       best_lay_price=None, fraction=1.0, target_price=target)
                if plan.actionable:
                    return Decision("PRE_OPEN",
                                    [_place("under_green", MARKET_OU35, SEL_UNDER, "lay", plan.price, plan.size)],
                                    "green resting appoggiata (residuo)" if green is not None else "green resting appoggiata")
            return Decision("PRE_OPEN", [], "posizione aperta, green resting sul book")
        # taker
        target = green_target(Pe, int(params["pre_green_ticks"]))
        if bk is not None and bk.best_lay is not None and bk.best_lay <= target + _EPS:
            plan = compute_greenup(matched_if_win=w, matched_if_lose=l, best_back_price=bk.best_back,
                                   best_lay_price=bk.best_lay, fraction=1.0)
            if plan.actionable:
                return Decision("PRE_GREEN_PENDING",
                                [_place("under_green", MARKET_OU35, SEL_UNDER, "lay", plan.price, plan.size)],
                                "green taker: 2 tick disponibili")
        return Decision("PRE_OPEN", [], "posizione aperta, in attesa dei 2 tick")

    if st == "PRE_GREEN_PENDING":
        green = _last(ctx, "under_green")
        if green is None:
            return Decision("PRE_OPEN", [], "green assente")
        if not green.is_live and green.matched <= 0:
            # chiusura non abbinata: posizione ancora aperta → si torna a gestirla
            # (finale = KO imminente: HOLD, entrera' in live scoperta)
            return Decision("HOLD" if green.final else "PRE_OPEN", [], "green non abbinata")
        if green.filled and not green.is_live:
            w, l = exposure(ctx.legs, MARKET_OU35, SEL_UNDER)
            if abs(w - l) >= _FLAT_EPS:
                # chiusura taker abbinata SOLO in parte: residuo ancora scoperto →
                # si torna a gestirlo (PRE_OPEN riappoggia/chiude il residuo); la
                # finale (KO imminente) va in HOLD col residuo
                return Decision("HOLD" if green.final else "PRE_OPEN", [], "green parziale: residuo aperto")
            if green.final:
                return _after_final_green(ctx, snap, params, bk, stake)
            return _cycle_done(ctx, snap, S, Pe, green, w)
        if green.is_live and snap.now - green.placed_at >= float(params["close_retry_s"]) and \
                ctx.attempts < int(params["close_max_attempts"]):
            if bk is not None and bk.best_lay is not None:
                w, l = exposure(ctx.legs, MARKET_OU35, SEL_UNDER)
                plan = compute_greenup(matched_if_win=w, matched_if_lose=l, best_back_price=bk.best_back,
                                       best_lay_price=bk.best_lay, fraction=1.0)
                if plan.actionable:
                    return Decision(st, [Action(kind="cancel", ref=green.ref, role=green.role),
                                         _place("under_green", MARKET_OU35, SEL_UNDER, "lay", plan.price,
                                                plan.size, final=green.final)],
                                    "green taker: riprezzo", updates={"attempts": ctx.attempts + 1})
        return Decision(st, [], "attesa fill green")

    if st == "HOLD":
        return Decision("HOLD", [], "in perdita pre-KO: tengo fino al live")

    if st == "PRE_LAST_ENTRY_PENDING":
        return Decision(st, [], "attesa fill ingresso PERSIST")

    return Decision("ERROR", _cancel_live(ctx), f"stato pre-match sconosciuto {st}")


def _after_entry_fill(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any], leg: Leg) -> Decision:
    upd = {}
    if ctx.entry_price_initial is None:
        upd["entry_price_initial"] = leg.fill_price
    acts: List[Action] = []
    if params["pre_exit_mode"] == "resting":
        target = green_target(leg.fill_price, int(params["pre_green_ticks"]))
        w, l = exposure(ctx.legs, MARKET_OU35, SEL_UNDER)
        plan = compute_greenup(matched_if_win=w, matched_if_lose=l, best_back_price=None,
                               best_lay_price=None, fraction=1.0, target_price=target)
        if plan.actionable:
            acts.append(_place("under_green", MARKET_OU35, SEL_UNDER, "lay", plan.price, plan.size,
                               note="take-profit resting"))
    return Decision("PRE_OPEN", acts, "ingresso abbinato", updates=upd)


def _cycle_done(ctx: MatchCtx, snap: Snapshot, S: float, Pe: Optional[float], green: Optional[Leg],
                locked_w: Optional[float] = None) -> Decision:
    # P&L bloccato = esposizione netta reale (W ≈ L a green completa), coerente
    # anche con fill parziali; il calcolo "S·(Pe/p−1)" resta solo come fallback
    if locked_w is not None:
        locked = float(locked_w)
    else:
        locked = locked_pnl_back(S, Pe, green.fill_price) if (Pe and green is not None) else 0.0
    tele = {"pre_cycle": {"cycle": ctx.cycle_no, "entry": Pe, "exit": green.fill_price if green else None,
                          "stake": S, "locked": round(locked, 2),
                          "closed_at": snap.now}}
    # Il ciclo viene ARCHIVIATO: una gamba ancora VIVA sul book diventerebbe
    # 'cancelled' solo nei nostri libri pur restando sull'exchange (posizione
    # invisibile). Prima si annulla davvero.
    # ``{locked:+.2f}``: il segno lo mette il formato — un '+' cablato scriveva
    # "+-0.27" quando il ciclo si chiude sotto zero (fill parziali).
    return Decision("WATCH", _cancel_live(ctx),
                    f"ciclo {cycle_label(ctx.cycle_no)} chiuso: {locked:+.2f}",
                    updates={"cycle_no": ctx.cycle_no + 1, "last_green_at": snap.now,
                             "attempts": 0, "_archive_legs": True},
                    telemetry=tele)


def _after_final_green(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any],
                       bk: Optional[Book], stake: float) -> Decision:
    upd = {"cycle_no": ctx.cycle_no + 1, "last_green_at": snap.now, "attempts": 0, "_archive_legs": True}
    if not params["last_entry_persist"]:
        return Decision("IDLE_LIVE", [], "ultimo ingresso disabilitato", updates=upd)
    if bk is None or not price_ok(bk.best_back) or bk.status != "OPEN":
        return Decision("IDLE_LIVE", [], "ultimo ingresso: book assente", updates=upd)
    need = stake * float(params["pre_min_back_size_factor"])
    if float(bk.back_size) < need:
        return Decision("IDLE_LIVE", [], f"ultimo ingresso: liquidita {bk.back_size:.2f} < {need:.2f}", updates=upd)
    # il ciclo appena chiuso viene archiviato dagli updates → il tetto si misura
    # sul capitale che resta davvero a rischio (qui: zero) piu' il nuovo stake
    if stake > float(params.get("max_liability_per_match") or float("inf")) + _EPS and \
            float(params.get("max_liability_per_match") or 0.0) > 0:
        return Decision("IDLE_LIVE", [], "ultimo ingresso: cap liability partita", updates=upd)
    price = bk.best_back
    n_up = int(params["last_entry_ticks_above"])
    if n_up > 0:
        price = float(ticks_away(price, n_up))
    return Decision("PRE_LAST_ENTRY_PENDING",
                    [_place("under_last", MARKET_OU35, SEL_UNDER, "back", price, stake,
                            persistence="PERSIST")],
                    "ultimo ingresso PERSIST", updates=upd)


# ---- live -----------------------------------------------------------------------
# ---- flusso dal fischio d'inizio (specifica utente 13/09) -------------------
#
# La posizione Under 3.5 abbinata nel pre-match entra in gioco cosi' com'e' (la
# persistenza riguarda solo l'INESEGUITO: una gamba gia' abbinata non viene
# toccata dal cambio di stato). Da li' il bot ha tre strade, e una sola si
# realizza:
#
#   A) l'uscita a +N tick dal nostro punto di ingresso si abbina entro la
#      finestra -> profitto bloccato, NESSUNA copertura, capitale libero;
#   B) la finestra scade senza gol e senza abbinamento -> si annulla l'ordine e
#      si compra la copertura PIENA sull'Over 4.5;
#   C) arriva un gol mentre siamo ancora scoperti e non usciti -> si annulla
#      l'ordine di uscita, si entra una SECONDA volta sull'Under 3.5 al miglior
#      prezzo disponibile (la quota e' salita: alza la media e sfrutta il tempo
#      senza gol), poi ci si copre in DUE tranche distanziate nel tempo.
#
# Dal momento in cui Under 3.5 e Over 4.5 sono entrambi a mercato valgono le
# uscite GLOBALI sulla posizione (``_decide_covered``), non piu' le regole di
# singola gamba: e' per questo che la copertura a tranche passa da LIVE_COVERED
# fra una tranche e l'altra.


def gol_dopo_il_fischio(ctx: MatchCtx, snap: Snapshot) -> bool:
    """Il tabellone dice piu' gol di quanti ce n'erano al fischio?

    Senza baseline (feed muto al calcio d'inizio) la risposta e' NO: meglio
    perdere la seconda puntata che inventarsi un gol che non c'e' stato.
    """
    if snap.goals is None or ctx.ko_goals is None:
        return False
    return int(snap.goals) > int(ctx.ko_goals)


def momento_del_gol(snap: Snapshot) -> float:
    """Istante da cui contare i minuti di attesa della prima tranche.

    Si usa l'orario del gol dichiarato dal feed quando e' plausibile (entro
    l'ultimo quarto d'ora e non nel futuro), altrimenti ADESSO: il feed ha un
    ritardo di 2-3 secondi, non di minuti.
    """
    ts = snap.last_goal_ts
    if ts is not None:
        try:
            eta = float(snap.now) - float(ts)
        except (TypeError, ValueError):
            return float(snap.now)
        if 0.0 <= eta <= 900.0:
            return float(ts)
    return float(snap.now)


def finestra_uscita_scaduta(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any]) -> bool:
    """Sono passati i minuti concessi all'ordine di uscita al fischio?"""
    if ctx.live_since is None:
        return False
    return float(snap.now) - float(ctx.live_since) >= float(params["ko_green_window_s"])


def piano_uscita_ko(ctx: MatchCtx, params: Dict[str, Any],
                    prezzo_ingresso: Optional[float]) -> Optional[GreenupPlan]:
    """Lay di uscita a ``ko_green_ticks`` tick SOTTO il nostro prezzo d'ingresso.

    E' un LIMITE: se il mercato offre di meglio l'ordine si abbina meglio, mai
    peggio. Il prezzo di riferimento e' la MEDIA delle gambe Under abbinate e
    ancora a rischio, cioe' il punto di ingresso reale della posizione.
    """
    if not price_ok(prezzo_ingresso):
        return None
    target = green_target(round_to_tick(float(prezzo_ingresso)), int(params["ko_green_ticks"]))
    w, l = exposure(ctx.legs, MARKET_OU35, SEL_UNDER)
    plan = compute_greenup(matched_if_win=w, matched_if_lose=l, best_back_price=None,
                           best_lay_price=None, fraction=1.0, target_price=target)
    return plan if plan.actionable else None


def _decide_ko_green(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any], c: float) -> Decision:
    """Uscita a +N tick appoggiata dal fischio, per la finestra concessa."""
    S, Pe = _under_position(ctx)
    if S <= 0:
        return Decision("IDLE_LIVE", _cancel_live(ctx), "nessuna posizione Under")
    acts = _late_persist_cancel(ctx, snap, params)
    base: Dict[str, Any] = {}
    if ctx.live_since is None:
        base["live_since"] = snap.now
    if ctx.ko_goals is None and snap.goals is not None:
        base["ko_goals"] = int(snap.goals)
    uscita = _last(ctx, "ko_green")

    def _annulla(leg: Optional[Leg]) -> None:
        if leg is not None and leg.is_live:
            acts.append(Action(kind="cancel", ref=leg.ref, role=leg.role,
                               market=leg.market, selection=leg.selection))

    # -- A) uscita abbinata ---------------------------------------------------
    if uscita is not None and float(uscita.matched) > 0 and not uscita.is_live:
        if not live_open_selections(ctx.legs, snap.goals):
            bloccato = locked_pnl(ctx.legs, c)
            tele = {"ko_green": {"esito": "abbinata", "prezzo": uscita.fill_price,
                                 "size": round(float(uscita.matched), 2),
                                 "ingresso": Pe, "bloccato": bloccato,
                                 "minuto": snap.minute}}
            testo = "%+.2f" % bloccato if bloccato is not None else "chiusa"
            return Decision("FLAT", acts, "uscita al fischio: %s" % testo,
                            updates={"close_reason": "profit", "reentry_allowed": True,
                                     "attempts": 0, **base},
                            telemetry=tele)
        # fill PARZIALE consolidato: resta esposizione scoperta -> si copre il
        # residuo, che ``under_liability`` calcola gia' al netto della lay abbinata
        return Decision("LIVE_UNCOVERED", acts, "uscita al fischio parziale: copro il residuo",
                        updates={"cover_forced": True, **base})

    # -- C) gol precoce -------------------------------------------------------
    if gol_dopo_il_fischio(ctx, snap):
        _annulla(uscita)
        upd = dict(base)
        upd["early_goal_at"] = momento_del_gol(snap)
        tele = {"ko_green": {"esito": "gol", "gol": snap.goals, "minuto": snap.minute,
                             "ingresso": Pe}}
        if params.get("second_entry_enabled", True) and not ctx.second_entry_done:
            return Decision("LIVE_SECOND_ENTRY", acts,
                            "gol precoce: seconda puntata sull'Under 3.5",
                            updates=upd, telemetry=tele)
        upd["cover_forced"] = True
        return Decision("LIVE_UNCOVERED", acts, "gol precoce: copertura Over 4.5",
                        updates=upd, telemetry=tele)

    # -- B) finestra scaduta --------------------------------------------------
    if finestra_uscita_scaduta(ctx, snap, params):
        _annulla(uscita)
        tele = {"ko_green": {"esito": "scaduta", "finestra_s": int(params["ko_green_window_s"]),
                             "ingresso": Pe, "minuto": snap.minute}}
        return Decision("LIVE_UNCOVERED", acts,
                        "uscita non abbinata in %d': copertura Over 4.5"
                        % int(float(params["ko_green_window_s"]) // 60),
                        updates={"cover_forced": True, **base}, telemetry=tele)

    # -- l'ordine di uscita: si piazza o si riallinea --------------------------
    plan = piano_uscita_ko(ctx, params, Pe)
    if plan is None:
        return Decision("LIVE_UNCOVERED", acts, "uscita al fischio non calcolabile: copertura",
                        updates={"cover_forced": True, **base})
    # money-critical: con DUE lay vive sull'Under 3.5 un doppio abbinamento
    # ribalterebbe la posizione (da back netto a lay netto). Se una lay di un
    # altro ruolo e' ancora viva (il resting del pre-match in attesa che
    # l'annullamento sia confermato) si aspetta il giro dopo.
    altre_lay = [l for l in ctx.legs
                 if l.is_live and l.side == "lay" and l.market == MARKET_OU35
                 and l.selection == SEL_UNDER and l.role != "ko_green"]
    if altre_lay:
        return Decision("LIVE_KO_GREEN", acts, "attendo l'annullamento della lay precedente",
                        updates=base)
    vivo = uscita if (uscita is not None and uscita.is_live) else None
    if vivo is not None:
        if abs(float(vivo.price) - float(plan.price)) < 1e-9 and \
                abs(float(vivo.size) - float(plan.size)) < 0.01:
            return Decision("LIVE_KO_GREEN", acts, "uscita a +%d tick sul book"
                            % int(params["ko_green_ticks"]), updates=base)
        # la posizione e' cambiata (fill del residuo PERSIST): il prezzo di uscita
        # si ricalcola sulla NUOVA media, altrimenti si chiuderebbe al prezzo sbagliato
        _annulla(vivo)
    if uscita is not None and not uscita.is_live and float(uscita.matched) <= 0 and \
            snap.now - float(uscita.placed_at) < float(params.get("ko_green_retry_s", 5)):
        # il tentativo precedente non e' entrato (in live il prezzo non c'era
        # ancora): si ritenta, ma non a ogni giro del servizio -- 180 secondi a
        # mezzo secondo farebbero 360 righe di attivita' per partita, ed e'
        # esattamente la zavorra che il 13/09 ha causato lo statement timeout
        return Decision("LIVE_KO_GREEN", acts, "uscita: ritento fra poco", updates=base)
    acts.append(_place("ko_green", MARKET_OU35, SEL_UNDER, plan.side, plan.price, plan.size,
                       note="uscita al fischio: %d tick sotto %.2f"
                            % (int(params["ko_green_ticks"]), Pe)))
    resta = max(0.0, round(float(params["ko_green_window_s"])
                           - (snap.now - float(ctx.live_since or snap.now)), 1))
    tele = {"ko_green": {"esito": "appoggiata", "prezzo": plan.price, "size": plan.size,
                         "ingresso": Pe, "tick": int(params["ko_green_ticks"]),
                         "scade_fra_s": resta}}
    return Decision("LIVE_KO_GREEN", acts, "uscita appoggiata a %.2f" % plan.price,
                    updates=base, telemetry=tele)


def _decide_second_entry(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any], c: float) -> Decision:
    """Seconda puntata Under 3.5 dopo un gol precoce, al miglior prezzo disponibile.

    Non deve MAI ritardare la copertura: allo scadere dell'attesa prevista per la
    prima tranche si passa comunque a coprire, con o senza seconda puntata.
    """
    S, Pe = _under_position(ctx)
    if S <= 0:
        return Decision("IDLE_LIVE", _cancel_live(ctx), "nessuna posizione Under")
    acts = _late_persist_cancel(ctx, snap, params)
    leg = _last(ctx, "under_second")
    scaduta = ctx.early_goal_at is not None and \
        snap.now - float(ctx.early_goal_at) >= float(params["early_goal_cover_delay_s"])

    if leg is not None and float(leg.matched) > 0 and not leg.is_live:
        s2, media = _under_position(ctx)
        tele = {"second_entry": {"esito": "abbinata", "prezzo": leg.fill_price,
                                 "size": round(float(leg.matched), 2),
                                 "posizione": s2, "media": media, "minuto": snap.minute}}
        return Decision("LIVE_UNCOVERED", acts,
                        "seconda puntata abbinata a %.2f (media %.2f su %.2f EUR)"
                        % (leg.fill_price, media or 0.0, s2),
                        updates={"second_entry_done": True, "cover_stage": 1,
                                 "cover_forced": True, "attempts": 0},
                        telemetry=tele)

    if leg is not None and leg.is_live:
        if scaduta:
            acts.append(Action(kind="cancel", ref=leg.ref, role=leg.role, market=leg.market,
                               selection=leg.selection))
            return Decision("LIVE_UNCOVERED", acts,
                            "seconda puntata non abbinata in tempo: copertura piena",
                            updates={"second_entry_done": True, "cover_stage": 0,
                                     "cover_forced": True, "attempts": 0})
        return Decision("LIVE_SECOND_ENTRY", acts, "seconda puntata sul book")

    # nessun ordine vivo: si piazza (o si rinuncia se il tempo e' finito)
    rinuncia = {"second_entry_done": True, "cover_stage": 0, "cover_forced": True, "attempts": 0}
    if scaduta:
        return Decision("LIVE_UNCOVERED", acts, "seconda puntata non piazzabile: copertura piena",
                        updates=rinuncia)
    if ctx.attempts >= int(params["close_max_attempts"]):
        return Decision("LIVE_UNCOVERED", acts, "seconda puntata: tentativi esauriti",
                        updates=rinuncia)
    bk = snap.book(MARKET_OU35, SEL_UNDER)
    if bk is None or not price_ok(bk.best_back) or bk.status != "OPEN":
        return Decision("LIVE_SECOND_ENTRY", acts, "seconda puntata: book Under 3.5 assente")
    quota = float(params.get("second_entry_stake_pct", 50.0)) / 100.0
    size = round(float(params["stake"]) * quota, 2)
    if not size_ok(size):
        return Decision("LIVE_UNCOVERED", acts, "seconda puntata: importo nullo", updates=rinuncia)
    if size > liability_room(ctx, params) + _EPS:
        return Decision("LIVE_UNCOVERED", acts, "seconda puntata: cap liability partita",
                        updates=rinuncia)
    if float(bk.back_size) + _EPS < size:
        return Decision("LIVE_SECOND_ENTRY", acts,
                        "seconda puntata: liquidita %.2f < %.2f" % (bk.back_size, size))
    acts.append(_place("under_second", MARKET_OU35, SEL_UNDER, "back", bk.best_back, size,
                       note="seconda puntata dopo gol precoce"))
    return Decision("LIVE_SECOND_ENTRY", acts,
                    "seconda puntata %.2f EUR a %.2f" % (size, bk.best_back),
                    updates={"attempts": ctx.attempts + 1},
                    telemetry={"second_entry": {"esito": "piazzata", "prezzo": bk.best_back,
                                                "size": size, "minuto": snap.minute,
                                                "gol": snap.goals}})


def attesa_prima_tranche(ctx: MatchCtx, snap: Snapshot,
                         params: Dict[str, Any]) -> Optional[float]:
    """Secondi che mancano ai minuti di attesa dal gol prima della PRIMA tranche.

    None = si puo' comprare (attesa finita, o momento del gol sconosciuto).
    """
    if ctx.early_goal_at is None:
        return None
    manca = float(params["early_goal_cover_delay_s"]) - (float(snap.now) - float(ctx.early_goal_at))
    return round(manca, 1) if manca > 0 else None


def frazione_copertura(stage: int, params: Dict[str, Any], x_pieno: Optional[float]
                       ) -> Tuple[float, bool]:
    """(frazione della copertura da comprare ORA, split declassato?).

    Dopo un gol precoce la copertura si compra in due tempi: prima una frazione,
    poi il RESIDUO al prezzo che l'Over avra' in quel momento. Il senso e'
    proprio quello: senza altri gol la quota dell'Over 4.5 sale e la seconda
    meta' costa meno.

    Il minimo di Betfair NON e' piu' un ostacolo: con gli importi esatti
    (``exact_sizes``, il default) una tranche da 1,35 EUR — o da 5 centesimi —
    si piazza col place-and-trim (``omega_market.place_submin_live``). L'unico
    limite che resta e' il centesimo, che e' il floor assoluto dell'exchange.

    Se invece gli importi esatti sono SPENTI dalla UI, gli ordini vengono
    legalizzati al minimo .it: li' dividere avrebbe senso solo se ciascuna metà
    ci arriva da sola, altrimenti si comprerebbe Over di troppo su ENTRAMBE le
    tranche. In quel caso non si divide e si copre in una volta (``True``).
    """
    if int(stage or 0) != 1:
        return (1.0, False)
    f = float(params.get("early_goal_cover_pct", 50.0)) / 100.0
    f = max(0.0, min(1.0, f))
    if f <= 0.0 or f >= 1.0:
        return (1.0, False)
    if x_pieno is None:
        return (f, False)
    piu_piccola_piazzabile = SUBMIN_FLOOR if params.get("exact_sizes", True) else IT_BACK_MIN
    if float(x_pieno) * f >= piu_piccola_piazzabile - 0.0005:
        return (f, False)
    return (1.0, True)


def _decide_uncovered(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any], c: float) -> Decision:
    S, Pe = _under_position(ctx)
    if S <= 0:
        return Decision("IDLE_LIVE", _cancel_live(ctx), "nessuna posizione Under")
    acts = _late_persist_cancel(ctx, snap, params)
    stage = int(ctx.cover_stage or 0)
    # ripiego pulito: se la partita e' stata ripresa senza il momento del gol
    # (riavvio a meta' strada) la copertura a tranche non ha piu' un orologio →
    # si copre in una volta invece di restare scoperti in attesa di niente
    if stage in (1, 2) and ctx.early_goal_at is None:
        stage = 0
    if not params["cover_enabled"]:
        return Decision("LIVE_COVERED", acts, "copertura disabilitata",
                        updates={"cover_skipped": True, "cover_stage": 0, "cover_forced": False})
    if stage == 1:
        manca = attesa_prima_tranche(ctx, snap, params)
        if manca is not None:
            return Decision("LIVE_UNCOVERED", acts,
                            "prima tranche fra %d s (attesa dal gol)" % int(manca),
                            telemetry={"cover_staged": {"stage": 1, "manca_s": manca,
                                                        "minuto": snap.minute}})
    # §4.1 — la copertura si dimensiona sull'esposizione NETTA: se una lay di green
    # e' stata abbinata (anche solo in parte) la liability Under e' minore dello
    # stake e coprire lo stake intero comprerebbe Over di troppo (perdita maggiore
    # con 0-3 gol). ``already`` e' il netto con 5+ gol gia' garantito dal mercato
    # OU45 (coperture parziali gia' abbinate comprese).
    liab = under_liability(ctx.legs)
    already = cover_matched_value(ctx.legs, c)
    bk = snap.book(MARKET_OU45, SEL_OVER)
    price_best = bk.best_back if (bk is not None and price_ok(bk.best_back)) else None
    # CERT. 12/09 — CUSCINETTO in tick: si piazza ``cover_place_at_ticks`` SOTTO
    # il best back, perche' con il ritardo di piazzamento in gioco un ordine al
    # prezzo esatto muore (misurati 188 tentativi per 13 coperture abbinate, e
    # tre partite finite a -10,00 perche' scoperte). La size si dimensiona sul
    # prezzo DI PIAZZAMENTO, non sul best: altrimenti la copertura entrerebbe
    # sotto l'obiettivo di protezione dichiarato (``cover_profit_factor``).
    # La SIZE si dimensiona sul BEST (e' li' che l'ordine si abbina: su un
    # exchange un limite piu' basso prende comunque il miglior prezzo
    # disponibile). Il cuscinetto vale solo come LIMITE dell'ordine, per
    # sopravvivere al movimento durante il ritardo di piazzamento.
    price_over = price_best
    price_limite = cover_place_price(price_best, params)
    n_buf = int(params.get("cover_place_at_ticks") or 0)
    timing = cover_timing(goals=snap.goals, minute=snap.minute, hazard=snap.hazard,
                          p4_market=snap.p4_market, last_goal_ts=snap.last_goal_ts,
                          now=snap.now, params=params,
                          price_over=price_over,
                          cover_gain_pct=snap.cover_gain_pct)
    # la copertura ORDINATA dal flusso (finestra di uscita scaduta, gol precoce)
    # non passa piu' dall'attesa "intelligente": e' gia' stata decisa
    if timing == "wait" and ctx.cover_forced:
        timing = "cover"
    x_pieno = None
    if price_over is not None:
        x_pieno = cover_residual(liab, price_over, c, float(params["cover_profit_factor"]), already)
    frazione, split_declassato = frazione_copertura(stage, params, x_pieno)
    if split_declassato:
        stage = 0
    # piena precisione: l'arrotondamento al centesimo lo fa cover_legal_size,
    # qui una size troncata entrerebbe sotto l'obiettivo di protezione
    x_now = None if x_pieno is None else float(x_pieno) * frazione
    if timing == "skip":
        return Decision("LIVE_COVERED", acts, "copertura saltata: troppi gol",
                        updates={"cover_skipped": True, "cover_stage": 0, "cover_forced": False})
    if liab <= 0.0:
        return Decision("LIVE_COVERED", acts, "nessuna liability Under da coprire",
                        updates={"cover_skipped": True, "cover_stage": 0, "cover_forced": False})
    if timing == "wait" or price_over is None or bk.status != "OPEN":
        tele = {"cover_wait": {"minute": snap.minute, "goals": snap.goals, "hazard": snap.hazard,
                               "p4_market": snap.p4_market, "price_over": price_over,
                               "max_min": int(params["cover_wait_max_min"]),
                               "x_now": x_now}}
        return Decision("LIVE_UNCOVERED", acts, "attendo per coprire", telemetry=tele)
    if not size_ok(x_now):
        return Decision("LIVE_COVERED", acts, "copertura gia' sufficiente",
                        updates={"cover_skipped": True, "cover_stage": 0, "cover_forced": False})
    size, over = cover_legal_size(x_now, params)
    # M3: ``cover_max_overshoot_pct`` CABLATO — con importi legalizzati .it
    # l'arrotondamento per eccesso puo' gonfiare la copertura: oltre il tetto si
    # ripiega su 'floor' (mai comprare piu' Over di quanto la formula chieda).
    cap_over = float(params.get("cover_max_overshoot_pct") or 0.0)
    if cap_over > 0 and over > cap_over + _EPS:
        size2, over2 = legalize_back_size(x_now, "floor")
        if size2 > 0:
            size, over = size2, over2
        if over > cap_over + _EPS:
            return Decision("LIVE_UNCOVERED", acts,
                            f"copertura: overshoot {over:.1f}% oltre il tetto {cap_over:.0f}%",
                            telemetry={"cover_wait": {"minute": snap.minute, "goals": snap.goals,
                                                      "x_now": x_now, "reason": "overshoot"}})
    room = liability_room(ctx, params)
    if room < 0.01:
        return Decision("LIVE_COVERED", acts, "copertura saltata: cap liability partita",
                        updates={"cover_skipped": True, "cover_stage": 0, "cover_forced": False})
    if size > room:
        size = round(room, 2)   # clamp difensivo (mai oltre il tetto per partita)
    if float(bk.back_size) + _EPS < size:
        tele = {"cover_wait": {"minute": snap.minute, "goals": snap.goals, "x_now": x_now,
                               "reason": "liquidita"}}
        return Decision("LIVE_UNCOVERED", acts, f"copertura: liquidita {bk.back_size:.2f} < {size:.2f}",
                        telemetry=tele)
    if not size_ok(size):
        return Decision("LIVE_UNCOVERED", acts, "copertura: size non piazzabile",
                        telemetry={"cover_wait": {"minute": snap.minute, "goals": snap.goals,
                                                  "x_now": x_now, "reason": "size_nulla"}})
    acts.append(_place("over_cover", MARKET_OU45, SEL_OVER, "back",
                       price_limite if price_limite is not None else price_over, size,
                       note=f"X={x_now:.2f} legal={size:.2f} over={over:.1f}% buf={n_buf}t"))
    etichetta = {1: "copertura Over 4.5: prima tranche",
                 3: "copertura Over 4.5: seconda tranche (residuo)"}.get(stage, "copertura Over 4.5")
    if split_declassato:
        etichetta = "copertura Over 4.5 in una volta (la tranche sarebbe sotto il minimo)"
    return Decision("LIVE_COVER_PENDING", acts, etichetta,
                    updates={"cover_stage": stage},
                    telemetry={"cover": {"x": round(x_now, 2), "size": size, "overshoot_pct": over,
                                         "price": price_over, "liability": liab,
                                         "already": round(already, 2), "minute": snap.minute,
                                         "stage": stage, "frazione": round(frazione, 3),
                                         "x_pieno": None if x_pieno is None else round(x_pieno, 2),
                                         "split_declassato": split_declassato}})


def _late_persist_cancel(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any]) -> List[Action]:
    acts = []
    for leg in ctx.legs:
        if leg.is_live and leg.role == "under_last" and \
                snap.now - snap.ko_at >= float(params["cancel_unmatched_after_ko_s"]):
            acts.append(Action(kind="cancel", ref=leg.ref, role=leg.role, market=leg.market,
                               selection=leg.selection))
    return acts


def _decide_cover_pending(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any], c: float) -> Decision:
    leg = _last(ctx, "over_cover")
    if leg is None:
        return Decision("LIVE_UNCOVERED", [], "gamba copertura assente")
    if not leg.is_live and leg.matched <= 0:
        return Decision("LIVE_UNCOVERED", [], "copertura non abbinata: ritento",
                        updates={"attempts": ctx.attempts + 1})
    if leg.filled and not leg.is_live:
        upd: Dict[str, Any] = {"attempts": 0, "cover_forced": False}
        if int(ctx.cover_stage or 0) == 1:
            # prima tranche dentro: da qui partono i minuti prima della seconda.
            # Nel frattempo si passa da LIVE_COVERED, dove valgono le uscite
            # GLOBALI sulla posizione (Under 3.5 + Over 4.5 sono entrambi a mercato).
            upd["cover_stage"] = 2
            upd["cover_stage1_at"] = snap.now
            return Decision("LIVE_COVERED", [], "prima tranche di copertura abbinata", updates=upd)
        upd["cover_stage"] = 0
        return Decision("LIVE_COVERED", [], "copertura abbinata", updates=upd)
    if leg.is_live and snap.now - leg.placed_at >= float(params["close_retry_s"]) and \
            ctx.attempts < int(params["close_max_attempts"]):
        bk = snap.book(MARKET_OU45, SEL_OVER)
        if bk is not None and price_ok(bk.best_back) and leg.remaining > 0:
            # RESIDUO ESATTO sull'esposizione NETTA: la liability Under e' al netto
            # delle lay di green gia' abbinate; ``already`` somma il netto con 5+ gol
            # di TUTTE le coperture gia' abbinate (anche di gambe precedenti gia'
            # cancellate con fill parziale), non solo di questa gamba — altrimenti
            # il riprezzo ricompra Over gia' comprato.
            liab = under_liability(ctx.legs)
            already = cover_matched_value(ctx.legs, c)
            # stesso cuscinetto del primo piazzamento: si dimensiona e si piazza
            # allo STESSO prezzo, altrimenti il riprezzo entra sotto obiettivo
            prezzo_cop = cover_place_price(bk.best_back, params) or bk.best_back
            # size sul BEST (prezzo di abbinamento), limite col cuscinetto
            x = cover_residual(liab, bk.best_back, c, float(params["cover_profit_factor"]), already)
            # sulla PRIMA tranche il riprezzo insegue la stessa frazione, non la
            # copertura piena: altrimenti il riprezzo comprerebbe tutto e la
            # seconda tranche non avrebbe piu' ragione di esistere
            frazione, _declassato = frazione_copertura(int(ctx.cover_stage or 0), params, x)
            x = round(float(x) * frazione, 4)
            if not size_ok(x):
                return Decision("LIVE_COVERED", [Action(kind="cancel", ref=leg.ref, role=leg.role)],
                                "copertura sufficiente", updates={"attempts": 0})
            size, _ = cover_legal_size(x, params)
            if not size_ok(size):
                return Decision("LIVE_COVERED", [Action(kind="cancel", ref=leg.ref, role=leg.role)],
                                "copertura sufficiente", updates={"attempts": 0})
            return Decision("LIVE_COVER_PENDING",
                            [Action(kind="cancel", ref=leg.ref, role=leg.role),
                             _place("over_cover", MARKET_OU45, SEL_OVER, "back", prezzo_cop, size)],
                            "copertura: riprezzo", updates={"attempts": ctx.attempts + 1})
    return Decision("LIVE_COVER_PENDING", [], "attesa fill copertura")


def _loss_rule(snap: Snapshot, params: Dict[str, Any]) -> Optional[Tuple[float, str]]:
    """(pct, etichetta) della regola di perdita tollerata applicabile ora, o None."""
    if snap.ht_active and params["ht_loss_exit_enabled"]:
        return (float(params["ht_loss_pct"]), "ht")
    if snap.minute is not None and params["h2_loss_exit_enabled"] and \
            int(params["h2_loss_from_min"]) <= int(snap.minute) <= int(params["h2_loss_to_min"]):
        return (float(params["h2_loss_pct"]), "2t")
    return None


def _decide_covered(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any], c: float) -> Decision:
    if not live_open_selections(ctx.legs, snap.goals):
        return Decision("FLAT", [], "nessuna esposizione gestibile")
    acts = _late_persist_cancel(ctx, snap, params)
    cv = cashout_value(ctx.legs, snap.books, c, int(params["cashout_place_at_ticks"]), goals=snap.goals)
    base = _cashout_base(ctx, params)
    # M5: SEMPRE netto commissione lato servizio (``net``); ``gross`` e ``per``
    # restano per trasparenza, ``commission`` e' l'aliquota usata.
    tele = {"cashout": {"net": cv.net, "gross": cv.gross, "base": base, "complete": cv.complete,
                        "per": {f"{m}|{s}": v for (m, s), v in cv.per_selection_net.items()},
                        "per_gross": {f"{m}|{s}": v for (m, s), v in cv.per_selection.items()},
                        "decided": [f"{m}|{s}" for (m, s) in cv.decided],
                        "commission": round(c, 4),
                        "pct": round(100.0 * cv.net / base, 2) if base > 0 else None}}
    if not cv.complete:
        return Decision("LIVE_COVERED", acts, "prezzi incompleti", telemetry=tele)
    if should_cashout(cv.net, base, float(params["cashout_profit_pct"])):
        return Decision("LIVE_CLOSING", acts + _close_actions(ctx, cv, params),
                        f"profit: {cv.net:.2f} >= {params['cashout_profit_pct']}% di {base:.2f}",
                        updates={"close_reason": "profit", "attempts": 0}, telemetry=tele)
    smart, why, stele = smart_cashout(
        cv_net=cv.net, base=base, legs=ctx.legs, books=snap.books, commission=c, params=params,
        hazard=snap.hazard, pressure=float(snap.pressure or 1.0), goals=snap.goals,
        model_probs=snap.model_probs, place_at_ticks=int(params["cashout_place_at_ticks"]))
    tele["cashout"]["smart"] = stele
    if smart:
        return Decision("LIVE_CLOSING", acts + _close_actions(ctx, cv, params),
                        f"profit smart: {cv.net:.2f} ({why})",
                        updates={"close_reason": "profit", "attempts": 0}, telemetry=tele)
    rule = _loss_rule(snap, params)
    if rule is not None:
        pct, label = rule
        gmin, gmax = int(params["ht_loss_goals_min"]), int(params["ht_loss_goals_max"])
        in_goals = snap.goals is not None and gmin <= int(snap.goals) <= gmax
        decided = None
        if in_goals and params.get("loss_exit_mode", "model") == "model":
            # ``active_legs``: il P&L dei cicli ARCHIVIATI e' identico su ogni totale
            # (posizione chiusa) e NON e' dentro ``cv.net`` — lasciarlo nel ramo
            # "tengo" e non in quello "chiudo ora" spostava la soglia di quel
            # profitto gia' bloccato e faceva tenere posizioni da chiudere.
            decided, why, ltele = loss_exit_model(
                cv_net=cv.net, base=base, pnl_by_total=net_pnl_by_total(active_legs(ctx.legs), c),
                p_total_model=snap.p_total_model, p_total_emp=snap.p_total_emp,
                p4_market=snap.p4_market, params=params,
                p_total_market=snap.p_total_market)
            ltele["window"] = label
            tele["loss_exit"] = ltele
            if decided:
                # CERT. 12/09 — la telemetria della decisione finiva solo in
                # ``last_loss_exit`` sullo stato dell'evento, quindi veniva
                # SOVRASCRITTA al ciclo dopo: delle chiusure in perdita non
                # restava nulla da verificare. Questa riga e' permanente e dice
                # perche' si e' chiuso: EV del tenere, premio, P(4), fonte.
                tele["loss_exit_deciso"] = {**ltele, "cv_net": round(cv.net, 2),
                                            "base": round(base, 2), "motivo": why,
                                            "minuto": snap.minute, "gol": snap.goals}
                return Decision("LIVE_CLOSING", acts + _close_actions(ctx, cv, params),
                                f"uscita a modello ({label}): {why}",
                                updates={"close_reason": f"loss_{label}", "attempts": 0}, telemetry=tele)
        if decided is None and loss_exit_ok(cv.net, base, pct, goals=snap.goals, gmin=gmin, gmax=gmax):
            tele.setdefault("loss_exit", {"mode": "fixed", "window": label, "pct": pct})
            tele["loss_exit_deciso"] = {"mode": "fixed", "window": label, "pct": pct,
                                        "cv_net": round(cv.net, 2), "base": round(base, 2),
                                        "minuto": snap.minute, "gol": snap.goals,
                                        "motivo": f"regola fissa: {cv.net:.2f} entro {pct}% di {base:.2f}"}
            return Decision("LIVE_CLOSING", acts + _close_actions(ctx, cv, params),
                            f"loss tollerata ({label}): {cv.net:.2f} entro {pct}% di {base:.2f}",
                            updates={"close_reason": f"loss_{label}", "attempts": 0}, telemetry=tele)
    cap = float(params["event_loss_cap_pct"])
    if cap > 0 and base > 0 and cv.net <= -base * cap / 100.0:
        return Decision("LIVE_CLOSING", acts + _close_actions(ctx, cv, params),
                        f"cap perdita evento: {cv.net:.2f}",
                        updates={"close_reason": "loss_cap", "attempts": 0}, telemetry=tele)
    # SECONDA TRANCHE — le uscite globali qui sopra hanno la precedenza: se la
    # posizione si chiude non c'e' piu' niente da coprire. Solo se si tiene, e
    # solo quando l'attesa e' finita, si completa la copertura sul RESIDUO, che
    # ``cover_residual`` ricalcola al prezzo dell'Over di QUEL momento e a quanto
    # la prima tranche ha gia' garantito (mai "l'altra meta' dello stesso importo").
    if int(ctx.cover_stage or 0) == 2 and ctx.cover_stage1_at is not None and \
            snap.now - float(ctx.cover_stage1_at) >= float(params["early_goal_cover2_delay_s"]):
        tele["cover_staged"] = {"stage": 2, "atteso_s": round(snap.now - float(ctx.cover_stage1_at), 1),
                                "minuto": snap.minute}
        return Decision("LIVE_UNCOVERED", acts, "seconda tranche: completo la copertura",
                        updates={"cover_stage": 3, "cover_forced": True}, telemetry=tele)
    return Decision("LIVE_COVERED", acts, "tengo", telemetry=tele)


def _decide_closing(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any], c: float) -> Decision:
    pend = _pending_closings(ctx)
    # C2: una chiusura in attesa su una selezione GIA' DECISA non si abbinera'
    # mai a un prezzo sensato (la linea e' potata dal feed): si ritira.
    dead = [l for l in pend if selection_decided(l.market, l.selection, snap.goals) is not None]
    if dead:
        return Decision("LIVE_CLOSING",
                        [Action(kind="cancel", ref=l.ref, role=l.role, market=l.market,
                                selection=l.selection) for l in dead],
                        "chiusura su selezione gia' decisa: annullo")
    if not pend:
        if live_open_selections(ctx.legs, snap.goals):
            # residuo non chiuso (fill parziale gia' consolidato): riprova
            cv = cashout_value(ctx.legs, snap.books, c, int(params["cashout_place_at_ticks"]),
                               goals=snap.goals)
            acts = _close_actions(ctx, cv, params)
            if acts and ctx.attempts < int(params["close_max_attempts"]):
                return Decision("LIVE_CLOSING", acts, "chiusura residuo",
                                updates={"attempts": ctx.attempts + 1})
        upd = {"reentry_allowed": ctx.close_reason == "profit", "attempts": 0}
        return Decision("FLAT", [], f"chiuso ({ctx.close_reason})", updates=upd)
    acts: List[Action] = []
    if ctx.attempts >= int(params["close_max_attempts"]):
        # tentativi esauriti: si resta in attesa (chiusura naturale a fine
        # mercato / force_flat dalla UI), ma lo si DICE in telemetria
        return Decision("LIVE_CLOSING", [], "chiusura: tentativi esauriti",
                        telemetry={"close_retries_exhausted": True, "attempts": ctx.attempts})
    for leg in pend:
        if snap.now - leg.placed_at < float(params["close_retry_s"]):
            continue
        bk = snap.book(leg.market, leg.selection)
        if bk is None:
            continue
        # riprezzo del RESIDUO: l'esposizione include la parte gia' abbinata della
        # gamba pending (fix review F0: escluderla avrebbe raddoppiato la copertura)
        w, l = exposure(ctx.legs, leg.market, leg.selection)
        plan = compute_greenup(matched_if_win=w, matched_if_lose=l, best_back_price=bk.best_back,
                               best_lay_price=bk.best_lay, fraction=1.0,
                               place_at_ticks=int(params["cashout_place_at_ticks"]))
        acts.append(Action(kind="cancel", ref=leg.ref, role=leg.role, market=leg.market,
                           selection=leg.selection))
        if plan.actionable:
            acts.append(_place(leg.role, leg.market, leg.selection, plan.side, plan.price, plan.size))
    if acts:
        return Decision("LIVE_CLOSING", acts, "chiusura: riprezzo", updates={"attempts": ctx.attempts + 1})
    return Decision("LIVE_CLOSING", [], "attesa fill chiusura")


def residuo_non_chiudibile(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any],
                           c: float) -> bool:
    """L'esposizione ancora aperta e' cosi' piccola che NESSUN ordine puo'
    chiuderla (ogni gamba starebbe sotto il minimo Betfair di 2 EUR)?

    CERTIFICAZIONE 12/09 (osservata dal vivo) — senza questo controllo lo stato
    FLAT tornava a LIVE_COVERED per "esposizione residua", la chiusura veniva
    rifiutata perche' sotto il minimo, e si ricominciava: 222 oscillazioni
    registrate in poche ore, con una riga in errore a ogni giro. Un residuo che
    l'exchange non accetta non e' gestibile: lo si tiene fino al regolamento e
    lo si dichiara UNA volta, invece di inseguirlo per sempre.
    """
    try:
        cv = cashout_value(ctx.legs, snap.books, c, int(params["cashout_place_at_ticks"]),
                           goals=snap.goals)
    except Exception:  # noqa: BLE001 - senza prezzi non si decide nulla
        return False
    piani = [pl for pl in cv.plans.values() if pl.actionable]
    if not piani:
        return False
    return all(not size_chiudibile(pl.size) for pl in piani)


def _decide_flat(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any], c: float) -> Decision:
    if live_open_selections(ctx.legs, snap.goals):
        if residuo_non_chiudibile(ctx, snap, params, c):
            # niente oscillazione FLAT <-> LIVE_COVERED: il residuo resta e si
            # porta al regolamento, dichiarandolo
            return Decision("FLAT", [], "residuo sotto il minimo Betfair: si porta al regolamento")
        return Decision("LIVE_COVERED", [], "esposizione residua")
    if ctx.no_reentry:
        return Decision("FLAT", [], "flat: rientro disabilitato (chiusura manuale)")
    if not params["reentry_enabled"] or not ctx.reentry_allowed or ctx.reentry_done:
        return Decision("FLAT", [], "flat")
    if not snap.feed_fresh or snap.goals is None or snap.minute is None:
        return Decision("FLAT", [], "flat: dati feed mancanti")
    g = int(snap.goals)
    if g < 1 or g > int(params["reentry_max_goals"]):
        return Decision("FLAT", [], f"flat: {g} gol fuori range re-ingresso")
    if int(snap.minute) > int(params["reentry_until_min"]):
        return Decision("FLAT", [], "flat: oltre il minuto di re-ingresso")
    bk = snap.book(MARKET_OU45, SEL_UNDER)          # linea gol+3.5 con 1 gol = Under 4.5
    if bk is None or bk.best_back is None or bk.status != "OPEN":
        return Decision("FLAT", [], "flat: book Under 4.5 assente")
    if params["reentry_price_min_over_entry"] and ctx.entry_price_initial is not None and \
            bk.best_back <= float(ctx.entry_price_initial) + _EPS:
        return Decision("FLAT", [], f"flat: U4.5 {bk.best_back} <= ingresso {ctx.entry_price_initial}")
    stake = float(params["stake"])
    if float(bk.back_size) < stake * float(params["pre_min_back_size_factor"]):
        return Decision("FLAT", [], "flat: liquidita re-ingresso")
    if stake > liability_room(ctx, params) + _EPS:
        return Decision("FLAT", [], "flat: cap liability partita")
    return Decision("REENTRY_PENDING",
                    [_place("reentry", MARKET_OU45, SEL_UNDER, "back", bk.best_back, stake)],
                    "re-ingresso Under 4.5")


def _decide_reentry_pending(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any], c: float) -> Decision:
    leg = _last(ctx, "reentry")
    if leg is None:
        return Decision("FLAT", [], "gamba re-ingresso assente")
    if not leg.is_live and leg.matched <= 0:
        return Decision("FLAT", [], "re-ingresso non abbinato", updates={"reentry_done": True})
    if leg.filled and not leg.is_live:
        target = green_target(leg.fill_price, int(params["reentry_green_ticks"]))
        w, l = exposure(ctx.legs, MARKET_OU45, SEL_UNDER)
        plan = compute_greenup(matched_if_win=w, matched_if_lose=l, best_back_price=None,
                               best_lay_price=None, fraction=1.0, target_price=target)
        acts = [_place("reentry_green", MARKET_OU45, SEL_UNDER, "lay", plan.price, plan.size)] \
            if plan.actionable else []
        return Decision("REENTRY_OPEN", acts, "re-ingresso abbinato")
    if leg.is_live and snap.now - leg.placed_at >= float(params["pre_entry_ttl_s"]):
        if leg.matched > 0:
            return Decision("REENTRY_OPEN", [Action(kind="cancel", ref=leg.ref, role=leg.role)], "ttl: parte abbinata")
        return Decision("FLAT", [Action(kind="cancel", ref=leg.ref, role=leg.role)], "ttl re-ingresso",
                        updates={"reentry_done": True})
    return Decision("REENTRY_PENDING", [], "attesa fill re-ingresso")


def _decide_reentry_open(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any], c: float) -> Decision:
    green = _last(ctx, "reentry_green")
    w, l = exposure(ctx.legs, MARKET_OU45, SEL_UNDER)
    if abs(w - l) < _FLAT_EPS:
        return Decision("FLAT", _cancel_live(ctx, ("reentry_green",)), "re-ingresso chiuso",
                        updates={"reentry_done": True})
    # (green abbinata SOLO in parte e non piu' viva → esposizione non piatta → si
    #  riappoggia una lay per il residuo, sotto)
    bk = snap.book(MARKET_OU45, SEL_UNDER)
    exit_min = int(params.get("reentry_exit_until_min") or 0)      # 0 = mai (si va a fine gara)
    if exit_min > 0 and snap.minute is not None and int(snap.minute) >= exit_min:
        if params["reentry_hold_if_loss"]:
            return Decision("REENTRY_OPEN", [], "oltre il limite: tengo (hold_if_loss)")
        acts = _cancel_live(ctx, ("reentry_green",))
        if bk is not None and bk.best_lay is not None:
            plan = compute_greenup(matched_if_win=w, matched_if_lose=l, best_back_price=bk.best_back,
                                   best_lay_price=bk.best_lay, fraction=1.0)
            if plan.actionable:
                acts.append(_place("reentry_green", MARKET_OU45, SEL_UNDER, plan.side, plan.price, plan.size))
                return Decision("REENTRY_GREEN_PENDING", acts, "re-ingresso: chiusura a mercato",
                                updates={"close_reason": "reentry_time"})
        return Decision("REENTRY_OPEN", acts, "re-ingresso: prezzo assente")
    if green is None or not green.is_live:
        S, Pe = position(ctx.legs, MARKET_OU45, SEL_UNDER, ("reentry",))
        if Pe:
            target = green_target(Pe, int(params["reentry_green_ticks"]))
            plan = compute_greenup(matched_if_win=w, matched_if_lose=l, best_back_price=None,
                                   best_lay_price=None, fraction=1.0, target_price=target)
            if plan.actionable:
                return Decision("REENTRY_OPEN",
                                [_place("reentry_green", MARKET_OU45, SEL_UNDER, "lay", plan.price, plan.size)],
                                "green re-ingresso appoggiata")
    return Decision("REENTRY_OPEN", [], "re-ingresso aperto, green sul book")


def _decide_reentry_green_pending(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any], c: float) -> Decision:
    green = _last(ctx, "reentry_green")
    w, l = exposure(ctx.legs, MARKET_OU45, SEL_UNDER)
    if abs(w - l) < _FLAT_EPS or (green is not None and green.filled and not green.is_live):
        return Decision("FLAT", [], "re-ingresso chiuso", updates={"reentry_done": True})
    if green is not None and not green.is_live and green.matched <= 0:
        return Decision("REENTRY_OPEN", [], "chiusura re-ingresso non abbinata")
    if green is not None and green.is_live and snap.now - green.placed_at >= float(params["close_retry_s"]) \
            and ctx.attempts < int(params["close_max_attempts"]):
        bk = snap.book(MARKET_OU45, SEL_UNDER)
        if bk is not None and bk.best_lay is not None:
            plan = compute_greenup(matched_if_win=w, matched_if_lose=l, best_back_price=bk.best_back,
                                   best_lay_price=bk.best_lay, fraction=1.0)
            if plan.actionable:
                return Decision("REENTRY_GREEN_PENDING",
                                [Action(kind="cancel", ref=green.ref, role=green.role),
                                 _place("reentry_green", MARKET_OU45, SEL_UNDER, plan.side, plan.price, plan.size)],
                                "re-ingresso: riprezzo chiusura", updates={"attempts": ctx.attempts + 1})
    return Decision("REENTRY_GREEN_PENDING", [], "attesa fill chiusura re-ingresso")


# ---------------------------------------------------------------------------
# apply_decision
# ---------------------------------------------------------------------------
def apply_decision(ctx: MatchCtx, d: Decision, now: float) -> List[Leg]:
    """Applica stato/updates e crea le gambe pending per le azioni ``place``.

    Le azioni ``cancel`` NON cambiano lo stato della gamba: e' il chiamante
    (strategy) a marcare ``cancelled``/``open`` quando flumine conferma.
    Ritorna le nuove gambe create (in ordine), gia' con ``ref`` deterministico.
    """
    archive = False
    for k, v in d.updates.items():
        if k == "_archive_legs":
            archive = bool(v)
            continue
        setattr(ctx, k, v)
    if archive:
        # gambe del ciclo chiuso: restano nella lista (contabilita' del settlement)
        # ma escono dal capitale a rischio (fix review F0: senza `archived` lo stake
        # dei cicli precedenti si sommava a S e gonfiava copertura e basi %)
        for leg in ctx.legs:
            if leg.archived:
                continue
            if leg.is_live or leg.needs_reconcile:
                # money-critical: una gamba ancora VIVA (o a esito IGNOTO, C3) puo'
                # esistere su Betfair. Darla per 'cancelled' e archiviarla renderebbe
                # INVISIBILE la sua esposizione (fuori da exposure/invested/liability,
                # e ``_assume_matched`` non la vedrebbe piu'). Resta com'e' finche' il
                # chiamante non conferma l'annullamento o la riconciliazione: senza
                # fill non pesa su nessun calcolo.
                continue
            leg.archived = True
    ctx.state = d.state
    new: List[Leg] = []
    for a in d.actions:
        if a.kind != "place":
            continue
        ctx.seq += 1
        ref = a.ref or f"{a.role}-{ctx.cycle_no}-{ctx.seq}"
        leg = Leg(role=a.role, market=a.market, selection=a.selection, side=a.side,
                  price=float(a.price), size=float(a.size), ref=ref, status="pending",
                  placed_at=float(now), persistence=a.persistence, cycle_no=ctx.cycle_no,
                  final=a.final)
        if a.role in CLOSING_ROLES:
            # H4: ogni gamba di chiusura sa QUALE apertura chiude (sul DB:
            # closes_trade_id) → lo storico conta i CICLI, non le gambe
            leg.closes_ref = a.closes_ref or opening_ref(ctx.legs, a.market, a.selection)
        ctx.legs.append(leg)
        new.append(leg)
    if d.actions:
        ctx.last_action_at = float(now)
    return new
