"""reconcile_worker.py — A2: RICONCILIAZIONE dello specchio col CONTO Betfair (+ A6 ripresa).

Due responsabilita' DISTINTE del RUNNER (vedi runner.py):

  * IL SALDO (``run_account_sync_if_due`` + ``sync_account_worker``) — SEMPRE
    attivo, in QUALUNQUE LIVE_ORDER_MODE (OFF/PAPER/LIVE, fix 18/09): il saldo
    del CONTO Betfair è un fatto del CONTO, non del bot calcio — deve
    aggiornarsi anche quando il runner calcio è fermo/PAPER mentre altri bot
    (Omega/Safe/Mike/tennis, PROCESSI SEPARATI) sono LIVE sullo stesso conto.
    Cadenza FISSA 20s (3 chiamate REST/min), indipendente dalla mode.
    Saldo/exposure da ``getAccountFunds`` → ``betfair_live_account``
    (write-on-change) + publish sul canale locale (``local_channel``, zero
    costo DB) a OGNI lettura riuscita, cambiata o no: è la freschezza che il
    frontend mostra quando l'app è aperta.
    CHIAMATO DA DUE POSTI (18/09 sera, reperto del coordinatore): un
    BackgroundWorker (``sync_account_worker``, gira SOLO dentro
    ``framework.run()``, cioè con lo stream attivo) NON basta — lo stato
    normale del runner calcio ad app aperta senza partite seguite è il ciclo
    IDLE di ``runner.py`` (``if not follows:`` / ``if not market_ids:``), dove
    NESSUN BackgroundWorker esiste ancora. ``run_account_sync_if_due`` è quindi
    chiamata anche DIRETTAMENTE dal ciclo idle, con lo STESSO orologio
    (``_LAST_ACCOUNT_TS`` di modulo): mai due chiamate REST nello stesso
    intervallo di 20s nel passaggio idle→run o viceversa.
  * ``reconcile_worker`` — registrato SOLO con LIVE_ORDER_MODE ∈ {PAPER, LIVE}
    (invariato), ma la riconciliazione ORDINI che fa gira SOLO in LIVE (il
    conto riflette solo ordini reali, mai quelli simulati del paper). Il CONTO
    Betfair è la VERITÀ ULTIMA: dove specchio e conto divergono, vince SEMPRE
    il conto. Ad ogni ciclo LIVE:
     a. current orders REST (paginati) vs specchio ``betfair_live_orders``;
     b. ordini ESTERNI (piazzati dal sito, mai visti dal runner) → upsert nello
        specchio con ``client_order_ref = ext<bet_id>`` e ``source='account'``
        + alert WARN una volta per bet;
     c. DIVERGENZE (size_matched/status) → lo specchio viene CORRETTO coi
        valori del conto + alert WARN una volta per bet;
     d. ordini specchio EXECUTABLE assenti dal conto → MAI toccati (lo stream
        può essere più aggiornato del REST), solo WARN se persiste 2 cicli;
     e. cleared orders della giornata locale (groupBy MARKET) →
        ``betfair_live_settled`` (write-on-change): il P&L realizzato viene
        dal conto, non da una stima.
     f. (A6, una volta per avvio) report di RIPRESA: alert INFO con il
        riepilogo conto/specchio + verifica delle regole armate il cui
        ``entry_bet_id`` non esiste più né sul conto né nello specchio (WARN:
        restano armate, il flatten ricalcola dalle esposizioni reali).

MONEY-CRITICAL:
  * il conto vince SEMPRE: mai "correggere" il conto dallo specchio;
  * gli ordini esterni NON vengono mai ignorati: entrano nello specchio
    (chi somma lo specchio — xhedge, esposizioni — deve vederli) e l'utente
    viene avvisato (WARN, una volta per bet: anti-spam, mai silenzioso);
  * un ordine specchio assente dal REST NON viene cancellato/chiuso d'ufficio:
    il REST può essere in ritardo sullo stream — solo segnalazione;
  * REST KO → log warning e retry al prossimo ciclo: il saldo che salta NON
    blocca la riconciliazione ordini (e viceversa, sono worker separati). MAI
    far cadere il runner;
  * la riconciliazione ORDINI resta SOLO LIVE — mai in OFF/PAPER: gli ordini
    simulati del paper non sono sul conto, "riconciliarli" significherebbe
    cancellare/alterare lo specchio paper sulla base del conto reale.
  * UNA sola fonte per ``getAccountFunds``: solo ``run_account_sync_if_due``
    lo chiama, con un SOLO orologio di cadenza condiviso fra i due chiamanti
    (worker + ciclo idle) — mai duplicato altrove, mai due chiamate REST nello
    stesso intervallo.

Testabile a unità: session/supabase/db mockabili, nessuna rete.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import live_order_worker as low
from .net_retry import with_backoff
from .trading.daily_pnl import day_window_utc

logger = logging.getLogger(__name__)

_RECONCILE_TABLE = "betfair_live_orders"
_MAX_PAGES = 5  # cap difensivo alla paginazione REST (5×1000 ordini: oltre è patologico)

# anti-spam: chiavi (prefissate per tipo) delle divergenze già segnalate.
_ALERTED_BETS: set[str] = set()
# report di ripresa (A6) fatto una volta per mode per avvio del runner.
_STARTUP_DONE: dict[str, bool] = {}
# bet EXECUTABLE nello specchio ma assenti dal conto: cicli consecutivi visti.
_MISSING_SEEN: dict[str, int] = {}
# write-on-change del saldo / dei settled per mercato.
_LAST_ACCOUNT_SIG: Optional[Tuple] = None
_LAST_ACCOUNT_TS = 0.0  # monotonic dell'ultimo getAccountFunds (cadenza, vedi sync_account_worker)
_LAST_CLEARED_SIG: Dict[str, Tuple] = {}
# 18/09: cadenza FISSA del saldo, indipendente da LIVE_ORDER_MODE (prima era
# 60s PAPER/20s LIVE dentro _process_once — ma con OFF il worker non girava
# affatto: il saldo restava fermo per giorni se il runner calcio non era in
# PAPER/LIVE, anche con altri bot LIVE sullo stesso conto). 20s = 3 REST/min.
_ACCOUNT_SYNC_INTERVAL_SEC = 20.0


def _alert(level: str, msg: str) -> None:
    try:
        from . import db

        db.insert_alert(level, "RECONCILE", msg)
    except Exception:  # noqa: BLE001 - alert best-effort
        pass


def _warn_once(key: str, msg: str) -> None:
    """Alert WARN al massimo UNA volta per chiave (anti-spam per bet)."""
    if key in _ALERTED_BETS:
        return
    _ALERTED_BETS.add(key)
    _alert("WARN", msg)


def _rest(fn: Callable[[], Any]) -> Any:
    """Chiamata REST Betfair con retry SOLO su errori transitori di rete (A1).

    ``sleep=time.sleep`` risolto a runtime (testabile senza attese reali)."""
    return with_backoff(fn, attempts=2, base_delay=0.5, sleep=time.sleep)


def _now_local() -> datetime:
    """Ora nella timezone della giornata (Europe/Rome, come il daily stop)."""
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Europe/Rome"))
    except Exception:  # noqa: BLE001 - tzdata assente: fallback al fuso di sistema
        return datetime.now().astimezone()


def _round2(v: Optional[float]) -> Optional[float]:
    return round(v, 2) if v is not None else None


# ---------------------------------------------------------------------------
# 1) Saldo del conto (QUALUNQUE mode, vedi sync_account_worker) — write-on-change
# ---------------------------------------------------------------------------
def _sync_account(session: Any) -> None:
    global _LAST_ACCOUNT_SIG
    try:
        funds = _rest(lambda: session.context_api_client.account.get_account_funds())
    except Exception as ex:  # noqa: BLE001 - best-effort periodico: ritenta al prossimo ciclo
        logger.warning("[reconcile] getAccountFunds KO: %s", str(ex)[:200])
        return
    sig = (
        _round2(low._f(low._val(funds, "available_to_bet_balance"))),
        _round2(low._f(low._val(funds, "exposure"))),
    )
    # 18/09: publish SEMPRE sul canale locale (127.0.0.1:47331, zero costo DB),
    # a OGNI lettura riuscita — cambiata o no. E' la freschezza "controllato N
    # secondi fa" che il frontend mostra ad app aperta: write-on-change sotto
    # fa si' che ``betfair_live_account.updated_at`` NON si muova quando il
    # saldo e' invariato, quindi da solo non basta a dire "e' stato controllato
    # adesso". Best-effort: un canale assente/inattivo non deve mai bloccare
    # la scrittura del saldo.
    try:
        from . import local_channel as _lc

        _lc.publish(
            "account",
            {
                "available": sig[0],
                "exposure": sig[1],
                "checked_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception:  # noqa: BLE001 - canale opzionale, mai bloccare il saldo
        pass
    if sig == _LAST_ACCOUNT_SIG:
        return
    try:
        from . import db

        db.upsert_live_account(sig[0], sig[1])
        _LAST_ACCOUNT_SIG = sig
    except Exception as ex:  # noqa: BLE001 - retry al prossimo ciclo
        logger.warning("[reconcile] upsert account KO: %s", str(ex)[:200])


def run_account_sync_if_due(session: Any) -> None:
    """Nucleo CONDIVISO del saldo: cadenza + chiamata, un SOLO orologio.

    18/09 sera (reperto del coordinatore): ``sync_account_worker`` sotto e' un
    ``BackgroundWorker`` di flumine, e i BackgroundWorker vivono SOLO dentro
    ``framework.run()``. Ma lo stato NORMALE del runner calcio ad app aperta,
    SENZA partite seguite, e' PARCHEGGIATO nel ciclo idle di ``runner.py``
    (``if not follows:`` / ``if not market_ids:``, keep-alive desktop) — dove
    ``framework`` non esiste ancora e NESSUN worker gira (e' lo stesso motivo
    per cui il battito lì si scrive A MANO, vedi commento 14/09 in runner.py).
    Con SOLO il worker, il saldo restava fermo esattamente quando l'utente non
    segue live una partita — cioe' quasi sempre.

    Questa funzione e' quindi chiamata da DUE punti (vedi runner.py):
      * dal ciclo idle, subito prima/dopo il battito scritto a mano;
      * da ``sync_account_worker`` (BackgroundWorker), quando lo stream e' su.
    Un SOLO ``_LAST_ACCOUNT_TS`` globale garantisce UN SOLO orologio: nel
    passaggio idle -> run (o viceversa) non scatta MAI una seconda chiamata
    REST nello stesso intervallo di 20s, perche' entrambi i chiamanti leggono
    e aggiornano la STESSA variabile di modulo.

    Guardie: `session`/`context_api_client` assenti -> no-op silenzioso (fase
    di avvio, prima del login). Non solleva MAI (chiamata sia dal thread del
    BackgroundWorker sia dal thread principale del ciclo idle: un'eccezione
    qui non deve mai fermare ne' l'uno ne' l'altro).
    """
    if session is None or getattr(session, "context_api_client", None) is None:
        return
    global _LAST_ACCOUNT_TS
    now_mono = time.monotonic()
    if now_mono - _LAST_ACCOUNT_TS < _ACCOUNT_SYNC_INTERVAL_SEC:
        return
    _LAST_ACCOUNT_TS = now_mono
    sig_before = _LAST_ACCOUNT_SIG
    try:
        _sync_account(session)
    except Exception as ex:  # noqa: BLE001 - mai far cadere ne' il worker ne' il ciclo idle
        logger.exception("[reconcile] run_account_sync_if_due KO: %s", str(ex)[:200])
    # Parte B (18/09 sera): il manuale gira alla STESSA cadenza del saldo (60s
    # normalmente), MA un cambio di saldo appena visto (= qualcosa si e'
    # regolato) lo fa scattare SUBITO, senza aspettare i 60s residui.
    changed = _LAST_ACCOUNT_SIG != sig_before
    _run_manual_pnl_if_due(session, force=changed)


def annota_lettura_esterna(sig: Tuple[Optional[float], Optional[float]]) -> None:
    """23/09 - una lettura del saldo fatta DOPO UN EVENTO D'ORDINE in questo
    stesso processo (``saldo_evento``) ha gia' scritto e pubblicato ``sig``:
    la cadenza fissa riparte da adesso (niente seconda chiamata a pochi
    secondi) e la firma write-on-change si allinea (niente riscrittura
    identica al giro dopo)."""
    global _LAST_ACCOUNT_SIG, _LAST_ACCOUNT_TS
    _LAST_ACCOUNT_SIG = sig
    _LAST_ACCOUNT_TS = time.monotonic()


def attiva_saldo_su_evento(framework: Any, session: Any) -> None:
    """23/09 - runner in LIVE: saldo riletto dopo ogni ordine REALE confermato
    da Betfair e dopo ogni regolazione (``OrderEvent``/``ClearedOrdersEvent`` di
    flumine), con lo STESSO client e lo stesso ``_rest`` di ``_sync_account``.
    Mai solleva: senza questo il runner lavora come prima (cadenza 20 s)."""
    try:
        from . import saldo_evento

        if session is None or getattr(session, "context_api_client", None) is None:
            return
        saldo_evento.attiva(
            lambda: _rest(lambda: session.context_api_client.account.get_account_funds()),
            nome="calcio",
            dopo_lettura=annota_lettura_esterna,
        )
        framework.add_logging_control(saldo_evento.controllo_flumine())
    except Exception as ex:  # noqa: BLE001
        logger.warning("[reconcile] rilettura saldo su evento NON attiva: %s", str(ex)[:200])


def sync_account_worker(context: Any, flumine: Any, session: Any = None, strategy: Any = None) -> None:
    """BackgroundWorker SEMPRE registrato (OFF/PAPER/LIVE, vedi runner.py, 18/09).

    Copre SOLO la fase in cui lo stream e' attivo (dentro ``framework.run()``);
    la fase idle (nessuna partita seguita) e' coperta chiamando DIRETTAMENTE
    ``run_account_sync_if_due`` dal ciclo idle di ``runner.py`` — vedi il
    docstring sopra per il perche' serva una seconda chiamata."""
    run_account_sync_if_due(session)


