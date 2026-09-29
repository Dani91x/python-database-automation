# CANTIERE MIKE-COPERTURA - P5 blocco 4C: chiusura manuale e stato del mercato (29/09/2026)

Base: `4c66cbc` + `MIKE_P5_4.patch`. Patch: `AUDIT_2026-09-29/MIKE_P5_4C.patch` (6,8 KB). Nessun commit.

## Cosa cambia (`Betfair/mike/engine.py`, `_decide_flatten`, +16 / -3)
La guardia del blocco 4 fermava TUTTE le chiusure se anche una sola era su un mercato non operabile,
compreso un mercato CHIUSO (che non riapre): l'utente che preme Chiudi restava fermo per sempre.
Ora:
1. SOSPESO o stato ignoto (`riaprira(bk)` vero): si aspetta tutto, nessun ordine, stato fermo, motivo
   "attendo la riapertura" (come prima);
2. CHIUSO su una chiusura: quella chiusura si toglie, le altre (mercati aperti) partono; il motivo dice
   quale mercato e' chiuso ("... (mercato CHIUSO su OU45|OVER: quella chiusura non si puo' fare)");
   se tutte le chiusure sono su mercati chiusi: nessun ordine, "nessuna chiusura possibile (va al
   regolamento)".

## Test (`test_mike_p5_4c_2026_09_29.py`, 4) e mutazioni (`mike_p5/falsifica_mike_p5_4c.py`: 4 su 4 ROSSE)
Sospeso e ignoto = attesa (D3: nessuna attesa -> rosso); uno chiuso e uno aperto = parte solo quella
del mercato aperto (D1: la prima versione che ferma tutto -> rosso; D2: la chiusura sul mercato chiuso
parte lo stesso -> rosso); tutti chiusi = nessun ordine; selezione gia' decisa (D4 sotto).

## Punto 4: `force_flat_plan` e le selezioni gia' DECISE dai gol
CONFERMATO: non le mette fra le chiusure. `force_flat_plan` -> `cashout_value(..., goals=goals)`
(`engine.py:953` sul codice di questo worktree): con `won = selection_decided(...)` non None la
selezione va in `decided` e NON riceve un piano (`plans[key]` si scrive solo nel ramo `else`);
`_close_actions` (`engine.py:2042`) scorre solo `cv.plans`. Test: con 4 gol e l'Under 3,5 in mano,
`force_flat_plan` da' la sola chiusura `OU45|OVER`, e con il mercato 3,5 CHIUSO la chiusura della
copertura parte. Mutazione D4 (la selezione decisa riceve un piano) -> rosso.

## Suite
Sulla base `4c66cbc` + 4 + 4C: `Betfair/mike` 1222 verdi.
