# UI di Mike veritiera — tre difetti (30/09/2026)

Base: master `15f0a33`, worktree `agent-a4e1167523d6c772b`. Nessun commit, nessun processo
avviato, nessun `npm run build`, DB non toccato. Patch completa (file modificati + nuovi):
`AUDIT_2026-09-30/UI_MIKE_VERITIERA.patch` (`git apply --check -R` coerente con l'albero).

## 1. Badge rosso «⚠ FLUSSO PREZZI INTERROTTO · 1628 s» sulla scheda pre-partita

**Causa.** `frontend/src/components/controlroom/SchedaPreMatch.tsx:111` montava
`FlussoBadge` su `p.flusso` = `giudizioFlusso(payload.flusso)` (`lib/controlRoom.ts:846`). Quel
blocco è del MATCH ODDS (`Betfair/safe_strategy/service.py:803-829`, `flusso_evento`: `vivo`/`motivo`
del Match Odds, `dal_ms` = passaggio di stato del Match Odds). Prima del fischio lo scanner legge
il Match Odds solo in gioco o negli ultimi 20 minuti (`safe_strategy/scanner.py:390-407`,
`RELEVANT_PRE_KO_SEC`): motivo `mai_ricevuto`, `dal_ms` = creazione della riga. Da qui il rosso
e il contatore; il tooltip diceva anche «Nessun bot apre né chiude», falso per Mike, che lavora
sulle linee Under/Over 3,5 e 4,5.

**Correzione (in sola lettura, stessa regola di Mike, nessuna soglia nuova).**
- `lib/flussoPrezzi.ts`: `giudizioFlussoMike(riga, nowMs)` è la copia in lettura di
  `Betfair/mike/feed.py::flusso_esito` + `mercati_di_mike`. Considera le linee 3,5/4,5 della riga
  ancora in gioco (una linea già decisa dai gol, cioè gol > linea, non conta) e le giudica ferme
  se compaiono in `flusso.mercati_fermi`. L'età viene da `seen_ms` del blocco `ou`, cioè l'ultimo
  book RICEVUTO. `moNonAncoraRicevuto(g)` riconosce il Match Odds `mai_ricevuto`.
- `lib/controlRoom.ts`: `PartitaFeedLike.ou` (stessa chiave del payload) e
  `PartitaGiornata.flussoMike`.
- `FlussoBadge.tsx`: prop `prePartita` (solo la scheda pre-partita la passa). Match Odds
  `mai_ricevuto` → nota grigia, niente rosso, niente contatore. Nuovo `FlussoLineeMikeBadge`.
- `SchedaPreMatch.tsx`: `prePartita` + badge delle linee; la riga delle quote si monta anche
  senza 1X2 se una linea è ferma. `SchedaPartita.tsx` (in gioco): aggiunto il solo badge delle
  linee; il badge del Match Odds resta identico (Safe/Omega).

**A schermo (scheda pre-partita):**
| caso | prima | dopo |
|---|---|---|
| MO mai ricevuto, linee vive (riga 36132117) | `⚠ FLUSSO PREZZI INTERROTTO · 1628 s` rosso lampeggiante | `Match Odds: prezzi non ancora ricevuti` grigio (tooltip: «Prima del fischio lo scanner legge il Match Odds solo negli ultimi 20 minuti (o in gioco): finora nessun prezzo ricevuto. Non riguarda le linee Under/Over di Mike, che hanno il loro flusso.») |
| linea 3,5 in `mercati_fermi` | nessuna indicazione della linea | `⚠ UNDER/OVER 3,5 FERMA · ULTIMO BOOK 36 S FA` rosso (maiuscolo per lo stile del badge); tooltip «Flusso prezzi fermo per lo scanner: Under/Over 3,5 (1.35) ferma, ultimo book ricevuto 36 s fa. Mike non apre su queste linee; con una posizione aperta chiude o copre solo sui prezzi letti da Betfair (ripiego REST).» |
| MO `flusso_interrotto` pre-partita (ultimi 20') | rosso | rosso, invariato (è un'interruzione vera) |

In gioco: il badge Match Odds è invariato; se una linea di Mike è ferma compare in più il badge
`⚠ UNDER/OVER 4,5 FERMA · ULTIMO BOOK N S FA`.

## 2. «da N s» degli avvisi di flusso fermo di Mike contato dal fischio

**Causa.** `Betfair/stream/flusso_prezzi.py:180-186` (`_con_eta`) e `:284-301` (`secondi_fermo`)
usano `flusso.dal_ms`, che si muove solo al passaggio del Match Odds. Nel diario
(`mike/service.py:4667` `flusso_interrotto`, `:4678-4683` `flusso_interrotto_senza_rest`) usciva
«un mercato usato dalla decisione ha il flusso fermo (1.35); da 1628 s».

**Correzione (solo Mike; `flusso_prezzi.py` condiviso non toccato).** In `Betfair/mike/feed.py`:
- `linee_ferme_mike`: le linee di Mike in `mercati_fermi`, ciascuna con l'età di `seen_ms`;
- `testo_flusso_mike`;
- `secondi_fermo_mike`: il più vecchio fra gli ultimi book delle linee ferme e, se il giro dello
  scanner è bloccato, l'età dell'ultimo calcolo. Mai `dal_ms`;
- `flusso_esito`: con motivo `mercato_fermo` sostituisce il testo (`dataclasses.replace`);
  `vivo`, `motivo` e `mercati` restano invariati.

`service.py:4682`: `da_secondi` ora viene da `secondi_fermo_mike` e c'è una chiave nuova `testo`
(additiva). Se la riga non porta `seen_ms` (scanner precedente al 13/09) il comportamento resta
quello di prima.

In UI, `lib/mike.ts` riceve un `case 'flusso_interrotto_senza_rest'`: prima ricadeva sul default,
che mostrava solo la traduzione del motivo.

**A schermo (diario di Mike):**
- `flusso_interrotto`, prima: «un mercato usato dalla decisione ha il flusso fermo (1.35); da 1628 s · nessuna apertura né chiusura…».
  Dopo: «flusso prezzi fermo sulle linee di Mike: Under/Over 3,5 (1.35) ferma, ultimo book ricevuto 36 s fa · nessuna apertura né chiusura a mercato su quei prezzi · fase …».
- `flusso_interrotto_senza_rest`, prima: solo il motivo tradotto.
  Dopo: «<testo come sopra> · book Betfair (REST) non leggibile: posizione senza chiusura né copertura finché un prezzo vivo non torna · ultimo dato 36 s fa · esposizione 12,50 € · fase …».

## 3. «Salva parametri» di Mike senza riscontro visivo

**Causa.** Il salvataggio parte da `components/mike/useMike.ts:231`:
`saveParams = wrap(() => updateMikeParams(p))`.
- `wrap` non segnala il successo e restituisce `null` sull'errore, cioè lo ingoia (resta solo la
  notifica di `onError`).
