"""Place-and-trim (`submin`): macchina a stati per piazzare un ordine di size
SOTTO il minimo di giurisdizione, in modo idempotente e ripristinabile.

Per chi: il `live_order_worker` (azione `place_submin` della coda comandi) chiama
`advance_submin()` ad ogni poll, facendo avanzare UNO step alla volta in base allo
stato REALE dell'ordine sul mercato. Il worker persiste lo `SubminState` (nel
`result`/`params` della riga di coda) così che, dopo un crash o un riavvio del
framework, la sequenza riprenda esattamente da dove era rimasta.

TECNICA (Betfair): non puoi piazzare direttamente un ordine sotto il minimo
(.it BACK €2,00 / LAY €0,50), ma puoi RIDURRE un ordine esistente sotto quel
minimo. Quindi:

  step1 PLACED  - place size = minimo di giurisdizione a una quota NON abbinabile
                  (BACK→1000.0, LAY→1.01), persistenza LAPSE;
  step2 TRIMMED - cancel parziale di `size_reduction = placed_size - target_size`
                  → resta esattamente la `target_size` (sotto-minima);
  step3 REPRICED- replace alla `target_price` reale (la quota a cui vuoi operare);
  DONE          - ordine a riposo a (target_price, target_size).

GUARDIA RISCHIO (money-critical): mentre l'ordine è alla quota NON abbinabile
(fasi INIT/PLACED/TRIMMED) NON dovrebbe MAI abbinarsi. Se `size_matched > 0` in
quella fase → stato `ABORTED` e NESSUN ritento: la sequenza si ferma e va
riconciliata a mano (siamo entrati in mercato in modo non previsto). Alla fase
REPRICED, invece, l'abbinamento alla `target_price` è l'esito DESIDERATO e non
fa scattare l'abort.

Le operazioni flumine (place/cancel/replace) sono dietro l'interfaccia iniettabile
`SubminOps`: il runner inietta `FlumineSubminOps` (che usa `build_order` +
`market.place_order/cancel_order/replace_order` NATIVI); i test iniettano un mock.
Nessuna rete, nessun login: testabile a unità.
"""
from __future__ import annotations

import time

from dataclasses import dataclass, replace as _dc_replace
from enum import Enum
from typing import Any, Optional, Protocol, runtime_checkable

from Betfair.stream.live_order_build import (
    COM_MIN_STAKE,
    IT_BACK_MIN_STAKE,
    IT_LAY_MIN_SIZE,
    JURISDICTION_COM,
    JURISDICTION_IT,
    build_order,
    round_to_tick,
)

# Tolleranza confronti float (size/price già arrotondati a 2 decimali / al tick).
_TOL = 1e-6

# Floor ASSOLUTO della size residua dopo il trim: non si può ridurre a zero/negativo.
# Conservativo; il valore esatto su .it va verificato empiricamente (cert LIVE minimale).
SUBMIN_ABS_MIN_SIZE = 0.01

_VALID_SIDES = ("back", "lay")


# ---------------------------------------------------------------------------
# Stato della macchina
# ---------------------------------------------------------------------------
class SubminStep(str, Enum):
    INIT = "init"
    PLACED = "placed"        # step1: place min @ quota non abbinabile, LAPSE
    TRIMMED = "trimmed"      # step2: cancel size_reduction → resta target
    REPRICED = "repriced"    # step3: replace new_price = quota target
    DONE = "done"
    ABORTED = "aborted"      # guardia rischio: step1 abbinato → STOP, niente ritento


# Fasi in cui l'ordine è alla quota NON abbinabile (un match qui = anomalia → abort).
_UNMATCHABLE_PHASES = (SubminStep.INIT, SubminStep.PLACED, SubminStep.TRIMMED)
# Stati terminali (idempotenti: nessuna ulteriore azione).
_TERMINAL = (SubminStep.DONE, SubminStep.ABORTED)

# Verifica del trim (fix 11/07 — bug live 10/07 21:43): la promozione a TRIMMED
# avviene SOLO su OSSERVAZIONE fresca dell'ordine (size_remaining ≈ target),
# MAI sulla fiducia dell'esito API del cancel. Senza questa verifica il replace
# dello step3 può portare la size PIENA del park a una quota abbinabile
# (fill istantaneo del park intero, ripetuto = loop auto-amplificante).
_TRIM_RECHECK_MS = 5_000    # residuo intatto dopo il cancel → UNA ri-emissione
_TRIM_TIMEOUT_MS = 15_000   # trim mai osservato → full cancel + ABORTED


@dataclass
class SubminState:
    step: SubminStep
    bet_id: Optional[str]
    target_size: float
    target_price: float          # già al tick
    placed_size: float           # = minimo di giurisdizione (€2 .it BACK / €0,50 LAY)
    side: str                    # 'back' | 'lay'
    note: str = ""
    # epoch ms della RICHIESTA di cancel (step2); 0 = non ancora richiesto.
    # Il passaggio a TRIMMED avviene solo quando il trim viene OSSERVATO.
    trim_requested_ms: int = 0
    # 17/09 — nucleo universale. ``park_price=0.0`` = non deciso: vale la quota
    # estrema storica (``initial_place_price``), cosi' uno stato persistito da
    # una versione precedente si comporta ESATTAMENTE come prima (percorso B).
    park_price: float = 0.0
    serve_replace: bool = True

    @property
    def prezzo_parcheggio(self) -> float:
        """Quota del gradino 1 (percorso A = la target, percorso B = l'estrema)."""
        if self.park_price and self.park_price > 0:
            return float(self.park_price)
        return initial_place_price(self.side)

    @property
    def size_reduction(self) -> float:
        """Quantità da cancellare allo step2 per arrivare alla target_size."""
        return round(self.placed_size - self.target_size, 2)


