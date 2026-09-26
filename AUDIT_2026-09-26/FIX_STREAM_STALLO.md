# FIX_STREAM_STALLO - R-STREAM-1 + K2 + F-9 (+ watchdog e guasti di rete, dal messaggio del coordinatore)

Delegato di correzione, 26/09/2026. Worktree `agent-a59ff5d4e5acb408c`. Niente commit, niente `.env`, niente DB.
Nessuna strategia toccata (soglie, stake, ingressi, uscite): solo rilevamento, riavvio del processo, log, testi.

## File toccati (tutti)

| File | Cosa |
|---|---|
| `Betfair/stream/runner_lifecycle.py` | +`classifica_messaggio_stream` (168), +`verdetto_post_ricostruzione` (190), +`e_errore_di_rete` (225): funzioni pure condivise |
| `Betfair/stream/raw_listener.py` | battito dati/heartbeat anche a tee SPENTO (157) |
| `Betfair/stream/runner.py` | cancello dello stallo (1317), escalation (1157, 1391, 1442), mercati sottoscritti (1145, 2426), guardia di rete (1132, 2128, 2211), finally senza chiusura follow su riavvio per stallo (2466), F-9 (1746, 2091) |
| `Betfair/stream/tennis_live/tennis_recorder.py` | battito dati/heartbeat su ogni messaggio (132) |
| `Betfair/stream/tennis_live/tennis_runner.py` | `stall_worker` (1850), escalation (1892), guardia d'uscita (1829), registrazione worker (2828), epoca stream (2855), guardia di rete sulla lettura follow (2637) |
| `Betfair/stream/watchdog.py` | `messaggio_crash` con il modulo sorvegliato (104, 283) |
| `desktop/main.js` | K2: blocco `K2-LOG-FIGLI` (218-281), scrittura nel pipe (331-350), env `PYTHONUNBUFFERED`/`PYTHONIOENCODING` (320), avvio (769) |
| `.gitignore` | `_logs/` |
| nuovi | `Betfair/stream/tests/test_stream_stallo_2026_09_26.py` (34 test), `test_annuncio_modo_2026_09_26.py` (8), `test_watchdog_nome_modulo_2026_09_26.py` (4), `AUDIT_2026-09-26/verifica_log_figli.js`, `falsifica_log_figli.py`, `falsifica_stallo.py`, questo referto |

## A. R-STREAM-1 - runner cieco 4 ore

**Causa 1 (runner.py:1192 vecchio):** `if h.get("enabled") and session.market_to_event:`. `market_to_event` contiene SOLO i follow
manuali; i mercati dell'auto-follow (26/09: 0 manuali, 32 partite) non ci sono -> il controllo di stallo non girava mai. Il
cancello su `enabled` lo spegneva anche col tee raw spento.
**Causa 2 (raw_listener.py:`write_message`):** a tee spento `return` immediato, PRIMA di aggiornare `last_data_ms`/`last_heartbeat_ms`.
**Causa 3:** la ricostruzione nello stesso processo (14:39Z) non ha ridato dati e non c'era nessun gradino successivo.
**Causa 4 (tennis):** nessun controllo di stallo nel runner tennis; il tee tennis tornava subito senza partite registrate.

**Correzione:**
1. `runner.py:1317` il controllo gira se `_mercati_sottoscritti(session) > 0` = max(mappa manuali, `stream_market_count`), fissato a
   ogni `framework.run()` con TUTTI i mercati sottoscritti (`runner.py:2426`).
2. `raw_listener.py:157` e `tennis_recorder.py:132`: battito per regex (`classifica_messaggio_stream`, niente `json.loads`, niente disco).
3. Escalation (`_escalation_stallo`, runner.py:1157): dopo una ricostruzione per stallo (`stallo_rebuild_mono`, 1442) si osserva:
   `verdetto_post_ricostruzione` -> passata la finestra (**180 s**, `LIVE_STALL_POST_REBUILD_SEC`), ESCALA se nessun dato e' arrivato
   dopo la ricostruzione (subscription rotta anche a heartbeat freschi) oppure se lo stallo EFFETTIVO (dati E heartbeat) e' di nuovo
   >= 180 s (il caso 26/09: 89 ladder poi tutto fermo, alert 503 = stallo effettivo > 120 s); GUARITO dopo 900 s di osservazione.
   Un mercato quieto dopo l'immagine (heartbeat freschi) NON escala (niente riavvii a raffica di notte). Durante l'osservazione la
   ricostruzione normale non riparte.
   Escala = `planned_restart` + `shutdown_requested` + `_stop_framework` -> `_main` esce con **75** e il watchdog rilancia.
   Guardia money-critical: `_lifecycle_blockers` (ordini vivi, regole armate, DB illeggibile = resta), ricontrollata `fresh=True`
   subito prima dello stop (TOCTOU 17/07); bloccata -> alert CRITICAL al piu' ogni 5 min e nuovo tentativo al giro dopo (10 s).
   Solo con `LIVE_RUNNER_KEEP_ALIVE=1` (app desktop, watchdog presente): senza, un'uscita lascerebbe il runner morto -> resta il
   ciclo di prima.
