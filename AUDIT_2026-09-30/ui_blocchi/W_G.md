# W_G - P6 (riquadro Obiettivo) + tessere sport (M3/M15/M2)

Worktree `C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.claude\worktrees\agent-ad6a40b65633ea777`.
Base: `d4b4f6b` (checkout --detach -f nel mio worktree) + `R_G_incr_lane.patch` (pulita). Backup del diff di prima: `G_backup_pre_W.patch`.
Patch: `AUDIT_2026-09-30/ui_blocchi/W_G.patch` = `git diff -- frontend/` (R_G + W_G). Nessun commit, nessun build.

## PRIMA -> DOPO nel riquadro Obiettivo (fatti di oggi: 0 ordini regolati sul conto, Follo -0,82, esposizione -9,95)
PRIMA: `Obiettivo di oggi 100,00 € · partite 28 · operazioni 0 · 0V 0P · 3 vive · in corso (stimato) -0,74 € · Liability aperta 39,15 €` e nessun numero grande (0 ordini); nota «obiettivo non ancora storicizzato ...».
DOPO:
```
+0,00 € · 0,0 %      [CONTO BETFAIR · 3 min fa] nessun ordine regolato oggi
Obiettivo di oggi 100,00 € · operazioni regolate oggi 0 · 0V 0P · 1 partita con posizione LIVE · Realizzato +0,00 €
 · aperto adesso (se chiudo tutto) −0,82 € [STIMA] su 1 partita (+ N partite non calcolabili, se ci sono)
 · rischio massimo −9,95 € [CONTO BETFAIR · 3 s fa] · resta ...
nota: Omega oggi non ha ancora girato: l'obiettivo e' quello corrente del servizio - programma dello scanner: 28 partite
barra: realizzato pieno + aperto TRATTEGGIATO (se positivo; con aperto negativo e realizzato 0 la barra resta a 0)
composizione: Mike ... · aperto −0,82 €
```
Conto non letto e nessuna riga: `—` + «conto non letto: P&L dalle righe dei bot»; rischio `—` + «conto non letto».

