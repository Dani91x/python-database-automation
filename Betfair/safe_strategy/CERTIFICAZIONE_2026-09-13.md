# CERTIFICAZIONE SAFE STRATEGY — 13/09/2026

Verifica capillare del codice contro il manuale delle 4 strategie
(`C:\Users\Admin\Desktop\PYTHON DATABASE\STRATEGY S.txt` → artefatto
`7652e448-f013-4c25-856c-9243221573c1`), dal backend alla UI, più la
**separazione netta paper/live** richiesta esplicitamente.

**Le strategie NON sono state cambiate.** Quello che segue sono difetti di
funzionamento corretti, non riscritture di regole.

---

## 0. La domanda di partenza, e la risposta

> «il sistema usa solo le selezioni BANCA RISULTATO ESATTO CASA E OSPITE,
> mentre ignora totalmente la strategia base e punta»

**È vero, ed è misurabile.** Fotografia del DB il 13/09, storico completo
(240 righe, **tutte `paper`, zero `live`**):

| strategia | trade | note |
|---|---:|---|
| `esatto` | 152 | |
| `tennis` | 79 | |
| **`punta`** | **2** | = 1 posizione (apertura + green-up) |
| **`base`** | **2** | = 1 posizione (apertura + green-up) |

E nel feed, nello stesso momento: **31 partite di calcio in corso, 25 senza
riferimento 1X2 pre-kickoff**. I 6 che ce l'avevano erano tutti al minuto 15-19,
cioè le uniche partite iniziate **dopo** l'ultimo riavvio dello scanner.
Correlazione perfetta.

### Causa radice

`pre_ko` — il riferimento 1X2 congelato prima del calcio d'inizio — **viveva
solo nella RAM dello scanner** (`service.py`, `self.events`).

1. `scanner.freeze_pre_ko` lo cattura **solo prima del fischio d'inizio** e lo
   congela al primo tick in-play (`if inplay: return prev`).
2. `Scanner.__init__` parte con `self.events = {}` e **non rileggeva niente**:
   l'unico accesso al DB in avvio era `list_scan_event_ids()`, che prende solo
   la chiave.
3. Al primo `publish` la riga veniva riscritta con `pre_ko: None` — **il codice
   distruggeva la propria copia sul DB**.
4. Senza `pre_ko` non c'è `pre_match`; senza `pre_match` `favorite_side()` torna
   `None`; i check `favPre`/`dogPre` (base) e `leadFav` (punta) escono
   `ok=None`; `state_from_checks` («null vince su true») produce `"nd"`; il
   candidato viene **scartato prima di diventare segnale**.
5. `esatto` non legge `pre_ko` in nessun punto: era **l'unica a sopravvivere**.

E lo scarto era **muto**: nessun segnale, nessuno skip, niente a schermo.

Ogni riavvio dell'app, ogni crash raccolto dal watchdog, ogni modifica al codice
azzerava tutto: da quel momento, **per il resto della giornata**, base e punta
erano cieche su ogni partita già iniziata.

### Cosa è stato fatto

- `db.load_scan_pre_ko()` — rilettura **mirata** (per event_id, a blocchi di 40,
  sola proiezione `payload->pre_ko`: mai una SELECT su tutta la tabella, che va
  in timeout) + `db.is_usable_pre_ko()`.
- `Scanner.hydrate_pre_ko()` — reidrata le partite di calcio **in corso e senza
  riferimento**, un solo tentativo per evento, best-effort, mai nel percorso
  caldo, **spenta in `dry`**. Chiamata **prima di `publish`**, altrimenti il
  publish distruggerebbe la copia sul DB. Il valore reidratato è marcato
  `rehydrated: true`: non si spaccia per una cattura in diretta.
- Un riferimento catturato dal vivo **non viene mai sovrascritto** da quello
  riletto.
- `SafeEngine.pre_match_missing_events()` + `bot_service._log_pre_match_missing`
  — adesso il bot **scrive** perché non entra: attività `skip` con motivo
  `pre_ko_assente`, tradotto in italiano nella UI.

> Copre riavvii e crash. **Non** copre le partite iniziate mentre l'app era
> completamente spenta: per quelle non esiste nessuna riga da cui rileggere.

### Cosa aspettarsi al primo riavvio (misurato il 13/09 alle 22:4x)
Fotografia del feed in quel momento: **35 partite in gioco, 32 senza riferimento
pre-KO**, con minuti 29, 37, 45, 45, 46, …, 61, 61, 65, 73 — cioè in piena
finestra di BASE (55-62') e PUNTA (66-70'). Eseguendo la nuova
`load_scan_pre_ko` su quelle 32 partite: **32 interrogate, nessun timeout, 0
recuperabili**.

Zero è il risultato **atteso e corretto**: l'app in esecuzione gira ancora con il
codice vecchio, che ha già sovrascritto con «vuoto» la copia sul DB. Il recupero
vale **dal prossimo riavvio con il codice nuovo in poi**. In pratica:

- le partite di **oggi** già in corso restano cieche su base e punta (il dato non
  esiste più da nessuna parte);
