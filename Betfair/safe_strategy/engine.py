# -*- coding: utf-8 -*-
"""engine.py - MOTORE PURO della SAFE STRATEGY lato server (port fedele del
motore TypeScript ``frontend/src/lib/safeStrategy.ts``).

Perche' esiste: la sezione web valuta le 4 strategie nel browser
(SafeStrategyProvider + safeStrategy.ts). I bot/servizi Python hanno bisogno
delle STESSE identiche decisioni senza un browser aperto: questo modulo
riproduce, riga per riga, la semantica del motore TS e la pipeline del provider
(tracker di stabilita' punteggio anti-blip, riconciliazione segnali).

Regole portate INVARIATE dal TS (mai "migliorate" qui):
  * il minuto e' una SOGLIA ("dal 48' in poi"), mai un intervallo chiuso;
  * ``state_from_checks``: false vince su null, null vince su true
    (nessun segnale su dato mancante: mai un falso positivo);
  * mercato tradabile: ``mo_status``/``cs.status`` assente = ignoto (n/d),
    non "aperto" (semantica dello SCANNER, diversa dagli snapshot legacy);
  * cartellini rossi: check ENFORCED solo quando il dato c'e', altrimenti
    saltato (l'assenza del dato non e' l'assenza di rossi);
  * esclusioni tennis (doppi / competizioni) e bande quote d'ingresso.

NESSUN I/O: solo funzioni pure + una classe che conserva lo stato tra le
chiamate (tracker di stabilita' e segnali attivi). Input = le righe
``safe_strategy_scan`` prodotte da ``service.build_rows``.

Differenze DICHIARATE rispetto al TS (nessuna e' un cambio di semantica):
  * ``DEFAULT_PARAMS`` ha una sezione IN PIU', ``stake`` (laySize/backSize):
    serve a ``Signal.size``, lo stake operativo che il TS non ha (la UI non
    piazza ordini). Le 4 sezioni base/esatto/punta/tennis sono identiche al TS.
  * ``Signal`` porta anche market_id / selection_id / market_type: chi opera
    server-side deve poter piazzare l'ordine senza rileggere il catalogo.

I caratteri tipografici del TS (minuto 58', >=, EUR, separatori) sono raccolti
in costanti in cima al modulo: le stringhe prodotte a runtime sono IDENTICHE a
quelle del motore web, byte per byte.
"""
from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

# ------------------------------------------------------------ caratteri speciali
PRIME = "′"      # minuto: 58'
GEQ = "≥"        # >=
RSQUO = "’"      # apostrofo tipografico
EGRAVE = "è"     # e accentata
IGRAVE = "ì"     # i accentata (il "si" affermativo)
EURO = "€"
MIDDOT = "·"     # separatore
NDASH = "–"      # range quote (1.4-1.8) e separatore squadre
EMDASH = "—"     # placeholder nome mancante
SI = "s" + IGRAVE     # "si" affermativo dei check

SPORT_CALCIO = "calcio"
SPORT_TENNIS = "tennis"

# ------------------------------------------------------------------- helper base


def is_finite_number(v: Any) -> bool:
    """typeof v === 'number' && Number.isFinite(v) (i bool NON sono numeri)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    return math.isfinite(v)


def num_or_none(v: Any) -> Optional[float]:
    return float(v) if is_finite_number(v) else None


def _int_or_none(v: Any) -> Optional[int]:
    """intero da un valore numerico gia' validato (o da una stringa numerica)."""
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _int_field(v: Any) -> Optional[int]:
    """campo numerico del payload -> int, None se assente/non numerico."""
    return _int_or_none(v) if is_finite_number(v) else None


def _to_fixed(v: float, digits: int) -> str:
    """Number.prototype.toFixed: half-up sul valore binario ESATTO, come JS."""
    quant = Decimal(1).scaleb(-digits)
    return str(Decimal(v).quantize(quant, rounding=ROUND_HALF_UP))


