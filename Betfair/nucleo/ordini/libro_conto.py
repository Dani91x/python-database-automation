"""libro_conto.py - il LIBRO ORDINI DEL CONTO (comparto C, W1-C2, 09/10/2026).

Priorita' dell'utente (09/10): "sul ladder di Trading voglio vedere TUTTO come un
tool professionale: ogni ordine, mio o dei bot, da app o dal sito, con P&L e
tutto". Questo modulo implementa ``LibroOrdiniConto`` (contratto
``Betfair/nucleo/ordini/contratto.py``): TUTTI gli ordini del conto su un
mercato, ognuno con il suo autore, abbinato, residuo, prezzo medio e stato, e il
P&L di mercato "se vince" (``pnl_mercato``).

Entrate:
  * LIVE: un ``FlussoOrdiniConto`` (protocollo del comparto A,
    ``Betfair/nucleo/betfair/contratto.py``: stream degli ordini del conto, senza
    filtro, sola lettura). Il libro si iscrive come consumatore
    (``collega_live``) e prende la fotografia iniziale (``flusso.ordini()``);
  * PROVA: una ``SorgenteOrdiniProva`` (protocollo definito QUI, alimentato in
    ondata 2 dai motori paper): ordini ``OrdineInProva`` con l'attore del
    comando quando la sorgente lo conosce. Entrano con ``modo='paper'``;
  * indizi di attribuzione letti altrove (``aggiungi_indizi``): DB e specchio
    restano fuori da qui, il libro riceve solo dati;
  * il SEME da ``listCurrentOrders`` (``SorgenteOrdiniCorrenti``, REST di A1)
    all'avvio e a ogni riconnessione SENZA ripresa: lo stream non rimanda gli
    ordini gia' completamente abbinati (revisione 09/10, G3); la verifica con
    ``mb``/``ml`` dello stream segnala l'abbinato che manca;
  * dal book: runner, ``bettingType``, ``numberOfWinners``, chiuso
    (``imposta_mercato``).

Uscite: ``ordini(market_id, modo)`` -> ``OrdineConto``; ``posizione(market_id,
modo)`` -> ``PosizioneMercato``; ``calcolo_posizione`` (estensione: cosa la
posizione dichiara); consumatori avvisati a ogni ordine cambiato
(``aggiungi_consumatore``: l'aggancio al ladder in ondata 2).

Regole: paper e live MAI sommati (la chiave e' ``(modo, bet_id)``; ogni lettura
chiede il modo; una posizione e' sempre di UN modo, PSB par. 7 n.21). Un
messaggio piu' vecchio di quello gia' tenuto (``ricevuto_ms`` minore) non
sovrascrive (si conta); uno piu' nuovo che fa REGREDIRE l'ordine (abbinato che
cala, completo che torna eseguibile: un seme REST letto prima e consegnato dopo)
si rifiuta e si dice a WARNING. Il tetto di memoria dimentica prima i mercati
chiusi; l'abbinato degli ordini dimenticati di mercati aperti resta nel P&L
(riassunto); se un ordine riassunto rientra (seme, aggiornamento tardivo) la sua
parte si storna e tornano attore e indizi: mai contato due volte. Thread-safe: un ``RLock``; i consumatori sono chiamati FUORI dal
lucchetto, uno alla volta e sempre con lo stato PIU' RECENTE dell'ordine; un
loro errore si logga, mai propagato a chi alimenta.

NON fa: nessuna rete, nessun DB, nessun file, nessun thread proprio (gira nel
thread di chi lo alimenta); non piazza ne' annulla; non decide se un comando
sul ladder e' permesso (vedi ``comandi_ammessi`` e il referto W1-C2).

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import dataclasses
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import (Any, Callable, Dict, Iterable, List, Mapping, Optional, Protocol,
                    Sequence, Set, Tuple)

from Betfair.nucleo.betfair.contratto import FlussoOrdiniConto, OrdineDalConto
from Betfair.nucleo.comuni import Modo
from Betfair.nucleo.ordini import attribuzione as attr
from Betfair.nucleo.ordini import pnl_mercato
from Betfair.nucleo.ordini.contratto import OrdineConto, PosizioneMercato

logger = logging.getLogger(__name__)

MODI: Tuple[str, ...] = ("paper", "live")
#: tetto degli ordini tenuti per modo (un processo vive giorni): oltre, si
#: dimenticano per primi gli ordini terminali dei mercati piu' vecchi
MAX_ORDINI_DEFAULT = 20000


@dataclass(frozen=True)
class OrdineInProva:
    """Un ordine IN PROVA (paper): non esiste su Betfair. Stessa forma di
    ``OrdineDalConto`` (i motori paper la producono con la grafia di
    ``listCurrentOrders``, ``esiti_ordini_canale.ordine_paper_del_conto``) piu'
    l'``attore`` del comando quando la sorgente lo conosce."""

    ordine: OrdineDalConto
    attore: Optional[str] = None


