# -*- coding: utf-8 -*-
"""misura_ingresso_passivo — QUANTO VALEREBBE ENTRARE DENTRO LO SPREAD.

LA DOMANDA (REFERTO_V3_2026-09-16 §1 e §7.5, K_MISURATO_2026-09-16 §5.1):
Omega oggi entra prendendo il best ``availableToLay`` (FOK, attraversando lo
spread) e la misura di k dice che a quel prezzo il bias non basta (k < 1 in
OGNI fascia). Se invece APPOGGIASSE una lay DENTRO lo spread e aspettasse:

    quanto spesso sarebbe stata abbinata sulle registrazioni reali,
    a che prezzo, dopo quanta attesa, e quanto vale la differenza in k e in EV?

QUESTO MODULO NON DECIDE NIENTE E NON TOCCA LA STRATEGIA. E' uno strumento di
MISURA: legge le registrazioni, simula ordini appoggiati che non sono mai
esistiti, e scrive numeri. Non scrive sul database, non piazza niente, non
cambia il motore.

---------------------------------------------------------------------------
LA CATENA E' QUELLA DI PRODUZIONE (banco comune)
---------------------------------------------------------------------------
    _live_raw/<id>/<id>.raw.jsonl     stream NATIVO Betfair registrato
      -> flumine                       FlumineSimulation + HistoricalStream
      -> banco_comune.replay_evento    lo stesso driver del replay di Omega
      -> SCANNER VERO                  safe_strategy.service.Scanner
      -> riga di scan VERA             minuto e punteggio dal sidecar IPS
      -> qui                           i candidati e gli ordini appoggiati

Il minuto e il punteggio NON vengono mai dall'orologio: vengono dalla riga
dello scanner, che li prende dal sidecar dei punteggi come in produzione.

---------------------------------------------------------------------------
LA REGOLA DELLA CODA: E' QUELLA DI FLUMINE, NON UNA NOSTRA
---------------------------------------------------------------------------
Il matching degli ordini appoggiati lo fa ``flumine.simulation.simulatedorder.
SimulatedOrder``, cioe' la STESSA classe che abbina gli ordini di Omega nel
replay e nel banco comune. Non e' stata riscritta: viene istanziata e chiamata.

  1. ARRIVO IN CODA — ``SimulatedOrder.place`` (simulatedorder.py:64-240).
     Un LAY a prezzo ``P``: se ``best availableToLay <= P`` si abbina SUBITO
     (e allora non e' un ingresso passivo: qui quel caso si scarta). Se
     ``P < best availableToLay`` l'ordine si mette in coda, e la sua
     POSIZIONE IN CODA (``_piq``) e' la size gia' presente a quel prezzo sul
     lato ``availableToBack`` — cioe' esattamente "la quantita' che era gia'
     in coda a quel prezzo quando siamo arrivati".
  2. ABBINAMENTO — ``SimulatedOrder._process_traded`` /
     ``_calculate_process_traded`` (simulatedorder.py:457-496). A ogni
     aggiornamento si guarda il volume SCAMBIATO (``trd``/``tv`` dello stream)
     comparso DOPO il nostro arrivo: il delta per prezzo lo calcola
     ``flumine.markets.middleware.RunnerAnalytics``. Per un LAY conta il
     volume a prezzo ``<= P``; di quel volume flumine ne prende META'
     (``traded_size / 2``: il ``trd`` di Betfair conta le due gambe dello
     stesso abbinamento), e lo usa PRIMA per consumare ``_piq`` e solo per
     l'eccedenza per riempire noi. Finche' la coda davanti non e' finita, noi
     non prendiamo un centesimo.
  3. PREZZI DISPONIBILI — ``config.simulation_available_prices`` resta
     **False** (il default di flumine): il semplice fatto che il book si
     muova attraverso il nostro prezzo NON ci abbina. Serve volume scambiato.
     E' il ramo PRUDENTE, ed e' dichiarato.
  4. ISOLAMENTO — ogni candidato e' un MONDO A SE'. Nel controfattuale "se
     avessi appoggiato QUESTO ordine" esiste un ordine solo, quindi ogni
     ``SimulatedOrder`` riceve la SUA copia del delta scambiato. Se invece si
     lasciassero competere fra loro i tre livelli (a/b/c) dello stesso runner,
     il livello piu' alto mangerebbe il volume del piu' basso e la misura
     direbbe una cosa che nel controfattuale non succede.

SI AGGIUNGONO DUE MORTI CHE FLUMINE DA SOLO NON DA' SEMPRE, e sono le stesse
del banco comune (``MotoreReplay._lapse_alla_sospensione``, che le documenta
con le fonti Betfair):
  * SOSPENSIONE IN GIOCO (gol, rigore, rosso) -> l'ordine LAPSE non abbinato
    viene CANCELLATO prima che il mercato riapra. Applicata PRIMA del
    matching sul book della sospensione;
  * CAMBIO DI PUNTEGGIO visto dallo scanner -> stessa cosa, anche quando la
    sospensione in quella registrazione non si vede. E' una morte in PIU'
    rispetto a Betfair, quindi va nella direzione prudente (meno abbinati).
E la morte per FINE FINESTRA: oltre il minuto di chiusura della gamba
l'ordine non vale piu' (Omega non lo terrebbe).

IL BET DELAY NON E' REGALATO. L'ordine viene deciso al minuto d'ingresso sul
book di quell'istante (come farebbe il bot), ma ARRIVA A MERCATO solo sul
primo book successivo a ``place_latency + betDelay`` — la stessa formula che
flumine usa per i pacchetti (``orderpackage.calc_simulated_delay``). Se in
quel momento il mercato e' sospeso, l'ordine non entra affatto.

---------------------------------------------------------------------------
Uso
---------------------------------------------------------------------------
    python -m Betfair.omega.tools.misura_ingresso_passivo
    python -m Betfair.omega.tools.misura_ingresso_passivo --eventi 35760084
    python -m Betfair.omega.tools.misura_ingresso_passivo --out percorso.json

Scrive ``Betfair/omega/data/ingresso_passivo_2026-09-17.json``. Sola lettura
sul disco delle registrazioni, nessuna riga di database.
ASCII-only nel codice; commenti in italiano.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# COSTANTI DELLA MISURA (tutte dichiarate, nessuna nascosta)
# ---------------------------------------------------------------------------
# Stake della gamba V3: 1,00 EUR in lay, sempre (REFERTO_V3 §3.3).
STAKE_EUR = 1.00
# Commissione Betfair del conto (la stessa di misura_k e del motore).
COMMISSIONE = 0.05
# I tre livelli di prezzo passivo che si mettono a confronto col tocco.
LIVELLI: Tuple[str, ...] = ("a", "b", "c")
DESCRIZIONE_LIVELLI = {
    "a": "un tick sotto il best lay (davanti alla coda del lay)",
    "b": "mid fra best back e best lay, arrotondato al tick",
    "c": "al best back (dietro tutta la coda dei back)",
}
# Minuti d'ingresso: una GRIGLIA dentro la finestra della gamba. Con un solo
# istante per gamba il campione sarebbe di 39 osservazioni per mercato.
PASSO_GRIGLIA_MINUTI = 5
# tolleranza (minuti) entro cui un minuto d'ingresso e' ancora "quello": la
# riga di scan non arriva esattamente al minuto tondo.
TOLLERANZA_MINUTI = 2
# osservazione dopo un abbinamento, per la SELEZIONE AVVERSA (secondi)
OSSERVAZIONE_DOPO_FILL_S = 60.0
# finestra (secondi) entro cui un gol/una sospensione DOPO il fill lo marca
# come "abbinato subito prima del gol"
FINESTRA_PRE_GOL_S = 120.0
# sotto questo numero di celle abbinate CON esito, il k della riga non e' una
# misura (stesso spirito di ``misura_k.N_MIN_SECCHIO``, scalato al campione che
# le registrazioni possono dare).
N_MIN_ABBINATI = 30

MERCATI = {
    "HALF_TIME_SCORE": "1T",
    "CORRECT_SCORE": "2T",
}


# ---------------------------------------------------------------------------
# scala tick: quella UFFICIALE (betfairlightweight via flumine.utils), la
# stessa che usa gia' lo scalper del repo. Non se ne riscrive un'altra.
# ---------------------------------------------------------------------------
def _tick(prezzo: float, passi: int) -> Optional[float]:
    from flumine.utils import get_nearest_price, price_ticks_away

    try:
        base = get_nearest_price(float(prezzo))
        fuori = price_ticks_away(base, int(passi))
    except (TypeError, ValueError):
        return None
    if fuori is None or not math.isfinite(float(fuori)):
        return None
    return float(fuori)


def ticks_fra(p_basso: Optional[float], p_alto: Optional[float],
              max_ticks: int = 400) -> Optional[int]:
    """Numero di tick Betfair fra due prezzi (0 se uguali, None se non validi)."""
    from flumine.utils import get_nearest_price, price_ticks_away

    if not p_basso or not p_alto or float(p_alto) < float(p_basso):
        return None
    p = get_nearest_price(float(p_basso))
    obiettivo = get_nearest_price(float(p_alto))
    if abs(p - obiettivo) < 1e-9:
        return 0
    for t in range(1, max_ticks + 1):
        p = price_ticks_away(p, 1)
        if p >= obiettivo - 1e-9:
            return t
    return None


def prezzi_passivi(best_back: Optional[float],
                   best_lay: Optional[float]) -> Dict[str, Optional[float]]:
    """I tre prezzi passivi candidati. ``None`` = livello non costruibile.

    Un prezzo passivo di LAY deve stare STRETTAMENTE SOTTO il best lay (se no
    e' un ordine al tocco, che si abbina subito) e mai sotto il best back (li'
    saremmo dietro a tutta la coda dei back a un prezzo che nessuno prende).
    """
    from flumine.utils import get_nearest_price

    fuori: Dict[str, Optional[float]] = {"a": None, "b": None, "c": None}
    if not best_lay or float(best_lay) <= 1.01:
        return fuori
    bl = get_nearest_price(float(best_lay))
    bb = get_nearest_price(float(best_back)) if best_back else None
    # (a) un tick sotto il best lay
    a = _tick(bl, -1)
    if a is not None and a < bl - 1e-9 and (bb is None or a >= bb - 1e-9):
        fuori["a"] = a
    if bb is None or bb >= bl - 1e-9:
        return fuori          # nessuno spread misurabile: (b) e (c) restano vuoti
    # (c) al best back
    fuori["c"] = float(bb)
    # (b) mid fra best back e best lay, al tick piu' vicino, clampato dentro
    mid = get_nearest_price((bb + bl) / 2.0)
    if mid >= bl - 1e-9:
        mid = _tick(bl, -1) or bb
    if mid <= bb + 1e-9:
        mid = bb
    fuori["b"] = float(mid)
    return fuori


# ---------------------------------------------------------------------------
# il candidato misurato
# ---------------------------------------------------------------------------
@dataclass
class Candidato:
    event_id: str
    mercato: str                 # CORRECT_SCORE | HALF_TIME_SCORE
    gamba: str                   # 1T | 2T
    market_id: str
    selection_id: int
    nome: str
    minuto_ingresso: int
    minuto_riga: int
    punteggio: Tuple[int, int]
    prezzo_tocco: float
    size_tocco: float
    prezzo_back: Optional[float]
    size_back: Optional[float]
    spread_tick: Optional[int]
    livello: str
    prezzo_passivo: float
    ticks_guadagnati: Optional[int]
    p_impl_tocco: float
    p_impl_passivo: float
    fascia: str                  # secchio di p_impl_tocco (la cella non cambia secchio)
    esito_cella: Optional[bool] = None
    piazzato: bool = False
    motivo_non_piazzato: str = ""
    coda_davanti: float = 0.0
    abbinato: bool = False
    size_abbinata: float = 0.0
    prezzo_ottenuto: Optional[float] = None
    attesa_s: Optional[float] = None
    morte: str = ""
    attraversato: bool = False
    pre_gol: bool = False

    def a_dizionario(self) -> Dict[str, Any]:
        d = dict(self.__dict__)
        d["punteggio"] = list(self.punteggio)
        return d


# ---------------------------------------------------------------------------
# un ordine appoggiato: il guscio attorno al SimulatedOrder di flumine
# ---------------------------------------------------------------------------
class Appoggiato:
    """Un ordine passivo che non e' mai esistito, abbinato da flumine."""

    def __init__(self, candidato: Any, *, attivo_da_ms: int,
                 pt_decisione_ms: int = 0, size: float = STAKE_EUR,
                 fok: bool = False) -> None:
        self.cand = candidato
        self.attivo_da_ms = int(attivo_da_ms)
        self.pt_decisione_ms = int(pt_decisione_ms)
        # M1 usa lo stake fisso di 1,00 EUR; M1-bis dimensiona a LIABILITY fissa
        # (`size = liability/(L-1)`), quindi la size viaggia con l'ordine.
        self.size = float(size)
        # `fok`: l'ordine che PRENDE al tocco (`timeInForce=FILL_OR_KILL`), cioe'
        # esattamente quello che Omega manda oggi. Il passivo resta LIMIT semplice.
        self.fok = bool(fok)
        # annullo con latenza dichiarata: fino a `annulla_a_ms` l'ordine e'
        # ancora a mercato e puo' abbinarsi (come in produzione)
        self.annulla_a_ms: Optional[int] = None
        self.ordine: Any = None
        self.sim: Any = None
        self.in_attesa = True      # deciso, ma non ancora arrivato a mercato
        self.vivo = False          # a mercato e non ancora chiuso
        self.chiuso = False
        self.fill_ms: Optional[int] = None
        self.fine_osservazione_ms: Optional[int] = None
        self.minimo_atl_dopo: Optional[float] = None

    # ---------------------------------------------------------------- vita
    def piazza(self, cliente: Any, market_book: Any, strategia: Any) -> None:
        """Mette l'ordine a mercato usando il ``place`` VERO di flumine."""
        from flumine.order.order import BetfairOrder
        from flumine.order.orderpackage import BetfairOrderPackage, OrderPackageType
        from flumine.order.ordertype import LimitOrder
        from flumine.order.trade import Trade

        self.in_attesa = False
        c = self.cand
        if str(getattr(market_book, "status", "") or "") != "OPEN":
            c.motivo_non_piazzato = "mercato_non_aperto"
            self.chiuso = True
            return
        runner = runner_di(market_book, c.selection_id)
        if runner is None or str(getattr(runner, "status", "") or "") != "ACTIVE":
            c.motivo_non_piazzato = "runner_non_attivo"
            self.chiuso = True
            return
        md = getattr(market_book, "market_definition", None)
        bet_delay = int(getattr(md, "bet_delay", 0) or 0) if md is not None else 0
        trade = Trade(market_id=str(market_book.market_id),
                      selection_id=int(c.selection_id), handicap=0.0,
                      strategy=strategia)
        ordine = BetfairOrder(
            trade=trade, side="LAY",
            order_type=LimitOrder(
                price=float(c.prezzo_passivo), size=float(self.size),
                persistence_type="LAPSE",
                time_in_force=("FILL_OR_KILL" if self.fok else None),
                min_fill_size=(0.0 if self.fok else None)))
        # il client e' quello VERO del quadro simulato: serve a flumine per
        # `best_price_execution` e `simulated_full_match` (che resta False: un
        # place non e' un fill)
        ordine.update_client(cliente)
        pacchetto = BetfairOrderPackage(
            client=cliente, market_id=str(market_book.market_id), orders=[ordine],
            package_type=OrderPackageType.PLACE, bet_delay=bet_delay)
        istruzione = ordine.create_place_instruction()
        risposta = ordine.simulated.place(pacchetto, market_book, istruzione, 1)
        stato = str(getattr(risposta, "status", "") or "")
        if stato != "SUCCESS":
            c.motivo_non_piazzato = "place_" + (stato or "ignoto")
            self.chiuso = True
            return
        self.ordine = ordine
        self.sim = ordine.simulated
        self.vivo = True
        c.piazzato = True
        c.coda_davanti = float(getattr(self.sim, "_piq", 0.0) or 0.0)
        # se flumine ha gia' abbinato qualcosa nel ``place``, NON era un
        # ingresso passivo: il prezzo era gia' disponibile. Si dichiara e si
        # esclude dalla misura.
        if float(getattr(self.sim, "size_matched", 0.0) or 0.0) > 0:
            if self.fok:
                # il FOK che PRENDE al tocco: il fill immediato E' il suo scopo.
                # Un FOK riempito solo in parte NON e' un ingresso: Betfair ha
                # cancellato il residuo e la gamba non esiste alla size voluta.
                abbinata = float(getattr(self.sim, "size_matched", 0.0) or 0.0)
                if abbinata >= self.size - max(0.005, 0.005 * self.size):
                    self._registra_fill(market_book)
                else:
                    c.morte = "fok_parziale"
                    c.size_abbinata = round(abbinata, 4)
                    self.vivo = False
                    self.chiuso = True
                return
            c.motivo_non_piazzato = "abbinato_al_place_non_passivo"
            c.piazzato = False
            self.vivo = False
            self.chiuso = True
        elif self.fok:
            # FOK senza controparte: Betfair lo cancella all'istante
            c.morte = "fok_senza_controparte"
            self.vivo = False
            self.chiuso = True

    def annulla(self, pt_ms: int, latenza_s: float) -> None:
        """Annullo con la LATENZA DICHIARATA: l'ordine resta a mercato (e puo'
        abbinarsi) finche' Betfair non lo toglie. E' la stessa idea del bet
        delay in piazzamento: una chiamata REST costa tempo vero."""
        if not self.vivo or self.annulla_a_ms is not None:
            return
        self.annulla_a_ms = int(pt_ms) + int(float(latenza_s) * 1000)

    def in_annullo(self) -> bool:
        return self.vivo and self.annulla_a_ms is not None

    def uccidi(self, motivo: str) -> None:
        if self.in_attesa and not self.chiuso:
            self.in_attesa = False
            self.chiuso = True
            self.cand.motivo_non_piazzato = self.cand.motivo_non_piazzato or motivo
            return
        if not self.vivo:
            return
        self.vivo = False
        self.chiuso = True
        self.cand.morte = motivo

    # ------------------------------------------------------------ matching
    def applica(self, market_book: Any, runner: Any,
                scambiato: Dict[float, float]) -> None:
        """Il matching di flumine su questo book (copia isolata del delta)."""
        if not self.vivo or self.sim is None:
            return
        self.sim(market_book, (runner, scambiato))
        residuo = float(getattr(self.sim, "size_remaining", 0.0) or 0.0)
        abbinata = float(getattr(self.sim, "size_matched", 0.0) or 0.0)
        self.cand.size_abbinata = round(abbinata, 4)
        if abbinata >= self.size - max(0.005, 0.005 * self.size):
            self._registra_fill(market_book)
        elif residuo <= 0.0:
            # lapsata/annullata da flumine senza riempimento pieno
            self.uccidi(self.cand.morte or "residuo_zero")

    def _registra_fill(self, market_book: Any) -> None:
        c = self.cand
        c.abbinato = True
        c.morte = "abbinato"
        abbinamenti = list(getattr(self.sim, "matched", ()) or ())
        pt = int(abbinamenti[-1][0]) if abbinamenti else int(
            getattr(market_book, "publish_time_epoch", 0) or 0)
        self.fill_ms = pt
        prezzo = float(getattr(self.sim, "average_price_matched", 0.0) or 0.0)
        c.prezzo_ottenuto = prezzo if prezzo > 1.0 else float(c.prezzo_passivo)
        self.vivo = False
        self.fine_osservazione_ms = pt + int(OSSERVAZIONE_DOPO_FILL_S * 1000)

    # -------------------------------------------------- selezione avversa
    def osserva(self, market_book: Any) -> None:
        """Dopo il fill: il book e' andato SOTTO il nostro prezzo?"""
        if self.fill_ms is None or self.fine_osservazione_ms is None:
            return
        pt = int(getattr(market_book, "publish_time_epoch", 0) or 0)
        if pt > self.fine_osservazione_ms:
            return
        runner = runner_di(market_book, self.cand.selection_id)
        if runner is None:
            return
        from flumine.utils import get_price

        atl = get_price(runner.ex.available_to_lay, 0)
        if atl is None:
            return
        if self.minimo_atl_dopo is None or float(atl) < self.minimo_atl_dopo:
            self.minimo_atl_dopo = float(atl)
        riferimento = float(self.cand.prezzo_ottenuto or self.cand.prezzo_passivo)
        if float(atl) < riferimento - 1e-9:
            self.cand.attraversato = True


