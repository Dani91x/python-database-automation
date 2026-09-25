# Contratto "strada unica" verso l'Exchange (F10a, 25/09/2026)

Test: `Betfair/stream/tests/test_contratto_strada_unica_2026_09_25.py`.
Riferimenti: `AUDIT_2026-09-24/AUDIT_STRADE_ORDINE_2026-09-24.md` par.1.0 (tabella
delle strade) e par.4.6 punto 6; `AUDIT_2026-09-25/STRADA_UNICA_BANCO_E_PAPER.md`.

## Cosa fa il test

Scandisce con `ast` (non con una regex sola) ogni `.py` sotto `Betfair/`, esclusi
`tests/`, `tools/`, i file `test_*.py` e (per difesa futura) percorsi con
`worktrees`/`_live_raw`. Cerca:
- chiamate a un metodo o funzione chiamata `place_order`, `place_orders`,
  `cancel_orders`, `replace_orders`;
- la stringa letterale del metodo JSON-RPC diretto (`SportsAPING/v1.0/placeOrders`
  e affini), per beccare un eventuale bypass del client REST unico.

Confronta l'elenco trovato con `_CHIAMANTI_AUTORIZZATI` (dizionario nel test
stesso). E' ROSSO in due direzioni:
- un modulo chiama e non e' nell'elenco (strada nuova non dichiarata);
- un modulo e' nell'elenco ma non chiama piu' (elenco stantio).

Un secondo test stampa la mappa chiamante -> strada e verifica che l'unione dei
codici di strada usati copra esattamente le 7 strade della tabella par.1.0
dell'audit (S1, S2, S2t, S3a, S3b, S4a, S4b), ne' di piu' ne' di meno.

## Come leggere il rosso

`test_nessun_chiamante_nuovo_non_registrato` fallito: e' comparso un chiamante
nuovo verso l'Exchange. Il messaggio d'errore elenca il file e (riga, nome della
chiamata). Due esiti possibili:
1. e' una strada legittima (per esempio un bot nuovo, o il ripiego D5 di una
   fase futura del piano par.5): si aggiunge una voce a `_CHIAMANTI_AUTORIZZATI`
   col motivo e il codice di strada, e si rilancia il test;
2. non doveva esistere: e' un reperto, si scrive all'utente PRIMA di toccare
   qualunque file di produzione (non si "aggiusta" il contratto per farlo
   tacere).

`test_elenco_non_stantio` fallito: un modulo autorizzato non chiama piu'.
O la strada e' stata davvero tolta (si toglie la riga dal contratto, e si
verifica che sia una decisione presa, non un refuso), oppure `ast` non vede la
chiamata (per esempio dietro un `getattr` dinamico): va capito prima di toccare
l'elenco.

`test_mappa_chiamante_strada_coerente_con_tabella_1_0_audit` fallito: il numero
o l'identita' delle strade coperte dal contratto non coincide piu' con la
tabella par.1.0 dell'audit del 24/09. O l'audit va aggiornato (una strada e'
sparita o se ne e' aggiunta una legittima), o e' un refuso nel contratto.

## Come aggiungere o togliere un chiamante

E' una decisione dell'utente, mai un'iniziativa del delegato o del coordinatore:
1. si scrive il caso all'utente (quale modulo, quale funzione, perche' serve
   toccare l'Exchange da li');
2. con l'ok, si aggiunge (o si toglie) la voce in `_CHIAMANTI_AUTORIZZATI` nel
   test, con un motivo non vuoto e il codice di strada (par.1.0 dell'audit, o
   `BANCO` per il banco di certificazione, o un codice nuovo se l'utente decide
   che e' un'ottava strada — allora va aggiornata anche `_STRADE_AUDIT` e la
   tabella dell'audit);
3. si rilancia `python -m pytest Betfair/stream/tests/test_contratto_strada_unica_2026_09_25.py -q`
   e ci si assicura che torni verde.

## Stato al 25/09/2026: chiamanti trovati e sorprese

18 moduli di produzione autorizzati (vedi il file per il motivo di ciascuno),
piu' **4 trovati dalla scansione e NON previsti dall'audit del 24/09**, non
toccati in questa consegna, marcati `NON_PRODUZIONE?` perche' nessun runner di
produzione li importa (verificato: nessun modulo fuori dalla propria cartella
li richiama; `scalper_lab/*` si dichiara "LAB separato" nella propria docstring;
`tennis_lab.py` non e' in `_BOT_REGISTRY` di `tennis_runner.py`):
- `Betfair/stream/scalper_lab/grid_strategy.py`
- `Betfair/stream/scalper_lab/scalper_bot_base.py`
- `Betfair/stream/scalper_lab/theta_strategy.py`
- `Betfair/stream/tennis_scalper/tennis_lab.py`

Decisione da prendere con l'utente: chiuderli (mai usati), spostarli fuori da
`Betfair/` (per esempio sotto un `lab/` che il contratto esclude esplicitamente,
come oggi fa per `tests/`/`tools/`), oppure lasciarli e basta (rimangono nel
contratto con motivo dichiarato, il test resta verde cosi' com'e').

Dettaglio completo, con riga per riga: `AUDIT_2026-09-25/F10A_CONTRATTO_STRADA_UNICA_2026-09-25.md`.
