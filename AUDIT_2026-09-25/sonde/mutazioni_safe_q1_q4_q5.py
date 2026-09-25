"""Falsificazione dei test di Q1/Q4/Q5 (25/09): ogni mutazione deve far
diventare ROSSO almeno un test; poi il file torna identico (hash verificato).

Il ripristino e' dal CONTENUTO tenuto in memoria, mai da `git checkout`
(incidente del 23/09: cancellava il lavoro del delegato).

Lancio (sandbox): SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x
SUPABASE_KEY=x python AUDIT_2026-09-25/sonde/mutazioni_safe_q1_q4_q5.py
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
TEST = [
    "Betfair/safe_strategy/tests/test_safe_q1_q4_q5_2026_09_25.py",
    "Betfair/safe_strategy/tests/test_engine.py",
    "Betfair/safe_strategy/tests/test_certificazione_c3_2026_09_16.py",
    "Betfair/safe_strategy/tests/test_replay_tennis_2026_09_16.py",
    "Betfair/safe_strategy/tests/test_cert_2026_09_13.py",
]

MUTAZIONI = [
    ("Q1 banda di banca tolta (ok sempre True)", "Betfair/safe_strategy/engine.py",
     'None if dog_lay is None else in_range(dog_lay, params["dogLayMin"],\n'
     '                                                  params["dogLayMax"]),',
     "None if dog_lay is None else True,"),
    ("Q1 estremi esclusi", "Betfair/safe_strategy/engine.py",
     'None if dog_lay is None else in_range(dog_lay, params["dogLayMin"],\n'
     '                                                  params["dogLayMax"]),',
     'None if dog_lay is None else (params["dogLayMin"] < dog_lay < params["dogLayMax"]),'),
    ("Q1 default 20 -> 18", "Betfair/safe_strategy/engine.py",
     '"dogLayMin": 20,', '"dogLayMin": 18,'),
    ("Q1 Lettura A rimessa (favLive nel merge)", "Betfair/safe_strategy/engine.py",
     '"dogLayMin": _num(b.get("dogLayMin"), d["base"]["dogLayMin"]),',
     '"dogLayMin": _num(b.get("dogLayMin"), d["base"]["dogLayMin"]),\n'
     '            "favLiveMin": 1.2, "favLiveMax": 1.34,'),
    ("Q4 veto mai applicato", "Betfair/safe_strategy/engine.py",
     'if not params.get("vetoCampionati", True) or competition is None:',
     "if True:"),
    ("Q4 veto che non guarda il parametro", "Betfair/safe_strategy/engine.py",
     'if not params.get("vetoCampionati", True) or competition is None:',
     "if competition is None:"),
    ("Q4 competizione assente = veto (n/d)", "Betfair/safe_strategy/engine.py",
     'if not params.get("vetoCampionati", True) or competition is None:\n        return None',
     'if not params.get("vetoCampionati", True):\n        return None\n'
     '    if competition is None:\n        return ConditionCheck("campionato", "x", "n/d", None)'),
    ("Q4 Bundesliga 2 dopo Bundesliga (motivo sbagliato)",
     "Betfair/safe_strategy/veto_campionati.py",
     'frasi=("bundesliga 2", "2 bundesliga", "bundesliga ii", "zweite bundesliga",',
     'frasi=("zzz_mai",'),
    ("Q4 esclusione austriaca tolta", "Betfair/safe_strategy/veto_campionati.py",
     'frasi=("bundesliga", "1 bundesliga"),\n        escluse=("austria", "austrian", "osterreich", "oesterreich"),',
     'frasi=("bundesliga", "1 bundesliga"),\n        escluse=(),'),
    ("Q4 confronto a pezzi di parola", "Betfair/safe_strategy/veto_campionati.py",
     'return f" {frase} " in f" {testo} "', "return frase in testo"),
    ("Q4 accenti non tolti", "Betfair/safe_strategy/veto_campionati.py",
     's = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()',
     's = s.lower()'),
    ("Q4 voce coppe senza 'pokal'", "Betfair/safe_strategy/veto_campionati.py",
     '"coupe", "pokal", "beker"', '"coupe", "beker"'),
    ("Q4 lista TS divergente", "frontend/src/lib/vetoCampionati.ts",
     "frasi: ['bolivia', 'bolivian', 'boliviana', 'boliviano'],",
     "frasi: ['bolivia', 'bolivian', 'boliviana'],"),
    ("Q5 default 1.02 -> 1.01", "Betfair/safe_strategy/engine.py",
     '"backMin": 1.02,', '"backMin": 1.01,'),
    ("Q5 T1 torna specchio", "Betfair/safe_strategy/certificazione_tennis.py",
     "if lo is None or abs(lo - SPEC_TENNIS_BACK_MIN) > 1e-9:", "if False:"),
    ("B8 banda non confrontata col corso", "Betfair/safe_strategy/certificazione.py",
     '    if not _banda_uguale((v.par.get("dogLayMin"), v.par.get("dogLayMax")),\n'
     '                         SPEC_BASE["dogLay"]):',
     '    if False:'),
    ("B8 prezzo del segnale non guardato", "Betfair/safe_strategy/certificazione.py",
     "    if q is not None and not E.in_range(float(q), lo, hi):",
     "    if False:"),
    ("B8 prezzo d'ordine non guardato", "Betfair/safe_strategy/certificazione.py",
     "    if e is not None and not E.in_range(float(e), lo, hi):",
     "    if False:"),
    ("B9 muto", "Betfair/safe_strategy/certificazione.py",
     '    if "favLive" in v.check:', '    if False:'),
    ("B9 non guarda i parametri", "Betfair/safe_strategy/certificazione.py",
     '    for k in ("favLiveMin", "favLiveMax"):', '    for k in ():'),
]


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _pytest() -> tuple[int, str]:
    r = subprocess.run([sys.executable, "-m", "pytest", *TEST, "-q", "-x",
                        "-p", "no:cacheprovider", "-m", "not cert"],
                       cwd=RADICE, capture_output=True, text=True)
    righe = [x for x in r.stdout.splitlines() if x.startswith("FAILED") or " passed" in x
             or " failed" in x]
    return r.returncode, " | ".join(righe[-3:])


def main() -> int:
    esiti = []
    filtro = sys.argv[1] if len(sys.argv) > 1 else ""
    for nome, rel, vecchio, nuovo in MUTAZIONI:
        if filtro and filtro not in nome:
            continue
        f = RADICE / rel
        raw = f.read_bytes()
        prima = _sha(f)
        testo = raw.decode("utf-8")
        crlf = "\r\n" in testo
        norm = testo.replace("\r\n", "\n")
        if norm.count(vecchio) != 1:
            esiti.append((nome, "MUTAZIONE NON APPLICABILE", ""))
            continue
        mutato = norm.replace(vecchio, nuovo, 1)
        if crlf:
            mutato = mutato.replace("\n", "\r\n")
        try:
            f.write_bytes(mutato.encode("utf-8"))
            rc, dove = _pytest()
        finally:
            f.write_bytes(raw)
        assert _sha(f) == prima, f"RIPRISTINO FALLITO su {rel}"
        esiti.append((nome, "ROSSO (ok)" if rc != 0 else "VERDE (test NON falsificato!)", dove))
    for nome, esito, dove in esiti:
        print(f"- {nome}: {esito}\n    {dove}")
    return 0 if all(e[1] == "ROSSO (ok)" for e in esiti) else 1


if __name__ == "__main__":
    raise SystemExit(main())
