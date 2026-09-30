# G_P2 - Tessere sport a due corsie LIVE / PROVA (blocco B2 del progetto)

Worktree: `C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.claude\worktrees\agent-ad6a40b65633ea777`
Base: master `1d058a7` (ff da 35e1499, porta MarchioSoldi). Patch: `AUDIT_2026-09-30/ui_blocchi/G_P2.patch` (nessun commit).

## PRIMA -> DOPO a schermo (fatti di oggi: Mike LIVE acceso, Safe paper, Omega paper fermo, scalper calcio senza modalita', 4 bot tennis paper)

PRIMA:
```
Calcio MODALITA' PAPER 3 aperte +7,60 EUR 4 operazioni 4 V 0 P 100 %
Tennis MODALITA' PAPER +0,00 EUR nessuna operazione in prova oggi
```
DOPO (P2; le cifre PROVA restano quelle di oggi per regolamento finche' non arriva P8):
```
CALCIO [SOLDI VERI]
 LIVE   Mike                                              3 aperte
        +0,00 €  [BOT]  nessuna operazione con soldi veri oggi
 PROVA  Omega (spento) · Safe base · Safe esatto · Safe punta (spento)     (bordo tratteggiato)
        +7,60 €  [PROVA]  4 operazioni 4 V 0 P 100 %
 modalità non dichiarata: Scalper calcio (spento)
TENNIS
 LIVE   nessun bot in live
        +0,00 €  [BOT]  nessuna operazione con soldi veri oggi
 PROVA  Safe tennis · Scalper · Pro · FLB · Swing
        +0,00 €  [PROVA]  nessuna operazione in prova oggi
```
(«3 aperte» = partite con riga LIVE non regolata, conteggio invariato `apertePerSport`: il «a rischio vero» e' di altri blocchi.)

## Fonte di ogni cifra / voce
- Elenco bot per corsia: `control.mode` + `status` di ogni servizio gia' nel VM (`vm.bots`, `useControlRoom.ts:2220-2335`: Omega/Safe/Mike dalle RPC di stato, 4 bot tennis da `get_tennis_bot_services`, scalper da `statoBotScalper`). Safe diviso per strategia con la stessa regola di prima (`mode` del servizio = tetto, `strategy_modes` = con che soldi, `varianti` = chi apre): `lib/giornataCorsie.ts:voceSafe`.
- «SOLDI VERI»: un bot LIVE acceso, oppure una posizione LIVE aperta sullo sport (`apertePerSport`).
- Cifra LIVE: `soldiGiornata.perSport[sport]` (invariato, righe dei bot per giorno di regolamento, `useControlRoom.ts` `tesseraSport('live')`), marchio `BOT`. Cifra PROVA: `soldiGiornata.perSportPaper[sport]`, marchio `PROVA`. Mai sommate.

## File
- nuovi: `frontend/src/lib/giornataCorsie.ts`, `frontend/src/lib/giornataCorsie.test.ts`
- toccati: `frontend/src/components/controlroom/SplitSport.tsx` (riscritta la tessera: due corsie; prop `modalita` TOLTA, prop nuova `corsie`), `frontend/src/pages/ControlRoom.tsx` (tolta `modalitaPerSport`, montaggio `corsie={corsiePerSport(vm.bots)}`, 1 import), `ControlRoom.test.tsx` (+2 test), `fixPagine2609.giornata.test.tsx` (vedi sotto).
- Nessun campo nuovo del VM. `grep modalitaPerSport` prima del lavoro: usata solo in `ControlRoom.tsx:600`.
- testid conservati: `cr-split-sport`, `cr-sport-<s>`, `cr-filtro-<s>` (aria-pressed invariato), `cr-sport-<s>-pnl` (ora sul numero della corsia principale: LIVE se lo sport ha un bot LIVE o una posizione LIVE, altrimenti PROVA). Nuovi: `cr-sport-<s>-live|prova`, `-live-bot|-prova-bot`, `-live-pnl|-prova-pnl`, `-live-fonte|-prova-fonte`, `-soldi-veri`, `-ignote`.

## Test
- nuovi: `giornataCorsie.test.ts` (6), `ControlRoom.test.tsx` «Mike LIVE + Safe paper -> corsia LIVE con Mike, PROVA con Safe e Omega, scalper spento elencato» e «nessun bot LIVE -> nessun soldi veri».
- esistenti cambiati: `fixPagine2609.giornata.test.tsx:141` e `:148` - tolto il prop `modalita={{...}}` (prop eliminato perche' era la «modalita' dello sport» falsa); asserzioni IDENTICHE.
- Falsificazioni (copia in scratchpad, ripristino dalla copia, 0 `MUTAZIONE`, `git diff --stat` identico):
  - M1 modo di ogni bot preso dal solo Safe -> 3 rossi (2 unita' + test di pagina Mike LIVE);
  - M2 `soldiVeri = false` -> rosso il test di pagina Mike LIVE;
  - M3 `liveAcceso` sempre true -> 5 rossi (3 unita' + 2 di pagina).
- `npx tsc -p tsconfig.app.json --noEmit` = 0 errori.
- `npx vitest run src/pages/ControlRoom.test.tsx src/components/controlroom src/components/trading src/lib/composizioneObiettivo.test.ts src/lib/giornataCorsie.test.ts --maxWorkers=2` = 72 file, 1090 test verdi (590 s, PC carico).

## COSA NON HO FATTO
- Cifre per bot dentro le corsie (P7) e «oggi / arretrati» nella PROVA (P8): qui le cifre sono ancora quelle di prima.
- Eta' del dato nel marchio (etaS omesso): le righe dei bot hanno eta' per bot (`fonteRighe`), non per sport.
- Omega/Mike fissano il modo sulla PARTITA: una partita armata in live con il bot in paper non compare nella corsia LIVE (dato non nel VM per Omega; e' del blocco testata/chip).
- Scalper calcio spento ha modalita' `null` (`statoBotScalper`): elencato in «modalità non dichiarata», non in PROVA (corsia T/B5 lo sistemera' alla fonte).
## COSA NON HO POTUTO VERIFICARE
- L'app a schermo: non la vedo; disposizione e leggibilita' lette dal sorgente.

## Verifica del coordinatore UI (admin-07), 30/09 18:05
- Albero di verifica: `1d058a7` + C_P11 + G_P2 (+ test) + B1 + B2 impilati SENZA conflitti; le stesse patch, in questo ordine (G_P2 → G_P2_test → B1 → B2), si applicano pulite con `git apply` sul master `7bbff9b` (provato in un worktree di integrazione).
- Sull albero INTEGRATO: `npx tsc -p tsconfig.app.json --noEmit` = 0 errori; `npx vitest run src/components/controlroom src/components/trading src/pages src/components/mike` + i test di lib toccati = 111 file, 1685 test verdi, 1 saltato (737 s a PC carico).
- Diff riletto. Mutazioni MIE: strategia Safe non dichiarata che EREDITA live dal servizio -> rosso; bot con modalita null messo in PROVA -> 3 rossi; **corsia PROVA alimentata col dato LIVE -> SOPRAVVISSUTA** al primo giro (nessun test fissava il confine live/paper della tessera). Rimandata al delegato: test nuovo `SplitSport.corsie.test.tsx` (`G_P2_test.patch`, 3 test); rifatta da me la mutazione: 3/3 ROSSI. Ripristino da copia verificato con `cmp`.
- Resta vero a schermo dopo P2 (dichiarato dal delegato): le cifre PROVA sono ancora per giorno di regolamento (+7,60) finche non arriva G_P8; «N aperte» conta ancora le partite pareggiate/chiuse dal sito.
