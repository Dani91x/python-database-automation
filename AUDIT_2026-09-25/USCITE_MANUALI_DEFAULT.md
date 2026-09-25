# USCITE MANUALI DI DEFAULT PER TUTTI I BOT — referto del delegato (25/09/2026 sera)

Ordine dell'utente (testuale): «di default, tutte le uscite le voglio spente, ovvero decido io se
uscire o no, per tutti i bot».

Worktree su base `d771d05`, **rebased su `931c11b`** (origin/master, aiuti statistici accesi di
default O1/M1/O5) durante il lavoro: applicazione pulita con `git stash push -u` scoped ai soli
file mike/config.py+engine.py, nessun conflitto, test Mike rilanciati subito dopo per isolare
l'effetto (§5). Niente commit, niente push, nessuna scrittura sul DB vero, nessun processo nuovo,
nessun replay lanciato. Patch: `AUDIT_2026-09-25/uscite_manuali_default.patch`.

## 0. Cosa cambia rispetto a stamattina (b4fef79 / 442d21c)

Stamattina l'interruttore "uscite automatiche" per bot è nato **ACCESO** (comportamento di prima,
parità): Mike, Safe base/esatto/punta/model, scalper e i 4 bot tennis eseguivano le uscite
discrezionali da soli; solo Omega era già "avvisa e proponi" e il cancelletto storico del tennis
(`tennis_exit_approval`) nasceva spento (= automatiche). Stasera l'utente ha ribaltato la
decisione: **tutte le uscite discrezionali nascono PROPOSTE**, in tutti i bot, in paper e in live.
Non cambia NESSUN criterio d'uscita, NESSUNA soglia: cambia solo il valore di partenza
dell'interruttore già costruito stamattina. Le PROTEZIONI restano automatiche esattamente come
classificate in `AUDIT_2026-09-25/USCITE_AUTOMATICHE_PER_BOT.md` §3 e `TENNIS_AUTO_MODE.md` §3
(non toccate, non riclassificate).

## 1. Tabella bot × default prima → dopo

| Bot | Chiave | file:riga | Prima (stamattina) | Dopo (stasera) |
|---|---|---|---|---|
| Mike | `mike_control.params.uscite_automatiche` (spec del parametro) | `Betfair/mike/config.py:254` | `(True, bool, ...)` | `(False, bool, ...)` |
| Mike | fallback nel motore (se il dict non passa da `merge_params`) | `Betfair/mike/engine.py:2222-2226` `uscite_automatiche()` | assente/non-bool → `True` | assente/non-bool → `False` |
| Safe (base/esatto/punta/model) | `safe_strategy_control.params.uscite_automatiche.<strategia>` | `Betfair/safe_strategy/bot_service.py:440` `normalize_uscite_automatiche` (ramo else) | assente/non-bool → `True` | assente/non-bool → `False` |
| Safe tennis | `...uscite_automatiche.tennis` = `not tennis_exit_approval`; default di `tennis_exit_approval` | `bot_service.py:152` (DEFAULT_PARAMS) | `tennis_exit_approval: False` → tennis default `True` (automatiche) | `tennis_exit_approval: True` → tennis default `False` (manuali) |
| Scalper calcio | `scalper_control.params.uscite_automatiche` (whitelist di sessione) | `Betfair/stream/scalper/scalper_bot.py:446` (`ScalperStrategy.__init__`) | assente/non-bool → `True` | assente/non-bool → `False` |
| Scalper calcio | lettura a caldo del battito | `Betfair/stream/scalper/scalper_session.py:474-490` `applica_uscite_automatiche` | assente/non-bool → `True` | assente/non-bool → `False` |
| 4 bot tennis (swing/pro/flb) | attributo di classe `uscite_automatiche` (lo scalper tennis resta SEMPRE automatico, non gatato: `auto_mode.BOT_USCITE_SEMPRE_AUTOMATICHE`, non toccato) | `tennis_swing_bot.py:65`, `tennis_pro_bot.py:91`, `tennis_flb_bot.py:66` | `bool = True` | `bool = False` |
| 4 bot tennis | colonna assente / riga senza `uscite_automatiche` | `Betfair/stream/tennis_live/auto_mode.py:206-209` `uscite_automatiche_riga` | `... is not False` (default automatiche) | `... is True` (default manuali) |
| Omega | `omega_control.params.uscite_protezione` | `Betfair/omega/omega_config.py:309` | **NON TOCCATO**: già `"avvisa_e_proponi"` (manuale) dal 24/09 | invariato, verificato |

