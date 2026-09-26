# FIX_SCALPER_E_PAPER_FILL (26/09/2026, delegato di correzione)

Cantiere: SCALPER (auto-mode contro il freno, origine dei follow, force-flat) + PAPER FILL AL BEST (Mike/Safe).
Evidenze: `AUDIT_2026-09-25/e2e_fase2/ADMIN26_AUTOMODE_SAFE.md` par. A, `ADMIN26_ORDINI_SCHEDE.md` (R7).
Worktree: `.claude/worktrees/agent-abdb8a6be1222bc6d`. Niente commit, niente DB, niente processi, replay NON lanciato.

## File toccati (tutti)

| file | tipo |
|---|---|
| `Betfair/stream/scalper/scalper_service.py` | correzione (1, 2) |
| `Betfair/stream/scalper/auto_mode.py` | correzione (1) |
| `Betfair/stream/scalper/scalper_session.py` | correzione (1, 3) |
| `Betfair/mike/service.py` | correzione (4) |
| `Betfair/stream/tests/test_scalper_freno_origine_2026_09_26.py` | test nuovo (21) |
| `Betfair/mike/tests/test_mike_paper_fill_al_best_2026_09_26.py` | test nuovo (8) |
| `Betfair/safe_strategy/tests/test_paper_fill_al_best_2026_09_26.py` | test nuovo (7) |
| `AUDIT_2026-09-26/FIX_SCALPER_E_PAPER_FILL.md` | questo referto |

NON toccati: `execution.py`, `omega_engine.py`, `omega_service.py`, freno R3 (`modo_ordini.py`,
`live_order_worker.py`, `RigaFreno`, `controls.py`), strategie dello scalper (`scalper_bot.py`,
`sniper_bot.py`, `theta_bot.py`), nessuna migrazione.

## 1. Scalper arma a freno tirato

**Reperto.** 09:41:59Z `kill_switch=true`; 09:42:42Z l'auto-mode scrive 2 righe `requested` (`auto_armata`),
`stats.auto.motivo_blocco=null`; le partite fermate dal freno (36090788, 36090854) diventano «chiuse a mano» e
non si riarmano al rilascio.

**Causa.** `scalper_service.py` (prima): `giro_auto` chiamato prima di `freno_supervisore()` (vecchie :745/:750);
condizione di armamento (vecchia :430) senza il freno; `auto_mode.motivo_blocco` senza il freno;
`auto_mode.motivo_esclusione` tratta ogni `stopped` dopo l'accensione come «chiusa a mano»; la sessione non
scriveva nella riga che era stata fermata dal freno.

