"""Costruzione + validazione ordine flumine per il runner live (Fase 1).

Per chi: il `live_order_worker` (coda comandi) chiama `build_order()` per trasformare
una riga di `betfair_live_order_requests` in un `BetfairOrder` flumine pronto per
`market.place_order(...)`. Money-critical: la validazione qui è l'ultima barriera prima
di un ordine REALE, quindi qualunque input ambiguo solleva `ValueError` (il worker
scrive `error` e NON piazza nulla).

Tutto è logica pura + uso NATIVO di `flumine.utils` (get_nearest_price / price_ticks_away)
e delle classi ordine flumine (LimitOrder / LimitOnCloseOrder / MarketOnCloseOrder /
Trade / BetfairOrder). Nessuna rete, nessun login: testabile a unità con mock del Market.

Giurisdizione conto = .it (Italian Exchange):
  - BACK: stake minimo 1,00 EUR, al CENTESIMO (01/10/2026, ``trading.minimi_it``);
  - LAY : size (= stake del backer) minima 1,00 EUR; la liability NON conta;
  - NESSUN Minimum Bet Payout;
  - max vincita €10.000; vietato back+lay misti nello stesso ordine (ogni BuiltOrder = 1 lato).

01/10/2026 (RUNNER_MINIMI_CHIUSURE, AUDIT_2026-10-01/RICERCA_STAKE_MINIMI_BETFAIR.md):
NESSUNA eccezione per gli ordini che riducono l'esposizione. Fino a oggi
``reduces_liability=True`` esentava chiusure/green-up/hedge dai minimi: ipotesi FALSA
(nessuna fonte Betfair la prevede; il 01/10 una banca di chiusura da 0,43 @18 di Mike e'
stata rifiutata ``INVALID_BET_SIZE`` 21 volte). ``reduces_liability`` resta SOLO come
informazione (log, diario, ``order.context`` per i control di flusso). Sotto il minimo le
vie legittime sono decise da ``verdetto_minimi``: (a) l'ordine EQUIVALENTE sul lato opposto
dell'altra selezione di un mercato a due esiti; (b) il place-and-trim; (c) nessun ordine,
con rifiuto esplicito ``SOTTO_MINIMO_NON_PIAZZABILE``.
"""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR
from typing import Any, Optional

from flumine.order.order import BetfairOrder
from flumine.order.ordertype import LimitOnCloseOrder, LimitOrder, MarketOnCloseOrder
from flumine.order.trade import Trade
from flumine.strategy.strategy import BaseStrategy
from flumine.utils import (
    MAX_PRICE,
    MIN_PRICE,
    PRICES_FLOAT,
    get_nearest_price,
    price_ticks_away,
)

# ---------------------------------------------------------------------------
# Costanti giurisdizione / guardie money-critical
# ---------------------------------------------------------------------------
JURISDICTION_IT = "it"
JURISDICTION_COM = "com"

# 01/10/2026 - CORREZIONE DEFINITIVA (ordine dell'utente, Nota informativa betfair.it): i
# minimi .it sono UNA definizione, in ``trading.minimi_it`` (senza dipendenze, importata da
# motore, Safe, Omega e Mike con gli stessi nomi). Qui solo gli alias storici del modulo:
#   punta >= 1,00 al CENTESIMO (nessun passo di 0,50), banca >= 1,00 sul size (puntata
#   del backer, la liability non conta), nessuna esenzione per le chiusure, floor di legge
#   0,50 mai tentato, place-and-trim solo con parcheggio e importo finale >= 1,00.
from Betfair.stream.trading.minimi_it import (  # noqa: E402, F401 - riesportati
    IT_FLOOR_LEGGE,
    IT_MIN_BACK,
    IT_MIN_LAY,
    IT_PASSO_PUNTA_RIPIEGO,
    SOTTO_MINIMO_NON_PIAZZABILE,
    SUBMIN_IMPORTO_FINALE_MIN,
)

IT_BACK_MIN_STAKE = IT_MIN_BACK      # alias storico (submin, condotta tennis, worker)
IT_LAY_MIN_SIZE = IT_MIN_LAY         # alias storico
# Passo di 0,50 della documentazione: SOLO per il RIPIEGO (``size_ripiego_punta``) dopo un
# ``INVALID_BET_SIZE`` reale su una punta non multipla di 0,50; mai un floor preventivo.
IT_BACK_STEP = IT_PASSO_PUNTA_RIPIEGO

