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
import re
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
    # 24/09: anche un cambio di saldo visto da una lettura fatta ALTROVE
    # (``saldo_evento`` dopo un evento d'ordine, ``annota_lettura_esterna``)
    # e' il segnale di una possibile regolazione: il giro dei regolati parte
    # qui, nel ciclo del saldo, mai da un thread di chi ha piazzato l'ordine.
    global _REGOLATI_DA_RILEGGERE
    changed = _LAST_ACCOUNT_SIG != sig_before or _REGOLATI_DA_RILEGGERE
    _REGOLATI_DA_RILEGGERE = False
    _run_manual_pnl_if_due(session, force=changed)


def annota_lettura_esterna(sig: Tuple[Optional[float], Optional[float]]) -> None:
    """23/09 - una lettura del saldo fatta DOPO UN EVENTO D'ORDINE in questo
    stesso processo (``saldo_evento``) ha gia' scritto e pubblicato ``sig``:
    la cadenza fissa riparte da adesso (niente seconda chiamata a pochi
    secondi) e la firma write-on-change si allinea (niente riscrittura
    identica al giro dopo)."""
    global _LAST_ACCOUNT_SIG, _LAST_ACCOUNT_TS, _REGOLATI_DA_RILEGGERE
    if sig != _LAST_ACCOUNT_SIG:
        # 24/09: il saldo e' cambiato qui e non nel giro del saldo, che quindi
        # non lo vedrebbe mai come cambio: lo si segna per il giro dei regolati
        _REGOLATI_DA_RILEGGERE = True
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


def _fetch_cleared_markets_today(session: Any) -> List[Any]:
    """``listClearedOrders`` di OGGI (giorno Rome) raggruppati per MERCATO,
    SENZA alcun filtro di strategy ref (tutto il conto). E' l'UNICO livello,
    insieme a EVENT/EVENT_TYPE/EXCHANGE, che porta ``commission`` (fonte
    ufficiale in testa alla sezione "P&L REALE" sotto). Paginato."""
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
    return groups