- dal riavvio in avanti lo scanner cattura di nuovo `pre_ko` normalmente nei 20
  minuti prima di ogni calcio d'inizio, e da quel momento **il riferimento
  sopravvive ai riavvii**;
- se si volesse recuperare anche le partite già iniziate servirebbe ricostruire
  `pre_ko` da altre fonti già nel DB (`betfair_market_odds`, `engine_signals`,
  `omega_events.model`). È fattibile e non costa chiamate a Betfair, ma è una
  **decisione da prendere**: un riferimento ricostruito non è un riferimento
  congelato in diretta, e farebbe scattare denaro vero su un dato di seconda
  mano. Non è stato fatto.

---

## 1. Esecuzione e denaro

### 1.1 «Qualsiasi importo fino a 0,01 €» non era vero in apertura — **CRITICO**
`bot_service._execute` rifiutava ogni size sotto `min_stake` (2,00 €) **prima**
di `execution.place`: la macchina place-and-trim (parcheggio → taglio parziale →
riprezzo), che esiste ed è collegata, **non veniva mai raggiunta su un'apertura**.
Uno stake di 1,00 € finiva in `size_sotto_minimo_betfair` e dopo 3 tentativi il
segnale era morto per tutta la partita.
→ Ora l'unico pavimento è quello **assoluto dell'exchange**, `X.ABS_MIN_SIZE =
0,01 €`. Quale percorso usare (place normale o place-and-trim) lo decide
`X.place`, che conosce anche il lato. Stessa correzione sulle gambe delle combo.

### 1.2 Le CHIUSURE sotto minimo venivano uccise dal client — **CRITICO**
Sul percorso a coda (che è il default in paper e in live-via-flumine) il worker
chiamava `build_order` **senza** `reduces_liability`: `min_stake_rules`
**solleva** per ogni BACK sotto 2,00 € e **tronca a multipli di 0,50 €** le
altre. Risultato: la gamba di uscita andava in errore e **la posizione restava
esposta fino al settlement** — esattamente ciò che il manuale vieta («si esce
subito e si accetta»).
→ `execution.enqueue_place` marca le chiusure con `params.reduces_liability` e
`live_order_worker._do_place` lo passa a `build_order`. Betfair accetta gli
ordini che riducono una posizione sotto il minimo e senza passo: il flag lo
dichiara. Sulle aperture non c'è mai, quindi il minimo normale continua a valere.

### 1.3 Minimo di piazzamento uguale per i due lati — **ALTO**
`_min_size_live()` tornava 2,00 anche per il LAY, il cui minimo .it è **0,50**.
Ogni LAY fra 0,50 e 2,00 veniva marcato «sotto minimo» e mandato sulla macchina
place-and-trim, che però parcheggia a 0,50 e **solleva**: gamba persa su un
ordine che Betfair avrebbe accettato al primo colpo.
→ `_min_size_live(side)`: BACK 2,00 / LAY 0,50, override `SAFE_MIN_SIZE_LIVE`.

### 1.4 Tick arrotondato nella direzione sbagliata — **ALTO**
`round_to_tick` prende il tick **più vicino**. Su un prezzo già valido (il caso
normale, viene dal book) è un no-op, ma su un prezzo calcolato o arrivato dalla
UI può **peggiorarlo oltre il necessario** e far morire il FOK. Esempio reale:
chiusura LAY a 51 su CORRECT_SCORE (banda 50-100, passo 5) → `round_to_tick`
dava **50**, cioè sotto il best lay.
→ `place` usa `tick_up` per un LAY taker e `tick_down` per un BACK taker: così
l'ordine abbina, e mai a una quota peggiore del dovuto.

### 1.5 Nessun ritardo di piazzamento sulle uscite urgenti — **ALTO**
In-play Betfair valuta l'ordine **dopo** il bet delay (1-5 s): un FILL_OR_KILL
mandato esattamente al best di adesso trova un mercato già diverso e viene
ucciso; l'uscita non avviene e si ritenta con lo stesso difetto.
→ `close_plan(place_at_ticks=...)` + `X.ticks_for_exit()`: **1 tick** verso la
controparte solo sulle uscite **urgenti** (`loss`, `mandatory`, `red_card`),
dove il manuale dice «esci subito e accetta» e non uscire costa molto più di un
tick. Sulle uscite a profitto/tempo resta **0**: lì ritentare costa poco e il
prezzo conta.

### 1.6 Nessun freno globale sul percorso REST live — **ALTO**
`LIVE_KILL_SWITCH` e `LIVE_ORDER_MODE` fermavano **solo il worker della coda**.
Con il gate flumine chiuso (runner fermo, evento non in streaming) la Safe
Strategy ripiegava sul REST e chiamava `place_order_live`: con
`LIVE_ORDER_MODE=PAPER` nel `.env` — cioè con l'operatore che ha dichiarato
tutto il sistema in paper — **un LIVE passava lo stesso e muoveva soldi veri**.
→ `execution._live_brake()` legge entrambi i freni prima del ramo live.

### 1.7 Correlazione della combo sottostimata — **MEDIO**
Il gate di rischio riceveva `market_type="COMBO"`, che **nessuna posizione ha
mai**: tutte risultavano non correlate e pesavano il 70% invece del 100%. Con un
cap per evento di 150 € si arrivava a ~179 € reali sullo stesso mercato.
→ si passa il mercato della gamba con la responsabilità maggiore.