def runner_di(market_book: Any, selection_id: int) -> Any:
    for r in getattr(market_book, "runners", ()) or ():
        if int(getattr(r, "selection_id", 0) or 0) == int(selection_id):
            return r
    return None


# ---------------------------------------------------------------------------
# l'esito vero della cella, dal marketDefinition finale
# ---------------------------------------------------------------------------
def esiti_dal_catalogo(catalogo: Any) -> Dict[str, Optional[int]]:
    """market_id -> selectionId VINCITORE (None se il mercato non e' settlato).

    ``Catalogo.definizioni`` (``replay_registrazioni.leggi_catalogo``) conserva
    la successione dei ``marketDefinition``: l'ultima porta gli stati dei
    runner, e il WINNER e' l'esito vero della cella.
    """
    fuori: Dict[str, Optional[int]] = {}
    for mid, mtype in catalogo.tipi.items():
        if str(mtype).upper() not in MERCATI:
            continue
        vincitore: Optional[int] = None
        for _pt, _stato, _inplay, stati in reversed(catalogo.definizioni.get(mid, [])):
            vinti = [sid for sid, st in stati.items() if str(st).upper() == "WINNER"]
            if vinti:
                vincitore = int(vinti[0])
                break
        fuori[str(mid)] = vincitore
    return fuori


# ---------------------------------------------------------------------------
# LA MISURA SU UNA REGISTRAZIONE
# ---------------------------------------------------------------------------
class MisuraEvento:
    """Arma i candidati ai minuti d'ingresso e li fa vivere sul book vero."""

    def __init__(self, event_id: str, *, catalogo: Any, esiti: Dict[str, Optional[int]],
                 parametri: Dict[str, Any]) -> None:
        self.event_id = str(event_id)
        self.catalogo = catalogo
        self.esiti = esiti
        self.par = parametri
        # market_id -> market_type, solo CORRECT_SCORE e HALF_TIME_SCORE
        self.mercati: Dict[str, str] = {
            str(mid): str(mt).upper()
            for mid, mt in catalogo.tipi.items() if str(mt).upper() in MERCATI}
        self.per_tipo: Dict[str, str] = {}
        for mid, mt in self.mercati.items():
            self.per_tipo.setdefault(mt, mid)
        self.ultimo_book: Dict[str, Any] = {}
        self.appoggiati: Dict[str, List[Appoggiato]] = {}
        self.armati: set = set()
        self.punteggio: Optional[Tuple[int, int]] = None
        self._stato_mercato: Dict[str, str] = {}
        self.cliente: Any = None
        self.strategia: Any = None
        self.candidati: List[Candidato] = []
        self.note: List[str] = []
        self.minuti_visti: List[int] = []

    # -------------------------------------------------------------- aggancio
    def aggancia(self, strategia: Any) -> None:
        """Avvolge ``process_market_book`` per vedere OGNI book, dopo il
        middleware simulato (che e' quello che calcola il delta scambiato)."""
        self.strategia = strategia
        originale = strategia.process_market_book

        def avvolto(market: Any, market_book: Any) -> None:
            try:
                self._su_book(market, market_book)
            finally:
                originale(market, market_book)

        strategia.process_market_book = avvolto

    # ----------------------------------------------------------- ogni book
    def _su_book(self, market: Any, market_book: Any) -> None:
        mid = str(getattr(market_book, "market_id", "") or "")
        if mid not in self.mercati:
            return
        if self.cliente is None:
            quadro = getattr(market, "flumine", None)
            clienti = getattr(quadro, "clients", None)
            if clienti is not None:
                try:
                    self.cliente = clienti.get_default()
                except Exception:  # noqa: BLE001 - il client e' diagnostica
                    self.cliente = None
            if self.cliente is None:
                from ...stream.backtest import banco_comune as BC

                self.cliente = BC.cliente_simulato()
        self.ultimo_book[mid] = market_book
        pt = int(getattr(market_book, "publish_time_epoch", 0) or 0)
        stato = str(getattr(market_book, "status", "") or "")
        md = getattr(market_book, "market_definition", None)
        in_gioco = bool(getattr(md, "in_play", False)) if md is not None else False
        prima = self._stato_mercato.get(mid)
        self._stato_mercato[mid] = stato
        sospeso_ora = (stato == "SUSPENDED" and prima != "SUSPENDED" and in_gioco)

        analitiche = (getattr(market, "context", {}) or {}).get("simulated") or {}
        lista = self.appoggiati.get(mid) or ()
        for ap in lista:
            # 1) l'ordine deciso entra a mercato quando Betfair lo rilascia
            if ap.in_attesa and not ap.chiuso and pt >= ap.attivo_da_ms:
                if sospeso_ora or stato != "OPEN":
                    ap.uccidi("sospensione_prima_dell_arrivo")
                else:
                    ap.piazza(self.cliente, market_book, self.strategia)
                continue          # mai matching sul book del proprio arrivo
            # 2) la sospensione in gioco uccide PRIMA del matching
            if sospeso_ora and ap.vivo:
                ap.uccidi("sospensione")
                continue
            if ap.vivo:
                ra = analitiche.get((int(ap.cand.selection_id), 0.0))
                if ra is None:
                    continue
                ap.applica(market_book, ra.runner, dict(ra.traded))
            elif ap.fill_ms is not None:
                if sospeso_ora and pt - ap.fill_ms <= FINESTRA_PRE_GOL_S * 1000:
                    ap.cand.pre_gol = True
                ap.osserva(market_book)

    # ------------------------------------------------------------- ogni giro
    def giro(self, *, db: Any, market: Any, now: Any, row: Optional[dict],
             banco: Any, strategia: Any) -> None:
        """Il "servizio" del banco: qui si decide se armare i candidati."""
        if not row:
            return
        # la riga di scan e' {event_id, sport, updated_at, payload}: minuto e
        # punteggio stanno nel PAYLOAD, che e' esattamente dove li legge il
        # servizio di Omega (`omega_service._feed_row`).
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else row
        minuto = payload.get("minute")
        sh, sa = payload.get("score_home"), payload.get("score_away")
        if minuto is None or sh is None or sa is None:
            return
        minuto = int(minuto)
        punteggio = (int(sh), int(sa))
        self.minuti_visti.append(minuto)
        if self.punteggio is not None and punteggio != self.punteggio:
            for lista in self.appoggiati.values():
                for ap in lista:
                    if ap.vivo or ap.in_attesa:
                        ap.uccidi("gol")
                    elif ap.fill_ms is not None and not ap.cand.pre_gol:
                        ultimo = self.ultimo_book.get(str(ap.cand.market_id))
                        pt = int(getattr(ultimo, "publish_time_epoch", 0) or 0)
                        if pt and pt - ap.fill_ms <= FINESTRA_PRE_GOL_S * 1000:
                            ap.cand.pre_gol = True
        self.punteggio = punteggio

        # chiusura per fine finestra
        for mid, mt in self.mercati.items():
            fine = int(self.par["finestre"][mt][1])
            if minuto <= fine:
                continue
            for ap in self.appoggiati.get(mid, ()):  # noqa: B007
                if ap.vivo or ap.in_attesa:
                    ap.uccidi("fine_finestra")

        # armamento
        for mt, mid in self.per_tipo.items():
            inizio, fine = self.par["finestre"][mt]
            for m in self.par["minuti"][mt]:
                chiave = (mid, m)
                if chiave in self.armati:
                    continue
                if minuto < m:
                    continue
                if minuto > m + TOLLERANZA_MINUTI or minuto > fine:
                    self.armati.add(chiave)      # occasione persa: non si recupera
                    continue
                self.armati.add(chiave)
                self._arma(mid, mt, m, minuto, punteggio)

    # ------------------------------------------------------------- armamento
    def _arma(self, market_id: str, mercato: str, minuto_ingresso: int,
              minuto_riga: int, punteggio: Tuple[int, int]) -> None:
        from flumine.utils import get_price, get_size

        from . import misura_k as MK

        book = self.ultimo_book.get(market_id)
        if book is None:
            return
        if str(getattr(book, "status", "") or "") != "OPEN":
            return
        md = getattr(book, "market_definition", None)
        if md is not None and not bool(getattr(md, "in_play", False)):
            return
        pt = int(getattr(book, "publish_time_epoch", 0) or 0)
        ritardo_ms = int(self._ritardo_s(book) * 1000)
        nomi = self.catalogo.nomi.get(str(market_id), {})
        vincitore = self.esiti.get(str(market_id))
        sh, sa = punteggio
        for runner in getattr(book, "runners", ()) or ():
            if str(getattr(runner, "status", "") or "") != "ACTIVE":
                continue
            sid = int(getattr(runner, "selection_id", 0) or 0)
            nome = str(nomi.get(sid) or "")
            coppia = _scoreline(nome)
            if coppia is None:
                continue                      # mai gli aggregati (come select_by_model)
            h, a = coppia
            if h < sh or a < sa:
                continue                      # irraggiungibile
            if (h - sh) + (a - sa) < int(self.par["min_goal_distance"]):
                continue                      # punteggio corrente o adiacente
            atl = get_price(runner.ex.available_to_lay, 0)
            atl_size = get_size(runner.ex.available_to_lay, 0) or 0.0
            if atl is None or not math.isfinite(float(atl)):
                continue
            if float(atl) < self.par["price_min"] or float(atl) > self.par["price_max"]:
                continue                      # fuori banda
            if float(atl_size) < float(self.par["min_lay_liquidity"]):
                continue                      # liquidita' sotto il minimo di produzione
            atb = get_price(runner.ex.available_to_back, 0)
            atb_size = get_size(runner.ex.available_to_back, 0) or 0.0
            p_tocco = MK.p_implicita(float(atl), COMMISSIONE)
            if p_tocco is None:
                continue
            spread = ticks_fra(atb, atl) if atb else None
            prezzi = prezzi_passivi(atb, float(atl))
            esito = None if vincitore is None else bool(int(vincitore) == sid)
            for livello in LIVELLI:
                prezzo = prezzi.get(livello)
                if prezzo is None:
                    continue
                p_pass = MK.p_implicita(float(prezzo), COMMISSIONE)
                if p_pass is None:
                    continue
                cand = Candidato(
                    event_id=self.event_id, mercato=mercato,
                    gamba=MERCATI[mercato], market_id=str(market_id),
                    selection_id=sid, nome=nome,
                    minuto_ingresso=int(minuto_ingresso), minuto_riga=int(minuto_riga),
                    punteggio=(sh, sa), prezzo_tocco=float(atl),
                    size_tocco=float(atl_size),
                    prezzo_back=(float(atb) if atb else None),
                    size_back=float(atb_size), spread_tick=spread,
                    livello=livello, prezzo_passivo=float(prezzo),
                    ticks_guadagnati=ticks_fra(prezzo, float(atl)),
                    p_impl_tocco=float(p_tocco), p_impl_passivo=float(p_pass),
                    fascia=MK.secchio_di(float(p_tocco)), esito_cella=esito)
                ap = Appoggiato(cand, attivo_da_ms=pt + ritardo_ms,
                                pt_decisione_ms=pt)
                self.appoggiati.setdefault(str(market_id), []).append(ap)
                self.candidati.append(cand)

    @staticmethod
    def _ritardo_s(book: Any) -> float:
        """``place_latency + betDelay``: la stessa formula di flumine."""
        import flumine.config as fconf

        md = getattr(book, "market_definition", None)
        bet_delay = int(getattr(md, "bet_delay", 0) or 0) if md is not None else 0
        return float(getattr(fconf, "place_latency", 0.120)) + float(bet_delay)

    # --------------------------------------------------------------- chiusura
    def chiudi(self) -> None:
        """Alla fine della registrazione: chi e' ancora appoggiato e' scaduto."""
        for lista in self.appoggiati.values():
            for ap in lista:
                if ap.vivo or ap.in_attesa:
                    ap.uccidi("registrazione_finita")
                if ap.fill_ms is not None and ap.pt_decisione_ms:
                    ap.cand.attesa_s = round(
                        (ap.fill_ms - int(ap.pt_decisione_ms)) / 1000.0, 1)


def _scoreline(nome: str) -> Optional[Tuple[int, int]]:
    from .. import omega_engine as E

    return E.parse_scoreline(nome or "")


def misura_evento(event_id: str, cartella: str, *,
                  parametri: Dict[str, Any]) -> Tuple[List[Candidato], Dict[str, Any]]:
    """Fa vivere una registrazione e torna i candidati misurati."""
    from ...stream.backtest import banco_comune as BC
    from .replay_registrazioni import leggi_catalogo

    raw = os.path.join(cartella, str(event_id), "%s.raw.jsonl" % event_id)
    diagnostica: Dict[str, Any] = {"event_id": str(event_id), "errori": [], "note": []}
    if not os.path.exists(raw):
        diagnostica["errori"].append("registrazione assente")
        return [], diagnostica
    catalogo = leggi_catalogo(raw)
    esiti = esiti_dal_catalogo(catalogo)
    diagnostica["mercati"] = {str(mt): str(mid) for mid, mt in catalogo.tipi.items()
                              if str(mt).upper() in MERCATI}
    diagnostica["esiti"] = {k: v for k, v in esiti.items()}
    misura = MisuraEvento(event_id, catalogo=catalogo, esiti=esiti, parametri=parametri)
    t0 = time.time()
    esito = BC.replay_evento(event_id=str(event_id), cartella=cartella,
                             servizio=misura.giro, nomi_extra=catalogo.nomi,
                             su_strategia=misura.aggancia)
    misura.chiudi()
    diagnostica["durata_s"] = round(time.time() - t0, 1)
    diagnostica["errori"].extend(list(esito.errori))
    diagnostica["note"].extend(list(esito.note))
    diagnostica["giri"] = esito.giri
    diagnostica["tick"] = esito.tick
    return misura.candidati, diagnostica


# ---------------------------------------------------------------------------
# AGGREGAZIONE — le stesse fasce e lo stesso bootstrap di misura_k
# ---------------------------------------------------------------------------
def _mediana(valori: Sequence[float]) -> Optional[float]:
    v = [float(x) for x in valori if x is not None and math.isfinite(float(x))]
    return statistics.median(v) if v else None