# ---------------------------------------------------------------------------
# Interfaccia iniettabile sulle operazioni flumine (per testabilità con MOCK)
# ---------------------------------------------------------------------------
@runtime_checkable
class SubminOps(Protocol):
    """Astrazione delle 3 operazioni flumine usate dalla macchina a stati.

    Il default di produzione è `FlumineSubminOps`; i test iniettano un mock che
    registra le chiamate senza toccare la rete.
    """

    def place(
        self,
        market: Any,
        *,
        side: str,
        price: float,
        size: float,
        customer_order_ref: str,
    ) -> Any:
        """Piazza l'ordine iniziale (size minima @ quota non abbinabile). Ritorna
        il BetfairOrder flumine (il cui `bet_id` arriverà async)."""
        ...

    def cancel(self, market: Any, order: Any, size_reduction: Optional[float]) -> None:
        """Cancel PARZIALE di `size_reduction` (riduce l'ordine sotto il minimo).
        Con ``size_reduction=None`` cancella l'INTERO residuo (ritiro totale)."""
        ...

    def replace(self, market: Any, order: Any, new_price: float) -> None:
        """Sposta l'ordine a riposo alla `new_price` (la quota target reale)."""
        ...


@dataclass
class FlumineSubminOps:
    """Implementazione di produzione di `SubminOps` su un Market flumine NATIVO.

    Legata a (selection_id, handicap, jurisdiction, strategy) — costanti per l'intera
    sequenza submin — così che `advance_submin` non debba trasportarli nello stato.
    ``strategy`` è l'istanza LiveTradingStrategy registrata: il Trade è creato sotto di
    essa così che lo specchio (process_orders) intercetti anche gli ordini submin.

    ``max_stake`` (cap effettivo per-ordine) e ``customer_strategy_ref`` (customerStrategyRef
    NATIVO inviato a Betfair) replicano nel ramo submin le stesse barriere del place normale:
    il cap è l'ultima guardia money-critical (NON deve essere bypassato con None) e lo
    strategy-ref instrada correttamente l'ordine lato Exchange.
    """

    selection_id: int
    handicap: float
    jurisdiction: str
    strategy: Any
    max_stake: Optional[float] = None
    customer_strategy_ref: Optional[str] = None
    # F0 (16/09): client flumine della MODALITA' DELLA RIGA che ha chiesto il
    # place-and-trim (simulato per 'paper', reale per 'live'). ``None`` = non
    # specificato -> vale il client di default del framework (uso storico).
    # I 3 passi (park / trim / reprice) DEVONO stare sullo stesso client, altrimenti
    # flumine rifiuta cancel/replace (``Transaction``: order.client != transaction client).
    client: Any = None

    def place(
        self,
        market: Any,
        *,
        side: str,
        price: float,
        size: float,
        customer_order_ref: str,
    ) -> Any:
        built = build_order(
            market,
            strategy=self.strategy,
            selection_id=self.selection_id,
            handicap=self.handicap,
            side=side,
            order_type="LIMIT",
            price=price,
            size=size,
            liability=None,
            persistence="LAPSE",          # step1 deve decadere se non gestito
            time_in_force=None,
            min_fill_size=None,
            jurisdiction=self.jurisdiction,
            max_stake=self.max_stake,     # cap effettivo: NON bypassare la guardia
            customer_order_ref=customer_order_ref,
        )
        # Fix CRITICAL-1: place/cancel/replace flumine ritornano **False** se un trading
        # control rifiuta (ordine VIOLATION, MAI inviato a Betfair). Ignorarlo lascerebbe la
        # sequenza submin ad attendere un ordine INESISTENTE ('processing' per sempre).
        extra = {"client": self.client} if self.client is not None else {}
        if self.customer_strategy_ref is not None:
            ok = market.place_order(
                built.order, customer_strategy_ref=self.customer_strategy_ref, **extra)
        else:
            ok = market.place_order(built.order, **extra)
        if ok is False:
            raise ValueError(f"submin place RIFIUTATO — {_violation_reason(built.order)}")
        return built.order

    def cancel(self, market: Any, order: Any, size_reduction: Optional[float]) -> None:
        # size_reduction=None = ritiro TOTALE del residuo (usato dagli abort).
        if market.cancel_order(order, size_reduction) is False:
            raise ValueError(f"submin cancel RIFIUTATO — {_violation_reason(order)}")

    def replace(self, market: Any, order: Any, new_price: float) -> None:
        # CODE-MED-1: per un LAY ri-valida il cap PRIMA del replace. Lo step3 REPRICED sposta
        # l'ordine dalla quota NON abbinabile (1.01) alla target_price reale: la liability
        # (= size*(price-1)) CRESCE col prezzo, quindi un reprice al rialzo potrebbe sfondare
        # il cap money-critical che il place del minimo rispettava. Solleva senza piazzare.
        _guard_replace_cap_lay(order, new_price, self.max_stake)
        if market.replace_order(order, new_price) is False:
            raise ValueError(f"submin replace RIFIUTATO — {_violation_reason(order)}")


def _violation_reason(order: Any) -> str:
    """Motivo del rifiuto dal trading control (violation_msg), con fallback leggibile."""
    try:
        msg = getattr(order, "violation_msg", None)
    except Exception:  # noqa: BLE001 - property di confine
        msg = None
    return str(msg) if msg else "rifiutato dai trading control flumine (violation)"


