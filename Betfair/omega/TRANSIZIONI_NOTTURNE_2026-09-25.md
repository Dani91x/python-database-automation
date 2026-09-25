# Transizioni di Omega aggiornate ogni notte (O2, 25/09/2026)

Migrazione: `migrations/omega_transitions_catchup_2026-09-25.sql` (la applica l'utente).
Verifica: `python -m Betfair.omega.tools.verifica_transizioni_2026_09_25`.
Referto completo con numeri e alternative: `AUDIT_2026-09-25/O2_TRANSIZIONI_OMEGA_2026-09-25.md`.

## Cosa faceva

- `omega_minute_transitions` (veto empirico di Omega, `get_omega_minute_ft`) e
  `omega_ht_ft_transitions` (ripiego di Omega e blend dei gol di Mike, `get_omega_ht_ft`)
  sono state costruite **una volta**, l'11/09 (minuto: 27 min, 939.506 partite valide;
  HT->FT: una sola istruzione), e da allora sono ferme.
- Il costruttore del minuto procede per `matches.id` e **somma** (`n = n + EXCLUDED.n`).
  Le partite entrano in `matches` prima di giocarsi (backfill stagionale) e diventano FT
  dopo: un recupero "id > ultimo id" le perde (1.556 partite FT dal 11/09 con id gia'
  passato), un recupero "ripassa il lotto" le conta due volte.
- pg_cron era attivo ma nessun job `omega_*` era mai stato schedulato.

## Cosa fa

1. **Registro per partita** `omega_transitions_ledger` (una riga per `fixture_id`):
   `ht_ft_at` e `minute_at` = quando e' stata contata in ciascuna tabella. Si conta solo
   cio' che il registro non ha, e il registro si scrive nella stessa transazione dei
   conteggi: rilanciare e' innocuo (n non cambia).
2. **Conteggi grezzi** `omega_minute_transitions_raw` e `omega_ht_ft_transitions_raw`:
   tutte le leghe, mai potate. Le tabelle lette dai bot sono la **pubblicazione** del
   grezzo: minuto = globale (0) + leghe con almeno `min_league_matches` partite valide
   (1000, come prima); HT->FT = tutto (come prima). Una lega che supera la soglia viene
   pubblicata per intero dal grezzo nel passo stesso.
3. **Giro notturno** `omega_transitions_nightly(p_budget_s)` alle **04:00 UTC** (pg_cron):
   - A. finestra calda: partite FT con `fixture_date` negli ultimi 10 giorni non ancora
     contate (serve l'indice su `matches(fixture_date)`; senza, la fase e' saltata e il
     referto lo dice: `hot_skipped_no_index = true`);
   - B. cursore per id: la ricostruzione (prima volta, dal 0) e poi le righe nuove;
   - C. giro di controllo a rotazione, 100.000 id a notte (tutto lo spazio in ~16
     notti): partite finite tardi fuori finestra e partite scartate (gol negli eventi
     diversi dal finale) da ricontrollare quando gli eventi arrivano.
   Una riga di referto per giro in `omega_transitions_runs`.
4. **Ricostruzione una tantum** nel grezzo, a lotti, entro il budget di ogni notte: i bot
   continuano a leggere i numeri dell'11/09 finche' non si **pubblica a mano**
   (`omega_transitions_publish('PUBBLICA')`), dopo la verifica. La pubblicazione e' una
   sola transazione: chi legge vede i numeri vecchi fino al commit, poi i nuovi.
5. I vecchi costruttori (`omega_build_minute_transitions_*`, `omega_build_ht_ft_transitions`)
   rifiutano con un messaggio: non si puo' piu' contare due volte per errore.

Le RPC dei bot non cambiano. Per le partite gia' contate i numeri restano quelli (le
definizioni sono le stesse); cambia solo che crescono ogni notte. Omega rilegge le
tabelle ogni 6 ore (`EMPIRICAL_CACHE_TTL_S`); **Mike le tiene in memoria per tutta la vita
del processo** (`Betfair/mike/dossier.py:113-141`): vede i numeri nuovi al riavvio.

## Come si verifica

```
python -m Betfair.omega.tools.verifica_transizioni_2026_09_25                   # tutto
python -m Betfair.omega.tools.verifica_transizioni_2026_09_25 --confronto pre   # prima di pubblicare
python -m Betfair.omega.tools.verifica_transizioni_2026_09_25 --confronto post  # dopo
python -m Betfair.omega.tools.verifica_transizioni_2026_09_25 --salva-impronta a.json
python -m Betfair.omega.tools.verifica_transizioni_2026_09_25 --confronta-impronta a.json
```

Valori attesi (lo script stampa i numeri, il giudizio e' di chi legge):
- A: `leghe diverse 0` per grezzo e pubblicato, minuto e HT->FT; globale = registro;
- B: celle con n <= 0 = 0 nelle quattro tabelle;
- C: `built_at` massimo >= la data dell'ultimo giro con partite contate;
- D: pubblicate non ammesse = 0, ammesse non pubblicate = 0;
- E: contatori per lega uguali al registro;
- F: un secondo giro lanciato subito dopo conta 0 partite (salvo partite arrivate nel mezzo).

Stato in SQL: `SELECT public.omega_transitions_status();` (stato, ultimi 10 giri, job e
ultime esecuzioni pg_cron, indici, copia dell'11/09).

## Cosa fare se il cron salta

- **Nessun dato perso**: il giro successivo riparte dai cursori e dal registro. Si puo'
  lanciare a mano quante volte si vuole: `SELECT public.omega_transitions_nightly(90);`
  (90 s: sotto il timeout del gateway dell'SQL editor; ripetere finche' `status = 'ok'`).
- Se e' saltato per **piu' di 10 giorni**, allargare una volta la finestra calda:
  `SELECT public.omega_transitions_nightly(90, false, 5000, 60);` (60 giorni). Comunque il
  giro di controllo recupera tutto entro un ciclo (~16 notti).
- Il job non c'e' piu': `SELECT public.omega_transitions_schedule(true);`.
  Spegnerlo: `SELECT public.omega_transitions_schedule(false);`.
- Il giro finisce in `status = 'errore'`: il lavoro di quel giro e' annullato (cursori
  fermi), l'errore e' nella colonna `error` di `omega_transitions_runs`. Si ripete da solo
  la notte dopo: se l'errore si ripete e' un dato anomalo da guardare, non un transitorio.
- Il giro non lascia nessuna riga in `omega_transitions_runs`: e' stato cancellato prima di
  finire (statement timeout del ruolo o riavvio del DB). Guardare
  `status().cron_last_runs[].return_message`; il comando schedulato alza il timeout a 20
  minuti per il solo giro.
- Numeri sbagliati dopo la pubblicazione: `SELECT public.omega_transitions_unpublish('RITORNA');`
  rimette le tabelle dell'11/09 (copia fatta alla pubblicazione); registro e grezzo restano.

## Limiti dichiarati

- Una partita gia' contata e poi **corretta** in `matches` o `match_events` (punteggio
  rettificato) non viene ricontata: il registro dice "gia' contata". Il confronto `pre`/`post`
  (`cells_lower`) e le differenze dell'invariante A non la vedono, perche' sono coerenti col
  registro. La difesa e' una ricostruzione completa (nuovo registro) se un giorno serve.
- Le partite senza `fixture_date` recente e con id gia' passato dal cursore si prendono solo
  col giro di controllo: ritardo massimo ~16 notti.
