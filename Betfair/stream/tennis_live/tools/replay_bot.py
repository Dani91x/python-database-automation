# -*- coding: utf-8 -*-
"""I QUATTRO BOT TENNIS SULLE REGISTRAZIONI VERE — il replay col motore Betfair.

Fa rivivere a UNO dei quattro bot tennis (`tennis_scalper`, `tennis_pro`,
`tennis_flb`, `tennis_swing`) una partita registrata, tick per tick, coi prezzi
veri di Betfair, e a ogni giro verifica la CONDOTTA contro
`Betfair/stream/tennis_live/certificazione_bot.py`. Non misura il profitto:
misura la condotta (`PROCESSO_STANDARD_BOT.md` gradino 3).

LA CATENA, e nessun passo e' saltato:

    raw registrato  `~/Desktop/tennis_rec/<giorno>/<id>/<id>.raw.jsonl`
      -> flumine    `FlumineSimulation` + `HistoricalStream` (banco comune:
                    UN solo `SimulatedMiddleware`, tetti di flumine aperti,
                    `simulation_available_prices=False` = fill solo sul volume
                    davvero scambiato, coda rispettata)
      -> `tennis_runner._instantiate_bot` VERO: e' la funzione che il runner di
         produzione usa per armare un bot dal control-row (preset TENNIS_PARAMS
         dello scalper, `dry_run` dalla modalita', tetti di esposizione,
         `_scope_to_market`, carry-over delle stats)
      -> il PUNTEGGIO entra come in produzione: `parse_tennis_scores` (la stessa
         funzione di `score_and_now_worker`) sul sidecar `<id>.score.jsonl`,
         assegnato a `strat.score` / `strat.point_pressure` alla cadenza VERA
         del worker (`TENNIS_SCORE_POLL_SEC`, 2 s di tempo di mercato)
      -> ordini VERI su flumine (`market.place_order`), con il BET DELAY del
         `marketDefinition` streamato (flumine trattiene il pacchetto finche'
         `elapsed > place_latency + betDelay`, `orderpackage.py:73-77`) e la
         `place_latency` del PAPER TENNIS di produzione
         (`TENNIS_PAPER_LATENCY_MS`, 600 ms)
      -> lo SPECCHIO vero: `tennis_live_order_worker._mirror_order` e
         `_position_row` girati sul blotter, cosi' il referto giudica anche le
         righe che la UI vedrebbe (§6.5)

-----------------------------------------------------------------------------
TRE DICHIARAZIONI, perche' un banco che non le fa e' peggio di nessun banco
-----------------------------------------------------------------------------

1. IL CATALOGO NON C'E'. Nel raw dello stream non esistono i NOMI dei runner
   (`marketDefinition.runners` porta solo `id` e `sortPriority`): in produzione
   i nomi arrivano da `listMarketCatalogue` (`tennis_runner._resolve_market` ->
   `name_to_sel`). `tennis_pro` ne ha BISOGNO per mappare il punteggio IPS sulla
   selezione: senza, `_sel_of` non trova nessuno e il bot non apre MAI. Qui la
   mappa si DICHIARA: `--nomi` esplicito, oppure la cache `_names.json` che i
   grid runner scrivono accanto alle registrazioni (`lab_grid_score.py:86-118`).
   Lo scenario `catalogo-assente` mostra che cosa succede senza.

2. IL PUNTEGGIO HA L'OROLOGIO DEL POLL, NON DEL MERCATO. Il sidecar `.score.jsonl`
   timbra ogni riga con `time.time()` LOCALE al momento del poll IPS
   (`tennis_score.py:260-262`), mentre i book portano il `publish_time` di
   Betfair: fra i due c'e' la latenza HTTP dell'IPS piu' l'intervallo di poll
   (2 s). Qui i punteggi entrano confrontando quei due orologi, ed e' la stessa
   approssimazione dichiarata da `backtest_pro.py:73-74`: le condizioni dei bot
   valgono su scala set/game/servizio, non per il micro-timing sub-secondo.

3. IL CICLO DI VITA DEGLI ORDINI E' DI FLUMINE, NON NOSTRO. Il bot chiama
   `market.place_order`, che in flumine e' ASINCRONA: il pacchetto entra in
   `handler_queue` e viene eseguito quando l'orologio di mercato ha superato
   `place_latency + betDelay`. E' esattamente cio' che succede in produzione
   (il bot non si blocca sulla REST: e' il `OrderStream` a portargli l'esito),
   quindi qui NON si usa `MercatoFlumine.attendi_esecuzione` — si lascia fare
   a `MotoreReplay._a_flumine`, che chiama `_check_pending_packages` a ogni book
   come fa `FlumineSimulation.run`.

Uso:
    python -m Betfair.stream.backtest.certifica tennis_flb 35794049
    python -m Betfair.stream.backtest.certifica tennis_flb 35794049 --scenari tutti
    python -m Betfair.stream.tennis_live.tools.replay_bot tennis_flb 35794049

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import os
import sys
from bisect import bisect_right
from contextlib import contextmanager
from typing import Any, Callable, Dict, List, Optional, Tuple

from .. import certificazione_bot as CERT
from ...backtest import chiusura_parziale as CP
from ..tennis_recorder import default_record_dir

logger = logging.getLogger(__name__)

# la registrazione di riferimento: Sinner - Struff, 07/07/2026, COMPLETE 99.1 %,
# 8609 righe di raw, sidecar punteggi presente e `_names.json` col catalogo.
EVENTO_DI_RIFERIMENTO = "35794049"

# i mercati che i quattro bot usano: uno solo, il MATCH_ODDS (dossier §4)
MERCATI = ("MATCH_ODDS",)


# ---------------------------------------------------------------------------
# GLI SCENARI — cambiano SOLO parametri, freschezza del feed o guasti iniettati.
# Mai la partita, mai i prezzi, mai la strategia (PROCESSO_STANDARD_BOT §6.7).
# ---------------------------------------------------------------------------
SCENARI_DESCRITTI: Dict[str, str] = {
    "base": "come gira in produzione: i parametri del preset, modalita' paper",
    "gate-aperto": (
        "SOLO le soglie di liquidita' e di banda allargate, per sollecitare i "
        "controlli su una partita in cui i default non entrano mai. La "
        "STRATEGIA non cambia: cambiano i numeri che l'utente puo' gia' "
        "cambiare dalla UI"),
    "dry-run": "il control chiede dry_run: nessun ordine deve raggiungere il mercato",
    "bot-fermo": (
        "a meta' partita il runner DISARMA il bot (`_disable_strategy` vero): "
        "le protezioni girano, le aperture no"),
    "rifiuti-betfair": (
        "un controllo di flumine RIFIUTA ogni piazzamento (`place_order` torna "
        "False, stato `Violation`): provoca il difetto 2 del catalogo, `res.ok` "
        "mai letto. Porta con se' i gate aperti di `gate-aperto`, altrimenti i "
        "bot che non tentano nessun ingresso non verrebbero mai rifiutati"),
    "feed-stantio": (
        "il punteggio smette di arrivare dopo il primo terzo della partita: "
        "`strat.score` resta quello vecchio, come in un blackout IPS"),
    "parziali": (
        "SOLO lo stake alzato: l'ordine non trova abbastanza coda e si abbina "
        "in parte, cosi' residuo e prezzo medio hanno un caso"),
    "riavvio": (
        "RIAVVIO A META' PARTITA, come lo fa il runner: a meta' si chiede il "
        "restart del framework e lo si concede SOLO a bot flat "
        "(`tennis_runner._strategy_is_flat`, il blotter e' l'unica fonte); poi "
        "il bot viene RI-ISTANZIATO con `_instantiate_bot` e il carry-over "
        "delle stats, esattamente come al rebuild dello stream"),
    "catalogo-assente": (
        "la mappa dei nomi NON viene dichiarata (limite 1 del banco): mostra "
        "che cosa perde `tennis_pro` senza `listMarketCatalogue`"),
    "live": (
        "la stessa partita in modalita' LIVE, col `dry_run` tolto come lo "
        "toglierebbe l'utente: gli ordini restano simulati da flumine (il banco "
        "gira su `FlumineSimulation`), ma i parametri sono quelli del percorso "
        "live — minimi e granularita' .it compresi — cosi' la blindatura di "
        "giurisdizione e' davvero verificata e la parita' paper/live misurabile"),
    # 23/09 (cancello C3): i gate di `gate-aperto` (senza, scalper e swing non
    # aprono mai su queste partite e non esisterebbe una chiusura da colpire)
    # piu' il guasto del banco comune.
    CP.SCENARIO: "i gate di `gate-aperto`, ma " + CP.DESCRIZIONE,
}


def parametri_scenario(scenario: str, bot: str) -> Dict[str, Any]:
    """I parametri che lo scenario cambia. SOLO numeri gia' esposti dalla UI."""
    if scenario in ("rifiuti-betfair", "live", CP.SCENARIO):
        # ⚠️ IL CASO VA PROVOCATO, non sperato. Con i parametri di produzione
        # lo scalper e lo swing non tentano MAI un ingresso su questa partita:
        # il rifiuto non sarebbe nemmeno possibile e K2 resterebbe «non lo so»
        # proprio nello scenario che esiste per sollecitarlo; e senza nessun
        # ordine il percorso LIVE non esisterebbe, cioe' B8 — la blindatura dei
        # minimi .it, che e' money-critical — non verrebbe mai verificata
        # (§6.7). Si aprono percio' gli stessi gate di `gate-aperto`, e lo si
        # dichiara nel referto.
        return parametri_scenario("gate-aperto", bot)
    if scenario == "gate-aperto":
        # le soglie di liquidita' e le bande: sono i `min_matched` / `price_*`
        # che il dossier §4 elenca come parametri del bot, non regole.
        comuni = {"min_matched": 0.0, "min_total_matched": 0.0}
        per_bot = {
            # ⚠️ `inplay_tick_enabled` e' un parametro della MISSIONE dello
            # scalper (`one_tick_per_phase`, preset `TENNIS_PARAMS` del runner
            # standalone, esposto nella scheda del bot in
            # `frontend/src/lib/tennis.ts`): col default di produzione
            # (`one_tick_per_phase=True`, `inplay_tick_enabled=False`) un bot
            # armato su una partita GIA' IN-PLAY non apre MAI nulla e non lo
            # dice (difetto D13 del referto d'audit). Qui si apre per poter
            # sollecitare i controlli; e' un numero della UI, non una regola.
            "tennis_scalper": {"min_size": 0.0, "price_min": 1.01,
                               "price_max": 30.0, "min_flow": 0.0,
                               "warmup_ms": 0, "inplay_tick_enabled": True,
                               "runner_filter": "all"},
            "tennis_pro": {"min_book_size": 0.0, "price_min": 1.01,
                           "price_max": 30.0},
            "tennis_flb": {"min_lay_size": 0.0, "lay_max": 1.30},
            "tennis_swing": {"price_min": 1.01, "price_max": 30.0,
                             "zin": 1.0, "er_max": 1.0, "conf_ticks": 1},
        }
        out = dict(comuni)
        out.update(per_bot.get(bot, {}))
        return out
    if scenario == "parziali":
        # stake molto alto: la coda davanti non basta e l'ordine si abbina in
        # parte. Si cambia UN numero, quello che l'utente sceglie dalla UI.
        return {"stake": 400.0}
    return {}


