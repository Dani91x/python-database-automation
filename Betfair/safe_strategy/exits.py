"""exits — regole di USCITA automatica delle posizioni del bot Safe Strategy.

Modulo PURO (nessun DB, nessuna rete): il bot (``bot_service.process_exits``)
chiama ad ogni ciclo, per ogni trade 'open' di origine 'auto' delle 4
strategie, prima ``track`` (aggiorna il tracciamento in ``meta.exit_track``:
punteggio d'ingresso, gol/game da allora, rossi, set) e poi ``decide`` che
restituisce, se c'è, un ``ExitDecision`` da eseguire con ``execution.close_trade``
(green-up/chiusura INTEGRALE, fraction=1.0).

Regole del manuale operativo (una per strategia):

  BASE   (lay della squadra che perde sul Match Odds, favorita avanti)
         PROFIT  la favorita segna ancora dopo l'ingresso
         TIME    nessun altro gol al minuto ``base_exit_minute`` (80)
         LOSS    la squadra bancata pareggia (o sorpassa) — dopo il ritardo di
                 assestamento ``loss_settle_delay_s`` (30 s) dal gol
         ROSSO   cartellino rosso alla favorita → uscita (``red_card_fav_exit``);
                 rosso alla sfavorita → nessuna azione

  ESATTO (lay "Altro risultato Casa/Ospite" sul Correct Score)
         TIME    al minuto ``esatto_exit_minute`` (72) se il lato bancato non ha segnato
         LOSS    il lato BANCATO segna (es. 1-0 → 2-0), dopo il ritardo di assestamento

  PUNTA  (back della favorita avanti di 2+)
         PROFIT  la favorita segna ancora
         TIME    al minuto ``punta_exit_minute`` (83)
         LOSS    la favorita SUBISCE un gol, anche se resta avanti (dopo il ritardo)

  TENNIS (back del leader sul Match Odds)
         PROFIT  il leader vince il game successivo all'ingresso
                 (``tennis_take_profit_next_game``; False = si tiene fino alla fine)
         LOSS    opzionale, il leader perde il game (``tennis_exit_on_lost_game``)
         OBBLIGO il leader perde DUE game di fila E i game del set corrente sono
                 in parità (es. 3-3) — senza eccezioni; il cambio set azzera il
                 conteggio dei game

  MODEL  (trade di modello/anomalia/combo/tennis-modello, strategia 'model')
         EVENTO AVVERSO  calcio: un gol o un rosso dopo l'ingresso porta la
                 P(perdita) ricalcolata dal modello sopra ``model_exit_p_lose``
                 (0.10) e sopra quella d'ingresso → uscita (dopo il ritardo di
                 assestamento); la linea tradata DECISA contro (O/U, BTTS, CS)
                 → uscita immediata. Tennis: il giocatore puntato perde DUE game
                 di fila o un SET → uscita.
         TAKE-PROFIT  P&L bloccato ≥ ``model_take_profit_frac`` (0.8) × profitto
                 massimo, oppure P(perdita) ≤ ``model_free_cashout_p_lose``
                 (0.005) con P&L bloccato ≥ 0 (cash-out quasi gratis) → uscita;
                 altrimenti si tiene fino al settlement.

Il ritardo di assestamento vale per OGNI uscita innescata da un evento
(gol o rosso): dopo un gol il mercato è sospeso e le quote si riallineano in
qualche decina di secondi — inviare subito la chiusura fallirebbe (live) o
userebbe quote non più vere (paper). Le uscite a TEMPO sono immediate.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

# strategie con regole di uscita automatica del manuale (manual: mai toccata)
EXIT_STRATEGIES = ("base", "esatto", "punta", "tennis")
# strategie di MODELLO (regole a modello: decide_model); il tipo è in meta.kind
MODEL_STRATEGIES = ("model",)

# parametri di default della sezione ``exits`` del control (fusi con l'utente)
DEFAULT_EXIT_PARAMS: dict[str, Any] = {
    "enabled": True,
    "base_exit_minute": 80,          # manuale: 80-83
    "esatto_exit_minute": 72,        # manuale: 70-75
    "punta_exit_minute": 83,
    "loss_settle_delay_s": 30,       # manuale: 20-60 s
    "red_card_fav_exit": True,
    "tennis_take_profit_next_game": True,
    "tennis_exit_on_lost_game": False,
    "exit_max_retries": 3,
    # RESIDUO dopo una chiusura cappata dalla liquidità (fill parziale): si
    # ritenta la chiusura del residuo ogni residual_retry_s, al massimo
    # residual_max_attempts volte (mai mentre una gamba di chiusura è 'pending')
    "residual_retry_s": 20,
    "residual_max_attempts": 15,
    # USCITE IN PROFITTO (a tempo / take-profit) con P&L bloccato < 0: decisione
    # a MODELLO sulla probabilità residua di perdere la posizione (decide_time_exit):
    #   p_lose ≤ hold_max_risk            → si TIENE fino al settlement (margine ampio)
    #   p_lose ≥ risk_cap                 → si ESCE (rischio troppo alto)
    #   locked ≥ ev_hold − ev_margin      → si ESCE (tenere non rende di più)
    # Le uscite in PERDITA (gol subito, rosso, obbligo tennis) restano incondizionate.
    "hold_max_risk": 0.02,
    "risk_cap": 0.10,
    "ev_margin": 0.10,
    # TRADE DI MODELLO (decide_model): evento avverso se P(perdita) > model_exit_p_lose;
    # take-profit a model_take_profit_frac del profitto massimo; cash-out quasi
    # gratis quando P(perdita) <= model_free_cashout_p_lose e P&L bloccato >= 0
    "model_exit_p_lose": 0.10,
    "model_take_profit_frac": 0.8,
    "model_free_cashout_p_lose": 0.005,
}

# tipi di uscita soggetti alla decisione a modello (mai le uscite in perdita)
PROFIT_KINDS = ("profit", "time")

# tipo di uscita per la UI (ExitBadge): 'mandatory' del manuale = 'forced'
EXIT_KIND_UI = {"profit": "profit", "loss": "loss", "time": "time",
                "red_card": "red_card", "mandatory": "forced"}

_REASON_TEXT = {
    "sfavorita_pareggia": "La squadra bancata ha pareggiato: chiusura in perdita",
    "favorita_segna_ancora": "La favorita ha segnato ancora: green-up",
    "rosso_alla_favorita": "Cartellino rosso alla favorita: uscita",
    "lato_bancato_segna": "Il lato bancato ha segnato: chiusura in perdita",
    "favorita_subisce_gol": "La favorita ha subito gol: chiusura in perdita",
    "leader_vince_il_game": "Il leader ha vinto il game: take profit",
    "leader_perde_il_game": "Il leader ha perso il game: uscita",
    "due_game_persi_di_fila_e_parita": "Due game persi di fila e parità nel set: uscita obbligatoria",
    "linea_decisa_contro": "La linea tradata è decisa contro: chiusura in perdita",
    "gol_avverso": "Gol avverso: la probabilità di perdere è salita oltre la soglia, uscita",
    "rosso_avverso": "Cartellino rosso avverso: la probabilità di perdere è salita oltre la soglia, uscita",
    "due_game_persi_di_fila": "Il giocatore puntato ha perso due game di fila: uscita",
    "set_perso": "Il giocatore puntato ha perso un set: uscita",
    "take_profit_modello": "Take profit del modello: profitto bloccato",
    "cashout_quasi_gratis": "Posizione ormai vinta: cash-out quasi gratis, liability liberata",
}
_MINUTE_REASON_RE = re.compile(r"^minuto_(\d+)")

# sotto questo residuo (in stake d'apertura) la posizione è chiusa (= execution.HEDGE_EPS)
RESIDUAL_EPS = 0.01

# freschezza del feed: la riga dell'evento (o l'heartbeat dello scanner) deve
# essere più recente di così, altrimenti si ASPETTA (mai chiudere su dati vecchi)
FEED_FRESH_S = 20.0

TRACK_KEY = "exit_track"          # meta.exit_track: stato del tracciamento
REQUEST_KEY = "exit_requested"    # meta.exit_requested: uscita richiesta/inviata

_SCORE_RE = re.compile(r"(\d+)\s*-\s*(\d+)")
_SET_RE = re.compile(r"set\s*(\d+)\s*-\s*(\d+)", re.IGNORECASE)
_GAME_RE = re.compile(r"game\s*(\d+)\s*-\s*(\d+)", re.IGNORECASE)
_ESATTO_KEY_RE = re.compile(r":esatto:(home|away):")
_HOME_NAME_RE = re.compile(r"casa|home", re.IGNORECASE)
_AWAY_NAME_RE = re.compile(r"ospite|away", re.IGNORECASE)


@dataclass(frozen=True)
class ExitDecision:
    kind: str            # 'profit' | 'loss' | 'time' | 'red_card' | 'mandatory'
    reason: str          # etichetta breve per il log (es. 'favorita_segna_ancora')
    not_before_ts: float  # epoch: non inviare la chiusura prima di questo istante (0 = subito)


# ---------------------------------------------------------------------------
# parametri
# ---------------------------------------------------------------------------
def merge_exit_params(raw: Any) -> dict[str, Any]:
    """Default + override utente, con clamp: minuti interi 1-120, ritardo 0-600 s,
    retry 1-20, residuo (2-600 s, 0-100 tentativi), soglie di rischio 0-1,
    ev_margin ≥ 0 EUR. Chiavi sconosciute ignorate."""
    out = dict(DEFAULT_EXIT_PARAMS)
    if isinstance(raw, dict):
        for k in DEFAULT_EXIT_PARAMS:
            if k in raw and raw[k] is not None:
                out[k] = raw[k]
    for k in ("base_exit_minute", "esatto_exit_minute", "punta_exit_minute"):
        out[k] = int(min(120, max(1, _f(out.get(k), DEFAULT_EXIT_PARAMS[k]))))
    out["loss_settle_delay_s"] = float(min(600.0, max(0.0, _f(out.get("loss_settle_delay_s"), 30.0))))
    out["exit_max_retries"] = int(min(20, max(1, _f(out.get("exit_max_retries"), 3))))
    # residual_retry_s 2-600 s; residual_max_attempts 0 (= mai) - 100
    out["residual_retry_s"] = float(min(600.0, max(2.0, _f(out.get("residual_retry_s"), 20.0))))
    out["residual_max_attempts"] = int(min(100, max(0, _f(out.get("residual_max_attempts"), 15))))
    out["hold_max_risk"] = float(min(1.0, max(0.0, _f(out.get("hold_max_risk"), 0.02))))
    out["risk_cap"] = float(min(1.0, max(0.0, _f(out.get("risk_cap"), 0.10))))
    out["ev_margin"] = float(max(0.0, _f(out.get("ev_margin"), 0.10)))
    out["model_exit_p_lose"] = float(min(1.0, max(0.0, _f(out.get("model_exit_p_lose"), 0.10))))
    out["model_take_profit_frac"] = float(min(1.0, max(0.0, _f(out.get("model_take_profit_frac"), 0.8))))
    out["model_free_cashout_p_lose"] = float(min(1.0, max(0.0, _f(out.get("model_free_cashout_p_lose"), 0.005))))
    for k in ("enabled", "red_card_fav_exit", "tennis_take_profit_next_game",
              "tennis_exit_on_lost_game"):
        out[k] = _bool(out.get(k), DEFAULT_EXIT_PARAMS[k])
    return out


def exit_params(params: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Sezione ``exits`` dei parametri del bot (già fusa o grezza) → completa."""
    return merge_exit_params((params or {}).get("exits"))


