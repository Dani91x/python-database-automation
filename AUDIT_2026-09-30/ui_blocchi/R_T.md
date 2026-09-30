# R_T - review finale della testata: 3 reperti + riga tennis/scalper

Worktree: `C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.claude\worktrees\agent-a4993b702a303cacc`, base `1d058a7`, nessun commit.
Patch CUMULATIVA di `frontend/`: `AUDIT_2026-09-30/ui_blocchi/R_T.patch` (`git apply --check -R` OK).

## PRIMA -> DOPO

1. **Omega «scattato» fisso a false.** Prima: `Omega PAPER −300,00 €`, come se lo stop fosse armato. Dopo: `Omega PAPER −300,00 € scatto non pubblicato` (grigio), col title «Omega non pubblica se il suo stop e' scattato (lo scrive solo nella sua attivita'): la soglia c'e', lo stato no».
   - Lo stato dello scatto di Omega NON e' nel VM: il servizio scrive solo l'attivita' `loss_stop` (`omega_service.py:1850-1851` e `:2370-2373`), senza una chiave in `stats`.
   - Nuovo campo `StopBot.scattoPubblicato`: false per Omega, true per Safe (`stats.risk.loss_stop_active`) e per Mike (`stats.daily_stop`).
2. **«Conto: SPENTO» in grigio tenue con soldi veri in gioco.** Dopo: ambra (`text-amber-300`) se almeno un bot di `vm.bots` ha `modalita === 'live'`, acceso o fermo; grigio se tutti sono in paper. Il testo resta «SPENTO».
   - Il dato arriva col nuovo prop `qualcheBotLive` di `StopPerdita`, passato da `Freni` in `ControlRoom.tsx`: copre anche tennis e scalper.
   - Se il prop manca, si guardano i tre bot con stop.
3. **Rischio dei bot stantio visibile solo nel tooltip.** Dopo: sotto la cifra, in ambra, `dato del bot non aggiornato (Mike)` (testid `cr-rischio-bot-stantio`). Compare quando il servizio dichiara `liability_stale` e la voce e' inclusa nella somma. Nuovo campo `VoceRischio.stantio`.
4. **(un hunk in piu')** In coda agli stop, in grigio: `Tennis, Scalper: stop proprio non pubblicato` (testid `cr-stop-altri`), mai «nessuno stop».

## File

- `testata/stopPerdita.ts`
- `testata/FasciaStop.tsx`
- `testata/soldiVeri.ts`
- `testata/FasciaSoldiVeri.tsx`
- `testata/FasciaStop.test.tsx` (+5 test)
- `testata/FasciaSoldiVeri.test.tsx` (+2 test)
- `pages/ControlRoom.tsx`: solo `Freni` riceve e passa `qualcheBotLive` (2 righe). Non era nell'elenco del perimetro, ma serve al punto 2 perche' tennis e scalper non sono in `stop.bot`.
- `useControlRoom.ts` non toccato.

## Test

- `npx vitest run src/components/controlroom/testata --maxWorkers=2`: 4 file, 65 test verdi.
- `npx vitest run src/pages/ControlRoom.test.tsx --maxWorkers=2`: 117 test verdi.
- `npx tsc -p tsconfig.app.json --noEmit`: 0 errori (una volta, alla fine).
- Nessun carattere non ASCII nei file di `testata/`.

## Falsificazioni (`T_falsificazioni/mut_rt.json`, copia -> mutazione -> ripristino con hash; `git diff --stat` identico prima e dopo)

| Mutazione | Esito |
|---|---|
| RT-1 Omega di nuovo presentato come armato | ROSSO 1 |
| RT-2 conto SPENTO grigio anche con bot LIVE | ROSSO 2 |
| RT-3 l'ambra ignora i bot fuori dai tre | ROSSO 1 |
| RT-4 stantio di nuovo solo nel tooltip | ROSSO 1 |
| RT-5 stantio non propagato dal modulo puro | ROSSO 1 |
| RT-6 la riga tennis/scalper dice «nessuno stop» | ROSSO 1 |

## Non verificato

- L'app a schermo: larghezza della riga degli stop con le due scritte in piu'.
- Che stasera `liability_stale` di Mike sia davvero `true` a bot fermo: nella SQL vale `heartbeat_at` piu' vecchio di 60 s (`mike_aggregati_per_modalita_2026-09-13.sql:90-92`). Se Mike fermo continua a battere, non comparira'.

## Verifica del coordinatore UI (admin-07), 30/09 20:35
- Giro 6 dell'albero integrato (tutti i blocchi + R_C, R_B2, R_T, R_B1): tsc 0 errori; vitest controlroom + trading + ControlRoom.test + lib toccate = 90 file, 1455 test verdi. R_G impilata dopo: test mirati di pagina/plancia/prova 185 verdi (tsc del giro 7 sul master + R1: vedi messaggio di consegna).
- La patch in QUESTA cartella e l INCREMENTALE della corsia; applica pulita sul master `d4b4f6b` (verificato con indice temporaneo). Ordine consigliato: R_C → R_B2 → R_T → R_B1 → R_G.
- Mutazione MIA: «Conto: SPENTO» grigio anche con un bot LIVE -> 2 rossi.
