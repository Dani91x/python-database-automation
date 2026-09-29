# CANTIERE MIKE-COPERTURA - P5 blocco 1 (M3.4): i conti del mercato 4,5 PER MERCATO (29/09/2026)

Base: master `6cc91a0` (riallineato; lavoro nato su `94e165c` e riapplicato con `git apply --3way`,
nessun conflitto). Patch: `AUDIT_2026-09-29/MIKE_P5_1.patch` (`git apply --check --cached` su
`6cc91a0`: applica pulita). Nessun commit. Nessuna decisione di trading cambiata nella forma di oggi
(copertura = punta Over 4,5): replay identico al riferimento, scenario per scenario.

## 1. Righe toccate
| File | + / - | Cosa |
|---|---|---|
| `Betfair/mike/engine.py` | +180 / -28 circa | vedi sotto |
| `Betfair/mike/service.py` | +4 / -1 | `_sorveglia_posizione_di_conto`: il ciclo scorre `E.selezioni_da_sorvegliare(ctx.legs)` invece di `sorted(aperte)` (una riga) |
| `Betfair/mike/tests/test_mike_conto_e_sovracopertura_2026_09_16.py` | +38 / -3 | UN test vecchio rovesciato (autorizzato dal coordinatore) + 2 gemelli di confine |
| `Betfair/mike/tests/test_mike_p5_compensazione_mercato_2026_09_29.py` | nuovo, 19 test | |

`engine.py`, funzione per funzione (tutte ritrovate per nome; firme esistenti invariate, solo
`opening_ref` riceve un argomento FACOLTATIVO in coda):
- `exposure`: conta TUTTE le gambe del mercato; una gamba sull'altra selezione pesa rovesciata
  (punta Y: `w -= s; l += s(p-1)`; banca Y: `w += s; l -= s(p-1)`). Con gambe su una sola selezione:
  stesse gambe, stesso ordine, stessi conti (bit per bit).
- nuove `selezioni_con_gambe`, `_chiave_ou45`, `selezioni_da_sorvegliare`, `_stessa_posizione`.
- `open_selections`: UNA chiave per mercato. OU35 -> `(OU35, UNDER)` come prima. OU45:
  gambe su una sola selezione -> quella selezione, ESATTAMENTE come prima (anche un residuo corto di
  arrotondamento resta dov'era: nessun ordine nuovo da un centesimo), salvo il caso nuovo "corto nato
  da una BANCA di apertura" (copertura banca Under) -> chiave sull'altra selezione, quella lunga, cosi'
  la chiusura e' una banca Over (M3.3). Gambe sulle due selezioni -> la selezione LUNGA.
- `invested`: puntate di apertura + rischio delle banche di apertura (abbinato x (prezzo-1)).
  12,27 sull'esempio guida. Nella forma di oggi non esistono banche di apertura: identico.
- `opening_ref(legs, market, selection, role=None)`: ruolo di chiusura -> apertura
  (`over_close`->`over_cover`, `reentry_green`->`reentry`, `under_green`/`ko_green`/`under_close`->
  `UNDER_ROLES`, altri -> `OPENING_ROLES`); prima la stessa selezione (come prima), poi il mercato;
  tolto il filtro `side=="back"`. `apply_decision` passa `a.role`.
- `ordini_vivi_su`, `lay_in_volo`, `copertura_in_volo`, il controllo "altra lay" di
  `_decide_flatten`: per MERCATO (`_stessa_posizione`). Firme invariate.
- `riepilogo_cicli`: lo stake del ciclo somma il rischio delle banche di apertura (il prezzo
  d'ingresso resta quello delle puntate).
- `posizione_per_selezione`: `abbinato` somma le gambe del mercato (le due selezioni) e c'e' il
  campo NUOVO `abbinato_per_selezione` ({selezione: {back, lay}}). Presentazione; nella forma di oggi
  cambia solo durante il rientro (la riga Under 4,5 conta anche le gambe Over della copertura chiusa).

## 2. Collegamenti controllati (grep prima e dopo)
- `exposure`: `under_liability` (OU35, invariato), `open_selections`, `cashout_value`,
  `posizione_per_selezione`, `_decide_closing` (riprezzo), `_decide_reentry_pending/_open/
  _green_pending`, 4 chiamate OU35 nel pre-partita/fischio (invariate: solo Under sul 3,5).
- `open_selections` / `live_open_selections`: engine (cashout, locked_pnl, flatten, covered,
  closing, flat) e servizio `:2784`, `:3124`, `:3346`, `:4059`, `:4191`, `:4240`, `:4271`, `:4280`,
  `:4289-4290` (numeri su `94e165c`): tutti usano la chiave, nessuno la selezione delle gambe salvo il
  conto (corretto).
- `copertura_in_volo` / `_mai_sovracopertura`: chiamati SOLO da `engine.py` (`decide`) e dai test;
  NON dal servizio ne' da `certificazione.py` (grep: nessun uso fuori da mike/engine e mike/tests;
  gli omonimi in `safe_strategy/certificazione*.py` e `tennis_scalper` sono funzioni diverse).
- `lay_in_volo`: `_una_sola_lay` e `engine :2777` (OU35). `ordini_vivi_su`: solo `_close_actions`.
- `opening_ref`: solo `apply_decision` e test. `invested`: `cashout_base`, `liability_room`,
  servizio `:4662` (scheda).

## 3. Test vecchio modificato (unico, autorizzato dal coordinatore)
`test_copertura_in_volo_su_UNALTRA_selezione_non_conta` -> `test_copertura_in_volo_su_UNALTRA_selezione_del_mercato_4_5_CONTA`:
stesso scenario; prima asseriva che una copertura in volo sull'Under 4,5 non ferma una copertura
sull'Over 4,5; ora (M3.4 + ordine dell'utente 16/09 "MAI SOVRACOPERTURA") la copertura nuova e'
rimandata, 0 piazzamenti, stato che non avanza. Gemelli di confine: copertura in volo su ALTRO
mercato non ferma; gamba di altro ruolo (`reentry_green`, `over_close`, `reentry`) in volo sul 4,5
non e' una copertura. Nessun test cancellato o saltato.

