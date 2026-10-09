# Betfair/monitor - COSA FA (schema 04 par. 2.4)

1. **Scopo**: misurare l'app senza cambiarla. Contatori in memoria in ogni servizio Python (CPU, RAM, richieste al
   DB per tabella, REST Betfair per metodo, transazioni, tratti in ms del percorso dato -> ordine), una riga ogni
   30 s per servizio in `monitor_metrics`, un referto giornaliero in `AUDIT_MONITOR/`. Tappa T0A (05 par. 1).
2. **Entrate**: messaggi grezzi dello stream (`osserva_stream`), richieste httpx del PostgREST (hook del client),
   risposte requests dell'APIClient Betfair (hook della sessione), record di log che le librerie GIA' scrivono
   (`flumine.baseflumine`, `flumine.execution`, `betfairlightweight.streaming.listener`, `flumine.streams`,
   ERROR/CRITICAL alla radice), marche dei punti d'aggancio (`marca_ladder`, `marca_emesso`, `ricevuto_ms`,
   `drenate`, `tratto("diario_fsync_ms")`).
3. **Uscite**: riga `monitor_metrics` (colonne della migrazione `migrations/monitor_metrics_2026-10-09.sql`,
   `metriche` jsonb v=1: `processo`, `contatori`, `tratti`, `valori`, ogni 10 minuti `sistema`); copia locale
   `_logs/monitor/<giorno>/<servizio>.jsonl`; referto `AUDIT_MONITOR/REFERTO_SALUTE_<giorno>.md|.json`; marche
   additive `rx` (raw), `ts_pub_ms`/`pt` (ladder del canale), `emesso_ms` (params della coda), `ricevuto_ms`
   (LocalRequest). Nessuno le legge per decidere.
4. **Dipendenze ammesse**: libreria standard, `psutil` facoltativo (requirements: 7.2.2; senza si degrada e lo si
   dichiara), `db_client` solo nello scrittore e nel referto (import pigro). MAI flumine, betfairlightweight o
   moduli dei bot all'import: importare `Betfair.monitor` non cambia niente nel processo.
5. **Funzionalita' coperte**: C-053 (tempi d'ordine: `emesso_ms` per `decisione_ms`, lettura con
   `leggi_tempi_ordine` nel referto), G-045 (vitalita' dei raccoglitori: RPC `monitor_vitalita_raccoglitori`).
   Test: `tests/test_monitor_salute_2026_10_09.py`, `tests/test_monitor_agganci_2026_10_09.py`,
   `tests/test_monitor_referto_2026_10_09.py`; frontend `src/lib/salute.test.ts`, `src/pages/Salute.test.tsx`.
6. **Interruttore**: `MONITOR_SALUTE=0|1`, di serie 0. Acceso solo se =1 E il `main` del servizio chiama
   `sonde.avvia(...)` E nel processo non c'e' il banco (`Betfair.stream.backtest*`) E non gira pytest. Spento =
   nessun campo, nessuna scrittura, nessun thread, nessun handler. `MONITOR_SALUTE_SEC` = intervallo (30).
7. **Come si sostituisce**: `sonde.py` (API degli agganci) + colonne di `monitor_metrics`; far passare i tre file
   di test qui sopra e il confronto delle colonne con la migrazione.
8. **Come si prova da solo**: `python -m pytest Betfair/monitor -q -p no:cacheprovider` (client Supabase e
   APIClient VERI con il trasporto sostituito; LiveSession, recorder, canale e Diario veri).
9. **Misure**: costo del giro dello scrittore (`monitor_giro_ms`); 2 richieste/min al DB per servizio (la riga);
   righe ~1-2 KB (~30-55 MB/giorno con ~10 servizi; conservazione: `monitor_metrics_pulizia(7)`, 7 giorni).
10. **PSB par. 6/7**: 6.8 (referto riproducibile: stesse righe = stessi byte, `--salva-righe`/`--righe`), 7 n.27
    (finti con chiavi e tipi del vero), falsificazione (mutazioni nel referto di T0A), paper e live mai sommati
    (`esecuzione_live`/`esecuzione_paper` separati, transazioni solo dal Betfair vero), calcio e tennis mai
    mischiati (colonna `sport`).
