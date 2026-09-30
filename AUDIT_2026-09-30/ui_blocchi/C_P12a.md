# C_P12a - Cash out della PARTITA: matematica e riquadro (blocco B12, parte a)

Delegato C_CASHOUT, 30/09/2026. Worktree:
`C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.claude\worktrees\agent-a4f88b994afb4b99a`
Base `1d058a7` (ff fatto PRIMA della regola nuova; da ora nessun merge). Patch CUMULATIVA di `frontend/`:
`C_P12a.patch` (contiene anche P11). Niente commit. Il riquadro NON e' montato in `SchedaPartita.tsx` (P12b).

## File toccati SOLO da P12a

| File | Cosa |
|---|---|
| `frontend/src/lib/cashOutPartita.ts` (NUOVO) | `cashOutPartita(gambe, {prezzo, nowMs, esitoDeciso?})` pura -> `{live, paper}`; `gambeDaOperazioni(ops, {dueEsiti?})` dalle righe della scheda; `r2` |
| `frontend/src/lib/cashOutPartita.test.ts` (NUOVO) | 30 test tabellari |
| `frontend/src/components/controlroom/useCashOutPartita.ts` (NUOVO) | hook: righe -> gambe -> `usePrezziAlMs` (esistente, 1 sottoscrizione per mercato) -> cifra |
| `frontend/src/components/controlroom/CashOutGlobale.tsx` (NUOVO) | riquadro, solo presentazione, `MarchioSoldi` pagina/bot/prova |
| `frontend/src/components/controlroom/CashOutGlobale.test.tsx` (NUOVO) | 5 test del riquadro + 3 del montaggio isolato hook+riquadro |
| `frontend/src/components/controlroom/CashOutPartita.tsx` | SOLO testi (etichetta, title, conferma, frase armata, intestazione) |
| `frontend/src/lib/chiusuraUtente.ts` | SOLO testi: motivo spento, messaggio `EventoMancante` |
| `frontend/src/components/controlroom/CashOutPartita.test.tsx` | +2 test (testi esatti) |
| `frontend/src/lib/chiusuraUtente.test.ts` | +1 test (testi esatti) |
| `frontend/src/pages/ControlRoom.test.tsx:1346` | asserzione rafforzata: `/nessuna posizione viva/` -> `/nessuna posizione viva di Safe su questa partita/` |
| `frontend/src/components/controlroom/useControlRoom.ts` | (via libera) 2 righe: `commission` passata a `chiusuraViva` in `operazioni` (~:3088, cast strutturale: Omega/Safe/Mike hanno la colonna ALIQUOTA, `omega_bot.sql:50`, `safe_strategy_bot.sql:63`, `mike_bot.sql:99`) e in `bloccabileOra` delle proposte Safe (~:2811, `SafeTrade.commission`). Tennis NON toccato |
| `frontend/src/components/controlroom/useChiusuraAlMs.parita.test.tsx` | +1 test: colonna `commission = 0,02` senza meta -> scheda = posizioni = ms = 0,77 |

## PRIMA -> DOPO a schermo

| Dove | PRIMA | DOPO |
|---|---|---|
| pulsante (`cr-cashout-partita-avvia`) | «Cash out globale della partita» | «Cash out Safe» |
| title del pulsante | «chiude TUTTE le posizioni del bot su questa partita e gli dice di non fare altro» | «chiude TUTTE le posizioni di SAFE su questa partita (non quelle degli altri bot) e gli dice di non fare altro» |
| motivo spento (`-bloccato`) | «nessuna posizione viva del bot su questa partita» | «nessuna posizione viva di Safe su questa partita» |
| conferma (`-conferma`) | «Confermo: chiudi tutta la partita» | «Confermo: chiudi le posizioni di Safe» |
| armato live (`-armato`) | «Sono soldi veri: conferma per chiudere tutta la partita.» | «Sono soldi veri: conferma per chiudere le posizioni di Safe su questa partita.» |
| riquadro nuovo (P12b lo monta) | - | «CASH OUT DELLA PARTITA (SE CHIUDO TUTTO ADESSO) −0,82 € netto commissione [STIMA · 0 s fa]» / «Mike LIVE punta Under 3.5 Goals 5,00 € @ 2,40 · chiudo banca 4,69 € @ 2,56 · −0,32 €» / «Mike LIVE banca Under 4.5 Goals 6,32 € @ 1,76 · chiudo punta 6,82 € @ 1,63 · −0,50 €» / «il bot Mike calcola: −0,84 € [BOT · 1 s fa] differenza 0,02 €: prezzi letti in istanti diversi (pagina 0,3 s fa, bot 1,2 s fa)»; senza un prezzo: «NON CALCOLABILE: manca il prezzo di Under 4.5 Goals (punta)» e nessuna cifra; riga «Prova (simulato, mai sommato ai soldi veri)» separata [PROVA] |

