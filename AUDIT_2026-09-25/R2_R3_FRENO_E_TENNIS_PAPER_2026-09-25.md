# R2 + R3 - freno unico (live e paper) e bot tennis in paper al nuovo avvio - 25/09/2026

Delegato Opus (sessione B). Base finale delle patch: **origin/master `9ed1bbe`**.
Consegna: `AUDIT_2026-09-25/r3_patch_A_freno.patch` (A), `AUDIT_2026-09-25/r2_patch_B_tennis_paper.patch` (B).
Nessun commit su master, nessuna migrazione (la RPC `set_live_kill_switch` esistente basta).

Decisioni dell'utente applicate (testuali): «un freno unico che ferma ogni cosa sia live che paper»;
«I bot a ogni riavvio (TUTTI) devono restare spenti... NO, non devono mai partire in live senza mio ordine».

## PATCH A (R3) - il freno unico

Punto di verita' invariato: `betfair_live_settings.kill_switch` (RPC `set_live_kill_switch`) + env
`LIVE_KILL_SWITCH`, letti da `controls.motivo_kill_switch` (cache ~2 s, fail-closed).

| Bot / strada | Prima | Adesso | Dove (righe su 9ed1bbe+A) |
|---|---|---|---|
| Worker coda calcio, motore canale | frenavano gia' live E paper | invariato (verificato leggendo `live_order_worker.py:3402/3677`, `motore_ordini.py:901`) | - |
| Safe calcio+tennis, Mike (tutti via `execution.place`) - fill PAPER in casa | NESSUN freno (solo `_live_brake` sul REST live) | freno sulle APERTURE nello stesso punto del live (dopo il gate, prima dell'esecuzione), stesso esito `PlaceOutcome('error', motivo)`; chiusure (`closes_trade_id`/`cashout`) passano | `safe_strategy/execution.py:152` (`_freno_aperture`), `:743` |
| Mike lay appoggiata PAPER di apertura | nessun freno | `_freno_resting_paper` (oggi tutte le appoggiate sono chiusure: rete per il futuro) | `mike/service.py:1212`, `:3703` |
| Omega automatico PAPER | nessun freno | stesso esito del REST live (`_leg_certain_failure` 'kill_switch', `percorso='paper'`) | `omega/omega_service.py:2547` |
| Omega manuale PAPER | nessun freno | riga terminale come il manuale live (`percorso='paper'`) | `omega/omega_service.py:5276` |
| Scalper (sessione) | solo file `STOP_SCALPER` | `motivo_freno()` = file OPPURE freno condiviso; alla partenza non si arma (`stopped` + motivo); in corsa un sorvegliante (2 s) arma subito il force-flat, il battito chiude la sessione (`stopped`) come per il file | `stream/scalper/scalper_session.py:120,140,159,706,1241,1307` |
| Scalper (supervisore) | spawnava a prescindere | a freno tirato nessuna sessione nuova (la riga resta `requested`) | `stream/scalper/scalper_service.py:613,622,759` |
| 4 bot tennis | `ControlloKillSwitchTennis` dentro flumine, paper e live | invariato (verificato leggendo `guardie_tennis.py:281`, `tennis_runner.py` registrazione) | - |
| `_live_brake` fail-closed | GIA' fail-closed dal 24/09 (il reperto su `execution.py:101-106` era superato) | invariato, ora COLLAUDATO (3 test) | - |

Push alla Control Room: `modo_ordini.stato_corrente()` porta `kill_switch`, `kill_switch_env`,
`kill_switch_letto` (`stream/modo_ordini.py:54,190-209`); le tre chiavi entrano nella firma del cambio
(`live_order_worker.py:525`): tirare/rilasciare esce subito sul topic `modo_ordini` e nell'`hello`.

Control Room: NUOVO `frontend/src/components/controlroom/RigaFreno.tsx`, montato in
`pages/ControlRoom.tsx:612` accanto a «Ordini reali» (`ordiniReali={<><RigaOrdiniReali /><RigaFreno /></>}` + import).
Stato dal push (se piu' recente) o da `get_live_settings` (poll 30 s), fonte ed eta' a video; «TIRA IL FRENO»
= un clic senza domande (come «FERMA TUTTI», interpretazione di «conferma singola»); «RILASCIA» = due
conferme con finestra anti-doppio-clic 400 ms + annulla; freno dal .env dichiarato («da qui non si toglie»).

### Test A
- NUOVO `Betfair/stream/tests/test_r3_freno_unico_2026_09_25.py` (25): (a) Mike paper apertura ferma / chiusura passa / parita'; resting paper; (b) scalper: freno DB senza file, sessione non parte, supervisore, sorvegliante; (c) Safe paper; (d) fail-closed: `_freno_aperture`, `_live_brake` (controls e modo_ordini non importabili), Omega/Mike/scalper illeggibile = tirato; (e) messaggio `modo_ordini` col freno + finti del frontend = chiavi/tipi veri.
- MODIFICATO `Betfair/omega/tests/test_omega_kill_switch_rest_o1_2026_09_24.py`: `test_automatico_paper_non_guarda_il_kill_switch` collaudava il CONTRARIO della decisione di oggi -> sostituito da 6 test (auto/manuale paper con freno env/db, parita' a freno rilasciato).
- NUOVO `frontend/src/components/controlroom/RigaFreno.test.tsx` (13); fixture `runnerCanaleFinti.json` + `modo_ordini_freno` e le 3 chiavi nuove.

## PATCH B (R2) - bot tennis in paper al nuovo avvio

- `tennis_live/tennis_bot_service.py` `ferma_interruttori_al_nuovo_avvio` (:829-848): avvio nuovo -> `status='stopped'` E `mode='paper'`; anche un interruttore gia' fermo ma rimasto `live` torna `paper`. Stesso `APP_BOOT_ID`: nulla.
- `ferma_bot_al_nuovo_avvio` (:94-115): righe per partita attive -> `stopped` + `mode='paper'` + `dry_run=true` (attivita' con `mode_precedente`). Params/stake intatti.
- `tennis_live/tennis_db.py`: `set_tennis_bot_status(..., mode=None, dry_run=None)` (:312-358, ripiego senza `mode` se la colonna manca, PGRST204/42703) e `set_tennis_bot_service_state(..., mode=None)` (:577). None = non si tocca: i chiamanti di prima scrivono identico.
- Test: NUOVO `tennis_live/tests/test_r2_tennis_paper_al_nuovo_avvio_2026_09_25.py` (15, anche su `tennis_db` con client supabase finto); MODIFICATO `stream/tests/test_avvio_app_2026_09_16.py` (finto con la firma vera; `test_tennis_i_params_della_riga_non_si_toccano` asseriva `dry_run False` dopo il nuovo avvio: ora `True`/`paper`, per decisione dell'utente).
- Non toccati: `_instantiate_bot`, `tennis_runner.py`.

## Esiti (su albero 9ed1bbe + A + B, materializzato a parte con `git checkout-index`)

- pytest (SUPABASE finto 127.0.0.1:9): `Betfair/omega Betfair/mike Betfair/safe_strategy Betfair/stream/tennis_live/tests` + stream tests di worker, modo_ordini, punto6, avvio_app, motore_ordini, strada unica, porta banco F4, tutti gli scalper, r3 -> **5097 passed, 11 skipped, 1 xfailed, 0 failed**.
- `npx tsc -p tsconfig.app.json --noEmit` -> **0**. vitest RigaFreno + RigaOrdiniReali(+canale) + runnerCanale -> **76 passed**; `pages/ControlRoom.test.tsx` -> **112 passed**.
- `git apply --check`: A su 9ed1bbe OK; B su 9ed1bbe OK; B su 9ed1bbe+A OK.

## Falsificazioni (tutte ROSSE, rieseguite anche sull'albero 9ed1bbe; ripristino dal testo in memoria, diff pulito)
F1 freno ignorato in paper (4 rossi) - F2 chiusure frenate (3) - F3 `_freno_aperture` fail-open (2) - F4 Omega auto paper (2) - F5 Omega manuale paper (2) - F6 Mike resting paper (1) - F7 scalper legge solo il file (3) - F8 supervisore ignora il freno (1) - F9 sorvegliante non arma il force-flat (1) - F10 freno fuori dalla firma del canale (1) - F11 stato_corrente ignora la riga (1) - F12 tennis interruttore mode non azzerata (2) - F13 righe partita mode/dry_run non azzerati (4) - F14 fermo-ma-live saltato (1) - F15 stesso avvio toccato (1) - F16 senza ripiego colonna mode (1).
UI: U1 rilascio senza conferma (2) - U2 una sola conferma (1) - U3 TIRA scrive false (2) - U4 push ignorato (4) - U5 `kill_switch_letto` ignorato (1).

## Da portare all'utente / NON VERIFICATO
1. **Scalper col freno = force-flat + fine sessione** (la semantica di "stop" che le strategie scalper hanno gia', certificata S2), non una semplice pausa delle aperture: le posizioni vengono chiuse. Alternativa (pausa reversibile) richiede toccare `scalper_bot/sniper_bot/theta_bot`. A freno rilasciato le righe `requested` rimaste in attesa partono (le aveva chieste l'utente o l'auto-mode acceso).
2. **Safe**: un'apertura fermata dal freno consuma il budget ritentativi del segnale (`bot_service._place_fail`, 3 tentativi) come gia' oggi in live; `bot_service.py` non toccato.
3. `over_cover` di Mike conta come APERTURA (classificazione del codice: `OPENING_ROLES`): col freno non parte, come gia' in live.
4. Ogni sessione scalper rilegge `get_live_settings` ogni ~2 s (cache di `controls`): IO in piu' sul DB proporzionale alle sessioni vive.
5. NON VERIFICATO: nessun replay (`certifica`), nessun processo, nessun DB vero, nessuna prova nell'app viva; comportamento del thread sorvegliante dentro una sessione flumine reale non esercitato (solo le funzioni pure e il sorgente del ciclo).
6. Rebase: `git rebase` NEGATO dal classificatore di permessi. Le patch sono state rigenerate su `9ed1bbe` senza rebase del worktree (merge-tree + indice temporaneo): unico conflitto `Betfair/mike/service.py` (righe `approvazione_id` altrui conservate, aggiunti solo i due blocchi R3). Il worktree resta sulla base `d771d05` con 3 commit WIP (`a4451e3` A, `3846a14` B, `88faa5e` fix test A).
7. Flaky pre-esistente osservato una volta (non riprodotto in 3 esecuzioni successive, base inclusa): `Betfair/omega/test_omega_missions.py::test_advisor_presente_su_ft_con_dati_reali_fake` (`poisson_prob` None) in una corsa concorrente con vitest.
