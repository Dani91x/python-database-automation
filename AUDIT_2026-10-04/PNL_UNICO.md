# P&L UNICO DI GIORNATA (04/10/2026) - referto del delegato

Segnalazione dell'utente: «la scheda Calcio dice LIVE -10,75 EUR CONTO BETFAIR (5 ordini
regolati oggi), Posizioni chiuse dice Oggi 4 chiuse -5,68 (2 V 2 P). Non abbiamo mai perso 10
euro: uniforma i dati una volta per tutte.»

Ramo: `worktree-agent-aef19746f90dc5a52`. Commit: backend `c22bd96`, frontend + referto nel
commit successivo (vedi `git log`).

## 1. Causa (A) con la prova

Dati letti dal DB in sola lettura (04/10, `betfair_live_account.pnl_reale_oggi` letto_at
13:08:03 UTC; `mike_trades` 5150-5160; `betfair_live_orders` 49268-49270):

| bet_id | chi | partita / mercato | profit | dove lo metteva il conto |
|---|---|---|---|---|
| 445568321596 | Mike under_entry (5152) | Farense U3.5 1.263086158 | -5,00 | mike |
| 445572454155 | Mike over_cover (5159) | Farense U4.5 1.263086155 | -0,82 | mike |
| 445568325409 | Mike under_entry (5154) | Miyazaki U3.5 1.263199718 | +2,20 | mike |
| 445568328282 | Mike under_green (5155) | Miyazaki U3.5 | -2,13 | mike |
| 445572059076 | Mike under_entry (5156) | Vasalunds U3.5 1.263105235 | -5,00 | mike |
| **445577040174** | **UTENTE dal sito**, riga Mike 5160 `role='utente'`, `closes_trade_id` 5156 | Vasalunds U3.5 (stesso mercato della 5156) | +5,07 | **manuale_sito** |
| 445569572640 | UTENTE dal sito (`betfair_live_orders.source='account'`, `client_order_ref='ext445569572640'`) | 1.263096939 sel. 1221386 | +0,55 lordo, commissione 0,02 | manuale_sito |

