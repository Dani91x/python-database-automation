# LIVE_MARKET_TYPES e BETA_DEFAULT — due residui tecnici (25/09/2026)

Delegato del coordinatore, worktree `agent-ae644388fb18920f7`, base `099412c`. Nessun commit,
nessun `git add -A`, nessun push, nessuna scrittura sul DB. Sul punto 2 sono state fatte letture
in SOLA LETTURA sul DB vero (dichiarate, vedi §2.2): ~299 richieste (`raccogli.py`, senza le 17
sonde esplorative del referto originale, non necessarie per ricalcolare beta).

## 1. `LIVE_MARKET_TYPES` (whitelist mercati per evento, runner calcio)

### 1.1 Tabella bot calcio -> market type (fonte primaria: `registro_bot.py`)

`Betfair/stream/backtest/registro_bot.py` (`BotRegistrato.mercati`) e' la fonte autorevole: e'
la stessa che il test di contratto (`test_registro_bot_2026_09_16.py`) verifica contro i moduli
di produzione veri, quindi non puo' andare fuori sincrono con silenzio.

| bot | mercati (`registro_bot.py`) | riga |
|---|---|---|
| mike | OVER_UNDER_35, OVER_UNDER_45 | :119 |
| omega | CORRECT_SCORE, HALF_TIME_SCORE, MATCH_ODDS | :130 |
| safe_base | MATCH_ODDS, CORRECT_SCORE | :141 |
| safe_esatto | CORRECT_SCORE | :152 |
| safe_punta | MATCH_ODDS | :163 |
| scalper_calcio | MATCH_ODDS, OVER_UNDER_15, OVER_UNDER_25, OVER_UNDER_35 | :194 |

