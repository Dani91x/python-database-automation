# Parità coda/canale di Safe e `.env` dell'operatore (02/10/2026)

Ramo `parita-safe-env` (base master `d56bb3b`), worktree `agent-a11985ec60bea0327`.
Interprete: `.venv` del principale (percorso assoluto), nessuna junction. Registrazioni:
`<principale>\_live_raw`. Nessun ordine vero, nessuna scrittura sul DB, nessun processo
lasciato acceso. Replay lanciati uno alla volta. Il merge sul master di oggi (`5a7e076`) è
pulito (`git merge-tree`).

## 1. La causa, con le prove

### 1.1 La premessa del 01/10 era sbagliata due volte

- Il referto «PARITÀ RAGGIUNTA» del 01/10 (`AUDIT_2026-10-01/replay/safe_base_entrambi_RUNNER_MINIMI.txt`,
  riga 3) **non è lo stesso comando**: è `--scenari base --trasporto entrambi`. Lo scenario `base`
  su 35760084 non ha ordini (0 segnali nelle tre strategie), quindi coda=0 e canale=0 sono
  uguali per forza. Il profilo `rapidi` confronta invece lo scenario d'ordine `ordini-manuali`
  (`trasporto_rapido.py:91`).
- Quel delegato **non aveva un ambiente isolato**. Un worktree sotto `.claude/worktrees/` sta
  dentro l'albero del repo: `load_dotenv()` risale le cartelle e trova il `.env` del principale.
  La prova è nel suo stesso referto della coda: `safe_base_ordini_manuali_coda_RUNNER_MINIMI.txt:1`
  contiene `canale di comando ws://127.0.0.1:47331/comando/safe non disponibile (token del canale
  assente: porta giu' (fail-closed))`, e la riga finisce `error`.

### 1.2 La variabile e il punto del codice

**La variabile è `SAFE_ORDINI_VIA_CANALE=1`** del `.env` del principale. Gli altri interruttori del
`.env` sono stati letti solo per nome e valore, mai le chiavi.

1. `Betfair/stream/config_stream.py:16-17`: `load_dotenv()` al primo import. Riempie solo le
   variabili ASSENTI, e il primo import può cadere anche a metà replay.
2. `Betfair/stream/backtest/trasporto.py:100-104` (master `d56bb3b`): `contesto()` scriveva l'interruttore
   **solo per il canale**. Con `"coda"` lo lasciava all'ambiente, che vale `1` per via del `.env`.
3. `Betfair/safe_strategy/bot_service.py:870-881` (`_porta_di` / `_porta_kw`), poi
   `porta_ordini.py:134-136` (`acceso`) e `:752` (`porta_per_sport`). Con l'interruttore acceso il
   servizio passa a `execution.place` la porta VERA `PortaCanale` verso `127.0.0.1:47331`. Nel
   replay non ci sono né runner né token, quindi la porta è giù e chiude (fail-closed).
4. `execution.place` → `_place_via_canale`: l'apertura a canale giù non si manda mai sul REST
   (decisione D5). Il risultato è la riga `error` `canale_giu:apertura_non_inviata`.

In breve: con il `.env` del principale, la «coda» del banco era in realtà un «canale giù».

### 1.3 Prove sperimentali (stesso codice master `d56bb3b`, stesso comando)

| Ambiente | coda | canale | Parità | File |
|---|---|---|---|---|
| `.env` del principale (worktree dentro il repo) | decisioni 3512, azioni 1, ordini 0, righe 1 `error` | 3512 / 2 / 2 / 2 | **NON RAGGIUNTA, KO** | `replay/safe_base_entrambi_PRIMA_env_principale.txt` (107,2 s) |
| stesso `.env` + **solo** `SAFE_ORDINI_VIA_CANALE=0` nella shell | 3508 / 2 / 2 / 2 | 3512 / 2 / 2 / 2 | **RAGGIUNTA, OK** | `replay/safe_base_entrambi_PRIMA_solo_SAFE_ORDINI_0.txt` (95,1 s) |

Cambiando una sola variabile, il referto si capovolge. Il referto del coordinatore su master
(`<principale>/AUDIT_2026-10-02/replay/safe_base_entrambi_MASTER_d56bb3b.txt`) coincide con la prima
riga, compreso il WARNING `47331 ... fail-closed`.

### 1.4 Le azioni del diario: sono ordini MANUALI dello scenario, non della strategia

Sonda: `sonda_diario_azioni.py`. Fa girare lo scenario `ordini-manuali` con le funzioni vere e
stampa le righe complete di `safe_strategy_trades` e `safe_strategy_requests`. Uscite:
`replay/sonda_diario_coda_env_principale.txt` e `replay/sonda_diario_canale_env_principale.txt`.

