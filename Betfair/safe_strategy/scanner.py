"""scanner.py — logica PURA dello scanner Safe Strategy (testabile senza rete).

Qui vivono le decisioni "di testa": mappatura selezioni, finestre di interesse,
cadenze adattive, congelamento del riferimento pre-KO, firma write-on-change.
Il glue di rete/DB sta in service.py; NESSUNA valutazione di strategia qui
(quella è del motore certificato frontend, lib/safeStrategy.ts).
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# finestre di interesse (minuti EFFETTIVI di gioco, come certificato).
# REGOLA (utente, 09/09): il minuto delle strategie calcio è una SOGLIA
# ("dal 48' in poi"), NON un intervallo chiuso — il tetto lo mettono i range
# quote. Quindi anche qui le finestre sono aperte verso la fine partita:
# prima del 40' lo scanner rallenta per non sprecare peso API Betfair, dal 40'
# in poi resta "caldo" fino al fischio finale.
HOT_MINUTE_FROM = 40
# candidati Correct Score: dal 30' in poi (Omega entra dal 30', la Safe
# Strategy R.E. dal 48') con al massimo 3 gol per lato (le scoreline esplicite
# del mercato arrivano a 3-3: oltre, resta solo "Any Other" e nessuno lava).
# Nessun tetto di minuto. Il CS dei candidati va sul POOL STREAM come il
# MATCH_ODDS (quote al secondo) e viene pubblicato COMPLETO (tutte le
# selezioni): è il feed unico anche per Omega (audit 09/09 sera).
CS_MINUTE_FROM = 30
CS_MAX_GOALS_SIDE = 3
# HALF TIME SCORE (Omega v2, gamba 1T): sotto quote dal 15' finché il 1T è in corso
HT_MINUTE_FROM = 15
HT_MINUTE_TO = 45

# ---------------------------------------------------------------- OPPORTUNITA'
# Mercati "a gol" tenuti sotto quote per il motore opportunità
# (opportunity.py): Over/Under di tutte le linee quotate da Betfair, Gol/NoGol e
# 1X2 del primo tempo. Servono SOLO in-play (prima del kickoff il modello non ha
# nulla da dire su tempo/punteggio) e SOLO per le linee ancora INDECISE: una
# linea già superata non è un'opportunità, è aritmetica.
OU_MARKET_TYPES = (
    "OVER_UNDER_05", "OVER_UNDER_15", "OVER_UNDER_25", "OVER_UNDER_35",
    "OVER_UNDER_45", "OVER_UNDER_55", "OVER_UNDER_65", "OVER_UNDER_75",
)
BTTS_MARKET_TYPE = "BOTH_TEAMS_TO_SCORE"
HT_RESULT_MARKET_TYPE = "HALF_TIME"          # 1X2 all'intervallo
OPP_MARKET_TYPES = OU_MARKET_TYPES + (BTTS_MARKET_TYPE, HT_RESULT_MARKET_TYPE)
OPP_MINUTE_FROM = 1
# tetto di eventi con i mercati opportunità sotto quote: 10 mercati per evento
# pesano sul pool stream (180/connessione) e sul poll REST di fallback. I posti
# vanno ai minuti più avanzati (dove le probabilità sono davvero estreme).
OPP_MAX_EVENTS = 20

_OU_LINE_RE = re.compile(r"OVER_UNDER_(\d)(\d)$", re.IGNORECASE)
# cattura pre-KO: da KO-15' fino al kickoff
PRE_KO_WINDOW_SEC = 15 * 60
# ------------------------------------------------------- RAMO PRE-KO O/U (Mike)
# Le DUE linee a gol tenute sotto quote PRIMA del calcio d'inizio per il bot Mike
# (Under 3.5 / Over 4.5): stesso ciclo di vita dei mercati opportunità (catalogo
# per i candidati nuovi, quote dal pool stream con priorità tier 2, REST di
# fallback) ma SENZA requisito di minuto/punteggio. Acceso SOLO se
# ``SAFE_PRE_KO_OU_HOURS`` > 0 (service.py): a 0 nulla cambia nel feed.
PRE_KO_OU_MARKET_TYPES = ("OVER_UNDER_35", "OVER_UNDER_45")


def in_pre_ko_ou_window(open_date: Optional[str], now: datetime, hours: float) -> bool:
    """KO fra ``now`` e ``now + hours`` (hours <= 0 = ramo spento)."""
    if hours is None or float(hours) <= 0.0:
        return False
    ko = parse_iso(open_date)
    if ko is None:
        return False
    delta = (ko - now).total_seconds()
    return 0 < delta <= float(hours) * 3600.0


def is_pre_ko_ou_candidate(
    inplay: Optional[bool], mo_status: Optional[str], open_date: Optional[str],
    now: datetime, hours: float,
) -> bool:
    """Evento calcio NON ancora iniziato con KO entro ``hours``: le sue linee
    O/U 3.5 e 4.5 vanno sotto quote (ramo pre-KO Mike)."""
    if inplay or mo_status == "CLOSED":
        return False
    return in_pre_ko_ou_window(open_date, now, hours)

_ANY_OTHER_HOME = re.compile(r"any\s*other.*home", re.IGNORECASE)
_ANY_OTHER_AWAY = re.compile(r"any\s*other.*away", re.IGNORECASE)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def best_price(levels: Any) -> Optional[float]:
    try:
        return float(levels[0].price) if levels else None
    except Exception:  # noqa: BLE001 - struttura inattesa = prezzo assente
        return None


def best_size(levels: Any) -> Optional[float]:
    """Importo (EUR) disponibile al MIGLIOR prezzo: è quanto si può abbinare
    SUBITO a quella quota (best offers, livello 0)."""
    try:
        return round(float(levels[0].size), 2) if levels else None
    except Exception:  # noqa: BLE001
        return None


def price_pair(ex: Any) -> Dict[str, Optional[float]]:
    """Coppia back/lay al miglior prezzo con le size abbinabili, da un runner.ex
    (poll REST o stream, stessa forma betfairlightweight)."""
    atb = getattr(ex, "available_to_back", None) if ex else None
    atl = getattr(ex, "available_to_lay", None) if ex else None
    return {
        "back": best_price(atb),
        "lay": best_price(atl),
        "back_size": best_size(atb),
        "lay_size": best_size(atl),
    }


def selection_sides(runners: List[Dict[str, Any]]) -> Dict[str, Optional[int]]:
    """Mappa home/away/draw → selection_id dal catalogo MATCH_ODDS calcio.

    Regola Betfair: sort_priority 1 = casa, 2 = trasferta, 3 = pareggio.
    Fallback sul nome 'The Draw' se i sort mancano.
    """
    by_sort: Dict[int, int] = {}
    draw_by_name: Optional[int] = None
    for r in runners:
        sid = r.get("selection_id")
        if sid is None:
            continue
        sp = r.get("sort_priority")
        if isinstance(sp, int):
            by_sort[sp] = int(sid)
        name = str(r.get("name") or "").strip().lower()
        if name == "the draw":
            draw_by_name = int(sid)
    return {
        "home": by_sort.get(1),
        "away": by_sort.get(2),
        "draw": by_sort.get(3, draw_by_name),
    }


def tennis_sides(runners: List[Dict[str, Any]]) -> Dict[str, Optional[int]]:
    """p1/p2 → selection_id (sort_priority 1/2) dal catalogo MATCH_ODDS tennis."""
    by_sort: Dict[int, int] = {}
    for r in runners:
        sid = r.get("selection_id")
        sp = r.get("sort_priority")
        if sid is not None and isinstance(sp, int):
            by_sort[sp] = int(sid)
    return {"p1": by_sort.get(1), "p2": by_sort.get(2)}


def split_event_name(event_name: Optional[str]) -> "tuple[Optional[str], Optional[str]]":
    """'Casa v Ospite' → (Casa, Ospite); None se la forma non è riconoscibile."""
    if not event_name:
        return None, None
    for sep in (" v ", " vs ", " @ "):
        if sep in event_name:
            a, b = event_name.split(sep, 1)
            return a.strip() or None, b.strip() or None
    return None, None


def is_hot_minute(minute: Optional[int]) -> bool:
    """Minuto 'caldo' per le strategie calcio: dalla soglia HOT_MINUTE_FROM in poi."""
    return minute is not None and minute >= HOT_MINUTE_FROM


def is_cs_candidate(minute: Optional[int], score_home: Optional[int], score_away: Optional[int]) -> bool:
    """Evento per cui vale la pena tenere sotto quote il Correct Score:
    dal 30' in poi (soglia aperta) con max 3 gol per lato."""
    if minute is None or score_home is None or score_away is None:
        return False
    if minute < CS_MINUTE_FROM:
        return False
    return score_home <= CS_MAX_GOALS_SIDE and score_away <= CS_MAX_GOALS_SIDE