4. **Finally del calcio (runner.py:2466):** con `riavvio_per_stallo` NON si finalizzano gli eventi. Prima ogni uscita del processo
   metteva CLOSED (e caricava nel Replay) tutte le partite seguite: il processo nuovo non le avrebbe riagganciate.
5. Tennis (stessa forma, stesse funzioni pure): `stall_worker` ogni 10 s (tennis_runner.py:1850, registrato a 2828); ricostruzione
   via `_request_restart(..., forza=False)` (mai forzata, stessa guardia dei bot non flat); escalation `_escala_stallo_tennis` (1892)
   con guardia `_tennis_blocker_uscita_stallo` (disarm in corso, bot NON flat, ordini vivi nel blotter). Soglie env dedicate
   `TENNIS_RAW_STALL_*`, `TENNIS_STALL_POST_REBUILD_*` (stessi default del calcio). Il finally del tennis non chiude i follow.

## Guasti di rete che uccidevano il processo (messaggio del coordinatore, punto 3)

Punti trovati dove un'eccezione di rete risaliva fino a `main` (exit 1) FUORI da `framework.run()` (che e' gia' protetto):
- `runner.py` (vecchia ~1980) `follows = db.list_pending_follows()` nel ciclo principale, **anche nel giro idle ogni ~2 s**: un
  DNS/timeout Supabase = crash. In piu' il `finally` chiudeva tutti i follow. -> **corretto** (2128).
- `runner.py` `_catalog_events(rest, ...)` (REST `listMarketCatalogue`, `RuntimeError` dopo 3 retry) alla ricostruzione -> **corretto** (2211).
- `tennis_runner.py` `tennis_db.list_pending_tennis_follows()` nel ciclo principale (anche idle ogni 2 s) -> **corretto** (2637).
Correzione: `e_errore_di_rete` (solo trasporto: `ConnectionError`, `TimeoutError`, `socket.gaierror/herror`, `requests.RequestException`,
`httpx.TransportError`, il `RuntimeError` "RPC failed after ... Network error" di `BetfairClient._rpc`, anche nella catena
cause/context; NON ogni `OSError`) -> avviso, 15 s, nuovo giro. Tutto il resto si RILANCIA.
NON corretti (elencati): login iniziale `rest.login_cert()`/`build_client(login=True)` prima del ciclo (crash-restart del watchdog
accettabile all'avvio); nel tennis gli altri accessi DB del build (`set_tennis_bot_status`, `set_tennis_follow_status`,
`_ET.follows_con_comandi`) restano non protetti; nel calcio `_sync_record_events` e' gia' protetto. Il crash tennis 15:04:20Z
(uptime 611 s) NON e' attribuibile senza traceback: con K2 il prossimo sara' in `_logs/runner-tennis_*.log`.

## Watchdog: quale processo e' caduto

`watchdog.py:104` `messaggio_crash(target, rc, uptime)` -> `RUNNER CRASHATO [Betfair.stream.tennis_live.tennis_runner]: exit code 1,
uptime 611s.`; usato per alert E Telegram (anche il "Riavvii/ora esauriti").

## B. K2 - console dei figli su file (fatto per primo)

Una sola via: `desktop/main.js` (nessun `FileHandler` nei runner). `<repo>/_logs/<label>_<ISO-avvio>.log`, un file per figlio e per
avvio dell'app (i riavvii del watchdog finiscono nello stesso file, perche' il figlio del watchdog eredita il pipe), riga per riga con
timestamp ISO e tag (`[runner-calcio:err] ...`), piu' righe `avviato (pid)` e `terminato (exit N)`. All'avvio cancella i `.log` con
mtime > 7 giorni (solo `.log`). Cartella/file non scrivibili -> solo console con avviso, mai blocco (stream con handler `error`).
Aggiunti all'ambiente dei figli `PYTHONUNBUFFERED=1` e `PYTHONIOENCODING=utf-8` (su pipe python bufferizzava stdout e scriveva cp1252
mentre il pipe legge utf8: righe perse al kill e accenti/frecce rotti). `_logs/` in `.gitignore`. Exe NON ricompilato; il blocco non
richiede moduli nuovi (il fallback del main.js impacchettato resta valido).

