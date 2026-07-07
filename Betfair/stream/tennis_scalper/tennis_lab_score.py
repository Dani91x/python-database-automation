"""ScoreConditionedLab — FASE 2: TennisLab con gate sullo STATO DI GIOCO.

Inietta la timeline dei punteggi registrati (.score.jsonl) allineata al
publish_time del book (stesso meccanismo di backtest_pro) e filtra gli ingressi
su condizioni di punteggio fondate su edge reali del tennis:

  SIDE-AGNOSTIC (nessuna mappa nomi -> ZERO rischio di bug di mapping):
    any       -> nessun filtro (baseline)
    set1      -> solo nel 1o set (rischio-crollo del favorito piu' alto a inizio match)
    set2plus  -> solo dopo che un set e' deciso (FLB sul set-leader sovra-prezzato)
    pressure  -> solo su break/set point live (la quota GAPPA -> fade dell'over-reaction)
    calm      -> solo FUORI dai punti che pesano (entra FLB quando il libro e' stabile)
    setlead   -> esiste esattamente un set di vantaggio
    early     -> pochi game giocati nel set corrente (<=3)

  SIDE-AWARE (richiede side_map sel->home/away; FAIL-SAFE: se il lato del target
  e' ignoto NON entra, cosi' una mappa incerta non genera mai un trade finto):
    serving    -> il target sta servendo (vantaggio al servizio)
    receiving  -> il target ribatte (piu' esposto al break)
    broke      -> il target ha appena BREKKATO (momentum, Klaassen-Magnus)
    gotbroken  -> il target ha appena SUBITO il break (fade / reversione)

Price-driven + score-gated. Il P&L resta il settlement simulato di flumine
(coda reale + delay in-play modellato dalla base TennisLab).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from flumine.utils import get_price

from .tennis_lab import TennisLabStrategy
from .tennis_score import TennisScore
from .tennis_winprob import p_match, estimate_holds

logger = logging.getLogger(__name__)

_BREAK_WINDOW_MS = 90_000  # finestra "appena brekkato" (90s)
SIDE_AGNOSTIC = {"any", "set1", "set2plus", "pressure", "calm", "setlead", "early",
                 "post_game"}
_POST_GAME_WINDOW_MS = 15_000  # finestra momentum dopo un cambio-game/break
SIDE_AWARE = {"serving", "receiving", "broke", "gotbroken", "fav_ahead"}
# condizioni MODELLO (win-prob vs mercato): fade dell'over-reaction
MODEL_CONDS = {"model_over", "model_under"}


class ScoreConditionedLab(TennisLabStrategy):
    """TennisLab + gate sullo stato di gioco (timeline score iniettata)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        lp = dict(kwargs.get("lab_params", {}) or {})
        self._cond: str = str(lp.pop("score_cond", "any")).lower()
        self._model_edge: float = float(lp.pop("model_edge", 0.05))
        self._best_of: int = int(lp.pop("best_of", 3))
        kwargs["lab_params"] = lp
        super().__init__(*args, **kwargs)
        self._tl: List[Tuple[float, TennisScore]] = []
        self._ti: int = 0
        # side_map: selection_id -> "home"|"away" (per condizioni side-aware)
        self.side_map: Dict[int, str] = {}
        # tracking eventi (break/game) DAI GAMES (serviceBreaks non e' popolato)
        self._prev_games: Optional[Tuple[int, int]] = None   # (home, away)
        self._prev_server: Optional[str] = None
        self._break_side: Optional[str] = None
        self._break_at_pt: int = 0
        self._game_event_pt: int = -10_000_000  # ultimo cambio-game (post_game window)
        self.stats.setdefault("skipped_nomap", 0)

    def set_timeline(self, timeline: List[Tuple[float, TennisScore]]) -> None:
        self._tl = timeline or []
        self._ti = 0

    def set_side_map(self, side_map: Dict[int, str]) -> None:
        self.side_map = {int(k): v for k, v in (side_map or {}).items()}

    # ------------------------------------------------- iniezione score
    def process_market_book(self, market: Any, mb: Any) -> None:
        pt = int(getattr(mb, "publish_time_epoch", 0) or 0)
        tl = self._tl
        if pt and tl:
            while self._ti + 1 < len(tl) and tl[self._ti + 1][0] <= pt:
                self._ti += 1
            if tl[self._ti][0] <= pt:
                new = tl[self._ti][1]
                if new is not None and (self.score is None or new.key() != self.score.key()):
                    self._update_events(new, pt)
                self.score = new
        super().process_market_book(market, mb)

    @staticmethod
    def _breaks(ts: TennisScore) -> Tuple[int, int]:
        sc = (ts.raw or {}).get("score", {}) if ts else {}
        h = sc.get("home", {}) or {}
        a = sc.get("away", {}) or {}
        try:
            return int(h.get("serviceBreaks") or 0), int(a.get("serviceBreaks") or 0)
        except (TypeError, ValueError):
            return 0, 0

    def _update_events(self, ts: TennisScore, pt: int) -> None:
        """Rileva cambio-game e BREAK dai GAMES (serviceBreaks non e' popolato).

        Break = il game e' stato vinto dal RIBATTITORE (chi ha guadagnato il game
        != chi serviva). post_game window aggiornata a ogni cambio-game.
        """
        gh, ga = ts.games_home, ts.games_away
        if gh is None or ga is None:
            return
        cur = (int(gh), int(ga))
        if self._prev_games is not None:
            pg = self._prev_games
            gained = None
            if cur[0] > pg[0]:
                gained = "home"
            elif cur[1] > pg[1]:
                gained = "away"
            if gained is not None:
                self._game_event_pt = pt
                # chi serviva quel game = il server PRIMA del cambio
                srv = self._prev_server
                if srv is not None and gained != srv:
                    self._break_side, self._break_at_pt = gained, pt  # break!
        self._prev_games = cur
        self._prev_server = ts.server

    # ------------------------------------------------- gate d'ingresso
    def _entry_allowed(self, mb: Any, sel: int) -> bool:
        cond = self._cond
        if cond == "any":
            return True
        ts = self.score
        if ts is None:
            return False  # senza punteggio non applichiamo condizioni -> fail-safe

        sh, sa = ts.sets_home or 0, ts.sets_away or 0
        gh, ga = ts.games_home or 0, ts.games_away or 0

        if cond == "set1":
            return (sh + sa) == 0
        if cond == "set2plus":
            return (sh + sa) >= 1
        if cond == "setlead":
            return abs(sh - sa) == 1
        if cond == "early":
            return (gh + ga) <= 3
        if cond == "pressure":
            return bool(ts.point_pressure)
        if cond == "calm":
            return not bool(ts.point_pressure)
        if cond == "post_game":
            pt = int(getattr(mb, "publish_time_epoch", 0) or 0)
            return (pt - self._game_event_pt) <= _POST_GAME_WINDOW_MS

        # --- side-aware: serve il lato del target ---
        side = self.side_map.get(int(sel))
        if side is None:
            self.stats["skipped_nomap"] += 1
            return False  # FAIL-SAFE: lato ignoto -> niente trade

        # --- MODELLO win-prob vs mercato (fade over-reaction) ---
        if cond in MODEL_CONDS:
            return self._model_signal(cond, side, sel, mb, ts)
        other = "away" if side == "home" else "home"
        if cond == "fav_ahead":
            # il TARGET (favorito) e' avanti di >=1 set
            sh, sa = ts.sets_home or 0, ts.sets_away or 0
            my = sh if side == "home" else sa
            opp = sa if side == "home" else sh
            return my > opp
        if cond == "serving":
            return ts.server == side
        if cond == "receiving":
            return ts.server == other
        if cond in ("broke", "gotbroken"):
            pt = int(getattr(mb, "publish_time_epoch", 0) or 0)
            if self._break_side is None or (pt - self._break_at_pt) > _BREAK_WINDOW_MS:
                return False
            return (self._break_side == side) if cond == "broke" \
                else (self._break_side == other)
        return False

    def _model_signal(self, cond: str, side: str, sel: int, mb: Any,
                      ts: TennisScore) -> bool:
        """True se il MODELLO win-prob diverge dal mercato oltre model_edge.

        model_under -> il target vale PIU' di quanto lo prezza il mercato (back).
        model_over  -> il target vale MENO (lay). side_map dice se il target e'
        home o away nello score; usiamo lo score per calcolare la win-prob 'giusta'.
        """
        sh, sa = ts.sets_home or 0, ts.sets_away or 0
        gh, ga = ts.games_home or 0, ts.games_away or 0
        hb, ab = ScoreConditionedLab._breaks(ts)  # (break subiti home, away) approx
        ha, hb_ = estimate_holds(hb, ab, gh, ga)
        a_serves = (ts.server == "home")
        # p_match calcola per "A" = home. Se target e' away, prendi il complemento.
        p_home = p_match(sh, sa, gh, ga, a_serves, ha, hb_, self._best_of)
        model_p = p_home if side == "home" else (1.0 - p_home)
        # prezzo di mercato del target (best-back) -> prob implicita
        price = None
        for r in mb.runners:
            if int(getattr(r, "selection_id", 0) or 0) == int(sel):
                ex = getattr(r, "ex", None)
                price = get_price(ex.available_to_back, 0) if ex else None
                break
        if not price or price <= 1.0:
            return False
        market_p = 1.0 / price
        if cond == "model_under":
            return (model_p - market_p) > self._model_edge   # sottovalutato -> back
        return (market_p - model_p) > self._model_edge       # sopravvalutato -> lay
