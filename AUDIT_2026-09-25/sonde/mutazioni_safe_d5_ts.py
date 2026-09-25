"""FALSIFICAZIONE dei test D5 lato PAGINA (motore TS). Stessa disciplina di
`mutazioni_safe_d5.py`: ripristino dal contenuto in memoria + hash.

Uso (dalla radice del worktree, con frontend/node_modules):
  python AUDIT_2026-09-25/sonde/mutazioni_safe_d5_ts.py
"""
from __future__ import annotations

import hashlib
import subprocess
import sys

ENG = "frontend/src/lib/safeStrategy.ts"
VETO = "frontend/src/lib/vetoCampionati.ts"
T = ["src/lib/safeStrategy.d5.test.ts", "src/lib/vetoCampionati.test.ts",
     "src/lib/safeStrategy.q7q12.test.ts"]

MUT = [
    ("P1 finale ignorata", VETO, "    if (ROUND_FINALE.includes(ultimo)) return true;",
     "    if (false) return true;"),
    ("P1 piazzamenti come finali", VETO,
     "    if (PAROLE_PIAZZAMENTO.some((p) => contiene(tutto, p))) return false;", ""),
    ("P1 nome anche col round", ENG, "    } else if (nomeIndicaFinale(extra.eventName)) {",
     "    } if (nomeIndicaFinale(extra.eventName)) {"),
    ("P1 competizione assente zittisce la finale", ENG,
     "    const label = 'Campionato non vietato dal corso';\n    if (competition != null) {",
     "    const label = 'Campionato non vietato dal corso';\n    if (competition == null) return null;\n"
     "    if (competition != null) {"),
    ("P1 la pagina non legge fixture_round", ENG,
     "        fixtureRound: typeof p.fixture_round === 'string' ? p.fixture_round.trim() || null : null,",
     "        fixtureRound: null,"),
    ("P4 nomi squadra ignorati", ENG,
     "    if (squadraFemminile(extra.home) || squadraFemminile(extra.away)) {", "    if (false) {"),
    ("P4 'w' ovunque", VETO,
     "    if (parole[parole.length - 1] === SUFFISSO_SQUADRA_FEMMINILE) return true;",
     "    if (parole.includes(SUFFISSO_SQUADRA_FEMMINILE)) return true;"),
    ("P2 Bolivia di nuovo in lista", VETO, "    // BOLIVIA: tolta",
     "    { codice: 'bolivia', nome: 'b', citazione: 'x', frasi: ['bolivian'], escluse: [] },\n"
     "    // BOLIVIA: tolta"),
    ("P5 minimo ignorato", ENG, "            if (meetings < minMeetings) {", "            if (false) {"),
    ("P5 chiave vecchia", ENG,
     "                  h2hManyGoals: numOrNull(p.selection_hint.h2h_many_goals),",
     "                  h2hManyGoals: null,"),
    ("P5 soglia 0,58 cambiata", ENG, "        h2hManyGoalsRateMax: 0.58,",
     "        h2hManyGoalsRateMax: 0.12,"),
    ("P5 lato della difesa invertito", ENG,
     "    const opponent: SideId = laidSide === 'home' ? 'away' : 'home';\n    let meetings",
     "    const opponent: SideId = laidSide;\n    let meetings"),
    ("P6 forze non dichiarate", ENG, "    if (forze !== null) parti.push(forze);", ""),
    ("P7 bordo incluso", ENG, "    if (qFav < favSuperMax && leader !== fav) {",
     "    if (qFav <= favSuperMax && leader !== fav) {"),
    ("P7 super favorito escluso anche lui", ENG, "    if (qFav < favSuperMax && leader !== fav) {",
     "    if (qFav < favSuperMax) {"),
    ("P7 legge leaderPreMax", ENG,
     "            favSuperMax: num(t.favSuperMax, d.tennis.favSuperMax),",
     "            favSuperMax: num(t.leaderPreMax, d.tennis.favSuperMax),"),
]


def main() -> int:
    rosse = 0
    for nome, path, vecchio, nuovo in MUT:
        orig = open(path, "rb").read()
        h0 = hashlib.sha256(orig).hexdigest()
        testo = orig.decode("utf-8")
        if "\r\n" in testo:
            vecchio, nuovo = vecchio.replace("\n", "\r\n"), nuovo.replace("\n", "\r\n")
        if testo.count(vecchio) != 1:
            print(f"[??] {nome}: frammento trovato {testo.count(vecchio)} volte")
            continue
        try:
            open(path, "wb").write(testo.replace(vecchio, nuovo).encode("utf-8"))
            r = subprocess.run("npx vitest run " + " ".join(T), cwd="frontend", shell=True,
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            rossa = r.returncode != 0
        finally:
            open(path, "wb").write(orig)
            assert hashlib.sha256(open(path, "rb").read()).hexdigest() == h0, path
        rosse += rossa
        print(f"[{'ROSSA' if rossa else 'VIVA!'}] {nome}", flush=True)
    print(f"\n{rosse}/{len(MUT)} mutazioni rosse")
    return 0 if rosse == len(MUT) else 1


if __name__ == "__main__":
    sys.exit(main())
