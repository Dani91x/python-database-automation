"""saldo_evento.py - rilettura del SALDO del conto Betfair DOPO un evento d'ordine.

Perche' esiste (23/09, bug dell'utente: "il saldo non si aggiorna, ne' quando
partono gli ordini, ne' quando vengono chiusi"): fino a oggi il saldo lo
leggeva SOLO il runner calcio (``reconcile_worker.run_account_sync_if_due``,
cadenza fissa 20 s). Gli ordini veri li piazzano ANCHE processi separati
(Omega, Safe, Mike via REST; runner tennis e bot tennis via flumine): nessuno
di loro rileggeva il saldo, e la pagina lo vedeva cambiare solo al giro del
runner calcio (se vivo).

Regola: il processo che POSSIEDE il client Betfair dell'ordine, e solo lui,
rilegge il saldo UNA volta per evento d'ordine (piazzamento confermato,
chiusura/regolazione), scrive ``betfair_live_account`` e pubblica il topic
``account`` sul SUO canale locale (stesso formato del runner calcio:
``{"available", "exposure", "checked_at"}`` + ``fonte``). Niente polling in
piu': nessun evento, nessuna chiamata.

MONEY-CRITICAL / regole:
  * mai sollevare verso chi ha piazzato l'ordine: la rilettura gira in un
    thread a parte e ogni errore finisce nel log;
  * mai rallentare il percorso d'ordine: ``segnala`` e' solo un flag + avvio
    di un thread demone;
  * coalescenza: eventi che arrivano mentre una lettura e' GIA' in coda ne
    condividono l'esito (una lettura in coda basta a vedere lo stato dopo
    tutti); un evento che arriva DURANTE una lettura ne provoca UNA dopo;
  * INATTIVO finche' il processo non chiama ``attiva(get_funds)``: nei test e
    nei processi che non lo accendono ``segnala`` non fa nulla (nessuna rete);
  * il saldo e' del CONTO reale: paper e live non si sommano mai, e un ordine
    paper non passa da qui (i chiamanti agganciano solo il percorso REALE).
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Tuple

logger = logging.getLogger(__name__)

# funzione che fa UNA chiamata getAccountFunds col client del processo
_GET_FUNDS: Optional[Callable[[], Any]] = None
# callback opzionale dopo una lettura riuscita (runner calcio: allinea
# l'orologio e la firma write-on-change di reconcile_worker)
_DOPO_LETTURA: Optional[Callable[[Tuple[Optional[float], Optional[float]]], None]] = None
_NOME: str = ""

_LOCK = threading.Lock()
_IN_CODA = False          # una lettura e' stata chiesta e non e' ancora iniziata
_THREAD: Optional[threading.Thread] = None


def attiva(get_funds: Callable[[], Any], *, nome: str = "",
           dopo_lettura: Optional[Callable[[Tuple[Optional[float], Optional[float]]], None]] = None) -> None:
    """Accende la rilettura su evento per QUESTO processo."""
    global _GET_FUNDS, _DOPO_LETTURA, _NOME
    _GET_FUNDS = get_funds
    _DOPO_LETTURA = dopo_lettura
    _NOME = nome or ""


def disattiva() -> None:
    """Spegne (test/teardown)."""
    global _GET_FUNDS, _DOPO_LETTURA, _NOME
    _GET_FUNDS = None
    _DOPO_LETTURA = None
    _NOME = ""


def attiva_in_questo_processo() -> bool:
    return _GET_FUNDS is not None


def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, 2) if f == f else None  # NaN -> None


def _campo(funds: Any, snake: str, camel: str) -> Any:
    """Legge un campo sia dalla risorsa betfairlightweight (``AccountFunds``,
    attributi snake_case) sia dal dict JSON-RPC del client REST
    (``availableToBetBalance``/``exposure``): stesse chiavi del vero."""
    if isinstance(funds, dict):
        if camel in funds:
            return funds.get(camel)
        return funds.get(snake)
    return getattr(funds, snake, None)


def firma_da_funds(funds: Any) -> Tuple[Optional[float], Optional[float]]:
    return (
        _num(_campo(funds, "available_to_bet_balance", "availableToBetBalance")),
        _num(_campo(funds, "exposure", "exposure")),
    )


def rileggi_saldo(motivo: str) -> Optional[Tuple[Optional[float], Optional[float]]]:
    """UNA lettura + UNA scrittura + UNA pubblicazione. Sincrona, mai solleva.

    Ritorna la firma (available, exposure) scritta, o None se non attiva/KO."""
    get_funds = _GET_FUNDS
    if get_funds is None:
        return None
    try:
        funds = get_funds()
    except Exception as ex:  # noqa: BLE001 - mai propagare al percorso d'ordine
        logger.warning("[saldo-evento] getAccountFunds KO (%s): %s", motivo, str(ex)[:200])
        return None
    sig = firma_da_funds(funds)
    if sig[0] is None:
        logger.warning("[saldo-evento] risposta senza availableToBetBalance (%s): scarto", motivo)
        return None
    checked_at = datetime.now(timezone.utc).isoformat()
    try:
        from . import db

        # stesso istante della lettura su DB e canale (F1 revisore A, 23/09)
        db.upsert_live_account(sig[0], sig[1], updated_at=checked_at)
    except Exception as ex:  # noqa: BLE001
        logger.warning("[saldo-evento] upsert saldo KO (%s): %s", motivo, str(ex)[:200])
    try:
        from . import local_channel as _lc

        _lc.publish("account", {
            "available": sig[0],
            "exposure": sig[1],
            "checked_at": checked_at,
            "fonte": f"{_NOME}:{motivo}" if _NOME else motivo,
        })
    except Exception:  # noqa: BLE001 - canale opzionale
        pass
    cb = _DOPO_LETTURA
    if cb is not None:
        try:
            cb(sig)
        except Exception:  # noqa: BLE001
            logger.debug("[saldo-evento] dopo_lettura KO", exc_info=True)
    logger.info("[saldo-evento] saldo riletto dopo %s: disponibile %s, esposizione %s",
                motivo, sig[0], sig[1])
    return sig


def _giro() -> None:
    global _IN_CODA, _THREAD
    while True:
        with _LOCK:
            if not _IN_CODA:
                _THREAD = None
                return
            _IN_CODA = False
            motivo = _MOTIVO[0]
        rileggi_saldo(motivo)


_MOTIVO = ["evento"]


def segnala(motivo: str = "evento") -> None:
    """Un evento d'ordine REALE e' avvenuto: chiede UNA rilettura del saldo.

    No-op se il processo non ha chiamato ``attiva``. Non blocca, non solleva."""
    global _IN_CODA, _THREAD
    if _GET_FUNDS is None:
        return
    try:
        with _LOCK:
            _IN_CODA = True
            _MOTIVO[0] = str(motivo)
            if _THREAD is not None:
                return  # il thread vivo la prendera' al prossimo giro
            t = threading.Thread(target=_giro, name="saldo-evento", daemon=True)
            _THREAD = t
        t.start()
    except Exception:  # noqa: BLE001 - mai rompere il chiamante
        logger.debug("[saldo-evento] segnala KO", exc_info=True)


def attendi(timeout: float = 5.0) -> None:
    """SOLO test: aspetta che il thread di rilettura abbia finito."""
    t = _THREAD
    if t is not None:
        t.join(timeout)


# ---------------------------------------------------------------------------
# Regolazioni (REST): un bet regolato MAI visto prima in questo processo
# ---------------------------------------------------------------------------
_REGOLATI_VISTI: set = set()
_REGOLATI_SEMINATI = False


def nota_regolati(bet_ids: Any) -> bool:
    """Chi legge i regolati (``listClearedOrders``) passa i bet_id visti.

    La PRIMA lettura del processo SEMINA soltanto (i regolati di ieri non sono
    un evento di oggi); dopo, un bet_id nuovo = una regolazione avvenuta ->
    UNA rilettura. Ritorna True se ha segnalato."""
    global _REGOLATI_SEMINATI
    if _GET_FUNDS is None:
        return False
    ids = {str(b) for b in (bet_ids or []) if b}
    with _LOCK:
        nuovi = ids - _REGOLATI_VISTI
        _REGOLATI_VISTI.update(ids)
        seminato = _REGOLATI_SEMINATI
        _REGOLATI_SEMINATI = True
    if seminato and nuovi:
        segnala("regolazione")
        return True
    return False


def azzera() -> None:
    """SOLO test: stato del modulo come a processo appena partito."""
    global _IN_CODA, _THREAD, _REGOLATI_SEMINATI
    attendi()
    disattiva()
    with _LOCK:
        _IN_CODA = False
        _THREAD = None
        _REGOLATI_VISTI.clear()
        _REGOLATI_SEMINATI = False


# ---------------------------------------------------------------------------
# Processi flumine (runner calcio, runner tennis): LoggingControl
# ---------------------------------------------------------------------------
def controllo_flumine() -> Any:
    """Un ``LoggingControl`` flumine che segnala sugli eventi d'ordine REALI.

    flumine emette ``OrderEvent`` quando Betfair conferma un piazzamento (bet_id
    assegnato) o un replace (``execution/baseexecution.py``), e
    ``ClearedOrdersEvent`` quando i regolati di un mercato chiuso arrivano
    (``worker.py``). Gli ordini simulati (paper) sono ignorati: il saldo e' del
    conto reale."""
    from flumine.controls.loggingcontrols import LoggingControl

    class ControlloSaldo(LoggingControl):
        NAME = "SALDO_EVENTO"

        def _process_order(self, event: Any) -> None:
            order = getattr(event, "event", None)
            if order is None or getattr(order, "simulated", False):
                return
            segnala("ordine")

        def _process_cleared_orders(self, event: Any) -> None:
            segnala("regolazione")

    return ControlloSaldo()
