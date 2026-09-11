"""risk — motore di RISCHIO di TUTTI i piazzamenti del bot Safe Strategy.

Modulo PURO (nessun DB, nessuna rete): il bot (``bot_service``) lo chiama
PRIMA della riserva in ogni percorso di piazzamento — segnali del motore,
opportunità di modello, anomalie, combo, tennis — e, in forma "morbida"
(solo i cap di esposizione), per le richieste manuali della UI.

Sezione ``params.risk`` del control (fusa con i default da ``merge_risk_params``):

  daily_liability_cap        liability TOTALE impegnata nella giornata operativa
                             (aperta + già regolata, gambe di chiusura escluse)
  per_event_liability_cap    esposizione CORRELATA per evento (vedi sotto)
  per_event_max_trades       posizioni aperte per evento
  max_open_trades            posizioni aperte totali (None = params.max_open_trades)
  correlated_cap             peso (0-1) della liability dei trade su MERCATI DIVERSI
                             dello stesso evento nel computo per evento: stesso
                             evento+mercato conta al 100%, mercati diversi al 70%
  daily_loss_stop            realizzato della giornata (Europe/Rome) a cui si
                             FERMANO i nuovi ingressi (≤ soglia negativa)
  model_stake                stake unico dei trade di modello/anomalia/combo/tennis
  model_daily_liability_cap  liability giornaliera dei soli trade di modello

Giornata operativa = giorno solare Europe/Rome (``operating_day_start``).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

try:  # tzdata può mancare su Windows: riserva con regola DST europea
    from zoneinfo import ZoneInfo

    _ROME: Any = ZoneInfo("Europe/Rome")
except Exception:  # noqa: BLE001
    _ROME = None

DEFAULT_RISK_PARAMS: dict[str, Any] = {
    "daily_liability_cap": 500.0,
    "per_event_liability_cap": 150.0,
    "per_event_max_trades": 3,
    "max_open_trades": None,          # None → params.max_open_trades del bot
    "correlated_cap": 0.7,
    "daily_loss_stop": -50.0,
    "model_stake": 5.0,
    "model_daily_liability_cap": 150.0,
}

# strategie "di modello" (stessa colonna 'model' del DB; il tipo è in meta.kind)
MODEL_STRATEGIES = ("model",)

# motivi di blocco (etichette stabili per log/UI)
R_LOSS_STOP = "daily_loss_stop"
R_MAX_OPEN = "max_open_trades"
R_EVENT_TRADES = "per_event_max_trades"
R_EVENT_LIAB = "per_event_liability_cap"
R_DAILY_LIAB = "daily_liability_cap"
R_MODEL_LIAB = "model_daily_liability_cap"


def _f(v: Any, default: float) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if f == f else default


def merge_risk_params(raw: Any) -> dict[str, Any]:
    """Default + override utente con clamp: cap ≥ 0 (0 = nessun cap), conteggi
    interi ≥ 0, peso correlazione 0-1, stake ≥ 0. ``daily_loss_stop`` è sempre
    ≤ 0 per SEGNO INTERPRETATO (50 → −50; 0 = disattivo).
    Chiavi sconosciute ignorate."""
    out = dict(DEFAULT_RISK_PARAMS)
    src = raw if isinstance(raw, dict) else {}
    for k in ("daily_liability_cap", "per_event_liability_cap",
              "model_daily_liability_cap", "model_stake"):
        out[k] = max(0.0, _f(src.get(k, out[k]), float(out[k])))
    out["per_event_max_trades"] = max(0, int(_f(src.get("per_event_max_trades"),
                                                float(out["per_event_max_trades"]))))
    mo = src.get("max_open_trades", out["max_open_trades"])
    out["max_open_trades"] = None if mo is None else max(0, int(_f(mo, 0.0)))
    out["correlated_cap"] = min(1.0, max(0.0, _f(src.get("correlated_cap"),
                                                 float(out["correlated_cap"]))))
    # daily_loss_stop: il SEGNO si interpreta, non si azzera (review H2).
    # L'utente che scrive "50" intende "fermati a -50 EUR": clamparlo a 0
    # SPEGNEVA lo stop perdite senza dirlo. 0 resta 0 = disattivo.
    out["daily_loss_stop"] = -abs(_f(src.get("daily_loss_stop"),
                                     float(out["daily_loss_stop"])))
    return out


def risk_params(params: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Sezione ``risk`` completa dai parametri del bot (già fusa da resolve_params
    oppure grezza); ``max_open_trades`` None → quello del bot."""
    params = params if isinstance(params, dict) else {}
    sec = params.get("risk")
    rp = sec if isinstance(sec, dict) and set(sec) >= set(DEFAULT_RISK_PARAMS) \
        else merge_risk_params(sec)
    rp = dict(rp)
    if rp.get("max_open_trades") is None:
        rp["max_open_trades"] = max(0, int(_f(params.get("max_open_trades"), 0.0)))
    return rp


