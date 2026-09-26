# E2E FASE 3 — PAGINE, CAMPO PER CAMPO — SESSIONE B — 26/09/2026

Delegato Opus del coordinatore (sessione B). **SOLA LETTURA**: nessuna scrittura sul DB, nessun comando ai bot,
nessun clic che scrive, nessun processo del progetto avviato/fermato, nessun commit. Base `origin/master` = `46e619b`
(fetch del 26/09, worktree isolato `agent-a9d14a77b4f5c9155`, junction `frontend/node_modules` → checkout principale).
Finestra di misura: 26/09 09:03-09:55 UTC (11:03-11:55 Roma).

**Stato dell'impianto durante la misura (dal DB):** alle 09:03 UTC Omega/Mike/Safe `stopped/paper`; dalle ~09:10 UTC
tutti e tre `running/paper` (acceso dall'utente: fase 2) con posizioni paper vive (Omega 3→4, Safe 2, Mike 2). I
numeri dei bot sono quindi confrontati con la risposta RPC registrata **nello stesso istante** del render e con
SQL indipendente sulle righe (che per le parti regolate non cambiano).

## 0. Metodo (come è stato «visto» ogni valore)

- **Chrome non disponibile** (`list_connected_browsers` = nessun browser collegato) → per TUTTE le pagine si è usato il
  ripiego del brief: **render del componente vero** (pagina intera, con i provider di `App.tsx`: QueryClient, Helmet,
  TooltipProvider, Router; Safe dentro `SafeStrategyProvider`) in jsdom, con il **client Supabase vero in sola lettura**
  (`frontend/src/certification/sessB/clientB.ts`): service role del `.env` della radice, `rpc()` ammessa SOLO per
  funzioni non volatili (verificato in `pg_proc`: tutte le `get_*`/`list_*`/`trading_*` sono STABLE, più
  `run_strategy*`, `backtest_strategy`, `omega_eventi_chiusi_dall_utente`), `insert/update/upsert/delete` bloccati,
  realtime stub, **canale locale spento** (WebSocket finto: le pagine leggono dal DB, ripiego dichiarato), ogni
  risposta RPC/select registrata (evidenza del valore alla fonte). Il testo visibile (con `data-testid` e `title`) è
  salvato per ogni pagina/tab/pannello.
- **Esito delle guardie** (4 esecuzioni, 20 test verdi): `blocked = []`, `wsSends = []` in tutte → **nessun tentativo di
  scrittura** e nessun invio sul canale da parte delle pagine all'apertura.
- **Atteso**: SELECT esplicite scritte da zero (Supabase MCP `execute_sql`, solo SELECT e chiamate a funzioni STABLE) e
  ricalcoli Python: `verifica_modelli.py` (funzioni di PRODUZIONE importate: `_build_score_grid`/`_dc_tau` di
  `Prediction/today_predictions_backfill.py`, `PoissonCalibrator`, `score_matrix`/`markets_from_matrix`/
  `top_correct_scores`/`expected_goals`/`rho_bounds` di `tactical_engine/dixon_coles.py`), `verifica_direzione.py`
  (ricalcolo indipendente in Python di direzione, pagella con shrinkage K=50, Wilson 95%, lift, concordanza, quota).
- Limiti del banco (dichiarati): nessun hover (tooltip dei grafici non letti: il loro dato è verificato sulla serie
  della RPC); i grafici recharts sono disegnati (assi letti) con un ResizeObserver d'ambiente 900×400; nessun login
  (e-mail utente non visibile); canale locale spento (la sovrapposizione 47333/47334/47335 non è misurata qui).

Partite di prova (Dashboard): **A** 1492980 Cobh Ramblers–Athlone (lega 358, 25/09, finita 3-3, tutti i motori + quote
Betfair); **B** 1498845 Quilmes–Güemes (129, oggi, tutti i motori, nessuna quota); **C** 1637820 Bohemians–Bohemians
1905 (667 amichevoli, oggi, solo Poisson); **D** 1528882 Türkiye–France (5, 25/09, niente Poisson); **E** 1533042
(1093, 04/07, uno dei 17 payload TacticAI con `under_0_5<0`).

Legenda esito: **OK** = visto = atteso entro la tolleranza; **KO** = divergenza con evidenza; **NC** = NON CERTIFICATO
(motivo scritto).

---

## 1. Dashboard `/dashboard` (U0001-U0108)

### 1.1 Lista partite e scheda (U0001-U0040)

| id | campo | fonte | atteso (SQL/ricalcolo) | visto | scarto | esito |
|---|---|---|---|---|---|---|
| U0001 | e-mail utente | `useAuth` | — | vuoto (nessuna sessione nel banco) | — | NC: richiede login dell'utente |
| U0002 | pulsanti barra | navigazione | presenti | CONTROL ROOM…Esci presenti | 0 | OK (Esci non esercitato: scrive la sessione) |
| U0003 | «Torna a …» da `from=` | param URL | — | solo «Torna alle partite» | — | NC: `from=` non esercitato |
| U0004 | deep-link `?fixture=` | `fixture_predictions` `.eq` | 5 partite caricate | 5 schede aperte | 0 | OK |
| U0005 | titolo/sottotitolo | stato | «Partite del Giorno · Tutte le partite in programma oggi» | idem | 0 | OK |
| U0006 | toggle «Match Betfair» | `get_betfair_fixtures(26/09)` | 0 righe: `engine_signals` max `run_date` = 25/09 | (non cliccato) | — | NC (rinvio): la pipeline del 26/09 non ha ancora scritto `engine_signals`; oggi il filtro restituirebbe lista vuota |
| U0007 | filtro campionato | `.eq(league_id)` | — | elenco fisso presente | — | NC: non esercitato |
| U0008 | «N Match» | calcolo | `count(*)` status ok, `fixture_date>='2026-09-26T00:00:00Z'` = **1186** | **1186 Match** | 0 | OK |
| U0009 | sorgente a blocchi | `fixture_predictions` range 1000 | 1186 id distinti | 1000+186 righe; sonda `sonda_lista.mjs` 5 ripetizioni: 1186 righe, 0 doppioni | 0 | OK — nota: ordine solo per `fixture_date` (16 righe a pari orario 17:00Z a cavallo del blocco 1000, pos. 988-1003): oggi stabile, non garantito |
| U0010 | gruppi lega + «N partite» | group by `league_id-league_name` | 284 gruppi, md5 `5073f474…` (SQL collate "C") | 284 gruppi, md5 `5073f474…`, somma 1186 | 0 | OK |
| U0011 | ora | `toLocaleTimeString` | 14:00Z→16:00 Roma | Bohemians 16:00 | 0 | **KO lieve (fuso)**: la lista del 26 include partite 22:00-23:59Z che a video sono «00:00»/«01:00» (Deportivo Madryn 22:00Z → «00:00», Colegiales 23:00Z) = giorno 27 locale senza data; confine `T00:00:00Z` (`MatchesList.tsx:126,145`) |
| U0012 | stato | `status` | ok | «ok» | 0 | OK |
| U0013 | squadre | `home/away_team_name` | Bohemians / Bohemians 1905 | idem | 0 | OK |
| U0014 | casella watchlist | stato locale | presente | presente | — | OK (non cliccata) |
| U0015 | ANALIZZA | → U0004 | presente | presente | — | OK |
| U0016 | aggiungi a watchlist | SCRIVE `add_to_watchlist` | — | — | — | NC: scrittura, vietata |
| U0017-U0019 | Hero lega·stagione·paese, squadre, Fixture/League ID | `raw_json` + colonne | First Division • 2026 • Ireland; 1492980 / 358 | idem | 0 | OK (×3) |
| U0020 | % Match Odds | `predictions.percent` | 35/35/30 | Home 35% Draw 35% Away 30% | 0 | OK |
| U0021 | Advice / Winner | `predictions.advice/winner` | «Double chance : Cobh Ramblers or draw», Cobh Ramblers (Win or draw) | idem | 0 | OK |
| U0022 | Goals & Outcome | `predictions.goals` | A: `-2.5/-2.5`; **D: `home=null, away=null`** | A: «Home -2.5 / Away -2.5»; **D: «Home 0 / Away 0»** | null→0 | **KO (caso limite)**: gol nulli resi come 0 invece di «—» (`PredictionsCard.tsx:88-102`) |
| U0023 | pannello squadra | `teams.<lato>` | ID 3849 / 3846 | idem | 0 | OK |
| U0024 | League Form | `league.form` (32 car.) | Last 32; 13W 6D 13L (`fixtures`) | «Last 32 … 13 W 6 D 13 L» | 0 | OK |
| U0025 | Last 5 % | `last_5` | 53/63/44 e 87/63/81 | idem | 0 | OK |
| U0026 | Last 5 medie | `last_5.goals/played` | A: 10/5=2.0, 9/5=1.8; **D: played=0** | A ok; **D: «Avg: NaN per match»** | NaN | **KO (caso limite)**: `played=0` → NaN a video (`Last5Card.tsx:6-7`) |
| U0027-U0028 | Goals totali/medie | `league.goals` | 21/18/39; 1.3/1.1/1.2 | idem | 0 | OK (×2) |
| U0029 | Goals by Minute | `minute[*].total` | D: tutti `null` | asse 0-4, barre a 0 | null→0 | **KO (caso limite)**: nulli resi 0 (dichiarato in inventario, confermato sul dato) |
| U0030 | Under/Over distribution | `under_over` | 0.5: U9·O23 … 4.5: U32·O0 | idem | 0 | OK |
| U0031 | Cards by Minute | `cards` | casa gialli Σ=80, rossi 2; ospite gialli Σ=80 (1+9+13+11+17+21+8), rossi 2 | 80 / 2 per entrambe | 0 | OK (coincidenza verificata cella per cella) |
| U0032 | Records & Streaks | `biggest` | 3/2/4; 4-0, 1-3, 0-3, 5-1; 4/3/3/5 | idem | 0 | OK |
| U0033 | Formations | `lineups` | `[]` | carta assente | — | OK (caso «assente → non mostrato») |
| U0034 | riepilogo partite | `fixtures` | 32; W 6/7=13, D 6/0=6, L 4/9=13 | idem | 0 | OK |
| U0035 | Penalty | `penalty` | 8; 7 (87.50%); 1 (12.50%) | idem | 0 | OK |
| U0036 | Clean sheet / Failed | `clean_sheet`, `failed_to_score` | 6/2/8; 3/6/9 | idem | 0 | OK |
| U0037-U0038 | Confronto + TOTALE | `comparison` | 38/62, 50/50, 25/75, 60/40, 60/40, 55/45, 48.0/52.0 | idem | 0 | OK (×2) |
| U0039 | Insight AI | `|h−a|≥5` | 5 frasi (form 62, dif 75, poisson 60, h2h 60, gol 55) | 5 frasi identiche | 0 | OK (nota grammaticale: «un forma», «un difesa») |
| U0040 | H2H (primi 6) | `raw_json.h2h` | 10/07/26 Athlone 2-0 … 23/05/25 Athlone 2-3 | 6 righe identiche | 0 | OK |

### 1.2 Frequenze Mercati (U0041-U0052) — `get_market_frequency`, ricalcolo SQL da `matches`

| id | campo | atteso (SQL indipendente) | visto | esito |
|---|---|---|---|---|
| U0041 | pulsante | presente se `leagueId` | presente (5 schede) | OK |
| U0042 | filtri mercato/selezione | 12 mercati | 12 | OK |
| U0043 | Intervallo / Stagioni | 358: 8 stagioni (2026: 164) | 358 ok; **667: `get_league_seasons(667)` → «canceling statement due to statement timeout»** (2 volte) | **KO**: su lega 667 il menu Stagioni resta vuoto |
| U0044 | Baseline | 358 last300 1X2 «1»: 147/300=**0.4900**; 129: 0.5067; 667: 0.4200; 5: 46.0%; 1093: 0.4525 (263) | 49.0% · 50.7% · 42.0% · 46.0% · 45.2% | OK (×5) |
| U0045 | «Serie su N … richieste X, disponibili Y» | 300; 1093: 263 disponibili | «300 esiti validi»; 1093: «richieste 300, disponibili 263» | OK |
| U0046 | σ, se(MM10) | σ=0.4999 (pop), se=σ/√10=0.1581 | «σ 0.500 · se(MM10) 0.158» | OK |
| U0047 | dal → al | 358: 18/04/2025 → 25/09/2026 (129: 22/09 ora Roma = 21/09 22:00Z) | idem | OK (fuso Roma corretto) |
| U0048 | badge copertura HT | 667: 87.7 % (meta) | mercato HT non aperto nel banco | NC |
| U0049 | confronto stagione B | — | non esercitato | NC |
| U0050 | grafico MM5/10/15 + bande | ultimo punto 358: MM5 0.6, MM10 0.6, MM15 0.4, z=(0.6−0.49)/0.158082=0.696 (SQL ultime 5/10/15) | serie RPC identica; assi disegnati | OK |
| U0051 | tooltip | — | hover non eseguibile | NC (dato del punto verificato in U0050) |
| U0052 | avvisi serie corta/errore | serie < 15 non presente | — | NC |

### 1.3 Studio Ritardi (U0053-U0064) — `get_market_delays`

| id | campo | atteso (SQL indipendente) | visto | esito |
|---|---|---|---|---|
| U0053-U0054 | pulsante, 13 fogli | 13 | 13 | OK (×2) |
| U0055 | Storico: Tutto / Stagione / Ultime N | — | **lega 667, default «Tutto lo storico»: «Errore: canceling statement due to statement timeout»** (schede C e test dedicato); `get_market_delays(667,…,'all')` misurata 21,8 s, lega 45 (10.511 gare) 16,2 s; ruolo `authenticated` ha `statement_timeout=8s` | **KO**: sulle leghe grandi il trader vede un errore invece dello studio; ok su 358/129/5/1093 |
| U0056 | eventi / occorrenze / dal→al | 358 SGE=3: 1240 / 268; 129: 7367/1311; 5: 678/147; 1093: 263/36 | identici | **KO lieve (formato)**: date mostrate come ISO UTC grezze «2019-02-22T19:45:00+00:00 → …» (Frequenze le formatta dd/mm/yyyy) |
| U0057 | avviso HT «escluse» | 667 ovpt 0.5 last 500: 51 senza PT, 449 eventi, 341 occ., copertura 89,8 % (SQL); tutto lo storico: **25.409** eventi (25.408 del 25/09 + 1), 14.342 esclusi, 63,9 % (SQL) | «Copertura primo tempo 89.8 %: le 51 gare … ESCLUSE … 449 eventi» | OK (regola «escluse» applicata; migrazione `market_delays_ht` attiva) |
| U0058 | carte | 358: freq 268/1240=0.2161, media storica 1240/268=4.627, rit. attuale 1, ×0.216, record 35, media rit. (AVERAGEIF≠0) 4.9372 | 4.63 · ogni 4.6 · 1 · 0.22× · 35 · 21.6% · 4.94 | OK |
| U0059 | grafico RIT | serie 1240 | asse 8…1240, linee media/record | OK |
| U0060 | tooltip | — | hover | NC |
| U0061 | distribuzione serie | cnt_rit(0)=268, cnt_rit(1)=211, occ_suc(0)=58, occ_suc(1)=45+1 (serie iniziale, semantica Excel) | 58/268, 46/211 | OK |
| U0062-U0063 | sotto/sopra media, run | valori RPC (188/80, 70,15 %/29,85 %) | idem | NC: ricalcolo indipendente non eseguito |
| U0064 | tabella DATI MATCH | ultima riga UCD–Bray 1-3, PT 0-1 (`matches`) → GCFH 0, GAFH 1, GCSH 1, GASH 2 | idem | OK |

### 1.4 Poisson (U0065-U0074) — `db_json_analisi`, ricalcolo con funzioni di produzione

| id | campo | atteso | visto | esito |
|---|---|---|---|---|
| U0065-U0066 | titolo, sorgente | — | «Poisson · casa vs trasferta» | OK (×2) |
| U0067 | modello, calibrato | `poisson_xg_hybrid_dc`, `markets_calibrated` presente | «✓ calibrato» | OK |
| U0068 | λ, ρ, partite, xG | A: 1.3148/1.0714, −0.13, 15/15, false; B: ρ −0.1757; C: 6/8, −0.0772 | «λ 1.31 / 1.07 ρ −0.13 partite 15/15 xG no»; B −0.18; C 6/8 −0.08 | OK |
| U0069 | età previsione | A `generated_at` 25/09 08:02Z | «25/09/2026, 10:02 (25 h fa)» (< 36 h) | OK |
| U0070 | età calibrazione | `poisson_calibration.generated_at` lega 358 = 21/09 09:20Z | «21/09/2026, 11:20 (5 g fa)» (< 8 g); «applicata il 25/09 10:02:06» = `calibrated_at` | OK |
| U0071 | mercati | 7 chiavi | 7 | OK |
| U0072 | barre / più probabile | ricalcolo griglia DC (produzione) dalle λ/ρ salvate: scarto max 3,1e-4 su 1X2/Over/BTTS (arrotondamento λ a 4 decimali); somme calibrate = 1,00000; ricalibrazione con `PoissonCalibrator` sui mercati grezzi: scarto **0** (A, B, C); E (luglio): 0,092 (calibrazione cambiata dopo) | A «1 (Casa) 45%» = cal H 0.4504; B 64%; C 44% | OK |
| U0073 | dettaglio 1°T | ibrido w·freq+(1−w)·poisson = True (scarto ≤1e-4); `poisson` = 1−P(0-0) griglia HT (ricalcolata) | mercato 1°T non selezionato | NC (dato ricalcolato, resa non aperta) |
| U0074 | «non disponibile» | D: `db_json_analisi` nullo | «Poisson non disponibile per questa partita» | OK (nessuno zero inventato) |

### 1.5 Tactical Engine (U0075-U0082) — ricalcolo `dixon_coles.py`

| id | campo | atteso | visto | esito |
|---|---|---|---|---|
| U0075 | sorgente | `tactical_engine_json` | caricato | OK |
| U0076 | meta | A: gsg-dc-z2-1.0, λ 1.686/0.981, ρ 0.0635, 1097, converged | «λ 1.69 / 0.98 ρ 0.06 storico 1097 ✓ converged» | OK (nota: «leakage-free» è testo fisso, non letto dal dato) |
| U0077 | età | A 25/09 09:33Z (23 h); B 23/09 12:31Z; E 04/07 | A «23 h fa»; B «2 g 20 h fa · oltre 36 h» (rosso); E «84 g 2 h fa · oltre 36 h» | OK (i payload vecchi compaiono come VECCHI) |
| U0078 | gol attesi, forze | ricalcolo `expected_goals`: scarto 0,000; att/dif 0.947/1.128, 0.752/1.181 | 1.69/0.98; att 0.95·dif 1.13, 0.75·1.18 | OK |
| U0079 | barre / più probabile | ricalcolo `markets_from_matrix` (ρ clampato `rho_bounds(TAU_MIN)`): scarto max 1e-4 (A), 2e-4 (B); E: 3,6e-3 (payload pre-fix con ρ=0,2 al bordo, `under_0_5=−0.0018`, `over_0_5=1.0018`) | A «1 (Casa) 55%» (0.5465) | OK — il valore negativo di E NON è mostrato (Under 0.5 FT non in menu), E è marcato «oltre 36 h» |
| U0080 | risultati esatti | `top_correct_scores` = payload (scarto ≤1e-4) | «1-0 12% 1-1 11% 2-0 10% 2-1 10% 0-1 8%» | OK |
| U0081 | esito reale | A finita FT 3-3 (`matches`), payload `actual=null` | blocco assente | **KO**: `tactical_engine/serving.py:187-188` scrive SEMPRE `actual: None`; nessun processo di produzione lo aggiorna (solo `generate_predictions.py` offline): 233/5.976 payload hanno l'esito → il blocco «Esito reale (90')» non compare mai sulle previsioni giornaliere |
| U0082 | consiglio | ricalcolo regole `lib/tacticalEngine.ts:70-104` su A: max 0.5465 → «favorita», <0.55 → 1X 0.7734=77 %, Over/Under 2.5 <0.58 → «equilibrata (Over 2.5 50 %)», BTTS nessuna frase | identico | OK |

