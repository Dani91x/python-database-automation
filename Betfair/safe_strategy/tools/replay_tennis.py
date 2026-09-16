"""SAFE TENNIS SULLE REGISTRAZIONI VERE — il replay col motore ufficiale Betfair.

C.4 del `PIANO_CERTIFICAZIONE_DEFINITIVA_2026-09-16.md`. Fa rivivere alla
strategia TENNIS di Safe una partita registrata, giro per giro, coi prezzi veri
di Betfair, e a ogni giro verifica le regole di `SPEC_STRATEGIA_S.md` §3
(`Betfair/safe_strategy/certificazione_tennis.py`). Non misura il profitto:
misura la CONDOTTA.

LA CATENA, e nessun passo e' saltato:

    raw registrato  `~/Desktop/tennis_rec/<giorno>/<id>/<id>.raw.jsonl`
      -> flumine    `FlumineSimulation` + `HistoricalStream` (banco comune)
      -> SCANNER VERO   `safe_strategy.service.Scanner._apply_market_book`
                        con sport TENNIS: il catalogo nasce dai
                        `marketDefinition` (`ScannerReplay.registra_mercato` ->
                        `scanner.tennis_sides`), i PUNTEGGI entrano da
                        `Scanner.apply_score_state`, cioe' dalla stessa funzione
                        che usa `poll_scores` in produzione, che per il tennis
                        passa da `parse_tennis_scores` e scrive `sets`/`games`
      -> `build_rows` VERA -> riga `safe_strategy_scan` in memoria
      -> `engine.build_tennis_ctx_from_scan` + `engine.evaluate_tennis` VERI,
         con `track_tennis_score_stability` dentro `SafeEngine._ingest`
      -> `bot_service.run_once` VERO (il giro intero: coda flumine,
         riconciliazione, richieste della UI, settlement, uscite, segnali,
         opportunita')
      -> ordini VERI su flumine (`execution.place` -> `MercatoFlumine`),
         FILL_OR_KILL, bet delay, `close_plan` al best opposto.

-----------------------------------------------------------------------------
TRE DICHIARAZIONI, perche' un banco che non le fa e' peggio di nessun banco
-----------------------------------------------------------------------------

1. IL CATALOGO NON C'E' (limite 1 del banco comune). Nel raw dello stream non
   esistono ne' i nomi dei giocatori ne' la COMPETIZIONE: i nomi li porta il
   sidecar dei punteggi, la competizione no. Ma `evaluate_tennis` ha bisogno
   della competizione per il filtro «al meglio dei 3 set» (`excludeBestOf5`,
   acceso di default): senza, quel check esce `n/d`, `state_from_checks` da'
   "nd" e NESSUN ingresso e' possibile — mai. E' un falso negativo DEL BANCO,
   non un comportamento del bot: in produzione la competizione arriva da
   `listMarketCatalogue`. Qui si DICHIARA con `--competizione`, come gia' si fa
   con `ScannerReplay(nomi_extra=...)` per i nomi del Correct Score; lo scenario
   `catalogo-assente` mostra che cosa succede senza.

2. IL FRENO LIVE E' DI PROCESSO. `execution._live_brake` legge
   `LIVE_ORDER_MODE`/`LIVE_KILL_SWITCH` dall'ambiente: con i valori di riposo
   (`OFF`) il percorso LIVE non partirebbe MAI e il replay direbbe che il bot
   non fa niente. Nel replay si dichiara `LIVE_ORDER_MODE=LIVE` per la durata
   del giro e lo si rimette com'era (`_freni_live_dichiarati`): gli ordini
   restano simulati da flumine, i soldi veri non esistono.

3. L'INGRESSO PUO' NON ESSERE ESERCITABILE. Su una registrazione in cui la
   strategia non ha MAI le sue condizioni, uscite, ordini e approvazione non si
   possono certificare: lo scenario `posizione-iniettata` apre una posizione
   con le funzioni di PRODUZIONE (`_reserve_row` + `_execute` + `execution.place`
   su flumine) al primo giro utile, DICHIARANDO che il trigger non e' della
   strategia. Tutto cio' che viene dopo (tracciamento, uscite, proposta,
   approvazione, ordini, riconciliazione, settlement) e' codice di produzione
   su dati veri, e i controlli sull'INGRESSO restano ⊘ in quello scenario.

Uso:
    python -m Betfair.safe_strategy.tools.replay_tennis 35790650
    python -m Betfair.safe_strategy.tools.replay_tennis 35790650 --scenari tutti
    python -m Betfair.safe_strategy.tools.replay_tennis 35790650 --diario diario.txt

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import sys
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from .. import bot_db as BOTDB
from .. import bot_service as BS
from .. import certificazione_tennis as CERT
from .. import engine as E
from .. import exits as XE
from .. import risk as RK
from ...stream.backtest.banco_comune import DbMemoria, replay_evento

logger = logging.getLogger(__name__)

# la registrazione di riferimento (regola operativa del piano, 16/09 h11:40)
EVENTO_DI_RIFERIMENTO = "35790650"


# ---------------------------------------------------------------------------
# il database in memoria, con le firme di `safe_strategy/bot_db.py`
# ---------------------------------------------------------------------------
class DbMemoriaSafe(DbMemoria):
    """Le tabelle di Safe in RAM, con le FIRME e i TIPI DI RITORNO del vero.

    `Betfair/safe_strategy/bot_db.py` e' l'accessor che `bot_service.run_once`
    usa in produzione (`_real_db`): ogni metodo qui sotto ha la sua stessa firma
    e restituisce lo stesso tipo — `insert_trade` l'ID e non la riga,
    `traded_signal_keys` un set di tuple, `aggregates` il dizionario con le
    dodici chiavi di `_AGG_KEYS`. Un doppio che risponde a domande a cui il vero
    non risponde e' la causa di tutti i difetti del 15/09.

    Gli AGGREGATI non sono ricalcolati qui: si chiama `bot_db.aggregate_rows`,
    che e' la stessa funzione PURA che il vero usa quando la RPC non c'e'.
    """

    def __init__(self, control: Dict[str, Any], *, orologio) -> None:
        super().__init__(control)
        self._ora = orologio                 # () -> datetime UTC del replay
        self.richieste: List[Dict[str, Any]] = []
        self._rid = 0

    # --------------------------------------------------------------- tempo
    def _adesso(self) -> datetime:
        return self._ora()

    def _iso(self) -> str:
        return self._adesso().isoformat()

    # -------------------------------------------------------------- trades
    def insert_trade(self, trade: Dict[str, Any]) -> Optional[int]:
        """Il vero torna l'ID. `placed_at` lo mette il DEFAULT della colonna sul
        DB: qui lo mette l'orologio del replay, o la giornata operativa non
        esisterebbe e tutti gli aggregati del giorno sarebbero zero."""
        riga = dict(trade)
        riga.setdefault("placed_at", self._iso())
        # INDICE UNICO `uq_safe_trades_signal` (event_id, signal_key) sulle sole
        # righe automatiche non di chiusura: e' il LOCK che impedisce il doppio
        # piazzamento. Senza, il banco sarebbe piu' permissivo del DB vero.
        if (str(riga.get("origin") or "") == "auto" and riga.get("signal_key")
                and riga.get("closes_trade_id") is None):
            chiave = (str(riga.get("event_id")), str(riga.get("signal_key")))
            for r in self.trades:
                if (r.get("closes_trade_id") is None
                        and str(r.get("origin") or "") == "auto"
                        and str(r.get("status")) != "error"
                        and (str(r.get("event_id")), str(r.get("signal_key"))) == chiave):
                    raise RuntimeError(
                        "uq_safe_trades_signal: segnale gia' riservato "
                        f"({chiave[0]}, {chiave[1]})")
        return super().insert_trade(riga)

    def delete_trade(self, trade_id: int) -> None:
        self.trades = [r for r in self.trades if int(r.get("id") or 0) != int(trade_id)]

    def get_trade(self, trade_id: int) -> Optional[Dict[str, Any]]:
        for r in self.trades:
            if int(r.get("id") or 0) == int(trade_id):
                return dict(r)
        return None

    def list_trades(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.trades
                if status is None or str(r.get("status")) == str(status)]

    def open_trades(self, mode: Optional[str] = None) -> List[Dict[str, Any]]:
        m = BOTDB._norm_mode(mode)
        return [dict(r) for r in self.trades
                if str(r.get("status")) in ("open", "hedged", "pending")
                and (m is None or BOTDB.row_mode(r) == m)]

    def closing_trades_for(self, trade_ids: List[int]) -> List[Dict[str, Any]]:
        voluti = {int(i) for i in trade_ids or []}
        return [dict(r) for r in self.trades
                if r.get("closes_trade_id") is not None
                and int(r["closes_trade_id"]) in voluti]

    def trade_by_idempotency_key(self, key: str,
                                 mode: Optional[str] = None) -> Optional[Dict[str, Any]]:
        m = BOTDB._norm_mode(mode)
        for r in self.trades:
            if str(r.get("status")) == "error":
                continue
            if m is not None and BOTDB.row_mode(r) != m:
                continue
            if str((r.get("meta") or {}).get("idempotency_key") or "") == str(key):
                return dict(r)
        return None

    def traded_signal_keys(self, mode: Optional[str] = None) -> set:
        """STESSO FILTRO dell'indice unico del DB (`uq_safe_trades_signal`):
        automatiche, non in errore, non gambe di chiusura."""
        m = BOTDB._norm_mode(mode)
        out = set()
        for r in self.trades:
            if str(r.get("origin") or "") != "auto" or str(r.get("status")) == "error":
                continue
            if r.get("closes_trade_id") is not None:
                continue
            if m is not None and BOTDB.row_mode(r) != m:
                continue
            if r.get("event_id") and r.get("signal_key"):
                out.add((str(r["event_id"]), str(r["signal_key"])))
        return out

    def aggregates(self, now: Optional[datetime] = None,
                   mode: Optional[str] = None) -> Dict[str, float]:
        adesso = now or self._adesso()
        return BOTDB.aggregate_rows(list(self.trades),
                                    RK.operating_day_start(adesso), mode)

    def place_attempts(self) -> Dict[Tuple[str, str], Dict[str, Any]]:
        out: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for r in self.trades:
            if str(r.get("origin") or "") != "auto" or str(r.get("status")) != "error":
                continue
            pl = (r.get("meta") or {}).get("place")
            if not (r.get("event_id") and r.get("signal_key") and isinstance(pl, dict)):
                continue
            out[(str(r["event_id"]), str(r["signal_key"]))] = {
                "attempts": int(pl.get("attempts") or 0),
                "last_ts": pl.get("last_ts"), "final": bool(pl.get("final"))}
        return out

    def recent_activity(self, limit: int = 60) -> List[Dict[str, Any]]:
        return [{"kind": k, "payload": p} for k, p, _e in self.attivita[-int(limit):]]

    # ------------------------------------------------- richieste della UI
    def pending_requests(self, limit: int = 50) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.richieste
                if str(r.get("status")) == "pending"][:int(limit)]

    def set_request_status(self, req_id: int, status: str,
                           result: Optional[Dict[str, Any]] = None) -> None:
        for r in self.richieste:
            if int(r.get("id") or 0) == int(req_id):
                r["status"] = str(status)
                if result is not None:
                    r["result"] = dict(result)
                r["updated_at"] = self._iso()
                return

    def fail_stale_processing(self, max_age_min: int = 10) -> None:
        return None

    def proposta_di_chiusura_viva(self, trade_id: int) -> Optional[Dict[str, Any]]:
        for r in self.richieste:
            if (str(r.get("status")) == "proposed"
                    and str((r.get("payload") or {}).get("trade_id")) == str(int(trade_id))):
                return dict(r)
        return None

    def scrivi_proposta_di_chiusura(self, trade_id: int,
                                    payload: Dict[str, Any]) -> Optional[int]:
        corpo = {**payload, "trade_id": int(trade_id)}
        viva = self.proposta_di_chiusura_viva(trade_id)
        if viva is not None:
            for r in self.richieste:
                if int(r.get("id") or 0) == int(viva["id"]):
                    r["payload"] = corpo
                    r["updated_at"] = self._iso()
                    return int(viva["id"])
        self._rid += 1
        self.richieste.append({"id": self._rid, "kind": "cashout", "status": "proposed",
                               "payload": corpo, "created_at": self._iso(),
                               "updated_at": self._iso()})
        return self._rid

    def chiudi_proposta(self, trade_id: int, motivo: str) -> None:
        viva = self.proposta_di_chiusura_viva(trade_id)
        if viva is None:
            return
        for r in self.richieste:
            if int(r.get("id") or 0) == int(viva["id"]):
                r["status"] = "rejected"
                r["result"] = {**(r.get("result") or {}), "decaduta": True,
                               "motivo": str(motivo)[:200]}
                r["updated_at"] = self._iso()

    # ----------------------------------------------- opportunita' e feed
    def upsert_opportunities(self, rows: List[Dict[str, Any]]) -> None:
        return None

    def purge_opportunities(self, older_than_iso: str) -> None:
        return None

    def delete_opportunities(self, event_ids: List[str]) -> None:
        return None

    def scanner_status(self, *_a: Any, **_k: Any) -> Optional[Dict[str, Any]]:
        """IL BATTITO DELLO SCANNER, come in produzione.

        In produzione `ScoreFeedWorker` riscrive `safe_strategy_status` ogni
        `_STATUS_PERIOD_SEC`: e' cio' che permette a una riga ferma (per
        write-on-change) di restare utilizzabile. Senza questo metodo il banco
        sarebbe piu' severo del vero e NESSUN ingresso passerebbe mai il
        controllo di freschezza. L'invecchiamento dichiarato dello scenario
        `feed-stantio` agisce qui e sulla riga insieme, come nel vero."""
        vecchio = float(getattr(self, "scanner_vecchio_s", 0.0) or 0.0)
        ts = self._adesso().timestamp() - vecchio
        return {"updated_at": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()}

    # --------------------------------- dati che la registrazione NON contiene
    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        self._dichiara("get_event", "anagrafica evento (tabella events): non e' "
                                    "nello stream registrato")
        return None

    def fixtures_for_window(self, start_iso: str, end_iso: str) -> List[Dict[str, Any]]:
        self._dichiara("fixtures_for_window", "fixture del calcio: non pertinenti al tennis")
        return []

    def fixture_analysis(self, fixture_id: int) -> Optional[Dict[str, Any]]:
        return None

    def live_follow_status(self, event_id: str) -> Optional[str]:
        """Il gate della coda flumine chiede se l'evento e' in STREAMING sul
        runner. Nel replay il runner non esiste: None = gate CHIUSO (fail-closed
        dichiarato da `omega_service._flumine_gate`) e si passa dal percorso
        REST, che e' quello che finisce su flumine."""
        self._dichiara("live_follow_status", "coda del runner (live_follow): non "
                                             "esiste nel replay, il gate resta chiuso "
                                             "e gli ordini passano dal percorso REST")
        return None

    def runner_heartbeat(self) -> Optional[Dict[str, Any]]:
        return None

    def enqueue_live_order(self, payload: Dict[str, Any]) -> Optional[int]:
        return None

    def get_live_order_request(self, request_id: int) -> Optional[Dict[str, Any]]:
        return None

    def get_live_order_request_by_ref(self, client_ref: str) -> Optional[Dict[str, Any]]:
        return None

    def revoke_live_order_request(self, request_id: int) -> bool:
        return False

    def get_live_order_mirror(self, client_order_ref: str,
                              mode: str = "paper") -> Optional[Dict[str, Any]]:
        return None

    def _dichiara(self, nome: str, causa: str) -> None:
        voce = (nome, causa)
        if voce not in self.senza_dato:
            self.senza_dato.append(voce)