def _sync_cleared(session: Any, sb: Any = None) -> None:
    # 24/09: la lettura per MERCATO e' la stessa che serve al P&L reale
    # (commissione per mercato): si legge UNA volta e si conserva in
    # ``_MERCATI_CACHE``, cosi' il giro dei regolati la riusa invece di
    # rifarla (chiamate REST che diminuiscono, regola del 13/09).
    groups = _leggi_mercati_regolati(session, max_eta_s=0.0)

    # 24/09: la mappa mercato -> evento (una LETTURA DB di fino a 1000 righe)
    # serve solo se c'e' almeno un mercato da scrivere: prima si leggeva a
    # OGNI giro (2 letture/min in LIVE) anche a mercati invariati.
    da_scrivere = []
    for group in groups:
        market_id = low._val(group, "market_id")
        profit = low._f(low._val(group, "profit"))
        if market_id is None or profit is None:
            continue
        bet_count = low._int(low._val(group, "bet_count")) or 0
        if _LAST_CLEARED_SIG.get(str(market_id)) == (round(profit, 2), bet_count):
            continue
        da_scrivere.append(group)
    ev_map = _event_by_market(sb) if (sb is not None and da_scrivere) else {}
    for group in da_scrivere:
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
# P&L REALE DA BETFAIR (24/09, ordini dell'utente 9 e 10)
#
# (9)  "il P&L delle operazioni va preso DIRETTAMENTE da Betfair e non
#      stimato, al netto di tutto (commissione)";
# (10) "la barra di giornata deve avanzare considerando le operazioni di TUTTI
#      i bot attivi e le mie in manuale, sia dalla nostra app che dal sito".
#
# FONTE UFFICIALE (docs.developer.betfair.com, "Betting Type Definitions" ->
# ClearedOrderSummary, e "listClearedOrders - Roll-up Fields Available"):
#   * profit: "The profit or loss (negative profit) gained on this line, in
#     the account currency". Nella tabella dei roll-up e' sommato (SUM) a ogni
#     livello e la doc non lo dice MAI "net of commission": e' il LORDO;
#   * commission: "The cumulative amount of commission paid by the customer
#     across all bets under this Item, in the account currency. Available at
#     EXCHANGE, EVENT_TYPE, EVENT and MARKET level groupings only" (roll-up:
#     Commission = N a livello BET e SIDE, Y a livello MARKET).
# Quindi il NETTO reale di un mercato e' profit(MARKET) - commission(MARKET).
# Il netto di UN ordine e' il suo profit(BET) meno la sua QUOTA della
# commissione del mercato: Betfair la applica sulle vincite nette del MERCATO,
# non ordine per ordine. La quota e' in proporzione ai profit POSITIVI degli
# ordini di quel mercato (chi ha vinto paga), arrotondata al centesimo con il
# residuo sull'ultimo ordine in utile: la somma resta ESATTA.
#
# CHI E' DI CHI (nota del coordinatore, 24/09): un ordine regolato e' di una
# NOSTRA riga se una delle 5 tabelle ha una riga LIVE con quel ``bet_id``
# (omega_trades, safe_strategy_trades, mike_trades, tennis_live_orders,
# betfair_live_orders); in subordine se il suo ``customerOrderRef`` e'
# ``omega-t<id>``/``safe-t<id>``/``mike-t<id>`` e quella riga esiste. MAI per
# ``customerStrategyRef``: oggi Safe piazza con il ref di strategia di Omega.
# Senza una nostra riga l'ordine e' "manuale sito". Eccezione dichiarata: una
# riga di ``betfair_live_orders`` con ``source='account'`` e' la COPIA che la
# riconciliazione scrive per un ordine trovato sul conto e mai piazzato da noi
# (``_account_order_row``): e' proprio il sito, non conta come nostra.
#
# UN SOLO PUNTO DI SCRITTURA: questo giro, dentro il ciclo del saldo gia'
# esistente (``run_account_sync_if_due``). Nessun processo nuovo. Il paper
# non passa MAI di qui (il conto e' reale; nelle tabelle si toccano solo le
# righe ``mode='live'``).
#
# CADENZA (le chiamate REST possono solo diminuire, regola del 13/09):
#   * la lettura per MERCATO (una chiamata) gira: dopo un cambio di saldo
#     (segnale di una regolazione, mai due volte in 20 s) e comunque ogni 5
#     minuti come rete; riusa quella che ``_sync_cleared`` ha appena fatto
#     (``_MERCATI_CACHE``: 35 s per il giro di rete, 5 s per il forzato);
#   * la lettura per ORDINE (una chiamata, paginata) SOLO se la firma dei
#     mercati regolati e' cambiata (un mercato nuovo, un profit o una
#     commissione diversi): a mercati invariati non parte.
# Prima (18/09): una lettura per ORDINE ogni 60 s + una a ogni cambio di saldo.
# ---------------------------------------------------------------------------
_MANUAL_PNL_INTERVAL_SEC = 300.0
_LAST_MANUAL_PNL_TS = 0.0
_LAST_MANUAL_PNL_SIG: Optional[Tuple] = None
# la firma dei mercati regolati dell'ultimo giro COMPLETO (tutte le scritture
# riuscite): uguale -> niente lettura per ordine
_LAST_MERCATI_SIG: Optional[Tuple] = None
_LAST_PNL_REALE_SIG: Optional[Tuple] = None
# cache della lettura per MERCATO: monotonic, giorno, gruppi
_MERCATI_CACHE: Dict[str, Any] = {"ts": None, "day": None, "gruppi": []}
_MERCATI_CACHE_REGOLARE_SEC = 35.0
_MERCATI_CACHE_FORZATO_SEC = 5.0
# fra due giri FORZATI (cambio di saldo) almeno questo
_MANUAL_PNL_MIN_FORZATO_SEC = 20.0
# segnale "il saldo e' cambiato" arrivato da una lettura fatta altrove
# (``annota_lettura_esterna``): il prossimo giro del saldo forza i regolati
_REGOLATI_DA_RILEGGERE = False
# proprietario di un bet_id gia' risolto in questo processo:
# bet_id -> (tabella, id riga, extra) oppure None = nessuna nostra riga
_PROPRIETARIO_BET: Dict[str, Optional[Tuple[str, Any, Dict[str, Any]]]] = {}
_PROPRIETARIO_DAY: Optional[str] = None
# firma dell'ultima scrittura per riga: (tabella, id) -> (netto, commissione, settled)
_FIRMA_RIGA: Dict[Tuple[str, str], Tuple] = {}

