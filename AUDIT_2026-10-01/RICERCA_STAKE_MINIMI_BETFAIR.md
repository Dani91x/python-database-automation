# Ricerca: stake minimi su Betfair Exchange Italia e come chiudere sotto il minimo

Data: 01/10/2026. Sola lettura: nessun file di codice modificato.
Metodo: documentazione ufficiale letta per intero dall'API REST di Confluence (non dal
riassunto della pagina), articoli di supporto letti dall'API di Zendesk, forum letti post
per post. Date «ultima modifica» prese dai metadati delle pagine.

Caso di partenza: posizione aperta «banca Under 4,5 6,32 € @1,23». Il bot ha mandato
«banca Over 4,5 0,43 € @18», rifiutata con `INVALID_BET_SIZE`. Chiusura a mano con «punta
Under 4,5 7,47 € @1,03», accettata.

---

## 0. In breve

1. **Le regole ufficiali per .it (documentazione per sviluppatori)**: la punta va da
   **2,00 €** in su, *«can only be incremented in multiples of 50 Euro Cents»*. Per la
   banca conta la **puntata del controparte** (lo stake del backer, cioè il `size` di una
   LAY), che deve essere **≥ 0,50 €**. La liability non conta. La banca da 0,43 € è stata
   rifiutata proprio per questo: 0,43 < 0,50. Su .it **non valgono** né il «Min Bet
   Payout» né il `betTargetType`.
2. **Non esiste un'eccezione ufficiale** per gli ordini che riducono l'esposizione.
   Nessun campo API permette di piazzare direttamente sotto il minimo, e Betfair non
   espone il proprio cash out via API. L'unica via, nota e tollerata, è il
   **place-and-trim**: piazzare il minimo, ridurlo con un cancel parziale, poi spostarne il
   prezzo. Dal 19/06/2020 il trim e lo spostamento sono soggetti al controllo
   `INVALID_PROFIT_RATIO` (banda −20 % / +25 %).
3. **Reperto sul nostro codice.** `live_order_build.py` (righe 18-19 e 224-227) dichiara
   che con `reduces_liability=True` Betfair «consente size sotto il minimo». **Nessuna
   fonte Betfair lo dice**, e il rifiuto di oggi lo smentisce: un ordine diretto sotto il
   minimo viene rifiutato anche quando chiude una posizione.
4. **Per il nostro caso.** In un mercato a due esiti (Over/Under), la banca di S € sul
   lato opposto alla quota q equivale esattamente a una **punta sulla STESSA selezione di
   S·(q−1) €** alla quota q/(q−1). Oggi: banca Over 0,43 @18 ≡ punta Under **7,31 €** @1,0588.
   Quella punta supera il minimo e si piazza direttamente. Il place-and-trim serve solo
   quando anche la punta equivalente resta sotto il minimo.
5. **Da verificare sul conto reale.** La regola dei multipli di 0,50 € è contraddetta
   dalla punta 7,47 € accettata oggi. Inoltre il blog ufficiale betfair.it (30/10/2023,
   pagina non leggibile per un blocco anti-bot) annuncia una «bancata minima a 1 €». Le
   regole .it della documentazione per sviluppatori potrebbero quindi non essere
   aggiornate (vedi §1.4).

---

## 1. Regole ufficiali dei minimi: .it, UK/internazionale

### Risposta breve

| Exchange | Punta (BACK) | Banca (LAY) | Passo | Eccezioni |
|---|---|---|---|---|
| **.it** (documentazione per sviluppatori) | stake ≥ 2,00 €, «incrementato in multipli di 0,50 €» | lo stake del backer corrispondente (il `size` della LAY) ≥ 0,50 € | testo «multipli di 0,50 €», ma contraddetto dalla prova di oggi | nessun Min Bet Payout, nessun `betTargetType`; max 50 istruzioni per richiesta; punta e banca nella stessa richiesta = rifiuto; vincita potenziale ≤ 10.000 € |
| **Internazionale / UK** (Currency Parameters) | EUR **1** · GBP **1** | stesso minimo sul `size` | al centesimo (dedotto: nessun passo documentato) | sotto il minimo è valido se `size × price ≥ Min Bet Payout` (EUR 20, GBP 10), solo LIMIT; BSP lay: liability minima EUR 10 / GBP 10 |

### Evidenze

- **«Betting On Italian Exchange»**, documentazione ufficiale, ultima modifica
  **31/07/2026**:
  https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687808/Betting+On+Italian+Exchange
  Testo: *«The stake for each back offer is a minimum of 200 Euro Cents and can only be
  incremented in multiples of 50 Euro Cents. Any lay offers placed by the customer, must
  be placed in such a way as to ensure that the stake for any corresponding back offer
  amounts to a minimum of 50 Euro Cents. A placeOrders request may contain up to 50 bet
  instructions… We cannot accept betting offers with potential winnings… that exceed…
  (10,000 Euros)… placeOrders request containing both back and lay bets in the same order
  will be rejected.»*