Comportamento del pulsante e tutti i `data-testid` invariati (`cr-cashout-partita*`, `cr-riprendi-partita`, `cr-badge-chiusa-da-te`). Nuovi testid: `cr-cashout-globale`, `-live`, `-live-netto`, `-live-marchio`, `-live-non-calcolabile`, `-live-gamba`, `-live-gamba-chiudo`, `-live-gamba-pnl`, `-live-gamba-liquidita`, `-live-caso-migliore`, `-live-commissione`, `-live-avviso`, `-live-bot-<bot>`, `-live-bot-<bot>-netto`, `-live-bot-<bot>-marchio`, `-live-bot-<bot>-differenza`, `-live-vuoto`, `-prova`, `-prova-netto`, `-prova-marchio`.

## Formula (porting, nessuna terza formula)

1. Solo l'ABBINATO (`statoOrdine(...).abbinato`, prezzo `prezzoMedio`); residuo sul book escluso.
2. Esposizione per (mercato, selezione) di TUTTI i bot della stessa modalita': `engine.exposure` `Betfair/mike/engine.py:680-715`; su mercato a DUE esiti con gambe su entrambe le selezioni l'altra pesa rovesciata e la chiave e' la selezione lunga (`engine._chiave_ou45` :795-798).
3. Green-up pieno: `greenup.compute_greenup` `Betfair/stream/trading/greenup.py:196-247`, importo `round(|W−L|/p, 2)` (`_hedge_size` :109-111), bloccato = min dei due esiti (engine :972); stesso `hedgeSide`/`partialLockedPnl` di `CashOutButton.tsx:34-74`.
4. Commissione per MERCATO sul netto positivo (engine :978-992), ripartita pro-rata sulle selezioni in utile, residuo sulla piu' pesante (engine :993-1002). Aliquote diverse nello stesso mercato: la piu' alta, dichiarata.
5. Fail-closed (engine :966-968): un prezzo mancante, un mercato SOSPESO/CHIUSO, un abbinato o prezzo medio o mercato/selezione non dichiarati, una modalita' ignota (solo nel live), un ordine in riconciliazione -> `netto: null`, `mancanti` con la frase.
6. Arrotondamenti come Betfair: profitto di OGNI scommessa (anche la chiusura) al centesimo; commissione `round(aliquota × netto mercato, 2)`.

### Parita' con `engine.cashout_value` (commissione 0,05)

| Caso Python | Ingressi | engine (calcolato a mano dal codice) | TS |
|---|---|---|---|
| `test_mike_engine.py:167-180` | back 20 @ 1,50; lay 1,40 | size 21,43 -> 1,43/1,43; gross 1,43; net 1,36; senza libro `complete=False` | 1,43 / 1,36; senza libro `netto null` |
| `test_mike_engine_cert_2026_09_12.py:178-187` | Under 3,5 back 20 @ 1,50 (L 1,31) + Over 4,5 back 4 @ 8 (L 12,5) | 22,90 -> 2,90; 2,56 -> −1,44; net round(2,755 − 1,44) = 1,31 | 1,31 |
| `test_mike_engine_cert_2026_09_12.py:164-174` | Over 4,5 back 4 @ 8 + Under 4,5 back 10 @ 1,40, stesso mercato (L Over 9,4) | chiave OVER (18, 0); banca 1,91 @ 9,4 -> 1,96/1,91; net 1,81 | 1,81, una sola chiave |
| `test_mike_engine_cert_2026_09_12.py:303-316` | come sopra 178 ma 4 gol: Under 3,5 decisa; Over L 2,02 | −20 + 15,84 -> 11,84; net −8,752 -> −8,75, `complete=True` | −8,75, completo |

Non ho eseguito il Python (brief: solo lettura): i valori engine sono ricavati riga per riga dal codice; i test Python citati li asseriscono a ±0,01/0,02.

### Differenze DICHIARATE rispetto all'engine (anche nel commento di testa del file)
- Selezione piatta: qui vale min(W, L) (Farul +0,05); l'engine la esclude (`open_selections` :803-815, per lui non c'e' niente da chiudere).
- Chiusura che arrotondata vale 0,00: qui min(W, L) + `residuoNonPiazzabile`; l'engine la rende incompleta.
- Copertura come BANCA d'apertura su una selezione sola (Follo, banca Under 4,5): qui si chiude PUNTANDO l'Under 4,5 (come il «chiudi ora» della riga, −0,50 atteso dal brief); Mike la chiude BANCANDO l'Over 4,5 (`engine._chiave_ou45` :788-792, test `test_mike_p5_compensazione_mercato_2026_09_29.py:127-135`). Stesso rischio tolto, altro libro: e' una delle cause probabili del −0,84 (Mike) contro −0,82 (pagina). Per rispecchiarlo servirebbe il libro dell'Over 4,5 e la regola dei ruoli di Mike: non l'ho portata (sarebbe una seconda regola per bot).