# Censimento 18/09 (vedi ``_classify_cleared_order``): i ref di strategia del
# terminale manuale della nostra app. Restano per la classificazione STORICA
# (diagnostico, test); l'attribuzione di oggi e' per riga (sopra).
_MANUAL_APP_STRATEGY_REFS = frozenset({"live", "tennis"})
_OUR_ORDER_REF_PREFIXES = ("omega-", "safe-t", "mike-t")

# tabelle in ordine di precedenza: un ordine di Omega/Safe passa ANCHE dalla
# coda del runner (``betfair_live_orders``), ma e' del bot.
_TABELLE_BOT = ("omega_trades", "safe_strategy_trades", "mike_trades")
_TABELLE_SPECCHIO = ("tennis_live_orders", "betfair_live_orders")
_TABELLA_DEL_PREFISSO = {"omega": "omega_trades", "safe": "safe_strategy_trades",
                         "mike": "mike_trades"}
_RE_REF_RIGA = re.compile(r"^(omega|safe|mike)-t(\d+)$")
_BLOCCO_IN = 100  # bet_id per lettura (lunghezza dell'URL PostgREST)

#: le voci della composizione, nello stesso vocabolario del frontend
#: (``frontend/src/lib/composizioneObiettivo.ts``)
FONTI = ("omega", "safe_calcio", "safe_tennis", "mike", "bot_tennis",
         "manuale_app", "manuale_sito", "altri_bot")


def _classify_cleared_order(order: Any) -> str:
    """'ours' | 'manual_app' | 'manual' | 'ambiguous' - classificazione
    STORICA per ref (18/09), invariata. 24/09: NON decide piu' a chi va il
    P&L (lo decide la riga con quel bet_id, vedi ``_proprietari``): resta
    come diagnostico, perche' ``customerStrategyRef`` oggi mente per Safe."""
    sref = low._val(order, "customer_strategy_ref")
    oref = low._val(order, "customer_order_ref")
    sref_s = str(sref).strip() if sref else ""
    oref_s = str(oref).strip() if oref else ""
    if sref_s.lower() in _MANUAL_APP_STRATEGY_REFS:
        return "manual_app"
    if sref_s:
        return "ours"
    if oref_s.startswith(_OUR_ORDER_REF_PREFIXES):
        return "ours"
    if not sref_s and not oref_s:
        return "manual"
    return "ambiguous"


def _fetch_cleared_orders_today(session: Any) -> List[Any]:
    """``listClearedOrders`` di OGGI (giorno Rome), livello ORDINE (nessun
    groupBy): l'unico che porta betId/customerOrderRef/eventTypeId per
    singolo ordine. SENZA filtro di strategy ref (tutto il conto). Paginato."""
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


def _leggi_mercati_regolati(session: Any, *, max_eta_s: float) -> List[Any]:
    """I mercati regolati di oggi (livello MERCATO), dalla cache se piu'
    giovane di ``max_eta_s`` e dello stesso giorno, altrimenti UNA lettura
    REST. Solleva se la lettura fallisce (il chiamante decide)."""
    day = _now_local().strftime("%Y-%m-%d")
    ts = _MERCATI_CACHE.get("ts")
    if (ts is not None and _MERCATI_CACHE.get("day") == day
            and (time.monotonic() - float(ts)) <= max_eta_s):
        return list(_MERCATI_CACHE.get("gruppi") or [])
    gruppi = _fetch_cleared_markets_today(session)
    _MERCATI_CACHE["ts"] = time.monotonic()
    _MERCATI_CACHE["day"] = day
    _MERCATI_CACHE["gruppi"] = list(gruppi)
    return gruppi


def _firma_mercati(gruppi: List[Any]) -> Tuple:
    out = []
    for g in gruppi:
        mid = low._val(g, "market_id")
        if mid is None:
            continue
        p = low._f(low._val(g, "profit"))
        c = low._f(low._val(g, "commission"))
        out.append((str(mid), None if p is None else round(p, 2),
                    low._int(low._val(g, "bet_count")) or 0,
                    None if c is None else round(c, 2)))
    return tuple(sorted(out, key=repr))


