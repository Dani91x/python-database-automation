# CERTIFICAZIONE SCALPER CALCIO — 04/10/2026

## AGGIORNAMENTO (giro 3: certificazione piena)
Commit 0c4ba67, ab16aef, merge di master b68c23d, 1cec563. Le sezioni 1-11 qui sotto restano lo storico del giro 2.

### Da quando sono KO `riavvio` e `chiusura-abbinata-in-parte`
- Entrambi gli scenari esistono dal 24/09 (2577080).
- Rilanciati sul codice certificato del 29/09 (ff555fb) erano già KO:
  - `riavvio`: B1 ×20, B2, S7;
  - `chiusura-abbinata-in-parte`: B2, CP1 ×2, CP4 ×4, K5 ×2.
- Non sono quindi regressioni: il 29/09 si erano certificati solo `base`, `paper`, `uscite-manuali` e `uscite-manuali-firmate`. Non li aveva mai passati nessun codice.

### Cause e correzioni

**CP4 ×2 (BOT).** Lo scratch ritirava la close a target e piazzava subito la nuova chiusura, mentre l'annullo della vecchia era ancora in volo. Esempio (selezione 22): punta 2,50 @1,66 viva e punta 2,50 @1,65 piazzata insieme; se si fossero abbinate entrambe, posizione rovesciata di 2,50 EUR.
- Correzione in `scalper_bot.py`, ramo dello scratch: lo scratch parte quando la close vecchia è morta (`scratch_in_attesa`, un giro dopo).
- Prezzo e importo dello scratch sono invariati. Una firma già usata non si richiede di nuovo.

**CP1 ×1 (BANCO).** Il replay passava a CP1 solo le credenze dello slot. Una chiusura colpita, abbinata 10,00 su un ciclo poi chiuso e non più seguita dal bot, risultava «non riconosciuta».
- Per i bot tennis il banco passa già l'ultima riga di specchio (`betfair_live_orders`) di ogni ordine; ora lo fa anche per lo scalper.
- Modifica in `scalper/tools/replay_registrazioni.credenze_cp`, alimentata in modo incrementale con le sole righe nuove di ogni giro.
- I numeri della riga (abbinato, residuo, prezzo medio) li giudica sempre CP1.

**S7 ×1 (BOT/SERVIZIO).** Un processo di sessione morto lasciava ordini abbinati o vivi che nessuno seguiva né dichiarava. Un flumine nuovo non adotta ordini che non ha creato.
- Nuova `scalper_service.marca_orfana`: riga `error` più avviso CRITICAL `SCALPER_SESSIONE_ORFANA` in `live_alerts` («verificali sul conto e chiudili a mano»). Coerente con la decisione 1 dell'utente.
- Usata dal supervisore vero e dal banco (`_riarma` chiama la funzione di produzione).
- **Non** ho aggiunto l'adozione degli ordini della sessione morta da parte di quella nuova: sarebbe una scelta di strategia (il bot che chiude ordini non suoi). Proposta all'utente nel §B.

**Tutto-residuo valutato alla quota inseguita** (scalper e sniper). Trovato adattando il test dello sniper sulla fine finestra.
- Al best il resto valeva 0,50 (place-and-trim possibile); alla quota inseguita del flatten valeva 0,48 (residuo).
- Lo sniper ripiazzava a ogni giro (`min_bet_skip` a ogni book).
- Ora «tutto residuo» si valuta alla stessa quota del flatten (`cross`).

### I 23 test vecchi adattati (prima → dopo, motivo nel docstring di ognuno)

**`test_cantiere_s_scalper_ko`**
- **flatten_non_dichiara_chiuso:**
  - prima: piatta ≤ 0,02 su LAY 0,2 / 1,0 / 25;
  - dopo: piatta ≤ 0,02 oppure residuo dichiarato e ricordato al centesimo (`residuo_dichiarato_ok`);
  - aggiunto il parametro 0,7: place-and-trim con piatta ≤ 0,02;
  - K5/K6 invariati.
