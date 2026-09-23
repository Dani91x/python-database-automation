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
  * la riga     : **LO SCANNER VERO**. Dal 16/09 il payload di
                  `safe_strategy_scan` NON si scrive piu' a mano qui dentro: i
                  MarketBook di flumine entrano in
                  `safe_strategy.service.Scanner._apply_market_book` (la stessa
                  funzione con cui lo scanner applica i book dello stream) e la
                  riga la produce `Scanner.build_rows`, che e' la funzione che
                  scrive davvero la tabella. Il banco comune
                  (`Betfair/stream/backtest/banco_comune.py`) tiene la tabella
                  in memoria col suo write-on-change e il suo throttle, e Mike
                  ci legge sopra come farebbe dal DB. Il payload scritto a mano
                  resta solo come STRUMENTO DI CONFRONTO (`--diff`);
  * la lettura  : il payload passa dal `feed.py` VERO di Mike
                  (`event_info` + `snapshot_from_row`). **Questo e' il punto.**
                  Costruire lo `Snapshot` a mano qui dentro avrebbe voluto dire
                  scrivere l'ennesimo finto che parla una lingua diversa dal
                  vero — la causa di tutti e cinque i difetti del 15/09. Cosi'
                  invece si certifica anche il feed;
  * i punteggi  : il sidecar `<id>.scores.jsonl` porta il RECORD IPS GREZZO, che
                  entra da `Scanner.apply_score_state`, cioe' dalla stessa
                  funzione che usa `poll_scores` in produzione;
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

import logging
import os
import sys
from bisect import bisect_right
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .. import certificazione as CERT
from .. import config as C
from .. import engine as E
from .. import service as S
from ...stream.backtest import banco_comune as BANCO
from ...stream.backtest import chiusura_parziale as CP
from ...stream.backtest.banco_comune import (
    DbMemoria, MercatoFlumine, MotoreReplay, ScannerReplay,
    assicura_middleware_simulato, carica_punteggi, cliente_simulato,
    nomi_dal_punteggio, simulazione_flumine,
)
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
    # 17/09 (reperto 25): la copertura sotto minimo rifiutata SEMPRE. Il freno
    # si tara a 1 rifiuto perche' su una registrazione la copertura si tenta
    # poche volte: con il default (3) il controllo S1 non avrebbe MAI un caso e
    # il referto direbbe "non lo so" invece di "sano". Non e' un cambio di
    # strategia: e' la stessa taratura di `cap-stretto`, che stringe il tetto
    # per far parlare il clamp.
    # 17/09 (reperto 25). Due tarature, dichiarate:
    #  * ``stake`` 3,00 invece di 10: la copertura si dimensiona
    #    X = factor*S/((Po-1)(1-c)) e con 10 EUR di stake finisce SOPRA il minimo
    #    .it, quindi il caso del 17/09 (copertura SOTTO minimo) non capiterebbe
    #    mai sulla registrazione e il controllo S1 non avrebbe niente da
    #    guardare. Con 3,00 la copertura e' sotto-minima, come quel giorno.
    #  * ``cover_rifiuti_max`` 1 invece di 3: su una registrazione la copertura
    #    si tenta poche volte; col default il freno non scatterebbe mai.
    # Stessa natura della taratura di ``cap-stretto``: si stringe per far parlare
    # una guardia, non si cambia la strategia.
    "copertura-rifiutata": {"cover_rifiuti_max": 1, "stake": 3.00},
    # bot fermo / stop giornaliero: nessuna apertura, le chiusure restano (§5)
    "bot-fermo": {"pre_enabled": False, "reentry_enabled": False},
    # seconda puntata spenta: l'altro ramo del gol precoce (§15.3)
    "senza-seconda-puntata": {"second_entry_enabled": False},
    # GOL PRECOCE (16/09, §15.6): NON tocca un solo parametro — e' `base`, e
    # deve restarlo. Quello che cambia e' la REGISTRAZIONE su cui va lanciato:
    # una partita con un gol nei primissimi minuti (35777617 = 2', 36006953 =
    # 4', 35760084 = 7'). E' l'unico modo di far accadere davvero la catena che
    # l'utente ha ordinato di gestire: il mercato si sospende per il gol,
    # Betfair fa SCADERE (LAPSE) la lay di uscita appoggiata, e alla riapertura
    # il bot deve RILEGGERE l'ordine invece di darlo per vivo (controllo R1).
    # Su una registrazione senza gol precoce quella catena non capita mai, e un
    # controllo che non ha un caso non e' una garanzia.
    "gol-precoce": {},
    # CASH-OUT GLOBALE DELL'UTENTE (16/09 h18:20): NON tocca un parametro. Quello
    # che cambia e' che a meta' partita arriva una richiesta VERA di `cashout`
    # dalla UI (`service.process_requests`), come se l'utente avesse premuto il
    # tasto. Da quel momento il bot non deve aprire piu' niente su quella
    # partita (controllo R2). Senza provocarla, quella regola non ha mai un caso.
    "cashout-globale": {},
}
SCENARIO_GOL_PRECOCE = "gol-precoce"
SCENARIO_CASHOUT_GLOBALE = "cashout-globale"

# CHIUSURA FATTA DALL'UTENTE **FUORI DALL'APP** (ordine 16/09 sera). Non tocca
# un parametro: quello che cambia e' che a meta' partita compaiono sul mercato
# ordini che NON sono del bot — una posizione dell'utente e poi la lay con cui
# l'utente chiude TUTTO. Sono ordini VERI su flumine, con un ref che non e' di
# Mike: nella lista filtrata per strategia (quella che il bot legge) non ci
# sono, nella POSIZIONE DI CONTO sul mercato si'. Da quel momento il bot deve
# accorgersi che la sua posizione non e' piu' sul conto e non fare piu' niente
# su quella partita (controllo R3).
SCENARIO_CHIUSO_FUORI_APP = "chiuso-fuori-app"

# RIFIUTO DICHIARATO DI BETFAIR (`ok=False`). Non tocca un parametro: i primi N
# piazzamenti tornano con un report NEGATIVO, come quando Betfair rifiuta
# l'istruzione (prezzo non piu' valido, profit ratio fuori banda, fondi). E'
# l'unico modo di mettere alla prova il difetto 2 del catalogo del 15/09 —
# «`res.ok` mai letto» — che sulle registrazioni non capita mai perche' nel
# replay nessun ordine viene rifiutato.
SCENARIO_RIFIUTI = "rifiuti-betfair"
QUANTI_RIFIUTI = 3
# 17/09 (reperto 25): la COPERTURA sotto minimo rifiutata SEMPRE, con il
# codice vero di quel giorno. Non un rifiuto che finisce dopo N: 171 su 171.
SCENARIO_COVER_RIFIUTATA = "copertura-rifiutata"
COVER_RIFIUTO_CODICE = "CANCELLED_NOT_PLACED"
COVER_RIFIUTO_INTERNO = "INVALID_BET_SIZE"
# quanto l'utente ha di SUO sulla stessa selezione, prima di chiudere tutto:
# serve a provare che Mike riconosce LA SUA posizione dentro quella di conto e
# non da' per sua ogni cosa che vede.
UTENTE_SUO_BACK = 3.0

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

