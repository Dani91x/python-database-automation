"""service — BOT MIKE (Under 3.5 / Over 4.5), come il Safe bot: legge SOLO il feed unico.

Ciclo (``run_once``, iniettabile per i test):
  (a) richieste della UI (cashout / flatten / skip / resume) — SEMPRE;
  (b) per ogni partita seguita: Snapshot dal feed → ``engine.decide`` → azioni;
      protezioni/uscite SEMPRE, nuovi ingressi SOLO se status='running';
  (c) settlement a mercato chiuso (REST listMarketBook: 2 chiamate per partita, a fine gara);
  (d) stats + heartbeat su ``mike_control``.

Esecuzione = ``Betfair/safe_strategy/execution.place`` (reserve-first su ``mike_trades``,
paper = fill sul feed, live = REST FOK con la sessione condivisa). In PAPER e in-play
il fill viene DIFFERITO di ``bet_delay`` secondi (dal feed) e rieseguito al prezzo
allora disponibile: mai piu' ottimista del live. ``mode`` SOLO da ``mike_control``.

Uso: python -m Betfair.mike.service [--once] [--dry]
  --once  un ciclo e esce (collaudo);  --dry  nessun ordine (azioni loggate come would_place)
"""
from __future__ import annotations

import argparse
import dataclasses
import logging
import time
from datetime import datetime
from datetime import timedelta as _timedelta
from datetime import timezone
from typing import Any, Dict, List, Optional

from Betfair.safe_strategy import execution as X
from Betfair.stream import avvio_app as AA
from Betfair.stream import local_channel as _lc
from Betfair.stream import sveglia_canale as _SV

from . import config as C
from . import db as _real_db
from . import dossier as D
from . import engine as E
from . import feed as F

logger = logging.getLogger("mike")

_LOCK_PORT = C.env_int("MIKE_LOCK_PORT", C.LOCK_PORT_DEFAULT)
# (la deroga "scanner vivo" e' il parametro ``scanner_alive_max_s``: vedi
#  config.PARAM_SPEC e feed.feed_fresh. Questa costante non la usava nessuno.)
_PENDING_STALE_S = 120.0          # gamba pending senza esito da troppo: esito noto → ritirata, ignoto → riconciliazione
_SETTLE_RETRY_S = 30.0            # ripiego se settle_confirm_s = 0 (fra due letture REST a mercato chiuso)
_SETTLE_MAX_WAIT_S = 2 * 3600.0   # oltre: fallback sull'ultimo punteggio noto o ERROR
_DAILY_STOP_LOGGED: Dict[str, str] = {}   # {"day": iso Rome} → lo stop giornaliero si logga una volta al giorno
_ROW_MISSING_GRACE_S = 600.0      # riga assente dal feed per meno di cosi' = transitoria (es. passaggio pre-KO → in-play)
_MATCH_OVER_S = 3 * 3600.0        # oltre 3h dal KO la partita e' finita comunque
_MATCH_LIKELY_OVER_S = 100 * 60.0 # vista in-play e KO + 100': la riga sparita = partita finita (regolamento subito)
# 13/09 — le due cadenze del battito su ``mike_control`` sono diventate
# PARAMETRI (``heartbeat_min_s`` / ``stats_min_s``, vedi config.py): una
# cadenza cablata nel codice non si puo' allargare quando il database soffre.
# Questi restano solo come ripiego se i parametri mancassero.
_CRITICAL_LOG_EVERY_S = 45.0      # M7: i log CRITICI non vengono silenziati per 5 minuti
_STALE_REQUEST_MIN = 10           # richieste 'processing' piu' vecchie = crash: chiuse in errore (M2)
_STRATEGY_REF = C.CUSTOMER_STRATEGY_REF
_LAST_HEARTBEAT: Dict[str, float] = {}
_CONFIG_WARNED: Dict[str, str] = {}
# FASE A (16/09) — all'avvio dell'app nessun bot opera: la guardia confronta
# l'``APP_BOOT_ID`` di questo processo con quello salvato in ``mike_control.stats``.
# Vive per PROCESSO: si accende in ``main()``, cosi' un ``run_once`` chiamato da
# un test o da un banco di replay non e' un avvio dell'app e non cambia niente.
_GUARDIA_AVVIO = AA.Guardia("mike")

ACTIVE_STATES = tuple(s for s in E.STATES if s not in E.TERMINAL_STATES)


# ---------------------------------------------------------------------------
# L'ULTIMA BARRIERA PRIMA DI BETFAIR
# ---------------------------------------------------------------------------
# Mike piazza in REST diretto: non passa dalla coda flumine, quindi NON e'
# coperto da ``LIVE_ORDER_MODE`` ne' dal rifiuto cross-mode del worker, che sono
# gli interruttori di Omega e Safe. Fino al 13/09 l'unica cosa che separava il
# bot dai soldi veri era il valore di una colonna sul database: bastava un
# ``mike_control.mode`` rimasto a 'live' dalla sessione prima, e il primo
# "Avvia" armava fino a ``max_open_matches`` partite con denaro reale.
#
# ``MIKE_LIVE_ENABLED`` e' l'interruttore che mancava. Sta nel .env, si tocca a
# mano, e vale per il PROCESSO: finche' non e' acceso, ogni tentativo di
# piazzare un ordine reale solleva PRIMA di toccare la rete. Non e' una
# scomodita': e' la differenza fra "ho deciso di operare in live" e "il bot ha
# trovato un flag acceso da ieri".
#
# Il paper non lo vede nemmeno: la simulazione non passa da qui.
def mike_live_abilitato() -> bool:
    """Il processo e' autorizzato a piazzare ordini con SOLDI VERI?

    Ri-letta a ogni chiamata (come i kill-switch di Omega): spegnerla deve avere
    effetto SUBITO, senza riavviare niente.
    """
    return C.env_bool("MIKE_LIVE_ENABLED", False)


class _LiveNonAbilitato(RuntimeError):
    """Ordine reale tentato col kill-switch spento. NON e' un rifiuto
    dell'exchange: l'ordine non e' mai partito e non esiste da nessuna parte."""


def _pretendi_live_abilitato(che_cosa: str) -> None:
    if mike_live_abilitato():
        return
    logger.critical("[mike] ORDINE REALE BLOCCATO (%s): MIKE_LIVE_ENABLED non e' attiva. "
                    "Nessun ordine e' partito. Per operare davvero con soldi veri "
                    "impostare MIKE_LIVE_ENABLED=1 nel .env e riavviare l'app.", che_cosa)
    raise _LiveNonAbilitato(
        "MIKE_LIVE_ENABLED non attiva: nessun ordine reale e' stato inviato. "
        "E' l'interruttore di sicurezza del live, si accende a mano nel .env.")


# ---------------------------------------------------------------------------
# Market REST (solo settlement / fallback): sessione CONDIVISA di omega_market
# ---------------------------------------------------------------------------
class _RealMarket:
    @staticmethod
    def _bind_strategy_ref(omega_market: Any) -> None:
        """L1 — gli ordini LIVE di Mike devono portare il SUO customerStrategyRef.

        ``omega_market.place_order_live`` legge la costante di modulo: il servizio
        Mike e' un PROCESSO separato (lock 47319), quindi legare qui il ref
        'mike' marchia solo gli ordini di Mike e rende utilizzabili
        ``list_current_orders``/``listClearedOrders`` filtrate per Mike.
        Prima ogni ordine Mike usciva marchiato 'omega'.
        """
        if getattr(omega_market, "CUSTOMER_STRATEGY_REF", None) != _STRATEGY_REF:
            omega_market.CUSTOMER_STRATEGY_REF = _STRATEGY_REF

    @staticmethod
    def read_book(market_id: str, names: Dict[int, str]) -> Optional[dict]:
        from Betfair.omega import omega_market

        return omega_market.read_book(str(market_id), names)

    @staticmethod
    def place_order_live(**kw: Any) -> Any:
        from Betfair.omega import omega_market

        _pretendi_live_abilitato("place_order_live")
        _RealMarket._bind_strategy_ref(omega_market)
        return omega_market.place_order_live(**kw)

    @staticmethod
    def place_submin_live(**kw: Any) -> Any:
        """Importi SOTTO il minimo di piazzamento Betfair (place-and-trim).

        Mike lavora con importi esatti al centesimo (``exact_sizes``): una
        copertura da 1,35 EUR o uno stake da 0,73 EUR devono poter esistere.
        La sequenza (parcheggio a quota non abbinabile, taglio parziale,
        riprezzo) e' in ``omega_market.place_submin_live``.
        """
        from Betfair.omega import omega_market

        _pretendi_live_abilitato("place_submin_live")
        _RealMarket._bind_strategy_ref(omega_market)
        return omega_market.place_submin_live(**kw)

    @staticmethod
    def cancel_order_live(bet_id: str, market_id: str,
                          size_reduction: Optional[float] = None) -> Any:
        """ANNULLA DAVVERO l'ordine su Betfair (C.12a).

        ⚠️ Fino al 16/09 questa strada NON ESISTEVA: ``_RealMarket`` non
        esponeva nessun annullamento e tutti i «cancel» di Mike
        (``_request_cancel``, ``_request_flatten``, l'azione ``cancel``
        dell'engine, il TTL delle pending stantie) cambiavano SOLO lo stato
        della riga nel database. L'ordine restava VIVO su Betfair: il trader
        leggeva «annullato», quattro minuti dopo l'ordine si abbinava, nessuno
        lo contabilizzava e il motore nel frattempo rientrava — posizione
        doppia con soldi veri. QUANDO annullare non cambia (e' strategia):
        cambia che l'annullamento ARRIVA a Betfair.
        """
        from Betfair.omega import omega_market

        _pretendi_live_abilitato("cancel_order_live")
        _RealMarket._bind_strategy_ref(omega_market)
        return omega_market.cancel_order_live(str(bet_id), str(market_id), size_reduction)

    @staticmethod
    def list_current_orders() -> List[dict]:
        """Ordini VIVI marchiati 'mike' (riconciliazione C3)."""
        from Betfair.omega import omega_market

        _RealMarket._bind_strategy_ref(omega_market)
        return list(omega_market.list_current_orders(_STRATEGY_REF) or [])

    @staticmethod
    def list_cleared_orders() -> List[dict]:
        from Betfair.omega import omega_market

        _RealMarket._bind_strategy_ref(omega_market)
        return list(omega_market.list_cleared_orders(strategy_ref=_STRATEGY_REF) or [])

    # ------------------------------------------- LA POSIZIONE DI CONTO
    # ORDINE DELL'UTENTE 16/09 SERA - "se chiudo io il bot deve saperlo, anche
    # fuori dall'app". Le due letture qui sotto NON filtrano per
    # ``customerStrategyRef``: tornano cio' che c'e' sul CONTO su quel mercato,
    # ordini dell'utente compresi. Sono chiamate REST IN PIU', quindi le fa solo
    # ``_sorveglia_posizione_di_conto`` e alla cadenza del respiro del database
    # (``reconcile_every_s``, default 30 s per partita), mai a ogni giro (16.17).
    @staticmethod
    def list_account_orders(market_id: str) -> List[dict]:
        from Betfair.omega import omega_market

        return list(omega_market.list_current_orders_account([str(market_id)]) or [])

    @staticmethod
    def list_account_cleared_orders(market_id: str) -> List[dict]:
        from Betfair.omega import omega_market

        return list(omega_market.list_cleared_orders_account([str(market_id)]) or [])

    @staticmethod
    def market_profit_and_loss(market_id: str) -> Dict[str, Any]:
        """Controprova sintetica della posizione di conto (``listMarketProfitAndLoss``).
        Non decide niente: serve al referto e alla diagnosi."""
        from Betfair.omega import omega_market

        return dict(omega_market.market_profit_and_loss([str(market_id)]) or {})


_real_market = _RealMarket()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(ts: Optional[float]) -> Optional[str]:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat() if ts else None


# ---------------------------------------------------------------------------
# Serializzazione stato partita (mike_events) ⇄ MatchCtx
# ---------------------------------------------------------------------------
_CTX_FIELDS = ("last_green_at", "last_action_at", "attempts", "reentry_allowed", "reentry_done",
               "close_reason", "cover_skipped", "seq", "flatten_pending", "no_reentry",
               # CERT. 13/09: prezzo Under al fischio d'inizio (misura dello
               # scostamento fra ingresso pre-match e apertura del gioco)
               "ko_price_under",
               # FLUSSO 13/09 dal fischio: orologio della finestra di uscita,
               # baseline dei gol, momento del gol precoce e stato della
               # copertura a tranche. Senza questi un riavvio a meta' partita
               # perderebbe i timer e ricomincerebbe da capo (o resterebbe
               # scoperto in attesa di un'attesa che non finisce mai).
               "live_since", "ko_goals", "early_goal_at", "second_entry_done",
               "cover_stage", "cover_stage1_at", "cover_forced",
               # 16/09 — i rifiuti del mercato gia' incassati (difetto 19 del
               # catalogo: uno stato che vive solo in RAM si perde al riavvio, e
               # qui il riavvio farebbe ricominciare la riproposizione da capo).
               "rifiuti",
               # ORDINE DELL'UTENTE 16/09 — la memoria della sospensione con una
               # lay appoggiata viva: se il processo riparte in mezzo, la
               # rilettura alla riapertura non deve andare persa.
               "riapertura",
               # ORDINE DELL'UTENTE 16/09 SERA — la partita chiusa dall'utente
               # FUORI dall'app: un riavvio non deve far ricominciare Mike a
               # gestire una posizione che non c'e' piu'.
               "chiuso_dall_utente",
               # 17/09 (reperto 25) — il FRENO della copertura (conteggio dei
               # rifiuti per codice d'errore, orologio del ritmo minimo) e
               # l'ultimo stato visto del mercato Over 4.5. Senza persistenza un
               # riavvio farebbe ricominciare i 104 tentativi da capo (difetto
               # 19 del catalogo: lo stato che vive solo in RAM).
               "cover_rifiuti", "cover_mercato")


# ===========================================================================
# FAR RESPIRARE IL DATABASE (13/09/2026)
# ===========================================================================
# Il budget di IO di Supabase non e' infinito: finito quello l'istanza viene
# STROZZATA, i tempi di risposta esplodono, l'autovacuum salta e alla fine il
# database non risponde piu' (guides/troubleshooting/exhaust-disk-io). Misurato
# sul campo il 13/09: una lettura per chiave primaria arrivata a 39 secondi, e
# la query che questo ciclo fa ogni secondo che ha smesso di rispondere del
# tutto. Con letture cosi' il ciclo non chiude mai, e le partite restano ferme
# dove sono — che e' esattamente quello che si vedeva in pagina.
#
# Queste cache NON cambiano una virgola della logica di trading. Cambiano solo
# ogni quanto si richiede al database una cosa che nel frattempo non e'
# cambiata. Ognuna ha il suo parametro, quindi si stringe o si allarga dalla UI.
#
# Money-critical: il FEED e' l'unica lettura che influenza una decisione di
# mercato, ed e' per questo che la sua cache e' cortissima (2 s di default,
# contro i 15 s di ``feed_max_age_s`` oltre i quali il bot si ferma da solo).
# La freschezza continua a essere giudicata sull'``updated_at`` della riga, non
# su quando l'abbiamo letta: una riga vecchia resta vecchia anche se la
# rileggiamo adesso.
class _Cache:
    """Un valore letto dal database, con la sua scadenza."""

    __slots__ = ("valore", "letto_a")

    def __init__(self) -> None:
        self.valore: Any = None
        self.letto_a: float = 0.0

    def fresco(self, ora: float, ttl: float) -> bool:
        return self.valore is not None and (ora - self.letto_a) < ttl

    def metti(self, valore: Any, ora: float) -> Any:
        self.valore, self.letto_a = valore, ora
        return valore

    def svuota(self) -> None:
        self.valore, self.letto_a = None, 0.0


# parametri dell'ULTIMO giro: il loop li usa per decidere quanto aspettare,
# invece di rileggere il control una seconda volta a ogni secondo
_ULTIMI_PARAMS: Optional[Dict[str, Any]] = None

_CACHE_FEED = _Cache()
_CACHE_AGGREGATI = _Cache()
# le partite seguite: il servizio e' l'UNICO che scrive ``mike_events``, quindi
# la copia in memoria E' la verita' fra una rilettura e l'altra. La rilettura
# completa serve solo a riallinearsi dopo un riavvio o una modifica fatta da
# fuori (per esempio a mano sul database).
_CACHE_EVENTI: Dict[str, Dict[str, Any]] = {}
_EVENTI_LETTI_A: float = 0.0
# ultima riparazione dello specchio gambe <-> righe, per partita
_RICONCILIATO_A: Dict[str, float] = {}
# ultima SCRITTURA di ``mike_events``, per partita: e' l'orologio del battito di
# pubblicazione (vedi ``_persist``). Non e' una cache di dati, e' la memoria di
# "quando ho scritto l'ultima volta": senza, ogni giro riscriverebbe.
_SCRITTO_A: Dict[str, float] = {}


def svuota_le_cache() -> None:
    """Butta via tutto il letto: la prossima lettura va al database.

    Serve ai test e a chi vuole forzare un riallineamento immediato.
    """
    global _EVENTI_LETTI_A, _ULTIMI_PARAMS
    _ULTIMI_PARAMS = None
    _CACHE_FEED.svuota()
    _CACHE_AGGREGATI.svuota()
    _CACHE_EVENTI.clear()
    _RICONCILIATO_A.clear()
    _SCRITTO_A.clear()
    _LAST_HEARTBEAT.clear()
    _EVENTI_LETTI_A = 0.0


_MALFORMED_LOGGED: Dict[str, float] = {}   # {event_id: epoch} — dedup dell'attivita' 'leg_malformata'
_MALFORMED_EVERY_S = 300.0


def _legs_from_json(raw: Any, db: Any = None, event_id: Optional[str] = None) -> List[E.Leg]:
    """Gambe dal JSON di ``mike_events.positions``.

    M3 — una gamba MALFORMATA non viene piu' scartata in silenzio: e' una
    posizione che il bot non vedrebbe piu' (soldi invisibili) → log critico.
    L'ATTIVITA' e' deduplicata per partita (``_MALFORMED_EVERY_S``): il ciclo
    rilegge le stesse posizioni ogni secondo e senza freno riempirebbe
    ``mike_activity``.
    """
    out: List[E.Leg] = []
    fields = {f.name for f in dataclasses.fields(E.Leg)}
    for d in raw or []:
        bad = None
        if not isinstance(d, dict):
            bad = "elemento non oggetto"
        else:
            try:
                out.append(E.Leg(**{k: v for k, v in d.items() if k in fields}))
                continue
            except (TypeError, ValueError) as ex:
                bad = str(ex)[:120]
        logger.critical("[mike] %s: gamba MALFORMATA scartata (%s): %s", event_id, bad,
                        str(d)[:200])
        if db is not None:
            key = str(event_id)
            now_ts = time.time()
            if now_ts - float(_MALFORMED_LOGGED.get(key) or 0.0) < _MALFORMED_EVERY_S:
                continue
            _MALFORMED_LOGGED[key] = now_ts
            try:
                db.log("error", {"reason": "leg_malformata", "err": bad, "raw": str(d)[:200],
                                 "critical": True}, event_id)
            except Exception:  # noqa: BLE001 — il log non deve mai fermare il ciclo
                pass
    return out


def _ctx_from_row(row: Dict[str, Any], db: Any = None) -> E.MatchCtx:
    extra = row.get("ctx") or {}
    ctx = E.MatchCtx(state=str(row.get("state") or "WATCH"),
                     legs=_legs_from_json(row.get("positions"), db, row.get("event_id")),
                     cycle_no=int(row.get("cycle_no") or 0),
                     entry_price_initial=row.get("entry_price_initial"))
    for k in _CTX_FIELDS:
        if k in extra and extra[k] is not None:
            setattr(ctx, k, extra[k])
    if row.get("settled_pnl") is not None:
        ctx.settled_pnl = float(row["settled_pnl"])       # colonna top-level (round-trip, review F1 #5)
    if ctx.entry_price_initial is not None:
        ctx.entry_price_initial = float(ctx.entry_price_initial)
    return ctx


