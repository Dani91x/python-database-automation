# CANTIERE 14 - Replay tennis: nome «Marcelo Tomas Barrios V» troncato (08/10/2026)

Delegato di costruzione. Worktree `/home/user/python-database-automation/.claude/worktrees/agent-ac4c6d5023a08ad94`,
ramo `worktree-agent-ac4c6d5023a08ad94`, lavoro NON committato. Punto di partenza: `b5547eb`
(il worktree nasceva da `8226d76`, 68 commit indietro, con la cartella `AUDIT_2026-10-08` assente: portato a
`b5547eb` con `git merge --ff-only b5547eb`, nessun lavoro perso, ramo vuoto).

Ambiente: container cloud, 4 CPU CONDIVISE con altri cantieri (load average 12-31 durante i miei lanci): TUTTI i tempi
sotto sono gonfiati dal carico e vanno letti come ordine di grandezza. Registrazioni tennis e DB di produzione NON
disponibili qui: vedi «Da rieseguire sul PC».

## 1. Cosa ho cambiato (file:riga) e perche'

Causa: il flusso Betfair non porta i nomi dei runner; senza `_names.json` ne' catalogo nel DB il convertitore ripiega sul
nome dell'IPS (TRONCATO) e la pagina lo mostrava come se fosse intero. Tre interventi, come da specifica.

### 1.1 Registratore: `_names.json` completo a ogni REC
- `Betfair/stream/tennis_live/tennis_recorder.py`: `nomi_dal_catalogo` (r.73), `scrivi_nomi_catalogo` (r.98),
  `TennisRawTee._scrivi_nomi` e la chiamata in `enable()` (r.223-225).
- Cosa scrive, nella cartella del giorno accanto al raw (`<root>/<YYYYMMDD>/_names.json`, la stessa che
  `nomi_da_cache`/`replay_bot`/`applica_bot` leggono):
  - chiave PIATTA di sempre `{event_id: {selection_id: nome}}` = Match Odds (formato dei grid runner, di `replay_bot.catalogo_dichiarato`,
    di `lab_grid_score.build_names_cache`, del banco);
  - in piu' la chiave RISERVATA `"_mercati": {event_id: {market_id: {selection_id: nome}}}` con TUTTI i mercati registrati
    (Match Odds, Set Betting, Total Games...), dal catalogo del runner (`market_meta[event]`: `selection_names` e
    `mercati_registrati`, i formati veri di `_resolve_market` e `catalogo_mercati_evento`).
- Non sovrascrive: voce piatta di una partita gia' presente = intatta; di un mercato gia' presente si aggiungono solo le selezioni
  mancanti; altre partite conservate; file illeggibile o non-oggetto = NON si tocca (warning); scrittura atomica (tmp + `os.replace`);
  mai un'eccezione verso il chiamante.