def commissioni_per_ordine(ordini: List[Any], gruppi: List[Any]) -> Dict[str, Optional[float]]:
    """bet_id -> quota della commissione del SUO mercato (None = commissione
    del mercato non leggibile: quell'ordine non ha un netto reale).

    Funzione PURA. La commissione e' quella di ``listClearedOrders``
    raggruppato per MERCATO (``commission``); ripartita sui profit POSITIVI
    degli ordini di quel mercato, somma esatta al centesimo."""
    comm_m: Dict[str, Optional[float]] = {}
    for g in gruppi:
        mid = low._val(g, "market_id")
        if mid is None:
            continue
        comm_m[str(mid)] = low._f(low._val(g, "commission"))
    per_mercato: Dict[str, List[Tuple[str, float]]] = {}
    for o in ordini:
        bet = low._val(o, "bet_id")
        profit = low._f(low._val(o, "profit"))
        if bet is None or profit is None:
            continue
        per_mercato.setdefault(str(low._val(o, "market_id")), []).append((str(bet), profit))
    out: Dict[str, Optional[float]] = {}
    for mid, bets in per_mercato.items():
        c = comm_m.get(mid)
        if c is None:
            for bet, _p in bets:
                out[bet] = None
            continue
        c = round(max(0.0, c), 2)
        positivi = [(b, p) for b, p in bets if p > 0]
        tot_pos = sum(p for _b, p in positivi)
        for bet, _p in bets:
            out[bet] = 0.0
        if c <= 0:
            continue
        if tot_pos <= 0:
            # commissione senza ordini in utile (non dovrebbe esistere): tutta
            # sul primo ordine, la somma resta esatta e il caso non si perde
            out[bets[0][0]] = c
            continue
        assegnata = 0.0
        for i, (bet, p) in enumerate(positivi):
            if i == len(positivi) - 1:
                q = round(c - assegnata, 2)
            else:
                q = round(c * p / tot_pos, 2)
                assegnata = round(assegnata + q, 2)
            out[bet] = q
    return out


def _chiave_ref(order: Any) -> Optional[Tuple[str, str]]:
    """(tabella, id) dal ``customerOrderRef`` ``<bot>-t<id>``, o None."""
    oref = low._val(order, "customer_order_ref")
    m = _RE_REF_RIGA.match(str(oref).strip()) if oref else None
    if not m:
        return None
    return _TABELLA_DEL_PREFISSO[m.group(1)], m.group(2)


def _fonte_di(tabella: str, extra: Dict[str, Any], order: Any) -> str:
    """La voce della composizione per un ordine GIA' attribuito a una riga.
    Lo sport viene da ``eventTypeId`` dell'ordine (2 = tennis), mai dal ref."""
    tennis = str(low._val(order, "event_type_id") or "") == "2"
    if tabella == "omega_trades":
        return "omega"
    if tabella == "safe_strategy_trades":
        return "safe_tennis" if tennis else "safe_calcio"
    if tabella == "mike_trades":
        return "mike"
    src = str(extra.get("source") or "").strip().lower()
    if tabella == "tennis_live_orders":
        return "manuale_app" if src in ("", "manual") else "bot_tennis"
    # betfair_live_orders: 'runner' = terminale manuale dell'app;
    # 'bot:<ref>' = ordine di un bot visto sul conto
    if src.startswith("bot:"):
        return "bot_tennis" if tennis else "altri_bot"
    return "manuale_app"


def _client_db() -> Any:
    """Il client Supabase del processo (punto unico, sostituibile nei test)."""
    from db_client import get_supabase_client

    return get_supabase_client()


