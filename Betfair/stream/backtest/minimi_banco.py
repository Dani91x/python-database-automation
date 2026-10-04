"""minimi_banco.py - IL BANCO RIFIUTA COME BETFAIR .it GLI ORDINI SOTTO IL MINIMO.

02/10/2026 (punto 3 dell'utente, reperto R1 del correttore di Mike del 01/10).
Fatto: il simulatore del banco ABBINAVA ordini che Betfair .it rifiuta per taglia.
``cliente_simulato`` apre i tetti di flumine (``min_bet_size`` 0: sono limiti di
flumine e in GBP) e nessuno metteva al loro posto i minimi VERI del listino
italiano; il place-and-trim della coda (``MercatoFlumine``) piazzava diretto qualunque
importo. Cosi' le banche di chiusura da 0,59 / 0,14 / 0,03 / 0,01 di Mike nelle
sintetiche risultavano «abbinate» e il difetto di Ashdod (banca di chiusura
0,43 @ 18 rifiutata INVALID_BET_SIZE 21 volte, 01/10 LIVE) nel replay non si
vedeva.

Qui c'e' la regola dell'EXCHANGE simulato, nel punto in cui flumine esegue i
pacchetti (``SimulatedExecution.execute_place`` / ``execute_replace``), quindi
per entrambi i trasporti (coda e canale) e per ogni bot del banco:

  * ordine piazzato DIRETTO: punta sotto ``IT_MIN_BACK`` (1,00) o banca sotto
    ``IT_MIN_LAY`` (1,00) -> FAILURE ``INVALID_BET_SIZE``, nessun abbinato;
  * 04/10/2026 (regola delle punte dell'utente; Umea FC v Hammarby, punta di chiusura
    7,27 rifiutata LIVE): punta piazzata DIRETTA da 1,00 in su NON multipla di 0,50
    -> FAILURE ``INVALID_BET_SIZE`` (``punta_fuori_passo``). Fino a oggi il banco la
    abbinava (stessa regola sbagliata di ``minimi_it`` del 01/10): replay verdi;
  * ordine NUOVO di un replace (la coda del place-and-trim: parcheggio >= 1,00,
    taglio, replace alla quota voluta) e place-and-trim della coda
    (il place-and-trim della coda di ``MercatoFlumine``, nota ``NOTA_PLACE_AND_TRIM``): sotto
    ``SUBMIN_IMPORTO_FINALE_MIN`` (0,50, floor di legge) -> FAILURE
    ``INVALID_BET_SIZE``.
I minimi si leggono dalla fonte unica ``Betfair/stream/trading/minimi_it.py``.

Il CONTROLLO di certificazione (``abbinati_sotto_minimo``) e' indipendente
dalla regola: guarda gli ordini che flumine ha davvero eseguito e dice se uno
sotto il suo minimo ha un abbinato. Con la regola spenta (``ATTIVO = False``,
solo per la falsificazione) il controllo deve diventare rosso.

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import contextlib
from typing import Any, Dict, Iterator, List, Optional

from ..trading.minimi_it import IT_MIN_BACK, IT_MIN_LAY, SUBMIN_IMPORTO_FINALE_MIN
from ..trading.minimi_it import VIA_DIRETTA as _VIA_DIRETTA
from ..trading.minimi_it import importo_piazzabile as _importo_piazzabile

#: la regola dell'exchange simulato. ``False`` SOLO per la falsificazione: il
#: controllo ``abbinati_sotto_minimo`` deve allora trovare gli abbinati.
ATTIVO = True

#: il codice che Betfair da' a un importo fuori listino
CODICE_TAGLIA = "INVALID_BET_SIZE"

#: nota dell'ordine flumine piazzato dal place-and-trim della coda del banco
NOTA_PLACE_AND_TRIM = "banco_place_and_trim"

#: codice della violazione di certificazione (referto del banco)
CODICE_CONTROLLO = "BANCO-SOTTO-MINIMO"
REGOLA_CONTROLLO = ("nessun ordine sotto il minimo Betfair .it abbinato dal banco "
                    "(punta 1,00 a multipli di 0,50 e banca 1,00 dirette; importo "
                    "finale del place-and-trim >= 0,50): Betfair lo rifiuta "
                    "INVALID_BET_SIZE")

DIRETTO = "diretto"
SOSTITUZIONE = "sostituzione"
PLACE_AND_TRIM = "place_and_trim"


class Registro:
    """Gli ordini che l'exchange simulato ha visto in UN replay."""

    def __init__(self) -> None:
        # (ordine flumine, tipo, size al piazzamento)
        self.piazzati: List[tuple] = []
        self.rifiutati: List[Dict[str, Any]] = []

    def azzera(self) -> None:
        self.piazzati.clear()
        self.rifiutati.clear()