## Tessere sport
- LIVE dal CONTO quando letto (`perSportDalConto`): calcio = per_fonte mike+omega+safe_calcio+scalper, tennis = safe_tennis+bot_tennis; marchio CONTO con eta'; «N ordini regolati oggi» / «nessuna operazione regolata oggi». Conto non letto: righe dei bot con marchio BOT (come prima). Il difetto preesistente («differenza conto-righe» con sport calcio: una posizione Safe tennis di ieri regolata oggi finiva nel calcio) con questa regola SPARISCE (test dedicato). Le voci manuali (app/sito) e «altri bot» non hanno sport: restano nella composizione, fuori dalle tessere.
- «—»/«0,00»: letto e vuoto = `+0,00 €` + «nessuna operazione ... oggi»; non letto = `—` (regola gia' in vigore nelle tessere; testo non cambiato per non rompere F-3).
- «N aperte» -> «N partite con posizione LIVE» / «N partite con posizione in prova».

## Fonti
- realizzato: `pnl_reale_oggi` (conto, `fonteReale`), eta' `letto_at`; aperto: `lib/apertoAdesso.ts` = `cashOutPartita(gambeDaOperazioni(operazioni della partita))` per partita, prezzi dallo scanner gia' in memoria (`prezzoVivo` sul payload del feed, `odds_ts_ms`), Mike: `dueEsitiMike`/`esitoDecisoMike`; rischio: `vm.soldiVeri.conto` (la stessa cifra della testata); partite con posizione LIVE: `vm.soldiVeri.partite.live`.
- Memo dell'aperto: dipende da una FIRMA dei dati (righe LIVE, `updated_at` della riga del feed, partita di Mike), non da `nowMs` (`operazioni` cambia ogni secondo). Nessuna sottoscrizione nuova.

## File
- nuovi: `lib/apertoAdesso.ts` (+test 4), `components/controlroom/ObiettivoVoci.tsx` (voci aperto/rischio), `components/trading/DayBar.aperto.test.tsx` (3), `AUDIT_.../falsifica_W_G.ps1`
- toccati: `components/trading/DayBar.tsx` (SOLO opzionali: `realizedMissing`, `realizedNote`, `openNow`, `openNowNode`, `riskNode`, `liveLabel`; testid nuovi `day-bar-realizzato`, `-realizzato-nota`, `-aperto`, `-aperto-barra`, `-rischio`; default = comportamento di prima), `ObiettivoHero.tsx` (prop `apertoPerBot`, colonna «aperto» per voce `cr-composizione-<chiave>-aperto`), `SplitSport.tsx` (prop `perSportConto`/`contoEtaS`, etichette partite), `lib/composizioneConto.ts` (`perSportDalConto`), `useControlRoom.ts` (memo `firmaAperto`/`apertoOggi`; campi VM additivi `apertoAdesso`, `soldiGiornata.perSportConto`), `pages/ControlRoom.tsx` (blocco dayBar/ObiettivoHero/SplitSport + import).
- Test esistenti cambiati (`ControlRoom.test.tsx`): «obiettivo non storicizzato» (testo nuovo in parole da trader); «LE TESSERE: 2 aperte» (ora «1 partita con posizione LIVE / in prova»); «R_G: ... niente liability LORDA» (tolte le 2 asserzioni sulla nota «rischio adesso: vedi in testata», sostituita dal rischio del conto nel riquadro: nuovo test P6).
- Test nuovi: `ControlRoom.test.tsx` P6 ×3 (0 ordini -> +0,00 CONTO «nessun ordine regolato oggi · 3 min fa», aperto −0,82 su 1 partita STIMA, rischio −9,95 CONTO, aperto di Mike nella composizione, etichette; partita non calcolabile detta; conto non letto -> «—»); `SplitSport.corsie.test.tsx` +2; `composizioneConto.test.ts` +3; hook: identita' di `apertoAdesso` stabile nello stesso giorno.

## Falsificazioni (`falsifica_W_G.ps1`, ripristino da copia, 0 MUTAZIONE, diff --stat identico)
M1 aperto per RIGA (chiusure ignorate) -> rosso (dopo aver stretto il test Farul: la prima volta era SOPRAVVISSUTA, test corretto e rifatta); M2 non calcolabile taciuta -> rosso; M3 riquadro tace le non calcolabili -> rosso; M4 DayBar di serie cambiata -> rosso; M5 realizzato a 0 ordini invisibile -> rosso; M6 tessera LIVE dalle righe col conto -> rosso; M7 Safe tennis nel calcio -> 2 rossi; M8 aperto ricalcolato a ogni secondo -> rosso.

## Numeri
`npx vitest run src/pages/ControlRoom.test.tsx src/components/controlroom src/components/trading src/lib/composizioneObiettivo.test.ts src/lib/giornataCorsie.test.ts src/lib/provaGiornata.test.ts src/lib/composizioneConto.test.ts src/lib/apertoAdesso.test.ts src/pages/Mike.test.tsx src/pages/Omega src/pages/SafeStrategy --maxWorkers=2` = 101 file, 1504 verdi + 1 saltato (964 s): le pagine Mike/Omega/Safe che montano DayBar invariate. tsc = 0 (una volta, alla fine).

## COSA NON HO FATTO / NON VERIFICATO
- Aperto ai prezzi dello SCANNER, non al ms: le gambe su selezioni che lo scanner non porta (es. chiusura di Mike sull'Over 4,5) rendono la partita «non calcolabile» nel riquadro, mentre la scheda (ladder al ms) la calcola: dichiarato «+ N partite non calcolabili».
- Aperto per bot: cash out delle SOLE gambe di quel bot (commissione per mercato sul sottoinsieme): con due bot sulla stessa partita la somma per bot puo' differire di centesimi dal totale della partita.
- Aperto negativo con realizzato 0: la barra resta a 0 (nessun tratteggio visibile), la cifra e' comunque scritta.
- L'app a schermo non la vedo.
