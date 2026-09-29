# Mike, pacchetto P5: la copertura come BANCA Under 4,5 - progetto di implementazione

> Progetto prodotto il 29/09/2026 da un delegato in SOLA LETTURA (nessun file modificato), trascritto
> dal coordinatore. E' un PROGETTO, non codice verificato: ogni `file:riga` va ritrovato prima di
> toccare. Le decisioni dell'utente stanno in `PIANO_MODIFICHE_MIKE_2026-09-29.md`.

## In breve
1. **L'ordine di CHIUSURA della copertura resta identico a oggi.** «Banca Under 4,5 12,63 a 1,18» e'
   la stessa posizione di «punta Over 4,5 2,26 a 6,60». Per annullarla serve lo stesso ordine di
   oggi: banca Over 4,5 0,71 a 21, ruolo `over_close`. M3.3 non cambia ne' l'ordine ne' la cifra:
   cambia che quella banca va compensata con una gamba che sta sull'ALTRA selezione.
2. **Punto critico: il codice compensa le gambe selezione per selezione, non per mercato**
   (`exposure`, `engine.py:649-665`). Con la copertura su Under 4,5 e la chiusura su Over 4,5 oggi
   Mike vedrebbe DUE posizioni aperte dopo una chiusura riuscita, cercherebbe di «chiuderle» e
   disferebbe la chiusura; e dimensionerebbe la banca del rientro mescolando copertura e rientro,
   lasciando una banca Over NUDA da 0,71 a 21 (con 5+ gol costa circa 14 EUR). La compensazione
   PER MERCATO del mercato 4,5 e' il prerequisito di tutto il pacchetto (blocco 1).
3. **Niente migrazione SQL** se si tiene il ruolo `over_cover` (lato `lay`, selezione Under): le
   colonne coi vincoli (`strategy`, `side`) accettano gia' questi valori e nessuna funzione SQL
   distingue il lato della copertura.
4. **Interruttore di sicurezza:** parametro nuovo `cover_form` con valori `lay_under45` e
   `back_over45`. Nei blocchi 2-4 resta di serie sul vecchio; nel blocco 5 passa di serie sul nuovo.

## 1. Mappa dei punti del codice (OK = generico, funziona gia'; CAMBIA = da modificare)

