# Ricerca di mercato per il redesign (01/10/2026)

Metodo: WebSearch/WebFetch su pagine pubbliche + screenshot ufficiali scaricati in `screens/`.
Onesta': per i tool NON verificati direttamente (vedi "Limiti") le schede si basano su
sintesi di articoli di terzi, non su prove di schermata. Dove ho visto l'immagine lo dico.

## 1. Schede per tool

### Bet Angel (Pro + Guardian)
- Fonti: https://apps.betfair.com/trading/bet-angel-pro/ ; https://botblog.co.uk/bet-angel-ladder-trading-setup/ ; https://www.betfairtradingblog.com/bet-angel-guardian/
- Screenshot: `screens/bet-angel_ladder_pro-1.png`, `bet-angel_pro-2.png`, `bet-angel_ladder-setup.png`, `bet-angel_guardian-main.png`, `bet-angel_guardian-markets.png`. (Visto: `bet-angel_ladder_pro-1.png` = finestra impostazioni grafici sovrapposta, UI Windows classica chiara, grafico prezzo/volume/peso del denaro a destra, righe runner con P&L per runner.)
- Navigazione: nessuna sidebar; finestre multiple + Guardian come elenco multi-mercato con filtri. Barra "Global settings" in alto (offsetting automatico, green-up, stop-loss, uscite nominate): comandi di rischio sempre visibili.
- Testata: P&L per runner e colonna "Trade Profit"; il saldo non e' protagonista.
- Griglia/ladder: ladder densa, back a sinistra / prezzi al centro / lay a destra; celle cambiano colore con il movimento. La schermata One-Click e' una griglia stile Betfair aggiornata fino a 50/s.
- Colori: back azzurro, lay rosa (convenzione Betfair); profit/loss nelle colonne P&L.
- Dark mode: no (tema chiaro predefinito, personalizzabile).
- Comandi pericolosi: one-click SENZA conferma (scelta dichiarata); stop/green-up nella barra globale e come ordini automatici.
- Test/live: modalita' pratica separata ma poco evidente graficamente.

### Geeks Toy
- Fonti: https://apps.betfair.com/trading/geeks-toy/ ; https://botblog.co.uk/geeks-toy-ladder-trading-setup/ ; https://caanberry.com/geeks-toy-for-dummies-software-fully-explained/
- Screenshot: `screens/geeks-toy_ladder.png` (VISTO: a sinistra pannelli impilabili/comprimibili con intestazione scura e pulsanti "?" e "x"; al centro due ladder affiancate con prezzo al centro, volume matched a destra, back azzurro / lay rosa; a destra grid stile Betfair; riquadro in alto con countdown grande, percentuali book 101% / 99.2% in azzurro/rosa; sezione "Unmatched Bets" con ordini colorati come il lato e X rossa di cancellazione).
- Navigazione: pannelli verticali ripiegabili (accordion); layout salvabile.
- Testata: countdown e overround in evidenza; importo matched del mercato.
- Densita': massima; trascinamento degli ordini su/giu' sulla ladder per cambiare prezzo.
- Colori: back blu, lay rosa; ordini propri colorati come il lato.
- Pericolo: hotkey per piazza/cancella/hedge; cancella per riga.
- Test/live: nessuna distinzione grafica forte (limite).

### Fairbot / BetTrader / Cymatic Trader / Bf Bot Manager
- Fonti: https://botblog.co.uk/fairbot-review/ ; https://betting.exchange/bettrader-primer/ ; https://review.goalprofits.com/bf-bot-manager/ ; https://botblog.co.uk/betfair-bot-reviews/
- Fairbot: interfaccia essenziale, "funziona ma non e' moderna", focus sull'esecuzione. Lezione: la funzione batte l'estetica, ma un'estetica datata riduce la fiducia.
- BetTrader: tre viste (Ladder, Grid con 5 prezzi per lato, Sports = tutti i mercati di un evento insieme); one-click ovunque. Lezione: stessa posizione, tre densita'.
- Cymatic Trader: gratuito, ladder + grid, "training mode" (paper), coda posizione, multi-mercato, autopilot. Lezione: modalita' addestramento nominata e separata.
- Bf Bot Manager: all'apertura si sceglie il TIPO di bot (Trading, Dutching, Back/Lay, Multi Strategy, Soccer Draw, Notes); piu' strategie in parallelo senza codice. Lezione: ingresso per bot/strategia, non per mercato.
- Nessuna immagine ufficiale scaricabile trovata per questi quattro.