# scenario speciale: LO STESSO GUASTO, SUL PERCORSO TAKER. Serve a sollecitare
# J1 e J4, che sul `taker` puro non hanno MAI un caso da giudicare: li' ogni
# piazzamento si risolve dentro lo stesso giro (fill o rifiuto), quindi al
# momento della decisione non c'e' mai una gamba in volo e non parte mai un
# `cancel`. Con gli esiti IGNOTI la gamba resta invece `pending_reconcile` per
# piu' giri, ed e' esattamente la condizione che i due controlli difendono:
# «mai due gambe in volo identiche» e «una gamba a esito ignoto non si da' mai
# per annullata, ne' si rifa». Non tocca la partita ne' i prezzi: sono gli
# stessi parametri del `taker` piu' lo stesso guasto di `esiti-ignoti`.
SCENARIO_TAKER_IGNOTI = "taker-esiti-ignoti"

# scenario speciale: RIAVVIO A META' PARTITA (copertura §6.3). Con una posizione
# aperta si butta via tutto cio' che vive nel PROCESSO (le cache di modulo di
# `mike/service.py`) e si riparte: lo stato della partita deve essere ritrovato
# dal database, come succede quando l'app si riavvia o il watchdog rilancia il
# servizio. E' il difetto 19 del catalogo (`pre_ko` che viveva solo in RAM:
# base e punta spente per ore), riprodotto apposta invece che aspettato.
SCENARIO_RIAVVIO = "riavvio"


def _riavvia_processo() -> List[str]:
    """Butta via le cache di PROCESSO di `mike/service.py`, come un riavvio.

    Non tocca il database in memoria: quello e' il DB, e in produzione
    sopravvive. Torna l'elenco di cio' che e' stato azzerato, che finisce nel
    referto: un riavvio che non si sa che cosa ha buttato non prova niente.

    ⚠️ 16/09 SERA — prima questa funzione girava su `dir(S)` e svuotava OGNI
    dizionario di modulo: fra quelli c'e' `_ALIAS_ORDINE`, la tabella con cui
    Mike legge le chiavi camelCase di Betfair. Azzerarla vuol dire
    reintrodurre il difetto 1 del 15/09 dentro lo scenario che dovrebbe
    certificare il riavvio. Adesso l'elenco e' ESPLICITO e vive nel servizio
    (`service.azzera_cache_di_processo`), accanto alle cache che dichiara.
    """
    return S.azzera_cache_di_processo()


