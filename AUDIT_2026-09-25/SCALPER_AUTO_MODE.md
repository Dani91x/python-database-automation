# SCALPER CALCIO: AUTO-MODE, ORDINI FLAGGATI «scalper», CANALE 47338 (25/09/2026)

Lavoro di un delegato del coordinatore in un worktree su base `d1ef6cb`. Niente commit, nessuna
scrittura sul DB vero, nessun processo nuovo, nessun replay lanciato.
Patch: `AUDIT_2026-09-25/scalper_auto_mode.patch` (file già tracciati) più i file nuovi elencati
in fondo.

Ordine dell'utente (testuale): «Lo scalper deve lavorare da solo su tutte le partite del feed come
gli altri bot, i suoi ordini devono finire flaggati col nome "scalper", pubblicalo sul canale come
tutti gli altri.»
**La strategia non è stata toccata**: maker, sniper, theta, tick, soglie e bias sono invariati.
`scalper_bot.py`, `sniper_bot.py`, `theta_bot.py` e `bias_resolver.py` non sono stati modificati.

## 1. Interruttore globale e auto-mode

**Prima.** Lo scalper si armava solo per singola partita, dalla card (`scalper_activate`, una riga
`scalper_control` per evento). Il supervisore (`scalper_service.py`) lanciava una sessione per ogni
riga in stato 'requested'. In Control Room la riga scalper offriva solo FERMA
(`interruttori.ts`, `armoPerPartita`, `ScalperSiArmaPerPartita`).

**Dopo.**
- **Interruttore**: nuova tabella `scalper_service_control`, con una sola riga (id=1). Colonne:
  `status` running/stopped, `mode` paper/live, `strategia` maker/bias/both, `stake`, `params`,
  `stats`, `started_at`, `stopped_at`. Tre RPC owner-only:
  - `scalper_auto_activate(p_mode, …)`: la modalità va scritta. Se lo scalper è già acceso
    nell'altra modalità la chiamata viene rifiutata (paper e live mai insieme).
  - `scalper_auto_stop()`: spegne l'interruttore e ferma **tutte** le sessioni attive in un solo
    gesto atomico, con le stesse transizioni di `scalper_stop`.
  - `scalper_auto_update(p_stake, p_params, p_strategia)`: non tocca `status` né `mode`.