### 1.6 Modelli ML (U0083-U0092)

| id | campo | atteso | visto | esito |
|---|---|---|---|---|
| U0083 | sorgente | `model_predictions_json` | caricato | OK |
| U0084 | meta | A: ensemble_v2, high 1.0, 100 %, 110/111; B: 111/108 | idem | OK |
| U0085 | età | A 25/09 16:38Z; B 26/09 08:21Z | «18:38 (16 h fa)»; «10:21 (1 h fa)» | OK |
| U0086 | mercati | 21 target = 21 righe `ai_model_registry` (358 e 129, `ensemble_v2`) | «Mercato (21)» | OK |
| U0087 | barre / previsione | A `target_1x2` H .4591 D .2072 A .3337 (somma 1); nessun target con somma ≠ 1 (5 partite) | «1 (Casa) 46%», ordine H>A>D | OK |
| U0088 | accordo ensemble | voti rf/lgb/xgb = H, logreg = D → 75 % | «classe prevista 1 (Casa) 75 % accordo» | **KO (coerenza)**: la «classe prevista» è il VOTO dei 4 modelli grezzi, la «Previsione» è l'argmax delle probabilità calibrate: divergono su 7 target di A (es. `target_btts`: Previsione «No» 51,74 %, classe prevista «Sì» 75 %), 5 di B, 4 di D, 2 di E — due verdetti opposti nello stesso riquadro |
| U0089 | Brier/ECE/affidabile | 0.5895/0.0533; `targets_not_reliable` BSS=0.116 | «Brier 0.590 ECE 0.053 · MODEL_NOT_RELIABLE…» | OK |
| U0090-U0091 | segnali di valore | `bet_signals` = null nelle 5 partite | — | NC: nessun dato |
| U0092 | «ML non disponibile» | C: null | messaggio | OK |

