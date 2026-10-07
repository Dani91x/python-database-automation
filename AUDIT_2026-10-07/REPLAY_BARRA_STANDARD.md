# Match Replay: la coerenza barra / simboli / tabellone e' uno STANDARD per tutte le partite (07/10/2026)

Ordine dell'utente (07/10, testuale): "NON SOLO SULLE DUE PARTITE, DEVE ESSERE UNO STANDARD PER TUTTE QUELLE
PRESENTI E QUELLE FUTURE." Delegato in worktree cloud, NON committato (il worktree e' stato portato in avanti,
senza commit nuovi, al commit 94af2eb che contiene il controllo di stamattina `REPLAY_BARRA_SIMBOLI.md`).
Perimetro rispettato: `MatchReplay.tsx`, `lib/replayBot.ts`, `BotOrdersPanel.tsx`, `backtest/**`, `scalper/**`
e i file tennis NON toccati. Nessuna strategia, nessun bot, nessuna decisione di trading.

## 0. Esito in breve

- **Verificatore puro** `lib/replayVerificaBarra.ts` (parte generica, riusabile) + `lib/replayVerificaBarraCalcio.ts`
  (gol, cartellini, angoli, tabellone, motore opportunita'): dati di una partita -> elenco di INCOERENZE con codice,
  passo, istante, minuto e spiegazione per il trader. 36 codici. Usa le STESSE funzioni della pagina
  (`timelineEventMarkers`, `punteggioAlTs`, `buildSnapshots`) e oracoli scritti dalla regola con codice diverso:
  se la pagina sbaglia, il verificatore diventa rosso (provato, par. 5).
- **Test su TUTTE le registrazioni**, presenti e future: `replayVerificaBarra.partite.test.ts` scopre da solo ogni
  cartella di `registrazioni_banco/<event>/` (nessun elenco a mano). Sulle due registrazioni del repo: **0 incoerenze**
  (solo note dichiarate: i buchi della registrazione, 5 e 2). Una registrazione nuova senza la sua fixture fa cadere il
  test di contratto **con il comando da lanciare** (provato con una cartella finta, par. 5.3).
- **Le fixture si rigenerano dal raw** con un comando: `python3 tools/replay_barra_fixture.py <event>` (curator vero,
  punteggi, timeline, campionamento del server). **Provato: rigenerando dal raw le due partite si ottengono frame,
  punteggi e timeline IDENTICI a quelli del controllo di stamattina** (`event`, `mo`, `frames`, `score_timeline`
  uguali, par. 3.1): e' lo stesso dato, ora riproducibile da chiunque.
- **Strumento per il database** `frontend/scripts/verifica_barra_replay.ts` (`npx vite-node`, nessuna installazione):
  sola lettura garantita dal codice, referto per partita e riepilogo, codice di uscita. Provato **davvero** (lo script
  lanciato, con il client vero di supabase-js) contro un finto PostgREST su localhost dalle identiche chiavi e tipi
  delle RPC. Comando esatto per l'agente col DB al par. 6.
- **Avviso nella pagina** per le partite future: `components/replay/AvvisoCoerenzaBarra.tsx` + patch (2 righe) per
  `MatchReplay.tsx` che il coordinatore applica (par. 7).
- **Un difetto REALE nuovo trovato dal verificatore e corretto** (con test rosso prima): fra due righe del punteggio
  il conteggio di gol, cartellini o angoli puo' saltare di 2 o piu' (due angoli fra un poll e l'altro), la barra
  disegnava UN solo simbolo per riga: i simboli non contavano quanto il punteggio. Ora un simbolo per ogni unita'
  (`replayTimelineEvents.ts`, par. 2). Non si manifesta sulle due partite registrate (nessun salto > 1), si
  manifesta sul replay sintetico e puo' capitare in qualunque partita futura.
- **Tennis**: la parte generica e' separata e riusabile (par. 8).

## 1. Come si usa lo standard (per ogni partita nuova)

1. Si aggiunge la registrazione in `registrazioni_banco/<event>/` (`<event>.raw.jsonl.gz`, `<event>.scores.jsonl.gz`,
   `<event>.timeline.jsonl`).
2. `python3 tools/replay_barra_fixture.py <event>` (o `--tutte`; `--verifica` non scrive e dice se manca o e' diversa).
   Scrive `frontend/src/lib/__fixtures__/replay_barra_<event>.json` (< 150 KB).
3. `npx vitest run src/lib/replayVerificaBarra.partite.test.ts` (da `frontend/`): la partita e' entrata da sola;
   0 incoerenze = coerente. Se la registrazione cambia, la fixture risulta VECCHIA (impronta sha256) e il test cade.
4. Per le partite gia' nel database: `scripts/verifica_barra_replay.ts` (par. 6). Per quelle future: l'avviso nella pagina.

## 2. Causa radice del difetto trovato (con prova)

`frontend/src/lib/replayTimelineEvents.ts`, `timelineEventMarkers`, rami "deriva dai delta" (gol senza timeline,
cartellini, angoli) e "angoli con timeline discreta": `if (ch > pCH) add(...)` aggiungeva UN simbolo per riga anche se
`ch - pCH >= 2`. Prova: `replayTimelineEvents.salti.test.ts`, 5 test ROSSI prima della correzione (angoli da 1 a 3 =
2 simboli invece di 3; gialli +2; gol 0-0 -> 2-0; angoli 0 -> 2 alla prima riga; fonte in ritardo che scende e risale),
VERDI dopo. Il verificatore lo segnala come `ANGOLI_DIVERSI` / `CARTELLINI_DIVERSI` ("il punteggio ne conta 3, sulla
barra ci sono 1 simboli"). Correzione: helper `unita(salto, f)` che ripete `f` per ogni unita' del salto; nessun altro
cambio di logica. Le due partite registrate e i test del commit 94af2eb restano verdi (nessun salto > 1 nei dati).

Osservazione (NON cambiata): con baseline 0, una registrazione che inizia a partita in corso e la cui prima riga del
punteggio ha gia' N angoli disegna N simboli a quel primo istante (prima ne disegnava 1). I fatti prima della
registrazione non hanno un istante sulla barra; il verificatore li tratta coerentemente (atteso = conteggio massimo
meno quello gia' raggiunto PRIMA dell'inizio della registrazione), ma se la prima riga e' DENTRO la registrazione
il conteggio iniziale compare tutto insieme. Da decidere se serve (par. 11).

## 3. Cosa c'e' (file)

### 3.1 Generatore delle fixture (Python, riproducibile)
- `tools/replay_barra_fixture.py` (NUOVO): raw dello stream -> libro per mercato (betfairlightweight come il recorder,
  depth 3) -> `Betfair.stream.curator.curate_event` VERO (cadenza 10 s, minuto dalla mappa del punteggio come
  `uploader.py`) -> estremi come `get_replay_meta` -> campionamento del server (`get_replay_frames`: DISTINCT ON
  mercato e bucket, ordine per mercato e bucket, LIMIT con dimezzamento della finestra) con bucket e finestre come
  `live.ts::fetchReplayChunked` -> righe punteggio + righe-evento come `uploader.py`. NON importa `config_stream`
  (carica il `.env` vero). Solo lettura dei file di registrazione, nessuna rete, nessun DB. Da ~10 s a ~60 s a partita (la piu' lunga ha 81.000 messaggi).
- `tools/test_replay_barra_fixture.py` (NUOVO, pytest): fixture presente e aggiornata per ogni registrazione;
  **riproducibile dal raw (stessi byte)**; il campionamento del server su dati sintetici (un frame per mercato e bucket,
  il primo, ordine, bucket adattivi con i limiti 30-300 s / 2-60 s, pre-match al massimo 4 h, estremi come `meta`).
- Fixture: `replay_barra_35797769.json` (144 KB) e `replay_barra_35760084.json` (110 KB) RIGENERATE: `event`, `mo`,
  `frames`, `score_timeline` **identici** a quelli del commit 94af2eb (confronto chiave per chiave); aggiunte le chiavi
  `meta` (ts_min, ts_max, inplay_from_ts, n_mercati, bucket usati) e `sorgente` (sha256 dei file di registrazione).

### 3.2 Verificatore (TypeScript)
- `frontend/src/lib/replayVerificaBarra.ts` (NUOVO): tipi (`Rilievo`, `EsitoVerificaBarra`, `BarraDaVerificare`),
  COSTRUTTORI della barra (`passiBarra`, `kickoffTsDaFrame`, `kickoffIndexSuPassi`, `sospesiPerPasso`,
  `idMercatiSospensione`: copie fedeli dei blocchi in linea di `MatchReplay.tsx`; la patch B del par. 7 fa chiamare questi
  alla pagina e la logica diventa UNA) e CONTROLLI GENERICI (`verificaBarraGenerica`).
- `frontend/src/lib/replayVerificaBarraCalcio.ts` (NUOVO): `verificaBarraReplayCalcio(replay, {estremi, snapshots,
  controllaMotore, funzioni})` = barra costruita come la pagina + generico + controlli di calcio. `funzioni` permette di
  sostituire le funzioni della pagina con versioni difettose (solo per falsificare).
- `frontend/src/lib/replayVerificaBarraTesto.ts` (NUOVO): referto in testo (comune a calcio e tennis).
- `frontend/src/lib/replayVerificaBarraDb.ts` (NUOVO): caricamento dal database con le funzioni VERE della pagina
  (`fetchReplayList`, `fetchReplayChunked`) + `get_replay_meta` per gli estremi; `blindaSolaLettura`; riepilogo.
- `frontend/scripts/verifica_barra_replay.ts` (NUOVO): lo strumento da riga di comando.
- `frontend/src/components/replay/AvvisoCoerenzaBarra.tsx` (NUOVO): l'avviso.

Codici (gravita': E errore, A avviso = rosso; n nota = dichiarata, non e' incoerenza):
Generici: NESSUN_FRAME E; TS_NON_VALIDO E; TS_ORDINE_STRINGHE E (orari in formati diversi: la pagina ordina come testo);
PASSI_NON_ORDINATI E; ESTREMO_INIZIO E; ESTREMO_FINE E; FRAME_FUORI_ESTREMI E; SIMBOLO_FUORI_BARRA E;
SIMBOLO_FUORI_REGISTRAZIONE E (D3); SIMBOLO_NON_ORDINATO E; SIMBOLO_PRIMA_DELL_ISTANTE E; SIMBOLO_POSIZIONE E;
KICKOFF_FUORI_POSTO E; KICKOFF_DIVERSO_DA_META E; KICKOFF_DISCORDANTE A; KICKOFF_IN_RITARDO A; SOSPENSIONE_LUNGHEZZA E;
SOSPENSIONE_DISCORDANTE E; SOSPENSIONE_FUORI_ESTREMI E; SOSPENSIONE_NON_VISIBILE n; BUCO_REGISTRAZIONE n;
INIZIO_IN_CORSO n; FUNZIONE_PAGINA_ERRORE E (una funzione della pagina lancia un errore su questa partita).
Calcio: TABELLONE_DIVERSO_DAL_FEED E (D1); TABELLONE_FINALE E (D1); TABELLONE_SCENDE E (le due fonti discordanti fanno
andare avanti e indietro il tabellone); TABELLONE_CORREZIONE_FEED n (la STESSA fonte corregge il punteggio = VAR, distinta);
GOL_SENZA_SIMBOLO E (D4); SIMBOLO_GOL_SENZA_AUMENTO E; GOL_SQUADRA_DIVERSA A; GOL_ANNULLATO n (simbolo senza aumento ma
punteggio corretto subito dopo = VAR); CARTELLINI_DIVERSI A/E; ANGOLI_DIVERSI E; MOTORE_PUNTEGGIO E (D2);
PUNTEGGIO_ASSENTE n; CONTEGGI_ASSENTI n.
Regola per i fatti fuori registrazione: non si pretende un simbolo (voluto, D3) e i conteggi attesi sono quelli
raggiunti DENTRO la registrazione.

### 3.3 Test e fixture di supporto (tutti NUOVI salvo dove detto)
- `replayVerificaBarra.partite.test.ts` (17): contratto fixture, 0 incoerenze, falsificazione D1-D4, per ogni registrazione.
- `replayVerificaBarra.test.ts` (41): ogni codice rosso con un difetto introdotto (barra vera + replay sintetico con le
  stesse chiavi e tipi del vero).
- `replayVerificaBarra.pagina.test.tsx` (2): monta la PAGINA VERA su ogni registrazione e confronta con il verificatore
  (passi, apertura, lineetta del calcio d'inizio, sospensioni, simboli, tabellone a un campione di passi).
- `replayVerificaBarra.avvisoPagina.test.tsx` (4): l'avviso nella pagina. **2 ROSSI ATTESI finche' la patch non e' applicata.**
- `replayVerificaBarraDb.test.ts` (13) e `replayVerificaBarraScript.test.ts` (4): lo strumento sul database (par. 6).
- `components/replay/AvvisoCoerenzaBarra.test.tsx` (10).
- `replayTimelineEvents.salti.test.ts` (6): il difetto del par. 2.
- `__fixtures__/replayBarraTutte.ts` (scoperta delle registrazioni, impronte), `replayBarraConversione.ts`
  (conversione fixture -> ReplayData, STACCATA da `replayBarra.ts` che ora la ri-esporta: i test esistenti non cambiano),
  `replayBarraMutanti.ts` (funzioni difettose D1/D2/D3+D4), `replayTimelineEventsLegacy.ts` (copia DIFETTOSA di
  proposito di `replayTimelineEvents.ts` prima di 94af2eb, solo per falsificare), `replayBarraDbFinto.ts` (finto delle RPC
  + finto PostgREST su localhost).

### 3.4 File TOCCATI (esistenti)
- `frontend/src/lib/replayTimelineEvents.ts`: helper `unita` e 8 righe che lo usano (par. 2). Intestazione aggiornata.
- `frontend/src/lib/__fixtures__/replayBarra.ts`: la conversione e' stata spostata in `replayBarraConversione.ts` e
  ri-esportata (stessi nomi, stessi tipi).
- `frontend/src/lib/__fixtures__/replay_barra_35797769.json` e `..._35760084.json`: rigenerati (solo chiavi aggiunte).

## 4. Test: comandi e numeri

Dalla cartella `frontend/` (worktree cloud, carico variabile; altri processi in corso sulla macchina):
- `npx tsc -p tsconfig.app.json --noEmit` -> **0 errori** (nessun `any`, nessun `@ts-ignore`). Lo script
  `scripts/verifica_barra_replay.ts` (fuori da `src`) controllato a parte con un tsconfig temporaneo: 0 errori.
- `npx vitest run src/lib/replayVerificaBarra src/lib/replayTimelineEvents src/lib/replayBarra src/components/replay
  src/lib/trainingLadder.replay.test.tsx src/lib/opportunities` -> 28 file, **346 test: 344 verdi, 2 ROSSI ATTESI**
  (`replayVerificaBarra.avvisoPagina.test.tsx`, verdi con la patch: provato su una copia della pagina, 26/26 con le
  partite, il punteggio, l'aderenza e l'avviso), 53 s con la macchina libera (153 s con altri processi in corso).
  Nessuna regressione nei test del commit 94af2eb (`replayBarraSimboli` 12, `replayBarraPunteggio` 8,
  `replayTimelineEvents` 5 + 19, `TimelineSlider` 10, `opportunities/*`).
- Python: `python3 -m pytest tools/test_replay_barra_fixture.py -q -p no:cacheprovider` -> **9 passati in 68 s**
  (7 veloci + 2 rigenerazioni dal raw). `BARRA_FIXTURE_SALTA_RIGENERAZIONE=1` salta le 2 lente (0,1 s).
  `python3 tools/replay_barra_fixture.py --tutte --verifica` -> OK per entrambe (67 s).
- Tempo del replay del banco: non toccato (nessun replay del banco lanciato, nessun file di `backtest/`).

## 5. Falsificazioni

Metodo: mutazione nel codice, `vitest` sui test indicati, ripristino dalla copia e verifica con `cmp` + `grep -c MUTAZIONE`
= 0 (tutte le mutazioni sono state ripristinate: `git status` mostra solo i file elencati al par. 3). Script fuori dal repo
(`falsifica.py`, `falsifica2.py`, `falsifica_contratto.py` nello scratchpad). "Rossi" = test falliti con la mutazione
(senza mutazione: 0).

### 5.1 I quattro difetti di stamattina, rimessi uno a uno nel CODICE VERO
| Difetto | Mutazione | Rossi | Dove |
|---|---|---|---|
| D1 tabellone a 0-0 dopo le righe-evento | `punteggioAlTs` come il vecchio codice | 9 | partite (entrambe), unitari |
| D2 motore opportunita' | `snapshot.ts` legge l'ultima riga di qualunque tipo | 9 | partite (entrambe), unitari |
| D3 simboli fuori registrazione (inizio) | tolta la guardia "prima del primo frame" | 3 | partite: variante "inizia a partita in corso", entrambe + unitari |
| D3 simboli fuori registrazione (fine) | tolta la guardia "dopo l'ultimo frame" | 2 | partite: variante "finisce prima", entrambe |
| D4 gol perso dalla timeline | i gol del punteggio non si disegnano | 3 | partite: variante "senza Goal discreto", entrambe + sintetico |

In piu' i test di `partite.test.ts` rimettono gli STESSI difetti come funzioni difettose passate al verificatore
(`replayBarraMutanti.ts`, `replayTimelineEventsLegacy.ts` = la funzione dei simboli com'era prima di 94af2eb): D1 rosso
su ENTRAMBE le partite con `TABELLONE_DIVERSO_DAL_FEED` e `TABELLONE_FINALE` (a fine replay "0 - 0" invece di 2-1 e 4-0),
D2 `MOTORE_PUNTEGGIO` (196 e 133 bucket sbagliati), D3 `SIMBOLO_FUORI_REGISTRAZIONE` (10-18 incoerenze per partita: simboli incollati agli
estremi), D4 `GOL_SENZA_SIMBOLO`. Se una partita futura non ha gol o non ha righe-evento dopo un gol, il difetto
non si applica e il test lo dichiara (`d1Applicabile`) invece di fingere.

### 5.2 Il verificatore stesso e le funzioni della pagina
| Sigla | Mutazione | Rossi |
|---|---|---|
| V1 | oracolo di posizione `>=` -> `>` | 8 |
| V2 | tolto SIMBOLO_FUORI_REGISTRAZIONE | 5 |
| V3 | tolto il confronto tabellone-feed per passo | 3 |
| V4 | tolto il controllo del motore | 3 |
| V5 | gol senza simbolo non segnalato | 3 |
| V6 | sospensioni: confronto con lo stato del mercato tolto | 1 |
| V7 | calcio d'inizio: indice non confrontato | 1 |
| V8 | estremo di fine barra non confrontato (PRIMA 0 rossi: era coperto solo dal confronto con gli estremi del server; aggiunto il caso senza estremi, ora rosso) | 1 |
| V9 | due fonti discordanti trattate come correzione VAR | 2 |
| V10 | cartellini e angoli non confrontati | 2 |
| P4 | `stepIndexFor` +1 (simboli un passo dopo) | 15 |
| P5 | salto di piu' unita': un simbolo per riga | 5 |
| B1 | passi della barra a bucket da 20 s | 2 (pagina vera, 2 partite) |
| B2 | segmenti di sospensione: stato mai riconosciuto | 2 |
| B3 | indice del calcio d'inizio +1 | 2 |
| B4 | calcio d'inizio = primo frame invece del primo in gioco | 2 |

### 5.3 Contratto "tutte le registrazioni, presenti e future"
- Fixture MANCANTE di una partita presente: 3 rossi, con il messaggio `manca la fixture ... Generala (dalla radice del
  repository): python3 tools/replay_barra_fixture.py 35760084`.
- Fixture VECCHIA (impronta diversa): rosso, `la registrazione 35760084 e' cambiata dopo la generazione della fixture:
  rigenerala con ...`.
- **Registrazione NUOVA scoperta da sola**: creata una cartella finta `registrazioni_banco/99999999/` (poi rimossa) SENZA
  toccare il test: 3 rossi con `manca la fixture ... python3 tools/replay_barra_fixture.py 99999999`; gli altri test
  continuano a girare sulle partite che hanno la fixture (nessun crash del file).

### 5.4 Strumento DB, script, avviso, generatore Python
| Sigla | Mutazione | Rossi |
|---|---|---|
| D1 | riepilogo: `tutteOk` sempre vero | 3 |
| D2 | blindatura: ogni RPC permessa | 2 |
| D3 | blindatura: `from()` permesso | 2 |
| D4 | filtro `--evento` ignorato | 1 |
| D5 | una partita che non si carica sparisce dal conto | 1 |
| S1 | script: codice di uscita sempre 0 | 1 |
| S2 | script: credenziali mancanti non fermano | 1 |
| C1 | avviso: compare sempre | 3 |
| C2 | avviso: non compare mai | 6 |
| C3 | avviso: elenco senza limite | 1 |
| C4 | avviso: errore del verificatore non catturato (PRIMA 0 rossi: il test "dati malformati" non faceva lanciare nulla; sostituito con un frame nullo, ora rosso) | 1 |
| G1 | generatore: bucket in gioco senza il minimo di 2 s | 2 |
| G2 | generatore: DISTINCT ON tiene l'ULTIMO frame del bucket | 1 |
| G3 | generatore: pre-match non limitato a 4 ore | 2 |

## 6. Strumento per il database: COMANDO ESATTO per l'agente CON accesso al DB

Da `frontend/` (Node >= 20.12 per `--env-file`; vite-node e' gia' in `node_modules`, nessuna installazione):

```
cd frontend
npx vite-node scripts/verifica_barra_replay.ts --env-file ../.env
```

Il `.env` della radice deve avere `SUPABASE_URL` (o `VITE_SUPABASE_URL`) e `SUPABASE_SERVICE_ROLE_KEY` (nomi gia' usati
dai tool Python; non verificato qui che il `.env` vero li abbia). In alternativa le stesse variabili impostate nella shell
(PowerShell: `$env:SUPABASE_URL="..."; $env:SUPABASE_SERVICE_ROLE_KEY="..."`), oppure con la chiave anonima del frontend:
`VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VERIFICA_EMAIL`, `VERIFICA_PASSWORD` (le RPC sono concesse a
`authenticated` e `service_role`). **Le credenziali vivono solo nell'ambiente: nessun file le contiene.**
Per spiegare il rilancio: vite-node fissa `import.meta.env` all'avvio, quindi se le variabili non sono gia' quelle del
frontend lo script si rilancia UNA volta con l'ambiente giusto (provato).

Opzioni: `--evento <id>` (ripetibile), `--limite N` (1-500, default 500 = il massimo di `list_replays`; se ne torna
esattamente N lo script avverte che potrebbero essercene altre), `--solo-incoerenti`, `--senza-note`, `--json`.
Codice di uscita: 0 tutte coerenti, 1 almeno una incoerente o non verificabile, 2 uso errato o credenziali mancanti.

**Sola lettura, garantita dal codice**: `blindaSolaLettura` sostituisce `supabase.rpc` e `supabase.from`: solo
`list_replays`, `get_replay_meta`, `get_replay_frames` e `get_replay` (il ripiego di `fetchReplayChunked`) passano; ogni
altra RPC o accesso a una tabella lancia un errore. Provato: test unitari (D2/D3 sopra) e, nello script lanciato, il
finto server registra le richieste: **tutte** `POST /rest/v1/rpc/{list_replays|get_replay_meta|get_replay_frames}`.
I sorgenti non contengono `.insert/.update/.delete/.upsert` ne' `.from('...')` (test statico).

Cosa fa: `list_replays(p_limit)`; per ogni partita `get_replay_meta` (estremi) + `fetchReplayChunked` (la funzione DELLA
PAGINA: finestre da 10 minuti, bucket adattivi, `get_replay_frames` con `p_event_id, p_from_ts, p_to_ts, p_bucket_sec,
p_max_rows`); poi il verificatore. Le partite si fanno in sequenza (un'RPC alla volta come la pagina).

Prova qui, senza DB (finto delle RPC dalle chiavi e dai tipi del vero: `migrations/live_stream_rpc.sql`,
`live_stream_rpc_chunked.sql`, `lib/live.ts`; orari come li serializza Postgres in jsonb, microsecondi senza zeri finali):
```
[1/2] OK     35797769 Spain - Belgium (2026-07-10): 0 incoerenze, 5 note | passi 1122, frame 1360, simboli [goal 3, corner 6, yellow 4], righe punteggio 116, righe evento 11, buchi 5
  [nota  ] BUCO_REGISTRAZIONE (passo 1120, 21:05:06 UTC, 97'): Buco della registrazione di 3 min 58 s ...
[2/2] OK     35760084 FK Liepaja - Ogre United (2026-06-30): 0 incoerenze, 2 note | passi 861, frame 1107, simboli [corner 15, goal 4, yellow 3], ...
RIEPILOGO: 2 partite verificate: 2 OK, 0 con incoerenze, 0 non verificabili (errore di caricamento).
Tempo totale: 0.4 s. Sola lettura: nessuna scrittura sul database.            [uscita 0]
```
e con un difetto nei dati (una seconda fonte che rimette 0-0 dopo il primo gol):
```
[1/2] INCOERENTE 35797769 ...: 1 incoerenze ...
  [ERRORE] TABELLONE_SCENDE (passo 624, 19:30:13 UTC, 29'): Il tabellone scende senza una correzione del feed una volta: le due fonti non concordano (es. "betfair" 1 - 0 alle 19:30:08 UTC, poi "api_football" 0 - 0 alle 19:30:13 UTC). ...
RIEPILOGO: 2 partite verificate: 0 OK, 2 con incoerenze, 0 non verificabili ...            [uscita 1]
```
Limite di questa prova: le RPC vere possono rispondere con forme che qui non ho (es. `selections` come oggetto invece
che array, visto in `scripts/scalper_avgdown/run.ts`): se una funzione della pagina lancia un errore su una partita, il
verificatore lo riporta come `FUNZIONE_PAGINA_ERRORE` e lo script come partita non verificabile, senza fermarsi.

## 7. Avviso nella pagina: patch per `MatchReplay.tsx` (la applica il coordinatore)

Due file, entrambi verificati con `git apply --check` sul HEAD (`94af2eb`):
- `AUDIT_2026-10-07/REPLAY_BARRA_STANDARD_pagina_minima.patch` (SOLO l'avviso, 2 righe):
```diff
 import { punteggioAlTs, timelineEventMarkers } from '@/lib/replayTimelineEvents';
+import { AvvisoCoerenzaBarra } from '@/components/replay/AvvisoCoerenzaBarra';
 ...
                             />
                         </Card>

+                        {/* avviso discreto: barra, simboli e tabellone non tornano con i dati registrati */}
+                        <AvvisoCoerenzaBarra replay={replay} snapshots={snapshots} />
+
                         {/* menu SOTTO LA TIMELINE: ...
```
- `AUDIT_2026-10-07/REPLAY_BARRA_STANDARD_pagina.patch` (avviso + **pagina e verificatore con UN solo codice**): sostituisce i
  quattro blocchi in linea (`kickoffTs`, `timeline`, `kickoffIndex`, `suspended`: -40 righe) con le chiamate a
  `kickoffTsDaFrame`, `passiBarra`, `kickoffIndexSuPassi`, `sospesiPerPasso`. Consigliata: da allora il verificatore
  fallisce se la pagina sbaglia per costruzione, non solo per il test di aderenza.
Provato su una COPIA della pagina (poi cancellata) con la patch completa: i test della pagina vera `replayBarraSimboli` 12,
`replayBarraPunteggio` 8, `replayVerificaBarra.pagina` 2 e `replayVerificaBarra.avvisoPagina` 4 = **26/26 verdi**; con la
pagina attuale i primi 22 sono verdi e `avvisoPagina` ha i 2 rossi attesi ("barra che non torna: la pagina mostra
l'avviso"). L'avviso e' un `<details>` ambra (stile del riquadro "Applica bot" della pagina) chiuso di default, con codice,
passo, ora, minuto e spiegazione; non compare se tutto e' coerente; non rompe mai la pagina (errore del verificatore =
nessun avviso + un `console.warn`). Passa gli `snapshots` gia' calcolati dalla pagina: nessun secondo `buildSnapshots`.
`MatchReplay.tsx` e' di un altro delegato che ci lavora: se la patch non si applica pulita, le righe da ritoccare sono
quelle indicate (ancore: l'import di `replayTimelineEvents` e il `</Card>` dopo `<TimelineSlider ... />`).

## 8. Come il tennis riusera' il verificatore

La parte generica NON sa nulla di sport. Il replay tennis (altro delegato) deve:
1. costruire i suoi passi, kickoff e sospensioni con gli STESSI costruttori se i suoi frame hanno la forma di `Frame`
   (`passiBarra`, `kickoffTsDaFrame`, `kickoffIndexSuPassi`, `sospesiPerPasso`) oppure con i suoi, e passare i suoi
   simboli (break, set, game) come `SimboloBarra[]` (`ts`, `pctLeft`, `kind`, `team`, `minute`);
2. chiamare `verificaBarraGenerica({ passi, simboli, frames, kickoffTs, kickoffIndex, sospesi, mercatiSospensione,
   estremi, inizioDichiarato })`: estremi, ordine dei ts, simboli fuori barra o fuori registrazione, posizione e comparsa
   dei simboli, calcio d'inizio, sospensioni, buchi: tutto riusato, con gli oracoli gia' falsificati;
3. aggiungere i SUOI controlli di dominio (punteggio di game/set/partita monotono, break e set senza simbolo e simboli
   senza cambio di punteggio, sul modello di `verificaCalcio` in `replayVerificaBarraCalcio.ts`) producendo `Rilievo` con
   `creaRilievo(codice, gravita, spiegazione, { ambito: 'tennis', ... })` (l'ambito `'tennis'` e' gia' nel tipo; i codici
   nuovi si aggiungono a `CodiceRilievo`) e componendo l'esito con `esitoDaRilievi`;
4. riusare lo strumento DB passando `verificaPartite(fonte, { verifica: verificaBarraReplayTennis })` (parametro
   `verifica`, provato nel test) e il referto `formattaReferto`;
5. riusare l'avviso: `<AvvisoCoerenzaBarra replay={...} verifica={verificaBarraReplayTennis} />` (prop `verifica`,
   provata nel test con un verificatore di un altro sport);
6. entrare nel test su tutte le registrazioni con un test gemello di `replayVerificaBarra.partite.test.ts` che scopre da
   solo le registrazioni tennis (generatore Python da estendere ai mercati tennis: oggi `replay_barra_fixture.py` cerca il
   MATCH_ODDS e i punteggi del calcio).
Non ho toccato nessun file tennis.

## 9. Parita' paper/live

Non applicabile: nessun bot, nessun ramo paper/live, nessuna strategia toccata. Il lavoro riguarda solo la
visualizzazione di Match Replay e strumenti di verifica.

## 10. Cosa NON ho fatto / NON ho potuto verificare

- NON applicata la patch a `MatchReplay.tsx` (file di un altro delegato): finche' non e' applicata, l'avviso non e' nella
  pagina e 2 test (`avvisoPagina`) sono rossi di proposito.
- NON eseguito lo strumento sul database vero (qui non c'e'): provato sul finto delle RPC e sul client vero di supabase-js
  su localhost. Non verificato: che il `.env` vero abbia i nomi delle variabili indicati; che `list_replays` e le RPC
  vere restituiscano forme diverse da quelle documentate nelle migrazioni; il tempo reale su centinaia di partite
  (ogni partita = 1 + ~20 richieste a finestre di 10 minuti; il motore opportunita' si rifa' per partita).
- NON verificato in un browser o nell'app desktop (solo jsdom): aspetto reale dell'avviso (`<details>` ambra), clic.
- NON rieseguita la build (`npm run build`, ordine del CLAUDE.md dopo modifiche a `frontend/src`): va fatta dal
  coordinatore quando l'app e' chiusa, dopo l'applicazione della patch.
- Il campionamento del server e' replicato in Python (stesso criterio di stamattina, identico ai dati committati): lo
  scarto con il server vero, in particolare l'ordine dei mercati (`ORDER BY market_id` con la collation del database) che
  decide quale frame sta in testa a un bucket da 10 s, non e' verificabile qui. Incide al piu' di un bucket sul ts di un passo.
- Le registrazioni sono solo due, entrambe senza rossi, senza correzioni VAR, senza tempi supplementari o rigori, senza
  salti del conteggio > 1: quei rami sono provati sul replay sintetico, non su una partita vera.
- Il verificatore e' di CALCIO (gol, cartellini, angoli): nessun controllo sul tennis.
- Non toccati `CRONOSTORIA.md` e `CLAUDE.md` (del coordinatore). Il worktree e' stato portato in avanti al commit 94af2eb
  con un fast-forward (nessun commit mio).

## 11. Decisioni per l'utente

Nessuna che tocchi una strategia. Due scelte di visualizzazione, solo se le vuoi:
- Registrazione che inizia a partita in corso con angoli o cartellini gia' presenti alla prima riga del punteggio: oggi
  compaiono tutti insieme a quel primo istante (par. 2). Proposta: lasciare cosi'; in alternativa non disegnarli se la
  prima riga e' entro 2 minuti dall'inizio della registrazione.
- L'avviso nella pagina e' chiuso di default e mostra anche gli "avvisi" (dati del feed discordanti, es. cartellini
  diversi dai conteggi), non solo gli errori della barra. Proposta: lasciare cosi'.

## 12. Da controllare dal vivo al prossimo avvio dell'app (dopo la patch e la build)

Aprire Match Replay su 35797769 e su 35760084: **nessun avviso** sotto la barra (sono coerenti). Per vedere l'avviso serve
una partita con una barra che non torna: l'agente col DB lancia lo script del par. 6 su tutte le partite caricate e porta
all'utente l'elenco; una partita che risulta INCOERENTE nello script deve mostrare l'avviso, con gli stessi codici, aprendola
nella pagina.
