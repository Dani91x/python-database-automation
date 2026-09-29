# Ricerca documentale — stato degli ordini Betfair e come fanno i competitor

> **NOTA DEL COORDINATORE (29/09/2026), da leggere prima del resto.**
> 1. L'affermazione «il runner flumine e' fermo dal 2/09» viene da `ESECUZIONE_LIVE.md`, un
>    documento del 14/09 NON aggiornato e non tracciato nel repo. Dal 18/09 in poi sono stati
>    costruiti e certificati il canale al millisecondo, il motore ordini e il paper di Mike sul
>    runner (vedi `CRONOSTORIA.md`). Lo stato VERO del runner va letto a app accesa: questa
>    ricerca NON lo prova. La raccomandazione 3 («riaccendere il runner») non e' quindi una
>    conclusione, e' un punto da verificare.
> 2. Sul LAPSE a ogni sospensione in gioco esiste una frase ufficiale che la ricerca non cita:
>    pagina placeOrders, nota sulla versione del mercato: la versione cambia per «Runner removal
>    and addition - Turn in-play - Lapsing or voiding bets (eg on goals being scored in managed
>    Football market)». Betfair quindi documenta che sui gol, nei mercati di calcio gestiti, le
>    scommesse non abbinate vengono fatte decadere o annullate.
> 3. Le raccomandazioni 1 e 2 (ritiro nostro scritto come errore; motivo della decadenza letto
>    da `lapseStatusReasonCode`) sono passate al delegato del pacchetto P4 come punti da
>    VERIFICARE con un test prima di toccare il codice.


> Ricerca in sola lettura, 29/09/2026. Nessun file di codice toccato, nessuna chiamata
> API Betfair, nessun test/replay eseguito. Fonti: repo (docs interni + PDF ufficiale
> Betfair già presente in `Betfair/`), pagine Confluence ufficiali di
> `betfair-developer-docs.atlassian.net` scaricate per intero con `curl`, pagine
> pubbliche dei competitor trovate via ricerca web, pacchetti `flumine`/`betfairlightweight`
> installati nel `.venv` del repo.

---

## 1. In tre righe

Betfair vi dice sempre tutto sui vostri ordini, ma non da un'unica fonte istantanea:
l'**order stream** è il più rapido (arriva in push, con i campi che dicono abbinato,
in coda, scaduto, annullato) ma oggi il runner flumine che lo usa è **fermo dal
2/09** (`ESECUZIONE_LIVE.md`), quindi Mike, Safe e Omega scoprono lo stato reale di un
ordine solo interrogando Betfair a polling (`listCurrentOrders`) — mai in tempo reale.
La cancellazione automatica (LAPSE) di un ordine appoggiato **al passaggio in gioco**
è scritta nero su bianco da Betfair; che la stessa cosa succeda **a ogni sospensione
successiva** (un gol) non ha una frase ufficiale altrettanto esplicita — è un fatto
misurato dai nostri test dal vivo del 16-17/09, non una citazione della documentazione.
La chiusura di una posizione fatta dall'utente **fuori dall'app** (sul sito) è già
rilevata da tutti e tre i bot (non solo Mike) leggendo la "posizione di conto" —
ordini di CHIUNQUE su quel mercato — ma solo in LIVE, a bassa cadenza (~30 s), e mai
in paper.

---

## 2. Cosa dice Betfair

### 2.1 Le fonti per ogni stato di un ordine

| Stato che l'utente vuole conoscere | Fonte ufficiale | Campi | Ritardo |
|---|---|---|---|
| Abbinato (matched) | Order stream (`ocm`) **o** `listCurrentOrders`/`listClearedOrders` | `sm`/`sizeMatched`, `avp`/`averagePriceMatched` | stream: push quasi immediato; REST: al momento della chiamata |
| Abbinato in parte | stream **o** `listCurrentOrders` | `status=EXECUTABLE` + `sm`>0 e `sr`/`sizeRemaining`>0 | idem |
| In coda (unmatched, a riposo) | stream **o** `listCurrentOrders` | `status=EXECUTABLE`, `sr`/`sizeRemaining`>0 | idem |
| Cancellato da Betfair (LAPSE) | stream **o** `listCurrentOrders` (mentre è ancora visibile) poi `listClearedOrders` (dopo che è uscito dai correnti) | `sl`/`sizeLapsed`, `lsrc`/`lapseStatusReasonCode`, `status` diventa `EXECUTION_COMPLETE` o l'ordine esce dai correnti | stream: push; `listClearedOrders`: **"Please note: Only BET returns details of LAPSED or CANCELLED bets"** (serve `groupBy=BET`) |
| Ritirato da noi (cancel volontario) | risposta sincrona di `cancelOrders`/`replaceOrders` **e** `sc`/`sizeCancelled` su stream/`listCurrentOrders` | `sizeCancelled`, `CancelInstructionReport.status` | risposta sincrona della chiamata stessa |
| Rifiutato | risposta sincrona di `placeOrders`/`replaceOrders`: `InstructionReportStatus=FAILURE` + `InstructionReportErrorCode` | `errorCode` (esterno) **e**, nel caso di un `replaceOrders`, i report annidati `placeInstructionReport.errorCode`/`cancelInstructionReport.status` | sincrono |
| Esito incerto | risposta `InstructionReportStatus=TIMEOUT`, poi verifica su `listCurrentOrders` | — | vedi §2.4 sotto: fino a 15 secondi |

Fonti dirette: [Betting Enums](https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687455) (`OrderStatus`, `PersistenceType`, `InstructionReportStatus`, `InstructionReportErrorCode`), [listCurrentOrders](https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687504/listCurrentOrders), [listClearedOrders](https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687749/listClearedOrders), [Exchange Stream API](https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687396/Exchange+Stream+API).

