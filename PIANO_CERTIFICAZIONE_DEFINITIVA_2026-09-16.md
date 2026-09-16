# PIANO — CERTIFICAZIONE DEFINITIVA DEI BOT (16/09/2026)

> Coordinatore: sessione `admin-e2` (Fable 5.1). Esecutori: **Opus 5** (costruzione) e
> **Sonnet 5** (misure, inventari, revisioni indipendenti, audit dei test).
> **La certificazione finale di ogni fase è del coordinatore**, che rilegge i diff,
> rilancia i test e i replay di persona e non firma nulla che non ha rieseguito.
>
> Documenti di partenza (letti, non riassunti qui): `HANDOFF_CONTROL_ROOM.md`,
> `STATO_PRODUZIONE.md`, `PIANO_MAESTRO_2026-09-14.md`, `ESECUZIONE_LIVE.md`,
> `SPEC_STRATEGIA_S.md`, `Betfair/mike/COSTITUZIONE_MIKE.md`,
> `Betfair/safe_strategy/COSTITUZIONE_SAFE_STRATEGY.md`, i RISCONTRO calcio/tennis,
> `SESSIONE_LIVE_TENNIS_2026-09-14.md`, e la memoria di progetto del 13-15/09.

---

## 0. Le condizioni dell'utente (vincolanti, non negoziabili)

