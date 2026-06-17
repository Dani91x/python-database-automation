"""
calibrate.py — calibra la distribuzione TEMPORALE dei gol dai dati reali (match_events) e salva
una CDF empirica (value_engine/data/goal_time_cdf.json) usata da goal_timing.py.

Sostituisce l'ipotesi di intensita' costante (frazione lineare (T-t)/T) con la curva reale:
nel calcio i gol sono piu' frequenti nel 2o tempo e in chiusura.

SICUREZZA: solo SELECT su match_events. Esegui:  python -m value_engine.calibrate
"""
from __future__ import annotations
import os
import sys
import json

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from db_client import get_supabase_client

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "goal_time_cdf.json")
MAX_GOALS_FETCH = 120_000   # campione ampio e sufficiente per una CDF stabile
PAGE = 1000


def fetch_goal_minutes() -> list[int]:
    """Scarica i minuti dei gol reali (escludendo i rigori sbagliati).
    Bucketing per MINUTO REGOLAMENTARE: lo stoppage di 1o tempo conta a 45, quello di fine partita
    a 90 (coerente con come i mercati HT/FT si risolvono; per questo minute_extra non viene sommato).
    Niente ORDER BY: su una tabella >1M righe il sort + offset profondo va in timeout; lo scan naturale
    e' veloce e la FORMA della curva (validata vs la regolarita' universale ~45/55 + late-surge) e' la
    garanzia anti-bias."""
    sb = get_supabase_client()
    minutes: list[int] = []
    start = 0
    while len(minutes) < MAX_GOALS_FETCH:
        resp = (sb.table("match_events")
                .select("minute, detail")
                .eq("event_type", "Goal")
                .range(start, start + PAGE - 1)
                .execute())
        rows = resp.data or []
        if not rows:
            break
        for r in rows:
            if "missed" in (r.get("detail") or "").lower():   # esclude rigori sbagliati (case-insensitive)
                continue
            m = r.get("minute")
            if m is None:
                continue
            m = int(m)
            if m < 1:
                m = 1
            elif m > 90:                                       # supplementari/recupero -> bucket 90
                m = 90
            minutes.append(m)
        start += PAGE
        if len(rows) < PAGE:
            break
    return minutes


def build_cdf(minutes: list[int]) -> list[float]:
    """CDF cumulativa per minuto 0..90 (cdf[t] = frazione di gol entro il minuto t incluso)."""
    hist = [0] * 91                       # indice 0 = pre-calcio (sempre 0); 1..90 = gol in quel minuto
    for m in minutes:
        hist[m] += 1
    total = sum(hist) or 1
    cdf = [0.0] * 91
    cum = 0
    for t in range(91):
        cum += hist[t]
        cdf[t] = cum / total
    cdf[90] = 1.0                          # forza normalizzazione
    return cdf


def main() -> None:
    print("Scarico i minuti dei gol da match_events (read-only)...")
    minutes = fetch_goal_minutes()
    print(f"Gol campionati: {len(minutes)}")
    if len(minutes) < 5000:
        print("ATTENZIONE: campione piccolo, CDF poco affidabile.")
    cdf = build_cdf(minutes)

    # diagnostica: distribuzione per fasce di 15'
    buckets = [(1, 15), (16, 30), (31, 45), (46, 60), (61, 75), (76, 90)]
    print("\nDistribuzione gol per fascia (validazione forma curva):")
    for lo, hi in buckets:
        share = cdf[hi] - cdf[lo - 1]
        print(f"  {lo:2d}-{hi:2d}': {share*100:5.1f}%")
    fh = cdf[45]
    print(f"  -> 1o tempo {fh*100:.1f}%  |  2o tempo {(1-fh)*100:.1f}%  (atteso ~45/55)")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"n_goals": len(minutes), "cdf_by_minute": cdf,
                   "first_half_share": fh}, f)
    print(f"\n[OK] CDF salvata: {OUT}")


if __name__ == "__main__":
    main()
