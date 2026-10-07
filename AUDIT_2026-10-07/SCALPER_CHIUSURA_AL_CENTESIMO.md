# SCALPER CALCIO (maker e sniper): chiusure al centesimo (07/10/2026)

Delegato del coordinatore (Opus). Lavoro NON committato nel worktree
`/home/user/python-database-automation/.claude/worktrees/agent-abbefe960f380ce4c` (base `8226d766`).
Ordine dell'utente (07/10): «lo scalper deve chiudere pulito come gli altri bot! questi residui
non hanno senso, controlla il calcolo di uscita, se facciamo back, possiamo uscire in lay al
centesimo!». Regola 10 del brief: chiusure all'importo esatto, mai gonfiate, mai arrotondate.

## 1. Causa radice dei 6 residui sulla 35797769

Diagnostica in sola lettura (via libera del coordinatore): scenario `base` del banco con le
funzioni VERE avvolte per stampare ogni ordine del ciclo chiuso (chiesto, abbinato, prezzo medio,
`size_remaining`, `size_cancelled`, `size_lapsed`, stato). Script e uscite:
`AUDIT_2026-10-07/replay_scalper_chiusura_al_centesimo/diag_ordini.py`, `diag_base_prima.txt`,
`diag_base_dopo.txt`.

Le cause sono tre, tutte nel calcolo/strada di uscita, NESSUNA nella formula del green-up
(`compute_green` e' giusta: size = |se vince - se perde| / quota, sull'ABBINATO):

- **C1 - punta di chiusura tagliata al multiplo di 0,50 col resto buttato** (R1, R3, R5, R6).
  `scalper_bot.spezza_uscita` traduceva `minimi_it.importo_piazzabile` cosi': punta >= 1,00 ->
  diretta al multiplo di 0,50 PER DIFETTO, resto (< 0,50) = "residuo non piazzabile". Ma il
  resto si puo' chiudere: basta scendere di UN passo con la parte diretta e mandare
  resto + 0,50 (fra 0,50 e 0,99) col place-and-trim, che su .it accetta un finale da 0,50 in
  su (`minimi_it.SUBMIN_IMPORTO_FINALE_MIN`). 2,80 -> 2,00 + 0,80, esatto al centesimo.
  Questo NON e' portare la chiusura al minimo (vietato dalla regola 10): la somma e' sempre
  l'importo chiesto.
- **C2 - aggiunta di banca della pre-dimensione sotto il minimo saltata** (R2). Con l'ingresso
  BACK abbinato, la close LAY in coda va portata a `stake x P_entry / P_exit` (25,14). L'aggiunta
  +0,14 e' sotto anche il floor di legge (0,50): `_place_exact` la saltava (`min_bet_skip`), la
  close si abbinava a 25,00 e a fine ciclo restava una banca da 0,13 impossibile. Ma la BANCA
  si piazza al centesimo da 1,00 in su: si piazza LAY 1,14 alla stessa quota e si RIDUCE di
  1,00 la close in coda (cancel parziale, la coda del resto resta). Totale 25,14.
