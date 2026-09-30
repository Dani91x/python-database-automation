# W_C - P16, scalper nel cash out, tennis a due esiti, bassi del revisore (30/09 sera)

Worktree `...\.claude\worktrees\agent-a4f88b994afb4b99a`, strada (B'): backup `C_backup_pre_W.patch` (apply --check -R ok), `checkout --detach -f d4b4f6b`, `R_C_incr_lane.patch` applicata pulita (4 file). `W_C.patch` = `git diff -- frontend/` CUMULATIVA (R_C + W_C, 9 file). Niente commit ne' build. Falsificazioni: `falsifica_w_c.sh {p16|scalper|tennis|bassi}`, uscita `falsifica_w_c.out`.

## 1. P16 - «Chiudi tutte le gambe dei bot» (`CashOutGlobale.tsx`)
- Nessun comando nuovo: `pianoChiusuraPartita(ops, modalita)` (puro) decide con `chiudiRiga.chiudibile` (la regola del pulsante di riga) e l'esecuzione usa `ChiusuraRigaContext.chiudi(riga)` (lo stesso comando del «Chiudi» di riga). Mike: UN comando per partita (prima riga chiudibile; `mike_request('cashout')` chiude il ciclo) che copre N gambe; Safe (per riga, decisione del coordinatore), Omega, 4 bot tennis: per riga; scalper: per sessione con firma. Posizioni non chiudibili adesso -> dichiarate col motivo del bot, restano aperte.
- A schermo, in ogni blocco sulla SUA modalita': piano PRIMA del clic («2 gambe di Mike, 1 di Safe; Scalper calcio #7 non ha un comando adesso: resta aperta (firma della sessione assente ...)»); LIVE: arma + «Sono soldi veri: N comandi a M bot» + conferma inerte 400 ms (`ATTESA_CONFERMA_USCITE_MS`); PROVA: un clic. Esecuzione IN SEQUENZA (`await chiudi` una alla volta). Riscontro per comando da `stato()` + `faseMostrata`/`TESTO_FASE`: «Mike (partita, 2 gambe): presa in carico», «Safe #9: rifiutata: <motivo>». Spento con prezzi fermi (> 20 s, `feedFreshness`), eta' ignota o cifra non calcolabile. Senza il contesto della Control Room: nessun pulsante. `chiudiRiga.ts` NON toccato.
- Testid nuovi: `cr-cashout-globale-{live|prova}-chiudi-tutte`, `-piano`, `-avvia`, `-armato`, `-conferma`, `-annulla`, `-bloccato`, `-esito` (data-bot).
- Test `CashOutGlobale.chiudiTutte.test.tsx` 8. Falsificazioni: P1 parallelo 2 rossi; P2 Mike per gamba 4; P3 guardia tolta 1; P4 gamba senza comando taciuta 2.

## 2. Scalper nel cash out
- `useControlRoom.ts`: tipo `OperazionePartita.esposizioneSelezioni?` + UNA riga nella sola riga della sessione scalper di `operazioni` (`v.esp.selezioni`, `selezione: null`: il nome non c'e').
- `lib/cashOutPartita.ts`: `GambaViva.esposizione {win, lose}` (W/L gia' calcolati; altri bot invariati; sull'altra selezione di un mercato a due esiti W/L si scambiano); adattatore: una gamba per selezione; sessione regolata (`pnl`) o ferma senza residuo: fuori; senza esposizioni: resta «non scomponibile». Riga del riquadro: «esposizione Scalper calcio: se vince X / se perde Y».
- PRIMA -> DOPO: «NON CALCOLABILE: scalper #7: sessione dello scalper ...» -> cifra (es. −1,08 = −0,76 −0,32).
- Test: lib 3 (parita' con `esposizioneScalper` VERO sugli ordini), hook vero 1. Falsificazioni S1 3 rossi, S2 1.

## 3. Tennis a due esiti
- `dueEsitiPartita(sport, moMarketId, mike)`: nel tennis il Match Odds (`p.marketId` = `mo_market_id`) e' a due esiti; calcio no (3 esiti); altri mercati tennis per selezione. `CashOutGlobalePartita` prop `moMarketId`; `SchedaPartita.tsx`: SOLO `moMarketId={p.marketId}` sul `<CashOutGlobalePartita/>` (autorizzato).
- PRIMA -> DOPO: punta P1 + punta P2 10 @ 2,0 = due righe da chiudere -> UNA riga «pareggiata», +0,00.
- Test lib 1, montaggio 1. Falsificazioni T1 2 rossi, T2 1.

## 4. Bassi del revisore
- Sbilancio < 2 centesimi SENZA prezzo: «pareggiata (±0,0x), prezzo assente: vale il bloccato» (avviso) invece di NON CALCOLABILE; da 2 centesimi in su resta non calcolabile (Farul 0,02). Nome selezione: prima dell'id grezzo, il nome da qualunque gamba sulla stessa (mercato, selezione). Test 2, falsificazioni B1/B2 rosse.

## Test esistenti cambiati
Nessuno.

## Numeri
- `npx tsc -p tsconfig.app.json --noEmit`: 0 errori (una volta a fine lavori).
- Mirati: `npx vitest run src/lib/cashOutPartita.test.ts src/components/controlroom/CashOutGlobale.test.tsx src/components/controlroom/CashOutGlobale.montaggio.test.tsx src/components/controlroom/CashOutGlobale.chiudiTutte.test.tsx src/components/controlroom/useChiusuraAlMs.parita.test.tsx src/components/controlroom/SchedaPartita.test.tsx --maxWorkers=2`: 99/99.
- `npx vitest run src/components/controlroom src/lib/cashOutPartita.test.ts src/lib/chiusuraAlMs.test.ts src/lib/chiusuraUtente.test.ts src/pages/ControlRoom.test.tsx --maxWorkers=2`: **73 file, 1123/1123 verdi**.

## COSA NON HO FATTO / NON HO POTUTO VERIFICARE
- App a schermo non vista. Comandi veri non inviati (solo finti con le chiavi di `StatoChiusuraRiga`/`RigaDaChiudere`).
- «Aspettare l'esito» = esito d'INVIO del comando (la promessa di `chiudi`, che scrive inviata/rifiutata), non l'abbinamento finale (per Mike puo' richiedere piu' giri): il riscontro successivo si aggiorna a schermo dallo stato.
- Il nome delle selezioni della sessione scalper resta assente (la riga non lo porta): si vede «selezione <id>» se nessun'altra gamba lo conosce.
- Il pulsante sta anche nel blocco PROVA (un clic) per coerenza con «in PAPER un clic»: se lo vuoi solo in LIVE e' una riga.
