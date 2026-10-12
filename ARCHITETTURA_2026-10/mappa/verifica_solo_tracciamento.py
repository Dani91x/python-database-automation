"""Verifica "solo tracciamento" della mappatura dei flussi (decisione dell'utente, 12/10/2026).

L'utente: "se aggiungiamo solo una riga di codice di TRACCIAMENTO non c'e' bisogno dei replay
perche' non abbiamo cambiato nulla; gli unici test sono di corretto e uguale funzionamento".

Questa verifica PROVA che, a interruttori spenti, il codice di produzione gia' esistente e'
IDENTICO a quello della base (master). Non si fida dei commenti ne' del diff a occhio:

1. PYTHON - per ogni file di produzione gia' esistente toccato dal ramo, confronta l'AST della
   base con l'AST del ramo dopo aver tolto SOLO il tracciamento:
   - gli import dei moduli di tracciamento (``Betfair.monitor``, ``registratore_canale``);
   - gli ``if <interruttore>: ...`` senza ``else`` il cui test e' un interruttore
     (``_mon.ATTIVO``, ``_reg.ATTIVO``, ``_ro.attivo()``, anche in ``and``/``or`` fra loro);
   - le espressioni ``A if <interruttore> else B`` -> ``B`` (il ramo dello spento).
   La normalizzazione e' applicata IDENTICA a base e ramo. Se dopo restano differenze, il
   file ha un cambiamento che NON e' tracciamento: ROSSO.
   Unica eccezione dichiarata (elenco ``ECCEZIONI``): l'argomento di misura
   ``invio=req.ricevuto_ms`` in ``live_order_worker._TEMPI.nuovo``; a monitor spento vale 0 e
   ``tempi_ordine._ms_da(0)`` e' None, cioe' identico a prima (provato dal test K2 di
   ``agganci_mutazioni.py`` e qui sotto al punto 3).
2. FRONTEND - ogni riga aggiunta ai file gia' esistenti deve essere un import di
   ``misuraSchermo``, una riga guardata da ``misuraAccesa()``, la chiamata dell'hook
   ``useMisuraDipinto`` (che a misura spenta esce subito: test T2/T4/T5), una riga di etichette
   della pagina Salute, un commento, o la lettura di ``Date.now()`` usata solo sotto
   ``misuraAccesa()``. Nessuna riga tolta.
3. FUNZIONAMENTO - lancia i test "spento = identico, acceso = uguale esito" dei quattro pezzi
   (registratore ordini, misure, agganci, canale) e la prova ``_ms_da(0) is None``.

Uso (dalla radice del repo, sul ramo da firmare):
    python ARCHITETTURA_2026-10/mappa/verifica_solo_tracciamento.py [--base a3a58ad8] [--senza-test]
Uscita 0 = VERDE (solo tracciamento, funzionamento uguale); 1 = ROSSO con il motivo.
"""
from __future__ import annotations

import argparse
import ast
import copy
import subprocess
import sys
from typing import List, Optional, Tuple

BASE_DI_SERIE = "a3a58ad8"

# file nuovi o di solo tracciamento: non sono "codice di prima" (non esistono in base o sono il
# modulo di tracciamento stesso, eseguito solo dagli agganci guardati)
PREFISSI_TRACCIAMENTO = ("Betfair/monitor/", "ARCHITETTURA_2026-10/")
FILE_NUOVI_TRACCIAMENTO = {
    "Betfair/stream/registratore_canale.py", "Betfair/stream/mappa_flussi.py",
    "Betfair/stream/gz_tollerante.py", "frontend/src/lib/misuraSchermo.ts",
}

# nomi dei moduli di tracciamento negli import
MODULI_TRACCIAMENTO = ("monitor", "registratore_canale", "registratore_ordini", "sonde")

# alias degli interruttori (``_mon.ATTIVO``, ``_reg.ATTIVO``, ``_ro.attivo()``)
ALIAS_ATTIVO = {"_mon", "_reg"}
ALIAS_ATTIVO_CHIAMATA = {"_ro"}