class SorgenteOrdiniProva(Protocol):
    """La sorgente degli ordini in prova (ondata 2: i motori paper)."""

    def aggiungi_consumatore(self, cb: Callable[[OrdineInProva], None]) -> None: ...
    def ordini(self, market_id: Optional[str] = None) -> Tuple[OrdineInProva, ...]: ...


# ---------------------------------------------------------------------------
# conversione: la grafia di listCurrentOrders (camelCase) -> OrdineDalConto
# ---------------------------------------------------------------------------
def _iso_a_ms(v: Any) -> Optional[int]:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        dt = v
    else:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(round(dt.timestamp() * 1000))


def _num0(v: Any) -> float:
    return float(v) if v is not None else 0.0


def ordine_da_riga_conto(riga: Mapping[str, Any], *, ricevuto_ms: int) -> OrdineDalConto:
    """UN ordine nella grafia di ``listCurrentOrders`` (quella di
    ``esiti_ordini_canale.ordine_del_conto`` / ``ordine_paper_del_conto``, o il
    JSON di Betfair) -> ``OrdineDalConto``. Le chiavi sono quelle di Betfair
    (catalogo PSB par. 7 n.1); un campo essenziale che manca SOLLEVA
    ``ValueError`` (mai un valore inventato, n.3)."""
    ps = riga.get("priceSize")
    if not isinstance(ps, Mapping) or ps.get("price") is None or ps.get("size") is None:
        raise ValueError(f"ordine {riga.get('betId')}: priceSize assente ({ps!r})")
    lato = str(riga.get("side") or "").upper()
    if lato not in ("BACK", "LAY"):
        raise ValueError(f"ordine {riga.get('betId')}: lato sconosciuto {riga.get('side')!r}")
    stato = str(riga.get("status") or "")
    if stato not in ("EXECUTABLE", "EXECUTION_COMPLETE"):
        raise ValueError(f"ordine {riga.get('betId')}: stato sconosciuto {stato!r}")
    for k in ("betId", "marketId", "selectionId"):
        if riga.get(k) is None:
            raise ValueError(f"ordine senza {k}: {dict(riga)!r}"[:300])
    avp = riga.get("averagePriceMatched")
    return OrdineDalConto(
        bet_id=str(riga["betId"]), market_id=str(riga["marketId"]),
        selection_id=int(riga["selectionId"]),
        handicap=float(riga.get("handicap") or 0.0),
        lato="back" if lato == "BACK" else "lay",
        prezzo=float(ps["price"]), importo=float(ps["size"]),
        stato="EXECUTABLE" if stato == "EXECUTABLE" else "EXECUTION_COMPLETE",
        persistenza=riga.get("persistenceType"), tipo=riga.get("orderType"),
        piazzato_ms=_iso_a_ms(riga.get("placedDate")),
        abbinato_ms=_iso_a_ms(riga.get("matchedDate")),
        abbinato=_num0(riga.get("sizeMatched")), residuo=_num0(riga.get("sizeRemaining")),
        scaduto=_num0(riga.get("sizeLapsed")), annullato=_num0(riga.get("sizeCancelled")),
        annullato_da_betfair=_num0(riga.get("sizeVoided")),
        prezzo_medio=float(avp) if avp is not None and float(avp) > 0 else None,
        customer_order_ref=riga.get("customerOrderRef"),
        customer_strategy_ref=riga.get("customerStrategyRef"),
        regulator_code=riga.get("regulatorCode"),
        ricevuto_ms=int(ricevuto_ms),
    )


def ordine_da_corrente(co: Any, *, ricevuto_ms: int) -> OrdineDalConto:
    """Un ``CurrentOrder`` VERO di betfairlightweight (``listCurrentOrders`` o la
    cache dello stream ordini) -> ``OrdineDalConto``, passando dalla STESSA
    normalizzazione con cui il runner pubblica il conto sul canale
    (``esiti_ordini_canale.ordine_del_conto``). ``regulatorCode`` non e' in
    quella normalizzazione: si legge dall'oggetto."""
    from Betfair.stream.esiti_ordini_canale import ordine_del_conto

    riga = dict(ordine_del_conto(co))
    riga["regulatorCode"] = getattr(co, "regulator_code", None)
    return ordine_da_riga_conto(riga, ricevuto_ms=ricevuto_ms)


