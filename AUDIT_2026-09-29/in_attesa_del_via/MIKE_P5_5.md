# CANTIERE MIKE-COPERTURA - P5 blocco 5: la banca Under 4,5 diventa il valore di serie (29/09/2026)

Base: `4c66cbc` + `MIKE_P5_4.patch` + `MIKE_P5_4C.patch`. Patch: `AUDIT_2026-09-29/MIKE_P5_5.patch`
(25 KB). Nessun commit. **Da NON integrare senza il via dell'utente** (ordine del coordinatore).

## 1. Cosa cambia
- `Betfair/mike/config.py`: `cover_form` di serie `lay_under45` (era `back_over45`). Una riga.
- `Betfair/mike/tests/conftest.py`: fixture `forma_di_prima` (NON automatica) che porta
  `C.DEFAULTS["cover_form"]` a `back_over45` per il solo test che la chiede.
- 31 test vecchi FISSATI sulla forma di prima con `@pytest.mark.usefixtures("forma_di_prima")` (una
  riga ciascuno, asserzioni INVARIATE; elenco in `mike_p5/elenco_fissati_b5.txt`, script
  `mike_p5/fissa_forma_di_prima.py`) + 1 test fissato scrivendo il parametro (usa `PAR` calcolato
  all'import, che la fixture non raggiunge). Nessun test cancellato o saltato.
- 2 miei test aggiornati: `test_interruttore_back_over45...` (ora "di serie e' la banca") e
  `test_cover_form_sconosciuto...` (un valore non previsto in `merge_params` torna al valore di SERIE;
  `engine.cover_form` su un dizionario senza la chiave resta la forma di prima, difesa del motore).
- nuovo `test_mike_p5_gemelli_banca_2026_09_29.py` (6): i GEMELLI nella forma banca dei test fissati
  (freno bloccato, ritmo minimo, prima tranche a meta', copertura ordinata che non aspetta) piu' "di
  serie la copertura e' la banca" (20 x 1,2 / 0,95 = 25,26). Mutazioni `mike_p5/falsifica_mike_p5_5.py`:
  4 su 4 ROSSE (valore di serie ancora la punta, freno spento, ritmo spento, copertura ordinata che
  aspetta).

## 2. Test fissati (motivo comune: descrivono la PUNTA Over 4,5, cioe' la forma di prima)
`test_mike_audit_2026_09_11.py::test_m3_cover_max_overshoot_pct_evita_coperture_gonfiate` (legalizzazione
.it di una punta) - `test_mike_certificazione_2026_09_13.py::test_la_copertura_ordinata_non_compra_nei_secondi_del_gol`
- `test_mike_conto_e_sovracopertura_2026_09_16.py::test_il_riprezzo_della_copertura_emette_SOLO_lannullamento`
(parametro scritto) - `test_mike_engine.py`: `test_live_cover_wait_then_cover`,
`test_liability_cap_blocks_entry_cover_and_reentry`, `test_partial_cover_reprice_uses_exact_residual`
- `test_mike_engine_cert_2026_09_12.py`: `test_copertura_dimensionata_sulla_liability_netta_non_sullo_stake_lordo`,
`test_riprezzo_copertura_conta_tutte_le_coperture_gia_abbinate`, `test_telemetria_cover_wait_ha_i_campi_letti_dalla_card`,
`test_ordine_a_esito_ignoto_blocca_solo_le_aperture` - `test_mike_flusso_fischio_2026_09_13.py` (12):
`test_strada_B_finestra_scaduta_annulla_e_compra_la_copertura_piena`,
`test_strada_B_la_copertura_ordinata_non_passa_dall_attesa_intelligente`,
`test_prima_tranche_compra_meta_copertura_al_minuto_giusto`, `test_la_divisione_si_fa_a_qualunque_quota`,
`test_con_importi_esatti_spenti_la_divisione_si_ferma_al_minimo`,
`test_seconda_tranche_si_ricalcola_sulla_quota_del_momento`, `test_la_tranche_sotto_il_minimo_si_piazza_lo_stesso`,
`test_split_attivo_quando_la_tranche_e_piazzabile`, `test_il_riprezzo_della_prima_tranche_resta_sulla_frazione`,
`test_fra_le_due_tranche_valgono_le_uscite_globali_non_la_singola_gamba`,
`test_la_chiusura_globale_ha_la_precedenza_sulla_seconda_tranche`,
`test_riavvio_a_meta_strada_non_lascia_la_partita_scoperta` - `test_mike_freno_copertura_2026_09_17.py` (6):
`test_a_copertura_bloccata_il_motore_NON_emette_piu_nessuna_copertura`, `test_riprendi_dell_utente_riapre_la_copertura`,
`test_fra_due_tentativi_di_copertura_passa_almeno_cover_retry_min_s`,
`test_a_mercato_Over45_SOSPESO_la_copertura_non_parte_e_si_ASPETTA`,
`test_alla_RIAPERTURA_la_copertura_riparte_da_dove_era_rimasta`,
`test_a_mercato_sospeso_il_RIPREZZO_non_annulla_e_non_ripiazza` -
`test_mike_p2bis_2026_09_29.py::test_b_copertura_aspetta_senza_punteggio` -
`test_mike_review_2026_09_11.py::test_h8_con_esito_ignoto_il_ciclo_continua_e_riduce_il_rischio` -
`test_mike_service.py::test_inplay_cover_in_paper_va_al_runner_senza_differita_in_casa` -
`test_mike_uscite_automatiche_2026_09_25.py::test_spento_la_copertura_over_45_parte_lo_stesso`.
I gemelli della forma banca sono nei file P5 (`test_mike_p5_copertura_banca`, `_2b`, `_4b`, `_banco`,
`_gemelli_banca`: importo, tranche, riprezzo, freno, ritmo, sospensione, resto sotto 0,50, tetto,
liquidita', punteggio assente).

## 3. Suite
`Betfair/mike` su `4c66cbc` + 4 + 4C + 5: **1227 verdi, 1 ROSSO ATTESO**:
`test_mike_certificazione_ui_2026_09_11.py::test_contratto_parametri_stessi_clamp_scelte_e_default`
(il pannello ha ancora `cover_form: 'back_over45'` come valore di serie). Riga per il delegato
dell'app, in `MIKE_PARAM_DEFAULTS` di `frontend/src/lib/mike.ts`: `cover_form: 'lay_under45',`.
Senza il blocco 5 (4 + 4C): 1222 verdi.

## 4. Replay (ambiente neutro, `--worker 0`; misurati prima della 4C, che non tocca questi scenari)
| Scenario | forma | fill | P&L replay | tempo |
|---|---|---|---|---|
| base | banca (di serie) | 22,63 [1,33; 1,71]: banca 12,63 a 1,33 | -14,17 (forma di prima -14,00) | 97,8 s |
| cap-stretto (tetto 12) | banca | 15,71 [1,33; 1,71]: banca 5,71 a 1,33 | -11,88 (forma di prima -12,00) | 97,0 s |
| copertura-legacy | punta | 14,00 [1,71; 4,0] | -14,00 (identico al `base` di prima) | 97,5 s |
| `_synth_mike_prezzo_migliore` | banca | IDENTICO al riferimento | +3,55 | 6,4 s |
| `_synth_mike_reingresso` | banca | IDENTICO al riferimento | +3,28 | 8,3 s |
0 violazioni. `cap-stretto`: spazio 2,00 (tetto 12 - 10 investiti), limite 1,35 -> 2,00 / 0,35 =
5,71 (il tetto conta il rischio al prezzo limite). Le due sintetiche NON piazzano una copertura in
nessuna delle due forme (restano identiche): il rientro dopo una copertura-banca non ha un caso sul
banco (dichiarato; coperto dai test del blocco 1 e 2B). Numeri uguali alla sonda del coordinatore.

## 5. Cosa cambia per una partita GIA' IN CORSO al momento dell'aggiornamento
ATTENZIONE PRIMA DI TUTTO: il valore di serie vale solo se `cover_form` NON e' gia' salvato nei
parametri di Mike sul database. Se l'app ha salvato i parametri col campo del pannello (valore di serie
del pannello `back_over45`), il valore salvato VINCE su quello del codice: la forma resta la punta
finche' l'utente non sceglie `lay_under45` nel pannello (o il pannello non passa al nuovo valore di
serie e i parametri non vengono risalvati). Da controllare in sola lettura sui parametri salvati.
Con la forma banca effettiva, dal primo giro dopo l'aggiornamento:
- `LIVE_UNCOVERED`: la prossima copertura e' la banca Under 4,5 (importo 1,2 x perdita / 0,95 meno cio'
  che e' gia' coperto, anche da una punta Over gia' abbinata: `cover_matched_value` conta tutto il 4,5).
- `LIVE_COVER_PENDING` con la punta Over vecchia sul book (FOK: di norma si risolve nel giro; resta
  solo a esito ignoto): il riprezzo manda l'annullamento e la banca nuova viene TOLTA finche'
  l'annullamento non e' confermato (`_mai_sovracopertura`, per mercato): al giro dopo la banca si
  dimensiona sulla copertura reale. Mai due coperture insieme.
- `LIVE_COVERED` con la punta Over abbinata: uscite identiche a prima (chiusura = banca Over, come
  oggi); se manca la seconda tranche, la seconda tranche e' una banca Under dimensionata sul gia'
  coperto dalla punta (le due selezioni si compensano per mercato, blocco 1).
- chiusure, rientro, regolamento: invariati nella forma; le righe nuove della copertura portano
  `meta.cover_form`. Nessuna migrazione.

## 6. Non verificato
- Il replay completo (18 + 3 scenari) col valore di serie nuovo: lo fa il coordinatore.
- Il valore di `cover_form` salvato sul database (par. 5): sola lettura, da fare.
- Il rientro dopo una copertura-banca su una registrazione reale.