# le due linee che interessano a Mike, coi nomi di mercato Betfair
_LINEE = {"OVER_UNDER_35": 3.5, "OVER_UNDER_45": 4.5}


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(int(ms) / 1000.0, tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# IL PAYLOAD SCRITTO A MANO — adesso serve SOLO al confronto
# ---------------------------------------------------------------------------
# Fino al 15/09 la riga di scan la costruivano queste due funzioni. Era un finto
# che poteva parlare una lingua diversa dal vero, ed e' esattamente la famiglia
# di difetti che ci e' costata cinque incidenti. Dal 16/09 la riga la produce lo
# SCANNER VERO (`Scanner.build_rows`) e queste restano solo come TERMINE DI
# PARAGONE: `--diff` confronta campo per campo cio' che scriverebbero loro con
# cio' che lo scanner scrive davvero, su un campione di tick.
def blocco_ou(market_book: Any, linea: float, pt_ms: int) -> Optional[Dict[str, Any]]:
    """Un blocco ``ou`` del feed unico, ricavato a mano da un MarketBook flumine.

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
    """Il payload come lo scriveva QUESTO FILE. Solo per il confronto `--diff`."""
    return {
        "event_name": nome,
        "open_date": ko_iso,
        "inplay": bool(inplay),
        "minute": minuto if isinstance(minuto, int) else None,
        "score_home": int(gol_casa),
        "score_away": int(gol_fuori),
        "ou": [b for b in blocchi.values() if b],
    }


def _ou_per_linea(payload: Dict[str, Any]) -> Dict[float, Dict[str, Any]]:
    out: Dict[float, Dict[str, Any]] = {}
    for b in payload.get("ou") or []:
        if isinstance(b, dict) and b.get("line") is not None:
            out[float(b["line"])] = b
    return out


def confronta_payload(a_mano: Dict[str, Any], vero: Dict[str, Any]) -> List[str]:
    """Differenze CAMPO PER CAMPO fra il payload scritto a mano e quello che lo
    scanner vero produce. Ogni riga e' un reperto, non un dettaglio."""
    diff: List[str] = []
    for campo in ("event_name", "open_date", "inplay", "minute",
                  "score_home", "score_away"):
        a, b = a_mano.get(campo), vero.get(campo)
        if a != b:
            diff.append(f"payload.{campo}: a_mano={a!r} scanner={b!r}")
    ma, mv = _ou_per_linea(a_mano), _ou_per_linea(vero)
    if set(ma) != set(mv):
        diff.append(f"ou.linee: a_mano={sorted(ma)} scanner={sorted(mv)}")
    for linea in sorted(set(ma) & set(mv)):
        ba, bv = ma[linea], mv[linea]
        for campo in ("market_id", "status", "inplay", "bet_delay", "seen_ms",
                      "total_matched"):
            if ba.get(campo) != bv.get(campo):
                diff.append(f"ou[{linea}].{campo}: a_mano={ba.get(campo)!r} "
                            f"scanner={bv.get(campo)!r}")
        solo_vero = sorted(set(bv) - set(ba))
        solo_mano = sorted(set(ba) - set(bv))
        if solo_vero:
            diff.append(f"ou[{linea}]: chiavi SOLO nello scanner: {solo_vero}")
        if solo_mano:
            diff.append(f"ou[{linea}]: chiavi SOLO a mano: {solo_mano}")
        sa = {int(x["selection_id"]): x for x in (ba.get("selections") or [])
              if x.get("selection_id") is not None}
        sv = {int(x["selection_id"]): x for x in (bv.get("selections") or [])
              if x.get("selection_id") is not None}
        if set(sa) != set(sv):
            diff.append(f"ou[{linea}].selections: a_mano={sorted(sa)} scanner={sorted(sv)}")
        for sid in sorted(set(sa) & set(sv)):
            for campo in ("name", "back", "lay", "back_size", "lay_size"):
                if sa[sid].get(campo) != sv[sid].get(campo):
                    diff.append(f"ou[{linea}].sel[{sid}].{campo}: "
                                f"a_mano={sa[sid].get(campo)!r} scanner={sv[sid].get(campo)!r}")
    solo_vero = sorted(set(vero) - set(a_mano))
    if solo_vero:
        diff.append(f"payload: chiavi SOLO nello scanner: {solo_vero}")
    return diff


# ---------------------------------------------------------------------------
# la strategia flumine: raccoglie i book, fa decidere Mike, certifica
# ---------------------------------------------------------------------------
def _crea_strategia():
    from flumine import BaseStrategy

    class MikeCert(BaseStrategy):
        """A ogni tick del replay alimenta lo SCANNER VERO coi book di flumine,
        prende la riga che lo scanner scrive, la da' al servizio vero di Mike e
        verifica le regole."""

        def __init__(self, *, event_id: str, params: Dict[str, Any],
                     banco: ScannerReplay,
                     punteggi: List[Tuple[int, Dict[str, Any]]],
                     ogni_ms: int = 1000, campioni_diff: int = 0, **kw: Any) -> None:
            self.event_id = str(event_id)
            self.params = params
            self.banco = banco
            self._punteggi = list(punteggi or [])
            self._ts_punteggi = [t for t, _ in self._punteggi]
            self._i_punteggi = 0
            self.ogni_ms = int(ogni_ms)
            self.invecchia_s = float(kw.pop("invecchia_s", 0.0) or 0.0)
            # RIAVVIO A META' PARTITA (§6.3): al primo giro con una posizione
            # aperta si azzerano le cache di processo del servizio.
            self.riavvia = bool(kw.pop("riavvia", False))
            self.riavvio_fatto: Optional[List[str]] = None
            # CASH-OUT GLOBALE DELL'UTENTE (16/09 h18:20): al primo giro con una
            # posizione aperta si manda la richiesta VERA, quella che scrive la
            # UI, allo STESSO `service.process_requests` della produzione.
            self.cashout_utente = bool(kw.pop("cashout_utente", False))
            self.cashout_fatto: Optional[Dict[str, Any]] = None
            # CHIUSURA DELL'UTENTE FUORI DALL'APP (16/09 sera): ordini VERI su
            # flumine con un ref che non e' del bot.
            self.chiuso_fuori_app = bool(kw.pop("chiuso_fuori_app", False))
            self.chiusura_utente: Optional[Dict[str, Any]] = None
            # A2 — I GIRI DEL SERVIZIO SU UNA PARTITA GIA' TERMINALE.
            # Il controllo A2 («da uno stato terminale non esce nessuna azione»)
            # non puo' avere un caso attraverso il servizio: `_run_event` esce
            # PRIMA di chiamare `decide` quando lo stato e' terminale. E' una
            # garanzia piu' forte del controllo, ma va MISURATA, non assunta:
            # qui si contano i giri fatti su una partita terminale e le azioni
            # che ne sono uscite (devono essere zero).
            self.giri_terminali: int = 0
            self.azioni_dopo_terminale: int = 0
            # scenario `chiusura-abbinata-in-parte`: la sorveglianza CP del
            # banco comune (None in tutti gli altri scenari)
            self.sorveglianza_cp: Optional[CP.Sorveglianza] = None

            # i mercati flumine, per market_id: servono per piazzare davvero
            self.mercati: Dict[str, Any] = {}
            self.ko_iso: Optional[str] = None
            self.nome: str = ""
            # IL BANCO: database in memoria e mercato flumine. Da qui in poi il
            # giro lo fa `service._run_event`, cioe' il bot INTERO — cervello
            # e mani. Le gambe non le tiene piu' questo file: stanno nel `ctx`
            # dell'evento, esattamente come in produzione.
            self.db = DbMemoria({"status": "running", "mode": "live", "params": params})
            self.mercato = MercatoFlumine(self)
            self.referto = CERT.Referto(event_id=str(event_id))
            self._ultimo_ms: int = 0
            self._stati: List[str] = []
            # confronto payload-a-mano vs payload-scanner (solo con --diff)
            self.campioni_diff = int(campioni_diff)
            self._blocchi_a_mano: Dict[str, Dict[str, Any]] = {}
            self.diff_visti: List[str] = []
            self.diff_campionati: int = 0
            self.righe_assenti: int = 0
            super().__init__(**kw)

        # ---------------------------------------------------------- flumine
        def check_market_book(self, market, market_book) -> bool:
            return True

        def process_market_book(self, market, market_book) -> None:
            mtype = self.banco.registra_mercato(market_book)
            if not mtype:
                return
            self.mercati[str(market_book.market_id)] = market
            pt = getattr(market_book, "publish_time", None)
            # "adesso" per lo scanner E' il publish time del tick, e NON TORNA
            # INDIETRO: i book non arrivano in ordine di tempo (vedi
            # `MotoreReplay`). Da qui in poi il tempo del replay e' questo.
            pt_ms = (int(self.banco.imposta_ora(pt.timestamp()) * 1000)
                     if pt is not None else 0)
            self.banco.applica_book(market_book)
            linea = _LINEE.get(mtype)
            if linea is None:
                # gli altri mercati servono allo scanner (MATCH_ODDS per il
                # catalogo e il pre-KO, le altre linee per il payload), ma il
                # CONTEGGIO DEI TICK resta quello delle due linee di Mike: e'
                # il numero con cui si confrontano i referti precedenti
                return
            if self.ko_iso is None:
                md = getattr(market_book, "market_definition", None)
                mt = getattr(md, "market_time", None) or getattr(md, "open_date", None)
                if mt is not None:
                    self.ko_iso = mt.isoformat() if hasattr(mt, "isoformat") else str(mt)
                self.nome = str(getattr(md, "event_name", None) or self.event_id)
            if self.campioni_diff:
                self._blocchi_a_mano[mtype] = blocco_ou(market_book, linea, pt_ms)
            self.referto.tick += 1
            # Mike gira ogni 1-2 secondi: nel replay si decide alla stessa
            # cadenza, non ad ogni singolo messaggio dello stream.
            if pt_ms - self._ultimo_ms < self.ogni_ms:
                return
            self._ultimo_ms = pt_ms
            self._un_giro(pt_ms)
            # LA CADENZA RIPARTE DA QUANDO IL GIRO E' FINITO, non da quando
            # e' cominciato. In produzione le chiamate bloccanti (un
            # piazzamento in gioco: `place_latency + betDelay`) consumano tempo
            # VERO, e il ciclo successivo parte dopo: un giro lungo ritarda il
            # giro dopo. Segnando l'inizio, il replay farebbe girare il bot piu'
            # spesso di quanto giri davvero.
            if BANCO.CADENZA_DOPO_LE_CHIAMATE:
                self._ultimo_ms = max(self._ultimo_ms, int(self.banco.ora * 1000))

        # ------------------------------------------------------------ Mike
        def _un_giro(self, pt_ms: int) -> None:
            # 1) i punteggi fino a questo istante, dal record IPS grezzo e dal
            #    parser vero (`Scanner.apply_score_state`)
            i = bisect_right(self._ts_punteggi, int(pt_ms))
            while self._i_punteggi < i:
                self.banco.applica_punteggio(self.event_id,
                                             self._punteggi[self._i_punteggi][1])
                self._i_punteggi += 1
            # 2) "questa partita la segue Mike": in produzione lo scanner lo
            #    legge da `mike_events` (stati non terminali) e da li' decide se
            #    tenere vive le due linee anche quando sono gia' decise. Qui la
            #    verita' e' nel banco, e viene dichiarata allo scanner con la
            #    stessa forma (lista di event_id).
            stato_ev = str((self.db.events.get(self.event_id) or {}).get("state") or "")
            self.banco.scan._mike_followed_ids = (
                [self.event_id] if stato_ev and stato_ev not in E.TERMINAL_STATES else [])
            # 2-bis) RIAVVIO A META' PARTITA, con soldi dentro: le cache di
            #    processo spariscono, il database resta. Se lo stato non si
            #    ritrova da li', il bot dimentica una posizione aperta — ed e'
            #    esattamente quello che e' successo al `pre_ko` il 13/09.
            if self.riavvia and self.riavvio_fatto is None and any(
                    str(r.get("status")) in ("open", "pending") for r in self.db.trades):
                self.riavvio_fatto = _riavvia_processo()
                self.db.log("replay_riavvio", {"azzerati": self.riavvio_fatto},
                            self.event_id)
            # 3) LA RIGA LA SCRIVE LO SCANNER VERO
            self.banco.pubblica()
            row = self.banco.riga(self.event_id)
            if row is None:
                # riga assente dal feed: NON si salta il giro. E' esattamente il
                # caso che `_run_event` deve saper gestire (row_missing_since,
                # settlement per riga sparita), e senza passarci non lo si
                # certifica mai.
                self.righe_assenti += 1
            elif self.invecchia_s > 0:
                # `invecchia_s` > 0: la riga si dichiara vecchia di tot secondi.
                # Non cambia NESSUN prezzo: cambia solo da quanto tempo non
                # arriva. Perche' il feed risulti STANTIO devono essere vecchi
                # TUTTI E DUE — la riga e lo scanner — e lo scanner lo si
                # invecchia col `scanner_age` passato al servizio.
                row = dict(row, updated_at=_iso(pt_ms - int(self.invecchia_s * 1000)))
            if row is not None and self.campioni_diff and self.diff_campionati < self.campioni_diff:
                blocchi = {k: v for k, v in self._blocchi_a_mano.items() if v}
                if len(blocchi) == len(_LINEE):
                    self.diff_campionati += 1
                    gc = int(row["payload"].get("score_home") or 0)
                    gf = int(row["payload"].get("score_away") or 0)
                    a_mano = payload_evento(
                        self.event_id, blocchi, self.ko_iso, self.nome,
                        row["payload"].get("minute"), gc, gf,
                        bool(row["payload"].get("inplay")))
                    for riga in confronta_payload(a_mano, row["payload"]):
                        if riga not in self.diff_visti:
                            self.diff_visti.append(riga)

            # -- IL BOT INTERO, non solo il motore --------------------------
            # `service._run_event` fa il giro vero: snapshot -> decide ->
            # ESEGUE gli ordini -> riconcilia -> scrive le righe. E' il
            # percorso in cui il 15/09 si sono rotte cinque cose, e senza
            # passare di qua non si certifica niente di quello.
            #
            # I controlli si agganciano a `engine.decide`, che viene chiamata
            # dentro: si intercetta li', cosi' si vede ogni decisione con il
            # `ctx` e lo `snap` veri costruiti dal servizio.
            ev = self.db.events.get(self.event_id) or {
                "event_id": self.event_id,
                "event_name": ((row or {}).get("payload") or {}).get("event_name") or self.nome,
                "state": "WATCH", "mode": "live", "ctx": {},
            }
            # I MERCATI SULLA RIGA DELL'EVENTO, come in produzione.
            # In produzione la riga la crea `service.run_once` quando arma la
            # partita, e ci scrive `markets = {tipo: {"market_id": ...}}` dal
            # `feed.event_info` (`service.py:2366`). Il replay costruiva la riga
            # a mano e quel campo NON c'era: tutto cio' che in `_run_event`
            # dipende da `ev["markets"]` — la lettura REST di regolamento e,
            # dal 16/09 sera, la POSIZIONE DI CONTO — non veniva mai esercitato.
            # E' un buco del banco, non del bot: qui si chiude, con la stessa
            # funzione di produzione.
            if row is not None and not ev.get("markets"):
                try:
                    _info = S.F.event_info(self.event_id, row.get("payload") or {})
                    mkts = {m: {"market_id": _info.market_id(m)} for m in _info.markets}
                    if mkts:
                        ev["markets"] = mkts
                except Exception:  # noqa: BLE001 - senza catalogo si prosegue
                    pass
            self.db.upsert_event(ev)
            self.db.scan_rows = [row] if row is not None else []
            now = pt_ms / 1000.0
            terminale = str(self.db.events[self.event_id].get("state") or "") in E.TERMINAL_STATES
            try:
                azioni, _settled = S._run_event(
                    db=self.db, market=self.mercato, ev=self.db.events[self.event_id],
                    row=row, params=self.params, mode="live",
                    now=datetime.fromtimestamp(now, tz=timezone.utc),
                    # lo scanner e' vecchio quanto la riga: e' l'altra meta'
                    # della regola del feed stantio
                    scanner_age=self.invecchia_s, atlas=None, dry=False)
            except Exception as ex:  # noqa: BLE001 - un'eccezione del servizio E' un referto
                self.referto.violazioni.append(CERT.Violazione(
                    "SERVIZIO", "il giro del servizio non deve mai sollevare",
                    f"{type(ex).__name__}: {ex}",
                    str(self.db.events[self.event_id].get("state") or "")))
                return
            # -- CASH-OUT GLOBALE DELL'UTENTE (16/09 h18:20) ----------------
            # Non si finge: si manda la richiesta VERA, quella che scrive la UI,
            # allo STESSO `service.process_requests` che la esegue in produzione.
            # Da qui in poi il bot non deve aprire piu' niente sulla partita (R2).
            if self.cashout_utente and self.cashout_fatto is None and any(
                    str(r.get("status")) == "open" for r in self.db.trades):
                try:
                    esito = S.process_requests(
                        db=self.db, market=self.mercato,
                        events={self.event_id: self.db.events[self.event_id]},
                        rows_by_event={self.event_id: row} if row is not None else {},
                        params=self.params, now=datetime.fromtimestamp(now, tz=timezone.utc),
                        dry=False, scanner_age=self.invecchia_s, eff=self.params,
                        reqs=[{"id": 1, "kind": "cashout",
                               "payload": {"event_id": self.event_id}}])
                    self.cashout_fatto = {"richieste": int(esito or 0), "ms": int(pt_ms)}
                    self.db.log("replay_cashout_utente", dict(self.cashout_fatto),
                                self.event_id)
                except Exception as ex:  # noqa: BLE001 - e' un referto, non un crash
                    self.referto.violazioni.append(CERT.Violazione(
                        "SERVIZIO", "il cash-out manuale non deve mai sollevare",
                        f"{type(ex).__name__}: {ex}",
                        str(self.db.events[self.event_id].get("state") or "")))
                    self.cashout_fatto = {"errore": str(ex)[:120]}

            # -- CHIUSURA FATTA DALL'UTENTE FUORI DALL'APP (16/09 sera) ----
            # Non si finge niente: si piazzano su flumine DUE ordini veri che
            # non sono del bot (ref 'utente-*', invisibili alla lista filtrata
            # per strategia che Mike legge, presenti nella posizione di conto):
            #   1. una posizione dell'utente sulla STESSA selezione — cosi' la
            #      posizione di conto contiene anche roba sua, e si prova che
            #      Mike riconosce la propria e non si prende il resto;
            #   2. la lay con cui l'utente chiude TUTTO (la sua piu' quella del
            #      bot).
            if self.chiuso_fuori_app and self.chiusura_utente is None:
                self._chiudi_come_utente(pt_ms)

            # -- I CONTROLLI K: LA MEMORIA DEL BOT CONTRO IL MERCATO -------
            # Si fanno QUI, dopo il giro del servizio, perche' solo qui
            # esistono insieme le gambe (nel ctx dell'evento) e gli ORDINI VERI
            # di flumine. I controlli A-J guardano la decisione; questi guardano
            # il rapporto fra cio' che il bot crede e cio' che c'e' a mercato —
            # ed e' li' che vivevano tutti e cinque i difetti del 15/09.
            self._verifica_consapevolezza()
            # -- I CONTROLLI CP (scenario chiusura-abbinata-in-parte) --------
            if self.sorveglianza_cp is not None:
                for cod, reg, det in self.sorveglianza_cp.verifica(
                        credenze_mike(self.db, self.event_id), self.referto.sollecitati):
                    self.referto.violazioni.append(CERT.Violazione(
                        cod, reg, det,
                        str(self.db.events[self.event_id].get("state") or "")))

            if terminale:
                self.giri_terminali += 1
                self.azioni_dopo_terminale += int(azioni or 0)
            self.referto.azioni += int(azioni or 0)
            stato = str(self.db.events[self.event_id].get("state") or "")
            if stato and stato not in self._stati:
                self._stati.append(stato)

        def _verifica_consapevolezza(self) -> None:
            ev = self.db.events.get(self.event_id)
            if not ev:
                return
            ctx = S._ctx_from_row(ev, self.db)
            ordini = {ref: self.mercato._riga(ref, o)
                      for ref, o in self.mercato.ordini.items()}
            rifiutati = {str(r.get("ref") or "") for r in self.mercato.rifiutati}
            self.referto.violazioni.extend(CERT.verifica_consapevolezza(
                ctx, ordini, rifiutati,
                self.db.trades_for_event(self.event_id), self.referto.sollecitati))

        def _chiudi_come_utente(self, pt_ms: int) -> None:
            """L'utente chiude la posizione di Mike da FUORI: ordini veri, ref suo."""
            ev = self.db.events.get(self.event_id) or {}
            mkts = ev.get("markets") or {}
            sels = ((ev.get("ctx") or {}).get("selections") or {})
            market_id = str((mkts.get(E.MARKET_OU35) or {}).get("market_id") or "")
            sel = sels.get(f"{E.MARKET_OU35}|{E.SEL_UNDER}")
            if not market_id or sel is None:
                return
            # quanto Mike ha ABBINATO adesso sull'Under 3.5 (netto back-lay):
            # e' la posizione che l'utente sta chiudendo
            netto = 0.0
            for r in self.db.trades:
                if str(r.get("status")) != "open":
                    continue
                if str(r.get("market_id") or "") != market_id:
                    continue
                try:
                    if int(r.get("selection_id") or 0) != int(sel):
                        continue
                except (TypeError, ValueError):
                    continue
                size = float(r.get("size") or 0.0)
                netto += size if str(r.get("side")) == "back" else -size
            if netto <= 0.01:
                return
            # 1) la posizione SUA (stessa selezione, stesso lato): la posizione
            #    di conto la conterra' insieme a quella di Mike
            # un BACK si abbina accettando QUALUNQUE quota disponibile: prezzo
            # minimo. (Una lay fa il contrario: prezzo massimo.)
            suo = self.mercato.place_order_utente(
                market_id=market_id, selection_id=int(sel), price=1.01,
                size=UTENTE_SUO_BACK, side="back", customer_ref="utente-suo-back")
            suo_abbinato = (float(getattr(getattr(suo, "simulated", None), "size_matched", 0.0) or 0.0)
                            if suo is not None else 0.0)
            # 2) la lay con cui chiude TUTTO (la sua piu' quella del bot).
            #    Prezzo altissimo = si accetta qualunque quota disponibile:
            #    e' il modo in cui un ordine a mercato si abbina davvero.
            chiusura = self.mercato.place_order_utente(
                market_id=market_id, selection_id=int(sel), price=1000.0,
                size=round(netto + suo_abbinato, 2), side="lay",
                customer_ref="utente-chiusura")
            abb = (float(getattr(getattr(chiusura, "simulated", None), "size_matched", 0.0) or 0.0)
                   if chiusura is not None else 0.0)
            self.chiusura_utente = {"ms": int(pt_ms), "market_id": market_id,
                                    "selection_id": int(sel),
                                    "posizione_del_bot": round(netto, 2),
                                    "back_dell_utente": round(suo_abbinato, 2),
                                    "lay_di_chiusura_abbinata": round(abb, 2)}
            self.db.log("replay_chiusura_fuori_app", dict(self.chiusura_utente),
                        self.event_id)

        def chiudi(self) -> CERT.Referto:
            self.referto.stati_visti = list(self._stati)
            return self.referto

    return MikeCert


# ---------------------------------------------------------------------------
# un evento
# ---------------------------------------------------------------------------
def certifica_evento(*a: Any, **kw: Any) -> CERT.Referto:
    """Guscio: accende la simulazione di flumine e la RIMETTE A POSTO alla fine
    (i flag di `flumine.config` sono di PROCESSO: lasciarli accesi fa mentire
    tutto cio' che gira dopo nello stesso processo)."""
    with simulazione_flumine():
        return _certifica_evento(*a, **kw)


def _certifica_evento(event_id: str, *, data_dir: str,
                      params: Optional[Dict[str, Any]] = None,
                      ogni_ms: int = 1000,
                      invecchia_s: float = 0.0,
                      guasti: int = 0,
                      rifiuti: int = 0,
                      cover_rifiutata: bool = False,
                      campioni_diff: int = 0,
                      riavvia: bool = False,
                      cashout_utente: bool = False,
                      chiuso_fuori_app: bool = False,
                      chiusura_parziale: bool = False) -> CERT.Referto:
    """Fa rivivere a Mike una partita registrata e ritorna il referto."""
    from flumine import FlumineSimulation

    # OGNI REPLAY PARTE DA UN PROCESSO PULITO. Con la pool (`--worker N`) piu'
    # coppie evento x scenario girano nello STESSO processo figlio, una dopo
    # l'altra: senza questo azzeramento il secondo replay eredita i throttle del
    # primo e certifica una cosa diversa da quella che certifica da solo.
    # Misurato il 16/09 sera: `chiuso-fuori-app` dentro `--scenari tutti
    # --worker 3` non leggeva mai la posizione di conto e dava R1/R3 a zero.
    S.azzera_cache_di_processo()
    par = dict(params or C.merge_params(None))
    raw = os.path.join(data_dir, str(event_id), f"{event_id}.raw.jsonl")
    ref = CERT.Referto(event_id=str(event_id))
    if not os.path.exists(raw):
        ref.note.append(f"registrazione assente: {raw}")
        return ref

    try:
        # il RECORD IPS GREZZO del sidecar, non un riassunto: e' cio' che
        # `Scanner.apply_score_state` sa leggere
        punteggi = carica_punteggi(data_dir, str(event_id), "calcio")
    except Exception as ex:  # noqa: BLE001 - senza punteggio si replica lo stesso
        punteggi = []
        ref.note.append(f"punteggi non letti ({type(ex).__name__}): minuti e gol assenti")

    # IL BANCO COMUNE: lo scanner VERO, con il suo orologio agganciato al
    # publish time del tick. `SAFE_PRE_KO_OU_HOURS` in produzione accende il
    # ramo pre-KO delle due linee di Mike: qui lo si dichiara, altrimenti prima
    # del fischio le linee non entrerebbero MAI nel feed e Mike non aprirebbe.
    banco = ScannerReplay(sport="calcio",
                          pre_ko_ou_hours=max(6.0, float(par.get("entry_hours_before_ko") or 0.0)))
    banco.dichiara_nomi(*nomi_dal_punteggio(punteggi))

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
    strategia = Strategia(event_id=str(event_id), params=par, banco=banco,
                          punteggi=punteggi, ogni_ms=ogni_ms,
                          invecchia_s=invecchia_s, campioni_diff=campioni_diff,
                          riavvia=riavvia, cashout_utente=cashout_utente,
                          chiuso_fuori_app=chiuso_fuori_app,
                          market_filter={"markets": [raw]},
                          max_order_exposure=1e9, max_selection_exposure=1e9,
                          max_trade_count=int(1e9), max_live_trade_count=int(1e9))
    if rifiuti > 0:
        # i primi N piazzamenti tornano `ok=False`: e' il RIFIUTO dichiarato di
        # Betfair, non un errore di rete (quello e' `place_exception`)
        strategia.mercato.guasti["place_rifiuto"] = int(rifiuti)
        # sul LATO LAY: e' li' che vivono le uscite appoggiate, cioe' il ramo
        # (`_piazza_resting_live`) in cui il 15/09 `res.ok` non veniva letto
        strategia.mercato.rifiuta_lato = "lay"
    if cover_rifiutata:
        # 17/09 — LA COPERTURA SOTTO MINIMO RIFIUTATA SEMPRE, come il 17/09.
        # -1 = il rifiuto non si consuma; il filtro sulla size colpisce SOLO gli
        # ordini sotto il minimo .it (la copertura), non l'ingresso da 5 EUR ne'
        # le uscite. Il codice e' quello vero, esterno E interno.
        strategia.mercato.guasti["place_rifiuto"] = -1
        strategia.mercato.rifiuta_lato = "back"
        strategia.mercato.rifiuta_sotto_minimo = 2.00
        strategia.mercato.rifiuto_codice = COVER_RIFIUTO_CODICE
        strategia.mercato.rifiuto_codice_interno = COVER_RIFIUTO_INTERNO
    if guasti > 0:
        # i primi N piazzamenti falliranno con esito IGNOTO: e' cosi' che
        # nascono le gambe `pending_reconcile` che altrimenti non si vedono mai
        strategia.mercato.guasti["place_exception"] = int(guasti)
    referti_vivi.append(strategia.referto)
    # i tetti di flumine aperti anche sul CLIENT (min bet size/payout GBP):
    # il minimo che conta e' quello del bot, non quello di flumine
    quadro = FlumineSimulation(client=cliente_simulato())
    assicura_middleware_simulato(quadro)
    quadro.add_strategy(strategia)

    def _scanner_durante_attesa(mb: Any) -> None:
        # Mike e' bloccato sulla REST mentre Betfair trattiene l'ordine; lo
        # SCANNER no: in produzione e' un altro processo e continua a ricevere
        # i book. Qui riceve gli stessi book, senza far girare il bot.
        pt = getattr(mb, "publish_time", None)
        if pt is not None:
            banco.imposta_ora(pt.timestamp())
        if banco.registra_mercato(mb):
            banco.applica_book(mb)

    # IL MOTORE: il ciclo di flumine, ma con l'ATTESA del bet delay. Un ordine
    # piazzato a t si abbina sul book di t + place_latency + betDelay, come fa
    # Betfair, non su quello di t.
    motore = MotoreReplay(quadro, su_book=_scanner_durante_attesa)
    strategia.mercato.motore = motore
    guasto_cp: Optional[CP.GuastoChiusuraParziale] = None
    if chiusura_parziale:
        # il RUOLO dell'ordine si legge dalla riga di `mike_trades` che lo ha
        # chiesto (ref `mike-t<id>`, `closes_trade_id` sulle chiusure, H4)
        guasto_cp = CP.GuastoChiusuraParziale(
            ruolo=CP.ruolo_da_righe(lambda: strategia.db.trades))
        motore.guasto_chiusure = guasto_cp
        strategia.sorveglianza_cp = CP.Sorveglianza(guasto_cp)
    E.decide = decide_sorvegliata          # type: ignore[assignment]
    try:
        motore.esegui(strategia)
    finally:
        E.decide = decide_vero             # type: ignore[assignment]

    out = strategia.chiudi()
    if guasto_cp is not None:
        out.note.append(guasto_cp.riepilogo())
        out.note.append("CP2 (copertura dichiarata sull'abbinato) NON APPLICABILE a "
                        "Mike: non scrive una copertura per riga (`meta.hedged_size`), "
                        "la posizione la ricalcola dalle gambe; la consapevolezza "
                        "dell'abbinato la guardano CP1 e i controlli K")
    if strategia.db.mancanti:
        out.note.append("metodi di database chiamati dal servizio e assenti dal banco: "
                        f"{sorted(strategia.db.mancanti)}")
    if strategia.db.senza_dato:
        # NON ESERCITABILE, con la causa: il metodo c'e' e risponde col tipo
        # vero, ma il DATO che in produzione arriva da una tabella/RPC non e'
        # nella registrazione. PROCESSO_STANDARD_BOT §6.8 lo vuole scritto.
        out.note.append("[NON ESERCITABILE] dati di produzione assenti dalla "
                        "registrazione: "
                        + " | ".join(f"{n}: {c}" for n, c in strategia.db.senza_dato))
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
                    + ", ".join(f"{k} x{n}" for k, n in kinds.most_common(20)))
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
    if not punteggi:
        out.note.append("senza sidecar `.scores.jsonl`: minuto e gol non arrivano mai, "
                        "quindi le regole che dipendono dal punteggio non sono state "
                        "messe alla prova")
    if strategia.riavvio_fatto is not None:
        out.note.append("RIAVVIO a meta' partita: azzerate le cache di processo "
                        + ", ".join(strategia.riavvio_fatto[:8]))
    elif strategia.riavvia:
        out.note.append("scenario riavvio: nessuna posizione aperta da ritrovare, "
                        "il riavvio non e' mai scattato")
    if strategia.cashout_utente:
        quante = int(out.sollecitati.get("R2") or 0)
        if strategia.cashout_fatto is None:
            out.note.append("scenario cashout-globale: nessuna posizione aperta, la "
                            "richiesta dell'utente non e' mai partita")
        else:
            out.note.append(
                f"scenario cashout-globale: richiesta `cashout` VERA mandata dall'utente "
                f"({strategia.cashout_fatto}); il controllo R2 «dopo un cash-out globale "
                f"il bot non apre piu' niente» e' stato sollecitato {quante} volte")
    if strategia.chiuso_fuori_app:
        quante = int(out.sollecitati.get("R3") or 0)
        if strategia.chiusura_utente is None:
            out.note.append("scenario chiuso-fuori-app: nessuna posizione aperta del bot, "
                            "l'utente non ha avuto niente da chiudere")
        else:
            out.note.append(
                f"scenario chiuso-fuori-app: ordini VERI dell'utente su flumine con un ref "
                f"non di Mike ({strategia.chiusura_utente}); il controllo R3 «se ha chiuso "
                f"l'utente il bot non fa piu' niente» e' stato sollecitato {quante} volte")
    # LE QUATTRO REAZIONI ALLA RIAPERTURA, contate una per una (§15.6, R1).
    # «Quante volte R1 ha avuto un caso» non basta: dice che la catena gira, non
    # QUALE dei quattro rami e' stato esercitato. Il ramo (b) «scaduto alla
    # sospensione» e' quello che il 16/09 non era mai capitato sui dati reali.
    esiti_riapertura = Counter()
    for k, p_, _e in strategia.db.attivita:
        if k == "rilettura_alla_riapertura":
            esiti_riapertura[str((p_ or {}).get("esito") or "?")] += 1
    scaduti = sum(1 for k, _p, _e in strategia.db.attivita
                  if k == "ordine_scaduto_alla_sospensione")
    out.note.append(
        "riapertura dopo una sospensione (§15.6): riletture "
        + (", ".join(f"{k} x{n}" for k, n in sorted(esiti_riapertura.items())) or "nessuna")
        + f" | ordini dichiarati SCADUTI alla sospensione (ramo b): {scaduti}")
    if strategia.giri_terminali:
        out.note.append(
            f"stato TERMINALE: {strategia.giri_terminali} giri del servizio su una partita "
            f"gia' chiusa, azioni prodotte {strategia.azioni_dopo_terminale} (devono essere 0). "
            f"Il controllo A2 resta a zero casi per COSTRUZIONE: `service._run_event` esce "
            f"prima di chiamare `decide` su uno stato terminale, quindi A2 e' la SECONDA "
            f"linea di difesa e la si mette alla prova togliendo quel return "
            f"(falsificazione dichiarata nel checkpoint), non con una registrazione")
    else:
        out.note.append("stato TERMINALE: la partita non ci e' mai arrivata in questo "
                        "scenario, quindi A2 non ha avuto nemmeno un giro da guardare")
    fill = strategia.mercato.riepilogo_fill()
    conto = strategia.mercato.pnl(C.commission_rate(par))
    out.note.append(f"fill: {fill['fill']} abbinamenti su {fill['ordini_con_fill']} ordini "
                    f"per {fill['abbinato']} EUR (prezzi {fill['prezzi']})")
    out.note.append(f"P&L del replay: lordo {conto['lordo']:+.2f} | commissione "
                    f"{conto['commissione']:.2f} ({conto['aliquota'] * 100:.1f}%) | "
                    f"NETTO {conto['netto']:+.2f} EUR (non e' il metro della "
                    f"certificazione: il metro e' la condotta)")
    out.note.append(f"bet delay: {motore.pompati} book passati mentre i piazzamenti "
                    f"aspettavano Betfair | book arrivati in ritardo (orologio fermo): "
                    f"{motore.book_in_ritardo} | ordini appoggiati uccisi dal "
                    f"passaggio in gioco (LAPSE): {motore.lapse_al_fischio} | "
                    f"uccisi dalla SOSPENSIONE in gioco (gol/rigore/rosso): "
                    f"{motore.lapse_alla_sospensione}"
                    + (f" | {motore.senza_futuro} piazzamenti senza book futuro "
                       f"(registrazione finita): valutati sull'ultimo noto"
                       if motore.senza_futuro else ""))
    # L'ASSUNZIONE DELLE LETTURE, dichiarata insieme a quanto pesa: se il bot
    # legge poco, 120 ms per lettura non spostano niente; se legge molto, il
    # referto lo fa vedere invece di nasconderlo.
    out.note.append(
        f"chiamate di LETTURA a Betfair: {strategia.mercato.letture} "
        f"({strategia.mercato.letture / max(1, out.decisioni):.2f} per giro) | "
        f"latenza ASSUNTA {BANCO.LATENZA_LETTURA_S * 1000:.0f} ms per chiamata "
        f"(non misurata: `storia_operazioni.py` ha solo la catena del "
        f"piazzamento) -> {motore.tempo_letture:.1f} s di tempo di mercato "
        f"consumati, {motore.book_letture} book passati")
    out.note.append(f"righe di scan scritte dallo SCANNER VERO: {banco.righe_scritte}"
                    + (f" | giri senza riga nel feed: {strategia.righe_assenti}"
                       if strategia.righe_assenti else ""))
    if strategia.diff_visti:
        out.note.append(f"DIFF payload a mano vs scanner ({strategia.diff_campionati} "
                        f"campioni): " + " ; ".join(strategia.diff_visti[:12]))
    return out


