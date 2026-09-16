# CHECKPOINT K — SAFE (calcio + tennis) — 16/09/2026

Reperto da chiudere: i controlli di certificazione Safe guardano la DECISIONE.
I 5 difetti del 15/09, reintrodotti in `execution.py`/`bot_service.py`, potrebbero
lasciare il replay verde (e' il punto 36 del catalogo §7, scoperto su Mike).

Obiettivo: famiglia **K** (consapevolezza dell'ordine contro il banco) per Safe
calcio e tennis, scenari `rifiuti-betfair` e sintetica `prezzo migliore`, pool
isolata, e falsificazione dei 5 difetti con tabella difetto -> controlli.

## Stato
- [x] P0 — letture obbligatorie (PROCESSO §6.7/§7.36-37, piano, modello Mike)
- [x] P1 — mappa di cio' che Safe scrive (`safe_strategy_trades`) e di cio' che
      il banco espone (`MercatoFlumine`)
- [x] P2 — `certificazione_k.py` condiviso (K1..K5)
- [x] P3 — aggancio nei due replay + copertura
- [x] P4 — scenari `rifiuti-betfair` + sintetica `_synth_safe_prezzo_migliore`
- [x] P5 — pool isolata (`azzera_cache_di_processo` Safe, elenco esplicito)
- [x] P6 — falsificazione dei 5 difetti (tabella)
- [x] P7 — replay di riferimento + suite + `-m cert`

## Diario
- 16/09 — avvio. Letti §6.7, §7.36-37, famiglia K di Mike
  (`Betfair/mike/certificazione.py:779-930`).
- 16/09 — P1/P2/P3 fatti: `certificazione_k.py` (K1..K6), agganciato a
  `certificazione.py` (calcio) e `certificazione_tennis.py`, chiamato a ogni
  giro dai due replay. `safe_esatto 35797769 --scenari base`: K1..K6 x922,
  0 violazioni, nessun falso positivo.
- 16/09 — P5 (pool isolata): l'elenco esplicito del calcio e' ora UNICO (il
  tennis ci delega). Mancavano `_CONTO_LETTO_A` (throttle 30 s della POSIZIONE
  DI CONTO, per market_id) e `_EVENTI_CHIUSI` (per event_id): dentro
  `--scenari tutti` gli scenari girano sulla STESSA partita nello stesso figlio,
  quindi le chiavi coincidono e il valore del primo sopravvive nel secondo — e'
  esattamente il difetto 37. La copia del tennis era anche SBAGLIATA: svuotava
  `_APERTE`/`_BLOCCO`/`_LETTURA_FEED`/`_SCANNER_TS_CACHE`, che hanno chiavi
  fisse lette senza `.get`. Azzeramento ora anche all'INIZIO di ogni replay.
- 16/09 — P4 (scenari e sintetiche):
  * `rifiuti-betfair` aggiunto a calcio (`rifiuta_lato='lay'`, il lato con cui la
    SPEC APRE) e a tennis (`rifiuta_lato='back'`, il lato con cui il tennis apre).
    Sul calcio si rifiuta UN solo piazzamento e non tre: i piazzamenti di una
    partita Safe sono pochissimi (3 su 35797769) e rifiutarli tutti lascerebbe
    K1/K3/K4/K5 senza nessun caso.
  * la prima stesura di K contava tutti e sei i controlli a ogni giro: nello
    scenario `rifiuti-betfair` (dove NON esiste nessun ordine a mercato) li
    contava tutti ZERO e K2 — l'unico che quello scenario esiste per sollecitare
    — risultava «non lo so». Ora ogni K ha il suo `quando=`.
  * sintetiche «prezzo migliore»: `_synth_safe_prezzo_migliore` (calcio: il LAY
    della SFAVORITA, cioe' il prezzo a cui la BASE banca, cala di un gradino
    VERO della scala Betfair ogni 4 s dal 55'; il BACK della favorita resta a
    1,28 dentro la banda della SPEC, quindi la regola d'ingresso non si tocca) e
    `_synth_safe_tennis_prezzo_migliore` (tennis: il BACK sale di due tick a ogni
    book; il bet delay di 3 s fa abbinare sul book successivo).

## Tabella dei 5 difetti (falsificazione, 16/09)

| # | difetto reintrodotto | calcio (35797769) | tennis (35792939) |
|---|----------------------|-------------------|-------------------|
| a | `customer_order_ref` letto come `customerOrderRef` (2 punti di `bot_service`) | **K3** x922/919/763 | **K3** x397/399/380 |
| b | `res.ok` ignorato in `execution.place` (rifiuto = copertura esistente) | **K2 K4 K5** + J2 T2 | **K2 K4** + J2 |
| c | `avg_price` al posto di `avg_price_matched` | **K1** x733/919 + J3 (anche su `_synth_safe_prezzo_migliore`: K1 x300) | ⊘ vedi sotto |
| d | ref di riconciliazione diverso da quello di piazzamento | **K7** x921 (scenario `timeout-dopo-accettazione`) | copertura condivisa: il difetto vive in `bot_service.reconcile_pending`, lo stesso per i due bot |
| e | `closes_trade_id` in colonna ma NON nel meta | **K6** | **K6** |

⊘ (c) sul TENNIS, con causa: su `banco_comune.replay_evento` (il percorso del
tennis) flumine decide il fill AL MOMENTO DEL PIAZZAMENTO, contro lo stesso
`market_book` che il bot ha appena letto; il bet delay conta i book ma non
sposta il libro su cui l'ordine si abbina. Misurato sulla sintetica: chiesto
1,10, abbinato 1,10 sul book dei 20 s mentre quello dei 25 s offriva 1,12. Sul
calcio riesce perche' la riga dello scanner e' write-on-change e resta indietro
rispetto al book. `execution.place` e' lo STESSO codice per i due bot ed e'
rosso sul calcio. La causa e' nel banco (`Betfair/stream/backtest/`), fuori dai
file che questo incarico puo' toccare: e' un reperto da portare all'utente.

### Cio' che e' stato aggiunto perche' due difetti restavano verdi
- **K7** «nessun ordine ABBINATO resta senza una riga viva che lo dichiari»: e'
  lo specchio di K4 e prende il difetto (d), che K4 non vede perche' quando la
  riconciliazione dichiara la riga mai piazzata la riga NON e' piu' 'open'.
- scenario **`timeout-dopo-accettazione`**: la riga torna in riconciliazione
  senza bet_id mentre l'ordine VERO resta a mercato. E' l'unico modo di dare un
  caso al difetto (d): `esiti-ignoti` solleva PRIMA del piazzamento, quindi li'
  un ordine da ritrovare non esiste proprio.

## Pool isolata — prova
`chiusura-fuori-app` dopo `base` nello STESSO processo, contro la stessa
partita, confrontata con `chiusura-fuori-app` da sola:

| | da solo | pool, elenco VECCHIO | pool, elenco NUOVO |
|---|---|---|---|
| calcio T14 | x918 | x919 | **x918** |
| tennis S4 | x406 | x405 | **x406** |

Con l'elenco nuovo la copertura dentro la pool e' IDENTICA a quella da solo;
con quello vecchio differiva. Lo scarto e' piccolo su questa partita, ma e'
esattamente la differenza che su Mike valeva R3 x0 contro x5837.

## Replay di riferimento con la pool isolata (P7)

| | referti | violazioni | K1 | K2 | K3 | K4 | K5 | K6 | K7 |
|---|---|---|---|---|---|---|---|---|---|
| calcio `safe_esatto 35797769 --scenari tutti --worker 3` | 16 | 0 | 23403 | 922 | 23403 | 23403 | 18746 | 22126 | 23403 |
| tennis `safe_tennis 35792939 35795560 35790650 --scenari tutti --worker 3` | 45 | 0 (69 T7-APPROVAZIONE, dichiarate) | 14481 | 1526 | 14490 | 14435 | 6301 | 7644 | 14481 |

PRIMA di questo lavoro i sette controlli K non esistevano: la copertura era
x0 per tutti e sette e i cinque difetti del 15/09, reintrodotti, lasciavano il
replay VERDE (e' il punto 36 del catalogo §7, misurato su Mike e confermato qui).
Mai sollecitati: calcio 18 su 65, tennis 2 su 34 (T10 e L2, entrambi gia'
dichiarati con causa in `CAUSE_NON_ESERCITABILI`).

Suite: `pytest Betfair/safe_strategy Betfair/stream -q -p no:cacheprovider`
2490 passed. `pytest Betfair -q -m cert` 19 passed.

`execution.py` e `bot_service.py` toccati SOLO dalla falsificazione e ripristinati
byte per byte (md5 verificato a ogni giro; `git diff` vuoto).

## Reperti da portare all'utente
1. ⊘ (c) sul tennis: il banco del tennis abbina sull'ordine al momento del
   piazzamento, contro il book che il bot ha appena letto. Il bet delay conta i
   book ma non sposta il libro dell'abbinamento. Sta in
   `Betfair/stream/backtest/banco_comune.py` (`replay_evento`), fuori dai file
   di questo incarico.
2. Il tennis aveva una SECONDA copia dell'elenco delle cache di processo, piu'
   corta e sbagliata (svuotava dizionari a chiavi fisse letti senza `.get`).
   Adesso e' una sola.