### `Betfair/mike/engine.py`
| Punto | Stato | Oggi -> dopo | Rischio se dimenticato |
|---|---|---|---|
| `:46-53` `ROLES`, `OPENING_ROLES`, `CLOSING_ROLES` | OK | si tiene `over_cover` (apertura) e `over_close` (chiusura) | - |
| `:67-68` `IT_BACK_MIN`, `IT_BACK_STEP` | CAMBIA | aggiungere `IT_LAY_MIN = 0.50` (stesso valore di `execution._min_size_live`, `execution.py:71-89`) | tranche e residui sotto 0,50 finiscono nel piazza e riduci e vengono rifiutati |
| `:419-443` `cover_size`, `cover_residual`, `cover_size_residual` | restano | formule della puntata; aggiungere `cover_residual_lay` | importo 5-6 volte sbagliato |
| `:446-456` `cover_matched_value` | OK | somma gia' tutte le gambe del mercato 4,5 a 5 gol | - |
| `:459-465` `under_liability` | OK | - | - |
| `:468-506` `legalize_back_size`, `cover_legal_size` | CAMBIA | su `lay` solo il centesimo, mai minimo 2,00 e passi 0,50, anche con `exact_sizes=False` | banca legalizzata come una puntata |
| `:509-516` `needs_submin` | OK | con `lay` da' gia' False | - |
| `:649-665` `exposure` | **CAMBIA (cuore)** | oggi solo le gambe della stessa selezione. Dopo: TUTTE le gambe del mercato; una gamba sull'altra selezione pesa rovesciata (punta Y: `w-=s; l+=s(p-1)`; banca Y: `w+=s; l-=s(p-1)`). Con gambe su una sola selezione il risultato e' identico a oggi | chiusura disfatta, rientro sbagliato, `locked_pnl` sempre None |
| `:668-675` `open_selections` | CAMBIA | una chiave per mercato non piatto. OU35 -> sempre `(OU35, UNDER)` (nel feed non c'e' il libro Over 3,5, `feed.py:416`). OU45 -> la selezione LUNGA: `OVER` se W_over > W_under, altrimenti `UNDER`: cosi' la chiusura e' sempre una BANCA | due selezioni «aperte» su una posizione piatta |
| `:700-704` `invested` | CAMBIA | puntate di apertura + per ogni banca di apertura `matched*(avg-1)`. Esempio 10 + 2,27 = 12,27 | copertura fuori dal capitale impegnato: soglia 5 %, cash out intelligente, `liability_room` sbagliati |
| `:737-805` `cashout_value` | OK dopo `exposure`/`open_selections` | commissione gia' per mercato (`:778-792`) | - |
| `:938-947` `event_liability` | OK | - | - |
| `:950-968` `locked_pnl` | OK dopo `open_selections` | - | la scheda non dice mai «bloccato» (M7.2) |
| `:993-1001` `opening_ref` | CAMBIA | oggi cerca una puntata di apertura sulla stessa selezione: per `over_close` su Over non trova niente -> `closes_trade_id` NULL. Dopo: per ruolo sull'intero mercato (`over_close`->`over_cover`, `reentry_green`->`reentry`, chiusure OU35 -> `UNDER_ROLES`, `manual_close` -> ultima apertura del mercato) | K4 rosso; chiusura contata come apertura in `mike_aggregates` e nello storico |
| `:1212-1251` `cover_timing` | quasi OK | la quota Over serve solo a `cover_good_price`: leggerla come oggi; se manca, equivalente `q/(q-1)` dalla banca Under | - |
| `:1254-1336` `settle_legs*` | OK | generico | - |
| `:1370-1410` `riepilogo_cicli` | CAMBIA (presentazione) | aggiungere il rischio delle banche di apertura | stake sottostimato in scheda |
| `:1413-1461` `posizione_per_selezione` | CAMBIA | una riga per mercato con le gambe delle due selezioni | scheda con abbinato 0 sulla copertura |
| `:1687-1704` `cover_place_price` | CAMBIA | per la banca: `ticks_away(best_lay_U45, +n)` | banca 2 tick sotto il miglior prezzo: non si abbina mai |
| `:1707-1714` `liability_room` | OK con `invested` corretto | - | - |
| `:1737-1751` `ordini_vivi_su` | CAMBIA | per OU45: le due selezioni | copertura viva sull'Under che si abbina dopo la chiusura sull'Over |
| `:1754-1783` `_close_actions` | CAMBIA poco | aggiungere il ripiego sotto 0,50 | - |
| `:1854-1879` `_strip_openings` | invariato | la copertura qui e' un'«apertura» | vedi par. 3 |
| `:1882-1951` `lay_in_volo`, `_una_sola_lay` | CAMBIA | su OU45: UNA banca per MERCATO | banca di chiusura sull'Over con la copertura sull'Under ancora in volo |
| `:1954-1969` `copertura_in_volo` | CAMBIA | qualunque `over_cover` in volo sul MERCATO | al cambio di versione: punta Over vecchia viva + banca Under nuova = DOPPIA COPERTURA |
| `:2023-2074` `_freno_copertura` | OK | per ruolo | - |
| `:3240-3270` `frazione_copertura` | CAMBIA | con `lay`: minimo `IT_LAY_MIN` | - |
| `:3273-3412` `_decide_uncovered` | **CAMBIA** | oggi libro Over (`:3301`), puntata (`:3333`), eccedenza (`:3369-3382`), `back_size` (`:3389`), `_place(... SEL_OVER, "back")` (`:3398`). Dopo, secondo `cover_form`: libro `(OU45, UNDER)`, `cover_residual_lay`, controllo eccedenza solo per la puntata, liquidita' su `lay_size`, rischio calcolato sul prezzo limite, `_place("over_cover", OU45, UNDER, "lay", q_lim, X)`. Libro Under assente: attesa col motivo | ordine dal lato sbagliato |
| `:3425-3498` `_decide_cover_pending` | CAMBIA | il riprezzo legge il libro della forma scelta | riprezzo che rifa' la puntata Over |
| `:3511-3651` `_decide_covered`, `_decide_closing` | OK dopo `exposure` | - | - |
| `:3711-3808` rientro | OK SOLO con `exposure` per mercato | - | banca del rientro sbagliata |