# ---------------------------------------------------------------------------
# Helper su size minima di piazzamento per giurisdizione
# ---------------------------------------------------------------------------
def place_min_size(jurisdiction: str, side: str) -> float:
    """Size minima LEGALE per PIAZZARE un ordine (lo step1 usa questa)."""
    j = (jurisdiction or "").lower()
    s = (side or "").lower()
    if s not in _VALID_SIDES:
        raise ValueError(f"side non valido: {side!r} (atteso back|lay)")
    if j == JURISDICTION_IT:
        return IT_BACK_MIN_STAKE if s == "back" else IT_LAY_MIN_SIZE
    if j == JURISDICTION_COM:
        return COM_MIN_STAKE
    raise ValueError(f"giurisdizione sconosciuta: {jurisdiction!r}")


def initial_place_price(side: str) -> float:
    """Quota NON abbinabile per lo step1: BACK→1000.0, LAY→1.01.

    A questi estremi della scala un match è quasi impossibile; va comunque
    verificato empiricamente (la guardia rischio resta l'ultima barriera).
    """
    s = (side or "").lower()
    if s == "back":
        return round_to_tick(1000.0)
    if s == "lay":
        return round_to_tick(1.01)
    raise ValueError(f"side non valido: {side!r} (atteso back|lay)")


# ---------------------------------------------------------------------------
# Costruttore di stato (valida e calcola placed_size)
# ---------------------------------------------------------------------------
def start_submin(
    *,
    side: str,
    target_price: float,
    target_size: float,
    jurisdiction: str,
    note: str = "",
    best_back: Optional[float] = None,
    best_lay: Optional[float] = None,
    max_stake: Optional[float] = None,
) -> SubminState:
    """Crea uno `SubminState` iniziale (step=INIT) validando i vincoli.

    Solleva `ValueError` se: side non valido; target_size ≤ floor assoluto;
    target_size ≥ minimo di piazzamento (in tal caso usa un place NORMALE, non
    serve il submin). `placed_size` = minimo di giurisdizione per quel side.
    """
    s = (side or "").lower()
    if s not in _VALID_SIDES:
        raise ValueError(f"side non valido: {side!r} (atteso back|lay)")
    if target_size is None or target_size <= SUBMIN_ABS_MIN_SIZE - _TOL:
        raise ValueError(
            f"target_size {target_size!r} ≤ floor assoluto €{SUBMIN_ABS_MIN_SIZE:.2f}"
        )
    placed = place_min_size(jurisdiction, s)
    tsize = round(float(target_size), 2)
    if tsize >= placed - _TOL:
        raise ValueError(
            f"target_size €{tsize:.2f} ≥ minimo di piazzamento €{placed:.2f}: "
            "usa un place normale (submin non necessario)"
        )
    tick = round_to_tick(target_price)
    # 17/09 — la scelta del gradino 1 passa dal NUCLEO UNICO, identico al REST:
    # quota target non abbinabile -> percorso A (parcheggio ALLA target, niente
    # replace); altrimenti percorso B (quota estrema + replace), come prima.
    piano = pianifica_submin(
        side=s, target_price=tick, target_size=tsize, jurisdiction=jurisdiction,
        best_back=best_back, best_lay=best_lay, max_stake=max_stake,
    )
    if piano.rifiuto:
        raise ValueError(piano.rifiuto)
    return SubminState(
        step=SubminStep.INIT,
        bet_id=None,
        target_size=tsize,
        target_price=tick,
        placed_size=round(float(placed), 2),
        side=s,
        note=note or ("submin init; " + piano.motivo),
        park_price=piano.park_price,
        serve_replace=piano.serve_replace,
    )


# ---------------------------------------------------------------------------
# Lettura difensiva dello stato dell'ordine (mock-friendly)
# ---------------------------------------------------------------------------
def _size_matched(order: Any) -> float:
    return float(getattr(order, "size_matched", 0.0) or 0.0)


def _size_remaining(order: Any) -> Optional[float]:
    val = getattr(order, "size_remaining", None)
    return None if val is None else float(val)


def _bet_id(order: Any) -> Optional[str]:
    return getattr(order, "bet_id", None)


def _status_name(order: Any) -> Optional[str]:
    st = getattr(order, "status", None)
    if st is None:
        return None
    # OrderStatus.EXECUTABLE -> name "EXECUTABLE"; stringa "Executable"/"EXECUTABLE" -> str()
    name = getattr(st, "name", None)
    return (name or str(st)).upper()


def _is_executable(order: Any) -> bool:
    return _status_name(order) == "EXECUTABLE"


def _order_price(order: Any) -> Optional[float]:
    ot = getattr(order, "order_type", None)
    price = getattr(ot, "price", None)
    return None if price is None else float(price)


def _order_side(order: Any) -> Optional[str]:
    side = getattr(order, "side", None)
    return None if side is None else str(side).lower()


def _order_size(order: Any) -> Optional[float]:
    """Size NOMINALE dell'ordine (order_type.size), fallback alla size residua. Difensivo."""
    ot = getattr(order, "order_type", None)
    size = getattr(ot, "size", None)
    if size is None:
        size = _size_remaining(order)
    return None if size is None else float(size)


def _guard_replace_cap_lay(
    order: Any, new_price: float, max_stake: Optional[float]
) -> None:
    """Ri-valida il cap money-critical prima di un replace LAY (CODE-MED-1).

    Per un LAY la liability = size*(price-1) CRESCE col prezzo: un replace verso quote più
    alte può sfondare il cap che il place iniziale rispettava. Se l'ordine è LAY e la nuova
    liability supera ``max_stake`` (cap effettivo) solleva ``ValueError`` (nessun replace).
    Difensivo: se cap/side/size non sono determinabili NON blocca (no falsi positivi su mock).
    """
    if max_stake is None:
        return
    if _order_side(order) != "lay":
        return
    size = _order_size(order)
    if size is None:
        return
    new_liab = round(float(size) * (float(new_price) - 1.0), 2)
    if new_liab > float(max_stake) + _TOL:
        raise ValueError(
            f"replace LAY: liability €{new_liab:.2f} a quota {new_price} "
            f"oltre cap €{float(max_stake):.2f}"
        )