def aggrega(candidati: Sequence[Candidato], *, giri_boot: int = 2000,
            per_fascia: bool = True, per_mercato: bool = True) -> Dict[str, Any]:
    """Tabelle con k al tocco e k passivo.

    ``per_fascia``/``per_mercato`` scelgono quanto e' fine il raggruppamento:
    mercato x fascia x livello (il dettaglio), mercato x livello (le fasce
    accorpate, dove il dettaglio ha troppi pochi casi) o solo livello.
    """
    from . import misura_k as MK

    etichette = [s[2] for s in MK.SECCHI]

    def _chiave(c: Candidato) -> Tuple[str, str, str]:
        return ((c.mercato if per_mercato else "tutti"),
                (c.fascia if per_fascia else "tutte"), c.livello)

    righe: List[Dict[str, Any]] = []
    chiavi = sorted({_chiave(c) for c in candidati},
                    key=lambda t: (t[0], etichette.index(t[1]) if t[1] in etichette else 99, t[2]))
    for mercato, fascia, livello in chiavi:
        gruppo = [c for c in candidati if _chiave(c) == (mercato, fascia, livello)]
        piazzati = [c for c in gruppo if c.piazzato]
        abbinati = [c for c in piazzati if c.abbinato]
        con_esito = [c for c in abbinati if c.esito_cella is not None]
        per_partita: Dict[str, List[int]] = {}
        somma_pass = somma_tocco = 0.0
        uscite = 0
        for c in con_esito:
            cella = per_partita.setdefault(c.event_id, [0, 0])
            cella[0] += 1 if c.esito_cella else 0
            cella[1] += 1
            uscite += 1 if c.esito_cella else 0
            p_ott = MK.p_implicita(float(c.prezzo_ottenuto or c.prezzo_passivo), COMMISSIONE)
            somma_pass += float(p_ott or 0.0)
            somma_tocco += float(c.p_impl_tocco)
        n_esito = len(con_esito)
        p_reale = (uscite / n_esito) if n_esito else None
        lo_b, hi_b = (MK.bootstrap_grappolo({k: (v[0], v[1]) for k, v in per_partita.items()},
                                            giri=giri_boot) if per_partita else (0.0, 1.0))
        p_pass_media = (somma_pass / n_esito) if n_esito else None
        p_tocco_media = (somma_tocco / n_esito) if n_esito else None

        def _k(p_media: Optional[float], p: Optional[float]) -> Optional[float]:
            if not p_media or not p or p <= 0:
                return None
            return round(p_media / p, 3)

        riga = {
            "mercato": mercato, "gamba": MERCATI.get(mercato, "-"), "fascia": fascia,
            "livello": livello, "descrizione_livello": DESCRIZIONE_LIVELLI[livello],
            "n_candidati": len(gruppo),
            "n_piazzati": len(piazzati),
            "n_abbinati": len(abbinati),
            "quota_abbinati": (round(len(abbinati) / len(piazzati), 4) if piazzati else None),
            "n_con_esito": n_esito,
            "partite": len(per_partita),
            "uscite": uscite,
            "attesa_mediana_s": _mediana([c.attesa_s for c in abbinati]),
            "ticks_guadagnati_mediana": _mediana([c.ticks_guadagnati for c in gruppo]),
            "guadagno_p_impl_mediano": _mediana(
                [c.p_impl_passivo - c.p_impl_tocco for c in gruppo]),
            "spread_tick_mediano": _mediana([c.spread_tick for c in gruppo]),
            "coda_davanti_mediana": _mediana([c.coda_davanti for c in piazzati]),
            "p_impl_passivo_media": (round(p_pass_media, 6) if p_pass_media else None),
            "p_impl_tocco_media": (round(p_tocco_media, 6) if p_tocco_media else None),
            "p_reale": (round(p_reale, 6) if p_reale is not None else None),
            "p_reale_boot_lo": round(lo_b, 6),
            "p_reale_boot_hi": round(hi_b, 6),
            "k_passivo": _k(p_pass_media, p_reale),
            "k_passivo_prudente": _k(p_pass_media, hi_b),
            "k_tocco_stesse_celle": _k(p_tocco_media, p_reale),
            "k_tocco_prudente_stesse_celle": _k(p_tocco_media, hi_b),
            "attraversati": sum(1 for c in abbinati if c.attraversato),
            "pre_gol": sum(1 for c in abbinati if c.pre_gol),
            "quota_attraversati": (round(sum(1 for c in abbinati if c.attraversato)
                                         / len(abbinati), 4) if abbinati else None),
            "quota_pre_gol": (round(sum(1 for c in abbinati if c.pre_gol)
                                    / len(abbinati), 4) if abbinati else None),
            # sotto N_MIN_ABBINATI il k della riga NON e' una misura: e' rumore.
            # Si riporta lo stesso, marcato, perche' nascondere una riga e'
            # peggio che dichiararla non misurabile.
            "misurabile": bool(n_esito >= N_MIN_ABBINATI),
        }
        riga["ev_passivo"] = ev_per_euro(riga["k_passivo"])
        riga["ev_tocco_stesse_celle"] = ev_per_euro(riga["k_tocco_stesse_celle"])
        righe.append(riga)
    return {"righe": righe}


def ev_per_euro(k: Optional[float]) -> Optional[float]:
    """EV per 1 EUR di stake: ``(1-c)*(1 - 1/k)`` (PROGETTO §3.3)."""
    if not k or float(k) <= 0:
        return None
    return round((1.0 - COMMISSIONE) * (1.0 - 1.0 / float(k)), 4)


def tabella_al_tocco(candidati: Sequence[Candidato], *,
                     giri_boot: int = 2000) -> Dict[str, Any]:
    """k AL TOCCO su TUTTI i candidati (non solo gli abbinati): e' la riga di
    riferimento, quella che dice cosa succede oggi. Un candidato conta una
    volta sola per (mercato, fascia): i tre livelli sono lo stesso runner."""
    from . import misura_k as MK

    visti = set()
    unici: List[Candidato] = []
    for c in candidati:
        chiave = (c.event_id, c.market_id, c.selection_id, c.minuto_ingresso)
        if chiave in visti:
            continue
        visti.add(chiave)
        unici.append(c)
    etichette = [s[2] for s in MK.SECCHI]
    righe: List[Dict[str, Any]] = []
    for mercato, fascia in sorted({(c.mercato, c.fascia) for c in unici},
                                  key=lambda t: (t[0], etichette.index(t[1])
                                                 if t[1] in etichette else 99)):
        gruppo = [c for c in unici if c.mercato == mercato and c.fascia == fascia
                  and c.esito_cella is not None]
        if not gruppo:
            continue
        per_partita: Dict[str, List[int]] = {}
        uscite = 0
        somma = 0.0
        for c in gruppo:
            cella = per_partita.setdefault(c.event_id, [0, 0])
            cella[0] += 1 if c.esito_cella else 0
            cella[1] += 1
            uscite += 1 if c.esito_cella else 0
            somma += float(c.p_impl_tocco)
        n = len(gruppo)
        p_reale = uscite / n
        p_media = somma / n
        lo_b, hi_b = MK.bootstrap_grappolo(
            {k: (v[0], v[1]) for k, v in per_partita.items()}, giri=giri_boot)
        k_c = round(p_media / p_reale, 3) if p_reale > 0 else None
        k_p = round(p_media / hi_b, 3) if hi_b > 0 else None
        righe.append({
            "mercato": mercato, "gamba": MERCATI[mercato], "fascia": fascia,
            "n_celle": n, "partite": len(per_partita), "uscite": uscite,
            "p_impl_media": round(p_media, 6), "p_reale": round(p_reale, 6),
            "p_reale_boot_lo": round(lo_b, 6), "p_reale_boot_hi": round(hi_b, 6),
            "k_tocco": k_c, "k_tocco_prudente": k_p,
            "ev_tocco": ev_per_euro(k_c),
            "misurabile": bool(n >= N_MIN_ABBINATI),
        })
    return {"righe": righe}


# =========================================================================
# M1-BIS — LA POLITICA V4: QUOTA VIVA, PANIERE, LIABILITY FISSA
# =========================================================================
# M1 ha misurato un ordine appoggiato e DIMENTICATO, e ha concluso (§11 del
# referto) che l'unica speranza sta nella VITA dell'ordine: riprezzo, rientro
# dopo la sospensione, finestre piu' lunghe. Qui quella vita si simula.
#
# LA POLITICA, esattamente come l'ha scritta il coordinatore
# (`VISIONE_OMEGA_V4_COORDINATORE_2026-09-17.md` §2, §4, §9):
#
#  1. finestre larghe: gamba HT dal 1' al 44', gamba FT dal 46' all'89';
#  2. a ogni giro di politica (cadenza dichiarata, default 10 s di TEMPO DI
#     MERCATO) e per ogni cella ammissibile (>= 2 gol dal punteggio, mai la
#     corrente ne' le adiacenti, mai una gia' impossibile) il modello V3 di
#     PRODUZIONE (`omega_v3.probabilita_selezioni`) da' `p_centro`; da li'
#         p_sup  = p_centro * FATTORE_PSUP        (dichiarato: non esiste una SE)
#         L*     = (1 - c) / (p_sup * k_soglia) + c
#     che e' il PREZZO DI RISERVA: il lay piu' alto che regge il margine k;
#  3. se il best lay e' <= L* si PRENDE al tocco (FOK, col bet delay);
#     altrimenti si APPOGGIA a `min(L*, best_lay - 1 tick)`, arrotondato al
#     tick VERSO IL BASSO (mai sopra la riserva);
#  4. ISTERESI: la quota si sposta solo se il prezzo obiettivo cambia di
#     >= 1 tick o la cella esce dalle migliori; annullo con latenza dichiarata
#     (300 ms) e nuovo ordine al giro dopo — MAI due ordini vivi sulla stessa
#     cella;
#  5. SOSPENSIONE: l'ordine muore (come oggi, e come su Betfair con LAPSE);
#     alla riapertura si RIENTRA dopo N secondi (default 20) ricalcolando
#     tutto sul punteggio nuovo;
#  6. FINE FINESTRA: annullo;
#  7. DIMENSIONE a LIABILITY FISSA: `s = liability_gamba / (L - 1)`. La
#     variante `A_stake1` rifa' la stessa politica con stake 1,00 EUR, per il
#     confronto con M1 e con V3;
#  8. VARIANTI: `A` = una cella (la migliore per EV/liability);
#     `B3`/`B5` = PANIERE delle 3 / 5 migliori quotate INSIEME, con cap di
#     CASO PEGGIORE `max_j[s_j(L_j-1) - somma_{i!=j} s_i(1-c)]` <= cap. Tutti i
#     fill contano; il paniere resta quotato finche' il caso peggiore sta sotto
#     il cap.
#
# Ogni variante e' un MONDO A SE' (stesso isolamento per ordine di M1): il
# matching di ciascun ordine usa la sua copia del delta di volume scambiato.
#
# USCITE: si tiene fino al regolamento (default della visione, §5 e §9.5). A
# parte, e SENZA entrare nel P&L principale, si registra che cosa varrebbe una
# chiusura al tocco al 44' / 89' (il confronto col 12/09).

LIABILITY_GAMBA_EUR = 30.0
K_SOGLIA_V4 = 2.0
# Il modello V3 da' una stima puntuale: non esiste una SE per cella (servirebbero
# piu' stime indipendenti, e con una sola fonte di lambda non ci sono). Si usa
# quindi il limite superiore DICHIARATO `p_centro * 1,25`, come da brief.
FATTORE_PSUP = 1.25
CADENZA_POLITICA_S = 10.0
LATENZA_ANNULLO_S = 0.300
RIENTRO_DOPO_SOSPENSIONE_S = 20.0
# minimo di giurisdizione .it per un LAY (place-and-trim in produzione): qui NON
# si applica, si CONTA quante quote ci finirebbero sotto
MINIMO_IT_LAY = 0.50

# LA QUOTA E' VIVA: il prezzo di riserva si ricalcola a ogni giro e l'ordine lo
# segue. `False` rimette l'ordine «appoggiato e dimenticato» di M1 — cioe' la
# quota non si sposta piu' una volta piazzata. Serve SOLO alla FALSIFICAZIONE
# (stesso patto di `banco_comune.ATTESA_ESATTA`): con il riprezzo spento il fill
# all'incrocio non avviene, e il test che lo pretende diventa rosso.
RIPREZZO_ATTIVO = True

FINESTRE_V4 = {"HALF_TIME_SCORE": (1, 44), "CORRECT_SCORE": (46, 89)}
MINUTO_CHIUSURA_V4 = {"HALF_TIME_SCORE": 44, "CORRECT_SCORE": 89}
PERIODO_DI = {"HALF_TIME_SCORE": "ht", "CORRECT_SCORE": "ft"}
# (nome variante, celle quotate insieme, stake fisso o None = liability fissa)
# (nome, celle quotate insieme, stake fisso o None = liability fissa, banda)
# Le due varianti `_coda` NON sono nel brief: sono una SENSIBILITA' aggiunta da
# questa misura e dichiarata come tale. Servono a rispondere alla domanda che
# M1 lasciava aperta — «con una quota VIVA, la CODA funziona?» — perche'
# l'ordinamento per EV/liability della visione §4, con k fisso a 2, e'
# monotono decrescente in L: senza banda sceglie SEMPRE la cella ammissibile
# con la quota piu' bassa, cioe' esce dalla coda. La banda e' quella di
# produzione (`omega_config` price_min/price_max = 20..120).
VARIANTI_V4: Tuple[Tuple[str, int, Optional[float], Optional[Tuple[float, float]]], ...] = (
    ("A", 1, None, None),
    ("B3", 3, None, None),
    ("B5", 5, None, None),
    ("A_stake1", 1, 1.00, None),
    ("A_coda", 1, None, (20.0, 120.0)),
    ("B5_coda", 5, None, (20.0, 120.0)),
)


@dataclass
class QuotaV4:
    """Una quotazione emessa dalla politica. I nomi dei campi che servono a
    ``Appoggiato`` sono gli STESSI di ``Candidato`` (``selection_id``,
    ``market_id``, ``prezzo_passivo``, ``abbinato``, ...): la classe che abbina
    e' la stessa, e non deve sapere quale delle due misure la sta usando."""

    # --- campi che ``Appoggiato`` legge e scrive (contratto con M1) ---------
    event_id: str
    market_id: str
    selection_id: int
    prezzo_passivo: float
    piazzato: bool = False
    motivo_non_piazzato: str = ""
    coda_davanti: float = 0.0
    abbinato: bool = False
    size_abbinata: float = 0.0
    prezzo_ottenuto: Optional[float] = None
    morte: str = ""
    attraversato: bool = False
    pre_gol: bool = False
    # --- campi della politica V4 -------------------------------------------
    variante: str = ""
    mercato: str = ""
    gamba: str = ""
    nome: str = ""
    minuto_quota: float = 0.0
    minuto_fill: Optional[float] = None
    punteggio: Tuple[int, int] = (0, 0)
    p_centro: float = 0.0
    p_sup: float = 0.0
    l_stella: float = 0.0
    prezzo_tocco: Optional[float] = None
    prezzo_back: Optional[float] = None
    modo: str = "passivo"          # 'tocco' (FOK) | 'passivo'
    size: float = 0.0
    liability: float = 0.0
    ev_liability: float = 0.0
    k_al_prezzo: float = 0.0
    fascia_psup: str = ""
    fascia_minuto: str = ""
    sotto_minimo_it: bool = False
    esito_cella: Optional[bool] = None
    attesa_s: Optional[float] = None
    prezzo_back_chiusura: Optional[float] = None
    pl_regolamento: Optional[float] = None
    pl_chiusura_finestra: Optional[float] = None

    def a_dizionario(self) -> Dict[str, Any]:
        d = dict(self.__dict__)
        d["punteggio"] = list(self.punteggio)
        return d


def caso_peggiore(posizioni: Sequence[Tuple[float, float]], commissione: float) -> float:
    """`max_j [ s_j (L_j - 1) - somma_{i != j} s_i (1 - c) ]` — la perdita
    massima di un insieme di lay su celle MUTUAMENTE ESCLUSIVE dello stesso
    mercato (visione §4, §9.4). Non e' la somma delle liability: se esce una
    scoreline, tutte le altre si vincono."""
    righe = [(float(s), float(L)) for s, L in posizioni if s > 0 and L > 1.0]
    if not righe:
        return 0.0
    incassi = sum(s * (1.0 - commissione) for s, _ in righe)
    return max(s * (L - 1.0) - (incassi - s * (1.0 - commissione)) for s, L in righe)


