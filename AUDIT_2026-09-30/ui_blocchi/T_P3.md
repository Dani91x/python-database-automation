# T_P3 - Fascia "SOLDI VERI ADESSO" nella testata della Control Room (B3)

Worktree: `C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.claude\worktrees\agent-a4993b702a303cacc`
Base: master `1d058a7` (ff-only da `35e1499` su ordine del coordinatore). Nessun commit.
Patch: `AUDIT_2026-09-30/ui_blocchi/T_P3.patch` (= `git diff -- frontend/`, file nuovi con `git add -N`;
`git apply --check -R` OK).

## 1. PRIMA -> DOPO a schermo (testata, `data-testid="cr-testata"`)

| Prima | Dopo |
|---|---|
| `ESPOSIZIONE 39,15 €` (+ nota `+ X € in prova, non sono soldi veri`) - somma LORDA per riga | `ESPOSIZIONE CONTO −9,95 €` con `[CONTO BETFAIR · 3 s fa]`; se il dato viene dalla riga del database anche `ultimo cambio`; se la regola della card lo dice `non verificato di recente` (arancione). Conto mai letto: `—` + `[CONTO BETFAIR] conto non letto` (arancione), nessuna cifra |
| (assente) | `DISPONIBILE 30,61 €` `[CONTO BETFAIR]` - solo se il conto e' letto; con l'occhio della card chiuso: `••••,•• €` (anche l'esposizione) |
| (assente) | `RISCHIO SECONDO I BOT −16,22 €` `[BOT · 7 s fa]` `solo LIVE, per partita`; se un bot con posizioni LIVE non dichiara il rischio live separato: `stima parziale: manca Mike` (ambra); righe non lette: `—` `posizioni non ancora lette`. Tooltip: una voce per bot (`Mike: 16,22 € su 5 posizioni LIVE; Omega: 0,00 €; Safe: 0,00 €`) |
| (assente) | `CONTO E BOT  NON TORNANO: 6,27 €` `[STIMA]` `il conto rischia meno dei bot` (ambra) - solo se conto letto, rischio dei bot completo e differenza > 0,01 €. Tooltip: «possono esserci ordini fuori dai bot o bot non allineati. Controlla le posizioni sul conto.» (nessuna causa affermata) |
| `CON POSIZIONE 3 / 28` (+ `N in prova`) | `POSIZIONI LIVE 3 partite` e sotto, piccolo: `in prova N · programma scanner 28` (il 28 non e' piu' un denominatore) |

Il rischio dei bot e' scritto col segno del conto (perdita massima = negativo) perche' le due cifre si
leggano nello stesso verso; lo scarto e' un valore assoluto con il verso detto a parole.
Nessuna cifra in euro senza `MarchioSoldi` (conto / bot / stima).

## 2. Fonte di ogni cifra

| Cifra | Fonte |
|---|---|
| Esposizione, disponibile | `betfair_live_account.exposure/available` (getAccountFunds: `Betfair/stream/reconcile_worker.py:140-179`, write-on-change) GIA' in memoria del hook (`useControlRoom.ts` effetto «conto Betfair (R4)», `fetchLiveAccount`/`subscribeLiveAccount` `lib/liveOrders.ts:940/:966`) + topic `account` dei canali `CANALI_SALDO` (calcio, tennis, mike, omega, safe; `reconcile_worker.py:161-167` `{available, exposure, checked_at}` e `stream/saldo_evento.py`). Regola: `saldoDaMostrare` (`lib/saldoBetfair.ts:155`, vince l'istante piu' recente) e `statoSaldoBetfair` (`:33`, eta' del battito del runner = `vm.runner.ageS`, stessa notizia di `betfair_live_heartbeat.ts` della card) |
| Eta' del conto | `checked_at` del canale (ultimo CONTROLLO) oppure `updated_at` della riga (ultimo CAMBIO, detto a schermo) |
| Rischio secondo i bot | `aggregates.open_liability` dichiarato LIVE dal servizio (`testata/soldiVeri.ts::liabilityLiveDichiarata`): Omega `aggregates_by_mode.live` (`migrations/omega_state_per_modalita_2026-09-26.sql:106`); Mike `aggregates` con `mode='live'` (`migrations/mike_aggregati_per_modalita_2026-09-13.sql:76-109`: somma di `mike_events.live.liability` NETTA, filtro modalita'); Safe `get_safe_state()` SENZA `p_mode` = `mode: null`, tutte le modalita' (`migrations/safe_strategy_paper_live_2026-09-13.sql:255/:447`): usato solo se Safe non ha posizioni paper aperte. Aggregato paper = mai rischio vero. Bot con posizioni LIVE senza liability dichiarata (anche i 4 tennis e lo scalper, che non ne pubblicano) = "non incluso", somma parziale detta a schermo |
| Eta' del rischio dei bot | `lettoAlle` (ultimo giro del database della pagina) |
| Scarto | calcolo della pagina: `|esposizione| − rischio bot`, `scartoContoBot` (`testata/soldiVeri.ts`) |
| Partite con posizione | `vm.posizioni` (aperture non regolate, gambe di chiusura escluse), partite DISTINTE per modalita' (`partiteConPosizione`) |
| Programma dello scanner | `totali.partite` (`lib/controlRoom.ts::totaliGiornata`, righe di `safe_strategy_scan`) - invariato |

## 3. Velocita': nessuna lettura nuova, `SaldoBetfairCard` NON montata due volte

- `SaldoBetfairCard` e' autosufficiente e apre per ogni montaggio: 1 fetch + 1 realtime di
  `betfair_live_account`, 1 fetch + 1 realtime di `betfair_live_heartbeat`, 5 ascolti `account`.
  Non l'ho montata una seconda volta.
- `useControlRoom` aveva GIA' la riga del conto (`liveAccount`, fetch + realtime propri, preesistenti).
  P3 la riusa; aggiunge SOLO 5 ascolti in memoria (`subscribe('account')`) sui canali singleton gia'
  aperti dalla pagina: nessuna porta nuova, nessuna query, nessun poll. Test: `fetchLiveAccount` e
  `subscribeLiveAccount` restano chiamate UNA volta (falsificato, M6).
- Proposta (NON fatta, fuori perimetro: `SaldoBetfairCard.tsx`): la card potrebbe ricevere dal hook
  `liveAccount`/`saldoCanale` via `deps` e togliere il suo doppio realtime della stessa riga.

## 4. File

Toccati: `frontend/src/pages/ControlRoom.tsx` (Testata: i due `Dato` -> `<FasciaSoldiVeri>`, import;
`Dato` rimosso perche' non piu' usato - `noUnusedLocals`), `frontend/src/components/controlroom/useControlRoom.ts`
(solo additivo: import, campo `soldiVeri` in `ControlRoomVM` accanto a `freni`, stato `saldoCanaleConto`,
effetto di ascolto, `useMemo soldiVeri`, chiave nel ritorno), `frontend/src/lib/fonteSoldi.ts` (SOLO `cls`
di `bot` e `prova`, ordine del coordinatore), `frontend/src/components/controlroom/MarchioSoldi.test.tsx`
(4 test aggiunti), `frontend/src/pages/ControlRoom.test.tsx` (1 test cambiato, 2 nuovi, 1 import).
Nuovi: `components/controlroom/testata/soldiVeri.ts`, `soldiVeri.test.ts`, `FasciaSoldiVeri.tsx`,
`FasciaSoldiVeri.test.tsx`, `components/controlroom/useControlRoom.soldiVeri.test.tsx`.
Non toccati: `totaliGiornata`, `groupCicliByEvent`, `etaPushS`, `fonteDi`, `soldiGiornata` (la DayBar
continua a mostrare «Liability aperta» lorda: e' del blocco B6, non mio).

Campo nuovo del VM: `soldiVeri: SoldiVeriTestata` = `{ conto: ContoAdesso, rischioBot: RischioBotLive,
etaBotS, scarto: ScartoContoBot | null, partite: PartiteConPosizione | null, programmaScanner }`.

MarchioSoldi (`lib/fonteSoldi.ts`): BOT = `bg-indigo-400/10 text-indigo-200 border-indigo-400/30`;
PROVA = `bg-white/5 text-slate-300 border-white/15 border-dashed` (tono di `MODE_META.paper` + tratteggio).

## 5. Test

- Nuovi: `soldiVeri.test.ts` 21, `FasciaSoldiVeri.test.tsx` 9, `useControlRoom.soldiVeri.test.tsx` 6,
  `MarchioSoldi.test.tsx` +4, `ControlRoom.test.tsx` +2. Caso di oggi: conto −9,95; Mike 16,22 (9,80+6,42+0),
  Omega 0, Safe 0 -> totale 16,22, NON TORNANO 6,27; 39,15/37,04 assenti; conto non letto -> nessuna cifra.
- Cambiato: `ControlRoom.test.tsx` «L'ESPOSIZIONE in testata e' quella VERA...» (era a riga 858):
  attendeva `77,71` (somma lorda) e `2 / 59` nella pagina. Cambia perche' cambia il testo voluto: ora
  attende in TESTATA l'esposizione del conto (`9,95`), NON `77,71`/`315,97`/`2 / 59`, `2 partite` e
  `programma scanner 59`; l'assenza di `393,68` resta su tutta la pagina. Asserzioni piu' strette, nessuna tolta
  (a parte `2 / 59` e `77,71` che diventano «non deve comparire» in testata).
- Comandi (da `frontend/`): `npx tsc -p tsconfig.app.json --noEmit` = 0 errori;
  `npx vitest run src/pages/ControlRoom.test.tsx src/components/controlroom --maxWorkers=2` = **57 file,
  888 test verdi** (449 s); dopo un ritocco di tipo al test puro rilanciato `src/components/controlroom/testata` = 30/30.

## 6. Falsificazioni (script fuori dal repo, copia -> mutazione -> vitest -> ripristino dalla copia, hash verificato; `git diff --stat` identico prima/dopo). Mutazioni in `T_falsificazioni/mut_p3.json`

| Mutazione | Esito |
|---|---|
| M1 aggregato paper accettato come rischio live | ROSSO 5 test |
| M2 scarto anche entro il centesimo | ROSSO 1 |
| M3 conto non letto vale 0 | ROSSO 2 |
| M12 bot senza liability netta ignorati | ROSSO 1 |
| M14 rischio "completo" anche con voci mancanti | ROSSO 4 |
| M7 occhio del saldo ignorato | ROSSO 1 |
| M11 partite non lette scritte "0 partite" | ROSSO 1 |
| M5 saldo ascoltato solo dal runner calcio | ROSSO 1 (hook) |
| M6 una lettura del conto in piu' | ROSSO 1 (hook) |
| M8 BOT col testo di PROVA | ROSSO 1 |
| M9 BOT in sky | ROSSO 1 |
| M10 PROVA senza tratteggio | ROSSO 1 (era anche il rosso TDD iniziale) |
| M4 la testata torna a mostrare lorda + "N / programma" | ROSSO 2 (pagina) |

## 7. Specchio ordini del conto (richiesto per un blocco successivo)

`get_live_positions_all()` / `get_live_positions_event(p_event_id)` (`migrations/betfair_live_pnl_journal.sql:238/:258`,
`live_positions_senza_mercati_regolati_2026-09-26.sql:24`) leggono `betfair_live_positions`, che scrive
SOLO il runner dal `blotter.get_exposures` della SUA strategia (`Betfair/stream/engine/live_trading_strategy.py:11-17`,
`stream/db.py:889-908`). La tabella non ha colonna `source`. Gli ordini del sito/app entrano invece in
`betfair_live_orders` (`reconcile_worker.py:311-372`: `client_order_ref = ext<bet_id>`, `source='account'`
o `bot:<csr>`, `mode='live'`) e **senza `event_id`** (la riga di `_account_order_row` porta solo `market_id`).
Quindi: **NO, quelle RPC non restituiscono gli ordini `ext`/`source='account'`.** Per l'elenco delle partite che
non tornano serve una RPC nuova (migrazione, la applica l'utente), forma proposta:
`get_live_orders_account_open() RETURNS jsonb { rows: [{bet_id text, market_id text, selection_id bigint,
side text, price numeric, size_matched numeric, average_price_matched numeric, status text, source text,
placed_at timestamptz, event_id text /* da un join mercato->evento */}] }` filtrata `mode='live' AND
client_order_ref LIKE 'ext%' AND status <> 'EXECUTION_COMPLETE' OR (size_matched > 0 AND mercato non regolato)`;
il `event_id` va ricavato con un join su una tabella che mappi `market_id -> event_id` (da verificare quale:
`safe_strategy_scan.payload` o lo specchio del runner) oppure scritto da `reconcile_worker` nella riga `ext`.

## 8. COSA NON HO FATTO

- L'elenco delle partite che non tornano (serve lo specchio ordini del conto: §7).
- «Partite con rischio vero» (1 = Follo) al posto di «con posizione» (3): serve lo stesso specchio.
- Nessun tocco a `SaldoBetfairCard.tsx`, `lib/saldoBetfair.ts`, DayBar/Obiettivo (la «Liability aperta 39,15»
  della barra di giornata resta: blocco B6).
- Lo stantio di Mike (`liability_stale`) va solo nel tooltip, non in ambra a schermo.

## 9. COSA NON HO POTUTO VERIFICARE

- **L'app a schermo non l'ho vista**: larghezza reale della testata sticky (5 blocchi + freni + runner + bot + feed),
  a capo su schermi stretti, leggibilita' del marchio a 9 px: da guardare dal vivo.
- Che `getAccountFunds` restituisca SEMPRE l'esposizione negativa (Betfair la documenta cosi'; il DB di oggi
  la ha a −9,95): la cifra e' mostrata come arriva, lo scarto usa il valore assoluto.
- Che `aggregates.mode` di Mike arrivi davvero in `get_mike_state` (il tipo TS `MikeAggregates` non lo
  dichiara; la SQL lo costruisce): se mancasse, Mike con posizioni live finirebbe «non incluso» (onesto, ma parziale).
- DB non letto in questo blocco (nessuna query): i numeri di oggi vengono dal progetto §0.

## 10. Dati che mancano dal backend

- Specchio ordini del conto per evento con gli `ext` (§7).
- Per Safe: il rischio LIVE separato arriva solo se la pagina chiamasse `get_safe_aggregates('live')`
  (esiste: `safe_strategy_paper_live_2026-09-13.sql:383`) - lettura NUOVA, non fatta per il vincolo di velocita';
  oggi Safe e' in paper senza posizioni live, quindi la voce vale 0 esatto.

## Verifica del coordinatore UI (admin-07), 30/09 18:30
- Albero di verifica integrato (`1d058a7` + C_P12a + B1 + B2 + T_P3 + G_P8, fusione a tre vie senza conflitti): `npx tsc -p tsconfig.app.json --noEmit` = 0 errori; `npx vitest run src/components/controlroom src/components/trading src/pages/ControlRoom.test.tsx` + test di lib toccati = 87 file, 1379 test verdi.
- Sul master `96a2189` (worktree di integrazione) lo stack G_P2 → G_P2_test → B1 → B2 → T_P3 → C_P12a → G_P8 produce, su ogni file toccato, lo STESSO contenuto byte per byte dell albero verificato.
- `T_P3.patch` si applica pulita (senza --3way) DOPO G_P2, G_P2_test, B1, B2.
- Diff riletto: in `useControlRoom.ts` solo aggiunte (import, campo `soldiVeri`, 5 ascolti del topic `account` sui canali gia aperti, un `useMemo`); nessuna lettura nuova.
- Mutazioni MIE (oltre le 13 del delegato), ROSSE, ripristino da copia: aggregato MISTO (mode null) accettato anche con posizioni paper aperte (2 rossi); scarto mostrato anche con rischio dei bot incompleto (2); verso dello scarto rovesciato (4).
- Limiti dichiarati, veri a schermo: «Posizioni LIVE 3 partite» conta ancora le pareggiate e quelle chiuse dal sito (serve lo specchio ordini del conto per evento, §7); il rischio LIVE di Safe e separabile solo senza posizioni paper aperte; tennis e scalper non pubblicano un rischio netto (con posizioni LIVE: «stima parziale»).
