"""Scalper bot (flumine) — micro-scalping mean-reversion a basso rischio.

FILOSOFIA
---------
Logica semplice, esecuzione avanzata. Il bot cerca **micro-profitti costanti**:
entra MAKER su un micro-segnale, cavalca pochi tick e chiude bloccando un
profitto minimo; ripete ogni volta che si presenta un'occasione. Di default
opera SOLO pre-match (``allow_inplay=False``): a partita non iniziata non esiste
rischio di settlement (gol/sospensione), coerente con il profilo "rischio
quasi-zero". L'in-play e' attivabile ma con i limiti di fedelta' del simulatore
(vedi note in fondo).

NESSUN LOOK-AHEAD
-----------------
Tutte le decisioni usano ESCLUSIVAMENTE il book corrente e finestre del passato
(deque per-runner). Non si leggono punteggi, esiti o dati futuri: il replay di
flumine e' forward-only e la strategia non riceve nulla che non sarebbe
disponibile in live allo stesso istante.

MACCHINA A STATI (per selezione)
--------------------------------
``IDLE`` --(gate+segnale)--> ``QUOTING`` (entry maker resting)
``QUOTING`` --(entry riempita)--> ``LOCKING`` (close maker a +scalp_ticks)
``QUOTING`` --(timeout entry)--> ``IDLE`` (cancella, riprova)
``LOCKING`` --(close riempita)--> ``DONE`` (profitto bloccato)
``LOCKING`` --(stop: avversa/timeout)--> ``DONE`` (flatten a mercato)
``DONE`` --(sotto max_cycles)--> ``IDLE`` (nuovo ciclo)

MATEMATICA DEL PROFITTO (green-up, indipendente dall'esito)
-----------------------------------------------------------
Con back matchato ``SB`` @ ``OB`` e lay matchato ``SL`` @ ``OL``:
    net_win  = SB*(OB-1) - SL*(OL-1)
    net_lose = SL - SB
Per chiudere a prezzo ``P`` si piazza (formula generale di green):
    se net_win > net_lose:  LAY  x=(net_win-net_lose)/P  -> locked = net_lose + x
    se net_lose > net_win:  BACK x=(net_lose-net_win)/P  -> locked = net_win  + x
Per uno scalp BACK→LAY a +1 tick il locked e' ``SB*(OB-OL)/OL > 0`` (OB>OL).

DIREZIONE (mean-reversion, niente segno arbitrario sul book)
------------------------------------------------------------
Sul micro-price (mid pesato per liquidita') in finestra:
  * se le quote sono SALITE di >= ``signal_ticks`` -> attesa rientro in giu'
    -> BACK ora (back alto, lay piu' basso dopo) ;
  * se sono SCESE -> attesa rientro in su' -> LAY ora (lay basso, back piu' alto).
La WoM (imbalance di liquidita') e' usata solo come FILTRO di conferma.
"""
from __future__ import annotations

import datetime as _dt
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Tuple

from flumine import BaseStrategy
from flumine.order.order import OrderStatus
from flumine.order.ordertype import LimitOrder
from flumine.order.trade import Trade
from flumine.utils import get_nearest_price, get_price, get_size, price_ticks_away

logger = logging.getLogger(__name__)

# Stake minimo accettato (Betfair / client simulato).
MIN_STAKE: float = 2.0
# Tolleranza per confronti su importi (EUR).
_EPS: float = 1e-9

# Stati flumine di un ordine ancora VIVO sul book (mirror di
# tennis_runner._LIVE_ORDER_STATUSES, fix audit #5): CANCELLING/UPDATING/REPLACING
# sono transizioni con esito NON confermato — mai trattarle come "morto" (una
# cancel inviata puo' ancora perdere la corsa con un fill tardivo).
_LIVE_ORDER_STATUSES = (
    OrderStatus.PENDING,
    OrderStatus.EXECUTABLE,
    OrderStatus.CANCELLING,
    OrderStatus.UPDATING,
    OrderStatus.REPLACING,
)

# Stati della macchina.
# QUOTING  = una gamba resting (modalita' reversion/momentum)
# QUOTING2 = due gambe resting (modalita' market-maker, cattura spread)
IDLE, QUOTING, QUOTING2, CANCELLING, LOCKING, FLATTENING, DONE = (
    "IDLE", "QUOTING", "QUOTING2", "CANCELLING", "LOCKING", "FLATTENING", "DONE"
)


# ---------------------------------------------------------------------------
# Helper PURI (testabili senza flumine)
# ---------------------------------------------------------------------------
def micro_price(
    best_back: Optional[float],
    size_back: Optional[float],
    best_lay: Optional[float],
    size_lay: Optional[float],
) -> Optional[float]:
    """Mid pesato per la liquidita' (micro-price), in spazio QUOTA.

    ``micro = (best_back*size_lay + best_lay*size_back)/(size_back+size_lay)``.
    Pende verso il lato con MENO liquidita' (dove il prezzo tende a muoversi).
    Ritorna ``None`` se i dati non sono sufficienti.
    """
    if not best_back or not best_lay:
        return None
    sb = float(size_back or 0.0)
    sl = float(size_lay or 0.0)
    if sb + sl <= 0:
        return (best_back + best_lay) / 2.0
    return (best_back * sl + best_lay * sb) / (sb + sl)


def wom_imbalance(size_back: Optional[float], size_lay: Optional[float]) -> float:
    """Weight-of-Money imbalance in [-1, 1].

    ``(size_back - size_lay)/(size_back + size_lay)``. 0 se non disponibile.
    """
    sb = float(size_back or 0.0)
    sl = float(size_lay or 0.0)
    tot = sb + sl
    if tot <= 0:
        return 0.0
    return (sb - sl) / tot


def ticks_between(p_low: Optional[float], p_high: Optional[float], max_ticks: int = 200) -> Optional[int]:
    """Numero di tick Betfair tra ``p_low`` (<=) e ``p_high`` (>=).

    0 se uguali; ``None`` se input non validi o ordine invertito. Usa la ladder
    ufficiale via :func:`flumine.utils.price_ticks_away`.
    """
    if not p_low or not p_high or p_high < p_low:
        return None
    p = get_nearest_price(p_low)
    target = get_nearest_price(p_high)
    if p == target:
        return 0
    for t in range(1, max_ticks + 1):
        p = price_ticks_away(p, 1)
        if p >= target - _EPS:
            return t
    return None


def compute_green(
    net_win: float, net_lose: float, price: float
) -> Optional[Tuple[str, float, float]]:
    """Ordine di green per pareggiare net_win/net_lose a prezzo ``price``.

    Ritorna ``(side, size, locked)`` oppure ``None`` se gia' piatto o ``price``
    non valido. ``side`` e' il lato dell'ordine di chiusura ("BACK"/"LAY").
    """
    if price is None or price <= 1.0:
        return None
    diff = net_win - net_lose
    if abs(diff) < _EPS:
        return None
    if diff > 0:  # "lungo" la selezione -> LAY per chiudere
        # LAY x@P: win-=x*(P-1), lose+=x ; equalizza con x=(win-lose)/P
        size = diff / price
        locked = net_lose + size
        return "LAY", size, locked
    # "corto" -> BACK per chiudere
    # BACK x@P: win+=x*(P-1), lose-=x ; equalizza con x=(lose-win)/P
    size = (-diff) / price
    locked = net_lose - size
    return "BACK", size, locked


@dataclass
class _Slot:
    """Stato per (market_id, selection_id)."""

    status: str = IDLE
    entry: Optional[Any] = None          # ordine di ingresso (Order flumine)
    entry_side: Optional[str] = None     # "BACK" | "LAY"
    entry_back: Optional[Any] = None     # gamba BACK (modalita' maker 2-lati)
    entry_lay: Optional[Any] = None      # gamba LAY  (modalita' maker 2-lati)
    close: Optional[Any] = None          # ordine di chiusura (green)
    close_scratched: bool = False        # close gia' ripiazzata a pari (scratch)
    next_entry: Optional[Any] = None     # PIPELINE: ingresso del ciclo dopo,
                                         # in coda DIETRO la close (stesso
                                         # lato/prezzo: mai doppia esposizione)
    flatten_orders: list = field(default_factory=list)  # ordini di flatten (tracciati)
    flat_tries: int = 0                  # tentativi di flatten (escalation aggressivita')
    t_quote: Optional[int] = None        # publish_time ms dell'ingresso piazzato
    t_lock: Optional[int] = None         # publish_time ms del lock avviato
    ref_price: Optional[float] = None    # prezzo di riferimento (mid all'ingresso)
    cycles: int = 0                      # cicli completati su questa selezione
    # contabilita' INCREMENTALE del ciclo corrente (fix audit #6: un ciclo puo'
    # chiudersi PIU' volte — DONE → fill orfano → flatten riaperto — e ogni
    # booking deve accreditare SOLO la differenza rispetto al gia' contabilizzato)
    booked: float = 0.0                  # locked gia' accreditato in pnl_locked
    cycle_counted: bool = False          # ciclo gia' contato in slot.cycles
    history: Deque[Tuple[int, float]] = field(default_factory=lambda: deque(maxlen=64))
    # --- flusso tradato (prints) per lato, per il gate min_flow ---
    prev_trd: Dict[float, float] = field(default_factory=dict)  # ladder trd cumulata
    flow: Deque[Tuple[int, float, float]] = field(default_factory=lambda: deque(maxlen=512))
    last_bb: Optional[float] = None      # best back del tick PRECEDENTE (classificazione)
    last_bl: Optional[float] = None
    first_seen: Optional[int] = None     # primo publish_time visto (warmup flusso)
    cooldown_until: int = 0              # niente ingressi prima di questo ts (gap/loss)
    t_last_flat: Optional[int] = None    # ultimo piazzamento flatten (anti-churn live)
    residual_ok: bool = False            # micro-residuo accettato: NON ri-flattenare
    # sequenze park-trim-replace (uscite a size ESATTA su .it): vedi _drive_submins
    submins: list = field(default_factory=list)
    # prints DENTRO lo spread (ts, EUR): il CIBO diretto dei maker
    flow_inside: Deque[Tuple[int, float]] = field(default_factory=lambda: deque(maxlen=512))
    t_last_submin: int = 0               # rate-limit creazione submin (anti-cascata)
    submin_count: int = 0                # sequenze create nel ciclo corrente (tetto)
    swing: bool = False                  # ciclo originato dal trend (target/stop swing)
    inplay_cycle: bool = False           # ciclo aperto in-play (per circuit breaker)
    # campioni RADI del micro-price (1 ogni ~30s) per la deriva di lungo
    # periodo: history (maxlen 64) copre solo secondi sui mercati veloci
    drift_samples: Deque[Tuple[int, float]] = field(
        default_factory=lambda: deque(maxlen=64))


