# W_B2 - referto (30/09 sera)

Worktree: `C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.claude\worktrees\agent-aef9b44f1a9ce5796`.
Base: `d4b4f6b` (checkout -f), poi `R_B2_incr_lane.patch` e `R_G_incr_lane.patch` (applicate pulite; per `useControlRoom.ts` la R_G andava in conflitto col mio blocco 4: file riportato a HEAD, R_G applicata, blocco 4 riapplicato a mano sulla forma R_G, `provaPerBot`).
**`W_B2.patch` è cumulativa: R_B2 + R_G + W_B2** (`git diff -- frontend/`, file nuovi con `git add -N`). Backup del diff di prima: `B2_backup_pre_W.patch`.
Solo presentazione e lettura di dati già in memoria. Nessuna lettura nuova, nessun ordine.

## 1. Esiti veri anche per Omega e Safe (M10)

`lib/tradeStatus.ts` `esitoOrdineMeta`: si applica solo alle righe `error`, in quest'ordine.
1. Esito scritto da Mike (`meta.esito_ordine`). Un esito sconosciuto dà `null` (fail-closed).
2. Motivo scritto dal servizio (`meta.reason`), con il prefisso Omega `flumine_` tolto (`omega_service.py:3551`).

| motivo scritto (bot) | etichetta | dove nel Python |
|---|---|---|
| `cancelled_by_engine` (Mike), `cancelled_no_fill` (Omega: annullo nostro dopo il TTL) | RITIRATO dal bot | mike/service.py:4307; omega_service.py:3701-3703 |
| `reconciled_not_placed` (Mike), `live_rest_no_fill`, `live_rest_not_found`, `canale_rest_no_fill`, `canale_rest_not_found`, `canale_mai_visto_su_betfair` (Omega), `reconcile_ordine_assente`, `reconcile_ordine_senza_fill` (Safe) | NON ABBINATO (verificato su Betfair) | mike 5422-5424; omega 3811, 3825, 3192, 3214, 3218; safe bot_service 1236, 1481 |
| `live_rifiutato:<C>` (Safe/condiviso), `live_not_matched:<stato>:<C>` | RIFIUTATO da Betfair: C; con `senza_codice` → «(codice non dichiarato)» | execution.py:985-987, 919-921 |
| `terminal_violation` (Omega paper) | RIFIUTATO da Betfair: VIOLATION | omega 3643; motore_ordini.py:500 |
| `live_not_matched:<stato>` SENZA codice (Safe/Mike), `live_fok_<stato>` (Omega) | NON ABBINATO (tutto o niente) | regola di Mike `_esito_del_rifiuto` service.py:646-653; omega 3780 |
| `canale_scaduto`, `terminal_expired`, `terminal_lapsed` | NON ABBINATO (scaduto su Betfair) | motore_ordini.py:503-509; omega 3643 |
| `canale_annullato` | ANNULLATO senza abbinamento (la riga non dice da chi) | motore_ordini.py:505-512; omega 3082 |
| `canale_rifiutato[:motivo]` | RIFIUTATO dal runner[: motivo] (nessun ordine a Betfair) | execution.py:590; omega 3082 |
| `kill_switch`, `live_kill_switch_attivo`, `db_kill_switch_attivo`, `kill_switch_illeggibile`, `freni_live_non_letti`, `live_order_mode_non_live:*`, `paper_runner_non_disponibile`, `paper_senza_runner*`, `canale_giu:*`, `live_revoked_deadline`, `paper_revoked_deadline`, `submin_non_disponibile:*`, `canale_comando_non_valido:*`, `canale_senza_trade_id`, `canale_premarcatura_fallita`, `mode_non_valido:*`, `side_non_valido:*`, `prezzo_non_disponibile`, `size_non_valida`, `liquidita_insufficiente` | FERMATO dal bot (mai inviato) | omega 5500, 5582-5592, 3855, 3667; execution.py 180-214, 506-556, 703-730, 846, 851; controls.py:107-140 |
| tutto il resto (es. Omega manuale `live_not_matched` NUDO, senza codice scritto; `no_mirror_after_ttl`; `reconcile_orphan_old`) | resta ERRORE / ERRORE (definitivo), con il motivo accanto (`motivoErroreTesto`): tradotto dove si sa, altrimenti grezzo con gli `_` tolti | omega 5546, 3676-3678, 4213 |