# ---------------------------------------------------------------------------
# GLI SCENARI — le condizioni rare non si aspettano, si provocano
# ---------------------------------------------------------------------------
# Cambiano SOLO parametri, freschezza del feed o guasti iniettati: mai la
# partita, mai i prezzi, mai la strategia (PROCESSO_STANDARD_BOT §6.7).
SCENARI_DESCRITTI: Dict[str, str] = {
    "base": "come gira in produzione, percorso LIVE su flumine, competizione dichiarata",
    "paper": "stessa cosa in PAPER (percorso legacy: fill sul libro del feed, FOK)",
    "paper-iniettata": "PAPER con la posizione dichiarata: e' il percorso legacy del "
                       "paper (`_paper_ladder` + `omega_engine.paper_fill`, FOK) messo "
                       "accanto a quello LIVE su flumine — reperto per la parita' C.5",
    "catalogo-assente": "senza competizione dichiarata: mostra il falso negativo del "
                        "banco (check `bestOf` n/d -> nessun ingresso possibile)",
    "posizione-iniettata": "ingresso DICHIARATO dal replay (la strategia non ne ha "
                           "mai uno su questa partita): esercita uscite e ordini",
    "approvata-subito": "posizione iniettata + `tennis_exit_approval` acceso e il "
                        "trader che firma la proposta al giro dopo",
    "mai-approvata": "posizione iniettata + `tennis_exit_approval` acceso e NESSUNA "
                     "firma: la chiusura resta ferma, come in produzione",
    "bot-fermo": "control.status='stopped' con posizione aperta: niente aperture, "
                 "le uscite e il settlement continuano",
    "feed-stantio": "riga E battito dello scanner vecchi: nessun ingresso",
    "esiti-ignoti": "i primi piazzamenti sollevano: nasce la riconciliazione",
    "rifiuti-betfair": "Betfair RIFIUTA (`ok=False`) i primi piazzamenti sul lato "
                       "BACK, quello con cui il tennis APRE: la riga non deve mai "
                       "restare viva su un ordine che non esiste (difetto 2 del "
                       "15/09, controllo K2)",
    "uscita-ignota": "il guasto colpisce la CHIUSURA, non l'apertura: resta una LAY "
                     "in volo a esito ignoto e si guarda se ne nasce una seconda "
                     "(regola di piattaforma: mai due lay sulla stessa selezione)",
    "riavvio": "a meta' partita si buttano le cache di PROCESSO di bot_service: lo "
               "stato si deve ritrovare dal database",
    "chiusura-fuori-app": "posizione del bot aperta, e il trader la chiude con un "
                          "ordine SUO su Betfair (ref non del bot), fuori dall'app: "
                          "il bot deve accorgersene dalla POSIZIONE DI CONTO, "
                          "scrivere `chiuso_dall_utente` e non fare altro",
    "chiusura-fuori-app-ridotta": "come sopra ma il trader chiude solo META' della "
                                  "posizione: il bot lo DICHIARA "
                                  "(`ridotta_dall_utente`) e continua a proteggere "
                                  "il resto",
}

