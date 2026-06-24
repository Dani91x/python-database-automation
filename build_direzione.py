"""
build_direzione.py — popola la PAGELLA (tabella direction_pagella) dallo storico.

Per ogni motore (poisson, ml, tacticai) e ogni (mercato, selezione):
  - GLOBALE (league_id=0): hit-rate reale per fascia di probabilita' + base
  - PER-LEGA  (league_id>0): idem, dove il campione lo consente (n>=MIN_LEAGUE)
da public.bet_features (solo righe settled, con esito reale 'hit').

E' la fonte dell'AFFIDABILITA' del cruscotto Direzione. Sostituisce ENGINE_GRID_REPORT.json.
Idempotente: ricalcola e fa upsert (sovrascrive le righe per chiave). Rilanciabile.

Uso: python build_direzione.py
"""
import sys, datetime as dt
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd

ENGINES = {"poisson": "poisson_prob", "ml": "ml_prob", "tacticai": "tacticai_prob"}
# 1.01 (non 1.0) come estremo superiore: con right=False [lo,hi) cattura anche prob == 1.0
BINS = [0, .30, .40, .50, .60, .70, 1.01]
LBL = ["<.30", ".30-.40", ".40-.50", ".50-.60", ".60-.70", ">.70"]
CAL_MARKETS = ["1x2", "ht_1x2", "over_1_5", "over_2_5", "over_3_5", "btts", "first_half_over_0_5"]
MIN_GLOBAL = 20    # campione minimo per una fascia globale
MIN_LEAGUE = 10    # campione minimo per una fascia per-lega (lo shrinkage gestisce il resto)


def bucket_series(p: pd.Series) -> pd.Series:
    return pd.cut(p, BINS, labels=LBL, include_lowest=True, right=False).astype("object")


def load() -> pd.DataFrame:
    from db_client import get_supabase_client
    sb = get_supabase_client()
    cols = "league_id,market,selection,hit,poisson_prob,ml_prob,tacticai_prob"
    rows, start = [], 0
    while True:
        d = (sb.table("bet_features").select(cols)
             .eq("settled", True).in_("market", CAL_MARKETS)
             .order("fixture_id").range(start, start + 999).execute().data)
        rows.extend(d)
        if len(d) < 1000:
            break
        start += 1000
    df = pd.DataFrame(rows)
    # scarta righe senza esito (hit NULL): astype(bool) su NaN darebbe True -> falserebbe l'hit_rate
    df = df[df["hit"].notna()].copy()
    df["hit"] = df["hit"].astype(bool).astype(int)
    for c in ENGINES.values():
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def agg_scope(df: pd.DataFrame, engine: str, col: str, league_id: int, min_n: int) -> list[dict]:
    """Righe pagella per uno scope (globale o una singola lega)."""
    sub = df[df[col].notna()].copy()
    if sub.empty:
        return []
    sub["bucket"] = bucket_series(sub[col])
    sub = sub[sub["bucket"].notna()]
    out = []
    # base_rate per (market, selection) nello scope
    base = sub.groupby(["market", "selection"])["hit"].mean().to_dict()
    grp = sub.groupby(["market", "selection", "bucket"], observed=True)["hit"].agg(["size", "sum"])
    for (market, selection, bkt), row in grp.iterrows():
        n = int(row["size"])
        if n < min_n:
            continue
        out.append({
            "engine": engine, "market": market, "selection": selection,
            "league_id": int(league_id), "prob_bucket": str(bkt),
            "n": n, "hits": int(row["sum"]),
            "hit_rate": round(float(row["sum"]) / n, 4),
            "base_rate": round(float(base.get((market, selection), np.nan)), 4),
        })
    return out


def build(df: pd.DataFrame) -> list[dict]:
    rows = []
    for engine, col in ENGINES.items():
        # GLOBALE
        rows += agg_scope(df, engine, col, 0, MIN_GLOBAL)
        # PER-LEGA
        dl = df[df["league_id"].notna()]
        for lid, g in dl.groupby("league_id"):
            rows += agg_scope(g, engine, col, int(lid), MIN_LEAGUE)
    return rows


def main():
    from db_client import get_supabase_client
    sb = get_supabase_client()
    df = load()
    print(f"Storico: {len(df)} righe settled su {len(CAL_MARKETS)} mercati.")
    if df.empty:
        print("ATTENZIONE: zero righe settled. Interrompo per non svuotare la pagella.", file=sys.stderr)
        sys.exit(1)
    rows = build(df)
    if not rows:
        print("ATTENZIONE: zero righe pagella calcolate. Interrompo per sicurezza.", file=sys.stderr)
        sys.exit(1)
    print(f"Pagella: {len(rows)} righe da scrivere "
          f"({sum(r['league_id']==0 for r in rows)} globali + {sum(r['league_id']>0 for r in rows)} per-lega).")

    # Scrittura SICURA (no finestra vuota): upsert sulla PK -> aggiorna/inserisce, poi
    # cancella le sole righe STALE (generato in un run precedente). Mai delete-then-insert.
    run_ts = dt.datetime.now(dt.timezone.utc).isoformat()
    for r in rows:
        r["generated_at"] = run_ts
    pk = "engine,market,selection,league_id,prob_bucket"
    for i in range(0, len(rows), 500):
        res = sb.table("direction_pagella").upsert(rows[i:i + 500], on_conflict=pk).execute()
        if not res.data:
            raise RuntimeError(f"Upsert batch {i // 500} fallito: risposta vuota dal DB.")
    sb.table("direction_pagella").delete().lt("generated_at", run_ts).execute()  # rimuove gli stale
    tot = sb.table("direction_pagella").select("engine", count="exact").limit(1).execute()
    print(f"Scritte. Totale in DB: {tot.count} righe.  ({dt.datetime.now():%H:%M:%S})")


if __name__ == "__main__":
    main()