- **reperto_35797769:**
  - prima: LAY 1,98 (punta 1,98 al place-and-trim, punta non multipla);
  - dopo: LAY 0,98 (punta 0,98 sotto 1,00 = place-and-trim);
  - la proprietà «una sola chiusura» resta, con soglia del diretto 1,00 (era 2,00).
- **sostituto_del_rimpiazzo:**
  - prima: LAY 25 (resto 0,23 al trim);
  - dopo: LAY 0,7 (tutto al trim);
  - «una sola sequenza», «nessun residuo inventato» e «piatta ≤ 0,02» restano.
- **parcheggio_orfano:** LAY 25. Prima: piatta ≤ 0,02. Dopo: residuo dichiarato (punta 25,00 + 0,23). «Orfano ritirato» e «slot chiuso» restano.
- **parcheggio_ritirato_prima_del_taglio:**
  - prima: LAY 1,0 (punta 1,00 oggi diretta, nessuna sequenza);
  - dopo: LAY 0,7;
  - tutte le asserzioni restano.

**`test_cantiere_s_bis_sniper`**
- **il_parcheggio_della_sequenza:** punta 3,3 → 0,7 (la banca 3,30 è oggi diretta al centesimo).
- **parcheggio_ritirato_prima_del_taglio_chiusura:** 0,4 → 0,7 (la banca 0,40 è sotto 0,50).
- **fine_finestra_a_prezzi_assenti_mai_residuo:** non toccato, ora verde dopo la correzione «tutto-residuo alla quota inseguita».

**`test_cantiere_s3` sniper_nessun_critical_nella_pausa:** 0,4 → 0,7, stesse asserzioni.

**`test_cantiere_s4` scratch_firmato:**
- prima: punta 2,80 intera;
- dopo: 2,50 (punta per difetto) + `min_bet_skip` 0,30 dichiarato;
- aggiunta a ogni giro: mai due chiusure BACK vive o in volo insieme (CP4).

**`test_stato_mercato_freno` d7, ramo 2:**
- prima: −2,00/+0,05, cioè punta 1,03, «non piazzabile» col minimo copiato 2,00;
- dopo: −0,60/+0,30, cioè punta 0,45, sotto 0,50;
- messaggio e CRITICAL invariati.

Ogni test vale per ritardo 1 e 4: 11 test × 2 + il parametro d7 = 23 casi.

### Falsificazione, giro 3

Per gruppo e per le correzioni nuove. Ripristino ogni volta da patch, `MUTAZIONE` = 0.

| # | mutazione | test rossi |
|---|---|---|
| M16 | lo scratch non aspetta la close vecchia morta | 2 (S4) |
| M17 | la sessione orfana non si dichiara | 2 |
| M18 | CP1 senza lo specchio | 1 |
| M19 | sniper: tutto-residuo valutato al best | 2 (fine_finestra) |
| M20 | il residuo non si ricorda | 14 (gruppo S e test nuovi) |
| M21 | «ultima spiaggia» che non accetta mai | 1 (d7) |
| M22 | ordine in volo contato come morto (taglio in volo) | 13 (gruppo S) |
| M23 | sniper che ritira il parcheggio della sequenza a ogni book | 6 (gruppo S-bis) |
| M24 | sniper con CRITICAL anche nella pausa | 2 (S3) |

Restano valide le M1-M15 del giro 2.

### Merge di master b68c23d
- Una sola definizione di `soglia_resto` in `uscite_manuali.py`, quella di master: il file è identico a master.
- Lo scalper passa 0,50.
- `test_banco_uscite_manuali_n3` più `stream/tennis_live`: 837 verdi, 5 xfail.

### Suite `Betfair/` intera
**9954 verdi, 16 rossi, 31 saltati, 6 xfail, 457 s.** Nessuno dei 16 rossi è dello scalper, tutti rossi anche su master:
- 15 in `omega/tests/test_riconciliazione_tradotti_omega_2026_10_02.py` e `safe_strategy/tests/test_riconciliazione_tradotti_safe_2026_10_02.py`: rilanciati da me sull'albero esportato di master b68c23d → 15 rossi identici.
- Il test Safe `Betfair/stream/tests/test_banco_ambiente_dichiarato_2026_10_02.py::test_coda_stesso_referto_con_ambiente_principale_e_ambiente_vuoto`, messaggio: `AssertionError: assert ['open', 'error'] == ['hedged', 'open']` (rosso anche su 8a40f5c). Non toccato.