# Floor MECCANICO della macchina place-and-trim (residuo > 0 dopo il taglio). La REGOLA
# d'ingresso (importo finale >= ``SUBMIN_IMPORTO_FINALE_MIN``) la verificano il verdetto e
# ogni ingresso reale nella macchina (``trading.submin.verifica_importo_finale``).
SUBMIN_ABS_MIN_SIZE = 0.01
# Tolleranza dell'equivalenza economica (EUR): l'ordine tradotto non puo' essere peggiore
# di quello chiesto di piu' di un centesimo in nessuno dei due esiti.
TOLLERANZA_EQUIVALENZA = 0.01

COM_MIN_STAKE = 2.00           # stake minimo generico .com (€)
COM_MIN_BET_PAYOUT = 20.0      # Min Bet Payout .com: ammesso sotto-minimo se size*price >= 20

MAX_PAYOUT_IT = 10000.0        # max vincita consentita (€)

# Guardia Betfair per ordini sotto-minimo che riducono la liability (green-up/hedge):
# il profit-ratio implicito deve restare nella banda [-20%, +25%].
INVALID_PROFIT_RATIO_MIN = -0.20
INVALID_PROFIT_RATIO_MAX = 0.25

_EPS = 1e-9

_VALID_SIDES = ("back", "lay")
_VALID_ORDER_TYPES = ("LIMIT", "LIMIT_ON_CLOSE", "MARKET_ON_CLOSE")
_VALID_PERSISTENCE = ("LAPSE", "PERSIST", "MARKET_ON_CLOSE")
_VALID_TIF = (None, "FILL_OR_KILL")


# ---------------------------------------------------------------------------
# Dataclass di output
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MinStakeVerdict:
    valid: bool
    legalized_size: Optional[float]   # size arrotondata alla regola di giurisdizione
    reason: Optional[str]             # motivo se non valido


@dataclass(frozen=True)
class BuiltOrder:
    order: BetfairOrder               # Trade+BetfairOrder pronti per market.place_order
    side: str                         # 'BACK' | 'LAY' (convenzione Betfair)
    price: Optional[float]            # già al tick (None per MARKET_ON_CLOSE)
    size: Optional[float]             # già legalizzata (None per MARKET_ON_CLOSE)
    liability: Optional[float]
    persistence: str
    time_in_force: Optional[str]
    min_fill_size: Optional[float]
    note: str                         # tracciabilità


# ---------------------------------------------------------------------------
# Prezzo / tick
# ---------------------------------------------------------------------------
def round_to_tick(price: float) -> float:
    """Snap al tick Betfair valido più vicino (ROUND_HALF_UP, clamp 1.01..1000)."""
    if price is None:
        raise ValueError("price is None")
    return get_nearest_price(float(price))


def ticks_away(price: float, n_ticks: int) -> float:
    """Sposta `n_ticks` lungo la scala Betfair.

    Passa SEMPRE per round_to_tick prima: price_ticks_away usa PRICES_FLOAT.index(price)
    e su un prezzo non-ladder solleverebbe ValueError (non gestito dalla libreria).
    """
    valid = round_to_tick(price)
    return price_ticks_away(valid, int(n_ticks))


# ---------------------------------------------------------------------------
# Lay: size <-> liability
# ---------------------------------------------------------------------------
def lay_size_from_liability(liability: float, price: float) -> float:
    """size = liability / (price - 1), arrotondata a 2 decimali."""
    if price is None or price <= 1.0:
        raise ValueError(f"price {price!r} non valido per conversione lay")
    if liability is None or liability < 0:
        raise ValueError(f"liability {liability!r} non valida")
    return round(float(liability) / (float(price) - 1.0), 2)


def liability_from_lay_size(size: float, price: float) -> float:
    """liability = size * (price - 1), arrotondata a 2 decimali."""
    if price is None or price <= 1.0:
        raise ValueError(f"price {price!r} non valido per conversione lay")
    if size is None or size < 0:
        raise ValueError(f"size {size!r} non valida")
    return round(float(size) * (float(price) - 1.0), 2)


def _floor_to_step(size: float, step: float) -> float:
    """Arrotonda PER DIFETTO al multiplo di `step` (Decimal: niente errori float)."""
    q = (Decimal(str(size)) / Decimal(str(step))).to_integral_value(rounding=ROUND_FLOOR)
    return float(q * Decimal(str(step)))


