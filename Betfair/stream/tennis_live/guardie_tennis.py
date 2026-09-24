"""guardie_tennis.py - le guardie del runner TENNIS (reperti T1 e T2, 24/09/2026).

T1 - MODALITA' DEL BOT, MAI EREDITATA DAL RUNNER
------------------------------------------------
Prima del 24/09 la riga di controllo per partita (``tennis_bot_control``) non
portava la modalita' del bot: il ponte scriveva ``dry_run = (mode == 'live')``,
quindi un bot acceso in PAPER nasceva con ``dry_run=False``, e il runner, se
girava in LIVE (``TENNIS_LIVE_ORDER_MODE``), lo eseguiva sul client REALE.
Adesso la modalita' di ESECUZIONE di un bot e' decisa cosi' (``modalita_esecuzione_bot``):

  runner OFF                               -> OFF   (dry_run forzato, come prima)
  runner PAPER                             -> PAPER (nel processo non esiste un client reale)
  runner LIVE  + riga mode='live'          -> LIVE  (reale SOLO con dry_run=False esplicito)
  runner LIVE  + riga mode paper/assente   -> PAPER (client SIMULATO affiancato)

Un bot PAPER dentro un runner LIVE piazza con ``market.place_order(order)``, cioe'
sul client di DEFAULT del framework, che li' e' quello reale. Le strategie non si
toccano: il runner fa passare al bot una VISTA del mercato (``MercatoConClient``)
che aggiunge ``client=<client paper>`` a ogni piazzamento. E' lo stesso schema del
worker calcio (F0, ``live_order_worker._client_for_mode``): il client giusto
passato a ``place_order`` E' l'intera separazione, perche' flumine instrada
l'esecuzione dal client dell'ordine. Seconda rete: il trading control
``ControlloModalitaBotTennis`` rifiuta DENTRO flumine ogni piazzamento di un bot
il cui client non corrisponde alla sua modalita' (paper su reale, o viceversa).

``dry_run`` resta quello di sempre: e' il cancello del BOT su ``market.place_order``.
In PAPER ``dry_run=False`` vuol dire "l'ordine passa dal blotter SIMULATO" (client
``paper_trade=True`` -> ``SimulatedExecution`` di flumine, che non contatta mai
Betfair): serve a vederlo sul ladder e nello specchio ``tennis_live_orders``.

T2 - KILL-SWITCH E GUARDIA D'AVVIO
----------------------------------
Stesso freno del calcio, con le STESSE funzioni (import da ``live_order_worker``,
nessuna copia): ``LIVE_KILL_SWITCH`` dall'ambiente, riletto a ogni chiamata, e
``betfair_live_settings.kill_switch`` dal DB (lo stesso che lo stop giornaliero
del calcio accende). A freno tirato passano SOLO le chiusure: per la coda del
desktop le azioni di ``_CLOSING_ACTIONS``; per i bot un piazzamento che non
aumenta la perdita worst-case della strategia sul mercato (matematica nativa di
flumine ``blotter.market_exposure``, la stessa di ``LiveEventExposureControl``).

Guardia d'avvio (``GUARDIA_RUNNER``, gemella di ``Guardia("runner_calcio")``):
armata all'avvio del runner, disarmata SOLO da una ripresa riuscita (bot di un
avvio vecchio fermati, richieste stantie della coda chiuse in 'error', specchio
paper orfano chiuso). Finche' e' armata: nessun bot si arma, la coda del desktop
non si esegue e i comandi del canale 47332 ricevono subito il rifiuto.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, Optional

from flumine.controls import BaseControl
from flumine.order.orderpackage import OrderPackageType

from .. import avvio_app as _aa
from .. import live_order_worker as _low

logger = logging.getLogger(__name__)


# ===========================================================================
# T1 - modalita' del bot
# ===========================================================================
MODALITA_PAPER = "paper"
MODALITA_LIVE = "live"
# motivo di rifiuto quando manca il client della modalita' (stesso contratto del calcio)
ERR_PAPER_CLIENT_ASSENTE = _low.ERR_PAPER_CLIENT_ASSENTE


def modalita_riga(control: Any) -> str:
    """La modalita' DICHIARATA sulla riga di controllo per partita.

    ``'live'`` SOLO se la riga porta esattamente ``mode='live'`` (spazi e maiuscole
    tollerati). Assente, vuota, ``None`` o qualunque altro valore -> ``'paper'``:
    ai soldi veri si arriva scrivendolo, mai ereditandolo (regola del 14/09)."""
    if not isinstance(control, dict):
        return MODALITA_PAPER
    m = str(control.get("mode") or "").strip().lower()
    return MODALITA_LIVE if m == MODALITA_LIVE else MODALITA_PAPER


def modalita_esecuzione_bot(control: Any, runner_mode: Any) -> str:
    """``'OFF'`` | ``'PAPER'`` | ``'LIVE'``: come il bot ESEGUE davvero.

    LIVE solo se il runner e' LIVE E la riga dichiara ``live``. Il runner non puo'
    promuovere a reale cio' che il bot dichiara simulato; il bot non puo' andare
    a reale se il runner non ha un client reale."""
    r = str(runner_mode or "OFF").strip().upper()
    if r == "LIVE":
        return "LIVE" if modalita_riga(control) == MODALITA_LIVE else "PAPER"
    if r == "PAPER":
        return "PAPER"
    return "OFF"


def dry_run_esplicito_falso(control: Any) -> bool:
    """True SOLO se la riga porta ``dry_run`` ESATTAMENTE ``False`` (booleano).

    Il reale e' il doppio gesto per partita: il bot nasce in dry-run e l'utente
    lo toglie. ``None``, assente, stringhe, numeri: non sono un gesto -> dry-run."""
    return isinstance(control, dict) and control.get("dry_run") is False


class MercatoConClient:
    """VISTA di un ``Market`` flumine che forza il client su ``place_order``.

    Tutto il resto (blotter, market_book, cancel/replace/update, che flumine
    esegue sul client DELL'ORDINE) passa al mercato vero senza modifiche. Il
    ``client`` passato dal chiamante viene SOVRASCRITTO: un bot paper non puo'
    scegliersi il client reale."""

    __slots__ = ("_mercato", "_client")

    def __init__(self, mercato: Any, client: Any) -> None:
        object.__setattr__(self, "_mercato", mercato)
        object.__setattr__(self, "_client", client)

    def place_order(self, order: Any, *args: Any, **kwargs: Any) -> Any:
        kwargs["client"] = self._client
        return self._mercato.place_order(order, *args, **kwargs)

    def __getattr__(self, nome: str) -> Any:
        return getattr(self._mercato, nome)

    def __setattr__(self, nome: str, valore: Any) -> None:
        setattr(self._mercato, nome, valore)


def instrada_ordini_su_client(strat: Any, client: Any) -> None:
    """Fa piazzare al bot ``strat`` i suoi ordini SUL ``client`` dato.

    Per istanza, come lo scoping di ``_scope_to_market``: la classe del bot non
    si tocca. flumine chiama ``strategy.process_market_book(market, book)``
    leggendo l'attributo al momento della chiamata, quindi l'ombra per istanza
    e' quella che gira. ``process_closed_market`` non piazza in nessuno dei 4 bot."""
    orig = strat.process_market_book

    def _con_client(market: Any, market_book: Any, _orig: Any = orig, _c: Any = client) -> Any:
        return _orig(MercatoConClient(market, _c), market_book)

    strat.process_market_book = _con_client  # type: ignore[assignment]
    strat._tennis_client_ordini = client


def is_client_paper(client: Any) -> bool:
    """Stessa definizione del worker calcio (``paper_trade=True`` o venue SIMULATED)."""
    return _low._is_paper_client(client)


def client_paper_del_framework(framework: Any) -> Optional[Any]:
    """Il client SIMULATO registrato nel framework, oppure ``None``."""
    for c in list(getattr(framework, "clients", None) or []):
        if is_client_paper(c):
            return c
    return None


def build_client_paper_affiancato(api_client: Any) -> Any:
    """Client SIMULATO da affiancare al reale nel runner tennis LIVE.

    Stessi parametri del client PAPER del tennis (``tennis_runner.build_order_client``:
    order_stream=True -> SimulatedOrderStream, ``min_bet_validation=False``); la
    classe e' quella del calcio (``client_paper_affiancato.PaperCompanionClient``:
    login/logout/keep-alive/saldo no-op, username ``#paper``). La latenza paper
    (``flumine.config.place_latency``) e' globale di flumine e tocca SOLO la
    ``SimulatedExecution``: la si imposta come nel runner PAPER."""
    from flumine import config as flumine_config

    from ..client_paper_affiancato import PaperCompanionClient
    from .tennis_runner import TENNIS_PAPER_LATENCY_MS_DEFAULT

    lat = float(os.getenv("TENNIS_PAPER_LATENCY_MS", str(TENNIS_PAPER_LATENCY_MS_DEFAULT)) or 0)
    flumine_config.place_latency = max(0.0, lat) / 1000.0
    return PaperCompanionClient(
        api_client, order_stream=True, paper_trade=True, min_bet_validation=False,
    )


class ControlloModalitaBotTennis(BaseControl):
    """Seconda rete di T1, DENTRO flumine: un bot tennis ospitato piazza SOLO sul
    client della sua modalita' di esecuzione.

    Riconosce i bot dall'attributo ``_tennis_modalita_esecuzione`` che
    ``_instantiate_bot`` scrive su ogni istanza; le altre strategie (la capture
    degli ordini del desktop) non sono affar suo: le governa il worker della coda."""

    NAME = "TENNIS_MODALITA_BOT"

    def _validate(self, order: Any, package_type: OrderPackageType) -> None:
        if package_type != OrderPackageType.PLACE:
            return
        trade = getattr(order, "trade", None)
        strategy = getattr(trade, "strategy", None) if trade is not None else None
        mod = getattr(strategy, "_tennis_modalita_esecuzione", None)
        if mod is None:
            return
        paper = is_client_paper(getattr(order, "client", None))
        if str(mod).upper() == "LIVE":
            if paper:
                self._on_error(order, "bot LIVE su client simulato: rifiutato "
                                      "(mai un fill simulato spacciato per reale)")
            return
        if not paper:
            self._on_error(order, "bot %s su client REALE: rifiutato (T1: il runner "
                                  "non promuove a reale un bot simulato)" % mod)


# ===========================================================================
# T2 - kill-switch (stesse funzioni del calcio)
# ===========================================================================
_IMPOSTAZIONI_RILETTE: Dict[str, float] = {"ts": 0.0}
_IMPOSTAZIONI_OGNI_S = 1.0


def aggiorna_impostazioni(sb: Any, forza: bool = False) -> None:
    """Rilegge ``betfair_live_settings`` (RPC ``get_live_settings``) al massimo
    una volta al secondo, con la funzione del calcio (``_refresh_settings``:
    rebind atomico, su errore resta l'ultimo snapshot)."""
    adesso = time.monotonic()
    if not forza and adesso - _IMPOSTAZIONI_RILETTE["ts"] < _IMPOSTAZIONI_OGNI_S:
        return
    _IMPOSTAZIONI_RILETTE["ts"] = adesso
    try:
        _low._refresh_settings(sb)
    finally:
        # il secondo si conta dalla FINE della lettura: un DB lento (o giu')
        # non viene riletto a raffica a ogni giro del worker
        _IMPOSTAZIONI_RILETTE["ts"] = time.monotonic()


def kill_switch_attivo() -> bool:
    """Freno d'emergenza: ``LIVE_KILL_SWITCH`` (env, riletto ora) oppure
    ``betfair_live_settings.kill_switch`` (ultimo snapshot DB)."""
    return bool(_low._kill_switch() or _low._db_kill_switch())


def is_riga_di_chiusura(action: Any, params: Any) -> bool:
    """La riga/il comando del desktop chiude (o riduce) una posizione? Stessa
    regola del calcio: cancel e greenup, oppure ``params.reduces_liability``."""
    return _low._is_closing_row(str(action or ""), params)


def ordine_riduce_il_rischio(flumine: Any, order: Any) -> bool:
    """True se il piazzamento NON aumenta la perdita worst-case della strategia
    sul mercato (e' un'uscita, un hedge, una copertura).

    ``reduces_liability`` nel context vale come dichiarazione (green-up del
    desktop). Altrimenti si confronta ``blotter.market_exposure`` prima e dopo
    il nuovo ordine (``trading.controls._market_loss``, matematica di flumine).
    FAIL-CLOSED: se non si riesce a calcolare, NON e' una chiusura (col freno
    tirato un ordine di cui non si sa niente non parte)."""
    ctx = getattr(order, "context", None)
    if isinstance(ctx, dict) and ctx.get("reduces_liability"):
        return True
    from ..trading.controls import _market_loss

    try:
        market = flumine.markets.markets.get(getattr(order, "market_id", None))
    except Exception:  # noqa: BLE001 - struttura inattesa: non e' una chiusura
        return False
    if market is None:
        return False
    blotter = getattr(market, "blotter", None)
    book = getattr(market, "market_book", None)
    trade = getattr(order, "trade", None)
    strategy = getattr(trade, "strategy", None) if trade is not None else None
    if blotter is None or book is None or strategy is None:
        return False
    prima = _market_loss(blotter, strategy, book)
    dopo = _market_loss(blotter, strategy, book, new_order=order)
    if prima is None or dopo is None:
        return False
    return dopo <= prima + 1e-9


class ControlloKillSwitchTennis(BaseControl):
    """Kill-switch DENTRO flumine per ogni piazzamento del runner tennis (bot e
    desktop): a freno tirato passano solo gli ordini che non aumentano il rischio."""

    NAME = "TENNIS_KILL_SWITCH"

    def _validate(self, order: Any, package_type: OrderPackageType) -> None:
        if package_type != OrderPackageType.PLACE:
            return
        if not kill_switch_attivo():
            return
        if ordine_riduce_il_rischio(self.flumine, order):
            return
        self._on_error(order, "kill-switch ATTIVO: apertura RIFIUTATA (passano solo le chiusure)")


# ===========================================================================
# T2 - guardia d'avvio del runner tennis
# ===========================================================================
GUARDIA_RUNNER = _aa.Guardia("runner_tennis")
RIPRESA_RIPROVA_S = 10.0
_RIPRESA_STATO: Dict[str, float] = {"ultimo": -1e18}
_RIPRESA_LOCK = threading.Lock()
# richieste della coda piu' vecchie di cosi', all'avvio, non si eseguono (come il calcio)
RIPRESA_ETA_MAX_S = 120.0
MOTIVO_GUARDIA_LOCALE = "runner tennis in ripresa: comando NON eseguito, riprova"


def arma_guardia_runner() -> None:
    """Chiamata una volta all'avvio del runner (PAPER/LIVE)."""
    GUARDIA_RUNNER.attiva = True
    GUARDIA_RUNNER.fatto = False
    GUARDIA_RUNNER.boot_id = _aa.boot_id_ambiente()
    _RIPRESA_STATO["ultimo"] = -1e18


def ripresa_all_avvio(db: Any = None) -> bool:
    """La ripresa del runner tennis. True = riuscita, guardia disarmata.

    1) bot di un avvio vecchio dell'app fermati (``ferma_bot_al_nuovo_avvio``,
       deve riuscire per intero: lettura E ogni scrittura);
    2) richieste della coda desktop piu' vecchie di 120 s chiuse in 'error'
       (mai un comando di prima del crash eseguito minuti dopo);
    3) specchio PAPER orfano chiuso (ordini simulati morti col processo: VOIDED;
       posizioni paper a zero). Le righe LIVE non si toccano MAI.
    Qualunque errore: la guardia resta armata e si riprova."""
    from . import tennis_bot_service as _svc
    from . import tennis_db as _tdb

    d = db if db is not None else _tdb
    try:
        _svc.ferma_bot_al_nuovo_avvio(db=d)
        if not _svc.ESITO_ULTIMO_FERMO.get("riuscito"):
            logger.error("[tennis-runner] ripresa: fermo dei bot di un avvio vecchio NON "
                         "riuscito: bot e coda FERMI (guardia d'avvio armata), riprovo")
            return False
        n_stale = d.fail_stale_pending_tennis_orders(RIPRESA_ETA_MAX_S)
        n_ord, n_pos = d.chiudi_specchio_paper_orfano()
    except Exception as ex:  # noqa: BLE001 - la guardia resta armata, si riprova
        logger.error("[tennis-runner] ripresa KO: bot e coda FERMI (guardia d'avvio "
                     "armata) finche' non riesce: %s", str(ex)[:200])
        return False
    GUARDIA_RUNNER.fatto = True
    logger.info("[tennis-runner] ripresa riuscita: %d richieste stantie chiuse, specchio "
                "paper orfano chiuso (%d ordini, %d posizioni). Guardia disarmata.",
                n_stale, n_ord, n_pos)
    return True


def guardia_blocca(db: Any = None) -> bool:
    """True se la guardia e' armata e la ripresa non e' riuscita. Riprova la
    ripresa al massimo ogni ``RIPRESA_RIPROVA_S`` secondi."""
    if not GUARDIA_RUNNER.blocca_aperture:
        return False
    # due worker (coda ordini e bot_control) la chiedono: UNA ripresa alla volta
    # (reperto M-5 del revisore B del 23/09 sul calcio: ripresa su due thread)
    if _RIPRESA_LOCK.acquire(blocking=False):
        try:
            adesso = time.monotonic()
            if adesso - _RIPRESA_STATO["ultimo"] >= RIPRESA_RIPROVA_S:
                _RIPRESA_STATO["ultimo"] = adesso
                ripresa_all_avvio(db)
        finally:
            _RIPRESA_LOCK.release()
    return GUARDIA_RUNNER.blocca_aperture


def azzera_per_i_test() -> None:
    """Stato di processo a nuovo (solo test)."""
    GUARDIA_RUNNER.azzera()
    _RIPRESA_STATO["ultimo"] = -1e18
    _IMPOSTAZIONI_RILETTE["ts"] = 0.0
