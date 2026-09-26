p = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.claude\worktrees\agent-a1bc87b400bbc7d7c\AUDIT_2026-09-25\E2E_FASE2_BOT_PAPER_2026-09-26.md"
s = open(p, encoding="utf8").read()
SEZ = """## ★ CRASH DEL RUNNER CALCIO 10:00:46Z (reperto grave di admin-26, analisi in SOLA LETTURA)

Evidenze: `e2e_fase2/crash_runner_canali_0958_1003.txt` (ascoltatore dei canali, estratto con
`finestra_canali.py 09:58:00 10:03:30 runner_calcio,scanner`), `live_alerts` 496-501, righe dei trade/attività.
**Lo stdout/stderr dell'app NON è stato catturato da nessun mio processo**: l'exe è stato avviato senza
redirezione e i miei ascoltatori leggono solo i websocket. Non c'è il traceback.

**Cronologia (UTC)**
| ora | fonte | fatto |
|---|---|---|
| 09:42:44 | `scalper_activity` | l'auto-mode dello scalper arma 36090936/37 (a freno tirato, R-F2-10) |
| 09:43:30 → 09:43:35 | 47331 `auto_follow` | `mercati_sottoscritti` 17 → **0** → 32 (`mercati_manuali` 17 → 32): risottoscrizione dopo il `segui` |
| 09:57:40-09:59:40 | conteggi 47331 | `ladder` al minuto 174 → 87 → 14 (fine delle partite J-League) |
| 09:59:48 | `scalper_activity` | auto-mode arma 36090941 (Imabari–Shonan, a fine partita) → `db.segui` |
| 09:59:49 | `live_alerts` 496 | `NEW_MATCHES` «1 nuove partite agganciate al live» |
| 09:59:58 | 47331 `battito` | ultimo battito prima del crash (`mode LIVE+PAPER`) |
| 10:00:30 | 47331 `auto_follow` | `mercati_seguiti` 32, **`mercati_sottoscritti` 0**, `ultimo_errore` null |
| **10:00:46** | ascoltatore | **47331 chiuso** (`ConnectionClosedError`), poi `ConnectionRefused` ogni 5 s fino alle 10:01:21 |
| 10:01:06 | `live_alerts` 497 | `RUNNER_WATCHDOG` «RUNNER CRASHATO: exit code 1, uptime 3858s. Riavvio n. 1 tra 10s» |
| 10:01:22 | `live_alerts` 498 | `ORDER_MODE` «Live trading: modalità LIVE attiva. *** LIVE *** ORDINI REALI (SOLDI VERI) attivi» |
| 10:01:22 | `live_alerts` 499 | `RUNNER_RESUME` «specchio paper pulito (10 ordini, 0 posizioni), 0 richieste stantie scartate» |
| 10:01:24 | 47331 | di nuovo in ascolto: `hello mode=LIVE`, `modo_ordini` 10:01:26 **effettivo PAPER**, tetto LIVE, kill false |
| 10:01:28 | `live_alerts` 500 | `RECONCILE` «ripresa LIVE: 0 ordini correnti sul conto, 0 esterni, 91 righe specchio» |
| 10:04:31-32 | scalper + alert 501 | l'auto-mode arma 36111770 → `NEW_MATCHES` |
| 10:05:17-20 | 47331 `auto_follow` | seguiti 32 → 20 → 25, `ultimo_errore` «stream di mercato non ancora connesso», `risottoscrizioni` 1 |

Canale muto per **38 s** (10:00:46-10:01:24). `betfair_live_heartbeat`: 0 righe fra 09:59 e 10:03 (tabella non
usata oggi come battito del runner: il battito è sul canale).

**Esito per bot**
- **Omega**: non ha perso il feed. Il feed unico è un processo a parte (47336): i conteggi `scan_calcio` al minuto
  sono continui (229, 267, 210) e `omega_stato` esce 12 volte al minuto anche durante il buco. Dalle 10:00 alle
  10:02 fa solo 3 `skip` (10:01:22-47Z). Posizione aperta al crash: **118** (lay AOHW 36090941), regolata `won`
  +0.95 alle 10:02:54Z, una volta sola, nessuna riga doppia. I suoi ordini paper non passano dal runner (R-F2-2),
  quindi non c'era niente da perdere nello specchio.
- **Mike**: non ha perso il feed. Posizioni aperte al crash: 5070 e 5071 (partite femminili al fischio delle
  10:00Z). Transizioni `LIVE_KO_GREEN` e `uscita_proposta` alle 10:00:10-20Z, poi `under_second` 5072 alle
  10:02:45Z e coperture 5073-5075: tutte REST paper, non dipendono dal runner. Nessuna riga doppia.
- **Safe**: nessuna posizione calcio aperta (342 e 343 regolate alle 09:55-09:56Z); Safe tennis 344 alle
  10:04:01Z (REST). Nessuna attività anomala nella finestra.
- **Scalper**: le sessioni sono processi a parte con un loro stream: 36090936 si ferma alle 10:00:41-43Z
  (`stop richiesto: force-flat`, fine partita), 36111764 si arma alle 10:01:04Z durante il buco del runner. Nessun
  errore di sessione.
- **Tennis**: runner tennis (47332) non toccato (conteggi continui).
- **Specchio paper del runner**: «pulito 10 ordini, 0 posizioni» alla ripresa. `betfair_live_orders` non ha
  righe dal 25/09, quindi quei 10 ordini erano nel blotter in memoria del runner: NON so quali (nessun log).

**Reperti del crash (nessuna correzione)**
- **R-F2-C1 (KO, grave)**: il runner calcio va in crash (exit 1) dopo 3858 s. Il watchdog lo riavvia in 36 s.
  Causa NON verificabile senza log. Correlazione osservata: il crash cade 57 s dopo un `NEW_MATCHES` provocato
  dal `segui` dell'auto-mode dello scalper (09:59:48-49Z), mentre `auto_follow` segnava `mercati_sottoscritti = 0`
  con 32 seguiti (10:00:30Z). Lo stesso schema (seguiti che salgono, sottoscritti a 0) si era già visto alle
  09:43:30Z senza crash, e alle 10:05:17Z con «stream di mercato non ancora connesso». Ipotesi da verificare col
  traceback: risottoscrizione dello stream a caldo durante un `segui` a fine partita.
- **R-F2-C2 (KO di comunicazione, grave per il trader)**: a ogni avvio del runner l'alert `ORDER_MODE` dice
  «*** LIVE *** ORDINI REALI (SOLDI VERI) attivi» (498, 10:01:22Z), mentre l'effettivo è PAPER (`modo_ordini`
  10:01:26Z, effettivo PAPER, `scelto_ui` PAPER). L'alert racconta il TETTO del `.env`, non la modalità effettiva.
- **R-F2-C3**: la console dell'app non finisce in un file (`runner.py:2325` fa `basicConfig` sulla console,
  l'exe non la redirige): un crash in produzione non lascia traceback.
- **Doppi ordini / righe orfane dopo la ripresa**: nessuno sulle tabelle dei bot (verificate `omega_trades`,
  `mike_trades`, `safe_strategy_trades`, `betfair_live_orders`, `betfair_live_order_requests`: nessuna riga nuova
  nella finestra oltre a quelle elencate sopra).

"""
anchor = "## 0. Come si è acceso (dichiarazione obbligatoria)"
assert anchor in s
s = s.replace(anchor, SEZ + anchor, 1)
open(p, "w", encoding="utf8").write(s)
print("ok")
