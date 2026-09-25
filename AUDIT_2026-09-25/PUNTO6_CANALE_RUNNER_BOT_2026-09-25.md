# Punto 6 - canale runner e bot (completamento dell'audit 6, tempo reale) - 25/09/2026

Delegato Opus (sessione B). Base: `edc5540` (origin/master al momento del lavoro). Niente commit.
Riferimento: `AUDIT6_TEMPO_REALE_VOCI_4_5_6_12_13_14_2026-09-25.md`, "Cosa manca lato runner"
(voce 6) e "Cosa manca lato bot" (voce 4).

Strategie intoccabili: nessuna logica dei bot cambia; solo pubblicazione di dati GIA' in memoria.
Nessun IO DB in piu', nessun processo nuovo, nessuna variabile `.env` nuova.

## Due consegne

| patch | file | quando |
|---|---|---|
| `punto6_patch_A_runner.patch` (11 file) | `Betfair/stream/canale_bot.py`, `live_order_worker.py`, `runner.py`, `tests/test_punto6_battito_modo_ordini_2026_09_25.py` (nuovo); `frontend/src/lib/runnerCanale.ts` (+test), `__fixtures__/runnerCanaleFinti.json` (nuovo), `components/controlroom/RigaOrdiniReali.tsx` (+`.canale.test.tsx`), `useControlRoom.ts` (+`.statoCanale.test.tsx`) | subito: nessuno di questi file e' cambiato su origin/master dopo `edc5540` (verificato fino a `f4af173`) |
| `punto6_patch_B_bot_tennis.patch` (7 file) | `Betfair/omega/omega_service.py`, `Betfair/safe_strategy/bot_service.py`, `Betfair/stream/tennis_live/tennis_runner.py`, `Betfair/stream/tests/test_punto6_b_stato_bot_e_battito_tennis_2026_09_25.py` (nuovo); `frontend/src/lib/statoBotCanale.ts` (+test), `__fixtures__/statoBotCanaleFinti.json` (nuovo) | DOPO l'avviso "bot_service/omega_service/tennis_runner liberi"; RICHIEDE A (usa `canale_bot.battito_runner`/`pubblica_stato_processo`/`TOPIC["battito"]`) |

I due insiemi di file sono DISGIUNTI: A si applica da sola; B si applica dopo A (testualmente
anche da sola, ma a runtime il tennis ha bisogno delle funzioni di A).
Attenzione: su origin/master `f4af173` la sessione A ha gia' toccato `omega_service.py`,
`bot_service.py`, `tennis_runner.py` (lontano dai nostri pezzi: omega ~1043-1530, safe ~2678-6896,
tennis setup_and_run +2 righe prima di `if not session.market_meta:`). Probabile applicazione con
offset; `git apply --3way` consigliato. NON VERIFICATO sul master nuovo (vedi sotto).

## Voce per voce

### A1 - battito del runner calcio sul 47331
- **Cosa faceva.** `heartbeat_worker` (`runner.py`, prima 1105) e il giro di attesa (prima 1955-1962)
  scrivevano SOLO `betfair_live_heartbeat`; sul canale nessun battito: la UI deduceva il vivo dal
  saldo `account` (~20 s) e da `ladder`/`now`.
