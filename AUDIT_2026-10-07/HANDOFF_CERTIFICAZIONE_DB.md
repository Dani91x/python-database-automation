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
| D | Replay TENNIS da zero (pagina separata, tutti i mercati, Applica bot tennis), registrazione tennis di tutti i mercati, curatore calcio | DA COMPLETARE | `Betfair/stream/tennis_replay/**`, `tennis_live/tennis_runner.py`, `tennis_recorder.py`, `mercati_registrati.py`, `Betfair/stream/curator.py`, `db.py`, `frontend/src/pages/TennisReplay.tsx`, `components/tennis-replay/**`, `migrations/replay_tennis_2026-10-07.sql` | `AUDIT_2026-10-07/REPLAY_TENNIS.md` |
| K | Safe ESATTO solo nel 2T (decisione dell'utente) | DA COMPLETARE | `Betfair/safe_strategy/**` | `AUDIT_2026-10-07/SAFE_ESATTO_SECONDO_TEMPO.md` |
| L | Scalper/sniper CALCIO: chiusura al centesimo (ordine dell'utente) | DA COMPLETARE | `Betfair/stream/scalper/scalper_bot.py`, `sniper_bot.py` | `AUDIT_2026-10-07/SCALPER_CHIUSURA_AL_CENTESIMO.md` |

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
    DA COMPLETARE con l'eventuale migrazione della fase 2 del replay tennis.

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
3.10 **Safe ESATTO solo nel 2T** (K): DA COMPLETARE.
3.11 **Scalper calcio chiusura al centesimo** (L): DA COMPLETARE.

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
- Omega prima/dopo: DA COMPLETARE. Safe esatto prima/dopo: DA COMPLETARE. Scalper chiusura al centesimo: DA COMPLETARE.

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
6.4 Replay Tennis (sezione Tennis della barra laterale e bottone «Replay» della TennisNav): DA COMPLETARE.
6.5 Omega: pannello Motore v3 con «Includi Any Other».

## 7. Cosa so che NON e' coperto

- UI mai vista a schermo da nessuno (solo jsdom/vitest).
- Nessuna RPC provata su Supabase vero (DB assente nel cloud).
- Tennis: una sola registrazione vera (35790089, da meta' partita, solo Match Odds).
- Banco tennis: `certifica` non passa i nomi dei giocatori (`_names.json`), quindi i setup di tennis_pro che dipendono
  dai nomi (fade, set transition, break point) non si certificano sul banco ufficiale; lo scenario `gate-aperto` del
  banco tennis cambia anche parametri di strategia regolabili dalla UI (dichiarato nella nota del referto).
- Parcheggio LAY @1,01 del place-and-trim: banda INVALID_PROFIT_RATIO per residui 0,50-0,79 (L, DA COMPLETARE).

## 8. Decisioni aperte dell'utente (NON tue)

- Scalper calcio: come conta i residui il tetto di perdita (in attesa; con L i residui dovrebbero sparire).
- Media under: liquidita' al clic e rischio massimo «al momento no»; da rivedere dopo la prova su partita liquida.
- Tutto il resto deciso il 07/10 (vedi `CRONOSTORIA.md`, sezione 2026-10-07).

## 9. Numeri finali e commit

DA COMPLETARE a fine lavori (suite Python, vitest, tsc, commit finale).