**Sul "con che ritardo" per lo stream** (nessuna cifra esatta in millisecondi trovata per
il caso normale, solo questi meccanismi qualitativi, fonte Exchange Stream API):

> «heartbeatMs - Specifies a minimum interval that a client would expect to receive a
> message (in milliseconds) - bounds are 500 to 5000 milliseconds.»
>
> «conflateMs - [...] the field value will be 180000 if you access the Stream API using
> a Delayed App Key or have an account delay in place when using the Live App Key.»
>
> «Stream API Status - latency: By default, when the stream data is up to date the value
> is set to null and will be set to 503 when the stream data is unreliable [...] due to
> an increase in push latency. Clients shouldn't disconnect if status 503 is returned.»

Con **Live App Key** e nessun account delay, non c'è quindi il ritardo forzato di 180
secondi che invece si applica con una Delayed App Key: il push resta nell'ordine dei
millisecondi indicato dall'heartbeat (500-5000 ms), salvo lo stato 503 che segnala un
rallentamento reale del canale.

### 2.2 `OrderStatus` — testo esatto (Betting Enums)

> «**PENDING** | An asynchronous order is yet to be processed. Once the bet has been
> processed by the exchange (including waiting for any in-play delay), the result
> will be reported and available on the Exchange Stream API and API NG.»
> «**EXECUTION_COMPLETE** | An order that does not have any remaining unmatched
> portion.»
> «**EXECUTABLE** | An order that has a remaining unmatched portion.»
> «**EXPIRED** | The order is no longer available for execution due to its time in
> force constraint. In the case of FILL_OR_KILL orders, this means the order has
> been killed because it could not be filled to your specifications.»

Fonte: [Betting Enums](https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687455).

### 2.3 `PersistenceType` — LAPSE vs PERSIST, testo esatto

> «**LAPSE** | Lapse (cancel) the order automatically when the market is turned in
> play if the bet is unmatched»
>
> «**PERSIST** | Persist the unmatched order to in-play. The bet will be placed
> automatically into the in-play market at the start of the event. Once in play,
> the bet won't be cancelled by Betfair if a material event takes place and will
> be available until matched or cancelled by the user»
>
> «**MARKET_ON_CLOSE** | Put the order into the auction (SP) at turn-in-play»

Fonte: [Betting Enums](https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687455). La stessa frase («What to do with the order at turn-in-play») è ripetuta identica nella pagina [Betting Type Definitions](https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687465) per i campi `persistenceType` di `CurrentOrderSummary` e `PlaceInstruction`.

**Punto onesto**: la frase ufficiale parla del **momento in cui il mercato passa
in gioco** ("turn in play"), NON di ogni sospensione successiva durante il gioco
(un gol). Vedi §7.

### 2.4 Cosa succede a un ordine non abbinato durante una SOSPENSIONE in-play (gol)

L'unica traccia ufficiale trovata è nel `lapseStatusReasonCode` (campo `lsrc` sullo
stream), pagina Exchange Stream API, sezione «Lapse Status Reason Code Possible
Values»:

> «This field will now be present in some cases on the Order object of the Order
> Stream to denote the reason that some or all of the order is lapsed. It will be
> null if no portion of the order is lapsed or if the order lapsed for some reason
> other than those listed below.»
>
> «**MKT_SUSPENDED** | The market was suspended at the time the bet came to be
> matched.»
> «**TIME_ELAPSED** | The bet was waiting in the queue too long, so was lapsed for
> safety.»

Fonte: [Exchange Stream API](https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687396/Exchange+Stream+API), sezione "Lapse Status Reason Code Possible Values".

Coerente col `InstructionReportErrorCode.BET_TAKEN_OR_LAPSED`:

> «Bet cannot be cancelled or modified as it has already been taken or has been
> cancelled/lapsed [...] The error may be returned on placeOrders request if for
> example a bet is placed at the point when a market admin event takes place (i.e.
> market is turned in-play).»

Fonte: [Betting Enums](https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687455).

**Nessuna delle due frasi dice esplicitamente**: "un ordine appoggiato PRIMA della
sospensione viene cancellato NON APPENA il mercato si sospende per un gol". `MKT_SUSPENDED`
descrive un ordine che **stava per essere abbinato** mentre il mercato era sospeso, non
la cancellazione a freddo di un ordine già a riposo. La prova che questo avviene
davvero — Betfair cancella la lay appoggiata al gol — è nel nostro test dal vivo del
17/09 (`Betfair/stream/trading/PLACE_AND_TRIM_INDAGINE_2026-09-17.md` §7) e
nell'esperienza diretta dell'utente riportata in `Betfair/mike/service.py:2405-2422`,
non in una riga della documentazione ufficiale che io abbia trovato.

**Il pezzo più vicino a una prova ufficiale** è nella stessa pagina Exchange Stream API,
sezione «VAR (Video Assistant Referee) Void Bets Handling», che mostra un esempio REALE
di un gol poi annullato dal VAR: una lay già abbinata (`status=EC`) diventa `sv` (size
voided), e una back ancora in coda (`status=E`) riceve una `ld` (lapsed date) con
`sl` (size lapsed) valorizzato. Testo esatto della pagina:

> «Key difference being in the values of sizeMatched and sizeRemaining before the event
> and sizeVoided and sizeLapsed after the event.»

