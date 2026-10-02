"""Sonda di SOLA LETTURA (nessuna scrittura su DB, nessun ordine vero): fa girare
lo scenario d'ordine di Safe ('ordini-manuali') sul banco, nel trasporto chiesto,
e stampa le righe COMPLETE di ``safe_strategy_trades`` del replay (stato,
motivo, meta) e le richieste manuali (``safe_strategy_requests``): sono il
"diario" delle azioni che il rapporto di parita' riassume in una riga.

Uso: python AUDIT_2026-10-02/sonda_diario_azioni.py <coda|canale> [evento]
"""
import json
import logging
import os
import sys

sys.path.insert(0, os.getcwd())
logging.basicConfig(level=logging.WARNING)

from Betfair.stream.backtest import certifica as CE  # noqa: E402
from Betfair.stream.backtest import registro_bot as REG  # noqa: E402
from Betfair.stream.backtest import trasporto as TRA  # noqa: E402

trasp = sys.argv[1]
ev = sys.argv[2] if len(sys.argv) > 2 else "35760084"
DATA = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\_live_raw"
print("SAFE_ORDINI_VIA_CANALE nell'ambiente PRIMA del replay:",
      repr(os.environ.get("SAFE_ORDINI_VIA_CANALE")))
fn = REG.bot("safe_base").funzione_replay()
with CE._freni_da_banco():
    with TRA.contesto("safe_base", trasp) as st:
        r = fn(ev, data_dir=DATA, scenario="ordini-manuali", ogni_ms=0, campioni_diff=0)
        print("SAFE_ORDINI_VIA_CANALE DURANTE il replay:",
              repr(os.environ.get("SAFE_ORDINI_VIA_CANALE")))
        db = getattr(st.get("strategia"), "db", None)
        print("azioni del referto:", getattr(r, "azioni", None))
        for nome in ("trades", "requests"):
            for riga in list(getattr(db, nome, []) or []):
                print("[%s]" % nome, json.dumps(riga, default=str, ensure_ascii=False)[:1500])
        for n in (getattr(r, "note", []) or []):
            if any(k in n for k in ("righe per stato", "ordini reali", "fill:", "attivita'")):
                print("nota:", n[:400])
