"""certify_backtest_strategy.py — CERTIFICAZIONE money-critical dell'RPC
backtest_strategy: ricalcola in Python, in modo INDIPENDENTE dal DB, ROI/hit/Wilson
su una finestra delimitata e confronta riga-per-riga con l'output dell'RPC.

Oracolo indipendente: legge le tabelle GREZZE (analytics_signals, analytics_decisions,
fixture_predictions) via service-role, ricostruisce le scommesse (pivot), aggancia la
quota con la STESSA catena (Betfair piazzata→media, fallback bookmaker), calcola P&L
netto 5% e Wilson — SENZA usare la vista né l'RPC. Poi chiama l'RPC e pretende parità.

Uso:  python certify_backtest_strategy.py
"""
from __future__ import annotations
import math
import sys
from collections import defaultdict
from datetime import date, timedelta

sys.path.insert(0, ".")
from db_client import get_supabase_client

MARKET, SELECTION = "over_2_5", "Over"
DATE_FROM, DATE_TO = "2026-05-01", "2026-05-15"   # finestra delimitata
COMM = 0.05
Z = 1.96


# ---- replica INDIPENDENTE di book_odds (mappa canonico → quota bookmaker) ----
def book_odds(raw: dict, market: str, selection: str):
    if not isinstance(raw, dict):
        return None
    if market == "1x2":
        bet_name = "Match Winner"; val = {"H": "Home", "D": "Draw", "A": "Away"}.get(selection)
    elif market == "ht_1x2":
        bet_name = "First Half Winner"; val = {"H": "Home", "D": "Draw", "A": "Away"}.get(selection)
    elif market == "btts":
        bet_name = "Both Teams Score"; val = selection
    elif market.startswith("first_half_over_"):
        bet_name = "Goals Over/Under First Half"; val = f"{selection} {market.split('first_half_over_')[1].replace('_', '.')}"
    elif market.startswith("over_"):
        bet_name = "Goals Over/Under"; val = f"{selection} {market.split('over_')[1].replace('_', '.')}"
    else:
        return None
    if val is None:
        return None
    found = []
    for bk in (raw.get("bookmakers") or []):
        for bet in (bk.get("bets") or []):
            if bet.get("name") != bet_name:
                continue
            for v in (bet.get("values") or []):
                if v.get("value") == val:
                    try:
                        found.append(float(v.get("odd")))
                    except (TypeError, ValueError):
                        pass
    return min(found) if found else None


def wilson(n_hit: int, n: int):
    if n == 0:
        return (None, None)
    p = n_hit / n
    denom = 1 + Z * Z / n
    center = (p + Z * Z / (2 * n)) / denom
    half = (Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n))) / denom
    return (center - half, center + half)


def fetch_all(sb, table, select, **eq):
    out, off = [], 0
    while True:
        q = sb.table(table).select(select)
        for k, v in eq.items():
            q = q.eq(k, v)
        if table == "analytics_signals":
            # boundary identica all'RPC: kickoff < (date_to + 1 giorno)
            q = q.gte("kickoff", DATE_FROM).lt("kickoff", (date.fromisoformat(DATE_TO) + timedelta(days=1)).isoformat())
        r = q.range(off, off + 999).execute().data
        if not r:
            break
        out += r
        if len(r) < 1000:
            break
        off += 1000
    return out