### 1.7 Direzione (U0093-U0106) — `verifica_direzione.py` (ricalcolo Python indipendente dalle righe)

Ricalcolo su 5 partite, 35 carte: **0 scarti** su direzione, affidabilità, Wilson low/high, n, lift, quota, scope,
concordi, motori totali (tolleranza 1e-4).

| id | campo | atteso | visto | esito |
|---|---|---|---|---|
| U0093 | sorgente / ordine | ordine per lift desc | Over 3.5, Over 2.5, 1°T, 1X2, BTTS, HT, Over 1.5 | OK |
| U0094 | età pagella | `max(direction_pagella.generated_at)` = 25/09 09:52Z | «25/09/2026, 11:52 (23 h fa)» | OK |
| U0095 | quote presenti | A: 45 righe, 20 con prezzo | «presenti su 20 righe di 45»; B/C/D «quota assente» | OK |
| U0096 | avviso Poisson mancante | D `poisson_present=false` | avviso mostrato | OK |
| U0097-U0099 | semaforo, affid.+Wilson, LIFT | A Over 3.5 Under: 0.761 [0.6729-0.8313], lift +0.1041 | «76 % 67-83 % +10» | OK (×3) |
| U0100 | quota / valore | A: `odds_betfair` NULL, `odds_book` 1.36 (Under 3.5), 2.50 (1X2 H) | «1.36 quota», «2.50 quota» | **KO**: la «quota» della carta è del BOOKMAKER (`coalesce(odds_betfair, odds_book)`, e `odds_betfair` è quasi sempre NULL: 0 righe su 17 giorni tranne 17/09 e 23/09) mentre nello stesso pannello «Quote Betfair back/lay» mostra Under 3.5 1.42/1.46 e H 2.68/2.78; il giudizio «valore» (`wilson_low > 1/odds`) è fatto sulla quota book senza dichiararlo |
| U0101 | N/M motori | 3/3, 3/4, 1/1 (C), 1/3 (D) | idem | OK |
| U0102 | frase dettaglio | 76 %, 67-83 %, ~109 partite lega, media 66 %, +10, implicita 1/1.36=74 % | idem | OK |
| U0103 | cosa dice ogni motore | P 0.779/0.221, ML 0.656/0.344, Tac 0.721/0.279 | «Under 78 % Over 22 % / 66/34 / 72/28» | OK |
| U0104 | stato attuale · frequenza | 358 under 3.5 all: baseline 0.6766, MM10 0.6, z −0.518 | «attuale 60 % · media 68 % · z −0.5 · in media (1240)» | OK |
| U0105 | stato attuale · ritardo | 358: attuale 1, media 1.478, record 5, ×0.677 | «1 · 1.5 · 5 · sotto la media (×0.7) su 1240» | **KO (leghe grandi)**: stesso RPC `get_market_delays(mode 'all')` di U0055 → su 667/45 va in timeout (21,8 s / 16,2 s > 8 s); OK su 358 |
| U0106 | quote Betfair back/lay | `betfair_market_odds` | Over 3.15/3.40, Under 1.42/1.46 | OK (nessuna età delle quote a video) |

