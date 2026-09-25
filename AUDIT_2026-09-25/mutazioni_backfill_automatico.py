# Falsificazione del backfill automatico (25/09/2026): mutazione minima -> test rossi -> ripristino verificato (sha256).
# Uso (dalla radice del repo): python AUDIT_2026-09-25/mutazioni_backfill_automatico.py [M1 M2 ...]
import hashlib
import os
import subprocess
import sys

T = "test_backfill_automatico_2026_09_25.py"
V = "test_actions_fail_rumoroso_2026_09_25.py"
M = [
    # (id, file, vecchio, nuovo, test attesi rossi)
    ("M1 mapper non aggiorna", "leagues_mapper.py", "            if diff:\n", "            if False:\n",
     [T + "::test_mapper_aggiorna_i_flag_di_una_riga_esistente_senza_toccare_inserted_at"]),
    ("M2 mapper tocca inserted_at", "leagues_mapper.py", '.update({**diff, "updated_at": adesso})',
     '.update({**diff, "updated_at": adesso, "inserted_at": adesso})',
     [T + "::test_mapper_aggiorna_i_flag_di_una_riga_esistente_senza_toccare_inserted_at"]),
    ("M3 finestra infinita", "leagues_mapper.py", ">= oggi - timedelta(days=FINESTRA_AGGIORNAMENTO_GIORNI)",
     ">= date(1900, 1, 1)", [T + "::test_mapper_non_riscrive_le_stagioni_chiuse_da_oltre_30_giorni"]),
    ("M4 current del DB ignorato", "leagues_mapper.py", 'if riga_api.get("current") or riga_db.get("current"):',
     'if riga_api.get("current"):', [T + "::test_mapper_chiude_current_quando_la_stagione_finisce"]),
    ("M5 una sola pagina", "leagues_mapper.py", "        if len(data) < PAGINA:\n", "        if True:\n",
     [T + "::test_mapper_pagina_oltre_10000_coppie"]),
    ("M6 flag False chiamati", "season_gaps.py", "            if not on:\n                continue\n            tabella",
     "            if False:\n                continue\n            tabella",
     [T + "::test_lacune_chiama_solo_cio_che_manca_e_solo_endpoint_con_flag_true"]),
    ("M7 tutti gli endpoint per fixture", "per_fixture_backfill.py", "endpoints=endpoints, registra=True,",
     "endpoints=None, registra=True,", [T + "::test_lacune_chiama_solo_cio_che_manca_e_solo_endpoint_con_flag_true"]),
    ("M8 vuoto non registrato", "per_fixture_backfill.py", '"season_year": season_year, "esito": "vuoto"})',
     '"season_year": season_year, "esito": "sonda"})',
     [T + "::test_risposta_vuota_registrata_non_richiamata_poi_ritentata_poi_definitiva",
      T + "::test_daily_fixture_vuota_non_si_perde_entra_nella_coda_del_catchup"]),
    ("M9 in_attesa richiamata", "season_gaps.py", 'STATI_DA_CHIAMARE = ("da_chiamare", "errore", "da_richiamare")',
     'STATI_DA_CHIAMARE = ("da_chiamare", "errore", "da_richiamare", "in_attesa")',
     [T + "::test_risposta_vuota_registrata_non_richiamata_poi_ritentata_poi_definitiva"]),
    ("M10 errors trattato come vuoto", "per_fixture_backfill.py", '    if data.get("errors"):\n        return None\n', "",
     [T + "::test_errore_api_non_e_un_vuoto_e_non_cancella_dati_esistenti"]),
    ("M11 errore cancella i dati", "per_fixture_backfill.py", "            if grezzi is None:\n",
     "            if grezzi is None:\n                get_supabase().table(tabella).delete().eq(\"fixture_id\", fixture_id).execute()\n",
     [T + "::test_errore_api_non_e_un_vuoto_e_non_cancella_dati_esistenti"]),
    ("M12 odds non cancellate", "per_fixture_backfill.py",
     '        q.execute()\n', "        pass\n",
     [T + "::test_match_odds_cancellate_prima_del_reinserimento_niente_doppioni"]),
    ("M13 migrazione mancante muta", "season_gaps.py", "    msg = str(err)\n    return (", "    msg = str(err)\n    return False and (",
     [T + "::test_senza_migrazione_il_recupero_si_ferma_con_messaggio_chiaro"]),
    ("M14 completed con buchi", "season_gaps.py", "and lacune.aperti(flags) == 0 and lacune.ft_totali > 0:",
     "and lacune.ft_totali > 0:", [T + "::test_stato_completed_solo_a_stagione_finita_e_senza_buchi"]),
    ("M15 completed con 0 partite", "season_gaps.py", "and lacune.aperti(flags) == 0 and lacune.ft_totali > 0:",
     "and lacune.aperti(flags) == 0:", [T + "::test_stato_completed_solo_a_stagione_finita_e_senza_buchi"]),
    ("M16 chiamate fisse sempre", "season_backfill.py",
     "fisse = 1 if (chiamate_partite > 0 or serve_fixtures) else 0", "fisse = 1",
     [T + "::test_orchestratore_riapre_completed_vecchio_riempie_e_rilancio_fa_zero_chiamate"]),
    ("M17 stato sempre completed", "season_backfill.py", "es.stato = sg.calcola_stato(piano.coverage_row, lac_dopo, oggi)",
     'es.stato = "completed"', [T + "::test_orchestratore_riapre_completed_vecchio_riempie_e_rilancio_fa_zero_chiamate"]),
    ("M18 stato non scritto senza lavoro", "league_orchestrator.py",
     '            sb_mod.scrivi_stato_senza_lavoro(sb, piano, prec, "orchestratore", oggi)\n', "            pass\n",
     [T + "::test_orchestratore_stagione_finita_e_piena_diventa_completed"]),
    ("M19 dry-run esegue", "league_orchestrator.py", "        if dry_run:\n            continue\n",
     "        if False:\n            continue\n", [T + "::test_dry_run_non_chiama_l_api_e_non_scrive"]),
    ("M20 riserva da env ignorata", "api_quota.py", 'grezzo = (env.get("API_FOOTBALL_RISERVA_GIORNALIERA") or "").strip()',
     'grezzo = ""', [T + "::test_quota_riserva_da_env_default_3000"]),
    ("M21 niente fallback log", "api_quota.py", "if stato is None and n_log is not None:", "if False:",
     [T + "::test_quota_status_giu_fallback_api_call_log_con_avviso"]),
    ("M22 parte senza quota", "api_quota.py", '            raise QuotaNonLeggibile("contatore API non leggibile',
     '            return StatoQuota(0, 7500, self.riserva, "inventata")\n            raise QuotaNonLeggibile("contatore API non leggibile',
     [T + "::test_quota_nessuna_fonte_non_si_parte", T + "::test_quota_catchup_non_parte_se_quota_illeggibile"]),
    ("M23 /status con errors creduto", "api_quota.py", "    if errori:\n", "    if False:\n",
     [T + "::test_status_con_errors_non_e_un_contatore_valido"]),
    ("M24 header non letti", "api_client.py", "                self._leggi_header_quota(resp, endpoint)\n", "",
     [T + "::test_api_client_legge_gli_header_di_quota_senza_cambiare_call"]),
    ("M25 nessun controllo quota per partita", "per_fixture_backfill.py",
     "if quota is not None and not quota.copre(costo):", "if False:",
     [T + "::test_quota_si_ferma_a_fine_partita_mai_a_meta"]),
    ("M26 priorita' invertita", "seasons_catchup.py", "    return p1 + p2 + p3\n", "    return p3 + p2 + p1\n",
     [T + "::test_catchup_ordine_di_priorita_e_db_senza_buchi"]),
    ("M27 P2 per meno mancanze", "seasons_catchup.py",
     "p2 = sorted([v for v in con_lavoro if v.priorita == 2], key=lambda v: (-v.chiamate, v.chiave))",
     "p2 = sorted([v for v in con_lavoro if v.priorita == 2], key=lambda v: (v.chiamate, v.chiave))",
     [T + "::test_catchup_ordine_di_priorita_e_db_senza_buchi"]),
    ("M28 niente ricalcolo dopo lega", "seasons_catchup.py",
     "            quota.aggiorna()                               # RICALCOLO dopo ogni lega-stagione\n", "",
     [T + "::test_catchup_ordine_di_priorita_e_db_senza_buchi", T + "::test_catchup_fermo_per_quota_esce_0_con_riepilogo"]),
    ("M29 stop per quota = errore", "seasons_catchup.py", "    return 1 if (ris.errori or falliti) else 0",
     "    return 1 if (ris.errori or falliti or ris.fermato_per) else 0",
     [T + "::test_catchup_fermo_per_quota_esce_0_con_riepilogo"]),
    ("M30 errore lega ignorato", "seasons_catchup.py", "    return 1 if (ris.errori or falliti) else 0",
     "    return 1 if falliti else 0", [T + "::test_catchup_errore_di_una_lega_stagione_esce_diverso_da_0"]),
    ("M31 buchi vecchi tollerati", "seasons_catchup.py", "        if giorni > max_giorni:\n",
     "        if giorni > max_giorni + 100:\n", [T + "::test_catchup_buco_vecchio_con_budget_disponibile_esce_1_con_la_causa"]),
    ("M32 quota trattata come colpa", "seasons_catchup.py",
     '            if k in rimaste or (fermata and fermata != "errori_api"):', "            if False:",
     [T + "::test_catchup_buco_vecchio_per_quota_esce_0_con_stima_giorni"]),
    ("M33 concorrenza ignorata", "seasons_catchup.py",
     "        motivo = concorrenza.in_corso(forza=True) if concorrenza is not None else None", "        motivo = None",
     [T + "::test_catchup_si_ferma_se_un_action_concorrente_e_in_corso"]),
    ("M34 run GitHub mal lette", "seasons_catchup.py", 'get("total_count") or 0) > 0:', 'get("total_count") or 0) > 1:',
     [T + "::test_controllo_concorrenza_legge_le_run_di_github"]),
    ("M35 prioritarie sbagliate", "seasons_catchup.py", 'get("by_league")', 'get("by_team")',
     [T + "::test_leghe_prioritarie_dall_atlante_v3"]),
    ("M36 referto cieco", "seasons_catchup.py", "        n_aperti = lac.aperti(flags)\n", "        n_aperti = 0\n",
     [T + "::test_catchup_fermo_per_quota_esce_0_con_riepilogo"]),
    ("M37 daily chiama tutto", "daily_yesterday_backfill.py", "                                       endpoints=endpoints)",
     "                                       endpoints=None)",
     [T + "::test_daily_fixture_vuota_non_si_perde_entra_nella_coda_del_catchup"]),
    ("M38 fisse sulle stagioni vive", "season_backfill.py",
     "    if not fisse_su_stagione_viva and sg.e_corrente_o_recente(coverage_row, oggi):", "    if False:",
     [T + "::test_catchup_ordine_di_priorita_e_db_senza_buchi"]),
    ("M39 errore di lega fa crollare la run", "seasons_catchup.py",
     "        except Exception as e:                             # DB giu' ecc.: la run prosegue, exit 1 alla fine",
     "        except ZeroDivisionError as e:",
     [T + "::test_catchup_errore_di_una_lega_stagione_esce_diverso_da_0"]),
    ("M40 daily crolla senza migrazione", "daily_yesterday_backfill.py",
     "        except season_gaps.MigrazioneMancante as e:", "        except KeyError as e:",
     [T + "::test_daily_senza_migrazione_fa_il_lavoro_di_prima_con_avviso"]),
    ("M41 vuoti persi in silenzio", "season_gaps.py", "        if not _avviso_registro_dato:\n", "        if False:\n",
     [T + "::test_daily_senza_migrazione_fa_il_lavoro_di_prima_con_avviso"]),
    # --- reperti del coordinatore (R1-R5) ---
    ("M42 R1 delete quote di tutte le fonti", "per_fixture_backfill.py",
     '            q = q.eq("snapshot_type", "api_football")\n', "            pass\n",
     [T + "::test_r1_sostituzione_quote_non_tocca_le_quote_csv"]),
    ("M43 R2 vuoto che cancella", "per_fixture_backfill.py",
     "            if not rows:\n                stats[\"esiti\"][chiave] = \"vuoto\"\n",
     "            if not rows:\n                _sostituisci_righe(tabella, fixture_id, [])\n"
     "                stats[\"esiti\"][chiave] = \"vuoto\"\n",
     [T + "::test_r2_risposta_vuota_o_in_errore_non_cancella_mai_righe_presenti"]),
    ("M44 R2 errore che cancella", "per_fixture_backfill.py",
     "            if grezzi is None:\n",
     "            if grezzi is None:\n                _sostituisci_righe(tabella, fixture_id, [])\n",
     [T + "::test_r2_risposta_vuota_o_in_errore_non_cancella_mai_righe_presenti"]),
    ("M45 R3 parziale non registrato", "per_fixture_backfill.py", '"esito": "parziale" if batch_err else "ok"})',
     '"esito": "ok"})', [T + "::test_r3_insert_parziale_resta_un_buco_e_si_rifa_al_giro_dopo"]),
    ("M46 R4 quote fuori finestra chiamate", "season_gaps.py",
     'STATI_DA_CHIAMARE = ("da_chiamare", "errore", "da_richiamare")',
     'STATI_DA_CHIAMARE = ("da_chiamare", "errore", "da_richiamare", "non_disponibile")',
     [T + "::test_r4_quote_fuori_finestra_non_si_chiamano_e_non_sono_buchi",
      T + "::test_r4_referto_distingue_quote_non_recuperabili_dai_buchi"]),
    ("M47 R4 referto senza non disponibili", "seasons_catchup.py", "        non_disp += lac.non_disponibili(flags)\n", "",
     [T + "::test_r4_referto_distingue_quote_non_recuperabili_dai_buchi"]),
    ("M48 R5 retrain non esclusivo", "seasons_catchup.py", '"predictions_results_backfill.yml", "retrain_models.yml")',
     '"predictions_results_backfill.yml")',
     [T + "::test_r5_retrain_tra_le_action_esclusive_e_buco_vecchio_per_concorrenza_esce_0"]),
    ("M49 R5 concorrenza trattata come colpa", "seasons_catchup.py",
     '            if k in rimaste or (fermata and fermata != "errori_api"):', "            if fermata == 'quota':",
     [T + "::test_r5_retrain_tra_le_action_esclusive_e_buco_vecchio_per_concorrenza_esce_0"]),
    # --- aggregati per lega-stagione (seguito 25/09) ---
    ("M50 aggregati mai chiamati", "season_backfill.py", "    for nome in piano.lacune.agg_da_fare():",
     "    for nome in []:", [T + "::test_agg_mancante_va_in_coda_ed_e_chiamato_poi_db_senza_buchi"]),
    ("M51 costo aggregati fuori dalla coda", "seasons_catchup.py",
     "        return self.lacune.chiamate_per_fixture(self.flags) + self.lacune.chiamate_aggregati()",
     "        return self.lacune.chiamate_per_fixture(self.flags)",
     [T + "::test_agg_mancante_va_in_coda_ed_e_chiamato_poi_db_senza_buchi"]),
    ("M52 flag aggregato ignorato", "season_aggregates.py", "    if not flag:\n        return \"flag_false\"\n", "",
     [T + "::test_agg_flag_false_non_chiamato_e_dichiarato"]),
    ("M53 classifica sempre da rifare", "season_aggregates.py", "        serve = nuove\n", "        serve = True\n",
     [T + "::test_agg_presente_e_fresco_zero_chiamate"]),
    ("M54 top_* senza cadenza settimanale", "season_aggregates.py",
     "t < adesso - timedelta(days=GIORNI_TOP)", "True",
     [T + "::test_agg_cadenza_classifica_dopo_giornata_injuries_giornaliero_top_settimanale"]),
    ("M55 injuries non giornaliero", "season_aggregates.py",
     "        serve = viva and t < adesso - timedelta(hours=ORE_INJURIES)", "        serve = False",
     [T + "::test_agg_cadenza_classifica_dopo_giornata_injuries_giornaliero_top_settimanale"]),
    ("M56 delete fallita che inserisce", "season_aggregates.py",
     "              f\"NESSUN insert (niente doppioni)\")\n        return \"errore\"",
     "              f\"NESSUN insert (niente doppioni)\")",
     [T + "::test_agg_idempotente_nessuna_riga_doppia_e_delete_fallita_non_inserisce"]),
    ("M57 errore API aggregato come vuoto", "season_aggregates.py", "        if lista is None:",
     "        if lista is None and False:", [T + "::test_agg_errore_api_non_e_vuoto_e_resta_buco"]),
    ("M58 vuoto aggregato non ricordato", "season_aggregates.py",
     'if esito in ("righe", "vuoto") else None', 'if esito in ("righe",) else None',
     [T + "::test_agg_mancante_va_in_coda_ed_e_chiamato_poi_db_senza_buchi"]),
    ("M59 dry-run senza aggregati", "league_orchestrator.py",
     '        stampa("      " + sa.riga_dry_run(piano.lacune.aggregati))\n', "",
     [T + "::test_agg_dry_run_mostra_gli_aggregati_per_stagione"]),
    ("M60 catchup non calcola gli aggregati", "seasons_catchup.py",
     "    sa.attacca(sb, lacune, righe_per_k, stati, sa.adesso())\n", "",
     [T + "::test_agg_mancante_va_in_coda_ed_e_chiamato_poi_db_senza_buchi"]),
    ("M61 parziale aggregato creduto", "season_aggregates.py", '    if esito in ("errore", "parziale"):',
     '    if esito in ("errore",):',
     [T + "::test_agg_idempotente_nessuna_riga_doppia_e_delete_fallita_non_inserisce"]),
]