- Lo stesso testo compare nell'articolo di supporto **«How Do I Access Betfair Italy
  Exchange via the API?»**, aggiornato il **18/06/2026**:
  https://support.developer.betfair.com/hc/en-us/articles/26096487231644-How-Do-I-Access-Betfair-Italy-Exchange-via-the-API
- **placeOrders**, ultima modifica **31/07/2026**:
  https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687496/placeOrders
  - *«Please note that additional bet sizing rules apply to bets placed into the Italian
    Exchange.»*
  - Limite di istruzioni per richiesta: 200 sull'exchange internazionale, 50 su quello
    italiano.
  - «Ability to place lower minimum stakes at larger prices» (Min Bet Payout): *«This
    function is only enabled for UK & International customers and not .it, .es, .dk and
    .se jurisdictions.»*
  - Bet to Payout / Profit (`betTargetType`): stessa esclusione per .it.
- **Additional Information → Currency Parameters**, ultima modifica **04/09/2026**:
  https://docs.developer.betfair.com/display/1smk3cen4v3lu3yomq5qye0ni/Additional+Information
  - EUR: Min Bet Size **1**, Minimum BSP Liability **10**, Minimum Bet Payout **20**.
  - GBP: 1 / 10 / 10.
  - Questi sono i parametri dell'exchange internazionale. Su .it prevalgono le regole
    della pagina italiana.
- **`INVALID_BET_SIZE`** (Betting Enums, ultima modifica **17/07/2026**):
  https://docs.developer.betfair.com/display/1smk3cen4v3lu3yomq5qye0ni/Betting+Enums
  Testo: *«The bet size is invalid for your currency or your regulator.»* Il «your
  regulator» copre il caso .it.
- **Altre voci dello stesso elenco**:
  - **`REJECTED_BY_REGULATOR`**: *«On the Italian Exchange this error will occur if more
    than 50 bets are sent in a single placeOrders request.»*
  - **`BET_TAKEN_OR_LAPSED`**: viene restituito anche su placeOrders *«if… a bet is placed
    at the point when a market admin event takes place»*, oppure quando il
    `marketVersion` è superato.