- **C3 - ingresso abbinato sotto 0,50** (R4). BACK abbinata solo 0,29: la chiusura LAY 0,29 e'
  sotto il floor di legge 0,50 (DM 47/2013 art. 8; nessuna tecnica, place-and-trim compreso,
  la piazza). Resta un residuo dichiarato (decisione dell'utente del 04/10 «lo chiudo io»).
  Proposta per chiuderlo comunque in sez. 7.

| # | ora, selezione | ordini veri (dalla diagnostica) | chiusura che serviva | prima | causa | dopo |
|---|---|---|---|---|---|---|
| R1 | 17:02 sel 22 (Spagna) | LAY 25 @1,65 abbinata 2,80 (22,20 annullati); scratch BACK 2,50 @1,65 abbinata | BACK 2,80 @1,65 | 2,50 diretti + 0,30 "residuo" -> -0,195 / +0,30 | C1 | 2,00 + 0,80 place-and-trim: ciclo `scratch_par` 0,00 / 0,00 |
| R2 | 17:27 sel 47973 | BACK 25 @1,85 abbinata; close LAY 25 @1,84; pre-dimensione +0,14 saltata | LAY 25,14 @1,84 | close 25,00 + flatten LAY 0,13 impossibile -> +0,25 / 0,00 | C2 | LAY 1,14 @1,84 + riduzione 1,00 della close: abbinati 24,00 + 1,14 = 25,14, ciclo **verde** `scalp` +0,13 / +0,14 |
| R3 | 17:35 sel 22 | LAY 25 @1,67 abbinata 9,25; scratch BACK 9,00 @1,67 | BACK 9,25 | 9,00 + 0,25 "residuo" -> -0,1675 / +0,25 | C1 | non piu' raggiunto (missione compiuta alle 17:27, vedi sotto); con la regola nuova 8,50 + 0,75 |
| R4 | 17:36 sel 22 | ingresso BACK 25 @1,67 abbinato 0,29 (in annullo) | LAY 0,29 @1,67 | residuo -0,29 / +0,19 | C3 (impossibile per legge) | non piu' raggiunto su questa partita; il caso resta dichiarato, testo corretto |
| R5 | 17:36 sel 47973 | LAY 25 @1,85; BACK 4,54 @1,85 + flatten BACK 20,50 @1,83 | BACK 20,69 | 20,50 + 0,19 "residuo" -> -0,376 / -0,04 | C1 | non piu' raggiunto; con la regola nuova 20,00 + 0,69 |
| R6 | 18:19 sel 47972 (Under 2,5) | LAY 25 @2,22 abbinata 1,98; scratch BACK 1,50 @2,22 | BACK 1,98 | 1,50 + 0,48 "residuo" -> -0,5856 / +0,48: **fa scattare il tetto** (-1,61) | C1 | non piu' raggiunto; con la regola nuova 1,00 + 0,98 |

Effetto sulla partita (diagnostica `base`, prima -> dopo): 19 cicli, 0 verdi, 6 residui, tetto di
perdita a -1,61 alle 18:19 -> **5 cicli, 1 verde (+0,14 alle 17:27), 0 residui, tetto mai
scattato**. Al primo verde la missione «1 tick per fase» (`one_green_per_phase`, invariata) ferma
gli ingressi: per questo R3-R6 non si ripresentano. R3, R5, R6 sono coperti dai test con i loro
numeri.

**Confronto con gli altri bot.** Pro/FLB/swing (`tennis_scalper/condotta_ordini.spezza_esatta`)
spezzano la punta come faceva lo scalper (diretta per difetto + resto < 0,50 dichiarato,
`UsciteEsatte.piazza`): lo stesso residuo teorico esiste anche li', solo che nei loro replay non
capita (ingressi a importo pieno, niente scratch su abbinati parziali). La strada comune che uso e'
la stessa dei tennis per il resto: `trading/submin` (parcheggio, riduzione, rimpiazzo) col
parcheggio al minimo della fonte unica (come `UsciteEsatte.piazza`, `placed_size=IT_BACK_MIN_STAKE`).
Fuori perimetro: proposta per il coordinatore di portare la stessa spartizione in
`condotta_ordini.spezza_esatta` (sez. 6).

**Documentazione Betfair (fonti gia' raccolte nel repo, `AUDIT_2026-10-01/RICERCA_STAKE_MINIMI_BETFAIR.md`
e `RICERCA_TOOL_ITALIA_STAKE_MINIMI.md`; NON riaperte oggi dal web):**
- placeOrders: https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687496/placeOrders
- Betting On Italian Exchange (minimi .it, passo 0,50 della punta):
  https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687808/Betting+On+Italian+Exchange
- cancelOrders con `sizeReduction` e replaceOrders: stessa raccolta (pagine 2687465 / 2687487 del
  link sopra); INVALID_PROFIT_RATIO (banda -20 % / +25 %): articolo di supporto 360010423978
  citato in `trading/submin.py` (`BANDA_PROFIT_RATIO`).
- Floor di legge 0,50 (DM 47/2013 art. 8) e minimi 1,00 punta/banca: Nota informativa betfair.it
  (in `RICERCA_TOOL_ITALIA_STAKE_MINIMI.md`) e decisione dell'utente del 04/10 («SOTTO 1 EURO
  place and trim, 0.50 il minimo; SOPRA 1 EURO multipli di 0.50 in back»).
