# PROCESSO STANDARD PER OGNI BOT — presenti e futuri

> Ordine dell'utente, 16 settembre 2026. Vale per Omega, Safe (base, esatto, punta,
> tennis), Mike, scalper calcio (scalper, sniper, theta), i quattro bot tennis
> (scalper, pro, flb, swing) e per **qualunque bot verrà dopo**. Nessun gradino si salta.

> «Si progetta il bot → si mappa ogni cosa e ogni possibile condizione → si valida su
> backtest flumine con dati reali il corretto funzionamento in tutti gli scenari di
> mercato (il bot deve operare come progettato) con la massima fedeltà alla realtà →
> si testa paper → se paper conferma si va live.»

## 1. Si progetta

Una Costituzione o specifica scritta prima del codice: fasi e macchina a stati,
invarianti money-critical, sicurezze, cosa il bot **non** fa, dimensionamento, uscite.
Modelli: `Betfair/mike/COSTITUZIONE_MIKE.md`, `SPEC_STRATEGIA_S.md`.
La strategia, una volta progettata, **non si altera** se non per ordine diretto
dell'utente. L'unica differenza ammessa fra due esecuzioni è paper o live.

## 2. Si mappa ogni cosa e ogni condizione

- **Elenco numerato delle condizioni** che il bot deve rispettare (Mike: 1→75), generato
  da uno strumento, non scritto a mano.
- **Matrice della consapevolezza degli ordini**: per ogni tipo di ordine (ingresso,
  appoggiato, place-and-trim, green-up, copertura, cash-out, chiusura, seconda entrata)
  e per ogni esito (abbinato tutto · parziale subito · appoggiato poi parziale · poi
  intero · mai abbinato e scaduto · annullato dal bot · rifiutato da Betfair · esito
  ignoto · prezzo migliore · mercato annullato) tre colonne: cosa il bot **sa** (campi e
  fonte), cosa **fa** (regola della spec), cosa la **UI mostra**. Mai «abbinato» dedotto
  dal prezzo di mercato senza conferma di Betfair.
- **Scenari di mercato**: sospeso (può riaprire) ≠ chiuso (non si opera più); feed
  stantio; tetto di rischio che stringe; bot fermato con posizione aperta; esiti ignoti.

## 3. Si valida sul replay flumine con dati reali

- Registrazioni vere: calcio `_live_raw/<id>/<id>.raw.jsonl` (+ `.scores.jsonl`),
  tennis `Desktop/tennis_rec/<giorno>/<id>/` (+ `.score.jsonl`). Qualità dichiarata
  (COMPLETE / PARTIAL) con `Betfair/stream/tools/validate_recordings.py`.
- **Codice di produzione, non copie**: scanner vero → riga di scan vera → feed vero del
  bot → servizio vero (`run_once`) → ordine vero su flumine. Nessuno snapshot o fill
  scritto a mano; nessuna classe «lab» o «base» al posto di quella di produzione.
- **Matching di flumine** con la coda vera (`_piq`, volume scambiato) e **bet delay**
  sull'orologio virtuale ancorato al `publish_time`; tetti di flumine aperti (si
  certificano i limiti del bot, non quelli di flumine); `order.status` come Enum.
- **Tutte le logiche esercitate**: scenari che provocano le condizioni rare cambiando
  solo parametri, freschezza del feed o guasti iniettati — mai la partita, mai i prezzi,
  mai la strategia. Il referto conta i controlli **sollecitati** e dice «non lo so» su
  quelli mai sollecitati.
- **Falsificazione**: si reintroduce un difetto noto (i cinque del 15/09 come minimo) e
  il replay **deve** diventare rosso. Un controllo che non sa diventare rosso non
  certifica.
- Verdetti a quattro stati: ✓ osservato · vuoto mai osservato · ⊘ non esercitabile con
  la causa · ⊗ da provocare. Si misura la **condotta**, non il profitto.