class TennisScalperStrategy(BaseStrategy):
    """Strategia di micro-scalping mean-reversion — variante TENNIS.

    COPIA di ``scalper_bot.ScalperStrategy`` (logica di esecuzione bit-identica:
    green-up, state machine, _place, join/maker). L'unica differenza e' la
    RI-ABITAZIONE per il tennis: niente kickoff/intervallo, in-play continuo, e
    una gap-guard aggiuntiva guidata dal punteggio (``point_pressure``). Il bot
    del calcio NON e' toccato: questa e' una classe separata in un file separato.


    Parametri (``context`` o kwargs dedicati, tutti con default sensati):

    Esecuzione / rischio
        stake: float = 2.0            size per ingresso (>= MIN_STAKE)
        scalp_ticks: int = 1          tick di profitto target alla chiusura
        stop_ticks: int = 3           tick avversi che innescano lo stop
        entry_ttl_ms: int = 6000      ms max per riempire l'ingresso (poi cancella)
        lock_ttl_ms: int = 20000      ms max in LOCKING prima del flatten
        max_cycles: int = 50          cicli max per selezione/mercato
        allow_inplay: bool = False    se False opera SOLO pre-match

    Gate (selezione automatica dei mercati/momenti adatti)
        max_spread_ticks: int = 2     spread massimo per quotare
        min_size: float = 50.0        liquidita' minima sui best back/lay
        min_total_matched: float = 0  total_matched minimo del runner
        price_min: float = 1.20       quota minima operabile
        price_max: float = 8.0        quota massima operabile
        market_types: set|None        whitelist tipi mercato (None = tutti)

    Segnale (mean-reversion)
        signal_ticks: float = 1.0     movimento (in tick) per innescare il segnale
        signal_window_ms: int = 8000  finestra del momentum sul micro-price
        wom_block: float = 0.85       se |WoM| oltre soglia ED e' contro la
                                      reversion, blocca l'ingresso
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # estrai i parametri dedicati PRIMA di passare il resto a BaseStrategy
        ctx_in: Dict[str, Any] = dict(kwargs.pop("scalper_params", {}) or {})
        # sink di telemetria: callable(kind:str, payload:dict) — opzionale,
        # usato dal servizio live per log/statistiche (mai dalla logica).
        self.event_sink = kwargs.pop("event_sink", None)
        super().__init__(*args, **kwargs)
        c = {**(self.context or {}), **ctx_in}

        # Default = configurazione VALIDATA in backtest (grid 02/07/2026 su
        # dati reali, fill conservativi, commissione 5%): vedi dossier §9.
        self.stake: float = max(MIN_STAKE, float(c.get("stake", 25.0)))
        self.scalp_ticks: int = max(1, int(c.get("scalp_ticks", 1)))
        self.stop_ticks: int = max(1, int(c.get("stop_ticks", 1)))
        # TTL LUNGHI: un maker in coda non cancella per timeout (paga lo
        # spread ogni volta): escono scratch/stop/reprice/KO, non l'orologio.
        self.entry_ttl_ms: int = int(c.get("entry_ttl_ms", 600_000))
        self.lock_ttl_ms: int = int(c.get("lock_ttl_ms", 3_600_000))
        self.max_cycles: int = int(c.get("max_cycles", 500))
        self.allow_inplay: bool = bool(c.get("allow_inplay", False))
        # FINESTRA IN-PLAY (solo backtest/HT-trading): con allow_inplay=True,
        # ingressi consentiti SOLO tra from/to secondi dopo il KO (es.
        # intervallo: 2900-3600 = ~48'-60', zero rischio gol). 0/0 = sempre.
        self.inplay_from_s: float = float(c.get("inplay_from_s", 0.0))
        self.inplay_to_s: float = float(c.get("inplay_to_s", 0.0))
        # tetto di CONCORRENZA in-play: max cicli aperti simultanei (la
        # latenza 5.5s fa slittare gli stop: N slot che perdono INSIEME
        # sfondano il loss cap — visto -8.41 con cap 1.5 su elite HT)
        self.max_inplay_slots: int = int(c.get("max_inplay_slots", 2))
        # CIRCUIT BREAKER per-ciclo in-play: un singolo flatten peggiore di
        # -X EUR = slippage di latenza che mangia (elite HT) -> stop evento.
        self.cycle_loss_breaker: float = float(c.get("cycle_loss_breaker", 0.50))
        # Controllo ESTERNO dell'intervallo (dal feed punteggi via sessione):
        # None = solo finestra a orologio; True/False = intervallo in corso
        # si'/no (clock resta come sanita'). inplay_close_now: chiusura
        # IMMEDIATA dei cicli in-play richiesta dalla sessione (2T ripreso).
        self.ht_active: Optional[bool] = None
        self.inplay_close_now: bool = False
        # chiusura forzata N secondi prima del kickoff (0 = disattivata).
        # Evita di restare con posizioni NUDE al passaggio in-play.
        self.flatten_before_s: float = float(c.get("flatten_before_s", 180.0))
        # stop NUOVI ingressi N secondi prima del kickoff (>= flatten_before_s;
        # 0 = disattivato). Un ciclo aperto a ridosso del KO non ha il tempo
        # di chiudersi da maker: meglio non aprirlo.
        self.entry_stop_before_s: float = float(c.get("entry_stop_before_s", 420.0))

        self.max_spread_ticks: int = int(c.get("max_spread_ticks", 2))
        self.min_size: float = float(c.get("min_size", 150.0))
        self.min_total_matched: float = float(c.get("min_total_matched", 0.0))
        # niente quote basse (<1.5): tick minuscoli, code enormi, cicli
        # lentissimi che finiscono trascinati nel gap del kickoff
        self.price_min: float = float(c.get("price_min", 1.50))
        self.price_max: float = float(c.get("price_max", 4.6))
        mt = c.get("market_types")
        self.market_types: Optional[set] = set(mt) if mt else None

        self.signal_ticks: float = float(c.get("signal_ticks", 1.0))
        # GUARDIA ANTI-GAP: se il movimento recente supera questa soglia (in tick)
        # NON e' una micro-oscillazione da fadere ma una rottura di regime (es. gol):
        # si evita l'ingresso. Protegge dalle perdite da gap.
        self.max_signal_ticks: float = float(c.get("max_signal_ticks", 4.0))
        self.signal_window_ms: int = int(c.get("signal_window_ms", 15000))
        self.wom_block: float = float(c.get("wom_block", 0.90))

        # MODALITA' operativa:
        #   "join"      -> due gambe in coda ai touch (spread stretto 1-2 tick):
        #                  BACK al best lay + LAY al best back, cattura lo spread
        #   "maker"     -> due gambe DENTRO lo spread (spread largo), cattura tick
        #   "reversion" -> una gamba, fade del micro-movimento
        #   "auto"      -> join se spread<=join_max_spread, altrimenti maker se
        #                  dentro la banda capture; MAI reversion implicita
        self.mode: str = str(c.get("mode", "auto")).lower()
        self.inside_ticks: int = max(0, int(c.get("inside_ticks", 1)))
        self.capture_min_ticks: int = max(2, int(c.get("capture_min_ticks", 2)))
        self.capture_max_ticks: int = int(c.get("capture_max_ticks", 12))

        # ---- GATE DI FLUSSO (la lezione dei dati reali: quotare SOLO dove il
        # mercato stampa volume su ENTRAMBI i lati, altrimenti si finisce con
        # una gamba nuda in un mercato morto) ----
        # min_flow: EUR minimi stampati PER LATO nella finestra flow_window_ms.
        self.min_flow: float = float(c.get("min_flow", 10.0))
        # EQUILIBRIO del flusso: min(fb,fl)/max(fb,fl) minimo per quotare
        # two-sided. E' il discriminante fra i mercati che PAGANO il maker
        # (flusso alternato sui due lati, es. Ivory-Norway) e quelli che lo
        # spennano (flusso a senso unico a prezzo fermo, es. elite WC:
        # lay-aggressione 10-40x il lato back → solo fill avversi). 0 = off.
        self.flow_balance_min: float = float(c.get("flow_balance_min", 0.0))
        # OSCILLAZIONE richiesta (il CIBO del maker): nella finestra lunga il
        # mid deve aver fatto almeno un movimento SU e uno GIU' (>=1 tick).
        # Un book congelato o a senso unico (elite pre-match) non nutre i
        # roundtrip: si sanguina a micro-stop. False = off.
        self.require_oscillation: bool = bool(c.get("require_oscillation", False))
        # PRINTS DENTRO LO SPREAD minimi (EUR nella finestra lunga): metrica
        # DIRETTA del cibo dei maker. Ivory-Norway (habitat, +0.67): ~1700
        # EUR/min di prints interni; elite congelata (POR-CRO): ~0. 0 = off.
        self.min_inside_flow: float = float(c.get("min_inside_flow", 0.0))
        # finestra dell'EQUILIBRIO (piu' lunga del gate di flusso: il regime
        # e' una proprieta' lenta, 90s e' rumore)
        self.flow_balance_window_ms: int = int(c.get("flow_balance_window_ms", 300_000))
        self.flow_window_ms: int = int(c.get("flow_window_ms", 90000))
        # warmup: non quotare finche' non abbiamo osservato il runner abbastanza
        self.warmup_ms: int = int(c.get("warmup_ms", self.flow_window_ms))

        # ---- modalita' JOIN (spread stretto) ----
        self.join_max_spread: int = int(c.get("join_max_spread", 2))
        # PRE-POSIZIONAMENTO (quote-behind, "layering" genuino): quota le due
        # gambe N tick DIETRO il touch. Al flip del prezzo la nostra quota E'
        # il nuovo touch con MASSIMA anzianita' di coda (la coda nuova riparte
        # da zero e noi c'eravamo gia'); la cattura vale spread+2N tick.
        # Fill piu' rari ma in prima fila e a prezzo migliore. 0 = off (touch).
        self.join_offset_ticks: int = max(0, int(c.get("join_offset_ticks", 0)))
        # se spread>=2, migliora di 1 tick il lato con la coda peggiore (priorita')
        self.improve_inside: bool = bool(c.get("improve_inside", True))
        # requota se il book si sposta di N tick dalle nostre quote inevase
        self.reprice_ticks: int = max(1, int(c.get("reprice_ticks", 2)))
        # scratch: se il mercato va contro dopo il fill, esci A PARI appena puoi
        self.scratch_enable: bool = bool(c.get("scratch", True))
        # pausa ingressi dopo gap/perdita (ms)
        self.cooldown_ms: int = int(c.get("cooldown_ms", 20000))
        # PIPELINE: durante l'attesa della close, pre-piazza l'ingresso del
        # ciclo successivo dietro di lei (stesso lato/prezzo). Per priorita'
        # di coda si riempie solo DOPO la close -> zero tempo morto tra i
        # cicli senza aumentare l'esposizione direzionale.
        # ⚠️ A/B 02/07 sui dati reali: PEGGIORATIVA (adverse selection sul
        # fill del next_entry). Lasciare OFF salvo nuovo A/B su piu' dati.
        self.pipeline: bool = bool(c.get("pipeline", False))

        # ---- GATE DI FATTIBILITA' DELLA CODA (0 = off) ----
        # non mettersi in coda se l'attesa stimata del fill supera la soglia:
        # attesa ≈ coda_davanti / (flusso_lato/2, come il modello piq flumine).
        # Capitale morto in coda = solo fill avversi quando arrivano.
        self.max_queue_wait_s: float = float(c.get("max_queue_wait_s", 0.0))

        # ---- FILTRO ANTI-DERIVA (0 = off) ----
        # il maker vuole OSCILLAZIONE, non tendenza: se il micro-price ha una
        # deriva netta >= max_drift_ticks nella finestra lunga, salta il runner
        # (visto sui dati: runner in drift lento = scratch continui, zero catture).
        self.max_drift_ticks: float = float(c.get("max_drift_ticks", 0.0))
        self.drift_window_ms: int = int(c.get("drift_window_ms", 300_000))

        # ---- STAKE DINAMICO SUL FLUSSO (stake_max<=stake = off) ----
        # piu' flusso = code che reggono size maggiori: stake interpolato tra
        # stake e stake_max in base a min(flusso back, flusso lay)/flow_ref.
        self.stake_max: float = float(c.get("stake_max", 0.0))
        self.flow_ref: float = float(c.get("flow_ref", 60.0))

        # ---- BIAS DIREZIONALE (modulo "model exec") ----
        # {selection_id: "BACK"|"LAY"}: sulle selezioni indicate NON si quota
        # two-sided ma SOLO dal lato del segnale (sempre da maker al touch:
        # mai taker, mai inseguire). Gli altri runner restano neutri.
        raw_bias = c.get("bias") or {}
        self.bias: Dict[int, str] = {
            int(k): str(v).upper() for k, v in dict(raw_bias).items()
            if str(v).upper() in ("BACK", "LAY")
        }
        # 'bias' puro: quota SOLO le selezioni con bias (niente maker neutro)
        self.only_bias: bool = bool(c.get("only_bias", False))

        # ---- PROTEZIONI LIVE (0 = off, i backtest restano identici) ----
        # live_min_bet: minimo Betfair (2.0 su .it). Gli hedge/close sotto il
        # minimo verrebbero RIFIUTATI dall'exchange lasciando la posizione
        # aperta: qui si arrotonda a 2.0 (over-hedge minuscolo e limitato) o,
        # per residui <0.8, si accetta il micro-rischio e non si piazza.
        self.live_min_bet: float = float(c.get("live_min_bet", 0.0))
        # granularita' delle puntate dell'exchange (.it: MULTIPLI DI 0,50 €,
        # verificato empiricamente 02/07: size 2.03 → INVALID_BET_SIZE,
        # 2.50/2.00 → SUCCESS). 0 = off (backtest: size esatte).
        self.size_step: float = float(c.get("size_step", 0.0))
        # intervallo minimo tra due piazzamenti di flatten sullo stesso slot
        # (anti-churn sui rifiuti istantanei dell'exchange). 0 = off.
        self.flatten_min_interval_ms: int = int(c.get("flatten_min_interval_ms", 0))
        # USCITE A SIZE ESATTA (live .it): come i tool professionali, un'uscita
        # non piazzabile direttamente (multipli 0,50 / minimi) viene spezzata
        # in parte diretta + resto via PARK-TRIM-REPLACE (trading/submin.py:
        # place >= minimo a quota imabbinabile -> cancel parziale alla size
        # esatta -> replace alla quota target). Cosi' si esce con QUALSIASI
        # importo e qualsiasi decimale.
        self.exact_exits: bool = bool(c.get("exact_exits", False))
        # tetto TRANSAZIONI/ora (anti transaction-charge): oltre il budget si
        # bloccano i NUOVI ingressi; hedge/close/flatten passano SEMPRE.
        self.max_txn_hour: int = int(c.get("max_txn_hour", 0))
        self._txn_ts: Deque[float] = deque(maxlen=4096)

        # DRY-RUN: nessun ordine reale; ogni _place viene loggato come
        # "dry_place" (throttled) e ritorna None. Tutto il resto del cervello
        # (gate, segnali, finestre KO) lavora normalmente → cablaggio
        # verificabile in produzione senza rischio.
        self.dry_run: bool = bool(c.get("dry_run", False))
        self._dry_seen: Dict[Tuple[int, str, float], int] = {}

        # FORCE-FLAT: il servizio lo alza per fermare il bot in sicurezza
        # (stesso percorso del near-KO: cancella tutto e chiude flat).
        self.force_flat: bool = False

        # statistiche cumulative (lette dal servizio per la UI)
        self.stats: Dict[str, float] = {
            "orders_placed": 0, "dry_quotes": 0, "cycles": 0,
            "scalps": 0, "roundtrips": 0, "scratches": 0, "stops": 0,
            "flattens": 0, "pnl_locked": 0.0, "pnl_peak": 0.0,
            "trend_entries": 0, "target_hit": 0,
        }

        # ---- TREND SURF (il fix dei "segni negativi" sui mercati in deriva) ----
        # Quando la deriva lunga E il flusso CONCORDANO (mercato in tendenza),
        # il join simmetrico e' vietato li' e si quota UNA SOLA gamba COL
        # flusso: quote in discesa -> BACK al touch (close 1 tick sotto, dove
        # il mercato sta andando); quote in salita -> LAY (close 1 tick sopra).
        # Stop stretto se la tendenza gira. 0/False = off.
        self.trend_mode: bool = bool(c.get("trend_mode", False))
        self.trend_min_ticks: float = float(c.get("trend_min_ticks", 3.0))
        self.trend_flow_ratio: float = float(c.get("trend_flow_ratio", 1.5))
        # SWING (costruzione surebet): gli ingressi originati dal trend usano
        # target/stop DEDICATI piu' larghi: al target la copertura blocca
        # profitto su ogni esito (= surebet della selezione). swing_only=True
        # spegne il maker simmetrico (si opera SOLO col segnale di trend).
        self.swing_target_ticks: int = int(c.get("swing_target_ticks", 0))
        self.swing_stop_ticks: int = int(c.get("swing_stop_ticks", 0))
        self.swing_only: bool = bool(c.get("swing_only", False))

        # ---- TARGET E TETTO DI PERDITA PER EVENTO (0 = off) ----
        # profit target con CRICCHETTO: raggiunto il target si continua, ma
        # se dal picco si restituisce piu' di `giveback` si smette di aprire
        # (i profitti della partita sono protetti). Loss cap = stop duro.
        self.event_profit_target: float = float(c.get("event_profit_target", 0.0))
        self.event_target_giveback: float = float(c.get("event_target_giveback", 0.30))
        self.event_loss_cap: float = float(c.get("event_loss_cap", 0.0))

        # ---- STOP ADATTIVO SUL TEMPO AL KICKOFF (0 = off) ----
        # lontano dal KO il rischio settlement e' solo teorico: stop largo
        # (stop_ticks_far) lascia lavorare la reversione invece di pagare lo
        # spread; avvicinandosi al KO lo stop si stringe linearmente fino a
        # stop_ticks (e le finestre entry_stop/flatten chiudono il resto).
        self.stop_ticks_far: int = int(c.get("stop_ticks_far", 0))
        self.stop_horizon_s: float = float(c.get("stop_horizon_s", 1800.0))

        # stato per (market_id, selection_id)
        self._slots: Dict[Tuple[str, int], _Slot] = {}
        # ordini regolati (dedup per id) per il report del P&L
        self._settled_by_id: Dict[Any, Tuple[Any, str]] = {}
        # kickoff (ms epoch) per market_id, dal market_definition (NON wall-clock:
        # market.seconds_to_start usa datetime.now() ed e' insensato in replay)
        self._ko_ms: Dict[str, Optional[float]] = {}
        # log diagnostico dei cicli chiusi (per analisi, non usato dalla logica)
        self.cycle_log: List[Dict[str, Any]] = []

        # ============================================================== TENNIS
        # RI-ABITAZIONE: il tennis non ha kickoff ne' intervallo. Si opera
        # in-play CONTINUO. Neutralizziamo il modello-tempo calcio SENZA
        # rimuovere il codice provato: con allow_inplay=True i blocchi KO/HT in
        # process_market_book non vengono mai eseguiti (restano solo come
        # gestione di chiusura sotto force_flat manuale). Questo preserva la
        # logica money-critical bit-identica e azzera il rischio di regressioni.
        self.allow_inplay = bool(c.get("allow_inplay", True))
        self.inplay_from_s = 0.0          # nessuna finestra: in-play da subito
        self.inplay_to_s = 0.0
        self.max_inplay_slots = int(c.get("max_inplay_slots", 0))   # 0 = off
        self.entry_stop_before_s = float(c.get("entry_stop_before_s", 0.0))
        self.flatten_before_s = float(c.get("flatten_before_s", 0.0))
        # GAP-GUARD PUNTEGGIO (cintura 2): la setta il TennisScoreWorker quando
        # siamo su un punto che pesa (break/set/game point). La cintura 1
        # (order-book, max_signal_ticks) resta la difesa anti-gap primaria.
        self.point_pressure: bool = False

        # ---- MISSIONE "1 TICK PER FASE" (prodotto tennis) ----
        # one_tick_per_phase=True: obiettivo 1 green (>=0.05 EUR) PRE-MATCH +
        # 1 green IN-PLAY per match; a fase verde niente nuovi ingressi in
        # quella fase; a missione compiuta (entrambe verdi) stop totale.
        self.one_tick_per_phase: bool = bool(c.get("one_tick_per_phase", False))
        # inplay_tick_enabled: gamba IN-PLAY della missione. Il backtest di
        # validazione (11/07, 34 eventi) ha bocciato il tick in-play sul
        # MATCH_ODDS tennis (1 green/34, coda -13/ciclo non comprimibile:
        # adverse selection da gap punto-per-punto col delay 3s) → il preset
        # live lo SPEGNE; il default di classe resta True per compatibilita'
        # (fuori missione non ha effetto).
        self.inplay_tick_enabled: bool = bool(c.get("inplay_tick_enabled", True))
        # runner_filter: "all" | "favorite". Con "favorite" i NUOVI ingressi
        # avvengono SOLO sul favorito (best-back piu' basso al momento della
        # valutazione): evita la doppia esposizione correlata sui 2 runner.
        self.runner_filter: str = str(c.get("runner_filter", "all")).strip().lower()
        # True quando entrambe le fasi sono verdi (valutato SOLO in missione:
        # fuori missione i contatori restano diagnostici e non fermano il bot).
        self.mission_done: bool = False
        # inplay PRECEDENTE per mercato: rileva la transizione pre-match→in-play
        # (il gap di apertura puo' lasciare una gamba nuda: si chiude ASAP).
        self._prev_inplay: Dict[str, bool] = {}
        # contabilita' di FASE (letta dalla UI: badge missione)
        self.stats.update({
            "pnl_prematch": 0.0, "pnl_inplay": 0.0,
            "greens_prematch": 0, "greens_inplay": 0,
        })

    # ------------------------------------------------------------------ API
    def _emit(self, kind: str, **payload: Any) -> None:
        """Telemetria best-effort: MAI un errore del sink tocca la logica."""
        if self.event_sink is None:
            return
        try:
            self.event_sink(kind, payload)
        except Exception:  # noqa: BLE001 - il sink non deve mai rompere il bot
            logger.debug("[scalper] event_sink errore su %s", kind, exc_info=True)

    @property
    def settled_orders(self):
        """Ordini regolati UNICI (deduplicati per ``order.id``)."""
        return list(self._settled_by_id.values())

    def _slot(self, mid: str, sid: int) -> _Slot:
        key = (mid, int(sid))
        s = self._slots.get(key)
        if s is None:
            s = _Slot()
            self._slots[key] = s
        return s

    # ------------------------------------------------- missione 1-tick-per-fase
    def _phase_green(self, inplay: bool) -> bool:
        """True se la fase indicata ha gia' incassato il suo green (>=1)."""
        key = "greens_inplay" if inplay else "greens_prematch"
        return int(self.stats.get(key, 0) or 0) >= 1

    def _mission_blocks(self, inplay: bool) -> bool:
        """True se la missione vieta NUOVI ingressi nella fase corrente:
        fase gia' verde, oppure gamba in-play disattivata (verdetto backtest
        11/07: il tick in-play sul MATCH_ODDS tennis non e' catturabile)."""
        if not self.one_tick_per_phase:
            return False
        if inplay and not self.inplay_tick_enabled:
            return True
        return self._phase_green(inplay)

    def _book_locked(self, slot: _Slot, locked: float) -> float:
        """Accredita in ``stats['pnl_locked']`` SOLO il DELTA rispetto a quanto gia'
        contabilizzato per il ciclo corrente (fix audit #6, money-critical).

        Un ciclo puo' chiudersi PIU' volte: DONE → fill orfano → flatten riaperto
        (_drive_flatten). Prima ogni chiusura ri-sommava l'INTERO min(nw,nl) su
        tutti gli ordini dello slot → P&L raddoppiato in telemetria/missione.
        Ora ``slot.booked`` ricorda il locked gia' accreditato: ogni booking
        aggiunge (locked − booked) e aggiorna booked. Ritorna il delta (da passare
        a ``_on_cycle_closed``: anche la contabilita' di FASE resta esatta)."""
        delta = float(locked) - float(slot.booked)
        slot.booked = float(locked)
        self.stats["pnl_locked"] += delta
        return delta

    def _count_cycle(self, slot: _Slot, stats_too: bool = False) -> None:
        """Incrementa ``slot.cycles`` UNA sola volta per ciclo (fix audit #6:
        _begin_flatten su una riapertura post-DONE non deve ricontare).
        ``stats_too``: incrementa anche stats['cycles'] (solo chiusure pulite,
        comportamento storico invariato)."""
        if not slot.cycle_counted:
            slot.cycle_counted = True
            slot.cycles += 1
            if stats_too:
                self.stats["cycles"] += 1

    def _on_cycle_closed(self, slot: _Slot, locked: float) -> None:
        """Contabilita' di FASE di un ciclo CHIUSO (missione one_tick_per_phase).

        La fase e' quella di APERTURA del ciclo (``slot.inplay_cycle``): un ciclo
        nato pre-match e trascinato oltre il via conta come pre-match. Un ciclo
        con ``locked >= 0.05`` EUR e' un green di fase. A entrambe le fasi verdi
        (SOLO in missione) ``mission_done`` diventa True e si alza ``force_flat``:
        nessun nuovo ingresso e chiusura di ogni residuo (il runner leggera'
        ``mission_done`` e portera' lo status DB a 'done').
        """
        phase = "inplay" if slot.inplay_cycle else "prematch"
        locked_f = float(locked)
        self.stats[f"pnl_{phase}"] = float(self.stats.get(f"pnl_{phase}", 0.0)) + locked_f
        if locked_f >= 0.05:
            self.stats[f"greens_{phase}"] = int(self.stats.get(f"greens_{phase}", 0)) + 1
            if self.one_tick_per_phase and int(self.stats[f"greens_{phase}"]) == 1:
                self._emit("mission", phase=phase, locked=round(locked_f, 4))
        # missione compiuta = tick pre-match + (tick in-play SE la gamba
        # in-play e' abilitata; disabilitata → basta il pre-match).
        inplay_ok = (
            not self.inplay_tick_enabled
            or int(self.stats.get("greens_inplay", 0)) >= 1
        )
        if (
            self.one_tick_per_phase
            and not self.mission_done
            and int(self.stats.get("greens_prematch", 0)) >= 1
            and inplay_ok
        ):
            self.mission_done = True
            # force-flat: blocca ogni nuovo ingresso (oltre al gating di fase)
            # e chiude/cancella ogni residuo con il percorso provato del near-KO.
            self.force_flat = True
            self._emit("mission", phase="done")

    def _favourite_sel(self, market_book: Any) -> Tuple[Optional[int], bool]:
        """(selection_id del favorito, dati_completi) per ``runner_filter``.

        Favorito = runner ACTIVE col best-back piu' BASSO al momento della
        valutazione. Se un runner ACTIVE non ha best-back il confronto e'
        ambiguo -> ``(None, False)``: fail-safe, nessun nuovo ingresso.
        """
        best_sel: Optional[int] = None
        best_bb: Optional[float] = None
        for r in market_book.runners:
            if getattr(r, "status", None) != "ACTIVE":
                continue
            ex = getattr(r, "ex", None)
            bb = get_price(ex.available_to_back, 0) if ex is not None else None
            if not bb:
                return None, False
            if best_bb is None or bb < best_bb:
                best_bb, best_sel = float(bb), int(r.selection_id)
        return best_sel, True

    # ------------------------------------------------------------ flumine hook
    def check_market_book(self, market: Any, market_book: Any) -> bool:
        if getattr(market_book, "status", None) != "OPEN":
            return False
        if not getattr(market_book, "runners", None):
            return False
        # NB: i book in-play NON vengono filtrati anche con allow_inplay=False:
        # servono per GESTIRE (chiudere) le posizioni rimaste aperte al KO.
        # Il divieto riguarda solo i NUOVI ingressi (vedi process_market_book).
        if self.market_types is not None:
            md = getattr(market_book, "market_definition", None)
            mtype = getattr(md, "market_type", None) or getattr(market, "market_type", None)
            if mtype not in self.market_types:
                return False
        return True

    def _ko_epoch_ms(self, market_book: Any) -> Optional[float]:
        """Kickoff in ms epoch dal market_definition (cache per market_id).

        ATTENZIONE: niente ``isinstance(mt, datetime)``. Nel processo possono
        convivere DUE classi datetime (implementazione C e pura Python, visto
        su py3.13 con betfairlightweight): l'isinstance fallirebbe pur con un
        datetime valido. Si usa il duck-typing su ``timestamp()``.
        """
        mid = market_book.market_id
        cached = self._ko_ms.get(mid)
        if cached is not None:
            return cached
        ko: Optional[float] = None
        md = getattr(market_book, "market_definition", None)
        mt = getattr(md, "market_time", None) if md is not None else None
        ts_fn = getattr(mt, "timestamp", None)
        if callable(ts_fn):
            try:
                if getattr(mt, "tzinfo", None) is None:
                    mt = mt.replace(tzinfo=_dt.timezone.utc)
                ko = float(mt.timestamp()) * 1000.0
            except (TypeError, ValueError, OSError, OverflowError):
                ko = None
        # il None NON si cachea: al prossimo book si riprova (il primo book
        # di un mercato potrebbe non avere il market_definition completo)
        if ko is not None:
            self._ko_ms[mid] = ko
        return ko

    def process_market_book(self, market: Any, market_book: Any) -> None:
        now = getattr(market_book, "publish_time_epoch", None)
        if now is None:
            return
        mid = market_book.market_id
        inplay = bool(getattr(market_book, "inplay", False))
        # TRANSIZIONE PRE-MATCH → IN-PLAY (bug critico: il gap di apertura puo'
        # lasciare una gamba nuda). Al flip False→True, per OGNI ciclo nato
        # pre-match ancora aperto: cancella gli ordini resting inevasi e avvia
        # SUBITO il flatten della parte matchata (chiusura ASAP, senza aspettare
        # che lo stop scatti sul book post-gap). Vale SEMPRE, non solo in missione.
        prev_inplay = self._prev_inplay.get(mid)
        self._prev_inplay[mid] = inplay
        if inplay and prev_inplay is False:
            for (mid_, _sid), s_ in list(self._slots.items()):
                if mid_ != mid:
                    continue
                if not s_.inplay_cycle and s_.status not in (IDLE, DONE):
                    for o in (s_.entry, s_.entry_back, s_.entry_lay,
                              s_.close, s_.next_entry):
                        self._cancel_if_live(market, o)
                    self._begin_flatten(s_)
                    self._emit("ko_transition_flatten", market_id=mid,
                               selection_id=int(_sid))
        if self.inplay_close_now and inplay:
            for (mid_, sid_), s_ in list(self._slots.items()):
                if mid_ != market.market_id:
                    continue
                if s_.inplay_cycle and s_.status not in (IDLE, DONE):
                    self._cancel_if_live(market, s_.entry)
                    self._cancel_if_live(market, s_.entry_back)
                    self._cancel_if_live(market, s_.entry_lay)
                    self._cancel_if_live(market, s_.close)
                    self._begin_flatten(s_)
        # FORCE-FLAT: vicino al kickoff (flatten_before_s) o gia' in-play con
        # allow_inplay=False -> chiudi tutto e vieta nuovi ingressi. Il tempo
        # al KO deriva dal publish_time del book vs il market_time del
        # market_definition (coerente anche in replay; MAI wall-clock).
        near_ko = False
        no_entry = False
        if self.force_flat:
            near_ko = True
        elif not self.allow_inplay:
            if inplay:
                near_ko = True
            else:
                ko = self._ko_epoch_ms(market_book)
                if ko is not None:
                    left_s = (ko - now) / 1000.0
                    if self.flatten_before_s > 0 and left_s <= self.flatten_before_s:
                        near_ko = True
                    if self.entry_stop_before_s > 0 and left_s <= self.entry_stop_before_s:
                        no_entry = True
        # GAP-GUARD PUNTEGGIO (tennis): su un punto che pesa (break/set/game
        # point) riusiamo il percorso provato di ``no_entry``: le quote inevase
        # vengono cancellate (blocco A2) e non si aprono nuovi ingressi. Le
        # posizioni gia' aperte restano gestite da green/stop normali.
        if self.point_pressure:
            no_entry = True
        # MISSIONE 1-tick-per-fase: fase corrente gia' verde → nessun nuovo
        # ingresso in questa fase. Riusa il percorso provato di ``no_entry``
        # (blocco A2: le quote inevase vengono ritirate); i cicli aperti si
        # gestiscono normalmente fino alla chiusura.
        if self._mission_blocks(inplay):
            no_entry = True
        # RUNNER FILTER "favorite": favorito calcolato UNA volta per book.
        fav_sel: Optional[int] = None
        fav_ok = True
        if self.runner_filter == "favorite":
            fav_sel, fav_ok = self._favourite_sel(market_book)
        for runner in market_book.runners:
            if getattr(runner, "status", None) != "ACTIVE":
                continue
            ex = getattr(runner, "ex", None)
            if ex is None:
                continue
            best_back = get_price(ex.available_to_back, 0)
            best_lay = get_price(ex.available_to_lay, 0)
            size_back = get_size(ex.available_to_back, 0)
            size_lay = get_size(ex.available_to_lay, 0)
            mp = micro_price(best_back, size_back, best_lay, size_lay)
            slot = self._slot(mid, int(runner.selection_id))
            if slot.first_seen is None:
                slot.first_seen = int(now)
            if mp is not None:
                slot.history.append((int(now), float(mp)))
                # campione rado per la deriva di lungo periodo (~1 ogni 30s)
                if (
                    not slot.drift_samples
                    or now - slot.drift_samples[-1][0] >= 30_000
                ):
                    slot.drift_samples.append((int(now), float(mp)))
            # aggiorna il flusso tradato (prints) PRIMA di aggiornare last_bb/bl:
            # la classificazione usa i best del tick precedente (nessun look-ahead)
            self._update_flow(slot, int(now), ex)
            slot.last_bb, slot.last_bl = best_back, best_lay
            # avanza le sequenze park-trim-replace (uscite a size esatta)
            self._drive_submins(market, slot, int(now))

            # A) chiusura forzata pre-kickoff / in-play senza allow_inplay
            if near_ko:
                if slot.status in (QUOTING, QUOTING2, CANCELLING, LOCKING):
                    for o in (slot.entry, slot.entry_back, slot.entry_lay,
                              slot.close, slot.next_entry):
                        self._cancel_if_live(market, o)
                    self._begin_flatten(slot)
                elif slot.status == DONE:
                    # anche i cicli CONCLUSI vanno sorvegliati qui: un ordine
                    # orfano ancora vivo puo' riempirsi a ridosso del KO e
                    # riaprire l'esposizione (visto sui dati reali: fill a
                    # KO-12s su una quote di un ciclo gia' chiuso).
                    for o in (slot.entry, slot.entry_back, slot.entry_lay,
                              slot.close, slot.next_entry, *slot.flatten_orders):
                        self._cancel_if_live(market, o)
                    nw0, nl0 = self._net_position(slot)
                    if abs(nw0 - nl0) > (0.30 if slot.residual_ok else 0.02):
                        self._begin_flatten(slot)
                if slot.status == FLATTENING:
                    self._drive_flatten(market, slot, best_back, best_lay, now)
                continue  # nessun nuovo ingresso vicino al KO

            # A2) finestra "no i nuovi ingressi" pre-KO: gli ingressi ancora
            # inevasi vanno CANCELLATI (un fill a ridosso del KO non ha il
            # tempo di chiudersi da maker); le posizioni aperte si gestiscono
            # normalmente fino alla finestra di flatten.
            if no_entry and slot.status in (QUOTING, QUOTING2):
                matched_any = any(
                    float(getattr(o, "size_matched", 0.0) or 0.0) > _EPS
                    for o in (slot.entry, slot.entry_back, slot.entry_lay)
                    if o is not None
                )
                if not matched_any:
                    for o in (slot.entry, slot.entry_back, slot.entry_lay):
                        self._cancel_if_live(market, o)
                    slot.status = CANCELLING
                    continue

            # B) gestione posizione in corso
            if slot.status in (QUOTING, LOCKING):
                self._manage(market, market_book, runner, slot, now,
                             best_back, best_lay, size_back, size_lay)
                continue
            if slot.status == QUOTING2:
                self._manage_maker(market, slot, now,
                                   best_back, best_lay, size_back, size_lay)
                continue
            if slot.status == CANCELLING:
                self._handle_cancelling(market, slot, now, best_back, best_lay)
                continue
            if slot.status == FLATTENING:
                self._drive_flatten(market, slot, best_back, best_lay, now)
                continue
            # C) DONE: il ciclo e' concluso ma la POSIZIONE va sorvegliata.
            # Un ordine orfano (es. close sostituita il cui cancel e' fallito
            # per race PENDING) puo' riempirsi DOPO: se l'esposizione non e'
            # piu' piatta si riapre la chiusura garantita. Mai abbandonare.
            if slot.status == DONE:
                if slot.submins:
                    continue  # uscita esatta ancora in corso: niente riciclo
                nw0, nl0 = self._net_position(slot)
                tol = 0.30 if slot.residual_ok else 0.02
                if abs(nw0 - nl0) > tol:
                    self._begin_flatten(slot)
                    self._drive_flatten(market, slot, best_back, best_lay, now)
                    continue
                # PIPELINE: il next_entry (in coda dietro la close appena
                # riempita) diventa la gamba del NUOVO ciclo, ereditando la
                # priorita' di coda maturata. Adottabile solo se il contesto
                # consente nuovi ingressi.
                ne = slot.next_entry
                adopt = (
                    self.pipeline
                    and slot.cycles < self.max_cycles
                    and ne is not None
                    and self._has_live(ne)
                    and not no_entry
                    and not (inplay and not self.allow_inplay)
                    and now >= slot.cooldown_until
                )
                live = [slot.entry, slot.close, slot.entry_back, slot.entry_lay]
                live += list(slot.flatten_orders)
                if not adopt:
                    live.append(ne)
                still = [o for o in live if self._has_live(o)]
                if still:
                    # in DONE nessun ordine deve restare vivo: ritenta il cancel
                    for o in still:
                        self._cancel_if_live(market, o)
                    continue
                if slot.cycles < self.max_cycles:
                    self._reset(slot)
                    if adopt:
                        side = (getattr(ne, "side", "") or "").upper()
                        opp = None
                        if side == "LAY" and best_back and best_lay:
                            opp = self._place(market, int(runner.selection_id),
                                              "BACK", get_nearest_price(best_lay),
                                              self.stake)
                            slot.entry_lay, slot.entry_back = ne, opp
                        elif side == "BACK" and best_back and best_lay:
                            opp = self._place(market, int(runner.selection_id),
                                              "LAY", get_nearest_price(best_back),
                                              self.stake)
                            slot.entry_back, slot.entry_lay = ne, opp
                        if slot.entry_back is not None or slot.entry_lay is not None:
                            slot.status = QUOTING2
                            slot.t_quote = now
                            slot.ref_price = mp
                        else:
                            self._cancel_if_live(market, ne)
                else:
                    if ne is not None:
                        self._cancel_if_live(market, ne)
                    continue
            # D) nuovo ingresso (IDLE) — mai in-play senza allow_inplay, mai
            # dentro il buffer pre-KO (entry_stop_before_s)
            if slot.status == IDLE:
                # GAP-GUARD PUNTEGGIO: nessun nuovo ingresso su un punto che pesa
                if self.point_pressure:
                    continue
                # MISSIONE: fase gia' verde → niente nuovi ingressi in fase
                if self._mission_blocks(inplay):
                    continue
                # RUNNER FILTER "favorite": nuovi ingressi SOLO sul favorito.
                # fav_ok False = best-back mancante su un runner → fail-safe,
                # niente ingressi su nessuno in questo giro. Le posizioni
                # aperte sugli altri runner restano gestite normalmente.
                if self.runner_filter == "favorite" and (
                    not fav_ok or int(runner.selection_id) != fav_sel
                ):
                    continue
                if inplay and not self.allow_inplay:
                    continue
                if inplay and self.inplay_to_s > 0:
                    ko = self._ko_epoch_ms(market_book)
                    el = (now - ko) / 1000.0 if ko else None
                    if self.ht_active is not None:
                        # rilevatore reale (feed punteggi) + clock di sanita'
                        if not self.ht_active:
                            continue
                        if el is None or not (
                            self.inplay_from_s - 300 <= el <= self.inplay_to_s + 600
                        ):
                            continue
                    elif el is None or not (self.inplay_from_s <= el <= self.inplay_to_s):
                        continue
                slot.inplay_cycle = inplay
                if inplay and self.max_inplay_slots > 0:
                    busy = sum(
                        1 for s in self._slots.values()
                        if s.status not in (IDLE, DONE)
                    )
                    if busy >= self.max_inplay_slots:
                        continue
                if not inplay and self.entry_stop_before_s > 0:
                    ko = self._ko_epoch_ms(market_book)
                    if ko is not None and (ko - now) / 1000.0 <= self.entry_stop_before_s:
                        continue
                self._try_enter(market, market_book, runner, slot, now,
                                best_back, best_lay, size_back, size_lay, mp)

    def process_closed_market(self, market: Any, market_book: Any) -> None:
        md = getattr(market_book, "market_definition", None)
        mtype = (
            getattr(md, "market_type", None)
            or getattr(market, "market_type", None)
            or "UNKNOWN"
        )
        try:
            orders = market.blotter.strategy_orders(self)
        except Exception:  # noqa: BLE001
            orders = []
        for order in orders:
            oid = getattr(order, "id", None) or id(order)
            self._settled_by_id[oid] = (order, mtype)

    # ----------------------------------------------------------------- logica
    def _try_enter(
        self, market: Any, market_book: Any, runner: Any, slot: _Slot,
        now: int, best_back: Optional[float], best_lay: Optional[float],
        size_back: Optional[float], size_lay: Optional[float], mp: Optional[float],
    ) -> None:
        # ---- GATE: condizioni di mercato adatte ----
        if best_back is None or best_lay is None or mp is None:
            return
        if not (self.price_min <= best_back <= self.price_max):
            return
        if (size_back or 0.0) < self.min_size or (size_lay or 0.0) < self.min_size:
            return
        tm = getattr(runner, "total_matched", None) or 0.0
        if tm < self.min_total_matched:
            return
        st = ticks_between(best_back, best_lay)
        if st is None:
            return

        # ---- cooldown (post gap / post perdita) ----
        if now < slot.cooldown_until:
            return
        # ---- guardia anti-gap comune: rottura di regime -> pausa ----
        mv = self._recent_move(slot, now, mp)
        if mv is not None and mv > self.max_signal_ticks:
            slot.cooldown_until = now + self.cooldown_ms
            return

        # ---- ROUTING modalita' ----
        if self.mode != "reversion":
            # gate di FLUSSO: senza volume recente su ENTRAMBI i lati non si
            # quota (mai piu' gambe nude in mercati morti)
            if slot.first_seen is None or now - slot.first_seen < self.warmup_ms:
                return
            fb, fl = self._flow_sums(slot, now)
            if self.min_flow > 0 and (fb < self.min_flow or fl < self.min_flow):
                return
            if self.min_inside_flow > 0:
                hz = now - self.flow_balance_window_ms
                fi_sum = sum(v for ts, v in slot.flow_inside if ts >= hz)
                if fi_sum < self.min_inside_flow:
                    return  # niente incroci nello spread: qui i maker non mangiano
            if self.require_oscillation:
                hz = now - self.flow_balance_window_ms
                samples = [v for ts, v in slot.drift_samples if ts >= hz]
                up = down = False
                for a, b in zip(samples, samples[1:]):
                    t = ticks_between(min(a, b), max(a, b))
                    if t is not None and t >= 0.9:
                        if b > a:
                            up = True
                        else:
                            down = True
                if not (up and down):
                    return  # niente inversioni: il maker qui non mangia
            if self.flow_balance_min > 0:
                hz = now - self.flow_balance_window_ms
                bfb = bfl = 0.0
                for ts, b_, l_ in slot.flow:
                    if ts >= hz:
                        bfb += b_
                        bfl += l_
                hi = max(bfb, bfl)
                if hi <= 0 or min(bfb, bfl) / hi < self.flow_balance_min:
                    return  # flusso a senso unico: il maker non offre la sponda
            # squilibrio estremo = pressione a senso unico: non fare il maker
            wom = wom_imbalance(size_back, size_lay)
            if abs(wom) > self.wom_block:
                return
            # FILTRO ANTI-DERIVA: tendenza netta di lungo periodo -> il maker
            # verrebbe riempito solo dal lato sbagliato. Salta il runner.
            if self.max_drift_ticks > 0 and mp is not None:
                dr = self._long_drift(slot, now, mp)
                if dr is not None and dr >= self.max_drift_ticks:
                    return
            # ---- GATE DI EVENTO: loss cap duro + cricchetto post-target ----
            locked = float(self.stats.get("pnl_locked", 0.0))
            if locked > float(self.stats.get("pnl_peak", 0.0)):
                self.stats["pnl_peak"] = locked
            if self.event_loss_cap > 0 and locked <= -self.event_loss_cap:
                # tetto di perdita partita: FORCE-FLAT totale (non solo stop
                # ingressi: i cicli in volo continuerebbero a perdere — visto
                # -2.10 con cap -1.00 in backtest)
                if not self.force_flat:
                    self.force_flat = True
                    self._emit("loss_cap", locked=round(locked, 2))
                return
            if (
                self.event_profit_target > 0
                and self.stats.get("pnl_peak", 0.0) >= self.event_profit_target
            ):
                if not self.stats.get("target_hit"):
                    self.stats["target_hit"] = 1
                    self._emit("target_raggiunto", locked=round(locked, 2))
                if locked <= self.stats["pnl_peak"] - self.event_target_giveback:
                    return  # cricchetto: profitti della partita protetti

            # BIAS: quota SOLO dal lato del segnale, in coda al touch (maker)
            side_bias = self.bias.get(int(runner.selection_id))
            # TREND SURF: se deriva e flusso CONCORDANO, bias automatico col
            # flusso (quote in discesa = aggressione dei backer -> BACK;
            # in salita -> LAY). Vince sul join simmetrico per questo slot.
            if side_bias is None and self.trend_mode and mp is not None:
                dr = self._long_drift_signed(slot, now, mp)
                if dr is not None and abs(dr) >= self.trend_min_ticks:
                    if dr < 0 and fb >= self.trend_flow_ratio * max(fl, 1e-9):
                        side_bias = "BACK"
                    elif dr > 0 and fl >= self.trend_flow_ratio * max(fb, 1e-9):
                        side_bias = "LAY"
                    if side_bias is not None:
                        slot.swing = True
                        self.stats["trend_entries"] += 1
                        self._emit("trend_surf", selection_id=int(runner.selection_id),
                                   side=side_bias, drift=round(dr, 1),
                                   fb=round(fb, 0), fl=round(fl, 0))
            if side_bias is None:
                slot.swing = False
                if self.swing_only:
                    return  # solo swing: senza segnale di trend non si quota
            if side_bias is not None:
                if st > self.join_max_spread:
                    return
                if side_bias == "BACK":
                    price = get_nearest_price(best_lay)   # back in coda su atl
                else:
                    price = get_nearest_price(best_back)  # lay in coda su atb
                if price is None or price <= 1.0:
                    return
                order = self._place(market, runner.selection_id, side_bias,
                                    price, self.stake)
                if order is None:
                    return
                slot.status = QUOTING
                slot.entry = order
                slot.entry_side = side_bias
                slot.t_quote = now
                slot.ref_price = mp
                return
            # modalita' 'bias' pura: niente maker neutro sulle altre selezioni
            if self.only_bias:
                return
            if st <= self.join_max_spread and self.mode in ("auto", "join"):
                self._enter_join(market, runner, slot, now, best_back, best_lay,
                                 size_back, size_lay, mp, st, fb, fl)
                return
            if self.mode in ("auto", "maker") and (
                self.capture_min_ticks <= st <= self.capture_max_ticks
            ):
                self._enter_maker(market, runner, slot, now, best_back, best_lay, mp, st)
            return

        # ---- REVERSION (una gamba): solo spread stretto ----
        if st > self.max_spread_ticks:
            return
        side = self._signal(slot, now, mp, size_back, size_lay)
        if side is None:
            return
        if side == "BACK":
            price = get_nearest_price(best_back)   # back: resta sul best back
        else:
            price = get_nearest_price(best_lay)    # lay: resta sul best lay
        if price is None or price <= 1.0:
            return
        order = self._place(market, runner.selection_id, side, price, self.stake)
        if order is None:
            return
        slot.status = QUOTING
        slot.entry = order
        slot.entry_side = side
        slot.t_quote = now
        slot.ref_price = mp

    def _enter_maker(
        self, market: Any, runner: Any, slot: _Slot, now: int,
        best_back: float, best_lay: float, mp: float, st: int,
    ) -> None:
        """Market-maker a due lati: quota dentro lo spread e cattura i tick.

        BACK alto (1 tick dentro dal lay) + LAY basso (1 tick dentro dal back).
        Se entrambe si riempiono la posizione e' 0-o-profitto (mai negativa).
        """
        if st < self.capture_min_ticks or st > self.capture_max_ticks:
            return
        # guardia anti-gap anche per il maker: niente quote nel caos (post-gol)
        mv = self._recent_move(slot, now, mp)
        if mv is not None and mv > self.max_signal_ticks:
            return
        bb = get_nearest_price(best_back)
        bl = get_nearest_price(best_lay)
        back_price = price_ticks_away(bl, -self.inside_ticks)  # back alto (inset dal lay)
        lay_price = price_ticks_away(bb, +self.inside_ticks)   # lay basso (inset dal back)
        # serve back_price > lay_price (>=1 tick) per un profitto positivo
        room = ticks_between(lay_price, back_price)
        if room is None or room < 1:
            return
        ob = self._place(market, runner.selection_id, "BACK", back_price, self.stake)
        ol = self._place(market, runner.selection_id, "LAY", lay_price, self.stake)
        if ob is None or ol is None:
            self._cancel_if_live(market, ob)
            self._cancel_if_live(market, ol)
            return
        slot.status = QUOTING2
        slot.entry_back = ob
        slot.entry_lay = ol
        slot.t_quote = now
        slot.ref_price = mp

    def _enter_join(
        self, market: Any, runner: Any, slot: _Slot, now: int,
        best_back: float, best_lay: float,
        size_back: Optional[float], size_lay: Optional[float],
        mp: float, st: int, flow_back: float = 0.0, flow_lay: float = 0.0,
    ) -> None:
        """JOIN dei touch su spread stretto (1-2 tick): il cuore dello scalping.

        BACK in coda al best lay + LAY in coda al best back: se entrambe si
        riempiono si cattura lo spread (st tick). Con spread >= 2 e
        ``improve_inside`` si migliora di 1 tick il lato con la coda piu'
        LUNGA (dentro lo spread la priorita' e' immediata: coda zero).
        """
        if st < 1:
            return
        bb = get_nearest_price(best_back)
        bl = get_nearest_price(best_lay)
        back_price, lay_price = bl, bb  # join puro: cattura = st tick
        if self.join_offset_ticks > 0:
            # pre-posizionamento DIETRO il touch: prima fila alle code nuove
            back_price = price_ticks_away(bl, +self.join_offset_ticks)
            lay_price = price_ticks_away(bb, -self.join_offset_ticks)
            if lay_price is None or lay_price <= 1.0 or back_price is None:
                return
        elif self.improve_inside and st >= 3:
            back_price = price_ticks_away(bl, -1)
            lay_price = price_ticks_away(bb, +1)
        elif self.join_offset_ticks == 0 and self.improve_inside and st == 2:
            # 1 solo tick di room dentro: migliora il lato con coda peggiore.
            # La nostra LAY fa la coda su atb (size_back); il nostro BACK su
            # atl (size_lay).
            if (size_back or 0.0) >= (size_lay or 0.0):
                lay_price = price_ticks_away(bb, +1)
            else:
                back_price = price_ticks_away(bl, -1)
        room = ticks_between(lay_price, back_price)
        if room is None or room < 1:
            return
        # GATE DI FATTIBILITA' DELLA CODA: per ogni gamba che si mette in coda
        # AL touch (non dentro lo spread, dove la coda e' zero) stima l'attesa
        # del fill: coda_davanti / (flusso_del_lato/2, modello piq flumine).
        if self.max_queue_wait_s > 0:
            win_s = max(1.0, self.flow_window_ms / 1000.0)
            # il nostro BACK in coda su atl a bl: fill dai prints lato lay
            if back_price >= bl - _EPS:
                rate = (flow_lay / win_s) / 2.0
                q = float(size_lay or 0.0)
                if rate <= 0 or q / rate > self.max_queue_wait_s:
                    return
            # la nostra LAY in coda su atb a bb: fill dai prints lato back
            if lay_price <= bb + _EPS:
                rate = (flow_back / win_s) / 2.0
                q = float(size_back or 0.0)
                if rate <= 0 or q / rate > self.max_queue_wait_s:
                    return
        # STAKE DINAMICO: interpola tra stake e stake_max col flusso del lato
        # piu' debole (e' quello che limita il roundtrip completo)
        stake = self.stake
        if self.stake_max > self.stake and self.flow_ref > 0:
            factor = min(1.0, min(flow_back, flow_lay) / self.flow_ref)
            stake = round(self.stake + (self.stake_max - self.stake) * factor, 2)
        ob = self._place(market, runner.selection_id, "BACK", back_price, stake)
        ol = self._place(market, runner.selection_id, "LAY", lay_price, stake)
        if ob is None or ol is None:
            self._cancel_if_live(market, ob)
            self._cancel_if_live(market, ol)
            return
        slot.status = QUOTING2
        slot.entry_back = ob
        slot.entry_lay = ol
        slot.t_quote = now
        slot.ref_price = mp

    def _manage_maker(
        self, market: Any, slot: _Slot, now: int,
        best_back: Optional[float], best_lay: Optional[float],
        size_back: Optional[float], size_lay: Optional[float],
    ) -> None:
        eb, el = slot.entry_back, slot.entry_lay
        mb = float(getattr(eb, "size_matched", 0.0) or 0.0) if eb else 0.0
        ml = float(getattr(el, "size_matched", 0.0) or 0.0) if el else 0.0

        # guardia URGENTE: se il book ha incrociato una nostra gamba ancora
        # viva (fill imminente E avverso), cancellala subito; il residuo
        # matchato viene gestito ai giri successivi.
        pb0 = float(getattr(getattr(eb, "order_type", None), "price", 0.0) or 0.0)
        pl0 = float(getattr(getattr(el, "order_type", None), "price", 0.0) or 0.0)
        if self._has_live(eb) and best_back is not None and pb0 > 0 and best_back >= pb0 - _EPS:
            self._cancel_if_live(market, eb)
        if self._has_live(el) and best_lay is not None and pl0 > 0 and best_lay <= pl0 + _EPS:
            self._cancel_if_live(market, el)

        # entrambe le gambe (anche parziali): cancella residui e valuta il netto
        if mb > 0 and ml > 0:
            self._cancel_if_live(market, eb)
            self._cancel_if_live(market, el)
            sb, ob, sl, ol = self._matched_position(eb, el)
            net_win = sb * (ob - 1.0) - sl * (ol - 1.0)
            net_lose = sl - sb
            # FIX 11/07 (validazione): tolleranza 0.02 come il monitor DONE e
            # il percorso scalp — con le size arrotondate a 2 decimali l'_EPS
            # (1e-9) non veniva MAI soddisfatto e il ciclo finiva in un flatten
            # infinito da centesimi (deadlock visto nel backtest paper).
            # locked = worst-case dei due esiti (mai l'esito migliore).
            if abs(net_win - net_lose) <= 0.02:
                locked = min(net_win, net_lose)
                slot.status = DONE
                self._count_cycle(slot, stats_too=True)
                self.stats["roundtrips"] += 1
                # fix audit #6: booking INCREMENTALE (mai ri-sommare su riapertura)
                delta = self._book_locked(slot, locked)
                self._emit("cycle", esito="roundtrip", locked=round(locked, 4),
                           selection_id=getattr(eb, "selection_id", None))
                self._on_cycle_closed(slot, delta)
            else:
                # roundtrip completato ma NON equalizzato (o residuo che puo'
                # perdere): green/chiusura GARANTITA -> ogni ciclo finisce
                # PIATTO, il profitto e' bloccato e non dipende dall'esito.
                self._begin_flatten(slot)
            return

        # una sola gamba riempita.
        # Se l'ingresso e' COMPLETO e le size coincidono, NON cancellare la
        # gamba opposta: e' gia' la chiusura al prezzo di profitto, con la
        # priorita' di coda maturata da quando abbiamo quotato (cancellarla e
        # ripiazzare una close nuova azzererebbe la posizione in coda).
        if mb > 0:
            done = not self._has_live(eb)
            if done and el is not None and abs(mb - float(
                getattr(getattr(el, "order_type", None), "size", 0.0) or 0.0
            )) <= 0.01:
                slot.entry, slot.entry_side = eb, "BACK"
                slot.close = el
                slot.close_scratched = False
                slot.entry_back = slot.entry_lay = None
                slot.t_lock = now
                slot.status = LOCKING
                return
            if done:
                # fill parziale poi chiuso: hedge di size esatta (vecchia via)
                self._cancel_if_live(market, el)
                slot.entry, slot.entry_side = eb, "BACK"
                slot.entry_back = slot.entry_lay = None
                self._open_lock(market, slot, now, eb, best_back, best_lay)
                return
            # FIX 11/07 (validazione): parziale col resting ANCORA VIVO =
            # posizione SENZA stop (visto -13 EUR nel backtest: gamba parziale
            # esposta 27 min in trend). Due guardie, poi percorso LOCKING
            # standard (close + stop sul prezzo d'ingresso):
            #   a) stop avverso: book mosso CONTRO la parte matchata di
            #      >= stop_ticks (stessa semantica del LOCKING: BACK avverso
            #      = best_back SALITO oltre il nostro prezzo);
            #   b) TTL: oltre entry_ttl_ms il parziale non e' piu' un maker
            #      in attesa, e' un rischio aperto.
            adverse_pb = None
            if best_back is not None and pb0 > 0 and best_back > pb0 + _EPS:
                adverse_pb = ticks_between(pb0, best_back)
            ttl_hit = (
                slot.t_quote is not None
                and now - slot.t_quote > self.entry_ttl_ms
            )
            if (adverse_pb is not None and adverse_pb >= self.stop_ticks) or ttl_hit:
                self._cancel_if_live(market, eb)
                self._cancel_if_live(market, el)
                slot.entry, slot.entry_side = eb, "BACK"
                slot.entry_back = slot.entry_lay = None
                self._open_lock(market, slot, now, eb, best_back, best_lay)
            return  # parziale vivo entro TTL e non avverso: lascia lavorare
        if ml > 0:
            done = not self._has_live(el)
            if done and eb is not None and abs(ml - float(
                getattr(getattr(eb, "order_type", None), "size", 0.0) or 0.0
            )) <= 0.01:
                slot.entry, slot.entry_side = el, "LAY"
                slot.close = eb
                slot.close_scratched = False
                slot.entry_back = slot.entry_lay = None
                slot.t_lock = now
                slot.status = LOCKING
                return
            if done:
                self._cancel_if_live(market, eb)
                slot.entry, slot.entry_side = el, "LAY"
                slot.entry_back = slot.entry_lay = None
                self._open_lock(market, slot, now, el, best_back, best_lay)
                return
            # FIX 11/07: come sopra, per la gamba LAY parzialmente riempita
            # (LAY avverso = best_lay SCESO sotto il nostro prezzo).
            adverse_pl = None
            if best_lay is not None and pl0 > 0 and best_lay < pl0 - _EPS:
                adverse_pl = ticks_between(best_lay, pl0)
            ttl_hit = (
                slot.t_quote is not None
                and now - slot.t_quote > self.entry_ttl_ms
            )
            if (adverse_pl is not None and adverse_pl >= self.stop_ticks) or ttl_hit:
                self._cancel_if_live(market, el)
                self._cancel_if_live(market, eb)
                slot.entry, slot.entry_side = el, "LAY"
                slot.entry_back = slot.entry_lay = None
                self._open_lock(market, slot, now, el, best_back, best_lay)
            return

        # nessun fill: guardie di REQUOTE (anti adverse-selection) + timeout
        requote = False
        pb = float(getattr(getattr(eb, "order_type", None), "price", 0.0) or 0.0)
        pl = float(getattr(getattr(el, "order_type", None), "price", 0.0) or 0.0)
        if best_back is not None and pb > 0 and best_back >= pb - _EPS:
            # il best back ha raggiunto/superato il nostro BACK: la nostra
            # offerta e' incrociata col book -> fill immediato E avverso. Via.
            requote = True
        elif best_lay is not None and pl > 0 and best_lay <= pl + _EPS:
            requote = True
        else:
            # book allontanato dalle nostre quote (in QUALSIASI direzione):
            # quota stantia = o non fillera' mai, o fillera' solo in avverso
            if best_lay is not None and pb > 0:
                d = ticks_between(min(pb, best_lay), max(pb, best_lay))
                if d is not None and d >= self.reprice_ticks:
                    requote = True
            if not requote and best_back is not None and pl > 0:
                d = ticks_between(min(pl, best_back), max(pl, best_back))
                if d is not None and d >= self.reprice_ticks:
                    requote = True
        if requote or (
            slot.t_quote is not None and now - slot.t_quote > self.entry_ttl_ms
        ):
            self._cancel_if_live(market, eb)
            self._cancel_if_live(market, el)
            slot.status = CANCELLING

    def _update_flow(self, slot: _Slot, now: int, ex: Any) -> None:
        """Accumula i prints (delta della ladder ``trd``) classificati per lato.

        Lato BACK  = trade a prezzo <= best back precedente (aggressione dei
        backer che consumano la coda atb: riempie i NOSTRI lay in coda).
        Lato LAY   = trade a prezzo >= best lay precedente (aggressione dei
        layer: riempie i NOSTRI back in coda). Prints dentro lo spread: 1/2 e 1/2.
        """
        trd = getattr(ex, "traded_volume", None) or []
        if not slot.prev_trd:
            # prima osservazione: snapshot cumulato, nessun print da contare
            for t in trd:
                p, s = t.get("price"), t.get("size")
                if p is not None and s:
                    slot.prev_trd[float(p)] = float(s)
            return
        bb, bl = slot.last_bb, slot.last_bl
        fb = fl = fi = 0.0
        for t in trd:
            p, s = t.get("price"), t.get("size")
            if p is None or s is None:
                continue
            p = float(p)
            d = float(s) - slot.prev_trd.get(p, 0.0)
            if d <= _EPS:
                continue
            slot.prev_trd[p] = float(s)
            if bb is not None and p <= bb + _EPS:
                fb += d
            elif bl is not None and p >= bl - _EPS:
                fl += d
            else:
                fb += d / 2.0
                fl += d / 2.0
                fi += d
        if fb > 0 or fl > 0:
            slot.flow.append((now, fb, fl))
        if fi > 0:
            slot.flow_inside.append((now, fi))

    def _flow_sums(self, slot: _Slot, now: int) -> Tuple[float, float]:
        """(flusso lato back, flusso lato lay) in EUR nella finestra."""
        horizon = now - self.flow_window_ms
        fb = fl = 0.0
        for ts, b, l in slot.flow:
            if ts >= horizon:
                fb += b
                fl += l
        return fb, fl

    def _long_drift(self, slot: _Slot, now: int, mp: float) -> Optional[float]:
        """Deriva (tick, assoluta) del micro-price nella finestra LUNGA."""
        d = self._long_drift_signed(slot, now, mp)
        return None if d is None else abs(d)

    def _long_drift_signed(self, slot: _Slot, now: int, mp: float) -> Optional[float]:
        """Deriva FIRMATA (tick) del micro-price nella finestra lunga.

        >0 = quote in SALITA, <0 = quote in DISCESA. E' il sensore di REGIME:
        deriva persistente = mercato in TENDENZA → il maker simmetrico rema
        contro (visto sui Mondiali: solo scratch/stop); li' si SURFA il flusso.
        """
        horizon = now - self.drift_window_ms
        ref = None
        for ts, val in slot.drift_samples:
            if ts >= horizon:
                ref = val
                break
        if ref is None:
            return None
        t = ticks_between(min(ref, mp), max(ref, mp))
        if t is None:
            return None
        return float(t) if mp >= ref else -float(t)

    def _recent_move(self, slot: _Slot, now: int, mp: float) -> Optional[int]:
        """Movimento (in tick) del micro-price nella finestra. None se assente."""
        ref = None
        horizon = now - self.signal_window_ms
        for ts, val in slot.history:
            if ts >= horizon:
                ref = val
                break
        if ref is None:
            return None
        return ticks_between(min(ref, mp), max(ref, mp))

    def _signal(
        self, slot: _Slot, now: int, mp: float,
        size_back: Optional[float], size_lay: Optional[float],
    ) -> Optional[str]:
        """Mean-reversion: ritorna "BACK"/"LAY"/None (no look-ahead)."""
        # prezzo di riferimento = primo campione dentro la finestra
        ref = None
        horizon = now - self.signal_window_ms
        for ts, val in slot.history:
            if ts >= horizon:
                ref = val
                break
        if ref is None:
            return None
        move = ticks_between(min(ref, mp), max(ref, mp))
        if move is None or move < self.signal_ticks:
            return None
        # guardia anti-gap: movimento troppo grande = rottura regime (gol) -> niente fade
        if move > self.max_signal_ticks:
            return None
        wom = wom_imbalance(size_back, size_lay)
        if mp > ref:
            # quote salite -> reversione attesa giu' -> BACK (back alto, lay basso)
            # blocca se troppa pressione di lay (WoM molto negativa) che spinge su'
            if wom < -self.wom_block:
                return None
            return "BACK"
        # quote scese -> reversione attesa su' -> LAY
        if wom > self.wom_block:
            return None
        return "LAY"

    def _manage(
        self, market: Any, market_book: Any, runner: Any, slot: _Slot,
        now: int, best_back: Optional[float], best_lay: Optional[float],
        size_back: Optional[float], size_lay: Optional[float],
    ) -> None:
        if slot.status == QUOTING:
            entry = slot.entry
            matched = float(getattr(entry, "size_matched", 0.0) or 0.0)
            if matched > 0:
                # blocca ulteriori fill sull'ingresso e apri la chiusura
                self._cancel_if_live(market, entry)
                self._open_lock(market, slot, now, entry, best_back, best_lay)
                return
            # guardie di REQUOTE (come per il maker two-sided): quota
            # incrociata dal book o rimasta lontana dal touch -> cancella
            requote = False
            if self._has_live(entry):
                ep = float(getattr(getattr(entry, "order_type", None), "price", 0.0) or 0.0)
                es = (getattr(entry, "side", "") or "").upper()
                if es == "BACK" and best_back is not None and ep > 0 and best_back >= ep - _EPS:
                    requote = True
                elif es == "LAY" and best_lay is not None and ep > 0 and best_lay <= ep + _EPS:
                    requote = True
                elif es == "BACK" and best_lay is not None and ep > 0:
                    d = ticks_between(min(ep, best_lay), max(ep, best_lay))
                    requote = d is not None and d >= self.reprice_ticks
                elif es == "LAY" and best_back is not None and ep > 0:
                    d = ticks_between(min(ep, best_back), max(ep, best_back))
                    requote = d is not None and d >= self.reprice_ticks
            if requote or (
                slot.t_quote is not None and now - slot.t_quote > self.entry_ttl_ms
            ):
                # NON resettare subito: la cancel non e' confermata (race in live).
                self._cancel_if_live(market, entry)
                slot.status = CANCELLING
            return

        if slot.status == LOCKING:
            # vecchie close sostituite (scratch): ritenta il cancel finche'
            # non sono morte (il primo cancel puo' fallire su ordini PENDING)
            for o in slot.flatten_orders:
                if self._has_live(o):
                    self._cancel_if_live(market, o)
            close = slot.close
            c_match = float(getattr(close, "size_matched", 0.0) or 0.0) if close else 0.0
            if close is not None and c_match > 0 and not self._has_live(close):
                # roundtrip completato: se resta un residuo direzionale (es.
                # cattura spread con size uguali), GREEN garantito -> il
                # profitto e' bloccato qualunque sia l'esito della partita.
                nw0, nl0 = self._net_position(slot)
                if abs(nw0 - nl0) > 0.02:
                    self._begin_flatten(slot)
                else:
                    # fix audit #12: locked = min(nw0, nl0) come OVUNQUE (il floor
                    # garantito sui due esiti), mai il solo nl0 (esito migliore).
                    locked = min(nw0, nl0)
                    slot.status = DONE
                    self._count_cycle(slot, stats_too=True)
                    self.stats["scalps"] += 1
                    # fix audit #6: booking INCREMENTALE (mai ri-sommare su riapertura)
                    delta = self._book_locked(slot, locked)
                    self._emit("cycle", esito="scalp", locked=round(locked, 4),
                               selection_id=getattr(slot.entry, "selection_id", None))
                    self._on_cycle_closed(slot, delta)
                return
            # ---- gestione avversita' basata sul PREZZO D'INGRESSO ----
            sb, ob, sl, ol = self._matched_position(slot.entry)
            adverse: Optional[int] = 0
            scratch_now = False
            entry_p: Optional[float] = None
            if slot.entry_side == "BACK" and ob and ob > 1.0:
                entry_p = get_nearest_price(ob)
                # avverso = quote SALITE oltre il nostro back
                if best_back is not None and best_back > entry_p + _EPS:
                    adverse = ticks_between(entry_p, best_back)
                scratch_now = (
                    best_back is not None and best_back >= entry_p - _EPS
                )
            elif slot.entry_side == "LAY" and ol and ol > 1.0:
                entry_p = get_nearest_price(ol)
                # avverso = quote SCESE sotto il nostro lay
                if best_lay is not None and best_lay < entry_p - _EPS:
                    adverse = ticks_between(best_lay, entry_p)
                scratch_now = (
                    best_lay is not None and best_lay <= entry_p + _EPS
                )
            # stop duro: N tick contro o timeout -> chiusura garantita a mercato.
            # Con stop_ticks_far attivo lo stop si ADATTA al tempo al KO:
            # largo quando il KO e' lontano (pazienza da maker), stretto sotto.
            eff_stop = self.stop_ticks
            if slot.swing and self.swing_stop_ticks > 0:
                eff_stop = self.swing_stop_ticks
            elif self.stop_ticks_far > self.stop_ticks:
                ko = self._ko_epoch_ms(market_book)
                if ko is not None:
                    left = max(0.0, (ko - now) / 1000.0)
                    frac = min(1.0, left / max(1.0, self.stop_horizon_s))
                    eff_stop = int(round(
                        self.stop_ticks
                        + (self.stop_ticks_far - self.stop_ticks) * frac
                    ))
            if (adverse is not None and adverse >= eff_stop) or (
                slot.t_lock is not None and now - slot.t_lock > self.lock_ttl_ms
            ):
                self._cancel_if_live(market, close)
                self._cancel_if_live(market, slot.next_entry)
                self._begin_flatten(slot)
                slot.cooldown_until = now + self.cooldown_ms
                self.stats["stops"] += 1
                self._emit("stop", selection_id=getattr(slot.entry, "selection_id", None),
                           adverse_ticks=adverse, entry_side=slot.entry_side)
                return
            # SCRATCH: il touch ha raggiunto il nostro prezzo d'ingresso ->
            # ripiazza la chiusura A PARI (profitto 0) invece di inseguire
            # +scalp_ticks che ormai non arrivera'. Una sola volta per ciclo.
            if (
                self.scratch_enable
                and scratch_now
                and not slot.close_scratched
                and c_match <= _EPS
                and entry_p is not None
            ):
                self._cancel_if_live(market, close)
                if close is not None:
                    slot.flatten_orders.append(close)  # contabilita' posizione
                # il mercato e' girato: il next_entry pre-piazzato dietro la
                # vecchia close non ha piu' senso li' -> cancellalo (restera'
                # tracciato in flatten_orders per l'esposizione)
                if slot.next_entry is not None:
                    self._cancel_if_live(market, slot.next_entry)
                    slot.flatten_orders.append(slot.next_entry)
                    slot.next_entry = None
                nw = sb * (ob - 1.0) - sl * (ol - 1.0)
                nl = sl - sb
                g = compute_green(nw, nl, entry_p)
                if g is not None:
                    side, size, _locked = g
                    o = self._place(market, slot.entry.selection_id, side,
                                    entry_p, size, floor_min=False, slot=slot)
                    if o is not None:
                        slot.close = o
                        slot.close_scratched = True
                        self.stats["scratches"] += 1
                        self._emit("scratch",
                                   selection_id=getattr(slot.entry, "selection_id", None),
                                   price=entry_p, entry_side=slot.entry_side)
                        return
                # scratch impossibile -> chiusura garantita
                self._begin_flatten(slot)
                return
            # PIPELINE: mentre la close riposa in coda, pre-piazza l'ingresso
            # del ciclo successivo allo STESSO prezzo/lato, DIETRO di lei:
            # per priorita' di coda si riempie solo dopo la close, quindi non
            # crea mai doppia esposizione, ma eredita i minuti di coda.
            if (
                self.pipeline
                and slot.next_entry is None
                and close is not None
                and c_match <= _EPS
                and self._has_live(close)
                and now >= slot.cooldown_until
            ):
                cp = float(getattr(getattr(close, "order_type", None), "price", 0.0) or 0.0)
                cs = (getattr(close, "side", "") or "").upper()
                if 1.0 < cp and self.price_min <= cp <= self.price_max and cs in ("BACK", "LAY"):
                    ne = self._place(market, slot.entry.selection_id, cs, cp, self.stake)
                    if ne is not None:
                        slot.next_entry = ne
            return

    def _handle_cancelling(
        self, market: Any, slot: _Slot, now: int,
        best_back: Optional[float], best_lay: Optional[float],
    ) -> None:
        """Attende la conferma della cancellazione dell'ingresso (anti-race live).

        Se nel frattempo e' arrivato un fill, apre comunque la chiusura.
        """
        legs = [o for o in (slot.entry, slot.entry_back, slot.entry_lay)
                if o is not None]
        matched = sum(float(getattr(o, "size_matched", 0.0) or 0.0) for o in legs)
        if matched > 0:
            # fill arrivato durante la cancel -> chiusura garantita (mai nuda)
            self._begin_flatten(slot)
        elif not any(self._has_live(o) for o in legs):
            self._reset(slot)

    def _open_lock(
        self, market: Any, slot: _Slot, now: int, entry: Any,
        best_back: Optional[float], best_lay: Optional[float],
    ) -> None:
        sb, ob, sl, ol = self._matched_position(entry)
        net_win = sb * (ob - 1.0) - sl * (ol - 1.0)
        net_lose = sl - sb
        # prezzo target della chiusura (+scalp_ticks a nostro favore).
        # IMPORTANTE: price_ticks_away esige un prezzo ESATTAMENTE sulla ladder,
        # ma OB/OL (average_price_matched) sono float grezzi -> snap obbligatorio.
        t_ticks = self.scalp_ticks
        if slot.swing and self.swing_target_ticks > 0:
            t_ticks = self.swing_target_ticks
        if slot.entry_side == "BACK":
            base_p = get_nearest_price(ob) if (ob and ob > 1.0) else None
            target = price_ticks_away(base_p, -t_ticks) if base_p else None
        else:
            base_p = get_nearest_price(ol) if (ol and ol > 1.0) else None
            target = price_ticks_away(base_p, +t_ticks) if base_p else None
        g = compute_green(net_win, net_lose, target) if target else None
        if g is None:
            # impossibile bloccare un profitto a target: NON lasciare la posizione
            # nuda -> flatten a mercato e chiudi il ciclo.
            logger.warning(
                "[scalper] niente close (target=%s nw=%.4f nl=%.4f) -> flatten",
                target, net_win, net_lose,
            )
            self._begin_flatten(slot)
            return
        side, size, _locked = g
        # floor_min=False: l'hedge deve coprire ESATTAMENTE la quota matchata.
        # Forzare MIN_STAKE su un fill parziale creerebbe una posizione direzionale.
        order = self._place(market, entry.selection_id, side, target, size, floor_min=False, slot=slot)
        if order is None:
            self._begin_flatten(slot)
            return
        slot.close = order
        slot.t_lock = now
        slot.status = LOCKING

    def _begin_flatten(self, slot: _Slot) -> None:
        """Avvia la chiusura GARANTITA della posizione (stato FLATTENING).

        Il driver (_drive_flatten) ripiazza il flatten via via piu' aggressivo
        finche' il netto non e' piatto: nessuna gamba resta MAI nuda.
        """
        if slot.status != FLATTENING:
            slot.status = FLATTENING
            slot.flat_tries = 0
            # fix audit #6: un flatten RIAPERTO su un ciclo gia' chiuso (fill
            # orfano post-DONE) non e' un ciclo nuovo: niente doppio conteggio.
            self._count_cycle(slot)

    def _net_position(self, slot: _Slot) -> Tuple[float, float]:
        """(net_win, net_lose) su TUTTI gli ordini matchati dello slot."""
        orders = [slot.entry, slot.entry_back, slot.entry_lay, slot.close,
                  slot.next_entry]
        orders += list(slot.flatten_orders)
        sb, ob, sl, ol = self._matched_position(*orders)
        return sb * (ob - 1.0) - sl * (ol - 1.0), sl - sb

    def _drive_flatten(
        self, market: Any, slot: _Slot,
        best_back: Optional[float], best_lay: Optional[float],
        now: Optional[int] = None,
    ) -> None:
        """Chiude la posizione finche' non e' piatta (escalation aggressivita')."""
        # le gambe di apertura non servono piu': cancellale se ancora vive
        for o in (slot.entry, slot.entry_back, slot.entry_lay, slot.close,
                  slot.next_entry):
            self._cancel_if_live(market, o)
        net_win, net_lose = self._net_position(slot)
        # FIX 11/07 (validazione): tolleranza 0.02 come il monitor DONE — con
        # size a 2 decimali l'_EPS non veniva mai soddisfatto e lo slot restava
        # in FLATTENING per sempre (ping-pong di ordini da centesimi, cicli MAI
        # contabilizzati: la missione non poteva completarsi in paper).
        if abs(net_win - net_lose) <= 0.02:
            locked = min(net_win, net_lose)
            slot.status = DONE
            self.stats["flattens"] += 1
            # fix audit #6: booking INCREMENTALE — su un flatten RIAPERTO (fill
            # orfano dopo il DONE) si accredita solo la CORREZIONE, non tutto il
            # locked un'altra volta.
            delta = self._book_locked(slot, locked)
            self._emit("flatten_done", locked=round(locked, 4))
            self._on_cycle_closed(slot, delta)
            if (
                self.cycle_loss_breaker > 0
                and locked <= -self.cycle_loss_breaker
                and slot.inplay_cycle
                and not self.force_flat
            ):
                # slippage di latenza in-play: un solo ciclo cosi' negativo
                # significa che il book e' invalicabile -> stop TOTALE evento
                self.force_flat = True
                self._emit("circuit_breaker", locked=round(net_lose, 2))
            return
        # un flatten vivo ma STANTIO (il book si e' allontanato: non fillera')
        # va cancellato e ripiazzato piu' aggressivo al giro dopo
        for o in slot.flatten_orders:
            if not self._has_live(o):
                continue
            p = float(getattr(getattr(o, "order_type", None), "price", 0.0) or 0.0)
            # i PARK delle sequenze exact (BACK@1000 / LAY@1.01) sono
            # imabbinabili PER DESIGN: non sono flatten stantii, NON vanno
            # cancellati qui (il 03/07 questo li uccideva ogni 1.5s e la
            # sequenza park-trim-replace non completava mai → churn di txn)
            if p >= 999.0 or p <= 1.011:
                continue
            side = (getattr(o, "side", "") or "").upper()
            stale = (
                side == "LAY" and best_back is not None and p < best_back - _EPS
            ) or (
                side == "BACK" and best_lay is not None and p > best_lay + _EPS
            )
            if stale:
                self._cancel_if_live(market, o)
        if any(self._has_live(o) for o in slot.flatten_orders):
            return  # un flatten e' ancora in coda: aspetta il fill
        # ANTI-CHURN (live): se l'exchange rifiuta istantaneamente (es. size
        # invalida) l'ordine muore subito e questo loop ritenterebbe ad ogni
        # book update (visto live 02/07: decine di place/secondo). Rate-limit.
        if (
            self.flatten_min_interval_ms > 0
            and now is not None
            and slot.t_last_flat is not None
            and now - slot.t_last_flat < self.flatten_min_interval_ms
        ):
            return
        cross = min(slot.flat_tries, 8)  # ogni tentativo crossa 1 tick piu' a fondo
        fo = self._flatten(market, slot, best_back, best_lay, cross_ticks=cross)
        slot.flat_tries += 1
        if fo is not None:
            slot.flatten_orders.append(fo)
            if now is not None:
                slot.t_last_flat = int(now)
        else:
            # flatten NON piazzabile (size sotto il minimo/rounding, o book
            # monco): se il residuo NON puo' perdere piu' di pochi centesimi,
            # accettalo UNA VOLTA (flag) e chiudi il ciclo. Senza flag il
            # monitor DONE rivedrebbe l'esposizione != 0 e riaprirebbe il
            # flatten ad ogni book update (loop, visto live).
            # FIX 11/07 (validazione): il ramo era gated su size_step>0/
            # live_min_bet>0/exact_exits — ma fuori LIVE il runner li azzera,
            # quindi in sim/PAPER il residuo non veniva MAI accettato (slot
            # bloccato per sempre). L'accettazione vale in OGNI modalita'.
            if min(net_win, net_lose) >= -0.25:
                slot.status = DONE
                if not slot.residual_ok:
                    slot.residual_ok = True
                    self._emit("micro_residuo_accettato",
                               nw=round(net_win, 3), nl=round(net_lose, 3))
                    # contabilita': il residuo accettato entra in pnl_locked
                    # (loss cap/telemetria oneste) e nella fase col FLOOR
                    # garantito (min sui due esiti), mai l'esito migliore.
                    # fix audit #6: anche qui booking INCREMENTALE.
                    delta = self._book_locked(slot, min(net_win, net_lose))
                    self._on_cycle_closed(slot, delta)
            elif (
                best_back is None and best_lay is None and slot.flat_tries > 50
            ):
                # solo con book DAVVERO vuoto e dopo molti tentativi: esci dal
                # loop (il monitor dello stato DONE riprovera' se l'esposizione
                # non e' piatta). MAI arrendersi con prezzi disponibili.
                slot.status = DONE

    def _flatten(
        self, market: Any, slot: _Slot,
        best_back: Optional[float], best_lay: Optional[float],
        cross_ticks: int = 0,
    ) -> Optional[Any]:
        """Ordine di chiusura del netto a prezzo marketable (aggressivo).

        ``cross_ticks`` spinge il prezzo OLTRE il best (peggiore per noi) per
        garantire il match contro la liquidita' disponibile. Considera tutti gli
        ordini dello slot (entry singola/maker + close + flatten precedenti).
        """
        orders = [slot.entry, slot.entry_back, slot.entry_lay, slot.close,
                  slot.next_entry]
        orders += list(slot.flatten_orders)
        sid = next((o.selection_id for o in orders if o is not None), None)
        if sid is None:
            return None
        sb, ob, sl, ol = self._matched_position(*orders)
        net_win = sb * (ob - 1.0) - sl * (ol - 1.0)
        net_lose = sl - sb
        if abs(net_win - net_lose) < _EPS:
            return None
        if net_win > net_lose:  # LAY per chiudere; aggressivo = odds piu' ALTE
            base = get_nearest_price(best_lay) if best_lay else None
            price = price_ticks_away(base, +cross_ticks) if base else None
        else:                   # BACK per chiudere; aggressivo = odds piu' BASSE
            base = get_nearest_price(best_back) if best_back else None
            price = price_ticks_away(base, -cross_ticks) if base else None
        g = compute_green(net_win, net_lose, price) if price else None
        if g is None:
            return None
        side, size, _locked = g
        return self._place(market, sid, side, price, size, floor_min=False, slot=slot)

    # --------------------------------------------------------------- utility
    def _should_stop(
        self, slot: _Slot, now: int,
        best_back: Optional[float], best_lay: Optional[float],
        size_back: Optional[float], size_lay: Optional[float],
    ) -> bool:
        if slot.t_lock is not None and now - slot.t_lock > self.lock_ttl_ms:
            return True
        ref = slot.ref_price
        if ref is None or best_back is None or best_lay is None:
            return False
        # confronto COERENTE col riferimento (micro-price), non col mid aritmetico
        mid = micro_price(best_back, size_back, best_lay, size_lay)
        if mid is None:
            mid = (best_back + best_lay) / 2.0
        # avverso = il mercato si muove CONTRO la nostra reversione attesa
        if slot.entry_side == "BACK":
            # abbiamo backato attendendo discesa: avverso = quote SALITE ancora
            if mid <= ref:
                return False
            adverse = ticks_between(ref, mid)
        else:
            # abbiamo laiato attendendo salita: avverso = quote SCESE ancora
            if mid >= ref:
                return False
            adverse = ticks_between(mid, ref)
        return adverse is not None and adverse >= self.stop_ticks

    @staticmethod
    def _matched_position(*orders: Any) -> Tuple[float, float, float, float]:
        """Aggrega gli ordini matchati in (SB, OB, SL, OL).

        SB/SL = stake matchato lato back/lay; OB/OL = prezzo medio matchato
        (media pesata per size). Ordini ``None`` ignorati.
        """
        sb = sl = 0.0
        sb_pw = sl_pw = 0.0  # somma price*size per la media pesata
        for o in orders:
            if o is None:
                continue
            m = float(getattr(o, "size_matched", 0.0) or 0.0)
            if m <= 0:
                continue
            p = float(getattr(o, "average_price_matched", 0.0) or 0.0)
            if p <= 0:
                continue
            side = (getattr(o, "side", "") or "").upper()
            if side == "BACK":
                sb += m
                sb_pw += p * m
            elif side == "LAY":
                sl += m
                sl_pw += p * m
        ob = (sb_pw / sb) if sb > 0 else 0.0
        ol = (sl_pw / sl) if sl > 0 else 0.0
        return sb, ob, sl, ol

    def _place(
        self, market: Any, selection_id: int, side: str, price: float, size: float,
        floor_min: bool = True, slot: Optional[_Slot] = None,
    ) -> Optional[Any]:
        """Piazza un LimitOrder LAPSE.

        ``floor_min=True`` (ingressi): porta lo stake a MIN_STAKE se inferiore.
        ``floor_min=False`` (hedge/close/flatten): usa la size ESATTA (floor
        tecnico 0.01) per non creare posizioni direzionali su fill parziali.
        Con ``exact_exits`` attivo (live .it) le uscite non piazzabili
        direttamente vengono SPEZZATE: parte diretta (multipli di 0,50 €)
        subito a mercato + resto esatto via park-trim-replace (submin).
        """
        size = round(float(size), 2)
        if floor_min:
            if size < MIN_STAKE:
                size = MIN_STAKE
        elif size < 0.01:
            return None
        price = float(price)
        if price <= 1.0:
            return None
        # ---- USCITE A SIZE ESATTA (come i tool pro: qualsiasi importo) ----
        if (
            not floor_min
            and self.exact_exits
            and not self.dry_run
            and slot is not None
            and not self._size_direct_ok(side, size)
        ):
            return self._place_exact(market, selection_id, side, price, size, slot)
        # LIVE: GRANULARITA' exchange (.it = multipli di 0,50 €): una size non
        # multipla viene RIFIUTATA (INVALID_BET_SIZE) e la posizione resta
        # aperta. Arrotonda al multiplo piu' vicino PRIMA di ogni altro check.
        if self.size_step > 0:
            size = round(round(size / self.size_step) * self.size_step, 2)
            if size < self.size_step:
                size = 0.0
        # LIVE: minimo Betfair sugli hedge/close (sotto: l'exchange RIFIUTA
        # e la posizione resterebbe aperta — peggio di un micro over-hedge)
        _side_floor = self._side_min(side) if self.live_min_bet > 0 else 0.0
        if self.live_min_bet > 0 and not floor_min and size < _side_floor:
            if size >= 0.25:
                import math as _m
                bumped = max(_side_floor, round(_m.ceil(size / 0.5) * 0.5, 2))
                self._emit("min_bet_adjust", selection_id=int(selection_id),
                           side=side, size_orig=size, size=bumped)
                size = bumped
            else:
                # residuo minuscolo: accetta il micro-rischio, non piazzare
                self._emit("min_bet_skip", selection_id=int(selection_id),
                           side=side, size=size)
                return None
        if size < 0.01:
            return None
        # tetto transazioni/ora: blocca SOLO i nuovi ingressi (floor_min=True);
        # chiusure e flatten passano sempre (la sicurezza vince sui costi)
        if self.max_txn_hour > 0 and not self.dry_run:
            import time as _t
            now_s = _t.time()
            while self._txn_ts and now_s - self._txn_ts[0] > 3600:
                self._txn_ts.popleft()
            if floor_min and len(self._txn_ts) >= self.max_txn_hour:
                self._emit("txn_cap", selection_id=int(selection_id), side=side)
                return None
            self._txn_ts.append(now_s)
        # DRY-RUN: logga la quota che AVREBBE piazzato (throttled) e basta.
        if self.dry_run:
            key = (int(selection_id), side, price)
            import time as _t
            now_s = int(_t.time())
            if now_s - self._dry_seen.get(key, 0) >= 60:
                self._dry_seen[key] = now_s
                self.stats["dry_quotes"] += 1
                self._emit("dry_place", market_id=market.market_id,
                           selection_id=int(selection_id), side=side,
                           price=price, size=size)
            return None
        self.stats["orders_placed"] += 1
        self._emit("place", market_id=market.market_id,
                   selection_id=int(selection_id), side=side,
                   price=price, size=size)
        trade = Trade(
            market_id=market.market_id,
            selection_id=int(selection_id),
            handicap=0.0,
            strategy=self,
        )
        order = trade.create_order(
            side=side,
            order_type=LimitOrder(price=price, size=size, persistence_type="LAPSE"),
        )
        market.place_order(order)
        return order

    # ---------------------------------------------- uscite a size ESATTA (.it)
    @staticmethod
    def _side_min(side: str) -> float:
        """Minimo di piazzamento diretto per lato su .it (BACK 2 / LAY 0,50)."""
        return 2.0 if (side or "").upper() == "BACK" else 0.5

    def _size_direct_ok(self, side: str, size: float) -> bool:
        """True se la size e' piazzabile DIRETTAMENTE su .it (multiplo di 0,50
        e >= minimo del lato)."""
        if size < self._side_min(side) - _EPS:
            return False
        mult = size / 0.5
        return abs(mult - round(mult)) < 1e-6

    @staticmethod
    def _track(slot: _Slot, order: Any) -> None:
        """Aggiunge l'ordine al tracking di posizione SENZA duplicati
        (un duplicato in flatten_orders raddoppierebbe il matched in
        _matched_position: money-critical)."""
        if order is None:
            return
        for o in slot.flatten_orders:
            if o is order:
                return
        slot.flatten_orders.append(order)

    # anti-cascata (lezione live 02/07: un flatten in trend genero' 2355
    # sequenze): UNA sequenza per slot, creazione al piu' ogni 3 s.
    _SUBMIN_MIN_INTERVAL_MS = 30_000   # briglia dura (03/07 sera: il flatten
    # ricreava la sequenza ogni 5s pur con l'ordine gia' a riposo al target)
    _SUBMIN_MAX_PER_CYCLE = 5

    def _cancel_submins(self, market: Any, slot: _Slot) -> None:
        """Cancella le sequenze exact dello slot (ordini gia' tracciati)."""
        for entry in list(slot.submins):
            o = entry.get("order") or getattr(entry.get("ops"), "last_order", None)
            if o is not None:
                self._track(slot, o)
                self._cancel_if_live(market, o)
            slot.submins.remove(entry)

    def _place_exact(
        self, market: Any, selection_id: int, side: str, price: float,
        size: float, slot: _Slot,
    ) -> Optional[Any]:
        """Uscita a QUALSIASI size (tool-pro): parte diretta + resto via submin.

        Regole anti-cascata:
          * in FLATTENING (inseguimento del book) il submin parte SOLO se e'
            l'unico modo (nessuna parte diretta) e col rate-limit passato:
            durante la caccia conta la velocita', il residuo esatto si sistema
            quando il book si ferma;
          * UNA sola sequenza attiva per slot (cancel della precedente);
          * creazione rate-limited (3 s) per slot.
        Park LEGALI e universali: size 2,00 su entrambi i lati (BACK @1000,
        LAY @1.01 → payout 2.02, liability 0.02, guardia-abort di submin).
        """
        from ..live_order_build import round_to_tick
        from ..trading.submin import FlumineSubminOps, SubminState, SubminStep

        smin = self._side_min(side)
        main = round(int(size / 0.5 + 1e-9) * 0.5, 2)   # floor al multiplo 0,50
        if main < smin - _EPS:
            main = 0.0
        rest = round(size - main, 2)
        main_order = None
        if main >= smin - _EPS:
            main_order = self._place(market, selection_id, side, price, main,
                                     floor_min=False, slot=None)  # diretto
        if rest < 0.05:
            if rest >= 0.01:
                self._emit("min_bet_skip", selection_id=int(selection_id),
                           side=side, size=rest)
            return main_order

        import time as _t
        now_ms = int(_t.time() * 1000)
        rate_ok = now_ms - (slot.t_last_submin or 0) >= self._SUBMIN_MIN_INTERVAL_MS
        # tetto per ciclo: oltre, il residuo (comunque <=0.25 di rischio) si
        # accetta come micro e si smette di creare sequenze
        if getattr(slot, "submin_count", 0) >= self._SUBMIN_MAX_PER_CYCLE:
            self._emit("min_bet_skip", selection_id=int(selection_id),
                       side=side, size=rest)
            return main_order
        if (slot.status == FLATTENING and main_order is not None) or not rate_ok:
            self._emit("min_bet_skip", selection_id=int(selection_id),
                       side=side, size=rest)
            return main_order
        if slot.submins:
            for entry in slot.submins:
                st_old = entry.get("state")
                if (
                    st_old is not None
                    and st_old.side == side.lower()
                    and abs(st_old.target_size - rest) < 0.05
                    and abs(st_old.target_price - price) < 0.021
                ):
                    return main_order  # sequenza equivalente gia' in corso
            self._cancel_submins(market, slot)
        try:
            state = SubminState(
                step=SubminStep.INIT, bet_id=None,
                target_size=round(rest, 2),
                target_price=round_to_tick(price),
                placed_size=2.0,          # park legale/universale (.it)
                side=side.lower(),
                note="exact exit",
            )

            class _CapturingOps(FlumineSubminOps):
                last_order: Any = None

                def place(self, market_, **kw):  # noqa: ANN001
                    o = super().place(market_, **kw)
                    _CapturingOps.last_order = o
                    return o

            ops = _CapturingOps(selection_id=int(selection_id), handicap=0.0,
                                jurisdiction="it", strategy=self)
            ref = f"sc{abs(hash((selection_id, price, rest, now_ms))) % 10**8:08d}"
            slot.submins.append({"state": state, "ops": ops, "order": None,
                                 "ref": ref, "market_id": market.market_id})
            slot.t_last_submin = now_ms
            slot.submin_count = getattr(slot, "submin_count", 0) + 1
            self._emit("submin_start", selection_id=int(selection_id),
                       side=side, size=rest, price=price)
        except Exception as exc:  # noqa: BLE001 - mai bloccare l'uscita principale
            self._emit("submin_error", msg=str(exc)[:200])
        return main_order

    def _drive_submins(self, market: Any, slot: _Slot, now: int) -> None:
        """Avanza le sequenze park-trim-replace dello slot (idempotente)."""
        if not slot.submins:
            return
        from ..trading.submin import SubminStep, advance_submin

        for entry in list(slot.submins):
            if entry.get("market_id") != market.market_id:
                continue
            order = entry.get("order")
            if order is None:
                order = getattr(entry["ops"], "last_order", None)
                if order is not None:
                    entry["order"] = order
                    self._track(slot, order)
            # dopo un replace flumine appende il NUOVO ordine allo stesso
            # Trade: aggancia sempre l'ultimo e tienilo in contabilita'
            if order is not None:
                tr = getattr(order, "trade", None)
                t_orders = list(getattr(tr, "orders", None) or [])
                for o in t_orders:
                    self._track(slot, o)
                if t_orders:
                    entry["order"] = t_orders[-1]
            try:
                new_state = advance_submin(
                    market, entry["state"], order=entry.get("order"),
                    jurisdiction="it", customer_order_ref=entry["ref"],
                    ops=entry["ops"],
                )
            except Exception as exc:  # noqa: BLE001
                self._emit("submin_error", msg=str(exc)[:200])
                slot.submins.remove(entry)
                continue
            if entry.get("order") is None:
                o = getattr(entry["ops"], "last_order", None)
                if o is not None:
                    entry["order"] = o
                    self._track(slot, o)
            if new_state.step is not entry["state"].step:
                self._emit("submin_step", step=str(new_state.step.value),
                           note=new_state.note[:120])
            entry["state"] = new_state
            if new_state.step == SubminStep.DONE:
                slot.submins.remove(entry)
            elif new_state.step == SubminStep.ABORTED:
                self._emit("submin_abort", note=new_state.note[:200])
                slot.submins.remove(entry)

    @staticmethod
    def _has_live(order: Any) -> bool:
        """True se l'ordine e' ancora VIVO sul book con residuo.

        Fix audit #5: includere CANCELLING/UPDATING/REPLACING (mirror di
        tennis_runner._LIVE_ORDER_STATUSES). Un ordine in CANCELLING ha la cancel
        INVIATA ma l'esito NON confermato: trattarlo come morto resettava lo slot
        e un fill tardivo diventava una posizione NUDA non gestita."""
        if order is None:
            return False
        if getattr(order, "status", None) not in _LIVE_ORDER_STATUSES:
            return False
        return float(getattr(order, "size_remaining", 0.0) or 0.0) > _EPS

    @staticmethod
    def _cancel_if_live(market: Any, order: Any) -> None:
        if order is None:
            return
        # include PENDING (appena piazzato, non ancora EXECUTABLE) e gli stati
        # transitori CANCELLING/UPDATING/REPLACING (fix audit #5): il retry della
        # cancel e' idempotente e un esito non confermato NON e' un ordine morto.
        if getattr(order, "status", None) in _LIVE_ORDER_STATUSES:
            rem = float(getattr(order, "size_remaining", 0.0) or 0.0)
            if rem > _EPS:
                try:
                    market.cancel_order(order)
                except Exception as e:  # noqa: BLE001 - cancel idempotente (ritentato
                    # a ogni tick), ma MAI muto: una causa persistente (auth scaduta,
                    # rete, restrizione account) deve lasciare traccia nei log.
                    logger.debug("[scalper] cancel_order KO bet=%s: %s",
                                 getattr(order, "bet_id", None), e)

    @staticmethod
    def _reset(slot: _Slot) -> None:
        slot.status = IDLE
        slot.entry = None
        slot.entry_side = None
        slot.entry_back = None
        slot.entry_lay = None
        slot.close = None
        slot.close_scratched = False
        slot.residual_ok = False
        slot.submin_count = 0
        slot.next_entry = None
        slot.flatten_orders = []
        slot.flat_tries = 0
        slot.t_quote = None
        slot.t_lock = None
        slot.ref_price = None
        # contabilita' incrementale del ciclo (fix audit #6): il NUOVO ciclo
        # riparte da zero accreditato e non ancora contato.
        slot.booked = 0.0
        slot.cycle_counted = False
        # NB: history/flow/prev_trd/first_seen/cooldown NON si azzerano:
        # sono memoria di mercato, non del ciclo.


# ---------------------------------------------------------------------------
# NOTE DI FEDELTA' DEL SIMULATORE
# ---------------------------------------------------------------------------
# * PRE-MATCH (default): rischio settlement nullo; il P&L deriva dal green
#   bloccato e/o dal settlement degli ordini matchati. Modello realistico.
# * IN-PLAY (allow_inplay=True): il simulatore flumine NON modella il bet-delay
#   calcistico (5-8s) ne' l'annullamento degli inmatchati alla sospensione su
#   gol. I risultati in-play vanno quindi letti come OTTIMISTICI sullo stop.
# * Lo STOP a mercato (_flatten) in simulazione si riempie quando passa volume
#   al prezzo: con simulation_available_prices=False puo' riempirsi in ritardo.
