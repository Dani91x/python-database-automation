"""Falsificazione del CANTIERE N: applica UNA mutazione alla volta al codice di
produzione, lancia i test collegati, ripristina SEMPRE il contenuto originale
(tenuto in memoria) anche in caso di errore, e verifica il ripristino byte per byte.

Uso (dalla radice del worktree):
    .venv/Scripts/python.exe AUDIT_2026-09-28/cantiere_n/falsifica_n.py [NOME ...]
Senza nomi le esegue tutte. Mai interrompere a meta'.
"""
import os
import subprocess
import sys

WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PY = os.path.join(WT, ".venv", "Scripts", "python.exe")
ENV = dict(os.environ, SUPABASE_URL="http://127.0.0.1:9", SUPABASE_SERVICE_ROLE_KEY="x",
           SUPABASE_KEY="x", PYTHONDONTWRITEBYTECODE="1")

T_AVVIO = "Betfair/stream/tests/test_uscite_manuali_al_nuovo_avvio_2026_09_28.py"
T_MIKE_R = "Betfair/mike/tests/test_mike_uscite_manuali_al_riavvio_2026_09_28.py"
T_OMEGA_R = "Betfair/omega/test_omega_uscite_manuali_al_riavvio_2026_09_28.py"
T_SAFE_R = "Betfair/safe_strategy/tests/test_uscite_manuali_al_riavvio_2026_09_28.py"
T_SCALP_R = "Betfair/stream/tests/test_scalper_uscite_manuali_al_riavvio_2026_09_28.py"
T_TENNIS_R = "Betfair/stream/tennis_live/tests/test_tennis_uscite_manuali_al_riavvio_2026_09_28.py"
T_TS = "Betfair/stream/tennis_scalper/tests/test_uscite_proposte_bot_tennis_2026_09_28.py"
T_TS25 = "Betfair/stream/tennis_scalper/tests/test_uscite_manuali_bot_tennis_2026_09_25.py"
T_SCAL = "Betfair/stream/tests/test_scalper_uscite_automatiche_2026_09_25.py"
T_TFP = "Betfair/stream/tennis_live/tests/test_tennis_firme_e_proposte_2026_09_28.py"
T_COORD = "Betfair/stream/tests/test_coordinatore_cancello_uscite_2026_09_28.py"
T_COORD_MIKE = "Betfair/mike/tests/test_coordinatore_firma_dopo_decadenza_2026_09_28.py"

