# CANTIERE M — I test non devono dipendere dal .env vero — 28/09/2026

Delegato: tocca SOLO `Betfair/conftest.py` e, dichiarato uno per uno, i singoli test che
dipendevano dall'ambiente. Nessuna modifica alla logica dei bot, nessuna scrittura DB, nessuna
chiamata Betfair, `.env` mai toccato. Lavoro NON committato.

## 0. Il problema (reperto del cantiere Omega, 28/09)

Il `.env` vero del checkout principale contiene, dal 26/09, 20 interruttori di produzione accesi
(`=1`): `SAFE_SCAN_CANALE`, `MIKE_CANALE_POSIZIONI`, `OMEGA_CANALE_POSIZIONI`,
`SAFE_CANALE_POSIZIONI`, `TENNIS_BOT_CANALE`, `SAFE_BOT_LEGGE_CANALE`, `SAFE_BOT_SVEGLIA_CANALE`,
`OMEGA_SVEGLIA_CANALE`, `MIKE_SVEGLIA_CANALE`, `TENNIS_BOT_SVEGLIA_CANALE`, `MIKE_LEGGE_CANALE`,
`OMEGA_LEGGE_CANALE`, `PUNTEGGI_CANALE`, `ESITI_ORDINI_CANALE`, `MOTORE_ORDINI_CANALE`,
`SCALPER_CANALE`, `SAFE_ORDINI_VIA_CANALE`, `OMEGA_ORDINI_VIA_CANALE`,
`MOTORE_ORDINI_CANALE_TENNIS`, `SAFE_TENNIS_ORDINI_VIA_CANALE` (verificati riga per riga nel
`.env` del checkout principale). `load_dotenv()` in produzione risale le cartelle e trova quel
`.env` anche da un worktree isolato: la suite pytest lo eredita senza che nessuno lo scriva nel
codice.

## 1. Misura — causa radice con prova

Comando usato per ogni cartella: `python -m pytest <cartella> -q -p no:cacheprovider --tb=no -rf`.
"Ambiente com'e'" = shell pulita, nessuna variabile impostata a mano (i 20 interruttori arrivano
SOLO dal `.env` vero via `load_dotenv()`, quindi `=1`). "Interruttori a 0" = i 20 nomi sopra
esportati a `"0"` PRIMA di lanciare pytest (stesso schema di
`.claude/worktrees/agent-a946824ef51067fea/AUDIT_2026-09-28/cantiere_c/falsifica_c.py`,
`INTERRUTTORI`).

| cartella | ambiente com'e' (.env vero, switch=1) | interruttori a 0 | differenza |
|---|---|---|---|
| `Betfair/omega` | **111 failed**, 1248 passed, 3 skipped — 61,8 s | 1359 passed, 3 skipped — 76,9 s | **111 test cambiano esito** |
| `Betfair/mike` | 924 passed — 35,2 s | 924 passed — 26,2 s | nessuna |
| `Betfair/safe_strategy` | 1876 passed, 3 skipped, 1 xfailed — 135,3 s | 1876 passed, 3 skipped, 1 xfailed — 132,4 s | nessuna |
| `Betfair/stream` (tennis_live e scalper compresi) | 3192 passed, 25 skipped — 233,0 s | 3192 passed, 25 skipped — 188,4 s | nessuna |
| test della radice (18 file `test_*.py`) | 325 passed — 98,1 s | 325 passed — 35,6 s | nessuna |

**Unica cartella dipendente dall'ambiente: `Betfair/omega`.** I 111 test che cambiano esito sono
tutti e soli in 11 file: `test_omega_audit_2026_09_11.py`, `test_omega_avvio_app_2026_09_16.py`,
`test_omega_certificazione_2026_09_11.py`, `test_omega_chaos_2026_09_11.py`,
`test_omega_flumine_live.py`, `test_omega_flumine_paper.py`, `test_omega_service.py`,
`test_t3_consapevolezza_2026_09_17.py`, `tests/test_consapevolezza_flumine_2026_09_17.py`,
`tests/test_esiti_ordini_canale_2026_09_23.py`, `tests/test_omega_kill_switch_rest_o1_2026_09_24.py`.