# ---------------------------------------------------------------------------
# Regole stake minimo per giurisdizione
# ---------------------------------------------------------------------------
def min_stake_rules(
    jurisdiction: str,
    side: str,
    price: float,
    size: float,
    reduces_liability: bool = False,
) -> MinStakeVerdict:
    """Verifica/legalizza la size secondo la giurisdizione.

    .it  -> BACK: size >= ``IT_MIN_BACK`` (1,00), legalizzata al CENTESIMO; LAY: size >=
            ``IT_MIN_LAY`` (1,00; la liability non conta); NO Min Bet Payout.
    .com -> min 2,00 EUR oppure Min Bet Payout (size*price >= 20).

    ``reduces_liability`` e' SOLO informazione (01/10/2026): NON esenta piu' dai minimi.
    Betfair non ha nessuna eccezione per chi riduce l'esposizione: un ordine sotto il
    minimo, anche di chiusura, viene rifiutato ``INVALID_BET_SIZE``. La via legittima
    sotto il minimo la decide ``verdetto_minimi``. Il parametro resta per i chiamanti
    esistenti (tennis, condotta, worker) e non cambia il verdetto.
    """
    del reduces_liability  # informazione: mai un'esenzione dai minimi
    j = (jurisdiction or "").lower()
    s = (side or "").lower()
    if s not in _VALID_SIDES:
        return MinStakeVerdict(False, None, f"side non valido: {side!r}")
    if size is None or not math.isfinite(size) or size <= 0:
        return MinStakeVerdict(False, None, f"size non valida: {size!r}")

    if j == JURISDICTION_IT:
        legal = round(float(size), 2)
        if s == "back":
            if legal < IT_BACK_MIN_STAKE - _EPS:
                return MinStakeVerdict(
                    False, None,
                    f"{SOTTO_MINIMO_NON_PIAZZABILE}: BACK size {legal:.2f} < minimo "
                    f"{IT_BACK_MIN_STAKE:.2f} EUR (.it)",
                )
            return MinStakeVerdict(True, legal, None)
        # lay: conta il size (stake del backer), mai la liability
        if legal < IT_LAY_MIN_SIZE - _EPS:
            return MinStakeVerdict(
                False, None,
                f"{SOTTO_MINIMO_NON_PIAZZABILE}: LAY size {legal:.2f} < minimo "
                f"{IT_LAY_MIN_SIZE:.2f} EUR (.it, conta lo stake del backer)",
            )
        return MinStakeVerdict(True, legal, None)

    if j == JURISDICTION_COM:
        payout = float(size) * float(price) if price else 0.0
        if size >= COM_MIN_STAKE - _EPS or payout >= COM_MIN_BET_PAYOUT - _EPS:
            return MinStakeVerdict(True, round(float(size), 2), None)
        return MinStakeVerdict(
            False, None,
            f"{side.upper()} size {size:.2f} < €{COM_MIN_STAKE:.2f} e payout {payout:.2f} "
            f"< Min Bet Payout €{COM_MIN_BET_PAYOUT:.2f} (.com)",
        )

    return MinStakeVerdict(False, None, f"giurisdizione sconosciuta: {jurisdiction!r}")


def size_ripiego_punta(size: float) -> Optional[float]:
    """RIPIEGO dopo un ``INVALID_BET_SIZE`` REALE su una punta non multipla di 0,50.

    Ritorna la size arrotondata PER DIFETTO al multiplo di ``IT_BACK_STEP`` se e' diversa
    da quella rifiutata e resta >= ``IT_BACK_MIN_STAKE``; altrimenti None (nessun ripiego:
    la punta era gia' un multiplo, oppure scenderebbe sotto il minimo). Pura: chi la usa
    garantisce che il ripiego avvenga UNA sola volta e solo dopo il rifiuto vero di
    Betfair, mai in via preventiva.
    """
    try:
        s = round(float(size), 2)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(s) or s <= 0:
        return None
    ripiego = round(_floor_to_step(s, IT_BACK_STEP), 2)
    if abs(ripiego - s) <= _EPS or ripiego < IT_BACK_MIN_STAKE - _EPS:
        return None
    return ripiego


def punta_da_sorvegliare_per_ripiego(side: str, size: Optional[float]) -> bool:
    """Una punta legale al centesimo ma NON multipla di 0,50 che, se Betfair la rifiutasse
    ``INVALID_BET_SIZE``, avrebbe un ripiego possibile (``size_ripiego_punta``)."""
    if str(side or "").lower() != "back" or size is None:
        return False
    return size_ripiego_punta(size) is not None


# ---------------------------------------------------------------------------
# Sotto il minimo: l'ordine EQUIVALENTE e il verdetto (01/10/2026)
# ---------------------------------------------------------------------------
def _tick_su(price: float) -> Optional[float]:
    """Il tick Betfair piu' piccolo >= price (None oltre 1000)."""
    i = bisect.bisect_left(PRICES_FLOAT, float(price) - 1e-9)
    return PRICES_FLOAT[i] if i < len(PRICES_FLOAT) else None


