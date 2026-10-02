# Quando una partita è finita per Betfair (02/10/2026)

Ordine dell'utente: «lo scanner deve sapere le posizioni di tutti i bot; SOLO QUANDO I MERCATI SONO
CLOSED (o qualsiasi altra dicitura che indichi che LA PARTITA è FINITA) possiamo liberare lo scanner,
documentati».

## 1. Fonti consultate

**Nel repo** (prima fonte, come da regola):
- `Betfair/Betfair_api_documentation.pdf` (62 pagine). Contiene solo esempi JSON, non le definizioni
  degli enum. Non ha la sezione Stream API: a p.61 rimanda solo ai campioni su GitHub.
- `docs/BETFAIR_BEST_PRACTICES_2026-07.md`: limiti, con link alle pagine ufficiali.
- Commenti e referti interni (osservazioni sui dati veri, non documentazione ufficiale).

**Fuori dal repo**: le definizioni che mancano nel repo vengono dalle pagine ufficiali Betfair (Confluence),
scaricate il 02/10/2026 via `rest/api/content/<id>?expand=body.view`. Le copie, e lo script che ne
estrae il testo, stanno in `AUDIT_2026-10-02/_fonti_betfair/`:
- `2687396` Exchange Stream API (`bf_2687396.txt`);
- `2687455` Betting Enums (`bf_2687455.txt`);
- `2687517` listMarketCatalogue (`bf_2687517.txt`);
- `2687478` Market Data Request Limits (`bf_2687478.txt`).

Per ogni frase qui sotto è indicata la fonte: [REPO] o [UFFICIALE, rete 02/10].

## 2. Che cosa dice Betfair

### 2.1 Stato del mercato (`status`)

**Enum `MarketStatus`** [UFFICIALE, Betting Enums, `bf_2687455.txt:85-99`]:

| Valore | Descrizione |
|---|---|
| `INACTIVE` | «The market has been created but isn't yet available.» |
| `OPEN` | aperto alle scommesse |
| `SUSPENDED` | «The market is suspended and not available for betting.» |
| `CLOSED` | «The market has been settled and is no longer available for betting.» |

**Stream API, `marketDefinition`** [UFFICIALE, Exchange Stream API, `bf_2687396.txt`]:
- `status` (`:712-713`): «The status of the market, for example, OPEN, SUSPENDED, CLOSED (settled), etc.»
- `inPlay` (`:688-689`): «True if the market is currently in play».
- `complete` (`:684-685`): «If false, runners may be added to the market». Non dice nulla sulla fine
  della partita.
- `settledTime` (`:608-609`): «Market settled time.»
- `bspReconciled` (`:680-681`): «True if the market starting price has been reconciled». Riguarda il
  prezzo BSP, non la fine della partita.
- `marketTime` (`:672-673`): «The market start time». È l'orario PREVISTO.
- `openDate` (`:724-725`): «The scheduled start date and time of the event». Anche questo è PREVISTO.
- `suspendTime` (`:676-677`): «The market suspend time».
- `suspendReason` (`:732-733`): «Currently returned only for Soccer markets, when status = SUSPENDED.
  Possible values are Goal, Third Party Unavailable, Penalty, Red Card, Non In Play Market».
  Una sospensione è dunque un evento di gioco, non una fine.

**Cache degli ordini** [UFFICIALE, `bf_2687396.txt:848`]: «closed - indicates when the market is closed».

**REST `listMarketBook`, esempio di mercato regolato** [REPO, PDF p.50, righe 3092-3112 del testo
estratto]:
- «To retrieve the result of a settled market, request listMarketBook after the market has been
  settled. The response will indicate whether the selection was settled as a 'WINNER' or 'LOSER' in
  the runners 'status' field. Settled market information is available for 90 days after settlement.»
- Valori dell'esempio: `"status": "CLOSED"`, `"complete": true`, `"inplay": false`.
- Runner a p.51: `WINNER`, `LOSER`, `REMOVED`.

### 2.2 Catalogo

[UFFICIALE, listMarketCatalogue, `bf_2687517.txt`]:
- «Returns a list of information about published (ACTIVE/SUSPENDED) markets […]»
- «**Please note: listMarketCatalogue does not return markets that are CLOSED.**»
- `maxResults`: «must be greater than 0 and less than or equal to 1000».
- `sort`: se non indicato, il default è `RANK`. Il codice usa `FIRST_TO_START`.

**Limiti di dati** [UFFICIALE, Market Data Request Limits, `bf_2687478.txt:4-6`]: «sum(Weight) * number
market ids must not exceed 200 points per requests […] If you exceed the maximum weighting of 200
points, the API will return a TOO_MUCH_DATA error.» Vedi anche
`docs/BETFAIR_BEST_PRACTICES_2026-07.md:37-42` [REPO].