### Betfair Exchange web (grid, ladder, cash out), Smarkets, Betdaq
- Fonti: https://traderline.com/education/betfair-ladder-trading-guide ; https://botblog.co.uk/comparing-top-5-uk-sports-exchanges/ ; https://thetrader.bet/best-betting-exchanges/smarkets-vs-betdaq/
- Betfair web: griglia back/lay (azzurro/rosa) e cash out base con margine incorporato (diverso dall'esecuzione a mercato della ladder); nessuna posizione in coda ne' ordini di uscita pre-piazzati; refresh lento, molti passaggi.
- Smarkets: interfaccia moderna e pulita, commissione fissa 2%, pochi strumenti di terze parti. Betdaq: commissione bassa, interfaccia piu' classica.
- Lezione: la griglia serve a leggere, la ladder a eseguire; il cash out deve mostrare il costo reale.
- Nessuno screenshot ufficiale scaricato.

### TradingView
- Fonti: https://www.tradingview.com/support/solutions/43000745825-mastering-the-tradingview-watchlists/ ; https://www.tradingview.com/charting-library-docs/latest/ui_elements/Toolbars/
- Layout: grafico al centro, strumenti di disegno a sinistra, timeframe/indicatori in alto, barra destra con Watchlist / Avvisi / Dettagli / Notizie.
- Watchlist: sezioni trascinabili, tre viste (lista, tabella, avanzata): la densita' la sceglie l'utente.
- Colori: verde/rosso sul % di variazione; tema scuro curato.
- Test/live: il Paper Trading e' un "broker" selezionabile nel pannello trading.

### Bloomberg Terminal
- Fonti: https://www.bloomberg.com/ux/2021/10/14/designing-the-terminal-for-color-accessibility/ (403 al fetch, contenuto da sintesi di ricerca) ; https://ted-merz.com/2021/06/26/amber-on-black/
- Densita' massima, sfondo nero, ambra come colore di marca; semantico verde=su rosso=giu' ma con varianti progettate per il daltonismo (piu' sature/luminose, coerenti). Launchpad = pannello di componenti tabellari personalizzabili.
- Lezione: il colore semantico non deve essere l'unico segnale; un colore di marca separato dal semantico.

### Interactive Brokers TWS / Mosaic
- Fonti: https://www.ibkrguides.com/traderworkstation/mosaic-layout.htm ; https://www.interactivebrokers.com/en/trading/tws.php
- Screenshot: `screens/ibkr_tws-mosaic.jpg` (VISTO: tema nero; in alto barra Orders/Trades/Data; riquadro P&L giornaliero in rosso accanto a Margin/Liquidita'; tabella portafoglio con celle intere verdi/rosse (heatmap) per P&L e posizione; Order Entry in blu scuro; Buy blu / Sell rosso / Transmit rosso; tab dei layout in basso "Mosaic | Classic TWS | +"). Anche `screens/ibkr_tws-classic.jpg`.
- Mosaic: pannelli agganciati, collegati a colori (stesso colore = cambiano simbolo insieme), layout salvabili in tab in basso, Portfolio/Order Entry/Order Monitor sempre presenti, ordini collegati (bracket, OCO, stop).
- Paper: conto separato con 1.000.000 virtuali, stessa configurazione del live (specchio).

### Robinhood / Trade Republic
- Fonti: https://ixd.prattsi.org/2025/02/design-critique-robinhood-ios-app/ ; https://oh-my-design.kr/design-systems/robinhood
- Il valore del portafoglio e' l'elemento eroe: numero piu' grande, cifre tabulari, grafico sotto. Palette quasi monocroma bianco/nero + verde/rosso. Pochissimi comandi per schermata. Lezione: una cifra grande e vera in testa, il resto la sostiene.

### Linear
- Fonti: https://linear.app/now/how-we-redesigned-the-linear-ui ; https://linear.app/now/behind-the-latest-design-refresh
- Screenshot: `screens/linear_redesign-1.png` (non ispezionato in dettaglio).
- Sidebar resa piu' scura/tenue perche' l'area di lavoro prevalga; piu' gerarchia e densita' nella navigazione; allineamento maniacale di icone/etichette; tema generato da 3 variabili (base, accento, contrasto) in spazio LCH; contrasto del testo aumentato in dark; command palette con Cmd+K o "/".

### Vercel dashboard
- Fonti: https://vercel.com/changelog/dashboard-navigation-redesign-rollout ; https://vercel.com/changelog/new-dashboard-navigation-available
- Screenshot: `screens/vercel_dashboard-dark.png`, `vercel_dashboard-light.png` (VISTO dark: in alto selettore team con badge "Pro"; campo "Find..." con scorciatoia; voci con icone lineari e frecce per sottomenu; voce attiva con riquadro grigio scuro; tab orizzontali nel contenuto).
- Sidebar ridimensionabile e nascondibile al posto delle tab orizzontali; stessi link a livello team e progetto; "progetti come filtri" (stessa pagina, cambio ambito in un clic).

### Stripe Dashboard
- Fonti: https://docs.stripe.com/sandboxes/dashboard/manage ; https://www.chargeforms.com/blog/stripe-test-mode-guide ; https://mattstromawn.com/projects/stripe-dashboard/
- Interruttore Test/Live in alto a sinistra, sempre visibile; test = banner arancione persistente e fascia colorata, live = tema normale/blu. Dati test e live completamente separati; chiavi diverse. Home: 4-6 KPI con numero, freccia di trend e sparkline; tabelle con filtri a pillole. Sidebar ~256px comprimibile a 64px (da sintesi di terzi).

## 2. PATTERN CONCRETI da adottare

1. **Banner di modalita' PAPER persistente e colorato su tutta l'app** (striscia sottile in alto + accento che cambia): PAPER = oro/ambra (secondario del tema) con scritta "PROVA - nessun soldo vero"; LIVE = etichetta "SOLDI VERI" ben leggibile, mai solo un verde. Dove: shell/testata globale, identico in ogni pagina e finestra figlia. Fonte: Stripe (banner arancione test), Cymatic (training mode), IBKR (conto paper separato).
2. **Dati paper e live mai nello stesso numero**: due contatori affiancati e filtro esplicito, nessuna somma. Dove: testata, Control Room, storici P&L. Fonte: Stripe (dati separati per modalita'), regola del repo.
3. **Testata con una cifra eroe vera**: P&L reale del conto del giorno (bot + manuale) in grande, cifre tabulari; sotto saldo, esposizione, posizioni aperte; ogni cifra con la fonte in tooltip. Dove: header Control Room e Home. Fonte: Robinhood/Trade Republic, IBKR (riquadro P&L + margine).
4. **Blocco "Rischio" sempre in vista** (esposizione totale, perdita massima aperta, numero posizioni) accanto al P&L. Dove: testata. Fonte: barra "Global settings" di Bet Angel, riquadro Margin di IBKR.
5. **Colore semantico coerente con doppio segnale**: P&L positivo verde, negativo rosso, SEMPRE con segno +/- e freccia; back azzurro / lay rosa SOLO dentro ladder e ordini (mai per profit/loss); oro riservato a PAPER/avvisi/marca. Dove: token di colore di tutta l'app. Fonte: Bloomberg (accessibilita' daltonismo), Betfair/Geeks Toy (back/lay), IBKR.
6. **Celle di tabella con riempimento semantico (heatmap) per P&L e posizione** con intensita' proporzionale. Dove: tabella posizioni per bot in Control Room. Fonte: IBKR Mosaic (screenshot).
7. **Sidebar comprimibile a icone con gruppi** (Operativita': Control Room, Bot; Analisi: Storici, Report; Sistema), voce attiva come riquadro tenue, sidebar piu' scura dell'area di lavoro. Dove: navigazione principale. Fonte: Vercel, Linear, Stripe.
8. **Command palette (Ctrl+K)** per saltare a bot, mercato, pagina e lanciare azioni sicure (mai quelle pericolose senza conferma). Dove: globale. Fonte: Linear, Vercel ("Find..." con tasto rapido).
9. **Workspace a pannelli con tab di layout in basso** ("Sorveglianza", "Ladder", "Analisi") e collegamento a colori fra pannelli (cambio bot/mercato in uno aggiorna i collegati). Dove: Control Room + ladder. Fonte: IBKR Mosaic.
10. **Lista di sorveglianza a destra con sezioni e vista lista/tabella** (posizioni aperte raggruppate per bot, PAPER/LIVE nel gruppo). Dove: colonna destra della Control Room. Fonte: TradingView.
11. **Ladder: prezzo al centro, back azzurro a sinistra, lay rosa a destra, ordini propri colorati come il lato con X di cancellazione per riga, coda di posizione, P&L per runner; pannelli accordion comprimibili**. Dove: ladder/griglia. Fonte: Bet Angel, Geeks Toy (screenshot).
12. **Comandi pericolosi a due livelli**: uscita/stop per singola posizione vicino alla riga (rosso, conferma con importo e modalita' per il live), "ferma tutto" in zona fissa lontana dai clic frequenti; paper senza attrito. Dove: Control Room, ladder. Fonte: Bet Angel (stop in barra dedicata), IBKR (Transmit/Cancel distinti e colorati).
13. **KPI a schede con trend e sparkline in Home/Report, tabelle con filtri a pillole** (periodo, bot, PAPER/LIVE, calcio/tennis). Dove: Storici e Report. Fonte: Stripe.

## 3. ANTI-PATTERN da evitare

1. **Modalita' indicata solo da una piccola etichetta o interruttore ambiguo** (Geeks Toy/Bet Angel non distinguono forte paper e reale): con bot veri e di prova un errore costa soldi. Serve il banner persistente (pattern 1).
2. **Sommare o mediare paper e live, o usare lo stesso verde/rosso per entrambi senza etichetta**: cifre false; contraddice il P&L reale del conto.
3. **Colore come unico segnale** (solo verde/rosso, o back/lay riusati per profit/loss): daltonismo e confusione con le convenzioni Betfair; Bloomberg ha dovuto riprogettare per questo.
4. **Finestre modali che coprono la posizione** (impostazioni sovrapposte alla ladder in Bet Angel) e estetica da anni 2000: trasmette poca affidabilita' e nasconde P&L e stop. Impostazioni in pannello laterale, mai sopra le posizioni.
5. **One-click senza conferma esteso alle chiusure totali**: giusto per la ladder dello scalper, pericoloso per "chiudi tutto"/"ferma bot". Gli stop globali non vanno accanto a controlli ad alta frequenza.
6. **Densita' Bloomberg dappertutto** (tutto fitto, ambra su nero, nessuna gerarchia): densita' solo dove serve (ladder, tabelle); altrove aria e cifra eroe come Robinhood, cosi' un utente non tecnico capisce in 3 secondi come va.

## 4. Limiti (cosa non ho potuto fare)
- Nessun accesso diretto a: Fairbot, BetTrader (solo testo), Cymatic Trader, Bf Bot Manager, Betfair Exchange web, Smarkets, Betdaq, Trade Republic, Robinhood, TradingView, Stripe, Bloomberg (403): schede da articoli di terzi, senza screenshot; Stripe e Bloomberg da sintesi di ricerca.
- Screenshot scaricati: 11 (Bet Angel x5, Geeks Toy, IBKR x2, Linear, Vercel x2); ispezionati visivamente solo Bet Angel impostazioni, Geeks Toy, IBKR Mosaic, Vercel dark. Le immagini Bet Angel/Geeks Toy sono del 2014 (UI attuale puo' differire).
- Non ho provato dal vivo la modalita' paper/training di Bet Angel e Cymatic.

## 5. Come i pattern sono entrati nel prototipo (aggiunta del delegato che ha costruito l'artefatto)

| Pattern | Applicato | Dove / perché no |
|---|---|---|
| 1 banner modalità persistente | sì, con i colori dell'app | testata globale «Ordini: n LIVE · m PROVA» + `ModeBanner` in ogni bot. PAPER resta **verde** e LIVE **rosso** come oggi in `ModeBanner`/`ModeToggle` (non oro: l'oro è già obiettivo/Safe/LTP) |
| 2 paper e live mai sommati | sì | corsie LIVE/PROVA, «altra modalità non sommata», selettore esclusivo negli storici, MTM e rischio a due righe in Market watch |
| 3 cifra eroe con fonte | sì | Obiettivo e Saldo in Control Room, Giornata operativa nei bot; ogni cifra porta il marchio CONTO / BOT / PROVA / STIMA |
| 4 rischio sempre in vista | sì | testata globale: saldo CONTO + esposizione, con occhio per nascondere |
| 5 colore + segno | sì | segno U+2212 e `+` sempre, back azzurro / lay rosa solo su quote e ordini |
| 6 heatmap | sì | calendari P&L, matrice X-Hedge, Report personale |
| 7 sidebar a gruppi comprimibile | sì | gruppi Calcio / Tennis / Trading / Analisi / Account, filtro sport, stato dei bot nelle voci |
| 8 command palette | **no** | sarebbe una funzione nuova: l'utente ha chiesto nessuna funzionalità nuova |
| 9 workspace a pannelli collegati | **no** | nuova funzione; il Multi-ladder esistente resta com'è |
| 10 watchlist a destra | parziale | le colonne «Uscite» e «Opportunità» della Control Room restano dove sono oggi (vincolo: Control Room invariata) |
| 11 ladder Bet Angel / Geeks Toy | sì, con il layout dell'app | resta il «layout v2» di produzione (LAY a sinistra del prezzo, BACK a destra), non quello della ricerca |
| 12 comandi pericolosi a due livelli | sì, come oggi | conferme a due tempi nello stesso punto; «Ferma tutti» e «tira il freno» senza conferma (freno d'emergenza, scelta già in produzione) |
| 13 KPI e filtri a pillole | sì | storici, Analytics, Report |
