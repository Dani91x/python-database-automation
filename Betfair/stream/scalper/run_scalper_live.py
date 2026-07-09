"""Runner LIVE dello scalper (pre-match) con protezioni.

USO (dal root del repo):
    python -m Betfair.stream.scalper.run_scalper_live --hours-ahead 2
    python -m Betfair.stream.scalper.run_scalper_live --market-ids 1.259526914,...
    python -m Betfair.stream.scalper.run_scalper_live --event-ids 35764745

PROTEZIONI:
  * opera SOLO pre-match (allow_inplay forzato False; le posizioni aperte al
    KO vengono comunque GESTITE fino a flat, come da design v2);
  * KILL-SWITCH: crea un file ``STOP_SCALPER`` nella cwd per fermare tutto
    (cancella gli ordini vivi, flatten e shutdown);
  * cap di esposizione flumine per selezione/ordine derivati dallo stake;
  * selezione mercati LIQUIDI: top per volume scambiato dal catalogo, solo
    calcio (eventTypeId=1), tipi validati (MATCH_ODDS, O/U), KO entro N ore.

Lo stake di default live e' PRUDENTE (5). La config validata in backtest
(dossier §9) usa 25: alzarlo esplicitamente con --stake quando si e' pronti.
"""
from __future__ import annotations

import argparse
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

from flumine import Flumine, clients

from ..auth import build_client
from .scalper_bot import ScalperStrategy

logger = logging.getLogger(__name__)

KILL_FILE = "STOP_SCALPER"
# tipi mercato validati in backtest (dossier §9): MATCH_ODDS ha il flusso
# migliore; O/U principali ok. Tutto il resto e' fuori dal perimetro live.
LIVE_MARKET_TYPES = [
    "MATCH_ODDS",
    "OVER_UNDER_15",
    "OVER_UNDER_25",
    "OVER_UNDER_35",
]


def select_liquid_markets(
    trading: Any,
    hours_ahead: float,
    max_markets: int,
    event_ids: Optional[List[str]] = None,
) -> List[str]:
    """Market id dei mercati calcio piu' LIQUIDI con KO entro ``hours_ahead``."""
    from betfairlightweight import filters

    market_filter = filters.market_filter(
        event_type_ids=["1"],
        event_ids=event_ids or None,
        market_type_codes=LIVE_MARKET_TYPES,
        market_start_time={
            "from": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "to": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + hours_ahead * 3600)
            ),
        },
        in_play_only=False,
    )
    cat = trading.betting.list_market_catalogue(
        filter=market_filter,
        market_projection=["MARKET_START_TIME", "EVENT"],
        sort="MAXIMUM_TRADED",
        max_results=max_markets,
    )
    out = []
    for m in cat:
        total = float(getattr(m, "total_matched", 0.0) or 0.0)
        ev = getattr(getattr(m, "event", None), "name", "?")
        logger.info("[scalper-live] candidato %s (%s) matched=%.0f",
                    m.market_id, ev, total)
        out.append(m.market_id)
    return out


def _streaming_filter(market_ids: List[str]) -> Dict[str, Any]:
    """Filtro nel formato STREAMING Betfair (camelCase: ``marketIds``).

    ⚠️ fix 09/07: prima si passava ``{"market_ids": [...]}`` (snake_case):
    per lo stream e' una chiave SCONOSCIUTA → filtro vuoto → flumine si
    abbona a TUTTO l'exchange → SUBSCRIPTION_LIMIT_EXCEEDED (stesso bug
    visto live il 02/07 e gia' fixato in scalper_session).
    """
    from betfairlightweight import filters

    return filters.streaming_market_filter(market_ids=list(market_ids))


def _parse_param_value(v: str) -> Any:
    """Valore di un --param: bool/int/float/str.

    fix 09/07: il vecchio parser lasciava "false"/"true" come STRINGHE →
    ``bool("false") is True``: un ``--param exact_exits=false`` ATTIVAVA il
    flag. Inoltre i negativi ("-1.5") restavano stringhe.
    """
    s = str(v).strip()
    low = s.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        return s


