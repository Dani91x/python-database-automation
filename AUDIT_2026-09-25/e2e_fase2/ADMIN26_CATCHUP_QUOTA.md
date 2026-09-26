# Referto delegato — §7.9.4 Catchup/quota: referto buchi e riserva dinamica ricalcolati

Delegato in sola lettura, coordinatore admin-26, 26/09/2026. Perimetro: SOLO §7.9.4 del piano
`PIANO_TEST_E2E_REALE_2026-09-25.md` (con appoggio a §7.4 per i controlli complementari citati
dallo stesso piano). Nessuna chiamata API-Football (vietata dal brief specifico di questo
delegato, per non consumare quota): il punto 7.9.4.B(c) e' quindi NON CERTIFICATO per limite di
perimetro, non per un difetto trovato. Nessuna scrittura sul DB: solo `.select()` e `.rpc()` su
funzioni dichiarate `stable` (`season_detail_gaps`, `season_gaps_summary`); nessun comando git di
scrittura. Nessun bot toccato, nessun ordine, nessun file del repo modificato fuori da questa
cartella.

Script di sonda (tutti in `AUDIT_2026-09-25/e2e_fase2/`, prefisso `sonda_catchup_`):
- `sonda_catchup_quota.py` — ricalcolo indipendente del REFERTO BUCHI per 3 lega-stagioni campione
  (output numerico in `sonda_catchup_quota_output.json`).
- `sonda_catchup_riserva.py` — richiama `seasons_catchup.ControlloConcorrenza.action_completate_oggi`
  di produzione (nessuna chiamata API-Football, solo GitHub) per verificare la riserva dinamica.
- `sonda_catchup_stato.py` / `sonda_catchup_stato2.py` — 7.4.1/7.4.2/7.4.6.
- `sonda_catchup_mapper.py` — conferma che il mapper ha scritto i flag prima del catchup.

Run analizzato: **seasons_catchup.yml, run 36223432528, creato 2026-09-26T06:20:02Z, concluso
2026-09-26T06:23:51Z, conclusion=success** (`gh run view 36223432528 --log`, salvato in
`%TEMP%\claude\e2e_fase2_catchup_sonda\catchup_run_20260926_0620.log`, fuori dal repo). Catena
osservata su GitHub (tutte lette con `gh run list`, sola lettura):

| workflow | run rilevante | createdAt UTC | conclusion |
|---|---|---|---|
| daily_yesterday_backfill.yml | 36222712613 | 2026-09-26T06:05:36Z | success |
| leagues_mapper.yml | (run automatico dopo Daily) | 2026-09-26T06:18:52Z→06:20:00Z | success |
| seasons_catchup.yml | 36223432528 | 2026-09-26T06:20:02Z→06:23:51Z | success |
| retrain_models.yml | (run automatico) | 2026-09-26T06:18:52Z→07:13:12Z | success (ancora in corso alle 06:23) |
| today_predictions_backfill.yml | 36227977240 | 2026-09-26T07:50:00Z | in_progress (non ancora finito oggi) |
| predictions_results_backfill.yml | 36230561535 | 2026-09-26T08:42:00Z | in_progress (non ancora finito oggi) |

## Tabella id → esito