def _proprietari(sb: Any, ordini: List[Any], day: str) -> None:
    """Risolve (e ricorda) a quale NOSTRA riga appartiene ogni ordine non
    ancora risolto in questo processo. Letture SOLO per i bet_id nuovi, a
    blocchi, una per tabella (+ una per i ref ``<bot>-t<id>`` rimasti
    orfani). Solleva se una lettura fallisce: il giro si ferma senza scrivere
    e riprova al prossimo (mai un "manuale sito" dedotto da una lettura KO)."""
    global _PROPRIETARIO_DAY
    if _PROPRIETARIO_DAY != day:
        _PROPRIETARIO_BET.clear()
        _PROPRIETARIO_DAY = day
    nuovi = [o for o in ordini
             if low._val(o, "bet_id") is not None
             and str(low._val(o, "bet_id")) not in _PROPRIETARIO_BET]
    if not nuovi:
        return
    ids = sorted({str(low._val(o, "bet_id")) for o in nuovi})
    trovati: Dict[str, Tuple[str, Any, Dict[str, Any]]] = {}
    for tabella in _TABELLE_BOT + _TABELLE_SPECCHIO:
        colonne = "id,bet_id" if tabella in _TABELLE_BOT else "id,bet_id,source"
        for i in range(0, len(ids), _BLOCCO_IN):
            blocco = [b for b in ids[i:i + _BLOCCO_IN] if b not in trovati]
            if not blocco:
                continue
            res = (sb.table(tabella).select(colonne)
                   .eq("mode", "live").in_("bet_id", blocco).execute())
            for r in getattr(res, "data", None) or []:
                b = str(r.get("bet_id"))
                if b in trovati:
                    continue
                if tabella == "betfair_live_orders" and \
                        str(r.get("source") or "").strip().lower() == "account":
                    continue  # copia di un ordine del SITO, non nostra
                trovati[b] = (tabella, r.get("id"), {"source": r.get("source")})
    # in subordine: customerOrderRef <bot>-t<id>, se quella riga esiste
    per_tabella: Dict[str, Dict[str, List[str]]] = {}
    for o in nuovi:
        b = str(low._val(o, "bet_id"))
        if b in trovati:
            continue
        k = _chiave_ref(o)
        if k is not None:
            per_tabella.setdefault(k[0], {}).setdefault(k[1], []).append(b)
    for tabella, per_id in per_tabella.items():
        res = (sb.table(tabella).select("id")
               .eq("mode", "live").in_("id", sorted(per_id)).execute())
        for r in getattr(res, "data", None) or []:
            for b in per_id.get(str(r.get("id")), []):
                trovati[b] = (tabella, r.get("id"), {"via_ref": True})
    for b in ids:
        _PROPRIETARIO_BET[b] = trovati.get(b)


def componi_regolati(ordini: List[Any], gruppi: List[Any],
                     proprietari: Dict[str, Optional[Tuple[str, Any, Dict[str, Any]]]],
                     day: str) -> Tuple[Dict[str, Any], Dict[Tuple[str, str], Dict[str, Any]]]:
    """Funzione PURA: (totali del conto di oggi, P&L reale per riga).

    Totali: netto/lordo/commissione dell'intero conto e per voce (``FONTI``),
    gli ordini contati, i bet_id regolati (la pagina non li conta anche come
    stimati), quanti ordini non hanno un netto (commissione del mercato
    illeggibile: NON entrano nei totali reali, restano stimati)."""
    comm = commissioni_per_ordine(ordini, gruppi)
    per_fonte: Dict[str, Dict[str, Any]] = {
        f: {"netto": 0.0, "lordo": 0.0, "ordini": 0, "senza_commissione": 0} for f in FONTI}
    tot_netto = tot_lordo = tot_comm = 0.0
    n = senza = sospetti = 0
    bet_ids: List[str] = []
    righe: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for o in ordini:
        bet = low._val(o, "bet_id")
        profit = low._f(low._val(o, "profit"))
        if bet is None or profit is None:
            continue
        bet = str(bet)
        prop = proprietari.get(bet)
        if prop is None:
            fonte = "manuale_sito"
            if _chiave_ref(o) is not None or low._val(o, "customer_strategy_ref"):
                sospetti += 1  # porta un ref ma nessuna nostra riga: dichiarato
        else:
            fonte = _fonte_di(prop[0], prop[2], o)
        c = comm.get(bet)
        pf = per_fonte[fonte]
        pf["lordo"] += profit
        if c is None:
            senza += 1
            pf["senza_commissione"] += 1
            continue
        netto = round(profit - c, 2)
        n += 1
        tot_netto += netto
        tot_lordo += profit
        tot_comm += c
        pf["netto"] += netto
        pf["ordini"] += 1
        bet_ids.append(bet)
        if prop is not None:
            k = (prop[0], str(prop[1]))
            acc = righe.setdefault(k, {"netto": 0.0, "commissione": 0.0,
                                       "settled_at": None, "bet_ids": []})
            acc["netto"] = round(acc["netto"] + netto, 2)
            acc["commissione"] = round(acc["commissione"] + c, 2)
            acc["bet_ids"].append(bet)
            sd = _dt_iso(low._val(o, "settled_date"))
            if sd and (acc["settled_at"] is None or sd > acc["settled_at"]):
                acc["settled_at"] = sd
    for pf in per_fonte.values():
        pf["netto"] = round(pf["netto"], 2)
        pf["lordo"] = round(pf["lordo"], 2)
    totali = {
        "day": day,
        "netto": round(tot_netto, 2),
        "lordo": round(tot_lordo, 2),
        "commissione": round(tot_comm, 2),
        "ordini": n,
        "senza_commissione": senza,
        "sospetti_sito": sospetti,
        "per_fonte": per_fonte,
        "bet_ids": sorted(bet_ids),
    }
    return totali, righe


