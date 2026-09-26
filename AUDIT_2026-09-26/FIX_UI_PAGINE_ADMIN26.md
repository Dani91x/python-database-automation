# FIX UI PAGINE (admin-26) — le 13 FAIL di Control Room, Segui Live, Market Watch, Tennis Terminal

Delegato di correzione, 26/09/2026. Worktree `agent-a5e62d641b4ae202b` (base `498ba07`). Niente commit, niente DB, niente `.env`.
Fonte dei reperti: `AUDIT_2026-09-25/e2e_fase2/ADMIN26_FASE3_PAGINE.md` (§2, §7) e `CRONOSTORIA.md` 26/09 h12:50 / h13:20.
Fuori perimetro (altri cantieri, NON toccati): F-9 (runner, banner ORDER_MODE), F-11 (Tennis Terminal `tennis_follow_event`).
Strategie: nessuna regola toccata (vedi «Divergenze» in fondo).

## Esito in breve

| reperto | stato | test nuovi (RED→GREEN) | falsificazione |
|---|---|---|---|
| F-1 P&L «oggi» per bot NULL (Omega/Mike/Safe) | corretto | giornata F-1 ×3, hook F-1 | rossa |
| F-2 due verità (piazzamento vs regolamento) | corretto (regolamento ovunque per il realizzato) | giornata F-2 ×3 | rossa |
| F-3 «giornata non ancora letta» su lettura vuota | corretto | giornata F-3 ×4 | rossa |
| F-4 tick col segno invertito | corretto (anche `SafeTradesTable`; `offsetTargetPrice` era giusto) | tick ×5 + 2 attese vecchie corrette | rossa |
| F-5 «ingresso None-None» | corretto (servizio + UI) | pytest ×2, vitest ×1 | rossa |
| F-6 proposte Safe scadute con «Piazza» | corretto (servizio + UI) + sanatoria scritta | pytest ×5, vitest ×3 | rossa |
| F-7 P mercato con due definizioni | corretto | vitest ×2 (+1 attesa vecchia corretta) | rossa |
| F-8 «vol. 0,00 €» falso | corretto alla fonte (zero dello stream non è misura) | pytest ×3 | rossa |
| F-10 Market Watch «LIVE» su partita finita + 3° set mancante | corretto (UI + `set_summary` nel runner tennis) | pytest ×4, vitest ×1 | rossa |
| F-12 «Chiudere adesso» lordo | corretto (netto 5 %, stessa funzione per tutta la pagina) | hook ×1 | rossa |
| F-13 «4+ gol» ma il numero è P(=4) | corretto (etichetta e title «esattamente 4», il numero è quello su cui Mike decide) | vitest ×1 | rossa |
| KO §9-bis n.2 paper+live sommati (Market Watch) | corretto (due numeri etichettati) | vitest ×1 (+ helper del test canale aggiornato) | rossa |

Numeri (rilanciati alla fine): tsc `-p tsconfig.app.json` **0 errori**; vitest sui file toccati + test esistenti dei moduli toccati
**45 file, 850/851 verdi** al primo giro (`AUDIT_2026-09-26/vitest_toccati.txt`: l'unico rosso era `SafeTradesTable.audit.test.tsx:78`, attesa
«+6» che codificava il segno invertito di F-4, corretta in «−6»; poi `src/components/safestrategy/` 15 file / 206 test verdi);
pytest dei moduli toccati (Mike intero, tennis_live, 12 file Safe) **2016 passed, 1 skipped** (`AUDIT_2026-09-26/pytest_toccati.txt`).
**Falsificazione: 18 mutazioni su 18 ROSSE, ripristino sha256 identico 18/18** (`falsifica_fix_ui_pagine.txt` + `_giro1.json` per le 14
TS/SQL-free; le 4 Python rilanciate col filtro dopo aver tolto il `\n` dai modelli — i file Python sono CRLF —
`falsifica_fix_ui_pagine_python.txt`).

---

## F-1 — P&L «oggi» per bot NULL per Omega/Mike/Safe (U0209)

