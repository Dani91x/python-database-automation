# MIKE - FEED STANTIO: la stessa gamba respinta non si ripropone a ogni giro (02/10/2026)

Ramo locale `mike-feed-stantio-loop` (base master `c190dc8`, ribasato dopo l'avvio da `2c5df69`:
master nel frattempo ha preso solo documenti e `Betfair/conftest.py`, nessun file di Mike,
scanner o banco). Nessun push, nessun ordine vero, nessuna scrittura sul DB, nessun processo
lasciato acceso. Patch: `AUDIT_2026-10-02/MIKE_FEED_STANTIO_LOOP.patch` (`git diff master`).

## 1. Il difetto e la causa

Scenario `lettura-dati-ko` del banco (35760084): KO su master, P1/P2/P3.
`under_green lay 10.12 @ 1.69` proposta 373 volte di fila in HOLD, `no_fill feed_stantio x370`,
376 gambe proposte contro 6 ordini.

**Che cosa l'ha scatenato (diff `ebfab2a -> aa5749a`, «bot MAI ciechi»).**
`Betfair/safe_strategy/scanner.py:411` (`in_post_ko_wait`) e `:448` (`is_monitorable` ... `or
(bool(visto) and in_post_ko_wait(..., esposto))`), usati da
`Betfair/safe_strategy/service.py:2552` (`build_rows`, `esposto=str(eid) in esposti`): dopo
l'orario previsto del fischio la riga di una partita con esposizione di Mike RESTA pubblicata
finche' Betfair non la mette in gioco. Prima la riga spariva all'orario previsto. Nello
scenario la lettura dei dati di Mike cade proprio in quella finestra (KO da 1782835237 a
1782835957 s): Mike, per M8.7 (`service.py:7103`, «nessuna partita viene data per sparita»),
continua a girare sull'ultima riga letta, ora PRESENTE ma STANTIA (`feed_fresh=False`).
Su `ebfab2a` quella riga non c'era: 1147 giri senza riga contro 603, e il motore non decideva.

**Il difetto vero e' in Mike** (gia' latente, la «mai ciechi» lo ha solo reso raggiungibile):
- `Betfair/mike/service.py` (resting, ~riga 5235) ed `execute_place` (~riga 806): con il feed
  stantio la gamba si annulla e si scrive `no_fill feed_stantio`, ma NIENTE arriva al ctx
  (il commento diceva «il motore ripropone quando il feed torna vivo»: in realta' ripropone
  a OGNI giro);
- `Betfair/mike/engine.py` `_decide_prematch` (PRE_OPEN/HOLD, ramo resting): green non viva
  -> ripropone la lay per il residuo. Nessun freno la vede (`tentativo_gia_rifiutato` guarda
  solo `ctx.rifiuti`, che per il feed stantio restava vuoto).

## 2. La correzione (minima, solo Mike; scanner e «mai ciechi» intatti)

- `engine.py:1952` `MOTIVO_FEED_STANTIO = "feed_stantio"`;
  `engine.py:1955` `gia_respinta_a_feed_stantio(ctx, a)`: la STESSA richiesta (gamba, prezzo,
  size) gia' respinta per feed stantio;
  `engine.py:1961` `_tieni_a_feed_stantio(ctx, d, snap)`: SOLO con `feed_fresh=False` toglie
  dalla decisione quelle richieste. Se non resta nessun ordine, lo stato resta quello di
  adesso e gli `updates` non si applicano (stessa regola di `_strip_openings`, CERT. 13/09
  difetto 3; un `attempts+1` consumerebbe i tentativi di chiusura senza ordine). Motivo
  esplicito: «tengo, feed stantio: under_green lay 10.12 @ 1.69 gia' respinta, non si
  ripropone finche' il feed non torna fresco (...)». Annulli e richieste DIVERSE passano.
- `engine.py:3004` chiamata in `_ultime_guardie`: vale su OGNI ramo, compresa la chiusura
  manuale in corso (che esce da `decide` prima del resto).
