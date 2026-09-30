# R_B2 - correzioni della review finale (30/09)

Worktree: `...\.claude\worktrees\agent-aef9b44f1a9ce5796` (base 4fcb867, niente merge). Patch CUMULATIVA di `frontend/` (B2 + P13 + R): `R_B2.patch` (25 file, `git apply --check -R` OK).

## 1. ALTO - cash out monco nella scheda di approvazione (`PropostaUscitaMike.tsx`)
- PRIMA: `bloccabileOra = live.cashout.net` senza guardare `complete`. A schermo «chiudendo tutta la partita ora +1,23 € (aggiornata N s fa)» anche con una linea senza prezzo.
- DOPO: la cifra si mostra solo se `live.cashout.complete === true` (stessa regola di `SchedaMike` A9, `engine.py:946-968`). Altrimenti: «chiudendo tutta la partita ora: non calcolabile (manca il prezzo di una linea)» (testid nuovo `…-cifra-non-calcolabile`, nessuna cifra). Con la cifra compare « (calcolo del bot)» (testid nuovo `…-fonte-cifra`): `MarchioSoldi.tsx` non esiste su 4fcb867, quindi NON è stato creato.
- Invariati: cifra barrata se vecchia, «alla decisione», «deciso N s fa», approva spento su feed fermo/ignoto. Con `cashout` assente resta «—», come prima.

## 2. MEDIO - causa inventata nella striscia (`lib/certezzaChiusura.ts`)
- PRIMA: «…(2 annullate): la posizione è ANCORA APERTA, nessuna contropartita è stata trovata.»
- DOPO: «…(2 annullate): la posizione è ANCORA APERTA.» Stato ed esposizione invariati.

## 3. Test
- `PropostaUscitaMike.test.tsx`:
  - finto `cashout` reso completo come il vero `MikeCashout` (`{net:1.28, gross, base, complete:true, pct}`), senza cambiare nessuna asserzione;
  - 2 test nuovi: `complete:false` → nessuna cifra, testo «non calcolabile», «alla decisione» e approva invariati; `complete:true` → «+1,28 €» + «(calcolo del bot)».
- `certezzaChiusura.test.ts`: nel test esistente «CHIUSURA_FALLITA … rifiutata» ho aggiunto l'asserzione del motivo esatto, senza «contropartita». Nessun test citava la vecchia coda.
- **FUORI PERIMETRO, da approvare**: `components/mike/useMikeEventoAlMs.test.tsx` righe 49 e 60. Ai finti `cashout: { net }` ho aggiunto `complete: true`. Senza questo, 4 test diventano rossi: `complete === true` è la regola chiesta e il finto era più povero del vero. Il bot spinge sul canale l'intero `ev` (`service.py:6386-6392`), con `live.cashout.complete` (`engine.py:4144`). Nessuna asserzione cambiata. Se non va bene, l'alternativa è trattare come non calcolabile solo `complete === false` (l'assente mostrerebbe la cifra): più debole, e diverso da SchedaMike.

## 4. Falsificazioni (`falsifica_R_B2.cjs`, copie fuori dal repo, ripristino dalla copia, `git diff` identico dopo con `cmp`)
- R1: `cashCompleto = true` → rosso (1).
- R3: senza «(calcolo del bot)» → rosso (1).
- R4: coda «nessuna contropartita…» rimessa → rosso (1).
- R2 (guardia `cashCompleto &&` su `bloccabileOra`) → VERDE. Con `complete` falso il ramo della cifra non si monta, e `bloccabileOra` non entra nel contesto del clic. La guardia è ridondante: difesa in profondità, non osservabile a schermo.

## 5. Numeri
- Vitest mirato `--maxWorkers=2`: 10 file, 105 passati (PropostaUscitaMike, certezzaChiusura, B2GlossarioAuditCR, P13EsitiChiusura, StrisciaEsitoChiusura, EsitoAbbinamento.schede, useMikeEventoAlMs, Mike.fixA, SchedaMike, PosizioniChiuse).
- tsc: una volta alla fine, 0 errori.

## 6. Non verificato
L'app a schermo non l'ho vista.

## Verifica del coordinatore UI (admin-07), 30/09 20:35
- Giro 6 dell'albero integrato (tutti i blocchi + R_C, R_B2, R_T, R_B1): tsc 0 errori; vitest controlroom + trading + ControlRoom.test + lib toccate = 90 file, 1455 test verdi. R_G impilata dopo: test mirati di pagina/plancia/prova 185 verdi (tsc del giro 7 sul master + R1: vedi messaggio di consegna).
- La patch in QUESTA cartella e l INCREMENTALE della corsia; applica pulita sul master `d4b4f6b` (verificato con indice temporaneo). Ordine consigliato: R_C → R_B2 → R_T → R_B1 → R_G.
- Mutazione MIA: proposta di Mike con la cifra anche se `complete` e' falso -> 1 rosso. Nota: tocca i finti di `components/mike/useMikeEventoAlMs.test.tsx` (aggiunge `complete: true`, coerente col payload vero del servizio): file dell'altra sessione, segnalato.
