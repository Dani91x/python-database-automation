"""esiti_ordini_canale.py - gli ESITI degli ordini in coda, dal canale del runner.

Che cosa risolve (23/09). Omega e Safe mettono i loro ordini sulla coda del
runner calcio (``betfair_live_order_requests``) e ne vengono a sapere l'esito
SOLO al giro dopo, rileggendo lo specchio ``betfair_live_orders`` dal database
(``omega_service.poll_flumine_pending``): fino a 20 s dopo per Omega, 2 s per
Safe. Eppure il runner quell'esito lo PUBBLICA GIA', riga per riga, sul canale
locale 47331 (topic ``order``, ``db.upsert_live_order``: la riga esatta dello
specchio, a ogni cambio di bet_id/stato/abbinato/residuo/prezzo medio). Questo
modulo e' il lettore.

LE REGOLE, ognuna inchiodata da un test
(``Betfair/omega/tests/test_esiti_ordini_canale_2026_09_23.py``):

1. **Interruttore ``ESITI_ORDINI_CANALE``, SPENTO di serie.** Acceso solo se
   qualcuno lo scrive davvero (``1``/``true``/``si``/``yes``, la regola di
   ``canale_bot.acceso``). Spento: nessun thread, nessuna porta, nessuna
   istruzione diversa nel poll (traccia delle chiamate identica).
2. **Nessuna decisione cambia.** La riga del canale entra nel poll AL POSTO
   della lettura ``get_live_order_mirror`` e passa per le STESSE funzioni
   (``_poll_one_flumine_trade`` / ``_poll_one_flumine_live_trade`` ->
   ``_flumine_confirm`` -> ``X.aggiorna_trade``). Cambia solo QUANDO il bot lo
   sa e DA DOVE lo legge.
3. **Solo gli esiti TERMINALI.** Dal canale si prende una riga solo se il suo
   stato e' terminale (``EXECUTION_COMPLETE``, ``EXPIRED``, ``LAPSED``,
   ``VIOLATION``, ``VOIDED``, ``CANCELLED``): e' definitiva, un fotogramma
   perso non la puo' rendere falsa. Una riga intermedia (``EXECUTABLE``,
   parziale) NON si usa: se il client ha perso un push per contropressione, la
   riga intermedia potrebbe essere vecchia e portare a un "nessun abbinamento"
   sbagliato alla scadenza del TTL. Per quelle vale il database, come oggi.
4. **Mai piu' vecchia.** In memoria una riga non sostituisce mai una riga con
   ``updated_at`` uguale o piu' recente, ne' una terminale con una non
   terminale. Nel poll, se la riga del bot ha gia' un ``betfair_updated_at``
   piu' recente del ``matched_at`` dell'evento (o non confrontabile), si legge
   il database.
5. **Zero letture in piu'.** Nel poll la riga dal canale SOSTITUISCE una
   lettura. L'applicatore (il "subito") gira solo per le richieste di QUESTO
   bot (``rid`` noti: dall'ultimo elenco dei pending e dall'enqueue) e fa le
   letture che il poll successivo avrebbe fatto per quella riga (elenco dei
   pending + richiesta di coda): dopo, quella riga non e' piu' pending e il
   poll non le rifa'.
6. **Il ciclo del bot non si tocca.** L'applicatore lavora in un thread suo, ma
   SOLO col lucchetto del ciclo (``ciclo()``): mai in parallelo a
   ``run_once``. La cadenza del poll resta quella di oggi, che fa da ripiego
   (canale muto) e da riconciliazione.
7. **Il canale del runner non cambia comportamento.** Il client si collega come
   LETTORE (``/lettore/order``, vedi ``local_channel.PREFISSO_LETTORE``): riceve
   solo ``order``, non conta come desktop collegato, non puo' mandare comandi.
8. **Modulo PURO**: nessun import di flumine, betfairlightweight, supabase o
   database. ``websockets`` entra solo dentro il thread del client.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from contextlib import nullcontext
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, Optional, Tuple

from .canale_bot import VALORI_ACCESI, acceso

logger = logging.getLogger(__name__)

__all__ = [
    "VALORI_ACCESI", "acceso", "ENV_ESITI", "ENV_PORTA", "PORTA", "TOPIC",
    "PERCORSO", "STATI_TERMINALI", "MemoriaEsiti", "ClientEsiti", "EsitiOrdini",
    "DbConSpecchioDalCanale", "porta", "terminale", "istanza", "attiva",
    "ricorda_richiesta",
]

#: L'interruttore. Assente = SPENTO, sempre.
ENV_ESITI = "ESITI_ORDINI_CANALE"
#: La porta del canale del runner calcio: lo STESSO nome che usa il runner
#: (``runner.py``: ``LIVE_LOCAL_WS_PORT``), un nome solo per i due lati.
ENV_PORTA = "LIVE_LOCAL_WS_PORT"
PORTA = 47331
#: Il topic che il runner gia' pubblica (``db.upsert_live_order``).
TOPIC = "order"
#: Il percorso da LETTORE: solo ``order``, mai comandi, non conta come desktop.
PERCORSO = "/lettore/" + TOPIC
#: Gli stati TERMINALI di un ordine flumine. Gli stessi di
#: ``omega_service._FLUMINE_TERMINAL``: un test di contratto verifica che non
#: divergano (una stringa scritta due volte diverge sempre, prima o poi).
STATI_TERMINALI = frozenset(
    {"EXECUTION_COMPLETE", "EXPIRED", "LAPSED", "VIOLATION", "VOIDED", "CANCELLED"}
)
#: Tetto della memoria (righe). Il bot ha qualche decina di ordini al giorno;
#: il tetto esiste perche' una cache senza tetto in un processo che vive giorni
#: e' un guasto che arriva sempre.
MAX_RIGHE = 5000

_ATTESE_S = (0.5, 1.0, 2.0, 5.0)
_RECV_TIMEOUT_S = 2.0


def porta() -> int:
    """La porta del canale del runner calcio: ``LIVE_LOCAL_WS_PORT`` o 47331."""
    grezza = (os.getenv(ENV_PORTA) or "").strip()
    if not grezza:
        return PORTA
    try:
        return int(grezza)
    except ValueError:
        return PORTA


def _istante(valore: Any) -> Optional[float]:
    """ISO-8601 -> epoch (s). ``None`` se assente o illeggibile: mai inventato."""
    if valore is None or valore == "":
        return None
    if isinstance(valore, datetime):
        dt = valore
    else:
        try:
            dt = datetime.fromisoformat(str(valore).replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def terminale(riga: Any) -> bool:
    """La riga dello specchio dice un esito DEFINITIVO?"""
    return isinstance(riga, dict) and str(riga.get("status") or "").upper() in STATI_TERMINALI


def _rid(riga: Dict[str, Any]) -> Optional[int]:
    """L'id della richiesta di coda: ``request_id`` o, in sua assenza, dal ref
    ``awlq<id>`` (la stessa regola di ``live_trading_strategy._request_id_from_ref``)."""
    v = riga.get("request_id")
    if v is None:
        ref = riga.get("client_order_ref")
        if isinstance(ref, str) and ref.startswith("awlq"):
            v = ref[4:]
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ la memoria
class MemoriaEsiti:
    """L'ULTIMA riga dello specchio per ``(mode, client_order_ref)``.

    Thread-safe: scrive il thread del client, legge il thread del bot.
    """

    def __init__(self, max_righe: int = MAX_RIGHE) -> None:
        self._righe: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._max = max(1, int(max_righe))
        self._conti: Dict[str, int] = {"ricevute": 0, "tenute": 0, "vecchie": 0,
                                       "scartate": 0, "terminali": 0}

    def _conta(self, chiave: str) -> None:
        self._conti[chiave] = int(self._conti.get(chiave, 0)) + 1

    def ricevi(self, riga: Any) -> bool:
        """Una riga dal canale. ``True`` se e' entrata (piu' fresca di quella
        che c'era). NON SOLLEVA MAI."""
        with self._lock:
            self._conta("ricevute")
            if not isinstance(riga, dict):
                self._conta("scartate")
                return False
            ref = riga.get("client_order_ref")
            mode = riga.get("mode")
            quando = _istante(riga.get("updated_at"))
            if not ref or mode not in ("paper", "live") or quando is None:
                # senza chiave o senza istante non si sa dove metterla ne' se
                # e' piu' fresca: fuori (il database resta la verita').
                self._conta("scartate")
                return False
            chiave = (str(mode), str(ref))
            prima = self._righe.get(chiave)
            if prima is not None:
                if quando <= float(prima["_istante"]):
                    self._conta("vecchie")
                    return False
                if terminale(prima) and not terminale(riga):
                    # un esito definitivo non torna indietro
                    self._conta("vecchie")
                    return False
                self._righe.pop(chiave, None)       # in coda: la piu' recente
            copia = dict(riga)
            copia["_istante"] = quando
            self._righe[chiave] = copia
            while len(self._righe) > self._max:
                self._righe.pop(next(iter(self._righe)))
            self._conta("tenute")
            if terminale(riga):
                self._conta("terminali")
            return True

    def esito_terminale(self, ref: str, mode: str) -> Optional[Dict[str, Any]]:
        """La riga TERMINALE per ``(mode, ref)``, come la darebbe il database
        (senza chiavi interne), o ``None``."""
        with self._lock:
            riga = self._righe.get((str(mode), str(ref)))
            if riga is None or not terminale(riga):
                return None
            fuori = dict(riga)
        fuori.pop("_istante", None)
        return fuori

    def stato(self) -> Dict[str, Any]:
        with self._lock:
            return {**self._conti, "righe": len(self._righe)}


