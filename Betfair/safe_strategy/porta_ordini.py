"""porta_ordini.py - la PORTA da cui un ordine di Safe esce verso Betfair.

Decisione dell'utente (24/09, audit ``AUDIT_STRADE_ORDINE_2026-09-24.md`` F5):
la strada UNICA verso gli ordini e' il runner dello sport (flumine nello stesso
processo). Il bot gli parla sul canale locale del runner (47331 calcio, 47332
tennis) con il PROTOCOLLO "COMANDO ORDINE"; il DB resta diario e ripiego.

Qui vive SOLO il trasporto (cambia il COME, mai cosa/quando/quanto si piazza):

* ``PortaOggi``   - il trasporto di oggi (coda DB del runner se il gate e'
  aperto, REST FOK altrimenti). NON e' a comandi: e' il corpo di
  ``execution.place`` / ``execution.annulla_su_betfair`` cosi' com'e', byte per
  byte. Esiste per dare un nome al ripiego e per i test di parita'.
* ``PortaCanale`` - client WebSocket PERSISTENTE su ``/comando/<attore>``,
  header ``X-Canale-Token``, ``ack`` entro ``max_eta_ms``, eventi ``order`` con
  numero di sequenza, ``da_seq`` alla riconnessione.

Interruttori (SPENTI di serie, regola ``canale_bot.acceso``):
``SAFE_ORDINI_VIA_CANALE`` (calcio, 47331, attore ``safe``) e
``SAFE_TENNIS_ORDINI_VIA_CANALE`` (tennis, 47332, attore ``safe_tennis``).
Spento -> ``porta_per_sport`` ritorna ``None`` e ``execution`` fa esattamente
cio' che fa oggi (nessun thread, nessuna porta aperta, nessuna chiamata in piu').

Regole money-critical (ognuna inchiodata da un test in
``tests/test_porta_ordini_f5_2026_09_24.py``):

1. Il ``ref`` e' DETERMINISTICO dalla riga (``safe-t<id>``): la stessa richiesta
   rimandata ha lo stesso ref e il runner la scarta come doppione.
2. Nessun ``ack`` entro ``max_eta_ms`` su una ``place`` = ESITO IGNOTO: nessun
   ripiego automatico (l'ordine potrebbe essere partito). Si decide per ref.
3. Ripiego automatico consentito SOLO per ``cancel`` (e per le chiusure SOLO se
   il canale era gia' giu' PRIMA dell'invio: decisione D5 dell'audit).
4. Il ``mode`` del comando e' quello della RIGA (``strategy_modes`` al momento
   della riserva), mai ereditato dal servizio.
5. Un evento ``order`` piu' vecchio (``seq`` minore) non sostituisce mai quello
   che c'e'; un esito terminale non torna indietro.
6. ``creato_ms`` e' un INTERO (``motore_ordini._intero`` rifiuta un float, anche
   un numero tondo): mai ``round(ms, 1)``.
7. ``strategy_ref`` e' SEMPRE l'attore che manda il comando (``safe`` calcio,
   ``safe_tennis`` tennis), mai una costante fissa: il motore rifiuta uno
   ``strategy_ref`` diverso dall'attore del percorso.
8. Le chiusure via canale portano ``time_in_force=FILL_OR_KILL`` e
   ``reduces_liability=True`` come la coda flumine (``execution.enqueue_place``);
   le fasi INTERMEDIE del place-and-trim (``parcheggiato``/``ridotto``, quando la
   sequenza arrivera' anche dal canale) non sono mai terminali.

Difetti trovati e corretti (24/09, dal referto del delegato che ha costruito la
porta di Omega, ``Betfair/omega/porta_ordini.py::adatta_comando``): i tre punti
6-8 sopra erano rotti (``creato_ms`` float -> ogni comando respinto,
``strategy_ref`` fisso a ``safe`` -> Safe tennis sempre rifiutato, chiusure
senza FOK/reduces_liability -> divergenti dalla coda).

Modulo PURO: nessun import di flumine, betfairlightweight, supabase o database.
``websockets`` entra solo dentro il thread del client (import pigro).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("safe.porta_ordini")

# ------------------------------------------------------------------ costanti
ENV_CANALE = "SAFE_ORDINI_VIA_CANALE"
ENV_CANALE_TENNIS = "SAFE_TENNIS_ORDINI_VIA_CANALE"
ENV_TOKEN = "LOCAL_CHANNEL_TOKEN"
#: stessi nomi d'ambiente dei due runner (runner.py / tennis_runner.py:1527)
ENV_PORTA_CALCIO = "LIVE_LOCAL_WS_PORT"
ENV_PORTA_TENNIS = "TENNIS_LOCAL_WS_PORT"
PORTA_CALCIO = 47331
PORTA_TENNIS = 47332
ATTORE_CALCIO = "safe"
ATTORE_TENNIS = "safe_tennis"
PREFISSO_COMANDO = "/comando/"
HEADER_TOKEN = "X-Canale-Token"
#: eta' massima di un comando (ms): oltre, il runner lo rifiuta
MAX_ETA_MS = 3000
REF_MAX = 32
TABELLA_ORIGINE = "safe_strategy_trades"
#: estensione del protocollo (coordinatore, 24/09): FILL_OR_KILL sul ``place``
FOK = "FILL_OR_KILL"

VALORI_ACCESI = frozenset({"1", "true", "si", "yes"})
AZIONI = frozenset({"place", "cancel", "replace", "greenup", "cashout_event", "cashout_all"})
MODI = ("paper", "live")
LATI = ("BACK", "LAY")
PERSISTENZE = ("LAPSE", "PERSIST")
#: fasi del protocollo (``motore_ordini.FASI``) PIU' le fasi INTERMEDIE del
#: place-and-trim (``trading/submin.py``: parcheggio al minimo non abbinabile,
#: poi ridotto sotto il minimo) quando quella sequenza arrivera' anche dal
#: canale (F4, punto di ripresa 1 dell'audit strade ordine): intermedie, MAI
#: terminali, non si scartano e non sostituiscono un esito.
FASI = frozenset({"inviato", "accettato_betfair", "rifiutato", "abbinato_parziale",
                  "abbinato", "annullato", "scaduto", "errore",
                  "parcheggiato", "ridotto"})
FASI_TERMINALI = frozenset({"rifiutato", "abbinato", "annullato", "scaduto", "errore"})

#: le chiavi della richiesta ``t="comando"``, TUTTE e sempre, in quest'ordine.
#: ``time_in_force``/``reduces_liability``: estensione del protocollo (24/09,
#: dal referto della porta di Omega) — le stesse due chiavi che la coda del
#: runner mette sulle chiusure (``execution.enqueue_place``).
CHIAVI_COMANDO = ("ref", "attore", "azione", "mode", "market_id", "selection_id", "side",
                  "price", "size", "persistence", "bet_id", "size_reduction", "new_price",
                  "strategy_ref", "creato_ms", "max_eta_ms", "origine",
                  "time_in_force", "reduces_liability")
CHIAVI_ACK = ("ref", "seq", "accettato", "motivo", "ricevuto_ms")
#: le chiavi che il protocollo AGGIUNGE alla riga dello specchio negli eventi
CHIAVI_EVENTO_EXTRA = ("ref", "seq", "fase", "esito_ms")
#: motivo di rifiuto per un ref gia' visto dal runner: NON e' un rifiuto
#: dell'ordine (il primo invio e' li'), si aspetta il suo esito
MOTIVO_REF_GIA_VISTO = "ref_gia_visto"

MAX_REF_IN_MEMORIA = 5000
_ATTESE_S = (0.5, 1.0, 2.0, 5.0)
_RECV_TIMEOUT_S = 1.0


def _ora_ms() -> int:
    """Orologio in millisecondi INTERO per ``creato_ms``.

    ``motore_ordini._intero`` (``Betfair/stream/motore_ordini.py``) rifiuta
    QUALSIASI float, anche uno che vale un numero tondo: ``isinstance(v, int)``
    e basta. Un ``round(..., 1)`` restava float sul JSON e ogni comando di
    Safe veniva respinto con ``parametri_invalidi: creato_ms non intero``
    (difetto trovato dal delegato che ha costruito la porta di Omega)."""
    return int(round(time.time() * 1000.0))


def acceso(nome_env: str) -> bool:
    """Interruttore acceso SOLO se scritto (``1``/``true``/``si``/``yes``)."""
    return (os.getenv(nome_env) or "").strip().lower() in VALORI_ACCESI


def token() -> Optional[str]:
    """Il token del canale: ``local_channel.token_canale()`` se esiste, altrimenti
    l'env ``LOCAL_CHANNEL_TOKEN``. ``None`` se vuoto: senza token il runner
    chiude la connessione, quindi la porta resta GIU' (fail-closed)."""
    try:
        from Betfair.stream import local_channel as _lc

        fn = getattr(_lc, "token_canale", None)
        if callable(fn):
            t = str(fn() or "").strip()
            if t:
                return t
    except Exception:  # noqa: BLE001 - modulo assente: si prova l'env
        pass
    t = (os.getenv(ENV_TOKEN) or "").strip()
    return t or None


