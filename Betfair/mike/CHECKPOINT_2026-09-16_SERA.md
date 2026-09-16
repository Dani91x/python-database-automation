# CHECKPOINT — Mike, 16/09/2026 SERA (delegato Opus 5)

> Sei ordini dell'utente. Repo `master`, commit di partenza `740fad7`.
> Nessun commit, nessuna migrazione, nessun processo avviato.
>
> ⚠️ **SETTIMO ORDINE (proposte di green/cash-out in Control Room): ANNULLATO
> dall'utente** — «Mike deve lavorare come progettato». Era stato iniziato
> (`engine.EXIT_ROLES_FIRMA`, `MatchCtx.uscita_approvata`, `_uscita_su_firma`,
> due parametri in `config.py`) e **ripristinato per intero**: `git diff` su
> `Betfair/mike/config.py` è VUOTO e in `engine.py` non resta nessuna traccia
> (`grep -n "EXIT_ROLES_FIRMA\|uscita_approvata\|_uscita_su_firma\|exit_approval"`
> non trova niente). Prova di NON regressione in fondo a questo file.

| # | ordine | stato |
|---|---|---|
| 1 | 4 controlli mai sollecitati (A2, B2, F1, F2) | **FATTO** (A2: ⊘ con causa + falsificazione + test) |
| 2 | re-ingresso H1/H2 (registrazione SINTETICA) | **FATTO** |
| 3 | ordine appoggiato che muore a una sospensione (R1 ramo b) | **FATTO**, su dati REALI |
| 4 | MAI SOVRACOPERTURA — `over_cover` (J6) | **FATTO** |
| 5 | falsificazione indipendente dei 5 difetti del 15/09 | **FATTO — con un REPERTO GRAVE** |
| 6 | chiusura dell'utente FUORI DALL'APP (posizione di conto, R3) | **FATTO** |

## Baseline misurata PRIMA di toccare qualunque cosa
`certifica mike 35760084 --scenari tutti --worker 3` (11 scenari): **0 violazioni**,
27 controlli, mai sollecitati **A2, H1, H2**. B2 x1006, F1 x2, F2 x1006 erano già
sollecitati e verdi: il «mai sollecitati» del checkpoint precedente veniva dal solo
scenario `base`. Numeri di riferimento: **base azioni 15 / ordini 13**, **taker 13 / 12**
(NON 12/10 e 10/9: quei numeri sono di un codice precedente al commit `740fad7`, che ha
cambiato i tempi del banco con la cache Poisson e la latenza delle letture).

## 1 — A2, B2, F1, F2
* **B2 (x1006), F1 (x2), F2 (x1006)**: già sollecitati e VERDI con la pool su tutti
  gli scenari. Nessun lavoro necessario, solo la misura.
* **A2**: non può avere un caso attraverso il servizio, e la causa è precisa:
  `service._run_event` esce PRIMA di chiamare `decide` quando lo stato è terminale.
  È una garanzia più forte del controllo. Misurato e scritto nel referto: nello
  scenario `bot-fermo` il servizio fa **4.860 giri su una partita già regolata e
  produce 0 azioni**. Falsificazione: tolto quel `return`, **A2 diventa sollecitato
  x3642 e resta VERDE** — la seconda linea di difesa (la guardia dentro `decide`)
  esiste e funziona. Sei test nuovi la difendono direttamente (uno per stato
  terminale, più quello che prova che il servizio non chiama nemmeno `decide`).

