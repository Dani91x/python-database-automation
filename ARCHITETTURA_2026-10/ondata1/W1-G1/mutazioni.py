"""mutazioni.py - falsificazione dei test di W1-G1 (CANT par. 0 regola 5; brief comune par. 1.6).

Le mutazioni sono di tre famiglie:
  * ``M..`` - le 33 della consegna (5164d6e1), riscritte sul codice corretto dopo la revisione
    (stesso difetto iniettato, testo aggiornato dove il codice e' cambiato);
  * ``R1..R14`` - le 14 del revisore indipendente (``scratchpad/rev-w1g1/mut.py``), riportate
    sul codice corretto; R1, R7, R8, R12, R13 erano SOPRAVVISSUTE: ora le uccidono i test
    ``test_rev_R1/R7/R13`` (dal revisore), ``test_R8_*`` e ``test_pg_R12_*``;
  * ``N..`` - le nuove, una per ogni correzione (A1-A4, M1-M7, B1, B2, B7);
  * ``V01..V16`` - le 16 della seconda revisione (``scratchpad/rev_w1g1_2/mie_mutazioni.py``),
    stesso difetto, testo riportato sul codice della terza revisione dove e' cambiato (V04, V05,
    V15). V08, V09, V10 mutavano la tolleranza dell'orologio e il "+1 us", TOLTI dalla terza
    revisione (R1): sono sostituite da V08r/V09r/V10r, lo stesso rischio (scrittura del bot persa
    o versione che non sale) sul codice nuovo; le V si giudicano come il revisore, su TUTTI i
    test G1 (``-k "not sigkill"``);
  * ``T..`` - le nuove della terza revisione (R1 versione locale, R2 rientro/archiviazione,
    R3 guasto del codice, R4 disco guasto a processo vivo).
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
T3 = T + "test_g1_terza_revisione.py"
TUTTI = ["Betfair/nucleo/dati/tests", "-k", "not sigkill"]          # come il revisore: tutti i test G1

# (id, file, testo originale, testo mutato, test che devono diventare rossi, cosa prova)
MUTAZIONI = [
    # ------------------------------------------------------------ consegna (riscritte)
    ("M01", A, "                self._file_log[nome].flush()", "                pass",
     [TC + "::test_scrittore_ucciso_a_meta_zero_confermati_persi[0.0-conferma]"],
     "senza flush le righe di log confermate si perdono al crash"),
    ("M02", A, '        conn.execute("BEGIN IMMEDIATE")\n        try:\n            for v in voci:',
     "        try:\n            for v in voci:",
     [TA + "::test_riga_e_outbox_nella_stessa_transazione"], "riga e outbox fuori da una transazione comune"),
    ("M03", A, "                self._vseq[regime] += 1", "                self._vseq[regime] += 0",
     [T3 + "::test_R1_esito_vecchio_di_3_s_scritto_dopo_vince_con_updated_at_tale_e_quale"],
     "vseq locale che non sale: la scrittura nuova e' 'gia' vista' per il cloud e si perde"),
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
    ("M09", P, '"p_righe": [r for _, r in valide],',
     '"p_righe": [dict(r, **({"uid": __import__("uuid").uuid4().hex} if "uid" in r else {})) for _, r in valide],',
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
    ("M27", A, "        testo = testo_json(r)\n        ms = self._ora_ms()\n\n        def crea(",
     "        testo = testo_json({k: v for k, v in r.items() if v is not None})\n        ms = self._ora_ms()\n\n"
     "        def crea(",
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
    ("R13", A, "            self._in_attesa[(tabella, chiave)] = (n, testo)",
     "            if prec is None:\n                self._in_attesa[(tabella, chiave)] = (n, testo)",
     [TR + "::test_rev_R13_leggi_vede_l_ultima_scritta_prima_e_dopo_il_commit"],
     "leggi(): la vista in attesa tiene la prima scrittura, non l'ultima (riletta con R1)"),
    ("R14", P, '        if tipo in ("ok", "ignorata", "vecchia"):', '        if tipo in ("ok", "ignorata", "vecchia", "errore"):',
     [TP + "::test_check_rifiutato_va_in_dead_letter_visibile_le_altre_passano"],
     "esito errore per riga contato come consegnato"),
    # ------------------------------------------------------------ correzioni (nuove)
    ("N01", A, "            if rimasti and (errore_di_dato(self._ultimo_errore_unita) or tentativo + 1 >= "
               "TENTATIVI_PRIMA_DI_ISOLARE):",
     "            if False:",
     [TK + "::test_A2_versione_oltre_2_alla_63_isolata_negli_scarti_il_resto_prosegue"],
     "A2: nessun isolamento, lo scrittore si pianta su una voce"),
    ("N02", A, "            if errore_di_dato(exc):\n                try:\n                    self._veleno(v, exc)",
     "            if False:\n                try:\n                    self._veleno(v, exc)",
     [T3 + "::test_R3_scarti_nell_allarme_poi_archiviati_poi_tolti_dalla_pulizia"],
     "A2/R3: errore di dato provato non riconosciuto (voce sola: presa per guasto del codice, scrittore fermo)"),
    ("N03", A, "                    fine = inizio", "                    break",
     [TR + "::test_rev_D4_riga_troncata_oltre_1MiB_le_righe_buone_restano"], "A3: \\n cercato solo nell'ultimo MiB"),
    ("N04", P, "        if offset > dimensione or (firma is not None and firma_ora != firma):", "        if False:",
     [TR + "::test_rev_D5_marcatore_oltre_la_fine_torna_a_zero"], "M2: marcatore oltre la fine non azzerato"),
    ("N05", P, "        if offset > dimensione or (firma is not None and firma_ora != firma):",
     "        if offset > dimensione:",
     [TR + "::test_rev_D5b_file_sostituito_piu_lungo_del_marcatore"], "M2: file sostituito non riconosciuto"),
    ("N06", A, "        if riga is not None:\n            conn.execute(\"UPDATE righe SET json = ?, vseq = ?",
     "        if riga is not None and json.loads(riga[0]).get(\"updated_at\", \"\") > "
     "json.loads(v.testo).get(\"updated_at\", \"~\"):\n            return 0\n"
     "        if riga is not None:\n            conn.execute(\"UPDATE righe SET json = ?, vseq = ?",
     [TR + "::test_rev_D6b_orologio_indietro_di_3_s_vince_l_ultima_scritta"],
     "R1: l'orologio del bot torna a decidere (updated_at piu' vecchio scartato)"),
    ("N07", A, "        if riga is not None:\n            conn.execute(\"UPDATE righe SET json = ?, vseq = ?",
     "        if riga is not None and json.loads(riga[0]).get(\"rev\", -1) > json.loads(v.testo).get(\"rev\", 0):\n"
     "            return 0\n        if riga is not None:\n            conn.execute(\"UPDATE righe SET json = ?, vseq = ?",
     [TK + "::test_M3_versione_intera_vince_sempre_l_ultima_scritta_tale_e_quale"],
     "R1: la versione INTERA del bot torna a decidere"),
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
    ("N20", A, "(testo_json(_fondi(riga[0], json.loads(v.testo))), v.vseq, v.ms",
     "(v.testo, v.vseq, v.ms",
     [TR + "::test_rev_D7_coalescenza_fonde_le_colonne_degli_upsert_parziali"], "B2: riga locale sostituita, non fusa"),
    ("N21", SC, '    if int(conn.execute("PRAGMA auto_vacuum").fetchone()[0]) == 2:\n        return', "    return",
     [TR + "::test_rev_E3_auto_vacuum_effettivo_e_il_file_si_restringe"], "B1: auto_vacuum mai effettivo"),
    ("N22", P, "                conta.subtract(via)", "                pass",
     [TK + "::test_B7_stato_conta_la_coda_dei_log_in_modo_incrementale"], "B7: conteggio incrementale sbagliato"),
    ("N23", P, '            if tipo == "vecchia":                        # R1', "            if False:",
     [TP + "::test_riga_vecchia_tardiva_non_riporta_indietro_il_cloud"], "M3: riga scartata dal cloud senza evento"),
    ("N24", A, "PULIZIA_PEZZO = 1000", "PULIZIA_PEZZO = 10 ** 9",
     [TR + "::test_rev_E9_conferma_non_aspetta_una_pulizia_grossa"], "M7: pulizia in un pezzo solo"),
    # ------------------------------------------------------------ seconda revisione (V01-V16), su TUTTI i test G1
    ("V01", P, '                self._morta(valide[0][0], str(getattr(exc, "code", "") or "dato"), descr, giro, "dato")\n'
               '                return True', "                pass\n                return True", TUTTI,
     "A1: riga velenosa isolata ma non registrata in dead_letter (resta in outbox)"),
    ("V02", P, "            return self._invia(spec, op, seconda, giro, adesso)\n        self._in_linea()",
     "            return True\n        self._in_linea()", TUTTI, "A1: dopo la bisezione la seconda meta' non parte"),
    ("V03", A, "        if v.futuro is not None and not v.futuro.done():\n            v.futuro.set_exception(exc if exc is not "
               "None else RuntimeError(errore))\n        self._risolti([v])",
     "        if v.futuro is not None and not v.futuro.done():\n            v.futuro.set_exception(exc if exc is not "
     "None else RuntimeError(errore))", TUTTI, "A2: voce isolata mai risolta: conferma() non torna piu'"),
    ("V04", A, "            if errore_di_io(exc):\n                return sorted([*voci[i:]",
     "            if exc is not None:\n                return sorted([*voci[i:]", TUTTI,
     "A2: ogni errore trattato come I/O, la voce velenosa non si isola mai (riportata in _isola)"),
    ("V05", A, '                    conn.execute("DELETE FROM dead_letter WHERE id = ?", (i,))\n                    n += 1',
     "                    n += 1", TUTTI, "A4: rientro che non toglie la riga dalla dead_letter (riportata)"),
    ("V06", P, '    if c.startswith("22") or (c.startswith("23") and c != "23503"):',
     '    if c.startswith("22") or c.startswith("23"):', TUTTI, "A4: FK 23503 trattata come dato non valido"),
    ("V07", A, '"dato": 24 * 3_600_000', '"dato": 24 * 3_600_000_000', TUTTI, "A4: rientro dei dati non validi mai"),
    ("V08r", P, '"p_origine": origine, "p_versioni": versioni if origine is not None else None}',
     '"p_origine": origine, "p_versioni": [__import__("Betfair.nucleo.dati.schema_locale", fromlist=["x"])'
     '.rev_ordinabile(r["updated_at"]) if r.get("updated_at") else None for _, r in valide] '
     'if origine is not None else None}', TUTTI,
     "V08 (tolleranza 50 s) TOLTA da R1: qui la versione mandata al cloud torna a essere l'orologio del bot"),
    ("V09r", A, "                self._vseq[regime] += 1", "                self._vseq[regime] += 0", TUTTI,
     "V09 (versione uguale che non sale di 1 us) TOLTA da R1: qui la vseq locale non sale"),
    ("V10r", A, "            self._in_outbox(conn, tabella, \"upsert\", k, testo, ms, spec.coalesce, mia[0])",
     "            self._in_outbox(conn, tabella, \"upsert\", k, testo, ms, spec.coalesce, mia[0] - 1)", TUTTI,
     "V10 (interi con la tolleranza dei tempi) TOLTA da R1: qui la transizione esce con una versione vecchia"),
    ("V11", A, "AND p.seq < o.seq", "AND p.seq > o.seq", TUTTI, "M4: FIFO per chiave rovesciata"),
    ("V12", P, "                if v.chiave is not None and k in giro.chiavi_fallite:", "                if False:", TUTTI,
     "M4: voci successive di una chiave fallita non aspettano"),
    ("V13", A, "                    for v in scritture:\n                        f.write(testo_json(v.salvabile()) + \"\\n\")",
     "                    for v in scritture[:1]:\n                        f.write(testo_json(v.salvabile()) + \"\\n\")",
     TUTTI, "M6: salvataggio di una sola voce su N"),
    ("V14", A, "            if self._in_chiusura and tentativo >= TENTATIVI_PRIMA_DI_ISOLARE:",
     "            if tentativo >= TENTATIVI_PRIMA_DI_ISOLARE:", TUTTI,
     "M6: salvataggio+abbandono anche a processo vivo (SOPRAVVISSUTA alla seconda revisione: R4)"),
    ("V15", A, "            self._in_outbox(conn, tabella, \"upsert\", k, testo, ms, spec.coalesce, mia[0])\n            return True",
     "            return True", TUTTI, "F: transizione senza voce in outbox (riportata)"),
    ("V16", A, "            if d.get(col) != da:\n                return False", "            if d.get(col) is None:\n"
               "                return False", TUTTI, "F: claim che accetta qualunque stato di partenza"),
    # ------------------------------------------------------------ terza revisione (T..)
    ("T01", A, "                conn.execute(\"UPDATE meta SET valore = max(valore, ?) WHERE nome = 'vseq'\", (alta,))",
     "                conn.execute(\"SELECT ?\", (alta,))",
     [T3 + "::test_R1_vseq_persistita_mai_riusata_anche_dopo_pulizia_e_riapertura"],
     "R1: vseq non persistita: dopo la riapertura riparte da 1 e il cloud scarta le scritture nuove"),
    ("T02", A, "(testo_json(_fondi(riga[0], json.loads(v.testo))), v.vseq, v.ms, v.tabella, v.chiave)",
     "(testo_json(_fondi(riga[0], json.loads(v.testo))), None, v.ms, v.tabella, v.chiave)",
     [T3 + "::test_R2a_dl_stale_il_rientro_non_riporta_indietro_il_cloud"],
     "R1/R2a: la riga locale non porta la vseq dell'ultima scrittura (il rientro non sa di essere superato)"),
    ("T03", P, '"p_origine": origine, "p_versioni": versioni if origine is not None else None}',
     '"p_origine": origine, "p_versioni": None}',
     [T3 + "::test_R1_ritento_di_una_voce_gia_superata_della_stessa_origine_scartato"],
     "R1: il postino non manda le versioni (il ritento vecchio riporta indietro il cloud)"),
    ("T04", P, "        origine = next((self.archivio.origine(v.regime) for v, _ in valide",
     "        origine = next((__import__(\"uuid\").uuid4().hex for v, _ in valide",
     [T3 + "::test_R1_ritento_di_una_voce_gia_superata_della_stessa_origine_scartato"],
     "R1: origine diversa a ogni chiamata (la stessa origine non si riconosce)"),
    ("T05", T + "test_g1_finti.py", "        guardia = origine is not None and ver is not None and op != \"insert\"",
     "        guardia = False",
     [T3 + "::test_R1_due_processi_vince_l_ultima_arrivata"],
     "finto: la guardia per origine spenta (il finto deve diventare rosso come il vero, S01/S08)"),
    ("T06", A, '                    if vseq is not None and chiave is not None and op != "insert" and conn.execute(',
     "                    if False and conn.execute(",
     [T3 + "::test_R2a_dl_stale_il_rientro_non_riporta_indietro_il_cloud"],
     "R2a: il rientro non controlla la scrittura piu' nuova della stessa chiave"),
    ("T07", A, '"CASE WHEN ? = \'dato\' AND rientri >= ? THEN ? END, "',
     '"CASE WHEN ? = \'dato\' AND rientri >= ? AND 0 THEN ? END, "',
     [T3 + "::test_R2b_dato_archiviata_dopo_N_rientri_niente_allarme_niente_chiamate"],
     "R2b: la dead_letter di dato non si archivia mai (allarme eterno, chiamate eterne)"),
    ("T08", A, '"SELECT count(*) FROM dead_letter WHERE archiviata_ms IS NULL", ()',
     '"SELECT count(*) FROM dead_letter", ()',
     [T3 + "::test_R2a_dl_stale_il_rientro_non_riporta_indietro_il_cloud"],
     "R2b: le archiviate contano ancora nell'allarme"),
    ("T09", A, '"WHERE archiviata_ms IS NULL AND prossimo_rientro_ms <= ? ORDER BY id LIMIT ?"',
     '"WHERE prossimo_rientro_ms <= ? ORDER BY id LIMIT ?"',
     [T3 + "::test_R2b_dato_archiviata_dopo_N_rientri_niente_allarme_niente_chiamate"],
     "R2b: le archiviate rientrano lo stesso (costano chiamate)"),
    ("T10", A, '"DELETE FROM dead_letter WHERE id IN (SELECT id FROM dead_letter WHERE archiviata_ms IS NOT NULL "\n'
               '                    "AND archiviata_ms < ? LIMIT ?)"',
     '"DELETE FROM dead_letter WHERE id IN (SELECT id FROM dead_letter WHERE coalesce(archiviata_ms, 0) "\n'
     '                    "< ? LIMIT ?)"',
     [T3 + "::test_R2c_pulisci_toglie_le_archiviate_oltre_la_conservazione_mai_le_attive"],
     "R2c: la pulizia toglie anche le dead_letter ATTIVE"),
    ("T11", A, "        limite_arch = adesso - int(CONSERVA_ARCHIVIATE_GIORNI * 86_400_000)", "        limite_arch = 0",
     [T3 + "::test_R2c_pulisci_toglie_le_archiviate_oltre_la_conservazione_mai_le_attive"],
     "R2c: le archiviate non si tolgono mai (crescita senza limite)"),
    ("T12", P, "                                    archiviate=self.archivio.conteggio_archiviate(),",
     "                                    archiviate=0,",
     [T3 + "::test_R2a_dl_stale_il_rientro_non_riporta_indietro_il_cloud"], "R2b: stato() non conta le archiviate"),
    ("T13", A, "    return isinstance(exc, (UnicodeEncodeError, UnicodeDecodeError, OverflowError,",
     "    return isinstance(exc, (TypeError, UnicodeEncodeError, UnicodeDecodeError, OverflowError,",
     [T3 + "::test_R3_errore_di_codice_su_tutte_le_voci_resta_in_coda_critical_una_volta_al_minuto"],
     "R3: errore_di_dato di nuovo largo (un TypeError su tutte le voci le scarta tutte)"),
    ("T14", A, "        if passate == 0:\n            self._guasto_codice(", "        if False:\n            self._guasto_codice(",
     [T3 + "::test_R3_errore_di_codice_su_tutte_le_voci_resta_in_coda_critical_una_volta_al_minuto"],
     "R3: guasto del codice trattato come voci velenose (tutte negli scarti)"),
    ("T15", A, "        if adesso - self._critico_ultimo >= CRITICO_OGNI_S:", "        if True:",
     [T3 + "::test_R3_errore_di_codice_su_tutte_le_voci_resta_in_coda_critical_una_volta_al_minuto"],
     "R3: CRITICAL a ogni giro (non una volta al minuto)"),
    ("T16", A, "        passate = 1 if altre_passate else 0", "        passate = 0",
     [T3 + "::test_R3_errore_di_codice_su_una_sola_voce_e_lo_scarto_le_altre_passano"],
     "R3: la voce tenuta dietro una sospetta scambiata per guasto del codice (scrittore fermo)"),
    ("T17", A, "            if adesso - int(s.get(\"ms\") or 0) >= SCARTI_IN_ALLARME_MS:", "            if False:",
     [T3 + "::test_R3_scarti_nell_allarme_poi_archiviati_poi_tolti_dalla_pulizia"],
     "R3: gli scarti restano nell'allarme per sempre"),
    ("T18", A, '            tenere = [x for x in linee if int(json.loads(x).get("ms") or 0) >= limite_ms]',
     "            tenere = linee",
     [T3 + "::test_R3_scarti_nell_allarme_poi_archiviati_poi_tolti_dalla_pulizia"],
     "R3: il file degli scarti cresce senza limite"),
    ("T19", A, "                self.guasto = None\n                    self.guasto_codice = None",
     "                self.guasto = None",
     [T3 + "::test_R3_errore_di_codice_su_tutte_le_voci_resta_in_coda_critical_una_volta_al_minuto"],
     "R3: l'allarme del guasto del codice non si spegne alla ripresa"),
]

MUTAZIONI_SQL = [
    ("S01", SQL, "                IF FOUND AND v_prec > v_ver THEN\n                    v_esito := 'vecchia';",
     "                IF false THEN\n                    v_esito := 'vecchia';",
     [TG + "::test_pg_versione_per_origine_mai_dall_orologio"], "R1: voce vecchia della stessa origine applicata"),
    ("S02", SQL, "        EXCEPTION WHEN OTHERS THEN\n            GET STACKED DIAGNOSTICS",
     "        EXCEPTION WHEN division_by_zero THEN\n            GET STACKED DIAGNOSTICS",
     [TG + "::test_pg_check_dead_letter_e_23503_poi_padre"], "nessun esito per riga"),
    ("S03", SQL, "'ON CONFLICT (%s) DO NOTHING', p_tabella, v_lista, v_sel, p_tabella, v_conf);\n                ELSIF p_op = 'upsert'",
     "'', p_tabella, v_lista, v_sel, p_tabella);\n                ELSIF p_op = 'upsert'",
     [TG + "::test_pg_consegna_idempotente_e_colonne_vere"], "insert senza ON CONFLICT"),
    ("R11", SQL, "            IF NOT (p_conflitto <@ v_chiavi) THEN\n                RAISE EXCEPTION 'manca la chiave naturale %', "
                 "p_conflitto USING ERRCODE = '22023';\n            END IF;", "",
     [TG + "::test_pg_R11_riga_senza_chiave_naturale_rifiutata"], "SQL: riga senza chiave naturale accettata"),
    ("R12", SQL, "                IF v_guardia THEN\n                    -- nella STESSA",
     "                IF false THEN\n                    -- nella STESSA",
     [TG + "::test_pg_R12_patch_con_versione_piu_vecchia_della_stessa_origine_non_tocca_il_cloud"],
     "R1: versione applicata mai registrata (patch vecchia della stessa origine passa)"),
    ("S04", SQL, "                ELSIF FOUND AND v_prec = v_ver THEN\n                    v_esito := 'ignorata';\n",
     "", [TG + "::test_pg_versione_per_origine_mai_dall_orologio"],
     "R1: la STESSA voce ritentata si riapplica (ignorata non detta)"),
    ("S06", SQL, "WHERE pv.tabella = p_tabella AND pv.chiave = v_k AND pv.origine = p_origine FOR UPDATE;",
     "WHERE pv.tabella = p_tabella AND pv.chiave = v_k FOR UPDATE;",
     [TG + "::test_pg_versione_per_origine_mai_dall_orologio"],
     "R1: versioni confrontate fra origini DIVERSE (l'ultima arrivata non vince piu')"),
    ("S07", SQL, "WHERE tabella = p_tabella AND aggiornato < now() - interval '90 days' LIMIT 100));",
     "WHERE tabella = p_tabella AND aggiornato < clock_timestamp() LIMIT 100));",
     [TG + "::test_pg_versione_per_origine_mai_dall_orologio"],
     "R1: versioni tolte subito (nessuna memoria della stessa origine)"),
    ("S08", SQL, "            v_guardia := p_origine IS NOT NULL AND v_ver IS NOT NULL AND p_op <> 'insert';",
     "            v_guardia := false;",
     [TG + "::test_pg_R2a_dl_stale_il_rientro_non_riporta_indietro_il_cloud"],
     "R2: il rientro di una dead_letter vecchia riporta indietro il cloud (seconda difesa spenta)"),
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
