# AUTO-FOLLOW: i bot operano da soli su tutte le partite (25/09/2026)

Lavoro di un delegato del coordinatore. Worktree rebased su `f8b3a7e` (conflitto in
`motore_ordini.py` risolto tenendo entrambe le modifiche: la riga di misura dei tempi
`_TEMPI.nuovo` resta prima del parcheggio). Niente commit, niente DB vero, nessun processo
nuovo: l'auto-follow è un thread dentro il runner calcio.

Patch: `AUDIT_2026-09-25/auto_follow.patch` (file già tracciati). File nuovi:
- `Betfair/stream/auto_follow.py`;
- `Betfair/stream/tests/test_auto_follow_2026_09_25.py`;
- `frontend/src/components/live/LiveMatchCard.origine.test.tsx`;
- `migrations/live_follow_origine_2026-09-25.sql`;
- `AUDIT_2026-09-25/mutazioni_auto_follow.py` e `AUDIT_2026-09-25/falsificazione_auto_follow.txt`.

Ordine dell'utente: «TUTTI I BOT NELLA CONTROL ROOM UNA VOLTA ARMATI DEVONO POTER OPERARE SU
TUTTE LE PARTITE IDONEE DA SOLI». Le strategie non sono state toccate: nessuna modifica a
`safe_strategy/engine.py`, `exits.py`, `omega/omega_v3.py`, `mike/engine.py` e nemmeno ai
servizi o alle porte dei bot.

## 0. In breve

- **Prima.** Con il canale acceso, un comando su un mercato che il runner non seguiva
  veniva rifiutato: `live_order_worker.py:638`, «market … non sottoscritto nel runner»
  (scenario R10).
  - Per seguire una partita serviva il clic «Segui live».
  - Aggiungerla allo stream voleva dire RICOSTRUIRE flumine. La ricostruzione si rinvia
    finché ci sono ordini vivi o regole armate (`runner._lifecycle_blockers`). In più
    azzera il blotter: le posizioni paper vanno perse. Quindi, mentre i bot lavorano,
    non si può fare.
- **Dopo.** Il runner segue da solo:
  - il mercato di ogni comando di un bot (**aggancio al volo**);
  - in anticipo, le partite del feed quando un bot calcio è collegato al canale
    (**proattivo**).
- **Come.** Una **risottoscrizione a caldo sulla stessa connessione**: un nuovo
  `marketSubscription` con `BetfairStream.subscribe_to_markets`.
  - Nessuna ricostruzione e nessuna connessione in più.
  - Il blotter e le posizioni paper e live restano intatti.
- **Profili rapidi** (`--trasporto entrambi`): **safe_base OK, omega OK**.
  - 14 scenari ciascuno, R10 compreso con il nuovo esito.
  - La parità coda/canale non cambia.
- **Test:** 31 test nuovi, verdi. 16 mutazioni su 16 fanno diventare rossi i test (4 anche
  sul profilo rapido vero), e dopo ogni mutazione il file è stato ripristinato con sha1
  verificato.
- **Tennis NON fatto: è un buco dichiarato (§6).**

## 1. Runner calcio: cosa fa ora → dopo (file:riga del worktree)