### Scenari (giro 3): VERDETTO CERTIFICATO
Ogni lotto dentro `timeout 900`, uno alla volta. Referti in `replay/scalper_calcio_GIRO3_*.txt`.

**15 scenari su 15 OK su 35797769**, più `base` e `paper` OK su 35760084 (0 azioni: il bot non entra).

| scenario | esito | azioni |
|---|---|---|
| base | OK | 167 |
| auto-live | OK | 167 |
| paper | OK | 167 |
| bot-fermo | OK | 99 |
| kill-switch | OK | 99 |
| senza-missione | OK | 167 |
| esiti-ignoti | OK | 167 |
| rifiuti-betfair | OK | 179 |
| **riavvio** | **OK** (prima KO S7) | 204 |
| **chiusura-abbinata-in-parte** | **OK** (prima KO CP1, CP4 ×2) | 41 |
| sniper | OK | 167 |
| sniper-paper | OK | 167 |
| sniper-uscite-auto | OK | 167 |
| uscite-manuali | OK | 229 |
| uscite-manuali-firmate | OK | 53 |

**Controlli mai sollecitati**, dichiarati «non lo so» come prima:
- K2 e S7 nel `base` (S7 è sollecitato nello scenario `riavvio`);
- CP2: lo scalper non scrive `hedged_size`;
- S6 fuori da `base` e `paper`;
- su 35760084 il bot non entra: 14 controlli.

**Tempi, totale ≈ 1493 s: LENTO** (tetto 600 s).

| lotto | tempo |
|---|---|
| A1 | 225 s |
| A2 | 269 s |
| B1 | 412 s |
| B2 | 391 s |
| B3 | 196 s |
| C | 17 s |

Difetto del banco, non toccato per ordine del coordinatore: proposte nel §9.

### §B. Proposta per l'utente (non fatta: sarebbe una scelta di strategia)
Dopo la morte di un processo di sessione, oggi la posizione della sessione morta resta a mercato DICHIARATA (avviso CRITICAL `SCALPER_SESSIONE_ORFANA`) e la chiude l'utente. Nel replay, uccisa a metà della finestra pre-match con una posizione abbinata aperta, 22 ordini della sessione morta non sono seguiti da nessun processo.

L'alternativa: la sessione nuova ADOTTA gli ordini della morta e li chiude col flatten.

Il valore in euro di quella posizione non l'ho misurato: va sondato prima di decidere.

Delegato, ramo del worktree `agent-a8a111b7f6a26f75e`.
Commit: e632f79 (correzione), 4d47534 (merge di master 4dd624a), 24eb499 (minimi solo da `minimi_it`).

## VERDETTO

**CERTIFICATO su 13 scenari su 15** della registrazione 35797769, più `base` e `paper` su 35760084.

**Non certificati due scenari**, entrambi KO già su master prima di questo lavoro:
- `riavvio` (S7);
- `chiusura-abbinata-in-parte` (CP1, CP4).

**Restano da decidere (coordinatore e utente):**
- 22 test vecchi rossi: pretendono chiusure al centesimo impossibili su .it (vedi §6);
- il banco è sopra il tetto dei tempi (vedi §9).

Il verdetto è mio: il coordinatore deve rifare replay e falsificazioni.

---

## 1. Causa del KO (immutata dal primo referto)

Bisezione fatta col replay `base`:

| commit | esito | azioni |
|---|---|---|
| ff555fb | OK | 43 |
| e255676 | OK | 43 |
| **09072ca** (02/10) | **KO 7** | 538 |