# nome -> (file, testo originale, testo mutato, test da lanciare)
MUTAZIONI = {
    "M1_avvio_non_resetta": (
        "Betfair/stream/avvio_app.py",
        "        uscite_manuali = uscite_a_manuali(uscite_bot, base)",
        "        uscite_manuali = None  # MUTAZIONE",
        [T_AVVIO, T_MIKE_R, T_OMEGA_R, T_SAFE_R, T_SCALP_R]),
    "M2_safe_scorda_il_tennis": (
        "Betfair/stream/avvio_app.py",
        '        return {**params, "uscite_automatiche": nuova, "tennis_exit_approval": True}',
        '        return {**params, "uscite_automatiche": nuova}  # MUTAZIONE',
        [T_AVVIO, T_SAFE_R]),
    "M3_mike_non_collegato": (
        "Betfair/mike/service.py",
        '                                       uscite_bot="mike")',
        '                                       uscite_bot=None)  # MUTAZIONE',
        [T_MIKE_R]),
    "M4_omega_non_collegato": (
        "Betfair/omega/omega_service.py",
        '                                       uscite_bot="omega")',
        '                                       uscite_bot=None)  # MUTAZIONE',
        [T_OMEGA_R]),
    "M5_safe_non_collegato": (
        "Betfair/safe_strategy/bot_service.py",
        '                                       uscite_bot="safe")',
        '                                       uscite_bot=None)  # MUTAZIONE',
        [T_SAFE_R]),
    "M6_scalper_non_collegato": (
        "Betfair/stream/scalper/scalper_service.py",
        '                uscite_bot="scalper")',
        '                uscite_bot=None)  # MUTAZIONE',
        [T_SCALP_R]),
    "M7_tennis_non_resetta": (
        "Betfair/stream/tennis_live/tennis_bot_service.py",
        '        uscite_auto = r.get("uscite_automatiche") is True',
        '        uscite_auto = False  # MUTAZIONE',
        [T_TENNIS_R]),
    "M8_watchdog_resetta": (
        "Betfair/stream/avvio_app.py",
        "    if stesso_avvio(stats, boot):",
        "    if False and stesso_avvio(stats, boot):  # MUTAZIONE",
        [T_AVVIO]),
    # --- blocco 2: l'approvazione ricontrolla la condizione ---
    "M9_omega_firma_senza_ricontrollo": (
        "Betfair/omega/omega_service.py",
        "    rifiuto = _rifiuta_se_condizione_caduta(db, tr, payload)",
        "    rifiuto = None  # MUTAZIONE",
        ["Betfair/omega/tests/test_omega_approvazione_ricontrolla_2026_09_28.py"]),
    "M10_omega_valida_ignorata": (
        "Betfair/omega/omega_service.py",
        '    if not isinstance(val, dict) or val.get("valida") is not False:',
        '    if True:  # MUTAZIONE',
        ["Betfair/omega/tests/test_omega_approvazione_ricontrolla_2026_09_28.py"]),
    # M11-M13 (Safe) tolte: il ricontrollo all'approvazione di Safe e' quello del
    # cantiere D1 gia' su master (`_proposta_non_piu_valida`), falsificato da D1.
    "M14_mike_firma_vale_per_ogni_motivo": (
        "Betfair/mike/engine.py",
        "                          and not _stessa_uscita_firmata(ctx, d))",
        "                          and False)  # MUTAZIONE",
        ["Betfair/mike/tests/test_mike_firma_stesso_motivo_2026_09_28.py"]),
    # --- blocco 2: il pulsante unico (frontend) ---
    "F1_conferma_non_inerte": (
        "frontend/src/components/controlroom/InterruttoreUscite.tsx",
        "    const troppoPresto = armataDa != null && Date.now() - armataDa < ATTESA_CONFERMA_USCITE_MS;",
        "    const troppoPresto = false; // MUTAZIONE",
        ["vitest", "src/components/controlroom/PannelloBotUscite.test.tsx"]),
    "F2_tennis_fuori_dal_pulsante": (
        "frontend/src/lib/interruttori.ts",
        "            await setTennisBotUscite(i.bot as TennisBotKey, automatiche);",
        "            throw new UsciteNonGestiteQui(i.etichetta); // MUTAZIONE",
        ["vitest", "src/lib/interruttoriUscite.test.ts"]),
    # --- blocco 3: proposta -> firma -> ordine per i bot di flusso ---
    "M15_firma_mai_valida": (
        "Betfair/stream/uscite_proposte.py",
        "        if firma is not None and now_s - firma <= TTL_APPROVAZIONE_S:",
        "        if False:  # MUTAZIONE",
        [T_TS, T_SCAL]),
    "M16_firma_senza_scadenza": (
        "Betfair/stream/uscite_proposte.py",
        "        if firma is not None and now_s - firma <= TTL_APPROVAZIONE_S:",
        "        if firma is not None:  # MUTAZIONE",
        [T_TS]),
    "M17_condizione_caduta_ignorata": (
        "Betfair/stream/uscite_proposte.py",
        "        tenere = set(vive)",
        "        return  # MUTAZIONE",
        [T_TS, T_SCAL]),
    "M18_swing_stop_sempre_automatico": (
        "Betfair/stream/tennis_scalper/tennis_swing_bot.py",
        "            automatiche=bool(self.uscite_automatiche), chiave=chiave,",
        "            automatiche=bool(self.uscite_automatiche) or kind != 'target', chiave=chiave,  # MUTAZIONE",
        [T_TS, T_TS25]),
    "M19_pro_strutturale_automatica": (
        "Betfair/stream/tennis_scalper/tennis_pro_bot.py",
        "                if self._cancello_lascia(prefisso, \"strutturale\", vive, *nums):",
        "                if True:  # MUTAZIONE",
        [T_TS]),
    "M20_flb_green_senza_proposta": (
        "Betfair/stream/tennis_scalper/tennis_flb_bot.py",
        "            vuole_green = self.cancello_uscite.lascia_uscire(",
        "            vuole_green = bool(self.uscite_automatiche) and self.cancello_uscite.lascia_uscire(  # MUTAZIONE",
        [T_TS]),
    "M21_scalper_stop_sempre_automatico": (
        "Betfair/stream/scalper/scalper_bot.py",
        "                if not self._lascia_uscire(\n                        slot, \"stop\" if cond_stop else \"timeout\",",
        "                if False and not self._lascia_uscire(  # MUTAZIONE\n                        slot, \"stop\" if cond_stop else \"timeout\",",
        [T_SCAL]),
    "M22_tennis_scalper_gamba_opposta_in_manuale": (
        "Betfair/stream/tennis_scalper/tennis_scalper_bot.py",
        "            if done and el is not None and self.uscite_automatiche and abs(mb - float(",
        "            if done and el is not None and abs(mb - float(  # MUTAZIONE",
        [T_TS]),
    "M23_eccezione_scalper_tennis_rimessa": (
        "Betfair/stream/tennis_live/auto_mode.py",
        "BOT_USCITE_SEMPRE_AUTOMATICHE: frozenset = frozenset()",
        "BOT_USCITE_SEMPRE_AUTOMATICHE: frozenset = frozenset({\"tennis_scalper\"})  # MUTAZIONE",
        ["Betfair/stream/tennis_live/tests/test_tennis_auto_mode_2026_09_25.py"]),
    "M24_runner_non_passa_la_firma": (
        "Betfair/stream/tennis_live/tennis_runner.py",
        "            _UP.applica_firme((strat,), riga.get(\"params\"))",
        "            pass  # MUTAZIONE",
        [T_TFP]),
    "M25_ponte_senza_proposte": (
        "Betfair/stream/tennis_live/tennis_bot_service.py",
        "                proposte.append({**p, \"event_id\": str(r.get(\"event_id\") or \"\")})",
        "                pass  # MUTAZIONE",
        [T_TFP]),
    "F4_firma_al_bot_sbagliato": (
        "frontend/src/lib/proposteUscite.ts",
        "            p_event_id: p.eventId, p_bot_key: p.bot, p_chiave: p.chiave,",
        "            p_event_id: p.eventId, p_bot_key: 'tennis_swing', p_chiave: p.chiave, // MUTAZIONE",
        ["vitest", "src/components/controlroom/ProposteUsciteFlusso.test.tsx"]),
    "F5_scheda_mike_spunta_libera": (
        "frontend/src/components/mike/MikeParamsSheet.tsx",
        "            if (f.key === 'uscite_automatiche') {",
        "            if (f.key === 'MUTAZIONE') {",
        ["vitest", "src/components/controlroom/InterruttoreUsciteSchede.test.tsx"]),
    "F6_scheda_omega_due_pulsanti": (
        "frontend/src/lib/omega.ts",
        "            { key: 'uscite_protezione', label: 'Uscite calcolate dal bot', type: 'uscite',",
        "            { key: 'uscite_protezione', label: 'Uscite calcolate dal bot', type: 'choice', // MUTAZIONE",
        ["vitest", "src/components/omega/OmegaParamsSheet.test.tsx"]),
    # --- 29/09: reperti del coordinatore A-I ---
    "A1_la_decadenza_non_porta_via_la_firma": (
        "Betfair/stream/uscite_proposte.py",
        "        firma = self.approvate.pop(k, None)",
        "        firma = self.approvate.get(k)  # MUTAZIONE",
        [T_COORD, T_TS]),
    "A2_firma_accettata_senza_proposta": (
        "Betfair/stream/uscite_proposte.py",
        "                if viva is None or (nata is not None and t < nata):",
        "                if False:  # MUTAZIONE",
        [T_COORD, T_TS, T_SCAL]),
    "B1_mike_firma_senza_proposta_vale": (
        "Betfair/mike/engine.py",
        "        # dice che cosa e' stato approvato -> non esegue niente\n        return False",
        "        # dice che cosa e' stato approvato -> non esegue niente\n        return True  # MUTAZIONE",
        [T_COORD_MIKE, "Betfair/mike/tests/test_mike_firma_stesso_motivo_2026_09_28.py"]),
    "B2_mike_decadenza_tiene_la_firma": (
        "Betfair/mike/engine.py",
        "    # se la proposta decade, la firma cade con lei\n    if isinstance(ctx.uscita_approvata, dict):",
        "    # se la proposta decade, la firma cade con lei\n    if False:  # MUTAZIONE",
        [T_COORD_MIKE]),
    "C1_omega_non_guarda_il_giro_di_adesso": (
        "Betfair/omega/omega_service.py",
        "        motivo = PR.firma_ancora_valida(tr.get(\"id\"), payload.get(\"motivo_codice\"), now)",
        "        motivo = None  # MUTAZIONE",
        ["Betfair/omega/tests/test_omega_approvazione_ricontrolla_2026_09_28.py"]),
    "C2_omega_motivo_diverso_accettato": (
        "Betfair/omega/omega_proposte.py",
        "    if str(v[2]) != str(motivo_firmato):",
        "    if False:  # MUTAZIONE",
        ["Betfair/omega/tests/test_omega_approvazione_ricontrolla_2026_09_28.py"]),
    "C3_safe_motivo_diverso_accettato": (
        "Betfair/safe_strategy/bot_service.py",
        "        if motivo_firmato and (re.sub(",
        "        if False and motivo_firmato and (re.sub(",
        ["Betfair/safe_strategy/tests/test_firma_stesso_motivo_2026_09_29.py"]),
    "E1_messaggio_falso": (
        "Betfair/stream/tennis_live/tennis_runner.py",
        "time-stop, uscita strutturale) e' una PROPOSTA che approvi tu \"",
        "time-stop, uscita strutturale) stop e protezioni restano \"  # MUTAZIONE",
        [T_TFP]),
    # --- 29/09 sera: sniper sulla base D2 e strada esatta ---
    "S1_sniper_timeout_scavalca": (
        "Betfair/stream/scalper/sniper_bot.py",
        "                    and self._lascia_uscire(pos, runner.selection_id, \"timeout\",",
        "                    and True or self._lascia_uscire(pos, runner.selection_id, \"timeout\",  # MUTAZIONE",
        ["Betfair/stream/tests/test_sniper_uscite_automatiche_2026_09_28.py"]),
    "S2_sniper_stop_scavalca": (
        "Betfair/stream/scalper/sniper_bot.py",
        "                            and self._lascia_uscire(pos, runner.selection_id, \"stop\",",
        "                            and True or self._lascia_uscire(pos, runner.selection_id, \"stop\",  # MUTAZIONE",
        ["Betfair/stream/tests/test_sniper_uscite_automatiche_2026_09_28.py"]),
    "X1_swing_uscita_non_esatta": (
        "Betfair/stream/tennis_scalper/tennis_swing_bot.py",
        "        o = self._place(market, sel, side, get_nearest_price(price), sz,\n                        copertura=True)",
        "        o = self._place(market, sel, side, get_nearest_price(price), sz,\n                        copertura=False)  # MUTAZIONE",
        [T_TS]),
    "F3_automatiche_senza_conferma": (
        "frontend/src/components/controlroom/InterruttoreUscite.tsx",
        "                    onClick={() => setArmataDa(Date.now())}",
        "                    onClick={() => void cambia(true)} // MUTAZIONE",
        ["vitest", "src/components/controlroom/PannelloBotUscite.test.tsx"]),
}