def _porta_env(nome: str, default: int) -> int:
    grezza = (os.getenv(nome) or "").strip()
    if not grezza:
        return default
    try:
        return int(grezza)
    except ValueError:
        return default


# ------------------------------------------------------------------ i ref
#: F1 (25/09) - il ref di una riga TENNIS ha il prefisso dell'ATTORE tennis
#: (``ATTORE_TENNIS``), non piu' quello calcio: il motore del runner
#: (``motore_ordini.valida_comando``/``_dispatch``) rifiuta un customerOrderRef
#: che non inizia con ``f"{attore}-"`` (contratto scritto in ``motore_ordini``,
#: non modificabile qui), e Safe tennis manda i comandi con attore
#: ``safe_tennis`` (vedi ``ATTORE_TENNIS`` sopra). Prima di questo fix
#: ``ref_ordine`` tornava sempre ``safe-t<id>`` anche per il tennis: col canale
#: acceso (``SAFE_TENNIS_ORDINI_VIA_CANALE``) OGNI comando sarebbe stato
#: rifiutato dal motore (prefisso ``safe-`` != ``safe_tennis-`` richiesto).
PREFISSO_REF_CALCIO = "safe-t"
PREFISSO_REF_TENNIS = "safe_tennis-t"
#: prefisso LEGACY del tennis (prima del 25/09): le registrazioni gia' fatte
#: (replay/certificazione) hanno ordini piazzati con questo ref, mai riscritto.
PREFISSO_REF_TENNIS_LEGACY = "safe-t"