# ---------------------------------------------------------------------------
# 2) Riconciliazione ordini (SOLO LIVE): il CONTO vince sempre
# ---------------------------------------------------------------------------
def _fetch_current_orders(session: Any) -> Dict[str, Any]:
    """Tutti i current orders del CONTO, paginati: dict bet_id → CurrentOrder."""
    orders: Dict[str, Any] = {}
    from_record = 0
    for _page in range(_MAX_PAGES):
        res = _rest(
            lambda fr=from_record: session.context_api_client.betting.list_current_orders(
                from_record=fr, record_count=1000
            )
        )
        page = low._val(res, "orders") or []
        for order in page:
            bet_id = low._val(order, "bet_id")
            if bet_id is not None:
                orders[str(bet_id)] = order
        from_record += len(page)
        if not page or not low._val(res, "more_available"):
            break
    return orders


def _dt_iso(v: Any) -> Optional[str]:
    if v is None:
        return None
    try:
        return v.isoformat()
    except Exception:  # noqa: BLE001 - già stringa o tipo esotico
        return str(v)


def _account_order_row(order: Any) -> Dict[str, Any]:
    """Riga specchio COMPLETA per un ordine visto SOLO sul conto (source='account').

    Shape allineata a ``LiveTradingStrategy._order_row`` (specchio betfair_live_orders),
    campi mappati dal CurrentOrder betfairlightweight."""
    bet_id = str(low._val(order, "bet_id"))
    side = low._val(order, "side")
    ps = low._val(order, "price_size")
    # fix 11/07 (rumore live 10/07): flumine stampa customerStrategyRef su
    # OGNI ordine bot → un ordine col ref NON e' "esterno dal sito", e' di un
    # bot noto (scalper/sniper girano in un processo separato dal runner).
    csr = low._val(order, "customer_strategy_ref")
    source = (f"bot:{csr}"[:32] if csr and str(csr) != "live" else "account")
    return {
        "bet_id": bet_id,
        "client_order_ref": f"ext{bet_id}"[:32],
        "mode": "live",
        "source": source,
        "market_id": low._val(order, "market_id"),
        "selection_id": low._int(low._val(order, "selection_id")),
        "handicap": low._f(low._val(order, "handicap")) or 0.0,
        "side": side.lower() if isinstance(side, str) else side,
        "order_type": str(low._val(order, "order_type") or "LIMIT"),
        "price": low._f(low._val(ps, "price")) if ps is not None else None,
        "size": low._f(low._val(ps, "size")) if ps is not None else None,
        "size_matched": low._f(low._val(order, "size_matched")) or 0.0,
        "size_remaining": low._f(low._val(order, "size_remaining")) or 0.0,
        "size_cancelled": low._f(low._val(order, "size_cancelled")) or 0.0,
        "size_lapsed": low._f(low._val(order, "size_lapsed")) or 0.0,
        "size_voided": low._f(low._val(order, "size_voided")) or 0.0,
        "average_price_matched": low._f(low._val(order, "average_price_matched")) or 0.0,
        "status": low._val(order, "status"),
        "persistence": low._val(order, "persistence_type"),
        "placed_at": _dt_iso(low._val(order, "placed_date")),
    }