def _tick_giu(price: float) -> Optional[float]:
    """Il tick Betfair piu' grande <= price (None sotto 1,01)."""
    i = bisect.bisect_right(PRICES_FLOAT, float(price) + 1e-9) - 1
    return PRICES_FLOAT[i] if i >= 0 else None


@dataclass(frozen=True)
class OrdineEquivalente:
    """L'ordine sul lato OPPOSTO dell'altra selezione (mercato a due esiti) con lo stesso
    effetto economico di quello chiesto.

    ``scarto_*`` = P&L dell'equivalente MENO P&L dell'ordine chiesto (tutto abbinato al
    limite) nei due esiti: ``_se_vince_chiesta`` = vince la selezione dell'ordine chiesto,
    ``_se_vince_altra`` = vince l'altra. Positivo = l'equivalente rende di piu'.
    """

    side: str                 # 'back' | 'lay' (lato OPPOSTO a quello chiesto)
    price: float              # al tick, arrotondata dal lato che non peggiora mai il limite
    price_esatta: float       # q/(q-1), prima del tick
    size: float               # size*(q-1) dell'ordine chiesto, al centesimo
    scarto_se_vince_chiesta: float
    scarto_se_vince_altra: float


def equivalente_lato_opposto(side: str, price: float,
                             size: float) -> Optional[OrdineEquivalente]:
    """In un mercato a DUE esiti (X, Y): ``lay X S@q`` == ``back Y S(q-1) @ q/(q-1)`` e
    ``back X B@p`` == ``lay Y B(p-1) @ p/(p-1)`` (stessa formula, lato opposto).

    Prima della commissione, che Betfair applica sul netto del mercato. La quota esatta
    raramente e' un tick: si arrotonda dal lato che NON peggiora mai il limite chiesto
    (equivalente BACK -> tick in su, equivalente LAY -> tick in giu'), cosi' nessun
    abbinamento puo' avvenire a un prezzo peggiore di quello che il bot ha accettato. La
    size copre esattamente l'esito sfavorevole dell'ordine chiesto (liability di una
    banca, stake di una punta), al centesimo. Pura. None = equivalente non costruibile.
    """
    s = (side or "").lower()
    if s not in _VALID_SIDES:
        return None
    try:
        q = float(price)
        z = float(size)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(q) and math.isfinite(z)) or q <= 1.0 + _EPS or z <= 0:
        return None
    esatta = q / (q - 1.0)
    lato = "back" if s == "lay" else "lay"
    tick = _tick_su(esatta) if lato == "back" else _tick_giu(esatta)
    if tick is None or not (MIN_PRICE - _EPS <= tick <= MAX_PRICE + _EPS):
        return None
    size_eq = round(z * (q - 1.0), 2)
    if size_eq <= 0:
        return None
    if s == "lay":
        # chiesto: lay X z@q        -> X vince: -z(q-1)      ; Y vince: +z
        # equivalente: back Y e@t   -> X vince: -e           ; Y vince: +e(t-1)
        sc_x = -size_eq + z * (q - 1.0)
        sc_y = size_eq * (tick - 1.0) - z
    else:
        # chiesto: back X z@q       -> X vince: +z(q-1)      ; Y vince: -z
        # equivalente: lay Y e@t    -> X vince: +e           ; Y vince: -e(t-1)
        sc_x = size_eq - z * (q - 1.0)
        sc_y = -size_eq * (tick - 1.0) + z
    return OrdineEquivalente(
        side=lato, price=float(tick), price_esatta=round(esatta, 6), size=size_eq,
        scarto_se_vince_chiesta=round(sc_x, 4), scarto_se_vince_altra=round(sc_y, 4),
    )