- Quando: a ogni `enable()` (il `record_flag_worker` lo richiama a ogni giro col catalogo piu' recente, quindi anche i mercati
  in piu' che arrivano dopo), ma scrive solo se il catalogo e' cambiato dall'ultima volta (firma), dopo un errore riprova non prima di 60 s,
  FUORI dal lock del tee (il tee dei messaggi non aspetta il disco).

**DEVIAZIONE DALLA LETTERA DELLA SPECIFICA (da portare all'utente).** La specifica dice «chiave `event_id` -> `market_id` ->
`selection_id` -> nome». Scritto cosi' nella chiave dell'evento ROMPEREBBE i lettori esistenti: `replay_bot.catalogo_dichiarato` fa
`int(sel)` su ogni chiave (un market_id `1.259...` e' scartato) e ne uscirebbe `{}`; `nomi_da_cache` darebbe nomi-spazzatura; il cantiere 6
(che passa il `_names.json` al banco tennis) non troverebbe i nomi delle partite nuove. Ho tenuto la forma piatta per il Match Odds
(compatibile) e messo la struttura evento->mercato->selezione sotto `_mercati`. Stessa informazione, nello stesso file, nessun lettore
rotto. Se si preferisce la forma letterale, basta cambiare i lettori: ma e' una decisione da prendere insieme al cantiere 6.

### 1.2 Convertitore: da dove viene ogni nome
- `Betfair/stream/tennis_replay/convertitore.py`: `selezioni_mercato` (r.396) ora aggiunge `name_source` a ogni selezione
  (`catalogo` | `marketdef` | `ips` | `id`), con ESATTAMENTE la stessa catena di prima (nomi del chiamante -> `name` della
  marketDefinition -> IPS per sortPriority sul Match Odds -> `#id`); `converti_evento` (r.~520-568) scrive in `diagnostica["nomi_fonte"]`
  la fonte dei due giocatori (`catalogo`/`marketdef`/`evento`/`ips`; anagrafica dal chiamante = `catalogo`); `nomi_da_cache` (r.574) legge anche
  `_mercati` (una chiave per mercato, la `"*"` piatta resta) e ignora valori che non sono stringhe (prima stringificava anche un dict);
  `rango_selezione` / `migliora_selezioni` / `RANGO_NOME_FONTE` (r.75): catalogo 3 > marketdef/evento 2 > ips 1 > id 0 (un nome gia' nel DB senza fonte = rango 1).
- Nessuna colonna nuova: `name_source` vive nel jsonb `selections`, `nomi_fonte` nel jsonb `diagnostica`.

### 1.3 Importatore e caricamento: ordine delle fonti, reimport che migliora
- `Betfair/stream/tennis_replay/importa.py`: ordine finale `--nomi` / `_names.json` (per-mercato `_mercati` e piatto) / catalogo nel DB / IPS / `#id`.
  Nuovo: `_nomi_dalle_tabelle_live` (r.82): se il Match Odds NON e' in `tennis_markets` (caso 35790089) legge i nomi che il runner ha pubblicato in
  `tennis_live_now.state.markets[].selections` e `tennis_live_ladder.ladder.selections` (SOLA LETTURA, formati di `_now_selections`/`build_ladder_payload`);
  se `tennis_markets` ha gia' il Match Odds non fa nessuna query in piu' (comportamento di prima identico). Nuovo flag `--solo-nomi` (r.180).
  `betfair_market_*` NON usabile: e' del calcio (per `fixture_id` API-Football), non porta mai nomi tennis.
- `Betfair/stream/tennis_replay/caricamento.py`: `_nomi_migliori` (r.65) + `_carica` (r.138): al reimport un nome gia' nel DB cambia SOLO se la
  nuova fonte e' migliore (prima: un reimport da un PC senza `_names.json` faceva tornare il nome troncato); a parita' l'esito e' quello di prima
  (idempotente). `aggiorna_nomi` (r.105): reimport leggero per `--solo-nomi`, UPDATE delle sole `selections` dei mercati GIA' nel DB e dei due nomi dei
  giocatori + `diagnostica.nomi_fonte`; non tocca snapshot, punteggio, conteggi; non crea mercati; partita non caricata = non fa nulla.
- Limite dichiarato: `meta` dell'anagrafica (`tennis_live_follow.player1_name/2`) vale rango `catalogo`; il follow nasce da `tennis_markets`/feed (catalogo) ma ha
  il segnaposto «P1»/«P2» (`tennis_bot_service.py:198`) se manca il nome: e' un comportamento PREESISTENTE di `anagrafica_dal_db` che non ho toccato.

### 1.4 Pagina Replay Tennis (nessun cambio di layout)
- `frontend/src/lib/tennisReplay.ts`: tipo `TennisNomiFonte`, `NOTA_NOME_IPS` = «nome dall'IPS, troncato», `CLASSE_NOTA`, `notaNomeGiocatore`; campi opzionali
  `nomi_fonte` su `TennisReplayItem` e `TennisReplayEvent`, `name_source?` sulla selezione.
- `frontend/src/components/tennis-replay/TennisReplayList.tsx` e `frontend/src/pages/TennisReplay.tsx` (testata): `title` (tooltip) + sottolineatura punteggiata SOLO sul
  nome con fonte `ips`; nessuna fonte dichiarata = DOM identico a prima.
- `migrations/replay_tennis_fonte_nomi_2026-10-08.sql` (NON applicata, la applica l'utente): espone `nomi_fonte` in `list_replays_tennis` (elenco) e in
  `get_replay_tennis_meta` (`event.nomi_fonte`). Per le tabelle serve soltanto che la pagina lo legga: i dati sono gia' nel jsonb. ATTENZIONE: questa
  `list_replays_tennis` CONTIENE anche `market_types` (migrazione `replay_tennis_mercati_elenco_2026-10-08.sql`): va applicata DOPO o al posto di quella; riapplicare
  DOPO la sola migrazione dell'elenco fa sparire `nomi_fonte` (provato, vedi 3.5). Senza la migrazione la pagina e' come prima.
  La migrazione non era nominata dalla specifica: e' l'unico modo per mostrare il tooltip nell'elenco (la testata della partita aperta richiede comunque `get_replay_tennis_meta`).

## 2. Test aggiunti
- `Betfair/stream/tennis_live/tests/test_nomi_names_json_2026_10_08.py` (12 test): formato scritto, lettori VERI (`nomi_da_cache`, `replay_bot.catalogo_dichiarato`; il lettore del lab
  e' verificato per forma, `laboratorio/` non e' importabile da `Betfair/`), percorso intero raw -> `_names.json` -> import, non sovrascrittura, file illeggibile, firma/una sola scrittura,
  errore+60 s, scrittura fuori dal lock, `sync_record_flags`. Finti dai formati veri: `MarketCatalogue` di betfairlightweight, `tennis_runner._resolve_market` e
  `mercati_registrati.catalogo_mercati_evento` (codice vero).
- `Betfair/stream/tennis_replay/tests/test_nomi_fonte_2026_10_08.py` (26 test): fonti per selezione e per evento, `_names.json` esteso/junk, regola del nome migliore (pura), reimport sale/non scende,
  conteggi invariati, righe di prima senza fonte, `aggiorna_nomi` (non tocca snapshot/punteggio, non crea, non declassa), `main --solo-nomi` e `--solo-nomi --prova`,
  tabelle `tennis_live_*` con righe prodotte dal codice vero (`_now_selections`, `build_ladder_payload`), errore di lettura che non blocca.
- Frontend: `TennisReplayList.test.tsx` (+2), `TennisReplay.test.tsx` (+4, mock con `nomi_fonte` nelle due RPC).
- `AUDIT_2026-10-08/cantiere_14/verifica_migrazione_pg.py`: 21 controlli su un PostgreSQL 16 usa-e-getta (cluster temporaneo, fermato a fine script, nessun processo residuo).

## 3. Prove

### 3.1 Mutazioni (rosso con la modifica, ripristino con sha uguale, verde dopo) - dettaglio in `mutazioni_python.txt`, `mutazioni_python_i3.txt`, `mutazioni_frontend.txt`
| id | mutazione | rossi |
|---|---|---|
| M1 | il tee non scrive i nomi all'enable | 11 |
| M2 | sovrascrive la voce piatta gia' presente | 1 |
| M3 | sovrascrive le selezioni gia' scritte di un mercato | 1 |
| M4 | scrive solo il primo mercato | 5 |
| M5 | un `_names.json` illeggibile viene sovrascritto | 1 |
| M6 | scrittura non atomica (residuo .tmp) | 1 |
| M7 | riscrive a ogni giro (firma ignorata) | 2 |
| M8 | nessuna attesa di 60 s dopo errore | 1 |
| M9 | scrittura dei nomi dentro il lock del tee | 1 |
| C1 | nome IPS dichiarato `catalogo` | 5 |
| C2 | regola del nome migliore invertita | 5 |
| C3 | a parita' resta il vecchio | 1 |
| C4 | `nomi_da_cache` ignora `_mercati` | 4 |
| C5 | anagrafica del chiamante senza fonte `catalogo` | 1 |
| C6 | nomi giocatori riscritti sempre | 2 |
| C7 | selezioni riscritte sempre | 2 |
| C8 | `aggiorna_nomi` cancella gli snapshot | 2 |
| C9 | `aggiorna_nomi` aggiorna mercati non nel DB | 1 |
| C10 | `aggiorna_nomi` su partita non caricata procede | 1 |
| I1 | niente fallback tabelle `tennis_live_*` | 3 |
| I2 | tabelle live lette anche col Match Odds noto | 3 |
| I3 | segnaposto «?» accettato | 0 al primo giro -> test rinforzato -> 1 |
| I4 | `--solo-nomi` ignorato | 1 |
| F1 | tooltip per qualunque fonte (frontend) | 4 |
| F2 | testata col giocatore sbagliato | 1 |
| F3 | elenco senza tooltip sul giocatore 1 | 2 |
Sopravvissuto trovato: I3 (il test dei nomi nulli non esercitava il «?» perche' un'altra fonte lo copriva): corretto il test, ora rosso. Bug vero trovato dai test durante la costruzione:
`nomi_da_cache` con `_mercati` non-dizionario sollevava `AttributeError` (corretto in `convertitore.py`). La falsificazione della migrazione e' dentro `verifica_migrazione_pg.py`
(prima della migrazione la chiave non c'e'; riapplicando solo l'elenco sparisce).

### 3.2 Non regressione del reimport (richiesta della specifica) - `reimport_confronto.py`, `reimport_prima.txt` (codice di `b5547eb` estratto con `git archive`), `reimport_dopo.txt`
Cartella finta (formato vero dello Stream API, `dati_tennis.partita_costruita`: MO + SET_BETTING + TOTAL_GAMES, punteggio) con `_names.json` completo e senza, importata DUE volte ciascuna su Supabase finto:
conteggi identici prima/dopo: eventi=1 mercati=3 snapshot=9 punteggi=1, `n_markets=3 n_snapshots=9 n_score=1`, nomi invariati («Uno Completo/Due Completo» con file, «Uno Troncato/Due Troncato» senza).
`diff prima dopo`: UNICA differenza = la chiave in piu' `"name_source"` su ogni selezione (6 righe: 3 mercati x 2 scenari), voluta dalla correzione. Scenario in sequenza
(senza nomi -> con nomi -> di nuovo senza): PRIMA il terzo passo faceva TORNARE il nome troncato (`Uno Troncato`); DOPO resta `Uno Completo` (nomi aggiornati solo dove c'e' la fonte, mai declassati).

### 3.3 Suite
- Mirati prima (b5547eb): `tennis_replay` + `test_tennis_recorder` + `test_rec_tutti_i_mercati`: 52 passed, 6 skipped (skip = registrazione vera 35790089 assente nel container, preesistenti), 3.97 s (real 5.7 s). Dopo: 90 passed, 6 skipped (stessi 6 skip), 5.6 s: +38 test, nessuno dei 52 e' cambiato.
- `python3 -m pytest Betfair/ -q -p no:cacheprovider` (macchina molto carica): lancio 1 = 10796 passed, 1 failed (il MIO test importava `laboratorio.tennis_lab`: vietato dal contratto strada unica, corretto), 87 skipped, 6 xfailed, 440 s
  (`pytest_completo_dopo_1_con_rosso_mio.txt`). Lancio 2 dopo la correzione = 10796 passed, 1 failed = `test_motore_ordini_2026_09_24.py::test_latenza_logica_comando_place_sotto_20_ms` (soglia di latenza < 20 ms con load average 12-30; rilanciato da solo: 84 passed, `pytest_latenza_rilancio.txt`), 387 s (`pytest_completo_dopo.txt`). Non ho una suite intera verde in un solo lancio:
  il coordinatore la rilanci sul PC. Il contratto `test_contratto_strada_unica` + i miei file: 89 passed dopo la correzione.
- `npx tsc -p tsconfig.app.json --noEmit`: 0 errori (nessun output; 2 min 33 s).
- `npx vitest run` completo (`vitest_completo_dopo.txt`): 3 failed | 351 passed | 10 skipped file, 4 failed | 5303 passed | 51 skipped test, 38 min con load ~25. I 4 rossi sono in file NON toccati
  (`SafeStrategy.test.tsx` x2: spy 0 chiamate; `PosizioniChiuse.raggruppamento.test.tsx`: soglia «montata in meno di 1 s»; `BotParamsSheet.test.tsx`): rilanciati da soli senza gli altri: 3 file, 97 passed (`vitest_4_rossi_rilancio.txt`).
  Sono rossi da carico (timing), non causati da me; verifica sul PC raccomandata. I test del tennis replay: 16 passed.
- `npm run build`: NON eseguito (CLAUDE.md lo richiede sul checkout principale dopo modifiche a `frontend/src`; qui solo tsc + vitest).

### 3.4 Tempi prima/dopo
Mirati Python: 3.97 s -> 5.6 s (macchina condivisa, +38 test). Il percorso di runtime toccato: `enable()` del tee ora fa una lettura+scrittura di un json da pochi KB solo quando il catalogo cambia (le altre chiamate: una `json.dumps` del catalogo);
fuori dal lock del tee e dal percorso dei messaggi (`write_message` non modificato). `_carica` aggiunge 2 SELECT leggere per evento al caricamento (non interattivo). Nessun replay del banco e' toccato (vedi 3.6).

### 3.5 Migrazione su PostgreSQL 16 usa-e-getta (`verifica_migrazione_pg.py`, esito in `verifica_migrazione_pg.txt`): 21/21 OK
Applicata dopo la 07/10 e dopo l'elenco 08/10, riapplicata (idempotente); `nomi_fonte` in lista e meta; `market_types` non perso; eventi vecchi: chiave presente con null; non-owner = «accesso negato»;
anon senza EXECUTE; falsificazioni (senza la nuova migrazione la chiave non c'e'; riapplicando solo l'elenco sparisce); ordine 07/10 -> nuova (senza elenco) gia' completa.

### 3.6 Replay del banco
NON eseguiti e NON dovuti: nessun file del banco (`banco_comune`, `varianti_bot`, `replay_registrazioni`, `replay_bot`) e' toccato; `applica_bot.py` usa solo `importa.trova_registrazioni` (invariata);
`nomi_da_cache` e' usata solo da `importa`. Strategie, soglie, stake, gambe: NON toccati.

## 4. Da rieseguire sul PC (comandi esatti, numeri attesi)
Prerequisito: applicare `migrations/replay_tennis_fonte_nomi_2026-10-08.sql` (SQL Editor, ruolo postgres) e rilanciare la verifica in coda al file.
1. Suite: `python -m pytest Betfair/ -q -p no:cacheprovider` (atteso 0 rossi; qui 10796 passed, 87 skipped, 6 xfailed, con 1 rosso di latenza da carico).
   `cd frontend && npx tsc -p tsconfig.app.json --noEmit && npx vitest run && npm run build`.
2. Test con la registrazione vera (i 6 skip diventano esecuzione): `python -m pytest Betfair/stream/tennis_replay -q -p no:cacheprovider` (atteso 64 passed, 0 skipped se `_live_raw_tennis/20260707/35790089` c'e').
3. Caso vero 35790089 (nome troncato): sul PC non c'e' il nome completo ne' nel `_names.json` ne' nel DB. Cercare il nome vero in un solo modo, in sola lettura:
   `python -m Betfair.stream.tennis_replay.importa C:/Users/Admin/Desktop/tennis_rec --evento 35790089 --prova` -> in `diagnostica.nomi_fonte` atteso `{"player1_name": "ips", "player2_name": "ips"}`
   (finche' manca il catalogo). Poi aggiungere a mano la voce vera in `tennis_rec\20260707\_names.json` (`{"35790089": {"<selection_id>": "<nome intero>", ...}}`, il nome completo di Barrios Vera da Betfair o dal log del registratore)
   e lanciare `python -m Betfair.stream.tennis_replay.importa C:/Users/Admin/Desktop/tennis_rec --evento 35790089 --solo-nomi` (atteso: `aggiornato: true`, `giocatori` col nome intero, snapshot/punteggio intatti: nel DB `n_snapshots`/`n_score` identici a prima).
   Rilanciando `--solo-nomi` senza la voce il nome intero NON ridiscende. Non l'ho potuto fare qui: nessuna registrazione tennis, nessun DB.
4. REC tennis: alla prossima partita con REC acceso verificare che `<tennis_rec>\<giorno>\_names.json` contenga la voce piatta della partita e `"_mercati"` con tutti i mercati registrati (atteso: Match Odds + gli altri; il log dice `[tennis-rec] nomi dei runner di <ev> scritti`).
5. `python AUDIT_2026-10-08/cantiere_14/verifica_migrazione_pg.py` (richiede PostgreSQL 16 in `/usr/lib/postgresql/16/bin`, quindi probabilmente non sul PC Windows): e' la prova cloud, non va ripetuta per forza.
6. Schermo: Replay Tennis, elenco e testata di una partita col nome dall'IPS (dopo il reimport senza catalogo): tooltip «nome dall'IPS, troncato» e sottolineatura punteggiata; dopo `--solo-nomi` col nome intero: nessuna nota.

## 5. Limiti dichiarati
- Mai provato su registrazioni tennis vere ne' sul DB: il percorso di `anagrafica_dal_db` verso `tennis_live_now`/`tennis_live_ladder` e' provato con righe prodotte dal codice vero del runner ma su un client Supabase FINTO (stesso del test di caricamento); la forma reale delle righe nel DB di produzione non e' verificata.
- Le righe gia' nel DB non hanno `name_source` ne' `nomi_fonte`: finche' non si reimporta la partita NESSUN tooltip (volutamente: nessuna fonte dichiarata = nessuna nota). La 35790089 va reimportata per mostrare la nota.
- Il tooltip e' sul nome dell'evento (elenco e testata); non sui nomi delle selezioni nei pannelli di mercato (`name_source` per selezione e' salvato e disponibile).
- Precedenza `_names.json` piatto (`"*"`) vs catalogo DB per-mercato sul Match Odds: nel convertitore vince la chiave per-mercato (comportamento di prima). La chiave per-mercato di `_names.json` (`_mercati`) invece vince sul DB. Entrambi sono catalogo Betfair: differiscono solo se uno dei due e' sbagliato.
- La scrittura di `_names.json` e' protetta da un lock di processo e da `os.replace`; se un grid runner scrive lo stesso file nello stesso istante da un altro processo resta una finestra di gara minima (nessun lock fra processi).
- `self.dir` del tee e' fissato alla prima accensione (preesistente): un processo che attraversa la mezzanotte scrive i nomi nella cartella del giorno di avvio, coerente col raw.
- Non ho eseguito `npm run build`.

## Decisioni per l'utente
1. **Formato di `_names.json`** (sezione 1.1): ho tenuto la chiave piatta di sempre per il Match Odds e messo `event -> market -> selection -> nome` sotto la chiave riservata `"_mercati"` invece che nell'evento, per non rompere `replay_bot`, il lab e il cantiere 6. Se vuoi la forma letterale va deciso con il cantiere 6.
2. **Migrazione `replay_tennis_fonte_nomi_2026-10-08.sql`** (non nominata dalla specifica): serve per il tooltip nell'elenco; da applicare DOPO (o al posto di) quella dell'elenco 08/10. Nessuna decisione di trading.
3. **Reimport che non declassa**: un reimport da fonte peggiore non cambia piu' il nome nel DB (prima lo cambiava). E' il significato di «AGGIORNA quando compare una fonte migliore»; se si vuole poter forzare un nome peggiore bisogna cancellare la partita e reimportarla.
4. Nessuna decisione di trading toccata (soglie, stake, tetti, gambe: nessun file di strategia modificato).

## Blocco per la cronostoria
**Cantiere 14 (08/10) - nome troncato nel Replay Tennis.** Registratore tennis (`tennis_recorder.py`): a ogni REC scrive in `<cartella del giorno>/_names.json` i nomi completi di tutti i mercati registrati
(voce piatta di sempre per il Match Odds + chiave riservata `_mercati` evento->mercato->selezione; non sovrascrive, atomico, fuori dal lock del tee). Convertitore: `name_source` per selezione e `diagnostica.nomi_fonte`
(catalogo/marketdef/evento/ips); importatore: fonti `--nomi`/`_names.json`/catalogo DB (+ `tennis_live_now`/`tennis_live_ladder` se il Match Odds manca in `tennis_markets`)/IPS; reimport che SOLO migliora i nomi, `--solo-nomi` che non tocca snapshot ne' punteggio.
Pagina: tooltip «nome dall'IPS, troncato» sul nome con fonte IPS (elenco e testata), senza cambio di layout; migrazione `replay_tennis_fonte_nomi_2026-10-08.sql` (non applicata; contiene anche `market_types`).
Prove: +38 test Python, +6 vitest, 26 mutazioni rosse col ripristino a sha uguale, reimport prima/dopo con conteggi identici (unica differenza `name_source`), 21/21 controlli della migrazione su PostgreSQL 16 usa-e-getta, tsc 0 errori.
Da rieseguire sul PC: suite complete (qui 1 rosso di latenza da carico + 4 vitest rossi da carico, rilanciati verdi), registrazione vera 35790089 (nome completo da mettere nel `_names.json`, poi `importa --evento 35790089 --solo-nomi`), applicare la migrazione. Deviazione dalla specifica: formato di `_names.json` (vedi referto 1.1).
Punto di ripresa: coordinatore rilegge il diff, rilancia suite e mutazioni, decide il formato di `_names.json` d'accordo col cantiere 6.

## Verifica del coordinatore cloud (08/10)
- Diff riletto. Compatibilita' del nuovo `_names.json` verificata su TUTTI i lettori: `replay_bot.catalogo_dichiarato` legge solo
  `tutto[event_id]`, `laboratorio/tennis_lab/lab_grid_score.build_names_cache` legge per evento e riscrive il dizionario intero
  (la chiave `_mercati` resta), convertitore/importatore nuovi la gestiscono. Il cantiere 6 e' stato avvisato del formato.
- Test rilanciati nel checkout integrato: Python 64 verdi / 6 saltati (registrazioni vere assenti), vitest Replay Tennis 16/16.
- MIE MUTAZIONI: M1 il registratore sovrascrive la voce piatta di una partita gia' presente -> 1 rosso; M2 il reimport declassa i
  nomi -> 2 rossi; M3 scrittura che perde i nomi -> 9 rossi. Ripristino verificato.
- ORDINE DELLE MIGRAZIONI (utente): `replay_tennis_fonte_nomi_2026-10-08.sql` contiene anche `market_types`: va applicata DOPO
  (o al posto di) `replay_tennis_mercati_elenco_2026-10-08.sql`; riapplicare quella dopo toglie `nomi_fonte`.
