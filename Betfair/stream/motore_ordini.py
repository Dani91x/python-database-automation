"""motore_ordini.py - MOTORE ORDINI del runner (strada unica verso Betfair).

Decisione dell'utente (24/09/2026): la strada UNICA verso gli ordini reali e' il
runner dello sport con flumine nello stesso processo; desktop e bot ci arrivano
dal canale locale; il DB e' solo diario e ripiego del trasporto. Questo modulo e'
l'esecutore di quella strada, parametrizzato per sport (oggi montato dal runner
calcio; il tennis lo monta dopo con il suo esecutore).

Tre pezzi (AUDIT_STRADE_ORDINE_2026-09-24, par. 4.2-4.3):

F2 SVUOTAMENTO A EVENTO. Un thread dedicato ("motore-ordini-<sport>") dorme su un
   ``threading.Event``; il canale lo sveglia a ogni comando messo in coda
   (``LocalChannel.set_su_comando``). Niente sonno da 1,0 s del BackgroundWorker
   nel percorso dell'ordine. Il giro periodico della coda DB resta com'era (e'
   il ripiego, e aggiorna i settings in RAM). Fra ricezione e ``_dispatch`` non
   c'e' IO DB: kill-switch e limiti si leggono dalla copia in RAM dei settings,
   con eta' dichiarata; troppo vecchia -> rifiuto delle aperture, mai una lettura
   sincrona.
F1 DIARIO write-ahead. PRIMA di qualunque chiamata a Betfair (o al client paper)
   una riga append-only in ``_diario_ordini/<AAAA-MM-GG>.jsonl`` con flush e
   fsync: il comando (``inviato``) e, subito prima di ogni ``market.place_order``,
   l'ordine con il ``customer_order_ref`` di flumine (``ordine``). Dopo, la riga
   ``esito``. Il DB (audit, riga di coda, journal, specchio) lo scrive uno
   SCRITTORE ASINCRONO (thread suo, coda in RAM, tentativi), mai il percorso
   dell'ordine ne' il thread principale di flumine. All'avvio il diario del
   giorno si rilegge: comandi ``inviato`` senza esito -> ``listCurrentOrders``
   per ref PRIMA di disarmare la guardia d'avvio.
F3 PROTOCOLLO «comando ordine» su ``/comando/<attore>`` (ack immediato, rifiuti
   con motivo, dedup per ref che sopravvive al riavvio, eventi ``order`` con la
   riga dello specchio + ref/seq/fase/esito_ms, ``seq`` per attore, ``da_seq``
   con memoria degli ultimi 500). Il ``/order`` del desktop di sempre e' servito
   dallo STESSO motore con le stesse regole e le stesse risposte.

Le guardie sono quelle del worker (``live_order_worker``): ``_dispatch`` (mode per
comando, client per modalita'), ``_kill_switch``/``_db_kill_switch`` con
``_CLOSING_ACTIONS``, guardia d'avvio (solo ``cancel``, come B-1), controlli
nativi di flumine, place-and-trim, dedup, audit, specchio. Nessuna e' copiata qui.

ESTENSIONE DEL PROTOCOLLO (coordinatore, 24/09, dal referto della porta di Safe):
  * ``time_in_force``: "FILL_OR_KILL" | null sul ``place`` (build_order lo valida
    con la persistenza come per la coda DB; non abbinato -> l'evento ``order``
    porta la fase "scaduto"/"annullato" con size_matched 0, mai un residuo);
  * ``reduces_liability``: bool del COMANDO (mai dai params: tolto sempre). Di
    serie passa come oggi (build_order consente la size sotto il minimo); con
    kill-switch, guardia d'avvio o settings stantie scavalca SOLO se il runner lo
    verifica sulle esposizioni abbinate del blotter, altrimenti rifiuto
    ``reduces_liability_non_verificabile``;
  * sotto il minimo di Betfair senza ``reduces_liability``: oggi rifiuto
    ``submin_non_percorribile`` (il place-and-trim dal canale e' il punto di
    ripresa 1 di STATO_RIPRESA.md);
  * ``customerOrderRef`` = ref del comando: NON fattibile senza rompere il
    riconoscimento degli ordini di flumine (vedi STATO_RIPRESA.md, punto 2); il
    diario lega ogni ref al customerOrderRef VERO inviato (riga ``ordine``);
  * dedup: ack con ``accettato`` e ``seq`` della prima risposta e motivo
    ``MOTIVO_REF_GIA_VISTO``; un solo contatore ``seq`` per attore per ack ed
    eventi ``order``.

MONEY-CRITICAL. Fail-closed: nel dubbio il comando e' RIFIUTATO con il motivo,
mai eseguito "per sicurezza".
"""
from __future__ import annotations

import collections
import json
import logging
import math
import os
import queue
import threading
import time
from datetime import datetime
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

from . import live_order_worker as LOW

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Contratto del protocollo (scritto dal coordinatore: non cambiarlo in silenzio)
# ---------------------------------------------------------------------------
ATTORI_COMANDO = frozenset({
    "desktop", "safe", "omega", "mike", "safe_tennis",
    "tennis_scalper", "tennis_pro", "tennis_flb", "tennis_swing",
})
AZIONI_COMANDO = frozenset({"place", "cancel", "replace", "greenup",
                            "cashout_event", "cashout_all"})
MAX_REF = 32
MEMORIA_EVENTI = 500
MAX_ETA_DEFAULT_MS = 3000
FUTURO_TOLLERATO_MS = 1000       # creato_ms oltre l'arrivo: orologio impossibile
MAX_ETA_SETTINGS_S_DEFAULT = 10.0

# Motivi di rifiuto (prefisso stabile, dettaglio dopo i due punti).
M_TOKEN = "token_mancante_o_errato"
M_ATTORE = "attore_non_ammesso"
M_PARAM = "parametri_invalidi"
M_ETA = "comando_scaduto"
M_AGGANCIO = "runner_non_agganciato"
M_MODE = "mode_non_servibile"
M_GUARDIA = "guardia_avvio"
M_KILL = "kill_switch"
M_SETTINGS = "settings_stantie"
M_DIARIO = "diario_non_scrivibile"
M_RIDUZIONE = "reduces_liability_non_verificabile"
M_SUBMIN = "submin_non_percorribile"
# Estensione del coordinatore (24/09): ack a un ref gia' visto = ``accettato`` e
# ``seq`` della PRIMA risposta, motivo questa costante.
MOTIVO_REF_GIA_VISTO = "ref_gia_visto"

# Fasi degli eventi ``order``.
# 24/09 (estensione 3, place-and-trim): passi della macchina -> fase dell'evento.
# ``parcheggiato`` = minimo a quota non abbinabile, ``ridotto`` = trim alla size
# chiesta, poi l'ordine e' alla quota target (``accettato_betfair``); le fasi di
# abbinamento arrivano dallo specchio come per ogni ordine. Ogni evento del
# place-and-trim porta anche ``submin_step`` (passo esatto della macchina).
FASE_SUBMIN = {"placed": "parcheggiato", "trimmed": "ridotto",
               "repriced": "accettato_betfair", "done": "accettato_betfair"}
FASI = ("inviato", "parcheggiato", "ridotto", "accettato_betfair", "rifiutato",
        "abbinato_parziale",
        "abbinato", "annullato", "scaduto", "errore")

# Chiavi della riga dello specchio ``betfair_live_orders`` (LiveTradingStrategy
# ._order_row + ``updated_at`` di db.upsert_live_order): un evento nato da un
# esito del motore (rifiuto, errore, invio) porta le STESSE chiavi.
CHIAVI_SPECCHIO = (
    "bet_id", "client_order_ref", "request_id", "mode", "event_id", "market_id",
    "selection_id", "handicap", "side", "order_type", "price", "size",
    "size_matched", "size_remaining", "size_cancelled", "size_lapsed",
    "size_voided", "average_price_matched", "status", "persistence",
    "placed_at", "matched_at", "updated_at",
)
_CHIAVI_ZERO = ("handicap", "size_matched", "size_remaining", "size_cancelled",
                "size_lapsed", "size_voided", "average_price_matched")