## 4. Si testa in paper, che è lo specchio della realtà

- Il paper in produzione usa **lo stesso motore di matching di flumine** del replay
  (client simulato, bet delay, coda, FOK): nessun fill locale, nessun ripiego su uno
  snapshot. Un ordine senza esito è «non abbinato», non un fill.
- Parità **campo per campo** fra la riga che il percorso paper e quella che il percorso
  live manderebbero a Betfair: qualunque campo diverso è un reperto.
- Il paper deve **confermare** il replay: stessa condotta, stessi controlli verdi.

## 5. Si va live

Solo se il paper conferma. Bot per bot, stake piccolo, uscite approvate a mano finché
non c'è un referto forense per operazione (`storia_operazioni.py` come modello),
cinque operazioni prima di dichiarare validato. Paper e live non si sommano mai; i bot
li accende solo l'utente, dalla UI, in paper e in live.

## Regole che attraversano tutti i gradini

- I finti nei test hanno **le identiche chiavi e tipi del vero**, costruiti dalle
  funzioni vere o da payload registrati.
- I test certificano il comportamento di produzione: un test verde che non sa diventare
  rosso si cancella o si riscrive.
- Prima di dire che un percorso non sa fare una cosa, si cerca nel repo chi gliela fa
  già fare. Prima di creare una risorsa (canale, processo, tabella) si cerca quella
  esistente.
- Nessun processo, registratore o runner nuovo senza permesso esplicito dell'utente.
- Chi certifica rilegge il diff, rilancia test e replay di persona e prova la
  falsificazione: non firma sul referto di chi ha costruito.

---

## 6. COPERTURA OBBLIGATORIA DEL BANCO — ogni componente, nessuna esclusa