def js_num(v: Any) -> str:
    """Interpolazione JS di un numero: 4.0 -> "4" (in JS ogni numero e' double,
    quindi 4 e 4.0 stampano identici: le label restano stabili)."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        if math.isfinite(v) and v.is_integer() and abs(v) < 1e21:
            return str(int(v))
        return repr(v)
    return str(v)


def fmt_odds(v: Optional[float]) -> str:
    return _to_fixed(v, 2) if is_finite_number(v) else "n/d"


def fmt_eur(v: Optional[float]) -> Optional[str]:
    """importo EUR abbinabile, compatto (es. "<euro>152", "<euro>41.26")."""
    if not is_finite_number(v):
        return None
    body = _to_fixed(v, 0) if float(v).is_integer() else _to_fixed(v, 2)
    return f"{EURO}{body}"


def fmt_odds_with_size(odds: Optional[float], size: Optional[float]) -> str:
    """quota + size abbinabile per la checklist (es. "8.40 . <euro>120 abbinabili")."""
    eur = fmt_eur(size)
    return fmt_odds(odds) if eur is None else f"{fmt_odds(odds)} {MIDDOT} {eur} abbinabili"


def size_or_none(v: Optional[float]) -> Optional[float]:
    return float(v) if is_finite_number(v) else None


def fmt_minute(minute: Optional[int]) -> str:
    return "n/d" if minute is None else f"{js_num(minute)}{PRIME}"


_SCORELINE_RE = re.compile(r"^\s*(\d{1,2})\s*-\s*(\d{1,2})\s*$")


def parse_scoreline(s: Any) -> Optional[Tuple[int, int]]:
    """"2-1" -> (2,1); None se malformato."""
    if not isinstance(s, str):
        return None
    m = _SCORELINE_RE.match(s)
    return (int(m.group(1)), int(m.group(2))) if m else None


def score_in_list_oriented(scores: Sequence[str], a: int, b: int) -> bool:
    """true se (a,b) compare nella lista COME ORIENTATO (primo numero = a)."""
    for s in scores:
        p = parse_scoreline(s)
        if p is not None and p[0] == a and p[1] == b:
            return True
    return False


def score_in_list_any_order(scores: Sequence[str], a: int, b: int) -> bool:
    """true se {a,b} compare nella lista in QUALSIASI orientamento."""
    for s in scores:
        p = parse_scoreline(s)
        if p is not None and ((p[0] == a and p[1] == b) or (p[0] == b and p[1] == a)):
            return True
    return False


def in_range(v: float, vmin: float, vmax: float) -> bool:
    return vmin <= v <= vmax


# ------------------------------------------------------------------- parametri
DEFAULT_PARAMS: Dict[str, Any] = {
    "base": {
        "minuteMin": 55,
        "scores": ["1-0", "2-1", "2-0"],
        "favPreMin": 1.4,
        "favPreMax": 1.8,
        "dogPreMin": 4,
        "dogPreMax": 8,
        "favLiveMin": 1.2,
        "favLiveMax": 1.34,
        "scoreConfirmSec": 30,
    },
    "esatto": {
        "minuteMin": 48,
        "scores": ["0-0", "1-0", "1-1", "2-1"],
        "maxGoalsLaySide": 1,
        "entryMin": 30,
        "entryMax": 70,
        "scoreConfirmSec": 30,
    },
    "punta": {
        "minuteMin": 66,
        "scores": ["2-0", "3-1", "3-0"],
        "entryMin": 1.03,
        "entryMax": 1.1,
        "minMinutesAfterGoal": 3,
    },
    "tennis": {
        "setsLeadMin": 1,
        "gamesLeadMin": 2,
        "backMin": 1.01,
        "backMax": 1.1,
        "excludeDoubles": True,
        # vuoto di default: il filtro per nome torneo non distingue tabellone
        # maschile/femminile - la lista la compila l'utente.
        "excludeCompetitions": [],
        "scoreConfirmSec": 15,
    },
    # EXTRA rispetto al TS: stake operativo dei segnali (il motore web non
    # piazza ordini, il server si). Minimo Betfair = 2 EUR.
    "stake": {"laySize": 2.0, "backSize": 2.0},
}

VARIANT_META: Dict[str, Dict[str, str]] = {
    "base": {"num": "1", "label": f"Calcio {MIDDOT} Base", "sport": SPORT_CALCIO, "short": "BASE"},
    "esatto": {
        "num": "2",
        "label": f"Calcio {MIDDOT} Risultato Esatto",
        "sport": SPORT_CALCIO,
        "short": "RIS. ESATTO",
    },
    "punta": {
        "num": "3",
        "label": f"Calcio {MIDDOT} Variante Punta",
        "sport": SPORT_CALCIO,
        "short": "PUNTA",
    },
    "tennis": {"num": "4", "label": "Tennis", "sport": SPORT_TENNIS, "short": "TENNIS"},
}


def _num(v: Any, fallback: Any) -> Any:
    return v if is_finite_number(v) else fallback


def _bool(v: Any, fallback: bool) -> bool:
    return v if isinstance(v, bool) else fallback


def _score_list(v: Any, fallback: List[str]) -> List[str]:
    if not isinstance(v, (list, tuple)):
        return list(fallback)
    out = [s for s in v if isinstance(s, str) and parse_scoreline(s) is not None]
    return out if out else list(fallback)


def _keyword_list(v: Any, fallback: List[str]) -> List[str]:
    if not isinstance(v, (list, tuple)):
        return list(fallback)
    return [s.strip().lower() for s in v if isinstance(s, str) and s.strip()]


def _section(p: Dict[str, Any], key: str) -> Dict[str, Any]:
    sec = p.get(key)
    return sec if isinstance(sec, dict) else {}


def merge_params(params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Merge DIFENSIVO di parametri parziali sui default: qualsiasi campo
    assente/malformato torna al default. Non lancia mai (port di mergeParams)."""
    p = params if isinstance(params, dict) else {}
    d = DEFAULT_PARAMS
    b, e = _section(p, "base"), _section(p, "esatto")
    u, t = _section(p, "punta"), _section(p, "tennis")
    st = _section(p, "stake")
    return {
        "base": {
            "minuteMin": _num(b.get("minuteMin"), d["base"]["minuteMin"]),
            "scores": _score_list(b.get("scores"), d["base"]["scores"]),
            "favPreMin": _num(b.get("favPreMin"), d["base"]["favPreMin"]),
            "favPreMax": _num(b.get("favPreMax"), d["base"]["favPreMax"]),
            "dogPreMin": _num(b.get("dogPreMin"), d["base"]["dogPreMin"]),
            "dogPreMax": _num(b.get("dogPreMax"), d["base"]["dogPreMax"]),
            "favLiveMin": _num(b.get("favLiveMin"), d["base"]["favLiveMin"]),
            "favLiveMax": _num(b.get("favLiveMax"), d["base"]["favLiveMax"]),
            "scoreConfirmSec": _num(b.get("scoreConfirmSec"), d["base"]["scoreConfirmSec"]),
        },
        "esatto": {
            "minuteMin": _num(e.get("minuteMin"), d["esatto"]["minuteMin"]),
            "scores": _score_list(e.get("scores"), d["esatto"]["scores"]),
            "maxGoalsLaySide": _num(e.get("maxGoalsLaySide"), d["esatto"]["maxGoalsLaySide"]),
            "entryMin": _num(e.get("entryMin"), d["esatto"]["entryMin"]),
            "entryMax": _num(e.get("entryMax"), d["esatto"]["entryMax"]),
            "scoreConfirmSec": _num(e.get("scoreConfirmSec"), d["esatto"]["scoreConfirmSec"]),
        },
        "punta": {
            "minuteMin": _num(u.get("minuteMin"), d["punta"]["minuteMin"]),
            "scores": _score_list(u.get("scores"), d["punta"]["scores"]),
            "entryMin": _num(u.get("entryMin"), d["punta"]["entryMin"]),
            "entryMax": _num(u.get("entryMax"), d["punta"]["entryMax"]),
            "minMinutesAfterGoal": _num(
                u.get("minMinutesAfterGoal"), d["punta"]["minMinutesAfterGoal"]
            ),
        },
        "tennis": {
            "setsLeadMin": _num(t.get("setsLeadMin"), d["tennis"]["setsLeadMin"]),
            "gamesLeadMin": _num(t.get("gamesLeadMin"), d["tennis"]["gamesLeadMin"]),
            "backMin": _num(t.get("backMin"), d["tennis"]["backMin"]),
            "backMax": _num(t.get("backMax"), d["tennis"]["backMax"]),
            "excludeDoubles": _bool(t.get("excludeDoubles"), d["tennis"]["excludeDoubles"]),
            "excludeCompetitions": _keyword_list(
                t.get("excludeCompetitions"), d["tennis"]["excludeCompetitions"]
            ),
            "scoreConfirmSec": _num(t.get("scoreConfirmSec"), d["tennis"]["scoreConfirmSec"]),
        },
        "stake": {
            # accettato sia annidato in "stake" sia al livello superiore
            "laySize": _num(st.get("laySize"), _num(p.get("laySize"), d["stake"]["laySize"])),
            "backSize": _num(st.get("backSize"), _num(p.get("backSize"), d["stake"]["backSize"])),
        },
    }


# ----------------------------------------------------------------- tipi motore
@dataclass(frozen=True)
class OddsPair:
    back: Optional[float] = None
    lay: Optional[float] = None
    back_size: Optional[float] = None
    lay_size: Optional[float] = None
    selection_id: Optional[int] = None


@dataclass(frozen=True)
class ConditionCheck:
    """Esito di una singola condizione. ok=None -> dato non disponibile."""

    id: str
    label: str
    value: str
    ok: Optional[bool]


@dataclass(frozen=True)
class VariantEvaluation:
    variant: str                       # 'base' | 'esatto' | 'punta' | 'tennis'
    state: str                         # 'signal' | 'nd' | 'no'
    checks: Tuple[ConditionCheck, ...]
    headline: Optional[str]
    side: Optional[str]                # 'BACK' | 'LAY'
    selection: Optional[str]
    entry_odds: Optional[float]
    entry_size: Optional[float]
    sub_id: Optional[str] = None       # 'home' | 'away' (variante esatto)
    market_type: str = "MATCH_ODDS"
    market_id: Optional[str] = None
    selection_id: Optional[int] = None


def state_from_checks(checks: Sequence[ConditionCheck]) -> str:
    """stato aggregato: false vince su null, null vince su true."""
    if any(c.ok is False for c in checks):
        return "no"
    if any(c.ok is None for c in checks):
        return "nd"
    return "signal"


@dataclass(frozen=True)
class FootballOdds:
    home: Optional[OddsPair]
    draw: Optional[OddsPair]
    away: Optional[OddsPair]