def in_pre_ko_window(open_date: Optional[str], now: datetime) -> bool:
    ko = parse_iso(open_date)
    if ko is None:
        return False
    delta = (ko - now).total_seconds()
    return 0 < delta <= PRE_KO_WINDOW_SEC


def is_monitorable(
    inplay: bool, open_date: Optional[str], now: datetime, pre_ko_ou_hours: float = 0.0,
) -> bool:
    """Riga da pubblicare: evento in-play, KO entro la finestra pre-KO, oppure
    (ramo pre-KO O/U acceso) KO entro ``pre_ko_ou_hours``."""
    return (
        inplay
        or in_pre_ko_window(open_date, now)
        or in_pre_ko_ou_window(open_date, now, pre_ko_ou_hours)
    )


# mercati per cui servono QUOTE (stream o REST): in-play, oppure KO entro
# questa finestra (copre la cattura pre-KO da KO-15' con margine), oppure KO
# già passato ma stato ancora ignoto (nessun book visto: probabilmente in-play).
# Tutto il resto del catalogo (KO lontano) non ha bisogno di quote: così lo
# stream (cap 180 mercati) e il poll REST servono solo ciò che conta.
RELEVANT_PRE_KO_SEC = 20 * 60


def is_relevant_market(
    inplay: Optional[bool],
    mo_status: Optional[str],
    open_date: Optional[str],
    now: datetime,
) -> bool:
    """True se il mercato va tenuto sotto quote adesso (vedi RELEVANT_PRE_KO_SEC)."""
    if mo_status == "CLOSED":
        return False
    if inplay:
        return True
    ko = parse_iso(open_date)
    if ko is None:
        return inplay is None  # senza orario: solo finché non sappiamo nulla
    return (ko - now).total_seconds() <= RELEVANT_PRE_KO_SEC