#: il registro del processo (un replay per processo, ``certifica._lavora``)
REGISTRO = Registro()


def minimo_per(tipo: str, side: Any) -> float:
    """Il minimo dell'exchange per un ordine di questo tipo e lato."""
    if tipo in (SOSTITUZIONE, PLACE_AND_TRIM):
        return float(SUBMIN_IMPORTO_FINALE_MIN)
    lato = str(getattr(side, "value", side) or "").upper()
    return float(IT_MIN_LAY if lato == "LAY" else IT_MIN_BACK)


def sotto_minimo(size: Any, tipo: str, side: Any) -> bool:
    try:
        s = round(float(size or 0.0), 2)
    except (TypeError, ValueError):
        return False
    return s < minimo_per(tipo, side) - 0.0005


def punta_fuori_passo(size: Any, tipo: str, side: Any) -> bool:
    """04/10/2026 (regola delle punte dell'utente): una PUNTA piazzata DIRETTA da 1,00 in
    su che NON e' un multiplo di 0,50 (``minimi_it.importo_piazzabile``: residuo > 0).
    Betfair .it la rifiuta ``INVALID_BET_SIZE`` (Umea FC v Hammarby, 04/10, punta di
    chiusura 7,27 @1,07). Solo il piazzamento DIRETTO: il sostituto di un replace e il
    finale del place-and-trim sono il resto di un ordine gia' esistente."""
    if tipo != DIRETTO:
        return False
    lato = str(getattr(side, "value", side) or "").upper()
    if lato != "BACK":
        return False
    try:
        v = _importo_piazzabile("back", size)
    except ValueError:
        return False
    return v.via == _VIA_DIRETTA and v.residuo > 0.0


def fuori_listino(size: Any, tipo: str, side: Any) -> bool:
    """L'exchange simulato rifiuta QUESTO ordine per taglia (``INVALID_BET_SIZE``)?
    Sotto il minimo del suo tipo, oppure punta diretta non multipla di 0,50."""
    return sotto_minimo(size, tipo, side) or punta_fuori_passo(size, tipo, side)


