# CANTIERE F — Hazard Atlas: HTTP 500 (28/09/2026)

Brief: ordine dell'utente 28/09 «FIXA OGNI COSA, TUTTO DEVE FUNZIONARE SENZA INTERRUZIONI».
Perimetro: `Betfair/stream/scalper/genera_atlante.py`, `.github/workflows/hazard_atlas.yml`, test
collegati, `migrations/`. Lavoro NON committato. Nessuna chiamata scrivente al DB vero, nessun
`gh workflow run`, nessuna esecuzione di `genera_atlante.py` contro il DB reale: tutte le verifiche
sono state fatte con `gh run view --log` (sola lettura), query `SELECT`/`EXPLAIN` sul DB Supabase
`dqbwaocvlzbxfrpacsac` (letto con `mcp__plugin_supabase_supabase__execute_sql`), documentazione
ufficiale Supabase (`mcp__plugin_supabase_supabase__search_docs`), lettura di codice/log/CRONOSTORIA,
e test locali con HTTP finto (nessuna rete). **Verifica del coordinatore integrata in questo
referto** (due punti riaperti dopo la prima consegna: vedi §3 mutazione sopravvissuta e §2/§4/§7
causa radice non chiusa).

## 1. Causa radice, con prova

**Il traceback** (`gh run view 36390445058 --log`, passo «Rigenera l'atlante hazard (incrementale
per lega)», iniziato 07:13:13.75Z, traceback a 07:13:50.10Z):

```
File ".../Betfair/stream/scalper/genera_atlante.py", line 1146, in <module>
    sys.exit(main())
File ".../genera_atlante.py", line 1133, in main
    _Scrittore(url, key).salva(stati, sorted(toccate, key=int), atlas)
File ".../genera_atlante.py", line 918, in salva
    self.salva_versione(atlas, tieni)
File ".../genera_atlante.py", line 943, in salva_versione
    self._req("POST", "hazard_atlas", {...
File ".../genera_atlante.py", line 912, in _req
    with urllib.request.urlopen(req, timeout=300) as r:
urllib.error.HTTPError: HTTP Error 500: Internal Server Error
```

Il fallimento e' su UNA sola POST: quella di `salva_versione` (`genera_atlante.py:943`, prima
della correzione), che scrive l'atlante GLOBALE assemblato (tutte le leghe, non solo quelle
toccate stanotte) in **un'unica riga** `hazard_atlas.payload` (jsonb). Il codice non catturava
mai il corpo della risposta d'errore (`_req` faceva solo `r.read()` sulla risposta buona): non
sappiamo il messaggio Postgres esatto restituito quella notte, ma vedi sotto per le prove indirette.

**A DB (sola lettura, prova numerica):**

- `hazard_atlas`: solo 2 righe, id=1 (26/09 06:19Z, 21 leghe) e id=2 (27/09 07:02Z, 188 leghe).
  **Nessuna riga per il 28/09**: la POST e' fallita PRIMA del commit, come dice il traceback.
- **Dimensione REALE del corpo della richiesta (misura del coordinatore, non la compressa su
  disco)**: la POST manda l'atlante come TESTO JSON, non come `jsonb` compresso. id=2 (27/09,
  188 leghe) = **14.465.171 byte** (~13,8 MiB) di corpo; id=1 (26/09, 21 leghe) = 1.961.888 byte.
  `pg_column_size` (3,50 MB / 0,43 MB, misura mia della prima consegna) e' la dimensione
  COMPRESSA su disco dopo TOAST: la richiesta HTTP e il parsing JSON lato Postgres vedono i 14+ MB,
  non i 3,5 MB.
- Crescita marginale reale fra i due punti: (14.465.171 − 1.961.888) / (188 − 21) ≈ **74.870
  byte/lega** di corpo, con ~390 KB di struttura fissa (bucket globali, `h2h_hint`) indipendente
  dal numero di leghe. `matches` ha **1.244 `league_id` distinti**; solo 185 sono nello stato di
  `hazard_atlas_leghe` oggi: c'e' ancora molta strada di crescita (proiezione: ~14,2 MB a 185
  leghe, coerente con la misura; ~30 MB a 400 leghe; ~93 MB se l'atlante arrivasse a coprire tutte
  le 1.244 leghe osservate in `matches`).