Il banco di replay (`Betfair/stream/backtest/`, punto d'ingresso `certifica <bot>`) certifica
**esattamente come opererebbe il bot sul mercato reale**. Per dirlo deve coprire tutte le
componenti qui sotto. Una componente non coperta si dichiara ⊘ con la causa nel referto:
mai silenziosamente.

### 6.1 Dati di mercato (l'unica verità è lo stream registrato)
- Formato nativo Betfair (`mcm`, `rc` con `atb/atl/trd`, `marketDefinition`), letto da
  `HistoricalStream`: mai un formato «curato» o ricostruito.
- Tutti i mercati che il bot usa (Match Odds, Correct Score, Over/Under, HT, ecc.):
  se la registrazione non li ha, il bot **non può** essere certificato su quella partita.
- Profondità del ladder e volumi scambiati (`EX_TRADED`, `ladder_levels` almeno pari a
  quelli letti in produzione): senza volume scambiato il matching a riposo non esiste.
- Stato del mercato tick per tick: `OPEN` / `SUSPENDED` / `CLOSED` / `INACTIVE`, flag
  `inPlay`, `betDelay` dalla `marketDefinition`, runner rimossi, mercato annullato.
- Punteggi, minuto, cartellini, timeline dal sidecar (`.scores.jsonl` / `.score.jsonl`),
  iniettati **con lo stesso ritardo** che hanno in produzione (IPS 2-3 s dopo il gol).
- Qualità della registrazione dichiarata (COMPLETE / PARTIAL / NO_RAW) in ogni referto;
  le sintetiche (`_synth_*`) mai contate come reali.

### 6.2 Scanner e feed (il bot vede solo ciò che lo scanner scrive)
- Lo **scanner vero** (`safe_strategy/service.py::Scanner`) alimentato dai MarketBook di
  flumine, `build_rows` vero, orologio dello scanner = `publish_time`.
- `pre_ko` congelato al primo tick in-play; riferimento 1X2 mai da quote live.
- Freschezza: `feed_age`, righe e scanner **entrambi** vecchi per un feed stantio
  (write-on-change tiene fresco quello che non cambia); dato assente non è zero.
- Il feed del bot (`feed.py`, `snapshot_from_row`, `build_*_ctx_from_scan`) è quello di
  produzione, mai uno snapshot costruito a mano.

### 6.3 Il servizio intero, non solo il cervello
- Si esegue `run_once` (il ciclo vero), non solo `_run_event` o `decide`: così entrano
  stop giornaliero, tetti di partite e di rischio, `status`/`mode` di controllo, richieste
  della UI, riconciliazione, settlement, cache, cadenze.
- **Cadenza reale**: il bot gira ogni N secondi in produzione (Safe ~2 s, Mike fino a
  20, Omega fino a 60): il replay lo chiama alla stessa cadenza sul tempo di mercato, non
  a ogni tick, altrimenti vede più (o meno) di quanto vedrebbe.
- **Tutti gli stati e tutte le fasi** della macchina a stati osservati almeno una volta
  (Mike: 21 stati, 7 fasi, SETTLING compreso via `process_closed_market`); i mai visti
  elencati per nome.
- Riavvio a metà partita: il replay ferma il servizio con una posizione aperta e lo
  riavvia (stato dal DB in memoria): la posizione deve essere ritrovata e sorvegliata.
- Bot fermato con posizione aperta: le protezioni girano, le aperture no.
- Modalità: paper e live esercitate entrambe nel replay, con parità campo per campo
  delle richieste; `strategy_modes` per strategia; guardia di avvio (`avvio_app`).

### 6.4 Ciclo di vita dell'ordine (dove sono nati tutti i difetti del 15/09)
- Piazzamento vero su flumine (`market.place_order`), esito riletto da oggetti veri
  (`PlaceResult`, `order.status.value`, `size_matched`, `size_remaining`,
  `average_price_matched`, `bet_id`), mai da un finto.
- **Bet delay** sull'orologio virtuale di flumine (`SimulatedDateTime`) più latenza di
  piazzamento: mai saltati, mai sommati a un ritardo «in casa».
- Taker, appoggiato (`_piq`: size davanti a noi, consumata dal volume scambiato, metà
  per lato), FOK, place-and-trim/submin, green-up, copertura, cash-out, chiusura,
  seconda entrata, cancel e replace.
- **Parziali**: abbinato z su x → copertura e green-up sulla parte abbinata, residuo
  gestito (annullato o seguito), mai una posizione scoperta non dichiarata.
- Minimo di giurisdizione (.it: back 2,00 / lay 0,50) e place-and-trim, banda del
  profit-ratio (`INVALID_PROFIT_RATIO`), fondi insufficienti, `BET_TAKEN_OR_LAPSED`.
- Esito ignoto (timeout o eccezione): gamba `pending_reconcile`, riconciliazione per
  `bet_id` → ref → ref storico **solo a mercato e selezione concordi** (i ref
  `{ruolo}-{ciclo}-{seq}` collidono fra partite).
- Sospensione diversa da chiusura: su sospeso si aspetta, su chiuso si cambia strada; le
  finestre temporali non scorrono a mercato non operabile; l'ordine appoggiato scade alla
  sospensione se Betfair lo farebbe (`LAPSE`/`PERSIST` come in produzione).
- Settlement dal risultato del mercato registrato, con **commissione**; P&L netto.
- Esposizione e liability calcolate sull'abbinato, non sul chiesto.

### 6.5 Persistenza e UI (ciò che il trader vede)
- Le righe scritte nel DB in memoria hanno le **colonne vere** delle migrazioni
  (`CHECK` compresi: uno stato non ammesso dal vincolo è un difetto, non un dettaglio).
- Ogni trade porta chiesto, abbinato, residuo, prezzo medio, stato, ultimo aggiornamento
  da Betfair: sono i campi che la UI mostra; se mancano, il referto lo dice.
- Attività (`kind`) scritte per ogni decisione rilevante: freno, rifiuto, riconciliazione,
  blocco d'avvio, motivo di non apertura.

### 6.6 Concorrenza e limiti
- Più partite insieme: tetti di partite e di rischio che interagiscono, ref che non
  collidono, stop giornaliero che ferma le aperture e non le uscite.
- Tetti di flumine aperti nel replay (si certificano i limiti del bot); i tetti di flumine
  usati in produzione (dallo stake) esercitati in uno scenario dedicato.

### 6.7 Scenari e falsificazione
- Scenari che cambiano **solo** parametri, freschezza del feed o guasti iniettati:
  base · taker · cap stretto · bot fermo · senza seconda puntata · feed stantio ·
  esiti ignoti · sospensione prolungata · riavvio a metà · parziali (coda davanti e
  volume basso) · rifiuto di Betfair · prezzo migliore · mercato annullato.
- Copertura dei controlli: ogni controllo dichiara `quando=` è sollecitato; il referto
  conta le sollecitazioni; «zero violazioni» senza sollecitazioni vale «non lo so».
- **Falsificazione obbligatoria**: reintrodotti i difetti del catalogo §7 sul codice
  corretto, il replay **deve** diventare rosso; si registra quali controlli scattano.
- Prima di accusare il bot: escludere che il falso positivo sia del controllo (stato
  persistente letto come corrente, regola letta a metà).

### 6.8 Referto e riproducibilità
- Per bot: partite (con qualità), tick, decisioni, ordini, fill, violazioni per codice
  con regola citata, copertura dei controlli, stati e fasi visti e non visti, scenari
  eseguiti, falsificazioni, celle della matrice ordini provocate, limiti residui ⊘.
- Comando esatto, versioni (flumine, betfairlightweight), hash del codice del bot: il
  referto deve essere rifacibile identico.
- Il banco gira anche nella suite (`pytest -m cert`, campione ridotto) così che una
  modifica al bot rilanci la certificazione **di default**.

---

## 7. CATALOGO DEGLI ERRORI GIÀ VISTI — ognuno è un controllo, un test o una falsificazione

Difetti di consapevolezza dell'ordine (15/09, ordini veri):
1. Chiave scritta in una grafia e letta in un'altra (`customerOrderRef` vs
   `customer_order_ref`, `sizeMatched` vs `size_matched`) → 32 green-up in loop.
