# CANTIERE MIKE-APP - Pacchetto P6, blocco 5: testi di P2 e P4 (blocchi 2-3) + «tentativo n» in Control Room, 29/09/2026

Patch: `AUDIT_2026-09-29/MIKE_P6_5.patch`. Verificata con `git apply --cached --check` su master
`2686136` (che contiene gia' P6 blocchi 1-3, P2, P3, P4 blocchi 2-3): pulita. Pulita anche con
P6_4 applicata prima (i file non si sovrappongono). Solo frontend.

## 1. Cosa e' cambiato
| File | Cosa | Perche' |
|---|---|---|
| `frontend/src/lib/mike.ts` - `pre_last_entry_min` | hint: «a questo segno: se Mike e' piatto fa l'ultimo ingresso; se ha posizione non entra piu' e la banca resta appoggiata fino al fischio. Da qui nessun giro nuovo» | P2 (M2.1, M2.4) |
| idem - `last_entry_persist` | etichetta «Ultimo ingresso a 10 min dal fischio», hint senza PERSIST (stessa chiave) | P2 (M2.4) |
| idem - `last_entry_ticks_above` | «(NON ATTIVO)» + spiegazione, limiti invariati | P2: il motore non lo legge piu' |
| idem - `veto_p_under35_cal` | «blocca l'ultimo ingresso ... Non chiude mai niente» | P2 (M2.2) |
| idem - `MIKE_PHASE_META.HOLD.what` | «dopo il segno dei 10 minuti: nessun ingresso fino al fischio; la banca resta appoggiata» | P2 |
| idem - `MIKE_PHASE_META.PRE_LAST_ENTRY_PENDING.what` | «ultimo ingresso a 10 minuti dal fischio: ingresso normale, poi la banca a 2 tick sotto fino al fischio» | P2 |
| idem - `MIKE_REASON_LABEL` | `lettura_feed_fallita`, `lettura_feed_ripresa` (P4 b2); `punteggio_assente`, `punteggio_assente_tornato`, `quote_assenti_tornato`, `runner_senza_esito` (P4 b3), con le frasi del coordinatore | P4 |
| idem - `mikeActivityLine` `feed_line_missing` | con `reason: punteggio_assente` la riga non dice piu' «linee assenti nel feed» | P4 b3 |
| idem - nuova `notaRegolamentoMike(meta)` | `regolamento = non_determinabile` -> «da regolare a mano: risultato non leggibile»; `settle_reason = risultato_indipendente_dal_punteggio` -> «regolata senza punteggio: il risultato non dipendeva dai gol» | P4 b2 (M8.6) |
| `frontend/src/components/mike/MikeEventPnlTable.tsx` | la nota di regolamento accanto allo stato della gamba | P4 b2 |
| `frontend/src/lib/mikeEsitoChiusura.ts`, `EsitoChiusuraMike.tsx` | massimo dei tentativi NON noto (card della Control Room, che non riceve i parametri di Mike: verificato, `ElencoPartite` riceve solo `mikeEventi`) = «tentativo n» senza «di M»; i tentativi esauriti si riconoscono comunque col valore di serie del bot | punto 4 del coordinatore |

Etichette «ULTIMO (PERSIST)» del ruolo `under_last` (`lib/mike.ts`, `DayDetail.tsx`,
`PerformancePanel.tsx`): lasciate, servono alle righe vecchie.

Le stringhe dei motivi sono quelle scritte dal servizio di master (verificato con
`git show master:Betfair/mike/service.py`: `db.log("error", {"reason": "lettura_feed_fallita"...`,
`db.log("skip", {"reason": "lettura_feed_ripresa"...`, `meta["regolamento"] = "non_determinabile"`,
`meta["settle_reason"] = "risultato_indipendente_dal_punteggio"`, `"reason": "runner_senza_esito"` su
`no_fill`). `punteggio_assente*` e `quote_assenti_tornato` presi dal messaggio del coordinatore
(P4 blocco 3, `2686136`: non riletti riga per riga).

## 2. Test
- Nuovo `src/components/mike/MikeP6Blocco5.test.tsx`, 9 test (testi di P2, attivita' di P4, nota di
  regolamento anche nella tabella montata).
- `EsitoChiusuraMike.test.tsx`: +1 test («tentativo 5» senza «di M»; esauriti riconosciuti).
- Test esistenti modificati:
  | Test | Prima | Dopo | Decisione |
  |---|---|---|---|
  | `MikeMatchCard.test.tsx` «la fase dice a parole ...» | HOLD = «chiudere adesso sarebbe in perdita» | «dopo il segno dei 10 minuti: nessun ingresso fino al fischio» | P2, decisioni 2, 3, 6 del piano |
  | `useMikeEventoAlMs.test.tsx` (mio, blocco 3) | «tentativo 1 di 20» | «tentativo 1» | punto 4 del coordinatore: niente «di 20» fisso in Control Room |
- `npx vitest run src/pages/Mike src/components/mike src/lib/mike src/components/controlroom
  src/components/trading` -> **82 file, 1192 verdi, 1 saltato (preesistente)**; `tsc` 0 errori.
- Contratto Python dei parametri contro il `config.py` di master: tutto verde tranne
  `reentry_max_goals`, che su master (`7b6be41`) e' gia' portato a 2: controllo eseguito prima di
  P3 con il config di master in memoria (1 rosso atteso, solo `reentry_max_goals`); con P3 integrato
  il contratto e' allineato (il pannello dice 2/0-2 dal blocco 1).
- Il contratto dei kind di attivita': nessun kind scritto dal servizio di master manca in UI
  (confronto dei `db.log("...")` di master con `MIKE_ACTIVITY_KINDS`).

## 3. Falsificazione (`falsifica_mike_p6.mjs 5`): 10 mutazioni, 10 ROSSE
H1 etichetta vecchia dell'ultimo ingresso; H2 tick sopra il best presentato come attivo; H3 veto
che «si piazza col PERSIST»; H4 HOLD vecchio; H5 lettura fallita senza parole; H6 punteggio
assente come linea assente; H7 runner senza esito senza parole; H8 nota «non determinabile» tolta;
H9 la tabella non mostra la nota; H10 «di 20» finto a massimo ignoto.

## 4. Non verificato
- Le righe vere di P4 blocco 3 (`feed_line_missing` con `punteggio_assente`): il payload non l'ho
  riletto nel servizio; se oltre a `reason` porta `markets`, la riga resta comunque quella del
  punteggio (il caso speciale guarda solo `reason`).
- Dal vivo nulla (niente app).
