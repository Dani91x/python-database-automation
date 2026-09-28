# CANTIERE D1 — SAFE E MIKE: PAPER SPECCHIO DEL LIVE (28/09/2026)

Delegato D1, worktree `agent-ae168c1f19f739518`, base `2eb3c1d`. Lavoro **NON committato**.
Ordine dell'utente (28/09): «deve essere lo specchio per tutti i bot»; sul doppio fill di Safe: «fixa».
Piu' tre aggiunte del coordinatore nella stessa giornata (proposte d'uscita, posizioni aperte al
riavvio, aggregati per modalita' + niente fill paper «di casa»).

## 0. Esito in poche righe

| # | Difetto | Esito |
|---|---|---|
| 1 | Safe paper: doppio fill se accodamento KO e ricerca per ref KO | **CORRETTO** (`execution.py:1144`) |
| 2 | Mike: riserva con risposta persa, riga `pending` che blocca per sempre | **CORRETTO** (+ id assente, + freno paper) |
| 3 | Timeout PostgREST 120 s | **CORRETTO** per i processi Safe e Mike (profilo bot 5 s / 20 s) |
| A1 | Safe: proposte d'uscita `cashout` mai decadute (6 del 26/09) | **CORRETTO** (spazzino + verifica all'approvazione) |
| A2 | Posizioni paper aperte su partite finite ad app spenta | **CORRETTI 2 difetti**: Safe blocco misto OPEN/CLOSED, Mike finestra 48 h |
| A3 | Aggregati che decidono: solo la modalita' attiva | **CORRETTI 3 difetti** (Safe richieste UI, Mike tetto di armo, Mike ripiego/memoria aggregati) |
| A3-b | Niente fill paper «di casa» in `execution.place`/`close_trade` | **NON FATTO** — misurato: rompe 128 test e spegne Mike paper (manca il lettore della coda per Mike, lavoro F7). Piano in §6 e in `STATO_RIPRESA.md` |
| P | Parita' Mike alla sospensione (paper teneva viva la lay che Betfair cancella) | **CORRETTO** (trovato nell'audit) |

Suite dei moduli toccati: **Mike 952 passati**, **Safe 1911 passati, 3 saltati, 1 xfailed**,
`db_client` 25 passati. 47 mutazioni, tutte ROSSE (una prima verde, test rinforzato), ripristino
byte-identico verificato con SHA-256 per ciascuna.

---

## 1. Cause radice (con prova) e correzioni

### 1.1 Safe — doppio fill paper (`Betfair/safe_strategy/execution.py`)
**Causa**: in `enqueue_place`, dopo l'errore dell'accodamento, la ricerca per `client_ref` puo'
fallire anch'essa. Il codice tornava `ENQUEUE_UNKNOWN` **solo** con `mode == "live"`; in paper
tornava `None` e `place()` scendeva al fill simulato in casa (`execution.py:737-790`). Ma la riga
di coda poteva essere gia' scritta (risposta persa): il runner la eseguiva col suo matching →
**due esecuzioni dello stesso ordine**.
**Correzione** (`execution.py:1144`): `if lookup_failed:` per entrambe le modalita'. La riga resta
`pending` col marcatore `flumine_client_ref`; la risolve `omega_service.poll_flumine_pending` →
`_recover_flumine_orphan` (adotta la richiesta per ref; se non esiste: paper `no_fill`, live
riserva liberata). Nessun secondo percorso in nessun modo. Ramo «ricerca riuscita e risponde
"non c'e'"»: invariato (l'accodamento certamente non e' avvenuto, ripiego di sempre).