def _kill_switch_worker(framework: Flumine) -> None:
    """Ferma il framework se compare il file KILL_FILE."""
    while True:
        if os.path.isfile(KILL_FILE):
            logger.warning("[scalper-live] KILL-SWITCH rilevato (%s): stop.",
                           KILL_FILE)
            try:
                framework.handler_queue.put(None)  # segnala lo shutdown
            except Exception:  # noqa: BLE001
                pass
            os._exit(0)  # hard-stop: gli ordini LAPSE decadono da soli
        time.sleep(2.0)


def main() -> None:
    ap = argparse.ArgumentParser(description="Scalper LIVE pre-match")
    ap.add_argument("--market-ids", default="",
                    help="market id espliciti, separati da virgola")
    ap.add_argument("--event-ids", default="",
                    help="event id: i mercati liquidi si scelgono dal catalogo")
    ap.add_argument("--hours-ahead", type=float, default=2.0,
                    help="finestra KO per la selezione automatica (default 2h)")
    ap.add_argument("--max-markets", type=int, default=12)
    ap.add_argument("--stake", type=float, default=5.0,
                    help="stake per ingresso (default PRUDENTE 5; validato 25)")
    ap.add_argument("--param", action="append", default=[],
                    help="override parametri strategia: nome=valore (ripetibile)")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    trading = build_client(login=True)

    if args.market_ids:
        market_ids = [m.strip() for m in args.market_ids.split(",") if m.strip()]
    else:
        event_ids = [e.strip() for e in args.event_ids.split(",") if e.strip()]
        market_ids = select_liquid_markets(
            trading, args.hours_ahead, args.max_markets, event_ids or None
        )
    if not market_ids:
        raise SystemExit("nessun mercato selezionato (catalogo vuoto?)")
    logger.info("[scalper-live] %d mercati: %s", len(market_ids), market_ids)

    scalper_params: Dict[str, Any] = {
        "stake": args.stake,
        "allow_inplay": False,  # FORZATO: il live e' SOLO pre-match
        # PROTEZIONI EXCHANGE .it (come scalper_session, fix 09/07): senza,
        # una size non multipla di 0,50 € viene RIFIUTATA (INVALID_BET_SIZE,
        # verificato live 02/07) e la posizione resta NUDA.
        "live_min_bet": 2.0,
        "size_step": 0.5,
        "flatten_min_interval_ms": 1500,
    }
    for kv in args.param:
        k, _, v = kv.partition("=")
        scalper_params[k] = _parse_param_value(v)
    scalper_params["allow_inplay"] = False

    # min_bet_validation=False COME scalper_session (fix CRITICAL-3 del
    # live-trading): l'OrderValidation di flumine rifiuterebbe gli hedge di
    # size esatta sotto-minimo; i minimi veri li garantisce la strategia.
    framework = Flumine(client=clients.BetfairClient(
        trading, min_bet_validation=False))
    # cap esposizione: il worst-case di un ciclo e' ~stake*(price_max-1) sul
    # lay; margine 2x per gli hedge in volo.
    price_max = float(scalper_params.get("price_max", 4.6))
    exposure_cap = args.stake * (price_max - 1.0) * 2.0
    strategy = ScalperStrategy(
        market_filter=_streaming_filter(market_ids),
        scalper_params=scalper_params,
        max_selection_exposure=exposure_cap,
        max_order_exposure=exposure_cap,
        max_trade_count=int(1e6),
        max_live_trade_count=int(1e6),
    )
    framework.add_strategy(strategy)

    t = threading.Thread(target=_kill_switch_worker, args=(framework,),
                         daemon=True, name="scalper-kill-switch")
    t.start()

    logger.info("[scalper-live] avvio (stake=%.2f, cap esposizione=%.2f). "
                "Kill-switch: crea il file %s", args.stake, exposure_cap,
                KILL_FILE)
    framework.run()


if __name__ == "__main__":
    main()