def _row_from_ctx(row: Dict[str, Any], ctx: E.MatchCtx, extra: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    out["state"] = ctx.state
    out["cycle_no"] = int(ctx.cycle_no)
    out["entry_price_initial"] = ctx.entry_price_initial
    # CERT. 13/09 — si salvano le gambe POTATE: quelle annullate e mai abbinate
    # oltre le ultime per ruolo sono zavorra (vedi engine.prune_dead_legs).
    # Una riga da 60 KB di sole gambe morte faceva sforare il timeout di
    # get_mike_state e produceva l'alert «statement timeout» sulla pagina Mike.
    out["positions"] = [dataclasses.asdict(l) for l in E.prune_dead_legs(ctx.legs)]
    out["settled_pnl"] = ctx.settled_pnl
    # i campi dell'engine VINCONO sui valori stantii di extra (bug: last_green_at
    # sovrascritto dal ctx precedente → cooldown ignorato)
    keep = dict(extra)
    keep.update({k: getattr(ctx, k) for k in _CTX_FIELDS})
    out["ctx"] = keep
    return out


# ---------------------------------------------------------------------------
# CHE COSA VUOL DIRE "E' CAMBIATO" (13/09, secondo tempo)
# ---------------------------------------------------------------------------
# La firma serve a una cosa sola: decidere se vale la pena RISCRIVERE la riga.
# Perche' funzioni deve guardare i FATTI e ignorare tutto cio' che si muove da
# solo — altrimenti risponde "cambiato" sempre, e il write-on-change non esiste
# piu'. E' esattamente quello che era successo: dentro ``live`` c'erano
# ``published_at`` / ``published_ts`` (l'orologio) e ``feed_age_s`` /
# ``scanner_age_s`` (eta' che crescono da sole). Con quei quattro campi dentro,
# DUE giri identici a un secondo di distanza producevano due firme diverse e
# due UPSERT da decine di KB: 300 scritture al minuto con cinque partite ferme.
#
# Alla lista si sono aggiunti i campi che si muovono col BOOK: il miglior
# prezzo oscilla di un tick in continuazione, e con lui il "se chiudo ora", le
# posizioni, l'hazard. Sono diagnostica per la scheda, non fatti: viaggiano sul
# battito di pubblicazione (``publish_heartbeat_s``), non su una POST al secondo.
#
# REGOLA DI SICUREZZA — la lista e' una LISTA NERA, non una lista bianca. Un
# campo nuovo che nessuno ha classificato finisce fra i sostanziali: al massimo
# si scrive una volta di troppo. Col criterio opposto un fatto nuovo potrebbe
# non essere scritto MAI, e quello e' un errore che costa soldi.
_LIVE_VOLATILI = frozenset({
    # l'orologio puro: cambiano a ogni giro per costruzione
    "published_at", "published_ts", "feed_age_s", "scanner_age_s",
    # il book e tutto cio' che ne discende (un tick in piu' o in meno)
    "books", "total_matched", "cashout", "posizioni",
    "hazard", "hazard_atlas", "hazard_model", "pressure",
    "p4_market", "p4_model", "p_total_model", "p_total_emp", "p_over45_model",
    "cover_gain_pct", "model_probs", "ko_drift_ticks",
})
# dentro ``ctx`` la stessa cosa: sono spiegazioni per la scheda, non memoria
# dell'engine (nessuna di queste chiavi sta in ``_CTX_FIELDS``, cioe' nessuna
# viene riletta per decidere). ``last_reason`` in particolare contiene prezzi e
# liquidita' — "ultimo ingresso: liquidita 12.40 < 15.00" — quindi cambia a
# ogni tick del book pur dicendo sempre la stessa cosa.
_CTX_VOLATILI = frozenset({"last_reason", "last_cashout", "last_cover_wait", "last_loss_exit"})


def _corpo_sostanziale(row: Dict[str, Any]) -> Dict[str, Any]:
    """La riga senza i campi che cambiano da soli (vedi sopra)."""
    body = {k: v for k, v in row.items() if k != "updated_at"}
    live = body.get("live")
    if isinstance(live, dict):
        body["live"] = {k: v for k, v in live.items() if k not in _LIVE_VOLATILI}
    ctx = body.get("ctx")
    if isinstance(ctx, dict):
        body["ctx"] = {k: v for k, v in ctx.items() if k not in _CTX_VOLATILI}
    return body


def _signature(row: Dict[str, Any]) -> str:
    import hashlib
    import json

    body = _corpo_sostanziale(row)
    return hashlib.md5(json.dumps(body, sort_keys=True, default=str).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Esecuzione di UNA azione (place) via execution.place + riga mike_trades
# ---------------------------------------------------------------------------
def _trade_row(info: F.EventInfo, leg: E.Leg, mode: str, params: Dict[str, Any],
               minute: Optional[int], score: Optional[str],
               closes_trade_id: Optional[int] = None,
               close_reason: Optional[str] = None) -> Dict[str, Any]:
    sid = info.selection_id(leg.market, leg.selection)
    liability = round(leg.size * (leg.price - 1.0), 2) if leg.side == "lay" else round(leg.size, 2)
    meta: Dict[str, Any] = {"phase": "reserved", "leg_ref": leg.ref, "final": bool(leg.final)}
    if leg.role in E.CLOSING_ROLES:
        # H4: la riga di chiusura dice SEMPRE come si e' usciti (contratto UI)
        meta["exit_kind"] = E.exit_kind_for(leg.role, close_reason)
        meta["exit_reason"] = str(close_reason or leg.role)
        if leg.closes_ref:
            meta["closes_ref"] = leg.closes_ref
    row = {
        "event_id": info.event_id, "event_name": info.event_name, "sport": "calcio",
        "strategy": leg.role, "role": leg.role, "cycle_no": int(leg.cycle_no),
        "market_id": info.market_id(leg.market), "market_type": C.OU35 if leg.market == E.MARKET_OU35 else C.OU45,
        "selection_id": int(sid) if sid is not None else None,
        "selection_name": info.selection_name(leg.market, leg.selection),
        "side": leg.side, "mode": mode, "price": leg.price, "size": leg.size, "liability": liability,
        "commission": C.commission_rate(params), "persistence": leg.persistence,
        "minute_at_entry": minute, "score_at_entry": score, "status": "pending", "pnl": 0.0,
        "origin": "manual" if (leg.role == "manual_close" or close_reason == "manual") else "auto",
        "signal_key": leg.ref,
        "meta": meta,
    }
    if closes_trade_id is not None:
        row["closes_trade_id"] = int(closes_trade_id)
    return row


_SCHEMA_ERR_MARKERS = ("42703", "pgrst204", "does not exist", "unknown column", "schema cache")


def _is_missing_column_error(ex: Exception, column: str) -> bool:
    """True SOLO se l'errore dice che QUELLA COLONNA non esiste (C5).

    Un timeout o un errore di rete NON e' un errore di schema: ritentare
    l'insert su un'eccezione qualunque significa rischiare la riga DOPPIA
    (il primo insert potrebbe essere andato a buon fine).
    """
    msg = str(ex).lower()
    return column.lower() in msg and any(m in msg for m in _SCHEMA_ERR_MARKERS)


def _insert_trade_row(db: Any, row: Dict[str, Any], event_id: str) -> Optional[int]:
    """Inserimento tollerante: se la colonna ``closes_trade_id`` non esiste
    ancora (``mike_bot_v2.sql`` non applicata) la riga viene riscritta senza,
    con il riferimento conservato in ``meta.closes_trade_id_pending`` — mai un
    ordine perso per una migrazione mancante. Su QUALUNQUE altro errore
    l'eccezione RISALE: la riserva fallita e' gestita dal chiamante (nessun
    ordine), un retry cieco creerebbe righe doppie."""
    try:
        return db.insert_trade(row)
    except Exception as ex:  # noqa: BLE001
        if "closes_trade_id" not in row or not _is_missing_column_error(ex, "closes_trade_id"):
            raise
        fallback = {k: v for k, v in row.items() if k != "closes_trade_id"}
        meta = dict(fallback.get("meta") or {})
        meta["closes_trade_id_pending"] = row["closes_trade_id"]
        fallback["meta"] = meta
        db.log("schema_warn", {"reason": "closes_trade_id assente (migrazione mike_bot_v2 non applicata)",
                               "err": str(ex)[:120]}, event_id)
        return db.insert_trade(fallback)


def execute_place(*, db: Any, market: Any, info: F.EventInfo, leg: E.Leg, book: Optional[E.Book],
                  mode: str, params: Dict[str, Any], now: datetime, dry: bool,
                  minute: Optional[int] = None, score: Optional[str] = None,
                  feed_fresh: bool = True, closes_trade_id: Optional[int] = None,
                  close_reason: Optional[str] = None,
                  ctx: Optional[E.MatchCtx] = None) -> str:
    """Piazza la gamba (reserve-first). Ritorna 'open' | 'cancelled' | 'pending'.

    Regola prezzo TAKER: il fill avviene al prezzo richiesto solo se ANCORA
    disponibile (back: best_back ≥ prezzo; lay: best_lay ≤ prezzo); altrimenti
    nessun fill (mai piu' ottimista del live). La size e' cappata alla size al best.

    M7 — FEDELTA' PAPER: con il feed STANTIO (riga vecchia e scanner muto) in
    paper non si simula NESSUN fill: i prezzi fermi darebbero un fill fantasma a
    un prezzo che il mercato non ha piu'. In live non cambia nulla (li' risponde
    l'exchange).
    """
    sid = info.selection_id(leg.market, leg.selection)
    mid = info.market_id(leg.market)
    if sid is None or mid is None:
        leg.status = "cancelled"
        db.log("skip", {"leg": leg.ref, "reason": "mercato/selezione assenti"}, info.event_id)
        return "cancelled"

    # ⚠️ IL FRENO, ANCHE QUI (15/09 pomeriggio).
    # Il freno del mattino stava solo su `_piazza_resting_live`, cioe' sulla lay
    # appoggiata. Ma le gambe di CHIUSURA passano di qua, e qui non c'era
    # niente: un errore ripetuto sul piazzamento ha prodotto SESSANTA righe
    # `under_close` identiche in pochi minuti (0,20 € l'una, Trinec v Mlada
    # Boleslav). Ogni giro la riga restava 'pending' in riconciliazione e il
    # motore ne creava una nuova col `seq` successivo.
    # Si frena solo sulle gambe di CHIUSURA: la copertura (`over_cover`) va a
    # tranche, e due righe con lo stesso ruolo e ciclo li' sono legittime.
    # Come il freno del mattino, NON cambia la strategia: la strategia dice UNA
    # gamba di chiusura per ciclo, non sessanta.
    if leg.role in E.CLOSING_ROLES:
        doppia = _gia_appoggiata(db, info.event_id, leg)
        if doppia is not None:
            leg.status = "cancelled"
            _rifiutata(ctx, leg, "gamba di chiusura gia' in volo")
            db.log("place_saltato", {"leg": leg.ref, "role": leg.role, "critical": True,
                                     "reason": "gamba_di_chiusura_gia_in_volo",
                                     "gia_in_volo": doppia.get("id"),
                                     "nota": "una gamba di chiusura con lo stesso ruolo e "
                                             "ciclo e' gia' in attesa: non se ne piazza "
                                             "una seconda"}, info.event_id)
            logger.critical("[mike] %s: NON piazzo %s, la riga #%s con lo stesso ruolo e "
                            "ciclo e' gia' pending", info.event_id, leg.ref, doppia.get("id"))
            return "cancelled"
    # ⚠️ IL FRENO DELLA COPERTURA, FAIL-CLOSED (ordine dell'utente 17/09).
    # E' la SECONDA barriera: la prima e' ``engine._freno_copertura``, che toglie
    # l'azione dalla decisione. Se un percorso qualunque arrivasse comunque fin
    # qui con una copertura mentre il freno e' scattato, nessun ordine parte.
    # Riguarda SOLO la copertura (ruolo ``over_cover``), che e' un INGRESSO:
    # uscite, green-up e chiusure passano sempre — la lezione del 15/09, quando
    # il freno live aveva frenato anche le uscite.
    if leg.role == "over_cover" and ctx is not None:
        fermo = E.copertura_bloccata(ctx)
        if fermo is not None:
            leg.status = "cancelled"
            db.log("skip", {"leg": leg.ref, "role": leg.role,
                            "reason": "copertura_bloccata",
                            "error_code": fermo.get("error_code"),
                            "conteggio": int(fermo.get("conteggio") or 0),
                            "max": int(fermo.get("max") or 0),
                            "stato_freno": E.COVER_BLOCCATA,
                            "critical": True}, info.event_id)
            logger.critical("[mike] %s: copertura FERMA (%s x%s): nessun tentativo",
                            info.event_id, fermo.get("error_code"), fermo.get("conteggio"))
            return "cancelled"
    if book is None or book.status != "OPEN":
        leg.status = "cancelled"
        # M-17 (ordine dell'utente 17/09) — SOSPESO/CHIUSO/IGNOTO si chiamano per
        # nome anche qui: "book non OPEN" non diceva se il mercato riaprira'.
        db.log("skip", {"leg": leg.ref, "role": leg.role,
                        "reason": f"mercato {E.stato_mercato(book)}",
                        "stato_mercato": E.stato_mercato(book),
                        "market": leg.market}, info.event_id)
        return "cancelled"
    if mode == "paper" and not feed_fresh:
        leg.status = "cancelled"
        db.log("no_fill", {"leg": leg.ref, "role": leg.role, "reason": "feed_stantio",
                           "wanted": leg.price, "side": leg.side}, info.event_id)
        return "cancelled"
    if leg.side == "back":
        avail_price, avail_size = book.best_back, book.back_size
        ok_price = avail_price is not None and avail_price >= leg.price - 1e-9
    else:
        avail_price, avail_size = book.best_lay, book.lay_size
        ok_price = avail_price is not None and avail_price <= leg.price + 1e-9
    if not ok_price:
        leg.status = "cancelled"
        # ⚠️ 16/09 — IL MERCATO HA GIA' RISPOSTO NO A QUESTA DOMANDA.
        # Qui non nasce nessun ordine (la riga di riserva viene dopo), quindi il
        # freno anti-duplicato — che guarda le righe 'pending' di `mike_trades` —
        # non ha niente da trovare: il motore rifaceva la stessa identica
        # richiesta a ogni giro. Scriverlo sulla gamba e' l'unico modo che il
        # motore ha di saperlo (`engine.tentativo_gia_rifiutato`).
        _rifiutata(ctx, leg, f"prezzo non disponibile ({avail_price})")
        # CERT. 12/09 — mancavano ``role`` e ``size``: in UI la riga diceva
        # "— lay non abbinato" senza dire QUALE gamba (ingresso, green, copertura,
        # chiusura) e per quanto. Osservati 58 casi in un giorno, tutti muti.
        db.log("no_fill", {"leg": leg.ref, "role": leg.role, "size": leg.size,
                           "wanted": leg.price, "available": avail_price,
                           "size_disponibile": avail_size,
                           "side": leg.side}, info.event_id)
        return "cancelled"
    if dry:
        leg.status = "cancelled"
        db.log("would_place", {"leg": leg.ref, "role": leg.role, "side": leg.side, "price": leg.price,
                               "size": leg.size, "persistence": leg.persistence}, info.event_id)
        return "cancelled"
    if leg.side == "back" and not params.get("exact_sizes", True) and E.needs_submin(leg.side, leg.size):
        # importi esatti SPENTI (scelta esplicita dalla UI): le aperture BACK
        # vengono legalizzate (.it min 2.00, passo 0.50). Con exact_sizes=True —
        # il default — la size resta al CENTESIMO e viene piazzata davvero: in
        # paper dal fill simulato, in live dal place-and-trim.
        legal, _ = E.legalize_back_size(leg.size, str(params.get("cover_rounding", "ceil")))
        db.log("size_legalized", {"leg": leg.ref, "from": leg.size, "to": legal}, info.event_id)
        leg.size = legal
    row = _trade_row(info, leg, mode, params, minute, score, closes_trade_id, close_reason)
    try:
        trade_id = _insert_trade_row(db, row, info.event_id)
    except Exception as ex:  # noqa: BLE001 — riserva fallita: nessun ordine
        leg.status = "cancelled"
        db.log("error", {"leg": leg.ref, "reason": "reserve_failed", "err": str(ex)[:160]}, info.event_id)
        return "cancelled"
    exec_params = dict(params)
    exec_params["execution_mode"] = "rest" if not C.env_bool("MIKE_USE_FLUMINE_QUEUE", False) else "auto"
    # ⚠️ 15/09 — «QUESTA GAMBA CHIUDE» VA DETTO A CHI ESEGUE, e Mike non lo diceva.
    #
    # `execution.place` riconosce una chiusura COSI':
    #     is_closing = bool(meta.get("cashout") or meta.get("closes_trade_id"))
    # ma Mike scriveva `closes_trade_id` nella COLONNA della riga e passava il
    # solo `row["meta"]`, che quella chiave non l'ha mai avuta. Per chi eseguiva,
    # NESSUNA chiusura di Mike era una chiusura. Ancora una volta: un dato
    # scritto in un posto e letto in un altro. Due conseguenze, tutte e due sui
    # soldi:
    #
    #   1. `sotto_minimo = ... and not is_closing` restava VERO, quindi una
    #      chiusura da 0,20 € finiva nel place-and-trim invece di essere piazzata
    #      diretta. Il parcheggio della lay (il minimo a quota 1,01) su una
    #      selezione dove abbiamo gia' un back RIDUCE la liability, e Betfair lo
    #      misura con la banda del profit-ratio: rifiutato, `INVALID_PROFIT_RATIO`.
    #      Ogni giro. E' il loop delle 60 righe `under_close` del 15/09.
    #   2. `blocco = None if is_closing else _live_brake()` — il freno live si
    #      applicava anche alle USCITE di Mike. Col freno attivo una posizione
    #      aperta non si sarebbe potuta chiudere: l'opposto della protezione,
    #      e il commento di `execution.place` lo dice a chiare lettere.
    #
    # Safe e Omega lo fanno giusto da sempre (`execution.close_position` mette
    # `closes_trade_id` NEL META). Mike era l'unico fuori riga, di nuovo.
    meta_exec = dict(row["meta"])
    if row.get("closes_trade_id") is not None:
        meta_exec["closes_trade_id"] = int(row["closes_trade_id"])
    elif leg.role in E.CLOSING_ROLES:
        # la colonna puo' mancare (migrazione non applicata: il riferimento resta
        # in `meta.closes_trade_id_pending`). Il RUOLO pero' lo sappiamo sempre, e
        # una gamba di chiusura e' una chiusura anche senza il numero della riga
        # che chiude: `-1` dice «chiude, riferimento ignoto» e resta un numero,
        # perche' chi legge questa chiave la usa come vero/falso ma se la ritrova
        # scritta nel meta della riga.
        meta_exec["closes_trade_id"] = int(
            (row.get("meta") or {}).get("closes_trade_id_pending") or -1)
    if leg.role == "over_cover" and ctx is not None:
        # L'OROLOGIO DEL RITMO MINIMO si fa partire PRIMA della chiamata: e' il
        # TENTATIVO che consuma una richiesta a Betfair e un bet delay, non il
        # suo esito. Se la risposta non arrivasse mai, il prossimo giro deve
        # comunque aspettare ``cover_retry_min_s``.
        E.segna_tentativo_copertura(ctx, now.timestamp())
    out = X.place(db=db, market=market, mode=mode, event_id=info.event_id, market_id=mid,
                  selection_id=int(sid), side=leg.side, price=leg.price, size=leg.size,
                  best_size=avail_size, ladder=(), client_ref=f"mike-t{trade_id}",
                  trade_id=int(trade_id), meta=meta_exec, now=now, params=exec_params)
    if out.status == "open":
        leg.matched = float(out.size)
        leg.avg_price = float(out.price or leg.price)
        leg.status = "open"
        try:
            # C.12a — la conferma porta anche il CHIESTO e il RESIDUO: ``size``
            # viene sovrascritta con l'abbinato, e senza le colonne nuove il
            # numero che il bot aveva chiesto sparirebbe per sempre.
            X.aggiorna_trade(
                db, int(trade_id),
                campi={"status": "open", "price": out.price, "size": out.size,
                       "liability": X.liability_of(leg.side, out.size, out.price or 0.0),
                       "bet_id": out.bet_id,
                       "meta": {**row["meta"], "phase": "open", "fill": out.fill_note}},
                consapevolezza=out.consapevolezza)
        except Exception as ex:  # noqa: BLE001
            logger.critical("[mike] conferma DB FALLITA (trade %s): %s", trade_id, str(ex)[:160])
        db.log("place", {"leg": leg.ref, "trade_id": trade_id, "role": leg.role, "side": leg.side,
                         "price": out.price, "size": out.size, "mode": mode, "note": out.fill_note,
                         "size_requested": out.size_requested,
                         "size_remaining": out.size_remaining},
               info.event_id)
        return "open"
    if out.status == "pending":
        # C3 — esito IGNOTO (eccezione dopo l'invio): la gamba NON e' "non
        # piazzata". Resta in riconciliazione: conta nel rischio, blocca i nuovi
        # ingressi, MAI cancellata per TTL.
        if str(out.fill_note or "").startswith("place_exception_reconciling"):
            leg.status = E.STATUS_RECONCILE
            logger.critical("[mike] %s: gamba %s con esito IGNOTO → riconciliazione (nessun rientro)",
                            info.event_id, leg.ref)
            db.log("reconcile_pending", {"leg": leg.ref, "trade_id": trade_id, "role": leg.role,
                                         "side": leg.side, "price": leg.price, "size": leg.size,
                                         "note": out.fill_note, "critical": True}, info.event_id)
            return "pending_reconcile"
        db.log("place_pending", {"leg": leg.ref, "trade_id": trade_id, "note": out.fill_note}, info.event_id)
        return "pending"
    leg.status = "cancelled"
    # 16/09 — rifiuto DICHIARATO di Betfair (FOK ucciso, codice d'errore,
    # istruzione non accettata): nessun ordine e' a mercato e la risposta e'
    # gia' arrivata. La stessa richiesta identica non si rifa (fail-closed: la
    # Costituzione non dice «riprova» per questo caso, §3 Fase 1 e Fase 6
    # descrivono UNA uscita appoggiata per ciclo).
    _rifiutata(ctx, leg, f"rifiutata da Betfair ({out.error_code or out.fill_note})")
    try:
        db.update_trade(int(trade_id), status="error", meta={**row["meta"], "reason": out.fill_note})
    except Exception:  # noqa: BLE001
        pass
    # C.12a — se Betfair ha dato un CODICE, si scrive col kind dedicato (lo
    # stesso ``place_rifiutato`` gia' in uso per la lay appoggiata): un rifiuto
    # per INSUFFICIENT_FUNDS e uno per INVALID_PROFIT_RATIO non sono la stessa
    # cosa, e finora erano entrambi uno ``skip`` muto.
    # ⚠️ ORDINE DELL'UTENTE 17/09 (reperto 25) — IL RIFIUTO DELLA COPERTURA SI
    # CONTA. 104 rifiuti identici in un'ora, uno ogni ~5 s, e nessuno li contava:
    # il conteggio per CODICE D'ERRORE e' quello che permette di fermarsi.
    freno: Optional[Dict[str, Any]] = None
    if leg.role == "over_cover" and ctx is not None:
        freno = E.registra_rifiuto_copertura(
            ctx, error_code=out.error_code, motivo=str(out.fill_note or ""),
            ref=leg.ref, now=now.timestamp(), params=params)
    if out.error_code:
        db.log("place_rifiutato", {"leg": leg.ref, "trade_id": trade_id, "role": leg.role,
                                   "side": leg.side, "price": leg.price, "size": leg.size,
                                   "error_code": out.error_code, "critical": True,
                                   "reason": out.fill_note,
                                   # il CONTEGGIO in chiaro: un rifiuto isolato e il
                                   # centesimo di fila non sono la stessa notizia
                                   "conteggio": (None if freno is None
                                                 else int(freno.get("conteggio") or 0)),
                                   "max": (None if freno is None
                                           else int(freno.get("max") or 0))}, info.event_id)
    if freno is not None and freno.get("bloccata"):
        # IL FRENO E' SCATTATO: da qui la copertura non si ritenta piu' finche'
        # non interviene l'utente («Riprendi») o finche' Betfair non risponde
        # con un codice DIVERSO. E' una notizia critica, non un dettaglio.
        db.log("error", {"reason": "copertura_bloccata", "leg": leg.ref,
                         "role": leg.role, "trade_id": trade_id,
                         "error_code": freno.get("error_code"),
                         "conteggio": int(freno.get("conteggio") or 0),
                         "max": int(freno.get("max") or 0),
                         "stato_freno": E.COVER_BLOCCATA, "critical": True,
                         "nota": "copertura Over 4.5 FERMATA dopo rifiuti identici "
                                 "ripetuti: serve un intervento (Riprendi) o un "
                                 "codice d'errore diverso"}, info.event_id)
        logger.critical("[mike] %s: COPERTURA BLOCCATA dopo %s rifiuti '%s' (%s)",
                        info.event_id, freno.get("conteggio"), freno.get("error_code"), leg.ref)
    db.log("skip", {"leg": leg.ref, "trade_id": trade_id, "reason": out.fill_note,
                    "error_code": out.error_code}, info.event_id)
    return "cancelled"


# ---------------------------------------------------------------------------
# Settlement a mercato chiuso: REST listMarketBook (runner WINNER/LOSER)
# ---------------------------------------------------------------------------
def market_winner(book: Optional[dict], market: str, info: F.EventInfo) -> Optional[str]:
    """Selezione dichiarata WINNER dai runner del book, o None se non regolato."""
    if not book or str(book.get("status") or "").upper() != "CLOSED":
        return None
    for r in book.get("runners") or []:
        if str(r.get("status") or "").upper() == "WINNER":
            try:
                sid = int(r.get("selection_id"))
            except (TypeError, ValueError):
                continue
            if sid == info.selection_id(market, E.SEL_UNDER):
                return E.SEL_UNDER
            if sid == info.selection_id(market, E.SEL_OVER):
                return E.SEL_OVER
    return None


def final_total_from_books(b35: Optional[dict], b45: Optional[dict], info: F.EventInfo) -> Optional[int]:
    """Somma gol RAPPRESENTATIVA (3 | 4 | 5) dagli esiti dei runner, o None se non regolati."""
    w35 = market_winner(b35, E.MARKET_OU35, info)
    w45 = market_winner(b45, E.MARKET_OU45, info)
    if w35 == E.SEL_UNDER:
        return 3
    if w45 == E.SEL_OVER:
        return 5
    if w35 == E.SEL_OVER and w45 == E.SEL_UNDER:
        return 4
    return None


# Stati di mercato che Betfair usa per un mercato ANNULLATO. 'INACTIVE' NON c'e':
# e' il mercato non ancora attivo (pre-apertura), non un void — trattarlo come
# void azzerava il P&L di una partita viva (C4, review 11/09).
_VOID_MARKET_STATUS = ("VOID", "VOIDED")
_VOID_RUNNER_STATUS = ("REMOVED", "REMOVED_VACANT", "VOID", "VOIDED")


def market_voided(book: Optional[dict]) -> bool:
    """M9 — MERCATO annullato (partita abbandonata / mercato cancellato): Betfair
    non dichiara nessun vincitore e le scommesse su QUEL mercato sono nulle.

    Segnali: stato del mercato esplicitamente void, oppure mercato CLOSED senza
    NESSUN runner WINNER e con tutti i runner rimossi/annullati. Il giudizio e'
    PER MERCATO: l'altra linea viene regolata normalmente dai suoi runner (C4).
    """
    if not book:
        return False
    status = str(book.get("status") or "").upper()
    if status in _VOID_MARKET_STATUS:
        return True
    runners = book.get("runners") or []
    if status != "CLOSED" or not runners:
        return False
    states = [str(r.get("status") or "").upper() for r in runners]
    if any(s == "WINNER" for s in states):
        return False
    return all(s in _VOID_RUNNER_STATUS for s in states)


def settle_plan(b35: Optional[dict], b45: Optional[dict], info: F.EventInfo
                ) -> "tuple[Optional[Dict[str, Optional[str]]], Dict[str, Any]]":
    """(winners, telemetria) per il regolamento PER MERCATO (C4).

    ``winners[market]`` = selezione vincente, oppure ``None`` se il mercato e'
    ANNULLATO (solo le sue gambe valgono zero). Ritorna ``None`` se almeno un
    mercato non e' ne' regolato ne' annullato: in quel caso si aspetta ancora
    (nessun P&L inventato, nessun azzeramento globale).
    """
    books = {E.MARKET_OU35: b35, E.MARKET_OU45: b45}
    winners: Dict[str, Optional[str]] = {}
    voided: List[str] = []
    for market, book in books.items():
        if market_voided(book):
            winners[market] = None
            voided.append(market)
            continue
        w = market_winner(book, market, info)
        if w is None:
            return (None, {"voided": voided})
        winners[market] = w
    return (winners, {"voided": voided, "winners": dict(winners)})


# ---------------------------------------------------------------------------
# Ciclo
# ---------------------------------------------------------------------------
_LAST_AGG: Dict[str, Any] = {}


def _aggregates_cached(db: Any, now: datetime, params: Dict[str, Any],
                       forza: bool = False) -> Dict[str, Any]:
    """Gli aggregati, ricalcolati al massimo ogni ``aggregates_cache_s``.

    Governano lo stop giornaliero e i numeri in cima alla pagina: nessuno dei
    due e' una decisione al secondo, e la RPC che li calcola scorre l'intera
    ``mike_trades``. ``forza=True`` dopo un'azione: se qualcosa e' appena
    cambiato il numero va rifatto subito.
    """
    ora = now.timestamp()
    ttl = float(params.get("aggregates_cache_s") or 0.0)
    if not forza and _CACHE_AGGREGATI.fresco(ora, ttl):
        return _CACHE_AGGREGATI.valore
    return _CACHE_AGGREGATI.metti(_aggregates(db, now), ora)


def _aggregates(db: Any, now: datetime) -> Dict[str, Any]:
    """Aggregati con MEMORIA dell'ultima lettura buona.

    Una lettura fallita non deve valere "zero": con ``{}`` lo STOP GIORNALIERO
    si spegneva (``realized_today`` = 0 → il bot continuava ad aprire dopo aver
    gia' perso il massimo) e i KPI della UI (P&L, posizioni aperte, V/P)
    lampeggiavano a zero. Si riusa l'ultimo valore noto e si logga il guasto.
    """
    try:
        agg = db.aggregates(now)
        if isinstance(agg, dict) and agg:
            _LAST_AGG["v"] = dict(agg)
            return agg
        raise ValueError("aggregati vuoti")
    except Exception as ex:  # noqa: BLE001
        logger.warning("[mike] aggregates KO: %s", str(ex)[:160])
        last = _LAST_AGG.get("v")
        return dict(last) if isinstance(last, dict) else {}


def _scanner_age(db: Any, now: float) -> Optional[float]:
    st = db.scanner_status()
    if not st:
        return None
    ts = F.parse_iso_epoch(st.get("updated_at"))
    return None if ts is None else max(0.0, now - ts)


def _live_exit_override(params: Dict[str, Any], mode: str) -> Dict[str, Any]:
    """H3 — in LIVE la lay APPOGGIATA non e' cablata su NESSUN percorso: ne' REST
    (servirebbe un ordine senza FOK + polling) ne' coda flumine (la gamba
    resting non passa da ``execution.place``, viene solo riservata su
    ``mike_trades``). Finche' non esiste davvero (F6) in live si usa SEMPRE la
    chiusura taker: mai un fill simulato su soldi veri, con o senza
    ``MIKE_USE_FLUMINE_QUEUE``.

    12/09 — va applicato sul mode della PARTITA (``mike_events.mode``), non solo
    su quello del control: una partita armata in LIVE mentre il control e' gia'
    tornato in paper riceveva parametri ``pre_exit_mode='resting'`` su soldi
    veri (l'engine pianificava una lay appoggiata che il servizio poi annullava,
    lasciando la posizione senza green-up).
    """
    # 14/09 — CABLATO. L'uscita appoggiata in live adesso esiste davvero
    # (``place_order_live(fill_or_kill=False)`` + riconciliazione dal book
    # ordini), quindi il dirottamento NON si applica piu' per difetto: in live
    # il bot piazza lo STESSO ordine che piazza in paper, allo stesso prezzo,
    # con lo stesso tipo di esecuzione. Era l'unica cosa che rendeva la demo
    # diversa dal live su questa strategia.
    # Resta la valvola ``live_resting_enabled``: spenta, si torna al
    # dirottamento di prima. Serve a poter tornare indietro dalla UI senza
    # toccare il codice, non a cambiare strategia.
    # ⚠️ 16/09 — questa valvola NON tocca piu' ``ko_green``: per ordine
    # dell'utente l'uscita al fischio e' appoggiata in ogni modalita' e
    # ``_is_resting_leg`` non guarda piu' ``pre_exit_mode`` per quel ruolo.
    # Qui resta cio' che governa ``under_green`` e ``reentry_green``.
    if (str(mode) == "live" and str(params.get("pre_exit_mode")) == "resting"
            and not bool(params.get("live_resting_enabled", True))):
        return dict(params, pre_exit_mode="taker")
    return params


def _params_for(params: Dict[str, Any], running: bool, mode: str = "paper") -> Dict[str, Any]:
    """A bot fermo: NESSUN nuovo ingresso, protezioni e uscite sempre attive."""
    p = dict(_live_exit_override(params, mode))
    if running:
        return p
    p["pre_enabled"] = False
    p["reentry_enabled"] = False
    p["last_entry_persist"] = False
    return p


def _log_throttled(db: Any, extra: Dict[str, Any], params: Dict[str, Any], now_ts: float,
                   kind: str, payload: Dict[str, Any], event_id: Optional[str] = None) -> bool:
    """M3/H5 — ``skip_log_interval_s`` CABLATO: lo STESSO motivo sulla stessa
    partita non viene riscritto piu' di una volta ogni N secondi (prima i log
    ripetitivi riempivano ``mike_activity`` a ogni ciclo).

    M7 (review): un evento CRITICO (``payload['critical']``) usa un intervallo
    molto piu' corto (``_CRITICAL_LOG_EVERY_S``): una linea mancante o un ordine
    a esito ignoto non possono restare muti 5 minuti.
    """
    every = float(params.get("skip_log_interval_s") or 300)
    if payload.get("critical"):
        every = min(every, _CRITICAL_LOG_EVERY_S)
    seen: Dict[str, Any] = dict(extra.get("log_seen") or {})
    key = f"{kind}:{payload.get('reason') or payload.get('leg') or ''}"
    last = float(seen.get(key) or 0.0)
    if now_ts - last < every:
        return False
    seen[key] = now_ts
    # spurgo: mai un dizionario che cresce senza fine
    extra["log_seen"] = {k: v for k, v in seen.items() if now_ts - float(v or 0.0) < every * 4}
    db.log(kind, payload, event_id)
    return True


def _rifiutata(ctx: Optional[E.MatchCtx], leg: E.Leg, motivo: str) -> None:
    """Scrive NEL CTX che il mercato ha rifiutato questa richiesta.

    ⚠️ 16/09 — E' la meta' mancante del dialogo `ctx` <-> riga <-> mercato.
    Fino a ieri un rifiuto finiva solo in `mike_activity` (`no_fill`, `skip`,
    `place_rifiutato`): la gamba diventava 'cancelled', indistinguibile da una
    annullata dal motore, e il motore rifaceva la stessa domanda al giro dopo.
    Sulla registrazione 35674515 in `taker` sono 531 riproposizioni identiche
    di `reentry_green` (lay 10,11 @ 1,75) contro 3 ordini davvero piazzati.

    Si scrive SOLO dove nessun ordine e' nato e la risposta e' definitiva
    (prezzo non disponibile, rifiuto dichiarato di Betfair, freno
    anti-duplicato). MAI su un esito IGNOTO — li' comanda la riconciliazione
    (§4.11) — e mai in `dry` (li' non si e' nemmeno chiesto niente al mercato).

    Non cambia nessuna regola di strategia: prezzi, soglie, quando si esce e
    quante gambe prevede la spec restano quelli. Cambia solo che il motore SA.

    ``ctx`` puo' mancare solo nei test che chiamano ``execute_place`` da solo:
    li' non c'e' nessun motore da frenare, e il rifiuto resta nelle attivita'.
    """
    if ctx is None:
        return
    E.registra_rifiuto(ctx, leg, motivo)


def _is_resting_leg(leg: E.Leg, params: Dict[str, Any]) -> bool:
    """Lay di green-up appoggiata sul book (take-profit): NON e' un ordine taker.

    ⚠️ ORDINE DELL'UTENTE 16/09 — ``ko_green`` E' APPOGGIATA IN OGNI MODALITA'.
    «Mettiamola appoggiata allora, cosi' risparmiamo una marea di chiamate»:
    fino a ieri l'uscita al fischio seguiva ``pre_exit_mode`` e in `taker`
    veniva RI-PRESENTATA ogni ``ko_green_retry_s``, cioe' 25-32 chiamate REST
    per una sola uscita (misurato sulla registrazione 35674515). Adesso quel
    ruolo non consulta piu' il parametro: la lay si appoggia e si aspetta.
    ``under_green`` e ``reentry_green`` restano governate da ``pre_exit_mode``.
    """
    if leg.final or leg.side != "lay":
        return False
    if leg.role == "ko_green":
        return True
    return (leg.role in ("under_green", "reentry_green")
            and str(params.get("pre_exit_mode")) == "resting")


def _gia_appoggiata(db: Any, event_id: str, leg: E.Leg,
                    cache: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> Optional[dict]:
    """C'e' GIA' una gamba appoggiata in attesa, per lo stesso ruolo e ciclo?

    ⚠️ 15/09 — IL FRENO CHE MANCAVA, e che e' costato un loop con soldi veri.
    Il 15/09 Mike ha piazzato TRENTADUE volte lo stesso green-up (lay 5,07 @
    1,43) su Beijing Guoan v Pohang Steelers, una ogni tre secondi, arrivando a
    61 EUR impegnati su un budget di 35. La catena era:

        piazza la lay appoggiata  ->  `_segui_resting_live` la cerca su Betfair
        per `customerOrderRef` e NON la trova  ->  la marca
        'reconciled_not_placed'  ->  il motore non vede piu' nessuna gamba di
        green-up  ->  ne crea una NUOVA con un ref nuovo  ->  si ricomincia.

    Ogni anello aveva un suo perche'; quello che mancava era la domanda piu'
    semplice: «ne ho gia' una in volo?». La strategia dice UNA lay appoggiata,
    non trentadue: questo freno non la cambia, la fa rispettare.

    Si confronta ruolo + ciclo + mercato + lato, NON il ref: il ref e' diverso a
    ogni giro, ed e' esattamente il motivo per cui il duplicato passava.
    """
    righe = _event_rows(db, event_id, cache)
    if righe is None:
        # FAIL-CLOSED: righe illeggibili = non sappiamo se ce n'e' gia' una in
        # volo, e nel dubbio non si piazza. E' la stessa regola di
        # `_trade_unknown_outcome`: un dubbio non si risolve mai mandando un
        # ordine reale in piu'.
        return {"id": None, "role": leg.role, "illeggibile": True}
    for r in righe:
        if str(r.get("status")) != "pending":
            continue
        if str(r.get("role")) != str(leg.role):
            continue
        if int(r.get("cycle_no") or 0) != int(leg.cycle_no):
            continue
        if str(r.get("side")) != str(leg.side):
            continue
        return r
    return None


def _piazza_resting_live(*, db: Any, market: Any, info: Any, leg: E.Leg, mode: str,
                         params: Dict[str, Any], minuto: Optional[int], score: Optional[str],
                         chiude: Optional[int], motivo: Optional[str],
                         ev: Dict[str, Any], ctx: Optional[E.MatchCtx] = None) -> None:
    """Piazza in LIVE la lay appoggiata e la lascia sul book.

    Nessuna differenza di STRATEGIA rispetto al paper: stessa selezione, stesso
    lato, stesso prezzo, stessa size. Cambia solo che i soldi sono veri — che e'
    l'unica differenza che ci deve essere.

    ORDINE DELLE OPERAZIONI, e conta: prima si SCRIVE la riga di riserva, poi si
    piazza. Se il processo muore in mezzo resta una riga 'pending' che la
    riconciliazione ritrova e chiude; l'ordine contrario — piazzare e morire
    prima di scrivere — lascerebbe su Betfair un ordine VIVO che nessuno sa di
    avere, e piu' tardi si abbinerebbe mentre il bot e' gia' rientrato:
    posizione doppia con soldi veri. Fra i due rischi si sceglie sempre quello
    che si puo' riparare.
    """
    eid = str(ev["event_id"])

    # ⚠️ IL FRENO (15/09): mai due gambe protettive identiche in volo.
    doppia = _gia_appoggiata(db, eid, leg)
    if doppia is not None:
        leg.status = "cancelled"
        db.log("place_saltato", {"leg": leg.ref, "role": leg.role, "critical": True,
                                 "reason": "gamba_gia_appoggiata",
                                 "gia_in_volo": doppia.get("id"),
                                 "nota": "una gamba con lo stesso ruolo e ciclo e' gia' "
                                         "in attesa: non se ne piazza una seconda"}, eid)
        logger.critical("[mike] %s: NON piazzo %s, la riga #%s con lo stesso ruolo e "
                        "ciclo e' gia' pending", eid, leg.ref, doppia.get("id"))
        return

    try:
        trade_id = _insert_trade_row(
            db, _trade_row(info, leg, mode, params, minuto, score, chiude, motivo), eid)
    except Exception as ex:  # noqa: BLE001 — riserva fallita: NESSUN ordine reale
        leg.status = "cancelled"
        db.log("error", {"leg": leg.ref, "reason": "reserve_failed", "err": str(ex)[:160]}, eid)
        return
    # ⚠️ 15/09 — IL RIFERIMENTO DELL'ORDINE E' `mike-t<id>`, QUI COME OVUNQUE.
    # Fino a oggi questa era l'UNICA gamba di Mike piazzata con un ref diverso
    # (`leg.ref`, del tipo `under_green-0-2`) mentre la riconciliazione cercava
    # `mike-t<id>`: l'ordine VIVO non veniva riconosciuto ne' fra i correnti ne'
    # fra i regolati, passata la grazia la riga andava in 'error', e il freno
    # anti-duplicato — che guarda le righe 'pending' — smetteva di coprire. Al
    # giro dopo il motore piazzava un SECONDO green-up. Terzo ramo dello stesso
    # loop, e la stessa radice: un identificativo scritto in un modo e letto in
    # un altro.
    # `leg.ref` non poteva fare da identificativo: vale `{ruolo}-{ciclo}-{seq}`
    # con `seq` che conta PER PARTITA, quindi due partite diverse possono
    # esibire lo stesso ref. Il `mike-t<id>` viene dall'id di riga: unico.
    ref_ordine = f"mike-t{int(trade_id)}" if trade_id is not None else str(leg.ref)
    try:
        res = market.place_order_live(
            market_id=info.market_id(leg.market),
            selection_id=info.selection_id(leg.market, leg.selection),
            price=float(leg.price), size=float(leg.size), event_id=eid,
            side="lay", customer_ref=ref_ordine, fill_or_kill=False)
    except Exception as ex:  # noqa: BLE001
        # Esito IGNOTO: l'ordine POTREBBE esistere. Non si annulla la riga e non
        # si rientra — si manda in riconciliazione, che e' l'unico modo onesto
        # di dire "non lo so" senza scommettere due volte.
        leg.status = E.STATUS_RECONCILE
        logger.critical("[mike] %s: resting live a esito IGNOTO (%s) -> riconciliazione",
                        eid, str(ex)[:120])
        db.log("reconcile_pending", {"leg": leg.ref, "role": leg.role,
                                     "reason": "resting_place_unknown", "critical": True}, eid)
        return
    # ⚠️ 15/09 — L'ESITO SI LEGGE, PRIMA DI TUTTO IL RESTO.
    # `place_order_live` torna `ok=False` quando Betfair RIFIUTA l'istruzione
    # (report o istruzione con status != SUCCESS). L'esito IGNOTO — timeout,
    # nessun report — non arriva mai fin qui: viene sollevato e lo raccoglie il
    # blocco sopra. Quindi `ok=False` significa una cosa sola, e precisa:
    # l'ordine NON e' a mercato.
    # Prima `ok` non veniva letto DA NESSUNA PARTE: su un rifiuto il codice
    # proseguiva, scriveva `place_resting` e lasciava la riga 'pending'. Il bot
    # credeva di avere una copertura che non esisteva e il back reale da 5 EUR
    # restava scoperto — Trinec v Mlada Boleslav, 13:43:33 del 15/09.
    bet_id = res.bet_id
    matched = float(res.size_matched or 0.0)
    if not res.ok:
        if bet_id or matched > 0:
            # Rifiuto DICHIARATO ma con tracce di un ordine (un identificativo,
            # un abbinamento): i due racconti non tornano e non si sceglie da
            # soli quale credere. Va in riconciliazione, che lo chiede a Betfair.
            leg.status = E.STATUS_RECONCILE
            logger.critical("[mike] %s: %s rifiutata MA con tracce (bet_id=%s matched=%.2f) "
                            "-> riconciliazione", eid, leg.ref, bet_id, matched)
            db.log("reconcile_pending", {"leg": leg.ref, "role": leg.role, "critical": True,
                                         "reason": "resting_rifiutata_con_tracce",
                                         "bet_id": bet_id, "matched": round(matched, 2),
                                         "order_status": res.order_status}, eid)
            return
        # Rifiuto pulito: nessun ordine esiste. La riga si CHIUDE subito, cosi'
        # il motore puo' riproporre la copertura al giro dopo; una riga 'pending'
        # eterna terrebbe alzato il freno anti-duplicato su una gamba mai nata.
        leg.status = "cancelled"
        logger.critical("[mike] %s: Betfair ha RIFIUTATO la lay appoggiata %s (%s): "
                        "nessun ordine a mercato", eid, leg.ref, res.order_status)
        db.log("place_rifiutato", {"leg": leg.ref, "role": leg.role, "critical": True,
                                   "reason": "resting_rifiutata",
                                   "order_status": res.order_status,
                                   # C.12a — il CODICE di Betfair, non solo lo stato
                                   "error_code": getattr(res, "error_code", None),
                                   "price": leg.price, "size": leg.size,
                                   "nota": "la copertura NON e' a mercato: la riga si chiude "
                                           "e il motore la ripropone"}, eid)
        _mark_trade_cancelled(db, eid, leg, "resting_rifiutata")
        # 16/09 — IL MOTORE DEVE SAPERLO. Nessun ordine e' nato e la risposta e'
        # definitiva: senza questo, tolto il ritmo di ri-presentazione di
        # ``ko_green``, la stessa lay rifiutata verrebbe riproposta a ogni giro.
        _rifiutata(ctx, leg, f"resting rifiutata ({res.order_status})")
        return
    # ⚠️ IL BET_ID SI SCRIVE SEMPRE (15/09), non solo quando l'ordine si abbina.
    # Un ordine appoggiato che resta sul book e' il caso NORMALE: senza il suo
    # identificativo la riconciliazione puo' cercarlo solo per
    # `customerOrderRef`, e se quella ricerca fallisce la riga risulta «mai
    # piazzata» mentre su Betfair l'ordine e' vivo. E' l'anello da cui e' partito
    # il loop del 15/09.
    if bet_id:
        try:
            r0 = _trade_row_for_leg(db, eid, leg)
            if r0 is not None:
                db.update_trade(int(r0["id"]), bet_id=str(bet_id))
        except Exception as ex:  # noqa: BLE001 — il bet_id non si perde in silenzio
            db.log("error", {"leg": leg.ref, "reason": "bet_id_non_salvato",
                             "err": str(ex)[:160], "critical": True}, eid)
    else:
        db.log("error", {"leg": leg.ref, "reason": "resting_senza_bet_id", "critical": True,
                         "nota": "Betfair non ha restituito un identificativo: la riga "
                                 "resta pending e la riconciliazione la risolve"}, eid)

    if matched > 0:
        # puo' succedere: il book si e' mosso fra la decisione e il piazzamento.
        # E' un abbinamento VERO e va contabilizzato subito.
        # ⚠️ 15/09 — IL PREZZO E' `avg_price_matched`. Qui si leggeva
        # `avg_price`, un campo che su `PlaceResult` NON ESISTE: `getattr`
        # tornava sempre `None` e il prezzo ricadeva su quello CHIESTO. Un
        # abbinamento immediato veniva contabilizzato al prezzo sbagliato — e
        # da li' passano liability, P&L e cash-out. Nessun errore, solo numeri
        # falsi: la stessa firma degli altri due difetti.
        leg.matched = matched
        leg.avg_price = float(res.avg_price_matched or leg.price)
        if matched >= float(leg.size) - 1e-9:
            leg.status = "open"
    residuo_iniziale = getattr(res, "size_remaining", None)
    if residuo_iniziale is None:
        residuo_iniziale = round(max(0.0, float(leg.size) - matched), 2)
    # ⚠️ CONSAPEVOLEZZA DELL'ORDINE (replay del banco, mike-t2/t3/t4, CP1 x3,
    # residuo 10,12) — la riga si aggiorna SEMPRE qui, non solo `if matched > 0`.
    # L'ordine appoggiato SENZA abbinamento immediato e' il caso NORMALE (resta
    # sul book): prima, in quel caso, `_aggiorna_riga_resting` non veniva mai
    # chiamata e la riga restava 'pending' senza `size_matched`/`size_remaining`
    # leggibili finche' l'ordine era vivo. Qui si scrive SEMPRE chiesto/abbinato
    # (0 se non c'e' stato abbinamento)/residuo (= chiesto, se abbinato e' 0)/
    # prezzo medio, come fa `execution.place` (`Betfair/safe_strategy/
    # execution.py`) per il percorso Safe/Omega — nessuna decisione di
    # STRATEGIA cambia, solo la tracciatura.
    _aggiorna_riga_resting(db, eid, leg,
                           "live_resting_immediato" if matched > 0 else "live_resting_piazzato",
                           residuo=residuo_iniziale,
                           aggiornato_al=getattr(res, "betfair_updated_at", None))
    db.log("place_resting", {"leg": leg.ref, "role": leg.role, "price": leg.price,
                             "size": leg.size, "matched": round(matched, 2),
                             "live": True,
                             # C.12a — chiesto e residuo detti per nome
                             "size_requested": round(float(leg.size), 2),
                             "size_remaining": round(float(residuo_iniziale), 2),
                             "nota": (f"parziale {matched:.2f} su {float(leg.size):.2f}, "
                                      f"residuo {float(residuo_iniziale):.2f} vivo"
                                      if 0 < matched < float(leg.size) - 1e-9 else None)}, eid)


def _aggiorna_riga_resting(db: Any, event_id: str, leg: E.Leg, come: str,
                          residuo: Optional[float] = None,
                          aggiornato_al: Optional[str] = None) -> None:
    """Porta l'abbinamento sulla riga di ``mike_trades``. Stessa strada del paper.

    C.12a — porta anche CHIESTO, RESIDUO, PREZZO MEDIO e l'istante dell'ultima
    notizia da Betfair sulle colonne nuove (se la migrazione e' applicata):
    ``size`` da sola racconta l'abbinato e fa sparire il chiesto.
    Il ``residuo`` arriva da ``sizeRemaining`` di Betfair quando c'e'; solo in
    sua assenza si ripiega sulla differenza chiesto-abbinato, ed e' una stima.
    """
    r = _trade_row_for_leg(db, event_id, leg)
    if r is None:
        return
    if residuo is None:
        residuo = round(max(0.0, float(leg.size) - float(leg.matched)), 2)
    try:
        X.aggiorna_trade(
            db, int(r["id"]),
            campi={"status": ("open" if leg.status == "open" else "pending"),
                   "price": leg.avg_price or leg.price, "size": leg.matched,
                   "meta": {**(r.get("meta") or {}), "phase": "open", "fill": come}},
            consapevolezza={"size_requested": round(float(leg.size), 2),
                            "size_matched": round(float(leg.matched), 2),
                            "size_remaining": round(float(residuo), 2),
                            "avg_price_matched": leg.avg_price,
                            "betfair_updated_at": aggiornato_al})
    except Exception as ex:  # noqa: BLE001
        db.log("error", {"leg": leg.ref, "reason": "fill_update_failed",
                         "err": str(ex)[:160]}, event_id)


# ===========================================================================
# I CAMPI DI UN ORDINE BETFAIR — UN SOLO POSTO CHE NE CONOSCE I NOMI
# ===========================================================================
# ⚠️ 15/09 — QUI E' NATO IL LOOP DEI 32 ORDINI VERI, ed e' rinato una seconda
# volta dentro la funzione che lo aveva causato.
#
# `omega_market.list_current_orders()` / `list_cleared_orders()` NORMALIZZANO le
# chiavi in snake_case (``size_matched``, ``customer_order_ref``…). Chi legge
# ``sizeMatched`` da quei dizionari non prende un errore: prende `None`, che
# diventa `0.0`, che significa «non abbinato niente». Un confronto falso per
# costruzione, silenzioso, sul percorso dei soldi:
#
#   * in `_ordine_di` valeva «questo ordine non l'ho mai piazzato» → e il
#     motore ne piazzava un altro, trentadue volte;
#   * in `_segui_resting_live` valeva «la lay appoggiata non si e' abbinata» →
#     e un green-up gia' eseguito a mercato restava `pending` nel database.
#
# Da qui in avanti i nomi dei campi stanno SOLO in questa tabella, e si
# accettano ENTRAMBE le grafie: cosi' un cambio di normalizzazione a monte non
# puo' piu' rompere in silenzio una lettura da cui dipendono ordini veri.
# Il contratto e' verificato da `tests/test_mike_contratto_ordini_2026_09_15.py`,
# che fa passare una risposta Betfair grezza dal normalizzatore VERO.
_ALIAS_ORDINE: Dict[str, tuple] = {
    "bet_id": ("bet_id", "betId"),
    "customer_order_ref": ("customer_order_ref", "customerOrderRef"),
    "size_matched": ("size_matched", "sizeMatched"),
    "avg_price_matched": ("avg_price_matched", "averagePriceMatched"),
    "size_remaining": ("size_remaining", "sizeRemaining"),
    "size_settled": ("size_settled", "sizeSettled"),
    # C.12a — il resto di cio' che Betfair dice sull'ordine. `size_cancelled`
    # distingue «l'ho annullato io» da «e' scaduto» (`size_lapsed`), e
    # `matched_date` e' il «quando l'ho saputo» che mancava ovunque.
    "size_cancelled": ("size_cancelled", "sizeCancelled"),
    "size_lapsed": ("size_lapsed", "sizeLapsed"),
    "size_voided": ("size_voided", "sizeVoided"),
    "matched_date": ("matched_date", "matchedDate"),
    "placed_date": ("placed_date", "placedDate"),
    "market_id": ("market_id", "marketId"),
    "selection_id": ("selection_id", "selectionId"),
    "status": ("status",),
    "side": ("side",),
}


def campo_ordine(o: Optional[Dict[str, Any]], campo: str,
                 difetto: Any = None) -> Any:
    """Un campo di un ordine Betfair, comunque sia scritto.

    Vale `None` solo se il campo MANCA DAVVERO: un valore presente ma nullo
    (``None``) resta `None` e non diventa il difetto, perche' «non lo so» e
    «zero» non sono la stessa cosa — su un prezzo medio abbinato quella
    differenza sono soldi.
    """
    if not isinstance(o, dict):
        return difetto
    for nome in _ALIAS_ORDINE.get(campo, (campo,)):
        if nome in o:
            return o[nome]
    return difetto


def _num_ordine(o: Optional[Dict[str, Any]], campo: str, difetto: float = 0.0) -> float:
    """Come `campo_ordine`, ma il risultato e' un numero utilizzabile."""
    v = campo_ordine(o, campo)
    if v is None:
        return difetto
    try:
        return float(v)
    except (TypeError, ValueError):
        return difetto


_ASSENTE = object()


def ordine_normalizzato(o: Dict[str, Any]) -> Dict[str, Any]:
    """Un ordine Betfair riscritto con le chiavi in snake_case, comunque arrivi.

    Chi sta a valle — ``omega_engine._order_matches`` e le
    ``reconcile_decision`` — legge ``size_matched``, ``size_remaining``,
    ``avg_price_matched``, ``customer_order_ref`` e basta. Se l'ordine arriva
    in camelCase quelle letture NON danno errore: danno `None`, che diventa
    `0.0`, che significa «non abbinato». E' il difetto del 15/09, e quelle
    funzioni non hanno modo di difendersene da sole.
    Qui il dizionario si rende conforme UNA volta, passando dall'unica tabella
    che conosce i nomi dei campi.
    """
    out = dict(o)
    for campo in _ALIAS_ORDINE:
        v = campo_ordine(o, campo, _ASSENTE)
        if v is not _ASSENTE:
            out[campo] = v
    return out


def ref_ordine_di_riga(r: Dict[str, Any]) -> str:
    """Il ``customerOrderRef`` con cui Mike piazza l'ordine di questa riga.

    UNO SOLO, e viene dall'id di riga: e' l'unico identificativo di Mike che
    sia davvero unico. Lo usano il place delle aperture (``X.place``), il place
    della lay appoggiata e la riconciliazione — dal 15/09 tutti e tre.
    """
    return f"mike-t{r.get('id')}"


def _ordine_della_riga(ordini: Optional[List[Dict[str, Any]]],
                       r: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """L'ordine Betfair che appartiene a questa riga di ``mike_trades``, o None.

    Tre strade, dalla piu' solida alla piu' debole, e la piu' debole porta una
    guardia:

      1. il ``bet_id`` scritto sulla riga — l'identificativo che ci ha dato
         Betfair, unico su tutto il conto: non puo' confondersi con niente;
      2. ``mike-t<id>``, il ref di oggi: unico perche' viene dall'id di riga;
      3. il ``signal_key`` della gamba (``under_green-0-2``) — il ref con cui
         PRIMA del 15/09 venivano appoggiate le lay. Questo NON e' unico fra
         partite: vale `{ruolo}-{ciclo}-{seq}` e `seq` conta per partita, quindi
         due eventi diversi possono esibire lo stesso ref nello stesso momento.
         Si accetta SOLO a mercato e selezione concordi.

    La terza strada serve agli ordini gia' vivi a mercato al momento del fix e
    a nessun altro: i nuovi nascono tutti con `mike-t<id>`.
    """
    if not ordini:
        return None
    norm = [ordine_normalizzato(o) for o in ordini if isinstance(o, dict)]

    bet_id = str(r.get("bet_id") or "").strip()
    if bet_id:
        for o in norm:
            if str(o.get("bet_id") or "").strip() == bet_id:
                return o

    mio = ref_ordine_di_riga(r)
    for o in norm:
        if str(o.get("customer_order_ref") or "") == mio:
            return o

    storico = str(r.get("signal_key") or "").strip()
    if not storico or storico == mio:
        return None
    mid = r.get("market_id")
    try:
        sid = int(r["selection_id"]) if r.get("selection_id") is not None else None
    except (TypeError, ValueError):
        sid = None
    for o in norm:
        if str(o.get("customer_order_ref") or "") != storico:
            continue
        # LA GUARDIA, e non e' teorica: alle 14:00 del 15/09 c'erano a mercato
        # `under_green-0-116` e `under_green-0-2` su due partite diverse. Senza
        # questo confronto una riga verrebbe confermata con l'ordine di un ALTRO
        # evento — prezzo e size di un'altra posizione, con soldi veri.
        if mid is not None and str(o.get("market_id") or "") != str(mid):
            continue
        if sid is not None and o.get("selection_id") is not None:
            try:
                if int(o["selection_id"]) != sid:
                    continue
            except (TypeError, ValueError):
                continue
        return o
    return None


def _ordine_di(vivi: List[Dict[str, Any]], leg: E.Leg, db: Any,
               event_id: str) -> Optional[Dict[str, Any]]:
    """Ritrova FRA GLI ORDINI VIVI quello di questa gamba.

    ⚠️ 15/09 — QUI STAVA LA RADICE DEL LOOP, ed era una sola parola.

    `omega_market.list_current_orders()` NORMALIZZA le chiavi in snake_case e
    restituisce ``customer_order_ref``; qui si cercava ``customerOrderRef``,
    che in quel dizionario NON ESISTE. Il confronto falliva sempre, per
    costruzione: ogni ordine appoggiato risultava «mai piazzato», il motore ne
    creava uno nuovo, e si ricominciava. Trentadue volte con soldi veri.

    La ricerca sta tutta in ``_ordine_della_riga``, che e' l'UNICO posto in cui
    Mike decide se un ordine Betfair e' suo: bet_id, poi ``mike-t<id>``, poi il
    ref storico a mercato concorde. Qui non si duplica quella logica — e' il
    modo in cui lo stesso difetto e' rinato una seconda volta.

    Senza riga non si cerca per ref: ``leg.ref`` non e' unico fra partite e un
    match sbagliato contabilizzerebbe l'abbinamento di un ALTRO evento. Non
    trovare un ordine costa un ciclo di attesa; trovarne uno sbagliato costa
    soldi. Nel dubbio si dice «non lo so».
    """
    riga = _trade_row_for_leg(db, event_id, leg)
    if riga is None:
        return None
    return _ordine_della_riga(vivi, riga)


def _segui_resting_live(*, db: Any, market: Any, leg: E.Leg, extra: Dict[str, Any],
                        params: Dict[str, Any], now_ts: float, ev: Dict[str, Any],
                        rilettura_in_corso: bool = False) -> None:
    """Quanto si e' abbinato della lay appoggiata? Lo dice BETFAIR, non il prezzo.

    In paper la simulazione guarda il book e decide. Qui no: un ordine reale ha
    una CODA davanti, e l'unico modo di sapere se e' toccato a noi e' chiederlo.
    Si riconosce l'ordine con ``_ordine_di`` → ``_ordine_della_riga``: bet_id,
    poi ``mike-t<id>``, poi il ref storico a mercato concorde. Vedi li' perche'
    la vecchia ricerca per sola ``customerOrderRef`` falliva SEMPRE.
    """
    eid = str(ev["event_id"])
    try:
        vivi = market.list_current_orders() or []
    except Exception as ex:  # noqa: BLE001 — rete: si riprova al giro dopo, senza inventare
        logger.debug("[mike] list_current_orders KO: %s", str(ex)[:120])
        return
    o = _ordine_di(vivi, leg, db, eid)
    if o is None:
        if rilettura_in_corso:
            # ⚠️ 16/09 SERA — C'E' UNA SOSPENSIONE IN CORSO E UNA RILETTURA GIA'
            # ANNOTATA: questa funzione NON deve dire la sua. Betfair fa scadere
            # (LAPSE) le lay appoggiate alla sospensione, quindi l'ordine sparisce
            # dai correnti per un MOTIVO NOTO e dichiarato (§15.6); a leggerlo e'
            # `_sorveglia_sospensione` alla riapertura, che sa distinguere i
            # quattro esiti (vivo / scaduto / abbinato / parziale). Se qui la
            # gamba venisse messa in `pending_reconcile`, alla riapertura non
            # sarebbe piu' viva e la rilettura chiuderebbe con
            # «gamba_non_piu_viva»: il ramo (b) «scaduto alla sospensione» non
            # verrebbe MAI esercitato — ed e' esattamente quello che il replay
            # ha misurato il 16/09 (riletture 0 su una registrazione con un
            # LAPSE alla sospensione). Consapevolezza, non strategia: cambia chi
            # legge l'esito, non che cosa il bot fa.
            _log_throttled(db, extra, params, now_ts, "resting_in_sospensione",
                           {"leg": leg.ref, "role": leg.role,
                            "reason": "sospensione_in_corso_rilettura_alla_riapertura",
                            "nota": "l'ordine appoggiato non e' piu' fra i correnti mentre "
                                    "il mercato e' sospeso: l'esito lo dice Betfair alla "
                                    "riapertura, non si indovina adesso"}, eid)
            return
        # Non e' piu' fra i vivi: o si e' abbinato del tutto, o e' stato
        # annullato, o non e' mai arrivato. Non si indovina fra tre casi che
        # hanno conseguenze opposte: riconciliazione.
        leg.status = E.STATUS_RECONCILE
        _log_throttled(db, extra, params, now_ts, "reconcile_pending",
                       {"leg": leg.ref, "role": leg.role,
                        "reason": "resting_uscito_dagli_ordini_vivi", "critical": True}, eid)
        return
    # ⚠️ 15/09 — QUI C'ERA `o.get("sizeMatched")`, ed era lo STESSO difetto che
    # aveva appena causato il loop dei 32 ordini, rinato nella stessa funzione.
    # Il dizionario espone `size_matched`: `sizeMatched` non esiste, quindi
    # `matched` valeva SEMPRE 0.0 e questa funzione — il cui unico compito e'
    # accorgersi che la lay appoggiata si e' abbinata — non se ne accorgeva mai.
    # Si e' visto dal vivo: la riga #4817 era `pending` nel database mentre su
    # Betfair l'ordine era EXECUTION_COMPLETE.
    matched = _num_ordine(o, "size_matched", 0.0)
    # ⚠️ C.12a — IL RESIDUO LO DICE BETFAIR, non una sottrazione.
    # Fino al 16/09 il residuo vivo era DEDOTTO da ``leg.size - leg.matched``:
    # se un fill arriva fra due letture, o se Betfair riduce l'ordine, quel
    # numero e' un'ipotesi. ``sizeRemaining`` c'e' nella risposta di
    # ``listCurrentOrders`` da sempre e ``omega_market`` lo normalizzava gia' in
    # ``size_remaining``: nessuno in Mike lo leggeva. Se manca (ordine che non
    # lo espone) si ripiega sulla differenza, dichiarandolo.
    residuo_betfair = campo_ordine(o, "size_remaining")
    residuo = (round(float(residuo_betfair), 2) if residuo_betfair is not None
               else round(max(0.0, float(leg.size) - matched), 2))
    aggiornato_al = campo_ordine(o, "matched_date") or campo_ordine(o, "placed_date")
    if matched <= float(leg.matched) + 1e-9:
        return                      # nessun progresso: si aspetta, come in paper
    leg.matched = matched
    prezzo = campo_ordine(o, "avg_price_matched")
    leg.avg_price = float(prezzo) if prezzo else float(leg.price)
    if matched >= float(leg.size) - 1e-9:
        leg.status = "open"         # abbinata del tutto
    _aggiorna_riga_resting(db, eid, leg, "live_resting", residuo=residuo,
                           aggiornato_al=(str(aggiornato_al) if aggiornato_al else None))
    db.log("fill_resting", {"leg": leg.ref, "role": leg.role, "matched": round(matched, 2),
                            "price": leg.avg_price, "live": True,
                            "size_requested": round(float(leg.size), 2),
                            "size_remaining": residuo,
                            "nota": (f"parziale {matched:.2f} su {float(leg.size):.2f}, "
                                     f"residuo {residuo:.2f} vivo"
                                     if leg.status != "open" else
                                     f"abbinata tutta ({matched:.2f})")}, eid)


# ===========================================================================
# LA SOSPENSIONE UCCIDE GLI ORDINI APPOGGIATI (ordine dell'utente, 16/09)
# ===========================================================================
# «Attenzione pero': quella gamba, se il mercato si sospende per qualsiasi
# motivo, Betfair cancella quell'ordine; il bot deve saperlo e appena riapre il
# mercato verificare cosa e' successo (gol estremamente precoci)».
#
# Un ordine LIMIT non abbinato ha ``persistenceType=LAPSE``: alla sospensione
# del mercato Betfair lo fa SCADERE. Un gol al 2' basta. Da fuori non si vede
# niente — nessun errore, nessuna notifica — e il bot resterebbe convinto di
# avere un'uscita sul book per tutta la finestra, per poi scoprire al momento
# di annullarla che non esiste piu'. Nel frattempo non ha ne' l'uscita ne' la
# copertura: e' il peggior punto in cui stare.
#
# Da qui in avanti: a ogni sospensione con una gamba appoggiata VIVA il ctx se
# lo ricorda (``ctx.riapertura``), e alla riapertura l'ordine si RILEGGE da
# Betfair per ``bet_id``. Le reazioni possibili sono quattro e sono tutte
# dichiarate — vivo, scaduto, abbinato, abbinato in parte — piu' l'ignoto, che
# non e' una reazione ma una riconciliazione (§4.11).
_ESITO_VIVO = "vivo"
_ESITO_SCADUTO = "scaduto"
_ESITO_ABBINATO = "abbinato"
_ESITO_PARZIALE = "parziale"
_ESITO_IGNOTO = "ignoto"


def _gambe_appoggiate_vive(ctx: E.MatchCtx, params: Dict[str, Any]) -> List[E.Leg]:
    """Le lay APPOGGIATE che in questo momento sono (per il bot) sul book."""
    return [l for l in ctx.legs if l.is_live and _is_resting_leg(l, params)]


def _classifica_ordine(leg: E.Leg, o: Dict[str, Any]) -> tuple:
    """Dall'ordine come lo racconta Betfair all'esito, con i numeri.

    Nessuna deduzione: ``size_matched``, ``size_remaining``, ``size_lapsed`` e
    ``size_cancelled`` vengono dalla risposta (``omega_market`` li normalizza
    gia' cosi', C.12a). Il residuo NON si calcola per differenza quando Betfair
    lo dice: una sottrazione e' un'ipotesi, e qui le ipotesi sono soldi.
    """
    abbinato = _num_ordine(o, "size_matched", 0.0)
    residuo_betfair = campo_ordine(o, "size_remaining")
    residuo = (float(residuo_betfair) if residuo_betfair is not None
               else max(0.0, float(leg.size) - abbinato))
    scaduto = _num_ordine(o, "size_lapsed", 0.0)
    annullato = _num_ordine(o, "size_cancelled", 0.0)
    stato = str(campo_ordine(o, "status", "") or "").upper()
    numeri = {"size_requested": round(float(leg.size), 2),
              "size_matched": round(abbinato, 2),
              "size_remaining": round(residuo, 2),
              "size_lapsed": round(scaduto, 2),
              "size_cancelled": round(annullato, 2),
              "order_status": stato or None,
              "avg_price_matched": campo_ordine(o, "avg_price_matched"),
              "betfair_updated_at": campo_ordine(o, "matched_date") or campo_ordine(o, "placed_date")}
    if residuo > 0.009 and stato != "EXECUTION_COMPLETE":
        return (_ESITO_VIVO, numeri)
    if abbinato >= float(leg.size) - 0.009:
        return (_ESITO_ABBINATO, numeri)
    if abbinato > 0.009:
        return (_ESITO_PARZIALE, numeri)
    return (_ESITO_SCADUTO, numeri)


def _rileggi_ordine_appoggiato(*, db: Any, market: Any, leg: E.Leg, ev: Dict[str, Any],
                               cache: Optional[Dict[str, List[Dict[str, Any]]]] = None):
    """RILEGGE da Betfair l'ordine di questa gamba. ``None`` = non si e' potuto.

    Due strade, nell'ordine: gli ordini CORRENTI (dove sta un ordine ancora
    vivo, con ``size_lapsed``/``size_cancelled``) e, se li' non c'e' piu',
    ``order_state_by_bet_id`` — l'unica chiave certa quando l'ordine e' uscito
    dalla lista dei correnti (`omega_market:1082`, guarda anche i regolati
    LAPSED/CANCELLED). ``None`` significa «non lo so ancora»: si riprova al
    giro dopo, e fino ad allora NESSUNO puo' dire che quell'ordine e' vivo.
    """
    eid = str(ev["event_id"])
    riga = _trade_row_for_leg(db, eid, leg, cache)
    if riga is None:
        return (_ESITO_IGNOTO, {"reason": "riga_assente"})
    try:
        vivi = market.list_current_orders() or []
    except Exception as ex:  # noqa: BLE001 — rete: si riprova, non si inventa
        logger.warning("[mike] %s: rilettura alla riapertura KO (correnti): %s",
                       eid, str(ex)[:120])
        return None
    o = _ordine_della_riga(vivi, riga)
    if o is not None:
        return _classifica_ordine(leg, o)
    bet_id = str(riga.get("bet_id") or "").strip()
    fn = getattr(market, "order_state_by_bet_id", None)
    if not bet_id or not callable(fn):
        # senza identificativo non si puo' chiedere niente a Betfair: e' ignoto,
        # e l'ignoto si riconcilia (§4.11), non si indovina.
        return (_ESITO_IGNOTO, {"reason": "senza_bet_id" if not bet_id else "mercato_senza_lettura"})
    try:
        st = fn(bet_id) or {}
    except Exception as ex:  # noqa: BLE001
        logger.warning("[mike] %s: rilettura alla riapertura KO (bet %s): %s",
                       eid, bet_id, str(ex)[:120])
        return None
    if not st.get("found"):
        return (_ESITO_IGNOTO, {"reason": "betfair_non_lo_conosce", "bet_id": bet_id})
    esito, numeri = _classifica_ordine(leg, dict(st))
    numeri["bet_id"] = bet_id
    return (esito, numeri)


def _chiudi_gamba_scaduta(db: Any, event_id: str, leg: E.Leg, numeri: Dict[str, Any]) -> None:
    """La gamba e' morta alla sospensione: si chiude PER QUELLO CHE E'.

    Non e' un errore del bot e non e' «mai piazzata»: l'ordine e' esistito, e
    quanto ha abbinato prima di scadere resta una POSIZIONE. Si scrive
    l'abbinato vero, il residuo a zero, e il motivo per esteso nel ``meta``.
    (Il vincolo di ``mike_trades.status`` ammette solo
    pending|open|hedged|won|lost|void|error: una riga senza abbinato resta
    'error' come ogni altra gamba ritirata — nessuna migrazione, e il motivo
    sta nel ``meta`` e nell'attivita'.)
    """
    abbinato = float(numeri.get("size_matched") or 0.0)
    prezzo = numeri.get("avg_price_matched")
    leg.matched = abbinato
    if abbinato > 0:
        leg.avg_price = float(prezzo) if prezzo else float(leg.price)
    leg.status = "open" if abbinato > 0 else "cancelled"
    r = _trade_row_for_leg(db, event_id, leg)
    if r is None:
        return
    meta = dict(r.get("meta") or {})
    meta.update({"phase": "lapsed", "reason": "lapsed_alla_sospensione"})
    campi: Dict[str, Any] = {"meta": meta}
    if abbinato > 0:
        campi.update({"status": "open", "size": round(abbinato, 2), "price": leg.fill_price})
    else:
        campi["status"] = "error"
    try:
        X.aggiorna_trade(db, int(r["id"]), campi=campi,
                         consapevolezza={"size_requested": round(float(leg.size), 2),
                                         "size_matched": round(abbinato, 2),
                                         "size_remaining": 0.0,
                                         "avg_price_matched": leg.avg_price if abbinato > 0 else None,
                                         "betfair_updated_at": numeri.get("betfair_updated_at")})
    except Exception as ex:  # noqa: BLE001
        db.log("error", {"leg": leg.ref, "reason": "lapsed_update_failed",
                         "err": str(ex)[:160]}, event_id)


def _applica_esito_riapertura(*, db: Any, event_id: str, leg: E.Leg, esito: str,
                              numeri: Dict[str, Any]) -> None:
    """LE QUATTRO REAZIONI, una per una. Chi decide dopo e' il motore.

    (a) vivo      -> la gamba resta com'e': ``_segui_resting_live`` continua a
                     seguirne gli abbinamenti, niente gamba nuova;
    (b) scaduto   -> attivita' ``ordine_scaduto_alla_sospensione`` con i numeri
                     e gamba chiusa; il motore, al giro dopo, ri-appoggia se la
                     finestra e' ancora aperta oppure passa alla copertura
                     (`engine._decide_ko_green`: freno anti-duplicato e
                     ``finestra_uscita_scaduta`` decidono, non questa funzione);
    (c) abbinato  -> e' una POSIZIONE: si contabilizza subito, il ciclo prosegue;
    (d) parziale  -> la parte abbinata e' posizione, il residuo e' scaduto: si
                     dichiara con i numeri e la gamba si chiude come in (b),
                     per la sola parte residua.
    ignoto        -> ``pending_reconcile`` (§4.11), MAI una gamba nuova.
    """
    comune = {"leg": leg.ref, "role": leg.role, "esito": esito, **numeri}
    if esito == _ESITO_VIVO:
        db.log("rilettura_alla_riapertura",
               {**comune, "nota": "l'ordine appoggiato e' ancora vivo sul book: "
                                  "nessuna gamba nuova"}, event_id)
        return
    if esito == _ESITO_ABBINATO:
        leg.matched = float(numeri.get("size_matched") or leg.size)
        prezzo = numeri.get("avg_price_matched")
        leg.avg_price = float(prezzo) if prezzo else float(leg.price)
        leg.status = "open"
        _aggiorna_riga_resting(db, event_id, leg, "riapertura_abbinata", residuo=0.0,
                               aggiornato_al=(str(numeri.get("betfair_updated_at"))
                                              if numeri.get("betfair_updated_at") else None))
        db.log("rilettura_alla_riapertura",
               {**comune, "nota": "abbinato durante la sospensione: e' una posizione, "
                                  "il ciclo prosegue"}, event_id)
        return
    if esito == _ESITO_IGNOTO:
        leg.status = E.STATUS_RECONCILE
        logger.critical("[mike] %s: esito IGNOTO alla riapertura su %s -> riconciliazione",
                        event_id, leg.ref)
        db.log("rilettura_alla_riapertura",
               {**comune, "critical": True,
                "nota": "Betfair non ha detto che fine ha fatto: riconciliazione, "
                        "mai una gamba nuova su un dubbio"}, event_id)
        db.log("reconcile_pending", {"leg": leg.ref, "role": leg.role, "critical": True,
                                     "reason": "riapertura_esito_ignoto"}, event_id)
        return
    # (b) e (d): l'ordine e' morto alla sospensione, in tutto o nel residuo
    db.log("rilettura_alla_riapertura", {**comune}, event_id)
    db.log("ordine_scaduto_alla_sospensione",
           {**comune, "critical": True,
            "nota": ("Betfair ha fatto SCADERE (LAPSE) l'ordine appoggiato quando il "
                     "mercato si e' sospeso"
                     + (": la parte abbinata resta una posizione, il residuo non c'e' piu'"
                        if esito == _ESITO_PARZIALE else
                        ": non era abbinato niente, la gamba si chiude"))}, event_id)
    _chiudi_gamba_scaduta(db, event_id, leg, numeri)


# ===========================================================================
# LA POSIZIONE DI CONTO - "SE CHIUDO IO, IL BOT DEVE SAPERLO, ANCHE FUORI
# DALL'APP" (ordine dell'utente, 16/09/2026 sera)
# ===========================================================================
# Mike legge i SUOI ordini per ``customerStrategyRef``: una lay che l'utente
# piazza dal sito Betfair (o da un'altra app) per chiudere la posizione NON ha
# quel ref, quindi Mike non la vede e continua a gestire un back che, sul conto,
# non e' piu' esposto. Coperture, green-up e re-ingressi su una posizione
# inesistente: e' lo stesso reperto gia' aperto su Omega (R9).
#
# La verita' e' la POSIZIONE DI CONTO sul mercato: ``listCurrentOrders`` e
# ``listClearedOrders`` con i soli ``marketIds`` (nessun filtro di strategia).
# Ci sono dentro ANCHE le altre operazioni dell'utente sulla stessa partita:
# Mike deve riconoscere LA SUA dentro quella di conto (per riferimento e size),
# non dare per suo tutto quello che vede.
#
# CADENZA DICHIARATA: ``reconcile_every_s`` (default 30 s per partita), la
# stessa del respiro del database; MAI a ogni giro. Due letture REST per
# mercato per volta, e solo con una posizione aperta da difendere.
_CONTO_LETTO_A: Dict[str, float] = {}


# ---------------------------------------------------------------------------
# LE CACHE DI PROCESSO, IN UN ELENCO SOLO
# ---------------------------------------------------------------------------
# ⚠️ 16/09 SERA — un difetto del BANCO, trovato col referto alla mano. Il replay
# con la pool (`--worker 3`) esegue piu' coppie evento x scenario NELLO STESSO
# processo figlio, una dopo l'altra: le cache di modulo del servizio
# sopravvivono da uno scenario al successivo e lo scenario dopo parte con i
# throttle gia' «consumati» dell'altro. Misurato: nello scenario
# `chiuso-fuori-app` dentro `--scenari tutti --worker 3` la lettura della
# POSIZIONE DI CONTO non e' mai partita (throttle ereditato da uno scenario
# precedente) e il controllo R3 risultava sollecitato ZERO volte, mentre lo
# stesso scenario da solo lo sollecita 5.837 volte. In produzione questo non
# accade (un processo, un ciclo continuo): e' il banco che deve ripartire
# pulito a ogni replay.
#
# L'elenco e' ESPLICITO e non generato da `dir()`: `_ALIAS_ORDINE` e' un
# dizionario di modulo come gli altri, ma svuotarlo toglierebbe al bot la
# capacita' di leggere le chiavi camelCase di Betfair — cioe' proprio il
# difetto 1 del 15/09, reintrodotto da un azzeramento troppo allegro.
_CACHE_DI_PROCESSO = ("_DAILY_STOP_LOGGED", "_LAST_HEARTBEAT", "_CONFIG_WARNED",
                      "_CACHE_EVENTI", "_RICONCILIATO_A", "_SCRITTO_A",
                      "_MALFORMED_LOGGED", "_LAST_AGG", "_CONTO_LETTO_A")


def azzera_cache_di_processo() -> List[str]:
    """Riporta il MODULO allo stato di un processo appena avviato.

    La usa il banco all'inizio di ogni replay (e lo scenario `riavvio` a meta'
    partita). Non tocca il database: quello, in produzione, sopravvive.
    Torna l'elenco di cio' che ha azzerato — un riavvio che non si sa che cosa
    ha buttato non prova niente.
    """
    global _ULTIMI_PARAMS, _EVENTI_LETTI_A

    azzerati: List[str] = []
    for nome in _CACHE_DI_PROCESSO:
        valore = globals().get(nome)
        if isinstance(valore, dict):
            valore.clear()
            azzerati.append(nome)
    if _ULTIMI_PARAMS is not None:
        _ULTIMI_PARAMS = None
        azzerati.append("_ULTIMI_PARAMS")
    if _EVENTI_LETTI_A:
        _EVENTI_LETTI_A = 0.0
        azzerati.append("_EVENTI_LETTI_A")
    # 18/09 (F5): anche i contatori e l'istante dell'ultimo giro della sveglia
    # sono stato di PROCESSO (difetto 37 del catalogo): il banco riparte pulito.
    try:
        _SVEGLIA.azzera()
        azzerati.append("_SVEGLIA")
    except Exception:  # noqa: BLE001 - mai far fallire un azzeramento
        pass
    return azzerati

# tolleranza sotto la quale una differenza di posizione e' rumore di
# arrotondamento e non una chiusura (Betfair lavora al centesimo)
_CONTO_EPS = 0.05


def _netto_su_selezione(righe: List[Dict[str, Any]], market_id: str, selection_id: int,
                        solo_refs: Optional[set] = None) -> float:
    """BACK meno LAY dell'ABBINATO su (mercato, selezione), in euro di size.

    ``solo_refs`` = conta solo gli ordini con quel ``customer_order_ref``: e' il
    modo in cui Mike riconosce LA SUA parte dentro la posizione di conto.
    Nessun campo dedotto: ``size_matched`` e' quello che Betfair dichiara (le
    righe regolate lo portano con la stessa grafia, vedi
    ``omega_market._riga_regolata``).
    """
    netto = 0.0
    for o in righe or []:
        if str(o.get("market_id") or "") != str(market_id):
            continue
        try:
            if int(o.get("selection_id") or 0) != int(selection_id):
                continue
        except (TypeError, ValueError):
            continue
        if solo_refs is not None and str(o.get("customer_order_ref") or "") not in solo_refs:
            continue
        size = float(campo_ordine(o, "size_matched") or 0.0)
        if size <= 0:
            continue
        netto += size if str(o.get("side") or "").lower() == "back" else -size
    return round(netto, 2)


def _posizione_attesa(ctx: E.MatchCtx, mercato: str, selezione: str) -> float:
    """Quanto Mike CREDE di avere su (mercato, selezione): BACK meno LAY
    dell'abbinato delle sue gambe non archiviate."""
    netto = 0.0
    for l in ctx.legs:
        if l.archived or l.market != mercato or l.selection != selezione:
            continue
        m = float(l.matched or 0.0)
        if m <= 0:
            continue
        netto += m if l.side == "back" else -m
    return round(netto, 2)


def _refs_di_mike(ctx: E.MatchCtx, mercato: str, selezione: str,
                  db: Any, event_id: str,
                  cache: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> set:
    """I riferimenti con cui Mike ha piazzato su (mercato, selezione).

    Sono due grafie, entrambe vere: il ref della gamba (``under_entry-0-1``,
    usato dalle uscite) e ``mike-t<id>`` (usato dalle aperture). Le si prendono
    tutte e due - cercarne una sola e' il difetto 4 del 15/09.
    """
    refs = set()
    for l in ctx.legs:
        if l.archived or l.market != mercato or l.selection != selezione:
            continue
        refs.add(str(l.ref))
        r = _trade_row_for_leg(db, event_id, l, cache)
        if r is not None:
            rif = ref_ordine_di_riga(r)
            if rif:
                refs.add(str(rif))
    return refs


def _sorveglia_posizione_di_conto(*, db: Any, market: Any, ctx: E.MatchCtx,
                                  ev: Dict[str, Any], extra: Dict[str, Any],
                                  params: Dict[str, Any], mode: str, now_ts: float,
                                  cache: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> bool:
    """La posizione di CONTO contiene ancora quella di Mike? (True = l'ha chiusa
    l'utente, ed e' la prima volta che lo si scopre).

    In PAPER non esiste nessun conto da leggere: si dichiara e si esce. In LIVE
    si legge alla cadenza di ``reconcile_every_s``. Il verdetto e' conservativo:
    * se le gambe di Mike NON si ritrovano sul conto (per ref e size), il caso
      e' una riconciliazione, non una chiusura dell'utente: si dichiara e basta;
    * se si ritrovano ma il NETTO di conto non contiene piu' la sua posizione,
      la posizione e' stata chiusa da qualcun altro: ``chiuso_dall_utente``;
    * se la contiene solo in parte, lo si DICE e non si fa nulla (una copertura
      parziale dell'utente non autorizza il bot a smettere di proteggere).
    """
    if str(mode) == "paper":
        return False
    if ctx.chiuso_dall_utente:
        return False
    ogni = float(params.get("reconcile_every_s") or 0.0)
    eid = str(ev["event_id"])
    if now_ts - float(_CONTO_LETTO_A.get(eid) or 0.0) < ogni:
        return False
    aperte = E.open_selections(ctx.legs)
    if not aperte:
        return False
    _CONTO_LETTO_A[eid] = now_ts
    leggi_vivi = getattr(market, "list_account_orders", None)
    leggi_morti = getattr(market, "list_account_cleared_orders", None)
    if not callable(leggi_vivi) or not callable(leggi_morti):
        _log_throttled(db, extra, params, now_ts, "posizione_di_conto_non_letta",
                       {"reason": "il mercato non espone la posizione di conto",
                        "nota": "senza questa lettura una chiusura fatta FUORI "
                                "dall'app resta invisibile"}, eid)
        return False
    mkts = ev.get("markets") or {}
    selezioni = dict(extra.get("selections") or {})
    per_mercato: Dict[str, List[Dict[str, Any]]] = {}
    chiuse: List[Dict[str, Any]] = []
    parziali: List[Dict[str, Any]] = []
    for (mercato, selezione) in sorted(aperte):
        atteso = _posizione_attesa(ctx, mercato, selezione)
        if abs(atteso) <= _CONTO_EPS:
            continue
        market_id = str((mkts.get(mercato) or {}).get("market_id") or "")
        sel = selezioni.get(f"{mercato}|{selezione}")
        if not market_id or sel is None:
            continue
        if market_id not in per_mercato:
            try:
                per_mercato[market_id] = (list(leggi_vivi(market_id) or [])
                                          + list(leggi_morti(market_id) or []))
            except Exception as ex:  # noqa: BLE001 - rete: si riprova, non si inventa
                logger.warning("[mike] %s: posizione di conto non letta su %s: %s",
                               eid, market_id, str(ex)[:120])
                _CONTO_LETTO_A[eid] = 0.0
                return False
        righe = per_mercato[market_id]
        refs = _refs_di_mike(ctx, mercato, selezione, db, eid, cache)
        mio = _netto_su_selezione(righe, market_id, int(sel), solo_refs=refs)
        conto = _netto_su_selezione(righe, market_id, int(sel))
        dettaglio = {"mercato": mercato, "selezione": selezione, "market_id": market_id,
                     "selection_id": int(sel), "atteso": atteso, "mio_sul_conto": mio,
                     "netto_di_conto": conto, "altrui": round(conto - mio, 2)}
        if abs(mio) + _CONTO_EPS < abs(atteso):
            # le SUE gambe non si ritrovano: e' un problema di riconciliazione,
            # non una chiusura dell'utente. Non si spegne niente su un dubbio.
            db.log("posizione_di_conto", {**dettaglio, "verdetto": "gambe_non_ritrovate",
                                          "critical": True,
                                          "nota": "gli ordini di Mike non si ritrovano sul "
                                                  "conto: e' riconciliazione, non una "
                                                  "chiusura dell'utente"}, eid)
            continue
        # quanto della posizione di Mike SOPRAVVIVE dentro il netto di conto
        vivo = (min(atteso, max(0.0, conto)) if atteso > 0
                else max(atteso, min(0.0, conto)))
        if abs(vivo) <= _CONTO_EPS:
            chiuse.append({**dettaglio, "verdetto": "chiusa_dall_utente"})
        elif abs(vivo) + _CONTO_EPS < abs(atteso):
            parziali.append({**dettaglio, "verdetto": "ridotta_dall_utente",
                             "ancora_viva": round(vivo, 2)})
    for d in parziali:
        db.log("posizione_di_conto", {**d, "critical": True,
                                      "nota": "il conto contiene solo in PARTE la posizione "
                                              "di Mike: si dichiara, il bot continua a "
                                              "proteggere quello che resta"}, eid)
    if not chiuse:
        return False
    db.log("chiuso_dall_utente",
           {"dove": "fuori dall'app", "selezioni": chiuse, "critical": True,
            "nota": "la posizione di CONTO sul mercato non contiene piu' la posizione di "
                    "Mike: l'ha chiusa l'utente con un ordine suo. Da qui in poi Mike non "
                    "gestisce piu' questa partita (niente coperture, green-up, "
                    "re-ingressi); il P&L lo contabilizza il regolamento vero."}, eid)
    logger.critical("[mike] %s: posizione chiusa DALL'UTENTE fuori dall'app -> "
                    "il bot non gestisce piu' questa partita", eid)
    # le gambe ancora VIVE (ordini appoggiati) vanno tolte dal mercato: se si
    # abbinassero aprirebbero una posizione nuova su una partita che non e' piu'
    # del bot. Annullare RIDUCE il rischio: e' sempre permesso.
    for leg in list(ctx.legs):
        if leg.is_live:
            _mark_trade_cancelled(db, eid, leg, "chiuso_dall_utente_fuori_app",
                                  cache, market=market)
    ctx.chiuso_dall_utente = True
    ctx.no_reentry = True
    ctx.reentry_allowed = False
    ctx.reentry_done = True
    ctx.flatten_pending = False
    return True


def _sorveglia_sospensione(*, db: Any, market: Any, ctx: E.MatchCtx, snap: E.Snapshot,
                           params: Dict[str, Any], mode: str, now_ts: float,
                           ev: Dict[str, Any],
                           cache: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> None:
    """Ricorda le sospensioni e, alla riapertura, RILEGGE gli ordini appoggiati.

    Gira PRIMA della decisione: il motore deve vedere gambe che dicono la
    verita', non gambe date per vive per abitudine.
    """
    bk = snap.book(E.MARKET_OU35, E.SEL_UNDER)
    stato = E.stato_mercato(bk)

    if stato in (E.STATO_SOSPESO, E.STATO_IGNOTO):
        vive = _gambe_appoggiate_vive(ctx, params)
        if not vive:
            return
        refs = sorted(l.ref for l in vive)
        gia = ctx.riapertura or {}
        if gia and not gia.get("letto") and sorted(gia.get("refs") or []) == refs:
            return                       # stessa sospensione, gia' annotata
        ctx.riapertura = {"ts": now_ts, "refs": refs, "letto": False, "esiti": {}}
        db.log("mercato_sospeso", {"stato": stato, "refs": refs, "critical": True,
                                   "nota": "mercato sospeso con una lay appoggiata viva: "
                                           "Betfair puo' averla fatta scadere, alla "
                                           "riapertura si rilegge"}, str(ev["event_id"]))
        return

    if stato != E.STATO_APERTO:
        return                            # chiuso: non c'e' piu' niente da appoggiare
    r = ctx.riapertura
    if not r or r.get("letto"):
        return

    eid = str(ev["event_id"])
    esiti: Dict[str, Any] = dict(r.get("esiti") or {})
    for ref in list(r.get("refs") or []):
        leg = next((l for l in ctx.legs if l.ref == ref), None)
        if leg is None or not leg.is_live:
            esiti[ref] = "gamba_non_piu_viva"
            continue
        if str(mode) == "paper":
            # in paper non esiste nessun ordine su Betfair da far scadere: la
            # simulazione lo tiene sul book. Lo si DICHIARA, non lo si finge.
            esiti[ref] = "paper"
            continue
        letto = _rileggi_ordine_appoggiato(db=db, market=market, leg=leg, ev=ev, cache=cache)
        if letto is None:
            # non si e' potuto leggere: si riprova al giro dopo. ``letto`` resta
            # False, quindi il controllo R1 della certificazione lo vede.
            return
        esito, numeri = letto
        esiti[ref] = esito
        _applica_esito_riapertura(db=db, event_id=eid, leg=leg, esito=esito, numeri=numeri)
    ctx.riapertura = {**r, "letto": True, "letto_ts": now_ts, "esiti": esiti}


def _sorveglia_mercato_copertura(*, db: Any, ctx: E.MatchCtx, snap: E.Snapshot,
                                 now_ts: float, ev: Dict[str, Any]) -> None:
    """⚠️ ORDINE DELL'UTENTE 17/09 — «il bot deve essere informato dei cambi di
    stato del mercato (SOSPESO / APERTO / CHIUSO) DURANTE la copertura».

    Che cosa c'era prima, per non raccontarsela: ``_sorveglia_sospensione``
    guarda SOLO il mercato Under 3.5 e SOLO se c'e' una lay APPOGGIATA viva
    (la copertura e' un BACK sull'Over 4.5, quindi non ci entrava mai). Il
    motore ``operabile()`` lo consultava, ma la notizia moriva li': in pagina
    e nel referto una copertura ferma per sospensione era indistinguibile da
    una copertura ferma per attesa "intelligente".

    Qui si osserva lo stato del mercato della COPERTURA e si scrive UNA riga per
    TRANSIZIONE (non una per giro): sospeso/chiuso/ignoto quando si perde
    l'operabilita', riaperto quando torna. L'ignoto vale come non aperto
    (fail-closed): ``stato_mercato(None)`` e' ``ignoto``, mai "aperto".

    Nessun ordine viene emesso o annullato da qui: e' consapevolezza, non
    esecuzione. Chi decide resta il motore.
    """
    if not E.copertura_in_corso(ctx):
        return
    bk = snap.book(E.MARKET_OU45, E.SEL_OVER)
    stato = E.stato_mercato(bk)
    prima = str((ctx.cover_mercato or {}).get("stato") or "")
    if stato == prima:
        return                              # nessuna transizione: niente da dire
    ctx.cover_mercato = {"stato": stato, "ts": float(now_ts)}
    if not prima and stato == E.STATO_APERTO:
        return                              # prima lettura, mercato regolare: nessuna notizia
    mid = str(((ev.get("markets") or {}).get(E.MARKET_OU45) or {}).get("market_id") or "")
    gambe = sorted(l.ref for l in ctx.legs
                   if l.role == "over_cover" and (l.is_live or l.needs_reconcile))
    comune = {"stato": stato, "mercato": E.MARKET_OU45, "market_id": mid,
              "fase": "copertura", "refs": gambe, "state": ctx.state}
    if stato != E.STATO_APERTO:
        db.log("mercato_sospeso", {**comune, "critical": True,
                                   "nota": "mercato della copertura Over 4.5 non operabile: "
                                           "nessun ordine di copertura finche' non riapre"},
               str(ev["event_id"]))
        return
    db.log("skip", {**comune, "reason": "mercato_riaperto",
                    "nota": "mercato della copertura Over 4.5 di nuovo aperto: "
                            "la copertura riprende da dove era rimasta"},
           str(ev["event_id"]))


def _resting_filled(leg: E.Leg, book: Optional[E.Book]) -> bool:
    """Simulazione CONSERVATIVA della lay appoggiata a ``leg.price``: si considera
    abbinata SOLO quando il mercato ha scambiato SOTTO il suo prezzo (best back
    strettamente minore), mai perche' qualcuno laya allo stesso livello."""
    if book is None or book.status != "OPEN" or book.best_back is None:
        return False
    return float(book.best_back) < float(leg.price) - 1e-9


def _result(code: str, message: str, **extra: Any) -> Dict[str, Any]:
    """M1 — esito standard di una richiesta UI: ``code`` per il codice, ``message``
    in ITALIANO per l'utente. ``ok`` presente solo sugli esiti positivi."""
    out: Dict[str, Any] = {"code": code, "message": message}
    out.update(extra)
    return out


# Esiti ATTESI (l'utente ha chiesto qualcosa che ora non si puo' fare): status
# 'rejected'. Tutto il resto e' 'error' = il servizio non ce l'ha fatta
# (``kind_non_valido`` compreso: significa contratto rotto fra UI e DB).
_REJECT_CODES = ("evento_non_seguito", "stato_terminale", "posizione_aperta", "stato_non_riprendibile",
                 "feed_assente", "snapshot_assente", "niente_da_chiudere", "feed_stantio")


def process_requests(*, db: Any, market: Any, events: Dict[str, Dict[str, Any]],
                     rows_by_event: Dict[str, Dict[str, Any]], params: Dict[str, Any],
                     now: datetime, dry: bool, scanner_age: Optional[float] = None,
                     eff: Optional[Dict[str, Any]] = None,
                     reqs: Optional[List[Dict[str, Any]]] = None) -> int:
    # L3: le chiusure manuali usano i parametri EFFETTIVI del ciclo (in live la
    # lay appoggiata e' spenta: la chiusura deve essere taker)
    eff = eff if eff is not None else params
    n = 0
    if reqs is None:
        try:
            reqs = db.pending_requests()
        except Exception as ex:  # noqa: BLE001
            db.log("error", {"reason": "requests_failed", "err": str(ex)[:160]})
            return 0
    for req in reqs:
        rid = int(req["id"])
        kind = str(req.get("kind") or "")
        payload = req.get("payload") or {}
        eid = str(payload.get("event_id") or "")
        db.set_request_status(rid, "processing")
        res: Dict[str, Any]
        try:
            ev = events.get(eid)
            if ev is None:
                res = _result("evento_non_seguito", "Partita non seguita dal bot.")
            elif kind != "resume_event" and str(ev.get("state")) in ("SETTLED", "ERROR"):
                res = _result("stato_terminale",
                              f"Partita in stato {ev.get('state')}: nessuna operazione possibile.")
            elif kind in ("cashout", "flatten"):
                res = _request_flatten(db, market, ev, rows_by_event.get(eid), eff, now, dry,
                                       scanner_age=scanner_age, kind=kind)
            elif kind == "cancel":
                res = _request_cancel(db, ev, events, eid, market)
            elif kind == "skip_event":
                ctx = _ctx_from_row(ev, db)
                if E.open_selections(ctx.legs) or any(l.is_live or l.needs_reconcile for l in ctx.legs):
                    res = _result("posizione_aperta",
                                  "Posizione ancora aperta: prima chiudi con Cash out.")
                else:
                    ctx.state = "SKIPPED"
                    events[eid] = _row_from_ctx(ev, ctx, dict(ev.get("ctx") or {}))
                    events[eid]["skipped"] = True
                    db.upsert_event(events[eid])      # terminale: il ciclo partita non persiste
                    db.log("skip_event", {"by": "utente"}, eid)
                    res = _result("ok", "Partita saltata.", ok=True, state="SKIPPED")
            elif kind == "resume_event":
                ctx = _ctx_from_row(ev, db)
                extra = dict(ev.get("ctx") or {})
                if ctx.state == "SKIPPED":
                    ctx.state = "WATCH"
                    ctx.no_reentry = False            # H1/C3: l'utente riattiva la partita
                    ctx.flatten_pending = False
                    events[eid] = _row_from_ctx(ev, ctx, extra)
                    events[eid]["skipped"] = False
                    db.upsert_event(events[eid])
                    db.log("resume_event", {"by": "utente", "to": "WATCH"}, eid)
                    res = _result("ok", "Partita ripresa.", ok=True, state="WATCH")
                elif ctx.no_reentry or ctx.flatten_pending or E.copertura_bloccata(ctx):
                    # C3: dopo un cash out manuale pre-KO il bot NON rientra da
                    # solo; "Riprendi" e' l'unico modo di riabilitarlo. Si azzera
                    # anche ``flatten_pending``, altrimenti il completamento
                    # della chiusura manuale rimetterebbe subito il divieto.
                    ctx.no_reentry = False
                    ctx.flatten_pending = False
                    # 17/09 — ed e' anche L'INTERVENTO UMANO che riapre la
                    # copertura fermata dal freno sui rifiuti ripetuti: il freno
                    # e' fail-closed, da solo non si toglie mai.
                    sbloccata = E.copertura_bloccata(ctx)
                    E.sblocca_copertura(ctx)
                    events[eid] = _row_from_ctx(ev, ctx, extra)
                    db.upsert_event(events[eid])
                    db.log("resume_event", {"by": "utente", "no_reentry": False,
                                            "copertura_sbloccata": (
                                                None if sbloccata is None
                                                else {"error_code": sbloccata.get("error_code"),
                                                      "conteggio": int(sbloccata.get("conteggio") or 0)})},
                           eid)
                    res = _result("ok", "Rientro riabilitato su questa partita.", ok=True,
                                  state=ctx.state)
                else:
                    res = _result("stato_non_riprendibile",
                                  f"Stato {ctx.state}: niente da riprendere.")
            else:
                res = _result("kind_non_valido", f"Comando non valido: {kind}.")
        except Exception as ex:  # noqa: BLE001
            res = _result("errore_interno", f"Errore interno: {str(ex)[:120]}")
        status = "done" if res.get("ok") else ("rejected" if res.get("code") in _REJECT_CODES else "error")
        db.set_request_status(rid, status, res)
        n += 1
    return n


def _request_cancel(db: Any, ev: Dict[str, Any], events: Dict[str, Dict[str, Any]],
                    eid: str, market: Any = None) -> Dict[str, Any]:
    """Annulla gli ordini VIVI (resting) della partita, senza toccare la posizione.
    Una gamba in riconciliazione NON viene mai cancellata (C3).

    C.12a — ``_mark_trade_cancelled`` manda l'annullamento a BETFAIR e decide lo
    stato della gamba: annullato davvero, oppure in riconciliazione se Betfair
    non lo conferma. Il messaggio dice quanti ne ha annullati DAVVERO."""
    ctx = _ctx_from_row(ev, db)
    live = [l for l in ctx.legs if l.is_live]
    if not live:
        return _result("niente_da_chiudere", "Nessun ordine vivo da annullare.")
    annullati, in_verifica = 0, 0
    for leg in live:
        esito = _mark_trade_cancelled(db, eid, leg, "cancelled_by_user", market=market)
        if esito == E.STATUS_RECONCILE:
            in_verifica += 1
        else:
            annullati += 1
        db.log("cancel", {"leg": leg.ref, "role": leg.role, "by": "utente",
                          "esito": esito}, eid)
    events[eid] = _row_from_ctx(ev, ctx, dict(ev.get("ctx") or {}))
    db.upsert_event(events[eid])
    msg = f"Annullati {annullati} ordini sul book."
    if in_verifica:
        msg += (f" ATTENZIONE: {in_verifica} annullamenti non confermati da Betfair, "
                f"in verifica (l'ordine potrebbe essere ancora vivo).")
    return _result("ok", msg, ok=True, cancelled=annullati, in_verifica=in_verifica)


def _request_flatten(db: Any, market: Any, ev: Dict[str, Any], row: Optional[Dict[str, Any]],
                     params: Dict[str, Any], now: datetime, dry: bool,
                     scanner_age: Optional[float] = None, kind: str = "cashout") -> Dict[str, Any]:
    """Cash out / flatten MANUALE (H1, C2, M5).

    La richiesta ARMA la chiusura e annulla subito gli ordini vivi; la chiusura
    vera la guida l'ENGINE (``ctx.flatten_pending`` → ``_decide_flatten``) nello
    stesso ciclo e in quelli successivi, con i riprezzi. Cosi':
      1. prima si CANCELLA (una lay di green-up appoggiata che resta sul book
         lascerebbe una posizione netta LAY scoperta);
      2. poi si chiude la posizione netta delle sole selezioni ANCORA VIVE;
      3. C2 — finche' ``flatten_pending`` e' attivo il ciclo pre-match NON
         riappoggia la lay di green-up (prima, con ``pre_exit_mode='resting'``,
         cancellava e riappoggiava all'infinito: cash out impossibile);
      4. il contesto NON viene azzerato (ht_score, last_goals, deferred, selezioni);
      5. pre-KO: ciclo chiuso E ``no_reentry`` — il bot non rientra finche'
         l'utente non riabilita la partita con "Riprendi".
    """
    ctx = _ctx_from_row(ev, db)
    extra = dict(ev.get("ctx") or {})
    eid = str(ev["event_id"])
    # H3/L-3 — la chiusura manuale usa i parametri EFFETTIVI della PARTITA: se
    # la partita e' in live la lay appoggiata non esiste, si chiude taker.
    params = _live_exit_override(params, str(ev.get("mode") or "paper"))
    info = F.event_info(eid, (row or {}).get("payload") or {})
    if row is None or not info.complete:
        return _result("feed_assente",
                       "Quote non disponibili nel feed per questa partita: chiusura impossibile ora.")
    snap = F.snapshot_from_row(row, info, now=now.timestamp(), params=params,
                              scanner_age_s=scanner_age)
    if snap is None:
        return _result("snapshot_assente", "Fotografia del mercato non disponibile: riprova.")
    # soglia d'ORDINE, non di lettura: qui si attraversa lo spread davvero.
    if not snap.order_fresh:
        return _result("feed_stantio",
                       "Feed non aggiornato: chiudere ora userebbe prezzi vecchi. Riprova tra qualche secondo.")
    reconciling = E.has_unknown_orders(ctx)
    cv = E.cashout_value(ctx.legs, snap.books, C.commission_rate(params),
                         int(params["cashout_place_at_ticks"]), goals=snap.goals)
    live = [l for l in ctx.legs if l.is_live]
    if not live and not E.live_open_selections(ctx.legs, snap.goals):
        # nulla da annullare e nulla da chiudere: si registra comunque il divieto
        # di rientro pre-KO (l'utente ha detto "chiudi questa partita")
        ctx.close_reason = "manual"
        if not snap.inplay:
            ctx.no_reentry = True
        ev.update(_row_from_ctx(ev, ctx, extra))
        db.upsert_event(ev)
        msg = "Nessuna posizione da chiudere."
        if not cv.complete:
            msg = "Prezzi non disponibili sulle selezioni ancora in gioco: nessuna chiusura possibile."
        return _result("niente_da_chiudere", msg, cashout=cv.net, complete=cv.complete)
    # 1) annullo immediato degli ordini vivi (la gamba a esito IGNOTO non si
    #    tocca mai: C3)
    cancelled = 0
    in_verifica = 0
    for leg in live:
        extra["deferred"] = [x for x in (extra.get("deferred") or []) if x.get("ref") != leg.ref]
        # C.12a — l'annullamento ARRIVA a Betfair prima che la riga lo dichiari.
        esito = _mark_trade_cancelled(db, eid, leg, "cancelled_manual", market=market)
        db.log("cancel", {"leg": leg.ref, "role": leg.role, "by": "utente",
                          "esito": esito}, eid)
        if esito == E.STATUS_RECONCILE:
            in_verifica += 1
        else:
            cancelled += 1
    # 2) la chiusura la guida l'engine (stesso ciclo): mai un doppio percorso
    ctx.flatten_pending = True
    ctx.close_reason = "manual"
    ctx.attempts = 0
    if not snap.inplay:
        ctx.no_reentry = True
    ev.update(_row_from_ctx(ev, ctx, extra))
    db.upsert_event(ev)
    label = "Cash out" if kind == "cashout" else "Flatten"
    parts = []
    if cancelled:
        parts.append(f"annullati {cancelled} ordini sul book")
    if in_verifica:
        parts.append(f"{in_verifica} annullamenti NON confermati da Betfair (in verifica)")
    parts.append(f"chiusura in corso (netto stimato {cv.net:.2f} EUR)")
    msg = f"{label}: " + ", ".join(parts) + "."
    if reconciling or in_verifica:
        msg += " ATTENZIONE: un ordine e' in riconciliazione, l'esposizione reale potrebbe differire."
    return _result("ok", msg, ok=True, cancelled=cancelled, phase="armed",
                   in_verifica=in_verifica,
                   cashout_net=cv.net, complete=cv.complete,
                   warning="reconcile" if (reconciling or in_verifica) else None)


def ferma_al_nuovo_avvio(db: Any = _real_db, now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """FASE A — se questo processo viene da un AVVIO NUOVO dell'app, Mike si
    ferma: ``status='stopped'``, ``mode='paper'``, attivita' ``avvio_app_bot_fermato``.

    I ``params`` (soglie, stake, tetti) NON si toccano: qui si scrive solo lo
    stato e la modalita'. Un riavvio dal watchdog (stesso ``APP_BOOT_ID``) non
    tocca niente: il bot che l'utente ha acceso non muore a ogni crash.

    Ritorna il riepilogo di cio' che e' stato azzerato, ``None`` se non c'era
    niente da fare o se il controllo non si e' potuto concludere (in quel caso
    la guardia resta «non fatta» e il ciclo non apre: si riprova al giro dopo).
    """
    now = now or _now()
    try:
        control = db.read_control()
    except Exception as ex:  # noqa: BLE001 — si riprova al giro dopo, intanto non si apre
        logger.warning("[mike] controllo d'avvio: read_control KO: %s", str(ex)[:160])
        return None
    if control is None:
        # nessuna riga di controllo: non c'e' niente che possa operare.
        _GUARDIA_AVVIO.fatto = True
        return None
    try:
        return AA.ferma_al_nuovo_avvio(_GUARDIA_AVVIO, control=control,
                                       set_control=db.set_control, log=db.log,
                                       now_iso=now.isoformat())
    except Exception as ex:  # noqa: BLE001
        logger.critical("[mike] controllo d'avvio NON riuscito (%s): "
                        "nessuna apertura finche' non riesce.", str(ex)[:160])
        return None


def run_once(*, db: Any = _real_db, market: Any = _real_market, now: Optional[datetime] = None,
             atlas: Optional[Dict[str, Any]] = None, rows: Optional[List[Dict[str, Any]]] = None,
             dry: bool = False) -> Dict[str, Any]:
    now = now or _now()
    now_ts = now.timestamp()
    try:
        control = db.read_control()
    except Exception as ex:  # noqa: BLE001
        logger.warning("[mike] read_control KO: %s", str(ex)[:160])
        return {"skipped": "control_unreadable"}
    if control is None:
        return {"skipped": "no_control"}
    status = str(control.get("status") or "idle")
    mode = str(control.get("mode") or "paper")
    if mode not in ("paper", "live"):
        mode = "paper"
    params = C.merge_params(control.get("params"))
    global _ULTIMI_PARAMS
    _ULTIMI_PARAMS = params
    # FASE A — finche' il controllo d'avvio non si e' concluso (database muto
    # in avvio) il bot NON apre: non sapere da quale avvio si viene e' il caso
    # in cui si sta fermi. Le protezioni qui sotto girano comunque.
    running = status == "running" and not _GUARDIA_AVVIO.blocca_aperture
    eff = _params_for(params, running, mode)
    _config_warn(db, params)

    # LE RICHIESTE SI LEGGONO UNA VOLTA SOLA (14/09). Erano due select al giro
    # sulla stessa tabella — le richieste in attesa e quelle rimaste appese —
    # cioe' 68 letture al minuto per una tabella quasi sempre vuota. E' la stessa
    # domanda posta due volte. Nessuna delle due va in cache: una richiesta della
    # UI deve partire SUBITO, ed e' il motivo per cui questa lettura e' rimasta
    # fuori da tutte le cache del respiro (COSTITUZIONE §17).
    richieste_in_attesa: Optional[List[Dict[str, Any]]] = None
    richieste_bloccate: Optional[List[Dict[str, Any]]] = None
    leggi_insieme = getattr(db, "requests_da_lavorare", None)
    if callable(leggi_insieme):
        try:
            richieste_in_attesa, richieste_bloccate = leggi_insieme()
        except Exception as ex:  # noqa: BLE001 — si ripiega sulle due letture separate
            logger.warning("[mike] lettura richieste KO: %s", str(ex)[:120])
            richieste_in_attesa = richieste_bloccate = None

    # M2: richieste rimaste in 'processing' (crash) chiuse a OGNI ciclo, altrimenti
    # quella partita non accetta piu' nessun cash out.
    # L'ombrello sta FUORI e copre entrambe le chiamate: in Python un'eccezione
    # sollevata DENTRO una clausola ``except`` non viene catturata dalle clausole
    # successive dello stesso ``try``, quindi il ripiego era scoperto e una sua
    # eccezione avrebbe fatto saltare l'intero giro.
    try:
        try:
            db.fail_stale_processing(_STALE_REQUEST_MIN, rows=richieste_bloccate)
        except TypeError:      # accessore vecchio senza il parametro (fake dei test)
            db.fail_stale_processing(_STALE_REQUEST_MIN)
    except Exception as ex:  # noqa: BLE001
        logger.warning("[mike] fail_stale_processing KO: %s", str(ex)[:120])

    # feed unico: UNA lettura ogni ``feed_cache_s``, non a ogni giro.
    # Lo scanner non lo aggiorna piu' in fretta di cosi', e la FRESCHEZZA delle
    # quote continua a essere giudicata sull'``updated_at`` della riga (vedi
    # ``feed.feed_fresh``): una riga vecchia resta vecchia anche rileggendola.
    if rows is None:
        ttl_feed = float(params.get("feed_cache_s") or 0.0)
        if _CACHE_FEED.fresco(now_ts, ttl_feed):
            rows = _CACHE_FEED.valore
        else:
            rows = _CACHE_FEED.metti(list(db.fetch_scan_rows() or []), now_ts)
    rows_by_event = {str(r.get("event_id")): r for r in rows if r.get("event_id")}
    scanner_age = _scanner_age(db, now_ts)

    # partite seguite (stato persistito): ANCHE le terminali recenti (SKIPPED/
    # SETTLED), così non vengono ri-armate come nuove candidate
    # Rilettura COMPLETA ogni ``events_reload_s``; fra una e l'altra vale la
    # copia in memoria, che il ciclo aggiorna scrivendoci sopra. E' corretto
    # perche' il servizio e' l'UNICO che scrive ``mike_events``: le richieste
    # della UI passano da ``mike_requests``, che si legge a parte a ogni giro.
    global _EVENTI_LETTI_A
    ttl_eventi = float(params.get("events_reload_s") or 0.0)
    if _CACHE_EVENTI and (now_ts - _EVENTI_LETTI_A) < ttl_eventi:
        tracked = _CACHE_EVENTI
    else:
        try:
            since = datetime.fromtimestamp(now_ts - 48 * 3600, tz=timezone.utc).isoformat()
            letti = {str(e["event_id"]): e for e in (db.list_events(since_iso=since) or [])}
        except Exception as ex:  # noqa: BLE001
            db.log("error", {"reason": "events_failed", "err": str(ex)[:160]})
            # Il database non risponde. Se abbiamo gia' una copia in memoria si
            # continua a lavorare con quella invece di fermare TUTTO: una
            # posizione aperta non puo' restare senza nessuno che la guardi
            # perche' una select e' andata in timeout.
            if not _CACHE_EVENTI:
                return {"skipped": "events_unreadable"}
            letti = None
        if letti is not None:
            _CACHE_EVENTI.clear()
            _CACHE_EVENTI.update(letti)
            _EVENTI_LETTI_A = now_ts
        tracked = _CACHE_EVENTI
    for ev in tracked.values():
        ev.setdefault("mode", mode)

    # STOP giornaliero (L3): P&L della giornata operativa (Europe/Rome, giorno di
    # PIAZZAMENTO — M6) = REGOLATO + BLOCCATO. Il bloccato sono i cicli già
    # chiusi/greenati non ancora pagati dal mercato: prima erano invisibili allo
    # stop e il bot continuava ad aprire dopo aver già perso il massimo.
    agg = _aggregates_cached(db, now, params)
    day_start_ts = _operating_day_start_ts(now)
    locked_open = _locked_open_pnl(tracked, params, day_start_ts, mode)
    realized_today = float(agg.get("realized_today", 0.0))
    day_pnl = round(realized_today + locked_open, 2)
    # ALLARME: partite ancora vive armate nella modalita' OPPOSTA. Il `mode` si
    # congela sulla partita quando viene armata, quindi riportare il toggle su
    # paper NON ferma quelle gia' avviate in live: continuano a coprirsi,
    # chiudere e fare cash-out con soldi VERI mentre la pagina dice PAPER.
    divergenti = partite_di_modalita_diversa(tracked, mode)
    if divergenti:
        logger.critical("[mike] %d partite ancora VIVE in modalita' diversa da '%s': %s — "
                        "continuano a operare con le regole di QUELLA modalita'",
                        len(divergenti), mode, ", ".join(divergenti[:6]))
    stop = float(params.get("daily_loss_stop") or 0.0)
    daily_stop = stop > 0 and day_pnl <= -stop
    if daily_stop:
        # H1 (review): anche l'ULTIMO INGRESSO (PERSIST) e' un ingresso nuovo —
        # senza spegnerlo `_after_final_green` piazzava ancora `under_last`.
        eff = dict(eff, pre_enabled=False, reentry_enabled=False, last_entry_persist=False)
        day_key = _operating_day_key(now)
        if _DAILY_STOP_LOGGED.get("day") != day_key:
            _DAILY_STOP_LOGGED["day"] = day_key
            logger.warning("[mike] STOP giornaliero: P&L oggi %.2f (regolato %.2f + bloccato %.2f) <= -%.2f",
                           day_pnl, realized_today, locked_open, stop)
            db.log("daily_stop", {"day_pnl": day_pnl, "realized_today": round(realized_today, 2),
                                  "locked_open": round(locked_open, 2), "stop": stop,
                                  "day": day_key})

    n_requests = process_requests(db=db, market=market, events=tracked, rows_by_event=rows_by_event,
                                  params=params, eff=eff, now=now, dry=dry, scanner_age=scanner_age,
                                  reqs=richieste_in_attesa)
    open_refs = _open_refs_by_event(db)      # H5: una query per il pre-controllo H2

    # nuove candidate (solo a bot in esecuzione, sotto il tetto partite)
    n_new = 0
    if running and not daily_stop:
        # tetto = partite con POSIZIONE (o ordini): quelle solo osservate (WATCH) o
        # in-play senza posizione (IDLE_LIVE) non bloccano le nuove candidate
        active = sum(1 for e in tracked.values()
                     if e.get("state") not in E.TERMINAL_STATES and e.get("state") not in ("WATCH", "IDLE_LIVE"))
        for eid, row in rows_by_event.items():
            if eid in tracked or active >= int(params["max_open_matches"]):
                continue
            payload = row.get("payload") or {}
            info = F.event_info(eid, payload)
            if not F.is_candidate(info, payload, now=now_ts, params=params):
                continue
            dossier = D.build_prematch(eid, db)
            tracked[eid] = {
                "event_id": eid, "fixture_id": dossier.get("fixture_id"), "event_name": info.event_name,
                "competition": info.competition, "league_id": dossier.get("league_id"),
                "ko_at": _iso(info.ko_at), "markets": {m: {"market_id": info.market_id(m)} for m in info.markets},
                "state": "WATCH", "cycle_no": 0, "entry_price_initial": None, "dossier": dossier,
                "live": {}, "positions": [], "skipped": False, "settled_pnl": None, "mode": mode, "ctx": {},
            }
            active += 1
            n_new += 1
            db.log("armed", {"event": info.event_name, "ko": _iso(info.ko_at), "dossier": dossier}, eid)

    # CERT. 12/09 -- RITENTATIVO DEL DOSSIER.
    # ``build_prematch`` girava UNA SOLA VOLTA, alla presa in carico della
    # partita. Se in quel momento la fixture non era ancora abbinata, il dossier
    # restava vuoto PER SEMPRE: niente gol attesi, niente griglia Poisson, e il
    # bot decideva senza modello per tutta la partita. E' cosi' che tutti e 93
    # gli eventi si sono ritrovati con ``source: "none"``.
    # Ora una partita ancora viva col dossier cieco riprova, al massimo ogni
    # ``_DOSSIER_RETRY_SEC``: il catalogo di Omega si popola nel tempo, e una
    # fixture che arriva dopo deve poter accendere il modello.
    _retry_dossier(db, tracked, now_ts)

    # ciclo per partita
    n_actions = n_settled = 0
    # PARTITE CHE CONSUMANO IL TETTO: quelle con soldi davvero sopra (stato
    # operativo, oppure una gamba viva o abbinata). Si parte dal conto vero di
    # adesso e lo si aggiorna DURANTE il giro: se una partita entra, il posto e'
    # occupato subito e la successiva lo trova gia' preso. Senza questo, dentro
    # lo stesso giro entrerebbero tutte insieme — che e' esattamente il difetto
    # che stiamo chiudendo.
    #
    # ⚠️ 15/09 — e i posti sono SEPARATI PER MODALITA': vedi
    # `posti_occupati_per_modo`, che dice perche' sommarli fermava il live.
    esposte_per_modo = posti_occupati_per_modo(tracked, mode)
    cap_partite = int(eff.get("max_open_matches") or 0)
    # quante partite il tetto ha fermato in questo giro: serve a SCRIVERLO in
    # pagina, non a decidere.
    bloccate_dal_tetto = 0
    trades_cache: Dict[str, List[Dict[str, Any]]] = {}
    # le riscritture di sola CORTESIA (rinfresco dell'ora di pubblicazione) del
    # giro: si accumulano qui e partono in UNA sola POST a fine ciclo. Le
    # scritture che portano un fatto nuovo NON ci passano: partono subito.
    lotto_eventi: Dict[str, Dict[str, Any]] = {}
    try:
        for eid, ev in list(tracked.items()):
            try:
                # il tetto si misura SOLO fra partite della STESSA modalita'
                modo_ev = str(ev.get("mode") or mode)
                pari_modo = esposte_per_modo.setdefault(modo_ev, set())
                gia_dentro = str(eid) in pari_modo
                puo_aprire = (gia_dentro or cap_partite <= 0
                              or len(pari_modo) < cap_partite)
                if not puo_aprire:
                    bloccate_dal_tetto += 1
                acted, settled = _run_event(db=db, market=market, ev=ev, row=rows_by_event.get(eid),
                                            params=eff, mode=modo_ev, now=now,
                                            scanner_age=scanner_age, atlas=atlas, dry=dry,
                                            cache=trades_cache, open_refs=open_refs,
                                            lotto=lotto_eventi,
                                            # una partita GIA' esposta non e' mai bloccata: deve
                                            # poter fare tutto, comprese le aperture del ciclo
                                            # successivo, altrimenti resterebbe a meta' strada.
                                            puo_aprire=puo_aprire)
                if not gia_dentro and E.ha_esposizione(ev.get("state"), _ctx_legs_of(ev)):
                    pari_modo.add(str(eid))   # il posto e' occupato da adesso
                n_actions += acted
                n_settled += settled
            except Exception as ex:  # noqa: BLE001 — una partita rotta non ferma le altre
                logger.exception("[mike] evento %s KO: %s", eid, str(ex)[:160])
                db.log("error", {"reason": "event_cycle", "err": str(ex)[:160]}, eid)
    finally:
        # SEMPRE: il lotto non deve sopravvivere al giro nemmeno se il ciclo
        # esplode a meta'. Rallentare una scrittura e' permesso, perderla no.
        _svuota_lotto(db, lotto_eventi, params)

    if status == "stopping":
        try:
            db.set_control(status="stopped", stopped_at=now.isoformat())
            db.log("stop", {})
        except Exception:  # noqa: BLE001
            pass
        status = "stopped"

    if n_actions or n_settled or n_requests:
        agg = _aggregates_cached(db, now, params, forza=True)   # qualcosa e' cambiato
        locked_open = _locked_open_pnl(tracked, params, day_start_ts, mode)
    by_state: Dict[str, int] = {}
    for e in tracked.values():
        by_state[str(e.get("state"))] = by_state.get(str(e.get("state")), 0) + 1
    # M4 — capitale a rischio VERO: perdita peggiore delle posizioni NETTE
    # aperte, partita per partita (un back coperto da lay non e' back + lay).
    open_liability = _open_liability(tracked, params, mode)
    realized_today = float(agg.get("realized_today", 0.0))
    # QUANTA FRETTA HA IL PROSSIMO GIRO (13/09). Il ciclo pieno serve quando c'e'
    # qualcosa che si muove da solo: una partita in gioco (i prezzi cambiano a
    # ogni secondo), un ordine vivo sul book, una richiesta dalla UI. Senza
    # niente di tutto questo -- la notte, o fra una giornata di partite e
    # l'altra -- girare ogni secondo vuol dire solo consumare il budget di IO del
    # database per rileggere cose ferme.
    c_e_fretta = bool(n_requests) or any(
        (e.get("live") or {}).get("inplay")
        or any(str(l.get("status")) in ("pending", "pending_reconcile")
               for l in (e.get("positions") or []))
        for e in tracked.values()
        if str(e.get("state")) not in E.TERMINAL_STATES)
    stats = {
        "events_feed": len(rows_by_event), "events_tracked": len(tracked), "by_state": by_state,
        "trades_open": int(agg.get("open_count", 0)), "open_liability": open_liability,
        # partite ancora vive armate nella modalita' OPPOSTA a quella corrente:
        # la pagina ci mette sopra un avviso rosso, perche' altrimenti il banner
        # direbbe PAPER mentre quelle partite spendono davvero
        "eventi_altra_modalita": len(divergenti),
        # il live e' fisicamente abilitato su questo processo?
        "live_abilitato": mike_live_abilitato(),
        "open_liability_rows": round(float(agg.get("open_liability", 0.0)), 2),
        "realized_today": round(realized_today, 2),
        "realized_total": round(float(agg.get("realized_total", 0.0)), 2),
        "locked_open": round(locked_open, 2),
        "day_pnl": round(realized_today + locked_open, 2),
        "won_today": int(agg.get("won_today", 0)), "lost_today": int(agg.get("lost_today", 0)),
        "cycles_today": int(agg.get("cycles_today", 0)), "events_today": int(agg.get("events_today", 0)),
        "live_now": sum(1 for e in tracked.values() if (e.get("live") or {}).get("inplay")),
        "scanner_age_s": round(scanner_age, 1) if scanner_age is not None else None,
        # ── QUELLO CHE IL BOT DECIDE, SCRITTO (15/09) ────────────────────────
        # Un trader non deve dedurre perche' il bot non apre: deve leggerlo.
        # Il tetto e' PER MODALITA' — i soldi finti non occupano il posto dei
        # soldi veri — quindi si pubblicano tutti e due i conti, mai la somma.
        "tetto_partite": cap_partite,
        "partite_esposte": len(esposte_per_modo.get(mode, ())),
        "partite_esposte_live": len(esposte_per_modo.get("live", ())),
        "partite_esposte_paper": len(esposte_per_modo.get("paper", ())),
        "aperture_bloccate": int(bloccate_dal_tetto),
        "motivo_blocco": (
            f"tetto partite raggiunto: {len(esposte_per_modo.get(mode, ()))} "
            f"su {cap_partite} in {mode}"
        ) if bloccate_dal_tetto else None,
        # Con che passo questo battito si ripete: la pagina deve giudicare la
        # vitalita' con la cadenza VERA del servizio, non con una costante
        # scritta nel frontend (che sarebbe una seconda verita').
        "cadenza_battito_s": _cadenza_battito(params),
        # FERMARE il bot toglie le APERTURE, non le uscite: coperture, green-up,
        # cash-out e settlement continuano, ed e' giusto — una posizione aperta
        # non si abbandona. Ma il pulsante deve dirlo, o promette una cosa che
        # non fa.
        "stop_ferma_solo_aperture": True,
        # F5: com'e' andata la sveglia del ciclo (``None`` a interruttore
        # spento). Sta FUORI dal battito: vedi ``beat`` piu' sotto.
        "sveglia": statistiche_sveglia(),
        "last_cycle": now.isoformat(), "dry": bool(dry), "mode": mode, "daily_stop": bool(daily_stop),
        "reconciling": sum(1 for e in tracked.values()
                           if any(str((l or {}).get("status")) == E.STATUS_RECONCILE
                                  for l in (e.get("positions") or []))),
    }
    # I NUMERI DI TESTATA VANNO SULLO SCHERMO A OGNI GIRO (14/09). La scrittura
    # su ``mike_control`` resta rallentata qui sotto — e' ascoltata in realtime da
    # tutte le pagine aperte e ogni PATCH le sveglia tutte — ma il socket locale
    # non ha nessuno di quei costi: P&L, liability e KPI si aggiornano al ritmo
    # del bot. Se l'app desktop non e' collegata questa riga non fa nulla.
    _pubblica_stato(control, agg, stats, now_ts)

    # H5 — la UI ascolta mike_control in REALTIME: un battito a ogni ciclo la
    # faceva ricaricare ogni secondo. M6 (review): non basta "cambiato", perche'
    # una stat cambia quasi sempre (P&L, liability) → si scriveva comunque a
    # ogni ciclo. Regola: stats al massimo ogni ``stats_min_s`` se qualcosa e'
    # cambiato, e comunque un battito ogni ``heartbeat_min_s``.
    #
    # 13/09 (secondo tempo) — le due soglie erano numeri fissi nel codice (5 e
    # 10 s) e valevano 12 PATCH al minuto su una tabella che la UI ascolta in
    # realtime, cioe' 12 risvegli al minuto di ogni pagina aperta. Ora sono
    # parametri: 10 s per le stats, 20 s per il battito nudo. Il margine c'e':
    # ``ServiceHealthChip.SERVICE_STALE_S`` dichiara il servizio morto a 45 s,
    # quindi anche saltando un battito il badge resta verde.
    # F5 (18/09): ``sveglia`` sta FUORI dal battito, esattamente come
    # ``scanner_age_s``. Sono contatori che crescono da soli: dentro la firma
    # renderebbero «cambiato» ogni giro e farebbero salire le PATCH su
    # ``mike_control``, che la UI ascolta in realtime - il contrario di questa
    # fase, che non deve far crescere una sola scrittura al minuto.
    beat = {k: v for k, v in stats.items()
            if k not in ("last_cycle", "scanner_age_s", "sveglia")}
    # zero = "a ogni giro": e' la valvola per tornare al comportamento di prima
    # senza toccare il codice (e la UI lo ammette, min 0 su entrambi). Da qui il
    # ``if ... is None`` invece di ``or``: con ``or`` uno zero scritto apposta
    # diventerebbe il default, cioe' l'opposto di quello che il trader ha chiesto.
    _hb = params.get("heartbeat_min_s")
    _st = params.get("stats_min_s")
    stats_min_s = float(C.DEFAULTS["stats_min_s"] if _st is None else _st)
    heartbeat_min_s = float(C.DEFAULTS["heartbeat_min_s"] if _hb is None else _hb)
    changed = _LAST_HEARTBEAT.get("sig") != _signature(beat)
    elapsed = now_ts - float(_LAST_HEARTBEAT.get("ts") or 0.0)
    if (changed and elapsed >= stats_min_s) or elapsed >= heartbeat_min_s:
        _LAST_HEARTBEAT["sig"] = _signature(beat)
        _LAST_HEARTBEAT["ts"] = now_ts
        try:
            # ⚠️ ``timbra``: l'``APP_BOOT_ID`` vive dentro ``stats``, che qui si
            # riscrive per INTERO. Senza il timbro l'id sparirebbe al primo
            # battito e il crash successivo verrebbe scambiato per un avvio
            # nuovo, spegnendo il bot che l'utente aveva appena acceso.
            db.set_control(stats=_GUARDIA_AVVIO.timbra(stats), heartbeat_at=now.isoformat())
        except Exception as ex:  # noqa: BLE001
            logger.warning("[mike] set_control KO: %s", str(ex)[:160])
    return {"status": status, "fretta": c_e_fretta,
            "new": n_new, "actions": n_actions, "settled": n_settled,
            "requests": n_requests, "stats": stats}


def _operating_day_start_ts(now: datetime) -> float:
    """Epoch della mezzanotte di Roma della giornata operativa corrente."""
    from Betfair.safe_strategy import risk as _risk

    return _risk.operating_day_start(now).timestamp()


def _operating_day_key(now: datetime) -> str:
    """Giorno operativo (Europe/Rome) in ISO: L2 — lo stop giornaliero si logga
    una volta per GIORNATA OPERATIVA, non per giorno UTC (alle 23:30 UTC a Roma
    e' gia' il giorno dopo)."""
    from Betfair.safe_strategy import risk as _risk

    start = _risk.operating_day_start(now)        # mezzanotte di Roma, in UTC
    return (start + _timedelta(hours=12)).date().isoformat()


def _ctx_legs_of(ev: Dict[str, Any]) -> List[E.Leg]:
    return _legs_from_json(ev.get("positions"), None, ev.get("event_id"))


def _open_liability(tracked: Dict[str, Dict[str, Any]], params: Dict[str, Any],
                    mode: Optional[str] = None) -> float:
    """Somma delle liability NETTE delle partite non terminali (M4).

    13/09 — con ``mode`` si contano SOLO le partite di quella modalita'. Il
    rischio di una partita in paper non e' rischio, e sommarlo a quello vero
    falsa il cap e lo stop giornaliero.
    """
    c = C.commission_rate(params)
    tot = 0.0
    for ev in tracked.values():
        if str(ev.get("state")) in E.TERMINAL_STATES:
            continue
        if mode is not None and str(ev.get("mode") or "paper") != str(mode):
            continue
        tot += E.event_liability(_ctx_legs_of(ev), c)
    return round(tot, 2)


def posti_occupati_per_modo(tracked: Dict[str, Dict[str, Any]],
                            mode: str) -> Dict[str, set]:
    """Le partite che OCCUPANO UN POSTO, tenute separate per modalita'.

    ⚠️ 15/09 — QUESTO CONTO SOMMAVA PAPER E LIVE.

    Il ``mode`` si congela sulla partita quando viene armata, quindi nel
    ``tracked`` convivono partite delle due modalita'. Contandole insieme, una
    vecchia posizione PAPER rimasta viva occupava un posto REALE: col tetto a 1
    il bot in live non apriva piu' nulla — e in pagina non c'era scritto da
    nessuna parte perche'. Un trader non puo' dedurlo: vede un bot fermo.

    I soldi finti non possono occupare il posto dei soldi veri, ne' viceversa:
    il tetto vale DENTRO una modalita'. Chi non dichiara la sua eredita quella
    corrente del servizio.
    """
    fuori: Dict[str, set] = {}
    for eid, ev in (tracked or {}).items():
        if E.ha_esposizione(ev.get("state"), _ctx_legs_of(ev)):
            fuori.setdefault(str(ev.get("mode") or mode), set()).add(str(eid))
    return fuori


def _cadenza_battito(params: Optional[Dict[str, Any]]) -> float:
    """Ogni QUANTI SECONDI, nel caso peggiore, questo servizio batte.

    ⚠️ 15/09 — la pagina giudicava la vitalita' dei bot con una costante
    scritta nel frontend. Era una SECONDA VERITA': se qui dentro si allarga la
    cadenza (ed e' successo il 13/09, per far respirare il database), il
    frontend non lo sa e continua a misurare col metro vecchio — o chiama morto
    un bot vivo, o chiama vivo un bot morto. La cadenza la dichiara CHI BATTE.

    Due cose la determinano insieme, e vince la piu' lenta:
      * il passo del ciclo quando non si muove niente (``idle_cycle_s``, e
        comunque mai sotto il doppio di ``decide_min_interval_ms``);
      * il freno sulle scritture: un battito al massimo ogni
        ``heartbeat_min_s`` (13/09, per non svegliare le pagine aperte).
    """
    p = params or {}

    def _num(chiave: str, difetto: float) -> float:
        v = p.get(chiave)
        if v is None:
            v = C.DEFAULTS.get(chiave)
            if isinstance(v, tuple):       # (default, tipo, min, max, ...)
                v = v[0]
        try:
            f = float(v)                   # type: ignore[arg-type]
        except (TypeError, ValueError):
            return difetto
        return f if f > 0 else difetto

    passo = max(1.0, _num("decide_min_interval_ms", 500.0) / 1000.0 * 2.0)
    passo = max(passo, _num("idle_cycle_s", 5.0))
    return round(max(passo, _num("heartbeat_min_s", 20.0)), 1)


def partite_di_modalita_diversa(tracked: Dict[str, Dict[str, Any]], mode: str) -> List[str]:
    """Partite ancora VIVE armate in una modalita' diversa da quella corrente.

    E' il caso pericoloso: il `mode` si congela sulla partita quando viene
    armata, quindi riportare il toggle su paper NON ferma le partite gia'
    avviate in live — continuano a coprirsi, chiudere e fare cash-out con soldi
    veri mentre il banner della pagina dice PAPER. Chi le trova deve gridarlo.
    """
    return [str(ev.get("event_id")) for ev in tracked.values()
            if str(ev.get("state")) not in E.TERMINAL_STATES
            and str(ev.get("mode") or "paper") != str(mode)]


def _first_placed_at(legs: List[E.Leg]) -> Optional[float]:
    """Epoch del PRIMO piazzamento della partita (giorno operativo della posizione)."""
    ts = [float(l.placed_at) for l in legs if float(l.placed_at or 0.0) > 0.0]
    return min(ts) if ts else None


def _locked_open_pnl(tracked: Dict[str, Dict[str, Any]], params: Dict[str, Any],
                     day_start_ts: Optional[float] = None,
                     mode: Optional[str] = None) -> float:
    """P&L già BLOCCATO sulle partite non ancora regolate (L3): cicli chiusi in
    green o in perdita che il mercato non ha ancora pagato. Le partite con
    esposizione viva NON contano (nulla e' deciso).

    M1 (review): solo le partite della GIORNATA OPERATIVA corrente (primo
    piazzamento ≥ mezzanotte di Roma). La finestra degli eventi seguiti e' di
    48 h: sommare il bloccato di ieri nello stop di oggi lo faceva scattare per
    un P&L che non appartiene alla giornata.
    """
    c = C.commission_rate(params)
    tot = 0.0
    for ev in tracked.values():
        if str(ev.get("state")) in E.TERMINAL_STATES:
            continue
        # 13/09 — mai il bloccato di una partita in paper dentro lo stop del
        # live (e viceversa): sono due contabilita' diverse
        if mode is not None and str(ev.get("mode") or "paper") != str(mode):
            continue
        legs = _ctx_legs_of(ev)
        if day_start_ts is not None:
            first = _first_placed_at(legs)
            if first is None or first < float(day_start_ts):
                continue
        v = E.locked_pnl(legs, c)
        if v is not None:
            tot += v
    return round(tot, 2)


def _config_warn(db: Any, params: Dict[str, Any]) -> None:
    """M8 — la finestra pre-match di Mike non puo' essere piu' ampia del ramo
    pre-KO dello scanner: oltre quell'ora le linee non sono nel feed e il bot
    vedrebbe 0 candidate SENZA dirlo."""
    scanner_h = C.env_float("SAFE_PRE_KO_OU_HOURS", 0.0)
    entry_h = float(params.get("entry_hours_before_ko") or 0.0)
    if scanner_h <= 0:
        msg = ("Il ramo pre-KO dello scanner e' SPENTO (SAFE_PRE_KO_OU_HOURS non impostata): "
               "nessuna linea Under 3.5 / Over 4.5 prima del calcio d'inizio, Mike non vedra' "
               "nessuna candidata.")
        key = "off"
    elif entry_h > scanner_h + 1e-9:
        msg = (f"Finestra di ingresso {entry_h:g} h piu' ampia del ramo pre-KO dello scanner "
               f"({scanner_h:g} h): fra {scanner_h:g} h e {entry_h:g} h prima del KO le linee non "
               f"sono nel feed e le partite non vengono armate. Allinea SAFE_PRE_KO_OU_HOURS "
               f"o entry_hours_before_ko.")
        key = f"{entry_h:g}>{scanner_h:g}"
    else:
        _CONFIG_WARNED.pop("key", None)
        return
    if _CONFIG_WARNED.get("key") == key:
        return
    _CONFIG_WARNED["key"] = key
    logger.warning("[mike] config: %s", msg)
    db.log("config_warn", {"message": msg, "entry_hours_before_ko": entry_h,
                           "scanner_pre_ko_hours": scanner_h, "critical": True})


def _run_event(*, db: Any, market: Any, ev: Dict[str, Any], row: Optional[Dict[str, Any]],
               params: Dict[str, Any], mode: str, now: datetime, scanner_age: Optional[float],
               atlas: Optional[Dict[str, Any]], dry: bool,
               cache: Optional[Dict[str, List[Dict[str, Any]]]] = None,
               open_refs: Optional[Dict[str, set]] = None,
               lotto: Optional[Dict[str, Dict[str, Any]]] = None,
               puo_aprire: bool = True) -> "tuple[int, int]":
    """Un giro per una partita: snapshot → decide → azioni → persistenza. (azioni, settled).

    ``lotto`` e' il raccoglitore delle riscritture di sola CORTESIA (rinfresco
    dell'ora di pubblicazione): il chiamante lo svuota in una sola POST a fine
    giro. Le scritture che portano un fatto nuovo non ci passano mai (vedi
    ``_persist``)."""
    now_ts = now.timestamp()
    if str(ev.get("state")) in E.TERMINAL_STATES:
        return (0, 0)
    # H3 — i parametri EFFETTIVI dipendono dal mode della PARTITA, non solo da
    # quello del control (una partita live con il control tornato in paper
    # riceveva 'resting' su soldi veri).
    params = _live_exit_override(params, mode)
    ctx = _ctx_from_row(ev, db)
    extra = dict(ev.get("ctx") or {})
    before_sig = _signature(ev)
    payload = (row or {}).get("payload") or {}
    info = F.event_info(ev["event_id"], payload) if row is not None else None
    dossier = ev.get("dossier") or {}
    settled = 0

    # -- H2: specchio gambe <-> righe -------------------------------------------
    # E' una RETE DI SICUREZZA (ripara righe mancanti o disallineate), non un
    # passaggio del flusso: chiedere le righe di ordine di ogni partita a OGNI
    # giro voleva dire una query al secondo per partita viva. Ogni mezzo minuto
    # ripara le stesse cose, e il database respira.
    _eid = str(ev["event_id"])
    _ogni = float(params.get("reconcile_every_s") or 0.0)
    if now_ts - float(_RICONCILIATO_A.get(_eid) or 0.0) >= _ogni:
        _RICONCILIATO_A[_eid] = now_ts
        _reconcile_trades(db, ev["event_id"], ctx, info, mode, params, cache, open_refs)

    # -- riga sparita dal feed o mercato chiuso: settlement via REST -------------
    # Una riga ASSENTE e' "chiusa" solo se manca da >= _ROW_MISSING_GRACE_S o se
    # la partita e' comunque finita (KO + 3h): al calcio d'inizio il feed passa dal
    # blocco pre-KO a quello in-play e la riga puo' sparire per qualche minuto
    # (refresh catalogo 300 s) — prima veniva scambiata per un regolamento.
    ko_ts = float(F.parse_iso_epoch(ev.get("ko_at")) or 0.0)
    status_closed = row is not None and str((F.ou_blocks(payload).get(E.MARKET_OU35) or {}).get("status") or
                                            payload.get("mo_status") or "").upper() == "CLOSED"
    if row is None:
        extra["row_missing_since"] = float(extra.get("row_missing_since") or now_ts)
        missing_for = now_ts - float(extra["row_missing_since"])
        absent_closed = missing_for >= _ROW_MISSING_GRACE_S or (ko_ts > 0 and (
            now_ts - ko_ts > _MATCH_OVER_S
            or (bool(extra.get("seen_inplay")) and now_ts - ko_ts >= _MATCH_LIKELY_OVER_S)))
    else:
        extra.pop("row_missing_since", None)
        absent_closed = False
    closed = status_closed or absent_closed
    if row is None and not closed and ctx.state not in E.TERMINAL_STATES:
        ev.update(_row_from_ctx(ev, ctx, extra))          # memorizza da quando manca
        _persist(db, ev, before_sig, now_ts=now_ts, params=params, lotto=lotto)
        return (0, 0)
    # falso regolamento gia' scattato (riga tornata, mercato aperto, partita in corso):
    # si torna nello stato coerente con le posizioni aperte
    if ctx.state == "SETTLING" and not closed and row is not None and (ko_ts <= 0 or now_ts - ko_ts < _MATCH_OVER_S):
        opens = E.open_selections(ctx.legs)
        inplay = bool(payload.get("inplay"))
        if (E.MARKET_OU45, E.SEL_OVER) in opens:
            back_to = "LIVE_COVERED"
        elif (E.MARKET_OU45, E.SEL_UNDER) in opens:
            back_to = "REENTRY_OPEN"
        elif (E.MARKET_OU35, E.SEL_UNDER) in opens:
            back_to = "LIVE_UNCOVERED" if inplay else "PRE_OPEN"
        else:
            back_to = "IDLE_LIVE" if inplay else "WATCH"
        extra.pop("settle_first_ts", None)
        extra.pop("settle_next_ts", None)
        db.log("settling_reverted", {"to": back_to, "reason": "riga tornata nel feed, mercato aperto"}, ev["event_id"])
        E.apply_decision(ctx, E.Decision(state=back_to, actions=[], reason="falso regolamento annullato"), now_ts)
    if closed and ctx.state not in E.TERMINAL_STATES:
        # throttle delle letture REST di regolamento (review F1 #3): mai un poll
        # stretto su un mercato chiuso; dopo troppo tempo si ripiega sull'ultimo
        # punteggio noto o si va in ERROR (mai SETTLING per sempre)
        if now_ts < float(extra.get("settle_next_ts") or 0.0):
            # L2: si persiste comunque (il throttle e le riparazioni H2 di questo
            # ciclo non devono andare perse)
            ev.update(_row_from_ctx(ev, ctx, extra))
            _persist(db, ev, before_sig, now_ts=now_ts, params=params, lotto=lotto)
            return (0, 0)
        # M3: ``settle_confirm_s`` CABLATO come intervallo fra due letture REST
        extra["settle_next_ts"] = now_ts + max(5.0, float(params.get("settle_confirm_s") or _SETTLE_RETRY_S))
        extra["settle_first_ts"] = float(extra.get("settle_first_ts") or now_ts)
        mkts = ev.get("markets") or {}
        names: Dict[int, str] = {}
        b35 = market.read_book(str((mkts.get(E.MARKET_OU35) or {}).get("market_id") or ""), names) \
            if (mkts.get(E.MARKET_OU35) or {}).get("market_id") else None
        b45 = market.read_book(str((mkts.get(E.MARKET_OU45) or {}).get("market_id") or ""), names) \
            if (mkts.get(E.MARKET_OU45) or {}).get("market_id") else None
        info_s = F.EventInfo(event_id=ev["event_id"], event_name=str(ev.get("event_name") or ""),
                             home=None, away=None, competition=ev.get("competition"),
                             ko_at=F.parse_iso_epoch(ev.get("ko_at")), open_date=ev.get("ko_at"),
                             markets={m: str(v.get("market_id")) for m, v in mkts.items() if v.get("market_id")},
                             selections={tuple(k.split("|")): int(v) for k, v in (extra.get("selections") or {}).items()})
        total = final_total_from_books(b35, b45, info_s)
        # M9 + C4 — mercato ANNULLATO: void PER MERCATO. Solo le gambe del
        # mercato annullato valgono zero; l'altra linea viene regolata dai suoi
        # runner (prima un solo mercato illeggibile azzerava tutta la partita e
        # con 4 gol la perdita reale sull'Under 3.5 spariva).
        #
        # 12/09 (COSTITUZIONE §10.B.1): il ramo per MERCATO vale anche quando il
        # totale gol e' comunque deducibile dall'altra linea. Prima era dentro un
        # ``if total is None``: con la 3.5 che dichiara UNDER (totale = 3) e la
        # 4.5 ANNULLATA si passava dalla strada normale e le gambe della 4.5
        # venivano regolate come UNDER (perdita/vincita inventata) invece che
        # void.
        winners, tele = settle_plan(b35, b45, info_s)
        if winners is not None and tele.get("voided"):
            res = E.settle_legs_by_market(
                ctx.legs, winners, C.commission_rate(_settle_params(db, ev["event_id"], params)))
            settle = {"per_leg": res.per_leg, "per_market": res.per_market, "net": res.net,
                      "per_leg_gross": res.per_leg_gross,
                      "commission_by_market": res.commission_by_market,
                      "void": True}
            E.apply_decision(ctx, E.Decision("SETTLED", [], "regolamento per mercato (void parziale)",
                                             updates={"settled_pnl": res.net}), now_ts)
            ok = _settle_trades(db, ev["event_id"], ctx, settle, params)
            if not ok and _retry_settle_rows(db, ev["event_id"], ctx, extra, now_ts):
                ev.update(_row_from_ctx(ev, ctx, extra))
                _persist(db, ev, before_sig, now_ts=now_ts, params=params, lotto=lotto)
                return (0, 0)
            extra.pop("settle_rows_attempts", None)
            db.log("settled", {"void": True, "reason": "mercato_annullato",
                               "voided": tele.get("voided"), "winners": tele.get("winners"),
                               "pnl": res.net, "legs": len(res.per_leg)}, ev["event_id"])
            ev.update(_row_from_ctx(ev, ctx, extra))
            _persist(db, ev, before_sig, now_ts=now_ts, params=params, lotto=lotto)
            return (0, 1)
        if total is None and now_ts - float(extra["settle_first_ts"]) > _SETTLE_MAX_WAIT_S:
            last_goals = extra.get("last_goals")
            if extra.get("seen_inplay") and last_goals is not None:
                total = int(last_goals)
                db.log("settle_fallback", {"reason": "book_non_leggibile", "total_from_feed": total},
                       ev["event_id"])
            else:
                # Il punteggio serve solo se il P&L DIPENDE dal punteggio. Senza
                # posizioni (finestra pre-match chiusa senza ingressi) o con soli
                # cicli gia' chiusi, il conto e' gia' noto: si chiude e basta,
                # invece di mandare in ERRORE una partita su cui non c'e' niente
                # da sistemare.
                comm = C.commission_rate(_settle_params(db, ev["event_id"], params))
                netto = E.pnl_indipendente_dal_risultato(ctx.legs, comm)
                if netto is not None:
                    db.log("settled", {"reason": "punteggio non recuperabile, ma il risultato "
                                                 "non dipende dal punteggio",
                                       "pnl": netto, "gambe_abbinate":
                                           sum(1 for l in ctx.legs if float(l.matched or 0) > 0)},
                           ev["event_id"])
                    E.apply_decision(ctx, E.Decision("SETTLED", [], "nessuna esposizione: chiusa a %+.2f" % netto,
                                                     updates={"settled_pnl": netto}), now_ts)
                    ev.update(_row_from_ctx(ev, ctx, extra))
                    _persist(db, ev, before_sig, now_ts=now_ts, params=params, lotto=lotto)
                    return (0, 1)
                db.log("error", {"reason": "settle_timeout", "critical": True}, ev["event_id"])
                d = E.Decision(state="ERROR", actions=[], reason="regolamento non determinabile")
                E.apply_decision(ctx, d, now_ts)
                ev.update(_row_from_ctx(ev, ctx, extra))
                _persist(db, ev, before_sig, now_ts=now_ts, params=params, lotto=lotto)
                return (0, 0)
        snap = E.Snapshot(now=now_ts, ko_at=info_s.ko_at or now_ts, books={}, inplay=True,
                          market_status="CLOSED", final_total=total)
        # aliquota di commissione FISSATA sulle righe (cert. 12/09): il P&L di
        # una posizione non cambia perche' l'utente ha toccato un parametro dopo
        # averla aperta
        s_params = _settle_params(db, ev["event_id"], params)
        d = E.decide(ctx, snap, s_params)
        E.apply_decision(ctx, d, now_ts)
        if d.state == "SETTLING" and total is not None:
            d = E.decide(ctx, snap, s_params)    # stesso ciclo: SETTLING -> SETTLED
            E.apply_decision(ctx, d, now_ts)
        if d.state == "SETTLED":
            ok = _settle_trades(db, ev["event_id"], ctx, d.telemetry.get("settle") or {}, s_params)
            if not ok and _retry_settle_rows(db, ev["event_id"], ctx, extra, now_ts):
                ev.update(_row_from_ctx(ev, ctx, extra))
                _persist(db, ev, before_sig, now_ts=now_ts, params=params, lotto=lotto)
                return (0, 0)
            extra.pop("settle_rows_attempts", None)
            settled = 1
            db.log("settled", {"total": total, "pnl": ctx.settled_pnl, **(d.telemetry.get("settle") or {})},
                   ev["event_id"])
        ev.update(_row_from_ctx(ev, ctx, extra))
        _persist(db, ev, before_sig, now_ts=now_ts, params=params, lotto=lotto)
        return (0, settled)
    if row is None or info is None or not info.complete:
        # C1 — la riga c'e' ma una delle due linee NON e' nel feed (tetto dei
        # mercati opportunita' dello scanner): con una posizione aperta questo
        # significa nessuna copertura, nessun cash out, nessuna uscita. Non si
        # inventa un prezzo: si GRIDA e lo si mostra sulla card.
        if info is not None and E.open_selections(ctx.legs):
            # CERTIFICAZIONE 12/09 — UNA sola forma per ``lines_missing``:
            # "MERCATO|SELEZIONE", la stessa scritta dal blocco live piu' sotto.
            # Con i due formati mescolati la UI produceva "undefined 3.5" e il
            # trader leggeva un allarme illeggibile su partite con soldi dentro.
            missing = [f"{m}|{s}" for (m, s) in ((E.MARKET_OU35, E.SEL_UNDER),
                                                 (E.MARKET_OU45, E.SEL_OVER),
                                                 (E.MARKET_OU45, E.SEL_UNDER))
                       if info.market_id(m) is None]
            _log_throttled(db, extra, params, now_ts, "feed_line_missing",
                           {"reason": "linee assenti dal feed", "markets": missing or ["selezioni"],
                            "state": ctx.state, "critical": True}, ev["event_id"])
            ev["live"] = {**(ev.get("live") or {}), "lines_missing": missing or ["selezioni"],
                          "feed_incomplete": True}
            ev.update(_row_from_ctx(ev, ctx, extra))
            _persist(db, ev, before_sig, now_ts=now_ts, params=params, lotto=lotto)
        return (0, 0)

    # -- snapshot dal feed --------------------------------------------------------
    goals = F.goals_from_payload(payload)
    if goals is not None and extra.get("last_goals") is not None and goals > int(extra["last_goals"]):
        extra["last_goal_ts"] = now_ts
    if goals is not None:
        extra["last_goals"] = goals
    if bool(payload.get("inplay")):
        extra["seen_inplay"] = True
    extra["selections"] = {f"{m}|{s}": sid for (m, s), sid in info.selections.items()}
    live = {}
    if bool(payload.get("inplay")):
        # punteggio dell'intervallo: fissato la prima volta che il feed dice "half time"
        if F.ht_active_from_payload(payload) and extra.get("ht_score") is None \
                and payload.get("score_home") is not None and payload.get("score_away") is not None:
            extra["ht_score"] = [int(payload["score_home"]), int(payload["score_away"])]
        ht_score = tuple(extra["ht_score"]) if extra.get("ht_score") else None
        empirical = D.get_empirical(dossier.get("league_id"), db, now_ts) if ht_score is not None else None
        live = D.live_frame(dossier, minute=payload.get("minute"), score_home=payload.get("score_home"),
                            score_away=payload.get("score_away"), red_home=payload.get("red_home") or 0,
                            red_away=payload.get("red_away") or 0, atlas=atlas, home=info.home, away=info.away,
                            payload=payload, wait_step_min=int(params.get("cover_wait_step_min", 5)),
                            ht_score=ht_score, empirical=empirical,
                            emp_min_n=int(params.get("loss_exit_emp_min_n", 200)))
    snap = F.snapshot_from_row(row, info, now=now_ts, params=params, scanner_age_s=scanner_age,
                               hazard=live.get("hazard"), p4_model=live.get("p4_model"),
                               last_goal_ts=extra.get("last_goal_ts"),
                               cover_gain_pct=live.get("cover_gain_pct"),
                               pressure=float(live.get("pressure") or 1.0),
                               model_probs=live.get("model_probs"),
                               p_total_model=live.get("p_total_model"), p_total_emp=live.get("p_total_emp"))
    if snap is None:
        # payload senza ``open_date`` (o non leggibile): la partita smetterebbe di
        # essere decisa SENZA dire niente. Con una posizione aperta e' un allarme.
        _log_throttled(db, extra, params, now_ts, "feed_line_missing",
                       {"reason": "snapshot_non_costruibile", "state": ctx.state,
                        "critical": bool(E.open_selections(ctx.legs))}, ev["event_id"])
        ev.update(_row_from_ctx(ev, ctx, extra))
        _persist(db, ev, before_sig, now_ts=now_ts, params=params, lotto=lotto)
        return (0, 0)

    # -- C1: linee MANCANTI dal feed su una partita con posizione ------------------
    # Il tetto dei mercati opportunità dello scanner (20 eventi, i minuti più
    # avanzati) può lasciare una partita Mike senza blocco `ou`: senza la 4.5
    # non c'è copertura né cash out. Non si può inventare un prezzo: si GRIDA.
    if E.open_selections(ctx.legs):
        missing = [f"{m}|{s}" for (m, s) in E.live_open_selections(ctx.legs, snap.goals)
                   if snap.book(m, s) is None]
        if missing:
            _log_throttled(db, extra, params, now_ts, "feed_line_missing",
                           {"reason": "linee assenti dal feed", "selections": missing,
                            "state": ctx.state, "critical": True}, ev["event_id"])

    # -- SOSPENSIONE E RIAPERTURA (ordine dell'utente, 16/09) ---------------------
    # PRIMA della decisione, sempre: a mercato riaperto dopo una sospensione le
    # lay appoggiate possono essere state fatte scadere da Betfair, e il motore
    # non deve mai decidere su una gamba data per viva senza averla riletta.
    _sorveglia_sospensione(db=db, market=market, ctx=ctx, snap=snap, params=params,
                           mode=mode, now_ts=now_ts, ev=ev, cache=cache)

    # -- LO STATO DEL MERCATO DELLA COPERTURA (ordine dell'utente, 17/09) ---------
    # Il fratello del controllo qui sopra, sull'altro mercato: quello guarda la
    # lay appoggiata sull'Under 3.5, questo guarda l'Over 4.5 mentre la
    # copertura e' in corso. Anche questo PRIMA della decisione.
    _sorveglia_mercato_copertura(db=db, ctx=ctx, snap=snap, now_ts=now_ts, ev=ev)

    # -- LA POSIZIONE DI CONTO (ordine dell'utente, 16/09 sera) -------------------
    # «SE CHIUDO IO, IL BOT DEVE SAPERLO, ANCHE FUORI DALL'APP». Anche questa
    # PRIMA della decisione: se la posizione non e' piu' sua, il motore non deve
    # coprirla, chiuderla o rientrarci. Cadenza `reconcile_every_s` (default
    # 30 s), mai a ogni giro: sono due letture REST in piu' per mercato.
    _sorveglia_posizione_di_conto(db=db, market=market, ctx=ctx, ev=ev, extra=extra,
                                  params=params, mode=mode, now_ts=now_ts, cache=cache)

    # -- gambe pending stantie (esito mai arrivato) --------------------------------
    # C3 — un ordine il cui esito e' IGNOTO (execution._reconciling →
    # meta.reason='place_exception_reconciling') NON viene MAI dato per "non
    # piazzato" e MAI marcato cancelled/error dal TTL: resta 'pending_reconcile'
    # (conta nel rischio, blocca il rientro) finche' non si riconcilia contro
    # Betfair. Solo le gambe con esito NOTO vengono ritirate.
    for leg in ctx.legs:
        if leg.is_live and now_ts - leg.placed_at > _PENDING_STALE_S and not _is_resting_leg(leg, params):
            # (la lay APPOGGIATA resta legittimamente sul book per ore: esclusa)
            if _trade_unknown_outcome(db, ev["event_id"], leg, cache):
                leg.status = E.STATUS_RECONCILE
                logger.critical("[mike] %s: gamba %s con esito REST IGNOTO → riconciliazione",
                                ev["event_id"], leg.ref)
                _log_throttled(db, extra, params, now_ts, "reconcile_pending",
                               {"leg": leg.ref, "reason": "pending_unknown_outcome",
                                "critical": True}, ev["event_id"])
                continue
            # C.12a — la gamba stantia con un ordine LIVE viene annullata DAVVERO
            # su Betfair prima di essere dichiarata ritirata; se Betfair non
            # conferma, `_mark_trade_cancelled` la lascia in riconciliazione.
            _mark_trade_cancelled(db, ev["event_id"], leg, "pending_stale", cache, market=market)

    # -- C3/H8: gambe a esito IGNOTO -----------------------------------------------
    # Si tenta la riconciliazione con un THROTTLE (2 chiamate REST per evento:
    # senza freno erano 2 al secondo per evento) e il ciclo CONTINUA: restano
    # attive tutte le azioni che RIDUCONO il rischio (annulli, cash-out, uscite,
    # cap di perdita) — le APERTURE le toglie l'engine (`_strip_openings`).
    if E.has_unknown_orders(ctx):
        every = max(5.0, float(params.get("settle_confirm_s") or 30.0))
        if now_ts >= float(extra.get("reconcile_next_ts") or 0.0):
            extra["reconcile_next_ts"] = now_ts + every
            _reconcile_unknown(db, market, ev["event_id"], ctx, mode, now, cache)
        if E.has_unknown_orders(ctx):
            _log_throttled(db, extra, params, now_ts, "reconcile_pending",
                           {"legs": [l.ref for l in ctx.legs if l.needs_reconcile],
                            "state": ctx.state, "critical": True}, ev["event_id"])

    # -- lay APPOGGIATE (resting): fill simulato solo se il mercato scambia sotto ----
    # H3 — SOLO in paper: in live una lay appoggiata deve stare DAVVERO sul book
    # (REST senza FOK / coda flumine, F6). Simularla in live significherebbe
    # contabilizzare un profitto che non esiste.
    n_actions = 0
    for leg in ctx.legs:
        if leg.is_live and _is_resting_leg(leg, params):
            if mode != "paper":
                # In LIVE l'abbinamento non si simula e non si deduce dal
                # prezzo: si LEGGE dal book ordini di Betfair. Un ordine vivo
                # che nessuno contabilizza diventa una posizione doppia con
                # soldi veri quando piu' tardi si abbina da solo.
                _segui_resting_live(db=db, market=market, leg=leg, extra=extra,
                                    params=params, now_ts=now_ts, ev=ev,
                                    rilettura_in_corso=bool(
                                        ctx.riapertura and not ctx.riapertura.get("letto")))
                continue
            book = snap.book(leg.market, leg.selection)
            if not snap.order_fresh:
                # M7: feed stantio = nessun fill simulato. Qui la soglia stretta
                # e' PIU' importante che in live: un fill inventato su un prezzo
                # che non esiste piu' gonfia un risultato simulato, e su quel
                # risultato si decide se passare ai soldi veri.
                continue
            if _resting_filled(leg, book):
                leg.matched = float(leg.size)
                leg.avg_price = float(leg.price)
                leg.status = "open"
                r = _trade_row_for_leg(db, ev["event_id"], leg)
                if r is not None:
                    try:
                        db.update_trade(int(r["id"]), status="open", price=leg.price, size=leg.size,
                                        meta={**(r.get("meta") or {}), "phase": "open", "fill": "paper_resting"})
                    except Exception as ex:  # noqa: BLE001
                        logger.warning("[mike] conferma resting %s KO: %s", leg.ref, str(ex)[:120])
                db.log("fill_resting", {"leg": leg.ref, "role": leg.role, "price": leg.price, "size": leg.size,
                                        "best_back": book.best_back if book else None}, ev["event_id"])
                n_actions += 1

    # -- azioni differite (paper + in-play: betDelay) -------------------------------
    # H5: gli id delle righe servono SOLO per collegare una chiusura alla sua
    # apertura (closes_trade_id) → si leggono alla prima chiusura, non a ogni ciclo
    _ids_box: Dict[str, Dict[str, int]] = {}

    def closes_id(leg: E.Leg) -> Optional[int]:
        if not leg.closes_ref:
            return None
        if "v" not in _ids_box:
            _ids_box["v"] = _trade_ids_by_ref(db, ev["event_id"], cache)
        return _ids_box["v"].get(leg.closes_ref)

    score_str = f"{payload.get('score_home')}-{payload.get('score_away')}"
    deferred: List[Dict[str, Any]] = list(extra.get("deferred") or [])
    still: List[Dict[str, Any]] = []
    for item in deferred:
        leg = next((l for l in ctx.legs if l.ref == item["ref"]), None)
        if leg is None or not leg.is_live:
            continue
        if now_ts < float(item["earliest_at"]):
            still.append(item)
            continue
        book = snap.book(leg.market, leg.selection)
        if book is None:
            # buco momentaneo del feed: un ordine reale non sparirebbe → si ritenta
            # al ciclo dopo (review F1 #6), entro un limite di grazia
            if now_ts - float(item["earliest_at"]) < 30.0:
                still.append(item)
                continue
        execute_place(db=db, market=market, info=info, leg=leg, book=book,
                      mode=mode, params=params, now=now, dry=dry, minute=snap.minute,
                      score=score_str, feed_fresh=snap.feed_fresh,
                      close_reason=ctx.close_reason, closes_trade_id=closes_id(leg),
                      ctx=ctx)
        n_actions += 1
    extra["deferred"] = still

    # -- decisione -----------------------------------------------------------------
    d = E.decide(ctx, snap, params)
    # IL TETTO DELLE PARTITE, APPLICATO DOVE NASCONO I SOLDI (13/09).
    # ``max_open_matches`` era controllato solo quando si ARMA una partita, e
    # lo stato ``WATCH`` non contava: il conto si rifaceva da zero a ogni giro,
    # quindi ogni giro ne armava altre dieci e nessuna soglia impediva che poi
    # entrassero tutte. Cosi' si e' arrivati a 44 partite esposte con un tetto
    # scritto "10" — e lo scanner serve le quote in gioco solo alle prime 40,
    # quindi le ultime restavano senza copertura e senza uscita.
    # Qui si toglie la sola APERTURA: tutto cio' che RIDUCE il rischio (annulli,
    # uscite, coperture, cash out) passa sempre. Non si blocca mai una via
    # d'uscita, solo una via d'ingresso — e al giro dopo si riprova.
    if not puo_aprire and any(a.kind == "place" and a.role in E.OPENING_ROLES for a in d.actions):
        d = E._strip_openings(d, "tetto partite aperte raggiunto", ctx.state)
        _log_throttled(db, extra, params, now_ts, "tetto_partite",
                       {"reason": "max_open_matches", "cap": int(params["max_open_matches"]),
                        "state": ctx.state}, ev["event_id"])
    for a in d.actions:
        if a.kind == "cancel":
            leg = next((l for l in ctx.legs if l.ref == a.ref), None)
            if leg is not None and leg.is_live:
                extra["deferred"] = [x for x in extra["deferred"] if x["ref"] != leg.ref]
                # C.12a — l'engine decide QUANDO annullare (strategia, invariata):
                # qui l'annullamento arriva finalmente a Betfair.
                esito = _mark_trade_cancelled(db, ev["event_id"], leg, "cancelled_by_engine",
                                              cache, market=market)
                db.log("cancel", {"leg": leg.ref, "role": leg.role, "esito": esito},
                       ev["event_id"])
                n_actions += 1
    new_legs = E.apply_decision(ctx, d, now_ts)
    for leg in new_legs:
        book = snap.book(leg.market, leg.selection)
        delay = int(book.bet_delay) if (book and snap.inplay) else 0
        if _is_resting_leg(leg, params):
            # lay appoggiata: resta 'pending' sul book (riga riservata in mike_trades)
            # finche' il mercato non scambia sotto il suo prezzo (vedi _resting_filled)
            if dry:
                leg.status = "cancelled"
                db.log("would_place", {"leg": leg.ref, "role": leg.role, "side": "lay", "price": leg.price,
                                       "size": leg.size, "resting": True}, ev["event_id"])
            elif mode != "paper":
                # 14/09 — IN LIVE SI PIAZZA DAVVERO. Stesso ordine del paper:
                # stessa selezione, stesso lato, stesso prezzo, stessa size.
                # L'unica differenza e' che qui i soldi sono veri — che e'
                # l'unica differenza che ci deve essere.
                _piazza_resting_live(db=db, market=market, info=info, leg=leg, mode=mode,
                                     params=params, minuto=snap.minute, score=score_str,
                                     chiude=closes_id(leg), motivo=ctx.close_reason, ev=ev,
                                     ctx=ctx)
            else:
                try:
                    _insert_trade_row(db, _trade_row(info, leg, mode, params, snap.minute, score_str,
                                                     closes_id(leg), ctx.close_reason),
                                      ev["event_id"])
                    db.log("place_resting", {"leg": leg.ref, "role": leg.role, "price": leg.price,
                                             "size": leg.size}, ev["event_id"])
                except Exception as ex:  # noqa: BLE001 — riserva fallita: nessun ordine
                    leg.status = "cancelled"
                    db.log("error", {"leg": leg.ref, "reason": "reserve_failed", "err": str(ex)[:160]}, ev["event_id"])
            n_actions += 1
            continue
        if mode == "paper" and delay > 0:
            extra["deferred"].append({"ref": leg.ref, "earliest_at": now_ts + delay})
            db.log("place_deferred", {"leg": leg.ref, "role": leg.role, "bet_delay": delay,
                                      "price": leg.price, "size": leg.size}, ev["event_id"])
        else:
            execute_place(db=db, market=market, info=info, leg=leg, book=book, mode=mode, params=params,
                          now=now, dry=dry, minute=snap.minute, score=score_str,
                          feed_fresh=snap.feed_fresh, close_reason=ctx.close_reason,
                          closes_trade_id=closes_id(leg), ctx=ctx)
        n_actions += 1
    if d.telemetry:
        for k, v in d.telemetry.items():
            # ``settle`` NON e' un kind di ATTIVITA': il regolamento lo scrive il
            # ramo "mercato chiuso" come 'settled', DOPO ``_settle_trades``.
            # Loggarlo da qui avrebbe prodotto un kind non dichiarato alla UI
            # (badge grigio in inglese) e un regolamento senza righe aggiornate.
            if k in ("pre_cycle", "cover", "cover_wait", "cashout", "close_retries_exhausted",
                     # 16/09 h18:20, ordine dell'utente: il cash-out globale
                     # dell'utente e' una NOTIZIA, non un dettaglio di stato —
                     # da qui in poi il bot non apre piu' niente su quella
                     # partita, e in pagina si deve vedere perche'.
                     "chiuso_dall_utente",
                     "loss_exit", "loss_exit_deciso"):
                if k == "cashout":
                    extra["last_cashout"] = v
                elif k == "cover_wait":
                    extra["last_cover_wait"] = v
                elif k == "loss_exit":
                    extra["last_loss_exit"] = v
                else:
                    db.log(k, v if isinstance(v, dict) else {"value": v}, ev["event_id"])
    # H5 — il log 'state' si scrive SOLO quando lo stato cambia davvero: prima
    # bastava un motivo con numeri diversi (prezzi, minuti) per riscriverlo a
    # ogni tick e riempire mike_activity.
    if d.state != ev.get("state"):
        db.log("state", {"from": ev.get("state"), "to": d.state, "reason": d.reason}, ev["event_id"])
    extra["last_reason"] = d.reason

    # -- persistenza (write-on-change) --------------------------------------------
    c_rate = C.commission_rate(params)
    cv_now = E.cashout_value(ctx.legs, snap.books, c_rate,
                             int(params["cashout_place_at_ticks"]), goals=snap.goals)
    base_now = E.cashout_base(ctx, params)
    # M5 — "se chiudo ora" SEMPRE netto commissione lato servizio: la UI non deve
    # piu' calcolare nulla (prima mescolava lordo del servizio e netto del client).
    cashout_live = {
        "net": cv_now.net, "gross": cv_now.gross, "base": round(base_now, 2),
        "complete": cv_now.complete, "commission": round(c_rate, 4),
        "per": {f"{m}|{s}": v for (m, s), v in cv_now.per_selection_net.items()},
        "per_gross": {f"{m}|{s}": v for (m, s), v in cv_now.per_selection.items()},
        "decided": [f"{m}|{s}" for (m, s) in cv_now.decided],
        "pct": round(100.0 * cv_now.net / base_now, 2) if base_now > 0 else None,
        "target_pct": float(params["cashout_profit_pct"]),
    }
    if extra.get("last_cashout"):
        cashout_live["smart"] = (extra.get("last_cashout") or {}).get("smart")
    ev["live"] = {"minute": snap.minute, "goals": snap.goals, "inplay": snap.inplay, "ht": snap.ht_active,
                  "score_home": payload.get("score_home"), "score_away": payload.get("score_away"),
                  # C1/H6 — diagnostica sempre visibile: eta' del feed per EVENTO,
                  # linee mancanti e riconciliazione in corso
                  "feed_age_s": round(max(0.0, now_ts - (F.parse_iso_epoch(row.get("updated_at")) or now_ts)), 1),
                  "scanner_age_s": round(scanner_age, 1) if scanner_age is not None else None,
                  "lines_missing": [f"{m}|{s}" for (m, s) in
                                    ((E.MARKET_OU35, E.SEL_UNDER), (E.MARKET_OU45, E.SEL_OVER),
                                     (E.MARKET_OU45, E.SEL_UNDER))
                                    if snap.book(m, s) is None],
                  "reconcile_pending": E.has_unknown_orders(ctx),
                  "liability": E.event_liability(ctx.legs, c_rate),
                  "locked": E.locked_pnl(ctx.legs, c_rate),
                  "no_reentry": bool(extra.get("no_reentry")),
                  "total_matched": snap.total_matched,
                  "red_home": payload.get("red_home") or 0, "red_away": payload.get("red_away") or 0,
                  "model_probs": live.get("model_probs"), "ht_score": extra.get("ht_score"),
                  "p_total_model": live.get("p_total_model"), "p_total_emp": live.get("p_total_emp"),
                  "loss_exit": extra.get("last_loss_exit"),
                  "hazard": snap.hazard, "hazard_atlas": live.get("hazard_atlas"),
                  "hazard_model": live.get("hazard_model"), "pressure": live.get("pressure"),
                  "cover_gain_pct": live.get("cover_gain_pct"), "p_over45_model": live.get("p_over45_model"),
                  "p4_market": snap.p4_market, "p4_model": snap.p4_model,
                  # CERT. 12/09 -- DA DOVE arriva il modello: "fixture" (la migliore),
                  # "pre_ko_odds", "live_ou", oppure "none" = il bot e' cieco e decide
                  # su tabella empirica e mercato. Finche' il dossier era vuoto su tutti
                  # gli eventi era sempre "none" e nessuno poteva accorgersene.
                  "lambda_source": live.get("lambda_source"),
                  # CERT. 13/09 — prezzo Under al FISCHIO e scostamento in tick
                  # rispetto al nostro ingresso: dice se il mercato si e' mosso
                  # a favore o contro nel passaggio dal pre-match al gioco.
                  "ko_price_under": ctx.ko_price_under,
                  "ko_drift_ticks": E.drift_ticks(ev.get("entry_price_initial"), ctx.ko_price_under),
                  "cashout": cashout_live, "cover_wait": extra.get("last_cover_wait"),
                  # CERTIFICAZIONE 12/09 — stessa BASE di ``cashout`` e
                  # ``liability`` (gambe ATTIVE): con le gambe archiviate dentro,
                  # la card mostrava "se chiudo ora" e "a fine gara per gol
                  # totali" calcolati su insiemi diversi, e i due numeri non
                  # tornavano fra loro. I cicli archiviati sono gia' chiusi: il
                  # loro risultato sta nel realizzato, non nel rischio aperto.
                  "pnl_by_total": E.net_pnl_by_total(E.active_legs(ctx.legs), c_rate),
                  # 13/09 — il risultato della PARTITA per numero di gol: cicli
                  # gia' chiusi COMPRESI. ``pnl_by_total`` qui sopra e' la sola
                  # posizione ancora aperta (stessa base di ``cashout`` e
                  # ``liability``): i due servono a domande diverse e la scheda
                  # deve poterli mostrare senza che il trader li confonda.
                  "pnl_totale_by_total": E.net_pnl_by_total(ctx.legs, c_rate),
                  "pnl_cicli_chiusi": E.pnl_cicli_chiusi(ctx.legs, c_rate),
                  # quanti cicli, con che prezzi e con che risultato: richiesta
                  # esplicita dell'utente, il dato c'era ma non usciva
                  "cicli": E.riepilogo_cicli(ctx.legs, c_rate),
                  "cicli_chiusi": int(ctx.cycle_no or 0),
                  "investito": E.invested(ctx.legs),
                  # una riga per selezione aperta, CALCOLATA QUI: lato netto,
                  # prezzo medio, prezzo e size con cui il bot chiuderebbe, e
                  # soprattutto se al book c'e' abbastanza liquidita' per farlo
                  "posizioni": E.posizione_per_selezione(
                      ctx.legs, snap.books, c_rate,
                      int(params["cashout_place_at_ticks"]), goals=snap.goals),
                  # ORA di pubblicazione: la scheda ci calcola sopra un'eta' che
                  # TICKA. ``feed_age_s`` qui sopra e' congelato al momento della
                  # scrittura: se il servizio si ferma resta verde per sempre, e
                  # i bottoni che mandano ordini veri lo usano come semaforo.
                  "published_at": _iso(now_ts),
                  "published_ts": round(now_ts, 1),
                  "books": {f"{m}|{s}": dataclasses.asdict(b) for (m, s), b in snap.books.items()},
                  "feed_fresh": snap.feed_fresh}
    ev.update(_row_from_ctx(ev, ctx, extra))
    _persist(db, ev, before_sig, now_ts=now_ts, params=params, lotto=lotto)
    return (n_actions, settled)


def _event_rows(db: Any, event_id: str, cache: Optional[Dict[str, List[Dict[str, Any]]]] = None
                ) -> Optional[List[Dict[str, Any]]]:
    """Righe ``mike_trades`` della partita, lette UNA volta per ciclo (H5).

    C1 — ``None`` = LETTURA FALLITA, mai messa in cache e mai confusa con
    "nessuna riga": interpretare un errore di rete come tabella vuota portava la
    riconciliazione a REINSERIRE una riga per ogni gamba abbinata (righe doppie
    con lo stesso signal_key → P&L e stop giornaliero raddoppiati).
    """
    if cache is not None and str(event_id) in cache:
        return cache[str(event_id)]
    try:
        rows = list(db.trades_for_event(str(event_id)) or [])
    except Exception as ex:  # noqa: BLE001
        logger.warning("[mike] trades_for_event %s KO: %s", event_id, str(ex)[:120])
        return None
    if cache is not None:
        cache[str(event_id)] = rows
    return rows


def _trade_ids_by_ref(db: Any, event_id: str,
                      cache: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> Dict[str, int]:
    """{leg.ref: id della riga mike_trades} — serve a scrivere ``closes_trade_id`` (H4)."""
    out: Dict[str, int] = {}
    for r in _event_rows(db, event_id, cache) or []:
        key = r.get("signal_key")
        if key and r.get("id") is not None:
            out[str(key)] = int(r["id"])
    return out


def _trade_row_for_leg(db: Any, event_id: str, leg: E.Leg,
                       cache: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> Optional[Dict[str, Any]]:
    for r in _event_rows(db, event_id, cache) or []:
        if str(r.get("signal_key")) == leg.ref:
            return r
    return None


def _trade_unknown_outcome(db: Any, event_id: str, leg: E.Leg,
                           cache: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> bool:
    """Esito dell'ordine IGNOTO? FAIL-CLOSED (H2): se la riga mirror non si riesce
    a leggere si risponde SI'. Un dubbio non si risolve mai cancellando una
    gamba che potrebbe essere un ordine reale vivo."""
    rows = _event_rows(db, event_id, cache)
    if rows is None:
        logger.critical("[mike] %s: righe illeggibili, gamba %s trattata come esito IGNOTO",
                        event_id, leg.ref)
        return True
    r = next((x for x in rows if str(x.get("signal_key")) == leg.ref), None)
    if r is None:
        return True                      # nessuno specchio: non si sa nulla dell'ordine
    meta = r.get("meta") or {}
    return str(meta.get("reason") or "") == "place_exception_reconciling"


def _open_refs_by_event(db: Any) -> Optional[Dict[str, set]]:
    """{event_id: {signal_key delle righe NON terminali}} con UNA query (H5).

    Serve come pre-controllo della riconciliazione: se lo specchio combacia non
    si legge nulla per quella partita. ``None`` se la lettura fallisce (allora
    si riconcilia leggendo partita per partita, come prima)."""
    try:
        rows = db.open_trades() or []
    except Exception as ex:  # noqa: BLE001
        logger.warning("[mike] open_trades KO: %s", str(ex)[:120])
        return None
    out: Dict[str, set] = {}
    for r in rows:
        eid = str(r.get("event_id") or "")
        key = r.get("signal_key")
        if eid and key:
            out.setdefault(eid, set()).add(str(key))
    return out


def _mirror_is_aligned(ctx: E.MatchCtx, open_refs: Optional[Dict[str, set]], event_id: str) -> bool:
    """True se lo specchio righe/gambe combacia: nessuna lettura necessaria."""
    if open_refs is None:
        return False
    idx = open_refs.get(str(event_id), set())
    expected = {l.ref for l in ctx.legs
                if not l.archived and (float(l.matched) > 0 or l.needs_reconcile)}
    all_refs = {l.ref for l in ctx.legs}
    return not (expected - idx) and not (idx - all_refs)


def _reconcile_trades(db: Any, event_id: str, ctx: E.MatchCtx, info: Optional[F.EventInfo],
                      mode: str, params: Dict[str, Any],
                      cache: Optional[Dict[str, List[Dict[str, Any]]]] = None,
                      open_refs: Optional[Dict[str, set]] = None) -> int:
    """H2 — riconciliazione ``mike_trades`` <-> ``mike_events.positions`` a OGNI ciclo.

    Due buchi possibili dopo un crash o una scrittura DB fallita:
      * GAMBA senza riga (la riserva non e' stata scritta ma l'ordine esiste):
        la riga viene RISCRITTA dalla gamba (mai una posizione invisibile);
      * RIGA senza gamba (stato partita perso): in paper e' una riga zombie e
        viene chiusa in errore; in live potrebbe essere una posizione REALE →
        marcata ``meta.orphan`` e loggata come critica, mai toccata in silenzio.

    H5: se l'indice delle righe non terminali (UNA query per ciclo) combacia con
    le gambe, non si legge nulla — nessuna query per partita.
    """
    if _mirror_is_aligned(ctx, open_refs, event_id):
        return 0
    rows = _event_rows(db, event_id, cache)
    if rows is None:
        # C1: lettura FALLITA != nessuna riga. Non si tocca NULLA: reinserire
        # righe su un errore di rete significava P&L doppio.
        db.log("reconcile_pending", {"reason": "righe_illeggibili",
                                     "note": "nessuna riparazione: si riprova al ciclo dopo",
                                     "critical": True}, event_id)
        return 0
    by_ref = {str(r.get("signal_key")): r for r in rows if r.get("signal_key")}
    fixed = 0
    for leg in ctx.legs:
        if leg.ref in by_ref or leg.archived:
            continue
        # Solo le gambe che portano un'esposizione REALE o un ordine di cui non
        # si conosce l'esito: la riserva si scrive PRIMA dell'ordine, quindi una
        # gamba pending senza riga (ordine differito dal betDelay, riserva
        # fallita) non ha nessun ordine dietro e non va ricostruita.
        if float(leg.matched) <= 0 and not leg.needs_reconcile:
            continue
        if info is None or not info.complete:
            continue
        row = _trade_row(info, leg, mode, params, None, None, None, ctx.close_reason)
        if leg.matched > 0:
            # la liability va RICALCOLATA sull'abbinato reale: ``_trade_row`` la
            # calcola sulla size CHIESTA e la riga ricostruita finiva nella somma
            # delle righe (KPI "stimata dalle righe") con un numero gonfiato.
            row.update({"status": "open", "size": round(float(leg.matched), 2),
                        "price": leg.fill_price,
                        "liability": X.liability_of(leg.side, float(leg.matched), leg.fill_price)})
        row["meta"] = {**row["meta"], "phase": "reconstructed", "reconciled": True}
        try:
            _insert_trade_row(db, row, event_id)
            fixed += 1
            db.log("reconcile_fix", {"leg": leg.ref, "action": "riga_ricostruita",
                                     "status": row["status"], "critical": True}, event_id)
        except Exception as ex:  # noqa: BLE001
            logger.warning("[mike] reconcile insert %s KO: %s", leg.ref, str(ex)[:120])
    refs = {l.ref for l in ctx.legs}
    for ref, r in by_ref.items():
        # M9: riferimento alla riga di apertura rimasto in meta perche' la colonna
        # non esisteva ancora → ora che c'e' si ribalta in colonna
        pending_link = (r.get("meta") or {}).get("closes_trade_id_pending")
        if pending_link and not r.get("closes_trade_id"):
            meta_l = {k: v for k, v in (r.get("meta") or {}).items()
                      if k != "closes_trade_id_pending"}
            try:
                db.update_trade(int(r["id"]), closes_trade_id=int(pending_link), meta=meta_l)
                fixed += 1
                db.log("reconcile_fix", {"leg": ref, "trade_id": r.get("id"),
                                         "action": "closes_trade_id_ripristinato",
                                         "closes_trade_id": int(pending_link)}, event_id)
            except Exception as ex:  # noqa: BLE001 — colonna ancora assente: si riprova
                logger.debug("[mike] ribaltamento closes_trade_id %s KO: %s", ref, str(ex)[:120])
        if ref in refs or r.get("closes_trade_id"):
            continue
        status = str(r.get("status") or "")
        if status not in ("pending", "open", "hedged"):
            continue
        meta = dict(r.get("meta") or {})
        if meta.get("orphan"):
            continue
        meta["orphan"] = True
        try:
            if mode == "paper":
                # M2: in PAPER non esiste nessun ordine reale dietro una riga
                # senza gamba: e' una zombie e va chiusa (anche 'open'/'hedged',
                # altrimenti resta per sempre nella liability e nei KPI).
                meta["reason"] = "orphan_paper"
                db.update_trade(int(r["id"]), status="error", meta=meta)
            else:
                # in LIVE potrebbe essere una posizione REALE: solo marcata
                db.update_trade(int(r["id"]), meta=meta)
        except Exception as ex:  # noqa: BLE001
            logger.warning("[mike] reconcile orphan %s KO: %s", ref, str(ex)[:120])
            continue
        fixed += 1
        db.log("reconcile_fix", {"leg": ref, "trade_id": r.get("id"), "action": "riga_orfana",
                                 "status": status, "mode": mode, "critical": True}, event_id)
    if fixed and cache is not None:
        cache.pop(str(event_id), None)
    return fixed


def _reconcile_unknown(db: Any, market: Any, event_id: str, ctx: E.MatchCtx, mode: str,
                       now: datetime, cache: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> int:
    """C3 — prova a chiudere il dubbio su una gamba a esito IGNOTO.

    PAPER: nessun ordine e' mai partito verso Betfair (l'eccezione viene dal
    fill simulato) → la gamba si risolve subito come non abbinata.
    LIVE: si interroga Betfair. L'ordine si riconosce con ``_ordine_della_riga``
    — bet_id, ``mike-t<id>``, ref storico a mercato concorde — e poi si decide:
    confermata (abbinata), liberata (mai esistita) o si resta in attesa. Senza
    accesso a ``listCurrentOrders`` si RESTA in riconciliazione: mai un'ipotesi.

    ⚠️ 15/09 — QUI PASSAVA IL TERZO RAMO DEL LOOP. Si passava a
    ``reconcile_decision`` sempre e solo ``ref=f"mike-t{id}"``, ma le gambe di
    USCITA venivano piazzate con ``customer_ref=leg.ref`` (``under_green-0-2``).
    E ``_order_matches`` e' categorico: se l'ordine dichiara un ref, e' suo
    SOLO se coincide — nessun ripiego, perche' per una gamba di chiusura
    mercato e selezione vengono azzerati di proposito (confermerebbero la
    chiusura con l'ordine dell'apertura). Quindi un ordine VIVO a mercato non
    veniva trovato ne' fra i correnti ne' fra i regolati, passata la grazia la
    riga andava in 'error', il freno anti-duplicato non copriva piu' e al giro
    dopo partiva un SECONDO green-up.
    Dal 15/09 l'ordine lo identifica Mike, che sa cosa ha piazzato; a
    ``reconcile_decision`` si consegna il solo ordine giusto, gia' normalizzato,
    col ref che sta cercando. Resta lei a decidere: la decisione non si duplica.
    """
    pend = [l for l in ctx.legs if l.needs_reconcile]
    if not pend:
        return 0
    current: List[dict] = []
    cleared: List[dict] = []
    if mode == "live":
        try:
            current = list(market.list_current_orders() or [])
            cleared = list(market.list_cleared_orders() or [])
        except Exception as ex:  # noqa: BLE001 — nessuna ipotesi: si resta in attesa
            db.log("reconcile_pending", {"reason": "betfair_non_raggiungibile",
                                         "err": str(ex)[:120], "critical": True}, event_id)
            return 0
    n = 0
    now_iso = now.isoformat()
    for leg in pend:
        r = _trade_row_for_leg(db, event_id, leg, cache)
        if r is None:
            continue
        if mode == "paper":
            dec = {"action": "free"}
        else:
            o_cur = _ordine_della_riga(current, r)
            o_clr = _ordine_della_riga(cleared, r)
            ref_eff = ref_ordine_di_riga(r)
            trovato = o_cur if o_cur is not None else o_clr
            if trovato is not None:
                # l'ordine e' gia' stato identificato qui sopra, in modo piu'
                # forte di quanto possa fare `_order_matches` da sola: le si
                # consegna col ref che sta cercando, cosi' lo riconosce e resta
                # padrona della decisione (abbinato? residuo? grazia?).
                ref_eff = str(campo_ordine(trovato, "customer_order_ref") or ref_eff)
            cur_r = [{**o_cur, "customer_order_ref": ref_eff}] if o_cur is not None else []
            clr_r = [{**o_clr, "customer_order_ref": ref_eff}] if o_clr is not None else []
            dec = X.reconcile_decision(r, cur_r, clr_r, now_iso, ref=ref_eff)
        action = str(dec.get("action") or "keep")
        if action == "confirm":
            leg.matched = float(dec.get("size") or leg.size)
            leg.avg_price = float(dec.get("price") or leg.price)
            leg.status = "open"
            try:
                db.update_trade(int(r["id"]), status="open", price=leg.avg_price,
                                size=round(leg.matched, 2),
                                liability=X.liability_of(leg.side, leg.matched, leg.avg_price or 0.0),
                                bet_id=dec.get("bet_id"),
                                meta={**(r.get("meta") or {}), "phase": "open", "reason": "reconciled",
                                      "reconciled": True})
            except Exception as ex:  # noqa: BLE001
                logger.critical("[mike] conferma riconciliazione %s KO: %s", leg.ref, str(ex)[:120])
            db.log("reconcile_fix", {"leg": leg.ref, "action": "confermata", "size": leg.matched,
                                     "price": leg.avg_price, "critical": True}, event_id)
            n += 1
        elif action in ("free", "error"):
            leg.status = "cancelled"
            try:
                db.update_trade(int(r["id"]), status="error",
                                meta={**(r.get("meta") or {}), "phase": "cancelled",
                                      "reason": "reconciled_not_placed", "reconciled": True})
            except Exception as ex:  # noqa: BLE001
                logger.warning("[mike] chiusura riconciliazione %s KO: %s", leg.ref, str(ex)[:120])
            db.log("reconcile_fix", {"leg": leg.ref, "action": "mai_piazzata", "mode": mode},
                   event_id)
            n += 1
        else:
            db.log("reconcile_pending", {"leg": leg.ref, "action": "attesa", "critical": True},
                   event_id)
    if n and cache is not None:
        cache.pop(str(event_id), None)
    return n


def _mark_trade_cancelled(db: Any, event_id: str, leg: E.Leg, reason: str,
                          cache: Optional[Dict[str, List[Dict[str, Any]]]] = None,
                          market: Any = None) -> str:
    """Annulla l'ordine su BETFAIR e poi allinea la riga mike_trades.

    Ritorna lo stato in cui la gamba deve restare: ``'open'`` (c'e' un abbinato
    da difendere), ``'cancelled'`` (annullamento CONFERMATO da Betfair, o
    nessun ordine reale da annullare) oppure ``E.STATUS_RECONCILE``.

    ⚠️ C.12a — PRIMA SI ANNULLA, POI SI SCRIVE. Fino al 16/09 questa funzione
    faceva solo la seconda meta': cambiava lo stato della riga mentre l'ordine
    restava vivo su Betfair. Adesso, se la riga e' LIVE e ha un ``bet_id``, si
    chiama ``cancel_order_live`` e si RILEGGE l'esito:

      * annullamento confermato e nulla abbinato nel frattempo -> 'cancelled';
      * annullamento confermato ma abbinato NEL FRATTEMPO -> quella parte e' una
        posizione reale: la riga resta 'open' con l'abbinato e il prezzo medio
        VERI, mai dimenticata;
      * annullamento NON confermato (rifiutato, o esito ignoto) -> FAIL-CLOSED:
        la riga NON diventa 'cancelled', resta in riconciliazione, che e'
        l'unico modo onesto di dire «non so se quell'ordine e' ancora vivo».

    QUANDO annullare non si tocca: lo decidono l'utente e l'engine, come prima.
    """
    r = _trade_row_for_leg(db, event_id, leg, cache)
    esito_base = "open" if leg.matched > 0 else "cancelled"
    if not r or str(r.get("status")) not in ("pending",):
        leg.status = esito_base
        return esito_base
    bet_id = r.get("bet_id")
    e_live = str(r.get("mode") or "") == "live"
    quando_betfair: Optional[str] = None
    if e_live and bet_id:
        db.log("cancel_richiesto", {"leg": leg.ref, "role": leg.role, "reason": reason,
                                    "bet_id": str(bet_id), "trade_id": r.get("id"),
                                    "critical": True}, event_id)
        ann = X.annulla_su_betfair(market, bet_id=str(bet_id),
                                   market_id=r.get("market_id"))
        confermato = bool(ann is not None and getattr(ann, "ok", False)
                          and getattr(ann, "riletto", False))
        db.log("cancel_esito", {
            "leg": leg.ref, "role": leg.role, "bet_id": str(bet_id),
            "trade_id": r.get("id"), "confermato": confermato, "critical": True,
            "size_cancelled": (getattr(ann, "size_cancelled", None) if ann else None),
            "size_matched": (getattr(ann, "size_matched", None) if ann else None),
            "error_code": (getattr(ann, "error_code", None) if ann else None),
            "nota": ("annullato su Betfair" if confermato else
                     "annullamento NON confermato: la riga resta in riconciliazione"),
        }, event_id)
        if not confermato:
            # FAIL-CLOSED: nessuna riga 'cancelled' su un ordine che potrebbe
            # essere vivo. Lo risolve `_reconcile_unknown` contro Betfair.
            leg.status = E.STATUS_RECONCILE
            logger.critical("[mike] %s: annullo NON confermato su %s (bet %s) -> "
                            "riconciliazione", event_id, leg.ref, bet_id)
            return E.STATUS_RECONCILE
        # abbinato NEL FRATTEMPO: la parte abbinata e' una posizione, non si perde
        quando_betfair = getattr(ann, "betfair_updated_at", None)
        abbinato = float(getattr(ann, "size_matched", 0.0) or 0.0)
        if abbinato > float(leg.matched) + 1e-9:
            leg.matched = abbinato
            prezzo = getattr(ann, "avg_price_matched", None)
            leg.avg_price = float(prezzo) if prezzo else float(leg.price)
            db.log("fill_resting", {"leg": leg.ref, "role": leg.role,
                                    "matched": round(abbinato, 2), "price": leg.avg_price,
                                    "live": True, "critical": True,
                                    "nota": "abbinato durante l'annullamento: la posizione "
                                            "resta e va gestita"}, event_id)
            esito_base = "open"
    leg.status = esito_base
    try:
        meta = dict(r.get("meta") or {})
        meta.update({"phase": "cancelled", "reason": reason})
        if leg.matched > 0:
            X.aggiorna_trade(db, int(r["id"]),
                             campi={"status": "open", "size": round(leg.matched, 2),
                                    "price": leg.fill_price, "meta": meta},
                             consapevolezza={"size_matched": round(leg.matched, 2),
                                             "size_remaining": 0.0,
                                             "avg_price_matched": leg.avg_price,
                                             "betfair_updated_at": quando_betfair})
        else:
            X.aggiorna_trade(db, int(r["id"]),
                             campi={"status": "error", "meta": meta},
                             consapevolezza={"size_matched": 0.0, "size_remaining": 0.0})
    except Exception as ex:  # noqa: BLE001
        logger.warning("[mike] mark cancelled %s KO: %s", leg.ref, str(ex)[:120])
    return esito_base


_SETTLE_ROWS_MAX_TRIES = 5


def _retry_settle_rows(db: Any, event_id: str, ctx: E.MatchCtx, extra: Dict[str, Any],
                       now_ts: float) -> bool:
    """Righe ``mike_trades`` NON aggiornate dal regolamento: la partita NON puo'
    diventare terminale.

    Una partita SETTLED non viene piu' guardata dal ciclo (``_run_event`` esce
    subito sugli stati terminali): le sue righe resterebbero 'open'/'pending'
    PER SEMPRE — posizioni aperte fantasma nei KPI, liability dichiarata su
    soldi gia' regolati e P&L reale mai contabilizzato. Si torna quindi in
    SETTLING e si riprova al giro dopo (il throttle ``settle_next_ts`` e' gia'
    fissato). Ritorna True se si deve riprovare, False se si rinuncia dopo
    ``_SETTLE_ROWS_MAX_TRIES`` (partita chiusa lo stesso, ma GRIDANDO).
    """
    tries = int(extra.get("settle_rows_attempts") or 0) + 1
    extra["settle_rows_attempts"] = tries
    if tries >= _SETTLE_ROWS_MAX_TRIES:
        logger.critical("[mike] %s: righe di regolamento non aggiornate dopo %d tentativi: "
                        "partita chiusa lo stesso, righe da sistemare a mano", event_id, tries)
        db.log("error", {"reason": "settle_rows_failed", "attempts": tries, "critical": True},
               event_id)
        return False
    logger.warning("[mike] %s: righe di regolamento non aggiornate (tentativo %d): si riprova",
                   event_id, tries)
    db.log("error", {"reason": "settle_rows_retry", "attempts": tries, "critical": True}, event_id)
    E.apply_decision(ctx, E.Decision("SETTLING", [], "righe non aggiornate: nuovo tentativo"), now_ts)
    return True


def _settle_params(db: Any, event_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """``params`` con l'ALIQUOTA DI COMMISSIONE FISSATA SULLE RIGHE della partita.

    CERTIFICAZIONE 12/09 — il regolamento usava sempre ``commission_pct``
    CORRENTE: se il trader cambiava il parametro con posizioni gia' aperte, le
    vecchie si regolavano con la nuova aliquota e il P&L storico cambiava di
    significato. Omega e Safe usano da sempre quella della riga. Qui si legge
    dalle righe della partita: se sono tutte d'accordo si usa quella, altrimenti
    (caso raro: parametro cambiato a partita aperta) si tiene quella corrente e
    lo si DICHIARA nel log, perche' il numero non e' piu' ricostruibile.
    """
    try:
        rows = db.trades_for_event(str(event_id)) or []
    except Exception:  # noqa: BLE001 - mai bloccare il regolamento per questo
        return params
    rates = set()
    for r in rows:
        v = r.get("commission")
        if v is None:
            continue
        try:
            rates.add(round(float(v), 6))
        except (TypeError, ValueError):
            continue
    if len(rates) != 1:
        if len(rates) > 1:
            db.log("settle_commissione_mista", {
                "reason": "righe con aliquote diverse: uso quella corrente",
                "aliquote": sorted(rates), "critical": True}, str(event_id))
        return params
    rate = rates.pop()
    if abs(rate - C.commission_rate(params)) < 1e-9:
        return params
    return {**params, "commission_pct": round(rate * 100.0, 6)}


def _settle_trades(db: Any, event_id: str, ctx: E.MatchCtx, settle: Dict[str, Any],
                   params: Optional[Dict[str, Any]] = None) -> bool:
    """Riporta l'esito per gamba sulle righe mike_trades (signal_key = leg.ref).

    H4 — il ``pnl`` scritto su ogni riga e' NETTO commissione (la somma delle
    righe = ``settled_pnl`` della partita).
    L-08 — ``meta.commission_paid`` viene SCRITTA davvero (quota di commissione
    del mercato attribuita alla riga): lo storico non deve piu' stimarla.

    Ritorna False se le righe NON sono state scritte (lettura fallita o anche un
    solo update fallito): il chiamante non deve chiudere la partita.
    """
    per_leg = {ref: (st, pnl) for ref, st, pnl in (settle.get("per_leg") or [])}
    gross_leg = {ref: pnl for ref, _st, pnl in (settle.get("per_leg_gross") or [])}
    comm_market = dict(settle.get("commission_by_market") or {})
    legs_by_ref = {l.ref: l for l in ctx.legs}
    try:
        rows = db.trades_for_event(str(event_id))
    except Exception as ex:  # noqa: BLE001
        db.log("error", {"reason": "settle_rows_unreadable", "err": str(ex)[:160],
                         "critical": True}, event_id)
        return False
    ok = True
    now_iso = _now().isoformat()
    # C1 — DEDUP per signal_key: se per qualunque motivo esistono due righe per
    # la stessa gamba, il P&L si scrive UNA volta sola (sulla piu' vecchia) e le
    # altre vengono chiuse in errore. Senza, realized/stop/storico raddoppiano.
    seen: Dict[str, Dict[str, Any]] = {}
    for r in sorted(rows, key=lambda x: int(x.get("id") or 0)):
        ref0 = str(r.get("signal_key") or "")
        if not ref0 or ref0 not in per_leg or str(r.get("status")) in ("won", "lost", "void", "error"):
            continue
        if ref0 in seen:
            meta_d = dict(r.get("meta") or {})
            meta_d.update({"duplicate_of": seen[ref0].get("id"), "reason": "duplicate_signal_key"})
            try:
                db.update_trade(int(r["id"]), status="error", pnl=0.0, meta=meta_d)
            except Exception as ex:  # noqa: BLE001
                ok = False
                logger.warning("[mike] dedup riga %s KO: %s", r.get("id"), str(ex)[:120])
            logger.critical("[mike] %s: riga DOPPIA per %s (id %s, tenuta %s)", event_id, ref0,
                            r.get("id"), seen[ref0].get("id"))
            db.log("error", {"reason": "duplicate_signal_key", "leg": ref0,
                             "trade_id": r.get("id"), "kept": seen[ref0].get("id"),
                             "critical": True}, event_id)
            continue
        seen[ref0] = r
    for r in rows:
        if str(r.get("status")) in ("won", "lost", "void", "error"):
            continue
        ref = str(r.get("signal_key"))
        res = per_leg.get(ref)
        if res is None or seen.get(ref) is not r:
            continue
        st, pnl = res
        meta = dict(r.get("meta") or {})
        gross = gross_leg.get(ref)
        if gross is not None:
            meta["pnl_gross"] = round(float(gross), 2)
            meta["commission_paid"] = round(max(0.0, float(gross) - float(pnl)), 2)
        leg = legs_by_ref.get(ref)
        if leg is not None and leg.market in comm_market:
            meta["commission_market"] = round(float(comm_market[leg.market]), 2)
        if settle.get("void"):
            meta["void_reason"] = "mercato_annullato"
        try:
            db.update_trade(int(r["id"]), status=st, pnl=round(float(pnl), 2), settled_at=now_iso,
                            meta=meta)
        except Exception as ex:  # noqa: BLE001
            ok = False
            db.log("error", {"reason": "settle_update_failed", "trade_id": r.get("id"),
                             "err": str(ex)[:120], "critical": True}, event_id)
    # H4 — la somma dei ``pnl`` delle righe DEVE fare ``settled_pnl``: una gamba
    # regolata senza riga specchio (riserva mai scritta e mai ricostruita perche'
    # il feed era incompleto) rompe quella garanzia. Non si puo' riparare qui
    # (non c'e' ``EventInfo``), ma non deve restare muta.
    refs_on_db = {str(r.get("signal_key") or "") for r in rows}
    orphan_legs = [ref for ref in per_leg if ref not in refs_on_db]
    if orphan_legs:
        # CERT. 12/09 — distinzione che prima mancava. Una gamba PIANIFICATA e mai
        # piazzata (importo sotto il minimo Betfair, ordine annullato) si regola
        # 'void' e vale ZERO: non rompe nessuna garanzia e non e' un errore, e'
        # cronaca. Osservato dal vivo: 8 partite, 69 gambe orfane, scarto fra P&L
        # dichiarato e somma delle righe pari a 0,00 EUR su tutte e 8 — eppure
        # ognuna scriveva un 'error' critico che faceva sembrare rotto il conto.
        # Rompe la garanzia solo una gamba orfana con P&L NON nullo.
        def _pnl_of(ref: str) -> float:
            # ``per_leg`` e' {ref: (stato, pnl)} — vedi la riga che lo costruisce
            v = per_leg.get(ref)
            if isinstance(v, (tuple, list)) and len(v) >= 2:
                v = v[1]
            try:
                return float(v or 0.0)
            except (TypeError, ValueError):
                return 0.0
        pesanti = [ref for ref in orphan_legs if abs(_pnl_of(ref)) > 0.005]
        if pesanti:
            logger.critical("[mike] %s: %d gambe regolate SENZA riga e con P&L: %s",
                            event_id, len(pesanti), pesanti[:5])
            db.log("error", {"reason": "settle_leg_senza_riga", "legs": pesanti[:10],
                             "critical": True}, event_id)
        else:
            logger.info("[mike] %s: %d gambe pianificate e mai piazzate, regolate a zero",
                        event_id, len(orphan_legs))
            db.log("settle_gambe_non_piazzate",
                   {"quante": len(orphan_legs), "legs": orphan_legs[:10]}, event_id)
    return ok


# ogni quanto riprovare a costruire un dossier rimasto cieco (secondi)
_DOSSIER_RETRY_SEC = 300.0


def dossier_da_ritentare(ev: Dict[str, Any], now_ts: float,
                         ogni: float = _DOSSIER_RETRY_SEC) -> bool:
    """True se questa partita vale un nuovo tentativo di dossier: e' ancora viva,
    i gol attesi mancano, e l'ultimo tentativo e' abbastanza vecchio."""
    if str(ev.get("state") or "") in E.TERMINAL_STATES:
        return False
    d = ev.get("dossier")
    if not isinstance(d, dict):
        return True
    if d.get("lambda_home") and d.get("lambda_away"):
        return False                      # gia' risolto: non si tocca
    try:
        ultimo = float(d.get("retry_ts") or 0.0)
    except (TypeError, ValueError):
        ultimo = 0.0
    return (now_ts - ultimo) >= float(ogni)


def _retry_dossier(db: Any, tracked: Dict[str, Dict[str, Any]], now_ts: float) -> int:
    """Riprova il dossier delle partite vive rimaste senza gol attesi. Ritorna
    quante sono state RISOLTE. Non solleva mai: un dossier e' un di piu'."""
    risolte = 0
    for eid, ev in tracked.items():
        if not dossier_da_ritentare(ev, now_ts):
            continue
        try:
            nuovo = D.build_prematch(str(eid), db)
        except Exception as ex:  # noqa: BLE001
            logger.debug("[mike] dossier retry %s KO: %s", eid, str(ex)[:120])
            continue
        nuovo["retry_ts"] = now_ts
        ev["dossier"] = nuovo
        if nuovo.get("lambda_home") and nuovo.get("lambda_away"):
            ev["fixture_id"] = nuovo.get("fixture_id")
            ev["league_id"] = nuovo.get("league_id") or ev.get("league_id")
            risolte += 1
            db.log("dossier_risolto", {"fixture_id": nuovo.get("fixture_id"),
                                       "fonte": nuovo.get("source"),
                                       "lambda": [nuovo.get("lambda_home"), nuovo.get("lambda_away")]}, eid)
    return risolte


def _gambe_vive(ev: Dict[str, Any]) -> bool:
    """La partita ha SOLDI SUL TAVOLO? (una gamba non annullata, non regolata,
    non archiviata). E' la domanda che decide con che cadenza va rinfrescata
    l'ora di pubblicazione: dove c'e' qualcosa da chiudere, la scheda deve
    poter accendere i bottoni; dove non c'e' niente, l'eta' e' solo cosmetica."""
    for l in (ev.get("positions") or []):
        if not isinstance(l, dict) or l.get("archived"):
            continue
        if str(l.get("status") or "") not in ("cancelled", "settled"):
            return True
    return False


def _cadenza_pubblicazione(ev: Dict[str, Any], params: Optional[Dict[str, Any]]) -> float:
    """Ogni quanto si riscrive una riga che NON e' cambiata, solo per rinfrescare
    ``published_at``. Due velocita': stretta dove ci sono soldi o la partita e'
    in gioco, larga su una partita che stiamo solo guardando."""
    p = params or C.DEFAULTS
    if str(ev.get("state")) in E.TERMINAL_STATES:
        # regolata / saltata: non si tocca piu'. L'ultima scrittura e' gia' la
        # verita' definitiva e una card terminale non ha bottoni da illuminare.
        return 0.0
    if _gambe_vive(ev) or bool((ev.get("live") or {}).get("inplay")):
        return float(p.get("publish_heartbeat_s", C.DEFAULTS["publish_heartbeat_s"]) or 0.0)
    return float(p.get("publish_idle_heartbeat_s", C.DEFAULTS["publish_idle_heartbeat_s"]) or 0.0)


def _scrivi_evento(db: Any, ev: Dict[str, Any]) -> None:
    """Scrive la scheda della partita. Se non ci riesce, lo GRIDA.

    14/09 — questa funzione ha nascosto per DODICI GIORNI il difetto piu' grave
    della storia del bot. Il vincolo del database rifiutava gli stati
    ``LIVE_KO_GREEN`` e ``LIVE_SECOND_ENTRY`` (nati nel motore il 13/09 e mai
    aggiunti alla migrazione), l'upsert falliva, e qui il rifiuto veniva
    annotato con un ``logger.warning`` fra migliaia di righe di log.
    Conseguenza: l'uscita al fischio d'inizio non e' MAI partita — zero righe,
    zero partite in quello stato, mai — e ogni partita entrata in gioco con una
    posizione aperta e' rimasta scoperta fino al fischio finale.

    Non poter scrivere lo stato di una partita CON UNA POSIZIONE APERTA e'
    money-critical: il bot perde la memoria di dove si trova, e al giro
    successivo ricomincia da capo — per sempre, perche' i contatori che
    dovrebbero far scadere le finestre non vengono mai salvati.

    Quindi: log CRITICO, e una riga di attivita' che arriva in pagina. Chi
    guarda deve poterlo vedere senza leggere i log del processo.
    """
    try:
        db.upsert_event(ev)
    except Exception as ex:  # noqa: BLE001
        eid = str(ev.get("event_id") or "?")
        aperta = bool(ev.get("positions")) and str(ev.get("state")) not in E.TERMINAL_STATES
        logger.critical("[mike] SCRITTURA DI STATO FALLITA su %s (stato=%s, posizione aperta=%s): %s "
                        "— il bot non ricorda dove si trova e ricomincera' da capo",
                        eid, ev.get("state"), aperta, str(ex)[:200])
        try:
            db.log("error", {"reason": "stato_non_scritto", "state": ev.get("state"),
                             "posizione_aperta": aperta, "err": str(ex)[:200],
                             "critical": True}, eid)
        except Exception:  # noqa: BLE001 — se non si puo' nemmeno loggare, resta il critical
            pass


def _persist(db: Any, ev: Dict[str, Any], before_sig: str, *,
             now_ts: Optional[float] = None, params: Optional[Dict[str, Any]] = None,
             lotto: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
    """Scrive la scheda della partita — ma solo quando ha senso farlo.

    Tre casi, in quest'ordine, e l'ordine e' la parte importante:

    1. La firma SOSTANZIALE e' cambiata: e' successo qualcosa (uno stato, una
       gamba, un gol, un regolamento). Si scrive SUBITO e da sola, senza
       cadenze e senza lotti. Rallentare una scrittura di questo tipo vorrebbe
       dire perdere il filo di una posizione con soldi veri dentro.
    2. Niente di sostanziale e' cambiato ma e' passata la cadenza di
       pubblicazione: si riscrive per rinfrescare ``published_at``, cioe' per
       dire alla scheda "sono ancora vivo". Questa e' una scrittura di
       cortesia: puo' viaggiare in LOTTO con quelle delle altre partite (una
       sola POST invece di una per partita).
    3. Niente di sostanziale e cadenza non ancora scaduta: non si scrive. Non
       si SCARTA niente — la riga in memoria e' gia' aggiornata e verra'
       scritta al primo dei due casi qui sopra.
    """
    eid = str(ev.get("event_id"))
    # LO SCHERMO SI AGGIORNA A OGNI GIRO, il database no. E' tutto il punto:
    # spingere sul socket non costa un byte di disco, quindi non c'e' nessuna
    # ragione di rallentarlo. La riga che si pubblica e' la STESSA che verrebbe
    # scritta, quindi pagina e database non possono divergere.
    _pubblica_evento(ev)
    if _signature(ev) != before_sig:
        _SCRITTO_A[eid] = float(now_ts if now_ts is not None else time.time())
        if lotto is not None:
            lotto.pop(eid, None)          # la scrittura immediata copre il lotto
        _scrivi_evento(db, ev)
        return
    ogni = _cadenza_pubblicazione(ev, params)
    if ogni <= 0:
        return
    ora = float(now_ts if now_ts is not None else time.time())
    if ora - float(_SCRITTO_A.get(eid) or 0.0) < ogni:
        return
    _SCRITTO_A[eid] = ora
    if lotto is None:
        _scrivi_evento(db, ev)
    else:
        lotto[eid] = ev


def _svuota_lotto(db: Any, lotto: Dict[str, Dict[str, Any]], params: Dict[str, Any]) -> None:
    """Le riscritture di cortesia accumulate nel giro, in UNA sola POST.

    Un upsert con N righe costa al database una frazione di N upsert da una riga
    (una sola andata e ritorno, un solo giro di indici, un solo pezzo di WAL).
    Se l'accessore non espone la scrittura in blocco — o se il parametro e'
    spento — si ripiega riga per riga: MAI perdere una scrittura per
    un'ottimizzazione."""
    if not lotto:
        return
    righe = list(lotto.values())
    lotto.clear()
    scrivi_in_blocco = getattr(db, "upsert_events", None)
    if scrivi_in_blocco is not None and bool(params.get("events_batch_write", True)) and len(righe) > 1:
        try:
            scrivi_in_blocco(righe)
            return
        except Exception as ex:  # noqa: BLE001 — si ripiega riga per riga, niente va perso
            logger.warning("[mike] upsert_events in blocco KO (%d righe), riga per riga: %s",
                           len(righe), str(ex)[:160])
    for riga in righe:
        _scrivi_evento(db, riga)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
# ===========================================================================
# IL CANALE LOCALE VERSO LO SCHERMO (14/09/2026)
# ===========================================================================
# Porta di default 47333, accanto a quelle gia' in uso dal runner (47331 calcio,
# 47332 tennis). Un canale PER BOT e non uno condiviso: quello del runner accetta
# comandi ordine, e non va allargato per farci passare dati di visualizzazione.
_PORTA_CANALE = 47333


def _avvia_canale() -> None:
    """Accende il canale locale. Non solleva MAI: senza canale il bot lavora."""
    import os

    try:
        porta = int((os.environ.get("MIKE_LOCAL_WS_PORT") or "").strip() or _PORTA_CANALE)
    except ValueError:
        porta = _PORTA_CANALE
    try:
        ch = _lc.start_channel(porta, "mike", solo_lettura=True)
        if ch is None:
            logger.warning("[mike] canale locale NON attivo su %d (porta occupata?): "
                           "la pagina continuera' a leggere dal database.", porta)
    except Exception as ex:  # noqa: BLE001 — il canale e' opzionale, sempre
        logger.warning("[mike] canale locale KO: %s", str(ex)[:160])


# ===========================================================================
# LA SVEGLIA DEL CICLO (18/09/2026, fasi F5 e F6) - interruttore SPENTO di serie
# ===========================================================================
# Il ciclo di Mike NON si accorcia: si SVEGLIA. Con ``MIKE_SVEGLIA_CANALE=1``
# la dormita del loop diventa ``_SVEGLIA.attendi(pausa, pavimento)``, dove il
# pavimento e' la CADENZA ATTIVA DI OGGI (``decide_min_interval_ms``, cioe' lo
# stesso ``interval`` che il loop calcola prima di allargarsi a vuoto). Da li'
# la garanzia: per quante sveglie arrivino, fra l'inizio di un giro e quello
# del successivo passa almeno il tempo che passa oggi quando Mike e' attivo, e
# quindi le letture al minuto non crescono. Il guadagno e' sul lato lento (a
# vuoto ``idle_cycle_s``). A interruttore spento la dormita resta
# ``time.sleep(interval)``, la stessa istruzione di oggi.
_SVEGLIA = _SV.Sveglia("mike")
_ASCOLTO_SCAN: Optional[_SV.AscoltoScan] = None


def _evento_seguito(event_id: str) -> bool:
    """Mike sta seguendo questo evento? Si risponde SOLO con la memoria.

    ``_CACHE_EVENTI`` e' la copia in RAM di ``mike_events``: sono le partite
    che il bot ha in carico (posizione aperta, ordini vivi, osservate) piu' le
    terminali recenti. Nessuna select per decidere se svegliarsi.
    """
    return str(event_id) in _CACHE_EVENTI


def _pavimento_sveglia(params: Any) -> float:
    """Il pavimento della sveglia = la cadenza ATTIVA di oggi.

    E' lo STESSO calcolo che il loop fa per ``interval`` prima di allargarlo a
    vuoto: non un numero nuovo, il passo al quale Mike gia' gira quando c'e'
    movimento.
    """
    p = params if isinstance(params, dict) else {}
    try:
        ms = float(p.get("decide_min_interval_ms") or C.DEFAULTS["decide_min_interval_ms"])
    except (TypeError, ValueError):
        ms = float(C.DEFAULTS["decide_min_interval_ms"])
    return max(1.0, ms / 1000.0 * 2)


def _su_sveglia_dal_canale(params: Any) -> bool:
    """F6: il SOLO messaggio che il canale 47333 puo' ricevere.

    Alza la sveglia e NIENT'ALTRO: nessun parametro d'ordine sul canale. Il
    comando vero resta la riga di ``mike_requests``, letta con le funzioni, le
    guardie e l'idempotenza di oggi. Campi extra: ignorati.
    """
    motivo = _SV.messaggio_di_sveglia(params)
    if motivo is None:
        return False
    _SVEGLIA.alza(motivo, minimo_s=_SV.MINIMO_UI_S)
    return True


def _avvia_sveglia() -> None:
    """Accende l'ascolto del canale dello scanner e la sveglia da UI. Non
    solleva MAI; a interruttore spento non apre nessun thread e nessuna porta."""
    global _ASCOLTO_SCAN
    if not _SV.acceso(_SV.ENV_MIKE_SVEGLIA):
        return
    try:
        ascolto = _SV.AscoltoScan(_SVEGLIA, _evento_seguito,
                                  topic=(_SV.TOPIC_SCAN_CALCIO,), nome="mike")
        if ascolto.avvia():
            _ASCOLTO_SCAN = ascolto
            logger.info("[mike] sveglia dal canale ATTIVA (%s): il ciclo riparte "
                        "quando si muove una partita che Mike segue.", ascolto.url)
    except Exception as ex:  # noqa: BLE001 - la sveglia e' un'accelerazione
        logger.warning("[mike] sveglia dal canale KO: %s", str(ex)[:160])
    try:
        ch = _lc.get_channel()
        registra = getattr(ch, "set_sveglia", None) if ch is not None else None
        if callable(registra):
            registra(_su_sveglia_dal_canale)
        else:
            logger.info("[mike] il canale locale non espone 'set_sveglia': la "
                        "sveglia dalla UI non e' collegata (resta la coda sul "
                        "database, come oggi).")
    except Exception as ex:  # noqa: BLE001
        logger.warning("[mike] aggancio della sveglia da UI KO: %s", str(ex)[:160])


def statistiche_sveglia() -> Optional[Dict[str, Any]]:
    """I contatori della sveglia, o ``None`` a interruttore spento."""
    if _ASCOLTO_SCAN is None:
        return None
    return {**_SVEGLIA.statistiche(), "canale": _ASCOLTO_SCAN.statistiche()}


def _dormi_o_sveglia(pausa: float, params: Any) -> None:
    """La dormita del ciclo. A interruttore SPENTO e' ``time.sleep(pausa)``,
    la stessa identica istruzione di oggi."""
    if _ASCOLTO_SCAN is None:
        time.sleep(pausa)
        return
    _SVEGLIA.attendi(pausa, _pavimento_sveglia(params))


# Campi PESANTI e FERMI della scheda: non servono allo schermo a ogni giro e
# gonfierebbero il messaggio per niente (il dossier e' il modello pre-partita,
# i markets sono gli identificativi dei mercati: non cambiano mai durante la
# partita). Restano nel database, dove la pagina li ha gia' presi una volta.
# E ``updated_at``, che merita la sua riga perche' e' un difetto CRITICO che ho
# introdotto io e che la review ha trovato prima che costasse qualcosa.
#
# ``updated_at`` significa "QUANDO IL DATABASE HA SCRITTO QUESTA RIGA". In
# memoria, pero', il servizio ha ancora quello dell'ULTIMA RILETTURA: ``db.
# upsert_event`` fa ``row = dict(row)`` prima di imporre l'ora nuova, quindi la
# copia del ciclo non la vede mai, e le riletture complete avvengono ogni
# ``events_reload_s`` (60 s).
#
# Mandarlo vorrebbe dire riportare INDIETRO l'orologio della scheda, e la card
# e' memoizzata proprio su quel campo (``MikeMatchCard``: `a.ev.updated_at ===
# b.ev.updated_at`). Conseguenza a catena, verificata riga per riga:
#   1. il merge lato pagina fa vincere il campo spinto -> updated_at torna vecchio
#   2. React.memo scarta tutti i push successivi -> la card si CONGELA
#   3. ma la card si ridisegna lo stesso ogni secondo per conto suo (orologio
#      interno), e confronta un tempo che avanza con un ``published_ts`` fermo
#   4. oltre 20 s il semaforo del feed diventa rosso
#   5. e il bottone di CASH OUT viene DISABILITATO — su una posizione aperta.
# Cioe': la funzione nata per rendere la pagina viva l'avrebbe resa 12 volte
# piu' vecchia (da ~5 s a 60 s) e avrebbe tolto al trader l'unico bottone che
# chiude una posizione dalla scheda.
#
# L'ora che serve alla pagina viaggia gia' dentro il payload: ``live.published_at``,
# che per costruzione e' l'istante in cui il servizio ha calcolato la scheda.
_FUORI_DAL_PUSH = ("dossier", "markets", "ctx", "updated_at")


def _pubblica_evento(ev: Dict[str, Any]) -> None:
    """Spinge la scheda della partita sullo schermo. No-op senza app collegata."""
    try:
        _lc.publish("mike_event", {k: v for k, v in ev.items() if k not in _FUORI_DAL_PUSH})
    except Exception as ex:  # noqa: BLE001 — mostrare non deve mai fermare il bot
        logger.debug("[mike] publish evento KO: %s", str(ex)[:120])


def _pubblica_stato(control: Dict[str, Any], agg: Dict[str, Any],
                    stats: Dict[str, Any], now_ts: float) -> None:
    """Spinge i numeri di testata (P&L, liability, KPI) sullo schermo."""
    try:
        _lc.publish("mike_stato", {"control": control, "aggregates": agg,
                                   "stats": stats, "published_ts": round(now_ts, 1)})
    except Exception as ex:  # noqa: BLE001
        logger.debug("[mike] publish stato KO: %s", str(ex)[:120])


def main() -> None:
    from Betfair.stream.single_instance import acquire_single_instance_lock

    parser = argparse.ArgumentParser(description="Bot Mike (Under 3.5 / Over 4.5)")
    parser.add_argument("--once", action="store_true", help="un ciclo e esce")
    parser.add_argument("--dry", action="store_true", help="nessun ordine (would_place)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
    lock = None
    if not args.once:
        lock = acquire_single_instance_lock(_LOCK_PORT, "mike")
    logger.info("[mike] servizio avviato (lock %s, dry=%s)", _LOCK_PORT, args.dry)
    # CANALE LOCALE verso l'app desktop (14/09): quote, P&L e stato viaggiano su
    # 127.0.0.1 invece che passare dal disco. Se la porta e' occupata o il
    # modulo non parte, ``start_channel`` torna None e il servizio continua
    # esattamente come prima: il canale e' un'accelerazione, non una dipendenza.
    if not args.once:
        _avvia_canale()
        # 23/09: saldo del conto riletto dopo ogni ordine reale / regolazione
        # nuova (una chiamata per evento, nessun polling; stream/saldo_evento.py).
        from Betfair.omega import omega_market as _om_saldo
        _om_saldo.attiva_saldo_su_evento("mike")
        # F5/F6 (18/09): la sveglia del ciclo. A interruttore spento non parte
        # nessun thread e la dormita resta quella di oggi.
        _avvia_sveglia()
    # FASE A — PRIMA di qualunque ciclo: se l'app e' stata riaperta, Mike si
    # ferma. Da qui in poi la guardia e' attiva: finche' il controllo non
    # riesce, ``run_once`` non apre niente (le protezioni girano).
    _GUARDIA_AVVIO.attiva = True
    ferma_al_nuovo_avvio()
    atlas = D.load_atlas()
    try:
        while True:
            interval = 2.0
            try:
                # controllo d'avvio non concluso (DB muto): si riprova a ogni
                # giro, e fino ad allora nessuna apertura.
                if _GUARDIA_AVVIO.blocca_aperture:
                    ferma_al_nuovo_avvio()
                # ``run_once`` rilegge il control da sola: leggerlo anche qui
                # voleva dire due query al secondo per lo stesso dato. I
                # parametri del giro PRECEDENTE bastano a decidere quanto
                # aspettare prima del prossimo.
                params = _ULTIMI_PARAMS or C.merge_params(None)
                interval = max(1.0, float(params.get("decide_min_interval_ms", 500)) / 1000.0 * 2)
                res = run_once(atlas=atlas, dry=args.dry)
                params = _ULTIMI_PARAMS or params
                # RITMO ADATTIVO: col ciclo pieno solo quando qualcosa si muove
                # da solo (partita in gioco, ordine vivo, richiesta dalla UI).
                if not res.get("fretta") and not res.get("actions") and not res.get("settled"):
                    interval = max(interval, float(params.get("idle_cycle_s") or interval))
                if res.get("new") or res.get("actions") or res.get("settled") or res.get("requests"):
                    logger.info("[mike] ciclo: %s", {k: res[k] for k in ("new", "actions", "settled", "requests")})
                if args.once:
                    logger.info("[mike] --once: %s", res)
                    break
            except KeyboardInterrupt:
                break
            except Exception as ex:  # noqa: BLE001 — il loop non deve morire
                logger.exception("[mike] errore di ciclo: %s", str(ex)[:200])
                try:
                    _real_db.log("error", {"reason": "cycle_exception", "err": str(ex)[:200]})
                except Exception:  # noqa: BLE001
                    pass
                if args.once:
                    break
            # F5: stessa dormita di oggi, ma svegliabile a interruttore acceso.
            # Il PAVIMENTO esce dai parametri dell'ultimo giro ed e' la cadenza
            # attiva: la garanzia che i giri al minuto non crescano.
            _dormi_o_sveglia(interval, _ULTIMI_PARAMS)
    finally:
        if lock is not None:
            try:
                lock.close()
            except Exception:  # noqa: BLE001
                pass


if __name__ == "__main__":
    main()