### 1.2 Mike — riserva con risposta persa (`Betfair/mike/service.py`)
**Causa**: `_insert_trade_row` puo' sollevare dopo il commit sul server. La gamba diventa
`cancelled` (`reserve_failed`), la riga `pending` resta: nessuno la chiude (`_reconcile_trades`
salta le righe la cui gamba esiste ancora in `ctx.legs`; le gambe annullate non sono «live»).
`_gia_appoggiata` (fail-closed) la vede come «gamba gia' in volo» e blocca **per sempre** il
green-up/copertura dello stesso ruolo e ciclo. Aggravante trovata: quando la gamba annullata
viene potata (`engine.prune_dead_legs`, max 5 annullate per ruolo — e il freno stesso ne genera
una a ogni riproposta) la riga diventa senza gamba; se e' una gamba di chiusura
(`closes_trade_id`) la regola delle orfane la salta del tutto → `pending` a vita anche in paper.
**Correzione**:
- `_aggancia_riserve_orfane` (`service.py:4129`, chiamata in `_reconcile_trades:4246`): riga
  `pending` con gamba annullata ad abbinato zero, o senza gamba (ricostruita da `_gamba_dalla_riga`
  `:4091` se mercato/selezione/lato sono leggibili) → gamba in `pending_reconcile`, riga marcata
  `place_exception_reconciling` + `riserva_orfana`. Decide `_reconcile_unknown`, **stesso codice
  per paper e live**: paper → chiusa come non eseguita; live → Betfair per bet_id / `mike-t<id>` /
  ref storico a mercato concorde: abbinata → agganciata (posizione visibile), viva → si aspetta,
  assente → chiusa. Ruolo di nuovo libero, mai doppia copertura.
- `_mirror_is_aligned` non da' piu' «specchio allineato» se una riga non terminale ha la gamba
  annullata (altrimenti la riconciliazione non leggeva nemmeno le righe).
- `insert_trade` che torna `None` (`:738`, `:1346`): trattato come riserva fallita. Prima
  `execute_place` esplodeva su `int(None)` e la lay appoggiata live partiva col ref `leg.ref`
  (catalogo §7 punti 4 e 6: ordine irriconoscibile dalla riconciliazione).
- **Parita'**: il freno anti-doppione della lay appoggiata esisteva solo sulla strada LIVE; ora e'
  `_freno_gia_appoggiata` (`:1194`) usato da live e paper.

### 1.3 Timeout PostgREST (`db_client.py`)
**Causa**: `create_client` senza opzioni = 120 s su connessione, lettura e scrittura
(`supabase 2.28.0`, `ClientOptions.postgrest_client_timeout=120`). Rete «a buco nero» → un giro
appeso minuti per ogni chiamata.
**Misure** (sola lettura sul DB): `pg_roles`: `authenticator` ha `statement_timeout=8s` e
`lock_timeout=8s`, `service_role` nessun valore proprio → ogni query PostgREST muore a 8 s; nessuna
RPC chiamata da Safe/Mike alza il limite (`get_safe_aggregates`, `get_mike_aggregates`,
`request_betfair_live_order`, `get_live_settings`, `live_order_mode_avvio`: nessun
`statement_timeout` nelle migrazioni). `pg_stat_statements` sulle tabelle dei bot: massimo
osservato **6,3 s** (`safe_strategy_scan`), `get_mike_aggregates` 5,8 s.
**Correzione**: default globale **invariato** (runner, backfill, action hanno RPC a 60-600 s:
`get_market_delays` 15 min, `refresh_analytics_riepilogo` 600 s…). Nuovo profilo bot
`usa_timeout_bot()` = `httpx.Timeout(20, connect=5, pool=5)` (override `SUPABASE_BOT_CONNECT_S`,
`SUPABASE_BOT_LETTURA_S`; vuoto/0/negativo = default), acceso all'avvio dei soli processi
**Safe bot** (`bot_service.main` → `_usa_timeout_bot`, vale anche per Safe tennis che gira nello
stesso processo) e **Mike** (`service.main`). Vale per tutti i thread e sostituisce i client gia'
creati. Verificato che il timeout arriva a `client.postgrest.session.timeout`.
**Fuori perimetro**: Omega (`omega_service.main`, cantiere C) e scanner (`safe_strategy/service.py`)
restano a 120 s: basta una riga `db_client.usa_timeout_bot()` nei loro `main`.

