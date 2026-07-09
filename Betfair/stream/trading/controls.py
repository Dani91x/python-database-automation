"""controls.py — Trading control NATIVI flumine per il runner live (money-critical).

Per chi: si registrano sul framework flumine con ``framework.add_trading_control(Control)``
(o sul client). flumine invoca ``control(order, package_type)`` -> ``_validate(...)`` PRIMA di
inviare l'istruzione a Betfair; un ``self._on_error(order, reason)`` marca l'ordine come
violazione e solleva ``flumine.exceptions.ControlError``, impedendo l'invio.

Questi due control sono la versione NATIVA e STRETTA di guardie che oggi vivono best-effort nel
worker (``live_order_worker._check_exposure_guard`` / ``_rate_limited``). Girando nel path di
esecuzione di flumine coprono OGNI ordine (place del worker, submin, dutch, green-up, ecc.),
non solo quelli passati esplicitamente dal worker.

Semantica (identica alle guardie del worker):
  * ``LiveExposureControl`` — rifiuta un PLACE se l'esposizione RISULTANTE sulla (market,
    selection) supererebbe ``max_exposure_per_selection`` (NULL/assente = disattivato). Esposizione
    corrente = ``market.blotter.selection_exposure(strategy, order.lookup)``; contributo del nuovo
    ordine = size (BACK) o liability = size*(price-1) (LAY).
  * ``LiveRateControl`` — rifiuta un PLACE se nei 60s scorsi i place hanno raggiunto
    ``max_orders_per_min`` (NULL/assente = disattivato). Finestra scorrevole in-memory.

I limiti sono letti da ``betfair_live_settings`` via RPC ``get_live_settings`` (Supabase), con
cache a TTL breve (default 2s) per evitare un hit DB per-ordine.

MONEY-CRITICAL & DIFENSIVO: qualunque errore di LETTURA (DB giù, blotter/esposizione non
calcolabile, order_type incompleto) NON blocca l'ordine (fail-open). Ma quando i dati SONO
disponibili il check è STRETTO: se l'esposizione risultante supera il tetto, o il rate ha
raggiunto il cap, l'ordine è RIFIUTATO.

Testabile a unità: order/market/blotter/settings sono mockabili; nessuna rete, nessun flumine
reale (si può istanziare il control con un flumine fittizio e chiamare ``__call__``/``_validate``).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from flumine.controls import BaseControl
from flumine.order.orderpackage import OrderPackageType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper di parsing difensivo (stessa semantica di live_order_worker._f / _int)
# ---------------------------------------------------------------------------
def _f(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _int(v: Any) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _now_epoch() -> float:
    return datetime.now(timezone.utc).timestamp()


# ---------------------------------------------------------------------------
# Settings runtime (betfair_live_settings via RPC get_live_settings) con cache TTL.
# Un solo snapshot letto al massimo ogni ``_SETTINGS_TTL`` secondi: gli ordini arrivano
# a raffica e non vogliamo un round-trip DB per ognuno. Fail-open su errore di lettura:
# si ritorna l'ultimo snapshot valido (dict vuoto se mai letto => limiti disattivati).
# ---------------------------------------------------------------------------
_SETTINGS_TTL: float = 2.0
_SETTINGS_CACHE: Dict[str, Any] = {"data": {}, "ts": 0.0}


def get_live_settings(force: bool = False) -> Dict[str, Any]:
    """Snapshot di ``betfair_live_settings`` (RPC ``get_live_settings``), cache TTL ~2s.

    Best-effort/fail-open: se il DB non risponde si ritorna l'ULTIMO snapshot valido (o {} se
    mai letto). L'aggiornamento del timestamp anche in caso di errore evita di martellare il DB
    a ogni ordine quando è irraggiungibile.
    """
    now = _now_epoch()
    if not force and (now - float(_SETTINGS_CACHE.get("ts", 0.0))) < _SETTINGS_TTL:
        return _SETTINGS_CACHE["data"]
    # oltre il TTL (o forzato): prova a rileggere. Qualunque KO => tieni l'ultimo valido.
    try:
        from db_client import get_supabase_client  # import lazy: no dipendenza all'import

        sb = get_supabase_client()
        res = sb.rpc("get_live_settings", {}).execute()
        data = getattr(res, "data", None)
        if isinstance(data, dict):
            _SETTINGS_CACHE["data"] = dict(data)
    except Exception:  # noqa: BLE001 - fail-open: mantieni l'ultimo snapshot, non bloccare
        logger.debug("[live-control] lettura settings KO, uso l'ultimo snapshot", exc_info=True)
    finally:
        _SETTINGS_CACHE["ts"] = now
    return _SETTINGS_CACHE["data"]


def _max_exposure_per_selection() -> Optional[float]:
    return _f(get_live_settings().get("max_exposure_per_selection"))


def _max_orders_per_min() -> Optional[int]:
    return _int(get_live_settings().get("max_orders_per_min"))


# ---------------------------------------------------------------------------
# Lettura difensiva dell'ordine flumine
# ---------------------------------------------------------------------------
def _val(obj: Any, attr: str) -> Any:
    try:
        return getattr(obj, attr)
    except Exception:  # noqa: BLE001 - alcune property sollevano in stati di confine
        return None


def _order_exposure(order: Any) -> Optional[float]:
    """Contributo worst-case del nuovo ordine all'esposizione della selezione.

    BACK: size. LAY: liability = size*(price-1). Ricade su ``order_type.liability`` per gli
    ordini a chiusura (LIMIT_ON_CLOSE / MARKET_ON_CLOSE). None se non calcolabile (=> fail-open).
    Semantica identica a ``live_order_worker._do_place`` (order_risk).
    """
    ot = _val(order, "order_type")
    if ot is None:
        return None
    size = _f(_val(ot, "size"))
    if size is None:
        size = _f(_val(ot, "bet_target_size"))
    price = _f(_val(ot, "price"))
    liability = _f(_val(ot, "liability"))
    side = _val(order, "side")
    side_u = str(side).upper() if side is not None else None

    if side_u == "BACK":
        if size is not None:
            return size
        return liability  # es. MARKET_ON_CLOSE back
    if side_u == "LAY":
        if size is not None and price is not None:
            return round(size * (price - 1.0), 2)
        return liability  # es. LIMIT_ON_CLOSE / MARKET_ON_CLOSE lay
    return None


# ---------------------------------------------------------------------------
# LiveExposureControl — max esposizione per selezione (STRETTA, NATIVA)
# ---------------------------------------------------------------------------
class LiveExposureControl(BaseControl):
    """Rifiuta un PLACE se l'esposizione RISULTANTE sulla (market, selection) supererebbe
    ``betfair_live_settings.max_exposure_per_selection`` (NULL/assente = disattivato).

    Risultante = esposizione corrente della selezione (``blotter.selection_exposure(strategy,
    order.lookup)``, worst-case win/lose, sempre >= 0) + contributo del nuovo ordine
    (size per BACK, liability=size*(price-1) per LAY). Difensivo: cap assente, strategy/blotter
    non disponibili o esposizione non calcolabile => NON blocca (fail-open). Con i dati
    disponibili il confronto è STRETTO.
    """

    NAME = "LIVE_EXPOSURE"

    def _validate(self, order: Any, package_type: OrderPackageType) -> None:
        # Solo i PLACE aprono nuova esposizione di selezione; gli altri package (CANCEL/REPLACE/
        # UPDATE) non sono gestiti qui (il replace LAY ha la sua guardia dedicata nel worker).
        if package_type != OrderPackageType.PLACE:
            return

        cap = _max_exposure_per_selection()
        if cap is None or cap <= 0:
            return  # limite disattivato

        # strategy dall'ordine (order.trade.strategy). Senza di essa non si legge l'esposizione.
        trade = _val(order, "trade")
        strategy = _val(trade, "strategy") if trade is not None else None
        if strategy is None:
            return  # fail-open: nessuna strategy => niente esposizione calcolabile

        market = None
        try:
            market = self.flumine.markets.markets.get(_val(order, "market_id"))
        except Exception:  # noqa: BLE001 - struttura framework inattesa => fail-open
            market = None
        if market is None:
            return
        blotter = _val(market, "blotter")
        if blotter is None:
            return

        order_risk = _order_exposure(order)
        if order_risk is None:
            return  # contributo non calcolabile => non bloccare

        try:
            lookup = _val(order, "lookup")
            current = abs(_f(blotter.selection_exposure(strategy, lookup)) or 0.0)
        except Exception:  # noqa: BLE001 - esposizione non determinabile => fail-open
            return

        resulting = current + max(0.0, float(order_risk))
        if resulting > float(cap) + 1e-9:
            self._on_error(
                order,
                "max esposizione selezione: €%.2f (corrente €%.2f + ordine €%.2f) "
                "oltre il tetto €%.2f" % (resulting, current, float(order_risk), float(cap)),
            )


# ---------------------------------------------------------------------------
# LiveRateControl — rate-limit place ordini/min (STRETTA, NATIVA)
# ---------------------------------------------------------------------------
class LiveRateControl(BaseControl):
    """Rifiuta un PLACE se nei 60s scorsi i place hanno raggiunto
    ``betfair_live_settings.max_orders_per_min`` (NULL/assente = disattivato).

    Finestra scorrevole in-memory per istanza del control. Un place che PASSA il check viene
    registrato (come nel worker: ``_record_order`` dopo il place riuscito); uno RIFIUTATO non
    viene registrato. Difensivo: cap assente => non blocca.
    """

    NAME = "LIVE_RATE"

    def __init__(self, flumine: Any, *args: Any, **kwargs: Any) -> None:
        super().__init__(flumine, *args, **kwargs)
        self._order_ts: list = []  # epoch (s) dei place recenti (finestra scorrevole 60s)

    def _validate(self, order: Any, package_type: OrderPackageType) -> None:
        if package_type != OrderPackageType.PLACE:
            return

        # Ordini di CHIUSURA (green-up/hedge/cash-out, marcati reduces_liability da
        # live_order_build): MAI rate-limitati. Il rate-limit protegge dal runaway di
        # APERTURE; bloccare un'uscita d'emergenza in una raffica sarebbe l'opposto
        # della protezione (stop-flatten rifiutato = posizione che sanguina).
        ctx = _val(order, "context")
        if isinstance(ctx, dict) and ctx.get("reduces_liability"):
            return

        cap = _max_orders_per_min()
        if cap is None or cap <= 0:
            return  # limite disattivato

        now = _now_epoch()
        # purge della finestra: tieni solo i place nell'ultimo minuto.
        self._order_ts = [t for t in self._order_ts if now - t < 60.0]
        if len(self._order_ts) >= cap:
            self._on_error(
                order,
                "rate-limit ordini/min raggiunto: %d nell'ultimo minuto "
                "(betfair_live_settings.max_orders_per_min=%d)" % (len(self._order_ts), cap),
            )
            return  # _on_error solleva; return è difensivo se venisse sovrascritto
        # check passato => questo place conta per la finestra.
        self._order_ts.append(now)


# ---------------------------------------------------------------------------
# E35 — LiveEventExposureControl: max esposizione per EVENTO e per CAMPIONATO
# ---------------------------------------------------------------------------
def _max_exposure_per_event() -> Optional[float]:
    return _f(get_live_settings().get("max_exposure_per_event"))


def _max_exposure_per_league() -> Optional[float]:
    return _f(get_live_settings().get("max_exposure_per_league"))


# Mappa event_id -> league_name da live_follow (cache TTL: gli ordini arrivano a
# raffica, il campionato di un evento non cambia). Fail-open: DB KO => ultimo
# snapshot valido ({} se mai letto => limite campionato di fatto non applicabile).
_LEAGUE_TTL: float = 60.0
_LEAGUE_CACHE: Dict[str, Any] = {"data": {}, "ts": 0.0}


def _league_map(force: bool = False) -> Dict[str, str]:
    now = _now_epoch()
    if not force and (now - float(_LEAGUE_CACHE.get("ts", 0.0))) < _LEAGUE_TTL:
        return _LEAGUE_CACHE["data"]
    try:
        from db_client import get_supabase_client  # import lazy

        sb = get_supabase_client()
        # limit difensivo (fix review MEDIUM): la mappa serve solo per gli eventi
        # attivi/recenti — mai una scansione illimitata dal thread ordini.
        res = (
            sb.table("live_follow")
            .select("event_id,league_name")
            .order("updated_at", desc=True)
            .limit(500)
            .execute()
        )
        rows = getattr(res, "data", None) or []
        data = {
            str(r.get("event_id")): str(r.get("league_name"))
            for r in rows
            if r.get("event_id") and r.get("league_name")
        }
        _LEAGUE_CACHE["data"] = data
    except Exception:  # noqa: BLE001 - fail-open: mantieni l'ultimo snapshot
        logger.debug("[live-control] lettura league map KO, uso l'ultimo snapshot", exc_info=True)
    finally:
        _LEAGUE_CACHE["ts"] = now
    return _LEAGUE_CACHE["data"]


def _market_loss(blotter: Any, strategy: Any, market_book: Any, new_order: Any = None) -> Optional[float]:
    """Perdita worst-case (>=0) della strategia su UN mercato, da flumine.

    Usa ``blotter.market_exposure`` (la matematica NATIVA flumine del worst-case di
    mercato attraverso gli esiti, con supporto ``new_order``): MAI ricalcolata a mano.
    None = non calcolabile (il chiamante decide fail-open/skip).
    """
    try:
        exp = blotter.market_exposure(strategy, market_book, new_order=new_order)
    except Exception:  # noqa: BLE001 - blotter/book in stato di confine
        return None
    v = _f(exp)
    if v is None:
        return None
    return max(0.0, -v)  # esposizione = perdita potenziale (market_exposure<0)


class LiveEventExposureControl(BaseControl):
    """Rifiuta un PLACE se l'esposizione worst-case RISULTANTE aggregata per EVENTO
    (somma dei worst-case di mercato di flumine su tutti i mercati dell'evento) o per
    CAMPIONATO (somma degli eventi del campionato, mappa live_follow) supererebbe
    ``max_exposure_per_event`` / ``max_exposure_per_league`` (NULL/assente = off).

    Gli ordini di CHIUSURA (``reduces_liability`` da live_order_build: green-up, hedge,
    cash-out) NON sono mai bloccati: un cap aggregato che rifiuta un'uscita sarebbe
    l'opposto della protezione. Difensivo/fail-open: senza strategy/mercato/book o con
    esposizione del mercato TARGET non calcolabile NON blocca; i mercati SECONDARI non
    calcolabili sono esclusi dalla somma (stima per difetto, mai un falso blocco).
    Con i dati disponibili il confronto è STRETTO.
    """

    NAME = "LIVE_EVENT_EXPOSURE"

    def _validate(self, order: Any, package_type: OrderPackageType) -> None:
        if package_type != OrderPackageType.PLACE:
            return

        ctx = _val(order, "context")
        if isinstance(ctx, dict) and ctx.get("reduces_liability"):
            return  # chiusure sempre permesse

        cap_event = _max_exposure_per_event()
        cap_league = _max_exposure_per_league()
        if (cap_event is None or cap_event <= 0) and (cap_league is None or cap_league <= 0):
            return  # entrambi i limiti disattivati

        trade = _val(order, "trade")
        strategy = _val(trade, "strategy") if trade is not None else None
        if strategy is None:
            return  # fail-open

        try:
            markets = dict(self.flumine.markets.markets)
        except Exception:  # noqa: BLE001 - struttura framework inattesa
            return
        target_market_id = _val(order, "market_id")
        target_market = markets.get(target_market_id)
        if target_market is None:
            return  # fail-open
        target_event = _val(target_market, "event_id")
        if target_event is None:
            return  # senza event_id non esiste aggregato evento

        # perdita worst-case per evento (il mercato TARGET include il NUOVO ordine).
        # fix review MEDIUM: se il cap CAMPIONATO è spento serve SOLO l'evento target →
        # niente market_exposure sui mercati di altri eventi (path sincrono del place).
        league_active = cap_league is not None and cap_league > 0
        losses_by_event: Dict[str, float] = {}
        for m_id, m in markets.items():
            if _val(m, "closed"):
                continue
            ev = _val(m, "event_id")
            if not league_active and ev != target_event and m_id != target_market_id:
                continue
            blotter = _val(m, "blotter")
            mb = _val(m, "market_book")
            if ev is None or blotter is None or mb is None:
                if m_id == target_market_id:
                    return  # target non valutabile => fail-open
                continue
            is_target = m_id == target_market_id
            loss = _market_loss(blotter, strategy, mb, new_order=order if is_target else None)
            if loss is None:
                if is_target:
                    return  # target non valutabile => fail-open
                continue  # secondario non calcolabile: escluso (stima per difetto)
            losses_by_event[ev] = losses_by_event.get(ev, 0.0) + loss

        event_total = losses_by_event.get(target_event, 0.0)
        if cap_event is not None and cap_event > 0 and event_total > float(cap_event) + 1e-9:
            self._on_error(
                order,
                "max esposizione EVENTO %s: risultante €%.2f oltre il tetto €%.2f"
                % (target_event, event_total, float(cap_event)),
            )
            return

        if cap_league is None or cap_league <= 0:
            return
        leagues = _league_map()
        league = leagues.get(str(target_event))
        if not league:
            return  # campionato ignoto => limite non applicabile (fail-open)
        league_total = sum(
            loss for ev, loss in losses_by_event.items() if leagues.get(str(ev)) == league
        )
        if league_total > float(cap_league) + 1e-9:
            self._on_error(
                order,
                "max esposizione CAMPIONATO '%s': risultante €%.2f oltre il tetto €%.2f"
                % (league, league_total, float(cap_league)),
            )
