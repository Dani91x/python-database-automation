# Cantiere E - Seasons Catchup: timeout 57014 (28/09/2026)

Delegato del coordinatore, worktree `agent-afc61df7a8e98907d`. Lavoro NON committato.
DB progetto Supabase `dqbwaocvlzbxfrpacsac`: solo `SELECT`/`EXPLAIN`/`EXPLAIN (ANALYZE)`,
nessuna scrittura, nessuna esecuzione di `seasons_catchup.py`/`season_gaps.py` contro il
DB vero o API-Football, nessun `gh workflow run`/`gh run rerun`.

**Revisione 2 (stessa giornata)**: il coordinatore ha rifatto la mia verifica nel mio
worktree, trovato 2 mutazioni sopravvissute su 3 e contestato la cifra "2 minuti" del
timeout con una controprova (`pg_db_role_setting`). Ho verificato la sua controprova,
l'ho confermata con la documentazione ufficiale (non solo con `pg_db_role_setting`), ho
corretto la diagnosi, aggiunto i test mancanti (falsificati sulle SUE mutazioni esatte) e
implementato la visibilita' delle degradate persistenti (punto 4), estesa a
`season_aggregates.py` come richiesto. I quattro punti, uno per uno, sono in fondo (§0).

## 0. Risposta ai 4 punti del coordinatore