def credenze_cp(cred: List[Dict[str, Any]],
                specchio: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Le credenze del bot tennis nella forma dei controlli CP.

    CHIUSA = lo stato che il bot dichiara chiuso (`STATI_CREDUTI_CHIUSI`, i nomi
    VERI dei quattro bot). I numeri di ogni uscita sono quelli della riga che la
    UI vedrebbe (`tennis_live_orders`, costruita da `_mirror_order` vero: chiave
    `average_price_matched`, non `avg_price_matched`). In coda una voce con TUTTE
    le righe dello specchio: un'uscita che il bot ha gia' smesso di seguire deve
    restare riconoscibile per CP1 (mai chiusa, mai coperta: CP2/CP3 la saltano).
    """
    per_id = {str(r.get("order_id") or ""): r for r in specchio or []}

    def _riga(o: Any) -> Dict[str, Any]:
        r = per_id.get(str(getattr(o, "id", "") or "")) or {}
        return {"ordine_id": str(getattr(o, "id", "") or ""), "bet_id": r.get("bet_id"),
                "size": r.get("size"), "price": r.get("price"),
                "status": r.get("status"),
                "size_matched": r.get("size_matched") if r else None,
                "size_remaining": r.get("size_remaining") if r else None,
                "avg_price_matched": r.get("average_price_matched") if r else None}

    out: List[Dict[str, Any]] = []
    for c in cred or []:
        out.append({
            "id": "%s%s" % (c.get("stato"), c.get("chiave")),
            "chiave": tuple(c.get("chiave") or ()),
            "chiusa": str(c.get("stato") or "") in CERT.STATI_CREDUTI_CHIUSI,
            "coperto": None, "apertura": None, "ingressi": [],
            "chiusure": [_riga(o) for o in (c.get("uscite") or ())],
            "per_selezione": True,
            "tolleranza": float(c.get("tolleranza") or 0.0),
        })
    out.append({
        "id": "specchio", "chiave": (), "chiusa": False, "coperto": None,
        "apertura": None, "ingressi": [],
        "chiusure": [{"ordine_id": str(r.get("order_id") or ""), "bet_id": r.get("bet_id"),
                      "size": r.get("size"), "price": r.get("price"),
                      "status": r.get("status"),
                      "size_matched": r.get("size_matched"),
                      "size_remaining": r.get("size_remaining"),
                      "avg_price_matched": r.get("average_price_matched")}
                     for r in specchio or []],
        "per_selezione": True, "tolleranza": 0.0,
    })
    return out


def stake_scenario(scenario: str, stake: float) -> float:
    return 400.0 if scenario == "parziali" else stake


def modalita_scenario(scenario: str) -> str:
    return "LIVE" if scenario == "live" else "PAPER"


def dry_run_scenario(scenario: str) -> Optional[bool]:
    """`None` = il default della modalita' (come `_instantiate_bot`).

    ⚠️ Lo scenario `live` DICHIARA `dry_run=False`. In LIVE `_instantiate_bot`
    fa nascere il bot in dry-run per prudenza sui soldi veri, e l'utente deve
    toglierlo a mano dalla scheda: col default, nel replay, il percorso LIVE non
    piazzava NIENTE e il controllo B8 (i minimi .it) restava «non lo so» — cioe'
    proprio la blindatura money-critical non era mai verificata. Qui i soldi veri
    non esistono comunque: il banco gira su `FlumineSimulation` e ogni ordine e'
    simulato, qualunque cosa dica la modalita'.
    """
    if scenario == "dry-run":
        return True
    if scenario == "live":
        return False
    return None


# ---------------------------------------------------------------------------
# il processo: le cache di modulo si azzerano da un elenco ESPLICITO
# ---------------------------------------------------------------------------
# ⚠️ catalogo §7 punto 37: una cache di modulo sopravvissuta fra scenari nello
# stesso figlio della pool sotto-sollecita i controlli. Qui si azzera un elenco
# NOMINATO (mai un `dir()` che svuota «tutto» e porta via anche cio' che serve).
_DA_AZZERARE: Tuple[Tuple[str, str], ...] = (
    ("Betfair.stream.tennis_live.tennis_runner", "_INSTANCE_LOCK"),
)


def _azzera_stato_di_processo() -> List[str]:
    fatti: List[str] = []
    for modulo, nome in _DA_AZZERARE:
        mod = sys.modules.get(modulo)
        if mod is None or not hasattr(mod, nome):
            continue
        setattr(mod, nome, None)
        fatti.append("%s.%s" % (modulo, nome))
    return fatti


@contextmanager
def _modalita_dichiarata(mode: str):
    """`TENNIS_LIVE_ORDER_MODE` e' di PROCESSO e il runner la rilegge a ogni
    giro: si dichiara per la durata del replay e si rimette com'era. Gli ordini
    restano simulati da flumine in ogni caso: i soldi veri non esistono qui."""
    chiavi = ("TENNIS_LIVE_ORDER_MODE", "TENNIS_PAPER_LATENCY_MS")
    prima = {k: os.environ.get(k) for k in chiavi}
    os.environ["TENNIS_LIVE_ORDER_MODE"] = mode
    try:
        yield
    finally:
        for k, v in prima.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ---------------------------------------------------------------------------
# la registrazione: raw, punteggi, catalogo
# ---------------------------------------------------------------------------
def cartella_predefinita() -> str:
    """La RADICE delle registrazioni tennis, la stessa del recorder di
    produzione (`tennis_recorder.default_record_dir`), col giorno piu' recente."""
    radice = default_record_dir()
    giorni = []
    if os.path.isdir(radice):
        giorni = sorted(d for d in os.listdir(radice) if d.isdigit())
    return os.path.join(radice, giorni[-1]) if giorni else radice


def percorsi(data_dir: str, event_id: str) -> Tuple[str, str]:
    base = os.path.join(data_dir, str(event_id))
    return (os.path.join(base, "%s.raw.jsonl" % event_id),
            os.path.join(base, "%s.score.jsonl" % event_id))


def mercato_dal_raw(raw: str) -> Tuple[Optional[str], Dict[int, int]]:
    """market_id del MATCH_ODDS e {selection_id: sortPriority}, dal raw.

    ⚠️ i NOMI non ci sono: `marketDefinition.runners` porta `id`,
    `sortPriority` e `status`, mai `name`. E' il limite 1 dichiarato in testa.
    """
    with io.open(raw, "r", encoding="utf-8") as f:
        for riga in f:
            try:
                d = json.loads(riga)
            except ValueError:
                continue
            for mc in d.get("mc") or []:
                md = mc.get("marketDefinition")
                if not md or md.get("marketType") != "MATCH_ODDS":
                    continue
                ordine = {int(r["id"]): int(r.get("sortPriority") or 0)
                          for r in (md.get("runners") or []) if r.get("id")}
                return str(mc.get("id")), ordine
    return None, {}


def carica_punteggi(score: str) -> List[Tuple[int, Dict[str, Any]]]:
    """(epoch_ms del poll, stato IPS grezzo) dal sidecar tennis, ordinati.

    Il formato e' quello che scrive `tennis_score.py:260-262`:
    `{"t": <epoch secondi locali>, "score": <stato IPS grezzo>}`.
    """
    out: List[Tuple[int, Dict[str, Any]]] = []
    if not os.path.exists(score):
        return out
    with io.open(score, "r", encoding="utf-8") as f:
        for riga in f:
            try:
                d = json.loads(riga)
            except ValueError:
                continue
            t = d.get("t")
            st = d.get("score")
            if t is None or st is None:
                continue
            try:
                out.append((int(float(t) * 1000.0), st))
            except (TypeError, ValueError):
                continue
    out.sort(key=lambda x: x[0])
    return out


def catalogo_dichiarato(data_dir: str, event_id: str,
                        nomi: Optional[str] = None) -> Dict[str, int]:
    """La mappa `{nome_runner: selection_id}` che in produzione porta
    `listMarketCatalogue` e che il raw NON contiene (limite 1).

    Fonti, in ordine: `--nomi "Nome=selid,Nome=selid"`, poi la cache
    `_names.json` che i grid runner scrivono accanto alle registrazioni.
    """
    if nomi:
        out: Dict[str, int] = {}
        for pezzo in str(nomi).split(","):
            if "=" not in pezzo:
                continue
            k, _, v = pezzo.partition("=")
            try:
                out[k.strip()] = int(v.strip())
            except ValueError:
                continue
        return out
    cache = os.path.join(data_dir, "_names.json")
    if not os.path.exists(cache):
        return {}
    try:
        with io.open(cache, "r", encoding="utf-8") as f:
            tutto = json.load(f)
    except (ValueError, OSError):
        return {}
    per_evento = (tutto or {}).get(str(event_id)) or {}
    out = {}
    for sel, nome in per_evento.items():
        try:
            out[str(nome)] = int(sel)
        except (TypeError, ValueError):
            continue
    return out


def qualita_registrazione(data_dir: str, event_id: str) -> str:
    try:
        from ...tools.validate_recordings import validate_event

        rep = validate_event(data_dir, str(event_id))
        buchi = len(getattr(rep, "gaps_in_window", None) or [])
        return "%s %s%% (%d buchi dichiarati)" % (
            rep.verdict, rep.coverage_pct, buchi)
    except Exception as ex:  # noqa: BLE001 - il verdetto e' un di piu', non un gate
        return "ignota (%s)" % type(ex).__name__


def impronta() -> Dict[str, str]:
    """Versioni e IMPRONTA del codice dei bot: un referto che non si puo' rifare
    identico non e' un referto, e' un ricordo (§6.8)."""
    import betfairlightweight
    import flumine

    sorgenti = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "tennis_scalper", nome)
        for nome in ("tennis_scalper_bot.py", "tennis_pro_bot.py",
                     "tennis_flb_bot.py", "tennis_swing_bot.py")
    ]
    sorgenti.append(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "tennis_runner.py"))
    h = hashlib.sha256()
    for percorso in sorgenti:
        try:
            with io.open(percorso, "rb") as f:
                h.update(f.read())
        except OSError:
            h.update(b"?")
    return {
        "flumine": getattr(flumine, "__version__", "?"),
        "betfairlightweight": getattr(betfairlightweight, "__version__", "?"),
        "codice_bot": h.hexdigest()[:12],
    }


