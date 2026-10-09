"""mutazioni.py - falsificazione dei test di W1-G1 (CANT par. 0 regola 5; brief comune par. 1.6).

Le mutazioni sono di tre famiglie:
  * ``M..`` - le 33 della consegna (5164d6e1), riscritte sul codice corretto dopo la revisione
    (stesso difetto iniettato, testo aggiornato dove il codice e' cambiato);
  * ``R1..R14`` - le 14 del revisore indipendente (``scratchpad/rev-w1g1/mut.py``), riportate
    sul codice corretto; R1, R7, R8, R12, R13 erano SOPRAVVISSUTE: ora le uccidono i test
    ``test_rev_R1/R7/R13`` (dal revisore), ``test_R8_*`` e ``test_pg_R12_*``;
  * ``N..`` - le nuove, una per ogni correzione (A1-A4, M1-M7, B1, B2, B7).
Per ogni mutazione: sha256 del file, UNA sostituzione esatta (deve comparire una volta sola),
i test indicati devono diventare ROSSI, poi il file torna identico (sha256 confrontato).
Le mutazioni della migrazione SQL (``S..``, R11, R12) si applicano al PostgreSQL usa-e-getta
(``G1_PG_PSQL``) e si annullano rilanciando la migrazione originale.

Uso (dalla radice del repo): python ARCHITETTURA_2026-10/ondata1/W1-G1/mutazioni.py [--sql] [--solo ID,ID] [--secco]
  --secco : controlla solo che ogni testo da mutare compaia una volta (nessun test lanciato)
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path

RADICE = Path(__file__).resolve().parents[3]
D = "Betfair/nucleo/dati/"
T = D + "tests/"
SQL = "migrations/architettura_uid_ombra_2026-10-09.sql"
A, P, RC, PE, SC = D + "archivio.py", D + "postino.py", D + "riconcilia.py", D + "percorso.py", D + "schema_locale.py"
TA, TP, TC = T + "test_g1_archivio.py", T + "test_g1_postino.py", T + "test_g1_crash.py"
TR, TK, TG = T + "test_g1_revisione.py", T + "test_g1_correzioni.py", T + "test_g1_pg_reale.py"

# (id, file, testo originale, testo mutato, test che devono diventare rossi, cosa prova)
MUTAZIONI = [
    # ------------------------------------------------------------ consegna (riscritte)
    ("M01", A, "                self._file_log[nome].flush()", "                pass",
     [TC + "::test_scrittore_ucciso_a_meta_zero_confermati_persi[0.0-conferma]"],
     "senza flush le righe di log confermate si perdono al crash"),
    ("M02", A, '        conn.execute("BEGIN IMMEDIATE")\n        try:\n            for v in voci:',
     "        try:\n            for v in voci:",
     [TA + "::test_riga_e_outbox_nella_stessa_transazione"], "riga e outbox fuori da una transazione comune"),
    ("M03", A, "        if v.rev is None or prec is None or v.rev > prec:\n            return v.rev",
     "        if True:\n            return v.rev",
     [TA + "::test_leggi_vede_subito_e_versione_mai_indietro"], "versione locale che torna indietro"),
    ("M04", A, "                conn.executemany(\"DELETE FROM outbox WHERE seq = ?\", [(s,) for s, _ in prec])",
     "                pass", [TA + "::test_coalescenza_tiene_solo_l_ultima_versione"], "coalescenza spenta"),
    ("M05", A, "            if d.get(col) != da:\n                return False", "            pass",
     [TA + "::test_transizione_claim_atomico_una_volta_sola"], "claim non atomico"),
    ("M06", A, "                f.truncate(taglio)", "                pass",
     [TA + "::test_riga_jsonl_troncata_scartata_e_segnalata"], "riga troncata non tagliata"),
    ("M07", A, "            if any(self.riconciliazione(t, giorno) != \"ok\" for t in tabelle):\n                continue",
     "            if False:\n                continue",
     [TA + "::test_pulizia_solo_consegnato_e_riconciliato"], "pulizia dei log senza riconciliazione"),
    ("M08", A, "        col_t = self._colonne_tempo.get(spec.nome)", "        col_t = None",
     [TP + "::test_consegna_log_e_stato_stesse_colonne"], "istante dell'evento non timbrato"),
    ("M09", P, '"p_righe": [r for _, r in valide]}',
     '"p_righe": [dict(r, **({"uid": __import__("uuid").uuid4().hex} if "uid" in r else {})) for _, r in valide]}',
     [TP + "::test_ritento_dopo_risposta_persa_zero_duplicati",
      TC + "::test_postino_ucciso_fra_risposta_e_conferma_zero_duplicati"],
     "uid generato alla consegna invece che alla scrittura -> il ritento duplica (G par. 5 n.2)"),
    ("M10", P, '    if classifica_guasto_rete(exc) is not None:\n        return "rete"',
     '    if False:\n        return "rete"',
     [TP + "::test_cloud_fermo_coda_cresce_allarme_e_ripresa"], "cloud fermo non riconosciuto come offline"),
    ("M11", P, "    if tentativi <= 0:\n        return 0.0", "    if True:\n        return 0.0",
     [TP + "::test_cloud_fermo_coda_cresce_allarme_e_ripresa"], "nessuna attesa crescente"),
    ("M12", P, '    if c.startswith("22") or (c.startswith("23") and c != "23503"):\n        return "dato"',
     '    if False:\n        return "dato"',
     [TP + "::test_check_rifiutato_va_in_dead_letter_visibile_le_altre_passano"],
     "CHECK ritentato invece di dead_letter (G par. 5 n.5)"),
    ("M13", P, '(c.startswith("23") and c != "23503")', 'c.startswith("23")',
     [TP + "::test_23503_transitorio_poi_consegnato_quando_arriva_il_padre"], "23503 trattato come definitivo (R06)"),
    ("M14", P, "key=lambda t: profondita[t])", "key=lambda t: -profondita[t])",
     [TP + "::test_padre_prima_del_figlio_nello_stesso_giro"], "figlio prima del padre"),
    ("M15", P, 'return f"{tabella}_ombra" if self.ombra else tabella', "return tabella",
     [TP + "::test_ombra_scrive_solo_sulle_tabelle_ombra"], "ombra che scrive sulle tabelle vere (R21)"),
    ("M16", P, "        for v in pezzo:\n            self._rimanda(v, giro, self._bloccate[spec.nome][0], descr, contare=False)",
     '        for v in pezzo:\n            self._morta(v, "x", descr, giro, "dato")',
     [TP + "::test_rpc_assente_tabella_bloccata_mai_dead_letter"], "RPC assente che uccide le righe"),
    ("M17", P, "        if giro.interrotto:\n            return                                          # offline",
     "        if False:\n            return                                          # offline",
     [TP + "::test_cloud_fermo_coda_cresce_allarme_e_ripresa"], "offline che fa avanzare i log"),
    ("M18", P, "        if dim > self._tetto_disco and not self.ripiego_diretto:", "        if False:",
     [TP + "::test_tetto_di_disco_segnale_di_ripiego_mai_perdita"], "nessun segnale al tetto di disco"),
    ("M19", P, "esito.consegnate + esito.dead_letter >= max_righe", "esito.consegnate + esito.morte >= max_righe",
     [TP + "::test_thread_del_postino_drena_da_solo"], "il difetto vero trovato dalla misura"),
    ("M20", P, "            nuovo = max(1, len(pezzo) // 2)", "            nuovo = len(pezzo)",
     [TP + "::test_57014_dimezza_il_blocco"], "57014 senza riduzione del blocco"),
    ("M21", P, '    if c.startswith("42") or c.startswith("0A") or c == CODICE_INTESTAZIONE:\n        return "schema"',
     '    if False:\n        return "schema"',
     [TP + "::test_permesso_negato_per_riga_blocca_non_uccide",
      TR + "::test_rev_D9b_colonna_sconosciuta_blocca_la_tabella_niente_dead_letter"],
     "permessi / colonna sconosciuta che uccidono le righe (A4)"),
    ("M22", RC, "if k not in cloud and k not in in_coda)", "if k not in cloud)",
     [TP + "::test_riconcilia_non_conta_come_mancante_cio_che_e_in_coda"], "riga in viaggio contata come persa"),
    ("M23", RC, "and cloud[k] is not None and locali[k] != cloud[k])", "and cloud[k] is not None and False)",
     [TP + "::test_riconcilia_mancanti_in_piu_diverse"], "versioni diverse non viste"),
    ("M24", PE, "    if _dentro(base, RADICE_REPO):\n        raise", "    if False:\n        raise",
     [TA + "::test_percorso_mai_dentro_il_repo"], "archivio dentro il repo"),
    ("M25", SC, "    if partenza > VERSIONE_SCHEMA:", "    if False:",
     [TA + "::test_schema_creato_versionato_e_rifiuto_del_piu_nuovo"], "schema piu' nuovo toccato da codice vecchio"),
    ("M26", A, "            if c in COLONNE_UID and r.get(c) is None:", "            if False:",
     [TA + "::test_tre_regimi_due_file_e_sincronia"], "uid non generato nel punto di scrittura"),
    ("M27", A, "        testo = testo_json(r)\n        ms = self._ora_ms()\n        n = self._prossimo_n()",
     "        testo = testo_json({k: v for k, v in r.items() if v is not None})\n        ms = self._ora_ms()\n"
     "        n = self._prossimo_n()",
     [T + "test_g1_parita.py"], "riga alterata nel trasporto (i None tolti)"),
    ("M28", P, "        quota = max(1, -(-max_righe // 3))", "        quota = 0",
     [TP + "::test_nessuna_fonte_affama_le_altre"], "una fonte affama le altre"),
    ("M29", P, '            while b"\\n" not in dati and len(dati) >= LETTURA_LOG_BYTE:', "            while False:",
     [TP + "::test_riga_di_log_piu_lunga_del_blocco_di_lettura"], "riga piu' lunga del blocco: file bloccato"),
    ("M30", P, '        giorno = (ora - timedelta(days=1)).strftime("%Y-%m-%d")', '        giorno = ora.strftime("%Y-%m-%d")',
     [TP + "::test_riconciliazione_notturna_automatica_abilita_la_pulizia"], "riconciliazione del giorno sbagliato"),
    # ------------------------------------------------------------ revisore (R1-R14) sul codice corretto
    ("R1", A, "            if self.offset_log(percorso.name) < percorso.stat().st_size:\n                continue",
     "            if False:\n                continue", [TR + "::test_rev_R1_pulizia_non_toglie_un_file_di_log_non_consegnato"],
     "pulizia dei JSONL non ancora consegnati"),
    ("R2", A, '"SELECT 1 FROM outbox o WHERE o.tabella = righe.tabella AND o.chiave = righe.chiave) AND EXISTS ("',
     '"SELECT 1 FROM outbox o WHERE 0 AND o.tabella = righe.tabella AND o.chiave = righe.chiave) AND EXISTS ("',
     [TA + "::test_pulizia_solo_consegnato_e_riconciliato"], "pulizia di righe ancora in outbox"),
    ("R3", A, "\"SELECT seq, json FROM outbox WHERE tabella = ? AND chiave = ? AND op = 'upsert' \"\n"
              "                                \"ORDER BY seq\", (tabella, chiave))",
     "\"SELECT seq, json FROM outbox WHERE tabella = ? AND op = 'upsert' \"\n"
     "                                \"ORDER BY seq\", (tabella,))",
     [TA + "::test_coalescenza_tiene_solo_l_ultima_versione"], "coalescenza che fonde chiavi diverse"),
    ("R4", A, "            for tabella, op, chiave, testo, ms, tentativi, prossimo, errore in ritenti:",
     "            for tabella, op, chiave, testo, ms, tentativi, prossimo, errore in []:",
     [TP + "::test_23503_transitorio_poi_consegnato_quando_arriva_il_padre"], "log ritentati persi (marcatore avanza)"),
    ("R5", P, "            ok = giro.ok_seq.get(regime, [])",
     "            ok = giro.ok_seq.get(regime, []) + [r[0] for r in giro.rimandate.get(regime, [])]",
     [TP + "::test_rpc_assente_tabella_bloccata_mai_dead_letter"], "rimandate cancellate come consegnate"),
    ("R6", A, "            while self._in_volo and min(self._in_volo) <= obiettivo:", "            while False:",
     [TC + "::test_scrittore_ucciso_a_meta_zero_confermati_persi[0.0-conferma]"], "conferma() non e' una barriera"),
    ("R7", P, '            if not linea.endswith(b"\\n") or len(voci) >= quante:', "            if len(voci) >= quante:",
     [TR + "::test_rev_R7_riga_di_log_a_meta_scrittura_non_si_salta_ne_si_perde"],
     "lettura di righe di log a meta' scrittura"),
    ("R8", A, "        except BaseException:\n            self._riavvolgi_log(posizioni)\n            raise",
     "        except BaseException:\n            raise",
     [TK + "::test_R8_unita_di_log_fallita_dopo_il_flush_riavvolta_nessun_doppione"],
     "unita' di log fallita: file non riavvolto (doppioni)"),
    ("R9", PE, "        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)", "        pass",
     [TA + "::test_lucchetto_esclusivo_fra_processi_e_liberato_dal_crash"], "nessun lucchetto"),
    ("R10", P, "voci.append(_Voce(tabella, op, chiave, testo_json(riga), ms, 0, file=percorso.name, seq=fine))",
     "voci.append(_Voce(tabella, op, chiave, testo_json(riga), ms, 0, file=percorso.name, seq=pos))",
     [TP + "::test_consegna_log_e_stato_stesse_colonne"], "marcatore fermo all'inizio dell'ultima riga"),
    ("R13", A, "            if rev is not None and prec[2] is not None and _stantia(rev, prec[2], valore_rev):\n"
               "                return",
     "            if False:\n                return",
     [TR + "::test_rev_R13_leggi_non_regredisce_con_versione_stantia"], "leggi(): la riga in attesa stantia vince"),
    ("R14", P, '        if tipo in ("ok", "ignorata", "vecchia"):', '        if tipo in ("ok", "ignorata", "vecchia", "errore"):',
     [TP + "::test_check_rifiutato_va_in_dead_letter_visibile_le_altre_passano"],
     "esito errore per riga contato come consegnato"),
    # ------------------------------------------------------------ correzioni (nuove)
    ("N01", A, "            if rimasti and (errore_di_dato(self._ultimo_errore_unita) or tentativo + 1 >= "
               "TENTATIVI_PRIMA_DI_ISOLARE):",
     "            if False:",
     [TK + "::test_A2_versione_oltre_2_alla_63_isolata_negli_scarti_il_resto_prosegue"],
     "A2: nessun isolamento, lo scrittore si pianta su una voce"),
    ("N02", A, "            if exc is not None and errore_di_io(exc):\n                return rimasti",
     "            if exc is not None:\n                return rimasti",
     [TK + "::test_A2_chiave_con_surrogato_isolata_denaro_e_vivo_non_si_fermano"],
     "A2: errore di dato trattato come I/O (ritento eterno)"),
    ("N03", A, "                    fine = inizio", "                    break",
     [TR + "::test_rev_D4_riga_troncata_oltre_1MiB_le_righe_buone_restano"], "A3: \\n cercato solo nell'ultimo MiB"),
    ("N04", P, "        if offset > dimensione or (firma is not None and firma_ora != firma):", "        if False:",
     [TR + "::test_rev_D5_marcatore_oltre_la_fine_torna_a_zero"], "M2: marcatore oltre la fine non azzerato"),
    ("N05", P, "        if offset > dimensione or (firma is not None and firma_ora != firma):",
     "        if offset > dimensione:",
     [TR + "::test_rev_D5b_file_sostituito_piu_lungo_del_marcatore"], "M2: file sostituito non riconosciuto"),
    ("N06", A, "    return prec - rev > TOLLERANZA_OROLOGIO_US", "    return True",
     [TR + "::test_rev_D6b_orologio_indietro_di_3_s_vince_l_ultima_scritta"], "M3: nessuna tolleranza dell'orologio"),
    ("N07", A, "    if rev >= prec:\n        return False", "    if rev > prec:\n        return False",
     [TK + "::test_M3_versione_intera_uguale_vince_l_ultima_minore_e_stantia"], "M3: versione uguale scartata"),
    ("N08", A, '"AND p.prossimo_ms > ?) ORDER BY o.seq LIMIT ?"', '"AND p.prossimo_ms > ? AND 0) ORDER BY o.seq LIMIT ?"',
     [TK + "::test_M4_voce_successiva_non_supera_quella_in_attesa_nei_giri_dopo"], "M4: outbox senza FIFO per chiave"),
    ("N09", P, "                if len(pezzo) < n and (v.chiave is None or k not in chiavi):",
     "                if len(pezzo) < n:",
     [TR + "::test_rev_D11b_upsert_vecchio_ritentato_non_supera_il_nuovo"], "M4: due voci della stessa chiave in una chiamata"),
    ("N10", P, "                if v.chiave is not None and k in giro.chiavi_fallite:", "                if False:",
     [TR + "::test_rev_D11_patch_aspetta_l_upsert_fallito"], "M4: patch che supera l'upsert fallito"),
    ("N11", P, "            if motivo is not None:                      # A1", "            if False:",
     [TR + "::test_rev_D1_riga_con_nan_isolata_le_altre_passano"], "A1: nessuna validazione prima della chiamata"),
    ("N12", P, '            if classifica_errore_chiamata(exc) != "dati":', "            if True:",
     [TK + "::test_A1_carattere_nullo_bisezione_isola_la_riga_sola"], "A1: nessuna bisezione"),
    ("N13", P, "                self.archivio.rientro_dead_letter(adesso)", "                pass",
     [TK + "::test_A4_dead_letter_transitoria_rientra_da_sola_dopo_15_minuti",
      TK + "::test_A4_dead_letter_di_dato_rientra_dopo_24_ore_e_passa_se_il_vincolo_e_cambiato"],
     "A4: nessun rientro automatico"),
    ("N14", P, "TETTO_TENTATIVI_RIGA = 360", "TETTO_TENTATIVI_RIGA = 12",
     [TR + "::test_rev_D10_padre_di_altro_processo_in_ritardo_il_figlio_aspetta"], "A4: tetto di ~10 min (D10)"),
    ("N15", P, '                    self._morta(v, "registro", f"tabella non registrata: {exc}"[:300], giro, "registro")',
     "                    pass",
     [TR + "::test_rev_D3_log_di_tabella_non_registrata_va_in_dead_letter"], "M1: voce sconosciuta saltata"),
    ("N16", A, "            if futuro.cancel():", "            if False:",
     [TR + "::test_rev_M5_claim_scaduto_prima_di_partire_non_avviene"], "M5: lavoro scaduto eseguito lo stesso"),
    ("N17", A, "                falliti.extend(gruppo)\n                continue", "                return voci",
     [TR + "::test_rev_D8_claim_riuscito_riferito_vero_anche_se_il_secondo_commit_fallisce",
      TK + "::test_R8_commit_del_vivo_fallito_dopo_il_log_nessun_doppione"],
     "M5: unita' non indipendenti (claim rieseguito dopo il commit)"),
    ("N18", A, "                self._salva(rimasti, exc)", "                self._salva([], exc)",
     [TR + "::test_rev_E10_chiusura_con_disco_guasto_le_righe_accettate_rientrano"], "M6: righe accettate perse alla chiusura"),
    ("N19", A, "                for _, j in prec:\n                    fusa.update(json.loads(j))",
     "                for _, j in []:\n                    fusa.update(json.loads(j))",
     [TR + "::test_rev_D7_coalescenza_fonde_le_colonne_degli_upsert_parziali"], "B2: coalescenza che sostituisce"),
    ("N20", A, "(testo_json(_fondi(riga[0], nuova)), rev if rev is not None else riga[1]",
     "(testo_json(nuova), rev if rev is not None else riga[1]",
     [TR + "::test_rev_D7_coalescenza_fonde_le_colonne_degli_upsert_parziali"], "B2: riga locale sostituita, non fusa"),
    ("N21", SC, '    if int(conn.execute("PRAGMA auto_vacuum").fetchone()[0]) == 2:\n        return', "    return",
     [TR + "::test_rev_E3_auto_vacuum_effettivo_e_il_file_si_restringe"], "B1: auto_vacuum mai effettivo"),
    ("N22", P, "                conta.subtract(via)", "                pass",
     [TK + "::test_B7_stato_conta_la_coda_dei_log_in_modo_incrementale"], "B7: conteggio incrementale sbagliato"),
    ("N23", P, '            if tipo == "vecchia":                        # M3', "            if False:",
     [TP + "::test_riga_vecchia_tardiva_non_riporta_indietro_il_cloud"], "M3: riga scartata dal cloud senza evento"),
    ("N24", A, "PULIZIA_PEZZO = 1000", "PULIZIA_PEZZO = 10 ** 9",
     [TR + "::test_rev_E9_conferma_non_aspetta_una_pulizia_grossa"], "M7: pulizia in un pezzo solo"),
]

MUTAZIONI_SQL = [
    ("S01", SQL, "v_sql := v_sql || format(' WHERE t.%1$I IS NULL OR EXCLUDED.%1$I > t.%1$I', p_rev);",
     "NULL;", [TG + "::test_pg_versione_mai_indietro"], "upsert senza versione (R02)"),
    ("S02", SQL, "        EXCEPTION WHEN OTHERS THEN\n            GET STACKED DIAGNOSTICS",
     "        EXCEPTION WHEN division_by_zero THEN\n            GET STACKED DIAGNOSTICS",
     [TG + "::test_pg_check_dead_letter_e_23503_poi_padre"], "nessun esito per riga"),
    ("S03", SQL, "'ON CONFLICT (%s) DO NOTHING', p_tabella, v_lista, v_sel, p_tabella, v_conf);\n            ELSIF p_op = 'upsert'",
     "'', p_tabella, v_lista, v_sel, p_tabella);\n            ELSIF p_op = 'upsert'",
     [TG + "::test_pg_consegna_idempotente_e_colonne_vere"], "insert senza ON CONFLICT"),
    ("R11", SQL, "            IF NOT (p_conflitto <@ v_chiavi) THEN\n                RAISE EXCEPTION 'manca la chiave naturale %', "
                 "p_conflitto USING ERRCODE = '22023';\n            END IF;", "",
     [TG + "::test_pg_R11_riga_senza_chiave_naturale_rifiutata"], "SQL: riga senza chiave naturale accettata"),
    ("R12", SQL, "                    v_sql := v_sql || format(' AND (t.%1$I IS NULL OR r.%1$I > t.%1$I)', p_rev);",
     "                    NULL;", [TG + "::test_pg_R12_patch_con_versione_piu_vecchia_non_tocca_il_cloud"],
     "SQL: patch senza guardia di versione"),
    ("S04", SQL, "CASE WHEN v_n > 0 THEN 'ok' WHEN v_vecchia THEN 'vecchia' ELSE 'ignorata' END",
     "CASE WHEN v_n > 0 THEN 'ok' ELSE 'ignorata' END", [TG + "::test_pg_versione_mai_indietro"],
     "SQL: riga scartata per versione non detta"),
    ("S05", SQL, "'postino_consegna: operazione non ammessa: %', p_op USING ERRCODE = 'GP001'",
     "'postino_consegna: operazione non ammessa: %', p_op USING ERRCODE = '22023'",
     [TG + "::test_pg_intestazione_ha_il_suo_sqlstate"], "SQL: errore d'intestazione scambiato per dato"),
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def pytest_rc(test: list[str]) -> int:
    r = subprocess.run([sys.executable, "-m", "pytest", *test, "-q", "-x", "-p", "no:cacheprovider"], cwd=RADICE,
                       capture_output=True, text=True, timeout=900, env=dict(os.environ))
    return r.returncode


def applica_sql(percorso: Path) -> None:
    args = os.environ["G1_PG_PSQL"].split()
    r = subprocess.run(["psql", *args, "-X", "-q", "-v", "ON_ERROR_STOP=1", "-f", str(percorso)],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr


def esegui(mutazioni: list, sql: bool, secco: bool) -> int:
    rossi = 0
    for mid, rel, vecchio, nuovo, test, cosa in mutazioni:
        f = RADICE / rel
        prima = sha(f)
        originale = f.read_bytes()
        testo = originale.decode("utf-8")
        assert testo.count(vecchio) == 1, f"{mid}: il testo da mutare compare {testo.count(vecchio)} volte"
        if secco:
            rossi += 1
            continue
        f.write_bytes(testo.replace(vecchio, nuovo).encode("utf-8"))
        t0 = time.time()
        try:
            if sql:
                applica_sql(f)
            rc = pytest_rc(test)
        finally:
            f.write_bytes(originale)
            if sql:
                applica_sql(f)
        dopo = sha(f)
        esito = "ROSSO" if rc != 0 else "VERDE (mutazione SOPRAVVISSUTA)"
        rossi += rc != 0
        print(f"{mid:4s} {esito:32s} {time.time() - t0:5.1f}s sha256 {'uguale' if dopo == prima else 'DIVERSO'} "
              f"{prima[:16]} | {cosa}", flush=True)
        assert dopo == prima, f"{mid}: file non ripristinato"
    return rossi


if __name__ == "__main__":
    solo = sys.argv[sys.argv.index("--solo") + 1].split(",") if "--solo" in sys.argv else None
    secco = "--secco" in sys.argv
    py = [m for m in MUTAZIONI if not solo or m[0] in solo]
    sq = [m for m in MUTAZIONI_SQL if not solo or m[0] in solo] if ("--sql" in sys.argv or secco) else []
    print(f"# mutazioni Python: {len(py)}", flush=True)
    rossi = esegui(py, False, secco)
    if sq:
        print(f"# mutazioni SQL (PostgreSQL usa-e-getta): {len(sq)}", flush=True)
        rossi += esegui(sq, not secco, secco)
    totale = len(py) + len(sq)
    print(f"# {'TESTI UNICI' if secco else 'ROSSE'} {rossi}/{totale}")
    sys.exit(0 if rossi == totale else 1)
