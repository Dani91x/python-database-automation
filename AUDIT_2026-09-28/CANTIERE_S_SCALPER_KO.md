# CANTIERE S (29/09/2026) - scalper CALCIO: posizione aperta al fischio col bot che si crede chiuso

Worktree `agent-a33555648dadfee29`, base `1fa2915`; `origin/master` (`0e0dd65`) aggiunge solo documenti, e il
bot è identico. Niente commit, niente push. Il DB non è stato toccato e Betfair non è stato chiamato.
Replay lanciati: tre, uno alla volta, tutti scenario `base` sulla partita 35797769.

## 1. Causa radice (con la prova)

### 1.1 Il reperto B2/K5 (sbilancio 4,44 sulla selezione `('1.259819682', 47972)`)

**Prova.** Sonda di sola osservazione sul punto d'ingresso unico: `cantiere_s/sonda_s.py`, lanciata da
`cantiere_s/sonda.sh`. Avvolge `_emit` e `process_market_book` della classe vera senza cambiarne il
comportamento. Il codice è quello di master. La traccia è in `cantiere_s/traccia_master.txt` e le
righe citate sono le sue.

Quando: **KO-3573 s**, un'ora prima del fischio. Il fischio ha solo trovato la posizione lasciata lì.

1. **La posizione.** Il maker (QUOTING2) ha una LAY 25 @2,22 abbinata per 1,98. Posizione: se vince
   -2,42, se perde +1,98.
2. **Il force-flat.** Scatta il `loss_cap` (evento), cioè il force-flat. Il flatten serve un BACK 1,98
   @2,22, sotto il minimo di 2,00. Il place-and-trim parte: `submin_start`, parcheggio BACK 2,00
   @1000.
3. **La chiusura doppia.** Al gradino 2 (taglio = cancel parziale) il parcheggio passa a
   `Cancelling`.
   - `_has_live` riconosce solo PENDING/EXECUTABLE: per lui il parcheggio è morto.
   - `_drive_flatten` non aspetta più la sequenza e piazza una **seconda chiusura, diretta**: `place`
     BACK 2,00 @2,20, abbinata a 2,22.
   - La posizione è già piatta: traccia `B ... se_vince=0.02 se_perde=-0.02`.
4. **Il sostituto non agganciato.** La sequenza prosegue: TRIMMED, poi REPRICED (`replace` a 2,22),
   poi DONE, e **esce da `slot.submins`**.
   - Il SOSTITUTO del replace nasce dopo: BACK 1,98 @2,22 (`'SOST'`), subito abbinato.
   - **Nessuno lo aggancia**: nella traccia ha la marca `-`, non `T`. Lo stesso difetto T6 dello
     scalper tennis.
   - A mercato adesso: se vince +2,44, se perde -2,00 (traccia `B ... sbil=4.44`). Un BACK 2,00 nudo.
5. **Lo slot DONE.** Il bot vede solo gli ordini tracciati: +0,02/-0,02.
   - `min_bet_skip` LAY 0,02, poi `flatten_residual` «residuo accettato 0,04»: slot **DONE** con
     `residual_ok`, tolleranza 0,30 (quella del referto).
   - La sorveglianza DONE e il flatten pre-KO (`flatten_before_s`) guardano solo gli ordini tracciati:
     il BACK 2,00 per loro non esiste e arriva al fischio. Da qui B2 x1 e K5 x1.

**Esclusi, con prova.**
- Stream muto (J2) e cancello delle uscite (N): la sequenza non li tocca. Il replay del coordinatore su
  `82239df`, senza N né J2, dà lo stesso esito.
- Il flatten pre-KO «senza prezzo»: al fischio la posizione era invisibile, non senza prezzo.
- Quanto a D2: la catena è place-and-trim (`exact_exits` dello scalper calcio), cioè il gemello dei
  difetti del cantiere T.

### 1.2 UF2 x14 «proposta 24,42, ordini nuovi 0,00»: il difetto è del BOT, non del controllo

- **La causa.** `_open_lock` piazza la close a target con `slot=slot`. Dall'11/07 (`802040f`,
  anti-orfani) `_place` traccia in `flatten_orders` ogni ordine piazzato con lo slot. Il ciclo LOCKING
  «vecchie close sostituite» (`93f1671`, 02/07) ritira ogni ordine vivo di `flatten_orders`: così la
  close CORRENTE muore al book dopo, insieme all'aggiunta di pre-dimensione e al suo parcheggio.
