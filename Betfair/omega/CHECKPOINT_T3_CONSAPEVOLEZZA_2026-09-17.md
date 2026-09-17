# CHECKPOINT T3 — consapevolezza completa degli ordini (Omega), 17/09/2026

Delegato Sonnet 5, worktree isolato `.claude/worktrees/agent-a0af86bc55e604bb2`.
**Base finale: `3733f17` (master locale)**, dopo `git merge master` in corsa (vedi §0).
Nessuna strategia toccata. Nessun commit creato (`git status` pulito su HEAD, nessun
`git add -A`), DB solo in lettura, nessuna chiamata Betfair, nessun processo nuovo.

## 0. Riallineamento a master (ordine del coordinatore)

Il worktree era partito da `1ee7624` (16/09 sera), 5 commit indietro rispetto al
`master` locale (`3733f17`, dove vivono K7, `_mirror_fill` gia' corretto, il catalogo
numerato, `PROGETTO_OMEGA_V4_2026-09-17.md`, la sintetica `_synth_omega_prezzo_migliore`,
976 test). Procedura seguita (mai bare `git stash`/`pop`, coerente con la regola del
worktree condiviso):

1. `git stash push -u -m "t3-omega-preT3merge-agent-a0af86bc"` → catturato lo SHA
   (`6ddebce2f6d529f5ff840d85eecbe4bbcb8ef633`) da `git stash list --format='%H %gs'`.
2. `git merge master --no-edit` sull'albero pulito → fast-forward, nessun conflitto (i
   miei cambi erano nello stash, non nel working tree).
3. `git stash apply 6ddeb...` → conflitto SOLO su `omega_service.py` (12 marker), NESSUNO
   su `omega_engine.py` (master non tocca `reconcile_decision`/`candidate_customer_refs`).
4. Risolti i 12 marker A MANO, punto per punto (§1 sotto: dove master aveva gia' chiuso
   `_mirror_fill`/K7, tenuta la sua versione, PIU' precisa della mia — residuo VERO dallo
   specchio, non un 0.0 fisso; dove non l'aveva chiusa, tenuta la mia).
5. `git add` (solo per marcare risolto, poi `git reset` per lasciare tutto SPOSTATO, non
   in stage — coerente col resto della sessione) → `git stash drop stash@{0}` (verificato
   lo SHA droppato = quello catturato al punto 1).
6. Verificato baseline PRIMA di ogni cosa mia: `git show master:...` nei due file →
   `python -m pytest Betfair/omega` **973 passed, 3 skipped** (master puro, senza i miei
   file). **Non 976**: la differenza (3) sono probabilmente test aggiunti/tolti fra il
   momento in cui il coordinatore ha contato e ora, o un arrotondamento del coordinatore —
   non l'ho potuto verificare oltre, la baseline MISURATA e' quella sopra.
7. Nessuna junction/symlink creata verso `.venv`/`node_modules`: `.venv/Scripts/python.exe`
   del checkout principale usato per ogni test e replay, come da regola.

## 1. Cosa era GIA' su master, cosa resta MIO (per file:funzione)

| area | master (`_mirror_fill`/K7) | mio (aggiunto sopra) |
|---|---|---|
| `_mirror_fill` | Gia' corretta il 17/09: 5-tupla `(matched, avg, status, size_remaining, betfair_updated_at)`, `size_remaining` letto DAVVERO da `src.get("size_remaining")` (non un 0.0 fisso come nella mia prima stesura), `betfair_updated_at` da `mirror.get("matched_at")`. **Tenuta la versione di master**, la mia era una sotto-approssimazione. | — |
| `_flumine_confirm` | Gia' accetta `size_remaining`/`betfair_updated_at` come parametri e li scrive nel `meta` PRIMA di `_confirm_open_trade` (righe ~2021-2053). | **Aggiunto io**: il blocco `place_parziale` (R-J6) quando `matched + 0.005 < tr['size']`, PRIMA della conferma — master non lo aveva (solo il place REST diretto lo loggava). |
| 5 call-site di `_flumine_confirm` (poll paper x3, poll live x2) | Gia' passano `size_remaining=size_remaining` (dal tuple di `_mirror_fill`) — **tenuta la versione di master** (piu' precisa della mia `betfair_updated_at=mirror_at` senza propagare il residuo vero). | — |
| `_place_one` ramo PAPER legacy (`:1619-1651`) | **NON toccato da master** (`omega_service.py` e' "di O1" per il progetto V3/V4, il paper legacy non e' stato riaperto). | **Mio, invariato dal merge**: `place_parziale` sul fill parziale (fully_matched=False), `meta["size_remaining"] = 0.0` dichiarato. |
| `reconcile_pending` ramo LIVE (`:2578+`) | **NON toccato da master**: la `_confirm_open_trade` nel ramo `act == "confirm"` non passava (ne' prima ne' ora su master) `size_remaining`/`betfair_updated_at` dell'ordine trovato da `reconcile_decision`. | **Mio, invariato dal merge**: `extra_meta={"size_remaining": d.get(...), "betfair_updated_at": d.get(...)}`. |
| `reconcile_pending` ramo PAPER (`:2543+`) | **NON toccato da master**. | **Mio, invariato dal merge**: `extra_meta={"size_remaining": 0.0, "betfair_updated_at": now.isoformat()}`. |
| `omega_engine.reconcile_decision` (i due rami `confirm`) | **NON toccato da master** (nessun conflitto sullo stash apply). | **Mio, invariato dal merge**: `size_remaining`/`betfair_updated_at` nel dict `confirm` (0.0 dichiarato per costruzione, istante da `matched_date`/`placed_date`; `None` dichiarato per i regolati, limite di `omega_market._riga_regolata`, CONDIVISO, non toccato). |
| `omega_engine.candidate_customer_refs` (R-J3, collisione fra gambe) | **NON toccato da master**. | **Mio, invariato dal merge**: il ref storico `omega-<event_id>` non e' piu' candidato per i trade CON `phase` (le due gambe v2 condividono lo stesso `event_id`). |
| `certificazione.py` K7 (`:1701`) | Gia' esiste (aggiunta da master il 17/09): controlla che, quando il META ha GIA' il numero giusto, la COLONNA non resti NULL (bug: scrittura passata per `db.update_trade` diretto invece che `X.aggiorna_trade`). | **Non toccato**: e' un controllo DIVERSO dal mio (vedi §2). |

