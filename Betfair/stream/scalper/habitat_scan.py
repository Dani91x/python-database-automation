"""HABITAT SCAN — trova le partite ADATTE allo scalper (oggi, dal catalogo).

Applica automaticamente la regola certificata sui replay (dossier §9.9):
l'habitat del maker e' la partita LIQUIDA DI FASCIA MEDIA che OSCILLA —
non l'elite congelata (code professionali), non le morte.

Per ogni MATCH_ODDS calcio con KO nelle prossime ore:
  * totale scambiato (fascia media: 20k-500k)
  * profondita' ai best (200-1500 ~ ok; >2500 = elite)
  * spread in tick (1-2)
  * OSCILLAZIONE osservata: campiona il book 3 volte in ~40s e conta i
    movimenti del mid (il "cibo" del maker)
Output: classifica con punteggio 0-100 e verdetto GO / CON BIAS / NO.

Uso:  python -m Betfair.stream.scalper.habitat_scan [--hours 6] [--top 15]
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TICK_BANDS = [(1.01, 2.0, 0.01), (2.0, 3.0, 0.02), (3.0, 4.0, 0.05),
              (4.0, 6.0, 0.1), (6.0, 10.0, 0.2)]


def _spread_ticks(bb: float, bl: float) -> Optional[float]:
    if not bb or not bl or bl < bb:
        return None
    n, p, guard = 0.0, bb, 0
    while p < bl - 1e-9 and guard < 500:
        t = next((t for lo, hi, t in TICK_BANDS if lo <= p < hi), 0.2)
        step = min(t, bl - p)
        n += step / t
        p += step
        guard += 1
    return n


def _book_snapshot(trading: Any, market_ids: List[str]) -> Dict[str, Any]:
    from betfairlightweight import filters

    def _ps(x: Any) -> tuple:
        # tollera sia PriceSize object sia dict {'price','size'}
        if isinstance(x, dict):
            return float(x.get("price") or 0), float(x.get("size") or 0)
        return float(getattr(x, "price", 0) or 0), float(getattr(x, "size", 0) or 0)

    out: Dict[str, Any] = {}
    for i in range(0, len(market_ids), 25):
        books = trading.betting.list_market_book(
            market_ids=market_ids[i:i + 25],
            price_projection=filters.price_projection(price_data=["EX_BEST_OFFERS"]),
        )
        for b in books:
            runners = {}
            for r in b.runners or []:
                atb = r.ex.available_to_back or []
                atl = r.ex.available_to_lay or []
                if atb and atl:
                    bp, bs = _ps(atb[0])
                    lp, ls = _ps(atl[0])
                    if bp and lp:
                        runners[int(r.selection_id)] = (bp, bs, lp, ls)
            out[b.market_id] = {
                "tv": float(getattr(b, "total_matched", 0.0) or 0.0),
                "runners": runners,
                "status": b.status,
            }
    return out


def scan(hours: float = 6.0, top: int = 15, samples: int = 3,
         sample_gap_s: float = 20.0) -> List[Dict[str, Any]]:
    from betfairlightweight import filters

    sys.path.insert(0, __file__.rsplit("Betfair", 1)[0])
    from Betfair.stream.auth import build_client

    trading = build_client(login=True)
    cat = trading.betting.list_market_catalogue(
        filter=filters.market_filter(
            event_type_ids=["1"], market_type_codes=["MATCH_ODDS"],
            market_start_time={
                "from": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "to": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                    time.gmtime(time.time() + hours * 3600)),
            },
            in_play_only=False,
        ),
        market_projection=["EVENT", "MARKET_START_TIME"],
        sort="MAXIMUM_TRADED", max_results=60,
    )
    if not cat:
        return []
    mids = [m.market_id for m in cat]
    names = {m.market_id: (getattr(m.event, "name", "?"),
                           getattr(m, "market_start_time", None)) for m in cat}

    # campiona il book N volte per misurare l'OSCILLAZIONE del mid
    snaps = []
    for k in range(samples):
        snaps.append(_book_snapshot(trading, mids))
        if k < samples - 1:
            time.sleep(sample_gap_s)

    rows = []
    for mid in mids:
        last = snaps[-1].get(mid) or {}
        if last.get("status") != "OPEN" or not last.get("runners"):
            continue
        tv = last["tv"]
        # profondita' e spread medi sui runner in banda quota operabile
        depths, spreads = [], []
        for sid, (bb, sb, bl, sl) in last["runners"].items():
            if not (1.5 <= bb <= 4.6):
                continue
            st = _spread_ticks(bb, bl)
            if st is not None:
                spreads.append(st)
                depths.append((sb + sl) / 2.0)
        if not spreads:
            continue
        avg_depth = sum(depths) / len(depths)
        avg_spread = sum(spreads) / len(spreads)
        # oscillazione: quanti runner hanno mosso il mid tra i campioni
        moves = 0
        checks = 0
        for s0, s1 in zip(snaps, snaps[1:]):
            r0 = (s0.get(mid) or {}).get("runners") or {}
            r1 = (s1.get(mid) or {}).get("runners") or {}
            for sid in r0.keys() & r1.keys():
                m0 = (r0[sid][0] + r0[sid][2]) / 2.0
                m1 = (r1[sid][0] + r1[sid][2]) / 2.0
                checks += 1
                if abs(m1 - m0) > 1e-9:
                    moves += 1
        osc = moves / checks if checks else 0.0

        # punteggio 0-100 secondo la regola certificata
        score = 0.0
        if 20_000 <= tv <= 500_000:
            score += 35
        elif 8_000 <= tv < 20_000 or 500_000 < tv <= 1_200_000:
            score += 15
        if 200 <= avg_depth <= 1500:
            score += 25
        elif 100 <= avg_depth < 200 or 1500 < avg_depth <= 2500:
            score += 12
        if avg_spread <= 2.2:
            score += 15
        score += min(25.0, osc * 60)   # l'oscillazione e' il cibo
        elite = avg_depth > 2500 or tv > 1_200_000
        dead = tv < 8_000 or avg_depth < 100
        verdict = ("NO (morta)" if dead else
                   "CON BIAS o NO (elite)" if elite else
                   "GO ✅" if score >= 60 else
                   "forse" if score >= 40 else "NO")
        ev_name, ko = names.get(mid, ("?", None))
        rows.append(dict(market_id=mid, event=ev_name, ko=str(ko)[:16],
                         tv=int(tv), depth=int(avg_depth),
                         spread=round(avg_spread, 1), osc=round(osc, 2),
                         score=int(score), verdict=verdict))
    rows.sort(key=lambda r: -r["score"])
    return rows[:top]


def main() -> None:
    ap = argparse.ArgumentParser(description="Habitat scan per lo scalper")
    ap.add_argument("--hours", type=float, default=6.0)
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)
    rows = scan(hours=args.hours, top=args.top)
    if not rows:
        print("Nessun mercato calcio nelle prossime ore.")
        return
    print(f"{'PARTITA':34s} {'KO':16s} {'scambiato':>10s} {'best€':>6s} "
          f"{'spr':>4s} {'osc':>4s} {'punti':>5s}  VERDETTO")
    for r in rows:
        print(f"{r['event'][:34]:34s} {r['ko']:16s} {r['tv']:>10,d} "
              f"{r['depth']:>6d} {r['spread']:>4.1f} {r['osc']:>4.2f} "
              f"{r['score']:>5d}  {r['verdict']}")


if __name__ == "__main__":
    main()
