# PROTOCOLLO DI CERTIFICAZIONE PER L'AGENTE CON ACCESSO AL DB (lavori del 07/10/2026)

Destinatario: l'agente che lavora sul PC dell'utente, con il DB Supabase e l'app.
Autore: il coordinatore della sessione cloud del 07/10. Il ramo e' `claude/eloquent-franklin-g2nyk5`
(commit finale in fondo, par. 9). Comunica in italiano; regole: `CLAUDE.md`, `BRIEF_STANDARD_DELEGATI.md`.

**Cosa NON devi fare.** I replay del banco li ho gia' rieseguiti io di persona (referti nel repo, par. 4):
NON rifarli, salvo il caso esplicito al par. 5.3. NON cambiare strategie, soglie o parametri: le decisioni
aperte sono dell'utente (par. 8). NON applicare migrazioni senza l'utente: le applica lui (par. 2).

**Cosa devi fare.** (1) controllare che il ramo sia quello giusto e che i test passino sul PC (par. 1);
(2) far applicare all'utente le migrazioni e verificarle in SOLA LETTURA (par. 2); (3) chiudere i dubbi
che nel cloud non potevo chiudere perche' non c'era il DB (par. 3); (4) confrontare i numeri dei miei
referti dove indicato (par. 4); (5) guidare la prova a schermo dell'utente (par. 6); (6) scrivere l'esito
in `CRONOSTORIA.md` (sezione del giorno, tuo blocco) con firma e commit.

Ogni passo ha: COMANDO, ATTESO, SE NON TORNA. Se un passo non torna: fermati su quel punto, scrivilo,
NON correggere di iniziativa codice di strategia; un bug di codice si corregge con test rosso -> verde e
falsificazione, come da brief.

---------------------------------------------------------------------------------------------------

## 0. Mappa dei lavori del 07/10 (cosa e' cambiato e dove)