class Rifiuto(Exception):
    """Un comando che non si esegue: ``codice`` stabile + dettaglio."""

    def __init__(self, codice: str, dettaglio: str = "") -> None:
        super().__init__(f"{codice}: {dettaglio}" if dettaglio else codice)
        self.codice = codice


def _ora_ms() -> int:
    return int(time.time() * 1000)


def _ora_iso() -> str:
    return datetime.now().astimezone().isoformat()


# ---------------------------------------------------------------------------
# F1 - Diario write-ahead (JSONL append-only, una cartella, un file al giorno)
# ---------------------------------------------------------------------------
class Diario:
    """Diario append-only del motore. ``scrivi`` ritorna solo quando la riga e'
    sul disco (flush + fsync se ``durevole``): se solleva, il chiamante NON deve
    mandare l'ordine. Thread-safe (un lucchetto)."""

    def __init__(self, cartella: str, *, giorno: Optional[Callable[[], str]] = None) -> None:
        self.cartella = cartella
        self._giorno = giorno or (lambda: datetime.now().strftime("%Y-%m-%d"))
        self._lock = threading.Lock()
        self._fh: Any = None
        self._fh_giorno: Optional[str] = None

    def percorso(self, giorno: Optional[str] = None) -> str:
        return os.path.join(self.cartella, f"{giorno or self._giorno()}.jsonl")

    def scrivi(self, record: Dict[str, Any], *, durevole: bool = True) -> None:
        riga = json.dumps(record, default=str, separators=(",", ":"), ensure_ascii=True)
        with self._lock:
            giorno = self._giorno()
            if self._fh is None or self._fh_giorno != giorno:
                self._chiudi()
                os.makedirs(self.cartella, exist_ok=True)
                self._fh = open(self.percorso(giorno), "a", encoding="ascii", newline="\n")
                self._fh_giorno = giorno
            try:
                self._fh.write(riga + "\n")
                self._fh.flush()
                if durevole:
                    os.fsync(self._fh.fileno())
            except Exception:
                # handle in stato ignoto: si riapre al prossimo giro
                self._chiudi()
                raise

    def _chiudi(self) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            except Exception:  # noqa: BLE001
                pass
        self._fh = None
        self._fh_giorno = None

    def chiudi(self) -> None:
        with self._lock:
            self._chiudi()

    def leggi(self, giorni: List[str]) -> List[Dict[str, Any]]:
        """Righe dei giorni indicati (in ordine). Una riga troncata (crash a meta'
        scrittura) si salta e si DICE, mai un'eccezione alla ripresa."""
        out: List[Dict[str, Any]] = []
        for g in giorni:
            p = self.percorso(g)
            if not os.path.exists(p):
                continue
            with open(p, "r", encoding="ascii", errors="replace") as fh:
                for n, riga in enumerate(fh, 1):
                    riga = riga.strip()
                    if not riga:
                        continue
                    try:
                        rec = json.loads(riga)
                    except Exception:  # noqa: BLE001
                        logger.warning("[motore] diario %s riga %d illeggibile: saltata", p, n)
                        continue
                    if isinstance(rec, dict):
                        out.append(rec)
        return out


# ---------------------------------------------------------------------------
# F1 - Scrittore asincrono (DB fuori dal percorso dell'ordine)
# ---------------------------------------------------------------------------
class ScrittoreAsincrono:
    """Un thread, una coda FIFO in RAM, tentativi con attesa crescente.

    ``accoda(descrizione, job, tentativi)``: ``job(sb)`` riceve il client DB del
    thread dello scrittore. L'ordine FIFO conserva la sequenza delle scritture
    dello stesso oggetto (upsert dello specchio). Coda piena -> il lavoro si
    SCARTA con log ERROR e conteggio (il diario su disco ha comunque i comandi).
    """

    def __init__(self, *, sb_factory: Optional[Callable[[], Any]] = None,
                 max_coda: int = 20000,
                 attese: Tuple[float, ...] = (0.2, 0.5, 1.0, 2.0, 5.0),
                 dormi: Callable[[float], None] = time.sleep,
                 nome: str = "scrittore-db") -> None:
        self._sb_factory = sb_factory
        self._coda: "queue.Queue[Any]" = queue.Queue(maxsize=max_coda)
        self._attese = attese
        self._dormi = dormi
        self._nome = nome
        self._sb: Any = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.thread_ident: Optional[int] = None
        self.conti = {"accodati": 0, "eseguiti": 0, "falliti": 0, "scartati": 0}

    def avvia(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._giro, daemon=True, name=self._nome)
        self._thread.start()

    def ferma(self, timeout: float = 2.0) -> None:
        self._stop.set()
        try:
            self._coda.put_nowait(None)
        except queue.Full:
            pass
        if self._thread is not None:
            self._thread.join(timeout)

    def accoda(self, descrizione: str, job: Callable[[Any], None], tentativi: int = 1) -> bool:
        try:
            self._coda.put_nowait((descrizione, job, max(1, int(tentativi))))
        except queue.Full:
            self.conti["scartati"] += 1
            logger.error("[motore] scrittore DB: coda PIENA, scartato '%s' (il diario su "
                         "disco resta la fonte)", descrizione)
            return False
        self.conti["accodati"] += 1
        return True

    def svuota(self, timeout: float = 5.0) -> bool:
        """Attende che la coda sia vuota e il lavoro in corso finito (test/uscita)."""
        fine = time.monotonic() + timeout
        while time.monotonic() < fine:
            if self._coda.unfinished_tasks == 0:
                return True
            time.sleep(0.005)
        return self._coda.unfinished_tasks == 0

    def _client(self) -> Any:
        if self._sb is None:
            if self._sb_factory is not None:
                self._sb = self._sb_factory()
            else:
                from db_client import get_supabase_client
                self._sb = get_supabase_client()
        return self._sb

    def _giro(self) -> None:
        self.thread_ident = threading.get_ident()
        while True:
            item = self._coda.get()
            try:
                if item is None:
                    if self._stop.is_set():
                        return
                    continue
                descrizione, job, tentativi = item
                for i in range(tentativi):
                    try:
                        job(self._client())
                        self.conti["eseguiti"] += 1
                        break
                    except Exception as ex:  # noqa: BLE001 - mai far morire lo scrittore
                        if i + 1 >= tentativi:
                            self.conti["falliti"] += 1
                            logger.error("[motore] scrittura DB '%s' FALLITA dopo %d "
                                         "tentativi: %s", descrizione, tentativi, str(ex)[:200])
                        else:
                            self._dormi(self._attese[min(i, len(self._attese) - 1)])
            finally:
                self._coda.task_done()


# ---------------------------------------------------------------------------
# Funzioni pure del protocollo
# ---------------------------------------------------------------------------
def _num(v: Any, nome: str, *, minimo: Optional[float] = None, maggiore: bool = True,
         obbligatorio: bool = True) -> Optional[float]:
    if v is None:
        if obbligatorio:
            raise Rifiuto(M_PARAM, f"{nome} mancante")
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise Rifiuto(M_PARAM, f"{nome} non numerico: {v!r}")
    f = float(v)
    if not math.isfinite(f):
        raise Rifiuto(M_PARAM, f"{nome} non finito")
    if minimo is not None and ((f <= minimo) if maggiore else (f < minimo)):
        raise Rifiuto(M_PARAM, f"{nome} fuori campo: {v!r}")
    return f


def _intero(v: Any, nome: str, obbligatorio: bool = True) -> Optional[int]:
    if v is None:
        if obbligatorio:
            raise Rifiuto(M_PARAM, f"{nome} mancante")
        return None
    if isinstance(v, bool) or not isinstance(v, int):
        raise Rifiuto(M_PARAM, f"{nome} non intero: {v!r}")
    return int(v)


def _testo(v: Any, nome: str, obbligatorio: bool = True) -> Optional[str]:
    if v is None or v == "":
        if obbligatorio:
            raise Rifiuto(M_PARAM, f"{nome} mancante")
        return None
    if not isinstance(v, str):
        raise Rifiuto(M_PARAM, f"{nome} non testo: {v!r}")
    return v


