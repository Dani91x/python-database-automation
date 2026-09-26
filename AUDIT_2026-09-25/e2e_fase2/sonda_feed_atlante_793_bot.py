"""sonda_feed_atlante_793_bot.py - 7.3.5 / 7.3.6 / 7.9.3.B (e2e fase 2, 26/09), SOLA LETTURA.
Ogni PASSO secondi raccoglie cio' che i BOT hanno scritto dall'atlante v4:
  * Mike: frame live di mike_events in gioco (hazard_atlas, hazard_versione, hazard_fase,
    hazard_recupero_atteso_min, hazard_nota, minute, gol, dossier league/team id, published_at);
  * Safe: richieste in safe_strategy_requests il cui payload cita l'atlante (nota hazard);
  * versione dell'atlante che i bot leggono (Betfair/omega/data/hazard_atlas_live.json): a ogni
    cambio ne salva una COPIA nella cartella indicata (scratchpad, fuori dal repo) per ricalcolare
    poi con la versione giusta.
Uscita: sonda_793_bot.jsonl. Uso: python sonda_feed_atlante_793_bot.py <minuti> <passo_s> <dir_copie>
"""
import datetime as dt
import json
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sonda_feed_atlante_db import get  # noqa: E402

QUI = Path(__file__).resolve().parent
LIVE = QUI.parents[1] / "Betfair" / "omega" / "data" / "hazard_atlas_live.json"
minuti, passo, copie = float(sys.argv[1]), float(sys.argv[2]), Path(sys.argv[3])
copie.mkdir(parents=True, exist_ok=True)
fine = time.time() + minuti * 60
ult_mtime = None
ult_req = 0
visti = set()
SEL_M = ("event_id,updated_at,competition,lid:dossier->league_id,hid:dossier->home_team_id,"
         "aid:dossier->away_team_id,minute:live->minute,sh:live->score_home,sa:live->score_away,"
         "inplay:live->inplay,ha:live->hazard_atlas,hv:live->>hazard_versione,hf:live->>hazard_fase,"
         "hr:live->hazard_recupero_atteso_min,hn:live->>hazard_nota,hs:live->>hazard_source,"
         "hl:live->>hazard_livello,hnn:live->hazard_n,pub:live->>published_at")
while True:
    ora = dt.datetime.now(dt.timezone.utc)
    rec = {"t": ora.isoformat(timespec="seconds")}
    try:
        m = os.path.getmtime(LIVE)
        if m != ult_mtime:
            a = json.loads(LIVE.read_text(encoding="utf-8"))
            # il nome porta il MTIME: il motore scrive lo stesso generated_at due volte (la
            # dichiarazione "in preparazione" a inizio ciclo e il file finale, atlante_a_domanda.py
            # ciclo() -> _scrivi_live), con contenuti diversi
            dest = copie / f"hazard_atlas_live_m{m:.3f}.json"
            if not dest.exists():
                shutil.copyfile(LIVE, dest)
            rec["atlante_nuovo"] = {"generated_at": a["meta"]["generated_at"], "copia": str(dest),
                                    "mtime_utc": dt.datetime.fromtimestamp(m, dt.timezone.utc).isoformat()}
            ult_mtime = m
    except Exception as e:  # noqa: BLE001 - file in scrittura: al prossimo giro
        rec["atlante_err"] = repr(e)[:160]
    da = (ora - dt.timedelta(minutes=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    st, r, _ = get(f"mike_events?select={SEL_M}&updated_at=gte.{da}&limit=200")
    rec["mike"] = [x for x in r if x.get("minute") is not None] if st == 200 else r
    st, r, _ = get(f"safe_strategy_requests?select=id,created_at,payload&id=gt.{ult_req}&order=id.asc&limit=500")
    if st == 200:
        for x in r:
            ult_req = max(ult_req, int(x["id"]))
        rec["safe_note"] = [x for x in r if "atlante" in json.dumps(x["payload"]).lower()]
    with open(QUI / "sonda_793_bot.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    if time.time() + passo > fine:
        break
    time.sleep(passo)
