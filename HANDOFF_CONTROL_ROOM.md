# HANDOFF — CONTROL ROOM e primo bot validato in LIVE

> **Se sei un agente che riprende questo lavoro, questo è il file da leggere per primo.**
> Aggiornato: **15 settembre 2026**. Ultimo commit: `cbb1f4c`. Tutto pushato su `master`.
>
> Se hai tempo per leggere una sola cosa, leggi **§2B — l'incidente del loop**:
> è il giorno in cui questo progetto ha piazzato trentadue ordini veri che non
> doveva piazzare, e spiega meglio di qualunque regola perché qui si controlla
> due volte tutto ciò che tocca i soldi.

La Control Room (`/control-room`) è la **cabina di regia** della piattaforma: da lì
il trader guarda i tre bot, approva le uscite e comanda tutto. Oggi è stato
**validato il primo bot in live con denaro reale**; gli altri seguiranno, e
passeranno da qui.

---

## 1. Che cosa è successo il 14 settembre, in una riga

Il bot tennis (Safe, strategia `tennis`) ha operato **con soldi veri**, 3 € a
segnale, per **5 operazioni chiuse, tutte in positivo, +0,44 €**. Le entrate
sono automatiche, le **uscite le approva il trader** dalla Control Room. Poi il
bot è stato fermato su richiesta dell'utente.

---

## 2. Le operazioni live del 14 settembre (evidenza)

| # | partita | ingresso | esito | P&L |
|---|---|---|---|---|
| 285 | Masur – Dan de Jonge | back @ 1,02 | vinta | **+0,06** |
| 286 | Kawa – Ma Garcia Cid | back @ 1,10 | vinta | **+0,29** |
| 287 (+288) | Ju Boulais – Bobichon | back @ 1,11, coperta @ 1,10 | vinta | **+0,03** |
| 290 (+292) | Pedone – Zoldakova | back @ 1,04, coperta @ 1,03 | vinta | **+0,03** |
| 296 | Ya Zeng – Santillan | back @ 1,01 | vinta | **+0,03** |

**Realizzato live: +0,44 €.** Paper della stessa giornata: **−9,80 €** (13
operazioni, quasi tutte calcio). *I due numeri non si sommano mai — vedi §4.*

### La domanda a cui l'utente teneva di più

> «quando invio gli ordini di chiusura, voglio capire a che prezzo si abbinano
> rispetto al segnale o se scorrono il book falsando l'uscita»