def rank_key(inplay: Optional[bool], open_date: Optional[str]) -> "tuple[int, str]":
    """Ordine di priorità per il cap dello stream: in-play prima, poi per KO."""
    return (0 if inplay else 1, str(open_date or ""))


def freeze_pre_ko(
    prev: Optional[Dict[str, Any]],
    inplay: bool,
    odds: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Riferimento 1X2 pre-KO: si AGGIORNA solo prima del kickoff (closing line),
    si CONGELA per sempre al primo tick in-play. Mai quote in-play nel riferimento.
    """
    if inplay:
        return prev
    if not odds:
        return prev
    triple = {}
    for side in ("home", "draw", "away"):
        pair = odds.get(side) or {}
        back = pair.get("back")
        if not isinstance(back, (int, float)):
            return prev  # riferimento solo se il 1X2 è completo
        triple[side] = float(back)
    return {**triple, "captured_at": now_iso()}


def books_period_calcio(any_inplay: bool, any_hot: bool) -> float:
    """Cadenza (s) del poll quote MATCH_ODDS calcio: fitta solo quando serve."""
    if any_hot:
        return 10.0
    if any_inplay:
        return 20.0
    return 60.0


def books_period_tennis(any_inplay: bool) -> float:
    return 10.0 if any_inplay else 60.0


def payload_signature(payload: Dict[str, Any]) -> str:
    """Firma stabile del payload per il write-on-change (niente updated_at qui)."""
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.md5(canon.encode("utf-8")).hexdigest()


def is_ht_candidate(minute: Optional[int]) -> bool:
    """Evento per cui vale la pena tenere sotto quote il HALF TIME SCORE:
    primo tempo in corso, dal 15' al 45' (poi il mercato si regola)."""
    return minute is not None and HT_MINUTE_FROM <= minute < HT_MINUTE_TO


# campi "critici": un loro cambio va pubblicato SUBITO, saltando il throttle
# per-evento pensato per le sole quote (gol, minuto, rossi, stato mercato,
# in-play, set/game; per il CS lo stato del mercato). Le quote da sole aspettano.
_CRITICAL_CALCIO = ("inplay", "mo_status", "minute", "score_home", "score_away", "red_home", "red_away")
_CRITICAL_TENNIS = ("inplay", "mo_status", "sets", "games")


def _opp_blocks(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """I blocchi opportunità del payload (ou + btts + ht_result), in ordine stabile."""
    out: List[Dict[str, Any]] = [b for b in (payload.get("ou") or []) if isinstance(b, dict)]
    for key in ("btts", "ht_result"):
        b = payload.get(key)
        if isinstance(b, dict):
            out.append(b)
    return out


def critical_signature(sport: str, payload: Dict[str, Any]) -> str:
    keys = _CRITICAL_CALCIO if sport == "calcio" else _CRITICAL_TENNIS
    crit: Dict[str, Any] = {k: payload.get(k) for k in keys}
    if sport == "calcio":
        cs = payload.get("cs") or {}
        crit["cs_status"] = cs.get("status") if isinstance(cs, dict) else None
        ht = payload.get("ht") or {}
        crit["ht_status"] = ht.get("status") if isinstance(ht, dict) else None
        # mercati opportunità: un cambio di STATO (sospensione, chiusura) va
        # pubblicato subito come per CS/HT — le quote da sole aspettano il throttle
        crit["opp_status"] = [
            [b.get("market_id"), b.get("status")]
            for b in _opp_blocks(payload)
        ]
    # lo stato IPS grezzo è il feed dei runner (punti tennis, corner/cartellini
    # calcio): ogni suo cambio va pubblicato subito, come un gol
    crit["score_raw"] = payload.get("score_raw")
    return json.dumps(crit, sort_keys=True, separators=(",", ":"), default=str)


# campi dello stato IPS che cambiano OGNI secondo senza informazione utile
# (il minuto è già in `timeElapsed`): tolti dal payload per non riscrivere la
# riga a ogni poll. I parser dei runner li usano solo come fallback.
_VOLATILE_STATE_KEYS = ("timeElapsedSeconds",)


def strip_volatile_state(state: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Copia dello stato IPS senza i campi al secondo. None resta None."""
    if not isinstance(state, dict):
        return None
    return {k: v for k, v in state.items() if k not in _VOLATILE_STATE_KEYS}


def num_or_none(v: Any) -> Optional[float]:
    """float da un valore numerico, None se assente/malformato."""
    return float(v) if isinstance(v, (int, float)) else None


def media_flags(broadcasts: Optional[Dict[str, Any]]) -> Dict[str, Optional[bool]]:
    """Disponibilità media Betfair per l'evento dal blocco `broadcasts` dell'IPS
    scoresAndBroadcast (lo stesso che usa il sito per mostrare/nascondere le
    icone): video live (`isLiveVideoAvailable`) e animazione+statistiche
    (`isDataVisualizationAvailable`). None = dato non esposto, MAI inventato."""
    if not isinstance(broadcasts, dict):
        return {"video": None, "viz": None}

    def flag(key: str) -> Optional[bool]:
        v = broadcasts.get(key)
        return v if isinstance(v, bool) else None

    return {"video": flag("isLiveVideoAvailable"), "viz": flag("isDataVisualizationAvailable")}


def build_market_block(
    market_id: Optional[str],
    status: Optional[str],
    selections: List[Dict[str, Any]],
    inplay: Optional[bool] = None,
    total_matched: Optional[float] = None,
    *,
    market_type: Optional[str] = None,
    line: Optional[float] = None,
    ts_ms: Optional[int] = None,
    bet_delay: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Blocco GENERICO di un mercato nel payload: stato + elenco COMPLETO delle
    selezioni (selection_id, nome, best back/lay con le size abbinabili, stato
    runner). È la forma unica usata da Correct Score (Omega) e dai mercati a gol
    del motore opportunità: un solo builder, un solo formato da leggere.

    ``market_type``/``line``/``ts_ms`` finiscono nel blocco SOLO se valorizzati,
    così il blocco `cs` storico resta byte-identico a prima.
    """
    if market_id is None:
        return None
    full: List[Dict[str, Any]] = []
    for s in selections:
        if s.get("selection_id") is None:
            continue
        full.append({
            "selection_id": int(s["selection_id"]),
            "name": str(s.get("name") or ""),
            "runner_status": s.get("runner_status"),
            "back": s.get("back"), "lay": s.get("lay"),
            "back_size": s.get("back_size"), "lay_size": s.get("lay_size"),
        })
    blk: Dict[str, Any] = {
        "market_id": market_id,
        "status": status,
        "inplay": inplay,
        "total_matched": total_matched,
        "selections": full,
    }
    if market_type is not None:
        blk["market_type"] = market_type
    if line is not None:
        blk["line"] = float(line)
    if ts_ms is not None:
        blk["ts_ms"] = int(ts_ms)
    if bet_delay is not None:
        # betDelay del marketDefinition (0 pre-match, ~5s in-play calcio): serve a
        # chi simula i fill in paper con lo stesso ritardo del live (Mike)
        blk["bet_delay"] = int(bet_delay)
    return blk


def build_cs_block(
    market_id: Optional[str],
    status: Optional[str],
    selections: List[Dict[str, Any]],
    inplay: Optional[bool] = None,
    total_matched: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Blocco Correct Score del payload: le selezioni 'Any Other …' (Safe
    Strategy R.E.) E l'elenco COMPLETO delle selezioni con selection_id, nome,
    best back/lay + size e stato runner — è ciò su cui piazza Omega, che così
    legge il book dal feed (stream) invece di rifare listMarketBook a ogni ciclo."""
    blk = build_market_block(market_id, status, selections, inplay, total_matched)
    if blk is None:
        return None
    any_home = any_away = None
    for s in selections:
        name = str(s.get("name") or "")
        pair = {
            "back": s.get("back"), "lay": s.get("lay"),
            "back_size": s.get("back_size"), "lay_size": s.get("lay_size"),
        }
        if _ANY_OTHER_HOME.search(name):
            any_home = pair
        elif _ANY_OTHER_AWAY.search(name):
            any_away = pair
    blk["any_other_home"] = any_home
    blk["any_other_away"] = any_away
    return blk


# ------------------------------------------------------- mercati opportunità
def ou_line_from_market_type(market_type: Optional[str]) -> Optional[float]:
    """'OVER_UNDER_25' → 2.5, 'OVER_UNDER_05' → 0.5. None se non è un O/U."""
    if not market_type:
        return None
    m = _OU_LINE_RE.match(str(market_type).strip())
    return float(f"{m.group(1)}.{m.group(2)}") if m else None


def is_opp_candidate(inplay: Optional[bool], minute: Optional[int]) -> bool:
    """Evento per cui tenere sotto quote i mercati a gol del motore opportunità:
    partita IN CORSO dal 1' (prima non c'è nessuno stato live da valutare)."""
    return bool(inplay) and minute is not None and minute >= OPP_MINUTE_FROM


def is_ht_result_candidate(minute: Optional[int]) -> bool:
    """1X2 primo tempo (HALF_TIME): utile solo finché il 1T è in corso."""
    return minute is not None and OPP_MINUTE_FROM <= minute < HT_MINUTE_TO


def is_live_ou_line(line: Optional[float], score_home: Optional[int], score_away: Optional[int]) -> bool:
    """Linea Over/Under ancora INDECISA: i gol già segnati non l'hanno superata.
    Superata = esito certo (Over vinto, Under perso): nessuna opportunità."""
    if line is None or score_home is None or score_away is None:
        return False
    return float(line) > int(score_home) + int(score_away)


def is_live_btts(score_home: Optional[int], score_away: Optional[int]) -> bool:
    """Gol/NoGol ancora indeciso: appena segnano entrambe l'esito è certo."""
    if score_home is None or score_away is None:
        return False
    return not (int(score_home) >= 1 and int(score_away) >= 1)


def opp_rank_key(minute: Optional[int], open_date: Optional[str]) -> "tuple[int, int, str]":
    """Priorità dei mercati opportunità nel pool stream: SEMPRE dopo i mercati
    core (rank_key restituisce tier 0/1, qui il tier è 2) e, tra loro, prima i
    minuti più avanzati — è lì che le probabilità diventano estreme."""
    return (2, -(minute or 0), str(open_date or ""))


def is_opp_market_live(
    market_type: Optional[str],
    line: Optional[float],
    minute: Optional[int],
    score_home: Optional[int],
    score_away: Optional[int],
    pre_ko: bool = False,
) -> bool:
    """Il mercato opportunità serve ADESSO? (linea indecisa / 1T in corso).

    ``pre_ko=True`` (ramo Mike, evento non iniziato): vive SOLO una delle due
    linee ``PRE_KO_OU_MARKET_TYPES`` — senza punteggio nessuna linea è decisa."""
    mt = (market_type or "").upper()
    if pre_ko:
        return mt in PRE_KO_OU_MARKET_TYPES
    if mt.startswith("OVER_UNDER"):
        return is_live_ou_line(line, score_home, score_away)
    if mt == BTTS_MARKET_TYPE:
        return is_live_btts(score_home, score_away)
    if mt == HT_RESULT_MARKET_TYPE:
        return is_ht_result_candidate(minute)
    return False


def split_opportunity_blocks(blocks: Optional[Dict[str, Dict[str, Any]]]) -> Dict[str, Any]:
    """{market_id: blocco} → {'ou': [...ordinati per linea], 'btts': …, 'ht_result': …}
    (le tre chiavi ADDITIVE del payload calcio). Valori None se il mercato non c'è."""
    ou: List[Dict[str, Any]] = []
    btts = ht_result = None
    for blk in (blocks or {}).values():
        if not isinstance(blk, dict):
            continue
        mt = str(blk.get("market_type") or "").upper()
        if mt.startswith("OVER_UNDER"):
            ou.append(blk)
        elif mt == BTTS_MARKET_TYPE:
            btts = blk
        elif mt == HT_RESULT_MARKET_TYPE:
            ht_result = blk
    ou.sort(key=lambda b: b.get("line") or 0.0)
    return {"ou": ou or None, "btts": btts, "ht_result": ht_result}