**Correzione.**
- `scalper_service.py:764-766` il freno si legge PRIMA e si passa a `giro_auto(..., freno=freno)`.
- `scalper_service.py:445` armamento solo con `not freno` (nessuna riga, nessun follow, nessuna attivita').
- `scalper_service.py:390-392` un cambio del freno fa partire subito il giro (il rilascio non aspetta 15 s);
  `StatoAuto.freno` (:309-310).
- `stats.auto` porta `motivo_blocco` = `"freno tirato (<motivo>): nessuna partita nuova si arma; le sessioni vive
  chiudono flat"` e la chiave nuova `freno` (<motivo> o null): pubblicato sul 47338 come ogni `stats.auto`
  (`_scrivi_stats` -> `_pubblica("scalper_stato", ...)`). La UI mostra gia' `motivo_blocco` come testo.
- `auto_mode.py:390-393` `motivo_freno_testo`; `:414-415` il freno viene primo in `motivo_blocco` (anche con
  sessioni in piedi: stanno chiudendo flat).
- Marcatore «fermata dal freno»: la sessione scrive `stats.fermata_dal_freno=<motivo>` quando la ferma il freno
  (non uno stop scritto da fuori): `scalper_session.py:1378-1380` e `:1438` (`dichiara_stato_finale`, :163);
  anche la sessione non avviata col freno (`non_partire_col_freno`, :188).
- `scalper_service.py:144-148` `righe_control` legge il marcatore (`fermata_dal_freno:stats->fermata_dal_freno`).
- `auto_mode.py:269-276` una riga `stopped` AUTOMATICA col marcatore non e' «chiusa a mano»: al rilascio si riarma
  se ancora idonea (feed vivo, vita, follow non chiuso, tetto). Righe dell'utente (`origine` manuale) e righe
  `done`/`error` invariate. `auto_mode.py:290-305` `CHIAVE_FERMATA_FRENO`, `fermata_dal_freno()`.

Il freno stesso NON e' toccato: si usa solo la sua lettura (`motivo_freno` / `controls.motivo_kill_switch`).

## 2. Follow automatici scritti come «manuali»

**Causa.** `scalper_service.py` `Db.segui` (vecchie :165-178) senza `origine` -> default 'manuale'
(`migrations/live_follow_origine_2026-09-25.sql:30`).
**Correzione.** `scalper_service.py:178-181` `"origine": "auto"` nella riga (upsert `ignore_duplicates`
invariato: un follow dell'utente gia' presente NON si riscrive). La card dell'utente non passa da qui (la RPC
`scalper_arm` pretende un follow esistente, creato da «Segui live»): resta 'manuale' per default. Nessuna
migrazione (colonna gia' presente).

**Sanatoria per le righe di oggi (NON eseguita; la applica l'utente).** Anteprima, poi UPDATE:

```sql
-- ANTEPRIMA: follow aperti oggi dall'auto-mode dello scalper e rimasti 'manuale'
SELECT f.event_id, f.status, f.origine, f.fixture_id, f.watchlist_id, f.record, f.created_at
  FROM public.live_follow f
 WHERE f.origine = 'manuale'
   AND f.created_at >= (date_trunc('day', now() AT TIME ZONE 'Europe/Rome') AT TIME ZONE 'Europe/Rome')
   AND f.fixture_id IS NULL AND f.watchlist_id IS NULL AND coalesce(f.record, false) = false
   AND EXISTS (SELECT 1 FROM public.scalper_activity a
                WHERE a.event_id = f.event_id AND a.kind = 'auto_armata'
                  AND a.ts BETWEEN f.created_at - interval '1 minute' AND f.created_at + interval '1 minute');

-- SANATORIA (stesse condizioni)
UPDATE public.live_follow f
   SET origine = 'auto', updated_at = now()
 WHERE f.origine = 'manuale'
   AND f.created_at >= (date_trunc('day', now() AT TIME ZONE 'Europe/Rome') AT TIME ZONE 'Europe/Rome')
   AND f.fixture_id IS NULL AND f.watchlist_id IS NULL AND coalesce(f.record, false) = false
   AND EXISTS (SELECT 1 FROM public.scalper_activity a
                WHERE a.event_id = f.event_id AND a.kind = 'auto_armata'
                  AND a.ts BETWEEN f.created_at - interval '1 minute' AND f.created_at + interval '1 minute');
```

## 3. Force-flat «posizione NON flat dopo 30s» con `error=null`

**Causa.** `scalper_session.py` (vecchie :1318-1321 e :1336-1339): il NON flat andava solo nell'attivita';
la scrittura finale metteva `error=None` salvo crash; il micro-residuo <= 0,30 (accettato da
`sniper_bot.py:649-662`) era sotto la soglia D7 di `_dichiarazione_non_flat` e quindi invisibile nella riga.
**Correzione.**
- `scalper_session.py:293-323` `residuo_netto` (max |se vince - se perde| dal blotter, None se illeggibile) e
  `dichiarazione_stop_non_flat`: `"non_flat_dopo_30s: residuo X EUR"`, con `"(micro-residuo accettato <= 0.30)"`
  sotto soglia, `"residuo non leggibile (blotter)"` se illeggibile, piu' `", ordini vivi N"`.
- `:1376` (stop) e `:1399` (fine vita) registrano la dichiarazione; `:1438-1443` la riga finale porta
  `error` = dichiarazione (unita al testo del crash se c'e') e `stats.posizione_non_flat` (campo ESISTENTE D7:
  non sovrascritto se D7 l'ha gia' scritto, `dichiara_stato_finale` :163). La riga finale esce sul 47338
  (`PubblicaSessioni` rilegge la riga finale). Stato finale (`stopped`/`done`/`error`) invariato; i messaggi
  delle attivita' invariati (li legge `certificazione.messaggio_dichiara_non_flat`).
- Strategie intoccate: `is_flat`, soglie e residuo accettato restano come sono.

## 4. R7: paper di Mike riempie al PREZZO LIMITE

**Causa.** `Betfair/mike/service.py` (vecchia :766) `X.place(price=leg.price, ladder=(), best_size=avail_size)`;
`execution.place` senza ladder chiama `paper_fill(best_price=price)` = limite.
**Correzione (solo Mike, solo paper).** `mike/service.py:765-775` (blocco «26/09 (R7…)» prima di `X.place`):
in paper si passa il livello del feed gia' letto e gia' verificato (`ladder=((avail_price, avail_size),)`);
`paper_fill` cammina il livello col limite: back best >= limite -> fill al best; lay best <= limite -> fill al
best; liquidita' = size del livello; best peggiore del limite -> nessun fill (Mike lo rifiutava gia' prima con
`no_fill`). LIVE invariato: stesso limite, `ladder=()` (`livelli_previsti` del live identico a prima).
Docstring di `execute_place` corretta. `execution.py` NON modificato: Safe gia' passa il livello
(`bot_service._paper_ladder`, `close_position` con `prices[<side>_ladder]`).

**Omega (ripiego paper `omega_service.py:2545-2580`)**: NON ha il difetto e non usa `execution.place` per le
aperture: chiama `E.paper_fill(size, best_price=price, lay_ladder=runner.lay_ladder, limit_price=price, ...)`
(`omega_service.py:2440` ladder del book, `:2563` fill) -> cammina il book dal best. Nessuna modifica.

## Test

```
set SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_KEY=x   (bash: prefisso VAR=... )
python -m pytest -q -p no:cacheprovider Betfair/stream/tests/test_scalper_freno_origine_2026_09_26.py      # 21 passed
python -m pytest -q -p no:cacheprovider Betfair/mike/tests/test_mike_paper_fill_al_best_2026_09_26.py     # 8 passed
python -m pytest -q -p no:cacheprovider Betfair/safe_strategy/tests/test_paper_fill_al_best_2026_09_26.py # 7 passed
```
Test esistenti rilanciati (tutti verdi):
- scalper: `test_scalper_auto_mode_2026_09_25`, `test_r3_freno_unico_2026_09_25`, `test_scalper_certificazione_2026_09_24`,
  `test_scalper_control_room_2026_09_24`, `test_scalper_session_gates_2026_07_16`, `test_scalper_uscite_automatiche_2026_09_25`,
  `test_scalper_live_cli_guardia_2026_09_24`, `test_stato_mercato_freno_2026_09_24`, `test_avvio_app_2026_09_16`,
  `test_scalper_audit_2026_07_09` -> 256 passed; `test_contratto_strada_unica_2026_09_25`, `test_cert_banco_2026_09_16`,
  `test_theta_bot_2026_07_15`, `test_scalper_mission_2026_07_10`, `test_registro_bot_2026_09_16` -> 109 passed, 6 skipped.
- Mike: `Betfair/mike/tests` intera -> 915 passed.
- execution: `Betfair/safe_strategy/tests/test_execution.py` -> 71 passed.

Nota: `test_scalper_control_room_2026_09_24::test_la_sessione_vera_reagisce_a_stopping_con_force_flat` guarda una
finestra di 900 caratteri del sorgente: il marcatore del freno e' stato messo DOPO l'attesa del flat per non
spingere `_all_flat(timeout_s=30.0)` fuori dalla finestra (test esistente non modificato).

## Falsificazione

Script: `AUDIT_2026-09-26/falsifica_fix_scalper_paper_fill.py` (dalla radice del worktree:
`python AUDIT_2026-09-26/falsifica_fix_scalper_paper_fill.py [M1 M2 ...]`). Per ogni mutazione rimette il bug,
lancia pytest sul test nuovo, ripristina in `finally` e verifica sha256; gestisce i file CRLF. Non interromperlo.
sha256 dei 5 file di produzione verificati identici dopo le due esecuzioni.

| mutazione (bug rimesso) | file | esito |
|---|---|---|
| M1 arma a freno tirato (`not freno` tolto) | scalper_service | ROSSO |
| M2 `giro_auto` senza `freno=` nel supervisore | scalper_service | ROSSO |
| M3 `motivo_blocco` non conosce il freno | auto_mode | ROSSO |
| M4 fermata dal freno = chiusa a mano | auto_mode | ROSSO |
| M5 follow senza `origine` | scalper_service | ROSSO |
| M6 select senza marcatore del freno | scalper_service | ROSSO |
| M7 `error` finale senza il NON flat | scalper_session | ROSSO |
| M8 stats finali senza `posizione_non_flat` | scalper_session | ROSSO |
| M9 micro-residuo non dichiarato come tale | scalper_session | ROSSO |
| M10 rilascio del freno aspetta 15 s | scalper_service | ROSSO |
| M11 sessione non avviata senza marcatore | scalper_session | ROSSO |
| M12 Mike paper `ladder=()` (bug R7) | mike/service | ROSSO |
| M13 Mike ladder anche in live | mike/service | ROSSO |
| M14 `execution.place` ignora la ladder in paper | execution | ROSSO |

RED prima della correzione: M1-M12 rimettono esattamente il codice di prima (o la sua parte rilevante) e i test
nuovi falliscono; con la correzione passano.

## Cosa NON ho potuto verificare
- Il ciclo vero di `run_session` (login + flumine): i due rami NON flat e la scrittura finale sono provati con
  funzioni pure + controllo del sorgente; il ciclo intero lo esercita il replay (`certifica scalper ...`), che
  NON ho lanciato (lo lancia il coordinatore).
- La Control Room/Terminale a video (testo `motivo_blocco` col freno, follow «auto», `error` della riga ferma).
- Replay Mike (`certifica mike ...`) col fill al best: non lanciato.

## Rischi residui (da portare all'utente)
1. **Follow `origine='auto'` e runner calcio**: `auto_follow.FollowDb.chiudi_orfani` (all'avvio del runner) porta a
   CLOSED le righe auto PENDING/STREAMING. Dopo un riavvio del runner i follow aperti dallo scalper diventano
   CLOSED e l'auto-mode dello scalper, per la sua regola `FOLLOW_CHIUSI` (`auto_mode.py`), non riarma piu' quelle
   partite. Le sessioni gia' vive non ne dipendono (hanno login e stream propri). Da decidere se lo scalper debba
   riaprire i propri follow o se `chiudi_orfani` debba distinguerli (divergenza di progetto, non corretta qui).
   La sanatoria SQL porta le righe di oggi nella stessa condizione.
2. Se la colonna `live_follow.origine` mancasse (migrazione non applicata) `Db.segui` fallisce e la partita non si
   arma (errore nel log, giro continua). Oggi la colonna esiste (query dell'e2e).
3. Una sessione automatica fermata dal freno con un residuo NON flat viene riarmata al rilascio come sessione
   nuova (dry-run, come ogni armamento auto): il residuo resta dichiarato sulla riga precedente
   (`error`/`posizione_non_flat`), la sessione nuova non lo eredita (stesso comportamento di un riarmo a mano).
4. Freno file `STOP_SCALPER`: finale `done` col marcatore; non si riarma (il file spegne anche il supervisore).