### 1.8 Quote Betfair (U0107-U0108)

| id | atteso | visto | esito |
|---|---|---|---|
| U0107 | A Match Odds Cobh: back 2.68(13)/2.66(32.9)/2.64(11.37), lay 2.78(156)/2.82(180)/2.84(12); captured 25/09 17:28Z | «2.64 €11 · 2.66 €33 · 2.68 €13 | 2.78 €156 · 2.82 €180 · 2.84 €12» (migliore vicino al centro) | OK (nota: nessuna età della cattura a video) |
| U0108 | B: 0 righe | «Nessuna quota Betfair per questa partita» | OK |

**Dashboard: 108 campi — OK 82 · KO 11 · NC 15.**

---

## 2. Analytics e Reportistiche `/analytics` (U0109-U0139)

| id | campo | atteso | visto | esito |
|---|---|---|---|---|
| U0109 | «N segnali settlati» | 3×99.242 (`fixture_predictions.result_outcome`) + 920.064 (`analytics_signals settled`) = **1.217.790** (anche via RPC: 1.217.790 in **37,8 s**) | assente: `get_analytics_filters` → «statement timeout» | **KO** |
| U0110 | tab | 5 | 5 | OK |
| U0111 | filtri | opzioni da `get_analytics_filters` | tutti i menu con 1 sola opzione («Tutti») | **KO** (conseguenza di U0109) |
| U0112-U0113 | calibrazione / tabella gruppi | `get_analytics` | «canceling statement due to statement timeout» + «Nessun segnale settlato per questi filtri.» | **KO** ×2: errore + stato vuoto fuorviante |
| U0114 | drill-down | — | irraggiungibile | NC (bloccato da U0113) |
| U0115 | selettore logica | `list_strategies` = 2 | «Google Sheets (reale) (3 opz.)» | OK |
| U0116-U0118 | Decisioni (filtri, KPI, tabella) | `get_decisions_filters`, `get_decisions` | «statement timeout» + «Nessuna decisione per questi filtri.» | **KO** ×3 |
| U0119-U0120 | strategia salvata | `run_strategy*` | non selezionata | NC |
| U0121 | filtri Crea Strategia | commissione default 5 | presenti, «Commissione % (def. 5) 5» | OK |
| U0122-U0123 | risultati backtest | — | backtest non eseguito | NC |
| U0124 | Salva | SCRIVE | — | NC |
| U0125 | catalogo report | «Direzioni» | idem | OK |
| U0126 | periodo | 7 gg = oggi−6 | Dal 2026-09-20 Al 2026-09-26 | OK |
| U0127 | KPI | SQL indipendente (DISTINCT ON fixture×mercato argmax Poisson, finestra Roma, quote `engine_signals` mappate, pnl back 1u comm. 5 %): N 6783, hits 4094, avg_prob 0.604617, buone 5311/3415, prezzate 145, profit −6.683, ROI −0.046090, q.media 1.7704, buone prezzate 125, ROI buone −0.069776 | 6783 · 60.4 % (IC 59-62) · 60.5 % scarto −0.1 % · 64.3 % (5311) · ROI −4.6 % · buone −7 % · q.media 1.77 · 2 % 145/6783 | OK |
| U0128 | avviso copertura | 145/6783 = 2 % < 50 % | avviso «Copertura bassa» | OK |
| U0129 | andamento giornaliero | N per giorno (SQL): 3819/763/453/294/313/1068/73 | identici | OK |
| U0130 | heatmap segnale×giorno | — | valori della RPC | NC: celle non ricalcolate una a una |
| U0131 | riepilogo per segnale | SQL: 1x2 970/48.2/48.9/683, btts 970/56.7/56.7/664, 1T 973/74.1/71.3/908, ht 960/40.9/43.1/622, O1.5 970/79.6/76.2/914, O2.5 970/59.1/60.4/698, O3.5 970/63.6/66.4/822 | identici | OK |
| U0132 | per convinzione | SQL: 0/4 13 30.8 %, 1/4 1459 46.3 %, 2/4 4971 63.8 %, 3/4 340 71.2 % | identici (righe lette) | OK |
| U0133-U0135 | classifica leghe, partite, drill | valori RPC | letti | NC: ricalcolo non eseguito |
| U0136 | partite registrate | `live_follow status='UPLOADED'` = 38 | 38 righe (Parma–Cremonese 01/09 … ) | OK (nota: nessuna registrazione dopo il 01/09) |
| U0137 | configurazione backtest | default 1000 / 0.25 / 5 / LAPSE / 0.12 / 0.17 / OFF | idem | OK |
| U0138 | esegui | SCRIVE `request_backtest` | — | NC |
| U0139 | esecuzioni recenti | `list_backtest_runs`: 2 DONE 28/06 | «28/06/2026 13:24:36 · Motore Live · 1 · Completato» ×2 | OK |

