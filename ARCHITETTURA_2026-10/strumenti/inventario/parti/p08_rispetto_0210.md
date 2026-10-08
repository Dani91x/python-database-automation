## 8. Cosa e' cambiato rispetto a `SCHEMI_BOT/sistema/INVENTARIO_ARCHITETTURA.md` (02/10/2026)

Script: `c01_confronto_02_10.py` (`uscite/c01_confronto_0210.txt`, `c01_citazioni_0210.tsv`). Metodo: ognuna delle 277 citazioni `file:riga` dell'inventario del 02/10
viene riletta a `22d19cc` (la base dichiarata dall'inventario, `git show`) e il TESTO di quella riga viene cercato nel file di oggi: stessa riga / spostata (con la nuova riga) / testo cambiato o sparito.
Dal 02/10 sono passati 221 commit (6 il 02/10, 71 il 04/10, 23 il 05/10, 46 il 06/10, 65 il 07/10, 10 l'08/10: `git log --format=%cs 22d19cc..HEAD`).

{{file:c01_confronto_0210.txt}}

### 8.1 Che cosa significa

- **Le citazioni dell'inventario del 02/10 sono ancora valide come FATTI nel 98,5% dei casi** (149 alla stessa riga + 124 spostate = 273 su 277), ma il 44,8% non e' piu' al numero di riga indicato:
  `desktop/main.js` ha 22 citazioni su 24 spostate (i lanci dei servizi, citati dall'inventario a `:435-491` (A-2...A-10), oggi stanno a `:419-483`: e' stato **aggiunto il `backtest-worker`** e riscritto l'arresto ordinato), `omega_service.py` 15 su 15, `mike/service.py` 15 su 17.
  Le 3 citazioni il cui testo e' cambiato o sparito sono elencate in `c01_citazioni_0210.tsv` (esito `TESTO_CAMBIATO_O_SPARITO`: 2 in `desktop/main.js`, 1 in `Betfair/stream/scalper/scalper_bot.py`).
  Chi usa `INVENTARIO_ARCHITETTURA.md` deve ritrovare le righe con il TESTO, non col numero.
- **Quello che e' davvero nuovo dal 02/10** (da `git diff --name-status 22d19cc..HEAD`: 663 file aggiunti, 210 modificati, 0 cancellati; per cartella nella tabella sopra):
  1. **8 file Python di produzione nuovi** (nessuno tolto): `Betfair/stream/backtest/applica_bot.py` e `varianti_bot.py` («Applica bot» e varianti sul banco), `Betfair/stream/scalper/media_under_bot.py` (modalita'
     media under, 2.637 righe), `Betfair/stream/tennis_live/mercati_registrati.py`, `Betfair/stream/tennis_replay/{__init__,caricamento,convertitore,importa}.py` (Replay Tennis, 811 righe).
  2. **Un processo in piu' sotto watchdog**: `backtest-worker` (`desktop/main.js:469`, commit del 06/10 «il banco del replay parte con l'app»). L'inventario del 02/10 elencava 8 programmi sotto guardiano (A-2...A-9): oggi sono 9.
  3. **Frontend**: +46.180 righe aggiunte in `frontend/src` (174 file toccati), fra cui il «guscio v2» (`components/shell/`, `lib/uiShell.ts`), il replay professionale, `lib/replayBot.ts`, il catalogo generato `replayBotCatalogo.ts` (11.099 righe),
     `pages/TennisReplay.tsx`, il registro delle operazioni. Il numero di rotte e' 26.
  4. **Banco**: 11 bot registrati come il 02/10 (`registro_bot.py:217-401`: mike, omega, safe_base, safe_esatto, safe_punta, safe_tennis, scalper_calcio, tennis_scalper, tennis_pro, tennis_flb, tennis_swing).
  5. **Righe**: `bot_service.py` 10.862 -> 11.136, `omega_service.py` 8.709 -> 8.936, `mike/service.py` 7.496 -> 7.551, `mike/engine.py` 5.097 -> 5.359, `live_order_worker.py` 3.991 -> 3.997, `safe_strategy/service.py` 3.444 invariato
     (valori «a `22d19cc`» e «oggi» identici ai dichiarati: l'inventario del 02/10 conta giusto).
  6. **Migrazioni**: 6 file, +646 righe di SQL (`migrations/`); **documenti** e audit: `SCHEMI_BOT` +199.149 righe (gli schemi), `AUDIT_2026-10-04..08` +94.000 circa.
- **Che cosa NON e' cambiato** (verificato oggi sul codice): le 8 porte di lock e i 8 canali (A-19, C-4...C-11: sezione 5 di questo documento le conferma tutte, con le stesse porte); il watchdog (backoff 10-300 s, 5/h, codice 75, battito 30 s: `watchdog.py:73-105,248-252`);
  il client Supabase per thread (`db_client.py:75`); il doppio client Betfair (`betfairlightweight` + `requests`); il numero dei file DB «per bot».
- **Punti che l'inventario del 02/10 lasciava aperti** (sezione «Punti non chiariti», 6 punti) e che questo inventario NON chiude: 1 (chiamate Betfair non contate), 2 (Mike con login Betfair: `omega_market.py:508` e `certlogin` nei registri, `MISURE:212-213`, confermato dal codice),
  3-4 (Omega fermo, nessun tennis/scalper nella misura), 5-6 (sessione a domanda e canale all'avvio). Nessuna nuova misura di frequenza e' stata fatta qui (regola del compito).

