"""SAFE CALCIO SULLE REGISTRAZIONI VERE — base, esatto e punta sul banco comune.

«Per Safe calcio, controlla che le strategie siano applicate TUTTE e che
rispettino la loro logica in OGNI punto» (utente, 16/09).

CHE COSA FA, in una riga: fa rivivere alle tre strategie calcio della Safe una
partita registrata, alla cadenza vera del servizio, e a OGNI valutazione, ordine
e uscita controlla le voci di `SPEC_STRATEGIA_S.md` (`certificazione.py`).
Non misura il profitto: misura la condotta.

LA CATENA, e nessun passo e' saltato (PROCESSO_STANDARD_BOT §3 e §6):

    _live_raw/<id>/<id>.raw.jsonl        stream NATIVO Betfair registrato
      -> FlumineSimulation + HistoricalStream
      -> `Scanner._apply_market_book` VERO  (safe_strategy/service.py:493)
      -> `Scanner.build_rows` VERA          -> riga `safe_strategy_scan`
      -> `bot_service.run_once` VERO        (il CICLO INTERO: riconciliazione,
                                             settlement, richieste UI, uscite,
                                             tetti, stop giornaliero, battito)
      -> `engine.SafeEngine.evaluate`       -> base / esatto / punta
      -> `execution.place` VERA             -> `MercatoFlumine.place_order_live`
                                             (matching di flumine, coda `_piq`,
                                              FILL_OR_KILL, bet delay)

DA DOVE VIENE OGNI PEZZO — non si e' inventato niente:

  * il banco    : `Betfair/stream/backtest/banco_comune.py` (`ScannerReplay`,
                  `DbMemoria`, `MercatoFlumine`, `MotoreReplay`);
  * i controlli : `Betfair/safe_strategy/certificazione.py`, una riga per voce
                  della SPEC, sul modello di `RISCONTRO_CALCIO_2026-09-14.md`;
  * i nomi del  : `Betfair/safe_strategy/tools/validate_opportunity.py`
    Correct       (`selection_name`): lo stream NON porta i nomi dei runner e
    Score         senza «Any Other Home/Away Win» la variante ESATTO sarebbe
                  MUTA per sempre. Si riusa la mappa gia' verificata sugli
                  esiti WINNER delle registrazioni, non se ne scrive una nuova.

QUELLO CHE QUESTO REPLAY **NON** CERTIFICA (dichiarato, non taciuto):

  * il minimo di giurisdizione .it e il place-and-trim: flumine non ha un
    minimo, quindi `place_submin_live` piazza diretto -> ⊘;
  * le opportunita' a modello, le combo e le anomalie: sono un altro motore,
    non le tre strategie della SPEC -> fuori perimetro C.3;
  * il percorso PAPER legacy (`_paper_ladder` + `omega_engine.paper_fill`) non
    passa da flumine: lo scenario `paper` lo esercita e il referto riporta la
    DIVERGENZA come reperto (decisione 3 dell'utente del 16/09), non la corregge.

Uso:
    python -m Betfair.safe_strategy.tools.replay_registrazioni 35760084
    python -m Betfair.safe_strategy.tools.replay_registrazioni 35760084 \
        --strategie base,esatto,punta --scenari base,cap-stretto --diario d.txt

E' un chiamante sottile del punto d'ingresso unico
(`python -m Betfair.stream.backtest.certifica safe_calcio ...`).

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import logging
import os
import sys
from bisect import bisect_right
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, Tuple

from .. import bot_service as BS
from .. import certificazione as CERT
from .. import engine as E
from .. import execution as X
from .. import exits as XE
from ...stream.backtest.banco_comune import (
    DbMemoria, MercatoFlumine, MotoreReplay, ScannerReplay,
    assicura_middleware_simulato, carica_punteggi, cliente_simulato,
    nomi_dal_punteggio, simulazione_flumine,
)
from . import validate_opportunity as VO

logger = logging.getLogger(__name__)

# le tre strategie CALCIO della SPEC. Il tennis e' C.4, non sta qui.
STRATEGIE = ("base", "esatto", "punta")


# ---------------------------------------------------------------------------
# GLI SCENARI — le condizioni rare non si aspettano, si provocano
# ---------------------------------------------------------------------------
# Cambiano SOLO parametri, freschezza del feed o guasti iniettati: mai la
# partita, mai i prezzi, mai la strategia.
SCENARI: Dict[str, Dict[str, Any]] = {
    # come gira in produzione, con le tre strategie calcio accese in LIVE
    "base": {},
    # tetto di RESPONSABILITA' per operazione STRETTO: fa parlare il gate di
    # rischio (`max_liability_per_trade`) senza toccare le soglie d'ingresso.
    "cap-stretto": {"max_liability_per_trade": 5.0},
    # bot FERMO con posizioni aperte: nessuna apertura, le protezioni girano
    "bot-fermo": {},
    # esiti IGNOTI: i primi piazzamenti sollevano -> righe in riconciliazione
    "esiti-ignoti": {},
    # feed STANTIO: riga e scanner vecchi -> nessun ingresso, chiusure permesse
    "feed-stantio": {},
    # RIAVVIO a meta' partita: via le cache di processo, lo stato si ritrova dal DB
    "riavvio": {},
    # il percorso PAPER legacy, per misurare la divergenza con flumine
    "paper": {},
    # ORDINI VERI SU FLUMINE senza toccare la strategia: si usa il percorso
    # MANUALE della UI (`safe_strategy_requests`), cioe' il bottone del trader.
    "ordini-manuali": {},
    # DUE LAY MANUALI SULLA STESSA SELEZIONE: il trader preme «Investi» due
    # volte con due chiavi diverse (doppio clic, o due schede aperte). Dal
    # chiarimento dell'utente del 16/09 NON e' una violazione del bot — il bot
    # opera sulle SUE operazioni — e questo scenario serve a dimostrarlo: T12
    # ha un caso da giudicare e TACE.
    "due-lay": {},
    # IL TRADER OPERA A MANO MENTRE IL BOT LAVORA, sulla STESSA selezione che
    # il bot banca (Correct Score «Altro risultato Casa»): il bot deve
    # continuare a fare le SUE gambe identiche, e non toccare mai quella del
    # trader (controlli T12 e T13).
    "manuale-e-bot": {},
    # CASH-OUT GLOBALE DEL TRADER: appena il bot ha una posizione aperta,
    # l'utente chiude a mano TUTTE le operazioni della partita dal percorso
    # VERO del servizio (una richiesta `cashout` per ogni riga viva, che e'
    # cio' che la UI accoda). Da li' in poi il bot «lo capisce e non fa altro».
    "cashout-globale": {},
    # SELEZIONE AGGIUNTIVA della SPEC §2 ACCESA (ordine dell'utente 16/09):
    # cambia SOLO un parametro, come tutti gli altri scenari. Serve a far
    # girare davvero il filtro «scontri diretti senza troppi 2-2/3-3, difesa
    # avversaria solida» e a far avere un caso al controllo E10, che con il
    # parametro spento (default) non ne ha nessuno.
    "selezione-aggiuntiva": {"esatto": {"requireSelection": True}},
    # L'UTENTE CHIUDE FUORI DALL'APP (ordine del 16/09 sera, consegna S1): con
    # una posizione del bot aperta, il trader piazza un ordine SUO su Betfair
    # che la chiude. Il bot non lo vede fra i propri ordini (ref diverso): deve
    # accorgersene dalla POSIZIONE DI CONTO e non fare altro.
    "chiusura-fuori-app": {},
    # variante: l'utente chiude solo META' della posizione. Il bot lo DICHIARA
    # e continua a proteggere il resto (non e' un cash-out).
    "chiusura-fuori-app-ridotta": {},
    # RIFIUTO DICHIARATO DI BETFAIR (`ok=False`) sul lato che Safe usa per
    # APRIRE (lay). Non tocca un parametro: i primi N piazzamenti tornano con
    # un report NEGATIVO, come quando Betfair rifiuta l'istruzione (prezzo non
    # piu' valido, profit ratio fuori banda, fondi). E' l'unico modo di mettere
    # alla prova il difetto 2 del catalogo del 15/09 - «`res.ok` mai letto» -
    # che sulle registrazioni non capita mai, perche' nel replay nessun ordine
    # viene rifiutato.
    "rifiuti-betfair": {},
    # TIMEOUT DOPO CHE BETFAIR HA ACCETTATO (difetto 4 del 15/09). Non tocca un
    # parametro: una volta sola, a ordine gia' piazzato e abbinato su flumine, la
    # RIGA viene riportata nello stato in cui la lascia `execution._reconciling`
    # (`pending`, senza bet_id, `reason='place_exception_reconciling'`) - cioe'
    # quello che succede quando la REST va in timeout DOPO che l'exchange ha
    # preso l'ordine. L'ordine a mercato resta quello VERO. Da li' l'unica strada
    # per ritrovarlo e' il ref con cui e' stato CHIESTO: se la riconciliazione ne
    # usa un altro, la riga viene dichiarata mai piazzata e i soldi restano a
    # mercato senza padrone (controllo K7). E' l'unico modo di dare un caso a
    # quel difetto: lo scenario `esiti-ignoti` solleva PRIMA del piazzamento,
    # quindi li' un ordine da ritrovare non esiste proprio.
    "timeout-dopo-accettazione": {},
}

SCENARIO_BOT_FERMO = "bot-fermo"
SCENARIO_ESITI_IGNOTI = "esiti-ignoti"
SCENARIO_FEED_STANTIO = "feed-stantio"
SCENARIO_RIAVVIO = "riavvio"
SCENARIO_PAPER = "paper"
SCENARIO_ORDINI = "ordini-manuali"
SCENARIO_DUE_LAY = "due-lay"
SCENARIO_MANUALE_E_BOT = "manuale-e-bot"
SCENARIO_CASHOUT_GLOBALE = "cashout-globale"
SCENARIO_SELEZIONE = "selezione-aggiuntiva"
SCENARIO_FUORI_APP = "chiusura-fuori-app"
SCENARIO_FUORI_APP_RIDOTTA = "chiusura-fuori-app-ridotta"
SCENARIO_RIFIUTI = "rifiuti-betfair"
SCENARIO_TIMEOUT_ACCETTATO = "timeout-dopo-accettazione"
# UN solo rifiuto, e non tre come per Mike. Sulle registrazioni della Safe i
# piazzamenti di una partita sono pochissimi (tre su 35797769): rifiutarli tutti
# vuol dire una partita senza NESSUN ordine a mercato, e allora K1/K3/K4/K5
# restano senza caso e l'unica cosa che lo scenario dimostra e' che il bot sa
# dire «error». Con uno solo si ha il rifiuto (K2 ha il suo caso) E il resto
# della partita resta quella vera, ordini compresi.
QUANTI_RIFIUTI = 1
QUANTI_GUASTI = 3
# ogni quanti giri, dopo l'apertura, il trader chiede la chiusura (cash out):
# 60 giri x 2 s = due minuti di tempo di MERCATO.
GIRI_PRIMA_DEL_CASHOUT = 60
# gli scenari in cui il trader preme «Investi»: servono a far esistere un
# ordine VERO su flumine anche quando nessuna delle tre strategie entra.
SCENARI_CON_ORDINE_MANUALE = ("cap-stretto", "bot-fermo", "esiti-ignoti",
                              "feed-stantio", "riavvio", "paper",
                              "ordini-manuali", "due-lay", "manuale-e-bot")

SCENARI_DESCRITTI: Dict[str, str] = {
    "base": "le tre strategie calcio accese in LIVE, come girerebbero in produzione",
    "cap-stretto": "max_liability_per_trade stretto: parla il gate di rischio",
    SCENARIO_BOT_FERMO: "bot fermo con posizioni aperte: nessuna apertura, "
                        "protezioni e uscite continuano (§6.3)",
    SCENARIO_ESITI_IGNOTI: "i primi piazzamenti a esito IGNOTO: righe in "
                           "riconciliazione, mai ripiazzate (§6.4)",
    SCENARIO_FEED_STANTIO: "riga E scanner vecchi: nessun ingresso (CERT 12/09)",
    SCENARIO_RIAVVIO: "riavvio a meta' partita: lo stato si ritrova dal DB (difetto 19)",
    SCENARIO_PAPER: "percorso PAPER legacy (_paper_ladder + paper_fill): NON passa "
                    "da flumine: serve a MISURARE la divergenza, non a certificarla",
    SCENARIO_ORDINI: "il trader preme «Investi» e poi «Chiudi» dalla UI "
                     "(safe_strategy_requests): ordine VERO su flumine, FOK, bet "
                     "delay, riconciliazione, chiusura e settlement. NON tocca la "
                     "strategia: e' il percorso manuale di produzione",
    SCENARIO_DUE_LAY: "DUE lay MANUALI sulla stessa selezione (doppio «Investi» "
                      "con due chiavi): T12 ha un caso e deve TACERE, perche' le "
                      "operazioni del trader non sono del bot (16/09)",
    SCENARIO_MANUALE_E_BOT: "riga MANUALE viva sulla STESSA selezione che il bot "
                            "banca, col bot acceso: le gambe del bot devono "
                            "restare identiche allo scenario `base` e il bot non "
                            "deve mai toccare la riga del trader (T12, T13)",
    SCENARIO_CASHOUT_GLOBALE: "l'utente chiude a mano TUTTE le operazioni della "
                              "partita (una `cashout` per riga viva, percorso "
                              "vero del servizio): dal giro dopo il bot non deve "
                              "aprire ne' gestire altro (T14)",
    SCENARIO_FUORI_APP: "il trader chiude la posizione del bot con un ordine SUO "
                        "su Betfair, FUORI dall'app (ref non del bot): il bot deve "
                        "accorgersene dalla posizione di CONTO, scrivere "
                        "`chiuso_dall_utente` e non fare altro (T14)",
    SCENARIO_FUORI_APP_RIDOTTA: "come sopra ma il trader chiude solo META' della "
                                "posizione: il bot lo DICHIARA "
                                "(`ridotta_dall_utente`) e continua a proteggere "
                                "il resto — una copertura parziale non e' un "
                                "cash-out",
    SCENARIO_RIFIUTI: "Betfair RIFIUTA (`ok=False`) i primi piazzamenti sul lato "
                      "LAY, quello con cui Safe APRE: la riga non deve mai restare "
                      "viva su un ordine che non esiste (difetto 2 del 15/09)",
    SCENARIO_TIMEOUT_ACCETTATO: "timeout della REST DOPO che Betfair ha accettato: "
                                "la riga torna in riconciliazione senza bet_id e "
                                "l'ordine vero resta a mercato. Si ritrova solo col "
                                "ref con cui e' stato CHIESTO (difetto 4 del 15/09)",
    SCENARIO_SELEZIONE: "la «selezione aggiuntiva» della SPEC §2 ACCESA "
                        "(`esatto.requireSelection`): il filtro scontri diretti "
                        "+ difesa avversaria gira davvero e il controllo E10 ha "
                        "i suoi casi. Con i dati storici assenti il verdetto e' "
                        "n/d e la variante NON entra: e' la regola del motore",
}


# ---------------------------------------------------------------------------
# il database in memoria, con le FIRME di `bot_db.py` e `db.py`
# ---------------------------------------------------------------------------
class DbSafeMemoria(DbMemoria):
    """Le tabelle della Safe in RAM, funzione per funzione come il DB vero.

    ⚠️ Ogni metodo ha la firma E IL TIPO DI RITORNO del vero
    (`Betfair/safe_strategy/bot_db.py` per il bot,
    `Betfair/safe_strategy/db.py` per lo scanner): `insert_trade` torna l'ID
    (`Optional[int]`) e non la riga, `traded_signal_keys` torna un `set` di
    tuple e non `None`, `aggregates` torna il dizionario di `aggregate_rows`.
    Un doppio che risponde a domande a cui il vero non risponde e' la causa di
    tutti i difetti del 15/09 (catalogo §7.27).

    Gli aggregati NON sono ricalcolati qui: si passano le righe alla funzione
    PURA di produzione `bot_db.aggregate_rows`, cosi' il numero che il bot legge
    nel replay e' prodotto dallo stesso codice che lo produce in live.
    """

    def __init__(self, control: Dict[str, Any], *, orologio=None) -> None:
        super().__init__(control)
        self.requests: List[Dict[str, Any]] = []
        self.opportunita: List[Dict[str, Any]] = []
        self.scan_table: Dict[str, Dict[str, Any]] = {}
        self._req_id = 0
        # eta' dichiarata del battito dello SCANNER (scenario `feed-stantio`):
        # senza un attributo VERO, `__getattr__` del banco la trasformerebbe in
        # un metodo e la freschezza mentirebbe in silenzio.
        self.scanner_vecchio_s: float = 0.0
        # l'orologio del replay: `updated_at`/`ts` devono essere il TEMPO DI
        # MERCATO, non quello del PC che esegue il replay.
        self._orologio = orologio or (lambda: 0.0)

    # ------------------------------------------------------------- orologio
    def _ora_iso(self) -> str:
        return datetime.fromtimestamp(float(self._orologio()),
                                      tz=timezone.utc).isoformat()

    # --------------------------------------------------- bot_db: control
    def read_control(self) -> Optional[Dict[str, Any]]:
        return dict(self.control)

    def set_control(self, **fields: Any) -> None:
        if not fields:
            return
        fields.setdefault("updated_at", self._ora_iso())
        self.control.update(fields)

    def log(self, kind: str, payload: Optional[Dict[str, Any]] = None) -> None:
        # ⚠️ FIRMA IDENTICA AL VERO: `bot_db.log(kind, payload)` ha DUE
        # argomenti. Il banco comune ne ha un terzo (`event_id`, che serve a
        # Mike): tenerlo qui vorrebbe dire che il doppio risponde a una domanda
        # a cui il vero non risponde, ed e' la famiglia di difetti del 15/09.
        self.attivita.append((str(kind), dict(payload or {}), None))

    # ---------------------------------------------------- bot_db: trades
    def insert_trade(self, trade: Dict[str, Any]) -> Optional[int]:
        # l'indice unico `uq_safe_trades_signal` del DB vero: (event_id,
        # signal_key) per le righe AUTOMATICHE che non sono chiusure. Qui si
        # riproduce, altrimenti il banco sarebbe piu' permissivo del database.
        if (str(trade.get("origin")) == "auto" and trade.get("signal_key")
                and not trade.get("closes_trade_id")):
            chiave = (str(trade.get("event_id")), str(trade.get("signal_key")))
            for r in self.trades:
                if (str(r.get("origin")) == "auto" and not r.get("closes_trade_id")
                        and (str(r.get("event_id")), str(r.get("signal_key"))) == chiave
                        and str(r.get("status")) != "error"):
                    raise RuntimeError("duplicate key value violates unique constraint "
                                       "\"uq_safe_trades_signal\"")
        self._id += 1
        riga = {**trade, "id": self._id, "placed_at": self._ora_iso()}
        self.trades.append(riga)
        return self._id

    def update_trade(self, trade_id: int, **fields: Any) -> None:
        if not fields:
            return
        for r in self.trades:
            if int(r.get("id") or 0) == int(trade_id):
                r.update(fields)
                return

    def delete_trade(self, trade_id: int) -> None:
        """Il vero cancella SOLO una riserva ancora 'pending'."""
        for i, r in enumerate(self.trades):
            if int(r.get("id") or 0) == int(trade_id) and str(r.get("status")) == "pending":
                self.trades.pop(i)
                return

    def get_trade(self, trade_id: int) -> Optional[Dict[str, Any]]:
        for r in self.trades:
            if int(r.get("id") or 0) == int(trade_id):
                return dict(r)
        return None

    def list_trades(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.trades
                if status is None or str(r.get("status")) == str(status)]

    def open_trades(self, mode: Optional[str] = None) -> List[Dict[str, Any]]:
        """'open' e 'hedged' — MAI 'pending' (il vero: `bot_db.open_trades`)."""
        from .. import bot_db as BD

        m = BD._norm_mode(mode)
        out = [dict(r) for r in self.trades if str(r.get("status")) in ("open", "hedged")]
        return [r for r in out if not m or BD.row_mode(r) == m]

    def closing_trades_for(self, trade_ids: List[int]) -> List[Dict[str, Any]]:
        voluti = {int(i) for i in (trade_ids or [])}
        return [dict(r) for r in self.trades
                if r.get("closes_trade_id") is not None
                and int(r.get("closes_trade_id") or 0) in voluti]

    def trade_by_idempotency_key(self, key: str,
                                 mode: Optional[str] = None) -> Optional[Dict[str, Any]]:
        from .. import bot_db as BD

        m = BD._norm_mode(mode)
        for r in self.trades:
            meta = r.get("meta") if isinstance(r.get("meta"), dict) else {}
            if str(meta.get("idempotency_key") or "") != str(key):
                continue
            if str(r.get("status")) == "error":
                continue
            if m and BD.row_mode(r) != m:
                continue
            return {"id": r.get("id"), "status": r.get("status"),
                    "meta": r.get("meta"), "mode": r.get("mode")}
        return None

    def traded_signal_keys(self, mode: Optional[str] = None) -> set:
        from .. import bot_db as BD

        m = BD._norm_mode(mode)
        out: set = set()
        for r in self.trades:
            if str(r.get("origin")) != "auto" or str(r.get("status")) == "error":
                continue
            if r.get("closes_trade_id") is not None:
                continue
            if m and BD.row_mode(r) != m:
                continue
            eid, key = r.get("event_id"), r.get("signal_key")
            if eid and key:
                out.add((str(eid), str(key)))
        return out

    def aggregates(self, now: Optional[datetime] = None,
                   mode: Optional[str] = None) -> Dict[str, float]:
        """La funzione PURA di produzione, sulle righe in memoria."""
        from .. import bot_db as BD
        from .. import risk as _risk

        m = BD._norm_mode(mode)
        righe = [dict(r) for r in self.trades if not m or BD.row_mode(r) == m]
        quando = now or datetime.fromtimestamp(float(self._orologio()), tz=timezone.utc)
        return BD.aggregate_rows(righe, day_start=_risk.operating_day_start(quando))

    def place_attempts(self) -> Dict[Tuple[str, str], Dict[str, Any]]:
        out: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for r in self.trades:
            if str(r.get("origin")) != "auto" or str(r.get("status")) != "error":
                continue
            eid, key = r.get("event_id"), r.get("signal_key")
            pl = (r.get("meta") or {}).get("place")
            if not (eid and key and isinstance(pl, dict)):
                continue
            prec = out.get((str(eid), str(key))) or {}
            if int(pl.get("attempts") or 0) >= int(prec.get("attempts") or 0):
                out[(str(eid), str(key))] = {"attempts": int(pl.get("attempts") or 0),
                                             "last_ts": pl.get("last_ts"),
                                             "final": bool(pl.get("final"))}
        return out

    def recent_activity(self, limit: int = 60) -> List[Dict[str, Any]]:
        righe = [{"id": i, "ts": None, "kind": k, "payload": p}
                 for i, (k, p, _e) in enumerate(self.attivita)]
        return list(reversed(righe))[:int(limit)]

    # -------------------------------------------------- bot_db: richieste
    def pending_requests(self, limit: int = 50) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.requests
                if str(r.get("status")) == "pending"][:int(limit)]

    def proposta_di_chiusura_viva(self, trade_id: int) -> Optional[Dict[str, Any]]:
        for r in self.requests:
            if (str(r.get("status")) == "proposed"
                    and str((r.get("payload") or {}).get("trade_id")) == str(int(trade_id))):
                return dict(r)
        return None

    def scrivi_proposta_di_chiusura(self, trade_id: int,
                                    payload: Dict[str, Any]) -> Optional[int]:
        corpo = {**payload, "trade_id": int(trade_id)}
        viva = self.proposta_di_chiusura_viva(trade_id)
        if viva is not None:
            for r in self.requests:
                if int(r.get("id") or 0) == int(viva["id"]):
                    r["payload"] = corpo
                    r["updated_at"] = self._ora_iso()
            return int(viva["id"])
        self._req_id += 1
        self.requests.append({"id": self._req_id, "kind": "cashout",
                              "status": "proposed", "payload": corpo,
                              "created_at": self._ora_iso(), "result": None})
        return self._req_id

    def chiudi_proposta(self, trade_id: int, motivo: str) -> None:
        viva = self.proposta_di_chiusura_viva(trade_id)
        if viva is None:
            return
        for r in self.requests:
            if int(r.get("id") or 0) == int(viva["id"]):
                r["status"] = "rejected"
                r["result"] = {**(r.get("result") or {}), "decaduta": True,
                               "motivo": str(motivo)[:200]}
                r["updated_at"] = self._ora_iso()

    def set_request_status(self, req_id: int, status: str,
                           result: Optional[Dict[str, Any]] = None) -> None:
        for r in self.requests:
            if int(r.get("id") or 0) == int(req_id):
                r["status"] = str(status)
                if result is not None:
                    r["result"] = result
                r["updated_at"] = self._ora_iso()

    def fail_stale_processing(self, max_age_min: int = 10) -> None:
        for r in self.requests:
            if str(r.get("status")) == "processing":
                r["status"] = "error"
                r["result"] = {"err": "servizio interrotto durante l'elaborazione"}

    # ---------------------------------------------- bot_db: opportunita'
    def upsert_opportunities(self, rows: List[Dict[str, Any]]) -> None:
        per_evento = {str(r.get("event_id")): r for r in (rows or [])}
        self.opportunita = [r for r in self.opportunita
                            if str(r.get("event_id")) not in per_evento]
        self.opportunita.extend(per_evento.values())

    def purge_opportunities(self, older_than_iso: str) -> None:
        return None

    def delete_opportunities(self, event_ids: List[str]) -> None:
        fuori = {str(e) for e in (event_ids or [])}
        self.opportunita = [r for r in self.opportunita
                            if str(r.get("event_id")) not in fuori]

    # --------------------------------- bot_db: dati che la registrazione NON ha
    def _senza(self, nome: str, causa: str):
        voce = (nome, causa)
        if voce not in self.senza_dato:
            self.senza_dato.append(voce)

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        self._senza("get_event", "tabella `events` (anagrafica partite): non e' "
                                 "nello stream di mercato registrato")
        return None

    def fixtures_for_window(self, start_iso: str, end_iso: str) -> List[Dict[str, Any]]:
        self._senza("fixtures_for_window", "calendario `fixtures` del database "
                                           "calcio: fuori dalla registrazione")
        return []

    def fixture_analysis(self, fixture_id: int) -> Optional[Dict[str, Any]]:
        self._senza("fixture_analysis", "analisi Poisson per fixture: fuori "
                                        "dalla registrazione")
        return None

    def live_follow_status(self, event_id: str) -> Optional[str]:
        self._senza("live_follow_status", "tabella `live_follow` (copertura del "
                                          "pool stream): non e' nella registrazione")
        return None

    def runner_heartbeat(self) -> Optional[Dict[str, Any]]:
        # NIENTE runner: il gate flumine resta CHIUSO e l'ordine passa dal
        # percorso REST, che nel banco e' servito da `MercatoFlumine`.
        self._senza("runner_heartbeat", "battito del runner della coda: nel "
                                        "replay il runner non esiste, quindi il "
                                        "gate flumine e' chiuso e si usa il REST")
        return None

    def enqueue_live_order(self, payload: Dict[str, Any]) -> Optional[int]:
        self._senza("enqueue_live_order", "coda `betfair_live_order_requests`: "
                                          "nel replay non c'e' un worker")
        return None

    def get_live_order_request_by_ref(self, client_ref: str) -> Optional[Dict[str, Any]]:
        return None

    def get_live_order_request(self, request_id: int) -> Optional[Dict[str, Any]]:
        return None

    def revoke_live_order_request(self, request_id: int) -> bool:
        return False

    def get_live_order_mirror(self, client_order_ref: str,
                              mode: str = "paper") -> Optional[Dict[str, Any]]:
        return None

    # ------------------------------------------------------- bot_db: feed
    def fetch_scan_rows(self) -> List[Dict[str, Any]]:
        return list(self.scan_rows)

    def scanner_status(self) -> Optional[Dict[str, Any]]:
        """Il battito dello SCANNER, col tempo di MERCATO.

        Serve alla regola della freschezza (`exits.feed_is_fresh`): una riga
        ferma con lo scanner vivo e' legittima (write-on-change), una riga
        ferma con lo scanner morto no. Nel replay lo scanner e' vivo per
        costruzione, tranne nello scenario `feed-stantio`, che lo invecchia.
        """
        eta = float(getattr(self, "scanner_vecchio_s", 0.0) or 0.0)
        quando = float(self._orologio()) - eta
        return {"payload": {}, "updated_at": datetime.fromtimestamp(
            quando, tz=timezone.utc).isoformat()}

    # ------------------------------ db.py (scanner): stesse firme del vero
    def list_scan_event_ids(self) -> Optional[List[str]]:
        return [str(k) for k in self.scan_table]

    def load_scan_pre_ko(self, event_ids: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        from .. import db as SD

        out: Dict[str, Optional[Dict[str, Any]]] = {}
        for eid in [str(e) for e in (event_ids or []) if e]:
            pre = ((self.scan_table.get(eid) or {}).get("payload") or {}).get("pre_ko")
            out[eid] = dict(pre) if SD.is_usable_pre_ko(pre) else None
        return out

    def upsert_scan_rows(self, rows: List[Dict[str, Any]]) -> bool:
        for r in rows or []:
            self.scan_table[str(r.get("event_id"))] = dict(r)
        return True

    def delete_scan_rows(self, event_ids: List[str]) -> None:
        for e in event_ids or []:
            self.scan_table.pop(str(e), None)

    def upsert_status(self, payload: Dict[str, Any]) -> None:
        return None

    def list_mike_followed_event_ids(self) -> Optional[List[str]]:
        self._senza("list_mike_followed_event_ids", "tabella `mike_events`: nel "
                                                    "replay Safe gira da sola")
        return None


# ---------------------------------------------------------------------------
# il mercato: flumine, piu' le letture che il servizio della Safe chiede
# ---------------------------------------------------------------------------
class MercatoSafe(MercatoFlumine):
    """`MercatoFlumine` + `read_market`/`read_markets`/`order_state_by_bet_id`.

    Sono le tre letture che `bot_service` chiede al mercato oltre al
    piazzamento, e senza le quali settlement e riconciliazione per `bet_id`
    non verrebbero MAI esercitati (resterebbero due ⊘ silenziosi).
    Il contenuto NON e' inventato: viene dall'ultimo `marketDefinition` della
    registrazione, che a mercato chiuso porta gli esiti WINNER/LOSER veri.
    """

    def __init__(self, strategia: Any, motore: Optional[MotoreReplay] = None) -> None:
        super().__init__(strategia, motore)
        # market_id -> (status, inplay, {selection_id: runner_status})
        self.definizioni: Dict[str, Dict[str, Any]] = {}

    def registra_definizione(self, market_book: Any) -> None:
        md = getattr(market_book, "market_definition", None)
        mid = str(getattr(market_book, "market_id", "") or "")
        if not mid or md is None:
            return
        self.definizioni[mid] = {
            "status": str(getattr(md, "status", None) or "OPEN").upper(),
            "inplay": bool(getattr(md, "in_play", False)),
            "runners": {int(getattr(r, "selection_id", 0) or 0):
                        str(getattr(r, "status", "") or "").upper()
                        for r in (getattr(md, "runners", None) or [])
                        if getattr(r, "selection_id", None) is not None},
        }

    def read_market(self, cs: Any) -> Optional[Any]:
        from ...omega.omega_market import MarketSnapshot

        mid = str(getattr(cs, "market_id", "") or "")
        d = self.definizioni.get(mid)
        if d is None:
            return None
        stato = str(d["status"])
        vincitore = next((sid for sid, st in (d["runners"] or {}).items()
                          if st == "WINNER"), None)
        chiuso = stato in ("CLOSED", "SETTLED")
        annullato = stato in ("VOID", "VOIDED")
        return MarketSnapshot(
            status=stato, inplay=bool(d["inplay"]), runners=[],
            closed=bool(chiuso or annullato),
            winner_selection_id=(int(vincitore) if vincitore is not None else None),
            voided=bool(annullato or (chiuso and vincitore is None)),
            void_reason=("market_status_void" if annullato
                         else ("closed_senza_winner" if chiuso and vincitore is None
                               else None)))

    def read_markets(self, mercati: List[Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for cs in mercati or []:
            mid = str(getattr(cs, "market_id", "") or "")
            if mid:
                out[mid] = self.read_market(cs)
        return out

    def riga_ordine(self, customer_ref: str) -> Optional[Dict[str, Any]]:
        """L'ordine nella forma che `omega_market.list_current_orders` produce.

        Non e' una chiave nuova ne' un campo inventato: e' esattamente il
        dizionario di `MercatoFlumine._riga` (snake_case, `size_requested`,
        `size_matched`, `size_remaining`, `size_cancelled`, `avg_price_matched`),
        cioe' quello che il bot legge in produzione.
        """
        ordine = self.ordini.get(str(customer_ref))
        return self._riga(str(customer_ref), ordine) if ordine is not None else None

    def order_state_by_bet_id(self, bet_id: str) -> Dict[str, Any]:
        """Stato REALE di UN ordine per betId, come `omega_market`.

        Solleva su rete KO in produzione; qui l'ordine c'e' o non c'e'.
        """
        ordine = self._per_bet_id(bet_id)
        if ordine is None:
            return {"found": False}
        riga = self._riga(str(getattr(ordine, "notes", {}).get("bot_ref", "")), ordine)
        return {"found": True,
                "size_matched": riga["size_matched"],
                "avg_price_matched": riga["avg_price_matched"],
                "size_remaining": riga["size_remaining"],
                "matched_date": None, "placed_date": None}


# ---------------------------------------------------------------------------
# i freni LIVE: l'operatore deve aver dichiarato il sistema in LIVE
# ---------------------------------------------------------------------------
@contextmanager
def freni_live(attivi: bool) -> Iterator[None]:
    """`LIVE_ORDER_MODE` / `LIVE_KILL_SWITCH` per la durata del replay.

    NON e' una modifica di strategia: sono i due freni GLOBALI dell'operatore
    (`Betfair/stream/config_stream.py`), che in produzione l'utente dichiara nel
    `.env`. Con i default (`OFF`) `execution._live_brake` blocca OGNI apertura
    live e il percorso ordini non verrebbe mai percorso: il replay direbbe
    «nessun ordine» e non si saprebbe perche'. Si dichiarano qui, e si
    rimettono com'erano alla fine (sono di PROCESSO).
    """
    prima = {k: os.environ.get(k) for k in ("LIVE_ORDER_MODE", "LIVE_KILL_SWITCH")}
    try:
        if attivi:
            os.environ["LIVE_ORDER_MODE"] = "LIVE"
            os.environ["LIVE_KILL_SWITCH"] = "false"
        yield
    finally:
        for k, v in prima.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# LE CACHE DI PROCESSO di `bot_service`. Sono quelle che un riavvio del
# servizio si porta via, e quelle che fra un replay e l'altro nello stesso
# interprete devono tornare come nuove.
# ⚠️ Due gruppi, e la differenza NON e' un dettaglio: le prime sono mappe che
# nascono vuote (`.clear()` basta), le seconde hanno CHIAVI FISSE che il codice
# legge senza `.get` (`_LOG_MODE["value"]`, `_APERTE["n"]`): svuotarle
# produrrebbe un `KeyError` al primo giro, cioe' un guasto del banco scambiato
# per un difetto del bot.
_CACHE_VUOTE = ("_OPTIONAL_MODS", "_CONSAPEVOLEZZA_SCRITTA", "_MARKET_MISSING",
                "_EXIT_WAIT_AT", "_FEED_BLIND_LOG", "_DATO_MANCANTE_LOG",
                "_PLACE_ATTEMPTS", "_SKIP_LOG_STATE", "_EVENT_NAMES",
                "_PENDING_CICLO", "_AGG_ULTIMO_BUONO", "_AGG_LOG_TS",
                "_LAST_CONTROL",
                # ⚠️ 16/09 SERA - LE DUE CHE MANCAVANO, ed erano le due che
                # rompevano la pool (catalogo §7 punto 37). Sono ENTRAMBE
                # indicizzate per market_id / event_id: dentro `--scenari tutti`
                # gli scenari girano sulla STESSA partita, uno dopo l'altro nello
                # stesso figlio, quindi la chiave e' identica e il valore del
                # primo scenario SOPRAVVIVE nel secondo.
                #  * `_CONTO_LETTO_A` = l'istante dell'ultima lettura della
                #    POSIZIONE DI CONTO per mercato (respiro di 30 s): ereditato,
                #    lo scenario `chiusura-fuori-app` non legge il conto per i
                #    primi 30 s di partita e T14/S4 restano a zero;
                #  * `_EVENTI_CHIUSI` = gli eventi gia' dichiarati chiusi:
                #    ereditato, il secondo scenario nasce con la partita gia'
                #    «chiusa» e il bot non fa niente.
                "_CONTO_LETTO_A", "_EVENTI_CHIUSI")

# le cache di processo che NON vivono in `bot_service`: sono di altri moduli
# dello stesso servizio e un replay le eredita esattamente allo stesso modo.
# `modulo -> nomi`: l'elenco resta ESPLICITO (difetto 37 del catalogo: un
# azzeramento con `dir()` svuota anche cio' che non deve).
_CACHE_ALTRI_MODULI = {
    "Betfair.safe_strategy.bot_db": ("_AGG_RPC",),
    "Betfair.safe_strategy.selezione": ("_HINT_CACHE",),
}
# DICHIARATO E NON AZZERATO: `selezione._ATLAS` e `selezione._INDICE_NOMI` sono
# l'atlante letto DAL DISCO una volta per processo. E' sola lettura e identico
# per tutti gli scenari: non puo' far dire a un replay una cosa diversa da
# quella che direbbe da solo, e ricaricarlo a ogni scenario costerebbe la
# lettura del file per niente.
_CACHE_CON_CHIAVI = {
    "_REST_STATE": {"last": {}, "cycle_ts": 0.0, "used": 0},
    "_SCANNER_TS_CACHE": {"cycle_ts": None, "value": None},
    "_LETTURA_FEED": {"ms": 0.0},
    "_PLACE_SEED": {"ts": 0.0},
    "_EREDITA_LOG": {"ts": 0.0},
    "_COPERTURA_LOG": {"ts": 0.0},
    "_OPPS_STATE": {"last_ts": 0.0, "hashes": {}},
    "_APERTE": {"n": 0},
    "_BLOCCO": {"motivo": None, "tetto": None, "aperte": None},
    "_LOG_MODE": {"value": ""},
    "_CICLO_IN_ERRORE": {"value": False},
    "_EXIT_MODEL": {"model": None, "mod": None},
    "_SVEGLIA_FATTA": {"req_id": 0},
}


def richiesta_manuale(row: Dict[str, Any], params: Dict[str, Any],
                      mode: str) -> Optional[Dict[str, Any]]:
    """Il payload che la UI accoda quando il trader preme «Investi».

    Non e' una scorciatoia e non altera niente: e' il percorso MANUALE di
    produzione (`safe_strategy_requests` -> `process_requests` ->
    `_request_place` -> `_execute` -> `execution.place`), lo stesso bottone che
    il trader ha in pagina. Serve perche' su una registrazione in cui nessuna
    delle tre strategie entra il CICLO DI VITA DELL'ORDINE non verrebbe
    esercitato MAI, e la §6.4 del processo resterebbe tutta «non lo so».

    La selezione e' la SFAVORITA pre-KO sul 1X2 e il prezzo e' il suo LAY
    corrente: le coordinate vengono dal contesto VERO
    (`engine.build_football_ctx_from_scan`, `engine.favorite_side`), mai
    scritte a mano.
    """
    payload = row.get("payload") if isinstance(row, dict) else None
    if not isinstance(payload, dict) or not payload.get("inplay"):
        return None
    ctx = E.build_football_ctx_from_scan(str(row.get("event_id")), payload, None, None)
    fav = E.favorite_side(ctx.pre_match)
    if fav is None or ctx.match_odds_market_id is None:
        return None
    dog = "away" if fav == "home" else "home"
    coppia = E._side_pair(ctx.odds, dog)
    if coppia is None or coppia.lay is None or coppia.selection_id is None:
        return None
    return {
        "event_id": str(row.get("event_id")),
        "event_name": payload.get("event_name"),
        "sport": "calcio",
        "market_id": str(ctx.match_odds_market_id),
        "market_type": "MATCH_ODDS",
        "selection_id": int(coppia.selection_id),
        "selection_name": (ctx.home if dog == "home" else ctx.away),
        "side": "lay",
        "mode": str(mode),
        "price": float(coppia.lay),
        "size": float(E.stake_di_strategia(params, "base", "lay")),
        "minute": payload.get("minute"),
        "score": f"{payload.get('score_home')}-{payload.get('score_away')}",
        "idempotency_key": f"replay-{row.get('event_id')}-manuale",
    }


def richiesta_manuale_cs(row: Dict[str, Any], params: Dict[str, Any],
                         mode: str) -> Optional[Dict[str, Any]]:
    """«Investi» del trader sulla STESSA selezione che banca la Safe R.E.

    E' la condizione che il chiarimento dell'utente del 16/09 descrive: il
    trader opera a mano sulla partita su cui il bot sta lavorando, e sulla
    stessa selezione. Le coordinate vengono dal contesto VERO
    (`engine.build_football_ctx_from_scan`): «Altro risultato Casa» del
    mercato Risultato Esatto, al suo prezzo di banca corrente.
    """
    payload = row.get("payload") if isinstance(row, dict) else None
    if not isinstance(payload, dict) or not payload.get("inplay"):
        return None
    ctx = E.build_football_ctx_from_scan(str(row.get("event_id")), payload, None, None)
    if ctx.correct_score_market_id is None or ctx.any_other is None:
        return None
    coppia = ctx.any_other.home
    sid = ctx.any_other_home_selection_id
    if coppia is None or coppia.lay is None or sid is None:
        return None
    return {
        "event_id": str(row.get("event_id")),
        "event_name": payload.get("event_name"),
        "sport": "calcio",
        "market_id": str(ctx.correct_score_market_id),
        "market_type": "CORRECT_SCORE",
        "selection_id": int(sid),
        "selection_name": "Altro risultato Casa",
        "side": "lay",
        "mode": str(mode),
        "price": float(coppia.lay),
        "size": float(E.stake_di_strategia(params, "esatto", "lay")),
        "minute": payload.get("minute"),
        "score": f"{payload.get('score_home')}-{payload.get('score_away')}",
        "idempotency_key": f"replay-{row.get('event_id')}-manuale-cs",
    }


def _riavvia_processo() -> List[str]:
    """Butta via le cache di PROCESSO di `bot_service`, come un riavvio.

    Non tocca il database in memoria: quello e' il DB, e in produzione
    sopravvive. E' il difetto 19 del catalogo (`pre_ko` che viveva solo in RAM:
    base e punta spente per ore) riprodotto apposta invece che aspettato.
    """
    import importlib

    azzerati: List[str] = []
    for nome in _CACHE_VUOTE:
        v = getattr(BS, nome, None)
        if isinstance(v, dict) and v:
            v.clear()
            azzerati.append(nome)
    for nome, iniziale in _CACHE_CON_CHIAVI.items():
        v = getattr(BS, nome, None)
        if isinstance(v, dict):
            v.clear()
            v.update({k: (dict(x) if isinstance(x, dict) else x)
                      for k, x in iniziale.items()})
            azzerati.append(nome)
    # le cache degli ALTRI moduli dello stesso servizio
    for modulo, nomi in _CACHE_ALTRI_MODULI.items():
        try:
            mod = importlib.import_module(modulo)
        except ImportError:                 # modulo opzionale: si dichiara e basta
            continue
        for nome in nomi:
            v = getattr(mod, nome, None)
            if isinstance(v, dict) and v:
                v.clear()
                azzerati.append(f"{modulo.rsplit('.', 1)[-1]}.{nome}")
    # LA GUARDIA D'AVVIO non e' un dizionario ma e' stato di PROCESSO identico:
    # ereditata, il secondo replay crede di essere gia' partito e non riapplica
    # il freno delle aperture al primo giro (difetto 22 del catalogo).
    guardia = getattr(BS, "_GUARDIA_AVVIO", None)
    if guardia is not None and hasattr(guardia, "azzera"):
        guardia.azzera()
        azzerati.append("_GUARDIA_AVVIO")
    return sorted(azzerati)


# ---------------------------------------------------------------------------
# la strategia flumine: alimenta lo scanner, fa girare `run_once`, certifica
# ---------------------------------------------------------------------------
def _crea_strategia():
    from flumine import BaseStrategy

    class SafeCert(BaseStrategy):
        """A ogni tick alimenta lo SCANNER VERO coi book di flumine e, alla
        cadenza del servizio, chiama `bot_service.run_once` — il ciclo INTERO."""

        def __init__(self, *, event_id: str, params_grezzi: Dict[str, Any],
                     banco: ScannerReplay,
                     punteggi: List[Tuple[int, Dict[str, Any]]],
                     ogni_ms: int = 2000, **kw: Any) -> None:
            self.event_id = str(event_id)
            self.params_grezzi = dict(params_grezzi)
            self.banco = banco
            self._punteggi = list(punteggi or [])
            self._ts_punteggi = [t for t, _ in self._punteggi]
            self._i_punteggi = 0
            self.ogni_ms = int(ogni_ms)
            self.invecchia_s = float(kw.pop("invecchia_s", 0.0) or 0.0)
            self.riavvia = bool(kw.pop("riavvia", False))
            # il trader che preme «Investi» e poi «Chiudi»: un ordine VERO su
            # flumine anche quando nessuna delle tre strategie entra.
            self.ordine_manuale = bool(kw.pop("ordine_manuale", False))
            # due «Investi» sulla stessa selezione: e' la condizione vietata
            # dalla regola di piattaforma, e va PROVOCATA per giudicarla.
            self.doppia_lay = bool(kw.pop("doppia_lay", False))
            # il trader opera sulla STESSA selezione del bot (Correct Score)
            self.manuale_sul_bot = bool(kw.pop("manuale_sul_bot", False))
            # CASH-OUT GLOBALE dell'utente: si chiude tutto e si dichiara
            # l'istante, cosi' il controllo T14 sa da quando giudicare.
            self.cashout_globale = bool(kw.pop("cashout_globale", False))
            # TIMEOUT della REST DOPO l'accettazione di Betfair (difetto 4)
            self.timeout_accettato = bool(kw.pop("timeout_accettato", False))
            self.timeout_fatto: Optional[Dict[str, Any]] = None
            # CHIUSURA FUORI DALL'APP: "intera" | "ridotta" | None
            self.fuori_app: Optional[str] = kw.pop("fuori_app", None)
            self.fuori_app_fatta: Optional[Dict[str, Any]] = None
            self.chiuso_dall_utente: Dict[str, float] = {}
            self.richiesta_fatta = False
            self.cashout_chiesto = False
            self.giri_da_apertura = 0
            self.mode = str(kw.pop("mode", "live"))
            self.status = str(kw.pop("status", "running"))
            self.riavvio_fatto: Optional[List[str]] = None

            self.mercati: Dict[str, Any] = {}
            self.db = DbSafeMemoria(
                {"id": 1, "status": self.status, "mode": self.mode,
                 "params": self.params_grezzi, "stats": {}},
                orologio=lambda: self.banco.ora)
            self.mercato = MercatoSafe(self)
            self.referto = CERT.Referto(event_id=str(event_id))
            self.params: Dict[str, Any] = BS.resolve_params(self.params_grezzi,
                                                            engine_mod=E)
            self.motore_segnali = E.SafeEngine(self.params,
                                               clock=lambda: self.banco.ora)
            self.opps_state: Dict[str, Any] = {}
            self._ultimo_ms: int = 0
            self.righe_assenti = 0
            self.giri = 0
            # quante righe di attivita' erano gia' scritte a inizio giro: la
            # differenza sono quelle di QUESTO giro (controllo T12).
            self._attivita_a_inizio_giro = 0
            # il PRIMO riferimento 1X2 visto in gioco: serve al controllo B11
            self.pre_ko_congelato: Optional[Dict[str, float]] = None
            # ordini e uscite osservati, per il referto
            self.ordini_osservati = 0
            # gli ordini partiti in QUESTO giro, giudicati a fine giro: prima
            # della conferma la riga porta ancora i numeri della RISERVA
            # (chiesto, non abbinato) e ogni controllo J* griderebbe al lupo.
            self.ordini_del_giro: List[Tuple[Any, str, Dict[str, Any], Any, float]] = []
            self.uscite_osservate = 0
            self.aperture_nel_giro = 0
            self.segnali_di_variante_spenta = 0
            super().__init__(**kw)

        # ---------------------------------------------------------- flumine
        def check_market_book(self, market, market_book) -> bool:
            return True

        def process_market_book(self, market, market_book) -> None:
            mtype = self.banco.registra_mercato(market_book)
            if not mtype:
                return
            self.mercati[str(market_book.market_id)] = market
            self.mercato.registra_definizione(market_book)
            pt = getattr(market_book, "publish_time", None)
            pt_ms = (int(self.banco.imposta_ora(pt.timestamp()) * 1000)
                     if pt is not None else 0)
            self.banco.applica_book(market_book)
            # IL CONTEGGIO DEI TICK: i mercati che le tre strategie usano
            # davvero (1X2 e Risultato Esatto). Gli altri alimentano lo
            # scanner ma non sono cio' che il bot guarda.
            if mtype in ("MATCH_ODDS", "CORRECT_SCORE"):
                self.referto.tick += 1
            if pt_ms - self._ultimo_ms < self.ogni_ms:
                return
            self._ultimo_ms = pt_ms
            self._un_giro(pt_ms)

        # ------------------------------------------------------------ Safe
        def _un_giro(self, pt_ms: int) -> None:
            # 1) i punteggi arrivati fino a questo istante, dal record IPS
            #    grezzo e dal parser vero (`Scanner.apply_score_state`)
            i = bisect_right(self._ts_punteggi, int(pt_ms))
            while self._i_punteggi < i:
                self.banco.applica_punteggio(self.event_id,
                                             self._punteggi[self._i_punteggi][1])
                self._i_punteggi += 1
            # 2) LA RIGA LA SCRIVE LO SCANNER VERO
            self.banco.pubblica()
            row = self.banco.riga(self.event_id)
            if row is None:
                self.righe_assenti += 1
                righe = []
            else:
                if self.invecchia_s > 0:
                    row = dict(row, updated_at=_iso(pt_ms - int(self.invecchia_s * 1000)))
                righe = [row]
            self.db.scan_rows = righe
            self.db.upsert_scan_rows(righe)
            self.db.scanner_vecchio_s = self.invecchia_s
            # 2-bis) RIAVVIO a meta' partita con soldi dentro
            if (self.riavvia and self.riavvio_fatto is None
                    and any(str(r.get("status")) in ("open", "pending")
                            for r in self.db.trades)):
                self.riavvio_fatto = _riavvia_processo()
                self.db.log("replay_riavvio", {"azzerati": self.riavvio_fatto})
            # 2-ter) IL BOTTONE DEL TRADER (scenari con ordine manuale)
            if self.ordine_manuale and righe:
                self._forse_richiedi(righe[0])
            # 2-quater) IL CASH-OUT GLOBALE: l'utente chiude TUTTO
            if self.cashout_globale and not self.chiuso_dall_utente:
                self._forse_chiudi_tutto(pt_ms / 1000.0)
            # 2-quinquies) L'UTENTE CHIUDE FUORI DALL'APP, su Betfair
            if self.fuori_app and self.fuori_app_fatta is None:
                self._forse_chiudi_fuori_app(pt_ms / 1000.0)
            # 3) IL CICLO INTERO del servizio
            self.aperture_nel_giro = 0
            self._attivita_a_inizio_giro = len(self.db.attivita)
            adesso = datetime.fromtimestamp(pt_ms / 1000.0, tz=timezone.utc)
            try:
                esito = BS.run_once(db=self.db, market=self.mercato,
                                    engine=self.motore_segnali,
                                    opp_model=None, opp_mod=None, engine_mod=E,
                                    now=adesso, opps_state=self.opps_state,
                                    extra_mods={"anomaly": None, "combos": None,
                                                "tennis": None})
            except Exception as ex:  # noqa: BLE001 - un'eccezione del servizio E' un referto
                self.referto.violazioni.append(CERT.Violazione(
                    "SERVIZIO", "il giro del servizio non deve mai sollevare",
                    f"{type(ex).__name__}: {ex}"))
                return
            self.giri += 1
            self.referto.decisioni += 1
            # AZIONI = tutto cio' che il giro ha FATTO, non solo i segnali
            # automatici: le richieste della UI sono azioni sui soldi come le
            # altre, e un referto che le omette dice «azioni=0» con due ordini
            # veri a mercato.
            self.referto.azioni += (int(esito.get("placed") or 0)
                                    + int(esito.get("exits") or 0)
                                    + int(esito.get("settled") or 0)
                                    + int(esito.get("requests") or 0))
            # 4) GLI ORDINI, giudicati adesso: il servizio ha gia' scritto la
            #    riga (conferma, bet_id, prezzo medio). Giudicarli dentro
            #    `place` vorrebbe dire leggere la RISERVA e accusare il bot di
            #    non aver scritto quello che sta per scrivere.
            self._certifica_ordini()
            # 4-bis) I CONTROLLI K: LA MEMORIA DEL BOT CONTRO IL MERCATO.
            #    Si fanno QUI, dopo il giro del servizio, perche' solo qui
            #    esistono insieme le righe scritte dal bot e gli ORDINI VERI di
            #    flumine. I controlli B/E/P/T/J guardano la decisione; questi
            #    guardano il rapporto fra cio' che il bot crede e cio' che c'e'
            #    a mercato - ed e' li' che vivevano i cinque difetti del 15/09.
            self._verifica_consapevolezza()
            # 5) i controlli TRASVERSALI, a fine giro
            ciclo = CERT.Ciclo(db=self.db, market=self.mercato, params=self.params,
                               mode=self.mode, now_ts=pt_ms / 1000.0,
                               aperture_nel_giro=self.aperture_nel_giro,
                               feed_stantio=bool(self.invecchia_s > 0),
                               segnali_di_variante_spenta=self.segnali_di_variante_spenta,
                               attivita_del_giro=list(
                                   self.db.attivita[self._attivita_a_inizio_giro:]),
                               chiuso_dall_utente=dict(self.chiuso_dall_utente))
            self.referto.violazioni.extend(
                CERT.verifica(ciclo, self.referto.sollecitati,
                              self.referto.sollecitati_per_strategia))
            stato = f"{self.db.control.get('status')}/{self.db.control.get('mode')}"
            if stato not in self.referto.stati_visti:
                self.referto.stati_visti.append(stato)
            # 6) IL TIMEOUT DOPO L'ACCETTAZIONE, in CODA al giro: cosi' al giro
            #    successivo la riconciliazione lavora PRIMA che i controlli K
            #    guardino, ed e' il suo ESITO che si giudica - non il mezzo giro
            #    in cui la riga e' volutamente in riconciliazione.
            if self.timeout_accettato and self.timeout_fatto is None:
                self._forse_timeout_dopo_accettazione()

        def _forse_timeout_dopo_accettazione(self) -> None:
            """La REST va in timeout DOPO che Betfair ha preso l'ordine.

            Non si finge nessun ordine: quello a mercato e' il piazzamento VERO
            che il bot ha appena fatto su flumine. Si riporta la RIGA nello
            stato in cui la lascia `execution._reconciling` - 'pending', senza
            bet_id, `reason='place_exception_reconciling'` - che e' esattamente
            cio' che il servizio scrive quando la risposta non arriva. Da quel
            momento l'unica chiave per ritrovare l'ordine e' il ref con cui e'
            stato CHIESTO (`safe-t<id>`): e' il difetto 4 del 15/09, e senza
            questo gesto non ha MAI un caso, perche' lo scenario `esiti-ignoti`
            solleva PRIMA del piazzamento e un ordine da ritrovare non c'e'.
            """
            for r in self.db.trades:
                if str(r.get("status")) != "open" or not r.get("bet_id"):
                    continue
                meta = dict(r.get("meta") or {})
                meta.pop("fill", None)
                meta.update({"phase": "reserved",
                             "reason": "place_exception_reconciling",
                             "err": "timeout provocato DOPO l'accettazione"})
                self.timeout_fatto = {"trade_id": int(r["id"]),
                                      "bet_id": str(r.get("bet_id")),
                                      "size": r.get("size"), "price": r.get("price")}
                self.db.update_trade(int(r["id"]), status="pending", bet_id=None,
                                     meta=meta)
                self.db.log("replay_timeout_dopo_accettazione", self.timeout_fatto)
                return

        def _forse_chiudi_tutto(self, adesso: float) -> None:
            """L'utente chiude a mano TUTTE le operazioni della partita.

            Non e' un finto e non e' una scorciatoia: per ogni riga viva si
            accoda una richiesta `cashout` con `fraction=1.0`, che e' esattamente
            cio' che la UI manda a `bot_service.process_requests` ->
            `_request_cashout:1709`. Safe NON ha un `cashout_event` (quello vive
            nella coda del runner, `live_order_worker`, e non passa dalle sue
            tabelle): il cash-out globale della Safe E' questo insieme di
            richieste. Il fatto che non esista uno STATO «partita chiusa
            dall'utente» e' un reperto, non un dettaglio.
            """
            vive = [r for r in self.db.trades
                    if str(r.get("status")) == "open" and not r.get("closes_trade_id")]
            if not vive:
                return
            for r in vive:
                self.db._req_id += 1
                corpo = {"trade_id": int(r["id"]), "fraction": 1.0}
                self.db.requests.append(
                    {"id": self.db._req_id, "kind": "cashout", "status": "pending",
                     "payload": corpo, "created_at": self.db._ora_iso(),
                     "result": None})
                self.db.log("replay_cashout_globale", {"kind": "cashout",
                                                       "payload": corpo})
            self.chiuso_dall_utente[self.event_id] = float(adesso)

        def _forse_chiudi_fuori_app(self, adesso: float) -> None:
            """Il trader chiude la posizione del bot con un ordine SUO.

            Non e' un finto: l'ordine passa da
            `banco_comune.MercatoFlumine.place_order_utente`, cioe' dallo stesso
            `market.place_order` e dallo stesso matching del bot; l'unica
            differenza e' il `customer_order_ref`, che non e' del bot — come su
            Betfair, dove il bot filtra i propri ordini per
            `customerStrategyRef` e quindi NON vede questo.

            Prezzo: un limite che attraversa di sicuro (1,01 per un BACK, 1000
            per una LAY). Flumine abbina comunque al MIGLIOR prezzo del libro,
            non al limite: e' un ordine TAKER, che e' quello che fa chi chiude
            dal sito.
            """
            vive = [r for r in self.db.trades
                    if str(r.get("status")) == "open"
                    and str(r.get("origin") or "") == "auto"
                    and not r.get("closes_trade_id")
                    and float(r.get("size") or 0.0) > 0]
            if not vive:
                return
            tr = vive[0]
            lato_bot = str(tr.get("side") or "").lower()
            lato_utente = "back" if lato_bot == "lay" else "lay"
            size = round(float(tr.get("size") or 0.0)
                         * (0.5 if self.fuori_app == "ridotta" else 1.0), 2)
            if size < 0.01:
                return
            ordine = self.mercato.place_order_utente(
                market_id=str(tr.get("market_id")),
                selection_id=int(tr.get("selection_id") or 0),
                price=(1.01 if lato_utente == "back" else 1000.0),
                size=size, side=lato_utente,
                customer_ref=f"utente-fuori-app-{tr.get('id')}")
            dettaglio = {"trade_id": tr.get("id"), "lato_utente": lato_utente,
                         "size": size, "quota_del_bot": tr.get("size"),
                         "market_id": tr.get("market_id"),
                         "selection_id": tr.get("selection_id"),
                         "piazzato": ordine is not None,
                         "modo": self.fuori_app}
            self.db.log("replay_chiusura_fuori_app", dettaglio)
            self.fuori_app_fatta = dettaglio
            # l'istante da cui T14 giudica: SOLO per la chiusura INTERA (una
            # copertura parziale non e' un cash-out e il bot deve continuare)
            if ordine is not None and self.fuori_app == "intera":
                self.chiuso_dall_utente[self.event_id] = float(adesso)

        def _verifica_consapevolezza(self) -> None:
            """I controlli K su questo giro: righe del database contro ordini veri."""
            ordini = {ref: self.mercato._riga(ref, o)
                      for ref, o in self.mercato.ordini.items()}
            rifiutati = {str(r.get("ref") or "") for r in self.mercato.rifiutati}
            self.referto.violazioni.extend(CERT.verifica_consapevolezza(
                list(self.db.trades), ordini, rifiutati,
                self.referto.sollecitati, self.referto.sollecitati_per_strategia))

        def _certifica_ordini(self) -> None:
            """I controlli sugli ordini partiti in questo giro."""
            for tid, ref, meta, out, chiesta in self.ordini_del_giro:
                riga = self.db.get_trade(int(tid)) if tid is not None else None
                if riga is None:
                    continue
                if riga.get("closes_trade_id"):
                    padre = self.db.get_trade(int(riga["closes_trade_id"]))
                    if padre is not None:
                        riga = {**riga, "_padre": padre}
                apertura = not (meta.get("cashout") or meta.get("closes_trade_id")
                                or riga.get("closes_trade_id"))
                oss = CERT.Ordine(
                    strategia=str(riga.get("strategy") or ""), riga=riga, esito=out,
                    mode=self.mode, params=self.params,
                    stato_betfair=self.mercato.riga_ordine(ref),
                    apertura=bool(apertura), origine=str(riga.get("origin") or ""),
                    size_chiesta=float(chiesta or 0.0))
                self.ordini_osservati += 1
                self.referto.violazioni.extend(
                    CERT.verifica(oss, self.referto.sollecitati,
                                  self.referto.sollecitati_per_strategia))
            self.ordini_del_giro = []

        def _forse_richiedi(self, row: Dict[str, Any]) -> None:
            """Accoda una richiesta della UI, una sola volta per tipo."""
            if not self.richiesta_fatta:
                corpo = (richiesta_manuale_cs(row, self.params, self.mode)
                         if self.manuale_sul_bot
                         else richiesta_manuale(row, self.params, self.mode))
                if corpo is None:
                    return
                self.richiesta_fatta = True
                quante = 2 if self.doppia_lay else 1
                for n in range(quante):
                    corpo_n = dict(corpo)
                    if n:
                        # chiave diversa: l'idempotenza del manuale non la
                        # riconosce come la stessa richiesta, ed e' esattamente
                        # il doppio clic che la regola vieta
                        corpo_n["idempotency_key"] = str(corpo["idempotency_key"]) + f"-{n}"
                    self.db._req_id += 1
                    self.db.requests.append(
                        {"id": self.db._req_id, "kind": "place", "status": "pending",
                         "payload": corpo_n, "created_at": self.db._ora_iso(),
                         "result": None})
                    self.db.log("replay_richiesta_manuale",
                                {"kind": "place", "payload": corpo_n})
                return
            if self.manuale_sul_bot:
                return      # la riga del trader resta VIVA per tutta la partita
            aperte = [r for r in self.db.trades
                      if str(r.get("status")) == "open" and not r.get("closes_trade_id")]
            if not aperte:
                return
            self.giri_da_apertura += 1
            if self.cashout_chiesto or self.giri_da_apertura < GIRI_PRIMA_DEL_CASHOUT:
                return
            self.cashout_chiesto = True
            self.db._req_id += 1
            corpo = {"trade_id": int(aperte[0]["id"]), "fraction": 1.0}
            self.db.requests.append(
                {"id": self.db._req_id, "kind": "cashout", "status": "pending",
                 "payload": corpo, "created_at": self.db._ora_iso(), "result": None})
            self.db.log("replay_richiesta_manuale", {"kind": "cashout", "payload": corpo})

        def chiudi(self) -> CERT.Referto:
            return self.referto

    return SafeCert


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(int(ms) / 1000.0, tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# un evento
# ---------------------------------------------------------------------------
def certifica_evento(*a: Any, **kw: Any) -> CERT.Referto:
    """Guscio: accende la simulazione di flumine e la RIMETTE A POSTO alla fine
    (i flag di `flumine.config` sono di PROCESSO)."""
    with simulazione_flumine():
        return _certifica_evento(*a, **kw)


def _params_di_scenario(scenario: str, strategie: Tuple[str, ...],
                        mode: str) -> Dict[str, Any]:
    """I parametri GREZZI del control, come li scriverebbe la Control Room.

    Le tre strategie calcio si accendono ESPLICITAMENTE: `variants` dice CHI
    apre, `strategy_modes` dice CON CHE SOLDI. Nessuna delle due si eredita —
    «i soldi veri si raggiungono solo scrivendolo» (`modalita_di_strategia`).
    """
    par: Dict[str, Any] = {
        "variants": list(strategie),
        "strategy_modes": {s: mode for s in strategie},
        # cadenza vera del servizio
        "poll_interval_s": 2,
        # il gate flumine resta chiuso (nessun runner): percorso REST, che nel
        # banco e' servito da `MercatoSafe`. Lo si dichiara invece di subirlo.
        "execution_mode": "rest",
    }
    par.update(SCENARI.get(scenario, {}))
    return par


def _certifica_evento(event_id: str, *, data_dir: str,
                      params_grezzi: Optional[Dict[str, Any]] = None,
                      strategie: Tuple[str, ...] = STRATEGIE,
                      ogni_ms: int = 2000,
                      invecchia_s: float = 0.0,
                      guasti: int = 0,
                      rifiuti: int = 0,
                      timeout_accettato: bool = False,
                      riavvia: bool = False,
                      ordine_manuale: bool = False,
                      doppia_lay: bool = False,
                      manuale_sul_bot: bool = False,
                      cashout_globale: bool = False,
                      fuori_app: Optional[str] = None,
                      mode: str = "live",
                      status: str = "running",
                      scenario: str = "base") -> CERT.Referto:
    """Fa rivivere a Safe calcio una partita registrata e ritorna il referto."""
    from flumine import FlumineSimulation

    # OGNI REPLAY PARTE DA UN PROCESSO PULITO. Con la pool (`--worker N`) piu'
    # coppie evento x scenario girano nello STESSO processo figlio, una dopo
    # l'altra: senza questo azzeramento il secondo replay eredita i throttle del
    # primo (e la partita e' la stessa, quindi le chiavi coincidono) e certifica
    # una cosa diversa da quella che certifica da solo. E' il punto 37 del
    # catalogo §7. Si azzera all'INIZIO, non solo alla fine: un replay che
    # esplode a meta' lascerebbe le cache sporche al successivo.
    _pulisci_cache_di_processo()

    raw = os.path.join(data_dir, str(event_id), f"{event_id}.raw.jsonl")
    ref = CERT.Referto(event_id=str(event_id))
    if not os.path.exists(raw):
        ref.note.append(f"registrazione assente: {raw}")
        return ref

    try:
        punteggi = carica_punteggi(data_dir, str(event_id), "calcio")
    except Exception as ex:  # noqa: BLE001
        punteggi = []
        ref.note.append(f"punteggi non letti ({type(ex).__name__}): minuti e gol assenti")

    banco = ScannerReplay(sport="calcio", pre_ko_ou_hours=0.0)
    banco.dichiara_nomi(*nomi_dal_punteggio(punteggi))

    Strategia = _crea_strategia()
    strategia = Strategia(
        event_id=str(event_id),
        params_grezzi=params_grezzi or _params_di_scenario(scenario, strategie, mode),
        banco=banco, punteggi=punteggi, ogni_ms=ogni_ms,
        invecchia_s=invecchia_s, riavvia=riavvia, mode=mode, status=status,
        ordine_manuale=ordine_manuale, doppia_lay=doppia_lay,
        manuale_sul_bot=manuale_sul_bot, cashout_globale=cashout_globale,
        timeout_accettato=timeout_accettato, fuori_app=fuori_app,
        market_filter={"markets": [raw]},
        # I TETTI DI FLUMINE VANNO APERTI: il rischio lo governa la Safe coi suoi
        # parametri (`max_liability_per_trade`, `max_open_trades`, i cap di
        # `risk`), ed e' quello che si vuole misurare.
        max_order_exposure=1e9, max_selection_exposure=1e9,
        max_trade_count=int(1e9), max_live_trade_count=int(1e9))
    if guasti > 0:
        strategia.mercato.guasti["place_exception"] = int(guasti)
    if rifiuti > 0:
        # i primi N piazzamenti tornano `ok=False`: e' il RIFIUTO dichiarato di
        # Betfair (risposta ricevuta, nessun ordine a mercato), non un errore di
        # rete (quello e' `place_exception`).
        strategia.mercato.guasti["place_rifiuto"] = int(rifiuti)
        # SUL LATO LAY: e' con la lay che le tre strategie della SPEC APRONO, ed
        # e' il ramo in cui il 15/09 `res.ok` non veniva letto.
        strategia.mercato.rifiuta_lato = "lay"

    # ---------------------------------------------------------------- i ganci
    # I controlli si agganciano alle funzioni VERE: cosi' si vede ogni
    # valutazione, ogni ordine e ogni uscita con i dati che il bot ha davvero.
    ref_vivo = strategia.referto
    valuta_vero = E.evaluate_football_all
    decide_vero = XE.decide
    place_vero = X.place

    def valuta_sorvegliata(ctx, params):
        evs = valuta_vero(ctx, params)
        # il PRIMO riferimento 1X2 visto in gioco: da li' in poi non deve piu'
        # cambiare (controllo B11, difetto 19 del catalogo)
        if (ctx.inplay and ctx.pre_match is not None
                and strategia.pre_ko_congelato is None):
            strategia.pre_ko_congelato = dict(ctx.pre_match)
        for ev in evs:
            nome = str(ev.variant)
            if nome not in STRATEGIE:
                continue
            oss = CERT.Valutazione(
                strategia=nome, ctx=ctx, ev=ev, par=dict(params.get(nome) or {}),
                params=params, pre_ko_congelato=strategia.pre_ko_congelato)
            CERT.osserva_valutazione(ref_vivo, oss)
            ref_vivo.violazioni.extend(
                CERT.verifica(oss, ref_vivo.sollecitati,
                              ref_vivo.sollecitati_per_strategia))
            # il MOTIVO, scritto: «scartata per X» e' una prova, il silenzio no
            if ev.state != "signal":
                cadute = [c.id for c in ev.checks if c.ok is not True]
                motivo = f"{nome}: {ev.state} ({','.join(cadute[:4]) or '-'})"
            else:
                motivo = f"{nome}: SEGNALE {ev.headline}"
            ref_vivo.motivi[motivo] = ref_vivo.motivi.get(motivo, 0) + 1
            # le varianti spente: il servizio deve DIRLO (controllo T10)
            if ev.state == "signal" and nome not in (
                    strategia.params.get("variants") or []):
                strategia.segnali_di_variante_spenta += 1
        return evs

    def decide_sorvegliata(trade, payload, meta, now_ts, params):
        d = decide_vero(trade, payload, meta, now_ts, params)
        tr = (meta or {}).get(XE.TRACK_KEY)
        nome = str(trade.get("strategy") or "")
        if isinstance(tr, dict) and nome in STRATEGIE:
            strategia.uscite_osservate += 1
            oss = CERT.Uscita(strategia=nome, trade=dict(trade), tr=dict(tr),
                              decisione=d, par=dict(params or {}), now_ts=now_ts)
            ref_vivo.violazioni.extend(
                CERT.verifica(oss, ref_vivo.sollecitati,
                              ref_vivo.sollecitati_per_strategia))
        return d

    def place_sorvegliata(**kw):
        """Registra l'ordine; il GIUDIZIO arriva a fine giro (vedi
        `_certifica_ordini`): qui la riga porta ancora i numeri della riserva."""
        out = place_vero(**kw)
        meta = dict(kw.get("meta") or {})
        apertura = not (meta.get("cashout") or meta.get("closes_trade_id"))
        if apertura and str(getattr(out, "status", "")) != "error":
            strategia.aperture_nel_giro += 1
        strategia.ordini_del_giro.append(
            (kw.get("trade_id"), str(kw.get("client_ref") or "")[:32], meta, out,
             float(kw.get("size") or 0.0)))
        return out

    quadro = FlumineSimulation(client=cliente_simulato())
    assicura_middleware_simulato(quadro)
    quadro.add_strategy(strategia)

    def _scanner_durante_attesa(mb: Any) -> None:
        # il bot e' bloccato sulla REST mentre Betfair trattiene l'ordine; lo
        # SCANNER no: in produzione e' un altro processo e continua a ricevere.
        pt = getattr(mb, "publish_time", None)
        if pt is not None:
            banco.imposta_ora(pt.timestamp())
        if banco.registra_mercato(mb):
            banco.applica_book(mb)
        strategia.mercato.registra_definizione(mb)

    motore = MotoreReplay(quadro, su_book=_scanner_durante_attesa)
    strategia.mercato.motore = motore

    # I NOMI DEL CORRECT SCORE: lo stream non li ha, e senza di loro la variante
    # ESATTO non vede un prezzo. Si dichiarano al banco PRIMA di partire,
    # leggendoli dalle definizioni della registrazione.
    _dichiara_nomi_cs(banco, raw)

    E.evaluate_football_all = valuta_sorvegliata          # type: ignore[assignment]
    XE.decide = decide_sorvegliata                        # type: ignore[assignment]
    X.place = place_sorvegliata                           # type: ignore[assignment]
    try:
        with freni_live(mode == "live"):
            motore.esegui(strategia)
    finally:
        E.evaluate_football_all = valuta_vero             # type: ignore[assignment]
        XE.decide = decide_vero                           # type: ignore[assignment]
        X.place = place_vero                              # type: ignore[assignment]
        _pulisci_cache_di_processo()

    out = strategia.chiudi()
    _componi_note(out, strategia, banco, motore, scenario, mode, status)
    return out


def _dichiara_nomi_cs(banco: ScannerReplay, raw: str) -> None:
    """Riempie `banco.nomi_extra` per CORRECT_SCORE e HALF_TIME_SCORE.

    Si legge SOLO la prima definizione di ogni mercato punteggio (una passata
    corta sul file, si esce appena li si e' visti entrambi): i nomi sono
    invarianti per tutta la partita.
    """
    import json

    voluti = {"CORRECT_SCORE", "HALF_TIME_SCORE"}
    visti: set = set()
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
                    mt = str(md.get("marketType") or "").upper()
                    if mt not in voluti or mt in visti:
                        continue
                    visti.add(mt)
                    mid = str(mc.get("id") or "")
                    banco.nomi_extra[mid] = {
                        int(r["id"]): VO.selection_name(mt, int(r["id"]),
                                                        int(r.get("sortPriority") or 0),
                                                        "", "")
                        for r in (md.get("runners") or []) if r.get("id") is not None}
                if visti >= voluti:
                    return
    except OSError as ex:  # noqa: BLE001 - senza nomi l'ESATTO resta muta, e si dice
        logger.warning("[safe.replay] nomi Correct Score non letti: %s", ex)


def _pulisci_cache_di_processo() -> None:
    """Le cache di modulo di `bot_service` sono di PROCESSO: lasciarle sporche
    farebbe mentire il replay successivo nello stesso interprete (e la suite,
    che li esegue tutti dentro lo stesso `pytest`)."""
    _riavvia_processo()


def _componi_note(out: CERT.Referto, strategia: Any, banco: ScannerReplay,
                  motore: MotoreReplay, scenario: str, mode: str,
                  status: str) -> None:
    """Il referto §6.8: che cosa e' successo, e che cosa NON e' stato provato."""
    from collections import Counter

    db = strategia.db
    out.ordini_piazzati = len(strategia.mercato.ordini)
    out.righe_scritte = len(db.trades)
    out.note.append(f"scenario={scenario} | modalita' servizio={mode} | "
                    f"status={status} | strategie accese="
                    f"{','.join(strategia.params.get('variants') or [])} | "
                    f"strategy_modes={strategia.params.get('strategy_modes')}")
    out.note.append(f"giri di run_once: {strategia.giri} | ordini reali su flumine: "
                    f"{out.ordini_piazzati} | righe safe_strategy_trades: "
                    f"{out.righe_scritte} | place osservati: "
                    f"{strategia.ordini_osservati} | uscite valutate: "
                    f"{strategia.uscite_osservate}")
    # LE TRE STRATEGIE, una per una: valutata quante volte, con che esito
    for s in STRATEGIE:
        n = int(out.valutazioni.get(s, 0))
        stati = out.stati_valutazione.get(s, {})
        scarti = sorted((out.scarti.get(s) or {}).items(), key=lambda x: -x[1])[:6]
        if not n:
            out.note.append(f"[{s.upper()}] MAI VALUTATA: e' un reperto, non un "
                            f"silenzio — o il dato non c'era o il percorso non "
                            f"la raggiunge")
            continue
        out.note.append(
            f"[{s.upper()}] valutata {n} volte | stati {dict(stati)} | "
            f"segnali {out.segnali.get(s, 0)} | scartata per: "
            + (", ".join(f"{k} x{v}" for k, v in scarti) or "-"))
    kinds = Counter(db.kinds())
    out.note.append("attivita' del servizio: "
                    + (", ".join(f"{k} x{n}" for k, n in kinds.most_common(10)) or "-"))
    stati_righe = Counter(str(r.get("status")) for r in db.trades)
    out.note.append(f"righe per stato: {dict(stati_righe)}")
    motivi_scarto = Counter(
        str((p or {}).get("reason") or "")[:50]
        for k, p, _e in db.attivita if k in ("skip", "error", "place_rifiutato"))
    if motivi_scarto:
        out.note.append("scarti dichiarati dal servizio: "
                        + " | ".join(f"{m} x{n}" for m, n in motivi_scarto.most_common(6)))
    # OGNI RIGA, CAMPO PER CAMPO (PROCESSO §6.5 e parita' paper/live di §C.5):
    # e' quello che il trader vede in pagina, ed e' il termine di paragone fra
    # il percorso live e quello paper sullo stesso ordine.
    for r in db.trades:
        es = (r.get("meta") or {}).get("esecuzione") or {}
        out.note.append(
            f"[RIGA {r.get('id')}] {r.get('strategy')}/{r.get('origin')} "
            f"{r.get('side')} sel={r.get('selection_id')} mkt={r.get('market_id')} "
            f"stato={r.get('status')} mode={r.get('mode')} "
            f"chiesto={es.get('size_richiesta')} abbinato={es.get('size_abbinata')} "
            f"residuo={es.get('size_residua')} prezzo_chiesto={es.get('price_richiesto')} "
            f"prezzo_medio={es.get('price_medio')} scorrimento={es.get('scorrimento_tick')} "
            f"percorso={es.get('percorso')} bet_id={r.get('bet_id')} "
            f"chiude={r.get('closes_trade_id')} liability={r.get('liability')} "
            f"pnl={r.get('pnl')}")
    fill = strategia.mercato.riepilogo_fill()
    aliquota = float(strategia.params.get("commission_pct", 5.0)) / 100.0
    conto = strategia.mercato.pnl(aliquota)
    out.note.append(f"fill: {fill['fill']} abbinamenti su {fill['ordini_con_fill']} "
                    f"ordini per {fill['abbinato']} EUR (prezzi {fill['prezzi']})")
    out.note.append(f"P&L del replay: lordo {conto['lordo']:+.2f} | commissione "
                    f"{conto['commissione']:.2f} ({conto['aliquota'] * 100:.1f}%) | "
                    f"NETTO {conto['netto']:+.2f} EUR (non e' il metro: il metro "
                    f"e' la condotta)")
    out.note.append(f"bet delay: {motore.pompati} book passati durante le attese | "
                    f"book in ritardo: {motore.book_in_ritardo} | LAPSE al fischio: "
                    f"{motore.lapse_al_fischio}")
    out.note.append(f"righe di scan scritte dallo SCANNER VERO: {banco.righe_scritte}"
                    + (f" | giri senza riga nel feed: {strategia.righe_assenti}"
                       if strategia.righe_assenti else ""))
    # i tetti: a 0 sono SPENTI, e va detto (controllo T7)
    rischio = strategia.params.get("risk") or {}
    spenti = [k for k in ("daily_liability_cap", "per_event_liability_cap",
                          "per_event_max_trades", "model_daily_cap")
              if not float(rischio.get(k) or 0.0)]
    out.note.append(f"tetti di rischio SPENTI (valore 0): {spenti or '-'} | "
                    f"daily_loss_stop={rischio.get('daily_loss_stop')} | "
                    f"max_liability_per_trade="
                    f"{strategia.params.get('max_liability_per_trade')} | "
                    f"max_open_trades={strategia.params.get('max_open_trades')}")
    if db.mancanti:
        out.note.append("metodi di database chiamati dal servizio e ASSENTI dal "
                        f"banco: {sorted(db.mancanti)}")
    if db.senza_dato:
        out.note.append("[NON ESERCITABILE] dati di produzione assenti dalla "
                        "registrazione: "
                        + " | ".join(f"{n}: {c}" for n, c in db.senza_dato))
    if strategia.mercato.rifiutati:
        out.note.append(f"ordini rifiutati dal mercato: "
                        f"{len(strategia.mercato.rifiutati)} "
                        f"(es. {strategia.mercato.rifiutati[0].get('err')})")
    if strategia.riavvio_fatto is not None:
        out.note.append("RIAVVIO a meta' partita: azzerate le cache di processo "
                        + ", ".join(strategia.riavvio_fatto[:8]))
    elif strategia.riavvia:
        out.note.append("scenario riavvio: nessuna posizione aperta da ritrovare, "
                        "il riavvio non e' mai scattato")
    out.note.append("[NON ESERCITABILE] minimo di giurisdizione .it e "
                    "place-and-trim: flumine non ha un minimo, quindi "
                    "`place_submin_live` piazza diretto (controllo T11)")
    out.note.append("[FUORI PERIMETRO C.3] opportunita' a modello, combo e "
                    "anomalie: altro motore, non le tre strategie della SPEC "
                    "(controllo T5)")
    if strategia.ordine_manuale:
        out.note.append(
            "[SCENARIO] ordine MANUALE dalla UI: la richiesta e' passata da "
            "`safe_strategy_requests` -> `process_requests` -> `_request_place`, "
            "cioe' dal percorso di produzione del bottone «Investi». Serve a far "
            "esistere un ordine VERO su flumine su una partita in cui nessuna "
            "delle tre strategie entra: certifica il CICLO DI VITA dell'ordine "
            "(§6.4), NON le regole d'ingresso della SPEC. La riga nasce "
            "`strategy='manual'`, quindi le uscite di base/esatto/punta NON si "
            "applicano (`_MANUAL_STRATEGIES`). richiesta accodata="
            f"{strategia.richiesta_fatta} | cash out chiesto="
            f"{strategia.cashout_chiesto}")
    manuali = [r for r in db.trades if str(r.get("origin")) == "manual"]
    if manuali:
        resp = sum(float(r.get("liability") or 0.0) for r in manuali)
        out.note.append(
            f"[CHIUSO IL 16/09] {len(manuali)} righe manuali vive per {resp:.2f} "
            f"EUR di responsabilita': i CAP del bot adesso contano SOLO "
            f"l'automatico (consegna S1 del 16/09 sera). Il reperto di ieri "
            f"(`open_trades`/`aggregate_rows` senza filtro `origin`, con le "
            f"righe del trader dentro `build_risk_ctx`) non vale piu'; restano "
            f"nei TOTALI DI PAGINA, che e' il comportamento voluto. Le uscite "
            f"le filtravano gia' (`_exit_candidates`: `origin != 'auto'` -> "
            f"scartata): il bot non tocca le righe del trader.")
    if strategia.chiuso_dall_utente:
        out.note.append(
            "[CHIUSO IL 16/09] l'utente ha chiuso a mano tutte le operazioni "
            "della partita. Safe ADESSO ce l'ha, il cash-out globale: kind "
            "`cashout_event` in `process_requests`, marcatore "
            "`meta.chiuso_dall_utente` sulle righe (sopravvive al riavvio) e "
            "`riprendi_evento` per tornare indietro (consegna S1 del 16/09 "
            "sera). Il reperto di ieri — nessuno stato per evento, quindi il "
            "bot poteva riaprire al cambiare del punteggio — non vale piu': "
            "qui si verifica che dal giro dopo non apra, non copra e non esca "
            "(controllo T14).")
    if getattr(strategia, "timeout_fatto", None):
        out.note.append(
            "[SCENARIO] TIMEOUT della REST dopo l'accettazione di Betfair sulla riga "
            f"#{strategia.timeout_fatto.get('trade_id')} (bet "
            f"{strategia.timeout_fatto.get('bet_id')}): la riga e' tornata in "
            "riconciliazione senza bet_id e l'ordine vero e' rimasto a mercato. "
            "Si ritrova SOLO col ref con cui e' stato chiesto (difetto 4 del 15/09, "
            "controlli K3/K7)")
    if strategia.mercato.rifiutati:
        out.note.append(
            f"[SCENARIO] ordini RIFIUTATI da Betfair: {len(strategia.mercato.rifiutati)} "
            f"(es. {strategia.mercato.rifiutati[0].get('err')}) - e' la condizione che "
            f"mette alla prova il difetto 2 del 15/09 (`res.ok` mai letto), K2")
    if scenario == SCENARIO_PAPER:
        out.note.append("[DIVERGENZA, REPERTO] percorso PAPER legacy: il fill lo "
                        "fa `bot_service._paper_ladder` + `omega_engine.paper_fill` "
                        "sul book del FEED, NON il matching di flumine: niente "
                        "coda `_piq`, niente bet delay, niente volume scambiato. "
                        "Decisione 3 dell'utente (16/09): il paper deve passare "
                        "dal client simulato. Qui si MISURA, non si corregge.")
    out.note.extend(CERT.tabella_per_strategia(out))


# ---------------------------------------------------------------------------
# GLI SCENARI E IL COMANDO
# ---------------------------------------------------------------------------
def cadenza_ms(params: Dict[str, Any]) -> int:
    """OGNI QUANTO GIRA SAFE, letto dai SUOI parametri di produzione.

    `bot_service.main` dorme `poll_interval_s` fra un `run_once` e l'altro
    (default 2 s). Cablare qui un numero farebbe vedere al bot piu' (o meno)
    di quello che vedrebbe.
    """
    return int(max(1.0, float(params.get("poll_interval_s") or 2.0)) * 1000)


def certifica_scenario(event_id: str, *, data_dir: str, scenario: str = "base",
                       ogni_ms: int = 0, campioni_diff: int = 0,
                       strategie: Optional[Tuple[str, ...]] = None) -> CERT.Referto:
    """ADATTATORE PER IL BANCO — dal NOME dello scenario ai parametri di Safe.

    E' la funzione che il REGISTRO dei bot
    (`Betfair/stream/backtest/registro_bot.py`) chiama: firma identica per tutti
    i bot, cosi' il comando `python -m Betfair.stream.backtest.certifica <bot>`
    resta uno solo.
    """
    scelte = tuple(strategie or STRATEGIE_SCELTE)
    mode = "paper" if scenario == SCENARIO_PAPER else "live"
    status = "stopped" if scenario == SCENARIO_BOT_FERMO else "running"
    par = _params_di_scenario(scenario, scelte, mode)
    risolti = BS.resolve_params(par, engine_mod=E)
    # il feed STANTIO si ottiene invecchiando la riga E lo scanner, non toccando
    # i prezzi: devono essere vecchi TUTTI E DUE (`exits.feed_is_fresh`).
    vecchio = (float(XE.FEED_HARD_MAX_S) * 2.0
               if scenario == SCENARIO_FEED_STANTIO else 0.0)
    return certifica_evento(
        event_id, data_dir=data_dir, params_grezzi=par, strategie=scelte,
        ogni_ms=int(ogni_ms) or cadenza_ms(risolti),
        invecchia_s=vecchio,
        guasti=(QUANTI_GUASTI if scenario == SCENARIO_ESITI_IGNOTI else 0),
        rifiuti=(QUANTI_RIFIUTI if scenario == SCENARIO_RIFIUTI else 0),
        timeout_accettato=(scenario == SCENARIO_TIMEOUT_ACCETTATO),
        riavvia=(scenario == SCENARIO_RIAVVIO),
        ordine_manuale=(scenario in SCENARI_CON_ORDINE_MANUALE),
        doppia_lay=(scenario == SCENARIO_DUE_LAY),
        manuale_sul_bot=(scenario == SCENARIO_MANUALE_E_BOT),
        cashout_globale=(scenario == SCENARIO_CASHOUT_GLOBALE),
        fuori_app=("intera" if scenario == SCENARIO_FUORI_APP else
                   ("ridotta" if scenario == SCENARIO_FUORI_APP_RIDOTTA else None)),
        mode=mode, status=status, scenario=scenario)


def main(argv: Optional[List[str]] = None) -> int:
    """CHIAMANTE SOTTILE del punto d'ingresso unico.

    Il referto, la copertura dei controlli, il diario e il filtro delle
    registrazioni COMPLETE vivono in `Betfair/stream/backtest/certifica.py` e
    valgono per TUTTI i bot: qui non se ne tiene una seconda copia.
    """
    argomenti = list(argv if argv is not None else sys.argv[1:])
    # `--strategie base,esatto` restringe le tre varianti: e' un'opzione di
    # QUESTO bot, quindi si consuma qui e non si sporca il comando comune.
    scelte: Optional[str] = None
    ripuliti: List[str] = []
    i = 0
    while i < len(argomenti):
        a = argomenti[i]
        if a == "--strategie" and i + 1 < len(argomenti):
            scelte = argomenti[i + 1]
            i += 2
            continue
        if a.startswith("--strategie="):
            scelte = a.split("=", 1)[1]
            i += 1
            continue
        ripuliti.append(a)
        i += 1
    if scelte:
        global STRATEGIE_SCELTE
        STRATEGIE_SCELTE = tuple(s.strip() for s in scelte.split(",") if s.strip())
    from ...stream.backtest.certifica import main as certifica_main

    # IL REGISTRO HA TRE VOCI PER IL CALCIO (`safe_base`, `safe_esatto`,
    # `safe_punta`), non una `safe_calcio`: fino al 16/09 questo chiamante
    # passava un nome che il registro rifiuta, e il comando non partiva.
    # La voce si sceglie dalle strategie chieste; con piu' di una si usa
    # `safe_base`, che accende comunque tutte e tre (il registro passa
    # `strategie` al replay).
    voci = {"base": "safe_base", "esatto": "safe_esatto", "punta": "safe_punta"}
    bot = (voci.get(STRATEGIE_SCELTE[0], "safe_base")
           if len(STRATEGIE_SCELTE) == 1 else "safe_base")
    return certifica_main([bot] + ripuliti)


# le strategie scelte dalla riga di comando (default: tutte e tre)
STRATEGIE_SCELTE: Tuple[str, ...] = STRATEGIE


if __name__ == "__main__":
    sys.exit(main())
