# Migrazione arretrati_prova (30/09/2026)

File: `migrations/mike_state_arretrati_prova_2026-09-30.sql` (da applicare a cura dell'utente).

- Definizione viva presa: `migrations/mike_bot_v2.sql:149-196` (piu' recente; `mike_bot.sql:247` e' superata; nessun'altra migrazione la ridefinisce, verificato con grep su `migrations/*.sql`).
- Diff contro il corpo vivo: 1 sola riga rimossa (il `RETURN ... 'day_by', 'placed');` esteso con la nuova chiave); il resto e' aggiunta (variabili `v_arr`, `v_oggi`, la query ricorsiva, la chiave). Firma, SECURITY DEFINER, search_path, REVOKE/GRANT identici.
- Chiavi della risposta viva (RPC letta in sola lettura): activity, aggregates, control, day_by, day_start, events, requests, trades: le stesse 8 che la funzione della migrazione conserva.
- Logica: gambe paper con `settled_at` nel giorno di Roma di oggi; si risale `closes_trade_id` fino all'apertura; si tiene la gamba se giorno di Roma di `coalesce(mike_events.ko_at, apertura.placed_at)` < oggi. Tetto `LIMIT 2000` (ordine settled_at DESC, id DESC). Chiave sempre presente, `righe: []` se vuota.
- Prova (sonda `AUDIT_2026-09-30/sonda_arretrati_prova.py`, stessa logica con query normali): 5 righe selezionate su 5 paper regolate oggi, 0 live regolate oggi: ids 5077, 5078, 5080, 5081 (evento 36109477, lost -5.0 -2.5 -6.4 -6.67) e 5082 (evento 36093027, won +2.28), regolate 2026-09-30 12:41 UTC, tutte `closes_trade_id` nullo.
- Test: `Betfair/mike/tests/test_mike_migrazione_arretrati_prova_2026_09_30.py` (3 passati; falsificato: ogni campo tolto, chiave rinominata, filtro paper tolto -> rosso).
- Non verificato: la funzione SQL NON e' stata eseguita (migrazione non applicata; la sintassi plpgsql/CTE ricorsiva non e' stata provata su Postgres). Le verifiche commentate in coda al file vanno lanciate dopo l'applicazione, da ruolo owner.