- `09072ca` non tocca lo scalper.
- Rende fedele il banco: `minimi_banco` rifiuta come Betfair .it gli ordini sotto i minimi.
- È un **difetto del BOT**, rivelato dal banco. Le uscite esatte mandavano al place-and-trim resti sotto 0,50, e Betfair li rifiuta (misura sul conto del 13/09).
- Conseguenze:
  - il bot seguiva un sostituto inesistente (K1);
  - il residuo veniva dimenticato al reset del ciclo (K5, B2);
  - la banca diretta da 0,50, minimo copiato nello scalper, era rifiutata a ogni giro (1905 rifiuti nel primo tentativo).
- Dettaglio delle 7 violazioni: `replay/scalper_calcio_base_sonda_7_violazioni.txt`.

---

## 2. Correzione (bot; strategia, stake, soglie e tempi invariati)

### Minimi solo dalla fonte unica (`scalper_bot.py`, `sniper_bot.py`)
- `spezza_uscita(side, price, size)` divide ogni uscita in parte diretta, place-and-trim e residuo.
- Lo fa solo con `trading/minimi_it.importo_piazzabile`.
- Tolti i duplicati:
  - `_side_min` (2,00 / 0,50);
  - `_size_direct_ok` a multipli per tutti;
  - `MIN_STAKE` 2,00 di scalper e sniper, ora 1,00 da `minimi_it`.
- Un'uscita esatta piazzabile parte all'importo esatto (banca 1,35, non 1,50).
- **Arrotondamento al multiplo più vicino.** Non toccato: resta su ingressi e uscite non esatte, come prima. Nel replay ha arrotondato **0 volte** in `base`, `uscite-manuali` e `uscite-manuali-firmate` (sonda su `_place`): lo stake è 25 intero. Lo sniper su questa partita non apre, quindi non è misurato.

### Residuo ricordato (decisione 1)
- `_ricorda_residuo` emette UNA riga CRITICAL `residuo_ricordato` con il totale, i due esiti e la proposta.
- I campi `residuo_w` / `residuo_l` dello slot non si azzerano mai nel `_reset`.
- `_tutto_residuo` fa dichiarare SUBITO il residuo: prima la «ultima spiaggia» aspettava 12 tentativi.
- `_place_exact` non avvia mai un place-and-trim sotto 0,50.
- Sniper: stessa spartizione. Gli ordini restano già tracciati fra i cicli; `_dichiara_residuo` emette la riga CRITICAL. La «ultima spiaggia» ora termina (prima ripeteva `min_bet_skip` a ogni book).

### Freno sui rifiuti di taglia
- `_leggi_rifiuti_taglia` legge `responses.place_response.error_code == INVALID_BET_SIZE`.
- La chiusura non si ripiazza prima di 1, 2, 4, 8, 16, poi 30 s di mercato.
- Riga CRITICAL al primo rifiuto, WARN ai successivi.
- Per un ingresso rifiutato si arma il freno degli ingressi esistente.

### Soldi veri solo col pulsante (decisione 2)
- `scalper_session.freno_soldi_veri` usa `execution._live_brake`: kill-switch più modo effettivo, cioè tetto × «Ordini reali».
- `non_partire_senza_soldi_veri`: una sessione in soldi veri non parte senza «Ordini reali» in soldi veri. Nessun login, riga `stopped` col motivo, log `critical`.
- Il freno è iniettato in maker e sniper (`freno_live`). Ogni APERTURA live lo chiede; le chiusure partono sempre.
- Supervisore (`scalper_service.giro_auto`): con l'interruttore in soldi veri e «Ordini reali» non in soldi veri non arma niente, e `motivo_blocco` lo dice. Mai un ripiego automatico, né in prova né in soldi veri.

---

## 3. Controlli del banco adeguati (prima → dopo)

### B3 (`scalper/certificazione.py::_legale_it`)
- **Prima:** «size multipla di 0,50 e non sotto il minimo del lato (BACK 2,00 / LAY 0,50)».
- **Dopo:** legale se `minimi_it.importo_piazzabile` lo fa partire diretto, così com'è, senza residuo. Quindi punta ≥ 1,00 a multipli di 0,50, banca ≥ 1,00 al centesimo.
- Stessa fonte del bot; il rifiuto vero resta di `minimi_banco`.