QUANTI_GUASTI = 3
QUANTI_RIFIUTI = 3


@contextmanager
def _freni_live_dichiarati(attivo: bool):
    """DICHIARAZIONE 2 in testa al modulo: i freni live sono di PROCESSO.

    `execution._live_brake` rilegge `LIVE_ORDER_MODE`/`LIVE_KILL_SWITCH`
    dall'ambiente a ogni ordine. Con i valori di riposo il percorso LIVE del
    replay non partirebbe mai. Qui si dichiarano per la durata del giro e si
    rimettono com'erano: gli ordini restano quelli simulati di flumine."""
    if not attivo:
        yield False
        return
    prima = {k: os.environ.get(k) for k in ("LIVE_ORDER_MODE", "LIVE_KILL_SWITCH")}
    os.environ["LIVE_ORDER_MODE"] = "LIVE"
    os.environ["LIVE_KILL_SWITCH"] = "false"
    try:
        yield True
    finally:
        for k, v in prima.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _pulisci_processo() -> List[str]:
    """Butta via le cache di PROCESSO del servizio, come un riavvio.

    ⚠️ 16/09 SERA - QUI C'ERA UNA SECONDA COPIA DELL'ELENCO, piu' corta di
    quella del calcio (mancavano `_CONTO_LETTO_A` e `_EVENTI_CHIUSI`) e per di
    piu' SBAGLIATA: svuotava con `.clear()` anche `_APERTE`, `_BLOCCO`,
    `_LETTURA_FEED` e `_SCANNER_TS_CACHE`, che hanno CHIAVI FISSE lette senza
    `.get` (`_APERTE["n"]`) - un `KeyError` al primo giro, cioe' un guasto del
    banco scambiato per un difetto del bot. Il servizio e' lo STESSO
    (`bot_service`) per calcio e tennis: l'elenco e' uno solo, esplicito, e vive
    in `replay_registrazioni` (difetto 37 del catalogo: due elenchi che
    divergono sono peggio di nessun elenco).

    Non tocca il database in memoria: quello e' il DB, e in produzione
    sopravvive. Torna l'elenco di cio' che e' stato azzerato - un riavvio che
    non si sa che cosa ha buttato non prova niente (difetto 19 del catalogo:
    `pre_ko` viveva solo in RAM).
    """
    from .replay_registrazioni import _riavvia_processo

    return _riavvia_processo()


def _azzera_stato_di_processo() -> None:
    """Prima di OGNI replay: le cache di modulo sono di processo e due scenari
    nello stesso interprete non devono potersi sporcare a vicenda."""
    _pulisci_processo()      # comprende `_GUARDIA_AVVIO` e le chiavi fisse


# ---------------------------------------------------------------------------
# i parametri di ogni scenario
# ---------------------------------------------------------------------------
def parametri_scenario(scenario: str) -> Dict[str, Any]:
    """I parametri del CONTROL per uno scenario.

    ⚠️ La sezione `tennis` (soglie, bande, esclusioni) NON si tocca in nessuno
    scenario: e' la strategia. Qui si muovono solo le leve che l'utente ha nella
    Control Room — varianti accese, modalita' per strategia, cancelletto di
    approvazione, stato del bot.
    """
    live = scenario not in ("paper", "paper-iniettata")
    par: Dict[str, Any] = {
        # SOLO il tennis: la scheda tennis della Control Room accende questa
        "variants": ["tennis"],
        # CERT. 14/09 — la modalita' si SCRIVE, non si eredita
        "strategy_modes": {"tennis": "live" if live else "paper"},
        "tennis_exit_approval": False,
        # le opportunita' di modello non sono la strategia: restano spente come
        # in produzione (auto_trade_* tutti False di default)
        "opps_interval_s": 30,
    }
    if scenario in ("approvata-subito", "mai-approvata"):
        par["tennis_exit_approval"] = True
    return par


def _modo_control(scenario: str) -> str:
    return "paper" if scenario in ("paper", "paper-iniettata") else "live"


# ---------------------------------------------------------------------------
# il replay di UN evento
# ---------------------------------------------------------------------------
def certifica_evento(event_id: str, *, data_dir: str, scenario: str = "base",
                     ogni_ms: int = 0, competizione: Optional[str] = None,
                     campioni_diff: int = 0) -> CERT.Referto:
    """Fa rivivere a Safe tennis una partita registrata e ritorna il referto."""
    ref = CERT.Referto(event_id=str(event_id))
    raw = os.path.join(data_dir, str(event_id), f"{event_id}.raw.jsonl")
    if not os.path.exists(raw):
        ref.note.append(f"registrazione assente: {raw}")
        return ref

    _azzera_stato_di_processo()
    par_control = parametri_scenario(scenario)
    modo = _modo_control(scenario)
    stato = "stopped" if scenario == "bot-fermo" else "running"
    comp = None if scenario == "catalogo-assente" else competizione
    # gli scenari che devono avere una POSIZIONE per dire qualcosa: senza, uscite,
    # ordini, approvazione e riconciliazione non hanno un caso da giudicare
    inietta = scenario in ("posizione-iniettata", "approvata-subito", "mai-approvata",
                           "bot-fermo", "riavvio", "esiti-ignoti",
                           "paper-iniettata", "uscita-ignota", "rifiuti-betfair",
                           "chiusura-fuori-app", "chiusura-fuori-app-ridotta")
    firma = _Stato(ref=ref, scenario=scenario, competizione=comp, inietta=inietta,
                   approva=(scenario == "approvata-subito"),
                   riavvia=(scenario == "riavvio"))

    orologio: Dict[str, Any] = {"now": datetime.now(timezone.utc)}
    db = DbMemoriaSafe({"status": stato, "mode": modo, "params": par_control},
                       orologio=lambda: orologio["now"])
    # feed stantio: la riga E il battito dello scanner vecchi insieme, che e' la
    # sola condizione in cui `feed_is_fresh` dice no (write-on-change: una riga
    # ferma con lo scanner vivo e' legittima)
    if scenario == "feed-stantio":
        db.scanner_vecchio_s = float(XE.FEED_HARD_MAX_S) * 3.0
    firma.db = db
    firma.invecchia_s = (float(XE.FEED_HARD_MAX_S) * 3.0
                         if scenario == "feed-stantio" else 0.0)
    firma.guasti = QUANTI_GUASTI if scenario in ("esiti-ignoti",
                                                  "uscita-ignota") else 0
    firma.rifiuti = QUANTI_RIFIUTI if scenario == "rifiuti-betfair" else 0
    firma.guasti_sull_uscita = (scenario == "uscita-ignota")
    firma.fuori_app = ("intera" if scenario == "chiusura-fuori-app" else
                       ("ridotta" if scenario == "chiusura-fuori-app-ridotta"
                        else None))

    def servizio(*, db, market, now, row, banco, strategia):  # noqa: A002
        orologio["now"] = now
        firma.giro(db=db, market=market, now=now, row=row, banco=banco,
                   strategia=strategia)

    with _freni_live_dichiarati(modo == "live"):
        esito = replay_evento(event_id=str(event_id), cartella=data_dir,
                              servizio=servizio, sport="tennis",
                              ogni_ms=int(ogni_ms) or cadenza_ms(par_control),
                              pre_ko_ou_hours=0.0, db=db)
        giri_dopo_il_fischio(firma, raw)
    firma.chiudi(esito)
    return ref