def _reconcile_orders(sb: Any, current: Dict[str, Any], mirror: List[Dict[str, Any]]) -> int:
    """Confronto conto ↔ specchio. Ritorna il numero di ordini ESTERNI trovati."""
    by_bet = {str(r["bet_id"]): r for r in mirror if r.get("bet_id")}

    # b) ordini ESTERNI: sul conto ma NON nello specchio → entrano nello specchio.
    externals = 0
    for bet_id, order in current.items():
        if bet_id in by_bet:
            continue
        row = _account_order_row(order)
        try:
            sb.table(_RECONCILE_TABLE).upsert(row, on_conflict="mode,client_order_ref").execute()
        except Exception as ex:  # noqa: BLE001 - upsert idempotente: retry al prossimo ciclo
            logger.warning("[reconcile] upsert esterno %s KO: %s", bet_id, str(ex)[:200])
        if str(row.get("source") or "").startswith("bot:"):
            # ordine di un BOT noto (customerStrategyRef presente): entra
            # nello specchio ma NIENTE allarme — la pioggia di WARN del
            # 10/07 rendeva il feed alert inutile proprio quando serviva.
            continue
        externals += 1
        _warn_once(
            f"ext:{bet_id}",
            f"ordine ESTERNO sul conto (dal sito?): bet {bet_id} "
            f"mercato {low._val(order, 'market_id')} — aggiunto allo specchio.",
        )

    # c) DIVERGENZE: bet in entrambi ma con fill/status diversi → il CONTO vince.
    for bet_id, order in current.items():
        row = by_bet.get(bet_id)
        if row is None:
            continue
        acc_matched = low._f(low._val(order, "size_matched")) or 0.0
        acc_status = low._val(order, "status")
        mir_matched = low._f(row.get("size_matched")) or 0.0
        mir_status = row.get("status")
        if abs(mir_matched - acc_matched) <= 0.01 and mir_status == acc_status:
            continue
        updates = {
            "size_matched": acc_matched,
            "size_remaining": low._f(low._val(order, "size_remaining")) or 0.0,
            "size_cancelled": low._f(low._val(order, "size_cancelled")) or 0.0,
            "size_lapsed": low._f(low._val(order, "size_lapsed")) or 0.0,
            "size_voided": low._f(low._val(order, "size_voided")) or 0.0,
            "average_price_matched": low._f(low._val(order, "average_price_matched")) or 0.0,
            "status": acc_status,
        }
        try:
            (
                sb.table(_RECONCILE_TABLE)
                .update(updates)
                .eq("mode", "live")
                .eq("bet_id", bet_id)
                .execute()
            )
        except Exception as ex:  # noqa: BLE001 - retry al prossimo ciclo
            logger.warning("[reconcile] correzione %s KO: %s", bet_id, str(ex)[:200])
        _warn_once(
            f"div:{bet_id}",
            f"specchio divergente dal conto, corretto: bet {bet_id} "
            f"matched {mir_matched}→{acc_matched}, status {mir_status}→{acc_status}.",
        )

    # d) specchio NON-terminale ma assente dal conto: MAI toccare (lo stream può
    # essere più aggiornato del REST) — WARN solo se persiste 2 cicli consecutivi.
    # gli ordini bot (source 'bot:*' o 'account') spariscono dal conto per i
    # cancel rapidi del maker (requote/scratch): e' il loro funzionamento
    # normale, non un'anomalia da segnalare (rumore live 10/07).
    missing_now = {
        str(r["bet_id"])
        for r in mirror
        if r.get("bet_id") and r.get("status") == "EXECUTABLE"
        and str(r["bet_id"]) not in current
        and not str(r.get("source") or "").startswith("bot:")
        and str(r.get("source") or "") != "account"
    }
    for bet_id in list(_MISSING_SEEN):
        if bet_id not in missing_now:
            _MISSING_SEEN.pop(bet_id, None)  # ricomparso/risolto: reset del contatore
    for bet_id in missing_now:
        _MISSING_SEEN[bet_id] = _MISSING_SEEN.get(bet_id, 0) + 1
        if _MISSING_SEEN[bet_id] >= 2:
            _warn_once(
                f"miss:{bet_id}",
                f"ordine specchio EXECUTABLE bet {bet_id} ASSENTE dai current orders "
                "del conto da 2 cicli — verificare (riga NON toccata).",
            )
    return externals


