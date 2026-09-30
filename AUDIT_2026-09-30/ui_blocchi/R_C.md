# R_C - correzioni della review finale (C_CASHOUT)

Stesso worktree, stessa base `1d058a7`, nessun merge. Patch CUMULATIVA `R_C.patch` (18 file). Niente commit.
File toccati in R_C: `components/controlroom/CashOutGlobale.tsx`, `lib/cashOutPartita.ts`, `CashOutGlobale.test.tsx`, `lib/cashOutPartita.test.ts`.

| # | Reperto | PRIMA -> DOPO a schermo / nel calcolo |
|---|---|---|
| 1 ALTO | il riquadro non diceva di contare solo i bot | titolo «Cash out della partita (se chiudo TUTTO adesso)» -> «Cash out della partita: gambe dei bot (se le chiudo tutte adesso)»; riga SEMPRE visibile sotto la cifra, ambra tenue, nel solo blocco LIVE (anche con «NON CALCOLABILE»): «solo ordini dei bot: gli ordini fatti dal sito o dall'app Betfair non sono inclusi» (`cr-cashout-globale-live-solo-bot`) |
| 2 MEDIO | causa della differenza affermata | «differenza 0,02 €: prezzi letti in istanti diversi (...)» -> «differenza 0,02 € · cause possibili: prezzi letti in istanti diversi (pagina X s fa, bot Y s fa); il bot chiude la copertura su un altro libro; il bot conta solo le sue gambe» |
| 3 MEDIO | ordine tennis regolato trattato come gamba viva | `OperazionePerCashOut.pnl?` (opzionale, gia' su `OperazionePartita`); in `gambeDaOperazioni` una riga `tennis_*` con `pnl` valorizzato (in `useControlRoom` solo con `settled_at`) non e' una gamba. Le righe calcio restano governate da `statoOrdine` (won/lost/void) |

Test (nuovi/estesi): `CashOutGlobale.test.tsx` riga «solo bot» con cifra, con NON CALCOLABILE, assente in PROVA; testo della differenza con le tre cause. `cashOutPartita.test.ts`: ordine tennis `EXECUTION_COMPLETE` con `pnl` -> non gamba (e non rende la cifra incompleta), senza `pnl` e abbinato -> gamba.
Test esistenti cambiati (miei, di P12a): `CashOutGlobale.test.tsx` titolo e regex della differenza (motivo: testi corretti su richiesta della review).

Falsificazioni (`falsifica_r_c.sh` / `.out`): R1 riga tolta -> 2 rossi; R2 una sola causa -> 1 rosso; R3 filtro tennis tolto -> 1 rosso. Ripristino da copia fuori repo, MUTAZIONE = 0.

Numeri: `npx vitest run src/lib/cashOutPartita.test.ts src/components/controlroom/CashOutGlobale.test.tsx src/components/controlroom/CashOutGlobale.montaggio.test.tsx src/components/controlroom/useChiusuraAlMs.parita.test.tsx --maxWorkers=2` 51/51; `npx tsc -p tsconfig.app.json --noEmit` 0 errori (una volta, alla fine).

NON fatto / NON verificato: la suite intera della cartella non rilanciata (PC sotto replay; l'ultima, prima di R_C, 936/937 col solo rosso di velocita' di PosizioniChiuse); app a schermo non vista; l'inclusione degli ordini del sito nel calcolo resta per un blocco futuro (serve lo specchio `betfair_live_orders` per evento, B14).

## Verifica del coordinatore UI (admin-07), 30/09 20:35
- Giro 6 dell'albero integrato (tutti i blocchi + R_C, R_B2, R_T, R_B1): tsc 0 errori; vitest controlroom + trading + ControlRoom.test + lib toccate = 90 file, 1455 test verdi. R_G impilata dopo: test mirati di pagina/plancia/prova 185 verdi (tsc del giro 7 sul master + R1: vedi messaggio di consegna).
- La patch in QUESTA cartella e l INCREMENTALE della corsia; applica pulita sul master `d4b4f6b` (verificato con indice temporaneo). Ordine consigliato: R_C → R_B2 → R_T → R_B1 → R_G.
- Diff riletto: riga «solo ordini dei bot» sempre visibile nel blocco LIVE; cause della differenza non affermate; ordine tennis con `pnl` valorizzato non e' una gamba.