def _size(ordine: Any) -> float:
    try:
        return float(getattr(getattr(ordine, "order_type", None), "size", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _tipo(ordine: Any) -> str:
    note = getattr(ordine, "notes", None)
    if isinstance(note, dict) and note.get(NOTA_PLACE_AND_TRIM):
        return PLACE_AND_TRIM
    return DIRETTO


@contextlib.contextmanager
def _rifiuta_piazzamento(ordine: Any) -> Iterator[None]:
    """Per UNA chiamata di ``simulated.place``: FAILURE ``INVALID_BET_SIZE``, la
    size esce dal residuo come negli altri rifiuti di flumine (``size_voided``),
    nessun abbinato, nessun ordine vivo."""
    sim = ordine.simulated
    vero = sim.place

    def _place(*_a: Any, **_k: Any) -> Any:
        sim.size_voided += sim.size_remaining
        return sim._create_place_response(None, status="FAILURE",
                                          error_code=CODICE_TAGLIA)

    sim.place = _place
    try:
        yield
    finally:
        sim.place = vero


def _annota_rifiuto(ordine: Any, tipo: str, size: float) -> None:
    REGISTRO.rifiutati.append({"tipo": tipo, "side": str(getattr(ordine, "side", "")),
                               "size": round(float(size), 2),
                               "minimo": minimo_per(tipo, getattr(ordine, "side", None)),
                               "codice": CODICE_TAGLIA})


@contextlib.contextmanager
def minimi_it_su_flumine() -> Iterator[Registro]:
    """Monta la regola dei minimi .it sull'esecuzione simulata di flumine per la
    durata del ``with`` (la rimette com'era all'uscita, come
    ``orologio_monotono``). Registra SEMPRE gli ordini eseguiti (serve al
    controllo); rifiuta solo con ``ATTIVO``."""
    from flumine.execution.simulatedexecution import SimulatedExecution

    vero_place = SimulatedExecution.execute_place
    vero_replace = SimulatedExecution.execute_replace
    # un registro per simulazione (un replay = una simulazione): niente memoria
    # che cresce fra un replay e l'altro nello stesso processo (suite)
    REGISTRO.azzera()

    def execute_place(self: Any, order_package: Any, http_session: Any = None) -> Any:
        with contextlib.ExitStack() as pila:
            for ordine in order_package:
                tipo, size = _tipo(ordine), _size(ordine)
                REGISTRO.piazzati.append((ordine, tipo, size))
                if ATTIVO and fuori_listino(size, tipo, getattr(ordine, "side", None)):
                    _annota_rifiuto(ordine, tipo, size)
                    pila.enter_context(_rifiuta_piazzamento(ordine))
            return vero_place(self, order_package, http_session)

    def execute_replace(self: Any, order_package: Any, http_session: Any = None) -> Any:
        # 04/10 (CERTIFICAZIONE_TENNIS_PRO_SCALPER, K1 dello scalper tennis): un
        # replace il cui ordine NUOVO e' rifiutato deve lasciare il mondo come lo
        # lascia flumine LIVE (`BetfairExecution.execute_replace`): l'annullo
        # resta fatto (Betfair: "the cancellations will not be rolled back"), il
        # vecchio ordine e' `execution_complete`, e NESSUN ordine sostituto esiste
        # (live lo crea solo su SUCCESS). La simulazione di flumine invece crea il
        # sostituto in `trade.orders` (fuori dal blotter) e rimette il vecchio
        # `executable`: un bot che segue l'ultimo ordine del suo Trade seguirebbe
        # un fantasma che in produzione non esiste.
        respinti: List[tuple] = []
        with contextlib.ExitStack() as pila:
            for ordine in order_package:
                trade = getattr(ordine, "trade", None)
                if trade is None:
                    continue
                crea_vero = trade.create_order_replacement

                def _crea(*a: Any, _vero: Any = crea_vero, _vecchio: Any = ordine,
                          **kw: Any) -> Any:
                    nuovo = _vero(*a, **kw)
                    size = _size(nuovo)
                    REGISTRO.piazzati.append((nuovo, SOSTITUZIONE, size))
                    if ATTIVO and sotto_minimo(size, SOSTITUZIONE,
                                               getattr(nuovo, "side", None)):
                        _annota_rifiuto(nuovo, SOSTITUZIONE, size)
                        sim = nuovo.simulated
                        respinti.append((_vecchio, nuovo))

                        def _place(*_a: Any, **_k: Any) -> Any:
                            sim.size_voided += sim.size_remaining
                            return sim._create_place_response(
                                None, status="FAILURE", error_code=CODICE_TAGLIA)

                        sim.place = _place
                    return nuovo

                trade.create_order_replacement = _crea
                pila.callback(_rimetti_creazione, trade)
            esito = vero_replace(self, order_package, http_session)
        for vecchio, nuovo in respinti:
            _come_live_dopo_sostituto_respinto(vecchio, nuovo)
        return esito

    SimulatedExecution.execute_place = execute_place
    SimulatedExecution.execute_replace = execute_replace
    try:
        yield REGISTRO
    finally:
        SimulatedExecution.execute_place = vero_place
        SimulatedExecution.execute_replace = vero_replace


def _come_live_dopo_sostituto_respinto(vecchio: Any, nuovo: Any) -> None:
    """Il dopo-replace di flumine LIVE quando il piazzamento nuovo fallisce:
    nessun sostituto nel Trade, vecchio ordine completo (annullo non annullato)."""
    trade = getattr(nuovo, "trade", None)
    ordini = getattr(trade, "orders", None)
    if isinstance(ordini, list):
        ordini[:] = [o for o in ordini if o is not nuovo]
    try:
        vecchio.execution_complete()
    except Exception:  # noqa: BLE001 - stato gia' terminale
        pass


def _rimetti_creazione(trade: Any) -> None:
    try:
        del trade.create_order_replacement      # torna il metodo della classe
    except AttributeError:
        pass


def abbinati_sotto_minimo(registro: Optional[Registro] = None) -> List[Dict[str, Any]]:
    """IL CONTROLLO: gli ordini eseguiti dal banco sotto il loro minimo che hanno
    un ABBINATO. Vuoto = sano. Non usa la regola: legge gli ordini di flumine."""
    reg = registro or REGISTRO
    fuori: List[Dict[str, Any]] = []
    for ordine, tipo, size in reg.piazzati:
        sim = getattr(ordine, "simulated", None)
        abbinato = float(getattr(sim, "size_matched", 0.0) or 0.0)
        if abbinato > 0 and fuori_listino(size, tipo, getattr(ordine, "side", None)):
            fuori.append({"tipo": tipo, "side": str(getattr(ordine, "side", "")),
                          "size": round(size, 2), "abbinato": round(abbinato, 2),
                          "minimo": minimo_per(tipo, getattr(ordine, "side", None))})
    return fuori


def testo_violazione(fuori: List[Dict[str, Any]]) -> str:
    o = fuori[0]
    return ("%d ordini sotto il minimo abbinati dal banco; il primo: %s %s %.2f "
            "(minimo %.2f, abbinato %.2f)" % (len(fuori), o["tipo"], o["side"], o["size"],
                                              o["minimo"], o["abbinato"]))
