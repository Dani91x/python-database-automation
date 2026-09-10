"""tennis_opportunity.py — OPPORTUNITA' REALI in-play sul MATCH_ODDS tennis.

Gemello tennis di ``opportunity.py`` (punto 7): per ogni singolare in corso
confronta la P(vittoria) del modello Markov a livello game
(``tennis_winprob.p_match``) con PREZZO e LIQUIDITA' del book live e segnala
SOLO gli esiti quasi certi / quasi impossibili:

  * BACK del leader quando p_model >= min_prob_back (0.90), edge
    (p_model - 1/back) >= min_edge, back_size >= min_size e prezzo >=
    min_back_price (sotto 1.02 la commissione mangia tutto);
  * LAY di chi sta perdendo quando p_model <= max_prob_lay (0.10), lay <=
    max_lay_price (8) e lay_size >= min_size.

RITIRO = perdita totale: la P(vittoria) del leader viene ridotta di
``retire_risk`` (2%, piu' alto nei best-of-5) e la stessa quota viene sommata
a chi insegue (p1 + p2 resta ~1).

Gate: solo singolari, competizioni non escluse (stesse regole del motore
``engine.evaluate_tennis``), mercato OPEN, prezzi freschi (updated_at <=
max_stale_s), niente tiebreak e niente set decisivo in fase finale (salvo
parametri), match non concluso. Momentum: se il leader ha perso gli ultimi
due game (dal ``prev_payload`` passato nel payload, o dalla memoria interna
delle chiamate precedenti) la confidenza si dimezza.

Riuso (nessuna matematica nuova):
  * ``tennis_winprob.p_match / estimate_holds`` per la P(vittoria);
  * ``tennis_serve_data.get_serve_prob`` per gli hold da dato reale per
    giocatore (fallback: prior di ``estimate_holds``);
  * ``tennis_score.parse_tennis_scores`` per servizio e punti dallo
    ``score_raw`` IPS del feed unico;
  * ``engine.build_tennis_ctx_from_scan / merge_params`` per contesto ed
    esclusioni.

Tutto PURO: nessuna rete, nessun DB, orologio iniettabile.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from Betfair.safe_strategy import engine as E
from Betfair.stream.tennis_scalper import tennis_serve_data as _sd
from Betfair.stream.tennis_scalper.tennis_score import TennisScore, parse_tennis_scores
from Betfair.stream.tennis_scalper.tennis_winprob import estimate_holds, p_match

_EPS = 1e-9

# ---------------------------------------------------------------------------
# Parametri (tutti sovrascrivibili dal chiamante)
# ---------------------------------------------------------------------------
DEFAULT_TENNIS_OPP_PARAMS: Dict[str, Any] = {
    # soglie di segnalazione
    "min_prob_back": 0.90,     # back solo sul leader quasi certo
    "min_edge": 0.015,         # edge minimo (p_model - 1/quota)
    "min_size": 20.0,          # EUR abbinabili SUBITO al best price
    "min_back_price": 1.02,    # sotto: la commissione annulla il guadagno
    "max_prob_lay": 0.10,      # lay solo su chi e' quasi spacciato
    "max_lay_price": 8.0,      # oltre: liability sproporzionata
    # economia
    "commission": 0.05,
    # confidenza
    "ref_size": 200.0,         # profondita' di riferimento del book
    "stale_price_s": 10.0,     # sotto: prezzo fresco
    "max_stale_s": 30.0,       # oltre: prezzi morti -> nessuna opportunita'
    "momentum_penalty": 0.5,   # leader che ha perso gli ultimi 2 game
    "min_confidence": 0.0,
    # rischio ritiro (perdita totale)
    "retire_risk": 0.02,
    "retire_risk_bo5_extra": 0.01,   # best-of-5: piu' lungo, piu' ritiri
    # gate di contesto
    "allow_tiebreak": False,
    "allow_deciding_late": False,    # set decisivo con un giocatore a 5+ game
    # modello
    "best_of": None,           # None = auto (competizione / set giocati)
    "hold_prior": 0.75,        # prior di estimate_holds senza dati servizio
    "bo5_keywords": ["australian open", "roland garros", "french open",
                     "wimbledon", "us open"],
    "bo3_markers": ["women", "wta", "ladies", "girl", "boy", "junior",
                    "wheelchair", "qualif", "mixed", "legend", "doubles"],
    # esclusioni (default dal motore Safe Strategy sezione tennis)
    "exclude_doubles": E.DEFAULT_PARAMS["tennis"]["excludeDoubles"],
    "exclude_competitions": list(E.DEFAULT_PARAMS["tennis"]["excludeCompetitions"]),
    # forma
    "max_per_event": 2,
}


@dataclass(frozen=True)
class TennisOpportunity:
    market_type: str
    market_name: str
    line: Optional[float]
    market_id: Optional[str]
    selection_id: Optional[int]
    selection_name: str
    side: str               # 'back' | 'lay'
    price: float
    size_available: float
    p_model: float
    p_implied: float
    edge: float
    ev: float               # profitto atteso per 1 EUR di stake, netto commissione
    confidence: float
    rationale: str
    minute: Optional[int]
    score: str
    kind: str
    extra: Dict[str, Any]


@dataclass(frozen=True)
class _State:
    """Stato di gioco normalizzato dal payload."""
    sets: Tuple[int, int]
    games: Tuple[int, int]
    server: Optional[str]         # 'p1' | 'p2' | None
    points: Tuple[Optional[str], Optional[str]]
    best_of: int


# ---------------------------------------------------------------------------
# helper puri
# ---------------------------------------------------------------------------
def hold_from_serve_point(p: float) -> float:
    """P(tenere il servizio) da P(punto al servizio) — stessa formula chiusa di
    ``research_data.game_hold`` (non importato: quel modulo tira su il client
    Betfair)."""
    if p <= 0:
        return 0.0
    if p >= 1:
        return 1.0
    q = 1.0 - p
    base = p ** 4 + 4 * p ** 4 * q + 10 * p ** 4 * q * q
    deuce = 20 * (p ** 3) * (q ** 3)
    return base + deuce * (p * p / (p * p + q * q))


def devig_pair(back1: Optional[float], back2: Optional[float]) -> Tuple[Optional[float], Optional[float]]:
    """P implicite de-viggate (normalizzazione moltiplicativa) dai due back."""
    i1 = 1.0 / back1 if isinstance(back1, (int, float)) and back1 > 1.0 else None
    i2 = 1.0 / back2 if isinstance(back2, (int, float)) and back2 > 1.0 else None
    if i1 is not None and i2 is not None:
        s = i1 + i2
        return (i1 / s, i2 / s)
    return (i1, i2)


def detect_best_of(competition: Optional[str], sets: Tuple[int, int], params: Dict[str, Any]) -> int:
    """5 se forzato, se gia' giocati >= 3 set, o se Slam maschile (euristica sul
    nome torneo: keyword Slam senza marker femminile/junior/qualificazioni)."""
    forced = params.get("best_of")
    if forced in (3, 5):
        return int(forced)
    if sets[0] + sets[1] >= 3:
        return 5
    comp = (competition or "").lower()
    if comp and any(k in comp for k in params.get("bo5_keywords", [])):
        if not any(m in comp for m in params.get("bo3_markers", [])):
            return 5
    return 3


def _age_s(updated_at: Any, now_ts: float) -> Optional[float]:
    """Eta' in secondi di ``updated_at`` (ISO, epoch s o epoch ms)."""
    ts = E._parse_ts(updated_at)
    if ts is None:
        return None
    if ts > 1e11:          # epoch in millisecondi
        ts /= 1000.0
    return max(0.0, now_ts - ts)