- Cosa e' davvero impossibile: un ordine (o un finale di place-and-trim) sotto 0,50. E' il solo
  caso C3. Tutto il resto (banca >= 1,00 al centesimo; banca/punta 0,50-0,99 col place-and-trim;
  punta >= 1,50 = diretta multipla + resto 0,50-0,99) si chiude al centesimo.

**Parcheggio del place-and-trim (punto 2 del brief).** Era `placed_size=2.0` scritto a mano in
`scalper_bot._place_exact` e `sniper_bot._place_exact`, LAY sempre @1,01. Ora una funzione sola,
`scalper_bot.stato_parcheggio` (usata da maker e sniper): `placed_size = submin.place_min_size("it",
lato)` (1,00, fonte unica `minimi_it`) e quota `submin.quota_parcheggio_lontano(lato, target)`:
BACK 1000; LAY la quota piu' bassa con la banca residua DENTRO la banda INVALID_PROFIT_RATIO
(0,50 -> 1,02; 0,70 -> 1,03; 0,80 -> 1,01). Il flatten riconosce il parcheggio per appartenenza
alla sequenza e non piu' per quota (`p <= 1.011` tolto: a 1,03 l'avrebbe annullato come stantio).

**Testo del residuo (punto 3).** `_ricorda_residuo` scrive ora l'ORDINE che servirebbe
(«ordine di chiusura LAY 0.29 @1.67 sotto il minimo .it, RICORDATO (differenza fra gli esiti
0.48 ...)») e porta `ordine_size` / `ordine_quota` nel payload. La regola del tetto
(`event_loss_cap`, residuo contato al peggiore) NON e' toccata.

## 2. Cosa ho cambiato (file esatti)

- `Betfair/stream/scalper/scalper_bot.py`
  - `spezza_uscita`: punta non multipla >= 1,50 -> diretta un passo sotto + resto 0,50-0,99 col
    place-and-trim (somma = chiesto). Fra 1,00 e 1,49 non multipla: invariata (resto dichiarato).
  - nuova `stato_parcheggio` (pura) e `_place_exact` che la usa (parcheggio 1,00, LAY in banda;
    None = nessun ordine, resto dichiarato).
  - `_presize_close`: aggiunta di BANCA non diretta -> LAY (aggiunta + 1,00) alla stessa quota e
    riduzione di 1,00 della close in coda (solo con `exact_exits`, non in dry-run, close viva con
    almeno 2,00 da abbinare; altrimenti la strada di prima).
  - scratch: ritira anche la sequenza place-and-trim e gli ordini della close vecchia e aspetta
    che siano morti (CP4: prima il sostituto della close esatta e lo scratch potevano essere due
    chiusure vive insieme; trovato dal test S4 dopo la correzione C1).
  - `_drive_flatten`: il parcheggio si riconosce per appartenenza alla sequenza.
  - `_ricorda_residuo(..., quota=)` + helper `_quota_chiusura`: testo con l'ordine.
- `Betfair/stream/scalper/sniper_bot.py`: `_place_exact` usa `stato_parcheggio` (niente 2,00).
- Test nuovo: `Betfair/stream/tests/test_scalper_chiusura_al_centesimo_2026_10_07.py` (17 test).
- Test vecchi riallineati alla regola nuova (asserivano il residuo, difetto 28 del catalogo),
  con motivo datato nel file: `test_scalper_residui_e_soldi_veri_2026_10_04.py` (2 casi di
  `spezza_uscita` + caso del replay 2,80), `test_sniper_bot_2026_07_10.py` (7,63 e 5,04),
  `test_cantiere_s4_scratch_firmato_esatto_2026_09_29.py` (importo 2,80 esatto; "doppia chiusura"
  = quote diverse o importo vivo oltre lo scratch, perche' una chiusura esatta sono due ordini
  alla stessa quota).
- Referto e allegati: questo file, `AUDIT_2026-10-07/replay_scalper_chiusura_al_centesimo/`.
- NON toccati: `trading/submin.py`, `minimi_it.py`, `media_under_bot.py`, `scalper_session.py`,
  `certificazione.py`, `tools/replay_registrazioni.py`, banco, tennis, frontend.

Strategia invariata: soglie, stake, tick, cicli, missione, tetto identici. Cambia solo come
parte l'uscita (importo esatto invece di importo meno il resto).

## 3. Test e falsificazione

