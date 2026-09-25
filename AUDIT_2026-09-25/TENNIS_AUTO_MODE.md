# TENNIS AUTO-MODE e USCITE AUTOMATICHE/MANUALI — 25/09/2026

Delegato del coordinatore, worktree su base `372158e`. Niente commit, niente DB vero, nessun processo nuovo.
Patch: `AUDIT_2026-09-25/tennis_auto_mode.patch` (file tracciati) + file nuovi elencati in fondo.

## 0. Il reperto (perché «non partono»)

`tennis_bot_service.riconcilia_interruttori` (base `372158e`, righe 385-481) armava la coppia
(partita, bot) SOLO su `_followed_event_ids()`, cioè le partite seguite a mano nel Terminale.
Con zero partite seguite scriveva `motivo_blocco = "acceso, ma nessun evento tennis seguito in questo
momento"` (base r.438). La Control Room lo mostra così: «acceso ma non apre: …»
(`PannelloBot.tsx:641-648`, testo dal servizio via `useControlRoom.ts:1920`).

## 1. Auto-mode all'attivazione

**Prima:** armava solo le partite seguite a mano.
**Ora** (`Betfair/stream/tennis_live/tennis_bot_service.py`):
- `riconcilia_interruttori` (r.402): le partite seguite a mano restano quelle di sempre (stesso codice,
  r.~505-521). In più, per ogni bot acceso, sezione AUTO-MODE (r.523-555):
  - lista partite dal FEED UNICO: `safe_strategy_scan` righe `sport='tennis'`, la stessa tabella che legge
    Safe (`safe_strategy/bot_db.py:889 fetch_scan_rows`); lettura in `tennis_db.list_tennis_feed_rows`
    (r.141) che prende SOLO le chiavi utili (`p1,p2,competition,open_date,inplay,mo_market_id,mo_status`)
    via `payload->chiave`, niente `score_raw`;
  - il feed conta SOLO con lo scanner vivo (battito `safe_strategy_status` ≤ 30 s, stessa soglia di
    `scores/scan_feed.SCANNER_ALIVE_MAX_AGE_SEC`; `_leggi_feed` r.661, `_SCANNER_VIVO_S` r.625);
  - filtri: nessuno di strategia. Solo `mo_market_id` presente e `mo_status != CLOSED`
    (`auto_mode.partite_dal_feed`). Lo scanner pubblica già solo partite in gioco o con via entro 15'
    (`safe_strategy/scanner.py:373 is_monitorable`): le imminenti ci sono;
  - ordine deterministico e uguale per i 4 bot (in gioco prima, poi orario d'inizio, poi event_id);
  - **tetto** per bot: `params.auto_max_partite` > env `TENNIS_AUTO_MAX_PARTITE` > **5**; tagliato a 40;
    0 = auto-mode spento (solo a mano, come prima). La chiave del tetto NON arriva al bot
    (`auto_mode.params_per_strategia`). Le armate ancora nel feed si tengono e contano nel tetto;
  - il follow della partita del feed lo scrive il ponte con `origine='auto'` e i metadati del feed
    (`_segui_dal_feed` r.693; nessuna lettura di `tennis_markets`, nessun REST);
  - la riga per partita è IDENTICA a quella a mano (`_riga_armatura` r.714: `mode`, `dry_run`,
    `stake`, `params`).
- Esclusioni (fail-closed): seguita a mano (la gestisce il ramo di sempre), riga di quel bot in
  `stopping` (finestra di disarm), righe ferme non lette, chiusa dall'utente (D3), riga di quel bot
  `done`/`error`. `stopped` si riarma (spento e riacceso = gesto dell'utente).
- Partita automatica uscita dal feed: non si riarma; se `tennis_live_now.status == 'CLOSED'` le sue righe
  vanno a `stopping` (r.556-565); il follow automatico si chiude (`CLOSED`) quando nessuna riga lo
  occupa (attiva o in chiusura) e nessun bot lo vuole (r.595-607). Senza questo la lista del runner
  crescerebbe tutto il giorno. Follow manuali: mai chiusi. Feed muto: non si chiude/ferma niente.
- Guardia d'avvio armata: niente armamento, il feed non si legge nemmeno.
- Bot tutti spenti: il feed non si legge (zero letture in più).

**Perché il tetto 5** (misura dal codice): il runner sottoscrive UN mercato per partita su UNA
connessione (`tennis_runner._make_capture`, `all_market_ids`); i 200 mercati/connessione sono lontani.
Il vincolo vero è l'IO del DB: per ogni partita seguita `score_and_now_worker` fa un upsert
`tennis_live_now` ogni `TENNIS_SCORE_POLL_SEC`=2 s NON a firma (`tennis_runner.py`, worker
score/now) + ladder a firma ogni 2 s. 5 partite ≈ 2,5 scritture/s di `now` + ≤2,5 di ladder. Il tetto
è in UI (`stats.tetto_partite`, «tetto N» nella nota).

**Runner** (`tennis_runner.py`): un follow nuovo provoca il rebuild dello stream solo a bot flat
(`_request_restart`). Prima un rinvio alzava `force_flat` sui bot in posizione (solo lo scalper lo ha)
e in PAPER, dopo 180 s, forzava il restart azzerando la posizione simulata. Con l'auto-mode i follow
nuovi arrivano di continuo: sarebbe stata un'uscita imposta alla strategia dall'arrivo di una partita
altrui. Ora:
- `_request_restart(..., forza=False)` (r.930, r.962, `_rinvio_senza_forzare` r.1056): rinvio puro,
  niente `force_flat`, niente restart forzato; il motivo d'attesa resta visibile
  (`_mark_waiting_controls`);
- `follow_worker` (r.~1665): `forza=False` SOLO se TUTTI i follow nuovi sono `origine='auto'`;
  una partita seguita a mano forza come sempre;
- `bot_control_worker`: `forza=False` se il restart serve SOLO a ripulire un disarmo
  (`serve_armare`, r.1309/1342/1424/1518). **Cambio di comportamento anche per il manuale**:
  prima anche un disarmo alzava `force_flat` sullo scalper di un'altra partita. Motivo: con
  l'auto-mode ogni partita finita produce un disarmo. Da far validare all'utente.

## 2. Messaggio in UI

**Prima:** «acceso ma non apre: acceso, ma nessun evento tennis seguito in questo momento».
**Ora:**
- `motivo_blocco` (servizio → `PannelloBot.tsx:641` invariato) da `auto_mode.motivo_blocco`, SOLO se
  il bot non è armato su nessuna partita: «guardia d'avvio: aperture bloccate finche' il controllo
  d'avvio dell'app non riesce» · «feed tennis vuoto: nessuna partita in-play ora» · «feed tennis non
  disponibile (scanner fermo o lettura KO): nessuna partita dal feed» · «auto-mode spento: migrazione
  tennis_uscite_manuali_2026-09-25.sql non applicata» · «auto-mode spento (tetto 0)» · «nessuna partita
  armabile fra le N del feed (chiuse dall'utente, concluse o in errore)»; con suffisso « - e nessun
  evento seguito a mano» se non ce ne sono.
- `stats.auto` (fatti: armate dal feed/a mano, in attesa del runner, feed letto/vivo, età scanner,
  fonte, tetto, uscite) → `frontend/src/components/controlroom/tennisAuto.ts` → `nota` della riga
  (canale già esistente `righeBot.ts:83`): «armato su 2 partite dal feed (1 seguite a mano) · 2 in
  attesa del runner · tetto 5 · feed tennis: 7 partite, scanner 4 s fa (safe_strategy_scan)»; in LIVE
  aggiunge «LIVE: le partite nascono in dry-run, nessun ordine reale finché non lo togli per partita».
  Mai «parte»: «in attesa del runner» finché la riga è `requested/arming`.
- `useControlRoom.ts`: solo il `map` dei 4 bot tennis (+ tipo `autoTennis?` su `StatoBot`).
  `PannelloBot.tsx` e `interruttori.ts` NON toccati.

## 3. Uscite automatiche o manuali, per bot

Stato su `tennis_bot_service_control.uscite_automatiche` (colonna, default true) propagato dal ponte
a `tennis_bot_control.uscite_automatiche` SOLO dove diverso (`_propaga_uscite` r.741), riletto a caldo
dal runner nel battito (`_aggiorna_uscite` r.1535, chiamato r.1492; all'armamento r.723). Identico in
paper e live. Colonna assente = AUTOMATICHE (com'era). UI: `UsciteTennis.tsx` montato nello slot
`parametriRiga` dei 4 bot (`pages/ControlRoom.tsx`, righe isolate): «uscite: automatiche» → conferma →
MANUALI; ritorno ad automatiche senza conferma; avviso permanente arancione «uscite manuali: posizione
aperta da X min — chiudi con «Chiudi» dalla scheda partita» (dato: il runner annota
`stats.posizione_aperta_dal` sulla riga per partita, il ponte aggrega). In PAPER un bot a uscite
manuali non viene mai azzerato da un restart forzato (come in LIVE, `manuale` r.974).

### Classificazione delle uscite (nessuna soglia cambiata)

| Bot | Uscita | Dove | Classe | A uscite manuali |
|---|---|---|---|---|
| swing | target (`hit`, `target_frac`) | `tennis_swing_bot.py:~459/470` | DISCREZIONALE | spenta (r.470) |
| swing | stop a tick (`stop_ticks`) | `:~460` | protezione | resta |
| swing | time-stop (`tmax`) | `:~463` | AMBIGUA (chiude anche in utile) → trattata protezione | resta |
| swing | escalation/copertura tardiva/entry timeout/manuale D3 | `_manage_trade`, `_avvia_uscita_manuale` | protezione | resta |
| pro | scaglione (`staged`, `staged_frac`) | `tennis_pro_bot.py:~770` | DISCREZIONALE | spento |
| pro | target (`*_target_ticks`) | `:~776` | DISCREZIONALE | spento |
| pro | stop (`*_stop_ticks`) | `:~780` | protezione | resta |
| pro | uscita strutturale (game/set cambiato) | `:~785` | AMBIGUA → protezione | resta |
| pro | CLOSING/entry timeout/manuale D3 | `_surveil_closing`, `_avvia_uscita_manuale` | protezione | resta |
| FLB | green sullo swing (`exit_mode`, `green_ticks`, `green_frac`) | `tennis_flb_bot.py:~474` | DISCREZIONALE | spento (= `hold`) |
| FLB | re-place hedge di un green già deciso | `_manage` | prosecuzione | non parte se il green non parte |
| FLB | stop | — | non esiste per progetto | — |
| scalper | target a riposo al fill (`_open_lock` :1963) e gamba opposta maker/join (:1522, :1564) | `tennis_scalper_bot.py` | DISCREZIONALE ma È la strategia | **NON gatata: sempre automatica** |
| scalper | stop/TTL, scratch, flatten, force_flat, near-KO, loss cap, missione, D3 | vari | protezione | resta |

Lo scalper: spegnerne il target vuol dire cancellare la gamba d'uscita piazzata insieme all'ingresso
(modo `auto` del preset tennis = join/maker): altera la strategia. Portato all'utente; la UI dice
«uscite: sempre automatiche». FLB a uscite manuali non ha nessun limite di perdita proprio oltre la
liability piccola: restano solo «Chiudi» e fine mercato (è il suo progetto «senza stop»).

## 4. Migrazione

`migrations/tennis_uscite_manuali_2026-09-25.sql` (additiva, idempotente, LA APPLICA L'UTENTE):
`tennis_live_follow.origine` ('manuale'|'auto', default 'manuale'), `uscite_automatiche` (default
true) su `tennis_bot_service_control` e `tennis_bot_control`, RPC owner-only
`tennis_bot_service_set_uscite(p_bot_key, p_automatiche)` (non tocca `status/mode/stake/params`),
`tennis_follow_event` ridefinita con lo stesso corpo di `tennis_live.sql` + `origine='manuale'` (un
«segui» dell'utente su una partita aperta dal ponte la rende manuale).
Senza migrazione: auto-mode SPENTO e detto in UI (il follow automatico non si scrive se non si può
marcare `auto`: `tennis_db.register_tennis_follow` → `ColonnaAssente`; riprova ogni 10'), uscite
automatiche, nessun interruttore uscite in UI. `upsert_tennis_bot_control` si riscrive senza la
colonna mancante (anche insieme a `mode` mancante, in qualunque ordine PostgREST le denunci).

## 5. Test e falsificazione

- Nuovi: `Betfair/stream/tennis_live/tests/test_tennis_auto_mode_2026_09_25.py` (68),
  `Betfair/stream/tennis_scalper/tests/test_uscite_manuali_bot_tennis_2026_09_25.py` (13),
  `frontend/src/components/controlroom/tennisAuto.test.ts` (16, testi esatti),
  `frontend/src/components/controlroom/UsciteTennis.test.tsx` (6).
- Suite: `tennis_live/tests` + `tennis_scalper/tests` verdi; `Betfair/stream/tests` dei moduli
  toccati 199 verdi; vitest su tennisAuto/UsciteTennis/useControlRoom(3 file)/ControlRoom.test 209
  verdi; `tsc -p tsconfig.app.json --noEmit` 0 errori.
- Falsificazione: `AUDIT_2026-09-25/mutazioni_tennis_auto_mode.py` (24 mutazioni del codice di
  produzione, ripristino dal contenuto in memoria): tutte ROSSE. Frontend: 2 mutazioni a mano
  (avviso scalper, conferma del passaggio a manuali) → rosse, ripristinate, riverdi.
- Finti con chiavi/tipi del vero: righe di `tennis_bot_service_control`, `tennis_bot_control`,
  `tennis_live_follow`, `safe_strategy_scan` (payload del ramo tennis di `build_rows`),
  `safe_strategy_status`, `tennis_live_now`; errori PostgREST PGRST204 col testo reale.
- Paper/live: la riga dal feed ha `mode` e `dry_run` identici a quella a mano (paper → dry_run
  false su client simulato; live → dry_run true). T1: in base `372158e` risulta chiuso
  (`tennis_runner._instantiate_bot` r.641-655 + `guardie_tennis.ControlloModalitaBotTennis` r.184;
  suite `test_modalita_e_guardie_tennis_2026_09_24.py` verde). Non l'ho toccato.

## 6. Replay (da lanciare dal coordinatore, UNO per bot in sequenza)

```
python -m Betfair.stream.backtest.certifica tennis_scalper --scenari tutti --diario --worker 1
python -m Betfair.stream.backtest.certifica tennis_pro     --scenari tutti --diario --worker 1
python -m Betfair.stream.backtest.certifica tennis_flb     --scenari tutti --diario --worker 1
python -m Betfair.stream.backtest.certifica tennis_swing   --scenari tutti --diario --worker 1
```
Atteso: esiti IDENTICI al 24/09 (22/22), stessi numeri scenario per scenario: il replay istanzia le
classi senza toccare `uscite_automatiche` (default di classe True = codice di prima) e il ponte/runner
non sono nel banco. Qualunque differenza = regressione mia.

## 7. Non verificato / da decidere

- Non eseguito contro il DB vero né con l'app: la sintassi PostgREST `alias:payload->chiave` e il
  valore `CLOSED` di `tennis_live_now.status` a mercato chiuso sono dedotti dal codice
  (`_build_now_state` scrive `book.status`), non osservati.
- **LIVE + auto-mode**: le righe nascono in `dry_run=true` come quelle a mano (doppio gesto del
  14/09): in live i bot armati dal feed NON piazzano finché l'utente non toglie il dry-run per
  partita. Detto in UI. Se l'utente vuole il live automatico serve una SUA decisione.
- Posizione andata a regolamento (FLB in hold): la partita esce dal feed a mercato chiuso → la riga va
  in `stopping` → il runner può scriverla `error` «posizione NON flat» (blotter con esposizione
  regolata). Onesto ma rumoroso.
- Il Terminale Tennis (`get_tennis_follows`) mostra anche i follow `auto` (non distinti in UI).
- Cambio di comportamento sul restart di sola pulizia (§1, runner): da validare.
- T2 (kill-switch/stop giornaliero) non toccato.
- `npm run build` non eseguito (worktree).
- PUNTEGGI_CANALE/canale 47336: la lista partite del ponte si legge dal DB ogni 15 s (il DB è «la
  lista», il canale non aggiunge partite: contratto `canale_scan`); nessun canale nuovo.

## File

Modificati: `Betfair/stream/tennis_live/{tennis_bot_service,tennis_db,tennis_runner}.py`,
`Betfair/stream/tennis_scalper/{tennis_flb_bot,tennis_pro_bot,tennis_swing_bot}.py`,
`frontend/src/components/controlroom/useControlRoom.ts`, `frontend/src/lib/tennis.ts`,
`frontend/src/pages/ControlRoom.tsx`.
Nuovi: `Betfair/stream/tennis_live/auto_mode.py`, i 4 file di test sopra,
`frontend/src/components/controlroom/{tennisAuto.ts,UsciteTennis.tsx}`,
`migrations/tennis_uscite_manuali_2026-09-25.sql`, `AUDIT_2026-09-25/mutazioni_tennis_auto_mode.py`,
questo file, `AUDIT_2026-09-25/tennis_auto_mode.patch`.