**Riletto** `PROGETTO_OMEGA_V4_2026-09-17.md` §6 dopo il merge: conferma parola per
parola quello che ho trovato — «R-C1 — CORRETTO il 17/09... il difetto vero... era
`_mirror_fill`... **Resta aperto lo stesso buco in `reconcile_pending`**: e' quello che
la Fase 0 deve chiudere» (§6.2, riga 970). Questo e' esattamente cio' che ho chiuso.

## 2. K7 non e' ridondante coi miei test (dichiarato, come richiesto)

K7 (`certificazione.py:1701-1756`) accusa SOLO quando: `status in ('open','hedged')`,
`bet_id` presente, e **il meta HA GIA'** `requested_size`/`size_remaining`/
`betfair_updated_at` ma la COLONNA no (bug: scrittura bypassa `X.aggiorna_trade`). Il
buco che ho chiuso io era A MONTE: in `reconcile_pending`/paper-legacy il META STESSO
non aveva MAI questi valori (nessuno li calcolava), quindi K7 non poteva vederlo —
zero → zero non e' una discrepanza meta/colonna. **Non e' ridondante, e' un livello
sotto**: i miei test (`test_t3_consapevolezza_2026_09_17.py`) verificano che il VALORE
arrivi a esistere; K7 verifica che, una volta che esiste nel meta, arrivi anche sulla
colonna. Nessun test tolto.

## 3. Test, falsificazione (rifatta sui file POST-MERGE, righe cambiate)

12 test in `Betfair/omega/test_t3_consapevolezza_2026_09_17.py`. Due sono stati
AGGIORNATI dopo il merge per la nuova firma di `_mirror_fill`/`_flumine_confirm` (5-tupla
con residuo vero, non 4): `test_r_c1_mirror_fill_porta_residuo_e_istante`,
`test_r_c1_flumine_confirm_dichiara_residuo_e_istante_se_forniti`. Gli altri 10 invariati.