- L'ordine 445577040174 NON e' di Mike: lay 5,07 @1,51 identico al green di Mike (riga 5157,
  bet 445572063578, `status='error'`, `meta.reason='arresto'`, `esito_ordine='ritirato_da_noi'`:
  ritirato all'arresto). Lo ha rimesso l'utente dal sito: nessun `customerOrderRef`
  (`mike_trades.meta.customer_order_ref = null`), nessun `customerStrategyRef`
  (`pnl_reale_oggi.sospetti_sito = 0`, `reconcile_worker.py` `componi_regolati`: un ordine con
  un ref ma senza riga sarebbe contato in `sospetti_sito`), nessuna riga dello specchio
  `betfair_live_orders`.
- Mike lo conta nella SUA posizione per regola del 30/09 (`Betfair/mike/regolato_conto.py`
  righe 21-39: «gli ordini dell'utente entrano nel conto della partita», riga `role='utente'`
  con `closes_trade_id` = apertura di Mike): da qui le Posizioni chiuse -5,68.
- Il runner lo escludeva da Mike per la regola del 30/09 in `reconcile_worker._proprietari`
  (`if tabella == "mike_trades" and role == "utente": continue` -> nessun proprietario ->
  `manuale_sito`, `componi_regolati` ramo `prop is None`). Quindi `per_fonte.mike` = i soli 5
  ordini piazzati da Mike = -10,75.
- La tessera dello sport (`frontend/src/lib/composizioneConto.ts::perSportDalConto`, prima
  righe 135-148) sommava SOLO le voci dei bot (`mike+omega+safe_calcio+scalper`): gli ordini a
  mano (+5,60 netti) erano fuori da ogni tessera. Risultato: «LIVE -10,75 CONTO BETFAIR» mentre
  il conto era -5,15 netto.
- Nessun bug di attribuzione per bet_id: e' un problema di DUE significati (chi ha piazzato vs di
  quale posizione e') e di una tessera che mostrava solo una parte del conto con l'etichetta
  «conto».

La quarta posizione delle Posizioni chiuse: la copertura Over di Farense (riga 5159,
`over_cover`, lay Under 4.5 6,32 @1,13, -0,82) e' un'apertura a se' (`closes_trade_id` null).
Le 4: Farense under -5,00 (P), Farense over_cover -0,82 (P), Miyazaki +0,07 (V), Vasalunds
-5,00+5,07 = +0,07 (V). Totale -5,68, 2 V 2 P. Verificato dal test
`pnlUnicoConto.test.ts` con la funzione vera `posizioniChiuse`.

## 2. Regola scelta (minima)

`per_fonte` (CHI ha piazzato l'ordine) resta IDENTICA: il test del 30/09
`test_il_runner_non_attribuisce_a_mike_l_ordine_dell_utente` resta verde, `manual_pnl_*` invariati.
Il runner scrive in piu' (chiavi ADDITIVE di `pnl_reale_oggi`, nessuna migrazione: e' JSONB):

- `per_posizione`: le stesse voci, ma un ordine A MANO (sito o app) che sta nella posizione di
  Mike conta in Mike. «Sta nella posizione di Mike» = (a) il suo bet_id ha in `mike_trades` una
  riga `role='utente'` (letta dalla STESSA query di `_proprietari`, colonna `role` gia' chiesta),
  oppure (b) e' sullo STESSO mercato di un ordine di Mike regolato oggi (la regola di
  `mike.regolato_conto`). (b) serve perche' il giro dei regolati gira PRIMA che Mike scriva la
  riga utente (il 04/10: lettura 13:08, riga 5160 scritta alle 13:19) e il proprietario di un
  bet_id si risolve una volta per processo.
- SOLO Mike adotta: Omega e Safe non scrivono righe dell'utente nelle loro posizioni, quindi un
  ordine a mano sul loro mercato resta «a mano» (altrimenti composizione e Posizioni chiuse di
  Omega direbbero cifre diverse).
- `chiusure_a_mano`: per voce, netto/lordo/ordini/bet_id degli ordini adottati.
- `per_sport`: per `calcio`/`tennis`/`altro` (dall'`eventTypeId` dell'ordine, 1/2; senza, dalla
  voce del bot; altrimenti `altro`): netto, lordo, commissione, ordini, `bot`, `a_mano`,
  `chiusure_a_mano`. `bot + a_mano = netto` per costruzione.

Somma di `per_posizione` = somma di `per_fonte` = `netto`: si sposta di voce, non si crea ne'
si toglie un centesimo (assert nel test).

Commissioni: UNA regola, quella di sempre: netto = profit - quota della commissione del
MERCATO (`commissioni_per_ordine`). Ogni cifra a schermo e' NETTA e lo dice («netto di
commissione», «commissione 0,02 EUR gia' tolta»); l'unica vista lorda (pagina /live-pnl) ora lo
dichiara.

## 3. Le viste: prima / dopo con i numeri del 04/10

Conto: lordo -5,13, commissione 0,02, **netto -5,15** = Mike (posizioni) -5,68 + a mano +0,53
(lordo +0,55 - commissione 0,02). Mike -5,68 = i 5 ordini di Mike -10,75 + la tua chiusura +5,07.

| vista | fonte | formula | prima (04/10) | dopo | torna col conto? |
|---|---|---|---|---|---|
| Tessera Calcio, corsia LIVE (`SplitSport`) | `pnl_reale_oggi.per_sport.calcio` | bot (per posizione) + a mano, netto | -10,75 «5 ordini» | **-5,15** «7 ordini regolati oggi» + «bot -5,68 (di cui tue chiusure a mano +5,07) · a mano +0,53 · commissione 0,02 EUR gia' tolta» | prima NO, dopo SI' |
| Tessera Tennis, corsia LIVE | `per_sport.tennis` | idem | 0,00 | 0,00 | SI' |
| Barra di giornata / realizzato (`DayBar` in `ObiettivoHero`, `soldiGiornata.realizzato`) | righe dei bot + voci sintetiche dal conto | somma voci | -5,15 | -5,15 | SI' (gia' prima) |
| Composizione - Mike (`composizioneDalConto`) | `per_fonte` -> ora `per_posizione` | conto + stimato | -10,75 | **-5,68** + nota «Mike comprende le tue chiusure a mano sulle sue posizioni: +5,07 (1 ordine)» | SI' |
| Composizione - Manuale · sito Betfair | `per_fonte.manuale_sito` -> `per_posizione` | conto | +5,60 | **+0,53** | SI' |
| Composizione - totale | somma voci | | -5,15 | -5,15 | SI' |
| Posizioni chiuse, testa (Oggi) | righe dei bot (giorno della PARTITA) | netto delle posizioni | -5,68 (4, 2V 2P) | -5,68 (4, 2V 2P) invariato | = parte «bot» del conto |
| Posizioni chiuse, riga nuova `cr-chiuse-conto` | `per_sport` (contoPerVista) | bot + a mano | assente | «Conto Betfair oggi -5,15 = posizioni dei bot -5,68 + a mano fuori dai bot +0,53 (1 ordine) · netto di commissione (0,02 EUR tolta)» | SI' |
| Posizioni chiuse, controprova con la barra (VOCI_BARRA) | barra mike vs posizioni regolate oggi | | barra -10,75 vs qui -5,68: «differenza +5,07» (arancione) | -5,68 vs -5,68: «coincide» | SI' |
| Plancia per bot, Mike LIVE oggi (`PannelloBot` via `useControlRoom.liveDi`) | `per_fonte.mike` -> `per_posizione.mike` | conto | -10,75 | **-5,68**, nota «comprende le tue chiusure a mano sulle sue posizioni (+5,07, 1 ordine)» | SI' |
| Plancia Omega / Safe tennis | `per_posizione` | conto | 0 | 0 | SI' |
| Plancia Safe calcio per strategia | righe del bot | (dichiarato) | invariata | invariata | il conto non separa per strategia (gia' detto a schermo) |
| Pagina /live-pnl «P&L realizzato» | `get_live_settled` (profit per MERCATO) | somma dei profit LORDI di tutto il conto | -5,13 senza dirlo | -5,13 + «lordo, prima della commissione · tutto il conto (bot + a mano)» | torna col LORDO del conto, ora dichiarato |
| Pagina /live-pnl «Totale giornata» | `betfair_live_risk_state.total` (worker dello stop) | realizzato + MTM del runner calcio | non verificato | invariato | NON verificato (vedi §7) |
| Pagina Mike, DayBar | `get_mike_state.realized_today` (servizio Mike) | P&L della partita (Mike + utente) | non letto oggi | invariato | atteso -5,68 = Mike per posizione; NON verificato |
| Pagine Omega / Safe, DayBar | servizi dei bot | P&L del bot | 0 | invariato | atteso 0; NON verificato a schermo |
| Storico calcio/tennis (riga di oggi) | RPC storiche per bot (giorno della partita) | per bot | invariato | invariato | solo bot: gli ordini a mano fuori dai bot non hanno storico (gia' cosi') |

Runner di PRIMA (finche' non si riavvia il runner): niente `per_posizione`/`per_sport` ->
composizione, plancia e barra restano come prima (Mike -10,75, Manuale sito +5,60, totale
-5,15); la tessera mostra ancora i soli bot (-10,75) ma ora DICE sotto: «ordini a mano su tutto il
conto +5,60: non compresi qui (non separati per sport)»; la riga del conto nelle Posizioni chiuse
non compare (non si inventa la scomposizione).

## 4. File toccati

Backend (commit `c22bd96`):
- `Betfair/stream/reconcile_worker.py`: `_ADOTTATO_BET`, `_proprietari` (ricorda la riga
  utente invece di scartarla e basta), `componi_regolati(..., adottati=None)` con
  `per_posizione`/`chiusure_a_mano`/`per_sport`, `_sport_di`, firma di scrittura con le chiusure.
- `Betfair/stream/tests/test_reconcile_worker.py`: fixture `env` azzera anche `_ADOTTATO_BET`
  (aggiunta, nessun test indebolito).
- NUOVO `Betfair/stream/tests/test_pnl_unico_conto_2026_10_04.py` (9 test).

Frontend:
- `frontend/src/lib/composizioneObiettivo.ts`: tipi `ParteConto`/`SportConto`; `leggiPnlRealeOggi`
  usa `per_posizione` se c'e' (`attribuzione`), legge `chiusure_a_mano`, `per_sport`, `lordo`,
  `commissione`; `betIdChiusureAMano`.
- `frontend/src/lib/composizioneConto.ts`: `perSportDalConto` (conto dello sport + scomposizione;
  ripiego dichiarato), `contoPerVista`, `righeMikeDelConto`, `chiusureAMano` nella composizione.
- `frontend/src/components/controlroom/useControlRoom.ts`: righe di Mike con
  `righeMikeDelConto`, nota della plancia di Mike, `soldiGiornata.contoVista`.
- `frontend/src/components/controlroom/SplitSport.tsx`: `ScomposizioneConto`, dettaglio del marchio.
- `frontend/src/components/controlroom/PosizioniChiuse.tsx`: prop `contoOggi`, riga `cr-chiuse-conto`.
- `frontend/src/components/controlroom/ObiettivoHero.tsx`: nota delle chiusure a mano.
- `frontend/src/pages/ControlRoom.tsx`: passa `contoOggi`.
- `frontend/src/pages/LivePnl.tsx`: «lordo, prima della commissione · tutto il conto».
- NUOVI `frontend/src/lib/pnlUnicoConto.test.ts` (6), `frontend/src/components/controlroom/pnlUnicoConto.viste.test.tsx` (3).
- Fotografie: vedi §5.

Non toccati (perimetro): `PannelloBot.tsx`, `righeBot.ts`, `interruttori.ts`,
`Betfair/safe_strategy/**`, `Betfair/stream/tennis_live/**`, `motore_ordini.py`, `desktop/main.js`.

## 5. Test

Comandi (dal worktree):
- `<principale>\.venv\Scripts\python.exe -m pytest Betfair/stream/tests Betfair/mike/tests/test_mike_pnl_reale_del_conto_2026_09_30.py -q -p no:cacheprovider`
  -> **3471 passed, 25 skipped, 0 failed** (394 s). Nuovo file: 9/9.
- `frontend`: `npm ci` nel worktree; `npx tsc -p tsconfig.app.json --noEmit` = **0 errori**;
  `npx vitest run src/lib src/components/controlroom src/components/trading src/fotografia src/pages`
  -> **251 file, 4192 passed, 1 skipped, 0 failed**.

Test esistenti modificati (dichiarati, nessuno indebolito):
- `frontend/src/lib/composizioneConto.test.ts` (2 asserzioni W_G su `perSportDalConto`): stesse
  cifre di prima, piu' il campo nuovo `aManoNonSeparato` (5 e null) che il ripiego ora dichiara.
- `Betfair/stream/tests/test_reconcile_worker.py`: fixture `env` azzera anche `_ADOTTATO_BET`.
- Fotografie `live-pnl.off.json`/`live-pnl.v2.json` rigenerate (solo `-t live-pnl`): diff = una
  riga di testo «lordo, prima della commissione · tutto il conto (bot + a mano)» e il testid
  `livepnl-realizzato-lordo`. Nessun'altra fotografia cambiata (control-room: il finto
  dell'anteprima non porta `per_sport`, testi invariati).

Falsificazione (mutazione nel codice -> test rosso; ripristino verificato, `MUTAZIONE` = 0):

| mutazione | file | esito |
|---|---|---|
| M1 nessuna adozione (`posizione = fonte`) | reconcile_worker.py | 3 rossi |
| M2 senza regola del mercato | reconcile_worker.py | 1 rosso (riga utente scritta dopo il giro) |
| M3 riga utente non ricordata in `_proprietari` | reconcile_worker.py | 1 rosso |
| M4 adotta qualunque bot sullo stesso mercato | reconcile_worker.py | 1 rosso (Omega) |
| M5 tabelle dei bot non lette | reconcile_worker.py | 8 rossi (contratto «mai in manuale_sito») |
| M6 ordini a mano sempre calcio | reconcile_worker.py | 1 rosso |
| F1 tessera = solo voci dei bot | composizioneConto.ts | 3 rossi |
| F2 righe utente di Mike sempre fuori | composizioneConto.ts | 2 rossi |
| F3 voci per chi ha piazzato (`per_fonte`) | composizioneObiettivo.ts | 1 rosso |
| F4 Posizioni chiuse senza riga del conto | PosizioniChiuse.tsx | 1 rosso |
| F5 ripiego: a mano non separati taciuti | SplitSport.tsx | 1 rosso |
| F6 chiusure a mano non dichiarate | SplitSport.tsx | 1 rosso |

## 6. Chiamate DB / Betfair prima / dopo

- REST Betfair: invariate (una lettura per MERCATO, una per ORDINE solo a firma cambiata).
  Test `test_nessuna_lettura_in_piu_per_l_attribuzione_di_posizione`: 2 letture REST, 5 letture
  DB (una per tabella) come prima.
- DB: la colonna `role` di `mike_trades` era gia' nella SELECT di `_proprietari`; nessuna
  lettura nuova. Scrittura di `pnl_reale_oggi`: stessa, write-on-change (la firma ora include i
  bet_id delle chiusure a mano: si riscrive solo se cambiano).
- Frontend: nessuna lettura nuova (stesso `pnl_reale_oggi` gia' letto da DB/canale).

## 7. Cosa NON ho fatto / non ho potuto verificare

- Non ho visto l'app dal vivo: i testi sono verificati nei test di componente.
- Quando l'utente ha piazzato il 445577040174: l'ordine non e' in `betfair_live_orders` e nel DB
  non c'e' l'istante di piazzamento; la causa «rimesso a mano dal sito dopo il ritiro all'arresto»
  e' dedotta da: stesso prezzo/importo del green ritirato, nessun ref, riga utente di Mike.
- Lo sport dell'ordine 445569572640 (mercato 1.263096939): nel DB non c'e' il catalogo; nei
  test e' calcio (`eventTypeId` 1, selezione 1221386 = linea gol). Dal vivo lo decide
  l'`eventTypeId` che Betfair manda.
- Pagina Mike (`realized_today` del servizio), pagine Omega/Safe, /live-pnl «Totale giornata»
  (`risk_state.total` del worker dello stop): formule dei servizi, non toccate e non verificate.
- Ordini di sport diversi da calcio/tennis (`per_sport.altro`): nel conto e nella barra, non in
  una tessera (non c'e' una tessera «altro»).
- Bordo noto della regola (b): un ordine a mano su un mercato di Mike dove Mike NON ha ordini
  regolati oggi e la cui riga utente Mike scrive DOPO il giro conta «a mano» fino al riavvio del
  runner (o al giorno dopo).

## 8. Per attivarlo

1. Riavvio del RUNNER calcio (scrive le chiavi nuove; il giro riparte da zero e riscrive
   `pnl_reale_oggi` al primo giro). Nessuna migrazione.
2. `npm run build` del frontend e riavvio dell'app (lo fa l'utente; mai con posizioni live aperte).
3. Senza riavvio del runner la UI funziona col ripiego dichiarato (§3 in fondo).

Controllo dal vivo: tessera Calcio LIVE = `pnl_reale_oggi.netto` (se solo calcio) con la riga
«bot · a mano»; composizione Mike = Posizioni chiuse di Mike (controprova verde «coincide»).

## 9. Domanda per l'utente (cambia il significato di una cifra)

La voce «Mike» (composizione, plancia, tessera «bot») ora e' la POSIZIONE di Mike: comprende le
chiusure che metti tu a mano sulle sue posizioni (oggi +5,07), dichiarate a schermo. Alternative:
(A, fatta) Mike = posizione (come le Posizioni chiuse e la pagina Mike), «a mano» = solo gli ordini
fuori dalle posizioni dei bot; (B) Mike = solo gli ordini piazzati da Mike (-10,75) e «a mano» = tutti
gli ordini tuoi (+5,60): torna col conto ma le Posizioni chiuse di Mike direbbero un'altra cifra.