# ---------------------------------------------------------------------------
# 2e) Settled dal conto: cleared orders della giornata (verità ultima)
# ---------------------------------------------------------------------------
def _event_by_market(sb: Any) -> Dict[str, str]:
    """market_id → event_id dallo specchio ordini live (fix review MEDIUM: il
    settled scritto da REST deve portare event_id come quello del path blotter,
    per i raggruppamenti per-evento della dashboard). Best-effort: {} su errore."""
    try:
        res = (
            sb.table("betfair_live_orders")
            .select("market_id,event_id")
            .eq("mode", "live")
            .limit(1000)
            .execute()
        )
        rows = getattr(res, "data", None) or []
        return {
            str(r["market_id"]): str(r["event_id"])
            for r in rows
            if r.get("market_id") and r.get("event_id")
        }
    except Exception:  # noqa: BLE001 - arricchimento opzionale
        return {}


def _sync_cleared(session: Any, sb: Any = None) -> None:
    from betfairlightweight import filters

    start_utc, end_utc = day_window_utc(_now_local())
    date_range = filters.time_range(from_=start_utc.isoformat(), to=end_utc.isoformat())
    groups: List[Any] = []
    from_record = 0
    for _page in range(_MAX_PAGES):
        res = _rest(
            lambda fr=from_record: session.context_api_client.betting.list_cleared_orders(
                bet_status="SETTLED",
                group_by="MARKET",
                settled_date_range=date_range,
                from_record=fr,
                record_count=1000,
            )
        )
        page = low._val(res, "orders") or []
        groups.extend(page)
        from_record += len(page)
        if not page or not low._val(res, "more_available"):
            break

    ev_map = _event_by_market(sb) if sb is not None else {}
    for group in groups:
        market_id = low._val(group, "market_id")
        profit = low._f(low._val(group, "profit"))
        if market_id is None or profit is None:
            continue
        bet_count = low._int(low._val(group, "bet_count")) or 0
        sig = (round(profit, 2), bet_count)
        if _LAST_CLEARED_SIG.get(str(market_id)) == sig:
            continue
        try:
            from . import db

            db.upsert_live_settled(
                {
                    "mode": "live",
                    "market_id": market_id,
                    "event_id": ev_map.get(str(market_id)),
                    "profit": round(profit, 2),
                    "orders": bet_count,
                    "source": "cleared",
                }
            )
            _LAST_CLEARED_SIG[str(market_id)] = sig
        except Exception as ex:  # noqa: BLE001 - upsert idempotente: retry al prossimo ciclo
            logger.warning("[reconcile] upsert settled %s KO: %s", market_id, str(ex)[:200])