### K5 / B2 (`tolleranza_slot`)
- **Prima:** 0,02, oppure `max(0,30; residuo accettato + 0,02)` nel solo ciclo corrente.
- **Dopo:** in più il residuo RICORDATO dal bot, `max(prima; 0,02 + |residuo_w − residuo_l|)`, al centesimo.
- Un residuo non dichiarato resta violazione. Test M9: la mutazione dà 5 rossi.

### UF2 (`backtest/uscite_manuali.py`, file condiviso)
- Nuovo parametro `soglia_resto`, di serie 0,05: il tennis è invariato.
- Lo scalper passa 0,50, cioè `SUBMIN_IMPORTO_FINALE_MIN`.
- **Prima:** era scusato solo un resto dichiarato sotto 0,05.
- **Dopo, per lo scalper:** è scusato un resto dichiarato dal bot (`min_bet_skip`) sotto 0,50. Senza dichiarazione resta violazione.
- Senza questo, `uscite-manuali-firmate` era KO con UF2 ×4 (es. proposta 24,42 → punta 24,00 + 0,42 dichiarato).

---

## 4. Scenari: esito e confronto (dopo il merge di master 4dd624a)

Riferimenti: 29/09 = S4, referto OK; 04/10 HEAD = e578802 prima della correzione.

| scenario | prima del fix (04/10 HEAD) | dopo | 29/09 S4 |
|---|---|---|---|
| base | KO B2 K1×4 K5×2, 538 az. | **OK**, 167 az. | OK, 43 az. |
| paper | KO idem | **OK**, 167 | OK, 43 |
| auto-live | KO idem | **OK**, 167 (client reale) | — |
| senza-missione | KO B2 K1×7 K5×4 | **OK**, 167 | — |
| bot-fermo | KO K1×4 K5×2 | **OK**, 103 | — |
| kill-switch | KO K1×4 K5×2 | **OK**, 103 | — |
| esiti-ignoti | KO B2 K1×4 K5×2 | **OK**, 167 | — |
| rifiuti-betfair | KO B2 K1×4 K5×2 | **OK**, 179 | — |
| riavvio | KO B1×14 B2 K1×6 K5×6 S7 | **KO S7×1** | — |
| chiusura-abbinata-in-parte | KO B2 CP1 CP4×2 K1×2 K5 | **KO CP1×1 CP4×2** | — |
| sniper | KO B2 K1×4 K5×2 | **OK**, 167 | — |
| sniper-paper | KO idem | **OK**, 167 | — |
| sniper-uscite-auto | KO idem | **OK**, 167 | — |
| uscite-manuali | KO K1×1 | **OK**, 229 | OK, 242 |
| uscite-manuali-firmate | KO B2 K1×12 K5×5 UF2×21 | **OK**, 53 | OK, 72 |
| 35760084 base / paper | — | **OK**, 0 azioni (non entra) | OK, 0 |

Azioni diverse dal 29/09 (167 contro 43 sul base):
- la condotta cambia per le regole dei minimi: banca diretta al centesimo, punta per difetto, nessun place-and-trim sotto 0,50, residui chiusi e ricordati;
- di conseguenza cambiano anche cicli (10 contro 4) e scratch (14 contro 3);
- nel `base` scatta il `loss_cap` (−1,61 sul tetto 1,5). Il 29/09 non è registrato se scattasse.

Non ho confronti riga per riga col 29/09: le regole dei minimi sono cambiate e i numeri non possono coincidere.

**I due KO rimasti, entrambi già presenti su master:**
- **riavvio S7:** «22 ordini della sessione morta (abbinato o vivo) non governati né dichiarati dalla nuova sessione (primo: LAY 58805 @4,2 abbinato 25,00)». È la governance degli orfani dopo un riavvio. Non toccata (fuori dalla causa); da aprire come cantiere.
- **chiusura-abbinata-in-parte CP1 e CP4:**
  - CP1: «chiusura colpita abbinata 10,00 con residuo 0,00: NESSUNA riga/credenza del bot la riconosce»;
  - CP4 ×2: ripiazzi dopo la chiusura colpita.
  Da aprire come cantiere.