- **Causa**: `frontend/src/components/controlroom/useControlRoom.ts:2236` (base) `pnlOggi: isBotTennis(bot) ? … : null`.
- **Correzione**:
  - `frontend/src/lib/posizioniChiuse.ts` nuova `pnlChiuseDelGiorno(posizioni, {giorno, bot, modo, strategia?})`: `filtraChiuse` (giorno di
    REGOLAMENTO, una modalità) + somma dei `pnlGlobale` netti: è la STESSA regola e la stessa fonte della scheda Posizioni chiuse. `null` =
    nessuna chiusa («—»), mai uno zero inventato. `strategia` = quella dell'apertura del ciclo (Safe).
  - `useControlRoom.ts` `botsConPnl` (dopo `chiuse`, ~riga 2491): Omega/Mike `pnlOggi`/`pnlOggiPaper` da `pnlChiuseDelGiorno`; Safe
    `pnlOggiPerStrategia` per `base/esatto/punta/model/manual/tennis`. Il VM espone `bots: botsConPnl`. Tennis e scalper invariati.
  - `frontend/src/components/controlroom/righeBot.ts`: `StatoBotPlancia.pnlOggiPerStrategia`; una riga di STRATEGIA legge il suo P&L, mai
    quello del bot (un numero del bot ripetuto su 6 righe Safe sarebbe stato sommato 6 volte da `riassuntoGruppo` in `PannelloBot.tsx:151`).
- **Limite dichiarato**: la plancia usa le posizioni chiuse costruite dalle righe IN MEMORIA (`vm.chiuse`), come la scheda prima che la
  lettura `get_posizioni_chiuse_giornata` completi le catene. Un ciclo la cui apertura non è fra le righe caricate (es. Mike piazzato ieri,
  regolato oggi: `get_mike_state` porta solo le righe piazzate oggi) compare nella scheda (che legge anche la RPC) e non nella colonna «oggi».
  Leggere la RPC anche dal modello di vista = 2 letture in più ogni 60 s: non fatto senza permesso (respiro del DB).

## F-2 — due verità sullo stesso denaro (U0192/U0194/U0249)

DECISIONE applicata (coordinatore): il **realizzato di oggi è per giorno di REGOLAMENTO ovunque**; il conteggio delle partite PIAZZATE
oggi (obiettivo/barra Omega §14, `partite piazzate`) resta per piazzamento e non è stato toccato.
- **Causa**: `frontend/src/lib/composizioneObiettivo.ts:342-343` (base) ramo PAPER `if (!delGiorno(a.placed_at)) continue`; tessere sport da
  `get_safe_daily` (`migrations/safe_strategy_paper_live_2026-09-13.sql:329,344,348`, piazzamento, sola tabella di Safe).
- **Correzione**:
  - `composizioneObiettivo.ts` `righeGiornataPerCiclo`, ramo paper: il ciclo entra quando è CHIUSO (nessuna gamba viva; `cancelled`
    ammessa come nelle Chiuse) e la sua ultima gamba regolata (`settled_at`) è di oggi; senza istante di regolamento, il piazzamento
    (stesso ripiego delle Chiuse, `posizioniChiuse.ts` `giornoDa='piazzamento'`). Il ramo live era già per regolamento: invariato.
  - `frontend/src/lib/controlRoom.ts` nuova `perSportGiornata(conteggiate, soloPnl, conteggiExtra)`; `useControlRoom.ts` `tesseraSport`
    (in `giornataSoldi`, ~riga 3487) costruisce `perSport`/`perSportPaper` dalle STESSE righe della barra (tutti i bot, regolamento),
    righe sintetiche (bot tennis, voci manuali) solo nel P&L e i contatori veri dei bot tennis da `get_tennis_bot_daily`.
    `get_safe_daily` resta letta SOLO per la controprova `discordanza` (che confronta servizio e calcolo del bot con la regola del servizio).
  - `SplitSport.tsx` commento di testa aggiornato (la fonte non è più `get_safe_daily`).
- **Nessuna migrazione né RPC nuova**.
- **Effetto collaterale voluto**: le tessere Calcio/Tennis contano ora TUTTI i bot dello sport (prima solo Safe: era il KO §9-bis n.3
  «mostra SOLO Safe»), perché nascono dalle righe della barra.
- **Residuo**: la lettura `fetchSafeDaily(…, 'paper')` resta nel giro dei 30 s ma il suo valore non è più usato
  (`const [, setSafeOggiPaper]`): toglierla cambia `FONTI_RICARICA` (test di contratto) — da decidere.

