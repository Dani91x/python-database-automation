"""Falsificazioni del Replay Tennis (frontend): ogni mutazione DEVE far diventare
rosso il test vitest indicato. File ripristinato byte per byte dopo ogni mutazione.

Uso:  python3 AUDIT_2026-10-07/replay_tennis/falsifica_frontend.py
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
FE = RADICE / "frontend"
LIB = "src/lib/tennisReplay.ts"
PAG_T = "src/pages/TennisReplay.test.tsx"
LIB_T = "src/lib/tennisReplay.test.ts"
DEL_T = "src/lib/delayMercato.tennisReplay.test.ts"

MUTAZIONI = [
    ("F1 esito prima della chiusura del mercato", LIB,
     "    if (tsMs < new Date(market.settled_ts).getTime()) return null;\n", "", LIB_T),
    ("F2 handicap tennis senza categoria", LIB,
     "    if (t.includes('HANDICAP')) return 'HANDICAP';\n", "", LIB_T),
    ("F3 break etichettato coi game del set nuovo", LIB,
     "label = `Break di ${nome(vince)} (${gameDelPassaggio(prev, s)})`;",
     "label = `Break di ${nome(vince)} (${s.games.p1}-${s.games.p2})`;", LIB_T),
    ("F4 frame del tennis dalla RPC del calcio", LIB,
     "rpcFrames: 'get_replay_tennis_frames',", "rpcFrames: 'get_replay_frames',", LIB_T),
    ("F5 bet-delay del mercato ignorato", LIB,
     "? s * 1000 : DEFAULT_DELAY_MS", "? DEFAULT_DELAY_MS : DEFAULT_DELAY_MS", PAG_T),
    ("F6 punti oltre il cursore", LIB,
     "        if (r.ts > ts) break;\n", "", LIB_T),
    ("F7 sospensione scambiata con chiusura", LIB,
     "mo.some(id => ultimoAl(perMercato.get(id), step.ts)?.status === 'SUSPENDED')",
     "mo.some(id => ultimoAl(perMercato.get(id), step.ts)?.status === 'CLOSED')", LIB_T),
    ("F8 frame tennis non convertiti in EUR", "src/lib/live.ts",
     "        frames.push(...convertiFramesEur(part));\n        onProgress?.({ done: i + 1, total: windows.length, frames: frames.length });\n    }\n    return frames;",
     "        frames.push(...part);\n        onProgress?.({ done: i + 1, total: windows.length, frames: frames.length });\n    }\n    return frames;", LIB_T),
    ("F9 training: delay del mercato ignorato", "src/lib/trainingLadder.ts",
     "const delayMs = ctx.delayMsAt ? ctx.delayMsAt(cmd.market_id) : DEFAULT_DELAY_MS;",
     "const delayMs = DEFAULT_DELAY_MS;", DEL_T),
    ("F10 backtest: delay del mercato ignorato", "src/lib/ladderBacktest.ts",
     "            delayMs: inplay ? delayMs : 0,", "            delayMs: inplay ? DEFAULT_DELAY_MS : 0,", DEL_T),
    ("F11 tabellone del replay con la freschezza del live", "src/components/tennis/TennisMatchStats.tsx",
     "{freschezza ? freshnessLabel(updatedMs, now) : orarioPunteggio(updatedMs)}",
     "{freshnessLabel(updatedMs, now)}", PAG_T),
    ("F12 bot del calcio nell'Applica bot del tennis (FASE 2: pannello comune)", "src/pages/TennisReplay.tsx",
     '<ApplicaBotPanel\n                                            sport="tennis"\n',
     '<ApplicaBotPanel\n                                            sport="calcio"\n', PAG_T),
    ("F13 pannello backtest: delay mostrato sempre 5 s", "src/components/replay/LadderBacktestPanel.tsx",
     "const delaySec = Math.round((delayMsAt && marketId ? delayMsAt(marketId) : DEFAULT_DELAY_MS) / 1000);",
     "const delaySec = Math.round(DEFAULT_DELAY_MS / 1000);", PAG_T),
    ("F14 lista del tennis dalla RPC del calcio", LIB,
     "supabase.rpc('list_replays_tennis', { p_limit: limit })", "supabase.rpc('list_replays', { p_limit: limit })", PAG_T),
    ("F15 cursore non portato al passaggio in gioco (simboli fuori ordine)", LIB,
     "    if (inGiocoTs && inGiocoTs > timeline[0].ts) {", "    if (inGiocoTs) {", LIB_T),
    # FASE 2 (07/10): verificatore della barra tennis e barra parametrica
    ("F16 verificatore: break non controllato", "src/lib/tennisReplayVerificaBarra.ts",
     "        if (ev.has('BREAK') && !breakAtteso) {", "        if (ev.has('NIENTE') && !breakAtteso) {",
     "src/lib/tennisReplayVerificaBarra.test.ts"),
    ("F17 verificatore: simbolo perso non visto", "src/lib/tennisReplayVerificaBarra.ts",
     "            if (d < n) {", "            if (d < 0) {", "src/lib/tennisReplayVerificaBarra.test.ts"),
    ("F18 la pagina tennis mostra l'avviso del verificatore tennis (incoerenza iniettata)",
     "src/lib/tennisReplayVerificaBarra.ts",
     "    if (righe.length === 0) {\n",
     "    R('TENNIS_SET_SCENDONO', 'errore', 'MUTANTE');\n    if (righe.length === 0) {\n", PAG_T),
    ("F19 barra: titolo d'inizio fisso al calcio", "src/components/replay/TimelineSlider.tsx",
     "                        title={titoloInizio}\n", "                        title=\"Calcio d'inizio\"\n",
     "src/components/replay/TimelineSlider.test.tsx"),
    ("F20 simboli del tennis fuori dalla barra", "src/pages/TennisReplay.tsx",
     "events={markerTennis(simboliVisti)}", "events={[]}", PAG_T),
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    esiti = []
    for nome, rel, old, new, test in MUTAZIONI:
        p = FE / rel
        originale = p.read_bytes()
        prima = sha(p)
        testo = originale.decode("utf-8")
        assert testo.count(old) == 1, f"{nome}: testo da mutare non trovato una volta sola"
        try:
            p.write_bytes(testo.replace(old, new).encode("utf-8"))
            r = subprocess.run(["npx", "vitest", "run", test], cwd=FE, capture_output=True, text=True, timeout=600)
            rosso = r.returncode != 0
        finally:
            p.write_bytes(originale)
        assert sha(p) == prima, f"{nome}: ripristino fallito"
        esiti.append(rosso)
        print(("ROSSO " if rosso else "VERDE!") + f" {nome}  [{test}]")
    print(f"\n{sum(esiti)}/{len(esiti)} mutazioni rosse; file ripristinati (sha256 verificato)")
    return 0 if all(esiti) else 1


if __name__ == "__main__":
    sys.exit(main())
