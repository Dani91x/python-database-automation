# Falsificazione del catchup P4 - stagioni mai caricate + riserva dinamica (25/09/2026): mutazione minima -> test rossi ->
# ripristino verificato (sha256). Stesso motore di mutazioni_backfill_automatico.py.
# Uso (dalla radice del repo): python AUDIT_2026-09-25/mutazioni_catchup_p4.py [Q1 Q2 ...]
import hashlib
import os
import subprocess
import sys

T = "test_catchup_p4_2026_09_25.py"
R = "test_riserva_dinamica_2026_09_25.py"
M = [
    # (id, file, vecchio, nuovo, test attesi rossi)
    ("Q1 P4 anche se P1-P3 fermate", "seasons_catchup.py",
     "    if ris.fermato_per:\n        ris.p4_non_partita = f\"P1-P3",
     "    if False:\n        ris.p4_non_partita = f\"P1-P3",
     [T + "::test_p4_non_parte_se_p1_p3_si_sono_fermate"]),
    ("Q2 P4 prima di P1-P3", "seasons_catchup.py",
     "    # 3) lavoro\n",
     "    esegui_p4(sb, client, quota, ris, coperture, stati, lacune, prioritarie, env, oggi, stampa,\n"
     "              deve_fermarsi, concorrenza, lambda: False, max_min)\n    # 3) lavoro\n",
     [T + "::test_p4_parte_dopo_p1_p3_carica_la_stagione_e_il_db_resta_senza_buchi"]),
    ("Q3 pavimento ignorato nel lavoro", "seasons_catchup.py",
     "    q4 = QuotaConPavimento(quota, pavimento)\n", "    q4 = QuotaConPavimento(quota, 0)\n",
     [T + "::test_p4_stima_superata_si_ferma_sopra_il_pavimento_e_la_p3_chiude_senza_doppioni"]),
    ("Q4 pavimento ignorato alla partenza", "seasons_catchup.py",
     "        if quota.margine() < pavimento:\n", "        if False:\n",
     [T + "::test_p4_non_parte_sotto_il_pavimento_e_il_pavimento_viene_da_env"]),
    ("Q5 pavimento da env ignorato", "seasons_catchup.py",
     '_env_int("CATCHUP_P4_MARGINE_MINIMO", P4_PAVIMENTO_DEFAULT, env)', "P4_PAVIMENTO_DEFAULT",
     [T + "::test_p4_pavimento_da_env"]),
    ("Q6 ordine per id", "seasons_catchup.py",
     "out.sort(key=lambda c: (c.fascia, -c.importanza, -c.chiave[1], c.chiave[0]))",
     "out.sort(key=lambda c: (c.chiave[0], c.chiave[1]))",
     [T + "::test_p4_ordine_bot_poi_ml_poi_importanza_poi_stagione_piu_recente"]),
    ("Q7 importanza ignorata", "seasons_catchup.py",
     "out.sort(key=lambda c: (c.fascia, -c.importanza, -c.chiave[1], c.chiave[0]))",
     "out.sort(key=lambda c: (c.fascia, -c.chiave[1], c.chiave[0]))",
     [T + "::test_p4_ordine_bot_poi_ml_poi_importanza_poi_stagione_piu_recente"]),
    ("Q8 stagione piu' vecchia prima", "seasons_catchup.py",
     "out.sort(key=lambda c: (c.fascia, -c.importanza, -c.chiave[1], c.chiave[0]))",
     "out.sort(key=lambda c: (c.fascia, -c.importanza, c.chiave[1], c.chiave[0]))",
     [T + "::test_p4_ordine_bot_poi_ml_poi_importanza_poi_stagione_piu_recente"]),
    ("Q9 fascia ML ignorata", "seasons_catchup.py",
     "fascia = 0 if k[0] in prioritarie else (1 if k[0] in leghe_ml else 2)",
     "fascia = 0 if k[0] in prioritarie else 2",
     [T + "::test_p4_ordine_bot_poi_ml_poi_importanza_poi_stagione_piu_recente",
      T + "::test_referto_p4_quante_restano_e_stima_giorni"]),
    ("Q10 senza eventi non escluse", "seasons_catchup.py",
     '        if not r.get("fixtures_events") and not anche_senza_eventi:\n', "        if False:\n",
     [T + "::test_p4_stagione_senza_eventi_esclusa_salvo_richiesta_esplicita",
      T + "::test_p4_ordine_bot_poi_ml_poi_importanza_poi_stagione_piu_recente"]),
    ("Q11 richiesta esplicita ignorata", "seasons_catchup.py",
     '_env_si("CATCHUP_P4_ANCHE_SENZA_EVENTI", env)', "False",
     [T + "::test_p4_stagione_senza_eventi_esclusa_salvo_richiesta_esplicita"]),
    ("Q12 spezzoni riaccesi", "seasons_catchup.py",
     '    return "non_entra", costo\n', '    return "procedo", costo\n',
     [T + "::test_p4_solo_per_intero_se_non_entra_nessuna_chiamata",
      T + "::test_p4_col_pavimento_di_default_la_stessa_stagione_non_entra_per_intero"]),
    ("Q12b la prima che non entra ferma la coda", "seasons_catchup.py",
     "                ris.p4_non_entrate.append(k)            # per intero o niente: prova la successiva\n"
     "                continue\n",
     "                ris.p4_non_entrate.append(k)            # per intero o niente: prova la successiva\n"
     "                break\n",
     [T + "::test_p4_salta_quella_che_non_entra_e_carica_intera_la_successiva"]),
    ("Q13 /fixtures contata tardi", "season_backfill.py",
     "            if hasattr(quota, \"aggiungi_chiamate_esterne\"):\n                quota.aggiungi_chiamate_esterne(1)\n",
     "",
     [T + "::test_p4_stima_superata_si_ferma_sopra_il_pavimento_e_la_p3_chiude_senza_doppioni"]),
    ("Q14 memoria /fixtures vuota non scritta", "seasons_catchup.py",
     "                _segna_tentativo_p4(sb, piano, es, c.stato_prec, oggi)\n", "                pass\n",
     [T + "::test_p4_fixtures_senza_partite_ricordata_ritentata_dopo_7_giorni_poi_dichiarata"]),
    ("Q15 attesa 7 gg ignorata", "seasons_catchup.py",
     "(oggi - ultimo).days < P4_GIORNI_TRA_TENTATIVI", "(oggi - ultimo).days < 0",
     [T + "::test_p4_fixtures_senza_partite_ricordata_ritentata_dopo_7_giorni_poi_dichiarata"]),
    ("Q16 tentativi infiniti", "seasons_catchup.py",
     ">= P4_MAX_TENTATIVI_VUOTI:", ">= 99:",
     [T + "::test_p4_fixtures_senza_partite_ricordata_ritentata_dopo_7_giorni_poi_dichiarata"]),
    ("Q17 memoria persa alla riscrittura", "season_gaps.py",
     '        **({"mai_caricata": prec["mai_caricata"]} if prec.get("mai_caricata") else {}),\n', "",
     [T + "::test_p4_fixtures_senza_partite_ricordata_ritentata_dopo_7_giorni_poi_dichiarata"]),
    ("Q18 matches_count non letto", "season_gaps.py",
     '               "matches_count:stats_json->fixtures->>matches_count,"\n', "",
     [T + "::test_p4_fixtures_senza_partite_ricordata_ritentata_dopo_7_giorni_poi_dichiarata",
      T + "::test_p4_stagione_senza_eventi_esclusa_salvo_richiesta_esplicita"]),
    ("Q20 stato vecchio a zero chiamato", "seasons_catchup.py",
     "            if not piano.serve_fixtures:\n", "            if False:\n",
     [T + "::test_p4_stato_vecchio_a_zero_ma_partite_in_db_zero_chiamate_e_passa_alla_p3"]),
    ("Q21 mai caricata come buco P3", "seasons_catchup.py",
     "        if not viva and lac.partite_totali == 0:\n            continue", "        if False:\n            continue",
     [T + "::test_p4_stagione_mai_caricata_non_e_un_buco_p3_aggregati_solo_dopo_le_partite"]),
    ("Q22 referto cieco", "seasons_catchup.py",
     "    referto_p4(ris, stampa, margine_medio)\n", "",
     [T + "::test_referto_p4_quante_restano_e_stima_giorni",
      T + "::test_p4_parte_dopo_p1_p3_carica_la_stagione_e_il_db_resta_senza_buchi"]),
    ("Q23 stima giorni senza pavimento", "seasons_catchup.py",
     "~{math.ceil(costo_rest / (media - pav))} giorni", "~{math.ceil(costo_rest / media)} giorni",
     [T + "::test_referto_p4_quante_restano_e_stima_giorni"]),
    ("Q24 consumo giornaliero cumulato", "api_quota.py",
     "cumulati[i] - cumulati[i + 1])", "cumulati[i])",
     [T + "::test_consumo_giorni_log_e_margine_medio", T + "::test_referto_p4_quante_restano_e_stima_giorni"]),
    ("Q25 media senza riserva", "api_quota.py",
     "max(0, limit_day - riserva - n)", "max(0, limit_day - n)",
     [T + "::test_consumo_giorni_log_e_margine_medio", T + "::test_referto_p4_quante_restano_e_stima_giorni"]),
    ("Q26 log illeggibile fa crollare la run", "seasons_catchup.py",
     "        except Exception as e:                               # e' una stima, non un errore della run\n"
     "            errore = f\"{type(e).__name__}: {e}\"\n",
     "        except ZeroDivisionError as e:\n            errore = f\"{type(e).__name__}: {e}\"\n",
     [T + "::test_referto_p4_log_illeggibile_stima_non_disponibile_senza_errore"]),
    ("Q27 dry-run senza etichetta", "league_orchestrator.py",
     "{_etichetta_mai_caricata(piano, row, oggi)}{decisione}", "{decisione}",
     [T + "::test_dry_run_mostra_mai_caricata_con_il_costo"]),
    ("Q28 quote contate nella stima", "season_backfill.py",
     "    if flags.get(\"odds\") and (vecchia or not sg.e_corrente_o_recente(coverage_row, oggi)):\n        n -= 1\n",
     "",
     [T + "::test_p4_ordine_bot_poi_ml_poi_importanza_poi_stagione_piu_recente",
      T + "::test_dry_run_mostra_mai_caricata_con_il_costo"]),
    ("Q29 pavimento sottratto due volte", "api_quota.py",
     "        return self.quota.margine() - self.pavimento\n", "        return self.quota.margine() - 2 * self.pavimento\n",
     [T + "::test_quota_con_pavimento", T + "::test_p4_pavimento_da_env"]),
    ("Q30 P4 ignora le action concorrenti", "seasons_catchup.py",
     "        motivo = None if concorrenza is None else concorrenza.in_corso(forza=True)\n", "        motivo = None\n",
     [T + "::test_p4_non_parte_se_un_action_concorrente_e_in_corso"]),
    # --- stagioni 'current' con fine passata: verifica mirata all'API (decisione utente 25/09) ---
    ("V1 esito API ignorato", "seasons_catchup.py", '        r["current"] = valore                       #',
     '        pass                       #',
     [T + "::test_current_sospetta_verificata_e_trattata_come_dice_l_api"]),
    ("V2 memoria settimanale ignorata", "seasons_catchup.py", "(oggi - quando).days < VERIFICA_CURRENT_GIORNI",
     "(oggi - quando).days < 0",
     [T + "::test_current_sospetta_verificata_e_trattata_come_dice_l_api",
      T + "::test_current_confermata_dall_api_resta_viva_e_si_riverifica_dopo_7_giorni"]),
    ("V3 tetto ignorato", "seasons_catchup.py", 'if conti["chiamate"] >= tetto or quota.margine() < 1:',
     "if quota.margine() < 1:", [T + "::test_verifica_current_nel_budget_e_col_tetto"]),
    ("V4 budget ignorato", "seasons_catchup.py", 'if conti["chiamate"] >= tetto or quota.margine() < 1:',
     'if conti["chiamate"] >= tetto:', [T + "::test_verifica_current_nel_budget_e_col_tetto"]),
    ("V5 esito non salvato", "seasons_catchup.py", "            _salva_verifica_current(sb, k, esito)\n",
     "", [T + "::test_current_confermata_dall_api_resta_viva_e_si_riverifica_dopo_7_giorni"]),
    ("V6 euristica 30 gg rimessa", "seasons_catchup.py", "    return not sg.e_corrente_o_recente(row, oggi)\n",
     "    return not sg.e_corrente_o_recente(row, oggi) or current_sospetta(row, oggi)\n",
     [T + "::test_p4_criteri_di_ingresso",
      T + "::test_current_confermata_dall_api_resta_viva_e_si_riverifica_dopo_7_giorni"]),
    ("V7 errore API creduto", "seasons_catchup.py", "            if valore_api is None:\n",
     "            if False:\n", [T + "::test_verifica_current_errore_api_resta_come_nel_db"]),
    ("V8 partite reali della lega ignorate", "seasons_catchup.py",
     "partite = max(sbk.STIMA_PARTITE_STAGIONE_VUOTA, partite_lega.get(k[0], 0))",
     "partite = sbk.STIMA_PARTITE_STAGIONE_VUOTA", [T + "::test_p4_stima_con_le_partite_reali_della_lega"]),
    # --- riserva dinamica e fine giornata UTC (seguito del coordinatore, 25/09) ---
    ("R1 riserva residua sempre", "api_quota.py", "        if finite is True:\n", "        if True:\n",
     [R + "::test_prima_del_completamento_riserva_piena_3000", R + "::test_token_assente_riserva_piena_con_avviso"]),
    ("R2 riserva mai scende", "api_quota.py", "            return self.riserva_residua\n",
     "            return self.riserva\n",
     [R + "::test_dopo_il_completamento_riserva_residua_300_e_nota_una_volta"]),
    ("R3 run di ieri contano", "seasons_catchup.py",
     "params={\"status\": \"success\", \"created\": f\">={dal.strftime('%Y-%m-%dT%H:%M:%SZ')}\",",
     "params={\"status\": \"success\",",
     [R + "::test_run_di_ieri_in_ritardo_dopo_mezzanotte_non_conta"]),
    ("R4 anche le fallite contano", "seasons_catchup.py", "params={\"status\": \"success\", \"created\"",
     "params={\"status\": \"completed\", \"created\"",
     [R + "::test_action_fallita_oggi_riserva_piena"]),
    ("R5 action in corso ignorate", "seasons_catchup.py",
     "                    if attive:                                   # in corso o in coda: non ha finito\n",
     "                    if False:\n",
     [R + "::test_action_in_corso_riserva_piena_anche_se_una_run_e_riuscita"]),
    ("R6 errore GitHub creduto", "seasons_catchup.py",
     "                if getattr(r, \"status_code\", 0) != 200:\n                    return None\n                if int(",
     "                if False:\n                    return None\n                if int(",
     [R + "::test_github_in_errore_solo_sulle_run_riuscite_non_leggibile"]),
    ("R7 niente memoria del giorno", "seasons_catchup.py", "            self._completate_giorno = giorno\n",
     "            pass\n", [R + "::test_completate_resta_vero_nel_giorno_e_si_rilegge_il_giorno_dopo"]),
    ("R8 fine giornata spenta", "seasons_catchup.py", "if h >= ora_stop else None", "if h >= 99 else None",
     [R + "::test_dalle_23_utc_non_parte_nessuna_lega_stagione", R + "::test_p4_non_parte_dalle_23"]),
    ("R9 ora di stop da env ignorata", "seasons_catchup.py",
     "_env_int(\"CATCHUP_ORA_STOP_UTC\", ORA_STOP_UTC_DEFAULT, env)", "ORA_STOP_UTC_DEFAULT",
     [R + "::test_ora_di_stop_da_env"]),
    ("R10 fine giornata non a fine partita", "seasons_catchup.py",
     "        if fine_giornata():\n            return fine_giornata()\n", "",
     [R + "::test_lega_stagione_in_corso_si_ferma_a_fine_partita_alle_23"]),
    ("R11 P4 ignora la fine giornata", "seasons_catchup.py",
     "        motivo = motivo or fine_giornata()\n        if motivo:\n            ris.p4_non_partita",
     "        if motivo:\n            ris.p4_non_partita",
     [R + "::test_p4_non_parte_dalle_23"]),
    ("R12 capacita' con la riserva piena", "api_quota.py",
     "        return self.stato.limit_day - self.stato.riserva\n", "        return self.stato.limit_day - self.riserva\n",
     [R + "::test_dopo_il_completamento_riserva_residua_300_e_nota_una_volta"]),
    ("R13 residua sopra la piena", "api_quota.py",
     "    return valore if massimo is None else min(valore, massimo)\n", "    return valore\n",
     [R + "::test_residua_da_env_e_mai_sopra_la_piena"]),
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