## F-3 — «giornata non ancora letta» con RPC riuscita a 0 righe (U0194)

- **Causa**: `useControlRoom.ts:1290` `setSafeOggi(rows[0] ?? null)` + `SplitSport.tsx:69` `letto={perSport != null}`.
- **Correzione**: le tessere non dipendono più da quella RPC: `perSport` = `soldiLetti ? perSportGiornata(...) : null`, e
  `perSportGiornata` restituisce SEMPRE i due sport (a zero se vuoti). `SplitSport.tsx` `Tessera`: letta e senza righe per la modalità
  → `pnl = 0` («+0,00 €» e «nessuna operazione … oggi»); non letta → «—» e «giornata non ancora letta» come prima.

## F-4 — tick di movimento col segno invertito (U0239)

- **Causa**: `frontend/src/components/controlroom/dettaglioRiga.ts:129-141` (base): prezzo dello STESSO lato e `× −1` sul lay; commento
  `:113-116` finanziariamente falso. Stessa inversione in `frontend/src/components/safestrategy/SafeTradesTable.tsx:429`
  (`ticksBetween(entry, prezzo di chiusura) × (lay ? −1 : 1)`: su entrambi i lati il favorevole usciva negativo).
  `offsetTargetPrice` (`frontend/src/lib/riskMath.ts:85`) era GIUSTO (lay chiude back più alto): non toccato.
- **Correzione**: `riskMath.ts` nuova `tickAFavore(lato, ingresso, prezzoChiusura)` (lay: +ticks se sale; back: +ticks se scende).
  `dettaglioRiga.ts` `quotaViva`: `ora` = prezzo di CHIUSURA (lay → best back, back → best lay), `tick = tickAFavore(...)`; commento
  riscritto; doc di `QuotaViva.ora` aggiornata. `SafeTradesTable.tsx`: `dTicks = tickAFavore(...)`.
- **Attese vecchie corrette** (codificavano il bug): `dettaglioRiga.test.tsx` (lay@26 con back 24 → era «tick > 0», ora −2; back@3 con lay
  2,52 → ora > 0); `SafeTradesTable.audit.test.tsx:78` («+6» → «−6»: back 1,38 chiuso a lay 1,44 = −0,42 €).
- Casi del referto riprodotti (`fixPagine2609.tick.test.ts`): Omega 118 LAY 1@55, B 60 → **+1** (era −10); Mike 5071 BACK 5@1,60, L 1,68 →
  **−8** (era +2); Omega 119 LAY 1@80, B 29 → **−17** (era −8, atteso dal referto −17); Mike 5070 → −4 (era 0). Segno = «chiudi ora».

## F-5 — «ingresso None-None»

- **Causa**: `Betfair/mike/service.py:3616` (base) f-string senza guardia.
- **Correzione**: `service.py` nuova `_punteggio_ingresso(payload)` (~riga 520): `None` se manca uno dei due punteggi; la chiamata in
  `run_once` la usa. Il campo è solo notizia sulla riga (nessuna decisione di Mike legge `score_at_entry`: verificato con grep).
  UI: `dettaglioRiga.ts` `punteggioIngresso()` scarta i segnaposto (`None|null|undefined|NaN`; nessun formato imposto: il tennis ha punteggi
  con set e game) per le righe GIÀ nel DB; `DettaglioRigaView.tsx` `Ingresso` mostra «—» al posto del punteggio mancante.