> **Standard permanente per ogni bot, presente e futuro** (ordine dell'utente, 16/09):
> progetto → mappa di ogni condizione e della consapevolezza degli ordini → replay
> flumine su dati reali con codice di produzione in tutti gli scenari → paper come
> specchio della realtà → live solo se il paper conferma. Testo completo in
> `PROCESSO_STANDARD_BOT.md`. Questo piano è la sua prima applicazione.

1. **Le strategie non si toccano.** Nessuna soglia, minuto, quota, stake, tetto,
   gamba. Anche mettere un tetto dove non c'era è alterarle. L'unica differenza
   ammessa è PAPER o LIVE. Qualunque divergenza trovata che tocchi il *comportamento*
   → si scrive, si porta all'utente, **non si corregge di iniziativa**.
2. **Paper e live sono mondi distinti** e non si mischiano mai: né nei numeri, né nei
   tetti, né nei comandi. Idem **calcio e tennis**.
3. **I bot li accende solo l'utente**, sia in paper che in live. All'avvio dell'app
   nessun bot opera. Le posizioni già aperte restano sorvegliate (regola: niente che
   protegge può impedire di chiudere).
4. **Ogni bot va certificato sul replay flumine con le registrazioni reali**
   (calcio in `_live_raw/`, tennis in `Desktop/tennis_rec/`) e il replay deve
   riprodurre l'**esatto** comportamento di produzione: stesso feed, stesso servizio,
   stesso percorso ordini, matching di flumine con la coda vera.
5. **Con tutti i bot accesi il DB non deve andare in sofferenza** e la Stream API va
   usata al massimo (REST solo per cataloghi e fallback dichiarato).
6. **I test certificano**: un test che non sa diventare rosso non è un test. Ogni
   finto parla con le identiche chiavi e tipi del vero.
7. Vincoli operativi ereditati: mai `git add -A`; l'app la avvia/riavvia l'utente
   (mai ricompilare l'exe); nessun processo/registratore nuovo senza permesso; mai
   uccidere replay lunghi senza chiedere; codice ASCII, commenti in italiano;
   non regredire i 13 errori `tsc` preesistenti.

---

## 1. Stato di partenza (verificato il 16/09 mattina)

| voce | stato |
|---|---|
| repo | `master`, 1 commit non pushato (`dc0cc30`), working tree pulito su `Betfair/` e `frontend/src/` |
| test | backend `Betfair/` 3372 verdi (mike 605) · frontend 2396 verdi · `tsc` 13 errori preesistenti |
| migrazioni | **non verificate sul DB** (pendenti in memoria: `APPLY_ORDER_2026-09-11.md`, `omega_models_v4/v6`, `omega_daily_v2`, `tennis_*`, `mike_vincoli_flusso_fischio`, `safe_strategy_proposed`) |
| avvio app | `desktop/main.js` lancia scanner + `omega_service` + `safe bot_service` + `mike service` sotto watchdog; **ogni servizio rilegge `control.status` dal DB e se trova `running` riprende a operare** → è la causa dell'avvio automatico |
| Control Room | plancia con Omega / Safe (intero) / Mike + scheda tennis che accende solo Safe-tennis. Le 4 strategie Safe (base, esatto, punta, tennis) hanno già `variants` (chi apre) e `strategy_modes` (con che soldi) ma **non un interruttore ciascuna** |
| replay | esiste **solo per Mike**: `Betfair/mike/tools/replay_registrazioni.py` + `certificazione.py` + `banco.py` (38 partite, 0 violazioni, 7 scenari). Omega, Safe calcio e Safe tennis **non hanno replay** |
| registrazioni | calcio: 54 cartelle (3 sintetiche `_synth_*`), 42 con `.raw.jsonl`, mercati MATCH_ODDS + CORRECT_SCORE + O/U 0.5-8.5 + HT → **Omega, Safe calcio e Mike sono tutti replayabili**. Tennis: `Desktop/tennis_rec/20260707` + `setbetting_20260707`, 84 raw MATCH_ODDS + `.score.jsonl` → **Safe tennis replayabile** |
| flusso dati | scanner (`safe_strategy/service.py`) = Stream API su pool (≤180 mkt/conn) + REST fallback → scrive `safe_strategy_scan` write-on-change → i tre bot **leggono dal DB**. Canali locali WS 47331-47335 solo verso la UI |
| danni in DB | `params.variants = ["tennis"]` (base/esatto/punta spente anche in paper); `stake.backSize = 3` vale per tennis **e** punta |

Reperti aperti ereditati (nessuno si tocca senza l'utente): Mike `pre_exit_mode=taker`
ripropone la stessa uscita fino a 535 volte (regge solo grazie al freno del 15/09);
controllo A2 mai sollecitato; 6 fasi su 21 mai osservate (SETTLING richiede
`process_closed_market`); il banco non riproduce minimo .it, bet delay in-play, stop
giornaliero e tetto partite; Omega in paper senza bet delay (P4); guardia combo Safe
solo in paper (L4); finali tennis non escludibili (dato assente).

---

## 2. Fasi

### FASE 0 — Verità di partenza (Sonnet 5, sola lettura)

- **0.1 Migrazioni sul DB.** Per ogni file in `migrations/` dal 11/09: applicata sì/no,
  provato con query su `information_schema` / `pg_constraint` / `pg_proc`. Tabella con
  evidenza. **Nessuna applicazione**: la decide l'utente.
- **0.2 Registrazioni.** `Betfair/stream/tools/validate_recordings.py` su `_live_raw`
  e su `tennis_rec`: elenco COMPLETE / PARTIAL / NO_RAW, mercati presenti per evento,
  durata, gol/set. Esclusione dichiarata delle `_synth_*`.
- **0.3 Baseline.** Rilancio dei test e conteggio esatto; numeri da non regredire.
- **0.4 Stato di `control.params`** dei tre bot così com'è oggi nel DB, riga per riga
  (per la decisione dell'utente sui danni noti).

Uscita: `FASE0_VERITA_DI_PARTENZA_2026-09-16.md`.

### FASE A — All'avvio dell'app nessun bot opera (Opus 5 costruisce, Sonnet 5 rivede)

Meccanismo proposto (fail-closed, coerente con «ai soldi veri si arriva scrivendolo»):

- `desktop/main.js` genera un **`APP_BOOT_ID`** all'avvio e lo passa in env a tutti i
  runner. Un riavvio da **watchdog** (crash) conserva lo stesso id.
- Ogni servizio (`mike/service.py`, `omega/omega_service.py`,
  `safe_strategy/bot_service.py`) al primo giro confronta l'id con
  `control.stats.boot_id`: se **diverso** → `status='stopped'`, `mode='paper'`,
  in Safe `strategy_modes` tutte a `paper`; scrive un'attività
  `avvio_app_bot_fermato` con l'elenco di ciò che ha azzerato; salva il nuovo id.
  Se **uguale** (riavvio watchdog) → non tocca nulla: un bot acceso dall'utente non
  deve morire in silenzio a ogni crash.
- **Mai toccati i `params`** (soglie, stake, variants): solo status e modalità.
- Le fasi di **protezione** (riconciliazione, settlement, uscite delle posizioni già
  aperte, richieste UI) continuano a girare a bot fermo — va verificato per ciascun
  servizio quali fasi girano con `status='stopped'` e scritto nel referto.
- Tennis legacy (`tennis_runner`): verificare che stati `requested/arming/armed`
  persistiti non ri-armino bot all'avvio; `TENNIS_LIVE_ORDER_MODE` resta `PAPER`.
- Control Room: mostra «fermato all'avvio dell'app, attivazione manuale» leggendo
  l'attività (il servizio dichiara, la pagina non inventa).

Test che certificano (finti con le chiavi vere del `control`): avvio con `running`
→ `stopped` + attività; stesso boot id → intoccato; `strategy_modes` live → paper;
posizione aperta a bot fermo → le uscite girano; parametri identici prima/dopo.

### FASE B — Control Room: separazione e un interruttore per ogni bot (Opus 5 + Sonnet 5)

- **B.1 Certificazione globale della pagina.** Per ogni riquadro le cinque domande
  (fonte unica · età del dato · netto di commissione · cosa mostra quando manca ·
  paper e live separati) più la sesta: **calcio e tennis separati**. Verdetti a 4
  stati. Uscita: `CERTIFICAZIONE_CONTROL_ROOM_2026-09-16.md`.
- **B.2 Un interruttore per bot.** Sei interruttori, ciascuno con la propria
  modalità e la doppia conferma in live: **Omega**, **Mike**, **Safe base**,
  **Safe esatto**, **Safe punta** (scheda calcio) e **Safe tennis** (scheda tennis).
  Backend Safe già pronto (`variants` + `strategy_modes`): i comandi scrivono
  **sempre esplicitamente** entrambe le mappe, mai ereditano; una strategia spenta
  non compare in `variants`, una accesa in paper ha `strategy_modes[x]='paper'`.
  Nella scheda calcio non compare il tennis, e viceversa. Gli scalper tennis legacy
  restano fuori finché l'utente non li nomina.
- **B.3 Test.** Payload RPC di ogni interruttore confrontato campo per campo;
  default fail-closed; nessuna somma paper+live; isolamento per sport; i due varchi
  noti (`groupTradesIntoCicli` su id nudo, `useControlRoom.ts` senza test proprio).
- Ricostruzione del frontend (`npm run build`) alla fine; riavvio app = utente.

### FASE C — Replay flumine per OGNI bot sulle registrazioni reali (il cuore)

Principio: **la catena certificata è stream registrato → scanner vero → riga
`safe_strategy_scan` → feed vero del bot → servizio vero (`run_once`) → ordine vero
su flumine (matching con coda) → esito riletto dal bot**. Niente snapshot a mano,
niente fill a mano, niente finti.

- **C.0 Banco comune** (Opus 5). Generalizzare `Betfair/mike/tools/banco.py`
  (`DbMemoria`, `MercatoFlumine`) e il replay in un banco riusabile da tutti i bot,
  senza duplicare: lo scanner **vero** (`Scanner` di `safe_strategy/service.py`)
  alimentato dai book di flumine produce le righe di scan; ogni bot legge da lì.
  Tetti di flumine aperti (`max_live_trade_count`, `max_order_exposure`,
  `max_selection_exposure`); lettura ladder con `_offer_price/_offer_size`;
  `order.status.value`; bet delay in-play, minimo di giurisdizione e place-and-trim,
  stop giornaliero e tetto partite **riprodotti** (passando da `run_once`, non da
  `_run_event`). Verificare che il replay di Mike non costruisca la riga di scan a
  mano: se lo fa, passare dallo scanner vero.
- **C.1 Mike** (Opus 5). Chiudere i buchi: A2 sollecitabile, 6 fasi mai viste
  (SETTLING via `process_closed_market`), scenari sulle leve di servizio. La
  riproposizione a 535 in `taker` si **misura e si riporta**, non si corregge.
- **C.2 Omega** (Opus 5). Aggancio di `omega_service.run_once` + `omega_engine` al
  banco; Correct Score completo dallo scanner. Controlli derivati dal manuale Omega:
  2 gambe sempre, catena λ, veto HT→FT, target per gamba, obiettivo di giornata,
  green-up, cap. Il replay mostrerà la divergenza **paper istantaneo vs live con
  bet delay** (P4): si riporta come reperto, decisione dell'utente.
- **C.3 Safe calcio** (Opus 5): base, esatto, punta contro `SPEC_STRATEGIA_S.md` e
  `RISCONTRO_CALCIO`. `pre_ko` congelato al primo tick in-play, FOK, `close_plan`,
  guardia combo (L4 riportata, non toccata).
- **C.4 Safe tennis** (Opus 5): sulle 84 registrazioni di `tennis_rec`.
  `build_tennis_ctx_from_scan` dal percorso vero, `evaluate_tennis`, take profit e
  stop, uscite con approvazione: due scenari dichiarati (approvata subito / mai
  approvata).
- **C.5 Parità paper = live per bot**: per ogni ordine la riga che il percorso paper
  e quella che il percorso live manderebbero, confrontate **campo per campo** (come
  già fatto per Safe sulla coda). Qualunque campo diverso = reperto.
- **C.6 Scenari e copertura** (Opus 5): come i 7 di Mike, per ogni bot; il referto
  conta i controlli **sollecitati** e dichiara «non lo so» sui mai sollecitati.
- **C.7 Falsificazione** (Sonnet 5, indipendente): reintrodurre i cinque difetti del
  15/09 e uno per bot scelto dal revisore sul codice corretto: il replay **deve**
  diventare rosso. Se non lo fa, il controllo non certifica.
- Uscita per bot: `CERTIFICAZIONE_REPLAY_<bot>_2026-09-xx.md` con 4 verdetti,
  partite, tick, decisioni, ordini, violazioni, reperti per l'utente.

### FASE D — Carico DB e Stream API con tutti i bot accesi (Sonnet 5 misura, Opus 5 progetta)

- **D.1 Inventario** di chi legge/scrive cosa e a che cadenza (scanner, 3 bot, job
  quote tennis, runner, UI realtime, canali locali). Regola: nessuna chiamata Betfair
  duplicata; solo lo scanner parla con i mercati.
- **D.2 Misura** nel picco pomeridiano con tutti i bot in paper: letture/scritture al
  minuto per tabella, durata del giro per fase (`Cronometro`), copertura stream vs
  REST per evento, ampiezza del pool, budget IO Supabase.
- **D.3 Stream al massimo**: verificare che ogni mercato rilevante in-play stia sul
  pool (180/conn × N conn, 10 conn max), REST solo cataloghi e fallback dichiarato;
  la percentuale `feed_source=stream` per evento va in Control Room.
- **D.4 Se il DB soffre**: proposta ordinata di alternative (i bot che ricevono le
  righe di scan sul canale locale con il DB a fallback; cadenze; batch) con costi e
  rischi. **Decide l'utente.** Nessuna strategia toccata.
- Uscita: `CERTIFICAZIONE_CARICO_2026-09-xx.md` con i numeri.

### FASE E — I test certificano (Sonnet 5 audit, trasversale)

- **E.1** Audit dei test esistenti dei tre bot e della Control Room: finti con chiavi
  o tipi diversi dal vero; test che asseriscono il comportamento sbagliato; test
  che passano a vuoto. Per ciascuno: riscritto, cancellato, o tenuto, con motivo.
- **E.2** Prova di mutazione sui percorsi dei soldi: si rompe una cosa, i test
  devono diventare rossi.
- Uscita: `AUDIT_TEST_2026-09-xx.md`.

---

## 3. Ondate e parallelismo

| ondata | in parallelo | chi |
|---|---|---|
| **1** | 0.1-0.4 · A · C.0 (+ verifica scan a mano nel replay Mike) | Sonnet · Opus · Opus |
| **2** | B · C.2 Omega · C.3 Safe calcio · C.4 Safe tennis · D.1-D.3 | Opus ×4 · Sonnet |
| **3** | C.1 buchi Mike · C.5 parità · C.6 scenari · C.7 falsificazione · E.1-E.2 · D.4 | Opus · Sonnet |
| **4** | referti finali, decisioni dell'utente, push, riavvio app (utente) | coordinatore |

Ogni ondata si chiude solo con la **certificazione del coordinatore**: diff riletto,
test rilanciati, replay rieseguiti, falsificazione provata. Un agente non dichiara
«fatto»: consegna evidenza (`file:riga`, numeri, comandi).

---

## 4. Protocollo dei delegati (la parte per evitare gli errori ricorrenti)

Ogni brief contiene, sempre: obiettivo in una riga · file da leggere prima · file che
può toccare e che **non** può toccare · le 7 condizioni del §0 · gli 8 errori già
fatti (fill a mano, `getattr` sui dict del ladder, `order.status` Enum, tetti di
flumine, falso positivo del controllo, snapshot a mano, tipi di ritorno dei finti,
grafie diverse fra scritto e letto) · definizione di fatto · formato del referto
(cosa ho verificato, come, cosa NON ho verificato, reperti per l'utente).

Regole di ingaggio:
- Opus 5 costruisce; Sonnet 5 rivede **senza conoscere la conclusione di Opus** (gli
  si dà il codice, non la tesi).
- Nessun agente corregge un comportamento di strategia: lo segnala.
- Nessun agente applica migrazioni, avvia processi nuovi, chiude l'app, fa push.
- Ogni test nuovo va **falsificato** (si rompe il codice, il test diventa rosso) e il
  referto lo dice.

---

## 5. Decisioni dell'utente — DATE il 16/09 (ordini, non proposte)

1. **Sì**: all'avvio dell'app si azzerano anche le modalità **live** (fail-closed).
2. **Mike `taker` (535 riproposizioni): VA RISOLTO.** È il dialogo fra stato della
   gamba (ctx) e stato della riga (DB), non strategia. Entra nella Fase C.1.
3. **Paper = specchio della realtà, con flumine per TUTTI i bot.** Il bet delay di
   Omega in paper non si decide da solo: **si uniforma**. Ogni percorso paper (Omega,
   Safe, Mike, scalper, tennis) deve passare dal client simulato di flumine (coda del
   runner, bet delay, FOK, matching con la coda), non da un `paper_fill` locale. Nuova
   voce **C.8**.
4. **Guardia combo Safe (L4): uniformare.** Interpretazione del coordinatore: paper e
   live devono fare la stessa cosa e il live è la realtà → il paper si allinea al
   live (piazza e svolge), la guardia solo-paper decade. Se l'utente intende il
   contrario (guardia anche in live) lo dice e si inverte: è una riga.
5. **Tutto si accende e si spegne dalla UI**, paper e live, in modo facile e diretto,
   **sia dalle singole schede dei bot sia dalla Control Room**, e deve funzionare alla
   perfezione. `variants=["tennis"]` nel DB si ripristina dalla UI con gli interruttori
   della Fase B, non a mano.
6. **Stake personalizzabile per qualsiasi bot e strategia**: `stake.backSize` non può
   più valere insieme per tennis e punta. Chiave di stake per strategia (Safe: base,
   esatto, punta, tennis) e per bot, con migrazione dei valori attuali senza cambiarli.
   Nuova voce **B.5**.
7. Migrazioni: il coordinatore dirà quali applicare dopo la Fase 0.
8. **Perimetro «ogni bot» = TUTTI**: calcio → Omega (+ Missioni), Safe base/esatto/
   punta, Mike, **Scalper calcio** (`scalper_session` per partita: scalper, sniper,
   theta); tennis → Safe tennis, **tennis_scalper, tennis_pro, tennis_flb,
   tennis_swing** (armati per partita via `tennis_bot_arm`).

9. **Mike `ko_green` = lay APPOGGIATA in ogni modalità** (ordine dell'utente, 16/09 h13: «mettiamola
   appoggiata così risparmiamo una marea di chiamate»). Modifica di STRATEGIA ordinata: va in
   Costituzione §15.6 con data e motivo. Vincoli dati dall'utente: si appoggia solo a mercato
   aperto e in gioco (al fischio Betfair sospende e cancella gli ordini non abbinati); a ogni
   sospensione (gol precoce) Betfair può cancellare l'ordine → alla riapertura il bot **rilegge
   l'ordine da Betfair** (`bet_id`) e distingue vivo / cancellato (attività + ripresentazione
   se la finestra è aperta, altrimenti copertura) / abbinato / abbinato in parte; la finestra
   non scorre in sospensione. Il banco deve simulare la morte degli ordini appoggiati alla
   sospensione (flumine non lo fa) e lo scenario va provocato su una registrazione con gol
   precoce. → **C.1-bis** (Mike) + requisito banco (C.0).

10. **Operazioni manuali e cash-out globale** (16/09 h18). Il bot gestisce SOLO le sue
    operazioni; quelle manuali dell'utente le ignora (niente cap, chiusure, riconciliazione).
    **Unica eccezione: il cash-out globale** dell'utente sulla partita: al controllo successivo il
    bot deve accorgersi che le sue posizioni sono state chiuse da lui e **non fare altro** su
    quella partita (stato «chiuso dall'utente», attività, nessuna riapertura/copertura/re-ingresso).
    → controllo + scenario `cashout-globale` per Mike, Omega, Safe (C.13).

### Conseguenze sul piano

- **Fase A** copre anche `scalper_control` (righe `requested/running` che il
  supervisore rilancerebbe) e i bot tennis armati per evento.
- **Fase B.2** diventa: un interruttore per **ognuno** dei bot del punto 8, dalla
  Control Room **e** dalla scheda del bot, con la stessa RPC e la stessa verità.
- **B.5 (nuova)**: stake per strategia/bot, UI + backend + migrazione dei valori.
- **C.8 (nuova, prima di C.2-C.4)**: architettura «paper via flumine» per tutti i bot.
  Progetto scritto (Opus 5, architetto) → revisione (Sonnet 5) → certificazione del
  coordinatore → costruzione. Il replay della Fase C certifica lo **stesso** percorso
  simulato che il paper userà in produzione: un solo motore di matching, ovunque.
- **C.9 (nuova)**: replay e certificazione anche di scalper calcio (già su flumine:
  `run_backtest.py`, `sim_strategy.py`) e dei quattro bot tennis (`backtest_pro.py`,
  `validate.py`): verificare che il backtest esistente usi il codice di produzione
  del bot e non una copia (`scalper_lab`, `theta_strategy.py`).
- **C.1** include la correzione del `taker` di Mike, con test che riproduce le 535
  riproposizioni e diventa verde solo con la correzione.

### C.11 — RIUTILIZZABILITÀ: lo standard come strumento, usato di default (ordine dell'utente, 16/09)

«Ogni nuovo bot, o i precedenti, se voglio testarli devono passare da flumine ed essere
certificati; l'intero comparto backtest deve essere assolutamente veritiero.» Quindi:
- **un punto d'ingresso unico** `python -m Betfair.stream.backtest.certifica <bot> ...`
  per qualunque bot registrato: replay sul banco comune, referto a 4 verdetti, copertura
  dei controlli; il replay di Mike vi si assorbe (mai due implementazioni);
- **un registro dei bot** (servizio di produzione, sport, mercati, controlli, spec) e un
  **test di contratto** che elenca i bot in produzione (runner di `main.js`, `variants`
  Safe, `_BOT_REGISTRY` tennis, scalper) e fallisce se uno manca dal registro; i bot senza
  controlli sono «registrati senza certificazione», rumorosi, non silenziosi;
- `MODELLO_BOT_NUOVO.md` con i passi per un bot nuovo;
- `CLAUDE.md` di progetto (creato il 16/09) che ogni sessione carica: lo standard, il
  promemoria su «paper/live», il punto d'ingresso unico, i vincoli operativi;
- `PROCESSO_STANDARD_BOT.md` come testo dello standard.
Requisito girato al delegato C.0 come parte della consegna del banco.

### C.10 — CONSAPEVOLEZZA DELL'ORDINE (ordine dell'utente, 16/09; trasversale a B, C, E)

«Ordine x a prezzo y: il bot sa se è stato abbinato? in che quantità? tutto o parziale?
si comporta di conseguenza? In UI il trader ha queste informazioni?» Per OGNI bot e OGNI
tipo di ordine (taker, appoggiato, place-and-trim, green-up, copertura, cash-out, chiusura)
si scrive la **matrice degli esiti**: abbinato subito tutto · parziale subito · appoggiato
poi parziale · appoggiato poi tutto · mai abbinato e scaduto (sospensione/chiusura) ·
annullato dal bot · rifiutato da Betfair · esito ignoto (timeout) · abbinato a prezzo
migliore · mercato annullato. Per ogni cella: cosa il bot deve SAPERE (`size_matched`,
`size_remaining`, `avg_price_matched`, `status`, `bet_id`), cosa deve FARE secondo la sua
Costituzione/spec (proseguire, aspettare, ripiazzare, coprire SOLO la parte abbinata,
annullare il residuo), cosa la UI deve MOSTRARE (chiesto vs abbinato, residuo, prezzo).
Prima la matrice sulla carta con `file:riga` di dove ogni reazione vive o manca (Opus,
sola lettura); poi ogni cella **provocata** nel replay (C.6: coda `_piq`, volume
scambiato, `guasti`) e nel paper; le celle non provocabili dichiarate ⊘ con causa.
Regola: mai «abbinato» dedotto dal prezzo di mercato senza conferma di Betfair.

### Regola operativa dal 16/09 h11:40 — UNA partita di riferimento finché il setup non è finito

Ordine dell'utente: «scegli una partita completa e verifichiamo in prima battuta su una singola
partita; quando avremo finito tutto lanceremo i backtest massivi su tutti i bot, prima voglio
finire tutte le parti di set up e ottimizzazione».
- **Calcio: `35760084`** (COMPLETE, 30/06, 7,4 MB raw, tutti i mercati: MATCH_ODDS,
  CORRECT_SCORE, O/U 0.5-8.5, HT, BTTS, DC; Mike vi opera in-play: 4202 decisioni, 10 ordini,
  stati fino a LIVE_KO_GREEN). Serve a Mike, Omega, Safe base/esatto/punta, scalper.
- **Tennis: `35790650`** (COMPLETE 93,9 %, 165 min, 5 buchi per 9,3 min dichiarati) in
  `Desktop/tennis_rec/20260707/`. Serve a Safe tennis e ai 4 bot tennis.
- Ogni delegato usa queste due per i confronti prima/dopo; `--complete` e i replay massivi
  solo su ordine del coordinatore, a setup chiuso.

### Esito inventario flumine (16/09, `FLUMINE_CAPACITA_SIMULAZIONE_2026-09-16.md`; il difetto principale riprodotto dal coordinatore)

- 🔴 **`SimulatedMiddleware` montato DUE volte**: `add_client` lo monta già (`baseflumine.py:91-94`),
  il repo ne aggiunge un secondo a mano in 14 punti (`banco_comune.py:1298`, `run_backtest.py`,
  `replay_registrazioni.py`, scalper, tennis). Riprodotto: 1 dopo il costruttore, 2 dopo la riga
  1298. Misurato su 36006953: lay appoggiata 85,72 € abbinati con 1 → 200,34 € con 2 (+134 %).
  **Ogni fill passivo di ogni replay fatto finora è sovrastimato**: le certificazioni con
  ordini appoggiati vanno rifatte. Correzione affidata al delegato del banco (helper idempotente,
  test `== 1`, test sui 14 file, falsificazione, prima/dopo su 35760084).
- Versione: installata **2.13.11**, ultima **3.2.2** (3.1.0 de-dup del middleware, 3.2.0 matching
  passivo dinamico e fix loop sul cancel). **Non aggiornare ora**: 3.0 è breaking in 21 punti e
  cambierebbe i numeri di ogni certificazione firmata; da valutare a setup chiuso.
- Documentazione: readthedocs è 404; quella viva è `betcode-org.github.io/flumine/` e descrive
  la 3.x (13 divergenze doc↔codice elencate in §H: `commission_base` non implementata, valuta
  GBP cablata, 3 trading control di default, `_piq` e `traded/2` non documentati).
- Prestazioni: il replay crea 448.476 `MarketBook` per 58.801 aggiornamenti reali (7,6× di
  spreco, `_read_loop` emette un book per ogni cache a ogni riga); emettendo solo i mercati
  cambiati **14,2 s → 4,5 s** (79 s → 14,5 s sul file da 26 MB); `json.loads` è il 2-3 %;
  `orjson`/`ciso8601` presenti nel `.venv` ma non nell'installazione usata; eventi in serie →
  `ProcessPoolExecutor` per evento ≈ 8× senza cambiare un numero. → **C.0-perf** a
  correttezza chiusa.
- Altri: `transaction_limit` non aperto (5000/ora); flumine non simula le cancellazioni altrui
  in coda, la morte dei LAPSE al passaggio in-play, la commissione; `order.simulated.matched`
  ha già i fill con `publish_time` (da mettere nel referto); `run_backtest.py` non protetto dai
  `publish_time` non monotoni (47 % dei book). Tutti girati al delegato del banco.

### Esito C.0 — BANCO COMUNE CERTIFICATO dal coordinatore (16/09)

`Betfair/stream/backtest/banco_comune.py` (1174 righe): raw → flumine → **`Scanner._apply_market_book`
vero** (`service.py:493`) → `build_rows` vero → tabella di scan in memoria → feed vero → servizio;
punteggi via `Scanner.apply_score_state` (estratta da `poll_scores`) al `ts_ms` di ricezione (ritardo
IPS già dentro); `pre_ko` congelato dallo scanner; ladder di flumine (dict) tradotto in vista
`.price/.size` (senza, `best_price` leggeva None in silenzio); **bet delay sull'orologio virtuale**
(`attendi_esecuzione:683`); FOK vero di Betfair; tetti di flumine e valuta GBP (`min_bet 1.00`)
aperti in `cliente_simulato:547`. Iniettabilità additiva (`Scanner(orologio=…)`, test di parità).
**Riutilizzabilità**: `python -m Betfair.stream.backtest.certifica <bot>` (impronta sha1 del codice,
versioni, qualità registrazioni), `registro_bot.py` (11 bot, 1 certificabile, 10 «registrati senza
certificazione» col motivo), test di contratto su `main.js`/`variants`/`_BOT_REGISTRY`/scalper,
`pytest -m cert` nella suite, `MODELLO_BOT_NUOVO.md`.
Mike rieseguito: 39 partite, 0 violazioni, ma **azioni 116→145 e ordini 88→114** (FOK vero, fill a
`t+delay`, rifiuti non più contati come fill) e **H1/H2 re-ingresso da 1 a 0 sollecitazioni**
(reperto in indagine); `--complete` prima non filtrava (TypeError ingoiato): **solo 13 su 39 sono
COMPLETE**. Diff payload a mano vs scanner: `score_home/away` 0 vs None, O/U solo 3.5/4.5 vs tutte,
19 chiavi assenti nel finto. Copertura §6: 6.1, 6.2, 6.8 coperte; 6.3/6.4/6.5/6.7 parziali;
**6.6 (concorrenza) non coperta**; ⊘ da chiudere: `run_once`, parità paper/live, multi-evento,
place-and-trim/minimo .it, rifiuti Betfair provocati, settlement da `process_closed_market`,
`CHECK` in `DbMemoria`, sospensione prolungata, prezzo migliore, void.
Verifica del coordinatore: suite **3514 verdi**; `certifica mike 36006953` (24 s, referto con
copertura onesta: 23/24 mai sollecitati su una PARTIAL in cui Mike non piazza); `--complete`
lanciato; falsificazioni proprie: attesa del bet delay tolta → 1 rosso; modulo di Mike tolto dal
registro → 1 rosso. Indagine in corso su H1/H2 e sui 3 ordini rifiutati da un controllo di flumine.

### Esito C.12a — CERTIFICATO dal coordinatore (16/09)

`PlaceResult` con `size_requested/price_requested/size_remaining/error_code/size_cancelled/
lapsed/voided/betfair_updated_at` (dal report REST vero; il residuo sul place è derivato, quello
autoritativo viene da `listCurrentOrders`); `PlaceRifiutato` (rifiuto certo ≠ ignoto);
**`cancel_order_live`** (`omega_market.py:973`, esito riletto; timeout → solleva) e
`execution.annulla_su_betfair:326` punto unico; `aggiorna_trade:303` scrive le colonne nuove se
esistono; `place_rifiutato` con codice e `place_parziale` in Safe/Omega; Omega `_ordine_ancora_vivo:2323`
prima di ogni terminale; Mike `_mark_trade_cancelled:3017` punto unico: un cancel **arriva a
Betfair**, riletto, e se fallisce la riga resta in riconciliazione; `_segui_resting_live` legge
`size_remaining` da Betfair. Migrazione `trades_consapevolezza_ordine_2026-09-16.sql` (scritta,
da applicare; nessuna RPC da toccare). 24 test con payload REST grezzi e funzioni vere.
Verifica del coordinatore: 24 verdi; falsificazione propria (cancel sempre `ok`) → 2 rossi.
Debito verso la UI: `KIND_IN_ATTESA_DI_UI` (Mike: `cancel_richiesto`,`cancel_esito`; Omega: + 
`place_rifiutato`,`place_parziale`) da etichettare in C.12b e cancellare. Patch Safe in corso
(parziale a ogni giro, cancel prima del terminale, guardia combo L4 uniformata).

### Esito C.4 — Safe TENNIS sul banco — CERTIFICATO dal coordinatore (16/09 h17)

`safe_strategy/tools/replay_tennis.py` (1104) + `certificazione_tennis.py` (26 controlli) +
46 test (3 marcati `cert`). Catena vera: MATCH_ODDS tennis registrato nello `ScannerReplay`,
punteggio dal sidecar via `Scanner.apply_score_state` (ramo tennis, set/game),
`build_tennis_ctx_from_scan` → `evaluate_tennis` → **`bot_service.run_once` intero** →
`execution.place` FOK su flumine con bet delay; uscite con cancelletto `tennis_exit_approval`;
`DbMemoriaSafe` con le 36 firme di `bot_db.py`. Su 35790650: 11 scenari, **0 violazioni**, 15
controlli su 26 sollecitati; **l'ingresso non è esercitabile** (chi è avanti nei set non ha mai
2 game di vantaggio: è la partita, non un parametro) → T1-T4/T11 ⊘; chiusure a **0 tick** dal
segnale (conferma del 14/09 dal vivo); `mai-approvata` → nessuna chiusura, proposte decadute;
riavvio e esiti ignoti coperti. **Parità paper/live divergente e misurata**: live apre a 1,05
(il primo ordine a 1,06 ucciso dal FOK di flumine), paper apre a 1,06 e non fallisce mai,
`bet_id` None in paper, zero ordini a flumine in paper (è il progetto C.8). Regola mai-due-lay:
L1 (righe DB **e** ordini EXECUTABLE su Betfair) verde ×1594; L2 ⊘ (nel tennis la chiusura è un
FOK che nasce e muore nel giro). Reperti: il banco non porta la `competition` (con
`excludeBestOf5` acceso nessun ingresso: falso negativo del banco, dichiarato con flag);
`MercatoFlumine` senza `read_market` → nessun settlement (T8 ⊘); il freno live legge
`LIVE_ORDER_MODE` dall'env (dichiarato nel replay); `validate_recordings` cerca
`.scores.jsonl` (correzione affidata). Lezione: la prima J2 restava verde col difetto
`res.ok` ignorato perché dipendeva dall'attività del bot → riscritta per guardare l'ordine di
flumine: **un controllo che dipende dalla confessione del bot non certifica**.
Verifica del coordinatore: 40 unitari verdi; falsificazione propria (L1 tollera due lay) →
2 rossi. In corso: ricerca di una registrazione che eserciti l'ingresso (seconda partita di
riferimento tennis). Voce di registro `safe_tennis` da aggiungere (coordinatore).

### Esito C.0-perf — replay veloce a referto identico — CERTIFICATO dal coordinatore (16/09 h19)

Profilo (campionatore 5 ms su 728 s): **flumine + banco = 0,6 %**; `service._run_event` 90 %, di
cui `omega_model.lambdas_from_pre_ko` **83,6 %** (6.779.932 griglie Poisson ricalcolate da un
`pre_ko` congelato: 1.586 argomenti distinti in tutta la partita); `build_rows` 8,7 %.
Leve: `GeneratoreLibri` (memorizzazione dei book, stessi valori nello stesso ordine) 15,0 → 2,9 s
sul livello stream (5×; 62,9 → 10,9 s sul file da 26 MB), end-to-end ~1 % perché flumine pesa
0,6 %; `orjson` solo nel `.venv` (non installato); write-on-change e logging già a posto (misurato);
**pool `--worker`** (default 3, tetto core−1, spenta sotto pytest): 1 partita × 3 scenari 71,9 →
41,9 s (1,72×), referto e diario identici; memoria **176-184 MB per worker** (l'ipotesi «oltre
1 GB» non regge). Test di identità (7): decisioni, ordini, fill uno per uno, righe di scan, tick;
falsificazioni: book saltato → rosso, memo non invalidato → rosso (preso anche un difetto del
delegato). Verifica del coordinatore: 7 verdi; falsificazione propria (memoria mai invalidata) →
5 rossi. **La leva grossa è nel bot**: `lru_cache` su `_poisson_grid` misurata in memoria: base
1028,7 → 444,7 s CPU (2,31×), taker 2,37×, **sha del referto identica**; un gradino sopra → ~5×.
**Autorizzata dal coordinatore** come memoizzazione pura con condizioni (funzioni pure, chiave
senza arrotondamenti nuovi, risultati immutabili, test elemento per elemento, sha identica).
Addendum fatti: `DbMemoria.ht_ft_rows` (lista vuota dichiarata ⊘, mai `None`);
`_lapse_alla_sospensione` (LAPSE a ogni SUSPENDED in gioco, fonti citate; su 35777617 R1 resta
«non lo so»: Mike annulla o abbina prima della sospensione); **fedeltà del tempo**: `placeOrders`
sincrona in produzione (3,3 s Betfair misurati in HANDOFF §4.2) → `attendi_esecuzione` = esatto
`place_latency + betDelay` (prima dipendeva dalla liquidità del mercato), cadenza che riparte a
fine giro (banco e Mike). Il sintomo tennis **non era l'orologio**: gli scenari con posizione
iniettata agiscono in istanti diversi; a ingresso condiviso i fill sono identici. Letture
(`list_current_orders`, `read_book`): nessuna misura → **120 ms per chiamata, dichiarati «assunti»**
(decisione del coordinatore), con riga nel referto. Comando: `certifica mike 35760084
--scenari base,taker --worker 3`.

### Esito C.2 — OMEGA sul banco — CERTIFICATO dal coordinatore per la copertura raggiunta (16/09 h18)

`omega/tools/replay_registrazioni.py` (1562) + `omega/certificazione.py` (32 controlli) + 94 test.
Catena vera: scanner → `scan_feed.ScanRowCache` vera → `omega_service.run_once` intero (cadenza
20/60 s reale, 3 giri dopo il fischio per il settlement da WINNER) → `place_lay_live` →
flumine. Tre agganci dichiarati (`_real_market`, cache condivisa con `updated_at` ribasato,
`_mono` = tempo di mercato). `DbMemoriaOmega`: 45 firme di `omega_db.py` verificate, indici
unici del reserve-first riprodotti. Nomi delle scoreline derivati dai `selectionId` globali
(formula a gusci verificata sui dati: il raw non ha il catalogo). Su 35760084, 9 scenari, **0
violazioni, 18/32 sollecitati**; scenario `apertura`: 1 ordine vero (lay 3-3 @300, 5,26 €,
511 book di bet delay, settlement +5,00 netto); cap-stretto clamp vero; bot-fermo, feed-stantio,
esiti-ignoti, riavvio coperti. **Paper vs live misurato**: riga identica su questo ordine ma
percorso diverso (paper senza flumine, senza bet delay, senza coda, senza `bet_id`). Regola
mai-due-lay: E1 (identità distinte fra ordini vivi, pending, open/hedged) ×228 verde; E2 ⊘.
Verifica del coordinatore: 715 test Omega verdi; `omega_service.py` senza residui della
mutazione dichiarata; falsificazione propria (E1 tollera due lay) → 3 rossi.
**«Non lo so» (14)**: green-up/cash-out/chiusure (D1-D6, J4) mai entrati (il bancato 3-3 mai
raggiungibile: serve una registrazione con il punteggio bancato che si avvicina → massivi),
veto HT→FT (tabella storica assente), parziali/rifiuti, annulli. **Reperti**: R1 il banco mostra
un giorno con UNA partita (`legs_remaining` 2 → target di gamba ~125 €, size 131 € senza
controparte: Omega non apre; §6.6 multi-evento è necessario per Omega); R2 su questa partita
Omega non aprirebbe comunque (§11 scarta i candidati per centesimi; l'unico sovrapprezzato è a
lay 300, fuori `price_max` 120); R3 un lay a 300 con 5,26 € impegna 1.572 € di liability **con
tutti i cap a zero** → utente; R4 `PlaceResult` del banco senza `size_remaining`. Registro:
voce `omega` aggiunta dal coordinatore.

### Esito C.2-bis — Omega: manuali e cash-out globale (16/09 h19:30, verificato dal coordinatore: 103 test verdi, `aggregate_trades` senza filtro `origin` confermato)

E1 conta solo le lay del bot (discrimine `omega_trades.origin`: dal 16/09 auto e manuale usano
lo stesso ref `omega-t<id>`; un ordine vivo senza riga resta del bot). Scenari `manuale-e-bot`
e `cashout-globale`, controlli 34. **Reperti (non corretti, per il riepilogo)**:
- **R6** i numeri con cui il bot decide contengono le operazioni manuali: `aggregate_trades:338`
  non filtra `origin` → target di gamba, `stop_on_goal`, `daily_loss_cap`, `max_open_liability`
  vedono la liability dell'utente (misurato: 70 € «del bot» contro 0 delle sue gambe). Patch:
  aggregati per DECIDERE filtrati su `origin='auto'`, totali di pagina completi.
- **R7** il green-up automatico decide anche sulle righe manuali (`_greenup_candidates:3688`,
  §12 della Costituzione lo prescrive): **conflitto fra §12 e l'ordine dell'utente h18** →
  decisione utente. Sulle aperture il bot già salta la partita dell'utente (`manual_event_ids`).
- **R8** il cash-out globale non esiste nel backend (la UI manda un `cashout` per gamba, nessuno
  stato per evento); dopo le chiusure il bot non apre più (E4 ×110 verde) ma per effetto
  collaterale (riga `origin='manual'` → evento escluso, finestra di 3 giorni): chiudere UNA
  gamba di due esclude anche l'altra, mai dichiarato. Patch: marker esplicito sull'evento
  (colonna su `omega_events` → migrazione).
- **R9 pericoloso**: chiusura fatta dall'utente **sul sito Betfair** non viene mai riletta (le
  righe `open` non passano da `reconcile_pending`; `_alert_stale_open` solo dopo 8 h): il green-up
  coprirebbe una posizione che non esiste più → un back con soldi veri. Patch: rileggere
  `list_current_orders`/`listClearedOrders` per le `open` con `bet_id` in `settle_open:2580`.
  ⊘ non provocabile sul banco. **Da correggere prima di qualunque live di Omega.**
- R10 sul book sottile il cash-out si abbina in parte: E4 a due livelli (divieto di aprire
  sempre; «non fare altro» solo a residuo zero: fermare la copertura di un residuo sarebbe il
  contrario della protezione).

### Esito C.3 — SAFE CALCIO sul banco — CERTIFICATO dal coordinatore per la copertura raggiunta (16/09 h18)

`safe_strategy/tools/replay_registrazioni.py` (1391) + `certificazione.py` (**56 controlli, uno
per voce del RISCONTRO**, costanti della SPEC nel controllo, non lette dai params) + 106 test.
Catena vera: scanner → `bot_service.run_once` intero (2 s) → `execution.place` → flumine; nomi
Correct Score dal `selection_name` di `validate_opportunity.py`; `DbSafeMemoria` 36+6 firme;
`MercatoSafe` con `read_market` per il settlement. **Le tre strategie sono tutte valutate**
(BASE 3060, ESATTO 6120, PUNTA 3060 valutazioni, ragione scritta a ogni giro): **zero segnali**
perché la 35760084 ha favorita 1,35 / sfavorita 9,2 contro le bande 1,40-1,80 e 4-8 della SPEC
→ non è una partita da BASE; ESATTO ed PUNTA cadono su punteggio/entrata. 9 scenari, 31/56
sollecitati: BASE 8/17, ESATTO 5/10 (**E10 ⊗ «selezione aggiuntiva» non implementata**), PUNTA
5/10, trasversali FOK/J1-J7 conformi. **Violazione vera T12 (regola mai-due-lay)**: due
«Investi» manuali con chiavi diverse → 60 giri con due lay vive sulla stessa selezione; l'indice
unico copre solo l'automatico → **chiarito dall'utente (h18): le operazioni manuali il bot le
IGNORA e opera sulle sue**; T12 ristretto alle lay del bot + controllo nuovo T13 (le manuali non
alterano le decisioni del bot, il bot non tocca le manuali). Da replicare su Mike (righe
`manual_close`) e Omega (`omega_manual_requests`) nella passata C.7.
**Paper vs live**: lay chiesta 12,0 → live abbinata 11,0 (−2 tick, `bet_id`), paper 12,0 al
prezzo chiesto senza `bet_id`. Falsificazioni del delegato: banda `favPreMin` → B6 ×3064 rossi;
`_execute` che scrive i numeri chiesti invece di quelli di Betfair → J1/J3 rossi. 5 falsi
positivi esclusi (giudizio spostato a fine giro; T8 sul manuale). Verifica del coordinatore:
105 unitari verdi; falsificazione propria (banda favorita allargata nel controllo) in corso.
Registro: `safe_base/esatto/punta` collegati dal coordinatore al replay C.3.
**Ingressi e uscite delle tre strategie non esercitabili sulla partita di riferimento → serve
il massivo (o una partita nelle bande).**

### Esito C.3-bis — Safe calcio: seconda partita, manuali, cash-out (16/09 h20:30, verificato: 120 test verdi)

Corpus scansionato con le funzioni vere: **14 registrazioni su 39 hanno il `pre_ko` incompleto**
(BASE e PUNTA impossibili lì: difetto 19 come dato); BASE candidate: **35797769** (COMPLETE
95,4 %, fav 1,64 / dog 5,4) e 35768297; **PUNTA: nessuna partita nel corpus** (dog 4-8 con
favorita avanti 2-0/3-1/3-0 dal 66' non esiste); ESATTO 13 candidate. **35797769 = seconda
partita di riferimento calcio per Safe**: 3 ordini veri, ESATTO 335 segnali (lay «Altro
risultato» 32,0 → back 34,0), BASE 0 (la favorita live non entra mai in 1,20-1,34), 335
violazioni **tutte E10** (selezione aggiuntiva non implementata, già nota); «non lo so» 25 → 19
su 58; ciclo di ritentativo dopo un `place_rifiutato` esercitato. T12 ristretto al bot (tace su
due manuali). **T13 verde**: gambe del bot identiche con una riga manuale viva sulla stessa
selezione; tre barriere indipendenti impediscono al bot di toccarla. **Reperto**: i CAP non
filtrano `origin` (`open_trades:130`, `aggregate_rows:348` → `build_risk_ctx:3886`): 32,80 € di
responsabilità manuale dentro i cap del bot → utente. **T14 VIOLATO ×282**: Safe non ha un
cash-out globale (`cashout_event/all` vivono nella coda del runner e non toccano le sue
tabelle); con una `cashout` per riga il bot **aggiunge una gamba automatica da 0,04 € sulla
posizione già chiusa** e continua le uscite; nessuno stato «chiuso dall'utente». Patch
proposta: kind `cashout_event` in `process_requests:1466` + marcatore per evento letto in
`scan_and_place:4140` e `_exit_candidates:1999`. **Da correggere prima di un live di Safe calcio**
(il tennis usa lo stesso servizio: verificare). Reperto banco: `save_event_model` assente.

### Esito C.1-ter — Mike: mai due lay + cash-out globale — CERTIFICATO dal coordinatore (16/09 h21)

Guardia unica `engine._una_sola_lay:1704` (ultima parola di `decide`, applicata `:1885`) +
`lay_in_volo:1686` (viva **o** `needs_reconcile`): con una lay in volo sulla selezione nessuna
lay nuova; annullamento subito, la nuova al giro dopo solo a vecchia non più viva, dimensionata
sul reale; ignoto/fallito → `pending_reconcile`. Copre ogni ramo presente e futuro; `over_cover`
(due BACK) escluso e dichiarato. Controllo J5 (stato e decisione). Cash-out globale via bot
(`_request_flatten:1855` → `_decide_flatten:1774`): `no_reentry=True` anche in gioco, attività
`chiuso_dall_utente`, chiusure permesse, partita non terminale (P&L contabilizzato); controllo R2.
Replay: 35777617 gol-precoce **J2/J5 → 0** (azioni 6→9, arriva a LIVE_CLOSING); 35760084 base
identico; `cashout-globale` OK (R2 ×5835, ordini solo prima del cash-out). Suite `Betfair/` 3898
verdi. Verifica del coordinatore: 665 verdi; falsificazione propria (una lay a esito ignoto non
conta come in volo) → rossi. **Limite da portare all'utente**: se chiude la posizione **fuori dal
bot** con una sua lay su Betfair, Mike non se ne accorge (`list_current_orders` filtra per
`customerStrategyRef`) e continua a gestire il back; servirebbe leggere la posizione di conto
(chiamata Betfair nuova, non fatta). Costituzione §15.7 con due riquadri datati.

### Esito C.4-ter — validatore per sport e terna tennis (16/09 h20, verificato dal coordinatore: 80 test verdi)

`validate_recordings.py`: sport letto dal raw (`eventTypeId`), finestra tennis
[primo book → CLOSED] (senza CLOSED mai COMPLETE), plausibilità dal sidecar (partita più lunga
del registrato → PARTIAL forzato), verdetto che dichiara la finestra; calcio invariato (0
differenze su 39). Tennis: **19 COMPLETE su 84** (prima 0). **Terna di riferimento tennis
decisa dal coordinatore**: **35792939** (COMPLETE 98,3 %) per l'INGRESSO ed esercita T6
(ingresso a 1,02 portato a fine partita: 3 scenari OK, 0 violazioni); **35795560** (PARTIAL
83,2 %) per uscite in perdita e uscita obbligatoria (T7 ×145); **35790650** (PARTIAL 87,3 %)
per le uscite in profitto. Da usare tutte e tre nei massivi tennis.

### Esito C.4-bis — seconda partita di riferimento TENNIS: `35795560` (16/09 h17:30, verificato dal coordinatore)

Scansione dei 60 sidecar con `parse_tennis_scores` e i parametri veri: 34 partite hanno la
condizione d'ingresso; 6 passate alla catena vera, 5 producono segnali. Scelta **35795560**
(copertura 84,5 %, 5 buchi/19,5 min, quota d'ingresso 1,08). 12 scenari, **0 violazioni, 22
controlli su 26 sollecitati**: T1-T4/T11 (ingresso vero: back sul leader, 1,08 in banda, set
1-0 con 2+ game, singolare, stake per strategia 2,00) e T7 ×145 (uscita obbligatoria) ora
esercitati; chiusure a 0 tick; `approvata-subito` 2 firme, 2 cash-out, +0,23 €;
`mai-approvata` nessuna chiusura (T7-APPROVAZIONE dichiarata, scelta del 14/09); scenario nuovo
`uscita-ignota` → L1 ×117 senza violazioni (mai una seconda lay mentre la prima è in volo).
⊘ residui: T6 (ingresso < 1,03: lo esercita 35792939), T8 (settlement: `read_market` assente
nel banco), T10 (turno non pubblicato), L2. Due falsi positivi dei controlli corretti (gamba
`open` contata come viva; chiave `exit_proposta` scritta a mano invece di `PROPOSTA_KEY`
importata: difetto 27 applicato ai controlli). `validate_recordings` accetta ora `.score.jsonl`
e dichiara il nome trovato (4 test, falsificazione).
**Reperto di fedeltà del banco (in verifica)**: la quota di abbinamento dell'ingresso cambia fra
scenari sulla stessa partita (1,16 / 1,41 / 1,58) perché `attendi_esecuzione` fa scorrere il
tempo per tutti a ogni piazzamento in base alle chiamate del giro → regola del tempo da
allineare alla produzione (REST in-play blocca per il bet delay; le altre chiamate costano la
loro latenza) e da documentare: scenari diversi confrontabili solo a sequenza di chiamate
identica. Reperto: la copertura del validatore usa la finestra del calcio → nessuna tennis può
essere COMPLETE (finestra per sport affidata).

### Esito C.1-bis — Mike `ko_green` APPOGGIATA — CERTIFICATO dal coordinatore (16/09 h16)

`_is_resting_leg:946` → `ko_green` sempre appoggiata (`pre_exit_mode` governa solo
`under_green`/`reentry_green`); `_decide_ko_green:2337` senza ri-presentazione;
`appoggiabile_in_gioco:505` = aperto **e** in gioco (prima si aspetta; chiuso → copertura);
finestra ferma finché non si può appoggiare; «in volo» include `pending_reconcile` (J2/J4).
Riapertura (`_sorveglia_sospensione:1662`, prima di `decide`): rilettura per `bet_id`
(`_rileggi_ordine_appoggiato:1522`), classificazione (`:1490`), quattro reazioni
(`_applica_esito_riapertura:1604`): vivo / scaduto (attività + gamba chiusa; finestra aperta →
una nuova appoggiata, altrimenti copertura) / abbinato / parziale; ignoto → `pending_reconcile`.
Costituzione §15.6 riscritta con riquadro datato; `ko_green_retry_s` dichiarato senza effetto
(config, Costituzione, UI); controllo R1; `RITMI_DICHIARATI` svuotata (una serie di ko_green
identici torna violazione). Vincolo DB dichiarato: `mike_trades.status` non ammette `cancelled`
→ gamba scaduta senza abbinato resta `error` con motivo nel meta (nessuna migrazione).
Replay: 35760084 base identico prima/dopo; taker **32 ri-presentazioni → 1**, fill e P&L
identici; 35674515 base **J2/J4 → 0**; R1 sollecitato ×9528 e ×1773, verde.
Verifica del coordinatore: Mike 651 verdi (suite 3584); falsificazione propria (appoggio
consentito prima dell'in-play) → 2 rossi.
**Reperti**: (1) su 35777617 (gol al 2') J2 ×1 **pre-esistente**: sostituzione di una lay viva
abbinata in parte (8,15/10,14) con `cancel` + `place` nella STESSA decisione (`engine.py:2341-
2350`), divergenza da §15.7 «mai due lay vive»: se il cancel non è confermato la nuova nasce
comunque → **decisione utente** (proposta: solo `cancel`, nuova gamba al giro dopo, come già fa
`altre_lay`); (2) il ramo «scaduto alla sospensione» non capita mai sui dati reali perché
flumine lapsa solo se cambia `version` e il banco solo al fischio → addendum al banco (LAPSE a
ogni sospensione in gioco) girato al delegato delle prestazioni.

### PRIMO REPLAY VALIDO — Mike su 35760084, banco corretto, eseguito dal coordinatore (16/09 h15:00)

`certifica mike 35760084 --scenari base` (codice bot `4a9d8a4d5231`, con il lavoro C.1-bis in
corso nell'albero): 55.769 tick, 5.838 decisioni, 12 azioni, **10 ordini reali su flumine, 10
righe `mike_trades`**, 7 abbinamenti su 6 ordini per 26,42 €, P&L netto −2,30 € (commissione 5 %,
non è il metro), bet delay: 4.813 book passati durante le attese, LAPSE al fischio 0, 2.439 righe
di scan scritte dallo scanner vero, stati visti: WATCH → PRE_ENTRY_PENDING → PRE_OPEN → HOLD →
LIVE_KO_GREEN → LIVE_UNCOVERED → LIVE_COVER_PENDING → LIVE_COVERED → LIVE_CLOSING → FLAT.
**0 violazioni su 25 controlli; 19 sollecitati, 6 «non lo so»**: A2 (stato terminale), B2 (feed
stantio), F1 (tetto liability), F2 (bot fermo/stop) → si provocano con gli scenari; H1/H2
(re-ingresso) non esercitabili su questa registrazione (verdetto dell'indagine).
Durata: ~10 min per scenario → ottimizzazione C.0-perf lanciata (vincolo: referto identico).
Reperto per il banco: `DbMemoria` non espone `ht_ft_rows` (chiamato dal servizio).

### Esito C.0-bis — BANCO CORRETTO — CERTIFICATO dal coordinatore (16/09, h13:30)

Quattro correzioni (`Betfair/stream/backtest/INDAGINE_C0_2026-09-16.md`): **un solo
`SimulatedMiddleware`** (`assicura_middleware_simulato:746`, tolte 15 chiamate manuali nel repo,
`transaction_limit` aperto); **`cancel_order_live` simulato** col cancel vero di flumine e il
`CancelResult` di `omega_market` (`:522`); **orologio monotono** (`:827`, 47,3 % dei book più
vecchi del precedente, salti fino a 182 s: era la causa dei 3 «rifiuti» — `STRATEGY_EXPOSURE`
con tempo negativo — che erano del banco, non di Betfair); **LAPSE come Betfair** al passaggio
in gioco (`_lapse_al_fischio:991`; alla sospensione lo fa già flumine; PERSIST sopravvive).
Referto §6.8 completo: versioni, impronta, comando, qualità, fill uno per uno, P&L
lordo/commissione/netto con l'aliquota di produzione.
Su 35760084 prima→dopo: **violazioni 10 (J2×5, J4×5) → 0** (erano del banco: annullo impossibile
→ gamba pending → freno), `reconcile_pending` 28→1, `cover` 28→0, ordini 10=10, fill 26,67→26,42 €,
netto −2,07→−2,30 €. **H1/H2 (re-ingresso)**: verdetto (a) — con il bet delay l'uscita al
fischio abbina solo in parte, il motore copre il residuo e FLAT arriva al 31' con 4 gol, fuori
finestra: sulle 39 registrazioni il re-ingresso non è mai esercitato → «non lo so».
Verifica del coordinatore: 45 test verdi; una sola chiamata `add_market_middleware` residua ed è
dentro l'helper; falsificazioni proprie: lapse al fischio spento → 1 rosso, orologio non
monotono → 1 rosso. **Reperto vero rimasto su 35674515**: J2/J4 «nuova `ko_green` con
`ko_green-0-3` a esito IGNOTO» → in carico a C.1-bis. Gol precoce per lo scenario: 35777617 (2').
⚠️ Tutti i replay firmati prima delle 12:03 vanno rifatti (middleware doppio, orologio, cancel,
lapse). ⊘ residui per rischio (stime del delegato): parità paper/live 1 g · place-and-trim/
minimo .it 1-1,5 g · `run_once` 0,5-1 g · rifiuti Betfair provocati 0,5 g · settlement da
`process_closed_market` 0,5 g · multi-evento 1 g · `CHECK` 0,5 g · void 0,5 g · sospensione
prolungata 0,25 g · prezzo migliore 0,25 g.

### Esito C.1 — Mike taker 535× — CERTIFICATO dal coordinatore (16/09)

Radice: in `taker` la gamba di uscita passa da `execute_place` (`service.py:506`), dove su
`no_fill` (`:596-608`) nessun ordine nasce e nessuna riga viene scritta → il freno
`_gia_appoggiata` non trova nulla e il `ctx` non ricorda il tentativo → `_decide_reentry_open`
(`engine.py:2894`) e il ramo taker di `PRE_OPEN` (`:1984`) rifanno la stessa domanda a ogni giro
(`_decide_ko_green:2296` se la faceva già). Correzione: `registra_rifiuto`/`ctx.rifiuti`
(persistito) + `tentativo_gia_rifiutato` (chiave ruolo|ciclo|mercato|selezione|lato|finale +
prezzo + size: book mosso o size cambiata = domanda nuova; ciclo nuovo = pulito; mai su esito
ignoto; mai in `dry`); percorso `resting` (produzione) intatto. `ko_green` non toccato (§15.6
prescrive la ri-presentazione ogni `ko_green_retry_s`); per `under_green`/`reentry_green` la
spec tace → fail-closed dichiarato in Costituzione §6. J1/J2 su `_in_volo` (include
`pending_reconcile`), J4 allargato, P1 per ruolo con `P1-DICHIARATA`.
Numeri (A/B nello stesso processo, banco già senza middleggio doppio): 35760084 base e taker
**identici** prima/dopo; 35674515 taker: proposte 875 → 31, `reentry_green` 845 → 1, `no_fill`
872 → 28, ordini 3 → 3. Verifica del coordinatore: Mike 625 verdi; falsificazione propria (chiave
senza prezzo: un book mosso non verrebbe più interrogato) → 1 rosso.
Reperti: in `taker` `ko_green` si ri-presenta 25-32 volte per partita (§15.6 alla lettera, ma
25-32 chiamate REST per un'uscita; §15.6 nasce prima della resting live) → **decisione utente**;
P3 resta rossa in taker (6-10×) per lo stesso ritmo → soglia o esenzione; scenario
`taker-esiti-ignoti` scritto, non eseguito; **il banco esercita solo `mode='live'`**: il ramo
`deferred` (paper + bet delay in-play) mai percorso → C.0-bis (parità paper/live nel replay).

### Esito C.12b — UI consapevolezza ordini — CERTIFICATA dal coordinatore (16/09)

`lib/statoOrdine.ts` (logica pura: chiesto/abbinato/residuo/prezzo medio/scorrimento con
`fonte: colonna|nota|assente`, esito appoggiato/parziale/abbinato/annullato/rifiutato/
riconciliazione/regolato/ignoto, `errorCode`, `aggiornatoAl`; **mai** abbinato dedotto da
`size`, residuo da chiesto−abbinato, prezzo medio dal chiesto; quota ≤1 = assente) +
`components/trading/StatoOrdine.tsx` (riga e compatto). Montato su Omega `MatchTradesTable:365`,
Safe `SafeTradesTable:715,733`, Mike `MikeMatchCard:940` (adattatore `lib/mike.ts:92`),
Control Room `SchedaPartita:234`, `PosizioniChiuse:194`, `SchedaChiusura:137`. Appoggiato ≠
aperto (`resting` passato a `statusMeta`). Zero-per-assente corretti in `PlacedOrdersPanel:38`,
`TerminalPositionsRail:203,230` + guardia sui sorgenti. Etichette per `place_parziale`,
`cancel_richiesto`, `cancel_esito`, `place_rifiutato`; `KIND_IN_ATTESA_DI_UI` cancellati
(contratto TS equivalente). Verifica del coordinatore: frontend **2503 verdi**, `tsc` 13,
55 verdi sui due contratti Python, falsificazione propria (abbinato dedotto da `size`) →
7 rossi; bundle ricostruito. Reperti: `safe_strategy_proposed.payload` senza abbinato/residuo
(la scheda lo dichiara); Mike non pubblica `size_remaining` nello stato (residuo con asterisco);
`lib/betfair.ts:229` classifica un esito ASSENTE come `unmatched` (decisione di stato: E.2);
`isRestingMeta` perde `live_resting_immediato`; tennis senza timestamp nel payload.

### Esito patch Safe (C.12a-Safe + L4) — CERTIFICATO dal coordinatore (16/09)

`bot_service.py`: a ogni giro di riconciliazione la riga pending porta abbinato/residuo/prezzo
medio/`betfair_updated_at` (write-on-change, memo per trade) + attività `place_parziale`;
**punto unico prima di ogni terminale** (`:774-793`, `_annulla_prima_del_terminale:956`):
cancel richiesto → riletto → residuo > 0 **o esito ignoto** ⇒ la riga resta in
riconciliazione (più stretto di Omega); abbinato nel frattempo ⇒ posizione; paper non
annulla; mercato senza `cancel_order_live` ⇒ nota `cancel_non_disponibile` e comportamento
storico. **Guardia combo L4 rimossa** (`:5161`): paper e live fanno la stessa cosa, quella del
live (piazza e svolge); i numeri paper delle combo cambiano da oggi (dichiarato nel codice).
Verifica del coordinatore: 830 verdi nel perimetro; falsificazione propria (riga terminale
anche con ordine vivo) → 3 rossi. Residui girati a C.12a: `order_state_by_bet_id` senza
`matched_date/placed_date`; percorso coda flumine (`omega_service.py:2211`) che porta a
`error` con `bet_id` senza cancel. UI dei kind nuovi → C.12b (in corso).

### Esito Fase B-1 — CERTIFICATA dal coordinatore (16/09)

Modello di stato senza flag nuovi (`frontend/src/lib/interruttori.ts:153`): Omega/Mike =
`status`+`mode`; Safe `<strategia>` = servizio in corsa **e** strategia in `variants`, live
solo se `mode='live'` **e** `strategy_modes[x]='live'`; `variants` non letti = stato non letto
(non si comanda). Ogni gesto riparte dai params correnti e scrive **entrambe le mappe
complete** (`paramsAccensioni:212`); spegnere l'ultima strategia = `safe_stop` (una lista
vuota verrebbe letta come «tutte»); accendere la prima = `safe_activate` con params espliciti.
Scheda calcio: omega, mike, safe-base, safe-esatto, safe-punta; scheda tennis: safe-tennis.
`comandiBot.ts` è un adattatore su `lib/interruttori`; la pagina Safe monta lo stesso
`PannelloBot`; `creaComandiTennis` eliminata (solo-tennis = caso particolare del modello).
Stake per strategia: `stake.per_strategia` (nasce vuota, `engine.py:252/364/382`, letta
per nome in `_to_signal:1757`), ripiego per lato dichiarato in UI (badge «ereditato»);
`soloTennis` scrive su `per_strategia.tennis`, quindi la punta non si muove più.
Migrazioni scritte, non applicate: `safe_strategy_stake_per_strategia_2026-09-16.sql`
(facoltativa) e **`omega_activate_conserva_params_2026-09-16.sql` (DA APPLICARE)** + test di
contratto `test_contratto_activate_params_2026_09_16.py` (nessuna `*_activate` con `'{}'`).
Verifica del coordinatore: backend **3488 verdi, 0 rossi**; frontend **2429 verdi**; `tsc` 13;
falsificazione propria (mappa `strategy_modes` non più completa) → 3 rossi; bundle ricostruito.
**Follow-up in corso**: le pagine singole (`useMike.ts:206`, `Omega.tsx:283`) cambiavano
modalità con `*_activate` (che accende un bot fermo): decisione del coordinatore → il cambio
di modalità passa **solo** da `*_update_params(p_mode)` condiviso; test di parità sul bot fermo.
`model`/`manual` di Safe restano scritti esplicitamente ma senza interruttore (da valutare).

### Esito C.10 (16/09, `MATRICE_CONSAPEVOLEZZA_ORDINI_2026-09-16.md`, 340 righe; verificato a campione dal coordinatore)

**Il dimensionamento sull'abbinato è corretto ovunque** (Omega/Safe via `exposures` sul
`size` confermato, Mike via `leg.matched`, scalper/tennis via `_matched_position`). Il
problema è **sapere** e **mostrare**:
- `PlaceResult` (`omega_market.py:512`) non ha `size_remaining` né la size chiesta; le
  tabelle `omega_trades`, `safe_strategy_trades`, `mike_trades` **non hanno colonne** per
  abbinato, residuo, prezzo medio, ultimo aggiornamento da Betfair: alla conferma `size` e
  `price` vengono sovrascritti con l'abbinato e il chiesto sparisce. `betfair_live_orders`
  e `tennis_live_orders` hanno tutto, ma nessuna scheda bot le legge.
- **Nessun annullamento vero sul percorso REST**: `omega_market` non ha `cancel_order_live`
  e nessuno dei tre bot chiama un cancel; gli «annulla» di Mike sono contabili, l'ordine
  resta vivo su Betfair. Il ramo taker di `PRE_OPEN` riemette la stessa uscita a ogni ciclo.
- Nessun bot legge `errorCode` (`INSUFFICIENT_FUNDS`, `INVALID_PROFIT_RATIO`,
  `BET_TAKEN_OR_LAPSED` indistinguibili da `ok=False`); in Safe un rifiuto certo del
  place-and-trim arriva come eccezione e la riga resta `pending` su un ordine inesistente;
  `place_submin` accodato senza FOK può restare vivo fuori dalla riconciliazione; su un
  parziale con residuo vivo Safe/Mike restano `keep` finché il residuo non muore.
- scalper/sniper/theta chiamano `place_order` senza gestire un `False`; `tennis_pro` e
  `tennis_swing` non leggono `size_remaining` né `status`; void di mercato dedotto da
  Omega/Safe (CLOSED senza WINNER) e mai controllato su `marketStatus`.
- **UI**: solo Mike distingue chiesto/abbinato/residuo/prezzo medio; Omega e Safe mostrano
  un solo `size`; un ordine solo appoggiato appare come `APERTO`; tre punti mostrano
  «€0,00» al posto di assente; `scorrimento_tick` e `price_medio` salvati in
  `meta.esecuzione` e mai renderizzati; nessuno mostra «quando l'ho saputo da Betfair».
- Provocabilità nel banco: esiti 1-5, 8, 9 sì; 6 ⊘ (cancel inesistente); 7 parziale
  (niente minimo .it/place-and-trim); 10 ⊘ (`read_book` torna `None`).
- Costituzioni disallineate col codice (Mike `:1793,1815`, Safe `:367-369`); le spec non
  contengono le parole «parziale», «residuo», «annullato».

**C.12 (nuova, costruzione)**: (a) backend — `PlaceResult` con size chiesta e residuo;
`cancel_order_live` in `omega_market` + uso nei tre bot dove oggi l'annullamento è solo
contabile; `errorCode`/`violation_reason` letti e scritti in attività; rifiuto certo del
submin → riga chiusa, non `pending`; colonne `size_requested/size_matched/size_remaining/
avg_price_matched/betfair_updated_at` sulle tre tabelle trade (migrazione da scrivere);
(b) UI — chiesto/abbinato/residuo/prezzo medio/stato/ultimo aggiornamento su ogni riga
ordine di Omega, Safe, Mike e Control Room; appoggiato ≠ aperto; mai zero per assente;
(c) banco — esito 6 e 10 provocabili; (d) spec — Costituzioni allineate e arricchite di
parziale/residuo/annullato (doc-updater, senza cambiare regole).

### Esito Fase 0 (16/09, `FASE0_VERITA_DI_PARTENZA_2026-09-16.md`, 602 righe)

- **Migrazioni**: 13/17 applicate con evidenza diretta (la più forte: `mike_vincoli_flusso_fischio`,
  240 rigetti CHECK fino alle 10:56 del 14/09 e zero dopo). Con riserva: `omega_models_v6`
  (16 chiavi invece di 17 dichiarate), `omega_models_v4` (riscritta da v5/v6, non isolabile),
  `omega_activity_realtime_2026-09-12` (publication Realtime non leggibile via PostgREST),
  `safe_strategy_proposed_2026-09-14` (provata solo invocando le RPC con id inesistente).
  `mike_history.sql` superseduta da v2. Nessuna migrazione risulta da applicare con certezza:
  le quattro riserve si sciolgono con una query diretta (utente) o si accettano.
- **Registrazioni calcio** (`_live_raw`, 3 sintetiche escluse): **13 COMPLETE, 26 PARTIAL,
  12 NO_RAW**. ⚠️ Le «38 partite» della certificazione Mike comprendevano quindi PARTIAL.
- **Registrazioni tennis**: `20260707` 88 cartelle, 60 con raw (2 COMPLETE, 58 PARTIAL), 28
  solo sidecar; `setbetting_20260707` 24 raw tutte PARTIAL con copertura <30 %. **Bug reale
  dello strumento** `validate_recordings.py:353,415`: cerca `.scores.jsonl`, il recorder
  tennis scrive `.score.jsonl` → falso negativo sistematico sul tennis. Da correggere nel
  banco comune (strumento, non strategia).
- **Baseline**: 3372 verdi backend, 2396 verdi + 30 skip (`*.cert.test.tsx`) frontend, 13
  errori `tsc` preesistenti. Da **rilanciare a ondata 1 chiusa** (i numeri sono stati presi
  mentre altri delegati scrivevano nel working tree).
- **Controlli DB**: la riga di Mike diceva `running/live` con **battito del 15/09 14:37 e app
  chiusa** (il referto la dava per «accesa ora»: verificato dal coordinatore, non lo è, zero
  posizioni aperte). È esattamente il difetto della Fase A: al prossimo avvio dell'app Mike
  ripartirebbe in live da solo. La scrittura correttiva sul DB è stata **negata al
  coordinatore** dal classificatore: **non riavviare l'app prima che la Fase A sia
  certificata**, oppure fermare Mike dalla UI subito dopo l'avvio. Safe: `variants=["tennis"]`,
  `strategy_modes.tennis=live`, `stake.backSize=3` condiviso, `daily_loss_stop=-50` attivo,
  cap a 0. Omega: tutti i cap a 0.

### Esito Fase A — CERTIFICATA dal coordinatore (16/09)

Meccanismo: `desktop/main.js:23` genera `APP_BOOT_ID` e lo mette nell'env di ogni
runner; il watchdog lancia il figlio senza `env=` (`watchdog.py:231`) → un crash porta lo
stesso id. Modulo condiviso `Betfair/stream/avvio_app.py` (`Guardia`, `ferma_al_nuovo_avvio`,
`timbra`); l'id vive in `stats` JSONB → **nessuna migrazione**. Coperti: Mike, Omega
(via `set_control`, mai `omega_activate`), Safe (`strategy_modes_a_paper` tocca solo quella
chiave), bot tennis per evento, sessioni scalper. Le RPC `*_activate`/`*_stop` non toccano
`stats`: l'impronta sopravvive a un'accensione dell'utente (verificato nelle migrazioni).
Fasi di protezione a bot fermo verificate per i tre servizi con `file:riga`.
Verifica del coordinatore: 54 test nuovi verdi; suite completa **3426 verdi**; falsificazione
propria (`stesso_avvio` reso vero a id vuoto) → 5 rossi; `tsc` 13 (invariato; il delegato
aveva dichiarato 0 perché lanciato senza `-p tsconfig.app.json`); `dist` più recente dei
sorgenti. **Non esercitato**: la propagazione reale Electron→watchdog→servizio (serve un
avvio dell'app da parte dell'utente: al primo avvio Mike passerà da `running/live` a
`stopped/paper` con l'attività `avvio_app_bot_fermato` visibile in Control Room).
Reperti lasciati all'utente: le Missioni Omega ripartono da sole ma non piazzano mai
(ordini solo da clic); il supervisore scalper non è sotto watchdog; una riga tennis armata
prima del primo battito del runner viene disarmata da un riavvio del runner (fail-closed).

### Esito C.8 (16/09, `PROGETTO_PAPER_VIA_FLUMINE_2026-09-16.md`, verificato dal coordinatore)

**Architettura scelta: C3.** Lo scanner resta l'unico che parla con Betfair (pool
shardato; si aggiungono i campi `EX_TRADED` + `EX_ALL_OFFERS` ladder 3-5: più byte, zero
connessioni); il pool ritrasmette lo stream **grezzo** (stesso formato di
`_live_raw/*.raw.jsonl`) sul canale locale già esistente (`local_channel.py`, 47331/2);
il runner flumine lo consuma con un driver da socket gemello di `HistoricalStream`
(`flumine/streams/historicalstream.py:257-272`), così **produzione paper e replay
condividono il driver, non solo il motore**. Copertura ~720 mercati, 0 processi nuovi,
0 connessioni nuove, ~0 letture DB, <5 ms di latenza aggiunta, volume misurato
~161 msg/s e ~40 KB/s. A retrocede a prerequisito (F0: `mode` per riga invece di
`LIVE_ORDER_MODE` per processo; `_fail_cross_mode` non deve più uccidere l'altra
modalità); C2 resta opzionale. Punto di innesto del relay: `safe_strategy/stream.py:109-112`.
Gate: «coperto dal pool» (`stream.py:308 covered_ids`) al posto di `live_follow=STREAMING`.

Due requisiti non negoziabili del relay: (a) consegna garantita del raw (oggi `publish`
scarta oltre `_MAX_INVII_IN_VOLO=64`, `local_channel.py:37,183`: un delta perso corrompe
il book per sempre → o coda senza scarto o disconnessione + nuova immagine); (b) chi si
collega a metà stream riceve un'immagine iniziale per mercato (cache della `SUB_IMAGE`).

Correzione al replay: flumine ha già l'orologio virtuale (`simulation/simulation.py:35,110`,
`SimulatedDateTime`), quindi il bet delay nel replay manca solo perché
`banco_comune._esegui_subito` lo salta: requisito girato al delegato C.0 (F6 = 1 giorno).

Un solo processo runner basta (flumine ammette più client, `baseflumine.py:85`,
`market.place_order(client=...)`), ma la separazione paper/live dentro lo stesso processo
va **dimostrata da un test**: una riga `paper` non può mai raggiungere il client reale, e
il client reale non esiste se il processo non è in LIVE.

Decisioni operative prese dal coordinatore (implementative, non di strategia, reversibili;
l'utente può ribaltarle): ripiego sul fill a snapshot **vietato** (ordine `no_fill` con
motivo); discontinuità datata negli storici Omega per il bet delay; in Mike resta solo il
ritardo di flumine (mai sommato a quello in casa); scalper e bot tennis restano dove sono,
senza FOK (aggiungerlo sarebbe alterare la strategia); un solo processo runner con `mode`
per riga e test di separazione.

### Esito C.8 F0 — CERTIFICATO dal coordinatore (16/09)

Il runner serve righe `paper` e `live` nello stesso processo, instradate dal `mode`
**della riga** (`live_order_worker.py` `_servable_modes:133`, `_client_for_mode:174`
fail-closed, `_assert_order_mode:215` mai cross-mode su cancel/replace, `_dispatch:3096`
unico punto di instradamento); `_fail_cross_mode` inerte. Nel runner LIVE un
`PaperCompanionClient` (`runner.py:1468`, `paper_trade=True`, login/logout/keep_alive
no-op, username `#paper`: zero chiamate Betfair in più) affianca il client reale; il
client reale **non esiste** se il processo non è LIVE. Una `LiveTradingStrategy` per
modalità (blotter separati). Gate `_hb_serve` (`omega_service.py:1679`): heartbeat
`'LIVE'` vecchio → paper chiuso; `'LIVE+PAPER'` → entrambi. Verifica del coordinatore:
16 test nuovi + worker verdi; falsificazione propria (`_is_paper_client` sempre vero →
una riga paper finirebbe sul client reale) → 4 rossi. Suite completa col diff F0
nell'albero: **3453 verdi, 2 rossi**, entrambi i test dello stake Safe in riscrittura dal
delegato B-1 (`test_lo_stake_delle_strategie_e_fra_i_valori_effettivi`,
`test_merge_params_stake_default_e_override`); il resto della suite è isolato.
**Da chiudere nelle fasi seguenti**: (F1) heartbeat a più righe o colonna `modes` —
oggi `'LIVE+PAPER'` è codificato nel TEXT `mode` (migrazione da scrivere, lettori
`omega_db.runner_heartbeat:386`, `bot_db:681`, `mike/db:541`, `safeBot.ts:1736`);
badge `safeBot.ts:1802` e `set_hello(mode=…)` `runner.py:1525` ancora a modalità
singola; i worker `risk_engine`/`daily_stop`/`reconcile`/`xhedge` ricevono solo la
strategy della modalità del processo (gli ordini paper in un runner LIVE restano fuori:
invariato rispetto a oggi, da chiudere in F2/F4); copertura ancora ~180 mercati fino a F1.

### Esito E.1 (16/09, `AUDIT_TEST_2026-09-16.md`, mutazioni ripristinate: verificato dal coordinatore sui tre file)

- Nessun finto infedele né test che asserisca il comportamento sbagliato nel perimetro
  (pre-16/09); un solo test a vuoto: `mike/tests/test_mike_service.py:217-221`
  (`keeps_protections` a bot fermo senza posizione esposta nel fixture).
- **Mutazioni non catturate da nessun test (3 su 6)**: `safe_strategy/execution.py:287`
  (bordo `size == avail` del cap di liquidità); `omega/omega_service.py:1620`
  (`not res.ok` tolto dal cancello di `_place_one`: 0 rossi su 614); `lib/controlRoom.ts:804`
  (paper sommato nel netto live in `totaliGiornata`: 0 rossi su 71). Catturate: grafia
  camelCase in Mike (10 rossi), `cambiaImporto` a params vuoti (1), `modoDi` invertito (2).
- **Strutturale**: in Safe e Omega nessun finto isola `ok` da `size_matched` (lo stesso
  buco di Mike pre-15/09, in due bot su tre).
- **Reperto grave**: `migrations/omega_daily_v2.sql:75` `omega_activate` fa ancora
  `coalesce(p_params,'{}')` → azzera i cap se chiamata senza params; regge solo perché il
  frontend li passa sempre. → migrazione `omega_activate_conserva_params_2026-09-16.sql`
  da scrivere (B-1) + test di contratto sulle RPC `*_activate`.
- `lib/eventGroups.ts:83` raggruppa su id nudo, mai simulata una collisione fra bot.
- Safe non ha avuto la lettura riga per riga (sotto-agente fuori mandato): guardia combo
  L4 e congelamento `pre_ko` da riverificare a file stabili; `comandiBot` da ricertificare
  dopo B-1. **E.2 (da fare dopo B-1)**: i tre test mancanti sopra, il fixture di Mike,
  la collisione in `eventGroups`, i finti `ok`/`size_matched` di Safe e Omega.

### Esito C.9 (16/09, referto `FASE_C9_BACKTEST_SCALPER_TENNIS_2026-09-16.md`, verificato a campione dal coordinatore)

| bot | backtest esistente | usa il codice di produzione? |
|---|---|---|
| scalper (maker) | `scalper/run_scalper.py` | **sì**, stessa classe `ScalperStrategy` |
| theta | `scalper/run_theta.py` | **sì** |
| **sniper** | **nessun backtest flumine**: `tools/atlas_v0.py` è una reimplementazione a mano (fill a mano, delay cablato 5120 ms) che non esegue la classe attuale | **no → va costruito** sul banco flumine |
| tennis_scalper, tennis_flb | `backtest_pro.py`, `flb_backtest.py` | **sì** |
| tennis_pro | `backtest_pro.py` (sottoclasse che inietta solo il punteggio) | sì, di fatto |
| tennis_swing | `validate.py` con gate di liquidità **aperto** rispetto ai default di produzione | stessa classe, **configurazione diversa** → il numero non vale |
| `scalper_lab/*`, `TennisLabStrategy` (`validate.py` colonne P/S, `lab_grid*`) | copie di ricerca | **non certificano niente** |

Fatti trasversali: i tetti di flumine sono aperti in tutti i backtest (giusto per
certificare i tetti del bot, ma i tetti di flumine impostati in produzione dallo stake
**non vengono esercitati**: da coprire con uno scenario); `order.status` confrontato
sempre come Enum; nessuno dei 7 bot usa FOK; punteggi calcio da `live_now`, non da
`safe_strategy_scan` (fonte diversa da Omega/Safe/Mike: da riconciliare nel banco);
nessuna attività su questi harness dopo il 17/07; 2 eventi della certificazione
`min_size=300` dello scalper riclassificati PARTIAL e mai ricertificati.
**Lavoro che ne esce (C.9)**: sniper sul banco flumine da zero; swing rieseguito con i
default di produzione; scalper/theta/tennis rieseguiti sulle registrazioni attuali
(calcio fino al 14/09) con i controlli di condotta; le copie di ricerca dichiarate
fuori perimetro.