Nessuna modifica a `Betfair/mike/engine.py` oltre alla funzione `uscite_automatiche()` (righe
2222-2226): nessuna regola d'uscita, nessuna soglia, nessuna gamba toccata. Stesso per
`Betfair/safe_strategy/exits.py` (NON toccato) e `Betfair/mike/engine.py` altrove (NON toccato).

## 2. Migrazione

`migrations/uscite_manuali_default_2026-09-25.sql` — additiva, idempotente, **la applica
l'utente DOPO** le tre migrazioni di stamattina (`uscite_automatiche_mike_2026-09-25.sql`,
`uscite_automatiche_scalper_2026-09-25.sql` → `scalper_auto_mode_2026-09-25.sql`,
`tennis_uscite_manuali_2026-09-25.sql`, in quest'ordine):
1. **Mike**: forza `mike_control.params.uscite_automatiche = false` (riga unica, id=1).
2. **Safe**: forza `safe_strategy_control.params.uscite_automatiche =
   {base:false, esatto:false, punta:false, tennis:false, model:false}` e
   `.tennis_exit_approval = true` (riga unica, id=1).
3. **Scalper**: forza `uscite_automatiche = false` su OGNI riga di `scalper_control.params`
   (attiva o no) e, se la migrazione dell'auto-mode è già applicata, su
   `scalper_service_control.params` (guardia `IF EXISTS` sulla tabella).
4. **Tennis**: se le colonne `uscite_automatiche` di `tennis_bot_service_control` e
   `tennis_bot_control` esistono già (migrazione di stamattina applicata), il DEFAULT della
   colonna passa da `true` a `false` (`ALTER COLUMN ... SET DEFAULT false`) e i valori esistenti
   vengono forzati a `false`; se le colonne non esistono ancora, questa parte non fa niente
   (guardia `IF EXISTS` sulla colonna).

**Dichiarazione esplicita richiesta dal brief**: questa migrazione **sovrascrive anche valori
espliciti** già scritti (non solo NULL/assente). L'utente ha detto "di default TUTTE spente": è
un ordine nuovo che sostituisce quello di stamattina, non un rispetto di una scelta precedente.

Ho anche **modificato in-place** (non ancora applicata da nessuno, per quanto verificabile dal
codice) `migrations/tennis_uscite_manuali_2026-09-25.sql`: le due `ADD COLUMN ...
DEFAULT true` sono diventate `DEFAULT false` (righe 64/67 circa), con un commento che rimanda
alla migrazione additiva sopra per il caso in cui fosse già stata applicata con `true`.

**Il codice funziona anche senza nessuna delle due migrazioni**: i default sono nel codice
applicativo (tabella §1). Le migrazioni servono solo per righe già scritte con un valore esplicito
diverso da manuale prima di stasera.

## 3. UI — testi e inversione della conferma

- `frontend/src/lib/interruttori.ts`: `usciteSafeDi` (righe ~1086-1094) e `usciteMikeDi`
  (~1097-1104) ora restituiscono `false` quando il valore è assente/non booleano (prima `true`);
  per il tennis di Safe: `tennis_exit_approval === false` (esplicito) → automatiche, altrimenti
  manuali. `usciteSessioniScalper` (~1199-1222): nessuna sessione attiva → `uscite_automatiche:
  false` di default (prima `true`), stesso per l'aggregato delle sessioni attive senza la chiave.
- `frontend/src/lib/mike.ts:572`: default del campo UI `uscite_automatiche` da `true` a `false`
  (contratto verificato dal test `test_contratto_parametri_stessi_clamp_scelte_e_default`, che
  confronta il default Python con quello TS riga per riga — falsificato: senza questo fix il test
  è rosso).
- `frontend/src/components/controlroom/UsciteTennis.tsx`: **conferma invertita**. Prima: passare a
  MANUALI chiedeva conferma (secondo clic), tornare ad AUTOMATICHE no. Ora: passare a MANUALI
  **non chiede niente** (bottone `cr-uscite-automatiche-{bot}`, testo «uscite: automatiche (passa
  a manuali)»); passare ad AUTOMATICHE **chiede conferma** — primo clic arma
  (`cr-uscite-manuali-{bot}`, testo «uscite: MANUALI (passa ad automatiche)»), secondo clic
  conferma ed esegue (`cr-uscite-conferma-{bot}`, testo «conferma: uscite AUTOMATICHE (chiude il
  bot)»).