| id | controllo | esito | evidenza |
|---|---|---|---|
| 7.9.4.B(a) | REFERTO BUCHI ricalcolato per 3 lega-stagioni campione = referto pubblicato | **PASS** | vedi tabella sotto, 19/19 coppie (tabella,stato) uguali |
| 7.9.4.B(b) | riserva dinamica (300/3000) coerente con lo stato VERO delle 3 action | **PASS** | vedi sezione riserva |
| 7.9.4.B(c) | contatore `/status` reale = contatore dichiarato nel log | **NON CERTIFICATO** | perimetro: nessuna chiamata API-Football ammessa per questo delegato (vedi motivo) |
| 7.4.1 | migrazione applicata (3 funzioni RPC) | PASS (di supporto) | `season_detail_gaps`/`season_gaps_summary` richiamabili senza `MigrazioneMancante` |
| 7.4.2 | RPC senza timeout (indice presente) | PASS (di supporto) | risposta in 0.35-0.96 s su lega 135/2026 |
| 7.4.3 | formato REFERTO BUCHI | PASS (di supporto) | intestazione + righe + riga finale "BUCHI APERTI: 1300 lega-stagioni, ~171410 chiamate, il piu' vecchio da 1 giorni" nel log, righe 911-3186 |
| 7.4.4 | BUCO VECCHIO con causa dichiarata | N/A | stringa assente nel log di questo run: non applicabile (nessun buco > `BACKFILL_BUCHI_MAX_GIORNI`), nessuna anomalia da segnalare |
| 7.4.5 | margine = limit_day - current - riserva | PASS | log: `contatore API 649/7500 (fonte /status), riserva action 3000, margine 3851`; 7500-649-3000=3851 esatto |
| 7.4.6 | nessuna lega-stagione "a meta'" (`completed` con `buchi_aperti>0`) | **PASS** | scan COMPLETO di 7260/7260 righe `status='completed'` in `season_backfill_state`: 0 con `buchi_aperti>0` |
| 7.4.7 | `retrain_models.yml` fra le action escluse (concorrenza) | **PASS** | log: "STOP prima di lega 78 stagione 2026: action concorrente in_progress: retrain_models.yml"; confermato da GitHub: run retrain 06:18:52Z→07:13:12Z, quindi IN CORSO al momento del controllo (06:23:45Z) |
| 7.4.8 | dry-run `league_orchestrator.py --dry-run` | NON CERTIFICATO | non eseguito: richiede "permesso dell'utente" per il lancio di un processo nuovo (piano §7.4.8), non ricevuto in questo brief |
| (extra) | mapper aggiorna i flag PRIMA del catchup | **PASS** | 35 righe di `api_coverage_by_season` con `updated_at` 06:19:49-50Z (dentro la finestra del run mapper 06:18:52-06:20:00Z), 20 s prima dell'avvio del catchup (06:20:02Z) |

## 7.9.4.B(a) — dettaglio ricalcolo indipendente (3 lega-stagioni campione)

Campioni scelti dal REFERTO BUCHI pubblicato: lega **78/2026** (buchi noti, riga con tutti gli
endpoint aperti), lega **39/2026** (per-partita "DB SENZA BUCHI": riga pubblicata `0 0 0 0 -`),
lega **10/2026** (parziale/misto). Ricalcolo con `season_gaps.py` (stessa logica della RPC, non
la RPC stessa, per una verifica davvero indipendente) sulle 5 tabelle di dettaglio via
`.select()` paginato (nessuna scrittura):

```
lega 78 stagione 2026: FT diretti=36 (RPC=36)
  match_events         da_chiamare      rpc=36   ricalcolo=36   OK
  match_lineups        da_chiamare      rpc=36   ricalcolo=36   OK
  match_player_stats   da_chiamare      rpc=36   ricalcolo=36   OK
  match_team_stats     da_chiamare      rpc=36   ricalcolo=36   OK
  match_odds           da_chiamare      rpc=8    ricalcolo=8    OK
  match_odds           non_disponibile  rpc=28   ricalcolo=28   OK

lega 39 stagione 2026: FT diretti=50 (RPC=50)
  match_odds           non_disponibile  rpc=40   ricalcolo=40   OK
  (nessun'altra riga: 0 da_chiamare/errore/da_richiamare/in_attesa su tutte le altre 4 tabelle
   -> "DB SENZA BUCHI" per-partita confermato, coerente con la riga pubblicata "0 0 0 0 -")

lega 10 stagione 2026: FT diretti=495 (RPC=495)
  match_events         da_chiamare=80  in_attesa=5    rpc=ricalcolo su entrambe OK
  match_lineups        da_chiamare=276 in_attesa=7    OK
  match_player_stats   da_chiamare=377 in_attesa=8    OK
  match_team_stats     da_chiamare=355 in_attesa=7    OK
  match_odds           da_chiamare=4   in_attesa=5   non_disponibile=197   OK
```

