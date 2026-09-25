# -*- coding: utf-8 -*-
"""Falsificazione dei test dello SCALPER AUTO-MODE (25/09): ogni mutazione del
codice di produzione DEVE far diventare rosso almeno il test indicato.

Il file originale si ripristina dal CONTENUTO letto in memoria (mai
`git checkout`: nel worktree di un delegato ha gia' cancellato lavoro, 23/09).

Uso (dal worktree, con il sandbox del DB):
  SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_KEY=x \
    python AUDIT_2026-09-25/mutazioni_scalper_auto_mode.py [--solo-python|--solo-frontend]
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]
FRONT = RADICE / "frontend"
T_PY = "Betfair/stream/tests/test_scalper_auto_mode_2026_09_25.py"
T_CR = "Betfair/stream/tests/test_scalper_control_room_2026_09_24.py"
SVC = "Betfair/stream/scalper/scalper_service.py"
AM = "Betfair/stream/scalper/auto_mode.py"

MUTAZIONI_PY = [
    # ---- auto_mode (logica pura)
    ("tetto ignorato", AM, "return min(n, TETTO_MASSIMO)", "return 10 ** 6", T_PY),
    ("tetto di default 5", AM, "TETTO_DEFAULT = 2", "TETTO_DEFAULT = 5", T_PY),
    ("tetto nei params della sessione", AM, "    out.pop(CHIAVE_TETTO, None)\n", "", T_PY),
    ("vita ignorata", AM, "return float(ora) < ko + vita_sessione_s(params)", "return True", T_PY),
    ("chiusa a mano riarmata", AM, '        return "chiusa a mano"', "        return None", T_PY),
    ("errore riarmato", AM, '        return "in errore"', "        return None", T_PY),
    ("conclusa riarmata", AM, '        return "conclusa"', "        return None", T_PY),
    ("origine auto per difetto", AM,
     "return ORIGINE_AUTO if o == ORIGINE_AUTO else ORIGINE_MANUALE", "return ORIGINE_AUTO", T_PY),
    ("feed sparito subito", AM, "if float(ora) - dal >= ASSENZA_FEED_S:", "if True:", T_PY),
    ("feed CLOSED tenuto", AM,
     '        if str(p.get("mo_status") or "").strip().upper() == "CLOSED":\n            continue\n',
     "", T_PY),
    ("paper e live insieme", AM, "        if m != modalita:\n            return m\n", "", T_PY),
    # ---- il giro del supervisore
    ("feed muto trattato vivo", SVC,
     "feed_vivo = feed_letto and eta is not None and eta <= AM.SCANNER_VIVO_S",
     "feed_vivo = feed_letto", T_PY),
    ("spento non ferma", SVC,
     "        for r in auto_attive:\n            ev = str(r.get(\"event_id\"))\n            try:\n                db.ferma_auto(ev)\n",
     "        for r in []:\n            ev = str(r.get(\"event_id\"))\n            try:\n                db.ferma_auto(ev)\n",
     T_PY),
    ("guardia ignorata", SVC, "    if not bloccato and not conflitto and tetto > 0",
     "    if not conflitto and tetto > 0", T_PY),
    ("conflitto ignorato", SVC, "    if not bloccato and not conflitto and tetto > 0",
     "    if not bloccato and tetto > 0", T_PY),
    ("tetto senza la card", SVC, "posti = max(0, tetto - len(con_processo))", "posti = tetto", T_PY),
    ("live nasce paper", SVC, '"dry_run": modalita != "live",', '"dry_run": True,', T_PY),
    ("paper nasce live", SVC, '"dry_run": modalita != "live",', '"dry_run": False,', T_PY),
    ("origine non scritta", SVC, '"origine": AM.ORIGINE_AUTO,', '"origine": "manuale",', T_PY),
    ("follow riscritto sempre", SVC, "                    if ev not in follow:\n                        db.segui(p)\n",
     "                    db.segui(p)\n", T_PY),
    ("follow chiuso riaperto", SVC,
     "                if str(follow.get(ev) or \"\").upper() in AM.FOLLOW_CHIUSI:\n                    return True\n",
     "", T_PY),
    ("interruttore non riletto a caldo", SVC,
     "if not (cambiato or forza or ora - st.ultimo_giro >= AUTO_GIRO_S):",
     "if not (forza or ora - st.ultimo_giro >= AUTO_GIRO_S):", T_PY),
    ("avvio nuovo non spegne", SVC, "    if st.guardia.attiva and not st.guardia.fatto:",
     "    if False:", T_PY),
    ("stats sempre riscritte", SVC, "    if firma == st.firma_stats:\n        return\n", "", T_PY),
    ("ferma_auto anche manuali", SVC, '.eq("event_id", event_id).eq("origine", "auto")',
     '.eq("event_id", event_id)', T_PY),
    ("segui sovrascrive", SVC,
     '            riga, on_conflict="event_id", ignore_duplicates=True).execute()\n\n    def arma',
     '            riga, on_conflict="event_id").execute()\n\n    def arma', T_PY),
    ("arma sopra una riga viva", SVC,
     '.eq("event_id", event_id).eq("status", "stopped"))', '.eq("event_id", event_id))', T_PY),
    ("canale: pubblica sempre", SVC, "            if self.firme.get(ev) != firma:\n",
     "            if True:\n", T_PY),
    ("canale: finale mai riletta", SVC, "                finale = db.riga_control(ev)\n",
     "                finale = None\n", T_PY),
    # ---- il flag degli ordini
    ("specchio senza flag", "Betfair/stream/scalper/scalper_session.py",
     '                riga["source"] = SOURCE_SPECCHIO\n', "", T_PY),
    ("flag sbagliato", "Betfair/stream/scalper/scalper_session.py",
     'SOURCE_SPECCHIO = "scalper"', 'SOURCE_SPECCHIO = "runner"', T_CR),
    ("regolati nel manuale app", "Betfair/stream/reconcile_worker.py",
     '    if src == SOURCE_SCALPER:\n        return "scalper"\n', "", T_PY),
    ("ordini vivi contati male", "Betfair/stream/scalper/scalper_session.py",
     '_STATI_VIVI = frozenset({"PENDING", "EXECUTABLE", "UPDATING", "CANCELLING"})',
     '_STATI_VIVI = frozenset({"PENDING", "EXECUTABLE", "EXECUTION_COMPLETE"})', T_PY),
    # ---- la migrazione
    ("CHECK source senza scalper", "migrations/scalper_auto_mode_2026-09-25.sql",
     "CHECK (source IN ('runner', 'account', 'scalper')) NOT VALID;",
     "CHECK (source IN ('runner', 'account')) NOT VALID;", T_PY),
    ("activate cambia modalita a caldo", "migrations/scalper_auto_mode_2026-09-25.sql",
     "    IF v_row.status = 'running' AND v_row.mode <> v_mode THEN",
     "    IF false THEN", T_PY),
    ("card non torna manuale", "migrations/scalper_auto_mode_2026-09-25.sql",
     "        origine      = 'manuale'\n", "", T_PY),
]

T_FE_CANALE = "src/lib/scalperCanale.test.ts"
T_FE_AUTO = "src/lib/scalperAuto.test.ts"
T_FE_INT = "src/lib/interruttoriScalper.test.ts"
T_FE_HOOK = "src/components/controlroom/useControlRoom.scalperCanale.test.tsx"
T_FE_PAN = "src/components/controlroom/PannelloBotScalper.test.tsx"
MUTAZIONI_FE = [
    ("canale aggiunge righe", "frontend/src/lib/scalperCanale.ts",
     "    if (db == null) return { ov, rileggi: true };", "    if (db == null) return { ov, rileggi: false };",
     T_FE_CANALE),
    ("canale vince sempre", "frontend/src/lib/scalperCanale.ts",
     "    if (letturaMs != null && !(msg.ms > letturaMs)) return { ov, rileggi: false };\n", "",
     T_FE_CANALE),
    ("chiusura senza rilettura", "frontend/src/lib/scalperCanale.ts",
     "    const rileggi = sessioneViva(vistaPrima) && !sessioneViva(dopo);",
     "    const rileggi = false;", T_FE_HOOK),
    ("servizio ignorato nello stato", "frontend/src/lib/scalperControlRoom.ts",
     "    const autoAcceso = String(servizio?.status ?? '') === 'running';",
     "    const autoAcceso = false;", T_FE_AUTO),
    ("avvia non scrive", "frontend/src/lib/interruttori.ts",
     "        if (bot === 'scalper') { await attivaScalperAuto(modalita); dopo(); return; }",
     "        if (bot === 'scalper') { dopo(); return; }", T_FE_INT),
    ("ripiego silenzioso su ogni errore", "frontend/src/lib/interruttori.ts",
     "                    if (!rpcAssente(e)) throw e;\n", "", T_FE_INT),
    # la guardia e' DOPPIA (cambiaModalita e cambiaModalitaServizio): togliere
    # solo la prima resta verde perche' la seconda la copre (difesa voluta);
    # si toglie la seconda, che il gesto "tetto di modalita" chiama diretto
    ("modalita a caldo", "frontend/src/lib/interruttori.ts",
     "        if (bot === 'scalper') throw new ScalperModalitaAllAvvio();\n",
     "", T_FE_INT),
    ("pannello: passa a soldi veri", "frontend/src/components/controlroom/PannelloBot.tsx",
     "{r.modalita != null && !r.armoPerPartita && !r.modalitaSoloAllAvvio && (",
     "{r.modalita != null && !r.armoPerPartita && (", T_FE_PAN),
    ("hook: canale scalper non sottoscritto", "frontend/src/components/controlroom/useControlRoom.ts",
     "const offSessioni = ch.subscribe(TOPIC_SCALPER_SESSIONI,", "const offSessioni = ch.subscribe('x',",
     T_FE_HOOK),
    ("hook: overlay non applicato", "frontend/src/components/controlroom/useControlRoom.ts",
     "        () => vistaScalper(scalperCR, scalperLetturaMs, scalperOv),",
     "        () => scalperCR,", T_FE_HOOK),
    ("hook: canale giu' tiene l'overlay", "frontend/src/components/controlroom/useControlRoom.ts",
     "                scalperOvRef.current = overlayScalperVuoto();\n                setScalperOv(scalperOvRef.current);\n",
     "", T_FE_HOOK),
    ("frase auto sbagliata", "frontend/src/lib/scalperControlRoom.ts",
     "`auto-mode: ${n} ${n === 1 ? 'sessione' : 'sessioni'} (${dalFeed} dal feed)`",
     "`auto-mode: ${n} sessioni`", T_FE_AUTO),
]


def gira_py(test: str) -> int:
    return subprocess.run([sys.executable, "-m", "pytest", test, "-q", "-x",
                           "-p", "no:cacheprovider"], cwd=RADICE,
                          capture_output=True, text=True, encoding="utf-8", errors="replace").returncode


def gira_fe(test: str) -> int:
    return subprocess.run("npx vitest run %s" % test, cwd=FRONT, shell=True,
                          capture_output=True, text=True, encoding="utf-8", errors="replace").returncode


def applica(lista, gira) -> list:
    esiti = []
    for nome, rel, vecchio, nuovo, test in lista:
        p = RADICE / rel
        originale = p.read_text(encoding="utf-8")
        if originale.count(vecchio) != 1:
            esiti.append((nome, "NON TROVATA (%d)" % originale.count(vecchio)))
            continue
        try:
            p.write_text(originale.replace(vecchio, nuovo), encoding="utf-8")
            rc = gira(test)
        finally:
            p.write_text(originale, encoding="utf-8")
        esiti.append((nome, "ROSSO (ok)" if rc != 0 else "VERDE = TEST CIECO"))
    return esiti


def main() -> int:
    esiti = []
    if "--solo-frontend" not in sys.argv:
        esiti += applica(MUTAZIONI_PY, gira_py)
    if "--solo-python" not in sys.argv:
        esiti += applica(MUTAZIONI_FE, gira_fe)
    for nome, e in esiti:
        print("%-42s %s" % (nome, e))
    return 0 if all(e == "ROSSO (ok)" for _n, e in esiti) else 1


if __name__ == "__main__":
    raise SystemExit(main())