### 1.8 `selection_id` risolto due volte con precedenze opposte — **ALTO**
`scanner.build_cs_block` costruiva il pair «Altro risultato» **senza**
`selection_id` (vince l'ULTIMO nome che matcha) e `engine._any_other_selection_ids`
ri-scandiva le stesse selezioni per l'id (vince il PRIMO). Prezzo dell'ordine e
selezione su cui si piazza arrivavano da due passaggi indipendenti.
→ il `selection_id` **viaggia col prezzo**. Effetto collaterale risolto:
`exits.position_side` leggeva `blk.get("selection_id")` e trovava sempre `None`
— il suo percorso primario era **codice morto**.

---

## 2. Separazione netta PAPER / LIVE

### 2.1 Il manuale prendeva la modalità dal client — **CRITICO**
`_request_place` usava `payload.mode`, non `control.mode`. Scenario reale:
l'utente accoda un «Piazza (LIVE)» e subito dopo tocca PAPER sul toggle; il bot
legge la richiesta al ciclo successivo e piazza **soldi veri** mentre lo schermo
dice «nessun denaro reale».
→ la modalità del payload è ora una **asserzione da verificare**: se non
corrisponde a quella del servizio la richiesta è **rifiutata** con motivo
(`modalita_non_corrispondente`), sia nel Python sia nella RPC `safe_request`.

### 2.2 Le richieste non scadevano mai — **CRITICO**
`fail_stale_processing` copriva solo lo stato `processing`. Una `pending` creata
ore prima, a servizio spento, veniva eseguita al primo avvio utile, su quote di
un'altra partita.
→ `_REQUEST_MAX_AGE_S = 120 s`, con esito parlante (`richiesta_scaduta`).

### 2.3 P&L, KPI, storico e cap di rischio mescolavano paper e live — **CRITICO**
La colonna `mode` esisteva dal primo giorno e **non la leggeva nessuna query**.
Due conseguenze, entrambe pericolose:
- una settimana di paper vincente gonfiava il «P&L totale» di un conto che non
  aveva guadagnato un euro;
- una giornata paper negativa consumava `daily_loss_stop` e **fermava il live**;
  e nel verso opposto, profitti paper potevano mascherare perdite vere e tenere
  aperto il rubinetto oltre la soglia.
→ `open_trades(mode)`, `aggregates(mode)`, `aggregate_rows(mode)`,
`traded_signal_keys(mode)`, `trade_by_idempotency_key(key, mode)` e
`build_risk_ctx(..., mode)`. Una riga senza `mode` conta come **live**
(fail-safe: meglio vederla nei cap che nasconderla). Lato SQL la migrazione
aggiunge `p_mode` a tutte le RPC di lettura.

### 2.4 Idempotenza condivisa fra le due modalità — **ALTO**
Passando da paper a live, **tutti** i segnali già provati in paper risultavano
occupati: il bot vero **non entrava su niente** di quello che aveva appena
collaudato. Stessa cosa sul manuale: riclickare «Investi» in LIVE su
un'opportunità già presa in paper rispondeva `deduplicated: true` con l'id del
trade **paper** — la UI diceva «fatto», in banca non succedeva nulla.
→ `mode` nella chiave, in Python e nell'indice unico del DB.

### 2.5 Ogni riga di attività è etichettata
Solo 4 dei ~63 punti di log portavano `mode`: a posteriori era impossibile dire
se un blocco di rischio o un'uscita riguardassero soldi veri o finti.
→ `set_log_mode()` + etichetta nel **punto unico** di scrittura. Chi dichiara il
proprio `mode` (place, exit, coda) resta padrone del suo.

### 2.6 Riserva paper mai piazzata confermata come posizione — **ALTO**
Una riga paper ferma a `phase='reserved'` senza nessun segno di esecuzione (il
processo era morto fra l'insert e il place) veniva **confermata al prezzo della
riserva**: si inventava una posizione paper che il live non avrebbe mai avuto. I
numeri del paper non possono valere come prova se contengono posizioni mai
esistite.
→ ora va in `error` terminale (`reconcile_paper_mai_piazzata`). Le righe
**storiche** (senza `meta.phase`) continuano a essere confermate come prima.

---

## 3. Guardie del ciclo — difetti **attivi** al momento dell'audit

Il DB era in sofferenza (timeout sistematici su `get_safe_aggregates` e
`get_safe_state`), quindi questi due difetti stavano producendo i loro effetti
proprio mentre venivano trovati.

### 3.1 Aggregati illeggibili = tutte le barriere di rischio spente — **CRITICO**
`build_risk_ctx` dichiarava «letture KO → fail-closed» ma lo era **solo sul
primo `try`**. Sul secondo proseguiva con `agg={}`, e quindi: `realized_today`=0
→ **il fermo per perdita giornaliera si disattiva**; `day_liability`=0 → **il cap
giornaliero di responsabilità e quello dei trade di modello ripartono da zero**.
In silenzio, a ogni fallimento di lettura.
→ ora ritorna un contesto `unavailable` (nessun nuovo ingresso) e scrive
un'attività `aggregati_non_leggibili` marcata critica.

### 3.2 Control illeggibile = ciclo saltato per intero — **CRITICO**
`run_once` usciva subito con `control_unreadable`, **prima** di
`reconcile_pending`, `settle_open` e `process_exits`: con posizioni aperte e il
DB indisponibile, per tutta la durata del disservizio **non girava né il
settlement, né le uscite, né la riconciliazione**. È l'opposto della regola
dichiarata del modulo («SEMPRE, anche a bot fermo: mai posizioni nude»).
→ si riparte dall'**ultimo control noto** (`_LAST_CONTROL`) e si degrada in
sicurezza: le fasi di **protezione** girano, i **nuovi ingressi** no.

### 3.3 Lo stato d'errore del servizio non arrivava mai a schermo — **MEDIO**
La colonna `error` e lo stato `'error'` esistono dallo schema iniziale e non
venivano scritti da nessuno: un ciclo che esplodeva a ripetizione lasciava la
dashboard con un tranquillo «in esecuzione».
→ `_segnala_errore_di_ciclo` / `_pulisci_errore_di_ciclo`.

### 3.4 Cecità **parziale** del feed — **MEDIO**
La guardia esistente copriva solo la riga **assente** dal feed. Se la riga c'è ma
manca il punteggio (calcio) o i game (tennis), `XE.decide` torna `None` e
**nessuna regola gira**: niente uscita a tempo, niente uscita in perdita, e
**nessun log**. La posizione poteva arrivare al settlement con la responsabilità
intera senza traccia del perché.
→ `_dato_che_manca` / `_nota_dato_mancante`: attività `feed_blind` critica, con
il motivo e da quanto dura, throttlata a 60 s.

---

## 4. Correttezza delle 4 strategie

### 4.1 ESATTO bancava DUE volte la stessa partita — **ALTO**
Il motore valuta la variante su **entrambi i lati**, e a **0-0, 1-0 e 1-1**
passano tutti e due il filtro «al massimo 1 gol»: nascevano due segnali con
chiavi diverse (`…:esatto:home:1-1` e `…:esatto:away:1-1`) e il bot bancava due
volte lo stesso Correct Score. Con lay a 35 e 34 e stake 2 €: **134 € di
responsabilità** sulla stessa partita per 4 € lordi di profitto massimo. Né
`per_event_liability_cap` né `per_event_max_trades` lo fermavano. Il manuale
parla di **una** squadra da bancare, al singolare.
→ un secondo lato `esatto` sulla stessa partita viene scartato con motivo
visibile (`esatto_lato_gia_aperto`).

### 4.2 Cartellini rossi: base sbagliata — **MEDIO**
`entry_red_home/away` veniva fissato alla **prima osservazione utile del
tracciamento**, non all'ingresso. Se il feed iniziava a pubblicare i cartellini
tre minuti dopo l'apertura e nel frattempo la favorita ne aveva preso uno, quel
rosso entrava nella base e **la regola «rosso alla favorita → esci» non scattava
mai** — proprio nel caso che deve coprire.
→ i rossi si registrano nel `meta` **al piazzamento**; la prima osservazione
resta il ripiego.

### 4.3 TENNIS: l'uscita obbligatoria poteva non scattare più — **MEDIO**
La regola del manuale è «due game di fila persi **e** pareggio nel set → uscita
obbligatoria, senza eccezioni». Il codice la applicava correttamente in AND, ma
`games_level` era l'uguaglianza **esatta nell'istante osservato**: se il feed
passava da 5-4 a 5-6 senza mostrare il 5-5, l'obbligo non scattava **più per
tutto il set** — e per la strategia tennis, con i default, **non esiste
nessun'altra regola di perdita**.
→ si registra «parità **o peggio**» (`games_behind_or_level`). L'AND resta.

### 4.4 TENNIS: due stime di probabilità diverse nello stesso bot — **ALTO**
`bot_service._p_tennis` — la funzione che alimenta il gate a modello delle
**uscite** — usava `estimate_holds(0,0,0,0)`, che con zero game e zero break
legge «nessun break subito» e **alza il prior di hold a 0,792 invece di 0,75**,
gonfiando la P(vittoria) del leader; e **non applicava il rischio di ritiro**,
che nel tennis è l'unico modo di perdere tutto lo stake. Lo stesso difetto era
già stato corretto il 12/09 in `tennis_opportunity._holds`, ma non era stato
riportato qui. Misurato su 1 set + 4-2: **0,9311 contro 0,9038**, cioè
P(perdita) 0,069 contro 0,096 con un tetto di rischio a 0,10 — la stessa
posizione risultava «dentro il tetto» o «al limite» a seconda di chi la
guardava.
→ una sola stima: quella del modello, con il calcolo locale come ripiego.

### 4.5 Formato dei numeri: la dichiarazione di parità era falsa — **BASSO**
`engine.py` dichiarava stringhe «IDENTICHE byte per byte» al gemello TS, ma
stampava `8.40` e `€152` dove il TS stampa `8,40` e `152 €`.
→ formato italiano anche nel Python; la dichiarazione ora è vera.

---

## 5. Cosa è stato VERIFICATO CORRETTO (non toccato)

- **Lato e mercato di ogni strategia**: base = LAY sulla sfavorita su
  MATCH_ODDS; esatto = LAY su «Altro risultato» del CORRECT_SCORE; punta = BACK
  sulla favorita; tennis = BACK sul leader. Mai il contrario.
- **Punteggi orientati dalla FAVORITA**, non da «casa»: il caso favorita in
  trasferta è corretto e coperto dai test.
- **Bande pre-match 1.40–1.80 e 4–8**, **30–70** (esatto), **1.03–1.10**
  (punta): valori esatti del manuale, estremi inclusi, identici nei due motori.
- **Le uscite in PERDITA sono incondizionate** in tutte e quattro: `loss`,
  `mandatory` e `red_card` non passano dal gate a modello e **scavalcano il
  backoff** dei ritentativi. Verificato punto per punto.
- **La PUNTA reagisce a QUALSIASI gol subito**, non solo al pareggio: 2-0 → 2-1
  fa uscire anche restando avanti e anche con P&L Betfair ancora positivo.
- **Matematica del green-up**: `S·q/p` per chiudere un BACK, `S·p₀/p` per un
  LAY; invariante W' = L' verificata al centesimo su quote da 1,03 a 65.
- **Scala tick Betfair corretta**, bordo di banda compreso; `ValueError` su
  NaN/inf invece di un prezzo indefinito nell'ordine.
- **Responsabilità vs stake**: ogni cap usa `size·(price−1)` per i lay, mai lo
  stake. Un lay 10 € @ 45 conta 440 €.
- **Commissione solo sugli utili**, con l'aliquota **fissata sul trade**; nessuna
  doppia commissione nel settlement (il difetto di Omega **non** è replicato).
- **Fill parziali** tracciati con la size REALE abbinata; residuo ritentato e
  mai terminale.
- **Idempotenza del piazzamento**: indice unico come lock, `client_ref`
  deterministico, riconciliazione su Betfair prima di decidere. Un riavvio non
  ripiazza.
- **Nessun ingresso al buio**: dato mancante → `ok=None` → stato «n/d», mai un
  segnale.

---

## 6. Difformità dal manuale LASCIATE COM'ERANO (decisione dell'utente, 13/09)

Segnalate, discusse, e **deliberatamente non modificate**:

1. **Minuti = soglie aperte, senza tetto.** Il manuale dà finestre chiuse (base
   55-62', esatto 48-50', punta 66-70'); il codice usa `>=` senza limite
   superiore. Nel paper reale ha aperto trade `esatto` al **62'** e al **64'**.
2. **Quota di banca della BASE senza limiti.** La banda 1,20–1,34 è applicata
   alla quota della **favorita**; la selezione che si banca davvero non ha
   nessun vincolo. Nel paper reale ha bancato a **24,0**, con 46 € di
   responsabilità per 2 € di profitto massimo (il manuale profila la sfavorita a
   4–8 e nell'esempio banca a ~4,5).
3. **Stake fisso, responsabilità variabile.** Il manuale ragiona a
   responsabilità fissa («100 € di responsabilità → profitto max ≈ 28 €»); il
   codice usa stake fisso e la responsabilità varia. Nel DB reale: **da 46 € a
   128 €** per gli stessi 2 € di stake.
4. **Uscite a tempo (80'/72'/83') filtrate dalla decisione a modello** introdotta
   il 12/09, che può decidere di TENERE la posizione fino al settlement se la
   perdita bloccata è piccola e il rischio stimato è sotto il 2%. Il manuale dice
   «esci comunque».
5. **«Controllo del gioco»** — richiesto dal manuale in ingresso per base e
   punta, in uscita per la base, e **invertito** per l'esatto — **non è
   implementato in nessuna delle tre**. `pressure.py` esiste ma non è calibrato
   ed è spento di default: accenderlo cambierebbe il comportamento sulla base di
   un indicatore non validato.
6. **TENNIS, ramo LAY 1,18–1,34**: il codice fa solo BACK. La banda del manuale è
   matematicamente incompatibile con la banda back ≈1,03 della stessa pagina
   (quando il leader quota 1,03, il perdente sta a 15-40): sembra un errore di
   trascrizione nel manuale, non nel codice.
7. **TENNIS, esclusioni**: doppi sì; **finali, match equilibrati, sfavoriti
   estremi e Slam maschili (bo5) no**. Per le finali manca proprio il dato: il
   payload non porta il turno del torneo.

---

## 7. Da fare PRIMA di qualunque live

1. **Applicare la migrazione** `migrations/safe_strategy_paper_live_2026-09-13.sql`
   (ordine in `migrations/APPLY_ORDER_2026-09-11.md`). Senza, la separazione dei
   dati vive solo nel ripiego Python e gli indici di sicurezza non esistono.
2. **Riavviare l'app** perché scanner e bot ricarichino il codice nuovo.
3. **Riattivare i cap di rischio**: al momento dell'audit `daily_liability_cap`
   valeva **0,0** (= disattivo) e `max_open_trades` era **null**, con 2.610 € di
   responsabilità giornaliera impegnata. In paper non costa nulla; in live è il
   rischio più grande che ci sia.
4. **Indagare la salute del DB**: timeout sistematici su `get_safe_state` con
   sole 240 righe di trade non sono spiegabili col volume di questa sezione.
   Finché durano, il bot lavora in modalità degradata (vedi §3).
5. **Osservare qualche giorno di paper** con base e punta finalmente attive: i
   numeri raccolti finora su quelle due strategie sono **un trade ciascuna**, non
   sono una base di giudizio.
6. **Chiudere il punto §7-quater** (importi sotto il minimo: paper ≠ live sul
   percorso a coda). Finché resta aperto, in live conviene tenere gli stake sopra
   il minimo di giurisdizione, dove i tre percorsi coincidono.

---

## 7-bis. SECONDA TORNATA — la review avversariale

Le correzioni sopra sono state passate a una **review indipendente e ostile**,
che ha trovato **due regressioni introdotte dalle correzioni stesse**. Sono
state chiuse entrambe, e questa sezione le documenta perché non tornino.

### R1 [CRITICO] Il filtro di modalità aveva spento le uscite delle posizioni live
Filtrando `open_trades` per modalità e passando quella lista a `process_exits`,
una posizione **LIVE** aperta smetteva di essere gestita appena il servizio
tornava in PAPER — e `safe_stop()` lo fa apposta. Niente uscita in perdita,
niente uscita obbligatoria, niente rosso: la posizione arrivava al settlement
con la responsabilità intera. Era un difetto **peggiore** di quello che il
filtro voleva chiudere.
→ il contesto di rischio porta ora **due liste**: `open` (filtrata, per i CAP e
i numeri) e `open_all` (tutte, per la PROTEZIONE — uscite, cecità del feed,
svolgimento delle combo). Una posizione viva si protegge sempre, qualunque sia
la modalità del servizio.

### R2 [CRITICO] Il freno live bloccava anche le CHIUSURE
`_live_brake` era applicato prima del ramo live **senza distinguere apertura da
chiusura**: con il kill-switch attivo, o con `LIVE_ORDER_MODE != LIVE`, una
posizione live non era più chiudibile — né automaticamente né dal pulsante
manuale. E l'altra via era chiusa allo stesso modo: il worker della coda
rifiutava le chiusure della Safe Strategy come se fossero aperture, perché
vengono accodate con `action="place"` e la sua lista di azioni di chiusura non
lo prevedeva.
→ il freno vale **solo sulle aperture**, e `live_order_worker._is_closing_row`
riconosce anche un `place` con `params.reduces_liability`. È la regola che il
worker già applicava e documentava: il kill-switch ferma i soldi che escono,
non quelli che rientrano.

### R3 [ALTO] Un timeout bruciava la reidratazione per tutta la giornata
`hydrate_pre_ko` marcava gli eventi come «già tentati» **prima** della lettura:
un solo timeout del DB — e il DB va in timeout spesso — spegneva il recupero per
tutte le partite in corso fino a sera. Il difetto che la funzione esiste per
chiudere si richiudeva da solo al primo intoppo.
→ si marca solo ciò che è stato **davvero interrogato con esito**.
`load_scan_pre_ko` ritorna ora una chiave per ogni evento chiesto, con `None`
per «cercato e non trovato»: gli eventi che non compaiono non sono stati chiesti
e si ritentano.

### R4 [ALTO] La guardia «un solo lato ESATTO» era cieca ai `pending`
Funzionava dentro lo stesso ciclo (grazie a `_risk_commit`) ma non **fra** un
ciclo e l'altro: in LIVE via coda il fill richiede almeno un ciclo, la riga resta
`pending` e `open_trades` non la restituisce — quindi il secondo lato passava.
Il buco si apriva proprio dove costa, mentre in paper il fill immediato lo
nascondeva.
→ la guardia guarda anche le riserve in volo, riusando le righe già lette da
`reconcile_pending` nello stesso giro.

### R5 [MEDIO] La regola tennis era stata ALLARGATA, non riparata
La prima correzione usava «parità **o peggio**». Ma a inizio set il leader è 0-0:
perdendo i primi due game sarebbe uscito d'obbligo a **0-2**, dove il manuale non
chiede niente — un **cambio di regola** in una certificazione che dichiara di non
cambiare le strategie. Costo misurato del falso obbligo: back 100 € @1,03 con
quota risalita a 1,12 → circa **−8 €** bloccati, dove prima il bot teneva.
→ la condizione giusta è «nel set in corso il leader **aveva** un vantaggio e
adesso non ce l'ha più» (`set_lead_max` / `set_lead_lost`). Copre il caso del
5-5 mai comparso nel feed e lascia fuori il 0-2 di inizio set, come prima.

### R6 [MEDIO] Il fail-closed avrebbe fermato il bot quasi sempre
Con il DB in timeout sistematico, bloccare a ogni ciclo significava non entrare
mai più — e scrivere un'attività critica ogni 2 secondi (~1.800 righe l'ora)
sullo stesso DB in ginocchio.
→ entro **120 s** si riusano gli ultimi aggregati letti bene (possono solo
sottostimare la responsabilità del giorno, e le riserve del ciclo la
ricompongono); oltre, si blocca davvero. L'allarme è throttlato a uno al minuto.

### R7 [MEDIO] Il control in cache non scadeva, e validava le richieste manuali
→ oltre **600 s** si dichiara un allarme critico; e in ciclo degradato una
richiesta di **piazzamento** viene rifiutata (la modalità con cui validarla
verrebbe da una cache che può essere vecchia). Le **chiusure** continuano a
passare sempre.

### R8 [MEDIO] Falsi allarmi critici sulle righe pre-KO
`_dato_che_manca` pretendeva il minuto, che una riga pre-KO non ha per natura.
→ si allarma solo su righe `inplay` e solo per posizioni per cui la cecità è
davvero un allarme (stessa guardia già usata per la riga assente).

### R9 [BASSO] La size del piano non era coerente con lo snap al tick
`place` porta il prezzo al tick valido, ma la size del piano è `diff/prezzo`
calcolata sul prezzo originale. Oggi i prezzi vengono dal book e lo snap è
inerte, ma non per costruzione.
→ i prezzi si portano al tick **prima** del calcolo: prezzo e size restano
coerenti per definizione.

---

## 7-ter. FEED: quattro correzioni dalla diagnosi congiunta con la sessione su Mike

### F1 Il battito diceva la cosa sbagliata
`publish_status` stava **in coda al tick**, dentro lo stesso `try`: la sua età
non misurava «lo scanner è vivo», misurava **la durata del giro**. Con giri da
24 s (poll REST dei book a lotti di 25) il battito nasceva già vecchio di 24 s,
durante un refresh del catalogo superava i 30 s e faceva cadere la deroga di
freschezza di Mike — cioè **lo stesso rallentamento che invecchiava le righe
disarmava la valvola che doveva coprirle**. Una qualunque eccezione prima di
quella riga lo saltava del tutto.
→ lo scrive il thread dei punteggi, in un `try` suo, con cadenza propria.

### F2 Un contatore diagnostico riscriveva il feed
`total_matched` si muove a **ogni scambio** e non è un gate per nessuno (Mike lo
dichiara «diagnostica»; Safe, Omega e il frontend lo mostrano e basta). Tenendolo
nella firma del write-on-change, una partita in gioco molto scambiata riscriveva
~12 KB di JSONB ogni pochi secondi. La tabella è TOASTata e pubblicata su
realtime: ogni UPDATE costa heap + TOAST + indice + WAL + decodifica logica,
amplificazione 3-5 volte, ~5 GB al giorno.
→ fuori dalla **firma**, resta nel payload.

### F3 Prezzi morti indistinguibili da prezzi fermi
`ts_ms` dice quando il prezzo si è mosso l'ultima volta; da solo non distingue
«mercato fermo ma sotto osservazione» da «mercato che non guardiamo più». Nel
secondo caso il blocco resta in cache col **prezzo vecchio** e viene ripubblicato
come se fosse valido: coprirsi o uscire su un prezzo morto è peggio che non
coprirsi.
→ nuovo `seen_ms` su ogni blocco dei mercati a gol = momento dell'ultimo book
ricevuto, fuori dalla firma (altrimenti riscriverebbe la riga a ogni poll).

### F4 Il tetto delle partite di Mike tagliava quelle sbagliate
`MIKE_MAX_FOLLOWED` troncava seguendo l'ordine dei candidati dello scanner —
«minuti più avanzati per primi» — quindi cadevano le partite **appena iniziate**,
cioè quelle dove la copertura Over 4.5 serve di più. E `_mike_followed()`
conservava la lista in un **set**, perdendo qualunque ordine.
→ le partite arrivano ordinate per **soldi a rischio decrescente**
(`db._mike_exposure`), il taglio segue quell'ordine, e la cache conserva una
lista. Il numero 40 è rimasto invariato: con il criterio giusto non è più
money-critical.

---

## 7-quater. PUNTO APERTO, NON RISOLTO — importi sotto il minimo: paper ≠ live

Dichiarato qui perché resti visibile invece di essere scoperto in live.

Abbassando il pavimento a 0,01 € (§1.1) un'apertura da 0,30 € o 1,50 € arriva
davvero a `execution.place`. Ma i tre percorsi non si comportano allo stesso modo:

| percorso | sotto il minimo di giurisdizione |
|---|---|
| **PAPER** (gate coda chiuso) | `paper_fill` riempie **subito** al best |
| **LIVE via REST** | `place_submin_live` è **FOK**: o si abbina tutto o niente |
| **LIVE via coda** | `place_submin` lascia l'ordine **A RIPOSO** alla quota target: può abbinarsi minuti dopo |

Due conseguenze, entrambe reali:
1. **Fedeltà del paper.** Il paper dichiara fill che il live via coda non
   otterrebbe nello stesso istante — il contrario dell'invariante «demo = live
   senza soldi» su cui poi si decide di andare in live.
2. **Rischio di posizione doppia (solo live via coda).** Oltre
   `live_fill_deadline_s`, `poll_flumine_pending` può dichiarare morta una gamba
   mentre l'ordine è ancora **vivo su Betfair**. È lo stesso difetto già chiuso
   sul percorso REST (`place_submin_live(fill_or_kill=True)`) e ancora aperto
   sulla coda.

**Quando può mordere davvero** (verificato): serve che si verifichino INSIEME
un'apertura sotto il minimo di giurisdizione **e** il gate della coda aperto
(runner vivo, evento in streaming). Con lo stake di default a 2,00 € succede solo
quando la size viene **cappata dalla liquidità** al best. È un percorso stretto,
non la strada normale — ma è proprio il caso in cui il book è sottile, cioè
quello in cui un ordine rimasto a riposo è più probabile.

**Perché non è stato corretto stasera**: la sequenza place-and-trim della coda è
una macchina a stati **condivisa**, e la sua fase finale (`DONE`) è dichiarata
come «ordine a riposo alla target_price» — è la sua natura, non un difetto.
Renderla FOK-equivalente significa aggiungere il **ritiro del residuo** nello
stato terminale, come fa già `place_submin_live` in REST. È una modifica al
contratto di un componente usato da più bot: va fatta con il suo collaudo, non a
fine giornata. Verificato con la sessione parallela che **né Omega né Mike**
accodano `place_submin` (Omega usa sempre `action: place`, Mike va in REST),
quindi la correzione non creerà regressioni altrove. Il live è comunque
**bloccato**.

**Alternativa, forse migliore**: non dichiarare MAI morta una gamba senza prima
averla **annullata** su Betfair. Oggi oltre `live_fill_deadline_s` la si dichiara
morta e basta: è quello il passo che apre la finestra della posizione doppia,
indipendentemente dal place-and-trim.

**Le due vie, quando si affronterà**: o `place_submin` in coda ritira il residuo
al termine della sequenza (come fa il REST), oppure in paper la size sotto il
minimo di giurisdizione simula un ordine **a riposo** invece di un fill immediato.
La prima è quella giusta: allinea il live al live.

---

## 8. Stato dei test

| suite | esito |
|---|---|
| `Betfair` **per intero** | **3134 passati**, 0 falliti |
| `Betfair/safe_strategy` | **682 passati**, 0 falliti |
| `Betfair/stream/tests/test_live_order_worker.py` + `test_live_order_build.py` | **114 passati** |

### Gli 11 rossi di `Betfair/stream`: CAUSA TROVATA

Durante l'audit 11 test di `Betfair/stream` (ciclo di vita del runner, stallo
dello stream, guardia «flat» del sub-worker) fallivano. Sono stati attribuiti
prima a un difetto pre-esistente, poi a cache stantia: **erano sbagliate
entrambe le spiegazioni**.

**La causa vera, dimostrata con un esperimento controllato** dalla sessione
parallela, con i `__pycache__` svuotati in tutti e due i casi:

| condizione | esito |
|---|---|
| database raggiungibile | **47 passati, 0 falliti** |
| `SUPABASE_URL=https://127.0.0.1:9` | **11 falliti**, 36 passati |

Gli 11 nomi coincidono esattamente con quelli della prima misura
(`test_lifecycle_shuts_down_when_idle`, `test_lifecycle_max_hours_backstop`, i 5
di `sub_worker_flat_guard`, i 3 di `stream_heartbeat_stall`,
`test_stall_restart_parte_a_blotter_flat`).

**Perché**: `runner._lifecycle_blockers` importa `db_client.get_supabase_client()`
e interroga `betfair_live_risk_rules`; se la chiamata solleva, risponde «regole
di rischio non verificabili (prudenza: resto acceso)» e lo spegnimento viene
rinviato — che è esattamente il messaggio comparso nei fallimenti. Alle 21:37 il
database rispondeva 503: da lì i rossi. Dopo il suo riavvio, verdi.

**È un difetto vero, ma del COLLAUDO, non del codice di produzione**: quei test
unitari fanno una **vera chiamata di rete**, quindi il verde della suite dipende
dal fatto che il database di produzione sia su, e quando il DB è lento sono lenti
e intermittenti. `Betfair/stream/tests/` non ha un `conftest.py` che neutralizzi
quella lettura (e `_RISK_RULES_BLOCKED_UNTIL` è uno stato di modulo con TTL 15 s
che può trascinarsi fra un test e l'altro). Preso in carico dalla sessione
parallela.

**La lezione, che vale più della correzione**: due sessioni indipendenti hanno
prodotto due spiegazioni comode e sbagliate («pre-esistente», «cache stantia»)
prima che qualcuno facesse l'unico esperimento che le distingueva. Una misura che
non riesci a riprodurre a comando non è una misura.

Regola comunque utile, imparata qui: prima di credere a un rosso, svuotare i
`__pycache__` — e prima di dichiararlo «pre-esistente», rifarlo a cache pulite.

I test nuovi sono in `Betfair/safe_strategy/tests/test_cert_2026_09_13.py` (35),
più quelli aggiunti o aggiornati in `test_bot_service.py`, `test_scanner.py` e
`test_engine.py`. I test che codificavano un comportamento **sbagliato** sono
stati sostituiti, non cancellati: ognuno dichiara nella docstring quale test
rimpiazza e perché.
