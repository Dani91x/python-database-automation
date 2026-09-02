"""service.py — SCANNER AUTONOMO Safe Strategy (calcio + tennis in-play).

Monitora TUTTI gli eventi live del momento (nessuna iscrizione manuale):
  · catalogo MATCH_ODDS del giorno per sport (refresh 300s, peso ~0);
  · quote MATCH_ODDS a lotti EX_BEST_OFFERS (peso 5/mercato, chunk 25 → <200),
    cadenza ADATTIVA: 10s quando c'è una finestra utile (2°T calcio 40-78′ /
    tennis in-play), 20-60s altrimenti;
  · punteggi/minuti/rossi per TUTTI gli in-play in UNA chiamata IPS get_scores
    (chunk 20 id) ogni 10s — stesso endpoint già usato dai runner;
  · Correct Score SOLO per i candidati Risultato Esatto (minuto 40-60,
    max 2 gol per lato): catalogo dedicato + book, ogni 15s;
  · riferimento 1X2 pre-KO: aggiornato da KO-15′ e CONGELATO al primo tick
    in-play (mai quote live nel riferimento — regola di certificazione).

Scrive i FATTI su safe_strategy_scan (write-on-change) + heartbeat su
safe_strategy_status. La VALUTAZIONE resta nel motore certificato frontend.
Nessun ordine, nessuna subscription stream: solo REST leggero nei limiti.

Uso:  python -m Betfair.safe_strategy.service [--once] [--dry]
  --once  un ciclo completo e esce (collaudo)
  --dry   nessuna scrittura DB, stampa il riepilogo (collaudo senza migrazione)
"""
from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from Betfair.stream.auth import build_client, keep_alive, safe_logout
from Betfair.stream.scores.betfair_inplay import parse_score_dict
from Betfair.stream.single_instance import acquire_single_instance_lock
from Betfair.stream.tennis_scalper.tennis_score import parse_tennis_scores

from . import db as scan_db
from . import scanner

logger = logging.getLogger("safe_strategy")

_LOCK_PORT = int(os.getenv("SAFE_STRATEGY_LOCK_PORT", "47315"))
_CATALOGUE_TTL_SEC = 300.0
_CS_CATALOGUE_TTL_SEC = 600.0
_SCORES_PERIOD_SEC = 10.0
_CS_BOOKS_PERIOD_SEC = 15.0
_STATUS_PERIOD_SEC = 10.0
_KEEPALIVE_PERIOD_SEC = 900.0
_BOOK_CHUNK = 25          # peso EX_BEST_OFFERS 5/mercato → 125 < 200
_SCORES_CHUNK = 20
_REQ_DELAY = 0.35         # respiro tra chiamate REST (anti-throttling)
_MAX_MARKETS = 120        # cap difensivo catalogo per sport

_SPORTS = {"calcio": "1", "tennis": "2"}


def _today_window_iso() -> "tuple[str, str]":
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=8)
    end = now.replace(hour=23, minute=59, second=59)
    if end <= start:
        end = start + timedelta(hours=24)
    return start.isoformat(), end.isoformat()


class SportState:
    def __init__(self) -> None:
        self.catalogue_ts = 0.0
        self.books_ts = 0.0
        # meta per evento: market_id, event_name, open_date, competition, sides
        self.metas: Dict[str, Dict[str, Any]] = {}