Conferme nel codice vero (non solo nel registro):
- **Omega**: `omega_service.py:1734-1735` — gamba `ht_cs` = HALF_TIME_SCORE, `ft_cs` = CORRECT_SCORE.
  Con `strategy_version>=3` (`v3_on`, riga 1810; V3 e' il default da mandato utente) la riga 1840
  sostituisce ENTRAMBE le gambe con CORRECT_SCORE — HALF_TIME_SCORE resta comunque necessario come
  ripiego V2 (non spento nel codice, solo bypassato se v3_on). MATCH_ODDS seleziona la favorita
  pre-KO (`omega_engine.py`, filtro `market_type=="MATCH_ODDS"`).
- **Safe**: `safe_strategy/certificazione.py:278,607,844` verifica ESATTAMENTE MATCH_ODDS
  (base/punta) e CORRECT_SCORE (esatto) come criterio di accettazione del replay — combacia col
  registro.
- **Mike**: `mike/config.py:17-18` OU35/OU45; `mike/tools/replay_registrazioni.py:463` nota che gli
  ALTRI mercati (MATCH_ODDS) servono solo allo SCANNER, non a Mike.
- **Scalper**: `scalper/run_scalper_live.py:70-73`, `scalper/scalper_session.py:89` — MATCH_ODDS +
  OU 1.5/2.5/3.5, non oltre.
- **xhedge** (`Betfair/stream/trading/xhedge.py:26-29,212-215`, `stream/xhedge_worker.py:39-42`,
  copertura incrociata su ordini aperti, non un bot proprio): MATCH_ODDS, OVER_UNDER_* (regex
  `OVER_UNDER_(\d+)`), BOTH_TEAMS_TO_SCORE, CORRECT_SCORE.

**Seconda fonte** (dati che Safe/Omega CONSULTANO in decisione — non un bot nel registro, e'
lo scanner condiviso, `NON_BOT` in `registro_bot.py`: "pubblica i fatti, non piazza mai un
ordine"): `Betfair/safe_strategy/scanner.py:44-48`

```python
OU_MARKET_TYPES = ("OVER_UNDER_05","OVER_UNDER_15","OVER_UNDER_25","OVER_UNDER_35",
                    "OVER_UNDER_45","OVER_UNDER_55","OVER_UNDER_65","OVER_UNDER_75")
BTTS_MARKET_TYPE = "BOTH_TEAMS_TO_SCORE"
HT_RESULT_MARKET_TYPE = "HALF_TIME"
OPP_MARKET_TYPES = OU_MARKET_TYPES + (BTTS_MARKET_TYPE, HT_RESULT_MARKET_TYPE)
```

Queste linee alimentano `opportunity.py`/`anomaly.py` (segnali "opportunita'" e controincrocio
contro l'atlante hazard di Safe/Omega — §4.6 di `VALIDAZIONE_HAZARD.md`), quindi non sono rumore
anche se non hanno una riga propria nel registro.

`OVER_UNDER_85`: **non trovato in nessun consumo di produzione** (una sola menzione descrittiva
in un commento di `omega_engine.py:888`). Escluso dalla whitelist proposta.

### 1.2 Unione proposta (13 tipi)

```
MATCH_ODDS, CORRECT_SCORE, HALF_TIME_SCORE, HALF_TIME, BOTH_TEAMS_TO_SCORE,
OVER_UNDER_05, OVER_UNDER_15, OVER_UNDER_25, OVER_UNDER_35, OVER_UNDER_45,
OVER_UNDER_55, OVER_UNDER_65, OVER_UNDER_75
```

### 1.3 Misura sulle registrazioni `_live_raw/*`

Script (`.raw.jsonl` nativo Betfair, campo `marketDefinition.marketType`, un mercato contato una
volta per evento): 40 eventi con dati su 65 cartelle.

| | media mercati/evento |
|---|---|
| oggi (nessuna whitelist, tutto l'evento) | **19,8** |
| con la whitelist proposta (13 tipi) | **12,0** |

Riduzione ~39%. Col tetto duro `HARD_MARKET_CAP=180`: oggi ~9 eventi seguibili in parallelo su
una connessione (180/19,8), con la whitelist ~15 (180/12,0).

Distribuzione dei market type visti nel campione (n. di eventi in cui compaiono, su 40):
MATCH_ODDS, HALF_TIME_FULL_TIME, OVER_UNDER_45, CORRECT_SCORE, OVER_UNDER_85, OVER_UNDER_55,
DOUBLE_CHANCE, TEAM_A_1, TEAM_B_1, OVER_UNDER_65, OVER_UNDER_75 = 39/40; OVER_UNDER_25,
OVER_UNDER_35 = 38/40; BOTH_TEAMS_TO_SCORE = 37/40; OVER_UNDER_15 = 36/40; HALF_TIME,
FIRST_HALF_GOALS_25, HALF_TIME_SCORE = 34/40; FIRST_HALF_GOALS_15 = 32/40; OVER_UNDER_05,
FIRST_HALF_GOALS_05 = 30/28; TO_QUALIFY = 11; FIRST_GOAL_SCORER = 8; EXTRA_TIME = 1.
Fuori whitelist e MAI usati da un bot/scanner di produzione: HALF_TIME_FULL_TIME, OVER_UNDER_85,
DOUBLE_CHANCE, TEAM_A_1, TEAM_B_1, FIRST_HALF_GOALS_*, TO_QUALIFY, FIRST_GOAL_SCORER, EXTRA_TIME.

### 1.4 Valore proposto e dove sta

`LIVE_MARKET_TYPES` **resta vuota di default** (nessuna modifica di comportamento: il `.env` lo
tocca il coordinatore). Il valore e' documentato:
- in un commento sopra la costante in `Betfair/stream/config_stream.py`;
- in una costante eseguibile separata, `LIVE_MARKET_TYPES_PROPOSTA` (stesso file), che NON
  alimenta `LIVE_MARKET_TYPES` e non cambia il runner — serve solo perche' un test possa
  falsificarla.

Valore proposto per il `.env` del checkout principale, quando l'utente decide:
```
LIVE_MARKET_TYPES=MATCH_ODDS,CORRECT_SCORE,HALF_TIME_SCORE,HALF_TIME,BOTH_TEAMS_TO_SCORE,OVER_UNDER_05,OVER_UNDER_15,OVER_UNDER_25,OVER_UNDER_35,OVER_UNDER_45,OVER_UNDER_55,OVER_UNDER_65,OVER_UNDER_75
```

**Da portare all'utente (decisione, non presa qui)**: attivare la whitelist riduce ANCHE la
registrazione raw per il Replay (niente piu' DOUBLE_CHANCE, HALF_TIME_FULL_TIME,
FIRST_HALF_GOALS_*, TO_QUALIFY, FIRST_GOAL_SCORER, EXTRA_TIME, OVER_UNDER_85 nelle registrazioni
FUTURE): nessun bot li legge oggi, ma un bot nuovo che li usasse non li troverebbe piu' nel raw
finche' la whitelist non venisse riaperta.

### 1.5 Test e falsificazione

`Betfair/stream/tests/test_live_market_types_2026_09_25.py` (nuovo, 4 test):
- l'unione dei `mercati` di tutti i bot `sport=="calcio"` in `registro_bot.REGISTRO` e' un
  sottoinsieme di `LIVE_MARKET_TYPES_PROPOSTA`;
- l'unione di `safe_strategy.scanner.OPP_MARKET_TYPES` idem;
- `LIVE_MARKET_TYPES_PROPOSTA` non e' vuota e `LIVE_MARKET_TYPES` (quella USATA) resta vuota
  (il default non cambia);
- falsificazione: tolto CORRECT_SCORE dalla whitelist proposta, il test diventa rosso (omega,
  safe_base, safe_esatto lo usano). Verificato a mano (mutazione + pytest + ripristino dal testo
  in memoria, hash confrontato): **rosso confermato**, poi ripristinato.

Esecuzione: `4 passed` (sandbox `SUPABASE_URL=http://127.0.0.1:9` ecc.).

## 2. `BETA_DEFAULT` dell'atlante v4 vs eta

### 2.1 Come si stima beta (letto da `validazione_hazard/{banco,candidati,forza}.py`)

- `forza.py::lambda_prepartita(partite, eta, rientro, alfa_lega)`: Poisson-Elo cronologico (rating
  attacco/difesa per squadra, aggiornati con lr=`eta`; `rientro` scala i rating al cambio
  stagione). E' il PROXY dei lambda pre-partita (nessun DB in piu': solo storico gol).
- `banco.py::scegli_forza(partite, ultima_stagione)`: griglia FISSA
  `eta in (0.005, 0.01, 0.015, 0.02, 0.035, 0.05)` x `rientro in (0.7, 0.8, 0.9, 1.0)`, sceglie la
  coppia a MASSIMA verosimiglianza media di Poisson sulle partite fino a `ultima_stagione`
  (=2023 in fase di validazione). Risultato scritto in `risultati_validazione.json["forza"]`.
- `candidati.py` (A5): con l'eta scelta, calcola `lambda_tot` per ogni stato e stima **beta per
  orizzonte** (2' e 3') con `scipy.optimize` a massima verosimiglianza, come esponente del
  moltiplicatore `(lambda_tot / lambda_medio_lega) ** beta` sull'hazard base. Scritto in
  `risultati_validazione.json["catena"][passo="A5"]["esiti"][0]["info"]["beta"]`.
- **Beta dipende dall'eta**: l'eta fissa i lambda del proxy, beta e' poi la MLE del moltiplicatore
  CON QUEI lambda — cambiare l'eta senza ristimare beta produce una coppia scollegata.

### 2.2 Cosa c'era nel repo e perche' non bastava

Il commit `7211ac2` (che ha introdotto `atlante_v4.py`) porta anche
`AUDIT_2026-09-25/validazione_hazard/risultati_validazione.json` e `risultati_test.json`, ma
questi due file **erano l'esito di una corsa `--fumo`** (1 partita ogni 10: `banco.py` linea 52
`FUMO = {"attivo": False}` col commento "prova veloce di tutto il percorso"), scritta per errore
sul percorso di OUTPUT DI DEFAULT della corsa completa (`--fumo` e la corsa vera scrivono nello
stesso file se non si passa `--out` diverso).

Prove misurate (prima di correggere):
- `risultati_validazione.json` committato: `n_partite=439, n_stati=41877` — contro le
  **"4.396 partite, 420.150 stati"** dichiarate nel referto originale
  (`VALIDAZIONE_HAZARD.md` §3): **~1/10**, la firma esatta di `--fumo`.
- Con questo campione ridotto, il passo A5 (forza) **non entrava nella catena greedy**
  (`entra: False`, delta_ll con IC che attraversa lo zero) — l'opposto di quanto riportato nel
  referto ("+ A5 forza pre-partita (β = 0,63) — vince").
- `risultati_test.json` committato: `n_partite=107` (pulito) contro le **"1.021 partite"** del
  referto — stessa firma.
- `forza.scelta` nel json committato: `{"eta": 0.035, "rientro": 1.0}`. Il commento in
  `atlante_v4.py` citava proprio questo artefatto per `FORZA_ETA=0.035` — ma il `VALIDAZIONE_HAZARD.md`
  originale, in prosa (§2, proxy dei lambda), dice **"η=0,015 e rientro=1,0"**: il codice e il json
  committato erano allineati fra loro (entrambi 0,035) ma DISALLINEATI dal referto in prosa e,
  come misurato sotto, dal vero banco completo.

Per il §7 del brief ("se l'artefatto non basta, ricostruisci la cache e ristima"): l'artefatto
committato NON bastava (era la corsa sbagliata). Ricostruito.

### 2.3 Ricostruzione (AMMESSA, dichiarata: letture in sola lettura sul DB vero)

1. `python -m Betfair.stream.scalper.validazione_hazard.raccogli --env <.env principale>`:
   285 richieste, 180.256 righe, 133,0 s (leghe grandi + 395/833/834).
2. `... raccogli --env <.env principale> --supplemento`: 14 richieste, 3.459 righe, 4,3 s (leghe
   306, 835). Totale **299 richieste** in sola lettura (sotto il tetto ~400 del banco).
3. `python -m Betfair.stream.scalper.validazione_hazard.banco --da-cache --fase validazione`
   (corsa COMPLETA, senza `--fumo`): 679,0 s (~11 min, di cui 463,7 s per B1 con arresto anticipato
   a 213/206 giri — combacia esattamente con `taratura_b1.json` gia' committato, riusato).

Risultato (`risultati_validazione.json`, riscritto sul posto, incluso nel diff):
- `metriche.n_partite = 4396`, `metriche.n_stati = 420150` — **combaciano esattamente** con
  "4.396 partite, 420.150 stati" del referto originale: la ricostruzione e' fedele alla corsa
  vera, non un'altra corsa smoke.
- `forza.scelta = {"eta": 0.015, "rientro": 1.0}` (non 0,035). Combacia con la prosa del referto
  originale (§2: "η=0,015 e rientro=1,0").
- Passo A5 della catena: `entra: True`, `delta_ll_vs_corrente = [-0.00075421, -0.00100161,
  -0.00049656]` — arrotondato: **-0,00075 [-0,00100, -0,00050]**, IDENTICO al valore pubblicato
  nel referto originale ("−0,00075 [−0,00100, −0,00050]"): conferma indipendente, bit-per-bit
  compatibile, che questa e' la stessa corsa che ha prodotto i numeri del referto.
- **`beta = {"2": 0.6281010608081934, "3": 0.6265133964337202}`** — non 0,612/0,610.

### 2.4 Valore prima/dopo, con fonte

| costante | prima (nel repo) | dopo (misurato, 25/09) | fonte |
|---|---|---|---|
| `FORZA_ETA` | 0,035 | **0,015** | `risultati_validazione.json["forza"]["scelta"]["eta"]`, corsa completa |
| `FORZA_RIENTRO` | 1,0 | 1,0 (invariato) | idem |
| `BETA_DEFAULT[2]` | 0,612 | **0,628** | `risultati_validazione.json["catena"][A5]["esiti"][0]["info"]["beta"]["2"]` |
| `BETA_DEFAULT[3]` | 0,610 | **0,627** | idem `["3"]` (0,6265, arrotondato a 3 decimali) |

Applicato in `Betfair/stream/scalper/atlante_v4.py` (righe 73-94), con commento che cita il
percorso esatto nel json e spiega l'errore precedente (corsa `--fumo` sovrascritta sul path di
output di default).

### 2.5 Test rilanciati (come richiesto: parita' col banco deve reggere)

| suite | esito |
|---|---|
| `test_atlante_v4_2026_09_25.py` | verde |
| `test_atlante_v4_forza_id_squadra_2026_09_25.py` (aggiornata: `eta=0.035`→`0.015` nei due punti che citavano il valore letterale del banco, righe 133 e 457) | verde |
| `test_genera_atlante_2026_09_24.py` | verde |
| `test_atlante_a_domanda_2026_09_25.py` | verde |
| `test_validazione_hazard_2026_09_25.py` | verde |
| `safe_strategy/tests/test_atlante_note_livello_2026_09_25.py` | verde |
| `test_beta_forza_da_artefatto_2026_09_25.py` (nuovo, 5 test: legge l'artefatto e verifica che `FORZA_ETA`/`BETA_DEFAULT` combacino) | verde |

Totale: **106 passed** (esecuzione unica, sandbox).

**Nuovo test + falsificazione**: `test_beta_forza_da_artefatto_2026_09_25.py` legge
`risultati_validazione.json` e confronta `V4.FORZA_ETA`/`V4.BETA_DEFAULT` col contenuto.
Falsificazione VERIFICATA A MANO (mutazione + pytest + ripristino dal testo in memoria):
- `BETA_DEFAULT={2:0.612,3:0.610}` (vecchio valore) -> rosso (`0.0161 < 0.0005` falso).
- `FORZA_ETA=0.035` (vecchio valore) -> rosso, e in cascata **5 test cadono** anche nella suite di
  parita' esistente (`test_atlante_v4_forza_id_squadra_2026_09_25.py`: `test_parita_lambda_forza_col_proxy_del_banco`,
  `test_parita_p_astar_col_candidato_validato`, `test_motivi_della_forza_non_usata`,
  `test_blocco_forza_nel_file_live_piccolo`, oltre al nuovo) — prova indipendente che 0,035 e'
  incompatibile con la produzione a valle (i lambda scendono fuori tolleranza: diff 0,42 contro
  soglia 1e-6). Ripristinato tutto ai valori corretti, suite verde di nuovo.

### 2.6 Non verificato

- Non ho rilanciato la fase `test` del banco (addestra ≤2024, valuta 2025: B1 da solo richiede
  17-48 min in piu' secondo il referto originale) — non necessaria per allineare le costanti di
  produzione (che sono "congelate" in fase di validazione, §3 del referto originale), ma se si
  vuole anche `risultati_test.json` corretto (oggi ancora la versione `--fumo`, 107 partite invece
  di 1.021) va rilanciato con lo stesso comando (`--fase test`, usando la cache gia' scaricata).
- Le 17 richieste "sonde" del referto originale (colonne/filtri/copertura) non sono state rifatte:
  non servono a ricalcolare beta, solo ai reperti descrittivi del referto di validazione (gia'
  scritti in `VALIDAZIONE_HAZARD.md`).
- Il modulo v4 resta NON collegato ai bot: questa correzione tocca solo le costanti congelate,
  non l'attivazione.

## 3. Consegna

- Referto: questo file.
- `git diff` (tracked, incl. i due test nuovi via `git add -N`, nessun contenuto in stage):
  `AUDIT_2026-09-25/lmt_beta.patch`.
- File toccati: `Betfair/stream/config_stream.py`, `Betfair/stream/scalper/atlante_v4.py`,
  `Betfair/stream/tests/test_atlante_v4_forza_id_squadra_2026_09_25.py`,
  `AUDIT_2026-09-25/validazione_hazard/risultati_validazione.json` (riscritto dalla corsa
  completa del banco).
- File nuovi: `Betfair/stream/tests/test_live_market_types_2026_09_25.py`,
  `Betfair/stream/tests/test_beta_forza_da_artefatto_2026_09_25.py`.
- Nessun commit, nessun `git add -A`, nessun push, nessuna scrittura sul DB, nessun file di
  Safe/Omega/Mike toccato, nessuna soglia/strategia cambiata. Le uniche scritture sul DB vero
  sono letture GET (299 richieste, dichiarate in §2.3).
- **Nota di sessione**: durante il lavoro un fork di ricerca (Agent tool, subagent_type "fork",
  lanciato da me per il solo compito 1, in sola lettura) e' rimasto attivo per conto proprio oltre
  il previsto e ha lasciato file temporanei nel worktree condiviso (`tmp_conta_mercati_lmt.py`,
  poi `tmp_verifica_conteggio.py`); segnalato al coordinatore (SendMessage a "main"). Non
  influisce su questo referto: nessuno di quei file e' nel diff tracciato.