- `frontend/src/components/controlroom/PannelloBot.tsx` (righe 502-505 nuovo stato
  `confermaUscite`, blocco JSX 685-736): stessa inversione applicata al pulsante generico
  «uscite» della plancia (Mike/Safe/Scalper). **Nota per il coordinatore**: nella stesura di
  stamattina questo pulsante NON aveva nessuna conferma in nessuna direzione (eseguiva
  `cambiaUscite` al primo clic, sia verso manuali sia verso automatiche) — il testo del brief
  («oggi chiede conferma il passaggio a manuali») descrive fedelmente `UsciteTennis.tsx`, non
  questo file. Ho comunque aggiunto la conferma qui, per coerenza con l'istruzione esplicita e con
  `UsciteTennis.tsx`: **verificare che sia quello che si vuole**, perché è un pulsante nuovo, non
  una semplice inversione di uno già esistente.

## 4. Test e falsificazione

Sandbox: `SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_KEY=x`.

### 4.1 Reperto grosso: il default cascata su ~85 test PREESISTENTI

Flippare il default nel codice di produzione (`config.merge_params`, il `FakeDB`/`params()` di
ogni suite, i default di classe dei bot tennis) rompe qualunque test — anche di mesi fa, anche
fuori dal perimetro di stamattina — che costruisce i parametri con l'helper standard
(`C.merge_params(None)`, `FakeDB(params=...)`, `TennisXBot(...)`) e SI ASPETTA che un'uscita
discrezionale parta da sola senza dichiararlo esplicito: prima ereditavano `True` dal default,
ora ereditano `False` e il gate la trasforma in proposta. Prima di correggere altro ho misurato
l'entità isolando l'effetto (stash scoped ai due file Mike, rilancio, stash apply):

| Suite | Rosso PRIMA della correzione | File coinvolti |
|---|---|---|
| `Betfair/mike/tests` | 68/889 | 15 file, incl. `test_mike_engine.py` (motore), `test_mike_service.py`, e **`test_mike_veto_p_under35_2026_09_25.py`** (feature nuova di un altro delegato, merged da `931c11b`) |
| `Betfair/safe_strategy/tests` | 48/1826 | 4 file (`test_bot_service.py` 32, `test_audit_2026_09_11.py` 6, `test_giro_veloce_c6a_2026_09_23.py` 2, più gli 8 della mia suite nuova) |
| `Betfair/stream/{scalper,tennis_scalper,tennis_live,tests}` | 15/2799 | 8 file (presize, mission, pro_staged, flb_hybrid, audit_fixes, auto_mode, più la mia suite nuova) |
| `frontend` vitest | 3/3973 | `interruttoriUscite.test.ts` (2), `useControlRoom.scalperCanale.test.tsx` (1) |

**Come ho corretto** (dichiarato per ciascuna, nessuna soglia/criterio toccato): dove esiste un
helper condiviso (`params()` in `test_mike_engine.py` e 3 cloni identici, `FakeDB.__init__` in
`test_mike_service.py` e in `test_bot_service.py`, `_make_pro/_make_swing/_make_flb` nei test
tennis, `_strategy()` nei test scalper) ho aggiunto UN default esplicito
`uscite_automatiche=True` (o la mappa/il `tennis_exit_approval` equivalente per Safe) **dentro
l'helper**, così la suite continua a testare la MECCANICA di sempre senza dover toccare decine di
assert sparsi; dove non c'era un helper condiviso ho aggiunto il parametro esplicito alla singola
chiamata. **Nessuna soglia, nessuna regola d'uscita, nessuna riga di logica di produzione toccata
per questi fix**: solo fixture di test. Il file `test_mike_veto_p_under35_2026_09_25.py` (feature
di un delegato diverso, appena mersa da master) l'ho toccato SOLO nel suo helper locale `_p()`
(stesso pattern, una riga), MAI nella logica del veto o nelle soglie: segnalo comunque al
coordinatore perché lo riverifichi con chi ha scritto quella feature.

### 4.2 Test nuovi/aggiornati con l'aspettativa sul default dichiarata

- `Betfair/mike/tests/test_mike_uscite_automatiche_2026_09_25.py`: rinominato
  `test_default_e_il_comportamento_di_oggi` → `test_default_ora_e_manuale`; asserzioni invertite
  (`merge_params(None)["uscite_automatiche"] is False`, `E.uscite_automatiche({}) is False`).
- `Betfair/safe_strategy/tests/test_uscite_automatiche_2026_09_25.py`: rinominato
  `test_default_e_il_comportamento_di_oggi` → `test_default_ora_e_manuale_per_tutti`; mappa di
  default ora tutta `False`, `tennis_exit_approval` default `True`;
  `test_solo_un_booleano_vero_cambia_qualcosa` invertito (solo `True` conta, non più solo
  `False`); `test_spento_su_una_strategia_non_tocca_le_altre` ora accende esplicitamente "base"
  per isolare l'effetto (prima lo ereditava dal default).