# ---------------------------------------------------------------------------
# GLI SCENARI E IL COMANDO — il referto vive nel punto d'ingresso unico
# ---------------------------------------------------------------------------
# `Betfair/stream/backtest/certifica.py` produce il referto per TUTTI i bot
# leggendo il REGISTRO (`registro_bot.py`): qui restano solo i pezzi
# SPECIFICI di Mike, cioe' la strategia flumine e la mappa degli scenari.
# Non esistono due implementazioni del referto.
SCENARI_DESCRITTI: Dict[str, str] = {
    "base": "come gira in produzione",
    "taker": "uscita pre-match a mercato invece che appoggiata (§3 Fase 1)",
    "cap-stretto": "tetto di rischio stretto: fa parlare il clamp del motore (§4.9)",
    "bot-fermo": "bot fermo / stop giornaliero: nessuna apertura, chiusure vive (§5)",
    "senza-seconda-puntata": "seconda puntata spenta: l'altro ramo del gol precoce (§15.3)",
    SCENARIO_FEED_STANTIO: "riga E scanner vecchi: nessun ingresso, chiusure permesse (§5)",
    SCENARIO_ESITI_IGNOTI: "i primi piazzamenti a esito IGNOTO: gambe pending_reconcile (§4.11)",
    SCENARIO_TAKER_IGNOTI: "taker + esiti IGNOTI: e' l'unico modo di sollecitare J1 e J4 "
                           "sul percorso taker, dove ogni piazzamento si risolve nel giro",
    SCENARIO_RIAVVIO: "riavvio a meta' partita con posizione aperta: lo stato si ritrova dal DB",
    SCENARIO_GOL_PRECOCE: "gol nei primi minuti (registrazioni 35777617=2', 36006953=4', "
                          "35760084=7'): il mercato sospende, Betfair fa scadere la lay di "
                          "uscita appoggiata e alla riapertura il bot deve RILEGGERLA (§15.6, R1)",
    SCENARIO_CASHOUT_GLOBALE: "l'utente chiude a mano TUTTE le operazioni della partita "
                              "(richiesta `cashout` vera dalla UI): da li' in poi il bot non "
                              "apre piu' niente (§15.7-bis, R2)",
    SCENARIO_CHIUSO_FUORI_APP: "l'utente chiude la posizione FUORI dall'app (ordini veri su "
                               "flumine con un ref che non e' di Mike, piu' una posizione sua "
                               "sulla stessa selezione): il bot lo scopre dalla POSIZIONE DI "
                               "CONTO e non gestisce piu' quella partita (§15.7-ter, R3)",
    SCENARIO_COVER_RIFIUTATA: "Betfair rifiuta SEMPRE la copertura sotto minimo "
                              "(CANCELLED_NOT_PLACED / INVALID_BET_SIZE, come il 17/09 "
                              "sull'evento 36077571): sollecita il FRENO fail-closed "
                              "(S1) e il ritmo minimo fra due tentativi",
    SCENARIO_RIFIUTI: "Betfair RIFIUTA i primi piazzamenti (`ok=False`): l'esito si legge "
                      "e nessuna gamba rifiutata diventa una posizione (difetto 2 del "
                      "catalogo del 15/09)",
    # 23/09 (cancello C3) — parametri di `base`, un solo guasto del banco comune
    # (`Betfair/stream/backtest/chiusura_parziale.py`): la prima gamba di
    # chiusura su ogni selezione si abbina al piu' per il 40 %.
    CP.SCENARIO: "come `base`, ma " + CP.DESCRIZIONE,
}


