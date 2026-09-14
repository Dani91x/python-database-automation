# HANDOFF — CONTROL ROOM e primo bot validato in LIVE

> **Se sei un agente che riprende questo lavoro, questo è il file da leggere per primo.**
> Aggiornato: **14 settembre 2026**. Ultimo commit: `f13e952`. Tutto pushato su `master`.

La Control Room (`/control-room`) è la **cabina di regia** della piattaforma: da lì
il trader guarda i tre bot, approva le uscite e comanda tutto. Oggi è stato
**validato il primo bot in live con denaro reale**; gli altri seguiranno, e
passeranno da qui.

---

## 1. Che cosa è successo oggi, in una riga

Il bot tennis (Safe, strategia `tennis`) ha operato **con soldi veri**, 3 € a
segnale, per **5 operazioni chiuse, tutte in positivo, +0,44 €**. Le entrate
sono automatiche, le **uscite le approva il trader** dalla Control Room. Poi il
bot è stato fermato su richiesta dell'utente.

---

## 2. Le operazioni live di oggi (evidenza)

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

## 4. Il lavoro di oggi sulla Control Room

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

### Test

- Frontend: **2288 verdi**, 0 rossi. `npx vitest run` in `frontend/`.
- `Betfair/safe_strategy`: **766 verdi**. `python -m pytest Betfair/safe_strategy/tests/ -q`.
- `npx tsc -p tsconfig.app.json --noEmit` → **13 errori preesistenti**, nessuno
  nei file della Control Room. Non regredire questo numero.

---

## 7. Commit di oggi

```
f13e952  feat: Control Room a quattro schede, per calcio e per tennis
bcac6ad  feat: ritorno al punto esatto, azioni per scheda, pre-match, posizioni chiuse
8226d00  feat: plancia di comando dei tre bot in Control Room
b2c56b1  fix: soldi veri e soldi finti non si sommano più da nessuna parte
6bb0229  fix: t3 misurava l'inizio del ciclo, non la decisione
07505ba  perf: corsia preferenziale per le chiusure — dal clic all'ordine
c151431  feat: le tessere calcio/tennis diventano il filtro del banco
```

---

## 8. Stato al momento della consegna

- **Safe: `status=stopped`, `mode=paper`.** Fermato su richiesta dopo la quinta
  operazione. Fermare spegne le **aperture**: le posizioni restano sorvegliate
  (riconciliazione, settlement, uscite e approvazioni continuano a girare).
- Restano vive 5 posizioni **paper sul calcio**.
- Omega e Mike: `running`, `paper`.
- ⚠️ **La corsia preferenziale delle chiusure è pushata ma non ancora in
  funzione**: il servizio gira col codice precedente finché l'utente non
  riavvia l'app.
- ⚠️ Al momento dello stop il control era già su `mode=paper`, e non è stato
  l'agente a cambiarlo (`safe_stop` non tocca quella colonna). Da chiarire con
  l'utente se non è stato lui dalla UI.

---

## 9. Da fare (in ordine)

1. **Applicare i reperti della review a 12 dimensioni** (§10).
2. Riavviare l'app per attivare la corsia preferenziale, e **rimisurare il
   tempo dal clic all'ordine** con `storia_operazioni.py`: atteso un crollo dai
   4,2 s attuali.
3. Decisione dell'utente in sospeso: **la doppia conferma sulla chiusura in
   live** è l'unica voce rimasta che scambia sicurezza con velocità. Va tolta
   solo se lo dice lui.
4. Portare in live **gli altri bot**, uno per volta, con lo stesso metodo:
   stake piccolo, uscite approvate a mano, referto forense su ogni operazione,
   5 operazioni prima di dichiarare validato.
5. Decisioni aperte da prima di oggi: bet delay di Omega in paper (cambia i
   numeri storici), guardia combo di Safe, euristica finali tennis, cap di
   rischio.

---

## 10. Review a 12 dimensioni

Lanciata sul codice definitivo (`f13e952`) come workflow multi-agente: 12
dimensioni cercano, **ogni reperto passa da 3 scettici indipendenti** con lenti
diverse (correttezza, riproducibilità, già-risolto) istruiti a **confutare**;
sopravvive chi regge a 2 su 3. Chiude un critico di completezza.

### ⚠️ SE LA REVIEW SI INTERROMPE — non si ricomincia da capo

Ogni agente già concluso è in cache: alla ripresa i suoi risultati tornano
**istantaneamente** e riparte solo ciò che non era finito. Per riprenderla
servono due valori, ed è per questo che stanno scritti qui e non solo in chat:

```
Run ID       wf_ddeb4007-342
Script       C:\Users\Admin\.claude\projects\C--Users-Admin-Desktop-PYTHON-DATABASE-python-database-automation\ec0ecb56-4ba9-4225-91e9-8a1970be163b\workflows\scripts\review-control-room-wf_3ff59738-cb5.js
Trascrizioni C:\Users\Admin\.claude\projects\C--Users-Admin\ec0ecb56-4ba9-4225-91e9-8a1970be163b\subagents\workflows\wf_ddeb4007-342
```

Comando di ripresa (strumento `Workflow`):

```json
{ "scriptPath": "<Script qui sopra>", "resumeFromRunId": "wf_ddeb4007-342" }
```

**Prima di riprendere, leggi `journal.jsonl` nella cartella delle
trascrizioni**: registra il valore di ritorno di ogni agente, quindi dice
esattamente quali dimensioni sono già state completate e con che reperti. Un
risultato in cache può essere vuoto — il journal lo dice, l'assenza di errori no.

Lo script vive sotto `~/.claude`, che una pulizia cancella: **ne esiste una
copia versionata nel repo**, `tools/review/review-control-room.js`. Da lì la
review si rilancia sempre, anche perso tutto il resto (in quel caso riparte da
zero: si perde tempo, non correttezza).

Se anche quella sparisse, la review è comunque **ricostruibile**: le 12
dimensioni, le 3 lenti degli scettici e i criteri sono descritti in §3 e qui
sotto.

### Le 12 dimensioni (per rilanciarla anche senza lo script)

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

Verifica: 3 scettici per reperto, lenti *correttezza* / *riproducibilità* /
*già-risolto*, istruiti a **confutare** — nel dubbio il reperto cade. Sopravvive
chi regge a 2 voti su 3.

**Esito: da compilare quando la review termina.**

---

## 11. Documenti collegati

| file | contenuto |
|---|---|
| `SPEC_STRATEGIA_S.md` | le 4 varianti di Strategia S, con le decisioni chiuse |
| `ESECUZIONE_LIVE.md` | specifica dell'esecuzione live |
| `STATO_PRODUZIONE.md` | checklist di produzione condivisa |
| `PIANO_MAESTRO_2026-09-14.md` | il contratto fra le tre sessioni di lavoro |
| `Betfair/safe_strategy/SESSIONE_LIVE_TENNIS_2026-09-14.md` | diario della sessione live |
