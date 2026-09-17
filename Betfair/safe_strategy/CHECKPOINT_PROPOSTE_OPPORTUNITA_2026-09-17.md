# CHECKPOINT — Le opportunità di modello diventano PROPOSTE (17/09/2026)

**Ordine dell'utente (testuale):** «Le opportunità modello (SIA CALCIO CHE TENNIS) devono
apparirmi come la card della chiusura (falle apparire sotto e con card dedicata) CON TUTTE LE
INFORMAZIONI E I DUE TASTI: "PIAZZA" parte l'ordine, "RIFIUTA" la scheda viene rifiutata.»

Stato: **costruito, NON committato, NON certificato dal coordinatore.** La migrazione **non è
stata applicata**. `npm run build` **non** è stato eseguito (lo fa l'utente).

---

## 1. Che cosa fa adesso il bot

Le opportunità di modello **calcio** (`kind='model'`) e **tennis** (`kind='tennis'`) non
producono più ordini automatici. A ogni giro delle opportunità il servizio scrive una
**proposta**: una riga della coda che già esiste, `public.safe_strategy_requests`, con
`kind='place'`, `status='proposed'` e `payload.opp_key`.

Il perno è quello del 14/09 e del 17/09 di Omega: **il servizio drena SOLO `status='pending'`**
(`bot_db.pending_requests`). Una riga `proposed` sta ferma finché un essere umano non la
promuove.

- **PIAZZA** = `safe_request_approve(id)` (RPC del 14/09, invariata): `proposed → pending`. Al
  ciclo dopo `process_requests` la drena e la esegue con `_request_place`, cioè **la stessa
  strada della richiesta manuale della UI**, con `strategy='model'` + `kind`, il gate di rischio
  morbido, la freschezza del feed, il cap di responsabilità e la consapevolezza dell'ordine
  (`size_requested` / `size_matched` / `avg_price_matched` / `betfair_updated_at`, scritte da
  `_execute`). Nessuna seconda strada verso Betfair.
- **RIFIUTA** = `safe_request_ignore(id, motivo)` (RPC del 14/09, invariata): `proposed →
  rejected` con `result.ignorata_dall_utente`. Finché la chiave resta uguale **quella
  opportunità non torna**.
- **DECADUTA** = il servizio porta la riga a `rejected` con `result.decaduta` quando
  l'opportunità sparisce dal feed o la partita non è più in gioco. Una partita presente ma **non
  valutata** in quel ciclo (quote assenti, feed non fresco) **non fa decadere niente**: non
  sapere non è un motivo per togliere una scheda dagli occhi di chi decide. Con `rows` vuoto non
  si tocca nulla.

**Chiave stabile:** `opp_key = event_id + "|" + kind:market_type:selection_id:side` — la stessa
`signal_key` con cui l'automatico non si ripeteva. Non contiene il prezzo: se lo contenesse un
rifiuto durerebbe un tick.

**Modalità.** La proposta nasce con `modalita_di_strategia("model", mode, params)` e
`_request_place` la **ricalcola** all'approvazione. Con il servizio in LIVE e
`strategy_modes.model` in paper la proposta dice PAPER e parte in PAPER (senza questa regola il
confronto con `control.mode` nudo l'avrebbe rifiutata **sempre**, e il tasto PIAZZA non avrebbe
mai funzionato). Un payload che asserisce `live` mentre `strategy_modes` non lo dice viene
**rifiutato**, non degradato in silenzio: i soldi veri si raggiungono solo scrivendolo.

**Attività** (tutte con il `mode` della RIGA, non del servizio — reperto del 17/09):
`proposta_opportunita`, `opportunita_piazzata`, `opportunita_rifiutata`, `opportunita_decaduta`.
Il rifiuto lo scrive la RPC (il servizio non c'è in quel momento): l'attività la scrive il
servizio al primo ciclo utile, **una sola volta**
(`marca_proposta_opportunita_annotata`).

**Write-on-change:** una proposta viva si riscrive solo se cambia la sostanza (prezzo, stake,
liability, modalità, numeri del modello). `decided_at` non si rinfresca mai, `proposed_at` sì:
sono i due istanti che rendono misurabile la latenza vera (cert. 14/09). Il 13/09 (DB giù per IO)
è il motivo per cui questo conta.

---

## 2. Divergenze dichiarate — DA PORTARE ALL'UTENTE

1. **`auto_trade_combos` (combinazioni) e `auto_trade_anomalies` (cecchino) NON sono stati
   convertiti.** Hanno un motore proprio (`_auto_trade_combos`, tutte le gambe o nessuna;
   `process_anomalies`, piazzamento immediato) e convertirli richiede una proposta a più gambe e
   un PIAZZA che manda N richieste. Sono **spenti per default** e restano automatici se accesi.
   Non li ho toccati perché non avrei potuto collaudarli nel tempo dato, e perché la strategia
   non si altera di iniziativa: **decisione dell'utente**.
2. **`tennis_opportunity.evaluate` produce back leader + lay sfavorito sulla stessa partita**
   (reperto già aperto del checkpoint 24). Non toccato: è strategia.
3. La frase del rifiuto per modalità non corrispondente su una proposta dice «il servizio è in
   PAPER» quando in realtà è la *strategia* a essere in paper. Cosmetico, non corretto.

---

## 3. File toccati

**Backend**
- `Betfair/safe_strategy/proposte_opportunita.py` — **NUOVO**: chiave stabile, corpo della
  proposta, impronta di sostanza.
- `Betfair/safe_strategy/bot_service.py` — `_auto_trade_opps` **sostituita** da `_proponi_opps`
  (non chiama più né `insert_trade` né `_execute`); nuove `_leggi_proposte_opp` e
  `_riconcilia_proposte`; `process_opportunities` raccoglie i corpi e riconcilia a fine ciclo
  (ritorna anche `proposte`); `_request_place` riconosce `payload.opp_key` (autorità della
  modalità, `meta.opp_key` / `meta.da_proposta` / numeri del modello, attività
  `opportunita_piazzata`).
- `Betfair/safe_strategy/bot_db.py` — `proposte_opportunita`, `scrivi_proposta_opportunita`,
  `chiudi_proposta_opportunita`, `marca_proposta_opportunita_annotata`.

**Migrazione (NON applicata)**
- `migrations/safe_proposte_opportunita_2026-09-17.sql` — due soli indici: unico parziale su
  `payload->>'opp_key'` WHERE `status='proposed'`, e indice di lettura su
  `kind='place' AND status IN ('proposed','rejected')`. Nessuna tabella nuova, nessuna RPC nuova,
  nessuna RLS o GRANT toccati. **Ordine di applicazione:** dopo `safe_strategy_bot.sql`,
  `safe_strategy_bot_v2.sql`, `safe_strategy_proposed_2026-09-14.sql`.

**Frontend**
- `frontend/src/components/controlroom/SchedaPropostaOpportunita.tsx` — **NUOVO**: la card.
  **Rilievo del coordinatore (2° giro):** percentuali e numeri passano da `fmtPct`/`fmtNum`
  di `@/lib/format` (niente `toFixed` nei sorgenti, `designGuard.test.ts`): a schermo
  «77,0 %» e «0,200» come nel resto della piattaforma; test allineati.
- `frontend/src/components/controlroom/SchedaPropostaOpportunita.test.tsx` — **NUOVO**.
- `frontend/src/components/controlroom/useControlRoom.ts` — separa le proposte di opportunità da
  quelle di chiusura (che non devono leggerle), vista con abbinabile ed età del prezzo dal feed
  vivo, `piazzaOpportunita` / `rifiutaOpportunita`.
- `frontend/src/pages/ControlRoom.tsx` — **fuori dal dominio dichiarato, 2 punti**: import e
  render delle card **sotto** quelle della chiusura. Segnalato di proposito.
- `frontend/src/lib/safeBot.ts` — tipi `PropostaOpportunita(Payload)`, `isPropostaOpportunita`,
  `'proposed'` in `SafeRequestStatus`, `fetchSafeRequests` non mostra più le proposte fra le
  richieste dell'utente (stesso difetto che Omega ha corretto su `get_omega_manual_requests`).
  **Rilievo del coordinatore (2° giro):** il `limit` torna a essere passato al builder com'era
  (contratto di `safeBot.test.ts`); le proposte si tolgono DOPO la lettura. Costo accettato e
  scritto nel codice: in una finestra fitta di proposte l'elenco delle ultime richieste può
  tornare più corto di `limit`. Se un giorno desse fastidio, il posto giusto è un filtro lato
  server, non un `limit` gonfiato qui.
- `frontend/src/components/safestrategy/safeActivity.ts` — etichette dei 4 kind nuovi.
- `frontend/src/components/safestrategy/BotParamsSheet.tsx` — le due etichette dicono «NON piazza
  più da sola … si piazza SOLO dalla scheda della Control Room (PIAZZA / RIFIUTA)».

**Test aggiornati al contratto nuovo** (erano verdi sul contratto vecchio, che non esiste più)
- `tests/test_bot_service.py` — `FakeDB` con le 4 porte nuove (chiavi identiche al vero);
  `test_opportunita_tradate_se_abilitate_e_oltre_le_soglie` → rinominata
  `test_opportunita_proposte_e_mai_piazzate_da_sole`; tennis idem; shape di ritorno con
  `proposte`.
- `tests/test_due_motori_tennis_2026_09_17.py` — `..._true_piazza_...` →
  `..._true_non_piazza_piu_ma_propone`.
- `tests/test_audit_2026_09_11.py` — i 4 kind nuovi nel catalogo di contratto con la UI.
- `tests/test_proposte_opportunita_2026_09_17.py` — **NUOVO**, 14 test.

---

## 4. Numeri

- `pytest Betfair/safe_strategy -q -p no:cacheprovider` → **1119 passed** (erano 1105; +14 del
  file nuovo, nessuna perdita).
- `npx vitest run src/components/controlroom/ src/components/safestrategy/` → **311 passed**
  (23 file), di cui 11 nuovi.
- `npx tsc -p tsconfig.app.json --noEmit` → **0 errori**.
- 2° giro (rilievi del coordinatore): `npx vitest run src/lib/safeBot.test.ts src/components/trading/designGuard.test.ts src/components/controlroom` → **240 passed** (11 file), tsc **0**.

### Falsificazioni (rotto → rosso → ripristinato, md5 verificato)
`bot_service.py` md5 prima e dopo: `79d1a58f123d1bba56e98663442feb56` (identico).

1. rifiuto dell'utente ignorato (`if gia_decisa … : continue` → `if False`) →
   `test_rifiuto_persistito_la_stessa_chiave_non_torna` **rosso**.
2. decadenza anche su una partita non valutata (`elif eid in eventi_valutati` → `elif True`) →
   `test_una_partita_non_valutata_non_fa_decadere_niente` **rosso**.
3. autorità della modalità riportata a `control.mode` nudo →
   `test_servizio_live_e_modello_paper_la_proposta_paper_si_piazza` e
   `test_una_proposta_che_dice_live_col_modello_in_paper_e_rifiutata` **rossi**.
4. (dentro il file dei test, permanente) `test_falsificazione_una_chiave_instabile_farebbe_
   tornare_su_i_rifiuti`: con il prezzo dentro la chiave il rifiuto non tiene.
5. frontend: tolta la guardia fail-closed sull'età ignota delle quote →
   `età delle quote ignota: fail-closed` **rosso**; file ripristinato.

---

## 5. Che cosa NON ho potuto verificare

- **Nessuna verifica sul DB vero**: la migrazione non è applicata e non ho scritto nulla sul
  database (vincolo di sessione). Gli indici, il comportamento dell'indice unico parziale sotto
  concorrenza e l'effettiva convivenza con `uq_safe_requests_proposta_viva` sono ragionati, non
  misurati.
- **Nessun replay del banco comune** (`python -m Betfair.stream.backtest.certifica safe …`): non
  rientrava nel tempo dato. Finché non è fatto **questa modifica non è certificata** secondo
  `PROCESSO_STANDARD_BOT.md`, e va detto prima di qualunque discorso su paper o live.
- **Nessuna prova a schermo**: `npm run build` non fatto, app non riavviata. Il rendering reale
  della card dentro la colonna della Control Room è verificato solo dai test.
- Il comportamento in **concorrenza** (due schede aperte, doppio clic su PIAZZA) si appoggia al
  `FOR UPDATE` e al controllo di stato dentro `safe_request_approve` (14/09), non riprovato qui.
- Il volume reale di proposte con molte partite in-play (quante schede si accumulano in una
  serata) non è stato stimato: da guardare al primo giro vero.

---

## 6. Prossimi passi proposti

1. Verifica del coordinatore: rilettura del diff, riesecuzione di suite/vitest/tsc,
   falsificazioni rifatte in direzioni nuove.
2. Decisione dell'utente su combinazioni e cecchino (divergenza 1) e su
   `tennis_opportunity.evaluate` (divergenza 2).
3. Applicazione della migrazione da parte dell'utente, `npm run build`, riavvio dell'app.
4. Replay dal banco comune con uno scenario dedicato: «opportunità proposta, rifiutata, tornata»
   e «opportunità decaduta a mercato chiuso».