# ---------------------------------------------------------------------------
# Manuale (Parte B, 18/09 sera): P&L di OGGI delle operazioni NON dei bot
# (piazzate dal SITO Betfair). Girato da run_account_sync_if_due (QUALUNQUE
# LIVE_ORDER_MODE, mai in paper: il conto e' reale per definizione), cadenza
# bassa (60s) + SUBITO dopo un cambio di saldo (segnale di un settlement).
# NON duplica il futuro importer di personal_trades (entry_source='import',
# vedi migrations/personal_tracking_manual_entry.sql): questo e' SOLO un
# totale di giornata in tempo quasi reale, scritto su betfair_live_account.
# ---------------------------------------------------------------------------
_MANUAL_PNL_INTERVAL_SEC = 60.0
_LAST_MANUAL_PNL_TS = 0.0
_LAST_MANUAL_PNL_SIG: Optional[Tuple] = None

# Censimento 18/09, CORRETTO il 18/09 sera "terzo giro" dopo audit puntuale di
# CIASCUN file che chiama ``market.place_order`` (vedi CHECKPOINT §16-17):
#   * ``omega``/``mike`` -> bot REALI con customerStrategyRef esplicito (Safe
#     eredita "omega": nessun ref proprio, `Betfair/safe_strategy/bot_service.py:45`
#     importa `omega_market` senza mai ripatchare CUSTOMER_STRATEGY_REF).
#   * ``live`` (calcio, `Betfair/stream/live_order_worker.py:53`) e ``tennis``
#     (`Betfair/stream/tennis_live/tennis_live_order_worker.py:34`) NON sono bot:
#     sono il ref del TERMINALE DI TRADING MANUALE della nostra app (ladder +
#     comandi place/cashout/greenup via RPC, `migrations/betfair_live_cashout*.sql`
#     `migrations/betfair_live_greenup.sql`, + chiusure di risk_rule su posizioni
#     APERTE A MANO dall'utente) — verificato: `tennis_live_order_worker.py:1-6`
#     lo dichiara ESPLICITAMENTE ("drena tennis_live_order_queue, ordini MANUALI
#     della ladder"), e nessun file sotto `Betfair/stream/scalper/` o
#     `Betfair/stream/tennis_scalper/` (i bot AUTONOMI veri) usa questi ref.
#     Per l'utente ("tutto cio' che non e' bot: dal sito O dalla nostra app")
#     questi ordini vanno nel MANUALE, sotto-classe 'manual_app' (calcio+tennis
#     insieme: lo stesso ref serve sia ladder-click sia risk-rule, e non sono
#     distinguibili fra loro — ne' serve, sono comunque manuali per l'utente).
#   * QUALUNQUE ALTRO customerStrategyRef presente (compreso uno NON ancora
#     censito qui) -> 'ours': il sito non manda MAI questo campo, quindi se
#     c'e' e non e' live/tennis e' un bot, anche uno futuro.
_MANUAL_APP_STRATEGY_REFS = frozenset({"live", "tennis"})
# prefissi di customerOrderRef dei nostri bot: seconda rete SOLO quando lo
# strategy ref manca (difensivo, es. un futuro bot che dimentica il ref).
_OUR_ORDER_REF_PREFIXES = ("omega-", "safe-t", "mike-t")