env = dict(os.environ, SUPABASE_URL="http://127.0.0.1:9", SUPABASE_SERVICE_ROLE_KEY="x", SUPABASE_KEY="x",
           API_FOOTBALL_KEY="x")
solo = sys.argv[1:]
esiti = []
for mid, f, vecchio, nuovo, tests in M:
    if solo and mid.split()[0] not in solo:
        continue
    orig = open(f, "rb").read()
    h0 = hashlib.sha256(orig).hexdigest()
    testo = orig.decode("utf-8")
    vecchio_n = vecchio.replace("\n", "\r\n") if "\r\n" in testo else vecchio
    nuovo_n = nuovo.replace("\n", "\r\n") if "\r\n" in testo else nuovo
    n = testo.count(vecchio_n)
    if n != 1:
        esiti.append((mid, f"BERSAGLIO NON UNICO ({n})"))
        continue
    try:
        open(f, "wb").write(testo.replace(vecchio_n, nuovo_n).encode("utf-8"))
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *tests],
                           capture_output=True, text=True, env=env, timeout=600)
        ultima = (r.stdout.strip().splitlines() or ["?"])[-1]
        esiti.append((mid, ("ROSSO" if r.returncode != 0 else "VERDE (!!)") + " | " + ultima))
    finally:
        open(f, "wb").write(orig)
        assert hashlib.sha256(open(f, "rb").read()).hexdigest() == h0, f"ripristino fallito {f}"
for mid, e in esiti:
    print(f"{mid:<40} {e}")
print("ripristino verificato (sha256) su tutti i file mutati")
