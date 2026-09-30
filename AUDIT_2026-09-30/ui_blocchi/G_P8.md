# G_P8 - Corsia PROVA: partite di OGGI contro ARRETRATI regolati oggi (blocco B8)

**DIPENDENZE: richiede (1) la migrazione `migrations/mike_state_arretrati_prova_2026-09-30.sql` APPLICATA, (2) `fetchMikeState` che inoltra `arretrati_prova` (commit `eee6a7c` su master; il mio worktree resta sulla base `1d058a7` per ordine del coordinatore). Senza una delle due la pagina scrive «arretrati di Mike: non letti».**

Worktree: `C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.claude\worktrees\agent-ad6a40b65633ea777`
Patch: `AUDIT_2026-09-30/ui_blocchi/G_P8.patch` = diff CUMULATIVO di `frontend/` rispetto a `1d058a7` (P2 + test P2 + P8). Nessun commit.

Lettura della chiave: `frontend/src/components/controlroom/useControlRoom.ts:2208` `(mike as { arretrati_prova?: unknown } | null)?.arretrati_prova` (accesso tipizzato largo: compila sia col tipo `MikeStateView` senza la chiave sia con `arretrati_prova?: unknown` di master), validata da `lib/provaGiornata.ts::leggiArretratiProva` (giorno = oggi, righe con id numerico, status e placed_at stringa; altrimenti `null` = «non letti»).

## Regola applicata (decisione del coordinatore)
- PROVA «oggi» = cicli paper CHIUSI con l'ultima gamba regolata oggi (stessa regola F-2 del ciclo, `righeGiornataPerCiclo`, riusata ciclo per ciclo) E partita di OGGI.
- Giorno della partita: `kickoff` (Omega) o `ko_at` (arretrati di Mike dal backend) -> etichetta «N partite del GG/MM»; altrimenti giorno di piazzamento dell'APERTURA (Safe, Mike dalle righe normali: le tabelle non hanno una colonna col fischio, verificato sul DB) -> «N operazioni aperte il GG/MM». Due origini = due righe, mai fuse.
- ARRETRATI = partite di giorni precedenti regolate oggi: righe a parte, con data, MAI dentro le cifre di oggi e mai sommati fra origini diverse.
- LIVE invariato (giorno di regolamento del conto).
- Bot tennis in prova: la RPC `get_tennis_bot_daily` e' aggregata per giorno di REGOLAMENTO senza giorno partita: restano in «oggi» e lo schermo lo DICE nella corsia PROVA del tennis («per giorno di regolamento»).
- Scalper calcio paper: fuori come prima (il bot dichiara solo un lordo).

## PRIMA -> DOPO a schermo (fatti di oggi)
PRIMA:
```
(riga sotto l'obiettivo) in prova +7,60 EUR su 4 operazioni simulate — non entra nell'obiettivo
(composizione)            in prova +7,60 EUR — mai sommato all'obiettivo
(tessera calcio)          MODALITA' PAPER ... +7,60 EUR 4 operazioni 4 V 0 P 100 %
(Mike -18,29: assente ovunque)
```
DOPO (migrazione applicata):
```
(composizione) IN PROVA (SIMULATO) — mai sommato all'obiettivo; gli arretrati mai sommati a oggi
  bot                partite di oggi     arretrati regolati oggi
  Omega              +0,00 € [PROVA]     nessuno
  Safe calcio        +0,00 € [PROVA]     +7,60 € (4 operazioni aperte il 26/09)
  Mike               +0,00 € [PROVA]     −18,29 € (2 partite del 26/09)
  Safe tennis        +0,00 € [PROVA]     nessuno
  Bot tennis (...)   +0,00 € [PROVA]     per giorno di regolamento: non separabili
(tessera calcio, corsia PROVA)  PARTITE DI OGGI +0,00 € [PROVA] nessuna operazione in prova oggi
  arretrati regolati oggi +7,60 € [PROVA] (4 operazioni aperte il 26/09) — fuori dalle cifre di oggi
  arretrati regolati oggi −18,29 € [PROVA] (2 partite del 26/09) — fuori dalle cifre di oggi
(tessera tennis, corsia PROVA)  ... Bot tennis (Scalper · Pro · FLB · Swing): per giorno di regolamento (la fonte non porta il giorno della partita)
```
Migrazione NON applicata: al posto della riga di Mike «arretrati di Mike: non letti» (composizione e tessera, in ambra). Nessun totale -10,69 da nessuna parte.