**Risposta certificata: le chiusure si abbinano al prezzo ESATTO del segnale.**
Tre chiusure approvate a mano, **0 tick di scostamento** tutte e tre. Gli
ingressi abbinano al prezzo chiesto o meglio (#286 −2 tick, #287 −1 tick).
Nessuna uscita falsificata.

Convenzione dello scostamento (`Betfair/safe_strategy/execution.py:201`):
**positivo = peggio del chiesto**, negativo = meglio, zero = al segnale.

Il green-up è confermato dal **settlement vero**, non dall'aritmetica:
#287 +0,33 / #288 −0,30 = **+0,03**, identico al bloccabile mostrato prima del clic.

### Strumenti per rifare questa verifica

```
python Betfair/safe_strategy/tools/storia_operazioni.py      # referto forense per operazione
python Betfair/safe_strategy/tools/conta_operazioni_live.py  # conteggio + realizzato
```

Sono **di sola lettura**. `storia_operazioni.py` ricostruisce ogni operazione:
prezzo chiesto vs abbinato con lo scostamento in tick, la catena dei tempi salto
per salto, la proposta di uscita con bloccabile e hold, la decisione umana e a
che prezzo ha abbinato la gamba di chiusura.

---

## 2B. L'INCIDENTE DEL 15 SETTEMBRE — 32 ordini veri in loop

> Leggilo prima di toccare `Betfair/mike/`. Non è un aneddoto: le tre correzioni
> che ne sono uscite sono ancora l'unica cosa che impedisce che si ripeta.

### Che cosa è successo

Mike è stato avviato **in live** per la prima volta, con 5 € di ingresso su un
conto da 35 €, tetto di **1 partita** in contemporanea. Al primo giro utile ha
piazzato il green-up, e poi lo ha piazzato **di nuovo**. E di nuovo. **Trentadue
volte**, ordini reali identici, fino a impegnare **~61 €** su un budget di 35.
Li ha cancellati a mano l'utente.

### La radice: una parola scritta in due grafie

Il motore, prima di piazzare la gamba di uscita, controlla se quell'ordine è
**già appoggiato a mercato**. Lo cercava così:

```python
o = next((x for x in vivi if str(x.get("customerOrderRef") or "") == str(leg.ref)), None)
```

Ma `omega_market.list_current_orders()` **normalizza le chiavi in snake_case** e
restituisce `customer_order_ref`. `customerOrderRef` in quel dizionario **non
esiste**. Il confronto era `"" == "mike-..."`: falso **sempre, per costruzione**.
Ogni ordine appoggiato risultava «mai piazzato», il motore ne creava uno nuovo, e
si ricominciava.

Nessun test lo prendeva perché tutti i doppioni di mercato nei test erano scritti
a mano con la grafia camelCase — cioè con la grafia *sbagliata*, la stessa del
bug. **Il finto rispondeva a una domanda a cui il vero non rispondeva.**

Corretto in `c4b6172`: `_ordine_di()` cerca per **due** strade — prima il
`bet_id` (l'identificativo che ci ha dato Betfair, il più solido), poi il
riferimento cliente **accettando entrambe le grafie**, così un cambio di
normalizzazione a monte non può più rompere in silenzio una ricerca da cui
dipendono ordini veri.

### Le due correzioni che vanno con essa (`b1285a0`)

1. **`_gia_appoggiata()`, freno a monte e FAIL-CLOSED.** Prima di piazzare si
   guarda se esiste già una riga `pending` per **stesso ruolo, stesso ciclo,
   stesso lato**. E se le righe **non si riescono a leggere**, non si piazza:
   non sapere se c'è già un ordine in volo è esattamente il caso in cui si sta
   fermi. Se questo freno fosse esistito, il bug della grafia avrebbe prodotto
   *un* ordine di troppo, non trentadue.
2. **Il `bet_id` si salva SEMPRE** dopo `place_order_live`, non solo quando
   l'ordine risulta già abbinato (`matched > 0`). Un ordine appoggiato e non
   ancora abbinato è precisamente quello che va ritrovato al giro dopo: era il
   caso in cui la riga restava senza identificativo.
   Nuovo tipo di attività `place_saltato`: quando il freno interviene lo si
   vede, invece di un silenzio identico a «non c'era niente da fare».

### Due cose che l'incidente ha rivelato

- **`mike_stop` non ferma gli ordini di uscita.** Fermare toglie le *aperture*
  (`_strip_openings`); coperture, green-up, cash-out e settlement continuano a
  girare — ed è giusto, una posizione aperta non si abbandona. Ma significa che
  **durante quel loop premere «FERMA» non lo avrebbe fermato**: il loop era su
  una gamba di uscita. Per fermarlo davvero sono stati **terminati i processi**.
  Se ti ritrovi in quella situazione: è quella la via, e va detto all'utente.
  → **Il comportamento resta**, ma adesso i servizi lo **dichiarano**
  (`stats.stop_ferma_solo_aperture`) e il pulsante lo scrive. Vedi §2C.
- **Il tetto `max_open_matches` contava paper e live INSIEME.** `esposte` in
  `_run_cycle` si costruiva su tutte le partite seguite senza filtro di
  modalità. Con tetto a 1, **una vecchia posizione paper rimasta viva impediva
  a Mike di aprire in live** — l'utente vedeva un bot «che non fa niente» senza
  nessun motivo scritto da nessuna parte.
  → **CORRETTO** (§2C). Non era una strategia da preservare: era la regola
  «paper e live perfettamente distinti» violata dentro il conto che decide gli
  ingressi.

---

## 2C. L'ALLINEAMENTO BACKEND ↔ CONTROL ROOM (15/09, `9143717`)

> «Se correggi gli errori e non allinei anche il backend, come fa il trader a
> capire?» — la Control Room è uno **specchio**: correggerla lasciando il
> servizio com'era non corregge niente.

Tre disallineamenti, tutti sul percorso per cui un trader capisce che cosa sta
succedendo. **Nessuna strategia toccata**: nessuna soglia, nessun prezzo,
nessuna dimensione. Cambia *chi conta chi*, e *che cosa viene detto*.

**1. Il tetto delle partite di Mike sommava paper e live.**
Ora vale DENTRO una modalità (`service.posti_occupati_per_modo`). Safe lo
faceva già (`_ctx_di(mode_s)`); Omega non ha un tetto partite.

**2. Un bot acceso che non apre adesso dice perché.**
Il motivo esisteva solo nel registro degli scarti, che il trader non guarda: in
Control Room c'era scritto «running» e basta, quindi un bot sano e un bot
bloccato erano **indistinguibili**. Mike e Safe pubblicano `motivo_blocco`,
`tetto_partite`, `partite_esposte`; il pannello li mostra sotto il bot
(«acceso ma non apre: tetto partite raggiunto: 2 su 2 in live — 2/2»). Se il
servizio non dichiara niente, **la pagina non inventa**.

**3. La cadenza del battito la dichiara chi batte.**
Nel frontend c'era una costante di 60 s: una **seconda verità**. I tre bot
battono a passi diversi — **Safe ~2 s, Mike fino a 20, Omega fino a 60** — e il
13/09 quei passi erano già stati allargati per far respirare il database senza
che la pagina lo sapesse. Col metro unico, Safe risultava «vivo» per due minuti
dopo essere morto. Ora i tre servizi pubblicano `cadenza_battito_s`; la
costante resta solo come **ripiego** per un servizio che non dichiara, ed è la
più lenta delle tre perché mandare a riavviare un bot sano è il danno peggiore.
(In Omega `idle_cycle_s = 0` era trattato come «assente»: è invece una scelta
legittima — «non rallentare a vuoto» — e scambiarla dichiarava 60 s al posto
di 45.)

**Regola che ne esce, e che vale per qualunque numero nuovo in Control Room:**

> Se la pagina deve sapere qualcosa che il servizio decide, quel qualcosa lo
> **pubblica il servizio**. Una costante nel frontend che duplica una scelta
> del backend è una seconda verità, e prima o poi le due divergono in silenzio.

### La pulizia delle righe fantasma

Dopo l'incidente sono rimaste righe `pending` senza ordine dietro. Prima di
toccarle si è **verificato su Betfair** che `list_current_orders()` tornasse
**zero**: solo allora sono state chiuse, perché altrimenti il nuovo freno
anti-duplicato avrebbe bloccato per sempre anche il green-up legittimo.
Due dettagli che servono a chi rifarà la stessa operazione:

- si chiudono con `status='error'`, **non** `'cancelled'`: quel valore viola il
  vincolo CHECK della tabella;
- **non si tocca una posizione ABBINATA** (riga con `bet_id` valorizzato): una
  posizione abbinata non è un ordine da annullare, sono soldi a mercato.

---

## 3. Le regole del progetto (violarle è un difetto, non una scelta di stile)

Queste regole nascono tutte da errori veri, già costati.

1. **PAPER E LIVE NON SI SOMMANO MAI.** Soldi veri e simulati in un numero solo
   sono una bugia. Oggi ne sono stati trovati **quattro** casi (§4).
2. **ASSENTE non è ZERO.** Un valore ignoto si scrive `—`, mai `0,00 €` né
   `0 ms`. «Istantaneo» e «non lo so» sono affermazioni diverse.
3. **FAIL-CLOSED.** Nel dubbio si sceglie la strada che NON rischia denaro: una
   modalità non dichiarata vale `paper`, un'età ignota non è «fresca», un bot
   muto non è un bot sano. *Ai soldi veri si arriva scrivendolo, mai
   ereditandolo.*
4. **LE STRATEGIE NON SI TOCCANO.** Parole dell'utente: «LE STRATEGIE SONO
   PROGETTATE COSÌ E DEVONO RESTARE COSÌ, L'UNICA DIFFERENZA È LIVE O PAPER».
   Se un ordine non si abbina perché non c'è controparte, **è il mercato**, non
   un difetto.
5. **Un pulsante spento dice PERCHÉ.** Mai un `disabled` muto.
6. **Cercare prima di creare.** Prima di dire che un percorso non sa fare una
   cosa, cercare nel repo se qualcun altro gliela fa già fare. Questa regola
   nasce da un'affermazione sbagliata fatta e ritrattata.
7. **Design system:** i soldi passano da `fmtMoney`, le quote da `fmtOdds`, le
   età da `fmtAge`. Mai `toFixed` a mano. Testi in italiano.
   La guardia è meccanica: `frontend/src/components/trading/designGuard.test.ts`.

### Vincoli operativi

- **Mai `git add -A`** (c'è un log da 3 GB; GitHub rifiuta >100 MB).
- **L'app la avvia e la riavvia l'utente**, mai l'agente. L'exe è un avviatore
  del `main.js` vivo: dopo una modifica basta riavviare, **mai ricompilare**.
- **Nessun processo/registratore/runner nuovo senza permesso esplicito.**
- Comunicare in italiano.

---

## 4. Il lavoro del 14 settembre sulla Control Room

### 4.1 La verità dei numeri (priorità dichiarata dall'utente)

> «la veridicità DELLE OPERAZIONI DI PNL E DELLA BARRA è LA PRIORITÀ!! NON
> VOGLIO DATI MISCHIATI»

La pagina mostrava **tre verità diverse** sulla stessa giornata: testata
`0,00 €`, barra `−4,83 €`, tessere `+0,22 €`. Nessuna era un numero esistente.
Quattro cause, tutte corrette (`b2c56b1`):

| # | dove | che cosa diceva |
|---|---|---|
| 1 | `get_safe_daily` senza `p_mode` | tennis **+0,25 €** = +0,41 live − 0,16 paper |
| 2 | barra = somma dei 3 servizi | ogni servizio pubblica il realizzato **nella propria modalità** (`bot_service.py:5445`): un numero vero + due simulati |
| 3 | `soldiPerPartita` con un solo `netPnl` | sul tennis la stessa partita ha righe di entrambe le modalità: era la **media di due mondi** |
| 4 | `totaliGiornata.liability` | esposizione dichiarata **393,68 €** contro **77,71 €** di soldi veri impegnati |

**Come è stato reso impossibile ripeterlo:** `PartitaSoldi` non ha più un campo
che unisca le due modalità — è `{ live, paper, modi }`. Il compilatore ha
portato su **15 punti** da decidere uno per uno. `modoDi()` è fail-closed.

Verificato sui dati veri: live **+0,44 €** / 5 op, paper **−9,80 €** / 13 op;
server e righe grezze coincidono al centesimo in entrambe le modalità. Il numero
misto (−9,36 €) non compare più da nessuna parte. Se server e pagina non
concordano, **la pagina lo dichiara** invece di scegliere il numero più bello.

### 4.2 Latenza — due colli di bottiglia trovati e corretti

**Dal clic all'ordine passavano 4,2 secondi NOSTRI** (i 3,3 s di Betfair sono
bet delay e non si toccano). Erano due attese sommate (`07505ba`):

- il ciclo gira ogni 2 s → **attesa ora interrompibile**: con almeno una
  posizione aperta si sbircia la coda ogni 250 ms con una query da una riga; a
  banco vuoto **zero letture in più**;
- `process_requests` stava al punto (c), dopo coda flumine, riconciliazione,
  settlement, contesto di rischio, cecità del feed e combo rotte → **le
  chiusure passano in testa al ciclo**.

Le **aperture restano dov'erano**, e non è una dimenticanza: un piazzamento ha
bisogno del contesto di rischio condiviso perché due aperture nello stesso giro
devono vedersi a vicenda per i cap. Una chiusura no.

Protezione contro il ciclo impazzito: una richiesta incagliata sveglierebbe il
bot ogni 250 ms — è la forma esatta del guasto del 13/09 (budget IO esaurito).
Si anticipa **una sola volta per richiesta** (`_SVEGLIA_FATTA`).

**Cronometro che sbagliava a nostro favore** (`6bb0229`): `t3_deciso_ms`
registrava l'inizio del ciclo, non la decisione. t3 cadeva **prima** di t2 (216,
238, 282 ms sui trade veri), il salto «bot → decisione» era negativo e la pagina
lo mostrava come `—`; e `prezzo_to_decisione_ms` dichiarava 3,2 s contro 4,7 s
reali. Corretto: solo misura, nessun ordine toccato.

### 4.3 Plancia di comando dei tre bot (`8226d00`)

`PannelloBot.tsx` + `comandiBot.ts`. Usa i comandi che i servizi **espongono
già** (`X_activate` / `X_stop` / `X_update_params`) e monta i **fogli parametri
esistenti** (`BotParamsSheet` di Safe, `MikeParamsSheet` di Mike): due schede
diverse per lo stesso servizio sarebbero due verità.

- accendere in **LIVE** vuole doppia conferma, col secondo pulsante nella stessa
  posizione del primo; tornare in prova non chiede niente (toglie rischio);
- **FERMA TUTTI** non chiede conferme — un freno d'emergenza con una finestra
  davanti non è un freno. Ferma **in sequenza**;
- lo stato mostrato è quello che **risponde il servizio**: `stopping` si scrive
  «sta fermandosi», non «fermo»;
- un comando fallito si **dichiara**.

**Gli importi non sono uno solo**, e fingere di sì sarebbe falso:
Safe ne ha **due** (`stake.backSize` per chi punta — tennis e punta —,
`stake.laySize` per chi banca — base ed esatto); Mike uno (`stake`, «Under
3.5»); Omega `min_stake`, che è un **minimo**: dimensiona dall'obiettivo,
quindi la scheda scrive che è un minimo.

`cambiaImporto` riparte **sempre** dai parametri correnti e cambia una chiave
sola: mandare solo quella cambiata cancellerebbe il resto (`exits` compresi).
Omega senza obiettivo noto **non parte**: `omega_activate` pretende un numero.

### 4.4 Le quattro schede (`f13e952`)

`Pre-match` · `Live` · `Posizioni aperte` · `Posizioni chiuse`, per calcio e per
tennis (il tennis non ha il pulsante Statistiche perché non esistono).

**Il nastro delle uscite resta FUORI dalle schede, sempre visibile**: una
chiusura matura su soldi veri mentre il trader guarda un'altra scheda.

Ogni scheda ha la **stessa riga di pulsanti** (video, statistiche, trading,
segui live) e ognuno si segna il punto di ritorno.

### 4.5 Ritorno al punto esatto (`lib/ritorno.ts`)

Nel software **non esisteva**: c'era solo `?from=`, che riporta alla pagina e la
fa ripartire dal tab predefinito, in cima. Un punto di ritorno sono quattro
cose: rotta, scheda, partita, scorrimento. Vive in `sessionStorage` e **scade
dopo 15 minuti** — tornare dopo mezz'ora alla riga di allora significa tornare
su una partita finita. Ogni lettura è difensiva: un ritorno impreciso degrada in
uno **onesto**, mai in uno sbagliato.

«Torna alla Control Room» aggiunto in `Dashboard.tsx` e `SeguiLive.tsx`; il
tasto indietro di `TennisTerminal.tsx` riporta qui invece che alla lista.

---

## 5. Due trappole trovate — NON reintrodurle

### 5.1 Calcio e tennis NON registrano nello stesso posto

`set_follow_record` scrive su **`live_follow`**, che il registratore del tennis
**non legge mai**: lui guarda **`tennis_live_follow`**
(`Betfair/stream/tennis_live/tennis_recorder.py`).

Un pulsante «Segui live» unico avrebbe acceso una spia verde **senza registrare
niente**. Ogni sport usa la sua coppia:

| sport | segui | registra |
|---|---|---|
| calcio | `followMission` (`omega_mission_follow`) | `setFollowRecord` (`set_follow_record`) |
| tennis | `followTennisEvent` (`tennis_follow_event`) | `setTennisFollowRecord` (`tennis_set_follow_record`) |

### 5.2 Il feed dello scanner non ha loghi né campionato

Verificato sui dati veri: il payload di `safe_strategy_scan` porta
`mo_market_id` e `open_date`, **e basta**. Campionato, loghi e `fixture_id`
vivono nella tabella eventi di Omega (`get_omega_events`): **campionato 55/55,
loghi e fixture 27/55**. Si uniscono per `event_id` (`arricchimentoDa`); dove
mancano, il pulsante Statistiche è **spento con la ragione scritta**.

---

## 6. Mappa dei file

### Frontend — `frontend/src/`

| file | che cosa fa |
|---|---|
| `pages/ControlRoom.tsx` | la pagina: testata, barra, tessere sport, plancia bot, catena, 4 schede |
| `components/controlroom/useControlRoom.ts` | tutta la lettura dati. `RICARICA_MS = 30_000` + realtime |
| `components/controlroom/PannelloBot.tsx` | avvia/ferma/modalità/importi dei tre bot |
| `components/controlroom/comandiBot.ts` | le RPC dei comandi. **Parte money-critical** |
| `components/controlroom/SchedaChiusura.tsx` | la scheda che decide un'uscita reale |
| `components/controlroom/SchedaPartita.tsx` | riga partita in gioco |
| `components/controlroom/SchedaPreMatch.tsx` | riga pre-match con loghi |
| `components/controlroom/PosizioniChiuse.tsx` | vinte/perse filtrabili, P&L globale + dettaglio |
| `components/controlroom/AzioniPartita.tsx` | video/statistiche/trading/segui-live + punto di ritorno |
| `components/controlroom/SplitSport.tsx` | tessere calcio/tennis, **sono il filtro** |
| `lib/controlRoom.ts` | modello della giornata, `soldiPerPartita`, `totaliGiornata`, `modoDi` |
| `lib/controlRoomCatena.ts` | catena dei tempi a 6 salti |
| `lib/controlRoomProposte.ts` | prezzo vivo, scostamento, motivo di non approvabilità |
| `lib/posizioniChiuse.ts` | una posizione = apertura + coperture |
| `lib/ritorno.ts` | ritorno al punto esatto |

### Backend — `Betfair/safe_strategy/`

| file | punti toccati oggi |
|---|---|
| `bot_service.py` | `process_requests(solo_chiusure)`, corsia «a-0» in `run_once`, `_attesa_interrompibile`, `_catena_dei_tempi` (t3) |
| `tools/storia_operazioni.py` | referto forense (nuovo, sola lettura) |
| `tools/conta_operazioni_live.py` | conteggio operazioni (nuovo, sola lettura) |

### Backend — `Betfair/mike/` (toccato il 15, vedi §2B)

| file | punti toccati |
|---|---|
| `service.py` | `_ordine_di()` (la chiave giusta), `_gia_appoggiata()` (freno fail-closed), `bet_id` salvato sempre dopo `place_order_live`, attività `place_saltato` |
| `service.py` ~1398 | `esposte`: il tetto `max_open_matches` conta paper e live **insieme** — noto, NON cambiato |
| `engine.py` | `_strip_openings`: fermare toglie le aperture, **non** le uscite — noto, NON cambiato |

### Test

- Frontend: **2348 verdi**, 0 rossi (erano 2288 il 14). `npx vitest run` in `frontend/`.
- Backend: **1304 verdi** su tutta `Betfair/`. `python -m pytest Betfair/ -q`.
- `npx tsc -p tsconfig.app.json --noEmit` → **13 errori preesistenti**, nessuno
  nei file della Control Room. Non regredire questo numero.

---

## 7. I commit (14 e 15 settembre)

**14 settembre — costruzione della Control Room**

```
c151431  feat: le tessere calcio/tennis diventano il filtro del banco
07505ba  perf: corsia preferenziale per le chiusure — dal clic all'ordine
6bb0229  fix: t3 misurava l'inizio del ciclo, non la decisione
b2c56b1  fix: soldi veri e soldi finti non si sommano più da nessuna parte
8226d00  feat: plancia di comando dei tre bot in Control Room
bcac6ad  feat: ritorno al punto esatto, azioni per scheda, pre-match, posizioni chiuse
f13e952  feat: Control Room a quattro schede, per calcio e per tennis
c47a9ed  docs: HANDOFF_CONTROL_ROOM.md — il punto di ripresa dei lavori
```

**15 settembre — i reperti della review, e il loop**

```
91011be  fix: due critici della review — i freni di Omega e la barra in testata
1ee606f  fix: tre critici della review — scritture distruttive e id che collidono
f73168a  fix: tre critici della corsia preferenziale (backend)
b8f2ee1  fix: ultimi due critici — il cancello di approvazione e la catena dei tempi
21b1a93  fix: otto reperti alti — perimetri, contatori e il pannello di comando
a5f2a71  fix: quattro reperti alti sul percorso che manda ordini veri
b1285a0  fix(mike): il loop dei green-up — 32 ordini reali identici al primo avvio
f1c92b4  fix: i tre test rossi lasciati dal commit precedente
c4b6172  fix(mike): LA RADICE del loop — una chiave scritta nella grafia sbagliata
cbb1f4c  fix: gli ultimi reperti della review — 53 su 53
```

⚠️ `b1285a0` è stato spinto **con quattro test rossi**, chiusi subito dopo da
`f1c92b4`. Tre erano finti DB che non sapevano rispondere a `trades_for_event`
(li bloccava il nuovo freno fail-closed), uno era un confronto fra float scritto
male. Resta scritto qui perché non succeda una seconda volta: *si guarda il
verde prima di spingere, anche quando si ha fretta*.

---

## 8. Stato al momento della consegna (15/09, 12:25 ora locale)

| bot | status | mode | note |
|---|---|---|---|
| **Mike** | `running` | **live** | stake **5,00 €**, `max_open_matches` **2** |
| Omega | `stopped` | paper | |
| Safe | fermo | paper | fermato ieri dopo la quinta operazione |

**Posizioni Mike ancora vive:**

```
#4777 paper open    under_entry  back@1.49  Daejeon Citizen v Kyoto
#4779 paper open    manual_close lay @1.55  Daejeon Citizen v Kyoto
#4780 LIVE  open    under_entry  back@1.45  Beijing Guoan v Pohang Steelers   bet 442889708346
#4812 LIVE  open    under_entry  back@1.55  Johor Darul Tazim v Buriram Utd   bet 442891669120
#4817 LIVE  pending under_green  lay @1.53  Johor Darul Tazim v Buriram Utd   bet 442892101412
#4818 LIVE  pending under_green  lay @1.43  Beijing Guoan v Pohang Steelers   bet 442892112965
```

**UN green-up per partita, ciascuno col suo `bet_id`.** È la prova che il freno
di `b1285a0` e la chiave corretta di `c4b6172` fanno il loro mestiere: prima,
allo stesso identico punto, ne uscivano trentadue.

### ⚠️ Due cose che un agente che riprende deve sapere subito

1. **L'applicazione desktop è CHIUSA.** L'ultimo battito di Mike è delle
   `10:05 UTC`, alla consegna sono le `10:25`: nessun servizio sta girando. I
   due green-up qui sopra sono ordini **veri appoggiati a mercato** e ci
   restano — ma **nessuno li sta sorvegliando**, e non partirà nessun settlement
   finché l'app non torna su. L'app la avvia **l'utente**: non chiuderla e non
   ricompilarla mai (è solo l'avviatore del `main.js` vivo).
2. **Il frontend va ricostruito** perché la Control Room mostri il lavoro di
   oggi: l'exe carica il bundle compilato, non i sorgenti. **Ricostruito il
   15/09 dopo `9143717`.**

---

## 9. Da fare (in ordine)

1. **Riavviare l'app** (utente). Serve a tre cose insieme: rimettere Mike sotto
   sorveglianza, far entrare in vigore `c4b6172` — finché il servizio gira col
   codice vecchio, **la radice del loop è ancora lì** — e attivare
   l'allineamento di §2C, che è per metà nei servizi.
2. ~~Ricostruire il frontend~~ — **fatto** il 15/09 dopo `9143717`
   (`npm run build` in `frontend/`, bundle in `frontend/dist/`).
3. **Rimisurare il tempo dal clic all'ordine** con `storia_operazioni.py`: la
   corsia preferenziale è pushata da ieri ma non è mai stata misurata in
   funzione. Atteso un crollo dai 4,2 s.
4. **Una review dedicata a `Betfair/mike/`** — engine, esecuzione,
   riconciliazione. **La review a 12 dimensioni non ha mai guardato lì dentro**:
   il loop non l'ha trovato lei, l'ha trovato l'utente guardando gli ordini
   veri. È il buco più grande rimasto, ed è sul percorso dei soldi.
   Da fare **solo su ordine esplicito dell'utente**.
5. Chiudere i due varchi noti di §10.
6. Decisione dell'utente in sospeso: **la doppia conferma sulla chiusura in
   live** è l'unica voce rimasta che scambia sicurezza con velocità.
7. Portare in live **gli altri bot**, uno per volta, con lo stesso metodo:
   stake piccolo, uscite approvate a mano, referto forense su ogni operazione,
   5 operazioni prima di dichiarare validato.
8. Decisioni aperte da prima: bet delay di Omega in paper, guardia combo di
   Safe, euristica finali tennis, cap di rischio.

---

## 10. Review a 12 dimensioni — ESITO

Lanciata sul codice di `f13e952` come workflow multi-agente: 12 dimensioni
cercano, **ogni reperto passa da 3 scettici indipendenti** con lenti diverse
(correttezza, riproducibilità, già-risolto) istruiti a **confutare**; sopravvive
chi regge a 2 su 3. Chiude un critico di completezza.

### Esito

**53 reperti confermati. 53 corretti.** Nessuno rimandato. In ordine di gravità:

- **10 critici** — fra cui: `omega_activate` che **azzerava i tre cap di
  rischio** a ogni accensione (fa `coalesce(p_params,'{}')`, non
  `coalesce(p_params, params)` come safe e mike: partire «senza parametri»
  significava partire **senza freni**); `cambiaImporto` che con i parametri non
  letti **riscriveva l'intero oggetto**, perdendo `strategy_modes` e
  `tennis_exit_approval`; la corsia preferenziale delle chiusure che girava
  **prima** della riconciliazione e poteva cancellare una riserva il cui ordine
  era già a mercato; id di raggruppamento che **collidevano fra bot diversi**.
- **~20 alti** — perimetri paper/live, contatori, cancelli di approvazione,
  catena dei tempi, pannello di comando.
- il resto fra medi e bassi.

⚠️ **Un reperto critico era un test scritto da me che asseriva il comportamento
sbagliato** («non si azzera niente: si manda solo la chiave»). Un test può
certificare un difetto: la dimensione 11, *«i test passano o passano a vuoto?»*,
non è una formalità e va rimessa in ogni review futura.

### Quello che la review NON ha coperto

- **`Betfair/mike/` non è mai stato guardato.** Vedi §9 punto 4.
- **Due varchi del critico di completezza restano aperti**, entrambi noti:
  - `lib/eventGroups.ts` → `groupTradesIntoCicli` raggruppa sull'**id nudo**: è
    la stessa classe di collisione già chiusa in `posizioniChiuse.ts`, dove la
    chiave è `chiave(bot, id)`. Qui non è ancora stata cambiata.
  - **`useControlRoom.ts` non ha un file di test dedicato.** È il pezzo che
    porta in pagina *tutti* i numeri della Control Room; è coperto di rimbalzo
    dai test di `ControlRoom.tsx`, non in proprio.

### Se va rilanciata

```
Run ID       wf_ddeb4007-342
Script       ~/.claude/projects/C--Users-Admin-Desktop-PYTHON-DATABASE-python-database-automation/
             ec0ecb56-4ba9-4225-91e9-8a1970be163b/workflows/scripts/review-control-room-wf_3ff59738-cb5.js
Trascrizioni ~/.claude/projects/C--Users-Admin/ec0ecb56-4ba9-4225-91e9-8a1970be163b/
             subagents/workflows/wf_ddeb4007-342
```

Ripresa (strumento `Workflow`):
`{ "scriptPath": "<Script qui sopra>", "resumeFromRunId": "wf_ddeb4007-342" }`

Ogni agente già concluso è in cache e torna istantaneamente. **Prima di
riprendere, leggi `journal.jsonl`** nella cartella delle trascrizioni: registra
il valore di ritorno di ogni agente, quindi dice quali dimensioni sono davvero
finite e con che reperti. Un risultato in cache può essere vuoto — il journal lo
dice, l'assenza di errori no.

Lo script vive sotto `~/.claude`, che una pulizia cancella: **ne esiste una copia
versionata nel repo**, `tools/review/review-control-room.js`. Da lì si rilancia
sempre (ripartendo da zero: si perde tempo, non correttezza).

### Le 12 dimensioni (per ricostruirla anche senza lo script)

1. paper e live mischiati — cercarne altri oltre ai quattro di §4.1
2. assente scambiato per zero (e lo zero vero scambiato per assente)
3. i comandi che accendono un bot su soldi veri (`comandiBot.ts`)
4. catena dei tempi e latenza
5. corsia preferenziale delle chiusure (backend Python)
6. proposte di chiusura — ci si clicca sopra e parte un ordine
7. posizioni chiuse e P&L globale
8. ritorno al punto esatto e navigazione
9. «Segui live»: registra davvero? (vedi la trappola §5.1)
10. design system e lingua
11. **i test passano o passano a vuoto?** (caccia ai falsi verdi)
12. il dato è davvero in tempo reale?

**Test alla consegna: 2348 verdi sul frontend, 1304 sul backend.**

---

## 11. Documenti collegati

| file | contenuto |
|---|---|
| `SPEC_STRATEGIA_S.md` | le 4 varianti di Strategia S, con le decisioni chiuse |
| `ESECUZIONE_LIVE.md` | specifica dell'esecuzione live |
| `STATO_PRODUZIONE.md` | checklist di produzione condivisa |
| `PIANO_MAESTRO_2026-09-14.md` | il contratto fra le tre sessioni di lavoro |
| `Betfair/safe_strategy/SESSIONE_LIVE_TENNIS_2026-09-14.md` | diario della sessione live |