Fonte: [Exchange Stream API](https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687396/Exchange+Stream+API), sezione "VAR (Video Assistant Referee) Void Bets Handling".
**Attenzione onesta**: è l'esempio di un VAR che ANNULLA un gol già assegnato (quindi
tocca anche ordini già abbinati, con voiding), non la sospensione generica "si è
segnato un gol, il mercato si ferma" che interessa a Mike in ogni caso — ma è comunque
la prova più diretta trovata nella documentazione ufficiale che un evento di gioco
(qui un VAR check) cambia realmente `sizeLapsed`/`sizeVoided` sull'order stream, non
solo teoricamente.

### 2.5 `listCurrentOrders` vs `listClearedOrders`

`listCurrentOrders`:

> «Returns a list of your current orders. [...] setting none of the parameters
> will return all of your current orders up to a maximum of 1000 bets [...] Best
> Practice: To efficiently track new bet matches from a specific time, customers
> should use a combination of the dateRange, orderBy "BY_MATCH_TIME" and
> orderProjection "ALL" [...]»

Fonte: [listCurrentOrders](https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687504/listCurrentOrders).

`listClearedOrders`:

> «Returns a list of settled bets based on the bet status, ordered by settled
> date. [...] By default the service will return all available data for the last
> 90 days [...] groupBy | [...] Only applicable to SETTLED BetStatus. Please note:
> **Only BET returns details of LAPSED or CANCELLED bets.**»

Fonte: [listClearedOrders](https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687749/listClearedOrders).

Un ordine LAPSE-ato o CANCELLED non compare più fra i correnti; per vederne i dettagli
via `listClearedOrders` bisogna chiedere `groupBy=BET` (il nostro `omega_market.order_state_by_bet_id`
lo fa già, vedi §5).

### 2.6 TIMEOUT — la fonte per "esito incerto"

> «**TIMEOUT** | The order timed out & the status of the bet is unknown. If a
> TIMEOUT error occurs on a placeOrders/replaceOrders request, you should check
> listCurrentOrders to verify the status of your bets before placing further
> orders. Please Note: Timeouts will occur after 5 seconds of attempting to
> process the bet but please allow up to 15 seconds for a timed out order to
> appear. After this time any unprocessed bets will automatically be Lapsed and no
> longer be available on the Exchange.»

Fonte: [Betting Enums](https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687455), `InstructionReportStatus`.

### 2.7 Il codice di rifiuto vero è ANNIDATO in un `replaceOrders`

Già documentato nel repo (`PLACE_AND_TRIM_INDAGINE_2026-09-17.md` §3) con fonte:

> «This operation is logically a bulk cancel followed by a bulk place. The cancel
> is completed first then the new orders are placed. [...] In the case where the
> new orders cannot be placed the cancellations will not be rolled back.»

Fonte: [placeOrders](https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687496/placeOrders) (stessa pagina per `replaceOrders`, che ne eredita la logica).

### 2.8 Exchange Italiano (Betfair.it) — cosa cambia sullo stato ordini

Dalla pagina ufficiale [Betting On Italian Exchange](https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687808):

> «The stake for each back offer is a minimum of 200 Euro Cents and can only be
> incremented in multiples of 50 Euro Cents. Any lay offers placed by the customer,
> must be placed in such a way as to ensure that the stake for any corresponding
> back offer amounts to a minimum of 50 Euro Cents. A placeOrders request may
> contain up to 50 bet instructions. [...] placeOrders request containing both back
> and lay bets in the same order will be rejected.»

**Nessuna differenza documentata** sugli STATI dell'ordine (OrderStatus, LAPSE/PERSIST,
order stream) fra Exchange italiano e UK: le uniche differenze sono di importo/istruzioni
(già note e gestite dal place-and-trim, vedi §5) e di sessione (scadenza 20 minuti,
già in `docs/BETFAIR_BEST_PRACTICES_2026-07.md` §1.5).

### 2.9 Bet piazzate manualmente sul sito — visibili all'API?

**Non trovato**: nessuna pagina consultata dichiara esplicitamente "le bet piazzate
sul sito web sono visibili via API esattamente come quelle piazzate via API". Resta
però un punto documentato — non solo una deduzione — sul meccanismo di filtro
dell'Order Stream, pagina Exchange Stream API, sezione OrderSubscription Message:

> «This optional filter already filters by your account, but additional data shaping
> is supported» — e sul campo `accountIds`: «This is for internal use only & should
> not be set on your filter (your subscription is already locked to your account).»

Cioè: l'Order Stream è **sempre** agganciato all'intero conto. Se il codice sottoscrive
SENZA il filtro `customerStrategyRefs`, riceve tutti gli ordini del conto, compresi
quelli piazzati manualmente dall'utente sul sito. Se invece filtra per
`customerStrategyRefs` (come fa oggi il motore ordini per gli ordini propri, §5), la
stessa pagina dice: «Restricts to specified customerStrategyRefs [...] this will filter
orders and StrategyMatchChanges accordingly (**Note: overall position is not
filtered**)» — quindi un ordine piazzato dall'utente sul sito non comparirebbe nel
flusso ordini filtrato per strategia, ma l'**esposizione aggregata di mercato**
(`overall position`) resterebbe visibile comunque. Questo è coerente con — e rafforza,
con una frase ufficiale — il motivo per cui il nostro codice legge la "posizione di
conto" SENZA filtro di strategia per accorgersi delle chiusure fuori app (§5.4): con
un filtro per strategia sull'Order Stream, quell'ordine manuale sfuggirebbe.
Resta comunque una deduzione, non una frase Betfair, che "senza filtro l'utente vede
esattamente gli stessi campi (sm/sr/sl/sc/sv) anche sulle bet piazzate sul sito": la
documentazione dice solo che quegli ordini SONO nello stream, non conferma
esplicitamente la parità di dettaglio dei campi.