- `Betfair/safe_strategy/tests/test_bot_service.py::test_senza_cancelletto_NIENTE_cambia`:
  `resolve_params(None)["tennis_exit_approval"]` da `is False` a `is True`.
- `Betfair/stream/tests/test_scalper_uscite_automatiche_2026_09_25.py`: rinominato
  `test_solo_un_booleano_vero_spegne` → `test_solo_un_booleano_vero_accende`; parametrizzazione
  invertita; `test_sessione_applica_il_valore_letto_a_caldo` riscritto per dimostrare il nuovo
  default (prima passava da `True` iniziale a un valore non-bool che tornava `True`; ora passa
  da `True` esplicito a un valore non-bool che torna `False`, il nuovo default).
- `Betfair/stream/tennis_live/tests/test_tennis_auto_mode_2026_09_25.py`: rinominato
  `test_uscite_false_solo_se_scritto` → `test_uscite_true_solo_se_scritto`; parametrizzazione e
  `test_instantiate_bot_porta_le_uscite_della_riga` (colonna assente → `False`, non più `True`)
  invertiti.
- `Betfair/stream/tennis_scalper/tests/test_uscite_manuali_bot_tennis_2026_09_25.py`:
  `test_di_classe_le_uscite_sono_automatiche` → `test_di_classe_le_uscite_sono_manuali`
  (`cls.uscite_automatiche is False`).
- `frontend/src/lib/interruttoriUscite.test.ts`,
  `frontend/src/components/controlroom/PannelloBotUscite.test.tsx`,
  `frontend/src/components/controlroom/UsciteTennis.test.tsx`,
  `frontend/src/components/controlroom/useControlRoom.scalperCanale.test.tsx`: aspettative sul
  default e sulla direzione della conferma invertite (dettaglio nei diff, testi esatti verificati
  da vitest).

### 4.3 Falsificazione

Rimesso a mano `True` in ciascuno dei 7 punti-sorgente del default (§1, colonna file:riga) uno
alla volta: in ognuno dei casi la relativa suite (`test_mike_uscite_automatiche_2026_09_25.py`,
`test_uscite_automatiche_2026_09_25.py` di Safe, `test_scalper_uscite_automatiche_2026_09_25.py`,
`test_tennis_auto_mode_2026_09_25.py`, `test_uscite_manuali_bot_tennis_2026_09_25.py`) torna
rossa sui test del default (non su tutta la suite: conferma che il resto del comportamento non
dipende da quel singolo valore). Ripristinato subito dopo ogni mutazione, verificato byte per
byte col diff.

### 4.4 Esiti finali (dopo tutte le correzioni)

| Suite | Comando | Esito |
|---|---|---|
| `Betfair/mike/tests` | `pytest Betfair/mike/tests -q` | **889 passed** |
| `Betfair/safe_strategy/tests` | `pytest Betfair/safe_strategy/tests -q` | **1825 passed, 3 skipped, 1 xfailed** (identico al riferimento del 24/09) |
| `Betfair/omega` (non toccato, verifica di non regressione) | `pytest Betfair/omega -q` | **1343 passed, 3 skipped** |
| `Betfair/mike + safe_strategy + stream` (run unico finale) | `pytest Betfair/mike Betfair/safe_strategy Betfair/stream -q` | **5564 passed, 28 skipped, 1 xfailed, 1 failed** (vedi §4.5, non causato da questo lavoro) |
| `frontend` vitest (intera suite) | `npx vitest run` | **3943 passed, 30 skipped** (235 file, 6 skip) |
| `npx tsc -p tsconfig.app.json --noEmit` | | **0 errori** |

### 4.5 Un rosso NON causato da questo lavoro

`Betfair/stream/tests/test_banco_identita_2026_09_16.py::test_la_latenza_di_lettura_e_dichiarata_e_governabile`
fallisce SOLO dentro la suite intera (`B.LATENZA_LETTURA_S == fconf.place_latency`, atteso 0.12
ottenuto 0.6: qualcos'altro nella suite scrive su `flumine.config.place_latency`, un modulo
globale, senza ripristinarlo — inquinamento fra test, non un difetto di `uscite_automatiche`).
Verificato: **passa da solo** (`pytest
Betfair/stream/tests/test_banco_identita_2026_09_16.py::test_la_latenza_di_lettura_e_dichiarata_e_governabile
-q` → 1 passed) e falliva anche prima di isolare le mie modifiche (osservato identico nella prima
corsa completa scalper+tennis). Non l'ho inseguito: fuori perimetro, preesistente.

## 5. Non verificato / da confermare col coordinatore