# ---------------------------------------------------------------------------
# IL GUASTO INIETTATO: Betfair rifiuta
# ---------------------------------------------------------------------------
def _rifiuta_tutto(quadro: Any):
    """Un trading control di flumine che RIFIUTA ogni piazzamento.

    E' la via di produzione del rifiuto, non un finto: si eredita da
    `flumine.controls.BaseControl`, e il suo `_on_error` chiama
    `order.violation(...)` (stato -> `OrderStatus.VIOLATION`) e alza
    `ControlError`; `Transaction._validate_controls` la cattura e
    `place_order` torna **False senza piazzare**
    (`flumine/execution/transaction.py:67-75, 230-242`). Il bot vede
    esattamente cio' che vedrebbe con un rifiuto vero di Betfair.
    """
    from flumine.controls import BaseControl
    from flumine.order.orderpackage import OrderPackageType

    class _RifiutaTutto(BaseControl):
        NAME = "REPLAY_RIFIUTA_TUTTO"

        def __init__(self, flumine: Any) -> None:
            super().__init__(flumine)
            self.rifiutati: List[str] = []

        def _validate(self, order: Any, package_type: Any) -> None:
            if package_type != OrderPackageType.PLACE:
                return
            self.rifiutati.append(str(getattr(order, "id", "") or ""))
            self._on_error(order, "rifiuto iniettato dal replay")

    return _RifiutaTutto(quadro)