## Che cosa c'e' per ogni bot (dati per gamba che arrivano alla scheda, `OperazionePartita`)

| Bot | mercato/selezione | abbinato + prezzo medio | aliquota | chiusure (green) | esito |
|---|---|---|---|---|---|
| Mike | si' (`market_id`/`selection_id` dal 23/09; righe storiche no -> mancante) | si' (`size_matched`, `avg_price_matched`, `service.py:2217-2222`) | colonna `commission` (0,05) o `meta.commission` | in `chiusureOrdini` SENZA mercato/selezione -> **MANCA** | calcolabile se le chiusure non sono abbinate (Follo); Farul (green abbinato) oggi = NON CALCOLABILE |
| Omega | si' | si' (colonne o `meta`) | `meta.commission` | come Mike: **MANCA** mercato/selezione della chiusura | idem |
| Safe | si' | si' | colonna `commission` | come Mike | idem |
| 4 bot tennis | si' (`tennis_live_orders`, NOT NULL) | si' (`size_matched`, `average_price_matched`) | nessuna: 5 % di ripiego (la colonna `commission` e' un IMPORTO, non si usa) | nessuna catena | calcolabile; `selezione` = null (la riga non porta il nome): la frase dice «selezione <id>» |
| Scalper calcio | NO (la riga e' la SESSIONE, `lato null`, `marketId null`) | solo l'abbinato totale | - | - | **NON scomponibile** -> se abbinato, NON CALCOLABILE col motivo |
| Mike, cifra del servizio | `MikeEvent.live.cashout {net, complete, per, commission}` + `live.published_ts` | | | | da passare a `valoriBot` (P12b) |

### DATI MANCANTI (forma esatta richiesta)
1. **Mercato/selezione delle gambe di chiusura**: in `useControlRoom.agg` (~:3139) aggiungere a `OperazionePartita` il campo opzionale `chiusureGambe?: { id: number | null; marketId: string | null; selectionId: number | null }[]` (stesso ordine di `chiusureOrdini`), da `closes.map((c) => ({ id: c.id, marketId: c.market_id ?? null, selectionId: c.selection_id ?? null }))`. Fonte: le righe grezze gia' in memoria (colonne `market_id`/`selection_id` di `omega_trades`/`safe_strategy_trades`/`mike_trades`). `gambeDaOperazioni` lo legge gia' (tipo `OperazionePerCashOut.chiusureGambe`). Senza: ogni partita con una chiusura ABBINATA e' «NON CALCOLABILE: mercato/selezione non pubblicati: mike #5091/chiusura 1».
2. **Scalper**: `esposizioneSelezioni?: { marketId: string; selectionId: number; win: number; lose: number }[]` sulla riga della sessione (da `v.esp.selezioni`, `lib/scalperControlRoom.ts:459-461`). Oggi la sessione abbinata rende la cifra non calcolabile.
3. **Mike, mercato a due esiti e esito deciso**: `dueEsiti(marketId)` = mercati O/U (da `MikeEvent.markets` OU35/OU45 -> `market_id`); `esitoDeciso` = linea superata dai gol (`live.goals`, engine `selection_decided` :666-677). Si passano all'hook in P12b, se il coordinatore lo vuole; senza, un Under 3,5 gia' perso dopo il 4o gol (linea potata, prezzo assente) da' «NON CALCOLABILE» invece di −stake.

## Test

- Nuovi: `lib/cashOutPartita.test.ts` 30 (Follo −0,82 con scomposizione; pareggiata +0,05 una riga; piatta; 6 fail-closed; abbinato/parziale; LIVE/PROVA; modalita' ignota; commissione per mercato 1,04 vs 0,99 per gamba; aliquote diverse; liquidita'; eta' ignota; 4 parita' engine; 5 adattatore su `OperazionePartita` vera; `r2`). `CashOutGlobale.test.tsx` 8. `CashOutPartita.test.tsx` +2, `chiusuraUtente.test.ts` +1, `useChiusuraAlMs.parita.test.tsx` +1.
- Esistenti cambiati: `pages/ControlRoom.test.tsx:1346` (rafforzata, non indebolita). Nessun test tolto.

## Falsificazioni (`falsifica_c_p12a.sh`, uscita `falsifica_c_p12a.out`)

| Mutazione | Rossi |
|---|---|
| M1 somma per RIGA invece che per selezione | 3 (pareggiata, piatta, Farul adattatore) |
| M2 commissione per GAMBA | 3 (commissione per mercato) |
| M3 gamba senza prezzo contata 0 | 4 (fail-closed, parita' incompleta, riquadro NON CALCOLABILE) |
| M4 paper sommato al live | 2 (lib + riquadro) |
| M5 altra selezione non rovesciata | 1 (parita' cert:164) |
| M6 righe `error` mai abbinate dentro | 2 (Follo adattatore) |
| M7 testo di nuovo «del bot» | 3 (CashOutPartita, chiusuraUtente, ControlRoom) |
| M8 `operazioni` senza `commission` | 1 (parita' 0,02) |
| M9 liquidita' mai controllata | 2 |
| M10 esito deciso ignorato | 1 (parita' cert:303) |

Ripristino dalla copia fuori repo; `MUTAZIONE` rimaste 0 in tutti i file; `git diff --stat` identico (11 file, +388 −23 prima dei nuovi).

## Numeri

- `npx tsc -p tsconfig.app.json --noEmit` (include i test): 0 errori.
- Fine blocco: `npx vitest run src/components/controlroom src/lib/chiusuraAlMs.test.ts src/lib/cashOutPartita.test.ts src/lib/chiusuraUtente.test.ts src/pages/ControlRoom.test.tsx --maxWorkers=2`: **59 file, 928 test verdi**.

## COSA NON HO FATTO
- Montaggio in `SchedaPartita.tsx` (P12b, adesso). «perdita massima se non chiudo / vincita massima» del §5.C: non richiesto in P12a, non fatto.
- `pages/SafeStrategy.tsx:832` toast «Cash out globale della partita in coda»: fuori perimetro, testo non cambiato (la pagina e' di Safe, li' e' comunque vero per Safe).
- Nessun test per la riga `bloccabileOra` (b) delle proposte Safe (mutazione non provata: servirebbe una proposta Safe completa nei finti).
- Parita' con la regola di Mike «copertura banca -> banca Over 4,5»: non portata (vedi differenze).

## COSA NON HO POTUTO VERIFICARE
- L'app a schermo (non la vedo): verificati solo testi e testid nei test di montaggio.
- I valori engine non eseguiti in Python (solo letti).
- Se `size_matched`/`avg_price_matched` sono valorizzati su TUTTE le righe live di oggi (DB non letto): dove mancano, la cifra dice «importo abbinato non dichiarato» invece di un numero.

## Verifica del coordinatore UI (admin-07), 30/09 18:30
- Albero di verifica integrato (`1d058a7` + C_P12a + B1 + B2 + T_P3 + G_P8, fusione a tre vie senza conflitti): `npx tsc -p tsconfig.app.json --noEmit` = 0 errori; `npx vitest run src/components/controlroom src/components/trading src/pages/ControlRoom.test.tsx` + test di lib toccati = 87 file, 1379 test verdi.
- Sul master `96a2189` (worktree di integrazione) lo stack G_P2 → G_P2_test → B1 → B2 → T_P3 → C_P12a → G_P8 produce, su ogni file toccato, lo STESSO contenuto byte per byte dell albero verificato.
- ATTENZIONE: `C_P12a.patch` in QUESTA cartella e l INCREMENTALE ricavato da me sul master (P11 e gia su master): 12 file; si applica dopo T_P3. La cumulativa del delegato resta nel suo worktree.
- `lib/cashOutPartita.ts` letto per intero: raggruppa per (mercato, selezione), commissione per mercato sul netto positivo, fail-closed su prezzo mancante / mercato non aperto / abbinato o mercato non dichiarati / modalita ignota; LIVE e PROVA separati.
- Mutazioni MIE (oltre le 10 del delegato), ROSSE, ripristino da copia: lato di chiusura rovesciato (25 rossi); mercato SOSPESO trattato come aperto (1); commissione anche su un mercato in perdita (15).
- NON ANCORA A SCHERMO: il riquadro `CashOutGlobale` non e montato nella scheda (lo fa P12b, in corso). Con questa patch cambiano a schermo SOLO i testi del pulsante («Cash out Safe», «nessuna posizione viva di Safe su questa partita»).
- Limiti dichiarati: senza `chiusureGambe` (in arrivo con P12b) una partita con una chiusura ABBINATA e «NON CALCOLABILE»; sessione scalper non scomponibile; la copertura «banca Under 4,5» qui si chiude puntando l Under, Mike banca l Over: le due cifre possono differire di centesimi (il riquadro mostra entrambe). I valori dell engine nei casi di parita sono letti dal codice Python, non eseguiti.