**Analytics: 31 campi — OK 13 · KO 7 · NC 11.**

## 3. Report personale `/report-personale` (U0140-U0158)

`personal_trades` = 0 righe, `personal_trade_legs` = 0 (report svuotato): le metriche non sono certificabili sul dato.

| id | esito |
|---|---|
| U0140 barra, U0141 filtri | OK (presenti) |
| U0142 Cassa | OK: SQL `personal_cash_movements` 10 movimenti, depositi 2720, prelievi −1405, netto 1315 = «€2720.00 / −€1405.00 / €1315.00», date 20/07/26… |
| U0143 KPI | OK caso vuoto: «Nessun trade chiuso nel periodo» (nessuno zero inventato) |
| U0150 tabella trade | OK caso vuoto: «Trade (0)» |
| U0144-U0149, U0151-U0155 | NC: nessun trade nel DB |
| U0156-U0158 | NC: dialoghi che scrivono (U0157 distruttivo) |

**Report personale: 19 campi — OK 5 · KO 0 · NC 14.**

## 4. Fogli parametri (U0268-U0272)

| id | atteso (DB) | visto | esito |
|---|---|---|---|
| U0270 Omega | `omega_control.params` (32 chiavi salvate) + `daily_goal` 100; chiavi non salvate = `Betfair/omega/omega_config.py` DEFAULTS | tutte le 32 chiavi salvate identiche (prezzi 20/120, finestre 20-40/50-80, v1 30/60, p max 2, liquidità 5, stake 0.5, green-up …, `greenup_risk_cap` 0.1 salvato vs default 0.15 dichiarato); blocco v3 = DEFAULTS (versione 3, 1 €, 1-44/46-85, k 1.11, 1-2 %, 95/190/1000/300) | OK |
| U0269 Mike | `mike_control.params` {stake 5, max_open_matches 2, uscite_automatiche false, entry_hours_before_ko 1} | 5 / 2 / spento / 1 | OK (campione; il resto a default) |
| U0268 Safe | `safe_strategy_control.params` (≈80 chiavi) | campione di 30 chiavi identico (poll 2, comm 5, max trade 20, liability 300, spread 1.6, stake LAY 2/BACK 3, cap evento 150, 3 per evento, stop −50, conf 0.7, edge 0.03, minuti 55/48/66, uscite a tempo 80/72/83, tennis 0.01 …) | OK (campione) — nota: il testo del gruppo «Il servizio chiude da solo le posizioni aperte …» convive con `uscite_automatiche` tutte false (uscite manuali di default): testo potenzialmente fuorviante |
| U0271 bot tennis | — | fogli solo in Control Room | NC (perimetro Control Room / admin-26) |
| U0272 «parametri non letti» | — | caso non riprodotto (params letti) | NC |

**Fogli: 5 — OK 3 · KO 0 · NC 2.**

## 5. Live P&L `/live-pnl` (U0273-U0281)

| id | atteso | visto | esito |
|---|---|---|---|
| U0273 giorno/mode | 26/09, tutte | idem | OK |
| U0274 realizzato | `betfair_live_settled` 26/09 = 0 righe; 14/09 = 1 riga live +0.30 | «+€0.00 (0 mercati)»; 14/09 «+€0.30 (1 mercati)» | OK |
| U0275 MTM + posizioni aperte | `betfair_live_risk_state.open_mtm`=0 | «+€0.00 · **1 posizioni aperte · rischio €4.40**» | **KO**: la posizione è la riga 14265 (`mode=live`, mercato 1.259819675, aggiornata **10/07/2026**) su un mercato GIÀ regolato (1 riga in `betfair_live_settled`): posizione fantasma mostrata come aperta con rischio; inoltre è mostrata anche col filtro Mode=paper (non filtra per modalità) |
| U0276 totale giornata | `risk_state.total` 0 | «+€0.00 (live)», ⚠ se filtro ≠ live | OK |
| U0277 stop giornaliero | `limit_value` null, `stop_fired` false | «— non scattato» | OK |
| U0278 equity | 14/09: 0 → 0.30 | curva 0,00 → +0,30 16:09-16:39 | OK |
| U0279 per mercato | 1.262395833, +0.30, cleared, 14:24Z | «1.262395833 · — · +€0.30 · reale · 16:24» | OK |
| U0280 per evento | event_id null | «(senza evento) 1 +€0.30» | OK |
| U0281 tennis aperte | `get_tennis_live_positions_all(p_mode=null)`: righe `mode=paper` | mostrate anche con **Mode = live** | **KO (paper e live mischiati)**: la sezione tennis ignora il filtro Mode |

Coerenza: il realizzato di questa pagina (runner) NON contiene il P&L paper di Omega/Safe/Mike (tabelle proprie):
per progetto, ma il titolo «P&L di giornata» non lo dichiara. KO candidato §9-bis n.2 (somma con «tutte»):
confermato dal codice (`LivePnl.tsx:269,272`), non manifestabile sul dato (unica riga storica = live).

**Live P&L: 9 campi — OK 7 · KO 2 · NC 0.**

## 6. Omega `/omega` (U0404-U0468)

Istante: `get_omega_state` registrata con il render (control `running`, heartbeat 09:44:11Z). SQL indipendente su
`omega_trades` (solo `mode=paper` esiste): P&L regolato −44.64, liability aperta 274.0 (94+54+79+47), 4 aperte,
4 gambe oggi.

