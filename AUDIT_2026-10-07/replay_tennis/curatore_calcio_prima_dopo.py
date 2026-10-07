"""Curatore del CALCIO prima/dopo la correzione del 07/10, sulle registrazioni vere.

Ricostruisce i record del file curato `<event>.jsonl` dal raw `_live_raw/<id>/<id>.raw.jsonl`
(stessa catena del recorder: betfairlightweight -> `serialize_book`), poi cura con la
regola VECCHIA (ricopiata qui sotto, identica al curatore prima della correzione) e con
quella NUOVA (`curator.curate_records`), e confronta per mercato:
  * righe vecchie che mancano nelle nuove (devono essere 0);
  * righe nuove in piu': devono essere SOLO cambi di stato (status o inplay) coi best invariati.

Uso:  python3 AUDIT_2026-10-07/replay_tennis/curatore_calcio_prima_dopo.py [<cartella _live_raw>]
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple

RADICE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RADICE))


def cura_vecchia(records, event_id, cadence_sec=10.0) -> List[Dict[str, Any]]:
    """La regola del curatore PRIMA del 07/10 (solo best back/lay/ltp, cadenza)."""
    from Betfair.stream.curator import _best_signature, _ms_to_iso, ladder_db_format

    cadence_ms = cadence_sec * 1000.0
    last_kept_ms: Dict[str, float] = {}
    last_sig: Dict[str, Tuple] = {}
    rows = []
    for rec in records:
        mid = rec.get("market_id")
        if not mid:
            continue
        pt = rec.get("pt")
        runners = rec.get("runners") or {}
        sig = _best_signature(runners)
        changed = (mid not in last_sig) or (last_sig[mid] != sig)
        prev = last_kept_ms.get(mid)
        thr = pt is not None and prev is not None and (pt - prev) >= cadence_ms
        if not changed and not thr:
            continue
        rows.append({"event_id": event_id, "market_id": mid, "ts": _ms_to_iso(pt), "minute": None,
                     "inplay": bool(rec.get("inplay", False)), "status": rec.get("status") or "OPEN",
                     "ladder": ladder_db_format(runners)})
        last_sig[mid] = sig
        if pt is not None:
            last_kept_ms[mid] = pt
    rows.sort(key=lambda r: (r["ts"] or "", r["market_id"]))
    return rows


def chiave(r: Dict[str, Any]) -> str:
    return json.dumps([r["market_id"], r["ts"], r["status"], r["inplay"], r["ladder"]], sort_keys=True)


def main() -> int:
    from Betfair.stream.curator import curate_records
    from Betfair.stream.tennis_replay.convertitore import decodifica_raw

    base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/home/user/python-database-automation/_live_raw")
    tutto_ok = True
    for ev in ("35797769", "35760084"):
        raw = base / ev / f"{ev}.raw.jsonl"
        if not raw.exists():
            print(f"{ev}: raw assente ({raw})")
            tutto_ok = False
            continue
        records = decodifica_raw(raw).record
        vecchie = cura_vecchia(records, ev)
        nuove = curate_records(records, ev)
        kv = Counter(chiave(r) for r in vecchie)
        kn = Counter(chiave(r) for r in nuove)
        sparite = kv - kn
        in_piu = kn - kv
        per_mercato = Counter(r["market_id"] for r in vecchie)
        per_mercato_n = Counter(r["market_id"] for r in nuove)
        # ogni riga in piu' e' un cambio di stato rispetto alla riga precedente dello stesso mercato
        prec: Dict[str, Dict[str, Any]] = {}
        non_stato = 0
        cambi = Counter()
        for r in nuove:
            k = chiave(r)
            p = prec.get(r["market_id"])
            if in_piu.get(k):
                if p is None or (p["status"], p["inplay"]) == (r["status"], r["inplay"]):
                    non_stato += 1
                else:
                    cambi[f'{p["status"]}/{"in" if p["inplay"] else "pre"} -> {r["status"]}/{"in" if r["inplay"] else "pre"}'] += 1
            prec[r["market_id"]] = r
        diversi = {m: (per_mercato[m], per_mercato_n[m]) for m in sorted(set(per_mercato) | set(per_mercato_n))
                   if per_mercato[m] != per_mercato_n[m]}
        ok = sum(sparite.values()) == 0 and non_stato == 0
        tutto_ok &= ok
        print(f"{ev}: libri {len(records)}, righe prima {len(vecchie)}, dopo {len(nuove)}, "
              f"sparite {sum(sparite.values())}, in piu' {sum(in_piu.values())} (non di stato {non_stato}) "
              f"-> {'OK' if ok else 'KO'}")
        print(f"   mercati {len(per_mercato_n)}; mercati con righe in piu': {len(diversi)}")
        for m, (a, b) in diversi.items():
            print(f"     {m}: {a} -> {b}")
        for c, n in cambi.most_common():
            print(f"   cambio {c}: {n}")
    return 0 if tutto_ok else 1


if __name__ == "__main__":
    sys.exit(main())
