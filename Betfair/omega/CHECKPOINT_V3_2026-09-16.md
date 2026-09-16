# CHECKPOINT OMEGA V3 — 16/09/2026 (delegato O2)

> Aggiornato a OGNI passo: se i crediti finiscono, chi riprende legge solo questo file.
> Progetto di partenza: `Betfair/omega/PROGETTO_OMEGA_V3_2026-09-16.md`.
> VINCOLO: `omega_service.py` e' di O1 (riconciliazione/chiusure/aggregati): NON TOCCARE
> finche' il coordinatore non dice che O1 ha consegnato.

## Ordine allargato (coordinatore, 16/09 sera)

«Trova tu la soluzione matematica e probabilistica piu' avanzata»: il motore v3 NON e' il
Poisson residuo e basta. Vanno COSTRUITI e CONFRONTATI sui nostri dati, con log-loss/Brier
out-of-sample e calibrazione per decile:

1. Poisson indipendente residuo (base)
2. Dixon-Coles (1997) — correzione rho sulle celle basse (decisiva per l'HT)
3. Dixon & Robinson (1998) — intensita' variabili nel tempo + effetto del punteggio
4. Poisson bivariato (Karlis & Ntzoufras 2003) — solo se i dati lo giustificano
5. aggiornamento bayesiano dei lambda in gioco dai segnali del feed (gol, rossi,
   pressure_index/corner/timeline IPS): il peso si STIMA, non si assume
6. fusione col MERCATO: shrinkage in logit fra P_modello e P_implicita, peso per fascia

Uscita: la proposta di green nasce da una TRAIETTORIA attesa del profitto bloccabile
(EV di tenere vs EV di chiudere), non da una soglia fissa.

## Stato

| passo | descrizione | stato |
|---|---|---|
| 0 | lettura progetto + codice | FATTO |
| 1 | MISURA DI k (`tools/misura_k.py`) -> `data/k_misurato_2026-09-16.json` | **FATTO — risultato sotto** |
| 1b | `K_MISURATO_2026-09-16.md` | FATTO |
| 2 | banco modelli 1-5 (`tools/banco_modelli.py`) + log-loss/Brier OOS | **FATTO — risultato sotto** |
| 2b | banco fusione col mercato (candidato 6, `tools/banco_fusione.py`) | **FATTO** |
| 2c | calibrazione della CODA a risoluzione fine | **FATTO** |
| 3 | `omega_v3.py` (funzioni pure) + 41 test falsificati | **FATTO (verde)** |
| 4 | `omega_config.py` + `omega_engine.py`: percorso v3 dietro `strategy_version` (default 2) | **FATTO** |
| 5 | `certificazione.py` A8-A12/C5/G1/G2 + scenario `v3` nel replay + replay 35760084/35797769 | **FATTO — risultato sotto** |
| 6 | ADDENDUM coordinatore: famiglia K, scenario `rifiuti-betfair`, sintetica, cache per scenario, falsificazione dei 5 difetti | **FATTO — risultato sotto** |
| 6b | migrazione `omega_proposte_uscita_2026-09-16.sql` (SCRITTA, non applicata) | **FATTO** |
| 7 | referto per l'utente (`REFERTO_V3_2026-09-16.md`) | **FATTO** |

## PASSO 1 — RISULTATO DELLA MISURA DI k (il numero che decide il progetto)

Comando riproducibile: `python -m Betfair.omega.tools.misura_k`
Dati: `betfair_market_odds` (58.234 righe CS+HTS, 2.018 fixture) x `matches`
(1.997 esiti; 1.859 partite utili per il CS, 1.645 per l'HT). Quote **PRE-MATCH**.
Intervalli: **bootstrap a grappolo sulle partite** (le selezioni della stessa partita
non sono indipendenti: esce una sola scoreline).

**(a) k al prezzo di LAY realmente disponibile** — `k = p_implicita / p_reale`:

| mercato | secchio p_impl | n | partite | uscite | p_impl | p_reale | k | k prudente |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Correct Score | 0-0,2% | 258 | 229 | 2 | 0,0016 | 0,0078 | 0,21 | 0,08 |
| Correct Score | 0,2-0,5% | 1.148 | 656 | 6 | 0,0036 | 0,0052 | 0,68 | 0,36 |
| Correct Score | 0,5-1% | 2.385 | 1.184 | 22 | 0,0071 | 0,0092 | 0,77 | 0,54 |
| Correct Score | 1-2% | 5.079 | 1.773 | 77 | 0,0149 | 0,0152 | 0,98 | 0,80 |
| Correct Score | 2-5% | 10.685 | 1.841 | 458 | 0,0340 | 0,0429 | 0,79 | 0,73 |
| Correct Score | 5-10% | 10.427 | 1.846 | 873 | 0,0705 | 0,0837 | 0,84 | 0,80 |
| Correct Score | >10% | 2.464 | 1.562 | 394 | 0,1403 | 0,1599 | 0,88 | 0,81 |
| Half Time Score | 0,2-0,5% | 281 | 240 | 1 | 0,0038 | 0,0036 | 1,08 | 0,34 |
| Half Time Score | 0,5-1% | 1.039 | 886 | 9 | 0,0071 | 0,0087 | 0,82 | 0,49 |
| Half Time Score | 1-2% | 1.699 | 1.099 | 22 | 0,0149 | 0,0129 | 1,15 | 0,81 |
| Half Time Score | 2-5% | 4.222 | 1.597 | 166 | 0,0331 | 0,0393 | 0,84 | 0,73 |
| Half Time Score | 5-10% | 3.625 | 1.595 | 363 | 0,0751 | 0,1001 | 0,75 | 0,69 |
| Half Time Score | >10% | 5.050 | 1.644 | 1.062 | 0,1793 | 0,2103 | 0,85 | 0,82 |

> **NESSUN SECCHIO E' OPERABILE**: `k prudente <= 1` ovunque. Al prezzo di lay che il book
> offre davvero, bancare la coda pre-match e' in media a EV NEGATIVO. §3.3 del progetto:
> «se nessun secchio supera 1, il progetto non ha edge e va detto».

**(b) k con probabilita' DEVIGATA (mid back/lay normalizzato a 1): la FORMA del bias**

| mercato | secchio p_equa | n | partite | uscite | p_equa | p_reale | k_equo | k_equo prudente |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Correct Score | 0,5-1% | 3.855 | 1.391 | 21 | 0,0084 | 0,0054 | **1,53** | **1,07** |
| Correct Score | 1-2% | 3.700 | 1.481 | 48 | 0,0151 | 0,0130 | 1,16 | 0,90 |
| Correct Score | 2-5% | 12.060 | 1.846 | 396 | 0,0354 | 0,0328 | 1,08 | 0,99 |
| Correct Score | 5-10% | 11.881 | 1.847 | 865 | 0,0705 | 0,0728 | 0,97 | 0,92 |
| Correct Score | >10% | 3.681 | 1.700 | 518 | 0,1351 | 0,1407 | 0,96 | 0,90 |
| Half Time Score | 1-2% | 272 | 226 | 1 | 0,0154 | 0,0037 | 4,17 | **1,36** |
| Half Time Score | 2-5% | 5.811 | 1.596 | 139 | 0,0332 | 0,0239 | **1,39** | **1,20** |
| Half Time Score | 5-10% | 3.878 | 1.602 | 298 | 0,0717 | 0,0768 | 0,93 | 0,84 |
| Half Time Score | >10% | 6.331 | 1.643 | 1.199 | 0,1844 | 0,1894 | 0,97 | 0,94 |

> **IL FAVOURITE-LONGSHOT BIAS ESISTE E VA NELLA NOSTRA DIREZIONE** (coda sovraprezzata:
> k_equo 1,53 sul CS 0,5-1 %, 1,39 sull'HT 2-5 %, entrambi con estremo basso > 1), **ma se
> lo mangia interamente lo SPREAD**: la differenza fra (a) e (b) e' solo il prezzo a cui
> si opera. Conseguenza operativa per V3: **non si puo' raccogliere il bias attraversando
> lo spread** (FOK sul best availableToLay, che e' quello che Omega fa oggi). O l'edge
> viene dal MODELLO che batte il mercato su celle specifiche, o serve un ingresso PASSIVO
> a un prezzo dentro lo spread. Da portare all'utente come reperto, non da nascondere.

Il motore usa comunque `k_soglia = max(2, k_prudente)` e non scende MAI sotto 2 dove il
bias non e' dimostrato (`misura_k.tabella_k`).

## PASSO 2 — BANCO DEI MODELLI: chi vince, sui nostri dati, fuori campione

Comando: `python -m Betfair.omega.tools.estrai_transizioni --leghe 60` poi
`python -m Betfair.omega.tools.banco_modelli --max-iter 600`
Dati: `omega_minute_transitions`, **1,07 M righe** da ~1,4 M partite (globale 22.193
righe; 60 leghe campionate). Stati con n >= 200: **548**. Fit = massima verosimiglianza
multinomiale sui conteggi; prova su dati mai visti, con **due split indipendenti**
(meta' degli stati / 30 leghe contro 30). Metriche: log-loss e Brier multiclasse, piu'
la log-loss **della sola coda** (celle che il modello mette sotto il 2 %: e' li' che
Omega opera). Risultati in `data/banco_modelli_2026-09-16.json`.

| modello | logloss OOS (stati) | Brier | **coda <2 %** | HT | FT | logloss OOS (leghe) | coda (leghe) |
|---|---:|---:|---:|---:|---:|---:|---:|
| **5 Gamma-Poisson (bayesiano)** | **2,13041** | **0,78179** | **4,95478** | 1,26203 | **2,42266** | **1,93221** | **4,91797** |
| 3 Dixon-Robinson (1998) | 2,13731 | 0,78186 | 5,17026 | **1,26171** | 2,43198 | 1,93301 | 5,01694 |
| 4 bivariato Karlis-Ntzoufras (2003) | 2,13737 | 0,78188 | 5,17044 | 1,26166 | 2,43208 | 1,93307 | 5,01757 |
| 0 **v2 di produzione** (DC + mistura log-normale cv 0,30) | 2,14697 | 0,78381 | 5,11069 | 1,26589 | 2,44349 | 1,93904 | 5,01360 |
| 2 Dixon-Coles (1997) | 2,14830 | 0,78393 | 5,22601 | 1,26582 | 2,44529 | 1,93921 | 5,02951 |
| 1 Poisson indipendente | 2,14840 | 0,78395 | 5,22668 | 1,26577 | 2,44544 | 1,93929 | 5,03001 |

**Le cinque cose che i numeri dicono** (stesso ordine nei due split: non e' rumore):

1. **Vince il Gamma-Poisson bayesiano**, e vince proprio DOVE CONTA: sulla coda
   (`4,955` contro `5,111` del v2 di produzione e `5,226` del Poisson puro). E' il
   modello che aggiorna il tasso di ciascuna squadra dai gol gia' visti
   (posteriore coniugato Gamma) e la cui predittiva e' una **binomiale negativa**.
2. **Il Poisson bivariato NON e' giustificato dai dati**: `lambda3` si ferma a **0,000**
   in entrambi gli split, cioe' il modello degenera nel Dixon-Robinson. Risposta chiara
   al candidato 4: non serve.
3. **Dixon-Coles quasi non guadagna qui** (2,14830 contro 2,14840 del Poisson) e il rho
   stimato e' **-0,015/-0,031**, molto piu' piccolo del **-0,13** cablato in produzione
   (`omega_model.py:41`). Onesta': su dati AGGREGATI sui lambda la correzione tau non si
   puo' isolare (l'eterogeneita' fra partite domina). Il rho va tenuto, non gonfiato.
4. **`forma_gamma` 6,7-13,3 => cv = 1/sqrt(a) = 0,27-0,39**: il `model_lambda_cv` 0,30 di
   produzione era azzeccato. Ma la mistura log-normale del v2 *spalma* quell'incertezza
   e basta; il Gamma-Poisson la spalma **e impara dai gol visti**. Da qui il vantaggio.
5. **`beta_squilibrio` viene NEGATIVO** (chi e' avanti segna di piu'), il contrario del
   «chi e' sotto attacca». Non e' un paradosso: su dati aggregati chi e' avanti e'
   di solito la squadra piu' forte, e la forza non si puo' separare dal comportamento.
   Conferma della struttura: nel Gamma-Poisson `beta` scende a **-0,013** (contro -0,098
   del Dixon-Robinson) **perche' il posteriore ha gia' assorbito la forza**.

`profilo_c1` = **0,41**: l'intensita' dei gol al 90' vale `exp(0,41) = 1,5` volte quella
d'inizio partita — il profilo crescente di Dixon & Robinson, misurato sui nostri dati.

Calibrazione fuori campione (split leghe), decile piu' basso (dove sta tutta l'attivita'
di Omega): Gamma-Poisson **p prevista 0,335 % contro 0,331 % osservata** su 241 M di
peso; v2 0,337 % contro 0,338 %. Entrambi calibrati; serve la risoluzione fine sulla
coda (passo 2c).

## PASSO 3 — `omega_v3.py`

Modulo nuovo, **tutto puro** (nessun I/O, nessun Betfair, nessun database), che contiene:
`Parametri` · `esposizione` (profilo temporale) · `intensita_residue` · `griglia_residua`
/ `griglia_finale` (i 5 modelli) · `fondi_col_mercato` (pool logaritmico in logit) ·
`probabilita_selezioni` (scoreline **e aggregati**) · `p_implicita` · `candidato` (il
cancello del margine k) · `finestra_ingresso` · `profitto_bloccabile` ·
`p_punteggio_invariato` · `traiettoria_bloccabile` · `proposta_uscita`.
Test: `Betfair/omega/test_omega_v3_2026_09_16.py`, **41 verdi**, ognuno falsificato.

**Due difetti trovati dalla falsificazione** (il banco ha corretto il codice, non il test):
- `p_implicita(1.00)` valeva 1,0 e faceva passare qualunque cosa il cancello -> guardia
  `L <= 1` (`omega_v3.py:p_implicita`).
- la traiettoria del bloccabile, guardata nel solo ramo «non succede niente», diceva
  **sempre** «aspetta» e non si sarebbe mai chiuso niente. Ora il valore dell'attesa e'
  pesato con `p_punteggio_invariato` e nell'altro ramo si torna a valere l'EV di tenere
  di oggi (`valore_attesa = P(regge)*bloccabile + (1-P)*EV_tenere`).

## Log

- creato il checkpoint.
- scritto `Betfair/omega/tools/misura_k.py` (sola lettura del DB, bootstrap a grappolo).
- eseguita la misura: k<=1 al prezzo di lay in tutti i secchi; bias reale solo devigato.


## PASSO 5 — REPLAY: V3 IN OMBRA SULLE REGISTRAZIONI VERE

`python -m Betfair.stream.backtest.certifica omega 35760084 35797769 --scenari v3 --worker 3`

Lo scenario `v3` accende `strategy_version=3` (che spegne da sola il green-up automatico)
e fa girare `omega_v3` **in parallelo** al servizio, sullo STESSO book, allo STESSO minuto,
con gli STESSI lambda (il replay avvolge anche `_prematch_lambdas`, cosi' il confronto e'
sulla SELEZIONE e non sulla catena dei lambda). Il servizio non chiama ancora V3:
`omega_service.py` stasera e' di un altro delegato — dichiarato in testa al referto.

**ESITO: 0 violazioni su 2 partite.** E, soprattutto:

| | 35760084 | 35797769 |
|---|---|---|
| occasioni di selezione osservate | 66 | 141 |
| gambe che il **v2** avrebbe aperto | 1 | 0 |
| gambe che il **v3** avrebbe aperto | **0** | **0** |
| runner senza lato lay | 152 | 430 |
| scartati perche' troppo vicini al punteggio | 42 | 104 |
| scartati per P oltre il tetto del 2 % | 51 | 96 |
| scartati per MARGINE | 19 | 34 |
| **miglior margine offerto dal mercato** | **0,78x** | **0,87x** |
| margine mediano offerto | 0,57x | 0,70x |

> **Il numero piu' importante della serata, dopo k.** Su queste due partite il mercato non
> ha MAI offerto nemmeno 1x di margine, figurarsi 2x: il massimo e' stato **0,87x**. V3
> quindi non apre — ed e' la risposta giusta, non un guasto. E' la stessa cosa che dice la
> misura di k su 1.859 partite, vista qui dal vivo su due registrazioni.
> Il v2, sulla 35760084, ha invece aperto: al prezzo a cui e' entrato il margine era
> **sotto 1**, cioe' EV negativo. La differenza fra i due motori non e' «quante gambe»:
> e' che uno chiede un margine e l'altro no.

**Due difetti trovati dal replay stesso** (e corretti):
- i controlli del v2 giudicavano i momenti del v3 col vocabolario sbagliato (A1 accusava
  V3 di un motivo 'fuori_finestra' dichiaratissimo... in V3). Ora `Momento.motore`
  distingue i due motori e `_v3_suo()` gatta i controlli V3.
- `candidato()` che non sceglie non diceva PERCHE'. Ora c'e' `omega_v3.valuta_runner`
  che torna sempre i motivi di scarto runner per runner, col MARGINE VERO scritto dentro
  («margine 0,78x, ne serve 2x»): senza quel numero «non entra» non e' una spiegazione.


## PASSO 6 — ADDENDUM DEL COORDINATORE (reperto portato da Mike)

**(1) Famiglia K — la CONSAPEVOLEZZA.** `certificazione.py`: `K1..K6` +
`verifica_consapevolezza(righe, ordini, rifiutati)`, sul modello di
`Betfair/mike/certificazione.py:779-853`. Girano DOPO ogni giro del servizio nel
replay (`_verifica_consapevolezza`), confrontando le righe di `omega_trades` con gli
ordini VERI del banco, ref per ref:
K1 abbinato e prezzo medio · K2 rifiuto -> riga mai viva · K3 ref piazzato = ref riletto
· K4 `closes_trade_id` nella COLONNA · K5 riga aperta senza ordine a mercato · K6 residuo.
`elenco_controlli()` ora li include, se no un K mai sollecitato passava per inesistente
invece che per «non lo so».
Misurato: **K1-K6 sollecitati 1.466 volte** su `--scenari tutti`, **zero violazioni**.

**(2) Scenario `rifiuti-betfair`** (`place_rifiuto` del banco, SOLO sul lay): Betfair
risponde `ok=False` e nessun ordine esiste. Senza, `res.ok` non vale MAI False in tutto
il replay e K2 non puo' accorgersi di niente. Misurato su 35760084: 2 rifiuti provocati,
nessuna riga rimasta viva.

**(3) Sintetica `_synth_omega_prezzo_migliore`** — NON e' un terzo generatore: e' una
partita in piu' dentro `Betfair/safe_strategy/tools/synth_safe.py`, che ha guadagnato due
campi facoltativi (`cs_runners`, `cs_prezzi`) e per il resto e' identico. Il Risultato
Esatto arriva fino al 3-3 (Omega ha bisogno di celle davvero rare) e il "3 - 3" cala di
un tick VERO della scala Betfair ogni 4 secondi dal 50': col bet delay di 5 s l'ordine si
abbina a un prezzo MIGLIORE di quello chiesto.
Misurato: **lay chiesto 80, abbinato 75**, e la riga registra 75 — cioe' il prezzo
ABBINATO. K1 aveva finalmente un caso in cui poteva sbagliare, e non ha sbagliato.
Il referto lo dichiara ora in chiaro («ABBINATI A PREZZO DIVERSO DAL CHIESTO»).

**(4) Cache di processo per scenario.** Erano gia' azzerate (`AmbienteOmega.__enter__` e
`__exit__` chiamano `omega_service.svuota_le_cache()`, che e' un ELENCO scritto a mano, non
un `dir()`). Aggiunte due prove che mancavano, in
`test_omega_consapevolezza_2026_09_16.py`: (a) ogni nome che SEMBRA una cache dev'essere
citato in `svuota_le_cache` — cosi' una cache nuova non puo' sfuggire in silenzio; (b) si
sporca ogni cache e si pretende che torni vuota.
**Prova richiesta dal coordinatore, misurata**: `chiuso-fuori-app` sollecita **E5 x108**
da solo e **E5 x108** dentro `--scenari tutti --worker 3`. Identico: nessuno stato passa
da uno scenario all'altro.

**(5) Falsificazione dei 5 difetti del 15/09** — `test_omega_consapevolezza_2026_09_16.py`,
16 test verdi, ognuno col caso sano e col caso malato:
| difetto (15/09) | forma riprodotta | controllo che diventa rosso |
|---|---|---|
| 1 — `customerOrderRef` scritto, `customer_order_ref` riletto | ordine con la chiave camelCase | **K3** |
| 1-bis — il ref riletto e' un altro | `customer_order_ref` diverso dal chiesto | **K3** |
| 2 — `res.ok` ignorato | riga `open` + ref fra i rifiutati + nessun ordine | **K2** |
| 3 — `avg_price` invece di `avg_price_matched` | riga a 65, ordine abbinato a 62 | **K1** |
| 3-bis — abbinato diverso dal creduto | riga size 1,0, ordine 0,4 | **K1** |
| 4 — riconciliazione con un ref diverso | riga `open` con bet_id che a mercato non esiste | **K5** |
| 5 — `closes_trade_id` solo nel meta | riga back con la colonna a NULL | **K4** |
| 6 — residuo non dichiarato | chiesti 5, abbinati 2, nessun `size_remaining` | **K6** |
E i casi che NON devono accusare: ordine `EXECUTABLE` (ancora vivo), `meta.reconciling`
(dubbio dichiarato), chiusura con la colonna valorizzata.

> **DIVERGENZA DICHIARATA DAL METODO DELL'md5.** Il catalogo vuole che i difetti si
> rompano dentro `omega_service.py` / `omega_market.py`, si faccia girare il replay e si
> ripristini verificando l'md5. **Stasera non si poteva**: `omega_service.py` e' in mano a
> un altro delegato in questo stesso momento, e riscriverlo anche per un secondo avrebbe
> potuto cancellargli il lavoro. La falsificazione e' quindi al livello sotto — si
> costruisce l'ARTEFATTO che il difetto produrrebbe, con le chiavi VERE del banco
> (verificate contro `MercatoFlumine._riga` da un test apposta) e le chiavi VERE di
> `omega_trades` — ed e' altrettanto stringente. Va rifatta col metodo dell'md5 quando
> `omega_service.py` torna libero.
> ⊘ **NON ESERCITABILE**: il place-and-trim (il residuo tagliato da un secondo ordine
> sullo stesso ref) non passa dal banco, che non simula il trim. K6 si limita a pretendere
> che il residuo sia DICHIARATO, che e' la parte verificabile.

**Test**: `python -m pytest Betfair/omega Betfair/stream -q -p no:cacheprovider` -> **2.332 verdi**.


## PASSO 7 — DUE FALSI POSITIVI DEI MIEI CONTROLLI, trovati dalla batteria

La batteria `--scenari tutti` su 3 registrazioni (42 combinazioni) ha fatto quello che
doveva: ha accusato il bot, e due accuse su tre erano **del controllo**, non del bot.
Sono corrette, con un test di non-regressione ciascuna.

| controllo | accusa | perche' era falsa | correzione |
|---|---|---|---|
| **K5** (242 accuse, scenario `paper`) | «riga aperta senza ordine a mercato» | in PAPER il fill viene da `omega_engine.paper_fill` — uno snapshot, non un ordine: la riga e' aperta SENZA `bet_id` e a mercato non c'e' niente. E' la divergenza P4 DICHIARATA | K5 accusa solo chi dichiara un `bet_id` |
| **K1** (119 accuse, scenario `cashout-globale`) | «il bot crede 7,01 abbinato, il mercato dice 0» | la riga era gia' marcata `error` dopo un `place_rifiutato`: li' `size` e' la size CHIESTA, non un abbinamento. Accusarla vuol dire accusare il bot di aver detto il contrario di quello che ha detto | K1 salta gli stati che dichiarano il fallimento |

> E' la regola scritta in testa a `certificazione.py`: «prima di accusare il bot si esclude
> che il falso positivo sia del controllo». Un referto con 361 accuse false non e' severo,
> e' **inutile**: nessuno lo legge piu' e il giorno che l'accusa e' vera passa inosservata.

## FILE TOCCATI (nessun commit, nessuna migrazione applicata, nessuna app avviata)

**Nuovi**: `Betfair/omega/omega_v3.py` · `Betfair/omega/tools/misura_k.py` ·
`Betfair/omega/tools/estrai_transizioni.py` · `Betfair/omega/tools/banco_modelli.py` ·
`Betfair/omega/tools/banco_fusione.py` · `Betfair/omega/test_omega_v3_2026_09_16.py` ·
`Betfair/omega/test_omega_v3_certificazione_2026_09_16.py` ·
`Betfair/omega/test_omega_consapevolezza_2026_09_16.py` ·
`Betfair/omega/K_MISURATO_2026-09-16.md` · `Betfair/omega/REFERTO_V3_2026-09-16.md` ·
`Betfair/omega/CHECKPOINT_V3_2026-09-16.md` ·
`migrations/omega_proposte_uscita_2026-09-16.sql` (SCRITTA, non applicata) ·
`Betfair/omega/data/` (k misurato, transizioni, banco modelli, banco fusione,
calibrazione della coda, parametri vincenti).

**Modificati**: `omega_config.py` (parametri V3 + G1 nella whitelist) ·
`omega_engine.py` (percorso v3 in coda al file, il v2 non e' toccato) ·
`certificazione.py` (A8-A12, C5, G1, G2, famiglia K) ·
`tools/replay_registrazioni.py` (scenari `v3` e `rifiuti-betfair`, motore in ombra,
famiglia K a ogni giro) · `test_omega_ui_contratto_2026_09_11.py` (esenzione temporanea
e auto-estinguente per i parametri V3 non ancora nel pannello) ·
`Betfair/safe_strategy/tools/synth_safe.py` (una partita in piu' e due campi
facoltativi; nessun generatore nuovo).

**NON toccato**: `omega_service.py` (e' di O1), `frontend/`, nessun processo avviato.


## REPERTI PER CHI HA IN MANO `omega_service.py` (io non potevo toccarlo)

La batteria completa ne ha trovati tre. **Nessuno e' di V3**: stanno tutti nel motore
di oggi, e tre sono emersi grazie a uno scenario o a una sintetica NUOVI.

| dove | cosa | quanto |
|---|---|---|
| `rifiuti-betfair` (scenario nuovo) e `chiuso-fuori-app` | **J3**: il ref `omega-t1` del piazzamento non e' riconducibile a nessuna riga con `customer_ref_for` — la riconciliazione non ritroverebbe l'ordine | x2, su 2 partite |
| `cashout-globale` sulla sintetica | **J6**: abbinato 0,0 su 7,01 chiesti e nessuna attivita' `place_parziale`: il trader non vede il residuo | x1 |

## COSA MANCA (in ordine di importanza)

1. **Il raccordo di V3 dentro `omega_service.py`**: oggi V3 gira solo in ombra nel replay.
   Il servizio deve chiamare `omega_engine.seleziona_v3` quando `strategy_version >= 3`,
   dimensionare a stake fisso, e scrivere le proposte di uscita invece di chiudere.
2. **La UI**: pannello dei parametri V3 (`frontend/src/lib/omega.ts`, gruppo nuovo) e
   pagina delle proposte in Control Room (modello: `controlRoomProposte.ts`).
3. **La migrazione** `omega_proposte_uscita_2026-09-16.sql` — la applica l'utente.
4. **A12 e G2 mai sollecitati**: il veto storico non ha tabella nel replay (le transizioni
   sono un dato di DB, non stanno in una registrazione) e le proposte non nascono finche'
   il servizio non le scrive. Sono due «non lo so», non due garanzie.
5. **L'INGRESSO PASSIVO**: e' la domanda vera aperta dal §1 del referto. Finche' si
   attraversa lo spread, il bias misurato resta sulla carta.
6. **Rifare la falsificazione col metodo dell'md5** su `omega_service.py` quando torna libero.

## AVVISO AL COORDINATORE

Alle **21:31** un'altra sessione ha committato (`f412912`, poi `ffd039f`) portandosi dentro
il mio lavoro **a meta'** — `omega_v3.py`, `omega_config.py`, `certificazione.py`,
`omega_engine.py`, i file in `data/` e i test. **Io non ho mai eseguito `git add` ne'
`git commit`**, come da vincolo. Va saputo: il repo non e' nello stato «niente committato»
che il mandato dava per scontato, e in quei due commit c'e' codice V3 intermedio (per
esempio `omega_v3.candidato` prima del refactor che restituisce i motivi di scarto, e i
controlli K prima delle due correzioni dei falsi positivi).


## BATTERIA FINALE (col codice di adesso, sintetica rigenerata)

`python -m Betfair.stream.backtest.certifica omega 35760084 35797769 _synth_omega_prezzo_migliore --scenari tutti --worker 3`

**39 partite-scenario su 42 senza violazioni; 5 accuse in tutto**, tutte del motore di oggi
(J3 x2 su due partite, J6 x1 sulla sintetica). **Zero accuse a V3**, che nello scenario
dedicato apre 0 gambe sulle partite vere e 1 sulla sintetica, con tutti i suoi controlli
(A8, A9, A10, A11, C5, G1) sollecitati e verdi. A12 e G2 restano «non lo so»: il primo
perche' le tabelle storiche non stanno in una registrazione, il secondo perche' le proposte
nascono solo quando il servizio chiamera' V3.

`python -m pytest Betfair/omega Betfair/stream -q -p no:cacheprovider` -> **2.334 verdi**.