def riporta_abbinato_all_originale(
    side_chiesto: str, price_chiesta: float, size_chiesta: float,
    size_mandata: float, abbinato_mandato: float,
) -> "tuple[float, Optional[float]]":
    """L'abbinato dell'ordine EQUIVALENTE riportato nei termini dell'ordine CHIESTO.

    Per il bot che ha chiesto (``side_chiesto`` ``size_chiesta`` @ ``price_chiesta``) e a
    cui il runner ha mandato l'equivalente di ``size_mandata``: ritorna (abbinato, quota
    media) come se avesse abbinato l'ordine chiesto. abbinato = size chiesta x frazione
    abbinata dell'equivalente; quota = 1 + abbinato_mandato / abbinato, cioe':
      - banca chiesta (equivalente PUNTA): la liability riportata e' ESATTA (= stake
        abbinato della punta); la vincita reale e' >= quella riportata;
      - punta chiesta (equivalente BANCA): la vincita riportata e' ESATTA (= stake del
        backer abbinato); la perdita reale e' <= quella riportata.
    In entrambi i casi il bot non sovrastima mai il suo esito (l'equivalente ha un limite
    mai peggiore del chiesto). Quota None se l'abbinato riportato e' zero.
    """
    try:
        q = float(price_chiesta)
        mandata = float(size_mandata)
        m = max(0.0, float(abbinato_mandato or 0.0))
        chiesta = float(size_chiesta)
    except (TypeError, ValueError):
        return 0.0, None
    if m <= 0 or mandata <= 0 or q <= 1.0:
        return 0.0, None
    frazione = min(1.0, m / mandata)
    abbinato = round(chiesta * frazione, 2)
    if abbinato <= 0 or str(side_chiesto or "").lower() not in _VALID_SIDES:
        return 0.0, None
    # banca chiesta: m (stake della punta equivalente) = liability = abbinato*(quota-1);
    # punta chiesta: m (stake del backer della banca equivalente) = vincita = idem.
    return abbinato, round(1.0 + m / abbinato, 4)


VERDETTO_DIRETTO = "diretto"
VERDETTO_EQUIVALENTE = "equivalente"
VERDETTO_SUBMIN = "submin"
VERDETTO_IMPOSSIBILE = "impossibile"


@dataclass(frozen=True)
class VerdettoMinimi:
    """Cosa fare di un ordine rispetto ai minimi di giurisdizione.

    - ``diretto``: piazzabile cosi' com'e' (``size`` = legalizzata al centesimo);
    - ``equivalente``: sotto il minimo, ma l'ordine equivalente sull'altra selezione
      (``altra_selezione``, ``equivalente``) e' piazzabile diretto;
    - ``submin``: sotto il minimo, nessun equivalente diretto, importo >=
      ``SUBMIN_IMPORTO_FINALE_MIN`` (0,50, floor di legge): va col place-and-trim (``place_submin``);
    - ``impossibile``: nessuna via legittima; ``motivo`` comincia con
      ``SOTTO_MINIMO_NON_PIAZZABILE``. MAI un ordine verso Betfair.
    """

    esito: str
    size: Optional[float]
    motivo: Optional[str]
    equivalente: Optional[OrdineEquivalente] = None
    altra_selezione: Optional[tuple] = None   # (selection_id, handicap)

    @property
    def sotto_minimo(self) -> bool:
        return self.esito != VERDETTO_DIRETTO