---

## 5. Residui lasciati a mercato nel replay (euro, fine sessione, per selezione)

Ogni coppia è «se vince / se perde» la selezione. I residui sono dichiarati CRITICAL e ricordati.

### `base` (identico in paper, auto-live, sniper ×3, senza-missione, esiti-ignoti)
Fonte: `replay/scalper_calcio_sonda_residui_base.txt`.
- Match Odds 1.259819674, selezione 22: −0,17 / +0,26;
- mercato 1.259819682, selezione 47973: −0,13 / −0,04;
- mercato 1.259819682, selezione 47972: −0,59 / +0,48.

**Caso peggiore circa −0,89 EUR** in tutto, su due mercati distinti. In sei episodi dichiarati.

### `uscite-manuali` (residui forzati a fine finestra dalle protezioni)
- selezione 22: −0,12 / +0,30;
- selezione 58805: −2,00 / −1,00;
- selezione 47972: −0,59 / +0,48;
- selezione 47973: −1,11 / −0,50;
- selezione 1222345: −1,70 / −1,00.

Il caso peggiore è di qualche euro, ma la parte negativa su entrambi gli esiti è perdita già fatta (le gambe sono abbinate). La parte non piazzabile è solo lo sbilancio fra i due esiti.

### `uscite-manuali-firmate`
- selezione 22: −0,20 / +0,30.

---

## 6. I 22 test vecchi rossi (non adattati: decide il coordinatore con l'utente)

Ogni test è rosso nelle due varianti, ritardo 1 e 4. Tutti pretendono una chiusura esatta che su .it richiede punte non multiple di 0,50 o rimpiazzi sotto 0,50, oppure presuppongono una sequenza place-and-trim che con le regole nuove non parte.

### `test_cantiere_s_scalper_ko_2026_09_29.py`
- **`test_flatten_non_dichiara_chiuso_con_sequenza_o_ordini_vivi[0.2]`:** LAY 0,20 @2,22. La chiusura è una punta da 0,20, sotto 0,50: ora residuo ricordato (|w−l| 0,44). Il test vuole ≤ 0,02.
- **Stesso test `[25.0]`:** LAY 25 @2,22. La chiusura è una punta da 25,23 → 25,00 + 0,23 residuo (|w−l| 0,50). Il test vuole ≤ 0,02.
- **`test_reperto_35797769_nessuna_chiusura_doppia_col_taglio_in_volo`:** LAY 1,98. La chiusura è una punta da 1,98: prima andava al place-and-trim, ma una punta non multipla è rifiutata su .it. Ora 1,50 diretta + residuo, e il test vieta la punta diretta.
- **`test_sostituto_del_rimpiazzo_agganciato_mai_posizione_rovesciata`:** LAY 25. Il resto è 0,23, nessun sostituto, ma il test vuole il sostituto.
- **`test_parcheggio_orfano_si_ritira_e_la_chiusura_parte`:** LAY 25. Il test vuole la chiusura esatta, ora resta un residuo di 0,23.
- **`test_parcheggio_ritirato_prima_del_taglio_non_blocca_la_sorveglianza`:** LAY 1,00. La punta da 1,00 è ora diretta (minimo 1,00), quindi il presupposto «la sequenza deve partire» cade.

### `test_cantiere_s_bis_sniper_2026_09_29.py`
- **`test_il_parcheggio_della_sequenza_non_si_ritira_a_ogni_book`:** punta 3,3. La chiusura è una banca al centesimo, diretta: nessuna sequenza.
- **`test_parcheggio_ritirato_prima_del_taglio_non_blocca_la_chiusura`:** punta 0,4. La banca da 0,4 è sotto 0,50: residuo, nessuna sequenza.
- **`test_fine_finestra_a_prezzi_assenti_mai_residuo`:** punta 10 @1,5. Dopo l'abbinamento a prezzo migliore resta una banca da 0,48: residuo ricordato invece della chiusura esatta.