# unica eccezione dichiarata: (file, nome della keyword, sorgente del valore)
ECCEZIONI = [("Betfair/stream/live_order_worker.py", "invio", "req.ricevuto_ms")]


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True,
                          encoding="utf-8").stdout


def _file_toccati(base: str) -> List[str]:
    out = _git("diff", "--name-only", base)
    return [r.strip() for r in out.splitlines() if r.strip()]


def _esiste_in_base(base: str, percorso: str) -> bool:
    return subprocess.run(["git", "cat-file", "-e", f"{base}:{percorso}"],
                          capture_output=True).returncode == 0


def _e_interruttore(nodo: ast.AST) -> bool:
    """True se il test e' un interruttore di tracciamento (o una combinazione che lo
    richiede: con l'interruttore spento il blocco non gira)."""
    if isinstance(nodo, ast.Attribute) and nodo.attr == "ATTIVO" \
            and isinstance(nodo.value, ast.Name) and nodo.value.id in ALIAS_ATTIVO:
        return True
    if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute) \
            and nodo.func.attr == "attivo" and isinstance(nodo.func.value, ast.Name) \
            and nodo.func.value.id in ALIAS_ATTIVO_CHIAMATA and not nodo.args:
        return True
    if isinstance(nodo, ast.BoolOp):
        if isinstance(nodo.op, ast.Or):
            # spento solo se TUTTI gli operandi sono interruttori
            return all(_e_interruttore(v) for v in nodo.values)
        # ``and``: il PRIMO e' un interruttore (corto circuito: niente altro gira), oppure
        # un operando e' un interruttore e quelli PRIMA di lui sono senza effetti
        # (confronti, nomi, attributi, costanti: nessuna chiamata)
        for i, v in enumerate(nodo.values):
            if _e_interruttore(v):
                return all(_senza_effetti(w) for w in nodo.values[:i])
        return False
    return False


def _senza_effetti(nodo: ast.AST) -> bool:
    """Espressione che non chiama niente (solo confronti, nomi, attributi, costanti)."""
    return not any(isinstance(n, (ast.Call, ast.Await, ast.Yield, ast.YieldFrom, ast.NamedExpr))
                   for n in ast.walk(nodo))


def _import_tracciamento(nodo: ast.AST) -> bool:
    if isinstance(nodo, ast.ImportFrom):
        mod = nodo.module or ""
        nomi = [a.name for a in nodo.names]
        return any(m in mod.split(".") for m in MODULI_TRACCIAMENTO) or \
            any(n in MODULI_TRACCIAMENTO for n in nomi)
    if isinstance(nodo, ast.Import):
        return all(any(m in a.name.split(".") for m in MODULI_TRACCIAMENTO) for a in nodo.names)
    return False


class _Normalizza(ast.NodeTransformer):
    def __init__(self, percorso: str) -> None:
        self.percorso = percorso
        self.tolti = 0

    def _filtra(self, corpo: List[ast.stmt]) -> List[ast.stmt]:
        nuovo = []
        for st in corpo:
            if _import_tracciamento(st):
                self.tolti += 1
                continue
            if isinstance(st, ast.If) and not st.orelse and _e_interruttore(st.test):
                self.tolti += 1
                continue
            nuovo.append(st)
        return nuovo or [ast.Pass()]

    def generic_visit(self, node: ast.AST) -> ast.AST:
        for campo in ("body", "orelse", "finalbody"):
            val = getattr(node, campo, None)
            if isinstance(val, list) and val and isinstance(val[0], ast.stmt):
                setattr(node, campo, self._filtra(val))
        return super().generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> ast.AST:
        if _e_interruttore(node.test):
            self.tolti += 1
            return self.visit(node.orelse)
        return self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> ast.AST:
        for f, nome, sorgente in ECCEZIONI:
            if f == self.percorso:
                prima = len(node.keywords)
                node.keywords = [k for k in node.keywords
                                 if not (k.arg == nome and ast.unparse(k.value) == sorgente)]
                self.tolti += prima - len(node.keywords)
        return self.generic_visit(node)