2. `res.ok` mai letto: rifiuto di Betfair trattato come copertura esistente.
3. Campo inesistente letto con `getattr(..., default)` (`avg_price` vs
   `avg_price_matched`) → prezzo medio uguale al prezzo chiesto.
4. Riconciliazione con un ref diverso da quello di piazzamento → ordine vivo dichiarato
   mai piazzato → secondo green-up.
5. `closes_trade_id` in colonna ma letto nel meta → nessuna chiusura riconosciuta →
   place-and-trim rifiutato in loop e freno live applicato alle uscite.
6. Ref storico confrontato senza mercato e selezione: `seq` conta per partita, collide.
7. `bet_id` salvato solo se abbinato: l'ordine appoggiato non si ritrova al giro dopo.

Difetti di simulazione (banco):
8. Fill scritto a mano al posto del matching di flumine (11 azioni contro 2.432).
9. Ladder letto con `getattr` su un `dict` → `None` in silenzio → bot cieco.
10. `order.status` Enum confrontato come stringa → nessun ordine risulta vivo → loop.
11. Tetti di flumine lasciati ai default → si certificano i limiti di flumine.
12. Bet delay saltato (`_esegui_subito`) o sommato al ritardo in casa.
13. `_resting_filled` che dichiara il fill quando il prezzo viene sfiorato, senza coda.
14. Paper senza FOK dove il live lo ha; paper senza bet delay (Omega); guardia combo
    solo in paper: il paper più generoso (o più severo) del live.
15. Snapshot di scan costruito a mano invece che dallo scanner vero.
16. Falso positivo del controllo: `ctx.close_reason` persistente letto come corrente;
    `under_second` accusata quando è nella spec (§15.3).

