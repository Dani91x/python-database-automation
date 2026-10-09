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
    restano fuori da qui, il libro riceve solo dati.

Uscite: ``ordini(market_id, modo)`` -> ``OrdineConto``; ``posizione(market_id,
modo)`` -> ``PosizioneMercato``; consumatori avvisati a ogni ordine cambiato
(``aggiungi_consumatore``: l'aggancio al ladder in ondata 2).

Regole: paper e live MAI sommati (la chiave e' ``(modo, bet_id)``; ogni lettura
chiede il modo; una posizione e' sempre di UN modo, PSB par. 7 n.21). Un
messaggio piu' vecchio di quello gia' tenuto (``ricevuto_ms`` minore) non
sovrascrive (si conta). Thread-safe: un ``RLock``; i consumatori sono chiamati
FUORI dal lucchetto e un loro errore si logga, mai propagato a chi alimenta.

NON fa: nessuna rete, nessun DB, nessun file, nessun thread proprio (gira nel
thread di chi lo alimenta); non piazza ne' annulla; non decide se un comando
sul ladder e' permesso (vedi ``comandi_ammessi`` e il referto W1-C2).

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import (Any, Callable, Dict, Iterable, List, Mapping, Optional, Protocol,
                    Set, Tuple)

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
@dataclass
class _Voce:
    ordine: OrdineDalConto
    conto: OrdineConto
    attore_dichiarato: Optional[str]


class LibroConto:
    """Implementazione di ``LibroOrdiniConto`` (vedi il docstring del modulo)."""

    def __init__(self, *, regole: Optional[attr.RegoleAttribuzione] = None,
                 max_ordini: int = MAX_ORDINI_DEFAULT) -> None:
        self._regole = regole
        self._max = int(max_ordini)
        self._lock = threading.RLock()
        self._voci: Dict[Tuple[str, str], _Voce] = {}
        self._per_mercato: Dict[Tuple[str, str], Set[str]] = {}
        self._indizi: Dict[str, Tuple[attr.Indizio, ...]] = {}
        self._consumatori: List[Callable[[OrdineConto], None]] = []
        self._attribuzioni: Dict[Tuple[str, str], attr.Attribuzione] = {}
        self._quanti: Dict[str, int] = {m: 0 for m in MODI}
        self.conti: Dict[str, int] = {"ricevuti": 0, "fuori_ordine": 0, "scartati": 0,
                                      "dimenticati": 0, "consumatori_ko": 0}

    # ------------------------------------------------------------ alimentazione
    def collega_live(self, flusso: FlussoOrdiniConto) -> None:
        """Iscrive il libro allo stream degli ordini del conto e prende la sua
        fotografia attuale (``ordini()``)."""
        flusso.aggiungi_consumatore(self.ricevi_live)
        for o in flusso.ordini():
            self.ricevi_live(o)

    def collega_prova(self, sorgente: SorgenteOrdiniProva) -> None:
        """Iscrive il libro alla sorgente degli ordini in prova."""
        sorgente.aggiungi_consumatore(self.ricevi_prova)
        for o in sorgente.ordini():
            self.ricevi_prova(o)

    def ricevi_live(self, o: OrdineDalConto) -> None:
        self._ricevi("live", o, None)

    def ricevi_prova(self, o: OrdineInProva) -> None:
        self._ricevi("paper", o.ordine, o.attore)

    def aggiungi_indizi(self, bet_id: str, indizi: Iterable[attr.Indizio]) -> Optional[OrdineConto]:
        """Indizi (DB, specchio, coda) su un ordine LIVE: si ricordano e
        l'ordine, se c'e', si riattribuisce. Ritorna l'ordine aggiornato."""
        nuovo: Optional[OrdineConto] = None
        bid = str(bet_id)
        with self._lock:
            self._indizi[bid] = tuple(self._indizi.get(bid, ())) + tuple(indizi)
            voce = self._voci.get(("live", bid))
            if voce is not None:
                nuovo = self._componi("live", voce.ordine, None)
                voce.conto = nuovo
        if nuovo is not None:
            self._avvisa(nuovo)
        return nuovo

    def _ricevi(self, modo: str, o: OrdineDalConto, attore: Optional[str]) -> None:
        if modo not in MODI:
            raise ValueError(f"modo non ammesso: {modo!r}")
        conto: Optional[OrdineConto] = None
        with self._lock:
            self.conti["ricevuti"] += 1
            chiave = (modo, str(o.bet_id))
            voce = self._voci.get(chiave)
            if voce is not None and int(o.ricevuto_ms) < int(voce.ordine.ricevuto_ms):
                self.conti["fuori_ordine"] += 1
                logger.debug("[libro] %s %s: messaggio piu' vecchio di quello tenuto, ignorato",
                             modo, o.bet_id)
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
        self._avvisa(conto)

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
        """Oltre il tetto si dimenticano gli ordini TERMINALI piu' vecchi (mai un
        ordine vivo: e' denaro sul mercato)."""
        if self._quanti[modo] <= self._max:
            return
        chiavi = [k for k in self._voci if k[0] == modo]
        terminali = sorted((self._voci[k].ordine.ricevuto_ms, k) for k in chiavi
                           if self._voci[k].ordine.stato == "EXECUTION_COMPLETE")
        for _ms, k in terminali[:len(chiavi) - self._max]:
            self._togli(k)
            self.conti["dimenticati"] += 1

    def _togli(self, chiave: Tuple[str, str]) -> None:
        voce = self._voci.pop(chiave, None)
        self._attribuzioni.pop(chiave, None)
        if voce is not None:
            self._quanti[chiave[0]] -= 1
            ids = self._per_mercato.get((chiave[0], str(voce.ordine.market_id)))
            if ids is not None:
                ids.discard(chiave[1])

    def dimentica_mercato(self, market_id: str, modo: Optional[Modo] = None) -> int:
        """Mercato chiuso: toglie i suoi ordini (di un modo o di entrambi)."""
        n = 0
        with self._lock:
            for m in ((modo,) if modo else MODI):
                for bid in list(self._per_mercato.pop((m, str(market_id)), set())):
                    self._togli((m, bid))
                    n += 1
        return n

    # ------------------------------------------------------------ consumatori
    def aggiungi_consumatore(self, cb: Callable[[OrdineConto], None]) -> None:
        with self._lock:
            self._consumatori.append(cb)

    def _avvisa(self, o: Optional[OrdineConto]) -> None:
        if o is None:
            return
        with self._lock:
            cbs = list(self._consumatori)
        for cb in cbs:
            try:
                cb(o)
            except Exception:  # noqa: BLE001 - un consumatore rotto non ferma il libro
                with self._lock:
                    self.conti["consumatori_ko"] += 1
                logger.exception("[libro] consumatore KO sull'ordine %s", o.bet_id)

    # ------------------------------------------------------------ letture
    def ordini(self, market_id: str, modo: Optional[Modo] = None) -> Tuple[OrdineConto, ...]:
        """Gli ordini del mercato. ``modo=None`` restituisce entrambi i modi come
        ELENCO (ogni ordine porta il suo ``modo``): nessuna somma qui."""
        with self._lock:
            out: List[OrdineConto] = []
            for m in ((modo,) if modo else MODI):
                for bid in self._per_mercato.get((m, str(market_id)), ()):
                    out.append(self._voci[(m, bid)].conto)
        return tuple(sorted(out, key=lambda x: (x.modo, x.aggiornato_ms, x.bet_id)))

    def ordine(self, bet_id: str, modo: Modo) -> Optional[OrdineConto]:
        with self._lock:
            voce = self._voci.get((modo, str(bet_id)))
            return voce.conto if voce is not None else None

    def attribuzione(self, bet_id: str, modo: Modo) -> Optional[attr.Attribuzione]:
        """Il perche' dell'autore (motivo, fonte, conflitto) di un ordine."""
        with self._lock:
            return self._attribuzioni.get((modo, str(bet_id)))

    def mercati(self, modo: Modo) -> Tuple[str, ...]:
        with self._lock:
            return tuple(sorted(mid for (m, mid), ids in self._per_mercato.items()
                                if m == modo and ids))

    def posizione(self, market_id: str, modo: Modo,
                  runner: Optional[Iterable[int]] = None) -> PosizioneMercato:
        """P&L di mercato "se vince" su TUTTI gli ordini abbinati del mercato di
        UN modo (``pnl_mercato.calcola``). Gli ordini scartati dal calcolo
        (abbinato senza prezzo medio) si loggano."""
        if modo not in MODI:
            raise ValueError(f"modo non ammesso: {modo!r}")
        calcolo = pnl_mercato.calcola(market_id, modo, self.ordini(market_id, modo),
                                      runner=runner)
        for bid in calcolo.scartati:
            logger.warning("[libro] %s %s: abbinato senza prezzo medio, fuori dal P&L",
                           modo, bid)
        return calcolo.posizione

    def stato(self) -> Mapping[str, object]:
        with self._lock:
            return {"ordini": dict(self._quanti), "conti": dict(self.conti),
                    "consumatori": len(self._consumatori)}


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