@dataclass(frozen=True)
class AnyOtherOdds:
    home: Optional[OddsPair]
    away: Optional[OddsPair]


@dataclass(frozen=True)
class TennisOdds:
    p1: Optional[OddsPair]
    p2: Optional[OddsPair]


@dataclass(frozen=True)
class FootballMatchCtx:
    event_id: str
    home: str
    away: str
    inplay: bool
    minute: Optional[int]
    score_home: Optional[int]
    score_away: Optional[int]
    odds: Optional[FootballOdds]
    any_other: Optional[AnyOtherOdds]
    pre_match: Optional[Dict[str, float]]
    match_odds_market_id: Optional[str]
    match_odds_open: Optional[bool]
    correct_score_open: Optional[bool]
    odds_name_mismatch: bool
    score_stable_since_minute: Optional[int]
    score_observed_sec: Optional[float]
    red: Optional[Dict[str, int]]
    correct_score_market_id: Optional[str] = None
    any_other_home_selection_id: Optional[int] = None
    any_other_away_selection_id: Optional[int] = None
    competition: Optional[str] = None
    event_name: Optional[str] = None


@dataclass(frozen=True)
class TennisMatchCtx:
    event_id: str
    p1: str
    p2: str
    inplay: bool
    sets: Optional[Dict[str, int]]
    games: Optional[Dict[str, int]]
    odds: Optional[TennisOdds]
    match_odds_market_id: Optional[str]
    match_odds_open: Optional[bool]
    odds_name_mismatch: bool
    competition: Optional[str]
    score_observed_sec: Optional[float]
    event_name: Optional[str] = None


# --------------------------------------------------- contesti dallo SCANNER
_ANY_OTHER_HOME = re.compile(r"any\s*other.*home", re.IGNORECASE)
_ANY_OTHER_AWAY = re.compile(r"any\s*other.*away", re.IGNORECASE)


def scan_pair(x: Any) -> Optional[OddsPair]:
    if not isinstance(x, dict):
        return None
    return OddsPair(
        back=num_or_none(x.get("back")),
        lay=num_or_none(x.get("lay")),
        back_size=num_or_none(x.get("back_size")),
        lay_size=num_or_none(x.get("lay_size")),
        selection_id=_int_field(x.get("selection_id")),
    )


def scan_market_open(status: Any) -> Optional[bool]:
    """stato mercato dallo scanner: None = non ancora interrogato (ignoto)."""
    return None if status is None else status == "OPEN"


def _any_other_selection_ids(cs: Any) -> Tuple[Optional[int], Optional[int]]:
    """selection_id di "Any Other Home/Away Win" dal blocco CS: il pair
    ``any_other_*`` non li porta, si risolvono per nome da ``cs.selections``."""
    if not isinstance(cs, dict):
        return None, None
    home = away = None
    for key, target in (("any_other_home", "home"), ("any_other_away", "away")):
        blk = cs.get(key)
        sid = _int_field(blk.get("selection_id")) if isinstance(blk, dict) else None
        if target == "home":
            home = sid
        else:
            away = sid
    sels = cs.get("selections")
    if isinstance(sels, (list, tuple)):
        for s in sels:
            if not isinstance(s, dict):
                continue
            sid = _int_field(s.get("selection_id"))
            if sid is None:
                continue
            name = str(s.get("name") or "")
            if home is None and _ANY_OTHER_HOME.search(name):
                home = sid
            elif away is None and _ANY_OTHER_AWAY.search(name):
                away = sid
    return home, away


def _text_or_none(v: Any) -> Optional[str]:
    """``p.competition?.trim() || null`` del TS."""
    return (v.strip() or None) if isinstance(v, str) else None


def build_football_ctx_from_scan(
    event_id: str,
    p: Dict[str, Any],
    score_stable_since_minute: Optional[int],
    score_observed_sec: Optional[float],
) -> FootballMatchCtx:
    """Contesto calcio dalla riga dello scanner autonomo (payload difensivo)."""
    p = p if isinstance(p, dict) else {}
    red_h = num_or_none(p.get("red_home"))
    red_a = num_or_none(p.get("red_away"))
    odds_raw = p.get("odds")
    odds = (
        FootballOdds(
            home=scan_pair(odds_raw.get("home")),
            draw=scan_pair(odds_raw.get("draw")),
            away=scan_pair(odds_raw.get("away")),
        )
        if isinstance(odds_raw, dict)
        else None
    )
    cs = p.get("cs") if isinstance(p.get("cs"), dict) else None
    any_other = (
        AnyOtherOdds(
            home=scan_pair(cs.get("any_other_home")), away=scan_pair(cs.get("any_other_away"))
        )
        if cs is not None
        else None
    )
    any_home_sid, any_away_sid = _any_other_selection_ids(cs)
    pre = p.get("pre_ko") if isinstance(p.get("pre_ko"), dict) else None
    pre_match: Optional[Dict[str, float]] = None
    if pre is not None and all(num_or_none(pre.get(k)) is not None for k in ("home", "draw", "away")):
        pre_match = {"home": pre["home"], "draw": pre["draw"], "away": pre["away"]}

    home = p.get("home")
    if home is None:
        home = p.get("event_name")
    if home is None:
        home = EMDASH
    away = p.get("away")
    if away is None:
        away = EMDASH

    return FootballMatchCtx(
        event_id=event_id,
        home=home,
        away=away,
        inplay=p.get("inplay") is True,
        minute=_int_field(p.get("minute")),
        score_home=_int_field(p.get("score_home")),
        score_away=_int_field(p.get("score_away")),
        odds=odds,
        any_other=any_other,
        pre_match=pre_match,
        match_odds_market_id=p.get("mo_market_id"),
        match_odds_open=scan_market_open(p.get("mo_status")),
        correct_score_open=scan_market_open(cs.get("status")) if cs is not None else None,
        odds_name_mismatch=False,  # nomi e selezioni vengono dallo STESSO catalogo
        score_stable_since_minute=score_stable_since_minute,
        score_observed_sec=score_observed_sec,
        red=(
            {"home": int(red_h), "away": int(red_a)}
            if red_h is not None and red_a is not None
            else None
        ),
        correct_score_market_id=cs.get("market_id") if cs is not None else None,
        any_other_home_selection_id=any_home_sid,
        any_other_away_selection_id=any_away_sid,
        competition=_text_or_none(p.get("competition")),
        event_name=p.get("event_name"),
    )


def build_tennis_ctx_from_scan(
    event_id: str, p: Dict[str, Any], score_observed_sec: Optional[float]
) -> TennisMatchCtx:
    """Contesto tennis dalla riga dello scanner autonomo."""
    p = p if isinstance(p, dict) else {}
    raw_sets = p.get("sets") if isinstance(p.get("sets"), dict) else None
    raw_games = p.get("games") if isinstance(p.get("games"), dict) else None
    sets = (
        {"p1": int(raw_sets["p1"]), "p2": int(raw_sets["p2"])}
        if raw_sets is not None
        and num_or_none(raw_sets.get("p1")) is not None
        and num_or_none(raw_sets.get("p2")) is not None
        else None
    )
    games = (
        {"p1": int(raw_games["p1"]), "p2": int(raw_games["p2"])}
        if raw_games is not None
        and num_or_none(raw_games.get("p1")) is not None
        and num_or_none(raw_games.get("p2")) is not None
        else None
    )
    odds_raw = p.get("odds")
    odds = (
        TennisOdds(p1=scan_pair(odds_raw.get("p1")), p2=scan_pair(odds_raw.get("p2")))
        if isinstance(odds_raw, dict)
        else None
    )
    p1 = p.get("p1")
    if p1 is None:
        p1 = p.get("event_name")
    if p1 is None:
        p1 = EMDASH
    p2 = p.get("p2")
    if p2 is None:
        p2 = EMDASH
    return TennisMatchCtx(
        event_id=event_id,
        p1=p1,
        p2=p2,
        inplay=p.get("inplay") is True,
        sets=sets,
        games=games,
        odds=odds,
        match_odds_market_id=p.get("mo_market_id"),
        match_odds_open=scan_market_open(p.get("mo_status")),
        odds_name_mismatch=False,
        competition=_text_or_none(p.get("competition")),
        score_observed_sec=score_observed_sec,
        event_name=p.get("event_name"),
    )


