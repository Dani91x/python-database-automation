# B17 (25/09) - Schede: a che prezzo e' abbinato il mio ordine, e se e' abbinato davvero

Delegato, worktree `agent-a7b971258796d041a`, base `d1ef6cb` (gia' in pari con origin/master). Niente commit.

Ordine dell'utente (punto 14): «una volta che clicco, devo sapere a che prezzo e' stato abbinato il mio ordine rispetto al segnale e soprattutto se e' stato realmente abbinato, con un messaggio».

## 1. Com'e' fatto

**Modulo puro `frontend/src/lib/esitoAbbinamento.ts`** (nessun React, nessuna chiamata di rete)
- `ClicOrdine` (:83): quello che la scheda sa al clic. Bot, tipo (apertura o chiusura), lato dell'ordine che parte, **prezzo visto**, **prezzo del segnale**, contesto, modalita', righe del bot gia' note sulla partita, ruoli (Mike).
- `gambeDelClic` (:263): quali righe sono l'ordine di quel clic.
  - Prima di tutto gli id dichiarati dal servizio (`idsDaRisultato` :236).
    - Apertura: `result.trade_id` o `trade_ids`.
    - Chiusura: `closing_trade_id`.
  - Un'apertura senza id **non si indovina mai**.
  - Chiusura Omega/Safe: `closes_trade_id` della posizione, solo gambe nate dopo il clic.
  - Mike e bot tennis: righe NUOVE del bot sulla partita (col ruolo proposto, per Mike).
- `esitoGamba` (:349): legge solo campi veri, attraverso `statoOrdine` (colonne del 16/09, poi `meta`). Le righe tennis passano da `comeRigaOrdine` (:291): `average_price_matched` e `updated_at` dello specchio flumine.
  - FOK:
    - `paper_fok_parziale` e `paper_no_fill` = NON abbinato.
    - `live_not_matched:EXPIRED` = NON abbinato: non e' un rifiuto, anche se `statoOrdine` lo leggerebbe come codice.
  - Stati flumine terminali (`EXECUTION_COMPLETE`/`LAPSED`/...): contano l'abbinato vero e il residuo.
  - Una riga `open` senza numeri: «abbinata per il servizio». Il medio **non si inventa**.
- `esitoAbbinamento` (:484): produce il messaggio.
  - Delta in tick con la ladder Betfair (`riskMath.ticksBetween`), rispetto al prezzo visto e al segnale.
  - «a favore» o «contro» secondo il lato.
  - Dichiara fonte ed eta'.
  - Dopo 3 minuti senza esito finale lo dice.

**Seguito `frontend/src/components/controlroom/useSeguiOrdini.ts`**
- La riga dell'ordine si prende dalla mappa `righePos` della Control Room. Puo' arrivare in due modi:
  - dal **canale del bot al ms**, overlay con `_seq`;
  - dall'ultimo blocco del **database**.
- Se la riga manca o non e' terminale, ogni 2 s:
  - si rilegge la coda del bot per id. E' la stessa `LETTURA` del «Chiudi»; per Safe la nuova `fetchRichiestaSafe` (`safeBot.ts:1397`), una select per id;
  - si chiede una **rilettura mirata** del blocco (`RilettureMirate`: anti-tempesta, al massimo 1 ogni 2 s per bot).
- La rilettura si chiede solo se il canale non ha portato la riga negli ultimi 3 s, e al massimo per 90 s dal clic.
- Tutto si ferma all'esito terminale. Nessuna query nuova, nessun canale nuovo.

**Striscia `EsitoAbbinamentoStriscia.tsx`**: mostra
- il messaggio;
- «visto al clic X · segnale Y · medio abbinato Z»;
- «esito: <fonte> · N s fa»;
- il cartellino «paper · abbinamento simulato» (il testo e' identico al live) oppure «soldi veri».

## 2. Tabella scheda x (prima del clic / al clic / dopo il clic)

| Scheda | Prima del clic | Al clic (visto + segnale) | Dopo il clic |
|---|---|---|---|
| **Safe opportunita'** (`SchedaPropostaOpportunita.tsx`) | Gia' fatto il 24/09 (3acde25): ladder al ms, semaforo, EV, eta' e fonte. Verificato, non toccato. | Prima: solo prezzo visto + contesto. **Ora** si aggiunge `prezzo_segnale` = `price_at_decision`, altrimenti `price` (:289, `schedaAlMs.prezzoSegnaleDi` :170). Il servizio lo scrive sulla riga come `meta.prezzo_segnale` (`bot_service.py:2778`) e nel contesto (`proposte_opportunita.py:377`). | Prima: solo «inviata/eseguita/rifiutata» della coda (`OpportunitaColonna.tsx`). **Ora** la coda da' `trade_id`, poi la riga, poi il messaggio d'abbinamento (`useControlRoom.ts:2518`, `OpportunitaColonna.tsx:74`). La vecchia riga resta solo per le proposte non seguite. |
| **Safe uscita** (`SchedaChiusura.tsx`) | Gia' fatto il 24/09 (al ms, avvisi). | Prima: visto + contesto. **Ora** anche `prezzo_segnale` = `price_at_decision` (:167). | Prima: la striscia di certezza viveva dentro la scheda, che sparisce al clic. **Ora** la gamba `closing_trade_id` e' seguita fino all'abbinamento in «Uscite» (`useControlRoom.ts:2581`, `UsciteColonna.tsx:77`). |
| **Omega uscita** (`SchedaChiusuraOmega.tsx`) | Gia' fatto il 24/09 (back al ms, «Blocchi adesso», semaforo). | Prima: **solo `p_id`**. **Ora** partono il back a video (o l'ultimo noto col flag), il contesto e `prezzo_segnale` = `back_price` (:138). Nuova migrazione `omega_request_approve_contesto_2026-09-25.sql`. Ripiego su `p_id` solo su PGRST202, dichiarato nell'etichetta (`useControlRoom.ts:2620`, `omegaProposte.ts:320`). | **Ora** la gamba `closing_trade_id` di `omega_trades` e' seguita fino al messaggio, in «Uscite». |
| **Mike proposta d'uscita** (`PropostaUscitaMike.tsx`) | **Non al ms**: i prezzi vengono da `mike_events.live` (get_mike_state, tick di 1 s, badge di freschezza). Non toccato: vedi §6. | Prima: `prezzo_visto`, eta', fonte. **Ora** anche `prezzo_segnale` = `ordini[0].prezzo` e `clic_ms`, nel `contesto` della richiesta `approva_uscita` (:101). Nessuna migrazione: payload jsonb libero. | Prima: «approvazione inviata». **Ora** seguito con la coda `mike_requests` e le **righe nuove di Mike sulla partita coi ruoli proposti**. L'esito resta a video anche dopo che il motore consuma la proposta (:72). |
| **«Chiudi» di riga** (tutti i bot, tennis compresi; `BottoneChiudiRiga.tsx`) | Il prezzo «se chiudo ora» della riga (feed; invariato). | Prezzo visto = `chiusura.prezzo` della riga, salvato solo nel clic della pagina. **Payload della richiesta invariato**: vedi §6. Nessun segnale (chiusura manuale). | Prima: «richiesta inviata / presa in carico / eseguita / rifiutata». **Ora**, dopo la richiesta, anche il messaggio dell'ordine di chiusura (`BottoneChiudiRiga.tsx:77`, `useControlRoom.ts:2921`). Omega/Safe: gamba `closes_trade_id`. Mike e bot tennis: righe nuove del bot sulla partita. Scalper escluso: ferma una sessione, non e' un ordine. |
| **Tennis «arma»** | - | - | Non e' un ordine con prezzo: fuori perimetro, dichiarato. |
| **Ladder manuale** | - | - | Non passa da queste schede: fuori perimetro. |

## 3. Esempi dei messaggi (testi esatti, inchiodati da `esitoAbbinamento.test.ts`)

- `inviato: in attesa del servizio`
- `in corso: eseguito · in attesa della riga dell'ordine`
- `accettato da Betfair a 2,40: in attesa di abbinamento, 5,00 € sul book`
- `ABBINATO TOTALMENTE a prezzo medio 2,42 (Δ vs visto +1 tick a favore, vs segnale −1 tick contro), size 5,00 €`
- `ABBINATO PARZIALMENTE: 2,00 € su 5,00 € a 2,40 (Δ vs visto 0 tick, vs segnale −2 tick contro), resto 3,00 € in attesa sul book`
- `ABBINATO PARZIALMENTE: 2,00 € su 5,00 € a 2,40 (...), resto annullato`
- `NON abbinato (FOK): il book non copriva l'intera size, ordine ucciso senza abbinamento`
- `rifiutato: Betfair: INSUFFICIENT_FUNDS` e `rifiutato: <message del servizio coi due prezzi>`
- `ABBINATO TOTALMENTE (prezzo medio non dichiarato dal servizio; prezzo della riga 2,40), size 5,00 €`
- Fonte:
  - `canale del bot al ms (seq 44) · 1 s fa`
  - `database (ripiego: lettura del blocco del bot) · 4 s fa · esito Betfair dal canale ordini del runner (seq 7, matched)`
  - `coda del bot (riletta ogni 2 s) · 1 s fa`

## 4. Migrazioni

- `migrations/omega_request_approve_contesto_2026-09-25.sql` (nuova, da applicare dall'utente).
  - `omega_request_approve(p_id, p_price DEFAULT NULL, p_contesto DEFAULT NULL)` scrive `price_visto`, `price_visto_at` e `prezzo_visto_ctx` nel payload.
  - Il payload si conserva e `approved_at` resta.
  - Permessi: REVOKE anon, GRANT authenticated.
  - Idempotente, ASCII.
  - **Nessun effetto sull'esecuzione**: Omega chiude ancora a mercato (B17 aperto).
- Safe: nessuna migrazione nuova. `p_contesto` (24/09) e' jsonb libero, e il servizio accetta `prezzo_segnale` nel contesto solo se e' una quota valida.

## 5. Test e falsificazioni

**vitest, file toccati: 14 file, 419 verdi (prima della B17), piu' i nuovi**
- `lib/esitoAbbinamento.test.ts`: 36
- `EsitoAbbinamento.schede.test.tsx`: 11 (seguito, striscia, colonne, Chiudi, Mike)
- `SchedaChiusuraOmega.test.tsx`: 14. Le 2 asserzioni `toHaveBeenCalledWith(9)` sono aggiornate al contratto nuovo, `(9, 31, {fonte:'proposta', prezzo_vivo_assente:true, prezzo_segnale:31})`, piu' 1 test al ms.
- `SchedaPropostaOpportunita.alms.test.tsx`: +2
- `useControlRoom.test.tsx`: 58 (+4: seguito del clic Safe; Omega con prezzo, ripiego PGRST202, niente ripiego sul rifiuto vero)
- Tutti verdi.

**tsc**: `npx tsc -p tsconfig.app.json --noEmit` = 0 errori miei. Restano **8 errori preesistenti su master** (`EtaDato`/`etaDato`: file non tracciati nel checkout principale, importati da `DirezioneDashboard`/`MLPanel`/`PoissonPanel`/`TacticalEnginePanel` in 5139d2b). Non sono miei.

**pytest** (sandbox SUPABASE a 127.0.0.1:9)
- `test_prezzo_segnale_b17_2026_09_25.py` (9) e `test_omega_approve_contesto_b17_2026_09_25.py` (6), nuovi.
- `test_scheda_al_ms`, `test_proposte_opportunita`, `test_combos_anomalie_proposte`: 99 verdi.
- `test_bot_service`, `omega/test_omega_proposte_2026_09_17`, `test_audit_2026_09_11`: 285 verdi.

**Falsificazione**: `AUDIT_2026-09-25/mutazioni_schede_abbinamento.py`, log in `falsificazione_schede_abbinamento.txt`.
- Il controllo senza mutazioni e' VERDE.
- **18/18 mutazioni ROSSE**, md5 ripristinato: 13 TS, 3 Python, 2 SQL.
- Esempi: «a favore» invertito; FOK ucciso letto come rifiuto; righe note contate come ordine; apertura indovinata senza id; chiesto spacciato per medio; nomi tennis ignorati; rilettura col canale fresco; coda chiusa riletta; doppia riga d'esito; Omega senza prezzo visto; segnale = price riscritto; ripiego Omega su rifiuto vero; Mike senza segnale; segnale non scritto sulla riga; segnale sporco accettato; funzione aperta ad anon; payload rifatto da zero.

## 6. Non fatto / non verificato (da portare al coordinatore)

1. **Mike prima del clic non e' al ms.** La proposta ha `mercato`/`selezione` simbolici (OU35/UNDER), non `market_id`/`selection_id`: agganciare `usePrezzoAlMs` richiede una mappa verso gli id veri che non ho trovato sulla proposta.
2. **Mike e tennis: le gambe sono per CORRELAZIONE, non per chiave.** Sono le righe nuove del bot sulla partita dopo il clic (Mike: stesso ruolo). Dare una chiave vera vorrebbe dire scrivere la chiave dell'approvazione sulle gambe (`engine.py`/`service.py` di Mike): e' la strategia, non l'ho toccata. Un'uscita di protezione nata nello stesso istante verrebbe attribuita al clic.
3. **«Chiudi» di riga: il prezzo visto non va al servizio** (payload `cashout`/`chiudi_bot` invariato: percorso soldi, non l'ho allargato). Si usa solo a video per il Δ.
4. **Topic `order` del runner (`betfair_live_orders`) non letto direttamente dalla scheda.** L'esito arriva dalla riga del bot, che il servizio aggiorna dal canale ordini (`meta.canale_seq`/`canale_fase` mostrati). Una lettura diretta per `client_order_ref` richiederebbe un accesso nuovo allo store di `localTransport`.
5. **Lato servizio (punto 4 del brief)**: Mike REST (`service.py:1389`, `:1818`) e Safe tennis REST (`execution.place` -> `_conferma_apertura`) scrivono gia' `size_matched`/`avg_price_matched`/`size_remaining`. Non c'era niente da aggiungere; verificato solo in lettura, senza replay.
6. **Non rieseguiti**: banco/replay, suite intere, `npm run build`, prova nell'app viva.
7. B17 «esecuzione a mercato vs prezzo visto» per le uscite Safe/Omega resta una **decisione dell'utente**: qui si salva e si mostra, non si esegue.

## 7. File

`git diff > AUDIT_2026-09-25/schede_abbinamento.patch` (modifiche ai file tracciati). File nuovi:
- `frontend/src/lib/esitoAbbinamento.ts` + `.test.ts`
- `frontend/src/components/controlroom/useSeguiOrdini.ts`
- `frontend/src/components/controlroom/EsitoAbbinamentoStriscia.tsx`
- `frontend/src/components/controlroom/EsitoAbbinamento.schede.test.tsx`
- `Betfair/safe_strategy/tests/test_prezzo_segnale_b17_2026_09_25.py`
- `Betfair/omega/tests/test_omega_approve_contesto_b17_2026_09_25.py`
- `migrations/omega_request_approve_contesto_2026-09-25.sql`
- `AUDIT_2026-09-25/mutazioni_schede_abbinamento.py`, `falsificazione_schede_abbinamento.txt`

Nel worktree ci sono le junction `frontend/node_modules` e `.venv` verso il principale: vanno tolte con `cmd /c rmdir`, **mai** con `--force`.