- **L'effetto su UF2.** L'uscita firmata parte ma viene ritirata subito: abbinato 0 + residuo 0, cioè
  «ordini nuovi 0,00».
- **Vale anche in AUTOMATICO.** Ogni close di `_open_lock` (ingresso join, fill parziali, scratch) muore
  e il ciclo finisce a stop o timeout.
- **Dove non tocca.** Il percorso maker a due gambe, dove la close è la gamba opposta piazzata senza
  slot.
- **La prova.** `sonda_close.py` sul banco di test: la close passa a `Cancelling` al primo book, in
  automatico e con la firma. Il test nuovo `test_la_close_a_target_resta_...` è ROSSO su master e VERDE
  ora.

### 1.3 Trovato durante il lavoro: la protezione si arrendeva a prezzi assenti

In `_drive_flatten`, quando la chiusura non parte (prezzi del lato assenti, mercato fermo, pausa di
30 s fra due sequenze), la «ULTIMA SPIAGGIA» dopo 12 tentativi **accettava come residuo l'intera
posizione**, qualunque fosse l'importo. Col book vuoto lo slot andava DONE comunque.

**La prova.** Test `test_al_fischio_..._interrotto[*-True]`: ciclo in LOCKING a KO-200 s e prezzi assenti
da KO-190 a KO-110. Su master la LAY 25 @2,22 viene «accettata» (sbilancio 55,50), lo slot va DONE
e resta aperto al fischio. Poi `_reset` la dimentica.

## 2. Cosa ho cambiato (solo `Betfair/stream/scalper/scalper_bot.py`)

Nessuna soglia toccata: stake, tick, stop, `flatten_before_s`, 0,02, 0,25, 0,30, 30 s, 5 sequenze, 12
tentativi restano uguali.

1. **`_vivo_o_in_volo` (nuovo).** Vivo oppure con cancel/replace IN VOLO (CANCELLING, UPDATING,
   REPLACING), gli stessi stati del gemello tennis. Si usa dove «morto» porta a una decisione
   irreversibile:
   - l'attesa del flatten prima di una nuova chiusura (causa del punto 3 in 1.1);
   - la chiusura dichiarata a posizione piatta;
   - il reset del ramo DONE;
   - il reset di `_handle_cancelling`;
   - il LOCKING a ciclo pari.

   `_has_live` resta com'era per le decisioni di «ritira».
2. **`_drive_submins`: i sostituti.** A ogni book aggancia a `flatten_orders` gli ordini dei Trade già
   tracciati, cioè i sostituti (T6). Una sequenza in PLACED o TRIMMED col parcheggio morto si chiude e
   si dichiara (`submin_abort`): prima aspettava per sempre e il DONE saltava la sorveglianza (T7).
3. **`_drive_flatten`.** Quattro correzioni:
   - a posizione piatta, con ordini vivi o in volo o sequenze, le sequenze si chiudono, gli ordini si
     ritirano e il DONE arriva dopo (T1);
   - un parcheggio ORFANO (fuori da ogni sequenza in corso) si ritira nello stale (T8);
   - con una sequenza appena avviata non si «accetta il residuo» (T2);
   - la ULTIMA SPIAGGIA accetta solo ciò che il suo commento promette (`_resto_davvero_non_piazzabile`):
     prezzo del lato presente, chiusura sotto il minimo diretto, sequenze del ciclo esaurite (tetto 5
     invariato). Altrimenti lo slot resta FLATTENING, riprova a ogni book (gli ordini vivi li ritira già
     la testa della funzione) e scrive UNA riga CRITICAL `flatten_bloccato` per episodio. Tolto il
     «book vuoto: DONE».
4. **LOCKING.** Due correzioni:
   - il ciclo delle vecchie close NON ritira la close corrente, le aggiunte di pre-dimensione (stesso
     lato e quota) e gli ordini di una sequenza in corso (`_ordini_della_close`);
   - a ciclo pari con un ordine vivo o in volo o una sequenza nello slot non si chiude: si decide al book
     dopo (T9).
5. **`_Slot.chiusura_bloccata_detta`** (nuovo): azzerato al reset e quando una chiusura parte.

**File toccati:** `Betfair/stream/scalper/scalper_bot.py`.

**File nuovi:**
- `Betfair/stream/tests/test_cantiere_s_scalper_ko_2026_09_29.py`
- `AUDIT_2026-09-28/CANTIERE_S.patch`
- in `AUDIT_2026-09-28/cantiere_s/`: `falsifica_s.py`, `falsificazione_esito.txt`, `sonda_s.py`,
  `sonda.sh`, `replay_base.sh`, `sonda_close.py`, `dbg_s.py`
