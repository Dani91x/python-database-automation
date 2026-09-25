# Catchup P4 (stagioni mai caricate) + riserva dinamica + verifica dei `current` (25/09/2026)

Delegato del coordinatore, worktree `agent-aad822618157b6628`, base `2f04bc4` (contiene `000d8f6`, `f015204`,
`9cbfe76`, `306fd11`). Niente commit, niente push, **nessuna scrittura sul DB vero**. Chiamate esterne: vedi par. 9
(una violazione mia, dichiarata).

Ordini dell'utente coperti:
1. (25/09) "Il backfill deve occuparsi di tenere PERFETTO il DB: ... il 40 % di crediti API da utilizzare, potrebbe
   popolare qualche lega" -> coda **P4** delle stagioni mai caricate.
2. (seguito, coordinatore) usare il 40 % inutilizzato = la riserva delle action -> **riserva dinamica**.
3. (decisione utente) "dopo che tutte le action hanno fatto il loro lavoro possiamo utilizzare le chiamate rimanenti,
   ovviamente non dobbiamo eccedere e NON DOBBIAMO LASCIARE LEGHE A META'" -> P4 **solo per intero** (spezzoni tolti).
4. (decisione utente) "dobbiamo fidarci dell'API: in caso effettua una chiamata di test" -> niente euristica dei 30
   giorni sul flag `current`: **verifica mirata** `/leagues?id=&season=` al massimo 1 volta a settimana per stagione.
5. `CATCHUP_MAX_VERIFICHE_PASSATE` 150 -> 400; M56 riallineata; M19 tolta per sempre.

---

## 0. In breve

- **Numero reale (DB vero, sola lettura, codice di produzione)**: le stagioni passate a 0 partite sono quasi zero.
  Oggi la P4 trova **1** stagione (111/2023, ~518 chiamate), che in realta' ha 400 partite (stato vecchio): la P4 la
  riconosce a **0 chiamate** e la passa alla P3. Le 2 stagioni a 0 partite secondo lo stato (880/2021, 888/2022)
  sono `current=True` nel DB: entrano in P4 solo se la verifica all'API le dice chiuse (ordine 4).
- Il "40 %" e' la riserva di 3.000 delle action che a fine giornata avanza: ora, quando Daily + Today + Results del
  giorno UTC hanno finito con successo (stato letto da GitHub), la riserva scende a **300**: il catchup delle 13:47
  UTC (reale ~19:00) lavora con quel margine P1-P3-P4. Dalle **23 UTC** nessun lavoro nuovo (reset a 00:00).
- Il lavoro vero che il margine andra' a fare e' la **P3**: 5.793 stagioni passate con stato v1 mai verificate dai
  dati; ora se ne verificano 400 per run (~2 run/giorno) invece di 150.

---

## 1. Cosa fa ora -> cosa fa dopo (file:riga, versione nuova)

### 1.1 P4 - stagioni mai caricate (`seasons_catchup.py`)