def favorite_side(pre_match: Optional[Dict[str, float]]) -> Optional[str]:
    """favorita dal 1X2 pre-match; None se pari o dato mancante."""
    if not pre_match:
        return None
    if pre_match["home"] == pre_match["away"]:
        return None
    return "home" if pre_match["home"] < pre_match["away"] else "away"


def leader_side(score_home: int, score_away: int) -> Optional[str]:
    if score_home == score_away:
        return None
    return "home" if score_home > score_away else "away"


# ------------------------------------------------------- valutatori CALCIO
def minute_check(check_id: str, minute: Optional[int], from_minute: Any) -> ConditionCheck:
    """SOGLIA minuto: vera dal minuto indicato IN POI, mai un intervallo chiuso
    - con un range fisso (es. 48-50') quasi nessun segnale passerebbe; il tetto
    reale lo mettono i range quote delle strategie."""
    return ConditionCheck(
        id=check_id,
        label=f"Dal minuto {js_num(from_minute)}{PRIME} in poi",
        value=fmt_minute(minute),
        ok=None if minute is None else minute >= from_minute,
    )


def market_open_check(label: str, open_: Optional[bool]) -> ConditionCheck:
    """mercato tradabile ORA (post-gol i mercati restano sospesi per secondi)."""
    return ConditionCheck(
        id="marketOpen",
        label=label,
        value="n/d" if open_ is None else ("aperto" if open_ else "sospeso"),
        ok=open_,
    )


def _inplay_check(label: str, inplay: bool) -> ConditionCheck:
    return ConditionCheck("inplay", label, SI if inplay else "no", True if inplay else False)


def _score_confirm_check(observed_sec: Optional[float], confirm_sec: Any) -> ConditionCheck:
    """anti-blip: l'in-play service Betfair a volte manda punteggi errati."""
    return ConditionCheck(
        id="scoreConfirmed",
        label=f"Punteggio stabile da {GEQ}{js_num(confirm_sec)}s",
        value="n/d" if observed_sec is None else f"{int(math.floor(observed_sec))}s",
        ok=None if observed_sec is None else observed_sec >= confirm_sec,
    )


def _side_pair(odds: Optional[FootballOdds], side: Optional[str]) -> Optional[OddsPair]:
    if side is None or odds is None:
        return None
    return odds.home if side == "home" else odds.away


def evaluate_base(ctx: FootballMatchCtx, params: Dict[str, Any]) -> VariantEvaluation:
    """1 . Calcio Base - banca (lay) la squadra che perde sul mercato 1X2."""
    checks: List[ConditionCheck] = []
    sh, sa = ctx.score_home, ctx.score_away
    fav = favorite_side(ctx.pre_match)
    lead = leader_side(sh, sa) if sh is not None and sa is not None else None
    scores_label = f" {MIDDOT} ".join(params["scores"])

    checks.append(_inplay_check("Partita in-play", ctx.inplay))
    checks.append(minute_check("minute", ctx.minute, params["minuteMin"]))

    # punteggio: la FAVORITA deve essere avanti con uno dei punteggi ammessi
    score_label = f"Favorita avanti {scores_label}"
    if sh is None or sa is None:
        checks.append(ConditionCheck("score", score_label, "n/d", None))
    elif fav is None:
        checks.append(ConditionCheck("score", score_label, f"{sh}-{sa} (favorita n/d)", None))
    else:
        fav_goals = sh if fav == "home" else sa
        dog_goals = sa if fav == "home" else sh
        checks.append(
            ConditionCheck(
                "score",
                score_label,
                f"{sh}-{sa}",
                lead == fav and score_in_list_oriented(params["scores"], fav_goals, dog_goals),
            )
        )

    # quote pre-match favorita / sfavorita
    fav_pre_label = (
        f"Favorita pre-match {js_num(params['favPreMin'])}{NDASH}{js_num(params['favPreMax'])}"
    )
    dog_pre_label = (
        f"Sfavorita pre-match {js_num(params['dogPreMin'])}{NDASH}{js_num(params['dogPreMax'])}"
    )
    if ctx.pre_match is None or fav is None:
        checks.append(ConditionCheck("favPre", fav_pre_label, "n/d", None))
        checks.append(ConditionCheck("dogPre", dog_pre_label, "n/d", None))
    else:
        fav_pre = ctx.pre_match["home"] if fav == "home" else ctx.pre_match["away"]
        dog_pre = ctx.pre_match["away"] if fav == "home" else ctx.pre_match["home"]
        checks.append(
            ConditionCheck(
                "favPre",
                fav_pre_label,
                fmt_odds(fav_pre),
                in_range(fav_pre, params["favPreMin"], params["favPreMax"]),
            )
        )
        checks.append(
            ConditionCheck(
                "dogPre",
                dog_pre_label,
                fmt_odds(dog_pre),
                in_range(dog_pre, params["dogPreMin"], params["dogPreMax"]),
            )
        )

    # quota live (back) della favorita - valida solo a mercato aperto
    checks.append(market_open_check("Mercato Match Odds aperto", ctx.match_odds_open))
    fav_pair = _side_pair(ctx.odds, fav)
    fav_live = fav_pair.back if fav_pair is not None else None
    checks.append(
        ConditionCheck(
            "favLive",
            f"Quota live favorita {js_num(params['favLiveMin'])}{NDASH}{js_num(params['favLiveMax'])}",
            fmt_odds(fav_live),
            None if fav_live is None else in_range(fav_live, params["favLiveMin"], params["favLiveMax"]),
        )
    )

    checks.append(_score_confirm_check(ctx.score_observed_sec, params["scoreConfirmSec"]))

    # rosso alla favorita = "mezzo gol subito": ENFORCED solo se il dato c'e'
    if ctx.red is not None and fav is not None:
        red_fav = ctx.red["home"] if fav == "home" else ctx.red["away"]
        checks.append(
            ConditionCheck(
                "noRedFav",
                "Nessun rosso alla favorita",
                "nessuno" if red_fav == 0 else f"{red_fav} rosso/i",
                red_fav == 0,
            )
        )

    dog = None if fav is None else ("away" if fav == "home" else "home")
    dog_name = None if dog is None else (ctx.home if dog == "home" else ctx.away)
    dog_pair = _side_pair(ctx.odds, dog)
    dog_lay = dog_pair.lay if dog_pair is not None else None
    dog_lay_size = dog_pair.lay_size if dog_pair is not None else None
    # senza un prezzo LAY reale della sfavorita non c'e' nulla da bancare
    checks.append(
        ConditionCheck(
            "dogLay",
            "Quota banca sfavorita disponibile",
            fmt_odds_with_size(dog_lay, dog_lay_size),
            None if dog_lay is None else True,
        )
    )

    state = state_from_checks(checks)
    return VariantEvaluation(
        variant="base",
        state=state,
        checks=tuple(checks),
        headline=f"BANCA {dog_name}" if state == "signal" and dog_name else None,
        side="LAY",
        selection=dog_name,
        entry_odds=dog_lay,
        entry_size=None if dog_lay is None else size_or_none(dog_lay_size),
        market_type="MATCH_ODDS",
        market_id=ctx.match_odds_market_id,
        selection_id=dog_pair.selection_id if dog_pair is not None else None,
    )


