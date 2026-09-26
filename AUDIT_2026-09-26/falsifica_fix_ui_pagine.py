# -*- coding: utf-8 -*-
"""Falsificazione dei fix FIX_UI_PAGINE_ADMIN26 (26/09).

Per ogni mutazione: copia di sicurezza dei byte, UNA sostituzione (che deve
esistere una e una sola volta), lancio del test mirato, ripristino dei byte
originali e controllo sha256 (il file deve tornare IDENTICO). Una mutazione
e' «falsificata» se il test diventa ROSSO (exit != 0).

Uso (dalla radice del worktree):
    .venv/Scripts/python.exe AUDIT_2026-09-26/falsifica_fix_ui_pagine.py
Non interrompere: ogni file mutato si ripristina nel `finally`.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]
FE = RADICE / "frontend"
ENV = {**os.environ, "SUPABASE_URL": "http://127.0.0.1:9", "SUPABASE_SERVICE_ROLE_KEY": "x",
       "SUPABASE_KEY": "x"}
PY = str(RADICE / ".venv" / "Scripts" / "python.exe")
NPX = "npx.cmd" if os.name == "nt" else "npx"


def vit(*args: str) -> list[str]:
    return [NPX, "vitest", "run", *args]


def pyt(*args: str) -> list[str]:
    return [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args]


# (nome, file, vecchio, nuovo, comando, cartella)
MUTAZIONI = [
    ("F-2 barra paper per piazzamento", "frontend/src/lib/composizioneObiettivo.ts",
     "!delGiorno(ultima ?? a.placed_at)", "!delGiorno(a.placed_at)",
     vit("src/components/controlroom/fixPagine2609.giornata.test.tsx"), FE),
    ("F-1 plancia senza P&L chiuse", "frontend/src/components/controlroom/useControlRoom.ts",
     "bots: botsConPnl,", "bots,",
     vit("src/components/controlroom/useControlRoom.test.tsx", "-t", "26/09 correzioni"), FE),
    ("F-1 pnlChiuseDelGiorno senza filtro modalita'", "frontend/src/lib/posizioniChiuse.ts",
     "{ giorno: f.giorno, bot: f.bot, modo: f.modo }", "{ giorno: f.giorno, bot: f.bot }",
     vit("src/components/controlroom/fixPagine2609.giornata.test.tsx"), FE),
    ("F-3 letta e vuota = trattino", "frontend/src/components/controlroom/SplitSport.tsx",
     "mio ? mio.pnl : (letto ? 0 : null)", "mio ? mio.pnl : null",
     vit("src/components/controlroom/fixPagine2609.giornata.test.tsx"), FE),
    ("F-4 segno del tick rovesciato", "frontend/src/lib/riskMath.ts",
     "return entrySide === 'lay' ? t : -t;", "return entrySide === 'lay' ? -t : t;",
     vit("src/components/controlroom/fixPagine2609.tick.test.ts"), FE),
    ("F-4 prezzo dello stesso lato", "frontend/src/components/controlroom/dettaglioRiga.ts",
     "const ora = lato === 'lay' ? back : lato === 'back' ? lay : null;",
     "const ora = lato === 'lay' ? lay : lato === 'back' ? back : null;",
     vit("src/components/controlroom/fixPagine2609.tick.test.ts"), FE),
    ("F-5 UI None-None", "frontend/src/components/controlroom/dettaglioRiga.ts",
     "punteggio: punteggioIngresso(t.score_at_entry),", "punteggio: str(t.score_at_entry),",
     vit("src/components/controlroom/dettaglioRiga.test.tsx", "-t", "punteggio mancante"), FE),
    ("F-5 Mike f-string senza guardia", "Betfair/mike/service.py",
     "    score_str = _punteggio_ingresso(payload)",
     "    score_str = f\"{payload.get('score_home')}-{payload.get('score_away')}\"",
     pyt("Betfair/mike/tests/test_mike_punteggio_ingresso_2026_09_26.py"), RADICE),
    ("F-6 servizio senza scadenza", "Betfair/safe_strategy/bot_service.py",
     "    _scadi_proposte_vecchie(db, now, st)", "    pass",
     pyt("Betfair/safe_strategy/tests/test_proposte_scadute_2026_09_26.py"), RADICE),
    ("F-6 query senza eta'", "Betfair/safe_strategy/bot_db.py",
     '.eq("kind", "place").eq("status", "proposed").lt("created_at", cutoff).execute()',
     '.eq("kind", "place").eq("status", "proposed").execute()',
     pyt("Betfair/safe_strategy/tests/test_proposte_scadute_2026_09_26.py"), RADICE),
    ("F-6 UI senza filtro", "frontend/src/lib/controlRoomProposte.ts",
     "return Number.isFinite(t) && nowMs - t > SCADENZA_PROPOSTA_ORE * 3600 * 1000;",
     "return false;",
     vit("src/components/controlroom/useControlRoom.test.tsx", "-t", "26/09 correzioni"), FE),
    ("F-7 P mercato de-vig", "frontend/src/components/controlroom/SchedaPropostaOpportunita.tsx",
     "valore={PCT(ap?.p_implicita ?? pMercatoProposta(p.price, p.p_implied))}",
     "valore={PCT(ap?.p_implicita ?? p.p_implied)}",
     vit("src/components/controlroom/fixPagine2609.varie.test.tsx"), FE),
    ("F-8 zero dello stream scritto", "Betfair/safe_strategy/service.py",
     "        if not (dallo_stream and not tm):", "        if True:",
     pyt("Betfair/safe_strategy/tests/test_volume_mo_2026_09_26.py"), RADICE),
    ("F-10 set_summary senza set in corso", "Betfair/stream/tennis_live/tennis_runner.py",
     "    if (gh or ga) and len(parti) < attesi:", "    if False:",
     pyt("Betfair/stream/tennis_live/tests/test_set_summary_2026_09_26.py"), RADICE),
    ("F-10 LIVE su partita finita", "frontend/src/pages/MarketWatch.tsx",
     "{partitaTennisFinita(score?.status, mo?.status) ? (", "{false ? (",
     vit("src/pages/MarketWatch.test.tsx"), FE),
    ("KO 9-bis rischio sommato", "frontend/src/pages/MarketWatch.tsx",
     "€{eventExposure(live).toFixed(2)}", "€{eventExposure(positions).toFixed(2)}",
     vit("src/pages/MarketWatch.test.tsx"), FE),
    ("F-12 chiudi ora lordo", "frontend/src/components/controlroom/useControlRoom.ts",
     "aliquotaDi(t.commission, (t.meta ?? {})['commission'])),", "0),",
     vit("src/components/controlroom/useControlRoom.test.tsx", "-t", "26/09 correzioni"), FE),
    ("F-13 title 4+ gol", "frontend/src/components/controlroom/SchedaMike.tsx",
     'title="probabilità di ESATTAMENTE 4 gol secondo il modello del bot">',
     'title="probabilità di 4+ gol secondo il modello del bot">',
     vit("src/components/controlroom/dettaglioRiga.test.tsx", "-t", "esatti"), FE),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> int:
    esiti = []
    solo = sys.argv[1] if len(sys.argv) > 1 else None   # filtro facoltativo sul nome
    for nome, rel, vecchio, nuovo, cmd, cwd in MUTAZIONI:
        if solo and solo not in nome:
            continue
        path = RADICE / rel
        orig = path.read_bytes()
        testo = orig.decode("utf-8")
        n = testo.count(vecchio)
        if n != 1:
            esiti.append({"mutazione": nome, "esito": f"NON APPLICABILE (occorrenze {n})"})
            continue
        try:
            path.write_bytes(testo.replace(vecchio, nuovo).encode("utf-8"))
            r = subprocess.run(cmd, cwd=cwd, env=ENV, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", shell=False)
            rosso = r.returncode != 0
        finally:
            path.write_bytes(orig)
        ok_rip = sha(path.read_bytes()) == sha(orig)
        esiti.append({"mutazione": nome, "file": rel, "test_rosso": rosso,
                      "ripristino_identico": ok_rip})
        print(f"{'ROSSO' if rosso else 'VERDE (!)'} ripristino={'ok' if ok_rip else 'KO'}  {nome}",
              flush=True)
    out = RADICE / "AUDIT_2026-09-26" / "falsifica_fix_ui_pagine.json"
    out.write_text(json.dumps(esiti, ensure_ascii=False, indent=2), encoding="utf-8")
    tutti = all(e.get("test_rosso") and e.get("ripristino_identico") for e in esiti)
    print("TUTTE ROSSE E RIPRISTINATE" if tutti else "ATTENZIONE: vedi il json")
    return 0 if tutti else 1


if __name__ == "__main__":
    sys.exit(main())