def _int_pair(d: Any) -> Optional[Tuple[int, int]]:
    if not isinstance(d, dict):
        return None
    try:
        return (int(d["p1"]), int(d["p2"]))
    except (KeyError, TypeError, ValueError):
        return None


def _parse_raw(payload: dict) -> Optional[TennisScore]:
    raw = payload.get("score_raw")
    if not isinstance(raw, dict):
        return None
    try:
        return parse_tennis_scores([raw], payload.get("event_id"))
    except Exception:  # noqa: BLE001 — feed difensivo, mai rompere il modello
        return None


# ---------------------------------------------------------------------------
# modello
# ---------------------------------------------------------------------------
class TennisOpportunityModel:
    """Opportunita' MATCH_ODDS tennis dal punteggio + book del feed unico."""

    def __init__(self, params: Optional[dict] = None, *, clock: Callable[[], float] = time.time) -> None:
        merged = dict(DEFAULT_TENNIS_OPP_PARAMS)
        if params:
            merged.update({k: v for k, v in params.items() if v is not None})
        self.params = merged
        self._clock = clock
        # memoria momentum: chiave evento -> (stato (sets, games), vincitori ultimi game)
        self._mem: Dict[str, Tuple[Tuple[int, int], Tuple[int, int], List[str]]] = {}

    # ------------------------------------------------------------- stato
    def _state(self, payload: dict) -> Optional[_State]:
        sets = _int_pair(payload.get("sets"))
        games = _int_pair(payload.get("games"))
        ts = _parse_raw(payload)
        if sets is None and ts is not None and ts.sets_home is not None and ts.sets_away is not None:
            sets = (ts.sets_home, ts.sets_away)
        if games is None and ts is not None and ts.games_home is not None and ts.games_away is not None:
            games = (ts.games_home, ts.games_away)
        if sets is None or games is None:
            return None
        server = None
        points: Tuple[Optional[str], Optional[str]] = (None, None)
        if ts is not None:
            server = {"home": "p1", "away": "p2"}.get(ts.server or "")
            points = (ts.point_home, ts.point_away)
        best_of = detect_best_of(E._text_or_none(payload.get("competition")), sets, self.params)
        return _State(sets=sets, games=games, server=server, points=points, best_of=best_of)

    def _holds(self, payload: dict) -> Tuple[float, float]:
        """(hold p1, hold p2): dal dato di servizio per giocatore se c'e', altrimenti
        dal prior di ``estimate_holds`` (break non noti dal feed)."""
        prior = float(self.params["hold_prior"])
        ha, hb = estimate_holds(0, 0, 0, 0, prior=prior)
        s1 = _sd.get_serve_prob(payload.get("p1"))
        s2 = _sd.get_serve_prob(payload.get("p2"))
        if s1 is not None:
            ha = min(0.98, max(0.5, hold_from_serve_point(s1)))
        if s2 is not None:
            hb = min(0.98, max(0.5, hold_from_serve_point(s2)))
        return ha, hb

    def _retire_risk(self, st: _State) -> float:
        rr = float(self.params["retire_risk"])
        if st.best_of == 5:
            rr += float(self.params["retire_risk_bo5_extra"])
        return max(0.0, min(0.5, rr))

    def _p_raw_p1(self, st: _State, ha: float, hb: float) -> float:
        s1, s2 = st.sets
        g1, g2 = st.games
        if st.server == "p1":
            p = p_match(s1, s2, g1, g2, True, ha, hb, st.best_of)
        elif st.server == "p2":
            p = p_match(s1, s2, g1, g2, False, ha, hb, st.best_of)
        else:   # servizio ignoto: media dei due casi
            p = 0.5 * (p_match(s1, s2, g1, g2, True, ha, hb, st.best_of)
                       + p_match(s1, s2, g1, g2, False, ha, hb, st.best_of))
        return min(1.0, max(0.0, float(p)))

    def _probs(self, payload: dict, st: _State) -> Dict[str, Dict[str, float]]:
        """{'p1': {'raw', 'adj'}, 'p2': {...}}: il ritiro toglie al leader e da'
        a chi insegue (p1_adj + p2_adj = 1)."""
        ha, hb = self._holds(payload)
        raw1 = self._p_raw_p1(st, ha, hb)
        rr = self._retire_risk(st)
        if raw1 >= 0.5:
            adj1 = max(0.0, raw1 - rr)
        else:
            adj1 = min(1.0, raw1 + rr)
        return {
            "p1": {"raw": raw1, "adj": adj1},
            "p2": {"raw": 1.0 - raw1, "adj": 1.0 - adj1},
        }

    # ------------------------------------------------------------- API pubblica
    def p_win(self, payload: dict, player: str) -> Optional[float]:
        """P(vittoria) del giocatore 'p1'|'p2' (rischio ritiro incluso); None se
        il punteggio manca."""
        if player not in ("p1", "p2") or not isinstance(payload, dict):
            return None
        st = self._state(payload)
        if st is None:
            return None
        return round(self._probs(payload, st)[player]["adj"], 6)

    def evaluate(self, payload: dict, now_ts: float) -> List[dict]:
        if not isinstance(payload, dict):
            return []
        p = self.params
        st = self._state(payload)
        if st is None:
            return []
        key = str(payload.get("event_id") or payload.get("mo_market_id") or payload.get("event_name") or "")
        momentum_against = self._momentum(key, payload, st)   # aggiorna SEMPRE la memoria
        if not self._gates_ok(payload, st):
            return []
        age = _age_s(payload.get("updated_at"), now_ts)
        if age is not None and age > float(p["max_stale_s"]):
            return []
        odds = payload.get("odds") if isinstance(payload.get("odds"), dict) else None
        if not odds:
            return []
        o1 = odds.get("p1") if isinstance(odds.get("p1"), dict) else {}
        o2 = odds.get("p2") if isinstance(odds.get("p2"), dict) else {}
        impl = devig_pair(o1.get("back"), o2.get("back"))
        probs = self._probs(payload, st)
        rr = self._retire_risk(st)
        names = {"p1": str(payload.get("p1") or "p1"), "p2": str(payload.get("p2") or "p2")}
        leader = "p1" if probs["p1"]["adj"] >= 0.5 else "p2"

        out: List[TennisOpportunity] = []
        for side_player, runner, p_impl in (("p1", o1, impl[0]), ("p2", o2, impl[1])):
            pm = probs[side_player]["adj"]
            for side in ("back", "lay"):
                opp = self._try_side(
                    side, side_player, runner, pm, probs[side_player]["raw"], p_impl,
                    payload, st, names, age, rr,
                    momentum_against if side_player == leader else False,
                )
                if opp is not None:
                    out.append(opp)
        out.sort(key=lambda o: o.ev * o.confidence, reverse=True)
        return [asdict(o) for o in out[: int(p["max_per_event"])]]

    # ------------------------------------------------------------- gate
    def _gates_ok(self, payload: dict, st: _State) -> bool:
        p = self.params
        ctx = E.build_tennis_ctx_from_scan(str(payload.get("event_id") or ""), payload, None)
        if not ctx.inplay or ctx.match_odds_open is not True:
            return False
        if p["exclude_doubles"] and ("/" in ctx.p1 or "/" in ctx.p2):
            return False
        excl = [str(k).lower() for k in (p.get("exclude_competitions") or []) if k]
        if excl:
            comp = (ctx.competition or "").lower()
            if any(k in comp for k in excl):
                return False
        need = st.best_of // 2 + 1
        if st.sets[0] >= need or st.sets[1] >= need:
            return False            # match finito
        g1, g2 = st.games
        if g1 == 6 and g2 == 6 and not p["allow_tiebreak"]:
            return False
        deciding = st.sets[0] == need - 1 and st.sets[1] == need - 1
        if deciding and max(g1, g2) >= 5 and not p["allow_deciding_late"]:
            return False
        return True

    # ------------------------------------------------------------- momentum
    def _momentum(self, key: str, payload: dict, st: _State) -> bool:
        """True se il LEADER ha perso gli ultimi due game. Fonte: ``prev_payload``
        nel payload (diff dei game) oppure la memoria interna delle chiamate
        precedenti (aggiornata qui)."""
        leader = "p1" if self._p_raw_p1(st, *self._holds(payload)) >= 0.5 else "p2"
        trailer = "p2" if leader == "p1" else "p1"
        winners: List[str] = []
        prev = payload.get("prev_payload")
        if isinstance(prev, dict):
            ps, pg = _int_pair(prev.get("sets")), _int_pair(prev.get("games"))
            if ps is not None and pg is not None:
                winners = self._winners_between(ps, pg, st.sets, st.games)
                if len(winners) >= 2 and winners[-1] == trailer and winners[-2] == trailer:
                    return True
        if not key:
            return False
        mem = self._mem.get(key)
        hist: List[str] = list(mem[2]) if mem else []
        if mem and (mem[0], mem[1]) != (st.sets, st.games):
            hist.extend(self._winners_between(mem[0], mem[1], st.sets, st.games))
            hist = hist[-4:]
        self._mem[key] = (st.sets, st.games, hist)
        return len(hist) >= 2 and hist[-1] == trailer and hist[-2] == trailer

    @staticmethod
    def _winners_between(ps: Tuple[int, int], pg: Tuple[int, int],
                         cs: Tuple[int, int], cg: Tuple[int, int]) -> List[str]:
        """Vincitori dei game fra due istantanee (stesso set: diff dei game;
        cambio set: chi ha vinto il set piu' i game del set nuovo)."""
        out: List[str] = []
        if cs == ps:
            d1, d2 = cg[0] - pg[0], cg[1] - pg[1]
            if d1 < 0 or d2 < 0:
                return []
            # ordine ignoto: si mette per ultimo chi ha vinto piu' game (peggio per chi guida)
            first, second = ("p1", d1), ("p2", d2)
            if d1 > d2:
                first, second = second, first
            out.extend([first[0]] * first[1])
            out.extend([second[0]] * second[1])
            return out
        if cs[0] == ps[0] + 1 and cs[1] == ps[1]:
            out.append("p1")
        elif cs[1] == ps[1] + 1 and cs[0] == ps[0]:
            out.append("p2")
        else:
            return []
        out.extend(["p1"] * cg[0])
        out.extend(["p2"] * cg[1])
        return out

    # ------------------------------------------------------------- lato
    def _staleness_weight(self, age: Optional[float]) -> float:
        if age is None:
            return 1.0
        fresh, dead = float(self.params["stale_price_s"]), float(self.params["max_stale_s"])
        if age <= fresh:
            return 1.0
        if age >= dead or dead <= fresh:
            return 0.0
        return max(0.0, 1.0 - (age - fresh) / (dead - fresh))

    def _try_side(
        self, side: str, player: str, runner: dict, p_model: float, p_raw: float,
        p_implied: Optional[float], payload: dict, st: _State, names: Dict[str, str],
        age: Optional[float], rr: float, momentum_against: bool,
    ) -> Optional[TennisOpportunity]:
        p = self.params
        price = runner.get("back") if side == "back" else runner.get("lay")
        size = runner.get("back_size") if side == "back" else runner.get("lay_size")
        if not isinstance(price, (int, float)) or isinstance(price, bool) or price <= 1.0:
            return None
        price = float(price)
        size_f = float(size) if isinstance(size, (int, float)) and not isinstance(size, bool) else 0.0
        if size_f < float(p["min_size"]):
            return None
        if side == "back":
            if p_model < float(p["min_prob_back"]) or price < float(p["min_back_price"]):
                return None
            edge = p_model - 1.0 / price
            head = (p_model - float(p["min_prob_back"])) / max(_EPS, 1.0 - float(p["min_prob_back"]))
        else:
            if p_model > float(p["max_prob_lay"]) or price > float(p["max_lay_price"]):
                return None
            edge = 1.0 / price - p_model
            head = (float(p["max_prob_lay"]) - p_model) / max(_EPS, float(p["max_prob_lay"]))
        if edge < float(p["min_edge"]):
            return None
        comm = float(p["commission"])
        if side == "back":
            ev = p_model * (price - 1.0) * (1.0 - comm) - (1.0 - p_model)
        else:
            ev = (1.0 - p_model) * (1.0 - comm) - p_model * (price - 1.0)
        if ev <= 0:
            return None

        c_edge = min(1.0, edge / max(_EPS, 2.0 * float(p["min_edge"])))
        c_head = max(0.0, min(1.0, head))
        c_depth = min(1.0, size_f / max(_EPS, float(p["ref_size"])))
        c_fresh = self._staleness_weight(age)
        conf = 0.35 * c_edge + 0.25 * c_head + 0.20 * c_depth + 0.20 * c_fresh
        conf *= 1.0 - min(0.5, rr * 5.0)            # ritiro: 2% -> x0.90
        if momentum_against:
            conf *= float(p["momentum_penalty"])
        conf = max(0.0, min(1.0, conf))
        if conf < float(p["min_confidence"]):
            return None

        sid = runner.get("selection_id")
        score = f"set {st.sets[0]}-{st.sets[1]} {E.MIDDOT} game {st.games[0]}-{st.games[1]}"
        return TennisOpportunity(
            market_type="MATCH_ODDS",
            market_name="Match Odds",
            line=None,
            market_id=payload.get("mo_market_id"),
            selection_id=int(sid) if sid is not None else None,
            selection_name=names[player],
            side=side,
            price=round(price, 4),
            size_available=round(size_f, 2),
            p_model=round(p_model, 6),
            p_implied=round(float(p_implied), 6) if p_implied is not None else round(1.0 / price, 6),
            edge=round(edge, 6),
            ev=round(ev, 6),
            confidence=round(conf, 4),
            rationale=self._rationale(side, player, names, price, size_f, p_model, edge, st, rr),
            minute=None,
            score=score,
            kind="tennis",
            extra={
                "p_model_raw": round(p_raw, 6),
                "retire_risk": round(rr, 4),
                "best_of": st.best_of,
                "server": st.server,
                "momentum_against": bool(momentum_against),
                "price_age_s": round(age, 1) if age is not None else None,
            },
        )

    # ------------------------------------------------------------- rationale
    @staticmethod
    def _situation(player: str, st: _State) -> str:
        """Descrizione del vantaggio/svantaggio del giocatore (italiano)."""
        i, j = (0, 1) if player == "p1" else (1, 0)
        ds, dg = st.sets[i] - st.sets[j], st.games[i] - st.games[j]
        parts: List[str] = []
        if ds > 0:
            parts.append(f"{ds} set di vantaggio" if ds > 1 else "1 set")
        elif ds < 0:
            parts.append(f"sotto {st.sets[i]}-{st.sets[j]} nei set")
        if dg >= 4:
            parts.append("doppio break di vantaggio")
        elif dg >= 2:
            parts.append("break di vantaggio")
        elif dg == 1:
            parts.append("avanti di un game")
        elif dg < 0:
            parts.append(f"sotto {st.games[i]}-{st.games[j]} nel set")
        else:
            parts.append(f"{st.games[i]}-{st.games[j]} nel set")
        return " e ".join(parts[:2])

    def _rationale(self, side: str, player: str, names: Dict[str, str], price: float,
                   size: float, p_model: float, edge: float, st: _State, rr: float) -> str:
        head = f"{'Back' if side == 'back' else 'Lay'} {names[player]} a {price:.2f}"
        return (
            f"{head}: {self._situation(player, st)}, "
            f"P(vittoria)={p_model * 100:.1f}% (ritiro {rr * 100:.0f}% incluso), "
            f"edge {edge * 100:.1f}%, {size:.0f} EUR abbinabili"
        )