md5 di riferimento (stato fixato POST-MERGE):
`omega_service.py = 054a921462726245161a4f7f49b51796`,
`omega_engine.py = 7645ee67b25163d81869fee75b3a7a4c` — verificato uguale dopo OGNI
ripristino, per tutte e 4 le rotture (rifatte sui nuovi numeri di riga):

1. **R-C1 LIVE**: tolto `extra_meta=...` da `reconcile_pending` ramo LIVE →
   `test_r_c1_reconcile_live_size_remaining_e_istante_dichiarati` e
   `test_r_c1_reconcile_live_cleared_parziale_residuo_dichiarato_zero` → ROSSO
   (`KeyError: 'size_remaining'`).
2. **R-C1 PAPER**: tolto `extra_meta=...` dal ramo PAPER →
   `test_r_c1_reconcile_paper_size_remaining_e_istante_dichiarati` → ROSSO.
3. **R-J6**: tolto il blocco `place_parziale` da `_flumine_confirm` E dal ramo paper
   legacy di `_place_one` → i due test di parziale ROSSI (`assert 0 == 1`), i due test
   "fill pieno -> nessun log" restano VERDI.
4. **R-J3**: ripristinato il vecchio `candidate_customer_refs` (ref storico anche con
   `phase`) → ROSSO su entrambi i test, con la collisione VERA mostrata:
   `{'action': 'confirm', ...}` sulla gamba `ht_cs` con l'ordine storico condiviso.

Suite dopo ogni ripristino: identica, `git diff` confermato vuoto per contenuto (md5).

### Suite completa (venv del checkout principale)
```
python -m pytest Betfair/omega -q -p no:cacheprovider
  master puro (senza i miei 2 file):        973 passed, 3 skipped
  master + miei fix (senza test nuovo):     973 passed, 3 skipped   <- ZERO regressioni
  master + miei fix + test nuovo:           985 passed, 3 skipped   (973 + 12)

python -m pytest Betfair/stream -q -p no:cacheprovider
  1443 passed, 24 skipped, 0 failed
  (il fallimento ambientale di test_runner_lifecycle.py del giro precedente — porta
  47399 occupata, WinError 10048 — QUESTA volta e' passato: conferma che era una porta
  tenuta da un altro processo sulla macchina condivisa in quel momento, non una mia
  regressione. Dichiarato, non aggirato: nessuna modifica al test o al lock.)
```

## 4. Replay sul banco comune — ESEGUITO (dati letti in sola lettura dal checkout principale)

`LIVE_STREAM_DATA_DIR` puntato a `...\python-database-automation\_live_raw` (checkout
principale), MAI copiato ne' linkato nel worktree — solo letto dalla variabile d'ambiente,
per processo, come indicato.

### 4.1 Partita reale 35760084 — 4 scenari, 3 giri (prima/dopo/master-puro)
```
python -m Betfair.stream.backtest.certifica omega 35760084 --scenari esiti-ignoti,rifiuti-betfair,riavvio,base --worker 3
```
Risultato **IDENTICO** nei tre giri (master puro senza i miei file; master + miei fix;
e la stessa identita' si ripete perche' — vedi §4.2 — i miei cambi non vengono
esercitati da QUESTA registrazione):

```
ESITO: 3 partite senza violazioni, 1 con violazioni, 0 senza decisioni
       2 violazioni totali (scenario 'rifiuti-betfair', entrambe J3)

K1 x223 | K2 x223 | K3 x223 | K4 x223 | K5 x223 | K6 x223 | K7 x223  -> 0 VIOLAZIONI su tutti
J1 x2 (0 viol) | J2 x1 (0 viol) | J3 x4 (2 VIOLAZIONI) | J5 x1808 (0 viol)
J6 x0, J7 x0 — mai sollecitati (nessun fill parziale ne' cancel in questa registrazione)
F1 x6 (0 viol) | F2 x12 (0 viol)
```

