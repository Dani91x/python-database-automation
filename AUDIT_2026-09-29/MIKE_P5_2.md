# CANTIERE MIKE-COPERTURA - P5 blocco 2: la copertura come BANCA Under 4,5 (29/09/2026)

Base: master `08b9c6a` (blocco 1 gia' su master in `e023a0d`). Patch: `AUDIT_2026-09-29/MIKE_P5_2.patch`
(md5 `1AAC921680BC88E9AFA16D5D5E84C581`, `git apply --check --cached` su `08b9c6a`: pulita).
Nessun commit. **Di serie `cover_form = back_over45`: con i parametri di serie Mike fa esattamente
cio' che faceva** (replay identici, par. 6). La forma nuova si accende col parametro (blocco 5).

## 1. Righe toccate
| File | + / - | Cosa |
|---|---|---|
| `Betfair/mike/config.py` | +9 | `PARAM_SPEC["cover_form"] = ("back_over45", str, None, None, ("lay_under45", "back_over45"))` |
| `Betfair/mike/engine.py` | +341 / -14 | vedi sotto |
| `Betfair/mike/tests/test_mike_p5_copertura_banca_2026_09_29.py` | nuovo, 22 test | |

`engine.py`:
- costanti `IT_LAY_MIN = 0.50`, `COVER_LAY_U45`, `COVER_BACK_O45`; funzioni nuove `cover_form(params)`,
  `cover_residual_lay` (X = max(0, (F x L - A)/(1-c)), non dipende dalla quota),
  `cover_place_price_lay` (limite = miglior lay + `cover_place_at_ticks` tick: 1,18 -> 1,20),
  `_copertura_banca`, `_riprezzo_copertura_banca`, `_banca_di_apertura`,
  `ripiego_chiusura_sotto_minimo`, `tolleranza_piatto_ou45`, `residuo_non_piazzabile`, `_tele_residuo`.
- `cover_legal_size(x, params, side="back")`: argomento facoltativo; su `lay` solo il centesimo (anche
  con `exact_sizes` spento). Chiamanti vecchi invariati.
- `frazione_copertura`: con la forma banca il minimo piazzabile della tranche e' 0,50.
- `_decide_uncovered`: UNA riga di smistamento dopo i controlli comuni (stadio, `cover_enabled`, attesa
  della prima tranche): con `lay_under45` -> `_copertura_banca`. Il ramo della forma di prima e' intatto.
- `_decide_cover_pending`: UNA condizione in piu' prima del riprezzo: con `lay_under45` ->
  `_riprezzo_copertura_banca`. Ramo vecchio intatto.
- `CashoutValue.ripieghi` (campo nuovo con default) riempito da `cashout_value`; `_close_actions` piazza
  sulla selezione del ripiego se c'e' (M3.3 sotto 0,50).
- `_decide_closing`, riprezzo: SOLO se sul mercato 4,5 c'e' una banca di apertura (forma nuova) si
  riprezza sulla chiave del mercato col ripiego; forma di prima: ramo non toccato.
- `_chiave_ou45`, `_decide_reentry_open`, `_decide_reentry_green_pending`: piatto del 4,5 con
  `tolleranza_piatto_ou45` (par. 3). `_decide_closing` (FLAT), `_decide_covered` (FLAT) e le due
  del rientro scrivono `residuo_non_piazzabile` nella telemetria quando c'e'.

`_copertura_banca`, in ordine (stessi controlli della forma di prima, altro ordine): importo
`cover_residual_lay` x frazione; `cover_timing` con la quota Over letta come prima (se manca,
l'equivalente q/(q-1): serve solo a `cover_good_price`); troppi gol -> saltata; liability 0 -> niente;
**libro Under 4,5 assente -> attesa col motivo**; mercato non aperto -> attesa; attesa intelligente o
**nessun prezzo di banca -> attesa col motivo**; importo < 0,01 -> sufficiente; **resto < 0,50 ->
coperta, nessun secondo ordine (M3.5), telemetria `cover_resto_sotto_minimo`**; tetto per partita
sul **rischio al prezzo limite** X x (q_lim - 1) (se non ci sta: X = spazio/(q_lim-1), sotto 0,50 ->
saltata); **liquidita': TUTTO l'importo al miglior prezzo lay (regola di oggi)**; ordine
`over_cover` `OU45|UNDER` `lay` al limite `q_lim`, importo intero. Il punteggio lo legge solo
`cover_timing` (comune, non toccato: la correzione "gol assenti = attesa" del delegato del motore vale
anche qui).

## 2. Collegamenti controllati
`cover_legal_size`: `_decide_uncovered`, `_decide_cover_pending` (forma vecchia, firma invariata),
rami nuovi con `side="lay"`. `frazione_copertura`: `_decide_uncovered`, `_decide_cover_pending`, rami
nuovi; `certificazione.py` non la chiama. `CashoutValue`: costruito solo da `cashout_value`
(grep); letto da engine, servizio (`cv.net`, `cv.complete`, `cv.plans`, `cv.per_selection_net`) e
certificazione: il campo nuovo ha default, nessun lettore rotto. `_close_actions`: 4 chiamate in
`_decide_covered`, 1 in `_decide_closing`, 1 in `force_flat_plan` (firma invariata).
Servizio: `execute_place` non legalizza le banche (`service.py:746` solo `side == "back"`); la
copertura-banca parte diretta. Il libro dell'Under 4,5 per la sorveglianza della copertura e
`_riduzione_verificata` sono il blocco 3.

## 3. Correzione di un difetto gia' presente (separata dalla copertura nuova, autorizzata)
Una chiusura si dimensiona al centesimo: resta uno sbilancio fino a 0,005 x p (a quota 21 circa
0,10). Prima quel resto >= 0,01 teneva la selezione "aperta" con una chiusura da 0,00 non eseguibile:
partita ferma in `LIVE_COVERED` "prezzi incompleti" fino al regolamento, rientro impossibile. Ora sul
mercato 4,5 (una o due selezioni) e' PIATTO se |D| < 0,005 x (prezzo dell'ULTIMA chiusura abbinata
del mercato), cioe' se la chiusura arrotondata al centesimo vale 0,00; senza chiusure abbinate resta
0,01. Sull'Under 3,5 resta 0,01 (test). Il resto non sparisce: e' nel `locked_pnl` e nella telemetria
`residuo_non_piazzabile` (sbilancio, tolleranza, esiti) delle decisioni che portano a FLAT.
Numeri dei test: p = 21, sbilancio 0,09 (0,0043 di banca) -> piatto e scritto; sbilancio 0,138
(0,0066 di banca) -> NON piatto, parte la chiusura `over_close` banca 0,01 a 21.

## 4. Test nuovi (22) e falsificazione
Esempio guida (12,63; esiti +2,48 / -12,27 / +2,00), cuscinetto 1,20 e rischio al limite 2,53, due
tranche 9,47 / 9,48, resto 0,33 sotto 0,50 coperto senza secondo ordine (primo giro e riprezzo),
riprezzo della banca (12,63 al limite 1,23 su best 1,21), libro Under assente, nessun prezzo di banca,
liquidita' 12,00 < 12,63 -> attesa, tetto sul rischio (12 -> 10,00; 13 -> 12,63 intera), banca mai
legalizzata come puntata (`exact_sizes` spento -> 12,63 non 13,00), interruttore `back_over45` =
ordine identico alla forma di prima e di serie invariato, M3.3 ripiego (banca Over 0,24 -> punta Under
12,00 a 1,02; resta banca se la punta sarebbe 11,88; riprezzo che torna banca), nessun ripiego nella
forma di prima, piatto del 4,5 (2 test), 3,5 al centesimo, due selezioni lunghe sull'Over (chiesto dal
coordinatore, mutazione Q5).
Test 14 del progetto (falso regolamento -> `LIVE_COVERED`): il ramo del servizio
(`service.py`, "falso regolamento annullato") decide su `(OU45, OVER) in open_selections`; con la
copertura-banca la chiave e' `(OU45, OVER)` (test del blocco 1 `test_copertura_banca_aperta_si_chiude
_bancando_l_over`): coperto dalla chiave, non da un test del servizio (non l'ho scritto).

Script `AUDIT_2026-09-29/mike_p5/falsifica_mike_p5_2.py` (esito `falsifica_mike_p5_2.txt`), su
`08b9c6a`: **17 mutazioni, 17 ROSSE** (B1 formula della puntata, B2 lettura B senza /0,95, B3 cuscinetto
col segno meno, B4 gia' coperto ignorato, B5/B6 M3.5 tolta nel primo giro e nel riprezzo, B7 libro Under
non controllato, B8 liquidita', B9 tetto sull'importo, B10 ramo banca mai scelto, B11/B12 ripiego,
B13 piatto a 0,05 x p, B14 piatto al centesimo, B15 banca legalizzata, Q5 chiave sempre Under, B16
riprezzo della chiusura sulla selezione della gamba). Ripristino verificato (hash, nessuna MUTAZIONE).

## 5. Suite
`Betfair/mike` su `08b9c6a` + blocco 2: **1172 verdi, 2 ROSSI ATTESI** del contratto pannello/config
(`test_mike_certificazione_ui_2026_09_11.py::test_contratto_parametri_stesse_chiavi_in_ui_e_backend`
e `..._stessi_clamp_scelte_e_default`): manca `cover_form` in `frontend/src/lib/mike.ts`. Righe da
passare al delegato dell'app:
- in `MIKE_PARAM_FIELDS`, gruppo `cover` (vicino a `cover_policy`, riga ~484):
  `{ key: 'cover_form', label: 'Forma della copertura', kind: 'choice', choices: ['lay_under45', 'back_over45'], hint: 'lay_under45 = BANCA Under 4.5 (importo sempre piazzabile, minimo 0,50); back_over45 = PUNTA Over 4.5 (forma di prima, minimo 2,00 e passi da 0,50). Stessa strategia, cambia solo come si scrive l ordine', group: 'cover' },`
- in `MIKE_PARAM_DEFAULTS` (riga ~580): `cover_form: 'back_over45',` (diventera' `'lay_under45'` nel blocco 5).
Filtro `-k "mike or banco or certifica or uscite"` su `Betfair/mike Betfair/stream/tests` (su
`bf48003`): 1516 verdi, 25 saltati, stessi 2 rossi attesi.

## 6. Replay (ambiente neutro, `--worker 0`; su `bf48003` + blocco 1, poi + blocco 2)
Riferimento misurato da me nelle stesse condizioni togliendo il solo blocco 2 (`git apply -R` e
ripristino con controllo dell'hash):
| Replay | solo blocco 1 | + blocco 2 | confronto |
|---|---|---|---|
| `35760084 base,cap-stretto,copertura-rifiutata --trasporto canale` | 3 OK, 0 violazioni, 190 s | 3 OK, 0 violazioni, 218 s | 3/3 IDENTICI |
| `_synth_mike_reingresso base` | OK | OK, 99 s | IDENTICO |
| `_synth_mike_prezzo_migliore base` | OK | OK, 40 s | IDENTICO |
Referti: `AUDIT_2026-09-29/mike_p5/replay_rif_b1_*.txt`, `replay_b2_*.txt`. I tempi variano col
carico del PC (altri replay in corso), non col codice: il blocco 2 con la forma di serie non esegue
nessun ramo nuovo nel giro (una chiamata in piu' a `cover_form` e a `tolleranza_piatto_ou45`).
NON ho rilanciato sul `08b9c6a` (P4 blocchi 4-5 e UI entrati dopo): la patch si applica pulita, la
suite e' verde; il replay completo resta al coordinatore. La forma NUOVA sul replay arriva col
blocco 4 (scenari che accendono `cover_form=lay_under45`).

## 7. Parita' paper/live
Solo motore puro e config: nessun ramo per modalita'. La banca parte diretta in entrambe (il paper
passa dallo stesso `execute_place`). DA VERIFICARE nel blocco 3: `_riduzione_verificata` di
`motore_ordini.py` (paper sul canale) che oggi non riconosce la banca Over di chiusura come riduzione.

## 8. Reperto del banco (chiesto dal coordinatore): numeri diversi fra processo nuovo e riusato
Nasce in `Betfair/mike/service.py:2759-2762` (`_CACHE_DI_PROCESSO`, l'elenco esplicito che
`azzera_cache_di_processo` svuota all'inizio di ogni replay): mancano `_RIPIEGO_REST_ULTIMO`
(`service.py:1199`, tetto del ripiego REST per mercato), `_ULTIMO_STATO_SCANNER` (`:1190`) e i due
promemoria `_FLUSSO_CRITICO` / `_FLUSSO_RIPIEGO` (`:1200-1201`, si azzerano con `.azzera()`), che invece
`svuota_le_cache` (`:392-394`) conosce. In un processo della pool riusato lo scenario eredita gli
istanti dell'ultimo ripiego REST sugli STESSI `market_id` e il promemoria gia' consumato: 0 letture
REST invece di 150 (quindi 18 s di tempo di mercato non consumati: tick 56229 invece di 56098) e
nessuna attivita' `flusso_interrotto_senza_rest` (x28). Catalogo n. 37. Correzione proposta (non
fatta: fuori perimetro, file del delegato degli ordini): aggiungere i quattro nomi
all'azzeramento, con un test "ogni cache di modulo di `svuota_le_cache` e' anche in
`azzera_cache_di_processo`".

## 9. Cosa NON ho potuto verificare
- La forma nuova sul banco (blocco 4) e in paper: solo test del motore.
- Il servizio con la copertura-banca (libro della sorveglianza, testi, `meta.cover_form`,
  `_riduzione_verificata`): blocco 3.
- Se Betfair accetta via API una banca di chiusura sotto 0,50 (oggi le chiusure partono dirette come
  prima; il ripiego sulla puntata copre solo il caso del multiplo di 0,50).

## 10. Rischi per le partite in corso
Di serie nessuno per la copertura (forma di prima). La correzione del piatto (par. 3) cambia il
comportamento solo di una partita ferma in `LIVE_COVERED` "prezzi incompleti" dopo una chiusura con
resto di arrotondamento: al primo giro passa a FLAT (e puo' rientrare, se le condizioni del rientro
valgono), scrivendo il resto nella telemetria.