- **Supervisore**: `scalper_service.py`, `giro_auto` (r.330), chiamato a ogni giro del loop
  (r.719-721).
  - L'interruttore si rilegge ogni 3 s. Se cambia, il giro dell'auto-mode parte subito; altrimenti
    il feed si rilegge ogni 15 s (`AUTO_GIRO_S`).
  - **Feed unico**: `safe_strategy_scan` con `sport='calcio'`, solo le chiavi utili via
    `payload->k` (`Db.feed_calcio` r.103). Il feed conta solo se il battito dello scanner ha al
    massimo 30 s.
  - **Ordine delle partite**: prima quelle in gioco, poi per orario d'inizio, poi per event_id
    (`auto_mode.partite_dal_feed` r.179).
  - **Tetto**: `params.auto_max_partite`, poi l'env `SCALPER_AUTO_MAX_PARTITE`, altrimenti **2**;
    massimo 4 (`auto_mode.py` r.68-69, r.128).
    - Motivo: ogni sessione è un processo con il suo login e la sua connessione stream (in live
      anche l'order stream). Betfair ammette 10 connessioni per app key. Lo scanner ne usa 4 di
      serie; i runner calcio e tennis 1 ciascuno, più 1 ciascuno in live. Nel caso peggiore
      restano 2 connessioni. Il limite dei 200 mercati per connessione è lontano (4-12 mercati a
      sessione).
    - Il tetto conta anche le sessioni armate dalla card, perché il vincolo sono le connessioni.
  - **Vita della sessione**: non si arma una partita già oltre KO + vita. La vita è 600 s per il
    maker, 4200 s con l'intervallo (ht), 7800 s con sniper/theta. Sono gli stessi numeri che la
    sessione aveva inline; ora `scalper_session.py` r.1228 li prende da `auto_mode.vita_sessione_s`
    (r.150). Senza questo filtro, per ogni partita in gioco il maker farebbe login, leggerebbe il
    catalogo e chiuderebbe la sessione al primo battito.
  - **Righe armate**: `origine='auto'`, `dry_run` uguale alla modalità dell'interruttore; `stake`,
    `strategia` e `params` vengono dall'interruttore, senza la chiave del tetto; `stats` timbrate
    con l'avvio dell'app. Se il follow `live_follow` manca (lo pretende la FK di `scalper_control`)
    viene creato con `ignore_duplicates`: un follow dell'utente non viene mai riscritto e non si
    imposta `record` (r.165, r.179).
  - **Non si riarmano mai** (`auto_mode.motivo_esclusione` r.227):
    - le partite chiuse a mano, cioè righe 'stopped' armate DOPO l'accensione corrente;
    - le partite in 'error' o 'done';
    - quelle in attesa di consenso bias ('armed');
    - quelle con follow CLOSED, UPLOADED o ERROR.

    Una riga 'stopped' di prima dell'accensione si riarma: spegnere e riaccendere è un gesto
    dell'utente, come nel tennis.
  - **Spento**, oppure **partita uscita dal feed da almeno 60 s** con lo scanner vivo: stop pulito
    ('stopping', quindi force-flat e attesa del flat) delle **sole** sessioni con
    `origine='auto'` (`Db.ferma_auto` r.195, filtro `.eq("origine","auto")`). Con il feed muto o
    non letto non si ferma niente.
  - **Paper e live mai insieme**: se una sessione con processo è attiva nella modalità opposta, non
    si arma niente di nuovo e lo si dice.
  - **Avvio dell'app (FASE A)**: `avvio_app.ferma_al_nuovo_avvio` riporta l'interruttore a
    stopped/paper a ogni avvio nuovo (Guardia "scalper-auto", r.667). Finché il controllo non
    riesce non si arma niente.
  - I fatti del giro finiscono in `stats.auto` della riga dell'interruttore, scritti solo quando
    cambiano: armate, fermate, tetto, motivo del blocco, feed (letto, vivo, partite, età, fonte),
    P&L lordo e ordini vivi.
- **Sessione in paper**: comportamento invariato. `dry_run=true` porta a `paper_trade=True` e, in
  caso di crash, a nessuno sweep REST (`_order_client_kwargs`, `_handle_flumine_crash`, non
  toccati). Le righe automatiche in paper nascono con `dry_run=True`: test
  `test_acceso_arma_dal_feed…` più le mutazioni "live nasce paper" e "paper nasce live".
- **Control Room**:
  - `interruttori.ts`: AVVIA chiama `attivaScalperAuto(modalita)` (r.864); FERMA chiama
    `fermaScalperAuto()` (r.893). Se la migrazione manca si torna al FERMA di prima, sessione per
    sessione; un errore vero invece si propaga. Lo stake usa `aggiornaScalperAuto` (r.946).
  - Il cambio di modalità a caldo è rifiutato (`ScalperModalitaAllAvvio`, r.557). `PannelloBot`
    mostra «prova o soldi veri si scelgono all'avvio: per cambiare, ferma e riavvia» (r.771-778).
  - La card per partita resta e l'auto-mode si aggiunge a lei. `scalper_activate` è ridefinita con
    lo stesso corpo più `origine='manuale'`.
  - `useControlRoom.rigaScalper` (r.2089) dice acceso anche senza sessioni. La nota ha la forma
    «auto-mode: N sessioni (M dal feed) - tetto 2 - feed calcio: 7 partite, scanner 4 s fa
    (safe_strategy_scan) - 3 ordini vivi [- LIVE: le partite del feed nascono con soldi veri]».
    Se la migrazione manca, la nota lo dice.
  - `scalper_uscite_automatiche` ora scrive anche sulla riga dell'interruttore, così le sessioni
    armate dopo il cambio nascono con quella scelta (dubbio 5 del referto uscite).

## 2. Ordini flaggati «scalper»

**Prima.** Lo specchio della sessione (`_SessionOrderMirror`) non scriveva `source`, quindi valeva
il default 'runner'. `reconcile_worker._fonte_di` metteva quegli ordini nella voce "manuale_app" e
la pagina li spostava a mano per bet_id.

**Dopo.**
- `scalper_session.py` r.409: `_SessionOrderMirror._order_row` imposta
  `source='scalper'` (`SOURCE_SPECCHIO`, r.33). È l'unico scrittore dello specchio della sessione
  (`_order_mirror_loop`), quindi copre maker, sniper e theta, e ingresso, chiusura, scratch, stop,
  flatten e force-flat, in paper e in live.
- `reconcile_worker.py` r.634 e r.793: nuova voce `scalper` in `FONTI` e in `_fonte_di`.
- Migrazione: il CHECK `betfair_live_orders_source_check` viene ricreato con 'scalper' in più
  (NOT VALID), solo se il CHECK esiste.
- `get_scalper_control_room` accettava già `source IN ('runner','scalper')`.
- Pagina, `useControlRoom` r.1887: la sottrazione dal "manuale app" per bet_id resta solo per gli
  ordini vecchi (source 'runner'), oppure per tutti se il conto non dichiara la voce 'scalper'
  (runner di prima). `composizioneObiettivo.FONTI_REALI` include 'scalper' e c'è
  `fontiDichiarate`.
- Posizioni chiuse: le sessioni chiuse erano già `__bot: 'scalper'` (`righeChiuseScalper`),
  invariato.
- In più: `stats.ordini_vivi` della sessione (`_ordini_vivi`, r.207, sola lettura del blotter).

## 3. Stato sul canale

**Scelta.** Porta dedicata **47338** dentro il **supervisore**, che l'app già avvia
(`desktop/main.js:292`).
- Un processo ha un solo canale (difetto D1) e le sessioni sono processi figli: non potrebbero
  pubblicare su un canale altrui.
- Il supervisore legge già ogni 3 s tutte le righe di sessione, quindi non servono letture in più.
- Stesso schema del 47337 (ponte tennis): sola lettura, interruttore `SCALPER_CANALE` (default
  SPENTO), porta sovrascrivibile con `SCALPER_WS_PORT` (`canale_bot.py` r.103-132).

Topic:
- `scalper_stato`: la riga di `scalper_service_control`, com'è stata restituita dalla scrittura
  delle stats, oppure riletta quando cambia.
- `scalper_sessioni`: la riga di `scalper_control` appena letta, solo se cambia. Una sessione che
  esce dalle attive viene riletta una volta e pubblicata nel suo stato finale (`PubblicaSessioni`,
  r.574).

**Pagina.**
- `localChannel.ts` r.67: `scalper: 47338`, sola lettura, nessuna sveglia.
- `lib/scalperCanale.ts` (nuovo, puro). Il canale non aggiunge sessioni. Una sessione nuova, o che
  diventa ferma, provoca la rilettura mirata subito (`RilettureMirate`, gruppo 'scalper',
  `useControlRoom` r.1399). Un messaggio vince solo se è più fresco dell'inizio della lettura.
- `useControlRoom` r.1526 (sottoscrizione) e r.1652 (`vistaScalper`). La fonte e l'età sono
  dichiarate: «dal canale locale, N s fa» oppure «dal database, letto N s fa». Se il canale cade
  lo stato va a 'off', l'età viene azzerata e si torna al database. Il ripiego resta il giro dei
  30 s.

## 4. Migrazione

`migrations/scalper_auto_mode_2026-09-25.sql` è additiva e idempotente, e **la applica l'utente**
dopo `uscite_automatiche_scalper_2026-09-25.sql`. Contenuto:
- colonna `scalper_control.origine` (con CHECK);
- tabella `scalper_service_control` con la riga seed, RLS attivo e revoke per anon/authenticated;
- le tre RPC `scalper_auto_*`;
- `scalper_uscite_automatiche`, `scalper_activate` e `get_scalper_control_room` ridefinite. I test
  verificano, diffando riga per riga i corpi rispetto alle migrazioni di prima, che le sole
  differenze siano `origine` e `servizio`;
- il CHECK sulla `source`.

## 5. Test e falsificazione

- **Python**: nuovo `Betfair/stream/tests/test_scalper_auto_mode_2026_09_25.py` (66 test). Include
  un finto Db con gli stessi metodi del vero, le query vere su un client che registra la catena
  PostgREST, lo specchio vero e il contratto SQL. `test_scalper_control_room_2026_09_24.py`
  aggiornato (lo specchio ora ha `source=='scalper'`). Le suite dei file toccati e di quelli vicini
  (scalper, reconcile, pnl reale, canale f3 di tutti i bot, avvio_app, banco/registro, tennis
  auto-mode): **637 passati, 6 saltati** (saltati preesistenti: registrazioni assenti).
- **Vitest** (nuovi e toccati, 20 file): **480 passati**.
  - Nuovi: `scalperCanale.test.ts`, `scalperAuto.test.ts` (testi esatti),
    `useControlRoom.scalperCanale.test.tsx` (hook vero: interruttore, sessione nuova → rilettura,
    overlay, arresto → rilettura, stato dal canale, canale giù).
  - Riscritti secondo la decisione del 25/09: `interruttoriScalper.test.ts` e 3 casi di
    `PannelloBotScalper.test.tsx`.
  - Aggiornati: `interruttori.test.ts` (importo dello scalper), `localChannel.test.ts` (47338),
    fixture `pnlRealeBetfair.test.ts` (voce scalper).
- **tsc** (`npx tsc -p tsconfig.app.json --noEmit`): **0 errori miei**. Restano **8 errori
  TS2307 preesistenti sulla base `d1ef6cb`**: `EtaDato` e `@/lib/etaDato` importati da 4 file di
  `components/dashboard/` ma **non committati**. I file esistono non tracciati solo nel checkout
  principale. Segnalato al coordinatore.
- **Falsificazione**: `AUDIT_2026-09-25/mutazioni_scalper_auto_mode.py`, con 48 mutazioni del
  codice di produzione e ripristino dal contenuto in memoria.
  - Python: 36 su 36 ROSSE.
  - Frontend: 12 su 12 ROSSE.
  - Una mutazione era inizialmente VERDE, "modalità a caldo" su `cambiaModalita`: la guardia è
    doppia e la seconda (`cambiaModalitaServizio`) la copriva. Ho spostato la mutazione sulla
    seconda guardia, che ora risulta ROSSA; la doppia guardia resta.

## 6. Replay (da lanciare dal coordinatore, uno solo)

```
python -m Betfair.stream.backtest.certifica scalper_calcio --scenari tutti --diario --worker 1
```

Atteso: **parità con il riferimento del 24/09**, cioè stesse azioni, stati e fasi, scenario per
scenario.
- Il replay esegue la `run_session` vera, dove la strategia è invariata e i numeri della vita
  sessione sono gli stessi (ora da `auto_mode`).
- Il supervisore e l'auto-mode non fanno parte del banco.
- Due differenze attese, **non di condotta**:
  - le righe di specchio catturate portano `source='scalper'`;
  - `stats_finali` ha la chiave in più `ordini_vivi`, che a fine sessione dovrebbe valere 0.
- Qualunque altra differenza è una regressione mia.

## 7. Non verificato / da decidere

- Nulla è stato eseguito contro il DB vero o con l'app. Non verificati:
  - le RPC;
  - l'upsert con `ignore_duplicates` su `live_follow` (FK) e su `scalper_control`;
  - la sintassi `alias:payload->k` sul calcio (la stessa del tennis, non osservata dal vivo);
  - il comportamento del runner calcio con i follow creati dall'auto-mode (li streamma e li
    ritira da solo: `_FOLLOW_STALE_AFTER`, uploader SWEEP; dedotto dal codice).
