# FIX_TENNIS_CHIUSURA - R-FA-1 (partita automatica finita mai chiusa + tetto) e F-11 (Terminal che scrive all'apertura) - 26/09/2026

Delegato di correzione (Opus), worktree `agent-a15ef6330a7a0b48e`, base `498ba07`. Niente commit, niente DB, niente processi, niente replay.
Strategie dei 4 bot NON toccate (nessuna soglia, stake, veto, condizione d'ingresso o uscita).

## File toccati (tutti)
| file | tipo |
|---|---|
| `Betfair/stream/tennis_live/tennis_runner.py` | modificato (+39 -0) |
| `Betfair/stream/tennis_live/tennis_bot_service.py` | modificato (+66 -14; un blocco spostato, vedi sotto) |
| `Betfair/stream/tennis_live/auto_mode.py` | modificato (+8 -3) |
| `frontend/src/pages/TennisTerminal.tsx` | modificato (+54 -10) |
| `Betfair/stream/tennis_live/tests/test_tennis_chiusura_2026_09_26.py` | NUOVO (19 test) |
| `frontend/src/pages/TennisTerminal.test.tsx` | NUOVO (5 test) |
| `AUDIT_2026-09-26/falsifica_tennis_chiusura.py`, `AUDIT_2026-09-26/falsifica_terminal_f11.py` | NUOVI (script di falsificazione, ripristino con sha256) |
| `AUDIT_2026-09-26/FIX_TENNIS_CHIUSURA.md` | questo referto |

Nessuna migrazione (non serviva una colonna). Junction create nel worktree: `.venv` e `frontend/node_modules` -> checkout principale
(lasciate per la rilettura del coordinatore: prima di `git worktree remove` fare `cmd /c rmdir <wt>\.venv` e `cmd /c rmdir <wt>\frontend\node_modules`).

## R-FA-1 - reperto -> causa -> correzione

**Reperto** (`ADMIN26_AUTOMODE_SAFE.md` §B, `ADMIN26_FEED_ATLANTE.md` R-FA-1): 7 partite finite ferme a `SUSPENDED` riscritte ogni ~2 s per ore,
28 righe `running`, 12 armate per bot col tetto 5; `tennis_live_now.status='CLOSED'` 0 righe in tutta la tabella.

**Cause (file:riga della base 498ba07)**
1. flumine chiude il mercato con `CloseMarketEvent` + `continue` (`.venv/Lib/site-packages/flumine/baseflumine.py:157-159`) e poi chiama
   `strategy.process_closed_market` (`baseflumine.py:378-380`), MAI `process_market_book`. La capture del runner (`tennis_runner.py:379-403`)
   non aveva `process_closed_market`: teneva l'ultimo book (SUSPENDED) e `_build_now_state` (`:1273-1295`) lo scriveva a `:1380`.
2. Il ponte fermava una partita automatica uscita dal feed SOLO se `tennis_live_now.status == 'CLOSED'` (`tennis_bot_service.py:492-500, 565-572`).
3. Il tetto contava solo le armate ancora nel feed (`auto_mode.py:190-191`, chiamato da `tennis_bot_service.py:543-544`).

**Correzioni (righe del worktree)**
- (a) runner:
  - `tennis_runner.py:394` `_Capture.process_closed_market`: serializza il book di chiusura (o l'ultimo noto) con `status='CLOSED'` (stessa via del
    calcio, `recorder.py:197-212`).
  - `tennis_runner.py:1311`: a `CLOSED` `inplay=False` (l'ultimo book porta ancora inplay=true e la UI scriverebbe LIVE).
  - `tennis_runner.py:1356-1366, 1417-1421` + `:526` (`session.now_chiusi`): `CLOSED` si scrive UNA volta, poi la partita non si riscrive piu' e non
    chiede piu' il punteggio IPS (niente REST diretto ogni 2 s); se l'upsert fallisce si riprova al giro dopo; il set NON si svuota a
    `reset_streams` (dopo un rebuild il book vuoto direbbe SUSPENDED).
  - Rete di sicurezza del runner NON aggiunta (vedi Divergenze 1): la rete sta nel ponte, che conosce il feed.
- (b) ponte:
  - `tennis_bot_service.py:495` + `:663-690` (`_FINE_FUORI_FEED_DEFAULT_S=600`, `_fine_fuori_feed_s`, `_aggiorna_fuori_feed`, `_FUORI_FEED_DAL`):
    memoria di "fuori dal feed dal", aggiornata solo a feed VIVO; rientro nel feed = orologio azzerato; scanner fermo = tutto azzerato.
    Soglia dichiarata: **600 s**, env `TENNIS_AUTO_FINE_FUORI_FEED_S` (vuota/illeggibile/<=0 = 600).
  - `tennis_bot_service.py:497-522` `_mercato_chiuso`: finita = `CLOSED` **oppure** fuori dal feed da >= soglia con mercato **non OPEN**
    (SUSPENDED o riga `tennis_live_now` assente). Un mercato OPEN non si chiude mai da qui (test esistente `test_sparita_a_mercato_APERTO_non_si_tocca` intatto).
  - `tennis_bot_service.py:547-557`: il blocco di chiusura (righe -> `stopping`) e' SPOSTATO prima dell'auto-mode (era dopo l'armamento), cosi' nello
    stesso giro il tetto non conta le finite. Il resto invariato: il runner porta `stopping` -> `stopped` a flat verificato; il follow automatico si chiude
    al giro dopo quando nessuna riga lo occupa (codice esistente `:626-640`).
  - `tennis_bot_service.py:572-576` + `auto_mode.py:179,191-196` (`scegli_partite(..., altre_vive=0)`): le armate VIVE fuori dal feed (non ancora
    finite) occupano un posto del tetto. Default 0 = firma e comportamento di prima per chi non lo passa.
- (c) riavvio: nessun codice nuovo necessario. Verificato con test che la catena esistente basta: `ferma_bot_al_nuovo_avvio` (R2) porta a
  `stopped`/paper le righe di un avvio vecchio, e il primo `riconcilia_interruttori` chiude i follow automatici non occupati (anche a bot riacceso:
  le partite di ieri non sono nel feed, non si riarmano, il follow si chiude). I follow MANUALI di una partita finita: al rebuild il catalogo
  REST non la trova e il runner la marca `ERROR` (`tennis_runner.py` `_risolvi_follow`) - NON verificato su Betfair vero (vedi sotto).

## F-11 - reperto -> causa -> correzione
- Reperto (`ADMIN26_FASE3_PAGINE.md` F-11, U0361): all'apertura `rpc('tennis_follow_event', {p_event_id:'36118619', p_market_id:'1.262933523'})`.
- Causa: `frontend/src/pages/TennisTerminal.tsx:112-117` (base) useEffect che seguiva la partita al mount. Nessun bottone «Segui» esisteva nella pagina
  (esiste in `Board.tsx:106` e `AzioniPartita.tsx:133`, non qui). Effetto collaterale: la RPC riporta a PENDING anche un follow CLOSED (`tennis_live.sql:183-187`).
- Correzione: useEffect rimosso; stato `seguita` letto da `get_tennis_follows` (`:74`, PENDING/STREAMING = seguita); funzione `segui` (`:119`)
  chiamata SOLO dal bottone «SEGUI» nell'intestazione (`:201-231`); senza follow la pagina scrive «partita non seguita: premi «Segui» per ladder e
  punteggio»; errore mostrato («SEGUI KO» col messaggio nel title); a partita seguita un'etichetta «SEGUITA» e nessun bottone.

## Test
- `Betfair/stream/tennis_live/tests/test_tennis_chiusura_2026_09_26.py` (19): Flumine + client paper + MarketStream/listener VERI con messaggi `mcm`
  (OPEN -> SUSPENDED -> CLOSED con runner WINNER/LOSER): `test_flumine_vero_il_book_closed_arriva_alla_capture_e_a_tennis_live_now`,
  `test_flumine_vero_non_passa_il_closed_a_process_market_book` (documenta la causa), `test_score_worker_scrive_closed_una_volta_poi_smette`,
  `..._partita_sospesa_si_riscrive_come_prima` (contrario), `..._closed_non_scritto_si_riprova`, `test_closed_scritto_sopravvive_al_reset_degli_stream`;
  ponte con orologio finto: `test_ponte_chiude_su_closed_scritto_dal_runner`, `test_ponte_rete_fuori_dal_feed_oltre_soglia_a_mercato_sospeso`
  (599 s no, 600 s si', poi follow CLOSED a righe ferme), `..._riga_now_assente_oltre_soglia`, `..._mercato_OPEN_fuori_dal_feed_non_si_chiude_mai`,
  `..._rientrata_nel_feed_l_orologio_riparte`, `..._scanner_fermo_l_orologio_riparte`, `..._soglia_da_env`, `test_ponte_la_seguita_a_mano_non_si_chiude`,
  `test_tetto_conta_le_armate_vive_fuori_dal_feed`, `test_scegli_partite_altre_vive`, `test_il_reperto_7_morte_e_5_vive_col_tetto_5` (i 7 event_id veri);
  riavvio: `test_riavvio_righe_stantie_fermate_e_follow_automatici_chiusi`, `test_riavvio_bot_riacceso_non_riprende_le_partite_di_ieri`.
- `frontend/src/pages/TennisTerminal.test.tsx` (5): finto = client supabase (le funzioni vere di `lib/tennis` e i figli veri girano); montare la
  pagina con follow CLOSED / STREAMING / assente => zero rpc non `get_*` e zero insert/update/upsert/delete; «Segui» chiama `tennis_follow_event`
  con `{p_event_id, p_market_id}` una volta; a partita seguita nessun bottone e nessun avviso.
- Esiti: nuovi 19/19 e 5/5 verdi. Regressione: `Betfair/stream/tennis_live/tests` + `Betfair/stream/tennis_scalper` + `stream/tests/test_avvio_app_2026_09_16.py`
  + `test_punto6_b_stato_bot_e_battito_tennis_2026_09_25.py` + `test_stato_mercato_freno_2026_09_24.py` -> **807 passed**. `npx tsc -p tsconfig.app.json --noEmit` -> 0 errori.
- RED sulla base: con i 3 file Python di `498ba07` il file nuovo da' 5 failed + 12 errors (gli errori: la fixture tocca `S._FUORI_FEED_DAL`, che
  sulla base non esiste) e 2 passed (`chiude_su_closed`, gia' vero prima; `non_passa_il_closed`, documenta flumine). Il rosso LOGICO di ogni
  pezzo e' dato dalle mutazioni qui sotto.

## Falsificazione (tutte ROSSE, file ripristinati e verificati con sha256)
`falsifica_tennis_chiusura.py`: M1 capture senza `process_closed_market` - M2 CLOSED resta in gioco - M3 CLOSED riscritto ogni giro - M4 chiusi
svuotati al reset - M5 ponte solo CLOSED (niente rete) - M6 rete che chiude anche a mercato OPEN - M7 rientro nel feed non azzera l'orologio -
M8 scanner fermo non azzera - M9 tetto senza vive (ponte) - M10 tetto senza vive (`auto_mode`) - M11 soglia env ignorata: **11/11 ROSSE**.
`falsifica_terminal_f11.py`: F1 follow automatico all'apertura (il bug: 4 rossi) - F2 bottone che non chiama la rpc (1) - F3 nessun avviso (1): **3/3 ROSSE**.

## Comandi esatti (dalla radice del worktree)
```
SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_KEY=x .venv/Scripts/python.exe -m pytest Betfair/stream/tennis_live/tests/test_tennis_chiusura_2026_09_26.py -q -p no:cacheprovider
SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_KEY=x .venv/Scripts/python.exe -m pytest Betfair/stream/tennis_live/tests Betfair/stream/tennis_scalper Betfair/stream/tests/test_avvio_app_2026_09_16.py Betfair/stream/tests/test_punto6_b_stato_bot_e_battito_tennis_2026_09_25.py Betfair/stream/tests/test_stato_mercato_freno_2026_09_24.py -q -p no:cacheprovider
SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_KEY=x .venv/Scripts/python.exe AUDIT_2026-09-26/falsifica_tennis_chiusura.py
cd frontend && npx vitest run src/pages/TennisTerminal.test.tsx && npx tsc -p tsconfig.app.json --noEmit
.venv/Scripts/python.exe AUDIT_2026-09-26/falsifica_terminal_f11.py
```
Replay NON lanciato (ordine): `certifica safe_tennis 35795993 --scenari rapidi --trasporto entrambi` e profilo rapido dei 4 bot, al coordinatore.

## Calcio (solo segnalazione, NON corretto: cantiere separato)
`Betfair/stream/runner.py:354` scrive `live_now.status = "OPEN" if inplay else "SUSPENDED"` e `:378` `status="OPEN"`: `live_now.status` del calcio non
e' MAI `CLOSED` al livello di riga. NON e' lo stesso difetto: il calcio chiude la partita per un'altra via (`recorder.py:197-212`
`process_closed_market` marca il book CLOSED nella cache -> `_finalize_event` `runner.py:760` porta `live_follow` a CLOSED), e lo scalper calcio
non legge `live_now.status` (e2e 7.9.6.E1 scalper PASS). Chi legge `live_now.status` per sapere se una partita e' chiusa leggerebbe sempre OPEN/SUSPENDED.
Non e' una funzione condivisa col tennis: non toccato.

## Divergenze / da portare all'utente
1. **Rete di sicurezza "non in-play" -> "non OPEN".** Il brief dice «uscita dal feed da > N minuti con mercato non in-play». Nelle righe del reperto il
   mercato morto porta `inplay=true` (ultimo book SUSPENDED in gioco): con «non in-play» la rete non sarebbe MAI scattata sul caso reale. Ho usato
   «non OPEN» (SUSPENDED o riga assente). Una partita sospesa a lungo (pioggia) E uscita dal feed per >= 10 min verrebbe portata a `stopping`
   (chiusura a flat: nessuna apertura nuova, le protezioni restano). Rete messa nel ponte (che conosce il feed), non nel runner.
2. **CLOSED a scanner fermo non chiude** (test esistente `test_scanner_fermo_non_chiude_niente_e_non_ferma_niente` lasciato com'e'): con il runner che
   ora scrive CLOSED davvero si potrebbe chiudere anche a scanner fermo; non l'ho cambiato (comportamento certificato ieri). Decisione dell'utente.
3. **Follow MANUALI di partite finite**: non si chiudono dal ponte (regola esistente «un follow manuale non si chiude mai»); ora non vengono piu'
   riscritti ogni 2 s (CLOSED scritto una volta) ma i bot armati a mano su una partita chiusa restano `running` (heartbeat del runner) finche'
   l'utente non li ferma o l'app riparte. Da decidere se chiudere anche quelli su CLOSED.
4. Il tetto ora conta anche le armate fuori feed non ancora finite (fino a 10 min dopo l'uscita): in quella finestra una partita nuova del feed puo'
   attendere un giro in piu' per armarsi.

## Cosa NON ho potuto verificare
- Nessun replay (`certifica`), nessuna app viva, nessun DB vero, nessuna sessione Betfair: il messaggio `mcm` di chiusura e' costruito come quello
  di Betfair (marketDefinition status CLOSED, runner WINNER/LOSER) ma non preso da una registrazione reale.
- Che `listMarketCatalogue` non restituisca i mercati CLOSED (per il follow manuale stantio -> `ERROR` al rebuild): da documentazione/ricordo, non provato.
- `_strategy_is_flat` su un bot ospitato quando il mercato e' chiuso da flumine (ordini regolati): letto nel codice, non esercitato con un ordine vivo al momento della chiusura.
- Una riga `stopping` di una partita che il runner non ospita piu' (evento non in `market_meta`) resta `stopping` (il worker gira solo sugli eventi seguiti): pre-esistente, non toccato; non conta nel tetto e non si riarma.

## Rischi residui
- `_FUORI_FEED_DAL` e' memoria di processo: a ogni riavvio del ponte l'orologio riparte (la partita morta si chiude 10 min dopo il riavvio, se non
  l'ha gia' chiusa R2).
- `vi.mock` del client supabase nel test del Terminal: i figli (ladder/bot panel/stats) girano col finto; se in futuro un figlio scrive al mount il
  test lo segnalera' (e' voluto).