| id | atteso | visto | esito |
|---|---|---|---|
| U0404 stato | running, battito 14 s | «IN CORSA», «servizio Omega vivo (14 s)» | OK |
| U0405 canale locale | — | canale spento nel banco | NC |
| U0406-U0409 salute | `safe_strategy_status` payload ⚽17 🎾16, stream 158 | «feed vivo (20 s) ⚽ 17 · 🎾 16 · ⚡ STREAM 158» | OK (×4) |
| U0410 PAPER/LIVE | `mode=paper` | PAPER | OK |
| U0411 Avvia/Ferma | SCRIVE | — | NC |
| U0412 Parametri | = U0270 | — | OK |
| U0413 banner | paper | «MODALITÀ PAPER …» | OK |
| U0414 giorno | 26/09 Europe/Rome | «sabato 26 settembre 2026» | OK |
| U0415 obiettivo | `goal_today` 100 | 100,00 € | OK |
| U0416 partite/operazioni/V/P/vive | SQL 4 gambe oggi, 4 vive, 0 regolate | 4 · 4 · 0V 0P · 4 vive | OK |
| U0417-U0418 realizzato, resta, % | 0; 100; 0 % | +0,00 €; 100,00 €; 0,0 % | OK (×2) |
| U0419 liability, bloccato, totale storico | 274 / 0 / −44.64 | 274,00 € / +0,00 € / −44,64 € | OK — **nota latente**: `omega_aggregates_sql` non filtra per `mode` (oggi non esistono righe live: nessuna divergenza, ma paper e live si sommerebbero) |
| U0420 partite chiuse da te | `stats.eventi_chiusi_dall_utente` [] | nessuna riga | OK |
| U0421 liability + bot | 274 / 274 | idem | OK |
| U0422-U0423 bloccato, in verifica | 0 / 0 | idem | OK (×2) |
| U0424 target | 100/266 = 0.376 → 0.38; `target_match` 0.76 | «0,38 € … 266 operazioni e 133 partite (su 150) · 0,76 €/partita» | OK — nota: 0,76 = 2×0,38 arrotondato dal servizio; 100/133 = 0,752 → 0,75 (scarto 0,01) |
| U0425 equity | nessuna regolata oggi | «nessun match ancora regolato» | OK |
| U0426 nota card «storico N partite» | partite distinte (event_id) = **100** | «storico **109** partite» | **KO (etichetta)**: `omega_aggregates_sql.matches_traded` conta le APERTURE (109), non le partite |
| U0427 Totali «Se chiudo ora» | somma «se chiudo ora» delle gambe (−0,50, −2,20, …) | «Se chiudo ora · PAPER +0,00 €» | **KO (coerenza)**: il totale mostra il P&L bloccato (`lockedOpen`), mentre il tooltip e le righe parlano di chiusura a mercato ora |
| U0428-U0434 riga partita | placed 09:10:57Z → 11:10; LAY @48/@80 = `price`; stake 1; rischio 47/79 = `liability`; P mercato 1/55 = 1,8 % | idem | OK (×7) |
| U0435 «se chiudo ora» | ricalcolo green: lay 1@48 chiuso back @32 → −0,50; lay 1@80 back @25 → −2,20 (nessuna commissione sulle perdite) | −0,50 € / −2,20 € netti | OK |
| U0436 stato gamba | open | APERTO · in corso | OK |
| U0437 righe di chiusura | nessuna oggi | — | NC |
| U0438 Cash out | disabilitato (feed fermo 26 s) | disabilitato | OK (non cliccato) |
| U0439 risultati 1T/2T | `meta` | «2-3», «0-0» | NC: non confrontati con `matches` (partite in corso) |
| U0440 P&L partita | in corso | «— in corso · rischio 47,00 €» | OK |
| U0441-U0442 attività, toast | — | — | NC |
| U0443-U0445 Missione: obiettivo, eventi, target/partita | 100; 150 = `events_total`; 0,76 · 133 | idem (= KPI U0424: coerente) | OK (×3) |
| U0446 missioni attive/totali | `get_omega_missions` | «0 / 0» | NC: non ricalcolato |
| U0447 «di quel totale» | 0 | +0,00 € | OK |
| U0448-U0458 missioni (azioni, card) | nessuna missione attiva / scritture | — | NC (×11) |
| U0459 Manuale: eventi | 150 | «— scegli evento (150) —» | OK |
| U0460-U0464 book/ordine | richiede `omega_request` (scrittura) | — | NC (×5) |
| U0465 ultime richieste | `get_omega_manual_requests` | 10/09 15:29-15:30 ESEGUITA | OK |
| U0466 calendario | SQL per giorno (paper, giorno di piazzamento Roma): 01/09 0.95, 09/09 54.44, 10/09 4.73, 11/09 0.52, 12/09 −14.22, 13/09 −17.19, 15/09 0.53, 17/09 3.80, 24/09 1.90 | idem | OK |
| U0467 Performance | P&L 35.46; giornate 7/2 (10 con attività); 72V·8P; 80 regolate · 84 piazzate; PF, expectancy 35.46/80 = 0.44; max DD 60.64→29.23 = 31.41, in corso 25.18; best 54.44 (09/09), worst −17.19 (13/09); serie 4+/2−; liability max 625.94; breakdown gamba 50.64+13.84−29.02 = 35.46; origine 34.39+1.07 | identici; **commissioni 10,69 €** vs ricalcolo 10,68 € (stima per giorno×mercato `net·c/(1−c)`, nessuna `commission_paid` scritta: somma di arrotondamenti) | OK (±0,01) — nota: la commissione è una STIMA, a video «già dedotte» senza dirlo |
| U0468 dettaglio giorno | 26/09: 4 trade, liability 274 | «4 trade · 4 ancora vivi · liability piazzata 274,00 €» | OK |

**Omega: 65 campi — OK 40 · KO 2 · NC 23.**

## 7. Safe Strategy `/safe-strategy` (U0469-U0508)

Istante: `get_safe_state` chiamata con `{}` (`lib/safeBot.ts:1100`) → `aggregates.mode = null`. SQL: paper regolato
**−47.83**, live regolato **2.58**, 2 aperte paper (98+108 = 206).

| id | atteso | visto | esito |
|---|---|---|---|
| U0469-U0470 testata, salute | running, battito 19 s, ⚽17 🎾15 | «BOT IN CORSA», «feed vivo (17 s) ⚽ 17 · 🎾 15» | OK (×2) |
| U0471 canale locale | badge come Omega/Mike | nessun uso di `canaleLocale` in `pages/SafeStrategy.tsx` (grep) | **KO** (candidato §9-bis n.4 confermato dal codice) |
| U0472 PAPER/LIVE | paper | PAPER | OK |
| U0473 Avvia/Ferma | SCRIVE | — | NC |
| U0474 Parametri | = U0268 | — | OK |
| U0475 radar localStorage | bot presente | — | NC |
| U0476-U0478 banner, disallineamento, soldi veri | `strategy_modes` tutte paper | banner PAPER, nessun disallineamento, nessuna riga «SOLDI VERI» | OK (×3) |
| U0479 strategie | 6 strategie, `variants`+modello+a mano, tutte `prova` | 5 calcio + 1 tennis «in esecuzione · prova», P&L «oggi —» (0 regolate oggi) | OK — candidato §9-bis n.1 (P&L per strategia sempre «—») NON confermabile oggi: nessuna regolazione |
| U0480 esecuzione | `betfair_live_heartbeat.mode` = LIVE+PAPER, battito 7 s | «REST … runner in streaming (LIVE+PAPER) · battito 7 s fa · 4 partite agganciate» | OK |
| U0481 barra giornata | paper: realizzato 0; **totale storico paper −47,83** | «realizzato oggi +0,00 € · totale storico **−45,25 €**» | **KO GRAVE (paper+live sommati)**: −45,25 = −47,83 (paper) + 2,58 (live) |
| U0482 segnali attivi | calcolo nel browser | 0 · 0 | NC (valutatore del browser non ricalcolato) |
| U0483 trade aperti | 2 | 2 · «1 coperte in parte» | OK |
| U0484 P&L oggi · PAPER | 0 | +0,00 € | OK — **latente**: stessa fonte senza modalità di U0485 (oggi nessuna riga live) |
| U0485 P&L totale · PAPER | `realized_paper_total` **−47,83** (anche nella RPC) | «P&L totale · PAPER **−45,25 €**» = `realized_total` (tutte le modalità) | **KO GRAVE**: `pages/SafeStrategy.tsx:410` usa `agg.realized_total` mentre la RPC fornisce `realized_paper_total`/`realized_live_total`; il tooltip dice «paper e live … non si sommano» |
| U0486 liability aperta | 206 | 206,00 € su 2 posizioni | OK |
| U0487 P&L bloccato | — | — | NC |
| U0488 partite monitorate | payload 17+15 | 32 (⚽17 · 🎾15 · 0 caricate) = chip salute | OK |
| U0489 pannello rischio | 206 impegnato; cap 0 → «—»; stop −50 (`risk.daily_loss_stop`) | «206,00 € impegnato oggi / cap — · stop ok (−50,00 €)» | OK |
| U0490 contatori tab | 0/0 | Calcio (0) Tennis (0) | OK |
| U0491-U0496 segnali/opportunità/monitor | 0 righe in questo istante | stati vuoti | NC (×6) |
| U0497-U0500 tab Trade | 2 posizioni, investito 2+2, responsabilità 108+98; feed con `lay/back = null` per le selezioni «Any Other Home/Away Win» (verificato nel `payload` di `safe_strategy_scan`) | «Operazioni 2 · Investito 4,00 € · Responsabilità 206,00 € · Se chiudo ora — · 2 posizioni non valutabili (nessun prezzo nel feed)»; righe 108,00 / 98,00 | OK (×4) |
| U0501-U0505 dettaglio posizioni, cash out | non aperti / scritture | — | NC (×5) |
| U0506 filtro sport | tutti | tutti | OK |
| U0507 Storico | `get_safe_daily(p_mode=null)` = TUTTE le modalità (funzione: «nessun valore = tutte») | «P&L periodo −45,25 €» = paper+live | **KO GRAVE**: Omega e Mike aprono lo Storico nella modalità corrente del bot, Safe somma paper e live |
| U0508 attività | 80 righe | 80 | NC (contenuto non ricalcolato) |

