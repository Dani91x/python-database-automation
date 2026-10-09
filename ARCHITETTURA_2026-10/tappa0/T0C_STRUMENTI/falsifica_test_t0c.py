"""T0C - FALSIFICAZIONE DEI TEST NUOVI (PSB par. 6.7, catalogo n. 35; CANT par. 0
regola 5): ogni mutazione del codice di cassetta/ombra/congela/certifica DEVE
far diventare rosso almeno un test di
``Betfair/stream/tests/test_banco_cassetta_ombra_t0c_2026_10_09.py``.

Per ogni mutazione: sha256 del file prima, sostituzione testuale (UNA
occorrenza, che deve esistere), pytest del file di test, ripristino del testo
originale e VERIFICA che lo sha256 sia tornato quello di prima (se no, si
ferma tutto con exit code 2).

Uso (dalla radice del repository; ~5 s a mutazione):
    python ARCHITETTURA_2026-10/tappa0/T0C_STRUMENTI/falsifica_test_t0c.py
ASCII-only.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys

TEST = "Betfair/stream/tests/test_banco_cassetta_ombra_t0c_2026_10_09.py"
B = "Betfair/stream/backtest/"

#: (nome, file, testo vecchio, testo nuovo)
MUTAZIONI = [
    ("ombra: confronto sempre vuoto", B + "ombra.py",
     "    out: List[Divergenza] = []\n    for k in ordine:",
     "    out: List[Divergenza] = []\n    ordine = []\n    for k in ordine:"),
    ("ombra: tolleranza 1 allargata a 'tempo' ovunque", B + "ombra.py",
     "return str(testo).lstrip().startswith(PREFISSI_RIGHE_TEMPI)",
     "return 'tempo' in str(testo).lower() or str(testo).lstrip().startswith(PREFISSI_RIGHE_TEMPI)"),
    ("ombra: tolleranza 2 toglie l'intera riga del codice", B + "ombra.py",
     "testo = RE_CODICE_BOT.sub(SEGNAPOSTO_CODICE_BOT, testo)",
     "continue"),
    ("ombra: bet_id fra gli id d'orologio", B + "ombra.py",
     '"stopped_at", "heartbeat_at")',
     '"stopped_at", "heartbeat_at", "bet_id", "pid")'),
    ("ombra: id d'orologio senza ordinale (tutti uguali)", B + "ombra.py",
     'self.mappa = {v: "#id%d" % (i + 1) for i, v in enumerate(ids)}',
     'self.mappa = {v: "#id" for i, v in enumerate(ids)}'),
    ("cassetta: sigillo mai verificato", B + "cassetta.py",
     '    if atteso != calcolato:\n        return "sigillo: sha256',
     '    if False:\n        return "sigillo: sha256'),
    ("cassetta: forma non canonica (chiavi non ordinate)", B + "cassetta.py",
     'return json.dumps(voce, sort_keys=True, separators=(",", ":"), ensure_ascii=True)',
     'return json.dumps(voce, sort_keys=False, separators=(",", ":"), ensure_ascii=True)'),
    ("cassetta: repr degli oggetti (indirizzi)", B + "cassetta.py",
     'return "<%s>" % type(x).__name__',
     'return repr(x)'),
    ("cassetta: le toppe non si tolgono", B + "cassetta.py",
     "        while self._fatte:\n            cls, nome, vecchia, aveva = self._fatte.pop()",
     "        while False:\n            cls, nome, vecchia, aveva = self._fatte.pop()"),
    ("cassetta: DB delle sottoclassi non osservato", B + "cassetta.py",
     "        for nome in METODI_DB_MEMORIA:\n            for cls in type(self).__mro__:",
     "        for nome in ():\n            for cls in type(self).__mro__:"),
    ("cassetta: decisioni mai scritte", B + "cassetta.py",
     '            self.voce("decisione", quando, "referto%d" % i, dati)',
     '            pass'),
    ("cassetta: fill non registrato", B + "cassetta.py",
     '            reg.voce("fill", ms if isinstance(ms, (int, float)) else reg.ora_ms,',
     '            (lambda *a: None)(ms if isinstance(ms, (int, float)) else reg.ora_ms,'),
    ("congela: manifesto sovrascrivibile", B + "congela.py",
     "            if gia[\"sha256\"] == v[\"sha256\"]:\n                continue\n            raise",
     "            if True:\n                continue\n            raise"),
    ("congela: catena mai verificata", B + "congela.py",
     "        if v.get(\"catena\") != atteso:",
     "        if False:"),
    ("congela: verifica non ricalcola lo sha", B + "congela.py",
     "        if sha != v.get(\"sha256\") or n != v.get(\"byte\"):",
     "        if False:"),
    ("certifica: _lavora ignora la cassetta", B + "certifica.py",
     "    if not _CAS.accesa():\n        return _lavora_di_sempre(compito)",
     "    if True:\n        return _lavora_di_sempre(compito)"),
    ("ombra: --congela senza prova di determinismo", B + "ombra.py",
     "    if a.congela and not a.ombra:",
     "    if False:"),
]


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def pytest():
    out = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "-p", "no:cacheprovider"],
                         capture_output=True, text=True)
    m = re.search(r"(\d+) failed", out.stdout)
    p = re.search(r"(\d+) passed", out.stdout)
    return (int(m.group(1)) if m else 0), (int(p.group(1)) if p else 0), out.returncode


def main():
    rossi_base, verdi_base, _rc = pytest()
    print("base: %d rossi, %d verdi" % (rossi_base, verdi_base))
    if rossi_base or not verdi_base:
        # un banco di prova che non gira (0 verdi) non falsifica niente
        return 2
    ko = 0
    print("| mutazione | file | test rossi | esito |")
    print("|---|---|---|---|")
    for nome, f, vecchio, nuovo in MUTAZIONI:
        prima = sha(f)
        testo = open(f, encoding="utf-8").read()
        if testo.count(vecchio) != 1:
            print("| %s | %s | - | TESTO DA MUTARE NON TROVATO (%d) |" % (nome, f, testo.count(vecchio)))
            ko += 1
            continue
        try:
            open(f, "w", encoding="utf-8", newline="").write(testo.replace(vecchio, nuovo))
            rossi, _verdi, _rc = pytest()
        finally:
            open(f, "w", encoding="utf-8", newline="").write(testo)
        if sha(f) != prima:
            print("!! RIPRISTINO FALLITO su %s" % f)
            return 2
        esito = "ROSSO" if rossi else "VERDE (mutazione NON catturata)"
        ko += 0 if rossi else 1
        print("| %s | %s | %d | %s |" % (nome, f.split("/")[-1], rossi, esito))
    print("ESITO: %d mutazioni, %d non catturate; file ripristinati (sha256 verificato)"
          % (len(MUTAZIONI), ko))
    return 1 if ko else 0


if __name__ == "__main__":
    sys.exit(main())