1. **`test_mike_veto_p_under35_2026_09_25.py`** (§4.1): ho aggiunto `uscite_automatiche=True` nel
   suo helper `_p()` per farlo tornare verde. È un fix meccanico (stesso pattern di tutti gli
   altri), ma il file è di un altro delegato appena mersa da `931c11b`: va fatto rileggere a chi
   l'ha scritta.
2. **`PannelloBot.tsx`**: come detto in §3, ho AGGIUNTO una conferma che prima non c'era in nessuna
   direzione (non l'ho solo invertita). Comportamento nuovo, testato (vitest verde,
   `PannelloBotUscite.test.tsx` aggiornato) ma mai visto nell'app reale (niente `npm run build`,
   niente avvio app — vincolo del brief).
3. **`BotParamsSheet.tsx`** (scheda parametri di Safe, spunta `tennis_exit_approval`): il valore
   INIZIALE mostrato dalla spunta quando il DB non ha ancora scritto la chiave dipende dal
   resolver generico dei campi booleani del form (non ho trovato, nel tempo a disposizione, un
   punto dedicato che applichi il nuovo default `True` lì); il valore di PRODUZIONE (quello che
   decide davvero se il bot esegue o propone) è corretto e testato — è solo la spunta a poter
   mostrare "off" finché l'utente non salva una volta. Minore, non money-critical, ma lo dichiaro:
   non l'ho risolto.
4. **Migrazioni**: scritte, non applicate né provate su Postgres vero (vincolo). L'ordine
   dichiarato in §2 (dopo le tre di stamattina) non è stato verificato eseguendole in sequenza su
   un DB reale.
5. **Replay**: non lanciati (vincolo, PC condiviso). Con l'interruttore ora spento di default, gli
   scenari «uscite automatiche» del banco richiedono `uscite_automatiche: true` esplicito nei
   parametri del replay per restare comparabili col riferimento del 24/09 — altrimenti il banco
   eseguirà TUTTI gli scenari sul ramo "proposta" invece che "esegue", il che è client CORRETTO
   ma non è più la stessa cosa che è stata certificata il 24/09. Segnalo esplicitamente: chi
   rilancia il banco deve decidere se certificare anche il ramo "manuale" (proposte, zero uscite
   discrezionali eseguite, protezioni sempre eseguite) come nuovo scenario, o forzare
   `uscite_automatiche: true` negli scenari esistenti per mantenere la parità del 24/09.
6. **App reale**: non avviata (vincolo worktree). Ho dovuto creare io la junction
   `frontend/node_modules` verso il checkout principale (assente in questo worktree, a differenza
   di quanto riportato da altri delegati) per poter lanciare vitest/tsc: rimossa con `cmd /c
   rmdir`, mai con cancellazione ricorsiva, se il coordinatore vuole richiudere il worktree.
7. **`scalperControlRoom.ts`**: nessuna modifica funzionale (la funzione `impostaUsciteScalper` è
   solo un wrapper RPC senza default proprio); non toccato.

## 6. File

Modificati (codice + test, elenco completo nel patch): `Betfair/mike/config.py`,
`Betfair/mike/engine.py`, `Betfair/safe_strategy/bot_service.py`,
`Betfair/stream/scalper/{scalper_bot,scalper_session}.py`,
`Betfair/stream/tennis_live/{auto_mode,tennis_bot_service,tennis_runner}.py`,
`Betfair/stream/tennis_scalper/{tennis_swing_bot,tennis_pro_bot,tennis_flb_bot}.py`,
`frontend/src/lib/{interruttori,mike}.ts`,
`frontend/src/components/controlroom/{PannelloBot,UsciteTennis}.tsx`,
`migrations/tennis_uscite_manuali_2026-09-25.sql` (default `true`→`false` nelle due colonne),
più i 19 file di test collaterali elencati in §4.1-4.2.

Nuovi: `migrations/uscite_manuali_default_2026-09-25.sql`,
`AUDIT_2026-09-25/uscite_manuali_default.patch`, questo file.

Non toccati (fuori perimetro, come da brief): `Betfair/mike/engine.py` (regole d'uscita, solo la
funzione dell'interruttore), `Betfair/safe_strategy/exits.py`, `Betfair/mike/engine.py`
money-critical, `Betfair/omega/**`, `components/controlroom/CashOutPartita*`, `BottoneChiudiRiga`,
`Scheda*.tsx`, `mike/service.py` (righe `approvazione_id`), `scalper_session.py` (sniper),
`tennis_bot_service.py:799-846` (mode→paper), `tennis_runner.py` fuori da `_aggiorna_uscite`.
