# MIKE - testi veritieri (A3, A4, A12, M17, punto 15) - 30/09/2026

Delegato Sonnet. Solo testi e test: nessuna logica, soglia, stake o flusso toccati.
Patch: `AUDIT_2026-09-30/MIKE_TESTI_VERITIERI.patch` (`git diff HEAD`, 13 file; il test nuovo Python e' incluso con `git add -N` sul solo suo percorso).

## A4 - motivi del motore (Betfair/mike/engine.py)
| riga | prima | dopo |
|---|---|---|
| 3511 | gol precoce: copertura Over 4.5 | gol precoce: copertura sulla linea 4,5 |
| 3528 | uscita non abbinata in %d': copertura Over 4.5 | ...: copertura sulla linea 4,5 |
| 3841 | copertura: mercato Over 4.5 %s, si aspetta la riapertura | copertura: mercato della linea 4,5 %s, si aspetta la riapertura |
| 4081 | copertura: mercato Over 4.5 %s, nessun riprezzo | copertura: mercato della linea 4,5 %s, nessun riprezzo |
| 3888-3891 | copertura Over 4.5: prima tranche / seconda tranche (residuo) / Over 4.5 (default) / in una volta (...) | copertura sulla linea 4,5: prima tranche / seconda tranche (residuo) / sulla linea 4,5 (default) / sulla linea 4,5 in una volta (...) |
- Chiavi? Nessuna: grep su tutto `Betfair/` e `frontend/src` - nessun `==`/`in`/`startswith` di produzione su queste frasi. Unico consumatore letterale: `Betfair/tools/verifica_75_condizioni_2026_09_13.py:241` (`motivo_contiene("copertura Over 4.5")`, script di verifica, non test) aggiornato alla frase nuova.
- Nessun test esistente confrontava queste frasi alla lettera (`Betfair/mike` 1388 passati prima e dopo, invariati). Gli altri «copertura Over 4.5» trovati sono docstring/commenti (non toccati) e `service.py:1045` (nota «copertura Over 4.5 FERMATA...», altra stringa, fuori dall'elenco: NON toccata, da valutare).
- NON cambiate (gia' vere): le varianti della forma di serie `copertura: mercato Under 4.5 %s, ...` (engine 3961, 4127), `flat: mercato Under 4.5` (4369), testate da `test_mike_p5_4b`.
- Nota: 3841/3888/4081 stanno nel ramo `back_over45` (forma vecchia), dove «Over 4.5» era vero; cambiate perche' richiesto, la nuova frase resta vera in entrambe le forme.
- Test nuovo: `Betfair/mike/tests/test_mike_testi_veritieri_2026_09_30.py` (3 test: uscita non abbinata allo scadere, mercato sospeso forma punta Over, guardia AST sul sorgente: nessuna stringa non-docstring dice «copertura Over 4.5»/«mercato Over 4.5»).

## A3 + punto 15 (frontend)
- `MikeMatchCard.tsx:749` Over: `'Over 4.5 back / lay'` -> `'Over 4.5 · chiusura della copertura'` (variante terminal invariata).
- `MikeMatchCard.tsx:757` Under: `'Under 4.5 (re-ingresso)'` -> `'Under 4.5 · copertura (banca) e re-ingresso'`; title: `linea del re-ingresso dopo un gol` -> `su questa linea Mike banca la copertura (di serie) e rientra dopo un gol`.
- `SchedaMike.tsx`: nuova Voce `Under 4.5` (testId `<id>-u45`, `books['OU45|UNDER']`) accanto all'Over; title Over: `... (la copertura)` -> `... sull'Over 4.5: serve alla chiusura della copertura`.
- `SchedaMike.tsx:127` (punto 15): `perdono sia Under 3.5 sia Over 4.5` -> `perdono l'Under 3,5 e la copertura`.
- Test: `MikeMatchCard.test.tsx` (+1), `SchedaMike.test.tsx` (+1: Under e Over presenti, niente «(la copertura)», parentesi p4).

## A12 - InterruttoreUscite.tsx
- Tooltip «passa a manuali» con la nota di Mike: `le uscite in PERDITA diventano proposte da approvare; green-up, uscita al fischio e cash out in profitto restano automatici`. Tooltip di conferma (manuali -> automatiche), sempre con la nota di Mike: `confermi? da qui Mike esegue da solo anche le uscite in PERDITA (green-up, uscita al fischio e cash out in profitto sono gia' automatici)`.
- Scelta: il testo speciale scatta quando `uscite.nota === NOTA_USCITE_MIKE` (importata da `lib/interruttori`), non per qualunque nota: lo scalper ha una nota diversa («nessuna sessione attiva...») e il testo di Mike sarebbe falso per lui. Senza la nota di Mike i tooltip sono identici a oggi.
- Test: `PannelloBotUscite.test.tsx` (+1: con nota, conferma con nota, senza nota invariato).

## M17 - lib/mike.ts e pages/Mike.tsx
- `mike.ts:473` `copertura piena sull'Over 4.5` -> `copertura piena sulla linea 4,5`.
- `mike.ts:482` `sulla quota Over di quel momento` -> `sul prezzo della copertura di quel momento`.
- `mike.ts:523` `a fine 1T con 2-4 gol` -> `a fine 1T con 3-4 gol (vedi gol min/max)`; verificato: `config.py:296-297` `ht_loss_goals_min=3`, `ht_loss_goals_max=4` (anche in MIKE_PARAM_DEFAULTS).
- `mike.ts:524` `chiude comunque se la perdita...` -> `propone (o esegue, se le uscite automatiche sono accese) l'uscita se la perdita...`.
- `Mike.tsx:763` `La struttura Under 3.5 / Over 4.5 perde con esattamente 4 gol` -> `La struttura Under 3,5 + copertura 4,5 perde con esattamente 4 gol` (nel file c'era gia' «esattamente»).
- Flatten: SI, era mostrato al trader (`MIKE_REQUEST_KIND_LABEL.flatten` = `Flatten`, usato in toast e riga «Flatten armato: ...»). Ora `Chiusura a mercato` (come il pulsante «Chiudi a mercato»); concordanza al femminile in `requestOutcome` (armata/eseguita/rifiutata; Cash out resta maschile). Lo stato `FLAT` era gia' «PIATTA» in italiano (`MIKE_PHASE_META`), non toccato.
- Test: `mikeCoverForm.test.ts` (+1 hint), `mike.test.ts` (aggiornato «Chiusura a mercato armata: ...» + asserzioni su label/eseguita).

## Verifiche (numeri)
- `python -m pytest Betfair/mike -q -p no:cacheprovider` (env neutro): 1388 passati (prima del test nuovo); test nuovo 3 passati.
- `npx tsc -p tsconfig.app.json --noEmit`: 0 errori.
- `npx vitest run src/components/mike src/components/controlroom/SchedaMike src/components/controlroom/PannelloBotUscite src/lib/mike ...`: 20 file, 267 test verdi. Piu' `src/components/controlroom src/pages/Mike src/certification`: 55 file passati, 771 test, 50 skipped (gia' tali).
- Falsificazione (mutazione -> rosso -> ripristino da copia, ri-verde): (1) in engine.py rimesse due frasi vecchie -> i 3 test Python rossi, ripristino -> 3 verdi; (2) `conNotaMike = false` in InterruttoreUscite -> test A12 rosso; (3) etichetta Under di MikeMatchCard rimessa alla vecchia -> test A3 rosso; ripristinati, 43/43 verdi.

## Non verificato / non cambiato
- Non ho rieseguito l'intera suite Python dopo aver aggiunto il solo file di test nuovo (engine invariato dalla corsa da 1388).
- `service.py:1045` («copertura Over 4.5 FERMATA dopo rifiuti identici») e i commenti/docstring con «Over 4.5» non toccati (fuori perimetro).
- Nessun replay lanciato (solo testi, nessuna decisione cambia).
- Nel worktree ho creato la junction `frontend/node_modules` verso il checkout principale (da togliere con `cmd /c rmdir`, mai remove --force).