def prefisso_ref(sport: Any) -> str:
    """Il prefisso del ref per lo sport (``"tennis"`` o ``"calcio"``, di
    default calcio): l'UNICA forma che si scrive da oggi in poi (F1, 25/09)."""
    return PREFISSO_REF_TENNIS if str(sport) == "tennis" else PREFISSO_REF_CALCIO


def ref_ordine(trade_id: Any, sport: Any = "calcio") -> str:
    """Il ref DETERMINISTICO di una riga di ``safe_strategy_trades``.

    F1 (25/09) - UNIFICATO sul prefisso dell'ATTORE che manda il comando:
    calcio resta ``safe-t<id>`` (invariato, l'attore ``safe`` ha sempre
    scritto cosi'), tennis diventa ``safe_tennis-t<id>`` (prima era
    ``safe-t<id>``, identico al calcio: il motore del runner rifiutava ogni
    comando tennis via canale perche' il ref non iniziava per ``safe_tennis-``,
    il prefisso che l'attore ``safe_tennis`` impone). Il chiamante passa lo
    sport della riga (``"tennis"``/``"calcio"``, calcio di default per
    compatibilita' con chi non lo passa ancora)."""
    return (prefisso_ref(sport) + "%d" % int(trade_id))[:REF_MAX]


def ref_annullo(bet_id: Any, size_reduction: Optional[float] = None,
                attore: str = ATTORE_CALCIO) -> str:
    """Il ref di un ``cancel``: deterministico dal bet_id (e dalla riduzione,
    se parziale). Un secondo annullo identico e' un doppione per il runner.

    25/09 (F8): il prefisso e' quello dell'ATTORE che lo manda, come per il
    place (F1): il motore pretende ``f"{attore}-"`` e Safe tennis e' l'attore
    ``safe_tennis``. Prima ogni annullo di Safe tennis sul canale sarebbe stato
    rifiutato (``safe-c...`` non inizia per ``safe_tennis-``). Calcio invariato
    (``safe-c<bet_id>``)."""
    ref = "%s-c%s" % (str(attore or ATTORE_CALCIO), str(bet_id).strip())
    if size_reduction is not None:
        ref += "-%d" % int(round(float(size_reduction) * 100))
    return ref[:REF_MAX]


