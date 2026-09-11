"""Osservatore di Omega a runtime (solo lettura): ogni N secondi stampa le NUOVE
righe di omega_activity che contano (ingressi, uscite, regolazioni, errori, allarmi)
e segnala se l'heartbeat del servizio o dello scanner si ferma.

    python tools/omega_watch.py --every 60 --minutes 45
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, ".")
from Betfair.omega import omega_db as db  # noqa: E402

KINDS = {"placed", "settle", "settle_hedged", "settle_orphan_closing", "greenup", "greenup_hold",
         "greenup_wait", "greenup_blind", "error", "loss_stop", "goal_stop", "reconcile_error",
         "settle_error", "size_reduced", "confirm_failed", "manual_place_exception", "flumine_enqueue",
         "paper_fill_fallback", "live_fok_fallback", "stop", "start"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--every", type=int, default=60)
    ap.add_argument("--minutes", type=int, default=45)
    args = ap.parse_args()
    sb = db._sb()
    last_ts = datetime.now(timezone.utc).isoformat()
    t_end = time.time() + args.minutes * 60
    skips = {}
    while time.time() < t_end:
        try:
            now = datetime.now(timezone.utc)
            c = sb.table("omega_control").select("status,heartbeat_at,stats").eq("id", 1).execute().data[0]
            hb = datetime.fromisoformat(str(c["heartbeat_at"]).replace("Z", "+00:00"))
            age = (now - hb).total_seconds()
            if age > 120:
                print(f"ALLARME heartbeat Omega fermo da {int(age)} s", flush=True)
            st = sb.table("safe_strategy_status").select("updated_at,payload").eq("id", "scanner").execute().data
            if st:
                sa = (now - datetime.fromisoformat(str(st[0]["updated_at"]).replace("Z", "+00:00"))).total_seconds()
                if sa > 90:
                    print(f"ALLARME scanner fermo da {int(sa)} s", flush=True)
            rows = (sb.table("omega_activity").select("kind,payload,ts").gt("ts", last_ts)
                    .order("ts", desc=False).limit(200).execute().data or [])
            for r in rows:
                last_ts = max(last_ts, r["ts"])
                k = r["kind"]
                p = r.get("payload") or {}
                if k in KINDS:
                    print(f"{r['ts'][11:19]} {k} {json.dumps(p, ensure_ascii=False)[:160]}", flush=True)
                elif k == "skip":
                    skips[p.get("reason")] = skips.get(p.get("reason"), 0) + 1
            stats = c.get("stats") or {}
            print(f"{now.isoformat(timespec='seconds')[11:]} hb {int(age)}s | eventi {stats.get('events_total')} "
                  f"| gambe oggi {stats.get('legs_today', '?')} | P&L oggi {stats.get('realized_today')} "
                  f"| skip {dict(skips)}", flush=True)
            skips = {}
        except Exception as ex:  # noqa: BLE001
            print(f"watch KO: {str(ex)[:120]}", flush=True)
        time.sleep(args.every)


if __name__ == "__main__":
    main()
