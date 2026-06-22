"""enrich_analytics_snapshots.py — riempie freq_*/delay_* in analytics_signals con
lo SNAPSHOT POINT-IN-TIME (valore del mercato AL MOMENTO di quella partita) usando
gli RPC certificati get_market_frequency / get_market_delays.

⚠️ Lo snapshot è per (fixture × mercato): Over e Under condividono lo stato del
mercato. Point-in-time = il valore della media mobile / ritardo CALCOLATO fino a
quella giornata (le RPC restituiscono la serie con un punto per fixture).

Pesante (1 coppia di RPC per lega×mercato) → eseguire on-demand / settimanale, NON
nel path notturno critico. v1: mercati Over FT (over_0_5..4_5), che mappano pulito
su ou_ft (freq) e 'over' (delay). Altri mercati: estensione successiva.

Uso:
  python enrich_analytics_snapshots.py --league 256
  python enrich_analytics_snapshots.py --league 256 --dry-run
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_client import get_supabase_client

# mercato canonico Over FT → linea (per le RPC ou_ft / 'over')
_OVER_FT = re.compile(r"^over_(\d)_5$")


def _line(market: str) -> Optional[float]:
    m = _OVER_FT.match(market)
    return float(m.group(1)) + 0.5 if m else None


def _snapshots_for(sb, league_id: int, market: str) -> dict[int, dict]:
    """Ritorna {fixture_id: {freq_baseline, freq_current, freq_deviation,
    delay_current, delay_record, delay_avg}} per il mercato Over dato."""
    line = _line(market)
    if line is None:
        return {}
    out: dict[int, dict] = {}
    # FREQUENZE: meta.baseline + points[].mm10 (media mobile = "frequenza attuale")
    f = sb.rpc("get_market_frequency", {"p_league_id": league_id, "p_market": "ou_ft",
               "p_selection": "over", "p_line": line, "p_mode": "all",
               "p_last_n": None, "p_season_year": None}).execute().data
    baseline = (f.get("meta") or {}).get("baseline")
    for p in f.get("points") or []:
        fid = p.get("fid")
        mm = p.get("mm10")
        if fid is None:
            continue
        out.setdefault(fid, {})
        out[fid]["freq_baseline"] = round(baseline, 4) if baseline is not None else None
        out[fid]["freq_current"] = round(mm, 4) if mm is not None else None
        out[fid]["freq_deviation"] = (round(mm - baseline, 4)
                                      if (mm is not None and baseline is not None) else None)
    # RITARDI: stats.record/media_ritardi + series[].rit (ritardo a quella giornata)
    d = sb.rpc("get_market_delays", {"p_league_id": league_id, "p_market": "over",
               "p_target": str(line), "p_mode": "all", "p_last_n": None,
               "p_season_year": None}).execute().data
    st = d.get("stats") or {}
    rec = st.get("record")
    avg = st.get("media_ritardi")
    for s in d.get("series") or []:
        fid = s.get("fid")
        if fid is None:
            continue
        out.setdefault(fid, {})
        out[fid]["delay_current"] = s.get("rit")
        out[fid]["delay_record"] = rec
        out[fid]["delay_avg"] = round(avg, 4) if avg is not None else None
    return out


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", type=int, required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    sb = get_supabase_client()

    # mercati Over FT + fixture_id REALMENTE presenti per questa lega in
    # analytics_signals (così non si fanno UPDATE a vuoto sulle migliaia di
    # fixture storiche che la RPC restituisce ma che non sono in tabella).
    rows = (sb.table("analytics_signals").select("fixture_id,market")
            .eq("league_id", args.league).like("market", "over_%").execute().data)
    markets = sorted({r["market"] for r in rows if _OVER_FT.match(r["market"])})
    present_fids = {r["fixture_id"] for r in rows}
    print(f"Lega {args.league}: mercati Over = {markets} | fixture in tabella = {len(present_fids)}")

    updated = 0
    for market in markets:
        snaps = {fid: s for fid, s in _snapshots_for(sb, args.league, market).items() if fid in present_fids}
        print(f"  {market}: snapshot per {len(snaps)} fixture (in tabella)")
        if args.dry_run:
            ex = next(iter(snaps.items()), None)
            if ex:
                print(f"    esempio fix {ex[0]}: {ex[1]}")
            continue
        for fid, snap in snaps.items():
            for attempt in range(3):
                try:
                    sb.table("analytics_signals").update(snap).eq("fixture_id", fid).eq("market", market).execute()
                    updated += 1
                    break
                except Exception as e:  # noqa: BLE001
                    if attempt == 2:
                        print(f"    [ERR] fix {fid} {market}: {str(e)[:80]}")
                    else:
                        time.sleep(0.4 * (attempt + 1))
    print(f"\n{'[DRY-RUN] ' if args.dry_run else ''}Aggiornati {updated} (fixture×mercato)")


if __name__ == "__main__":
    main()
