"""MIKE SULLE REGISTRAZIONI VERE — il replay col motore ufficiale Betfair.

«Voglio sapere SE RISPETTA LE CONDIZIONI PER CUI E' STATO PROGETTATO. TUTTE.
Deve comunicare con gli ordini, sapere che cosa sta succedendo, e muoversi come
progettato» (utente, 15/09).

CHE COSA FA, in una riga: fa rivivere a Mike una partita registrata, tick per
tick, coi prezzi veri di Betfair, e a OGNI decisione controlla le regole della
Costituzione (`certificazione.py`). Non misura il profitto: misura la condotta.

DA DOVE VIENE OGNI PEZZO — non si e' inventato niente:

  * le partite  : `_live_raw/<id>/<id>.raw.jsonl`, lo stream NATIVO Betfair
                  registrato dal recorder (`Betfair/stream/recorder.py`), piu'
                  il sidecar `<id>.scores.jsonl` per punteggio e minuto;
  * il replay   : `FlumineSimulation` + `HistoricalStream`, cioe' il motore
                  UFFICIALE gia' usato dal Backtest Automatico
                  (`Betfair/stream/backtest/run_backtest.py`). Stessa API,
                  stesso formato file;
  * la qualita' : `Betfair/stream/tools/validate_recordings.py` dice quali
                  registrazioni sono COMPLETE. Una registrazione monca fa
                  mentire qualsiasi verdetto, quindi il referto la dichiara;
  * la lettura  : il payload passa dal `feed.py` VERO di Mike
                  (`event_info` + `snapshot_from_row`). **Questo e' il punto.**
                  Costruire lo `Snapshot` a mano qui dentro avrebbe voluto dire
                  scrivere l'ennesimo finto che parla una lingua diversa dal
                  vero — la causa di tutti e cinque i difetti del 15/09. Cosi'
                  invece si certifica anche il feed;
  * le decisioni: `engine.decide` e `engine.apply_decision`, che sono pure.

  * gli ordini : si piazzano DAVVERO, con `market.place_order(...)`, e chi
                 decide se e quanto si abbinano e' il matching di flumine —
                 non una regola scritta qui.

IL MATCHING E' QUELLO DI FLUMINE, CODA COMPRESA. `flumine/simulation/
simulatedorder.py` al piazzamento registra `_piq` = la size gia' presente
DAVANTI a noi a quel prezzo, e a ogni aggiornamento del book `_process_traded`
consuma quella coda col volume realmente scambiato (`trd`) prima di abbinare il
nostro ordine, assumendo prudentemente che solo META' del volume sia dal nostro
lato. E' la coda vera della partita registrata.

Cosi' gli ordini sono OGGETTI VERI, con `bet_id`, `status`, `size_matched`,
`average_price_matched` e `size_remaining`: cioe' esattamente la superficie su
cui il 15/09 Mike ha collezionato cinque difetti. Leggere l'esito, riconoscere
un ordine, sapere se e' abbinato — qui viene certificato, non simulato.

Uso:
    python -m Betfair.mike.tools.replay_registrazioni            # tutte
    python -m Betfair.mike.tools.replay_registrazioni 35674515   # una
    python -m Betfair.mike.tools.replay_registrazioni --complete # solo COMPLETE

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import os
import sys
from bisect import bisect_right
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .. import certificazione as CERT
from .. import config as C
from .. import engine as E
from .. import feed as F
from .. import service as S
from .banco import DbMemoria, MercatoFlumine
# i lettori di un livello del ladder ESISTONO GIA': flumine in simulazione
# espone `available_to_back` come dict {'price','size'}, betfairlightweight
# live come oggetto `.price/.size`, il raw come `[price, size]`. Leggerli con
# `getattr` prende None da un dict — in SILENZIO, ed e' esattamente il
# difetto che ha prodotto i cinque incidenti del 15/09. Si riusano i lettori
# gia' scritti e gia' provati del Backtest Automatico.
from ...stream.backtest.sim_strategy import _offer_price, _offer_size

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GLI SCENARI — le condizioni rare non si aspettano, si provocano
# ---------------------------------------------------------------------------
# Una registrazione racconta la partita che e' andata come e' andata. Certe
# regole del bot non si possono mettere alla prova sperando che capiti il caso
# giusto: il tetto di rischio non scatta mai se il tetto e' spento, e il freno
# del bot fermo non scatta mai se il bot e' acceso.
#
# Questi scenari cambiano SOLO i parametri o la freschezza del feed — mai la
# partita, mai i prezzi, mai la strategia. Sono le stesse manopole che l'utente
# ha nella UI, girate apposta per far parlare i controlli che tacciono.
SCENARI: Dict[str, Dict[str, Any]] = {
    # come gira in produzione
    "base": {},
    # uscita pre-match a mercato invece che appoggiata: e' l'altro ramo della
    # Fase 1, e senza di esso PRE_GREEN_PENDING non si vede mai
    "taker": {"pre_exit_mode": "taker"},
    # tetto di rischio STRETTO: fa parlare il clamp dentro il motore (§4.9)
    # 12 EUR: lo stake da 10 passa, la copertura no. Con 8 l'ingresso non
    # avverrebbe proprio e il controllo del tetto non avrebbe MAI un caso.
    "cap-stretto": {"max_liability_per_match": 12.0},
    # bot fermo / stop giornaliero: nessuna apertura, le chiusure restano (§5)
    "bot-fermo": {"pre_enabled": False, "reentry_enabled": False},
    # seconda puntata spenta: l'altro ramo del gol precoce (§15.3)
    "senza-seconda-puntata": {"second_entry_enabled": False},
}

# scenario speciale: non tocca i parametri ma INVECCHIA la riga del feed, per
# far scattare la regola «feed stantio: nessun ingresso, chiusure permesse».
SCENARIO_FEED_STANTIO = "feed-stantio"

# scenario speciale: fa FALLIRE i primi piazzamenti con un esito IGNOTO (la
# stessa eccezione che in produzione arriva da un timeout REST). E' l'unico
# modo di far nascere le gambe `pending_reconcile`, e quindi di mettere alla
# prova le regole che le governano: «via le aperture, restano le riduzioni di
# rischio» (§5) e «una gamba a esito ignoto non si da' mai per annullata»
# (§4.11). Nel replay non esistono errori di rete: se non li si provoca, quelle
# due regole non vengono verificate MAI.
SCENARIO_ESITI_IGNOTI = "esiti-ignoti"
QUANTI_GUASTI = 3

# le due linee che interessano a Mike, coi nomi di mercato Betfair
_LINEE = {"OVER_UNDER_35": 3.5, "OVER_UNDER_45": 4.5}


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(int(ms) / 1000.0, tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# da MarketBook flumine al payload che Mike legge davvero
# ---------------------------------------------------------------------------
def blocco_ou(market_book: Any, linea: float, pt_ms: int) -> Optional[Dict[str, Any]]:
    """Un blocco ``ou`` del feed unico, ricavato da un MarketBook flumine.

    E' la forma che `feed.ou_blocks`/`feed._book_for` si aspettano:
    ``{line, market_id, status, inplay, bet_delay, seen_ms, selections:[...]}``
    con ogni selezione che porta ``back/back_size/lay/lay_size``.

    I nomi delle selezioni NON sono nello stream: si usa `sort_priority`, che su
    Betfair per le linee Over/Under vale 1 = Under, 2 = Over (la stessa
    convenzione di `sim_strategy._synth_name`). `feed.canonical_selection` sa
    leggere sia il nome sia la posizione, quindi il nome si scrive esplicito.
    """
    md = getattr(market_book, "market_definition", None)
    sels: List[Dict[str, Any]] = []
    priorita: Dict[int, int] = {}
    for rd in getattr(md, "runners", None) or []:
        sid = getattr(rd, "selection_id", None)
        if sid is not None:
            priorita[int(sid)] = int(getattr(rd, "sort_priority", 0) or 0)
    for r in getattr(market_book, "runners", None) or []:
        sid = int(r.selection_id)
        ex = getattr(r, "ex", None)
        atb = (getattr(ex, "available_to_back", None) if ex else None) or []
        atl = (getattr(ex, "available_to_lay", None) if ex else None) or []
        sp = priorita.get(sid, 0)
        nome = (f"Under {linea} Goals" if sp == 1 else
                f"Over {linea} Goals" if sp == 2 else "")
        sels.append({
            "selection_id": sid,
            "name": nome,
            "back": _offer_price(atb[0]) if atb else None,
            "back_size": _offer_size(atb[0]) if atb else None,
            "lay": _offer_price(atl[0]) if atl else None,
            "lay_size": _offer_size(atl[0]) if atl else None,
            "sort_priority": sp,
        })
    if not sels:
        return None
    return {
        "line": linea,
        "market_id": str(market_book.market_id),
        "status": str(getattr(market_book, "status", None)
                      or getattr(md, "status", None) or "OPEN").upper(),
        "inplay": bool(getattr(market_book, "inplay", False)
                       or getattr(md, "in_play", False)),
        "bet_delay": int(getattr(market_book, "bet_delay", 0) or 0),
        # `seen_ms` = l'ultimo book RICEVUTO: nel replay e' il publish time del
        # tick, che e' esattamente la stessa cosa (vedi `feed.blocco_osservato`).
        "seen_ms": int(pt_ms),
        "total_matched": getattr(market_book, "total_matched", None),
    } | {"selections": sels}


def payload_evento(event_id: str, blocchi: Dict[str, Dict[str, Any]],
                   ko_iso: Optional[str], nome: str,
                   minuto: Optional[int], gol_casa: int, gol_fuori: int,
                   inplay: bool) -> Dict[str, Any]:
    """Il payload del feed unico per questo istante, come lo scriverebbe lo scanner."""
    return {
        "event_name": nome,
        "open_date": ko_iso,
        "inplay": bool(inplay),
        "minute": minuto if isinstance(minuto, int) else None,
        "score_home": int(gol_casa),
        "score_away": int(gol_fuori),
        "ou": [b for b in blocchi.values() if b],
    }


# ---------------------------------------------------------------------------
# la strategia flumine: raccoglie i book, fa decidere Mike, certifica
# ---------------------------------------------------------------------------
def _crea_strategia():
    from flumine import BaseStrategy
    from flumine.order.ordertype import LimitOrder
    from flumine.order.trade import Trade

    class MikeCert(BaseStrategy):
        """Ad ogni tick del replay costruisce il payload, chiama il feed VERO di
        Mike, fa decidere il motore e verifica le regole."""

        def __init__(self, *, event_id: str, params: Dict[str, Any],
                     scores: List[Tuple[int, Optional[int], int, int]],
                     ogni_ms: int = 1000, **kw: Any) -> None:
            self.event_id = str(event_id)
            self.params = params
            self._scores = sorted(scores or [], key=lambda x: x[0])
            self._score_ts = [s[0] for s in self._scores]
            self.ogni_ms = int(ogni_ms)
            self.invecchia_s = float(kw.pop("invecchia_s", 0.0) or 0.0)

            self.blocchi: Dict[str, Dict[str, Any]] = {}
            # i mercati flumine, per market_id: servono per piazzare davvero
            self.mercati: Dict[str, Any] = {}
            # l'ordine flumine di ogni gamba: leg.ref -> BetfairOrder
            self.ordini: Dict[str, Any] = {}
            self.senza_ordine: List[str] = []
            self.ko_iso: Optional[str] = None
            self.nome: str = ""
            self.ctx = E.MatchCtx()
            # IL BANCO: database in memoria e mercato flumine. Da qui in poi il
            # giro lo fa `service._run_event`, cioe' il bot INTERO — cervello
            # e mani. Le gambe non le tiene piu' questo file: stanno nel `ctx`
            # dell'evento, esattamente come in produzione.
            self.db = DbMemoria({"status": "running", "mode": "live", "params": params})
            self.mercato = MercatoFlumine(self)
            self.referto = CERT.Referto(event_id=str(event_id))
            self._ultimo_ms: int = 0
            self._stati: List[str] = []
            self._info: Optional[F.EventInfo] = None
            super().__init__(**kw)

        # ---------------------------------------------------------- flumine
        def check_market_book(self, market, market_book) -> bool:
            return True

        def process_market_book(self, market, market_book) -> None:
            md = getattr(market_book, "market_definition", None)
            mtype = str(getattr(md, "market_type", None)
                        or getattr(market, "market_type", None) or "")
            linea = _LINEE.get(mtype)
            if linea is None:
                return                     # Mike guarda solo O/U 3.5 e 4.5
            pt = getattr(market_book, "publish_time", None)
            pt_ms = int(pt.timestamp() * 1000) if pt is not None else 0
            blk = blocco_ou(market_book, linea, pt_ms)
            if blk is None:
                return
            self.blocchi[mtype] = blk
            self.mercati[str(market_book.market_id)] = market
            # il banco ha bisogno del book CORRENTE per dare l'esito immediato
            # del place, come fa Betfair via REST
            self.mercato.book[str(market_book.market_id)] = market_book
            if self.ko_iso is None:
                mt = getattr(md, "market_time", None) or getattr(md, "open_date", None)
                if mt is not None:
                    self.ko_iso = mt.isoformat() if hasattr(mt, "isoformat") else str(mt)
                self.nome = str(getattr(md, "event_name", None) or self.event_id)
            self.referto.tick += 1
            # Mike gira ogni 1-2 secondi: nel replay si decide alla stessa
            # cadenza, non ad ogni singolo messaggio dello stream.
            if pt_ms - self._ultimo_ms < self.ogni_ms:
                return
            self._ultimo_ms = pt_ms
            self._un_giro(pt_ms)

        # ------------------------------------------------------------ Mike
        def _un_giro(self, pt_ms: int) -> None:
            if len(self.blocchi) < 1 or not self.ko_iso:
                return
            # ⚠️ `seen_ms` = «qualcuno sta ancora GUARDANDO questo mercato»
            # (`feed.blocco_osservato`), NON «il prezzo e' cambiato». Nel replay
            # stiamo guardando tutte e due le linee di continuo: il book di una
            # linea che non manda tick e' fermo, non morto — write-on-change.
            # Mettendo `seen_ms` all'ultimo tick DI QUEL mercato, la linea piu'
            # lenta risultava non osservata e Mike vedeva «book assente» per
            # tutta la finestra utile. E' un difetto del banco di prova, non del
            # bot: qui si allinea al momento del giro.
            for b in self.blocchi.values():
                b["seen_ms"] = int(pt_ms)
            gc, gf, minuto = self._score_at(pt_ms)
            inplay = any(bool(b.get("inplay")) for b in self.blocchi.values())
            payload = payload_evento(self.event_id, self.blocchi, self.ko_iso,
                                     self.nome, minuto, gc, gf, inplay)
            # `invecchia_s` > 0: la riga del feed si dichiara vecchia di tot
            # secondi. Non cambia NESSUN prezzo: cambia solo da quanto tempo
            # non arriva, che e' cio' che la regola del feed stantio misura.
            row = {"payload": payload,
                   "updated_at": _iso(pt_ms - int(self.invecchia_s * 1000))}
            now = pt_ms / 1000.0

            info = F.event_info(self.event_id, payload)
            if not info.complete:
                return                     # senza entrambe le linee Mike non opera
            self._info = info
            snap = F.snapshot_from_row(row, info, now=now, params=self.params,
                                       # con la riga vecchia MA lo scanner vivo il
                                       # feed resta fresco (write-on-change): per
                                       # provocare lo stantio invecchiano entrambi
                                       scanner_age_s=self.invecchia_s or 0.0)
            if snap is None:
                return

            # ── IL BOT INTERO, non solo il motore ────────────────────────
            # `service._run_event` fa il giro vero: snapshot -> decide ->
            # ESEGUE gli ordini -> riconcilia -> scrive le righe. E' il
            # percorso in cui il 15/09 si sono rotte cinque cose, e senza
            # passare di qua non si certifica niente di quello.
            #
            # I controlli si agganciano a `engine.decide`, che viene chiamata
            # dentro: si intercetta li', cosi' si vede ogni decisione con il
            # `ctx` e lo `snap` veri costruiti dal servizio.
            ev = self.db.events.get(self.event_id) or {
                "event_id": self.event_id, "event_name": self.nome,
                "state": "WATCH", "mode": "live", "ctx": {},
            }
            self.db.upsert_event(ev)
            self.db.scan_rows = [dict(row, event_id=self.event_id, sport="calcio")]
            try:
                azioni, _settled = S._run_event(
                    db=self.db, market=self.mercato, ev=self.db.events[self.event_id],
                    row=dict(row, event_id=self.event_id),
                    params=self.params, mode="live",
                    now=datetime.fromtimestamp(now, tz=timezone.utc),
                    scanner_age=0.0, atlas=None, dry=False)
            except Exception as ex:  # noqa: BLE001 — un'eccezione del servizio E' un referto
                self.referto.violazioni.append(CERT.Violazione(
                    "SERVIZIO", "il giro del servizio non deve mai sollevare",
                    f"{type(ex).__name__}: {ex}",
                    str(self.db.events[self.event_id].get("state") or ""),
                    snap.minute, snap.goals))
                return
            self.referto.azioni += int(azioni or 0)
            stato = str(self.db.events[self.event_id].get("state") or "")
            if stato and stato not in self._stati:
                self._stati.append(stato)
            return

            if self.ctx.state not in self._stati:
                self._stati.append(self.ctx.state)

        # ------------------------------------------------- ordini VERI flumine
        def _piazza(self, leg: E.Leg, info: F.EventInfo) -> None:
            """Una gamba di Mike diventa un ordine flumine vero.

            Il `customer_order_ref` e' quello di Mike (`mike-t<n>`): e' la chiave
            con cui il bot ritrova i suoi ordini, ed e' la stessa che il 15/09
            ha prodotto il loop quando veniva scritta in un modo e letta in un
            altro. Qui la si mette sull'ordine vero e la si rilegge da li'.
            """
            mid = info.market_id(leg.market)
            sid = info.selection_id(leg.market, leg.selection)
            mercato = self.mercati.get(str(mid)) if mid else None
            if mercato is None or sid is None:
                self.senza_ordine.append(leg.ref)
                return
            try:
                trade = Trade(market_id=str(mid), selection_id=int(sid),
                              handicap=0.0, strategy=self)
                ordine = trade.create_order(
                    side="BACK" if leg.side == "back" else "LAY",
                    order_type=LimitOrder(price=float(leg.price),
                                          size=round(float(leg.size), 2),
                                          persistence_type=str(leg.persistence or "LAPSE")),
                )
                # `customer_order_ref` in flumine e' derivato e in sola lettura
                # (`name_hash + sep + id`): e' gia' unico per ordine ed e' quello
                # che Betfair riceverebbe. Il legame gamba<->ordine lo tiene la
                # mappa `self.ordini`, ed e' proprio quel legame che il 15/09
                # si era rotto in produzione.
                mercato.place_order(ordine)
            except Exception as ex:  # noqa: BLE001 — un place rifiutato E' un referto
                self.referto.violazioni.append(CERT.Violazione(
                    "ORDINE", "ogni gamba deve poter diventare un ordine reale",
                    f"{leg.ref}: {type(ex).__name__}: {ex}", self.ctx.state))
                self.senza_ordine.append(leg.ref)
                return
            self.ordini[leg.ref] = ordine

        def _rileggi_ordini(self) -> None:
            """Lo stato delle gambe viene DAGLI ORDINI, come in produzione.

            `size_matched` / `average_price_matched` / `status` li calcola il
            matching di flumine sulla coda vera; qui si ricopiano sulla gamba
            con la stessa semantica del contratto di `Leg`: 'pending' finche'
            l'ordine e' vivo, 'open' quando non lo e' piu' con qualcosa
            abbinato, 'cancelled' se non ha mai preso niente.
            """
            for leg in self.ctx.legs:
                ordine = self.ordini.get(leg.ref)
                if ordine is None or leg.archived:
                    continue
                sim = getattr(ordine, "simulated", None)
                abbinato = float(getattr(sim, "size_matched", 0.0) or 0.0)
                prezzo = getattr(sim, "average_price_matched", None)
                leg.matched = round(abbinato, 2)
                if prezzo:
                    leg.avg_price = float(prezzo)
                stato = str(getattr(ordine, "status", "") or "")
                vivo = stato in ("Pending", "Executable", "EXECUTABLE")
                if leg.status in ("pending", "pending_reconcile"):
                    if not vivo:
                        leg.status = "open" if leg.matched > 0 else "cancelled"

        def _score_at(self, pt_ms: int) -> Tuple[int, int, Optional[int]]:
            if not self._scores:
                return 0, 0, None
            i = bisect_right(self._score_ts, int(pt_ms)) - 1
            if i < 0:
                return 0, 0, None
            _, minuto, gc, gf = self._scores[i]
            return int(gc), int(gf), (int(minuto) if minuto is not None else None)

        def chiudi(self) -> CERT.Referto:
            self.referto.stati_visti = list(self._stati)
            return self.referto

    return MikeCert


# ---------------------------------------------------------------------------
# un evento
# ---------------------------------------------------------------------------
def certifica_evento(event_id: str, *, data_dir: str,
                     params: Optional[Dict[str, Any]] = None,
                     ogni_ms: int = 1000,
                     invecchia_s: float = 0.0,
                     guasti: int = 0) -> CERT.Referto:
    """Fa rivivere a Mike una partita registrata e ritorna il referto."""
    import flumine.config
    flumine.config.simulated = True
    from flumine import FlumineSimulation, clients
    from flumine.markets.middleware import SimulatedMiddleware

    from ...stream.backtest.run_backtest import _load_scores

    par = dict(params or C.merge_params(None))
    raw = os.path.join(data_dir, str(event_id), f"{event_id}.raw.jsonl")
    ref = CERT.Referto(event_id=str(event_id))
    if not os.path.exists(raw):
        ref.note.append(f"registrazione assente: {raw}")
        return ref

    try:
        scores = _load_scores(data_dir, str(event_id))
    except Exception as ex:  # noqa: BLE001 — senza punteggio si replica lo stesso
        scores = []
        ref.note.append(f"punteggi non letti ({type(ex).__name__}): minuti e gol assenti")

    Strategia = _crea_strategia()

    # I CONTROLLI SI AGGANCIANO A `engine.decide`.
    # `decide` ora viene chiamata DENTRO `service._run_event`, quindi da fuori
    # non si vede piu': la si avvolge. Il `ctx` e lo `snap` che arrivano qui
    # sono quelli VERI costruiti dal servizio, non una ricostruzione — ed e' il
    # punto: si certifica cio' che il bot decide davvero, coi dati che ha
    # davvero.
    referti_vivi: List[CERT.Referto] = []
    decide_vero = E.decide

    def decide_sorvegliata(ctx, snap, params):
        d = decide_vero(ctx, snap, params)
        if referti_vivi:
            r = referti_vivi[0]
            r.violazioni.extend(CERT.verifica(ctx, snap, d, params, r.sollecitati))
            # il COMPORTAMENTO nel tempo: i difetti di progettazione non si
            # vedono in un istante, si vedono nella ripetizione
            CERT.osserva(r.andamento, ctx, d)
            r.decisioni += 1
            motivo = str(getattr(d, "reason", "") or "-")[:90]
            r.motivi[motivo] = r.motivi.get(motivo, 0) + 1
        return d

    # I tetti di flumine vanno APERTI: qui il rischio lo governa Mike coi suoi
    # parametri (`max_liability_per_match`, tetto partite, stop giornaliero) ed
    # e' proprio quello che si vuole misurare. Lasciare i default di flumine
    # (1 trade vivo per selezione, 10 EUR per ordine) vorrebbe dire certificare
    # i limiti di flumine invece di quelli del bot: gli ordini verrebbero
    # rifiutati da fuori e il referto direbbe che Mike non fa niente.
    strategia = Strategia(event_id=str(event_id), params=par, scores=scores,
                          ogni_ms=ogni_ms, invecchia_s=invecchia_s,
                          market_filter={"markets": [raw]},
                          max_order_exposure=1e9, max_selection_exposure=1e9,
                          max_trade_count=int(1e9), max_live_trade_count=int(1e9))
    if guasti > 0:
        # i primi N piazzamenti falliranno con esito IGNOTO: e' cosi' che
        # nascono le gambe `pending_reconcile` che altrimenti non si vedono mai
        strategia.mercato.guasti["place_exception"] = int(guasti)
    referti_vivi.append(strategia.referto)
    quadro = FlumineSimulation(client=clients.SimulatedClient())
    quadro.add_market_middleware(SimulatedMiddleware())
    quadro.add_strategy(strategia)
    E.decide = decide_sorvegliata          # type: ignore[assignment]
    try:
        quadro.run()
    finally:
        E.decide = decide_vero             # type: ignore[assignment]

    out = strategia.chiudi()
    if strategia.db.mancanti:
        out.note.append("metodi di database chiamati dal servizio e assenti dal banco: "
                        f"{sorted(strategia.db.mancanti)}")
    if strategia.mercato.rifiutati:
        out.note.append(f"ordini rifiutati: {len(strategia.mercato.rifiutati)} "
                        f"(es. {strategia.mercato.rifiutati[0].get('err')})")
    out.ordini_piazzati = len(strategia.mercato.ordini)
    out.righe_scritte = len(strategia.db.trades)
    out.note.append(f"ordini reali piazzati: {out.ordini_piazzati} | "
                    f"righe mike_trades scritte: {out.righe_scritte}")
    # la diagnosi: che cosa ha scritto il servizio, e come sono finite le gambe
    from collections import Counter
    kinds = Counter(strategia.db.kinds())
    out.note.append("attivita' del servizio: "
                    + ", ".join(f"{k} x{n}" for k, n in kinds.most_common(8)))
    stati_righe = Counter(str(r.get("status")) for r in strategia.db.trades)
    out.note.append(f"righe per stato: {dict(stati_righe)}")
    motivi_err = Counter(str((p or {}).get("reason") or (p or {}).get("note") or "")[:60]
                         for k, p, _e in strategia.db.attivita
                         if k in ("error", "reconcile_pending", "skip", "no_fill"))
    if motivi_err:
        out.note.append("motivi dichiarati: "
                        + " | ".join(f"{m} x{n}" for m, n in motivi_err.most_common(5)))
    # il verdetto sul comportamento, che vale piu' di ogni singola decisione
    out.violazioni.extend(CERT.difetti_di_progettazione(
        out.andamento, ordini_piazzati=out.ordini_piazzati,
        righe_scritte=out.righe_scritte))
    if not scores:
        out.note.append("senza sidecar `.scores.jsonl`: minuto e gol sono 0-0/None, "
                        "quindi le regole che dipendono dal punteggio non sono state "
                        "messe alla prova")
    return out


# ---------------------------------------------------------------------------
# tutte
# ---------------------------------------------------------------------------
def eventi_disponibili(data_dir: str) -> List[str]:
    out: List[str] = []
    if not os.path.isdir(data_dir):
        return out
    for nome in sorted(os.listdir(data_dir)):
        if nome.startswith("_"):
            continue                       # `_synth_*`: registrazioni sintetiche
        if os.path.exists(os.path.join(data_dir, nome, f"{nome}.raw.jsonl")):
            out.append(nome)
    return out


def _complete(data_dir: str, eventi: List[str]) -> Dict[str, str]:
    """Verdetto di `validate_recordings` per ogni evento: una registrazione
    monca fa mentire il replay, e il referto lo deve dichiarare."""
    try:
        from ...stream.tools.validate_recordings import validate_all
        esiti = validate_all(eventi, data_dir=data_dir)
    except Exception as ex:  # noqa: BLE001 — il verdetto e' un di piu', non un gate
        logger.debug("validate_recordings non disponibile: %s", ex)
        return {}
    out: Dict[str, str] = {}
    for e in esiti or []:
        if isinstance(e, dict):
            out[str(e.get("event_id"))] = str(e.get("verdict") or e.get("status") or "?")
    return out


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Mike sulle registrazioni vere")
    p.add_argument("eventi", nargs="*", help="event_id (vuoto = tutti)")
    p.add_argument("--data-dir", default=None)
    p.add_argument("--ogni-ms", type=int, default=1000,
                   help="cadenza di decisione, come il ciclo reale (default 1000)")
    p.add_argument("--complete", action="store_true",
                   help="solo le registrazioni giudicate COMPLETE")
    p.add_argument("--json", dest="come_json", action="store_true")
    p.add_argument("--scenari", default="base",
                   help="elenco separato da virgole, oppure 'tutti': "
                        + ", ".join(list(SCENARI) + [SCENARIO_FEED_STANTIO,
                                                     SCENARIO_ESITI_IGNOTI]))
    p.add_argument("--diario", default=None,
                   help="file in cui scrivere il referto DOPO OGNI partita: senza, "
                        "un run lungo resta cieco fino alla fine")
    a = p.parse_args(argv)

    logging.basicConfig(level=logging.WARNING)
    from ...stream.config_stream import DATA_DIR
    data_dir = a.data_dir or DATA_DIR
    eventi = a.eventi or eventi_disponibili(data_dir)
    verdetti = _complete(data_dir, eventi)
    if a.complete and verdetti:
        eventi = [e for e in eventi if verdetti.get(e) == "COMPLETE"]

    print(f"REGISTRAZIONI: {len(eventi)} | controlli attivi: {len(CERT.elenco_controlli())}")
    sollecitati_tot: Dict[str, int] = {}
    print()
    scelti = (list(SCENARI) + [SCENARIO_FEED_STANTIO, SCENARIO_ESITI_IGNOTI]
              if a.scenari.strip().lower() == "tutti"
              else [x.strip() for x in a.scenari.split(",") if x.strip()])
    for sc in scelti:
        if sc not in SCENARI and sc not in (SCENARIO_FEED_STANTIO,
                                            SCENARIO_ESITI_IGNOTI):
            print(f"scenario sconosciuto: {sc}")
            return 2
    coppie = [(ev, sc) for sc in scelti for ev in eventi]
    if len(scelti) > 1:
        print(f"SCENARI: {', '.join(scelti)}")
        print()

    referti: List[CERT.Referto] = []
    for ev, sc in coppie:
        par = dict(C.merge_params(None))
        par.update(SCENARI.get(sc, {}))
        # il feed stantio si ottiene invecchiando la riga, non toccando i prezzi
        # perche' il feed risulti STANTIO devono essere vecchi TUTTI E DUE: la
        # riga (`feed_max_age_s`) e lo scanner (`scanner_alive_max_s`). Con lo
        # scanner vivo una riga ferma e' legittima — e' write-on-change, vuol
        # dire che i prezzi non sono cambiati.
        vecchio = (max(float(par.get("feed_max_age_s") or 15.0),
                       float(par.get("scanner_alive_max_s") or 75.0)) * 3.0
                   if sc == SCENARIO_FEED_STANTIO else 0.0)
        try:
            r = certifica_evento(ev, data_dir=data_dir, ogni_ms=a.ogni_ms,
                                 params=par, invecchia_s=vecchio,
                                 guasti=(QUANTI_GUASTI
                                         if sc == SCENARIO_ESITI_IGNOTI else 0))
        except Exception as ex:  # noqa: BLE001
            r = CERT.Referto(event_id=ev)
            r.note.append(f"replay fallito: {type(ex).__name__}: {ex}")
        if len(scelti) > 1:
            r.event_id = f"{ev} [{sc}]"
        referti.append(r)
        for cod, n in r.sollecitati.items():
            sollecitati_tot[cod] = sollecitati_tot.get(cod, 0) + n
        if a.diario:
            # si scrive SUBITO, partita per partita: un run da ore che non
            # dice niente finche' non finisce non e' osservabile, e un lavoro
            # non osservabile non si sa nemmeno se sta andando bene.
            with io.open(a.diario, "a", encoding="utf-8") as f:
                f.write(f"{'OK' if r.pulita else 'KO'} {ev} tick={r.tick} "
                        f"decisioni={r.decisioni} azioni={r.azioni} "
                        f"ordini={r.ordini_piazzati} stati={','.join(r.stati_visti)}" + chr(10))
                for v in r.violazioni[:6]:
                    f.write(f"    {v.codice}: {v.dettaglio}" + chr(10))
                f.flush()
        segno = "OK " if r.pulita else "KO "
        print(f"{segno} {r.event_id}  tick={r.tick:>6} decisioni={r.decisioni:>5} "
              f"azioni={r.azioni:>4} stati={','.join(r.stati_visti) or '-'} "
              f"[{verdetti.get(ev, '?')}]")
        for nota in r.note:
            print(f"      nota: {nota}")
        for motivo, n in sorted(r.motivi.items(), key=lambda x: -x[1])[:6]:
            print(f"      motivo x{n}: {motivo}")
        for cod, n in sorted(r.per_codice().items()):
            esempio = next(v for v in r.violazioni if v.codice == cod)
            print(f"      {cod} x{n}: {esempio.regola}")
            print(f"           es. {esempio.dettaglio}")

    print()
    tot = sum(len(r.violazioni) for r in referti)
    pulite = sum(1 for r in referti if r.pulita and r.decisioni > 0)
    mute = sum(1 for r in referti if r.decisioni == 0)
    print(f"ESITO: {pulite} partite senza violazioni, "
          f"{len(referti) - pulite - mute} con violazioni, {mute} senza decisioni")
    print(f"       {tot} violazioni totali")
    print()
    print("COPERTURA DEI CONTROLLI — quante volte ognuno ha avuto un caso:")
    for cod, reg in CERT.elenco_controlli():
        n = sollecitati_tot.get(cod, 0)
        segno = "  " if n else "??"
        print(f"  {segno} {cod:3} x{n:<7} {reg[:66]}")
    mai = CERT.mai_sollecitati(sollecitati_tot)
    if mai:
        print()
        print(f"?? MAI SOLLECITATI: {len(mai)} controlli su {len(CERT.elenco_controlli())}. "
              f"Su questi il referto NON dice «sano», dice «non lo so»:")
        for cod, reg in mai:
            print(f"     {cod}: {reg}")
    if a.come_json:
        print(json.dumps([{
            "event_id": r.event_id, "tick": r.tick, "decisioni": r.decisioni,
            "azioni": r.azioni, "stati": r.stati_visti, "note": r.note,
            "violazioni": [v.__dict__ for v in r.violazioni],
        } for r in referti], indent=1, default=str))
    return 0 if tot == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
