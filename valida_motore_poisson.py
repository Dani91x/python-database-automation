"""
valida_motore_poisson.py — VALIDAZIONE ISOLATA del motore POISSON.

Per ogni partita FT legge db_json_analisi.markets (le PROBABILITA' Poisson, non
gli score del ventaglio) e misura il motore da solo:
  1. accuratezza DIREZIONALE per mercato  (la scelta argmax/binaria azzecca?)
  2. CALIBRAZIONE per fascia di convinzione (quando dice ~70% succede ~70%?)
  3. lista delle miss ad alta convinzione (>=70%) = gli errori che fanno male

Uso:  python valida_motore_poisson.py            (18 Betfair 2026-06-19)
      python valida_motore_poisson.py <fid...>
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from collections import defaultdict

from dotenv import load_dotenv

load_dotenv()
URL = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
H = {"apikey": KEY, "Authorization": "Bearer " + KEY}

DEFAULT_FIDS = [
    1529745, 1553788, 1529747, 1495868, 1553787, 1492916, 1492917, 1492915,
    1492717, 1492718, 1492919, 1492918, 1492719, 1492720, 1553786, 1492716,
    1514209, 1499479,
]

# label -> (chiave Poisson, tipo)   tipo: 'ou'(usa tot), 'htou'(usa htot), 'btts', '1x2', 'ht1x2'
MARKETS = [
    ("O/U 1.5", "over_1_5", "ou", 2),
    ("O/U 2.5", "over_2_5", "ou", 3),
    ("O/U 3.5", "over_3_5", "ou", 4),
    ("HT Over 0.5", "first_half_over_0_5", "htou", 1),
    ("BTTS", "btts", "btts", None),
    ("1X2", "1x2", "1x2", None),
    ("HT 1X2", "ht_1x2", "ht1x2", None),
]


def _get(p: str):
    return json.loads(urllib.request.urlopen(
        urllib.request.Request(URL + "/rest/v1/" + p, headers=H), timeout=90).read())


def pick(market_probs: dict, kind: str):
    """Ritorna (direzione, convinzione=prob_del_lato_scelto)."""
    if kind in ("ou", "htou"):
        p = float(market_probs.get("True", 0.0))
        return ("OVER", p) if p >= 0.5 else ("UNDER", 1.0 - p)
    if kind == "btts":
        p = float(market_probs.get("True", 0.0))
        return ("SI", p) if p >= 0.5 else ("NO", 1.0 - p)
    # 1x2 / ht1x2
    d = {k: float(market_probs[k]) for k in ("H", "D", "A") if k in market_probs}
    k = max(d, key=lambda x: d[x])
    return k, d[k]


def actual(kind: str, thr, gh: int, ga: int, hh: int, ha: int):
    tot, htot = gh + ga, hh + ha
    if kind == "ou":
        return "OVER" if tot >= thr else "UNDER"
    if kind == "htou":
        return "OVER" if htot >= thr else "UNDER"
    if kind == "btts":
        return "SI" if (gh >= 1 and ga >= 1) else "NO"
    if kind == "1x2":
        return "H" if gh > ga else ("A" if ga > gh else "D")
    if kind == "ht1x2":
        return "H" if hh > ha else ("A" if ha > hh else "D")


def bucket(conv: float) -> str:
    if conv >= 0.80:
        return "80%+ "
    if conv >= 0.70:
        return "70-80"
    if conv >= 0.60:
        return "60-70"
    if conv >= 0.50:
        return "50-60"
    return "<50  "


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    fids = [int(x) for x in sys.argv[1:]] or DEFAULT_FIDS
    csv = "in.(" + ",".join(map(str, fids)) + ")"
    fps = {f["fixture_id"]: f for f in _get(
        "fixture_predictions?select=fixture_id,db_json_analisi&fixture_id=" + csv)}
    ms = {m["fixture_id"]: m for m in _get(
        "matches?select=fixture_id,home_team_name,away_team_name,goals_home,goals_away,"
        "halftime_home,halftime_away,status_short&fixture_id=" + csv)}

    per_market: dict[str, list[bool]] = defaultdict(list)
    calib: dict[str, list[bool]] = defaultdict(list)   # bucket -> hit list
    conv_sum: dict[str, float] = defaultdict(float)    # bucket -> somma convinzioni
    misses: list[tuple] = []
    rows: list[tuple] = []

    for fid in fids:
        fp, m = fps.get(fid), ms.get(fid)
        if not fp or not m or m.get("status_short") not in ("FT", "AET", "PEN"):
            continue
        gh, ga = m["goals_home"], m["goals_away"]
        hh = m.get("halftime_home") or 0
        ha = m.get("halftime_away") or 0
        nm = f"{m['home_team_name']} - {m['away_team_name']}"
        markets = (fp.get("db_json_analisi") or {}).get("markets") or {}
        for label, pkey, kind, thr in MARKETS:
            pm = markets.get(pkey)
            if not isinstance(pm, dict):
                continue
            d, conv = pick(pm, kind)
            act = actual(kind, thr, gh, ga, hh, ha)
            hit = (d == act)
            per_market[label].append(hit)
            b = bucket(conv)
            calib[b].append(hit)
            conv_sum[b] += conv
            rows.append((fid, nm, label, d, conv, act, hit, gh, ga, hh, ha))
            if not hit and conv >= 0.70:
                misses.append((label, d, conv, nm, gh, ga, hh, ha))

    def pct(lst):
        return f"{sum(lst)/len(lst):5.1%}" if lst else "  -  "

    print("=" * 74)
    print(f"VALIDAZIONE MOTORE POISSON — {len(rows)} previsioni su "
          f"{len({r[0] for r in rows})} partite FT")
    print("=" * 74)

    print("\n── 1) ACCURATEZZA DIREZIONALE per MERCATO ──")
    print(f"{'MERCATO':14s} {'hit-rate':>8s} {'n':>4s}  {'conv.media':>10s}")
    for label, *_ in MARKETS:
        lst = per_market.get(label, [])
        if lst:
            cv = sum(r[4] for r in rows if r[2] == label) / len(lst)
            print(f"{label:14s} {pct(lst):>8s} {len(lst):>4d}  {cv:>10.1%}")
    allhit = [h for lst in per_market.values() for h in lst]
    print(f"{'— TOTALE —':14s} {pct(allhit):>8s} {len(allhit):>4d}")

    print("\n── 2) CALIBRAZIONE (la convinzione predice il successo?) ──")
    print(f"{'fascia conv':12s} {'reale':>7s} {'attesa':>7s} {'n':>4s}  {'scarto':>7s}")
    for b in ["80%+ ", "70-80", "60-70", "50-60", "<50  "]:
        lst = calib.get(b, [])
        if lst:
            real = sum(lst) / len(lst)
            exp = conv_sum[b] / len(lst)
            print(f"{b:12s} {real:>7.1%} {exp:>7.1%} {len(lst):>4d}  {real-exp:>+7.1%}")

    print("\n── 3) MISS ad ALTA CONVINZIONE (Poisson >=70% ma sbagliato) ──")
    if not misses:
        print("  (nessuna)")
    for label, d, conv, nm, gh, ga, hh, ha in sorted(misses, key=lambda x: -x[2]):
        print(f"  ✗ {label:12s} {d:5s} {conv:4.0%}  {nm:34s} FT {gh}-{ga} (HT {hh}-{ha})")


if __name__ == "__main__":
    main()
