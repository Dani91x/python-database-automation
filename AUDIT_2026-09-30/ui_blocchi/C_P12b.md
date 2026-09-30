# C_P12b - Cash out della PARTITA montato nella scheda (blocco B12, parte b)

Delegato C_CASHOUT, 30/09/2026. Worktree:
`C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.claude\worktrees\agent-a4f88b994afb4b99a`
Base `1d058a7` (nessun merge dopo la regola del coordinatore). Patch CUMULATIVA `C_P12b.patch` (P11 + P12a + P12b).
Niente commit. P16 NON iniziato.

## File toccati SOLO da P12b

| File | Cosa |
|---|---|
| `components/controlroom/SchedaPartita.tsx` | 1 import (in fondo alle import `controlroom/`, riga 41) + 1 blocco JSX subito DOPO il blocco `{safe && (... <CashOutPartita/> ...)}`: `<CashOutGlobalePartita sport={p.sport} operazioni={operazioni} mike={mike} />`. Nient'altro (intestazione, `cr-calcio-vivo`, barra tennis, riga «resp.», riga «target» intatte) |
| `components/controlroom/useControlRoom.ts` (via libera) | tipo `OperazionePartita`: campo OPZIONALE `chiusureGambe?: { id; marketId; selectionId }[]`; in `agg` (~:3145) `chiusureGambe` dalle righe grezze `closes` (stesso ordine di `chiusureOrdini`). Nessun altro hunk nuovo |
| `components/controlroom/CashOutGlobale.tsx` | `CashOutGlobalePartita` (contesto -> sorgente al ms, Mike -> `dueEsiti`/`esitoDeciso`/cifra del bot); `ValoreBotCashOut.modalita`; cifra del bot con `complete === false` -> «non calcolabile» |
| `components/controlroom/useCashOutPartita.ts` | nessuna selezione da chiudere -> sorgente NON toccata |
| `lib/cashOutPartita.ts` | `dueEsitiMike`, `esitoDecisoMike`, `valoreBotMike`; robustezza su righe storiche senza `ordine`/`chiusureOrdini` |
| `components/controlroom/CashOutGlobale.montaggio.test.tsx` (NUOVO) | 6 test sulla `SchedaPartita` vera |
| `components/controlroom/useChiusuraAlMs.parita.test.tsx` | +1 test sul modello di vista VERO (Farul) |

## PRIMA -> DOPO a schermo (scheda live di Follo, dati di oggi)

PRIMA: «Cash out globale della partita · nessuna posizione viva del bot su questa partita» e nessuna cifra.

DOPO (sotto il pulsante):
```
[Cash out Safe] nessuna posizione viva di Safe su questa partita
CASH OUT DELLA PARTITA (SE CHIUDO TUTTO ADESSO)  −0,82 €  netto commissione  [STIMA · 0 s fa]
  Mike LIVE  punta Under 3.5 Goals 5,00 € @ 2,40   chiudo banca 4,69 € @ 2,56   −0,32 €   ladder al ms · 0,3 s fa
  Mike LIVE  banca Under 4.5 Goals 6,32 € @ 1,76   chiudo punta 6,82 € @ 1,63   −0,50 €   ladder al ms · 0,3 s fa
  il bot Mike calcola: −0,84 € [BOT · 1 s fa]  differenza 0,02 €: prezzi letti in istanti diversi (pagina 0,3 s fa, bot 1,2 s fa); il bot conta solo le gambe di Mike, sul suo book; una copertura in banca Under 4,5 la chiude bancando l'Over 4,5
```
Se Mike dichiara la sua cifra incompleta: «il bot Mike calcola: non calcolabile». Se un prezzo manca: «NON CALCOLABILE: manca il prezzo di ...» senza cifra. Gambe PROVA: blocco «Prova (simulato, mai sommato ai soldi veri)» [PROVA] sotto. Partita senza gambe abbinate: niente (nessun riquadro, nessuna sottoscrizione).

## Che cosa entra per Mike (dati gia' in pagina, nessuna lettura nuova)
- `dueEsiti`: i `market_id` di `MikeEvent.markets` (OU35/OU45) sono Over/Under -> due esiti (gambe sulle due selezioni nettate, chiave = selezione lunga, engine `_chiave_ou45` :795-798).
- `esitoDeciso`: `live.goals` > linea (3,5 / 4,5, engine `LINE` :35) -> Over VINTO, Under PERSO (engine `selection_decided` :666-677); Under/Over letto dal NOME della selezione della riga (`/\bunder\b/`, `/\bover\b/`); nome non riconosciuto -> resta in gioco (fail-closed).
- cifra del bot: `live.cashout.net`/`complete` + eta' `etaQuoteS(live)` (feed + tempo dalla pubblicazione, `lib/mike.ts:759`). In PROVA se `mike.mode` e' paper.
- Tennis: testa a testa a due esiti NON dichiarato (la riga non porta il tipo di mercato): per selezione, come prima.
- Scalper: resta «non scomponibile», dichiarato (domani).