def _classify_cleared_order(order: Any) -> str:
    """'ours' | 'manual_app' | 'manual' | 'ambiguous'.

    Precedente 15/09 (customerOrderRef vs customer_order_ref): le chiavi qui
    sono lette con ``low._val`` esattamente come le espone l'oggetto
    ``ClearedOrder`` di betfairlightweight (snake_case reale, verificato in
    ``betfairlightweight/resources/bettingresources.py``), mai un dict/camelCase
    a mano.

    'manual_app' = ref "live"/"tennis" (terminale di trading MANUALE della
    nostra app, calcio o tennis — MAI un bot, vedi censimento sopra): erode
    l'obiettivo come il manuale dal sito, ma contato SEPARATO
    (``manual_app_pnl_*``).
    'ambiguous' (ref presente ma irriconoscibile: ne' un nostro bot ne'
    manual_app ne' chiaramente il sito) -> MAI nel manuale, contato a parte
    ("nel dubbio escludi e conta gli esclusi", ordine esplicito).
    'manual' = NESSUN ref leggibile (ne' strategy ne' order): il caso NORMALE
    di una scommessa dal sito. ATTENZIONE (dichiarato, vedi CHECKPOINT §17):
    OGGI questo stesso bucket include ANCHE gli ordini reali dei bot
    AUTONOMI (scalper/sniper calcio, i 4 bot tennis) perche' quei file NON
    passano alcun customerStrategyRef a ``market.place_order`` — non
    distinguibile da qui, serve un fix nel loro codice (proposto, non
    applicato: sono file di strategia).
    """
    sref = low._val(order, "customer_strategy_ref")
    oref = low._val(order, "customer_order_ref")
    sref_s = str(sref).strip() if sref else ""
    oref_s = str(oref).strip() if oref else ""
    if sref_s.lower() in _MANUAL_APP_STRATEGY_REFS:
        return "manual_app"
    if sref_s:
        return "ours"  # presente e non manual_app = un bot, chiunque sia
    if oref_s.startswith(_OUR_ORDER_REF_PREFIXES):
        return "ours"
    if not sref_s and not oref_s:
        return "manual"
    return "ambiguous"


def _fetch_cleared_orders_today(session: Any) -> List[Any]:
    """``listClearedOrders`` di OGGI (giorno Rome, STESSA finestra di
    ``_sync_cleared``), NON raggruppati (bet-level: i soli che portano
    customerStrategyRef/customerOrderRef/commission per singolo ordine).
    Paginato (moreAvailable, stesso cap difensivo ``_MAX_PAGES``)."""
    from betfairlightweight import filters

    start_utc, end_utc = day_window_utc(_now_local())
    date_range = filters.time_range(from_=start_utc.isoformat(), to=end_utc.isoformat())
    orders: List[Any] = []
    from_record = 0
    for _page in range(_MAX_PAGES):
        res = _rest(
            lambda fr=from_record: session.context_api_client.betting.list_cleared_orders(
                bet_status="SETTLED",
                settled_date_range=date_range,
                from_record=fr,
                record_count=1000,
            )
        )
        page = low._val(res, "orders") or []
        orders.extend(page)
        from_record += len(page)
        if not page or not low._val(res, "more_available"):
            break
    return orders