## 2 — Re-ingresso (H1/H2): REGISTRAZIONE SINTETICA
Nuovo strumento `Betfair/mike/tools/synth_mike.py`: costruisce stream **nel formato
nativo Betfair** copiando i `marketDefinition` VERI di 35760084 (stessi `selectionId`,
stessi `sortPriority`) e un record IPS VERO di fonte **betfair** dal sidecar (il parser
di produzione legge `timeElapsed`/`score.home.score`: un modello preso dalla fonte
`api_football` avrebbe dato minuto e gol nulli — trovato e corretto al primo giro).
Registrazione `_live_raw/_synth_mike_reingresso/`, **dichiarata SINTETICA** dal referto
(`certifica.py` la stampa in testa: «NON SONO PARTITE REALI»).
Storia: ingresso a 1,50 pre-KO → al fischio l'uscita appoggiata a 1,48 si abbina
INTERA (chiusura in profitto) → gol al 20' → Under 4.5 a 1,60 (sopra il prezzo
d'ingresso) → **re-ingresso, UNA volta**.
Esito: 0 violazioni, stati `…,FLAT,REENTRY_PENDING,REENTRY_OPEN`, **H1 x1 e H2 x1
sollecitati e verdi**, 10 ordini, 9 fill (1.20 / 1.48 / 1.50 / 1.60).

## 3 — L'ordine appoggiato che muore alla sospensione (R1 ramo b) — su dati REALI
Tre buchi, tutti chiusi; nessuna registrazione sintetica è servita.
1. `banco_comune.MercatoFlumine.order_state_by_bet_id` **non esisteva**. In produzione
   esiste (`omega_market:1082`) ed è l'unica strada quando l'ordine è uscito dai
   correnti: senza, `_rileggi_ordine_appoggiato` tornava «ignoto/mercato_senza_lettura».
   Aggiunto con le **stesse chiavi del vero**, nemmeno una in più.
2. La riga dell'evento nel replay non aveva `markets` (in produzione la scrive
   `run_once:2366` dal `feed.event_info`): tutto ciò che in `_run_event` dipende da
   `ev["markets"]` non veniva MAI esercitato. Ora la scrive la stessa funzione vera.
3. `service._segui_resting_live` dichiarava «resting uscito dagli ordini vivi» anche
   **durante** una sospensione con una rilettura già annotata: la gamba finiva in
   `pending_reconcile` e alla riapertura la rilettura chiudeva con «gamba_non_più_viva».
   Il ramo (b) non poteva capitare per costruzione. Ora, con `ctx.riapertura.letto=False`,
   quella funzione tace e lascia parlare Betfair alla riapertura (attività
   `resting_in_sospensione`). È consapevolezza, non strategia: cambia chi legge
   l'esito, non che cosa il bot fa.

**Esito su 35760084 `base`**: `rilettura_alla_riapertura` esito **scaduto x1**,
`ordine_scaduto_alla_sospensione x1`, **R1 x4681 verde**, 0 violazioni, azioni 15 /
ordini 13 (identico alla baseline).

## 4 — MAI SOVRACOPERTURA
`engine._mai_sovracopertura` + `engine.copertura_in_volo`, ultima parola di `decide()`
subito dopo `_una_sola_lay`: finché c'è una copertura VIVA o IN VOLO non se ne emette
una nuova; l'annullamento sì; la nuova al giro dopo, ad annullamento CONFERMATO,
dimensionata su `cover_matched_value` (tutte le gambe già abbinate del mercato Over 4.5).
**Conseguenza corretta insieme**: una copertura annullata con fill PARZIALE non è né
viva né piena — prima cadeva in fondo a `_decide_cover_pending` e lo stato restava
`LIVE_COVER_PENDING` «attesa fill copertura» per sempre (il residuo non veniva mai
ricomprato). Ora si torna a `LIVE_UNCOVERED` e si ridimensiona sul residuo reale.
Controllo **J6** in tre parti (stato, decisione, quantità). 16 test nuovi; tre test
esistenti che codificavano il vecchio `cancel`+`place` aggiornati alla regola nuova.
Replay 35760084 base: **identico alla baseline** (15 azioni / 13 ordini, 0 violazioni),
J6 sollecitato e verde: su quella partita la copertura si abbina al primo colpo e il
riprezzo non capita mai — il ramo è difeso dai test.