def valida_comando(attore: str, d: Dict[str, Any]) -> Dict[str, Any]:
    """Valida il ``d`` di un comando e ritorna il PIANO: riga per ``_dispatch``
    (chiavi della coda), azione, mode, strategy_ref, creato_ms, max_eta_ms.
    Solleva ``Rifiuto(M_PARAM, ...)``. Nessun default "comodo" sui soldi:
    lato, prezzo, size e mode sono obbligatori dove servono."""
    if d.get("attore") != attore:
        raise Rifiuto(M_PARAM, f"attore del messaggio {d.get('attore')!r} diverso dal "
                               f"percorso {attore!r}")
    azione = d.get("azione")
    if azione not in AZIONI_COMANDO:
        raise Rifiuto(M_PARAM, f"azione non ammessa: {azione!r}")
    mode = d.get("mode")
    if mode not in ("paper", "live"):
        raise Rifiuto(M_PARAM, f"mode non ammessa: {mode!r}")
    strategy_ref = d.get("strategy_ref")
    if strategy_ref is None:
        strategy_ref = attore
    if strategy_ref != attore:
        raise Rifiuto(M_PARAM, f"strategy_ref {strategy_ref!r} diverso dall'attore "
                               f"{attore!r}")
    creato_ms = _intero(d.get("creato_ms"), "creato_ms")
    max_eta_ms = _intero(d.get("max_eta_ms"), "max_eta_ms", obbligatorio=False)
    if max_eta_ms is None:
        max_eta_ms = MAX_ETA_DEFAULT_MS
    if max_eta_ms <= 0:
        raise Rifiuto(M_PARAM, f"max_eta_ms deve essere > 0: {max_eta_ms}")
    market_id = _testo(d.get("market_id"), "market_id")
    params = d.get("params")
    if params is not None and not isinstance(params, dict):
        raise Rifiuto(M_PARAM, "params deve essere un oggetto")
    origine = d.get("origine")
    if origine is not None and not isinstance(origine, dict):
        raise Rifiuto(M_PARAM, "origine deve essere un oggetto {tabella, id}")
    handicap = _num(d.get("handicap"), "handicap", obbligatorio=False) or 0.0

    riga: Dict[str, Any] = {k: None for k in LOW._LOCAL_ROW_KEYS}
    riga.update({"market_id": market_id, "handicap": handicap, "order_type": "LIMIT"})
    if azione == "place":
        riga["selection_id"] = _intero(d.get("selection_id"), "selection_id")
        lato = d.get("side")
        if lato not in ("BACK", "LAY"):
            raise Rifiuto(M_PARAM, f"side non ammesso: {lato!r}")
        riga["side"] = lato
        riga["price"] = _num(d.get("price"), "price", minimo=1.0)
        riga["size"] = _num(d.get("size"), "size", minimo=0.0)
        pers = d.get("persistence") or "LAPSE"
        if pers not in ("LAPSE", "PERSIST"):
            raise Rifiuto(M_PARAM, f"persistence non ammessa: {pers!r}")
        riga["persistence"] = pers
        # estensione 24/09 (1): FILL_OR_KILL per ordine (null = ordine normale).
        # build_order lo valida con la persistenza, come per la coda DB.
        tif = d.get("time_in_force")
        if tif not in (None, "FILL_OR_KILL"):
            raise Rifiuto(M_PARAM, f"time_in_force non ammesso: {tif!r}")
        riga["time_in_force"] = tif
    elif azione in ("cancel", "replace"):
        riga["bet_id"] = _testo(d.get("bet_id"), "bet_id")
        if azione == "cancel":
            riga["size_reduction"] = _num(d.get("size_reduction"), "size_reduction",
                                          minimo=0.0, obbligatorio=False)
        else:
            riga["new_price"] = _num(d.get("new_price"), "new_price", minimo=1.0)
    elif azione == "greenup":
        riga["selection_id"] = _intero(d.get("selection_id"), "selection_id")
    # estensione 24/09 (2): ``reduces_liability`` e' una chiave del COMANDO, mai
    # dei params: un ``params.reduces_liability`` messo dall'attore farebbe
    # passare un'apertura col kill-switch senza verifica -> tolto sempre.
    riduce = d.get("reduces_liability", False)
    if not isinstance(riduce, bool):
        raise Rifiuto(M_PARAM, f"reduces_liability non booleano: {riduce!r}")
    if riduce and azione != "place":
        raise Rifiuto(M_PARAM, "reduces_liability vale solo per 'place'")
    p = dict(params or {})
    p.pop("reduces_liability", None)
    if riduce:
        p["reduces_liability"] = True
    p["comando"] = {"ref": d.get("ref"), "attore": attore, "origine": origine}
    riga["params"] = p
    return {"riga": riga, "azione": azione, "mode": mode, "strategy_ref": strategy_ref,
            "creato_ms": creato_ms, "max_eta_ms": max_eta_ms, "riduce": riduce}


def riduce_esposizione(win: float, lose: float, side: str, price: float,
                       size: float) -> bool:
    """True se il place porta la posizione ABBINATA verso il piatto: c'e' una
    posizione, il caso peggiore non peggiora e la distanza fra i due esiti non
    cresce. ``win``/``lose`` = profitto se la selezione vince/perde (blotter)."""
    eps = 1e-9
    if side == "BACK":
        nw, nl = win + size * (price - 1.0), lose - size
    else:
        nw, nl = win - size * (price - 1.0), lose + size
    if min(win, lose) >= -eps and abs(win - lose) <= eps:
        return False            # posizione piatta: niente da ridurre
    return min(nw, nl) >= min(win, lose) - eps and abs(nw - nl) <= abs(win - lose) + eps


def fase_da_riga(riga: Dict[str, Any]) -> str:
    """Fase del protocollo da una riga dello specchio (stato flumine + numeri)."""
    st = str(riga.get("status") or "").upper()
    sm = float(riga.get("size_matched") or 0.0)
    if st == "VIOLATION":
        return "rifiutato"
    if st in ("EXPIRED", "LAPSED"):
        return "scaduto"
    if st == "EXECUTION_COMPLETE":
        if float(riga.get("size_cancelled") or 0.0) > 0:
            return "annullato"
        if float(riga.get("size_lapsed") or 0.0) > 0 and sm <= 0:
            return "scaduto"
        if float(riga.get("size_lapsed") or 0.0) > 0:
            return "annullato"
        return "abbinato" if sm > 0 else "annullato"
    if st == "EXECUTABLE":
        if sm > 0:
            return "abbinato_parziale"
        return "accettato_betfair" if riga.get("bet_id") else "inviato"
    return "inviato"


def riga_specchio_da_esito(result: Dict[str, Any], *, cust_ref: str, rid: int,
                           mode: str, riga: Dict[str, Any]) -> Dict[str, Any]:
    """Riga con le STESSE chiavi dello specchio, costruita dall'esito del
    dispatch (per gli eventi che precedono o sostituiscono lo specchio)."""
    out: Dict[str, Any] = {k: None for k in CHIAVI_SPECCHIO}
    res = result or {}
    side = res.get("side") or riga.get("side")
    out.update({
        "bet_id": res.get("bet_id"),
        "client_order_ref": cust_ref,
        "request_id": rid,
        "mode": mode,
        "market_id": res.get("market_id") or riga.get("market_id"),
        "selection_id": res.get("selection_id") if res.get("selection_id") is not None
        else riga.get("selection_id"),
        "handicap": riga.get("handicap"),
        "side": side.lower() if isinstance(side, str) else side,
        "order_type": "LIMIT",
        "price": res.get("price") if res.get("price") is not None else riga.get("price"),
        "size": res.get("size") if res.get("size") is not None else riga.get("size"),
        "size_matched": res.get("size_matched"),
        "size_remaining": res.get("size_remaining"),
        "average_price_matched": res.get("average_price_matched"),
        "status": res.get("status"),
        "persistence": riga.get("persistence"),
        "updated_at": _ora_iso(),
    })
    for k in _CHIAVI_ZERO:
        if out[k] is None:
            out[k] = 0.0
    return out