def _sum_pnl(orders: List[Any]) -> "Tuple[float, bool, int]":
    """Somma profit/commissione di una lista di ordini GIA' filtrata.

    Ritorna (pnl_eur, is_net, n_ordini). ``is_net`` False (LORDO, mai finto
    netto) se la commissione manca su almeno un ordine o la lista e' vuota."""
    profit_tot = 0.0
    commission_tot = 0.0
    commission_readable = True
    n = 0
    for order in orders:
        profit = low._f(low._val(order, "profit"))
        if profit is None:
            continue
        profit_tot += profit
        n += 1
        commission = low._f(low._val(order, "commission"))
        if commission is None:
            commission_readable = False
        else:
            commission_tot += commission
    is_net = commission_readable and n > 0
    pnl = round(profit_tot - commission_tot, 2) if is_net else round(profit_tot, 2)
    return pnl, is_net, n


def _sync_manual_pnl(session: Any) -> None:
    """Calcola e scrive (write-on-change) il P&L manuale di oggi — DUE totali
    SEPARATI (terzo giro, 18/09 sera, ordine esplicito dell'utente "tutto cio'
    che non e' bot: dal sito O dalla nostra app"):
      * ``manual_pnl_*``     — dal SITO Betfair (nessun ref leggibile);
      * ``manual_app_pnl_*`` — dal TERMINALE MANUALE della nostra app
        (calcio+tennis, ref "live"/"tennis" — MAI un bot, vedi censimento
        in ``_classify_cleared_order``).
    ``manual_pnl_excluded`` resta un contatore UNICO (ordini 'ambiguous',
    ref presente ma irriconoscibile): non si sa a quale bucket assegnarli,
    quindi non stanno in nessuno dei due totali, solo nel diagnostico.

    MONEY-CRITICAL: un KO REST NON tocca MAI i totali gia' scritti (si esce
    PRIMA di toccare la firma write-on-change) — mai azzerare per un guasto
    transitorio. Non solleva MAI (chiamata da run_account_sync_if_due)."""
    global _LAST_MANUAL_PNL_SIG
    try:
        orders = _fetch_cleared_orders_today(session)
    except Exception as ex:  # noqa: BLE001 - REST KO: i totali restano quelli di prima
        logger.warning("[reconcile] listClearedOrders (manuale) KO: %s", str(ex)[:200])
        return

    site_orders: List[Any] = []
    app_orders: List[Any] = []
    n_ambiguous = 0
    for order in orders:
        kind = _classify_cleared_order(order)
        if kind == "ours":
            continue
        if kind == "ambiguous":
            n_ambiguous += 1
            continue
        if kind == "manual_app":
            app_orders.append(order)
        else:  # 'manual' (sito)
            site_orders.append(order)

    pnl_value, is_net, n_manual = _sum_pnl(site_orders)
    app_pnl_value, app_is_net, n_app = _sum_pnl(app_orders)
    day = _now_local().strftime("%Y-%m-%d")

    sig = (pnl_value, is_net, n_manual, n_ambiguous, day, app_pnl_value, app_is_net, n_app)
    if sig == _LAST_MANUAL_PNL_SIG:
        return
    try:
        from . import db

        db.upsert_live_account_manual_pnl(
            pnl_eur=pnl_value, is_net=is_net, orders=n_manual, excluded=n_ambiguous, day=day,
            app_pnl_eur=app_pnl_value, app_is_net=app_is_net, app_orders=n_app,
        )
        _LAST_MANUAL_PNL_SIG = sig
    except Exception as ex:  # noqa: BLE001 - migrazione non applicata o DB KO: ritenta al giro dopo
        logger.warning(
            "[reconcile] upsert manuale KO (migrazione betfair_live_account_manual_pnl.sql "
            "applicata?): %s", str(ex)[:200],
        )
        return
    # publish SEMPRE sul canale locale (STESSO topic 'account' del saldo, zero
    # costo DB): il frontend vede il manuale aggiornato in tempo reale ad app aperta.
    try:
        from . import local_channel as _lc

        _lc.publish(
            "account",
            {
                "manual_pnl_eur": pnl_value,
                "manual_pnl_is_net": is_net,
                "manual_pnl_orders": n_manual,
                "manual_pnl_excluded": n_ambiguous,
                "manual_pnl_day": day,
                "manual_app_pnl_eur": app_pnl_value,
                "manual_app_pnl_is_net": app_is_net,
                "manual_app_pnl_orders": n_app,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception:  # noqa: BLE001 - canale opzionale, mai bloccare il dato
        pass


def _run_manual_pnl_if_due(session: Any, *, force: bool = False) -> None:
    """Cadenza bassa (60s) + trigger immediato (``force=True``) subito dopo
    un cambio di saldo (segnale che qualcosa si e' appena regolato). Non
    solleva MAI."""
    global _LAST_MANUAL_PNL_TS
    now_mono = time.monotonic()
    if not force and (now_mono - _LAST_MANUAL_PNL_TS) < _MANUAL_PNL_INTERVAL_SEC:
        return
    _LAST_MANUAL_PNL_TS = now_mono
    try:
        _sync_manual_pnl(session)
    except Exception as ex:  # noqa: BLE001 - mai far cadere ne' il worker ne' il ciclo idle
        logger.exception("[reconcile] _run_manual_pnl_if_due KO: %s", str(ex)[:200])


# ---------------------------------------------------------------------------
# 3) Ripresa (A6): report una volta per avvio + regole armate orfane
# ---------------------------------------------------------------------------
def _startup_report(
    sb: Any, mode_l: str, current: Dict[str, Any], mirror: List[Dict[str, Any]], externals: int
) -> None:
    if _STARTUP_DONE.get(mode_l):
        return
    _STARTUP_DONE[mode_l] = True
    _alert(
        "INFO",
        f"ripresa LIVE: {len(current)} ordini correnti sul conto, "
        f"{externals} esterni, {len(mirror)} righe specchio.",
    )
    # regole armate con entry_bet_id che non esiste più né sul conto né nello specchio:
    # restano armate (il flatten ricalcola dalle esposizioni reali) ma vanno DICHIARATE.
    try:
        res = (
            sb.table("betfair_live_risk_rules")
            .select("id,entry_bet_id,market_id")
            .eq("status", "armed")
            .eq("mode", "live")
            .execute()
        )
        rules = getattr(res, "data", None) or []
        mirror_bets = {str(r["bet_id"]) for r in mirror if r.get("bet_id")}
        for rule in rules:
            entry_bet = rule.get("entry_bet_id")
            if not entry_bet:
                continue
            if str(entry_bet) in current or str(entry_bet) in mirror_bets:
                continue
            _alert(
                "WARN",
                f"regola {rule.get('id')} armata con riferimento bet {entry_bet} non trovato "
                "dopo il riavvio (resta armata: il flatten ricalcola dalle esposizioni reali).",
            )
    except Exception as ex:  # noqa: BLE001 - report best-effort, il runner prosegue
        logger.warning("[reconcile] verifica regole armate KO: %s", str(ex)[:200])


# ---------------------------------------------------------------------------
# Ciclo
# ---------------------------------------------------------------------------
def _process_once(sb: Any, session: Any, mode_l: str) -> None:
    # 18/09: il saldo NON si tocca piu' qui (e' sync_account_worker, SEMPRE
    # registrato indipendentemente dalla mode). Questa funzione fa SOLO
    # riconciliazione ORDINI, che resta SOLO LIVE — mai OFF, mai PAPER (il
    # conto non riflette gli ordini simulati del paper).
    if mode_l != "live":
        return
    if getattr(session, "context_api_client", None) is None:
        return

    # 2) current orders del conto + specchio → esterni/divergenze/assenti.
    try:
        current = _fetch_current_orders(session)
    except Exception as ex:  # noqa: BLE001 - REST KO: retry al prossimo ciclo
        logger.warning("[reconcile] listCurrentOrders KO: %s", str(ex)[:200])
        return
    try:
        res = (
            sb.table(_RECONCILE_TABLE)
            .select("bet_id,client_order_ref,size_matched,status,source")
            .eq("mode", "live")
            .execute()
        )
        mirror = getattr(res, "data", None) or []
    except Exception as ex:  # noqa: BLE001 - DB KO: retry al prossimo ciclo
        logger.warning("[reconcile] lettura specchio KO: %s", str(ex)[:200])
        return
    externals = _reconcile_orders(sb, current, mirror)

    # 2e) settled della giornata dal conto (best-effort: KO → retry al prossimo ciclo).
    try:
        _sync_cleared(session, sb)
    except Exception as ex:  # noqa: BLE001
        logger.warning("[reconcile] listClearedOrders KO: %s", str(ex)[:200])

    # 3) ripresa A6: report una volta per avvio (solo dopo un ciclo LIVE riuscito).
    _startup_report(sb, mode_l, current, mirror, externals)


def reconcile_worker(context: Any, flumine: Any, session: Any = None, strategy: Any = None) -> None:
    """Entry BackgroundWorker (vedi runner.py) — SOLO riconciliazione ORDINI.

    Registrato con LIVE_ORDER_MODE ∈ {PAPER, LIVE} (invariato, vedi runner.py),
    ma ``_process_once`` e' un no-op fuori da LIVE: il conto non riflette gli
    ordini simulati del paper. Il saldo (QUALUNQUE mode) e' ``sync_account_worker``,
    worker separato. Non solleva MAI.
    """
    if session is None:
        return
    # 24/09: modo di PROCESSO (tetto del .env), non la scelta dalla Control
    # Room: questo worker protegge/riconcilia cio' che e' GIA' a mercato, e un
    # declassamento dalla UI ferma le aperture, mai la sorveglianza.
    mode = low._modo_processo()
    if mode != "LIVE":
        return
    try:
        from db_client import get_supabase_client

        sb = get_supabase_client()
    except Exception as ex:  # noqa: BLE001 - DB non raggiungibile: salta il giro
        logger.warning("[reconcile] client supabase KO: %s", str(ex)[:200])
        return
    try:
        _process_once(sb, session, mode.lower())
    except Exception as ex:  # noqa: BLE001 - il worker non deve mai far cadere il runner
        logger.exception("[reconcile] ciclo KO: %s", str(ex)[:200])