- `hazard_atlas_leghe`: **90 leghe su 185 risultano scritte con successo alle 07:13:13Z** (stessa
  run fallita) — sono gli upsert A BLOCCHI DI 20 di `salva_leghe` (righe piccole, decine di KB a
  blocco), che gira PRIMA di `salva_versione` nello stesso `salva()`. Solo l'ULTIMA scrittura
  (quella grande, un payload solo, 14+ MB) e' quella che va in 500.
- Nessun trigger, nessun CHECK constraint su `hazard_atlas` (solo `PRIMARY KEY (id)`,
  `payload jsonb NOT NULL`): **non e' un difetto nei dati**.
- `pg_roles.rolconfig`: `authenticator` (il login REALE di PostgREST, anche quando la chiamata
  usa la `service_role` key) ha **`statement_timeout=8s`** e `lock_timeout=8s`; `service_role` non
  ha una riga propria in `rolconfig`. **Confermato dalla documentazione ufficiale Supabase**
  (`https://supabase.com/docs/guides/database/postgres/timeouts`, sezione "Role level"):
  > `service_role`: none (**defaults to the `authenticator` role's 8s timeout if unset**)
  Cioe' le chiamate service_role di PostgREST ereditano davvero l'8 s di `authenticator` quando
  `service_role` non ha un proprio override — esattamente lo stato misurato sul DB. Questo NON era
  piu' un'ipotesi circostanziale nella prima consegna: e' documentato.
- La tabella degli error code PostgREST ufficiali (`https://supabase.com/docs/guides/api/rest/
  postgrest-error-codes`) conferma: `57*` (operator intervention, include 57014
  "canceled due to statement timeout") -> **HTTP 500**. E' lo stesso codice gia' visto QUELLA
  STESSA NOTTE da `season_gaps.py` (R-28-1, referto del coordinatore) su un'altra action.
- Non risulta, nella documentazione Supabase consultata (Data API / PostgREST), un limite
  generale di dimensione del CORPO della richiesta REST/RPC paragonabile a quello esplicito di
  Storage (50 MB free / 500 GB Pro) o di Realtime (256 KB-3 MB): un rifiuto per dimensione
  darebbe tipicamente 413, non 500. Le prove disponibili convergono sullo statement_timeout, non
  su un limite di banda/corpo.
- Quella notte giravano insieme, sullo stesso Daily: Hazard Atlas, Retrain ML Models, Monthly
  Leagues Mapping (fatto accertato dal coordinatore) — carico concorrente sullo stesso DB
  condiviso, proprio nella finestra in cui la POST unica (14+ MB) rischia di superare 8 s.

**Conclusione**: la scrittura fallita e' una singola POST monolitica ("una scrittura sola" per
l'intero atlante, 14+ MB di corpo), sotto un timeout di sessione di 8 s **documentato come
ereditato da service_role**, con contese di carico concorrente quella notte. E' insieme
transitoria (il carico passa) E STRUTTURALE (il corpo cresce ogni notte, ~75 KB/lega, verso un
tetto di 1.244 leghe possibili): i ritentativi (§2) coprono la prima causa, la RPC dedicata (§2,
punto 2 del coordinatore) affronta la seconda. Resta un limite: non ho potuto leggere il
messaggio Postgres esatto della run del 28/09 (la vecchia `_req` non lo catturava, corretto ora;
la risposta di quella notte non esiste piu').

## 2. Cosa ho cambiato e perche'

**File modificati:**
- `Betfair/stream/scalper/genera_atlante.py` — `_Scrittore`:
  1. **`_req`**: ritentativi su 5xx/rete con attese crescenti `(5, 30, 120, 300)` s — STESSA
     politica gia' usata da `LettoreDB.get` (preesistente) per le LETTURE. Un 4xx si propaga
     SUBITO. Cattura e logga il corpo della risposta d'errore (`ex.read()`), cosa che PRIMA non
     succedeva.
  2. **`salva_leghe`**: i blocchi da 20 righe si tentano TUTTI (un blocco KO dopo i ritentativi
     non ferma i blocchi successivi); se alla fine resta qualcosa di non scritto, alza
     `ScritturaLegheParziale` (sottoclasse di `RuntimeError`) con l'elenco ESATTO in
     `.non_scritte`. **Contratto invariato per chi non fallisce mai**: ritorna ancora un `int`
     (righe scritte) — nessuna riscrittura dei due chiamanti in `atlante_a_domanda.py`.
  3. **`_scrivi_riga` (NUOVO, punto 2 del coordinatore)**: la scrittura della riga globale prova
     PRIMA la RPC dedicata `rpc/hazard_atlas_salva_versione` (timeout piu' alto, SOLO per questa
     scrittura, vedi migrazione in §4); se la RPC risponde 404 (PGRST202/42883, "function not
     found": la migrazione non e' ancora applicata) **ripiega SUBITO** sulla POST diretta di
     oggi su `hazard_atlas`, stesso corpo/chiavi di prima. Un 500 (o altro 5xx) sulla RPC **NON**
     fa ripiegare alla cieca: si ritenta SULLA RPC con la stessa politica di `_req`, e se resta
     KO l'errore esce cosi' com'e' — un ripiego indiscriminato nasconderebbe un guasto vero
     dietro una scrittura diretta "riuscita per caso" (che comunque prima o poi tornera' a
     sforare, essendo la causa strutturale). Il codice puo' andare su master PRIMA che la
     migrazione sia applicata: senza la RPC si comporta esattamente come oggi.
  4. **`salva_versione`**: usa `_scrivi_riga`; la pulizia delle versioni vecchie (lettura +
     `DELETE` oltre le `tieni`) non fa MAI fallire la scrittura buona appena fatta — **sia il
     ramo di LETTURA sia il ramo di `DELETE`** restano avvolti in `try/except` con solo un
     `logger.warning` e nessun `raise` (vedi §3, mutazione sopravvissuta chiusa).
  5. **`salva`**: ritorna la lista di cio' che e' rimasto non scritto (leghe + eventualmente
     `"versione_globale"`); prova SEMPRE la versione globale anche se qualche lega e' rimasta KO.
  6. **`main()`**: l'esito rosso (`return 1`) scatta SOLO se `non_scritte` non e' vuota a fine
     run, con l'elenco preciso sia loggato sia nel JSON (`riepilogo["leghe_non_scritte"]`).
- `.github/workflows/hazard_atlas.yml` — `timeout-minutes: 30 -> 60` (i ritentativi possono
  usare alcuni minuti in piu': un timeout dell'intero JOB a meta' sarebbe un rosso "muto").

**File nuovo (codice):**
- `Betfair/stream/tests/test_genera_atlante_scrittura_ritentativi_2026_09_28.py` — 20 test,
  nessuna rete/DB.

**File nuovo (migrazione, NON applicata):**
- `migrations/hazard_atlas_rpc_scrittura_2026-09-28.sql` — vedi §4.

**Cosa NON ho toccato**: `atlante_a_domanda.py`, `atlante_v4.py`, la logica di lettura/assemblaggio
(`assembla`, `incrementale`, `bootstrap`, idempotenza per `fixture_id`) — nessuna soglia, stake o
decisione di trading e' stata sfiorata. Ho letto ma NON modificato `hazard_atlas_sync.py` (vedi §7
punto 3, proposta del coordinatore da NON applicare io).

## 3. Test

Comando (dalla radice, worktree):
```
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider ^
  Betfair\stream\tests\test_genera_atlante_scrittura_ritentativi_2026_09_28.py ^
  Betfair\stream\tests\test_genera_atlante_2026_09_24.py ^
  Betfair\stream\tests\test_atlante_a_domanda_2026_09_25.py ^
  Betfair\stream\tests\test_atlante_a_domanda_coda_scrittura_2026_09_26.py ^
  Betfair\stream\tests\test_atlante_v4_2026_09_25.py Betfair\stream\tests\test_atlante_v4_collegato_2026_09_25.py ^
  Betfair\stream\tests\test_atlante_v4_forza_id_squadra_2026_09_25.py Betfair\stream\tests\test_atlante_v4_stagione_rif_per_lega_2026_09_26.py
```
Esito: **115 passati, 0 falliti** (20 nuovi + 95 esistenti dei moduli collegati), ~64 s.
`Betfair/mike/tests/` (924 test, usa l'atlante condiviso via `hazard_atlas_live.json`): **924
passati**, ~79 s — nessuna regressione sui consumatori.

I 20 test nuovi coprono (oltre ai 13 gia' descritti nella prima consegna): `_scrivi_riga` usa la
RPC quando risponde (corpo `p_generated_at`/`p_payload`/...); ripiega sulla POST diretta SOLO su
404 (corpo `generated_at`/`payload`/... come prima); un 500 sulla RPC si ritenta SULLA RPC (non
ripiega); un 500 sulla RPC con i ritentativi esauriti esce cosi' com'e' (nessun ripiego alla
cieca su `hazard_atlas`); `salva_versione` con la GET di pulizia sempre KO non blocca (rinominato,
gia' c'era); **`salva_versione` con la GET che TROVA 2 versioni vecchie e la DELETE di entrambe
sempre KO non blocca (NUOVO: chiude la mutazione sopravvissuta del coordinatore)**; `salva()` con
la lettura di pulizia KO non conta come "non scritto" (NUOVO); `salva()` con la DELETE di pulizia
KO non conta come "non scritto" (NUOVO).

### Falsificazione (obbligatoria, 6 mutazioni totali: 3 della prima consegna + 3 di questo giro)

`git diff > patch_prima.diff` prima di ogni mutazione; ripristino con `git checkout -- <file>` +
`git apply patch_prima.diff`; verificato `grep -c MUTAZIONE` = 0 e `git diff --stat` identico
(197 righe, invariato) dopo OGNI ripristino.

| # | mutazione | test attesi rossi | esito |
|---|---|---|---|
| 1 | `_req`: tolto il ritentativo (`raise` incondizionato sui 5xx) | `test_req_ritenta_su_500_e_va_a_buon_fine`, `test_req_esaurisce_i_tentativi_e_rialza`, `test_salva_leghe_un_blocco_ko_non_ferma_gli_altri` | **3 rossi** (prima consegna) |
| 2 | `salva_leghe`: `break` sul primo blocco KO | `test_salva_leghe_un_blocco_ko_non_ferma_gli_altri` | **1 rosso** (prima consegna) |
| 3 | `main()`: `return 0` anche con `non_scritte` non vuota | `test_main_rosso_solo_se_resta_qualcosa_non_scritto` | **1 rosso** (prima consegna) |
| 4 | `salva_versione`, ramo **DELETE**: `raise` prima del `logger.warning` | `test_salva_versione_pulizia_delete_ko_non_blocca`, `test_salva_pulizia_delete_ko_non_conta_come_non_scritto` | **2 rossi** (SOPRAVVISSUTA dal coordinatore alla prima consegna, ORA CHIUSA) |
| 5 | `salva_versione`, ramo **LETTURA**: `raise` al posto di `logger.warning; return` | `test_salva_versione_pulizia_lettura_ko_non_blocca`, `test_salva_pulizia_lettura_ko_non_conta_come_non_scritto` | **2 rossi** (confermato) |
| 6 | `_scrivi_riga`: ripiego su QUALSIASI errore RPC (non solo 404) | `test_scrivi_riga_rpc_500_esaurito_non_ripiega_alla_cieca` | **1 rosso** (confermato; la prima versione di questo test — con i ritentativi ancora attivi — NON lo catturava perche' `_req` assorbiva il 500 col proprio ritentativo prima che l'eccezione uscisse: corretto usando `attese=()` per far uscire l'errore dalla RPC) |

Tutte le mutazioni hanno fatto diventare rossi ESATTAMENTE i test attesi (nessun rosso a sorpresa
altrove). Ripristino verificato ogni volta (byte per byte: `git diff --stat` identico, 0
`MUTAZIONE` residue).

## 4. Migrazioni SQL

**`migrations/hazard_atlas_rpc_scrittura_2026-09-28.sql` (scritta, NON applicata)**: crea
`public.hazard_atlas_salva_versione(p_generated_at, p_n_leghe, p_n_partite,
p_watermark_event_id, p_payload) RETURNS bigint`, `LANGUAGE plpgsql SECURITY DEFINER`,
`SET search_path = public`, **`SET statement_timeout TO '120s'`** (pattern "Function level"
della doc Supabase: alza il limite SOLO per questa funzione, senza toccare `ALTER ROLE` che
cambierebbe l'8 s di TUTTO il progetto, anche per Safe/Omega/Mike/UI che devono restare veloci).
`REVOKE ALL ... FROM PUBLIC, anon, authenticated` + `GRANT EXECUTE ... TO service_role` (stessa
politica di `hazard_atlas_2026-09-24.sql`). `NOTIFY pgrst, 'reload schema'` in coda (necessario
perche' PostgREST veda la nuova RPC). Verifica e rollback documentati in coda al file.

**Perche' 120 s e non un altro numero**: ordine di grandezza sotto il timeout socket del client
Python (300 s, invariato in `_req`), ben sopra il tempo che la scrittura richiede oggi anche sotto
carico (la POST del 27/09, 14+ MB, e' passata liscia). Se il payload continuera' a crescere (vedi
proiezioni §1) andra' rialzato con `ALTER FUNCTION ... SET statement_timeout TO 'Xs'` — oppure,
meglio, si applica la proposta del punto 3 sotto (ridurre COSA si scrive).

**Perche' non ho scritto anche una migrazione per `ALTER ROLE service_role`**: il coordinatore lo
ha escluso esplicitamente ("niente ALTER ROLE: cambierebbe il limite di tutto il progetto") — e'
la scelta tecnicamente corretta: alzare l'8 s per TUTTO service_role rallenterebbe la protezione
contro query lente ovunque nel progetto (Safe/Omega/Mike/UI/action), non solo per questa scrittura.

## 5. Parita' paper/live

Non applicabile in senso stretto: questo cantiere e' una action GitHub notturna (batch, fuori dal
processo di trading paper/live) e i moduli toccati non eseguono mai ordini. La RPC e il ripiego
non cambiano la catena che TOCCA i bot (vedi §7 punto 3): stesso comportamento identico in paper e
in live.

## 6. Cosa NON ho fatto e cosa NON ho potuto verificare

- **Non ho potuto leggere il messaggio Postgres/PostgREST esatto della run fallita**: la vecchia
  `_req` non catturava il corpo della risposta d'errore. L'ipotesi statement_timeout (57014) e'
  ora **documentata** (Supabase: "service_role... defaults to the authenticator role's 8s timeout
  if unset"), non solo circostanziale — ma resta senza il log letterale di quella notte.
- **Non ho eseguito `genera_atlante.py` contro il DB vero** (vietato dal brief), **non ho
  applicato la migrazione**, **non ho rilanciato l'action**, **non ho chiamato la RPC contro il
  DB vero** (avrebbe scritto una riga): tutto verificato SOLO con HTTP finto in locale.
- **Non ho verificato `HAZARD_ATLAS_MODO`** in modo diretto: il coordinatore ha confermato che
  `.env` NON lo imposta -> vale il default `'domanda'` (vedi §7 punto 3): confermato dal
  coordinatore, non da me (fuori dal mio perimetro leggere `.env` del checkout principale).
- **Non ho potuto misurare quanto dura DAVVERO l'INSERT** (vietato eseguire scritture): ho usato
  `EXPLAIN` (senza `ANALYZE`, che avrebbe eseguito l'INSERT per davvero) su un INSERT sintetico
  che copia la riga id=2 gia' presente — il piano e' banale (`cost=0.15..2.37`, un Index Scan):
  i costi del planner NON includono serializzazione JSON, TOAST, ne' rete, quindi questa misura
  non dice quanto ci mette la scrittura vera; l'ho scartata come prova e mi sono affidato alla
  dimensione reale del corpo (14+ MB, misura del coordinatore) e alla documentazione del timeout.
- **Non ho potuto verificare la correzione (ritentativi + RPC) su una run reale**: chiedo che il
  prossimo run notturno, o un `workflow_dispatch` manuale, sia osservato (vedi §8) — e che la
  migrazione sia applicata PRIMA, cosi' la prima prova vera e' gia' sulla RPC (altrimenti la prima
  notte gira ancora sul ripiego diretto, corretto ma senza il beneficio del timeout piu' alto).
- Non ho toccato ne' misurato le ALTRE due action dello stesso Daily (Retrain ML Models, Monthly
  Leagues Mapping): fuori perimetro. Non ho toccato R-28-1 (`season_gaps.py`, altro cantiere).

## 7. Decisioni per l'utente

1. **Applicare la migrazione** `migrations/hazard_atlas_rpc_scrittura_2026-09-28.sql` (RPC con
   timeout dedicato 120 s, solo per la scrittura della riga globale, permesso solo a
   `service_role`, nessun cambio all'8 s del resto del progetto). Senza applicarla il codice
   funziona comunque (ripiego automatico sulla POST diretta di oggi), ma resta esposto alla
   stessa causa strutturale (payload in crescita verso l'8 s condiviso).
2. **Se il payload continuera' a crescere** anche oltre i 120 s dedicati (proiezione §1: ~30 MB a
   400 leghe, ~93 MB a 1.244), la RPC andra' rialzata (`ALTER FUNCTION ... SET statement_timeout`)
   o si dovra' agire sulla dimensione stessa: vedi punto 3.
3. **Chi legge `hazard_atlas.payload` e se serve ancora scriverlo intero** (chiesto dal
   coordinatore, PROPOSTA, non applicata da me): l'UNICO lettore di `hazard_atlas.payload` e'
   `hazard_atlas_sync.sincronizza()` (`Betfair/stream/scalper/hazard_atlas_sync.py:85-96`),
   attivato SOLO quando `HAZARD_ATLAS_MODO == 'scarica'` (dispatch in `avvia_se_abilitato()`,
   righe 175-188; default e definizione del modo alle righe 129-135). Il coordinatore ha
   confermato che il `.env` reale NON imposta `HAZARD_ATLAS_MODO`: vale il default `'domanda'`,
   nel quale il PC costruisce da solo l'atlante live (`atlante_a_domanda.py`, `MotoreAtlante`) a
   partire da `hazard_atlas_leghe` (stato per lega, gia' scritto dai blocchi da 20 righe che NON
   c'entrano con questo guasto) — **NON scarica mai `hazard_atlas.payload`**. L'unico altro
   lettore di `hazard_atlas` e' `leggi_stato_db()` (`genera_atlante.py`), che legge SOLO
   `watermark_event_id` (un intero), mai `payload`. **In sintesi: col modo di default, oggi
   nessuno legge la riga da 14+ MB che sta causando il problema.** Una riga MOLTO piu' piccola
   (solo `generated_at`/`n_leghe`/`n_partite`/`watermark_event_id`, senza `payload`, o addirittura
   nessuna riga — la filigrana potrebbe vivere in una colonna/tabella dedicata da poche decine di
   byte) coprirebbe lo stesso bisogno operativo (far avanzare la filigrana fra un run e l'altro) a
   una frazione del costo, e toglierebbe la causa strutturale invece di limitarsi a spostare il
   timeout. Questa e' una PROPOSTA: cambia la forma dei dati scritti dall'action (non una
   strategia di trading, ma tocca uno schema DB gia' usato altrove — es. `hazard_atlas_sync.py`
   in modalita' `'scarica'`, oggi spenta ma presente nel codice) e la decido io di non applicarla
   senza il permesso esplicito dell'utente.

## 8. Cosa controllare dal vivo al prossimo avvio dell'action

- **Prima applicare la migrazione** (§4/§7.1), poi osservare la prossima run notturna (o un
  `workflow_dispatch` manuale, decide l'utente/coordinatore, NON fatto da me):
  `gh run view <id> --log | grep -i "atlante\|leghe_non_scritte\|ritento\|RPC"`. Atteso: nessuna
  riga "RPC hazard_atlas_salva_versione assente" (la RPC c'e' e viene usata), run VERDE anche
  sotto carico concorrente del Daily.
- **Se la migrazione NON e' ancora applicata**: atteso ESATTAMENTE UNA riga "RPC ... assente
  (migrazione non ancora applicata?): ripiego sulla POST diretta" per run, poi il comportamento
  di oggi (POST diretta, con ritentativi).
- **A DB** (`SELECT generated_at, n_leghe, n_partite FROM hazard_atlas ORDER BY generated_at DESC
  LIMIT 3`): dopo un run verde deve comparire una riga nuova per la notte in corso.
- **`hazard_atlas_leghe`**: `SELECT count(*), max(updated_at) ...` — deve avanzare anche se la
  versione globale fosse rimasta KO (la scrittura delle leghe e' indipendente e viene tentata per
  intero comunque).
- **Dopo l'applicazione della migrazione** (sola lettura, verifica di chi applica):
  `SELECT proname, prosecdef, proconfig FROM pg_proc WHERE proname =
  'hazard_atlas_salva_versione';` — `proconfig` deve contenere `statement_timeout=120s`;
  `SELECT grantee, privilege_type FROM information_schema.routine_privileges WHERE routine_name =
  'hazard_atlas_salva_versione';` — solo `service_role`.