def credenze_mike(db: Any, event_id: str) -> List[Dict[str, Any]]:
    """Le posizioni che MIKE crede di avere, una per selezione, per i controlli
    CP dello scenario `chiusura-abbinata-in-parte`.

    Mike non dichiara una copertura per riga (non usa `apply_hedge_state`):
    `coperto` resta None e CP2 non ha un caso (dichiarato nel referto). CHIUSA =
    lo stato della macchina `FLAT`, oppure un ciclo pre-match le cui gambe
    d'apertura sono tutte ARCHIVIATE (cioe' chiuse in green, `Leg.archived`).
    Le righe sono quelle di `mike_trades` (chiavi snake_case del vero); la
    posizione a mercato si misura su TUTTI gli ordini del bot sulla selezione.
    """
    ev = db.events.get(str(event_id))
    if not ev:
        return []
    ctx = S._ctx_from_row(ev, db)
    gambe = {str(g.ref): g for g in ctx.legs}
    per_chiave: Dict[Tuple[str, int], List[Dict[str, Any]]] = {}
    for r in db.trades_for_event(str(event_id)) or []:
        try:
            k = (str(r.get("market_id") or ""), int(r.get("selection_id") or 0))
        except (TypeError, ValueError):
            continue
        per_chiave.setdefault(k, []).append(r)
    out: List[Dict[str, Any]] = []
    for k, righe in per_chiave.items():
        aperture = [r for r in righe if str(r.get("role")) in E.OPENING_ROLES]
        chiusure = [r for r in righe if str(r.get("role")) in E.CLOSING_ROLES]
        g_ap = [gambe.get(str(r.get("signal_key"))) for r in aperture]
        g_ap = [g for g in g_ap if g is not None and float(g.matched or 0.0) > 0]
        archiviate = bool(g_ap) and all(bool(g.archived) for g in g_ap)
        out.append({
            "id": f"mike{k}",
            "chiave": k,
            "chiusa": ctx.state == "FLAT" or archiviate,
            "coperto": None,
            "apertura": None,
            "ingressi": [{"bet_id": r.get("bet_id")} for r in aperture],
            "chiusure": [{"bet_id": c.get("bet_id"), "id_riga": c.get("id"),
                          "status": c.get("status"),
                          "size": c.get("size"), "price": c.get("price"),
                          "size_requested": c.get("size_requested"),
                          "size_matched": c.get("size_matched"),
                          "size_remaining": c.get("size_remaining"),
                          "avg_price_matched": c.get("avg_price_matched")}
                         for c in chiusure],
            "per_selezione": True,
            "tolleranza": 0.0,
        })
    return out