- **Storia dei minimi**:
  - Riduzione del minimo per molte valute dal 28/03/2022 (annuncio sul forum ufficiale
    per sviluppatori; EUR non compare nell'elenco):
    https://forum.developer.betfair.com/forum/developer-program/announcements/35967-betfair-exchange-change-of-minimum-stake-multiple-currencies-28th-march-2022
  - La stampa italiana scrive che la riduzione da 2 € a 1 € del 28/03/2022 «riguarda
    anche il mercato italiano»: assopoker, 29/03/2022,
    https://www.assopoker.com/betting-exchange/betting-exchange-betfair-stakes_288712/ ;
    statistiche-lotto, senza data,
    https://www.statistiche-lotto.it/betfair-puntata-minima-a-1-euro/
  - Blog ufficiale betfair.it, «anche la bancata minima viene portata a 1€», URL datato
    301023: https://scommesseonline.betfair.it/bancata-minima-1-euro-301023-369.html
    **Non leggibile** (blocco anti-bot Cloudflare / 403). Ho visto solo l'estratto del
    motore di ricerca: banca minima da 2 € a 1 €, «puntata minima di 1€ già disponibile da
    tempo».

### 1.4 Contraddizioni da risolvere sul conto reale (non risolvibili dalle fonti)

- **(i) Passo di 0,50 €.** La documentazione per sviluppatori lo impone, ma la punta
  7,47 € di oggi è stata accettata. Due spiegazioni possibili, entrambe *dedotte e non
  documentate*:
  - la regola è superata;
  - la regola vale per gli **aumenti di size** di un ordine esistente. La tecnica
    italiana del 2014 «2,00 → 2,50 crea una seconda scommessa da 0,50» è coerente con
    questa lettura.

  Fonti: bettingtraderblog, 25/05/2014,
  https://bettingtraderblog.com/2014/05/come-puntare-cifre-inferiori-ai-2-su-betfair-exchange.html ;
  bettingexchange.it, commenti dal 2014,
  https://bettingexchange.it/come-puntare-e-bancare-50-centesimi-con-betfair-exchange/

  Il nostro `live_order_build.py` applica ancora `IT_BACK_STEP = 0.50` (riga 41).
- **(ii) Minimi attuali su .it.** Il minimo di punta è 2 € secondo la documentazione,
  1 € secondo la stampa. Il minimo di banca è 0,50 € secondo la documentazione, 1 €
  secondo il blog betfair.it del 2023.

  Conseguenza pratica: se il minimo LAY fosse oggi 1 €, il **parcheggio** del nostro
  place-and-trim LAY (0,50 €, `IT_LAY_MIN_SIZE`) verrebbe rifiutato con
  `INVALID_BET_SIZE`.

  **Come verificarlo senza ordini nuovi**: leggere dallo storico del conto
  (`listClearedOrders` / `listCurrentOrders`, sola lettura) le size .it già accettate e
  rifiutate. Un ordine di prova vero spetta solo all'utente.

---

## 2. Eccezioni ufficiali: si può stare sotto il minimo quando si riduce l'esposizione?

### Risposta breve

**No, non come eccezione dichiarata.**

- Nessun campo serve allo scopo: `minFillSize` non può stare sotto il minimo, e
  `betTargetType` e il Min Bet Payout sono vietati su .it.
- Il cash out del sito non è disponibile via API.
- Betfair **non documenta** il «place at 1000 then reduce» come procedura. Lo riconosce
  però di fatto: nel 2020 ha introdotto `INVALID_PROFIT_RATIO` per i trim «sleali» e ha
  descritto proprio quei casi («cancel a bet down to a remaining size», «price-editing a
  13p @ 1000 bet»). È una tecnica che si regge sulla tolleranza, non su un diritto.

### Evidenze

- **`minFillSize`** (Betting Type Definitions, ultima modifica **11/12/2025**):
  https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687465
  - Vale solo con `timeInForce=FILL_OR_KILL`.
  - `INVALID_MIN_FILL_SIZE`: *«The minFillSize cannot be less than the minimum bet size
    for your currency»* (Betting Enums, 17/07/2026).
- **`betTargetType` PAYOUT / BACKERS_PROFIT** (placeOrders, 31/07/2026): *«only enabled for
  UK & International customers and not .it»*. Fonte: placeOrders, link al §1.
- **`customerStrategyRef`** (placeOrders): è solo un'etichetta fino a 15 caratteri,
  restituita sullo stream degli ordini. Non ha alcun effetto sui minimi.
- **Cash out**: *«The 'Cashout' functionality isn't available via the API as an
  operation»*. Betfair rimanda a un algoritmo esterno per calcolare la copertura.
  Articolo di supporto aggiornato il **21/07/2026**:
  https://support.developer.betfair.com/hc/en-us/articles/115003887431-Is-Cashout-available-via-the-Betfair-API
  Come il cash out del sito piazzi importi piccoli **non è documentato** (non trovato).
- **`INVALID_PROFIT_RATIO`**, articolo ufficiale aggiornato il **21/07/2026**:
  https://support.developer.betfair.com/hc/en-us/articles/360010423978-Why-am-I-receiving-the-INVALID-PROFIT-RATIO-error
  Testo: *«This doesn't impact all bets below £2 but only those that meet specific
  criteria which we consider unfair. Any attempt to place, cancel or update a bet at these
  stake and price combinations will result in the error… returns 20% less or 25% more
  than it 'ought' to… • Cancel £1.83 of a £2.00 bet @ 1.06 (to leave a 13p remainder @
  1.06) • Price-editing a 13p @ 1000 bet to 13p @ 1.06…»*
  Cita il regolamento: *«You are not permitted to place bets… which deliberately take
  advantage of Betfair rounding»*.
- **Annuncio originale del 19/06/2020** («Retrospective – API Release To Prevent Minimum
  Bet Abuse»):
  https://forum.developer.betfair.com/forum/developer-program/announcements/32066-retrospective-api-release-to-prevent-minimum-bet-abuse-19th-june
  - Nelle risposte, gli sviluppatori descrivono la procedura «storica» per il green-up
    (placeOrders → cancelOrders con `sizeReduction` → replaceOrders). Betfair non la
    smentisce e la lascia in piedi.
  - Misure empiriche degli utenti (pagine 2-3 del thread): per una LAY, la liability
    residua deve essere **≥ circa 0,008**. Esempi:
    - si può bancare 0,01 @1,8 ma non @1,79;
    - 0,80 si parcheggia @1,01, 0,79 no;
    - quota minima di parcheggio ≈ `1 + 0,008 / size`, arrotondata al tick superiore;
    - alcune size sono rifiutate comunque (1,49 @1,01).
- **Rischio sul conto**: secondo un commento su bettingtraderblog del 28/03/2022 (link al
  §1.4), un utente è stato «richiamato» da Betfair per uso ripetuto della tecnica.
  Secondo Market Feeder Pro, citato sul forum Bet Angel nel 2010
  (https://forum.betangel.com/viewtopic.php?t=2620), alcuni conti sono stati sospesi per
  abuso. **Aneddotico, non documentato da Betfair.**

---

## 3. Come fanno i competitor

### Risposta breve

Tutti usano la stessa macchina in 3 o 4 passi: parcheggio del minimo a quota fuori
mercato, riduzione, spostamento del prezzo. Le varianti:

- **BACK** parcheggiato @1000 (Bet Angel, Geeks Toy) o @990/900 (Cymatic).
- **LAY** parcheggiato @1,01. Dal 06/2020 si parcheggia invece alla quota più bassa che
  supera `INVALID_PROFIT_RATIO`: 1,02-1,10 secondo la size, oppure 1,8 per le size più
  piccole (Gruss, forum per sviluppatori).
- **Riduzione** con `cancelOrders.sizeReduction` (Bet Angel), oppure con un «size-up»
  che crea un secondo ordine piccolo, seguito dalla cancellazione del primo (Geeks Toy,
  Gruss, tecnica manuale italiana).
- **Residuo accettato.** Se Betfair rifiuta il trim per arrotondamento, Bet Angel accetta
  un P&L «sbilanciato di qualche centesimo» e lo scrive nel log.
- **Guardia sul prezzo.** Bet Angel blocca le chiusure sotto il minimo su selezioni con
  quota sopra una soglia scelta dall'utente.
- **Bet delay.** Ogni passo di place o replace subisce il ritardo. Il cancel no.

**Bet Angel non funziona con conti .it**: è il loro supporto a dirlo (vedi sotto).

### Evidenze

- **Bet Angel**
  - KB «What is the minimum bet allowed», 23/04/2023:
    https://support.betangel.com/support/solutions/articles/80001073147-what-is-the-minimum-bet-allowed
    *«Place a bet of £2 at 1000. 80p is removed and the remain moved down to 7.8… it will
    take twice as long… this also includes the in-play delay… on very rare occasions your
    bet might get matched at 1000…»*
  - Guida «Green Up Settings», senza data:
    https://www.betangel.com/user-guide/green_up_settings.html
    Opzione «Trade Closure Bets Being Placed on Selections Priced >»: *«In fast moving
    markets the £2 stake maybe matched @ 1000 before Bet Angel can cancel part of it…»*
  - KB «When I see bets at 1.01 or 1000», 26/04/2023:
    https://support.betangel.com/support/solutions/articles/80001073646-when-i-am-using-the-software-i-see-bets-at-1-01-or-1000
    *«During in-play events each step… is subject to the in-play delay… This can add up to
    30 seconds»*.
  - KB su `INVALID_PROFIT_RATIO`, 21/04/2023:
    https://support.betangel.com/support/solutions/articles/80001073003-while-greening-up-unable-to-place-lay-bet-due-to-betfair-s-rules-regarding-pay-out-liability-rounding
    P&L «uneven by a few pence».
  - KB su .es e .it, 23/04/2023:
    https://support.betangel.com/support/solutions/articles/80001073138-using-bet-angel-with-betfair-es-and-betfair-it-accounts
    *«It will not work with the Betfair.es and the Betfair.it betting exchanges»*.
  - Peter Webb (Bet Angel), 06/2020:
    https://www.peterwebb.com/betfair-api-greening-hedging-cash-out-issues/
    Patch rilasciata in giornata dopo aver chiarito con Betfair i nuovi parametri.
- **Geeks Toy**
  - Forum «Hedging delay», mercato U/O 2.5 calcio:
    https://www.geekstoy.com/forum/forum/geeks-toy/help/4222-hedging-delay
    Sequenza: lay 2 @1,01 (8 s nel calcio estero in gioco), size-up a 3 (crea un ordine
    separato da 1, altri 8 s), cancel del 2 e riprezzo dell'1 (altri 8 s): **circa 25 s
    in totale**.
  - Forum, sotto-minimo:
    https://www.geekstoy.com/forum/forum/betting-trading/newbies-corner/6806-minimum-bet-placement-possible-with-geeks-toy
    *«first places a 2 euro bet @1000 and then amends stake… if current price is already
    1000, all 2 euro are matched»*.
- **Gruss Betting Assistant**
  - Forum «Laying below minimum stakes», 19-23/06/2020:
    http://www.gruss-software.co.uk/forum/viewtopic.php?f=13&t=10610
  - Dopo il cambio del 2020 il trim falliva e **l'ordine pieno da 5 AUD finiva alla quota
    vera (1000)**. Un utente segnala una perdita di circa 1.300 AUD.
  - Un utente italiano: il parcheggio @1,01 falliva, @1,10 funzionava. Gruss ha
    rilasciato una correzione.
- **Cymatic Trader** (forum, 12/10/2014): http://www.cymatic.co.uk/forum/topic106-10.html
  *«a bet can get stuck at 990, if you are trying to back a stake less than £2… it has to
  first make a £2 bet and then amend it»*. Il supporto consiglia di aprire con stake
  sopra il minimo, per non dover chiudere con il «4 stage process».
- **Bf Bot Manager**: la pagina della KB
  (https://www.bfbotmanager.com/en/help/knowledge_base/article/38-what-is-minimum-bet-size-and-can-bot-place-bets-below-minimum-bet-size)
  risponde 403. Ho letto solo l'estratto del motore di ricerca: per gli ordini exchange
  «no minimum bet size, but bet payout must result in fair payout», e il consiglio di
  alternare anche puntate regolari. **Non verificato sulla pagina.**
- **Fairbot, BetTrader**: **non ho trovato** documentazione su come trattano il
  sotto-minimo.
- **Quando il place-and-trim non è possibile o è lento in gioco**:
  - Il **cancel (anche parziale) non subisce il bet delay**; place e replace sì.
    Risposta sul forum ufficiale per sviluppatori («Betdelay», data non rilevata):
    https://forum.developer.betfair.com/forum/sports-exchange-api/exchange-api/3347-betdelay
    *«replaceOrders will also have the delay… Cancelling an order is, however, not subject
    to the delay»*, e inoltre *«If the market suspends during the bet delay period… the
    bet will lapse.»*
  - Articolo ufficiale, 06/07/2026:
    https://support.developer.betfair.com/hc/en-us/articles/360002825652-Why-do-you-have-a-delay-on-placing-bets-on-a-market-that-is-in-play
    *«The amount of delay your placeOrders/replaceOrders requests are subject to…»*
  - **Passive bet delay**: su alcuni mercati in gioco, gli ordini che non si abbinano
    subito (come il nostro parcheggio) entrano **senza ritardo**. Si riconoscono dal campo
    `betDelayModels` (PASSIVE / DYNAMIC). Articolo del 15/06/2026:
    https://support.developer.betfair.com/hc/en-us/articles/26791968420636-How-can-I-identify-markets-that-accept-passive-orders-via-the-Betfair-API
    Nel calcio la funzione è attiva solo su «selected football markets». Sintesi
    divulgativa di Bet Angel: https://www.betangel.com/betfair-passive-bet-delay/
  - Il riprezzo verso una quota abbinabile è «aggressivo» e resta comunque ritardato
    (*dedotto*, dalla definizione stessa di passive bet).

---

## 4. Rifiuti noti e come evitarli

Fonte dei testi: Betting Enums, 17/07/2026
(https://docs.developer.betfair.com/display/1smk3cen4v3lu3yomq5qye0ni/Betting+Enums), salvo
dove indicato diversamente.

| Errore | Causa | Come evitarlo |
|---|---|---|
| `INVALID_BET_SIZE` | size sotto il minimo di valuta o di regolatore. Su .it: punta < 2 € (o fuori passo); LAY con `size` (stake del backer) < 0,50 €. La liability non conta. | Controllare il minimo .it **sul `size`** prima di inviare. Sotto il minimo: punta equivalente sulla stessa selezione (§5a) oppure place-and-trim (§5b). Arrotondare a 2 decimali. |
| `INVALID_PROFIT_RATIO` | place, cancel parziale o replace che lascia un ordine il cui guadagno, dopo l'arrotondamento al centesimo, devia di oltre −20 % / +25 % (articolo del 21/07/2026, §2). | Prima di **ogni** passo calcolare `ratio = arrotondato(size·(p−1)) / (size·(p−1))` per la BACK, e la liability per la LAY, e verificare 0,80 ≤ ratio ≤ 1,25. Per le LAY piccole parcheggiare alla quota minima `≥ 1 + 0,008/size` (empirico, forum per sviluppatori 2020). Il metodo di arrotondamento di Betfair (al più vicino o per difetto) **non è documentato**. |
| `MARKET_SUSPENDED` / `MARKET_NOT_OPEN_FOR_BETTING` | gol o VAR: mercato sospeso. | Non inviare durante la sospensione e ritentare quando torna `OPEN`. Usare `marketVersion` (sotto) per non finire nel mercato riformato con un prezzo vecchio. |
| `BET_TAKEN_OR_LAPSED` | evento amministrativo durante il ritardo, `marketVersion` superato, oppure cancel o replace di un ordine già abbinato o decaduto. | Osservare lo stato reale dallo stream degli ordini prima di ogni passo. Il parcheggio decaduto dopo un gol è un esito sicuro (nessuna esposizione). |
| `INSUFFICIENT_FUNDS` | esposizione o disponibile superati. | Parcheggiare la LAY alla quota bassa: la liability del parcheggio è quasi nulla (0,50 @1,02 → 0,01 €). Come Betfair calcoli l'esposizione di un ordine non abbinato che *riduce* una posizione **non è documentato**: tenere un margine. |
| `INVALID_ODDS` | prezzo fuori dal listino dei tick o > 1000. | `round_to_tick`. Il listino «Asian Handicap & Total Goal» usa incrementi di 0,01 fino a 1000 (placeOrders, 31/07/2026). L'Over/Under 4.5 di Betfair usa il listino standard (dedotto dal tipo di mercato: verificare `priceLadderDescription` in `listMarketCatalogue`). |
| `REJECTED_BY_REGULATOR` (.it) | più di 50 istruzioni in un placeOrders. | Massimo 50 per richiesta. |
| Rifiuto di un placeOrders con BACK e LAY insieme (.it) | regola .it («Betting On Italian Exchange», 31/07/2026). | Un lato per richiesta. |
| `CANCELLED_NOT_PLACED` (replace) | il cancel del replace è riuscito, il nuovo place no. *«the cancellations will not be rolled back»* (replaceOrders, ultima modifica 04/06/2024: https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687487). | Trattarlo come «posizione ancora aperta, nessun ordine a riposo» e ripartire dal passo 1. Esito sicuro: non c'è esposizione aggiunta. |
| `TIMEOUT` / `BET_IN_PROGRESS` | nessuna risposta entro 5 s; l'esito può comparire fino a 15 s dopo (Betting Enums). | Non reinviare alla cieca: riconciliare con lo stream degli ordini o con `listCurrentOrders` tramite `customerOrderRef`. Il `customerRef` deduplica le richieste solo per 60 s (placeOrders). |
| LAY sotto il minimo con liability sopra il minimo | su .it la regola riguarda **solo** lo stake del backer. Su .com vale il Min Bet Payout (`size × price ≥ 20 EUR`), vietato su .it (placeOrders). | Su .it il caso «stake piccolo, liability grande» resta comunque `INVALID_BET_SIZE` (prova di oggi: 0,43 @18, liability 7,31). |
| Replace in gioco con bet delay | il replace è un cancel immediato più un place ritardato (forum «Betdelay»). | Prevedere 1 ritardo per il parcheggio (0 se il mercato è PASSIVE) + 0 per il trim + 1 per il riprezzo. Passare `marketVersion` sia a placeOrders sia a replaceOrders. |

`marketVersion`, dalla documentazione di placeOrders (31/07/2026): *«in managed football
markets, you can avoid your bets reaching the Exchange after the market has reformed
following a goal»*. Nel calcio gestito, un gol è un evento «materiale»: lapsing/voiding.
Un ordine LAPSE non abbinato decade al gol. Un ordine PERSIST in gioco no:
*«Once in play, the bet won't be cancelled by Betfair if a material event takes place»*
(PersistenceType, Betting Enums).

---

## 5. Raccomandazione per il nostro caso

**Posizione**: banca della selezione U (Under 4,5) per S₀ @p₀. La chiusura calcolata
sull'altra selezione O (Over 4,5) è una banca di S € @q, con S < 0,50 €.

### (a) Punta sulla stessa selezione (prima scelta)

**Equivalenza** (dedotta con l'algebra; vale per un mercato a 2 esiti, prima della
commissione, che Betfair applica sul netto del mercato):

- banca O di S @q dà: O vince → −S(q−1); U vince → +S;
- punta U di B @p dà: U vince → +B(p−1); O vince → −B;
- le due coincidono per **B = S·(q−1)** e **p = q/(q−1)**.

Oggi: S = 0,43, q = 18 → **B = 7,31 € @1,0588**. Sul listino, a 1,05 o 1,06, sono
quote diverse dalla 1,03 a cui ha chiuso l'utente: lui ha preso il prezzo disponibile su U.

- **Pro**
  - B è quasi sempre ≥ 2 €. Basta B ≥ 2 € ⇔ S ≥ 2/(q−1): con q = 18 vale già da
    S ≥ 0,12 €.
  - Una sola chiamata e un solo bet delay.
  - Nessun parcheggio, quindi nessun rischio di abbinamento accidentale.
  - Nessun `INVALID_PROFIT_RATIO`: il controllo colpisce solo le combinazioni sotto il
    minimo (articolo del 21/07/2026).
- **Contro**
  - Il prezzo da usare è quello del libro di U, non il riflesso di quello di O. I due
    libri possono differire: l'abbinamento incrociato (cross-matching) non garantisce
    parità di prezzo.
  - Il passo di 0,50 €, se fosse davvero applicato, imporrebbe di arrotondare B (§1.4).
    Oggi 7,47 € è stato accettato.
- **Sequenza API**
  1. `placeOrders(marketId, instructions=[{selectionId: U, handicap: 0, side: BACK,
     orderType: LIMIT, limitOrder: {size: B (2 decimali), price: <prezzo del libro di U,
     al tick>, persistenceType: LAPSE}, customerOrderRef: <id idempotente>}],
     marketVersion: {version: <ultima versione vista>}, customerStrategyRef: <bot>)`.
     Un solo lato per richiesta (regola .it).
  2. Conferma solo dallo stream degli ordini (`sizeMatched`, `sizeRemaining`), mai dalla
     risposta da sola.
  3. Residuo non abbinato: `cancelOrders` (immediato) e ricalcolo.

  Quanto essere aggressivi sul prezzo (taker vs tick più favorevole, eventuale
  `FILL_OR_KILL`) è una **scelta di strategia dell'utente**. Qui non la modifico. Note
  tecniche: FOK lavora sul prezzo medio ponderato (VWAP), e `minFillSize` non può stare
  sotto il minimo (placeOrders, Betting Type Definitions).

### (b) Place-and-trim (solo quando anche la punta equivalente è sotto il minimo .it)

Vale anche per le LAY sotto 0,50 € quando non c'è un'equivalente sopra il minimo.

**Passi per una BACK di B < minimo @p_target su U:**

1. **Parcheggio.** `placeOrders`: BACK, size = minimo .it (2,00 per la documentazione,
   da verificare: §1.4), price = **1000**, persistenceType = LAPSE, `customerOrderRef`,
   `marketVersion`. È la richiesta di un solo lato.
   - In gioco subisce il bet delay, salvo mercato con `betDelayModels` PASSIVE: il
     parcheggio non si abbina, quindi è passivo.
   - Prima di inviare, controllare che la miglior quota di banca su U sia ≪ 1000. Se U è
     già prossima a 1000, il parcheggio si abbina (Geeks Toy, Bet Angel).
2. **Osservazione.** Dallo stream: ordine EXECUTABLE con `sizeMatched = 0`. Se
   `sizeMatched > 0` → ABORT, senza ritentare. La guardia c'è già in `submin.py`.
3. **Trim.** `cancelOrders(marketId, [{betId, sizeReduction: round(min − B, 2)}])`. È
   **immediato**: il cancel non subisce ritardo. Prima del trim, controllare il ratio
   sul residuo a 1000: con B·999 è praticamente sempre valido.
4. **Verifica del trim.** `sizeRemaining == B` osservato sullo stream. Senza questa
   osservazione non si riprezza: lezione Gruss 2020 e bug del 10/07 annotato in
   `submin.py`.
5. **Riprezzo.** `replaceOrders(marketId, [{betId, newPrice: p_target}],
   marketVersion: {...})`.
   - Controllare **prima** il ratio a p_target: `round(B·(p−1), 2) / (B·(p−1))` in
     [0,80; 1,25].
   - A quote basse il controllo morde: per esempio B = 0,20 @1,03 → guadagno teorico
     0,006, arrotondato a 0,01 → +67 % → rifiuto.
   - Subisce il bet delay e restituisce un **nuovo betId**.
   - `CANCELLED_NOT_PLACED` lascia la posizione invariata, senza esposizione extra: si
     riparte dal passo 1.

**Per una LAY di S < 0,50 € @q:** stessi passi, con parcheggio LAY di size minima .it
(0,50 per la documentazione, da verificare: §1.4) alla quota **minima che supera il
controllo sul residuo**, cioè `p_park ≥ 1 + 0,008/S` arrotondato al tick superiore
(empirico, forum per sviluppatori 2020), e non necessariamente 1,01.

- Esempio oggi: S = 0,43 → 1,0186 → **1,02**.
- Liability residua 0,0086, arrotondata a 0,01 → +16 % → valida.
- A 1,01: 0,0043 → arrotondata a 0,00 → rifiuto (*dedotto*: il metodo di arrotondamento
  non è documentato).
- Il riprezzo a 18 porta la liability a 7,31: valida.

**Rischi in gioco** (sintesi delle fonti sopra):

- **Tempo.** Ritardo di parcheggio + 0 + ritardo di riprezzo. Nel calcio sono circa
  2 × 5-8 s (Geeks Toy misura 8 s per passo nel calcio estero). Diventa circa un solo
  ritardo se il mercato è PASSIVE. Il prezzo intanto si muove: il riprezzo va ricalcolato
  sul libro attuale, non su quello di partenza.
- **Gol durante il ritardo.** Il parcheggio o il riprezzo decadono: `marketVersion` o
  LAPSE (forum «Betdelay» e placeOrders). È un esito sicuro, ma la posizione resta
  aperta.
- **Abbinamento accidentale del parcheggio.** Improbabile a 1000 o 1,02 su un mercato
  normale. Possibile quando la selezione è già a quote estreme, o se il mercato si
  riforma. → ABORT e riconciliazione a mano.
- **Trim che fallisce in silenzio.** Il rischio più costoso: l'ordine pieno finisce alla
  quota vera (Gruss 2020). → Mai riprezzare senza aver osservato il residuo.
- **`INVALID_PROFIT_RATIO` al trim o al riprezzo.** → Controllo preventivo; se fallisce,
  restano un parcheggio a vuoto (da cancellare, immediato) e un residuo di P&L di pochi
  centesimi (la stessa scelta di Bet Angel).
- **Uso ripetuto.** Possibile attenzione da parte di Betfair (aneddotico, §2).

### Reperti sul codice da portare all'utente (non corretti: fuori perimetro)

1. `Betfair/stream/live_order_build.py`, righe 18-19 e 224-227: la premessa
   «`reduces_liability=True` consente size sotto il minimo» **non è documentata** da
   Betfair ed è smentita dal rifiuto di oggi. Un ordine di chiusura sotto il minimo va
   instradato verso (a) o (b), mai inviato direttamente.
2. `live_order_build.py`, riga 41 (`IT_BACK_STEP = 0.50`), contro la punta 7,47 € accettata
   oggi: va verificato sullo storico del conto (§1.4).
3. `Betfair/stream/trading/submin.py`, `initial_place_price`: il parcheggio LAY è fisso a
   1,01. Per size LAY residue sotto circa 0,80 il trim a 1,01 viola la soglia empirica
   di 0,008 di liability. Il modulo cita già `INVALID_PROFIT_RATIO` alla riga 752, ma la
   quota di parcheggio non dipende dalla size. Va verificato se un altro percorso
   (`park_price`, «percorso A») copre il caso.
4. `submin.py`, riga 49: la costante `SUBMIN_ABS_MIN_SIZE = 0.01` è dichiarata «da
   verificare empiricamente su .it». Nessuna fonte pubblica conferma il floor su .it.
5. flumine 2.13.11 (`controls/tradingcontrols.py:88`, `_validate_betfair_min_size`)
   valida solo il place, contro `min_bet_size` e `min_bet_payout` del client. Su .it il
   payout non vale: verificare che i valori del client .it siano coerenti con le regole
   italiane.

---

## 6. Tabella riassuntiva

| Tecnica | Quando usarla | Rischi | Fonte |
|---|---|---|---|
| Ordine diretto ≥ minimo | size ≥ minimo .it (BACK 2 €, LAY con size ≥ 0,50 €) | 1 bet delay; prezzo che scorre | Betting On Italian Exchange (31/07/2026); placeOrders (31/07/2026) |
| **Punta equivalente sulla stessa selezione** (B = S·(q−1)) | chiusura calcolata come banca < 0,50 € sull'altra selezione di un mercato a 2 esiti | libri di U e O non identici; eventuale passo di 0,50 € | algebra dedotta; regole .it come sopra |
| Place-and-trim BACK (2 € @1000 → cancel `sizeReduction` → replace) | punta necessaria < minimo .it | 2 ritardi in gioco (1 se PASSIVE); abbinamento a 1000 se la selezione è già lì; `INVALID_PROFIT_RATIO` al riprezzo su quote basse; possibile attenzione del conto | Bet Angel KB (23/04/2023); Geeks Toy forum; articolo INVALID_PROFIT_RATIO (21/07/2026) |
| Place-and-trim LAY (0,50 € @ p ≥ 1+0,008/S → cancel → replace) | banca necessaria < 0,50 € senza un'equivalente sopra il minimo | parcheggio a 1,01 rifiutato per size piccole; trim fallito → size piena alla quota vera (Gruss 2020) | forum per sviluppatori 32066 (06/2020); forum Gruss t=10610 (06/2020) |
| Size-up che crea un secondo ordine, poi cancel del primo | variante senza `sizeReduction` (Geeks Toy, tecnica manuale .it) | 3 ritardi (circa 25 s nel calcio); su .it produce multipli di 0,50 | Geeks Toy «Hedging delay»; bettingtraderblog (25/05/2014) |
| Accettare il residuo (P&L sbilanciato di pochi cent) | trim o riprezzo rifiutato per `INVALID_PROFIT_RATIO` | piccolo squilibrio tra gli esiti | Bet Angel KB (21/04/2023) |
| Blocco delle chiusure sotto il minimo su selezioni a quota alta | selezione vicina a 1000 (il parcheggio si abbinerebbe) | posizione lasciata aperta | Bet Angel «Green Up Settings» |
| `marketVersion` su place e replace | sempre in gioco nel calcio | l'ordine decade dopo un gol (sicuro, posizione ancora aperta) | placeOrders (31/07/2026) |
| Mercati PASSIVE (`betDelayModels`) | in gioco, per il parcheggio non abbinabile | disponibile solo su alcuni campionati | supporto per sviluppatori (15/06/2026) |
| `betTargetType` / Min Bet Payout | **mai su .it** | `INVALID_BET_SIZE` o rifiuto | placeOrders (31/07/2026) |

## Cosa non ho trovato o non ho potuto verificare

- Il testo del blog betfair.it «bancata minima a 1€» (30/10/2023) e dell'articolo del
  08/01/2024: 403 / Cloudflare. Ho solo gli estratti del motore di ricerca. I siti
  betfair.com e betting.betfair.com sono inibiti dall'ADM su questa rete (certificato
  «sito-inibito-giochi.adm.gov.it»), quindi niente regolamento .it ufficiale e niente
  newsletter.
- Come il cash out del sito o dell'app Betfair gestisca gli importi sotto il minimo: non
  documentato.
- Se su .it il trim con `sizeReduction` sotto il minimo sia ammesso via API, e fino a
  quale floor: nessuna fonte pubblica per .it. Le fonti dei competitor riguardano .com, e
  Bet Angel dichiara di non supportare .it.
- Il metodo di arrotondamento di Betfair nel calcolo di `INVALID_PROFIT_RATIO` (al più
  vicino o per difetto): non documentato. La soglia di 0,008 è empirica (utenti, 2020).
- Fairbot e BetTrader: nessuna documentazione trovata sul sotto-minimo. Bf Bot Manager:
  pagina 403, solo l'estratto del motore di ricerca.
- La data del thread «Betdelay» (forum per sviluppatori 3347) non è rilevabile
  dall'HTML.
