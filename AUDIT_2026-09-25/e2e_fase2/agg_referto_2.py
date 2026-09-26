p = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.claude\worktrees\agent-a1bc87b400bbc7d7c\AUDIT_2026-09-25\E2E_FASE2_BOT_PAPER_2026-09-26.md"
s = open(p, encoding="utf8").read()


def rep(a, b):
    global s
    assert a in s, a[:80]
    s = s.replace(a, b)


rep("**Stato del referto: AGGIORNAMENTO 1 — 11:35 locali (09:35Z).** Il file viene riscritto a ogni aggiornamento.",
    "**Stato del referto: AGGIORNAMENTO 2 — 12:15 locali (10:15Z).** Il file viene riscritto a ogni aggiornamento.")
rep("| Z13.4 | FRENO | non ancora eseguito (dopo la prima partita in gioco completa per ogni bot) | in attesa |",
    """| Z13.4 | FRENO (1° ciclo) | `RigaFreno` VERA, guardia: solo `set_live_kill_switch` (falsificazione F0: p_on sbagliato e altre RPC bloccate). Tirato 09:42:00Z (1 clic), rilasciato 09:56:28Z (3 clic; dopo 2 ancora tirato). `e2e_fase2/freno/F1_*`, `F2_*`, `attesa.log` | Omega **OK** (3 tentativi rifiutati `kill_switch/db_kill_switch_attivo`, riserve cancellate); scalper force-flat **OK** ma R-F2-10/11; Safe/Mike/tennis **NON CERTIFICATO** (nessun tentativo nei 14 min). 2° ciclo autorizzato dal coordinatore dopo le 13:30Z |
| Z13.5 | uscite manuali = proposte | Omega: nessuna uscita discrezionale eseguita (sulle selezioni aggregate non c'è proposta: `skip proposta_uscita selezione_aggregata`); Safe: `cashout` 265 `proposed` + `exit_hold in_attesa_di_approvazione` fino al fischio; Mike: `uscita_proposta` green_pre / ko_green / `chiusura` «profit smart» mai eseguite, protezione copertura Over 4.5 ESEGUITA (automatica, come da classificazione); tennis flb: nessuna chiusura; scalper: lo sniper chiude da solo (R-F2-9) | OK salvo R-F2-9 |
| 3-bis A | feed vs libro Betfair VERO vs IPS | `sonda_libro_a.py` (login cert della sonda, `listMarketBook` EX_BEST_OFFERS ×6, IPS `get_scores` ×6, logout: chiamate elencate in `A_libro_1007Z.json`), 2 partite in gioco × 3 istanti | prezzi 3/6 identici, 3/6 con 1-2 tick di differenza su età riga 0.8-2.9 s nei primi minuti (mercato mobile; lo scanner usa la STESSA proiezione EX_BEST_OFFERS conflate 1 s, `safe_strategy/stream.py:235`); punteggio 6/6 = IPS, minuto = IPS ±1. **OK con riserva** (da ripetere su una partita calma) |
| 3-bis B Omega 120 | ricalcolo INTERO, P fusa compresa, dal book registrato (dt 0.9 s) | `B_omega_120.json`: p_mercato devigata dal `cs` registrato → `fondi_col_mercato` = 0.0176777 = p_fusa scritta; p_imp, margine 1.1208, EV, liability 47 = scritti; cancello vero | **OK** |
| 3-bis C Safe | rigioco del feed registrato nel motore di produzione `SafeEngine` (`verifica_safe_c.py`) | 09:24-09:40Z: 3516 righe; il trade 343 è preceduto dal segnale ricalcolato (09:24:48 e 09:24:53, trade 09:25:04); l'unico segnale senza ingresso (36090940 esatto Casa) è sulla partita dove Safe era già dentro (trade 342, 09:23:38). 09:40-10:10Z: 4272 righe, 0 segnali, 0 ingressi calcio (skip `pre_ko_assente`) | **OK** |
| 3-bis C Mike | parametri EFFETTIVI (`mike.config.merge_params`) e ingressi pre-match | `C_mike.json`: 5070/5071 banda 1.30-3.00, stake 5, 47-48 min prima del KO (finestra 10-60), paper | **OK** |
| Z14.2 P&L | ricalcolo indipendente di ogni posizione regolata (`verifica_pnl.py`) | Omega 117/118/119/120 +0.95 ciascuno (lay 1 € vinto, 5%), Safe 342/343 +1.90; tennis flb −0.04; 0 KO | **OK** |
| D (plancia) | hook VERO `useControlRoom` montato col client vero, guardia solo letture (`plancia.e2e.test.tsx`), confronto `confronto_d.py` | 09:34Z e 09:59Z: righe bot 9/9 = DB (stato/modalità), `cr-bot-pnl-tennis_*` = somma DB, `realizzatoOggi.paper` 6.61 = 2.85+3.80−0.04 (DB, giornata del piazzamento), posizioni a video = righe aperte DB (+ tennis e scalper) | OK; reperti R-F2-14/15 |""")
rep("""| bot | decisioni | ordini paper | aperti | P&L netto regolato |
|---|---|---|---|---|
| Omega | 3 ingressi, 40+ skip motivati | 3 lay CS 1 € (117 AOHW 95, 118 AOHW 55, 119 1-3 a 80) | 3 | 0 (nessuna regolazione) |
| Mike | 2 ingressi pre-match, 2 proposte d'uscita | 2 back U3.5 5 € | 2 | 0 |
| Safe | 2 ingressi esatto, 6 proposte opportunità (non piazzate), 16 «opportunità non più valida» | 2 lay CS 2 € | 2 | 0 |
| tennis_flb | 1 ingresso | 1 lay 2 € a 1.02 | 0 | −0.04 |
| tennis_pro / swing | superficie dichiarata, nessun ingresso | 0 | 0 | 0 |
| tennis_scalper | blocca in gioco (configurazione) | 0 | 0 | 0 |
| scalper | 2 sessioni, sniper 2 fire | simulati (dry-run) | 1 ordine vivo | lordo +0.50 (stats.auto) |""",
    """Aggiornamento 2 (10:12Z):

| bot | decisioni | ordini paper | aperti | P&L netto regolato (paper) |
|---|---|---|---|---|
| Omega | 4 ingressi (117-120), 3 tentativi rifiutati dal freno, decine di skip motivati | 4 lay CS 1 € | 0 | **+3.80** (4 vinti) |
| Mike | 2 ingressi pre-match (5070/5071), 2° Under dopo gol precoce (5072), coperture Over 4.5 (5073 1.34 € sotto il minimo, 5074 2.52 €, 5075 5.37 €), proposte d'uscita non eseguite | 6 | 6 | 0 (partite in corso) |
| Safe calcio | 2 ingressi esatto, ~10 proposte opportunità NON piazzate (`valutazione.valida=false` quando il prezzo sparisce, `opportunita_decaduta` a fine partita) | 2 lay CS 2 € | 0 | **+3.80** |
| Safe tennis | 2 ingressi (344, 345) back a 1.02 (= backMin 1.02, Q5) | 2 back 3 € | 2 | 0 |
| tennis_flb | 1 ingresso | 1 lay 2 € a 1.02 | 0 | −0.04 |
| tennis_swing | 1 ingresso (4350 back 1.78), 1 ordine PENDING | 2 | 1 | 0 |
| tennis_pro | superficie dichiarata, nessun ingresso | 0 | 0 | 0 |
| tennis_scalper | blocca in gioco (configurazione) | 0 | 0 | 0 |
| scalper | 2 sessioni fermate dal freno, poi 4-5 nuove dal feed (dry-run) | simulati | — | solo lordo dichiarato (non entra nel realizzato, per costruzione) |""")
rep("## 5. NON CERTIFICATO (motivo)", """- **R-F2-10 (KO candidato R3, scalper)**: a freno TIRATO l'auto-mode del supervisore ARMA sessioni nuove:
  `auto_armata` 36090936 e 36090937 alle 09:42:44Z (righe `requested`, dry_run), e `stats.auto.motivo_blocco`
  resta `null` (il freno non viene dichiarato). `scalper_service.py:745` chiama `giro_auto` (armamento
  `:455-490`, `motivo_blocco` a `:494` non riceve il freno) PRIMA di leggere il freno (`:750`); il freno ferma
  solo l'avvio del processo (`sessione_da_avviare`, `:623-627`). Nessun ordine partito; al rilascio le righe si
  sono avviate.
- **R-F2-11 (KO candidato, scalper force-flat)**: `stop: posizione NON flat dopo 30s` su entrambe le sessioni
  (`scalper_session.py:1312-1321`): il residuo dello sniper sotto il minimo (nl 0.5 / nw 0.585, `min_bet_skip`
  0.40 e 0.06) non viene appiattito (il force-flat non usa il place-and-trim) e la sessione va `stopped` con la
  posizione paper orfana.
- **R-F2-12 (design Omega)**: i rifiuti del freno consumano il budget dei tentativi della gamba (skip
  `kill_switch attempt 1..3 di max 3`, 36090944): dopo il rilascio quella gamba non si riprova più.
- **R-F2-13 (paper diverso dal live, Mike)**: la copertura Over 4.5 da 1.34 € (sotto il minimo di 2 €) viene
  riempita in paper con un fill simulato diretto (`mike/service.py:705-709`: «in paper dal fill simulato, in live
  dal place-and-trim»). Il place-and-trim di Mike non si esercita in paper: **NON CERTIFICATO** per costruzione.
- **R-F2-14 (D, due numeri per la stessa cosa)**: nello stesso view-model `totali.liabilityPaper` = 66 e
  `soldiGiornata.liability` = 64 (09:59Z): il primo conta anche il tennis_swing aperto (2 €), il secondo no. Sulla
  stessa pagina ci sono due verità per «liability paper aperta».
- **R-F2-15 (D, definizione di «oggi»)**: la plancia conta il realizzato paper per giornata del PIAZZAMENTO
  (`useControlRoom.ts:1987-2016`, «Paper invariato»). I trade piazzati ieri e regolati stamattina alle 08:57Z,
  all'avvio (Omega 116 +0.95, Mike 5063/5065/5067/5069 = +0.79, Safe 341 +0.03), non compaiono in nessun totale di
  oggi. Il piano (Z14.2) parla di «righe regolate di oggi»: la definizione va fatta scegliere all'utente.
- **R-F2-6 confermato**: alle 09:57Z la partita 36118619 (finita verso le 09:25Z) ha ancora 4 righe `running`,
  `tennis_live_now.status='SUSPENDED'`, `armate_feed=7` con tetto 5, 28 righe attive (7×4).
- **Proposta di Safe nata a bot fermo** (informativo): `safe_strategy_requests` 258 (anomaly) è stata scritta alle
  08:57:20Z, quando Safe era `stopped` (l'accensione è delle 09:13Z). Non è un'apertura.

## 5. NON CERTIFICATO (motivo)""")
rep("Accensioni: §0. Aggiornamento 1: 09:35Z.",
    "Accensioni: §0. Freno: tirato 09:42:00Z, rilasciato 09:56:28Z. Aggiornamento 1: 09:35Z. Aggiornamento 2: 10:15Z.")
open(p, "w", encoding="utf8").write(s)
print("ok")
