# B1bis — referto breve (30/09/2026)

Worktree: `...\.claude\worktrees\agent-a32982190acf0f4b4` (base `4fcb867`). Patch CUMULATIVA B1+B1bis:
`AUDIT_2026-09-30/ui_blocchi/B1bis.patch` (10 file, solo `frontend/`, `git apply --check -R` = 0).
Niente commit, niente build. La zona di `CashOutPartita` in `SchedaPartita.tsx` NON e' toccata.

## Prima -> dopo
| punto | PRIMA (B1) | DOPO (B1bis) |
|---|---|---|
| 1. linee O/U > 4 (es. 0-0 in gioco, 8 linee) | nessuna linea in scheda | in vista: 3,5, 4,5 e ogni linea con `for_mike` o `decided`; tutte le altre in `<details>` chiuso «altre N linee» (stesse celle). Title del blocco con la regola scritta. Nessuna linea del payload resta fuori |
| 1. linee O/U 1-4 | tutte in vista | invariato |
| 1. guardia | doppia (`<= MAX_LINEE_OU` in `LineeOu` e in ciascuna scheda) | una sola, in `LineeOu` (tolta da `SchedaPreMatch.tsx` e `SchedaPartita.tsx`) |
| 2. tennis in gioco SENZA posizione | nessuna quota; `ultimo cambio: …` nella riga pulsanti | fila `cr-tennis-quote`: `[P1 1,50/1,52] [P2 2,60/2,66] ultimo cambio: 4 s` (scanner, stessa fonte della pre-partita); il `cr-latenza` sta li' (uno solo) |
| 2. tennis in gioco CON posizione | barra del runner | invariato: SOLO la barra, mai anche le quote dello scanner (stesso cancello `apertaLive || apertaPaper` della barra) |
| 3. nomi senza loghi | nessuno spazio a sinistra (-22 px rispetto alle righe con logo) | spazio `w-4` invisibile SEMPRE riservato (`aria-hidden`, niente bordo/fondo), come la pre-partita prima di B1 |

## File toccati in B1bis
`QuoteMercato.tsx` (`LINEE_BOT_OU`, `lineaInVista`, `LineeOu` con `<details>`, `RigaLineaOu` estratta), `NomiPartita.tsx`,
`SchedaPreMatch.tsx` (1 riga: guardia + import), `SchedaPartita.tsx` (calcolo `haLineeOu`/`barraTennis`/`celleTennis`/
`latenzaAccantoQuote`, fila tennis prima di `TennisVivoBar`, import), e i test di questi.
**Fuori dalla lista del brief B1bis, dichiarato**: `lib/controlRoom.ts` (+ campo `perMike` in `LineaOuScheda`, mappato da
`for_mike` del blocco) e `lib/controlRoom.test.ts`: senza questo il marker `for_mike` non arriva alla scheda.

## Test
Nuovi: controlRoom +1 (`for_mike`), QuoteMercato +1 (8 linee: 4 in vista, 4 nel riquadro chiuso, title), NomiPartita +1
(allineamento), SchedaPreMatch 0 nuovi (1 sostituito), SchedaPartita +4 (6 linee in gioco; tennis senza posizione;
tennis con posizione = una fonte; tennis non in gioco).
Test B1 cambiati per decisione del coordinatore (dichiarati, commento nel file):
- `QuoteMercato.test.tsx`: «nessuna linea, o più di 4: non si monta» -> «nessuna linea non si monta; fino a 4 tutte in vista, nessun riquadro».
- `SchedaPreMatch.test.tsx`: «più di quattro linee: non si mostrano» -> «si mostrano tutte, 3,5 e 4,5 in vista, le altre nel riquadro».
- `NomiPartita.test.tsx` (quello falsificato da M7): «senza loghi: nessun segnaposto» -> «spazio riservato e INVISIBILE» (2 spazi `w-4`, niente bordo/fondo, `aria-hidden`, vuoti).
- `controlRoom.test.ts`: l'oggetto atteso di `lineeOuScheda` ha in piu' `perMike: false`; i finti delle linee nei test di scheda hanno `perMike`.
Rossi prima del codice: 8 (i due casi «tennis con posizione» e «tennis non in gioco» erano gia' veri: falsificati da N8/N9).

Falsificazioni (`falsifica_b1bis.ps1`, copia fuori dal repo, `try/finally`, hash identico, `git diff` identico prima/dopo):
N1 `for_mike` ignorato ROSSO · N2 `decided` ignorato ROSSO · N3 4,5 non in vista ROSSO · N4 linee oltre la vista buttate ROSSO ·
N5 riquadro aperto di default ROSSO · N6 `for_mike` non mappato ROSSO · N7 spazio logo non riservato ROSSO (3) ·
N8 due fonti tennis insieme ROSSO · N9 quote scanner a partita non in gioco ROSSO · N10 eta' tennis doppia ROSSO ·
N11 guardia <=4 in gioco ROSSO · N12 guardia <=4 in pre-partita ROSSO.

Numeri: `npx tsc -p tsconfig.app.json --noEmit` = 0; mirati (`--maxWorkers=2`, 5 file) 154/154;
allargato (`--maxWorkers=2 src/components/controlroom src/pages/ControlRoom.test.tsx src/components/trading/StatoOrdine.montaggio.test.tsx src/lib/flussoLineeMike.test.tsx src/lib/controlRoom.test.ts`) **58 file, 983/983**.

## Non verificato / note
- App a schermo non vista (jsdom). Da guardare: il `<summary>` «altre N linee» sullo sfondo scuro, l'altezza della scheda in gioco con 3,5/4,5 + riquadro.
- Tennis con posizione: il `cr-latenza` della riga pulsanti resta l'eta' delle quote dello SCANNER mentre le quote a schermo sono quelle del RUNNER (situazione di prima, non cambiata): da decidere se nasconderlo o rietichettarlo.
- Tennis senza posizione: P1/P2 restano etichette posizionali (nessun legame dimostrato fra `sortPriority` e l'ordine dei nomi).

## Verifica del coordinatore UI (admin-07), 30/09 18:55
- Terzo giro, albero integrato (`1d058a7` + C_P12a + B1bis + P13 + T_P4 + G_P7): `npx tsc -p tsconfig.app.json --noEmit` = 0 errori; `npx vitest run src/components/controlroom src/components/trading src/pages/ControlRoom.test.tsx` + 9 test di lib toccati = 91 file, 1478 test verdi.
- La patch in QUESTA cartella e l INCREMENTALE ricavato da me sul master `f58b595`; ordine di applicazione: `B1bis.patch` → `P13_ESITI_CHIUSURA.patch` → `T_P4.patch` → `G_P7.patch` (fusione a tre vie senza conflitti; su ogni file toccato il risultato e identico byte per byte all albero verificato).
- Mutazioni MIE (oltre le 12 del delegato), ROSSE, ripristino da copia: nel riquadro «altre linee» finiscono le linee gia in vista (3 rossi); tennis, P1 mostra i prezzi di P2 (2).
