# R_B1 — correzioni di review (30/09/2026)

Worktree `...\.claude\worktrees\agent-a32982190acf0f4b4` (base `4fcb867`, nessun merge). Patch CUMULATIVA
B1+B1bis+R_B1: `AUDIT_2026-09-30/ui_blocchi/R_B1.patch` (10 file, solo `frontend/`, `git apply --check -R` = 0).
Niente commit/build. In `SchedaPartita.tsx` toccata SOLO la riga del target (il riquadro sopra e `CashOutPartita` no).

## 1. MEDIO — eta' delle linee Under/Over
Verificato nel Python: `seen_ms` e' in `_FUORI_FIRMA` (`scanner.py:495`); `service.py:1975-1977`
(`sig = payload_signature(payload); if written_sig == sig: continue`) salta la riscrittura se la firma non cambia,
quindi la pagina riceve il `seen_ms` dell'ultima RISCRITTURA. `ts_ms` NON e' in `_FUORI_FIRMA`: un suo cambio
cambia la firma e riscrive la riga; avanza solo se il blocco cambia (`service.py:1298-1309`, `unchanged` -> `prev_ts`).
- PRIMA: `ultimo book: 3 min fa` (da `seen_ms`, falso su linea ferma). DOPO: `ultimo cambio: 3 min` (da `ts_ms`, grigio neutro),
  `ultimo cambio: età ignota` se `ts_ms` manca; title «ultimo cambio di prezzo o di importo di questa linea: non è l’ultima lettura (ts_ms del blocco)».
- Campo rinominato `etaBookS` -> `etaCambioS` (`lib/controlRoom.ts`, `LineaOuScheda`/`lineeOuScheda`).
- Resta fuori perimetro e ha lo STESSO difetto: `lib/flussoPrezzi.ts` (`giudizioFlussoMike`, `daS` da `seen_ms`) e
  `FlussoBadge.tsx` («⚠ Under/Over 3,5 ferma · ultimo book N s fa»). Li' e' un badge di linea ferma: il numero puo'
  essere l'eta' dell'ultima riscrittura, non dell'ultimo book. Da correggere da chi ne ha il dominio.

## 2. MEDIO — target di ripiego
PRIMA: `target 4,17 € *` (media solo nel tooltip). DOPO: `target (media della pagina) 4,17 € *`; col target del
servizio resta `target 4,17 €`. **L'asterisco e' rimasto** perche' `pages/ControlRoom.test.tsx:294-299` (fuori
perimetro) pretende `*` nel testo del target calcolato: toglierlo romperebbe quel test. Se lo vuoi via, va cambiato
quel test (una riga). Aggiunto `data-testid="cr-target"`.

## 3. BASSO — logo rotto
`NomiPartita.Squadra` ricorda l'URL rotto (`rottoSrc`), non un si'/no: se la riga passa a un'altra squadra il nuovo logo si mostra.

## Test
Nuovi: SchedaPartita +2 (target ripiego / servizio), NomiPartita +1 (cambio `src`). Cambiati (dichiarati):
`controlRoom.test.ts` (finto `bloccoOu`: il 3° parametro ora e' l'eta' di `ts_ms`, `seen_ms` fisso a 1 s; nomi di 2 test),
`QuoteMercato.test.tsx`/`SchedaPreMatch.test.tsx` (testo atteso `ultimo book: N s fa` -> `ultimo cambio: N s`, piu' asserzione sul title),
rinomina `etaBookS` -> `etaCambioS` nei finti di 4 file di test. Rossi prima della correzione: 8.
Falsificazioni (`falsifica_r_b1.ps1`, copia fuori repo, try/finally, hash e `git diff` identici):
R1 torna a `seen_ms` ROSSO (2) · R2 torna «ultimo book» ROSSO · R3 ripiego senza dicitura ROSSO · R4 dicitura anche col servizio ROSSO · R5 rotto appiccicato alla riga ROSSO.
Numeri: mirati `--maxWorkers=2` (SchedaPartita, SchedaPreMatch, QuoteMercato, NomiPartita, controlRoom, flussoLineeMike) 6 file 171/171;
tsc (una volta, alla fine) 0 errori. Corsa allargata NON rilanciata (PC sotto replay): l'ultima, prima di R_B1, era 58 file 983/983.

## Non verificato
App a schermo non vista. `pages/ControlRoom.test.tsx` non rilanciato dopo R_B1 (cambia solo il testo del target: contiene ancora «target» e «*»).

## Verifica del coordinatore UI (admin-07), 30/09 20:35
- Giro 6 dell'albero integrato (tutti i blocchi + R_C, R_B2, R_T, R_B1): tsc 0 errori; vitest controlroom + trading + ControlRoom.test + lib toccate = 90 file, 1455 test verdi. R_G impilata dopo: test mirati di pagina/plancia/prova 185 verdi (tsc del giro 7 sul master + R1: vedi messaggio di consegna).
- La patch in QUESTA cartella e l INCREMENTALE della corsia; applica pulita sul master `d4b4f6b` (verificato con indice temporaneo). Ordine consigliato: R_C → R_B2 → R_T → R_B1 → R_G.
- Mutazione MIA: eta' delle linee di nuovo da `seen_ms` -> 3 rossi.