## 5 — Falsificazione indipendente dei 5 difetti del 15/09 — 🔴 REPERTO
**Primo giro**: reintrodotti uno a uno sul codice di oggi e lanciato
`certifica mike 35760084 --scenari base,taker,esiti-ignoti`, **NESSUNO dei cinque
faceva diventare rosso il replay: il referto era identico cifra per cifra** (stessi
tick, stesse decisioni, stesse azioni). Le impronte del codice nel referto lo provano
(5 sha diversi: il difetto ERA applicato). Causa: i controlli A-J guardano la DECISIONE
del motore; i cinque difetti non stanno lì, stanno nel rapporto fra ciò che il bot
CREDE delle sue gambe e ciò che il MERCATO dice dei suoi ordini. **Nessun controllo
guardava quel rapporto.**

Rimedio (§6.7 del processo: «un controllo che non sa diventare rosso non certifica»):
* famiglia **K** in `certificazione.py` — `verifica_consapevolezza(ctx, ordini,
  rifiutati, righe)`, chiamata dal replay DOPO ogni giro del servizio, dove esistono
  insieme le gambe e gli ordini VERI di flumine:
  **K1** il bot crede quello che il mercato dice (abbinato, prezzo medio) ·
  **K2** una gamba rifiutata da Betfair non resta mai viva ·
  **K3** il ref con cui si è piazzato si rilegge con la stessa grafia ·
  **K4** ogni gamba di chiusura dichiara l'apertura che chiude;
* scenario **`rifiuti-betfair`** (guasto `place_rifiuto` nel banco): i primi 3
  piazzamenti tornano `ok=False` con le parole di Betfair. Chiude anche un ⊘ del banco
  («rifiuti Betfair provocati») elencato nell'handoff.

**Secondo giro, con i controlli K e lo scenario nuovo** — comando:
`certifica mike 35760084 _synth_mike_prezzo_migliore --scenari base,esiti-ignoti,rifiuti-betfair --worker 3`
(6 replay per difetto) più `pytest Betfair/mike -q`. Il codice sano: **0 violazioni, 0 test rossi**.

| difetto del 15/09 | replay | suite |
|---|---|---|
| (a) `customerOrderRef` letto al posto di `customer_order_ref` | **K3 x20.632 — tutti e 6 i replay KO** | 6 rossi |
| (b) `res.ok` mai letto | **K2 x56 — KO nello scenario `rifiuti-betfair`** | 3 rossi |
| (c) `avg_price` al posto di `avg_price_matched` | **K1 x2.265 — KO sulla SINTETICA `prezzo_migliore`** (su 35760084 resta verde: lì nessun ordine appoggiato si abbina a un prezzo migliore di quello chiesto) | 1 rosso |
| (d) ref di riconciliazione ≠ ref di piazzamento | **P1 x4 — KO: il loop del 15/09, azioni 54 contro 15** | 12 rossi |
| (e) `closes_trade_id` non passato nel meta | **verde — ⊘ DICHIARATO** | 1 rosso |

**⊘ del difetto (e), con la causa**: il suo effetto vive nel place-and-trim (`X.place`
decide `is_closing` dal meta) e nel freno live sulle uscite; nel banco
`place_submin_live` **è** `place_order_live` (limite già dichiarato «place-and-trim /
minimo .it»), quindi la conseguenza non si manifesta. Lo cattura il test
`test_mike_loop_chiusure_2026_09_15.py::test_la_chiusura_si_dichiara_a_chi_esegue`.

`Betfair/mike/service.py` **md5 identico prima e dopo ogni falsificazione**
(`5cc076bde04c1db17b4be997d8412fcd`), verificato a ogni ripristino dallo script stesso.

### Un secondo difetto del BANCO, trovato col referto alla mano
Con la pool (`--worker N`) più coppie evento × scenario girano nello **stesso processo
figlio**: le cache di modulo di `mike/service.py` sopravvivevano da uno scenario al
successivo. Misurato: `chiuso-fuori-app` dentro `--scenari tutti --worker 3` non leggeva
**mai** la posizione di conto (throttle ereditato) e dava **R3 x0**, mentre lo stesso
scenario da solo lo solleva **5.837 volte**. Adesso ogni replay parte da un processo
pulito (`service.azzera_cache_di_processo`, elenco **esplicito**). Nello stesso giro è
stato corretto `_riavvia_processo`, che azzerava ogni dizionario di modulo trovato con
`dir()` — compreso `_ALIAS_ORDINE`, cioè la tabella con cui Mike legge le chiavi
camelCase: lo scenario `riavvio` reintroduceva il difetto 1 del 15/09 dentro sé stesso.