- **Cosa fa.** Topic `battito` `{ts, mode, streaming}`:
  - `canale_bot.py:123` topic in `TOPIC` (nomi in un posto solo); `:242` `CHIAVI_BATTITO`;
    `:245` `battito_runner(mode, streaming)` (ts = ms del produttore); `:264`
    `pubblica_stato_processo(topic, payload)` (niente busta: non e' una riga; stessa consegna di
    `pubblica`: canale assente -> nessuna chiamata, eccezione inghiottita e CONTATA, mai solleva);
  - `runner.py:1106` `_partite_in_streaming(session)` = eventi catalogati (follow manuali portati a
    STREAMING) meno finalizzati + eventi dell'auto-follow (`piano.voci()`); `None` se non contabile
    (mai un numero inventato);
  - `runner.py:1128` `_pubblica_battito`; chiamato in `heartbeat_worker` (`:1170`, anche col DB giu')
    e in `_battito_in_attesa` (`:1143`, estratto SENZA cambiarne la logica dal giro di attesa, ora
    chiamato a `:2013`; stessa cadenza `HEARTBEAT_SEC`, stesso upsert DB, piu' il battito).
  - `mode` = `heartbeat_mode()` = lo STESSO valore della colonna DB ('LIVE+PAPER').
- **Interruttore (regola 5 di `canale_bot.py`).** Per i topic del RUNNER l'interruttore di processo e'
  il suo canale (`LIVE_LOCAL_WS_PORT` / `TENNIS_LOCAL_WS_PORT`), come gia' per `ladder`, `now`,
  `auto_follow`, `betfair_live_xhedge`: senza canale non esce nulla. Nessuna `.env` nuova (scelta
  coerente con xhedge; se il coordinatore vuole un interruttore esplicito e' una riga).
- **Perche'.** Il vivo del runner al ritmo del battito (10 s), con `mode`/`streaming` veri, anche
  senza partite seguite.

### A2 - modo ordini sul canale, solo al cambio
- **Cosa faceva.** Il modo EFFETTIVO viaggiava solo dentro `now` (solo con partite seguite);
  senza partite la riga "Ordini reali" restava al poll 30 s.
- **Cosa fa.** `live_order_worker.py:512` alla fine di `_refresh_settings` (fuori dal try della
  lettura: anche una lettura fallita che scade -> OFF e' un cambio) chiama `:526`
  `_pubblica_modo_ordini_se_cambiato()`: messaggio = `modo_ordini.stato_corrente()` + `ts`; firma
  del cambio = effettivo, tetto_ambiente, scelto_ui, motivo, scelto_ui_at, scelto_ui_da (non
  `eta_lettura_s`, che cambia a ogni giro). Lock condiviso: i tre thread che rileggono i settings
  (worker ordini, risk, daily stop) producono UN messaggio per cambio. Messo anche nell'`hello`
  (`set_hello(modo_ordini=...)`) per chi si collega dopo. Senza canale la firma NON si segna.
  **Solo sul canale CALCIO**: il runner tennis rilegge i settings con la stessa funzione
  (`guardie_tennis.aggiorna_impostazioni`, kill-switch) ma il suo tetto e' `TENNIS_LIVE_ORDER_MODE`,
  mentre `modo_ordini` legge `LIVE_ORDER_MODE`: sul 47332 sarebbe un'informazione falsa.
  Nessun IO in piu' (test: una sola `get_live_settings`). F0 (`_TEMPI`) non toccato.
- **Perche'.** "Ordini reali" si aggiorna senza poll anche senza partite.

### A3 - frontend (consumo)
- `runnerCanale.ts:76` `leggiBattito` (senza `ts` numerico = non e' un battito); `NotizieRunner.battito`;
  `runnerDalCanale` (`:138-142`): se il battito e' piu' recente della riga DB, `mode` e `streaming`
  vengono dal battito (oggetto intero, mai meta' e meta'; unica eccezione dichiarata: `streaming`
  null = "non contabile" -> resta il numero del DB). Il silenzio del battito non toglie nulla.
- `runnerCanale.ts:179` `leggiModoOrdiniCanale`; `sovrapponiModoOrdini` accetta `modoAlCambio`:
  vale finche' il canale e' collegato (niente scadenza 15 s: il runner manda ogni cambio); fra
  `now` e `modo_ordini` vince il piu' recente, INTERO (`:257`); rilettura RPC solo se la notizia del
  runner e' piu' recente della lettura e dichiara una scelta diversa.
- `RigaOrdiniReali.tsx:146` sottoscrive `modo_ordini` + legge `hello.modo_ordini`; fonte ed eta'
  gia' a video (`cr-ordini-reali-fonte`).
- `useControlRoom.ts:1729` sottoscrive `battito` su 47331 e 47332: l'eta' torna a 0 (foto immediata
  con orologio allineato: col solo giro da 1 s arrivava gia' arrotondata a 1 - reperto trovato dal
  test, vedi falsificazione F9). Chip "Runner"/"Runner tennis" invariati (fonte + eta').

### B1 - omega_stato / safe_stato con il control
- **Cosa faceva.** `{stats, last_cycle}`: modalita' e interruttori di Omega/Safe al poll 30 s.
- **Cosa fa.** `omega_service.py:7816` / `bot_service.py:9308` `_control_per_canale` =
  {status, mode, params, updated_at} della riga letta a INIZIO giro (nessuna lettura in piu');
  `_pubblica_stato(stats, now_iso, control=None)` (`:7825` / `:9318`) aggiunge `control` se c'e';
  chiamate a `:7590` / `:9142` passano `control`. Senza `control` il messaggio e' identico a prima.
  Safe in modalita' degradata pubblica la riga in cache: e' piu' vecchia e la UI non la applica.
- **Frontend.** `statoBotCanale.ts:82` `leggiPushStato` accetta `control` da tutti e tre i bot;
  `sovrapponiControl` invariata: applica solo con `updated_at` STRETTAMENTE piu' recente, colonne
  sostituite (params interi, mai fusi), le colonne non pubblicate (daily_goal, started_at...) restano
  del DB.
- **Limite dichiarato.** Omega pubblica `omega_stato` solo nel ramo "running" del giro (come prima):
  il passaggio a `stopped` resta al poll. Non ho aggiunto punti di pubblicazione nuovi.

### B2 - battito del runner tennis in attesa (47332)
- **Cosa faceva.** In attesa nulla (saldo solo su evento): eta' ferma all'hello.
- **Cosa fa.** `tennis_runner.py:1750` `_pubblica_battito_attesa()` = `battito_runner(live_order_mode(), 0)`
  (stesse chiavi del calcio; `mode` = quella dell'hello; `streaming` 0 in attesa), chiamato nei due
  giri di attesa (`:1826` nessun evento, ogni `TENNIS_IDLE_FOLLOW_POLL_SEC` = 2 s; `:1851` nessun
  mercato, 15 s). Durante lo streaming l'eta' la danno gia' `ladder`/`now`.

## Test (tutti con `SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_KEY=x`)

Nuovi, patch A (`test_punto6_battito_modo_ordini_2026_09_25.py`, 12): battito a ogni giro del
worker con chiavi esatte e mode = heartbeat_mode; battito col DB giu'; battito in attesa alla
cadenza con lo stesso mode del DB; streaming dalla memoria (manuali - finiti + auto); streaming non
contabile = None; canale assente -> nessuna chiamata, nessun errore, firma non segnata; canale che
solleva -> errore contato, runner vivo; modo_ordini SOLO al cambio (due giri uguali = 1 messaggio,
cambio = 2) + hello; lettura scaduta -> OFF pubblicato; mai sul canale tennis; nessuna lettura in
piu'; finti del frontend = chiavi e tipi dei messaggi veri. Canale finto = `LocalChannel` VERO non
avviato (solo `publish` registrato).
Vitest A: `runnerCanale.test.ts` (+13), `RigaOrdiniReali.canale.test.tsx` (+3: modo_ordini senza
partite aggiorna senza poll e rilegge; dall'hello; storto senza ts ignorato),
`useControlRoom.statoCanale.test.tsx` (+2: eta' a 0 a ogni battito con mode/streaming dal battito;
battito senza ts ignorato).

Nuovi, patch B (`test_punto6_b_stato_bot_e_battito_tennis_2026_09_25.py`, 9): `run_once` VERO di
Omega e Safe (finti dei loro test, riga da `riga_control` = colonne vere) -> `control` con le 4
colonne uguali alla riga; senza control messaggio di prima; canale che solleva non ferma i bot;
`setup_and_run` VERO del tennis fermato al primo sonno: battito con chiavi esatte nei due giri di
attesa; senza canale nessun errore; finti del frontend = chiavi/tipi veri.
Vitest B: `statoBotCanale.test.ts` (18; +6: control Omega/Safe, versione piu' nuova vince,
pari/vecchia -> stesso oggetto DB, params sostituiti mai fusi, senza updated_at mai).

Esistenti rieseguiti (file toccati e chi li importa): 237 + 593 (runner/worker/canale_bot/tennis/
omega/safe canale, auto-follow, motore, xhedge...) = verdi; omega+safe bot_service+tennis_runner:
**2900 passed, 4 skipped, 1 xfailed**; vitest runnerCanale/RigaOrdiniReali(+canale)/useControlRoom
statoCanale = 77 verdi; PannelloBot/useControlRoom/ControlRoom = 213 verdi; statoBotCanale+statoCanale
= 32 verdi; `npx tsc -p tsconfig.app.json --noEmit` = **0 errori**.

## Falsificazioni (ognuna rossa, poi ripristino da copia; `git diff` identico byte per byte a prima: verificato con `cmp`)

| # | mutazione | rosso |
|---|---|---|
| F1 | battito senza `ts` (`battito_runner`) | 3 test Python (worker, attesa, finti UI) |
| F2 | modo_ordini a ogni giro (tolta la firma) | `test_modo_ordini_solo_al_cambio` |
| F3 | firma segnata anche senza canale | `test_canale_assente_...` |
| F4 | battito tolto dal giro di attesa | `test_battito_in_attesa_...` |
| F5 | eventi auto non contati | `test_streaming_conta_...` |
| F6 | UI: streaming dal DB + mode dal battito (unione) | runnerCanale + hook |
| F7 | UI: modo_ordini trattato come `now` (scade a 15 s, perde col now) | 3 test runnerCanale |
| F8 | UI: sottoscrizione `modo_ordini` tolta | RigaOrdiniReali.canale |
| F9 | UI: niente foto immediata al battito | hook (eta' mai 0) |
| F10 | tolta la guardia "solo calcio" del modo_ordini | `test_modo_ordini_mai_sul_canale_del_runner_tennis` |
| FB1 | Omega non passa il control | test Omega + finti |
| FB2 | Safe pubblica solo status/mode | test Safe + finti |
| FB3 | battito tennis tolto dal giro di attesa | test tennis |
| FB4 | UI: control UNITO (params fusi) | 2 test statoBotCanale |
| FB5 | UI: control accettato solo da Mike | 4 test statoBotCanale |

## NON VERIFICATO
- App viva: nessun avvio di runner/bot/app; nessun messaggio osservato su un canale vero; nessun
  `npm run build`.
- Applicazione di B sul master NUOVO (`f4af173`, gia' cambiato su omega/safe/tennis dalla sessione
  A): controllato solo che i pezzi upstream siano lontani dai nostri; la `setup_and_run` nuova chiama
  `_entro_il_tetto_al_build(follows)` prima di `_catalog_follow`: il test "senza mercati" potrebbe
  doverlo sostituire con un finto.
- Suite intere e replay: non eseguiti (per brief).
- `git add -N` usato sui 4 file nuovi (intent-to-add, nessun commit): prima di un commit, `git status`.