**Le 2 violazioni J3 sono un reperto GIA' NOTO, non causato ne' chiuso da me**:
`CHECKPOINT_V3_2026-09-16.md:329` le documenta gia' identiche ("rifiuti-betfair... x2, su
2 partite"), ed e' il testo LETTERALE di R-J3 nel mandato. Meccanismo verificato:
`_leg_certain_failure` (`omega_service.py:1186-1226`) su un esito CERTO negativo
(`res.ok=False`, l'ordine rifiutato da Betfair, es. INVALID_ODDS) chiama
`db.delete_trade(trade_id)` — la riga di riserva viene CANCELLATA. Quando la certificazione
controlla J3 sull'evento "ordine", la riga con quell'id non esiste piu' in `db.trades`:
`_riga_dal_ref`/`_riga_del_piazzamento` non trovano nulla, J3 scatta.

**Verificato che e' sicuro OGGI, non un buco di soldi vivi**: `_place_one` chiama
`market.place_lay_live` -> `place_order_live(..., fill_or_kill=True)` (default, mai
cambiato da chi chiama in questo percorso): ogni lay LIVE di Omega porta
`timeInForce=FILL_OR_KILL` (`omega_market.py:656-666`). Un `res.ok=False` e' un rifiuto
SINCRONO e DEFINITIVO di Betfair (nessun ordine mai esistito, nessun `bet_id`); un
`res.ok=True` con `size_matched<=0` e' un FOK ucciso ISTANTANEAMENTE da Betfair (residuo
MAI vivo sul book, garantito dal FOK). In ENTRAMBI i casi non c'e' un ordine reale da
riconciliare — cancellare la riga non perde traccia di soldi a rischio OGGI.
Coerente con la nota del progetto V4 stesso (§6.2, riga 976): *"Con l'ordine FOK di oggi
e' un rischio [minore]; con una quotazione viva per minuti e' IL rischio"* — cioe' il
pericolo vero e' per il v4 futuro (quotazioni che restano vive sul book, non FOK), non
per il codice di oggi.