- sempre in `cantiere_s/`, le tracce e i referti: `traccia_master.txt`, `sonda_master.out.txt`,
  `replay_prima.out.txt`, `replay_dopo.out.txt`, i diari
- sempre in `cantiere_s/`, le copie di lavoro, da NON integrare: `scalper_bot_wip.py.txt`,
  `patch_prima.diff`, `wip_bot.diff`

**Fuori perimetro, non toccati:** `scalper_session.py` (non serviva) e `sniper_bot.py` (vedi par. 6).

## 3. Test e falsificazione

**Come girano i test.** Il bot VERO con i parametri della sessione (`VALIDATED_PARAMS`: uscite esatte,
multipli 0,50, minimi .it) gira su un **Flumine VERO** col client paper della sessione
(`_order_client_kwargs(True)`: esecuzione e middleware simulati di flumine).
- I book sono mcm Betfair letti dal `StreamListener` di betfairlightweight, con volume scambiato
  cumulativo.
- Il bot li riceve SOLO da `process_market_book`.
- L'esecuzione è differita di **1 e 4 book** (fixture `esecuzione_differita` del cantiere T) e
  `time.time` segue l'orologio di mercato, come nel banco.
- A ogni book si controllano K5/K6 (slot chiuso: sbilancio entro `certificazione.tolleranza_slot` +
  0,02 per ciclo, niente vivi, niente sequenze) e B2 (dopo il fischio: sbilancio entro la tolleranza,
  nessun ingresso vivo).
- I finti non esistono: ordini e mercato sono di flumine, le righe sono quelle di
  `certificazione.riga_ordine`.

**I numeri:**
- `.venv/Scripts/python.exe -m pytest Betfair/stream/tests/test_cantiere_s_scalper_ko_2026_09_29.py -q -p no:cacheprovider`:
  **26 passed**, circa 4 s. Sul bot di master: **18 failed, 8 passed**, e tra i rossi c'è il reperto
  `test_reperto_35797769_...` a ritardo 1 e 4.
- File collegati (`Betfair/stream/tests/test_scalper_*.py` + contratto strada unica + proposte coi numeri
  + stato mercato/freno + banco uscite manuali N3): **391 passed**, 25 s.
- Altri test scalper/sniper/submin (non tennis): **187 passed**, 10 s.
- `.venv/Scripts/python.exe AUDIT_2026-09-28/cantiere_s/falsifica_s.py`: **9 mutazioni, 9 ROSSE**.
  Ripristino con sha1 uguale e 0 `MUTAZIONE`. Esito in `cantiere_s/falsificazione_esito.txt`.

**Le mutazioni:**
- S1: in volo = morto
- S2: sostituto non agganciato
- S3: residuo accettato a sequenza avviata
- S4: piatta con vivi, DONE
- S5: LOCKING ritira la close corrente
- S6: sequenza col parcheggio morto
- S7: LOCKING con parcheggio pendente
- S8: ULTIMA SPIAGGIA accetta tutto
- S9: parcheggio orfano saltato

**Replay (scenario base, 35797769):**
- **prima** (master): KO, B2 x1 e K5 x1, 4,44, azioni 92 (`cantiere_s/replay_prima.out.txt`);
- **dopo:** vedi par. 9.

## 4. Migrazioni SQL

Nessuna.

## 5. Parità paper/live

Tutte le modifiche sono nel bot, uguali in paper e in live. Il ramo `exact_exits and not dry_run` è
quello di prima, e la sessione paper arma il bot con `dry_run=False` (parità dichiarata dal banco:
83 parametri, 0 diversi).

`_resto_davvero_non_piazzabile` usa `exact_exits`/`dry_run` come `_place`. La riga CRITICAL è la
stessa nei due modi. I test girano col client paper della sessione.

## 6. Cosa NON ho fatto e cosa NON ho potuto verificare

- **Scenari non rilanciati.** `paper`, `uscite-manuali`, `uscite-manuali-firmate` e le altre partite: il
  brief mi autorizzava solo `base`. UF2 è dimostrato sul banco di test, non sul replay firmato.