# ===========================================================================
# NUCLEO UNIVERSALE DEL PLACE-AND-TRIM (17/09/2026)
# ===========================================================================
# Ordine dell'utente: "il place-and-trim DEVE ESSERE AGGIUSTATO E RESO
# UNIVERSALE PER OGNI CASO CHE CI SERVE PRESENTE E FUTURO".
#
# Reperto 25 (17/09, Mike LIVE evento 36077571): 111 tentativi su 111 rifiutati
# con ``CANCELLED_NOT_PLACED`` AL GRADINO 3 (il replace). I gradini 1 e 2 sono
# sempre andati a buon fine: quindi Betfair ACCETTA un ordine ridotto SOTTO il
# minimo che resta a riposo sul book (il taglio e' confermato, ``sizeCancelled``
# esatto). Cio' che fallisce e' il RI-PIAZZAMENTO dentro ``replaceOrders``.
#
# Docs Betfair (replaceOrders): "This operation is logically a bulk cancel
# followed by a bulk place. The cancel is completed first then the new orders
# are placed... In the case where the new orders cannot be placed the
# cancellations will not be rolled back." Quindi il replace ri-piazza un ordine
# NUOVO, che passa dalla validazione di piazzamento (minimo di giurisdizione,
# bet delay in-play, stato del mercato): un residuo sotto minimo non la supera.
#
# CONSEGUENZA DI PROGETTO: il replace si EVITA quando si puo'.
#
#   PERCORSO A ("trim in loco", preferito, 2 chiamate mutanti):
#       la quota target NON e' abbinabile (ordine passivo, e' il caso della
#       copertura di Mike con ``cover_place_at_ticks``) ->
#       1. placeOrders del MINIMO direttamente ALLA QUOTA TARGET (LAPSE, niente
#          fill-or-kill): non si abbina, resta a riposo;
#       2. cancelOrders con ``sizeReduction`` = minimo - importo voluto.
#       Fine: l'ordine e' gia' alla quota giusta, NESSUN replace, quindi
#       ``CANCELLED_NOT_PLACED`` non puo' proprio accadere.
#
#   PERCORSO B (fallback, 3 chiamate mutanti):
#       la quota target E' abbinabile (ordine aggressivo) oppure il book non e'
#       noto -> parcheggio alla quota estrema (BACK 1000 / LAY 1.01), taglio,
#       replace. E' la sequenza storica, quella che in-play fallisce: si prova
#       UNA volta sola e il rifiuto va dichiarato con il codice INTERNO.
#
# Percorso A e percorso B sono decisi da UNA funzione pura (``pianifica_submin``)
# usata da ENTRAMBI gli adattatori: REST (``omega_market.place_submin_live``) e
# flumine (``start_submin``/``advance_submin`` qui sotto). Nessuna copia.

PARK_TARGET = "target"   # percorso A: parcheggio ALLA quota target, niente replace
PARK_FAR = "far"         # percorso B: parcheggio alla quota estrema + replace


@dataclass(frozen=True)
class PianoSubmin:
    """Piano dei gradini deciso PRIMA di toccare Betfair (funzione pura).

    ``rifiuto`` valorizzato = il piano NON e' eseguibile (fail-closed): il
    chiamante deve dichiarare il rifiuto, senza piazzare nulla.
    """

    serve_trucco: bool          # False = place normale (target >= minimo)
    park_mode: str              # PARK_TARGET | PARK_FAR
    park_price: float           # quota del gradino 1
    park_size: float            # size del gradino 1 = minimo di giurisdizione
    target_price: float         # quota finale (al tick)
    target_size: float          # importo finale (sotto minimo)
    size_reduction: float       # quanto si taglia al gradino 2
    serve_replace: bool         # True solo nel percorso B
    chiamate_mutanti: int       # quante chiamate mutanti costa il piano
    motivo: str
    rifiuto: Optional[str] = None


def quota_non_abbinabile(
    side: str, price: float, *,
    best_back: Optional[float] = None,
    best_lay: Optional[float] = None,
) -> Optional[bool]:
    """L'ordine (side, price) resta a riposo senza abbinarsi subito?

    ``best_back`` = migliore quota DISPONIBILE PER BANCARE (top di
    ``availableToBack``); ``best_lay`` = migliore quota DISPONIBILE PER LAYARE
    (top di ``availableToLay``).

    - BACK a quota P: si abbina subito se P <= best_back -> non abbinabile se
      P > best_back (chiedo una quota migliore di quella offerta).
    - LAY a quota P: si abbina subito se P >= best_lay -> non abbinabile se
      P < best_lay.

    Ritorna ``None`` se il dato di book manca: IGNOTO, e chi decide deve
    trattarlo come "potrebbe abbinarsi" (fail-closed sui soldi).
    """
    s = (side or "").lower()
    if s not in _VALID_SIDES:
        raise ValueError(f"side non valido: {side!r} (atteso back|lay)")
    p = float(price)
    if s == "back":
        if best_back is None:
            return None
        return p > float(best_back) + _TOL
    if best_lay is None:
        return None
    return p < float(best_lay) - _TOL