- **Coda, 1 azione** (`SAFE_ORDINI_VIA_CANALE` = `'1'` prima e durante il replay):
  `strategy: "manual", origin: "manual", side: lay, price 12.0, size 2.0, status: "error",
  meta.reason: "canale_giu:apertura_non_inviata"`. La richiesta `place` (`idempotency_key
  replay-35760084-manuale`) è stata respinta con `non eseguito (canale_giu:apertura_non_inviata)`.
  Attività: `canale_giu x1, place_retry x1`. Ordini reali su flumine: 0.
- **Canale, 2 azioni**:
  - riga 1 `strategy: "manual"`: LAY 2,00 chiesto a 12,0 e abbinato a 11,0 (`canale_ref safe-t1`), poi `hedged`;
  - riga 2 `closes_trade_id: 1`: BACK 2,39 @ 9,2, `exit_reason "Cash out manuale dalla dashboard"`
    (`safe-t2`), abbinata 2,39. P&L bloccato −0,40 EUR.

Tutte e tre le azioni sono **il trader finto del banco**: «Investi» e poi «Chiudi» dalla UI
(`replay_registrazioni.py:110`, `SCENARI_DESCRITTI[ordini-manuali]`). Non sono ordini delle tre
strategie, che su questa partita hanno 0 segnali (scenario `base`). La coda non «perdeva» un
ordine della strategia: non apriva il manuale perché usava il canale, giù nel replay. Il secondo
ordine del canale è la chiusura di quel manuale, che sulla coda non poteva esistere.

## 2. La condotta giusta secondo le decisioni scritte

- **CRONOSTORIA, checkpoint 07:49 del 29/09**: i replay di certificazione si fanno «con le
  variabili non segrete del `.env` DICHIARATE nell'ambiente: `LIVE_ORDER_MODE=LIVE`,
  `LIVE_KILL_SWITCH=false`, `MIKE_LIVE_ENABLED=1`, `SAFE_PRE_KO_OU_HOURS=1` … **i 20 interruttori
  dei canali a 0**; Supabase finto». Con quell'ambiente: «safe_base, safe_esatto, safe_punta |
  rapidi, entrambi | 14 OK ciascuno, **PARITA' RAGGIUNTA**».
- **CRONOSTORIA, checkpoint 07:11 del 29/09**: «il KO della coda era l'AMBIENTE». La
  certificazione deve essere ripetibile e non dipendere dal checkout.
- **CRONOSTORIA, 25/09 h19:20**: strada unica, parità coda/canale RAGGIUNTA su safe_base.
- **CRONOSTORIA, 28/09** («ambiente neutro», riga ~3870).
- **`trasporto.py`, docstring di testa**: `coda` = «il trasporto di oggi nel banco … l'ordine
  esce da `place_order_live` … è il riferimento certificato». Con l'interruttore acceso questo
  non vale più.
- **PROCESSO_STANDARD_BOT §6.8**: «il referto deve essere rifacibile identico».

Quindi la condotta giusta è questa: coda = interruttore SPENTO, canale = ACCESO, gli altri
interruttori a 0, e tutto **dichiarato dal banco**, non preso dal `.env`. Prima del 26/09
(scrittura delle 4 righe `*_ORDINI_VIA_CANALE` nel `.env`, CRONOSTORIA h17:15 del 26/09) il
problema non si vedeva perché l'interruttore mancava.

## 3. Cosa ho cambiato (solo banco e test, nessuna strategia, nessun file di produzione dei bot)

Commit `6517082` più il commit del referto.

- `Betfair/stream/backtest/trasporto.py`:
  - `VALORE_INTERRUTTORE = {"coda": "0", "canale": "1"}` (riga 54);
  - `contesto()` scrive l'interruttore del bot in **entrambi** i trasporti e lo ripristina
    all'uscita (righe 105-118 e 128).
  - `"0"` è spento per costruzione (`porta_ordini.VALORI_ACCESI`) e `load_dotenv` senza override
    non lo riscrive. Mike non ha interruttore e resta com'era.
- `Betfair/stream/backtest/certifica.py`:
  - `INTERRUTTORI_CANALE_DEL_BANCO` (riga 298): i 20 interruttori, stesso elenco di `Betfair/conftest.py`, e
    un test li tiene allineati.
  - `AMBIENTE_DEL_BANCO` (riga 319): freni D1-quater, più i 20 interruttori a `0`, più `MIKE_LIVE_ENABLED=1`
    e `SAFE_PRE_KO_OU_HOURS=1` (valori di produzione, elenco del 29/09).
  - `descrivi_ambiente()`.
  - `_freni_da_banco` (riga 267) dichiara e ripristina tutto `AMBIENTE_DEL_BANCO`, anche su eccezione.
  - Il referto stampa l'ambiente in testa, nel percorso normale e in quello `rapidi` (parametro
    `intestazione` di `main_rapidi`).
  - Non dichiarati, di proposito: `LIVE_MARKET_TYPES`, `LIVE_RECONCILE_POLL_SEC` e
    `HAZARD_ATLAS_SYNC`. Li leggono solo il runner, i worker e il `main` dello scanner, che nel
    replay non girano (verificato con grep).
