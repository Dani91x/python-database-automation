"""FALSIFICAZIONE dei test del P&L REALE DEL CONTO (30/09).

Ogni mutazione reintroduce UN difetto nel codice; i test indicati DEVONO
diventare rossi. Il file mutato si ripristina SEMPRE dalla copia in memoria
(try/finally) e alla fine si verifica che ogni file sia identico byte per byte
alla copia di partenza (anche i file nuovi, non tracciati da git).

Uso (dalla radice del worktree, ambiente NEUTRO):
    bash _pnl_scratch/neutro.sh .venv/Scripts/python.exe AUDIT_2026-09-30/falsifica_pnl_reale_conto.py
Mai interromperlo a meta'. ASCII-only.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PY = os.path.join(RADICE, ".venv", "Scripts", "python.exe")
T_PY = "Betfair/mike/tests/test_mike_pnl_reale_del_conto_2026_09_30.py"
NPX = "npx.cmd" if os.name == "nt" else "npx"

SVC = "Betfair/mike/service.py"
RC = "Betfair/mike/regolato_conto.py"
RW = "Betfair/stream/reconcile_worker.py"
FP = "frontend/src/lib/fontePnl.ts"
MK = "frontend/src/lib/mike.ts"
CR = "frontend/src/components/controlroom/useControlRoom.ts"
CARD = "frontend/src/components/mike/MikeMatchCard.tsx"

# (nome, file, testo vero, testo mutato, test (python: -k; vitest: file), attesa)
MUTAZIONI = [
    ("M1 vince il calcolo interno, non Betfair", SVC,
     '            st, pnl = b["esito"], b["netto"]\n',
     '            pass  # MUTAZIONE\n',
     ("py", "utente_entra_nel_conto")),
    ("M2 P&L della partita = solo Mike (interno)", SVC,
     '            ctx.settled_pnl = float(conto["netto_conto"])\n',
     '            pass  # MUTAZIONE\n',
     ("py", "utente_entra_nel_conto")),
    ("M3 l'ordine dell'utente contato come di Mike", RC,
     '            b["chi"] = "utente"\n',
     '            b["chi"] = "mike"  # MUTAZIONE\n',
     ("py", "utente_entra_nel_conto")),
    ("M4 regolamento cieco: non si aspettano le scommesse di Mike", RC,
     '    if mancano:\n        return {"pronto": False',
     '    if False:  # MUTAZIONE\n        return {"pronto": False',
     ("py", "non_ancora_disponibile or non_pronto_senza")),
    # M5: le DUE guardie del paper (modalita' della partita e delle righe)
    ("M5 il conto letto anche in paper", SVC,
     ['    if str(mode) != "live":\n        return None\n    params = params or {}',
      '    if not any(str(r.get("mode") or "") == "live" and RC._abbinato(r) > 0 for r in righe_bot):'],
     ['    if False:  # MUTAZIONE\n        return None\n    params = params or {}',
      '    if not any(RC._abbinato(r) > 0 for r in righe_bot):  # MUTAZIONE'],
     ("py", "paper_regola")),
    ("M6 la lettura VOIDED sempre (chiamate REST in piu')", SVC,
     '        if esito.get("mancano") and (ordini or tentativi >= 3):\n',
     '        if esito.get("mancano"):  # MUTAZIONE\n',
     ("py", "tetto")),
    ("M6b la lettura VOIDED anche senza scommesse mancanti", SVC,
     '        if esito.get("mancano") and (ordini or tentativi >= 3):\n',
     '        if True:  # MUTAZIONE\n',
     ("py", "due_chiamate_rest")),
    ("M7 nessun tetto ai tentativi", SVC,
     '        if tentativi >= _CONTO_TENTATIVI_MAX:\n',
     '        if False:  # MUTAZIONE\n',
     ("py", "tetto")),
    ("M8 una riga utente ricostruita come gamba di Mike", SVC,
     '    if RC.e_riga_utente(r):\n        return None          # 30/09',
     '    if False:  # MUTAZIONE\n        return None          # 30/09',
     ("py", "non_diventa_mai")),
    ("M9 il runner attribuisce a Mike l'ordine dell'utente", RW,
     '                if tabella == "mike_trades" and str(r.get("role") or "") == "utente":\n',
     '                if False:  # MUTAZIONE\n',
     ("py", "runner_non_attribuisce")),
    ("M10 la riga utente non viene scritta", SVC,
     '                _insert_trade_row(db, nuova, event_id)\n',
     '                pass  # MUTAZIONE\n',
     ("py", "utente_entra_nel_conto")),
    ("M11 la riga utente non dice quale posizione chiude", RC,
     '        riga["closes_trade_id"] = int(apertura["id"])\n',
     '        pass  # MUTAZIONE\n',
     ("py", "utente_entra_nel_conto")),
    ("M12 il segnale scrive righe utente anche per ordini di Mike", SVC,
     '    if not RC.ordine_non_di_mike(ordine, rows, refs, strategy_ref):\n        return False\n',
     '    if False:  # MUTAZIONE\n        return False\n',
     ("py", "non_scrive_righe_utente")),
    ("M13 il segnale duplica la riga utente", SVC,
     '            if not campi:\n                return False\n',
     '            if False:  # MUTAZIONE\n                return False\n',
     ("py", "senza_doppioni")),
    ("F1 ogni riga live dichiarata 'conto' anche senza Betfair", FP,
     "    if (f === 'betfair' || (r.pnl_betfair != null && r.pnl_betfair !== '')) return 'conto';\n",
     "    if (true) return 'conto'; // MUTAZIONE\n",
     ("vt", "src/lib/fontePnl.test.ts")),
    ("F2 il diario mostra il calcolo del bot invece del conto", MK,
     "            if (p.pnl_fonte === 'betfair') {\n",
     "            if (false) { // MUTAZIONE\n",
     ("vt", "src/lib/fontePnl.test.ts")),
    ("F3 la riga utente contata anche sotto Mike nella barra", CR,
     "(mike?.trades ?? []).filter((t) => !isRigaUtente(t as unknown as RigaPnl))",
     "(mike?.trades ?? []).filter((t) => t != null) /* MUTAZIONE */",
     ("vt", "src/components/controlroom/useControlRoom.test.tsx")),
    ("F4 la scheda non dice la fonte del regolato", CARD,
     "        return { breve: FONTE_PNL_BREVE[f], scomposizione,\n",
     "        return { breve: '', scomposizione, // MUTAZIONE\n",
     ("vt", "src/components/mike/MikeMatchCard.fontePnl.test.tsx")),
]


def _leggi(rel: str) -> bytes:
    with open(os.path.join(RADICE, rel), "rb") as f:
        return f.read()


def _scrivi(rel: str, dati: bytes) -> None:
    with open(os.path.join(RADICE, rel), "wb") as f:
        f.write(dati)


def _esegui(tipo: str, arg: str) -> int:
    if tipo == "py":
        cmd = [PY, "-m", "pytest", T_PY, "-q", "-p", "no:cacheprovider", "-k", arg]
        return subprocess.run(cmd, cwd=RADICE, capture_output=True).returncode
    cmd = [NPX, "vitest", "run", arg]
    return subprocess.run(cmd, cwd=os.path.join(RADICE, "frontend"), capture_output=True,
                          shell=False).returncode


def _muta(testo: str, veri: list, mutati: list) -> str | None:
    """Applica le sostituzioni (ognuna UNA volta); i file con fine riga CRLF
    si mutano con la stessa riga in CRLF. None = testo non trovato."""
    for v, mu in zip(veri, mutati):
        if testo.count(v) != 1:
            v, mu = v.replace("\n", "\r\n"), mu.replace("\n", "\r\n")
        if testo.count(v) != 1:
            return None
        testo = testo.replace(v, mu)
    return testo


def main() -> int:
    copie = {rel: _leggi(rel) for rel in {m[1] for m in MUTAZIONI}}
    impronte = {rel: hashlib.sha256(d).hexdigest() for rel, d in copie.items()}
    esiti = []
    for nome, rel, vero, mutato, (tipo, arg) in MUTAZIONI:
        testo = copie[rel].decode("utf-8")
        veri = vero if isinstance(vero, list) else [vero]
        mutati = mutato if isinstance(mutato, list) else [mutato]
        nuovo = _muta(testo, veri, mutati)
        if nuovo is None:
            esiti.append((nome, "NON APPLICABILE (testo non trovato)"))
            continue
        try:
            _scrivi(rel, nuovo.encode("utf-8"))
            rc = _esegui(tipo, arg)
        finally:
            _scrivi(rel, copie[rel])
        esiti.append((nome, "ROSSO (atteso)" if rc != 0 else "VERDE: MUTAZIONE NON CATTURATA"))
    for rel, h in impronte.items():
        if hashlib.sha256(_leggi(rel)).hexdigest() != h:
            print(f"!! {rel} NON ripristinato")
            return 2
        if b"MUTAZIONE" in _leggi(rel):
            print(f"!! {rel} contiene ancora MUTAZIONE")
            return 2
    for nome, e in esiti:
        print(f"{e:32s} {nome}")
    print("file ripristinati: " + ", ".join(sorted(impronte)))
    return 0 if all(e.startswith("ROSSO") for _n, e in esiti) else 1


if __name__ == "__main__":
    sys.exit(main())
