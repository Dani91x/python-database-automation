"""IL BANCO COMUNE — la catena di produzione, ricostruita su una registrazione.

Un solo banco per TUTTI i bot (Mike, Omega, Safe calcio, Safe tennis). La catena
e' quella vera, nello stesso ordine in cui gira in produzione:

    raw registrato        `_live_raw/<id>/<id>.raw.jsonl` (stream NATIVO Betfair)
      -> flumine          `FlumineSimulation` + `HistoricalStream` (motore ufficiale)
      -> MarketBook       oggetti `betfairlightweight` (gli stessi che il listener
                          dello stream produce in produzione)
      -> SCANNER VERO     `safe_strategy.service.Scanner._apply_market_book`, cioe'
                          ESATTAMENTE la funzione con cui lo scanner applica i book
                          dello stream e del REST
      -> `build_rows`     la funzione vera che scrive `safe_strategy_scan`
      -> tabella          le righe restano in memoria come nella tabella, con lo
                          stesso write-on-change e lo stesso throttle
      -> feed vero        del bot (es. `Betfair/mike/feed.py`)
      -> servizio vero    (`_run_event` / `run_once`)
      -> ordini VERI      su flumine, matching e coda di flumine

I PUNTEGGI non stanno nel file di mercato: arrivano dal sidecar della
registrazione (`<id>.scores.jsonl` calcio, `<id>.score.jsonl` tennis), che
contiene il RECORD IPS GREZZO, e vengono iniettati con
`Scanner.apply_score_state` — la stessa identica funzione che usa `poll_scores`.
Nessuna chiave ricostruita a mano: e' il record vero che passa dal parser vero.

IL RITARDO DEI PUNTEGGI E' GIA' NEL DATO, e va capito prima di "aggiungerlo".
`Betfair/stream/runner.py:349-355` scrive nel sidecar `ts_ms = snap.ts`, cioe'
il momento in cui il runner ha RICEVUTO lo stato dall'IPS — non il momento del
gol. Dentro quel numero ci sono gia' sia il ritardo dell'IPS (2-3 s dopo il gol,
memoria del 09/09) sia il giro di poll di chi lo ha catturato. Iniettare il
record quando il publish time del tick raggiunge `ts_ms` riproduce quindi il
ritardo VERO: sommargliene un altro a caso lo raddoppierebbe. `ritardo_punteggi_s`
esiste per chi volesse modellare un ritardo IN PIU' (per esempio il periodo di
poll dello scanner, `service._SCORES_PERIOD_SEC`), e va dichiarato nel referto
quando si usa; il default e' 0 per la ragione appena detta.

L'OROLOGIO dello scanner e' il `publish_time` del tick, non quello del PC
(`Scanner(orologio=...)`): con l'ora del PC una registrazione di giugno
nascerebbe gia' stantia e nessuna riga sarebbe fresca.

Il `pre_ko` si congela da solo al primo tick in-play: lo fa `freeze_pre_ko`
dentro `_apply_market_book`, come in produzione — qui non c'e' nessun codice che
lo congeli al posto suo.

-----------------------------------------------------------------------------
LIMITI DICHIARATI (un banco che non li dichiara e' peggio di nessun banco)
-----------------------------------------------------------------------------

1. IL CATALOGO NON C'E'. In produzione `listMarketCatalogue` da' nomi dei runner,
   nome dell'evento e competizione. Nel raw dello stream ci sono solo
   `id` + `sortPriority`. Il banco ricostruisce il catalogo dai
   `marketDefinition` + dai nomi delle squadre/giocatori del sidecar punteggi,
   e SINTETIZZA i nomi dei runner con la convenzione Betfair gia' usata dal
   Backtest Automatico (`sim_strategy._synth_name`): MATCH_ODDS 1/2/3 =
   casa/trasferta/The Draw, OVER_UNDER 1/2 = Under/Over, BTTS 1/2 = Yes/No.
   `competition` resta None.
   CORRECT_SCORE e HALF_TIME_SCORE NON hanno nomi sintetizzabili (le scoreline
   non sono deducibili dal sort priority): senza un fornitore esterno
   (`nomi_extra`) quei blocchi escono con `name` vuoto. Chi certifica Omega
   deve dichiararlo o portare i nomi.

2. NESSUN TETTO DI SCANNER. Il tetto dei 20 eventi con mercati a gol
   (`scanner.OPP_MAX_EVENTS`) e il cap del pool stream (180 mercati per
   connessione) non mordono: il banco replica UN evento per volta e tutti i suoi
   mercati sono presenti. Una certificazione che volesse misurare le linee che
   restano FUORI dal feed non puo' usare questo banco cosi' com'e'.

3. MINIMO DI GIURISDIZIONE (.it: BACK 2,00 / LAY 0,50) NON esiste su flumine:
   `place_submin_live` piazza diretto. Il place-and-trim e il rifiuto
   `INVALID_PROFIT_RATIO` NON vengono riprodotti. L'ANNULLO invece si':
   `cancel_order_live` passa dal cancel simulato di flumine e restituisce il
   `CancelResult` vero di `omega_market`.

4. BET DELAY IN-PLAY: RIPRODOTTO (non e' piu' un limite). Un ordine piazzato a
   `t` viene valutato da flumine sul book di `t + place_latency + betDelay`,
   perche' il banco fa scorrere il TEMPO DI MERCATO durante il piazzamento
   invece di forzare l'esecuzione (`MotoreReplay.attendi_esecuzione`). E' il
   comportamento vero: su un mercato in gioco Betfair trattiene l'ordine e
   risponde alla REST solo dopo. Resta un solo caso dichiarato: se la
   registrazione FINISCE prima che il ritardo sia trascorso, non esiste un book
   futuro e l'ordine viene valutato sull'ultimo noto (contato in
   `MotoreReplay.senza_futuro`).

5. STOP GIORNALIERO E TETTO PARTITE vivono in `run_once` (il giro su TUTTE le
   partite) e qui non mordono: il banco chiama il giro del servizio su UN evento.
   Un banco che li volesse misurare deve passare da `run_once` con piu' eventi.

6-bis. GLI ORDINI APPOGGIATI MUOIONO QUANDO BETFAIR LI UCCIDE.
   Regola Betfair: un ordine NON abbinato con `persistenceType=LAPSE` viene
   cancellato quando il mercato si SOSPENDE in gioco e quando il mercato PASSA
   IN GIOCO. Nel banco:
     * SOSPENSIONE: la fa gia' flumine
       (`simulation/simulatedorder.py:57-62`: al cambio di `market_book.version`
       con `status == "SUSPENDED"`, `size_lapsed += size_remaining`).
       VERIFICATO nel replay (35833626): la lay appoggiata passa da EXECUTABLE /
       residuo 2,00 a EXECUTION_COMPLETE / `size_lapsed` 2,00, sparisce da
       `list_current_orders` e compare in `list_cleared_orders`;
     * PASSAGGIO IN GIOCO: flumine NON lo fa, e serve. MISURATO sulle
       registrazioni (35674515, 35760084, 35777617, tutti i mercati MATCH_ODDS e
       O/U): la sequenza vera e' `(OPEN, inPlay=False)` -> **`(OPEN,
       inPlay=True)`** -> `(SUSPENDED, inPlay=True)`. C'e' quindi un tick in cui
       il mercato e' GIA' in gioco e ANCORA aperto: li' flumine terrebbe vivo un
       ordine che su Betfair e' gia' morto, e glielo farebbe abbinare ai prezzi
       del fischio — un fill che in live non sarebbe mai esistito. Lo chiude
       `MotoreReplay._lapse_al_fischio`, PRIMA del middleware che abbina.
     * SOSPENSIONE IN GIOCO (gol, rigore, rosso): flumine la copre SOLO se
       `market_book.version` cambia (`simulatedorder.py:57-62`), e l'uscita
       appoggiata di Mike nasce DOPO il fischio, quindi `_lapse_al_fischio` non
       la vede mai: senza una regola sua, quella lay sopravviverebbe al gol e si
       abbinerebbe ai prezzi della riapertura. La chiude
       `MotoreReplay._lapse_alla_sospensione`, a OGNI transizione verso
       `SUSPENDED` con `inPlay=True`, sempre PRIMA del middleware.
   Gli ordini `PERSIST` sopravvivono, come su Betfair.
   FONTE (letta il 16/09/2026; le due pagine di supporto Betfair rispondono 403
   a un recupero automatico, quindi si riporta cio' che si e' letto e da dove):
     * guida alle persistenze di Wagertool
       (`wagertool.com/support/user-guide/bet-persistence-types`): con la
       persistenza LAPSE «l'ordine non abbinato viene cancellato se il mercato
       si sospende — quando va in gioco o quando si sospende per un motivo
       qualsiasi, per esempio un gol»;
     * Betfair support, risposta 415 («Keep bet» e «Take SP»): quando in una
       partita di calcio capita un evento (gol, rigore, rosso) «gli altri
       ordini non abbinati vengono cancellati prima che il mercato riapra»,
       mentre un `keep` (PERSIST) no.
   Verificato di persona nel replay: il comportamento di flumine alla
   sospensione con cambio di versione e la sequenza degli stati nelle
   registrazioni.

6-ter. IL TEMPO DELLE CHIAMATE, E COSA SI PUO' CONFRONTARE.
   Una chiamata BLOCCANTE consuma tempo di mercato: `place_order_live` e' una
   REST SINCRONA e su un mercato in gioco Betfair la trattiene per il bet delay
   (misura vera del repo: `HANDOFF_CONTROL_ROOM.md` §4.2, «3,3 s di Betfair» su
   `t4_inviato -> t5_risposta`; la doc Betfair dice che solo il piazzamento
   ASINCRONO torna subito «senza il ritardo in gioco»). Il banco fa scorrere
   ESATTAMENTE `place_latency + betDelay` (e `cancel_latency` per un annullo),
   non «finche' flumine esegue» — vedi `MotoreReplay.attendi_esecuzione`. La
   cadenza del bot riparte da quando il giro e' FINITO, come in produzione.
   Ne segue una regola di lettura, e va detta ad alta voce:
     **i numeri di scenari diversi sono confrontabili solo dove la sequenza di
     chiamate e' identica fino al punto confrontato.**
   Due scenari che prima dell'ingresso fanno le stesse chiamate devono avere
   l'ingresso identico (test `test_banco_identita_2026_09_16.py`); due scenari
   che ne fanno di diverse — per esempio uno con la posizione DICHIARATA dal
   replay e uno in cui il bot la apre da se' — arrivano al mercato in istanti
   diversi e chiedono prezzi diversi: non e' un difetto, e confrontarne le quote
   non vuol dire niente.

6. NESSUN ERRORE DI RETE. Gli stati di riconciliazione da esito IGNOTO non
   capitano da soli: si provocano con `MercatoFlumine.guasti["place_exception"]`.

7. PAPER E LIVE NON SONO ANCORA CONFRONTATI. Il replay gira nella modalita' che
   gli passa il chiamante (Mike: `mode="live"`, cioe' il percorso degli ordini
   veri). La parita' campo per campo fra la richiesta che manderebbe il paper e
   quella del live (PROCESSO_STANDARD_BOT §6.3) non e' fatta qui: e' un lavoro a
   se', da fare sullo stesso banco.

8. SETTLEMENT DAL FEED, NON DAL BOOK CHIUSO. `MercatoFlumine.read_book` torna
   None: a mercato chiuso il servizio ripiega sull'ultimo punteggio noto del
   feed (`settle_fallback`). Il ramo `process_closed_market` di flumine (che
   porterebbe i `runner_status` veri, quindi il void per mercato e la
   commissione calcolata sul risultato) NON e' agganciato.

9. IL DATABASE IN MEMORIA NON HA I VINCOLI DEL VERO. `DbMemoria` ha le firme e i
   tipi di ritorno di `Betfair/mike/db.py`, ma non i `CHECK` delle migrazioni:
   uno stato che il vincolo del DB rifiuterebbe qui passa. E' il difetto 18 del
   catalogo, e questo banco non lo prende.

10. UN FILE RAW PER VOLTA. `MotoreReplay.esegui` riproduce il ramo "singolo
   stream" di `FlumineSimulation.run` (`simulation.py:86-100`), non quello
   `event_processing` che multiplexa piu' stream in ordine cronologico
   (`simulation.py:50-84`). Per le registrazioni di questo repo — un file per
   evento, con dentro tutti i suoi mercati — e' lo stesso ramo che usa il
   Backtest Automatico.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import json
import logging
import os
from bisect import bisect_right
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import (TYPE_CHECKING, Any, Callable, Deque, Dict, List, Optional,
                    Sequence, Tuple)

from ...safe_strategy import scanner as SCAN
from .sim_strategy import _offer_price, _offer_size, _synth_name

# `omega_market` e lo `Scanner` si importano PIGRAMENTE: portano dentro il
# client Supabase e l'autenticazione Betfair, e questo modulo deve poter essere
# importato anche da chi vuole solo l'helper del middleware (`run_backtest`).
if TYPE_CHECKING:  # pragma: no cover - solo per i tipi
    from ...omega.omega_market import CancelResult, PlaceResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# il database, in memoria
# ---------------------------------------------------------------------------
class DbMemoria:
    """Le tabelle di un bot in RAM, con le firme di `Betfair/mike/db.py`.

    Stessa firma e stessi TIPI DI RITORNO del vero: `insert_trade` torna l'ID
    (`Optional[int]`), non la riga. Un doppio che risponde a domande a cui il
    vero non risponde e' la causa di tutti i difetti del 15/09.
    """

    def __init__(self, control: Dict[str, Any]) -> None:
        self.control = dict(control)
        self.trades: List[Dict[str, Any]] = []
        self.events: Dict[str, Dict[str, Any]] = {}
        self.attivita: List[tuple] = []
        self.scan_rows: List[Dict[str, Any]] = []
        self._id = 0
        # i metodi che il servizio ha chiamato e che qui non esistono: si
        # dichiarano nel referto invece di essere ingoiati in silenzio.
        self.mancanti: List[str] = []
        # dati che in PRODUZIONE arrivano da una tabella/RPC che la
        # registrazione NON contiene: qui il metodo c'e' e risponde col TIPO
        # vero, ma il contenuto e' vuoto. Si dichiara nel referto (limite
        # "non esercitabile", PROCESSO_STANDARD_BOT §6.8), non si tace.
        self.senza_dato: List[Tuple[str, str]] = []

    # --- control ---
    def read_control(self) -> Dict[str, Any]:
        return dict(self.control)

    def set_control(self, **campi: Any) -> None:
        self.control.update(campi)

    # --- eventi ---
    def list_events(self, states: Optional[List[str]] = None,
                    since_iso: Optional[str] = None) -> List[Dict[str, Any]]:
        righe = list(self.events.values())
        if states:
            righe = [r for r in righe if str(r.get("state")) in set(states)]
        return righe

    def upsert_event(self, row: Dict[str, Any]) -> None:
        eid = str(row.get("event_id"))
        base = dict(self.events.get(eid) or {})
        base.update(row)
        self.events[eid] = base

    def upsert_events(self, rows: List[Dict[str, Any]]) -> None:
        for r in rows or []:
            self.upsert_event(r)

    # --- trades ---
    def insert_trade(self, trade: Dict[str, Any]) -> Optional[int]:
        # il vero torna l'ID, non la riga: qui uguale.
        self._id += 1
        self.trades.append({**trade, "id": self._id})
        return self._id

    def update_trade(self, trade_id: int, **campi: Any) -> None:
        for r in self.trades:
            if int(r.get("id") or 0) == int(trade_id):
                r.update(campi)
                return

    def trades_for_event(self, event_id: str, **_kw: Any) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.trades if str(r.get("event_id")) == str(event_id)]

    def open_trades(self, *_a: Any, **_k: Any) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.trades
                if str(r.get("status")) in ("open", "hedged", "pending")]

    # --- attivita' ---
    def log(self, kind: str, payload: Optional[Dict[str, Any]] = None,
            event_id: Optional[str] = None) -> None:
        self.attivita.append((str(kind), dict(payload or {}), event_id))

    def kinds(self) -> List[str]:
        return [k for k, _p, _e in self.attivita]

    # --- il resto del ciclo, che qui non ha niente da fare ---
    def fetch_scan_rows(self, *_a: Any, **_k: Any) -> List[Dict[str, Any]]:
        return list(self.scan_rows)

    def scanner_status(self, *_a: Any, **_k: Any) -> Optional[Dict[str, Any]]:
        return None

    def pending_requests(self, *_a: Any, **_k: Any) -> List[Dict[str, Any]]:
        return []

    def set_request_status(self, *_a: Any, **_k: Any) -> None:
        return None

    def fail_stale_processing(self, *_a: Any, **_k: Any) -> None:
        return None

    def aggregates(self, *_a: Any, **_k: Any) -> Dict[str, Any]:
        return {}

    # --- storico HT->FT: c'e' il metodo, non c'e' il dato -----------------
    def ht_ft_rows(self, league_id: Optional[int]) -> List[Dict[str, Any]]:
        """STESSA FIRMA E STESSO TIPO di `Betfair/mike/db.py::ht_ft_rows`.

        In produzione questa funzione chiama
        `Betfair/omega/omega_db.py::ht_ft_transitions`, cioe' la RPC Supabase
        `get_omega_ht_ft`, che restituisce righe `{league_id, ht, ft, n}`
        aggregate su MIGLIAIA di partite storiche. Il consumatore e'
        `Betfair/mike/dossier.py::get_empirical`, che ci costruisce sopra
        `EmpiricalTable`.

        Nel replay quel dato NON ESISTE: la registrazione e' UNA partita e
        contiene lo stream di mercato, non lo storico delle transizioni
        primo-tempo -> finale di una lega. Non e' ricavabile dalle righe di
        scan (che portano i prezzi e il punteggio di questo evento, non
        conteggi storici), e inventarlo vorrebbe dire far decidere il bot su
        numeri che in produzione non avrebbe.

        Quindi: lista VUOTA, che e' esattamente cio' che il vero restituisce
        quando la tabella e' vuota (`omega_db.ht_ft_transitions` -> `[]`), col
        tipo dichiarato dal vero (`list[dict]`, MAI `None`: `None` in
        produzione significa "errore RPC", ed e' un fatto diverso). Il limite
        si dichiara nel referto.
        """
        voce = ("ht_ft_rows", "storico HT->FT (RPC get_omega_ht_ft, migliaia di "
                              "partite): non e' nella registrazione di UNA partita, "
                              "quindi la tabella empirica del dossier resta assente")
        if voce not in self.senza_dato:
            self.senza_dato.append(voce)
        return []

    def __getattr__(self, nome: str):
        # un metodo che il servizio chiama e che qui manca NON deve passare
        # inosservato: si registra e si risponde None.
        if nome.startswith("_"):
            raise AttributeError(nome)

        def _ignoto(*_a: Any, **_k: Any):
            if nome not in self.mancanti:
                self.mancanti.append(nome)
            return None
        return _ignoto


# ---------------------------------------------------------------------------
# il ladder: farlo parlare la lingua della PRODUZIONE
# ---------------------------------------------------------------------------
class _Livello:
    """Un livello del ladder come lo vede la PRODUZIONE: `.price` e `.size`.

    ⚠️ IMPORTARE `flumine` RITOCCA `betfairlightweight` PER TUTTO IL PROCESSO
    (`flumine/__init__.py`: `bettingresources.RunnerBookEX = EX`), e la classe
    `EX` di flumine espone i livelli come `dict {'price','size'}` invece che
    come `PriceSize`. Lo scanner vero legge il prezzo con `levels[0].price`
    (`scanner.best_price`) dentro un `except Exception` che ritorna None: dargli
    i dict di flumine gli farebbe vedere TUTTI I PREZZI A None, in silenzio —
    lo stesso difetto che il 15/09 e' costato cinque incidenti.
    Qui il livello viene riletto con `_offer_price`/`_offer_size` (che sanno
    leggere dict, tupla e oggetto) e riesposto nella forma di produzione.
    """

    __slots__ = ("price", "size")

    def __init__(self, price: Optional[float], size: Optional[float]) -> None:
        self.price = price
        self.size = size

    def __repr__(self) -> str:  # pragma: no cover - diagnostica
        return f"<Livello {self.price}@{self.size}>"


class _VistaEx:
    """`runner.ex` con i tre ladder nella forma di produzione."""

    __slots__ = ("available_to_back", "available_to_lay", "traded_volume")

    def __init__(self, ex: Any) -> None:
        self.available_to_back = _livelli_di_produzione(
            getattr(ex, "available_to_back", None) if ex is not None else None)
        self.available_to_lay = _livelli_di_produzione(
            getattr(ex, "available_to_lay", None) if ex is not None else None)
        self.traded_volume = _livelli_di_produzione(
            getattr(ex, "traded_volume", None) if ex is not None else None)


class _VistaRunner:
    """Un runner del book, coi soli campi che lo scanner vero legge davvero."""

    __slots__ = ("selection_id", "status", "last_price_traded", "total_matched", "ex")

    def __init__(self, runner: Any) -> None:
        self.selection_id = getattr(runner, "selection_id", None)
        self.status = getattr(runner, "status", None)
        self.last_price_traded = getattr(runner, "last_price_traded", None)
        self.total_matched = getattr(runner, "total_matched", None)
        self.ex = _VistaEx(getattr(runner, "ex", None))


class _VistaBook:
    """Un `MarketBook` coi soli campi che lo scanner vero legge davvero.

    Sono esattamente quelli letti da `_apply_market_book`, `_apply_cs_book` e
    `_apply_opp_book`: `market_id`, `runners[].selection_id/.ex/.status/
    .last_price_traded`, `inplay`, `status`, `total_matched`, `bet_delay`.
    Il `market_definition` viaggia comunque, per chi ne avesse bisogno.
    """

    __slots__ = ("market_id", "runners", "inplay", "status", "total_matched",
                 "bet_delay", "market_definition", "publish_time")

    def __init__(self, market_book: Any) -> None:
        self.market_id = getattr(market_book, "market_id", None)
        self.runners = [_VistaRunner(r) for r in (getattr(market_book, "runners", None) or [])]
        self.inplay = bool(getattr(market_book, "inplay", False))
        self.status = getattr(market_book, "status", None)
        self.total_matched = getattr(market_book, "total_matched", None)
        self.bet_delay = getattr(market_book, "bet_delay", None)
        self.market_definition = getattr(market_book, "market_definition", None)
        self.publish_time = getattr(market_book, "publish_time", None)


def _livelli_di_produzione(livelli: Any) -> List[_Livello]:
    """Da qualunque forma (dict flumine, lista grezza, PriceSize) a `.price/.size`."""
    out: List[_Livello] = []
    for liv in livelli or []:
        out.append(_Livello(_offer_price(liv), _offer_size(liv)))
    return out


def libro_di_produzione(market_book: Any) -> _VistaBook:
    """Il book di flumine nella forma in cui lo scanner lo riceve in produzione."""
    return _VistaBook(market_book)


# ---------------------------------------------------------------------------
# il mercato: ordini VERI su flumine, matching di flumine
# ---------------------------------------------------------------------------
class MercatoFlumine:
    """`place_order_live` e compagnia, serviti dal matching di flumine.

    Il `customer_ref` che il servizio passa viene CONSERVATO e restituito in
    `customer_order_ref` da `list_current_orders`: e' la chiave con cui un bot
    ritrova i suoi ordini, ed e' esattamente quella che il 15/09 veniva scritta
    in un modo e letta in un altro. Qui il giro si chiude davvero.

    NESSUN FILL FATTO IN CASA, E NESSUNA FRETTA. In produzione
    `place_order_live` e' una REST SINCRONA e su un mercato in gioco Betfair
    TRATTIENE l'ordine per `betDelay` secondi prima di abbinarlo: la risposta
    che il bot legge e' gia' quella di dopo il ritardo. Flumine sa riprodurlo
    (`handler_queue` + `elapsed_seconds > simulated_delay`, cioe'
    `place_latency + bet_delay`), ma lo esegue al giro dopo. Qui il piazzamento
    ASPETTA: `MotoreReplay.attendi_esecuzione` fa scorrere il tempo di mercato
    finche' flumine non esegue il pacchetto, esattamente come il bot resta
    bloccato sulla REST. Da li' in poi decide tutto flumine:
      * `simulation/simulatedorder.py:140-176` (BACK) e `:186-227` (LAY) —
        abbinamento immediato contro il ladder corrente;
      * `:126-137` e `:151-175` — FILL_OR_KILL vero, con `minFillSize` che
        Betfair fa default alla size intera: la parte non abbinata subito viene
        uccisa (`size_cancelled`), non lasciata viva sul book;
      * `:230-236` — `_piq`, la coda gia' presente davanti a noi a quel prezzo;
      * `:457-496` — `_process_traded`, che consuma la coda col volume
        realmente scambiato nei tick successivi.
    """

    _avvisato_senza_motore = False

    def __init__(self, strategia: Any, motore: Optional["MotoreReplay"] = None) -> None:
        self.s = strategia
        # IL MOTORE del replay: serve ad ASPETTARE il bet delay come fa Betfair.
        # Senza (solo nei test unitari che non hanno uno stream da far scorrere)
        # il pacchetto viene eseguito subito e il ritardo NON e' riprodotto: lo
        # si dice ad alta voce, una volta.
        self.motore = motore
        # customer_ref -> ordine flumine
        self.ordini: Dict[str, Any] = {}
        # GLI ORDINI DELL'UTENTE, quelli che il bot NON ha piazzato. Stanno in
        # un cassetto a parte per la stessa ragione per cui in produzione stanno
        # fuori: ``omega_market.list_current_orders`` filtra per
        # ``customerStrategyRef``, quindi un ordine piazzato dall'utente (dal
        # sito, da un'altra app, da un altro bot) NON compare nella lista che il
        # bot legge. Compare invece nella POSIZIONE DI CONTO sul mercato, che e'
        # senza filtro: ed e' esattamente la differenza che il 16/09 ha reso
        # cieco Mike davanti a una chiusura fatta fuori dall'app.
        self.ordini_utente: Dict[str, Any] = {}
        self.rifiutati: List[Dict[str, Any]] = []
        # guasti da provocare apposta: {"place_exception": N} solleva sui
        # prossimi N piazzamenti, per far nascere gli stati di riconciliazione
        self.guasti: Dict[str, int] = {}
        # SU QUALE LATO cade il rifiuto provocato (None = il primo che capita).
        # Serve a colpire il ramo giusto: le aperture di Mike sono BACK e
        # passano da `execution.place`, le uscite appoggiate sono LAY e passano
        # da `_piazza_resting_live` — che e' dove il 15/09 `res.ok` non veniva
        # letto. Rifiutare "i primi tre ordini" colpirebbe solo le aperture e
        # il difetto 2 resterebbe senza un caso.
        self.rifiuta_lato: Optional[str] = None
        # 17/09 (reperto 25) — RIFIUTO PERSISTENTE, con il codice VERO di
        # Betfair. Con ``guasti["place_rifiuto"] == -1`` il rifiuto non si
        # consuma: e' il caso reale del 17/09, dove la copertura sotto minimo e'
        # stata rifiutata 171 volte su 171, sempre con lo stesso codice. Senza
        # un rifiuto che NON finisce, il banco non puo' sollecitare il freno.
        # ``rifiuta_market_id`` restringe il rifiuto a UN mercato (la copertura
        # vive sull'OU45: rifiutare tutto colpirebbe anche le uscite).
        self.rifiuta_market_id: Optional[str] = None
        # ``rifiuta_sotto_minimo``: rifiuta SOLO gli ordini sotto il minimo di
        # giurisdizione. E' il caso REALE del 17/09 alla lettera: l'ingresso da
        # 5 EUR passa, la copertura sotto minimo (1,21 EUR) no. Non serve
        # conoscere il market id della copertura per colpire solo lei.
        self.rifiuta_sotto_minimo: Optional[float] = None
        self.rifiuto_codice: str = "INVALID_ODDS"
        self.rifiuto_codice_interno: Optional[str] = None
        # quante LETTURE ha fatto il bot (ognuna costa `LATENZA_LETTURA_S` di
        # tempo di mercato): il referto lo dichiara, perche' l'assunzione pesa
        # in proporzione a questo numero
        self.letture: int = 0

    # ------------------------------------------------------------- place
    def place_order_live(self, *, market_id: str, selection_id: int, price: float,
                         size: float, event_id: str, side: str = "lay",
                         customer_ref: Optional[str] = None,
                         fill_or_kill: bool = True) -> PlaceResult:
        from flumine.order.ordertype import LimitOrder
        from flumine.order.trade import Trade

        from ...omega.omega_market import PlaceResult

        if self.guasti.get("place_exception", 0) > 0:
            self.guasti["place_exception"] -= 1
            raise RuntimeError("guasto provocato: esito IGNOTO dal place")
        _quanti = int(self.guasti.get("place_rifiuto", 0))
        if ((_quanti > 0 or _quanti == -1)
                and (self.rifiuta_lato is None
                     or str(side).lower() == str(self.rifiuta_lato).lower())
                and (self.rifiuta_market_id is None
                     or str(market_id) == str(self.rifiuta_market_id))
                and (self.rifiuta_sotto_minimo is None
                     or float(size) < float(self.rifiuta_sotto_minimo) - 1e-9)):
            # IL RIFIUTO DICHIARATO DI BETFAIR (`ok=False`): l'istruzione torna
            # con un report negativo e NESSUN ordine esiste. E' il difetto 2 del
            # catalogo del 15/09 («`res.ok` mai letto: un rifiuto trattato come
            # copertura esistente»), e senza provocarlo il replay non ha MAI un
            # caso in cui `ok` valga False — quindi non puo' accorgersi se
            # qualcuno smettesse di leggerlo. Le parole sono quelle di Betfair.
            if _quanti > 0:                       # -1 = rifiuto che non finisce
                self.guasti["place_rifiuto"] = _quanti - 1
            codice = str(self.rifiuto_codice)
            interno = self.rifiuto_codice_interno
            self.rifiutati.append({"ref": str(customer_ref or ""),
                                   "err": f"{codice} (rifiuto provocato)"})
            # Le parole e la FORMA sono quelle di Betfair: su un replace
            # rifiutato il codice esterno e' ``CANCELLED_NOT_PLACED`` e il
            # motivo vero sta in ``placeInstructionReport.errorCode``.
            grezzo: Dict[str, Any] = {"motivo": f"rifiuto provocato: {codice}",
                                      "error_code": codice}
            if interno:
                grezzo["instructionReports"] = [{
                    "status": "FAILURE", "errorCode": codice,
                    "cancelInstructionReport": {"status": "SUCCESS",
                                                "sizeCancelled": 0.0},
                    "placeInstructionReport": {"status": "FAILURE",
                                               "errorCode": str(interno)}}]
            return PlaceResult(ok=False, order_status="EXPIRED", bet_id=None,
                               size_matched=0.0, avg_price_matched=None,
                               raw=grezzo, error_code=codice)

        mercato = self.s.mercati.get(str(market_id))
        if mercato is None:
            return PlaceResult(ok=False, order_status="EXPIRED", bet_id=None,
                               size_matched=0.0, avg_price_matched=None,
                               raw={"motivo": "mercato non in replay"})
        ref = str(customer_ref or f"bot-{event_id}")[:32]
        trade = Trade(market_id=str(market_id), selection_id=int(selection_id),
                      handicap=0.0, strategy=self.s)
        ordine = trade.create_order(
            side="BACK" if str(side).lower() == "back" else "LAY",
            order_type=LimitOrder(
                price=float(price), size=round(float(size), 2),
                persistence_type="LAPSE",
                # LA STESSA ISTRUZIONE DELLA PRODUZIONE: `omega_market.
                # place_order_live` mette `timeInForce=FILL_OR_KILL` e NON manda
                # `minFillSize`. Flumine legge esattamente quella istruzione.
                time_in_force=("FILL_OR_KILL" if fill_or_kill else None),
            ),
        )
        # il ref del bot viaggia nelle note: `customer_order_ref` in flumine e'
        # derivato e in sola lettura, ma cio' che conta e' che il ref che il bot
        # ha CHIESTO torni indietro identico quando rilegge gli ordini.
        ordine.notes["bot_ref"] = ref
        try:
            accettato = mercato.place_order(ordine)
        except Exception as ex:  # noqa: BLE001 — rifiuto dichiarato, non eccezione
            self.rifiutati.append({"ref": ref, "err": str(ex)[:160]})
            return PlaceResult(ok=False, order_status="EXPIRED", bet_id=None,
                               size_matched=0.0, avg_price_matched=None,
                               raw={"motivo": str(ex)[:160]})
        if accettato is False:
            # ⚠️ UN ORDINE RIFIUTATO DAI CONTROLLI NON E' UN ORDINE.
            # `Transaction.place_order` torna False quando un controllo lo
            # ferma (`flumine/execution/transaction.py:70-75`): l'ordine non
            # esiste, nessun pacchetto viene accodato. Il banco di prima
            # ignorava il valore di ritorno e gli calcolava sopra un fill: il
            # referto raccontava abbinamenti di ordini mai nati.
            motivo = str(getattr(ordine, "violation_reason", "") or "controllo flumine")
            self.rifiutati.append({"ref": ref, "err": motivo[:160]})
            return PlaceResult(ok=False, order_status="EXPIRED", bet_id=None,
                               size_matched=0.0, avg_price_matched=None,
                               raw={"motivo": motivo[:160]})
        self.ordini[ref] = ordine
        self._attendi_betfair(mercato)

        abbinato = float(getattr(ordine, "size_matched", 0.0) or 0.0)
        medio = getattr(ordine, "average_price_matched", None) or None
        return PlaceResult(
            ok=True,
            # parole di Betfair, non enum flumine
            order_status=self._stato_betfair(ordine),
            bet_id=str(getattr(ordine, "bet_id", None) or getattr(ordine, "id", "")),
            size_matched=round(abbinato, 2),
            avg_price_matched=float(medio) if medio else None,
            raw={},
        )

    def _attendi_betfair(self, mercato: Any) -> None:
        """Aspetta che flumine esegua il pacchetto, come si aspetta Betfair.

        Col motore: il tempo di mercato scorre finche' `elapsed_seconds` supera
        `simulated_delay` (`place_latency` + `betDelay`) e flumine esegue da
        solo — l'ordine si abbina sul book di `t + delay`, non su quello di `t`.
        Senza motore (solo test unitari che non hanno uno stream): il pacchetto
        viene eseguito subito, quindi SENZA ritardo, e lo si dichiara.
        """
        if self.motore is not None:
            self.motore.attendi_esecuzione(str(getattr(mercato, "market_id", "")))
            self._chiudi_senza_residuo(mercato)
            return
        if not self._avvisato_senza_motore:
            MercatoFlumine._avvisato_senza_motore = True
            logger.warning("[banco] nessun motore: il bet delay NON e' riprodotto "
                           "(va bene solo nei test unitari senza stream)")
        quadro = getattr(mercato, "flumine", None)
        coda = getattr(quadro, "handler_queue", None)
        if coda is None:
            return
        mid = str(getattr(mercato, "market_id", ""))
        for pacco in list(coda):
            if str(getattr(pacco, "market_id", "")) != mid:
                continue
            pacco.client.execution.handler(pacco)
            try:
                coda.remove(pacco)
            except ValueError:  # pragma: no cover - gia' tolto
                pass
        self._chiudi_senza_residuo(mercato)

    @staticmethod
    def _chiudi_senza_residuo(mercato: Any) -> None:
        """`flumine._process_simulated_orders` (`simulation.py:158-172`): porta a
        EXECUTION_COMPLETE gli ordini senza residuo. Senza, un FILL_OR_KILL
        ucciso resterebbe "vivo" fino al tick dopo — una posizione fantasma
        nella lettura degli ordini."""
        quadro = getattr(mercato, "flumine", None)
        if quadro is not None:
            quadro._process_simulated_orders(mercato)

    # ------------------------------------------------------------- cancel
    def cancel_order_live(self, bet_id: str, market_id: str,
                          size_reduction: Optional[float] = None) -> CancelResult:
        """ANNULLA DAVVERO l'ordine, col cancel simulato di flumine.

        ⚠️ 16/09 (C.12a) — fino a stamattina nessuno dei tre bot annullava per
        davvero: gli "annulla" erano contabili. Adesso passano tutti da
        `execution.annulla_su_betfair` (`safe_strategy/execution.py:341`), che
        cerca proprio questo metodo sul mercato. Il banco non ce l'aveva: ogni
        annullo tornava `None` (= esito IGNOTO), la gamba finiva in
        riconciliazione e il freno anti-duplicato bloccava tutte le gambe
        successive con lo stesso ruolo. Fail-closed corretto in produzione,
        buco del banco qui (esito 6 della matrice ordini).

        Come lo fa flumine, riga per riga:
          * `Market.cancel_order` -> `Transaction.cancel_order`
            (`flumine/execution/transaction.py:104-122`): valida i controlli,
            chiama `order.cancel(size_reduction)` (stato CANCELLING) e accoda
            un pacchetto CANCEL;
          * l'attesa e' `config.cancel_latency` (0,170 s) e NON il bet delay
            (`orderpackage.py:74-79`): Betfair non trattiene un annullo. Qui la
            fa scorrere lo stesso motore del piazzamento;
          * `SimulatedExecution.execute_cancel` -> `order.simulated.cancel`
            (`simulation/simulatedorder.py:286-310`): a mercato non OPEN
            risponde FAILURE/`ERROR_IN_ORDER`; altrimenti annulla
            `min(size_reduction or size_remaining, size_remaining)` e aumenta
            `size_cancelled`.
        L'esito si RILEGGE dall'ordine, come fa `omega_market.cancel_order_live`
        con la risposta di Betfair: `ok` solo se qualcosa e' stato davvero
        annullato, `riletto=True` quando lo stato dell'ordine e' noto (cosi' chi
        chiama non manda in riconciliazione cio' che puo' vedere).
        """
        from ...omega.omega_market import CancelResult

        ordine = self._per_bet_id(bet_id)
        if ordine is None:
            # nessun ordine con quel bet_id: non si puo' dire com'e' andata.
            # `riletto=False` = "non lo so" -> il chiamante riconcilia.
            return CancelResult(ok=False, status="FAILURE", bet_id=str(bet_id),
                                size_cancelled=0.0, error_code="BET_NOT_FOUND",
                                riletto=False, raw={"motivo": "ordine non nel banco"})
        mercato = self.s.mercati.get(str(getattr(ordine, "market_id", "") or market_id))
        if mercato is None:
            return CancelResult(ok=False, status="FAILURE", bet_id=str(bet_id),
                                size_cancelled=0.0, error_code="BET_NOT_FOUND",
                                riletto=False, raw={"motivo": "mercato non in replay"})
        prima = self._numeri(ordine)
        try:
            accettato = mercato.cancel_order(ordine, size_reduction)
        except Exception as ex:  # noqa: BLE001 — rifiuto DICHIARATO, non ignoto
            # es. `OrderUpdateError: Current status: OrderStatus.EXECUTION_COMPLETE`
            # (l'ordine non e' piu' annullabile). Lo stato e' NOTO: si rilegge.
            return self._esito_cancel(bet_id, ordine, prima, ok=False,
                                      errore=type(ex).__name__ + ": " + str(ex)[:80])
        if accettato is False:
            motivo = str(getattr(ordine, "violation_msg", "") or "controllo flumine")
            return self._esito_cancel(bet_id, ordine, prima, ok=False, errore=motivo[:120])
        self._attendi_betfair(mercato)
        return self._esito_cancel(bet_id, ordine, prima, ok=None, errore=None)

    def _per_bet_id(self, bet_id: Any) -> Optional[Any]:
        for o in list(self.ordini.values()) + list(self.ordini_utente.values()):
            if str(getattr(o, "bet_id", None) or getattr(o, "id", "")) == str(bet_id):
                return o
        return None

    @staticmethod
    def _numeri(ordine: Any) -> Dict[str, float]:
        sim = getattr(ordine, "simulated", None)
        return {
            "matched": float(getattr(sim, "size_matched", 0.0) or 0.0),
            "cancelled": float(getattr(ordine, "size_cancelled", 0.0) or 0.0),
            "remaining": float(getattr(ordine, "size_remaining", 0.0) or 0.0),
        }

    def _esito_cancel(self, bet_id: Any, ordine: Any, prima: Dict[str, float],
                      ok: Optional[bool], errore: Optional[str]) -> CancelResult:
        """Legge dall'ordine com'e' andata. `ok=None` = lo decide il DELTA di
        `size_cancelled`: se non e' stato annullato niente, l'annullo NON e'
        avvenuto (e' il caso del mercato sospeso, `ERROR_IN_ORDER`)."""
        from ...omega.omega_market import CancelResult

        dopo = self._numeri(ordine)
        tagliato = round(max(0.0, dopo["cancelled"] - prima["cancelled"]), 2)
        riuscito = (tagliato > 0.0) if ok is None else bool(ok)
        sim = getattr(ordine, "simulated", None)
        return CancelResult(
            ok=riuscito,
            status=("SUCCESS" if riuscito else "FAILURE"),
            bet_id=str(bet_id),
            size_cancelled=tagliato,
            error_code=(errore if errore else (None if riuscito else "ERROR_IN_ORDER")),
            # lo stato dell'ordine e' sotto i nostri occhi: e' RILETTO davvero
            riletto=True,
            size_matched=round(dopo["matched"], 2),
            avg_price_matched=getattr(sim, "average_price_matched", None) or None,
            size_remaining=round(dopo["remaining"], 2),
            raw={"stato": self._stato_betfair(ordine)},
        )

    def place_submin_live(self, **kw: Any) -> PlaceResult:
        # LIMITE DICHIARATO: su flumine il minimo di giurisdizione non esiste,
        # quindi qui non c'e' nessun place-and-trim da riprodurre. Un importo
        # sotto il minimo viene piazzato diretto.
        return self.place_order_live(**kw)

    # -------------------------------------------------------- letture
    @staticmethod
    def _stato_betfair(ordine: Any) -> str:
        """Lo stato dell'ordine con le PAROLE DI BETFAIR.

        ⚠️ `order.status` in flumine e' un `Enum`: `str()` restituisce
        "OrderStatus.EXECUTABLE", non "Executable". Confrontarlo cosi' com'e'
        con le parole di Betfair non da' errore — da' sempre falso, e ogni
        ordine risulta NON vivo. Qui produceva 776 riproposizioni della stessa
        lay, cioe' un loop finto.
        """
        st = getattr(ordine, "status", None)
        parola = str(getattr(st, "value", st) or "").upper()
        if parola in ("PENDING", "EXECUTABLE"):
            return "EXECUTABLE"
        if parola.startswith("EXECUTION"):
            return "EXECUTION_COMPLETE"
        return parola or "EXPIRED"

    def _vivo(self, ordine: Any) -> bool:
        return self._stato_betfair(ordine) == "EXECUTABLE"

    def _riga(self, ref: str, ordine: Any) -> Dict[str, Any]:
        """Un ordine nella forma che `omega_market` produce dopo la
        normalizzazione: chiavi in snake_case, MAI camelCase."""
        sim = getattr(ordine, "simulated", None)
        return {
            "bet_id": str(getattr(ordine, "bet_id", None) or getattr(ordine, "id", "")),
            "market_id": str(getattr(ordine, "market_id", "")),
            "selection_id": int(getattr(ordine, "selection_id", 0) or 0),
            "side": str(getattr(ordine, "side", "") or "").lower(),
            "status": self._stato_betfair(ordine),
            "size_matched": float(getattr(sim, "size_matched", 0.0) or 0.0),
            "avg_price_matched": getattr(sim, "average_price_matched", None) or None,
            "size_remaining": float(getattr(ordine, "size_remaining", 0.0) or 0.0),
            "size_settled": float(getattr(sim, "size_matched", 0.0) or 0.0),
            "customer_order_ref": ref,
            # C.12a — la normalizzazione di produzione restituisce anche questi
            # (`omega_market.list_current_orders`): senza `size_cancelled` un
            # ordine annullato dal bot e uno morto per LAPSE sono
            # indistinguibili. Qui vengono dall'ordine flumine, non inventati.
            "size_cancelled": float(getattr(ordine, "size_cancelled", 0.0) or 0.0),
            "size_lapsed": float(getattr(ordine, "size_lapsed", 0.0) or 0.0),
            "size_voided": float(getattr(ordine, "size_voided", 0.0) or 0.0),
            "price_requested": getattr(getattr(ordine, "order_type", None), "price", None),
            "size_requested": getattr(getattr(ordine, "order_type", None), "size", None),
            # stessa cosa di `avg_price_matched`, con la grafia per esteso: un
            # consumatore che cerca l'una o l'altra trova sempre (15/09)
            "average_price_matched": getattr(sim, "average_price_matched", None) or None,
        }

    def _costa_una_lettura(self) -> None:
        """Una lettura NON e' gratis: costa il suo giro di rete, e in produzione
        quel tempo ritarda tutto cio' che il bot fa dopo. Vedi
        `LATENZA_LETTURA_S`: valore ASSUNTO, non misurato."""
        self.letture += 1
        if self.motore is not None and LATENZA_LETTURA_S > 0:
            self.motore.consuma_tempo(LATENZA_LETTURA_S)

    def list_current_orders(self, strategy_ref: Optional[str] = None) -> List[Dict[str, Any]]:
        self._costa_una_lettura()
        return [self._riga(ref, o) for ref, o in self.ordini.items() if self._vivo(o)]

    def list_cleared_orders(self, *_a: Any, **_k: Any) -> List[Dict[str, Any]]:
        self._costa_una_lettura()
        return [self._riga(ref, o) for ref, o in self.ordini.items() if not self._vivo(o)]

    def order_state_by_bet_id(self, bet_id: str) -> Dict[str, Any]:
        """Lo stato di UN ordine per betId, con le stesse chiavi della produzione.

        ⚠️ 16/09 SERA — QUESTO METODO MANCAVA, ed e' il motivo per cui il ramo
        (b) della riapertura («l'ordine appoggiato e' SCADUTO alla sospensione»)
        non e' MAI capitato sulle registrazioni vere. Quando Betfair fa scadere
        una lay appoggiata, quell'ordine esce dai CORRENTI: il servizio
        (``service._rileggi_ordine_appoggiato``) cerca allora
        ``market.order_state_by_bet_id`` — che in produzione esiste
        (``omega_market:1082``, guarda anche i regolati LAPSED/CANCELLED) e qui
        no. Senza, il servizio tornava «ignoto/mercato_senza_lettura» e la
        gamba finiva in riconciliazione invece che dichiarata SCADUTA: il banco
        raccontava una cosa che Betfair non avrebbe mai raccontato.

        Le chiavi sono quelle di ``omega_market.order_state_by_bet_id``
        (snake_case), nemmeno una in piu': un finto che parla una lingua
        diversa dal vero e' il difetto 27 del catalogo.
        """
        self._costa_una_lettura()
        ordine = self._per_bet_id(bet_id)
        if ordine is None:
            return {"found": False}
        sim = getattr(ordine, "simulated", None)
        return {
            "found": True,
            "size_matched": float(getattr(sim, "size_matched", 0.0) or 0.0),
            "avg_price_matched": getattr(sim, "average_price_matched", None) or None,
            "size_remaining": float(getattr(ordine, "size_remaining", 0.0) or 0.0),
            # la produzione non torna ne' ``size_lapsed`` ne' ``size_cancelled``
            # su questa strada (listCurrentOrders per betId e i regolati non li
            # portano): non si aggiungono qui, o il banco sarebbe piu' generoso
            # del vero.
            "matched_date": None,
            "placed_date": None,
        }

    # ------------------------------------------- LA POSIZIONE DI CONTO
    # «SE CHIUDO IO, IL BOT DEVE SAPERLO, ANCHE FUORI DALL'APP» (ordine
    # dell'utente, 16/09 sera). Il bot legge i SUOI ordini per
    # ``customerStrategyRef``; la posizione di CONTO sul mercato la si legge
    # SENZA filtro di strategia (``listCurrentOrders``/``listClearedOrders``
    # con i soli ``marketIds``). Qui il banco espone la stessa cosa dal
    # blotter di flumine: gli ordini del bot PIU' quelli dell'utente.
    def _righe_conto(self, quali: str, market_id: Optional[str]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for cassetto in (self.ordini, self.ordini_utente):
            for ref, o in cassetto.items():
                vivo = self._vivo(o)
                if (quali == "vivi") != vivo:
                    continue
                if market_id and str(getattr(o, "market_id", "")) != str(market_id):
                    continue
                out.append(self._riga(ref, o))
        return out

    def list_account_orders(self, market_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Ordini VIVI sul mercato, di CHIUNQUE (bot e utente)."""
        self._costa_una_lettura()
        return self._righe_conto("vivi", market_id)

    def list_account_cleared_orders(self, market_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Ordini non piu' vivi sul mercato, di CHIUNQUE (bot e utente)."""
        self._costa_una_lettura()
        return self._righe_conto("morti", market_id)

    def posizione_di_conto(self, market_id: str,
                           selection_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """LA POSIZIONE DI CONTO: vivi + morti, di CHIUNQUE, su questo mercato
        (e su UNA selezione se data).

        STESSO NOME, STESSA FIRMA, STESSE CHIAVI della produzione
        (``omega_market.posizione_di_conto``): e' la funzione che i bot chiamano
        per accorgersi di una chiusura fatta dall'utente FUORI dall'app. Qui
        costa due letture come li' (``_costa_una_lettura`` per lista), cosi' il
        tempo che ruba al giro e' quello vero.
        """
        righe = self.list_account_orders(market_id) + self.list_account_cleared_orders(market_id)
        if selection_id is None:
            return righe
        sid = int(selection_id)
        return [r for r in righe if int(r.get("selection_id") or -1) == sid]

    def place_order_utente(self, *, market_id: str, selection_id: int, price: float,
                           size: float, side: str = "lay",
                           customer_ref: str = "utente-1") -> Optional[Any]:
        """UN ORDINE DELL'UTENTE, piazzato DAVVERO su flumine con un ref suo.

        Non e' un finto: passa dallo stesso ``market.place_order`` e dallo
        stesso matching del bot. L'unica differenza e' che il suo ref non e'
        del bot, quindi il bot non lo vede fra i propri ordini — come su
        Betfair. Torna l'ordine, o None se il mercato non e' nel replay.
        """
        from flumine.order.ordertype import LimitOrder
        from flumine.order.trade import Trade

        mercato = self.s.mercati.get(str(market_id))
        if mercato is None:
            return None
        trade = Trade(market_id=str(market_id), selection_id=int(selection_id),
                      handicap=0.0, strategy=self.s)
        ordine = trade.create_order(
            side="BACK" if str(side).lower() == "back" else "LAY",
            order_type=LimitOrder(price=float(price), size=round(float(size), 2),
                                  persistence_type="LAPSE"),
        )
        ordine.notes["bot_ref"] = str(customer_ref)[:32]
        # marcato come dell'UTENTE: il guasto dello scenario
        # «chiusura-abbinata-in-parte» non lo colpisce e non lo conta nella
        # posizione del bot (le note non entrano nel matching di flumine)
        ordine.notes["utente"] = True
        if mercato.place_order(ordine) is False:
            return None
        self.ordini_utente[str(customer_ref)[:32]] = ordine
        self._attendi_betfair(mercato)
        return ordine

    # ------------------------------------------------- traccia forense
    def fills(self) -> Dict[str, List[List[Any]]]:
        """Ogni ABBINAMENTO, uno per uno: {ref: [[publish_time_ms, prezzo, size], ...]}.

        `SimulatedOrder.matched` (`flumine/simulation/simulatedorder.py:28`,
        riempita in `_process_price_matched` e `_process_traded`) tiene il
        PUBLISH TIME di ogni singolo fill, non solo l'aggregato: e' la traccia
        che PROCESSO_STANDARD_BOT §6.8 chiede nel referto e che finora il banco
        buttava via (leggeva solo `size_matched`/`average_price_matched`).
        Con questa si vede se "abbinato 5,00" e' venuto in un colpo o in sei, e
        a che prezzo ciascuno.
        """
        out: Dict[str, List[List[Any]]] = {}
        for ref, o in self.ordini.items():
            sim = getattr(o, "simulated", None)
            righe = list(getattr(sim, "matched", None) or [])
            if righe:
                out[ref] = [list(r) for r in righe]
        return out

    def riepilogo_fill(self) -> Dict[str, Any]:
        """Quanti fill, quanto abbinato, su quanti ordini (per il referto)."""
        per_ordine = self.fills()
        tutti = [r for righe in per_ordine.values() for r in righe]
        return {
            "ordini_con_fill": len(per_ordine),
            "fill": len(tutti),
            "abbinato": round(sum(float(r[2]) for r in tutti), 2),
            "prezzi": sorted({round(float(r[1]), 2) for r in tutti})[:8],
        }

    def pnl(self, commissione: float) -> Dict[str, Any]:
        """P&L LORDO e NETTO del replay, con la commissione della produzione.

        `order.simulated.profit` (`simulatedorder.py:564-635`) e' il LORDO:
        flumine non applica commissione (`client.commission_base` e' marcato
        `# not implemented`). La commissione di Betfair e' PER MERCATO sul netto
        VINCENTE, ed e' cosi' che la calcola gia' il Backtest Automatico
        (`run_backtest.py:156-162`): stessa formula, stessa aliquota che usa il
        bot in produzione — chi chiama la passa, il banco non se la inventa.
        """
        per_mercato: Dict[str, float] = {}
        for o in self.ordini.values():
            sim = getattr(o, "simulated", None)
            if sim is None:
                continue
            mid = str(getattr(o, "market_id", "") or "_ignoto")
            per_mercato[mid] = per_mercato.get(mid, 0.0) + float(getattr(sim, "profit", 0.0) or 0.0)
        lordo = sum(per_mercato.values())
        comm = sum(max(v, 0.0) * float(commissione) for v in per_mercato.values())
        return {"lordo": round(lordo, 2), "commissione": round(comm, 2),
                "netto": round(lordo - comm, 2), "aliquota": float(commissione),
                "mercati": {k: round(v, 2) for k, v in per_mercato.items()}}

    def read_book(self, market_id: str, *_a: Any, **_k: Any) -> Optional[Dict[str, Any]]:
        # il book a mercato chiuso serve al regolamento: nel replay lo stato
        # finale arriva dalla registrazione stessa (`process_closed_market`).
        self._costa_una_lettura()
        return None




def assicura_middleware_simulato(quadro: Any) -> int:
    """UN SOLO `SimulatedMiddleware`, e non due. Torna quanti ce ne sono.

    ⚠️ DIFETTO MISURATO IL 16/09 — `BaseFlumine.add_client` monta GIA' il
    `SimulatedMiddleware` quando il client e' simulato
    (`flumine/baseflumine.py:89-94`), e `add_market_middleware` NON
    de-duplica nella 2.13.11 (la de-duplicazione arriva in flumine 3.1.0).
    Aggiungerne un secondo a mano — come faceva questo repo in 15 punti —
    significa che OGNI book passa da DUE `RunnerAnalytics`, quindi il delta di
    `traded_volume` viene consumato DUE VOLTE dalla coda degli ordini
    appoggiati (`markets/middleware.py:182-243` + `simulatedorder.py:457-476`).
    Misura su `_live_raw/36006953`, stessa lay appoggiata:
    **85,72 EUR abbinati con 1 middleware, 200,34 EUR con 2 (+134 %)**.
    Non e' un fill scritto a mano: e' un fill CONTATO DUE VOLTE — il difetto 8
    del catalogo in forma nuova.

    Questa funzione e' l'unico punto da cui si monta il middleware: aggiunge
    solo se manca (per il caso in cui il quadro sia stato costruito senza un
    client simulato) e non aggiunge mai il secondo.
    """

    from flumine.markets.middleware import SimulatedMiddleware

    presenti = [m for m in quadro._market_middleware
                if isinstance(m, SimulatedMiddleware)]
    if not presenti:
        # e' l'UNICO punto del repo da cui si monta
        quadro.add_market_middleware(SimulatedMiddleware())
        return 1
    if len(presenti) > 1:  # pragma: no cover - difeso a monte
        raise RuntimeError(
            f"{len(presenti)} SimulatedMiddleware montati: la coda degli ordini "
            f"appoggiati verrebbe consumata {len(presenti)} volte "
            f"(misurato +134% di riempimento con 2)")
    return len(presenti)


def cliente_simulato() -> Any:
    """Il client simulato di flumine coi SUOI TETTI APERTI.

    `SimulatedClient` dichiara valuta GBP e da li' eredita `min_bet_size=1.00`
    e `min_bet_payout=10.00` (`flumine/clients/simulatedclient.py:32-50`): il
    controllo ORDER_VALIDATION rifiuta ogni ordine sotto quella soglia PRIMA
    che il bot possa dire la sua — visto dal vivo, "Order size is less than min
    bet size (1)" su tutte le chiusure sotto l'euro. Sono limiti DI FLUMINE, e
    per giunta di un'altra valuta: il minimo vero e' quello di giurisdizione
    (.it BACK 2,00 / LAY 0,50) e in produzione lo gestisce il place-and-trim
    (`omega_market.place_submin_live`). Lasciarli chiusi vorrebbe dire
    certificare i limiti di flumine invece di quelli del bot — la terza
    trappola gia' documentata nella memoria del 15/09, insieme a
    `max_order_exposure` / `max_selection_exposure` / `max_live_trade_count`.
    """
    from flumine import clients

    class _ClienteSenzaTetti(clients.SimulatedClient):
        def __init__(self, *a: Any, **kw: Any) -> None:
            # `transaction_limit`: 5000 transazioni/ora contate sull'ORA DI
            # MERCATO (`controls/clientcontrols.py:58-86`, e `datetime.now` in
            # simulazione e' il tempo dei book). E' un tetto DI FLUMINE: uno
            # scenario ad alta frequenza verrebbe frenato da lui invece che dal
            # bot. Aperto come gli altri; il limite vero, se si vuole misurare,
            # si esercita in uno scenario dedicato.
            kw.setdefault("transaction_limit", None)
            super().__init__(*a, **kw)

        @property
        def min_bet_size(self) -> float:
            return 0.0

        @property
        def min_bet_payout(self) -> float:
            return 0.0

        @property
        def min_bsp_liability(self) -> float:
            return 0.0

    return _ClienteSenzaTetti()


@contextmanager
def orologio_monotono():
    """L'orologio simulato di flumine NON TORNA INDIETRO.

    ⚠️ MISURATO IL 16/09 — il generatore storico di betfairlightweight
    consegna, a ogni aggiornamento, lo snapshot dei mercati sottoscritti, e ogni
    `MarketBook` porta il publish time DEL SUO mercato: la successione dei
    `publish_time` come arrivano NON e' monotona. Su `_live_raw/35833626`:
    **14.632 book su 30.923 (47,3 %) piu' vecchi del precedente, con salti
    all'indietro fino a 182 s.** `FlumineSimulation.run` li passa tali e quali a
    `simulated_datetime` (`simulation.py:110`), e da li' in poi:
      * `BaseEvent.elapsed_seconds` (`events/events.py:47`) puo' essere
        negativo -> l'attesa del bet delay perde significato;
      * `RunnerContext.reset/placed_elapsed_seconds` diventano negativi e il
        controllo STRATEGY_EXPOSURE rifiuta ordini legittimi
        (`strategy/strategy.py:162-171`): misurati 6 rifiuti su due partite,
        tutti con `reset_elapsed_seconds` fra -0,5 e -3,2 s.
    Il tempo vero non torna indietro. Qui si avvolge `SimulatedDateTime.__call__`
    perche' valga per QUALUNQUE simulazione del processo — banco comune e
    Backtest Automatico — senza che ognuno se lo ricordi.
    """
    from flumine.simulation.utils import SimulatedDateTime

    originale = SimulatedDateTime.__call__
    stato = {"ultimo": None, "in_ritardo": 0}

    def monotono(self, pt):
        ultimo = stato["ultimo"]
        if ultimo is not None and pt < ultimo:
            stato["in_ritardo"] += 1
            pt = ultimo
        stato["ultimo"] = pt
        return originale(self, pt)

    SimulatedDateTime.__call__ = monotono
    try:
        yield stato
    finally:
        SimulatedDateTime.__call__ = originale


@contextmanager
def simulazione_flumine():
    """Accende la simulazione di flumine e RIMETTE A POSTO i flag globali.

    `flumine.config` e' di PROCESSO: lasciare `simulated=True` (o una latenza
    cambiata) dopo un replay fa mentire tutto quello che gira dopo nello stesso
    processo — ed e' esattamente cosi' che, nella suite, due test di fedelta'
    paper hanno cominciato a fallire per colpa di un test del banco. Stesso
    pattern gia' usato da `run_backtest._run_one_event`.
    """
    import flumine.config as fconf

    prima = {
        "simulated": getattr(fconf, "simulated", False),
        "place_latency": getattr(fconf, "place_latency", 0.120),
        "cancel_latency": getattr(fconf, "cancel_latency", 0.170),
    }
    fconf.simulated = True
    try:
        with orologio_monotono() as stato:
            fconf._orologio_banco = stato       # diagnostica del giro corrente
            yield fconf
    finally:
        for chiave, valore in prima.items():
            setattr(fconf, chiave, valore)


# ---------------------------------------------------------------------------
# IL GENERATORE: gli stessi book, senza ricostruire quelli che non cambiano
# ---------------------------------------------------------------------------
# Il banco usa di DEFAULT la via veloce. E' un interruttore di modulo, non un
# parametro sparso, perche' il test di identita'
# (`Betfair/stream/tests/test_banco_identita_2026_09_16.py`) deve poter far
# girare la STESSA identica catena nelle due vie e confrontare i referti: se
# l'interruttore non fosse in un posto solo, la via lenta finirebbe per non
# essere piu' quella vera.
EMISSIONE_VELOCE = True

# L'ATTESA DELLE CHIAMATE BLOCCANTI DURA ESATTAMENTE QUANTO BETFAIR LA TRATTIENE.
# `False` rimette la vecchia attesa «finche' flumine esegue», che dipendeva dalla
# liquidita' del mercato invece che dalla regola: serve SOLO alla falsificazione
# (`MotoreReplay.attendi_esecuzione` spiega la regola e le fonti).
ATTESA_ESATTA = True

# LA CADENZA DEL BOT RIPARTE DA QUANDO IL GIRO E' FINITO, non da quando e'
# cominciato: in produzione le chiamate bloccanti consumano tempo vero e il ciclo
# successivo parte dopo. `False` rimette il conteggio dall'inizio del giro (che
# fa girare il bot piu' spesso di quanto giri davvero): serve alla misura
# prima/dopo e alla falsificazione.
CADENZA_DOPO_LE_CHIAMATE = True

# LATENZA DELLE CHIAMATE DI LETTURA — ASSUNTA, NON MISURATA (16/09/2026).
# `list_current_orders`, `list_cleared_orders` e `read_book` sono REST sincrone
# come il piazzamento, ma Betfair NON le trattiene per il bet delay: costano
# solo il giro di rete. Nel banco costavano ZERO tempo di mercato, cioe' il bot
# rileggeva gli ordini "gratis" — e in produzione non e' gratis.
# NON ABBIAMO UNA MISURA NOSTRA: `storia_operazioni.py` espone la catena del
# solo PIAZZAMENTO (`t4_inviato -> t5_risposta`). Su decisione del 16/09 si
# assume **120 ms per chiamata**, cioe' la stessa `config.place_latency` che
# flumine usa gia' ed e' gia' dentro ogni numero certificato. E' un'ASSUNZIONE:
# va detta nel referto (il banco stampa anche quante letture fa il bot per giro,
# cosi' si vede quanto pesa) e va sostituita appena esiste una misura vera.
# 0.0 la spegne (com'era prima): serve alla falsificazione e al confronto.
LATENZA_LETTURA_S = 0.120


class GeneratoreLibri:
    """`FlumineHistoricalGeneratorStream._read_loop`, con UNA differenza sola.

    COSA FA FLUMINE (`flumine/streams/historicalstream.py:259-275`): per OGNI
    riga del file costruisce un `MarketBook` per OGNI cache attiva, anche per i
    mercati che quel messaggio non ha toccato::

        yield [cache.create_resource(unique_id, snap=True)
               for cache in caches.values() if cache.active]

    Misurato su `_live_raw/36006953` (21 mercati): **448.476 MarketBook per
    58.801 aggiornamenti reali**, cioe' 7,6 volte quelli che servono, e
    `MarketBook.__init__` da solo vale 10,26 s su 30,2 s di replay.

    COSA CAMBIA QUI: **niente, tranne che l'oggetto non viene ricostruito**.
    Una cache cambia SOLO dentro `update_cache`, e `update_cache` viene chiamata
    SOLO per gli `id` presenti nel messaggio (`FlumineMarketStream._process`,
    `historicalstream.py:34-123`). Quindi per una cache non toccata
    `create_resource` produrrebbe un `MarketBook` con gli STESSI identici
    valori di quello del giro prima — compreso il `publish_time`, che e' quello
    del SUO ultimo aggiornamento (ed e' la ragione per cui il 47 % dei book
    arriva "all'indietro"). Qui quell'oggetto si riusa invece di rifarlo.

    Percio' la sequenza dei book emessi e' la stessa, nello stesso ordine, con
    gli stessi valori: il matching degli ordini (`SimulatedMiddleware` ->
    `_process_traded`), lo scanner, il conteggio dei tick e l'orologio vedono
    esattamente quello che vedevano prima. Non e' una emissione "selettiva" che
    salta aggiornamenti: e' la stessa emissione, memorizzata.

    Perche' riusare l'oggetto e' lecito: nessuno lo modifica. `Market.__call__`
    lo assegna e basta (`markets/market.py:43-46`), il `SimulatedMiddleware` lo
    legge (`markets/middleware.py:182-243`), lo scanner del banco se ne fa una
    vista propria (`libro_di_produzione`), e in flumine non esiste un solo
    confronto per identita' (`market_book is ...`). I `RunnerBook` erano gia'
    condivisi fra un `create_resource` e il successivo (`RunnerBookCache.
    serialise` memorizza `self.resource`, `betfairlightweight/streaming/
    cache.py:172-195`).

    IL JSON si legge una volta sola, con il parser che usa flumine
    (`betfairlightweight.compat.json`, cioe' `orjson` se installato): prima la
    riga veniva passata a `HistoricListener.on_data`, che la riparsava.
    """

    def __init__(self, stream: Any) -> None:
        # si lascia costruire il generatore a flumine, cosi' la costruzione
        # (listener, unique_id, update_clk) resta la sua, non una copia nostra
        funzione = stream.create_generator()
        gs = getattr(funzione, "__self__", None)
        if gs is None:  # pragma: no cover - flumine cambierebbe forma
            raise RuntimeError("generatore storico di flumine non riconosciuto")
        self._gs = gs
        self._funzione_lenta = funzione
        # diagnostica: quanti book ricostruiti e quanti riusati
        self.costruiti = 0
        self.riusati = 0

    # -- la via LENTA: esattamente quella di flumine, per il confronto -------
    def lento(self):
        return self._funzione_lenta()

    # -- la via VELOCE ------------------------------------------------------
    def veloce(self):
        import smart_open
        from betfairlightweight.compat import json as bflw_json

        gs = self._gs
        listener = gs.listener
        unique_id = gs.unique_id
        listener.register_stream(unique_id, gs.operation)
        flusso = listener.stream
        chiave = flusso._lookup
        caches = flusso._caches
        processa = flusso._process
        memoria: Dict[str, Any] = {}
        with smart_open.open(gs.file_path, "r") as fh:
            righe = fh.readlines()   # come flumine: tutto il file in RAM
        for riga in righe:
            try:
                dati = bflw_json.loads(riga)
            except ValueError:
                # `HistoricListener.on_data` (`historicalstream.py:245-250`)
                # logga e salta: qui uguale
                logger.error("value error: %s", riga[:120])
                continue
            # stesso ordine di lettura di `HistoricListener.on_data`
            # (`historicalstream.py:245-256`): prima `pt`, poi la chiave dello
            # stream. Una riga senza quei campi deve rompersi come si romperebbe
            # in flumine, non in un altro modo.
            publish_time = dati["pt"]
            aggiornamenti = dati[chiave]
            attivo = processa(aggiornamenti, publish_time)
            # L'INVALIDAZIONE VIENE PRIMA DEL FILTRO, SEMPRE.
            # `_process` aggiorna le cache e POI risponde `active` (che con i
            # `listener_kwargs` puo' essere False, `historicalstream.py:93-118`):
            # se si uscisse prima di invalidare, un mercato aggiornato da una
            # riga non emessa resterebbe memorizzato VECCHIO, e quello si' che
            # sarebbe una perdita di dati.
            for agg in aggiornamenti:
                mid = agg.get("id")
                if mid is not None:
                    memoria.pop(mid, None)      # questa cache e' cambiata
            if not attivo:
                continue
            fuori = []
            for mid, cache in caches.items():
                if not cache.active:
                    continue
                libro = memoria.get(mid)
                if libro is None:
                    libro = cache.create_resource(unique_id, snap=True)
                    memoria[mid] = libro
                    self.costruiti += 1
                else:
                    self.riusati += 1
                fuori.append(libro)
            yield fuori


# ---------------------------------------------------------------------------
# IL MOTORE: il ciclo di FlumineSimulation.run, ma guidabile
# ---------------------------------------------------------------------------
class MotoreReplay:
    """Il ciclo di `FlumineSimulation.run`, riscritto per poter ATTENDERE.

    Perche' non basta `quadro.run()`: in produzione `place_order_live` e' una
    REST SINCRONA e Betfair, su un mercato in gioco, TRATTIENE l'ordine per
    `betDelay` secondi prima di abbinarlo; la risposta che il bot legge e' gia'
    quella di DOPO il ritardo. Flumine sa riprodurlo — mette il pacchetto in
    `handler_queue` e lo esegue solo quando il TEMPO DI MERCATO ha superato
    `simulated_delay` = `config.place_latency` + `bet_delay`
    (`flumine/order/orderpackage.py:74-77`), col tempo che e' quello dei book
    grazie a `SimulatedDateTime` (`flumine/simulation/utils.py:17-41`, agganciato
    in `simulation.py:110`) — ma lo fa al giro successivo, quando la funzione del
    bot ha gia' restituito.

    Qui il ciclo e' nostro, quindi durante il piazzamento si puo' fare la cosa
    giusta: FAR SCORRERE IL TEMPO DI MERCATO fino a che flumine non esegue il
    pacchetto, esattamente come il bot resta bloccato sulla REST. I book che
    passano durante l'attesa vanno a flumine e allo SCANNER (che in produzione e'
    un altro processo e non si ferma mai), ma NON al giro del bot: quei tick il
    bot non li vede, perche' e' fermo ad aspettare Betfair.

    Il corpo di `_a_flumine` e' riga per riga quello di
    `FlumineSimulation._process_market_books` (`simulation.py:103-152`), meno la
    chiamata alla strategia.
    """

    def __init__(self, quadro: Any, *, su_book: Optional[Callable[[Any], None]] = None,
                 veloce: Optional[bool] = None) -> None:
        self.quadro = quadro
        self.su_book = su_book
        # `veloce=False` = il `_read_loop` di flumine tale e quale (ricostruisce
        # ogni MarketBook a ogni riga). Serve al test di identita', che confronta
        # le due vie sulla stessa registrazione: vedi `GeneratoreLibri`.
        # `None` = l'interruttore di modulo `EMISSIONE_VELOCE`.
        self.veloce = EMISSIONE_VELOCE if veloce is None else bool(veloce)
        self.generatore: Optional[GeneratoreLibri] = None
        self._gen: Any = None
        self._coda: Deque[Any] = deque()
        # L'OROLOGIO DI MERCATO NON TORNA INDIETRO.
        # Il generatore storico di betfairlightweight consegna, a ogni
        # aggiornamento, lo snapshot dei mercati sottoscritti, e OGNI MarketBook
        # porta il publish time DEL SUO mercato: la successione dei
        # `publish_time` cosi' come arrivano NON e' monotona. Misurato su
        # 35833626: 14.632 book su 30.923 (47,3 %) arrivano con un publish time
        # PIU' VECCHIO del precedente, con salti all'indietro fino a 182 s.
        # `FlumineSimulation.run` li passa tali e quali a `simulated_datetime`
        # (`simulation.py:110`), e da li' in poi il tempo simulato zigzaga: con
        # un tempo che torna indietro `BaseEvent.elapsed_seconds` e
        # `RunnerContext.reset/placed_elapsed_seconds` diventano NEGATIVI, il
        # controllo STRATEGY_EXPOSURE di flumine rifiuta ordini legittimi
        # (`strategy.py:162-171`) e l'attesa del bet delay perde significato.
        # Il tempo vero non torna indietro: qui nemmeno.
        self._ora_mercato: Any = None
        self.book_in_ritardo: int = 0
        # market_id -> era gia' in gioco? (per il lapse al fischio)
        self._in_gioco: Dict[str, bool] = {}
        self.lapse_al_fischio: int = 0
        # market_id -> ultimo stato visto (per la scadenza alla sospensione)
        self._stato_mercato: Dict[str, str] = {}
        self.lapse_alla_sospensione: int = 0
        # quanti book sono passati mentre un piazzamento aspettava il bet delay
        self.pompati: int = 0
        # piazzamenti per cui non esisteva nessun book futuro (registrazione
        # finita): eseguiti sull'ultimo book noto, e dichiarati
        self.senza_futuro: int = 0
        # tempo (e book) consumati dalle chiamate di LETTURA: l'assunzione dei
        # 120 ms si dichiara insieme a quanto ha pesato
        self.tempo_letture: float = 0.0
        self.book_letture: int = 0
        # IL GUASTO DELLO SCENARIO «chiusura-abbinata-in-parte»
        # (`chiusura_parziale.GuastoChiusuraParziale`). None = nessun guasto:
        # tutti gli altri scenari restano identici, riga per riga.
        self.guasto_chiusure: Any = None

    def _prepara_pacchi(self, pacchi: Sequence[Any]) -> None:
        """Passa al guasto (se c'e') i pacchetti PRIMA che flumine li esegua."""
        if self.guasto_chiusure is not None and pacchi:
            self.guasto_chiusure.prepara(self.quadro, list(pacchi))

    # ------------------------------------------------------------- flumine
    def _a_flumine(self, market_book: Any):
        from flumine import utils as futils
        from flumine.events import events as fevents

        quadro = self.quadro
        market_id = market_book.market_id
        adesso = market_book.publish_time
        if self._ora_mercato is not None and adesso < self._ora_mercato:
            # book piu' vecchio dell'orologio: si applica lo stesso (il PREZZO
            # e' l'ultimo noto di quel mercato) ma il tempo resta fermo
            self.book_in_ritardo += 1
            adesso = self._ora_mercato
        self._ora_mercato = adesso
        quadro.simulated_datetime(adesso)
        if quadro.handler_queue:
            if self.guasto_chiusure is not None:
                self._prepara_pacchi([p for p in quadro.handler_queue
                                      if str(getattr(p, "market_id", "")) == str(market_id)])
            quadro._check_pending_packages(market_id)
        if market_book.status == "CLOSED":
            quadro._process_close_market(event=fevents.CloseMarketEvent(market_book))
            return None, False
        market = quadro.markets.markets.get(market_id)
        nuovo = market is None
        if nuovo:
            market = quadro._add_market(market_id, market_book)
            quadro.log_control(fevents.MarketEvent(market))
        elif market.closed:
            quadro.markets.add_market(market_id, market)
        market(market_book)
        # PRIMA del middleware, che e' quello che abbina: su Betfair l'ordine e'
        # gia' morto quando il mercato passa in gioco, quindi non deve poter
        # prendere i prezzi del fischio.
        self._lapse_al_fischio(market, market_book)
        # ... e alla SOSPENSIONE IN GIOCO: su Betfair il gol uccide l'ordine
        # appoggiato prima che il mercato riapra. Anche questa PRIMA del
        # middleware che abbina.
        self._lapse_alla_sospensione(market, market_book)
        for middleware in quadro._market_middleware:
            futils.call_middleware_error_handling(middleware, market)
        if market.blotter.active:
            quadro._process_simulated_orders(market)
        return market, nuovo

    def _lapse_al_fischio(self, mercato: Any, market_book: Any) -> int:
        """Il mercato PASSA IN GIOCO: Betfair cancella gli ordini LAPSE non
        abbinati. Flumine lo fa solo alla SOSPENSIONE, e la sospensione arriva
        un tick DOPO (misurato: `(OPEN, False)` -> `(OPEN, True)` ->
        `(SUSPENDED, True)`). Torna quanti ordini sono stati uccisi.

        Si usano gli stessi campi di flumine (`SimulatedOrder.size_lapsed`),
        cosi' `size_remaining` va a zero, `_process_simulated_orders` chiude
        l'ordine e `list_current_orders`/`list_cleared_orders` del banco lo
        raccontano come lo racconterebbe Betfair.
        """
        md = getattr(market_book, "market_definition", None)
        in_gioco = bool(getattr(md, "in_play", False) if md is not None
                        else getattr(market_book, "inplay", False))
        mid = str(getattr(market_book, "market_id", ""))
        prima = self._in_gioco.get(mid)
        self._in_gioco[mid] = in_gioco
        if prima is not False or not in_gioco:
            return 0
        uccisi = self._uccidi_appoggiati(mercato)
        self.lapse_al_fischio += uccisi
        return uccisi

    def _lapse_alla_sospensione(self, mercato: Any, market_book: Any) -> int:
        """IL MERCATO SI SOSPENDE IN GIOCO (gol, rigore, rosso): Betfair
        CANCELLA gli ordini non abbinati con persistenza LAPSE. Torna quanti ne
        sono stati uccisi.

        PERCHE' SERVE, e perche' flumine non basta. `SimulatedOrder.__call__`
        (`flumine/simulation/simulatedorder.py:57-62`) lapsa a `SUSPENDED`
        **solo se `market_book.version` e' cambiata**:

            if market_book.version != self.market_version:
                self.market_version = market_book.version
                if market_book.status == "SUSPENDED":
                    if ...persistence_type == "LAPSE": size_lapsed += ...

        Sulle registrazioni vere quella condizione non si verifica sempre, e
        l'uscita appoggiata di Mike — che nasce DOPO il fischio, quindi non e'
        ancora a mercato quando scatta `_lapse_al_fischio` — sopravvivrebbe al
        gol e si abbinerebbe ai prezzi della riapertura: un fill che in live non
        sarebbe mai esistito, cioe' esattamente il difetto 13 del catalogo §7 in
        forma nuova.

        LA REGOLA DI BETFAIR (fonte, 16/09/2026): la persistenza LAPSE vuol dire
        che «l'ordine non abbinato viene cancellato se il mercato si sospende —
        quando va in gioco o quando si sospende per qualunque motivo, per esempio
        un gol» (guida alle persistenze di Wagertool,
        `wagertool.com/support/user-guide/bet-persistence-types`), e la risposta
        di Betfair sul `Keep bet` (support.betfair.com, risposta 415) dice che,
        quando in una partita di calcio capita un evento (gol, rigore, rosso),
        «gli altri ordini non abbinati vengono cancellati prima che il mercato
        riapra», mentre un `keep` (PERSIST) no. Le due pagine di supporto
        rispondono 403 a un recupero automatico: cio' che e' stato letto viene
        dalla ricerca, ed e' riportato qui per intero perche' chi rilegge possa
        contestarlo.

        Chi PERSISTE sopravvive, come su Betfair. Va chiamata PRIMA del
        middleware che abbina, per la stessa ragione di `_lapse_al_fischio`.
        """
        stato = str(getattr(market_book, "status", "") or "")
        mid = str(getattr(market_book, "market_id", ""))
        prima = self._stato_mercato.get(mid)
        self._stato_mercato[mid] = stato
        if stato != "SUSPENDED" or prima == "SUSPENDED":
            return 0
        md = getattr(market_book, "market_definition", None)
        in_gioco = bool(getattr(md, "in_play", False) if md is not None
                        else getattr(market_book, "inplay", False))
        if not in_gioco:
            # PRE-MATCH: qui la sospensione la gestisce gia' flumine al cambio di
            # versione, ed e' il caso VERIFICATO nel replay (35833626). Non si
            # tocca: si allarga solo il caso che flumine non copre.
            return 0
        uccisi = self._uccidi_appoggiati(mercato)
        self.lapse_alla_sospensione += uccisi
        return uccisi

    @staticmethod
    def _uccidi_appoggiati(mercato: Any) -> int:
        """Uccide gli ordini APPOGGIATI (non abbinati) con persistenza LAPSE.

        Si usano gli stessi campi di flumine (`SimulatedOrder.size_lapsed`),
        cosi' `size_remaining` va a zero, `_process_simulated_orders` chiude
        l'ordine e `list_current_orders`/`list_cleared_orders` del banco lo
        raccontano come lo racconterebbe Betfair.
        """
        uccisi = 0
        for ordine in list(getattr(mercato.blotter, "live_orders", []) or []):
            sim = getattr(ordine, "simulated", None)
            if sim is None:
                continue
            tipo = getattr(ordine, "order_type", None)
            if str(getattr(tipo, "persistence_type", "LAPSE") or "LAPSE") != "LAPSE":
                continue                      # PERSIST: sopravvive, come su Betfair
            residuo = float(getattr(ordine, "size_remaining", 0.0) or 0.0)
            if residuo <= 0:
                continue
            sim.size_lapsed += residuo
            uccisi += 1
        return uccisi

    def _prossimo(self) -> Optional[Any]:
        while not self._coda:
            try:
                evento = next(self._gen)
            except StopIteration:
                return None
            for mb in evento or []:
                self._coda.append(mb)
        return self._coda.popleft()

    # ------------------------------------------------------------- attesa
    def attendi_esecuzione(self, market_id: str) -> int:
        """Fa scorrere ESATTAMENTE il tempo per cui Betfair trattiene la
        chiamata, poi esegue. Torna quanti book sono passati.

        LA REGOLA DEL TEMPO, e da dove viene.
        `place_order_live` in produzione e' una REST **SINCRONA** (nessun
        `async` nelle istruzioni di `omega_market`), e su un mercato in gioco
        Betfair la TRATTIENE per il bet delay prima di rispondere. Due prove:
          * la doc Betfair per sviluppatori sul piazzamento asincrono dice che
            «la chiamata async torna subito con un riferimento e SENZA il
            ritardo in gioco» — cioe' quella sincrona il ritardo se lo prende;
          * i tempi VERI di questo repo: `HANDOFF_CONTROL_ROOM.md` §4.2 misura
            «4,2 s nostri + **3,3 s di Betfair**, che sono bet delay e non si
            toccano» sulla catena `t4_inviato -> t5_risposta` letta da
            `safe_strategy/tools/storia_operazioni.py`.
        Quindi il ciclo del bot e' DAVVERO fermo per `place_latency + betDelay`
        a ogni piazzamento, e per `cancel_latency` a ogni annullo (Betfair non
        trattiene un annullo, `flumine/order/orderpackage.py:74-79`).

        COSA C'ERA PRIMA, E PERCHE' ERA UN DIFETTO. Il banco aspettava «finche'
        flumine non esegue», e flumine controlla i pacchetti solo quando arriva
        un book **di quel mercato** (`simulation.py:113-115`): su un mercato
        poco liquido l'attesa poteva durare molto piu' del bet delay, su un
        altro meno. Il tempo consumato dipendeva dalla LIQUIDITA' del mercato,
        non dalla regola di Betfair — e siccome durante l'attesa scorrono i book
        di TUTTI i mercati, due scenari che facevano un numero diverso di
        chiamate arrivavano al punto in comune con l'orologio in posti diversi.
        E' cosi' che sulla stessa partita l'INGRESSO risultava abbinato a quote
        diverse in scenari che prima dell'ingresso sono identici.

        ADESSO: si pompano book finche' l'orologio di mercato non ha superato
        `simulated_delay` (che flumine calcola gia': `place_latency + bet_delay`
        per un PLACE, `cancel_latency` per un CANCEL), e a quel punto si esegue,
        sul book piu' recente noto di quel mercato — che e' esattamente
        l'informazione che Betfair avrebbe a quell'istante.

        `ATTESA_ESATTA = False` rimette la vecchia attesa: serve solo al test di
        falsificazione.
        """
        mid = str(market_id)
        passati = 0
        while True:
            pacchi = [p for p in self.quadro.handler_queue
                      if str(getattr(p, "market_id", "")) == mid]
            if not pacchi:
                break
            if ATTESA_ESATTA and all(
                    float(getattr(p, "elapsed_seconds", 0.0) or 0.0)
                    > float(getattr(p, "simulated_delay", 0.0) or 0.0)
                    for p in pacchi):
                # il tempo di Betfair e' trascorso: si risponde ADESSO
                self._esegui_adesso(pacchi)
                break
            mb = self._prossimo()
            if mb is None:
                # la registrazione e' finita: non esiste NESSUN book futuro su
                # cui valutare l'ordine. Si esegue sull'ultimo noto (che e'
                # quanto di meglio esista) e lo si DICHIARA nel referto.
                self._esegui_adesso(pacchi)
                self.senza_futuro += 1
                break
            passati += 1
            mercato, _nuovo = self._a_flumine(mb)
            if mercato is not None and self.su_book is not None:
                # lo SCANNER non si ferma: in produzione e' un altro processo,
                # e mentre il bot aspetta Betfair lui continua a pubblicare
                self.su_book(mb)
        self.pompati += passati
        return passati

    def consuma_tempo(self, secondi: float) -> int:
        """Fa scorrere `secondi` di TEMPO DI MERCATO senza far girare il bot.

        E' quello che succede a ogni chiamata REST che non sia un piazzamento:
        il bot e' fermo sulla rete, i book continuano ad arrivare, lo SCANNER
        (in produzione e' un altro processo) continua a pubblicare. Torna quanti
        book sono passati. Se la registrazione finisce si smette e basta: non si
        inventa futuro.
        """
        if secondi <= 0 or self._ora_mercato is None:
            return 0
        scadenza = self._ora_mercato + timedelta(seconds=float(secondi))
        passati = 0
        while self._ora_mercato < scadenza:
            mb = self._prossimo()
            if mb is None:
                break
            passati += 1
            mercato, _nuovo = self._a_flumine(mb)
            if mercato is not None and self.su_book is not None:
                self.su_book(mb)
        self.tempo_letture += float(secondi)
        self.book_letture += passati
        return passati

    def _esegui_adesso(self, pacchi: Sequence[Any]) -> None:
        """Esegue i pacchetti e li toglie dalla coda, come farebbe
        `_check_pending_packages` (`simulation.py:185-195`)."""
        self._prepara_pacchi(list(pacchi))
        for pacco in list(pacchi):
            pacco.client.execution.handler(pacco)
            try:
                self.quadro.handler_queue.remove(pacco)
            except ValueError:  # pragma: no cover - gia' tolto
                pass

    # ------------------------------------------------------------- il giro
    def esegui(self, strategia: Any) -> None:
        from flumine import utils as futils

        from . import trasporto as _trasporto

        # 25/09 (F4): il TRASPORTO dell'ordine scelto da ``certifica --trasporto``
        # (coda di oggi o canale del runner). Fuori da ``trasporto.contesto`` e'
        # nullo: i replay di sempre non cambiano di una riga.
        _trasporto.su_esegui(self, strategia)
        quadro = self.quadro
        with quadro:
            with quadro.simulated_datetime:
                for stream in quadro.streams:
                    quadro.simulated_datetime.reset_real_datetime()
                    self.generatore = GeneratoreLibri(stream)
                    self._gen = (self.generatore.veloce() if self.veloce
                                 else self.generatore.lento())
                    while True:
                        mb = self._prossimo()
                        if mb is None:
                            break
                        mercato, nuovo = self._a_flumine(mb)
                        if mercato is None:
                            continue
                        if mb.streaming_unique_id not in strategia.stream_ids:
                            continue
                        if nuovo:
                            futils.call_strategy_error_handling(
                                strategia.process_new_market, mercato, mb)
                        if futils.call_strategy_error_handling(
                                strategia.check_market_book, mercato, mb):
                            futils.call_strategy_error_handling(
                                strategia.process_market_book, mercato, mb)
                    quadro.handler_queue.clear()


# ---------------------------------------------------------------------------
# lo SCANNER VERO alimentato dai book di flumine
# ---------------------------------------------------------------------------
_TIPI_OPP = tuple(t.upper() for t in SCAN.OPP_MARKET_TYPES)
_TIPI_PUNTEGGIO = {"CORRECT_SCORE": "cs", "HALF_TIME_SCORE": "ht"}


def _nome_runner(market_type: str, sort_priority: Optional[int],
                 linea: Optional[float], squadre: Tuple[Optional[str], Optional[str]]) -> str:
    """Il nome del runner come lo darebbe il catalogo (LIMITE 1 in testa)."""
    mt = (market_type or "").upper()
    sp = int(sort_priority) if sort_priority is not None else None
    if mt == "MATCH_ODDS" or mt == SCAN.HT_RESULT_MARKET_TYPE:
        casa, fuori = squadre
        if sp == 1 and casa:
            return str(casa)
        if sp == 2 and fuori:
            return str(fuori)
        return str(_synth_name("MATCH_ODDS", sp) or "")
    if mt.startswith("OVER_UNDER") and linea is not None:
        if sp == 1:
            return f"Under {linea} Goals"
        if sp == 2:
            return f"Over {linea} Goals"
        return ""
    if mt == SCAN.BTTS_MARKET_TYPE:
        return str(_synth_name("BOTH_TEAMS_TO_SCORE", sp) or "")
    return ""


class ScannerReplay:
    """Lo `Scanner` VERO di `safe_strategy/service.py`, alimentato dal replay.

    Il client Betfair e' None e `dry=True`: nessuna rete, nessun DB. Verificato
    (test `Betfair/stream/tests/test_banco_comune_2026_09_16.py`): `Scanner.__init__` non fa login, non apre
    stream (`use_stream=False`) e non chiama REST — l'unico ramo che tocca la
    rete e' `MarketStreamPool`, che nasce solo con `use_stream=True`.
    Il catalogo, che in produzione arriva da `listMarketCatalogue`, qui lo
    riempie `registra_mercato` dai `marketDefinition` della registrazione
    (LIMITE 1).
    """

    def __init__(self, *, sport: str = "calcio", pre_ko_ou_hours: float = 6.0,
                 nomi_extra: Optional[Dict[str, Dict[int, str]]] = None,
                 conflate_ms: int = 1000, ritardo_punteggi_s: float = 0.0) -> None:
        if sport not in ("calcio", "tennis"):
            raise ValueError(f"sport non gestito: {sport}")
        self.sport = sport
        # CONFLAZIONE, come in produzione. Il pool stream dello scanner e'
        # sottoscritto con `conflate_ms=1000` (`safe_strategy/stream.py:49,228`):
        # allo scanner arriva AL PIU' UN book al secondo per mercato. Il
        # recorder invece registra con conflate 0 (`stream/recorder.py:127`),
        # cioe' ogni singolo messaggio. Applicarli tutti darebbe allo scanner
        # del banco un flusso che in produzione non vede mai (misurato su
        # 35674515: 4,3 book al secondo sul solo MATCH_ODDS). Qui si conflata
        # per mercato alla stessa cadenza del vero. A 0 si applica tutto.
        self.conflate_ms = int(conflate_ms)
        self._ultimo_book_ms: Dict[str, int] = {}
        # ritardo AGGIUNTIVO dei punteggi (vedi la testa del modulo: quello vero
        # e' gia' dentro `ts_ms` del sidecar). In secondi, 0 = nessuna aggiunta.
        self.ritardo_punteggi_s = float(ritardo_punteggi_s)
        self._ora_s: float = 0.0
        from ...safe_strategy.service import Scanner as ScannerVero

        self.scan = ScannerVero(api_client=None, dry=True, use_stream=False,
                                orologio=lambda: self._ora_s)
        # ramo pre-KO O/U (bot Mike): in produzione e' l'env SAFE_PRE_KO_OU_HOURS.
        # Qui si dichiara esplicitamente, perche' senza di esso le linee O/U di
        # una partita non ancora iniziata non entrerebbero MAI nel feed.
        self.scan.pre_ko_ou_hours = float(pre_ko_ou_hours) if sport == "calcio" else 0.0
        # nomi che il catalogo darebbe e il raw non ha (CORRECT_SCORE,
        # HALF_TIME_SCORE): {market_id: {selection_id: nome}}
        self.nomi_extra: Dict[str, Dict[int, str]] = dict(nomi_extra or {})
        # squadre/giocatori dal sidecar punteggi (l'unico posto dove i nomi ci sono)
        self.squadre: Tuple[Optional[str], Optional[str]] = (None, None)
        self.event_name: Optional[str] = None
        # LA TABELLA `safe_strategy_scan`, in memoria: e' da qui che i bot leggono
        self.tabella: Dict[str, Dict[str, Any]] = {}
        self.righe_scritte: int = 0
        self.mercati_visti: Dict[str, str] = {}      # market_id -> market_type

    # ------------------------------------------------------------- orologio
    @property
    def ora(self) -> float:
        return self._ora_s

    def imposta_ora(self, epoch_s: float) -> float:
        """"Adesso" per lo scanner = il publish time del tick, e NON TORNA
        INDIETRO (vedi `MotoreReplay`: i book non arrivano in ordine di tempo).

        In produzione lo scanner legge l'orologio del PC, che e' monotono: una
        riga di scan con `updated_at` che indietreggia, o un `seen_ms` che
        ringiovanisce, sarebbero fatti che in produzione non esistono.
        Torna l'ora effettivamente impostata."""
        self._ora_s = max(self._ora_s, float(epoch_s))
        return self._ora_s

    def adesso(self) -> datetime:
        return datetime.fromtimestamp(self._ora_s, tz=timezone.utc)

    # ------------------------------------------------------------- catalogo
    def dichiara_nomi(self, home: Optional[str], away: Optional[str]) -> None:
        """I nomi veri delle due parti, letti dal sidecar punteggi."""
        if home or away:
            self.squadre = (home, away)
            self.event_name = f"{home or '?'} v {away or '?'}"
            for st in self.scan.sports.values():
                for meta in st.metas.values():
                    meta["event_name"] = self.event_name
                    for r in meta.get("runners") or []:
                        if r.get("sort_priority") == 1 and home:
                            r["name"] = home
                        elif r.get("sort_priority") == 2 and away:
                            r["name"] = away

    def registra_mercato(self, market_book: Any) -> Optional[str]:
        """Mette il mercato nel CATALOGO dello scanner (una volta sola).

        Torna il tipo di mercato, o None se il book non e' utilizzabile.
        """
        md = getattr(market_book, "market_definition", None)
        mid = str(getattr(market_book, "market_id", "") or "")
        if not mid or md is None:
            return None
        mtype = str(getattr(md, "market_type", None) or "").upper()
        eid = str(getattr(md, "event_id", "") or "")
        if not eid:
            return mtype or None
        if mid in self.mercati_visti:
            return self.mercati_visti[mid]
        linea = SCAN.ou_line_from_market_type(mtype)
        runners = [
            {
                "selection_id": int(getattr(rd, "selection_id", 0) or 0),
                "name": (self.nomi_extra.get(mid, {}).get(int(getattr(rd, "selection_id", 0) or 0))
                         or _nome_runner(mtype, getattr(rd, "sort_priority", None),
                                         linea, self.squadre)),
                "sort_priority": (int(getattr(rd, "sort_priority", 0))
                                  if getattr(rd, "sort_priority", None) is not None else None),
            }
            for rd in (getattr(md, "runners", None) or [])
            if getattr(rd, "selection_id", None) is not None
        ]
        avvio = getattr(md, "market_time", None) or getattr(md, "open_date", None)
        open_date = avvio.isoformat() if hasattr(avvio, "isoformat") else (
            str(avvio) if avvio else None)
        registrato = False
        if mtype == "MATCH_ODDS":
            st = self.scan.sports[self.sport]
            st.metas[eid] = {
                "event_id": eid,
                "market_id": mid,
                "event_name": self.event_name or str(getattr(md, "event_name", None) or eid),
                "open_date": open_date,
                # LIMITE 1: la competizione sta solo nel catalogo REST
                "competition": None,
                "runners": runners,
                "sides": (SCAN.selection_sides(runners) if self.sport == "calcio"
                          else SCAN.tennis_sides(runners)),
            }
            st.catalogue_ts = 1.0
            registrato = True
        elif mtype in _TIPI_OPP and self.sport == "calcio":
            self.scan.opp_markets.setdefault(eid, {})[mid] = {
                "market_id": mid,
                "market_type": mtype,
                "line": linea,
                "names": {int(r["selection_id"]): r["name"] for r in runners},
            }
            self.scan.opp_full_eids.add(eid)
            registrato = True
        elif mtype in _TIPI_PUNTEGGIO and self.sport == "calcio":
            store = (self.scan.cs_markets if _TIPI_PUNTEGGIO[mtype] == "cs"
                     else self.scan.ht_markets)
            store[eid] = {
                "market_id": mid,
                "names": {int(r["selection_id"]): r["name"] for r in runners},
            }
            registrato = True
        self.mercati_visti[mid] = mtype
        if registrato:
            self.scan._rebuild_market_index()
        return mtype

    # ------------------------------------------------------------- i book
    def applica_book(self, market_book: Any) -> bool:
        """IL PUNTO: il book di flumine entra nello SCANNER VERO.

        `Scanner._apply_market_book` e' la stessa identica funzione con cui lo
        scanner applica i book dello stream e del poll REST: da qui in poi
        prezzi, `pre_ko`, blocchi O/U, Correct Score e Half Time li costruisce
        lui, non questo file.
        """
        mid = str(getattr(market_book, "market_id", "") or "")
        if mid not in self.scan.market_meta:
            return False
        if self.conflate_ms > 0:
            adesso_ms = int(self._ora_s * 1000)
            if adesso_ms - self._ultimo_book_ms.get(mid, -10 ** 12) < self.conflate_ms:
                return False
            self._ultimo_book_ms[mid] = adesso_ms
        self.scan._apply_market_book(libro_di_produzione(market_book))
        return True

    # ------------------------------------------------------------ punteggi
    def applica_punteggio(self, event_id: str, record: Dict[str, Any]) -> bool:
        """Lo stato IPS grezzo del sidecar entra da `Scanner.apply_score_state`,
        cioe' dalla stessa funzione che usa `poll_scores` in produzione."""
        return self.scan.apply_score_state(str(event_id), record)

    # --------------------------------------------------------- le righe
    def pubblica(self) -> List[Dict[str, Any]]:
        """`build_rows` VERA -> tabella `safe_strategy_scan` in memoria.

        Riproduce anche cio' che fa `publish`: le righe degli eventi che non
        sono piu' monitorabili vengono CANCELLATE dalla tabella (e' quello che
        in produzione fa sparire la riga dal feed quando la partita chiude).
        """
        rows, wanted = self.scan.build_rows(self.adesso())
        for row in rows:
            self.tabella[str(row["event_id"])] = row
            self.righe_scritte += 1
        voluti = set(wanted)
        for eid in [e for e in self.tabella if e not in voluti]:
            self.tabella.pop(eid, None)
            self.scan.written_sig.pop(eid, None)
            self.scan.written_crit.pop(eid, None)
            self.scan.last_pub_mono.pop(eid, None)
        return rows

    def riga(self, event_id: str) -> Optional[Dict[str, Any]]:
        """La riga come un bot la leggerebbe dalla tabella (o None se assente)."""
        row = self.tabella.get(str(event_id))
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# i sidecar dei punteggi
# ---------------------------------------------------------------------------
def carica_punteggi(cartella: str, event_id: str, sport: str = "calcio") -> List[Tuple[int, Dict[str, Any]]]:
    """[(ts_ms, record IPS grezzo)] dal sidecar della registrazione.

    Calcio: `<id>.scores.jsonl`, righe `{"ts_ms":…, "payload": <record IPS>}`.
    Tennis: `<id>.score.jsonl`,  righe `{"t": <epoch s>, "score": <record IPS>}`.
    In entrambi i casi cio' che si tiene e' il RECORD GREZZO, che e' l'unica
    cosa che `apply_score_state` sa leggere: nessun campo ricostruito a mano.
    """
    nomi = ([f"{event_id}.scores.jsonl", f"{event_id}.score.jsonl"] if sport == "calcio"
            else [f"{event_id}.score.jsonl", f"{event_id}.scores.jsonl"])
    out: List[Tuple[int, Dict[str, Any]]] = []
    for nome in nomi:
        path = os.path.join(cartella, str(event_id), nome)
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as fh:
            for riga in fh:
                riga = riga.strip()
                if not riga:
                    continue
                try:
                    rec = json.loads(riga)
                except (ValueError, TypeError):
                    continue
                if not isinstance(rec, dict):
                    continue
                stato = rec.get("payload") if isinstance(rec.get("payload"), dict) else None
                if stato is None and isinstance(rec.get("score"), dict):
                    stato = rec["score"]
                if stato is None:
                    continue
                ts = rec.get("ts_ms")
                if ts is None and rec.get("t") is not None:
                    ts = int(float(rec["t"]) * 1000)
                if ts is None and rec.get("ts"):
                    try:
                        ts = int(datetime.fromisoformat(
                            str(rec["ts"]).replace("Z", "+00:00")).timestamp() * 1000)
                    except (ValueError, TypeError):
                        ts = None
                if ts is None:
                    continue
                out.append((int(ts), stato))
        if out:
            break
    out.sort(key=lambda x: x[0])
    return out


def nomi_dal_punteggio(punteggi: Sequence[Tuple[int, Dict[str, Any]]]) -> Tuple[Optional[str], Optional[str]]:
    """I nomi delle due parti dal record IPS (l'unico posto dove ci sono)."""
    for _ts, rec in punteggi:
        blocco = (rec or {}).get("score") or {}
        casa = ((blocco.get("home") or {}).get("name")) if isinstance(blocco, dict) else None
        fuori = ((blocco.get("away") or {}).get("name")) if isinstance(blocco, dict) else None
        if casa or fuori:
            return (str(casa) if casa else None, str(fuori) if fuori else None)
    return (None, None)


# ---------------------------------------------------------------------------
# il driver: un evento, un servizio
# ---------------------------------------------------------------------------
class EsitoReplay:
    """Che cosa e' successo in un replay: numeri grezzi, nessun giudizio."""

    def __init__(self, event_id: str) -> None:
        self.event_id = str(event_id)
        self.tick = 0
        self.giri = 0
        self.righe_scan = 0
        self.errori: List[str] = []
        self.note: List[str] = []
        self.mercati: Dict[str, int] = {}
        self.ultima_riga: Optional[Dict[str, Any]] = None
        # book passati mentre un piazzamento aspettava il bet delay
        self.book_attesi: int = 0
        # piazzamenti senza nessun book futuro (registrazione finita)
        self.senza_futuro: int = 0
        # book arrivati con un publish time piu' vecchio dell'orologio di mercato
        self.book_in_ritardo: int = 0
        # ordini appoggiati uccisi dal passaggio in gioco, come fa Betfair
        self.lapse_al_fischio: int = 0
        # ordini appoggiati uccisi dalla SOSPENSIONE IN GIOCO (gol/rigore/rosso)
        self.lapse_alla_sospensione: int = 0


def replay_evento(**kw: Any) -> EsitoReplay:
    """Guscio: accende la simulazione di flumine e la RIMETTE A POSTO alla fine
    (i flag di `flumine.config` sono di processo). Il lavoro lo fa
    `_replay_evento`."""
    with simulazione_flumine():
        return _replay_evento(**kw)


def _replay_evento(*, event_id: str, cartella: str, servizio: Callable[..., Any],
                   sport: str = "calcio", ogni_ms: int = 1000,
                   pre_ko_ou_hours: float = 6.0, conflate_ms: int = 1000,
                   ritardo_punteggi_s: float = 0.0,
                   strategia_extra: Optional[Dict[str, Any]] = None,
                   su_strategia: Optional[Callable[[Any], None]] = None,
                   nomi_extra: Optional[Dict[str, Dict[int, str]]] = None,
                   db: Optional[Any] = None,
                   veloce: Optional[bool] = None) -> EsitoReplay:
    """Fa rivivere UNA registrazione e chiama `servizio` a ogni giro.

    ``servizio`` riceve, per parole chiave: ``db`` (il `DbMemoria`),
    ``market`` (il `MercatoFlumine`), ``now`` (datetime UTC del tick), ``row``
    (la riga di scan come la leggerebbe dalla tabella, o None), ``banco``
    (lo `ScannerReplay`) e ``strategia`` (l'oggetto flumine, per i mercati).
    E' il punto di aggancio per Omega, Safe calcio e Safe tennis: cambia il
    servizio, non il banco.
    """
    from flumine import BaseStrategy, FlumineSimulation

    raw = os.path.join(cartella, str(event_id), f"{event_id}.raw.jsonl")
    esito = EsitoReplay(event_id)
    if not os.path.exists(raw):
        esito.errori.append(f"registrazione assente: {raw}")
        return esito

    punteggi = carica_punteggi(cartella, str(event_id), sport)
    if not punteggi:
        esito.note.append("sidecar punteggi assente: minuto e gol non arrivano mai")
    ts_punteggi = [t for t, _ in punteggi]
    banco = ScannerReplay(sport=sport, pre_ko_ou_hours=pre_ko_ou_hours,
                          nomi_extra=nomi_extra, conflate_ms=conflate_ms,
                          ritardo_punteggi_s=ritardo_punteggi_s)
    banco.dichiara_nomi(*nomi_dal_punteggio(punteggi))
    memoria = db if db is not None else DbMemoria({"status": "running", "mode": "paper"})

    class _Ponte(BaseStrategy):
        def __init__(self, **kw: Any) -> None:
            self.mercati: Dict[str, Any] = {}
            # il motore lo si aggancia dopo (serve il `quadro`): e' lui che fa
            # scorrere il tempo di mercato durante il piazzamento
            self.mercato = MercatoFlumine(self)
            self._ultimo_ms = 0
            self._i_punteggi = 0
            super().__init__(**kw)

        def check_market_book(self, market: Any, market_book: Any) -> bool:
            return True

        def process_market_book(self, market: Any, market_book: Any) -> None:
            mtype = banco.registra_mercato(market_book)
            if not mtype:
                return
            esito.mercati[mtype] = esito.mercati.get(mtype, 0) + 1
            self.mercati[str(market_book.market_id)] = market
            pt = getattr(market_book, "publish_time", None)
            pt_ms = int(banco.imposta_ora(pt.timestamp()) * 1000) if pt is not None else 0
            banco.applica_book(market_book)
            esito.tick += 1
            if pt_ms - self._ultimo_ms < int(ogni_ms):
                return
            self._ultimo_ms = pt_ms
            self._giro(pt_ms)
            # LA CADENZA RIPARTE DA QUANDO IL GIRO E' FINITO, non da quando
            # e' cominciato. In produzione le chiamate bloccanti (un
            # piazzamento in gioco: `place_latency + betDelay`) consumano tempo
            # VERO, e il ciclo successivo parte dopo: un giro lungo ritarda il
            # giro dopo. Segnando l'inizio, il replay farebbe girare il bot piu'
            # spesso di quanto giri davvero.
            if CADENZA_DOPO_LE_CHIAMATE:
                self._ultimo_ms = max(self._ultimo_ms, int(banco.ora * 1000))

        def _giro(self, pt_ms: int) -> None:
            # i punteggi fino a questo istante, uno per uno, dalla funzione vera
            i = bisect_right(ts_punteggi,
                             int(pt_ms - banco.ritardo_punteggi_s * 1000.0))
            while self._i_punteggi < i:
                banco.applica_punteggio(str(event_id), punteggi[self._i_punteggi][1])
                self._i_punteggi += 1
            banco.pubblica()
            esito.righe_scan = banco.righe_scritte
            riga = banco.riga(str(event_id))
            esito.ultima_riga = riga
            esito.giri += 1
            try:
                servizio(db=memoria, market=self.mercato, now=banco.adesso(),
                         row=riga, banco=banco, strategia=self)
            except Exception as ex:  # noqa: BLE001 - un'eccezione del servizio E' un referto
                esito.errori.append(f"{type(ex).__name__}: {ex}")

    strategia = _Ponte(
        market_filter={"markets": [raw]},
        # I TETTI DI FLUMINE VANNO APERTI: qui il rischio lo governa il bot coi
        # suoi parametri, ed e' quello che si vuole misurare. Coi default
        # (1 trade vivo per selezione, 10 EUR per ordine) flumine rifiuterebbe
        # gli ordini da fuori e il referto direbbe che il bot non fa niente.
        max_order_exposure=1e9, max_selection_exposure=1e9,
        max_trade_count=int(1e9), max_live_trade_count=int(1e9),
        **(strategia_extra or {}),
    )
    if su_strategia is not None:
        su_strategia(strategia)
    quadro = FlumineSimulation(client=cliente_simulato())
    assicura_middleware_simulato(quadro)
    quadro.add_strategy(strategia)

    def _scanner_durante_attesa(mb: Any) -> None:
        # il bot e' bloccato sulla REST, lo SCANNER no: in produzione e' un
        # altro processo e continua a ricevere i book e a pubblicare.
        pt = getattr(mb, "publish_time", None)
        if pt is not None:
            banco.imposta_ora(pt.timestamp())
        if banco.registra_mercato(mb):
            banco.applica_book(mb)

    motore = MotoreReplay(quadro, su_book=_scanner_durante_attesa, veloce=veloce)
    strategia.mercato.motore = motore
    with simulazione_flumine():
        motore.esegui(strategia)
    esito.book_attesi = motore.pompati
    esito.book_in_ritardo = motore.book_in_ritardo
    esito.lapse_al_fischio = motore.lapse_al_fischio
    esito.lapse_alla_sospensione = motore.lapse_alla_sospensione
    esito.senza_futuro = motore.senza_futuro
    return esito