def esito_finale_dal_raw(raw: str) -> Dict[str, Dict[str, Any]]:
    """L'ULTIMO `marketDefinition` di ogni mercato della registrazione.

    A mercato chiuso porta gli esiti veri (WINNER/LOSER) ed è l'unico posto
    dove stanno: lo si legge dal file, non lo si inventa. Stessa tecnica già
    usata dal replay calcio per i nomi del Correct Score.
    """
    import json

    out: Dict[str, Dict[str, Any]] = {}
    try:
        with open(raw, encoding="utf-8") as fh:
            for riga in fh:
                try:
                    msg = json.loads(riga)
                except ValueError:
                    continue
                for mc in msg.get("mc") or []:
                    md = mc.get("marketDefinition")
                    if not md:
                        continue
                    out[str(mc.get("id") or "")] = {
                        "status": str(md.get("status") or "OPEN").upper(),
                        "inplay": bool(md.get("inPlay")),
                        "runners": {int(r["id"]): str(r.get("status") or "").upper()
                                    for r in (md.get("runners") or [])
                                    if r.get("id") is not None},
                    }
    except OSError as ex:  # noqa: BLE001
        logger.warning("[safe.tennis] esito finale non letto: %s", ex)
    return out


def giri_dopo_il_fischio(firma: Any, raw: str, quanti: int = 3) -> int:
    """Fa girare il servizio ANCORA, a mercato CHIUSO, per il SETTLEMENT.

    PERCHE' SERVE, misurato il 16/09: flumine consegna un mercato chiuso a
    `process_closed_market`, non a `process_market_book`, e il ponte del banco
    comune inoltra solo il secondo. Risultato: l'ultimo giro del servizio
    avviene con il mercato ancora OPEN e il bot non vede MAI la chiusura —
    per questo T8 (che vuole una riga `settled`) non aveva mai un caso. Non
    è «manca una partita che arrivi a CLOSED»: nemmeno una che ci arriva
    basterebbe.

    Qui si fa quello che fa già il replay di Omega («3 giri dopo il fischio
    per il settlement da WINNER»): l'esito finale si legge dal
    `marketDefinition` REGISTRATO (`esito_finale_dal_raw`), si mette nelle
    definizioni del mercato — le stesse che `registra_definizione` riempirebbe
    — e si chiama il servizio VERO altre `quanti` volte. Nessun fill, nessun
    P&L scritto a mano: il settlement lo fa `bot_service`.
    """
    if firma.mercato is None or firma.db is None or firma.ultimo_now is None:
        return 0
    if not hasattr(firma.mercato, "definizioni"):
        return 0
    finali = esito_finale_dal_raw(raw)
    chiusi = {mid: d for mid, d in finali.items()
              if str(d.get("status")) in ("CLOSED", "SETTLED", "VOID", "VOIDED")}
    if not chiusi:
        return 0
    firma.mercato.definizioni.update(chiusi)
    fatti = 0
    for i in range(int(quanti)):
        adesso = firma.ultimo_now + timedelta(seconds=2 * (i + 1))
        try:
            firma.giro(db=firma.db, market=firma.mercato, now=adesso, row=None,
                       banco=firma.banco, strategia=firma.strategia)
        except Exception as ex:  # noqa: BLE001 - un giro che esplode E' un referto
            firma.ref.note.append(f"giro di settlement fallito: "
                                  f"{type(ex).__name__}: {ex}")
            break
        fatti += 1
    firma.giri_di_chiusura = fatti
    return fatti


def abilita_settlement(mercato: Any, strategia: Any) -> bool:
    """Dà al mercato del banco le LETTURE che gli mancano, senza toccarlo.

    LIMITE 8 del banco: `MercatoFlumine` piazza e annulla ma non espone
    `read_market`/`read_markets`, quindi `bot_service` non può leggere l'esito
    del mercato CHIUSO e il SETTLEMENT non avviene mai — ed è la ragione per
    cui il controllo T8 non ha mai avuto un caso sul tennis (⊘ dichiarato il
    16/09), non la mancanza di una partita che arrivi a CLOSED.

    Qui NON si scrive un mercato nuovo e non si tocca il banco comune (è di
    un'altra sessione): si riusa `MercatoSafe`, già scritto e già certificato
    per il calcio (C.3), appoggiando i suoi due metodi all'oggetto esistente.
    Il contenuto non è inventato: viene dal `marketDefinition` della
    registrazione, che a mercato chiuso porta i WINNER/LOSER veri.
    Torna True se il settlement è stato abilitato adesso.
    """
    import types

    from .replay_registrazioni import MercatoSafe

    acceso = False
    if not hasattr(mercato, "read_market"):
        mercato.definizioni = {}
        mercato.read_market = types.MethodType(MercatoSafe.read_market, mercato)
        mercato.read_markets = types.MethodType(MercatoSafe.read_markets, mercato)
        mercato.registra_definizione = types.MethodType(
            MercatoSafe.registra_definizione, mercato)
        acceso = True
    for mkt in (getattr(strategia, "mercati", None) or {}).values():
        mb = getattr(mkt, "market_book", None)
        if mb is not None:
            mercato.registra_definizione(mb)
    return acceso


def cadenza_ms(params: Dict[str, Any]) -> int:
    """OGNI QUANTO GIRA SAFE, letto dai SUOI parametri di produzione.

    `bot_service.main` dorme `poll_interval_s` fra un `run_once` e l'altro
    (default 2 s). Cablare qui un numero farebbe vedere al bot piu' (o meno) di
    quello che vedrebbe in live."""
    v = params.get("poll_interval_s")
    try:
        sec = float(v) if v is not None else float(BS.DEFAULT_PARAMS["poll_interval_s"])
    except (TypeError, ValueError):
        sec = float(BS.DEFAULT_PARAMS["poll_interval_s"])
    return int(max(0.5, sec) * 1000)


