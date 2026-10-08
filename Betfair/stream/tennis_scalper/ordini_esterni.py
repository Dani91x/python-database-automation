# -*- coding: utf-8 -*-
"""ordini_esterni.py - i bot DENTRO flumine sanno SUBITO degli ordini esterni (W3b, 08/10/2026).

ORDINE DELL'UTENTE (08/10): "QUANDO INTERVENGO IO DA QUELLA PAGINA O DAL SITO O
MANUALMENTE SU UN OPERAZIONE DEI BOT, I BOT LO SANNO E NON FANNO ALTRO" e "I BOT
DEVONO ESSERE AGGIORNATI NEL MINOR TEMPO POSSIBILE".

Vale per i bot che sono STRATEGIE flumine: lo scalper calcio (maker, sniper,
theta, media under: ``scalper_session``, UN processo per partita con il suo
flumine) e i quattro bot tennis ospitati dal runner tennis (``tennis_runner``).
Fino a oggi leggevano l'esposizione SOLO dal blotter della propria strategia: un
ordine fatto dall'utente sul sito, o a mano dal ladder dell'app, sul mercato del
bot non lo vedeva nessuno (rischio di doppia copertura).

LE FONTI (nessuna chiamata Betfair in piu', nessun canale nuovo):
  * LIVE: lo STREAM ORDINI del conto che il flumine del processo GIA' riceve
    (iscrizione senza filtro di strategia: ``esiti_ordini_canale``, 30/09). Il
    processo monta lo STESSO osservatore del runner calcio
    (``esiti_ordini_canale.osserva_conto_su_flumine``) con una ``pubblica`` in
    memoria (``Registro.ricevi_conto``) invece del canale locale: la fotografia
    del mercato (``MemoriaConto``, la stessa classe) arriva al bot nel thread di
    flumine, subito dopo che flumine ha elaborato il messaggio dello stream.
  * PAPER: gli ordini manuali SIMULATI del ladder, letti nello stesso processo
    (tennis: ``session.tracked_orders`` della capture del runner). In prova il
    sito non esiste. Lo scalper calcio e' un processo SEPARATO dal runner calcio
    (``scalper_session``: login e flumine propri): in prova la sua fonte
    (``fonte_paper``) e' un'INTERFACCIA che il coordinatore collega (referto W3b).

LA REGOLA (una sola, per tutti):
  un ordine dell'UTENTE (sito: nessun ``customerStrategyRef``; app: il ref del
  terminale manuale dello sport) con ABBINATO nuovo su un MERCATO DEL BOT (quelli
  su cui il bot e' armato - tennis: il Match Odds della partita; scalper: i
  mercati della sessione - piu' ogni mercato dove il bot ha ordini) = intervento
  dell'utente. Il bot: annulla i suoi ordini vivi, si ferma
  (nessun ordine nuovo, nessuna copertura, nessun rientro su quella partita) e
  lo scrive. Gli ordini del bot stesso (bet_id del suo blotter, ref di flumine
  con l'hash della sua strategia, ``customerStrategyRef`` = suo nome) e quelli
  degli ALTRI bot (riconosciuti con la regola di W2,
  ``trading.esposizione_fuori_bot.motivo_bot_da_riferimenti``) NON lo sono.

LA LINEA DI BASE: un ordine dell'utente piazzato PRIMA dell'accensione del bot
conta solo per l'abbinato che cresce DOPO (l'immagine iniziale dello stream
porta anche gli ordini vecchi: non sono un intervento sul bot).

Modulo PURO: nessun import di flumine/betfairlightweight in testa, nessun I/O.
Codice ASCII-only, commenti in italiano.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

#: interruttore di processo: ACCESO di serie (come ``MIKE_CONTO_CANALE``);
#: ``0``/``false``/``no``/``off`` lo spegne = tutto identico a prima del 08/10
ENV = "BOT_ORDINI_ESTERNI"
_VALORI_SPENTI = frozenset({"0", "false", "no", "off"})

#: ``customerStrategyRef`` del terminale manuale dell'app (stessi valori di
#: ``live_order_worker.CUSTOMER_STRATEGY_REF`` e
#: ``tennis_live_order_worker.CUSTOMER_STRATEGY_REF``: un test di contratto li
#: confronta, qui non si importano i worker)
RIF_MANUALE_CALCIO = "live"
RIF_MANUALE_TENNIS = "tennis"

PROPRIO = "proprio"
BOT = "bot"
UTENTE = "utente"

FONTE_STREAM = "stream_ordini"
FONTE_PAPER = "ordini_manuali_simulati"

#: chiave dell'attivita' e del marcatore nelle stats della riga del bot
KIND = "intervento_utente"
#: abbinato nuovo minimo per dire "intervento" (mezzo centesimo: Betfair lavora
#: al centesimo, sotto e' rumore di arrotondamento)
EPS = 0.005

# --- SECONDO GIRO (08/10, coordinatore): la verifica "del bot / fuori bot" ---
#: esito della verifica sul DB per un ordine che NON e' di nessun bot
FUORI_BOT = "fuori_bot"
#: le attivita' della verifica (oltre a ``intervento_utente``)
KIND_VERIFICA = "ordine_esterno_in_verifica"
KIND_DI_UN_BOT = "ordine_esterno_di_un_bot"
KIND_NON_VERIFICABILE = "ordine_esterno_non_verificabile"
#: dopo una lettura del DB fallita si riprova al piu' ogni tanti secondi: il
#: "respiro" del database (30 s) che il progetto usa gia' come ripiego
RIPROVA_DB_S = 30.0
#: tetto della cache per bet_id (un processo vive giorni)
MAX_ESITI = 5000


def acceso() -> bool:
    """ACCESO salvo ``BOT_ORDINI_ESTERNI`` scritto a un valore di spegnimento."""
    return (os.getenv(ENV) or "").strip().lower() not in _VALORI_SPENTI


def _testo(v: Any) -> str:
    return str(v).strip() if v is not None else ""


def _num(v: Any) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def istante_ms(v: Any) -> Optional[int]:
    """ISO-8601 / ``datetime`` / epoch (s o ms) -> epoch ms. ``None`` se assente:
    mai inventato."""
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        x = float(v)
        return int(x if x > 1e11 else x * 1000.0)
    if isinstance(v, datetime):
        dt = v
    else:
        try:
            dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(round(dt.timestamp() * 1000.0))


# ---------------------------------------------------------------------------
# chi e' il bot (identita' per riconoscere i SUOI ordini)
# ---------------------------------------------------------------------------
class Identita:
    """Nomi (``customerStrategyRef`` = ``str(strategia)[:15]``, regola di
    ``flumine.markets.market.place_order``) e hash di flumine (prefisso del
    ``customerOrderRef``: ``order.customer_order_ref`` = name_hash + sep + id)
    delle strategie del bot."""

    __slots__ = ("nomi", "hash")

    def __init__(self, strategie: Iterable[Any]) -> None:
        nomi, hashes = set(), []
        for s in strategie:
            if s is None:
                continue
            nome = _testo(getattr(s, "name", None) or str(s))
            if nome:
                nomi.add(nome[:15].lower())
            h = _testo(getattr(s, "name_hash", None))
            if h:
                hashes.append(h)
        self.nomi = frozenset(nomi)
        self.hash = tuple(sorted(set(hashes)))


def prefissi_bot() -> Tuple[str, ...]:
    """I prefissi dei ref dei bot: la regola di W2 (nessuna copia)."""
    from ..trading.esposizione_fuori_bot import prefissi_ref_bot

    return prefissi_ref_bot()


def classifica(o: Dict[str, Any], *, identita: Identita, bet_ids_propri: Any,
               rif_manuali: Sequence[str], prefissi: Sequence[str]) -> str:
    """UN ordine del conto (camelCase, ``esiti_ordini_canale.ordine_del_conto``)
    -> ``proprio`` | ``bot`` | ``utente``.

    Nel dubbio NON e' dell'utente solo se un riferimento lo dice di un bot: un
    ordine senza riferimenti e' del SITO (Betfair non ne mette)."""
    bid = _testo(o.get("betId"))
    if bid and bid in bet_ids_propri:
        return PROPRIO
    cor = _testo(o.get("customerOrderRef"))
    if cor and any(cor.startswith(h) for h in identita.hash):
        return PROPRIO
    csr = _testo(o.get("customerStrategyRef"))
    if csr and csr[:15].lower() in identita.nomi:
        return PROPRIO
    from ..trading.esposizione_fuori_bot import motivo_bot_da_riferimenti

    manuali = {str(r).strip().lower() for r in rif_manuali}
    # il ref del terminale manuale dello sport vale "dell'utente" come il
    # ``live`` del calcio nella regola di W2: si passa come assente
    vista = dict(o)
    vista["customerStrategyRef"] = None if (csr and csr.lower() in manuali) else (csr or None)
    if motivo_bot_da_riferimenti(vista, tuple(prefissi)) is not None:
        return BOT
    return UTENTE


