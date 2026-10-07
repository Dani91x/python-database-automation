"""Genera la fixture del frontend del Replay Tennis dalla registrazione VERA 35790089.

La fixture e' l'uscita del convertitore (la stessa che le RPC restituirebbero
dal DB): evento, catalogo, punteggio completo (104 righe, senza il payload IPS
grezzo) e un estratto dei frame (i primi 40 e gli ultimi 8: apertura, ultimo
tie-break, sospensione e chiusura), nella forma dei frame delle RPC
(`minute: null`). Rigenerabile:

    python3 AUDIT_2026-10-07/replay_tennis/genera_fixture_frontend.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RADICE))


def main() -> int:
    from Betfair.stream.tennis_replay.convertitore import converti_evento
    from Betfair.stream.tennis_replay.tests.dati_tennis import EVENTO_VERO, cartella_vera

    cart = cartella_vera()
    if cart is None:
        print("registrazione vera assente")
        return 1
    rt = converti_evento([cart / f"{EVENTO_VERO}.raw.jsonl"], [cart / f"{EVENTO_VERO}.score.jsonl"])
    frames = [{"market_id": s["market_id"], "ts": s["ts"], "minute": None, "inplay": s["inplay"],
               "status": s["status"], "ladder": s["ladder"]} for s in rt.snapshot]
    estratto = frames[:40] + frames[-8:]
    out = {
        "_origine": "Betfair/stream/tennis_replay/convertitore.py su _live_raw_tennis/20260707/35790089 (registrazione vera)",
        "event": dict(rt.evento, valuta="GBP"),
        "markets": [{k: m[k] for k in ("market_id", "market_type", "market_name", "sort_priority", "selections",
                                       "bet_delay", "settled_ts")} for m in rt.mercati],
        "score_timeline": [{k: p[k] for k in ("ts", "source", "score", "event_types", "point")} for p in rt.punteggio],
        "frames": estratto,
    }
    dest = RADICE / "frontend" / "src" / "lib" / "__fixtures__" / "replay_tennis_35790089.json"
    dest.write_text(json.dumps(out, ensure_ascii=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(dest, dest.stat().st_size, "byte")
    return 0


if __name__ == "__main__":
    sys.exit(main())