Difetti di stato e di mercato:
17. Sospeso trattato come chiuso (rinuncia) o chiuso come sospeso (attesa eterna);
    finestre che scorrono durante la sospensione del fischio.
18. Vincolo `CHECK` del DB che non ammette uno stato del motore → upsert rifiutato per
    12 giorni, posizioni scoperte al fischio; scrittura fallita declassata a warning.
19. Stato in RAM perso al riavvio (`pre_ko`): base e punta spente per ore.
20. Battito «vivo» scambiato per «coda utilizzabile»; processo vivo con codice vecchio.
21. Tetto partite che conta paper e live insieme; P&L che somma paper e live; zero
    scritto al posto di assente.
22. Bot che riparte da solo all'avvio dell'app (`status='running'` ereditato).
23. `stats` riscritte per intero che cancellano l'impronta di avvio.
24. RPC `*_activate` con `coalesce(p_params,'{}')` che azzera i cap alla riaccensione.
25. Modalità ereditata dal servizio invece che scritta per strategia.
26. `execution_mode` cablato in env o `'rest'` che spegne la coda in silenzio;
    `LIVE_ORDER_MODE` per processo che uccide le righe dell'altra modalità.

Difetti di test:
27. Finti con chiavi o tipi diversi dal vero (riga al posto dell'id, camelCase, `ok`
    assente) che certificano il difetto.
28. Test che asserisce il comportamento sbagliato (la review 53/53 ne ha trovato uno).
29. Test che passa a vuoto (fixture che non espone mai la condizione).
30. Mutazioni non catturate: `not res.ok` tolto (0 rossi su 614), bordo del cap di
    liquidità, paper sommato nel netto live.
31. Copie di laboratorio (`scalper_lab`, `TennisLabStrategy`) spacciate per backtest;
    backtest con gate «aperto» rispetto ai default di produzione.
32. Registrazioni PARTIAL contate come complete; sidecar cercato con il nome sbagliato.

Difetti di piattaforma:
33. Costante nel frontend che duplica una scelta del backend (cadenza del battito).
34. Fase di protezione che gira **dopo** la riconciliazione o che viene frenata.
35. Un test verde mai visto diventare rosso (`b1285a0` spinto con 4 rossi).

Difetti dei controlli di certificazione (16/09 sera, trovati falsificando Mike):
36. **I controlli che guardano solo la DECISIONE non vedono i difetti di consapevolezza**: i 5
    difetti del 15/09 reintrodotti uno per uno lasciavano il replay verde e il referto identico
    cifra per cifra. Serve sempre una famiglia di controlli **K** che confronta, dopo ogni giro,
    ciò che il bot CREDE di ogni gamba (stato, abbinato, prezzo medio, ref) con ciò che il
    MERCATO/banco dice degli ordini (`verifica_consapevolezza`), più scenari che provocano
    rifiuti di Betfair e abbinamenti a prezzo migliore. Un controllo che dipende dalla
    confessione del bot (attività scritte dal bot) non certifica.
37. **La pool di processi non isolava i replay**: cache di modulo sopravvissute fra scenari nello
    stesso figlio → controlli sotto-sollecitati (R3 ×0 dentro `--scenari tutti`, ×5837 da solo).
    Ogni replay parte con le cache di processo azzerate da un elenco ESPLICITO; un `_riavvia`
    che svuota «tutto» con `dir()` reintroduce difetti (svuotava `_ALIAS_ORDINE`).

**Definizione di fatto, per un bot:** referto §6.8 completo, tutti i controlli sollecitati
almeno una volta o dichiarati ⊘ con causa, falsificazione con i punti 1-17 del catalogo
(quelli applicabili) tutti rossi **a livello di replay** (famiglia K), non solo di test unitario, parità paper/live verde, stati e fasi tutti visti o
elencati, e la firma di chi ha rieseguito il replay di persona.

Piano operativo in corso: `PIANO_CERTIFICAZIONE_DEFINITIVA_2026-09-16.md`.