### `test_cantiere_s3_critical_e_replacing_2026_09_29.py`
- **`test_sniper_nessun_critical_nella_pausa_fra_due_sequenze`:** banca da 0,40, sotto 0,50: residuo dichiarato, non c'è sequenza.

### `test_cantiere_s4_scratch_firmato_esatto_2026_09_29.py`
- **`test_scratch_firmato_parte_esatto_subito_dopo_la_target`:** scratch punta 2,80 → 2,50 + 0,30 residuo (punta per difetto). Il test vuole 2,80.

**Proposta:** riscriverli sotto la regola di `minimi_it`, con la chiusura dichiarata e il residuo ricordato. Vanno riscritti, non solo cambiate le soglie.

---

## 7. Test (fuori dai 22 del §6)

### File nuovo `Betfair/stream/tests/test_scalper_residui_e_soldi_veri_2026_10_04.py`
31 casi, bot VERO su Flumine VERO con `minimi_banco` montato:
- spartizione (9 casi);
- minimi dalla fonte unica;
- residuo ricordato oltre il ciclo;
- caso del replay 2,80;
- banca fra 0,50 e 1,00 al place-and-trim;
- dichiarazione subito;
- banca esatta;
- sniper col freno;
- tolleranza del banco;
- freno dei rifiuti di taglia;
- aperture ferme con «Ordini reali» in prova;
- sessione live (LIVE / PAPER / OFF);
- cablaggio di `run_session`.

### Test esistenti modificati (motivo nel testo di ognuno)
- `test_scalper_bot.py::test_size_direct_ok_regole_it`: regole nuove.
- `test_sniper_bot_2026_07_10.py`: 5 test sulle regole nuove (banca al centesimo, residuo sotto 0,50, minimo 1,00).
- `test_scalper_certificazione_2026_09_24.py`:
  - `test_b3_legalita_it`: parametri delle regole nuove;
  - fixture `soldi_veri_dichiarati` sui 2 test di parità che armano una sessione live.
- `test_scalper_auto_mode_2026_09_25.py`:
  - la fixture `_ambiente` dichiara «Ordini reali» = soldi veri senza DB (`_freni_da_banco`);
  - più un test nuovo parametrizzato PAPER / OFF.
- `test_banco_uscite_manuali_n3_2026_09_28.py`: un test nuovo `soglia_resto`; quelli esistenti sono invariati.

### Comandi
- Mirati: `pytest Betfair/stream/tests Betfair/stream/scalper -k "scalper or sniper or cantiere_s or uscite_manuali or minimi"` → 797 verdi, 22 rossi (quelli del §6).
- Suite completa `Betfair/stream/tests Betfair/stream/scalper Betfair/stream/backtest`: vedi §10.

### Reperto fuori dal mio perimetro
`test_banco_ambiente_dichiarato_2026_10_02.py::test_coda_stesso_referto_con_ambiente_principale_e_ambiente_vuoto` (Safe) è rosso anche su master 8a40f5c, rilanciato da me in un albero esportato.

---

## 8. Falsificazione

Ripristino ogni volta da patch, con `MUTAZIONE` = 0. Test usati: il file nuovo, `auto_mode` e `uscite_manuali`.

| # | mutazione | test rossi |
|---|---|---|
| M1 | punta non arrotondata per difetto (diretta = chiesto) | 4 |
| M2 | il reset del ciclo dimentica il residuo | 6 |
| M3 | niente dichiarazione immediata del tutto-residuo | 2 |
| M4 | niente freno sui rifiuti di taglia | 2 |
| M5 | aperture live senza `freno_live` | 2 |
| M6 | la sessione live parte senza «Ordini reali» | 2 |
| M7 | minimi copiati di nuovo (2,00 / 0,50) | 1 |
| M8 | nessuna riga CRITICAL del residuo | 6 |
| M9 | K5/B2 ignorano il residuo ricordato | 5 |
| M10 | il supervisore arma in soldi veri senza «Ordini reali» | 2 |
| M11 | place-and-trim anche sotto 0,50 (il difetto del replay) | 8 |
| M12 | uscita esatta arrotondata al multiplo di 0,50 | 2 |
| M13 | freno non iniettato nella sessione | 1 |
| M14 | sniper senza freno sulle aperture | 1 |
| M15 | UF2 con soglia fissa 0,05 | 1 |