def liability_parcheggio(side: str, park_price: float, park_size: float) -> float:
    """Quanto ESPONE il parcheggio del gradino 1.

    BACK: lo stake. LAY: la liability = size*(quota-1), che col percorso A
    (parcheggio ALLA quota target) puo' essere enorme: 2,00 EUR a quota 95
    sono 188,00 EUR impegnati fino al taglio, contro 0,02 EUR del parcheggio
    a 1.01 del percorso B.
    """
    s = (side or "").lower()
    if s == "lay":
        return round(float(park_size) * (float(park_price) - 1.0), 2)
    return round(float(park_size), 2)


def guardia_cap_parcheggio(side: str, park_price: float, park_size: float,
                           max_stake: Optional[float]) -> None:
    """IL PARCHEGGIO NON ESPONE MAI PIU' DEL CAP (money-critical).

    Solleva ``ValueError`` se la liability del gradino 1 supera il cap
    effettivo per-ordine. Difensiva: cap ignoto (``None``) non blocca, come
    ``_guard_replace_cap_lay`` per il replace.
    """
    if max_stake is None:
        return
    liab = liability_parcheggio(side, park_price, park_size)
    if liab > float(max_stake) + _TOL:
        raise ValueError(
            "parcheggio place-and-trim: liability %.2f EUR a quota %s oltre il "
            "cap %.2f EUR" % (liab, park_price, float(max_stake)))


def pianifica_submin(
    *,
    side: str,
    target_price: float,
    target_size: float,
    jurisdiction: str,
    best_back: Optional[float] = None,
    best_lay: Optional[float] = None,
    consenti_replace: bool = True,
    max_stake: Optional[float] = None,
) -> PianoSubmin:
    """Decide i gradini del place-and-trim. Pura: nessuna rete, nessuno stato.

    E' il NUCLEO UNICO: REST e flumine devono passare di qui, cosi' la sequenza
    e le garanzie sono identiche sui due percorsi.
    """
    s = (side or "").lower()
    if s not in _VALID_SIDES:
        raise ValueError(f"side non valido: {side!r} (atteso back|lay)")
    if target_size is None:
        raise ValueError("target_size mancante")
    tsize = round(float(target_size), 2)
    if tsize <= SUBMIN_ABS_MIN_SIZE - _TOL:
        raise ValueError(
            f"target_size {target_size!r} sotto il floor assoluto "
            f"{SUBMIN_ABS_MIN_SIZE:.2f} EUR"
        )
    minimo = round(float(place_min_size(jurisdiction, s)), 2)
    tick = round_to_tick(float(target_price))

    # Caso banale: non serve nessun trucco.
    if tsize >= minimo - _TOL:
        return PianoSubmin(
            serve_trucco=False, park_mode=PARK_TARGET, park_price=tick,
            park_size=tsize, target_price=tick, target_size=tsize,
            size_reduction=0.0, serve_replace=False, chiamate_mutanti=1,
            motivo=f"target {tsize:.2f} >= minimo {minimo:.2f}: place normale",
        )

    riduzione = round(minimo - tsize, 2)
    if riduzione < 0.01:
        raise ValueError(f"riduzione nulla: minimo {minimo} target {tsize}")

    passiva = quota_non_abbinabile(s, tick, best_back=best_back, best_lay=best_lay)
    # GUARDIA money-critical: nel percorso A il parcheggio sta ALLA quota target,
    # quindi per un LAY impegna size*(quota-1). Se sfonda il cap effettivo NON si
    # usa il percorso A: si ripiega sul parcheggio lontano (1.01, liability
    # trascurabile) e, se nemmeno quello e' possibile, si rifiuta.
    cap_sfondato = False
    if passiva is True and max_stake is not None:
        liab_park = liability_parcheggio(s, tick, minimo)
        cap_sfondato = liab_park > float(max_stake) + _TOL
    if passiva is True and cap_sfondato:
        if not consenti_replace:
            return PianoSubmin(
                serve_trucco=True, park_mode=PARK_FAR,
                park_price=initial_place_price(s), park_size=minimo,
                target_price=tick, target_size=tsize, size_reduction=riduzione,
                serve_replace=True, chiamate_mutanti=0,
                motivo="parcheggio oltre il cap e replace non consentito",
                rifiuto=("SUBMIN_CAP_PARCHEGGIO: il parcheggio del minimo a "
                         "quota %s impegnerebbe %.2f EUR, oltre il cap %.2f EUR; "
                         "nessun ordine piazzato." % (
                             tick, liability_parcheggio(s, tick, minimo),
                             float(max_stake))),
            )
        return PianoSubmin(
            serve_trucco=True, park_mode=PARK_FAR,
            park_price=initial_place_price(s), park_size=minimo,
            target_price=tick, target_size=tsize, size_reduction=riduzione,
            serve_replace=True, chiamate_mutanti=3,
            motivo=("percorso B forzato: il parcheggio alla quota target "
                    "impegnerebbe %.2f EUR, oltre il cap %.2f EUR" % (
                        liability_parcheggio(s, tick, minimo), float(max_stake))),
        )
    if passiva is True:
        return PianoSubmin(
            serve_trucco=True, park_mode=PARK_TARGET, park_price=tick,
            park_size=minimo, target_price=tick, target_size=tsize,
            size_reduction=riduzione, serve_replace=False, chiamate_mutanti=2,
            motivo=(
                f"percorso A: quota {tick} NON abbinabile "
                f"(best_back={best_back}, best_lay={best_lay}) -> parcheggio "
                "ALLA quota target e taglio in loco, nessun replace"
            ),
        )

    perche = ("quota target abbinabile: il parcheggio del minimo alla quota "
              "target si abbinerebbe per intero"
              if passiva is False else
              "book NON noto: la quota target potrebbe essere abbinabile")
    if not consenti_replace:
        return PianoSubmin(
            serve_trucco=True, park_mode=PARK_FAR,
            park_price=initial_place_price(s), park_size=minimo,
            target_price=tick, target_size=tsize, size_reduction=riduzione,
            serve_replace=True, chiamate_mutanti=0,
            motivo="percorso B necessario ma replace non consentito",
            rifiuto=(
                "SUBMIN_REPLACE_VIETATO: " + perche + "; il percorso B usa "
                "replaceOrders, che in-play viene rifiutato "
                "(CANCELLED_NOT_PLACED). Nessun ordine piazzato."
            ),
        )
    return PianoSubmin(
        serve_trucco=True, park_mode=PARK_FAR,
        park_price=initial_place_price(s), park_size=minimo,
        target_price=tick, target_size=tsize, size_reduction=riduzione,
        serve_replace=True, chiamate_mutanti=3,
        motivo="percorso B (parcheggio lontano + replace): " + perche,
    )