def _f(v: Any, default: float) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return float(default)
    return f if f == f else float(default)


def _bool(v: Any, default: bool) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "1", "yes", "si", "sì", "on"):
            return True
        if s in ("false", "0", "no", "off", ""):
            return False
    return default


def _int(v: Any) -> Optional[int]:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)) and v == v:
        return int(v)
    if isinstance(v, str):
        try:
            return int(float(v))
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------
# parsing punteggi
# ---------------------------------------------------------------------------
def parse_calcio_score(s: Any) -> Optional[tuple[int, int]]:
    """'1-0' → (1, 0). None se assente/illeggibile."""
    if s is None:
        return None
    m = _SCORE_RE.search(str(s))
    return (int(m.group(1)), int(m.group(2))) if m else None


def parse_tennis_score(s: Any) -> tuple[Optional[tuple[int, int]], Optional[tuple[int, int]]]:
    """'set 1-0 · game 4-2' → ((1, 0), (4, 2)); ciascuna parte None se assente."""
    if s is None:
        return None, None
    txt = str(s)
    ms, mg = _SET_RE.search(txt), _GAME_RE.search(txt)
    sets = (int(ms.group(1)), int(ms.group(2))) if ms else None
    games = (int(mg.group(1)), int(mg.group(2))) if mg else None
    return sets, games


