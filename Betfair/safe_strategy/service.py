"""service.py — SCANNER AUTONOMO Safe Strategy (calcio + tennis in-play).

Monitora TUTTI gli eventi live del momento (nessuna iscrizione manuale):
  · catalogo MATCH_ODDS per sport su finestra MOBILE (KO da -6h a +14h,
    refresh 300s, peso ~0, fino a 400 mercati/sport: mai tagliare le giornate
    piene);
  · quote MATCH_ODDS dei soli mercati RILEVANTI (in-play, o KO entro 20′):
    Exchange Stream API ufficiale (push, conflate 1s, cap 180 mercati con
    priorità in-play) + poll REST EX_BEST_OFFERS (chunk 25 → peso 125 < 200)
    come FALLBACK per i mercati che lo stream non copre o quando lo stream
    non è in salute — cadenza ADATTIVA 10s (2°T calcio dal 40′ in poi /
    tennis in-play), 20-60s altrimenti;
  · punteggi/minuti/rossi per TUTTI gli in-play in UNA chiamata IPS get_scores
    (chunk 20 id) ogni 5s — stesso endpoint già usato dai runner;
  · Correct Score SOLO per i candidati Risultato Esatto (dal 40′ in poi,
    max 2 gol per lato — il minuto è una SOGLIA, come nella strategia):
    catalogo dedicato appena compare un candidato nuovo + book ogni 15s;
  · riferimento 1X2 pre-KO: aggiornato da KO-15′ e CONGELATO al primo tick
    in-play (mai quote live nel riferimento — regola di certificazione).

Scrive i FATTI su safe_strategy_scan (write-on-change) + heartbeat su
safe_strategy_status. La VALUTAZIONE resta nel motore certificato frontend.
Nessun ordine, mai.

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
from .stream import MarketStreamWorker

logger = logging.getLogger("safe_strategy")

_LOCK_PORT = int(os.getenv("SAFE_STRATEGY_LOCK_PORT", "47315"))
_CATALOGUE_TTL_SEC = 300.0
# catalogo Correct Score: la chiamata parte SOLO se c'è un candidato senza
# mercato in cache (refresh_cs_catalogue esce subito altrimenti), quindi il
# throttle può essere corto: un candidato nuovo al 48′ ha la quota entro ~20s
# (prima il TTL era 600s → segnale R.E. in ritardo fino a 10 minuti)
_CS_CATALOGUE_MIN_INTERVAL_SEC = 20.0
_SCORES_PERIOD_SEC = 5.0    # IPS non ha stream: poll batch fitto (1-2 chiamate)
_CS_BOOKS_PERIOD_SEC = 15.0
# throttle di scrittura per-evento: con lo STREAM le quote cambiano ogni secondo
# (conflate 1s) — mai inondare Supabase: max 1 riga/evento ogni 2.5s (e comunque
# solo write-on-change).
_PUBLISH_MIN_INTERVAL_SEC = 2.5
_STATUS_PERIOD_SEC = 10.0
_KEEPALIVE_PERIOD_SEC = 900.0
_BOOK_CHUNK = 25          # peso EX_BEST_OFFERS 5/mercato → 125 < 200
_SCORES_CHUNK = 20
_REQ_DELAY = 0.35         # respiro tra chiamate REST (anti-throttling)
# cap catalogo per sport: le proiezioni usate pesano 0 (EVENT, COMPETITION,
# MARKET_START_TIME, RUNNER_DESCRIPTION) → nessun vincolo di peso; 400 copre
# anche il sabato pieno (col vecchio 120 + sort FIRST_TO_START gli eventi serali
# restavano FUORI dal radar finché quelli del pomeriggio non chiudevano)
_MAX_MARKETS = 400
# finestra catalogo MOBILE: in-play iniziati fino a 6h fa + KO nelle prossime
# 14h (la vecchia finestra "fino a mezzanotte UTC" perdeva i notturni)
_CATALOGUE_PAST_H = 6
_CATALOGUE_AHEAD_H = 14

_SPORTS = {"calcio": "1", "tennis": "2"}


def _catalogue_window_iso() -> "tuple[str, str]":
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=_CATALOGUE_PAST_H)
    end = now + timedelta(hours=_CATALOGUE_AHEAD_H)
    return start.isoformat(), end.isoformat()


class SportState:
    def __init__(self) -> None:
        self.catalogue_ts = 0.0
        self.books_ts = 0.0
        # meta per evento: market_id, event_name, open_date, competition, sides
        self.metas: Dict[str, Dict[str, Any]] = {}


class Scanner:
    def __init__(self, api_client: Any, dry: bool, use_stream: bool = False) -> None:
        self.client = api_client
        self.dry = dry
        self.sports = {name: SportState() for name in _SPORTS}
        # stato runtime per evento (inplay, quote, punteggio, pre_ko, cs, …)
        self.events: Dict[str, Dict[str, Any]] = {}
        # QUOTE IN TEMPO REALE: Exchange Stream API ufficiale (push, conflate 1s);
        # il poll REST resta come fallback quando lo stream non è in salute.
        self.stream: Optional[MarketStreamWorker] = (
            MarketStreamWorker(api_client) if use_stream else None
        )
        # indice market_id → (sport, meta) per applicare i book (stream E rest)
        self.market_meta: Dict[str, "tuple[str, Dict[str, Any]]"] = {}
        # throttle di pubblicazione per-evento
        self.last_pub_mono: Dict[str, float] = {}
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
        frm, to = _catalogue_window_iso()
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
        self._rebuild_market_index()
        logger.info("[safe-scan] catalogo %s: %d eventi oggi", sport, len(metas))

    def _rebuild_market_index(self) -> None:
        """Indice market_id → (sport, meta) su tutto il catalogo."""
        idx: Dict[str, "tuple[str, Dict[str, Any]]"] = {}
        for sport, st in self.sports.items():
            for meta in st.metas.values():
                idx[meta["market_id"]] = (sport, meta)
        self.market_meta = idx

    def relevant_market_ids(self, sport: str, now: datetime) -> List[str]:
        """Mercati del sport che servono QUOTE adesso (scanner.is_relevant_market),
        ordinati per priorità (in-play prima, poi per KO). Il resto del catalogo
        (KO lontano) non consuma né stream né REST."""
        out: List["tuple[tuple[int, str], str]"] = []
        for eid, meta in self.sports[sport].metas.items():
            ev = self.events.get(eid)
            inplay: Optional[bool] = None if ev is None else bool(ev.get("inplay"))
            status = None if ev is None else ev.get("mo_status")
            if scanner.is_relevant_market(inplay, status, meta.get("open_date"), now):
                out.append((scanner.rank_key(inplay, meta.get("open_date")), meta["market_id"]))
        out.sort()
        return [mid for _, mid in out]

    def refresh_stream_set(self, now: datetime) -> None:
        """Subscription stream = mercati rilevanti di TUTTI gli sport insieme.

        Parte SOLO quando tutti gli sport hanno un catalogo caricato (warm-up in
        main): senza questa guardia lo stream partiva col solo calcio e il
        throttle anti-resubscribe teneva fuori il tennis per minuti (visto in
        collaudo). Va chiamata a ogni tick: il set cambia quando un evento va
        in-play, entra in finestra pre-KO o chiude — non solo al refresh catalogo.
        """
        if self.stream is None:
            return
        if not all(st.catalogue_ts > 0.0 for st in self.sports.values()):
            return
        ranked: List["tuple[tuple[int, str], str]"] = []
        for sport in self.sports:
            for mid in self.relevant_market_ids(sport, now):
                _, meta = self.market_meta[mid]
                ev = self.events.get(meta["event_id"])
                inplay = None if ev is None else bool(ev.get("inplay"))
                ranked.append((scanner.rank_key(inplay, meta.get("open_date")), mid))
        ranked.sort()
        ids = [mid for _, mid in ranked]
        if ids:
            self.stream.set_markets(ids)

    def _apply_market_book(self, book: Any) -> None:
        """Applica UN MarketBook (dal poll REST o dallo STREAM) allo stato evento."""
        found = self.market_meta.get(getattr(book, "market_id", None))
        if not found:
            return
        sport, meta = found
        pairs: Dict[int, Dict[str, Optional[float]]] = {}
        for r in getattr(book, "runners", None) or []:
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
        ev["inplay"] = bool(getattr(book, "inplay", False))
        ev["mo_status"] = getattr(book, "status", None)
        ev["odds"] = odds
        # riferimento pre-KO: aggiorna pre-KO, congela al primo in-play
        ev["pre_ko"] = scanner.freeze_pre_ko(
            ev.get("pre_ko"), ev["inplay"], odds if sport == "calcio" else None,
        )

    # ------------------------------------------------------------- quote MO (REST)
    def poll_books(self, sport: str, ids: List[str]) -> None:
        """Poll REST EX_BEST_OFFERS dei mercati indicati (chunk 25, peso 125)."""
        from betfairlightweight import filters

        st = self.sports[sport]
        for i in range(0, len(ids), _BOOK_CHUNK):
            chunk = ids[i:i + _BOOK_CHUNK]
            books = self.client.betting.list_market_book(
                market_ids=chunk,
                price_projection=filters.price_projection(price_data=["EX_BEST_OFFERS"]),
            )
            for b in books or []:
                self._apply_market_book(b)
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

        # cache solo per eventi ancora noti (memoria stabile nei run lunghi)
        for eid in [e for e in self.cs_markets if e not in self.events]:
            self.cs_markets.pop(eid, None)
        missing = [e for e in candidates if e not in self.cs_markets]
        if not missing:
            return  # nessuna chiamata: il throttle non parte
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
                # throttle per-evento: con lo stream le quote cambiano ogni secondo;
                # la riga aspetta il prossimo giro (sig NON consumata) — mai perdere
                # l'ultimo stato, mai inondare il DB
                mono = time.monotonic()
                if mono - self.last_pub_mono.get(eid, 0.0) < _PUBLISH_MIN_INTERVAL_SEC:
                    continue
                self.last_pub_mono[eid] = mono
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
                self.last_pub_mono.pop(eid, None)
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
            "source": getattr(self, "last_source", "rest"),
            # mercati coperti dallo stream (0 = REST puro): utile nei weekend
            # pieni per vedere se il cap 180 sta lasciando mercati al fallback
            "stream_markets": len(self.stream.subscribed_ids()) if self.stream else 0,
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
        return any(
            ev.get("sport") == "calcio"
            and ev.get("inplay")
            and scanner.is_hot_minute(ev.get("minute"))
            for ev in self.events.values()
        )

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

            # QUOTE: stream ufficiale (push, conflate 1s) sui mercati rilevanti;
            # poll REST come FALLBACK per i mercati rilevanti che lo stream non
            # copre (oltre il cap, o stream non in salute) — mai un buco dati.
            self.refresh_stream_set(now)
            if self.stream is not None:
                for b in self.stream.drain():
                    self._apply_market_book(b)
            stream_ok = self.stream is not None and self.stream.healthy()
            self.last_source = "stream" if stream_ok else "rest"
            covered = self.stream.subscribed_ids() if stream_ok else set()
            any_inplay_c = any(
                e.get("sport") == "calcio" and e.get("inplay") for e in self.events.values()
            )
            any_inplay_t = any(
                e.get("sport") == "tennis" and e.get("inplay") for e in self.events.values()
            )
            periods = {
                "calcio": scanner.books_period_calcio(any_inplay_c, self.any_hot_calcio()),
                "tennis": scanner.books_period_tennis(any_inplay_t),
            }
            for sport, period in periods.items():
                st = self.sports[sport]
                if now_mono - st.books_ts <= period:
                    continue
                uncovered = [
                    mid for mid in self.relevant_market_ids(sport, now) if mid not in covered
                ]
                if uncovered:
                    self.poll_books(sport, uncovered)
                else:
                    st.books_ts = now_mono

            if now_mono - self.scores_ts > _SCORES_PERIOD_SEC:
                self.poll_scores()

            candidates = self.cs_candidates()
            if candidates and now_mono - self.cs_catalogue_ts > _CS_CATALOGUE_MIN_INTERVAL_SEC:
                self.cs_catalogue_ts = now_mono
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
    # stream ufficiale SOLO nel run persistente (--once = collaudo REST puro)
    scan = Scanner(client, dry=args.dry, use_stream=not args.once)
    try:
        if args.once:
            # collaudo: un giro completo esplicito (senza il write-on-change del
            # tick, così le righe restano visibili nel log)
            now = datetime.now(timezone.utc)
            for sport in scan.sports:
                scan.refresh_catalogue(sport)
                time.sleep(_REQ_DELAY)
            for sport in scan.sports:
                ids = scan.relevant_market_ids(sport, now)
                logger.info(
                    "[safe-scan] %s: %d mercati a catalogo, %d rilevanti (in-play / KO entro 20′)",
                    sport, len(scan.sports[sport].metas), len(ids),
                )
                scan.poll_books(sport, ids)
            # secondo passaggio: gli in-play appena scoperti sono ora rilevanti
            for sport in scan.sports:
                ids = scan.relevant_market_ids(sport, now)
                scan.poll_books(sport, ids)
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
        # warm-up: ENTRAMBI i cataloghi prima del primo tick, così lo stream
        # nasce già con calcio+tennis insieme (vedi nota in _rebuild_market_index)
        for sport in scan.sports:
            try:
                scan.refresh_catalogue(sport)
            except Exception as e:  # noqa: BLE001 - il tick riproverà
                logger.warning("[safe-scan] warm-up catalogo %s KO: %s", sport, str(e)[:120])
            time.sleep(_REQ_DELAY)
        while True:
            scan.tick()
            time.sleep(0.5)
    finally:
        if scan.stream is not None:
            scan.stream.stop()
        safe_logout(client)
        if lock is not None:
            lock.close()


if __name__ == "__main__":
    main()