- `Betfair/stream/backtest/trasporto_rapido.py`: argomento `intestazione` (stampata e scritta nel
  diario).
- `Betfair/stream/tests/test_strada_unica_banco_2026_09_25.py`: il test
  `test_contesto_accende_e_rimette_l_interruttore` pretendeva «in coda l'interruttore ASSENTE»,
  cioè la condotta difettosa. Ora pretende `"0"` dentro e assente dopo.

## 4. Test e falsificazione

`Betfair/stream/tests/test_banco_ambiente_dichiarato_2026_10_02.py` (23 test):

- coda spenta e canale acceso per ogni valore dell'ambiente (`1/true/si/yes/0/""/assente`), con
  `porta_per_sport` vera;
- ogni bot con interruttore (omega, safe_tennis, safe_esatto, safe_punta);
- **`load_dotenv` a metà replay** con un `.env` finto che accende tutto: non riaccende niente (è
  il meccanismo esatto del reperto);
- ripristino dell'ambiente anche su eccezione;
- elenco allineato al conftest e ai bot del trasporto;
- intestazione identica per ogni ambiente;
- **[cert]** sulla registrazione vera: la coda dello scenario `ordini-manuali` con i 20
  interruttori ACCESI nell'ambiente e con l'ambiente VUOTO dà lo stesso referto e la stessa
  traccia, con 2 ordini (righe `hedged`, `open`). Dura circa 90 s.

Esecuzioni:

- file nuovo + `test_strada_unica` + D1-quater: 43 verdi;
- [cert]: 1 verde (90,6 s);
- **suite `Betfair/stream/tests` intera (non cert): 3228 passed, 10 skipped** (269 s).

Falsificazione: `falsifica_parita_env.py` e `_out.txt`. Esito **TUTTO COME ATTESO**, sha256 dei
file ripristinati identico.

| Mutazione | Atteso | Ottenuto |
|---|---|---|
| 0 codice corretto | verde | 39 passed |
| M1 la coda non scrive l'interruttore (strato trasporto di master) | rosso | 11 failed |
| M2 freni senza i 20 interruttori (strato freni di master) | rosso | 6 failed |
| M3 = master (M1+M2): test [cert] sulla registrazione vera | rosso | 1 failed (87 s) |
| M4 intestazione senza interruttori | rosso | 1 failed |
| R ripristinato: veloci / [cert] | verde | 39 passed / 1 passed |

## 5. I due replay dopo la correzione

Comando `certifica safe_base 35760084 --scenari rapidi --trasporto entrambi --worker 1 --data-dir <principale>\_live_raw`.

| Ambiente | Scenari di trasporto | coda | canale | Parità | ESITO | Durata |
|---|---|---|---|---|---|---|
| `.env` del principale caricato (worktree dentro il repo) | 14 OK | 3508 / 2 azioni / 2 ordini / 2 righe | 3512 / 2 / 2 / 2 | **RAGGIUNTA** (scarto tempi max 2,1 s di mercato) | **OK** | 171,7 s |
| isolato: `PYTHON_DOTENV_DISABLED=1` (nessun `.env` letto) | 14 OK | 3508 / 2 / 2 / 2 | 3512 / 2 / 2 / 2 | **RAGGIUNTA** | **OK** | 160,8 s |

`confronta_referti_env.py` toglie solo le righe dei tempi (§6.9). Uscita in `replay/confronto_referti_env.txt`:

- principale e isolato: **referti identici, 90 righe su 90, tracce identiche**, intestazione dell'ambiente identica;
- master con il solo `SAFE_ORDINI_VIA_CANALE=0` e correzione con il `.env` del principale: **identici**.

La correzione quindi non cambia altro rispetto all'ambiente certificato del 29/09: gli altri 19
interruttori a 0 non toccano il referto di Safe.

Durate: 95-107 s prima, 152-172 s dopo. Le durate dei singoli replay sono salite allo stesso
modo in coda e canale (coda 43 → 75 s), anche sul codice del runner senza la mia correzione
(152,5 s): è carico della macchina (suite e falsificazione appena finite), non la correzione.
Il profilo resta sotto il tetto dei 10 minuti. Da rimisurare a macchina scarica.

## 6. Dato del coordinatore: «la patch del runner porta la coda da 1 a 2 ordini»

**Non è la patch del runner. È ancora l'ambiente.** Prove:

1. Ho fatto girare il commit `e4c93e0` (master `fb890d5` + patch del runner corretta), staccato nel
   mio worktree, che sta dentro il repo e quindi legge il `.env` del principale. Risultato: coda
   3512 / 1 / 0 ordini, canale 3512 / 2 / 2, **NON RAGGIUNTA, ESITO KO**, con il WARNING
   `47331 ... fail-closed`. È lo stesso referto di master. File:
   `replay/safe_base_entrambi_RUNNER_e4c93e0_env_principale.txt` (152,5 s).
2. Il worktree del coordinatore sta in `...\scratchpad\verifica-runner`, **fuori dall'albero del
   repo**. Ho risalito le cartelle fino alla radice del disco: nessun `.env`, quindi
   `load_dotenv()` non carica niente e l'interruttore resta assente. Nel suo referto
   (`safe_base_entrambi_RUNNER_coord.txt`) **manca** la riga `47331 ... token del canale assente
   (fail-closed)`, che c'è sempre quando la coda usa la porta vera. Il suo replay è quindi l'ambiente
   «isolato», non quello del principale.
3. **Nessun ordine perso in produzione.** Il «secondo ordine» che la coda non faceva è la chiusura
   (BACK 2,39 @ 9,2) dell'ordine MANUALE che la coda non aveva aperto. Sulla coda vera, a
   interruttore spento, entrambi gli ordini partono sia su master sia con la patch.
4. **Decisioni 3512 → 3508.** È la differenza ammessa e dichiarata in `trasporto.py` (docstring):
   sulla coda il bot resta FERMO sulla REST per `place_latency + betDelay`
   (`MotoreReplay.attendi_esecuzione`) a ogni piazzamento. Con 2 piazzamenti veri si perdono 4
   giri di `run_once`. Con l'interruttore acceso la coda non piazzava niente (rifiuto immediato a
   canale giù), non aspettava e faceva tutti i 3512 giri. 3508 è il segno che la coda sta
   piazzando davvero.

## 7. REPERTI per l'utente

- **R1 (banco, CORRETTO qui).** Il referto di certificazione dipendeva dal `.env` di chi lo
  lancia e dalla posizione del checkout. Tutte le parità coda/canale lanciate dal principale dopo
  il 26/09 (4 righe `*_ORDINI_VIA_CANALE=1` nel `.env`) confrontavano un «canale giù», non la
  coda. Per Safe questo ha dato un falso KO. **Omega** (`OMEGA_ORDINI_VIA_CANALE=1`) e
  **safe_tennis** (`SAFE_TENNIS_ORDINI_VIA_CANALE=1`) avevano lo stesso difetto sulla coda dal
  principale. Non li ho rilanciati: i loro referti «coda» dal principale dopo il 26/09 vanno
  riletti con questo in mente.
- **R2 (produzione): nessun difetto money-critical trovato.** La coda non perde ordini della
  strategia e il canale non ne manda di più: tutte e tre le azioni sono del trader finto. Impatto
  in euro sulla strategia: 0. Sul manuale dello scenario: apertura LAY 2,00 (rischio 20-22 EUR)
  non aperta, chiusura −0,40 EUR non necessaria.
  - In produzione, con `SAFE_ORDINI_VIA_CANALE=1` e il runner giù o senza token, un'apertura
    finisce `error` `canale_giu:apertura_non_inviata` e non passa mai sul REST. È la decisione D5,
    verificata anche dallo scenario R4 del profilo rapido. È la condotta voluta, non un difetto.
  - Da sapere: a interruttore acceso **la coda non è un ripiego automatico per le aperture**.
    Se il canale cade, le aperture si fermano; solo le chiusure passano dal REST (D5).
- **R3 (da decidere, non toccato).** `config_stream.py:16-17` carica il `.env` al primo import
  da qualunque processo, test e banco compresi. Il banco ora non ne dipende più. Restano esposti
  i test che fanno `delenv` di un interruttore presente nel `.env` (già segnalato in
  `TEST_ISOLAMENTO.md`).

## 8. NON VERIFICATO

- Parità coda/canale di **omega** e **safe_tennis** e i replay di Mike dopo la correzione.
  L'ambiente dichiarato vale per tutti i bot. Per Mike i valori sono quelli del `.env` del
  principale, quindi dal principale nulla cambia; da un checkout fuori dal repo ora vale come dal
  principale. Non l'ho misurato.
- La suite `Betfair/` intera: ho lanciato solo `Betfair/stream/tests` più i file toccati.
- La patch è prodotta contro la base `d56bb3b`: `git diff d56bb3b`, non contro il `master`
  attuale `5a7e076`, che contiene solo commit successivi. Il merge è pulito.
- Durata dei replay a macchina scarica (vedi §5).
