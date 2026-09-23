"""Scenari DETERMINISTICI per la parita' di Omega col canale dello scanner.

Servono al test ``test_omega_legge_canale_2026_09_23.py``. Due tracce:

* ``traccia_run_once``: tre giri di ``run_once`` con un finto database che
  REGISTRA ogni chiamata (nome + argomenti) e un Betfair muto;
* ``traccia_feed``: una sequenza di ``_feed_row`` con cadenze VERE, un orologio
  che avanza a mano e un finto ``ScanRowCache`` che registra ogni select
  (``rows_for`` con gli id, ``scanner_age_sec``) e cio' che ``_feed_row`` rende.

La traccia "PRIMA" e' stata prodotta sul codice di base (b8cc1df), PRIMA di
qualunque modifica a ``omega_service.py``, con

    python -m Betfair.omega.tests.traccia_canale_scan_2026_09_23 scrivi

ed e' salvata in ``traccia_canale_scan_2026_09_23.json``. Il test ricalcola la
traccia sul codice di oggi e pretende che sia IDENTICA, a interruttore spento
(e, per il feed, anche acceso con il canale muto).

File ASCII-only. Nessuna rete, nessun database: i finti hanno le chiavi del
vero (``event_id``, ``sport``, ``payload``, ``updated_at``: la select di
``scan_feed._fetch_rows``).
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

GOLDEN = Path(__file__).with_name("traccia_canale_scan_2026_09_23.json")

NOW = datetime(2026, 9, 23, 20, 0, 0, tzinfo=timezone.utc)

CADENZE_VERE = {
    "feed_cache_s": 2.0,
    "scanner_status_cache_s": 10.0,
}


# ---------------------------------------------------------------- i finti
class DbRegistra:
    """Finto ``omega_db``: registra OGNI chiamata con i suoi argomenti."""

    def __init__(self) -> None:
        self.diario: list[list[Any]] = []
        self.params: dict[str, Any] = {"engine": "legs"}

    def _r(self, nome: str, *args: Any, **kw: Any) -> None:
        self.diario.append([nome, _norm(args), _norm(kw)])

    def read_control(self):
        self._r("read_control")
        return {"id": 1, "status": "running", "mode": "paper",
                "daily_goal": 250.0, "params": dict(self.params), "stats": {}}

    def list_trades(self, status=None):
        self._r("list_trades", status)
        return []

    def open_trades(self):
        self._r("open_trades")
        return []

    def hedged_trades(self):
        self._r("hedged_trades")
        return []

    def closing_trades_for(self, ids):
        self._r("closing_trades_for", ids)
        return []

    def get_trade(self, trade_id):
        self._r("get_trade", trade_id)
        return None

    def positions_for_results(self, since_iso):
        self._r("positions_for_results", since_iso)
        return []

    def pending_manual_requests(self):
        self._r("pending_manual_requests")
        return []

    def active_missions(self):
        self._r("active_missions")
        return []

    def mission_event_ids(self):
        self._r("mission_event_ids")
        return set()

    def manual_event_ids(self, since_iso=None):
        self._r("manual_event_ids", since_iso)
        return set()

    def traded_event_ids(self):
        self._r("traded_event_ids")
        return set()

    def traded_legs(self, since_iso=None):
        self._r("traded_legs", since_iso)
        return set()

    def failed_legs(self, since_iso=None):
        self._r("failed_legs", since_iso)
        return {}

    def aggregates(self, day_start=None):
        self._r("aggregates", day_start)
        return {"realized_today": 0.0, "realized_profit": 0.0, "matches_open": 0,
                "open_liability": 0.0, "matches_traded": 0, "matches_traded_today": 0,
                "events_today": 0, "legs_today": 0, "live_now": 0}

    def trades_for_event(self, event_id):
        self._r("trades_for_event", event_id)
        return []

    def get_event(self, event_id):
        self._r("get_event", event_id)
        return None

    def get_inplay_scores(self, event_ids):
        self._r("get_inplay_scores", event_ids)
        return {}

    def set_control(self, **fields):
        self._r("set_control", **fields)

    def log(self, kind, payload=None):
        self._r("log", kind, payload)

    def update_trade(self, trade_id, **fields):
        self._r("update_trade", trade_id, **fields)

    def insert_trade(self, trade):
        self._r("insert_trade", trade)
        return 1

    def update_mission(self, event_id, **fields):
        self._r("update_mission", event_id, **fields)

    def replace_events(self, rows):
        self._r("replace_events", rows)

    def upsert_daily_goal(self, day, goal):
        self._r("upsert_daily_goal", day, goal)
        return True


class MarketMuto:
    """Un Betfair che non ha niente da dire: qui si misura il DATABASE."""

    def list_today_football_events(self, with_competitions=False):
        return []

    def read_markets(self, markets):
        return {}


class ScanRowCacheRegistra:
    """Finto ``scan_feed.ScanRowCache``: stessa interfaccia usata da Omega
    (``rows_for(list[str]) -> {event_id: riga}``, ``scanner_age_sec()``),
    registra ogni chiamata con l'istante dell'orologio del test."""

    def __init__(self, righe: dict[str, dict], orologio: dict) -> None:
        self.righe = righe
        self.orologio = orologio
        self.diario: list[list[Any]] = []
        self.eta_scanner: Optional[float] = 2.0

    def rows_for(self, event_ids):
        self.diario.append(["rows_for", self.orologio["t"], list(event_ids)])
        return {e: dict(self.righe[e]) for e in event_ids if e in self.righe}

    def scanner_age_sec(self):
        self.diario.append(["scanner_age_sec", self.orologio["t"]])
        return self.eta_scanner


# ------------------------------------------------------------------ aiuti
def _norm(x: Any) -> Any:
    """Argomenti in forma JSON stabile (set ordinati, date in iso)."""
    return json.loads(json.dumps(x, default=_default, sort_keys=True))


def _default(o: Any) -> Any:
    if isinstance(o, (set, frozenset)):
        return sorted(str(v) for v in o)
    if isinstance(o, datetime):
        return o.isoformat()
    return repr(o)


def iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def riga_scan(event_id: str, updated_epoch: float, minute: int = 30,
              odds_ts_ms: Any = "auto", home: int = 0) -> dict[str, Any]:
    """Una riga di ``safe_strategy_scan`` con le CHIAVI del vero."""
    payload: dict[str, Any] = {"inplay": True, "minute": minute,
                               "score_home": home, "score_away": 0}
    if odds_ts_ms == "auto":
        payload["odds_ts_ms"] = 1790000000000     # un numero vero, fisso
    elif odds_ts_ms is not None:
        payload["odds_ts_ms"] = odds_ts_ms
    return {"event_id": event_id, "sport": "calcio", "payload": payload,
            "updated_at": iso(updated_epoch)}


# ---------------------------------------------------------------- scenari
def traccia_run_once(S: Any) -> list[list[Any]]:
    """Tre giri di ``run_once``: il diario del finto database."""
    db = DbRegistra()
    market = MarketMuto()
    # stato di processo che ``svuota_le_cache`` NON azzera (pre-esistente, fuori
    # perimetro): senza, la traccia dipenderebbe dal test girato prima.
    for nome in ("_EVENTS_REFRESH_AT", "_DAILY_GOAL_WRITTEN", "_IDLE_STATS_AT",
                 "_LAMBDA_CACHE", "_MINUTE_CACHE", "_REALLY_OVER_CACHE",
                 "_SKIP_SEEN", "_BLIND_CYCLES", "_LEG_RETRY_DB", "_LEG_RETRY",
                 "_EMPIRICAL_CACHE", "_MARKET_FIT_CACHE"):
        getattr(S, nome).clear()
    for i in range(3):
        S.run_once(market=market, db=db, now=NOW + timedelta(seconds=30 * i))
    return db.diario


def traccia_feed(S: Any, SF: Any, monkeypatch: Any = None) -> list[list[Any]]:
    """Una sequenza di ``_feed_row`` con cadenze VERE e orologio a mano.

    Righe relative all'orologio VERO (``fresh_payload`` usa ``time.time()``):
    nella traccia si registrano il payload e SE ``updated_at`` e' quello della
    riga, non la stringa, cosi' la traccia non dipende dall'ora del giorno.
    """
    from Betfair.omega import omega_config as C

    adesso = time.time()
    righe = {
        "E1": riga_scan("E1", adesso - 1.0, minute=31),
        "E2": riga_scan("E2", adesso - 40.0, minute=55),     # vecchia: fuori dai 25 s
        "E4": riga_scan("E4", adesso - 3.0, minute=12, odds_ts_ms=None),
    }
    orologio = {"t": 5000.0}
    finta = ScanRowCacheRegistra(righe, orologio)
    vecchie = {k: C.DEFAULTS.get(k) for k in CADENZE_VERE}
    vecchio_shared, vecchio_mono = SF.shared_cache, S._mono
    try:
        for k, v in CADENZE_VERE.items():
            C.DEFAULTS[k] = v
        S.svuota_le_cache()
        SF.shared_cache = lambda: finta
        S._mono = lambda: orologio["t"]
        uscite: list[list[Any]] = []

        def chiedi(eid: str, tetto: Optional[float] = None) -> None:
            payload, upd = S._feed_row(eid, hard_max_age=tetto)
            riga = righe.get(eid) or {}
            uscite.append(["feed_row", orologio["t"], eid, tetto, _norm(payload),
                           upd is not None and upd == riga.get("updated_at")])

        passi = [
            (0.0, "E1", None), (0.0, "E2", 25.0), (0.0, "E1", 25.0),
            (1.0, "E1", None), (1.0, "E3", None), (1.0, "E4", 25.0),
            (2.5, "E1", 25.0), (2.5, "E2", None),
            (6.0, "E1", 25.0), (11.0, "E4", None), (13.0, "E1", 25.0),
            (15.0, "E3", 25.0), (200.0, "E1", 25.0), (201.0, "E4", None),
        ]
        for dt, eid, tetto in passi:
            orologio["t"] = 5000.0 + dt
            chiedi(eid, tetto)
        return [["select", finta.diario], ["uscite", uscite]]
    finally:
        SF.shared_cache, S._mono = vecchio_shared, vecchio_mono
        for k, v in vecchie.items():
            C.DEFAULTS[k] = v
        S.svuota_le_cache()


def calcola() -> dict[str, Any]:
    from Betfair.omega import omega_config as C
    from Betfair.omega import omega_service as S
    from Betfair.stream.scores import scan_feed as SF

    # stesso stato di partenza del conftest di Omega: cadenze spente, motore v2
    chiavi = ("feed_cache_s", "scanner_status_cache_s", "aggregates_cache_s",
              "sets_cache_s", "results_every_s", "missions_every_s",
              "events_refresh_s", "idle_stats_s", "idle_cycle_s", "conto_every_s")
    for k in chiavi:
        if k in C.DEFAULTS:
            C.DEFAULTS[k] = 0.0
    C.DEFAULTS["strategy_version"] = 2
    S.svuota_le_cache()
    run = traccia_run_once(S)
    S.svuota_le_cache()
    feed = traccia_feed(S, SF)
    return {"run_once": run, "feed": feed}


if __name__ == "__main__":  # pragma: no cover - strumento, non test
    if len(sys.argv) > 1 and sys.argv[1] == "scrivi":
        GOLDEN.write_text(json.dumps(calcola(), indent=1, sort_keys=True) + "\n",
                          encoding="ascii")
        print("scritta", GOLDEN)
    else:
        print(json.dumps(calcola(), sort_keys=True)[:2000])