## 6 — «Se chiudo io, il bot deve saperlo, anche fuori dall'app»
* `omega_market`: `_riga_corrente`/`_riga_regolata` estratte + **`list_current_orders_account`**,
  **`list_cleared_orders_account`** (senza filtro di strategia) e **`market_profit_and_loss`**.
* `mike/service._RealMarket`: `list_account_orders`, `list_account_cleared_orders`,
  `market_profit_and_loss`.
* `mike/service._sorveglia_posizione_di_conto` (+ `_netto_su_selezione`,
  `_posizione_attesa`, `_refs_di_mike`), chiamata in `_run_event` **prima della
  decisione**. **CADENZA DICHIARATA: `reconcile_every_s`, default 30 s per partita**,
  la stessa del respiro del DB; mai a ogni giro; solo in LIVE; solo con una posizione
  aperta. Misurato sul replay: le letture passano da 635 a 965 per partita.
* Verdetto a tre esiti, conservativo: gambe non ritrovate = riconciliazione (non si
  spegne niente) · netto di conto che non contiene più la posizione =
  `chiuso_dall_utente` · contenuta solo in parte = si dichiara e basta.
  Mike riconosce LA SUA posizione dentro quella di conto per **ref e size**, con
  ENTRAMBE le grafie (`under_entry-0-1` e `mike-t<id>`).
* `engine.MatchCtx.chiuso_dall_utente` (persistito in `_CTX_FIELDS`) + guardia in
  `decide()`: nessuna azione, né apertura né chiusura; gli ordini ancora vivi vengono
  annullati DAVVERO; la partita **non** diventa terminale, così il regolamento
  contabilizza il P&L vero.
* Controllo **R3** + scenario **`chiuso-fuori-app`** (ordini VERI su flumine con ref
  `utente-suo-back` / `utente-chiusura`: l'utente ha ANCHE una posizione sua).
  Esito su 35760084: `chiuso_dall_utente x1`, **R3 x5837 verde**, 0 violazioni.

## PROVA DI NON REGRESSIONE (dopo il ripristino del punto 7)
| replay | baseline di oggi | adesso | verdetto |
|---|---|---|---|
| 35760084 `base` | azioni 15 / ordini 13, 0 violazioni | **15 / 13, 0 violazioni** | identico |
| 35760084 `taker` | azioni 13 / ordini 12, 0 violazioni | **13 / 12, 0 violazioni** | identico |
| 35674515 `base` | 0 violazioni, J2 x4 e J4 x3 sollecitati | **0 violazioni, J2 x4, J4 x3** | identico |

### Certificazione finale
`certifica mike 35760084 --scenari tutti --worker 3` (**13 scenari**): **0 violazioni**,
**33 controlli**, mai sollecitati soltanto **A2** (⊘ con causa e falsificazione sopra),
**H1** e **H2** (che le due registrazioni SINTETICHE sollecitano e trovano verdi).
Registrazioni sintetiche: `_synth_mike_reingresso` (0 violazioni, H1 x1, H2 x1) e
`_synth_mike_prezzo_migliore` (0 violazioni, abbinamento a 1,44 contro 1,48 chiesti).

Suite: `python -m pytest Betfair/ -q -p no:cacheprovider` → **4152 verdi, 0 rossi**;
`pytest Betfair/ -m cert` → **19 verdi**; frontend `npx vitest run src/lib` → 1426 verdi;
`npm run build` OK; `tsc` 14 errori (13 preesistenti + 1 in
`src/components/safestrategy/ParamsSheet.tsx`, che non è di questo lavoro).
Nessun commit, nessuna migrazione, nessun processo avviato.