### `Betfair/mike/service.py`
| Punto | Stato | Nota |
|---|---|---|
| `:552`, `:559-564`, `:656-690`, `:700`, `:718-723`, `:746`, `:1330-1346` | OK | rischio della banca, freni per ruolo, controllo di prezzo taker, legalizzazione solo delle puntate |
| `:2760-2869` `_sorveglia_posizione_di_conto` | **CAMBIA** | usa `open_selections` (`:2784`): con la chiave lunga `(OU45, OVER)` l'atteso sull'Over e' 0 e a `:2803` salta: la banca Under non verrebbe MAI controllata sul conto. Dopo: controllare ogni selezione con gambe non archiviate nei mercati non piatti. Rischio: chiusura fatta dall'utente fuori dall'app sul mercato 4,5 invisibile |
| `:2965-3004` `_sorveglia_mercato_copertura` | CAMBIA | leggere il libro della forma scelta; testi |
| `:4059-4068` (annullo del falso regolamento) | OK con la chiave lunga | con la logica per selezione finirebbe in `REENTRY_OPEN`: stato sbagliato |
| `:4186-4207`, `:4289-4296` | CAMBIA | `F.EventInfo.complete` (`feed.py:37-41`) non richiede `(OU45, UNDER)`: se manca l'id dell'Under 4,5 `execute_place` annulla a `:640-643` senza `_rifiutata` e senza orologio del ritmo = riproposta a ogni giro. Proteggere nel motore: «libro Under 4,5 assente -> attesa» |

### Fuori da Mike
- `Betfair/safe_strategy/execution.py:71-89`: minimo della banca gia' 0,50. `:737-768`: una banca da
  12,63 parte diretta; sotto 0,50 va nel piazza e riduci e per Mike (tutto o niente con limite
  abbinabile) viene rifiutata prima di toccare Betfair: il rifiuto conta per il freno della
  copertura (dopo 3 si blocca).