# ------------------------------------------------------------------ il comando
def costruisci_comando(*, ref: str, attore: str, azione: str, mode: str,
                       market_id: Any = None, selection_id: Any = None,
                       side: Optional[str] = None, price: Optional[float] = None,
                       size: Optional[float] = None, persistence: Optional[str] = None,
                       bet_id: Any = None, size_reduction: Optional[float] = None,
                       new_price: Optional[float] = None,
                       creato_ms: Optional[float] = None,
                       max_eta_ms: int = MAX_ETA_MS,
                       origine: Optional[Dict[str, Any]] = None,
                       time_in_force: Optional[str] = None,
                       reduces_liability: bool = False) -> Dict[str, Any]:
    """Il corpo ``d`` di un ``t="comando"``: TUTTE le chiavi del protocollo,
    sempre, ``None`` dove l'azione non le usa. Solleva ``ValueError`` su un
    valore fuori protocollo (nessun comando a sorpresa esce di qui).

    ``strategy_ref`` e' SEMPRE quello dell'attore che manda il comando (mai
    una costante fissa a "safe"): il motore del runner rifiuta un
    ``strategy_ref`` diverso dall'attore del percorso (``valida_comando``),
    e Safe calcio (attore ``safe``) e Safe tennis (attore ``safe_tennis``)
    sono due attori diversi sullo stesso protocollo.

    ``time_in_force``/``reduces_liability``: le due chiavi che la coda del
    runner mette gia' oggi sulle chiusure (``execution.enqueue_place``):
    FOK su OGNI ``place`` normale (paper e live, apertura e chiusura — la
    coda lo fa sempre, tranne ``place_submin``, che il canale non serve
    ancora), ``reduces_liability`` SOLO quando il place dichiara di ridurre
    una posizione (chiusura). Valgono solo per ``place``: su ogni altra
    azione restano ``None``/``False``, come fa ``motore_ordini.valida_comando``."""
    ref = str(ref or "")
    if not ref or len(ref) > REF_MAX:
        raise ValueError("ref non valido: %r" % ref)
    if azione not in AZIONI:
        raise ValueError("azione fuori protocollo: %r" % azione)
    if mode not in MODI:
        raise ValueError("mode fuori protocollo: %r" % mode)
    lato = None
    if side is not None:
        lato = str(side).upper()
        if lato not in LATI:
            raise ValueError("side fuori protocollo: %r" % side)
    if persistence is not None and persistence not in PERSISTENZE:
        raise ValueError("persistence fuori protocollo: %r" % persistence)
    if azione == "place" and (market_id is None or selection_id is None or lato is None
                              or price is None or size is None):
        raise ValueError("place senza mercato/selezione/lato/prezzo/size")
    if azione == "cancel" and not bet_id:
        raise ValueError("cancel senza bet_id")
    if time_in_force not in (None, FOK):
        raise ValueError("time_in_force fuori protocollo: %r" % time_in_force)
    if creato_ms is None:
        creato_intero = _ora_ms()
    else:
        if isinstance(creato_ms, bool) or not isinstance(creato_ms, (int, float)):
            raise ValueError("creato_ms non numerico: %r" % creato_ms)
        # il runner vuole un INTERO (``motore_ordini._intero``): un float resta
        # float sul JSON e viene rifiutato anche se vale un numero tondo.
        creato_intero = int(round(float(creato_ms)))
    return {
        "ref": ref,
        "attore": str(attore),
        "azione": azione,
        "mode": mode,
        "market_id": (str(market_id) if market_id is not None else None),
        "selection_id": (int(selection_id) if selection_id is not None else None),
        "side": lato,
        "price": (float(price) if price is not None else None),
        "size": (float(size) if size is not None else None),
        "persistence": persistence,
        "bet_id": (str(bet_id) if bet_id else None),
        "size_reduction": (float(size_reduction) if size_reduction is not None else None),
        "new_price": (float(new_price) if new_price is not None else None),
        "strategy_ref": str(attore),
        "creato_ms": creato_intero,
        "max_eta_ms": int(max_eta_ms),
        "origine": dict(origine) if origine else None,
        "time_in_force": (time_in_force if azione == "place" else None),
        "reduces_liability": (bool(reduces_liability) if azione == "place" else False),
    }


def busta(t: str, d: Dict[str, Any]) -> str:
    """La busta del protocollo: ``{"t":..., "d":{...}}``."""
    return json.dumps({"t": t, "d": d}, separators=(",", ":"))