**Safe: 40 campi — OK 20 · KO 4 · NC 16.**

## 8. Mike `/mike` (U0509-U0542)

SQL `mike_trades`: paper regolato 8.14, live 2.15, 2 aperte paper liability 5+5.

| id | atteso | visto | esito |
|---|---|---|---|
| U0509, U0511-U0512, U0514 | running, feed, PAPER, banner | idem | OK (×4) |
| U0510 canale locale | — | spento nel banco | NC |
| U0513 Parametri | = U0269 | — | OK |
| U0515-U0516 allarmi | nessuna partita nell'altra modalità; live spento | nessun allarme | OK (×2) |
| U0517 barra giornata | 2 partite, 2 operazioni, 0V 0P, liability 10, storico paper **8,14** | idem | OK (Mike NON somma il live 2,15: corretto) |
| U0518-U0522 KPI | 2 seguite (2 pre, 0 live, 2 con posizione); 2 aperte; oggi 0 (stop −50); totale 8,14; liability 10 | idem | OK (×5) |
| U0523 bloccato | nessuno | «—» | OK |
| U0524 ultimo ciclo | `heartbeat` 09:45:50Z | «11:45:50 · feed 14 s fa» | OK |
| U0525-U0526 sezioni, card | pre 2 / live 0; Badalona–Granada KO 12:00 | idem | OK (×2) |
| U0527 avvisi | nessuno presente | — | NC |
| U0528 P(4) mercato | calcolo del servizio | 18,3 % («nessun modello per questa lega») | OK (fonte servizio) |
| U0529 quote | frame del servizio | U3.5 1,69/1,73; O4.5 4,20/4,50; U4.5 1,30/1,33 | OK (fonte servizio) |
| U0530 meta | ingresso = `price` 1.6 | «ingresso @ 1,60 · ciclo 1 di 10» | OK |
| U0531 «se chiudo ora» | ricalcolo: back 5@1.60 chiuso lay @1.73 → 5·1.60/1.73 = 4.624; −0,376 in entrambi gli esiti | −0,38 € | OK |
| U0532 ordini sul book | nessuno pendente | «—» | OK |
| U0533 P&L per gol | 0-3: 5·0,60·0,95 = +2,85; 4+: −5,00; liability 5 | idem | OK |
| U0534 cash out | −0,38 netto, soglia 5 % | «−0,38 € (in perdita · … sopra 5,0 %)» | OK |
| U0535 pulsanti | SCRIVONO | — | NC |
| U0536 proposta d'uscita + APPROVA | con uscite MANUALI di default (DB: `uscite_automatiche=false`) ogni uscita è una proposta | assente su `/mike`: `uscita_proposta`/`approva_uscita` solo in `components/controlroom/PropostaUscitaMike.tsx` (grep) | **KO** (reperto inventario confermato): dalla pagina Mike il trader non può firmare le uscite |
| U0537 Operazioni · Totali | «Se chiudo ora» delle 2 posizioni: −0,38 € + seconda | «Se chiudo ora · PAPER —» | **KO (coerenza)**: come U0427, il totale è il bloccato, la card dice −0,38 € |
| U0538-U0539 equity, tab Pre/Live | nessuna regolata; 2 / 0 | idem | OK (×2) |
| U0540 attività, U0542 toast | — | — | NC (×2) |
| U0541 Storico | SQL (paper, 01-26/09): P&L 8.14; giornate 5/1 su 7; max DD 2.16→−17.90 = 20.06; best 11.29 (13/09); worst −20.06 (12/09); liability max 10.35; regolate 242, piazzate 244; **V=148, P=91, 3 a zero** (2 `won` con P&L totale 0.00: id 527, 4762; 1 void) | P&L, giornate, DD, best/worst, liability, 242/244 identici; **«150V · 91P · 1 void», win rate 62,2 %** | **KO lieve (definizione)**: le posizioni a P&L totale 0 (scratch) sono contate «V» benché il tooltip dica «V = P&L totale positivo»; con la definizione dichiarata 148/239 = 61,9 % |

**Mike: 34 campi — OK 26 · KO 3 · NC 5.**

---

## 9. Conteggio complessivo (311 campi del perimetro)

| pagina | campi | OK | KO | NC |
|---|---|---|---|---|
| Dashboard (U0001-U0108) | 108 | 82 | 11 | 15 |
| Analytics/Reportistiche (U0109-U0139) | 31 | 13 | 7 | 11 |
| Report personale (U0140-U0158) | 19 | 5 | 0 | 14 |
| Fogli parametri (U0268-U0272) | 5 | 3 | 0 | 2 |
| Live P&L (U0273-U0281) | 9 | 7 | 2 | 0 |
| Omega (U0404-U0468) | 65 | 40 | 2 | 23 |
| Safe Strategy (U0469-U0508) | 40 | 20 | 4 | 16 |
| Mike (U0509-U0542) | 34 | 26 | 3 | 5 |
| **Totale** | **311** | **196** | **29** | **86** |

## 10. KO in ordine di gravità (NESSUNO corretto)

1. **Safe: paper e live sommati sotto etichetta PAPER** (U0481, U0485, U0507). Evidenza: `get_safe_state {}` →
   `aggregates = {realized_total: −45.25, realized_paper_total: −47.83, realized_live_total: 2.58, mode: null}`;
   SQL `safe_strategy_trades` paper −47.83 / live 2.58. File: `frontend/src/lib/safeBot.ts:1100` (nessun `p_mode`),
   `frontend/src/pages/SafeStrategy.tsx:410` (`agg.realized_total`); Storico: `get_safe_daily(p_mode=null)` = tutte.
   Riproduzione: aprire `/safe-strategy` → tile «P&L totale · PAPER». Latente: `realized_today`, `open_liability` stessa
   fonte. Omega: `omega_aggregates_sql` senza filtro `mode` (latente, oggi solo righe paper).
2. **Analytics › Performance Motori e Decisioni non caricabili** (U0109, U0111-U0113, U0116-U0118):
   `get_analytics_filters` 37,8 s misurati, `get_analytics`, `get_decisions_filters`, `get_decisions` → «canceling statement
   due to statement timeout» (timeout ruolo `authenticated` = 8 s); la pagina mostra poi «Nessun segnale settlato per
   questi filtri» (stato vuoto fuorviante). Atteso U0109: 1.217.790.
