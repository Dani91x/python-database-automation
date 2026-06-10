"""
BACKTEST POINT-IN-TIME (zero leak).

Per ogni partita, in ordine cronologico:
  - il modello DC è addestrato SOLO su partite con data < kickoff
  - le probabilità sono calibrate (isotonic) SOLO su partite gia' risolte in passato
  - le quote usate sono pre-kickoff (apertura o chiusura, entrambe disponibili prima)
  - si confronta prob modello vs quota, si calcola edge, si decide la scommessa
  - si regola con il risultato reale e si registrano PnL e CLV (vs Pinnacle closing)

Simula esattamente "una partita oggi": nessuna informazione dal futuro.
"""
from __future__ import annotations
import math
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

from dc_model import fit_dc, predict_markets
from devig import devig_multiplicative, devig_shin

# mercati 1X2 (market_key 1) e Over/Under 2.5 (market_key 5)
MK1_LABELS = {"H": "Home", "D": "Draw", "A": "Away"}
MK5_LABELS = {"O25": "Over 2.5", "U25": "Under 2.5"}


def outcome(sel: str, gh: int, ga: int) -> bool:
    if sel == "H": return gh > ga
    if sel == "D": return gh == ga
    if sel == "A": return gh < ga
    if sel == "O25": return (gh + ga) >= 3
    if sel == "U25": return (gh + ga) <= 2
    if sel == "BTTS": return gh > 0 and ga > 0
    if sel == "BTTS_NO": return not (gh > 0 and ga > 0)
    if sel == "O15": return (gh + ga) >= 2
    if sel == "U15": return (gh + ga) <= 1
    if sel == "O35": return (gh + ga) >= 4
    if sel == "U35": return (gh + ga) <= 3
    raise ValueError(sel)


@dataclass
class Config:
    half_life_days: float = 180.0
    refit_every_days: int = 7
    rho: float = -0.13
    l2_alpha: float = 1e-4
    max_history_days: int = 1000    # finestra storica (time-decay rende vecchio dato ~0)
    min_history: int = 150          # partite minime di storico prima di iniziare
    warmup_seasons: int = 1
    # calibrazione walk-forward
    calibrate: bool = True
    calib_min_samples: int = 400
    calib_refit_every: int = 150     # rifit isotonic ogni N partite processate
    # betting
    markets: tuple = ("H", "D", "A", "O25", "U25")
    bet_book: str = "Maximum"        # book su cui scommettere (best price). opening.
    anchor_book: str = "Pinnacle_closing"  # linea sharp per fair prob & CLV
    edge_threshold: float = 0.03     # EV minimo
    # blending modello<->mercato (anti winner's curse). 0=puro modello, 1=puro mercato.
    # blend_book = consenso di mercato disponibile a bet-time (apertura), leak-free.
    blend_weight: float = 0.0
    blend_book: str = "Average"
    min_odds: float = 1.40
    max_odds: float = 8.0
    stake_mode: str = "flat"         # "flat" | "kelly"
    kelly_frac: float = 0.25
    commission: float = 0.0          # book odds: 0 (no commission); Betfair userebbe 0.05
    devig_method: str = "shin"       # "shin" | "mult"


@dataclass
class Result:
    bets: pd.DataFrame = field(default_factory=pd.DataFrame)

    def summary(self) -> dict:
        b = self.bets
        if b.empty:
            return {"n": 0}
        stake = b["stake"].sum()
        pnl = b["pnl"].sum()
        clv = b["clv"].dropna()
        return {
            "n": len(b),
            "roi_pct": 100 * pnl / stake if stake else 0.0,
            "pnl": pnl, "stake": stake,
            "hit_pct": 100 * b["win"].mean(),
            "avg_odds": b["odds"].mean(),
            "avg_edge_pct": 100 * b["edge"].mean(),
            "clv_pct": 100 * clv.mean() if len(clv) else float("nan"),
            "clv_pos_pct": 100 * (clv > 0).mean() if len(clv) else float("nan"),
        }