# ---------------------------------------------------------------------------
# giornata operativa (Europe/Rome)
# ---------------------------------------------------------------------------
def _rome_offset(dt_utc: datetime) -> timedelta:
    """Riserva senza tzdata: CET/CEST con la regola UE (ultima domenica di
    marzo 01:00 UTC → ultima domenica di ottobre 01:00 UTC)."""
    y = dt_utc.year

    def last_sunday(month: int) -> datetime:
        d = datetime(y, month + 1, 1, 1, tzinfo=timezone.utc) - timedelta(days=1) \
            if month < 12 else datetime(y, 12, 31, 1, tzinfo=timezone.utc)
        return d - timedelta(days=(d.weekday() + 1) % 7)

    start, end = last_sunday(3), last_sunday(10)
    return timedelta(hours=2) if start <= dt_utc < end else timedelta(hours=1)


def operating_day_start(now: Optional[datetime] = None) -> datetime:
    """Mezzanotte Europe/Rome della giornata operativa corrente, in UTC."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    if _ROME is not None:
        local = now.astimezone(_ROME)
        start = local.replace(hour=0, minute=0, second=0, microsecond=0)
        return start.astimezone(timezone.utc)
    off = _rome_offset(now)
    local = now + off
    start_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return (start_local - off).replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# esposizione
# ---------------------------------------------------------------------------
def _liab(t: dict[str, Any]) -> float:
    return max(0.0, _f(t.get("liability"), 0.0))


def _is_position(t: dict[str, Any]) -> bool:
    """Riga che conta come posizione: non gamba di chiusura, stato vivo."""
    if t.get("closes_trade_id"):
        return False
    return str(t.get("status") or "open") in ("open", "hedged", "pending")


def event_exposure(open_trades: list[dict[str, Any]], event_id: str,
                   market_type: Optional[str], weight: float) -> float:
    """Esposizione CORRELATA già aperta sull'evento: liability piena sui trade
    dello stesso mercato, pesata ``weight`` sui mercati diversi."""
    eid, mt = str(event_id), str(market_type or "").upper()
    tot = 0.0
    for t in open_trades or []:
        if not _is_position(t) or str(t.get("event_id")) != eid:
            continue
        same = str(t.get("market_type") or "").upper() == mt
        tot += _liab(t) * (1.0 if same else weight)
    return round(tot, 2)


def event_count(open_trades: list[dict[str, Any]], event_id: str) -> int:
    eid = str(event_id)
    return sum(1 for t in open_trades or [] if _is_position(t) and str(t.get("event_id")) == eid)


def open_count(open_trades: list[dict[str, Any]]) -> int:
    return sum(1 for t in open_trades or [] if _is_position(t))


def loss_stop_active(realized_today: Any, params: Optional[dict[str, Any]]) -> bool:
    rp = risk_params(params)
    stop = float(rp.get("daily_loss_stop") or 0.0)
    return stop < 0 and _f(realized_today, 0.0) <= stop


# ---------------------------------------------------------------------------
# verifica
# ---------------------------------------------------------------------------
def check(open_trades: list[dict[str, Any]], candidate: dict[str, Any],
          realized_today: Any, params: Optional[dict[str, Any]], *,
          day_liability: Any = 0.0, day_liability_model: Any = 0.0,
          soft: bool = False) -> tuple[bool, Optional[str]]:
    """(ok, motivo). ``candidate`` = {event_id, market_type, liability, strategy}.

    Ordine: loss stop giornaliero → max posizioni aperte → posizioni per evento
    → cap liability correlata per evento → cap liability giornaliera → cap
    giornaliero dei trade di modello. ``soft=True`` (richieste MANUALI della
    UI): SOLO i cap di esposizione (evento + giornata), mai loss stop/conteggi.
    Un cap a 0 è disattivo. Il primo motivo che blocca vince."""
    rp = risk_params(params)
    liab = max(0.0, _f(candidate.get("liability"), 0.0))
    eid = str(candidate.get("event_id") or "")
    mt = candidate.get("market_type")
    if not soft:
        if loss_stop_active(realized_today, params):
            return False, R_LOSS_STOP
        max_open = int(rp.get("max_open_trades") or 0)
        if max_open and open_count(open_trades) >= max_open:
            return False, R_MAX_OPEN
        per_ev = int(rp.get("per_event_max_trades") or 0)
        if per_ev and event_count(open_trades, eid) >= per_ev:
            return False, R_EVENT_TRADES
    ev_cap = float(rp.get("per_event_liability_cap") or 0.0)
    if ev_cap > 0:
        exp = event_exposure(open_trades, eid, mt, float(rp.get("correlated_cap") or 0.0))
        if exp + liab > ev_cap + 1e-9:
            return False, R_EVENT_LIAB
    day_cap = float(rp.get("daily_liability_cap") or 0.0)
    if day_cap > 0 and _f(day_liability, 0.0) + liab > day_cap + 1e-9:
        return False, R_DAILY_LIAB
    if not soft and str(candidate.get("strategy") or "") in MODEL_STRATEGIES:
        m_cap = float(rp.get("model_daily_liability_cap") or 0.0)
        if m_cap > 0 and _f(day_liability_model, 0.0) + liab > m_cap + 1e-9:
            return False, R_MODEL_LIAB
    return True, None