def _scrivi_righe(righe: Dict[Tuple[str, str], Dict[str, Any]]) -> bool:
    """P&L reale ACCANTO a quello calcolato (``pnl`` non si tocca), sulle
    righe LIVE, write-on-change. Ritorna False se almeno una scrittura e'
    fallita (il giro verra' rifatto). Una tabella che rifiuta una scrittura
    (migrazione non applicata) non riceve le altre in questo giro."""
    from . import db

    ok = True
    tabelle_ko: set = set()
    for (tabella, rid), v in sorted(righe.items()):
        if tabella in tabelle_ko:
            ok = False
            continue
        firma = (v["netto"], v["commissione"], v["settled_at"])
        if _FIRMA_RIGA.get((tabella, rid)) == firma:
            continue
        try:
            db.update_pnl_betfair(tabella, rid, {
                "pnl_betfair": v["netto"],
                "commissione_betfair": v["commissione"],
                "pnl_betfair_settled_at": v["settled_at"],
            })
            _FIRMA_RIGA[(tabella, rid)] = firma
        except Exception as ex:  # noqa: BLE001 - riprova al prossimo giro
            ok = False
            tabelle_ko.add(tabella)
            logger.warning("[reconcile] P&L reale su %s id %s KO (migrazione "
                           "pnl_betfair_reale_2026-09-24.sql applicata?): %s",
                           tabella, rid, str(ex)[:200])
    return ok


