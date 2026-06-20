"""
valida_ventaglio.py — VALIDAZIONE dei segnali del ventaglio 5-motori contro i
risultati reali (FT + HT). Riusa build_signals() da ventaglio_segnali.py così la
card-logic e' identica 1:1 a quella operativa.

Calcola hit/miss per ogni segnale e aggrega accuratezza:
  - per TIER (A_MAX / B_ALTA / C_MEDIA / D_DEBOLE / SCARTA / EVITA)
  - per MERCATO (O/U 1.5, O/U 2.5, ...)
  - direzionale "AGISCI" = tier >= C_MEDIA (segnali che avremmo davvero seguito)

Uso:  python valida_ventaglio.py            (le 18 Betfair del 2026-06-19)
      python valida_ventaglio.py 1492915 ...
"""
from __future__ import annotations

import sys
from collections import defaultdict

import ventaglio_segnali as V


def resolve(market: str, direction: str, gh: int, ga: int, hh: int, ha: int) -> bool | None:
    """True=hit, False=miss, None=non risolvibile/void."""
    tot = gh + ga
    htot = hh + ha
    if market == "O/U 1.5":
        return (tot >= 2) == (direction == "OVER")
    if market == "O/U 2.5":
        return (tot >= 3) == (direction == "OVER")
    if market == "O/U 3.5":
        return (tot >= 4) == (direction == "OVER")
    if market == "HT Over 0.5":
        return (htot >= 1) == (direction == "OVER")
    if market == "BTTS":
        both = gh >= 1 and ga >= 1
        return both == (direction == "SI")
    if market == "1X2":
        res = "H" if gh > ga else ("A" if ga > gh else "D")
        return res == direction
    if market == "HT 1X2":
        res = "H" if hh > ha else ("A" if ha > hh else "D")
        return res == direction
    return None