# ------------------------------------------------------------------- il client
def _connetti_ws(url: str) -> Any:
    """Client WebSocket di sola lettura. Import PIGRO: senza ``websockets`` il
    modulo resta importabile e il bot lavora esattamente come oggi."""
    from websockets.sync.client import connect

    return connect(url, open_timeout=5.0, close_timeout=1.0, max_queue=64)


class ClientEsiti:
    """Client LETTORE del canale del runner (``/lettore/order``), in un thread
    daemon. Non solleva mai verso il bot; riconnette con attesa crescente."""

    def __init__(self, memoria: MemoriaEsiti, *,
                 su_terminale: Optional[Callable[[Dict[str, Any]], None]] = None,
                 porta_ws: Optional[int] = None, host: str = "127.0.0.1",
                 connetti: Optional[Callable[[str], Any]] = None) -> None:
        self.memoria = memoria
        self._su_terminale = su_terminale
        self.porta = int(porta_ws) if porta_ws is not None else porta()
        self.host = host
        self._connetti = connetti or _connetti_ws
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.collegato = False
        self.connessioni = 0
        self.riagganci = 0
        self.errori = 0
        self.ultimo_errore: Optional[str] = None
        self._detto = False

    @property
    def url(self) -> str:
        return "ws://%s:%d%s" % (self.host, self.porta, PERCORSO)

    def avvia(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._gira, daemon=True,
                                        name="esiti-ordini-ws")
        self._thread.start()

    def ferma(self) -> None:
        self._stop.set()

    def stato(self) -> Dict[str, Any]:
        return {"collegato": self.collegato, "connessioni": self.connessioni,
                "riagganci": self.riagganci, "errori": self.errori,
                "ultimo_errore": self.ultimo_errore, "url": self.url,
                "memoria": self.memoria.stato()}

    def _gira(self) -> None:
        i = 0
        while not self._stop.is_set():
            try:
                with self._connetti(self.url) as ws:
                    self.collegato = True
                    self.connessioni += 1
                    self._detto = False
                    i = 0
                    logger.info("[esiti-ws] agganciato come lettore a %s", self.url)
                    while not self._stop.is_set():
                        try:
                            grezzo = ws.recv(timeout=_RECV_TIMEOUT_S)
                        except TimeoutError:
                            continue
                        self.incassa(grezzo)
            except Exception as ex:  # noqa: BLE001 - il bot vive senza canale
                self.errori += 1
                self.ultimo_errore = str(ex)[:200]
                if not self._detto:
                    self._detto = True
                    logger.info("[esiti-ws] canale %s non disponibile (%s): gli esiti "
                                "arrivano dal poll del database, come oggi.",
                                self.url, str(ex)[:120])
            finally:
                self.collegato = False
            if self._stop.is_set():
                break
            self.riagganci += 1
            self._stop.wait(_ATTESE_S[min(i, len(_ATTESE_S) - 1)])
            i += 1

    def incassa(self, grezzo: Any) -> bool:
        """Un messaggio del canale. ``True`` se una riga e' entrata in memoria.
        NON SOLLEVA MAI (e' il pezzo che i test esercitano senza socket)."""
        try:
            msg = json.loads(grezzo) if isinstance(grezzo, (str, bytes, bytearray)) else grezzo
        except (ValueError, TypeError):
            return False
        if not isinstance(msg, dict) or msg.get("t") != TOPIC:
            return False                    # hello e altro: non sono righe
        riga = msg.get("d")
        if not self.memoria.ricevi(riga):
            return False
        if terminale(riga) and self._su_terminale is not None:
            try:
                self._su_terminale(riga)
            except Exception as ex:  # noqa: BLE001 - avvisare non ferma il client
                self.errori += 1
                self.ultimo_errore = str(ex)[:200]
        return True


