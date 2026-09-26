p = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.claude\worktrees\agent-a1bc87b400bbc7d7c\AUDIT_2026-09-25\E2E_FASE2_BOT_PAPER_2026-09-26.md"
s = open(p, encoding="utf8").read()
SEZ = """## ★ RUNNER CALCIO «CIECO» 10:01Z → riavvio: riscontro dalle MIE registrazioni (14:50Z)

Richiesta del coordinatore (ipotesi di admin-26: runner cieco dal riavvio post-crash delle 10:01Z fino
all'alert 502 delle 14:39Z). Evidenze: `e2e_fase2/ladder_fasce.txt` (script `ladder_fasce.py`: conteggi al
minuto e campioni interi del 47331/47332, un campione per topic al minuto), query in sola lettura su
`live_now`, `tennis_live_now`, `tennis_bot_activity`, `tennis_bot_control`, `safe_strategy_scan`, `live_alerts`.

**(2) «zero tick di mercato dalle 10:01Z»: per la finestra 10:01-10:42Z le mie registrazioni lo SMENTISCONO.**

| fascia UTC | ladder 47331 (calcio) | payload distinti nei campioni | eventi | ladder 47332 (tennis) |
|---|---|---|---|---|
| 09:50 | 2842 | 9/9 | 36090788, 36090854, 36090936 (J-League, finiscono) | 858 |
| 10:00 (crash 10:00:46, ripresa 10:01:24) | 4390 | 9/9 | 36090941, 36111764, 36111770 | 1072 |
| 10:10 | 6090 | 10/10 | 36111764, 36111770 (femminili) | 1036 |
| 10:20 | 6055 | 10/10 | idem | 1075 |
| 10:30 | 6176 | 10/10 | idem | 1634 |
| 10:40 | 1198 (ultimo minuto pieno 10:41:40 = 557; 10:42:40 = 14) | 3/3 | idem | 261 |
| 10:50 | **0** | — | — | **0** |

Dopo il crash il runner pubblica ladder VIVE (prezzi e `updated_ms` che cambiano; es. 10:42:36Z HT Score
36111770 `updated_ms` 10:41:39Z) sulle due partite seguite. `live_now` dei due eventi femminili si aggiorna
(ora 14:45Z). Quelli fermi a 09:55-10:02Z sono le partite J-League FINITE (36090854/36/37/41), quindi non
sono una prova di cecità. **Tutto si ferma alle 10:42Z, INSIEME:** ladder calcio e tennis, `scan_calcio`
dello scanner (259 → 7 al minuto), il `battito` del runner (6 → 1). Nello stesso minuto le mie sonde verso
Supabase hanno iniziato a fallire con `getaddrinfo failed` / `ConnectionAborted` (sentinella, 10:41-10:48Z):
**interruzione di rete / DNS del PC alle ~10:42Z**. La cecità nasce lì, non alle 10:01Z. Gli alert 502
(14:39:12Z, «stream mercati MUTO da 14251 s»: 14:39:12 − 14251 s = **10:41:41Z**) e 503 (14:42:46Z) lo
confermano. Nuovo **crash del runner calcio alle 14:46:15Z** (alert 505, uptime 17099 s = avviato alle
10:01:16Z), riavvio n. 2, di nuovo `ORDER_MODE` «*** LIVE ***» (506) con effettivo PAPER (R-F2-C2).

**(3) Runner tennis / bot tennis: NON sani dalle 10:42Z.** `tennis_live_now` si aggiorna (14:48Z), ma:
nessuna riga in `tennis_bot_activity` dopo le 10:41:35Z per nessuno dei 4 bot (ultime: flb/pro 10:40:18,
scalper 10:40:21, swing 10:41:35); `tennis_bot_control` fermo alle 10:40:00Z con **12 righe attive per bot**
(tetto 5, vedi R-F2-6); ladder 47332 a zero dalle 10:42Z; `safe_strategy_scan` tennis più recente alle
14:34:51Z (14 min prima). I battiti dei servizi sono freschi (`heartbeat_at` 14:48:05Z), quindi vivi ma
senza decisioni: stesso quadro «battito fresco, dati morti». Gli ordini tennis già eseguiti
(`tennis_live_orders` flb 1, swing 7) vengono ancora riscritti ogni secondo (R-F2-7).

**(4) Effetto sulle righe già scritte del referto**
- Fino alle 10:42Z il runner calcio e il tennis erano vivi: restano validi Z4.T1-T3, R-F2-6/7, la sezione
  crash, 3-bis A (10:07Z), B Omega 120 e C Safe/Mike, P&L, D (09:34/09:59Z), freno (09:42-09:56Z).
- **Dalle 10:42Z: NON CERTIFICATO «runner cieco / rete caduta»** tutto ciò che passa dal runner calcio
  (ladder, fill flumine, specchio, registrazioni, F0 via runner), dal runner tennis e dai 4 bot tennis.
  Omega, Safe e Mike girano sul feed dello scanner (attività fino alle 14:47Z): le loro decisioni dopo le
  10:42Z restano valutabili solo con quella nota. Nel buco di rete lo scanner stesso si è fermato.
- **I miei strumenti si sono fermati**: `raccolta_db.py` ultimo giro alle 10:38Z; `ascolto_scanner.py`
  ultimo file alle 10:41Z; `ascolto_canali.py` ultimo messaggio alle 10:58:16Z. Dopo li ha fermati Claude
  Code per memoria bassa del PC. Non li ho riavviati. Dalle 10:42Z non ho registrazioni proprie.

**(5) Reperti di admin-26 riscontrati**
- «nessun ordine passato dalla coda DB»: **CONFERMATO** (R-F2-2). 0 righe in `betfair_live_order_requests`
  e `betfair_live_orders` oggi; Omega/Safe `paper_fill*:follow_assente`, Mike `paper_fill:execution_mode_rest`.
- Mike riempie in paper al prezzo limite: coerente con quello che ho visto. 5070-5075 hanno
  `avg_price_matched` = `price` richiesto e `size_matched` = size. Non l'ho confrontato col best del feed
  dell'istante: NON verificato da me.
- scalper `live_follow` senza origine: NON verificato da me.

**(1) Secondo ciclo del freno: SOSPESO**, come ordinato. Si rifà solo dopo il riavvio dell'app da parte
dell'utente.

"""
anchor = "## 0. Come si è acceso (dichiarazione obbligatoria)"
assert anchor in s
s = s.replace(anchor, SEZ + anchor, 1)
s = s.replace("**Stato del referto: AGGIORNAMENTO 2 — 12:15 locali (10:15Z).**",
              "**Stato del referto: AGGIORNAMENTO 3 — 16:50 locali (14:50Z).**")
open(p, "w", encoding="utf8").write(s)
print("ok")