**NON toccato di conseguenza**: cambiare `_leg_certain_failure` (delete vs mantenere la
riga terminale per l'audit trail) e' esplicitamente FUORI dal mio perimetro per due
motivi: (1) il coordinatore ha gia' dato la direttiva "`_leg_certain_failure` con
matched=0: solo segnalato, corretto cosi'" per un'altra faccia della STESSA funzione
(R-J6), e la delete e' la stessa area di codice; (2) e' una scelta fra "cancellare la
riserva per liberare subito il retry" e "tenerla terminale per l'audit", che tocca il
budget dei tentativi (`_leg_retry_allowed`) — piu' vicina a una decisione di condotta
che a un buco di logging. **SEGNALATO, non toccato.**

### 4.1-bis FOLLOW-UP (17/09 sera, scadenza 17:45) — le 2 violazioni J3 CHIUSE

Diagnosi condivisa col coordinatore dopo la sua revisione: **falso positivo DEL
CONTROLLO** (PROCESSO §6.7), non un buco nel servizio. Corretto `_j3`
(`certificazione.py:971-1017`): quando la riga e' assente, ora NON si accusa SOLO se
ENTRAMBE le condizioni sono vere — (1) il ref e' gia' nel formato per-gamba
`omega-t<int>` (nuovo helper `_e_ref_per_gamba`, un metro indipendente dal codice,
identico principio del secondo controllo gia' presente in J3), (2) il BANCO STESSO
(`m.esito`, il `PlaceResult` VERO, MAI le attivita' scritte dal bot — §7.36) dice
`ok=False` e nessun `bet_id`: un rifiuto CERTO. Un esito IGNOTO (`m.esito is None`,
l'eccezione durante il place) NON conta come rifiuto certo — li' J3 resta acceso, come
prima. `_leg_certain_failure` NON e' stata toccata.

**4 test nuovi** in `Betfair/omega/test_omega_replay_2026_09_16.py` (accanto ai due J3
gia' esistenti), falsificati in ENTRAMBE le direzioni:
- `test_j3_non_scatta_su_rifiuto_certo_con_riga_cancellata` (il caso vero, c) → **verde**;
  rotto togliendo l'intera esclusione → **rosso** (`assert 'J3' not in ['J3']`).
- `test_j3_scatta_ancora_se_la_riga_manca_dopo_un_ordine_accettato` (a: esito ok=True,
  riga assente resta un buco vero) → verde; con l'esclusione resa TROPPO permissiva
  (tolti sia il vincolo sul formato ref sia il controllo `bet_id`, lasciato solo
  `not ok`) NON e' andato rosso da solo con `_Esito(True,...)` — l'`ok=True` gia' lo
  esclude dalla condizione larga, quindi questo test non falsifica quella specifica
  rottura (limite dichiarato: la sua funzione e' provare che un esito ACCETTATO non
  entra MAI nell'esclusione, cosa che resta vera in ogni versione provata).
- `test_j3_scatta_ancora_su_ref_malformato_anche_col_rifiuto_certo` (b: ref storico,
  rifiuto vero) → verde; con l'esclusione allargata (tolto il vincolo sul formato ref)
  → **rosso** (`assert 'J3' in []`), la falsificazione mirata a (b) ha funzionato.
- `test_j3_scatta_ancora_su_esito_ignoto_con_riga_assente` (esito IGNOTO, `m.esito is
  None`) → verde; con l'esclusione allargata (tolto il controllo `esito is not None`)
  → **rosso** (`assert 'J3' in []`): la versione larga trattava `getattr(None,'ok',False)
  = False` come "rifiuto certo", ESATTAMENTE il pericolo che il vincolo esplicito
  `esito is not None` previene — la falsificazione ha trovato la stessa insidia da due
  angoli diversi (formato ref E completezza dell'esito).

md5 `certificazione.py` fixato: `6c77ed5ffdc1d228455113d61ed7688c` — verificato
identico dopo entrambe le rotture (tolta l'esclusione intera; allargata l'esclusione).

Suite dopo il fix: `python -m pytest Betfair/omega -q` → **989 passed, 3 skipped**
(985 + questi 4). Nessuna regressione sugli altri J-test (J1/J2 ancora verdi con
`esito.ok=True`/prezzo diverso, non toccati dalla modifica).

### 4.1-ter Replay DOPO il fix (comando esatto del coordinatore)
```
LIVE_STREAM_DATA_DIR=.../_live_raw python -m Betfair.stream.backtest.certifica omega 35760084 --scenari rifiuti-betfair,base,esiti-ignoti --worker 3
```
```
ESITO: 3 partite senza violazioni, 0 con violazioni, 0 senza decisioni   <- 0 VIOLAZIONI

K1-K7  x112 ciascuno  -> 0 violazioni (tutti)
J1 x2 (0 viol) | J2 x1 (0 viol) | J3 x3 (0 VIOLAZIONI, prima erano 2 su x4) | J5 x1341
F1 x3 (0 viol) | F2 x12 (0 viol)
K2 sollecitato: SI (x112)
```
**Nota sul numero atteso**: il comando del coordinatore usa 3 scenari
(`rifiuti-betfair,base,esiti-ignoti`), NON i 4 del giro precedente (mancava `riavvio`,
che da solo contribuiva 1 sollecitazione J3 nel run originale: 4 scenari -> J3 x4,
2 violazioni; 3 scenari -> J3 x3, 0 violazioni). Il conteggio osservato e' **J3 x3**,
non "≥4" come indicato nell'atteso — riportato con esattezza, non arrotondato: la
condizione che conta (**0 violazioni**) e' soddisfatta, e la copertura di J3 e' comunque
piena (3/3 scenari possibili in questa lista lo sollecitano, 0 rossi). Non ho rilanciato
aggiungendo `riavvio` di mia iniziativa: il comando andava eseguito esattamente com'e'
stato dato.

**I miei fix R-C1/R-J3(collisione)/R-J6(fill parziale con matched>0) sono un problema
DIVERSO e ADIACENTE**, verificato a livello di test (falsificato, §3) ma **NON
esercitato da questa registrazione reale**: nessuna riga passa da `reconcile_pending` in
modalita' 'confirm' (l'unica riconciliazione vista e' 'reconciled_free', cioe' 'ordine
mai esistito', non 'confirm'), e tutte le partite giravano in modalita' LIVE (mai
paper), quindi il ramo paper-legacy di `_place_one` non e' mai stato esercitato. La
prova che il mio fix FUNZIONA sta nei 12 test + le 4 falsificazioni (§3), non in
questo replay — dichiarato onestamente, non nascosto.

### 4.2 Sintetica `_synth_omega_prezzo_migliore` — 2 scenari
```
python -m Betfair.stream.backtest.certifica omega _synth_omega_prezzo_migliore --scenari base,esiti-ignoti --worker 3
```
```
ESITO: 2 partite senza violazioni, 0 con violazioni, 0 senza decisioni

K1 x236 | K2 x236 | K3 x236 | K4 x236 | K5 x236 | K6 x236 | K7 x236  -> 0 VIOLAZIONI su tutti
J2 x1 (0 viol) | J3 x2 (0 VIOLAZIONI — qui lo scenario 'esiti-ignoti' passa dal ramo
  IGNOTO, non dal certo-negativo: la riga resta 'pending'+reconciling, MAI cancellata,
  quindi J3 non ha nulla da accusare) | J5 x634 (0 viol)
```
0 violazioni totali, exit code 0. Confermato: eseguito UNA sola volta (con i miei fix
gia' in campo); non rieseguito su master-puro per limite di tempo, ma il ragionamento
di §4.1 (nessun ramo mio esercitato: solo `place` diretto e `place_reconciling`->`free`)
vale identico qui.

## 5. Direttive del coordinatore applicate

- (a) migrazione `cancelled`/`lapsed`: **scritta**, NON applicata
  (`migrations/omega_trades_status_cancelled_lapsed_2026-09-17.sql`, idempotente, stesso
  pattern di `omega_cashout.sql`). La classificazione nel servizio resta Fase 2, NON
  toccata.
- (b) `_leg_certain_failure` con matched=0: **lasciato com'e'**, non toccato (vedi anche
  §4.1: la stessa cautela si estende alla delete-on-certain-failure, stessa funzione).
- (c) `_manual_place`/`process_manual`: **non toccato**, passato a T1. La stessa classe
  di bug R-C1 e' plausibile anche li' (`_confirm_open_trade` chiamata a `:3865`/`:3916`
  senza `extra_meta` dedicato) — solo SEGNALATO.
- `test_runner_lifecycle.py` (porta 47399): dichiarato in §3, non aggirato; questo giro
  e' passato da solo.

## 6. Cosa NON ho potuto/dovuto verificare (esplicito)

- Il replay reale (35760084) non esercita i rami che ho corretto (reconcile_pending
  confirm, paper-legacy): la prova del fix e' nei test unitari falsificati, non nel
  replay — limite della registrazione disponibile, non del fix.
- Non ho rieseguito la sintetica su master-puro (tempo): il ragionamento per analogia
  (stessi rami non esercitati) e' documentato ma non misurato numero-per-numero su
  quella specifica sintetica.
- La divergenza J3 letterale (delete-on-certain-failure) resta un reperto APERTO, gia'
  noto dal 16/09, confermato di nuovo oggi dal replay: NON l'ho chiuso (vedi §4.1 per il
  perche').
- `_manual_place`/`process_manual` (T1): non verificato se porta lo stesso buco R-C1.
- La classificazione `cancelled` vs `lapsed` nel servizio (Fase 2): non fatta per
  direttiva esplicita.

## File toccati (perimetro dichiarato)
- `Betfair/omega/omega_service.py` (modificato, ri-mergiato)
- `Betfair/omega/omega_engine.py` (modificato, invariato dal merge)
- `Betfair/omega/certificazione.py` (modificato, §4.1-bis: fix `_j3`, follow-up 17/09 sera)
- `Betfair/omega/test_t3_consapevolezza_2026_09_17.py` (nuovo, 2 test aggiornati per la
  nuova firma di `_mirror_fill`)
- `Betfair/omega/test_omega_replay_2026_09_16.py` (modificato: 4 test nuovi per `_j3`,
  §4.1-bis)
- `migrations/omega_trades_status_cancelled_lapsed_2026-09-17.sql` (nuovo, NON applicata)
- Questo referto (aggiornato)

`git status --short`: solo questi 7 percorsi. Nessuna junction/symlink. Nessun
`pip install`/`npm install`. Nessun commit (HEAD = `3733f17`, identico a master locale
prima del mio arrivo). Stash usato SOLO per il merge, catturato per SHA e droppato dopo
verifica (§0).