# ---------------------------------------------------------------------------
# IL PONTE: fa girare i WORKER di produzione alla loro cadenza vera
# ---------------------------------------------------------------------------
class _Ponte:
    """Sta fra `MotoreReplay` e il BOT DI PRODUZIONE, e non decide niente.

    Fa quello che in produzione fanno i `BackgroundWorker` del runner, alla
    LORO cadenza (tempo di mercato, non tempo reale):

      * `score_and_now_worker` (2 s): legge il punteggio col parser VERO e
        scrive `strat.score` / `strat.point_pressure` esattamente come
        `tennis_runner.py:1060-1070`;
      * `bot_control_worker` (3 s): lo scenario `bot-fermo` chiama il
        `_disable_strategy` VERO del runner;
      * `tennis_live_order_worker` (1 s): lo specchio degli ordini dal blotter,
        con le funzioni VERE `_mirror_order` / `_position_row`;
      * il giro dei CONTROLLI: una `Osservazione` per giro.

    Il bot lo si chiama tale e quale: `check_market_book` e
    `process_market_book` sono i suoi, e lo scoping per mercato lo ha gia'
    messo `_instantiate_bot` con `_scope_to_market`.
    """

    def __init__(self, *, strat: Any, bot_key: str, event_id: str,
                 market_id: str, scenario: str, punteggi: List[Tuple[int, Dict[str, Any]]],
                 referto: CERT.Referto, quadro: Any, modalita: str,
                 stake: float, cap: Optional[float], attivita: List[Tuple[str, Dict[str, Any]]],
                 rifiuta: Optional[Any], ogni_ms: int,
                 feed_stantio_da_ms: Optional[int] = None,
                 riavvia: Optional[Callable[[Any], Any]] = None) -> None:
        from ..tennis_runner import SCORE_POLL_SEC

        self.s = strat
        self.bot_key = bot_key
        self.event_id = str(event_id)
        self.market_id = str(market_id)
        self.scenario = scenario
        self.punteggi = punteggi
        self.ts_punteggi = [t for t, _ in punteggi]
        self.ref = referto
        self.quadro = quadro
        self.modalita = modalita
        self.stake = stake
        self.cap = cap
        self.attivita = attivita
        self.rifiuta = rifiuta
        self.ogni_ms = max(0, int(ogni_ms))
        self.feed_stantio_da_ms = feed_stantio_da_ms
        self.riavvia = riavvia
        self._riavviato = False
        self.cadenza_punteggio_ms = int(float(SCORE_POLL_SEC or 2.0) * 1000)
        self._ultimo_punteggio_ms = 0
        self._ultimo_controllo_ms = 0
        self._i_punteggio = 0
        self._disabilitato = False
        # gli id degli ordini gia' visti a mercato: cio' che compare adesso e'
        # NUOVO, e solo su quello si giudica «il bot ha chiesto un ordine ora»
        self._ordini_visti: set = set()
        self._meta_ms: Optional[int] = None
        self._fine_ms: Optional[int] = None
        self._ultimo_book: Any = None
        # scenario `chiusura-abbinata-in-parte` (None negli altri)
        self.sorveglianza_cp: Optional[Any] = None

    def ruolo_ordine(self, ordine: Any) -> Optional[str]:
        """Il RUOLO di un ordine per il guasto CP, dalla credenza VERA del bot
        (`credenze`: ingressi e uscite che il bot sta seguendo)."""
        for c in CERT.credenze(self.s, self.bot_key):
            if any(x is ordine for x in (c.get("uscite") or ())):
                return "uscita"
            if any(x is ordine for x in (c.get("ingressi") or ())):
                return "ingresso"
        return None

    # ------------------------------------------------------------- contratto
    @property
    def stream_ids(self) -> Any:
        return self.s.stream_ids

    def process_new_market(self, market: Any, market_book: Any) -> None:
        self.s.process_new_market(market, market_book)

    def check_market_book(self, market: Any, market_book: Any) -> bool:
        self._ultimo_book = market_book
        self.ref.tick += 1
        pt = getattr(market_book, "publish_time", None)
        ms = int(pt.timestamp() * 1000) if pt is not None else 0
        self._forse_punteggio(ms)
        self._forse_disarmo(market, ms)
        self._forse_riavvio(market, ms)
        return bool(self.s.check_market_book(market, market_book))

    def process_market_book(self, market: Any, market_book: Any) -> None:
        pt = getattr(market_book, "publish_time", None)
        ms = int(pt.timestamp() * 1000) if pt is not None else 0
        prima = len(self.attivita)
        self.s.process_market_book(market, market_book)
        self.ref.decisioni += 1
        self.ref.azioni += len(self.attivita) - prima
        if self.ogni_ms and (ms - self._ultimo_controllo_ms) < self.ogni_ms:
            return
        self._ultimo_controllo_ms = ms
        self.giro(market, market_book, prima)

    # --------------------------------------------------------------- worker
    def _forse_punteggio(self, ms: int) -> None:
        """`score_and_now_worker` alla cadenza vera (2 s di tempo di mercato)."""
        if not self.punteggi or ms <= 0:
            return
        if ms - self._ultimo_punteggio_ms < self.cadenza_punteggio_ms:
            return
        self._ultimo_punteggio_ms = ms
        if (self.feed_stantio_da_ms is not None and ms >= self.feed_stantio_da_ms):
            # blackout IPS: il worker esce senza toccare `strat.score` — e' il
            # comportamento VERO (`tennis_runner.py:1057-1058`: l'eccezione e'
            # loggata e il punteggio resta quello di prima).
            return
        from ...tennis_scalper.tennis_score import parse_tennis_scores

        i = bisect_right(self.ts_punteggi, ms)
        if i <= self._i_punteggio:
            return
        self._i_punteggio = i
        grezzo = self.punteggi[i - 1][1]
        try:
            ts = parse_tennis_scores([grezzo], self.event_id)
        except Exception as ex:  # noqa: BLE001 - il feed non rompe il replay
            logger.debug("punteggio illeggibile: %s", ex)
            return
        # ESATTAMENTE come tennis_runner.py:1060-1070
        if hasattr(self.s, "score"):
            self.s.score = ts
        if hasattr(self.s, "point_pressure") and ts is not None:
            self.s.point_pressure = bool(ts.point_pressure)

    def _forse_disarmo(self, market: Any, ms: int) -> None:
        """Lo scenario `bot-fermo`: a meta' partita il runner disarma davvero."""
        if self.scenario != "bot-fermo" or self._disabilitato:
            return
        if self._meta_ms is None or ms < self._meta_ms:
            return
        from ..tennis_runner import _disable_strategy

        _disable_strategy(self.s)
        self._disabilitato = True
        self.ref.note.append(
            "bot DISARMATO a meta' partita con `_disable_strategy` di produzione")

    def _forse_riavvio(self, market: Any, ms: int) -> None:
        """Lo scenario `riavvio`: il runner ricostruisce lo stream a meta' partita.

        LA REGOLA E' QUELLA DI PRODUZIONE, non una nostra: `_request_restart`
        (`tennis_runner.py:816-...`) concede il restart SOLO se ogni bot ospitato
        e' FLAT secondo `_strategy_is_flat`, che legge il blotter e in caso di
        dubbio risponde «non flat». Con una posizione aperta il restart si
        RINVIA al giro dopo, perche' il rebuild azzererebbe il blotter e la
        posizione resterebbe orfana. Qui si fa esattamente questo: si prova a
        ogni giro dal punto di meta' partita, e quando il bot e' flat lo si
        ri-istanzia con `_instantiate_bot` (carry-over delle stats compreso).
        """
        if self.riavvia is None or self._riavviato:
            return
        if self._meta_ms is None or ms < self._meta_ms:
            return
        from ..tennis_runner import _disable_strategy, _strategy_is_flat

        if not _strategy_is_flat(self.quadro, self.s):
            return              # rinviato, come in produzione
        vecchio = self.s
        nuovo = self.riavvia(vecchio)
        if nuovo is None:
            return
        _disable_strategy(vecchio)
        self.s = nuovo
        self._riavviato = True
        self.ref.note.append(
            "RIAVVIO a meta' partita concesso a bot FLAT (regola di produzione "
            "`_request_restart`): il bot e' stato ri-istanziato con "
            "`_instantiate_bot` e il blotter nuovo e' vuoto, come dopo un "
            "rebuild dello stream")

    def imposta_finestra(self, primo_ms: int, ultimo_ms: int) -> None:
        self._meta_ms = primo_ms + (ultimo_ms - primo_ms) // 2
        self._fine_ms = ultimo_ms

    # ------------------------------------------------------------ i controlli
    def ordini_del_bot(self, market: Any) -> List[Any]:
        blotter = getattr(market, "blotter", None)
        if blotter is None:
            return []
        try:
            return list(blotter.strategy_orders(self.s) or [])
        except Exception:  # noqa: BLE001 - blotter illeggibile: nessun ordine
            return []

    def esposizioni(self, market: Any, ordini: List[Any]) -> Dict[Any, Dict[str, float]]:
        """L'esposizione per selezione dalla funzione VERA del worker ordini
        (`_position_row`): mai numeri ricalcolati a mano."""
        from ..tennis_live_order_worker import _position_row

        out: Dict[Any, Dict[str, float]] = {}
        viste = set()
        for o in ordini:
            sel = getattr(o, "selection_id", None)
            if sel is None:
                continue
            chiave = (int(sel), float(getattr(o, "handicap", 0.0) or 0.0))
            if chiave in viste:
                continue
            viste.add(chiave)
            riga = _position_row(market, self.s, self.modalita.lower(),
                                 self.event_id, self.market_id, int(sel), chiave[1])
            if riga:
                out[chiave] = riga
        return out

    def specchio(self, ordini: List[Any]) -> List[Dict[str, Any]]:
        """Le righe che `tennis_live_orders` porterebbe, costruite dalla
        funzione VERA dello specchio (`_mirror_order`), catturate invece che
        scritte: il DB qui non esiste, il CONTENUTO si'."""
        from .. import tennis_live_order_worker as OW

        righe: List[Dict[str, Any]] = []
        vero = OW.tennis_db.upsert_tennis_order
        per_ref: Dict[str, Any] = {}

        def _cattura(row: Dict[str, Any]) -> None:
            righe.append(dict(row))

        OW.tennis_db.upsert_tennis_order = _cattura  # type: ignore[assignment]
        try:
            for o in ordini:
                oid = getattr(o, "id", None)
                if oid is None:
                    continue
                ref = ("bot:" + str(oid))[:32]
                per_ref[ref] = oid
                OW._mirror_order(self.modalita.lower(), self.event_id, ref, o, {},
                                 source=self.bot_key)
        finally:
            OW.tennis_db.upsert_tennis_order = vero  # type: ignore[assignment]
        for riga in righe:
            riga["order_id"] = str(per_ref.get(riga.get("client_order_ref"), ""))
        return righe

    def giro(self, market: Any, market_book: Any, prima: int) -> None:
        ordini_veri = self.ordini_del_bot(market)
        specchio = self.specchio(ordini_veri)
        righe = [CERT.riga_ordine(o) for o in ordini_veri]
        cred = CERT.credenze(self.s, self.bot_key)
        ids_ingresso = set()
        for c in cred:
            ids_ingresso |= CERT._ids(c.get("ingressi") or ())
        tutti = {r.get("order_id") for r in righe}
        nuovi = tutti - self._ordini_visti
        self._ordini_visti |= tutti
        pt = getattr(market_book, "publish_time", None)
        oss = CERT.Osservazione(
            bot=self.bot_key,
            scenario=self.scenario,
            quando=pt.isoformat() if pt is not None else "",
            modalita=self.modalita.lower(),
            dry_run=bool(getattr(self.s, "dry_run", False)),
            disabilitato=bool(getattr(self.s, "_tennis_disabled", False)),
            inplay=bool(getattr(market_book, "inplay", False)),
            stato_mercato=str(getattr(market_book, "status", "") or ""),
            market_id=self.market_id,
            stake=float(self.stake or 0.0),
            cap_esposizione=self.cap,
            ordini=righe,
            rifiutati=list(self.rifiuta.rifiutati) if self.rifiuta else [],
            credenze=cred,
            attivita=self.attivita[prima:],
            stats=dict(getattr(self.s, "stats", None) or {}),
            specchio=specchio,
            esposizioni=self.esposizioni(market, ordini_veri),
            ids_ingresso=ids_ingresso,
            ordini_nuovi=nuovi,
        )
        self.ref.violazioni.extend(CERT.verifica(oss, self.ref.sollecitati))
        # I CONTROLLI CP (scenario chiusura-abbinata-in-parte)
        if self.sorveglianza_cp is not None:
            for cod, reg, det in self.sorveglianza_cp.verifica(
                    credenze_cp(cred, specchio), self.ref.sollecitati):
                self.ref.violazioni.append(CERT.Violazione(
                    cod, reg, det, oss.quando))
        for c in cred:
            stato = str(c.get("stato") or "")
            if stato and stato not in self.ref.stati_visti:
                self.ref.stati_visti.append(stato)
        self.ref.ordini_piazzati = len(righe)
        self.ref.ordini_abbinati = sum(
            1 for r in righe if (r.get("size_matched") or 0.0) > 0.009)

    def chiudi(self, market: Any) -> None:
        """L'ULTIMO giro, a mercato CHIUSO: e' li' che si misura il P&L (P3)."""
        if market is None:
            return
        ordini_veri = self.ordini_del_bot(market)
        righe = [CERT.riga_ordine(o) for o in ordini_veri]
        cred = CERT.credenze(self.s, self.bot_key)
        oss = CERT.Osservazione(
            bot=self.bot_key, scenario=self.scenario, quando="settlement",
            modalita=self.modalita.lower(),
            dry_run=bool(getattr(self.s, "dry_run", False)),
            disabilitato=bool(getattr(self.s, "_tennis_disabled", False)),
            stato_mercato="CLOSED", market_id=self.market_id,
            stake=float(self.stake or 0.0), cap_esposizione=self.cap,
            ordini=righe, credenze=cred,
            stats=dict(getattr(self.s, "stats", None) or {}),
            specchio=self.specchio(ordini_veri),
        )
        self.ref.violazioni.extend(CERT.verifica(oss, self.ref.sollecitati))
        self.ref.stats_finali = dict(getattr(self.s, "stats", None) or {})