def fase_dell_ordine(o: OrdineDalConto) -> str:
    """Lo stato mostrato: la fase del protocollo del motore
    (``motore_ordini.fase_da_riga``: accettato_betfair, abbinato_parziale,
    abbinato, annullato, scaduto) sulla riga in forma di specchio."""
    from Betfair.stream.motore_ordini import fase_da_riga

    return fase_da_riga({"status": o.stato, "size_matched": o.abbinato, "size": o.importo,
                         "size_cancelled": o.annullato, "size_lapsed": o.scaduto,
                         "bet_id": o.bet_id})


def componi_ordine_conto(modo: str, o: OrdineDalConto, a: attr.Attribuzione) -> OrdineConto:
    """``OrdineDalConto`` + attribuzione -> ``OrdineConto`` (la riga del libro)."""
    if modo not in MODI:
        raise ValueError(f"modo non ammesso: {modo!r}")
    return OrdineConto(
        bet_id=str(o.bet_id), market_id=str(o.market_id), selection_id=int(o.selection_id),
        handicap=float(o.handicap), lato=o.lato, prezzo=float(o.prezzo),
        importo=float(o.importo), abbinato=float(o.abbinato), residuo=float(o.residuo),
        prezzo_medio=o.prezzo_medio, stato=fase_dell_ordine(o), autore=a.autore,  # type: ignore[arg-type]
        ref=(o.customer_order_ref or None), modo=modo,  # type: ignore[arg-type]
        aggiornato_ms=int(o.ricevuto_ms))


# ---------------------------------------------------------------------------
# il libro
# ---------------------------------------------------------------------------
class SorgenteOrdiniCorrenti(Protocol):
    """La lettura REST ``listCurrentOrders`` del conto (comparto A1: ``ClienteRest.
    lettura``), paginata: ``CurrentOrder`` VERI di betfairlightweight. Serve per
    il SEME (revisione 09/10, G3): una sottoscrizione nuova dello stream ordini
    porta solo gli ordini EXECUTABLE; gli EXECUTION_COMPLETE arrivano "only when
    transitioning" (documentazione Betfair, Exchange Stream API, "Unmatched
    Orders"; copia in ``AUDIT_2026-10-02/_fonti_betfair/bf_2687396.txt:941``)."""

    def ordini_correnti(self, market_ids: Optional[Sequence[str]] = None) -> Iterable[Any]: ...


@dataclass
class _Voce:
    ordine: OrdineDalConto
    conto: OrdineConto
    attore_dichiarato: Optional[str]


@dataclass
class _InfoMercato:
    runner: Optional[Tuple[int, ...]] = None
    tipo_scommessa: Optional[str] = None
    vincitori: Optional[int] = None
    tipo_mercato: Optional[str] = None
    chiuso: bool = False


@dataclass
class _Riassunto:
    """Un ordine terminale dimenticato dal tetto su un mercato APERTO: il suo
    stato (per le guardie se rientra), l'attore, gli indizi e la sua parte nel
    riassunto (per stornarla se rientra: seconda revisione 09/10, M2)."""

    ordine: OrdineDalConto
    attore: Optional[str]
    indizi: Tuple[attr.Indizio, ...]
    chiave_acc: Optional[Tuple[int, float, str, str]]
    abbinato: float
    somma: float


#: tetto degli indizi tenuti per bet_id non (ancora) nel libro
MAX_INDIZI_SENZA_ORDINE = 5000
#: tolleranza sull'abbinato (centesimo) per la verifica con mb/ml dello stream
EPS_ABBINATO = 0.01


def _ora_ms() -> int:
    return int(time.time() * 1000)


