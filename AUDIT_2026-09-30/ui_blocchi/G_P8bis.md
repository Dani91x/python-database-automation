# G_P8bis - Plancia dei bot: prova di OGGI e arretrati a parte

Worktree: `C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.claude\worktrees\agent-ad6a40b65633ea777` (base `1d058a7`)
Patch: `AUDIT_2026-09-30/ui_blocchi/G_P8bis.patch` = diff CUMULATIVO `frontend/` vs `1d058a7` (P2 + test P2 + P8 + P7 + P8bis). Nessun commit. Dipendenze per gli arretrati di Mike: le stesse di P8 (migrazione `mike_state_arretrati_prova_2026-09-30.sql` + `fetchMikeState` che inoltra la chiave).

## PRIMA -> DOPO (riga Safe base della plancia, Safe in prova, fatti di oggi)
PRIMA: `Safe base · prova · oggi 7,60 €`
DOPO:  `Safe base · prova · oggi —   arretrati regolati oggi: +7,60 € (4 operazioni aperte il 26/09)`
- «oggi —» segue la regola gia' certificata della plancia (`PannelloBot.tsx`: `null` = niente di regolato oggi, «—», mai «0,00 €»): per le partite di oggi non c'e' niente di regolato. Le tessere e il riquadro scrivono 0,00 per «letto e vuoto» (regola F-3 delle tessere): due regole preesistenti diverse, NON uniformate qui (decisione tua se allinearle).
- Mike in prova (quando lo e'): `oggi` delle partite di oggi + arretrati dalla chiave `arretrati_prova` (non letti = nessuna riga di arretrati nella plancia; lo dice la corsia PROVA del riquadro).
- In LIVE la riga NON cambia (giorno di regolamento, `pnlChiuseDelGiorno`) e non mostra arretrati di prova.

## Fonte
Stessa regola e fonte di P8: `lib/provaGiornata.ts` (`provaPerGiornoPartita` + nuovo `provaDellaRiga`), sulle stesse righe (`get_omega_trades`, `get_safe_state`, `get_mike_state`); Safe per STRATEGIA dell'apertura del ciclo (`strategy`).

## File del SOLO P8bis
- nuovi: `frontend/src/components/controlroom/righeBot.provaArretrati.test.tsx` (3), `AUDIT_2026-09-30/ui_blocchi/falsifica_G_P8bis.ps1`
- toccati: `lib/provaGiornata.ts` (campo `strategy` in ingresso, `strategia` sulla riga, `provaDellaRiga`), `righeBot.ts` (campi opzionali `arretratiPaper` del bot e per strategia; `arretratiProva` sulla riga solo in prova), `PannelloBot.tsx` (campo opzionale `arretratiProva` di `RigaInterruttore` e UNA riga di stampa accanto a `cr-bot-pnl-<id>`: testid nuovo `cr-bot-arretrati-<id>`), `useControlRoom.ts` (tipo `StatoBot`: `arretratiPaper`; in `botsConPnl` la sola parte PROVA di Omega/Mike/Safe-per-strategia; LIVE invariato), `useControlRoom.provaGiornata.test.tsx` (+2).
- Significato CAMBIATO (dichiarato): `StatoBot.pnlOggiPaper` (Omega/Mike) e `pnlOggiPerStrategia[k].paper` (Safe) = sole partite di OGGI (prima: posizioni chiuse per giorno di regolamento, F-1 del 26/09). «Posizioni chiuse» NON toccata.
- Nessun test esistente cambiato (il test F-1 del hook «Omega in prova ... pnlOggiPaper 0,95» resta verde: partita di oggi).

## Test e falsificazioni
- nuovi: plancia Safe base in prova -> `pnlOggi` null e arretrati +7,60 accanto; in LIVE nessun arretrato; a schermo «oggi —» e «arretrati regolati oggi: +7,60 € (4 operazioni aperte il 26/09)»; hook vero: Safe base `paper` null + arretrati 7,60, le altre strategie senza; Mike arretrati dalla chiave del backend.
- Falsificazioni (`falsifica_G_P8bis.ps1`, ripristino in `finally`, 0 `MUTAZIONE`, diff --stat identico): M1 Safe torna alla prova per regolamento -> 1 rosso (hook); M2 la riga perde gli arretrati -> 2 rossi; M3 la plancia non li stampa -> 1 rosso.
- tsc = 0. Fine blocco: `npx vitest run src/pages/ControlRoom.test.tsx src/components/controlroom src/components/trading src/lib/composizioneObiettivo.test.ts src/lib/giornataCorsie.test.ts src/lib/provaGiornata.test.ts src/lib/composizioneConto.test.ts --maxWorkers=2` = 77 file, 1121 verdi (443 s).

## COSA NON HO FATTO / NON HO POTUTO VERIFICARE
- Riassunto del gruppo in plancia (`riassuntoGruppo`, «oggi» del bot intero): somma i `pnlOggi` delle righe, quindi ora esclude gli arretrati (giusto); gli arretrati non sono riassunti a livello di gruppo.
- Scalper calcio e 4 bot tennis nella plancia: invariati (tennis per regolamento, gia' dichiarato in P8).
- L'app a schermo non la vedo.

## Verifica del coordinatore UI (admin-07), 30/09 19:05
- Quarto giro, albero integrato (`1d058a7` + B1bis + P13 + T_P4 + G_P7 + G_P8bis + C_P12b): `npx tsc -p tsconfig.app.json --noEmit` = 0 errori; `npx vitest run src/components/controlroom src/components/trading src/pages/ControlRoom.test.tsx` + 9 test di lib = 93 file, 1480 test verdi.
- La patch in QUESTA cartella e l INCREMENTALE ricavato da me sul master `f58b595` + B1bis + P13 + T_P4 + G_P7; ordine: `G_P8bis.patch` → `C_P12b.patch` (tre vie senza conflitti; file toccati identici byte per byte all albero verificato).
- Mutazione MIA (oltre le 3 del delegato), ROSSA: la riga della plancia conta gli arretrati dentro «oggi» (1 rosso). Diff riletto: in live la riga non mostra arretrati di prova; `pnlOggiPaper` e `pnlOggiPerStrategia[k].paper` ora = sole partite di oggi (significato cambiato, dichiarato).
- Da uniformare (preesistente): in prova senza niente di regolato la plancia scrive «—», tessere e riquadro «0,00».