# ---------------------------------------------------------------------------
# IL REPLAY DI UN EVENTO
# ---------------------------------------------------------------------------
def certifica_scenario(event_id: str, *, data_dir: str, scenario: str = "base",
                       ogni_ms: int = 1000, campioni_diff: int = 0,
                       bot: str = "tennis_flb",
                       nomi: Optional[str] = None) -> CERT.Referto:
    """Un evento, uno scenario, un referto. E' il contratto del banco comune."""
    del campioni_diff        # il diff dello scanner non si applica: i bot tennis
    # non passano dalla riga di scan (leggono il MarketBook direttamente)
    from ...backtest import banco_comune as BC

    ref = CERT.Referto(event_id=str(event_id), bot=bot, scenario=scenario)
    azzerate = _azzera_stato_di_processo()
    if azzerate:
        ref.note.append("cache di processo azzerate: %s" % ", ".join(azzerate))

    raw, score = percorsi(data_dir, event_id)
    if not os.path.exists(raw):
        ref.note.append("registrazione assente: %s" % raw)
        return ref
    ref.note.append("qualita' registrazione: %s"
                    % qualita_registrazione(data_dir, event_id))

    market_id, _ordine = mercato_dal_raw(raw)
    if not market_id:
        ref.note.append("nessun MATCH_ODDS nel raw: il bot non ha un mercato")
        return ref

    punteggi = carica_punteggi(score)
    if not punteggi:
        ref.note.append("sidecar punteggi assente: `strat.score` resta None per "
                        "tutta la partita (tennis_pro non aprira' mai)")
    else:
        ref.note.append("punteggi: %d campioni dal sidecar (orologio del poll "
                        "IPS, non del mercato: vedi dichiarazione 2)" % len(punteggi))

    catalogo: Dict[str, int] = {}
    if scenario != "catalogo-assente":
        catalogo = catalogo_dichiarato(data_dir, event_id, nomi)
        if catalogo:
            ref.note.append("catalogo DICHIARATO (il raw non lo contiene): %s"
                            % ", ".join(sorted(catalogo)))
        else:
            ref.note.append("catalogo NON disponibile: ne' --nomi ne' _names.json")
    else:
        ref.note.append("scenario `catalogo-assente`: la mappa dei nomi NON e' "
                        "dichiarata (limite 1 del banco)")

    modalita = modalita_scenario(scenario)
    extra = parametri_scenario(scenario, bot)
    stake = stake_scenario(scenario, 2.0)
    attivita: List[Tuple[str, Dict[str, Any]]] = []

    def _sink(kind: str, payload: Dict[str, Any]) -> None:
        attivita.append((str(kind), dict(payload or {})))

    control: Dict[str, Any] = {
        "event_id": str(event_id), "bot_key": bot, "status": "running",
        "stake": stake, "params": dict(extra), "stats": None,
    }
    dry = dry_run_scenario(scenario)
    if dry is not None:
        control["dry_run"] = dry

    from betfairlightweight.filters import streaming_market_data_filter
    from flumine import FlumineSimulation

    with _modalita_dichiarata(modalita):
        from ..tennis_runner import (
            LADDER_DEPTH, STREAM_FIELDS, TENNIS_PAPER_LATENCY_MS_DEFAULT,
            _instantiate_bot,
        )

        data_filter = streaming_market_data_filter(
            fields=list(STREAM_FIELDS), ladder_levels=LADDER_DEPTH)
        with BC.simulazione_flumine() as fconf:
            # LA LATENZA DI PIAZZAMENTO E' QUELLA DEL PAPER TENNIS DI PRODUZIONE
            # (`build_order_client`: 600 ms di rete/processing NOSTRI). Il
            # betDelay in-play lo aggiunge flumine dal marketDefinition
            # streamato: `simulated_delay = place_latency + bet_delay`.
            lat = float(os.getenv("TENNIS_PAPER_LATENCY_MS",
                                  str(TENNIS_PAPER_LATENCY_MS_DEFAULT)) or 0)
            fconf.place_latency = max(0.0, lat) / 1000.0
            ref.note.append("place_latency %s ms (paper tennis di produzione) + "
                            "betDelay dal marketDefinition, dormito da flumine"
                            % int(lat))
            try:
                strat = _instantiate_bot(bot, control, market_id, catalogo,
                                         _sink, data_filter, modalita,
                                         market_ids=[market_id])
            except Exception as ex:  # noqa: BLE001 - un'istanza che non nasce E' un referto
                ref.note.append("il bot non si e' istanziato: %s: %s"
                                % (type(ex).__name__, ex))
                return ref
            # il market_filter del banco: la registrazione al posto dello stream
            strat.market_filter = {"markets": [raw]}
            cap = getattr(strat, "max_selection_exposure", None)

            quadro = FlumineSimulation(client=BC.cliente_simulato())
            BC.assicura_middleware_simulato(quadro)
            rifiuta: Optional[Any] = None
            if scenario == "rifiuti-betfair":
                rifiuta = _rifiuta_tutto(quadro)
                quadro.trading_controls.append(rifiuta)
                ref.note.append("guasto iniettato: ogni piazzamento e' RIFIUTATO "
                                "da un trading control di flumine (place_order "
                                "torna False, stato Violation)")
            quadro.add_strategy(strat)

            def _riavvia(vecchio: Any) -> Any:
                """Ri-istanzia il bot come fa il rebuild dello stream: stessa
                funzione di produzione, stesso control, carry-over delle stats
                (che `_instantiate_bot` prende da `control['stats']`)."""
                ctrl = dict(control)
                ctrl["stats"] = dict(getattr(vecchio, "stats", None) or {})
                nuovo = _instantiate_bot(bot, ctrl, market_id, catalogo, _sink,
                                         data_filter, modalita,
                                         market_ids=[market_id])
                nuovo.market_filter = {"markets": [raw]}
                quadro.add_strategy(nuovo)
                # lo stream e' lo stesso (stesso market_filter): il ponte deve
                # continuare a vedere gli stessi `stream_ids`
                try:
                    nuovo.stream_ids = set(vecchio.stream_ids)
                except Exception:  # noqa: BLE001 - flumine li ha gia' assegnati
                    pass
                return nuovo

            ponte = _Ponte(
                strat=strat, bot_key=bot, event_id=str(event_id),
                market_id=market_id, scenario=scenario, punteggi=punteggi,
                referto=ref, quadro=quadro, modalita=modalita, stake=stake,
                cap=cap, attivita=attivita, rifiuta=rifiuta, ogni_ms=ogni_ms,
                feed_stantio_da_ms=None,
                riavvia=_riavvia if scenario == "riavvio" else None,
            )
            if punteggi:
                primo, ultimo = punteggi[0][0], punteggi[-1][0]
                ponte.imposta_finestra(primo, ultimo)
                if scenario == "feed-stantio":
                    ponte.feed_stantio_da_ms = primo + (ultimo - primo) // 3
                    ref.note.append("guasto iniettato: il punteggio smette di "
                                    "arrivare dopo il primo terzo (blackout IPS)")

            motore = BC.MotoreReplay(quadro)
            guasto_cp = None
            if scenario == CP.SCENARIO:
                # il RUOLO dell'ordine dalla credenza del bot (ingresso/uscita)
                guasto_cp = CP.GuastoChiusuraParziale(ruolo=ponte.ruolo_ordine)
                motore.guasto_chiusure = guasto_cp
                ponte.sorveglianza_cp = CP.Sorveglianza(guasto_cp)
            motore.esegui(ponte)
            if guasto_cp is not None:
                ref.note.append(guasto_cp.riepilogo())
            ref.note.append(
                "book attesi durante i piazzamenti: %d; lapse al fischio: %d; "
                "lapse alla sospensione: %d"
                % (motore.pompati, motore.lapse_al_fischio,
                   motore.lapse_alla_sospensione))
            mercato = quadro.markets.markets.get(market_id)
            ponte.chiudi(mercato)

    if scenario in ("gate-aperto", "parziali", "rifiuti-betfair", "live", CP.SCENARIO):
        ref.note.append("SCENARIO DICHIARATO: cambiati SOLO i parametri %s "
                        "(numeri che l'utente puo' gia' cambiare dalla UI). La "
                        "strategia e' quella di produzione."
                        % sorted(extra) if extra else "stake")
    if not ref.decisioni:
        ref.note.append("il bot non ha MAI deciso: nessun controllo puo' dire "
                        "«sano», il referto dice «non lo so»")
    return ref