| Prima (`2f04bc4`) | Dopo |
|---|---|
| `seleziona_candidati`: le passate a 0 partite (v2, `ft_count` 0) contate e lasciate "all'orchestratore a mano" | stagione con `stats_json.fixtures.matches_count == 0` (v1 o v2) contata e mandata alla P4, non rimessa nella rotazione di verifica; una passata verificata stanotte con 0 partite non e' piu' una voce P3 ne' un buco del referto (va in P4) |
| - | `:309` `passata_per_p4` = NON viva per `e_corrente_o_recente` (si fida del `current` dell'API, niente euristica sulle date); `seleziona_p4` (criteri e ordine, par. 2; stima con le partite reali della lega `:412`); `:448` `decidi_p4` **solo per intero**; `_segna_tentativo_p4` (memoria di `/fixtures` senza partite); `:652` `esegui_p4` dopo P1-P3 |
| referto: "passate con 0 partite in DB (solo orchestratore a mano)" | `:751` `referto_p4`: sezione **STAGIONI MAI CARICATE** prima dell'ultima riga, che resta `DB SENZA BUCHI` / `BUCHI APERTI` |
| `league_orchestrator.py` dry-run: "mai car." | `:70-82` + riga della stagione: `MAI CARICATA ~N chiamate (recupero automatico: coda P4): procederei` / `(fuori dal recupero automatico: API senza eventi, ...)` / `(stagione viva o finita da meno di 30 gg: non ancora in coda P4)` |

### 1.2 Riserva dinamica (`api_quota.py`, `seasons_catchup.py`)

| Prima | Dopo |
|---|---|
| riserva fissa 3.000 tutto il giorno | `api_quota.py:87` `leggi_riserva_residua` (`API_FOOTBALL_RISERVA_RESIDUA`, default 300, mai sopra la piena); `GestoreQuota(action_completate=...)`; `:233` `riserva_del_momento`: True -> 300, False -> 3000, None (non leggibile) -> 3000 **con avviso**; ricalcolata a ogni `aggiorna` (cioe' dopo ogni lega-stagione), nota stampata solo quando cambia (`:255`); `:310` capacita' giornaliera con la riserva del momento; `:229` `riserva_minima` per la stima dei giorni |
| `ControlloConcorrenza`: solo "in corso / in coda" | `seasons_catchup.py:167` `orario_cron` (cron letto dal file del workflow: 01:12, 02:18, 03:23 UTC); `:178` `action_completate_oggi` (criterio sotto); `:898` `main` collega il gestore quota al controllo |
| lancio senza `GITHUB_TOKEN` | controllo spento come prima -> `action_completate` None -> riserva 3000 con avviso `stato delle action del giorno non leggibile (...): riserva piena 3000` |
| nessun limite orario | `:79` `_adesso_utc`, `:527` `fine_giornata`: dalle `CATCHUP_ORA_STOP_UTC` (23) niente lega-stagioni nuove (P1-P3 e P4) e stop a fine partita dentro una lega-stagione (controllo ogni 25 partite, come la concorrenza) |

**Criterio "action completate" (scelto il piu' semplice e sicuro)**: per OGNUNA delle 3 action, sul giorno UTC
corrente: (a) nessuna run `in_progress`/`queued`; (b) almeno una run `success` creata DOPO l'orario del suo cron di
oggi (`created=>=YYYY-MM-DDTHH:MM:SSZ`). Motivi: lo stato vero da GitHub e' certo, un "orario massimo osservato +
margine" sbaglierebbe nei giorni lenti (ritardo cron ~5 h, variabile); "dopo il cron di oggi" esclude la run di IERI
partita in ritardo dopo la mezzanotte (altrimenti la riserva scenderebbe prima che l'action di oggi abbia girato);
solo `success` perche' un'action fallita di solito si rilancia a mano lo stesso giorno e deve trovare la quota. Una
volta vero resta vero fino a fine giorno UTC (nessuna richiesta a GitHub in piu'); falso si rilegge al massimo ogni 2
minuti. Errore di GitHub -> None -> riserva piena.

**Perche' le 23 UTC**: il contatore API si azzera alle 00:00 UTC (assunto, coerente con `api_call_log`); con riserva
300 un lavoro a cavallo del reset mangerebbe la quota del giorno dopo prima del Daily. Il catchup delle 13:47 (reale
~19:00) con tetto 150 minuti finisce ~21:30: le 23 sono una rete, non il caso normale.

### 1.3 Verifica dei `current` sospetti (decisione utente, `seasons_catchup.py`)

| Prima | Dopo |
|---|---|
| (P4 del primo giro) euristica: finita da > 30 gg per data = passata anche se `current` | tolta: `passata_per_p4` segue `current` |
| stagione `current=True` con fine passata da anni: "viva" per sempre, verificata ogni notte, mai caricata se a 0 partite | `:317` `current_sospetta` (current True e fine < oggi - 30 gg: **575** sul DB vero); `:350` `verifica_current_sospette` prima della selezione (`:546`): 1 chiamata `/leagues?id=<lega>&season=<anno>` per stagione, **contata nella quota** (margine >= 1, poi `quota.aggiorna()`), al massimo `CATCHUP_MAX_VERIFICHE_CURRENT` (100) per run; esito in `stats_json.verifica_current {at, current}` (`:336`, lettura dello stats_json completo di quella riga + update, niente scritture se la riga non esiste); per 7 giorni si usa la nota senza richiamare; la riga di coverage in memoria prende il `current` dell'API e da li' P1-P3/P4 la trattano come dice l'API; errore/stagione assente -> resta come nel DB e si ritenta al giro dopo; log dichiarato per ogni verifica e riga di riepilogo |

Nota: il mapper aggiorna gia' `current` dalla `/leagues` completa ogni giorno (da `f015204`, non ancora girato su
master con quella logica quando ho letto il DB). Se le 575 restano `current`, e' l'API a dirlo: la verifica mirata lo
conferma e la stagione resta viva (1 chiamata a settimana ciascuna, ~82/giorno a regime, ~575 nei primi 3 giorni
con il tetto 100 per run).

### 1.4 Altro

- `season_backfill.py:176-179` (bug trovato, valeva anche per la P3): la chiamata `/fixtures` entrava nel margine
  solo a fine stagione -> i controlli per partita vedevano 1 chiamata in meno. Ora contata subito.
- `season_backfill.py` `stima_*_mai_caricata(..., partite=380)`: la coda P4 usa le partite della stagione piu' grande
  della stessa lega gia' in DB (min 380), per non sottostimare leghe da 552 partite.
- `season_gaps.py`: lettura leggera degli stati con `matches_count`, `mai_caricata`, `verifica_current`;
  `costruisci_stats_json` conserva `mai_caricata` e `verifica_current` a ogni riscrittura.
- `test_backfill_automatico_2026_09_25.py`: SOLO una riga nella fixture `mondo` (`sc._adesso_utc` fissata alle 10:00
  UTC), perche' i test esistenti non diventino rossi se lanciati dopo le 23 UTC. Nessuna aspettativa cambiata.
- `.github/workflows/seasons_catchup.yml`: SOLO variabili env del job: `API_FOOTBALL_RISERVA_RESIDUA '300'`,
  `CATCHUP_ORA_STOP_UTC '23'`, `CATCHUP_MAX_VERIFICHE_PASSATE '400'` (era 150), `CATCHUP_P4_MARGINE_MINIMO '500'`,
  `CATCHUP_P4_ANCHE_SENZA_EVENTI '0'`, `CATCHUP_MAX_VERIFICHE_CURRENT '100'`. `permissions: actions: read` e
  `GITHUB_TOKEN` c'erano gia'. YAML riletto con `yaml.safe_load`.

## 2. P4: criteri di ingresso e ordine (`seleziona_p4`)

Entra una (lega, stagione) con: almeno un flag per-partita True (la coverage non ha un flag "fixtures" base); iniziata;
**non viva** secondo l'API (`current` False, verificato se sospetto) e finita da oltre 30 giorni; **0 partite in
`matches`** (conteggio della verifica di stanotte se c'e', altrimenti `stats_json.fixtures.matches_count`: sul DB vero
2.651/2.692 uguali al conteggio vivo, 0 casi "stato > 0 e DB 0", 1 caso "stato 0 e DB 400" gestito a 0 chiamate);
`fixtures_events` True salvo `CATCHUP_P4_ANCHE_SENZA_EVENTI=1`; non dichiarata "API senza partite" (2 risposte
`/fixtures` senza partite a 7 giorni di distanza). Ordine: leghe dei bot (fonte P1: atlante v3), leghe con modelli ML
(`training_planner._load_eligible_leagues`), altre; poi importanza (stagioni della lega con eventi); poi stagione piu'
recente.

## 3. P4: regola di budget (SOLO PER INTERO)

```
P4 parte solo se P1-P3 sono finite senza fermarsi (quota / tempo / action concorrente / fine giornata)
margine_P4 = limit_day - current - riserva (dinamica: 3000 o 300) - pavimento (CATCHUP_P4_MARGINE_MINIMO 500)
costo      = max(stima del piano, 1 /fixtures + partite stimate x endpoint attivi + aggregati)
             partite stimate = max(380, stagione piu' grande della stessa lega gia' in DB)
margine reale < pavimento   -> stop P4
margine_P4 >= costo         -> procedo (intera)
altrimenti                  -> non_entra: NESSUNA chiamata; si prova la successiva della coda (se entra intera)
dentro: stop a fine partita se il margine scenderebbe sotto il pavimento (QuotaConPavimento)
```

Unico caso residuo di stagione "a meta'": l'API ha piu' partite della stima. Il lavoro si ferma a fine partita sopra
il pavimento (mai oltre la quota); dal giorno dopo la stagione ha partite, e' una P3 con precedenza su ogni P4 e si
chiude senza doppioni (`/fixtures` = upsert su `fixture_id`; lacune dai dati: nessuna partita gia' fatta si
richiama). Test `test_p4_stima_superata_...`. Rischio di "fame": una stagione grande che non entra mai per intero
mentre le piu' piccole passano; con margine serale ~3.000+ e stagioni da ~1.500 e' improbabile, ed e' visibile nel
referto ("N stagioni non entrano PER INTERO").

## 4. Referto e dry-run

Sezione del REFERTO BUCHI (codice di produzione sui finti del test `test_referto_p4_quante_restano_e_stima_giorni`):
```
--------------------------------------------------------------------------------------------------------------
STAGIONI MAI CARICATE (0 partite in DB; P4 dopo P1-P3, solo PER INTERO con il margine sopra il pavimento 500)
  in coda P4: 2 (leghe bot 0, leghe ML 1, altre 1), ~3042 chiamate stimate
  caricate oggi: 1 per intero, 0 interrotte (partite oltre la stima: il resto lo chiude la P3 dal prossimo giro); chiamate P4 oggi: 9
  restano: 1 stagioni, ~1521 chiamate
  escluse: 1 senza fixtures_events (...), 0 API senza partite (/fixtures vuota 2 volte), 0 in attesa di ritentativo (...)
  P4 ferma: 1 stagioni non entrano PER INTERO nel margine di oggi (margine ... - pavimento 500): nessuna lasciata a meta'
  stima giorni al completamento: ~4 giorni (margine medio ultimi 7 gg da api_call_log 1000 - pavimento 500 = 500 chiamate/giorno per la P4)
  prossime: lega 777 stagione 2023 ~1521
DB SENZA BUCHI
```
Stima dei giorni = ceil(costo restante / (margine medio - pavimento)), margine medio = media su 7 giorni UTC completi di
max(0, limit_day - riserva minima - chiamate del giorno in `api_call_log`) (riserva minima = 300 con la riserva
dinamica attiva). Log illeggibile -> "non disponibile", la run non fallisce. Log catchup: riga
`[CATCHUP] stagioni 'current' con fine passata da > 30 gg: N (verificate ora K chiamate /leagues, ...)` e una riga per
ogni verifica; `[QUOTA] action del giorno UTC completate: riserva 3000 -> 300` quando cambia.

## 5. Numeri sul DB vero (25/09, sola lettura, codice di produzione)

`AUDIT_2026-09-25/sonde/p4_conta_stagioni_mai_caricate.py` (usa `seleziona_p4`, `current_sospetta` e le fonti vere
di atlante e ML), esito in `AUDIT_2026-09-25/sonde/p4_conta_esito_2026-09-25.txt`:

| Voce | Numero |
|---|---|
| coppie in coverage / stati | 8.742 / 8.662 |
| stati con `matches_count` > 0 | 8.659 (a 0: 111/2023, 880/2021, 888/2022) |
| **candidate P4 oggi** | **1** (111/2023, ~518): ha 400 partite nel conteggio vivo -> 0 chiamate, passa alla P3 |
| `current` con fine passata da > 30 gg (da verificare) | **575**; di cui a 0 partite secondo lo stato: 880/2021 (~766), 888/2022 (~386) -> P4 solo se l'API le chiude |
| passate con stato v1 mai verificate dai dati (lavoro P3) | **5.793** -> con 400 per run ~8 run (~4 giorni) invece di ~39 notti |
| margine medio ultimi 7 gg (riserva 3000, `consumo_giorni_log` sul DB vero) | 3.436 (giorni: 3618, 4129, 2639, 3713, 4038, 1780, 4136) |
| consumo action ultimi 7 gg | 364-2.720/giorno, media ~1.064: con riserva residua 300 il margine serale sale di ~2.700 |
| giorni al completamento P4 | 0-1 (se l'API chiude 880/2021 e 888/2022: ~1.152 chiamate, 1 giorno) |

Il margine medio e' misurato prima che il catchup esistesse: da domani P1-P3 ne useranno una parte.

## 6. Costo di `CATCHUP_MAX_VERIFICHE_PASSATE = 400` (IO del DB, non quota API)

Per run (2 run/giorno: dopo il mapper e cron 13:47): +250 stagioni verificate -> +13 RPC `season_gaps_summary`
(blocchi da 20: per partita FT una sonda EXISTS su indice `fixture_id` per 5 tabelle: ~250 x ~300 FT x 5 = ~375.000
sonde di indice in piu', ordine di grandezza), +2 RPC `season_aggregates_summary` (blocchi da 150), +250 righe di stato
in upsert (blocchi da 200). Nessuna chiamata API in piu' (le chiamate arrivano solo se si trovano buchi, e allora
sono lavoro utile nella quota). Non misurato sul DB vero (nessuna esecuzione consentita). Se ricompaiono 57014,
riabbassare la variabile.

## 7. Test e falsificazione

Sandbox env, `timeout 600`: `pytest test_catchup_p4_2026_09_25.py test_riserva_dinamica_2026_09_25.py
test_backfill_automatico_2026_09_25.py test_actions_fail_rumoroso_2026_09_25.py test_daily_niente_aggregati_2026_09_25.py
test_delete_ritentativi_2026_09_25.py test_orchestratore_niente_refresh_mv_2026_09_25.py` -> **121 passed**
(81 esistenti con aspettative invariate + 25 P4/verifica current + 15 riserva dinamica). `pyflakes` pulito, tutto ASCII.

Finti: client supabase-py e API-Football come nei test esistenti; `/leagues?id=&season=` con la struttura reale
(`league/country/seasons[year,start,end,current,coverage]`) ed errore con `errors`; **finto GitHub** con i parametri
veri (`status` = in_progress|queued|success|completed, `created=>=...Z`, `per_page`) e la risposta vera
`{total_count, workflow_runs[{id,name,path,status,conclusion,event,created_at}]}`; `api_call_log` con `id, endpoint,
created_at`.

`python AUDIT_2026-09-25/mutazioni_catchup_p4.py` -> **51/51 ROSSE** (una, V5, era verde al primo giro: il test non
controllava la nota salvata sulle stagioni confermate `current`; test rafforzato, ora rossa), ripristino sha256:

| Requisito | Test | Mutazioni |
|---|---|---|
| P4 solo dopo P1-P3 | `test_p4_parte_dopo_p1_p3_...`, `test_p4_non_parte_se_p1_p3_si_sono_fermate` | Q1, Q2 |
| pavimento | `test_p4_non_parte_sotto_il_pavimento_...`, `test_p4_pavimento_da_env`, `test_quota_con_pavimento`, `test_p4_stima_superata_...` | Q3, Q4, Q5, Q29 |
| **solo per intero** | `test_p4_solo_per_intero_se_non_entra_nessuna_chiamata`, `test_p4_col_pavimento_di_default_...`, `test_p4_salta_quella_che_non_entra_e_carica_intera_la_successiva` | Q12, Q12b |
| stima superata: fine partita, P3 senza doppioni | `test_p4_stima_superata_si_ferma_sopra_il_pavimento_e_la_p3_chiude_senza_doppioni` | Q3, Q13 |
| stima con partite reali | `test_p4_stima_con_le_partite_reali_della_lega` | V8 |
| ordine | `test_p4_ordine_...` | Q6-Q9 |
| criteri, stato vecchio | `test_p4_criteri_di_ingresso`, `test_p4_stato_vecchio_a_zero_...` | Q20, V6 |
| senza eventi | `test_p4_stagione_senza_eventi_...` | Q10, Q11, Q18 |
| `/fixtures` senza partite | `test_p4_fixtures_senza_partite_...` | Q14-Q17 |
| mai caricata non e' un buco P3 | `test_p4_stagione_mai_caricata_non_e_un_buco_p3_...` | Q21 |
| action concorrente | `test_p4_non_parte_se_un_action_concorrente_e_in_corso` | Q30 |
| referto e stima giorni | `test_referto_p4_...`, `test_consumo_giorni_log_e_margine_medio`, `test_referto_p4_log_illeggibile_...` | Q22-Q26 |
| dry-run e stima | `test_dry_run_mostra_mai_caricata_con_il_costo` | Q27, Q28 |
| **verifica `current`** | `test_current_sospetta_verificata_e_trattata_come_dice_l_api`, `test_current_confermata_..._dopo_7_giorni`, `test_verifica_current_nel_budget_e_col_tetto`, `test_verifica_current_errore_api_resta_come_nel_db` | V1-V7 |
| **riserva dinamica**: prima -> 3000, dopo -> 300, token assente -> 3000, run di ieri, fallita, in corso, GitHub in errore, memoria del giorno, residua <= piena, capacita' | `test_riserva_dinamica_2026_09_25.py` (11 test) | R1-R7, R12, R13 |
| **fine giornata UTC** | `test_dalle_23_utc_non_parte_nessuna_lega_stagione`, `test_ora_di_stop_da_env`, `test_lega_stagione_in_corso_si_ferma_a_fine_partita_alle_23` (25 partite, poi stop), `test_p4_non_parte_dalle_23` | R8-R11 |

Mutazioni vecchie (`mutazioni_backfill_automatico.py`): **60/60 ROSSE**. M19 tolta per sempre con commento (sotto
mutazione faceva richieste vere ad api-sports.io); M56 riallineata al testo di `306fd11` (rossa); M33 e M34 erano
diventate "non uniche" per righe gemelle nel codice nuovo: righe nuove riscritte, tornano uniche e rosse.

## 8. Letture del DB vero (dichiarate)

- `api_coverage_by_season` 10 GET da 1.000; `season_backfill_state` 10 GET da 1.000 (solo campi JSON: versione,
  `matches_count`, `ft_count`). Script `AUDIT_2026-09-25/sonde/p4_sonda_get.py`.
- Vista `league_season_riepilogo_popolamento` (conteggio vivo): 1 riga + 2 pagine riuscite, **26 richieste in 57014**
  (~8 s ciascuna, la vista conta `matches` per riga). **Da non usare mai nel codice.**
- `api_call_log`: 1 max(id) + 8 count su finestra di PK (`consumo_giorni_log`, `AUDIT_2026-09-25/sonde/p4_margine_medio_log.py`).

## 9. Chiamate esterne e violazione dichiarata

- Nessuna chiamata API-Football con la nostra chiave, nessuna chiamata a GitHub.
- **Violazione mia**: mentre riallineavo lo script delle mutazioni vecchie, uno script di modifica ha fallito
  un'asserzione e il comando successivo nella stessa riga ha lanciato comunque `mutazioni_backfill_automatico.py M56
  M19`: la mutazione M19 e' girata (~57 s) e il codice mutato ha fatto richieste ad api-sports.io **con la chiave
  finta `x`** (nessuna quota nostra consumata, ma e' rete esterna, vietata dal brief). File ripristinati (sha256).
  Dopo, M19 e' stata tolta dallo script per sempre.
- Una prima corsa completa delle mutazioni vecchie l'avevo interrotta io prima di M19 per lo stesso motivo; verificato
  che nessun file sia rimasto mutato (`git status` + sha256).

## 10. Non verificato

- Nulla e' stato eseguito sul DB vero ne' su GitHub vero: la riserva dinamica e' provata sul finto GitHub (parametri
  e risposta come da API REST documentata). Da verificare dopo il merge: il filtro `created=>=...T..:..:..Z` con ora
  (la documentazione di GitHub accetta date e date-ora ISO nella sintassi di ricerca; non provato dal vivo) e che
  `GITHUB_TOKEN` con `actions: read` legga le run degli altri workflow (gia' usato dal controllo di concorrenza).
- Reset del contatore API alle 00:00 UTC: assunto, non osservato.
- Il conteggio partite di 880/2021, 888/2022 e delle 575 `current` sospette viene dallo stato, non dal conteggio vivo.
- `/fixtures` per lega+stagione assunta senza paginazione (come `fixtures_backfill.py`).
- IO delle 400 verifiche per run: stimato, non misurato.
- Un'action rilanciata a mano DOPO che la riserva e' scesa a 300 trova solo il margine rimasto (le 3 action risultano
  gia' `success`): scelta consapevole (il caso normale e' il rilancio di una fallita, che tiene la riserva piena).

## 11. File

Modificati: `seasons_catchup.py`, `season_backfill.py`, `season_gaps.py`, `api_quota.py`, `league_orchestrator.py`,
`.github/workflows/seasons_catchup.yml` (solo env), `test_backfill_automatico_2026_09_25.py` (1 riga nella fixture),
`AUDIT_2026-09-25/mutazioni_backfill_automatico.py` (M19 tolta, M56 riallineata). Nuovi: `test_catchup_p4_2026_09_25.py`,
`test_riserva_dinamica_2026_09_25.py`, `AUDIT_2026-09-25/mutazioni_catchup_p4.py`, `AUDIT_2026-09-25/sonde/p4_sonda_get.py`,
`AUDIT_2026-09-25/sonde/p4_conta_stagioni_mai_caricate.py`, `AUDIT_2026-09-25/sonde/p4_margine_medio_log.py`,
`AUDIT_2026-09-25/sonde/p4_conta_esito_2026-09-25.txt`, questo referto, `AUDIT_2026-09-25/catchup_p4.patch`.
