"""D3 + D7 (25/09) - FALSIFICAZIONE dei test nuovi (dry-run scalper, esecuzione a
mercato entro la banda della strategia, Mike al ms).

Per ogni mutazione: sostituzione esatta (deve esistere UNA volta), test mirato
(deve diventare ROSSO), ripristino dal contenuto originale in memoria (mai
`git checkout`: memoria del 23/09) e verifica md5. Prima, un CONTROLLO: senza
mutazioni ogni comando e' VERDE.
Uso (dalla radice del worktree):
    python AUDIT_2026-09-25/mutazioni_dryrun_esecuzione.py
Il Python: `.venv` del worktree se c'e', altrimenti quello del checkout
principale (tre cartelle sopra). ASCII-only.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FE = os.path.join(RADICE, "frontend")
_PY_LOCALE = os.path.join(RADICE, ".venv", "Scripts", "python.exe")
_PY_PRINCIPALE = os.path.normpath(os.path.join(RADICE, "..", "..", "..", ".venv", "Scripts",
                                               "python.exe"))
PY = _PY_LOCALE if os.path.exists(_PY_LOCALE) else _PY_PRINCIPALE
ENV = dict(os.environ, SUPABASE_URL="http://127.0.0.1:9", SUPABASE_SERVICE_ROLE_KEY="x",
           SUPABASE_KEY="x")

VITEST = ["npx.cmd" if os.name == "nt" else "npx", "vitest", "run"]


def pytest(*files: str) -> list:
    return [PY, "-m", "pytest", *files, "-q", "-p", "no:cacheprovider"]


T_SCALPER = pytest("Betfair/stream/tests/test_scalper_auto_mode_2026_09_25.py")
T_D7 = pytest("Betfair/safe_strategy/tests/test_esecuzione_a_mercato_d7_2026_09_25.py")
T_BANCO = pytest("Betfair/stream/tests/test_proposte_modello_2026_09_23.py")
T_SCHEDA = pytest("Betfair/safe_strategy/tests/test_scheda_al_ms_2026_09_24.py")

MUTAZIONI = [
    # (nome, file, vecchio, nuovo, comando, cartella)
    # ---------------------------------------------------------------- D3 scalper
    ("PY1 in live l'auto-mode nasce con soldi veri", "Betfair/stream/scalper/auto_mode.py",
     "DRY_RUN_ALLA_NASCITA = True", "DRY_RUN_ALLA_NASCITA = False", T_SCALPER, RADICE),
    ("PY2 supervisore torna a dry_run = modalita'", "Betfair/stream/scalper/scalper_service.py",
     '"dry_run": AM.dry_run_alla_nascita(modalita),', '"dry_run": modalita != "live",',
     T_SCALPER, RADICE),
    ("PY3 in live il dry-run blocca l'armamento", "Betfair/stream/scalper/auto_mode.py",
     "    if modalita == \"live\":\n        return None\n", "", T_SCALPER, RADICE),
    ("PY4 attivita' senza dry_run", "Betfair/stream/scalper/scalper_service.py",
     '                            "dry_run": campi["dry_run"],\n', "", T_SCALPER, RADICE),
    # ---------------------------------------------------------------- D7 Safe
    ("PY5 l'ordine torna al prezzo visto", "Betfair/safe_strategy/bot_service.py",
     "        prezzo_ordine = prezzo_attuale\n",
     "        prezzo_ordine = pv if pv is not None else prezzo_attuale\n", T_D7, RADICE),
    ("PY6 nessun controllo di banda", "Betfair/safe_strategy/bot_service.py",
     "        if prezzo_attuale is None or not PO.in_banda(",
     "        if prezzo_attuale is None or False and not PO.in_banda(", T_D7, RADICE),
    ("PY7 la banda ignora l'edge minimo", "Betfair/safe_strategy/proposte_opportunita.py",
     'CODICI_DI_PREZZO = ("quota_sotto_minimo", "quota_sopra_massimo", "edge_sotto_minimo",',
     'CODICI_DI_PREZZO = ("quota_sotto_minimo", "quota_sopra_massimo",', T_D7, RADICE),
    ("PY8 la banda conta anche abbinabile e probabilita'",
     "Betfair/safe_strategy/proposte_opportunita.py",
     "            if str((m or {}).get(\"codice\")) in CODICI_DI_PREZZO]",
     "            if True]", T_D7, RADICE),
    ("PY9 messaggio senza le parole dell'ordine", "Betfair/safe_strategy/proposte_opportunita.py",
     'f"{testo_banda(banda)} della strategia")', 'f"{testo_banda(banda)}")', T_D7, RADICE),
    ("PY10 esecuzione non scritta sulla riga", "Betfair/safe_strategy/bot_service.py",
     '            meta["esecuzione_al_clic"] = esecuzione\n', "            pass\n", T_D7, RADICE),
    ("PY11 banda mai usata (sempre la regola del 18/09)", "Betfair/safe_strategy/bot_service.py",
     "    if opp_key and banda is not None:", "    if opp_key and banda is not None and False:",
     T_SCHEDA, RADICE),
    ("PY12 senza banda si inventa il mercato", "Betfair/safe_strategy/proposte_opportunita.py",
     "    if not _banda_valutabile(side, p_model, criteri):\n        return None\n    lato",
     "    if not _banda_valutabile(side, p_model, criteri):\n"
     "        return {\"min\": 1.01, \"max\": 1000.0, \"vuota\": False}\n    lato", T_D7, RADICE),
    ("PY13 senza prezzo sul mercato si piazza al visto", "Betfair/safe_strategy/bot_service.py",
     "        prezzo_attuale = PO.prezzo_visto_valido((prices or {}).get(side))\n",
     "        prezzo_attuale = PO.prezzo_visto_valido((prices or {}).get(side)) or pv\n",
     T_D7, RADICE),
    # ---------------------------------------------------------------- PM3 del banco (D7)
    ("PM3a il banco accetta un ordine fuori banda", "Betfair/stream/backtest/proposte_modello.py",
     "        if nate and vivo is not None and not dentro:",
     "        if False and nate and vivo is not None and not dentro:", T_BANCO, RADICE),
    ("PM3b PM3 vecchio anche con la banda (spurio)", "Betfair/stream/backtest/proposte_modello.py",
     "            if banda is not None:\n                _sollecita(sollecitati, \"PM3\")\n                self._pm3_banda(",
     "            if False:\n                _sollecita(sollecitati, \"PM3\")\n                self._pm3_banda(",
     T_BANCO, RADICE),
    ("PM3c rifiuto fuori banda in banda accettato", "Betfair/stream/backtest/proposte_modello.py",
     "        if motivo == \"fuori_banda_strategia\" and dentro:",
     "        if False and motivo == \"fuori_banda_strategia\" and dentro:", T_BANCO, RADICE),
    ("PM3d chiesto diverso dal mercato accettato", "Betfair/stream/backtest/proposte_modello.py",
     "            if chiesto is None or abs(chiesto - attuale) > 1e-6:",
     "            if chiesto is None:", T_BANCO, RADICE),
    ("PM3e esecuzione a mercato non pretesa", "Betfair/stream/backtest/proposte_modello.py",
     "            if str(ea.get(\"regola\") or \"\") != PO.ESECUZIONE_A_MERCATO or attuale is None:",
     "            if False:", T_BANCO, RADICE),
    # ---------------------------------------------------------------- TS
    ("TS1 porta TS: banda senza EV", "frontend/src/lib/valutaProposta.ts",
     "'edge_sotto_minimo_servizio', 'ev_non_positivo', 'responsabilita_oltre_tetto',",
     "'edge_sotto_minimo_servizio', 'responsabilita_oltre_tetto',",
     VITEST + ["src/lib/valutaProposta.banda.test.ts"], FE),
    ("TS2 porta TS: scala da 1.02", "frontend/src/lib/valutaProposta.ts",
     "    let p = 1.01;\n", "    let p = 1.02;\n",
     VITEST + ["src/lib/valutaProposta.banda.test.ts"], FE),
    ("TS3 scheda: fuori banda non detto", "frontend/src/components/controlroom/SchedaPropostaOpportunita.tsx",
     "if (banda != null && vivo != null && vivoInBanda === false) {",
     "if (banda != null && vivo != null && vivoInBanda === null) {",
     VITEST + ["src/components/controlroom/SchedaPropostaOpportunita.banda.test.tsx"], FE),
    ("TS4 scheda: banda congelata (p_model ignorata)",
     "frontend/src/components/controlroom/SchedaPropostaOpportunita.tsx",
     "    const pModel = p.p_model;\n", "    const pModel = 0.99;\n",
     VITEST + ["src/components/controlroom/SchedaPropostaOpportunita.banda.test.tsx"], FE),
    ("TS5 Mike: ctx.selections ignorato", "frontend/src/components/controlroom/PropostaUscitaMike.tsx",
     "    const grezzo = sels[`${o.mercato}|${o.selezione}`];",
     "    const grezzo = undefined as unknown;",
     VITEST + ["src/components/controlroom/PropostaUscitaMike.test.tsx"], FE),
    ("TS6 Mike: al clic il prezzo del feed, non quello al ms",
     "frontend/src/components/controlroom/PropostaUscitaMike.tsx",
     "const visto = o ? prezzoDelLato(alMs0, o.lato === 'lay' ? 'lay' : 'back') : null;",
     "const visto = o ? ((ev.live?.books ?? {})[`${o.mercato}|${o.selezione}`]?.best_lay ?? null) : null;",
     VITEST + ["src/components/controlroom/PropostaUscitaMike.test.tsx"], FE),
    ("TS7 Mike: ordine 1 senza sottoscrizione", "frontend/src/components/controlroom/PropostaUscitaMike.tsx",
     "        sorgente, sport: 'calcio', marketId, selectionId, lato,\n        ripiego: ripiegoDaBook(bk, istanteFeedMs),",
     "        sorgente: null, sport: 'calcio', marketId, selectionId, lato,\n        ripiego: ripiegoDaBook(bk, istanteFeedMs),",
     VITEST + ["src/components/controlroom/PropostaUscitaMike.test.tsx"], FE),
    ("TS8 scalper: frase LIVE di ieri", "frontend/src/lib/scalperControlRoom.ts",
     "        parti.push('LIVE: le partite del feed nascono in dry-run, nessun ordine reale finché '\n"
     "            + 'non lo togli per partita (scheda scalper della partita)');",
     "        parti.push('LIVE: le partite del feed nascono con soldi veri');",
     VITEST + ["src/lib/scalperAuto.test.ts"], FE),
]


def md5(p: str) -> str:
    with open(p, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def _esegui(cmd: list, cwd: str) -> int:
    r = subprocess.run(cmd, cwd=cwd, env=ENV, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=900, shell=False)
    return r.returncode


def controllo() -> bool:
    visti = set()
    tutto_verde = True
    for _n, _rel, _v, _nu, cmd, cwd in MUTAZIONI:
        k = (tuple(cmd), cwd)
        if k in visti:
            continue
        visti.add(k)
        rc = _esegui(cmd, cwd)
        print("CONTROLLO %-75s %s" % (" ".join(cmd[-4:]), "VERDE" if rc == 0 else "ROSSO"),
              flush=True)
        tutto_verde = tutto_verde and rc == 0
    return tutto_verde


def main() -> int:
    if not controllo():
        print("CONTROLLO FALLITO: i test non sono verdi senza mutazioni")
        return 2
    esiti = []
    for nome, rel, vecchio, nuovo, cmd, cwd in MUTAZIONI:
        p = os.path.join(RADICE, rel)
        with open(p, "rb") as f:
            orig = f.read()
        h0 = md5(p)
        testo = orig.decode("utf-8")
        if "\r\n" in testo and "\n" in vecchio and "\r\n" not in vecchio:
            # file con fine riga Windows: la mutazione si scrive con \r\n
            vecchio = vecchio.replace("\n", "\r\n")
            nuovo = nuovo.replace("\n", "\r\n")
        n = testo.count(vecchio)
        if n != 1:
            esiti.append((nome, "NON APPLICABILE (occorrenze %d)" % n))
            print("%-55s %s" % esiti[-1], flush=True)
            continue
        with open(p, "wb") as f:
            f.write(testo.replace(vecchio, nuovo).encode("utf-8"))
        try:
            rosso = _esegui(cmd, cwd) != 0
        finally:
            with open(p, "wb") as f:
                f.write(orig)
        ok_md5 = md5(p) == h0
        esiti.append((nome, ("ROSSO" if rosso else "VERDE (test NON falsificante!)")
                      + (" md5 ripristinato" if ok_md5 else " md5 DIVERSO")))
        print("%-55s %s" % esiti[-1], flush=True)
    print("---")
    for nome, e in esiti:
        print("%-55s %s" % (nome, e))
    return 0 if all(e.startswith("ROSSO") and "ripristinato" in e for _, e in esiti) else 1


if __name__ == "__main__":
    sys.exit(main())