TIER_ORDER = ["A_MAX", "B_ALTA", "C_MEDIA", "D_DEBOLE", "SCARTA", "EVITA (regime girato)"]
AGISCI_TIERS = {"A_MAX", "B_ALTA", "C_MEDIA"}


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    fids = [int(x) for x in sys.argv[1:]] or V.DEFAULT_FIDS
    fid_csv = "in.(" + ",".join(map(str, fids)) + ")"
    fps = V._get(
        "fixture_predictions?select=fixture_id,db_json_analisi,model_predictions_json,flat_summary"
        f"&fixture_id={fid_csv}"
    )
    names = V._get(
        "matches?select=fixture_id,home_team_name,away_team_name,league_id,"
        "goals_home,goals_away,halftime_home,halftime_away,status_short"
        f"&fixture_id={fid_csv}"
    )
    name_by = {m["fixture_id"]: m for m in names}
    fp_by = {f["fixture_id"]: f for f in fps}

    delays_cache: dict = {}
    rows: list[tuple] = []  # (fid, name, signal, hit)

    for fid in fids:
        fp = fp_by.get(fid)
        m = name_by.get(fid, {})
        if not fp or m.get("status_short") not in ("FT", "AET", "PEN"):
            continue
        gh, ga = m.get("goals_home"), m.get("goals_away")
        hh, ha = m.get("halftime_home"), m.get("halftime_away")
        if None in (gh, ga):
            continue
        hh = hh if hh is not None else 0
        ha = ha if ha is not None else 0
        league_id = (fp.get("db_json_analisi") or {}).get("league_id") or m.get("league_id")
        nm = f"{m.get('home_team_name','?')} - {m.get('away_team_name','?')}"
        for s in V.build_signals(fp, delays_cache, league_id):
            hit = resolve(s.market, s.direction, gh, ga, hh, ha)
            rows.append((fid, nm, s, hit, gh, ga, hh, ha))

    # ---------- DETTAGLIO per partita ----------
    OUT = {True: "✓", False: "✗", None: "·"}
    print("=" * 84)
    print("DETTAGLIO SEGNALI PER PARTITA (esito vs risultato reale)")
    print("=" * 84)
    cur_fid = None
    for fid, nm, s, hit, gh, ga, hh, ha in rows:
        if fid != cur_fid:
            cur_fid = fid
            print(f"\n┌─ {fid}  {nm}   FT {gh}-{ga}  (HT {hh}-{ha})")
            print(f"│ {'esito':5s} {'mercato':12s} {'dir':5s} {'tier':8s} {'fid':>5s}  "
                  f"{'conc':>5s}  motori")
        eng = []
        for v in s.votes:
            if v.engine in ("Poisson", "ML", "API"):
                if v.direction == "-":
                    eng.append(f"{v.engine}✗")
                else:
                    mk = "v" if v.direction == s.direction else "x"
                    eng.append(f"{v.engine}{mk}{v.direction}({v.conviction:.0%})")
            elif v.engine == "Freq":
                eng.append(f"Freq{v.conviction:.0%}")
            elif v.engine == "Ritardi":
                eng.append(f"Rit:{v.note.split('->')[-1].strip()}")
        print(f"│  {OUT[hit]:4s} {s.market:12s} {s.direction:5s} {s.tier[:8]:8s} "
              f"{s.score:5.2f}  {s.concord}/{s.n_engines:<3d}  {'  '.join(eng)}")
    print("└" + "─" * 82)

    # ---------- aggregati ----------
    by_tier: dict[str, list[bool]] = defaultdict(list)
    by_market: dict[str, list[bool]] = defaultdict(list)
    agisci_by_market: dict[str, list[bool]] = defaultdict(list)

    for fid, nm, s, hit, *_ in rows:
        if hit is None:
            continue
        by_tier[s.tier].append(hit)
        by_market[s.market].append(hit)
        if s.tier in AGISCI_TIERS:
            agisci_by_market[s.market].append(hit)

    def pct(lst: list[bool]) -> str:
        if not lst:
            return "  -  "
        return f"{sum(lst)/len(lst):5.1%}"

    print("=" * 72)
    print(f"VALIDAZIONE VENTAGLIO 5-MOTORI — {len([r for r in rows])} segnali su "
          f"{len({r[0] for r in rows})} partite FT")
    print("=" * 72)

    print("\n── ACCURATEZZA per TIER (tutti i segnali) ──")
    print(f"{'TIER':22s} {'hit-rate':>9s}  {'n':>4s}   (hit/tot)")
    for t in TIER_ORDER:
        lst = by_tier.get(t, [])
        if lst:
            print(f"{t:22s} {pct(lst):>9s}  {len(lst):>4d}   ({sum(lst)}/{len(lst)})")

    print("\n── ACCURATEZZA AGISCI (tier A_MAX+B_ALTA+C_MEDIA) per MERCATO ──")
    print(f"{'MERCATO':14s} {'reale':>7s}  {'atteso':>7s}  {'n':>4s}   (hit/tot)")
    for mkt, _b, _t, _k, *_ in V.MARKETS:
        lst = agisci_by_market.get(mkt, [])
        exp = V.MARKET_BASE.get(mkt, 0.55)
        if lst:
            print(f"{mkt:14s} {pct(lst):>7s}  {exp:>7.0%}  {len(lst):>4d}   ({sum(lst)}/{len(lst)})")

    # agisci totale
    all_agisci = [h for lst in agisci_by_market.values() for h in lst]
    print(f"{'— TOTALE —':14s} {pct(all_agisci):>7s}  {'':>7s}  {len(all_agisci):>4d}   "
          f"({sum(all_agisci)}/{len(all_agisci)})")

    print("\n── ACCURATEZZA per MERCATO (TUTTI i tier, anche SCARTA) ──")
    for mkt, _b, _t, _k, *_ in V.MARKETS:
        lst = by_market.get(mkt, [])
        if lst:
            print(f"{mkt:14s} {pct(lst):>7s}  {len(lst):>4d}   ({sum(lst)}/{len(lst)})")

    # ---------- dettaglio MISS sui tier alti (i casi che fanno male) ----------
    print("\n── MISS nei tier A_MAX / B_ALTA (segnali forti sbagliati) ──")
    miss = [(fid, nm, s, gh, ga, hh, ha) for fid, nm, s, hit, gh, ga, hh, ha in rows
            if hit is False and s.tier in ("A_MAX", "B_ALTA")]
    if not miss:
        print("  (nessuno)")
    for fid, nm, s, gh, ga, hh, ha in miss:
        print(f"  ✗ {s.tier:7s} {s.market:12s} {s.direction:5s}  {nm:34s} "
              f"FT {gh}-{ga} (HT {hh}-{ha})")


if __name__ == "__main__":
    main()