def evaluate_esatto(ctx: FootballMatchCtx, params: Dict[str, Any], side: str) -> VariantEvaluation:
    """2 . Calcio Risultato Esatto - banca "Altro risultato Casa/Ospite"."""
    checks: List[ConditionCheck] = []
    sh, sa = ctx.score_home, ctx.score_away
    side_name = ctx.home if side == "home" else ctx.away
    side_label = "Casa" if side == "home" else "Ospite"
    scores_label = f" {MIDDOT} ".join(params["scores"])

    checks.append(_inplay_check("Partita in-play", ctx.inplay))
    checks.append(minute_check("minute", ctx.minute, params["minuteMin"]))

    goals_label = f"{side_label} con max {js_num(params['maxGoalsLaySide'])} gol"
    if sh is None or sa is None:
        checks.append(ConditionCheck("score", f"Punteggio {scores_label}", "n/d", None))
        checks.append(ConditionCheck("sideGoals", goals_label, "n/d", None))
    else:
        checks.append(
            ConditionCheck(
                "score",
                f"Punteggio {scores_label}",
                f"{sh}-{sa}",
                score_in_list_any_order(params["scores"], sh, sa),
            )
        )
        side_goals = sh if side == "home" else sa
        checks.append(
            ConditionCheck(
                "sideGoals", goals_label, f"{side_goals} gol", side_goals <= params["maxGoalsLaySide"]
            )
        )

    checks.append(_score_confirm_check(ctx.score_observed_sec, params["scoreConfirmSec"]))

    # quota "Altro risultato" - si BANCA: quota di riferimento = SOLO il lay
    # (mai il back come sostituto: lo spread e' ampio e non e' ottenibile)
    checks.append(market_open_check("Mercato Risultato Esatto aperto", ctx.correct_score_open))
    pair = (
        None if ctx.any_other is None else (ctx.any_other.home if side == "home" else ctx.any_other.away)
    )
    entry = pair.lay if pair is not None else None
    entry_size = pair.lay_size if pair is not None else None
    entry_label = (
        f'Quota "Altro risultato {side_label}" '
        f"{js_num(params['entryMin'])}{NDASH}{js_num(params['entryMax'])}"
    )
    checks.append(
        ConditionCheck(
            "entry",
            entry_label,
            fmt_odds_with_size(entry, entry_size),
            None if entry is None else in_range(entry, params["entryMin"], params["entryMax"]),
        )
    )

    state = state_from_checks(checks)
    sid = ctx.any_other_home_selection_id if side == "home" else ctx.any_other_away_selection_id
    if pair is not None and pair.selection_id is not None:
        sid = pair.selection_id
    return VariantEvaluation(
        variant="esatto",
        sub_id=side,
        state=state,
        checks=tuple(checks),
        headline=(
            f"BANCA Altro risultato {side_label} ({side_name})" if state == "signal" else None
        ),
        side="LAY",
        selection=f"Altro risultato {side_label}",
        entry_odds=entry,
        entry_size=None if entry is None else size_or_none(entry_size),
        market_type="CORRECT_SCORE",
        market_id=ctx.correct_score_market_id,
        selection_id=sid,
    )


def evaluate_punta(ctx: FootballMatchCtx, params: Dict[str, Any]) -> VariantEvaluation:
    """3 . Calcio Variante Punta - punta (back) la squadra avanti di 2 gol."""
    checks: List[ConditionCheck] = []
    sh, sa = ctx.score_home, ctx.score_away
    lead = leader_side(sh, sa) if sh is not None and sa is not None else None
    fav = favorite_side(ctx.pre_match)
    scores_label = f" {MIDDOT} ".join(params["scores"])

    checks.append(_inplay_check("Partita in-play", ctx.inplay))
    checks.append(minute_check("minute", ctx.minute, params["minuteMin"]))

    if sh is None or sa is None:
        checks.append(ConditionCheck("score", f"In vantaggio {scores_label}", "n/d", None))
    else:
        a, b = max(sh, sa), min(sh, sa)
        checks.append(
            ConditionCheck(
                "score",
                f"In vantaggio {scores_label}",
                f"{sh}-{sa}",
                lead is not None and score_in_list_oriented(params["scores"], a, b),
            )
        )

    # chi e' avanti deve essere la favorita pre-match (se il riferimento c'e')
    lead_fav_label = f"In vantaggio c{RSQUO}{EGRAVE} la favorita"
    if lead is None:
        checks.append(
            ConditionCheck(
                "leadFav",
                lead_fav_label,
                "pareggio" if sh is not None and sa is not None else "n/d",
                False if sh is not None and sa is not None else None,
            )
        )
    elif fav is None:
        checks.append(ConditionCheck("leadFav", lead_fav_label, "favorita n/d", None))
    else:
        checks.append(
            ConditionCheck(
                "leadFav", lead_fav_label, ctx.home if lead == "home" else ctx.away, lead == fav
            )
        )

    # rosso a CHI SI PUNTA: enforced solo quando il dato cartellini e' esposto
    if ctx.red is not None and lead is not None:
        red_lead = ctx.red["home"] if lead == "home" else ctx.red["away"]
        checks.append(
            ConditionCheck(
                "noRedLead",
                "Nessun rosso a chi si punta",
                "nessuno" if red_lead == 0 else f"{red_lead} rosso/i",
                red_lead == 0,
            )
        )

    # quota live (back) della squadra in vantaggio - solo a mercato aperto
    checks.append(market_open_check("Mercato Match Odds aperto", ctx.match_odds_open))
    lead_pair = _side_pair(ctx.odds, lead)
    lead_back = lead_pair.back if lead_pair is not None else None
    lead_back_size = lead_pair.back_size if lead_pair is not None else None
    checks.append(
        ConditionCheck(
            "entry",
            f"Quota live {js_num(params['entryMin'])}{NDASH}{js_num(params['entryMax'])}",
            fmt_odds_with_size(lead_back, lead_back_size),
            None if lead_back is None else in_range(lead_back, params["entryMin"], params["entryMax"]),
        )
    )

    # assestamento post-gol: dal momento in cui ABBIAMO OSSERVATO il punteggio
    # corrente devono essere passati almeno N minuti (stima conservativa)
    since = ctx.score_stable_since_minute
    elapsed = ctx.minute - since if since is not None and ctx.minute is not None else None
    checks.append(
        ConditionCheck(
            "settled",
            f"Almeno {js_num(params['minMinutesAfterGoal'])}{PRIME} dopo l'ultimo gol",
            "n/d" if elapsed is None else f"{elapsed}{PRIME}",
            None if elapsed is None else elapsed >= params["minMinutesAfterGoal"],
        )
    )

    state = state_from_checks(checks)
    lead_name = None if lead is None else (ctx.home if lead == "home" else ctx.away)
    return VariantEvaluation(
        variant="punta",
        state=state,
        checks=tuple(checks),
        headline=f"PUNTA {lead_name}" if state == "signal" and lead_name else None,
        side="BACK",
        selection=lead_name,
        entry_odds=lead_back,
        entry_size=None if lead_back is None else size_or_none(lead_back_size),
        market_type="MATCH_ODDS",
        market_id=ctx.match_odds_market_id,
        selection_id=lead_pair.selection_id if lead_pair is not None else None,
    )


