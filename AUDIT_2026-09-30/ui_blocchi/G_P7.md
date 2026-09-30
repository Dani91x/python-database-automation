# G_P7 - Composizione LIVE per bot dal conto (`pnl_reale_oggi.per_fonte`) (blocco B7)

Worktree: `C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.claude\worktrees\agent-ad6a40b65633ea777` (base `1d058a7`)
Patch: `AUDIT_2026-09-30/ui_blocchi/G_P7.patch` = diff CUMULATIVO `frontend/` vs `1d058a7` (P2 + test P2 + P8 + P7). Nessun commit. Nessuna modifica a `DayBar` (P6 rinviato a domani).

## Cosa cambia
Con il conto letto, la voce di ogni bot nella composizione e' `per_fonte[bot].netto` (attribuzione del BACKEND per bet_id / customerOrderRef, `reconcile_worker.py`, non rifatta) + la parte ancora STIMATA delle righe del bot (chiusa dal bot, bet_id non contato dal conto). Prima era il reale delle righe caricate dalla pagina e la differenza col conto finiva in «Altro sul conto Betfair»: una posizione LIVE di ieri regolata oggi (che `get_mike_state` non porta: solo righe piazzate oggi o aperte; `get_safe_state`: ultime 200) spariva dal suo bot. «Altro» ora = solo `per_fonte.altri_bot`. La voce «Manuale» (cicli aperti a mano dentro i bot) tiene solo la parte stimata: il reale il conto lo attribuisce al bot. Il TOTALE non cambia (verificato nei test: stesse fonti, voce diversa). Conto non letto: composizione di prima, invariata, dichiarata «conto Betfair non letto: dalle righe dei bot».

