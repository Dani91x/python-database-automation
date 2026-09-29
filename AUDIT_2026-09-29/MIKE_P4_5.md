# MIKE P4 - blocco 5 (solo test)

Patch: `AUDIT_2026-09-29/MIKE_P4_5.patch` (un file nuovo: `Betfair/mike/tests/test_mike_p4_blocco5_2026_09_29.py`),
sopra `MIKE_P4_4.patch`. Catena 3+4+5 da `6cc91a0` verificata su indice temporaneo = worktree. Codice NON toccato.

| Mutazione del coordinatore | Test | Esito con la mutazione |
|---|---|---|
| V2 tolto `and not leg.needs_reconcile` (ordine paper senza risposta) | `test_senza_risposta_gia_in_riconciliazione_non_si_ripete`: tre giri col runner muto -> UNA riga `reconcile_pending` `runner_senza_esito`, UN aggiornamento della riga | rosso |
| V7 `if ep.get("avvisato"):` -> `if True:` | `test_quota_sparita_3_s_e_tornata_nessuna_riga_di_ritorno` (sotto i 10 s: nessuna attivita', chiave tolta da `extra`) | rosso |
| V8 tolto `extra.pop(chiave, None)` | `test_episodio_chiuso_poi_nuovo_episodio` (avviso, un ritorno, tre giri col dato presente senza righe e senza chiave in `extra`, seconda assenza lunga = avviso nuovo con `da_secondi` 11) | rosso (anche il test V7) |

Ripristino da copia + hash, `MUTAZIONE` = 0.
`pytest Betfair/mike`: 1123 passed (master 6cc91a0 + P4_3 + P4_4 + P4_5). Niente replay, come chiesto.