- `Betfair/stream/motore_ordini.py:1023-1037` `_riduzione_verificata`: legge le esposizioni PER
  SELEZIONE. La banca Over che chiude una banca Under non risulta una riduzione: con kill-switch o
  guardia d'avvio armata il runner (paper sul canale) la RIFIUTA (`:951`, `:964`). Differenza nuova
  fra paper e live (il live REST non e' toccato).

### Database (`migrations/`)
`mike_vincoli_flusso_fischio_2026-09-14.sql:63-69` (CHECK su `strategy`): `over_cover` e `over_close`
gia' ammessi. `mike_bot.sql:95` (CHECK su `side`): OK. Nessun vincolo sulla selezione. Storico e
aggregati raggruppano per ruolo: OK dopo `opening_ref`.
DA FAR VERIFICARE ALL'UTENTE sul database vero (sola lettura):
`SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='public.mike_trades'::regclass;`

### Banco (`Betfair/mike/certificazione.py`, `Betfair/mike/tools/replay_registrazioni.py`)
| Controllo | Oggi | Dopo |
|---|---|---|
| E2 `:343-367` | salta le banche: con la banca diventa MUTO | ramo per la banca: atteso = F x S / (1 - c) |
| J6 `:572-642` | usa quota Over e formula della puntata | ramo per la banca, altrimenti FALSO ROSSO |
| S2 `:739-757` | legge il libro Over | libro della selezione dell'azione |
| J5 `:529-570` | per selezione | aggiungere J5-bis per mercato su OU45 |
| scenario `copertura-rifiutata` (`replay_registrazioni.py:109-156`, `:854-863`) | stake 3,00 per portare la copertura sotto 2,00; rifiuta `lato back` sotto 2,00 | con la banca da 3,79 NON SCATTA PIU': S1 e S3 restano senza casi in silenzio. Serve la leva «rifiuta la banca sull'Under 4,5» in `Betfair/stream/backtest/banco_comune.py:507-560` |
| `Betfair/stream/backtest/chiusura_parziale.py` CP3, CP4 `:836-848` | per selezione | verificare che la banca Over di chiusura non dia un falso «ribaltata» |
Difetto gia' presente in E2, non causato da P5: legge `params["commission"]` e
`params["cover_factor"]` che non esistono (usa sempre 0,05 e 1,2: oggi innocuo).

### Frontend
`frontend/src/lib/mike.ts`: `:1050-1053` `investedOf` (come `invested`); `:1068-1076`
`selectionExposure` e `:1107-1130` `positionRows` (compensare per mercato, altrimenti dopo la
chiusura mostrano due posizioni aperte); `:1055-1059`, `:1483` e i testi «Over 4.5» (`:431`, `:483`,
`:488`, `:500`, `:509`, `:641-643`); `MIKE_PARAM_FIELDS` / `MIKE_PARAM_DEFAULTS`: aggiungere
`cover_form` (obbligatorio: lo pretende il test di contratto
`test_mike_certificazione_ui_2026_09_11.py:112,158`; `BACKEND_ONLY_PARAMS`, `config.py:424`, deve
restare vuota). Altre etichette: `components/mike/MikeMatchCard.tsx:749-761`,
`components/controlroom/SchedaMike.tsx:78,161`, `components/trading/PerformancePanel.tsx:45`,
`components/trading/DayDetail.tsx:59`, `lib/dailyHistory.ts:1034-1035`,
`components/controlroom/DettaglioRigaView.tsx:233`, `pages/Mike.tsx:716`.

### Test Python
31 file citano `over_cover` / `SEL_OVER` (i piu' pesanti: `test_mike_engine_cert_2026_09_12.py`,
`test_mike_freno_copertura_2026_09_17.py`, `test_mike_engine.py:466`). Leggono i parametri di serie:
quando il valore di serie diventa la banca vanno FISSATI su `cover_form="back_over45"` (restano
verdi senza cambiare le asserzioni) e affiancati da un gemello `lay_under45`.

## 2. Formule nuove (verificate con numeri)
Simboli: L = perdita netta dell'Under 3,5; F = 1,2; c = 0,05; A = gia' coperto (netto a 5 gol delle
gambe OU45 non archiviate); f = frazione della tranche; q = quota della banca Under 4,5; p = quota
Over 4,5.
1. **Importo della banca: X = max(0, (F x L - A) / (1 - c)) x f**, al centesimo. NON dipende dalla
   quota. Rischio = X x (q abbinata - 1). Per `liability_room` si usa il rischio al prezzo LIMITE:
   se supera lo spazio, X = spazio / (q_lim - 1). Equivalenza: q = p / (p - 1).
2. **Esempio guida:** punta Under 3,5 10,00 a 1,50 -> X = 12 / 0,95 = 12,63; rischio a 1,18 = 2,27;
   esiti +2,48 (0-3 gol) / -12,27 (4 gol) / +2,00 (5+). Oggi con punta Over 2,26 a 6,60: +2,49 /
   -12,26 / +2,02. Al limite 1,20 rischio massimo 2,53. Capitale impegnato 12,27, soglia 5 % = 0,61.
3. **Piu' tranche:** A si ricalcola sempre dai fill. Posizione 15 EUR: copertura piena 18,95; prima
   tranche 9,47; dopo il fill A = 8,9965; seconda tranche (18 - 8,9965)/0,95 = 9,48. A meta'
   versione (1,00 di punta Over a 6,6 gia' abbinata): A = 5,32 -> banca residua 7,03.
   DIFETTO GIA' PRESENTE (anche con la puntata): prima tranche abbinata in parte (5,00 su 9,47) e
   annullata -> il riprezzo chiede 0,5 x (18 - 4,75)/0,95 = 6,97: la prima tranche arriva al 63 %
   invece del 50 % (`engine.py:3485-3486`).
4. **Annullare la copertura bancando l'Over:** W_u = P&L se vince l'Under, W_o = se vince l'Over,
   D = W_o - W_u > 0; banca Over al miglior prezzo p: s = D / p; bloccato = W_u + s. Esempio con
   Under 4,5 a 1,05 (Over a 21): D = 14,9034, s = 0,71; esito -1,56 / -1,57. Cash out al 40':
   Under 3,5 +2,38, copertura -1,56, totale +0,81 >= 0,61: chiude.
5. **Banca equivalente sotto 0,50** (esempio q = 1,02, p = 51, s = 0,29; puntata equivalente 14,61):
   se la puntata equivalente e' un multiplo di 0,50 da almeno 2,00 -> `over_close` come punta Under;
   altrimenti banca Over diretta. NOTA: nel codice il «piazza e riduci» per le CHIUSURE non esiste
   (`execution.py:768` esenta le chiusure, che partono dirette).
6. **Cuscinetto:** limite = `ticks_away(best_lay_U45, +cover_place_at_ticks)`: 1,18 -> 1,20. La size
   non si ridimensiona sul limite. Commissione per mercato, gia' cosi'.

## 3. Interazioni pericolose
1. **Copertura e rientro sulla stessa selezione.** Dopo la chiusura il mercato 4,5 contiene: banca U
   12,63, banca O 0,71, punta U del rientro, banca U di green del rientro (le gambe di copertura non
   vengono archiviate al passaggio a FLAT, `_decide_closing:3625`). Per selezione: banca Over NUDA
   (-14,2 con 5+ gol). Per mercato: corretto. TEST OBBLIGATORIO con mutazione. In piu':
   `_decide_reentry_open` (`:3746`) e `_decide_reentry_green_pending` (`:3793`) giudicano il piatto
   con `_FLAT_EPS` = 0,01; con la compensazione ci entra il resto di arrotondamento della chiusura
   (fino a 0,005 x p, circa 0,10 a p = 21). Proposta: piatto = la chiusura arrotondata al centesimo
   vale 0,00 (|D|/p < 0,005). Da dichiarare e provare.
2. **Una sola banca a mercato:** `_una_sola_lay` e `lay_in_volo` per mercato su OU45.
3. **Ordini sulle due selezioni:** servono INSIEME compensazione, `ordini_vivi_su` per mercato,
   lettura del conto per selezione, `_riduzione_verificata`, scheda.
4. **Freni che trattano la copertura come apertura:** invariati da P5 (M8.3 e' in P4).
5. **Ordini a esito ignoto:** la banca di copertura a esito ignoto conta per intero in
   `event_liability`; `copertura_in_volo` la vede e blocca una seconda copertura.
6. **Tetto per partita** (`max_liability_per_match`, di serie 0 = spento): conta il rischio (2,27),
   non l'importo (12,63). Scenario `cap-stretto` (tetto 12): banca ridotta a 2,00/0,20 = 10,00.
7. **Partite gia' in corso al momento dell'aggiornamento:** `LIVE_UNCOVERED` -> forma nuova;
   `LIVE_COVER_PENDING` con la punta Over vecchia viva -> il riprezzo la annulla e la banca Under
   parte SOLO al giro dopo la conferma (`copertura_in_volo` per mercato); `LIVE_COVERED` con punta
   Over -> chiusura identica a oggi; regolamento generico. Nessun campo nuovo nel contesto salvato
   (`_CTX_FIELDS`, `service.py:274`). Da provare con uno scenario apposito.
8. **Liquidita' separata** (`crossMatching: false` nella registrazione 35760084): banca Under e punta
   Over pescano da libri diversi. Il rischio di una banca non e' limitato dall'importo: con un prezzo
   lay assurdo esplode; oggi `cover_max_goals` = 2 lo tiene fuori (i casi anomali trovati, 35674515
   al 26'-28' con Under 4,5 lay 4,9-5,0, sono tutti con 4 gol).

## 4. Strategia di migrazione
- Ruolo: si tiene `over_cover` con `side='lay'` e `selection=UNDER`; la forma in `meta.cover_form`.
  Niente SQL. L'alternativa (ruolo nuovo) richiede una migrazione PRIMA del codice e tutti i
  consumatori per ruolo: sconsigliata.
- Interruttore: `PARAM_SPEC["cover_form"] = ("lay_under45", str, None, None, ("lay_under45",
  "back_over45"))` in `config.py` vicino a `:187-203`, esposto nella pagina dei parametri. Per
  tornare indietro: `back_over45` dall'app, dal giro successivo. La compensazione per mercato resta
  in entrambe le forme.

## 5. Piano di prova
Test del motore, ognuno con la mutazione che deve farlo diventare rosso:
| # | Test | Mutazione |
|---|---|---|
| 1 | Esempio guida (12,63; +2,48 / -12,27 / +2,00) | usare `cover_residual` della puntata |
| 2 | Copertura + chiusura sull'Over: `open_selections` vuoto, `locked_pnl` circa -1,56 | togliere il ramo «altra selezione» in `exposure` |
| 3 | Rientro dopo la copertura-banca: green dimensionata sul solo rientro, nessuna banca Over nuda | come sopra |
| 4 | `over_close` riceve `closes_ref` = copertura; `reentry_green` -> `reentry` | ripristinare il filtro `side=="back"` in `opening_ref` |
| 5 | `invested` = 12,27 | contare solo le puntate |
| 6 | Cuscinetto 1,18 -> 1,20 | segno -n |
| 7 | Due tranche 9,47 / 9,48 | A della sola ultima gamba |
| 8 | Punta Over vecchia viva + riprezzo: nessuna banca Under nello stesso giro | `copertura_in_volo` per selezione |
| 9 | Banca di chiusura Over bloccata finche' la banca Under e' in volo | `_una_sola_lay` per selezione |
| 10 | Residuo sotto 0,50 (regola scelta dall'utente) | - |
| 11 | Libro Under 4,5 assente: attesa, nessun ordine | - |
| 12 | Interruttore `back_over45`: ordine identico a `test_mike_engine.py:466` | - |
| 13 | Conto: selezione Under controllata | `open_selections` in `_sorveglia_posizione_di_conto` |
| 14 | Falso regolamento con copertura-banca -> `LIVE_COVERED` | - |
Banco: ricalibrare E2, J6, S2, aggiungere J5-bis; `copertura-rifiutata` sulla banca Under 4,5 con
`cover_rifiuti_max` 1 piu' il gemello `copertura-rifiutata-legacy`; scenari nuovi `copertura-legacy`,
`cambio-forma-in-corsa`, `copertura-banca-parziale`, `cashout-dopo-copertura-banca`; rientro dopo
copertura-banca su una registrazione adatta. Accettazione: i 15 scenari di oggi piu' i nuovi a 0
violazioni; riferimento 446 s con tre processi.

**Misura preliminare (sola lettura, 20 registrazioni, un campione ogni 10 s fra il 3' e il 60',
4.392 campioni):**
| Cosa | Risultato |
|---|---|
| Banca Under 4,5: liquidita' al miglior prezzo sotto 12,63 | 7,6 % dei momenti |
| Stessa cosa entro +2 tick | 1,4 % |
| Liquidita' sotto 18,95 (miglior prezzo / entro +2 tick) | 12,2 % / 2,2 % |
| Nessun prezzo lay sull'Under | 1,1 % |
| Chiusura (banca Over): liquidita' al miglior prezzo sotto D/p | 5,2 % |
| Nessun prezzo lay sull'Over | 3,1 % |
| Rischio in piu' della banca rispetto alla punta (stake 10, Over fino a 15) | mediano +0,03 EUR, p90 +0,10 EUR |
| Solo 35760084: al miglior prezzo sotto 12,63 | 38 % dei momenti |
Misura definitiva da fare: sui momenti VERI di copertura e chiusura del replay `base` (telemetria
`cover` e `cashout`) di tutte le registrazioni.

## 6. Ordine dei passi
| Blocco | Contenuto | File | Si verifica con |
|---|---|---|---|
| 0 | Misura definitiva; replay di riferimento con impronta delle transizioni | sola lettura | - |
| 1 | Compensazione per mercato SENZA cambiare nessuna decisione di oggi: `exposure`, `open_selections`, `invested`, `opening_ref`, `ordini_vivi_su`, `lay_in_volo`/`_una_sola_lay`, `copertura_in_volo`, `posizione_per_selezione`, `riepilogo_cicli`; nel servizio `_sorveglia_posizione_di_conto` | `engine.py`, `service.py`, test 2, 3, 4, 5, 8, 9, 13 | suite intera verde SENZA toccare i test vecchi; replay a 15 scenari con transizioni identiche |
| 2 | `cover_form` (di serie `back_over45`) e ramo della banca | `config.py`, `engine.py`, `frontend/src/lib/mike.ts` (campo del parametro), test 1, 6, 7, 10, 11, 12, 14 | - |
| 3 | Servizio: libro della forma in `_sorveglia_mercato_copertura`, testi, `meta.cover_form`; `_riduzione_verificata` per mercato | `service.py`, `motore_ordini.py` | - |
| 4 | Banco: E2, J6, S2, J5-bis, leva di rifiuto, scenari nuovi | `certificazione.py`, `tools/replay_registrazioni.py`, `stream/backtest/banco_comune.py` | replay su entrambe le forme |
| 5 | Valore di serie -> `lay_under45`; test vecchi fissati a `back_over45`, dichiarato | `config.py`, test | suite, vitest, tsc a 0 errori, replay completo con tempi |
| 6 | Interfaccia: `investedOf`, `positionRows`, etichette e testi | `mike.ts` e componenti | `npm run build` |
| 7 | Documenti: Costituzione, inventari, guida, registro del piano | - | - |

## 7. Non verificato e domande
Non verificato: i vincoli reali sul database; se Betfair accetta via API una banca di chiusura sotto
0,50 (oggi `over_close` ha gia' le stesse cifre: non e' un rischio nuovo); lo scenario di rientro
dopo la copertura-banca su una registrazione reale; la misura sui momenti veri di copertura; CP3 e
CP4 sulle due selezioni.
Domande per l'utente:
1. Liquidita': oggi Mike copre solo se al miglior prezzo c'e' tutto l'importo. Tenere la regola o
   contare la liquidita' entro i 2 tick del cuscinetto?
2. Residuo sotto 0,50 dopo un abbinamento parziale: portarlo a 0,50 o considerarlo coperto?
Decisioni tecniche (del coordinatore): tenere il nome `over_cover` (niente migrazione); correggere
`_riduzione_verificata` per mercato, perche' il paper deve essere lo specchio del live.