Uguaglianza numerica esatta su tutte le 19 coppie (tabella, stato) confrontate, sulle 3
lega-stagioni. Dettaglio macchina in `sonda_catchup_quota_output.json`.

**Nota di metodo (falsificazione della mia stessa sonda):** la prima stesura dello script usava
`select(...).limit(n_fixture)` per verificare la presenza dei fixture nelle tabelle di dettaglio.
Le tabelle di dettaglio hanno PIU' righe per fixture (eventi, formazioni...), quindi quel limite
tagliava la risposta a meta' e faceva apparire "mancanti" fixture che invece c'erano: sulla lega
39 il primo giro dava 198 lacune false (ricalcolo=198 contro rpc=0). Corretto impaginando con
`.range()` fino a pagina vuota; dopo la correzione tutte le 3 lega-stagioni tornano esatte. Lo
scrivo perche' e' esattamente il tipo di errore («falso positivo del verificatore») che lo
standard dell'utente chiede di scovare PRIMA di firmare un PASS: qui l'ho scovato e corretto io
stesso, non e' un difetto del codice di produzione.

## 7.9.4.B(b) — riserva dinamica

Al momento del run (avvio 06:20:02Z, quota letta 06:21:31Z), le action giornaliere avevano questi
orari-cron (letti da `.github/workflows/*.yml`, `ControlloConcorrenza.orario_cron`): Daily 01:12
UTC, Today Predictions 02:18 UTC, Results 03:23 UTC. Stato VERO su GitHub in quel momento (da `gh
run list`, tabella sopra): Daily aveva GIA' un run `success` creato alle 06:05:36Z (>= 01:12 UTC
di oggi: conta); Today Predictions e Results NON avevano ancora nessun run creato oggi (i loro
run di oggi sono partiti solo alle 07:50Z e alle 08:42Z, DOPO il catchup). Quindi
`action_completate_oggi()` alle 06:20 doveva restituire **False** (non tutte e 3 completate) →
riserva piena **3000**. Il log conferma esattamente questo: `riserva action 3000`.

Prova via codice di produzione (non solo lettura manuale dei timestamp): ho richiamato
`seasons_catchup.ControlloConcorrenza.action_completate_oggi()` (la stessa funzione usata dal
catchup, nessuna chiamata API-Football, solo GitHub) in tempo reale (09:15:44Z di oggi):
risultato **False**, coerente con lo stato reale osservato in quel momento
(`today_predictions_backfill.yml` e `predictions_results_backfill.yml` ENTRAMBI ancora
`in_progress`, partiti alle 07:50Z e 08:42Z e non ancora conclusi). Formula di 7.4.5 verificata:
`margine = 7500 - 649 - 3000 = 3851` = esattamente il valore del log.

**Avviso presente nel log (non un difetto, comportamento disegnato):** riga
`[QUOTA] controprova: api_call_log conta 749 > contatore 649` — il codice stesso segnala che il
conteggio locale (`api_call_log`, solo le chiamate di questo repo) supera di 100 il contatore
ufficiale `/status` (soglia di avviso: +50, `api_quota.py:284`). E' l'AVVISO previsto dal codice
quando la controprova diverge, non un errore: lo riporto perche' il coordinatore ha chiesto di
segnalare ogni divergenza osservata, ma non e' un FAIL (nessuna regola di quota e' stata
bypassata: il lavoro si e' fermato comunque per la concorrenza col retrain, non per la quota).

## 7.9.4.B(c) — NON CERTIFICATO (motivo)