# ------------------------------------------------------------------ l'ack
@dataclass(frozen=True)
class Ack:
    """Risposta del runner a un comando.

    ``inviato`` False = il comando NON e' mai uscito (canale giu' prima).
    ``arrivato`` False con ``inviato`` True = ESITO IGNOTO (nessun ack entro
    ``max_eta_ms``): per una ``place`` MAI ripiego automatico."""

    ref: str
    seq: Optional[int]
    accettato: bool
    motivo: Optional[str]
    ricevuto_ms: Optional[float]
    inviato: bool = True
    arrivato: bool = True

    @property
    def esito_ignoto(self) -> bool:
        return self.inviato and not self.arrivato

    @classmethod
    def non_inviato(cls, ref: str, motivo: str) -> "Ack":
        return cls(ref, None, False, motivo, None, inviato=False, arrivato=False)

    @classmethod
    def senza_risposta(cls, ref: str) -> "Ack":
        return cls(ref, None, False, "nessun_ack", None, inviato=True, arrivato=False)

    @classmethod
    def da_busta(cls, d: Dict[str, Any]) -> "Ack":
        seq = d.get("seq")
        return cls(str(d.get("ref") or ""),
                   int(seq) if isinstance(seq, int) and not isinstance(seq, bool) else None,
                   bool(d.get("accettato") is True),
                   (str(d.get("motivo")) if d.get("motivo") is not None else None),
                   d.get("ricevuto_ms"))


def _seq_di(d: Any) -> Optional[int]:
    if not isinstance(d, dict):
        return None
    s = d.get("seq")
    if isinstance(s, bool) or not isinstance(s, int):
        return None
    return s


def terminale(evento: Any) -> bool:
    return isinstance(evento, dict) and str(evento.get("fase") or "") in FASI_TERMINALI


# ------------------------------------------------------------------ la memoria
class MemoriaComandi:
    """Ack ed eventi ``order`` ricevuti, per ref (e per bet_id).

    Thread-safe: scrive il thread del client, legge il thread del bot.
    ``seq_visto`` = il piu' alto ``seq`` CONTIGUO ricevuto: e' quello che si
    chiede di nuovo con ``da_seq`` alla riconnessione o su un buco."""

    def __init__(self, max_ref: int = MAX_REF_IN_MEMORIA) -> None:
        self._cond = threading.Condition()
        self._ack: Dict[str, Ack] = {}
        self._eventi: Dict[str, Dict[str, Any]] = {}
        self._per_bet: Dict[str, Dict[str, Any]] = {}
        self._max = max(1, int(max_ref))
        self.seq_visto = 0
        self._sopra: set = set()
        self.buchi = 0
        #: risposte ``da_seq`` con ``completo`` False (buco NON colmabile)
        self.buchi_non_colmati = 0
        self.conti: Dict[str, int] = {"ack": 0, "eventi": 0, "vecchi": 0, "scartati": 0}

    def _avanza_seq(self, seq: Optional[int]) -> bool:
        """Registra ``seq``; True se ha aperto un BUCO (c'e' un seq mancante).

        25/09 (banco F4, reperto): il motore numera per attore a partire
        dall'istante del suo avvio (``motore_ordini._base_seq`` = epoch in ms),
        quindi il PRIMO seq che il client vede vale ~1,7e12 e non 1. Senza una
        base, ``seq_visto`` restava 0 per sempre: OGNI evento ``order`` apriva
        un "buco", chiedeva ``da_seq`` dal seq 0, il motore rimandava tutta la
        memoria (fino a 500 messaggi) e ognuno di quelli chiedeva un altro
        ``da_seq``: una tempesta alla prima accensione. Il primo seq visto
        (memoria vuota) e' la BASE: la contiguita' parte da li'."""
        if seq is None:
            return False
        if self.seq_visto == 0 and not self._sopra:
            self.seq_visto = seq - 1          # primo contatto: la base
        if seq <= self.seq_visto:
            return False
        self._sopra.add(seq)
        while (self.seq_visto + 1) in self._sopra:
            self.seq_visto += 1
            self._sopra.discard(self.seq_visto)
        if self._sopra:
            self.buchi += 1
            return True
        return False

    def ricevi_ack(self, d: Any) -> bool:
        if not isinstance(d, dict) or not d.get("ref"):
            self.conti["scartati"] += 1
            return False
        ack = Ack.da_busta(d)
        with self._cond:
            self._ack[ack.ref] = ack
            self._avanza_seq(ack.seq)
            self.conti["ack"] += 1
            self._pota(self._ack)
            self._cond.notify_all()
        return True

    def ricevi_evento(self, d: Any) -> Optional[bool]:
        """Un evento ``order``. True = entrato; False = scartato/vecchio;
        ritorna anche se ha aperto un buco di sequenza (``self.ultimo_buco``)."""
        self.ultimo_buco = False
        if not isinstance(d, dict) or not d.get("ref") or _seq_di(d) is None:
            self.conti["scartati"] += 1
            return False
        ref = str(d["ref"])
        seq = int(d["seq"])
        with self._cond:
            self.ultimo_buco = self._avanza_seq(seq)
            prima = self._eventi.get(ref)
            if prima is not None:
                if seq <= int(prima["seq"]) or (terminale(prima) and not terminale(d)):
                    self.conti["vecchi"] += 1
                    return False
            copia = dict(d)
            self._eventi.pop(ref, None)
            self._eventi[ref] = copia
            bet = copia.get("bet_id")
            if bet:
                self._per_bet[str(bet)] = copia
                self._pota(self._per_bet)
            self._pota(self._eventi)
            self.conti["eventi"] += 1
            self._cond.notify_all()
        return True

    def chiudi_da_seq(self, d: Any) -> bool:
        """La risposta ``t="da_seq"`` del motore (``{dal, fino_a, inviati,
        completo}``): i messaggi rimandati sono gia' arrivati PRIMA di questa
        risposta (stesso socket, in ordine), quindi fino a ``fino_a`` non c'e'
        piu' niente da chiedere. Se il motore non li aveva piu' tutti
        (``completo`` False: riavvio del runner, memoria di 500 superata) il
        buco non si puo' colmare: si RIPARTE da ``fino_a`` e si conta, e le
        righe si riallineano per ref (``_risolvi_via_canale`` -> Betfair)."""
        if not isinstance(d, dict):
            return False
        fino = d.get("fino_a")
        if isinstance(fino, bool) or not isinstance(fino, int):
            return False
        with self._cond:
            if d.get("completo") is False and fino > self.seq_visto:
                self.buchi_non_colmati += 1
            if fino > self.seq_visto:
                self.seq_visto = fino
            self._sopra = {s for s in self._sopra if s > self.seq_visto}
            while (self.seq_visto + 1) in self._sopra:
                self.seq_visto += 1
                self._sopra.discard(self.seq_visto)
            self._cond.notify_all()
        return True

    def _pota(self, d: Dict[str, Any]) -> None:
        while len(d) > self._max:
            d.pop(next(iter(d)))

    def ack(self, ref: str) -> Optional[Ack]:
        with self._cond:
            return self._ack.get(str(ref))

    def esito(self, ref: str) -> Optional[Dict[str, Any]]:
        with self._cond:
            e = self._eventi.get(str(ref))
            return dict(e) if e is not None else None

    def esito_per_bet(self, bet_id: str) -> Optional[Dict[str, Any]]:
        with self._cond:
            e = self._per_bet.get(str(bet_id))
            return dict(e) if e is not None else None

    def attendi(self, pred: Callable[[], Any], timeout_s: float) -> Any:
        """Aspetta finche' ``pred()`` (chiamato col lucchetto) e' vero."""
        fine = time.monotonic() + max(0.0, float(timeout_s))
        with self._cond:
            while True:
                v = pred()
                if v:
                    return v
                resto = fine - time.monotonic()
                if resto <= 0:
                    return None
                self._cond.wait(resto)

    def attendi_ack(self, ref: str, timeout_s: float) -> Optional[Ack]:
        return self.attendi(lambda: self._ack.get(str(ref)), timeout_s)