def main(nomi):
    for nome in nomi:
        rel, vecchio, nuovo, tests = MUTAZIONI[nome]
        path = os.path.join(WT, rel)
        with open(path, "r", encoding="utf-8", newline="") as fh:
            orig = fh.read()
        n = orig.count(vecchio)
        if n == 0 and "\n" in vecchio:        # file con fine riga CRLF
            vecchio, nuovo = vecchio.replace("\n", "\r\n"), nuovo.replace("\n", "\r\n")
            n = orig.count(vecchio)
        if n != 1:
            print(f"{nome}: TESTO ORIGINALE TROVATO {n} VOLTE - saltata")
            continue
        try:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(orig.replace(vecchio, nuovo))
            if tests and tests[0] == "vitest":
                r = subprocess.run(["npx.cmd", "vitest", "run", *tests[1:]],
                                   cwd=os.path.join(WT, "frontend"), env=ENV,
                                   capture_output=True, text=True, encoding="utf-8",
                                   errors="replace")
            else:
                r = subprocess.run([PY, "-m", "pytest", *tests, "-q", "-p", "no:cacheprovider"],
                                   cwd=WT, env=ENV, capture_output=True, text=True)
            coda = (r.stdout.strip().splitlines() or ["?"])[-1]
            print(f"{nome}: {'ROSSO' if r.returncode else 'VERDE (!!)'} -> {coda}")
        finally:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(orig)
        with open(path, "r", encoding="utf-8", newline="") as fh:
            assert fh.read() == orig, f"{nome}: RIPRISTINO NON IDENTICO"


if __name__ == "__main__":
    main(sys.argv[1:] or list(MUTAZIONI))