**Bisezione — da quale variabile dipendono**: ho isolato i 4 interruttori "omega" dai 16 altri
(`OMEGA_CANALE_POSIZIONI`, `OMEGA_LEGGE_CANALE`, `OMEGA_ORDINI_VIA_CANALE`,
`OMEGA_SVEGLIA_CANALE` a 0, gli altri 16 lasciati `=1` dal `.env`): 1359 passed, 3 skipped —
stessa suite pulita. Poi ho spento UNA variabile alla volta, le altre 19 lasciate accese dal
`.env`:

| variabile spenta da sola | esito |
|---|---|
| `OMEGA_CANALE_POSIZIONI=0` | 111 failed (nessun cambiamento) |
| `OMEGA_LEGGE_CANALE=0` | 111 failed (nessun cambiamento) |
| `OMEGA_SVEGLIA_CANALE=0` | non provata singolarmente (irrilevante: la successiva la include) |
| **`OMEGA_ORDINI_VIA_CANALE=0`** | **1359 passed, 3 skipped — TUTTI e 111 tornano verdi** |

Causa radice: `Betfair/omega/porta_ordini.py:48` `ENV_CANALE = "OMEGA_ORDINI_VIA_CANALE"`,
letto a ogni chiamata da `acceso()` (riga 68-70) che richiama
`Betfair/safe_strategy/porta_ordini.py:134-136` (`os.getenv(nome_env) or "").strip().lower() in
VALORI_ACCESI`, `VALORI_ACCESI = {"1","true","si","yes"}` — lettura PIGRA, non a modulo, quindi
`monkeypatch.setenv` la raggiunge senza bisogno di ricaricare moduli. Con l'interruttore acceso
`Betfair/omega/omega_service.py:2891-2898 _porta_ordini()/_porta_per()` instrada gli ordini sulla
porta del canale (`_place_via_canale`) invece del percorso REST di sempre: gli 11 file sopra sono
scritti per certificare il percorso REST byte-per-byte (kill-switch, parita' manuale
paper/live, consapevolezza, chaos, audit) e non forniscono il canale/il runner finto che la
strada nuova richiede — non e' un bug del canale, e' un ambiente di test che non dichiara cosa si
aspetta.

## 2. Correzione

**File toccato**: `Betfair/conftest.py` (estesa la fixture esistente del 25/09, NESSUNA fixture
parallela creata). Aggiunte due cose nello stesso file:

1. `INTERRUTTORI_CANALE` (i 20 nomi) e la fixture `_ambiente_neutro_canali_e_db`, **autouse**,
   che ad ogni test:
   - spegne i 20 interruttori con `monkeypatch.setenv(nome, "0")` (letti pigramente, nessun
     modulo da ricaricare — vedi §1);
   - forza `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_KEY` a valori finti (env);
   - **ripassa anche tutti i moduli GIA' importati** (`sys.modules`) e sovrascrive i loro
     attributi `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`/`SUPABASE_KEY` con `monkeypatch.setattr`
     (vedi §3 per il perche').

   Il test che vuole un interruttore acceso lo accende da se' con
   `monkeypatch.setenv(nome, "1")` **dopo** l'autouse: l'ultima scrittura vince, l'ordine dei
   fixture non conta, conta che il corpo del test gira sempre dopo il setup di TUTTI gli autouse.

2. Nessun altro file di produzione toccato.

**Moduli che leggono l'ambiente all'IMPORT (§2 del brief) — cercati e trattati**:
- **I 20 interruttori canale**: NESSUNO e' una costante di modulo. Cercato con
  `grep -rn "os\.environ\.get\(|os\.getenv\(" ` sui 20 nomi in `Betfair/`: l'unico risultato e'
  dentro un test che li stampa in un sottoprocesso (non produzione). Confermato leggendo il
  codice: `porta_ordini.acceso()` chiama `os.getenv` a ogni invocazione (§1). La fixture non ha
  bisogno di ricaricare moduli per questi 20 nomi.
- **`SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`: SI', all'import.** `config.py:9-10`:
  `SUPABASE_URL = os.getenv("SUPABASE_URL")`, `SUPABASE_SERVICE_ROLE_KEY =
  os.getenv("SUPABASE_SERVICE_ROLE_KEY")` — costanti di MODULO. Chi fa
  `from config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY` (`db_client.py`, `api_client.py`,
  `Betfair/client.py`, `Betfair/stream/auth.py`, `Betfair/stream/tennis_live/tennis_db.py` e
  altri script fuori dal perimetro test) si porta una COPIA del valore letto al momento
  dell'import, non raggiungibile da un `monkeypatch.setenv` fatto dopo. Verificato con un test
  scratch (poi cancellato) sotto `Betfair/`: importando `config`/`db_client` a livello di modulo
  (quindi in FASE DI COLLECTION, prima di qualunque fixture) i loro attributi valgono comunque
  quelli finti quando il corpo del test gira, perche' la fixture ripassa `sys.modules` e
  sovrascrive gli attributi gia' legati — non serve `importlib.reload` (che romperebbe le
  identita' di oggetto per chi ha gia' fatto `from db_client import get_supabase_client`).
  Prova: `config.SUPABASE_URL == "https://finto-non-esiste.invalid"`,
  `db_client.SUPABASE_URL == "https://finto-non-esiste.invalid"` dentro il test, con l'import a
  livello di modulo fatto PRIMA della fixture.
- Altre costanti di modulo trovate con `os.getenv`/`os.environ.get` (grep su `Betfair/*.py`):
  `TENNIS_LADDER_DEPTH`, `TENNIS_LADDER_MAX_LEVELS`, `TENNIS_SCORE_POLL_SEC`,
  `TENNIS_RUNNER_LOCK_PORT`, `SAFE_STRATEGY_LOCK_PORT`, `LIVE_RUNNER_LOCK_PORT`,
  `LIVE_ODDS_HTTP_PORT`, ecc. — timing/porte, NON fra i 20 interruttori ne' chiavi DB: fuori
  perimetro, non toccate.

## 3. Sicurezza dei test — DB vero raggiungibile per via del `.env` risalito

Cercato: ogni test Python che costruisce un client Supabase VERO (non un finto) e potrebbe
parlare col DB vero se le chiavi nell'ambiente sono vere.

- **Pattern trovato una sola volta**: `test_analytics_market_stats.py` (RADICE, fuori dal
  perimetro di `Betfair/conftest.py` — vedi §6), funzione `_try_db()` (riga 154-164): costruisce
  `get_supabase_client()` vero, prova una RPC di lettura, e se fallisce ritorna `None` — i due
  test che la usano (`test_cert_delay_shift_vs_rpc`, `test_cert_freq_shift_vs_rpc`) fanno
  `if sb is None: return` **prima di ogni asserzione**: si degradano da soli, verdi senza
  certificare niente, quando il DB non e' raggiungibile. Sono gli UNICI due test Python del
  repo che oggi parlano col DB vero SE le chiavi vere sono nell'ambiente (nessun marker
  dedicato che li dichiari esplicitamente: il gate e' `_try_db()` stesso).
- **Sotto `Betfair/`**: cercati tutti i file con `get_supabase_client`/`create_client(` (28 file)
  e incrociati con l'uso di `monkeypatch` nello stesso file: 27 lo usano per sostituire il client
  con un finto (spia/mock) prima di qualunque chiamata reale. L'unico file senza `monkeypatch`
  (`Betfair/stream/tests/test_banco_comune_2026_09_16.py`) nomina `get_supabase_client` solo in
  un COMMENTO che documenta la provenienza di un fisso "vero" copiato a mano (righe 49-54): non
  c'e' nessuna chiamata reale nel file. Nessun test sotto `Betfair/` chiama oggi il DB vero.
- **Difesa aggiunta** (oltre alla misura sopra): la fixture forza comunque
  `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`/`SUPABASE_KEY` finte per OGNI test sotto `Betfair/`
  (env + attributi di modulo, §2): anche un test futuro che dimenticasse il finto non
  raggiungerebbe il DB vero per caso.
- **Fuori dal mio perimetro** (non toccato, vedi §6): i test Python in radice (incluso
  `test_analytics_market_stats.py`), `Prediction/`, `Ai Engine/`, `tactical_engine/` non sono
  sotto `Betfair/conftest.py` e non ricevono questa protezione — restano protetti SOLO dal
  self-gating di `_try_db()` dov'e' presente. `frontend/src/certification/` (TypeScript) e'
  dichiaratamente fuori perimetro (solo Python).

## 4. Prova — falsificazione

Tutti i comandi: `.venv\Scripts\python.exe -m pytest <target> -q -p no:cacheprovider`.

1. **Dopo la correzione, stesso esito col `.env` vero**: `Betfair/omega` con l'ambiente COSI'
   COM'E' (switch=1 dal `.env`) → **1359 passed, 3 skipped, 0 failed — 67,4 s**, identico alla
   colonna "interruttori a 0" della tabella §1 (1359/3/0). Le altre 4 cartelle erano gia' uguali
   nelle due colonne (§1) e restano uguali dopo (rilanciate: mike 924 passed/25,8 s; radice 325
   passed/57,7 s; safe_strategy 1876/3/1/132,4 s; stream 3192 passed/25 skipped/203,1 s;
   `Betfair/` intera in un colpo solo — vedi in coda).
2. **Falsificazione in positivo** (accendere un interruttore nell'ambiente del processo, la
   suite non deve cambiare): esportate TUTTE le 20 variabili a `"1"` (piu' aggressivo del `.env`
   vero, che gia' le ha a 1) PIU' `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` a valori-finti-che-
   sembrano-veri, poi `Betfair/omega` → **1359 passed, 3 skipped — 71,5 s**. Nessun cambiamento.
3. **Mutazione della mia correzione** (deve tornare rosso): salvato `patch_prima_conftest.diff`
   (`git diff Betfair/conftest.py`), disattivata la fixture nuova (`autouse=True` →
   `autouse=False` SOLO su `_ambiente_neutro_canali_e_db`), rilanciato `Betfair/omega` col `.env`
   vero → **111 failed, 1248 passed, 3 skipped — 60,5 s**, stessi identici numeri di §1.
   Ripristinato (`autouse=False` → `autouse=True`), verificato `grep -c MUTAZIONE
   Betfair/conftest.py` = 0 e `git diff Betfair/conftest.py` uguale byte-per-byte al diff salvato
   prima della mutazione (`diff patch_prima.diff patch_dopo.diff` = vuoto). Rilanciato
   `Betfair/omega`: di nuovo 1359 passed, 3 skipped.
4. **Suite intera in un colpo** (il comando che usa il coordinatore, gia' in `CLAUDE.md`):
   `python -m pytest Betfair/ -q -p no:cacheprovider` → risultato riportato in coda a questo
   referto dopo l'ultima rilettura.

## 5. Reperto collegato — `test_latenza_logica_aggancio_sotto_i_20_ms`

File: `Betfair/stream/tests/test_auto_follow_2026_09_25.py`. Falliva SEMPRE (11/11 tentativi,
prima della correzione) quando lanciato DA SOLO, mai quando lanciato dentro il file intero
(31/31 verdi, sempre).

**Diagnosi** (script scratch fuori dalla suite, cancellato a fine lavoro, MAI committato):
cronometrato ogni sotto-passo (`_on_comando`, `motore.drena`, `auto.giro`, `_nuovo_mercato`,
`avanza_aggancio`) del giro misurato dal test. Poi, nello STESSO processo, lo stesso identico
giro ripetuto 8 volte su mercati diversi:

```
giro 1: 39.626 ms   <- quello che il test misura
giro 2: 4.466 ms
giro 3: 3.635 ms
giro 4: 5.008 ms
giro 5: 4.233 ms
giro 6: 5.191 ms
giro 7: 3.985 ms
giro 8: 5.023 ms
```

**Escluse per esperimento diretto** (non e' la causa):
- I/O del diario su disco (`Diario.scrivi(..., durevole=True)` fa `flush()`+`os.fsync()`,
  `Betfair/stream/motore_ordini.py:186-199`): disattivato `os.fsync` con un monkeypatch di prova
  → il primo giro resta lento (24-56 ms su 8 tentativi). Sostituito `amb.motore.diario` con un
  finto interamente in RAM (zero I/O) → il primo giro resta lento (29-49 ms su 9 tentativi).
  L'I/O su disco NON e' la causa (o non l'unica): il primo giro e' lento anche a zero I/O.
- Il thread scrittore in background (`ScrittoreAsincrono._giro`, riga 314-337): usa
  `self._coda.get()` BLOCCANTE senza timeout — resta fermo (0% CPU) finche' non arriva un
  lavoro, non gira a vuoto: escluso come sorgente di contesa GIL continua.

**Causa radice**: costo di RISCALDAMENTO del processo pagato una tantum dal primo giro di
QUALSIASI comando in tutto il processo pytest (import pigri di primo uso, prime allocazioni di
strutture di modulo, probabile specializzazione del bytecode di CPython 3.13 sui percorsi caldi
— la venv usa Python 3.13.3, che ha l'interprete adattivo specializzante di serie) — non la
"logica di aggancio" che il test dichiara di certificare. Riprodotto in modo deterministico
(8/8): primo giro sempre lento, dal secondo in poi sempre stabile sotto i 6 ms.

**Correzione** (SOLO questo test, dichiarato): un giro di RISCALDAMENTO su un mercato/ref diverso
(`"1.949"`/`ref="safe-t99"`, tempo scartato) PRIMA della misura, cosi' il processo e' gia' caldo
come lo sarebbe dopo il primo comando vero in produzione — stessa identica logica misurata, nessun
innalzamento della soglia (resta `< 20.0` ms).

**Falsificazione**: prima della correzione, 11/11 fallimenti da solo (3 + 8 tentativi in sessioni
separate, sempre 24-56 ms). Dopo la correzione: **8/8 verdi** da solo
(`Betfair/stream/tests/test_auto_follow_2026_09_25.py::test_latenza_logica_aggancio_sotto_i_20_ms`
isolato, comando ripetuto 8 volte in processi pytest separati) e il file intero resta **31/31
verde** (`Betfair/stream/tests/test_auto_follow_2026_09_25.py` senza filtro).

## 6. Cosa NON ho fatto / NON ho potuto verificare

- **Root-level e altri alberi Python** (`test_analytics_market_stats.py` e gli altri 17 file
  `test_*.py` di radice, `Prediction/`, `Ai Engine/`, `tactical_engine/`): NON hanno un
  conftest.py proprio con questa protezione — restano fuori dal perimetro che il brief mi ha
  dato (`Betfair/conftest.py`). Oggi sono gia' verdi in entrambe le colonne (§1) e l'unico test
  che tocca il DB vero (`test_cert_delay_shift_vs_rpc`/`_freq_...`) si degrada da solo — ma
  NON ho aggiunto loro chiavi finte forzate. **Decisione per il coordinatore**: se si vuole la
  stessa garanzia anche li', serve un conftest.py di radice (fuori dal mio perimetro dichiarato).
- **Non ho verificato `Betfair/stream/backtest/` (banco comune) ne' i replay/certificazioni
  vere**: il brief vieta replay e test del banco al delegato («niente replay ne' test del
  banco»); i test marcati `cert` dentro le cartelle misurate sono girati normalmente come parte
  della suite (nessuno escluso), ma non ho rilanciato `python -m Betfair.stream.backtest.certifica`.
- **Non ho controllato OGNI singolo modulo di produzione per costanti-di-modulo lette
  all'import**: ho cercato con grep sistematico (`^[A-Z_]+ *= *.*(os\.environ|os\.getenv)`) su
  tutto `Betfair/*.py` e trovato solo le costanti di timing/porta elencate in §2 (fuori
  perimetro) piu' il caso SUPABASE gia' trattato. Un modulo che legge l'ambiente con un pattern
  diverso da questi due (es. dentro una classe, con un alias insolito) potrebbe non essere stato
  visto dal grep; non ho controllato ogni file a mano.
- **Non ho toccato `Betfair/omega/tests/test_omega_kill_switch_rest_o1_2026_09_24.py` ne' gli
  altri 10 file con i 111 test**: sono nel dominio degli altri delegati che lavorano su
  `Betfair/omega/`; la correzione e' tutta e solo nel conftest condiviso.
- **Non ho misurato il tempo "a freddo" del comando UNICO `Betfair/` intero** con l'ambiente
  com'e' PRIMA della mia correzione (l'ho misurato dopo): il numero prima/dopo per cartella
  singola (§1, §4) e' la prova richiesta; il lancio unico di `Betfair/` e' aggiunto come controllo
  finale, riportato in coda — e ha scoperto un fallimento (§11) di stato-fra-file PRE-ESISTENTE e
  NON legato al mio lavoro (verde da solo, verde nei 3 lanci di `Betfair/stream`), fuori dal mio
  perimetro (dominio di un altro delegato su `Betfair/stream/tests/`): NON l'ho indagato ne'
  corretto, lo segnalo e basta.
- **Il tempo del lancio unico `Betfair/` (1h48) non e' attendibile**: il PC era condiviso con
  l'ONDATA 2 (altri due delegati in corso, cantieri G e K); non l'ho rilanciato da solo per non
  aggiungere altro carico mentre gli altri lavorano.

## 7. Parita' paper/live

Nessuna. Questo cantiere non tocca ne' logica di trading ne' codice di produzione: solo
`conftest.py` (ambiente dei test) e un singolo test di latenza. Zero effetto su paper o live.

## 8. Migrazioni SQL

Nessuna.

## 9. Decisioni per l'utente

Nessuna decisione di strategia toccata. Un solo punto tecnico per il coordinatore: **estendere la
stessa protezione (interruttori spenti, DB finto) ai test Python fuori da `Betfair/`** (radice,
`Prediction/`, `Ai Engine/`, `tactical_engine/`) con un conftest.py di livello superiore — oggi
sono gia' verdi e gia' al sicuro dal DB vero per via del self-gating di `_try_db()`, ma non hanno
la stessa garanzia STRUTTURALE che ho messo sotto `Betfair/`. Propongo di farlo in un cantiere
successivo, stesso schema (estendere, non duplicare).

## 10. Cosa controllare dal vivo al prossimo avvio dell'app

Nessuno: questo cantiere non cambia comportamento a runtime (solo `conftest.py` di test e un
test di latenza). Nulla da osservare in paper/live.

## 11. Comando UNICO per il coordinatore

Gia' quello di `CLAUDE.md`, ora affidabile indipendentemente da cosa c'e' nel `.env`:

```
python -m pytest Betfair/ -q -p no:cacheprovider
```

Per cartella singola (misura §1/§4), stesso schema:
```
python -m pytest Betfair/omega -q -p no:cacheprovider
python -m pytest Betfair/mike -q -p no:cacheprovider
python -m pytest Betfair/safe_strategy -q -p no:cacheprovider
python -m pytest Betfair/stream -q -p no:cacheprovider
```

**Risultato dell'ultimo lancio unico `Betfair/` (dopo tutte le correzioni, ambiente col `.env`
vero, nessuna variabile impostata a mano)**:

```
1 failed, 7431 passed, 31 skipped, 1 xfailed, 5 warnings in 6488.10s (1:48:08)
FAILED Betfair/stream/tests/test_uploader_sweep_2026_07_17.py::test_sweep_salta_i_match_potenzialmente_vivi
```

Due osservazioni, entrambe verificate, nessuna delle due tocca il mio lavoro:

1. **Il tempo (1h48) non e' credibile**: la somma dei 4 lanci separati e' ~7 min 45 s (61,8+35,2+
   135,3+233,0 s). Il PC era condiviso con l'ONDATA 2 (cantieri G e K in corso nello stesso
   momento, per `CRONOSTORIA.md`): questo lancio unico NON e' una misura pulita del tempo, solo
   dell'ESITO. Il coordinatore dovrebbe rilanciarlo da solo sul PC per un tempo attendibile.
2. **Il fallimento e' PRE-ESISTENTE e NON dipende dall'ambiente**: rilanciato da solo
   (`Betfair/stream/tests/test_uploader_sweep_2026_07_17.py::
   test_sweep_salta_i_match_potenzialmente_vivi`) → **1 passed in 0,18 s**. Lo stesso file fa
   parte di `Betfair/stream`, che ho misurato verde (0 failed) TRE volte in questo cantiere
   (prima e dopo la correzione, due volte). E' quindi un caso di stato che sopravvive fra FILE
   DIVERSI solo quando gira l'INTERO albero `Betfair/` insieme (migliaia di test, un ordine mai
   provato dai lanci per cartella) — non i 20 interruttori ne' le chiavi Supabase (la mia fixture
   li tocca, non tocca nient'altro che possa spiegare un test sui match "potenzialmente vivi").
   **Fuori dal mio perimetro** (tocca `Betfair/stream/tests/`, dominio di un altro delegato):
   segnalato al coordinatore, non toccato.