| # | Lavoro | Commit | File principali | Referto |
|---|---|---|---|---|
| A | Match Replay: tabellone a 0-0 dopo le righe-evento, simboli fuori registrazione, gol persi | `94af2eb` | `frontend/src/lib/replayTimelineEvents.ts` (`punteggioAlTs`), `frontend/src/pages/MatchReplay.tsx` (blocco punteggio), `frontend/src/lib/opportunities/snapshot.ts`, `components/replay/TimelineSlider.tsx` | `AUDIT_2026-10-07/REPLAY_BARRA_SIMBOLI.md` |
| E | Barra/simboli/tabellone come STANDARD per tutte le partite | `267605c` | `lib/replayVerificaBarra*.ts`, `components/replay/AvvisoCoerenzaBarra.tsx`, `frontend/scripts/verifica_barra_replay.ts`, `tools/replay_barra_fixture.py` | `AUDIT_2026-10-07/REPLAY_BARRA_STANDARD.md` |
| F | Scalper TENNIS: sovracopertura dopo chiusura abbinata in parte (parcheggio 2,00 scritto a mano) | `e2ca375` | `Betfair/stream/tennis_scalper/tennis_scalper_bot.py` (`_place_exact`) | `AUDIT_2026-10-07/SCALPER_TENNIS_CP4.md` |
| I | tennis_pro: prezzo dal book (D1), nome IPS troncato (D2), fade solo dopo break del favorito (D3) | `2f502dd` | `Betfair/stream/tennis_scalper/tennis_pro_bot.py` | `AUDIT_2026-10-07/CONFORMITA_BOT_TENNIS.md` par. 11 |
| H | Conformita' bot calcio (solo documenti) | `9ad5bfb` | note in `COSTITUZIONE_MIKE.md`, `COSTITUZIONE_SAFE_STRATEGY.md` | `AUDIT_2026-10-07/CONFORMITA_BOT_CALCIO.md` |
| C | Media under «Attiva adesso» (pulsante in prova e soldi veri, in gioco come pre-match, regola dei cicli) | merge `6edc5b6` | `Betfair/stream/scalper/media_under_bot.py`, `scalper_session.py`, `certificazione.py`, `tools/replay_registrazioni.py`, `frontend/src/lib/mediaUnder.ts`, `lib/mediaUnderAttiva.ts`, `components/live/ScalperPanel.tsx`, `migrations/media_under_attiva_adesso_2026-10-07.sql`, spec `SPEC_MEDIA_UNDER_2026-10-05.md` par.13 | `AUDIT_2026-10-07/MEDIA_UNDER_ATTIVA_ADESSO.md` |
| B | «Applica bot» per gli 11 bot + menu dei parametri | merge `6edc5b6` | `Betfair/stream/backtest/applica_bot.py`, `varianti_bot.py` (nuovo), `registro_bot.py`, `tools/replay_*` di Mike/Omega/Safe/Safe tennis/tennis_live, `frontend/src/lib/applicaBot.ts`, `useApplicaBot.ts`, `replayBotCatalogo.ts` (GENERATO), `components/replay/{ApplicaBot,ParametriBot,EsitoBot}Panel.tsx`, `MatchReplay.tsx` (riquadro) | `AUDIT_2026-10-07/APPLICA_BOT_TUTTI.md` |
| G | Omega CIECO nel 2T dal 29/09 (regressione di `304a8e1d`) | merge `6edc5b6` | `Betfair/omega/omega_service.py` (`_flusso_feed` = MO+CS, `_flusso_feed_ht`), `omega_proposte.py` | `AUDIT_2026-10-07/OMEGA_APERTURA_35760084.md` |
| J | Omega V3 con gli «Any Other» (decisione dell'utente) | merge `6edc5b6` | `Betfair/omega/omega_v3.py`, `omega_engine.py`, `omega_config.py` (`v3_include_aggregate`), `omega_proposte.py`, `frontend/src/lib/omega.ts`, `COSTITUZIONE_OMEGA.md` par.21; banco: `omega/tools/replay_registrazioni.py` (nomi aggregati), `omega/certificazione.py` (A11) | `AUDIT_2026-10-07/OMEGA_ANY_OTHER.md` |
| S | Banco Safe: regolamento mai esercitato nei replay | `4a8370e` (nel merge) | `Betfair/safe_strategy/tools/replay_registrazioni.py` (`process_closed_market`) | `AUDIT_2026-10-07/CONFORMITA_BOT_CALCIO.md` |
| D | Replay TENNIS da zero (pagina separata, tutti i mercati, Applica bot tennis, verificatore della barra tennis), registrazione tennis di TUTTI i mercati (stessa connessione), caricamento automatico a fine partita, curatore calcio con la chiusura dei mercati gia' sospesi | merge `c76b37b` (+ `3136e83` riga del registro) | `Betfair/stream/tennis_replay/{convertitore,caricamento,importa}.py`, `Betfair/stream/tennis_live/{tennis_runner,tennis_recorder,mercati_registrati}.py`, `Betfair/stream/curator.py` (`curate_records`, regola unica), `Betfair/stream/db.py` (`delete_event_rows(market_id=)`), `Betfair/stream/backtest/registro_bot.py` (`_MODULI_TENNIS`), `frontend/src/pages/TennisReplay.tsx`, `components/tennis-replay/**`, `lib/tennisReplay*.ts`, `lib/live.ts` (`fetchFramesAFinestre`), `trainingLadder.ts`/`ladderBacktest.ts`/`LadderBacktestPanel.tsx` (bet-delay del mercato, opzionale), `components/replay/TimelineSlider.tsx` (props opzionali), `App.tsx`, `components/shell/navigazione.ts`, `components/tennis/{TennisNav,TennisMatchStats}.tsx`, `migrations/replay_tennis_2026-10-07.sql` | `AUDIT_2026-10-07/REPLAY_TENNIS.md` |
| K | Safe ESATTO solo nel 2T (decisione dell'utente), bot + pagina | merge `2e70ff5` | `Betfair/safe_strategy/{engine,bot_service,certificazione}.py` (check `secondHalf`, E11), `frontend/src/lib/{safeStrategy,faseIps,safeStrategyScan}.ts` | `AUDIT_2026-10-07/SAFE_ESATTO_SECONDO_TEMPO.md` |
| L | Scalper/sniper CALCIO: chiusura al centesimo (ordine dell'utente) + banco CP4 | merge `41c94b7` | `Betfair/stream/scalper/{scalper_bot,sniper_bot}.py` (`spezza_uscita`, `stato_parcheggio`), `Betfair/stream/backtest/chiusura_parziale.py` (parcheggio BACK @1000 fuori dalla capacita' di CP4) | `AUDIT_2026-10-07/SCALPER_CHIUSURA_AL_CENTESIMO.md` |

Riferimenti «prima delle modifiche» calcolati da me: `AUDIT_2026-10-07/riferimenti_coordinatore/`.

---------------------------------------------------------------------------------------------------

## 1. Ramo e test sul PC (prima di tutto)

1.1 COMANDO: `git fetch origin claude/eloquent-franklin-g2nyk5` e verifica che il commit in cima sia quello
    del par. 9. ATTESO: uguale. SE NON TORNA: chiedi all'utente quale commit e' quello buono.
1.2 COMANDO (radice, `.venv` del PC): `python -m pytest Betfair/ -q -p no:cacheprovider`.
    ATTESO: 0 rossi (nel cloud: numeri al par. 9). SE NON TORNA: un rosso che nel cloud era verde e' quasi
    sempre ambiente (Windows, percorsi, `.env`): leggi il messaggio; se e' codice, scrivilo e fermati.
1.3 COMANDO (da `frontend/`): `npx tsc -p tsconfig.app.json --noEmit` e `npx vitest run`.
    ATTESO: tsc 0 errori; vitest 0 rossi.
1.4 Catalogo di Applica bot ALLINEATO: `python -m Betfair.stream.backtest.applica_bot --catalogo-ts` deve
    produrre ESATTAMENTE `frontend/src/lib/replayBotCatalogo.ts` (lo controlla anche il test
    `Betfair/stream/tests/test_applica_bot_tutti_2026_10_07.py`). Su Windows confronta ignorando i fine riga.
1.5 `npm run build` lo fa l'utente ad app CHIUSA (CLAUDE.md), dopo le migrazioni.

## 2. Migrazioni (le applica l'utente, nell'ordine) e controlli in SOLA LETTURA

Pendenti da ieri (06/10), se non gia' applicate: `migrations/segui_live_apri_partita_2026-10-06.sql`,
`migrations/ack_allarmi_replay_cambio_2026-10-06.sql`, `migrations/replay_applica_bot_2026-10-06.sql`.
Nuove del 07/10:

2.1 `migrations/media_under_attiva_adesso_2026-10-07.sql` (RPC owner-only `scalper_media_attiva_adesso(p_event_id, p_id)`;
    prerequisiti: `betfair_live_is_owner()`, tabella `scalper_control`). Controlli:
    - `SELECT proname, prosecdef FROM pg_proc WHERE proname='scalper_media_attiva_adesso';` ATTESO 1 riga, prosecdef=true.
    - `SELECT grantee, privilege_type FROM information_schema.routine_privileges WHERE routine_name='scalper_media_attiva_adesso';`
      ATTESO: `authenticated` e `service_role` EXECUTE; NIENTE `anon`, NIENTE `PUBLIC`.
2.2 `migrations/replay_tennis_2026-10-07.sql` (prerequisito: `public.tennis_is_owner()` da `migrations/tennis_bots.sql`;
    la migrazione si ferma con un messaggio se manca). Tabelle `tennis_replay_eventi`, `tennis_replay_mercati`,
    `tennis_replay_snapshots`, `tennis_replay_punteggio`; RPC `list_replays_tennis`, `get_replay_tennis_meta`,
    `get_replay_tennis_frames`. Controlli:
    - le 4 tabelle esistono con RLS attiva: `SELECT relname, relrowsecurity FROM pg_class WHERE relname LIKE 'tennis_replay_%';` ATTESO tutte true.
    - nessun privilegio ad `anon` sulle tabelle e sulle 3 RPC (stesse query di 2.1 su `table_privileges`/`routine_privileges`).
    - le tabelle e le RPC del calcio (`live_market_snapshots`, `list_replays`, `get_replay_*`) INVARIATE:
      `SELECT pg_get_functiondef('public.list_replays(integer)'::regprocedure);` uguale a `migrations/live_stream_rpc.sql`.
    La fase 2 del replay tennis (Applica bot tennis) NON ha migrazioni: usa la coda esistente
    `request_backtest` / `get_replay_bot_esito` di `migrations/replay_applica_bot_2026-10-06.sql`.
2.3 Nessun'altra migrazione oggi (Omega, Safe, scalper, tennis_pro, banco: solo codice).

## 3. Dubbi che nel cloud non potevo chiudere (servono DB o PC)

3.1 **Media under, RPC vera** (C): dopo 2.1, con una sessione Media Under in PROVA su una partita qualunque:
    chiama dalla scheda «Attiva adesso»; ATTESO in `scalper_control.params` la chiave `media_attiva_adesso {id, ts}`
    e, entro un book, `stats.media_comando.esito = 'eseguito'` con prezzo e importo; riga in `scalper_trades`/
    `betfair_live_orders` della punta allo stake base. Query: `SELECT params->'media_attiva_adesso', stats->'media_comando' FROM scalper_control WHERE event_id='<ev>';`
3.2 **Media under, riavvio dopo un clic** (C): riavvia il servizio dello scalper a posizione aperta in PROVA:
    ATTESO nessuna seconda punta per lo stesso id (`stats.media_comando.id` invariato, una sola riga d'ingresso).
3.3 **Applica bot dal worker vero** (B): il worker del Backtest (`python -m Betfair.stream.backtest.worker`, parte con l'app)
    riceve `request_backtest` con `params.tipo='applica_bot'` e i campi nuovi `parametri`, `dal_ms`, `clic_ms`;
    `get_replay_bot_esito` restituisce `parametri_usati`, `parametri_cambiati`, `dal_ms`. Verifica una richiesta
    per un bot calcio (Mike, `base`) e una per un bot tennis su una registrazione del PC: ATTESO DONE e righe.
    Se la RPC rifiuta i campi nuovi (whitelist dei params lato SQL), scrivilo: e' una migrazione mancante.
3.4 **Strumento della barra su TUTTE le partite del DB** (E): da `frontend/`:
    `npx vite-node scripts/verifica_barra_replay.ts --env-file ../.env` (variabili `SUPABASE_URL` o `VITE_SUPABASE_URL` +
    `SUPABASE_SERVICE_ROLE_KEY`; uscita 0 = tutto coerente, 1 = incoerenze, 2 = errore; opzioni `--evento`,
    `--limite`, `--solo-incoerenti`, `--senza-note`, `--json`). ATTESO: 0 incoerenze (le «note» sui buchi sono
    informative). Ogni incoerenza: codice e istante sono nel testo; riportali, NON correggere a mano i dati.
3.5 **Curatore del calcio** (D, decisione 3 dell'utente): le partite caricate DOPO il merge portano anche le righe di
    chiusura dei mercati gia' sospesi. Verifica su una partita nuova: `SELECT market_id, status, count(*) FROM live_market_snapshots WHERE event_id='<ev>' GROUP BY 1,2;`
    ATTESO: i mercati regolati hanno almeno una riga `CLOSED`. Le partite VECCHIE non cambiano (nessun ricaricamento automatico).
3.6 **Registrazione tennis di tutti i mercati** (D, decisione 1): alla prima partita tennis con REC acceso:
    nel log del runner tennis `[tennis-rec] <ev>: N mercati in piu' da registrare` e `mercati registrati sulla
    stessa connessione: accesi [...]`, nessun `STREAM DUPLICATO`; nel file `<ev>.raw.jsonl` righe con
    `marketType` diversi da MATCH_ODDS; i bot tennis della partita senza interruzioni oltre la risottoscrizione
    (confronta `tennis_live_ladder.updated_at` con una partita senza REC). A fine partita (circa 60 s dopo la
    chiusura del Match Odds) la partita compare in `list_replays_tennis` con TUTTI i mercati.
3.7 **Import a mano delle registrazioni tennis gia' sul PC** (D): `python -m Betfair.stream.tennis_replay.importa <cartella> --prova`
    (prova, nessuna scrittura) poi senza `--prova`; rilanciarlo deve dare lo stesso numero di righe (idempotente).
3.8 **Nome di Barrios nel catalogo** (I, D2): nel `_names.json` della partita tennis 35790089 sul PC: il nome Betfair
    completo e' «Marcelo Tomas Barrios Vera»? Se e' diverso, scrivilo (la correzione D2 accetta il prefisso unico).
3.9 **Omega sul DB** (G, J): dopo il riavvio dell'app, su una partita in PROVA con Omega acceso: nel 2T
    l'attivita' di Omega NON deve piu' dire `flusso_interrotto`/`no_live_state` per tutto il tempo (prima del fix
    succedeva dal 44'). Query: attivita' `omega_activity` della partita, conteggio per `kind` prima/dopo il 45'.
    Gli «Any Other»: nel pannello parametri del Motore v3 l'interruttore «Includi Any Other» c'e' ed e' acceso.
3.10 **Safe ESATTO solo nel 2T** (K): su una partita in PROVA, nel recupero del 1T (minuto del feed 46'-50',
    `score_raw.matchStatus` del primo tempo) la diagnosi della Safe ESATTO deve dire «Solo nel 2° tempo: no» e
    nessun ingresso; dopo `SecondHalfKickOff` il check passa. La pagina Safe mostra lo stesso check. Se la riga
    dello scanner arriva SENZA `score_raw` (vecchie righe), l'ESATTO resta «n/d: stato IPS assente» e non entra:
    controlla che le righe vive dello scan lo portino (tabella letta da `safe_strategy/bot_db.py::fetch_scan_rows`):
    `SELECT event_id, payload ? 'score_raw' AS ha_stato, payload->'score_raw'->>'matchStatus' AS stato, updated_at FROM safe_strategy_scan WHERE sport='calcio' ORDER BY updated_at DESC LIMIT 20;`
    ATTESO: `ha_stato` true sulle partite in gioco. Se e' false ovunque, l'ESATTO non entrera' MAI: scrivilo subito
    all'utente (e' una condizione d'ingresso, non un dettaglio).
3.11 **Scalper calcio chiusura al centesimo** (L): in PROVA, su una sessione maker, dopo una chiusura abbinata
    in parte: l'uscita e' un ordine diretto + eventuale resto col place-and-trim (parcheggio da 1,00, non 2,00;
    LAY a 1,02/1,03 per resti 0,50-0,79), NESSUN `residuo_ricordato` salvo un ingresso abbinato sotto 0,50
    (unico residuo ammesso, testo «LAY 0.29 @1.67» = l'ordine che lo chiuderebbe). Da NON verificare in soldi
    veri finche' l'utente non lo dice: il place-and-trim di punta e il parcheggio LAY a 1,02/1,03 non sono
    mai stati provati su Betfair vero (rischio INVALID_PROFIT_RATIO/INVALID_BET_SIZE da guardare nei log).
3.12 **Bot tennis dopo il cambio del runner** (D): rifatti da me (identici, par. 4); dal vivo vale 3.6.

## 4. I miei replay (NON rifarli): dove sono e cosa dicono

- Scalper calcio, 8 scenari di sempre x 2 partite: PRIMA `AUDIT_2026-10-07/riferimenti_coordinatore/scalper_base.txt`
  + `scalper_base_sniper.txt`; DOPO l'integrazione `scalper_DOPO_integrazione_07_10.txt`: IDENTICI (esiti, tick,
  decisioni, azioni, stati, NETTO).
- Media under, 18 scenari del pulsante x 2 partite: referti del delegato in `AUDIT_2026-10-07/replay/` (0 violazioni;
  1 NE dichiarato). Sulla 35760084 i cicli del pulsante perdono (mercato con 7 EUR scambiati in tutto: il pulsante
  salta il filtro di liquidita'; decisione dell'utente «al momento no»).
- Bot tennis, tutti gli scenari sulla 35790089: PRIMA `riferimenti_coordinatore/tennis_base_<bot>.txt`;
  tennis_scalper DOPO F: `AUDIT_2026-10-07/replay_scalper_tennis_cp4/`; tennis_pro DOPO I:
  `AUDIT_2026-10-07/replay_conformita_tennis_pro/tennis_pro_tutti_dopo_COORDINATORE.txt` (17/17 OK, identico al delegato).
- Omega (G, del delegato; codice integrato identico byte per byte): `AUDIT_2026-10-07/omega_apertura_35760084/`
  (35760084 `apertura` 438/0 -> 467/2 come il 25/09; `tutti` 20/20 OK su entrambe; 35797769 col motore V3: prima
  solo 1T, dopo 1T + 2T vinti).
- Safe esatto (K, miei): `AUDIT_2026-10-07/replay_safe_esatto/safe_esatto_{prima,dopo}.txt`: base/paper/riavvio/
  chiusura-abbinata-in-parte sulle due partite, esiti IDENTICI 8/8, ESATTO della 35797769 identico e regolato `won`.
- Scalper chiusura al centesimo (L): `AUDIT_2026-10-07/replay_scalper_chiusura_al_centesimo/replay_COORDINATORE_con_fix_banco.txt`
  (miei: chiusura-abbinata-in-parte OK, base OK 44 azioni, paper OK 44 azioni) + referti del delegato nella stessa cartella.
  NOTA: il «base» passa da 167 a 44 azioni perche' il primo ciclo ora chiude VERDE (+0,14) e la missione «un verde
  per fase» ferma gli ingressi (prima 0 verdi e 6 residui): e' l'effetto atteso, non un cambio di strategia.
- Bot tennis FINALI (dopo tutte le integrazioni, runner tennis compreso): `AUDIT_2026-10-07/riferimenti_coordinatore/finale/tennis_finale_<bot>.txt`:
  tennis_flb, tennis_swing, safe_tennis IDENTICI al riferimento del mattino; tennis_pro IDENTICO al «dopo D1-D3»;
  tennis_scalper IDENTICO al «dopo CP4».

## 5. Controlli anti-regressione che restano a te

5.1 Suite intera (par. 1.2/1.3).
5.2 Le fotografie del frontend (`frontend/src/fotografia/`) sono state rigenerate SOLO con righe aggiunte (voce
    «Replay tennis» e bottone «Replay» della TennisNav): `git diff 8226d76 -- frontend/src/fotografia/snapshot | grep '^-[^-]'`
    ATTESO: nessuna riga tolta.
5.3 Replay sul PC SOLO se hai registrazioni che io non avevo (tennis in particolare: l'utente ne ha altre):
    `python -m Betfair.stream.backtest.certifica <bot> <evento> --data-dir <cartella> --scenari tutti --worker 1`
    per tennis_pro, tennis_scalper, tennis_flb, tennis_swing, safe_tennis. ATTESO: 0 violazioni. Una violazione
    nuova: scrivila con il referto, non correggere di iniziativa.

## 6. Prova a schermo con l'utente (app riavviata dopo migrazioni e build)

6.1 Match Replay (calcio), partita 35797769 se caricata: tabellone 1-0 al gol del 30', 1-1 per tutto l'intervallo,
    «2 - 1 · FT» all'ultimo passo; simboli sulla barra al loro istante; nessun avviso di incoerenza.
6.2 Match Replay -> Applica bot: solo i 6 bot calcio; scenario; Prova/Soldi veri simulati; Parametri a tendina
    (gruppi Ingresso/Uscita/Importi/Tetti/Filtri/Tempi, «di serie» accanto, «cambiato» evidenziato, «Ripristina»);
    «accendi all'istante del cursore»; per la Media Under i clic aggiuntivi sulla barra; risultato con bot,
    scenario, parametri cambiati, istante di accensione; ordini del bot sul ladder in sola lettura.
6.3 Scheda Scalper -> Media Under: pulsante «⚡ Attiva adesso (PROVA)» / «(SOLDI VERI)» con conferma in soldi veri;
    interruttore «Rientri automatici pre-match con i filtri» (spento di serie); sotto il pulsante l'esito del clic.
    L'utente prova su una partita LIQUIDA, in PROVA.
6.4 Replay Tennis (voce «Replay tennis» nella sezione Tennis della barra laterale e bottone «Replay» della
    TennisNav, rotta `/tennis/replay`): dopo 2.2 e l'import (3.7), elenco delle partite tennis (MAI partite
    calcio), riproduzione, barra con i simboli tennis DENTRO la barra (set, break, tie-break) con la legenda,
    tabellone tennis all'istante, menu dei mercati tennis, ladder e ladder training (bet-delay del mercato: 3 s
    sul Match Odds tennis), pannelli; «Applica bot» con i SOLI 5 bot tennis; avviso di coerenza della barra
    assente su una partita sana. Il Match Replay calcio deve restare com'era (nessun bot tennis, nessuna partita tennis).
6.5 Omega: pannello Motore v3 con «Includi Any Other».

## 7. Cosa so che NON e' coperto

- UI mai vista a schermo da nessuno (solo jsdom/vitest).
- Nessuna RPC provata su Supabase vero (DB assente nel cloud).
- Tennis: una sola registrazione vera (35790089, da meta' partita, solo Match Odds).
- Banco tennis: `certifica` non passa i nomi dei giocatori (`_names.json`), quindi i setup di tennis_pro che dipendono
  dai nomi (fade, set transition, break point) non si certificano sul banco ufficiale; lo scenario `gate-aperto` del
  banco tennis cambia anche parametri di strategia regolabili dalla UI (dichiarato nella nota del referto).
- Parcheggio LAY del place-and-trim: corretto per lo scalper CALCIO (L: quota dentro la banda); i bot tennis
  pro/FLB/swing (`condotta_ordini`) e lo scalper tennis parcheggiano ancora a 1,01: per residui 0,50-0,79 Betfair
  rifiuterebbe (INVALID_PROFIT_RATIO). Non corretto oggi (scadenza): e' il prossimo cantiere; il banco non lo simula.
- Media under: replay lenti oltre il tetto del banco (alcuni giri dei clic fino a 4090 s); Omega `tutti` 35797769 33 min.
- Reperti del banco aperti (non toccano i bot): Omega RB-1..RB-5 (`OMEGA_APERTURA_35760084.md`), Safe tennis/tennis:
  `certifica` senza nomi, `gate-aperto` che cambia parametri regolabili; Omega A11 sugli aggregati corretto.
- La pagina di anteprima (`src/anteprima/safeRadarFinto.ts`) costruisce righe senza `score_raw`: l'ESATTO li'
  risulta n/d (solo anteprima, non l'app vera).
- La cartella temporanea del bisect di Omega (`<scratchpad della sessione cloud>/bisect`) e' rimasta nel container
  cloud: non riguarda il PC.

## 8. Decisioni aperte dell'utente (NON tue)

- Scalper calcio: (a) come conta i residui il tetto di perdita (con L i residui sono spariti salvo il caso C3);
  (b) chiudere anche il residuo C3 (ingresso abbinato sotto 0,50) con due ordini legali (punta 1,00 + banca al
  centesimo, costo ~ lo spread su 1 EUR)?
- Safe BASE «dal 55'»: il minuto del feed arriva a 56' durante l'intervallo, quindi puo' entrare all'intervallo.
  Proposta: stessa regola dell'ESATTO (solo 2T).
- Media under: liquidita' al clic e rischio massimo «al momento no»; da rivedere dopo la prova su partita liquida.
- Tutto il resto deciso il 07/10 (vedi `CRONOSTORIA.md`, sezione 2026-10-07).

## 9. Numeri finali e commit

Sul ramo finale, nel cloud (Python 3.13, flumine 2.13.11, betfairlightweight 2.23.2), rieseguito da me:
- `python3 -m pytest Betfair/ -q -p no:cacheprovider`: **10651 passati, 55 saltati, 6 xfail, 0 rossi** (424 s)
  -> `AUDIT_2026-10-07/riferimenti_coordinatore/finale/suite_python_finale.txt`.
- frontend: `npx tsc -p tsconfig.app.json --noEmit` **0 errori**; vitest a blocchi (la suite intera supera i 10
  minuti per comando nel cloud): `src/lib` 152 file / 2651 verdi, `src/components` + App 168 / 2130 verdi, resto
  (pages, fotografia, anteprima, hooks, ...) 29 file / 462 verdi + 50 saltati: **5243 verdi, 0 rossi**.
- Fotografie: rispetto a `8226d76` solo righe AGGIUNTE (537), 0 tolte.
- Commit finale del ramo: vedi `git log -1 origin/claude/eloquent-franklin-g2nyk5` (il commit che contiene
  questo file nella versione definitiva). Base del giorno: `8226d76`.
- `npm run build`: NON fatto (lo fa l'utente sul PC ad app chiusa).