**1) M2 sopravvissuta (`if False and k in degradate_set:`)**: il coordinatore ha ragione,
era un buco nel TEST, non nel codice (il codice era gia' corretto: lo skip esiste ed e'
`seasons_catchup.py:614`, invariato). Il mio test usava solo lega-stagioni "vive"
(`current=True`): per una viva degradata, `lac.ft_totali` resta 0 (placeholder mai
popolato) e lo skip PREESISTENTE `if viva and lac.ft_totali == 0: continue`
(`seasons_catchup.py:608`, non toccato da questo cantiere) produce lo STESSO risultato
osservabile con o senza lo skip dedicato alle degradate: la mutazione era invisibile.
Aggiunto `test_esegui_catchup_lega_passata_degradata_niente_stato_scritto_niente_coda`
con una lega-stagione PASSATA (`current=False`), dove quello skip non si applica: senza
lo skip dedicato, la mutazione scrive uno stato v2 completo con `buchi_aperti` calcolato
da un `Lacune` VUOTO (fonte `"catchup"`, come se la lega-stagione fosse stata verificata e
senza buchi: falso). Applicando ESATTAMENTE la mutazione del coordinatore sul codice vero:
**1 test rosso** (quello nuovo), con la prova esatta nell'assert (`AssertionError:
'buchi_aperti' not in {...'fonte': 'catchup'...}`). Inoltre la stessa mutazione, testata,
ha rivelato un SECONDO difetto reale (non solo di test): la coda P4 (stagioni mai
caricate) leggeva lo stesso `Lacune` vuoto placeholder delle degradate e le scambiava per
"mai caricate" (0 partite), ripescandole con una RPC diversa (`season_detail_gaps`
singola, non intercettata dal mio finto) e scrivendo comunque uno stato — corretto in
`seasons_catchup.py` escludendo le degradate dal dizionario passato a `esegui_p4` (vedi
§2, R-CATCHUP-2 esteso alla P4).

**2) M3 sopravvissuta (`_e_statement_timeout` -> `return True`)**: buco di test reale,
stesso motivo (nessun test provava che un errore VERO non-57014 restasse un errore).
Aggiunti 4 test: uno diretto sulla funzione (`test_e_statement_timeout_riconosce_solo_
57014_non_qualunque_errore`, permesso negato 42501, 500 generico, errore di rete) e tre di
propagazione (`riepilogo_lacune` due volte, `season_aggregates.leggi_info` una volta).
Applicando ESATTAMENTE la mutazione del coordinatore: **4 test rossi** (esattamente quelli
nuovi che la riguardano), gli altri 10 (inclusi quelli sulla M2 e sulla persistenza, che
usano tutti un vero 57014, ancora riconosciuto correttamente anche con `return True`)
restano verdi: la falsificazione e' precisa, non un "rosso ovunque".

**3) "Il limite non e' 2 minuti"**: CONFERMATO, la mia cifra era sbagliata per il percorso
vero. Causa: ho misurato `current_setting('statement_timeout')` con lo strumento SQL che
uso io, che si connette come `postgres` (verificato: `select current_user, session_user`
-> `postgres, postgres`), NON come lo fa l'action (supabase-py + `SUPABASE_SERVICE_ROLE_
KEY` via PostgREST, ruolo impersonato `service_role`). Il coordinatore ha letto
`pg_db_role_setting` e trovato `authenticator=8s`, `authenticated=8s`, `anon=3s`,
`service_role` NESSUNA impostazione propria: ho verificato la sua lettura (query identica,
stesso risultato) e l'ho confermata con la documentazione UFFICIALE Supabase (non solo col
catalogo, come richiesto), che dichiara esplicitamente la tabella dei default:
> "anon: 3s / authenticated: 8s / **service_role: none (defaults to the `authenticator`
> role's 8s timeout if unset)** / postgres: none (capped by default global timeout to be
> 2min)" -- <https://supabase.com/docs/guides/database/postgres/timeouts>

e i docs di PostgREST confermano il meccanismo (`SET LOCAL ROLE` per impersonare il ruolo
del JWT, con le impostazioni del ruolo impersonato che si applicano quando il ruolo le ha;
se non le ha, quella gia' in sessione dal login come `authenticator` resta valida):
<https://docs.postgrest.org/en/v13/references/auth.html>. **Il limite vero per
`seasons_catchup.py` (chiave service_role, via PostgREST) e' 8 secondi**, non 2 minuti; i
"2 minuti" che avevo misurato sono il default della cifra "`postgres`: none (capped...
2min)", cioe' il limite del MIO strumento di misura, non quello dell'action.
Conseguenza sui numeri e sulla raccomandazione: vedi §1.2 (rifatta) e §7 (cambiata).

**4) Le degradate non possono restare mute**: realizzato. `season_gaps.
segna_degradato_57014` (nuovo) scrive/aggiorna SOLO `stats_json.degradato_57014`
(`{consecutivi, primo_at, ultimo_at}`) sulla riga esistente di `season_backfill_state`,
SENZA toccare `status` ne' nessun altro campo (stessa tecnica gia' usata da
`_salva_verifica_current`, che non ho toccato): nessuno stato falso, solo un contatore.
Oltre `BACKFILL_BUCHI_MAX_GIORNI` (default 3) giorni CONSECUTIVI di degrado la
lega-stagione compare nel referto come "DEGRADATA PERSISTENTE" e la run esce con codice 1
(prima "NON e' un errore" sempre, ora lo diventa se persiste). Nessuna migrazione nuova:
riuso di `season_backfill_state.stats_json` (colonna JSON gia' esistente), quindi il
codice funziona SUBITO, prima e dopo qualunque migrazione. Se la lega-stagione torna
verificabile il contatore si azzera da solo (il nuovo `stats_json` v2 non riporta la
chiave `degradato_57014` se non e' stata ri-degradata quel giro). **Stessa gestione
estesa a `season_aggregates.py`** (perimetro allargato dal coordinatore):
`leggi_info`/`attacca` ora dimezzano e degradano su 57014 esattamente come
`season_gaps.riepilogo_lacune`, senza mai scrivere `lac.aggregati` per una lega-stagione
degradata (sarebbe "tutto mancante": falso, e farebbe richiamare l'API per dati magari
gia' presenti). 4 test nuovi dedicati (§3).

## 1. Causa radice

Due difetti distinti, uno di codice (fa morire il catchup) e uno di prestazioni SQL (fa
scattare il timeout piu' spesso). Entrambi corretti; la cifra del §1.2 e' stata RISCRITTA
dopo la verifica del coordinatore (§0.3).

### 1.1 Codice: un timeout sul RIEPILOGO uccideva l'intera run (difetto principale)

`season_gaps.riepilogo_lacune` (chiamata da `seasons_catchup.esegui_catchup:592`, PRIMA
di qualunque controllo di azioni concorrenti o di quota) chiama la RPC
`season_gaps_summary` a blocchi di 20 lega-stagioni. Se un blocco va in errore
`postgrest.exceptions.APIError({'code': '57014', ...})` (statement_timeout), il vecchio
codice non lo distingueva da un errore vero: l'eccezione risaliva non gestita fino a
`main()` (che cattura solo `QuotaNonLeggibile` e `MigrazioneMancante`), il processo
Python moriva con un traceback e l'exit code non era nessuno dei 3 dichiarati (0/1/2 nel
docstring del modulo) - il catchup NON degradava e NON proseguiva, contro l'ordine
esplicito dell'utente.

**Prova (log reale, letto con `gh run view <id> --log`, sola lettura):**
- Run 36258896621 (26/09/2026, 17:24:11Z, `event=schedule`, FALLITA): dopo
  `[CATCHUP] candidati: 1020 stagioni vive, 400 passate da verificare`, alla riga
  successiva:
  ```
  File ".../seasons_catchup.py", line 590, in esegui_catchup
  File ".../season_gaps.py", line 237, in riepilogo_lacune
  postgrest.exceptions.APIError: {'message': 'canceling statement due to statement timeout',
  'code': '57014', 'hint': None, 'details': None}
  ```
  Nessun blocco era riuscito prima (zero righe di log fra "candidati" e il traceback):
  e' il PRIMO blocco di 20 (lega 1 e lega 2, le prime in ordine `league_id,season_year`)
  ad andare in timeout.
- Run 36338805869 (27/09/2026, 17:56:46Z, `event=schedule`, FALLITA): stesso schema.
- Run 36301939261 (27/09, 07:03:34Z, `event=workflow_run`, VERDE, durata 1h36m: ha
  LAVORATO, non solo verificato) e 36390583106 (28/09, `event=workflow_run`, VERDE,
  "ATTESA FINITA dopo 35 min... coda 1318 lega-stagioni"): stesso identico codice, blocchi
  piu' grandi o uguali, MAI in timeout.

**Perche' non e' un problema di action concorrenti** (prima ipotesi, esclusa con prova):
`gh run list` per la finestra 26/09 14:00-18:00Z e 27/09 14:00-18:00Z mostra che TUTTE le
action esclusive (Daily/Today/Results/Retrain) erano gia' concluse da ore quando i due
Seasons Catchup serali sono falliti (26/09: ultimo Retrain concluso alle 13:07Z, fallito
alle 17:24Z; 27/09: ultimo Retrain concluso alle 13:59:23Z, fallito alle 17:56:46Z).

**Perche' scatta la sera e non la mattina** (misurato sul DB vero, sola lettura): il
numero di partite FT accumulate nel giorno cresce mentre le partite si giocano:

| giorno | partite FT in `matches` |
|---|---|
| 2026-09-25 | 263 |
| 2026-09-26 | 1.144 |
| 2026-09-27 | 845 |

Il cron di Seasons Catchup e' alle 13:47 UTC nominale ma con il ritardo del cron di
GitHub (mediana ~5 h, gia' misurato in `AUDIT_2026-09-25/ACTIONS_DIAGNOSI_E_FIX.md` §1.6)
parte realmente alle 17-18 UTC: a quell'ora la maggior parte delle partite del giorno e'
GIA' conclusa (`status_short` FT), quindi il CTE `ft` di `season_detail_gaps` (vedi 1.2)
e' molto piu' grande che al mattino presto. Stesso blocco di lega-stagioni, piu' righe da
verificare -> piu' probabile superare gli 8 secondi di `statement_timeout` REALI (§0.3),
un margine molto piu' stretto di quanto avessi scritto nella prima versione di questo
referto.

### 1.2 SQL: `season_detail_gaps` nasconde il costo vero al planner (causa dei timeout) - RISCRITTA

`public.season_detail_gaps` (letta con `pg_get_functiondef`, sola lettura) calcola le 5
tabelle di dettaglio con
```sql
cross join lateral (values
    ('match_events',  exists (select 1 from match_events x where x.fixture_id = ft.fixture_id)),
    ... altre 4 ...
) as t(tabella, presente)
```
Le 5 `EXISTS(...)` sono DENTRO una `VALUES`: Postgres NON le trasforma in Anti Join (join
a insieme) ma le esegue come 5 sotto-piani per OGNI riga di `ft` (ogni partita FT della
lega-stagione).

**Prova con `EXPLAIN` (nessuna esecuzione, sola pianificazione)**, lega 39 stagione 2024
(Premier League, 733 righe candidate prima del filtro status, 380 FT): il corpo vecchio
ha un costo totale stimato `828.38..828.40` (il planner NON vede il costo vero dei 5
sotto-piani: solo il probe su `match_odds` costerebbe da solo `4109.15` per riga); la
stessa logica riscritta con `NOT EXISTS`/`EXISTS` a livello di `WHERE` (non dentro una
`VALUES`), una tabella alla volta, viene riconosciuta e trasformata in
`Nested Loop Anti Join`/`Semi Join` propri, costo totale stimato `4536.26` (la stima ORA
e' vera).

**Prova con `EXPLAIN (ANALYZE, BUFFERS)` - misura in secondi VECCHIO vs NUOVO, stesso
identico blocco** (le 20 coppie `league_id,season_year` del PRIMO blocco della corsa
rossa del 26/09, lega 1 e 2), eseguite una dopo l'altra sullo stesso DB, sola lettura
(la versione nuova eseguita come SELECT libero via `unnest(...) cross join lateral (...)`,
la STESSA tecnica gia' usata da `season_gaps_summary` per chiamare `season_detail_gaps`,
NESSUNA funzione creata - autorizzazione esplicita del coordinatore al punto 3):

| | Execution Time | Buffers (shared hit + read) |
|---|---|---|
| VECCHIO (funzione vera, `season_gaps_summary`) | **1.141,629 ms** (~1,14 s; altra misura nella prima versione di questo referto: 2,47 s) | 95.808 hit + 2.654 read = 98.462 |
| NUOVO (riscrittura, stessa query, stesso blocco) | **102,314 ms** (~0,10 s) | 77.646 hit + 30 read = 77.676 |

**~11x piu' veloce, ~88x meno letture fisiche da disco** (2.654 -> 30) sullo STESSO blocco
che ha fatto fallire la run vera. Con un limite di 8 secondi reali (§0.3), il vecchio
corpo a 1,1-2,5 secondi su un blocco "leggero" (competizioni internazionali, non un
campionato nazionale enorme) lascia un margine strettissimo: basta un blocco un po' piu'
pesante (piu' partite FT accumulate durante il giorno, §1.1) per sforare. La riscrittura
riporta il margine a ~80x.

**Equivalenza dell'output della riscrittura VERIFICATA sul DB vero** (SELECT, sola
lettura, confronto riga per riga fra `season_detail_gaps()` vera e la stessa logica
riscritta come query libera):
- lega 39 stagione 2024 (tutto pieno tranne le quote fuori finestra): entrambe ->
  `match_odds non_disponibile 380` (unica riga oltre alle due `_partite`).
- lega 45 stagione 2026 (buchi veri, stati misti): entrambe -> `match_events da_chiamare
  238; match_lineups da_richiamare 94, vuoto_definitivo 144; match_odds da_richiamare 7,
  non_disponibile 202; match_player_stats da_chiamare 238; match_team_stats da_chiamare
  238`. Identiche, stesso ordine, stessi conteggi.
- Il ramo `esito='parziale'` non ha righe sul DB vero oggi (`fixture_detail_checks`: solo
  `esito='vuoto'`, 2.669 righe): verificato a mano che la condizione booleana della
  riscrittura e' la stessa del vecchio `where not t.presente or c.esito = 'parziale'`.

## 2. Cosa ho cambiato e perche'

**File modificati:**
- `season_gaps.py`
  - `_e_statement_timeout(err)`: riconosce `57014`/"statement timeout".
  - `riepilogo_lacune(sb, coppie, blocco=20, stampa=print)`: su 57014 dimezza il blocco e
    ritenta; una singola lega-stagione ancora in 57014 da sola viene DEGRADATA (non
    trattata come "zero buchi") e la run prosegue. Ritorna `(lacune, degradate)`.
  - `segna_degradato_57014(sb, league_id, season_year, oggi, stampa)` (NUOVO, punto 4):
    scrive/aggiorna SOLO `stats_json.degradato_57014` sulla riga esistente (o ne crea una
    minimale con `status="in_progress"` se non esisteva), senza toccare nessun altro
    campo. Soft (avviso, non fail-loud): un contatore di osservabilita' non deve mai far
    morire il catchup.
- `seasons_catchup.py`
  - `Risultato`: `degradate_timeout`, `degradate_consecutivi` (NUOVO), `degradate_
    aggregati` (NUOVO).
  - `esegui_catchup`: salta le degradate sia nella scrittura di stato sia nella coda di
    lavoro; per ognuna chiama `segna_degradato_57014` e registra i giorni consecutivi;
    **esclude le degradate dal dizionario `lacune` passato a `esegui_p4`** (punto 1, R-
    CATCHUP-2 esteso: un `Lacune` vuoto placeholder veniva scambiato per "stagione mai
    caricata" e la P4 la ripescava con una RPC diversa, scrivendo comunque uno stato).
  - `referto_buchi`: righe "DEGRADATE per 57014" e "AGGREGATI DEGRADATI per 57014"
    (non errori); righe "DEGRADATA PERSISTENTE" per chi supera `BACKFILL_BUCHI_MAX_
    GIORNI` giorni consecutivi, che ORA fanno uscire la run con codice 1.
- `season_aggregates.py` (perimetro allargato dal coordinatore, punto 4)
  - `leggi_info(sb, coppie, blocco=150, stampa=print)`: stessa gestione 57014
    (dimezza/degrada). Ritorna `(info, degradate)`.
  - `attacca(...)`: non calcola piu' `lac.aggregati` per le lega-stagioni degradate
    (restano vuote, mai scambiate per "tutto mancante"). Ritorna la lista delle degradate.
- `migrations/season_gaps_perf_2026-09-28.sql` (NUOVO, NON applicata): riscrive
  `season_detail_gaps` (vedi §1.2). Nessuna tabella toccata.
- `test_catchup_57014_2026_09_28.py` (NUOVO): 14 test, vedi §3.

## 3. Test

Comando:
```
python -m pytest test_catchup_57014_2026_09_28.py test_backfill_automatico_2026_09_25.py \
  test_catchup_p4_2026_09_25.py test_catchup_attesa_concorrenti_2026_09_26.py \
  test_riserva_dinamica_2026_09_25.py -q -p no:cacheprovider