# --------------------------------------------------- il db del poll, con canale
class DbConSpecchioDalCanale:
    """Il ``db`` del poll con UNA sola differenza: ``get_live_order_mirror``
    prende prima la riga TERMINALE dal canale (zero letture) e, se non c'e' o
    e' piu' vecchia della riga del bot, legge il database come oggi. Tutto il
    resto passa al ``db`` vero, attributi compresi (anche in scrittura)."""

    __slots__ = ("_db", "_memoria", "_soglie", "_conti", "_rid_per_trade", "_su_chiusa")

    def __init__(self, db: Any, memoria: MemoriaEsiti,
                 soglie: Optional[Dict[str, Optional[float]]] = None,
                 conti: Optional[Dict[str, int]] = None,
                 rid_per_trade: Optional[Dict[Any, int]] = None,
                 su_chiusa: Optional[Callable[[int], None]] = None) -> None:
        object.__setattr__(self, "_db", db)
        object.__setattr__(self, "_memoria", memoria)
        object.__setattr__(self, "_soglie", dict(soglie or {}))
        object.__setattr__(self, "_conti", conti if conti is not None else {})
        object.__setattr__(self, "_rid_per_trade", dict(rid_per_trade or {}))
        object.__setattr__(self, "_su_chiusa", su_chiusa)

    def _chiusa(self, trade_id: Any) -> None:
        """Una riga del poll non e' piu' pending: la sua richiesta non e' piu'
        da seguire (l'applicatore non fara' letture per niente)."""
        cb = self._su_chiusa
        rid = self._rid_per_trade.get(str(trade_id))
        if cb is not None and rid is not None:
            try:
                cb(rid)
            except Exception:  # noqa: BLE001 - dimenticare non ferma il poll
                pass

    def update_trade(self, trade_id: Any, **campi: Any) -> Any:
        esito = self._db.update_trade(trade_id, **campi)
        if "status" in campi and str(campi.get("status")) != "pending":
            self._chiusa(trade_id)
        return esito

    def delete_trade(self, trade_id: Any) -> Any:
        esito = self._db.delete_trade(trade_id)
        self._chiusa(trade_id)
        return esito

    def __getattr__(self, nome: str) -> Any:
        return getattr(object.__getattribute__(self, "_db"), nome)

    def __setattr__(self, nome: str, valore: Any) -> None:
        setattr(object.__getattribute__(self, "_db"), nome, valore)

    def _conta(self, chiave: str) -> None:
        self._conti[chiave] = int(self._conti.get(chiave, 0)) + 1

    def get_live_order_mirror(self, client_order_ref: str, mode: str = "paper") -> Any:
        riga = self._memoria.esito_terminale(str(client_order_ref), str(mode))
        if riga is not None:
            soglia = self._soglie.get(str(client_order_ref))
            if soglia is None:
                self._conta("specchio_dal_canale")
                return riga
            istante = _istante(riga.get("matched_at"))
            if istante is not None and istante >= soglia:
                self._conta("specchio_dal_canale")
                return riga
            # la riga del bot sa gia' qualcosa di piu' recente (o non si puo'
            # dire): nel dubbio vince il database, come oggi.
            self._conta("canale_piu_vecchio")
        self._conta("specchio_dal_db")
        return self._db.get_live_order_mirror(client_order_ref, mode)