### 1.4 Safe — proposte d'uscita mai decadute (aggiunta 1)
**Causa**: decadevano solo in `_process_exit_one` (posizioni ancora candidate alle uscite). Posizione
chiusa/regolata/coperta, partita uscita dal feed, servizio spento → `proposed` per sempre.
`scadi_proposte_opportunita` (`bot_db.py`) filtra `kind='place'`.
**Cosa succede OGGI se l'utente approva una proposta vecchia** (codice di partenza):
`process_requests` misura l'eta' dal clic (`approved_at`, `bot_service._request_age_s`) quindi la
richiesta e' «fresca»; `_request_cashout` rifiuta solo se la riga non e' `open` o il mercato non e'
`OPEN`; altrimenti chiude **ai prezzi di adesso** (feed fresco o book REST; `price_at_decision` non
e' usato) **senza ricontrollare la condizione d'uscita**: una «uscita in perdita» decisa al 65'
approvata all'88' in profitto veniva eseguita.
**Correzione**:
- `_decadi_proposte_non_eseguibili` (`bot_service.py:3619`, in `run_once` dopo le uscite `:9435`),
  una SELECT ogni 30 s (`bot_db.proposte_di_chiusura_vive`), decadenza per id atomica
  (`bot_db.chiudi_proposta_per_id`, `.eq("status","proposed")`), stessa marca `rejected` +
  `result.decaduta` + motivo. Decade se: posizione non piu' `open`; mercato della posizione
  `CLOSED` nel feed (`exits.market_status`, nuovo; `SUSPENDED` NON fa decadere); uscita del bot non
  riconfermata da 120 s (`_PROPOSTA_SENZA_CONFERMA_S`; il bot riconferma ogni ~20 s finche' la
  condizione regge). Il marcatore sulla riga viene tolto: se la condizione torna nasce una proposta
  NUOVA coi dati di allora (non «ignorata dall'utente»). Le coperture B25 (gambe manuali) decadono
  solo a posizione finita o mercato chiuso.
- All'approvazione (`_request_cashout` → `_proposta_non_piu_valida` `:3581`, chiamata `:3285`):
  regole (base/esatto/punta/tennis) → la stessa `exits.decide` sul feed di adesso deve dare la
  STESSA uscita, altrimenti `rejected` + `decaduta` («condizione cambiata / non vale piu'»); feed
  assente → rifiutata; modello → marcatore riconfermato da ≤120 s. Il «Cash out» della scheda
  (senza `exit_kind`) non passa di qui. Prezzi sempre quelli di adesso.
Le 6 righe vecchie (311, 315, 318-321): le pulisce la sanatoria SQL del coordinatore; col nuovo
codice decadono comunque al primo giro dello spazzino (posizioni non piu' open) — vedi §8.

### 1.5 Posizioni aperte su partite finite ad app spenta (aggiunta 2)
**Fonti**: Safe regola con `listMarketBook` (`omega_market.read_markets`, runner WINNER/LOSER,
`execution.settle_position`; `listClearedOrders` solo live e con finestra 72 h, poi ripiego sul
calcolo); Mike con `read_book` (un mercato per chiamata) → `settle_plan`, e dopo 2 h senza book
ripiego sull'ultimo punteggio visto in gioco, altrimenti `ERROR`.
Documentazione Betfair `listMarketBook`: «Separate requests should be made for OPEN & CLOSED
markets. Requests that include both OPEN & CLOSED markets will only return those markets that are
OPEN» ([listMarketBook](https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687510/listMarketBook)).
Conservazione dei mercati chiusi: circa 90 giorni secondo fonti secondarie (non trovata nella
pagina ufficiale): due giorni sono ampiamente dentro.
**Difetto Safe**: `_read_markets_batch` mette fino a 40 mercati in una richiesta; con anche un solo
mercato aperto in lettura (una posizione pre-partita o sospesa lo e' sempre) i CHIUSI mancano dalla
risposta → `None` → `_market_missing` → **mai regolati**. **Correzione** (`bot_service.py:2075`):
chi manca da un blocco di piu' mercati si rilegge da solo (max 4 per ciclo, `_CHIUSI_SINGOLI_PER_CICLO`);
se neppure cosi' c'e', resta «mancante» (nessun esito inventato).
**Difetto Mike**: `run_once` carica `list_events(since_iso=adesso-48h)`, filtro su `updated_at`; ad
app spenta le schede non si aggiornano → dopo 48 h una partita NON terminale sparisce dal ciclo e
le righe restano `open` per sempre. Sul DB oggi: 2 partite non terminali (Latvia U21, MVV) ferme dal
26/09 17:40Z → sarebbero uscite dalla finestra il **28/09 alle 17:40Z**. **Correzione**
(`mike/db.py:99`): con `since_iso` il filtro diventa `updated_at >= since OR state not in
(SETTLED,ERROR,SKIPPED)` in UNA sola SELECT (`filtro_finestra_eventi`). Verificato con una GET in
sola lettura su PostgREST: 7 righe, identiche all'SQL equivalente. Nessuna lettura in piu' (regola
del respiro del 13/09).

### 1.6 Aggregati per modalita' (aggiunta 3)
Verificato: Safe segnali automatici = contesto di rischio per modalita' (`scan_and_place._ctx_di`),
`get_safe_aggregates(p_mode)` e `get_mike_aggregates(p_mode)` per modalita' (applicate: verificato
su `pg_proc`), Mike `_locked_open_pnl(mode)`, `_open_liability(mode)`, `posti_occupati_per_modo`.
Difetti trovati e corretti:
1. **Safe richieste UI / proposte approvate** (`_request_place`, `_request_place_combo`): usavano il
   contesto del CICLO (modalita' del servizio) anche per ordini dell'altra modalita' (con
   `strategy_modes`) → nuovo `_ctx_della_modalita` (`bot_service.py:2621`).
2. **Mike tetto che ARMA le candidate** (`service.py:2932`): contava le partite di entrambe le
   modalita' → solo quelle della modalita' attiva.
3. **Mike aggregati** (`mike/db.py:356`, `service.py:981-1030`): (a) qualunque errore (anche un
   timeout) marcava la RPC «assente» per tutta la vita del processo e il ripiego sommava paper e
   live → ora «assente» solo su errore di schema (PGRST202/42883), il transitorio risale e si riusa
   l'ultimo valore buono; (b) il ripiego filtra per modalita'; (c) la RPC riceve `p_mode` esplicito;
   (d) memoria e cache degli aggregati PER MODALITA'.
Nessuna migrazione necessaria (le RPC per modalita' sono gia' sul DB).

### 1.7 Parita' Mike alla sospensione (trovato nell'audit)
`_sorveglia_sospensione` in paper dichiarava esito `"paper"` e teneva la lay appoggiata viva; in live
la piazza sempre `persistenceType: LAPSE` (`omega_market.py:735`) e le regole Betfair cancellano gli
ordini non abbinati alla sospensione per evento materiale (gol, rigore, espulsione:
[General Rules](https://support.betfair.com/app/answers/detail/exchange-general-rules/)). Ora paper =
esito `scaduto` con la stessa reazione del live (`_applica_esito_riapertura`, `service.py:2317`).
Il test che fissava la divergenza (`test_in_paper_non_si_chiede_niente_a_betfair`, catalogo §7.28) e'
stato corretto.

---

## 2. File toccati (elenco esatto)
Codice: `db_client.py`; `Betfair/safe_strategy/execution.py`; `Betfair/safe_strategy/bot_service.py`;
`Betfair/safe_strategy/bot_db.py`; `Betfair/safe_strategy/exits.py`; `Betfair/mike/service.py`;
`Betfair/mike/db.py`.
Test modificati: `Betfair/safe_strategy/tests/test_bot_service.py` (FakeDB: `proposte_di_chiusura_vive`,
`chiudi_proposta_per_id` come il vero; reset dello spazzino), `test_chiusura_dell_utente_2026_09_16.py`
(condizione dichiarata valida: oggetto del test e' il marcatore), `Betfair/mike/tests/test_mike_ko_green_appoggiata_2026_09_16.py`
(asseriva la divergenza), `Betfair/mike/tests/test_mike_review_2026_09_11.py` (RPC assente = errore di schema vero).
Test nuovi: `Betfair/safe_strategy/tests/test_d1_enqueue_ignoto_paper_live_2026_09_28.py` (7),
`test_d1_proposte_uscita_2026_09_28.py` (22), `test_d1_regolazione_al_riavvio_2026_09_28.py` (4),
`test_d1_rischio_per_modalita_2026_09_28.py` (2); `Betfair/mike/tests/test_mike_d1_riserva_orfana_2026_09_28.py` (14),
`test_mike_d1_regolazione_al_riavvio_2026_09_28.py` (7), `test_mike_d1_aggregati_per_modalita_2026_09_28.py` (6);
`Betfair/stream/tests/test_db_client_timeout_bot_2026_09_28.py` (10).
Strumenti (fuori codice): `AUDIT_2026-09-28/d1/falsifica.py` + file `*_old/_new.txt` delle mutazioni,
`patch_prima.diff`. Nessuna migrazione.

## 3. Test e falsificazioni
Comandi (dal worktree, `.venv` in junction):
`python -m pytest Betfair/mike/tests -q -p no:cacheprovider` → **952 passed** (11,6 s);
`python -m pytest Betfair/safe_strategy/tests -q -p no:cacheprovider` → **1911 passed, 3 skipped, 1 xfailed** (64,9 s);
`python -m pytest Betfair/stream/tests/test_db_client_timeout_bot_2026_09_28.py Betfair/stream/tests/test_net_retry.py -q` → **25 passed**.
Falsificazioni (`python AUDIT_2026-09-28/d1/falsifica.py <file> <old> <new> <test>`; ogni giro
ripristina e confronta SHA-256; `grep -c MUTAZIONE` = 0 a fine giro):
| id | mutazione | rossi |
|---|---|---|
| m1 / m1b / m1c | `mode=="live" and lookup_failed` / ramo ignoto spento / ignoto anche su «non c'e'» | 4 / 5 / 2 |
| m2a…m2g | aggancio tolto, specchio cieco, ricostruzione None, freno paper tolto, id None ignorato (resting / execute_place), gamba viva agganciata | 8, 2, 2, 1, 1, 2, 1 |
| m3a…m3d | profilo non salvato, client senza opzioni, client in cache non rinnovato, override ≤0 accettato | 3, 3, 1, 2 |
| p1…p9 | spazzino tolto, solo «sparita», CLOSED ignorato, riconferma ignorata, marcatore lasciato, verifica all'approvazione tolta, tipo d'uscita non confrontato, coperture trattate come uscite, modello senza riconferma | 12, 2, 1, 1, 1, 3, 2, 1, 1 |
| r1 / r2 | rilettura singola tolta / tetto 0 | 3 / 3 |
| k1 / k2 (db.py) | finestra solo `updated_at` / terminali sbagliati | 1 / 2 |
| l1 | paper alla riapertura di nuovo «paper» | 2 |
| a1…a6 | ripiego senza filtro, RPC senza `p_mode`, ogni errore = RPC assente, cache cieca alla modalita', memoria unica (**prima VERDE**, test rinforzato poi rosso), tetto di armo misto | 1 ciascuna |
| s1 | Safe: contesto del ciclo sempre | 2 |
RED sul codice di partenza: ogni mutazione qui sopra RIPRODUCE il codice di prima nel punto
corretto (m1, m2a, p1, r1, k1, l1, a1-a3, a6, s1 sono letteralmente il vecchio codice).

## 4. Migrazioni
Nessuna.

## 5. PARITA' PAPER / LIVE — Safe (base, esatto, punta, model) e Mike

| # | Ramo | file:riga | Paper | Live | Verdetto |
|---|---|---|---|---|---|
| S1 | esito accodamento ignoto | `execution.py:1144` | era: fill in casa (doppio) | riga pending, ref | **BUG corretto** → uguale |
| S2 | gate flumine aperto | `execution.py:701-713` | coda, FOK, LAPSE | coda, FOK, LAPSE | uguale |
| S3 | gate chiuso: aperture/chiusure | `execution.py:737-790` vs `810-915` | fill IN CASA sul libro del feed, istantaneo, **senza bet delay** | REST FOK (Betfair applica il bet delay) | **BUG aperto** (A3-b, §6) |
| S4 | FOK / parziali | `execution.py:767-769` | FOK: parziale ucciso | FOK REST | uguale |
| S5 | prezzo del fill (al best) | `bot_service._paper_ladder:5701`, `execution.py:752` | livello del feed = best, dentro il limite | abbinamento al best | uguale (il fix Mike 67c3ad4 qui c'era gia') |
| S6 | sotto il minimo (place-and-trim) | `execution.py:725-736` vs `819-823` | fill FOK diretto della size | parcheggio→taglio→riprezzo: al riprezzo l'ordine e' un limite, puo' restare non abbinato | **divergenza aperta** (effetto del simulatore, §6) |
| S7 | chiusura paper senza size nota | `execution.py:1608` | rimanda la chiusura | decide Betfair col FOK | divergenza di natura (senza size non si simula): si chiude col percorso a coda di §6 |
| S8 | freno (kill-switch) | `execution.py:744` / `810` | freno unico sulle aperture | stesso + modo ordini | uguale |
| S9 | riconciliazione pending | `bot_service.py:1050-1184` | nessun ordine reale: errore terminale | Betfair per bet_id/ref | uguale nella sostanza |
| S10 | canale: annullo senza ack | `execution.py:573,584` | esito ignoto | ripiego REST | di natura (non esiste REST paper) |
| S11 | posizione di conto | `bot_service._sorveglia_posizione_di_conto` | non letta | letta | di natura |
| S12 | settlement / commissione | `execution.settle_position`, `:1935` | runner WINNER, commissione della riga | cleared orders (profit) o stesso calcolo | uguale (fonte Betfair quando c'e') |
| S13 | cap / stop / idempotenza (segnali) | `bot_service.py:6424-6449` | per modalita' | per modalita' | uguale |
| S14 | cap delle richieste UI | `bot_service.py:2621` | era: cap dell'altra modalita' | idem | **BUG corretto** |
| S15 | proposte d'uscita | `bot_service.py:3581,3619` | — | — | stesso codice, test in entrambe |
| S16 | lettura mercati chiusi (settlement) | `bot_service.py:2075` | — | — | stesso codice |
| M1 | invio | `mike/service.py:744` | `execution_mode='rest'` → fill in casa (col bet delay applicato da Mike in gioco, `:3832`) | REST FOK | **divergenza aperta** (A3-b: lettore coda Mike = F7) |
| M2 | bet delay | `mike/service.py:3832` | differita di `bet_delay` poi fill sul libro di allora | Betfair | uguale nell'effetto (non nella coda) |
| M3 | feed stantio | `mike/service.py:689` | nessun fill | l'ordine parte (decide Betfair) | **decisione utente** (§7) |
| M4 | lay appoggiata: fill | `mike/service.py:2382` `_resting_filled` | abbinata solo se il best back scende SOTTO il prezzo, per intero, senza coda | coda vera, parziali | **divergenza aperta** (simulatore; §6, catalogo §7.13) |
| M5 | lay appoggiata alla sospensione | `mike/service.py:2317` | era: resta viva | LAPSE: scade | **BUG corretto** |
| M6 | freno anti-doppione appoggiata | `mike/service.py:1194` | era: assente | presente | **BUG corretto** |
| M7 | riserva orfana | `mike/service.py:4129` | chiusa come non eseguita | Betfair decide | uguale (stesso codice) |
| M8 | riga senza gamba (open) | `mike/service.py _reconcile_trades` | chiusa `orphan_paper` | solo marcata | di natura (paper non ha posizione vera) |
| M9 | posizione di conto / rilettura resting | `:2155`, `_segui_resting_live` | non letta | letta | di natura |
| M10 | aggregati / tetti | `mike/db.py:356`, `service.py:981,2932` | erano misti in ripiego, memoria e armo | idem | **BUG corretti** |
| M11 | `MIKE_LIVE_ENABLED` | `:90` | — | guardia soldi veri | di natura |
| M12 | dry | `:717, 3796` | `would_place` | idem | uguale |

## 6. Cosa NON ho fatto e cosa NON ho potuto verificare
**Non fatto — A3-b «niente fill paper di casa»** (ordine del coordinatore). Misura: sostituendo il
fill in casa di `execution.place` con «non eseguito» falliscono **128 test** di Safe e Mike, e Mike
paper smette di operare del tutto: Mike invia in REST (`execution_mode='rest'`) e **non ha un lettore
degli esiti della coda** (reperto M1 del 24/09, `AUDIT_STRADE_ORDINE_2026-09-24.md:251`; «MK5 …
accendere dopo costruzione e certificazione», `AIUTI_SPENTI_DI_DEFAULT_2026-09-25.md:86`). Farlo a
meta' spegnerebbe Mike paper in silenzio. Piano (in `STATO_RIPRESA.md`):
1. Mike: lettura degli esiti della coda sulle gambe (`omega_service.poll_flumine_pending` con `mike/db`,
   che ha gia' gli accessori copiati) + allineamento gamba←riga (abbinato, prezzo medio, stato);
   togliere la differita paper `:3832` quando l'ordine passa dalla coda (se no bet delay doppio,
   catalogo §7.12); lay appoggiata paper via coda (fine di `_resting_filled`, §7.13); banco F7.
2. Safe e chiusure di Omega via `execution.close_trade`: con gate chiuso in paper → `error
   paper_senza_runner:<motivo>` (le uscite restano in `retrying`/`failed` visibili col backoff);
   adeguare il finto di `test_bot_service` a una coda simulata (oggi `follow="NONE"` = fill in casa
   in centinaia di test).
3. Replay del banco per Safe e Mike dopo 1-2 (li lancia il coordinatore).
**Non fatto**: Omega e scanner senza il profilo di timeout (cantiere C / fuori perimetro); Mike con
book illeggibile per 2 h e senza partita vista in gioco resta `ERROR` con righe `open` (oltre ~90
giorni di conservazione Betfair; caso non riprodotto).
**Non verificato**: nessuna caduta di rete reale; nessun ordine vero; il comportamento di Betfair
sulle sospensioni NON materiali (in live si rilegge l'esito, in paper ora si applica sempre
«scaduto»); la conservazione di 90 giorni dei mercati chiusi (fonte secondaria); i replay del banco
NON lanciati (regola del carico: li lancia il coordinatore) — da rilanciare **Mike** (M5 cambia il
paper alla sospensione, orfane) e **Safe** (proposte, settlement). Un test preesistente
(`test_audit_2026_09_11.py::test_l4_…`) e' risultato rosso **anche sul codice di partenza** in un giro
e verde in un altro: dipende dall'ambiente (i freni live leggono `.env`/DB veri) — da isolare.
Alcuni test preesistenti di Safe/Mike creano un client Supabase vero (warning di deprecazione): i
miei test lo vietano esplicitamente.

## 7. Decisioni per l'utente (solo regole di trading)
1. **Mike, feed stantio** (`mike/service.py:689`): in paper con il feed fermo non parte nulla, in live
   l'ordine parte coi prezzi del feed fermo e decide Betfair. Proposta: stessa regola in entrambi —
   **in live non si invia un ordine su un feed stantio** (e' la regola del paper, piu' prudente).

## 8. Controlli dal vivo in PAPER al prossimo avvio
| controllo | atteso | dove |
|---|---|---|
| Safe 359 Bulgaria-Luxembourg (lay «Altro risultato Ospite» 60 x 2), finale **1-2** | `won`, pnl ≈ +1,90 (commissione 5%) | `safe_strategy_trades` |
| Safe 361 Faroe-Kazakhstan (lay «Altro Casa» 30 x 2), **1-1** | `won`, ≈ +1,90 | idem |
| Safe 362 Kuwait-Iraq (lay «Altro Ospite» 60 x 2), **2-3** | `won`, ≈ +1,90 (2-3 e' fra i risultati elencati) | idem |
| Safe 363 Iceland-Estonia (lay «Altro Casa» 34 x 2), **1-1** | `won`, ≈ +1,90 | idem |
| Mike 5077/5078 (back Under 3.5) Latvia U21-Germany U21, **0-4** | `lost` −5,00 e −2,50 | `mike_trades`; evento `SETTLED` |
| Mike 5080/5081 (back Over 4.5) stessa partita, 4 gol | `lost` −6,40 e −6,67 | idem |
| Mike 5082 (back Under 3.5 1,48 x 5) MVV-Helmond, **2-0** | `won` ≈ +2,28 | idem; evento da `PRE_OPEN` a `SETTLED` |
| Proposte 311, 315, 318-321 (se la sanatoria non e' ancora passata) | `rejected`, `result.decaduta`, motivo «posizione non piu' aperta» entro ~30 s dalla regolazione | `safe_strategy_requests` |
| Nessun `market_missing` ripetuto su mercati chiusi | assenza di `market_missing` per 1.262661603/513/536, 1.262898785 | `safe_strategy_activity` |
| Log di avvio | `timeout PostgREST del profilo bot: Timeout(connect=5.0, read=20.0, write=20.0, pool=5.0)` per `[safe.bot]` e `[mike]` | log dei processi |
Esiti attesi dal risultato reale (`matches`, API-Football); la verita' la dice il `listMarketBook`
di Betfair al riavvio.
