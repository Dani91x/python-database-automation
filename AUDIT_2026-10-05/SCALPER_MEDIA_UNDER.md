# SCALPER CALCIO — modalita' «MEDIA UNDER» (05/10/2026)

Delegato (sessione cloud). Ramo `feature/scalper-media-under` da `master` `20bbf9b`.
Specifica: `Betfair/stream/scalper/SPEC_MEDIA_UNDER_2026-10-05.md`.
Nessun ordine vero, nessuna chiamata a Betfair, nessun accesso al DB, nessun `.env`,
app non avviata, nessun processo lasciato acceso.

## 0. IN EVIDENZA — cio' che NON ho potuto verificare

1. **Nessun replay di certificazione eseguito.** Le registrazioni (`_live_raw/`) non
   sono nel mio ambiente. Gli scenari `media-under`, `media-under-paper`,
   `media-under-35` e i controlli M1-M9 sono PRONTI ma **mai girati su una partita
   vera**: il percorso completo del replay (`certifica_scenario` -> `MotoreReplay` ->
   `run_session` intera -> `_Banco.giro`) per la modalita' NON e' mai stato eseguito.
   Ho eseguito solo i pezzi che girano senza registrazione: armamento della sessione
   vera (`arma_e_cattura`, parita' paper/live) e il ponte dei controlli M
   (`_Banco.controlli_media`) sugli ordini veri di un flumine di prova. Non ho
   costruito registrazioni sintetiche (vietato dalla consegna).
2. **La modalita' NON e' certificata.** Gradini mancanti: replay sulle registrazioni
   vere, prova (paper), solo dopo soldi veri.
3. **Interfaccia mai vista a schermo** (solo test di componente vitest, `tsc` 0
   errori). Nessun `npm run build` (l'app la gestisce l'utente).
4. **Ordini messi a mano dall'utente: NON visti.** Il riquadro dichiara «solo
   ordini del bot» (vedi §6, punto P14, con la proposta).
5. **Database**: le scritture (`scalper_control.stats` con le chiavi `media_*`,
   `scalper_activity`, l'avviso `SCALPER_MEDIA_RIAVVIO` in `live_alerts`) sono
   provate solo col DB finto del banco. Nessuna migrazione: i parametri stanno in
   `scalper_control.params` (jsonb, passati cosi' come sono dalla RPC
   `scalper_activate`), lo stato in `stats`.
6. **Ambiente diverso dal PC dell'utente**: Python 3.11 (l'utente 3.13), dipendenze
   installate da `requirements.txt` (flumine 2.13.11, betfairlightweight 2.23.2).
   9 test della suite sono rossi **anche su master senza le mie modifiche** in
   questo ambiente (§5).
7. **Comportamento in LIVE (soldi veri) di flumine con l'order stream**: non
   verificato se, dopo un riavvio, flumine riadotta nel blotter gli ordini vivi della
   sessione morta (stesso nome di strategia). Vedi P13.

## 1. Cosa ho aggiunto (file:riga sul ramo)

| File | Dove | Cosa |
|---|---|---|
| `Betfair/stream/scalper/media_under_bot.py` (NUOVO) | :71-133 costanti, valori di serie, obbligatori, stati | la modalita' |
| | :141-310 `ParametriMedia`, `media_mode_acceso`, `leggi_parametri`, `motivo_non_parte`, `vita_sessione_s`, `posizione_aperta_nelle_stats` | parametri (spec par.5), mai un valore inventato |
| | :313-512 `Posizione`, `posizione_da_ordini`, `banca_esatta`, `rientro_esatto`, `lordo_da_netto`, `obiettivo_automatico`, `tick_sotto`, `punta_a_multiplo`, `riquadro_chiusura` | le formule del par.4 (pure) e il riquadro del par.6 |
| | :552 `MediaUnderStrategy` (flumine `BaseStrategy`) | la macchina a stati (§2) |
| `Betfair/stream/scalper/scalper_session.py` | :94-102 whitelist; :1117-1131 avvio rifiutato col motivo; :1163-1166 sniper non armato; :1386-1440 la strategia; freno soldi veri, maker non aggiunto, stats `media_*`, force-flat, attesa del flat, vita | aggancio alla sessione |
| `Betfair/stream/scalper/auto_mode.py` | :147-159 `params_per_sessione` toglie ogni chiave `media_*` | l'auto-mode non la arma mai |
| `Betfair/stream/scalper/certificazione.py` | :1285 `ESCLUSI_MEDIA`, `verifica(..., escludi=)`; :1368-1750 famiglia M (registro SEPARATO) | controlli di condotta |
| `Betfair/stream/scalper/tools/replay_registrazioni.py` | :137-150 scenari; :279-289 descrizioni; :315-332 control della scheda; :454 vita; `_Banco` attributi, aggancio della strategia, `controlli_media`, giro, parita', note del referto | il banco |
| `Betfair/stream/backtest/registro_bot.py` | :159 | modulo registrato fra i moduli di produzione dello scalper |
| `frontend/src/lib/mediaUnder.ts` (NUOVO) | | valori di serie, campi, controllo dei valori, lettura delle stats, testi |
| `frontend/src/components/live/ScalperPanel.tsx` | interruttore, mercato, parametri, conferma soldi veri, stato del ciclo, riquadro | scheda |
| `frontend/src/lib/scalper.ts` | tipo di `stats` aperto alle chiavi `media_*` | tipi |
| `Betfair/stream/tests/banco_media_under.py` (NUOVO) | | banco di prova: flumine VERO, book nativi Betfair |
| `Betfair/stream/tests/test_scalper_media_under_2026_10_05.py` (NUOVO) | 97 casi | test |
| `frontend/src/lib/mediaUnder.test.ts` (NUOVO), `ScalperPanel.test.tsx` (+3) | | test |
| `AUDIT_2026-10-05/strumenti/mutazioni_media_under.py` | | script di falsificazione (ripristino con `git checkout`) |
| `Betfair/stream/scalper/BIBBIA_SCALPER_CALCIO.md` | §14 | sezione sulla modalita' |

**Cio' che NON cambia** (regola 1): maker, Sniper, Theta, auto-mode (salvo togliere le
chiavi `media_*`, che nessuna riga di oggi porta), supervisore. Con la modalita'
spenta: nessun ramo nuovo e' percorso (verificato con `arma_e_cattura` sul control
`base`: arma il maker come prima; il contratto `test_tetto_della_sessione_dalle_sue_costanti`
resta verde). Il registro dei controlli del maker resta di 22 voci: la copertura che
il banco stampa per i 15 scenari certificati non cambia. Cambia l'**impronta** del
codice nei referti (`certifica.impronta`: un modulo in piu' fra i moduli di
produzione) e la riga «SCENARI» con `--scenari tutti` (tre scenari in piu'). File
vietati: nessuno toccato.

## 2. Mappa degli stati e delle condizioni

Stati (`media_under_bot.STATI`), scritti in `stats.media_stato`:

| Stato | Entra quando | Cosa fa | Esce |
|---|---|---|---|
| FERMO | avvio; ciclo chiuso in pre-match; punta d'ingresso morta senza abbinato | controlla le condizioni d'ingresso a ogni book | INGRESSO |
| INGRESSO | punta d'ingresso piazzata (LAPSE) | aspetta: abbinata in parte -> banca subito; dopo `media_ttl_punta_ms` (30 s) annulla il resto se e' sul book; PENDING (esito ignoto) = aspetta, mai un secondo ordine | IN_POSIZIONE / FERMO |
| IN_POSIZIONE | punta abbinata | UNA banca (PERSIST) a `ultimo ingresso - tick chiusura`, importo sulla posizione vera, riallineata (annullo, attesa, nuova) se cambia | RIENTRO / MASSIMO / ciclo chiuso / LIVE |
| RIENTRO | quota di punta >= ultimo ingresso + `tick rientro`, rientri < massimo, fuori dalla finestra di stop, rischio massimo rispettato | (a) annulla la banca e ASPETTA che sia morta (anche se era in volo), (b) ricalcola sulla posizione vera rileggendo la condizione sul book corrente, (c) punta il rientro, (d) banca dopo la punta | IN_POSIZIONE / MASSIMO |
| MASSIMO | rientri fatti = massimo (anche 0) | nessuna punta; la banca resta; UNA riga CRITICAL; riquadro pubblicato | ciclo chiuso -> FERMO; LIVE |
| LIVE | primo book in gioco con posizione | NESSUN ordine, annullo o riprezzo; riquadro a ogni book; attivita' su sospensione, riapertura, banca abbinata, banca caduta | FINE (banca abbinata e pari, mercato regolato) |
| FINE | in gioco senza posizione; ciclo chiuso in gioco; mercato regolato | niente | — |
| BLOCCATA | la sessione precedente ha lasciato una posizione (stats `media_*`) | NESSUN ordine; UNA riga CRITICAL + avviso `SCALPER_MEDIA_RIAVVIO` | — |

Condizioni d'ingresso (tutte): mercato OPEN e non in gioco, Under ACTIVE; quota di
punta in `[media_quota_min, media_quota_max]`; `media_min_size` sulla miglior punta E
sulla miglior banca; distanza fra le due <= `media_max_spread_ticks`; 60 s di
osservazione e `media_min_flow` scambiati per lato in 90 s (gli stessi numeri e lo
stesso calcolo dello scalper: `VALIDATED_PARAMS.warmup_ms`/`flow_window_ms`,
`_update_flow`); prima di `fischio - media_stop_ingressi_s`; nessun force-flat;
nessun freno dei soldi veri (sessione live); nessuna attesa dopo un rifiuto.

Matrice della consapevolezza degli ordini (§7 della spec):

| Ordine | Abbinato tutto | Parziale | Mai abbinato (TTL) | Rifiutato | Esito ignoto | In gioco |
|---|---|---|---|---|---|---|
| Punta d'ingresso (LAPSE) | banca sul totale | banca sulla parte abbinata, riallineata | annullo, attesa, FERMO, si rivaluta | freno 1-2-4-8-16-30 s, CRITICAL al primo | aspetta, nessun ripiazzo | cade (Betfair) |
| Punta di rientro (LAPSE) | rientro contato, banca a q - N | rientro contato (anche in parte), banca | annullo, attesa, NON contato, banca rimessa | freno, banca rimessa subito (freno separato) | aspetta | cade |
| Banca (PERSIST) | ciclo chiuso se pari | resta (il resto e' quello voluto) | resta | freno della banca | aspetta | resta; abbinata/caduta dette |

Rifiuto letto in due punti: `place_order` che torna False (flumine: ordine mai nel
blotter, catalogo par.7 punto 2) ed esito FAILURE arrivato dopo
(`responses.place_response.error_code`, come `scalper_bot._codice_rifiuto`).

## 3. Test

`Betfair/stream/tests/test_scalper_media_under_2026_10_05.py`, strategia VERA su
Flumine VERO (client paper della sessione), book nel formato nativo Betfair, esecuzione
differita di 1 e 4 book, regola dei minimi del banco montata
(`minimi_banco.minimi_it_su_flumine`): 97 casi.

- Vettori del par.4: A (tabella intera, riga per riga), B, C, D (riquadro), scala dei
  tick, punta a multiplo per difetto; A riprodotto anche su flumine (6 punte, 6
  banche, MASSIMO).
- Par.9: banca abbinata in parte prima di un rientro (5,00 su 10,14 -> rientro 5,00,
  banca 10,13 @1,50); punta di rientro non abbinata (annullata, non contata, banca
  rimessa); rientro bloccato dal massimo (0) e dal rischio massimo (con la riga);
  nessun rientro in gioco; banca PERSIST che passa il fischio e punta LAPSE che cade;
  nessuna chiusura forzata prima del fischio; mai due banche/punte vive (a OGNI
  book di ogni test); riavvio a posizione aperta (BLOCCATA); soldi veri fermati
  senza «Ordini reali» (la banca parte); l'auto-mode non passa le chiavi; la sessione
  rifiuta una riga d'origine 'auto'; modalita' spenta = la sessione arma il maker.
- In piu': rientro deciso con la banca ancora in volo; esito ignoto; rifiuto con
  freno distanziato (1 s, 2 s); sospeso prima del fischio; in gioco banca abbinata
  (FINE) e banca caduta; mercato regolato (e il Match Odds chiuso NON tocca la
  modalita'); parametri mancanti (uno per uno) e non validi; contratto valori di
  serie Python = scheda; chiavi nella whitelist; registro del banco; vita della
  sessione; controlli M muti sul bot vero e rossi sui difetti; ponte del replay.
- Frontend: `mediaUnder.test.ts` (10), `ScalperPanel.test.tsx` (+3: spenta di
  serie, accesa senza mercato non parte / col mercato manda tutto e spegne lo
  sniper, vista della sessione).

## 4. Falsificazione

Script `AUDIT_2026-10-05/strumenti/mutazioni_media_under.py`: una mutazione alla
volta, test, ripristino con `git checkout -- <file>`, `git diff --quiet` verificato.

| # | mutazione | test rossi |
|---|---|---|
| U1 | formula del rientro con il segno sbagliato | 16 rossi: test_banca_abbinata_in_parte_prima_di_un_rientro, test_controlli_m_muti_sul_bot_vero_e_tutti_sollecitati, test_controlli_m_rossi_sui_difetti, test_rientro_bloccato_dal_rischio_massimo_con_la_riga_di_log, test_rientro_deciso_con_la_banca_ancora_in_volo ... |
| U2 | banca arrotondata per difetto invece che al centesimo | 8 rossi: test_ingresso_e_banca_persist_sul_mercato_scelto, test_punta_di_rientro_non_abbinata_si_annulla_e_non_conta, test_vettore_a_base_10_a_150_obiettivo_automatico_punte_a_050, test_vettore_a_su_flumine_rientri_banche_e_massimo, test_vettore_b_esempio_dell_utente_netto_030_al_centesimo |
| U3 | obiettivo netto usato come lordo | 2 rossi: test_vettore_b_esempio_dell_utente_netto_030_al_centesimo, test_vettore_c_come_b_con_le_punte_a_multipli_di_050 |
| U4 | punta arrotondata al multiplo piu' vicino (non per difetto) | 9 rossi: test_controlli_m_muti_sul_bot_vero_e_tutti_sollecitati, test_punta_a_multiplo_per_difetto_dalla_fonte_unica, test_rientro_bloccato_dal_rischio_massimo_con_la_riga_di_log, test_vettore_a_base_10_a_150_obiettivo_automatico_punte_a_050, test_vettore_a_su_flumine_rientri_banche_e_massimo ... |
| U5 | riquadro: cifre 'esatte' calcolate col multiplo | 1 rossi: test_vettore_d_segnalazione_in_gioco_esempio_dell_utente |
| U6 | tick calcolati a 0,01 fissi (non la scala vera) | 1 rossi: test_tick_sulla_scala_vera_di_betfair |
| U7 | interruttore acceso da un valore 'vero' qualunque | 1 rossi: test_spenta_di_serie_solo_un_vero_la_accende |
| U8 | obiettivo 0 trattato come 0 netti (non automatico) | 17 rossi: test_banca_abbinata_in_parte_prima_di_un_rientro, test_controlli_m_rossi_sui_difetti, test_i_valori_di_serie_sono_validi_e_l_obiettivo_assente_e_automatico, test_il_ponte_del_replay_giudica_la_modalita, test_in_gioco_nessun_ordine_banca_persist_resta_punta_lapse_cade ... |
| U9 | un parametro mancante non ferma la sessione | 16 rossi: test_la_sessione_non_parte_con_un_parametro_mancante, test_un_parametro_mancante_non_fa_partire[media_commissione_pct], test_un_parametro_mancante_non_fa_partire[media_max_rientri], test_un_parametro_mancante_non_fa_partire[media_max_spread_ticks], test_un_parametro_mancante_non_fa_partire[media_mercato] ... |
| U10 | stake non multiplo di 0,50 accettato | 1 rossi: test_un_parametro_non_valido_non_fa_partire[media_stake-10.3] |
| U11 | riga dell'auto-mode accettata | 2 rossi: test_la_sessione_rifiuta_una_riga_armata_dall_auto_mode, test_origine_auto_theta_e_intervallo_non_fanno_partire |
| U12 | media_mercato fuori dalla whitelist | 1 rossi: test_le_chiavi_della_modalita_sono_nella_whitelist_della_sessione |
| U13 | valore di serie diverso dalla scheda | 3 rossi: test_i_valori_di_serie_sono_quelli_della_scheda, test_vettore_a_su_flumine_rientri_banche_e_massimo |
| U14 | banca di chiusura LAPSE | 26 rossi: test_banca_abbinata_in_parte_prima_di_un_rientro, test_ciclo_chiuso_in_profitto_e_ricomincia_con_lo_stake_base, test_controlli_m6_importo_e_quota_ognuno_da_solo, test_controlli_m_muti_sul_bot_vero_e_tutti_sollecitati, test_in_gioco_banca_abbinata_chiude_il_ciclo_e_finisce ... |
| U15 | ingresso senza liquidita' minima | 2 rossi: test_niente_ingresso_senza_liquidita_flusso_spread_o_quota |
| U16 | nessuna finestra di stop prima del fischio | 4 rossi: test_nessuna_chiusura_forzata_prima_del_fischio, test_niente_ingresso_dentro_la_finestra_di_stop_prima_del_fischio |
| U17 | ciclo chiuso mai riconosciuto | 4 rossi: test_ciclo_chiuso_in_profitto_e_ricomincia_con_lo_stake_base, test_in_gioco_banca_abbinata_chiude_il_ciclo_e_finisce |
| U18 | banca vecchia riappoggiata mentre la punta di rientro e' in volo | 6 rossi: test_banca_abbinata_in_parte_prima_di_un_rientro, test_controlli_m_muti_sul_bot_vero_e_tutti_sollecitati, test_controlli_m_rossi_sui_difetti, test_rientro_deciso_con_la_banca_ancora_in_volo, test_vettore_a_su_flumine_rientri_banche_e_massimo |
| U19 | posizione che ignora le banche abbinate | 6 rossi: test_banca_abbinata_in_parte_prima_di_un_rientro, test_ciclo_chiuso_in_profitto_e_ricomincia_con_lo_stake_base, test_in_gioco_banca_abbinata_chiude_il_ciclo_e_finisce |
| U20 | rientri mai contati (massimo mai raggiunto) | 2 rossi: test_vettore_a_su_flumine_rientri_banche_e_massimo |
| U21 | punta non abbinata mai annullata (TTL) | 2 rossi: test_punta_di_rientro_non_abbinata_si_annulla_e_non_conta |
| U22 | rientro bloccato con la banca in volo (annullo mai chiesto) | 1 rossi: test_rientro_deciso_con_la_banca_ancora_in_volo |
| U23 | un rientro oltre il massimo | 4 rossi: test_rientro_bloccato_dal_massimo_zero, test_vettore_a_su_flumine_rientri_banche_e_massimo |
| U24 | rischio massimo ignorato | 2 rossi: test_rientro_bloccato_dal_rischio_massimo_con_la_riga_di_log |
| U25 | in gioco opera come prima del fischio | 6 rossi: test_in_gioco_banca_abbinata_chiude_il_ciclo_e_finisce, test_in_gioco_nessun_ordine_banca_persist_resta_punta_lapse_cade, test_in_gioco_sospensione_e_banca_caduta_si_dicono |
| U26 | in gioco dopo la chiusura ricomincia un ciclo | 2 rossi: test_in_gioco_banca_abbinata_chiude_il_ciclo_e_finisce |
| U27 | banca caduta in gioco non detta | 2 rossi: test_in_gioco_sospensione_e_banca_caduta_si_dicono |
| U28 | esito ignoto (PENDING) creduto morto | 24 rossi: test_banca_abbinata_in_parte_prima_di_un_rientro, test_ciclo_chiuso_in_profitto_e_ricomincia_con_lo_stake_base, test_controlli_m6_importo_e_quota_ognuno_da_solo, test_controlli_m_muti_sul_bot_vero_e_tutti_sollecitati, test_controlli_m_rossi_sui_difetti ... |
| U29 | nessun freno dopo un rifiuto | 2 rossi: test_rifiuto_freno_mai_un_ripiazzo_a_ogni_giro |
| U30 | aperture senza il freno dei soldi veri | 2 rossi: test_soldi_veri_fermati_senza_ordini_reali_la_banca_parte |
| U31 | riavvio a posizione aperta ignorato | 2 rossi: test_riavvio_a_posizione_aperta_non_ricostruibile_nessun_ordine |
| U32 | ordini a mercato sospeso | 2 rossi: test_sospeso_prima_del_fischio_nessun_ordine |
| U33 | esito dal mercato sbagliato (Match Odds) | 2 rossi: test_mercato_regolato_esito_dal_risultato |
| U34 | la sessione arma anche il maker | 1 rossi: test_la_sessione_arma_solo_la_modalita_e_paper_uguale_live |
| U35 | modalita' accesa anche a interruttore spento | 1 rossi: test_modalita_spenta_nessun_effetto_la_sessione_arma_il_maker |
| U36 | la sessione parte con un parametro mancante | 2 rossi: test_la_sessione_non_parte_con_un_parametro_mancante, test_la_sessione_rifiuta_una_riga_armata_dall_auto_mode |
| U37 | l'auto-mode passa le chiavi media_* | 1 rossi: test_l_auto_mode_non_passa_mai_le_chiavi_della_modalita |
| U38 | replay: vita della sessione media a 10' | 1 rossi: test_vita_della_sessione_fino_a_fine_partita |
| U39 | modulo nuovo non registrato nel banco | 1 rossi: test_registrata_nel_banco_e_scenari_riconosciuti |
| U40 | M4 senza l'arrotondamento a 0,50 (falso positivo) | 2 rossi: test_controlli_m_muti_sul_bot_vero_e_tutti_sollecitati |
| U41 | M1 non guarda il mercato scelto | 2 rossi: test_controlli_m_rossi_sui_difetti |
| U42 | M2 cieco sul massimo | 2 rossi: test_controlli_m_rossi_sui_difetti |
| U43 | M3 cieco sui tick | 4 rossi: test_controlli_m_rossi_sui_difetti, test_il_ponte_del_replay_giudica_la_modalita |
| U44 | M5 cieco su due ordini vivi | 2 rossi: test_controlli_m5_m8_rossi_su_ordini_veri_sbagliati |
| U45 | M6 cieco sull'importo | 2 rossi: test_controlli_m6_importo_e_quota_ognuno_da_solo |
| U46 | M6 cieco sulla quota | 2 rossi: test_controlli_m6_importo_e_quota_ognuno_da_solo |
| U47 | M7 cieco sugli ordini in gioco | 2 rossi: test_controlli_m_rossi_sui_difetti |
| U48 | M8 cieco sulla banca LAPSE | 2 rossi: test_controlli_m5_m8_rossi_su_ordini_veri_sbagliati |
| U49 | M9 cieco sulla finestra di stop | 2 rossi: test_controlli_m_rossi_sui_difetti |
| U50 | replay: controlli M mai chiamati | 2 rossi: test_il_ponte_del_replay_giudica_la_modalita |
| U51 | replay: parametri dalla scheda di serie invece che dalla riga | 2 rossi: test_il_ponte_del_replay_giudica_la_modalita |
| U52 | interi sotto il minimo accettati (tick 0, rientri -1, attesa 0) | 3 rossi: test_un_parametro_non_valido_non_fa_partire[media_max_rientri--1], test_un_parametro_non_valido_non_fa_partire[media_tick_chiusura-0], test_un_parametro_non_valido_non_fa_partire[media_ttl_punta_ms-0] |
| U53 | numeri negativi accettati | 1 rossi: test_un_parametro_non_valido_non_fa_partire[media_rischio_max--5] |
| U54 | intervallo di quota rovesciato accettato | 1 rossi: test_un_parametro_non_valido_non_fa_partire[media_quota_min-4.5] |
| U55 | obiettivi in gioco come testo accettati | 1 rossi: test_un_parametro_non_valido_non_fa_partire[media_obiettivi_live-0] |
| U56 | commissione del 100 % accettata | 1 rossi: test_un_parametro_non_valido_non_fa_partire[media_commissione_pct-100] |
| U57 | obiettivo negativo accettato | 1 rossi: test_un_parametro_non_valido_non_fa_partire[media_obiettivo--0.3] |
| U58 | un mercato qualunque accettato | 2 rossi: test_un_parametro_non_valido_non_fa_partire[media_mercato-MATCH_ODDS], test_un_parametro_non_valido_non_fa_partire[media_mercato-OVER_UNDER_15] |
| U59 | un booleano letto come numero | 1 rossi: test_un_parametro_non_valido_non_fa_partire[media_min_size-True] |
| U60 | media insieme a theta o intervallo | 1 rossi: test_origine_auto_theta_e_intervallo_non_fanno_partire |
| U61 | riavvio: solo il MASSIMO riconosciuto | 2 rossi: test_riavvio_a_posizione_aperta_non_ricostruibile_nessun_ordine |
| U62 | stake qualunque accettato | 2 rossi: test_un_parametro_non_valido_non_fa_partire[media_stake-0.5], test_un_parametro_non_valido_non_fa_partire[media_stake-10.3] |
| U63 | interi letti troncando i decimali | 1 rossi: test_un_parametro_non_valido_non_fa_partire[media_tick_rientro-1.5] |
| F1 | scheda: punta non multipla accettata | 1 rossi: punta d'ingresso solo da 1,00 a multipli di 0,50 (Betfair.it) (vitest) |
| F2 | scheda: sniper non spento nel payload | 1 rossi: il payload ha TUTTE le chiavi, la modalità accesa e sniper/theta/intervallo spenti (vitest) |
| F3 | scheda: obiettivi con la virgola italiana non letti | 2 rossi: accesa: senza mercato non parte; col mercato manda tutti i parametri e spegne lo sniper (vitest), obiettivi in gioco scritti con la virgola italiana (vitest) |
| F4 | scheda: tipi delle stats non controllati | 1 rossi: un campo col tipo sbagliato non passa come numero (vitest) |
| F5 | scheda: punta esatta al posto del multiplo | 1 rossi: la riga dell'obiettivo dice punta a multiplo, importo esatto, rischio, media e banca dopo (vitest) |
| F6 | scheda: la media non spegne lo sniper | 1 rossi: accesa: senza mercato non parte; col mercato manda tutti i parametri e spegne lo sniper (vitest) |
| F7 | scheda: parte senza mercato | 1 rossi: accesa: senza mercato non parte; col mercato manda tutti i parametri e spegne lo sniper (vitest) |
| F8 | scheda: stato del ciclo non mostrato | 1 rossi: la sessione attiva mostra lo stato del ciclo e il riquadro di chiusura (vitest) |
| F10 | scheda: nessun controllo del mercato | 1 rossi: il mercato si sceglie: senza mercato la scheda non manda (vitest) |
| F11 | scheda: quote rovesciate accettate | 1 rossi: valori non validi: tick, rientri, quote, commissione (vitest) |
| F12 | scheda: vista della modalita' anche senza modalita' | 1 rossi: nessuna modalità = null (la vista non compare) (vitest) |
| F13 | scheda: banca appoggiata mai letta | 2 rossi: la sessione attiva mostra lo stato del ciclo e il riquadro di chiusura (vitest), legge stato, banca e riquadro con i loro tipi (vitest) |
| F14 | scheda: modalita' accesa di serie | 4 rossi: accesa: senza mercato non parte; col mercato manda tutti i parametri e spegne lo sniper (vitest), il form nasce con lo sniper spuntato e lo manda acceso (true esplicito) all'attivazione (vitest), spegnendo il checkbox lo sniper parte spento (sniper_mode=false ESPLICITO, mai assente) (vitest), spenta di serie: l'attivazione normale non manda la modalità (vitest) |
| F9 | valore di serie: modalita' accesa | 2 rossi: spenta di serie e i valori di serie della spec par.5 (vitest), test_i_valori_di_serie_sono_quelli_della_scheda |

**78 mutazioni, 0 sopravvissute.** Ogni caso dei 97 di `test_scalper_media_under_2026_10_05.py` (parametri compresi) e ognuno dei 13 test vitest nuovi e' diventato rosso almeno una volta (verificato dall'esito `AUDIT_2026-10-05/strumenti/mutazioni_media_under_esito.json` contro l'elenco raccolto da pytest). Albero ripristinato con `git checkout` dopo ogni mutazione e verificato pulito.

Storia della falsificazione (onesta): al primo giro sono SOPRAVVISSUTE U26 (in gioco dopo la chiusura ricomincia un ciclo), U45 e U46 (M6 cieco su importo o su quota: ogni test faceva scattare entrambe le meta'), U50 (controlli M mai chiamati dal giro del banco: il test chiamava la funzione diretta), U61 (riavvio riconosciuto solo in MASSIMO), e U40 non era applicabile (testo dello script sbagliato). Ho rafforzato i test (commit f098c48, 9de9eee, 8e01575), non il codice; poi tutto rosso. Un giro precedente e' stato interrotto da me: un test con un `while` senza limite restava appeso sotto mutazione (test corretto con attese limitate, 333c1be).

Test ESISTENTE diventato rosso con le mie modifiche e sistemato: `test_contratto_strada_unica_2026_09_25::test_nessun_chiamante_nuovo_non_registrato` (il modulo nuovo chiama `place_order`): registrato come strada S4a, la stessa di maker e sniper. `test_scalper_arresto_ordinato_2026_10_02::test_tetto_della_sessione_dalle_sue_costanti` era rosso con una mia prima stesura (avevo messo la modalita' nel ciclo `for extra in (sniper, theta)` che fissa il tempo massimo d'arresto): riga rimessa com'era, la modalita' aspettata a parte (in una sessione media under sniper e theta non esistono: al piu' due attese, dentro `STRATEGIE_MAX`).

## 5. Suite

Ambiente: container cloud, Python 3.11.15, flumine 2.13.11, betfairlightweight 2.23.2,
Node 22. Comandi della CLAUDE.md.

| Suite | Master `20bbf9b` (prima) | Ramo (dopo) |
|---|---|---|
| `python -m pytest Betfair/ -q -p no:cacheprovider` | 9941 verdi, **9 rossi**, 75 saltati, 6 xfail | **10043 verdi, 5 rossi**, 75 saltati, 6 xfail |
| file nuovo `test_scalper_media_under_2026_10_05.py` | — | 97 verdi |
| test mirati scalper/sniper/theta/auto-mode/registro/certificazione/minimi/arresto | — | 1118 verdi, 20 saltati |
| `npx vitest run` (tutto `frontend/`) | — | 324 file / 4971 verdi, 0 rossi, 50 saltati |
| `npx tsc -p tsconfig.app.json --noEmit` | 0 errori | **0 errori** |

I 5 rossi sono rossi anche su master in QUESTO ambiente, prima di ogni mia modifica:
`safe_strategy/tests/test_velocita_feed_2026_09_30.py` (5 test), `TypeError: 'Event'
object is not callable` dentro `threading` (i test toccano `_is_stopped`, che in Python
3.11 e 3.13 sono diversi). Su master c'erano in piu' 4 rossi di tempo in
`stream/tests/test_stream_heartbeat_stall_2026_07_17.py`, verdi nelle due corse finali:
dipendono dal carico della macchina (non li ho toccati).
**Saltati**: i test del banco che leggono le registrazioni (`_live_raw/`, non presenti
qui) sono «skipped»: nessun replay dello scalper e' stato eseguito in questa suite.

## 6. Punti che la specifica non decide (NON decisi da me, o decisi in modo dichiarato)

Ogni punto ha un esempio in euro. «Non fatto» = lasciato com'e' oggi nel codice comune.

- **P1 — Stop dalla UI / freno / fine vita con una posizione aperta prima del
  fischio. NON FATTO.** La modalita' al force-flat smette di aprire (nessun
  ingresso, nessun rientro) e NON chiude di sua iniziativa. Pero' l'arresto
  ESISTENTE della sessione (`chiudi_all_arresto`) annulla tutti gli ordini non
  abbinati, compresa la banca PERSIST, e dichiara la posizione (CRITICAL). Esempio:
  40,00 EUR puntati a media 1,525, banca 40,13 @1,52 appoggiata; l'utente preme
  STOP: la banca viene annullata, restano +21,00 se vince / -40,00 se perde,
  dichiarati, da chiudere a mano. Da decidere: lasciare la banca PERSIST a mercato
  allo stop, oppure chiudere, oppure come oggi.
- **P2 — Commissione.** La sessione dello scalper NON usa una commissione. Ho messo il
  parametro `media_commissione_pct` (di serie 5,0: quella dei vettori del par.4 e il
  `DEFAULT_COMMISSION_PCT` di Safe/Mike). Conta solo per il netto mostrato e per
  l'obiettivo in euro netti (0,30 netti = 0,3158 lordi). Con l'obiettivo automatico
  (di serie) gli ordini non dipendono dalla commissione. Da confermare.
- **P3 — Vettore D: rischio e media con l'importo esatto o col multiplo?** L'esempio
  dell'utente scrive «189,75 (199,75; 1,6525)» (esatto); il par.6 dice «a multiplo di
  0,50 ... il rischio totale che ne risulta». Il riquadro mostra ENTRAMBI (rischio
  199,50 col multiplo, 199,75 con l'esatto; banca dopo 199,80 / 200,05). Da scegliere.
- **P4 — Vettore C: il netto.** La spec dice «fra 0,294 e 0,299»; la formula del
  par.4 da' 0,2945 se l'Under perde e **0,3009** se vince (sopra 0,299). Il minimo
  garantito e' dentro. Divergenza riferita, nessuna formula cambiata.
- **P5 — Rischio massimo: due letture.** «blocco dei rientri quando lo stake supera il
  rischio massimo». Ho fatto la lettura che non lo supera mai: il rientro non parte
  se totale puntato + rientro > rischio massimo. Esempio con 35 EUR: 20 puntati +
  rientro 20 = 40 > 35 -> bloccato. L'altra lettura: si blocca solo quando il totale
  GIA' supera 35, quindi quel rientro da 20 parte (totale 40) e il successivo no. Di
  serie e' spento (0). Da confermare.
- **P6 — Rientro abbinato solo in parte.** Contato come rientro (mai piu' rientri del
  massimo); un rientro con abbinato 0 non conta e si rivaluta.
- **P7 — Banca sotto 1,00 EUR o rientro sotto 1,00 EUR. NON FATTO il place-and-trim.**
  Si dichiarano una volta (CRITICAL) e non partono. Accade solo con abbinati
  minimi (es. punta abbinata 0,40: banca 0,41 @1,48 non piazzata, dichiarata).
- **P8 — Salto di quota sul rientro (RISCHIO, non una scelta).** La formula del par.4
  con un salto grande da' importi enormi. Esempio: 10,00 @1,50 (obiettivo 0,1351), la
  quota salta a 2,00: c = 1,98, X = 253,38 -> punta 253,00 EUR in un colpo. Unico
  limite: `media_rischio_max`, spento di serie. Non ho aggiunto tetti (spec par.4).
- **P9 — Tetti di flumine.** La strategia nasce con `max_selection_exposure=None` e
  `max_order_exposure=None`: con i tetti di flumine (come maker/sniper) gli ordini
  oltre il tetto verrebbero rifiutati in silenzio, cioe' un tetto nuovo.
- **P10 — Tetto globale della sessione (`event_global_cap`, 2 EUR).** Somma i P&L di
  maker, sniper, theta: la modalita' non ci entra (non chiude mai in perdita da sola;
  aggiungerla sarebbe uno stop nuovo). Non fatto.
- **P11 — Sessione con theta o intervallo insieme, o mode diverso da 'maker'.** La
  sessione non parte (motivo scritto). Una sessione media under arma solo la modalita'
  (spec par.2); la scheda le rende alternative.
- **P12 — Obiettivi del riquadro in netti.** Convertiti in lordi con la commissione;
  l'esempio D ha commissione 0, quindi coincide.
- **P13 — Riavvio a posizione aperta.** Rilevato dalle `stats` della sessione
  precedente (sopravvivono al riarmo: `scalper_activate` non le azzera): stato
  BLOCCATA, nessun ordine, avviso CRITICAL. Conseguenza: su quella partita la
  modalita' non riparte finche' le stats dicono «posizione aperta» (anche dopo uno
  STOP volontario con posizione, e anche in prova, dove gli ordini simulati sono
  spariti col processo). L'adozione degli ordini della sessione morta NON e' fatta
  (coerente col §B del 04/10: e' una scelta dell'utente). In LIVE flumine potrebbe
  riadottare nel blotter gli ordini vivi con lo stesso nome di strategia (non
  verificato): la modalita' bloccata non li tocca, ma l'arresto della sessione
  annullerebbe anche quelli.
- **P14 — Ordini manuali (spec par.6). Limite, con proposta.** La sessione non li vede:
  flumine scarta gli ordini del conto senza il suo `customer_order_ref`. Il riquadro
  lo scrive («solo ordini del bot»). Proposta: in sessione SOLDI VERI leggere a ogni
  battito le righe di `betfair_live_orders` della selezione (scritte dal
  `reconcile_worker`, ordini del conto e `role='utente'`) e sommarle alla posizione
  del riquadro (mai negli ordini della modalita'); in prova MAI (paper e live non si
  sommano). Da approvare: e' una lettura nuova dal DB nella sessione.
- **P15 — Riquadro anche prima del massimo?** Pubblicato solo in LIVE e in MASSIMO
  (lettera del par.6).
- **P16 — Nuovo ciclo subito dopo la chiusura**, se le condizioni d'ingresso valgono
  (nessuna pausa: la spec non ne mette).
- **P17 — `media_ttl_punta_ms` = 30 000** (motivo: e' il `cooldown_ms` dello scalper, un
  numero gia' del repo; la punta d'ingresso e' presa alla miglior quota, 30 s bastano a
  latenza e coda dello stesso livello senza tenere la posizione senza banca a lungo).
- **P18 — Punta di rientro in volo = posizione senza banca.** E' la sequenza (a)-(d)
  della spec: fino all'abbinamento (al piu' 30 s) la posizione non ha banca.
- **P19 — Ciclo chiuso: tolleranza «pari»** 0,02 + 0,005 x quota (l'arrotondamento al
  centesimo della banca).
- **P20 — Banco: B2 e K5 del maker non si applicano alla modalita'** (la posizione va
  in gioco per progetto); al loro posto M5, M6, M7. I controlli M sono stampati nelle
  note di ogni scenario `media-under*` (sollecitati / mai sollecitati), non nella
  tabella di copertura di `certifica.py` (banco comune, non toccato). I controlli di
  slot del maker in quegli scenari escono «??» (mai sollecitati): atteso.
- **P21 — MissionCard (Omega)** arma lo scalper ma non ha la modalita' (spec par.8 cita
  solo ScalperPanel).

## 7. Per il revisore

```
python -m pytest Betfair/stream/tests/test_scalper_media_under_2026_10_05.py -q -p no:cacheprovider
python AUDIT_2026-10-05/strumenti/mutazioni_media_under.py      # albero pulito
python -m Betfair.stream.backtest.certifica scalper_calcio <evento> --scenari media-under,media-under-paper,media-under-35
python -m Betfair.stream.backtest.certifica scalper_calcio 35797769 --scenari base,paper   # deve restare identico a prima (tolta l'impronta)
cd frontend && npx vitest run src/lib/mediaUnder.test.ts src/components/live/ScalperPanel.test.tsx && npx tsc -p tsconfig.app.json --noEmit
```
Da guardare nel referto dei replay: note «MEDIA UNDER: controlli M sollecitati ... MAI
sollecitati», S6 (parita'), stati annunciati, e che la registrazione abbia il mercato
scelto (altrimenti la nota lo dice: referto non valido).