def marca_submin(piano: "PianoSubmin", *, bet_id: Optional[str] = None,
                 steps: Optional[list] = None) -> dict:
    """MARCA da appendere all'ordine/trade: "questo e' TRIMMATO, non piazzato".

    Serve ai controlli di condotta del banco comune (famiglia B8, minimi .it):
    senza marca un ordine da 0,79 EUR e' una VIOLAZIONE (piazzato sotto minimo);
    con la marca e' legale (parcheggiato al minimo e poi ridotto). Il banco deve
    violare SOLO se un ordine sotto minimo NON porta questa marca.
    """
    return {
        "park_price": piano.park_price,
        "park_size": piano.park_size,
        "trimmed_from": piano.park_size,
        "target_size": piano.target_size,
        "target_price": piano.target_price,
        "size_reduction": piano.size_reduction,
        "park_mode": piano.park_mode,
        "serve_replace": piano.serve_replace,
        "chiamate_mutanti": piano.chiamate_mutanti,
        "bet_id": bet_id,
        "steps": list(steps or ([] if not piano.serve_trucco else
                                (["place", "cancel"] if not piano.serve_replace
                                 else ["place", "cancel", "replace"]))),
    }


# ---------------------------------------------------------------------------
# Lettura dei report Betfair: esterno E INTERNO
# ---------------------------------------------------------------------------
# Reperto 25: leggevamo solo l'``errorCode`` ESTERNO del ReplaceInstructionReport
# (``CANCELLED_NOT_PLACED`` = "Bet cancelled but replacement bet was not
# placed"), che dice COSA e' successo ma non PERCHE'. Il perche' sta nei report
# ANNIDATI (``placeInstructionReport``/``cancelInstructionReport``): da 111
# rifiuti non abbiamo il codice vero. Qui si estraggono tutti, e i chiamanti li
# persistono.

def esito_istruzione(report: Any) -> dict:
    """Normalizza un report Betfair (place/cancel/replace) in un dict piatto.

    Chiavi del VERO, camelCase, come le manda Betfair:
    ``instructionReports``, ``status``, ``errorCode``, ``betId``,
    ``sizeMatched``, ``sizeCancelled``, ``orderStatus``,
    ``placeInstructionReport``, ``cancelInstructionReport``.
    """
    rep = report if isinstance(report, dict) else {}
    reports = rep.get("instructionReports") or []
    ir = reports[0] if reports and isinstance(reports[0], dict) else {}
    pir = ir.get("placeInstructionReport") or {}
    cir = ir.get("cancelInstructionReport") or {}
    if not isinstance(pir, dict):
        pir = {}
    if not isinstance(cir, dict):
        cir = {}
    return {
        "status": rep.get("status"),
        "istruzione_status": ir.get("status"),
        "error_code": ir.get("errorCode") or rep.get("errorCode"),
        # CODICE INTERNO: il motivo VERO di un CANCELLED_NOT_PLACED.
        "place_status": pir.get("status"),
        "place_error_code": pir.get("errorCode"),
        "cancel_status": cir.get("status"),
        "cancel_error_code": cir.get("errorCode"),
        "bet_id": pir.get("betId") or ir.get("betId"),
        "size_matched": float(pir.get("sizeMatched") or ir.get("sizeMatched") or 0.0),
        "size_cancelled": float(
            cir.get("sizeCancelled") or ir.get("sizeCancelled") or 0.0),
        "order_status": pir.get("orderStatus") or ir.get("orderStatus"),
        "placed_date": pir.get("placedDate") or ir.get("placedDate"),
        "average_price_matched": pir.get("averagePriceMatched")
        or ir.get("averagePriceMatched"),
    }


def codice_rifiuto(esito: dict) -> Optional[str]:
    """Codice da dichiarare al chiamante: l'INTERNO se c'e', altrimenti l'esterno.

    ``CANCELLED_NOT_PLACED`` da solo non e' una diagnosi; con il codice interno
    (``INVALID_BET_SIZE``, ``INVALID_PROFIT_RATIO``, ``MARKET_SUSPENDED``,
    ``BET_LAPSED_PRICE_IMPROVEMENT``, ...) lo diventa.
    """
    esterno = esito.get("error_code")
    interno = esito.get("place_error_code") or esito.get("cancel_error_code")
    if esterno and interno:
        return f"{esterno}:{interno}"
    return str(interno or esterno) if (interno or esterno) else None