- **LIVE automatico**: con l'interruttore in soldi veri le partite del feed nascono con
  `dry_run=false`, cioè ordini reali (doppia conferma in UI, come Omega e Mike). Il tennis invece
  fa nascere le righe in dry-run. **Decisione dell'utente**, e ricordargli che lo scalper va
  certificato sul replay prima del live.
- Lo stake di default è 25 € (lo stesso della card e della sessione), modificabile dalla riga.
- Il tetto di 2 è dedotto dal conteggio delle connessioni nel codice, non misurato. Anche lo
  scanner potrebbe usarne di più (`SAFE_STRATEGY_STREAM_CONNS`).
- Il maker pre-match (entrate chiuse 7' prima del KO) armato su partite già in gioco ma entro
  KO+10' non entrerà: vive fino a KO+10' e si chiude. Ordinando le partite «in gioco prima» le
  prime armate possono essere di questo tipo. Da valutare con l'utente se, per il solo maker,
  preferire le partite pre-KO. Non l'ho fatto: sarebbe un filtro di strategia.
- `customerStrategyRef` su Betfair: non impostato a 'scalper'. Il filtro dell'order stream di
  flumine usa `config.customer_strategy_ref`, quindi cambiarlo è money-critical e fuori perimetro.
  Il flag è quello dello specchio.
- Gli avvisi «EXECUTABLE assente dal conto» in `reconcile_worker` non escludono le righe 'scalper'
  (prima non escludevano 'runner'). Comportamento invariato.
- Per il canale va impostato `SCALPER_CANALE=1` nel `.env` (spento di serie, come gli altri).
- La race 'requested' → 'stopping' con la sessione in fase di arming (la sessione riscrive
  'arming') esiste già con `scalper_stop`. L'auto-mode ci riprova al giro successivo.
- `npm run build` non eseguito (worktree).

## File

**Modificati**:
- `Betfair/stream/canale_bot.py`
- `Betfair/stream/reconcile_worker.py`
- `Betfair/stream/scalper/scalper_service.py`
- `Betfair/stream/scalper/scalper_session.py`
- `Betfair/stream/tests/test_scalper_control_room_2026_09_24.py`
- `frontend/src/components/controlroom/{PannelloBot.tsx,righeBot.ts,useControlRoom.ts,PannelloBotScalper.test.tsx}`
- `frontend/src/lib/{composizioneObiettivo.ts,interruttori.ts,localChannel.ts,scalperControlRoom.ts,interruttori.test.ts,interruttoriScalper.test.ts,localChannel.test.ts,pnlRealeBetfair.test.ts}`

**Nuovi**:
- `Betfair/stream/scalper/auto_mode.py`
- `Betfair/stream/tests/test_scalper_auto_mode_2026_09_25.py`
- `frontend/src/lib/scalperCanale.ts`
- `frontend/src/lib/scalperCanale.test.ts`
- `frontend/src/lib/scalperAuto.test.ts`
- `frontend/src/components/controlroom/useControlRoom.scalperCanale.test.tsx`
- `migrations/scalper_auto_mode_2026-09-25.sql`
- `AUDIT_2026-09-25/mutazioni_scalper_auto_mode.py`
- questo file
- `AUDIT_2026-09-25/scalper_auto_mode.patch`

**Non toccati**: `safe_strategy/**`, `omega/**`, `mike/**`, `tennis_live/**` (solo importato
`tennis_live/auto_mode.scegli_partite`/`eta_s`, puri), `live_order_worker.py`, `backtest/**`,
`Scheda*.tsx`.

Nota: nel worktree ho creato la junction `frontend/node_modules` verso il checkout principale; va
rimossa con `cmd /c rmdir`, **mai** con cancellazione ricorsiva.