def main():
    sb = get_supabase_client()
    print(f"Certifico backtest {MARKET}/{SELECTION} finestra {DATE_FROM}..{DATE_TO}")

    # ---- 1) ORACOLO INDIPENDENTE dalle tabelle grezze ----
    sigs = fetch_all(sb, "analytics_signals",
                     "fixture_id,engine,prob,settled,hit,kickoff",
                     market=MARKET, selection=SELECTION)
    fids = sorted({s["fixture_id"] for s in sigs})
    print(f"  fixtures (scommesse) nella finestra: {len(fids)} | righe-motore: {len(sigs)}")

    # decisioni (quota Betfair) per fixture
    dec = defaultdict(list)
    for i in range(0, len(fids), 200):
        chunk = fids[i:i + 200]
        rows = (sb.table("analytics_decisions")
                .select("fixture_id,status,odds")
                .eq("market", MARKET).eq("selection", SELECTION)
                .in_("fixture_id", chunk).execute().data)
        for d in rows:
            dec[d["fixture_id"]].append(d)

    # raw_json_odds per il fallback bookmaker
    raw_by_fid = {}
    for i in range(0, len(fids), 100):
        chunk = fids[i:i + 100]
        rows = (sb.table("fixture_predictions")
                .select("fixture_id,raw_json_odds")
                .in_("fixture_id", chunk).execute().data)
        for r in rows:
            raw_by_fid[r["fixture_id"]] = r.get("raw_json_odds")

    # pivot per scommessa (qui market/selection sono fissi → 1 bet per fixture)
    bet = {}
    for s in sigs:
        b = bet.setdefault(s["fixture_id"], {"settled": False, "hit": None})
        if s["settled"]:
            b["settled"] = True
        if s["hit"] is not None:
            b["hit"] = s["hit"]

    # quota per scommessa (catena: Betfair placed→media, fallback bookmaker)
    odds_of = {}
    for fid in bet:
        ds = dec.get(fid, [])
        placed = [d["odds"] for d in ds if d["status"] == "PLACED" and d["odds"] is not None]
        allo = [d["odds"] for d in ds if d["odds"] is not None]
        odds_bf = (max(placed) if placed else (sum(allo) / len(allo) if allo else None))
        odds_of[fid] = odds_bf if odds_bf is not None else book_odds(raw_by_fid.get(fid), MARKET, SELECTION)

    def recompute(direction: str):
        n = n_settled = n_hit = n_priced = n_unpriced = 0
        profit = turnover = 0.0
        for fid, b in bet.items():
            n += 1
            odds = odds_of[fid]
            if not b["settled"]:
                continue
            n_settled += 1
            if b["hit"]:
                n_hit += 1
            if odds is None:
                n_unpriced += 1
                continue
            n_priced += 1
            if direction == "back":
                pnl = (odds - 1) * (1 - COMM) if b["hit"] else -1.0
                staked = 1.0
            else:  # lay: vince se la selezione NON si verifica
                pnl = -(odds - 1) if b["hit"] else (1 - COMM)
                staked = (odds - 1)
            profit += pnl
            turnover += staked
        hit_rate = n_hit / n_settled if n_settled else None
        wl, wh = wilson(n_hit, n_settled)
        roi = profit / turnover if turnover else None
        return dict(n=n, n_settled=n_settled, n_hit=n_hit, hit_rate=hit_rate,
                    wilson_low=wl, wilson_high=wh, n_priced=n_priced, n_unpriced=n_unpriced,
                    profit=profit, turnover=turnover, roi=roi)

    all_ok = True
    for direction in ("back", "lay"):
        o = recompute(direction)
        r = sb.rpc("backtest_strategy", {
            "p_market": MARKET, "p_selection": SELECTION,
            "p_date_from": DATE_FROM, "p_date_to": DATE_TO,
            "p_direction": direction, "p_odds_source": "betfair_book",
            "p_commission": COMM, "p_group_by": "overall",
        }).execute().data
        assert r, f"RPC vuota ({direction})"
        r = r[0]
        print(f"\n  === {direction.upper()} ===")
        print(f"  oracolo: n={o['n']} settled={o['n_settled']} hit={o['n_hit']} "
              f"hit_rate={o['hit_rate']:.6f} profit={o['profit']:.4f} turnover={o['turnover']:.4f} roi={o['roi']:.6f}")
        print(f"  rpc    : n={r['n']} settled={r['n_settled']} hit={r['n_hit']} "
              f"hit_rate={float(r['hit_rate']):.6f} profit={float(r['profit']):.4f} turnover={float(r['turnover']):.4f} roi={float(r['roi']):.6f}")
        errs = []
        def chk(name, a, b, tol=0.0):
            if a is None or b is None:
                if a != b:
                    errs.append(f"{name}: oracolo={a} rpc={b}")
            elif abs(float(a) - float(b)) > tol:
                errs.append(f"{name}: oracolo={a} rpc={b} (d={abs(float(a)-float(b)):.6g})")
        for k, tol in (("n", 0), ("n_settled", 0), ("n_hit", 0), ("hit_rate", 1e-5),
                       ("wilson_low", 1e-5), ("wilson_high", 1e-5), ("n_priced", 0),
                       ("n_unpriced", 0), ("profit", 1e-3), ("turnover", 1e-3), ("roi", 1e-5)):
            chk(k, o[k], r[k], tol)
        print("  " + ("[OK] oracolo == RPC" if not errs else "[FAIL]\n   " + "\n   ".join(errs)))
        all_ok = all_ok and not errs

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
