"""OMEGA SULLE REGISTRAZIONI VERE — il replay col motore ufficiale Betfair.

CHE COSA FA, in una riga: fa rivivere a Omega una partita registrata, alla
cadenza vera del suo servizio, coi prezzi veri di Betfair, e a ogni decisione
controlla le regole della Costituzione (`certificazione.py`). Non misura il
profitto: misura la CONDOTTA.

LA CATENA E' QUELLA DI PRODUZIONE, passo per passo (banco comune,
`Betfair/stream/backtest/banco_comune.py`):

    _live_raw/<id>/<id>.raw.jsonl        stream NATIVO Betfair registrato
      -> flumine                          FlumineSimulation + HistoricalStream
      -> SCANNER VERO                     safe_strategy.service.Scanner
      -> build_rows VERA                  la riga `safe_strategy_scan`
      -> FEED VERO DI OMEGA               scan_feed.ScanRowCache -> _feed_row
      -> SERVIZIO VERO                    omega_service.run_once (il giro INTERO)
      -> ORDINI VERI                      market.place_order su flumine, con la
                                          coda (_piq), il FOK e il bet delay

TRE AGGANCI, e perche' sono necessari (dichiarati, non nascosti):

 1. `omega_service._real_market`. Omega legge il feed unico SOLO quando
    `market is _real_market` (`omega_service.py:458,469,491,500,513,522`): con un
    market qualunque il servizio ripiega su `score_lookup`/REST, cioe' su un
    percorso che in produzione non fa. Per esercitare il percorso VERO il replay
    mette il proprio mercato in quella variabile di modulo per la durata del
    giro, e lo rimette a posto alla fine. Il mercato del replay espone anche
    `CorrectScoreMarket`/`MarketSnapshot`/`EventInfo`, che il servizio costruisce
    da li' (`omega_service.py:400,406,2605`).

 2. `scan_feed._SHARED_CACHE`. La riga del feed la legge `ScanRowCache`, che e'
    la classe VERA con `fetch` iniettabile (`scan_feed.py:97-115`): qui il
    `fetch` risponde con la riga che lo SCANNER VERO ha appena scritto nella
    tabella in memoria del banco. Nessuna riga costruita a mano.
    L'`updated_at` viene RIBASATO sull'orologio del PC conservando l'ETA' esatta:
    `fresh_payload` e `row_age_sec` (funzioni vere, non toccate) confrontano con
    `time.time()`, e una registrazione di giugno risulterebbe vecchia di mesi —
    cioe' il bot non vedrebbe MAI il feed. Ribasare l'istante lasciando l'eta'
    e' l'unico modo di far girare la regola di freschezza VERA sui dati veri.

 3. `omega_service._mono`. E' l'orologio delle cache del respiro (§18), ed e'
    dichiarato "sostituibile nei test" (`omega_service.py:214`). Nel replay e'
    il TEMPO DI MERCATO: con l'orologio del PC il replay comprime due ore in
    dieci minuti e `feed_cache_s` (2 s) coprirebbe decine di secondi di partita.

I NOMI DELLE SCORELINE. Il raw dello stream porta `id` + `sortPriority`, non i
nomi dei runner (il catalogo REST qui non c'e': LIMITE 1 del banco). Per Omega,
che banca un RISULTATO ESATTO, il nome E' la strategia. I `selectionId` di
CORRECT_SCORE e HALF_TIME_SCORE sono pero' GLOBALI Betfair e seguono una
enumerazione a GUSCI (vedi `nome_scoreline`), VERIFICATA su questa stessa
registrazione: a ogni gol i runner diventati impossibili smettono di avere
prezzi, e i blocchi che si spengono sono esattamente quelli che la formula
predice (35760084: a 1-0 muoiono {1,4,9,16} = tutti i "0-x"; a 2-0 {2,3,8,15} =
i "1-x"; a 3-0 {5,6,7,14} = i "2-x"). Il test
`test_omega_replay_2026_09_16.py` rifa' quella verifica.

CHE COSA IL REPLAY **NON** FA (limiti dichiarati, oltre a quelli del banco):
 * il minimo di giurisdizione .it e il place-and-trim non esistono su flumine:
   `place_submin_live` piazza diretto (LIMITE 3 del banco);
 * la coda `betfair_live_order_requests` del runner flumine non c'e': il gate
   (`_flumine_gate`) trova l'heartbeat del runner assente e ripiega sul percorso
   REST — che e' esattamente il percorso in cui gli ordini VERI di Omega nascono
   quando il runner e' giu'. E' il percorso che qui si certifica;
 * in PAPER Omega usa `omega_engine.paper_fill`, cioe' un fill ISTANTANEO su
   snapshot senza bet delay: lo scenario `paper` lo esercita e il referto
   MISURA la divergenza col percorso live su flumine (decisione 3 dell'utente,
   16/09: il paper deve passare da flumine — non e' ancora cosi').

Uso:
    python -m Betfair.omega.tools.replay_registrazioni 35760084
    python -m Betfair.omega.tools.replay_registrazioni 35760084 --scenari tutti
    python -m Betfair.stream.backtest.certifica omega 35760084 --diario d.txt

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import json
import logging
import math
import os
import sys
import time
from bisect import bisect_right
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .. import certificazione as CERT
from .. import omega_config
from .. import omega_engine as E
from .. import omega_market as OM
from .. import omega_service as S
from ...stream.backtest.banco_comune import (
    DbMemoria, MercatoFlumine, MotoreReplay, ScannerReplay,
    assicura_middleware_simulato, carica_punteggi, cliente_simulato,
    nomi_dal_punteggio, simulazione_flumine,
)
from ...stream.scores import scan_feed as SF

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# I NOMI DELLE SCORELINE — la formula, e perche' e' quella
# ---------------------------------------------------------------------------
# Betfair enumera i risultati esatti a GUSCI concentrici: il guscio k contiene
# tutti i punteggi con max(casa, ospiti) == k, e parte dall'id k*k+1:
#
#     k=0 -> 1 = 0-0
#     k=1 -> 2 = 1-0, 3 = 1-1, 4 = 0-1
#     k=2 -> 5 = 2-0, 6 = 2-1, 7 = 2-2, 8 = 1-2, 9 = 0-2
#     k=3 -> 10 = 3-0, 11 = 3-1, 12 = 3-2, 13 = 3-3, 14 = 2-3, 15 = 1-3, 16 = 0-3
#
# cioe': prima si scende sulla colonna casa=k (ospiti 0..k), poi si risale sulla
# riga ospiti=k (casa k-1..0). Gli id sono GLOBALI: valgono per CORRECT_SCORE e
# per HALF_TIME_SCORE (che usa lo stesso spazio, fermandosi al guscio 2).
# VERIFICATO sulle registrazioni: vedi la testa del modulo e il test.
_ALTRI = {
    9063254: "Any Unquoted Home",
    9063255: "Any Unquoted Draw",
    9063256: "Any Unquoted Away",
    4506345: "Any Other Half Time Score",
}
GUSCI_MAX = 12          # fino a 12-12: ben oltre qualunque mercato Betfair


def nome_scoreline(selection_id: int) -> Optional[str]:
    """Il nome Betfair del runner a punteggio esatto, dal suo `selectionId`.

    Ritorna ``None`` per gli id che NON sono una scoreline (gli "Any Unquoted"
    li traduce `nome_runner_punteggio`, che e' quello che il catalogo darebbe).
    """
    sid = int(selection_id)
    if sid < 1:
        return None
    k = int(math.isqrt(sid - 1))        # guscio
    if k > GUSCI_MAX:
        return None
    pos = sid - (k * k + 1)             # 0..2k dentro il guscio
    if pos <= k:
        casa, ospiti = k, pos
    else:
        casa, ospiti = 2 * k - pos, k
    if casa < 0:
        return None
    return f"{casa} - {ospiti}"


def nome_runner_punteggio(selection_id: int) -> str:
    """Il nome come lo darebbe `listMarketCatalogue` (scoreline o aggregato)."""
    if int(selection_id) in _ALTRI:
        return _ALTRI[int(selection_id)]
    nome = nome_scoreline(selection_id)
    return nome if nome is not None else f"sel {selection_id}"


# ---------------------------------------------------------------------------
# IL CATALOGO CHE IL RAW NON HA — una passata sul file, prima del replay
# ---------------------------------------------------------------------------
class Catalogo:
    """Cio' che in produzione arriva da `listMarketCatalogue` e dal book REST.

    Tutto viene dalla REGISTRAZIONE, niente e' inventato:
      * `nomi` — {market_id: {selection_id: nome}} per CORRECT_SCORE e
        HALF_TIME_SCORE (formula dei gusci, verificata sui dati);
      * `definizioni` — per ogni mercato la sequenza dei `marketDefinition`
        (publish time, stato, in-play, stato di ogni runner): e' cio' che
        permette al settlement di vedere il mercato CHIUSO col suo WINNER, che
        flumine in simulazione non consegna mai alla strategia;
      * `avvio` — il `marketTime` del MATCH_ODDS (il kickoff).
    """

    def __init__(self) -> None:
        self.nomi: Dict[str, Dict[int, str]] = {}
        self.definizioni: Dict[str, List[Tuple[int, str, bool, Dict[int, str]]]] = {}
        self.tipi: Dict[str, str] = {}
        self.avvio: Optional[datetime] = None
        self.event_id: Optional[str] = None


def leggi_catalogo(raw: str) -> Catalogo:
    """Una passata sul raw per i `marketDefinition` (i soli che servono)."""
    cat = Catalogo()
    ultimo: Dict[str, Tuple[str, bool, Dict[int, str]]] = {}
    with open(raw, "r", encoding="utf-8") as fh:
        for riga in fh:
            if '"marketDefinition"' not in riga:
                continue
            try:
                dati = json.loads(riga)
            except ValueError:
                continue
            pt = int(dati.get("pt") or 0)
            for mc in dati.get("mc") or []:
                md = mc.get("marketDefinition")
                if not md:
                    continue
                mid = str(mc.get("id") or "")
                if not mid:
                    continue
                mtype = str(md.get("marketType") or "").upper()
                cat.tipi[mid] = mtype
                if cat.event_id is None and md.get("eventId"):
                    cat.event_id = str(md["eventId"])
                if mtype == "MATCH_ODDS" and cat.avvio is None:
                    cat.avvio = _iso_dt(md.get("marketTime") or md.get("openDate"))
                runners = md.get("runners") or []
                if mtype in ("CORRECT_SCORE", "HALF_TIME_SCORE") and mid not in cat.nomi:
                    cat.nomi[mid] = {int(r["id"]): nome_runner_punteggio(int(r["id"]))
                                     for r in runners if r.get("id") is not None}
                stato = str(md.get("status") or "OPEN").upper()
                inplay = bool(md.get("inPlay"))
                sr = {int(r["id"]): str(r.get("status") or "ACTIVE")
                      for r in runners if r.get("id") is not None}
                firma = (stato, inplay, sr)
                if ultimo.get(mid) != firma:
                    ultimo[mid] = firma
                    cat.definizioni.setdefault(mid, []).append((pt, stato, inplay, sr))
    return cat


def _iso_dt(v: Any) -> Optional[datetime]:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# IL DATABASE DI OMEGA, IN MEMORIA
# ---------------------------------------------------------------------------
class DbMemoriaOmega(DbMemoria):
    """Le tabelle `omega_*` in RAM, con le FIRME e i TIPI di ritorno di
    `Betfair/omega/omega_db.py`, funzione per funzione.

    Un doppio che risponde a domande a cui il vero non risponde e' la causa di
    tutti i difetti del 15/09: qui `insert_trade` torna l'ID (`Optional[int]`),
    `ht_ft_transitions` torna `[]` per "tabella vuota" e `None` per "errore",
    `aggregates` passa da `omega_engine.aggregate_trades` (la stessa funzione
    PURA del fallback di produzione), e gli INDICI UNICI delle migrazioni
    (`uq_omega_trades_auto_leg`, `uq_omega_trades_leg`,
    `migrations/omega_models_v5.sql:222-236`) esistono davvero: il pattern
    RESERVE-FIRST di Omega (I1) si regge su di loro, e un banco senza unique
    dichiarerebbe sano un bot che raddoppia il lay.

    Cio' che NON c'e' — e che il referto dichiara, mai tace:
      * la coda flumine del runner (`betfair_live_order_requests`,
        `betfair_live_orders`, `betfair_live_heartbeat`): il gate la trova
        assente e Omega ripiega sul percorso REST;
      * le tabelle storiche (HT->FT, per minuto, fixture, frequenze di lega):
        una registrazione e' UNA partita, non uno storico;
      * `live_now` (il punteggio lo porta il feed dello scanner, come in
        produzione quando lo scanner c'e').
    """

    def __init__(self, control: Dict[str, Any]) -> None:
        super().__init__(control)
        self.eventi: Dict[str, Dict[str, Any]] = {}
        self.snapshot_mercati: Dict[str, Dict[str, Any]] = {}
        self.obiettivi: Dict[str, float] = {}
        self.missioni: List[Dict[str, Any]] = []
        self.richieste_manuali: List[Dict[str, Any]] = []

    # ------------------------------------------------------------- control
    def read_control(self) -> Optional[Dict[str, Any]]:
        return dict(self.control)

    def set_control(self, **fields: Any) -> None:
        if not fields:
            return
        self.control.update(fields)

    def log(self, kind: str, payload: Optional[Dict[str, Any]] = None,
            event_id: Optional[str] = None) -> None:
        # il vero ha firma (kind, payload): l'`event_id` resta opzionale per
        # compatibilita' col banco, e non viene mai passato dal servizio Omega
        self.attivita.append((str(kind), dict(payload or {}), event_id))

    # -------------------------------------------------------------- trades
    def _viola_unique(self, trade: Dict[str, Any]) -> Optional[str]:
        """Gli indici UNICI parziali delle migrazioni, come li applica il DB."""
        if trade.get("closes_trade_id"):
            return None
        fallita = str((trade.get("meta") or {}).get("leg_failed") or "") == "True"
        if (trade.get("meta") or {}).get("leg_failed") is True:
            fallita = True
        if fallita:
            return None
        eid = str(trade.get("event_id") or "")
        fase = trade.get("phase")
        for r in self.trades:
            if r.get("closes_trade_id"):
                continue
            if (r.get("meta") or {}).get("leg_failed") is True:
                continue
            if str(r.get("event_id") or "") != eid:
                continue
            # uq_omega_trades_auto_leg (event_id, coalesce(phase,'')) WHERE origin='auto'
            if (str(trade.get("origin") or "") == "auto"
                    and str(r.get("origin") or "") == "auto"
                    and str(r.get("phase") or "") == str(fase or "")):
                return "uq_omega_trades_auto_leg"
            # uq_omega_trades_leg (event_id, market_id, selection_id, side)
            # WHERE status <> 'error'
            if (str(r.get("status")) != "error" and str(trade.get("status")) != "error"
                    and str(r.get("market_id")) == str(trade.get("market_id"))
                    and int(r.get("selection_id") or 0) == int(trade.get("selection_id") or 0)
                    and str(r.get("side")) == str(trade.get("side"))):
                return "uq_omega_trades_leg"
        return None

    def insert_trade(self, trade: Dict[str, Any]) -> Optional[int]:
        viola = self._viola_unique(trade)
        if viola:
            # e' cosi' che PostgREST risponde a un conflitto: un'eccezione. Il
            # servizio la cattura e logga 'already_reserved' (I1).
            raise RuntimeError(f"duplicate key value violates unique constraint \"{viola}\"")
        self._id += 1
        riga = {**trade, "id": self._id}
        riga.setdefault("placed_at", self._adesso())
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
        # GUARD del vero: cancella SOLO se e' ancora 'pending'
        self.trades[:] = [r for r in self.trades
                          if not (int(r.get("id") or 0) == int(trade_id)
                                  and str(r.get("status")) == "pending")]

    def list_trades(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        righe = [dict(r) for r in self.trades
                 if status is None or str(r.get("status")) == str(status)]
        return sorted(righe, key=lambda r: int(r.get("id") or 0))

    def open_trades(self) -> List[Dict[str, Any]]:
        return self.list_trades(status="open")

    def get_trade(self, trade_id: int) -> Optional[Dict[str, Any]]:
        for r in self.trades:
            if int(r.get("id") or 0) == int(trade_id):
                return dict(r)
        return None

    def hedged_trades(self) -> List[Dict[str, Any]]:
        return self.list_trades(status="hedged")

    def closing_trades_for(self, trade_ids: List[int]) -> List[Dict[str, Any]]:
        if not trade_ids:
            return []
        ids = {int(i) for i in trade_ids}
        return [dict(r) for r in self.trades
                if r.get("closes_trade_id") is not None
                and int(r.get("closes_trade_id")) in ids]

    def trades_for_event(self, event_id: str, **_kw: Any) -> List[Dict[str, Any]]:
        campi = ("id", "phase", "status", "pnl", "liability", "bet_id", "side",
                 "size", "price", "mode")
        return [{k: r.get(k) for k in campi} for r in self.trades
                if str(r.get("event_id")) == str(event_id)]

    def traded_event_ids(self) -> set:
        return {str(r["event_id"]) for r in self.trades
                if r.get("event_id") and not (r.get("meta") or {}).get("leg_failed")}

    def manual_event_ids(self, since_iso: Optional[str] = None) -> set:
        return {str(r["event_id"]) for r in self.trades
                if r.get("event_id") and str(r.get("origin")) == "manual"
                and str(r.get("status")) != "error"}

    def traded_legs(self, since_iso: Optional[str] = None) -> set:
        out: set = set()
        for r in self.trades:
            if r.get("closes_trade_id"):
                continue
            if (r.get("meta") or {}).get("leg_failed"):
                continue
            eid = str(r.get("event_id") or "")
            if not eid:
                continue
            ph = r.get("phase")
            if ph in ("ht_cs", "ft_cs"):
                out.add((eid, ph))
            elif ph is None:
                out.update({(eid, "ht_cs"), (eid, "ft_cs")})
        return out

    def failed_legs(self, since_iso: Optional[str] = None) -> Dict[tuple, tuple]:
        out: Dict[tuple, tuple] = {}
        for r in self.trades:
            meta = r.get("meta") or {}
            if not meta.get("leg_failed"):
                continue
            chiave = (str(r.get("event_id") or ""), str(r.get("phase") or ""))
            n, _ts = out.get(chiave, (0, 0.0))
            ts = meta.get("leg_failed_at") or r.get("placed_at")
            epoch = 0.0
            dt = _iso_dt(ts)
            if dt is not None:
                epoch = dt.timestamp()
            out[chiave] = (n + 1, max(_ts, epoch))
        return out

    def positions_for_results(self, since_iso: str) -> List[Dict[str, Any]]:
        campi = ("id", "event_id", "phase", "status", "placed_at", "meta",
                 "closes_trade_id")
        return [{k: r.get(k) for k in campi} for r in self.trades
                if not r.get("closes_trade_id") and str(r.get("status")) != "error"]

    # -------------------------------------------------------------- eventi
    def upsert_events(self, events: List[Dict[str, Any]]) -> None:
        for e in events or []:
            eid = str(e.get("event_id"))
            base = dict(self.eventi.get(eid) or {})
            base.update(e)
            self.eventi[eid] = base

    def replace_events(self, events: List[Dict[str, Any]]) -> None:
        self.upsert_events(events)

    def update_event_markets(self, event_id: str, markets: List[Dict[str, Any]]) -> None:
        riga = self.eventi.setdefault(str(event_id), {"event_id": str(event_id)})
        riga["markets"] = markets
        riga["updated_at"] = self._adesso()

    def upsert_market_snapshot(self, snapshot: Dict[str, Any]) -> None:
        self.snapshot_mercati[str(snapshot.get("market_id"))] = dict(snapshot)

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        riga = self.eventi.get(str(event_id))
        return dict(riga) if riga else None

    def save_event_model(self, event_id: str, model: Dict[str, Any]) -> bool:
        riga = self.eventi.get(str(event_id))
        if riga is None:
            return False
        riga["model"] = dict(model)
        return True

    def event_lambda_hint(self, event_id: str) -> Optional[Dict[str, Any]]:
        for r in sorted(self.trades, key=lambda x: -int(x.get("id") or 0))[:5]:
            if str(r.get("event_id")) != str(event_id) or str(r.get("status")) == "error":
                continue
            model = (r.get("meta") or {}).get("model")
            lam = model.get("lambda_pre") if isinstance(model, dict) else None
            if isinstance(lam, (list, tuple)) and len(lam) == 2:
                return {"lambda_pre": [lam[0], lam[1]],
                        "lambda_source": model.get("lambda_source")}
        return None

    def read_live_now(self, event_id: str) -> Optional[Dict[str, Any]]:
        # in produzione la scrive il runner calcio; nel replay il punteggio
        # arriva dal FEED dello scanner, che e' il percorso di oggi (§5).
        self._dichiara("read_live_now", "tabella live_now del runner calcio: nel "
                                        "replay il punteggio passa dal feed unico")
        return None

    # -------------------------------------------------------------- manuale
    def pending_manual_requests(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.richieste_manuali if str(r.get("status")) == "pending"]

    def set_manual_status(self, req_id: int, status: str,
                          result: Optional[Dict[str, Any]] = None) -> None:
        for r in self.richieste_manuali:
            if int(r.get("id") or 0) == int(req_id):
                r["status"] = status
                if result is not None:
                    r["result"] = result
                if status in ("done", "error"):
                    r["processed_at"] = self._adesso()
                return

    def fail_stale_processing(self, max_age_min: int = 10) -> None:
        return None

    # ------------------------------------------------------------- missioni
    def active_missions(self) -> List[Dict[str, Any]]:
        return [dict(m) for m in self.missioni if str(m.get("status")) == "active"]

    def mission_event_ids(self) -> set:
        return {str(m["event_id"]) for m in self.missioni
                if m.get("event_id") and str(m.get("status")) in ("active", "paused")}

    def update_mission(self, event_id: str, **fields: Any) -> None:
        for m in self.missioni:
            if str(m.get("event_id")) == str(event_id):
                m.update(fields)
                return

    # ----------------------------------------------------- coda flumine
    def runner_heartbeat(self) -> Optional[Dict[str, Any]]:
        self._dichiara("runner_heartbeat",
                       "heartbeat del runner flumine: nel replay non esiste, "
                       "quindi il gate della coda e' CHIUSO e Omega percorre il "
                       "ramo REST (quello che usa in produzione a runner giu')")
        return None

    def live_follow_status(self, event_id: str) -> Optional[str]:
        return None

    def enqueue_live_order(self, payload: Dict[str, Any]) -> Optional[int]:
        self._dichiara("enqueue_live_order", "coda betfair_live_order_requests assente")
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

    # ------------------------------------------------------------ aggregati
    def aggregates(self, day_start: Any = None) -> Dict[str, Any]:
        """La STESSA funzione pura del fallback di produzione
        (`omega_db.aggregates` -> `omega_engine.aggregate_trades`): niente
        aritmetica scritta qui dentro."""
        campi = ("id", "event_id", "status", "pnl", "liability", "bet_id",
                 "placed_at", "settled_at", "meta", "mode", "closes_trade_id",
                 "size", "price", "commission", "phase", "side")
        righe = [{k: r.get(k) for k in campi} for r in self.trades]
        return E.aggregate_trades(righe, day_start)

    def upsert_daily_goal(self, day: str, goal: float) -> bool:
        self.obiettivi[str(day)] = float(goal)
        return True

    # ------------------------------------------ dati storici: non ci sono
    def ht_ft_transitions(self, league_id: Optional[int]) -> Optional[List[Dict[str, Any]]]:
        self._dichiara("ht_ft_transitions",
                       "storico HT->FT (RPC get_omega_ht_ft, migliaia di partite): "
                       "non e' nella registrazione di UNA partita, quindi il veto "
                       "empirico resta senza tabella")
        return []

    def minute_transitions(self, league_id: Optional[int], bucket: int,
                           target: str) -> Optional[List[Dict[str, Any]]]:
        self._dichiara("minute_transitions",
                       "tabella per MINUTO (RPC get_omega_minute_ft): storica, "
                       "assente dalla registrazione")
        return []

    def fixtures_for_window(self, start_iso: str, end_iso: str) -> List[Dict[str, Any]]:
        self._dichiara("fixtures_for_window",
                       "fixture_predictions (lambda pre-match del motore Poisson): "
                       "tabella storica, assente dalla registrazione")
        return []

    def fixture_analysis(self, fixture_id: int) -> Optional[Dict[str, Any]]:
        return None

    def market_frequency(self, league_id: int, market: str,
                         selection: str) -> Optional[Dict[str, Any]]:
        return None

    # -------------------------------------------------------------- servizio
    def _adesso(self) -> str:
        fn = getattr(self, "orologio", None)
        if callable(fn):
            return fn()
        return datetime.now(timezone.utc).isoformat()

    def _dichiara(self, nome: str, causa: str) -> None:
        voce = (nome, causa)
        if voce not in self.senza_dato:
            self.senza_dato.append(voce)


# ---------------------------------------------------------------------------
# IL MERCATO DI OMEGA SU FLUMINE
# ---------------------------------------------------------------------------
class MercatoOmega(MercatoFlumine):
    """`omega_market` servito dal matching di flumine.

    Le lettura di catalogo e book non sono REST: vengono dai `marketDefinition`
    della registrazione e dai `MarketBook` di flumine, e passano dalla FUNZIONE
    VERA che normalizza il book (`omega_market._snapshot_from_book`), cosi' che
    `closed`/`voided`/`winner` li decida `omega_engine.resolve_settlement` come
    in produzione.
    """

    # cio' che il servizio costruisce da `_real_market` (`omega_service.py:400`)
    CorrectScoreMarket = OM.CorrectScoreMarket
    MarketSnapshot = OM.MarketSnapshot
    EventInfo = OM.EventInfo
    PlaceResult = OM.PlaceResult
    CancelResult = OM.CancelResult
    PlaceRifiutato = OM.PlaceRifiutato

    def __init__(self, strategia: Any, *, catalogo: Catalogo, event_id: str,
                 nome_evento: str, motore: Optional[MotoreReplay] = None) -> None:
        super().__init__(strategia, motore)
        self.catalogo = catalogo
        self.event_id = str(event_id)
        self.nome_evento = str(nome_evento or event_id)
        self.ora_ms: int = 0
        # ogni piazzamento osservato (per i controlli J)
        self.piazzamenti: List[Dict[str, Any]] = []
        self.refs_usati: List[str] = []
        self.chiamate: Counter = Counter()

    # ------------------------------------------------------------- catalogo
    def list_today_football_events(self, lookback_hours: int = 12,
                                   *_a: Any, **_k: Any) -> List[Any]:
        self.chiamate["list_today_football_events"] += 1
        return [OM.EventInfo(event_id=self.event_id, name=self.nome_evento,
                             open_date=self.catalogo.avvio)]

    def _mercato_del_tipo(self, market_type: str) -> Optional[str]:
        for mid, mt in self.catalogo.tipi.items():
            if mt == str(market_type).upper():
                return mid
        return None

    def get_event_market_by_type(self, event_id: str, event_name: str,
                                 market_type: str) -> Optional[Any]:
        self.chiamate["get_event_market_by_type"] += 1
        mid = self._mercato_del_tipo(market_type)
        if mid is None:
            return None
        return OM.CorrectScoreMarket(
            market_id=mid, event_id=str(event_id),
            event_name=str(event_name or self.nome_evento),
            market_start_time=self.catalogo.avvio,
            runner_names=dict(self.catalogo.nomi.get(mid, {})))

    def get_correct_score_market(self, event: Any) -> Optional[Any]:
        return self.get_event_market_by_type(getattr(event, "event_id", self.event_id),
                                             getattr(event, "name", self.nome_evento),
                                             "CORRECT_SCORE")

    def list_event_markets(self, event_id: str, max_results: int = 30) -> List[Dict[str, Any]]:
        return [{"market_id": mid, "market_type": mt, "market_name": mt}
                for mid, mt in sorted(self.catalogo.tipi.items())][:max_results]

    def keep_alive(self) -> None:
        return None

    def get_inplay_scores(self, event_ids: List[str]) -> Dict[str, Any]:
        return {}

    def call(self, fn: Any) -> Any:
        raise RuntimeError("chiamata REST diretta nel replay: non esiste rete")

    # ------------------------------------------------------------ definizioni
    def _definizione(self, market_id: str) -> Tuple[str, bool, Dict[int, str]]:
        """Stato e stati-runner del mercato all'ORA DI MERCATO corrente."""
        storia = self.catalogo.definizioni.get(str(market_id)) or []
        stato, inplay, runners = "OPEN", False, {}
        for pt, st, ip, sr in storia:
            if pt > self.ora_ms:
                break
            stato, inplay, runners = st, ip, sr
        return stato, inplay, runners

    def _book_rest(self, market_id: str) -> Optional[Dict[str, Any]]:
        """Il book nella forma REST (quella che `_snapshot_from_book` legge):
        prezzi dal MarketBook di flumine, stati dal `marketDefinition`."""
        from ...stream.backtest.sim_strategy import _offer_price, _offer_size

        stato, inplay, stati_runner = self._definizione(market_id)
        mercato = self.s.mercati.get(str(market_id))
        libro = getattr(mercato, "market_book", None) if mercato is not None else None
        runners: List[Dict[str, Any]] = []
        sid_visti = set()
        for r in (getattr(libro, "runners", None) or []):
            sid = int(getattr(r, "selection_id", 0) or 0)
            sid_visti.add(sid)
            ex = getattr(r, "ex", None)
            atb = (getattr(ex, "available_to_back", None) if ex else None) or []
            atl = (getattr(ex, "available_to_lay", None) if ex else None) or []
            runners.append({
                "selectionId": sid,
                "status": stati_runner.get(sid, "ACTIVE"),
                "ex": {
                    "availableToBack": [{"price": _offer_price(x), "size": _offer_size(x)}
                                        for x in atb[:5]],
                    "availableToLay": [{"price": _offer_price(x), "size": _offer_size(x)}
                                       for x in atl[:5]],
                },
            })
        for sid, st in stati_runner.items():
            if sid not in sid_visti:
                runners.append({"selectionId": int(sid), "status": st,
                                "ex": {"availableToBack": [], "availableToLay": []}})
        if not runners:
            return None
        return {"status": stato, "inplay": bool(inplay), "runners": runners}

    def read_market(self, market: Any) -> Optional[Any]:
        self.chiamate["read_market"] += 1
        b = self._book_rest(str(getattr(market, "market_id", "")))
        if b is None:
            return None
        return OM._snapshot_from_book(market, b)

    def read_markets(self, markets: List[Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for mk in markets or []:
            snap = self.read_market(mk)
            if snap is not None:
                out[str(getattr(mk, "market_id", ""))] = snap
        return out

    def read_book(self, market_id: str, runner_names: Optional[Dict[int, str]] = None,
                  *_a: Any, **_k: Any) -> Optional[Dict[str, Any]]:
        self.chiamate["read_book"] += 1
        b = self._book_rest(str(market_id))
        if b is None:
            return None
        nomi = dict(runner_names or self.catalogo.nomi.get(str(market_id), {}))
        righe = []
        for r in b["runners"]:
            lay_price, lay_size, ladder = OM._best_lay(r["ex"]["availableToLay"])
            back_price, back_size = OM._best_back(r["ex"]["availableToBack"])
            righe.append({
                "selection_id": int(r["selectionId"]),
                "name": nomi.get(int(r["selectionId"]), "?"),
                "status": r.get("status"),
                "lay_price": lay_price, "lay_size": lay_size,
                "back_price": back_price, "back_size": back_size,
                "lay_ladder": [list(x) for x in ladder],
            })
        return {"market_id": str(market_id), "status": b["status"],
                "inplay": b["inplay"], "runners": righe}

    # ------------------------------------------------------------- ordini
    def place_order_live(self, **kw: Any) -> Any:
        ref = str(kw.get("customer_ref") or "")
        richiesta = {k: kw.get(k) for k in ("market_id", "selection_id", "price",
                                            "size", "side", "event_id",
                                            "customer_ref", "fill_or_kill")}
        richiesta["refs_gia_usati"] = list(self.refs_usati)
        richiesta["ruolo"] = "apertura" if str(kw.get("side", "lay")).lower() == "lay" else "chiusura"
        try:
            res = super().place_order_live(**kw)
        finally:
            if ref:
                self.refs_usati.append(ref)
        self.piazzamenti.append({"richiesta": richiesta, "esito": res})
        return res

    def place_lay_live(self, *, market_id: str, selection_id: int, price: float,
                       size: float, event_id: str,
                       customer_ref: Optional[str] = None) -> Any:
        """Wrapper storico di produzione (`omega_market.place_lay_live:1066`)."""
        return self.place_order_live(market_id=market_id, selection_id=selection_id,
                                     price=price, size=size, event_id=event_id,
                                     side="lay", customer_ref=customer_ref)


# ---------------------------------------------------------------------------
# IL FEED DI OMEGA: la ScanRowCache VERA, servita dalla tabella del banco
# ---------------------------------------------------------------------------
class FeedReplay:
    """Serve a `scan_feed.ScanRowCache` le righe che lo SCANNER VERO ha scritto.

    L'unica trasformazione e' il RIBASAMENTO dell'istante: `updated_at` diventa
    `adesso_reale - eta`, dove `eta` e' l'eta' VERA della riga sull'orologio di
    mercato (piu' l'invecchiamento dello scenario). Le funzioni di freschezza
    (`fresh_payload`, `row_age_sec`) restano quelle di produzione e continuano a
    confrontare con `time.time()`: e' l'ETA' che decide, ed e' quella vera.
    """

    def __init__(self, banco: ScannerReplay) -> None:
        self.banco = banco
        self.invecchia_s = 0.0
        self.scanner_fermo_s = 0.0
        self.letture = 0

    def righe(self, event_ids: List[str]) -> List[Dict[str, Any]]:
        self.letture += 1
        adesso = time.time()
        mercato = float(self.banco.ora or 0.0)
        out: List[Dict[str, Any]] = []
        for eid in event_ids:
            riga = self.banco.riga(str(eid))
            if riga is None:
                continue
            scritta = _iso_dt(riga.get("updated_at"))
            eta = 0.0 if scritta is None else max(0.0, mercato - scritta.timestamp())
            eta += self.invecchia_s
            out.append({**riga,
                        "updated_at": datetime.fromtimestamp(
                            adesso - eta, tz=timezone.utc).isoformat()})
        return out

    def eta_riga(self, event_id: str) -> Optional[float]:
        """L'eta' VERA (secondi di MERCATO) della riga di scan dell'evento,
        invecchiamento dello scenario compreso. None se la riga non c'e'."""
        riga = self.banco.riga(str(event_id))
        if riga is None:
            return None
        scritta = _iso_dt(riga.get("updated_at"))
        if scritta is None:
            return None
        return max(0.0, float(self.banco.ora) - scritta.timestamp()) + self.invecchia_s

    def stato_scanner(self) -> Optional[Dict[str, Any]]:
        """L'heartbeat dello scanner. Nel replay lo scanner gira a ogni tick:
        e' VIVO, e lo scenario `feed-stantio` lo ferma per davvero (senza
        fermarlo, una riga vecchia resterebbe legittima — write-on-change)."""
        eta = self.scanner_fermo_s
        return {"id": "scanner", "payload": {},
                "updated_at": datetime.fromtimestamp(time.time() - eta,
                                                     tz=timezone.utc).isoformat()}


# ---------------------------------------------------------------------------
# GLI SCENARI — le condizioni rare non si aspettano, si provocano
# ---------------------------------------------------------------------------
# Cambiano SOLO i parametri (le stesse manopole che l'utente ha nella UI), la
# freschezza del feed o i guasti iniettati. Mai la partita, mai i prezzi, mai la
# strategia.
#
# L'OBIETTIVO DI GIORNATA SU UNA PARTITA SOLA — il reperto del banco.
# `run_once` divide l'obiettivo (G=250 EUR di default) per le GAMBE ancora
# piazzabili OGGI (`E.legs_remaining` sugli eventi che il mercato gli passa).
# Nel replay l'universo e' UNA partita, quindi le gambe residue sono al massimo
# due e il target di gamba diventa ~125 EUR: la size che ne esce (131,58 EUR su
# un lay a 20) non trova MAI la liquidita' richiesta, e Omega non apre — non per
# una sua regola, ma perche' il banco gli mostra un giorno con una partita sola.
# MISURATO su 35760084: a 3-0 il runner "3 - 2" e' lay 55,0 con 24,11 EUR di
# controparte, cioe' un candidato perfetto, scartato solo dal confronto
# 24,11 < 131,58.
# Lo scenario `giornata-reale` rimette il target di GAMBA al valore che avrebbe
# in una giornata vera (250 EUR su ~100 gambe = 2,50 EUR a gamba) toccando
# SOLO l'obiettivo, che e' la manopola dell'utente in UI (`omega_control.
# daily_goal`): G = 5,00 EUR su due gambe = 2,50 EUR a gamba. Nessuna soglia,
# nessun tetto, nessuna finestra, nessuno stake e' stato toccato.
GOAL_UNA_PARTITA = 5.0

#
# E ANCHE COL TARGET GIUSTO, SU QUESTA PARTITA OMEGA NON APRE. Misurato al 50'
# sul 3-0 (gamba 2T, CORRECT_SCORE, size da target 5,26 EUR):
#   3 - 2  lay 70,0  controparte 53,83  P(modello) 1,463 %  P implicita 1,43 %
#   3 - 3  lay 410,0 controparte  9,04  P(modello) 0,254 %  P implicita 0,24 %
# tutti gli altri sono gia' impossibili (0-x, 1-x, 2-x) o troppo vicini al
# punteggio (3-0, 3-1). La regola §11 «P del modello SOTTO la probabilita'
# implicita» li scarta entrambi per una manciata di centesimi di punto: su una
# partita finita 4-0 il mercato non sovrapprezza nessuna scoreline raggiungibile.
# E' un verdetto sulla PARTITA, non un difetto.
#
# Il valore, su questa registrazione, sta TUTTO SOPRA LA BANDA: l'unico
# risultato che il mercato sovrapprezza davvero e' il "3 - 3", che al 52' vale
# lay 300 (P modello 0,316 % contro una implicita 0,317 %) — fuori dal
# `price_max` di 120. Per esercitare place, green-up, riconciliazione e
# settlement lo scenario `apertura` (e i suoi derivati) allarga SOLO la banda di
# quota a 500, che e' una manopola della whitelist e della UI
# (`omega_config._SPEC["price_max"]`, limite 1000). Nessuna finestra, nessuno
# stake, nessun tetto, nessuna soglia di probabilita', nessuna gamba toccata; il
# referto lo dichiara in testa a ogni scenario che lo usa.
# ATTENZIONE: un lay a 300 con 5,26 EUR di stake impegna 1.572 EUR di liability.
# E' esattamente il «raccogliere spiccioli davanti al treno» di §9, ed e' il
# motivo per cui `cap-stretto` esiste.
_APRE: Dict[str, Any] = {"__goal": GOAL_UNA_PARTITA, "price_max": 500.0}

SCENARI: Dict[str, Dict[str, Any]] = {
    # come gira in produzione, coi parametri e l'obiettivo di default
    "base": {},
    # l'obiettivo di GAMBA di una giornata vera (vedi sopra)
    "giornata-reale": {"__goal": GOAL_UNA_PARTITA},
    # l'unico scenario in cui, su QUESTA registrazione, Omega apre davvero
    "apertura": dict(_APRE),
    # PAPER: stessa strategia, altro percorso di esecuzione (E.paper_fill).
    # Serve a MISURARE la divergenza col live (decisione 3 dell'utente).
    "paper": dict(_APRE),
    # tetti di rischio STRETTI: oggi in produzione sono tutti a ZERO, cioe'
    # SPENTI (§19.5), quindi senza questo scenario i controlli C1/C2/C3 non
    # avrebbero MAI un caso da giudicare.
    # 600 EUR di tetto per partita MORDE senza uccidere l'ordine: il lay a 300
    # con 5,26 EUR di stake impegna 1.572 EUR, il clamp lo riporta a ~2,01 EUR
    # di stake. Con un tetto piu' basso la size finirebbe sotto `min_stake` e la
    # gamba non nascerebbe: il controllo non avrebbe niente da giudicare.
    "cap-stretto": dict(_APRE, max_liability_per_match=600.0,
                        max_open_liability=2000.0, daily_loss_cap=15.0),
    # bot FERMO con una posizione aperta: le protezioni girano, le aperture no.
    # Lo stop arriva quando la prima posizione e' aperta, come il pulsante della
    # UI: fermarlo dal primo tick non proverebbe niente.
    "bot-fermo": dict(_APRE),
    # feed STANTIO: riga e scanner entrambi vecchi (nessun ingresso, uscite vive)
    "feed-stantio": dict(_APRE),
    # i primi piazzamenti a esito IGNOTO: nascono le righe in riconciliazione
    "esiti-ignoti": dict(_APRE),
    # riavvio a meta' partita: le cache di PROCESSO spariscono, il DB resta
    "riavvio": dict(_APRE),
    # l'utente ha una sua operazione a mano sulla stessa partita: il bot deve
    # ignorarla (ordine dell'utente 16/09 h18)
    "manuale-e-bot": dict(_APRE),
    # l'utente chiude a mano TUTTE le gambe della partita: dal giro dopo il bot
    # se ne accorge e non fa piu' niente su quella partita
    "cashout-globale": dict(_APRE),
}

SCENARI_DESCRITTI: Dict[str, str] = {
    "base": "parametri E obiettivo di default (G=250): su UNA partita il target "
            "di gamba vale ~125 EUR e nessun book ha quella controparte — "
            "reperto del banco, non di Omega",
    "giornata-reale": "come sopra ma con l'obiettivo di giornata riportato a una "
                      "partita sola (G=5 EUR = 2,50 EUR a gamba, il target che "
                      "Omega avrebbe con ~100 gambe in un giorno)",
    "apertura": "giornata-reale + banda di quota allargata a 500 (manopola della "
                "whitelist): su 35760084 l'unico risultato sovrapprezzato dal "
                "mercato e' il '3 - 3' a 300, fuori dal price_max di 120",
    "paper": "modalita' PAPER: fill istantaneo di omega_engine.paper_fill, "
             "senza bet delay (P4) — si misura la divergenza col live",
    "cap-stretto": "tetti di rischio stretti: in produzione sono a ZERO (§19.5), "
                   "senza questo scenario C1/C2/C3 non hanno mai un caso",
    "bot-fermo": "bot fermato dalla UI con posizione aperta: settlement, "
                 "green-up e riconciliazione girano, le aperture no (§12)",
    "feed-stantio": "riga E scanner vecchi: nessuna decisione sui prezzi fermi "
                    "(FEED_MAX_AGE_S / DECISION_MAX_AGE_S / CASHOUT_FEED_MAX_AGE_S)",
    "esiti-ignoti": "i primi piazzamenti sollevano: nasce la riconciliazione "
                    "(§I3, difetto 4 del 15/09)",
    "riavvio": "riavvio a meta' partita con posizione aperta: lo stato si "
               "ritrova dal DB, non dalla RAM (difetto 19 del catalogo)",
    "manuale-e-bot": "una lay MANUALE dell'utente sulla stessa partita: il bot "
                     "deve ignorarla, e i suoi numeri non devono contenerla (E3)",
    "cashout-globale": "l'utente chiude a mano TUTTE le gambe della partita "
                       "(una richiesta `cashout` per gamba, come fa la UI): dal "
                       "giro dopo il bot non deve fare piu' niente li' (E4)",
}

QUANTI_GUASTI = 2


def _riavvia_processo() -> List[str]:
    """Butta via le cache di PROCESSO di `omega_service`, come un riavvio.

    Non tocca il database in memoria: quello e' il DB e in produzione
    sopravvive. Torna l'elenco di cio' che e' stato azzerato — un riavvio che
    non si sa che cosa ha buttato non prova niente.
    """
    azzerati: List[str] = []
    S.svuota_le_cache()
    azzerati.append("svuota_le_cache (feed, scanner, aggregati, insiemi, fasi)")
    for nome in ("_LEG_RETRY", "_SKIP_SEEN", "_BLIND_CYCLES", "_MARKET_FIT_CACHE",
                 "_LAMBDA_CACHE", "_IDLE_STATS_AT"):
        d = getattr(S, nome, None)
        if isinstance(d, dict) and d:
            d.clear()
            azzerati.append(nome)
    return azzerati


# ---------------------------------------------------------------------------
# la strategia flumine: alimenta lo scanner, fa girare il servizio, certifica
# ---------------------------------------------------------------------------
def _crea_strategia():
    from flumine import BaseStrategy

    class OmegaCert(BaseStrategy):
        """A ogni tick alimenta lo SCANNER VERO coi book di flumine; alla cadenza
        vera di Omega chiama `omega_service.run_once` — il giro INTERO."""

        def __init__(self, *, event_id: str, params: Dict[str, Any], mode: str,
                     banco: ScannerReplay, catalogo: Catalogo, feed: FeedReplay,
                     punteggi: List[Tuple[int, Dict[str, Any]]],
                     nome_evento: str, status: str = "running",
                     goal: float = omega_config.DEFAULT_DAILY_GOAL,
                     ferma_su_posizione: bool = False,
                     lay_manuale: bool = False, cashout_globale: bool = False,
                     ogni_ms: int = 0, riavvia: bool = False, **kw: Any) -> None:
            self.event_id = str(event_id)
            self.params = dict(params)
            self.mode = str(mode)
            self.banco = banco
            self.catalogo = catalogo
            self.feed = feed
            self.nome_evento = nome_evento
            self._punteggi = list(punteggi or [])
            self._ts_punteggi = [t for t, _ in self._punteggi]
            self._i_punteggi = 0
            self.ogni_ms = int(ogni_ms)
            self.riavvia = bool(riavvia)
            self.riavvio_fatto: Optional[List[str]] = None
            self.ferma_su_posizione = bool(ferma_su_posizione)
            self.fermato_al: Optional[str] = None
            self.lay_manuale = bool(lay_manuale)
            self.manuale_scritta = False
            self.scenario_cashout = bool(cashout_globale)
            self.cashout_chiesto: Optional[str] = None
            self.cashout_fatto = False
            self._req_id = 0
            self.mercati: Dict[str, Any] = {}
            self.db = DbMemoriaOmega({
                "id": 1, "status": status, "mode": self.mode,
                "params": dict(params), "daily_goal": float(goal),
                "stats": {},
            })
            self.db.orologio = lambda: self.banco.adesso().isoformat()
            self.mercato = MercatoOmega(self, catalogo=catalogo, event_id=self.event_id,
                                        nome_evento=nome_evento)
            self.referto = CERT.Referto(event_id=str(event_id))
            self._ultimo_ms = 0
            self._prossimo_giro_ms = 0
            self._stati: List[str] = []
            self.righe_assenti = 0
            self.giri = 0
            self.giri_finali = 0
            self._piazzamenti_visti = 0
            # ultima chiamata a E.dynamic_target: (goal, realized, legs_left, target)
            self.ultimo_target: Optional[Tuple[float, float, int, float]] = None
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
            pt_ms = (int(self.banco.imposta_ora(pt.timestamp()) * 1000)
                     if pt is not None else 0)
            self.mercato.ora_ms = pt_ms
            self.banco.applica_book(market_book)
            self.referto.tick += 1
            if pt_ms < self._prossimo_giro_ms:
                return
            self._ultimo_ms = pt_ms
            self._un_giro(pt_ms)

        # ------------------------------------------------------------ Omega
        def _un_giro(self, pt_ms: int) -> None:
            # 1) i punteggi fino a questo istante, dal record IPS grezzo e dal
            #    parser vero (`Scanner.apply_score_state`)
            i = bisect_right(self._ts_punteggi, int(pt_ms))
            while self._i_punteggi < i:
                self.banco.applica_punteggio(self.event_id,
                                             self._punteggi[self._i_punteggi][1])
                self._i_punteggi += 1
            # 2) LA RIGA LA SCRIVE LO SCANNER VERO
            self.banco.pubblica()
            if self.banco.riga(self.event_id) is None:
                self.righe_assenti += 1
            # 2-bis) RIAVVIO a meta' partita, con soldi dentro
            if self.riavvia and self.riavvio_fatto is None and any(
                    str(r.get("status")) in ("open", "pending", "hedged")
                    for r in self.db.trades):
                self.riavvio_fatto = _riavvia_processo()
                self.db.log("replay_riavvio", {"azzerati": self.riavvio_fatto})
            # 2-ter) BOT FERMATO DALLA UI con una posizione aperta: e' il gesto
            #    dell'utente sul pulsante, non un parametro. Da qui in poi le
            #    APERTURE devono sparire e le protezioni restare (§12).
            if (self.ferma_su_posizione and self.fermato_al is None
                    and any(str(r.get("status")) in ("open", "hedged")
                            for r in self.db.trades)):
                self.db.set_control(status="stopped")
                self.fermato_al = self.banco.adesso().isoformat()
                self.db.log("replay_stop_utente", {"quando": self.fermato_al})
            # 2-quater) L'UTENTE HA UNA SUA OPERAZIONE SULLA PARTITA.
            #    Una riga `omega_trades` con `origin='manual'`, scritta com'e'
            #    scritta dal percorso manuale di produzione
            #    (`omega_service._manual_place:3230`): da qui in poi il bot deve
            #    ignorarla (ordine dell'utente 16/09 h18).
            if self.lay_manuale and not self.manuale_scritta:
                self.manuale_scritta = bool(self._scrivi_lay_manuale())
            adesso = self.banco.adesso()
            # 2-quinquies) CASH-OUT GLOBALE: l'utente chiude a mano TUTTE le
            #    gambe aperte della partita. La UI non ha un bottone «tutto»:
            #    manda UNA richiesta `cashout` per gamba
            #    (`omega_service._manual_cashout:3421`), ed e' quello che si fa
            #    qui. Le richieste le esegue `process_manual` dentro `run_once`.
            if self.scenario_cashout and self.cashout_chiesto is None:
                aperte = [r for r in self.db.trades
                          if str(r.get("status")) == "open" and not r.get("closes_trade_id")]
                if aperte:
                    for r in aperte:
                        self._req_id += 1
                        self.db.richieste_manuali.append({
                            "id": self._req_id, "kind": "cashout", "status": "pending",
                            "payload": {"trade_id": int(r["id"]), "fraction": 1.0},
                        })
                    self.cashout_chiesto = adesso.isoformat()
                    self.db.log("replay_cashout_globale",
                                {"gambe": [int(r["id"]) for r in aperte],
                                 "quando": self.cashout_chiesto})
            # 3) IL SERVIZIO INTERO — `run_once`, non un pezzo
            prima_attivita = len(self.db.attivita)
            try:
                esito = S.run_once(market=self.mercato, db=self.db, now=adesso)
            except Exception as ex:  # noqa: BLE001 - un'eccezione del servizio E' un referto
                self.referto.violazioni.append(CERT.Violazione(
                    "SERVIZIO", "il giro del servizio non deve mai sollevare",
                    f"{type(ex).__name__}: {ex}", "giro"))
                return
            self.giri += 1
            self.referto.decisioni += 1
            # 3-bis) il cash-out globale e' ANDATO A BUON FINE quando non resta
            #    nessuna apertura del bot: da QUESTO giro in poi vale E4.
            if (self.scenario_cashout and self.cashout_chiesto is not None
                    and not self.cashout_fatto):
                # «l'utente ha chiuso a mano la partita» = le sue richieste sono
                # state ESEGUITE. Se la liquidita' ha cappato il fill e resta un
                # residuo, la posizione e' ancora aperta: E4 lo sa e allenta la
                # parte stretta del controllo (vedi `certificazione._e4`).
                self.cashout_fatto = bool(self.db.richieste_manuali) and all(
                    str(r.get("status")) == "done" for r in self.db.richieste_manuali)
            # 4) la CADENZA VERA: `poll_interval_s`, allargata a `idle_cycle_s`
            #    quando il giro non ha niente che si muova da solo
            #    (`omega_service.main:5414-5423`)
            passo = float(self.params.get("poll_interval_s") or 20.0)
            if not esito.get("fretta"):
                passo = max(passo, float(self.params.get("idle_cycle_s") or 0.0))
            self._prossimo_giro_ms = pt_ms + int(max(1.0, passo) * 1000)
            if self.ogni_ms:
                self._prossimo_giro_ms = pt_ms + self.ogni_ms
            # 5) gli ordini nati in questo giro: famiglia J
            attivita = self.db.attivita[prima_attivita:]
            nuovi = self.mercato.piazzamenti[self._piazzamenti_visti:]
            self._piazzamenti_visti = len(self.mercato.piazzamenti)
            for p in nuovi:
                self._osserva(CERT.Momento(
                    tipo="ordine", now=adesso, params=self.params,
                    event_id=self.event_id, mode=self.mode,
                    richiesta=p["richiesta"], esito=p["esito"],
                    db=self.db, attivita=attivita))
            # 6) fine giro: persistenza, stats, settlement
            stato = str(esito.get("status") or ("stopped" if esito.get("stopped")
                                                else "running"))
            if stato not in self._stati:
                self._stati.append(stato)
            for chiave in ("placed", "settled", "greenup", "missions"):
                if esito.get(chiave):
                    self.referto.azioni += int(esito[chiave] or 0)
            self._osserva(CERT.Momento(
                tipo="giro", now=adesso, params=self.params, event_id=self.event_id,
                mode=self.mode, db=self.db, stats=esito.get("stats"),
                esito_giro=esito, attivita=self.db.attivita,
                feed_eta=self.feed.eta_riga(self.event_id),
                status_control=str(self.db.control.get("status") or ""),
                cashout_globale=self.cashout_fatto,
                posizioni_aperte=len([r for r in self.db.trades
                                      if str(r.get("status")) in ("open", "hedged")]),
                righe_ordine=self.mercato.list_current_orders()
                + self.mercato.list_cleared_orders()))

        # ------------------------------------------------------- controlli
        def _osserva(self, m: CERT.Momento) -> None:
            self.referto.violazioni.extend(CERT.verifica(m, self.referto.sollecitati))
            CERT.osserva(self.referto.andamento, m)

        def _scrivi_lay_manuale(self) -> bool:
            """L'operazione dell'UTENTE sulla partita, scritta come la scrive il
            percorso manuale di produzione (`omega_service._manual_place:3204-3240`):
            `origin='manual'`, `meta.manual=True`, la stessa forma di riga.

            Si usa il mercato CORRECT_SCORE della registrazione e una scoreline
            vera del catalogo, cosi' che sia una posizione che l'utente avrebbe
            potuto davvero prendere. Nessun prezzo inventato: si legge il book
            di flumine di quel momento.
            """
            mid = next((k for k, v in self.catalogo.tipi.items()
                        if v == "CORRECT_SCORE"), None)
            if mid is None:
                return False
            book = self.mercato.read_book(mid)
            if not book:
                return False
            riga = next((r for r in book["runners"]
                         if r.get("lay_price") and float(r.get("lay_size") or 0) >= 2.0
                         and E.is_scoreline(str(r.get("name") or ""))), None)
            if riga is None:
                return False
            prezzo = float(riga["lay_price"])
            size = 2.0
            self.db.insert_trade({
                "event_id": self.event_id, "event_name": self.nome_evento,
                "market_id": mid, "selection_id": int(riga["selection_id"]),
                "runner_name": riga["name"], "side": "lay", "mode": self.mode,
                "origin": "manual", "price": prezzo, "size": size,
                "liability": E.liability_from_lay(size, prezzo),
                "commission": float(self.params.get("commission_pct", 5.0)) / 100.0,
                "status": "open", "pnl": 0.0,
                "meta": {"manual": True,
                         "commission": float(self.params.get("commission_pct", 5.0)) / 100.0,
                         "requested_size": size},
            })
            self.db.log("replay_lay_manuale",
                        {"market_id": mid, "selection_id": int(riga["selection_id"]),
                         "runner": riga["name"], "price": prezzo, "size": size})
            return True

        def giri_dopo_la_partita(self, quanti: int = 3) -> int:
            """IL SETTLEMENT VIENE DOPO IL FISCHIO, e il servizio non si ferma.

            `MotoreReplay` consegna i book `CLOSED` a flumine ma NON alla
            strategia (`_a_flumine` esce prima, come fa `FlumineSimulation`),
            quindi l'ultimo giro del bot cade sempre PRIMA della chiusura del
            mercato: senza questi giri in coda la fase di settlement
            (`settle_open` -> `market.read_market` -> WINNER del Correct Score)
            non avrebbe mai un mercato chiuso da leggere, e il P&L con la
            commissione resterebbe non verificato.
            In produzione il servizio continua a girare a partita finita, ed e'
            proprio li' che regola: qui si fa la stessa cosa, portando
            l'orologio all'ULTIMO istante della registrazione — non a un istante
            inventato.
            """
            ultimo = 0
            for storia in self.catalogo.definizioni.values():
                if storia:
                    ultimo = max(ultimo, int(storia[-1][0]))
            if not ultimo:
                return 0
            fatti = 0
            passo = int(max(1.0, float(self.params.get("poll_interval_s") or 20.0)) * 1000)
            for i in range(int(quanti)):
                pt_ms = ultimo + i * passo
                self.banco.imposta_ora(pt_ms / 1000.0)
                self.mercato.ora_ms = pt_ms
                self._prossimo_giro_ms = 0
                self._un_giro(pt_ms)
                fatti += 1
            self.giri_finali = fatti
            return fatti

        def chiudi(self) -> CERT.Referto:
            self.referto.stati_visti = list(self._stati)
            return self.referto

    return OmegaCert


# ---------------------------------------------------------------------------
# GLI AGGANCI AL SERVIZIO — avvolgere, mai riscrivere
# ---------------------------------------------------------------------------
class Sonde:
    """Avvolge cinque funzioni del servizio VERO per osservare la condotta.

    Non cambia un valore: chiama l'originale, guarda argomenti e risultato, e li
    passa ai controlli. Alla fine rimette tutto a posto (sono attributi di
    modulo: lasciarli avvolti farebbe mentire tutto cio' che gira dopo).
    """

    def __init__(self, strategia: Any) -> None:
        self.s = strategia
        self._originali: Dict[str, Any] = {}

    def __enter__(self) -> "Sonde":
        st = self.s
        self._originali = {
            "_model_select": S._model_select,
            "_size_and_place": S._size_and_place,
            "_greenup_decide": S._greenup_decide,
            "_greenup_p_lose": S._greenup_p_lose,
            "_floor_plausibile": S._floor_plausibile,
            "dynamic_target": E.dynamic_target,
        }
        vero_select = S._model_select
        vero_size = S._size_and_place
        vero_decide = S._greenup_decide
        vero_p = S._greenup_p_lose
        vero_floor = S._floor_plausibile
        vero_target = E.dynamic_target

        def target_sorvegliato(goal, realized, matches_remaining):
            out = vero_target(goal, realized, matches_remaining)
            st.ultimo_target = (float(goal), float(realized),
                                int(matches_remaining), float(out))
            return out

        def select_sorvegliata(*, db, event_id, payload, snapshot, state, half,
                               params, size_needed):
            sel, audit, why = vero_select(db=db, event_id=event_id, payload=payload,
                                          snapshot=snapshot, state=state, half=half,
                                          params=params, size_needed=size_needed)
            st._osserva(CERT.Momento(
                tipo="selezione", now=st.banco.adesso(), params=params,
                event_id=str(event_id), mode=st.mode,
                leg=("ht_cs" if half else "ft_cs"), half=bool(half), state=state,
                snapshot=snapshot, sel=sel, audit=audit, motivo=why,
                size_needed=size_needed, db=st.db))
            return sel, audit, why

        def size_sorvegliato(**kw):
            """Il dimensionamento si osserva DOPO: la size che conta e' quella
            scritta sulla riga (gia' passata dal clamp della liability e dal cap
            di liquidita'), non una ricalcolata qui — che sarebbe un secondo
            metro, cioe' un'altra cosa."""
            prima = len(st.db.trades)
            # gli aggregati PRIMA: `_size_and_place` ci somma dentro la
            # liability appena aperta (`:1235`), e contarla due volte
            # farebbe accusare il bot di un tetto che non ha sforato
            agg_prima = dict(kw.get("aggregates") or {})
            out = vero_size(**kw)
            riga = st.db.trades[-1] if len(st.db.trades) > prima else None
            t = st.ultimo_target
            st._osserva(CERT.Momento(
                tipo="sizing", now=st.banco.adesso(), params=kw.get("params") or {},
                event_id=str(getattr(kw.get("ev"), "event_id", "")), mode=st.mode,
                leg=kw.get("phase"), sel=kw.get("sel"), snapshot=kw.get("snapshot"),
                state=None, target=kw.get("target"),
                goal=(t[0] if t else None), realized=(t[1] if t else None),
                legs_left=(t[2] if t else None),
                minute=kw.get("minute"),
                size=(riga or {}).get("size"), price=(riga or {}).get("price"),
                aggregati=agg_prima, db=st.db))
            return out

        def decide_sorvegliata(trigger, p_lose, locked, hold_profit, loss_if_lose,
                               stake, params, distance, minute=None, half=False):
            azione, perche = vero_decide(trigger, p_lose, locked, hold_profit,
                                         loss_if_lose, stake, params, distance,
                                         minute, half)
            st._osserva(CERT.Momento(
                tipo="uscita", now=st.banco.adesso(), params=params,
                event_id=st.event_id, mode=st.mode, trigger=trigger,
                p_lose=p_lose, locked=locked, hold_profit=hold_profit,
                loss_if_lose=loss_if_lose, distance=distance, minute=minute,
                half=bool(half), azione=azione, perche=perche, db=st.db))
            return azione, perche

        def p_lose_sorvegliata(*, db, tr, payload, laid, state, half, prices,
                               params=None):
            """La P(perdita) e la sua FONTE, come il servizio le calcola. Il
            confronto modello-vs-mercato lo osserva `floor_sorvegliato`, che
            riceve i due numeri separati: da qui la P del modello non sarebbe
            ricavabile (il servizio restituisce gia' il massimo dei due)."""
            p, fonte = vero_p(db=db, tr=tr, payload=payload, laid=laid, state=state,
                              half=half, prices=prices, params=params)
            st._osserva(CERT.Momento(
                tipo="riserva", now=st.banco.adesso(), params=params or {},
                event_id=str(tr.get("event_id") or ""), mode=st.mode,
                p_lose=p, p_source=fonte,
                distance=S._goal_distance(laid, state),
                minute=getattr(state, "minute", None),
                half=bool(half), trade=tr, db=st.db))
            return p, fonte

        def floor_sorvegliato(p_model, p_mkt, distance, params):
            """`_floor_plausibile` riceve le DUE stime separate: e' il solo punto
            in cui si vede se il tetto di fine gara sta alzando il rischio oltre
            il rapporto dichiarato (§12, trade 84)."""
            ok = vero_floor(p_model, p_mkt, distance, params)
            st._osserva(CERT.Momento(
                tipo="riserva", now=st.banco.adesso(), params=params or {},
                event_id=st.event_id, mode=st.mode,
                p_lose=(max(float(p_model), float(p_mkt)) if ok else float(p_model)),
                p_source=("model_floor_market" if ok else "model_quota_implausibile"),
                p_modello=float(p_model), p_mercato=float(p_mkt),
                distance=distance, db=st.db))
            return ok

        S._model_select = select_sorvegliata          # type: ignore[assignment]
        S._size_and_place = size_sorvegliato          # type: ignore[assignment]
        S._greenup_decide = decide_sorvegliata        # type: ignore[assignment]
        S._greenup_p_lose = p_lose_sorvegliata        # type: ignore[assignment]
        S._floor_plausibile = floor_sorvegliato       # type: ignore[assignment]
        E.dynamic_target = target_sorvegliato         # type: ignore[assignment]
        return self

    def __exit__(self, *_exc: Any) -> None:
        S._model_select = self._originali["_model_select"]        # type: ignore[assignment]
        S._size_and_place = self._originali["_size_and_place"]    # type: ignore[assignment]
        S._greenup_decide = self._originali["_greenup_decide"]    # type: ignore[assignment]
        S._greenup_p_lose = self._originali["_greenup_p_lose"]    # type: ignore[assignment]
        S._floor_plausibile = self._originali["_floor_plausibile"]  # type: ignore[assignment]
        E.dynamic_target = self._originali["dynamic_target"]      # type: ignore[assignment]


class AmbienteOmega:
    """I tre agganci dichiarati nella testa del modulo, montati e smontati."""

    def __init__(self, mercato: Any, feed: FeedReplay, banco: ScannerReplay) -> None:
        self.mercato = mercato
        self.feed = feed
        self.banco = banco
        self._prima: Dict[str, Any] = {}

    def __enter__(self) -> "AmbienteOmega":
        self._prima = {
            "_real_market": S._real_market,
            "_mono": S._mono,
            "_SHARED_CACHE": SF._SHARED_CACHE,
        }
        S._real_market = self.mercato             # type: ignore[assignment]
        S._mono = (lambda: float(self.banco.ora))  # type: ignore[assignment]
        SF._SHARED_CACHE = SF.ScanRowCache(       # type: ignore[assignment]
            ttl_sec=0.0, fetch=self.feed.righe,
            clock=(lambda: float(self.banco.ora)),
            fetch_status=self.feed.stato_scanner)
        S.svuota_le_cache()
        return self

    def __exit__(self, *_exc: Any) -> None:
        S._real_market = self._prima["_real_market"]      # type: ignore[assignment]
        S._mono = self._prima["_mono"]                    # type: ignore[assignment]
        SF._SHARED_CACHE = self._prima["_SHARED_CACHE"]   # type: ignore[assignment]
        S.svuota_le_cache()


# ---------------------------------------------------------------------------
# un evento
# ---------------------------------------------------------------------------
def certifica_evento(*a: Any, **kw: Any) -> CERT.Referto:
    """Guscio: accende la simulazione di flumine e la RIMETTE A POSTO alla fine
    (i flag di `flumine.config` sono di PROCESSO)."""
    with simulazione_flumine():
        return _certifica_evento(*a, **kw)


def _certifica_evento(event_id: str, *, data_dir: str,
                      params: Optional[Dict[str, Any]] = None,
                      mode: str = "live", status: str = "running",
                      goal: float = omega_config.DEFAULT_DAILY_GOAL,
                      ferma_su_posizione: bool = False,
                      lay_manuale: bool = False, cashout_globale: bool = False,
                      ogni_ms: int = 0, invecchia_s: float = 0.0,
                      guasti: int = 0, riavvia: bool = False) -> CERT.Referto:
    """Fa rivivere a Omega una partita registrata e ritorna il referto."""
    from flumine import FlumineSimulation

    par = omega_config.resolve_params(dict(params or {}))
    raw = os.path.join(data_dir, str(event_id), f"{event_id}.raw.jsonl")
    ref = CERT.Referto(event_id=str(event_id))
    if not os.path.exists(raw):
        ref.note.append(f"registrazione assente: {raw}")
        return ref

    catalogo = leggi_catalogo(raw)
    try:
        punteggi = carica_punteggi(data_dir, str(event_id), "calcio")
    except Exception as ex:  # noqa: BLE001
        punteggi = []
        ref.note.append(f"punteggi non letti ({type(ex).__name__}): minuti e gol assenti")
    casa, fuori = nomi_dal_punteggio(punteggi)
    nome_evento = f"{casa or '?'} v {fuori or '?'}"

    banco = ScannerReplay(sport="calcio", nomi_extra=catalogo.nomi)
    banco.dichiara_nomi(casa, fuori)
    feed = FeedReplay(banco)
    feed.invecchia_s = float(invecchia_s or 0.0)
    if invecchia_s:
        # perche' il feed risulti STANTIO deve essere vecchio anche lo SCANNER:
        # con lo scanner vivo una riga ferma e' legittima (write-on-change)
        feed.scanner_fermo_s = float(invecchia_s)

    Strategia = _crea_strategia()
    strategia = Strategia(
        event_id=str(event_id), params=par, mode=mode, banco=banco,
        catalogo=catalogo, feed=feed, punteggi=punteggi, nome_evento=nome_evento,
        status=status, goal=float(goal), ferma_su_posizione=ferma_su_posizione,
        lay_manuale=lay_manuale, cashout_globale=cashout_globale,
        ogni_ms=ogni_ms, riavvia=riavvia,
        market_filter={"markets": [raw]},
        # I TETTI DI FLUMINE VANNO APERTI: qui il rischio lo governa Omega coi
        # suoi parametri, ed e' quello che si vuole misurare.
        max_order_exposure=1e9, max_selection_exposure=1e9,
        max_trade_count=int(1e9), max_live_trade_count=int(1e9))
    if guasti > 0:
        strategia.mercato.guasti["place_exception"] = int(guasti)

    quadro = FlumineSimulation(client=cliente_simulato())
    assicura_middleware_simulato(quadro)
    quadro.add_strategy(strategia)

    def _scanner_durante_attesa(mb: Any) -> None:
        # Omega e' bloccata sulla REST mentre Betfair trattiene l'ordine; lo
        # SCANNER no: in produzione e' un altro processo e continua a ricevere.
        pt = getattr(mb, "publish_time", None)
        if pt is not None:
            banco.imposta_ora(pt.timestamp())
        if banco.registra_mercato(mb):
            banco.applica_book(mb)

    motore = MotoreReplay(quadro, su_book=_scanner_durante_attesa)
    strategia.mercato.motore = motore
    with AmbienteOmega(strategia.mercato, feed, banco), Sonde(strategia):
        motore.esegui(strategia)
        # a partita finita il servizio NON si ferma: e' li' che regola (§6, I3)
        strategia.giri_dopo_la_partita()

    out = strategia.chiudi()
    out.ordini_piazzati = len(strategia.mercato.ordini)
    out.righe_scritte = len(strategia.db.trades)
    _componi_note(out, strategia, banco, motore, feed, catalogo, par, mode, status)
    out.violazioni.extend(CERT.difetti_di_progettazione(
        out.andamento, ordini_piazzati=out.ordini_piazzati,
        righe_scritte=out.righe_scritte))
    return out


def _componi_note(out: CERT.Referto, strategia: Any, banco: ScannerReplay,
                  motore: MotoreReplay, feed: FeedReplay, catalogo: Catalogo,
                  par: Dict[str, Any], mode: str, status: str) -> None:
    """Il referto §6.8: numeri, non aggettivi."""
    db = strategia.db
    out.note.append(f"modalita': {mode} | status del control: {status} | "
                    f"cadenza: poll {par.get('poll_interval_s')}s, a vuoto "
                    f"{par.get('idle_cycle_s')}s | giri di run_once: {strategia.giri} "
                    f"(di cui {strategia.giri_finali} dopo il fischio, per il settlement)")
    capi = {k: par.get(k) for k in ("max_liability_per_match", "max_open_liability",
                                    "daily_loss_cap", "max_events")}
    spenti = [k for k, v in capi.items() if not v]
    out.note.append(f"cap di rischio: {capi}"
                    + (f" | SPENTI (=0): {spenti}: i controlli C1/C2/C3 non hanno "
                       f"un caso da giudicare con questi parametri" if spenti else ""))
    if db.mancanti:
        out.note.append("metodi di database chiamati dal servizio e assenti dal "
                        f"banco: {sorted(db.mancanti)}")
    if db.senza_dato:
        out.note.append("[NON ESERCITABILE] dati di produzione assenti dalla "
                        "registrazione: "
                        + " | ".join(f"{n}: {c}" for n, c in db.senza_dato))
    if strategia.mercato.rifiutati:
        out.note.append(f"ordini rifiutati: {len(strategia.mercato.rifiutati)} "
                        f"(es. {strategia.mercato.rifiutati[0].get('err')})")
    out.note.append(f"ordini reali piazzati su flumine: {out.ordini_piazzati} | "
                    f"righe omega_trades scritte: {out.righe_scritte}")
    kinds = Counter(db.kinds())
    out.note.append("attivita' del servizio: "
                    + ", ".join(f"{k} x{n}" for k, n in kinds.most_common(10)))
    stati = Counter(str(r.get("status")) for r in db.trades)
    out.note.append(f"righe per stato: {dict(stati)}")
    # §6.5 — CIO' CHE IL TRADER VEDE: chiesto, abbinato, prezzo, residuo, stato.
    # E' la riga che la UI mostra: se un campo manca, il referto lo dice qui.
    for r in db.trades[:8]:
        meta = r.get("meta") or {}
        out.note.append(
            f"riga {r.get('id')} {r.get('phase') or '-'} {r.get('side')} "
            f"'{r.get('runner_name')}' stato={r.get('status')} "
            f"chiesto={meta.get('requested_size')} abbinato={r.get('size')} "
            f"prezzo={r.get('price')} residuo={meta.get('size_remaining')} "
            f"liability={r.get('liability')} bet_id={r.get('bet_id')} "
            f"pnl={r.get('pnl')} closes={r.get('closes_trade_id')} "
            f"fonte_lambda={(meta.get('model') or {}).get('lambda_source')}")
    motivi = Counter()
    for k, p, _e in db.attivita:
        if k in ("skip", "error", "size_reduced", "place_rifiutato"):
            motivi[str((p or {}).get("reason") or (p or {}).get("error_code") or k)[:60]] += 1
    if motivi:
        out.note.append("motivi dichiarati: "
                        + " | ".join(f"{m} x{n}" for m, n in motivi.most_common(6)))
        for m, n in motivi.most_common(8):
            out.motivi[m] = n
    fill = strategia.mercato.riepilogo_fill()
    conto = strategia.mercato.pnl(float(par.get("commission_pct", 5.0)) / 100.0)
    out.note.append(f"fill: {fill['fill']} abbinamenti su {fill['ordini_con_fill']} "
                    f"ordini per {fill['abbinato']} EUR (prezzi {fill['prezzi']})")
    out.note.append(f"P&L del replay: lordo {conto['lordo']:+.2f} | commissione "
                    f"{conto['commissione']:.2f} ({conto['aliquota'] * 100:.1f}%) | "
                    f"NETTO {conto['netto']:+.2f} EUR (non e' il metro: il metro "
                    f"e' la condotta)")
    out.note.append(f"bet delay: {motore.pompati} book passati mentre i piazzamenti "
                    f"aspettavano Betfair | book in ritardo (orologio fermo): "
                    f"{motore.book_in_ritardo} | LAPSE al passaggio in gioco: "
                    f"{motore.lapse_al_fischio}"
                    + (f" | {motore.senza_futuro} piazzamenti senza book futuro"
                       if motore.senza_futuro else ""))
    out.note.append(f"righe di scan scritte dallo SCANNER VERO: {banco.righe_scritte} "
                    f"| letture del feed di Omega: {feed.letture}"
                    + (f" | giri senza riga nel feed: {strategia.righe_assenti}"
                       if strategia.righe_assenti else ""))
    out.note.append(f"catalogo ricostruito dalla registrazione: "
                    f"{len(catalogo.tipi)} mercati, scoreline nominate su "
                    f"{len(catalogo.nomi)} mercati "
                    f"({sum(len(v) for v in catalogo.nomi.values())} selezioni)")
    out.note.append("chiamate al mercato: "
                    + ", ".join(f"{k} x{n}" for k, n in
                                strategia.mercato.chiamate.most_common(8)))
    if strategia.riavvio_fatto is not None:
        out.note.append("RIAVVIO a meta' partita: azzerate le cache di processo: "
                        + ", ".join(strategia.riavvio_fatto))
    elif strategia.riavvia:
        out.note.append("scenario riavvio: nessuna posizione aperta da ritrovare, "
                        "il riavvio non e' mai scattato")
    # la fotografia delle GAMBE: e' la regola §14.2 «due gambe SEMPRE»
    gambe = Counter(str(r.get("phase")) for r in db.trades if not r.get("closes_trade_id"))
    out.note.append(f"gambe aperte per fase: {dict(gambe)}")
    skip = out.andamento.skip_per_motivo
    if skip:
        out.note.append("gambe NON aperte, per motivo: "
                        + " | ".join(f"{m} x{n}" for m, n
                                     in sorted(skip.items(), key=lambda x: -x[1])[:6]))
    if out.andamento.uscite:
        out.note.append("decisioni di uscita: "
                        + " | ".join(f"{k} x{n}" for k, n in out.andamento.uscite.items()))
    if mode == "paper":
        out.note.append(
            "PAPER: i fill vengono da `omega_engine.paper_fill` (istantaneo, sullo "
            "snapshot, SENZA bet delay e senza coda) — non da flumine. E' la "
            "divergenza P4 dichiarata nel piano: qui si misura, non si corregge.")


# ---------------------------------------------------------------------------
# GLI SCENARI E IL COMANDO
# ---------------------------------------------------------------------------
def cadenza_ms(params: Dict[str, Any]) -> int:
    """La cadenza PIENA di Omega, dai SUOI parametri di produzione
    (`omega_service.main:5414`). 0 dal chiamante = questa."""
    return int(max(1.0, float(params.get("poll_interval_s") or 20.0)) * 1000)


def certifica_scenario(event_id: str, *, data_dir: str, scenario: str = "base",
                       ogni_ms: int = 0, campioni_diff: int = 0) -> CERT.Referto:
    """ADATTATORE PER IL BANCO — dal NOME dello scenario ai parametri di Omega.

    Firma identica per tutti i bot, cosi' il comando
    `python -m Betfair.stream.backtest.certifica <bot>` e' uno solo.
    """
    par = dict(omega_config.DEFAULTS)
    sc = dict(SCENARI.get(scenario, {}))
    goal = float(sc.pop("__goal", omega_config.DEFAULT_DAILY_GOAL))
    par.update(sc)
    mode = "paper" if scenario == "paper" else "live"
    status = "running"
    # il feed stantio si ottiene INVECCHIANDO la riga e lo scanner, non toccando
    # i prezzi: tre volte il tetto piu' largo che il servizio usa per decidere
    vecchio = (max(S.FEED_MAX_AGE_S, S.DECISION_MAX_AGE_S, S.GREENUP_MAX_AGE_S) * 3.0
               if scenario == "feed-stantio" else 0.0)
    ref = certifica_evento(
        event_id, data_dir=data_dir, params=par, mode=mode, status=status,
        goal=goal, ferma_su_posizione=(scenario == "bot-fermo"),
        lay_manuale=(scenario == "manuale-e-bot"),
        cashout_globale=(scenario == "cashout-globale"),
        ogni_ms=int(ogni_ms or 0), invecchia_s=vecchio,
        guasti=(QUANTI_GUASTI if scenario == "esiti-ignoti" else 0),
        riavvia=(scenario == "riavvio"))
    ref.note.insert(0, f"scenario '{scenario}': {SCENARI_DESCRITTI.get(scenario, '-')}")
    if scenario == "manuale-e-bot":
        quante = int(ref.sollecitati.get("E3") or 0)
        ref.note.append(
            f"scenario manuale-e-bot: il controllo E3 e' stato sollecitato "
            f"{quante} volte"
            + ("" if quante else " — la riga manuale non e' mai stata scritta "
                                "(nessun runner con lay e liquidita' al primo giro)"))
    if scenario == "cashout-globale":
        quante = int(ref.sollecitati.get("E4") or 0)
        ref.note.append(
            f"scenario cashout-globale: il controllo E4 e' stato sollecitato "
            f"{quante} volte"
            + ("" if quante else " — su questa registrazione il bot non ha mai "
                                "aperto, quindi non c'era niente da chiudere a "
                                "mano: il caso non e' capitato"))
    if scenario == "bot-fermo":
        quante = int(ref.sollecitati.get("C4") or 0)
        ref.note.append(
            f"scenario bot-fermo: il controllo C4 («a bot fermo nessuna apertura, "
            f"le protezioni girano») e' stato sollecitato {quante} volte"
            + ("" if quante else " — su questa registrazione nessuna posizione si "
                                "e' mai aperta, quindi il bot non e' mai stato "
                                "fermato CON soldi dentro: il caso non e' capitato"))
    return ref


def main(argv: Optional[List[str]] = None) -> int:
    """CHIAMANTE SOTTILE del punto d'ingresso unico.

    Il referto, la copertura dei controlli, il diario e il filtro delle
    registrazioni COMPLETE vivono in `Betfair/stream/backtest/certifica.py` e
    valgono per TUTTI i bot: qui non se ne tiene una seconda copia.
    """
    from ...stream.backtest.certifica import main as certifica_main

    return certifica_main(["omega"] + list(argv if argv is not None else sys.argv[1:]))


if __name__ == "__main__":
    sys.exit(main())