class Scanner:
    def __init__(self, api_client: Any, dry: bool) -> None:
        self.client = api_client
        self.dry = dry
        self.sports = {name: SportState() for name in _SPORTS}
        # stato runtime per evento (inplay, quote, punteggio, pre_ko, cs, …)
        self.events: Dict[str, Dict[str, Any]] = {}
        self.scores_ts = 0.0
        self.cs_catalogue_ts = 0.0
        self.cs_books_ts = 0.0
        self.status_ts = 0.0
        self.keepalive_ts = time.monotonic()
        self.written_sig: Dict[str, str] = {}
        self.last_error: Optional[str] = None
        self.started_at = scanner.now_iso()
        # cache mercati Correct Score: event_id → {market_id, runners}
        self.cs_markets: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------- catalogo MO
    def refresh_catalogue(self, sport: str) -> None:
        from betfairlightweight import filters

        st = self.sports[sport]
        frm, to = _today_window_iso()
        cats = self.client.betting.list_market_catalogue(
            filter=filters.market_filter(
                event_type_ids=[_SPORTS[sport]],
                market_type_codes=["MATCH_ODDS"],
                market_start_time={"from": frm, "to": to},
            ),
            market_projection=[
                "EVENT", "COMPETITION", "MARKET_START_TIME", "RUNNER_DESCRIPTION",
            ],
            sort="FIRST_TO_START",
            max_results=_MAX_MARKETS,
        )
        metas: Dict[str, Dict[str, Any]] = {}
        for c in cats or []:
            event = getattr(c, "event", None)
            event_id = getattr(event, "id", None)
            market_id = getattr(c, "market_id", None)
            if not event_id or not market_id:
                continue
            runners = [
                {
                    "selection_id": getattr(r, "selection_id", None),
                    "name": getattr(r, "runner_name", None),
                    "sort_priority": getattr(r, "sort_priority", None),
                }
                for r in (getattr(c, "runners", None) or [])
            ]
            start = getattr(c, "market_start_time", None)
            comp = getattr(c, "competition", None)
            metas[str(event_id)] = {
                "event_id": str(event_id),
                "market_id": market_id,
                "event_name": getattr(event, "name", None),
                "open_date": start.isoformat() if hasattr(start, "isoformat") else start,
                "competition": getattr(comp, "name", None),
                "runners": runners,
                "sides": (
                    scanner.selection_sides(runners)
                    if sport == "calcio"
                    else scanner.tennis_sides(runners)
                ),
            }
        st.metas = metas
        st.catalogue_ts = time.monotonic()
        logger.info("[safe-scan] catalogo %s: %d eventi oggi", sport, len(metas))

    # ------------------------------------------------------------- quote MO
    def poll_books(self, sport: str) -> None:
        from betfairlightweight import filters

        st = self.sports[sport]
        by_market = {m["market_id"]: m for m in st.metas.values()}
        ids = list(by_market.keys())
        for i in range(0, len(ids), _BOOK_CHUNK):
            chunk = ids[i:i + _BOOK_CHUNK]
            books = self.client.betting.list_market_book(
                market_ids=chunk,
                price_projection=filters.price_projection(price_data=["EX_BEST_OFFERS"]),
            )
            for b in books or []:
                meta = by_market.get(getattr(b, "market_id", None))
                if meta is None:
                    continue
                pairs: Dict[int, Dict[str, Optional[float]]] = {}
                for r in getattr(b, "runners", None) or []:
                    ex = getattr(r, "ex", None)
                    sid = getattr(r, "selection_id", None)
                    if sid is None:
                        continue
                    pairs[int(sid)] = {
                        "back": scanner.best_price(getattr(ex, "available_to_back", None)) if ex else None,
                        "lay": scanner.best_price(getattr(ex, "available_to_lay", None)) if ex else None,
                    }
                sides = meta["sides"]
                odds = {
                    side: pairs.get(sid) if sid is not None else None
                    for side, sid in sides.items()
                }
                ev = self.events.setdefault(meta["event_id"], {})
                ev["sport"] = sport
                ev["inplay"] = bool(getattr(b, "inplay", False))
                ev["mo_status"] = getattr(b, "status", None)
                ev["odds"] = odds
                # riferimento pre-KO: aggiorna pre-KO, congela al primo in-play
                ev["pre_ko"] = scanner.freeze_pre_ko(
                    ev.get("pre_ko"), ev["inplay"], odds if sport == "calcio" else None,
                )
            time.sleep(_REQ_DELAY)
        st.books_ts = time.monotonic()

    # ------------------------------------------------------------- punteggi IPS
    def poll_scores(self) -> None:
        inplay_ids = [
            eid for eid, ev in self.events.items() if ev.get("inplay")
        ]
        if not inplay_ids:
            self.scores_ts = time.monotonic()
            return
        raw_by_event: Dict[str, Dict[str, Any]] = {}
        for i in range(0, len(inplay_ids), _SCORES_CHUNK):
            chunk = inplay_ids[i:i + _SCORES_CHUNK]
            try:
                results = self.client.in_play_service.get_scores(
                    event_ids=chunk, lightweight=True
                )
            except Exception as e:  # noqa: BLE001 - IPS non ufficiale: best-effort
                logger.warning("[safe-scan] get_scores KO: %s", str(e)[:120])
                continue
            for rec in results or []:
                if isinstance(rec, dict) and rec.get("eventId") is not None:
                    raw_by_event[str(rec["eventId"])] = rec
            time.sleep(_REQ_DELAY)
        for eid, rec in raw_by_event.items():
            ev = self.events.get(eid)
            if ev is None:
                continue
            if ev.get("sport") == "calcio":
                snap = parse_score_dict(eid, rec)
                ev["minute"] = snap.minute
                ev["score_home"] = snap.score_home
                ev["score_away"] = snap.score_away
                ev["red_home"] = snap.red_home
                ev["red_away"] = snap.red_away
            else:
                ts = parse_tennis_scores([rec], eid)
                if ts is not None:
                    ev["sets"] = (
                        {"p1": ts.sets_home, "p2": ts.sets_away}
                        if ts.sets_home is not None and ts.sets_away is not None
                        else None
                    )
                    ev["games"] = (
                        {"p1": ts.games_home, "p2": ts.games_away}
                        if ts.games_home is not None and ts.games_away is not None
                        else None
                    )
        self.scores_ts = time.monotonic()

    # ------------------------------------------------------------- Correct Score
    def cs_candidates(self) -> List[str]:
        out = []
        for eid, ev in self.events.items():
            if ev.get("sport") != "calcio" or not ev.get("inplay"):
                continue
            if scanner.is_cs_candidate(
                ev.get("minute"), ev.get("score_home"), ev.get("score_away")
            ):
                out.append(eid)
        return out

    def refresh_cs_catalogue(self, candidates: List[str]) -> None:
        from betfairlightweight import filters

        missing = [e for e in candidates if e not in self.cs_markets]
        if not missing:
            self.cs_catalogue_ts = time.monotonic()
            return
        cats = self.client.betting.list_market_catalogue(
            filter=filters.market_filter(
                event_ids=missing, market_type_codes=["CORRECT_SCORE"],
            ),
            market_projection=["EVENT", "RUNNER_DESCRIPTION"],
            max_results=50,
        )
        for c in cats or []:
            event_id = getattr(getattr(c, "event", None), "id", None)
            market_id = getattr(c, "market_id", None)
            if not event_id or not market_id:
                continue
            self.cs_markets[str(event_id)] = {
                "market_id": market_id,
                "names": {
                    getattr(r, "selection_id", None): getattr(r, "runner_name", None)
                    for r in (getattr(c, "runners", None) or [])
                },
            }
        self.cs_catalogue_ts = time.monotonic()

    def poll_cs_books(self, candidates: List[str]) -> None:
        from betfairlightweight import filters

        wanted = {
            self.cs_markets[e]["market_id"]: e
            for e in candidates
            if e in self.cs_markets
        }
        ids = list(wanted.keys())
        for i in range(0, len(ids), _BOOK_CHUNK):
            chunk = ids[i:i + _BOOK_CHUNK]
            books = self.client.betting.list_market_book(
                market_ids=chunk,
                price_projection=filters.price_projection(price_data=["EX_BEST_OFFERS"]),
            )
            for b in books or []:
                eid = wanted.get(getattr(b, "market_id", None))
                if eid is None:
                    continue
                names = self.cs_markets[eid]["names"]
                selections = []
                for r in getattr(b, "runners", None) or []:
                    ex = getattr(r, "ex", None)
                    selections.append({
                        "name": names.get(getattr(r, "selection_id", None)),
                        "back": scanner.best_price(getattr(ex, "available_to_back", None)) if ex else None,
                        "lay": scanner.best_price(getattr(ex, "available_to_lay", None)) if ex else None,
                    })
                ev = self.events.get(eid)
                if ev is not None:
                    ev["cs"] = scanner.build_cs_block(
                        getattr(b, "market_id", None), getattr(b, "status", None), selections,
                    )
            time.sleep(_REQ_DELAY)
        self.cs_books_ts = time.monotonic()

    # ------------------------------------------------------------- pubblicazione
    def build_rows(self, now: datetime) -> "tuple[List[Dict[str, Any]], List[str]]":
        rows: List[Dict[str, Any]] = []
        wanted: List[str] = []
        for sport, st in self.sports.items():
            for eid, meta in st.metas.items():
                ev = self.events.get(eid) or {}
                inplay = bool(ev.get("inplay"))
                if not scanner.is_monitorable(inplay, meta.get("open_date"), now):
                    continue
                if ev.get("mo_status") == "CLOSED":
                    continue  # partita finita: la riga verrà cancellata
                wanted.append(eid)
                if sport == "calcio":
                    home, away = scanner.split_event_name(meta.get("event_name"))
                    payload: Dict[str, Any] = {
                        "event_name": meta.get("event_name"),
                        "home": home,
                        "away": away,
                        "competition": meta.get("competition"),
                        "open_date": meta.get("open_date"),
                        "inplay": inplay,
                        "mo_market_id": meta.get("market_id"),
                        "mo_status": ev.get("mo_status"),
                        "odds": ev.get("odds"),
                        "minute": ev.get("minute"),
                        "score_home": ev.get("score_home"),
                        "score_away": ev.get("score_away"),
                        "red_home": ev.get("red_home"),
                        "red_away": ev.get("red_away"),
                        "pre_ko": ev.get("pre_ko"),
                        "cs": ev.get("cs"),
                    }
                else:
                    p1, p2 = scanner.split_event_name(meta.get("event_name"))
                    payload = {
                        "event_name": meta.get("event_name"),
                        "p1": p1,
                        "p2": p2,
                        "competition": meta.get("competition"),
                        "open_date": meta.get("open_date"),
                        "inplay": inplay,
                        "mo_market_id": meta.get("market_id"),
                        "mo_status": ev.get("mo_status"),
                        "odds": ev.get("odds"),
                        "sets": ev.get("sets"),
                        "games": ev.get("games"),
                    }
                sig = scanner.payload_signature(payload)
                if self.written_sig.get(eid) == sig:
                    continue  # write-on-change
                self.written_sig[eid] = sig
                rows.append({
                    "event_id": eid,
                    "sport": sport,
                    "payload": payload,
                    "updated_at": scanner.now_iso(),
                })
        return rows, wanted

    def publish(self, now: datetime) -> "tuple[int, int]":
        rows, wanted = self.build_rows(now)
        stale = [eid for eid in self.written_sig if eid not in set(wanted)]
        if self.dry:
            return len(rows), len(stale)
        if rows:
            scan_db.upsert_scan_rows(rows)
        if stale:
            scan_db.delete_scan_rows(stale)
            for eid in stale:
                self.written_sig.pop(eid, None)
        return len(rows), len(stale)

    def publish_status(self, monitored: int) -> None:
        payload = {
            "calcio_inplay": sum(
                1 for e in self.events.values() if e.get("sport") == "calcio" and e.get("inplay")
            ),
            "tennis_inplay": sum(
                1 for e in self.events.values() if e.get("sport") == "tennis" and e.get("inplay")
            ),
            "monitored": monitored,
            "dry": self.dry,
            "last_error": self.last_error,
            "started_at": self.started_at,
        }
        if self.dry:
            logger.info("[safe-scan] status: %s", payload)
        else:
            scan_db.upsert_status(payload)
        self.status_ts = time.monotonic()

    # ------------------------------------------------------------- ciclo
    def any_hot_calcio(self) -> bool:
        for ev in self.events.values():
            if ev.get("sport") != "calcio" or not ev.get("inplay"):
                continue
            m = ev.get("minute")
            if m is not None and scanner.HOT_MINUTE_FROM <= m <= scanner.HOT_MINUTE_TO:
                return True
        return False

    def tick(self) -> None:
        now_mono = time.monotonic()
        now = datetime.now(timezone.utc)
        try:
            if now_mono - self.keepalive_ts > _KEEPALIVE_PERIOD_SEC:
                keep_alive(self.client)
                self.keepalive_ts = now_mono

            for sport, st in self.sports.items():
                if now_mono - st.catalogue_ts > _CATALOGUE_TTL_SEC:
                    self.refresh_catalogue(sport)
                    time.sleep(_REQ_DELAY)
            # pruning: eventi non più nel catalogo del giorno → via dallo stato
            known = {
                eid for st in self.sports.values() for eid in st.metas
            }
            for eid in [e for e in self.events if e not in known]:
                self.events.pop(eid, None)

            any_inplay_c = any(
                e.get("sport") == "calcio" and e.get("inplay") for e in self.events.values()
            )
            any_inplay_t = any(
                e.get("sport") == "tennis" and e.get("inplay") for e in self.events.values()
            )
            per_c = scanner.books_period_calcio(any_inplay_c, self.any_hot_calcio())
            per_t = scanner.books_period_tennis(any_inplay_t)
            if now_mono - self.sports["calcio"].books_ts > per_c:
                self.poll_books("calcio")
            if now_mono - self.sports["tennis"].books_ts > per_t:
                self.poll_books("tennis")

            if now_mono - self.scores_ts > _SCORES_PERIOD_SEC:
                self.poll_scores()

            candidates = self.cs_candidates()
            if candidates and now_mono - self.cs_catalogue_ts > _CS_CATALOGUE_TTL_SEC:
                self.refresh_cs_catalogue(candidates)
            if candidates and now_mono - self.cs_books_ts > _CS_BOOKS_PERIOD_SEC:
                self.poll_cs_books(candidates)

            written, deleted = self.publish(now)
            if written or deleted:
                logger.info(
                    "[safe-scan] pubblicate %d righe, rimosse %d (monitorati %d)",
                    written, deleted, len(self.written_sig),
                )
            if now_mono - self.status_ts > _STATUS_PERIOD_SEC:
                self.publish_status(len(self.written_sig))
            self.last_error = None
        except Exception as e:  # noqa: BLE001 - lo scanner non muore mai per un giro storto
            self.last_error = f"{type(e).__name__}: {str(e)[:140]}"
            logger.warning("[safe-scan] ciclo KO: %s", self.last_error)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scanner Safe Strategy")
    parser.add_argument("--once", action="store_true", help="un ciclo e esce (collaudo)")
    parser.add_argument("--dry", action="store_true", help="nessuna scrittura DB")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    lock = None
    if not args.once:
        lock = acquire_single_instance_lock(_LOCK_PORT, "safe-strategy")

    client = build_client(login=True)
    scan = Scanner(client, dry=args.dry)
    try:
        if args.once:
            # collaudo: un giro completo esplicito (senza il write-on-change del
            # tick, così le righe restano visibili nel log)
            for sport in scan.sports:
                scan.refresh_catalogue(sport)
                time.sleep(_REQ_DELAY)
            scan.poll_books("calcio")
            scan.poll_books("tennis")
            scan.poll_scores()
            candidates = scan.cs_candidates()
            if candidates:
                scan.refresh_cs_catalogue(candidates)
                scan.poll_cs_books(candidates)
            rows, wanted = scan.build_rows(datetime.now(timezone.utc))
            logger.info(
                "[safe-scan] COLLAUDO: %d eventi monitorabili, %d candidati CS, %d righe",
                len(wanted), len(candidates), len(rows),
            )
            for r in rows[:8]:
                logger.info(
                    "[safe-scan]   %s %s → %s",
                    r["sport"], r["event_id"], str(r["payload"])[:240],
                )
            if not args.dry:
                if rows:
                    scan_db.upsert_scan_rows(rows)
                scan.publish_status(len(wanted))
            return
        while True:
            scan.tick()
            time.sleep(1.0)
    finally:
        safe_logout(client)
        if lock is not None:
            lock.close()


if __name__ == "__main__":
    main()