class LibroConto:
    """Implementazione di ``LibroOrdiniConto`` (vedi il docstring del modulo)."""

    def __init__(self, *, regole: Optional[attr.RegoleAttribuzione] = None,
                 max_ordini: int = MAX_ORDINI_DEFAULT,
                 max_indizi: int = MAX_INDIZI_SENZA_ORDINE) -> None:
        self._regole = regole
        self._max = int(max_ordini)
        self._max_indizi = int(max_indizi)
        self._lock = threading.RLock()
        # consegna ai consumatori SERIALIZZATA e sempre dello stato piu' recente
        # (revisione 09/10: mai una versione vecchia dopo una nuova)
        self._consegna = threading.RLock()
        self._voci: Dict[Tuple[str, str], _Voce] = {}
        self._per_mercato: Dict[Tuple[str, str], Set[str]] = {}
        self._indizi: Dict[str, Tuple[attr.Indizio, ...]] = {}
        self._consumatori: List[Callable[[OrdineConto], None]] = []
        self._attribuzioni: Dict[Tuple[str, str], attr.Attribuzione] = {}
        self._quanti: Dict[str, int] = {m: 0 for m in MODI}
        self._mercati: Dict[str, _InfoMercato] = {}
        # ordini terminali dimenticati dal tetto su mercati APERTI: accumulati
        # per (selezione, handicap, lato, autore) -> [abbinato, abbinato*prezzo]
        self._riassunti: Dict[Tuple[str, str], Dict[Tuple[int, float, str, str], List[float]]] = {}
        # i bet_id riassunti per (modo, mercato): se rientrano (seme, aggiornamento
        # tardivo) si storna la loro parte, mai contati due volte
        self._riassunti_bet: Dict[Tuple[str, str], Dict[str, _Riassunto]] = {}
        self._attore_rientrato: Dict[Tuple[str, str], str] = {}
        self._mancanze: Dict[Tuple[str, str, int, float], Dict[str, float]] = {}
        # il live parte SENZA seme: lo stream non porta gli ordini gia' completi
        self._seme: Dict[str, bool] = {"live": False, "paper": True}
        self.conti: Dict[str, int] = {"ricevuti": 0, "fuori_ordine": 0, "regressioni": 0,
                                      "scartati": 0, "dimenticati": 0,
                                      "dimenticati_aperti": 0, "consumatori_ko": 0,
                                      "semi": 0, "semi_ko": 0, "riassunti_rientrati": 0}

    # ------------------------------------------------------------ alimentazione
    def collega_live(self, flusso: FlussoOrdiniConto, *,
                     correnti: Optional[SorgenteOrdiniCorrenti] = None) -> None:
        """Iscrive il libro allo stream degli ordini del conto, prende la sua
        fotografia (``ordini()``) e, se c'e' la sorgente REST, fa il SEME."""
        flusso.aggiungi_consumatore(self.ricevi_live)
        for o in flusso.ordini():
            self.ricevi_live(o)
        if correnti is not None:
            self.semina(correnti)

    def collega_prova(self, sorgente: SorgenteOrdiniProva) -> None:
        """Iscrive il libro alla sorgente degli ordini in prova (la sua
        fotografia e' il blotter paper intero: niente seme da fare)."""
        sorgente.aggiungi_consumatore(self.ricevi_prova)
        for o in sorgente.ordini():
            self.ricevi_prova(o)

    def semina(self, correnti: SorgenteOrdiniCorrenti, *,
               market_ids: Optional[Sequence[str]] = None,
               ricevuto_ms: Optional[int] = None) -> int:
        """Il SEME del live da ``listCurrentOrders`` (all'avvio e a ogni
        riconnessione SENZA ripresa): porta gli ordini gia' completamente
        abbinati che lo stream non rimanda. Ritorna gli ordini letti, ``-1`` se
        la lettura fallisce (il seme resta NON fatto e si dice)."""
        istante = int(ricevuto_ms) if ricevuto_ms is not None else _ora_ms()
        try:
            letti = list(correnti.ordini_correnti(market_ids))
        except Exception:  # noqa: BLE001 - REST KO: il seme resta da fare, mai finto
            with self._lock:
                self._seme["live"] = False
                self.conti["semi_ko"] += 1
            logger.warning("[libro] seme da listCurrentOrders KO: ordini gia' abbinati "
                           "possono mancare (P&L incompleto)", exc_info=True)
            return -1
        for co in letti:
            try:
                o = ordine_da_corrente(co, ricevuto_ms=istante)
            except Exception:  # noqa: BLE001 - un ordine illeggibile non ferma il seme
                with self._lock:
                    self.conti["scartati"] += 1
                logger.exception("[libro] seme: ordine %s illeggibile",
                                 getattr(co, "bet_id", None))
                continue
            self._ricevi("live", o, None)
        with self._lock:
            self._seme["live"] = True
            self.conti["semi"] += 1
        return len(letti)

    def riconnesso(self, *, con_ripresa: bool,
                   correnti: Optional[SorgenteOrdiniCorrenti] = None) -> None:
        """Lo stream ordini si e' riconnesso. Senza ripresa (``initialClk``/``clk``)
        l'immagine nuova non ha gli EXECUTION_COMPLETE: il seme torna da fare."""
        if con_ripresa:
            return
        with self._lock:
            self._seme["live"] = False
        logger.warning("[libro] stream ordini riconnesso SENZA ripresa: seme da rifare")
        if correnti is not None:
            self.semina(correnti)

    def seme_fatto(self, modo: Modo = "live") -> bool:
        with self._lock:
            return bool(self._seme.get(modo, False))

    def ricevi_live(self, o: OrdineDalConto) -> None:
        self._ricevi("live", o, None)

    def ricevi_prova(self, o: OrdineInProva) -> None:
        self._ricevi("paper", o.ordine, o.attore)

    def aggiungi_indizi(self, bet_id: str, indizi: Iterable[attr.Indizio]) -> Optional[OrdineConto]:
        """Indizi (DB, specchio, coda) su un ordine LIVE: si ricordano SENZA
        duplicati e l'ordine, se c'e', si riattribuisce."""
        nuovo: Optional[OrdineConto] = None
        bid = str(bet_id)
        with self._lock:
            tenuti = list(self._indizi.get(bid, ()))
            for ind in indizi:
                if ind not in tenuti:
                    tenuti.append(ind)
            self._indizi[bid] = tuple(tenuti)
            voce = self._voci.get(("live", bid))
            if voce is not None:
                nuovo = self._componi("live", voce.ordine, None)
                voce.conto = nuovo
            else:
                self._pota_indizi()
        if nuovo is not None:
            self._avvisa(("live", bid))
        return nuovo

    def _pota_indizi(self) -> None:
        """Gli indizi di bet_id mai arrivati non crescono senza limite."""
        orfani = [b for b in self._indizi if ("live", b) not in self._voci]
        for b in orfani[:max(0, len(orfani) - self._max_indizi)]:
            self._indizi.pop(b, None)

    def _regressione(self, vecchio: OrdineDalConto, nuovo: OrdineDalConto) -> Optional[str]:
        """Revisione 09/10 (M1): l'abbinato non cala (salvo annulli di Betfair,
        ``sv``) e un ordine completo non torna eseguibile."""
        if vecchio.stato == "EXECUTION_COMPLETE" and nuovo.stato == "EXECUTABLE":
            return "EXECUTION_COMPLETE -> EXECUTABLE"
        annullati = max(0.0, float(nuovo.annullato_da_betfair) - float(vecchio.annullato_da_betfair))
        if float(nuovo.abbinato) < float(vecchio.abbinato) - annullati - 1e-9:
            return f"abbinato {vecchio.abbinato} -> {nuovo.abbinato}"
        return None

    def _ricevi(self, modo: str, o: OrdineDalConto, attore: Optional[str]) -> None:
        if modo not in MODI:
            raise ValueError(f"modo non ammesso: {modo!r}")
        chiave = (modo, str(o.bet_id))
        with self._lock:
            self.conti["ricevuti"] += 1
            voce = self._voci.get(chiave)
            if voce is None and not self._rientro_da_riassunto(modo, o):
                return
            if voce is None:
                attore = attore or self._attore_rientrato.pop(chiave, None)
            if voce is not None and int(o.ricevuto_ms) < int(voce.ordine.ricevuto_ms):
                self.conti["fuori_ordine"] += 1
                logger.debug("[libro] %s %s: messaggio piu' vecchio di quello tenuto, ignorato",
                             modo, o.bet_id)
                return
            if voce is not None:
                regr = self._regressione(voce.ordine, o)
                if regr is not None:
                    self.conti["regressioni"] += 1
                    logger.warning("[libro] %s %s: regressione rifiutata (%s): tenuto lo "
                                   "stato piu' avanzato", modo, o.bet_id, regr)
                    return
            try:
                conto = self._componi(modo, o, attore)
            except Exception:  # noqa: BLE001 - un ordine illeggibile non ferma il libro
                self.conti["scartati"] += 1
                logger.exception("[libro] %s %s: ordine non componibile, scartato", modo, o.bet_id)
                return
            if voce is None:
                self._quanti[modo] += 1
            self._voci[chiave] = _Voce(o, conto, attore)
            self._per_mercato.setdefault((modo, str(o.market_id)), set()).add(str(o.bet_id))
            self._rispetta_tetto(modo)
        self._avvisa(chiave)

    def _rientro_da_riassunto(self, modo: str, o: OrdineDalConto) -> bool:
        """Un ordine gia' riassunto dal tetto rientra (seme dopo riconnessione,
        aggiornamento tardivo): con le stesse guardie di sempre contro il suo
        ultimo stato; se passa, la sua parte si STORNA dal riassunto e tornano
        attore e indizi. False = messaggio rifiutato (il riassunto resta)."""
        per_bet = self._riassunti_bet.get((modo, str(o.market_id)))
        rec = per_bet.get(str(o.bet_id)) if per_bet else None
        if rec is None:
            return True
        if int(o.ricevuto_ms) < int(rec.ordine.ricevuto_ms):
            self.conti["fuori_ordine"] += 1
            return False
        regr = self._regressione(rec.ordine, o)
        if regr is not None:
            self.conti["regressioni"] += 1
            logger.warning("[libro] %s %s (riassunto): regressione rifiutata (%s)",
                           modo, o.bet_id, regr)
            return False
        del per_bet[str(o.bet_id)]
        if rec.chiave_acc is not None:
            acc = self._riassunti.get((modo, str(o.market_id)), {})
            parte = acc.get(rec.chiave_acc)
            if parte is not None:
                parte[0] -= rec.abbinato
                parte[1] -= rec.somma
                if parte[0] <= 1e-9:
                    del acc[rec.chiave_acc]
        if rec.indizi:
            tenuti = list(self._indizi.get(str(o.bet_id), ()))
            self._indizi[str(o.bet_id)] = tuple(tenuti + [i for i in rec.indizi if i not in tenuti])
        if rec.attore is not None:
            self._attore_rientrato[(modo, str(o.bet_id))] = rec.attore
        self.conti["riassunti_rientrati"] += 1
        logger.info("[libro] %s %s: ordine riassunto rientrato, la sua parte stornata",
                    modo, o.bet_id)
        return True

    def _componi(self, modo: str, o: OrdineDalConto, attore: Optional[str]) -> OrdineConto:
        regole = self._regole_attive()
        if modo == "paper":
            a = attr.attribuisci_dichiarato(attore, o, regole)
        else:
            a = attr.attribuisci(o, self._indizi.get(str(o.bet_id), ()), regole)
        self._attribuzioni[(modo, str(o.bet_id))] = a
        return componi_ordine_conto(modo, o, a)

    def _regole_attive(self) -> attr.RegoleAttribuzione:
        if self._regole is None:
            self._regole = attr.regole_di_oggi()
        return self._regole

    def _rispetta_tetto(self, modo: str) -> None:
        """Oltre il tetto si dimenticano gli ordini TERMINALI (mai un ordine vivo:
        e' denaro sul mercato): PRIMA quelli dei mercati chiusi, poi i piu'
        vecchi dei mercati aperti, il cui abbinato resta nel P&L come riassunto
        (revisione 09/10, M2) e si dice a WARNING."""
        if self._quanti[modo] <= self._max:
            return
        da_togliere = self._quanti[modo] - self._max
        candidati = []
        for k, v in self._voci.items():
            if k[0] != modo or v.ordine.stato != "EXECUTION_COMPLETE":
                continue
            info = self._mercati.get(str(v.ordine.market_id))
            aperto = 0 if (info is not None and info.chiuso) else 1
            candidati.append((aperto, v.ordine.ricevuto_ms, k))
        candidati.sort()
        aperti = 0
        for aperto, _ms, k in candidati[:da_togliere]:
            if aperto:
                self._riassumi(k)
                aperti += 1
            self._togli(k)
            self.conti["dimenticati"] += 1
        if aperti:
            self.conti["dimenticati_aperti"] += aperti
            logger.warning("[libro] tetto di %d ordini %s: %d ordini terminali di mercati "
                           "APERTI tolti dall'elenco, il loro abbinato resta nel P&L",
                           self._max, modo, aperti)

    def _riassumi(self, chiave: Tuple[str, str]) -> None:
        v = self._voci[chiave]
        c = v.conto
        rec = _Riassunto(v.ordine, v.attore_dichiarato, tuple(self._indizi.get(chiave[1], ())),
                         None, 0.0, 0.0)
        self._riassunti_bet.setdefault((chiave[0], str(c.market_id)), {})[chiave[1]] = rec
        if c.abbinato <= 0 or c.prezzo_medio is None or not c.prezzo_medio > 1.0:
            return
        acc = self._riassunti.setdefault((chiave[0], str(c.market_id)), {})
        rec.chiave_acc = (int(c.selection_id), float(c.handicap), c.lato, c.autore)
        voce = acc.setdefault(rec.chiave_acc, [0.0, 0.0])
        rec.abbinato = float(c.abbinato)
        rec.somma = float(c.abbinato) * float(c.prezzo_medio)
        voce[0] += rec.abbinato
        voce[1] += rec.somma

    def _ordini_riassunti(self, market_id: str, modo: str) -> List[OrdineConto]:
        out: List[OrdineConto] = []
        for (sid, hc, lato, autore), (abb, somma) in sorted(
                self._riassunti.get((modo, str(market_id)), {}).items()):
            out.append(OrdineConto(
                bet_id=f"riassunto:{sid}:{hc}:{lato}:{autore}", market_id=str(market_id),
                selection_id=sid, handicap=hc, lato=lato, prezzo=somma / abb,  # type: ignore[arg-type]
                importo=abb, abbinato=abb, residuo=0.0, prezzo_medio=somma / abb,
                stato="riassunto", autore=autore, ref=None, modo=modo,  # type: ignore[arg-type]
                aggiornato_ms=0))
        return out

    def _togli(self, chiave: Tuple[str, str]) -> None:
        voce = self._voci.pop(chiave, None)
        self._attribuzioni.pop(chiave, None)
        if chiave[0] == "live":
            self._indizi.pop(chiave[1], None)
        if voce is not None:
            self._quanti[chiave[0]] -= 1
            ids = self._per_mercato.get((chiave[0], str(voce.ordine.market_id)))
            if ids is not None:
                ids.discard(chiave[1])

    def dimentica_mercato(self, market_id: str, modo: Optional[Modo] = None) -> int:
        """Mercato chiuso e regolato: toglie i suoi ordini (di un modo o di
        entrambi), i riassunti, le mancanze e gli indizi."""
        n = 0
        mid = str(market_id)
        with self._lock:
            for m in ((modo,) if modo else MODI):
                for bid in list(self._per_mercato.pop((m, mid), set())):
                    self._togli((m, bid))
                    n += 1
                self._riassunti.pop((m, mid), None)
                self._riassunti_bet.pop((m, mid), None)
                for k in [k for k in self._mancanze if k[0] == m and k[1] == mid]:
                    self._mancanze.pop(k, None)
            if modo is None:
                self._mercati.pop(mid, None)
        return n

    # ------------------------------------------------------------ il mercato
    def imposta_mercato(self, market_id: str, *, runner: Optional[Iterable[int]] = None,
                        tipo_scommessa: Optional[str] = None, vincitori: Optional[int] = None,
                        chiuso: Optional[bool] = None,
                        tipo_mercato: Optional[str] = None) -> None:
        """Dal book (``marketDefinition``): elenco dei runner, ``bettingType``,
        ``numberOfWinners``, ``marketType``, stato chiuso. Solo i valori dati
        cambiano."""
        with self._lock:
            info = self._mercati.setdefault(str(market_id), _InfoMercato())
            if runner is not None:
                info.runner = tuple(int(r) for r in runner)
            if tipo_scommessa is not None:
                info.tipo_scommessa = str(tipo_scommessa)
            if vincitori is not None:
                info.vincitori = int(vincitori)
            if chiuso is not None:
                info.chiuso = bool(chiuso)
            if tipo_mercato is not None:
                info.tipo_mercato = str(tipo_mercato)

    def verifica_abbinato(self, market_id: str, selection_id: int, handicap: float,
                          mb: Optional[Sequence[Sequence[float]]],
                          ml: Optional[Sequence[Sequence[float]]],
                          modo: Modo = "live") -> Optional[Mapping[str, float]]:
        """Revisione 09/10 (G3): ``mb``/``ml`` dell'``OrderRunnerChange`` dello
        stream (abbinato del CONTO per prezzo, tutti gli ordini, anche i completi
        di prima della sottoscrizione) contro l'abbinato che il libro conosce. Se
        il libro ha MENO, la mancanza si ricorda (il P&L dichiara
        ``abbinato_mancante``) e si dice a WARNING. ``None`` = nessuna mancanza."""
        sid, hc = int(selection_id), float(handicap)
        with self._lock:
            noto = {"back": 0.0, "lay": 0.0}
            for c in self._ordini_del_mercato(str(market_id), modo):
                if int(c.selection_id) == sid and abs(float(c.handicap) - hc) <= 1e-9:
                    noto[c.lato] += float(c.abbinato)
            mancanza: Dict[str, float] = {}
            for lato, coppie in (("back", mb), ("lay", ml)):
                if coppie is None:
                    continue
                stream = sum(float(s) for _p, s in coppie)
                if stream - noto[lato] > EPS_ABBINATO:
                    mancanza[lato] = round(stream - noto[lato], 2)
            chiave = (modo, str(market_id), sid, hc)
            if mancanza:
                self._mancanze[chiave] = mancanza
            else:
                self._mancanze.pop(chiave, None)
        if mancanza:
            logger.warning("[libro] %s %s sel %s: abbinato dello stream oltre quello degli "
                           "ordini noti %s (seme mancante?)", modo, market_id, sid, mancanza)
            return mancanza
        return None

    # ------------------------------------------------------------ consumatori
    def aggiungi_consumatore(self, cb: Callable[[OrdineConto], None]) -> None:
        with self._lock:
            self._consumatori.append(cb)

    def _avvisa(self, chiave: Tuple[str, str]) -> None:
        """Consegna serializzata dello stato PIU' RECENTE dell'ordine."""
        with self._consegna:
            with self._lock:
                voce = self._voci.get(chiave)
                if voce is None:
                    return
                o = voce.conto
                cbs = list(self._consumatori)
            for cb in cbs:
                try:
                    cb(o)
                except Exception:  # noqa: BLE001 - un consumatore rotto non ferma il libro
                    with self._lock:
                        self.conti["consumatori_ko"] += 1
                    logger.exception("[libro] consumatore KO sull'ordine %s", o.bet_id)

    # ------------------------------------------------------------ letture
    def _ordini_del_mercato(self, market_id: str, modo: str) -> List[OrdineConto]:
        return [self._voci[(modo, bid)].conto
                for bid in self._per_mercato.get((modo, market_id), ())]

    def ordini(self, market_id: str, modo: Optional[Modo] = None) -> Tuple[OrdineConto, ...]:
        """Gli ordini del mercato. ``modo=None`` restituisce entrambi i modi come
        ELENCO (ogni ordine porta il suo ``modo``): nessuna somma qui."""
        with self._lock:
            out: List[OrdineConto] = []
            for m in ((modo,) if modo else MODI):
                out.extend(self._ordini_del_mercato(str(market_id), m))
        return tuple(sorted(out, key=lambda x: (x.modo, x.aggiornato_ms, x.bet_id)))

    def ordine(self, bet_id: str, modo: Modo) -> Optional[OrdineConto]:
        with self._lock:
            voce = self._voci.get((modo, str(bet_id)))
            return voce.conto if voce is not None else None

    def attribuzione(self, bet_id: str, modo: Modo) -> Optional[attr.Attribuzione]:
        """Il perche' dell'autore (motivo, fonte, conflitto, provvisoria)."""
        with self._lock:
            return self._attribuzioni.get((modo, str(bet_id)))

    def mercati(self, modo: Modo) -> Tuple[str, ...]:
        with self._lock:
            return tuple(sorted(mid for (m, mid), ids in self._per_mercato.items()
                                if m == modo and ids))

    def calcolo_posizione(self, market_id: str, modo: Modo, *,
                          runner: Optional[Iterable[int]] = None,
                          tipo_scommessa: Optional[str] = None,
                          vincitori: Optional[int] = None) -> pnl_mercato.CalcoloPosizione:
        """La posizione con cio' che dichiara (estensione W1-C2): runner, tipo e
        vincitori dal book (``imposta_mercato``) se non dati; i riassunti del
        tetto dentro il P&L; motivi ``seme_non_fatto``, ``abbinato_mancante``,
        ``ordini_riassunti`` quando valgono."""
        if modo not in MODI:
            raise ValueError(f"modo non ammesso: {modo!r}")
        mid = str(market_id)
        with self._lock:
            info = self._mercati.get(mid) or _InfoMercato()
            ordini = self._ordini_del_mercato(mid, modo) + self._ordini_riassunti(mid, modo)
            extra: List[str] = []
            if not self._seme.get(modo, False):
                extra.append("seme_non_fatto")
            if any(k[0] == modo and k[1] == mid for k in self._mancanze):
                extra.append("abbinato_mancante")
            if self._riassunti.get((modo, mid)):
                extra.append("ordini_riassunti")
        calcolo = pnl_mercato.calcola(
            mid, modo, ordini,
            runner=runner if runner is not None else info.runner,
            tipo_scommessa=tipo_scommessa if tipo_scommessa is not None else info.tipo_scommessa,
            vincitori=vincitori if vincitori is not None else info.vincitori,
            tipo_mercato=info.tipo_mercato)
        for bid in calcolo.scartati:
            logger.warning("[libro] %s %s: abbinato senza prezzo medio, fuori dal P&L",
                           modo, bid)
        if extra:
            calcolo = dataclasses.replace(calcolo, motivi=tuple(calcolo.motivi) + tuple(extra))
        return calcolo

    def posizione(self, market_id: str, modo: Modo,
                  runner: Optional[Iterable[int]] = None) -> PosizioneMercato:
        """P&L di mercato "se vince" su TUTTI gli ordini abbinati del mercato di
        UN modo (contratto ``LibroOrdiniConto``; i dettagli in
        ``calcolo_posizione``)."""
        return self.calcolo_posizione(market_id, modo, runner=runner).posizione

    def stato(self) -> Mapping[str, object]:
        with self._lock:
            return {"ordini": dict(self._quanti), "conti": dict(self.conti),
                    "consumatori": len(self._consumatori), "seme": dict(self._seme),
                    "mancanze": len(self._mancanze), "indizi": len(self._indizi)}



#: i comandi che il ladder puo' offrire su un ordine. PROPOSTA per l'ondata 2
#: (referto W1-C2 par. 8): annulla/sposta SOLO sugli ordini dell'utente
#: (``desktop`` e ``sito``); sugli ordini dei bot e su quelli ``sconosciuto``
#: restano SPENTI finche' l'utente non decide altrimenti.
COMANDI_SU_ORDINE: Tuple[str, ...] = ("annulla", "sposta")


def comandi_ammessi(o: OrdineConto) -> Tuple[str, ...]:
    """I comandi del ladder ammessi su un ordine (vedi ``COMANDI_SU_ORDINE``).
    Un ordine terminale non ha comandi."""
    if o.residuo <= 0 or o.autore not in attr.AUTORI_UTENTE:
        return ()
    return COMANDI_SU_ORDINE