## C. F-9 - banner del modo ordini

Causa `runner.py:1610-1629` vecchio: banner/alert dal solo tetto `.env`. Correzione: `_testo_modo_ordini` (1746) e chiamata con
`_MO.modo_effettivo(modo_avvio, _MO.valore_db())` (2091) = la stessa regola del gate (piu' restrittivo; non letta -> OFF). Se diverso
dal tetto: `tetto LIVE, effettivo PAPER -- PAPER -- ordini SIMULATI ...`. CRITICAL solo con effettivo LIVE. Gate degli ordini
invariato. Il tennis (`tennis_runner._announce_order_mode`, env propria `TENNIS_LIVE_ORDER_MODE`) NON toccato: fuori brief.

## Test (RED -> GREEN) e falsificazione

Comandi (dalla radice del worktree/repo, PowerShell):
```
$env:SUPABASE_URL="http://127.0.0.1:9"; $env:SUPABASE_SERVICE_ROLE_KEY="x"; $env:SUPABASE_KEY="x"
python -m pytest Betfair/stream/tests/test_stream_stallo_2026_09_26.py Betfair/stream/tests/test_annuncio_modo_2026_09_26.py Betfair/stream/tests/test_watchdog_nome_modulo_2026_09_26.py -q -p no:cacheprovider
python AUDIT_2026-09-26/falsifica_stallo.py        # 19 mutazioni nel file VERO, ripristino + sha256 (NON interrompere)
node AUDIT_2026-09-26/verifica_log_figli.js        # K2 sul main.js vero: spawnRunner reale con figlio che crasha
python AUDIT_2026-09-26/falsifica_log_figli.py     # 6 mutazioni su COPIE di main.js
```
Esiti miei: 46 test nuovi verdi; `falsifica_stallo.py` 19/19 ROSSE (M1 = il cancello storico, M2/M3 = battito solo a tee acceso,
M4-M15 escalation/guardie/rete/finally, M16-M18 F-9, M19 watchdog), sha256 ripristinati, a codice intatto verdi.
`verifica_log_figli.js` 12/12 verdi; sul main.js ORIGINALE (HEAD) rosso; `falsifica_log_figli.py` 6/6 ROSSE, main.js vero intatto.
Regressioni: 275 test esistenti dei moduli toccati (stall/raw/recmeta/lifecycle/watchdog/record_optin/modo/runner/heartbeat/battito +
tennis recorder/runner) verdi; cartella `Betfair/stream/tennis_live/tests` intera 513 verdi. `node --check desktop/main.js` OK.

Nota onesta: tre test sono controlli sul SORGENTE di `setup_and_run` (monolitico, non eseguibile senza Betfair): cablaggio di
`stream_market_count`, delle guardie di rete, del finally e del `stall_worker`. La logica e' provata sulle funzioni estratte.

## Cosa NON ho potuto verificare

- Nessun replay/stream Betfair vero: il comportamento reale di flumine dopo una caduta di rete (riconnessione interna, se l'immagine
  arriva dopo un resubscribe) non e' riprodotto; i finti sono i messaggi grezzi Betfair e le sessioni vere.
- L'uscita 75 -> rilancio del watchdog e il riaggancio delle partite nel processo nuovo sono garantiti dai test esistenti del watchdog
  (`classify_exit`) e dal codice di avvio, non da una prova end-to-end.
- La causa dei crash exit 1 di oggi (calcio 10:00:46Z e 14:46:15Z, tennis 15:04:20Z): senza traceback. Ipotesi compatibile: la lettura
  dei follow fallita per rete (ora protetta). Da verificare nei `_logs/` al prossimo crash.
- K2 provato con node puro, non dentro Electron; serve il riavvio dell'app da parte dell'utente.

## Rischi residui

- Uscita per VITA MASSIMA 18 h (pre-esistente, fuori perimetro): il `finally` del calcio chiude ancora tutte le partite seguite
  (CLOSED + upload) a ogni ricambio pianificato; lo stesso vale per un crash non di rete. Da decidere se estendere il salto del
  finalize anche al ricambio pianificato.
- Mercato davvero muto > 30 min (hard-cap) con heartbeat freschi: ricostruzione soft; se l'immagine arriva, nessuna escalation.
- Escalation bloccata a lungo da regole armate / DB illeggibile durante un'interruzione di rete: resta cieco finche' non si sblocca
  (scelta prudente, alert CRITICAL ogni 5 min).
- Finestra TOCTOU residua di pochi ms fra l'ultimo check dei blocker e il `TerminationEvent` (gia' dichiarata il 17/07).