## Fonte di ogni cifra
- Righe Safe: `get_safe_state` (ultime 200 righe paper+live, `safe_strategy_paper_live_2026-09-13.sql`); Omega: `get_omega_trades` (500) con `kickoff`; Mike oggi: `get_mike_state.trades` (piazzate oggi o aperte); Mike arretrati: `get_mike_state.arretrati_prova` (SQL `mike_state_arretrati_prova_2026-09-30.sql`: righe paper regolate oggi con giorno(coalesce(ko_at, placed_at apertura)) < oggi, tutte le gambe, LIMIT 2000); bot tennis: `get_tennis_bot_daily(p_mode='paper')`.
- Calcolo: `lib/provaGiornata.ts` (`provaPerGiornoPartita`, `provaGiornata`), montato in `useControlRoom.ts` (`provaOggi`).

## File
- nuovi: `frontend/src/lib/provaGiornata.ts`, `frontend/src/lib/provaGiornata.test.ts`, `frontend/src/components/controlroom/useControlRoom.provaGiornata.test.tsx`, `AUDIT_2026-09-30/ui_blocchi/falsifica_G_P8.ps1`
- toccati dal solo P8: `useControlRoom.ts` (import; `provaOggi` accanto a `composizioneOggi`; `perSportPaper` = partite di oggi; campo VM nuovo `provaGiornata`; dipendenze del memo), `SplitSport.tsx` (prop `prova`, `ArretratiSport`, etichetta «partite di oggi»), `ObiettivoHero.tsx` (prop `prova`, `CorsiaProva`; senza prop resta la riga di prima), `ObiettivoHero.test.tsx` (+1), `ControlRoom.tsx` (tolta la riga `cr-riga-paper`, `prova=` a Obiettivo e tessere), `ControlRoom.test.tsx`.
- Campi nuovi del VM: `provaGiornata?: ProvaGiornata | null`. Significato CAMBIATO (dichiarato): `soldiGiornata.perSportPaper` = sole partite di OGGI (prima: giorno di regolamento, F-2 del 26/09). `realizzatoPaper`/`operazioniPaper` INVARIATI (non piu' mostrati dalla pagina).
- testid TOLTO: `cr-riga-paper` (riga duplicata della composizione, chiesta dal progetto §2.C). Test che la cercavano: `ControlRoom.test.tsx` «la BARRA dell'obiettivo porta i soldi veri, e il paper ha una riga sua» (ora verifica che non esista e che la prova stia nella corsia PROVA della tessera, fuori dalla barra) e «senza niente in prova non compare nessuna riga della prova» (invariato, resta verde). Nuovi: `cr-prova-<voce>`, `-oggi`, `-arretrati`, `-fonte`, `cr-sport-<s>-arretrati`, `-arretrati-fonte`, `-arretrati-non-letti`, `-per-regolamento`. `cr-composizione-prova` conservato (contenitore della corsia).

## Test
- `npx tsc -p tsconfig.app.json --noEmit` = 0 errori.
- `npx vitest run src/pages/ControlRoom.test.tsx src/components/controlroom src/components/trading src/lib/composizioneObiettivo.test.ts src/lib/giornataCorsie.test.ts src/lib/provaGiornata.test.ts --maxWorkers=2` = 75 file, 1109 test verdi (637 s). DayBar non toccata in P8.
- nuovi: `provaGiornata.test.ts` (9: Safe del 26/09 = arretrati; partita di oggi resta oggi; Omega dal fischio; caso vero con chiave piena -> Safe +7,60 «aperte il 26/09» e Mike −18,29 «partite del 26/09» in due gruppi; chiave assente = non letti; `righe: []` = nessun arretrato; chiave di altro giorno/malformata = non letti; tennis per regolamento; bot non letto = null), `useControlRoom.provaGiornata.test.tsx` (4, hook vero con i finti di `useControlRoom.test.tsx`: tessera PROVA 0,00 con gli arretrati; chiave piena; `righe: []`; partita di oggi), `ControlRoom.test.tsx` +2 («P8: la prova di OGGI e' 0,00 ...», «P8: arretrati di Mike non letti ...»), `ObiettivoHero.test.tsx` +1.
- esistenti cambiati: `ControlRoom.test.tsx` test «la BARRA dell'obiettivo porta i soldi veri...»: le 3 righe su `cr-riga-paper` sostituite (motivo: riga tolta); l'asserzione sulla barra invariata, la prova ora cercata nella corsia PROVA della tessera e verificata FUORI dalla barra.
- Falsificazioni (script `falsifica_G_P8.ps1`, copie in scratchpad, ripristino in `finally`, 0 `MUTAZIONE`, `git diff --stat` identico):
  - M1 tutto in «oggi» (la regola del 26/09) -> 8 rossi;
  - M2 chiave assente = `[]` (silenzio) -> 2 rossi;
  - M3 fusione di origini diverse -> 2 rossi;
  - M4 la tessera tace i «non letti» -> 1 rosso (pagina).

## COSA NON HO FATTO
- Omega/Safe: nessun limite di lettura cambiato (Safe 200 righe, Omega 500): in una giornata con piu' di 200 righe Safe gli arretrati piu' vecchi potrebbero mancare; oggi non succede.
- La plancia bot (`righeInterruttori`, `pnlOggiPaper` per bot da `pnlChiuseDelGiorno`) e le «Posizioni chiuse» restano per giorno di REGOLAMENTO: la riga di Safe nella plancia puo' ancora dire +7,60 in prova. Fuori dal mio perimetro (`righeBot`, `posizioniChiuse`): da decidere se allinearle.
- Tennis bot: arretrati non separabili (servirebbe il giorno partita nella RPC).
## COSA NON HO POTUTO VERIFICARE
- L'app a schermo. La migrazione non e' applicata: il ramo «chiave presente» e' verificato solo con i finti (forma copiata dal SQL).

## Verifica del coordinatore UI (admin-07), 30/09 18:30
- Albero di verifica integrato (`1d058a7` + C_P12a + B1 + B2 + T_P3 + G_P8, fusione a tre vie senza conflitti): `npx tsc -p tsconfig.app.json --noEmit` = 0 errori; `npx vitest run src/components/controlroom src/components/trading src/pages/ControlRoom.test.tsx` + test di lib toccati = 87 file, 1379 test verdi.
- Sul master `96a2189` (worktree di integrazione) lo stack G_P2 → G_P2_test → B1 → B2 → T_P3 → C_P12a → G_P8 produce, su ogni file toccato, lo STESSO contenuto byte per byte dell albero verificato.
- ATTENZIONE: `G_P8.patch` in QUESTA cartella e l INCREMENTALE ricavato da me (G_P2 e il suo test sono patch a parte): 9 file; si applica dopo C_P12a.
- Mutazioni MIE (oltre le 4 del delegato), ROSSE, ripristino da copia: righe LIVE contate nella prova (1 rosso); chiave degli arretrati di un ALTRO giorno accettata (1); arretrati di Mike contati dentro «oggi» (2).
- Significato cambiato e dichiarato: `soldiGiornata.perSportPaper` = sole partite di oggi (prima: giorno di regolamento, regola F-2 del 26/09). Tolto il testid `cr-riga-paper` (riga duplicata).
- Residui: la PLANCIA dei bot mostra ancora la prova per giorno di regolamento (Safe «+7,60»): in corso come P8bis. Un ciclo paper chiuso oggi su una partita con fischio DOMANI finirebbe fra gli «arretrati» (la regola e «giorno diverso da oggi»): rimandato al delegato.
- Finche la migrazione `mike_state_arretrati_prova_2026-09-30.sql` non e applicata, la riga di Mike dice «arretrati di Mike: non letti».