def certifica_evento(event_id: str, *, data_dir: str, scenario: str = "base",
                     ogni_ms: int = 1000, campioni_diff: int = 0,
                     bot: str = "tennis_flb",
                     nomi: Optional[str] = None) -> CERT.Referto:
    """Alias: `certifica.py` chiama `certifica_scenario`, il resto del repo
    chiama `certifica_evento`. Sono la stessa cosa."""
    return certifica_scenario(event_id, data_dir=data_dir, scenario=scenario,
                              ogni_ms=ogni_ms, campioni_diff=campioni_diff,
                              bot=bot, nomi=nomi)


# ---------------------------------------------------------------------------
# le quattro entrate del registro: una per bot (la firma del banco e' fissa)
# ---------------------------------------------------------------------------
def _per_bot(bot: str):
    def _f(event_id: str, *, data_dir: str, scenario: str = "base",
           ogni_ms: int = 1000, campioni_diff: int = 0) -> CERT.Referto:
        return certifica_scenario(event_id, data_dir=data_dir, scenario=scenario,
                                  ogni_ms=ogni_ms, campioni_diff=campioni_diff,
                                  bot=bot)
    _f.__name__ = "certifica_scenario_%s" % bot
    _f.__doc__ = ("Il replay di `%s` su UN evento registrato: firma del banco "
                  "comune (`MODELLO_BOT_NUOVO.md` passo 2)." % bot)
    return _f