def verdetto_minimi(
    jurisdiction: str,
    side: str,
    price: float,
    size: float,
    *,
    altra_selezione: Optional[tuple] = None,
    submin_disponibile: bool = True,
) -> VerdettoMinimi:
    """Traduce l'ordine chiesto in uno piazzabile con lo STESSO effetto economico, o dice
    che non si puo'. Nessuna decisione di strategia: stesso rischio, limite di prezzo mai
    peggiorato, importi entro ``TOLLERANZA_EQUIVALENZA``.

    ``altra_selezione`` = (selection_id, handicap) dell'ALTRO esito, solo se il mercato ha
    esattamente due esiti (chi chiama lo sa dal book; None = equivalente non applicabile).
    ``submin_disponibile`` = l'esecutore ha il place-and-trim (il runner tennis no).
    Pura: nessuna rete, nessuno stato.
    """
    v = min_stake_rules(jurisdiction, side, price, size)
    if v.valid:
        return VerdettoMinimi(VERDETTO_DIRETTO, v.legalized_size, None)
    s = (side or "").lower()
    j = (jurisdiction or "").lower()
    valida = s in _VALID_SIDES and size is not None
    try:
        valida = valida and math.isfinite(float(size)) and float(size) > 0
    except (TypeError, ValueError):
        valida = False
    if not valida or j not in (JURISDICTION_IT, JURISDICTION_COM):
        motivo = v.reason or "ordine non valido"
        if not motivo.startswith(SOTTO_MINIMO_NON_PIAZZABILE):
            motivo = f"{SOTTO_MINIMO_NON_PIAZZABILE}: {motivo}"
        return VerdettoMinimi(VERDETTO_IMPOSSIBILE, None, motivo)
    chiesta = round(float(size), 2)
    perche_no_eq = "mercato non a due esiti (equivalente non applicabile)"
    if altra_selezione is not None:
        eq = equivalente_lato_opposto(s, price, chiesta)
        if eq is None:
            perche_no_eq = "equivalente non costruibile (quota fuori scala)"
        else:
            v_eq = min_stake_rules(jurisdiction, eq.side, eq.price, eq.size)
            peggiore = min(eq.scarto_se_vince_chiesta, eq.scarto_se_vince_altra)
            vincita_eq = eq.size * (eq.price - 1.0) if eq.side == "back" else eq.size
            if not v_eq.valid:
                perche_no_eq = (f"equivalente {eq.side.upper()} {eq.size:.2f}@{eq.price} "
                                f"anch'esso sotto il minimo")
            elif peggiore < -TOLLERANZA_EQUIVALENZA - _EPS:
                perche_no_eq = (f"equivalente peggiore del chiesto di {-peggiore:.4f} EUR "
                                f"(oltre la tolleranza {TOLLERANZA_EQUIVALENZA:.2f})")
            elif vincita_eq > MAX_PAYOUT_IT + _EPS:
                perche_no_eq = "equivalente oltre la vincita massima"
            else:
                return VerdettoMinimi(
                    VERDETTO_EQUIVALENTE, eq.size,
                    (f"{s.upper()} {chiesta:.2f}@{price} sotto il minimo: equivalente "
                     f"{eq.side.upper()} {eq.size:.2f}@{eq.price} sull'altra selezione "
                     f"(quota esatta {eq.price_esatta}; scarti "
                     f"{eq.scarto_se_vince_chiesta:+.4f} / {eq.scarto_se_vince_altra:+.4f} EUR)"),
                    equivalente=eq,
                    altra_selezione=(int(altra_selezione[0]),
                                     float(altra_selezione[1] or 0.0)),
                )
    residuo = (f"residuo {s.upper()} {float(size):.2f}@{price} NON piazzato: va dichiarato "
               f"al trader (scelta sua: lasciarlo, oppure aumentare e richiudere)")
    if float(size) < SUBMIN_IMPORTO_FINALE_MIN - _EPS \
            or chiesta < SUBMIN_IMPORTO_FINALE_MIN - _EPS:
        return VerdettoMinimi(
            VERDETTO_IMPOSSIBILE, None,
            f"{SOTTO_MINIMO_NON_PIAZZABILE}: {s.upper()} {float(size):.2f} sotto il minimo "
            f"(e sotto {SUBMIN_IMPORTO_FINALE_MIN:.2f}, importo minimo del place-and-trim: "
            f"sotto il floor di legge di 0,50 non si tenta mai); {perche_no_eq}; {residuo}")
    if not submin_disponibile:
        return VerdettoMinimi(
            VERDETTO_IMPOSSIBILE, None,
            f"{v.reason}; {perche_no_eq}; place-and-trim non disponibile su questo "
            f"esecutore; {residuo}")
    return VerdettoMinimi(
        VERDETTO_SUBMIN, chiesta,
        f"{s.upper()} {chiesta:.2f}@{price} sotto il minimo: place-and-trim ({perche_no_eq}; "
        f"in gioco su .it il bet delay si paga due volte, parcheggio e riprezzo: calcio "
        f"circa 5 -> 10 s)")


