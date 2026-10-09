# Q - Orario delle quote (raw_json_odds) rispetto alla previsione e al calcio d'inizio (09/10/2026)

Domanda: le quote del confronto di `M_misure.md` (Betfair Sportsbook, API-Football) erano di chiusura o
successive alla previsione? Risposta breve: NO. Nel campione (n=1519, 21/09-07/10) 0 quote su 1519 hanno
`update` posteriore a `generated_at` del Poisson o dell'ML; la mediana e' 2,0 h PRIMA della previsione e 8,0 h
PRIMA del calcio d'inizio. Il confronto non e' sbilanciato a favore delle quote: se mai, le quote sono piu'
vecchie delle previsioni. La conclusione di M (quote battono Poisson/ML) resta invariata.

## 1. Chi scrive `raw_json_odds` (git grep su tutto il repo, tutti i tipi di file)
- UNICO scrittore: `Prediction/today_predictions_backfill.py`.
  - `_build_odds_row` (riga 893-898) costruisce `{"raw_json_odds": ..., "updated_at": now}`;
    `upsert_odds_row` (901-914) e' un `.update(...).eq("fixture_id", ...)` (non upsert) e, a quanto risulta da git grep,
    non viene chiamata dal flusso principale: il flusso usa `_queue_odds_for_fixture` (2375-2395) -> `writer.queue_odds`
    (2037) -> scrittura differita (2216).
  - Dati: `fetch_odds_for_league_season` (823-876) chiama `/odds?league=&season=&bookmaker=3` (paginata, riga 847-852),
    cache per (lega, stagione) per tutta la run (`odds_cache`); `extract_odds_for_fixture` (879) estrae la fixture.
    La chiave `update` e' quella restituita da API-Football dentro l'oggetto odds (non la scrive il repo).
- Nessun altro scrittore: `Ai Engine/ai_engine/predict_fixture.py:863,998` e `db_adapter.py:325,437` LEGGONO soltanto
  (il `live_odds` Betfair passato al predittore non finisce in `raw_json_odds`); `Betfair/betfair_report_manager.py:63,348`
  e le migrazioni `migrations/analytics_strategy*.sql` solo leggono.
- Quando gira: workflow `.github/workflows/today_predictions_backfill.yml` (`python -m Prediction.today_predictions_backfill`,
  righe 65-69), UNA volta al giorno, TERZO anello della catena notturna (dal 09/10: lanciata da Leagues Mapping via
  passa-testimone, orologio pg_cron 00:12 UTC; prima cron `18 2 * * *`, righe 3-4 del workflow). Data di default = oggi UTC.
  Nel campione l'orario reale e' 07-09 UTC (p_gen: ora 08 n=1023, 07 n=358, 09 n=138).
- Si riscrive dopo la previsione? Il ciclo `run_for_date` salta le fixture con `status='ok'` e `ht_predictions` non nullo
  (`done_fixture_ids`, righe 2426-2459: `if fixture_id in done_fixture_ids: continue`), quindi una riga gia' completata NON
  viene piu' toccata dal workflow (ne' prediction, ne' odds, ne' analisi). Una riga non completata viene riscritta INSIEME
  (ordine prediction -> odds -> analisi, commento 2433-2436), quindi odds e `generated_at` restano coerenti. Un rilancio
  manuale con `--date` di una data passata e' possibile (`workflow_dispatch` input `date`): per quelle date `/odds` restituisce
  cio' che l'API ha ancora. Nel campione non e' emerso (vedi sotto: 0/1519 con update > p_gen).
  NON VERIFICATO: eventuali scritture manuali dal pannello Supabase o da script fuori repo.

## 2. Misura (4 SELECT di sola lettura, `sonde/q_estrai.py` -> `q_ts.json`; analisi `sonde/q_orario.py` -> `q_orario_output.txt`)
Finestre fixture_date 21-25/09 (62), 25-29/09 (562), 29/09-03/10 (219), 03-08/10 (676) = 1519 righe, stesso filtro di
`m_estrai.py` (FT, db_json_analisi e raw_json_odds non null); i `p_gen`/`ml_gen` coincidono riga per riga con `m_dati.json`
(0 differenze), nessuna riga senza `update`.

| grandezza (ore) | n | min | p25 | mediana | p75 | max |
|---|---|---|---|---|---|---|
| fixture_date - update (>0 = quote prima del calcio d'inizio) | 1519 | -0,02 | 5,78 | 7,99 | 11,90 | 19,47 |
| update - generated_at Poisson (>0 = quote dopo la previsione) | 1519 | -26,04 | -2,42 | -2,00 | -0,97 | -0,01 |
| update - generated_at ML | 1510 | -28,85 | -3,91 | -2,99 | -2,10 | -0,12 |
| created_at riga - update | 1519 | -1201 | 0,88 | 1,99 | 2,42 | 26,06 |

- `update` DOPO il calcio d'inizio: 20 su 1519 (1,3%), al massimo 0,02 h = ~1 minuto dopo (partite delle 00-07 UTC
  prese dalla run delle 07-09 UTC; vedi sotto). Entro 1 h dal calcio d'inizio: 78; entro 3 h: 211. Non sono quote di chiusura.
