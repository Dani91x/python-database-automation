# STATO_RIPRESA - delegato Opus, schede proposte al ms (24/09/2026)

Worktree: agent-a5d6a648b59d268f2 (branch worktree-agent-a5d6a648b59d268f2, base master 3f65b2f).
Niente commit. Junction: frontend\node_modules -> principale (togliere con `cmd /c rmdir`, mai --force).
Consegna PARZIALE per ordine del coordinatore (PC saturo, 30 minuti): backend + banco + porte TS pure
FATTI e verificati; schede React al ms NON fatte (sotto, punto per punto).

## FATTO E VERIFICATO
1. Safe (Python)
   - `Betfair/safe_strategy/proposte_opportunita.py`: `motivo_prezzo_mosso`, `CRITERI_DEL_MOTORE`,
     `criteri_proposta`, `valuta_al_prezzo`, `valutazione_viva`, `valutazione_non_valida`,
     `impronta_valutazione`; `sostanza` estesa (impronta valutazione + criteri, mai l'istante).
   - `Betfair/safe_strategy/bot_service.py`: `_proponi_opps(motore_params=)` -> corpo con `criteri` e
     `valutazione`; `_parametri_motore_anomalie`; `_nascita_della_proposta` (decided_at,
     price_at_decision, size_available_at_decision, valutazione.dal); `_testo_non_piu_proposta`;
     `_marca_non_piu_valida` al posto della decadenza "opportunita' sparita dal feed" (partita finita e
     interruttore spento DECADONO come prima); `_request_place` e `_request_place_combo`: rifiuto con
     `price_visto`, `price_attuale`, `soglia_pct` e `message` con i due prezzi; combo con valutazione.
   - activity nuova `opportunita_non_piu_valida` (+ etichetta in `frontend/.../safeActivity.ts`,
     + catalogo in `tests/test_audit_2026_09_11.py`).
2. Omega (Python) `Betfair/omega/omega_proposte.py`: ingredienti nel payload (`commissione`,
   `margine_attesa` letto dal default VERO di `proposta_uscita`, `p_lose_max`, `max_attesa`) +
   `valutazione`; `esito_uscita_al_prezzo` (decisione di `proposta_uscita` al prezzo di adesso);
   `_non_piu_valida` al posto di `_decadi` quando la condizione non regge (aggregata e HT finita
   decadono ancora); activity `proposta_non_piu_valida` (+ etichetta in `frontend/src/lib/omega.ts`).
3. Banco `Betfair/stream/backtest/proposte_modello.py`: PM6 riletto, `Clic.scheda_valida`, trader
   (dopo_decadenza / dopo_sparizione firmano sulla scheda VIVA marcata non valida), descrizioni.
4. Porte TS pure + file d'oro: `frontend/src/lib/valutaProposta.ts` (+ `valutaProposta.golden.json`,
   generatore `Betfair/safe_strategy/tools/genera_oro_valuta_proposta.py`), `esitoUscitaAlPrezzo` in
   `frontend/src/lib/omegaProposte.ts` (+ `omegaUscita.golden.json`, `Betfair/omega/tools/genera_oro_uscita.py`).
5. Test: nuovi `Betfair/safe_strategy/tests/test_scheda_al_ms_2026_09_24.py` (20),
   `Betfair/omega/tests/test_omega_scheda_al_ms_2026_09_24.py` (4), `frontend/src/lib/valutaProposta.test.ts`
   (37), `frontend/src/lib/omegaUscita.test.ts` (22); aggiornati al contratto nuovo (spiegato nel
   docstring di ciascuno): test_proposte_opportunita_2026_09_17, test_bot_service (anomalie),
   test_combos_anomalie_proposte_2026_09_18 (2), test_omega_proposte_2026_09_17 (1),
   test_proposte_modello_2026_09_23 (PM6 parametrizzato + trader).
   Numeri: file toccati Python 423 verdi + 1 xfail; suite safe intera 1361 verdi (prima delle
   ultime modifiche Omega/banco), omega intera 1183+1 (poi corretto il test); tsc 0; vitest file
   toccati 154 verdi. Mutazioni: vedi referto (tutte rosse, md5 ripristinati).