## 4. Test nuovi (19) e falsificazione
Esempio guida in forma banca, compensazione rovesciata (punta e banca), mercato piatto dopo la
chiusura banca Over con `locked_pnl` -1,57, cash out che non disfa la chiusura, chiave lunga e
chiusura banca Over 0,71 a 21 (M3.3), residuo corto della forma di oggi sulla sua selezione, rientro
dopo la copertura-banca (green 13,0066/prezzo, mercato piatto su ogni totale, nessuna banca Over
nuda), `closes_ref` per ruolo, capitale impegnato 12,27 e `liability_room`, copertura in volo per
mercato (x2), una banca per mercato (x2), chiusura manuale che aspetta la banca Under a esito
ignoto, cancel della copertura viva sull'altra selezione, conto che controlla l'Under 4,5
(`_sorveglia_posizione_di_conto` in live con ordini snake_case come `omega_market`), selezioni da
sorvegliare nella forma di oggi. Sono i test 2, 3, 4, 5, 8, 9, 13 del progetto piu' altri.

Script: `AUDIT_2026-09-29/mike_p5/falsifica_mike_p5_1.py` (copia in memoria + hash, esito in
`falsifica_mike_p5_1.txt`), rieseguito su `6cc91a0`: 12 mutazioni, 12 ROSSE
(M1 ramo punta altra selezione, M1b ramo banca, M2 filtro `side==back`, M3 invested solo puntate,
M4 `copertura_in_volo` per selezione, M5 `lay_in_volo` per selezione, M6 conto su `open_selections`,
M7 `ordini_vivi_su` per selezione, M8 chiave corta, M9 riepilogo senza rischio banche, M10 flatten
per selezione, M11 `_stessa_posizione` per selezione). Ripristino verificato (hash identici, nessuna
`MUTAZIONE` nei file).

## 5. Suite
- Su `94e165c`: `Betfair/mike` 1072 verdi (1050 + 22); `Betfair/mike Betfair/stream/tests -k "mike
  or banco or certifica or uscite"` 1427 verdi, 25 saltati.
- Su `6cc91a0` dopo il riallineamento: `Betfair/mike` **1133 verdi** (1110 + 23), 84 s.