- `ParamsSheetBase.save()` (`components/trading/ParamsSheetBase.tsx:143-149`) non mostra nessun
  esito.
- Omega invece fa `toast.success('Parametri aggiornati')` nella sua pagina (`pages/Omega.tsx:357`).

Secondo punto: se la rilettura dal servizio arrivava a schermo durante il salvataggio (poll o
realtime), la bozza non si riallineava più. Con un valore normalizzato dal servizio (es. il filtro
competizioni trimmato da `mergeMikeParams`) il pallino «modifiche non salvate» restava acceso: la
falsificazione M6 lo mostra.

**Correzione.**
- `ParamsSheetBase`: prop opzionale `riscontroSalvataggio`; senza la prop il comportamento è
  identico per Safe, Omega e tennis, ed è provato da un test. Con la prop:
  - il pulsante dice «Salvataggio…» ed è disabilitato mentre aspetta;
  - sotto il pulsante compare «Parametri salvati alle HH:MM:SS» (verde) oppure «Salvataggio NON
    riuscito: <errore>» (rosso), e sull'errore la bozza resta com'era;
  - dopo un successo la bozza si riallinea ai valori del servizio e il pallino si spegne.
- `MikeParamsSheet` passa `riscontroSalvataggio`.
- `useMike.saveParams` rigetta con il testo dell'errore della RPC; la notifica `onError` resta.