def _normalizzato(sorgente: str, percorso: str) -> Tuple[str, int]:
    albero = ast.parse(sorgente)
    n = _Normalizza(percorso)
    albero = n.visit(copy.deepcopy(albero))
    albero.body = n._filtra(albero.body)
    return ast.dump(albero, annotate_fields=False, include_attributes=False), n.tolti


def verifica_python(base: str, percorso: str) -> Optional[str]:
    prima = _git("show", f"{base}:{percorso}")
    dopo = open(percorso, encoding="utf-8").read()
    a, _ = _normalizzato(prima, percorso)
    b, tolti = _normalizzato(dopo, percorso)
    if a != b:
        return "il codice a interruttori spenti NON e' identico alla base (cambiamento che non e' tracciamento)"
    return None


AMMESSE_TS = ("import { useMisuraDipinto } from '@/lib/misuraSchermo';",
              "import { misuraAccesa, notaArrivoLadder } from '@/lib/misuraSchermo';",
              "import { misuraAccesa } from '@/lib/misuraSchermo';",
              "useMisuraDipinto(marketId, row);",
              "const emessoMs = Date.now();")


def verifica_ts(base: str, percorso: str) -> Optional[str]:
    diff = _git("diff", "-U0", base, "--", percorso)
    for riga in diff.splitlines():
        if riga.startswith(("+++", "---", "@@", "diff ", "index ")):
            continue
        if riga.startswith("-"):
            return "riga TOLTA: %r" % riga[1:].strip()[:120]
        if not riga.startswith("+"):
            continue
        r = riga[1:].strip()
        codice = r.split("//")[0].strip() if not r.startswith("{ prefisso:") else r
        if not codice or r.startswith("//"):
            continue
        if any(codice.startswith(a) for a in AMMESSE_TS):
            continue
        if "misuraAccesa()" in codice:
            continue
        if percorso.endswith("salute.ts") and codice.startswith("{ prefisso:"):
            continue  # etichette della pagina Salute (solo testo)
        return "riga aggiunta non riconosciuta come tracciamento: %r" % r[:120]
    return None


def verifica_funzionamento() -> Optional[str]:
    import os
    sys.path.insert(0, os.getcwd())  # lanciato dalla radice del repo
    from Betfair.stream import tempi_ordine
    if tempi_ordine._ms_da(0) is not None:
        return "tempi_ordine._ms_da(0) non e' None: ricevuto_ms=0 produrrebbe una misura"
    test = ["Betfair/monitor/tests", "Betfair/stream/tests/test_registratore_canale_2026_10_11.py",
            "Betfair/stream/tests/test_mappa_flussi_2026_10_11.py"]
    r = subprocess.run([sys.executable, "-m", "pytest", *test, "-q", "-p", "no:cacheprovider"],
                       capture_output=True, text=True)
    coda = (r.stdout or "").strip().splitlines()[-1:] or [""]
    print("   test di funzionamento:", coda[0])
    if r.returncode != 0:
        return "test di funzionamento ROSSI"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE_DI_SERIE)
    ap.add_argument("--senza-test", action="store_true")
    a = ap.parse_args()
    rossi = 0
    for p in _file_toccati(a.base):
        if p.startswith(PREFISSI_TRACCIAMENTO) or p in FILE_NUOVI_TRACCIAMENTO or "/tests/" in p \
                or p.endswith(".test.ts") or not _esiste_in_base(a.base, p):
            continue
        if p.endswith(".py"):
            esito = verifica_python(a.base, p)
        elif p.endswith((".ts", ".tsx")):
            esito = verifica_ts(a.base, p)
        else:
            esito = "file non previsto dalla verifica"
        print("%-6s %s%s" % ("ROSSO" if esito else "VERDE", p, (" - " + esito) if esito else ""))
        rossi += bool(esito)
    if not a.senza_test:
        esito = verifica_funzionamento()
        print("%-6s funzionamento (spento = identico, acceso = stesso esito)%s"
              % ("ROSSO" if esito else "VERDE", (" - " + esito) if esito else ""))
        rossi += bool(esito)
    print("ESITO:", "VERDE - solo tracciamento" if not rossi else "ROSSO (%d)" % rossi)
    return 0 if not rossi else 1


if __name__ == "__main__":
    sys.exit(main())