def _sync_manual_pnl(session: Any, *, max_eta_s: float = _MERCATI_CACHE_FORZATO_SEC) -> None:
    """IL GIRO DEI REGOLATI DI OGGI (nome storico: nato per il solo manuale).

    1. mercati regolati di oggi (cache o UNA lettura REST per MERCATO);
    2. firma invariata rispetto all'ultimo giro completo -> fine (nessuna
       altra chiamata, nessuna scrittura);
    3. altrimenti ordini regolati di oggi (UNA lettura REST per ORDINE),
       proprietari per bet_id (letture DB solo per i bet_id nuovi), P&L reale
       sulle righe, totali del conto (``betfair_live_account.pnl_reale_oggi``)
       e i due totali manuali di sempre (``manual_pnl_*``/``manual_app_pnl_*``,
       ora NETTI con la commissione del mercato), pubblicati sul canale.

    MONEY-CRITICAL: un KO (REST o DB) non tocca MAI i valori gia' scritti e
    non fa avanzare la firma: si ritenta. Non solleva MAI. Mai in paper."""
    global _LAST_MANUAL_PNL_SIG, _LAST_MERCATI_SIG, _LAST_PNL_REALE_SIG
    day = _now_local().strftime("%Y-%m-%d")
    try:
        gruppi = _leggi_mercati_regolati(session, max_eta_s=max_eta_s)
    except Exception as ex:  # noqa: BLE001 - REST KO: i totali restano quelli di prima
        logger.warning("[reconcile] listClearedOrders per mercato KO: %s", str(ex)[:200])
        return
    firma_mercati = (day, _firma_mercati(gruppi))
    if firma_mercati == _LAST_MERCATI_SIG:
        return
    try:
        orders = _fetch_cleared_orders_today(session)
    except Exception as ex:  # noqa: BLE001 - REST KO: i totali restano quelli di prima
        logger.warning("[reconcile] listClearedOrders (ordini) KO: %s", str(ex)[:200])
        return
    try:
        _proprietari(_client_db(), orders, day)
    except Exception as ex:  # noqa: BLE001 - DB KO: mai un "sito" dedotto da un guasto
        logger.warning("[reconcile] lettura dei proprietari KO: %s", str(ex)[:200])
        return
    totali, righe = componi_regolati(orders, gruppi, dict(_PROPRIETARIO_BET), day)
    completo = _scrivi_righe(righe)

    def _bucket(pf: Dict[str, Any]) -> Tuple[float, bool, int]:
        # NETTO solo se la commissione del mercato era leggibile per TUTTI gli
        # ordini del bucket; altrimenti LORDO dichiarato (mai finto netto)
        n_tot = pf["ordini"] + pf["senza_commissione"]
        netto = pf["senza_commissione"] == 0 and n_tot > 0
        return (pf["netto"] if netto else pf["lordo"]), netto, n_tot

    pnl_value, is_net, n_manual = _bucket(totali["per_fonte"]["manuale_sito"])
    app_pnl_value, app_is_net, n_app = _bucket(totali["per_fonte"]["manuale_app"])
    manual_sig = (pnl_value, is_net, n_manual, 0, day, app_pnl_value, app_is_net, n_app)
    from . import db

    if manual_sig != _LAST_MANUAL_PNL_SIG:
        try:
            # ``excluded`` = 0: dal 24/09 non esistono piu' ordini "ambigui"
            # (o c'e' una nostra riga con quel bet_id, o e' il sito); gli
            # ordini con un ref ma senza riga sono in ``pnl_reale_oggi.
            # sospetti_sito`` (dentro il totale del sito, dichiarati)
            db.upsert_live_account_manual_pnl(
                pnl_eur=pnl_value, is_net=is_net, orders=n_manual, excluded=0, day=day,
                app_pnl_eur=app_pnl_value, app_is_net=app_is_net, app_orders=n_app,
            )
            _LAST_MANUAL_PNL_SIG = manual_sig
        except Exception as ex:  # noqa: BLE001 - migrazione non applicata o DB KO
            completo = False
            logger.warning(
                "[reconcile] upsert manuale KO (migrazione betfair_live_account_manual_pnl.sql "
                "applicata?): %s", str(ex)[:200],
            )
    letto_at = datetime.now(timezone.utc).isoformat()
    reale = dict(totali, letto_at=letto_at)
    reale_sig = (day, totali["netto"], totali["ordini"], totali["senza_commissione"],
                 tuple(totali["bet_ids"]),
                 tuple((f, v["netto"], v["ordini"]) for f, v in sorted(totali["per_fonte"].items())))
    if reale_sig != _LAST_PNL_REALE_SIG:
        try:
            db.upsert_live_account_pnl_reale(reale)
            _LAST_PNL_REALE_SIG = reale_sig
        except Exception as ex:  # noqa: BLE001 - migrazione non applicata o DB KO
            completo = False
            logger.warning(
                "[reconcile] upsert pnl_reale_oggi KO (migrazione "
                "pnl_betfair_reale_2026-09-24.sql applicata?): %s", str(ex)[:200],
            )
    if completo:
        _LAST_MERCATI_SIG = firma_mercati
    # canale locale (topic 'account', zero costo DB): i due manuali di sempre
    # + il P&L reale del conto, a ogni giro che ha letto gli ordini.
    try:
        from . import local_channel as _lc

        _lc.publish(
            "account",
            {
                "manual_pnl_eur": pnl_value,
                "manual_pnl_is_net": is_net,
                "manual_pnl_orders": n_manual,
                "manual_pnl_excluded": 0,
                "manual_pnl_day": day,
                "manual_app_pnl_eur": app_pnl_value,
                "manual_app_pnl_is_net": app_is_net,
                "manual_app_pnl_orders": n_app,
                "pnl_reale_oggi": reale,
                "checked_at": letto_at,
            },
        )
    except Exception:  # noqa: BLE001 - canale opzionale, mai bloccare il dato
        pass


def _run_manual_pnl_if_due(session: Any, *, force: bool = False) -> None:
    """Rete ogni 5 minuti + giro forzato dopo un cambio di saldo (segnale di
    una regolazione), mai due forzati a meno di 20 s. Non solleva MAI."""
    global _LAST_MANUAL_PNL_TS
    now_mono = time.monotonic()
    trascorso = now_mono - _LAST_MANUAL_PNL_TS
    regolare = trascorso >= _MANUAL_PNL_INTERVAL_SEC
    if not regolare and not (force and trascorso >= _MANUAL_PNL_MIN_FORZATO_SEC):
        return
    _LAST_MANUAL_PNL_TS = now_mono
    try:
        _sync_manual_pnl(session, max_eta_s=(_MERCATI_CACHE_FORZATO_SEC if force
                                             else _MERCATI_CACHE_REGOLARE_SEC))
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
