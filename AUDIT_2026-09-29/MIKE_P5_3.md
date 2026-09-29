# CANTIERE MIKE-COPERTURA - P5 blocco 3: servizio e motore ordini (29/09/2026)

Base: `08b9c6a` + `MIKE_P2BIS.patch` + `MIKE_P5_2.patch` + `MIKE_P5_2B.patch`. Patch:
`AUDIT_2026-09-29/MIKE_P5_3.patch` (17,6 KB), sopra `MIKE_P5_2B.patch`. Nessun commit.

## 1. Righe toccate
| File | + / - | Cosa |
|---|---|---|
| `Betfair/mike/service.py` | +30 / -8 | `_selezione_copertura` (nuova); `_sorveglia_mercato_copertura` con argomento FACOLTATIVO `params` (legge il libro della selezione della copertura, testi con l'etichetta giusta, campo `selezione` nell'attivita'); la sua unica chiamata in `_run_event` passa `params=params`; `_trade_row` scrive `meta.cover_form` sulle righe `over_cover` |
| `Betfair/stream/motore_ordini.py` (CONDIVISO) | +30 / -2 | `altro_runner_due_esiti` (nuova, pura); `_riduzione_verificata`: SOLO se la verifica per selezione dice no, e SOLO su un mercato con esattamente due runner, si somma l'altra selezione rovesciata |
| `Betfair/mike/tests/test_mike_p5_servizio_copertura_2026_09_29.py` | nuovo, 4 test | |
| `Betfair/stream/tests/test_motore_ordini_mercato_due_esiti_2026_09_29.py` | nuovo, 4 test | fixture vero del motore (`amb`) + `MarketBook` VERO di betfairlightweight |

Non toccato (dominio del delegato degli ordini): `_sorveglia_gambe`, sospensione, riconciliazione,
regolamento. I testi "copertura Over 4.5" nelle attivita' del freno (`service.py` intorno alla riga
1040) restano: sono etichette, da P6/documenti.

## 2. Perche'
- `_sorveglia_mercato_copertura` leggeva sempre il libro Over 4,5: con la copertura-banca una
  sospensione dell'Under 4,5 non veniva mai detta. Regola: una copertura gia' sul book (viva o a esito
  ignoto) decide il libro (al cambio di forma la punta Over vecchia si sorveglia sull'Over); altrimenti
  la forma scelta (`cover_form`). Senza `params` (chiamanti vecchi, test) = Over, come prima.
- `meta.cover_form` sulla riga: il ruolo resta `over_cover` (niente migrazione); la forma si legge
  dall'ordine stesso (banca sull'Under = `lay_under45`, altrimenti `back_over45`). Chiave NUOVA nel
  meta, aggiunta: nessuna colonna, nessun vincolo.
- `_riduzione_verificata` (paper sul canale con kill-switch o guardia d'avvio): la banca Over 4,5 che
  annulla la copertura-banca Under 4,5 non risultava una riduzione (sulla selezione Over non c'e'
  niente) e veniva RIFIUTATA: il paper diverso dal live REST. Ora, su un mercato a due esiti, si
  guarda il mercato.

## 3. Per gli altri bot non cambia niente (e perche')
Il ramo nuovo scatta solo dove prima la risposta era "non verificata" e solo con due runner: un caso
gia' verificato resta verificato identico; con tre o piu' runner (Match Odds, Correct Score) nessuna
somma (test). L'unico effetto possibile per un altro bot: una chiusura che riduce DAVVERO la posizione
del mercato a due esiti, prima rifiutata, ora passa. Suite:
- `Betfair/stream/tests`: **3093 verdi**, 25 saltati;
- `Betfair/omega Betfair/safe_strategy -k "motore or canale or porta or ordini or scalper or kill or
  guardia"`: **404 verdi**, 1 xfail (preesistente);
- `Betfair/mike`: **1191 verdi**, 2 rossi attesi del contratto UI (`cover_form` non ancora in
  `mike.ts`, righe nel referto del blocco 2).

## 4. Test e mutazioni (`AUDIT_2026-09-29/mike_p5/falsifica_mike_p5_3.py`, esito `..._3.txt`)
6 mutazioni, 6 ROSSE: S1 sorveglianza sempre sull'Over; S2 la copertura sul book non decide il libro;
S3 `meta.cover_form` non scritto; M1 riduzione solo per selezione (il comportamento di prima); M2
somma anche con tre esiti; M3 altra selezione non rovesciata (fa anche PASSARE una banca che aumenta
la posizione: il test "resta rifiutata" diventa rosso). Ripristino verificato (hash, nessuna MUTAZIONE).
Lo script comune ora ripristina tutti i file toccati dalle mutazioni (non solo `engine.py`).

## 5. Replay (ambiente neutro, `--worker 0`)
`35760084 --scenari copertura-rifiutata --trasporto entrambi`, misurato senza e con il blocco 3 sullo
stesso codice (blocco 3 tolto con `git apply -R` e rimesso con controllo dell'hash):
coda e canale **IDENTICI**, 0 violazioni, 158 s / 168 s (PC carico). "PARITA' coda/canale NON
RAGGIUNTA" identica nei due (preesistente). Con la forma di serie il ramo nuovo del motore non ha casi
(nessuna banca Over su una banca Under): la sua prova vera e' nel banco del blocco 4.

## 6. Parita' paper/live
Il live REST (`execute_place` -> `execution`) non passa da `_riduzione_verificata`: la correzione
porta il paper sul canale allo stesso esito del live (chiusura accettata). Servizio: nessun ramo per
modalita'.

## 7. Non verificato
- La forma banca nel servizio intero a cadenza reale (`run_once`) e sul banco: blocco 4.
- Il comportamento vero del kill-switch in live sulla banca Over di chiusura (il live REST non passa
  dal motore; nessuna chiamata a Betfair).