### 2.10 Il PDF del repo (`Betfair/Betfair_api_documentation.pdf`, 62 pagine)

Verificato con `pypdf` (script temporaneo nello scratchpad, mai scritto nel repo):
il PDF è una guida "getting started" con **soli esempi JSON** di richieste/risposte
(`placeOrders`, `listCurrentOrders`, `listClearedOrders`, con `persistenceType: LAPSE`
negli esempi delle pagine 47 e 54-55). **Nessuna narrativa** su in-play, sospensione,
`OrderStatus`, `lapseStatusReasonCode` o latenza è presente in questo PDF — i termini
"in-play", "suspend", "OrderStatus" non compaiono affatto nel testo estratto. Tutto
quanto sopra viene dalle pagine Confluence pubbliche, non da questo PDF.

---

## 3. Come fanno i competitor

### 3.1 Bet Angel

Trovato (guida utente ufficiale, pagine pubbliche):

- «**Lapse** cancels unmatched bets if the market is suspended (when it goes live
  or when it's suspended for any reason, like goals), while **Keep** means the bet
  will not be cancelled if the market is suspended, also known as keep in play.»
  — [Bet Angel — Bet persistence types (Wagertool mirror della guida)](https://www.wagertool.com/support/user-guide/bet-persistence-types)
- «The default is for all bets to be cancelled when the market turns in play unless
  you modify them with a Keep or Take SP feature.» — [Bet Angel — Unmatched Bets](https://www.betangel.com/user-guide/unmatched_bets.html)
- «For unmatched bets in the unmatched bets area, if you wish your bet to be
  carried over to the in play market, simply select "keep", or [...] "Take SP".»
  — [Bet Angel — Unmatched Bets Area](https://www.betangel.com/user-guide/unmatched_bets_area.html)
- Sul place-and-trim (già nel repo, `PLACE_AND_TRIM_INDAGINE_2026-09-17.md` §2):
  Bet Angel dichiara che il trucco sotto-minimo raddoppia i tempi in-play e "**cannot
  guarantee** that bets below the minimum value will enter the market without error".

**Punto notevole per la domanda dell'utente**: Bet Angel dichiara ESPLICITAMENTE, nella
sua guida, che la sospensione **per qualsiasi motivo (compresi i gol)** cancella gli
ordini non abbinati con persistenza Lapse — è la conferma più diretta trovata fra i
competitor di ciò che i nostri test dal vivo hanno misurato, anche se non è una fonte
Betfair ufficiale.

**Non trovato**: nessuna pagina pubblica di Bet Angel descrive un meccanismo di
rilevamento "questa posizione è stata chiusa da un ordine piazzato fuori da Bet
Angel" — probabilmente perché Bet Angel STESSO è l'interfaccia con cui si opera
(non c'è un "fuori app" nello stesso senso del nostro caso).

### 3.2 Gruss Betting Assistant

Trovato:

- «Any unmatched bets placed in running will be **cancelled** once the market
  suspends at the finish, which changes the bet reference to show as **CANCELLED**.»
- «In the betting options tab you can set the default keep settings for your bets,
  choosing between having bets set to keep in play or be converted to SP bets at
  inplay.»
- Esiste una funzione COM che cancella tutte le bet non abbinate sul mercato
  visualizzato.

Fonte: pagine del forum/manuale ufficiale Gruss (`gruss-software.co.uk`), trovate via
ricerca web; non ho scaricato il PDF completo della user guide (`userguide.pdf`),
solo gli estratti indicizzati.

**Non trovato**: nessun riferimento pubblico specifico a rilevamento di chiusure
fatte fuori da Gruss, né a come Gruss distingue LAPSE da CANCELLED nell'interfaccia
oltre alla dicitura generica "CANCELLED".

### 3.3 FairBot (Betting.com / binteko.com / fairbot.com)

Trovato:

- «FairBot supports early warnings for an event start, partially or fully matched
  bets, a market turning in-play, or **a market suspending during in-play**.»
  — [fairbot.com](https://fairbot.com/) / [binteko.com/fairbot](https://binteko.com/fairbot)
- «FairBot includes a "Fill or Kill" tool [...] that cancels unmatched bets
  automatically after a predefined number of seconds.»
- «The "Take SP" option for unmatched bets will convert unmatched exchange bets to
  Betfair SP bets at the start of the event.»

**Punto notevole**: FairBot avvisa l'utente **al momento stesso** in cui il mercato
si sospende in-play, non solo dopo. È uno spunto concreto per la raccomandazione §6.

**Non trovato**: dettagli tecnici su come FairBot legge/mostra `sizeLapsed` o
`lapseStatusReasonCode`; la documentazione pubblica è commerciale/di alto livello,
non un manuale tecnico dei campi.

### 3.4 Geeks Toy

Trovato (manuale utente pubblico):

- «The Unmatched Bets window is only shown when there are unmatched bets on the
  market that is currently loaded. [...] To cancel an individual unmatched bet you
  click on the Cancel Button [...] right-click [...] to cancel all.»
- «When the market goes In Play you can cancel the unmatched bet, change the
  unmatched bet to a Keep bet, or change the unmatched bet to a Take SP bet.»

Fonte: [Geeks Toy — Unmatched Bets (manuale)](https://www.geekstoy.co.uk/UserManuals/EN/Unmatched%20Bets.html), forum ufficiale Geeks Toy.

**Non trovato**: nessuna descrizione pubblica specifica di come Geeks Toy gestisce
una sospensione per gol distinta dal turn-in-play, né di riconciliazione con bet
piazzate fuori dal tool. La documentazione pubblica di Geeks Toy sul comportamento
interno è la più scarsa dei quattro competitor esaminati.

### 3.5 Onestà sul limite della ricerca sui competitor

Per tutti e quattro i tool, quanto trovato viene da **pagine pubbliche** (manuali
utente, forum, siti commerciali), non da codice sorgente o da documentazione tecnica
interna: nessuno di questi prodotti è open source. Le citazioni sopra sono la
posizione pubblica dei produttori, non una verifica indipendente del loro
comportamento reale.

---

## 4. Come fa flumine (e betfairlightweight) — `file:riga` nel pacchetto installato

Versione installata: **flumine 2.13.11** + **betfairlightweight 2.23.2**
(`.venv/Lib/site-packages/`).

### 4.1 Percorso LIVE (order stream reale — non simulazione)

- `betfairlightweight/streaming/cache.py:419-476` — classe `UnmatchedOrder`: riceve
  **direttamente i campi grezzi dell'`ocm`** (`p`, `s`, `side`, `status`, `ot`, `pd`,
  `sm`, `sr`, `sl`, `sc`, `sv`, `lsrc`, ecc.) e li normalizza; `serialise()` (righe
  479-514) li traduce nei nomi "ufficiali" (`sizeMatched`, `sizeLapsed`,
  `lapseStatusReasonCode`, ecc.).
- `betfairlightweight/streaming/cache.py:569` — `OrderBookCache`, il contenitore per
  mercato di tutti gli `UnmatchedOrder`.
- `flumine/streams/orderstream.py:18-92` — `OrderStream.run`/`handle_output`: si
  sottoscrive con `subscribe_to_orders(order_filter=..., conflate_ms=...)` (riga 40-51)
  e, se non arriva nulla dallo stream per più di `SNAP_DELTA=3` secondi (riga 15, 78-82),
  fa uno **snap** esplicito (`self._listener.snap(...)`) sui mercati con ordini vivi —
  quindi anche sull'order stream flumine non aspetta all'infinito un push silenzioso.
- `flumine/order/process.py:33-73` — `process_current_orders`: per ogni ordine
  ricevuto dallo stream, lo ritrova nel blotter locale per `customer_order_ref`
  (riga 41-45) o lo ricrea se manca (riga 46-61, `create_order_from_current`,
  righe 95-140).
- `flumine/order/process.py:76-92` — `process_current_order`: aggiorna lo stato
  locale (`order.update_current_order(current_order)`, riga 78) e fa transitare
  l'ordine `PENDING → EXECUTABLE → EXECUTION_COMPLETE/EXPIRED` leggendo
  `current_order.status` (righe 85-92) — la stessa logica a stati che il nostro
  `motore_ordini.fase_da_riga` implementa in proprio (§5).
- `flumine/order/order.py:36-46` — enum `OrderStatus`: `PENDING`, `CANCELLING`,
  `UPDATING`, `REPLACING`, `EXECUTABLE`, `EXECUTION_COMPLETE`, `EXPIRED`.
- `flumine/order/order.py:455-499` — proprietà `size_matched`/`size_remaining`/
  `size_cancelled`/`size_lapsed`/`size_voided` che leggono `self.current_order.*`
  (il dato che arriva dallo stream/REST), con fallback a `0.0`.

### 4.2 Percorso SIMULATO (replay/paper — non il vero comportamento in-play)

Già misurato e documentato per intero nel nostro stesso audit del 16/09
(`FLUMINE_CAPACITA_SIMULAZIONE_2026-09-16.md`, sola lettura, mai toccato in questa
ricerca):

- `simulation/simulatedorder.py:57-62` — il middleware di simulazione lapsa il
  residuo (`size_lapsed += size_remaining`) **solo su `SUSPENDED` con cambio di
  `version`**, e solo se `persistenceType=LAPSE`.
- **Limite ammesso dal codice stesso**: la libreria **non modella affatto** la
  cancellazione dei LAPSE al passaggio in-play iniziale (`FLUMINE_CAPACITA_SIMULAZIONE_2026-09-16.md`
  §B e "LE 10 COSE CHE FLUMINE NON FA", punto 3) — nella simulazione un ordine LAPSE
  sopravvive al turn-in-play a meno che il mercato non cambi *anche* `version` durante
  una sospensione. È un limite del **simulatore**, non prova che il comportamento
  LIVE reale sia diverso (il comportamento LIVE reale lo dice il vero order stream,
  §4.1, e i nostri test dal vivo).
- `markets/middleware.py:56-175` — `SimulatedMiddleware`: gestisce runner REMOVED
  e reduction factor, non il turn-in-play.

**Punto da non confondere**: il §4.2 riguarda SOLO `FlumineSimulation` (replay/certificazione).
Il percorso LIVE vero (§4.1) legge lo stream reale di Betfair e non ha questo limite:
è Betfair stessa che manda l'aggiornamento LAPSED quando succede davvero.

---

## 5. Cosa fa oggi il nostro codice

### 5.1 Motore ordini condiviso — `Betfair/stream/motore_ordini.py`

- `motore_ordini.py:482-508` (`fase_da_riga`) — traduce lo stato Betfair/flumine in
  **sette fasi** esplicite: `rifiutato` (VIOLATION), `scaduto` (EXPIRED/LAPSED, o
  EXECUTION_COMPLETE con `size_lapsed>0` e nulla abbinato), `annullato`
  (EXECUTION_COMPLETE con `size_cancelled>0` o `size_lapsed>0` con qualcosa abbinato),
  `abbinato`, `abbinato_parziale`, `accettato_betfair`, `inviato`.
- `motore_ordini.py:544-545` — `_STATI_TERMINALI_ORDINE = {"EXECUTION_COMPLETE",
  "EXPIRED", "VIOLATION"}`.
- `motore_ordini.py:1624-1668` (`riprendi_da_diario`) — **esito incerto** dopo un
  crash: i comandi `inviato` senza `esito` nel diario vengono verificati con
  `listCurrentOrders` per `customerOrderRef` PRIMA di disarmare la guardia; se
  Betfair non è raggiungibile, la guardia resta **ARMATA** (fail-closed, riga
  1656-1668) — mai un'ipotesi su soldi veri.

### 5.2 Risk engine — `Betfair/stream/risk_engine_worker.py`

- `risk_engine_worker.py:40` — set `_TERMINAL = {EXECUTION_COMPLETE, EXPIRED,
  LAPSED, VIOLATION, CANCELLED}`.
- `risk_engine_worker.py:471,506-522` — **alert CRITICAL** se un hedge resting non
  si abbina entro `_FILL_ALERT_AFTER_SEC=10.0` secondi (rischio di restare
  "unmatched in un mercato veloce").
- `risk_engine_worker.py:868-884` — al terminale, legge separatamente
  `size_cancelled`/`size_lapsed`/`size_voided` (commento esplicito: "il terminale
  può essere CANCELLED ma anche LAPSED/VOIDED... flumine espone campi SEPARATI...
  mutuamente esclusivi").

### 5.3 REST condiviso (usato da Mike, Safe, Omega) — `Betfair/omega/omega_market.py`

- `omega_market.py:1345-1402` (`order_state_by_bet_id`) — riconciliazione per
  `betId`: prima `listCurrentOrders` (righe 1367-1381), poi in cascata
  `listClearedOrders` per stato `SETTLED`, `VOIDED`, `LAPSED`, `CANCELLED` (righe
  1384-1401) — **solleva** su errore di rete, mai un `found=False` per un problema
  di connessione.
- `omega_market.py:1405-1442` (`_riga_corrente`) — normalizza `sizeCancelled`,
  `sizeLapsed`, `sizeVoided`, `matchedDate`, `placedDate` da ogni ordine corrente.
- `omega_market.py:1454-1476` (`list_current_orders_account`) — **la lettura senza
  filtro di strategia**, chiave per la "posizione di conto" (§5.4): «se chiudo io il
  bot deve saperlo, anche fuori dall'app» — legge TUTTI gli ordini sul mercato,
  ordini dell'utente compresi.
- `omega_market.py:950` in poi (`place_submin_live`) — sequenza place-and-trim
  certificata dal vivo (rif. `PLACE_AND_TRIM_INDAGINE_2026-09-17.md`).

### 5.4 «Chiuso dall'utente fuori dall'app» — CONDIVISO da Mike, Safe e Omega

Non è un buco solo di Mike: è stato aggiunto lo stesso giorno (16/09/2026, ordine
esplicito dell'utente) a **tutti e tre** i bot, con lo stesso pattern (leggere la
posizione di CONTO, non solo i propri ordini):

- **Mike**: `Betfair/mike/service.py:2760-2869` (`_sorveglia_posizione_di_conto`) —
  legge `market.list_account_orders`/`list_account_cleared_orders` (righe 210-220)
  alla cadenza di `reconcile_every_s` (default per partita, non a ogni giro); se il
  NETTO di conto non contiene più la posizione di Mike, scrive `chiuso_dall_utente`
  (righe 2849-2869), ritira le gambe ancora vive e blocca re-ingressi.
- **Safe**: `Betfair/safe_strategy/bot_service.py:1667` (`_sorveglia_posizione_di_conto`),
  marcatura persistente `meta.chiuso_dall_utente` (righe 2258-2354), test dedicato
  `Betfair/safe_strategy/tests/test_chiusura_dell_utente_2026_09_16.py`.
- **Omega**: `Betfair/omega/omega_service.py:4443` (`_marca_chiuso_dall_utente`) +
  righe 4539-4640, test dedicato `Betfair/omega/test_omega_chiuso_dall_utente_2026_09_16.py`.

Solo in **LIVE** (in paper non esiste un conto da leggere: la funzione dichiara e
esce, `service.py:2776-2777`); mai a ogni giro, solo al respiro del database
(`reconcile_every_s`, ~30 s per partita secondo il commento a `service.py:207-209`).

### 5.5 Le quattro reazioni alla sospensione — Mike, `Betfair/mike/service.py`

- `service.py:2405-2422` — **premessa dichiarata**: «Un ordine LIMIT non abbinato ha
  `persistenceType=LAPSE`: alla sospensione del mercato Betfair lo fa SCADERE. Un
  gol al 2' basta.»
- `service.py:2423-2427` — quattro esiti espliciti: `vivo`, `scaduto`, `abbinato`,
  `parziale`, più `ignoto` (mai una gamba nuova su un ignoto).
- `service.py:2435-2464` (`_classifica_ordine`) — legge `size_matched`,
  `size_remaining` (**da Betfair**, mai per sottrazione: commento esplicito "una
  sottrazione è un'ipotesi, e qui le ipotesi sono soldi"), `size_lapsed`,
  `size_cancelled`, `status`.
- `service.py:2467-2507` (`_rileggi_ordine_appoggiato`) — due strade: ordini
  correnti, poi `order_state_by_bet_id` (unica chiave certa quando l'ordine è uscito
  dai correnti); rete KO → `None` = "non lo so ancora", si riprova, **nessuno può
  dire che l'ordine è vivo**.
- `service.py:2549-2600` (`_applica_esito_riapertura`) — applica le quattro
  reazioni una per una.
- `service.py:2318-2401` (`_segui_resting_live`) — segue l'abbinamento della lay
  appoggiata **leggendo `list_current_orders()`** (REST, non stream: §5.6), con
  `size_remaining` letto da Betfair, non calcolato.
- `service.py:4874-4974` (`_reconcile_trades`) e `service.py:4977-5060`
  (`_reconcile_unknown`) — riconciliazione righe DB ↔ gambe, e chiusura del dubbio
  su un ordine a esito ignoto (LIVE: interroga `listCurrentOrders`+`listClearedOrders`;
  senza accesso a Betfair resta in attesa, mai un'ipotesi).

### 5.6 Il limite condiviso da TUTTI i bot (non solo Mike)

`ESECUZIONE_LIVE.md` §2, testuale: «🔴 MA IL RUNNER FLUMINE È FERMO DAL 2 SETTEMBRE
[...] Finché è fermo, nessun bot può piazzare un ordine appoggiato in live [via coda]».
Conseguenza per lo stato ordini: oggi Mike, Safe e Omega scoprono un fill, un LAPSE o
un annullo **al polling successivo** (`list_current_orders()`/`listCurrentOrders`),
non in push dall'order stream — il "canale più rapido" (§4.1) esiste già nel codice
(`Betfair/stream/`) ma non è agganciato a nessuno dei tre bot in produzione.

### 5.7 Dove Mike è più debole degli altri — verdetto onesto

**Non ho trovato un punto strutturale in cui Mike sia più debole di Safe/Omega su
questo tema** (stato ordini, LAPSE, chiusura fuori app): il pattern "posizione di
conto" e le quattro reazioni alla sospensione sono stati aggiunti allo stesso modo e
lo stesso giorno a tutti e tre. Se c'è un'asimmetria, è nella direzione opposta: la
logica delle quattro reazioni esplicite di Mike (§5.5) è più articolata di quanto
abbia trovato nei grep equivalenti di Safe/Omega (che pure hanno
`AttesaRiapertura`/`_ATTESE_MERCATO`, vedi `omega_service.py:1735-1800` e
`bot_service.py:2639-2653`, ma non ho letto per intero la loro logica di
classificazione a 4 vie — vedi §7).

**Un punto concreto e SPECIFICO a Mike esiste, però**, già scritto dal coordinatore
in `ESECUZIONE_LIVE.md:107-108` e non ancora corretto (verificato di persona in
questa ricerca, con `grep` diretto sul file):

> «**Ordine annullato ≠ errore.** Oggi un annullo legittimo di Mike viene scritto
> `status='error'`: va distinto, altrimenti la tabella accusa il bot di un guasto
> che non c'è.»

Questo È esattamente il punto "ritirato da noi" vs "rifiutato" richiesto dall'utente:
oggi, per Mike, i due stati sono confusi nella scrittura a DB/UI (un ritiro voluto e
riuscito appare con lo stesso `status='error'` di un vero rifiuto). Non ho verificato
se lo stesso problema esista anche in Safe/Omega (fuori dal perimetro di questa
ricerca, che si è concentrata sui file indicati nel compito); il documento lo
segnala come bug noto solo per Mike.

**Debolezza reale, condivisa da tutti**: nessuno dei tre bot, in nessuno dei file
letti, legge esplicitamente `lapseStatusReasonCode`/`lsrc` per **dichiarare il
motivo** di un LAPSE (MKT_SUSPENDED vs TIME_ELAPSED vs altro): lo si deduce dal
contesto (siamo in una finestra di sospensione? allora è per quello), non da un
campo che Betfair manda già.

---

## 6. Raccomandazioni per Mike

1. **[CERTO — verificato di persona, `ESECUZIONE_LIVE.md:107-108`]** Correggere il bug
   già scritto dal coordinatore: oggi un annullo LEGITTIMO di Mike (un ritiro nostro
   riuscito) viene scritto a DB/UI con lo stesso `status='error'` di un vero rifiuto.
   È esattamente la distinzione "ritirato da noi" vs "rifiutato" richiesta
   dall'utente, oggi confusa in un solo stato per Mike. Fonte: citazione esatta in
   §5.7 sopra; non verificato se lo stesso bug esista anche in Safe/Omega (§7).

2. **[CERTO — fonte Betfair]** Loggare/esporre `lapseStatusReasonCode` quando un
   ordine risulta `size_lapsed>0`: il campo esiste già nella risposta di
   `listCurrentOrders`/order stream (`lsrc`, betfairlightweight lo espone come
   `lapse_status_reason_code`, `betfairlightweight/streaming/cache.py:444,473`), ma
   `omega_market._riga_corrente` (`omega_market.py:1405-1442`) oggi non lo legge.
   Con questo campo, Mike (§5.5) potrebbe dichiarare "scaduto per MKT_SUSPENDED" con
   la certezza di Betfair, invece di dedurlo dal fatto di essere in una finestra di
   sospensione. Fonte: [Exchange Stream API — Lapse Status Reason Code](https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687396/Exchange+Stream+API).

3. **[DEDUZIONE, ma già decisa dal coordinatore in `ESECUZIONE_LIVE.md`]** Riaccendere
   il runner flumine e agganciare Mike (poi Omega, poi Safe, ordine già scritto in
   `ESECUZIONE_LIVE.md` §6) all'order stream per gli ordini appoggiati: oggi TUTTI i
   bot scoprono un fill o un LAPSE al polling successivo, mai in push. Non è una mia
   proposta nuova — è la stessa priorità che il coordinatore ha già scritto; la
   riporto qui perché è la risposta più diretta possibile a «il bot deve essere
   informato di ogni cosa... il più rapidamente possibile».

4. **[CERTO — fonte Betfair]** Sul caso "esito incerto": la documentazione dice che
   un `TIMEOUT` va verificato su `listCurrentOrders` aspettando **fino a 15 secondi**
   prima che Betfair stessa faccia scadere l'ordine non processato. Verificare che
   questa attesa sia rispettata anche per un TIMEOUT che arriva DURANTE l'esecuzione
   (non solo alla ripresa dopo un crash, dove `motore_ordini.riprendi_da_diario`,
   righe 1624-1668, già lo fa bene). Fonte: [Betting Enums — InstructionReportStatus.TIMEOUT](https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687455).

5. **[DEDUZIONE, spunto dal competitor FairBot]** FairBot avvisa l'utente **al
   momento stesso** in cui il mercato si sospende in-play (non solo alla riapertura).
   Mike oggi gestisce correttamente l'esito ALLA RIAPERTURA (`_sorveglia_sospensione`,
   `service.py:2872` e seguenti), ma — nei file letti in questo audit — non ho
   trovato un avviso a schermo emesso nell'istante stesso della sospensione
   (potrebbe esistere nel frontend/UI, fuori dal perimetro di sola lettura sul
   backend di questa ricerca: vedi §7). Fonte competitor: [fairbot.com](https://fairbot.com/).

6. **[DEDUZIONE]** Il pattern "posizione di conto" (§5.4) oggi legge solo in LIVE e
   solo ogni `reconcile_every_s` (~30 s per partita): se l'utente chiude una
   posizione manualmente proprio a cavallo di quella finestra, Mike lo scopre con
   un ritardo fino a quel tanto. Non ho trovato nulla che lo renda più rapido di
   così nella documentazione ufficiale (§2.9: non è chiaro nemmeno se lo stream
   ordini, filtrato per `customerStrategyRef`, mostrerebbe MAI una bet altrui — la
   lettura senza filtro di strategia resta necessaria). È una scelta di trade-off
   già fatta e dichiarata dal codice (chiamata REST "in più", quindi centellinata),
   non un difetto nuovo: la riporto solo perché è il limite reale di ciò che
   l'utente ha chiesto ("in ogni momento").

---

## 7. Cosa non ho potuto verificare

- **Nessuna frase ufficiale Betfair** dichiara esplicitamente che un ordine LAPSE
  già a riposo viene cancellato a OGNI sospensione in-play (non solo al turn-in-play
  iniziale): l'unico appiglio ufficiale è il `lapseStatusReasonCode=MKT_SUSPENDED`,
  che descrive un tentativo di match durante la sospensione, non la cancellazione a
  freddo di un ordine già in coda. Il fatto che questo avvenga davvero è misurato
  dai nostri test dal vivo (17/09) e confermato dalla guida di Bet Angel (§3.1), non
  da un testo Betfair che io abbia trovato.
- **Nessuna frase ufficiale** su come/se le bet piazzate manualmente sul sito sono
  visibili all'API esattamente come quelle via API (§2.9): ho dedotto dal
  comportamento documentato dei filtri di `listCurrentOrders`, non da una
  dichiarazione esplicita.
- **UI/frontend**: ho verificato solo il backend Python (i bot, il motore ordini).
  Non ho controllato se gli stati `vivo/scaduto/abbinato/parziale/ignoto/chiuso_dall_utente`
  arrivano davvero a schermo nella pagina del trader — era fuori dal perimetro di
  questa ricerca (repo Python + documentazione), e il compito era di sola lettura
  sul codice indicato.
- **Safe e Omega in dettaglio**: ho verificato con `grep` che entrambi hanno la
  logica "chiuso dall'utente" e una gestione delle sospensioni (`AttesaRiapertura`),
  ma NON ho letto per intero la loro classificazione a 4 vie come ho fatto per Mike
  (§5.5): non posso escludere differenze fini che un grep non mostra.
  `Betfair/safe_strategy/execution.py` e `Betfair/omega/omega_service.py` sono
  entrambi >2000 righe; ho letto solo le sezioni trovate per parola chiave.
- **Il bug `status='error'` su annullo legittimo di Mike** (§5.7, §6.1): trovato
  scritto per Mike in `ESECUZIONE_LIVE.md:107-108`. Non ho verificato se lo stesso
  problema esista anche nella scrittura a DB/UI di Safe o Omega: sarebbe da
  controllare con un grep dedicato su `status.?=.?.error` nei rispettivi file di
  servizio prima di considerarlo un difetto specifico solo di Mike.
- **Documentazione completa dei competitor**: ho letto solo pagine pubbliche
  trovate via ricerca web (manuali, forum, siti commerciali), non il codice
  sorgente (nessuno di questi tool è open source) né manuali PDF completi (es. il
  `userguide.pdf` di Gruss, 900+ pagine secondo l'indice, non scaricato per intero).
  Per Geeks Toy in particolare la documentazione pubblica sul comportamento interno
  in caso di sospensione/gol è scarsa o assente.
- **`Betting Type Definitions`** (id 2687465): pagina molto lunga (definizioni di
  decine di tipi); ho letto solo le sezioni con `OrderStatus`/`PersistenceType`/
  `sizeLapsed` ecc., non l'intera pagina.
- **Nessuna chiamata API Betfair reale** è stata fatta in questa ricerca (vincolo
  rispettato): tutto quanto scritto sullo stream/REST viene da documentazione e
  codice, non da una verifica live in questa sessione.
