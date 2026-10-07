# REFERTO - Certificazione sul PC con il DB, protocollo HANDOFF_CERTIFICAZIONE_DB par. 1-6 (+ par. 10)

Esecutore: agente con il DB (Opus) sul PC dell'utente, checkout principale
`C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation`, `.venv` del PC (Python 3.13), Node 22.16.0.
Data: 07/10/2026, ore dall'orologio del sistema (inizio 15:22, fine 16:13).
Parti del coordinatore (par. 2, 4, 5.2, 10.2): «verificato dal coordinatore (Fable 5.1), sola lettura», esiti
ricevuti per messaggio alle 15:34 e dopo le 16:00, riportati qui senza rifarli.

## Commit
- 15:23: `git fetch` + `git checkout claude/eloquent-franklin-g2nyk5` nel checkout principale (prima `tasklist`:
  nessun processo python dei bot, nessun electron; solo un node.exe generico). La cima remota era gia' `2af4b77`
  (non `0b40b09`: un commit di sola documentazione della sessione cloud piu' nuovo, preso e annotato).
- Suite intera Python, vitest intero, tsc, catalogo: girati su **`2af4b77`**.
- 16:00: `git merge origin/claude/eloquent-franklin-g2nyk5` (avanzamento veloce) -> **`25ba24ef`** (Safe BASE solo 2T
  + scalper/sniper scavalco e tetto). Su `25ba24ef` rilanciati: suite intera Python, tsc, vitest `src/lib/safeStrategy`,
  catalogo 1.4. Codice certificato = **`25ba24ef`**, identico a `f19864ae` per il codice (16:13: merge di `f19864ae`,
  solo CRONOSTORIA +1 riga e `riferimenti_coordinatore/finale/suite_python_finale_sera.txt`; suite non rilanciate).

## REPERTI NON TORNA (in testa)

1. **3.4 Strumento della barra sulle partite del DB: 13 partite su 38 con incoerenze (atteso 0).** Le due partite del
   banco (35797769, 35760084) sono OK. Le 13 sono partite VECCHIE (02/07-17/07). 5 ERRORE `SIMBOLO_GOL_SENZA_AUMENTO`
   (35812264 55' 12:36:22 UTC «Gol Liaoning Tieren FC»; 35787218 67' 17:30:58 «Gol Egypt»; 35777617 80' 21:41:28
   «Gol Norway»; 35768297 68' 00:27:27 «Gol Portugal»; 35768365 36' 19:36:24 «Gol Spain»: simbolo di gol senza aumento
   del punteggio entro 3 min, verosimilmente gol annullati/VAR o righe del feed); 11 AVVISO: `KICKOFF_DISCORDANTE` x6
   (35817305, 35817978, 35817332, 35828026: tutte con la lineetta del calcio d'inizio alle 15:06:49 UTC, scarti 3-6 min,
   cioe' lo stesso istante per 4 partite = verosimilmente il registratore/mercato passato in gioco in ritardo;
   35794996 e 35796477: scarti di 103 e 99 min) e `CARTELLINI_DIVERSI` x5 (35812264, 35823368, 35804974, 35787218 x2:
   gialli del punteggio diversi dai simboli di 1). Dati NON corretti a mano (come da protocollo). Uscita 1.
   Testo integrale: `verifica_barra_tutte.txt`.
2. **Strumento della barra non lanciabile sul PC col comando del protocollo** (difetto di portabilita' Windows, non dei
   bot): `npx vite-node scripts/verifica_barra_replay.ts --env-file ../.env` esce con
   `Error: Cannot find module '/@fs/C:/Users/Admin/Desktop/PYTHON'`. Causa: `frontend/scripts/verifica_barra_replay.ts:107`
   si rilancia con `spawnSync('npx.cmd', ['vite-node', fileURLToPath(import.meta.url), ...], { shell: true })`: con la
   shell e senza virgolette il percorso con lo spazio («PYTHON DATABASE») si spezza. Aggirato SENZA toccare codice:
   impostando gia' all'avvio `VITE_SUPABASE_URL`/`VITE_SUPABASE_ANON_KEY` (= SUPABASE_URL / chiave di servizio dal
   `.env`, solo nell'ambiente del processo) il rilancio non avviene; comando usato da `frontend/`:
   `node node_modules/vite-node/vite-node.mjs scripts/verifica_barra_replay.ts` con quelle variabili. NON corretto.
3. **vitest intero su `2af4b77`: 6 rossi** (5236 verdi, 51 saltati, 5293 test, 359 file; atteso 5243 verdi 0 rossi),
   tutti d'AMBIENTE WINDOWS nei test del cantiere E, nessuno nei bot:
   - `src/lib/replayVerificaBarra.partite.test.ts` x2 («CONTRATTO: la fixture ... e' aggiornata», 35760084 e 35797769):
     l'impronta di `registrazioni_banco/<ev>/<ev>.timeline.jsonl` sul PC (31dc..., 7a92...) differisce da quella della
     fixture (0a42..., 9a10...). Verificato: il blob git e' LF (sha256 0a42... = fixture); sul PC `core.autocrlf=true`
     lo scrive CRLF (11 CR); tolti i CR l'impronta coincide con la fixture. I `.gz` non ne risentono. Rimedio possibile
     (non applicato): `.gitattributes` con `registrazioni_banco/** -text` oppure impronta calcolata senza i CR.
   - `src/lib/replayVerificaBarraScript.test.ts` x4: timeout (120-180 s). Rilanciato DA SOLO a CPU libera: stessi 4
     rossi, con `Error: spawn npx ENOENT` (riga 30: `spawn('npx', ...)` senza shell; su Windows serve `npx.cmd`).
   Gli altri 5236 test verdi; somma senza i 6 rossi d'ambiente = 5236 + 6 = 5242 contro 5243 del cloud: differenza di 1
   test fra «verdi» del cloud e il totale del PC, dovuta ai saltati (51 sul PC contro 50 del cloud): uno in piu' saltato.
4. **3.8 Nome di Barrios: NON VERIFICABILE come chiesto.** Il `_names.json` del PC
   (`C:\Users\Admin\Desktop\tennis_rec\20260707\_names.json`) NON ha la voce 35790089 (una sola voce: 35794049
   Sinner/Struff); niente in `registrazioni_banco/` (solo calcio), niente in `tennis_markets`/`tennis_live_follow` del DB.
   Indizi: il punteggio IPS (`35790089.score.jsonl`) porta «Marcelo Tomas Barrios V» (troncato, 104 righe); il log del
   registratore (`_recorder.log`, riga 19) porta il nome Betfair dell'evento «Barrios Vera v Simakin». Coerente con
   «Marcelo Tomas Barrios Vera» (prefisso unico, come accetta D2), ma il nome del runner completo non e' sul PC.
   Conseguenza: l'import del replay tennis ha dato `player1_name = 'Marcelo Tomas Barrios V'` (ripiego sui nomi IPS).

## Tabella dei passi

| passo | comando | atteso | ottenuto | esito | file di prova |
|---|---|---|---|---|---|
| 1.1 | `git fetch` + checkout del ramo | cima `0b40b09` | cima `2af4b77` (solo docs, piu' nuova), poi merge -> `25ba24ef` | OK (annotato) | sopra, «Commit» |
| 1.2 | `python -m pytest Betfair/ -q -p no:cacheprovider` su `2af4b77` | 10651 / 55 saltati / 6 xfail, 0 rossi | **10697 passati, 9 saltati, 6 xfail, 0 rossi** (1170 s). Totale 10712 = cloud (10651+55+6): 46 test che nel cloud si saltavano sul PC girano (registrazioni presenti) | OK | `suite_python_pc.txt` |
| 1.2-bis | stessa suite su `25ba24ef` | 0 rossi; i 2 file nuovi verdi | **10730 passati, 9 saltati, 6 xfail, 0 rossi** (543 s); i 2 file nuovi (`test_base_secondo_tempo_2026_10_07.py` + `test_scalper_residuo_c3_e_tetto_2026_10_07.py`, 16 dello scalper) 33 verdi rilanciati a parte. Il cloud della sera dice 10684 verdi: +46 sul PC = gli stessi 46 che nel cloud si saltano | OK | `suite_python_pc_25ba24ef.txt` |
| 1.3 tsc | `npx tsc -p tsconfig.app.json --noEmit` | 0 errori | 0 errori su `2af4b77` (123 s) e su `25ba24ef` | OK | `tsc_pc.txt`, `tsc_pc_25ba24ef.txt` |
| 1.3 vitest | `npx vitest run` (intero, un comando, 1341 s) su `2af4b77` | 5243 verdi, 0 rossi | 5236 verdi, **6 rossi** (ambiente Windows, reperto 3), 51 saltati | NON TORNA (ambiente) | `vitest_pc_pulito.txt`, `vitest_script_barra_da_solo.txt` |
| 1.3 vitest mirato | `npx vitest run src/lib/safeStrategy` su `25ba24ef` | 0 rossi | 6 file, 148 verdi, 0 rossi | OK | `vitest_safeStrategy_25ba24ef.txt` |
| 1.4 | `python -m Betfair.stream.backtest.applica_bot --catalogo-ts` vs `frontend/src/lib/replayBotCatalogo.ts` (ignorando i fine riga) | identico | identico (11053 righe, diff vuoto) su `2af4b77` e su `25ba24ef` | OK | `catalogo_diff.txt` (vuoto; i cataloghi generati, identici al file del repo, non sono committati) |
| 1.5 | `npm run build` | lo fa l'utente ad app chiusa | non fatto | IN ATTESA (utente) | - |
| 2 (pendenti 06/10) | query in sola lettura (coordinatore, MCP) | applicate | `segui_live_apri_partita`, `replay_bot_esiti` + `get_replay_bot_esito` + `request_backtest`, `ack_allarmi` (CAMBIO_GBP_EUR finti non riconosciuti 0, riconosciuti 225): tutte applicate, SECURITY DEFINER, niente anon/PUBLIC | OK (verificato dal coordinatore (Fable 5.1), sola lettura) | messaggio del coordinatore |
| 2.1 | `pg_proc` / `routine_privileges` su `scalper_media_attiva_adesso` | 1 riga prosecdef=true; authenticated+service_role; niente anon/PUBLIC | come atteso; prerequisiti presenti | OK (coordinatore) | idem |
| 2.2 | `pg_class` tennis_replay_*, privilegi, `pg_get_functiondef(list_replays)` | 4 tabelle RLS true, niente anon; calcio invariato | come atteso; 0 policy (accesso solo via RPC definer, come il calcio); `list_replays` IDENTICO a `migrations/live_stream_rpc.sql`; tabelle vuote prima del 3.7 | OK (coordinatore) | idem |
| 2.3 | nessun'altra migrazione | - | confermato | OK (coordinatore) | idem |
| 3.1 | RPC vera media under | serve app riavviata + sessione in PROVA | - | IN ATTESA | lista sotto |
| 3.2 | riavvio dopo un clic | idem | - | IN ATTESA | lista sotto |
| 3.3 | Applica bot dal worker vero | serve app/worker acceso | - | IN ATTESA | lista sotto |
| 3.4 | strumento della barra su tutte le partite del DB | 0 incoerenze, uscita 0 | 38 partite: 25 OK, **13 con incoerenze** (5 ERRORE, 11 AVVISO), 0 non verificabili, uscita 1, 194,6 s; 35797769 e 35760084 OK | NON TORNA (dati vecchi; reperti 1 e 2) | `verifica_barra_tutte.txt` |
| 3.5 | righe CLOSED per mercato su una partita caricata dopo il merge | mercati regolati con >= 1 riga CLOSED | NESSUNA partita caricata dopo il merge: l'ultima caricata in `live_market_snapshots` e' 35833626 del 22/09 (500 righe, 17 mercati, tutte OPEN). PRE-MERGE: 35833626, 36006953, 35797769 hanno 0 righe CLOSED (le vecchie non cambiano, come atteso) | IN ATTESA (prima partita calcio caricata dopo il merge) | `p3_5_mercati_closed.txt` |
| 3.6 | registrazione tennis di tutti i mercati dal vivo | serve partita tennis con REC | - | IN ATTESA | lista sotto |
| 3.7 | `python -m Betfair.stream.tennis_replay.importa C:/Users/Admin/Desktop/tennis_rec --prova`, poi senza, poi rilancio | prova senza errori; import; rilancio = stesse righe | prova: 83 partite (60 MATCH_ODDS + 24 SET_BETTING = 84 mercati), 137171 aggiornamenti, 0 errori (115 s). Import vero (2.2 applicata, via libera del coordinatore): 83 eventi, 84 mercati, 137171 snapshot, 7040 punteggi, 0 errori (440 s); conteggi nel DB identici. Rilancio (712 s): 83 partite, 84 mercati, 137171 snapshot, 7040 punteggi, 0 errori; conteggi nel DB INVARIATI (83 / 84 / 137171 / 7040) = idempotente | OK | `p3_7_import_prova.txt`, `p3_7_import_1.txt`, `p3_7_conteggi_dopo_import_1.txt`, `p3_7_import_2.txt`, `p3_7_conteggi_dopo_import_2.txt` |
| 3.8 | nome di Barrios nel `_names.json` della 35790089 | «Marcelo Tomas Barrios Vera» | voce assente nel `_names.json`; indizio «Barrios Vera v Simakin» dal log del registratore | NON TORNA (non verificabile; reperto 4) | sopra |
| 3.9 | Omega sul DB nel 2T | serve app riavviata + Omega in PROVA | - | IN ATTESA | lista sotto |
| 3.10 query | `safe_strategy_scan`, sport calcio, `score_raw` | `ha_stato` true sulle partite in gioco | 24 righe calcio (ultimo aggiornamento 06/10 16:12, app spenta da allora): chiave `score_raw` presente in 24/24; valorizzata con `matchStatus` su **6/6 partite in gioco** (KickOff x3, SecondHalfKickOff x3), nulla sulle 18 pre-match | OK (NON e' il caso critico) | `p3_10_safe_scan.txt` |
| 3.10 schermo | diagnosi ESATTO nel recupero del 1T | serve partita in PROVA | - | IN ATTESA | lista sotto |
| 3.11 | scalper chiusura al centesimo dal vivo | serve PROVA | - | IN ATTESA | lista sotto |
| 3.12 | bot tennis dopo il cambio del runner | rifatti dal coordinatore; dal vivo = 3.6 | - | IN ATTESA (3.6) | - |
| 4 | referti dei replay (NON rifatti) | numeri del par. 4 e della cronostoria | tutti tornano (dettaglio sotto) | OK (verificato dal coordinatore (Fable 5.1), sola lettura) | messaggio del coordinatore |
| 5.1 | = par. 1 | - | vedi 1.2/1.3 | vedi 1.x | - |
| 5.2 | `git diff 8226d76 -- frontend/src/fotografia/snapshot \| grep '^-[^-]'` | vuoto | 0 righe tolte, 537 aggiunte | OK (verificato dal coordinatore) | - |
| 5.3 | `python -m Betfair.stream.backtest.certifica tennis_pro 35794049 --data-dir C:/Users/Admin/Desktop/tennis_rec/20260707 --scenari tutti --worker 1` | 0 violazioni, <= 10 min | ESITO 17 partite senza violazioni, **0 violazioni**, 17/17 OK, TEMPO TOTALE 125,8 s (obiettivo 300, tetto 600); 16:02:34-16:04:45; soldi-veri-prova: 0 ordini reali, 20 aperture fermate dalla terza rete | OK | `p5_3_tennis_pro_35794049.txt` |
| 6.1-6.5 | prova a schermo con l'utente | - | lista di controllo sotto | IN ATTESA (utente) | - |
| 10.1 | controlli dal vivo in PROVA (Safe BASE all'intervallo, scalper `scavalco`/`loss_cap`) | - | lista sotto | IN ATTESA | - |
| 10.2 | referti `replay_safe_base/` e `finale/scalper_N2.txt` | 8/8 identici, B18 viol=0; scalper 5/5 | tornano | OK (verificato dal coordinatore (Fable 5.1)) | messaggio del coordinatore |

## Par. 4 - dettaglio (verificato dal coordinatore (Fable 5.1), sola lettura, `git show` dal ramo)
- Bot tennis finali vs riferimento del mattino: tennis_flb 17/17, tennis_swing 17/17, safe_tennis 18/18: diff sostanziale 0
  (solo TEMPO TOTALE e hash del codice) -> IDENTICI. tennis_pro finale vs `tennis_pro_tutti_dopo_COORDINATORE.txt`: 17/17,
  0 violazioni, diff 0. tennis_scalper finale vs `replay_scalper_tennis_cp4/tennis_scalper_tutti_dopo.txt`: 17/17, diff 0.
- Safe esatto prima/dopo: 8 righe OK identiche (tick/decisioni/azioni), ESITO 8/8, 0 violazioni; nel dopo E11 x7698 viol=0
  (35797769) e x6092 viol=0 (35760084), `secondHalf:no x3796`, ESATTO lay sel 9063254 @32 chiesto 2,0 abbinato 2,0 `won`
  pnl 1,9. Le 77 righe diverse sono le note nuove di E11/secondHalf.
- Omega: PRIMA (4dd624af) 35760084 `apertura` 438/0; DOPO 467/2; FINALE = DOPO. `tutti`: 35760084 20/20 prima e dopo,
  35797769 20/20 dopo, 0 violazioni (35797769 LENTO 1986 s, dichiarato).
- Scalper chiusura al centesimo (`replay_COORDINATORE_con_fix_banco.txt`): chiusura-abbinata-in-parte OK 217 azioni, base
  OK 44, paper OK 44, ESITO 3/3 0 violazioni.
- Scalper 8 scenari x 2 partite: righe OK identiche prima/dopo (es. 35797769 base 1511913/286052/167; 35760084 0 azioni);
  differiscono solo l'etichetta `[sniper-paper]` e l'aggregazione dell'ESITO (14+2 vs 16).
- Media under: «0 violazioni, 1 NE» torna (35797769 r5 17 OK + 1 KO prezzi-fermi = falso positivo M15 dichiarato, rifatto
  verde in r8/r10; 35760084 r7 18/18 OK + r10 OK; NE unico `media-clic-sospeso` su 35797769). NOTE: (a) il run r7 della
  35760084 e' di prima di tre ritocchi del codice: sui 18 scenari col codice finale c'e' solo la 35797769; (b) lo scenario
  `auto-live` della 35760084 e' KO sia PRIMA sia DOPO (preesistente, dichiarato, non del 07/10): reperto aperto preesistente.
- Suite cloud `suite_python_finale.txt`: «10651 passed, 55 skipped, 6 xfailed in 423.92s» = par. 9.

## Par. 5.3 - registrazioni tennis sul PC diverse dalla 35790089
`C:\Users\Admin\Desktop\tennis_rec\`: `20260707\` 60 partite MATCH_ODDS (35790089 compresa) e `setbetting_20260707\`
24 file SET_BETTING (stesse partite, altro mercato). Le 59 + set betting diverse dalla 35790089 sono elencate nel
riepilogo dell'import (`p3_7_import_prova.txt`, campo `event_id`). Lanciato UN bot su UNA registrazione (tennis_pro sulla
35794049 Sinner-Struff, la sola con i nomi nel `_names.json`), durata stimata dichiarata prima del lancio: 5 min (tetto 10).
DA FARE COL VIA LIBERA dell'utente: tennis_scalper, tennis_flb, tennis_swing, safe_tennis sulla 35794049 e gli altri bot
sulle altre registrazioni (un bot per volta, `--scenari tutti --worker 1`).

## Lista di controllo IN ATTESA del par. 3 (pronta per quando l'utente da' il via)

- [ ] **3.1** (serve: app riavviata dopo build, sessione Media Under in PROVA su una partita qualunque, clic «Attiva adesso»):
  `SELECT params->'media_attiva_adesso', stats->'media_comando' FROM scalper_control WHERE event_id='<ev>';`
  ATTESO `media_attiva_adesso {id, ts}` e `stats.media_comando.esito='eseguito'` con prezzo e importo; una riga di punta
  allo stake base in `scalper_trades` / `betfair_live_orders`.
- [ ] **3.2** (serve: come 3.1, poi riavvio del servizio scalper a posizione aperta): stessa query; ATTESO
  `stats.media_comando.id` invariato e UNA sola riga d'ingresso per quell'id.
- [ ] **3.3** (serve: app accesa con il worker del Backtest): da Match Replay -> Applica bot, Mike `base` su una partita
  calcio, e un bot tennis su una partita importata col 3.7. Query:
  `SELECT id, status, params FROM backtest_requests ORDER BY created_at DESC LIMIT 5;` (tabella della coda di
  `request_backtest`) e `SELECT * FROM get_replay_bot_esito('<request_id>');` ATTESO DONE, `parametri_usati`,
  `parametri_cambiati`, `dal_ms`. Se la RPC rifiuta i campi nuovi: migrazione mancante.
- [ ] **3.5** (serve: la prima partita CALCIO caricata dopo il riavvio dell'app col codice nuovo):
  `SELECT market_id, status, count(*) FROM live_market_snapshots WHERE event_id='<ev>' GROUP BY 1,2;` ATTESO: ogni
  mercato regolato ha >= 1 riga `CLOSED`. (Sul PC la stessa cosa in sola lettura: sonda REST
  `select=id,market_id,status&event_id=eq.<ev>&id=gt.<ultimo>` a pagine per chiave, l'offset va in timeout.)
- [ ] **3.6** (serve: partita tennis con REC acceso): nel log del runner tennis `[tennis-rec] <ev>: N mercati in piu'` e
  `mercati registrati sulla stessa connessione: accesi [...]`, nessun `STREAM DUPLICATO`; nel `<ev>.raw.jsonl` righe con
  `marketType` diverso da MATCH_ODDS; `tennis_live_ladder.updated_at` senza buchi oltre la risottoscrizione; ~60 s dopo
  la chiusura del Match Odds la partita in `SELECT * FROM list_replays_tennis(50);` con TUTTI i mercati.
- [ ] **3.9** (serve: app riavviata, Omega acceso in PROVA su una partita): attivita' `omega_activity` della partita,
  conteggio per `kind` prima e dopo il 45': nel 2T NON solo `flusso_interrotto`/`no_live_state`. Pannello Motore v3:
  interruttore «Includi Any Other» presente e acceso.
- [ ] **3.10 a schermo** (serve: partita calcio in PROVA nel recupero del 1T, minuto del feed 46'-50'): diagnosi Safe
  ESATTO «Solo nel 2° tempo: no», nessun ingresso; dopo `SecondHalfKickOff` il check passa; la pagina Safe uguale.
- [ ] **3.11** (serve: sessione scalper maker in PROVA con una chiusura abbinata in parte; MAI soldi veri): uscita = ordine
  diretto + eventuale resto col place-and-trim (parcheggio 1,00, LAY a 1,02/1,03 per resti 0,50-0,79), nessun
  `residuo_ricordato`; nei log nessun INVALID_PROFIT_RATIO / INVALID_BET_SIZE.
- [ ] **10.1 Safe BASE** (serve: partita in PROVA all'intervallo, `FirstHalfEnd`, minuto del feed 46'-56'): diagnosi BASE
  «Solo nel 2° tempo: no», nessun ingresso; dopo `SecondHalfKickOff` il check passa; pagina Safe uguale.
- [ ] **10.1 Scalper** (serve: PROVA, ingresso abbinato sotto 0,50; MAI soldi veri): attivita' `scavalco` (punta 1,00 poi
  chiusura al centesimo), posizione PIATTA (differenza fra gli esiti <= 0,02); attivita' `loss_cap` con due cifre (perdite
  vere / residui), scatta solo sulle perdite vere.

## Lista di controllo del par. 6 (prova a schermo dell'utente, app riavviata dopo build)

- [ ] **6.1** Match Replay calcio, 35797769: tabellone 1-0 al gol del 30', 1-1 per tutto l'intervallo, «2 - 1 · FT»
  all'ultimo passo; simboli sulla barra al loro istante; nessun avviso di incoerenza (lo strumento 3.4 la da' OK).
- [ ] **6.2** Match Replay -> Applica bot: solo i 6 bot calcio; scenario; Prova/Soldi veri simulati; Parametri a tendina
  (Ingresso/Uscita/Importi/Tetti/Filtri/Tempi, «di serie», «cambiato», «Ripristina»); «accendi all'istante del cursore»;
  Media Under con i clic sulla barra; risultato con bot, scenario, parametri cambiati, istante; ordini sul ladder in
  sola lettura.
- [ ] **6.3** Scheda Scalper -> Media Under: «Attiva adesso (PROVA)» / «(SOLDI VERI)» con conferma; interruttore
  «Rientri automatici pre-match con i filtri» spento di serie; esito del clic sotto il pulsante. Prova su partita
  LIQUIDA, in PROVA.
- [ ] **6.4** Replay Tennis (`/tennis/replay`, voce nella barra laterale e bottone «Replay» della TennisNav): le 83
  partite importate col 3.7 (MAI partite calcio); riproduzione; simboli tennis DENTRO la barra con legenda; tabellone;
  menu dei mercati (MATCH_ODDS e, dove c'e', SET_BETTING); ladder e ladder training (bet-delay 3 s); «Applica bot» con
  i SOLI 5 bot tennis; nessun avviso di coerenza su una partita sana. Match Replay calcio invariato. Nota: la 35790089
  mostrera' «Marcelo Tomas Barrios V» (reperto 4).
- [ ] **6.5** Omega: pannello Motore v3 con «Includi Any Other» (acceso).

## Cosa NON ho potuto verificare e perche'
- Tutto cio' che richiede l'app riavviata o una partita in corso (3.1, 3.2, 3.3, 3.6, 3.9, 3.10 a schermo, 3.11, 10.1, 6.x).
- 3.5 sul codice nuovo: nessuna partita calcio caricata dopo il merge.
- 3.8: nome Betfair completo del runner non presente sul PC.
- Query del par. 2 con `psql`/psycopg: il `.env` del PC ha solo `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` (nessuna
  stringa Postgres); le ha fatte il coordinatore via MCP in sola lettura. Le mie letture (3.5, 3.8, 3.10, conteggi 3.7)
  sono GET su PostgREST (sonde nella scratchpad, nessuna scrittura).
- `npm run build` (1.5): lo fa l'utente.

## Scritture fatte sul DB
Solo quelle dell'import 3.7 (tabelle `tennis_replay_*`, vuote prima), prescritte dal protocollo e autorizzate dal
coordinatore dopo la verifica della migrazione 2.2. Nessun'altra scrittura.

Firma: agente con il DB (Opus), verificato da: in attesa del coordinatore.
