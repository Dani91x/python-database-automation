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
import random, sys, time, datetime as dt
sys.stdout.reconfigure(encoding="utf-8")
import httpx
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


PAGE = 5000      # righe per blocco RICHIESTE (il server puo' restituirne meno)
PAGE_MIN = 250   # blocco minimo dopo i dimezzamenti sui transitori
RETRY = 5        # tentativi su errori TRANSITORI

# Errori TRANSITORI (si ritentano): statement timeout, DB occupato/riavvio,
# deadlock, connessione persa, 5xx del gateway, PGRST002 (schema cache).
# Gli errori LOGICI (4xx di validazione, colonna inesistente) NON si ritentano.
_TRANSIENT_CODES = {"57014", "53300", "53400", "55P03", "40001", "40P01",
                    "08006", "08003", "08000", "57P01", "57P02", "57P03",
                    "PGRST002", "408", "500", "502", "503", "504"}

# SOLO le colonne usate dal calcolo: league_id/market/selection (groupby), hit
# (esito), poisson_prob/ml_prob/tacticai_prob (ENGINES). fixture_id serve come
# CURSORE della paginazione keyset e viene scartato prima del calcolo.
COLS = "fixture_id,league_id,market,selection,hit,poisson_prob,ml_prob,tacticai_prob"


def _is_transient(e: Exception) -> bool:
    """True solo per gli errori che ha senso ritentare."""
    if isinstance(e, httpx.TransportError):   # ReadTimeout, ConnectError, PoolTimeout...
        return True
    code = getattr(e, "code", None)
    if code is not None and str(code) in _TRANSIENT_CODES:
        return True
    msg = str(getattr(e, "message", "") or "").lower()
    return "timeout" in msg or "temporarily unavailable" in msg


def _sleep_backoff(attempt: int) -> None:
    """Attesa crescente con jitter (0,7x-1,3x)."""
    time.sleep(min(8.0, 0.5 * (2 ** attempt)) * (0.7 + random.random() * 0.6))


def _con_retry(call, what: str):
    """Esegue una chiamata al DB ritentando i SOLI errori transitori (backoff con
    jitter). Se non riesce, l'errore ESCE: nessuna scrittura data per fatta."""
    for attempt in range(RETRY):
        try:
            return call()
        except Exception as e:  # noqa: BLE001
            if not _is_transient(e) or attempt == RETRY - 1:
                raise RuntimeError(f"{what}: fallito dopo {attempt + 1} tentativi: "
                                   f"{type(e).__name__}: {str(e)[:120]}") from e
            _sleep_backoff(attempt)


def _base_query(sb):
    return (sb.table("bet_features").select(COLS)
            .eq("settled", True).in_("market", CAL_MARKETS).order("fixture_id"))


def _fetch_block(sb, cursor, limit: int) -> tuple[list[dict], int]:
    """UN blocco keyset (fixture_id >= cursor), con retry sui transitori e blocco
    ADATTIVO: su 57014/timeout attende e dimezza. Ritorna (righe, limite usato).
    Se non ce la fa, l'errore ESCE (nessun dato perso in silenzio)."""
    for attempt in range(RETRY):
        try:
            q = _base_query(sb)
            if cursor is not None:
                q = q.gte("fixture_id", cursor)
            return (q.limit(limit).execute().data or []), limit
        except Exception as e:  # noqa: BLE001
            if not _is_transient(e) or attempt == RETRY - 1:
                raise RuntimeError(
                    f"bet_features: blocco da {limit} righe (cursore {cursor}) non letto "
                    f"dopo {attempt + 1} tentativi: {type(e).__name__}: {str(e)[:120]}") from e
            _sleep_backoff(attempt)
            limit = max(PAGE_MIN, limit // 2)
    raise RuntimeError("bet_features: retry esauriti")   # irraggiungibile


def _fetch_one_fixture(sb, fixture_id: int) -> list[dict]:
    """Tutte le righe di UNA fixture (caso limite: un solo fixture_id riempie il
    blocco). Poche righe: 1 mercato x selezione, ~16 nei 7 mercati calibrati.
    ORDER BY fixture_id,market,selection = chiave primaria di analytics_bets,
    quindi ordine TOTALE; si esce solo a pagina vuota; retry sui transitori."""
    out, off = [], 0
    while True:
        d = _con_retry(
            lambda off=off: (_base_query(sb).eq("fixture_id", fixture_id)
                             .order("market").order("selection")
                             .range(off, off + 999).execute().data or []),
            f"bet_features fixture {fixture_id} (offset {off})")
        if not d:
            break
        out.extend(d)
        off += len(d)
    return out


def load() -> pd.DataFrame:
    from db_client import get_supabase_client
    sb = get_supabase_client()
    # PAGINAZIONE KEYSET (non OFFSET): l'OFFSET profondo rilegge e scarta tutte le
    # righe precedenti a ogni blocco (misurato: offset 45.000 = 3,65 s contro 0,12 s
    # del keyset) e a fine storico supera lo statement_timeout di 8s -> 57014 -> la
    # pagella resta quella del giorno prima. `fixture_id >= cursore` diventa invece
    # una Index Cond sulla pkey di analytics_bets (costo costante per blocco).
    # CONFINE: fixture_id NON e' unico nella vista (piu' mercati/selezioni per
    # fixture) e l'ordine FRA PARI non e' garantito; percio' l'ultimo gruppo di ogni
    # blocco viene SCARTATO e RILETTO INTERO dal blocco successivo -> nessuna riga
    # saltata ne' duplicata, stesso identico insieme di righe dell'OFFSET corretto.
    rows: list[dict] = []
    cursor, limit = None, PAGE
    while True:
        block, limit = _fetch_block(sb, cursor, limit)
        if not block:
            break
        last_fid = block[-1]["fixture_id"]
        keep = [r for r in block if r["fixture_id"] < last_fid]
        if keep:
            rows.extend(keep)
            cursor = last_fid
            continue
        # il blocco contiene UNA sola fixture: leggila tutta e passa alla successiva
        # (fixture_id e' intero, quindi +1 non salta nulla).
        rows.extend(_fetch_one_fixture(sb, last_fid))
        cursor = last_fid + 1
    df = pd.DataFrame(rows)
    if df.empty:
        return df                      # main() lo intercetta e si ferma
    df = df.drop(columns=["fixture_id"])
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
    # ORDINE OBBLIGATORIO: prima TUTTI gli upsert, poi il delete degli stale. Se un
    # upsert non riesce (anche dopo i retry) l'eccezione esce QUI e il delete NON
    # viene eseguito: la pagella resta quella del giorno prima, mai mezza nuova e
    # mezza cancellata.
    for i in range(0, len(rows), 500):
        res = _con_retry(
            lambda i=i: sb.table("direction_pagella").upsert(rows[i:i + 500], on_conflict=pk).execute(),
            f"upsert direction_pagella blocco {i // 500}")
        if not res.data:
            raise RuntimeError(f"Upsert batch {i // 500} fallito: risposta vuota dal DB.")
    _con_retry(lambda: sb.table("direction_pagella").delete().lt("generated_at", run_ts).execute(),
               "delete righe stale")  # rimuove gli stale SOLO dopo tutti gli upsert
    tot = _con_retry(lambda: sb.table("direction_pagella").select("engine", count="exact").limit(1).execute(),
                     "conteggio direction_pagella")
    print(f"Scritte. Totale in DB: {tot.count} righe.  ({dt.datetime.now():%H:%M:%S})")


if __name__ == "__main__":
    main()