- **`sniper_bot.py` ha gli stessi rami e NON l'ho corretto.**
  - `_has_live` solo PENDING/EXECUTABLE (riga circa 1069).
  - Nessun aggancio dei sostituti in `_drive_submins` (circa 1010).
  - La piatta dichiarata con sequenze o ordini vivi (circa 777).
  - La ULTIMA SPIAGGIA senza condizione di prezzo (circa 805).
  - In più il suo `_drive_flatten` ritira A OGNI BOOK tutti gli ordini vivi di `flatten_orders`,
    parcheggio compreso.

  Serve un cantiere col suo banco (scenari `sniper*`): toccarlo senza replay era peggio.
- **Micro-residui dimenticati al reset (vedi par. 7).** Resta ciò che la strategia decide: un
  residuo ≤ 0,25 accettato (per esempio la sovra-copertura di un flatten a più tick) viene dimenticato da
  `_reset` al ciclo dopo. Il banco lo conterebbe come K5 se supera 0,02 + 0,02 per ciclo. Il test
  `test_parcheggio_ritirato_...` verifica che il residuo dichiarato sia quello VERO, non che non ci sia.
- **Abbinamenti parziali del parcheggio stesso:** non provati. Il book del banco di test ha 50 a ogni
  livello.
- **Betfair live:** il ritiro di un parcheggio orfano senza bet_id (PENDING) si ritenta a ogni giro;
  non verificato dal vivo.

## 7. Decisioni per l'utente

1. **Micro-residuo accettato e poi dimenticato.** Quando lo scalper accetta un micro-residuo (≤ 0,25 di
   perdita possibile, soglia di strategia invariata), al ciclo successivo `_reset` lo dimentica: resta a
   mercato senza padrone, piccolo.
   - Proposta A: lo slot non riparte su quella selezione finché il residuo è aperto (sorvegliato e
     dichiarato).
   - Proposta B: il residuo si porta nel ciclo dopo e lo chiude la chiusura successiva.

   Entrambe cambiano il comportamento di trading: decide l'utente.
2. **ULTIMA SPIAGGIA più stretta** (fatto, perché la protezione non si arrenda).
   - Prima: dopo 12 tentativi si accettava qualunque residuo, anche a prezzi assenti o durante la pausa
     di 30 s fra due sequenze.
   - Ora: solo sotto il minimo diretto, con prezzo, a sequenze esaurite. Nel resto dei casi il bot
     continua a provare e lo dice (CRITICAL).
   - Effetto: in casi rari qualche chiusura esatta in più invece di un residuo accettato.
   - Da confermare, oppure da riportare a «accetta anche in pausa» (solo il vincolo del prezzo resta
     obbligatorio per la sicurezza).
3. **La close a target resta a mercato.** Effetto sul trading, ed è lo scopo della correzione: in
   automatico e dopo la firma la close resta a riposo al target invece di morire al book dopo. Più
   cicli chiusi a target, meno a stop o timeout. I numeri del replay cambieranno per questo.

## 8. Da controllare dal vivo in paper al prossimo avvio

- Attività scalper: righe `flatten_bloccato` (CRITICAL). Attese rare, solo con flusso prezzi
  interrotto; ognuna seguita da `flatten_done` quando tornano i prezzi.
- `submin_abort` con nota «parcheggio non piu' vivo»: rare.
- Specchio `betfair_live_orders`:
  - dopo un `uscita_proposta` target firmato, la close resta `Executable` alla quota target fino
    all'abbinamento;
  - nessuna selezione con slot DONE e sbilancio abbinato oltre 0,30.
- Mai due chiusure (una diretta e un place-and-trim) sulla stessa esposizione nello stesso minuto.

## 9. Replay dopo la correzione

`sh AUDIT_2026-09-28/cantiere_s/replay_base.sh dopo`, cioè `certifica scalper_calcio 35797769
--scenari base --worker 1`, con l'ambiente e i 20 interruttori a 0. Referto:
`cantiere_s/replay_dopo.out.txt`.

| | prima (master) | dopo |
|---|---|---|
| Esito | KO | **OK** |
| Violazioni | B2 x1, K5 x1 | **0** |
| Azioni | 92 | **47** |
| Stati visti | stessi | stessi |

Dopo:
- **Motivi:** place x20, submin_step x12, close_presize x3, scratch x3, **cycle x3**, submin_start x3.
- **Spariti:** min_bet_skip x27, submin_step x18, submin_start x5, stop x3.
- **Controlli:** B2 sollecitato x507, K5 x498, K6 x5666.
- **Mai sollecitati:** K2 e S7, come prima.

Il codice del bot che ha girato ha impronta `4e70ab9d276e`. Dopo il replay ho solo rimesso uno spazio
di allineamento in un commento (`_Slot.swing`): nessuna differenza di comportamento.