Scelta di prudenza: `live_not_matched` NUDO di Omega manuale (`omega_service.py:5546`) NON diventa «tutto o niente». Quel ramo scrive la riga anche per `not res.ok`, cioè un rifiuto, e non salva il codice. Resta «ERRORE (definitivo) · non abbinato o rifiutato da Betfair (codice non scritto sulla riga)».

Il codice di rifiuto si legge dalla forma della nota: in `live_not_matched:EXPIRED`, EXPIRED è lo stato, non un codice. `statoOrdine.codiceRifiuto` lo legge come codice: è un difetto di `statoOrdine.ts`, fuori perimetro, e lo segnalo.

`statusMetaOf` e `STATUS_META` non sono cambiati. In `dettaglioRiga.ts` la riga `error` non classificabile passa da `statoConMotivo`: badge di sempre + « · motivo».

## 2. «Liability» con due significati (M1)

- `SchedaPartita.tsx`, solo la riga `cr-liability-partita`:
  - PRIMA «liability 12,93 €». DOPO «liability delle righe (lorda) 12,93 €», con title «sommate riga per riga senza compensare… non il rischio netto».
  - Con Mike in LIVE e `live.liability` numerico compare prima «Liability aperta (netta, Mike) 9,80 € [BOT]» (testid `cr-liability-netta-mike`, `MarchioSoldi fonte="bot"`). In paper, o senza il dato, non compare.
  - La prova diventa «prova (lorda)».
- `SchedaMike.tsx`: «Liability aperta» diventa «Liability aperta (netta)» + marchio BOT (`cr-mike-liability-fonte`).
- Omega e Safe: una netta per partita non arriva alla scheda (gli `aggregates` non sono per partita), quindi resta solo la lorda, detta tale.

## 3. Parole della plancia

`PannelloBot.tsx`: la mappa locale `STATO_TESTO` («in esecuzione / sta fermandosi / fermo / in errore») è stata sostituita da `statoTesto`, che usa `botStatusMeta`: IN CORSA / IN ARRESTO / FERMO / INATTIVO / ERRORE. Resta «stato non letto» per l'ignoto. Nota: `idle` ora dice INATTIVO, prima «fermo».

## 4. Plancia: fonte del P&L LIVE di oggi (M15)

- `useControlRoom.ts` (`botsConPnl`, `liveDi`):
  - con il conto letto, Omega e Mike prendono `pnl_reale_oggi.per_fonte[bot].netto`, fonte CONTO, età da `etaContoS`. È la stessa lettura di `composizioneDalConto`; l'attribuzione non viene rifatta;
  - Safe per strategia: `tennis` prende `safe_tennis` dal conto; le strategie del calcio restano dalle righe (fonte BOT) con la nota «il conto separa Safe solo per sport…»;
  - senza conto: le posizioni chiuse del bot (BOT);
  - dato letto e vuoto: 0 con `vuoto`; non letto: null.
- `righeBot.ts`: nuovo tipo `FonteOggiLive`. La fonte passa alla riga solo in LIVE; la prova non passa mai dal conto.
- `PannelloBot.tsx`: accanto alla cifra LIVE compare `MarchioSoldi` (CONTO BETFAIR · N s fa / BOT); se vuoto, « · nessuna regolata oggi». Non letto: «—» senza marchio.
- Nota: con il conto, la cifra è il REGOLATO da Betfair (`per_fonte.netto`). La parte ancora stimata (chiusa dal bot, non ancora regolata), che la composizione dell'obiettivo aggiunge, qui non c'è. Si allinea aggiungendola, se vuoi: una riga.
- Richiesta aggiuntiva: test R_G con, nello stesso gruppo, LIVE +2,00 e PROVA +7,60 → «oggi LIVE 2,00 €» e «prova 7,60 €», mai 9,60. È falsificato con esattamente la tua mutazione (`|| r.modalita === 'paper'` → rosso).

## 5. Hunk del P&L reale del conto (patch `agent-a5d9566643a63ed1e/.../PNL_REALE_DEL_CONTO.patch`)

- Letti e applicati SOLO i 4 file indicati: `DettaglioRigaView.tsx` (etichetta «ordine tuo (non del bot)»), `PosizioniChiuse.tsx` (parole da `lib/fontePnl.ts`), `useControlRoom.ts` (le righe «utente» di Mike fuori dalla composizione, `isRigaUtente`), `useControlRoom.test.tsx` (il loro test).
- Si sono applicati puliti con offset; `lib/fontePnl.ts` è già su master.
- Test miei: `DettaglioRigaView.test` (riga «utente») e `PosizioniChiuse.raggruppamento.test` (parole delle fonti).