### 2.3 Sottoscrizione dello stream

- `SUBSCRIPTION_LIMIT_EXCEEDED`: «Thrown when subscribed to more markets than allowed to - set to 200
  markets by default» [UFFICIALE, `bf_2687396.txt:179-180`].
- Lo stesso limite è riportato in `docs/BETFAIR_BEST_PRACTICES_2026-07.md:19` e in
  `Betfair/safe_strategy/stream.py:5-6` [REPO]. Il codice usa 180 mercati per connessione, con 4
  connessioni.
- Mercati CLOSED nello stream [REPO, `Betfair/safe_strategy/stream.py:8-9`, fonte dichiarata «risposte
  del BDP sul forum ufficiale, 09/09/2026», non la documentazione]: «i mercati CLOSED vengono esclusi
  dal conteggio al re-subscribe (job interno Betfair ogni 5', eviction dopo 1h)». Il messaggio con
  `status: CLOSED` arriva; poi il mercato esce dalla sottoscrizione.

### 2.4 Che cosa NON è documentato (né nel repo né nelle pagine scaricate)

1. **Se Over/Under e Correct Score chiudono insieme al Match Odds.** Nessuna frase ufficiale.
   C'è però un fatto osservato nel repo: un mercato può chiudere PRIMA del Match Odds. Il Half Time Score
   `1.262446903` è stato «CLOSED da Betfair al 45'» con il Match Odds ancora OPEN
   (`Betfair/safe_strategy/service.py`, docstring di `_mercato_attivo`). Quindi lo stato di ogni mercato
   va letto dal suo book, mai dedotto da quello del Match Odds.
2. **Ritardi di regolamento** e sospensioni lunghe (es. verifica del risultato): nessuna frase ufficiale.
   La definizione dice solo che `SUSPENDED` è «not available for betting», non «finito».
3. **Durata del flusso dopo CLOSED**: c'è solo la nota del forum di `stream.py:8-9`.

## 3. Regola unica «partita finita» (scanner, 02/10)

Da §2 segue che l'unica dicitura di Betfair che vuol dire «finito» è **`CLOSED`**: «settled and no
longer available for betting». Le altre non lo sono:
- `SUSPENDED`, anche se lunga: è una pausa, «not available for betting».
- `inPlay=false` dopo il fischio.
- `marketTime`/`openDate`: sono orari PREVISTI.
- `complete`: riguarda i runner aggiunti.
- `bspReconciled`: riguarda il BSP.

> **Una partita con esposizione di un bot è finita quando il suo Match Odds è CLOSED e nessun altro
> mercato esposto è ancora noto come aperto. Mai per orologio.**

Come si applica:
- **Stato di ogni mercato esposto**: è l'ultimo `status` del SUO book, stream o REST
  (`Scanner._stato_blocco`).
- **Mercato esposto ancora OPEN/SUSPENDED con Match Odds CLOSED**: la riga resta pubblicata e il
  mercato resta sottoscritto finché non arriva il suo CLOSED (`Scanner._esposti_aperti_dopo_mo`,
  `build_rows`, `ranked_relevant_markets`).
- **Mercato esposto mai visto** (nessun book): non c'è nessun fatto che lo dica aperto. Il segnale
  ufficiale di fine resta il Match Odds CLOSED. Lo scanner chiede comunque il mercato al catalogo
  (punto 28): se Betfair non lo restituisce è CLOSED, perché «listMarketCatalogue does not return
  markets that are CLOSED».
- **Evento esposto che Betfair non restituisce più a catalogo**: stessa regola, è chiuso. Lo scanner lo
  scrive nel diario e non lancia un CRITICAL.
- **Prima del fischio**: nessun tetto per una partita esposta. Resta monitorata finché Betfair non la
  mette in gioco o non chiude il Match Odds (attesa del fischio del 01/10, ora per qualunque bot).
- **Il tetto di 3 h** (`scanner.POST_KO_WAIT_SEC`) vale SOLO per le partite senza esposizione di
  nessun bot.

## 4. Limiti onesti

- La fonte delle esposizioni sono le righe che i bot scrivono nel DB, lette ogni 10 s
  (`db.list_bot_exposures`). Un'esposizione nata da meno di 10 s non è ancora nota allo scanner.
- Le definizioni di stato vengono dalle pagine ufficiali in rete, non dal PDF del repo, che non ha né
  l'enum né lo Stream API. Le copie scaricate stanno nel repo, accanto a questo file.