## PRIMA -> DOPO a schermo
Caso: Mike, posizione LIVE piazzata ieri, regolata oggi +2,00 (conto: `per_fonte.mike = {2,00, 1 ordine}`), riga non caricata.
PRIMA: `Mike —` · `Altro sul conto Betfair +2,00 €`
DOPO: `Mike +2,00 € [CONTO BETFAIR · 3 min fa]` · `Altro sul conto Betfair —`; intestazione «composizione — solo soldi veri, entra nell'obiettivo · realizzato di ogni bot dal conto Betfair (attribuito da Betfair), la parte non ancora regolata stimata dal bot».
Oggi (0 ordini regolati sul conto): tutte le voci «—» come prima (0 ordini = nessuna voce; il «0,00 sempre visibile» e' di P6).

## Fonti
- `pnl_reale_oggi` (colonna `betfair_live_account.pnl_reale_oggi` o canale 47331 `account`, il piu' recente: `pnlRealePiuRecente`), letto gia' da `useControlRoom.ts` (`pnlRealeOggi`, ~riga 2001).
- stimato: `pnlStimato` delle righe-ciclo LIVE (`righeGiornataPerCiclo`).
- eta' del marchio CONTO: `pnl_reale_oggi.letto_at` (NB: il runner lo scrive solo al cambio del dato: e' l'eta' dell'ultima scrittura).

## File del SOLO P7
- nuovi: `frontend/src/lib/composizioneConto.ts` (`composizioneDalConto`, `etaContoS`), `frontend/src/lib/composizioneConto.test.ts` (5), `AUDIT_2026-09-30/ui_blocchi/falsifica_G_P7.ps1`
- toccati: `useControlRoom.ts` (import; `composizioneOggi` = `composizioneDalConto(componiObiettivo(...), pnlRealeOggi, righe)`; campo VM nuovo `contoLettoAt?: string | null`), `ObiettivoHero.tsx` (prop nuova `contoEtaS`, prop `composizione` accetta `ComposizioneConto`, marchio CONTO/BOT per voce `cr-composizione-<chiave>-fonte`, nota di fonte `cr-composizione-fonte`), `ControlRoom.tsx` (`contoEtaS={etaContoS(vm.contoLettoAt, vm.nowMs)}` + import), `ObiettivoHero.test.tsx` (+1), `useControlRoom.provaGiornata.test.tsx` (+1 describe P7).
- Nessun test esistente cambiato in P7. `lib/composizioneObiettivo.ts` NON toccato (funzioni certificate invariate, si aggiunge accanto).

## Test
- nuovi: `composizioneConto.test.ts` (Mike di ieri regolato oggi sotto Mike e «Altro» vuoto, totale invariato; reale+stimato dichiarati; Safe calcio/tennis per voce del conto, paper mai dentro; 0 ordini = «—»; conto non letto = invariato); hook vero: «P7 - Mike posizione di ieri regolata oggi -> sotto Mike dal CONTO, Altro vuoto, realizzato della barra invariato»; `ObiettivoHero`: marchio CONTO con eta' «3 min fa», BOT, nessun marchio su voce vuota, «conto Betfair non letto».
- Falsificazioni (`falsifica_G_P7.ps1`, ripristino in `finally`, 0 `MUTAZIONE`, diff --stat identico): M1 composizione mai ricomposta dal conto -> 5 rossi; M2 Mike ignora il conto -> 3 rossi; M3 la voce non dichiara la fonte -> 1 rosso.
- `npx tsc -p tsconfig.app.json --noEmit` = 0 (un errore di tipo nel test nuovo corretto allargando il tipo del prop `composizione`, poi ObiettivoHero.test rieseguito verde 7/7).
- fine blocco: `npx vitest run src/pages/ControlRoom.test.tsx src/components/controlroom src/components/trading src/lib/composizioneObiettivo.test.ts src/lib/giornataCorsie.test.ts src/lib/provaGiornata.test.ts src/lib/composizioneConto.test.ts --maxWorkers=2` = 76 file, 1116 verdi (475 s).

## COSA NON HO FATTO
- Tessere sport, corsia LIVE: la cifra per sport resta dalle righe dei bot + le voci sintetiche del conto; la differenza conto-righe («Altro») ha `sport: 'calcio'`, quindi una posizione Safe TENNIS di ieri regolata oggi comparirebbe nella tessera del CALCIO. Difetto preesistente, non corretto (servirebbe dividere la differenza per sport: decisione tua).
- Colonna «aperto (bot)» e «partite» per bot nella composizione (progetto §2.C): dipende dal cash out per partita (P6/B12), rinviato.
- P6 non iniziato (rinviato a domani): nessuna modifica a `DayBar`.
## COSA NON HO POTUTO VERIFICARE
- L'app a schermo; un giorno reale con ordini regolati sul conto (oggi 0): verificato solo con finti con la forma di `leggiPnlRealeOggi`.

## Verifica del coordinatore UI (admin-07), 30/09 18:55
- Terzo giro, albero integrato (`1d058a7` + C_P12a + B1bis + P13 + T_P4 + G_P7): `npx tsc -p tsconfig.app.json --noEmit` = 0 errori; `npx vitest run src/components/controlroom src/components/trading src/pages/ControlRoom.test.tsx` + 9 test di lib toccati = 91 file, 1478 test verdi.
- La patch in QUESTA cartella e l INCREMENTALE ricavato da me sul master `f58b595`; ordine di applicazione: `B1bis.patch` → `P13_ESITI_CHIUSURA.patch` → `T_P4.patch` → `G_P7.patch` (fusione a tre vie senza conflitti; su ogni file toccato il risultato e identico byte per byte all albero verificato).
- Mutazioni MIE (oltre le 3 del delegato), ROSSE: voce del conto mostrata anche con 0 ordini (0,00 al posto di «—») (3 rossi); Mike che prende il conto di Omega (3).
- Residuo dichiarato dal delegato, preesistente e NON corretto: nelle tessere sport la differenza conto-righe ha sport calcio (una posizione Safe TENNIS di ieri regolata oggi comparirebbe nel calcio).
