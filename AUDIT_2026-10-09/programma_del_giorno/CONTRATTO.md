# Programma del giorno (/board) — contratto backend/frontend (09/10/2026)

Ordine dell'utente del 09/10 (vale per calcio E tennis):
1. design system v2 dappertutto;
2. punteggio e minuto nelle partite live (calcio: minuto + gol; tennis: set/game/punti + battuta);
   il tabellone TENNIS deve partire sempre, come quello del calcio;
3. liquidita' del mercato evidenziata meglio;
4. menu' di scelta del mercato (sul calcio ESCLUSI i correct score), quote e liquidita' che si aggiornano;
5. i box delle quote PIAZZANO DAVVERO: clic su back o lay di una selezione -> si apre il box
   (come Betfair) dove si scrive l'importo e si conferma;
6. pulsante STATISTICHE (dashboard della partita, con ritorno al punto di partenza);
7. pulsante TRADING (sezione trading della partita, con ritorno al punto di partenza).

TASSATIVO: riusare tutto quello che esiste (componenti, feed, canali); creare solo cio' che
manca. NESSUNA connessione nuova: niente socket nuovi, niente stream nuovi, niente poller
nuovi lato frontend. Tutto centralizzato nel `board_worker` che gia' esiste e nei due canali
locali che gia' esistono (47331 calcio, 47332 tennis).

## 1. Push `board` (esistente, ESTESO in modo compatibile)

Topic `board`, payload `{"rows": [...]}`; le righe restano quelle di oggi (mercato MATCH_ODDS) con
campi AGGIUNTI (tutti opzionali per il frontend: un campo assente vale «non noto», mai 0):

```
row = {
  ...campi di oggi: event_id, event_name, open_date, market_id, status, inplay, total_matched, selections,
  "score":  null | CALCIO | TENNIS,          # solo partite in gioco, dal feed dello scanner (shared_cache)
  "fixture_id": int | null,                 # calcio: scan payload.selection_hint.fixture_id (per le Statistiche)
  "bet_delay": int | null,                  # dal feed se c'e'
  "updated_ms": int                         # quando la riga e' stata costruita
}
CALCIO = {"sport": "calcio", "minute": int|null, "home": int|null, "away": int|null,
          "red_home": int|null, "red_away": int|null, "ht": bool|null}
TENNIS = {"sport": "tennis", "sets": {"p1": int, "p2": int} | null, "games": {"p1": int, "p2": int} | null,
          "points": {"p1": str, "p2": str} | null, "server": "p1"|"p2"|null}
selection += {"back_size": float|null, "lay_size": float|null}   # importo disponibile al miglior prezzo
```

`total_matched` deve essere affidabile anche per le righe che vengono dal feed dello scanner (oggi
arriva `None` dallo stream): il worker lo integra con la REST che gia' usa (`list_market_book`,
stesso blocco da 25, stessa cadenza massima di 60 s), senza chiamate in piu' per riga.

## 2. Tipi di mercato disponibili (NUOVO, nello stesso push)

Nel payload `board` si aggiunge `"market_types": [{"market_type": str, "name": str, "count": int}]`:
i tipi di mercato presenti sugli eventi del programma (una chiamata `listMarketTypes`/catalogo
leggera, cache 300 s come il catalogo di oggi). Sul calcio sono ESCLUSI tutti i correct score
(`CORRECT_SCORE`, `CORRECT_SCORE2*`, `HALF_TIME_SCORE` e ogni tipo che contiene `CORRECT_SCORE`).
`MATCH_ODDS` e' sempre il primo.

## 3. Mercato scelto (NUOVO): richiesta `board_mercato` + push `board_mercato`

Il frontend sceglie UN tipo di mercato per scheda sport (menu' globale, come la «coupon» di Betfair).
- richiesta client->server sul canale dello sport: `{"id", "m": "board_mercato", "p": {"market_type": "OVER_UNDER_25"}}`
  metodo di SOLA LETTURA (non esegue nulla, non richiede il token), risposta `{ok: true}` o `{ok:false,e}`
  (tipo sconosciuto / escluso). Il frontend la RINNOVA ogni 30 s finche' la scelta resta; il worker
  dimentica un tipo non rinnovato da 75 s. `MATCH_ODDS` non si chiede: e' il `board` di sempre.
- push `board_mercato`, a ogni giro del worker finche' almeno un tipo e' richiesto:
```
{"market_type": "OVER_UNDER_25", "rows": [
   {"event_id", "market_id", "market_name", "status", "inplay", "total_matched",
    "selections": [{"selection_id", "name", "handicap": float|null, "back", "lay", "ltp", "back_size", "lay_size"}]}
 ], "updated_ms": int}
```
  una riga per evento del programma che ha quel tipo (per i tipi con piu' linee di handicap,
  es. ASIAN_HANDICAP, una riga per mercato con `handicap` per selezione). Prezzi: feed dello scanner
  dove copre quel mercato, altrimenti la stessa REST a blocchi da 25 con la stessa cadenza massima.

## 4. Ordini dal tabellone (ESISTENTE: nessun percorso nuovo)

Il box quota usa il percorso d'ordine manuale che gia' esiste: `localOrderApi(sport, dbApi)`
(`frontend/src/lib/localTransport.ts`) -> metodo `order` del canale (con token) -> ripiego DB
(`sendLiveOrderCommand` calcio / `sendTennisOrderCommand` tennis). Azione `place`, `order_type: 'LIMIT'`,
prezzo = quota cliccata (modificabile), `size` = importo, `handicap` della selezione, `persistence` come
il ladder. La modalita' (PROVA/REALE) e' SEMPRE quella del runner (`hello.mode` / `modo_ordini`),
mai scelta dalla pagina, e il box la dice in chiaro (componente `PlaceConfirmDialog`).
Il backend deve garantire che un `place` dal tabellone su un mercato NON ancora sottoscritto dal runner
non venga rifiutato con «market non sottoscritto»: aggancio al volo sulla connessione esistente
(calcio `AutoFollow.richiedi`, tennis iscrizione a caldo), come gia' fa il motore ordini per i comandi.
Se un aggancio non e' possibile (tetto pieno) il rifiuto e' esplicito e il frontend lo mostra.

## 5. Navigazione (ESISTENTE)

- STATISTICHE: calcio `/dashboard?fixture=<fixture_id>&from=board` (pulsante spento con la ragione se
  `fixture_id` manca, come `AzioniPartita`); tennis: le statistiche della partita esistono solo nel
  Tennis Terminal (`TennisMatchStats`) -> pulsante che apre il terminal sulla partita con `&from=board`.
- TRADING: come `AzioniPartita.apriTrading`: calcio `followMission` + `/segui-live?event=<id>&from=board`;
  tennis `/tennis/terminal?event&market&name=Match Odds&p1&p2&from=board`.
- RITORNO: `lib/ritorno.ts` riceve l'origine `board` (`/board`, «Torna al Programma»), con la
  scheda sport e la partita da riportare in vista (`data-event-id`).
