# P1_MARCHIO_FONTE - referto
File nuovi: frontend/src/lib/fonteSoldi.ts, frontend/src/components/controlroom/MarchioSoldi.tsx, MarchioSoldi.test.tsx. Nessun altro file toccato.
Test: 10/10 verdi (vitest, solo questo file). tsc -p tsconfig.app.json = 0 errori.
Falsificazioni (copia fuori repo, hash identico dopo il ripristino): M1 null trattato come 0 -> 2 rossi; M2 PROVA scambiata con CONTO -> 2 rossi.
Scelte: eta negativa/NaN = "età ignota" (arancione); eta 0 = "0 s fa". HEAD del worktree 15f0a33 (discendente di 35e1499).
Non verificato: l'aspetto a schermo (colori, 9 px, contrasto).

## Verifica del coordinatore UI (admin-07), 30/09 17:02
- Patch rigenerata da me dal worktree del delegato (`git diff -- frontend/`): la sua conteneva 2 file su 3 (mancava il test). Quella in questa cartella ha i 3 file (+154 righe), si applica pulita su `35e1499` (`git apply --check`).
- Nel mio worktree di verifica (`scratchpad/verifica-ui`, `35e1499` + patch): `npx tsc -p tsconfig.app.json --noEmit` = 0 errori; `npx vitest run src/components/controlroom/MarchioSoldi.test.tsx` = 10/10.
- Mutazioni MIE (diverse da quelle del delegato), tutte ROSSE, file ripristinati da copia e confrontati con `cmp`: (1) eta' negativa letta come valida; (2) `dettaglio` non entra nel `title`; (3) etichetta BOT scritta «CONTO BETFAIR».
- Attinenza: solo i tre file chiesti, nessun altro file toccato. Non verificato: l'aspetto a schermo (9 px, contrasto di BOT e PROVA, molto simili fra loro: da guardare al primo avvio).