## DA FARE (in ordine), come riprendere
A. Hook del prezzo al ms per scheda: NUOVO `frontend/src/components/controlroom/usePrezzoAlMs.ts`:
   `sorgenteLadderAlMs(sport).subscribe(market_id, cb)` (lib/localTransport.ts:447) in useEffect con
   unsubscribe al cleanup; dalla riga `LiveLadderRow.ladder.selections` prendere la selezione
   (`selection_id`) -> back[0]/lay[0] (prezzo, size), `ladder.updated_ms` (eta'), `status` (mercato),
   `sorgente.fonte(market_id)` ('canale'|'db'). Se il runner non streamma quel mercato (il ladder_worker
   pubblica SOLO i mercati seguiti, runner.py:678) nessun push arriva: ripiego sul feed dello scanner
   gia' in `useControlRoom.ts:1782` (`prezzoVivo`) con fonte dichiarata "feed scanner".
B. `SchedaPropostaOpportunita.tsx`: usare l'hook (prezzo al ms, fallback prop `prezzoVivo`), mostrare
   back/lay e size di adesso, `price_at_decision` (prezzo alla creazione) con differenza in tick
   (`riskMath.ticksBetween`) e %, EV/edge/responsabilita' da `valutaAlPrezzo({side, prezzo, abbinabile,
   p_model: payload.p_model, criteri: payload.criteri})`, semaforo: NO se `payload.valutazione.causa
   === 'modello'` o `!valutaAlPrezzo(...).valida`; QUASI se valida ma un tick contro (matching.ts
   tickDown per back / tickUp per lay) la rende non valida; SI altrimenti. Avvertimento "fuori
   criterio: <testoMotivo>" SENZA spegnere PIAZZA (restano fail-closed solo: prezzo assente/vecchio,
   abbinabile < stake in LIVE FOK). PIAZZA manda il prezzo mostrato (gia' cosi' a SchedaPropostaOpportunita.tsx:181).
   Stessi riquadri: cambiano i valori delle Celle esistenti (EV, P mercato, Vantaggio, Responsabilita').
C. `SchedaChiusura.tsx:90` + `lib/controlRoomProposte.ts:317`: la tolleranza dalla fotografia
   (`scost.fuoriTolleranza`) diventa AVVERTIMENTO, non blocco (e' il «dice che il prezzo e' cambiato»
   dell'utente). Aggiornare i test esistenti di `motivoNonApprovabile` che pretendono il blocco.
   NB: per le CHIUSURE Safe il servizio esegue a mercato (nessun prezzo visto: decisione B17 aperta).
D. `SchedaChiusuraOmega.tsx`: prezzo di back al ms (hook A), "Blocchi adesso" e decisione da
   `esitoUscitaAlPrezzo({lay_price: entry_price, size, back_price: vivo, back_size: size vivo,
   ev_tenere, max_attesa, p_evento, commissione, margine_attesa, cap_scattato, p_lose_max})`;
   `motivoNonApprovabileOmega` (omegaProposte.ts:135) NON deve piu' bloccare per motivo non proponente
   quando `valutazione.valida === false` (e' la scheda viva marcata dal servizio): avvertimento.
   `omega_request_approve` NON ha il prezzo visto (B17): serve una migrazione gemella di
   `safe_request_approve_prezzo_visto_2026-09-18.sql` + `_manual_cashout` che la rispetti -> decisione utente.
E. Esito dell'approvazione a video: dopo `piazzaOpportunita` (useControlRoom.ts:1829) leggere la riga
   per id finche' non e' done/error e mostrare `result.message` (ora porta i due prezzi) in
   `avvisoOpportunita` (OpportunitaColonna.tsx:57).
F. Test vitest per B-E (scheda che si aggiorna al tick con finto di `sorgenteLadderAlMs` con le chiavi
   di `LiveLadderRow`, semaforo SI/NO/QUASI, prezzo visto al clic = prezzo mostrato, avvertimento fuori
   criterio con PIAZZA acceso) + falsificazione.
G. Suite complete e replay del banco: le lancia il coordinatore all'integrazione.

## Reperti aperti
- Finestra fino a `opps_interval_s` (10 s) fra la sparizione di un'anomalia in `process_anomalies` e la
  marcatura della proposta in `process_opportunities`: la scheda al tick vede il PREZZO, non il
  riferimento dell'anomalia. Il trader del banco firma solo dopo la marcatura (PM6 lo pretende).