# ---------------------------------------------------------------------------
# Costruzione ordine
# ---------------------------------------------------------------------------
def build_order(
    market: Any,
    *,
    strategy: BaseStrategy,
    selection_id: int,
    handicap: float,
    side: str,
    order_type: str,
    price: Optional[float],
    size: Optional[float],
    liability: Optional[float],
    persistence: str,
    time_in_force: Optional[str],
    min_fill_size: Optional[float],
    jurisdiction: str,
    max_stake: Optional[float],
    customer_order_ref: str,
    reduces_liability: bool = False,
    simulato_ammette_sotto_minimo: bool = False,
) -> BuiltOrder:
    """Valida e costruisce un BetfairOrder flumine pronto per `market.place_order`.

    Validazioni: side, tick (get_nearest_price), conversione lay liability<->size,
    min_stake_rules per giurisdizione, FILL_OR_KILL vs persistenza/min_fill_size,
    cap `max_stake`, payout massimo. Solleva `ValueError` con motivo su input invalido.

    ``reduces_liability=True`` (green-up / hedge / cash-out): l'ordine CHIUDE/riduce una
    posizione esistente. Dal 01/10/2026 e' SOLO informazione (``order.context`` per i
    control di flusso, nota): NON esenta dai minimi. Un ordine sotto il minimo solleva
    ``ValueError`` con ``SOTTO_MINIMO_NON_PIAZZABILE`` PRIMA di qualunque invio: la via
    legittima (equivalente / place-and-trim) la sceglie il chiamante con
    ``verdetto_minimi``.

    ``simulato_ammette_sotto_minimo=True``: SOLO per un ordine che va al client SIMULATO
    (paper) dalle gambe di chiusura di greenup/cash-out del worker, che in paper non
    passano dal place-and-trim (la sequenza e' sincrona e il mercato simulato non
    avanza mentre aspetta; comportamento di sempre, ``_place_closing_leg``). Mai per un
    ordine che puo' raggiungere Betfair: chi chiama lo deriva dalla modalita' della riga.

    MONEY-CRITICAL: ``strategy`` DEVE essere l'istanza ``LiveTradingStrategy`` registrata
    nel framework via ``add_strategy``. Il Trade viene creato sotto questa istanza così che
    flumine instradi ``process_orders`` (specchio ordini/posizioni) alla nostra strategia —
    altrimenti l'ordine resta orfano e lo specchio DB non si popola mai.
    """
    if strategy is None:
        raise ValueError("build_order richiede la strategy registrata (LiveTradingStrategy)")
    # --- side -------------------------------------------------------------
    side_l = (side or "").lower()
    if side_l not in _VALID_SIDES:
        raise ValueError(f"side non valido: {side!r} (atteso back|lay)")
    side_bf = "BACK" if side_l == "back" else "LAY"

    # --- order_type -------------------------------------------------------
    ot = (order_type or "").upper()
    if ot not in _VALID_ORDER_TYPES:
        raise ValueError(f"order_type non valido: {order_type!r}")

    # --- persistence ------------------------------------------------------
    pers = (persistence or "LAPSE").upper()
    if pers not in _VALID_PERSISTENCE:
        raise ValueError(f"persistence non valida: {persistence!r}")

    # --- time_in_force / min_fill_size ------------------------------------
    tif = time_in_force if time_in_force in (None, "") else str(time_in_force).upper()
    if tif == "":
        tif = None
    if tif not in _VALID_TIF:
        raise ValueError(f"time_in_force non valido: {time_in_force!r}")
    if tif == "FILL_OR_KILL" and ot != "LIMIT":
        raise ValueError("FILL_OR_KILL ammesso solo su order_type LIMIT")
    if min_fill_size is not None and tif != "FILL_OR_KILL":
        raise ValueError("min_fill_size richiede time_in_force=FILL_OR_KILL")

    market_id = getattr(market, "market_id", None)
    if not market_id:
        raise ValueError("market privo di market_id")

    # =====================================================================
    # Ramo SP (LIMIT_ON_CLOSE / MARKET_ON_CLOSE): si ragiona a liability
    # =====================================================================
    if ot in ("LIMIT_ON_CLOSE", "MARKET_ON_CLOSE"):
        liab = liability if liability is not None else size
        if liab is None or liab <= 0:
            raise ValueError(f"{ot} richiede liability/size > 0")
        liab = round(float(liab), 2)
        if max_stake is not None and liab > float(max_stake) + _EPS:
            raise ValueError(f"liability {liab:.2f} oltre cap max_stake €{float(max_stake):.2f}")
        if ot == "LIMIT_ON_CLOSE":
            if price is None:
                raise ValueError("LIMIT_ON_CLOSE richiede price")
            sp_price = round_to_tick(price)
            order_obj = LimitOnCloseOrder(liability=liab, price=sp_price)
            built_price: Optional[float] = sp_price
        else:
            order_obj = MarketOnCloseOrder(liability=liab)
            built_price = None
        order = _create_order(
            strategy, market_id, selection_id, handicap, side_bf, order_obj, customer_order_ref
        )
        return BuiltOrder(
            order=order, side=side_bf, price=built_price, size=None, liability=liab,
            persistence=pers, time_in_force=tif, min_fill_size=min_fill_size,
            note=f"{ot} liability={liab:.2f}",
        )

    # =====================================================================
    # Ramo LIMIT
    # =====================================================================
    if price is None:
        raise ValueError("order_type LIMIT richiede price")
    if not (MIN_PRICE - _EPS <= float(price) <= MAX_PRICE + _EPS):
        raise ValueError(f"price {price!r} fuori range [{MIN_PRICE}, {MAX_PRICE}]")
    tick_price = round_to_tick(price)

    note_bits = []
    if reduces_liability:
        note_bits.append("reduces_liability (chiusura: minimi di giurisdizione invariati)")

    # Derivazione size per LAY da liability
    if side_l == "lay":
        if size is None and liability is None:
            raise ValueError("LAY richiede size oppure liability")
        if size is None:
            size = lay_size_from_liability(liability, tick_price)
            note_bits.append("lay size da liability")
    else:  # back
        if size is None:
            raise ValueError("BACK richiede size")
    raw_size = round(float(size), 2)

    # Regole stake minimo
    # Regole stake minimo: NESSUNA esenzione per le chiusure (01/10/2026). Solo il client
    # SIMULATO delle gambe greenup/cash-out in paper lo ammette (vedi docstring).
    verdict = min_stake_rules(jurisdiction, side_l, tick_price, raw_size)
    if not verdict.valid and simulato_ammette_sotto_minimo and raw_size > 0:
        verdict = MinStakeVerdict(True, raw_size, None)
        note_bits.append("sotto il minimo ammesso SOLO sul client simulato (paper)")
    if not verdict.valid:
        raise ValueError(verdict.reason or "size non valida per la giurisdizione")
    legal_size = verdict.legalized_size
    if legal_size is None or legal_size <= 0:
        raise ValueError("size legalizzata non valida")
    if abs(legal_size - raw_size) > _EPS:
        note_bits.append(f"size {raw_size:.2f}->{legal_size:.2f} (legalize)")

    # min_fill_size coerente con la size finale
    if min_fill_size is not None and float(min_fill_size) > legal_size + _EPS:
        raise ValueError(
            f"min_fill_size {float(min_fill_size):.2f} > size {legal_size:.2f}"
        )

    # liability finale (LAY)
    final_liability: Optional[float] = None
    if side_l == "lay":
        final_liability = liability_from_lay_size(legal_size, tick_price)

    # Cap max_stake: rischio = size (BACK) / liability (LAY)
    risk = legal_size if side_l == "back" else (final_liability or 0.0)
    if max_stake is not None and risk > float(max_stake) + _EPS:
        raise ValueError(
            f"rischio €{risk:.2f} oltre cap max_stake €{float(max_stake):.2f}"
        )

    # Payout massimo (.it €10.000): BACK win = size*(price-1); LAY win = size matched
    if side_l == "back":
        profit_if_win = legal_size * (tick_price - 1.0)
    else:
        profit_if_win = legal_size
    if profit_if_win > MAX_PAYOUT_IT + _EPS:
        raise ValueError(
            f"vincita potenziale €{profit_if_win:.2f} oltre il massimo €{MAX_PAYOUT_IT:.2f}"
        )

    limit = LimitOrder(
        price=tick_price,
        size=legal_size,
        persistence_type=pers,
        time_in_force=tif,
        min_fill_size=min_fill_size,
    )
    order = _create_order(
        strategy, market_id, selection_id, handicap, side_bf, limit, customer_order_ref
    )
    if reduces_liability:
        # Marca l'ordine come CHIUSURA (green-up/hedge/cash-out): i control che limitano il
        # FLUSSO (LiveRateControl) devono lasciarlo SEMPRE passare — bloccare un'uscita
        # d'emergenza per rate-limit sarebbe l'opposto della protezione.
        order.context["reduces_liability"] = True

    note = "; ".join(note_bits) if note_bits else "ok"
    return BuiltOrder(
        order=order, side=side_bf, price=tick_price, size=legal_size,
        liability=final_liability, persistence=pers, time_in_force=tif,
        min_fill_size=min_fill_size, note=note,
    )