- **Sanatoria dati (per l'utente, NON eseguita)**: `UPDATE public.mike_trades SET score_at_entry = NULL WHERE score_at_entry = 'None-None';`

## F-6 — proposte Safe `proposed` vecchie con «Piazza» (U0260)

- **Causa trovata**: la decadenza esiste (`bot_service.py` `_riconcilia_proposte`, «partita non più in gioco»), ma
  `Betfair/safe_strategy/bot_db.py:691` `proposte_opportunita(ore=24)` legge solo le ultime 24 h: la #257 (24/09 16:03Z) è rimasta viva
  mentre il servizio era spento e, uscita dalla finestra, non è più decaduta. Il finto dei test (`test_proposte_opportunita_2026_09_17.py:84`)
  ignora `ore`: per questo nessun test lo vedeva.
- **Correzione servizio**: `bot_db.py` nuova `scadi_proposte_opportunita(ore)`: UN UPDATE filtrato dal DB (`kind='place'`,
  `status='proposed'`, `created_at < adesso − ore`) → `status='rejected'`, `result={decaduta:true, scaduta:true, motivo}` (pubblicato sul
  canale come `chiudi_proposta_opportunita`). `bot_service.py` `_scadi_proposte_vecchie` (~riga 7260), chiamata in `process_opportunities`
  prima di `_leggi_proposte_opp`, al più ogni 10 min (`_OGNI_S_SCADENZA_PROPOSTE`), soglia `ORE_SCADENZA_PROPOSTA = 12`; annota
  `opportunita_decaduta` in attività. Cosa si propone NON cambia.
- **Correzione UI**: `frontend/src/lib/controlRoomProposte.ts` `SCADENZA_PROPOSTA_ORE = 12` e `propostaScaduta(created_at, feed, now)`
  (più vecchia di 12 h, o Match Odds `CLOSED` nel feed); `useControlRoom.ts` `proposteOpportunita` le filtra (contatore incluso).
- **Soglia dichiarata: 12 ore**, stessa nei due lati. Le opportunità nascono solo su partite in gioco (`eventi_in_gioco`): dopo 12 h la
  partita è finita di sicuro.
- **Divergenza dal brief**: lo stato `expired` NON esiste nel CHECK di `safe_strategy_requests`
  (`migrations/safe_strategy_proposed_2026-09-14.sql:25`: proposed/pending/processing/done/rejected/error). Si usa la marca già in uso per
  la decadenza (`rejected` + `result.decaduta`), che il servizio già riconosce (una proposta decaduta può tornare se l'opportunità torna).
  Nessuna migrazione.
- **Sanatoria per l'utente (NON eseguita)** — prima guardare, poi marcare:
  ```sql
  SELECT id, created_at, payload->>'event_name' AS partita, payload->>'kind' AS tipo
    FROM public.safe_strategy_requests
   WHERE kind = 'place' AND status = 'proposed' AND created_at < now() - interval '12 hours'
   ORDER BY created_at;
  UPDATE public.safe_strategy_requests
     SET status = 'rejected',
         result = coalesce(result, '{}'::jsonb)
                  || jsonb_build_object('decaduta', true, 'scaduta', true,
                                        'motivo', 'proposta scaduta: piu'' vecchia di 12 ore (sanatoria 26/09)'),
         updated_at = now()
   WHERE kind = 'place' AND status = 'proposed' AND created_at < now() - interval '12 hours';
  ```
  (Se `result` non fosse `jsonb`, togliere `coalesce(...) ||` e scrivere solo il `jsonb_build_object`.) Col servizio acceso la stessa
  cosa la fa `_scadi_proposte_vecchie` al primo ciclo delle opportunità.

## F-7 — «P mercato» con due definizioni (U0262)

- **Causa**: `SchedaPropostaOpportunita.tsx:540` (base) `ap?.p_implicita ?? p.p_implied` (de-vig) accanto a `ap?.edge ?? p.edge`
  (= p_model − 1/prezzo in TUTTI i motori: `opportunity.py:1000-1005`, `tennis_opportunity.py:431-436`, `anomaly.py`).
- **Correzione**: nuova `pMercatoProposta(prezzo, p_implied)` = 1/quota della proposta (ripiego su `p_implied` solo senza quota valida);
  etichetta «P del mercato (alla proposta)» quando manca la valutazione al prezzo di adesso. #257: 97,6 − 91,7 = 5,9 ≈ 0,058 (era 90,6).
- **Attesa vecchia corretta**: `SchedaPropostaOpportunita.test.tsx:65` 55,0 % → 76,9 % (= 1/1,30; la fixture non ha criteri).

## F-8 — «vol. 0,00 €» (U0232 dato)

- **Causa**: lo stream dello scanner si iscrive a `EX_BEST_OFFERS` + `EX_MARKET_DEF` (`Betfair/safe_strategy/stream.py:235`), niente
  `EX_TRADED_VOL`: il campo `tv` non arriva e betfairlightweight lascia `total_matched = 0` (`streaming/cache.py:214`).
  `Betfair/safe_strategy/service.py:835` (base) lo scriveva come volume.
- **Correzione**: `service.py` (~riga 835): uno ZERO dallo stream non sovrascrive il valore noto (REST) e senza valore resta `None`; il REST
  scrive il suo (anche 0). La UI (`SchedaPartita.tsx:357`) già nasconde il volume `null`: niente più «0,00 €» falso, «—»/assente.
- **Non fatto (decisione)**: la fonte «vera» nello scanner sarebbe aggiungere `EX_TRADED_VOL` ai `fields` dello stream (più banda e peso
  sui limiti di sottoscrizione del feed unico). Il «Matched €559» del ladder viene dal runner (47331), che lo scanner non legge.
  Le righe `safe_strategy_scan` già scritte con 0 restano finché lo scanner non le riscrive (al riavvio dell'app).

## F-10 — Market Watch «LIVE · 5-7 6-2» su partita finita (U0351)

- **Causa**: `frontend/src/pages/MarketWatch.tsx:419` (base) guardava solo `inplay`; `Betfair/stream/tennis_live/tennis_runner.py:276`
  `_set_summary` mostrava solo `gameSequence` (i set chiusi PRIMA del corrente), senza i game del set in corso/ultimo.
- **Correzione**: `frontend/src/lib/tennis.ts` `partitaTennisFinita(score.status, mercato.status)` (stato IPS di fine o Match Odds
  `CLOSED`); `MarketWatch.tsx` badge «FINITA · …» invece di «LIVE». `tennis_runner.py` `_set_summary(seq, gh, ga, sh, sa, status)`:
  aggiunge il set di `games` se la sequenza non lo contiene già (niente doppioni; a inizio set 0-0 non si aggiunge). Bondar v Birrell:
  «5-7 6-2 1-6». Lo stesso dato arriva al Tennis Terminal (`TennisTerminal.tsx:94`) e a `TennisMatchStats`.

## F-12 — scheda d'uscita Safe «Chiudere adesso» LORDO (U0256)

- **Causa**: `useControlRoom.ts:2516` (base) `partialLockedPnl(prezzo, win, lose, 1)` senza commissione, accanto a «Tenere» netto
  (`hold_profit`) e a `locked_at_decision` netto del servizio.
- **Correzione**: `chiusuraViva` (la funzione unica della pagina) restituisce `bloccabile` NETTO: `netAfterCommission(lordo, aliquota)`
  (commissione solo sul positivo), aliquota dalla riga (`commission`, poi `meta.commission`, altrimenti 5 %: `aliquotaDi`, ~riga 466).
  Vale per la scheda d'uscita (`bloccabileOra`), la colonna posizioni «chiudi ora», il dettaglio e l'«in corso» della barra: tutto netto.
- Esempio (test hook): Mike back 9@1,85, lay vivo 1,70: lordo +0,79 → **+0,75**.

## F-13 — `SchedaMike` «4+ gol» ma il numero è P(esattamente 4) (U0243)

- Letta la strategia: `Betfair/mike/engine.py:1137-1193` `hold_expectation` usa `dist[4]` e il pavimento `p4_market` = P(ESATTAMENTE 4)
  (`feed.py:159` `implied_p4` = P(O3.5) − P(O4.5)): 4 gol esatti è l'unico esito in cui perdono entrambe le linee. Il numero mostrato È
  quello che guida la decisione: si corregge l'ETICHETTA, non il numero.
- **Correzione**: `SchedaMike.tsx:117-130` etichetta «P(4 gol esatti) mercato», title «probabilità di ESATTAMENTE 4 gol …
  P(Over 3.5) − P(Over 4.5)» (mercato, modello, pre-partita). Nessun cambio alla strategia.

## KO §9-bis n.2 — paper e live sommati (Market Watch)

- **Causa**: `get_live_positions_event` senza filtro di modalità (`migrations/betfair_live_pnl_journal.sql:258-280`) e
  `get_tennis_live_positions_all(p_mode null)` (`migrations/tennis_live_positions_all_rpc.sql:19,27`); `MarketWatch.tsx:356,430`
  sommavano con `eventExposure`/`eventMtm`.
- **Correzione (lato pagina, nessuna migrazione)**: `frontend/src/lib/eventPnl.ts` `perModalita(rows)`; `MarketWatch.tsx` `MtmDueModi` e
  `RischioDueModi`: MTM e rischio «live» e «prova» in due numeri etichettati, mai sommati (calcio e tennis). Le righe portano `mode`
  (colonna delle tabelle). Il cash-out dell'evento non è toccato.
- **Non toccato**: Segui Live usa la stessa RPC `get_live_positions_event` per il rail posizioni (non nel perimetro dei due KO elencati).

---

## File toccati (tutti)

Python: `Betfair/mike/service.py`, `Betfair/safe_strategy/bot_db.py`, `Betfair/safe_strategy/bot_service.py`,
`Betfair/safe_strategy/service.py`, `Betfair/stream/tennis_live/tennis_runner.py`.
Frontend: `frontend/src/components/controlroom/{useControlRoom.ts, righeBot.ts, SplitSport.tsx, dettaglioRiga.ts, DettaglioRigaView.tsx,
SchedaMike.tsx, SchedaPropostaOpportunita.tsx}`, `frontend/src/components/safestrategy/SafeTradesTable.tsx`,
`frontend/src/lib/{composizioneObiettivo.ts, controlRoom.ts, controlRoomProposte.ts, eventPnl.ts, posizioniChiuse.ts, riskMath.ts, tennis.ts}`,
`frontend/src/pages/MarketWatch.tsx`.
Test nuovi: `frontend/src/components/controlroom/fixPagine2609.{giornata.test.tsx, tick.test.ts, varie.test.tsx}`,
`Betfair/mike/tests/test_mike_punteggio_ingresso_2026_09_26.py`, `Betfair/safe_strategy/tests/test_proposte_scadute_2026_09_26.py`,
`Betfair/safe_strategy/tests/test_volume_mo_2026_09_26.py`, `Betfair/stream/tennis_live/tests/test_set_summary_2026_09_26.py`.
Test esistenti estesi/corretti: `useControlRoom.test.tsx` (blocco «26/09 correzioni fase 3», 3 test), `dettaglioRiga.test.tsx` (F-5, F-13,
2 attese F-4), `SchedaPropostaOpportunita.test.tsx:65`, `SafeTradesTable.audit.test.tsx:78`, `MarketWatch.test.tsx` (2 test + mock
parziale di `@/lib/tennis`), `MarketWatch.canale.test.tsx` (mock parziale + helper `rischi()` legge il numero «prova»).
Banco fase 3: `frontend/e2e_fase3_admin26/confronta_cr.py` — COPIA aggiornata nel worktree (l'originale è non tracciato nel checkout
principale e NON è stato toccato): U0239 «chiudi ora» ora atteso NETTO (×0,95 sul positivo); U0260 le proposte > 12 h non si contano e
si verifica che NON siano a video (prima era un FAIL fisso). Le altre attese del banco (tick «a favore», U0209, U0194, U0192, U0262) erano
già scritte col valore giusto e ora dovrebbero passare.
Referto e strumenti: `AUDIT_2026-09-26/FIX_UI_PAGINE_ADMIN26.md`, `AUDIT_2026-09-26/falsifica_fix_ui_pagine.py` (+ `.json`),
`AUDIT_2026-09-26/vitest_toccati.txt`, `AUDIT_2026-09-26/pytest_toccati.txt`.
Nel worktree ci sono due JUNCTION (non file del repo): `.venv` e `frontend/node_modules` → togliere con `cmd /c rmdir` prima di rimuovere il worktree.

## Comandi per il coordinatore

```
cd <worktree>/frontend
npx vitest run src/components/controlroom/fixPagine2609.giornata.test.tsx src/components/controlroom/fixPagine2609.tick.test.ts \
  src/components/controlroom/fixPagine2609.varie.test.tsx src/components/controlroom/dettaglioRiga.test.tsx \
  src/components/controlroom/SchedaPropostaOpportunita.test.tsx src/components/safestrategy/SafeTradesTable.audit.test.tsx \
  src/pages/MarketWatch.test.tsx src/pages/MarketWatch.canale.test.tsx
npx vitest run src/components/controlroom/useControlRoom.test.tsx -t "26/09 correzioni"
npx tsc --noEmit -p tsconfig.app.json
cd ..
SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_KEY=x .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider \
  Betfair/mike/tests/test_mike_punteggio_ingresso_2026_09_26.py Betfair/safe_strategy/tests/test_proposte_scadute_2026_09_26.py \
  Betfair/safe_strategy/tests/test_volume_mo_2026_09_26.py Betfair/stream/tennis_live/tests/test_set_summary_2026_09_26.py
# falsificazione (18 mutazioni, ripristino con sha256; NON interrompere):
.venv/Scripts/python.exe AUDIT_2026-09-26/falsifica_fix_ui_pagine.py
```

## Cosa NON ho potuto verificare

- Il banco fase 3 (`e2e_fase3_admin26`) NON è stato rieseguito: legge il DB vero (service role) e i canali; fuori dalle regole di questo
  cantiere. Le attese aggiornate sono state solo scritte e controllate sintatticamente.
- Nessuna verifica dal vivo (app, DB, Betfair): F-8 in particolare (se il REST porta davvero `totalMatched` con `EX_BEST_OFFERS`) è
  ragionato sul codice di betfairlightweight, non osservato.
- Il formato esatto di `score.status` a partita finita diverso da 'Finished' (es. 'Retired'/'Walkover'): coperti solo
  finished/complete/completed/ended/closed + mercato CLOSED.

## Rischi residui

- F-2: cambiare il giorno del paper sposta numeri a cavallo della mezzanotte (un ciclo piazzato ieri e regolato oggi ora è di oggi) e un
  ciclo paper con una gamba ancora viva non conta più finché non chiude (prima contava il parziale): è la regola delle Chiuse.
- F-2/F-3: le tessere sport ora contano tutti i bot dello sport, non solo Safe; le righe sintetiche dei 4 bot tennis live entrano nel P&L,
  i contatori vengono da `get_tennis_bot_daily`.
- F-12: la colonna «chiudi ora» ora è netta (prima lorda): numeri positivi più bassi del 5 % rispetto a ieri; il banco è aggiornato.
- F-6: 12 h è una soglia, dichiarata e condivisa servizio/UI; una proposta di un torneo tennis lunghissimo non esiste nella pratica
  (le proposte nascono in gioco e decadono a partita chiusa).
- `MtmDueModi`/`RischioDueModi` sono esportati da una pagina (`MarketWatch.tsx`): lint `react-refresh/only-export-components` può avvisare.

## NON FATTO (per l'utente, con file:riga)

1. F-1: la colonna «oggi» usa le chiuse IN MEMORIA, non anche `get_posizioni_chiuse_giornata` (`useControlRoom.ts` `botsConPnl` ~r.2491;
   la scheda la legge in `PosizioniChiuse.tsx:136`): un ciclo con apertura fuori dalle righe caricate può mancare dalla colonna.
2. F-2: lettura `fetchSafeDaily(..., 'paper')` ormai inutile nel giro dei 30 s (`useControlRoom.ts` ~r.1058 `const [, setSafeOggiPaper]`,
   ~r.1302): toglierla tocca `FONTI_RICARICA` e il suo test di contratto.
3. F-8: volume vero nello scanner: serve `EX_TRADED_VOL` in `Betfair/safe_strategy/stream.py:235` (decisione di banda/limiti).
4. §9-bis: Segui Live usa ancora `get_live_positions_event` senza modalità per il rail posizioni (`lib/liveOrders.ts` `fetchLivePositionsEvent`);
   non era fra i punti elencati.
5. Sanatorie SQL scritte e NON eseguite: `mike_trades.score_at_entry='None-None'` (F-5) e proposte `proposed` > 12 h (F-6).
6. Banco `e2e_fase3_admin26` non rieseguito (DB vero); attese aggiornate solo nella copia del worktree.

## Divergenze dal brief

- F-6: `expired` non è uno stato ammesso dal CHECK della tabella → `rejected` + `decaduta` (convenzione già usata dal servizio).
- F-8: fonte vera del volume nello scanner non attivata (serve `EX_TRADED_VOL` sullo stream: decisione dell'utente); corretto il dato falso.
- Nessuna regola di strategia toccata in nessun fix.
