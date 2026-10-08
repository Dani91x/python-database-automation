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
import time
from contextlib import nullcontext
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from .canale_bot import VALORI_ACCESI, acceso

logger = logging.getLogger(__name__)

__all__ = [
    "VALORI_ACCESI", "acceso", "ENV_ESITI", "ENV_PORTA", "PORTA", "TOPIC",
    "PERCORSO", "STATI_TERMINALI", "MemoriaEsiti", "ClientEsiti", "EsitiOrdini",
    "DbConSpecchioDalCanale", "porta", "terminale", "istanza", "attiva",
    "ricorda_richiesta",
    # 30/09: la posizione di conto dallo stream ordini del runner LIVE
    "TOPIC_CONTO", "PERCORSO_CONTO", "FONTE_CONTO", "ordine_del_conto", "payload_conto",
    "pubblica_conto_da_evento", "osserva_conto_su_flumine", "MemoriaConto",
    # 08/10 (W3a): la fotografia PAPER e la sorveglianza unica dei bot
    "MODO_LIVE", "MODO_PAPER", "TOPIC_CONTO_PAPER", "TOPIC_CONTO_TUTTI",
    "PERCORSO_CONTO_TUTTI", "modo_della_fotografia", "ordine_paper_del_conto",
    "payload_conto_paper", "pubblica_conto_paper", "con_ref_del_bot",
    "SorveglianzaConto", "direzione_di_conto", "verdetto_in_esposizione",
    # 08/10 (W3a, seconda tappa): un verdetto per tutti, ordini di altri bot
    "vivo_in_size", "verdetto_posizione", "ProprietariConto", "lettore_proprietari",
    "RIPROVA_PROPRIETARI_S",
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
_PREFISSO_LETTORE = "/lettore/"
PERCORSO = _PREFISSO_LETTORE + TOPIC
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
                istante_prima = float(prima["_istante"])
                # 23/09 (M-2, revisore B): a PARITA' di ``updated_at`` entra una
                # riga TERMINALE sopra una intermedia (FOK: EXECUTABLE ed
                # EXECUTION_COMPLETE nello stesso ms), mai il contrario.
                a_pari_terminale = (quando == istante_prima and terminale(riga)
                                    and not terminale(prima))
                if quando <= istante_prima and not a_pari_terminale:
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

    def __init__(self, memoria: Any, *,
                 su_terminale: Optional[Callable[[Dict[str, Any]], None]] = None,
                 porta_ws: Optional[int] = None, host: str = "127.0.0.1",
                 connetti: Optional[Callable[[str], Any]] = None,
                 topic: str = TOPIC) -> None:
        self.memoria = memoria
        # 30/09: lo stesso client legge anche la POSIZIONE DI CONTO (``conto``,
        # Mike). Di serie ``order``: Omega e Safe non cambiano di una riga.
        # 08/10 (W3a): piu' topic separati da virgola (``conto,conto_paper``),
        # la stessa grammatica del lettore di ``local_channel``
        # (``/lettore/<topic>[,<topic>...]``).
        self.topic = str(topic)
        self._accettati = frozenset(t for t in self.topic.split(",") if t)
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
        return "ws://%s:%d%s%s" % (self.host, self.porta, _PREFISSO_LETTORE, self.topic)

    def avvia(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._gira, daemon=True,
                                        name=("esiti-ordini-ws" if self.topic == TOPIC
                                              else "conto-ordini-ws"))
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
        if not isinstance(msg, dict) or msg.get("t") not in self._accettati:
            return False                    # hello e altro: non sono righe
        riga = msg.get("d")
        # 08/10 (W3a): la fotografia del conto PAPER viaggia sul suo topic
        # gemello e porta ``modo='paper'``; quella del runner LIVE sul topic di
        # sempre (``modo`` 'live' o assente, 30/09). Una che dice il contrario
        # del suo topic non entra: paper e live MAI mischiati.
        if msg.get("t") in (TOPIC_CONTO, TOPIC_CONTO_PAPER) and \
                not _modo_coerente(str(msg.get("t")), riga):
            return False
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


# ===========================================================================
# LA POSIZIONE DI CONTO DALLO STREAM ORDINI (30/09, ordine dell'utente)
# ===========================================================================
# Fatto del 30/09 (live, 36130526): l'utente chiude la posizione di Mike dal
# sito Betfair verso le 15:30:45, Mike se ne accorge alle 15:32:13. Mike
# rilegge la posizione di conto via REST al piu' ogni ``reconcile_every_s``
# (30 s) dentro il suo giro. Eppure il runner LIVE e' iscritto allo STREAM
# ORDINI del conto SENZA filtro di strategia (flumine
# ``streams/orderstream.py``: ``customer_strategy_refs=None`` perche'
# ``flumine.config.customer_strategy_ref`` e' ``None``): riceve al millisecondo
# OGNI ordine del conto, anche quelli piazzati a mano dal sito. Poi pero'
# flumine li SCARTA (``order/process.py`` ``process_current_orders``: salta gli
# ordini senza ``customer_order_ref`` e quelli il cui ref non e' di una sua
# strategia, "Strategy not available to create order") e nessuna strategia li
# vede in ``process_orders``.
#
# Qui il runner li PUBBLICA sul canale locale (topic ``conto``, lettori su
# ``/lettore/conto``): per ogni mercato toccato dall'evento dello stream, TUTTI
# gli ordini del conto che la cache dello stream conosce su quel mercato, nella
# grafia di Betfair (camelCase, le stesse chiavi di ``listCurrentOrders``: chi
# legge li normalizza con la STESSA funzione che usa per la REST). Nessuna
# decisione qui: la prende il bot.
#
# REGOLE:
# * solo gli eventi del client REALE (``client.paper_trade`` falso): il client
#   PAPER affiancato non ha ordini del conto, e il runner PAPER non monta nulla;
# * l'osservatore avvolge ``Flumine._process_current_orders`` DOPO flumine
#   (flumine lavora identico) e non solleva mai;
# * Omega e Safe leggono ``/lettore/order``: un topic in piu' non arriva a loro
#   (``local_channel``: un lettore riceve solo i topic che ha chiesto).
TOPIC_CONTO = "conto"
PERCORSO_CONTO = _PREFISSO_LETTORE + TOPIC_CONTO
FONTE_CONTO = "stream_ordini"

# 08/10 (W3a, ordine dell'utente: «i bot devono essere al corrente degli
# ordini esterni [...] nel minor tempo possibile»). IL PAPER E' LO SPECCHIO DEL
# LIVE: in prova l'intervento esterno possibile e' l'ordine MANUALE dell'app
# (ladder del runner, simulato sul client PAPER). Il runner PAPER pubblica la
# fotografia dei SUOI ordini del mercato (bot e manuali, blotter della
# strategia paper) sul topic GEMELLO ``conto_paper``, con ``modo='paper'``:
# stesso formato di ``conto`` (grafia di ``listCurrentOrders``), mai sullo
# stesso topic (un lettore del 30/09 non vede mai una fotografia paper).
MODO_LIVE = "live"
MODO_PAPER = "paper"
TOPIC_CONTO_PAPER = "conto_paper"
FONTE_CONTO_PAPER = "blotter_paper"
#: il lettore dei bot: le due fotografie su UNA connessione
TOPIC_CONTO_TUTTI = TOPIC_CONTO + "," + TOPIC_CONTO_PAPER
PERCORSO_CONTO_TUTTI = _PREFISSO_LETTORE + TOPIC_CONTO_TUTTI


def modo_della_fotografia(foto: Any) -> str:
    """``paper`` o ``live``. Una fotografia senza ``modo`` e' quella del runner
    LIVE del 30/09 (lo stream ordini del conto)."""
    m = foto.get("modo") if isinstance(foto, dict) else None
    return MODO_PAPER if m == MODO_PAPER else MODO_LIVE


def _modo_coerente(topic: str, payload: Any) -> bool:
    """Il ``modo`` della fotografia e' quello del suo topic?"""
    if not isinstance(payload, dict):
        return False
    m = payload.get("modo")
    if topic == TOPIC_CONTO_PAPER:
        return m == MODO_PAPER
    return m in (None, MODO_LIVE)

#: (grafia Betfair di ``listCurrentOrders``, attributo di ``CurrentOrder``)
_CAMPI_ORDINE_CONTO: Tuple[Tuple[str, str], ...] = (
    ("betId", "bet_id"), ("marketId", "market_id"), ("selectionId", "selection_id"),
    ("handicap", "handicap"), ("side", "side"), ("status", "status"),
    ("orderType", "order_type"), ("persistenceType", "persistence_type"),
    ("sizeMatched", "size_matched"), ("sizeRemaining", "size_remaining"),
    ("sizeCancelled", "size_cancelled"), ("sizeLapsed", "size_lapsed"),
    ("sizeVoided", "size_voided"), ("averagePriceMatched", "average_price_matched"),
    ("customerOrderRef", "customer_order_ref"),
    ("customerStrategyRef", "customer_strategy_ref"),
    ("placedDate", "placed_date"), ("matchedDate", "matched_date"),
)


def _in_json(v: Any) -> Any:
    """Un valore che viaggia sul canale: le date in ISO-8601 UTC con la ``Z``
    (come le scrive Betfair), il resto com'e'."""
    if isinstance(v, datetime):
        dt = v if v.tzinfo is not None else v.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return v


def ordine_del_conto(ordine: Any) -> Dict[str, Any]:
    """UN ordine dello stream (``betfairlightweight`` ``CurrentOrder``, o il suo
    dict camelCase) nella grafia di ``listCurrentOrders``. Nessun campo
    dedotto: cio' che lo stream non porta resta ``None``."""
    out: Dict[str, Any] = {}
    for camel, snake in _CAMPI_ORDINE_CONTO:
        v = ordine.get(camel) if isinstance(ordine, dict) else getattr(ordine, snake, None)
        out[camel] = _in_json(v)
    ps = (ordine.get("priceSize") if isinstance(ordine, dict)
          else getattr(ordine, "price_size", None))
    if isinstance(ps, dict):
        out["priceSize"] = {"price": ps.get("price"), "size": ps.get("size")}
    elif ps is not None:
        out["priceSize"] = {"price": getattr(ps, "price", None),
                            "size": getattr(ps, "size", None)}
    else:
        out["priceSize"] = None
    return out


def _market_id_di(ordini_mercato: Any, ordini: list) -> Optional[str]:
    for o in ordini:
        mid = o.get("marketId")
        if mid:
            return str(mid)
    agg = getattr(ordini_mercato, "streaming_update", None)
    if isinstance(agg, dict) and agg.get("id"):
        return str(agg["id"])
    return None


def _iso_ms(ms: int) -> str:
    """Epoch in millisecondi -> ISO-8601 UTC al millisecondo con la ``Z``."""
    dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def payload_conto(ordini_mercato: Any, *, ricevuto_ms: int) -> Optional[Dict[str, Any]]:
    """Il messaggio ``conto`` per UN mercato (un ``CurrentOrders`` dello stream
    ordini). ``None`` se non si sa di che mercato si tratta."""
    ordini = [ordine_del_conto(o) for o in (getattr(ordini_mercato, "orders", None) or [])]
    market_id = _market_id_di(ordini_mercato, ordini)
    if not market_id:
        return None
    pt = getattr(ordini_mercato, "publish_time", None)
    return {"market_id": market_id, "ordini": ordini, "fonte": FONTE_CONTO,
            # 08/10 (W3a), chiave ADDITIVA: di chi e' questa fotografia. Lo
            # stream ordini del conto e' sempre e solo il LIVE.
            "modo": MODO_LIVE,
            "ricevuto_ms": int(ricevuto_ms),
            # 30/09 (UI), chiave ADDITIVA: l'istante in cui abbiamo LETTO gli
            # ordini del conto (= ``ricevuto_ms``, arrivo del messaggio dello
            # stream ordini; la pubblicazione segue nella stessa chiamata),
            # ISO-8601 UTC al millisecondo con la ``Z``
            "pnl_letto_at": _iso_ms(int(ricevuto_ms)),
            "publish_time_ms": (int(pt) if isinstance(pt, (int, float))
                                and not isinstance(pt, bool) else None),
            "snap": bool(getattr(ordini_mercato, "streaming_snap", False))}


def pubblica_conto_da_evento(evento: Any, pubblica: Callable[[str, Any], None], *,
                             adesso_ms: Optional[int] = None) -> int:
    """Un ``CurrentOrdersEvent`` di flumine -> un messaggio ``conto`` per ogni
    mercato del client REALE. Ritorna quanti ne ha pubblicati."""
    quando = int(adesso_ms if adesso_ms is not None else time.time() * 1000)
    n = 0
    for ordini_mercato in (getattr(evento, "event", None) or []):
        client = getattr(ordini_mercato, "client", None)
        if client is None or getattr(client, "paper_trade", True) is not False:
            continue        # client simulato (o ignoto): non e' il conto
        p = payload_conto(ordini_mercato, ricevuto_ms=quando)
        if p is None:
            continue
        pubblica(TOPIC_CONTO, p)
        n += 1
    return n


def osserva_conto_su_flumine(framework: Any, pubblica: Callable[[str, Any], None]) -> bool:
    """Monta l'osservatore sul framework flumine del runner LIVE. Idempotente;
    ``False`` se non montato (gia' montato, framework simulato, niente hook)."""
    if framework is None or getattr(framework, "SIMULATED", False):
        return False
    if getattr(framework, "_conto_osservato", False):
        return False
    originale = getattr(framework, "_process_current_orders", None)
    if not callable(originale):
        return False

    def _con_conto(evento: Any) -> None:
        originale(evento)           # flumine per primo, identico a prima
        try:
            pubblica_conto_da_evento(evento, pubblica)
        except Exception as ex:  # noqa: BLE001 - il canale non ferma mai flumine
            logger.debug("[conto-ws] pubblicazione KO: %s", str(ex)[:160])

    framework._process_current_orders = _con_conto
    framework._conto_osservato = True
    logger.info("[conto-ws] ordini del conto dallo stream pubblicati sul canale "
                "(topic %s)", TOPIC_CONTO)
    return True

def _impronta(ordini: Any) -> tuple:
    """Il CONTENUTO di una fotografia (per ordine: id, stato, abbinato, residuo,
    annullato, scaduto, invalidato), senza gli istanti. Lo stream ordini
    ripubblica la STESSA fotografia (snap ogni 3 s di flumine con ordini vivi):
    solo una fotografia DIVERSA da quella di prima puo' svegliare un bot."""
    out = []
    for o in ordini or []:
        if not isinstance(o, dict):
            continue
        numeri = []
        for k in ("sizeMatched", "sizeRemaining", "sizeCancelled", "sizeLapsed",
                  "sizeVoided"):
            try:
                numeri.append(round(float(o.get(k) or 0.0), 2))
            except (TypeError, ValueError):
                numeri.append(0.0)
        out.append((str(o.get("betId")), str(o.get("status")), *numeri))
    return tuple(sorted(out))


class MemoriaConto:
    """L'ULTIMA fotografia degli ordini del conto per mercato (dal canale).

    Thread-safe: scrive il thread del client, legge il giro del bot. Ogni
    fotografia nuova alza la ``versione`` del mercato: chi legge sa se c'e'
    qualcosa di nuovo senza confrontare le righe.

    08/10 (W3a): le fotografie sono tenute per ``(modo, mercato)``: quella del
    runner LIVE (stream ordini del conto) e quella del runner PAPER (blotter
    della strategia paper) dello stesso mercato non si sovrascrivono MAI.
    ``mercato(market_id)`` resta la fotografia LIVE (il contratto del 30/09).
    ``avvisa(market_id, modo)`` (se impostato) e' chiamato FUORI dal lucchetto
    quando arriva una fotografia dal CONTENUTO diverso dalla precedente: e' la
    sveglia del giro del bot (``SorveglianzaConto``)."""

    def __init__(self, max_mercati: int = 500,
                 orologio: Optional[Callable[[], float]] = None,
                 avvisa: Optional[Callable[[str, str], None]] = None) -> None:
        self._mercati: Dict[str, Dict[str, Any]] = {}
        self._impronte: Dict[str, tuple] = {}
        self._lock = threading.Lock()
        self._max = max(1, int(max_mercati))
        self._orologio = orologio or time.time
        self._versione = 0
        self._conti: Dict[str, int] = {"ricevute": 0, "tenute": 0, "scartate": 0,
                                       "vecchie": 0}
        self.avvisa = avvisa

    @staticmethod
    def _chiave(market_id: Any, modo: str) -> str:
        # la chiave LIVE e' il market_id nudo, come il 30/09
        return str(market_id) if modo == MODO_LIVE else "%s|%s" % (modo, market_id)

    def ricevi(self, payload: Any) -> bool:
        """Un messaggio ``conto`` (o ``conto_paper``). NON SOLLEVA MAI."""
        cambiata = False
        with self._lock:
            self._conti["ricevute"] += 1
            if not isinstance(payload, dict):
                self._conti["scartate"] += 1
                return False
            mid = payload.get("market_id")
            ordini = payload.get("ordini")
            if not mid or not isinstance(ordini, list):
                self._conti["scartate"] += 1
                return False
            modo = modo_della_fotografia(payload)
            chiave = self._chiave(mid, modo)
            prima = self._mercati.get(chiave)
            pt = payload.get("publish_time_ms")
            pt_prima = prima.get("publish_time_ms") if prima is not None else None
            if (isinstance(pt, (int, float)) and isinstance(pt_prima, (int, float))
                    and pt < pt_prima):
                # una fotografia piu' vecchia di quella che c'e' non la sostituisce
                self._conti["vecchie"] += 1
                return False
            self._versione += 1
            self._mercati.pop(chiave, None)
            righe = [dict(o) for o in ordini if isinstance(o, dict)]
            self._mercati[chiave] = {
                "ordini": righe,
                "ricevuto_ms": payload.get("ricevuto_ms"),
                "publish_time_ms": pt, "arrivato_s": float(self._orologio()),
                "versione": self._versione, "modo": modo}
            impronta = _impronta(righe)
            cambiata = self._impronte.get(chiave) != impronta
            self._impronte[chiave] = impronta
            while len(self._mercati) > self._max:
                via = next(iter(self._mercati))
                self._mercati.pop(via)
                self._impronte.pop(via, None)
            self._conti["tenute"] += 1
        avvisa = self.avvisa
        if cambiata and avvisa is not None:
            try:
                avvisa(str(mid), modo)
            except Exception:  # noqa: BLE001 - avvisare non ferma il client
                pass
        return True

    def mercato(self, market_id: Any, modo: str = MODO_LIVE) -> Optional[Dict[str, Any]]:
        """La fotografia del mercato (copia) nel ``modo`` chiesto, o ``None``."""
        with self._lock:
            f = self._mercati.get(self._chiave(market_id, modo))
            if f is None:
                return None
            return {**f, "ordini": [dict(o) for o in f["ordini"]]}

    def azzera(self) -> bool:
        with self._lock:
            c_era = bool(self._mercati)
            self._mercati.clear()
            self._impronte.clear()
            return c_era

    def stato(self) -> Dict[str, Any]:
        with self._lock:
            return {**self._conti, "mercati": len(self._mercati)}


# ===========================================================================
# 08/10 (W3a) - LA FOTOGRAFIA DEL CONTO PAPER (runner PAPER)
# ===========================================================================
# Il paper e' lo SPECCHIO del live: cio' che lo stream ordini del conto porta
# al runner LIVE (``pubblica_conto_da_evento``), in prova lo sa il BLOTTER
# della strategia paper del runner, che contiene OGNI ordine paper del mercato
# (quelli dei bot mandati in coda e quelli MANUALI dell'app). Stessa grafia
# (``listCurrentOrders``, le chiavi di ``_CAMPI_ORDINE_CONTO`` + ``priceSize``),
# stesso normalizzatore dal lato del bot (``omega_market._riga_corrente``).
# ``customerOrderRef`` e' il ref che il runner ha dato all'ordine (``awlq<id>``,
# ``live_order_build._create_order``): il bot riconosce i SUOI per ``bet_id``
# (``con_ref_del_bot``), come Omega fa gia' in live.
_STATI_VIVI_FLUMINE = frozenset({"PENDING", "EXECUTABLE", "CANCELLING", "UPDATING",
                                 "REPLACING"})


def _attr(obj: Any, nome: str) -> Any:
    """getattr difensivo: alcune property di flumine sollevano negli stati di
    confine (stessa regola di ``live_trading_strategy._val``)."""
    try:
        return getattr(obj, nome)
    except Exception:  # noqa: BLE001
        return None


def _numero(v: Any) -> float:
    try:
        return round(float(v or 0.0), 2)
    except (TypeError, ValueError):
        return 0.0


def ordine_paper_del_conto(ordine: Any) -> Optional[Dict[str, Any]]:
    """UN ordine flumine del client PAPER -> la grafia di ``listCurrentOrders``.
    ``None`` per un ordine senza ``bet_id`` (Betfair non lo conoscerebbe)."""
    bet_id = _attr(ordine, "bet_id")
    if not bet_id:
        return None
    ot = _attr(ordine, "order_type")
    stato = _attr(ordine, "status")
    stato = getattr(stato, "name", None) or (str(stato) if stato is not None else None)
    residuo = _numero(_attr(ordine, "size_remaining"))
    vivo = stato in _STATI_VIVI_FLUMINE and residuo > 0
    ref = None
    for fonte in ("context", "notes"):
        d = _attr(ordine, fonte)
        if isinstance(d, dict) and d.get("customer_order_ref"):
            ref = str(d.get("customer_order_ref"))
            break
    if ref is None:
        ref = _attr(ordine, "customer_order_ref")
    lato = _attr(ordine, "side")
    risposte = _attr(ordine, "responses")
    sid = _attr(ordine, "selection_id")
    medio = _attr(ordine, "average_price_matched")
    return {
        "betId": str(bet_id), "marketId": _attr(ordine, "market_id"),
        "selectionId": int(sid) if sid is not None else None,
        "handicap": _attr(ordine, "handicap"),
        "side": str(lato).upper() if lato is not None else None,
        "status": "EXECUTABLE" if vivo else "EXECUTION_COMPLETE",
        "orderType": "LIMIT",
        "persistenceType": _attr(ot, "persistence_type") if ot is not None else None,
        "sizeMatched": _numero(_attr(ordine, "size_matched")),
        "sizeRemaining": residuo,
        "sizeCancelled": _numero(_attr(ordine, "size_cancelled")),
        "sizeLapsed": _numero(_attr(ordine, "size_lapsed")),
        "sizeVoided": _numero(_attr(ordine, "size_voided")),
        "averagePriceMatched": (float(medio) if isinstance(medio, (int, float))
                                and not isinstance(medio, bool) and medio > 0 else None),
        "customerOrderRef": ref,
        "customerStrategyRef": None,
        "placedDate": _in_json(_attr(risposte, "date_time_placed")
                               if risposte is not None else None),
        "matchedDate": None,
        "priceSize": ({"price": _attr(ot, "price"), "size": _attr(ot, "size")}
                      if ot is not None else None),
    }


def payload_conto_paper(market_id: Any, ordini: Iterable[Any], *,
                        ricevuto_ms: int) -> Optional[Dict[str, Any]]:
    """Il messaggio ``conto_paper`` per UN mercato: tutti gli ordini paper del
    blotter su quel mercato. ``None`` senza mercato."""
    if not market_id:
        return None
    righe = []
    for o in ordini or []:
        r = ordine_paper_del_conto(o)
        if r is None:
            continue
        if r.get("marketId") and str(r["marketId"]) != str(market_id):
            continue
        righe.append(r)
    return {"market_id": str(market_id), "ordini": righe, "fonte": FONTE_CONTO_PAPER,
            "modo": MODO_PAPER, "ricevuto_ms": int(ricevuto_ms),
            "pnl_letto_at": _iso_ms(int(ricevuto_ms)),
            # nessuno stream: l'istante e' quello del blotter
            "publish_time_ms": int(ricevuto_ms), "snap": False}


def pubblica_conto_paper(market_id: Any, ordini: Iterable[Any],
                         pubblica: Callable[[str, Any], None], *,
                         adesso_ms: Optional[int] = None) -> bool:
    """Pubblica la fotografia PAPER del mercato sul topic gemello. ``True`` se
    pubblicata."""
    quando = int(adesso_ms if adesso_ms is not None else time.time() * 1000)
    p = payload_conto_paper(market_id, ordini, ricevuto_ms=quando)
    if p is None:
        return False
    pubblica(TOPIC_CONTO_PAPER, p)
    return True


# ===========================================================================
# 08/10 (W3a, reperto del coordinatore dal cantiere W2) - IL VERDETTO DI CONTO
# IN ESPOSIZIONE, non in size.
# ===========================================================================
# I tre verdetti (Mike, Omega, Safe) confrontavano il NETTO IN SIZE della
# selezione (BACK - LAY di tutti gli ordini, bot e utente) con la posizione del
# bot. Con il prezzo mosso un green-up CORRETTO della sola parte dell'utente
# (ordini suoi dal sito o dall'app) sposta il netto in size senza toccare il
# bot: Mike back 10, sito back 5 @1,50 coperto con lay 5,36 @1,40 -> netto 9,64
# -> «ridotta» (FALSO); Mike back 2, sito back 10 @5,0 coperto con lay 33,33
# @1,50 -> netto -21,33 -> «chiusa» (FALSO, e il bot abbandonerebbe la sua
# posizione). Da quando la «ridotta» ferma il bot, quel falso va tolto.
#
# LA REGOLA (una, per i tre bot): si separano gli ordini del BOT (riconosciuti
# per ref/bet_id, come sempre) da quelli ALTRUI, e si misura la parte
# DIREZIONALE dell'esposizione di ciascuno: la differenza fra il profitto se la
# selezione vince e quello se perde, che per ogni ordine abbinato vale
# ``+size*prezzo`` (back) o ``-size*prezzo`` (lay) (``flumine.utils.
# calculate_matched_exposure``: win - lose). Un green-up dell'utente su una
# posizione SUA ha parte direzionale ~0 e non tocca il bot; un ordine dell'utente
# che chiude (o riduce) la posizione del bot ha parte direzionale OPPOSTA. Quanto
# della parte direzionale del bot sopravvive (la stessa formula ``vivo`` di
# sempre, sulla direzione invece che sulla size) decide intera/ridotta/chiusa;
# il risultato si riporta in size equivalente al prezzo medio del bot. Se gli
# ordini altrui annullano il netto IN SIZE della posizione del bot (chiusura
# «a pari size» a un prezzo diverso) l'etichetta resta «chiusa» come prima.
# Dati che mancano (un abbinato senza prezzo medio, posizione del bot mista in
# segno): ``None`` = il chiamante usa l'aritmetica in size di prima (nessun
# prezzo inventato: difetto 3 del catalogo).
def _prezzo_medio(r: Dict[str, Any]) -> Optional[float]:
    for k in ("avg_price_matched", "average_price_matched", "averagePriceMatched",
              "price_matched", "priceMatched"):
        v = r.get(k)
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f > 1.0:
            return f
    return None


def _abbinato_riga(r: Dict[str, Any]) -> float:
    for k in ("size_matched", "size_settled", "sizeMatched"):
        v = r.get(k)
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return 0.0


def direzione_di_conto(righe: Iterable[Dict[str, Any]]) -> Optional[float]:
    """La parte DIREZIONALE dell'esposizione abbinata delle righe (win - lose):
    ``+size*prezzo`` per un back, ``-size*prezzo`` per un lay. Un ordine che
    compare in due liste (correnti e regolati) conta una volta (per ``bet_id``).
    ``None`` se un abbinato non ha un prezzo medio leggibile."""
    per_bet: Dict[str, Tuple[float, float, str]] = {}
    senza_bet = []
    for r in righe or []:
        if not isinstance(r, dict):
            continue
        s = _abbinato_riga(r)
        if s <= 0:
            continue
        p = _prezzo_medio(r)
        if p is None:
            return None
        lato = str(r.get("side") or "").lower()
        bid = str(r.get("bet_id") or r.get("betId") or "")
        if bid:
            prima = per_bet.get(bid)
            if prima is None or s > prima[0]:
                per_bet[bid] = (s, p, lato)
        else:
            senza_bet.append((s, p, lato))
    tot = 0.0
    for s, p, lato in list(per_bet.values()) + senza_bet:
        tot += s * p if lato == "back" else -s * p
    return round(tot, 4)


def verdetto_in_esposizione(*, atteso: float, righe_bot: Iterable[Dict[str, Any]],
                            righe_altrui: Iterable[Dict[str, Any]], eps: float,
                            conto_size: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """Il verdetto sulla posizione del bot (``atteso`` in size, segno del lato)
    dalla parte DIREZIONALE degli ordini del bot e di quelli altrui. Torna
    ``{"verdetto": "intera"|"ridotta"|"chiusa", "vivo": size equivalente,
    "direzione_bot", "direzione_altrui", "metro": "esposizione"}`` oppure
    ``None`` (il chiamante resta sull'aritmetica in size)."""
    if abs(atteso) <= eps:
        return None
    b = direzione_di_conto(righe_bot)
    u = direzione_di_conto(righe_altrui)
    if b is None or u is None or b * atteso <= 0:
        return None
    p_ref = b / atteso                       # prezzo medio del bot (> 0)
    vivo_d = min(b, max(0.0, b + u)) if b > 0 else max(b, min(0.0, b + u))
    eps_d = eps * p_ref
    if abs(vivo_d) + eps_d >= abs(b):
        verdetto = "intera"
    elif abs(vivo_d) <= eps_d:
        verdetto = "chiusa"
    else:
        verdetto = "ridotta"
    if verdetto == "ridotta" and conto_size is not None:
        vivo_size = (min(atteso, max(0.0, conto_size)) if atteso > 0
                     else max(atteso, min(0.0, conto_size)))
        if abs(vivo_size) <= eps:
            verdetto = "chiusa"      # chiusa a pari size, a un prezzo diverso
    return {"verdetto": verdetto, "vivo": round(vivo_d / p_ref, 2),
            "direzione_bot": round(b, 2), "direzione_altrui": round(u, 2),
            "metro": "esposizione"}


def vivo_in_size(atteso: float, conto: float) -> float:
    """Quanto della posizione del bot (``atteso``, in size col segno del lato)
    SOPRAVVIVE nel netto di conto ``conto``: la formula dei tre verdetti dal
    16/09 (Mike ``_verdetto_di_conto``, Omega e Safe idem)."""
    return (min(atteso, max(0.0, conto)) if atteso > 0
            else max(atteso, min(0.0, conto)))


def verdetto_posizione(*, atteso: float, conto_size: float,
                       righe_bot: Iterable[Dict[str, Any]],
                       righe_altrui: Iterable[Dict[str, Any]],
                       eps: float) -> Dict[str, Any]:
    """IL VERDETTO di conto sulla posizione di UN bot, UNA funzione per tutti
    (seconda tappa W3a, 08/10): i tre bot (Mike, Omega, Safe) la chiamano dopo
    il loro controllo «gambe non ritrovate», e la chiama ``esposizione_fuori_bot.
    effetto_sui_bot`` (worker del green-up fuori bot, W2) per PREVEDERE cosa
    diranno i bot dopo una copertura: nessuna copia dell'aritmetica.

    Prima la parte DIREZIONALE (``verdetto_in_esposizione``); se i dati non
    bastano (abbinato senza prezzo medio, posizione del bot mista) l'aritmetica
    in SIZE di sempre: ``chiusa`` se non sopravvive niente, ``ridotta`` se
    sopravvive meno dell'atteso, altrimenti ``intera``. ``righe_altrui`` sono
    SOLO gli ordini dell'utente (sito e app): quelli di un ALTRO bot si tolgono
    prima (``SorveglianzaConto.separa_altrui``) e non entrano nemmeno in
    ``conto_size``."""
    righe_bot = list(righe_bot or [])
    righe_altrui = list(righe_altrui or [])
    esp = verdetto_in_esposizione(atteso=atteso, righe_bot=righe_bot,
                                  righe_altrui=righe_altrui, eps=eps,
                                  conto_size=conto_size)
    if esp is not None:
        return dict(esp)
    vivo = vivo_in_size(atteso, conto_size)
    if abs(vivo) <= eps:
        verdetto = "chiusa"
    elif abs(vivo) + eps < abs(atteso):
        verdetto = "ridotta"
    else:
        verdetto = "intera"
    return {"verdetto": verdetto, "vivo": vivo, "metro": "size"}


# ===========================================================================
# 08/10 (W3a, seconda tappa) - DI CHI E' UN ORDINE ALTRUI: utente o un ALTRO bot
# ===========================================================================
# Un ordine di un ALTRO bot sulla stessa selezione (Omega su una selezione di
# Mike, due varianti della Safe sulla stessa partita) NON e' un intervento
# dell'utente: non deve fermare il bot ne' entrare nel verdetto come «altrui».
# La classificazione e' quella del cantiere W2, nessuna regola nuova:
#   1. riferimenti dell'ordine (``esposizione_fuori_bot.motivo_bot_da_riferimenti``:
#      ``customerStrategyRef`` diverso da assente/'live', ``customerOrderRef`` con
#      il prefisso di un bot), senza DB;
#   2. poi il DB per i soli ``bet_id`` mai visti (``esposizione_fuori_bot.
#      proprietari_bot``: tabelle dei bot, specchio, riga della coda del runner
#      con ``motivo_bot_da_coda``), letto dal bot con ``db.proprietari_bot_conto``.
# Esiti in memoria per (modo, bet_id): una lettura per bet_id nuovo, fuori dal
# percorso degli ordini (la fa la sorveglianza del conto, non il piazzamento).
# DB illeggibile: l'ordine resta IGNOTO -> nessun verdetto «chiuso dall'utente»
# al buio; il bot mette la selezione IN VERIFICA e non piazza ordini nuovi su
# quella partita finche' non sa (come W3b, ``ConfermaBot``). Una lettura fallita
# si ritenta dopo ``RIPROVA_PROPRIETARI_S``.
RIPROVA_PROPRIETARI_S = 30.0
MAX_PROPRIETARI = 5000
#: l'esito "dell'utente" nella memoria dei proprietari (stringa vuota: nessun bot)
_DELL_UTENTE = ""


def _motivo_da_riferimenti(r: Dict[str, Any], prefissi: Tuple[str, ...]) -> Optional[str]:
    """La prima cernita di W2 su una riga NORMALIZZATA (snake_case) o camelCase."""
    from .trading.esposizione_fuori_bot import motivo_bot_da_riferimenti

    csr = r.get("customer_strategy_ref", r.get("customerStrategyRef"))
    cor = r.get("customer_order_ref", r.get("customerOrderRef"))
    return motivo_bot_da_riferimenti({"customerStrategyRef": csr, "customerOrderRef": cor},
                                     prefissi)


class ProprietariConto:
    """La memoria «di chi e' questo ordine» di UN bot: (modo, bet_id) ->
    motivo del bot o utente. Mai un'eccezione verso chi chiede."""

    def __init__(self, *, riprova_s: float = RIPROVA_PROPRIETARI_S,
                 orologio: Callable[[], float] = time.monotonic,
                 max_esiti: int = MAX_PROPRIETARI) -> None:
        self._riprova_s = float(riprova_s)
        self._orologio = orologio
        self._max = int(max_esiti)
        self._esiti: Dict[Tuple[str, str], str] = {}
        self._errori: Dict[Tuple[str, str], Tuple[str, float]] = {}
        self._prefissi: Optional[Tuple[str, ...]] = None
        self._lock = threading.Lock()
        self.letture = 0

    def _pref(self) -> Tuple[str, ...]:
        if self._prefissi is None:
            from .trading.esposizione_fuori_bot import prefissi_ref_bot

            self._prefissi = tuple(prefissi_ref_bot())
        return self._prefissi

    def classifica(self, righe: Iterable[Dict[str, Any]], *,
                   leggi: Optional[Callable[[List[str], str], Any]],
                   modo: str = MODO_LIVE) -> Dict[str, Any]:
        """Le righe NON del bot (gia' separate dalle sue) divise in ``tenute``
        (dell'utente, piu' quelle senza abbinato che non spostano il verdetto),
        ``altri_bot`` ([{bet_id, motivo}]) e ``ignoti`` ([bet_id]: DB
        illeggibile). ``leggi=None``: il bot non ha la lettura del DB (finto di
        un test): contano i soli riferimenti, come prima del 08/10."""
        tenute: List[Dict[str, Any]] = []
        altri: List[Dict[str, str]] = []
        da_leggere: List[Tuple[Dict[str, Any], str]] = []
        modo = str(modo or MODO_LIVE)
        for r in righe or []:
            if not isinstance(r, dict):
                continue
            if _abbinato_riga(r) <= 0:
                tenute.append(r)              # niente abbinato: non sposta niente
                continue
            bid = str(r.get("bet_id") or r.get("betId") or "").strip()
            try:
                motivo = _motivo_da_riferimenti(r, self._pref())
            except Exception:  # noqa: BLE001 - regole non caricabili: si va al DB
                motivo = None
            if motivo:
                altri.append({"bet_id": bid, "motivo": motivo})
                continue
            if not bid or leggi is None:
                tenute.append(r)
                continue
            with self._lock:
                esito = self._esiti.get((modo, bid))
            if esito is None:
                da_leggere.append((r, bid))
            elif esito:
                altri.append({"bet_id": bid, "motivo": esito})
            else:
                tenute.append(r)
        errore: Optional[str] = None
        if da_leggere:
            ora = self._orologio()
            with self._lock:
                nuovi = sorted({b for _r, b in da_leggere
                                if not ((modo, b) in self._errori
                                        and ora - self._errori[(modo, b)][1]
                                        < self._riprova_s)})
            if nuovi:
                try:
                    self.letture += 1
                    dei_bot = leggi(list(nuovi), modo)
                    if not isinstance(dei_bot, dict):
                        raise TypeError("lettura dei proprietari: risposta %s"
                                        % type(dei_bot).__name__)
                    with self._lock:
                        for b in nuovi:
                            m = dei_bot.get(b)
                            self._esiti[(modo, b)] = str(m) if m else _DELL_UTENTE
                            self._errori.pop((modo, b), None)
                        while len(self._esiti) > self._max:
                            self._esiti.pop(next(iter(self._esiti)))
                except Exception as ex:  # noqa: BLE001 - DB illeggibile: nessun esito
                    with self._lock:
                        for b in nuovi:
                            self._errori[(modo, b)] = (str(ex)[:200] or type(ex).__name__,
                                                       ora)
        ignoti: List[str] = []
        for r, bid in da_leggere:
            with self._lock:
                esito = self._esiti.get((modo, bid))
                err = self._errori.get((modo, bid))
            if esito is None:
                ignoti.append(bid)
                if err is not None and errore is None:
                    errore = err[0]
            elif esito:
                altri.append({"bet_id": bid, "motivo": esito})
            else:
                tenute.append(r)
        return {"tenute": tenute, "altri_bot": altri, "ignoti": sorted(set(ignoti)),
                "errore": errore}

    def azzera(self) -> bool:
        with self._lock:
            c_era = bool(self._esiti or self._errori)
            self._esiti.clear()
            self._errori.clear()
            return c_era

    def stato(self) -> Dict[str, Any]:
        with self._lock:
            return {"esiti": len(self._esiti), "errori": len(self._errori),
                    "letture": self.letture}


def lettore_proprietari(db: Any) -> Optional[Callable[[List[str], str], Any]]:
    """La lettura del DB «di chi sono questi bet_id» del bot
    (``db.proprietari_bot_conto(bet_ids, modo)``, stessa firma nei tre
    moduli di produzione), o ``None`` se il ``db`` non la espone."""
    fn = getattr(db, "proprietari_bot_conto", None)
    return fn if callable(fn) else None


def con_ref_del_bot(righe: Iterable[Dict[str, Any]],
                    ref_per_bet: Dict[str, str]) -> list:
    """Le righe normalizzate della fotografia PAPER con il ref del BOT al posto
    di quello del runner, per gli ordini che il bot riconosce per ``bet_id``
    (l'unica chiave che il bot e il runner hanno in comune: il ``bet_id`` lo
    scrive il runner e il bot lo salva sulla sua riga). Cosi' l'aritmetica del
    verdetto, che riconosce gli ordini del bot per ref, resta UNA."""
    out = []
    for r in righe or []:
        if not isinstance(r, dict):
            continue
        bid = str(r.get("bet_id") or "")
        if bid and bid in ref_per_bet:
            r = dict(r, customer_order_ref=ref_per_bet[bid])
        out.append(r)
    return out


# ===========================================================================
# 08/10 (W3a) - LA SORVEGLIANZA DEL CONTO DAL CANALE: UNA, PER TUTTI I BOT
# ===========================================================================
# Il meccanismo del 30/09 di Mike (``mike/service.py``), estratto senza
# cambiarlo perche' Omega e Safe lo usino con la LORO aritmetica di verdetto:
#   * la memoria delle fotografie e il client lettore (``canale``);
#   * le versioni gia' valutate per (chiave, mercato) (``visto``);
#   * la firma anti-ripetizione dell'ultimo segnale (``firma``): gli snap
#     ripetuti dello stream non rigenerano un segnale gia' giudicato;
#   * il segnale in attesa della conferma (``segnale``);
#   * la SVEGLIA del giro (08/10): una fotografia dal contenuto NUOVO su un
#     mercato che interessa al bot (``interessa``) alza ``sveglia``; il giro del
#     bot riparte invece di aspettare la sua cadenza.
# La DECISIONE resta del bot: in LIVE la conferma e' la REST della posizione di
# conto (mai una decisione dal solo canale, 30/09); in PAPER la fotografia E'
# il blotter del runner, cioe' la fonte di verita' del paper.
class SorveglianzaConto:
    """Lo stato di processo della sorveglianza del conto di UN bot."""

    def __init__(self, nome: str, env: str) -> None:
        self.nome = str(nome)
        self.env = str(env)
        self.canale: Dict[str, Any] = {"memoria": None, "client": None}
        #: "chiave|market_id" (o "chiave|paper|market_id") -> versione valutata
        self.visto: Dict[str, int] = {}
        #: chiave -> il segnale del canale in attesa della conferma
        self.segnale: Dict[str, Dict[str, Any]] = {}
        #: chiave -> la firma dell'ultimo segnale mandato alla conferma
        self.firma: Dict[str, tuple] = {}
        self.sveglia = threading.Event()
        self._interessa: Optional[Callable[[str, str], bool]] = None
        self._avvisi: list = []
        self.conti: Dict[str, int] = {"fotografie_cambiate": 0, "sveglie": 0}
        #: 08/10 (W3a, seconda tappa): di chi sono gli ordini altrui
        self.proprietari = ProprietariConto()
        #: evento -> {chiave della selezione: dettaglio} delle selezioni IN
        #: VERIFICA (ordine altrui di proprietario ignoto, DB illeggibile)
        self.verifica: Dict[str, Dict[str, Dict[str, Any]]] = {}

    # ------------------------------------------------------------ memoria
    def memoria(self) -> Any:
        return self.canale.get("memoria")

    def installa(self, memoria: Any) -> None:
        """La memoria delle fotografie (``MemoriaConto``), o ``None`` per
        toglierla. Svuota versioni, segnali e firme (come Mike dal 30/09)."""
        self.canale["memoria"] = memoria
        self.visto.clear()
        self.segnale.clear()
        self.firma.clear()
        self.sveglia.clear()
        if memoria is not None and hasattr(memoria, "avvisa"):
            memoria.avvisa = self._su_fotografia

    # ------------------------------------------------------------- sveglia
    def interessa(self, fn: Optional[Callable[[str, str], bool]]) -> None:
        """``fn(market_id, modo)``: questo mercato interessa al bot ADESSO?
        (deve rispondere dalla SOLA memoria: una sveglia che costa una lettura
        e' il contrario di una sveglia)."""
        self._interessa = fn

    def su_sveglia(self, cb: Callable[[str, str], None]) -> None:
        """Un'azione in piu' a ogni sveglia (es. ``Sveglia.alza`` del bot)."""
        if cb not in self._avvisi:
            self._avvisi.append(cb)

    def _su_fotografia(self, market_id: str, modo: str) -> None:
        self.conti["fotografie_cambiate"] += 1
        fn = self._interessa
        try:
            ok = True if fn is None else bool(fn(str(market_id), str(modo)))
        except Exception:  # noqa: BLE001 - nel dubbio non si sveglia
            ok = False
        if not ok:
            return
        self.conti["sveglie"] += 1
        self.sveglia.set()
        for cb in list(self._avvisi):
            try:
                cb(str(market_id), str(modo))
            except Exception:  # noqa: BLE001 - svegliare non ferma il client
                pass

    def sveglia_alzata(self) -> bool:
        """La sveglia e' alzata? (e la si consuma)."""
        if self.sveglia.is_set():
            self.sveglia.clear()
            return True
        return False

    def dormi(self, pausa: float, *, minimo_s: float = 1.0,
              dormi: Callable[[float], None] = time.sleep,
              adesso: Callable[[], float] = time.monotonic) -> bool:
        """``time.sleep(pausa)`` che si interrompe alla sveglia del conto, ma
        MAI prima di ``minimo_s`` dall'inizio della dormita (il pavimento: una
        raffica di fotografie non fa girare il bot a vuoto). ``True`` se
        svegliato prima della cadenza."""
        pausa = max(0.0, float(pausa))
        inizio = adesso()
        if not self.sveglia.wait(pausa):
            return False
        self.sveglia.clear()
        resto = min(float(minimo_s), pausa) - (adesso() - inizio)
        if resto > 0:
            dormi(resto)
        return True

    # -------------------------------------------------------------- client
    def acceso(self) -> bool:
        """ACCESO di serie (regola dell'utente del 25/09: i canali al
        millisecondo sono la via principale); ``<ENV>=0`` lo spegne."""
        grezzo = (os.environ.get(self.env) or "").strip().lower()
        return grezzo not in ("0", "false", "no", "off")

    def avvia(self, *, etichetta: Optional[str] = None,
              topic: str = TOPIC_CONTO, porte: Optional[Iterable[int]] = None) -> bool:
        """Accende il lettore sul canale del runner calcio (stessa porta degli
        esiti: ``LIVE_LOCAL_WS_PORT`` o 47331). Non solleva MAI: senza
        ``websockets`` o senza runner resta la REST a cadenza, come prima.
        ``porte`` (08/10): piu' runner (calcio e tennis) nella STESSA memoria
        (i market_id non si ripetono fra sport); il primo client resta in
        ``canale['client']``, tutti in ``canale['clienti']``."""
        tag = etichetta or "[%s]" % self.nome
        if not self.acceso():
            logger.info("%s conto dal canale SPENTO (%s=%s): chiusure dell'utente "
                        "viste dalla REST alla cadenza.", tag, self.env,
                        (os.environ.get(self.env) or "").strip().lower())
            return False
        if self.canale.get("client") is not None:
            return True
        try:
            import websockets  # noqa: F401  - solo per sapere se c'e'

            memoria = MemoriaConto()
            lista = list(porte) if porte is not None else [None]
            clienti = [ClientEsiti(memoria, topic=topic, porta_ws=p) for p in lista]
            self.installa(memoria)
            self.canale["client"] = clienti[0]
            self.canale["clienti"] = clienti
            for client in clienti:
                client.avvia()
                logger.info("%s posizione di conto dallo stream ordini del runner: %s "
                            "(la REST resta la conferma e il ripiego)", tag, client.url)
            return True
        except Exception as ex:  # noqa: BLE001 - il canale e' un'accelerazione
            logger.warning("%s conto dal canale NON avviato (%s): chiusure dell'utente "
                           "viste dalla REST alla cadenza.", tag, str(ex)[:160])
            return False

    def attivo(self) -> bool:
        return self.memoria() is not None

    # ---------------------------------------------------------- fotografie
    def fotografie(self, chiave: str, market_ids: Iterable[Any], *,
                   modo: str = MODO_LIVE) -> Tuple[Dict[str, Dict[str, Any]], bool]:
        """Le fotografie dei mercati dati nel ``modo`` chiesto e se almeno una
        e' NUOVA per ``chiave`` (versione mai valutata: la si timbra)."""
        mem = self.memoria()
        fotografie: Dict[str, Dict[str, Any]] = {}
        nuove = False
        if mem is None:
            return fotografie, False
        for mid in market_ids:
            mid = str(mid or "")
            if not mid or mid in fotografie:
                continue
            f = mem.mercato(mid, modo) if modo != MODO_LIVE else mem.mercato(mid)
            if f is None:
                continue
            fotografie[mid] = f
            k = ("%s|%s" % (chiave, mid) if modo == MODO_LIVE
                 else "%s|%s|%s" % (chiave, modo, mid))
            versione = int(f.get("versione") or 0)
            if versione > int(self.visto.get(k) or 0):
                nuove = True
                self.visto[k] = versione
        return fotografie, nuove

    def firma_ripetuta(self, chiave: str, firma: tuple) -> bool:
        """La stessa situazione gia' mandata alla conferma? (se no la si
        ricorda)."""
        if self.firma.get(chiave) == firma:
            return True
        self.firma[chiave] = firma
        return False

    def dimentica_firma(self, chiave: str) -> None:
        self.firma.pop(chiave, None)

    @staticmethod
    def tempi(fotografie: Dict[str, Dict[str, Any]]) -> Dict[str, Optional[int]]:
        """Gli istanti del segnale: arrivo al runner e publish di Betfair."""
        ricevuti = [f.get("ricevuto_ms") for f in fotografie.values()
                    if isinstance(f.get("ricevuto_ms"), (int, float))]
        pubblicati = [f.get("publish_time_ms") for f in fotografie.values()
                      if isinstance(f.get("publish_time_ms"), (int, float))]
        return {"ricevuto_ms": int(max(ricevuti)) if ricevuti else None,
                "publish_time_ms": int(max(pubblicati)) if pubblicati else None}

    @staticmethod
    def latenza_ms(now_ts: float, segnale: Dict[str, Any]) -> Dict[str, Optional[int]]:
        """Dal runner e da Betfair al verdetto, in millisecondi."""
        ora_ms = float(now_ts) * 1000.0
        ric = segnale.get("ricevuto_ms")
        pub = segnale.get("publish_time_ms")
        return {"dal_runner": (int(round(ora_ms - float(ric)))
                               if isinstance(ric, (int, float)) else None),
                "da_betfair": (int(round(ora_ms - float(pub)))
                               if isinstance(pub, (int, float)) else None)}

    # ------------------------------------------- ordini altrui e verifica
    def separa_altrui(self, righe: Iterable[Dict[str, Any]], *,
                      del_bot: Callable[[Dict[str, Any]], bool],
                      leggi: Optional[Callable[[List[str], str], Any]],
                      modo: str = MODO_LIVE) -> Dict[str, Any]:
        """Le righe di UNA selezione divise per il verdetto: ``bot`` (del bot,
        come le riconosce lui), ``altrui`` (SOLO dell'utente, piu' le non
        abbinate), ``altri_bot`` (tolte: ordini di un ALTRO bot), ``ignoti``
        (proprietario non saputo: DB illeggibile) ed ``errore``."""
        proprie: List[Dict[str, Any]] = []
        altre: List[Dict[str, Any]] = []
        for r in righe or []:
            if not isinstance(r, dict):
                continue
            (proprie if del_bot(r) else altre).append(r)
        cls = self.proprietari.classifica(altre, leggi=leggi, modo=modo)
        return {"bot": proprie, "altrui": cls["tenute"], "altri_bot": cls["altri_bot"],
                "ignoti": cls["ignoti"], "errore": cls["errore"]}

    def metti_in_verifica(self, evento: Any, chiave: str, dettaglio: Dict[str, Any]) -> bool:
        """La selezione ``chiave`` dell'evento e' IN VERIFICA (nessun verdetto,
        nessun ordine nuovo). ``True`` se e' una notizia (prima non lo era)."""
        ev = str(evento or "")
        gia = self.verifica.setdefault(ev, {})
        nuova = str(chiave) not in gia
        gia[str(chiave)] = dict(dettaglio or {})
        return nuova

    def togli_verifica(self, evento: Any, chiave: Optional[str] = None) -> bool:
        """Fine della verifica della selezione (o di tutto l'evento con
        ``chiave=None``). ``True`` se c'era."""
        ev = str(evento or "")
        if ev not in self.verifica:
            return False
        if chiave is None:
            self.verifica.pop(ev, None)
            return True
        c_era = self.verifica[ev].pop(str(chiave), None) is not None
        if not self.verifica[ev]:
            self.verifica.pop(ev, None)
        return c_era

    def in_verifica(self, evento: Any) -> Dict[str, Dict[str, Any]]:
        return dict(self.verifica.get(str(evento or "")) or {})

    def eventi_in_verifica(self) -> set:
        return {e for e, d in self.verifica.items() if d}

    # --------------------------------------------------------------- stato
    def azzera(self) -> List[str]:
        """Memoria di PROCESSO (difetto 37 del catalogo): il banco riparte
        pulito. Torna i nomi di cio' che ha svuotato."""
        fatti: List[str] = []
        if self.proprietari.azzera():
            fatti.append("proprietari")
        for nome in ("visto", "segnale", "firma", "verifica"):
            d = getattr(self, nome)
            if d:
                d.clear()
                fatti.append(nome)
        self.sveglia.clear()
        mem = self.memoria()
        try:
            if mem is not None and mem.azzera():
                fatti.append("memoria")
        except Exception:  # noqa: BLE001 - mai far fallire un azzeramento
            pass
        return fatti

    def stato(self) -> Dict[str, Any]:
        client = self.canale.get("client")
        mem = self.memoria()
        return {"conti": dict(self.conti),
                "client": client.stato() if client is not None else None,
                "memoria": mem.stato() if mem is not None else None,
                "proprietari": self.proprietari.stato(),
                "in_verifica": sorted(self.eventi_in_verifica())}