def _fair_from_anchor(odds_wide_row, book: str, labels: dict, method: str):
    """De-vig della linea sharp per ottenere fair prob. None se manca."""
    cols = [f"{book}__{lab}" for lab in labels.values()]
    vals = [odds_wide_row.get(c) for c in cols]
    if any(v is None or (isinstance(v, float) and math.isnan(v)) or v is None for v in vals):
        return None
    try:
        vals = [float(v) for v in vals]
    except (TypeError, ValueError):
        return None
    if any(v <= 1.0 for v in vals):
        return None
    p = devig_shin(vals) if method == "shin" else devig_multiplicative(vals)
    return dict(zip(labels.keys(), p))


def run_backtest(matches: pd.DataFrame, odds1: pd.DataFrame, odds5: pd.DataFrame,
                 cfg: Config, league_id: int = 0) -> Result:
    m = matches.sort_values("fixture_date").reset_index(drop=True).copy()
    o1 = odds1.set_index("fixture_id") if (odds1 is not None and not odds1.empty) else pd.DataFrame()
    o5 = odds5.set_index("fixture_id") if (odds5 is not None and not odds5.empty) else pd.DataFrame()

    # buffer calibrazione: market -> (raw_probs[], outcomes[])
    calib_buf = defaultdict(lambda: ([], []))
    calibrators: dict = {}
    since_calib = 0

    model = None
    model_date = None
    bets = []

    start_date = m["fixture_date"].iloc[0] + pd.Timedelta(days=365 * cfg.warmup_seasons)

    for _, row in m.iterrows():
        kickoff = row["fixture_date"]
        if kickoff < start_date:
            continue
        past_all = m[m["fixture_date"] < kickoff]
        if len(past_all) < cfg.min_history:
            continue
        cutoff = kickoff - pd.Timedelta(days=cfg.max_history_days)
        past = past_all[past_all["fixture_date"] >= cutoff]

        # refit modello se stale (fit su finestra; fallback all-history se finestra povera)
        if model is None or model_date is None or (kickoff - model_date).days >= cfg.refit_every_days:
            fit_src = past if len(past) >= cfg.min_history else past_all
            model = fit_dc(fit_src, kickoff, cfg.half_life_days, cfg.l2_alpha, cfg.rho)
            model_date = kickoff
        if model is None:
            continue

        pred = predict_markets(model, row["home_team_id"], row["away_team_id"])
        if pred is None:
            continue

        gh, ga = int(row["goals_home"]), int(row["goals_away"])
        fid = row["fixture_id"]

        # refit calibratori periodicamente (solo su passato già nel buffer)
        if cfg.calibrate and since_calib >= cfg.calib_refit_every:
            for mk, (raws, outs) in calib_buf.items():
                if len(raws) >= cfg.calib_min_samples:
                    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
                    try:
                        iso.fit(raws, outs)
                        calibrators[mk] = iso
                    except Exception:
                        pass
            since_calib = 0

        # anchor fair probs (sharp, Pinnacle closing) per CLV/diagnostica
        row1 = o1.loc[fid].to_dict() if (not o1.empty and fid in o1.index) else None
        row5 = o5.loc[fid].to_dict() if (not o5.empty and fid in o5.index) else None
        fair1 = _fair_from_anchor(row1, cfg.anchor_book, MK1_LABELS, cfg.devig_method) if row1 else None
        fair5 = _fair_from_anchor(row5, cfg.anchor_book, MK5_LABELS, cfg.devig_method) if row5 else None
        # blend anchor (consenso apertura, leak-free) per shrink anti-winner's-curse
        bl1 = _fair_from_anchor(row1, cfg.blend_book, MK1_LABELS, cfg.devig_method) if (row1 and cfg.blend_weight > 0) else None
        bl5 = _fair_from_anchor(row5, cfg.blend_book, MK5_LABELS, cfg.devig_method) if (row5 and cfg.blend_weight > 0) else None

        for sel in cfg.markets:
            raw = pred.get(sel)
            if raw is None:
                continue
            # calibrazione
            p = raw
            if cfg.calibrate and sel in calibrators:
                p = float(calibrators[sel].predict([raw])[0])
                p = min(max(p, 1e-4), 0.9999)

            # quota su cui scommettere + blend col consenso di mercato
            if sel in MK1_LABELS:
                book_col = f"{cfg.bet_book}__{MK1_LABELS[sel]}"
                src = o1
                fair = fair1
                blend_fair = bl1
            elif sel in MK5_LABELS:
                book_col = f"{cfg.bet_book}__{MK5_LABELS[sel]}"
                src = o5
                fair = fair5
                blend_fair = bl5
            else:
                continue
            # shrink anti-winner's-curse verso il consenso di apertura
            if cfg.blend_weight > 0 and blend_fair is not None and sel in blend_fair:
                p = (1 - cfg.blend_weight) * p + cfg.blend_weight * blend_fair[sel]
            if src.empty or fid not in src.index or book_col not in src.columns:
                continue
            odds = src.loc[fid].get(book_col)
            if odds is None or (isinstance(odds, float) and math.isnan(odds)):
                continue
            odds = float(odds)
            if not (cfg.min_odds <= odds <= cfg.max_odds):
                continue

            odds_net = (odds - 1.0) * (1.0 - cfg.commission) + 1.0
            edge = p * odds_net - 1.0
            if edge < cfg.edge_threshold:
                continue

            # staking
            if cfg.stake_mode == "kelly":
                b = odds_net - 1.0
                k = (p * b - (1 - p)) / b if b > 0 else 0.0
                stake = max(0.0, k * cfg.kelly_frac)
                stake = min(stake, 0.05)  # cap 5% bankroll-unit
            else:
                stake = 1.0
            if stake <= 0:
                continue

            won = outcome(sel, gh, ga)
            pnl = stake * (odds_net - 1.0) if won else -stake

            # CLV vs anchor sharp
            clv = float("nan")
            if fair is not None and sel in fair and fair[sel] > 0:
                fair_odds = 1.0 / fair[sel]
                clv = odds / fair_odds - 1.0  # quota presa vs quota equa sharp

            bets.append({
                "league": league_id, "date": kickoff, "fixture_id": fid, "market": sel,
                "raw": raw, "prob": p, "odds": odds, "edge": edge,
                "stake": stake, "win": int(won), "pnl": pnl, "clv": clv,
            })

        # aggiorna buffer calibrazione DOPO aver scommesso (outcome ora noto, è passato)
        for sel in cfg.markets:
            raw = pred.get(sel)
            if raw is None:
                continue
            raws, outs = calib_buf[sel]
            raws.append(raw)
            outs.append(int(outcome(sel, gh, ga)))
        since_calib += 1

    return Result(pd.DataFrame(bets))


if __name__ == "__main__":
    import sys
    from dataload import get_league_data
    lid = int(sys.argv[1]) if len(sys.argv) > 1 else 78
    m, odds = get_league_data(lid)
    cfg = Config()
    res = run_backtest(m, odds.get("1"), odds.get("5"), cfg, lid)
    print("SUMMARY:", res.summary())
    if not res.bets.empty:
        print("\nPer market:")
        for mk, g in res.bets.groupby("market"):
            st = g["stake"].sum(); pnl = g["pnl"].sum()
            clv = g["clv"].dropna()
            print(f"  {mk:6s} n={len(g):5d} roi={100*pnl/st:7.2f}%  hit={100*g['win'].mean():5.1f}%  "
                  f"avgodds={g['odds'].mean():.2f}  clv={100*clv.mean() if len(clv) else float('nan'):6.2f}%")