def _soglia_del_trade(tr: Dict[str, Any]) -> Optional[float]:
    """L'istante di Betfair gia' noto alla riga del bot (colonna o meta)."""
    meta = tr.get("meta") or {}
    return _istante(tr.get("betfair_updated_at") or
                    (meta.get("betfair_updated_at") if isinstance(meta, dict) else None))


def rid_del_trade(tr: Dict[str, Any]) -> Optional[int]:
    meta = tr.get("meta") or {}
    try:
        v = meta.get("flumine_request_id") if isinstance(meta, dict) else None
        return int(v) if v else None
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------- l'orchestratore del bot
class EsitiOrdini:
    """Memoria + client + applicatore, UNO per processo di bot.

    ``applica(rids)`` e' la funzione del bot che fa avanzare SOLO le righe con
    quelle richieste (per Omega e Safe: ``omega_service.poll_flumine_pending``
    con ``solo_rid``). La chiama il thread dell'applicatore, sempre dentro il
    lucchetto del ciclo.
    """

    def __init__(self, applica: Callable[[frozenset], Any], *,
                 porta_ws: Optional[int] = None,
                 connetti: Optional[Callable[[str], Any]] = None,
                 memoria: Optional[MemoriaEsiti] = None) -> None:
        self.memoria = memoria or MemoriaEsiti()
        self._applica = applica
        self.client = ClientEsiti(self.memoria, su_terminale=self._su_terminale,
                                  porta_ws=porta_ws, connetti=connetti)
        self._lock_ciclo = threading.Lock()
        self._lock = threading.Lock()
        self._nostri: frozenset = frozenset()
        self._appena_accodati: set = set()
        self._da_applicare: set = set()
        self._evento = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._contesto: Optional[Dict[str, Any]] = None
        self.conti: Dict[str, int] = {"svegliate": 0, "applicazioni": 0,
                                      "applicazioni_saltate": 0, "errori": 0,
                                      "specchio_dal_canale": 0, "specchio_dal_db": 0,
                                      "canale_piu_vecchio": 0}

    # ------------------------------------------------------------ ciclo di vita
    def avvia(self, *, client: bool = True) -> bool:
        """Accende client e applicatore. ``client=False`` solo nei test."""
        if self._thread is not None:
            return True
        if client:
            try:
                import websockets  # noqa: F401  - solo per sapere se c'e'
            except Exception as ex:  # noqa: BLE001 - dipendenza opzionale
                logger.info("[esiti] 'websockets' non disponibile (%s): esiti dal "
                            "poll del database, come oggi.", str(ex)[:120])
                return False
            self.client.avvia()
        self._thread = threading.Thread(target=self._gira_applicatore, daemon=True,
                                        name="esiti-ordini-applica")
        self._thread.start()
        return True

    def ferma(self) -> None:
        self._stop.set()
        self._evento.set()
        self.client.ferma()

    # --------------------------------------------------------- lato del ciclo
    def ciclo(self) -> Any:
        """Il lucchetto del ciclo: il bot lo tiene per tutto ``run_once``."""
        return self._lock_ciclo

    def ricorda_contesto(self, **contesto: Any) -> None:
        """``db``/``params``/``market`` dell'ultimo poll del ciclo: l'applicatore
        usa gli STESSI oggetti, non ne costruisce di suoi."""
        self._contesto = dict(contesto)

    def contesto(self) -> Optional[Dict[str, Any]]:
        return self._contesto

    def ricorda_rid(self, rid: Any) -> None:
        """Una richiesta appena accodata da questo bot: da ora un suo esito
        TERMINALE sveglia l'applicatore, senza aspettare il prossimo poll."""
        try:
            r = int(rid)
        except (TypeError, ValueError):
            return
        if r <= 0:
            return
        gia_arrivato = any(self.memoria.esito_terminale("awlq%d" % r, m) is not None
                           for m in ("paper", "live"))
        with self._lock:
            self._appena_accodati.add(r)
            if gia_arrivato:
                # l'esito ha battuto la risposta dell'enqueue: non si perde
                self._da_applicare.add(r)
        if gia_arrivato:
            self._evento.set()

    def aggiorna_nostri(self, pendings: Iterable[Dict[str, Any]]) -> None:
        """Le richieste di QUESTO bot ancora in attesa, dall'elenco che il poll
        ha appena letto (nessuna lettura in piu')."""
        rids = {r for r in (rid_del_trade(t) for t in pendings if isinstance(t, dict))
                if r is not None}
        with self._lock:
            self._nostri = frozenset(rids)
            self._appena_accodati.clear()

    def e_nostra(self, rid: Optional[int]) -> bool:
        if rid is None:
            return False
        with self._lock:
            return rid in self._nostri or rid in self._appena_accodati

    def db_con_specchio(self, db: Any, pendings: Iterable[Dict[str, Any]]) -> Any:
        soglie: Dict[str, Optional[float]] = {}
        rid_per_trade: Dict[Any, int] = {}
        for t in pendings:
            if not isinstance(t, dict):
                continue
            rid = rid_del_trade(t)
            if rid is not None:
                soglie["awlq%d" % rid] = _soglia_del_trade(t)
                rid_per_trade[str(t.get("id"))] = rid
        return DbConSpecchioDalCanale(db, self.memoria, soglie, self.conti,
                                      rid_per_trade, self.dimentica_rid)

    def dimentica_rid(self, rid: int) -> None:
        """La riga di questa richiesta e' stata risolta: non si segue piu'."""
        with self._lock:
            self._nostri = self._nostri - {int(rid)}
            self._appena_accodati.discard(int(rid))
            self._da_applicare.discard(int(rid))

    # ------------------------------------------------------ lato del client
    def _su_terminale(self, riga: Dict[str, Any]) -> None:
        rid = _rid(riga)
        if not self.e_nostra(rid):
            return
        with self._lock:
            self._da_applicare.add(int(rid))  # type: ignore[arg-type]
            self.conti["svegliate"] = int(self.conti.get("svegliate", 0)) + 1
        self._evento.set()

    # -------------------------------------------------------- l'applicatore
    def applica_ora(self) -> int:
        """Un passaggio dell'applicatore (pubblico per i test): prende il
        lucchetto del ciclo, tiene solo le richieste ancora nostre e fa
        avanzare SOLO quelle. Ritorna quante ne ha passate ad ``applica``."""
        with self._lock_ciclo:
            with self._lock:
                rids = frozenset(r for r in self._da_applicare
                                 if r in self._nostri or r in self._appena_accodati)
                self._da_applicare.clear()
            if not rids:
                # il ciclo le ha gia' risolte (lo specchio dal canale era gia'
                # in memoria): nessuna lettura.
                self.conti["applicazioni_saltate"] += 1
                return 0
            try:
                self._applica(rids)
                self.conti["applicazioni"] += 1
            except Exception as ex:  # noqa: BLE001 - l'applicatore non ferma il bot
                self.conti["errori"] += 1
                logger.warning("[esiti] applicazione KO (%s): ci pensa il poll di "
                               "ciclo, come oggi.", str(ex)[:160])
            return len(rids)

    def _gira_applicatore(self) -> None:
        while not self._stop.is_set():
            if not self._evento.wait(1.0):
                continue
            self._evento.clear()
            if self._stop.is_set():
                break
            self.applica_ora()

    def statistiche(self) -> Dict[str, Any]:
        with self._lock:
            nostri = len(self._nostri) + len(self._appena_accodati)
        return {**self.conti, "richieste_seguite": nostri,
                "client": self.client.stato()}


# ------------------------------------------------ l'istanza del processo
_ISTANZA: Dict[str, Optional[EsitiOrdini]] = {"esiti": None}


def istanza() -> Optional[EsitiOrdini]:
    return _ISTANZA["esiti"]


def registra(esiti: Optional[EsitiOrdini]) -> None:
    """Registra (o toglie, con ``None``) l'istanza del processo."""
    _ISTANZA["esiti"] = esiti


def attiva() -> Optional[EsitiOrdini]:
    """L'istanza del processo SE l'interruttore e' acceso, altrimenti ``None``.
    L'interruttore si rilegge a ogni chiamata (mai memorizzato)."""
    e = _ISTANZA["esiti"]
    if e is None or not acceso(ENV_ESITI):
        return None
    return e


def ricorda_richiesta(rid: Any) -> None:
    """Chiamata all'enqueue di un ordine: no-op a interruttore spento."""
    e = attiva()
    if e is not None:
        e.ricorda_rid(rid)


def ciclo() -> Any:
    """Il lucchetto del ciclo a interruttore acceso, altrimenti un contesto
    vuoto: a interruttore spento ``run_once`` gira come oggi."""
    e = attiva()
    return e.ciclo() if e is not None else nullcontext()