# ---------------------------------------------------------------------------
# Macchina a stati
# ---------------------------------------------------------------------------
def advance_submin(
    market: Any,
    state: SubminState,
    *,
    order: Any = None,
    jurisdiction: str,
    customer_order_ref: str,
    ops: Optional[SubminOps] = None,
    allow_place: bool = True,
    now_ms: Optional[int] = None,
) -> SubminState:
    """Avanza la sequenza submin di UNO step in base allo stato REALE dell'ordine.

    - Guardia rischio: se nelle fasi a quota non abbinabile (INIT/PLACED/TRIMMED)
      l'ordine risulta `size_matched > 0` → `ABORTED` (mai ritentare).
    - Idempotente / ripristinabile: le transizioni si basano su ciò che si OSSERVA
      sull'ordine (bet_id, status, size_remaining, prezzo), non solo su `state.step`;
      ri-chiamarla con lo stesso stato non causa doppi place/cancel/replace.
    - `ops` (iniettabile) astrae place/cancel/replace per i test; in produzione il
      runner inietta `FlumineSubminOps`.

    `allow_place` (SICUREZZA money-critical): l'UNICO step che può PIAZZARE è INIT.
    Il primo avvio (``_start_submin``) chiama con il default ``allow_place=True``. La
    sola-ripresa (``_advance_submin_row``, righe già 'processing') chiama con
    ``allow_place=False``: in quel percorso lo stato INIT significa che lo step1 era
    stato persistito *prima* del place reale e il processo è poi caduto/ripartito,
    quindi il place POTREBBE essere GIÀ avvenuto. In ripresa NON si piazza mai un
    secondo ordine: o l'ordine è riconciliabile con certezza (bet_id assegnato), o si
    abortisce per riconciliazione manuale. Vedi il ramo STEP 1.
    """
    # Stati terminali: nessuna azione (idempotente).
    if state.step in _TERMINAL:
        return state

    # --- GUARDIA RISCHIO ---------------------------------------------------
    # Un match mentre l'ordine è alla quota non abbinabile = anomalia: STOP, niente ritento.
    if (
        state.step in _UNMATCHABLE_PHASES
        and order is not None
        and _size_matched(order) > _TOL
    ):
        return _dc_replace(
            state,
            step=SubminStep.ABORTED,
            bet_id=_bet_id(order) or state.bet_id,
            note=(
                f"ABORT: step1 abbinato (size_matched={_size_matched(order):.2f}) "
                "alla quota non abbinabile — nessun ritento, riconciliare a mano"
            ),
        )

    # --- STEP 1: place size minima @ quota non abbinabile ------------------
    if state.step == SubminStep.INIT:
        # Ripresa: se un ordine risulta GIÀ piazzato (bet_id assegnato), non ri-piazzare.
        if order is not None and _bet_id(order) is not None:
            return _dc_replace(
                state,
                step=SubminStep.PLACED,
                bet_id=_bet_id(order),
                note="resume: ordine step1 già presente (no re-place)",
            )
        # SICUREZZA money-critical — ripresa dopo RIAVVIO del processo (allow_place=False):
        # lo stato INIT in sola-ripresa = step1 persistito PRIMA del place reale + crash,
        # quindi il place POTREBBE essere già avvenuto sul mercato. Dopo un riavvio reale le
        # annotazioni locali (notes/context con il ref interno awlq<id>) sono PERSE — l'ordine
        # ricostruito dall'order stream non le porta — e non abbiamo né order_id né bet_id:
        # l'ordine NON è riconciliabile con CERTEZZA. Regola onesta: MAI un secondo place.
        #   - ordine ritrovato ma bet_id non ancora assegnato → ATTENDI (stato invariato);
        #   - ordine NON riconciliabile → ABORTED (riconciliazione manuale), zero place.
        if not allow_place:
            if order is not None:
                return state  # ritrovato (in-process, per ref): attende il bet_id, no place
            return _dc_replace(
                state,
                step=SubminStep.ABORTED,
                bet_id=state.bet_id,
                note=(
                    "submin interrotto a meta': riconciliare manualmente su Betfair, "
                    "NON ripiazzato"
                ),
            )
        park = state.prezzo_parcheggio
        # DIFESA IN PROFONDITA': il cap si ri-valida al momento del place, con
        # il cap EFFETTIVO che porta l'adattatore (lo stato persistito potrebbe
        # venire da un cap diverso).
        guardia_cap_parcheggio(state.side, park, state.placed_size,
                               getattr(ops, "max_stake", None))
        placed_order = _require_ops(ops).place(
            market,
            side=state.side,
            price=park,
            size=state.placed_size,
            customer_order_ref=customer_order_ref,
        )
        return _dc_replace(
            state,
            step=SubminStep.PLACED,
            bet_id=_bet_id(placed_order),
            note=f"step1 place {state.placed_size:.2f}@{park} (LAPSE)",
        )

    # --- STEP 2: cancel parziale (size_reduction) → resta target -----------
    # FIX 11/07 (bug live 10/07 21:43, money-critical): il passaggio a TRIMMED
    # avviene SOLO quando il trim viene OSSERVATO sull'ordine (size_remaining
    # ≈ target). L'esito API del cancel NON è una prova: quella sera il log
    # diceva "trimmed ✓" mentre il park era intatto (o già abbinato), e il
    # replace successivo ha portato 2€ PIENI a quota reale, 4 volte di fila.
    if state.step == SubminStep.PLACED:
        now = int(now_ms if now_ms is not None else time.time() * 1000)
        bid = _bet_id(order)
        if order is None or bid is None or not _is_executable(order):
            # Park SPARITO dopo la richiesta di trim (zero matched, zero
            # residuo, non executable) = cancellato per intero (es. doppia
            # riduzione): sequenza fallita in modo PULITO, nessun rischio.
            rem_gone = _size_remaining(order) if order is not None else None
            if (
                state.trim_requested_ms > 0
                and order is not None
                and _size_matched(order) <= _TOL
                and rem_gone is not None
                and rem_gone <= _TOL
            ):
                return _dc_replace(
                    state, step=SubminStep.ABORTED,
                    bet_id=_bet_id(order) or state.bet_id,
                    note=(
                        "step2: park scomparso (cancellato per intero) — "
                        "sequenza fallita pulita, nessun residuo a rischio"
                    ),
                )
            return state  # attesa: l'ordine non è ancora confermato/abbinabile
        rem = _size_remaining(order)
        # UNICA promozione a TRIMMED: l'osservazione del residuo al target.
        if rem is not None and rem <= state.target_size + _TOL:
            return _dc_replace(
                state, step=SubminStep.TRIMMED, bet_id=bid,
                note=(
                    f"step2 VERIFICATO su osservazione: residuo {rem:.2f} "
                    f"≤ target {state.target_size:.2f}"
                ),
            )
        if state.trim_requested_ms <= 0:
            _require_ops(ops).cancel(market, order, state.size_reduction)
            return _dc_replace(
                state, bet_id=bid, trim_requested_ms=now,
                note=(
                    f"step2 cancel {state.size_reduction:.2f} RICHIESTO → "
                    "in attesa della verifica osservata"
                ),
            )
        waited = now - state.trim_requested_ms
        if waited >= _TRIM_TIMEOUT_MS:
            # Trim mai osservato: MAI proseguire (il replace porterebbe la
            # size piena a quota abbinabile). Ritiro totale e stop.
            _require_ops(ops).cancel(market, order, None)
            return _dc_replace(
                state, step=SubminStep.ABORTED, bet_id=bid,
                note=(
                    "step2: trim NON osservato entro timeout → full cancel + "
                    "abort (mai replace a size piena)"
                ),
            )
        if waited >= _TRIM_RECHECK_MS and rem is not None and rem >= state.placed_size - _TOL:
            # Residuo INTATTO oltre la latenza attesa: il cancel non ha agito.
            # UNA ri-emissione per volta (il timestamp riparte → la prossima
            # scadenza utile è il timeout). Se entrambe le riduzioni agissero,
            # l'ordine sparisce per intero → ramo "park scomparso" (pulito).
            _require_ops(ops).cancel(market, order, state.size_reduction)
            return _dc_replace(
                state, bet_id=bid, trim_requested_ms=now,
                note="step2 cancel RI-EMESSO (residuo intatto oltre la latenza attesa)",
            )
        return state  # attesa dell'osservazione del trim

    # --- STEP 3: replace alla quota target reale ---------------------------
    if state.step == SubminStep.TRIMMED:
        bid = _bet_id(order) or state.bet_id
        if order is None or not _is_executable(order):
            # Park sparito senza matched (cancellato per intero) → abort
            # pulito invece di attesa infinita.
            rem_gone = _size_remaining(order) if order is not None else None
            if (
                order is not None
                and _size_matched(order) <= _TOL
                and rem_gone is not None
                and rem_gone <= _TOL
            ):
                return _dc_replace(
                    state, step=SubminStep.ABORTED, bet_id=bid,
                    note="step3: park scomparso (cancellato per intero) — sequenza fallita pulita",
                )
            return state  # attesa
        # PERCORSO A (17/09): il parcheggio era GIA' alla quota target, quindi
        # dopo il taglio l'ordine e' gia' dove deve stare: nessun replace, e
        # quindi nessun ``CANCELLED_NOT_PLACED`` possibile.
        if not state.serve_replace:
            return _dc_replace(
                state, step=SubminStep.REPRICED, bet_id=bid,
                note=("percorso A: parcheggio alla quota target, "
                      "nessun replace necessario"),
            )
        # Idempotenza/ripresa: se è già alla target_price, avanza.
        cur_price = _order_price(order)
        if cur_price is not None and abs(cur_price - state.target_price) <= _TOL:
            return _dc_replace(
                state, step=SubminStep.REPRICED, bet_id=bid,
                note="resume: ordine già alla target_price (no re-replace)",
            )
        # DIFESA IN PROFONDITÀ (bug 21:43): mai un replace se il residuo
        # osservato NON è al target — porterebbe una size piena a quota reale.
        rem = _size_remaining(order)
        if rem is None or rem > state.target_size + _TOL:
            _require_ops(ops).cancel(market, order, None)
            return _dc_replace(
                state, step=SubminStep.ABORTED, bet_id=bid,
                note=(
                    f"step3: residuo osservato {rem if rem is not None else 'sconosciuto'} "
                    f"oltre il target {state.target_size:.2f} — replace VIETATO, "
                    "full cancel + abort"
                ),
            )
        _require_ops(ops).replace(market, order, state.target_price)
        return _dc_replace(
            state, step=SubminStep.REPRICED, bet_id=bid,
            note=f"step3 replace → {state.target_price}",
        )

    # --- DONE: ordine a riposo a (target_price, target_size) ---------------
    if state.step == SubminStep.REPRICED:
        return _dc_replace(
            state, step=SubminStep.DONE, bet_id=_bet_id(order) or state.bet_id,
            note="submin completato: ordine sotto-minimo a riposo alla target_price",
        )

    return state  # difensivo (mai raggiunto)


def _require_ops(ops: Optional[SubminOps]) -> SubminOps:
    if ops is None:
        raise ValueError(
            "advance_submin richiede `ops` (SubminOps) per place/cancel/replace: "
            "il runner deve iniettare FlumineSubminOps(selection_id, handicap, jurisdiction)"
        )
    return ops