def evaluate_football_all(
    ctx: FootballMatchCtx, params: Dict[str, Any]
) -> List[VariantEvaluation]:
    """Valuta tutte le varianti calcio su un contesto (base, esatto x2, punta)."""
    return [
        evaluate_base(ctx, params["base"]),
        evaluate_esatto(ctx, params["esatto"], "home"),
        evaluate_esatto(ctx, params["esatto"], "away"),
        evaluate_punta(ctx, params["punta"]),
    ]


# ------------------------------------------------------------ valutatore TENNIS
def tennis_score_key(
    sets: Optional[Dict[str, int]], games: Optional[Dict[str, int]]
) -> Optional[str]:
    """chiave compatta della situazione set+game (tracker di stabilita')."""
    if not sets or not games:
        return None
    return f"s{sets['p1']}-{sets['p2']}{MIDDOT}g{games['p1']}-{games['p2']}"


def evaluate_tennis(ctx: TennisMatchCtx, params: Dict[str, Any]) -> VariantEvaluation:
    """4 . Tennis - punta chi e' avanti (il lay di chi perde resta informativo)."""
    checks: List[ConditionCheck] = []
    is_doubles = "/" in ctx.p1 or "/" in ctx.p2

    checks.append(_inplay_check("Match in-play", ctx.inplay))

    if params["excludeDoubles"]:
        checks.append(
            ConditionCheck(
                "singles",
                "Singolare (no doppio)",
                "doppio" if is_doubles else "singolare",
                not is_doubles,
            )
        )

    # filtro competizioni escluse: enforced solo se la lista e' compilata
    if len(params["excludeCompetitions"]) > 0:
        if ctx.competition is None:
            checks.append(ConditionCheck("competition", "Competizione non esclusa", "n/d", None))
        else:
            comp_lower = ctx.competition.lower()
            hit = next((k for k in params["excludeCompetitions"] if k in comp_lower), None)
            checks.append(
                ConditionCheck(
                    "competition",
                    "Competizione non esclusa",
                    f'esclusa ("{hit}")' if hit else ctx.competition,
                    not hit,
                )
            )

    # leader per SET
    leader: Optional[int] = None
    sets_label = f"Vantaggio di {js_num(params['setsLeadMin'])}+ set"
    if ctx.sets is None:
        checks.append(ConditionCheck("sets", sets_label, "n/d", None))
    else:
        diff = ctx.sets["p1"] - ctx.sets["p2"]
        leader = 1 if diff > 0 else (2 if diff < 0 else None)
        checks.append(
            ConditionCheck(
                "sets",
                sets_label,
                f"{ctx.sets['p1']}-{ctx.sets['p2']}",
                abs(diff) >= params["setsLeadMin"],
            )
        )

    # vantaggio game nel set corrente, dello STESSO giocatore avanti nei set
    games_label = f"{js_num(params['gamesLeadMin'])}+ game di vantaggio nel set corrente"
    if ctx.games is None or leader is None:
        checks.append(
            ConditionCheck(
                "games",
                games_label,
                "n/d" if ctx.games is None else f"{ctx.games['p1']}-{ctx.games['p2']}",
                False
                if (ctx.games is not None and leader is None and ctx.sets is not None)
                else None,
            )
        )
    else:
        g_lead = (
            ctx.games["p1"] - ctx.games["p2"] if leader == 1 else ctx.games["p2"] - ctx.games["p1"]
        )
        checks.append(
            ConditionCheck(
                "games",
                games_label,
                f"{ctx.games['p1']}-{ctx.games['p2']}",
                g_lead >= params["gamesLeadMin"],
            )
        )

    checks.append(_score_confirm_check(ctx.score_observed_sec, params["scoreConfirmSec"]))

    # quota d'ingresso = BACK del LEADER nel range (il lay del perdente al suo
    # prezzo REALE resta l'alternativa operativa: informativo, non decide)
    checks.append(market_open_check("Mercato Match Odds aperto", ctx.match_odds_open))
    lead_pair = (
        None if leader is None or ctx.odds is None else (ctx.odds.p1 if leader == 1 else ctx.odds.p2)
    )
    trail_pair = (
        None if leader is None or ctx.odds is None else (ctx.odds.p2 if leader == 1 else ctx.odds.p1)
    )
    lead_back = lead_pair.back if lead_pair is not None else None
    lead_back_size = lead_pair.back_size if lead_pair is not None else None
    trail_lay = trail_pair.lay if trail_pair is not None else None
    trail_txt = (
        f" {MIDDOT} lay perdente "
        f"{fmt_odds_with_size(trail_lay, trail_pair.lay_size if trail_pair is not None else None)}"
        if trail_lay is not None
        else ""
    )
    checks.append(
        ConditionCheck(
            "odds",
            f"Quota back leader {js_num(params['backMin'])}{NDASH}{js_num(params['backMax'])}",
            f"back {fmt_odds_with_size(lead_back, lead_back_size)}{trail_txt}",
            None if lead_back is None else in_range(lead_back, params["backMin"], params["backMax"]),
        )
    )

    state = state_from_checks(checks)
    lead_name = None if leader is None else (ctx.p1 if leader == 1 else ctx.p2)
    return VariantEvaluation(
        variant="tennis",
        state=state,
        checks=tuple(checks),
        headline=f"PUNTA {lead_name}" if state == "signal" and lead_name else None,
        side="BACK",
        selection=lead_name,
        entry_odds=lead_back,
        entry_size=None if lead_back is None else size_or_none(lead_back_size),
        market_type="MATCH_ODDS",
        market_id=ctx.match_odds_market_id,
        selection_id=lead_pair.selection_id if lead_pair is not None else None,
    )


# --------------------------------------------------- stabilita' punteggio
@dataclass(frozen=True)
class ScoreStability:
    score_key: str          # chiave del punteggio osservato (es. "2-0")
    since_minute: int       # minuto della PRIMA osservazione
    since_ms: float         # timestamp (ms) della PRIMA osservazione


@dataclass(frozen=True)
class TennisScoreStability:
    score_key: str
    since_ms: float


def track_score_stability(
    prev: Optional[ScoreStability],
    minute: Optional[int],
    score_home: Optional[int],
    score_away: Optional[int],
    now_ms: float,
) -> Optional[ScoreStability]:
    """Al cambio punteggio il timer riparte (minuto + timestamp correnti).
    PURA: il chiamante conserva la mappa per-evento e passa ``now_ms``."""
    if minute is None or score_home is None or score_away is None:
        return prev
    key = f"{score_home}-{score_away}"
    if prev is not None and prev.score_key == key:
        # stesso punteggio: la PRIMA osservazione resta (mai spostata avanti)
        return prev if prev.since_minute <= minute else ScoreStability(key, minute, prev.since_ms)
    return ScoreStability(key, minute, now_ms)