## 6. File

- Toccati da W_B2:
  - `lib/tradeStatus.ts` (`esitoOrdineMeta` e affini, `motivoErroreTesto`)
  - `components/controlroom/dettaglioRiga.ts`, `SchedaPartita.tsx` (riga liability + 2 righe di calcolo + import), `SchedaMike.tsx`, `PannelloBot.tsx`, `righeBot.ts`, `useControlRoom.ts` (`botsConPnl` + import + tipo `StatoBot`; hunk utente), `DettaglioRigaView.tsx` (1 riga dalla patch), `PosizioniChiuse.tsx` (dalla patch)
- Test cambiati di proposito:
  - `P13EsitiChiusura.test.tsx` (test Omega/Safe: ora ci sono esiti e motivo)
  - `SchedaPartita.test.tsx` (B1: «liability delle righe (lorda)»)
  - `PannelloBot.test.tsx` («sta fermandosi» → «IN ARRESTO»)
  - `pages/ControlRoom.test.tsx:1316` (idem)
  - `useControlRoom.test.tsx:1253` (Omega letto e vuoto → 0 fonte BOT)
- Test aggiunti:
  - `W_B2EsitiOmegaSafe.test.tsx` (nuovo, 13)
  - `SchedaPartita.test` (+2), `B2GlossarioAuditCR.test` (+2 asserzioni)
  - `PannelloBot.test` (+5: parole, fonte, vuoto, non letto, R_G), `righeBot.test` (+1)
  - `useControlRoom.provaGiornata.test` (+2), `useControlRoom.test` (+1 dalla patch)
  - `DettaglioRigaView.test` (+1), `PosizioniChiuse.raggruppamento.test` (+1)
- Fuori da `frontend/`: `falsifica_W.cjs`, `falsifica_W1.json`, `falsifica_W23.json` (con W2), `falsifica_W4.json`, `falsifica_W5.json`, file di appoggio `_w_*.txt`.

## 7. Falsificazioni (copie fuori dal repo, ripristino dalla copia, confronto byte a byte)

Tutte ROSSE e RIPRISTINATE:
- W1 11/11: prefisso Omega, verificato, codice/stato, nudo tranquillizzante, runner, mai-inviato, ritiro TTL, scaduto, motivo tolto, motivo rassicurante, solo `error`.
- W2 7/7: lorda con parola nuda, netta assente, netta anche in paper, netta senza marchio, prova senza «(lorda)», SchedaMike senza «(netta)», SchedaMike senza marchio.
- W3 3/3: «sta fermandosi», idle→FERMO, ignoto grezzo.
- W4 9/9: la mutazione R_G del coordinatore, marchio assente, «nessuna regolata» muto, fonte anche in prova, conto vuoto → «—», conto ignorato, Safe calcio dal conto, letto e vuoto → «—», età persa.
- W5 4/4: riga utente contata due volte, «utente» grezzo, parole vecchie in testata e nella fonte.

## 8. Numeri

- `npx tsc -p tsconfig.app.json --noEmit` UNA volta alla fine: 0 errori.
- `npx vitest run --maxWorkers=2`, file lanciati: `src/components/controlroom`, `src/components/trading`, `pages/ControlRoom.test`, `lib/tradeStatus`, `certezzaChiusura`, `fontePnl`, `statoOrdine`, `giornataCorsie`, `components/mike/useMikeEventoAlMs`, `pages/SafeStrategy*` (6), `pages/Mike.test`, `Mike.fixA`, `Omega.test`.
- Esito: **101 file, 1563 passati, 1 saltato, 0 falliti** (679 s).
- Patch: `W_B2.patch`, 32 file di `frontend/` (R_B2 + R_G + W_B2), `git apply --check -R` OK.

## 10. COSA NON HO FATTO

- Netta per partita di Omega e Safe nella scheda: il dato non arriva.
- `statoOrdine.codiceRifiuto` che legge lo stato come codice: fuori perimetro.
- La plancia non aggiunge la parte stimata al regolato del conto (vedi §4).
- Nessun commit, nessuna build, nessuna suite intera.

## 11. COSA NON HO POTUTO VERIFICARE

- L'app a schermo non l'ho vista (lunghezza della riga liability con i due numeri e il marchio; plancia).
- I `meta` veri di Omega e Safe non li ho letti dal DB: i finti seguono il codice che li scrive (righe citate).
- Il paper di Omega (`terminal_*`) nel runner reale: dedotto da `fase_da_riga`.