- `engine.py:1917` `tentativo_gia_rifiutato` ignora il rifiuto per feed stantio (non e' una
  risposta del mercato): al ritorno del feed la gamba parte UNA volta.
- `service.py:816` (`execute_place`) e `service.py:5247` (lay appoggiata, solo se
  `not snap.feed_fresh`, non per il ripiego REST): `_rifiutata(ctx, leg, E.MOTIVO_FEED_STANTIO)`.
  `ctx.rifiuti` e' gia' persistito e si spurga all'archivio del ciclo (`engine.py` `apply_decision`, «i rifiuti dei cicli chiusi»).

Nessuna condotta di strategia cambiata: cosa e quando chiudere/coprire/uscire restano quelli;
cambia solo che la stessa domanda non si ripete finche' il feed e' stantio.

## 3. Casi simmetrici (grep `feed_stantio|feed_fresh|order_fresh` in engine/service)

| Punto | Che cosa respinge | Loop prima? | Dopo |
|---|---|---|---|
| `service.execute_place` (~806) | ogni taker: ingresso, green taker, copertura, chiusure, `manual_close` | si' (stessa domanda a ogni giro) | rifiuto nel ctx, il motore tiene |
| `service` lay appoggiata (~5235) | `under_green`/`ko_green`/`reentry_green` | si' (il caso del replay) | idem |
| `service._comando` cash out (~3856) | richiesta UI rifiutata `feed_stantio` | no (una risposta per richiesta) | invariato |
| `engine._entry_guard` (~3407), ultimo ingresso (~3841), re-ingresso (~4907) | `order_fresh` falso -> nessuna azione | no | invariato |

## 4. Tabella caso -> test (`Betfair/mike/tests/test_mike_feed_stantio_loop_2026_10_02.py`)

| Caso | Test | Prima | Dopo |
|---|---|---|---|
| PRE_OPEN, lay appoggiata, 12 giri stantii, paper e live, servizio intero | `test_green_appoggiata_respinta_a_feed_stantio_non_si_ripropone[paper/live]` | ROSSO (5 gambe under_green nel ctx dopo 12 giri) | 1 gamba, 1 no_fill; ritorno del feed: 1 ordine; giro dopo: nessuno |
| PRE_OPEN ramo taker (`execute_place`), servizio intero | `test_green_taker_respinta_a_feed_stantio_non_si_ripropone` | ROSSO | 1 + 1 al ritorno |
| Motore da solo: tiene e riparte una volta | `test_motore_tiene_a_feed_stantio_e_riparte_una_volta` | ROSSO | verde |
| Il rifiuto per feed stantio non blocca a feed fresco; un rifiuto vero resta | `test_rifiuto_per_feed_stantio_non_blocca_a_feed_fresco` | ROSSO | verde |
| Domanda DIVERSA a feed stantio si propone | `test_una_richiesta_DIVERSA_a_feed_stantio_si_propone` | verde | verde |
| Tenere non applica stato/updates (attempts) | `test_tenere_non_consuma_aggiornamenti_ne_tentativi` | ROSSO | verde |
| In gioco: copertura LIVE_UNCOVERED -> LIVE_COVER_PENDING | `test_copertura_in_gioco_a_feed_stantio_non_si_ripropone` | ROSSO (M3) | verde |
| In gioco: chiusura manuale -> LIVE_CLOSING | `test_chiusura_manuale_in_gioco_a_feed_stantio_non_si_ripropone` | ROSSO (M3) | verde |

Finti: `FakeDB`/`FakeMarket` di `test_mike_service` (firme di `mike/db.py`), righe e payload
di `test_mike_feed` (chiavi vere dello scanner), runner finto sul protocollo vero, oggetti
veri dell'engine, foto in gioco di `test_mike_p5_banco_2026_09_29`.