def track_tennis_score_stability(
    prev: Optional[TennisScoreStability], key: Optional[str], now_ms: float
) -> Optional[TennisScoreStability]:
    """tracker set+game: a ogni cambio la finestra riparte. PURA."""
    if key is None:
        return prev
    if prev is not None and prev.score_key == key:
        return prev
    return TennisScoreStability(key, now_ms)


# ------------------------------------------------------------ segnali attivi
SIGNAL_HISTORY_MAX = 50


def signal_key(event_id: str, variant: str, sub_id: Optional[str], situation: str) -> str:
    """chiave stabile: evento + variante(+lato) + situazione punteggio."""
    return f"{event_id}:{variant}" + (f":{sub_id}" if sub_id else "") + f":{situation}"


@dataclass(frozen=True)
class Signal:
    """Segnale ATTIVO pronto per l'operativita' (uno per chiave)."""

    key: str
    event_id: str
    sport: str                    # 'calcio' | 'tennis'
    variant: str                  # 'base' | 'esatto' | 'punta' | 'tennis'
    event_name: str
    market_type: str              # 'MATCH_ODDS' | 'CORRECT_SCORE'
    market_id: Optional[str]
    selection_id: Optional[int]
    selection_name: str
    side: str                     # 'back' | 'lay'
    price: Optional[float]        # quota d'ingresso (lay per LAY, back per BACK)
    size_available: float         # EUR abbinabili SUBITO a quel prezzo
    size: float                   # stake dai parametri (laySize/backSize)
    headline: str
    minute: Optional[int]
    score: str
    first_seen_ts: float
    checks: tuple                 # ((label, ok, detail), ...)


@dataclass(frozen=True)
class _Candidate:
    """Candidato-segnale del ciclo corrente (SignalCandidate del TS + campi
    operativi: mercato e selezione su cui piazzare)."""

    key: str
    sport: str
    variant: str
    sub_id: Optional[str]
    event_id: str
    event_name: str
    headline: str
    side: Optional[str]           # 'BACK' | 'LAY'
    entry_odds: Optional[float]
    entry_size: Optional[float]
    market_type: str
    market_id: Optional[str]
    selection_id: Optional[int]
    selection_name: str
    minute: Optional[int]
    score: str
    context_at_trigger: str
    checks: Tuple[ConditionCheck, ...]


@dataclass(frozen=True)
class _Active:
    cand: _Candidate
    triggered_at: float
    status: str                   # 'active' | 'expired'
    expired_at: Optional[float]


def football_candidates(
    ctx: FootballMatchCtx, evaluations: Sequence[VariantEvaluation]
) -> List[_Candidate]:
    """Estrae i candidati-segnale dalle valutazioni di un match calcio."""
    out: List[_Candidate] = []
    sh = "?" if ctx.score_home is None else ctx.score_home
    sa = "?" if ctx.score_away is None else ctx.score_away
    situation = f"{sh}-{sa}"
    for ev in evaluations:
        if ev.state != "signal" or not ev.headline:
            continue
        out.append(
            _Candidate(
                key=signal_key(ctx.event_id, ev.variant, ev.sub_id, situation),
                sport=SPORT_CALCIO,
                variant=ev.variant,
                sub_id=ev.sub_id,
                event_id=ctx.event_id,
                event_name=f"{ctx.home} {NDASH} {ctx.away}",
                headline=ev.headline,
                side=ev.side,
                entry_odds=ev.entry_odds,
                entry_size=ev.entry_size,
                market_type=ev.market_type,
                market_id=ev.market_id,
                selection_id=ev.selection_id,
                selection_name=ev.selection or "",
                minute=ctx.minute,
                score=situation,
                context_at_trigger=f"{fmt_minute(ctx.minute)} {MIDDOT} {situation}",
                checks=ev.checks,
            )
        )
    return out


def tennis_candidates(ctx: TennisMatchCtx, ev: VariantEvaluation) -> List[_Candidate]:
    """Estrae il candidato-segnale dalla valutazione di un match tennis."""
    if ev.state != "signal" or not ev.headline:
        return []
    situation = f"set {ctx.sets['p1']}-{ctx.sets['p2']}" if ctx.sets else "set ?"
    context = situation + (
        f" {MIDDOT} game {ctx.games['p1']}-{ctx.games['p2']}" if ctx.games else ""
    )
    return [
        _Candidate(
            key=signal_key(ctx.event_id, "tennis", None, situation),
            sport=SPORT_TENNIS,
            variant="tennis",
            sub_id=None,
            event_id=ctx.event_id,
            event_name=f"{ctx.p1} {NDASH} {ctx.p2}",
            headline=ev.headline,
            side=ev.side,
            entry_odds=ev.entry_odds,
            entry_size=ev.entry_size,
            market_type=ev.market_type,
            market_id=ev.market_id,
            selection_id=ev.selection_id,
            selection_name=ev.selection or "",
            minute=None,
            score=context,
            context_at_trigger=context,
            checks=ev.checks,
        )
    ]


def reconcile_signals(
    prev: Sequence[_Active], candidates: Sequence[_Candidate], now: float
) -> Tuple[List[_Active], List[_Active]]:
    """Riconcilia i segnali correnti coi candidati del ciclo di valutazione:
      * candidato nuovo -> segnale attivo (e in ``fresh``);
      * candidato gia' attivo -> aggiorna i dati live, stesso first_seen;
      * attivo non piu' candidato -> 'expired' (resta nello storico);
      * scaduto tornato candidato -> riattivato senza nuovo "fresh".
    Storico limitato a SIGNAL_HISTORY_MAX (i piu' recenti). PURA."""
    by_key = {s.cand.key: s for s in prev}
    cand_keys = {c.key for c in candidates}
    fresh: List[_Active] = []
    nxt: List[_Active] = []
    for c in candidates:
        existing = by_key.get(c.key)
        if existing is not None:
            nxt.append(
                _Active(cand=c, triggered_at=existing.triggered_at, status="active", expired_at=None)
            )
        else:
            created = _Active(cand=c, triggered_at=now, status="active", expired_at=None)
            nxt.append(created)
            fresh.append(created)
    for s in prev:
        if s.cand.key in cand_keys:
            continue
        if s.status == "active":
            nxt.append(
                _Active(cand=s.cand, triggered_at=s.triggered_at, status="expired", expired_at=now)
            )
        else:
            nxt.append(s)
    # ordine deterministico: piu' recenti prima, a parita' per chiave
    nxt.sort(key=lambda s: (-s.triggered_at, s.cand.key))
    return nxt[:SIGNAL_HISTORY_MAX], fresh