```
Esito: **103 passed in ~15-25 s** (14 nuovi + 89 gia' esistenti, nessuna regressione;
tempo variabile fra le esecuzioni per via dei test di attesa/retry).

Test nuovi (`test_catchup_57014_2026_09_28.py`), 14, tutti verdi, per parte:
- **Parte A** (unit `riepilogo_lacune`): dimezzamento fino a isolare la lega maledetta;
  controprova senza 57014 (un solo blocco); `MigrazioneMancante` invariato.
- **Parte B** (integrazione `esegui_catchup`): non muore, degrada, referto/log corretti,
  nessuno stato falso per la lega buona; controprova senza 57014.
- **Parte C** (verifica del coordinatore, M2/M3): `_e_statement_timeout` riconosce SOLO
  57014 (diretto); `riepilogo_lacune` propaga errori non-57014 (permesso negato, rete);
  lega PASSATA degradata -> nessuno stato v2/buchi_aperti scritto, non entra in coda.
- **Parte D** (punto 4, persistenza): 4 giri consecutivi sulla stessa maledetta ->
  consecutivi 1,2,3,4, persistente solo al 4o (> soglia 3), referto/codice coerenti;
  controprova di recupero (il contatore si azzera quando torna verificabile).
- **Parte E** (punto 4 esteso, `season_aggregates.py`): dimezzamento/degrado su 57014;
  errore non-57014 si propaga; `attacca` non tocca gli aggregati della degradata.

**Falsificazione** (mutazioni sul codice vero, non su una copia; patch salvata con
`git diff -- season_gaps.py seasons_catchup.py season_aggregates.py` prima di ogni
mutazione, ripristino con `git checkout -- <file>` + `git apply --include='<file>'
<patch>`, verificato `grep -c MUTAZIONE` = 0 e diff BYTE PER BYTE identico dopo ogni
ripristino):

| Mutazione | Test rossi | Coerente con l'attesa |
|---|---|---|
| M1 (originale, 28/09 mattina): `_e_statement_timeout` -> `return False` | 2/5 (allora) | si' |
| **M2 (coordinatore)**: `if k in degradate_set:` -> `if False and k in degradate_set:` | **1/14**: `test_esegui_catchup_lega_passata_degradata_niente_stato_scritto_niente_coda`, con la prova esatta (`'buchi_aperti' not in {...'fonte': 'catchup'...}` fallisce: lo stato falso viene scritto) | si' |
| **M3 (coordinatore)**: `_e_statement_timeout` -> `return True` | **4/14**: il test diretto sulla funzione + le 3 propagazioni (season_gaps x2, season_aggregates x1); gli altri 10 restano verdi (usano un vero 57014, ancora riconosciuto) | si' |

Le mutazioni M2 e M3 sono state applicate UNA ALLA VOLTA (non insieme) sul codice vero,
verificate rosse, e ripristinate; il ripristino di ENTRAMBE e' stato confrontato byte per
byte con la patch salvata prima di qualunque mutazione (`diff` senza output = identico).
Rilanciata la suite intera dopo il ripristino finale: 103/103 verdi.

## 4. Migrazione SQL scritta (NON applicata)

`migrations/season_gaps_perf_2026-09-28.sql`: `CREATE OR REPLACE FUNCTION
public.season_detail_gaps(...)`, stesso nome, stessi parametri, stesso
`RETURNS TABLE`, stessa logica di classificazione, stesse due righe `_partite`
(invariate). Cambia SOLO la CTE `senza`: da "5 EXISTS dentro una VALUES per riga" a "5
tabelle, una alla volta, con NOT EXISTS/EXISTS a livello di WHERE" (§1.2, con misura in
secondi prima/dopo). Nessuna tabella toccata, nessun indice nuovo necessario. Non tocca
`season_gaps_summary`. Ripetibile (`CREATE OR REPLACE`), nessuna dipendenza da altre
migrazioni in coda.

## 5. Parita' paper/live

Non applicabile: `season_gaps.py`/`seasons_catchup.py`/`season_aggregates.py` sono
infrastruttura di backfill dati (nessun bot, nessun ordine, nessuna strategia di
trading). Non tocca `Betfair/`.

## 6. Cosa NON ho fatto e cosa NON ho potuto verificare

- **Non ho applicato la migrazione sul DB vero** (vietato, sola lettura): l'equivalenza e
  la velocita' sono verificate con query di sola lettura (§1.2), non con un
  `CREATE OR REPLACE` reale seguito da un confronto A/B della funzione live.
- **Non ho un numero "quanto piu' veloce" per blocchi PIU' PESANTI** del primo blocco
  della corsa rossa del 26/09 (es. un blocco con solo grandi campionati nazionali, molte
  stagioni): ho misurato il blocco REALE che ha causato il crash (lega 1+2), non ho
  ricostruito blocchi ipotetici piu' gravosi per restare dentro il perimetro "sola
  lettura, nessuna esecuzione ripetuta pesante sul DB vero".
- **Non ho una controprova diretta del limite 8s con un timeout REALE indotto**: la
  correzione (§0.3) si basa su `pg_db_role_setting` (letto due volte, io e il
  coordinatore, stesso risultato) + la documentazione ufficiale Supabase/PostgREST
  citata; non ho eseguito una query volutamente lenta CON la chiave service_role per
  vedere il 57014 scattare a 8s esatti (vietato: eseguirei codice di produzione o
  simulerei carico sul DB vero).
- **Non ho toccato `season_backfill.py`** (fuori perimetro esplicito): le sue due
  chiamate a `sa.attacca` (righe 120, 208, lega-stagione singola) beneficiano comunque
  della correzione fatta in `season_aggregates.py` (stessa funzione condivisa), ma non
  ho aggiunto test dedicati a quei due punti di chiamata specifici.
- **Non ho verificato `actionlint`** (non installato).
- **Non ho verificato la richiesta reale del contatore `degradato_57014` in produzione**
  (non eseguibile: scriverebbe sul DB vero).

## 7. Decisioni per l'utente

Nessuna tocca una strategia di trading (questo cantiere e' infrastruttura dati, non bot).

1. **Applicare la migrazione `season_gaps_perf_2026-09-28.sql`?** Con il limite reale di
   8 secondi (§0.3, non 2 minuti come avevo scritto la prima volta), la raccomandazione
   CAMBIA rispetto alla prima versione di questo referto: la riscrittura non e' piu' "un
   miglioramento facoltativo" ma riduce di ~11x il tempo e di ~88x le letture da disco
   sullo stesso blocco che ha causato i 2 fallimenti reali, lasciando un margine molto
   piu' ampio sotto una soglia stretta. La correzione di codice (degradare invece di
   morire, punto 4 compreso) resta comunque necessaria da sola: senza la migrazione, con
   un limite di 8s, e' plausibile che le stesse lega-stagioni vengano degradate quasi
   ogni sera (il codice le gestisce correttamente, ma il DB lavorerebbe di piu' del
   necessario e la soglia "DEGRADATA PERSISTENTE" potrebbe scattare piu' spesso).
   Consiglio: applicarla.
2. **Soglia di `BACKFILL_BUCHI_MAX_GIORNI` (default 3) anche per le degradate**: ho
   riusato lo stesso knob gia' esistente per i "buchi vecchi" invece di crearne uno
   nuovo, per coerenza. Se l'utente preferisce una soglia diversa specifica per il
   57014 (es. piu' bassa, per accorgersene prima), e' un nuovo env var da aggiungere
   (`CATCHUP_DEGRADATE_MAX_GIORNI`), non implementato: 5 minuti di lavoro se richiesto.

## 8. Cosa controllare dal vivo al prossimo avvio della action

- **Se scatta ancora un 57014**: la run deve restare VERDE (o rossa solo per veri
  buchi/errori/degradate persistenti), con `[LACUNE] 57014 ... dimezzo e ritento`,
  `[CATCHUP] AVVISO: N lega-stagioni DEGRADATE`, e nel referto finale sia "DEGRADATE per
  57014" sia (se capita anche sugli aggregati) "AGGREGATI DEGRADATI per 57014".
- **Le degradate di un giorno isolato devono sparire il giorno dopo** (si riverificano;
  nessuna riga "DEGRADATA PERSISTENTE" finche' non superano 3 giorni consecutivi).
- **Se una lega-stagione resta degradata per 4+ giorni consecutivi**: deve comparire
  "DEGRADATA PERSISTENTE" nel referto e la run deve uscire con codice 1 (visibile, non
  piu' muta) - controllo, `gh run view <id> --log`, cercare la stringa.
- **Dopo l'eventuale applicazione della migrazione**: il numero di 57014 nei log delle
  corse serali dovrebbe calare sensibilmente (non azzerarsi: il limite resta stretto, 8s).