---

## 9. Tempi del banco (ogni replay dentro `timeout 900`, uno alla volta)

| lotto | scenari | tempo |
|---|---|---|
| A1 | 5 scenari | 238 s |
| A2 | 5 scenari | 316 s |
| B1 | sniper + sniper-paper | 380 s |
| B2 | sniper-uscite-auto + uscite-manuali | 352 s |
| B3 | uscite-manuali-firmate | 138 s |

- **Totale 15 scenari ≈ 1424 s: LENTO**, tetto 600 s. Prima della correzione era 1704 s.
- Il PC era condiviso con i replay di Mike di un'altra sessione: i tempi sono sporchi.

**Profilo** (`cProfile`, scenario `sniper`, 485 s sotto profilo, 1,51 M book): i quattro scenari con sniper e uscite manuali girano 1,5 M book (fino a KO+130') contro 0,67 M del base.

| punto caldo | tempo (cumulativo) |
|---|---|
| `_a_flumine` del banco (flumine più middleware) | 226 s |
| `gira_specchio` → `live_trading_strategy._mirror_orders` / `_order_row` (921 k chiamate) | 96 s (20 %) |
| `valuta.converti_libro` (GBP→EUR su ogni livello di ogni book, anche col cambio non letto) | 53 s (11 %) |
| middleware simulato di flumine `_process_runner` | 42 s |
| `scalper_bot._update_flow` | 44 s |

Proposte, non fatte:
- specchio solo sugli ordini cambiati;
- `converti_libro` saltato a cambio 1,0;
- referto da confrontare numero per numero.

---

## 10. Non verificato / limiti

- **Nessuna prova dal vivo.** «Ordini reali» è provato con `dichiara_per_banco`, senza DB vero.
- **Residui di riavvio e chiusure parziali.** S7 e CP1/CP4 sono KO, non corretti.
- **Lo sniper non opera** su questa registrazione: i suoi rami nuovi (residuo, freno, regole) sono provati solo nei test, non nel replay.
- **Arrotondamento al più vicino.** 0 casi nel replay; dove vale:
  - ingressi: `_place` con `floor_min`, e `size_step` 0,50 su `stake`;
  - uscite non esatte: con `exact_exits` spento (mai in sessione).
  Con uno stake non multiplo di 0,50 dalla UI arrotonderebbe per eccesso fino a +0,25 a ingresso.
- **Mostrare il residuo nella UI** non è fatto: oggi esce come attività CRITICAL. In stats non c'è un campo dedicato.
- **Scenario di banco «Ordini reali in prova»** non aggiunto: ci sono solo i test.
- Suite completa: esito in coda (§11).

---

## 11. Suite completa

Comando: `pytest Betfair/stream/tests Betfair/stream/scalper Betfair/stream/backtest -q -p no:cacheprovider`.
Esito: **3556 verdi, 24 rossi, 25 saltati, in 258 s.**

I 24 rossi:
- **22** sono i test del §6;
- **1** è `test_stato_mercato_freno_2026_09_24.py::test_d7_i_due_residui_accettati_si_dichiarano[13-flatten_residual_forced]`:
  - stesso motivo del §6, quindi 23 test vecchi in tutto;
  - il caso è una punta da 1,03, che col minimo copiato 2,00 era «non piazzabile» e andava alla «ultima spiaggia»;
  - con il minimo 1,00 di `minimi_it` diventa 1,00 diretta + 0,03 di residuo, quindi è piazzabile e non va accettata come residuo;
  - non adattato;
- **1** è il test Safe `test_banco_ambiente_dichiarato…`, rosso anche su master 8a40f5c.
