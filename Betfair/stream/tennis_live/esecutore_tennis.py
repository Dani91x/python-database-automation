"""esecutore_tennis.py - il MOTORE ORDINI nel runner tennis (F8, 25/09).

PRIMA: ``SAFE_TENNIS_ORDINI_VIA_CANALE`` doveva restare spenta. Il runner
tennis non montava il motore ordini (``/comando/safe_tennis`` sul 47332 riceveva
``motore_non_attivo``) e una partita non seguita non entrava nello stream per
un ordine di Safe tennis (``AUDIT_2026-09-25/TENNIS_AUTO_FOLLOW.md`` par. 4,
``STRADA_UNICA_BANCO_E_PAPER.md`` par. 5).

DOPO (tre pezzi, nessun processo nuovo):

1. ESECUTORE (questo modulo come modulo): lo STESSO ``motore_ordini.MotoreOrdini``
   del calcio (protocollo, dedup per ref, diario write-ahead, seq, da_seq,
   eventi ``order``, guardie da RAM, aggancio al volo) riceve questo modulo
   come ``esecutore`` al posto di ``live_order_worker``. Qui ci sono SOLO i
   nomi che il motore chiama, e ognuno porta al codice del runner tennis:
   ``_dispatch`` -> ``tennis_live_order_worker._dispatch`` VERO (place/cancel/
   replace/greenup, guardia dello stato del mercato D2, client della modalita'
   T1, controlli nativi di flumine tra cui ``ControlloKillSwitchTennis`` e
   ``ControlloModalitaBotTennis``, specchio ``_track_manual``); kill-switch e
   freschezza dei settings = le stesse funzioni che il worker tennis usa gia'
   (``guardie_tennis.kill_switch_attivo`` -> ``live_order_worker``); modo di
   processo = ``TENNIS_LIVE_ORDER_MODE``; ref interno ``awtq<id>`` dal contatore
   del canale tennis. Cio' che il runner tennis NON fa, il motore lo rifiuta
   dichiarandolo: place-and-trim sotto il minimo (``submin_non_percorribile``),
   azioni fuori dal worker tennis (``cashout_event``/``cashout_all``).
2. CANALE SOLO COMANDI (``CanaleSoloComandi``): il motore serve ``/comando/<attore>``;
   il ``/order`` del desktop resta al worker tennis come oggi (stesso percorso,
   stesse risposte): il motore non lo drena.
3. AGGANCIO A COMANDO (``AgganciaTennis``, interfaccia ``servibile``/``richiedi``
   come ``auto_follow.AutoFollow`` del calcio): un comando di Safe tennis su
   una partita non seguita e' ACCETTATO ``in_aggancio`` e parcheggiato dal motore
   (codice del motore, invariato); qui la partita entra nel piano
   dell'iscrizione a caldo con priorita' COMANDO (``iscrizione_a_caldo.
   PRI_COMANDO``), sulla stessa connessione, e il comando parte al primo book
   NUOVO del mercato. Tetto pieno senza niente di espellibile: rifiuto
   dichiarato ``tetto_mercati_pieno``; mercato che non arriva: evento
   ``rifiutato`` ``in_aggancio`` (motore). Mai in silenzio.

Interruttore: ``MOTORE_ORDINI_CANALE_TENNIS`` SPENTO di serie (``=1`` lo
accende). Spento: il runner tennis e' identico a prima (nessun thread, nessun
diario, ``/comando/`` rifiutato come oggi).
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Set

from .. import live_order_worker as _low
from .. import tempi_ordine as _TEMPI  # noqa: F401 - nome letto dal motore
from ..trading.submin import place_min_size
from . import iscrizione_a_caldo as _IAC
from . import tennis_db
from . import tennis_live_order_worker as _TW

logger = logging.getLogger(__name__)

ENV_INTERRUTTORE = "MOTORE_ORDINI_CANALE_TENNIS"
#: origine dei follow SINTETICI nati da un comando (mai scritti nel DB)
ORIGINE_COMANDO = "comando"
#: una partita agganciata da un comando resta seguita finche' un comando la usa
#: (poi esce, se senza posizioni, dopo la grazia dell'iscrizione a caldo)
COMANDO_TTL_DEFAULT_S = 900.0
#: un comando appena chiesto protegge la sua partita (ordine in volo o
#: parcheggiato: espellerla lo farebbe scadere). Come ``PROTEZIONE_COMANDO_S``.
PROTEZIONE_COMANDO_S = 10.0
#: prefisso di una partita chiesta prima di conoscerne l'event_id
PREFISSO_SOLO_MERCATO = "m:"


def acceso(env: Optional[Dict[str, str]] = None) -> bool:
    """``MOTORE_ORDINI_CANALE_TENNIS=1``: SPENTO di serie (lavoro nuovo)."""
    envd = os.environ if env is None else env
    return str(envd.get(ENV_INTERRUTTORE, "") or "").strip() == "1"


def comando_ttl_s() -> float:
    raw = (os.getenv("TENNIS_AGGANCIO_COMANDO_TTL_S") or "").strip()
    try:
        v = float(raw) if raw else COMANDO_TTL_DEFAULT_S
    except ValueError:
        v = COMANDO_TTL_DEFAULT_S
    return v if v > 0 else COMANDO_TTL_DEFAULT_S


# ===========================================================================
# 1. ESECUTORE: i nomi che ``motore_ordini.MotoreOrdini`` chiama (``LOW.*``)
# ===========================================================================
#: contesto PER THREAD, lucchetto ordini, righe e scrittura differita: gli
#: STESSI oggetti del calcio (il worker tennis legge lo stesso contesto per il
#: modo di processo, il customerStrategyRef e il diario, e prende lo stesso
#: lucchetto attorno al suo ``_dispatch``)
_CONTESTO = _low._CONTESTO
LUCCHETTO_ORDINI = _low.LUCCHETTO_ORDINI
_LOCAL_ROW_KEYS = _low._LOCAL_ROW_KEYS
_LocalSb = _low._LocalSb
_SbDifferito = _low._SbDifferito
_CLOSING_ACTIONS = _low._CLOSING_ACTIONS
_SUBMIN_POLL_SEC = _low._SUBMIN_POLL_SEC
_submin_timeout_sec = _low._submin_timeout_sec
_kill_switch = _low._kill_switch            # = guardie_tennis.kill_switch_attivo (env)
_db_kill_switch = _low._db_kill_switch      # snapshot riletto dal worker tennis
eta_settings_s = _low.eta_settings_s        # idem (``_refresh_settings``)
_tempi_on = _TW._tempi_on
CUSTOMER_STRATEGY_REF = _TW.CUSTOMER_STRATEGY_REF
#: stesso contatore del ``/order`` del canale tennis: ref ``awtq<id>`` mai doppi
_LOCAL_RID = _TW._LOCAL_SID
_cust_ref = _TW._cust_ref
_resolve_market = _TW._resolve_market
_jurisdiction = _TW._jurisdiction
#: azioni che il worker tennis sa eseguire (place/cancel/replace/greenup)
AZIONI_TENNIS = _TW._LOCAL_TENNIS_ACTIONS
MOTIVO_SUBMIN = ("submin_non_percorribile: il runner tennis non ha il place-and-trim "
                 "(sotto il minimo di giurisdizione un'apertura non parte: rifiuto "
                 "dichiarato, nessun ordine)")


def _modo_processo() -> str:
    """Capacita' del processo: ``TENNIS_LIVE_ORDER_MODE`` (o il modo forzato
    del banco sul thread), letta da ``tennis_live_order_worker._runner_mode``."""
    return _TW._runner_mode()


def _servable_modes(proc_mode: Optional[str] = None) -> tuple:
    return _low._servable_modes(proc_mode or _modo_processo())


def _client_for_mode(flumine: Any, row_mode: str, proc_mode: Optional[str] = None) -> Any:
    return _low._client_for_mode(flumine, row_mode, proc_mode or _modo_processo())


def _strategy_for_mode(session: Any, row_mode: str) -> Any:
    """Nel tennis gli ordini vivono sotto la capture della PARTITA (una sola
    per tutte le modalita': il client giusto lo sceglie ``_client_kw``). Il
    motore passa la sessione del runner: la si ritorna, dopo aver verificato
    la modalita'."""
    if str(row_mode or "").strip().lower() not in ("paper", "live"):
        raise ValueError(f"mode di riga sconosciuta: {row_mode!r}")
    if session is None:
        raise ValueError(f"strategy_assente per la modalita' '{row_mode}': riga NON eseguita")
    return session


def _blocco_apertura_modo(row_mode: Any, action: str, params: Any) -> Optional[str]:  # noqa: ARG001
    """Il runner tennis non ha il modo ordini dalla Control Room (il worker
    tennis non lo applica ne' alla coda ne' al ``/order``): stessa regola qui.
    Il tetto e' ``TENNIS_LIVE_ORDER_MODE`` (``_servable_modes``)."""
    return None


def _sub_minimum_floor(side: str) -> float:
    """Il minimo di PIAZZAMENTO per lato con la giurisdizione del tennis
    (``TENNIS_LIVE_JURISDICTION``), come ``live_order_worker._sub_minimum_floor``."""
    return float(place_min_size(_jurisdiction(), str(side).lower()))


def _read_matched_exposures(flumine: Any, market: Any, session: Any, selection_id: int,
                            handicap: float) -> "tuple[float, float]":
    """Esposizioni ABBINATE della capture del mercato (dove vivono gli ordini
    dei comandi e del desktop). Senza capture: (0, 0) = non verificabile."""
    del flumine
    strat = _TW._capture_strategy(session, getattr(market, "market_id", None))
    return _TW._read_matched_exposures(market, strat, int(selection_id), float(handicap or 0.0))


def _payload_da_riga(riga: Dict[str, Any], mode: str) -> Dict[str, Any]:
    p = {k: riga.get(k) for k in _LOCAL_ROW_KEYS}
    p["action"] = riga.get("action")
    p["mode"] = mode
    return p


def _dispatch(sb: Any, flumine: Any, riga: Dict[str, Any], mode: str, session: Any) -> None:
    """Esegue UN comando col ``_dispatch`` VERO del worker tennis. L'esito va
    nella riga catturata (``sb.captured``), come fa il calcio con ``_write_done``."""
    action = str(riga.get("action") or "")
    if action == "place_submin":
        raise ValueError(MOTIVO_SUBMIN)
    if action not in AZIONI_TENNIS:
        raise ValueError(f"azione_non_servibile: {action!r} non esiste nel runner tennis "
                         f"(ammesse: {', '.join(sorted(AZIONI_TENNIS))})")
    cmd = _TW.parse_order_payload({"payload": _payload_da_riga(riga, mode)})
    if action in ("cancel", "replace"):
        # mai cross-mode (regola del calcio ``_assert_order_mode``): una riga
        # 'paper' non tocca un ordine REALE e viceversa
        ordine = _TW._find_order_by_bet_id(flumine, cmd.get("market_id"), cmd.get("bet_id"))
        if ordine is not None:
            _low._assert_order_mode(ordine, mode, action)
    result = _TW._dispatch(flumine, session, cmd, _cust_ref(riga["id"]))
    sb.captured.update({"status": "done", "result": result, "bet_id": result.get("bet_id"),
                        "error": None})


def _write_error(sb: Any, rid: Any, riga: Dict[str, Any], mode: str, ex: Any) -> None:
    cmd = _payload_da_riga(riga, mode)
    sb.captured.update({
        "status": "error", "error": str(ex)[:300],
        "result": _TW._result(ok=False, action=str(riga.get("action") or ""), mode=mode,
                              cmd=cmd, cust_ref=_cust_ref(rid), error=str(ex)),
    })


def _journal_contesto(flumine: Any, riga: Dict[str, Any]) -> None:  # noqa: ARG001
    """Il trade journal E37 e' del calcio: il tennis non lo scrive (come oggi)."""
    return None


def _job_locale(differito: Any, riga: Dict[str, Any], captured: Dict[str, Any], mode_l: str,
                contesto: Any) -> Callable[[Any], None]:  # noqa: ARG001
    """Il lavoro DB di un comando, DOPO l'ordine (scrittore asincrono): la riga
    in ``tennis_live_order_queue`` come il ``/order`` del canale tennis
    (storico/audit). Lo specchio ``tennis_live_orders`` lo scrive il reconcile
    del worker tennis (``_track_manual`` -> ``_reconcile_tracked``)."""
    def _job(sb: Any) -> None:
        differito.rigioca(sb)
        payload = _payload_da_riga(riga, mode_l)
        comando = (riga.get("params") or {}).get("comando") if isinstance(
            riga.get("params"), dict) else None
        res = captured.get("result")
        sb.table("tennis_live_order_queue").insert({
            "client_ref": f"cmd{riga['id']}",
            "payload": {**payload, "comando": comando},
            "status": captured.get("status") or "done",
            "result": res,
            "error": captured.get("error"),
            "processed_at": tennis_db._now_iso(),
        }).execute()
    return _job


def imposta_drenaggio_esterno(attivo: bool) -> None:  # noqa: ARG001
    """Il ``/order`` del desktop resta al worker tennis (``CanaleSoloComandi``):
    niente da dichiarare."""
    return None


def _process_local_requests(*_a: Any, **_k: Any) -> None:
    raise RuntimeError("il /order del canale tennis lo serve il worker tennis, non il motore")


def _find_submin_order(*_a: Any, **_k: Any) -> None:
    raise RuntimeError(MOTIVO_SUBMIN)


def _advance_submin_row(*_a: Any, **_k: Any) -> None:
    raise RuntimeError(MOTIVO_SUBMIN)


# ===========================================================================
# 2. CANALE: il motore serve SOLO ``/comando/<attore>``
# ===========================================================================
class CanaleSoloComandi:
    """Il ``LocalChannel`` del 47332 visto dal motore: tutto passa, tranne le
    richieste ``/order`` del desktop, che restano al worker tennis (stessa
    strada di oggi, stesse risposte)."""

    def __init__(self, canale: Any) -> None:
        self._canale = canale

    def pop_requests(self, max_n: int = 20) -> list:  # noqa: ARG002
        return []

    def __getattr__(self, nome: str) -> Any:
        return getattr(self._canale, nome)


# ===========================================================================
# 3. AGGANCIO A COMANDO
# ===========================================================================
def follow_sintetico(event_id: str, voce: Dict[str, Any]) -> Dict[str, Any]:
    """La riga di follow (chiavi di ``tennis_live_follow``) di una partita chiesta
    da un comando: MAI scritta nel DB, vive solo nel piano del runner. Porta il
    catalogo gia' risolto (``_meta``): nessuna seconda chiamata REST."""
    return {"event_id": str(event_id), "market_id": voce.get("market_id"),
            "status": "STREAMING", "origine": ORIGINE_COMANDO,
            "_meta": voce.get("meta")}


def e_comando(follow: Optional[Dict[str, Any]]) -> bool:
    return str((follow or {}).get("origine") or "") == ORIGINE_COMANDO


def follows_con_comandi(session: Any, follows: Iterable[Dict[str, Any]],
                        ora: Optional[float] = None) -> List[Dict[str, Any]]:
    """I follow del DB + le partite dei comandi ancora vive (dentro il TTL).
    Un follow del DB vince sempre (stesso event_id: la riga vera)."""
    base = list(follows or [])
    comandi = getattr(session, "comandi", None)
    if not comandi:
        return base
    ora = time.monotonic() if ora is None else ora
    ttl = comando_ttl_s()
    presenti = {str(f.get("event_id") or "") for f in base}
    for ev, voce in list(comandi.items()):
        if ora - float(voce.get("ultimo_uso") or 0.0) > ttl:
            comandi.pop(ev, None)
            logger.info("[tennis-aggancio] %s: nessun comando da %.0f s, la partita "
                        "lascia il piano (esce dopo la grazia se senza posizioni)", ev, ttl)
            continue
        if str(ev) not in presenti:
            base.append(follow_sintetico(ev, voce))
    return base


def comando_recente(session: Any, event_id: str, ora: Optional[float] = None) -> bool:
    voce = (getattr(session, "comandi", None) or {}).get(str(event_id))
    if voce is None:
        return False
    ora = time.monotonic() if ora is None else ora
    return ora - float(voce.get("ultimo_uso") or 0.0) < PROTEZIONE_COMANDO_S


def meta_da_catalogo(voce: Any) -> Optional[Dict[str, Any]]:
    """Meta di ``tennis_runner._resolve_market`` gia' risolta (o None)."""
    return voce if isinstance(voce, dict) and voce.get("market_id") else None


class AgganciaTennis:
    """``servibile``/``richiedi`` per il motore (come ``AutoFollow`` del calcio).

    Stato in RAM sulla SESSIONE del runner (sopravvive alle ricostruzioni):
      * ``session.comandi``: event_id -> {market_id, meta, ultimo_uso, motivo};
      * ``session.attesa_libro``: market_id -> id() del book che flumine aveva
        quando la sottoscrizione e' partita (servibile solo con un book NUOVO:
        mai un libro stantio di prima). Lo scrive il runner DENTRO il ciclo di
        flumine, prima di sottoscrivere.

    Dipendenze iniettate (runner vero o banco):
      * ``risolvi(market_id)`` -> meta del catalogo (REST, fuori da ogni lock) o None;
      * ``allinea()`` -> porta lo stream al piano (runner: ``_allinea_follow_a_caldo``
        con i follow del DB + ``follows_con_comandi``);
      * ``manuali()`` -> event_id seguiti a mano (dall'ultima lettura dei follow);
      * ``posizioni(event_id)`` -> posizioni vive (blotter, RAM);
      * ``tetto()`` -> il tetto dei mercati.
    """

    def __init__(self, session: Any, *, risolvi: Callable[[str], Optional[Dict[str, Any]]],
                 allinea: Callable[[], Any],
                 manuali: Callable[[], Set[str]] = lambda: set(),
                 posizioni: Callable[[str], bool] = lambda _ev: False,
                 tetto: Callable[[], int] = _IAC.tetto_mercati,
                 orologio: Callable[[], float] = time.monotonic) -> None:
        self.session = session
        if not hasattr(session, "comandi") or session.comandi is None:
            session.comandi = {}
        if not hasattr(session, "attesa_libro") or session.attesa_libro is None:
            session.attesa_libro = {}
        self._risolvi = risolvi
        self._allinea = allinea
        self._manuali = manuali
        self._posizioni = posizioni
        self._tetto = tetto
        self._ora = orologio
        self._lock = threading.RLock()
        self._framework: Any = None
        #: market_id -> {ts, motivo}: chiesti, catalogo non ancora risolto
        self.richieste: Dict[str, Dict[str, Any]] = {}
        self._sveglia = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.conti = {"agganci_comando": 0, "rifiuti_tetto": 0, "catalogo_ko": 0,
                      "allineamenti": 0}
        self.ultimo_errore: Optional[str] = None

    # ------------------------------------------------------------ runner
    def aggancia(self, framework: Any) -> None:
        with self._lock:
            self._framework = framework
        self._sveglia.set()

    def sgancia(self) -> None:
        with self._lock:
            self._framework = None

    def avvia(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._ciclo, daemon=True,
                                        name="aggancio-comandi-tennis")
        self._thread.start()

    def ferma(self, timeout: float = 2.0) -> None:
        self._stop.set()
        self._sveglia.set()
        if self._thread is not None:
            self._thread.join(timeout)

    # ------------------------------------------------------------ motore
    def _mercati_seguiti(self) -> Dict[str, str]:
        """market_id -> event_id delle partite nello stream (``market_meta``)."""
        out: Dict[str, str] = {}
        for ev, meta in list((getattr(self.session, "market_meta", {}) or {}).items()):
            mid = (meta or {}).get("market_id")
            if mid:
                out[str(mid)] = str(ev)
        return out

    def _mercati_flumine(self) -> Dict[str, Any]:
        fw = self._framework
        try:
            d = fw.markets.markets if fw is not None else None
        except Exception:  # noqa: BLE001
            d = None
        return d if isinstance(d, dict) else {}

    def servibile(self, market_id: Optional[str]) -> bool:
        """Il mercato e' nello stream e flumine ne ha un book arrivato DOPO
        l'invio della sottoscrizione: il comando puo' partire."""
        mid = str(market_id or "")
        if not mid:
            return False
        with self._lock:
            if self._framework is None or mid not in self._mercati_seguiti():
                return False
            m = self._mercati_flumine().get(mid)
            if m is None:
                return False
            attesa = self.session.attesa_libro
            if mid in attesa:
                libro = getattr(m, "market_book", None)
                if libro is None or id(libro) == attesa[mid]:
                    return False
                attesa.pop(mid, None)
            return True

    def _usa(self, event_id: str, ora: float) -> None:
        voce = self.session.comandi.get(str(event_id))
        if voce is not None:
            voce["ultimo_uso"] = ora

    def richiedi(self, market_id: str, *, event_id: Optional[str] = None,
                 motivo: str = "comando") -> Optional[str]:
        """Chiesto dal motore (thread del motore, ZERO I/O): il mercato entra nel
        piano a priorita' COMANDO. None = preso in carico; stringa = rifiuto
        dichiarato (tetto pieno e niente di espellibile)."""
        del event_id
        mid = str(market_id)
        ora = self._ora()
        with self._lock:
            seguiti = self._mercati_seguiti()
            if mid in seguiti:
                self._usa(seguiti[mid], ora)
                self._sveglia.set()
                return None
            for ev, voce in list(self.session.comandi.items()):
                if str(voce.get("market_id")) == mid:
                    voce["ultimo_uso"] = ora
                    self._sveglia.set()
                    return None
            if mid in self.richieste:
                self.richieste[mid]["ts"] = ora
                self._sveglia.set()
                return None
            no = self._tetto_pieno(mid, ora, seguiti)
            if no is not None:
                self.conti["rifiuti_tetto"] += 1
                logger.warning("[tennis-aggancio] comando su %s NON agganciabile: %s", mid, no)
                return no
            self.richieste[mid] = {"ts": ora, "motivo": str(motivo)}
            self.conti["agganci_comando"] += 1
        logger.info("[tennis-aggancio] aggancio al volo di %s (%s)", mid, motivo)
        self._sveglia.set()
        return None

    def _tetto_pieno(self, mid: str, ora: float, seguiti: Dict[str, str]) -> Optional[str]:
        """Il piano dell'iscrizione a caldo (``pianifica``) con quello che il
        runner sa in RAM: entra se c'e' posto o se c'e' una partita di priorita'
        piu' bassa, senza posizioni e senza un comando recente."""
        tetto = int(self._tetto())
        try:
            manuali = {str(e) for e in (self._manuali() or set())}
        except Exception:  # noqa: BLE001 - nel dubbio: tutte a mano (mai espulse)
            manuali = set(seguiti.values())
        armate = {str(ev) for (ev, _bk), st in list(
            (getattr(self.session, "hosted", {}) or {}).items())
            if not getattr(st, "_tennis_disabled", False)}
        occupati: List[_IAC.Evento] = []
        for ev in seguiti.values():
            try:
                pos = bool(self._posizioni(ev))
            except Exception:  # noqa: BLE001 - nel dubbio: protetta
                pos = True
            occupati.append(_IAC.Evento(
                ev, manuale=ev in manuali and ev not in self.session.comandi,
                armata=ev in armate, comando=ev in self.session.comandi,
                posizioni=pos or comando_recente(self.session, ev, ora)))
        # comandi gia' chiesti ma non ancora nello stream: occupano (protetti)
        for altro in list(self.richieste):
            occupati.append(_IAC.Evento(PREFISSO_SOLO_MERCATO + altro, comando=True,
                                        posizioni=True))
        for ev, voce in list(self.session.comandi.items()):
            if str(voce.get("market_id")) not in seguiti:
                occupati.append(_IAC.Evento(ev, comando=True, posizioni=True))
        nuovo = _IAC.Evento(PREFISSO_SOLO_MERCATO + mid, comando=True)
        voluti = [_IAC.Evento(e.event_id, e.manuale, e.armata, e.posizioni,
                              comando=e.comando) for e in occupati] + [nuovo]
        piano = _IAC.pianifica(occupati, voluti, tetto)
        if nuovo.event_id in piano.rifiutati:
            return (f"tetto di {tetto} mercati pieno sulla connessione del runner tennis "
                    f"(limite Betfair {_IAC.LIMITE_BETFAIR_MERCATI}) e nessuna partita "
                    f"espellibile (posizioni vive, a mano o comandi in corso)")
        return None

    # ------------------------------------------------------------ il giro
    def _ciclo(self) -> None:
        while not self._stop.is_set():
            self._sveglia.wait(timeout=1.0)
            self._sveglia.clear()
            if self._stop.is_set():
                return
            try:
                self.giro()
            except Exception:  # noqa: BLE001 - l'aggancio non muore mai
                logger.exception("[tennis-aggancio] giro KO")

    def giro(self) -> bool:
        """Catalogo dei mercati chiesti (REST, fuori da ogni lock) -> partite
        del piano -> ``allinea``. True se ha chiesto un allineamento."""
        with self._lock:
            chiesti = dict(self.richieste)
        nuovi = 0
        for mid, info in chiesti.items():
            try:
                meta = self._risolvi(mid)
            except Exception as ex:  # noqa: BLE001
                meta = None
                self.ultimo_errore = str(ex)[:200]
            with self._lock:
                self.richieste.pop(mid, None)
                if meta is None or not meta.get("market_id"):
                    self.conti["catalogo_ko"] += 1
                    logger.warning("[tennis-aggancio] %s: catalogo non risolto (il comando "
                                   "scade in_aggancio, il bot ripete la decisione)", mid)
                    continue
                ev = str(meta.get("event_id") or (PREFISSO_SOLO_MERCATO + mid))
                self.session.comandi[ev] = {"market_id": str(meta["market_id"]),
                                            "meta": meta, "ultimo_uso": self._ora(),
                                            "motivo": info.get("motivo")}
                nuovi += 1
        if not nuovi:
            return False
        self.conti["allineamenti"] += 1
        try:
            self._allinea()
        except Exception as ex:  # noqa: BLE001 - si riprova al giro dopo
            self.ultimo_errore = str(ex)[:200]
            logger.warning("[tennis-aggancio] allineamento KO (si riprova): %s", ex)
            self._sveglia.set()
        return True

    def stato(self) -> Dict[str, Any]:
        return {"acceso": True, "comandi": len(self.session.comandi),
                "richieste": len(self.richieste), "conti": dict(self.conti),
                "ultimo_errore": self.ultimo_errore}


def costruisci_motore(canale: Any, *, cartella_diario: str, guardia_armata: Callable[[], bool],
                      motivo_guardia_order: str, aggancio: Optional[AgganciaTennis]) -> Any:
    """Il ``MotoreOrdini`` del calcio con l'esecutore tennis: attori, protocollo,
    diario (``DATA_DIR/_diario_ordini`` del tennis), scrittore asincrono sul
    client DB tennis. Non avvia niente."""
    import sys

    from .. import motore_ordini as MO

    return MO.MotoreOrdini(
        "tennis", canale=CanaleSoloComandi(canale), diario=MO.Diario(cartella_diario),
        scrittore=MO.ScrittoreAsincrono(sb_factory=tennis_db.get_tennis_client,
                                        nome="scrittore-db-tennis"),
        guardia_armata=guardia_armata, motivo_guardia_order=motivo_guardia_order,
        aggancio=aggancio, esecutore=sys.modules[__name__])