# ------------------------------------------------------------------- pipeline
def _parse_ts(v: Any) -> Optional[float]:
    """updated_at ISO -> epoch secondi (None se assente/illeggibile)."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    if not isinstance(v, str) or not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _accepts(prev: Optional[Dict[str, Any]], nxt: Dict[str, Any]) -> bool:
    """newerRow del provider: senza timestamp da una parte vince la riga nuova;
    con entrambi vince la piu' recente (a parita' la nuova)."""
    if prev is None:
        return True
    a, b = _parse_ts(prev.get("updated_at")), _parse_ts(nxt.get("updated_at"))
    if a is None or b is None:
        return True
    return b >= a


@dataclass
class Monitor:
    """Stato valutato di un evento (FootballMonitor/TennisMonitor del provider)."""

    event_id: str
    sport: str
    payload: Dict[str, Any]
    ctx: Any
    evaluations: List[VariantEvaluation]
    pre_match_missing: bool = False


class SafeEngine:
    """Motore Safe Strategy server-side: stesse decisioni della sezione web.

    Conserva tra le chiamate i tracker di stabilita' punteggio (anti-blip) e i
    segnali attivi, come SafeStrategyProvider. L'orologio e' iniettabile.
    """

    def __init__(
        self,
        params: Optional[Dict[str, Any]] = None,
        *,
        clock: Callable[[], float] = time.time,
    ):
        self._params = merge_params(params)
        self._clock = clock
        self._rows: Dict[str, Dict[str, Any]] = {}
        self._stab: Dict[str, ScoreStability] = {}
        self._tn_stab: Dict[str, TennisScoreStability] = {}
        self._signals: List[_Active] = []

    # ------------------------------------------------------------- parametri
    @property
    def params(self) -> Dict[str, Any]:
        return self._params

    def update_params(self, params: Dict[str, Any]) -> None:
        self._params = merge_params(params)

    # -------------------------------------------------------------- pipeline
    def _ingest(self, rows: Sequence[Dict[str, Any]], now_ms: float) -> List[Monitor]:
        incoming: Dict[str, Dict[str, Any]] = {}
        accepted: List[Tuple[str, Dict[str, Any]]] = []
        for row in rows or []:
            if not isinstance(row, dict) or row.get("event_id") is None:
                continue
            eid = str(row["event_id"])
            incoming[eid] = row
            if _accepts(self._rows.get(eid), row):
                self._rows[eid] = row
                accepted.append((eid, row))
        # il set di righe e' lo stato COMPLETO: gli eventi assenti sono spariti
        for eid in [e for e in self._rows if e not in incoming]:
            self._rows.pop(eid, None)
            self._stab.pop(eid, None)
            self._tn_stab.pop(eid, None)

        # tracker di stabilita': alimentati SOLO dalle righe accettate
        for eid, row in accepted:
            p = row.get("payload") if isinstance(row.get("payload"), dict) else {}
            if row.get("sport") == SPORT_TENNIS:
                upd_t = track_tennis_score_stability(
                    self._tn_stab.get(eid), self._tennis_key(p), now_ms
                )
                if upd_t is not None:
                    self._tn_stab[eid] = upd_t
            else:
                upd = track_score_stability(
                    self._stab.get(eid),
                    _int_field(p.get("minute")),
                    _int_field(p.get("score_home")),
                    _int_field(p.get("score_away")),
                    now_ms,
                )
                if upd is not None:
                    self._stab[eid] = upd

        monitors: List[Monitor] = []
        # ordine deterministico: prima il calcio, poi il tennis, per event_id
        order = sorted(self._rows, key=lambda e: (self._rows[e].get("sport") != SPORT_CALCIO, e))
        for eid in order:
            row = self._rows[eid]
            p = row.get("payload") if isinstance(row.get("payload"), dict) else {}
            if row.get("sport") == SPORT_TENNIS:
                stab_t = self._tn_stab.get(eid)
                key = self._tennis_key(p)
                observed = (
                    (now_ms - stab_t.since_ms) / 1000.0
                    if stab_t is not None and key is not None and stab_t.score_key == key
                    else None
                )
                ctx_t = build_tennis_ctx_from_scan(eid, p, observed)
                monitors.append(
                    Monitor(
                        eid,
                        SPORT_TENNIS,
                        p,
                        ctx_t,
                        [evaluate_tennis(ctx_t, self._params["tennis"])],
                    )
                )
            else:
                stab = self._stab.get(eid)
                cur_key = f"{p.get('score_home')}-{p.get('score_away')}"
                stable = stab if stab is not None and cur_key == stab.score_key else None
                ctx = build_football_ctx_from_scan(
                    eid,
                    p,
                    stable.since_minute if stable is not None else None,
                    (now_ms - stable.since_ms) / 1000.0 if stable is not None else None,
                )
                monitors.append(
                    Monitor(
                        eid,
                        SPORT_CALCIO,
                        p,
                        ctx,
                        evaluate_football_all(ctx, self._params),
                        pre_match_missing=ctx.inplay and ctx.pre_match is None,
                    )
                )
        return monitors

    @staticmethod
    def _tennis_key(p: Dict[str, Any]) -> Optional[str]:
        return tennis_score_key(
            p.get("sets") if isinstance(p.get("sets"), dict) else None,
            p.get("games") if isinstance(p.get("games"), dict) else None,
        )

    # ---------------------------------------------------------------- API
    def monitors(self, rows: Sequence[Dict[str, Any]]) -> List[Monitor]:
        """Valutazione completa (contesti + valutazioni) senza riconciliare."""
        now = float(self._clock())
        return self._ingest(rows, now * 1000.0)

    def evaluate(self, rows: Sequence[Dict[str, Any]]) -> List[Signal]:
        """Valuta le righe ``safe_strategy_scan`` e ritorna i segnali ATTIVI."""
        now = float(self._clock())
        monitors = self._ingest(rows, now * 1000.0)
        candidates: List[_Candidate] = []
        for m in monitors:
            if m.sport == SPORT_TENNIS:
                candidates.extend(tennis_candidates(m.ctx, m.evaluations[0]))
            else:
                candidates.extend(football_candidates(m.ctx, m.evaluations))
        nxt, _fresh = reconcile_signals(self._signals, candidates, now)
        self._signals = nxt
        return [self._to_signal(s) for s in nxt if s.status == "active"]

    def evaluations(self, rows: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Per event_id: TUTTE le valutazioni di variante (stato + check)."""
        out: Dict[str, List[Dict[str, Any]]] = {}
        for m in self.monitors(rows):
            out[m.event_id] = [self._eval_to_dict(m, ev) for ev in m.evaluations]
        return out

    # ---------------------------------------------------------------- output
    def _to_signal(self, s: _Active) -> Signal:
        c = s.cand
        side = (c.side or "").lower()
        stake = self._params["stake"]["laySize" if side == "lay" else "backSize"]
        return Signal(
            key=c.key,
            event_id=c.event_id,
            sport=c.sport,
            variant=c.variant,
            event_name=c.event_name,
            market_type=c.market_type,
            market_id=c.market_id,
            selection_id=c.selection_id,
            selection_name=c.selection_name,
            side=side,
            price=c.entry_odds,
            size_available=float(c.entry_size) if c.entry_size is not None else 0.0,
            size=float(stake),
            headline=c.headline,
            minute=c.minute,
            score=c.score,
            first_seen_ts=s.triggered_at,
            checks=tuple((ck.label, ck.ok, ck.value) for ck in c.checks),
        )

    @staticmethod
    def _eval_to_dict(m: Monitor, ev: VariantEvaluation) -> Dict[str, Any]:
        return {
            "sport": m.sport,
            "variant": ev.variant,
            "sub_id": ev.sub_id,
            "state": ev.state,
            "headline": ev.headline,
            "side": ev.side,
            "selection": ev.selection,
            "selection_id": ev.selection_id,
            "market_type": ev.market_type,
            "market_id": ev.market_id,
            "entry_odds": ev.entry_odds,
            "entry_size": ev.entry_size,
            "checks": [
                {"id": c.id, "label": c.label, "value": c.value, "ok": c.ok} for c in ev.checks
            ],
        }