- TDD: test nuovo ROSSO sul codice di prima (13 rossi su 15 al primo giro; i 2 verdi sono i
  casi invariati della banca e della punta multipla), poi VERDE: **17 passati**.
  `python3 -m pytest Betfair/stream/tests/test_scalper_chiusura_al_centesimo_2026_10_07.py -q -p no:cacheprovider`
- Regressione: tutti i test di `Betfair/stream/tests/` con scalper, sniper, submin, minimi,
  uscite, esatte, cantiere_s, banco_scalper nel nome: **1103 passati, 0 rossi** (34 s, dopo il passaggio del codice ad ASCII).
  Tennis non rilanciati: `trading/submin.py` e `minimi_it.py` non toccati.
- Falsificazione (`replay_scalper_chiusura_al_centesimo/mutazioni.py`, una mutazione alla
  volta, file ripristinato da script; esito in sez. 3-bis).

## 3-bis. Falsificazione e replay

**Falsificazione** (script `mutazioni.py`, una mutazione alla volta, file ripristinato dallo
script; dopo: `grep -c MUTAZIONE` = 0 su entrambi i file, `git diff --stat` identico a prima):

| # | mutazione | esito |
|---|---|---|
| M1 | punta: resto < 0,50 lasciato residuo (il difetto C1) | ROSSO 9 |
| M2 | parcheggio 2,00 scritto a mano | ROSSO 8 |
| M3 | parcheggio LAY sempre @1,01 | ROSSO 6 |
| M4 | pre-dimensione: aggiunta di banca sotto il minimo saltata (C2) | ROSSO 1 |
| M5 | scratch che non aspetta gli ordini della close vecchia (solo l'attesa) | VERDE: non catturata, il ritiro da solo basta nel banco di S4 (in quel banco il cancel e' immediato) |
| M8 | scratch che ne' ritira ne' aspetta la sequenza della close vecchia | ROSSO 1 |
| M6 | testo del residuo senza l'ordine | ROSSO 1 |
| M7 | sniper col parcheggio 2,00 | ROSSO 2 |

**Replay** (via libera del coordinatore, uno alla volta, `--worker 1`, sulla 35797769). Comando:
`python3 -m Betfair.stream.backtest.certifica scalper_calcio 35797769 --data-dir /home/user/python-database-automation/_live_raw --scenari base,sniper-paper,chiusura-abbinata-in-parte --worker 1`
(uscita intera: `replay_scalper_chiusura_al_centesimo/replay_dopo.txt`; codice bot `72a48e9f333b` -> `ac2794fa2b81`).

| scenario | prima (riferimento del coordinatore) | dopo | tempo dopo |
|---|---|---|---|
| base | OK, 167 azioni, 6 `residuo_ricordato`, `loss_cap` -1,61 | **OK, 44 azioni, 0 residui, 0 tetto**, 1 ciclo verde +0,14 (missione) | 57,7 s |
| sniper-paper | OK, 167 azioni, 6 residui; sniper +0,73 (pnl_settled 0,75) | **OK, 44 azioni, 0 residui**; sniper IDENTICO (2 fuochi, +0,73, pnl_settled 0,75, piatto) | 206,2 s |
| chiusura-abbinata-in-parte | OK il 04/10 (referto `AUDIT_2026-10-04/CERTIFICAZIONE_SCALPER_CALCIO.md`; NON rilanciato da me sul codice di prima per tempo) | **KO CP4 x3** (217 azioni) | 84,6 s |

**Il KO CP4 e' il controllo del banco, non una sovracopertura del bot (da decidere col
coordinatore, file del banco fuori perimetro).** Esempio stampato: «chiusura BACK ... chiede di
spostare il netto di 1000.00 ... quando da chiudere ne resta 1.21». E' il PARCHEGGIO BACK 1,00 @1000
del place-and-trim: `backtest/chiusura_parziale.py:621` conta la capacita' `size x quota` = 1000.
Il caso era stato previsto dal referto `SCALPER_TENNIS_CP4.md` par. 6.4 («un parcheggio BACK 1,00
@1000 vale 1000 di netto, sarebbe sempre sovrarichiesta: se capitasse, il KO sarebbe del banco»).
Prima di questa correzione lo scalper calcio non faceva MAI place-and-trim di punta (il resto
< 0,50 era residuo), quindi CP4 non lo vedeva. Ho letto un solo esempio dei 3 (il referto ne stampa
uno): gli altri 2 non verificati uno per uno. Proposta per il banco: escludere dalla capacita' di
CP4 un ordine di una sequenza place-and-trim alla quota di parcheggio (BACK 1000), come gia' fa il
bot (`_ordini_in_sequenza`), oppure contare la capacita' di una BACK come `size` (la sua perdita se
perde) invece di `size x quota`. Senza questa decisione lo scenario resta KO.