## Test

- Nuovi: `CashOutGlobale.montaggio.test.tsx` 6 (Follo −0,82 + bot −0,84 [BOT] + pulsante «Cash out Safe» intatto; bot incompleto -> «non calcolabile»; nessuna gamba -> nessun riquadro e sorgente MAI chiamata; con gambe UNA sottoscrizione per mercato; 4 gol -> Under 3,5 persa senza prezzo, −8,75 = engine cert:303; Over+Under 4,5 stesso mercato -> una riga +1,81 = engine cert:164). `useChiusuraAlMs.parita.test.tsx` +1: `useControlRoom` vero, apertura 821 + chiusura 822 (`closes_trade_id`) -> `chiusureGambe = [{822, '1.2', 2}]`, cash out +0,05, una riga, nessun mancante.
- Esistenti cambiati in P12b: nessuno. (Tre test di `ControlRoom.test.tsx` erano diventati rossi al primo montaggio per righe costruite a mano senza `chiusureOrdini`: corretto nel CODICE (`?? []`), non nei test.)

## Falsificazioni (`falsifica_c_p12b.sh`, uscita `falsifica_c_p12b.out`)

| Mutazione | Rossi |
|---|---|
| F1 riquadro non montato | 5 |
| F2 senza `chiusureGambe` in `agg` | 1 (Farul +0,05 -> non calcolabile) |
| F3 Mike senza due esiti | 1 |
| F4 Mike senza esito deciso | 1 |
| F5 sorgente toccata anche senza gambe | 1 |
| F6 cifra del bot incompleta mostrata | 1 |
| F7 riquadro anche senza gambe | 1 |

Ripristino dalla copia fuori repo, `MUTAZIONE` = 0, `git diff --stat` identico prima/dopo (17 file, +1915 −23).

## Numeri
- `npx tsc -p tsconfig.app.json --noEmit` (test inclusi): 0 errori.
- Test mirati P12b: `npx vitest run src/components/controlroom/CashOutGlobale.montaggio.test.tsx src/components/controlroom/useChiusuraAlMs.parita.test.tsx src/components/controlroom/CashOutGlobale.test.tsx src/lib/cashOutPartita.test.ts --maxWorkers=2`: 50/50 verdi. `src/pages/ControlRoom.test.tsx`: 112/112.
- Fine blocco (cartella controlroom + lib + ControlRoom.test): vedi messaggio di consegna (in corso al momento della scrittura).

## COSA NON HO FATTO
- P16 (domani). Riga «target» non toccata (decisione rinviata). Scalper scomponibile (domani).
- Tennis a due esiti (manca il tipo di mercato sulla riga).
- `SchedaPreMatch.tsx` non toccata: una posizione pre-match NON mostra il riquadro finche' la scheda pre-match non riceve le `operazioni` (B10 di un altro delegato).
- Nessun `npm run build`.

## COSA NON HO POTUTO VERIFICARE
- L'app a schermo (non la vedo): impaginazione e a-capo del riquadro nella card stretta verificati solo dai testi nei test.
- Il carico reale: una sottoscrizione per mercato per ogni partita CON gambe (0 per le altre, verificato nel test); non misurato dal vivo.
- Che i nomi delle selezioni di Mike sulle righe contengano sempre «Under»/«Over» (oggi «Under 3.5 Goals»): se un nome non li contiene, dopo la linea superata la selezione resta «in gioco» e senza prezzo la cifra e' NON CALCOLABILE (fail-closed, non sbagliata).

## Verifica del coordinatore UI (admin-07), 30/09 19:05
- Quarto giro, albero integrato (`1d058a7` + B1bis + P13 + T_P4 + G_P7 + G_P8bis + C_P12b): `npx tsc -p tsconfig.app.json --noEmit` = 0 errori; `npx vitest run src/components/controlroom src/components/trading src/pages/ControlRoom.test.tsx` + 9 test di lib = 93 file, 1480 test verdi.
- La patch in QUESTA cartella e l INCREMENTALE ricavato da me sul master `f58b595` + B1bis + P13 + T_P4 + G_P7; ordine: `G_P8bis.patch` → `C_P12b.patch` (tre vie senza conflitti; file toccati identici byte per byte all albero verificato).
- Mutazioni MIE (oltre le 7 del delegato), ROSSE: linea superata dai gol con l Under dato per VINTO (1 rosso: caso 4 gol, −8,75); cifra di Mike sempre «completa» (1).
- Diff riletto: in `SchedaPartita.tsx` 1 import + 1 riga di montaggio dopo il blocco del pulsante Safe; in `useControlRoom.ts` il campo opzionale `chiusureGambe` e 1 riga in `agg`.
- Limiti dichiarati: la scheda PRE-MATCH non mostra il riquadro (non riceve le operazioni: blocco P10, domani); sessione scalper «non scomponibile»; tennis a due esiti non dichiarato; la guardia anti-doppio-clic sul «Confermo» del pulsante Safe arriva come aggiunta separata.
