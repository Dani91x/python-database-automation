"""Falsificazione dei test TypeScript (pagina Safe) delle decisioni del 25/09.

Ogni mutazione del motore della pagina deve far diventare ROSSO almeno un test
vitest; poi il file torna identico (hash). Ripristino dal contenuto in memoria.
Richiede `frontend/node_modules` (nel worktree: giunzione verso il principale).

Lancio: python AUDIT_2026-09-25/sonde/mutazioni_safe_ts_25_09.py
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
FE = RADICE / "frontend"
TEST = ["src/lib/safeStrategy.test.ts", "src/lib/vetoCampionati.test.ts",
        "src/lib/safeStrategy.q7q12.test.ts"]
TS = "src/lib/safeStrategy.ts"

MUTAZIONI = [
    ("Q1 banda di banca tolta", TS,
     "ok: dogLay === null ? null : inRange(dogLay, params.dogLayMin, params.dogLayMax),",
     "ok: dogLay === null ? null : true,"),
    ("Q4 veto mai applicato", TS,
     "if (!attivo || competition == null) return null;", "return null;"),
    ("Q4 veto ignora il parametro", TS,
     "if (!attivo || competition == null) return null;", "if (competition == null) return null;"),
    ("Q4 lista: pokal tolto", "src/lib/vetoCampionati.ts",
     "'coupe', 'pokal', 'beker'", "'coupe', 'beker'"),
    ("Q5 backMin 1.01", TS, "backMin: 1.02,", "backMin: 1.01,"),
    ("Q7 dato assente blocca", TS,
     "return { id: 'h2hDifesa', label, value: SELEZIONE_DATO_ASSENTE, ok: true };",
     "return { id: 'h2hDifesa', label, value: SELEZIONE_DATO_ASSENTE, ok: null };"),
    ("Q7 una parte assente blocca", TS,
     "ok: h2hOk !== false && difOk !== false };", "ok: h2hOk === true && difOk === true };"),
    ("Q10 punta ignora la sezione base", TS,
     "evaluatePunta(ctx, params.punta, params.base),", "evaluatePunta(ctx, params.punta),"),
    ("Q10 bande tolte dalla punta", TS,
     "checks.push(...preBandsChecks(ctx.preMatch, fav, bandePre ?? DEFAULT_PARAMS.base));",
     "void bandePre;"),
    ("Q12 lato del leader invertito", TS,
     "const qPre = leader === 1 ? pre.p1 : pre.p2;", "const qPre = leader === 1 ? pre.p2 : pre.p1;"),
    ("Q12 dato assente blocca", TS,
     "value: TENNIS_PRE_ASSENTE, ok: true });", "value: TENNIS_PRE_ASSENTE, ok: null });"),
]


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _vitest() -> tuple[int, str]:
    r = subprocess.run(["node", "node_modules/vitest/vitest.mjs", "run", *TEST],
                       cwd=FE, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    righe = [x.strip() for x in (r.stdout + r.stderr).splitlines()
             if "Tests " in x or "FAIL" in x]
    return r.returncode, " | ".join(righe[-2:])


def main() -> int:
    esiti = []
    for nome, rel, vecchio, nuovo in MUTAZIONI:
        f = FE / rel
        raw = f.read_bytes()
        prima = _sha(f)
        testo = raw.decode("utf-8")
        crlf = "\r\n" in testo
        norm = testo.replace("\r\n", "\n")
        if norm.count(vecchio) != 1:
            esiti.append((nome, f"MUTAZIONE NON APPLICABILE ({norm.count(vecchio)})", ""))
            continue
        mutato = norm.replace(vecchio, nuovo, 1)
        if crlf:
            mutato = mutato.replace("\n", "\r\n")
        try:
            f.write_bytes(mutato.encode("utf-8"))
            rc, dove = _vitest()
        finally:
            f.write_bytes(raw)
        assert _sha(f) == prima, f"RIPRISTINO FALLITO su {rel}"
        esiti.append((nome, "ROSSO (ok)" if rc != 0 else "VERDE (test NON falsificato!)", dove))
    for nome, esito, dove in esiti:
        print(f"- {nome}: {esito}\n    {dove}")
    return 0 if all(e[1] == "ROSSO (ok)" for e in esiti) else 1


if __name__ == "__main__":
    raise SystemExit(main())
