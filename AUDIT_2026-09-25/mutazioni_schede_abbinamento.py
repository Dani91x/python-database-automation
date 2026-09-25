"""B17 (25/09) - FALSIFICAZIONE dei test nuovi delle schede (abbinamento e prezzo).

Per ogni mutazione: copia del file, sostituzione esatta (deve esistere UNA
volta), test mirato (deve diventare ROSSO), ripristino dal contenuto originale
in memoria (mai `git checkout`: memoria del 23/09) e verifica md5.
Uso (dalla radice del worktree):
    python AUDIT_2026-09-25/mutazioni_schede_abbinamento.py
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

MUTAZIONI = [
    # (nome, file, vecchio, nuovo, comando, cartella)
    ("TS1 a favore invertito per la punta", "frontend/src/lib/esitoAbbinamento.ts",
     "lato === 'back' ? tick > 0 : tick < 0", "lato === 'back' ? tick < 0 : tick > 0",
     VITEST + ["src/lib/esitoAbbinamento.test.ts"], FE),
    ("TS2 FOK ucciso letto come rifiuto", "frontend/src/lib/esitoAbbinamento.ts",
     "if (nota && STATO_FOK_UCCISO.test(nota) && !testo(meta.error_code)) {",
     "if (false && nota && STATO_FOK_UCCISO.test(nota)) {",
     VITEST + ["src/lib/esitoAbbinamento.test.ts"], FE),
    ("TS3 righe note al clic contate come ordine", "frontend/src/lib/esitoAbbinamento.ts",
     "const noti = new Set(clic.idsNotiAlClic);", "const noti = new Set<number>();",
     VITEST + ["src/lib/esitoAbbinamento.test.ts"], FE),
    ("TS4 apertura indovinata senza id del servizio", "frontend/src/lib/esitoAbbinamento.ts",
     "if (clic.tipo === 'apertura') return [];", "if (clic.tipo === 'apertura') return delBot.map((c) => c.id);",
     VITEST + ["src/lib/esitoAbbinamento.test.ts"], FE),
    ("TS5 prezzo chiesto spacciato per medio", "frontend/src/lib/esitoAbbinamento.ts",
     "prezzoMedio: s.prezzoMedio.valore, prezzoChiesto",
     "prezzoMedio: s.prezzoMedio.valore ?? num(r.price), prezzoChiesto",
     VITEST + ["src/lib/esitoAbbinamento.test.ts"], FE),
    ("TS6 tennis: nomi dello specchio ignorati", "frontend/src/lib/esitoAbbinamento.ts",
     "avg_price_matched: tennis ? num(r.average_price_matched) : num(r.avg_price_matched),",
     "avg_price_matched: num(r.avg_price_matched),",
     VITEST + ["src/lib/esitoAbbinamento.test.ts"], FE),
    ("TS7 rilettura anche col canale fresco", "frontend/src/components/controlroom/useSeguiOrdini.ts",
     "if (!dalCanale && ora - e.clic.clicMs < RILETTURE_MAX_MS)",
     "if (ora - e.clic.clicMs < RILETTURE_MAX_MS)",
     VITEST + ["src/components/controlroom/EsitoAbbinamento.schede.test.tsx"], FE),
    ("TS8 coda chiusa riletta all'infinito", "frontend/src/components/controlroom/useSeguiOrdini.ts",
     "if (e.clic.requestId === null || chiusa) continue;", "if (e.clic.requestId === null) continue;",
     VITEST + ["src/components/controlroom/EsitoAbbinamento.schede.test.tsx"], FE),
    ("TS9 doppia riga d'esito nella colonna", "frontend/src/components/controlroom/OpportunitaColonna.tsx",
     ".filter((e) => !(vm.esitiOrdini ?? []).some((s) => s.clic.chiave === `safe:apertura:${e.id}`))",
     ".filter(() => true)",
     VITEST + ["src/components/controlroom/EsitoAbbinamento.schede.test.tsx"], FE),
    ("TS10 Omega approva senza prezzo visto", "frontend/src/components/controlroom/SchedaChiusuraOmega.tsx",
     "onClick={() => (live ? setArmato(true) : void azione(approvaConPrezzo))}",
     "onClick={() => (live ? setArmato(true) : void azione(onApprova))}",
     VITEST + ["src/components/controlroom/SchedaChiusuraOmega.test.tsx"], FE),
    ("TS11 segnale = price riscritto", "frontend/src/lib/schedaAlMs.ts",
     "return prezzoValido(p?.price_at_decision) ?? prezzoValido(p?.price);",
     "return prezzoValido(p?.price) ?? prezzoValido(p?.price_at_decision);",
     VITEST + ["src/components/controlroom/SchedaPropostaOpportunita.alms.test.tsx"], FE),
    ("TS12 Omega: ripiego anche su un rifiuto vero", "frontend/src/components/controlroom/useControlRoom.ts",
     """                if (!/PGRST202|schema cache|does not exist|not find the function/i
                    .test(e instanceof Error ? e.message : String(e))) throw e;
                await approvaPropostaOmega(id);""",
     """                await approvaPropostaOmega(id);""",
     VITEST + ["src/components/controlroom/useControlRoom.test.tsx", "-t", "B17"], FE),
    ("TS13 Mike: segnale non mandato", "frontend/src/components/controlroom/PropostaUscitaMike.tsx",
     "prezzo_segnale: o?.prezzo ?? null,", "prezzo_segnale: null,",
     VITEST + ["src/components/controlroom/EsitoAbbinamento.schede.test.tsx"], FE),
    ("PY1 segnale non scritto sulla riga", "Betfair/safe_strategy/bot_service.py",
     'meta["prezzo_segnale"] = segnale', 'pass',
     [PY, "-m", "pytest", "Betfair/safe_strategy/tests/test_prezzo_segnale_b17_2026_09_25.py", "-q",
      "-p", "no:cacheprovider"], RADICE),
    ("PY2 segnale sporco accettato nel contesto", "Betfair/safe_strategy/proposte_opportunita.py",
     "if segnale is not None and segnale > 1.0:", "if segnale is not None:",
     [PY, "-m", "pytest", "Betfair/safe_strategy/tests/test_prezzo_segnale_b17_2026_09_25.py", "-q",
      "-p", "no:cacheprovider"], RADICE),
    ("PY3 segnale = price riscritto", "Betfair/safe_strategy/proposte_opportunita.py",
     'for k in ("price_at_decision", "price"):', 'for k in ("price", "price_at_decision"):',
     [PY, "-m", "pytest", "Betfair/safe_strategy/tests/test_prezzo_segnale_b17_2026_09_25.py", "-q",
      "-p", "no:cacheprovider"], RADICE),
    ("SQL1 funzione aperta ad anon", "migrations/omega_request_approve_contesto_2026-09-25.sql",
     "REVOKE ALL ON FUNCTION public.omega_request_approve(bigint, numeric, jsonb) FROM anon;", "",
     [PY, "-m", "pytest", "Betfair/omega/tests/test_omega_approve_contesto_b17_2026_09_25.py", "-q",
      "-p", "no:cacheprovider"], RADICE),
    ("SQL2 payload rifatto da zero", "migrations/omega_request_approve_contesto_2026-09-25.sql",
     "payload = v_row.payload || v_extra", "payload = v_extra",
     [PY, "-m", "pytest", "Betfair/omega/tests/test_omega_approve_contesto_b17_2026_09_25.py", "-q",
      "-p", "no:cacheprovider"], RADICE),
]


def md5(p: str) -> str:
    with open(p, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def controllo() -> bool:
    """Senza mutazioni ogni comando e' VERDE (altrimenti un rosso non prova niente)."""
    visti = set()
    tutto_verde = True
    for _n, _rel, _v, _nu, cmd, cwd in MUTAZIONI:
        k = (tuple(cmd), cwd)
        if k in visti:
            continue
        visti.add(k)
        r = subprocess.run(cmd, cwd=cwd, env=ENV, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=600, shell=False)
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
            r = subprocess.run(cmd, cwd=cwd, env=ENV, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=600, shell=False)
            rosso = r.returncode != 0
        finally:
            with open(p, "wb") as f:
                f.write(orig)
        ok_md5 = md5(p) == h0
        esiti.append((nome, ("ROSSO" if rosso else "VERDE (test NON falsificante!)")
                      + (" md5 ripristinato" if ok_md5 else " md5 DIVERSO")))
    for nome, e in esiti:
        print("%-45s %s" % (nome, e))
    return 0 if all(e.startswith("ROSSO") and "ripristinato" in e for _, e in esiti) else 1


if __name__ == "__main__":
    sys.exit(main())