**A schermo:** prima, un clic su «Salva parametri» non mostrava niente di visibile. Dopo:
«Salvataggio…», poi «Parametri salvati alle 15:32:07», oppure «Salvataggio NON riuscito:
non autorizzato (owner-only)». Il pallino ambra sul pulsante «Parametri» si spegne dopo un
salvataggio riuscito.

## In più (costo zero)
`MIKE_ACTIVITY_EXTRA.canale_inviato` = «ORDINE INVIATO SUL CANALE · attesa esito», la stessa
etichetta di Omega. Il kind non entra in `MIKE_ACTIVITY_KINDS`, perché il contratto pytest elenca
solo i kind scritti da `mike/service.py`. Nel diario di Mike mancano ancora (non aggiunti, fuori
perimetro) `canale_rifiutato`, `canale_senza_ack`, `canale_giu` e `canale_giu_ripiego`, che
`safe_strategy/execution.py` può scrivere; per `canale_inviato` la riga di testo resta quella di
default.

## Test
- pytest `Betfair/mike` (ambiente neutro di `replay_mike.sh`): **1359 passed**. Include
  `test_mike_certificazione_ui_2026_09_11.py`, `test_l5_tutti_i_kind…` e il nuovo
  `test_mike_flusso_testo_linea_2026_09_30.py`: 8 test, uno sul ciclo vero `run_once`.
  Prima della correzione erano 6 rossi su 7 (il testo reale era «…(1.35); da 1628 s»).
- vitest `src/components/controlroom src/components/mike src/lib src/components/trading`:
  **203 file / 3326 test verdi**; `src/components/safestrategy|omega|tennis src/pages`:
  48 file / 712 verdi (1 skipped, già esistente).
- File di test nuovi:
  - `lib/flussoLineeMike.test.tsx`: 14 test;
  - `components/mike/MikeParamsSheet.riscontro.test.tsx`: 4 test;
  - `components/mike/useMike.saveParams.test.tsx`: 2 test.
- `npx tsc -p tsconfig.app.json --noEmit`: 0 errori. Nessun `any`, nessun `@ts-ignore`.
- Falsificazione (`AUDIT_2026-09-30/falsifica_ui_mike_veritiera.sh <scratchpad con bak/>`): 10
  mutazioni, tutte ROSSE, file ripristinati da copia e verificati con `cmp`.
  - M1: senza `prePartita`;
  - M2: linea decisa contata;
  - M3: badge in gioco tolto;
  - M4: testo Mike non sostituito;
  - M5: `secondi_fermo` generico;
  - M6: niente riallineamento della bozza;
  - M7: `saveParams` non rigetta;
  - M8: senza `riscontroSalvataggio`;
  - M9: `null` letto come 0;
  - M10: errore mostrato come successo.

## Non verificato
- **Non ho visto l'app**: nessun build, nessun avvio. Dopo `npm run build` (lo fa l'utente) deve
  vedere:
  - sulle partite pre-partita di Mike niente rosso «FLUSSO PREZZI INTERROTTO», al più la nota
    grigia «Match Odds: prezzi non ancora ricevuti»;
  - un badge rosso con il nome della linea solo se lo scanner mette 1.xx della 3,5/4,5 in
    `mercati_fermi`;
  - nel pannello parametri di Mike la riga verde con l'ora dopo «Salva parametri».
- Il DB non l'ho letto: la forma della riga 36132117 viene dal referto del coordinatore e dal
  codice dello scanner.
- La causa di «nessun riscontro» è ricostruita dal codice. Il pallino rimasto acceso è dimostrato
  in test (scenario con rilettura durante il salvataggio), non osservato nell'app.
- La scheda non vede lo STATO dello scanner (giro bloccato): quel caso lo dice il diario di Mike,
  non il badge.
- Replay di certificazione non rilanciato. La modifica Python cambia solo il testo e i
  `da_secondi` del diario, non le decisioni (`vivo`/`motivo`/`mercati` identici); il coordinatore
  può rilanciarlo con `replay_mike.sh` (entro 10 minuti).
- Il badge Match Odds in gioco resta «⚠ FLUSSO PREZZI INTERROTTO», senza dire che è il Match
  Odds: cambiarlo tocca Safe e Omega. Proposta per l'utente: etichetta «⚠ MATCH ODDS: FLUSSO
  INTERROTTO».
