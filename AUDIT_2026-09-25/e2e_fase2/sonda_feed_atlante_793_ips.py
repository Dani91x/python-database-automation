"""sonda_feed_atlante_793_ips.py - 7.9.3.B / 7.3.6 (e2e fase 2, 26/09), SOLA LETTURA.
Campiona ogni PASSO secondi le righe CALCIO del feed unico (safe_strategy_scan) con i campi che
servono al tempo 1T/2T dell'atlante v4 (minute, score, score_raw.matchStatus/timeElapsed/
elapsedRegularTime/elapsedAddedTime, competition, open_date, home/away, id squadra/lega se il
servizio li mette nel payload). Serve a ricalcolare `fase` e `tempo` su istanti REALI (1T, intervallo,
2T, recupero 2T) e a confrontarli col frame di Mike / la nota di Safe se i bot sono accesi.
Uscita: sonda_793_ips.jsonl (una riga per riga-evento letta, deduplicata per (event_id, updated_at)).
Uso: python sonda_feed_atlante_793_ips.py <minuti> [passo_s]
"""
import datetime as dt
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sonda_feed_atlante_db import get  # noqa: E402

QUI = Path(__file__).resolve().parent
SEL = ("event_id,updated_at,comp:payload->>competition,home:payload->>home,away:payload->>away,"
       "open_date:payload->>open_date,inplay:payload->inplay,minute:payload->minute,"
       "sh:payload->score_home,sa:payload->score_away,score_raw:payload->score_raw,"
       "home_team_id:payload->home_team_id,away_team_id:payload->away_team_id,league_id:payload->league_id")
minuti = float(sys.argv[1]) if len(sys.argv) > 1 else 1
passo = float(sys.argv[2]) if len(sys.argv) > 2 else 15
fine = time.time() + minuti * 60
visti = set()
while True:
    st, righe, ms = get(f"safe_strategy_scan?select={SEL}&sport=eq.calcio&limit=2000")
    letto = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    if st == 200:
        with open(QUI / "sonda_793_ips.jsonl", "a", encoding="utf-8") as fh:
            for r in righe:
                k = (r["event_id"], r["updated_at"])
                if k in visti:
                    continue
                visti.add(k)
                raw = r.pop("score_raw", None) or {}
                r["ips"] = {x: raw.get(x) for x in ("matchStatus", "timeElapsed", "elapsedRegularTime",
                                                     "elapsedAddedTime", "status")}
                r["score_raw"] = raw
                r["letto"] = letto
                fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    if time.time() + passo > fine:
        break
    time.sleep(passo)