# ------------------------------------------------------------------ le porte
class PortaOggi:
    """Il trasporto di OGGI: coda DB del runner se il gate e' aperto, REST FOK
    altrimenti. Non e' a comandi: e' il corpo di ``execution.place`` e di
    ``execution.annulla_su_betfair`` cosi' com'e'. ``via_canale`` False fa si'
    che ``execution`` non tocchi una riga del percorso di sempre."""

    via_canale = False
    nome = "oggi"

    def disponibile(self) -> bool:
        return True

    def invia(self, comando: Dict[str, Any]) -> Ack:
        return Ack.non_inviato(str(comando.get("ref") or ""), "porta_oggi_senza_comandi")

    def esiti(self, ref: str) -> Optional[Dict[str, Any]]:
        return None


def _connetti_ws(url: str, headers: Dict[str, str]) -> Any:
    """Client WebSocket sincrono. Import PIGRO: senza ``websockets`` il modulo
    resta importabile e la porta resta giu' (si lavora come oggi)."""
    from websockets.sync.client import connect

    return connect(url, additional_headers=headers, open_timeout=5.0,
                   close_timeout=1.0, max_queue=256)


class PortaCanale:
    """Client PERSISTENTE del canale di comando del runner (``/comando/<attore>``).

    Un thread daemon tiene la connessione, riceve ``ack`` e ``order`` e li mette
    in ``memoria``; alla (ri)connessione chiede ``da_seq`` dal piu' alto seq
    contiguo visto. ``invia`` gira sul thread del bot: scrive il comando e
    aspetta l'ack al massimo ``max_eta_ms``. Non solleva mai verso il bot."""

    via_canale = True
    nome = "canale"

    def __init__(self, *, porta_ws: int, attore: str, sport: str = "calcio",
                 host: str = "127.0.0.1",
                 connetti: Optional[Callable[[str, Dict[str, str]], Any]] = None,
                 token_fn: Callable[[], Optional[str]] = token,
                 memoria: Optional[MemoriaComandi] = None) -> None:
        self.porta_ws = int(porta_ws)
        self.attore = str(attore)
        self.sport = str(sport)
        self.host = host
        self._connetti = connetti or _connetti_ws
        self._token_fn = token_fn
        self.memoria = memoria or MemoriaComandi()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._ws: Any = None
        self._invio = threading.Lock()
        self.collegato = False
        self.connessioni = 0
        self.riagganci = 0
        self.errori = 0
        self.ultimo_errore: Optional[str] = None
        self.richieste_da_seq = 0
        self._da_seq_in_corso = False
        self._detto = False

    @property
    def url(self) -> str:
        return "ws://%s:%d%s%s" % (self.host, self.porta_ws, PREFISSO_COMANDO, self.attore)

    # -- ciclo di vita -----------------------------------------------------
    def avvia(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._gira, daemon=True,
                                        name="safe-porta-%s" % self.attore)
        self._thread.start()

    def ferma(self) -> None:
        self._stop.set()
        ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except Exception:  # noqa: BLE001
                pass

    def disponibile(self) -> bool:
        return bool(self.collegato and self._ws is not None)

    def stato(self) -> Dict[str, Any]:
        return {"collegato": self.collegato, "connessioni": self.connessioni,
                "riagganci": self.riagganci, "errori": self.errori,
                "ultimo_errore": self.ultimo_errore, "url": self.url,
                "seq_visto": self.memoria.seq_visto, "buchi": self.memoria.buchi,
                "richieste_da_seq": self.richieste_da_seq,
                "memoria": dict(self.memoria.conti)}

    def _gira(self) -> None:
        i = 0
        while not self._stop.is_set():
            prima = self.connessioni
            try:
                self.collega_una_volta()
            except Exception as ex:  # noqa: BLE001 - il bot vive senza canale
                self.errori += 1
                self.ultimo_errore = str(ex)[:200]
                if not self._detto:
                    self._detto = True
                    logger.warning("[safe.porta] canale di comando %s non disponibile (%s)",
                                   self.url, str(ex)[:120])
            if self._stop.is_set():
                break
            if self.connessioni > prima:
                i = 0                   # era collegato: si riparte dall'attesa breve
            self.riagganci += 1
            self._stop.wait(_ATTESE_S[min(i, len(_ATTESE_S) - 1)])
            i += 1

    def collega_una_volta(self) -> None:
        """Una connessione intera: aggancio, ``da_seq``, ricezione fino alla
        caduta. Esposta per i test (nessun thread necessario)."""
        tok = self._token_fn() if self._token_fn is not None else None
        if not tok:
            raise RuntimeError("token del canale assente: porta giu' (fail-closed)")
        with self._connetti(self.url, {HEADER_TOKEN: tok}) as ws:
            self._ws = ws
            self.collegato = True
            self.connessioni += 1
            self._detto = False
            self._da_seq_in_corso = False   # socket nuovo: nessuna richiesta in volo
            try:
                if self.memoria.seq_visto > 0:
                    self._chiedi_da_seq()
                while not self._stop.is_set():
                    try:
                        grezzo = ws.recv(timeout=_RECV_TIMEOUT_S)
                    except TimeoutError:
                        continue
                    self.incassa(grezzo)
            finally:
                self.collegato = False
                self._ws = None

    def _chiedi_da_seq(self) -> None:
        """UNA richiesta alla volta (25/09): finche' il motore non ha risposto
        (``t="da_seq"``) un altro buco non ne manda una seconda — i messaggi
        rimandati aprirebbero altri "buchi" e ognuno chiederebbe di nuovo."""
        ws = self._ws
        if ws is None or self._da_seq_in_corso:
            return
        self._da_seq_in_corso = True
        try:
            with self._invio:
                ws.send(busta("da_seq", {"seq": int(self.memoria.seq_visto)}))
        except Exception:
            self._da_seq_in_corso = False
            raise
        self.richieste_da_seq += 1

    def incassa(self, grezzo: Any) -> bool:
        """Un messaggio del runner. NON SOLLEVA MAI."""
        try:
            msg = json.loads(grezzo) if isinstance(grezzo, (str, bytes, bytearray)) else grezzo
        except (ValueError, TypeError):
            return False
        if not isinstance(msg, dict):
            return False
        t = msg.get("t")
        d = msg.get("d")
        if t == "ack":
            return self.memoria.ricevi_ack(d)
        if t == "da_seq":
            self._da_seq_in_corso = False
            return self.memoria.chiudi_da_seq(d)
        if t == "order":
            entrato = bool(self.memoria.ricevi_evento(d))
            if getattr(self.memoria, "ultimo_buco", False):
                # un fotogramma perso: si richiede da dove si e' contigui
                try:
                    self._chiedi_da_seq()
                except Exception as ex:  # noqa: BLE001
                    self.errori += 1
                    self.ultimo_errore = str(ex)[:200]
            return entrato
        return False

    # -- comandi -----------------------------------------------------------
    def invia(self, comando: Dict[str, Any]) -> Ack:
        """Scrive il comando e aspetta l'ack al massimo ``max_eta_ms``."""
        ref = str(comando.get("ref") or "")
        ws = self._ws
        if not self.collegato or ws is None:
            return Ack.non_inviato(ref, "canale_giu")
        gia = self.memoria.ack(ref)
        try:
            with self._invio:
                ws.send(busta("comando", comando))
        except Exception as ex:  # noqa: BLE001 - uscito o no? NON si sa: ignoto
            self.errori += 1
            self.ultimo_errore = str(ex)[:200]
            return Ack.senza_risposta(ref)
        attesa_s = max(0.0, float(comando.get("max_eta_ms") or MAX_ETA_MS) / 1000.0)
        ack = self.memoria.attendi(
            lambda: (lambda a: a if a is not None and a is not gia else None)(
                self.memoria._ack.get(ref)), attesa_s)
        return ack if ack is not None else Ack.senza_risposta(ref)

    def esiti(self, ref: str) -> Optional[Dict[str, Any]]:
        return self.memoria.esito(ref)

    def attendi_esito_bet(self, bet_id: str, timeout_s: float) -> Optional[Dict[str, Any]]:
        """L'evento dell'ordine ``bet_id`` che dice che NON ha piu' residuo vivo
        (terminale, o residuo zero), entro ``timeout_s``."""
        def _pronto() -> Optional[Dict[str, Any]]:
            e = self.memoria._per_bet.get(str(bet_id))
            if e is None:
                return None
            try:
                residuo = float(e.get("size_remaining") or 0.0)
            except (TypeError, ValueError):
                residuo = 1.0
            return dict(e) if (terminale(e) or residuo <= 0.0) else None
        return self.memoria.attendi(_pronto, timeout_s)


