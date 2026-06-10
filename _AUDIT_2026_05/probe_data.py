"""
READ-ONLY data probe. Raccoglie le evidenze decisive:
 1. signal_history: edge medio vs pnl reale vs CLV (closing line value) per track/market
 2. model_performance: distribuzione BSS/Brier/ECE per target su TUTTE le leghe
 3. match_odds: snapshot_type disponibili + struttura market_key/label
 4. match_team_stats: stat_type disponibili (cerca xG)
NESSUNA scrittura.
"""
from __future__ import annotations
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db_client import get_supabase_client  # noqa: E402

c = get_supabase_client()


def section(t): print("\n" + "=" * 72 + f"\n{t}\n" + "=" * 72)


# ── 1. signal_history: edge creduto vs reso reale vs CLV ──────────────────
section("1. signal_history — edge vs PnL vs CLV (la prova dell'edge reale)")
rows = c.table("signal_history").select(
    "track,market,prob,odds,edge,stake,result,pnl,bss,closing_odds,clv,date"
).limit(10000).execute().data
print(f"righe lette: {len(rows)}")

def agg(rows, keyfn):
    g = defaultdict(lambda: {"n": 0, "edge": 0.0, "pnl": 0.0, "stake": 0.0,
                             "clv": 0.0, "clv_n": 0, "win": 0, "res_n": 0})
    for r in rows:
        k = keyfn(r)
        s = g[k]
        s["n"] += 1
        s["edge"] += (r.get("edge") or 0)
        s["pnl"] += (r.get("pnl") or 0)
        s["stake"] += (r.get("stake") or 0)
        if r.get("clv") is not None:
            s["clv"] += r["clv"]; s["clv_n"] += 1
        res = (r.get("result") or "").lower()
        if res in ("win", "won", "lose", "lost", "loss", "w", "l"):
            s["res_n"] += 1
            if res in ("win", "won", "w"):
                s["win"] += 1
    return g

def show(g):
    print(f"{'key':<22}{'N':>6}{'edge%avg':>10}{'ROI%':>9}{'CLV%avg':>10}{'win%':>8}")
    for k in sorted(g, key=lambda x: -g[x]["n"]):
        s = g[k]
        edge = 100 * s["edge"] / s["n"] if s["n"] else 0
        roi = 100 * s["pnl"] / s["stake"] if s["stake"] else 0
        clv = 100 * s["clv"] / s["clv_n"] if s["clv_n"] else float("nan")
        win = 100 * s["win"] / s["res_n"] if s["res_n"] else float("nan")
        print(f"{str(k):<22}{s['n']:>6}{edge:>10.2f}{roi:>9.2f}{clv:>10.2f}{win:>8.1f}")

print("\n-- per TRACK --")
show(agg(rows, lambda r: r.get("track")))
print("\n-- per MARKET --")
show(agg(rows, lambda r: r.get("market")))
# settled only
settled = [r for r in rows if (r.get("result") or "").lower() in
           ("win","won","lose","lost","loss","w","l")]
print(f"\nsegnali REGOLATI (con result win/lose): {len(settled)} / {len(rows)}")
tot_stake = sum(r.get("stake") or 0 for r in settled)
tot_pnl = sum(r.get("pnl") or 0 for r in settled)
clv_vals = [r["clv"] for r in settled if r.get("clv") is not None]
if tot_stake:
    print(f"ROI complessivo regolati: {100*tot_pnl/tot_stake:.2f}%  (stake={tot_stake:.0f}, pnl={tot_pnl:.0f})")
else:
    print("Nessun segnale regolato: result/pnl/clv NON popolati nel DB.")
# date range
dts = [r.get("date") for r in rows if r.get("date")]
if dts:
    print(f"range date segnali: {min(dts)} -> {max(dts)}")


# ── 2. model_performance: BSS per target su tutte le leghe ────────────────
section("2. model_performance — BSS/Brier/ECE per target (tutte le leghe)")
mp = c.table("model_performance").select(
    "league_id,target,n_classes,brier,brier_random,bss,ece,train_rows,trained_at"
).limit(5000).execute().data
print(f"righe: {len(mp)}")
gt = defaultdict(list)
for r in mp:
    gt[r["target"]].append(r)
import statistics as st
print(f"{'target':<26}{'N':>5}{'bss_med':>9}{'bss_>0.05':>10}{'ece_med':>9}{'brier_med':>10}")
for tgt in sorted(gt, key=lambda x: -len(gt[x])):
    rs = gt[tgt]
    bss = [r["bss"] for r in rs if r.get("bss") is not None]
    ece = [r["ece"] for r in rs if r.get("ece") is not None]
    bri = [r["brier"] for r in rs if r.get("brier") is not None]
    if not bss:
        continue
    pos = 100*sum(1 for x in bss if x > 0.05)/len(bss)
    print(f"{tgt:<26}{len(rs):>5}{st.median(bss):>9.3f}{pos:>9.0f}%{(st.median(ece) if ece else float('nan')):>9.3f}{(st.median(bri) if bri else float('nan')):>10.3f}")


# ── 3. match_odds snapshot types ──────────────────────────────────────────
section("3. match_odds — snapshot_type + market_key disponibili")
# sample by recent fixture to avoid full scan
od = c.table("match_odds").select("snapshot_type,market_key,label,odd_value,snapshot_time").limit(2000).execute().data
print(f"campione: {len(od)} righe")
snaps = defaultdict(int); mkts = defaultdict(int)
for r in od:
    snaps[r.get("snapshot_type")] += 1
    mkts[r.get("market_key")] += 1
print("snapshot_type:", dict(snaps))
print("market_key (top):", dict(sorted(mkts.items(), key=lambda x:-x[1])[:15]))
print("esempio righe:", od[:3])


# ── 4. match_team_stats stat_type (cerca xG) ──────────────────────────────
section("4. match_team_stats — stat_type disponibili (cerca xG)")
ts = c.table("match_team_stats").select("stat_type,value_numeric,value_text").limit(3000).execute().data
print(f"campione: {len(ts)} righe")
types = defaultdict(int)
for r in ts:
    types[r.get("stat_type")] += 1
for k,v in sorted(types.items(), key=lambda x:-x[1]):
    print(f"   {k:<32} {v}")