def _create_order(
    strategy: BaseStrategy,
    market_id: str,
    selection_id: int,
    handicap: float,
    side_bf: str,
    order_type_obj: Any,
    customer_order_ref: str,
) -> BetfairOrder:
    """Crea Trade + BetfairOrder flumine SOTTO la strategia registrata e annota il
    customer_order_ref per il DB.

    Il Trade è legato a ``strategy`` (l'istanza LiveTradingStrategy del framework): è questo
    legame che fa instradare ``process_orders`` alla nostra strategia (lo specchio DB).
    """
    trade = Trade(
        market_id=market_id,
        selection_id=int(selection_id),
        handicap=float(handicap or 0),
        strategy=strategy,
    )
    order = trade.create_order(side=side_bf, order_type=order_type_obj)
    # tracciabilità: il NOSTRO ref INTERNO awlq<id> (correlazione richiesta↔ordine) va in
    # notes E context. NON è il customerRef Betfair: l'attributo flumine inviato all'Exchange
    # è `order.customer_order_ref` = name_hash+sep+order.id (order.id = uuid1, non
    # deterministico). process_orders rilegge il nostro ref da context/notes per ricostruire
    # request_id ↔ ordine nello specchio DB; non fa alcun de-dup lato Betfair.
    if customer_order_ref:
        order.notes["customer_order_ref"] = customer_order_ref
        order.context["customer_order_ref"] = customer_order_ref
    return order