def dove(o: Dict[str, Any]) -> str:
    """Da dove viene un ordine dell'utente: ``sito`` (nessun riferimento di
    strategia) o ``app`` (il terminale manuale)."""
    return "sito" if not _testo(o.get("customerStrategyRef")) else "app"


# ---------------------------------------------------------------------------
# la sorveglianza di UN bot
# ---------------------------------------------------------------------------
class Sorveglianza:
    """Giudica le righe degli ordini (del conto in live, manuali simulati in
    paper) per UN bot e, al primo intervento dell'utente, chiama
    ``al_intervento(evento)`` UNA volta sola.

    ``modo`` e' la modalita' con cui il bot ESEGUE ('paper'|'live'): una
    sorveglianza live riceve solo lo stream del conto reale, una paper solo la
    fonte paper. Paper e live non si mescolano mai."""

    def __init__(self, *, nome: str, modo: str, rif_manuali: Sequence[str],
                 prefissi: Sequence[str], identita: Identita,
                 bet_ids_propri: Callable[[], Any],
                 mercati_del_bot: Callable[[], Any],
                 al_intervento: Callable[[Dict[str, Any]], None],
                 adesso_ms: Callable[[], int], inizio_ms: int,
                 fonte_paper: Optional[Callable[[], Iterable[Dict[str, Any]]]] = None,
                 conferma: Any = None,
                 su_evento: Optional[Callable[[str, Dict[str, Any]], None]] = None) -> None:
        m = _testo(modo).lower()
        if m not in ("paper", "live"):
            raise ValueError("modo %r: atteso 'paper' o 'live'" % (modo,))
        self.nome = str(nome)
        self.modo = m
        self.rif_manuali = tuple(rif_manuali)
        self.prefissi = tuple(prefissi)
        self.identita = identita
        self._bet_ids_propri = bet_ids_propri
        self._mercati_del_bot = mercati_del_bot
        self._al_intervento = al_intervento
        self._adesso_ms = adesso_ms
        self.inizio_ms = int(inizio_ms)
        self._fonte_paper = fonte_paper if m == "paper" else None
        self.intervento: Optional[Dict[str, Any]] = None
        # betId -> abbinato gia' noto all'accensione (linea di base)
        self._base: Dict[str, float] = {}
        self._mercati_visti: set = set()
        self._lock = threading.RLock()
        self.conti: Dict[str, int] = {"valutazioni": 0, PROPRIO: 0, BOT: 0, UTENTE: 0,
                                      "fuori_dal_bot": 0, "in_verifica": 0, "bot_dal_db": 0,
                                      "non_verificabili": 0}
        # SECONDO GIRO (08/10, coordinatore): la classificazione "del bot / fuori
        # bot" di W2 sul DB, fuori dal giro caldo (``ConfermaBot``). None = la
        # decisione dai soli riferimenti (solo test e fonti in-process esatte).
        self._conferma = conferma
        self._su_evento = su_evento
        # betId -> (riga, abbinato nuovo, fonte, ricevuto_ms, publish_time_ms, da_ms)
        self._attesa: Dict[str, Tuple[Dict[str, Any], float, str, Any, Any, int]] = {}
        # (market_id, selection_id) -> betId in verifica: SOSPENSIONE prudente
        self._sospese: Dict[Tuple[str, str], set] = {}
        self._detti_non_verificabili: set = set()
        self.verifiche: List[Dict[str, Any]] = []

    # ---------------------------------------------------------------- base
    def _abbinato_nuovo(self, o: Dict[str, Any]) -> float:
        bid = _testo(o.get("betId")) or _testo(o.get("customerOrderRef"))
        sm = _num(o.get("sizeMatched"))
        if not bid:
            return sm
        if bid not in self._base:
            pd = istante_ms(o.get("placedDate"))
            mid = _testo(o.get("marketId"))
            if pd is not None:
                vecchio = pd < self.inizio_ms
            else:
                # senza istante di piazzamento: e' "vecchio" solo se arriva con
                # la PRIMA fotografia del mercato (l'immagine iniziale)
                vecchio = mid not in self._mercati_visti
            self._base[bid] = sm if vecchio else 0.0
        return round(sm - self._base[bid], 2)

    # ------------------------------------------------------------ giudizio
    def valuta_righe(self, righe: Iterable[Dict[str, Any]], *, fonte: str,
                     ricevuto_ms: Optional[int] = None,
                     publish_time_ms: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Le righe di UNA fotografia. Torna l'evento d'intervento se scatta ORA."""
        if self.intervento is not None:
            return None
        with self._lock:
            if self.intervento is not None:
                return None
            self.conti["valutazioni"] += 1
            propri: Any = None
            mercati: Any = None
            mercati_foto = set()
            scatto: Optional[Tuple[Dict[str, Any], float]] = None
            da_chiedere: List[str] = []
            for o in righe or ():
                if not isinstance(o, dict):
                    continue
                mid = _testo(o.get("marketId"))
                mercati_foto.add(mid)
                if propri is None:
                    propri = set(self._bet_ids_propri() or ())
                classe = classifica(o, identita=self.identita, bet_ids_propri=propri,
                                    rif_manuali=self.rif_manuali, prefissi=self.prefissi)
                self.conti[classe] += 1
                if classe != UTENTE:
                    continue
                nuovo = self._abbinato_nuovo(o)
                if nuovo <= EPS:
                    continue
                if mercati is None:
                    mercati = {str(x) for x in (self._mercati_del_bot() or ())}
                if mid not in mercati:
                    # ordine dell'utente su un mercato dove il bot non opera
                    self.conti["fuori_dal_bot"] += 1
                    continue
                if self._conferma is None:
                    if scatto is None:
                        scatto = (o, nuovo)
                    continue
                # SECONDO GIRO: i riferimenti dicono "dell'utente", ma un bot che
                # piazza dalla coda DB del runner porta lo stesso ref del terminale
                # manuale: decide la classificazione di W2 sul DB (per bet_id, una
                # volta sola, fuori dal giro caldo). Intanto: SOSPENSIONE prudente
                bid = _testo(o.get("betId")) or _testo(o.get("customerOrderRef"))
                esito = self._conferma.esito(bid)
                if esito == FUORI_BOT:
                    if scatto is None:
                        scatto = (o, nuovo)
                    continue
                if esito is not None:
                    self.conti["bot_dal_db"] += 1
                    continue
                prima = self._attesa.get(bid)
                self._attesa[bid] = (dict(o), nuovo, fonte, ricevuto_ms, publish_time_ms,
                                     prima[5] if prima else int(self._adesso_ms()))
                if prima is None:
                    self.conti["in_verifica"] += 1
                    self._sospendi(bid, o, ricevuto_ms)
                da_chiedere.append(bid)
            self._mercati_visti.update(mercati_foto)
            if da_chiedere:
                self._conferma.chiedi(da_chiedere)
            if scatto is None:
                # esito gia' noto (cache, o verifica sincrona): si decide adesso
                return self.rivedi() if self._attesa else None
            return self._scatta(scatto[0], scatto[1], fonte, ricevuto_ms, publish_time_ms)

    # ------------------------------------------- SECONDO GIRO: la verifica sul DB
    def _evento(self, kind: str, payload: Dict[str, Any]) -> None:
        if self._su_evento is None:
            return
        try:
            self._su_evento(kind, dict(payload))
        except Exception:  # noqa: BLE001 - il diario non ferma niente
            pass

    def _sospendi(self, bid: str, o: Dict[str, Any], ricevuto_ms: Any) -> None:
        chiave = (_testo(o.get("marketId")), _testo(o.get("selectionId")))
        self._sospese.setdefault(chiave, set()).add(bid)
        self._evento(KIND_VERIFICA, {
            "bot": self.nome, "modo": self.modo, "market_id": chiave[0],
            "selection_id": o.get("selectionId"), "bet_id": bid, "dove": dove(o),
            "abbinato": _num(o.get("sizeMatched")), "ricevuto_ms": ricevuto_ms,
            "nota": ("ordine con i riferimenti del terminale manuale o del sito: si "
                     "verifica sul DB se e' di un bot; intanto nessun ordine nuovo del "
                     "bot su questa selezione")})

    def _rilascia(self, bid: str) -> None:
        for chiave in list(self._sospese):
            self._sospese[chiave].discard(bid)
            if not self._sospese[chiave]:
                del self._sospese[chiave]

    def sospesa(self, market_id: Any, selection_id: Any) -> bool:
        """La selezione ha un ordine esterno ancora in verifica? (il controllo di
        flumine rifiuta ogni ordine nuovo del bot su di lei)."""
        return bool(self._sospese.get((_testo(market_id), _testo(selection_id))))

    def in_verifica(self) -> int:
        return len(self._attesa)

    def rivedi(self) -> Optional[Dict[str, Any]]:
        """Gli ordini in verifica il cui esito e' arrivato (thread di flumine):
        fuori bot -> intervento; di un bot -> si riprende; DB illeggibile -> resta
        sospeso, lo si scrive (una volta) e si richiede piu' tardi."""
        if self.intervento is not None or not self._attesa or self._conferma is None:
            return self.intervento
        with self._lock:
            # DB illeggibile prima: si richiede (la conferma rilegge solo dopo
            # ``riprova_s``), poi si guarda cosa c'e'
            riprova = [b for b in self._attesa if self._conferma.esito(b) is None
                       and self._conferma.errore(b) is not None]
            if riprova:
                self._conferma.chiedi(riprova)
            for bid, (o, nuovo, fonte, ric, pub, da_ms) in list(self._attesa.items()):
                esito = self._conferma.esito(bid)
                if esito == FUORI_BOT:
                    self._attesa.pop(bid, None)
                    ev = self._scatta(o, nuovo, fonte, ric, pub)
                    ev["verifica"] = {"esito": FUORI_BOT, "in_verifica_dal_ms": da_ms,
                                      "verifica_ms": int(ev["deciso_ms"]) - int(da_ms)}
                    return ev
                if esito is not None:
                    self._attesa.pop(bid, None)
                    self._rilascia(bid)
                    ora = int(self._adesso_ms())
                    info = {"bot": self.nome, "bet_id": bid, "motivo": esito,
                            "market_id": _testo(o.get("marketId")),
                            "selection_id": o.get("selectionId"),
                            "ricevuto_ms": ric, "ripreso_ms": ora,
                            "latenza_ms": (ora - int(ric)) if isinstance(ric, (int, float))
                            else None}
                    self.verifiche.append(info)
                    self._evento(KIND_DI_UN_BOT, {**info, "nota": (
                        "l'ordine e' di un altro bot (classificazione di W2): nessun "
                        "intervento dell'utente, il bot riprende")})
                    continue
                errore = self._conferma.errore(bid)
                if errore is not None:
                    if bid not in self._detti_non_verificabili:
                        self._detti_non_verificabili.add(bid)
                        self.conti["non_verificabili"] += 1
                        self._evento(KIND_NON_VERIFICABILE, {
                            "bot": self.nome, "bet_id": bid, "errore": errore,
                            "market_id": _testo(o.get("marketId")),
                            "selection_id": o.get("selectionId"),
                            "nota": ("DB illeggibile: non si sa se l'ordine e' di un bot o "
                                     "dell'utente. Il bot resta SOSPESO su questa "
                                     "selezione (nessun ordine nuovo al buio) e "
                                     "riprova la lettura")})
        return self.intervento

    def _scatta(self, o: Dict[str, Any], nuovo: float, fonte: str,
                ricevuto_ms: Optional[int], publish_time_ms: Optional[int]) -> Dict[str, Any]:
        deciso = int(self._adesso_ms())
        evento = {
            "come": "ordine_esterno_abbinato", "dove": dove(o), "modo": self.modo,
            "fonte": fonte, "bot": self.nome,
            "market_id": _testo(o.get("marketId")),
            "selection_id": o.get("selectionId"), "side": o.get("side"),
            "bet_id": _testo(o.get("betId")) or None,
            "abbinato_nuovo": round(nuovo, 2),
            "prezzo_medio": o.get("averagePriceMatched"),
            "ricevuto_ms": ricevuto_ms, "publish_time_ms": publish_time_ms,
            "deciso_ms": deciso,
            "latenza_ms": (deciso - int(ricevuto_ms)) if isinstance(ricevuto_ms, (int, float))
            else None,
            "nota": ("ordine dell'utente abbinato sul mercato del bot: il bot annulla i "
                     "suoi ordini vivi, non copre, non rientra su questa partita"),
        }
        self.intervento = evento
        try:
            self._al_intervento(evento)
        except Exception as ex:  # noqa: BLE001 - l'intervento resta registrato
            evento["errore_reazione"] = str(ex)[:200]
            logger.exception("[ordini-esterni] %s: reazione all'intervento KO", self.nome)
        return evento

    def controlla(self) -> Optional[Dict[str, Any]]:
        """Il controllo del book (thread di flumine, prima della decisione del
        bot). LIVE: la fotografia del conto e' gia' stata giudicata al suo arrivo
        (``Registro.ricevi_conto``): qui costa un confronto. PAPER: si leggono gli
        ordini manuali simulati (stesso processo)."""
        if self.intervento is not None:
            return self.intervento
        if self._attesa and self.rivedi() is not None:
            return self.intervento
        if self._fonte_paper is not None:
            try:
                righe = list(self._fonte_paper() or ())
            except Exception as ex:  # noqa: BLE001 - fonte illeggibile: si riprova
                logger.debug("[ordini-esterni] %s: fonte paper KO: %s", self.nome, ex)
                righe = []
            if righe:
                return self.valuta_righe(righe, fonte=FONTE_PAPER)
        return None


# ---------------------------------------------------------------------------
# SECONDO GIRO: "del bot / fuori bot" per bet_id, FUORI dal giro caldo
# ---------------------------------------------------------------------------
class ConfermaBot:
    """La classificazione di W2 per bet_id (``leggi(bet_ids) -> {bet_id: motivo}``
    degli ordini che il DB dice dei BOT; gli altri sono ``FUORI_BOT``), in un
    thread suo: UNA lettura per bet_id nuovo, esito tenuto in cache e riusato.
    ``leggi`` che solleva = DB illeggibile: nessun esito (il bot resta sospeso),
    ``errore(bet_id)`` lo dice; una nuova richiesta non rilegge prima di
    ``riprova_s``. ``sveglia`` (facoltativa) e' chiamata dopo ogni lettura: in
    produzione mette un evento nella coda di flumine, cosi' la decisione arriva
    subito e non al book dopo. Mai un'eccezione verso chi chiede."""

    def __init__(self, leggi: Callable[[List[str]], Dict[str, str]], *,
                 sveglia: Optional[Callable[[], None]] = None,
                 riprova_s: float = RIPROVA_DB_S,
                 orologio: Callable[[], float] = time.monotonic,
                 in_thread: bool = True) -> None:
        self._leggi = leggi
        self._sveglia = sveglia
        self._riprova_s = float(riprova_s)
        self._orologio = orologio
        self._in_thread = bool(in_thread)
        self._esiti: Dict[str, str] = {}
        self._errori: Dict[str, Tuple[str, float]] = {}
        self._coda: List[str] = []
        self._in_volo: set = set()
        self._lock = threading.Lock()
        self._evento = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.letture = 0

    def esito(self, bet_id: str) -> Optional[str]:
        with self._lock:
            return self._esiti.get(str(bet_id))

    def errore(self, bet_id: str) -> Optional[str]:
        with self._lock:
            e = self._errori.get(str(bet_id))
            return e[0] if e else None

    def chiedi(self, bet_ids: Iterable[str]) -> int:
        """Mette in coda i bet_id mai classificati. Ritorna quanti ne ha accodati."""
        ora = self._orologio()
        nuovi: List[str] = []
        with self._lock:
            for b in bet_ids:
                b = str(b or "").strip()
                if not b or b in self._esiti or b in self._in_volo or b in self._coda:
                    continue
                e = self._errori.get(b)
                if e is not None and ora - e[1] < self._riprova_s:
                    continue
                self._coda.append(b)
                nuovi.append(b)
        if not nuovi:
            return 0
        if not self._in_thread:
            self.leggi_ora()
            return len(nuovi)
        if self._thread is None:
            self._thread = threading.Thread(target=self._gira, daemon=True,
                                            name="ordini-esterni-conferma")
            self._thread.start()
        self._evento.set()
        return len(nuovi)

    def leggi_ora(self) -> int:
        """Un passaggio: legge il DB per i bet_id in coda (pubblico per i test)."""
        with self._lock:
            lotto = list(self._coda)
            self._coda.clear()
            self._in_volo.update(lotto)
        if not lotto:
            return 0
        try:
            self.letture += 1
            dei_bot = dict(self._leggi(lotto) or {})
            with self._lock:
                for b in lotto:
                    motivo = dei_bot.get(b)
                    self._esiti[b] = ("bot:%s" % motivo) if motivo else FUORI_BOT
                    self._errori.pop(b, None)
                while len(self._esiti) > MAX_ESITI:
                    self._esiti.pop(next(iter(self._esiti)))
        except Exception as ex:  # noqa: BLE001 - DB illeggibile: nessun esito al buio
            ora = self._orologio()
            with self._lock:
                for b in lotto:
                    self._errori[b] = (str(ex)[:200] or type(ex).__name__, ora)
        finally:
            with self._lock:
                self._in_volo.difference_update(lotto)
        if self._sveglia is not None:
            try:
                self._sveglia()
            except Exception:  # noqa: BLE001 - la sveglia e' un'accelerazione
                pass
        return len(lotto)

    def _gira(self) -> None:
        while True:
            self._evento.wait()
            self._evento.clear()
            try:
                self.leggi_ora()
            except Exception:  # noqa: BLE001 - il thread non muore mai
                logger.exception("[ordini-esterni] conferma KO")


def controllo_sospensione(framework: Any) -> Any:
    """Il trading control di flumine che RIFIUTA ogni ordine nuovo (PLACE,
    REPLACE) di un bot sorvegliato su una selezione SOSPESA (ordine esterno in
    verifica) o dopo l'intervento. Gli annulli passano sempre. Via di produzione
    del rifiuto: ``_on_error`` -> ``order.violation`` -> ``place_order`` falso."""
    from flumine.controls import BaseControl
    from flumine.order.orderpackage import OrderPackageType

    class _Sospensione(BaseControl):
        NAME = "ORDINI_ESTERNI"

        def _validate(self, order: Any, package_type: Any) -> None:
            if package_type not in (OrderPackageType.PLACE, OrderPackageType.REPLACE):
                return
            strat = getattr(getattr(order, "trade", None), "strategy", None)
            s = getattr(strat, "_ordini_esterni", None)
            if s is None:
                return
            if s.intervento is not None:
                self._on_error(order, "intervento dell'utente: il bot non piazza piu'")
            if s.sospesa(getattr(order, "market_id", None), getattr(order, "selection_id", None)):
                self._on_error(order, "ordine esterno in verifica su questa selezione: "
                                      "nessun ordine nuovo del bot")

    return _Sospensione(framework)


def monta_controllo(framework: Any) -> bool:
    """Il controllo nel framework, una volta sola. ``False`` se gia' montato."""
    if getattr(framework, "_controllo_ordini_esterni", False):
        return False
    framework.trading_controls.append(controllo_sospensione(framework))
    framework._controllo_ordini_esterni = True
    return True


# ---------------------------------------------------------------------------
# il registro del processo (UN flumine): stream del conto -> sorveglianze live
# ---------------------------------------------------------------------------
class Registro:
    """La ``pubblica`` che ``esiti_ordini_canale.osserva_conto_su_flumine`` chiama
    nel thread di flumine: la fotografia entra nella ``MemoriaConto`` (la STESSA
    del canale: mai una fotografia piu' vecchia sopra una piu' nuova) e va a ogni
    sorveglianza LIVE, che decide subito (nessun giro da aspettare)."""

    def __init__(self, memoria: Any = None) -> None:
        if memoria is None:
            from ..esiti_ordini_canale import MemoriaConto

            memoria = MemoriaConto()
        self.memoria = memoria
        self._sorveglianze: List[Sorveglianza] = []
        self._lock = threading.Lock()
        self.fotografie = 0
        #: chiamata nel thread di flumine PRIMA di giudicare una fotografia (il
        #: runner tennis ci fotografa la sua coda degli ordini manuali)
        self.prima_di_valutare: Optional[Callable[[], None]] = None

    def rivedi(self) -> int:
        """Le verifiche arrivate dal DB (thread di flumine). Ritorna gli interventi."""
        n = 0
        for s in self.sorveglianze():
            if s.intervento is None and s.in_verifica() and s.rivedi() is not None:
                n += 1
        return n

    def aggiungi(self, s: Sorveglianza) -> Sorveglianza:
        with self._lock:
            if s not in self._sorveglianze:
                self._sorveglianze.append(s)
        return s

    def togli(self, s: Sorveglianza) -> None:
        with self._lock:
            if s in self._sorveglianze:
                self._sorveglianze.remove(s)

    def sorveglianze(self) -> List[Sorveglianza]:
        with self._lock:
            return list(self._sorveglianze)

    def ricevi_conto(self, topic: str, payload: Any) -> int:
        """Una fotografia ``conto`` (da ``pubblica_conto_da_evento``). Ritorna
        quanti interventi sono scattati. NON SOLLEVA MAI (gira dentro flumine)."""
        from ..esiti_ordini_canale import TOPIC_CONTO

        if topic != TOPIC_CONTO:
            return 0
        try:
            if not self.memoria.ricevi(payload):
                return 0
            self.fotografie += 1
            if self.prima_di_valutare is not None:
                try:
                    self.prima_di_valutare()
                except Exception:  # noqa: BLE001 - un aiuto, mai un blocco
                    pass
            righe = [o for o in (payload.get("ordini") or []) if isinstance(o, dict)]
            n = 0
            for s in self.sorveglianze():
                if s.modo != "live" or s.intervento is not None:
                    continue
                if s.valuta_righe(righe, fonte=FONTE_STREAM,
                                  ricevuto_ms=payload.get("ricevuto_ms"),
                                  publish_time_ms=payload.get("publish_time_ms")) is not None:
                    n += 1
            return n
        except Exception as ex:  # noqa: BLE001 - mai far cadere flumine
            logger.warning("[ordini-esterni] fotografia del conto non valutata: %s",
                           str(ex)[:160])
            return 0


def monta_su_flumine(framework: Any, registro: Registro) -> bool:
    """Lo STESSO osservatore del runner calcio sul flumine di questo processo,
    con la ``pubblica`` in memoria. ``False`` se non montato (framework
    simulato, gia' osservato, niente hook): il bot resta identico a prima."""
    from ..esiti_ordini_canale import osserva_conto_su_flumine

    return osserva_conto_su_flumine(framework, registro.ricevi_conto)


def proteggi_strategia(strategia: Any, sorveglianza: Sorveglianza) -> None:
    """Il controllo prima di ogni decisione del bot (per ISTANZA, nessuna
    modifica di classe, come ``tennis_runner._scope_to_market``): fatto
    l'intervento, ``check_market_book`` torna falso e il bot non decide piu'."""
    originale = strategia.check_market_book

    def _con_sorveglianza(market: Any, market_book: Any, _orig: Any = originale,
                          _s: Sorveglianza = sorveglianza) -> bool:
        if _s.controlla() is not None:
            return False
        return bool(_orig(market, market_book))

    strategia.check_market_book = _con_sorveglianza  # type: ignore[assignment]
    strategia._ordini_esterni = sorveglianza


def ferma_strategia(strategia: Any) -> None:
    """Il bot non decide piu' (``check_market_book`` sempre falso), per istanza."""
    try:
        strategia.check_market_book = lambda *a, **k: False  # type: ignore[assignment]
    except Exception:  # noqa: BLE001 - istanza senza attributi scrivibili
        pass
    strategia._fermo_per_intervento = True


#: stati di un ordine flumine ancora sul book (``OrderStatus.name``)
STATI_VIVI = frozenset({"PENDING", "EXECUTABLE", "UPDATING", "CANCELLING", "REPLACING"})


def _stato(o: Any) -> str:
    st = getattr(o, "status", None)
    return str(getattr(st, "name", st) or "").upper()


def annulla_vivi(coppie: Iterable[Tuple[Any, Any]]) -> Dict[str, Any]:
    """``market.cancel_order`` (la via delle strategie) per ogni (mercato,
    ordine) ancora vivo e non gia' in annullo. Non solleva mai."""
    esito: Dict[str, Any] = {"vivi": 0, "annullo_chiesto": 0, "errori": []}
    for market, o in coppie:
        st = _stato(o)
        if st not in STATI_VIVI:
            continue
        esito["vivi"] += 1
        if st == "CANCELLING":
            continue
        try:
            market.cancel_order(o)
            esito["annullo_chiesto"] += 1
        except Exception as ex:  # noqa: BLE001 - si prova su tutti
            esito["errori"].append(str(ex)[:120])
    if not esito["errori"]:
        esito.pop("errori")
    return esito


def adesso_ms() -> int:
    return int(time.time() * 1000)