# ---------------------------------------------------------------------------
# Il motore
# ---------------------------------------------------------------------------
class MotoreOrdini:
    """Esecutore ordini di UNO sport dentro il runner. Vedi il docstring del modulo."""

    def __init__(self, sport: str, *, canale: Any, diario: Diario,
                 scrittore: ScrittoreAsincrono,
                 guardia_armata: Callable[[], bool] = lambda: False,
                 motivo_guardia_order: str = "runner in ripresa: comando NON eseguito, riprova",
                 orologio_ms: Callable[[], int] = _ora_ms,
                 max_eta_settings_s: Optional[float] = None,
                 attori: frozenset = ATTORI_COMANDO,
                 modo_processo: Optional[str] = None,
                 blocco_modo: Optional[Callable[..., Optional[str]]] = None,
                 eta_settings: Optional[Callable[[], float]] = None) -> None:
        self.sport = sport
        # 24/09 (banco F4): nel replay il processo e' PAPER per costruzione e non
        # c'e' ne' DB ne' Control Room: ``modo_processo`` vale sul thread durante
        # controlli e dispatch (``LOW._CONTESTO.modo_processo``), ``blocco_modo``
        # e ``eta_settings`` sostituiscono le letture dei settings. In produzione
        # restano None = funzioni del worker (nessun comportamento diverso).
        self._modo_processo_forzato = modo_processo
        self._blocco_modo = blocco_modo or LOW._blocco_apertura_modo
        self._eta_settings = eta_settings or LOW.eta_settings_s
        # place-and-trim in corso: ref interno awlq<rid> -> stato in RAM
        self._submin: Dict[str, Dict[str, Any]] = {}
        self.canale = canale
        self.diario = diario
        self.scrittore = scrittore
        self._guardia_armata = guardia_armata
        self._motivo_guardia_order = motivo_guardia_order
        self._ora_ms = orologio_ms
        if max_eta_settings_s is None:
            try:
                max_eta_settings_s = float(os.getenv("MOTORE_ORDINI_MAX_ETA_SETTINGS_S", "")
                                           or MAX_ETA_SETTINGS_S_DEFAULT)
            except ValueError:
                max_eta_settings_s = MAX_ETA_SETTINGS_S_DEFAULT
        self.max_eta_settings_s = float(max_eta_settings_s)
        self._attori = attori
        self._flumine: Any = None
        self._strategie: Any = None
        self._evento = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.thread_ident: Optional[int] = None
        # dedup per ref: ref -> ack (identico alla prima risposta)
        self._visti: Dict[str, Dict[str, Any]] = {}
        # seq per attore + memoria degli ultimi MEMORIA_EVENTI messaggi
        # RLock: l'emissione degli eventi trattenuti avviene sotto lo stesso
        # lucchetto che assegna il seq (ordine degli eventi = ordine dei seq).
        self._lock_seq = threading.RLock()
        self._base_seq = int(time.time() * 1000)
        self._seq: Dict[str, int] = {}
        self._memoria: Dict[str, Deque[Dict[str, Any]]] = {}
        # ref interno flumine awlq<rid> -> {attore, ref, mode, pronto, trattenuti}
        # per gli eventi. Finche' il motore non ha emesso l'esito del dispatch
        # (``pronto`` False) le righe dello specchio si TRATTENGONO: l'attore
        # vede sempre prima "inviato/rifiutato" e poi le fasi di Betfair.
        self._rif_interni: Dict[str, Dict[str, Any]] = {}
        self._rif_ordine: Deque[str] = collections.deque()
        # ref del comando in esecuzione (per le righe ``ordine`` del diario)
        self._ref_corrente: Optional[str] = None
        self.conti = {"comandi": 0, "accettati": 0, "rifiutati": 0, "order": 0}

    # ------------------------------------------------------------ ciclo di vita
    def avvia(self) -> None:
        """Carica il dedup dal diario, collega canale/specchio/worker, avvia il thread."""
        self._carica_visti()
        self.scrittore.avvia()
        from . import db as dbm

        dbm.imposta_scrittore(self.scrittore)
        dbm.aggiungi_osservatore_ordini(self._su_riga_specchio)
        LOW.imposta_drenaggio_esterno(True)
        if self.canale is not None:
            self.canale.set_su_comando(self.sveglia)
        self._stop.clear()
        self._thread = threading.Thread(target=self._ciclo, daemon=True,
                                        name=f"motore-ordini-{self.sport}")
        self._thread.start()

    def ferma(self, timeout: float = 2.0) -> None:
        from . import db as dbm

        if self.canale is not None:
            self.canale.set_su_comando(None)
        LOW.imposta_drenaggio_esterno(False)
        dbm.rimuovi_osservatore_ordini(self._su_riga_specchio)
        dbm.imposta_scrittore(None)
        self._stop.set()
        self._evento.set()
        if self._thread is not None:
            self._thread.join(timeout)
        self.scrittore.ferma()
        self.diario.chiudi()

    def aggancia(self, flumine: Any, strategie: Any) -> None:
        """Il framework corrente (ricostruito a ogni ripartenza dello stream)."""
        self._flumine = flumine
        self._strategie = strategie
        self.sveglia()

    def sgancia(self) -> None:
        self._flumine = None
        self._strategie = None

    @property
    def agganciato(self) -> bool:
        return self._flumine is not None

    def sveglia(self) -> None:
        self._evento.set()

    def _ciclo(self) -> None:
        self.thread_ident = threading.get_ident()
        while not self._stop.is_set():
            # timeout di sicurezza: se una sveglia andasse persa, il comando
            # aspetta al massimo questo (mai il secondo del worker). Con un
            # place-and-trim in corso il giro e' al passo della macchina
            # (``_SUBMIN_POLL_SEC``): si avanza in RAM, mai un sonno sincrono.
            attesa = LOW._SUBMIN_POLL_SEC if self._submin else 0.5
            self._evento.wait(timeout=attesa)
            self._evento.clear()
            if self._stop.is_set():
                return
            try:
                self.drena()
            except Exception:  # noqa: BLE001 - il motore non muore per un comando
                logger.exception("[motore] giro KO")
            try:
                self.avanza_submin()
            except Exception:  # noqa: BLE001
                logger.exception("[motore] avanzamento place-and-trim KO")

    def drena(self, max_giri: int = 20) -> int:
        """Serve tutto cio' che e' in coda sul canale. Ritorna i messaggi gestiti."""
        ch = self.canale
        if ch is None:
            return 0
        n = 0
        for _ in range(max_giri):
            comandi = ch.pop_comandi()
            for c in comandi:
                n += 1
                try:
                    self._gestisci(c)
                except Exception:  # noqa: BLE001 - mai lasciare il motore giu'
                    logger.exception("[motore] comando KO")
            reqs = ch.pop_requests()
            if reqs:
                n += len(reqs)
                try:
                    self._servi_order(reqs)
                except Exception as ex:  # noqa: BLE001
                    logger.exception("[motore] /order KO")
                    for r in reqs:
                        try:
                            ch.respond(r, False, error=f"comando NON eseguito: {str(ex)[:120]}")
                        except Exception:  # noqa: BLE001
                            pass
            if not comandi and not reqs:
                break
        return n

    # --------------------------------------------------------------- /comando
    def _prossimo_seq(self, attore: str) -> int:
        with self._lock_seq:
            s = self._seq.get(attore, self._base_seq) + 1
            self._seq[attore] = s
            return s

    def _memorizza_e_invia(self, attore: str, msg: Dict[str, Any], ws: Any = None) -> None:
        with self._lock_seq:
            mem = self._memoria.get(attore)
            if mem is None:
                mem = collections.deque(maxlen=MEMORIA_EVENTI)
                self._memoria[attore] = mem
            mem.append(msg)
        if self.canale is None:
            return
        if ws is not None:
            self.canale.invia(ws, msg)
        else:
            self.canale.invia_attore(attore, msg)

    def _ack(self, ref: Optional[str], seq: Optional[int], accettato: bool,
             motivo: Optional[str], ricevuto_ms: int) -> Dict[str, Any]:
        return {"ref": ref, "seq": seq, "accettato": bool(accettato),
                "motivo": motivo, "ricevuto_ms": ricevuto_ms}

    def _rifiuto_non_registrato(self, c: Any, ref: Optional[str], motivo: str) -> None:
        """Rifiuto senza seq e senza dedup: chi non e' autenticato (o non ha un
        ref valido) non consuma numeri di sequenza e non "prenota" ref altrui."""
        self.conti["rifiutati"] += 1
        if self.canale is not None:
            self.canale.invia(c.ws, {"t": "ack", "d": self._ack(ref, None, False, motivo,
                                                                 c.ricevuto_ms)})

    def _gestisci(self, c: Any) -> None:
        self.conti["comandi"] += 1
        d = c.d if isinstance(c.d, dict) else {}
        ref = d.get("ref") if isinstance(d.get("ref"), str) else None
        if not c.token_ok:
            self._rifiuto_non_registrato(c, ref, f"{M_TOKEN}: header X-Canale-Token assente "
                                                 f"o diverso da quello del canale")
            return
        if c.attore not in self._attori:
            self._rifiuto_non_registrato(c, ref, f"{M_ATTORE}: {c.attore!r}")
            return
        if c.tipo == "da_seq":
            self._rispondi_da_seq(c, d)
            return
        prefisso = f"{c.attore}-"
        if (ref is None or len(ref) > MAX_REF or not ref.startswith(prefisso)
                or len(ref) == len(prefisso)):
            self._rifiuto_non_registrato(c, ref, f"{M_PARAM}: ref deve essere "
                                                 f"'{prefisso}<id>' di al massimo {MAX_REF} "
                                                 f"caratteri")
            return
        prima = self._visti.get(ref)
        if prima is not None:
            # DEDUP: stesso ref = stessa richiesta, mai un secondo invio. Ack
            # con ``accettato`` e ``seq`` della prima risposta, motivo
            # MOTIVO_REF_GIA_VISTO (estensione 24/09, punto 5).
            if self.canale is not None:
                self.canale.invia(c.ws, {"t": "ack", "d": dict(
                    prima, motivo=MOTIVO_REF_GIA_VISTO)})
            return
        self._imposta_contesto(None, None)   # modo di processo forzato (banco) o env
        try:
            piano = valida_comando(c.attore, d)
            self._controlla(piano, c.ricevuto_ms)
        except Rifiuto as r:
            self._rifiuta_registrato(c, ref, str(r))
            return
        finally:
            self._pulisci_contesto()
        seq = self._prossimo_seq(c.attore)
        ack = self._ack(ref, seq, True, None, c.ricevuto_ms)
        riga = piano["riga"]
        riga["id"] = next(LOW._LOCAL_RID)
        riga["action"] = piano["azione"]
        riga["mode"] = piano["mode"]
        try:
            self.diario.scrivi({
                "tipo": "inviato", "canale": "comando", "ref": ref, "attore": c.attore,
                "azione": piano["azione"], "mode": piano["mode"], "seq": seq,
                "rid": riga["id"], "ref_interno": LOW._cust_ref(riga["id"]),
                "strategy_ref": piano["strategy_ref"], "parametri": d,
                "ts_ms": self._ora_ms(), "ack": ack,
            })
        except Exception as ex:  # noqa: BLE001 - fail-closed: senza diario niente ordine
            logger.error("[motore] diario NON scrivibile, comando %s RIFIUTATO: %s", ref, ex)
            ack = self._ack(ref, seq, False, f"{M_DIARIO}: {str(ex)[:160]}", c.ricevuto_ms)
            self._visti[ref] = ack
            self.conti["rifiutati"] += 1
            self._memorizza_e_invia(c.attore, {"t": "ack", "d": ack}, ws=c.ws)
            return
        self._visti[ref] = ack
        self.conti["accettati"] += 1
        self._memorizza_e_invia(c.attore, {"t": "ack", "d": ack}, ws=c.ws)
        self._esegui(c.attore, ref, piano)

    def _rifiuta_registrato(self, c: Any, ref: str, motivo: str) -> None:
        seq = self._prossimo_seq(c.attore)
        ack = self._ack(ref, seq, False, motivo, c.ricevuto_ms)
        self._visti[ref] = ack
        self.conti["rifiutati"] += 1
        try:
            # nessuna chiamata a Betfair: flush senza fsync basta (dedup al riavvio)
            self.diario.scrivi({"tipo": "rifiuto", "ref": ref, "attore": c.attore,
                                "ts_ms": self._ora_ms(), "ack": ack}, durevole=False)
        except Exception as ex:  # noqa: BLE001 - il rifiuto resta rifiuto
            logger.warning("[motore] diario del rifiuto %s non scritto: %s", ref, ex)
        self._memorizza_e_invia(c.attore, {"t": "ack", "d": ack}, ws=c.ws)

    def _controlla(self, piano: Dict[str, Any], ricevuto_ms: int) -> None:
        """Le guardie del runner, TUTTE da RAM (zero IO). Ordine: eta', aggancio,
        modalita' servibile, guardia d'avvio, kill-switch, freschezza settings."""
        eta = ricevuto_ms - int(piano["creato_ms"])
        if eta > int(piano["max_eta_ms"]):
            raise Rifiuto(M_ETA, f"eta' {eta} ms > max_eta_ms {piano['max_eta_ms']}")
        if -eta > FUTURO_TOLLERATO_MS:
            raise Rifiuto(M_ETA, f"creato_ms {-eta} ms nel futuro: orologio incoerente")
        flumine = self._flumine
        if flumine is None:
            raise Rifiuto(M_AGGANCIO, "nessun framework flumine attivo (runner fermo, "
                                      "senza partite o in ripartenza)")
        mode = piano["mode"]
        # capacita' del processo (tetto .env): quali client esistono. Il modo
        # EFFETTIVO scelto dalla UI governa le aperture (_blocco_apertura_modo).
        proc = LOW._modo_processo()
        if mode not in LOW._servable_modes(proc):
            raise Rifiuto(M_MODE, f"mode '{mode}' non servibile dal runner in {proc}")
        try:
            LOW._client_for_mode(flumine, mode, proc)
            LOW._strategy_for_mode(self._strategie, mode)
        except ValueError as ex:
            raise Rifiuto(M_MODE, str(ex)[:200]) from ex
        azione = piano["azione"]
        riga = piano["riga"]
        riduce = bool(piano.get("riduce"))
        # Un place che si DICHIARA chiusura scavalca guardia/kill-switch/settings
        # SOLO se il runner lo verifica sulle esposizioni abbinate del blotter
        # (estensione 24/09, punto 2). La verifica e' in RAM: zero IO.
        verificata: Optional[bool] = None

        def _verifica() -> bool:
            nonlocal verificata
            if verificata is None:
                verificata = self._riduzione_verificata(flumine, riga, mode)
            return verificata

        if self._guardia_armata() and azione != "cancel":
            if not riduce:
                raise Rifiuto(M_GUARDIA, "ripresa d'avvio non ancora riuscita: passa solo "
                                         "'cancel' (o una chiusura verificata)")
            if not _verifica():
                raise Rifiuto(M_RIDUZIONE, "guardia d'avvio armata e riduzione non "
                                           "verificabile sulle esposizioni del runner")
        chiusura = azione in LOW._CLOSING_ACTIONS or (riduce and _verifica())
        # 24/09 (fusione con master): modo EFFETTIVO dalla Control Room sulle
        # APERTURE, PRIMA del kill-switch. Una riduzione dichiarata conta come
        # chiusura SOLO se verificata: i params passati sono quelli verificati.
        blocco = self._blocco_modo(
            mode, azione, {"reduces_liability": True} if chiusura else {})
        if blocco:
            raise Rifiuto(M_MODE, blocco)
        if LOW._kill_switch() or LOW._db_kill_switch():
            if not chiusura:
                if riduce:
                    raise Rifiuto(M_RIDUZIONE, "kill-switch ATTIVO e riduzione non "
                                               "verificabile sulle esposizioni del runner")
                raise Rifiuto(M_KILL, "kill-switch ATTIVO: solo chiusure permesse")
        if not chiusura:
            eta_s = self._eta_settings()
            if eta_s > self.max_eta_settings_s:
                raise Rifiuto(M_SETTINGS, f"copia dei settings vecchia di {eta_s:.1f} s "
                                          f"(> {self.max_eta_settings_s:.1f} s): kill-switch "
                                          f"e limiti del DB non verificabili")
        if azione == "place" and not riduce:
            # estensione 24/09 (3), decisione dell'utente: sotto il minimo di
            # Betfair il motore usa la STESSA macchina place-and-trim del worker
            # (``_start_submin`` + ``_advance_submin_row``), in paper E in live
            # (paper = stessa macchina sul client simulato). Qui SOLO la verifica
            # di percorribilita' (``start_submin``, pura): se la macchina non puo'
            # partire -> rifiuto ``submin_non_percorribile`` col motivo suo.
            try:
                minimo = float(LOW._sub_minimum_floor(str(riga["side"]).lower()))
            except Exception:  # noqa: BLE001 - minimo ignoto: fail-closed
                raise Rifiuto(M_SUBMIN, "minimo di giurisdizione non determinabile")
            if float(riga["size"]) < minimo - 1e-9:
                if riga.get("time_in_force") == "FILL_OR_KILL":
                    raise Rifiuto(M_SUBMIN, "FILL_OR_KILL sotto il minimo: il "
                                            "place-and-trim parcheggia l'ordine, non "
                                            "puo' essere un fill-or-kill")
                from .trading.submin import start_submin
                try:
                    start_submin(side=str(riga["side"]).lower(),
                                 target_price=float(riga["price"]),
                                 target_size=float(riga["size"]),
                                 jurisdiction=LOW._jurisdiction())  # come _start_submin
                except ValueError as ex:
                    raise Rifiuto(M_SUBMIN, str(ex)[:200]) from ex
                piano["submin"] = True

    def _riduzione_verificata(self, flumine: Any, riga: Dict[str, Any], mode: str) -> bool:
        """Il place riduce DAVVERO la posizione abbinata del runner? Legge le
        esposizioni dal blotter di flumine (``_read_matched_exposures``, le
        stesse dello specchio posizioni). Qualunque dubbio -> False."""
        try:
            market = LOW._resolve_market(flumine, riga.get("market_id"))
            strat = LOW._strategy_for_mode(self._strategie, mode)
            win, lose = LOW._read_matched_exposures(
                flumine, market, strat, int(riga["selection_id"]),
                float(riga.get("handicap") or 0.0))
            return riduce_esposizione(float(win), float(lose), str(riga["side"]),
                                      float(riga["price"]), float(riga["size"]))
        except Exception:  # noqa: BLE001 - non verificabile = non verificata
            return False

    def _pre_invio(self, ref: Optional[str]) -> Callable[..., None]:
        """Hook del diario chiamato dal worker SUBITO PRIMA di ogni place."""
        def _hook(order: Any, market: Any, what: str, info: Optional[Dict[str, Any]]) -> None:
            rec: Dict[str, Any] = {"tipo": "ordine", "ref": ref, "cosa": what,
                                   "ts_ms": self._ora_ms()}
            if order is not None:
                ot = getattr(order, "order_type", None)
                ctx = getattr(order, "context", None)
                rec.update({
                    "cor": getattr(order, "customer_order_ref", None),
                    "ref_interno": ctx.get("customer_order_ref") if isinstance(ctx, dict)
                    else None,
                    "market_id": getattr(market, "market_id", None),
                    "selection_id": getattr(order, "selection_id", None),
                    "side": getattr(order, "side", None),
                    "price": getattr(ot, "price", None),
                    "size": getattr(ot, "size", None),
                })
            else:
                rec.update({"market_id": getattr(market, "market_id", None), **(info or {})})
            self.diario.scrivi(rec)
        return _hook

    def _esegui(self, attore: str, ref: str, piano: Dict[str, Any]) -> None:
        riga = piano["riga"]
        mode = piano["mode"]
        rid = riga["id"]
        cust = LOW._cust_ref(rid)
        with self._lock_seq:
            self._rif_interni[cust] = {"attore": attore, "ref": ref, "mode": mode,
                                       "pronto": False, "trattenuti": []}
            self._rif_ordine.append(cust)
            while len(self._rif_ordine) > 5000:
                self._rif_interni.pop(self._rif_ordine.popleft(), None)
        differito = LOW._SbDifferito()
        lsb = LOW._LocalSb(differito)
        ok, errore = True, None
        submin = bool(piano.get("submin"))
        if submin:
            # la STESSA macchina del worker: azione place_submin (step INIT->PLACED
            # qui, gli step successivi da ``avanza_submin`` a ogni giro)
            riga["action"] = "place_submin"
        self._imposta_contesto(piano["strategy_ref"], self._pre_invio(ref))
        try:
            with LOW.LUCCHETTO_ORDINI:
                LOW._dispatch(lsb, self._flumine, riga, mode, self._strategie)
        except Exception as ex:  # noqa: BLE001 - esito del comando, motore vivo
            ok, errore = False, str(ex)
            try:
                LOW._write_error(lsb, rid, riga, mode, ex)
            except Exception as ex_w:  # noqa: BLE001
                logger.error("[motore] esito error di %s non catturato: %s", ref, ex_w)
        finally:
            self._pulisci_contesto()
        result = lsb.captured.get("result") or {"ok": ok, "action": riga["action"],
                                                "mode": mode, "error": errore}
        if ok and submin:
            self._avvia_submin(attore, ref, piano, cust, differito, lsb, result)
            return
        try:
            self.diario.scrivi({"tipo": "esito", "ref": ref, "ok": ok, "errore": errore,
                                "risultato": result, "ts_ms": self._ora_ms()})
        except Exception as ex:  # noqa: BLE001 - l'ordine e' gia' partito: si DICE
            logger.critical("[motore] esito di %s NON scritto nel diario: %s (alla ripresa "
                            "sara' riletto da Betfair)", ref, ex)
        if ok:
            fase = "inviato"
        else:
            fase = "errore" if str(errore or "").startswith("post_place:") else "rifiutato"
        with self._lock_seq:
            self._emetti(attore, ref, riga_specchio_da_esito(result, cust_ref=cust, rid=rid,
                                                             mode=mode, riga=riga), fase)
            info = self._rif_interni.get(cust)
            if info is not None:
                info["pronto"] = True
                trattenuti, info["trattenuti"] = info["trattenuti"], []
                for payload in trattenuti:
                    self._emetti(attore, ref, payload, fase_da_riga(payload))
        contesto = None
        if ok:
            try:
                contesto = LOW._journal_contesto(self._flumine, riga)
            except Exception:  # noqa: BLE001 - journal best-effort
                logger.warning("[motore] contesto journal di %s non catturato", ref)
        self.scrittore.accoda(f"comando {ref}", LOW._job_locale(
            differito, riga, dict(lsb.captured), mode, contesto))

    # --------------------------------------------------- contesto sul thread
    def _imposta_contesto(self, strategy_ref: Optional[str], pre_invio: Any) -> None:
        LOW._CONTESTO.strategy_ref = strategy_ref
        LOW._CONTESTO.pre_invio = pre_invio
        LOW._CONTESTO.modo_processo = self._modo_processo_forzato

    @staticmethod
    def _pulisci_contesto() -> None:
        LOW._CONTESTO.strategy_ref = None
        LOW._CONTESTO.pre_invio = None
        LOW._CONTESTO.modo_processo = None

    # ------------------------------------------- place-and-trim (estensione 3)
    def _avvia_submin(self, attore: str, ref: str, piano: Dict[str, Any], cust: str,
                      differito: Any, lsb: Any, result: Dict[str, Any]) -> None:
        """Il gradino 1 (park al minimo) e' partito: la sequenza si registra in
        RAM e avanza a ogni giro del motore (``avanza_submin``). Le righe dello
        specchio restano TRATTENUTE finche' la sequenza non e' terminale: il
        park a quota non abbinabile non e' la posizione che l'attore ha chiesto."""
        riga = piano["riga"]
        stato = {"attore": attore, "ref": ref, "mode": piano["mode"], "riga": riga,
                 "differito": differito, "captured": lsb.captured,
                 "strategy_ref": piano["strategy_ref"], "t0": time.monotonic(),
                 "step": None}
        self._submin[cust] = stato
        with self._lock_seq:
            self._emetti(attore, ref, riga_specchio_da_esito(
                result, cust_ref=cust, rid=riga["id"], mode=piano["mode"], riga=riga),
                "inviato", extra={"submin_step": result.get("submin_step")})
        self._dopo_passo_submin(cust)

    def avanza_submin(self) -> int:
        """UN passo per ogni place-and-trim in corso (``_advance_submin_row`` del
        worker, ``allow_place=False``: mai un secondo place). Nessun sonno."""
        n = 0
        for cust in list(self._submin):
            s = self._submin.get(cust)
            if s is None or self._flumine is None:
                continue
            n += 1
            riga = s["riga"]
            mode = s["mode"]
            lsb = LOW._LocalSb(s["differito"])
            lsb.captured = s["captured"]
            if time.monotonic() - s["t0"] > LOW._submin_timeout_sec():
                self._abbandona_submin(cust, lsb, "timeout della sequenza place-and-trim")
                continue
            riga_corrente = dict(riga)
            riga_corrente["result"] = s["captured"].get("result")
            self._imposta_contesto(s["strategy_ref"], self._pre_invio(s["ref"]))
            try:
                with LOW.LUCCHETTO_ORDINI:
                    LOW._advance_submin_row(
                        lsb, self._flumine, riga_corrente, mode,
                        LOW._strategy_for_mode(self._strategie, mode),
                        client=LOW._client_for_mode(self._flumine, mode))
            except Exception as ex:  # noqa: BLE001 - come il worker: riga in errore
                try:
                    LOW._write_error(lsb, riga["id"], riga, mode, ex)
                except Exception:  # noqa: BLE001
                    pass
                self._chiudi_submin(cust, False, str(ex))
                continue
            finally:
                self._pulisci_contesto()
            self._dopo_passo_submin(cust)
        return n

    def _dopo_passo_submin(self, cust: str) -> None:
        s = self._submin.get(cust)
        if s is None:
            return
        result = s["captured"].get("result") or {}
        step = result.get("submin_step")
        if step != s["step"]:
            s["step"] = step
            fase = FASE_SUBMIN.get(str(step))
            if fase is not None and fase != s.get("fase"):
                s["fase"] = fase
                with self._lock_seq:
                    self._emetti(s["attore"], s["ref"], riga_specchio_da_esito(
                        result, cust_ref=cust, rid=s["riga"]["id"], mode=s["mode"],
                        riga=s["riga"]), fase, extra={"submin_step": step})
        if step == "done":
            self._chiudi_submin(cust, True, None)
        elif step == "aborted":
            self._chiudi_submin(cust, False, result.get("error") or result.get("detail"))

    def _abbandona_submin(self, cust: str, lsb: Any, motivo: str) -> None:
        """Timeout: il residuo si RITIRA (mai un parcheggio lasciato a mercato
        senza dirlo), poi errore esplicito."""
        s = self._submin[cust]
        result = s["captured"].get("result") or {}
        try:
            ordine = LOW._find_submin_order(
                self._flumine, s["riga"].get("market_id"), result.get("submin_order_id"),
                result.get("bet_id"), cust_ref=cust)
            if ordine is not None:
                with LOW.LUCCHETTO_ORDINI:
                    LOW._resolve_market(self._flumine, s["riga"].get("market_id")) \
                        .cancel_order(ordine)
        except Exception:  # noqa: BLE001 - ritiro best-effort, l'errore si dice sotto
            logger.exception("[motore] place-and-trim %s: ritiro del residuo KO", s["ref"])
        try:
            LOW._write_error(lsb, s["riga"]["id"], s["riga"], s["mode"], ValueError(motivo))
        except Exception:  # noqa: BLE001
            pass
        self._chiudi_submin(cust, False, motivo)

    def _chiudi_submin(self, cust: str, ok: bool, errore: Optional[str]) -> None:
        s = self._submin.pop(cust, None)
        if s is None:
            return
        result = s["captured"].get("result") or {}
        try:
            self.diario.scrivi({"tipo": "esito", "ref": s["ref"], "ok": ok, "errore": errore,
                                "risultato": result, "ts_ms": self._ora_ms()})
        except Exception as ex:  # noqa: BLE001
            logger.critical("[motore] esito place-and-trim %s NON scritto nel diario: %s",
                            s["ref"], ex)
        with self._lock_seq:
            if not ok:
                self._emetti(s["attore"], s["ref"], riga_specchio_da_esito(
                    result, cust_ref=cust, rid=s["riga"]["id"], mode=s["mode"],
                    riga=s["riga"]), "errore",
                    extra={"submin_step": result.get("submin_step"), "errore": errore})
            info = self._rif_interni.get(cust)
            if info is not None:
                info["pronto"] = True
                trattenuti, info["trattenuti"] = info["trattenuti"], []
                if trattenuti:
                    # SOLO l'ultima riga: lo stato attuale dell'ordine su Betfair
                    ultima = trattenuti[-1]
                    self._emetti(s["attore"], s["ref"], ultima, fase_da_riga(ultima))
        contesto = None
        if ok:
            try:
                contesto = LOW._journal_contesto(self._flumine, s["riga"])
            except Exception:  # noqa: BLE001
                contesto = None
        self.scrittore.accoda(f"comando {s['ref']}", LOW._job_locale(
            s["differito"], s["riga"], dict(s["captured"]), s["mode"], contesto))

    def _emetti(self, attore: str, ref: str, riga: Dict[str, Any], fase: str,
                extra: Optional[Dict[str, Any]] = None) -> None:
        d = dict(riga)
        if extra:
            d.update(extra)
        d.update({"ref": ref, "seq": self._prossimo_seq(attore), "fase": fase,
                  "esito_ms": self._ora_ms()})
        self.conti["order"] += 1
        self._memorizza_e_invia(attore, {"t": "order", "d": d})

    def _su_riga_specchio(self, payload: Dict[str, Any]) -> None:
        """Osservatore dello specchio (thread PRINCIPALE di flumine): SOLO un
        lookup in RAM e un invio. Righe non nate da un comando: ignorate."""
        cor = payload.get("client_order_ref")
        if not isinstance(cor, str) or not cor.startswith("awlq") or len(cor) < 14:
            return
        with self._lock_seq:
            info = self._rif_interni.get(cor[:14])
            if info is None or payload.get("mode") != info["mode"]:
                return
            if not info["pronto"]:
                info["trattenuti"].append(dict(payload))
                return
            self._emetti(info["attore"], info["ref"], payload, fase_da_riga(payload))

    def _rispondi_da_seq(self, c: Any, d: Dict[str, Any]) -> None:
        dal = d.get("seq")
        if isinstance(dal, bool) or not isinstance(dal, int):
            self._rifiuto_non_registrato(c, None, f"{M_PARAM}: da_seq richiede seq intero")
            return
        with self._lock_seq:
            mem = list(self._memoria.get(c.attore) or [])
            ultimo = self._seq.get(c.attore, self._base_seq)
        mancanti = [m for m in mem if int(m["d"].get("seq") or 0) > dal]
        primo = int(mem[0]["d"]["seq"]) if mem else ultimo + 1
        completo = dal >= primo - 1
        if self.canale is None:
            return
        for m in mancanti:
            self.canale.invia(c.ws, m)
        self.canale.invia(c.ws, {"t": "da_seq", "d": {
            "dal": dal, "fino_a": ultimo, "inviati": len(mancanti), "completo": completo}})

    # ----------------------------------------------------------------- /order
    def _servi_order(self, reqs: List[Any]) -> None:
        """Il ``/order`` del desktop di sempre, stesse regole e stesse risposte
        di ``_process_local_requests``; in piu': diario write-ahead e IO DB
        differito. Guardia armata -> come B-1 (solo ``cancel``)."""
        ch = self.canale
        if self._guardia_armata():
            annulli = []
            for r in reqs:
                p = r.params if isinstance(r.params, dict) else {}
                if r.method == "order" and str(p.get("action") or "") == "cancel":
                    annulli.append(r)
                else:
                    ch.respond(r, False, error=self._motivo_guardia_order)
            reqs = annulli
            if not reqs:
                return
        if self._flumine is None:
            for r in reqs:
                ch.respond(r, False, error="runner senza framework attivo (nessuna partita "
                                           "agganciata o ripartenza in corso): comando NON "
                                           "eseguito")
            return
        # capacita' del processo, come ``_process_once``/``esegui_richieste_locali_
        # scelte`` su master: il modo effettivo lo applica per comando
        # ``_blocco_apertura_modo`` dentro ``_process_local_requests``.
        mode = (self._modo_processo_forzato or LOW._modo_processo()).upper()
        if mode not in ("PAPER", "LIVE"):
            for r in reqs:
                ch.respond(r, False, error="modalita' ordini OFF: comando NON eseguito")
            return
        self._imposta_contesto(None, self._pre_invio_order())
        try:
            LOW._process_local_requests(None, self._flumine, mode.lower(), self._strategie,
                                        reqs=list(reqs), differisci=self._differisci,
                                        diario=self)
        finally:
            self._pulisci_contesto()
            self._ref_corrente = None

    def _differisci(self, descrizione: str, job: Callable[[Any], None]) -> None:
        self.scrittore.accoda(descrizione, job)

    def _pre_invio_order(self) -> Callable[..., None]:
        def _hook(order: Any, market: Any, what: str, info: Optional[Dict[str, Any]]) -> None:
            self._pre_invio(self._ref_corrente)(order, market, what, info)
        return _hook

    # interfaccia ``diario`` di _process_local_requests
    def inviato(self, row: Dict[str, Any], cmd: Dict[str, Any]) -> None:
        cref = cmd.get("client_ref")
        ref = f"order-{cref}" if cref else f"order-local{row['id']}"
        self._ref_corrente = ref
        self.diario.scrivi({
            "tipo": "inviato", "canale": "order", "ref": ref, "attore": "desktop",
            "azione": row.get("action"), "mode": row.get("mode"), "seq": None,
            "rid": row["id"], "ref_interno": LOW._cust_ref(row["id"]),
            "strategy_ref": LOW.CUSTOMER_STRATEGY_REF, "parametri": cmd,
            "ts_ms": self._ora_ms(),
        })

    def esito(self, row: Dict[str, Any], ok: bool, result: Any, errore: Optional[str]) -> None:
        try:
            self.diario.scrivi({"tipo": "esito", "ref": self._ref_corrente, "ok": ok,
                                "errore": errore, "risultato": result,
                                "ts_ms": self._ora_ms()})
        except Exception as ex:  # noqa: BLE001 - ordine gia' partito: si DICE
            logger.critical("[motore] esito /order %s NON scritto nel diario: %s",
                            self._ref_corrente, ex)

    # ------------------------------------------------------- ripresa all'avvio
    def _giorni_diario(self) -> List[str]:
        oggi = datetime.now()
        from datetime import timedelta

        return [(oggi - timedelta(days=1)).strftime("%Y-%m-%d"), oggi.strftime("%Y-%m-%d")]

    def _carica_visti(self) -> None:
        """Dedup che sopravvive al riavvio: gli ack gia' dati (accettati e
        rifiutati) tornano identici per lo stesso ref."""
        try:
            for rec in self.diario.leggi(self._giorni_diario()):
                if rec.get("tipo") in ("inviato", "rifiuto") and isinstance(rec.get("ack"), dict):
                    ref = rec.get("ref")
                    if isinstance(ref, str) and ref not in self._visti:
                        self._visti[ref] = rec["ack"]
        except Exception as ex:  # noqa: BLE001 - il dedup in RAM resta
            logger.error("[motore] diario illeggibile all'avvio (dedup solo in RAM): %s", ex)

    def riprendi_da_diario(self, lista_ordini: Optional[Callable[[List[str]], Any]]) -> bool:
        """Comandi ``inviato`` senza esito nel diario (crash in volo): per quelli
        LIVE si rilegge Betfair (``listCurrentOrders`` per customerOrderRef) e si
        scrive la riga ``ripresa``. True = ripresa completa (la guardia puo'
        disarmarsi); False = Betfair non raggiungibile: guardia ARMATA."""
        try:
            recs = self.diario.leggi(self._giorni_diario())
        except Exception as ex:  # noqa: BLE001
            logger.error("[motore] ripresa: diario illeggibile: %s", ex)
            return False
        inviati: Dict[str, Dict[str, Any]] = {}
        chiusi = set()
        cor_per_ref: Dict[str, List[str]] = {}
        for rec in recs:
            ref = rec.get("ref")
            if not isinstance(ref, str):
                continue
            tipo = rec.get("tipo")
            if tipo == "inviato":
                inviati[ref] = rec
            elif tipo in ("esito", "ripresa"):
                chiusi.add(ref)
            elif tipo == "ordine" and rec.get("cor"):
                cor_per_ref.setdefault(ref, []).append(str(rec["cor"]))
        pendenti = [r for r in inviati if r not in chiusi]
        if not pendenti:
            return True
        cor_live = sorted({c for r in pendenti if inviati[r].get("mode") == "live"
                           for c in cor_per_ref.get(r, [])})
        trovati: Dict[str, Dict[str, Any]] = {}
        if cor_live:
            if lista_ordini is None:
                logger.error("[motore] ripresa: %d ordini LIVE in volo e nessun accesso a "
                             "Betfair: guardia ARMATA", len(cor_live))
                return False
            try:
                for i in range(0, len(cor_live), 50):
                    risposta = lista_ordini(cor_live[i:i + 50]) or {}
                    for o in risposta.get("currentOrders") or []:
                        if o.get("customerOrderRef"):
                            trovati[str(o["customerOrderRef"])] = o
            except Exception as ex:  # noqa: BLE001 - fail-closed
                logger.error("[motore] ripresa: listCurrentOrders KO, guardia ARMATA: %s",
                             str(ex)[:200])
                return False
        sommario: List[str] = []
        for ref in pendenti:
            rec = inviati[ref]
            cors = cor_per_ref.get(ref, [])
            if rec.get("mode") != "live":
                esito, dett = "perso_paper", "ordine simulato: il blotter paper non " \
                                             "sopravvive al riavvio"
            elif any(c in trovati for c in cors):
                ordini = [trovati[c] for c in cors if c in trovati]
                esito = "ritrovato"
                dett = [{"betId": o.get("betId"), "status": o.get("status"),
                         "sizeMatched": o.get("sizeMatched"),
                         "customerOrderRef": o.get("customerOrderRef")} for o in ordini]
            elif cors:
                esito, dett = "non_trovato", "ordine inviato ma assente dagli ordini " \
                                             "correnti (mai arrivato o gia' chiuso)"
            else:
                esito, dett = "mai_inviato_place", "nessuna riga 'ordine': place mai " \
                                                   "chiamato (cancel/replace: esito ignoto)"
            sommario.append(f"{ref}={esito}")
            try:
                self.diario.scrivi({"tipo": "ripresa", "ref": ref, "esito": esito,
                                    "dettaglio": dett, "ts_ms": self._ora_ms()})
            except Exception as ex:  # noqa: BLE001
                logger.error("[motore] ripresa: riga di %s non scritta: %s", ref, ex)
                return False
        logger.warning("[motore] ripresa dal diario: %d comandi in volo: %s",
                       len(pendenti), ", ".join(sommario)[:500])
        msg = f"ripresa motore ordini: {len(pendenti)} comandi in volo al riavvio: " \
              f"{', '.join(sommario)[:300]}"

        def _alert(sb: Any) -> None:
            sb.table("live_alerts").insert({"level": "WARN", "code": "MOTORE_RIPRESA",
                                            "message": msg}).execute()
        self.scrittore.accoda("alert ripresa", _alert)
        return True
