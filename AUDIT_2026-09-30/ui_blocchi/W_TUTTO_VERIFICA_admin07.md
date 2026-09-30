# W_* — seconda ondata UI, verifica del coordinatore (admin-07), 30/09 ore 21:40

Consegna ad `admin-bc` per la fusione F2. UNA patch: `W_TUTTO_su_2a5cbba.patch`
(55 file, +3201/−245, tutti in `frontend/src`), ricavata da `scratchpad/integra` = master
`2a5cbba` + le sei corsie impilate in quest'ordine con `git apply --3way`:
W_C → W_T_P15 → W_B1 → W_G → W_B2 → W_T_P14 (incrementali di corsia allegati per
riferimento: `W_*_incr.patch`; NON vanno riapplicati, la cumulativa li contiene gia').
`git apply --check` pulita su `2a5cbba` con indice temporaneo. md5 della patch: 68ab9fe9a1d8.

## Cosa contiene (referti dei delegati: `W_C.md`, `W_T.md`, `W_B1.md`, `W_G.md`, `W_B2.md`)
- **W_C** chiudi TUTTE le gambe della partita: `pianoChiusuraPartita` + `await api.chiudi` in
  sequenza, guardia `troppoPresto`; `moMarketId` alla scheda.
- **W_T_P15** posizioni aperte: sezioni LIVE (sopra) / PROVA; stato per partita
  A RISCHIO / PAREGGIATA / DA REGOLARE / NON CALCOLABILE da `aperte/statoPartitaAperta.ts`
  (`cashOutPartita` senza prezzi); testata «N partite con posizione LIVE (M gambe)».
- **W_B1** scheda pre-match con ordini pre-fischio + `CashOutGlobalePartita` + `SchedaMike`;
  barra tennis: eta' delle quote = LETTURA del runner (`state.updated_ms`, verificato
  `tennis_runner.py:1498-1501`), grigia ≤ 20 s; nota «spread N tick · poco liquido» (> 5 tick);
  nomi dei tennisti al posto di P1/P2.
- **W_G** Obiettivo P6: realizzato dal CONTO sempre visibile; «aperto adesso (se chiudo tutto)»
  = somma PER PARTITA del cash out LIVE ai prezzi dello scanner (`lib/apertoAdesso.ts`) con
  marchio STIMA e «+ N partite non calcolabili»; rischio massimo = `soldiVeri.conto` [CONTO];
  tessere: corsia LIVE dal conto (`per_fonte`: calcio = mike+omega+safe_calcio+scalper,
  tennis = safe_tennis+bot_tennis; manuali/altri bot fuori, e lo dice nel dettaglio).
  `DayBar`: solo prop opzionali (pagine Mike/Omega/Safe invariate senza).
- **W_B2** `esitoOrdineMeta` con i motivi REALI di Omega (prefisso `flumine_` tolto) e Safe;
  liability delle righe «(lorda)» e «Liability aperta (netta)» solo con Mike LIVE;
  `PannelloBot` parole da `botStatusMeta`; plancia: cifra LIVE di oggi da `per_fonte[bot]`
  [CONTO] quando il conto e' letto, altrimenti righe [BOT]; hunk PNL_REALE di admin-bc
  (`DettaglioRigaView`, `PosizioniChiuse`, `useControlRoom`) applicati.
- **W_T_P14** ordini del conto fuori dai bot per partita: `fetchLiveOrdersAccountOpen()` nel giro
  dei 30 s di `ricarica` + dopo ogni clic di chiusura (nessun poll nuovo); RPC assente/errore =
  «ordini del conto: non letti (motivo)», MAI lista vuota; `price_matched` null = «non abbinato»;
  «aperto per il conto letto alle HH:MM:SS»; scheda tennis: niente da questa fonte.

## Verifica mia (non sul referto dei delegati)
| Cosa | Esito |
|---|---|
| tsc `tsconfig.app.json` sull'insieme | 0 errori |
| vitest `components/controlroom` + `components/trading` + `pages/ControlRoom.test.tsx` + `src/lib` | 220 file / 3712 test verdi, 0 rossi (21:39) |
| Mutazioni mie, ripristino da copia + `cmp` | W_B1: eta' tennis dal punteggio → 2 rossi; soglia spread `>=` → rosso; guardia `operazioni.length > 0` → equivalente (`CashOutGlobalePartita` torna gia' null). W_G: scalper nel tennis → rosso; somma dei cash out incompleti → equivalente (netto gia' null); PROVA dal conto → equivalente (`conto` arriva solo alla corsia LIVE). W_B2: plancia sempre «vuoto» → rosso; `cancelled_by_engine` → ERRORE → rosso (`P13EsitiChiusura.test`). W_T_P14: guardia tennis tolta → rosso; `price_matched` null trattato come 0 → rosso. |
| Motivi Omega/Safe mappati in `tradeStatus.ts` | 14 stringhe cercate nei `.py`: tutte presenti |
| `per_fonte` del backend | `reconcile_worker.py:908`: ogni chiave dichiarata sempre (0 = zero, non assente) |
| `integra` vs albero di verifica `verifica-ui` | differiscono SOLO per i 24 file dei commit frontend di admin-bc (diff identico file per file a `1d058a7..2a5cbba`) |

## Reperto trovato e corretto da me
`aperte/statoPartitaAperta.ts` (W_T_P15) costruiva il title con `toFixed(2)` e «EUR»:
`designGuard.test.ts` rosso (DESIGN_SYSTEM §1: un solo formato del denaro). Il delegato non
aveva lanciato `components/trading`. Corretto: `fmtMoney(x, { signed: true })` (3 righe +
import), test allineati (`statoPartitaAperta.test.ts`, `ControlRoom.test.tsx:2003`:
«caso peggiore −9,80 €»).

## Conflitti risolti a mano (2)
- `useControlRoom.ts` import (W_G vs W_B2): tenuti entrambi, un solo import da `composizioneConto`.
- `SchedaPartita.tsx` (W_C `moMarketId={p.marketId}` vs W_T_P14 `<OrdiniContoPartita …/>`): tenuti entrambi.

## Fuori dal dominio dichiarato (avviso)
- `lib/liveOrders.ts`: SOLO aggiunte (tipo `OrdineContoFuoriBot` + `fetchLiveOrdersAccountOpen`, 39 righe).
- `SchedaMike.tsx`: 8 righe (liability netta + marchio BOT). Il blocco Mike di admin-bc si fonde DOPO.

## Decisioni per l'utente (non cambiate di iniziativa)
- «PAREGGIATA» in Posizioni aperte = nessun esito perde (caso peggiore ≥ 0): Farul (+0,04/+0,06)
  e' PAREGGIATA anche se in verde su tutti gli esiti. Alternativa: «IN VERDE» quando il caso
  peggiore e' > 0.
- Nella plancia la cifra LIVE del bot e' il solo REGOLATO del conto (senza la parte stimata che
  la composizione dell'Obiettivo aggiunge); si allinea con una riga se l'utente lo vuole.

## Non verificato
- App a schermo. RPC `get_live_orders_account_open` chiamata davvero dal frontend (solo finti
  nella forma del contratto). Test di velocita' `PosizioniChiuse.raggruppamento` sotto carico.