def cadenza_ms(params: Dict[str, Any]) -> int:
    """OGNI QUANTO GIRA MIKE, letto dai SUOI parametri di produzione.

    In `service.main` il passo del ciclo e'
    ``max(1.0, decide_min_interval_ms/1000*2)`` (`Betfair/mike/service.py:3381`),
    e sale a ``idle_cycle_s`` quando non si muove niente. Il replay usa il passo
    PIENO: e' quello con cui il bot gira quando la partita e' viva, cioe' quando
    prende le decisioni che si vogliono certificare. Cablare qui un numero
    farebbe vedere al bot piu' (o meno) di quello che vedrebbe.
    """
    return int(max(1.0, float(params.get("decide_min_interval_ms", 500)) / 1000.0 * 2.0) * 1000)


def certifica_scenario(event_id: str, *, data_dir: str, scenario: str = "base",
                       ogni_ms: int = 0, campioni_diff: int = 0) -> CERT.Referto:
    """ADATTATORE PER IL BANCO — dal NOME dello scenario ai parametri di Mike.

    E' la funzione che il REGISTRO dei bot
    (`Betfair/stream/backtest/registro_bot.py`) chiama per certificare Mike:
    firma identica per tutti i bot, cosi' il comando
    `python -m Betfair.stream.backtest.certifica <bot>` e' uno solo.
    """
    par = dict(C.merge_params(None))
    par.update(SCENARI.get(scenario, {}))
    if scenario == SCENARIO_TAKER_IGNOTI:
        par.update(SCENARI["taker"])
    # il feed stantio si ottiene invecchiando la riga, non toccando i prezzi;
    # perche' il feed risulti STANTIO devono essere vecchi TUTTI E DUE: la riga
    # (`feed_max_age_s`) e lo scanner (`scanner_alive_max_s`). Con lo scanner
    # vivo una riga ferma e' legittima — e' write-on-change, vuol dire che i
    # prezzi non sono cambiati.
    vecchio = (max(float(par.get("feed_max_age_s") or 15.0),
                   float(par.get("scanner_alive_max_s") or 75.0)) * 3.0
               if scenario == SCENARIO_FEED_STANTIO else 0.0)
    ref = certifica_evento(
        event_id, data_dir=data_dir, params=par,
        # 0 = la cadenza del SERVIZIO, non una cablata nel banco
        ogni_ms=int(ogni_ms) or cadenza_ms(par),
        invecchia_s=vecchio,
        guasti=(QUANTI_GUASTI if scenario in (SCENARIO_ESITI_IGNOTI,
                                              SCENARIO_TAKER_IGNOTI) else 0),
        rifiuti=(QUANTI_RIFIUTI if scenario == SCENARIO_RIFIUTI else 0),
        cover_rifiutata=(scenario == SCENARIO_COVER_RIFIUTATA),
        campioni_diff=campioni_diff,
        riavvia=(scenario == SCENARIO_RIAVVIO),
        cashout_utente=(scenario == SCENARIO_CASHOUT_GLOBALE),
        chiuso_fuori_app=(scenario == SCENARIO_CHIUSO_FUORI_APP),
        chiusura_parziale=(scenario == CP.SCENARIO))
    if scenario == SCENARIO_GOL_PRECOCE:
        # Lo scenario DICHIARA se il caso e' capitato davvero. Un referto
        # "zero violazioni" su una registrazione senza gol precoce non dice
        # niente su §15.6: dice solo che non c'e' stato niente da giudicare.
        quante = int(ref.sollecitati.get("R1") or 0)
        ref.note.append(
            "scenario gol-precoce (§15.6): il controllo R1 «alla riapertura "
            f"l'ordine appoggiato e' stato riletto» e' stato sollecitato {quante} volte"
            + ("" if quante else " — su questa registrazione la sospensione con una "
                                "lay appoggiata viva NON e' mai capitata: serve una "
                                "partita con gol nei primi minuti (35777617)"))
    return ref


def main(argv: Optional[List[str]] = None) -> int:
    """CHIAMANTE SOTTILE del punto d'ingresso unico.

    Il referto, la copertura dei controlli, il diario e il filtro delle
    registrazioni COMPLETE vivono in `Betfair/stream/backtest/certifica.py` e
    valgono per TUTTI i bot: qui non se ne tiene una seconda copia. Il comando
    storico continua a funzionare ed equivale a
    `python -m Betfair.stream.backtest.certifica mike ...`.
    """
    from ...stream.backtest.certifica import main as certifica_main

    return certifica_main(["mike"] + list(argv if argv is not None
                                          else sys.argv[1:]))


if __name__ == "__main__":
    sys.exit(main())