def fascia_minuto_10(minuto: float) -> str:
    """Fascia di 10 minuti ('0-9', '10-19', ...) per la superficie."""
    lo = int(max(0.0, float(minuto)) // 10) * 10
    return "%d-%d" % (lo, lo + 9)


def _tick_giu(prezzo: float) -> Optional[float]:
    """Ultimo tick VALIDO <= prezzo. Per un prezzo di riserva si arrotonda
    sempre VERSO IL BASSO: un tick sopra L* e' un ordine senza margine."""
    from flumine.utils import get_nearest_price

    if prezzo is None or not math.isfinite(float(prezzo)) or float(prezzo) <= 1.01:
        return None
    vicino = get_nearest_price(float(prezzo))
    if vicino <= float(prezzo) + 1e-9:
        return float(vicino)
    giu = _tick(vicino, -1)
    return None if giu is None else float(giu)


class MondoV4:
    """Una variante della politica: le sue quote vive, le sue posizioni."""

    def __init__(self, nome: str, celle: int, stake_fisso: Optional[float],
                 banda: Optional[Tuple[float, float]] = None,
                 *, liability_gamba: float, commissione: float,
                 prezzo_da: Optional[str] = None,
                 ammissibilita: Optional[str] = None) -> None:
        self.nome = nome
        self.celle = int(celle)
        self.stake_fisso = stake_fisso
        self.banda = banda
        # M1-ter: da quale dei tre prezzi della misura viene la quotazione
        # ("riserva" | "back+1" | "back+3"); None = il prezzo unico di M1-bis
        self.prezzo_da = prezzo_da
        # M1-ter: quale regola di ammissibilita' ("m6" | "pequa"); None = M1-bis
        self.ammissibilita = ammissibilita
        self.liability_gamba = float(liability_gamba)
        self.commissione = float(commissione)
        # market_id -> selection_id -> ordine appoggiato vivo/in attesa
        self.vive: Dict[str, Dict[int, Any]] = {}
        # market_id -> quote ABBINATE (le posizioni)
        self.posizioni: Dict[str, List[QuotaV4]] = {}
        self.quote: List[QuotaV4] = []
        # market_id -> la gamba e' stata aperta (almeno una quota emessa)?
        self.gamba_quotata: Dict[str, bool] = {}
        self.chiusura_registrata: Dict[str, bool] = {}

    def size_per(self, prezzo: float) -> float:
        """`s = liability / (L - 1)`, arrotondata PER DIFETTO al centesimo: con
        l'arrotondamento normale la liability puo' superare il cap di qualche
        centesimo e il paniere si autoescluderebbe (misurato: 30,03 > 30)."""
        if self.stake_fisso is not None:
            return float(self.stake_fisso)
        grezza = self.liability_gamba / max(1e-9, float(prezzo) - 1.0)
        return max(0.01, math.floor(grezza * 100.0) / 100.0)

    def esposte(self, market_id: str) -> List[Tuple[float, float]]:
        """(size, prezzo) di cio' che e' gia' abbinato su questo mercato."""
        return [(q.size, float(q.prezzo_ottenuto or q.prezzo_passivo))
                for q in self.posizioni.get(market_id, ())]

    def gia_in_posizione(self, market_id: str, selection_id: int) -> bool:
        return any(int(q.selection_id) == int(selection_id)
                   for q in self.posizioni.get(market_id, ()))


class MisuraV4:
    """La politica V4 fatta vivere su una registrazione vera.

    Stessa catena di M1 (`banco_comune.replay_evento` -> scanner vero -> riga di
    scan), stesso matching (`flumine SimulatedOrder`), stesso isolamento per
    ordine. Cambia la POLITICA: qui l'ordine ha una vita.
    """

    def __init__(self, event_id: str, *, catalogo: Any, esiti: Dict[str, Optional[int]],
                 par: Dict[str, Any]) -> None:
        self.event_id = str(event_id)
        self.catalogo = catalogo
        self.esiti = esiti
        self.par = par
        self.mercati: Dict[str, str] = {
            str(mid): str(mt).upper()
            for mid, mt in catalogo.tipi.items() if str(mt).upper() in FINESTRE_V4}
        self.ultimo_book: Dict[str, Any] = {}
        self._stato_mercato: Dict[str, str] = {}
        self.riprendi_da_ms: Dict[str, int] = {}
        self.cliente: Any = None
        self.strategia: Any = None
        self.punteggio: Optional[Tuple[int, int]] = None
        self.lambdas: Optional[Tuple[float, float]] = None
        self.fonte_lambdas: str = "assente"
        self._ultimo_giro_ms: Dict[str, int] = {}
        self.mondi: List[MondoV4] = [
            MondoV4(nome, celle, stake, banda,
                    liability_gamba=float(par["liability_gamba"]),
                    commissione=float(par["commissione"]))
            for nome, celle, stake, banda in VARIANTI_V4]
        self.note: List[str] = []
        self.giri_politica = 0
        self.sospensioni = 0
        self.rientri = 0

    # ------------------------------------------------------------- aggancio
    def aggancia(self, strategia: Any) -> None:
        self.strategia = strategia
        originale = strategia.process_market_book

        def avvolto(market: Any, market_book: Any) -> None:
            try:
                self._su_book(market, market_book)
            finally:
                originale(market, market_book)

        strategia.process_market_book = avvolto

    # ------------------------------------------------------------ ogni book
    def _su_book(self, market: Any, market_book: Any) -> None:
        mid = str(getattr(market_book, "market_id", "") or "")
        if mid not in self.mercati:
            return
        if self.cliente is None:
            quadro = getattr(market, "flumine", None)
            clienti = getattr(quadro, "clients", None)
            if clienti is not None:
                try:
                    self.cliente = clienti.get_default()
                except Exception:  # noqa: BLE001 - il client e' diagnostica
                    self.cliente = None
            if self.cliente is None:
                from ...stream.backtest import banco_comune as BC

                self.cliente = BC.cliente_simulato()
        self.ultimo_book[mid] = market_book
        pt = int(getattr(market_book, "publish_time_epoch", 0) or 0)
        stato = str(getattr(market_book, "status", "") or "")
        md = getattr(market_book, "market_definition", None)
        in_gioco = bool(getattr(md, "in_play", False)) if md is not None else False
        prima = self._stato_mercato.get(mid)
        self._stato_mercato[mid] = stato
        sospeso_ora = (stato == "SUSPENDED" and prima != "SUSPENDED" and in_gioco)
        riaperto_ora = (stato == "OPEN" and prima == "SUSPENDED" and in_gioco)
        if sospeso_ora:
            self.sospensioni += 1
        if riaperto_ora:
            # RIENTRO: nessuna quota per N secondi dopo la riapertura (visione §2b)
            self.riprendi_da_ms[mid] = pt + int(
                float(self.par["rientro_dopo_sospensione_s"]) * 1000)
            self.rientri += 1

        analitiche = (getattr(market, "context", {}) or {}).get("simulated") or {}
        for mondo in self.mondi:
            vive = mondo.vive.get(mid)
            if not vive:
                continue
            for sid in list(vive.keys()):
                ap = vive[sid]
                q: QuotaV4 = ap.cand
                # 1) sospensione: l'ordine muore PRIMA del matching
                if sospeso_ora and (ap.vivo or ap.in_attesa):
                    ap.uccidi("sospensione")
                    vive.pop(sid, None)
                    continue
                # 2) l'ordine deciso arriva a mercato dopo place_latency+betDelay
                if ap.in_attesa and not ap.chiuso:
                    if pt >= ap.attivo_da_ms:
                        if stato != "OPEN":
                            ap.uccidi("mercato_chiuso_all_arrivo")
                            vive.pop(sid, None)
                        else:
                            ap.piazza(self.cliente, market_book, self.strategia)
                            if ap.chiuso and not q.abbinato:
                                vive.pop(sid, None)
                            elif q.abbinato:
                                self._registra_posizione(mondo, mid, ap)
                                vive.pop(sid, None)
                    continue        # mai matching sul book del proprio arrivo
                if not ap.vivo:
                    vive.pop(sid, None)
                    continue
                # 3) annullo scaduto: Betfair ha tolto l'ordine
                if ap.annulla_a_ms is not None and pt >= ap.annulla_a_ms:
                    ap.uccidi("annullato")
                    vive.pop(sid, None)
                    continue
                # 4) matching, con la copia isolata del delta scambiato
                ra = analitiche.get((int(sid), 0.0))
                if ra is None:
                    continue
                if not ra.traded and stato == "OPEN":
                    # NESSUN volume nuovo su un mercato APERTO: la chiamata a
                    # `SimulatedOrder.__call__` sarebbe un no-op dimostrabile.
                    # Con `simulation_available_prices=False` quella funzione
                    # fa solo tre cose: il ramo BSP (qui non esiste), il
                    # `_process_traded` sul delta (vuoto) e il lapse a
                    # SUSPENDED (che qui e' escluso dallo stato OPEN, e che
                    # comunque lo fa gia' `uccidi("sospensione")` PRIMA del
                    # matching). Saltarla vale ~40 % del tempo del replay e non
                    # cambia un solo fill.
                    continue
                ap.applica(market_book, ra.runner, dict(ra.traded))
                if q.abbinato:
                    self._registra_posizione(mondo, mid, ap)
                    vive.pop(sid, None)
                elif not ap.vivo:
                    vive.pop(sid, None)
            # 5) selezione avversa sulle posizioni gia' abbinate
            for q in mondo.posizioni.get(mid, ()):
                ap = getattr(q, "_appoggiato", None)
                if ap is None:
                    continue
                if sospeso_ora and ap.fill_ms is not None \
                        and pt - ap.fill_ms <= FINESTRA_PRE_GOL_S * 1000:
                    q.pre_gol = True
                ap.osserva(market_book)

    def _registra_posizione(self, mondo: MondoV4, market_id: str, ap: Any) -> None:
        q: QuotaV4 = ap.cand
        q.attesa_s = round((int(ap.fill_ms) - int(ap.pt_decisione_ms)) / 1000.0, 1)
        q.minuto_fill = self._minuto_stimato(q.minuto_quota, q.attesa_s)
        q.size = float(ap.size)
        q.liability = round(q.size * (float(q.prezzo_ottenuto or q.prezzo_passivo) - 1.0), 2)
        setattr(q, "_appoggiato", ap)
        mondo.posizioni.setdefault(market_id, []).append(q)

    @staticmethod
    def _minuto_stimato(minuto_quota: float, attesa_s: Optional[float]) -> float:
        return round(float(minuto_quota) + (float(attesa_s or 0.0) / 60.0), 2)

    # ------------------------------------------------------------ ogni giro
    def giro(self, *, db: Any, market: Any, now: Any, row: Optional[dict],
             banco: Any, strategia: Any) -> None:
        if not row:
            return
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else row
        if self.lambdas is None:
            self._risolvi_lambdas(payload)
        minuto = payload.get("minute")
        sh, sa = payload.get("score_home"), payload.get("score_away")
        if minuto is None or sh is None or sa is None:
            return
        minuto = float(minuto)
        punteggio = (int(sh), int(sa))
        gol = self.punteggio is not None and punteggio != self.punteggio
        self.punteggio = punteggio
        if gol:
            # il gol e' STALE per definizione: la quota muore subito (e le
            # posizioni gia' abbinate nei 2' precedenti si marcano pre-gol)
            for mondo in self.mondi:
                for mid, vive in list(mondo.vive.items()):
                    for sid in list(vive.keys()):
                        vive[sid].uccidi("gol")
                        vive.pop(sid, None)
                for mid, righe in mondo.posizioni.items():
                    ultimo = self.ultimo_book.get(mid)
                    pt = int(getattr(ultimo, "publish_time_epoch", 0) or 0)
                    for q in righe:
                        ap = getattr(q, "_appoggiato", None)
                        if ap is not None and ap.fill_ms is not None and pt \
                                and pt - ap.fill_ms <= FINESTRA_PRE_GOL_S * 1000:
                            q.pre_gol = True

        for mid, mtype in self.mercati.items():
            self._giro_mercato(mid, mtype, minuto, punteggio)

    def _risolvi_lambdas(self, payload: Optional[dict]) -> None:
        """I lambda pre-partita dalla CATENA VERA, per quel che ne e' raggiungibile
        senza database: il gradino 3 di `omega_service._prematch_lambdas`, cioe'
        le quote 1X2 PRE-KO congelate dallo scanner
        (`omega_model.lambdas_from_pre_ko`). I gradini 1-2 e 4 vogliono il DB e
        qui non esistono; il 5 (O/U live) NON e' pre-partita e non si usa.
        La fonte finisce nel referto."""
        if not isinstance(payload, dict):
            return
        from .. import omega_model as M

        try:
            lam = M.lambdas_from_pre_ko(payload.get("pre_ko"))
        except Exception as ex:  # noqa: BLE001 - un errore e' un referto
            self.note.append("lambdas_from_pre_ko KO: %s" % str(ex)[:80])
            return
        if lam:
            self.lambdas = (float(lam[0]), float(lam[1]))
            self.fonte_lambdas = "pre_ko_odds"

    # -------------------------------------------------------- la politica
    def _finestra(self, mercato: str) -> Tuple[int, int]:
        """La finestra della gamba. M1-ter la sovrascrive (1'-85' sul solo CS)."""
        return FINESTRE_V4[mercato]

    def _minuto_chiusura(self, mercato: str) -> int:
        """Il minuto in cui si registra il prezzo di chiusura (fuori dal P&L)."""
        return MINUTO_CHIUSURA_V4[mercato]

    def _giro_mercato(self, market_id: str, mercato: str, minuto: float,
                      punteggio: Tuple[int, int]) -> None:
        lo, hi = self._finestra(mercato)
        book = self.ultimo_book.get(market_id)
        if book is None:
            return
        pt = int(getattr(book, "publish_time_epoch", 0) or 0)

        # prezzo di chiusura al 44'/89' (per il confronto col 12/09, FUORI dal
        # P&L principale). Va registrato PRIMA di uscire per fine finestra, se
        # no una riga di scan che salta dal 88' al 90' lo perderebbe.
        if minuto >= self._minuto_chiusura(mercato):
            self._registra_chiusura_finestra(market_id, book)
        # fine finestra: si annulla tutto
        if minuto > hi:
            for mondo in self.mondi:
                for sid in list((mondo.vive.get(market_id) or {}).keys()):
                    mondo.vive[market_id][sid].uccidi("fine_finestra")
                    mondo.vive[market_id].pop(sid, None)
            return

        if minuto < lo:
            return
        if str(getattr(book, "status", "") or "") != "OPEN":
            return
        if pt < self.riprendi_da_ms.get(market_id, 0):
            return                      # riassestamento dopo la riapertura
        if self.lambdas is None:
            return                      # nessun modello possibile: mai a occhi chiusi
        # cadenza della politica, sul TEMPO DI MERCATO
        if pt - self._ultimo_giro_ms.get(market_id, 0) < int(float(self.par["cadenza_s"]) * 1000):
            return
        self._ultimo_giro_ms[market_id] = pt
        self.giri_politica += 1

        candidati = self._candidati(market_id, mercato, minuto, punteggio, book)
        for mondo in self.mondi:
            self._applica_mondo(mondo, market_id, mercato, minuto, punteggio, book,
                                candidati, pt)

    def _candidati(self, market_id: str, mercato: str, minuto: float,
                   punteggio: Tuple[int, int], book: Any) -> List[Dict[str, Any]]:
        """Le celle ammissibili, gia' prezzate, ordinate per EV/liability."""
        from flumine.utils import get_price, get_size

        from . import misura_k as MK
        from .. import omega_v3 as V3

        periodo = PERIODO_DI[mercato]
        nomi_mercato = self.catalogo.nomi.get(str(market_id), {})
        attivi = {int(getattr(r, "selection_id", 0) or 0): r
                  for r in (getattr(book, "runners", ()) or ())
                  if str(getattr(r, "status", "") or "") == "ACTIVE"}
        nomi = [str(nomi_mercato.get(sid) or "") for sid in attivi]
        nomi = [n for n in nomi if n]
        if not nomi:
            return []
        probs = V3.probabilita_selezioni(
            periodo=periodo, minuto=minuto, punteggio=punteggio, nomi=nomi,
            p=self.par["parametri_modello"], lambdas=self.lambdas)
        c = float(self.par["commissione"])
        k_soglia = float(self.par["k_soglia"])
        fattore = float(self.par["fattore_psup"])
        distanza = int(self.par["distanza_minima_gol"])
        sh, sa = punteggio
        fuori: List[Dict[str, Any]] = []
        for sid, runner in attivi.items():
            nome = str(nomi_mercato.get(sid) or "")
            coppia = V3.parse_scoreline(nome)
            if coppia is None:
                continue                     # mai gli aggregati
            h, a = coppia
            if h < sh or a < sa:
                continue                     # cella ormai impossibile
            if (h - sh) + (a - sa) < distanza:
                continue                     # corrente o adiacente
            p_centro = float(probs.get(nome) or 0.0)
            if p_centro <= 0.0:
                continue
            p_sup = min(0.999, p_centro * fattore)
            l_stella = (1.0 - c) / max(1e-12, p_sup * k_soglia) + c
            prezzo_riserva = _tick_giu(min(l_stella, 1000.0))
            if prezzo_riserva is None or prezzo_riserva <= 1.01:
                continue
            atl = get_price(runner.ex.available_to_lay, 0)
            atb = get_price(runner.ex.available_to_back, 0)
            atl_size = get_size(runner.ex.available_to_lay, 0) or 0.0
            if atl is not None and float(atl) <= prezzo_riserva + 1e-9:
                modo = "tocco"
                prezzo = prezzo_riserva      # FOK: si accetta fino alla riserva
                # ...ma il prezzo a cui si SCAMBIA davvero e' quello del book:
                # e' quello che decide margine, EV/liability e dimensione
                prezzo_effettivo = float(atl)
            else:
                modo = "passivo"
                limite = prezzo_riserva
                if atl is not None:
                    sotto = _tick(float(atl), -1)
                    if sotto is not None:
                        limite = min(limite, float(sotto))
                prezzo = _tick_giu(limite)
                if prezzo is None or prezzo <= 1.01:
                    continue
                prezzo_effettivo = float(prezzo)
            p_impl = MK.p_implicita(float(prezzo_effettivo), c)
            if p_impl is None:
                continue
            k_al_prezzo = p_impl / max(1e-12, p_sup)
            if k_al_prezzo < k_soglia - 1e-9:
                continue                     # nessun margine: non si quota
            ev_liab = (1.0 - c) * (1.0 - 1.0 / k_al_prezzo)                 / max(1e-9, float(prezzo_effettivo) - 1.0)
            fuori.append({
                "selection_id": int(sid), "nome": nome, "prezzo": float(prezzo),
                "prezzo_effettivo": float(prezzo_effettivo),
                "modo": modo, "p_centro": p_centro, "p_sup": p_sup,
                "l_stella": float(l_stella), "k_al_prezzo": float(k_al_prezzo),
                "ev_liability": float(ev_liab),
                "prezzo_tocco": (float(atl) if atl else None),
                "prezzo_back": (float(atb) if atb else None),
                "size_tocco": float(atl_size),
                "fascia_psup": MK.secchio_di(p_sup),
            })
        fuori.sort(key=lambda d: (-d["ev_liability"], d["prezzo"]))
        return fuori

    def _per_mondo(self, mondo: MondoV4, cand: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Adatta un candidato alla variante. In M1-bis il candidato e' gia'
        completo (un prezzo solo, nessuna regola di ammissibilita' per mondo):
        lo si consegna com'e'. M1-ter la sovrascrive."""
        return cand

    def _applica_mondo(self, mondo: MondoV4, market_id: str, mercato: str,
                       minuto: float, punteggio: Tuple[int, int], book: Any,
                       candidati: Sequence[Dict[str, Any]], pt: int) -> None:
        vive = mondo.vive.setdefault(market_id, {})
        posizioni = mondo.posizioni.get(market_id, [])
        # variante a UNA cella: una volta presa la gamba, non si quota piu'
        if mondo.celle <= 1 and posizioni:
            for sid in list(vive.keys()):
                vive[sid].uccidi("gamba_gia_presa")
                vive.pop(sid, None)
            return
        cap = float(self.par["liability_gamba"])
        c = float(self.par["commissione"])
        esposte = mondo.esposte(market_id)
        bersaglio: Dict[int, Dict[str, Any]] = {}
        for cand in candidati:
            if len(bersaglio) >= mondo.celle:
                break
            cand = self._per_mondo(mondo, cand)
            if cand is None:
                continue
            if mondo.banda is not None:
                lo_b, hi_b = mondo.banda
                # la banda guarda il prezzo a cui si SCAMBIA davvero: per un
                # ordine al tocco e' il prezzo del book, non il limite del FOK
                prezzo_banda = float(cand["prezzo_tocco"] or cand["prezzo"])                     if cand["modo"] == "tocco" else float(cand["prezzo"])
                if not (lo_b <= prezzo_banda <= hi_b):
                    continue          # fuori banda per questa variante
            sid = int(cand["selection_id"])
            if mondo.gia_in_posizione(market_id, sid):
                continue
            size = mondo.size_per(cand["prezzo"])
            if size <= 0:
                continue
            prova = list(esposte) + [(s["size"], s["prezzo"]) for s in bersaglio.values()] \
                + [(size, cand["prezzo"])]
            if caso_peggiore(prova, c) > cap + 1e-9:
                continue                    # il paniere ha finito il suo cap
            d = dict(cand)
            d["size"] = size
            bersaglio[sid] = d

        # 1) le quote vive su celle che NON sono piu' bersaglio: annullo
        for sid in list(vive.keys()):
            ap = vive[sid]
            if not RIPREZZO_ATTIVO:
                # FALSIFICAZIONE: l'ordine «appoggiato e dimenticato» di M1.
                # Non si annulla e non si sposta per nessun motivo di prezzo o
                # di bersaglio: muore solo di sospensione, gol o fine finestra.
                bersaglio.pop(sid, None)
                continue
            if sid not in bersaglio:
                if ap.in_attesa:
                    ap.uccidi("bersaglio_cambiato")
                    vive.pop(sid, None)
                else:
                    ap.annulla(pt, float(self.par["latenza_annullo_s"]))
                continue
            if ap.in_annullo():
                continue        # gia' in annullo: la si riquota quando il posto e' libero
            # 2) ISTERESI: si sposta solo se il prezzo obiettivo e' cambiato di
            #    almeno un tick
            nuovo = float(bersaglio[sid]["prezzo"])
            vecchio = float(ap.cand.prezzo_passivo)
            if abs(nuovo - vecchio) > 1e-9:
                salto = ticks_fra(min(nuovo, vecchio), max(nuovo, vecchio))
                if salto is not None and salto >= 1:
                    if ap.in_attesa:
                        ap.uccidi("riprezzo")
                        vive.pop(sid, None)
                    else:
                        ap.annulla(pt, float(self.par["latenza_annullo_s"]))
                    continue
            bersaglio.pop(sid, None)        # gia' quotata al prezzo giusto

        # 3) le celle bersaglio senza quota viva: nuovo ordine (mai due vivi)
        for sid, d in bersaglio.items():
            if sid in vive:
                continue                    # c'e' ancora l'ordine in annullo
            q = QuotaV4(
                event_id=self.event_id, market_id=str(market_id),
                selection_id=int(sid), prezzo_passivo=float(d["prezzo"]),
                variante=mondo.nome, mercato=mercato,
                gamba=("1T" if mercato == "HALF_TIME_SCORE" else "2T"),
                nome=str(d["nome"]), minuto_quota=float(minuto), punteggio=punteggio,
                p_centro=float(d["p_centro"]), p_sup=float(d["p_sup"]),
                l_stella=float(d["l_stella"]), prezzo_tocco=d["prezzo_tocco"],
                prezzo_back=d["prezzo_back"], modo=str(d["modo"]),
                size=float(d["size"]),
                liability=round(float(d["size"])
                                * (float(d["prezzo_effettivo"]) - 1.0), 2),
                ev_liability=float(d["ev_liability"]),
                k_al_prezzo=float(d["k_al_prezzo"]),
                fascia_psup=str(d["fascia_psup"]),
                fascia_minuto=fascia_minuto_10(minuto),
                sotto_minimo_it=bool(float(d["size"]) < MINIMO_IT_LAY))
            ritardo = int(MisuraEvento._ritardo_s(book) * 1000)
            ap = Appoggiato(q, attivo_da_ms=pt + ritardo, pt_decisione_ms=pt,
                            size=float(d["size"]), fok=(d["modo"] == "tocco"))
            vive[sid] = ap
            mondo.quote.append(q)
            mondo.gamba_quotata[market_id] = True

    # ------------------------------------------------- chiusura di finestra
    def _registra_chiusura_finestra(self, market_id: str, book: Any) -> None:
        from flumine.utils import get_price

        for mondo in self.mondi:
            if mondo.chiusura_registrata.get(market_id):
                continue
            righe = mondo.posizioni.get(market_id) or []
            if not righe:
                continue
            for q in righe:
                runner = runner_di(book, q.selection_id)
                if runner is None:
                    continue
                q.prezzo_back_chiusura = get_price(runner.ex.available_to_back, 0)
            mondo.chiusura_registrata[market_id] = True

    # --------------------------------------------------------- regolamento
    def chiudi(self) -> None:
        c = float(self.par["commissione"])
        for mondo in self.mondi:
            for mid, vive in mondo.vive.items():
                for sid in list(vive.keys()):
                    vive[sid].uccidi("registrazione_finita")
            # L'ESITO DELLA CELLA SI SA ANCHE SE NON CI SIAMO ABBINATI: serve al
            # denominatore della selezione avversa (la frequenza di uscita di
            # TUTTE le candidate). Prima veniva scritto solo sulle posizioni, e
            # il rapporto veniva 1,00 per costruzione.
            for q in mondo.quote:
                vincitore = self.esiti.get(str(q.market_id))
                q.esito_cella = (None if vincitore is None
                                 else bool(int(vincitore) == int(q.selection_id)))
            for mid, righe in mondo.posizioni.items():
                for q in righe:
                    L = float(q.prezzo_ottenuto or q.prezzo_passivo)
                    if q.esito_cella is None:
                        q.pl_regolamento = None
                    else:
                        q.pl_regolamento = round(
                            -q.size * (L - 1.0) if q.esito_cella else q.size * (1.0 - c), 4)
                    B = q.prezzo_back_chiusura
                    if B and float(B) > 1.0:
                        bloccato = q.size * (1.0 - L / float(B))
                        q.pl_chiusura_finestra = round(
                            bloccato * (1.0 - c) if bloccato > 0 else bloccato, 4)
                    if getattr(q, "_appoggiato", None) is not None:
                        delattr(q, "_appoggiato")
            for q in mondo.quote:
                if getattr(q, "_appoggiato", None) is not None:
                    delattr(q, "_appoggiato")


def misura_evento_v4(event_id: str, cartella: str, *,
                     par: Dict[str, Any]) -> Tuple[List[QuotaV4], Dict[str, Any]]:
    """Fa vivere una registrazione con la politica V4 e torna tutte le quote."""
    from ...stream.backtest import banco_comune as BC
    from .replay_registrazioni import leggi_catalogo

    raw = os.path.join(cartella, str(event_id), "%s.raw.jsonl" % event_id)
    diagnostica: Dict[str, Any] = {"event_id": str(event_id), "errori": [], "note": []}
    if not os.path.exists(raw):
        diagnostica["errori"].append("registrazione assente")
        return [], diagnostica
    catalogo = leggi_catalogo(raw)
    esiti = esiti_dal_catalogo(catalogo)
    misura = MisuraV4(event_id, catalogo=catalogo, esiti=esiti, par=par)
    t0 = time.time()
    esito = BC.replay_evento(event_id=str(event_id), cartella=cartella,
                             servizio=misura.giro, nomi_extra=catalogo.nomi,
                             su_strategia=misura.aggancia)
    misura.chiudi()
    diagnostica["durata_s"] = round(time.time() - t0, 1)
    diagnostica["errori"].extend(list(esito.errori))
    diagnostica["note"].extend(list(esito.note) + list(misura.note))
    diagnostica["giri"] = esito.giri
    diagnostica["giri_politica"] = misura.giri_politica
    diagnostica["sospensioni"] = misura.sospensioni
    diagnostica["rientri"] = misura.rientri
    diagnostica["fonte_lambdas"] = misura.fonte_lambdas
    diagnostica["lambdas"] = (list(misura.lambdas) if misura.lambdas else None)
    diagnostica["kickoff"] = (catalogo.avvio.isoformat() if catalogo.avvio else None)
    diagnostica["esiti"] = dict(esiti)
    quote: List[QuotaV4] = []
    for mondo in misura.mondi:
        quote.extend(mondo.quote)
    return quote, diagnostica


# ---------------------------------------------------------------------------
# AGGREGAZIONE M1-BIS
# ---------------------------------------------------------------------------
def _k_e_ic(righe: Sequence[QuotaV4], *, giri_boot: int,
            commissione: float) -> Dict[str, Any]:
    """k realizzato con IC a grappolo SULLE PARTITE (come `misura_k`)."""
    from . import misura_k as MK

    con_esito = [q for q in righe if q.esito_cella is not None]
    if not con_esito:
        return {"n": 0, "partite": 0, "uscite": 0, "p_impl_media": None,
                "p_reale": None, "k": None, "k_prudente": None,
                "p_reale_boot_lo": None, "p_reale_boot_hi": None, "ev_per_euro": None}
    per_partita: Dict[str, List[int]] = {}
    somma = 0.0
    uscite = 0
    for q in con_esito:
        cella = per_partita.setdefault(q.event_id, [0, 0])
        cella[0] += 1 if q.esito_cella else 0
        cella[1] += 1
        uscite += 1 if q.esito_cella else 0
        somma += float(MK.p_implicita(float(q.prezzo_ottenuto or q.prezzo_passivo),
                                      commissione) or 0.0)
    n = len(con_esito)
    p_media = somma / n
    p_reale = uscite / n
    lo_b, hi_b = MK.bootstrap_grappolo({k: (v[0], v[1]) for k, v in per_partita.items()},
                                       giri=giri_boot)
    k = (p_media / p_reale) if p_reale > 0 else None
    return {
        "n": n, "partite": len(per_partita), "uscite": uscite,
        "p_impl_media": round(p_media, 6), "p_reale": round(p_reale, 6),
        "p_reale_boot_lo": round(lo_b, 6), "p_reale_boot_hi": round(hi_b, 6),
        "k": (None if k is None else round(k, 3)),
        "k_prudente": (round(p_media / hi_b, 3) if hi_b > 0 else None),
        "ev_per_euro": ev_per_euro(None if k is None else round(k, 3)),
    }


def _drawdown(serie: Sequence[float]) -> float:
    """Drawdown massimo della curva cumulata (valore assoluto, >= 0)."""
    picco = 0.0
    cumulato = 0.0
    peggiore = 0.0
    for x in serie:
        cumulato += float(x)
        picco = max(picco, cumulato)
        peggiore = min(peggiore, cumulato - picco)
    return round(abs(peggiore), 2)


def aggrega_v4(quote: Sequence[QuotaV4], *, kickoff: Dict[str, Optional[str]],
               giri_boot: int, commissione: float) -> Dict[str, Any]:
    """Tabelle per variante x mercato, superficie, e conti di giornata."""
    righe: List[Dict[str, Any]] = []
    varianti = [v[0] for v in VARIANTI_V4]
    mercati = ["CORRECT_SCORE", "HALF_TIME_SCORE", "tutti"]
    for variante in varianti:
        for mercato in mercati:
            g = [q for q in quote if q.variante == variante
                 and (mercato == "tutti" or q.mercato == mercato)]
            if not g:
                continue
            gambe = {(q.event_id, q.market_id) for q in g}
            abbinate = [q for q in g if q.abbinato]
            gambe_con_fill = {(q.event_id, q.market_id) for q in abbinate}
            # P&L per gamba, in ordine di CALCIO D'INIZIO (la sequenza vera)
            per_gamba: Dict[Tuple[str, str], float] = {}
            gambe_senza_esito = set()
            for q in abbinate:
                chiave = (q.event_id, q.market_id)
                if q.pl_regolamento is None:
                    gambe_senza_esito.add(chiave)
                    continue
                per_gamba[chiave] = per_gamba.get(chiave, 0.0) + float(q.pl_regolamento)
            for chiave in gambe_senza_esito:
                per_gamba.pop(chiave, None)
            ordinate = sorted(per_gamba.items(),
                              key=lambda kv: (kickoff.get(kv[0][0]) or "", kv[0][1]))
            serie = [v for _k, v in ordinate]
            pl_totale = round(sum(serie), 2)
            chiusure = [q.pl_chiusura_finestra for q in abbinate
                        if q.pl_chiusura_finestra is not None]
            riga = {
                "variante": variante, "mercato": mercato,
                "n_quote_emesse": len(g),
                "n_quote_al_tocco": sum(1 for q in g if q.modo == "tocco"),
                "n_gambe_quotate": len(gambe),
                "n_gambe_con_fill": len(gambe_con_fill),
                "quota_gambe_con_fill": (round(len(gambe_con_fill) / len(gambe), 4)
                                         if gambe else None),
                "n_fill": len(abbinate),
                "quota_quote_abbinate": (round(len(abbinate) / len(g), 4) if g else None),
                "attesa_mediana_s": _mediana([q.attesa_s for q in abbinate]),
                "prezzo_medio_ottenuto": _media([q.prezzo_ottenuto for q in abbinate]),
                "prezzo_medio_quotato": _media([q.prezzo_passivo for q in g]),
                "l_stella_mediana": _mediana([q.l_stella for q in g]),
                "ev_liability_medio": _media([q.ev_liability for q in g]),
                "size_mediana": _mediana([q.size for q in abbinate]),
                "liability_mediana": _mediana([q.liability for q in abbinate]),
                "quote_sotto_minimo_it": sum(1 for q in g if q.sotto_minimo_it),
                "quote_per_gamba": (round(len(g) / len(gambe), 2) if gambe else None),
                "riprezzi_al_minuto_per_gamba": (
                    round(len(g) / len(gambe) / 44.0, 2) if gambe else None),
                "attraversati": sum(1 for q in abbinate if q.attraversato),
                "quota_attraversati": (round(sum(1 for q in abbinate if q.attraversato)
                                             / len(abbinate), 4) if abbinate else None),
                "pre_gol": sum(1 for q in abbinate if q.pre_gol),
                "quota_pre_gol": (round(sum(1 for q in abbinate if q.pre_gol)
                                        / len(abbinate), 4) if abbinate else None),
                "pl_totale_eur": pl_totale,
                "n_gambe_nel_pl": len(serie),
                "pl_per_gamba_eur": (round(pl_totale / len(serie), 4) if serie else None),
                "gambe_senza_esito": len(gambe_senza_esito),
                "drawdown_massimo_eur": _drawdown(serie),
                "pl_se_chiuso_a_finestra_eur": (round(sum(chiusure), 2) if chiusure else None),
                "n_chiusure_valutabili": len(chiusure),
            }
            riga["k_realizzato"] = _k_e_ic(abbinate, giri_boot=giri_boot,
                                          commissione=commissione)
            righe.append(riga)
    return {"righe": righe}


def superficie_v4(quote: Sequence[QuotaV4], *, giri_boot: int,
                  commissione: float) -> Dict[str, Any]:
    """fill% e k per FASCIA DI MINUTO (10') x FASCIA DI p_sup, per variante."""
    fuori: List[Dict[str, Any]] = []
    chiavi = sorted({(q.variante, q.fascia_minuto, q.fascia_psup) for q in quote},
                    key=lambda t: (t[0], int(t[1].split("-")[0]), t[2]))
    for variante, fm, fp in chiavi:
        g = [q for q in quote if q.variante == variante
             and q.fascia_minuto == fm and q.fascia_psup == fp]
        ab = [q for q in g if q.abbinato]
        k = _k_e_ic(ab, giri_boot=giri_boot, commissione=commissione)
        fuori.append({
            "variante": variante, "fascia_minuto": fm, "fascia_psup": fp,
            "n_quote": len(g), "n_fill": len(ab),
            "fill_pct": (round(100.0 * len(ab) / len(g), 1) if g else None),
            "prezzo_medio_quotato": _media([q.prezzo_passivo for q in g]),
            "attesa_mediana_s": _mediana([q.attesa_s for q in ab]),
            "k": k["k"], "k_prudente": k["k_prudente"], "n_con_esito": k["n"],
            "uscite": k["uscite"],
        })
    return {"righe": fuori}


def _media(valori: Sequence[Any]) -> Optional[float]:
    v = [float(x) for x in valori
         if x is not None and math.isfinite(float(x))]
    return round(sum(v) / len(v), 4) if v else None


def conto_di_giornata(quote: Sequence[QuotaV4], *, kickoff: Dict[str, Optional[str]],
                      registrazioni: int, partite_giorno_tipo: int) -> Dict[str, Any]:
    """Quante gambe/fill uscirebbero in un giorno tipo, riportando il tasso
    misurato PER PARTITA al numero di partite che si seguono in un giorno.

    `partite_giorno_tipo` e' un'ASSUNZIONE dichiarata: il tasso per partita e'
    il dato misurato, la moltiplicazione la fa chi legge."""
    giorni = sorted({(kickoff.get(e) or "")[:10] for e in {q.event_id for q in quote}}
                    - {""})
    fuori: Dict[str, Any] = {
        "registrazioni": registrazioni,
        "giorni_di_calendario_coperti": len(giorni),
        "giorni": giorni,
        "partite_giorno_tipo_assunte": partite_giorno_tipo,
        "per_variante": [],
    }
    for variante, _celle, _stake, _banda in VARIANTI_V4:
        g = [q for q in quote if q.variante == variante]
        if not g:
            continue
        gambe = {(q.event_id, q.market_id) for q in g}
        fill = [q for q in g if q.abbinato]
        gambe_fill = {(q.event_id, q.market_id) for q in fill}
        fuori["per_variante"].append({
            "variante": variante,
            "gambe_quotate_per_partita": round(len(gambe) / max(1, registrazioni), 3),
            "gambe_con_fill_per_partita": round(len(gambe_fill) / max(1, registrazioni), 3),
            "fill_per_partita": round(len(fill) / max(1, registrazioni), 3),
            "gambe_con_fill_giorno_tipo": round(
                len(gambe_fill) / max(1, registrazioni) * partite_giorno_tipo, 2),
            "fill_giorno_tipo": round(
                len(fill) / max(1, registrazioni) * partite_giorno_tipo, 2),
            "liability_impegnata_giorno_tipo_eur": round(
                sum(q.liability for q in fill) / max(1, registrazioni)
                * partite_giorno_tipo, 2),
        })
    return fuori


def parametri_v4(*, liability: float = LIABILITY_GAMBA_EUR,
                 k_soglia: float = K_SOGLIA_V4,
                 fattore_psup: float = FATTORE_PSUP,
                 cadenza_s: float = CADENZA_POLITICA_S) -> Dict[str, Any]:
    """I parametri della politica. Il MODELLO e' quello di produzione: i
    parametri vincenti del banco, caricati dalla funzione del replay ufficiale."""
    from .. import omega_config
    from .replay_registrazioni import _parametri_v3_dal_banco

    d = omega_config.DEFAULTS
    return {
        "liability_gamba": float(liability),
        "k_soglia": float(k_soglia),
        "fattore_psup": float(fattore_psup),
        "cadenza_s": float(cadenza_s),
        "latenza_annullo_s": LATENZA_ANNULLO_S,
        "rientro_dopo_sospensione_s": RIENTRO_DOPO_SOSPENSIONE_S,
        "commissione": float(d["commission_pct"]) / 100.0,
        "distanza_minima_gol": int(d["v3_distanza_minima_gol"]),
        "parametri_modello": _parametri_v3_dal_banco(),
        "finestre": {k: list(v) for k, v in FINESTRE_V4.items()},
    }


def main_v4(args: Any) -> int:
    cartella = args.cartella
    eventi = args.eventi if args.eventi else eventi_disponibili(cartella)
    par = parametri_v4(liability=args.liability, k_soglia=args.k_soglia,
                       fattore_psup=args.fattore_psup, cadenza_s=args.cadenza_s)
    pm = par["parametri_modello"]
    print("POLITICA V4 — registrazioni: %d" % len(eventi), flush=True)
    print("liability/gamba %.2f EUR, k soglia %.1f, p_sup = p x %.2f, cadenza %.0f s, "
          "annullo %.0f ms, rientro %.0f s"
          % (par["liability_gamba"], par["k_soglia"], par["fattore_psup"],
             par["cadenza_s"], par["latenza_annullo_s"] * 1000,
             par["rientro_dopo_sospensione_s"]), flush=True)
    print("finestre %s; modello %s (gol_totali %.3f, quota_casa %.3f)"
          % (par["finestre"], pm.modello, pm.gol_totali, pm.quota_casa), flush=True)

    tutte: List[QuotaV4] = []
    diagnostiche: List[Dict[str, Any]] = []
    kickoff: Dict[str, Optional[str]] = {}
    t0 = time.time()
    for i, eid in enumerate(eventi, 1):
        try:
            quote, diag = misura_evento_v4(eid, cartella, par=par)
        except Exception as ex:  # noqa: BLE001 - un errore e' un referto
            import traceback
            quote, diag = [], {"event_id": eid,
                               "errori": ["%s: %s" % (type(ex).__name__, ex)],
                               "traccia": traceback.format_exc()[-800:]}
        tutte.extend(quote)
        diagnostiche.append(diag)
        kickoff[str(eid)] = diag.get("kickoff")
        print("  [%d/%d] %s  quote=%d fill=%d  lambda=%s  %ss  %s"
              % (i, len(eventi), eid, len(quote),
                 sum(1 for q in quote if q.abbinato), diag.get("fonte_lambdas"),
                 diag.get("durata_s", "?"), ";".join(diag.get("errori", []))[:70]),
              flush=True)

    dati = {
        "generato_il": "2026-09-17",
        "politica": "v4 — quota viva con prezzo di riserva del modello",
        "fonte": "_live_raw (stream Betfair registrato) via banco_comune.replay_evento",
        "matching": "flumine.simulation.simulatedorder.SimulatedOrder (2.13.11), "
                    "delta scambiato da RunnerAnalytics, "
                    "simulation_available_prices=False, isolamento PER ORDINE",
        "modello": {
            "modulo": "omega_v3.probabilita_selezioni (produzione)",
            "parametri": {k: getattr(pm, k) for k in
                          ("modello", "gol_totali", "quota_casa", "profilo_c1",
                           "profilo_c2", "rho", "forma_gamma", "beta_squilibrio")},
            "p_sup": "p_centro x %.2f (nessuna SE disponibile: dichiarato)" % par["fattore_psup"],
            "lambdas": "omega_model.lambdas_from_pre_ko (gradino 3 della catena "
                       "di omega_service._prematch_lambdas; i gradini 1-2 e 4 "
                       "vogliono il database e nel replay non esistono)",
        },
        "parametri": {k: v for k, v in par.items() if k != "parametri_modello"},
        "varianti": [{"nome": n, "celle": c, "stake_fisso": s,
                      "banda": (list(b) if b else None)}
                     for n, c, s, b in VARIANTI_V4],
        "registrazioni": diagnostiche,
        "n_registrazioni": len(eventi),
        "n_quote": len(tutte),
        "risultati": aggrega_v4(tutte, kickoff=kickoff, giri_boot=args.boot,
                                commissione=par["commissione"]),
        "superficie": superficie_v4(tutte, giri_boot=args.boot,
                                    commissione=par["commissione"]),
        "giornata": conto_di_giornata(tutte, kickoff=kickoff, registrazioni=len(eventi),
                                      partite_giorno_tipo=args.partite_giorno),
        # le QUOTE ABBINATE stanno qui (sono dieci): le 12.486 quotazioni grezze
        # vanno nel sidecar compresso, come gli altri campioni grossi di `data/`
        "quote_abbinate": [q.a_dizionario() for q in tutte if q.abbinato],
        "quote_file": os.path.basename(_percorso_quote(args.out)),
        "durata_totale_s": round(time.time() - t0, 1),
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(dati, fh, ensure_ascii=False, indent=1, sort_keys=True, default=str)
    scrivi_quote(_percorso_quote(args.out), tutte)
    print("scritto %s (+ %s)" % (args.out, _percorso_quote(args.out)))
    stampa_v4(dati)
    return 0


def _percorso_quote(percorso_json: str) -> str:
    """Il sidecar compresso con TUTTE le quotazioni grezze."""
    base, _est = os.path.splitext(percorso_json)
    return base + "_quote.json.gz"


def scrivi_quote(percorso: str, quote: Sequence[QuotaV4]) -> None:
    """12.486 righe di quotazione non stanno in un JSON versionato da 14 MB:
    vanno compresse, come gli altri campioni grossi di `Betfair/omega/data/`."""
    import gzip

    with gzip.open(percorso, "wt", encoding="utf-8") as fh:
        json.dump([q.a_dizionario() for q in quote], fh, ensure_ascii=False,
                  sort_keys=True, default=str)


def leggi_quote(percorso: str) -> List[Dict[str, Any]]:
    """Le quotazioni grezze dal sidecar compresso."""
    import gzip

    with gzip.open(percorso, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def stampa_v4(dati: Dict[str, Any]) -> None:
    print("\n-- POLITICA V4: variante x mercato --")
    intest = ("variante", "mercato", "quote", "tocco", "gambe", "g.fill", "%g.fill",
              "fill", "attesa", "prezzo", "k", "P&L", "P&L/gamba", "DD")
    print("{:<10}{:<17}{:>7}{:>7}{:>7}{:>7}{:>9}{:>6}{:>8}{:>8}{:>7}{:>9}{:>11}{:>8}".format(*intest))
    for r in dati["risultati"]["righe"]:
        k = r["k_realizzato"]
        print("{:<10}{:<17}{:>7}{:>7}{:>7}{:>7}{:>9}{:>6}{:>8}{:>8}{:>7}{:>9}{:>11}{:>8}".format(
            r["variante"], r["mercato"][:16], r["n_quote_emesse"], r["n_quote_al_tocco"],
            r["n_gambe_quotate"], r["n_gambe_con_fill"],
            "-" if r["quota_gambe_con_fill"] is None else "%.1f%%" % (100 * r["quota_gambe_con_fill"]),
            r["n_fill"],
            "-" if r["attesa_mediana_s"] is None else "%.0fs" % r["attesa_mediana_s"],
            "-" if r["prezzo_medio_ottenuto"] is None else "%.1f" % r["prezzo_medio_ottenuto"],
            "-" if k["k"] is None else "%.2f" % k["k"],
            "%.2f" % r["pl_totale_eur"],
            "-" if r["pl_per_gamba_eur"] is None else "%.3f" % r["pl_per_gamba_eur"],
            "%.2f" % r["drawdown_massimo_eur"]))
    print("\n-- SUPERFICIE (variante A): fill%% e k per fascia di minuto x fascia di p_sup --")
    print("{:<8}{:<10}{:<11}{:>8}{:>7}{:>9}{:>9}{:>8}".format(
        "var", "minuti", "p_sup", "quote", "fill", "fill%", "attesa", "k"))
    for r in dati["superficie"]["righe"]:
        if r["variante"] != "A":
            continue
        print("{:<8}{:<10}{:<11}{:>8}{:>7}{:>9}{:>9}{:>8}".format(
            r["variante"], r["fascia_minuto"], r["fascia_psup"], r["n_quote"], r["n_fill"],
            "-" if r["fill_pct"] is None else "%.1f%%" % r["fill_pct"],
            "-" if r["attesa_mediana_s"] is None else "%.0fs" % r["attesa_mediana_s"],
            "-" if r["k"] is None else "%.2f" % r["k"]))
    print("\n-- GIORNO TIPO (%d partite assunte) --"
          % dati["giornata"]["partite_giorno_tipo_assunte"])
    for r in dati["giornata"]["per_variante"]:
        print("  %-10s gambe con fill/partita %.3f -> %.1f al giorno; fill/partita %.3f "
              "-> %.1f al giorno; liability %.0f EUR/giorno"
              % (r["variante"], r["gambe_con_fill_per_partita"],
                 r["gambe_con_fill_giorno_tipo"], r["fill_per_partita"],
                 r["fill_giorno_tipo"], r["liability_impegnata_giorno_tipo_eur"]))




# =========================================================================
# M1-TER — LA QUOTA VIVA AL PREZZO DEL *BIAS DI FASCIA* (non del modello)
# =========================================================================
# M1-bis ha misurato la quota viva al prezzo di riserva del MODELLO
# (`p_sup x k = 2`): 10 fill su 12.486 quotazioni, perche' quel prezzo sta
# 2,7-3,4 volte sotto il mercato. `M4M5M6_2026-09-17.md` §6-bis.3 riscrive il
# prezzo di riserva partendo da cio' che e' MISURATO invece che da cio' che il
# modello crede:
#
#     L*_fascia = (1 - c) / ( p_equa(cella) * k_fascia ) + c
#
#  * `p_equa` = probabilita' DEVIGATA del mercato per quella cella: mid fra i
#    due lati, normalizzato a 1 sui runner ATTIVI. Stessa identica regola di
#    `tools/superficie_liability.py` (>= 6 selezioni prezzate sui DUE lati e
#    somma dei pesi > 0,5: normalizzare mezzo book inventa probabilita').
#  * `k_fascia` = il BIAS PRUDENTE misurato da M6 per quella fascia, letto dal
#    file versionato `data/k_in_gioco_aggregato_2026-09-17.json`
#    (`bias_equo_prudente`). Non e' un numero scritto qui: e' una misura.
#
# **IL MODELLO NON ENTRA NEL PREZZO.** In questa modalita' `omega_v3` non viene
# nemmeno chiamato: l'ammissibilita' e' geometrica (raggiungibile, >= 2 gol) e
# il margine viene dal bias di fascia. Conseguenza pratica: **non servono le
# lambda pre-KO**, quindi si misurano tutte e 39 le registrazioni invece delle
# 22 di M1-bis.
#
# AMMISSIBILITA' — due regole, entrambe misurate, perche' il brief e M6 non
# definiscono la fascia sulla stessa quantita' (divergenza dichiarata, §1 del
# referto):
#   * `m6`    — CORRECT_SCORE, fascia calcolata sulla `p_implicita AL TOCCO`
#               (e' cosi' che M6 definisce le sue fasce: `k_in_gioco` §23-24) e
#               ristretta alle DUE fasce con bias prudente > 1: 0,5-1 % e 1-2 %;
#   * `pequa` — CORRECT_SCORE con `p_equa` fra 0,5 % e 2 % (la lettera del
#               brief), sempre scartando le celle la cui fascia non ha un bias
#               prudente > 1 (operare dove il bias non e' dimostrato e' cio' che
#               `K_MISURATO` §5.2 vieta).
#
# TRE PREZZI (tutti con liability fissa 30 EUR, quota VIVA con riprezzo):
#   (a) esattamente `L*_fascia`, arrotondato al tick verso il basso;
#   (b) al miglior back + 1 tick;
#   (c) al miglior back + 3 tick (verso il mid).
#
# Gli altri pezzi della vita dell'ordine sono quelli di M1-bis e non cambiano:
# riprezzo con isteresi di 1 tick, annullo con latenza 300 ms, mai due ordini
# vivi sulla stessa cella, morte a sospensione / gol / cella impossibile / fine
# finestra, rientro 20 s dopo la riapertura, matching di flumine con la coda.

FINESTRA_V4TER = (1, 85)
MERCATO_V4TER = "CORRECT_SCORE"
# le fasce che M6 misura operabili (bias prudente > 1). NON sono scritte a mano:
# si leggono dal file di M6 e queste sono solo il default se il file manca.
FASCE_OPERABILI_ATTESE = ("0,5-1%", "1-2%")
BANDA_PEQUA_V4TER = (0.005, 0.020)
# devig: la stessa soglia di `superficie_liability` e di `misura_k`
DEVIG_MIN_SELEZIONI = 6
FILE_M6 = "k_in_gioco_aggregato_2026-09-17.json"
# (nome variante, da dove viene il prezzo, regola di ammissibilita')
VARIANTI_V4TER: Tuple[Tuple[str, str, str], ...] = (
    ("a_riserva", "riserva", "m6"),
    ("b_back1", "back+1", "m6"),
    ("c_back3", "back+3", "m6"),
    ("a_riserva_pequa", "riserva", "pequa"),
    ("b_back1_pequa", "back+1", "pequa"),
    ("c_back3_pequa", "back+3", "pequa"),
)
# quante celle si quotano insieme: TUTTE le ammissibili, dentro il cap di caso
# peggiore. Con 39 registrazioni e un fill ogni tanto, quotare una cella sola
# darebbe un campione troppo piccolo per una selezione avversa con intervallo.
CELLE_V4TER = 60


def bias_di_fascia(percorso: Optional[str] = None) -> Dict[Tuple[str, str], float]:
    """(mercato, fascia) -> bias EQUO PRUDENTE misurato da M6.

    Dal file versionato di M6 (`data/k_in_gioco_aggregato_2026-09-17.json`,
    campo `bias_equo_prudente`). Le fasce sono quelle di `misura_k.SECCHI`,
    calcolate sulla `p_implicita AL TOCCO`: la stessa convenzione, cosi' il
    numero di M6 si incolla qui senza tradurre niente."""
    p = percorso or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", FILE_M6)
    fuori: Dict[Tuple[str, str], float] = {}
    try:
        with open(p, "r", encoding="utf-8") as fh:
            dati = json.load(fh)
    except (OSError, ValueError):
        return fuori
    for r in dati.get("righe", ()):
        v = r.get("bias_equo_prudente")
        if v is None:
            continue
        fuori[(str(r.get("mercato")), str(r.get("fascia")))] = float(v)
    return fuori


def probabilita_eque(book: Any, stati: Optional[Dict[int, str]] = None
                     ) -> Tuple[Dict[int, float], Dict[str, Any]]:
    """`p_equa` per selezione: mid fra i due lati, normalizzato sui runner ATTIVI.

    Riga per riga la regola di `tools/superficie_liability.py` (righe 334-390):
    si scartano i runner senza entrambi i lati e i book INCROCIATI, si somma
    `0,5 (1/lay + 1/back)` e si normalizza. Se meno di `DEVIG_MIN_SELEZIONI`
    selezioni sono prezzate sui due lati, o la somma dei pesi e' <= 0,5, NON si
    deviga: normalizzare mezzo book inventa probabilita'.
    """
    from flumine.utils import get_price

    pesi: Dict[int, float] = {}
    for runner in getattr(book, "runners", ()) or ():
        sid = int(getattr(runner, "selection_id", 0) or 0)
        stato = (stati or {}).get(sid) or str(getattr(runner, "status", "") or "")
        if stato != "ACTIVE":
            continue
        bl = get_price(runner.ex.available_to_lay, 0)
        bb = get_price(runner.ex.available_to_back, 0)
        if not bl or not bb:
            continue
        bl, bb = float(bl), float(bb)
        if bb >= bl or bl <= 1.0 or bb <= 1.0:
            continue                     # book incrociato: non e' un prezzo
        pesi[sid] = 0.5 * (1.0 / bl + 1.0 / bb)
    somma = sum(pesi.values())
    ok = bool(len(pesi) >= DEVIG_MIN_SELEZIONI and somma > 0.5)
    diagnostica = {"n_mid": len(pesi), "somma_mid": round(somma, 4), "devig_ok": ok}
    if not ok:
        return {}, diagnostica
    return {sid: w / somma for sid, w in pesi.items()}, diagnostica


class MisuraV4Ter(MisuraV4):
    """La politica M1-ter: quota viva col prezzo di riserva del BIAS DI FASCIA."""

    def __init__(self, event_id: str, *, catalogo: Any, esiti: Dict[str, Optional[int]],
                 par: Dict[str, Any]) -> None:
        super().__init__(event_id, catalogo=catalogo, esiti=esiti, par=par)
        # solo il CORRECT SCORE: M6 misura un bias prudente > 1 solo li'
        self.mercati = {mid: mt for mid, mt in self.mercati.items()
                        if mt == MERCATO_V4TER}
        self.mondi = [
            MondoV4(nome, CELLE_V4TER, None, None,
                    liability_gamba=float(par["liability_gamba"]),
                    commissione=float(par["commissione"]),
                    prezzo_da=prezzo_da, ammissibilita=amm)
            for nome, prezzo_da, amm in VARIANTI_V4TER]
        self.bias = dict(par["bias_fascia"])
        # il modello non serve: senza lambda si quota lo stesso
        self.lambdas = (0.0, 0.0)
        self.fonte_lambdas = "non_usato (il prezzo viene dal bias di fascia)"
        self.devig_ko = 0
        self.devig_ok = 0

    def _risolvi_lambdas(self, payload: Optional[dict]) -> None:
        return None                      # in M1-ter il modello non entra

    # ------------------------------------------------------------ candidati
    def _candidati(self, market_id: str, mercato: str, minuto: float,
                   punteggio: Tuple[int, int], book: Any) -> List[Dict[str, Any]]:
        from flumine.utils import get_price, get_size

        from . import misura_k as MK
        from .. import omega_v3 as V3

        p_eque, diag = probabilita_eque(book)
        if not p_eque:
            self.devig_ko += 1
            return []
        self.devig_ok += 1
        c = float(self.par["commissione"])
        distanza = int(self.par["distanza_minima_gol"])
        sh, sa = punteggio
        nomi_mercato = self.catalogo.nomi.get(str(market_id), {})
        fuori: List[Dict[str, Any]] = []
        for runner in getattr(book, "runners", ()) or ():
            if str(getattr(runner, "status", "") or "") != "ACTIVE":
                continue
            sid = int(getattr(runner, "selection_id", 0) or 0)
            nome = str(nomi_mercato.get(sid) or "")
            coppia = V3.parse_scoreline(nome)
            if coppia is None:
                continue                 # mai gli aggregati
            h, a = coppia
            if h < sh or a < sa:
                continue                 # cella ormai impossibile
            if (h - sh) + (a - sa) < distanza:
                continue                 # corrente o adiacente
            p_equa = p_eque.get(sid)
            if not p_equa or p_equa <= 0:
                continue
            atl = get_price(runner.ex.available_to_lay, 0)
            atb = get_price(runner.ex.available_to_back, 0)
            if not atl or not atb or float(atb) >= float(atl):
                continue                 # senza i due lati non c'e' ne' p_equa ne' prezzo
            atl, atb = float(atl), float(atb)
            p_tocco = MK.p_implicita(atl, c)
            if p_tocco is None:
                continue
            fascia = MK.secchio_di(p_tocco)          # LA FASCIA E' QUELLA DEL TOCCO
            k_fascia = self.bias.get((mercato, fascia))
            if k_fascia is None or k_fascia <= 1.0:
                continue                 # bias non dimostrato: non si opera
            l_stella = (1.0 - c) / max(1e-12, p_equa * k_fascia) + c
            prezzi = self._prezzi(l_stella, atb, atl)
            if not prezzi:
                continue
            fuori.append({
                "selection_id": sid, "nome": nome,
                "p_equa": float(p_equa), "p_sup": float(p_equa),
                "p_centro": float(p_equa), "k_fascia": float(k_fascia),
                "fascia": fascia, "fascia_psup": fascia,
                "l_stella": float(l_stella),
                "prezzo_tocco": atl, "prezzo_back": atb,
                "size_tocco": float(get_size(runner.ex.available_to_lay, 0) or 0.0),
                "prezzi": prezzi,
                "in_banda_pequa": bool(BANDA_PEQUA_V4TER[0] <= p_equa <= BANDA_PEQUA_V4TER[1]),
                "n_devig": diag["n_mid"],
            })
        # ordinamento: la cella con piu' margine al prezzo di riserva per euro di
        # liability; con la quotazione aperta a tutte le celle conta poco, ma
        # tiene un ordine stabile e riproducibile
        fuori.sort(key=lambda d: (-d["k_fascia"], d["prezzi"]["riserva"]["prezzo"]))
        return fuori

    def _prezzi(self, l_stella: float, best_back: float, best_lay: float
                ) -> Dict[str, Dict[str, Any]]:
        """I tre prezzi della misura, con il loro modo e il prezzo a cui si
        scambierebbe davvero."""
        c = float(self.par["commissione"])
        fuori: Dict[str, Dict[str, Any]] = {}
        grezzi = {
            "riserva": _tick_giu(min(l_stella, 1000.0)),
            "back+1": _tick(best_back, 1),
            "back+3": _tick(best_back, 3),
        }
        for nome, prezzo in grezzi.items():
            if prezzo is None or prezzo <= 1.01:
                continue
            if prezzo >= best_lay - 1e-9:
                # il prezzo che si vorrebbe e' gia' disponibile: si PRENDE al
                # tocco (FOK fino al limite), e si scambia al prezzo del book
                modo = "tocco"
                limite = _tick_giu(min(prezzo, 1000.0))
                if limite is None:
                    continue
                fuori[nome] = {"prezzo": float(limite), "modo": modo,
                               "prezzo_effettivo": float(best_lay)}
                continue
            fuori[nome] = {"prezzo": float(prezzo), "modo": "passivo",
                           "prezzo_effettivo": float(prezzo)}
        return fuori

    def _per_mondo(self, mondo: MondoV4, cand: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Il prezzo della VARIANTE e la regola di AMMISSIBILITA' del mondo."""
        from . import misura_k as MK

        if mondo.ammissibilita == "m6":
            if cand["fascia"] not in self.par["fasce_operabili"]:
                return None
        elif mondo.ammissibilita == "pequa":
            if not cand["in_banda_pequa"]:
                return None
        scelto = (cand.get("prezzi") or {}).get(mondo.prezzo_da or "riserva")
        if not scelto:
            return None
        c = float(self.par["commissione"])
        p_impl = MK.p_implicita(float(scelto["prezzo_effettivo"]), c)
        if p_impl is None:
            return None
        k_al_prezzo = p_impl / max(1e-12, float(cand["p_equa"]))
        d = dict(cand)
        d.update({
            "prezzo": float(scelto["prezzo"]),
            "prezzo_effettivo": float(scelto["prezzo_effettivo"]),
            "modo": str(scelto["modo"]),
            "k_al_prezzo": float(k_al_prezzo),
            # EV per unita' di liability al margine EFFETTIVO di questo prezzo:
            # qui `k` NON e' incollato alla soglia (e' il reperto §7.1 di M1-bis),
            # quindi il numero e' informativo
            "ev_liability": ((1.0 - c) * (1.0 - 1.0 / k_al_prezzo)
                             / max(1e-9, float(scelto["prezzo_effettivo"]) - 1.0)),
        })
        return d

    # ------------------------------------------------------------ finestre
    def _finestra(self, mercato: str) -> Tuple[int, int]:
        return FINESTRA_V4TER

    def _minuto_chiusura(self, mercato: str) -> int:
        return int(FINESTRA_V4TER[1])

    def _giro_mercato(self, market_id: str, mercato: str, minuto: float,
                      punteggio: Tuple[int, int]) -> None:
        if mercato != MERCATO_V4TER:
            return
        super()._giro_mercato(market_id, mercato, minuto, punteggio)


def misura_evento_v4ter(event_id: str, cartella: str, *,
                        par: Dict[str, Any]) -> Tuple[List[QuotaV4], Dict[str, Any]]:
    """Una registrazione con la politica M1-ter."""
    from ...stream.backtest import banco_comune as BC
    from .replay_registrazioni import leggi_catalogo

    raw = os.path.join(cartella, str(event_id), "%s.raw.jsonl" % event_id)
    diagnostica: Dict[str, Any] = {"event_id": str(event_id), "errori": [], "note": []}
    if not os.path.exists(raw):
        diagnostica["errori"].append("registrazione assente")
        return [], diagnostica
    catalogo = leggi_catalogo(raw)
    esiti = esiti_dal_catalogo(catalogo)
    misura = MisuraV4Ter(event_id, catalogo=catalogo, esiti=esiti, par=par)
    t0 = time.time()
    esito = BC.replay_evento(event_id=str(event_id), cartella=cartella,
                             servizio=misura.giro, nomi_extra=catalogo.nomi,
                             su_strategia=misura.aggancia)
    misura.chiudi()
    diagnostica.update({
        "durata_s": round(time.time() - t0, 1),
        "giri": esito.giri, "giri_politica": misura.giri_politica,
        "sospensioni": misura.sospensioni, "rientri": misura.rientri,
        "devig_ok": misura.devig_ok, "devig_ko": misura.devig_ko,
        "kickoff": (catalogo.avvio.isoformat() if catalogo.avvio else None),
        "esiti": dict(esiti),
    })
    diagnostica["errori"].extend(list(esito.errori))
    diagnostica["note"].extend(list(esito.note) + list(misura.note))
    quote: List[QuotaV4] = []
    for mondo in misura.mondi:
        quote.extend(mondo.quote)
    return quote, diagnostica


# ---------------------------------------------------------------------------
# SELEZIONE AVVERSA con intervallo — il numero che decide (M4M5M6 §0)
# ---------------------------------------------------------------------------
def selezione_avversa(quote: Sequence[QuotaV4], *, giri_boot: int = 2000,
                      seed: int = 20260917, per_cella: bool = True) -> Dict[str, Any]:
    """frequenza di uscita degli ABBINATI / frequenza di uscita di TUTTI i
    candidati, con IC a grappolo SULLE PARTITE (stessa metrica di M1 §7).

    Il numeratore e il denominatore si ricampionano INSIEME sulla stessa
    partita: sono legati (le stesse partite producono entrambi), e trattarli
    come indipendenti darebbe un intervallo falsamente stretto.
    """
    import random

    con_esito = [q for q in quote if q.esito_cella is not None]
    if not con_esito:
        return {"n_candidati": 0, "n_abbinati": 0, "fattore": None}
    # UNITA' = la CELLA distinta della gamba, non la singola quotazione: una
    # cella riquotata 40 volte e' UNA candidata, non quaranta (M1 §7 conta le
    # celle). Il conto per quotazione resta nel JSON come riferimento.
    if per_cella:
        viste: Dict[Tuple[str, str, int], QuotaV4] = {}
        for q in con_esito:
            chiave = (q.event_id, q.market_id, int(q.selection_id))
            precedente = viste.get(chiave)
            if precedente is None or (q.abbinato and not precedente.abbinato):
                viste[chiave] = q
        con_esito = list(viste.values())
    per_partita: Dict[str, List[int]] = {}
    for q in con_esito:
        cella = per_partita.setdefault(q.event_id, [0, 0, 0, 0])
        cella[1] += 1
        cella[0] += 1 if q.esito_cella else 0
        if q.abbinato:
            cella[3] += 1
            cella[2] += 1 if q.esito_cella else 0
    usc_t = sum(v[0] for v in per_partita.values())
    tot_t = sum(v[1] for v in per_partita.values())
    usc_a = sum(v[2] for v in per_partita.values())
    tot_a = sum(v[3] for v in per_partita.values())
    f_tutti = (usc_t / tot_t) if tot_t else None
    f_abb = (usc_a / tot_a) if tot_a else None
    fattore = (f_abb / f_tutti) if (f_abb is not None and f_tutti) else None
    chiavi = list(per_partita)
    rng = random.Random(seed)
    campioni: List[float] = []
    m = len(chiavi)
    for _ in range(max(1, int(giri_boot))):
        a = b = x = y = 0
        for _ in range(m):
            v = per_partita[chiavi[rng.randrange(m)]]
            a += v[0]
            b += v[1]
            x += v[2]
            y += v[3]
        if b and y and a:
            campioni.append((x / y) / (a / b))
    campioni.sort()
    lo = campioni[int(0.025 * (len(campioni) - 1))] if campioni else None
    hi = campioni[int(0.975 * (len(campioni) - 1))] if campioni else None
    return {
        "n_candidati": tot_t, "uscite_candidati": usc_t,
        "n_abbinati": tot_a, "uscite_abbinati": usc_a,
        "partite": len(per_partita),
        "frequenza_candidati": (round(f_tutti, 6) if f_tutti is not None else None),
        "frequenza_abbinati": (round(f_abb, 6) if f_abb is not None else None),
        "fattore": (round(fattore, 3) if fattore is not None else None),
        "ic_lo": (round(lo, 3) if lo is not None else None),
        "ic_hi": (round(hi, 3) if hi is not None else None),
        "giri_utili": len(campioni),
        "unita": "cella" if per_cella else "quotazione",
        "soglia_arresto": SOGLIA_SELEZIONE_AVVERSA,
    }


# La soglia del criterio di arresto, misurata dal Monte Carlo di M5
# (`M4M5M6_2026-09-17.md` §0): sopra questo fattore di selezione avversa V4 perde.
SOGLIA_SELEZIONE_AVVERSA = 1.27


def aggrega_v4ter(quote: Sequence[QuotaV4], *, kickoff: Dict[str, Optional[str]],
                  giri_boot: int, commissione: float) -> Dict[str, Any]:
    """Per variante x fascia: quote, fill, attesa, k realizzato, selezione
    avversa con IC, P&L e drawdown."""
    righe: List[Dict[str, Any]] = []
    varianti = [v[0] for v in VARIANTI_V4TER]
    for variante in varianti:
        base = [q for q in quote if q.variante == variante]
        if not base:
            continue
        fasce = ["tutte"] + sorted({q.fascia_psup for q in base})
        for fascia in fasce:
            g = base if fascia == "tutte" else [q for q in base if q.fascia_psup == fascia]
            if not g:
                continue
            gambe = {(q.event_id, q.market_id) for q in g}
            abb = [q for q in g if q.abbinato]
            gambe_fill = {(q.event_id, q.market_id) for q in abb}
            per_gamba: Dict[Tuple[str, str], float] = {}
            senza_esito = set()
            for q in abb:
                chiave = (q.event_id, q.market_id)
                if q.pl_regolamento is None:
                    senza_esito.add(chiave)
                    continue
                per_gamba[chiave] = per_gamba.get(chiave, 0.0) + float(q.pl_regolamento)
            for chiave in senza_esito:
                per_gamba.pop(chiave, None)
            ordinate = sorted(per_gamba.items(),
                              key=lambda kv: (kickoff.get(kv[0][0]) or "", kv[0][1]))
            serie = [v for _k, v in ordinate]
            riga = {
                "variante": variante, "fascia": fascia,
                "n_quote": len(g), "n_quote_al_tocco": sum(1 for q in g if q.modo == "tocco"),
                "n_gambe": len(gambe), "n_gambe_con_fill": len(gambe_fill),
                "n_fill": len(abb),
                "fill_pct": (round(100.0 * len(abb) / len(g), 3) if g else None),
                "attesa_mediana_s": _mediana([q.attesa_s for q in abb]),
                "prezzo_medio_quotato": _media([q.prezzo_passivo for q in g]),
                "prezzo_medio_ottenuto": _media([q.prezzo_ottenuto for q in abb]),
                "l_stella_mediana": _mediana([q.l_stella for q in g]),
                "k_al_prezzo_mediano": _mediana([q.k_al_prezzo for q in g]),
                "quote_sopra_riserva": sum(1 for q in g if q.prezzo_passivo > q.l_stella + 1e-9),
                "liability_mediana": _mediana([q.liability for q in abb]),
                "quote_sotto_minimo_it": sum(1 for q in g if q.sotto_minimo_it),
                "pl_totale_eur": round(sum(serie), 2),
                "n_gambe_nel_pl": len(serie),
                "pl_per_gamba_eur": (round(sum(serie) / len(serie), 4) if serie else None),
                "drawdown_massimo_eur": _drawdown(serie),
                "pl_se_chiuso_a_finestra_eur": (
                    round(sum(q.pl_chiusura_finestra for q in abb
                              if q.pl_chiusura_finestra is not None), 2)
                    if any(q.pl_chiusura_finestra is not None for q in abb) else None),
                "attraversati": sum(1 for q in abb if q.attraversato),
                "pre_gol": sum(1 for q in abb if q.pre_gol),
            }
            riga["k_realizzato"] = _k_e_ic(abb, giri_boot=giri_boot,
                                          commissione=commissione)
            riga["selezione_avversa"] = selezione_avversa(g, giri_boot=giri_boot)
            riga["selezione_avversa_per_quotazione"] = selezione_avversa(
                g, giri_boot=giri_boot, per_cella=False)
            righe.append(riga)
    return {"righe": righe}


def parametri_v4ter(*, liability: float = LIABILITY_GAMBA_EUR,
                    cadenza_s: float = 1.0,
                    file_m6: Optional[str] = None) -> Dict[str, Any]:
    from .. import omega_config

    d = omega_config.DEFAULTS
    bias = bias_di_fascia(file_m6)
    return {
        "liability_gamba": float(liability),
        "k_soglia": None,                  # in M1-ter il margine e' il bias di fascia
        "fattore_psup": None,
        "cadenza_s": float(cadenza_s),
        "latenza_annullo_s": LATENZA_ANNULLO_S,
        "rientro_dopo_sospensione_s": RIENTRO_DOPO_SOSPENSIONE_S,
        "commissione": float(d["commission_pct"]) / 100.0,
        "distanza_minima_gol": int(d["v3_distanza_minima_gol"]),
        "parametri_modello": None,
        "bias_fascia": bias,
        "fasce_operabili": tuple(sorted(f for (m, f), v in bias.items()
                                        if m == MERCATO_V4TER and v > 1.0)),
        "finestre": {MERCATO_V4TER: list(FINESTRA_V4TER)},
    }


def main_v4ter(args: Any) -> int:
    cartella = args.cartella
    eventi = args.eventi if args.eventi else eventi_disponibili(cartella)
    par = parametri_v4ter(liability=args.liability, cadenza_s=args.cadenza_s)
    operabili = {k: v for k, v in par["bias_fascia"].items() if v > 1.0}
    print("POLITICA V4-TER (bias di fascia) — registrazioni: %d" % len(eventi), flush=True)
    print("liability/gamba %.2f EUR, cadenza %.0f s, finestra %s, mercato %s"
          % (par["liability_gamba"], par["cadenza_s"], FINESTRA_V4TER, MERCATO_V4TER),
          flush=True)
    print("bias di fascia OPERABILI (da %s): %s"
          % (FILE_M6, {"%s %s" % k: v for k, v in sorted(operabili.items())}), flush=True)
    if not operabili:
        print("NESSUNA fascia operabile: il file di M6 manca o non ha bias > 1")
        return 2

    tutte: List[QuotaV4] = []
    diagnostiche: List[Dict[str, Any]] = []
    kickoff: Dict[str, Optional[str]] = {}
    t0 = time.time()
    for i, eid in enumerate(eventi, 1):
        try:
            quote, diag = misura_evento_v4ter(eid, cartella, par=par)
        except Exception as ex:  # noqa: BLE001 - un errore e' un referto
            import traceback
            quote, diag = [], {"event_id": eid,
                               "errori": ["%s: %s" % (type(ex).__name__, ex)],
                               "traccia": traceback.format_exc()[-800:]}
        tutte.extend(quote)
        diagnostiche.append(diag)
        kickoff[str(eid)] = diag.get("kickoff")
        print("  [%d/%d] %s  quote=%d fill=%d  devig ok/ko=%s/%s  %ss  %s"
              % (i, len(eventi), eid, len(quote),
                 sum(1 for q in quote if q.abbinato), diag.get("devig_ok"),
                 diag.get("devig_ko"), diag.get("durata_s", "?"),
                 ";".join(diag.get("errori", []))[:70]), flush=True)

    dati = {
        "generato_il": "2026-09-17",
        "politica": "v4ter — quota viva col prezzo di riserva del BIAS DI FASCIA (M6)",
        "fonte": "_live_raw via banco_comune.replay_evento",
        "matching": "flumine SimulatedOrder 2.13.11, coda _piq, delta trd da "
                    "RunnerAnalytics, simulation_available_prices=False, isolamento per ordine",
        "prezzo_di_riserva": "L*_fascia = (1-c)/(p_equa * k_fascia) + c; p_equa devigata "
                             "come in tools/superficie_liability.py; k_fascia = "
                             "bias_equo_prudente di M6 (%s)" % FILE_M6,
        "modello": "NON USATO: in M1-ter il prezzo non viene dal modello",
        "bias_fascia_usato": {"%s|%s" % k: v for k, v in sorted(par["bias_fascia"].items())},
        "parametri": {k: (list(v) if isinstance(v, tuple) else v)
                      for k, v in par.items()
                      if k not in ("parametri_modello", "bias_fascia")},
        "varianti": [{"nome": n, "prezzo_da": p, "ammissibilita": a}
                     for n, p, a in VARIANTI_V4TER],
        "banda_pequa": list(BANDA_PEQUA_V4TER),
        "celle_quotate_insieme": CELLE_V4TER,
        "soglia_selezione_avversa": SOGLIA_SELEZIONE_AVVERSA,
        "registrazioni": diagnostiche,
        "n_registrazioni": len(eventi),
        "n_quote": len(tutte),
        "risultati": aggrega_v4ter(tutte, kickoff=kickoff, giri_boot=args.boot,
                                   commissione=par["commissione"]),
        "superficie": superficie_v4(tutte, giri_boot=args.boot,
                                    commissione=par["commissione"]),
        "giornata": conto_di_giornata(tutte, kickoff=kickoff, registrazioni=len(eventi),
                                      partite_giorno_tipo=args.partite_giorno),
        "quote_abbinate": [q.a_dizionario() for q in tutte if q.abbinato],
        "quote_file": os.path.basename(_percorso_quote(args.out)),
        "durata_totale_s": round(time.time() - t0, 1),
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(dati, fh, ensure_ascii=False, indent=1, sort_keys=True, default=str)
    scrivi_quote(_percorso_quote(args.out), tutte)
    print("scritto %s (+ %s)" % (args.out, _percorso_quote(args.out)))
    stampa_v4ter(dati)
    return 0


def stampa_v4ter(dati: Dict[str, Any]) -> None:
    print("\n-- M1-TER: variante x fascia --")
    print("{:<18}{:<10}{:>8}{:>7}{:>7}{:>8}{:>8}{:>9}{:>8}{:>9}{:>18}{:>9}".format(
        "variante", "fascia", "quote", "gambe", "fill", "fill%", "attesa",
        "prezzo", "k", "P&L", "sel.avversa (IC)", "DD"))
    for r in dati["risultati"]["righe"]:
        k = r["k_realizzato"]
        sa = r["selezione_avversa"]
        avversa = ("-" if sa.get("fattore") is None
                   else "%.2f [%.2f-%.2f]" % (sa["fattore"], sa["ic_lo"] or 0.0,
                                              sa["ic_hi"] or 0.0))
        print("{:<18}{:<10}{:>8}{:>7}{:>7}{:>8}{:>8}{:>9}{:>8}{:>9}{:>18}{:>9}".format(
            r["variante"], r["fascia"], r["n_quote"], r["n_gambe"], r["n_fill"],
            "-" if r["fill_pct"] is None else "%.2f%%" % r["fill_pct"],
            "-" if r["attesa_mediana_s"] is None else "%.0fs" % r["attesa_mediana_s"],
            "-" if r["prezzo_medio_ottenuto"] is None else "%.1f" % r["prezzo_medio_ottenuto"],
            "-" if k["k"] is None else "%.2f" % k["k"],
            "%.2f" % r["pl_totale_eur"], avversa,
            "%.2f" % r["drawdown_massimo_eur"]))
    print("\nsoglia di arresto sulla selezione avversa: %.2f (M4M5M6 §0)"
          % dati["soglia_selezione_avversa"])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def eventi_disponibili(cartella: str) -> List[str]:
    """Le registrazioni vere (i ``_synth_*`` sono finti e si escludono)."""
    fuori: List[str] = []
    if not os.path.isdir(cartella):
        return fuori
    for nome in sorted(os.listdir(cartella)):
        if nome.startswith("_synth"):
            continue
        raw = os.path.join(cartella, nome, "%s.raw.jsonl" % nome)
        if os.path.isfile(raw):
            fuori.append(nome)
    return fuori


def parametri_di_produzione(par: Optional[Dict[str, Any]] = None, *,
                            passo_minuti: int = PASSO_GRIGLIA_MINUTI) -> Dict[str, Any]:
    """Bande, finestre e distanza: DAI DEFAULT DI ``omega_config``, non a mano."""
    from .. import omega_config

    p = omega_config.resolve_params(dict(par or {}))
    finestre = {
        "HALF_TIME_SCORE": (int(p["ht_entry_min"]), int(p["ht_entry_max"])),
        "CORRECT_SCORE": (int(p["ft_entry_min"]), int(p["ft_entry_max"])),
    }
    passo = max(1, int(passo_minuti))
    minuti = {
        mt: tuple(range(inizio, fine, passo)) or (inizio,)
        for mt, (inizio, fine) in finestre.items()
    }
    return {
        "price_min": float(p["price_min"]),
        "price_max": float(p["price_max"]),
        "min_lay_liquidity": float(p["min_lay_liquidity"]),
        "min_goal_distance": int(p["model_min_goal_distance"]),
        "finestre": finestre,
        "minuti": minuti,
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Misura dell'ingresso PASSIVO di Omega sulle registrazioni reali")
    ap.add_argument("--eventi", nargs="*", default=None,
                    help="event_id da misurare (default: tutte le registrazioni vere)")
    ap.add_argument("--cartella", default="_live_raw")
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--passo-minuti", type=int, default=PASSO_GRIGLIA_MINUTI,
                    dest="passo_minuti",
                    help="passo della griglia dei minuti d'ingresso dentro la finestra")
    # --- M1-bis: la politica V4 (quota viva) --------------------------------
    ap.add_argument("--politica", choices=("m1", "v4", "v4ter"), default="m1",
                    help="m1 = ordine appoggiato e dimenticato (17/09 mattina); "
                         "v4 = quota viva col prezzo di riserva del MODELLO (M1-bis); "
                         "v4ter = quota viva col prezzo di riserva del BIAS DI FASCIA "
                         "misurato da M6 (M1-ter)")
    ap.add_argument("--liability", type=float, default=LIABILITY_GAMBA_EUR,
                    help="liability per gamba (EUR) con dimensionamento a liability fissa")
    ap.add_argument("--k-soglia", type=float, default=K_SOGLIA_V4, dest="k_soglia")
    ap.add_argument("--fattore-psup", type=float, default=FATTORE_PSUP,
                    dest="fattore_psup",
                    help="p_sup = p_centro x questo fattore (nessuna SE disponibile)")
    ap.add_argument("--cadenza-s", type=float, default=CADENZA_POLITICA_S,
                    dest="cadenza_s", help="cadenza della politica in TEMPO DI MERCATO")
    ap.add_argument("--partite-giorno", type=int, default=20, dest="partite_giorno",
                    help="partite di un giorno tipo (ASSUNZIONE, serve solo a scalare)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    if not args.out:
        args.out = os.path.join(
            "Betfair", "omega", "data",
            {"v4": "politica_v4_2026-09-17.json",
             "v4ter": "quota_viva_bias_fascia_2026-09-17.json"}.get(
                args.politica, "ingresso_passivo_2026-09-17.json"))
    if args.politica == "v4ter":
        if args.cadenza_s == CADENZA_POLITICA_S:
            args.cadenza_s = 1.0        # M1-ter riprezza a ogni tick di scan
        return main_v4ter(args)
    if args.politica == "v4":
        return main_v4(args)

    cartella = args.cartella
    eventi = args.eventi if args.eventi else eventi_disponibili(cartella)
    par = parametri_di_produzione(passo_minuti=args.passo_minuti)
    print("registrazioni: %d" % len(eventi), flush=True)
    print("bande %.0f-%.0f, liquidita' min %.2f, distanza %d"
          % (par["price_min"], par["price_max"], par["min_lay_liquidity"],
             par["min_goal_distance"]), flush=True)
    print("finestre %s" % (par["finestre"],), flush=True)

    tutti: List[Candidato] = []
    diagnostiche: List[Dict[str, Any]] = []
    t0 = time.time()
    for i, eid in enumerate(eventi, 1):
        try:
            cand, diag = misura_evento(eid, cartella, parametri=par)
        except Exception as ex:  # noqa: BLE001 - un errore e' un referto
            cand, diag = [], {"event_id": eid, "errori": ["%s: %s" % (type(ex).__name__, ex)]}
        tutti.extend(cand)
        diagnostiche.append(diag)
        print("  [%d/%d] %s  candidati=%d  piazzati=%d  abbinati=%d  %ss  %s"
              % (i, len(eventi), eid, len(cand),
                 sum(1 for c in cand if c.piazzato),
                 sum(1 for c in cand if c.abbinato),
                 diag.get("durata_s", "?"), ";".join(diag.get("errori", []))[:80]),
              flush=True)

    dati = {
        "generato_il": "2026-09-17",
        "fonte": "_live_raw (stream Betfair registrato) via banco_comune.replay_evento",
        "matching": "flumine.simulation.simulatedorder.SimulatedOrder (2.13.11), "
                    "delta scambiato da flumine.markets.middleware.RunnerAnalytics, "
                    "simulation_available_prices=False, isolamento PER ORDINE",
        "stake_eur": STAKE_EUR,
        "commissione": COMMISSIONE,
        "parametri": {k: (list(v) if isinstance(v, tuple) else v)
                      for k, v in par.items() if k not in ("finestre", "minuti")},
        "finestre": {k: list(v) for k, v in par["finestre"].items()},
        "minuti_ingresso": {k: list(v) for k, v in par["minuti"].items()},
        "registrazioni": diagnostiche,
        "n_registrazioni": len(eventi),
        "n_candidati": len(tutti),
        "al_tocco": tabella_al_tocco(tutti, giri_boot=args.boot),
        "passivo": aggrega(tutti, giri_boot=args.boot),
        "passivo_per_mercato": aggrega(tutti, giri_boot=args.boot, per_fascia=False),
        "passivo_globale": aggrega(tutti, giri_boot=args.boot, per_fascia=False,
                                   per_mercato=False),
        "candidati": [c.a_dizionario() for c in tutti],
        "durata_totale_s": round(time.time() - t0, 1),
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(dati, fh, ensure_ascii=False, indent=1, sort_keys=True)
    print("scritto %s" % args.out)
    stampa(dati)
    return 0


def stampa(dati: Dict[str, Any]) -> None:
    print("\n-- k AL TOCCO (quello che Omega fa oggi) --")
    print("{:<17}{:<11}{:>7}{:>7}{:>8}{:>9}{:>9}{:>8}{:>9}".format(
        "mercato", "fascia", "n", "part.", "uscite", "p_impl", "p_reale",
        "k", "EV/1EUR"))
    for r in dati["al_tocco"]["righe"]:
        print("{:<17}{:<11}{:>7}{:>7}{:>8}{:>9.4f}{:>9.4f}{:>8}{:>9}".format(
            r["mercato"][:16], r["fascia"], r["n_celle"], r["partite"], r["uscite"],
            r["p_impl_media"], r["p_reale"],
            "-" if r["k_tocco"] is None else "%.2f" % r["k_tocco"],
            "-" if r["ev_tocco"] is None else "%.3f" % r["ev_tocco"]))
    print("\n-- INGRESSO PASSIVO --")
    print("{:<17}{:<11}{:<4}{:>7}{:>7}{:>8}{:>9}{:>8}{:>8}{:>9}".format(
        "mercato", "fascia", "liv", "cand", "piazz", "abbin", "%abbin",
        "attesa_s", "k_pass", "k_tocco"))
    for r in dati["passivo"]["righe"]:
        print("{:<17}{:<11}{:<4}{:>7}{:>7}{:>8}{:>9}{:>8}{:>8}{:>9}".format(
            r["mercato"][:16], r["fascia"], r["livello"], r["n_candidati"],
            r["n_piazzati"], r["n_abbinati"],
            "-" if r["quota_abbinati"] is None else "%.1f%%" % (100 * r["quota_abbinati"]),
            "-" if r["attesa_mediana_s"] is None else "%.0f" % r["attesa_mediana_s"],
            "-" if r["k_passivo"] is None else "%.2f" % r["k_passivo"],
            "-" if r["k_tocco_stesse_celle"] is None else "%.2f" % r["k_tocco_stesse_celle"]))


if __name__ == "__main__":
    raise SystemExit(main())
