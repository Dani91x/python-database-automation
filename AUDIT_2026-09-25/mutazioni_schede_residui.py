"""25/09 (residui B17) - FALSIFICAZIONE dei test nuovi: cash out globale per
ordine, "Chiudi" di riga e combo al ms, Mike per chiave.

Per ogni mutazione: sostituzione esatta (deve esistere UNA volta), test mirato
(deve diventare ROSSO), ripristino dal contenuto originale in memoria (mai
`git checkout`) e verifica md5. Uso (dalla radice del worktree):
    python AUDIT_2026-09-25/mutazioni_schede_residui.py
ASCII-only.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FE = os.path.join(RADICE, "frontend")
PY = os.path.join(RADICE, ".venv", "Scripts", "python.exe")
ENV = dict(os.environ, SUPABASE_URL="http://127.0.0.1:9", SUPABASE_SERVICE_ROLE_KEY="x",
           SUPABASE_KEY="x")

VITEST = ["npx.cmd" if os.name == "nt" else "npx", "vitest", "run"]
T_SCHEDE = VITEST + ["src/components/controlroom/ResiduiB17.schede.test.tsx"]
T_PURO = VITEST + ["src/lib/chiusuraAlMs.test.ts"]
T_HOOK = VITEST + ["src/components/controlroom/useControlRoom.test.tsx", "-t", "residui B17"]
T_SAFE = [PY, "-m", "pytest", "Betfair/safe_strategy/tests/test_cashout_event_ids_b17_2026_09_25.py",
          "-q", "-p", "no:cacheprovider"]
T_MIKE = [PY, "-m", "pytest", "Betfair/mike/tests/test_mike_chiave_approvazione_b17_2026_09_25.py",
          "-q", "-p", "no:cacheprovider"]

EA = "frontend/src/lib/esitoAbbinamento.ts"
MUTAZIONI = [
    # (nome, file, vecchio, nuovo, comando, cartella)
    ("TS1 cash out: correlazione al posto degli id", EA,
     "if (clic.tipo === 'apertura' || clic.soloIdDichiarati) return { ids: [], modo: 'nessuno' };",
     "if (clic.tipo === 'apertura') return { ids: [], modo: 'nessuno' };", T_SCHEDE, FE),
    ("TS2 Mike: chiave ignorata", EA,
     "if (conChiave.length) return { ids: conChiave.map((c) => c.id), modo: 'chiave' };",
     "if (false) return { ids: conChiave.map((c) => c.id), modo: 'chiave' };", T_SCHEDE, FE),
    ("TS3 Mike: chiave altrui nel ripiego", EA,
     "&& c.approvazioneId == null", "&& true", T_SCHEDE, FE),
    ("TS4 cash out: nessun ordine = attesa infinita", EA,
     "if (f === 'eseguita' && clic.soloIdDichiarati && richiesta && richiesta.tradeIds.length === 0) {",
     "if (false) {", T_SCHEDE, FE),
    ("TS5 cash out: posizioni non chiuse taciute", "frontend/src/components/controlroom/EsitoAbbinamentoStriscia.tsx",
     "for (const n of seguito.richiesta?.nonChiuse ?? []) {", "for (const n of [] as never[]) {",
     T_SCHEDE, FE),
    ("TS6 cash out: non_chiuse non lette dalla coda", "frontend/src/components/controlroom/useSeguiOrdini.ts",
     "nonChiuse: nonChiuseDaRisultato(r.result),", "nonChiuse: [],", T_HOOK, FE),
    ("TS7 cash out: clic senza soloIdDichiarati", "frontend/src/components/controlroom/useControlRoom.ts",
     "clicMs, ruoli: null, soloIdDichiarati: true,", "clicMs, ruoli: null,", T_HOOK, FE),
    ("TS8 Chiudi: P&L dallo scanner, non dal ms", "frontend/src/components/controlroom/useChiusuraAlMs.ts",
     "const c = chiusuraAlPrezzo(d.win, d.lose, chiusura.lato, p);",
     "const c = chiusuraAlPrezzo(d.win, d.lose, chiusura.lato, ripiegoScanner(d) ?? p);", T_SCHEDE, FE),
    ("TS9 Chiudi: ripiego non dichiarato", "frontend/src/lib/chiusuraAlMs.ts",
     "if (p.fonte === 'scanner') return", "if (p.fonte === 'scanner' && false) return", T_PURO, FE),
    ("TS10 Chiudi: prezzo visto non passato al clic", "frontend/src/components/controlroom/DettaglioRigaView.tsx",
     "prezzoAlClic={ch ? () => prezzoAlClic(ch, Date.now()) : undefined}", "prezzoAlClic={undefined}",
     T_SCHEDE, FE),
    ("TS11 Chiudi: prezzo visto nel payload", "frontend/src/components/controlroom/chiudiRiga.ts",
     "trade_id: r.id, fraction: 1, bot: 'safe',", "trade_id: r.id, fraction: 1, bot: 'safe', pv: r.prezzoVisto,",
     T_SCHEDE, FE),
    ("TS12 combo: gamba contro non conta", "frontend/src/lib/chiusuraAlMs.ts",
     "if (c) perdita += s * Math.abs(p1 - p0);", "if (false) perdita += s * Math.abs(p1 - p0);", T_PURO, FE),
    ("TS13 combo: niente ladder al ms", "frontend/src/components/controlroom/SchedaPropostaOpportunita.tsx",
     "sorgente: isCombo ? sorgenteLadder : null,", "sorgente: null,", T_SCHEDE, FE),
    ("TS14 combo: al clic i prezzi dello scanner", "frontend/src/components/controlroom/SchedaPropostaOpportunita.tsx",
     "const v = viviGambe[i];", "const v = prezziViviGambe?.[i];", T_SCHEDE, FE),
    ("PY1 Safe: id degli ordini non dichiarati", "Betfair/safe_strategy/bot_service.py",
     "closing_ids.append(cid)", "pass", T_SAFE, RADICE),
    ("PY2 Safe: closing_trade_ids assente dal risultato", "Betfair/safe_strategy/bot_service.py",
     '"closing_trade_ids": closing_ids, "gambe": gambe,', '"gambe": gambe,', T_SAFE, RADICE),
    ("PY3 Mike: chiave anche sulle coperture", "Betfair/mike/service.py",
     'if approvazione_id is None or getattr(leg, "role", None) not in E.USCITE_DISCREZIONALI:',
     "if approvazione_id is None:", T_MIKE, RADICE),
    ("PY4 Mike: id della richiesta non salvato", "Betfair/mike/service.py",
     '**({"request_id": rid_ok} if rid_ok is not None else {}),', "", T_MIKE, RADICE),
    ("PY5 Mike: chiave senza confronto", "Betfair/mike/service.py",
     'if str(tele.get("chiave")) != str(prima.get("chiave") or ""):', "if False:", T_MIKE, RADICE),
    ("PY6 Mike: chiave non scritta sulla riga", "Betfair/mike/service.py",
     'meta["approvazione_id"] = int(approvazione_id)', "pass", T_MIKE, RADICE),
]


def md5(p: str) -> str:
    with open(p, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def esegui(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, env=ENV, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=900, shell=False)


def controllo() -> bool:
    """Senza mutazioni ogni comando e' VERDE (altrimenti un rosso non prova niente)."""
    visti = set()
    tutto_verde = True
    for _n, _rel, _v, _nu, cmd, cwd in MUTAZIONI:
        k = (tuple(cmd), cwd)
        if k in visti:
            continue
        visti.add(k)
        r = esegui(cmd, cwd)
        print("CONTROLLO %-70s %s" % (" ".join(cmd[-3:]), "VERDE" if r.returncode == 0 else "ROSSO"))
        tutto_verde = tutto_verde and r.returncode == 0
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
        n = testo.count(vecchio)
        if n != 1:
            esiti.append((nome, "NON APPLICABILE (occorrenze %d)" % n))
            continue
        with open(p, "wb") as f:
            f.write(testo.replace(vecchio, nuovo).encode("utf-8"))
        try:
            rosso = esegui(cmd, cwd).returncode != 0
        finally:
            with open(p, "wb") as f:
                f.write(orig)
        ok_md5 = md5(p) == h0
        esiti.append((nome, ("ROSSO" if rosso else "VERDE (test NON falsificante!)")
                      + (" md5 ripristinato" if ok_md5 else " md5 DIVERSO")))
        print("%-48s %s" % esiti[-1], flush=True)
    print("---")
    for nome, e in esiti:
        print("%-48s %s" % (nome, e))
    return 0 if all(e.startswith("ROSSO") and "ripristinato" in e for _, e in esiti) else 1


if __name__ == "__main__":
    sys.exit(main())
