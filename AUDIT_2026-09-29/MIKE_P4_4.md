# MIKE P4 - blocco 4 (correzioni di verifica del coordinatore)

Patch: `AUDIT_2026-09-29/MIKE_P4_4.patch`, SOPRA `MIKE_P4_3.patch`, su master `6cc91a0`.
Catena 3+4 verificata su indice temporaneo partito da `6cc91a0`: risultato = worktree. Nessun commit.
Worktree riallineato a `6cc91a0` (`git reset --hard` nel SOLO mio worktree, copie di sicurezza in scratchpad
`p4/prima_blocco4/`), poi applicato P4_3.

## A. Due zone rimesse identiche a master (`service.py`)
- `_LIVE_VOLATILI`: `"published_at", "published_ts", "feed_age_s", "scanner_age_s",` e il commento
  `# il book e tutto cio' che ne discende ...` di nuovo su righe separate.
- dizionario `live` di `_run_event`: `"feed_age_s"` e `"scanner_age_s"` di nuovo su due righe.
- Causa: nel blocco 3 una rimozione (chiavi `score_age_s`/`punteggio_assente` tolte per il contratto UI)
  si e' portata via anche l'a capo. Controllo: `git diff origin/master -- Betfair/mike/service.py` non
  mostra piu' quelle zone (0 righe con `feed_age_s` / `il book e tutto`).

## B. Avviso del punteggio assente dopo 10 s
- `_episodio_dato_assente(..., "punteggio_assente", ...)`: ritardo da `0.0` a `_DATO_ASSENTE_AVVISO_S`.
  Cambia SOLO quando si scrive l'avviso: lo snapshot porta `goals=None` dal primo giro (asserito nei test).
- Test del blocco 3 aggiornato (era scritto per l'avviso immediato, stesso file del blocco 3):
  `test_punteggio_assente_in_gioco_...` -> `test_punteggio_assente_per_12_s_si_dichiara_una_volta_e_quando_torna`;
  nuovo `test_punteggio_assente_per_5_s_al_fischio_nessun_avviso` (nessun avviso, nessuna riga di ritorno).

## C. Test mancanti (codice invariato), nuovo file `test_mike_p4_blocco4_2026_09_29.py`
| Mutazione del coordinatore | Test | Esito con la mutazione |
|---|---|---|
| W4c sorveglianza tolta nel ramo «snapshot non costruibile» | `test_snapshot_non_costruibile_la_lay_appoggiata_si_segue_lo_stesso` | rosso |
| W5b `if not ok0 and _retry_settle_rows` -> False | `test_righe_non_scritte_la_partita_non_diventa_settled_e_si_ritenta` (4 giri SETTLING + `settle_rows_retry`, al 5o SETTLED + `settle_rows_failed` critico) | rosso |
| W11 `_FEED_KO` fuori da `_CACHE_DI_PROCESSO` | `test_azzera_cache_di_processo_chiude_l_episodio_di_lettura_fallita` | rosso (anche un test del blocco 2) |
| W13 `if mode == "paper"` -> False in `_sorveglia_senza_dati` | `test_paper_riga_assente_l_esito_del_runner_si_legge` (runner finto, protocollo vero) | rosso |
| W14 posizione di conto tolta in `_sorveglia_senza_dati` | `test_live_riga_assente_la_chiusura_fuori_app_si_vede` | rosso |
| B ritardo del punteggio a 0 | i 2 test del punto B | rossi |
Ripristino da copia + hash, `MUTAZIONE` = 0.

## Numeri
- `service.py`: +9 / -6 righe rispetto a P4_3 (2 zone rimesse + 1 argomento + commenti).
- `pytest Betfair/mike`: **1120 passed** (su master con P4_3+P4_4).
- `pytest Betfair/stream/tests -k "mike or banco or certifica"`: 293 passed, 25 skipped.
- Replay solo `punteggio-ko --trasporto canale`: 0 violazioni, «avvisi di assenza 1 | di ritorno 1»,
  131 s, 428 tick/s. (Azioni 6 invece di 2 rispetto alla mia corsa del blocco 3: il codice di master
  contiene P2 e altri pacchetti; lo scenario punteggio-ko non l'ho confrontato col giro completo, lo fai tu.)

## Non fatto (come da istruzioni)
`live.score_age_s` / `live.punteggio_assente`, M8.11, righe del motore.