3. **Studio Ritardi / Direzione «ritardo» / Stagioni in timeout sulle leghe grandi** (U0043, U0055, U0105):
   `get_market_delays(667,…,'all')` 21,8 s, `(45,…)` 16,2 s; `get_league_seasons(667)` in timeout. Il trader vede
   «Errore: canceling statement…» sulla vista di default.
4. **Live P&L: posizione fantasma e modalità mischiate** (U0275, U0281): riga `betfair_live_positions` 14265 (live,
   10/07, mercato già regolato) mostrata come «1 posizioni aperte · rischio €4.40» con qualunque filtro; tabella
   tennis con righe paper sotto «Mode = live».
5. **Mike: proposta d'uscita non firmabile da `/mike`** (U0536) con uscite manuali di default.
6. **Direzione: «quota» del bookmaker presentata come quota** (U0100): `analytics_bets.odds_betfair` quasi sempre NULL
   (per giorno dal 16/09: 0/5827, 380/3720, 0, 0, 0, 0, 0, 60/2121, 0, 0), il «valore» si giudica su `odds_book`
   mentre lo stesso pannello mostra le quote Betfair (1.36 book vs 1.42 Betfair back su Under 3.5 di A).
7. **ML: due verdetti opposti nello stesso riquadro** (U0088): «Previsione» (probabilità calibrate) vs «classe
   prevista» (voto dei modelli grezzi) — A `target_btts` No 51,74 % vs Sì 75 %.
8. **Totali «Se chiudo ora» = bloccato, non chiusura a mercato** (U0427 Omega +0,00 € vs righe −0,50/−2,20;
   U0537 Mike «—» vs card −0,38 €).
9. **TacticAI «Esito reale» mai valorizzato in produzione** (U0081): `tactical_engine/serving.py:187-188`.
10. **Etichette/definizioni**: Omega «storico 109 partite» = aperture (100 partite reali, U0426); Mike win rate con
    scratch contati «V» (U0541, 62,2 % vs 61,9 %); Safe senza badge canale locale (U0471).
11. **Casi limite di resa**: gol previsti null → «0» (U0022), `played=0` → «NaN» (U0026), minuti null → 0 (U0029),
    date ISO grezze nello Studio Ritardi (U0056), lista del giorno con partite del giorno dopo a «00:00/01:00» senza
    data (U0011).

**Reperto dati fuori campo (alimenta Analytics/Reportistiche):** `analytics_signals` ha righe con `kickoff` diverso da
`fixture_predictions.fixture_date` per la stessa partita: **25 partite / 546 righe** negli ultimi 60 giorni (es. 1499655:
Poisson 1 riga a 25/09 23:00Z + 15 righe a 26/09 20:00Z, `settled=true` con kickoff FUTURO; 90 righe «settled» con
kickoff > adesso). Oggi il giorno Roma coincide per le 4 partite viste, ma il dato è incoerente e duplicato.

## 11. Freschezza (R5) e rinvii

- Poisson 26/09: 790/1186 partite, `generated_at` 07:50-07:59Z; ML ancora in scrittura alle 09:54Z (834 righe);
  **TacticAI 26/09: 0** (ultimo `generated_at` 25/09 09:33Z; le 8 partite di oggi con TacticAI hanno payload del
  13-23/09 e sono marcate «oltre 36 h»); `engine_signals` max `run_date` 25/09 (toggle «Match Betfair» vuoto oggi);
  pagella 25/09 09:52Z. La run giornaliera risulta in corso: **da rimisurare a fine run** (U0006, U0077 del giorno).
- Quote Betfair (U0106-U0107): nessuna età a video (cattura 25/09 17:28Z per A).
- Registrazioni replay (U0136): ultima UPLOADED 01/09.

## 12. Coerenza fra pagine

- Salute feed: ⚽17 · 🎾15/16 su Omega/Mike/Safe negli istanti dei rispettivi render = `safe_strategy_status.payload`; Safe
  «Partite monitorate 32» = chip. OK.
- Target Omega: KPI «0,76 €/partita» = tab Missione «0,76 € dal servizio · 133». OK.
- Stato bot: IN CORSA/PAPER su tutte e tre = `*_control`. OK.
- P&L di oggi: 0 su Omega, Mike, Safe, Live P&L (runner) — coerente; ma Live P&L non include per progetto il paper dei bot.
- P&L storico: Omega −44,64 (solo paper, nessun live), Mike 8,14 (solo paper, live 2,15 escluso), **Safe −45,25 (paper+live)** → le tre pagine usano regole diverse (KO 1).

## 13. File creati (worktree, NON committati)

- `AUDIT_2026-09-25/E2E_FASE3_PAGINE_SESSIONE_B_2026-09-26.md` (questo referto)
- `AUDIT_2026-09-25/e2e_fase3_sessB/verifica_modelli.py`, `verifica_direzione.py`, `vlog.py`, `estrai.py`
- `AUDIT_2026-09-25/e2e_fase3_sessB/evidenze/` (86 file: testo visibile di ogni pagina/tab/pannello, `*_guard.json`,
  `modelli.json`, `direzione.json`, log delle 3 esecuzioni vitest)
- `frontend/src/certification/sessB/clientB.ts`, `util_base.tsx`, `util.tsx`, `dashboard.cert.test.tsx`,
  `pagine.cert.test.tsx`, `extra.cert.test.tsx`, `safetrade.cert.test.tsx`, `sonda_lista.mjs` (girano solo con
  `vitest.cert.config.ts`: con la config normale `npx vitest run src/certification/sessB/` → 4 file / 20 test
  **skipped**, e `clientB` non legge il `.env` senza `CERT_RUN=1`)
- junction `frontend/node_modules` → checkout principale (rimuovere con `cmd /c rmdir`, MAI `git worktree remove --force`)

## 14. Comandi eseguiti (tutti in sola lettura)

- `git fetch`, `git log` (worktree) — ok.
- `netstat` (porte 47330-47338 in ascolto: app accesa) — ok.
- Supabase MCP `execute_sql`: ~60 SELECT su tabelle e `pg_proc`/`pg_roles`/`pg_stat_activity`, più chiamate a
  funzioni STABLE (`get_betfair_fixtures`, `get_market_delays`, `get_market_frequency`, `get_analytics_filters`) — ok;
  una sonda è andata in timeout lato MCP (lega 10 + 667 insieme), nessun effetto.
- `node sonda_lista.mjs 2026-09-26` (5×3 SELECT) — ok.
- `.venv python verifica_modelli.py …` (solo GET PostgREST, 4 GET `poisson_calibration`, 0 richieste non-GET nel log
  httpx) — ok; `verifica_direzione.py …` (GET + POST `rpc/get_direction`, funzione STABLE) — ok.
- `npx vitest run --config vitest.cert.config.ts` su `dashboard` (7 test verdi, 722 s), `pagine` (7 verdi, 610 s),
  `extra` (5 verdi, 164 s), `safetrade` (1 verde, 49 s): **blocked = [], wsSends = [] in tutte**.

**Conferma: nessuna scrittura sul DB, nessun comando ai bot, nessun processo del progetto avviato o fermato, nessun
commit.** (I bot sono stati accesi in paper dall'utente durante la misura, alle ~09:10 UTC: non da questo delegato.)
