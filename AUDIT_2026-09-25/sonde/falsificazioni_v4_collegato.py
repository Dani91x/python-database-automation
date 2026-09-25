"""FALSIFICAZIONE del collegamento dell'atlante v4 (25/09/2026 sera).

Per ogni rottura: una sostituzione MINIMA nel codice di produzione, pytest
sui test del collegamento (devono diventare ROSSI), ripristino DAL TESTO IN
MEMORIA (mai git checkout: incidente del 23/09) con verifica dell'hash.
Alla fine la suite torna verde. Uso (dalla radice del worktree, sandbox DB):
    python AUDIT_2026-09-25/sonde/falsificazioni_v4_collegato.py
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TEST = ["Betfair/stream/tests/test_atlante_v4_collegato_2026_09_25.py"]
SC = "Betfair/stream/scalper/"

ROTTURE = [
    ("M1 select senza la durata del recupero", SC + "genera_atlante.py",
     '"halftime_home,halftime_away,extra:raw_json->fixture->status->extra")', '"halftime_home,halftime_away")'),
    ("M2 _sequenze non somma il v4", SC + "genera_atlante.py",
     "            aggiungi_v4(stato, m, per_fixture.get(int(m[\"fixture_id\"]), []), affidabile=affidabile_v4)\r\n",
     "            pass\r\n"),
    ("M3 motore: incrementale senza v4", SC + "atlante_a_domanda.py",
     "                    G.aggiungi_v4(st, m, gg)\r\n", "                    pass\r\n"),
    ("M4 bootstrap: stagione sempre affidabile", SC + "genera_atlante.py",
     "                aff_v4 = V4.affidabile_da_quota(con, tot_e)", "                aff_v4 = True"),
    ("M5 incrementale: conteggi non cumulati", SC + "genera_atlante.py",
     "        q[0] += int(con)\r\n        q[1] += int(tot)\r\n", "        pass\r\n"),
    ("M6 tempo: matchStatus ignorato", SC + "atlante_v4.py",
     "    if st:\r\n        if any(k in st for k in _STATI_2T):", "    if False:\r\n        if any(k in st for k in _STATI_2T):"),
    ("M7 tempo: stato vecchio creduto", SC + "atlante_v4.py",
     "_MAX_MINUTO_1T = 60 ", "_MAX_MINUTO_1T = 999 "),
    ("M8 tempo: intervallo con la regola del 1T in gioco", SC + "atlante_v4.py",
     "        if any(k in st for k in _STATI_INTERVALLO):\r\n            return 1\r\n", ""),
    ("M9 Safe: tempo non passato", "Betfair/safe_strategy/opportunity.py",
     "tempo=tempo_da_payload(payload),", "tempo=None,"),
    ("M10 Safe: lambda della fixture passati", "Betfair/safe_strategy/opportunity.py",
     "tempo=tempo_da_payload(payload),",
     "tempo=tempo_da_payload(payload), lambda_home=float(lambdas[0]), lambda_away=float(lambdas[1]),"),
    ("M11 Mike: tempo non passato", "Betfair/mike/dossier.py",
     "tempo=tempo_da_payload(dict(payload or {}, minute=minute)),", "tempo=None,"),
    ("M12 ripiego v3 per lega mai", SC + "atlante_v4.py",
     "    if not isinstance((atlas or {}).get(\"global\"), dict) or not atlas.get(\"global\"):\r\n        return None",
     "    if True:\r\n        return None"),
    ("M13 ripiego v3 non dichiarato in nota", SC + "atlante_v4.py",
     "    out[\"nota\"] = f\"{out.get('nota')} [atlante v3: recupero non modellato ({motivo})]\"",
     "    out[\"nota\"] = f\"{out.get('nota')}\""),
    ("M14 motore: adotta dal DB uno stato senza v4", SC + "atlante_a_domanda.py",
     "        if not isinstance(rows[0][\"stato\"].get(\"v4\"), dict):", "        if False:"),
    ("M15 motore: lega senza v4 non ricalcolata", SC + "atlante_a_domanda.py",
     "(l not in self.leghe or not self._ha_v4(l))", "(l not in self.leghe)"),
    ("M16 stagione di riferimento = ultima contata", SC + "genera_atlante.py",
     "for x in v[\"stagioni\"]) + 1", "for x in v[\"stagioni\"])"),
    ("M17 assembla_v4 senza leghe affidabili: NaN", SC + "atlante_v4.py",
     "    if L and not affid.any():\r\n        affid = np.ones(L, dtype=bool)\r\n", ""),
    ("M18 globale v4 sempre solido", SC + "atlante_v4.py",
     "    globale_solido = n_affid >= G.MIN_FIXTURES_GLOBALE", "    globale_solido = True"),
    ("M19 v4 con la seconda lista di fixture_id", SC + "genera_atlante.py",
     "recupero_affidabile=bool(affidabile), registra_fixture=False)",
     "recupero_affidabile=bool(affidabile), registra_fixture=True)"),
    ("M20 Mike: recupero atteso non volatile", "Betfair/mike/service.py",
     '    "hazard_recupero_atteso_min",\r\n', ""),
    ("M21 Safe: nota senza versione", "Betfair/safe_strategy/opportunity.py",
     "divergenza {div * 100:.0f}%; {versione_txt}; {eta}\")", "divergenza {div * 100:.0f}%; {eta}\")"),
    ("M22 workflow senza numpy", ".github/workflows/hazard_atlas.yml",
     'run: python -m pip install --disable-pip-version-check "numpy==2.4.6"', "run: echo niente"),
    ("M23 candidati: scipy di nuovo in testa", SC + "validazione_hazard/candidati.py",
     "import numpy as np\r\n\r\n\r\ndef minimize_scalar",
     "import numpy as np\r\nfrom scipy.optimize import minimize_scalar as _x  # noqa\r\n\r\n\r\ndef minimize_scalar"),
    ("M24 v4: minuto del recupero 1T come ripresa (cella propria off, tempo ignorato)", SC + "atlante_v4.py",
     "    if tempo == 1 and m >= 45:\r\n        return \"recupero_1T\"", "    if False:\r\n        return \"recupero_1T\""),
]


def _h(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def pytest_rosso() -> tuple:
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *TEST],
                       cwd=RADICE, capture_output=True, text=True, timeout=600)
    righe = [x for x in r.stdout.splitlines() if x.strip()]
    return r.returncode != 0, (righe[-1] if righe else r.stderr[-200:])


def main() -> int:
    esiti = []
    for nome, rel, vecchio, nuovo in ROTTURE:
        path = os.path.join(RADICE, rel)
        with open(path, "rb") as fh:
            originale = fh.read()
        testo = originale.decode("utf-8")
        if testo.count(vecchio) != 1:
            esiti.append((nome, "NON APPLICABILE (testo non trovato una volta)", ""))
            continue
        try:
            with open(path, "wb") as fh:
                fh.write(testo.replace(vecchio, nuovo).encode("utf-8"))
            rosso, coda = pytest_rosso()
        finally:
            with open(path, "wb") as fh:
                fh.write(originale)
        with open(path, "rb") as fh:
            ok = _h(fh.read()) == _h(originale)
        esiti.append((nome, "ROSSA" if rosso else "VERDE (!)", f"{coda} | ripristino {'OK' if ok else 'KO'}"))
        print(esiti[-1], flush=True)
    rosso, coda = pytest_rosso()
    print("\nsuite dopo i ripristini:", "ROSSA (!)" if rosso else "VERDE", coda)
    print(f"rotture rosse: {sum(1 for e in esiti if e[1] == 'ROSSA')}/{len(esiti)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