## 5. Falsificazione (`falsifica_mike_feed_stantio.py` + `_out.txt`)

8 mutazioni del codice di produzione, ripristino da memoria in `finally` e verifica sha256
dei sorgenti: **8/8 ROSSE**. M1 rifiuto non scritto in `execute_place`; M2 non scritto per la
lay appoggiata; M3 filtro spento; M4 filtro anche a feed fresco; M5 `tentativo_gia_rifiutato`
conta il feed stantio (blocco per sempre); M6 lo stato avanza tenendo; M7 updates applicati
tenendo; M8 filtro non chiamato da `_ultime_guardie`.

## 6. Test

- `Betfair/mike` intera: **1546 passati** (49,7 s) prima del ribasamento.
- Dopo il ribasamento: `Betfair/mike` + 35 file del banco/servizi che toccano Mike
  (`Betfair/stream/tests/*banco*|*cert*|*registro*|*strada_unica*|*replay_veloce*` e quelli che
  importano `Betfair.mike`): **2351 passati, 25 saltati, 0 rossi** (243 s).

## 7. Replay (banco comune, `--worker 0`, `_live_raw` del principale)

**lettura-dati-ko** (≈ 51-62 s):

| | decisioni | azioni | esito | no_fill feed_stantio | NETTO |
|---|---|---|---|---|---|
| `ebfab2a` (prima della «mai ciechi») | 4713 | 5 | OK | 0 | -17,70 |
| master `2c5df69` (prima della correzione) | 5219 | 377 | KO P1 P2 P3 | 370 | -17,58 |
| correzione | 5219 | 8 | **OK** | 1 | -17,58 |

Differenze col riferimento `ebfab2a`, azione per azione (sonda `sonda_azioni_mike_scenario.py`,
`replay/sonda_azioni_lettura_ko_{EBFAB2A,DOPO}.json`):
- +506 decisioni: i giri in cui la riga ora c'e' (603 giri senza riga contro 1147): attesa del
  fischio e lettura KO. Durante la lettura KO il motore decide e TIENE (369 «tengo, feed stantio»).
- +3 azioni: 2 ri-appoggi della `under_green` in HOLD a feed FRESCO (t=1782835225,5 e
  1782835318,7) dopo che le sospensioni di Betfair nell'attesa del fischio l'avevano fatta
  scadere (`ordine_scaduto_alla_sospensione`): su `ebfab2a` la riga non c'era e Mike non le
  vedeva. Sono effetto della «mai ciechi», non della correzione, e sono la strategia (una
  banca per ciclo che si rimette se manca). +1 proposta a feed stantio (t=1782835439,6),
  respinta UNA volta (`no_fill feed_stantio x1`): e' l'«1» atteso; poi si tiene.
- Al ritorno del feed la partita e' gia' in gioco: la gamba che parte e' la `ko_green`
  (1782835958,3 contro 1782835953,3 su `ebfab2a`, 5 s di passo dei giri), come su `ebfab2a`.
- NETTO -17,58 contro -17,70: stesso valore di master prima della correzione, quindi
  dovuto alla «mai ciechi» (tempi della `ko_green`/copertura), non alla correzione.

**base,riavvio,feed-stantio** (55-100 s):
- `--trasporto canale` (come i riferimenti del coordinatore): base e riavvio **5879 decisioni,
  6 azioni, NETTO -14,17, 602 giri senza riga**, feed-stantio 1024/0. Confronto
  (`confronta_referti.py`) con lo STESSO run fatto nel worktree col codice di master
  (`engine.py`/`service.py` di `2c5df69` rimessi e poi ripristinati da HEAD): **0 righe
  diverse**. Contro `mike_base_riavvio_feedstantio_INTEGRATA.txt` del principale: diverse
  solo le righe d'intestazione (output di PowerShell e riga «ambiente»).
- coda (default): stesso confronto col codice di master nel worktree: **0 righe diverse**.

**tutti** (26 scenari): vedi sezione 8.