## 4. Migrazioni SQL
Nessuna.

## 5. Parita' paper/live
Le strade cambiate (`spezza_uscita`, `_place_exact`, `_presize_close` con `exact_exits`, scratch,
testo del residuo) non leggono la modalita': `exact_exits` e' acceso in paper e in live dalla
sessione (`scalper_session`, parametri di produzione), il banco la esercita in `base` (live) e
`paper`/`sniper-paper`. Prova: sez. 3-bis (replay).

## 6. Cosa NON ho fatto / NON ho potuto verificare
1. **C3 (ingresso abbinato sotto 0,50) resta residuo dichiarato**: per legge nessun ordine sotto
   0,50. Proposta (sez. 7) non implementata.
2. **Punta non multipla fra 1,00 e 1,49** (es. 1,27): resta 1,00 + 0,27 dichiarato. Si potrebbe
   chiudere tutta col place-and-trim parcheggiando 1,50 e riducendo a 1,27, ma che Betfair .it
   accetti un FINALE di punta >= 1,00 non multiplo dopo la riduzione non e' documentato ne'
   misurato: non l'ho fatto.
3. **Non verificato dal vivo**: che Betfair .it accetti (a) il resto di punta 0,50-0,99 col
   place-and-trim accanto a una parte diretta (stessa macchina gia' usata per i resti < 1,00);
   (b) il parcheggio LAY a 1,02/1,03 (`quota_parcheggio_lontano`, gia' usato dal motore
   condiviso); (c) la riduzione di 1,00 della close + l'aggiunta di 1,14 (rischio di corsa: se la
   close si abbina tutta prima della riduzione, la posizione e' coperta di 1,00 in piu' e il
   flatten la pareggia con una punta ~1,00).
4. Stessa spartizione da portare in `tennis_scalper/condotta_ordini.spezza_esatta` (pro/FLB/swing)
   e nello scalper tennis: fuori perimetro, proposta per il coordinatore.
5. Il banco non simula INVALID_PROFIT_RATIO ne' il rifiuto del finale sotto 0,50: i replay non
   possono vedere un parcheggio fuori banda; lo vedono i test.
6. Scenari NON rilanciati per tempo (scadenza dell'utente): `paper`, `sniper`,
   `sniper-uscite-auto`, `uscite-manuali`, `rifiuti-betfair`, e la 35760084 (sulla 35760084 il
   maker non opera: 0 azioni nel riferimento).

## 7. Decisioni per l'utente
- **Residuo da ingresso abbinato sotto 0,50 (C3)**: oggi resta tuo («lo chiudo io»). Proposta:
  chiuderlo con DUE ordini legali, una punta 1,00 e una banca al centesimo calcolata coi due
  prezzi (es. R4: punta 1,00 @1,66 + banca 1,28 @1,67 -> piatto al centesimo), costo = lo
  spread su 1 euro (circa 0,01). Cambia il modo di uscire (due ordini invece di uno): decidi tu.
- Il tetto di perdita resta com'e' (decisione in sospeso): con le chiusure al centesimo sulla
  35797769 non scatta piu'.

## 8. Da controllare dal vivo in paper
- Uno scratch su un ingresso abbinato in parte (es. 2,80): attivita' `place` BACK 2,00 +
  `submin_start` 0,80 col parcheggio a 1,00 (non 2,00), poi `submin_step` trimmed/repriced/done;
  nessun `residuo_ricordato`.
- Pre-dimensione di una close LAY: attivita' `close_presize` con `aggiunta` e `riduzione` 1,00;
  nello specchio la close con `size_cancelled` 1,00 e l'aggiunta abbinata alla stessa quota.
- Un eventuale `residuo_ricordato` deve dire «ordine di chiusura LAY/BACK x @q».