# ------------------------------------------------------------------ registro
_PORTE: Dict[str, PortaCanale] = {}
_LOCK = threading.Lock()


def _config_di(sport: str) -> Optional[tuple]:
    if str(sport) == "tennis":
        if not acceso(ENV_CANALE_TENNIS):
            return None
        return ("tennis", _porta_env(ENV_PORTA_TENNIS, PORTA_TENNIS), ATTORE_TENNIS)
    if not acceso(ENV_CANALE):
        return None
    return ("calcio", _porta_env(ENV_PORTA_CALCIO, PORTA_CALCIO), ATTORE_CALCIO)


def porta_per_sport(sport: Any, *, avvia: bool = True) -> Optional[PortaCanale]:
    """La porta a comandi per lo sport, o ``None`` a interruttore SPENTO (=
    trasporto di oggi, nessuna chiamata diversa). Crea e avvia il client una
    volta sola per processo."""
    cfg = _config_di(str(sport or "calcio"))
    if cfg is None:
        return None
    chiave, porta_ws, attore = cfg
    with _LOCK:
        p = _PORTE.get(chiave)
        if p is None:
            p = PortaCanale(porta_ws=porta_ws, attore=attore, sport=chiave)
            _PORTE[chiave] = p
    if avvia:
        p.avvia()
    return p


def porta_esistente(sport: Any) -> Optional[PortaCanale]:
    """La porta gia' creata (anche se l'interruttore e' stato spento dopo),
    per leggere gli esiti delle righe gia' inviate. Mai ne crea una."""
    chiave = "tennis" if str(sport or "calcio") == "tennis" else "calcio"
    with _LOCK:
        return _PORTE.get(chiave)


def azzera() -> None:
    """Ferma e dimentica le porte. Per i test e per il riavvio."""
    with _LOCK:
        porte = list(_PORTE.values())
        _PORTE.clear()
    for p in porte:
        p.ferma()