# ---------------------------------------------------------------------------
# lo stato del replay fra un giro e l'altro
# ---------------------------------------------------------------------------
class _Stato:
    """Tiene il filo fra un giro e l'altro e costruisce l'osservazione."""

    def __init__(self, *, ref: CERT.Referto, scenario: str,
                 competizione: Optional[str], inietta: bool, approva: bool,
                 riavvia: bool) -> None:
        self.ref = ref
        self.scenario = scenario
        self.competizione = competizione
        self.inietta = inietta
        self.approva = approva
        self.riavvia = riavvia
        self.db: Optional[DbMemoriaSafe] = None
        self.invecchia_s = 0.0
        self.guasti = 0
        self._guasti_messi = False
        # RIFIUTO DICHIARATO di Betfair (`ok=False`) sul lato con cui il tennis
        # APRE: e' l'unico modo di avere un caso per K2 (difetto 2 del 15/09).
        self.rifiuti = 0
        self._rifiuti_messi = False
        # `uscita-ignota`: il guasto si arma solo QUANDO c'e' una posizione
        # aperta, cosi' colpisce la gamba di CHIUSURA e non l'apertura
        self.guasti_sull_uscita = False
        self.engine = E.SafeEngine(dict(BS.DEFAULT_PARAMS), clock=lambda: self._ora)
        self._ora = 0.0
        self._refs_visti: set = set()
        # quanto era gia' stato ANNULLATO su ogni ordine al giro precedente: la
        # crescita di `size_cancelled` e' un annullo avvenuto ADESSO (controllo
        # L2, sostituzione cancel+place nello stesso giro)
        self._cancellato_prima: Dict[str, float] = {}
        self._id_visti: set = set()
        self._stati_riga: Dict[int, str] = {}
        self._n_attivita = 0
        self._iniettata = False
        self._riavvio_fatto: Optional[List[str]] = None
        self.righe_assenti = 0
        self.approvazioni = 0
        self.proposte_viste: set = set()
        self.motivi: Counter = Counter()
        self.mercato = None
        self.settlement_abilitato = False
        self.banco = None
        self.strategia = None
        self.ultimo_now = None
        self.giri_di_chiusura = 0
        # CHIUSURA FUORI DALL'APP: "intera" | "ridotta" | None
        self.fuori_app: Optional[str] = None
        self.fuori_app_fatta: Optional[Dict[str, Any]] = None
        # {event_id: istante} saputo dal REPLAY, non dal bot
        self.chiuso_dall_utente: Dict[str, float] = {}

    # ------------------------------------------------------------- un giro
    def giro(self, *, db, market, now, row, banco, strategia) -> None:
        self.mercato = market
        self.banco = banco
        self.strategia = strategia
        self.ultimo_now = now
        # le letture del mercato CHIUSO (settlement): vedi `abilita_settlement`
        self.settlement_abilitato = (abilita_settlement(market, strategia)
                                     or self.settlement_abilitato)
        self._ora = now.timestamp()
        self.ref.tick += 1
        if self.guasti and not self._guasti_messi and not self.guasti_sull_uscita:
            market.guasti["place_exception"] = int(self.guasti)
            self._guasti_messi = True
        if self.rifiuti and not self._rifiuti_messi:
            # i primi N piazzamenti tornano `ok=False`: risposta RICEVUTA,
            # nessun ordine a mercato. Sul lato BACK, che e' quello con cui il
            # tennis apre (`_apri_dichiarata` -> `execution.place`).
            market.guasti["place_rifiuto"] = int(self.rifiuti)
            market.rifiuta_lato = "back"
            self._rifiuti_messi = True
        # DICHIARAZIONE 1: la competizione, che il raw non ha e il catalogo si'.
        # Si scrive nel CATALOGO dello scanner (dove la metterebbe
        # `refresh_catalogue`), non nella riga: da li' in poi e' `build_rows`
        # vera a portarla nel payload. La ri-pubblicazione forzata avviene una
        # volta sola, alla transizione, per non falsare il write-on-change.
        if self.competizione is not None:
            for meta in banco.scan.sports["tennis"].metas.values():
                meta["competition"] = self.competizione
            if row is not None and row.get("payload", {}).get("competition") != self.competizione:
                banco.scan.written_sig.pop(str(self.ref.event_id), None)
                banco.pubblica()
                row = banco.riga(str(self.ref.event_id)) or row
        if row is None:
            self.righe_assenti += 1
        elif self.invecchia_s > 0:
            vecchio = datetime.fromtimestamp(self._ora - self.invecchia_s,
                                             tz=timezone.utc).isoformat()
            row = dict(row, updated_at=vecchio)
        db.scan_rows = [row] if row is not None else []

        params = BS.resolve_params(db.read_control().get("params"))
        self.engine.update_params(params)
        xp = XE.exit_params(params)
        payload = (row or {}).get("payload") or {}
        prima_trades = {int(t["id"]): str(t.get("status")) for t in db.trades
                        if t.get("id") is not None}
        n_att = len(db.attivita)

        # IL TRADER: approva la proposta viva, come fa dalla Control Room
        if self.approva:
            self._firma_le_proposte(db, now)

        errore = ""
        # i monitor dell'ultimo giro non devono sopravvivere a questo: se il bot
        # e' fermo e non valuta niente, leggerli sarebbe leggere il giro prima
        self.engine._last_monitors = []
        try:
            BS.run_once(db=db, market=market, engine=self.engine, opp_model=None,
                        opp_mod=None, engine_mod=E, now=now, opps_state={},
                        extra_mods={"anomaly": None, "combos": None, "tennis": None})
        except Exception as ex:  # noqa: BLE001 - un'eccezione del servizio E' un referto
            errore = f"{type(ex).__name__}: {ex}"
        self.ref.decisioni += 1

        # IL CONTESTO E LA VALUTAZIONE VERI, per i controlli.
        # ⚠️ `SafeEngine._ingest` aggiorna i tracker di stabilita' del punteggio:
        # chiamarlo DUE volte nello stesso giro li falserebbe (lo dice il
        # docstring di `evaluate`). Quindi: se il bot ha girato i segnali
        # (`scan_and_place` -> `evaluate`) si riusano i monitor di QUEL giro; se
        # non ha girato (bot fermo) si chiama `monitors` una volta sola, che
        # resta l'unico `_ingest` del giro.
        ctx = valutazione = None
        mons = list(getattr(self.engine, "_last_monitors", None) or [])
        if not mons and row is not None:
            try:
                mons = self.engine.monitors([row])
            except Exception as ex:  # noqa: BLE001 - un motore rotto E' un referto
                self.ref.note.append(f"monitors KO: {type(ex).__name__}: {ex}")
                mons = []
        for m in mons:
            if str(getattr(m, "event_id", "")) == str(self.ref.event_id):
                ctx, valutazione = m.ctx, m.evaluations[0]
                break

        # l'ingresso DICHIARATO (dichiarazione 3), dopo il giro vero: cosi' il
        # servizio lo trova al giro successivo esattamente come una posizione
        # aperta da lui
        if self.inietta and not self._iniettata and row is not None:
            self._iniettata = self._apri_dichiarata(db, market, row, params, now)

        # IL TRADER CHIUDE FUORI DALL'APP: un ordine SUO su Betfair, con un ref
        # che non e' del bot (come sul sito). Il bot non lo vede fra i propri
        # ordini: se ne deve accorgere dalla POSIZIONE DI CONTO.
        if self.fuori_app and self.fuori_app_fatta is None:
            self._forse_chiudi_fuori_app(db, market, now)

        # IL GUASTO SULLA CHIUSURA: si arma appena c'e' qualcosa da chiudere.
        # E' l'unico modo di far restare una LAY in volo a esito ignoto sul
        # percorso del tennis, dove la chiusura e' un FILL_OR_KILL che nasce e
        # muore nello stesso giro: senza, la regola di piattaforma sulle due lay
        # non ha mai un caso da giudicare.
        if (self.guasti and self.guasti_sull_uscita and not self._guasti_messi
                and any(str(t.get("status")) == "open" and t.get("closes_trade_id") is None
                        and str(t.get("strategy") or "") == "tennis" for t in db.trades)):
            market.guasti["place_exception"] = int(self.guasti)
            self._guasti_messi = True
            db.log("replay_guasto_uscita", {"quanti": int(self.guasti)}, self.ref.event_id)

        # RIAVVIO a meta' partita, con soldi dentro
        if self.riavvia and self._riavvio_fatto is None and any(
                str(t.get("status")) in ("open", "pending") for t in db.trades):
            self._riavvio_fatto = _pulisci_processo()
            db.log("replay_riavvio", {"azzerati": self._riavvio_fatto}, self.ref.event_id)

        oss = self._osserva(db=db, market=market, now=now, row=row, payload=payload,
                            params=params, xp=xp, ctx=ctx, valutazione=valutazione,
                            prima=prima_trades, n_att=n_att, errore=errore)
        self.ref.violazioni.extend(CERT.verifica(oss, self.ref.sollecitati))
        # I CONTROLLI K: LA MEMORIA DEL BOT CONTRO IL MERCATO. Qui, dopo il giro
        # del servizio, esistono insieme le righe scritte dal bot e gli ORDINI
        # VERI di flumine; i controlli T/J/L guardano la decisione, questi
        # guardano il rapporto fra cio' che il bot crede e cio' che c'e' a
        # mercato - ed e' li' che vivevano i cinque difetti del 15/09.
        self.ref.violazioni.extend(CERT.verifica_consapevolezza(
            list(db.trades),
            {ref: market._riga(ref, o) for ref, o in market.ordini.items()},
            [str(x.get("ref") or "") for x in market.rifiutati],
            self.ref.sollecitati, oss.quando))
        CERT.osserva(self.ref.andamento, oss)
        if valutazione is not None:
            self.motivi[self._motivo(valutazione)] += 1

    # --------------------------------------------------------- osservazione
    def _osserva(self, *, db, market, now, row, payload, params, xp, ctx,
                 valutazione, prima, n_att, errore) -> CERT.Osservazione:
        aperture: List[Dict[str, Any]] = []
        chiusure: List[Dict[str, Any]] = []
        for t in db.trades:
            tid = int(t.get("id") or 0)
            stato = str(t.get("status"))
            if prima.get(tid) == stato:
                continue
            # UN SOLO evento per riga: l'istante in cui il piazzamento si e'
            # concluso. Contare anche la riserva 'pending' e i passaggi
            # successivi ('hedged') farebbe scattare i controlli d'ingresso piu'
            # volte sulla stessa apertura, e il conteggio delle sollecitazioni
            # e' meta' del referto.
            if stato not in ("open", "error"):
                continue
            voce = {"trade": dict(t), "ordine": self._ordine_di(market, tid)}
            (chiusure if t.get("closes_trade_id") is not None else aperture).append(voce)
        # quale RUOLO ha ogni ordine: il ref e' `safe-t<trade_id>` e la riga del
        # trade dice se e' un'apertura o una gamba di chiusura. Serve a P1, che
        # conta le riproposizioni PER RUOLO.
        per_id = {int(t["id"]): t for t in db.trades if t.get("id") is not None}
        nuovi: List[Dict[str, Any]] = []
        cancellati: List[Dict[str, Any]] = []
        for riga in self._righe_ordine(market):
            ref = str(riga.get("customer_order_ref") or "")
            if not ref:
                continue
            gia_noto = ref in self._refs_visti
            # ANNULLO avvenuto in questo giro: `size_cancelled` e' cresciuto su
            # un ordine che esisteva GIA' al giro prima.
            # ⚠️ L'ordine NATO in questo giro non conta: il suo `size_cancelled`
            # e' la parte uccisa dal FILL_OR_KILL al piazzamento, che non e' un
            # annullo del bot. Contarlo avrebbe fatto scattare L2 su ogni FOK
            # parziale — un falso positivo del controllo, il difetto §7.16.
            tagliato = float(riga.get("size_cancelled") or 0.0)
            if gia_noto and tagliato > self._cancellato_prima.get(ref, 0.0) + 1e-9:
                cancellati.append(dict(riga))
            self._cancellato_prima[ref] = tagliato
            if not gia_noto:
                self._refs_visti.add(ref)
                tid = ref[len("safe-t"):] if ref.startswith("safe-t") else ""
                padre = per_id.get(int(tid)) if tid.isdigit() else None
                riga = dict(riga,
                            _chiusura=bool((padre or {}).get("closes_trade_id")))
                nuovi.append(riga)
        self.ref.ordini_piazzati = len(self._refs_visti)
        self.ref.righe_scritte = len(db.trades)
        control = db.read_control()
        modo_serv = str(control.get("mode") or "paper")
        proposte = [dict(r) for r in db.richieste if str(r.get("status")) == "proposed"]
        for p in proposte:
            self.proposte_viste.add(int(p.get("id") or 0))
        punteggio = f"set {payload.get('sets')} game {payload.get('games')}"
        return CERT.Osservazione(
            now_ts=now.timestamp(),
            quando=f"{now.strftime('%H:%M:%S')} {punteggio}",
            scenario=self.scenario,
            stato_bot=str(control.get("status") or "idle"),
            modo_servizio=modo_serv,
            modo_strategia=BS.modalita_di_strategia("tennis", modo_serv, params),
            params=params, xp=xp, row=row, payload=payload,
            feed_fresco=BS._row_is_fresh(row, now.timestamp(),
                                         BS._scanner_ts(db, None)),
            ctx=ctx, valutazione=valutazione,
            segnali=list(getattr(self.engine, "_signals", []) or []),
            trades=[dict(t) for t in db.trades],
            aperture=aperture, chiusure=chiusure, ordini=nuovi,
            # cio' che Betfair ha DAVVERO sul book adesso (L1): non cio' che il
            # bot crede di avere
            ordini_vivi=[dict(o) for o in market.list_current_orders()],
            cancellati=cancellati,
            rifiutati=list(market.rifiutati),
            attivita=list(db.attivita[n_att:]),
            proposte=proposte, errore_servizio=errore,
            # cio' che il REPLAY sa: l'utente ha chiuso, e non perche' il bot
            # lo abbia scritto (vedi il campo sull'Osservazione)
            chiuso_dall_utente=dict(self.chiuso_dall_utente))

    @staticmethod
    def _righe_ordine(market) -> List[Dict[str, Any]]:
        return list(market.list_current_orders()) + list(market.list_cleared_orders())

    def _ordine_di(self, market, trade_id: int) -> Optional[Dict[str, Any]]:
        atteso = f"safe-t{int(trade_id)}"
        for riga in self._righe_ordine(market):
            if str(riga.get("customer_order_ref") or "") == atteso:
                return riga
        return None

    @staticmethod
    def _motivo(valutazione: Any) -> str:
        if getattr(valutazione, "state", None) == "signal":
            return "SEGNALE"
        falliti = [c.id for c in (getattr(valutazione, "checks", None) or ())
                   if c.ok is False]
        if falliti:
            return "no: " + ",".join(falliti[:3])
        nd = [c.id for c in (getattr(valutazione, "checks", None) or ()) if c.ok is None]
        return ("nd: " + ",".join(nd[:3])) if nd else "nessun motivo"

    # ------------------------------------------ il trader chiude fuori dall'app
    def _forse_chiudi_fuori_app(self, db, market, now) -> None:
        """Il trader chiude la posizione del bot con un ordine SUO.

        Passa da `banco_comune.MercatoFlumine.place_order_utente`: stesso
        `market.place_order`, stesso matching, ref diverso — esattamente cio'
        che succede quando si chiude dal sito di Betfair. Il tennis PUNTA, quindi
        la chiusura del trader e' una LAY sulla stessa selezione.
        """
        piazza = getattr(market, "place_order_utente", None)
        if not callable(piazza):
            return
        vive = [t for t in db.trades
                if str(t.get("strategy") or "") == "tennis"
                and str(t.get("status") or "") == "open"
                and t.get("closes_trade_id") is None
                and str(t.get("origin") or "") == "auto"
                and float(t.get("size") or 0.0) > 0]
        if not vive:
            return
        tr = vive[0]
        lato_bot = str(tr.get("side") or "").lower()
        lato_utente = "back" if lato_bot == "lay" else "lay"
        size = round(float(tr.get("size") or 0.0)
                     * (0.5 if self.fuori_app == "ridotta" else 1.0), 2)
        if size < 0.01:
            return
        ordine = piazza(market_id=str(tr.get("market_id")),
                        selection_id=int(tr.get("selection_id") or 0),
                        price=(1.01 if lato_utente == "back" else 1000.0),
                        size=size, side=lato_utente,
                        customer_ref=f"utente-fuori-app-{tr.get('id')}")
        dettaglio = {"trade_id": tr.get("id"), "lato_utente": lato_utente,
                     "size": size, "size_del_bot": tr.get("size"),
                     "market_id": tr.get("market_id"),
                     "selection_id": tr.get("selection_id"),
                     "piazzato": ordine is not None, "modo": self.fuori_app}
        db.log("replay_chiusura_fuori_app", dettaglio)
        self.fuori_app_fatta = dettaglio
        # solo la chiusura INTERA e' un «non fare altro»: quella parziale no
        if ordine is not None and self.fuori_app == "intera":
            self.chiuso_dall_utente[str(self.ref.event_id)] = float(now.timestamp())

    # ------------------------------------------------------- il trader firma
    def _firma_le_proposte(self, db, now) -> None:
        """La Control Room promuove la proposta a richiesta: 'proposed' ->
        'pending' con il payload del cash-out. E' esattamente la riga che scrive
        la pagina quando il trader clicca APPROVA."""
        for r in db.richieste:
            if str(r.get("status")) != "proposed":
                continue
            corpo = dict(r.get("payload") or {})
            r["status"] = "pending"
            # ⚠️ DIFETTO 27 (il finto che non parla come il vero), corretto il
            # 16/09: la RPC VERA (`migrations/safe_strategy_proposed_2026-09-14.sql`
            # :74) fa `payload = payload || {'approved_at': ...}`, cioe' CONSERVA
            # tutto il corpo e AGGIUNGE la firma. Il replay lo RIFACEVA da zero
            # con trade_id+fraction e buttava via `exit_kind` — proprio il campo
            # con cui `_uscita_del_bot_approvata` distingue l'uscita del BOT dal
            # cash-out dell'UTENTE. Un finto che perde una chiave certifica un
            # comportamento che in produzione non esiste.
            r["payload"] = {**corpo,
                            "approved_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "approvata_da": "replay: il trader firma al giro dopo"}
            r["created_at"] = now.isoformat()
            r["updated_at"] = now.isoformat()
            self.approvazioni += 1

    # --------------------------------------------------- ingresso dichiarato
    def _apri_dichiarata(self, db, market, row, params, now) -> bool:
        """APRE una posizione con le funzioni di PRODUZIONE, dichiarando che il
        trigger non e' della strategia (dichiarazione 3 in testa al modulo).

        Nessun campo e' inventato: mercato, selezione, prezzo e liquidita'
        vengono dalla riga vera dello scanner, lo stake da
        `engine.stake_di_strategia`, la riga da `bot_service._reserve_row` e
        l'ordine da `bot_service._execute` -> `execution.place` -> flumine.
        """
        # SE LA STRATEGIA E' GIA' ENTRATA DA SOLA, non si inietta niente: la
        # posizione dichiarata serve solo dove l'ingresso non e' esercitabile.
        # Su una registrazione in cui il segnale scatta davvero, aggiungerne una
        # seconda falserebbe i tetti e il rischio (e l'indice unico la
        # rifiuterebbe comunque, un giro dopo l'altro).
        # ⚠️ una riga in 'error' NON e' una posizione: e' un ordine che Betfair
        # non ha abbinato (FOK ucciso). Contarla qui bloccava per sempre il
        # ritentativo dell'ingresso dichiarato dopo il primo rifiuto.
        if any(str(t.get("strategy") or "") == "tennis"
               and t.get("closes_trade_id") is None
               and str(t.get("status") or "") != "error" for t in db.trades):
            return True
        payload = row.get("payload") or {}
        sets = payload.get("sets") if isinstance(payload.get("sets"), dict) else None
        games = payload.get("games") if isinstance(payload.get("games"), dict) else None
        odds = payload.get("odds") if isinstance(payload.get("odds"), dict) else None
        if not (payload.get("inplay") and sets and games and odds):
            return False
        if str(payload.get("mo_status") or "").upper() != "OPEN":
            return False
        diff = int(sets.get("p1") or 0) - int(sets.get("p2") or 0)
        if diff == 0:
            return False                     # senza un leader per set non si apre
        lato = "p1" if diff > 0 else "p2"
        blocco = odds.get(lato) or {}
        sid = blocco.get("selection_id")
        prezzo = blocco.get("back")
        disponibile = blocco.get("back_size")
        if sid is None or not prezzo or not disponibile:
            return False
        stake = E.stake_di_strategia(params, "tennis", "back")
        if float(disponibile) < stake:
            return False
        modo = BS.modalita_di_strategia("tennis", str(db.read_control().get("mode")), params)
        punteggio = (f"set {sets.get('p1')}-{sets.get('p2')} "
                     f"{E.MIDDOT} game {games.get('p1')}-{games.get('p2')}")
        riga = BS._reserve_row(
            event_id=str(self.ref.event_id), event_name=payload.get("event_name"),
            sport="tennis", strategy="tennis", market_id=payload.get("mo_market_id"),
            market_type="MATCH_ODDS", selection_id=int(sid),
            selection_name=payload.get(lato), side="back", mode=modo,
            price=float(prezzo), size=float(stake),
            liability=float(stake), commission=float(params.get("commission_pct", 5.0)) / 100.0,
            minute=None, score=punteggio, origin="auto",
            signal_key=f"{self.ref.event_id}:tennis:set "
                       f"{sets.get('p1')}-{sets.get('p2')}",
            meta={"variant": "tennis",
                  "ingresso_dichiarato": "il replay ha aperto qui: su questa "
                                         "registrazione la strategia non ha mai le sue "
                                         "condizioni (vedi referto). I controlli "
                                         "sull'INGRESSO non valgono su questa riga."})
        try:
            tid = db.insert_trade(riga)
        except Exception as ex:  # noqa: BLE001
            db.log("skip", {"reason": "ingresso_dichiarato_gia_riservato",
                            "err": str(ex)[:120]}, self.ref.event_id)
            return False
        if not tid:
            return False
        prezzi = BS.prices_from_row(row, market_type="MATCH_ODDS",
                                    selection_id=int(sid),
                                    market_id=payload.get("mo_market_id"))
        out = BS._execute(db=db, market=market, trade_id=int(tid), row=riga,
                          params=params, now=now, best_size=float(disponibile),
                          ladder=(), feed_prices=prezzi)
        db.log("replay_ingresso_dichiarato",
               {"trade_id": int(tid), "price": float(prezzo), "size": float(stake),
                "score": punteggio, "esito": out.status, "nota": out.fill_note},
               self.ref.event_id)
        return out.status != "error"

    # ---------------------------------------------------------- chiusura
    def chiudi(self, esito: Any) -> None:
        ref, db = self.ref, self.db
        ref.motivi = dict(self.motivi.most_common(8))
        ref.violazioni.extend(CERT.difetti_di_progettazione(ref.andamento))
        ref.stati_visti = sorted({str(t.get("status")) for t in (db.trades if db else [])})
        ref.azioni = len(self._refs_visti)
        note = ref.note
        note.append(f"scenario: {self.scenario} — {SCENARI_DESCRITTI.get(self.scenario, '')}")
        note.append(f"competizione dichiarata: {self.competizione!r} "
                    f"(il raw dello stream NON la contiene: limite 1 del banco)")
        if db is not None:
            kinds = Counter(db.kinds())
            note.append("attivita' del servizio: "
                        + (", ".join(f"{k} x{n}" for k, n in kinds.most_common(10)) or "-"))
            stati = Counter(str(t.get("status")) for t in db.trades)
            note.append(f"righe safe_strategy_trades: {len(db.trades)} {dict(stati)}")
            motivi = Counter(str((p or {}).get("reason") or "")[:60]
                             for k, p, _e in db.attivita if k in ("skip", "error"))
            if motivi:
                note.append("motivi dichiarati: "
                            + " | ".join(f"{m} x{n}" for m, n in motivi.most_common(5)))
            if db.mancanti:
                note.append("metodi di database chiamati dal servizio e assenti dal "
                            f"banco: {sorted(db.mancanti)}")
            if db.senza_dato:
                note.append("[NON ESERCITABILE] dati di produzione assenti dalla "
                            "registrazione: "
                            + " | ".join(f"{n}: {c}" for n, c in db.senza_dato))
            proposte = Counter(str(r.get("status")) for r in db.richieste)
            if db.richieste:
                note.append(f"proposte/richieste di chiusura: {dict(proposte)} "
                            f"(firme del trader: {self.approvazioni})")
        if self.mercato is not None:
            # LIMITE 8 DEL BANCO, dichiarato: `MercatoFlumine` non espone
            # `read_market`/`read_book`, quindi il SETTLEMENT non passa dal
            # `process_closed_market` di flumine (niente `runner_status` veri,
            # niente void per mercato) e ripiega sull'ultimo punteggio del feed.
            if not hasattr(self.mercato, "read_market"):
                note.append("[NON ESERCITABILE] settlement dal mercato chiuso: "
                            "`MercatoFlumine` non espone `read_market` (limite 8 "
                            "del banco comune) -> si ripiega sul feed, e i "
                            "controlli che dipendono dal REGOLAMENTO (T8) non "
                            "hanno un caso")
            if self.giri_di_chiusura:
                note.append(f"[DICHIARATO] {self.giri_di_chiusura} giri del "
                            f"servizio DOPO il fischio, a mercato CHIUSO, per il "
                            f"settlement (come il replay di Omega): flumine "
                            f"consegna il mercato chiuso a `process_closed_market` "
                            f"e il ponte del banco inoltra solo "
                            f"`process_market_book`, quindi senza questi giri il "
                            f"bot non vedrebbe MAI la chiusura. L'esito viene dal "
                            f"`marketDefinition` registrato.")
            if self.settlement_abilitato:
                note.append("[DICHIARATO] settlement dal mercato CHIUSO abilitato "
                            "dal replay: `read_market`/`read_markets` di "
                            "`MercatoSafe` (gli stessi del calcio, C.3) appoggiati "
                            "al mercato del banco, contenuto dal `marketDefinition` "
                            "registrato. Senza, T8 non avrebbe mai un caso "
                            "(limite 8 del banco comune)")
            fill = self.mercato.riepilogo_fill()
            note.append(f"fill: {fill['fill']} abbinamenti su {fill['ordini_con_fill']} "
                        f"ordini per {fill['abbinato']} EUR (prezzi {fill['prezzi']})")
            if self.mercato.rifiutati:
                note.append(f"ordini rifiutati: {len(self.mercato.rifiutati)} "
                            f"(es. {self.mercato.rifiutati[0].get('err')})")
            aliquota = float(BS.DEFAULT_PARAMS.get("commission_pct", 5.0)) / 100.0
            conto = self.mercato.pnl(aliquota)
            note.append(f"P&L del replay: lordo {conto['lordo']:+.2f} | commissione "
                        f"{conto['commissione']:.2f} ({conto['aliquota'] * 100:.1f}%) | "
                        f"NETTO {conto['netto']:+.2f} EUR (non e' il metro: il metro "
                        f"e' la condotta)")
        if esito is not None:
            note.append(f"tick dello stream: {esito.tick} | giri del servizio: "
                        f"{esito.giri} | righe di scan scritte dallo SCANNER VERO: "
                        f"{esito.righe_scan} | mercati: {esito.mercati}")
            note.append(f"bet delay: {esito.book_attesi} book passati durante i "
                        f"piazzamenti | book in ritardo (orologio fermo): "
                        f"{esito.book_in_ritardo} | LAPSE al passaggio in gioco: "
                        f"{esito.lapse_al_fischio}"
                        + (f" | {esito.senza_futuro} piazzamenti senza book futuro"
                           if esito.senza_futuro else ""))
            for e in esito.errori[:3]:
                ref.violazioni.append(CERT.Violazione(
                    "A1", "il giro del servizio non deve mai sollevare", e))
            for n in esito.note:
                note.append(f"banco: {n}")
        if self.righe_assenti:
            note.append(f"giri senza riga nel feed: {self.righe_assenti}")
        if self._riavvio_fatto is not None:
            note.append("RIAVVIO a meta' partita: azzerate le cache di processo "
                        + ", ".join(self._riavvio_fatto))
        elif self.riavvia:
            note.append("scenario riavvio: nessuna posizione aperta da ritrovare, "
                        "il riavvio non e' mai scattato")
        if self.inietta and not self._iniettata:
            note.append("scenario con ingresso dichiarato: NESSUNA posizione e' stata "
                        "aperta (nessun giro con leader per set, mercato aperto e "
                        "liquidita' sufficiente)")
        elif self.inietta:
            note.append("INGRESSO DICHIARATO DAL REPLAY: i controlli T1-T4, T11 "
                        "sull'ingresso NON valgono su questa riga (il trigger non e' "
                        "della strategia); valgono tutti quelli su uscite e ordini")


# ---------------------------------------------------------------------------
# adattatore per il registro dei bot (firma unica di MODELLO_BOT_NUOVO.md)
# ---------------------------------------------------------------------------
def certifica_scenario(event_id: str, *, data_dir: str, scenario: str = "base",
                       ogni_ms: int = 0, campioni_diff: int = 0) -> CERT.Referto:
    """Firma IDENTICA a quella degli altri bot, cosi' che il giorno in cui la
    scheda `safe_tennis` entra in `registro_bot.py` il comando
    `python -m Betfair.stream.backtest.certifica safe_tennis` funzioni senza
    toccare niente."""
    return certifica_evento(event_id, data_dir=data_dir, scenario=scenario,
                            ogni_ms=ogni_ms, competizione=COMPETIZIONE_DICHIARATA,
                            campioni_diff=campioni_diff)


# La competizione che il raw non porta. NON e' il nome vero del torneo: e' la
# DICHIARAZIONE di cio' che della registrazione si sa — che il match si e'
# giocato al meglio dei 3 set (e' finito 1-2 nei set, e un best-of-5 non puo'
# finire con due set al vincitore). `engine.detect_best_of` cerca le parole
# chiave degli Slam: questa stringa non ne contiene, quindi il filtro
# `excludeBestOf5` passa — ed e' esattamente cio' che farebbe col nome vero di
# un torneo al meglio dei 3 set.
COMPETIZIONE_DICHIARATA = "torneo al meglio dei 3 set (dichiarato dal replay)"


def cartella_predefinita() -> str:
    radice = (os.getenv("TENNIS_RECORD_DIR", "").strip()
              or os.path.join(os.path.expanduser("~"), "Desktop", "tennis_rec"))
    giorni = sorted(d for d in os.listdir(radice) if d.isdigit()) \
        if os.path.isdir(radice) else []
    return os.path.join(radice, giorni[-1]) if giorni else radice


def impronta() -> Dict[str, str]:
    """Versioni e IMPRONTA del codice: un referto che non si puo' rifare
    identico non e' un referto, e' un ricordo (PROCESSO §6.8)."""
    fuori: Dict[str, str] = {}
    try:
        import betfairlightweight
        import flumine

        fuori["flumine"] = str(getattr(flumine, "__version__", "?"))
        fuori["betfairlightweight"] = str(getattr(betfairlightweight, "__version__", "?"))
    except Exception as ex:  # noqa: BLE001
        fuori["flumine"] = f"non importabile: {str(ex)[:60]}"
    h = hashlib.sha1()  # noqa: S324 - impronta di identita', non firma
    contati = 0
    for modulo in ("Betfair.safe_strategy.bot_service", "Betfair.safe_strategy.engine",
                   "Betfair.safe_strategy.exits", "Betfair.safe_strategy.execution",
                   "Betfair.safe_strategy.certificazione_tennis"):
        percorso = os.path.join(*modulo.split(".")) + ".py"
        if os.path.isfile(percorso):
            with open(percorso, "rb") as fh:
                h.update(fh.read())
            contati += 1
    fuori["codice_bot"] = f"{h.hexdigest()[:12]} ({contati} file)" if contati else "ignoto"
    return fuori


def qualita_registrazione(data_dir: str, event_id: str) -> str:
    try:
        from ...stream.tools.validate_recordings import validate_event

        rep = validate_event(data_dir, str(event_id))
        buchi = len(getattr(rep, "gaps_in_window", None) or [])
        return (f"{rep.verdict} {rep.coverage_pct}% ({buchi} buchi dichiarati, "
                f"{getattr(rep, 'gap_in_window_min', 0)} min)")
    except Exception as ex:  # noqa: BLE001 - il verdetto e' un di piu', non un gate
        return f"ignota ({type(ex).__name__})"


# ---------------------------------------------------------------------------
# il comando
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Certificazione di SAFE TENNIS sulle registrazioni reali")
    p.add_argument("eventi", nargs="*", default=[EVENTO_DI_RIFERIMENTO],
                   help=f"event_id (default: {EVENTO_DI_RIFERIMENTO})")
    p.add_argument("--data-dir", default=None)
    p.add_argument("--scenari", default="base",
                   help="elenco separato da virgole, oppure 'tutti'")
    p.add_argument("--ogni-ms", type=int, default=0,
                   help="cadenza del servizio in ms. 0 = quella di produzione "
                        "(poll_interval_s)")
    p.add_argument("--competizione", default=COMPETIZIONE_DICHIARATA,
                   help="la competizione che il raw NON contiene (limite 1 del banco)")
    p.add_argument("--diario", default=None,
                   help="file in cui scrivere il referto dopo ogni partita")
    a = p.parse_args(argv)

    logging.basicConfig(level=logging.WARNING)
    data_dir = a.data_dir or cartella_predefinita()
    eventi = list(a.eventi or [EVENTO_DI_RIFERIMENTO])
    scelti = (list(SCENARI_DESCRITTI) if a.scenari.strip().lower() == "tutti"
              else [s.strip() for s in a.scenari.split(",") if s.strip()])
    for s in scelti:
        if s not in SCENARI_DESCRITTI:
            print(f"scenario sconosciuto: {s} (noti: {', '.join(SCENARI_DESCRITTI)})")
            return 2

    imp = impronta()
    print("BOT: safe_tennis | spec: SPEC_STRATEGIA_S.md §3 + "
          "Betfair/safe_strategy/RISCONTRO_TENNIS_2026-09-14.md")
    print(f"controlli attivi: {len(CERT.elenco_controlli())} | flumine "
          f"{imp.get('flumine')} | betfairlightweight {imp.get('betfairlightweight')} "
          f"| codice bot {imp.get('codice_bot')}")
    print(f"comando: python -m Betfair.safe_strategy.tools.replay_tennis "
          + " ".join(eventi) + f" --scenari {a.scenari}"
          + (f" --ogni-ms {a.ogni_ms}" if a.ogni_ms else ""))
    print(f"registrazioni: {data_dir}")
    for ev in eventi:
        print(f"  qualita' {ev}: {qualita_registrazione(data_dir, ev)}")
    print(f"SCENARI: {', '.join(scelti)}")
    print()

    sollecitati_tot: Dict[str, int] = {}
    referti: List[CERT.Referto] = []
    for sc in scelti:
        for ev in eventi:
            try:
                r = certifica_evento(ev, data_dir=data_dir, scenario=sc,
                                     ogni_ms=int(a.ogni_ms or 0),
                                     competizione=a.competizione)
            except Exception as ex:  # noqa: BLE001 - un replay che esplode E' un referto
                r = CERT.Referto(event_id=str(ev))
                r.note.append(f"replay fallito: {type(ex).__name__}: {ex}")
            r.event_id = f"{ev} [{sc}]"
            referti.append(r)
            for cod, n in r.sollecitati.items():
                sollecitati_tot[cod] = sollecitati_tot.get(cod, 0) + n
            segno = "OK " if r.pulita else "KO "
            print(f"{segno} {r.event_id}  tick={r.tick:>6} giri={r.decisioni:>5} "
                  f"ordini={r.ordini_piazzati:>3} righe={r.righe_scritte:>3} "
                  f"stati={','.join(r.stati_visti) or '-'}")
            for nota in r.note:
                print(f"      nota: {nota}")
            for motivo, n in sorted(r.motivi.items(), key=lambda x: -x[1])[:5]:
                print(f"      motivo x{n}: {motivo}")
            for cod, n in sorted(r.per_codice().items()):
                esempio = next(v for v in r.violazioni if v.codice == cod)
                print(f"      {cod} x{n}: {esempio.regola}")
                print(f"           es. {esempio.dettaglio}")
            if a.diario:
                with open(a.diario, "a", encoding="utf-8") as fh:
                    fh.write(f"{'OK' if r.pulita else 'KO'} {r.event_id} tick={r.tick} "
                             f"giri={r.decisioni} ordini={r.ordini_piazzati}\n")
                    for nota in r.note:
                        fh.write(f"    nota: {nota}\n")
                    for v in r.violazioni[:8]:
                        fh.write(f"    {v.codice}: {v.dettaglio}\n")
                    fh.flush()
            print()

    tot = sum(len([v for v in r.violazioni
                   if not v.codice.endswith(("-DICHIARATA", "-APPROVAZIONE"))])
              for r in referti)
    pulite = sum(1 for r in referti if r.pulita)
    print(f"ESITO: {pulite} su {len(referti)} senza violazioni, {tot} violazioni totali")
    print()
    print("COPERTURA DEI CONTROLLI — quante volte ognuno ha avuto un caso:")
    for cod, reg in CERT.elenco_controlli():
        n = sollecitati_tot.get(cod, 0)
        print(f"  {'  ' if n else '??'} {cod:16} x{n:<7} {reg[:60]}")
    mai = CERT.mai_sollecitati(sollecitati_tot)
    if mai:
        print()
        print(f"?? MAI SOLLECITATI: {len(mai)} su {len(CERT.elenco_controlli())}. "
              f"Su questi il referto NON dice «sano», dice «non lo so»:")
        for cod, reg in mai:
            causa = CERT.CAUSE_NON_ESERCITABILI.get(cod)
            print(f"     {cod}: {reg}")
            if causa:
                print(f"        (non esercitabile) {causa}")
    return 0 if tot == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
