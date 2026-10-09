# SAFE STRATEGY — Dossier di validazione

> Documento di riferimento per validare OGNI singolo punto nelle prossime sessioni.
> Costruito il 02/09/2026 (sessione di certificazione con l'utente).
> AUDIT 09/09/2026: regola MINUTO = SOGLIA (sez. 2bis), fix video/stats (sez. 5),
> scanner su giornate piene (sez. 3). Dettaglio dei fix in sez. 9.
> AUDIT 09/09 pomeriggio: LIMITI BETFAIR + pool stream (sez. 3bis), media flags (sez. 5),
> importo abbinabile nei segnali (sez. 4bis), pubblicazione immediata cambi critici. Sez. 10.
> Convenzione: ✅ = validato · 🔎 = da validare dal vivo · ⬜ = non ancora toccato.
> NB: come gli altri dossier di root, questo file resta LOCALE (non pushato).

---

## 1. Architettura (com'è fatta)

```
Betfair/safe_strategy/  (servizio autonomo, lock 127.0.0.1:47315, spawnato da desktop/main.js)
 ├─ service.py   glue: cataloghi, pool stream, thread punteggi, pubblicazione, heartbeat, pulizia orfane
 ├─ stream.py    Exchange Stream API ufficiale: POOL sharded (≤180 mercati/conn, max 4→10), conflate 1s, backoff
 ├─ scanner.py   logica PURA (soglie, rilevanza mercati, pre-KO, firme, size, media) — 23 pytest
 └─ db.py        upsert service_role su safe_strategy_scan / safe_strategy_status

migrations/safe_strategy_scan.sql   (APPLICATA il 02/09)

frontend/
 ├─ lib/safeStrategy.ts        MOTORE CERTIFICATO (valutatori 4 strategie) — 71 vitest
 ├─ lib/safeStrategyScan.ts    data-layer tabelle scanner (1 canale realtime)
 ├─ components/safestrategy/   Provider (coalescing 400ms) · SignalCard · MonitorCard · ParamsSheet
 ├─ components/BetfairMediaButtons.tsx  pulsante unico [📺 Video | 📊 Stats]
 └─ pages/SafeStrategy.tsx     pagina: barra scanner + sezioni Calcio/Tennis
```

**Flusso dati**: pool stream Betfair (quote push 1s, ≤180 mercati/connessione) + IPS
scoresAndBroadcast in thread dedicato (2s, lotti da 50: punteggi/minuti/rossi/set/game/punti +
disponibilità video) + timeline calcio (30s) + Correct Score REST (15s, solo candidati)
→ `safe_strategy_scan` (write-on-change; cambi critici SUBITO, sole quote throttle 2.5s/evento)
→ Supabase Realtime → motore TS certificato → segnali + toast. La stessa tabella è il FEED UNICO
di punteggi/quote per runner calcio, runner tennis e board (sez. 12).
**Principio cardine**: lo scanner raccoglie FATTI; la VALUTAZIONE vive solo nel motore
frontend certificato. Dati mancanti = `n/d`, MAI inventati.

---

## 2. Le 4 strategie (logica certificata a tavolino il 02/09)

### 2bis ⭐ REGOLA MINUTO = SOGLIA (utente, 09/09) — vale per Base, R.E. Casa/Ospite, Punta
Il minuto NON è un intervallo chiuso ma una SOGLIA: "48–50′" significava "dal 48′ in
poi". Col range fisso quasi nessun segnale sarebbe passato (al 51′ il R.E. si spegneva).
Ora `minuteCheck` = `minuto ≥ soglia` ("Dal minuto 48′ in poi"), il parametro "minuto
max" è stato RIMOSSO ovunque (motore, pannello, localStorage legacy ignorato). Il tetto
della finestra lo mettono i RANGE QUOTE (favorita live 1.20–1.34, "Altro risultato"
30–70, back 1.03–1.10): quando la partita avanza le quote escono dal range da sole.
Lo scanner backend segue la stessa regola: Correct Score interrogato dal 40′ fino al
fischio finale (prima 40–60′), cadenza "calda" dal 40′ in poi (prima 40–78′).
- [x] ✅ 75 vitest (soglia 54′→NO, 55/70/89′→SEGNALE; R.E. 47′→NO, 48/65/80′→SEGNALE con
      tetto dato dalla quota; Punta 65′→NO, 66/85′→SEGNALE) · 12 pytest scanner.

### 2.1 ✅ Calcio · BASE (lay di chi perde, mercato 1X2)
Condizioni (parametri editabili, default tra parentesi):
- [ ] 🔎 in-play + minuto EFFETTIVO DAL 55′ IN POI (soglia, sez. 2bis; timeElapsed IPS: intervallo escluso — verificato nel codice, da confermare su un match vero)
- [ ] 🔎 favorita in vantaggio con punteggio orientato (1-0 · 2-1 · 2-0) — vale anche in trasferta (0-1 ecc.), test dedicati
- [ ] 🔎 favorita pre-match 1.40–1.80 e sfavorita 4–8 (dal riferimento PRE-KO congelato)
- [ ] 🔎 quota LIVE favorita 1.20–1.34 ⚠️ INTERPRETAZIONE dichiarata: il range è sulla favorita, l'azione è lay della sfavorita (fonte ambigua)
- [ ] 🔎 mercato Match Odds APERTO (post-gol sospeso = segnale bloccato, si riattiva senza doppio toast)
- [ ] 🔎 punteggio stabile ≥30s (anti-blip IPS)
- [ ] 🔎 nessun ROSSO alla favorita (solo quando il dato cartellini c'è)
- [ ] 🔎 quota lay sfavorita DISPONIBILE (senza prezzo bancabile → n/d)

### 2.2 ✅ Calcio · RISULTATO ESATTO (lay "Any Other Home/Away")
- [ ] 🔎 minuto DAL 48′ IN POI (soglia, sez. 2bis) · punteggio in QUALSIASI ordine (0-0 · 1-0 · 1-1 · 2-1)
- [ ] 🔎 lato bancato con max 1 gol (a 0-0/1-1 possono scattare ENTRAMBI i lati)
- [ ] 🔎 quota LAY "Altro risultato" 30–70 — mai il back come sostituto (fix review HIGH)
- [ ] 🔎 mercato CS aperto · anti-blip ≥30s
- [ ] 🔎 lo scanner interroga il CS solo per i candidati (dal 40′ in poi, ≤2 gol/lato); catalogo CS entro ~20s dal primo candidato nuovo (prima fino a 10 minuti di ritardo)

### 2.3 ✅ Calcio · VARIANTE PUNTA (back di chi vince di 2)
- [ ] 🔎 minuto DAL 66′ IN POI (soglia, sez. 2bis) · punteggio orientato (2-0 · 3-1 · 3-0, vale in trasferta)
- [ ] 🔎 in vantaggio c'è la FAVORITA pre-KO · quota back 1.03–1.10
- [ ] 🔎 assestamento ≥3′ dall'ultimo gol OSSERVATO (timer conservativo: parte dall'osservazione)
- [ ] 🔎 mercato aperto · nessun rosso a CHI SI PUNTA

### 2.4 ✅ Tennis (back del leader)
- [ ] 🔎 in-play · singolare (no "/" nei nomi) · vantaggio ≥1 set
- [ ] 🔎 ≥2 game di vantaggio nel set corrente DELLO STESSO leader dei set (tie-break escluso per costruzione)
- [ ] 🔎 quota BACK del leader 1.01–1.10 — FIX certificazione: il vecchio range lay 1.18–1.34
      sul perdente era matematicamente impossibile (perdente ~15–40); il lay del perdente
      al prezzo reale è mostrato come alternativa informativa
- [ ] 🔎 anti-blip ≥15s · mercato aperto
- [ ] 🔎 filtro competizioni escluse (default VUOTO: il nome torneo non distingue tabellone M/F)
- [ ] 🔎 un segnale per SET (chiave = punteggio set), niente spam a ogni game

### Regole trasversali del motore
- [ ] 🔎 stati: SEGNALE (tutte vere) / N-D (dato mancante, mai falso positivo) / NO (almeno una falsa)
- [x] ✅ 09/09 ri-valutazione ogni 5s nel provider: i check "stabile da ≥N s" maturano anche se lo
      scanner non riscrive la riga (write-on-change a mercato fermo: prima il contatore restava congelato)
- [ ] 🔎 segnale scaduto → storico sessione; stessa situazione tornata valida → riattivazione SENZA nuovo toast
- [ ] 🔎 nuovo gol/set = nuova situazione = nuova valutazione (chiave evento+strategia+punteggio)
- [ ] 🔎 toast cliccabile → /safe-strategy solo da altre schermate

---

## 3. Scanner autonomo (collaudato dal vivo 02/09 sera)

- [x] ✅ Catalogo MO giornaliero per sport (300s), COMPETITION + sort_priority (home/away/draw affidabili)
- [x] ✅ STREAM ufficiale: 1 connessione, 114 mercati sottoscritti (70⚽+44🎾), conflate 1s, `source=stream`
- [x] ✅ Warm-up di ENTRAMBI i cataloghi prima della subscription (bug trovato e fixato in collaudo:
      partiva solo calcio e il tennis restava fuori minuti)
- [x] ✅ Fallback REST automatico se lo stream non è in salute (cadenze adattive 10/20/60s)
- [x] ✅ Punteggi IPS batch (dal 09/09 sera: thread dedicato, 2s, chunk 50) — parser certificati dei runner (minuti, gol, rossi; tennis set/game/punti)
- [x] ✅ Pre-KO: cattura da KO−15′, CONGELATO al primo tick in-play (mai quote live nel riferimento)
- [x] ✅ Write-on-change + throttle 2.5s/evento; delete righe a evento finito; heartbeat 10s
- [x] ✅ Degrado pulito senza migrazione (warning, mai crash)
- [x] ✅ E2E scritture/riletture: 64–69 righe reali, blocco CS con quote vere, heartbeat con contatori
- [x] ✅ 09/09 giornate PIENE: catalogo su finestra MOBILE (KO −6h…+14h, fino a 400 mercati/sport —
      il vecchio cap 120 + "fino a mezzanotte UTC" tagliava gli eventi serali/notturni); quote SOLO
      sui mercati RILEVANTI (in-play o KO entro 20′) → stream cap 180 con priorità in-play, e poll
      REST di fallback per i rilevanti che lo stream NON copre (prima: mercati fuori dal cap = zero quote,
      zero pre-KO, invisibili). Set stream ricalcolato a ogni tick (non solo al refresh catalogo);
      resubscribe in sospeso applicato allo scadere del throttle 60s. Badge ⚡STREAM mostra i mercati coperti.
      Collaudo 09/09 10:31: 83⚽+105🎾 a catalogo, 22 rilevanti, 16 righe, 0 errori.
- [ ] 🔎 weekend reale con >180 mercati rilevanti: verificare badge STREAM n + REST che copre il resto
- [ ] 🔎 Riconnessione stream dopo caduta rete reale · resubscribe a metà giornata con eventi nuovi
- [ ] 🔎 Pre-KO visto NASCERE dal vivo (partita seguita da pre-KO a in-play con riferimento congelato)

## 3bis ⭐ LIMITI BETFAIR E POOL STREAM (09/09 pomeriggio) — fonte: docs + risposte BDP sul forum ufficiale
Limiti accertati: **200 mercati per connessione stream** (default; il BDP può alzarlo a 1000 su
richiesta via email), **fino a 10 connessioni per app key**, `SUBSCRIPTION_LIMIT_EXCEEDED` se si
sfora, i mercati CLOSED vengono esclusi dal conteggio al re-subscribe (job Betfair ogni 5', eviction
dopo 1h). REST: peso ≤200 punti/richiesta (EX_BEST_OFFERS=5 → noi 25 mercati/chiamata = 125).
Come fanno i concorrenti (Bet Angel/BFExplorer): catalogo via REST, stream **per marketIds SOLO sui
mercati monitorati**, **più connessioni** quando si supera il limite ("I have 6 on the go 24/7").
Implementato in `stream.py` (`MarketStreamPool`):
- [x] ✅ sharding STABILE per market_id (hash mod N): un evento nuovo ricrea la subscription di UNO shard
- [x] ✅ N = ceil(mercati/180), default max 4 connessioni (capacità 720), hard cap 10; env
      `SAFE_STRATEGY_STREAM_CONNS` / `SAFE_STRATEGY_STREAM_MARKETS_PER_CONN` (>200 solo se il BDP ha alzato il limite)
- [x] ✅ salute per shard sul socket (heartbeat 5s): mercato fermo ≠ shard morto; i rilevanti non coperti
      da shard vivi vanno al REST di fallback
- [x] ✅ heartbeat espone `stream_markets` / `stream_connections` / `stream_capacity` (tooltip badge ⚡STREAM)
- [x] ✅ 6 pytest sharding · dry-run dal vivo 11:22: stream#0 32 mercati, 1 connessione, source stream, 0 errori
- [ ] 🔎 weekend con >180 rilevanti: vedere 2+ connessioni nel tooltip e nessun SUBSCRIPTION_LIMIT_EXCEEDED nel log

## 4. UI Safe Strategy

- [x] ✅ Card nel selettore + link su Board · route /safe-strategy · provider globale
- [ ] 🔎 Barra scanner: verde/rosso, "ultimo giro Xs fa", contatori ⚽/🎾, badge ⚡STREAM/REST, errori
- [ ] 🔎 Sezioni divise per sport; segnali attivi grandi; MonitorCard con chip 4 strategie + checklist espandibile
- [ ] 🔎 Note diagnostiche ("pre-KO non catturato…") · storico sessione · pannello Parametri (salva/valida/reset)
- [ ] 🔎 Prestazioni con tante schede aperte (coalescing 400ms, 1 canale realtime)

## 4bis ⭐ IMPORTO ABBINABILE SUBITO (09/09 pomeriggio)
Ogni segnale mostra "Abbinabile subito €X": la SIZE al miglior prezzo sul lato da operare
(stream EX_BEST_OFFERS livello 0, `back_size`/`lay_size` su ogni quota, anche Correct Score).
LAY → X = puntata da bancare (denaro in attesa) + responsabilità X×(quota−1); BACK → X = puntata.
Aggiornata live con la quota (reconcileSignals), anche nel toast e nella checklist
("8.40 · €120 abbinabili"). Fonte senza size → "n/d", mai inventata.
- [x] ✅ 7 vitest dedicati (Base/R.E./Punta/Tennis, legacy null, quota assente → size assente)
- [x] ✅ verificato dal vivo in-process: 1X2 `lay_size 88.18`, CS `back_size 15.87`, tennis `back_size 16.87`

## 5. Video + Statistiche (popup ufficiale Betfair)

- [x] ✅ Pulsante unico [📺 Video | 📊 Stats] in 9 sezioni (Safe Strategy, Omega, Segui Live,
      Tennis Terminal, Multi-Ladder, Market Watch, Board, Tennis Dashboard, Ladder Popout)
- [x] ✅ URL popup ufficiale: /exchange/plus/pop-out-live-stream/<eventId>?feedType=dataVisualization (verificato dall'utente su Udinese–Venezia)
- [x] ✅ 09/09 FIX feedType: i valori validi nel bundle ufficiale Betfair (LiveStreamMod.CONFIG.tabs)
      sono `liveVideo` · `dataVisualization` · `matchStats`. Noi mandavamo `video` (inesistente):
      il popout ripiegava sulla PRIMA tab disponibile → "Video" apriva il video se c'era, altrimenti
      l'animazione, senza dirlo. Ora 📺 = liveVideo, 📊 = matchStats (le altre tab restano a un click).
- [x] ✅ 09/09 finestre gestite dal main process Electron (setWindowOpenHandler): UNA finestra per
      evento+feed (secondo click = torna davanti, prima 10 click = 10 finestre), 640×780 senza menu,
      apertura solo a SSO pronto (max 8s di attesa al primo click dopo l'avvio), link esterni al browser
      di sistema, rotte UI (ladder popout) intatte. Nel browser: avviso se il popup è bloccato.
- [x] ✅ 09/09 SSO: retry con backoff 30→60→120→300s se il login fallisce all'avvio (prima il tentativo
      successivo arrivava col keep-alive dopo 15 minuti).
- [x] ✅ 09/09 E2E Electron (script collaudo, stesso SSO di main.js) su evento in-play 36049025:
      login interattivo SUCCESS (~400ms), popout aperto GIÀ LOGGATO (nessun "You need to be logged in"),
      feedType=matchStats atterra sulla tab "Statistiche partita", iframe videoplayer.betfair.it caricato.
      L'evento non aveva diritti video → tab video assente e liveVideo ripiega sulla visualizzazione (comportamento Betfair).
      Al primo avvio compare il banner cookie Betfair (una tantum: la sessione Electron persiste).
- [x] ✅ 09/09 pom. DISPONIBILITÀ MEDIA PER EVENTO: lo scanner usa l'IPS `scoresAndBroadcast` (stesso
      endpoint del sito, funziona con la nostra app key, punteggi + `isLiveVideoAvailable` /
      `isDataVisualizationAvailable` in UNA chiamata al posto di get_scores, fallback get_scores) →
      payload `media:{video,viz}` → pulsanti 📺/📊 attenuati col motivo quando Betfair NON offre
      video/animazione per quell'evento. Esattamente la logica delle icone del sito.
- [x] ✅ 09/09 pom. DIAGNOSI popout nero (Viktoriya Sumy v Metal Kharkiv): Betfair dichiara
      `video:false, viz:false` per l'evento; dentro l'iframe videoplayer il caricatore Sportradar
      (`widgets.sir.sportradar.com/.../widgetloader`) risponde 404 a QUALSIASI client (verificato
      con referer betfair.it, videoplayer.betfair.it e senza). Il nero è di Betfair, non dell'app:
      lo stesso popup sul sito mostra lo stesso vuoto. Il popout resta quello ufficiale con tutte le tab.
- [ ] 🔎 feedType=liveVideo su un match CON diritti video (tab "Live Video" presente) — ora individuabile
      dal pulsante 📺 non attenuato (media.video=true)
- [x] ✅ SSO all'avvio: login INTERATTIVO identitysso (token web pieno, video incluso) + fallback certlogin,
      cookie ssoid su .it/.com, keep-alive 15′, re-login automatico — verificato SUCCESS dal vivo
- [ ] 🔎 Zero login manuale sul VIDEO dopo il riavvio dell'exe (era "You need to be logged in" col solo certlogin)

## 6. Punti aperti / estensioni future (non bloccanti)

- ⬜ Statistiche native nelle card (possesso/tiri) → servirebbe provider terzo a pagamento (OPTA non ha API)
- ⬜ event_id Betfair su Dashboard calcio/Watchlist (serve RPC backend) per i pulsanti media anche lì
- ⬜ size minima sul lay "Any Other" (liquidità) come condizione della strategia 2
- ⬜ eventuale backtest delle 4 strategie sulle registrazioni (l'utente ha scelto per ora solo segnalazione)

## 9. Audit 09/09/2026 — cosa è stato trovato e cambiato

| # | Problema | Dove | Fix |
|---|---|---|---|
| 1 | Minuto trattato come intervallo chiuso (48–50′): quasi nessun segnale passava | `lib/safeStrategy.ts` minuteCheck, ParamsSheet, test | soglia `≥ minuto`, "minuto max" rimosso ovunque, 75 vitest |
| 2 | Scanner: CS solo 40–60′, cadenza calda solo 40–78′ (incoerente con la soglia) | `scanner.py`, `service.py` | finestre aperte verso il fischio finale, 12 pytest |
| 3 | Catalogo CS ogni 600s → quota "Altro risultato" fino a 10′ in ritardo | `service.py` | refresh appena c'è un candidato senza mercato (throttle 20s) |
| 4 | Cap catalogo 120 + finestra "fino a mezzanotte UTC": eventi serali/notturni fuori radar | `service.py` | finestra mobile −6h/+14h, 400 mercati/sport (peso 0) |
| 5 | Stream cap 180 su TUTTO il catalogo: mercati oltre il cap senza quote né pre-KO (REST non scattava se lo stream era "healthy") | `service.py`, `stream.py` | quote solo sui RILEVANTI; REST per i rilevanti non coperti; set stream ricalcolato a ogni tick |
| 6 | Resubscribe stream in sospeso perso se arrivato durante il throttle | `stream.py` | `maybe_resubscribe()` a ogni drain |
| 7 | `feedType=video` inesistente: pulsante Video apriva a caso | `lib/betfairMedia.ts` | `liveVideo` / `matchStats` dal bundle ufficiale |
| 8 | Finestre Betfair non gestite: duplicati a ogni click, aperte prima dell'SSO | `desktop/main.js` | handler main process, finestra per nome, attesa SSO |
| 9 | Login SSO fallito all'avvio → retry solo dopo 15′ | `desktop/main.js` | backoff 30→300s |
| 10 | Check temporali congelati senza update dello scanner | `SafeStrategyProvider.tsx` | tick di ri-valutazione 5s |

## 10. Audit 09/09 pomeriggio — punti 1-4 dell'utente

| # | Richiesta | Fatto | Dove |
|---|---|---|---|
| 1 | Limiti Betfair + stream su OGNI evento anche nei weekend | pool multi-connessione con sharding stabile, cap 180/conn, REST fallback per i non coperti | `stream.py`, `service.py` |
| 2 | Video/stats esattamente come il popup del sito | feedType ufficiali, disponibilità media per evento (IPS), diagnosi nero = Sportradar 404 lato Betfair | `betfairMedia.ts`, `BetfairMediaButtons.tsx`, `service.py` |
| 3 | Dati sempre allineati alla realtà | cambi CRITICI (gol, minuto, rossi, in-play, stato mercato, set/game) pubblicati SUBITO fuori throttle; ri-valutazione 5s; stato assente dall'IPS non sovrascrive il punteggio | `scanner.critical_signature`, `service.build_rows`, provider |
| 4 | Importo massimo eseguibile a quella quota | `entrySize` su ogni segnale (size best offer lato operativo) + responsabilità per il LAY | motore, SignalCard, toast |

## 11. App desktop: exe = avviatore, main.js sempre vivo (09/09)
Sintomo: "Scanner non attivo — heartbeat 575530s fa" nell'exe. Causa: l'exe del 17/07 aveva
DENTRO un main.js di quella data (electron-builder impacchetta main.js): niente spawn dello
scanner (02/09), niente SSO video, niente gestione finestre. Fix: `desktop/bootstrap.js` è la
nuova entry dell'exe (1.1.0) e fa require() del `desktop/main.js` del repo → ogni modifica a
main.js è attiva al riavvio, senza ricompilare. Ricompilare solo se cambiano bootstrap.js,
package.json o Electron. Lanciare `desktop/release/AlphaScore Trading 1.1.0.exe`.
- [ ] 🔎 primo avvio 1.1.0: nel log `[bootstrap] main.js VIVO dal repo`, barra "Scanner attivo" entro ~30s,
      pulsanti 📺/📊 con attenuazione, SSO OK.

## 12. Ottimizzazione processi e riuso dei dati (09/09 sera) — "come Bet Angel"
Principio: lo scanner Safe Strategy è il FEED UNICO (stream pool + IPS batch); tutti gli altri
processi LEGGONO da lui e chiamano Betfair solo come fallback o per ciò che è davvero loro.

| Sovrapposizione trovata | Prima | Dopo |
|---|---|---|
| Punteggi IPS calcio | runner: 1 get_scores + 1 timeline per evento ogni 5s | `scores/scan_feed.py`: SELECT unica su `safe_strategy_scan` (score_raw = stato IPS grezzo, stesso parser), timeline in batch dallo scanner ogni 30s; IPS diretto solo se riga assente/stantia (>15s) |
| Punteggi IPS tennis | tennis runner: 1 get_scores per evento ogni 2s | stesso feed (scanner a 3s, cambi di punto pubblicati subito); fallback diretto |
| Quote board desktop | 3 listMarketBook ogni 10s per sport (36/min) | prezzi dal feed (selection_id/ltp/size/volume nel payload); REST solo per i mercati non coperti, ogni 60s |
| Connessioni stream tennis | UNA PER MATCH seguito (5 match = 5 conn) | UNA capture con tutti i mercati; bot con lo stesso filtro e SCOPATI sul proprio mercato (`_scope_to_market`) |
| Cap mercati runner calcio | 400 su una connessione (2× il limite Betfair) | 180 (allerta 150); `LIVE_MARKET_TYPES` opzionale per seguire più partite |
| Sessioni/login | re-login JSON-RPC ogni 8' idle; habitat scan = login nuovo ogni 30'; 48 login/giorno job tennis | eliminati i primi due (client condiviso); job tennis con lock singola istanza 47316 + main.js non sovrappone run |
| Supabase risk engine | ~96.000 richieste/ora a vuoto (0.15s × 4 query) | settings/follow-through a 1s, esito "nessuna regola" valido 1s; con regole armate lettura per tick invariata |
| Saldo conto | getAccountFunds ogni 5s anche in PAPER | 60s PAPER / 20s LIVE |
| Runner morti in silenzio | calcio: exit 0 a 18h → watchdog fermo; tennis: idle-exit + corsa al lock con tennis_bot_service | exit 75 = riavvio PIANIFICATO (watchdog rilancia subito, `classify_exit`=planned); lifecycle tennis con keep-alive; tennis_bot_service `--bridge-only` (solo ponte, nessun hosting) |
| Sessione HTTP | connessione TLS nuova a ogni chiamata (bflw senza Session) | `requests.Session` in build_client per tutti i 16 processi |

Connessioni stream a regime (limite 10/app key): runner calcio 1 + tennis 1 + scanner ceil(n/180) (1-2) + 1 per sessione scalper attiva → 3-5 nel caso ordinario, 6-7 nel peggiore.
- [x] ✅ 1.552 pytest verdi (16 nuovi: scan_feed, board dal feed, stream unico tennis + scoping, watchdog planned, scanner raw/critical)
- [x] ✅ payload scanner dal vivo: selection_id/ltp/size/volume, score_raw senza campi al secondo, timeline (5 eventi)
- [ ] 🔎 primo weekend: nel log dei runner NESSUN `get_scores` diretto a regime (solo pre-match/scanner giù); tooltip STREAM con 1-2 connessioni scanner
- [ ] 🔎 tennis con 2+ match seguiti: "stream avviato: N eventi, 1 connessione Betfair"

## 13. Punteggi: precisione e latenza (09/09 sera, segnalazione "tennis lento")
Fonte = IPS Betfair `scoresAndBroadcast` (la stessa del sito). Catena: thread punteggi dello
scanner (2s, lotti da 50, ~70ms/chiamata, separato dal tick) → cambio di stato grezzo = pubblicazione
IMMEDIATA (critical, mai in coda al throttle quote) → Supabase Realtime → UI (Safe Strategy legge le
righe direttamente; il runner tennis le legge ogni 2s per tennis_live_now/terminal). Latenza attesa
punto→UI: 2-3s. Prima: giro serializzato nel tick (lotti da 20 + 0.35s) a 3s → fino a 6s.
- [x] ✅ heartbeat con updated_at esplicito (era la data del primo insert → "non attivo, 591462s fa")
- [x] ✅ righe orfane ripulite all'avvio e ogni 5' (123→34 righe)
- [ ] 🔎 orologio Windows sfasato di ~2.5s (w32tm): `w32tm /resync` da PowerShell AMMINISTRATORE — non lo può fare l'app
- [ ] 🔎 confronto dal vivo punto per punto con la scoreboard del sito su un match tennis

## 14. Omega in tempo reale sul feed unico (09/09 sera)

**Richiesta:** Omega (Correct Score calcio) deve avere punteggi e quote realtime come
Safe Strategy, riusando tutto. Poi si ragionerà sulle logiche (martingala del target,
regola di selezione, cap): NON toccate in questa fase.

**Produttore = lo scanner (nessun processo nuovo, nessuna chiamata nuova):**
- `scanner.CS_MINUTE_FROM=30`, `CS_MAX_GOALS_SIDE=3`: i CS dei candidati entrano in
  `relevant_market_ids("calcio")` → vanno sullo **stream** (resubscribe throttle 30s,
  era 60) con fallback REST identico al Match Odds. Sparito `poll_cs_books` (REST 15s).
- `build_cs_block(...)` pubblica `cs.selections` = TUTTE le selezioni con
  `selection_id/name/runner_status/back/lay/back_size/lay_size` + `inplay`,
  `total_matched`. I `any_other_*` restano per la Safe Strategy.
- Collaudo reale 105s (dry, stream): candidati 10→11, CS rilevanti 8→10, **CS su stream
  0 → 9 (t=45s) → 10**, eventi con selezioni 8→10, source=stream, err=None. Esempio
  blocco: 19 selezioni, 13 con lay (`0 - 0` back 4.3/lay 4.7, lay_size 21.47).

**Consumatore = Omega:**
- `omega_service.cs_snapshot_from_payload(event_id, payload)` → `(CorrectScoreMarket,
  MarketSnapshot)`; `score_from_payload(...)` → `LiveScore`. Regole money-critical:
  runner non ACTIVE saltati, mercato CLOSED/senza runner → `None` (settlement solo REST),
  `lay_ladder=((lay, lay_size),)`, id/prezzi/size mai rimappati.
- `_feed_row` usa `shared_cache().rows_for` + `fresh_payload(..., scanner_age_sec)`:
  una SELECT per ciclo; `_cs_from_feed` SOLO con `market is _real_market` (i fake dei
  test non toccano il DB); `_mission_scores` = feed prima, IPS solo per i mancanti;
  `_build_score_lookup` feed-first con `db is _real_db`.
- `scan_and_place` e `_cs_suggestion(CORRECT_SCORE)` provano il feed prima del REST.
- Test `Betfair/omega/test_omega_feed_2026_09_09.py` (6): fedeltà payload, selezione
  identica feed/REST, mai settlement dal feed, fake isolati.

**Frontend (Omega → Missioni):**
- `safeStrategyScan.ts`: tipo `ScanCsSelection` + helper `csSelection(payload, id)`.
- `MissionPanel.tsx`: hook `useMissionLiveFeed(eventIds)` = `fetchScanRows` iniziale +
  `subscribeScanRows` (UN canale, coalesce 400ms, set eventi in ref) → minuto/punteggio
  live in riga (pallino verde = feed attivo) e `live` passato a `MissionCard`.
- `MissionCard.tsx`: `liveLay(market, selection)` dal `cs.selections` del feed →
  quota/size lay live della selezione suggerita; il dialog mostra e CONFERMA la quota
  di quell'istante (`draftPrice`), rischio ricalcolato; con feed presente il solo
  cambio di quota della suggestion non chiude più il dialog (mercato/selezione sì).

**Desktop:** `omega_service` sotto `Betfair.stream.watchdog` come lo scanner.

**Da fare al prossimo avvio dell'app:** l'istanza aperta alle 16:08 gira col codice
precedente (CS senza selezioni, Omega non sotto watchdog): al riavvio dell'exe tutto
parte con il codice nuovo (bootstrap.js → main.js vivo, dist già ricostruita).

## 7. Comandi utili (collaudo)

```bash
# scanner: un ciclo dal vivo senza scritture / con scritture
.venv/Scripts/python.exe -m Betfair.safe_strategy.service --once --dry
.venv/Scripts/python.exe -m Betfair.safe_strategy.service --once
# test
.venv/Scripts/python.exe -m pytest Betfair/safe_strategy/tests/ -q     # 10 pytest
cd frontend && npx vitest run src/lib/safeStrategy.test.ts             # 71 vitest motore
cd frontend && npm test && npm run build                               # suite completa (832) + build
```

## 8. Commit della giornata (tutti pushati su master)

| Commit | Contenuto |
|---|---|
| e7ddb5d | Sezione Safe Strategy + video/stats in 9 sezioni |
| 12b48fc | SSO web Betfair automatico (certlogin) |
| 649f6d9 | Blindatura Base (pre-KO certificato, anti-blip 30s, rosso, lay-only) |
| d6a81bf | Popup ufficiale Betfair (pulsante unico 📺|📊, fix stats rotto) |
| b3447d1 | Blindature Punta (rosso) + R.E. (anti-blip) |
| 7773f5e | Fix tennis (quota ingresso = back leader) + anti-blip 15s + filtro tornei |
| de0fa05 | SCANNER AUTONOMO (servizio + migrazione + provider su tabella scan) |
| e8aeb05 | SSO video: login interattivo prima del certlogin |
| d248a86 | Quote real-time via Exchange Stream API + badge STREAM/REST |
| 24cd0ba | 09/09 AUDIT: minuto = SOGLIA, feedType Betfair corretti (liveVideo/matchStats), finestre Electron gestite + SSO, scanner giornate piene (finestra mobile, mercati rilevanti, REST fallback), CS catalogo 20s, tick 5s provider |
| de98830 | 09/09 pom.: pool stream nei limiti Betfair (sharding ≤180/conn, max 4→10 conn), size abbinabile sui segnali, IPS scoresAndBroadcast (media flags 📺/📊), cambi critici pubblicati subito |