## 6. Replay (ambiente neutro di `giro_completo.sh`, 20 interruttori a 0, `--worker 0`)
- Su `94e165c` + blocco 1, `--scenari tutti --trasporto canale`: 15/15 OK, 0 violazioni.
  Confronto con `AUDIT_2026-09-29/replay/mike_tutti_P1.txt` (tolte le righe dei tempi):
  **15 scenari su 15 IDENTICI** (transizioni, azioni, motivi, attivita', fill, P&L).
  Tempo 716 s (679,8 s interni, riga LENTO, PC carico con altri delegati) contro 747 s di P1 nelle
  stesse condizioni: il blocco 1 non rallenta. Referto: `mike_p5/replay_tutti_blocco1.txt`.
- Su `6cc91a0` + blocco 1, `base,cap-stretto,copertura-rifiutata --trasporto canale` (133 s):
  3/3 OK. Contro `mike_tutti_P2_P4_2.txt`: `base` IDENTICO; `cap-stretto` identico (l'unica
  "differenza" e' una riga WARNING di stderr incollata dentro un motivo nel riferimento);
  `copertura-rifiutata` diverso NEI NUMERI DEL BANCO (tick 56098 vs 56229, 150 letture vs 0):
  NON e' il codice. Nel riferimento i primi tre scenari (processi nuovi) hanno tick 56098 e gli altri
  (processi riusati dalla pool) 56229, sempre, in tutti i referti; lanciando solo tre scenari
  `copertura-rifiutata` gira in un processo nuovo. Prova: lo stesso scenario su `--trasporto entrambi`
  (processo nuovo anche nel riferimento `mike_coperture_P2_P4_2.txt`) e' IDENTICO su coda e canale.
  Reperto per il banco (catalogo n. 37, isolamento fra scenari nello stesso processo): il numero di
  tick e di letture dipende da chi ha girato prima nel processo. Non mio perimetro: lo segnalo.
- `copertura-rifiutata --trasporto entrambi` (186 s): coda e canale IDENTICI al riferimento
  `mike_coperture_P2_P4_2.txt`. "PARITA' coda/canale NON RAGGIUNTA" c'e' identica anche nel
  riferimento: preesistente, non mia.

## 7. Parita' paper/live
Solo logica pura del motore (comune a paper e live) e una riga del servizio che gira SOLO in live
(`_sorveglia_posizione_di_conto` esce subito in paper): nessun ramo per modalita' aggiunto.

## 8. Cosa NON ho potuto verificare / cosa resta
- Il replay non esercita mai gambe sulle due selezioni del 4,5 (nessun rientro nella registrazione
  35760084, copertura sempre Over): la compensazione per mercato e' provata dai test, non dal banco
  (arriva col blocco 4: J5-bis, scenari nuovi).
- Il servizio in live contro un conto vero: solo finti.
- Il replay completo su `6cc91a0` (lo fa il coordinatore, come chiesto).

## 9. Da sapere per il blocco 2 (non cambiato qui, nessuna decisione presa)
- DIFETTO GIA' PRESENTE, conservato identico: nella forma di oggi, se la banca Over che chiude la
  copertura lascia un residuo di arrotondamento >= 0,01 (fino a 0,005 x prezzo, ~0,10 a quota 21),
  l'Over resta "aperto" con un piano di chiusura da 0,00 non eseguibile: `cv.complete=False`,
  FLAT -> LIVE_COVERED "esposizione residua" -> "prezzi incompleti" fino al regolamento, niente
  rientro. Non l'ho toccato (cambierebbe transizioni di oggi). Nella forma banca lo stesso residuo,
  se corto sull'Over, diventerebbe una chiusura eseguibile da ~0,05-0,10 sull'Under (ordine doppio
  che l'utente non vuole): nel blocco 2 propongo la regola del progetto (par. 3.1) "piatto = la
  chiusura arrotondata al centesimo vale 0,00" SOLO per il mercato 4,5 con gambe sulle due
  selezioni, dichiarata e provata. Ti chiedo conferma quando consegno il blocco 2.

## 10. Rischi per le partite gia' in corso
Nessuno nella forma di oggi (copertura punta Over, un'unica selezione fino al rientro). Durante un
rientro gia' in corso la green si dimensiona sul mercato: differenza sotto 1 centesimo di sbilancio
(il residuo Over era < 0,01, altrimenti il rientro non partiva). La scheda: `abbinato` della riga
Under 4,5 ora comprende le gambe Over della copertura chiusa.