- `update` DOPO `generated_at` Poisson: 0 su 1519. DOPO `generated_at` ML: 0 su 1510 (9 senza ML).
- Stesso giorno UTC del calcio d'inizio: 1517; giorno precedente: 2. Ore UTC di `update`: 06 (974), 08 (422), 00 (104), altre poche
  -> sono istantanee dell'API (aggiornate a blocchi di ore), non la quota nell'istante della richiesta.
- `fixture.date` dentro raw_json_odds diversa da `fixture_date` della riga: 2 (sanita' dell'abbinamento: ok).
- Collegato ma gia' noto da M: `generated_at` Poisson DOPO il calcio d'inizio in 160/1519 (10,5%); sono previsioni tardive,
  non quote tardive.

## 3. Confronto log-loss 1X2 solo dove quote disponibili alla previsione (update <= generated_at)
Poiche' update <= p_gen vale per TUTTE le righe, il sottocampione coincide col campione di M (n=1518 con quote 1X2 valide + Poisson;
1509 con ML). Ripetuto comunque con ricampionamento bootstrap (1000, seed 20261009) e con sottocampioni piu' stretti. Differenze di
log-loss vs quote de-viggate moltiplicative (d>0 = peggio delle quote), IC95 bootstrap:

| campione | n | Q molt. | Poisson calibr. d [IC] | ML servito d [IC] |
|---|---|---|---|---|
| M originale (B, con ML) | 1509 | 0,9592 | +0,0527 [+0,0382,+0,0672] | +0,0489 [+0,0334,+0,0638] |
| P: update<=p_gen (senza ML) | 1518 | 0,9585 | +0,0538 [+0,0404,+0,0681] | n.d. |
| PM: con ML, update<=min(p_gen,ml_gen) | 1509 | 0,9592 | +0,0527 [+0,0382,+0,0672] | +0,0489 [+0,0334,+0,0638] |
| P3: update<=p_gen e >=3 h prima del calcio d'inizio | 1287 | 0,9554 | +0,0557 [+0,0405,+0,0701] | n.d. |
| S: quote, Poisson e ML tutti prima del calcio d'inizio | 1309 | 0,9537 | +0,0574 [+0,0423,+0,0730] | +0,0522 [+0,0370,+0,0675] |

Ovunque tutti gli IC95 escludono lo zero: le quote battono Poisson e ML. Anche la miscela migliore e' w*=0 (nessun peso a Poisson/ML:
CV5 d=+0,0000). Il vantaggio delle quote NON si riduce nel sottocampione "pulito" (S: +0,057 Poisson, +0,052 ML, piu' ampio che in M).
Controllo "update > p_gen" (dove le quote sarebbero posteriori): sottocampione vuoto (n=0), non eseguibile.

## 4. Reperti
1. (BASSO, esito del test) Ipotesi "quote di chiusura / posteriori alla previsione" FALSIFICATA sul campione: 0/1519 con update > p_gen,
   mediana update = 2,0 h prima della previsione e 8,0 h prima del calcio d'inizio. `sonde/q_orario_output.txt`.
2. (BASSO) 20/1519 quote con `update` fino a ~1 minuto dopo il calcio d'inizio (kickoff 00-07 UTC, run 07-09 UTC); escluse nel
   sottocampione S (n=1309 esclude anche le previsioni post-kickoff): risultato invariato.
3. (MEDIO, limite residuo, NON VERIFICATO) `update` e' il timestamp di API-Football, non l'istante in cui il bookmaker ha quotato; la
   frequenza di aggiornamento pre-partita dell'API non e' stata verificata (nessuna ricerca web fatta). Le quote sono comunque "piu'
   vecchie" della previsione, il che e' neutro o sfavorevole alle quote.
4. (BASSO) `upsert_odds_row` (Prediction/today_predictions_backfill.py:901) risulta non chiamata dal flusso principale (usa
   `queue_odds`); da confermare con git grep dei chiamanti, non e' rilevante per la misura.
5. (INFO) Il confronto resta valido solo per 21/09-07/10, un'unica fonte di quote (Betfair Sportsbook tramite API-Football, non
   l'exchange) e partite che hanno quote; il caveat di selezione (solo partite con raw_json_odds) e' quello di M.

## 5. Decisioni utente
Nessuna: misura in sola lettura, nessuna strategia toccata.

## 6. Metodo
- `git grep -n "raw_json_odds"` (py/yml/sql, poi tutti i tipi non py) -> unico scrittore in `today_predictions_backfill.py`; lettura
  righe 770-925, 2375-2480, 2625-2645 e del workflow; `git grep -n "_queue_odds_for_fixture|upsert_odds_row|fetch_odds"`.
- 4 SELECT di sola lettura (`q_estrai.py`, LIMIT 1000, ordine per fixture_id, finestre di 4-5 giorni; il maggiore ha dato 676 righe),
  nessuna scrittura/RPC. Nessun processo lasciato acceso.
- `q_orario.py` esegue le funzioni di `m_misure.py` (fino a `out = []`) su `m_dati.json` + `q_ts.json`; output `q_orario_output.txt`.