Il piano chiede di chiamare `GET /status` di API-Football per confrontare il contatore dichiarato
(649) con quello reale. Il brief specifico di questo delegato vieta ESPLICITAMENTE qualunque
chiamata all'API-Football per non consumare quota. Non ho fatto la chiamata. Quello che HO
verificato, in sua vece: (a) la formula del margine e' aritmeticamente esatta sul numero
dichiarato (7.4.5, PASS); (b) il codice stesso ha una controprova interna (`api_call_log`) che ha
gia' confrontato il numero e ha emesso un avviso (sopra); non ho trovato modo, nel perimetro
consentito, di certificare il numero 649 contro la fonte ufficiale. Il coordinatore, se vuole
chiudere questo punto, deve autorizzare UNA chiamata `/status` (gratuita per documentazione
API-Football, ma resta una chiamata verso un servizio a pagamento che questo delegato non e'
autorizzato a contattare).

## Cosa NON ho potuto verificare

- **7.9.4.B(c)**: vedi sopra, per limite di perimetro (niente API-Football).
- **7.4.8** (dry-run `league_orchestrator.py --league 135 --season 2026 --dry-run`): il piano
  stesso lo marca "permesso dell'utente"; non l'ho lanciato perche' il mio brief non mi da questo
  permesso esplicito e lanciare un processo nuovo senza autorizzazione e' vietato dallo standard
  dei bot Betfair di questo repo.
- Non ho controllato TUTTE le 1300 lega-stagioni "aperte" del referto (solo 3 campioni, come
  richiesto dal piano): un ricalcolo massivo su tutte richiederebbe molto piu' tempo/IO sul DB
  condiviso con l'app accesa.
- Non ho verificato la stima "giorni al completamento" della sezione P4 (dipende da
  `margine_medio_log`, media mobile sugli ultimi 7 giorni di `api_call_log`): e' una stima
  dichiarata come tale nel referto stesso, non un numero da certificare esatto.

## Comandi/script esatti per riprodurre (sola lettura)

```
gh run list --workflow=seasons_catchup.yml --json status,conclusion,createdAt,updatedAt -L 5
gh run view 36223432528 --log
gh run list --workflow=daily_yesterday_backfill.yml --json status,conclusion,createdAt -L 5
gh run list --workflow=today_predictions_backfill.yml --json status,conclusion,createdAt -L 5
gh run list --workflow=predictions_results_backfill.yml --json status,conclusion,createdAt -L 5
gh run list --workflow=retrain_models.yml --json status,conclusion,createdAt,updatedAt -L 5
gh run list --workflow=leagues_mapper.yml --json status,conclusion,createdAt,updatedAt -L 3

.venv\Scripts\python.exe AUDIT_2026-09-25\e2e_fase2\sonda_catchup_quota.py
.venv\Scripts\python.exe AUDIT_2026-09-25\e2e_fase2\sonda_catchup_stato.py
.venv\Scripts\python.exe AUDIT_2026-09-25\e2e_fase2\sonda_catchup_stato2.py
.venv\Scripts\python.exe AUDIT_2026-09-25\e2e_fase2\sonda_catchup_mapper.py
# sonda_catchup_riserva.py ha bisogno di GITHUB_TOKEN/GITHUB_REPOSITORY nell'ambiente del
# PROCESSO (non nel file .env, mai toccato): esempio (PowerShell)
#   $env:GITHUB_TOKEN = (gh auth token); $env:GITHUB_REPOSITORY = "Dani91x/python-database-automation"
#   .venv\Scripts\python.exe AUDIT_2026-09-25\e2e_fase2\sonda_catchup_riserva.py
```

## Riepilogo per il coordinatore

7.9.4.B(a) e (b) **PASS** con verifica indipendente robusta (19 coppie tabella/stato su 3
lega-stagioni, riserva confermata sia a mano sui timestamp GitHub sia richiamando la funzione di
produzione in tempo reale). 7.9.4.B(c) **NON CERTIFICATO** solo per il divieto di chiamare
API-Football imposto a questo delegato — nessun difetto trovato, solo un punto che serve
l'autorizzazione del coordinatore per essere chiuso con una singola chiamata `/status`. Nessun
FAIL in questo perimetro. Trovato un avviso gia' previsto dal codice (api_call_log vs /status,
+100) che non altera nessuna decisione di quota. 7.4.8 non eseguito per mancanza di permesso
esplicito al lancio di un processo nuovo.