def _pair(block: Any, a: str, b: str) -> Optional[tuple[int, int]]:
    if not isinstance(block, dict):
        return None
    x, y = _int(block.get(a)), _int(block.get(b))
    return (x, y) if x is not None and y is not None else None


def parse_ts(v: Any) -> Optional[float]:
    """updated_at ISO (o epoch) → epoch secondi; None se illeggibile."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, datetime):
        return v.timestamp()
    if not isinstance(v, str) or not v.strip():
        return None
    try:
        return datetime.fromisoformat(v.strip().replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def feed_is_fresh(row: Optional[dict[str, Any]], now_ts: float,
                  scanner_ts: Optional[float] = None,
                  max_age_s: float = FEED_FRESH_S) -> bool:
    """La riga del feed è utilizzabile per una chiusura: aggiornata da ≤ max_age_s
    OPPURE scanner vivo (heartbeat ≤ max_age_s: la riga non cambia perché non è
    cambiato nulla, non perché il feed è morto)."""
    if not isinstance(row, dict):
        return False
    ts = parse_ts(row.get("updated_at"))
    if ts is not None and now_ts - ts <= max_age_s:
        return True
    return scanner_ts is not None and now_ts - float(scanner_ts) <= max_age_s


def decide_time_exit(p_lose: Optional[float], locked_pnl: Optional[float],
                     hold_profit: float, stake: Any, params: dict[str, Any],
                     *, loss_if_lose: Optional[float] = None) -> tuple[str, str]:
    """Decisione a MODELLO per un'uscita in PROFITTO (a tempo / take-profit):
    ('exit'|'hold', motivo). PURA.

    ``p_lose``      probabilità che la posizione PERDA da qui al settlement
                    (lay: P(selezione vince); back: 1 − P(selezione vince))
    ``locked_pnl``  P&L bloccato dalla chiusura integrale ai prezzi correnti
    ``hold_profit`` P&L se si tiene e la posizione vince (lay: +stake; back: stake·(q−1))
    ``loss_if_lose`` perdita se si tiene e la posizione perde (= liability;
                    default: stake, il caso del back)

    Regole: locked ≥ 0 → EXIT (profitto: come da manuale). Altrimenti
    p_lose ≤ hold_max_risk → HOLD (margine ampio, si tiene fino al settlement);
    p_lose ≥ risk_cap → EXIT; ev_hold = (1−p)·hold_profit − p·loss_if_lose e
    locked ≥ ev_hold − ev_margin → EXIT (tenere non rende di più); altrimenti
    HOLD (si ricontrolla al ciclo successivo). p_lose ignoto → HOLD."""
    if locked_pnl is not None and float(locked_pnl) >= 0.0:
        return "exit", f"profitto bloccato {float(locked_pnl):+.2f} EUR: esco"
    if p_lose is None:
        return "hold", "P(perdita) non stimabile e chiusura in perdita: tengo"
    p = min(1.0, max(0.0, float(p_lose)))
    if p <= float(params.get("hold_max_risk") or 0.0):
        return "hold", f"margine ampio: P(perdita)={p * 100:.1f}%, tengo fino al settlement"
    loss = _f(loss_if_lose, _f(stake, 0.0)) if loss_if_lose is not None else _f(stake, 0.0)
    ev_hold = round((1.0 - p) * float(hold_profit) - p * max(0.0, loss), 2)
    locked = float(locked_pnl) if locked_pnl is not None else None
    if p >= float(params.get("risk_cap") or 1.0):
        return "exit", (f"rischio alto: P(perdita)={p * 100:.1f}% >= "
                        f"{float(params.get('risk_cap') or 1.0) * 100:.0f}%, esco")
    if locked is not None and locked >= ev_hold - float(params.get("ev_margin") or 0.0):
        return "exit", (f"tenere non rende: EV(tengo)={ev_hold:+.2f} EUR vs bloccato "
                        f"{locked:+.2f} EUR, P(perdita)={p * 100:.1f}%, esco")
    return "hold", (f"EV(tengo)={ev_hold:+.2f} EUR > bloccato "
                    f"{locked if locked is None else round(locked, 2):+.2f} EUR, "
                    f"P(perdita)={p * 100:.1f}%: tengo")


def ev_hold(p_lose: float, hold_profit: float, loss_if_lose: float) -> float:
    """Valore atteso del tenere la posizione fino al settlement."""
    p = min(1.0, max(0.0, float(p_lose)))
    return round((1.0 - p) * float(hold_profit) - p * max(0.0, float(loss_if_lose)), 2)


def reason_text(kind: str, reason: str) -> str:
    """Testo italiano per la UI (meta.exit_reason) dal motivo tecnico."""
    r = str(reason or "")
    if r in _REASON_TEXT:
        return _REASON_TEXT[r]
    m = _MINUTE_REASON_RE.match(r)
    if m:
        return f"Uscita a tempo al {m.group(1)}': green-up"
    return r.replace("_", " ").capitalize() if r else str(kind)


def spread_ratio(prices: Optional[dict[str, Any]]) -> Optional[float]:
    """lay/back della selezione dal feed; None se il back manca (o non è > 1)."""
    if not isinstance(prices, dict):
        return None
    back, lay = _f(prices.get("back"), 0.0), _f(prices.get("lay"), 0.0)
    if back <= 1.0 or lay <= 0.0:
        return None
    return round(lay / back, 4)


def market_open(trade: dict[str, Any], payload: Optional[dict[str, Any]]) -> Optional[bool]:
    """Stato del mercato della posizione dal feed: True/False, None = ignoto."""
    if not isinstance(payload, dict):
        return None
    mt = str(trade.get("market_type") or "").upper()
    if mt == "CORRECT_SCORE":
        cs = payload.get("cs")
        st = cs.get("status") if isinstance(cs, dict) else None
    else:
        st = payload.get("mo_status")
    return None if st is None else str(st).upper() == "OPEN"


# ---------------------------------------------------------------------------
# lato della posizione (favorita/leader/lato bancato)
# ---------------------------------------------------------------------------
def _side_by_selection(odds: Any, selection_id: Any, keys: tuple[str, ...]) -> Optional[str]:
    sid = _int(selection_id)
    if sid is None or not isinstance(odds, dict):
        return None
    for k in keys:
        blk = odds.get(k)
        if isinstance(blk, dict) and _int(blk.get("selection_id")) == sid:
            return k
    return None


def _opposite_player(side: Optional[str]) -> Optional[str]:
    return {"p1": "p2", "p2": "p1"}.get(str(side or ""))


def is_tennis(trade: dict[str, Any]) -> bool:
    """Trade di tennis: strategia 'tennis' o sport 'tennis' (trade di modello)."""
    return str(trade.get("strategy") or "") == "tennis" or \
        str(trade.get("sport") or "") == "tennis"


def _opposite(side: Optional[str]) -> Optional[str]:
    if side == "home":
        return "away"
    if side == "away":
        return "home"
    return None


def position_side(trade: dict[str, Any], payload: Optional[dict[str, Any]]) -> Optional[str]:
    """Lato della posizione:
      base  → la FAVORITA ('home'/'away'): la selezione bancata è la sfavorita
      punta → la FAVORITA: la selezione puntata
      esatto → il lato BANCATO ("Altro risultato Casa" → 'home')
      tennis → il LEADER ('p1'/'p2'): la selezione puntata
    Prima dalla selezione (selection_id nel feed), poi dal punteggio d'ingresso
    (la favorita/il leader era avanti all'ingresso per regola)."""
    strategy = str(trade.get("strategy") or "")
    payload = payload if isinstance(payload, dict) else {}
    sid = trade.get("selection_id")
    if strategy in MODEL_STRATEGIES and is_tennis(trade):
        # tennis a modello: il lato è "chi deve vincere" per la posizione: il
        # giocatore della selezione (back) o l'avversario (lay)
        s = _side_by_selection(payload.get("odds"), sid, ("p1", "p2"))
        if s and str(trade.get("side") or "").lower() == "lay":
            return _opposite_player(s)
        return s
    if strategy == "tennis":
        s = _side_by_selection(payload.get("odds"), sid, ("p1", "p2"))
        if s:
            return s
        sets, games = parse_tennis_score(trade.get("score_at_entry"))
        if sets and sets[0] != sets[1]:
            return "p1" if sets[0] > sets[1] else "p2"
        if games and games[0] != games[1]:
            return "p1" if games[0] > games[1] else "p2"
        return None
    if strategy == "esatto":
        cs = payload.get("cs") if isinstance(payload.get("cs"), dict) else {}
        s = _side_by_selection({"home": cs.get("any_other_home"), "away": cs.get("any_other_away")},
                               sid, ("home", "away"))
        if s:
            return s
        m = _ESATTO_KEY_RE.search(str(trade.get("signal_key") or ""))
        if m:
            return m.group(1)
        name = str(trade.get("selection_name") or "")
        if _HOME_NAME_RE.search(name):
            return "home"
        if _AWAY_NAME_RE.search(name):
            return "away"
        return None
    if strategy in ("base", "punta"):
        s = _side_by_selection(payload.get("odds"), sid, ("home", "away"))
        if s:
            return _opposite(s) if strategy == "base" else s
        sc = parse_calcio_score(trade.get("score_at_entry"))
        if sc and sc[0] != sc[1]:
            return "home" if sc[0] > sc[1] else "away"
    return None


# ---------------------------------------------------------------------------
# tracciamento (meta.exit_track)
# ---------------------------------------------------------------------------
def track(trade: dict[str, Any], payload: Optional[dict[str, Any]], now_ts: float) -> dict[str, Any]:
    """Meta AGGIORNATO (copia) con ``exit_track`` allineato al feed corrente.

    Calcio: entry_home/away (dal punteggio d'ingresso, una volta sola), last_home/
    away, goals_since_entry_home/away, last_goal_ts (primo istante in cui il
    nuovo punteggio è stato OSSERVATO), red_home/away + entry_red_*, last_red_ts,
    minute. Tennis: entry_sets/games, last_sets/games, set_index, games_won/
    games_lost (dal leader, da ingresso), consecutive_lost, last_game,
    last_game_ts, games_level. Idempotente: stesso feed → stesso tracciamento."""
    meta = dict(trade.get("meta") or {})
    prev = meta.get(TRACK_KEY)
    tr: dict[str, Any] = dict(prev) if isinstance(prev, dict) else {}
    payload = payload if isinstance(payload, dict) else {}
    strategy = str(trade.get("strategy") or "")
    if not tr.get("side"):
        tr["side"] = position_side(trade, payload)
    if is_tennis(trade):
        _track_tennis(tr, trade, payload, now_ts)
    else:
        _track_calcio(tr, trade, payload, now_ts)
    meta[TRACK_KEY] = tr
    return meta


def _track_calcio(tr: dict[str, Any], trade: dict[str, Any], payload: dict[str, Any],
                  now_ts: float) -> None:
    sh, sa = _int(payload.get("score_home")), _int(payload.get("score_away"))
    if "entry_home" not in tr:
        entry = parse_calcio_score(trade.get("score_at_entry"))
        if entry is None and sh is not None and sa is not None:
            entry = (sh, sa)   # ingresso senza punteggio: base = prima osservazione
        if entry is not None:
            tr["entry_home"], tr["entry_away"] = entry[0], entry[1]
    minute = _int(payload.get("minute"))
    if minute is not None:
        tr["minute"] = minute
    if sh is not None and sa is not None and "entry_home" in tr:
        prev_h, prev_a = tr.get("last_home"), tr.get("last_away")
        base_h = prev_h if prev_h is not None else tr["entry_home"]
        base_a = prev_a if prev_a is not None else tr["entry_away"]
        if (sh, sa) != (base_h, base_a):
            tr["last_goal_ts"] = now_ts
            tr["last_goal_minute"] = minute
        tr["last_home"], tr["last_away"] = sh, sa
        tr["goals_since_entry_home"] = max(0, sh - int(tr["entry_home"]))
        tr["goals_since_entry_away"] = max(0, sa - int(tr["entry_away"]))
    rh, ra = _int(payload.get("red_home")), _int(payload.get("red_away"))
    if rh is not None and ra is not None:
        if "entry_red_home" not in tr:
            tr["entry_red_home"], tr["entry_red_away"] = rh, ra
        prev_rh = tr.get("red_home", tr["entry_red_home"])
        prev_ra = tr.get("red_away", tr["entry_red_away"])
        if (rh, ra) != (prev_rh, prev_ra):
            tr["last_red_ts"] = now_ts
        tr["red_home"], tr["red_away"] = rh, ra


def _track_tennis(tr: dict[str, Any], trade: dict[str, Any], payload: dict[str, Any],
                  now_ts: float) -> None:
    sets = _pair(payload.get("sets"), "p1", "p2")
    games = _pair(payload.get("games"), "p1", "p2")
    if "entry_sets" not in tr:
        e_sets, e_games = parse_tennis_score(trade.get("score_at_entry"))
        if e_sets is None:
            e_sets = sets
        if e_games is None:
            e_games = games
        if e_sets is not None and e_games is not None:
            tr["entry_sets"], tr["entry_games"] = list(e_sets), list(e_games)
            tr.setdefault("games_won", 0)
            tr.setdefault("games_lost", 0)
            tr.setdefault("consecutive_lost", 0)
            tr.setdefault("last_game", None)
    if sets is None or games is None or "entry_sets" not in tr:
        return
    leader = tr.get("side")
    li = 0 if leader == "p1" else 1
    oi = 1 - li
    prev_sets = tuple(tr.get("last_sets") or tr["entry_sets"])
    prev_games = tuple(tr.get("last_games") or tr["entry_games"])
    if leader in ("p1", "p2"):
        if sets != prev_sets:
            # cambio set: l'ultimo game del set è di chi ha vinto il set, poi
            # il conteggio dei game riparte da zero (regola del manuale)
            if sets[li] > prev_sets[li]:
                _game_result(tr, "won", now_ts)
            elif sets[oi] > prev_sets[oi]:
                _game_result(tr, "lost", now_ts)
            tr["consecutive_lost"] = 0
            tr["set_games_won"] = 0
            tr["set_games_lost"] = 0
        elif games != prev_games:
            d_lead = games[li] - prev_games[li]
            d_opp = games[oi] - prev_games[oi]
            if d_lead > 0:
                for _ in range(d_lead):
                    _game_result(tr, "won", now_ts)
            if d_opp > 0:
                for _ in range(d_opp):
                    _game_result(tr, "lost", now_ts)
    tr["last_sets"], tr["last_games"] = list(sets), list(games)
    tr["set_index"] = sets[0] + sets[1]
    tr["games_level"] = games[0] == games[1]


def _game_result(tr: dict[str, Any], result: str, now_ts: float) -> None:
    if result == "won":
        tr["games_won"] = int(tr.get("games_won") or 0) + 1
        tr["set_games_won"] = int(tr.get("set_games_won") or 0) + 1
        tr["consecutive_lost"] = 0
    else:
        tr["games_lost"] = int(tr.get("games_lost") or 0) + 1
        tr["set_games_lost"] = int(tr.get("set_games_lost") or 0) + 1
        tr["consecutive_lost"] = int(tr.get("consecutive_lost") or 0) + 1
    tr["last_game"] = result
    tr["last_game_ts"] = now_ts


# ---------------------------------------------------------------------------
# decisione
# ---------------------------------------------------------------------------
def decide(trade: dict[str, Any], payload: Optional[dict[str, Any]], meta: dict[str, Any],
           now_ts: float, params: dict[str, Any]) -> Optional[ExitDecision]:
    """Regola di uscita applicabile ORA (None = si tiene). ``params`` = sezione
    ``exits`` completa (``exit_params``). Non guarda lo stato del trade né la
    freschezza del feed: se ne occupa il chiamante."""
    if not _bool(params.get("enabled"), True):
        return None
    strategy = str(trade.get("strategy") or "")
    if strategy not in EXIT_STRATEGIES:
        return None
    tr = (meta or {}).get(TRACK_KEY)
    if not isinstance(tr, dict) or not tr.get("side"):
        return None
    if strategy == "tennis":
        return _decide_tennis(tr, params)
    if "entry_home" not in tr or tr.get("last_home") is None:
        return None
    if strategy == "base":
        return _decide_base(tr, params)
    if strategy == "esatto":
        return _decide_esatto(tr, params)
    if strategy == "punta":
        return _decide_punta(tr, params)
    return None


def _after(tr: dict[str, Any], key: str, params: dict[str, Any]) -> float:
    """Istante minimo per un'uscita innescata da un evento: evento + ritardo."""
    ts = tr.get(key)
    delay = float(params.get("loss_settle_delay_s") or 0.0)
    return float(ts) + delay if isinstance(ts, (int, float)) else 0.0


def _calcio_state(tr: dict[str, Any]) -> tuple[int, int, int, int, str]:
    side = str(tr["side"])
    other = "away" if side == "home" else "home"
    cur_s, cur_o = int(tr[f"last_{side}"]), int(tr[f"last_{other}"])
    ent_s, ent_o = int(tr[f"entry_{side}"]), int(tr[f"entry_{other}"])
    return cur_s, cur_o, ent_s, ent_o, other


def _red_to(tr: dict[str, Any], side: str) -> bool:
    cur, ent = tr.get(f"red_{side}"), tr.get(f"entry_red_{side}")
    return isinstance(cur, int) and isinstance(ent, int) and cur > ent


def _decide_base(tr: dict[str, Any], params: dict[str, Any]) -> Optional[ExitDecision]:
    fav, dog, fav_e, dog_e, _ = _calcio_state(tr)
    if fav <= dog:
        return ExitDecision("loss", "sfavorita_pareggia", _after(tr, "last_goal_ts", params))
    if fav > fav_e:
        return ExitDecision("profit", "favorita_segna_ancora", _after(tr, "last_goal_ts", params))
    if _bool(params.get("red_card_fav_exit"), True) and _red_to(tr, str(tr["side"])):
        return ExitDecision("red_card", "rosso_alla_favorita", _after(tr, "last_red_ts", params))
    minute = tr.get("minute")
    if isinstance(minute, int) and minute >= int(params.get("base_exit_minute") or 80):
        return ExitDecision("time", f"minuto_{minute}_senza_altri_gol", 0.0)
    return None


def _decide_esatto(tr: dict[str, Any], params: dict[str, Any]) -> Optional[ExitDecision]:
    laid, _, laid_e, _, _ = _calcio_state(tr)
    if laid > laid_e:
        return ExitDecision("loss", "lato_bancato_segna", _after(tr, "last_goal_ts", params))
    minute = tr.get("minute")
    if isinstance(minute, int) and minute >= int(params.get("esatto_exit_minute") or 72):
        return ExitDecision("time", f"minuto_{minute}_lato_bancato_senza_gol", 0.0)
    return None


def _decide_punta(tr: dict[str, Any], params: dict[str, Any]) -> Optional[ExitDecision]:
    fav, dog, fav_e, dog_e, _ = _calcio_state(tr)
    if dog > dog_e:
        return ExitDecision("loss", "favorita_subisce_gol", _after(tr, "last_goal_ts", params))
    if fav > fav_e:
        return ExitDecision("profit", "favorita_segna_ancora", _after(tr, "last_goal_ts", params))
    minute = tr.get("minute")
    if isinstance(minute, int) and minute >= int(params.get("punta_exit_minute") or 83):
        return ExitDecision("time", f"minuto_{minute}", 0.0)
    return None


def _decide_tennis(tr: dict[str, Any], params: dict[str, Any]) -> Optional[ExitDecision]:
    if "entry_sets" not in tr or tr.get("last_games") is None:
        return None
    consecutive = int(tr.get("consecutive_lost") or 0)
    if consecutive >= 2 and bool(tr.get("games_level")):
        return ExitDecision("mandatory", "due_game_persi_di_fila_e_parita", 0.0)
    last = tr.get("last_game")
    if last == "won" and _bool(params.get("tennis_take_profit_next_game"), True):
        return ExitDecision("profit", "leader_vince_il_game", 0.0)
    if last == "lost" and _bool(params.get("tennis_exit_on_lost_game"), False):
        return ExitDecision("loss", "leader_perde_il_game", 0.0)
    return None


# ---------------------------------------------------------------------------
# TRADE DI MODELLO: situazione (pura) + decisione a numeri (pura)
# ---------------------------------------------------------------------------
_OU_LINE_RE = re.compile(r"(\d+)[._](\d)")
_OVER_RE = re.compile(r"\bover\b", re.IGNORECASE)
_UNDER_RE = re.compile(r"\bunder\b", re.IGNORECASE)
_YES_RE = re.compile(r"^\s*(yes|s[iì])\s*$", re.IGNORECASE)
_NO_RE = re.compile(r"^\s*no\s*$", re.IGNORECASE)
_ANY_OTHER_RE = re.compile(r"any\s*other|altro", re.IGNORECASE)


def ou_line(trade: dict[str, Any]) -> Optional[float]:
    """Linea O/U del trade: meta.line, poi il market_type (OVER_UNDER_25 → 2.5),
    poi il nome della selezione ('Over 2.5 Goals')."""
    meta = trade.get("meta") or {}
    ln = meta.get("line")
    if isinstance(ln, (int, float)) and not isinstance(ln, bool):
        return float(ln)
    for src in (str(trade.get("market_type") or ""), str(trade.get("selection_name") or "")):
        m = _OU_LINE_RE.search(src.replace(" ", ""))
        if m:
            return float(f"{m.group(1)}.{m.group(2)}")
    return None


def line_decided_against(trade: dict[str, Any], sh: Optional[int], sa: Optional[int]) -> bool:
    """True se, col punteggio corrente, la linea tradata è GIÀ decisa contro la
    posizione (nessuna probabilità residua): O/U oltre la linea, BTTS con
    entrambe a segno, CS puntato superato. Mai True per il Match Odds
    (si decide solo al fischio finale)."""
    if sh is None or sa is None:
        return False
    mt = str(trade.get("market_type") or "").upper()
    side = str(trade.get("side") or "").lower()
    name = str(trade.get("selection_name") or "")
    total = int(sh) + int(sa)
    if mt.startswith("OVER_UNDER"):
        line = ou_line(trade)
        if line is None or total <= line:
            return False          # linea ancora viva (o non nota)
        is_under = bool(_UNDER_RE.search(name))
        is_over = bool(_OVER_RE.search(name)) and not is_under
        if not (is_over or is_under):
            return False
        # total > line: vince l'Over → perde chi è sull'Under (back Under / lay Over)
        pos_on_over = (is_over and side == "back") or (is_under and side == "lay")
        return not pos_on_over
    if mt == "BOTH_TEAMS_TO_SCORE":
        if int(sh) >= 1 and int(sa) >= 1:
            pos_on_yes = (bool(_YES_RE.match(name)) and side == "back") or \
                (bool(_NO_RE.match(name)) and side == "lay")
            return not pos_on_yes
        return False
    if mt == "CORRECT_SCORE" and side == "back" and not _ANY_OTHER_RE.search(name):
        cs = parse_calcio_score(name)
        if cs is not None:
            return int(sh) > cs[0] or int(sa) > cs[1]
    return False


def model_situation(trade: dict[str, Any], meta: dict[str, Any], payload: Optional[dict[str, Any]],
                    params: dict[str, Any]) -> dict[str, Any]:
    """Fatti del tracciamento utili alla decisione a modello (PURA):
      adverse_event    'gol' | 'rosso' (calcio, dopo l'ingresso) |
                       'due_game_persi_di_fila' | 'set_perso' (tennis) | None
      not_before_ts    evento + ritardo di assestamento (calcio), 0 altrimenti
      decided_against  linea già decisa contro (calcio)"""
    tr = (meta or {}).get(TRACK_KEY)
    tr = tr if isinstance(tr, dict) else {}
    payload = payload if isinstance(payload, dict) else {}
    out: dict[str, Any] = {"adverse_event": None, "not_before_ts": 0.0, "decided_against": False}
    if is_tennis(trade):
        if "entry_sets" not in tr or tr.get("last_sets") is None:
            return out
        side = tr.get("side")
        oi = 1 if side == "p1" else 0
        last_sets, entry_sets = list(tr.get("last_sets") or []), list(tr.get("entry_sets") or [])
        if side in ("p1", "p2") and len(last_sets) == 2 and len(entry_sets) == 2 \
                and int(last_sets[oi]) > int(entry_sets[oi]):
            out["adverse_event"] = "set_perso"
        elif int(tr.get("consecutive_lost") or 0) >= 2:
            out["adverse_event"] = "due_game_persi_di_fila"
        return out
    sh, sa = _int(payload.get("score_home")), _int(payload.get("score_away"))
    out["decided_against"] = line_decided_against(trade, sh, sa)
    if out["decided_against"]:
        out["not_before_ts"] = _after(tr, "last_goal_ts", params)
    goals = int(tr.get("goals_since_entry_home") or 0) + int(tr.get("goals_since_entry_away") or 0)
    red = _red_to(tr, "home") or _red_to(tr, "away")
    if goals > 0:
        out["adverse_event"] = "gol"
        out["not_before_ts"] = max(out["not_before_ts"], _after(tr, "last_goal_ts", params))
    elif red:
        out["adverse_event"] = "rosso"
        out["not_before_ts"] = max(out["not_before_ts"], _after(tr, "last_red_ts", params))
    return out


def decide_model(*, p_lose: Optional[float], p_lose_entry: Optional[float],
                 locked: Optional[float], max_profit: Optional[float],
                 situation: dict[str, Any], params: dict[str, Any]) -> Optional[ExitDecision]:
    """Decisione a modello per un trade di strategia 'model' (PURA):

      1. linea decisa contro                          → 'loss'  linea_decisa_contro
      2. tennis: due game persi di fila / set perso   → 'loss'  (incondizionata)
      3. calcio: gol/rosso dopo l'ingresso E p_lose > model_exit_p_lose E
         p_lose > p_lose_entry (l'evento è AVVERSO)   → 'loss' | 'red_card'
      4. locked ≥ model_take_profit_frac × max_profit → 'profit' take_profit_modello
      5. p_lose ≤ model_free_cashout_p_lose, locked ≥ 0 → 'profit' cashout_quasi_gratis
      altrimenti None (si tiene fino al settlement)."""
    sit = situation or {}
    nb = float(sit.get("not_before_ts") or 0.0)
    if sit.get("decided_against"):
        return ExitDecision("loss", "linea_decisa_contro", nb)
    ev = sit.get("adverse_event")
    if ev in ("due_game_persi_di_fila", "set_perso"):
        return ExitDecision("loss", str(ev), 0.0)
    if ev in ("gol", "rosso") and p_lose is not None:
        p = float(p_lose)
        thr = float(params.get("model_exit_p_lose") or 0.0)
        worse = p_lose_entry is None or p > float(p_lose_entry) + 1e-9
        if p > thr and worse:
            kind = "red_card" if ev == "rosso" else "loss"
            return ExitDecision(kind, f"{ev}_avverso", nb)
    if locked is not None and max_profit is not None and float(max_profit) > 0:
        frac = float(params.get("model_take_profit_frac") or 0.0)
        if frac > 0 and float(locked) >= frac * float(max_profit) - 1e-9:
            return ExitDecision("profit", "take_profit_modello", 0.0)
    if p_lose is not None and locked is not None and float(locked) >= 0.0 and \
            float(p_lose) <= float(params.get("model_free_cashout_p_lose") or 0.0):
        return ExitDecision("profit", "cashout_quasi_gratis", 0.0)
    return None


# ---------------------------------------------------------------------------
# contesto per il log
# ---------------------------------------------------------------------------
def situation(trade: dict[str, Any], payload: Optional[dict[str, Any]]) -> dict[str, Any]:
    """{'minute','score'} correnti dal feed, per l'activity log."""
    payload = payload if isinstance(payload, dict) else {}
    if is_tennis(trade):
        sets = _pair(payload.get("sets"), "p1", "p2")
        games = _pair(payload.get("games"), "p1", "p2")
        score = None
        if sets is not None:
            score = f"set {sets[0]}-{sets[1]}"
            if games is not None:
                score += f" · game {games[0]}-{games[1]}"
        return {"minute": None, "score": score}
    sh, sa = _int(payload.get("score_home")), _int(payload.get("score_away"))
    return {"minute": _int(payload.get("minute")),
            "score": f"{sh}-{sa}" if sh is not None and sa is not None else None}