## 8. tutti

`certifica mike 35760084 --scenari tutti --worker 0` (`replay/mike_tutti_FEED_STANTIO_LOOP.txt`):
**26/26 OK, 0 violazioni, TEMPO TOTALE 581,7 s** (sotto il tetto di 600 s; durata dichiarata
in anticipo: circa 13 minuti, come i 772,6 s del riferimento; un altro `tutti` di un'altra
sessione girava in parallelo).

Confronto con `mike_tutti_MASTER_senza_rv.txt` del principale (`AUDIT_2026-10-02/confronta_referti.py`,
`PYTHONIOENCODING=utf-8`): 171 righe diverse, cosi' ripartite:
- **lettura-dati-ko**: KO -> OK, azioni 377 -> 8, `no_fill x370` -> `feed_stantio x1`,
  «green resting appoggiata (residuo) x372» -> «tengo, feed stantio ... x369», P1/P2/P3 spariti;
  ESITO 25+1 -> 26+0. I contatori aggregati di copertura dei controlli scendono TUTTI di
  esattamente 369 (A3 517->148, C1/C2/C3/L1 498->129, D1 434->65, D2 392->23, J2 444->75):
  sono le 369 riproposte tolte, nient'altro.
- tutte le altre: solo codifica (il riferimento ha `�` dove c'e' `§`, `«»`, `—`) e l'ordine in
  cui i worker intercalano le righe `CRITICAL` del logger. Conteggi identici nei due file:
  «aperture FERME» 1/1, «COPERTURA BLOCCATA» 2/2, «residuo scoperto» 18/18, «RIFIUTATO la lay»
  4/4, «esito IGNOTO» 10/10, 26 righe di esito in entrambi.
- `LENTO: X` presente solo nel riferimento (772,6 s contro 581,7 s).

## 9. NON VERIFICATO / reperti

- **Riproducibilita' del banco dipendente dalla cartella di lavoro**: lo stesso codice (master
  e correzione) lanciato da un'esportazione `git archive` (senza le cartelle `_*`, `.*`,
  `AUDIT*`, `docs`, `frontend`) da' `uscita_proposta x11` / «tengo x2200» / G3 x4296 sullo
  scenario base, contro x16 / 2347 / 4002 nel worktree. Decisioni, azioni, P&L identici; il
  codice NON c'entra (stessa differenza su master e correzione). Qualcosa fuori dal codice
  (un file in una di quelle cartelle) entra nel replay senza essere dichiarato nell'«ambiente
  del banco». Non indagato: e' fuori perimetro.
- Il percorso REST di ripiego con un'APERTURA (`fonte_prezzi == rest_ripiego`,
  `feed_fresh=True`) resta come prima: rifiuto `feed_stantio` senza nota nel ctx (il filtro
  vale solo a feed stantio). Un'apertura col ripiego e' gia' esclusa a monte da
  `order_fresh=False` nei rami d'ingresso; non provato un loop su quel ramo.
- `copertura-rifiutata`: `cover x1564` nell'attivita' anche su master: e' il ritmo del freno
  della copertura, non il feed stantio; non toccato.
- La durata di `--scenari tutti` supera il tetto di 600 s anche su master (772,6 s nel referto
  del coordinatore): difetto del banco gia' dichiarato in `REPLAY_VELOCE.md`, non toccato.
- Nessuna prova in paper/live vero: solo test e banco.

## 10. Nota sulla patch

Mentre girava il `tutti` il coordinatore ha integrato la correzione su master (`f34a281`): `engine.py`, `service.py` e il file di test su master sono IDENTICI a quelli del ramo (`git diff HEAD master` vuoto su quei tre file). Per questo la patch `MIKE_FEED_STANTIO_LOOP.patch` e' `git diff c190dc8` (la base del ramo), non `git diff master` (che oggi mostrerebbe al contrario il lavoro di master arrivato dopo).