certifica_scenario_tennis_scalper = _per_bot("tennis_scalper")
certifica_scenario_tennis_pro = _per_bot("tennis_pro")
certifica_scenario_tennis_flb = _per_bot("tennis_flb")
certifica_scenario_tennis_swing = _per_bot("tennis_swing")


# ---------------------------------------------------------------------------
# il comando
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Replay di un bot tennis sulle registrazioni reali")
    p.add_argument("bot", choices=sorted(
        ("tennis_scalper", "tennis_pro", "tennis_flb", "tennis_swing")))
    p.add_argument("eventi", nargs="*", default=[EVENTO_DI_RIFERIMENTO])
    p.add_argument("--data-dir", default=None)
    p.add_argument("--scenari", default="base")
    p.add_argument("--ogni-ms", type=int, default=1000)
    p.add_argument("--nomi", default=None,
                   help="catalogo dichiarato: \"Nome=selid,Nome=selid\"")
    a = p.parse_args(argv)

    logging.basicConfig(level=logging.WARNING)
    data_dir = a.data_dir or cartella_predefinita()
    eventi = a.eventi or [EVENTO_DI_RIFERIMENTO]
    scelti = (list(SCENARI_DESCRITTI) if a.scenari.strip().lower() == "tutti"
              else [x.strip() for x in a.scenari.split(",") if x.strip()])
    imp = impronta()
    print("BOT: %s | flumine %s | betfairlightweight %s | codice bot %s"
          % (a.bot, imp["flumine"], imp["betfairlightweight"], imp["codice_bot"]))
    sollecitati: Dict[str, int] = {}
    tot = 0
    for sc in scelti:
        for ev in eventi:
            r = certifica_scenario(ev, data_dir=data_dir, scenario=sc,
                                   ogni_ms=a.ogni_ms, bot=a.bot, nomi=a.nomi)
            tot += len(r.violazioni)
            for cod, n in r.sollecitati.items():
                sollecitati[cod] = sollecitati.get(cod, 0) + n
            print("%s %s [%s]  tick=%d decisioni=%d azioni=%d ordini=%d "
                  "abbinati=%d stati=%s"
                  % ("OK " if r.pulita else "KO ", ev, sc, r.tick, r.decisioni,
                     r.azioni, r.ordini_piazzati, r.ordini_abbinati,
                     ",".join(r.stati_visti) or "-"))
            for nota in r.note:
                print("      nota: %s" % nota)
            for cod, n in sorted(r.per_codice().items()):
                esempio = next(v for v in r.violazioni if v.codice == cod)
                print("      %s x%d: %s" % (cod, n, esempio.regola))
                print("           es. %s" % esempio.dettaglio)
            if r.stats_finali:
                print("      stats finali: %s" % r.stats_finali)
    print()
    print("COPERTURA DEI CONTROLLI:")
    for cod, reg in CERT.elenco_controlli():
        n = sollecitati.get(cod, 0)
        print("  %s %-3s x%-7d %s" % ("  " if n else "??", cod, n, reg[:66]))
    mai = CERT.mai_sollecitati(sollecitati)
    if mai:
        print()
        print("?? MAI SOLLECITATI: %d su %d. Su questi il referto dice «non lo so»:"
              % (len(mai), len(CERT.elenco_controlli())))
        for cod, reg in mai:
            print("     %s: %s" % (cod, reg))
    return 0 if tot == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
