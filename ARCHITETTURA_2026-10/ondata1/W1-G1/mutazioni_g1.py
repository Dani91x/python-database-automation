"""mutazioni_g1.py - falsificazione dei test di W1-G1 (CANT par. 0 regola 5; brief comune par. 1.6).

Per ogni mutazione: sha256 del file, UNA sostituzione esatta (deve comparire una volta sola),
i test indicati devono diventare ROSSI, poi il file torna identico (sha256 confrontato).
Le mutazioni della migrazione SQL si applicano al PostgreSQL usa-e-getta (``G1_PG_PSQL``),
si provano con ``test_g1_pg_reale.py`` e si annullano rilanciando la migrazione originale.

Uso: python mutazioni_g1.py [--sql]     (dalla radice del repo)
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

# (id, file, testo originale, testo mutato, test che devono diventare rossi, cosa prova)
MUTAZIONI = [
    ("M01", D + "archivio.py", "                self._file_log[nome].flush()", "                pass",
     [T + "test_g1_crash.py::test_scrittore_ucciso_a_meta_zero_confermati_persi[0.0-conferma]"],
     "senza flush le righe di log confermate si perdono al crash (prova deterministica)"),
    ("M02", D + "archivio.py", 'conn.execute("BEGIN IMMEDIATE")\n                    aperte.append',
     'aperte.append',
     [T + "test_g1_archivio.py::test_riga_e_outbox_nella_stessa_transazione"],
     "riga e outbox fuori da una transazione comune"),
    ("M03", D + "archivio.py", "WHERE righe.rev IS NULL OR excluded.rev IS NULL OR excluded.rev > righe.rev\")",
     "WHERE 1\")",
     [T + "test_g1_archivio.py::test_leggi_vede_subito_e_versione_mai_indietro"],
     "versione locale che torna indietro"),
    ("M04", D + "archivio.py",
     "            conn.execute(\"DELETE FROM outbox WHERE tabella = ? AND chiave = ? AND op = 'upsert'\", (tabella, chiave))",
     "            pass", [T + "test_g1_archivio.py::test_coalescenza_tiene_solo_l_ultima_versione"],
     "coalescenza spenta"),
    ("M05", D + "archivio.py", "            if d.get(col) != da:\n                return False", "            pass",
     [T + "test_g1_archivio.py::test_transizione_claim_atomico_una_volta_sola"], "claim non atomico"),
    ("M06", D + "archivio.py", "                f.seek(taglio)\n                f.truncate()", "                pass",
     [T + "test_g1_archivio.py::test_riga_jsonl_troncata_scartata_e_segnalata"], "riga troncata non tagliata"),
    ("M07", D + "archivio.py", "AND EXISTS (SELECT 1 FROM riconciliazioni r", "AND 1 OR EXISTS (SELECT 1 FROM riconciliazioni r",
     [T + "test_g1_archivio.py::test_pulizia_solo_consegnato_e_riconciliato"], "pulizia senza riconciliazione"),
    ("M08", D + "archivio.py", "        col_t = self._colonne_tempo.get(spec.nome)", "        col_t = None",
     [T + "test_g1_postino.py::test_consegna_log_e_stato_stesse_colonne"],
     "istante dell'evento non timbrato (consegna tardiva sposterebbe ts)"),
    ("M09", D + "postino.py", '"p_righe": [json.loads(v.testo) for v in pezzo]}',
     '"p_righe": [dict(json.loads(v.testo), **({"uid": __import__("uuid").uuid4().hex} if "uid" in v.testo else {})) '
     'for v in pezzo]}',
     [T + "test_g1_postino.py::test_ritento_dopo_risposta_persa_zero_duplicati",
      T + "test_g1_crash.py::test_postino_ucciso_fra_risposta_e_conferma_zero_duplicati"],
     "uid generato alla consegna invece che alla scrittura -> il ritento duplica (G par. 5 n.2)"),
    ("M10", D + "postino.py", '    return "rete" if classifica_guasto_rete(exc) is not None else "bloccante"',
     '    return "bloccante"', [T + "test_g1_postino.py::test_cloud_fermo_coda_cresce_allarme_e_ripresa"],
     "cloud fermo non riconosciuto come offline"),
    ("M11", D + "postino.py", "    if tentativi <= 0:\n        return 0.0", "    if True:\n        return 0.0",
     [T + "test_g1_postino.py::test_cloud_fermo_coda_cresce_allarme_e_ripresa"], "nessuna attesa crescente"),
    ("M12", D + "postino.py", "        if codice in TRANSITORI_RIGA and v.tentativi + 1 < self._tetto_riga:",
     "        if v.tentativi + 1 < self._tetto_riga:",
     [T + "test_g1_postino.py::test_check_rifiutato_va_in_dead_letter_visibile_le_altre_passano"],
     "CHECK ritentato invece di dead_letter (G par. 5 n.5)"),
    ("M13", D + "postino.py", 'TRANSITORI_RIGA = frozenset({"23503", ', 'TRANSITORI_RIGA = frozenset({',
     [T + "test_g1_postino.py::test_23503_transitorio_poi_consegnato_quando_arriva_il_padre"],
     "23503 trattato come definitivo (R06)"),
    ("M14", D + "postino.py", "key=lambda t: profondita[t])", "key=lambda t: -profondita[t])",
     [T + "test_g1_postino.py::test_padre_prima_del_figlio_nello_stesso_giro"], "figlio prima del padre"),
    ("M15", D + "postino.py", 'return f"{tabella}_ombra" if self.ombra else tabella', "return tabella",
     [T + "test_g1_postino.py::test_ombra_scrive_solo_sulle_tabelle_ombra"], "ombra che scrive sulle tabelle vere (R21)"),
    ("M16", D + "postino.py", "            self._rimanda(v, giro, self._bloccate[spec.nome][0], descr, contare=False)",
     '            self._morta(v, "x", descr, giro)',
     [T + "test_g1_postino.py::test_rpc_assente_tabella_bloccata_mai_dead_letter"],
     "errore della chiamata (RPC assente) che uccide le righe"),
    ("M17", D + "postino.py", "        if giro.interrotto:\n            return                                          # offline",
     "        if False:\n            return                                          # offline",
     [T + "test_g1_postino.py::test_cloud_fermo_coda_cresce_allarme_e_ripresa"],
     "offline che fa avanzare i file di log (perdita silenziosa)"),
    ("M18", D + "postino.py", "        if dim > self._tetto_disco and not self.ripiego_diretto:",
     "        if False:", [T + "test_g1_postino.py::test_tetto_di_disco_segnale_di_ripiego_mai_perdita"],
     "nessun segnale al tetto di disco"),
    ("M19", D + "postino.py", "esito.consegnate + esito.dead_letter >= max_righe",
     "esito.consegnate + esito.morte >= max_righe",
     [T + "test_g1_postino.py::test_thread_del_postino_drena_da_solo"], "il difetto vero trovato dalla misura"),
    ("M20", D + "postino.py", "            nuovo = max(1, len(pezzo) // 2)", "            nuovo = len(pezzo)",
     [T + "test_g1_postino.py::test_57014_dimezza_il_blocco"], "57014 senza riduzione del blocco"),
    ("M21", D + "postino.py", '        if codice in BLOCCANTI_RIGA:', '        if False:',
     [T + "test_g1_postino.py::test_permesso_negato_per_riga_blocca_non_uccide"], "permesso negato che uccide le righe"),
    ("M22", D + "riconcilia.py", "if k not in cloud and k not in in_coda)", "if k not in cloud)",
     [T + "test_g1_postino.py::test_riconcilia_non_conta_come_mancante_cio_che_e_in_coda"],
     "riga in viaggio contata come persa"),
    ("M23", D + "riconcilia.py", "and cloud[k] is not None and locali[k] != cloud[k])",
     "and cloud[k] is not None and False)", [T + "test_g1_postino.py::test_riconcilia_mancanti_in_piu_diverse"],
     "versioni diverse non viste"),
    ("M24", D + "percorso.py", "    if _dentro(base, RADICE_REPO):\n        raise", "    if False:\n        raise",
     [T + "test_g1_archivio.py::test_percorso_mai_dentro_il_repo"], "archivio dentro il repo"),
    ("M25", D + "schema_locale.py", "    if partenza > VERSIONE_SCHEMA:", "    if False:",
     [T + "test_g1_archivio.py::test_schema_creato_versionato_e_rifiuto_del_piu_nuovo"],
     "schema piu' nuovo toccato da codice vecchio"),
    ("M26", D + "archivio.py", "            if c in COLONNE_UID and r.get(c) is None:", "            if False:",
     [T + "test_g1_archivio.py::test_tre_regimi_due_file_e_sincronia"], "uid non generato nel punto di scrittura"),
    ("M27", D + "archivio.py",
     '        testo = json.dumps(r, ensure_ascii=False, separators=(",", ":"), default=str)\n        ms = self._ora_ms()\n        n = ',
     '        testo = json.dumps({k: v for k, v in r.items() if v is not None}, ensure_ascii=False, separators=(",", ":"), '
     'default=str)\n        ms = self._ora_ms()\n        n = ',
     [T + "test_g1_parita.py"], "riga alterata nel trasporto (i None tolti): non e' piu' quella di oggi"),
    ("M28", D + "postino.py", "        quota = max(1, -(-max_righe // 3))", "        quota = 0",
     [T + "test_g1_postino.py::test_nessuna_fonte_affama_le_altre"], "una fonte affama le altre (log mai consegnati)"),
    ("M29", D + "postino.py", "            while b\"\\n\" not in dati and len(dati) >= LETTURA_LOG_BYTE:",
     "            while False:", [T + "test_g1_postino.py::test_riga_di_log_piu_lunga_del_blocco_di_lettura"],
     "riga piu' lunga del blocco: il file si blocca per sempre"),
    ("M30", D + "postino.py", '        giorno = (ora - timedelta(days=1)).strftime("%Y-%m-%d")',
     '        giorno = ora.strftime("%Y-%m-%d")',
     [T + "test_g1_postino.py::test_riconciliazione_notturna_automatica_abilita_la_pulizia"],
     "riconciliazione notturna del giorno sbagliato (ancora aperto)"),
]

MUTAZIONI_SQL = [
    ("S01", SQL, "v_sql := v_sql || format(' WHERE t.%1$I IS NULL OR EXCLUDED.%1$I > t.%1$I', p_rev);",
     "NULL;", [T + "test_g1_pg_reale.py::test_pg_versione_mai_indietro"],
     "upsert senza versione: la riga vecchia riporta indietro il cloud (R02)"),
    ("S02", SQL, "        EXCEPTION WHEN OTHERS THEN\n            GET STACKED DIAGNOSTICS",
     "        EXCEPTION WHEN division_by_zero THEN\n            GET STACKED DIAGNOSTICS",
     [T + "test_g1_pg_reale.py::test_pg_check_dead_letter_e_23503_poi_padre"],
     "una riga guasta fa fallire tutto il blocco (niente esito per riga)"),
    ("S03", SQL, "'ON CONFLICT (%s) DO NOTHING', p_tabella, v_lista, v_sel, p_tabella, v_conf);\n            ELSIF p_op = 'upsert'",
     "'', p_tabella, v_lista, v_sel, p_tabella);\n            ELSIF p_op = 'upsert'",
     [T + "test_g1_pg_reale.py::test_pg_consegna_idempotente_e_colonne_vere"],
     "insert senza ON CONFLICT: il ritento non e' idempotente"),
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def pytest_rc(test: list[str], env: dict) -> int:
    r = subprocess.run([sys.executable, "-m", "pytest", *test, "-q", "-x", "-p", "no:cacheprovider"], cwd=RADICE,
                       capture_output=True, text=True, timeout=600, env=env)
    return r.returncode


def applica_sql(percorso: Path) -> None:
    args = os.environ["G1_PG_PSQL"].split()
    r = subprocess.run(["psql", *args, "-X", "-q", "-v", "ON_ERROR_STOP=1", "-f", str(percorso)],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr


def esegui(mutazioni: list, sql: bool) -> int:
    rossi = 0
    for mid, rel, vecchio, nuovo, test, cosa in mutazioni:
        f = RADICE / rel
        prima = sha(f)
        originale = f.read_bytes()
        testo = originale.decode("utf-8")
        assert testo.count(vecchio) == 1, f"{mid}: il testo da mutare compare {testo.count(vecchio)} volte"
        f.write_bytes(testo.replace(vecchio, nuovo).encode("utf-8"))
        t0 = time.time()
        try:
            if sql:
                applica_sql(f)
            rc = pytest_rc(test, dict(os.environ))
        finally:
            f.write_bytes(originale)
            if sql:
                applica_sql(f)
        dopo = sha(f)
        esito = "ROSSO" if rc != 0 else "VERDE (mutazione SOPRAVVISSUTA)"
        rossi += rc != 0
        print(f"{mid} {esito:32s} {time.time() - t0:5.1f}s sha256 {'uguale' if dopo == prima else 'DIVERSO'} "
              f"{prima[:16]} | {cosa}")
        assert dopo == prima, f"{mid}: file non ripristinato"
    return rossi


if __name__ == "__main__":
    solo = sys.argv[sys.argv.index("--solo") + 1].split(",") if "--solo" in sys.argv else None
    if solo:
        MUTAZIONI = [m for m in MUTAZIONI if m[0] in solo]
        MUTAZIONI_SQL = [m for m in MUTAZIONI_SQL if m[0] in solo]
    tutte = list(MUTAZIONI)
    print(f"# mutazioni Python: {len(tutte)}")
    rossi = esegui(tutte, False)
    totale = len(tutte)
    if "--sql" in sys.argv:
        print(f"# mutazioni SQL (PostgreSQL usa-e-getta): {len(MUTAZIONI_SQL)}")
        rossi += esegui(MUTAZIONI_SQL, True)
        totale += len(MUTAZIONI_SQL)
    print(f"# ROSSE {rossi}/{totale}")
    sys.exit(0 if rossi == totale else 1)
