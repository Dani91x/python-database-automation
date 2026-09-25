"""FALSIFICAZIONE dei test nuovi (25/09, atlante a domanda). Per ogni test:
una rottura MINIMA del codice di produzione, il test deve diventare ROSSO;
poi il file si ripristina dal contenuto in memoria (mai git checkout).
Da lanciare dalla radice del worktree con SUPABASE_URL finto esportato."""
import os
import subprocess
import sys

T = "Betfair/stream/tests/test_atlante_a_domanda_2026_09_25.py"
T_OLD = "Betfair/stream/tests/test_genera_atlante_2026_09_24.py"
T_SAFE = "Betfair/safe_strategy/tests/test_atlante_note_livello_2026_09_25.py"
AD = "Betfair/stream/scalper/atlante_a_domanda.py"
GA = "Betfair/stream/scalper/genera_atlante.py"
HA = "Betfair/stream/scalper/hazard_atlas.py"

MUT = [
    ("M1 lega ricalcolata a ogni comparsa", AD,
     "nuove = [l for l in osservate_ora if l not in self.leghe",
     "nuove = [l for l in osservate_ora if True",
     T + "::test_lega_nuova_calcolata_una_volta_sola_e_seconda_comparsa_senza_richieste"),
    ("M2 coverage senza filtro eventi", GA,
     '"league_id": f"in.({blocco})", "fixtures_events": "eq.true",',
     '"league_id": f"in.({blocco})",',
     T + "::test_lega_nuova_calcolata_una_volta_sola_e_seconda_comparsa_senza_richieste"),
    ("M2b coverage senza filtro eventi (test dedicato)", GA,
     '"league_id": f"in.({blocco})", "fixtures_events": "eq.true",',
     '"league_id": f"in.({blocco})",',
     T + "::test_stagioni_con_eventi_legge_solo_le_true"),
    ("M3 nessuna adozione dal DB", AD,
     "        if not rows or not isinstance(rows[0].get(\"stato\"), dict):\n            return None",
     "        return None",
     T + "::test_lega_gia_sul_db_si_adotta_con_una_sola_get"),
    ("M4 niente attesa degli eventi", AD,
     "                if senza_eventi:",
     "                if False:",
     T + "::test_incrementale_legge_solo_le_partite_nuove_e_aspetta_gli_eventi"),
    ("M5 rilettura delle gia' contate", AD,
     "            if fid in visti[lid] or str(fid) in self.chiuse:",
     "            if str(fid) in self.chiuse:",
     T + "::test_incrementale_legge_solo_le_partite_nuove_e_aspetta_gli_eventi"),
    ("M6 tetto orario ignorato", AD,
     'int(self.p["tetto_ora"]) - len(self.calcolate_ts)',
     'int(self.p["tetto_ora"])',
     T + "::test_tetto_per_ciclo_e_per_ora_e_leghe_in_preparazione"),
    ("M7 priorita' al contrario", AD,
     "nuove.sort(key=lambda l: primo_ko.get(l, adesso))",
     "nuove.sort(key=lambda l: primo_ko.get(l, adesso), reverse=True)",
     T + "::test_tetto_per_ciclo_e_per_ora_e_leghe_in_preparazione"),
    ("M8 stagioni nuove mai cercate", AD,
     "                        if y not in acquisite",
     "                        if False",
     T + "::test_stagione_nuova_in_coverage_acquisita_senza_intervento"),
    ("M9 'in preparazione' mai letto", HA,
     'raw = ((atlas or {}).get("meta") or {}).get("leghe_in_preparazione") or []',
     "raw = []",
     T + "::test_lookup_partita_osservata_livello_n_confidenza_eta"),
    ("M10 seme ignorato", GA,
     "    if seme:\n        for lid, blk in",
     "    if False:\n        for lid, blk in",
     T + "::test_lookup_partita_osservata_livello_n_confidenza_eta"),
    ("M11 squadre anche su lega non affidabile", HA,
     'if lega["affidabile"] and ta and tb and cell and sr',
     "if ta and tb and cell and sr",
     T + "::test_consulta_squadre_per_id_e_solo_su_lega_affidabile"),
    ("M12 squadra per id ignorata", HA,
     "    if team_id is not None:\n        try:",
     "    if False:\n        try:",
     T + "::test_consulta_squadre_per_id_e_solo_su_lega_affidabile"),
    ("M13 omonimi: primo trovato", HA,
     "    if len(trovate) <= 1:",
     "    if trovate:",
     T + "::test_consulta_squadre_per_id_e_solo_su_lega_affidabile"),
    ("M14 globale su tutte le leghe", GA,
     "    base = coperte or stati        # il globale si stima sul campione coperto (come il v1)",
     "    base = stati",
     T + "::test_lega_affidabile_identica_con_o_senza_le_leghe_piccole"),
    ("M15 soglia media spostata", GA, "PESO_MEDIA = 0.2", "PESO_MEDIA = 0.25",
     T + "::test_confidenze_dalle_soglie_dichiarate"),
    ("M16 notturno legge anche leghe fuori stato", GA,
     "        nuovi = [r for r in nuovi if str(_int(r.get(\"league_id\"))) in stati]",
     "        pass",
     T + "::test_incrementale_notturno_solo_leghe_in_stato"),
    ("M17 notturno senza filigrana si ferma", GA,
     "            if not args.filigrana_da_ora_se_assente:",
     "            if True:",
     T + "::test_cli_senza_filigrana_parte_da_ora_invece_di_fermarsi"),
    ("M18 by_league solo leghe sopra soglia (come prima)", GA,
     "    for lid, s in stati.items():\n        nf = int(s.get(\"n_fixtures\") or 0)",
     "    for lid, s in coperte.items():\n        nf = int(s.get(\"n_fixtures\") or 0)",
     T_OLD + "::test_lega_sotto_soglia_entra_con_griglia_e_confidenza_dichiarata"),
    ("M19 gol per lega/stagione (scansione della pkey)", GA,
     '                                                          "fixture_id": f"in.({lista})",\n'
     '                                                          "event_type": "eq.Goal"}, chiave="id"))',
     '                                                          "league_id": f"eq.{lid}",\n'
     '                                                          "season_year": f"eq.{anno}",\n'
     '                                                          "event_type": "eq.Goal"}, chiave="id"))',
     T + "::test_lega_nuova_calcolata_una_volta_sola_e_seconda_comparsa_senza_richieste"),
    ("M20 Safe: 'in preparazione' non dichiarato", "Betfair/safe_strategy/opportunity.py",
     '        elif consulta["lega"]["in_preparazione"]:',
     "        elif False:",
     T_SAFE + "::test_lega_in_preparazione_dichiarata_e_confronto_sul_globale"),
    ("M21 Safe: nota senza livello/n/confidenza", "Betfair/safe_strategy/opportunity.py",
     'f"[{source}] ({dettaglio}), divergenza {div * 100:.0f}%; {eta}")',
     'f"[{source}], divergenza {div * 100:.0f}%; {eta}")',
     T_SAFE + "::test_nota_safe_dice_livello_n_e_confidenza_senza_cambiare_la_decisione"),
    ("M22 Mike: livello non passato alla scheda", "Betfair/mike/dossier.py",
     '            out["hazard_livello"] = c["livello"]\n', "",
     T_SAFE + "::test_mike_live_frame_porta_livello_confidenza_e_nota"),
    ("M23 attesa riletta a ogni ciclo (niente pausa di 60')", AD,
     '            if ult is not None and adesso - ult < float(self.p["riprova_attesa_min"]) * 60.0:',
     "            if False:",
     T + "::test_incrementale_legge_solo_le_partite_nuove_e_aspetta_gli_eventi"),
    ("M24 stagione senza coverage lasciata in attesa", AD,
     "                    if cov_l is not None and anno_m is not None and anno_m not in cov_l:",
     "                    if False:",
     T + "::test_partita_di_stagione_senza_eventi_in_coverage_si_chiude_subito"),
    ("M25 partita assente da matches ignorata", AD,
     "                if fid not in presenti:\n                    self._attendi(fid, adesso, attesa, conti)",
     "                if False:\n                    pass",
     T + "::test_partita_di_stagione_senza_eventi_in_coverage_si_chiude_subito"),
    ("M26 scrittura su DB a ogni ciclo", AD,
     '                and adesso - self.ultimo_flush >= float(self.p["scrivi_db_ogni_h"]) * 3600.0):',
     "                ):",
     T + "::test_scrittura_su_db_a_blocchi_non_a_ogni_partita"),
]

env = dict(os.environ, SUPABASE_URL="http://127.0.0.1:9", SUPABASE_SERVICE_ROLE_KEY="x",
           SUPABASE_KEY="x")
esiti = []
for nome, path, vecchio, nuovo, test in MUT:
    orig = open(path, encoding="utf-8").read()
    assert orig.count(vecchio) == 1, (nome, orig.count(vecchio))
    try:
        open(path, "w", encoding="utf-8").write(orig.replace(vecchio, nuovo))
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-x", test],
                           capture_output=True, text=True, env=env, timeout=300)
        rosso = r.returncode != 0
    finally:
        open(path, "w", encoding="utf-8").write(orig)
    esiti.append((nome, "ROSSO" if rosso else "VERDE (!)"))
    print(f"{nome}: {'ROSSO' if rosso else 'VERDE - test NON falsificato'}")
r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", T, T_OLD, T_SAFE],
                   capture_output=True, text=True, env=env, timeout=300)
print("ripristino:", r.stdout.strip().splitlines()[-1])
