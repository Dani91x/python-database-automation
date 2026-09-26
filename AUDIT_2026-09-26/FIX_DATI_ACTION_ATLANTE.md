# FIX cantiere DATI e ACTION (26/09/2026, delegato di correzione)

Brief: `brief_fix_comune.md` + cantiere «dati e action» (R-CATCHUP-1, O-1, O-4, R-FA-2, R-FA-3, O-3).
Evidenze: `CRONOSTORIA.md` 26/09 h12:05 e h16:50, `AUDIT_2026-09-25/e2e_fase2/ADMIN26_CATCHUP_QUOTA.md`,
`ADMIN26_FEED_ATLANTE.md`. Niente commit, niente `git add`, nessuna chiamata API-Football, nessuna scrittura sul DB,
nessun processo lanciato. Strategie non toccate (nessuna soglia, stake, veto o regola di Mike cambiata).

## File toccati (tutti)

Modificati:
- `.github/workflows/seasons_catchup.yml` (env nuova + `timeout-minutes` 180 -> 270; cron NON cambiati)
- `seasons_catchup.py` (funzione `attendi_action_concorrenti`, chiamata in `main`)
- `Betfair/stream/scalper/atlante_a_domanda.py` (O-1 priorita' della coda, O-3 una scrittura)
- `Betfair/stream/scalper/genera_atlante.py` (O-4 riferimento per lega)
- `Betfair/stream/scalper/atlante_v4.py` (O-4 `assembla_v4` accetta il dict per lega; meta nuova)
- `Betfair/mike/service.py` (R-FA-2 quattro chiavi nel frame)
- `Betfair/mike/dossier.py` (R-FA-3 lega/id squadra anche senza lambda)
- `Betfair/stream/db.py` (R-FA-3 produttore: con `con_squadre=True` restituisce lega/id anche senza lambda)
- `frontend/src/lib/mike.ts` (R-FA-2 le 4 chiavi dichiarate in `MikeLive`, solo tipi opzionali: lo esige il
  test di contratto `test_contratto_live_ogni_chiave_scritta_e_dichiarata_in_ui`)

Nuovi:
- `test_catchup_attesa_concorrenti_2026_09_26.py` (radice, accanto agli altri test del catchup)
- `Betfair/stream/tests/test_atlante_a_domanda_coda_scrittura_2026_09_26.py`
- `Betfair/stream/tests/test_atlante_v4_stagione_rif_per_lega_2026_09_26.py`
- `Betfair/mike/tests/test_mike_atlante_frame_dossier_2026_09_26.py`
- `AUDIT_2026-09-26/falsifica_fix_dati_action_atlante.py` (script di falsificazione riproducibile)
- `AUDIT_2026-09-26/FIX_DATI_ACTION_ATLANTE.md` (questo referto)

---

## 1. R-CATCHUP-1 — il catchup del mattino si fermava alla prima lega per il Retrain in corso

**Reperto.** Run 36223432528 (26/09 06:20Z): «STOP prima di lega 78 stagione 2026: action concorrente in_progress:
retrain_models.yml», 0 chiamate, 1299 lega-stagioni in coda. Il Retrain e' agganciato allo stesso Daily (06:18-07:13Z).

**Causa.** `seasons_catchup.py` `esegui_catchup` (ciclo di lavoro, `concorrenza.in_corso(forza=True)` prima di ogni
lega-stagione) si ferma subito se un'action esclusiva e' in corso; nessuna attesa prima di iniziare. `main` chiamava
`esegui_catchup` direttamente.

**Correzione (la piu' semplice e robusta: attendere, non un secondo aggancio).**
- `seasons_catchup.py:239-272` nuova funzione pura `attendi_action_concorrenti(concorrenza, attesa_max_min, stampa,
  dormi, orologio, passo_sec=120)`: interroga GitHub con la STESSA `ControlloConcorrenza.in_corso(forza=True)` (stessa
  lista esclusiva Daily/Today/Results/Retrain, stesse GET `.../actions/workflows/{wf}/runs?status=in_progress|queued`),
  ricontrolla ogni 2 min, al massimo `CATCHUP_ATTESA_CONCORRENTI_MAX_MINUTI` (default 90). Restituisce None (via libera)
  o il motivo ancora vero a fine attesa: in quel caso `esegui_catchup` si ferma come prima, dichiarato. Senza token
  (lancio locale) non aspetta (controllo spento come prima).
- `seasons_catchup.py:930-932` `main` la chiama PRIMA di `esegui_catchup` (quindi prima di ogni chiamata API e di
  `verifica_current_sospette`): durante l'attesa zero quota consumata.
- `.github/workflows/seasons_catchup.yml`: `CATCHUP_ATTESA_CONCORRENTI_MAX_MINUTI: '90'`; `timeout-minutes` 180 -> 270
  (90 di attesa + i 180 di prima). `CATCHUP_MAX_MINUTI` (150) si conta da quando il lavoro parte (t0 di
  `esegui_catchup`), invariato. Cron e trigger invariati.
- Scelta rispetto a `workflow_run` su retrain: un secondo aggancio avrebbe richiesto una guardia anti-doppio (stato
  sul DB o lettura delle run del catchup stesso) e poteva comunque partire mentre Today/Results girano; l'attesa usa
  il controllo gia' esistente e non aggiunge trigger. Quota: invariata la logica (riserva dinamica di `api_quota.py`
  letta DOPO l'attesa; a Retrain finito Today/Results di oggi di solito non sono ancora girati -> riserva piena 3000).

**Test** (`test_catchup_attesa_concorrenti_2026_09_26.py`, finto GitHub = `FintoGitHub` di
`test_riserva_dinamica_2026_09_25.py`, stessa URL/parametri/risposta `{"total_count", "workflow_runs"}`, con
`retrain_models.yml` e il suo nome vero «Retrain ML Models (cloud, all leagues)»):
- `test_aspetta_la_fine_del_retrain_e_poi_parte` (Retrain di 55 min: 28 attese da 120 s, poi via libera; ogni
  ricontrollo interroga davvero GitHub);
- `test_attesa_scaduta_restituisce_il_motivo_e_non_supera_il_tetto` (mai oltre 90 min);
- `test_nessuna_action_concorrente_nessuna_attesa`; `test_senza_token_nessuna_attesa`;
- `test_main_aspetta_prima_di_eseguire` (ordine attendi -> esegui, env letta = 90).

**Come verificarlo DOMANI dal log del run (senza consumare quota oggi).** Il workflow nuovo vale solo quando e' sul
branch di default (i `workflow_run` usano il file del default branch).
```
gh run list --workflow=seasons_catchup.yml --json databaseId,event,createdAt,updatedAt,conclusion -L 3
gh run list --workflow=retrain_models.yml --json createdAt,updatedAt,conclusion -L 2
gh run view <id del run workflow_run del mattino> --log | findstr /C:"[CATCHUP]"
```
Atteso: righe `[CATCHUP] ATTESA: action concorrente in_progress: retrain_models.yml (atteso N/90 min, ricontrollo fra
120 s)` fino alla fine del Retrain, poi `[CATCHUP] ATTESA FINITA dopo ~M min: nessuna action concorrente, si parte`
(M = updatedAt del Retrain - createdAt del catchup), poi `[CATCHUP] quota all'avvio: ...` e righe
`[CATCHUP] P1 lega ... -> ...` con chiamate > 0. Se Today Predictions parte durante il lavoro, lo STOP «action
concorrente in_progress: today_predictions_backfill.yml» e' il comportamento voluto (Today ha la precedenza). Se
compare `ATTESA SCADUTA dopo 90/90 min` il Retrain e' durato > 90 min: il catchup si ferma come prima (dichiarato).

---

## 2. O-1 — la coda dell'atlante a domanda non metteva in testa le leghe in gioco

**Reperto.** Alle 14:39Z solo 42 leghe in gioco su 157 avevano il v4; alle 09:06 le leghe in gioco erano in media
alla posizione 109 di 304.

**Causa.** `atlante_a_domanda.py` (ex riga 436) `nuove.sort(key=lambda l: primo_ko.get(l, adesso))`: il PRIMO calcio
d'inizio nella finestra, che parte da 36 h indietro -> una lega che ha giocato ieri sera passa davanti a quella in
gioco ora; il commento «in-play in testa» era falso.

**Correzione.** `atlante_a_domanda.py:107-118` `fascia_priorita(ko, adesso, fine_s)`: 0 = in gioco adesso (ko <=
adesso < ko + `fine_partita_min`, il 150' gia' usato dall'incrementale per dire «finita»), 1 = inizia entro 2 h
(`PROSSIME_H`), 2 = il resto. `:436-448` la fascia di una lega e' la migliore fra le sue partite; `:455` ordinamento
`(fascia, primo_ko)`. Tetti (10 per ciclo, 40 l'ora) invariati. Dentro la fascia 2 l'ordine resta quello di prima.

**Test** (`test_atlante_a_domanda_coda_scrittura_2026_09_26.py`, finti di `test_atlante_a_domanda_2026_09_25.py`):
`test_fascia_priorita`, `test_coda_in_gioco_poi_prossime_2h_poi_il_resto` (lega di ieri, fra 10 h, fra 1 h, ieri+in
gioco, in gioco: con tetto 1 si prepara quella in gioco, poi la coda dichiarata e' in gioco -> fra 1 h -> resto).

## 3. O-3 — il file live dell'atlante scritto 2 volte per ciclo con lo stesso `generated_at`

**Causa.** `atlante_a_domanda.py` (ex righe 440-444) scriveva il live «in preparazione» PRIMA del lavoro e di nuovo
a fine ciclo (ex :490-492) con lo stesso `adesso`.

**Correzione.** `atlante_a_domanda.py:458-462` tolta la scrittura anticipata; `:508-509` la scrittura di fine ciclo
parte anche quando cambia solo l'elenco `leghe_in_preparazione` (prima lo garantiva la scrittura anticipata: cosi'
una lega il cui calcolo fallisce resta dichiarata «in preparazione»). Effetto noto: durante i 2-3 min del ciclo i bot
vedono il file del ciclo precedente (che gia' elencava come «in preparazione» le leghe rimaste fuori dal tetto).

**Test**: `test_una_sola_scrittura_del_live_per_ciclo` (1 scrittura, era 2; ciclo senza novita' 0 scritture),
`test_leghe_in_preparazione_dichiarate_anche_se_il_calcolo_fallisce`.

## 4. O-4 — `stagione_rif` unica (2028) per tutto l'atlante

**Causa.** `genera_atlante.py` (ex :562) `rif = max(stagioni di TUTTE le leghe) + 1`: 3 leghe (36, 850, 637) con una
stagione 2027 -> 2028 per tutte.

**Correzione.** `genera_atlante.py:562-566` riferimento PER LEGA: `max(stagioni della lega) + 1` (stessa regola S+1 del
banco, applicata a ogni calendario). `atlante_v4.py:389-399,411` `assembla_v4` accetta un intero (come prima: banco e
test esistenti invariati) o un dict `{lega: stagione}`; `:436-441` meta: `stagione_rif` = la piu' recente (compatibilita'
con chi la legge) e nuova `stagione_rif_per_lega`. Emivita (3), BETA, ETA, k_celle NON toccati.

**Test** (`test_atlante_v4_stagione_rif_per_lega_2026_09_26.py`, blocchi stagione con la forma vera di
`atlante_v4._blocco_stagione`): `test_riferimento_per_lega_con_calendari_diversi` (lega 501 2023-25 -> 2026, lega 36
2025-27 -> 2028; `n` della cella = somma dei pesi calcolata a mano: 192,4 e non 121,2), `test_una_lega_non_sposta_i_pesi_di_un_altra`,
`test_intero_come_prima`.

**Impatto atteso e rigenerazione.** Dentro una lega i pesi RELATIVI fra stagioni non cambiano (lo spostamento del
riferimento li moltiplica tutti per la stessa costante); cambia il peso ASSOLUTO: per una lega con ultima stagione
2025 x 1,587 (0,5^-(2/3)), 2026 x 1,26, 2027 invariato. Quindi: meno shrinkage verso il globale (k_celle fisso), e il
globale v4 ripesato fra leghe di calendari diversi. I numeri p2/p3/r_rec2/gol_medi del v4 si muovono di poco; le
leghe europee pesano di piu' nel globale di quanto pesavano. E' un cambio di NUMERI del modello (non di regole):
da portare all'utente. Il ricalcolo indipendente 7.9.3.B va rifatto con `stagione_rif_per_lega`.
Il file live NON va rigenerato a mano: `atlante_a_domanda` ricostruisce il blocco v4 da `G.assembla` a ogni scrittura
(prima scrittura dopo il riavvio dell'app con qualche novita', al massimo 12 h). Verifica: in
`Betfair/omega/data/hazard_atlas_live.json` deve comparire `v4.meta.stagione_rif_per_lega`. Anche l'action
`.github/workflows/hazard_atlas.yml` (usa `genera_atlante`) produrra' il nuovo riferimento alla prossima esecuzione.

## 5. R-FA-2 — chiavi v4 dell'atlante assenti dal frame live di Mike (0/166)

**Causa.** `dossier.live_frame` (`dossier.py:343-350`) le calcola; il frame `ev["live"]` di `service._run_event`
(`service.py` ~3795-3830) copiava solo `hazard`, `hazard_atlas`, `hazard_model`.

**Correzione.** `service.py:3816-3821` copiate `hazard_versione`, `hazard_fase`, `hazard_recupero_atteso_min`,
`hazard_nota` da `live`. Il frame e' la riga `mike_events.live` (stessa riga pubblicata sul canale), quindi arrivano a
DB e canale senza altre modifiche. `hazard_recupero_atteso_min` e `hazard_nota` erano gia' fra i volatili
(`_LIVE_VOLATILI`), versione e fase no (fatti da scrivere, pochi cambi a partita): write-on-change coerente con quanto
dichiarato il 25/09. Nessun effetto sulla decisione (non letti da engine). `frontend/src/lib/mike.ts:219-223` le 4
chiavi opzionali in `MikeLive` (il test di contratto UI altrimenti e' rosso).

**Test** (`test_mike_atlante_frame_dossier_2026_09_26.py`, `run_once` vero con il finto db di
`test_mike_respiro_scritture_2026_09_13.py`): `test_il_frame_live_porta_le_chiavi_v4_del_dossier` (live_frame vero +
le 4 chiavi coi tipi veri), `test_senza_atlante_le_chiavi_ci_sono_e_valgono_none`.

## 6. R-FA-3 — dossier di Mike senza lega e id squadra quando mancano i lambda

**Causa.** `dossier.py:81-94` valorizzava lega/id solo dentro `if lam:` e il produttore
`stream/db.get_fixture_prematch_lambdas` restituiva None se i lambda mancavano, anche con la riga presente.

**Correzione.** `Betfair/stream/db.py:265-269`: con `con_squadre=True` (usato SOLO da `mike.db.fixture_lambdas`) e riga
trovata senza lambda -> `(None, None, league_id, home_team_id, away_team_id)`; il default (tupla di 3 / None, usato da
Omega e runner) e' invariato. `dossier.py:81-95`: lambda e `source="fixture"` solo se ci sono; lega e id squadra sempre
quando la tupla c'e'. Stessa richiesta al DB, nessuna lettura in piu'.

**Test**: `test_produttore_senza_lambda_da_lega_e_squadre_solo_con_squadre` (supabase finto sulla catena vera, riga
della fixture 1573593: lega 142, squadre 19896/22018), `test_dossier_senza_lambda_ha_lega_e_id_squadra`,
`test_dossier_con_lambda_invariato`.

**ATTENZIONE (da portare all'utente, effetto sugli INPUT della decisione).** Con la lega nota, per le partite senza
lambda Mike consulta l'atlante sulla LEGA (e con la forza, se la lega ha i rating) invece che sul globale, e passa la
lega anche a `p_total_empirical`, `lambdas_from_live_ou` e (se i lambda arrivano dai ripieghi) a `event_goal_hazard`.
Le REGOLE di Mike (combine_hazard, soglie del timing, veti) non cambiano, ma i numeri che le alimentano si, come voluto
dal reperto. Se `fixture_id` stesso non si risolve (evento assente da `live_follow` e `omega_events`), la correzione non
ha effetto: il dossier resta vuoto come prima.

---

## Esiti dei test (miei)

- Nuovi: 17 test, verdi.
- Esistenti dei moduli toccati: `Betfair/mike/tests/` intera (con i nuovi), `test_atlante_v4_forza_id_squadra`,
  `test_o1_quote_prima`, `test_safe_lambda_quote_prima`, `test_atlante_a_domanda`, `test_atlante_note_livello`,
  `test_validazione_hazard`: 1004 verdi + 1 rosso (contratto UI di Mike, corretto con `mike.ts`, poi 40/40 verdi);
  `test_atlante_v4_2026_09_25`, `test_atlante_v4_collegato`, `test_genera_atlante_2026_09_24`: 77 verdi; catchup
  (`test_riserva_dinamica`, `test_catchup_p4`, `test_backfill_automatico`, `test_daily_niente_aggregati`): verdi.
  Rilancio finale a file ripristinati: 170 verdi.

Comandi (dalla radice; PowerShell: impostare prima `$env:SUPABASE_URL="http://127.0.0.1:9"; $env:SUPABASE_SERVICE_ROLE_KEY="x"; $env:SUPABASE_KEY="x"`):
```
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider test_catchup_attesa_concorrenti_2026_09_26.py test_riserva_dinamica_2026_09_25.py test_catchup_p4_2026_09_25.py test_backfill_automatico_2026_09_25.py test_daily_niente_aggregati_2026_09_25.py
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider Betfair/stream/tests/test_atlante_a_domanda_coda_scrittura_2026_09_26.py Betfair/stream/tests/test_atlante_a_domanda_2026_09_25.py Betfair/stream/tests/test_atlante_v4_stagione_rif_per_lega_2026_09_26.py Betfair/stream/tests/test_atlante_v4_2026_09_25.py Betfair/stream/tests/test_atlante_v4_collegato_2026_09_25.py Betfair/stream/tests/test_atlante_v4_forza_id_squadra_2026_09_25.py Betfair/stream/tests/test_genera_atlante_2026_09_24.py
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider Betfair/mike/tests/
```
(le suite v4 impiegano ~95 s per il banco sintetico).

## Falsificazione

`AUDIT_2026-09-26/falsifica_fix_dati_action_atlante.py` (12 mutazioni, ripristino byte per byte nel `finally`,
sha1 dei 7 file verificati identici dopo il lancio). Tutte ROSSE:

| mutazione | test rossi |
|---|---|
| M1a `main` non chiama l'attesa | test_main_aspetta_prima_di_eseguire |
| M1b attesa che non aspetta | test_aspetta_la_fine_del_retrain..., test_attesa_scaduta... |
| M2 coda per primo ko (bug O-1 originale) | test_coda_in_gioco_poi_prossime_2h_poi_il_resto |
| M2b fascia senza in-play | test_fascia_priorita, test_coda_... |
| M3 doppia scrittura (bug O-3 originale) | test_una_sola_scrittura_del_live_per_ciclo |
| M3b niente scrittura se cambia solo in_preparazione | test_leghe_in_preparazione_dichiarate_anche_se_il_calcolo_fallisce |
| M4 riferimento globale (bug O-4 originale) | test_riferimento_per_lega..., test_una_lega_non_sposta... |
| M4b assembla ignora il dict | idem |
| M5 frame senza versione/fase (bug R-FA-2) | test_il_frame_live_porta..., test_senza_atlante_le_chiavi... |
| M5b frame senza nota | idem |
| M6 dossier: lega solo coi lambda (bug R-FA-3) | test_dossier_senza_lambda_ha_lega_e_id_squadra |
| M6b produttore None senza lambda | test_produttore_senza_lambda..., test_dossier_senza_lambda... |

Lancio: `.venv\Scripts\python.exe AUDIT_2026-09-26\falsifica_fix_dati_action_atlante.py` (exit 0 = tutte rosse).
Nota: le mutazioni su `dossier.py`/`db.py` cercano `\r\n` (file con terminatori CRLF nel worktree).

## Cosa NON ho potuto verificare

- R-CATCHUP-1 sul vero GitHub: si vedra' solo al primo run del mattino dopo il push (comandi sopra). Durata reale
  del Retrain nei prossimi giorni (se > 90 min l'attesa scade e il comportamento resta quello di prima, dichiarato).
- `tsc`/`vitest` del frontend: il worktree non ha `frontend/node_modules` (niente junction creata); la modifica e'
  di soli tipi opzionali in un'interfaccia. Da lanciare dal coordinatore: `npx tsc -p tsconfig.app.json --noEmit`.
  Nessun `npm run build` necessario per la sola interfaccia (nessun componente la legge ancora).
- Impatto numerico reale di O-4 sull'atlante live (serve il file/DB veri: non letti per non toccare il DB).
- R-FA-3 sul DB vero (partite Liga F del 26/09): verificabile al prossimo paper di Mike leggendo
  `mike_events.dossier.league_id` e `live.hazard_nota` (livello lega invece di globale).

## Rischi residui

- O-4 cambia i numeri del v4 (vedi impatto): consumatori Omega/Safe/Mike/scalper vedranno hazard leggermente
  diversi. Divergenza di modello da portare all'utente, non una regola di strategia.
- R-FA-3 cambia gli input di Mike sulle partite senza lambda (lega/forza invece del globale): voluto dal reperto,
  da portare all'utente prima del paper.
- O-3: durante il ciclo (2-3 min) la lega appena scelta non e' dichiarata «in preparazione» se non lo era gia' nel
  file precedente (primo ciclo dopo l'avvio o lega appena comparsa).
- R-CATCHUP-1: il lavoro del mattino dura da fine Retrain (~07:13Z) all'avvio di Today (~07:50Z oggi): la finestra
  resta corta finche' i cron partono con ~5 h di ritardo; il cron 13:47 resta la seconda finestra.
- Nel frame di Mike restano fuori `hazard_livello`, `hazard_n`, `hazard_confidenza` (non richieste dal reperto;
  `hazard_n` e' gia' nei volatili ma non viene mai scritta): da decidere se aggiungerle.