| Pezzo | Prima | Dopo |
|---|---|---|
| Comando su mercato non seguito | `_dispatch` → `_resolve_market` solleva (`live_order_worker.py:638`) → evento `rifiutato` | Motore:<br>- `_serve_aggancio` (`motore_ordini.py:1048`, chiamato a `:786`): se il mercato non è servibile, ack **accettato** con motivo `in_aggancio: …`;<br>- `_parcheggia` (`:1070`, `:820`): comando in RAM in ordine FIFO e riga di diario `in_aggancio`;<br>- `avanza_aggancio` (`:1087`, a ogni giro del motore `:683`, attesa ≤50 ms): parte al primo book NUOVO, con le guardie rifatte;<br>- oltre `MOTORE_AGGANCIO_MAX_MS` (3000, `:119`): evento `rifiutato` ed esito nel diario `in_aggancio: … il bot ripete la decisione` (`errore_forzato`, `:999`) |
| Tetto pieno | — | `Rifiuto(M_TETTO)`, ack `tetto_mercati_pieno: …` (mai un ordine alla cieca) |
| Runner senza framework (nessuna partita) | `runner_non_agganciato` | Stesso rifiuto, ma il mercato entra nel piano (`:858` «aggancio richiesto») e il runner parte con i mercati dei bot (`runner.py:1929`) |
| Sottoscrizione | Solo i `live_follow` manuali, a ricostruzione | `auto_follow.AutoFollow._applica` (`auto_follow.py:778`) → `SottoscrittoreStream.applica` (`:363`):<br>- stessa MarketStream, `stream_id` aggiornato su stream e strategie;<br>- `market_filter` aggiornato: la riconnessione di flumine lo riusa;<br>- mai un filtro vuoto, mai oltre 200 mercati;<br>- invii raggruppati, minimo 250 ms fra due |
| Ricostruzione (clic manuale) | `market_ids = session.all_market_ids()` | Manuali + automatici, rientrati nel tetto (`runner.py:2002`); `auto.aggancia(framework, …)` (`:2210`), `sgancia` (`:2231`) |
| Righe `live_follow` automatiche | — | `FollowDb` (`auto_follow.py:402`):<br>- insert `ignore_duplicates` + update SOLO `WHERE origine='auto'` (il follow dell'utente non si riscrive mai);<br>- `STREAMING`, poi `CLOSED` quando l'evento esce;<br>- all'avvio le righe auto rimaste aperte vanno a `CLOSED` (`chiudi_orfani`, `runner.py:1850` e seguenti);<br>- senza colonna `origine`: nessuna scrittura, lavoro solo in RAM |
| `subscription_worker` | Ogni riga nuova → ricostruzione | `_nuovi_follow_manuali` (`runner.py:952`, usato a `:856`): una riga STREAMING di un evento seguito da solo non ricostruisce. Un clic dell'utente (PENDING) sì, come oggi |
| Follow manuali | Come oggi | In unione, mai toccati, mai espulsi |
| Eventi automatici | — | «Silenziosi»: solo lo stream (book, blotter, ordini, specchio, paper matching). Niente `live_now`, ladder su DB, segnali o raw: 30 e più partite schiaccerebbero il DB (13/09). Per il terminale completo serve «Segui live» |

Il motore e l'auto-follow si agganciano così:
- `_costruisci_auto_follow` (`runner.py:1637`) costruisce l'auto-follow;
- l'auto-follow viene passato al motore (`aggancio=_auto_attivo()`, `:1671`);
- è acceso di serie quando c'è il motore; `RUNNER_AUTO_FOLLOW=0` lo spegne e il motore
  torna al comportamento di prima.

## 2. Tetti e priorità (`PianoFollow`, `auto_follow.py:170`)

- **Tetto.** `tetto_mercati()` (`:123`) = `min(HARD_MARKET_CAP=180, 200)`.
  - Conta i mercati manuali e quelli automatici, sull'UNICA connessione di mercato del
    runner.
  - `AUTO_FOLLOW_TETTO_MERCATI` lo modifica, ma mai oltre 200.
  - Connessioni: nessuna in più (1 di mercato, più quella degli ordini in LIVE, come
    oggi).
- **Priorità.**
  - Mai espulsi:
    - gli eventi con **ordini nel blotter** (qualunque strategia, paper o live; nel dubbio
      protetti);
    - gli eventi con un **comando chiesto negli ultimi 10 s** (`PROTEZIONE_COMANDO_S`):
      il suo ordine è in volo o parcheggiato.
  - Poi **comando** (2), poi **candidata del feed** (1). I **manuali** non si espellono mai.
- **Espulsione** (solo per un comando):
  - si toglie la voce automatica con priorità ≤ quella del comando, prima la meno
    prioritaria, poi la più vecchia;
  - si espelle il minimo indispensabile;
  - è transazionale: entra tutto o non cambia niente (`richiedi`, `:233`).
- **Proattivo.** Non espelle mai nessuno.
- **Rientro.** A ricostruzione, se i manuali sono cresciuti, le voci automatiche meno
  prioritarie escono (`rientra`, `:287`).
- **Pulizia** (`_pulisci`, `:854`). Escono:
  - i mercati CHIUSI senza ordini vivi;
  - i mercati mai arrivati in flumine dopo 120 s (`MAI_ARRIVATO_S`);
  - le voci di comando uscite dal feed da 15 minuti e senza ordini.

**ATTENZIONE: questa è una decisione per l'utente.** `LIVE_MARKET_TYPES` non è impostata
nel `.env`, quindi ogni partita seguita a mano sottoscrive TUTTI i suoi mercati (50-100).
Bastano 2-3 partite seguite a mano per riempire i 180 posti. A quel punto ogni comando di
un bot su un'altra partita riceve `tetto_mercati_pieno`: il rifiuto è dichiarato, ma i bot
non operano. Per evitarlo si imposta `LIVE_MARKET_TYPES` (per esempio `MATCH_ODDS`,
`CORRECT_SCORE`, `HALF_TIME_SCORE` e le linee `OVER_UNDER_*`).

## 3. Aggancio al volo: la meccanica e perché

1. Il comando arriva al motore. Le guardie di sempre restano identiche (età, token, modo,
   guardia d'avvio, kill-switch, settings).
2. Se il mercato non è servibile, o se c'è già una fila su quel mercato, il motore chiede
   il mercato all'auto-follow con priorità COMANDO.
   - Ack **accettato**, con `motivo: "in_aggancio: mercato X non ancora sottoscritto,
     aggancio al volo in corso (al più 3000 ms)"`.
   - Stesse chiavi dell'ack di sempre.
3. Il thread dell'auto-follow, svegliato subito, invia la risottoscrizione (un
   `sendall`). Betfair risponde con il SUB_IMAGE.
4. Il mercato diventa **servibile** solo quando flumine ha un book NUOVO dopo l'invio
   (`servibile`, `auto_follow.py:674`: confronta l'`id()` del book).
   - Un mercato espulso e ripreso ha in flumine il suo ultimo book vecchio: su quello non
     si esegue mai.
5. Il motore esegue i comandi in fila, in ordine FIFO per mercato: un comando arrivato
   durante l'aggancio non scavalca quelli prima.
   - Rifà `_controlla`: se nel frattempo si è acceso il kill-switch, l'esito è
     `rifiutato`.
   - Poi il `_dispatch` di sempre, sul client della modalità della riga.
6. Se il book non arriva entro 3000 ms da `ricevuto_ms`: evento terminale `rifiutato` e
   diario `esito` con `errore = "in_aggancio: … non sottoscritto entro 3000 ms (aggancio
   richiesto: il bot ripete la decisione)"`.
   - Il mercato resta nel piano: il comando successivo del bot lo trova già servibile.

**Perché questa e non «rifiuta e il bot riprova».**
- I client di Safe e Omega gestiscono GIÀ la sequenza «ack accettato → evento terminale»:
  la riga resta `pending`, con TTL paper di 60 s. Quindi i bot non si toccano.
- Un rifiuto immediato renderebbe `error` la riga, e se la strategia riprova sulla stessa
  candidata non è una cosa che decide il trasporto.
- Il ritardo massimo aggiunto (3 s più i 3 s del trasporto) resta nell'ordine del bet
  delay in gioco (5 s) che ogni ordine sconta comunque.
- Il prezzo è un LIMIT del bot, e le aperture live di Safe e Omega sono FOK: un mercato
  che si è mosso produce al peggio un FOK non abbinato.
- Il tempo massimo si regola con `MOTORE_AGGANCIO_MAX_MS`.

**Latenza misurata** (logica, finti): comando → parcheggio → sottoscrizione → book →
place < 20 ms (`test_latenza_logica_aggancio_sotto_i_20_ms`). Dal vivo va aggiunto il
viaggio del SUB_IMAGE di Betfair: NON misurato.

## 4. Banco: R10 cambiato e 3 scenari nuovi (`trasporto_rapido.py`)

`PortaBanco.monta_auto_follow` (`porta_banco.py:377`) monta l'`AutoFollow` di produzione.
- Al posto della connessione c'è `SottoscrittoreBanco` (`:247`): l'immagine della
  sottoscrizione arriva al giro dopo, perché lo stato corrente del mercato è già in
  flumine.
- Senza montarlo il banco è identico a prima. La parità coda/canale gira senza
  auto-follow.

| Scenario | Controlli |
|---|---|
| R10 mercato non seguito (`:796`) | Il runner non segue niente; comando Safe/Omega sul MATCH_ODDS vero:<br>- ack accettato `in_aggancio`, voce a priorità COMANDO;<br>- sottoscrizione a caldo col mercato del comando;<br>- evento terminale e UN ordine su flumine, nessuna REST;<br>- mai «non sottoscritto»;<br>- riga `open` (abbinato);<br>- la voce prende l'event_id vero `35760084` |
| R10b tetto pieno (`:856`) | Tetto 1 occupato da una candidata senza ordini:<br>- il comando la espelle (`espulsi == 1`);<br>- ordine sul mercato del comando ed evento terminale;<br>- la sottoscrizione non supera mai il tetto |
| R10c mai espulsi (`:900`) | Tetto 1 occupato (a) dal MATCH_ODDS con gli ordini degli scenari precedenti, (b) da un follow MANUALE:<br>- ack `tetto_mercati_pieno`, piano invariato, 0 espulsi;<br>- nessun ordine, nessuna REST;<br>- esito del bot `error` con quel motivo |
| R10d aggancio mai in silenzio (`:952`) | Mercato inesistente, `aggancio_max_ms=300`:<br>- ack `in_aggancio`, poi evento `rifiutato`, diario `in_aggancio: …`;<br>- nessun ordine, nessuna REST, niente resta parcheggiato;<br>- riga `error` |

### Esiti dei due profili rapidi (`--scenari rapidi --trasporto entrambi --worker 1`, `_live_raw` del checkout principale)

| | safe_base | omega |
|---|---|---|
| scenari | 14, KO 0, 3,9 s | 14 (13 OK + R8 N/A col suo motivo), KO 0, 7,6 s |
| parità | RAGGIUNTA: decisioni coda 3508 / canale 3512, 0 violazioni, ordini 2/2, righe 2/2, REST sul canale 0, tempi +2,1 s max | RAGGIUNTA: decisioni 467/467, 0 violazioni, ordini 1/1, REST 0, tempi 0,0 s |
| client / motore | da_seq 0, buchi 0; comandi 2, accettati 2, eventi 6 | da_seq 0, buchi 0; comandi 1, eventi 3 |
| durata | 156,4 s (replay coda 65,2 s, canale 87,3 s) | 134,5 s (coda 66,9 s, canale 60,0 s) |
| ESITO | **OK** | **OK** |

I numeri della parità sono identici al referto del 25/09 (§4 di
`STRADA_UNICA_BANCO_E_PAPER.md`). Le uscite complete sono in
`AUDIT_2026-09-25/auto_follow_profilo_safe.txt` e `auto_follow_profilo_omega.txt`.

I profili sono stati rilanciati PRIMA dell'ultima aggiunta (protezione dei comandi recenti
e pulizia dei mercati mai arrivati). Dopo quell'aggiunta sono stati rilanciati gli scenari
rapidi di entrambi i bot (`test_strada_unica…::test_profilo_rapido_verde…[safe_base|omega]`,
verdi), non la parità intera. La parità non passa dall'auto-follow.

## 5. Test e falsificazione

- **`Betfair/stream/tests/test_auto_follow_2026_09_25.py`: 31 test.**
  - Finti: canale, flumine e DB presi da `test_motore_ordini_2026_09_24`, con le chiavi vere.
  - Il sottoscrittore è verificato con `BetfairStream` e `StreamListener` VERI di
    betfairlightweight e con la `MarketStream` VERA di flumine: messaggio
    `marketSubscription` inviato sul socket finto, id nuovo sullo stream e sulle
    strategie, mcm del vecchio id scartato, SUB_IMAGE del nuovo id consegnato.
  - Il market definition ha le chiavi Betfair (`test_backtest`).
- **Casi coperti.** Piano:
  - entra tutto o niente;
  - ordine di espulsione;
  - mai manuali, mai protetti, mai priorità più alta;
  - rientro, rinomina, tetto non oltre 200.

  Motore:
  - non seguito → agganciato ed eseguito;
  - mai su un book stantio;
  - FIFO durante l'aggancio;
  - scadenza dichiarata;
  - kill-switch acceso durante l'attesa;
  - **paper e live separati dopo l'aggancio** (client e strategia della modalità);
  - tetto pieno con ordini → rifiuto, poi espellibile senza ordini;
  - senza auto-follow come prima;
  - il cancel non aggancia;
  - runner fermo;
  - latenza;
  - comando recente protetto e mercato mai arrivato che esce.

  Sottoscrittore: vero, vuoto, oltre 200, stream giù, errore non marcato come applicato.

  Feed: in gioco prima ed entro il tetto; niente bot → niente lettura e candidate liberate
  (chi ha ordini resta); feed muto non toglie niente; `leggi_feed_calcio` con lo scanner
  fermo o vivo, e senza `score_raw`.

  DB: mai riscritto il follow dell'utente; senza colonna niente scritture; riga scritta dopo
  la rinomina.

  Runner: le righe auto STREAMING non ricostruiscono, il clic dell'utente sì.

  Canale: `attori_comando` conta solo chi ha il token giusto. Stato: tetto e numeri
  dichiarati.
- **`frontend/src/components/live/LiveMatchCard.origine.test.tsx`: 2 test.** Badge
  `auto`/`manuale`; colonna assente = manuale.
- **Test dei file toccati, tutti verdi:**
  - Python: 234 test (auto-follow, motore, porta_banco, strada unica, sub_worker flat guard,
    runner modo/guardia/canale, local_channel, tempi F0, contratto strada unica,
    lifecycle, live_strategy);
  - altri 356 test che importano i moduli toccati (porte Safe/Omega, canali, esiti,
    watchdog e così via);
  - `npx tsc -p tsconfig.app.json --noEmit` rc=0;
  - vitest del test nuovo verde.
- **Falsificazione** (`AUDIT_2026-09-25/mutazioni_auto_follow.py --banco`, esito in
  `falsificazione_auto_follow.txt`): **16/16 mutazioni ROSSE**, e il profilo rapido vero è
  rosso su M1, M4, M6 e M14.
  - Mutazioni: niente aggancio; book stantio accettato; niente FIFO; aggancio che non
    scade mai; guardie non rifatte; protezione di chi ha ordini tolta; espulsione senza
    guardare la priorità; `stream_id` non aggiornato; upsert che sovrascrive l'utente;
    righe auto ricostruite; feed muto che toglie; runner fermo senza richiesta; cancel che
    aggancia; manuali espellibili; comando recente non protetto; mercato mai arrivato
    eterno.
  - Ripristino dai BYTE salvati (mai `git checkout`), sha1 OK su tutte.
  - Base e dopo: 31 test passati.

## 6. Tennis: NON fatto, buco dichiarato

Verificato leggendo il codice:
- **I 4 bot tennis** sono strategie DENTRO il runner tennis. Si armano solo a ricostruzione,
  sulle partite seguite (`tennis_runner.py`, `setup_and_run`, ciclo `_instantiate_bot`).
  - Non possono mandare ordini su un mercato non seguito: il rifiuto «non seguito» non
    esiste per loro.
- **Il buco.** Il ponte crea i follow `origine='auto'`, ma `follow_worker`
  (`tennis_runner.py:1653`, `:1669`) chiede la ricostruzione con `forza=False`.
  - `_request_restart` (`:930`) la rinvia finché anche UN solo bot ospitato, su qualunque
    partita, non è flat.
  - Mentre i bot tengono posizioni, le partite nuove del feed non vengono mai sottoscritte
    né armate.
- **Safe tennis.** Oggi non passa dal runner tennis: REST o paper legacy.
  `SAFE_TENNIS_ORDINI_VIA_CANALE` deve restare spento, perché il runner tennis non monta
  il motore (F8). Per ora non c'è nessun rifiuto da correggere.
- **Proposta per il prossimo cantiere, da decidere.** Riusare `SottoscrittoreStream` nel
  runner tennis e armare i bot a caldo:
  1. catalogo dell'evento;
  2. risottoscrizione della MarketStream condivisa;
  3. `_instantiate_bot` con `market_ids` = il filtro NUOVO, ordinato come in `applica`
     (altrimenti flumine apre una seconda connessione);
  4. `framework.add_strategy(bot)` a framework avviato e `session.hosted`.

  Tocca il ciclo di vita del runner tennis (hosted, stopping, episodi di restart) e va
  certificato con un banco tennis: non l'ho fatto senza un banco su cui provarlo.

## 7. Accensione in paper: cosa deve comparire

Il coordinatore imposta `MOTORE_ORDINI_CANALE=1`, `SAFE_ORDINI_VIA_CANALE=1` e
`OMEGA_ORDINI_VIA_CANALE=1`; l'utente riavvia l'app. `RUNNER_AUTO_FOLLOW` non serve: è
acceso di serie.
- **Prima: applicare la migrazione** `migrations/live_follow_origine_2026-09-25.sql`.
  Senza, l'auto-follow funziona lo stesso ma solo in RAM: nessuna riga e nessun badge in UI,
  e nel log compare «live_follow.origine NON disponibile».

Log del runner calcio (livello INFO):
1. `[runner] AUTO-FOLLOW ATTIVO: i bot operano da soli su tutte le partite (aggancio al volo + feed), tetto 180 mercati sulla connessione di mercato (limite Betfair 200), N follow auto di prima chiusi`.
2. `[runner] motore ordini ATTIVO sul canale 47331 (diario …\_diario_ordini)`.
3. Con Safe o Omega collegati, entro 30 s e poi a ogni cambio:
   `[auto-follow] seguiti da soli X eventi (Y mercati) + manuali Z mercati = T/180 sulla connessione di mercato (limite Betfair 200); con posizioni P; feed F partite (db); espulsi E, rifiuti tetto R`.
4. `[auto-follow] sottoscrizione a caldo: N mercati (+a -b) sulla stessa connessione, tetto 180`.
5. Su un comando per una partita non ancora seguita:
   - `[auto-follow] aggancio al volo di 1.xxx (comando safe)`;
   - `[motore] safe-t123 in attesa dell'aggancio di 1.xxx (scade fra 3000 ms)`;
   - `[motore] safe-t123 agganciato dopo NNN ms: eseguo`.
6. Da NON vedere più: `market … non sottoscritto nel runner` sui comandi dei bot. Se
   compare `tetto_mercati_pieno`, vedi §2 (`LIVE_MARKET_TYPES`).

Diario `DATA_DIR/_diario_ordini/<AAAA-MM-GG>.jsonl`:
- righe `in_aggancio` (market_id, scadenza_ms);
- righe `agganciato` (`attesa_ms` = età dell'aggancio);
- poi `ordine` ed `esito`, come per ogni comando.
- L'età del comando resta `ts_ms − parametri.creato_ms`, sotto 3000.

UI e fonte:
- `/segui-live`: le partite seguite dai bot compaiono con il badge **auto** (con la
  migrazione), stato STREAMING.
- Il numero di eventi auto, il tetto, i mercati usati, l'età e la fonte del feed sono nel
  topic `auto_follow` del canale 47331 e nell'`hello` (`AutoFollow.stato()`).
  **Nessun pannello della Control Room li mostra ancora**: la fonte per ora è il log.
- Fonte del feed: `safe_strategy_scan` letta dal DB ogni 30 s, SOLO con lo scanner vivo
  (battito ≤ 30 s) e con un bot calcio collegato al canale.

La frase «i bot operano da soli su tutte le partite idonee» è vera quando:
- nel log il numero di eventi seguiti da soli segue le partite in gioco del feed, fino al
  tetto;
- i comandi dei bot su partite mai cliccate compaiono nel diario come `agganciato` e poi
  `esito ok`;
- non compare nessun `non sottoscritto`.

## 8. Non verificato

- **La risottoscrizione contro Betfair vero.** È provata con le classi vere di
  betfairlightweight e flumine su un socket finto, non in rete. Restano da vedere dal vivo:
  - che Betfair sostituisca la sottoscrizione e mandi subito il SUB_IMAGE;
  - la latenza reale;
  - la riconnessione di flumine con il filtro nuovo e i clk della nuova sottoscrizione.
- **La scrittura sul socket SSL dal thread dell'auto-follow** mentre il thread di lettura di
  betfairlightweight legge (lettura e scrittura concorrenti sullo stesso socket SSL).
  Nessun problema visto, ma non provato sotto carico.
- **Collisione di `stream_id`.** flumine distanzia gli stream di 10000 e ogni
  risottoscrizione fa +1: dopo 9999 risottoscrizioni nella vita di un framework ci sarebbe
  una collisione (a 250 ms minimo fra due, più di 40 minuti di risottoscrizioni continue).
  Dichiarato, non gestito.
- **La select del feed** (alias `payload->cs->>market_id`, …) non è stata eseguita su
  PostgREST vero. Nemmeno la migrazione è stata eseguita.
- **Il motivo del rifiuto dopo un ack accettato non arriva al bot.** L'evento `order` non
  ha una chiave di motivo: è il protocollo, non l'ho cambiato. Il motivo è nel diario e
  nel log del runner. Safe non salva nella riga il motivo `in_aggancio` dell'ack.
- **Il dettaglio del Terminale** di una partita seguita solo in automatico è vuoto (niente
  `live_now`): serve «Segui live».
- **Un clic manuale mentre i bot hanno posizioni.** La ricostruzione resta rinviata dalla
  flat guard, come oggi. La si potrebbe portare sulla via a caldo: è una decisione
  dell'utente.
- **Primo comando a runner fermo** (nessuna partita e feed vuoto): rifiutato
  `runner_non_agganciato` con aggancio richiesto. Il runner parte entro ~2 s più la
  connessione dello stream; il comando successivo passa.
- **Mike** (nessuna porta, REST) e **scalper** (processi propri) non passano dal runner
  calcio e non ne sono toccati.
- **La matrice completa** `--scenari tutti --trasporto entrambi` non è stata lanciata.
- **L'UI della Control Room** non mostra lo stato dell'auto-follow (vedi §7).

## 9. File toccati

- `Betfair/stream/motore_ordini.py`: aggancio al volo; conflitto del rebase su `f8b3a7e`
  risolto con entrambe le modifiche.
- `Betfair/stream/runner.py`: costruzione, idle, ricostruzione, `subscription_worker`,
  arresto.
- `Betfair/stream/local_channel.py`: `attori_comando`.
- `Betfair/stream/backtest/porta_banco.py`, `Betfair/stream/backtest/trasporto_rapido.py`,
  `Betfair/stream/tests/test_strada_unica_banco_2026_09_25.py` (14 scenari, R10 accettato).
- `frontend/src/lib/live.ts`, `frontend/src/components/live/LiveMatchCard.tsx`.
- Nuovi: vedi l'intestazione.
- `live_order_worker.py` NON toccato: la zona di `:628-638` è invariata; il rifiuto resta
  come ultima barriera.
