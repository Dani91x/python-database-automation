"""inserisce in CIMA al referto la sintesi finale (tabella controlli con %, NON certificati, KO, numeri)."""
p = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.claude\worktrees\agent-a1bc87b400bbc7d7c\AUDIT_2026-09-25\E2E_FASE2_BOT_PAPER_2026-09-26.md"
s = open(p, encoding="utf8").read()
C = [  # (id, controllo, esito, evidenza/nota)
    ("Z0/Z3", "accensione in paper dalla UI vera (mattino, riavvio 2), guardia anti-live falsificata", "OK", "ACCENSIONE_ORA.txt, accensione/, accensione_r2/"),
    ("Z13.2", "paper e live mai insieme (ogni riga di trade/ordini di oggi `mode=paper`, effettivo PAPER)", "OK", "sentinella + query di fine giornata"),
    ("Z4.O1", "Omega: stato sul canale con `control`, battito", "OK", "canali/, omega_control.stats"),
    ("Z4.O2", "Omega decide dal feed (audit V3 completo, skip motivati)", "OK", "omega_activity"),
    ("Z4.O3", "Omega ordini paper via canale+flumine, nessun doppio sulla coda (riavvio 2)", "OK", "canale_inviato, specchio awlq900…, coda 0"),
    ("Z4.O4", "Omega uscite manuali: nessuna uscita discrezionale eseguita", "OK", "omega_activity"),
    ("Z4.O5", "Omega nessun ingresso su mercato sospeso", "OK", "skip market_suspended"),
    ("B-Omega", "ricalcolo di 10 decisioni (117-120, 124-128) con le funzioni di produzione", "OK", "B_omega_*.json (P fusa ricalcolata solo sul 120)"),
    ("Z4.M1", "Mike: stato sul canale", "OK", "mike_stato"),
    ("Z4.M2", "Mike: hazard atlante v4 dichiarato nel frame", "NON CERTIFICATO", "chiave `hazard_versione` assente; ci sono solo hazard/hazard_atlas numerici"),
    ("Z4.M3", "Mike: paper REST, fuori dallo specchio", "OK", "mike_trades paper_fill:execution_mode_rest"),
    ("Z4.M4", "Mike: uscite proposte e non eseguite, protezioni (copertura Over 4.5) automatiche", "OK", "uscita_proposta ×17, cover"),
    ("C-Mike", "ingressi pre-match (banda, stake, finestra) e mancati ingressi (tetto 2/2)", "OK", "C_mike.json, mike_control.stats"),
    ("B-Mike", "stake delle coperture Over 4.5 (`cover_residual`)", "OK", "B_mike_cover.json"),
    ("Mike-PT", "place-and-trim del sotto-minimo in paper", "NON CERTIFICATO", "R-F2-13: in paper fill simulato diretto"),
    ("Mike-Reg", "regolazione dei 6 trade 5070-5075, nessun doppio ordine, P&L", "OK", "mike_aperti/"),
    ("Z4.S1", "Safe: stato sul canale, effettivi", "OK", "safe_stato"),
    ("Z4.S2", "Safe base banda 20-34 e veto campionati su ingressi reali", "NON CERTIFICATO", "nessun ingresso base oggi (pre_ko_assente al mattino)"),
    ("Z4.S3", "Safe tennis backMin 1.02", "OK", "ingressi a 1.02-1.11"),
    ("Z4.S4", "Safe: nota atlante v4 nelle attività", "NON CERTIFICATO", "0 attività con «atlante v»"),
    ("Z4.S5", "Safe ordini paper via canale+flumine (riavvio 2)", "OK", "canale_inviato + flumine_fill"),
    ("Z4.S6", "Safe uscite manuali = proposte (cashout proposed, exit_hold in attesa)", "OK", "safe_strategy_requests 265"),
    ("Z4.S7", "Safe proposte modello/anomalie NON piazzate", "OK", "46 proposte, 0 trade model/manual"),
    ("C-Safe", "rigioco del feed registrato nel `SafeEngine` di produzione", "OK", "C_safe_*.json"),
    ("Z4.T1", "tennis auto-mode dal feed (origine auto)", "OK", "tennis_bot_control, tennis_live_follow"),
    ("Z4.T2", "righe per partita paper, dry_run false", "OK", ""),
    ("Z4.T3", "ordini tennis nello specchio `tennis_live_orders` paper", "OK", "con R-F2-7"),
    ("Z4.T4", "uscite tennis: solo stop/protezioni, nessun target a uscite manuali", "OK", "swing `exit kind=stop`"),
    ("Z4.T-fine", "partita finita → righe in chiusura, tetto rispettato", "KO", "R-F2-6"),
    ("Z4.C1", "scalper auto-mode, sessioni dry-run", "OK", ""),
    ("Z4.C2", "specchio scalper con `source='scalper'` (riavvio 2)", "OK", "betfair_live_orders 43709"),
    ("Z4.C3", "scalper sul canale 47338", "OK", "scalper_stato"),
    ("Z4.C-exit", "scalper: nessuna chiusura da solo a uscite manuali", "KO", "R-F2-9 (sniper)"),
    ("Z5", "tempi degli ordini F0 dal log", "NON CERTIFICATO", "mattino senza log; riavvio 2 non analizzato da me"),
    ("Z6", "striscia d'esito a video", "NON CERTIFICATO", "nessun browser"),
    ("Z7", "transizioni Omega pubblicate e giro notturno", "OK", "omega_transitions_status: published 25/09 13:57Z, cron 04:00Z succeeded"),
    ("Z13.4-O", "freno: Omega rifiuta le aperture", "OK", "3 rifiuti (1° ciclo)"),
    ("Z13.4-T", "freno: tennis rifiuta le aperture", "OK", "tennis_swing 3 rifiuti (2° ciclo)"),
    ("Z13.4-C", "freno: scalper force-flat e NESSUN armamento", "KO", "R-F2-10 (arma a freno tirato, 2 cicli su 2); R-F2-11"),
    ("Z13.4-S", "freno: Safe rifiuta le aperture", "NON CERTIFICATO", "nessun tentativo nei 2 cicli"),
    ("Z13.4-M", "freno: Mike rifiuta le aperture", "NON CERTIFICATO", "nessun tentativo (tetto 2/2)"),
    ("Z13.4-R", "rilascio con doppia conferma e aperture che riprendono", "OK", "2 cicli; Safe 354, swing, scalper dopo il rilascio"),
    ("3-bis A", "feed vs libro Betfair vero vs IPS", "OK", "con riserva: 3/6 prezzi uguali, 3/6 a 1-2 tick su righe di 0.8-2.9 s"),
    ("D", "view-model vero della Control Room vs DB", "OK", "con reperti R-F2-14/15"),
    ("Z14.2", "P&L paper ricalcolato per posizione", "OK", "verifica_pnl.py, 0 KO"),
    ("Run-1", "runner calcio stabile", "KO", "R-F2-C1: 2 crash (10:00:46Z, 14:46:15Z)"),
    ("Run-2", "runner calcio si riaggancia dopo un'interruzione", "KO", "cieco 10:41:41Z → riavvio"),
    ("Alert", "alert ORDER_MODE col modo effettivo", "KO", "R-F2-C2"),
    ("Journal", "journal degli ordini senza errori", "KO", "R-F2-18 (alert 511)"),
    ("UI", "campi a video (U…)", "NON CERTIFICATO", "nessun browser collegato"),
]
tot = len(C)
ok = sum(1 for c in C if c[2] == "OK")
ko = sum(1 for c in C if c[2] == "KO")
nc = sum(1 for c in C if c[2] == "NON CERTIFICATO")
righe = "\n".join(f"| {a} | {b} | **{e}** | {n} |" for a, b, e, n in C)
SINTESI = f"""# ▶ SINTESI FINALE (fase 2, delegato sessione B) — aggiornata alle 18:55 locali (16:55Z)

**Esito dei controlli: {tot} controlli · OK {ok} ({ok*100/tot:.0f}%) · KO {ko} ({ko*100/tot:.0f}%) · NON CERTIFICATI {nc} ({nc*100/tot:.0f}%)**

| id | controllo | esito | evidenza / nota |
|---|---|---|---|
{righe}

**NON CERTIFICATI (motivo)**: Z4.M2 (versione dell'atlante non dichiarata nel frame di Mike) · Mike place-and-trim
(in paper non si esercita, R-F2-13) · Z4.S2 (nessun ingresso Safe base oggi) · Z4.S4 (nessuna nota atlante nelle
attività di Safe) · Z5 F0 (mattino senza log su file; il log del riavvio 2 non l'ho analizzato) · Z6 e tutti i campi
«a video» (nessun browser collegato) · freno su Safe e Mike (nessun tentativo di apertura in 2 cicli) · tutto ciò che
dipende dal runner fra le 10:41:41Z e il riavvio 2 («runner cieco»).

**KO (con file:riga; stato: APERTO salvo diversa indicazione del coordinatore — non ho verificato fix di altri)**
| KO | dove | stato |
|---|---|---|
| R-F2-6 tennis: partita finita con righe `running`, tetto 5 superato (armate 6-10) | `tennis_bot_service.py:492-500` (`_mercato_chiuso` legge `tennis_live_now.status`, che resta SUSPENDED) + `auto_mode.py:177-200` (`scegli_partite` conta solo le armate nel feed) | aperto |
| R-F2-9 sniper chiude da solo a uscite manuali | gate solo su `ScalperStrategy` (`scalper_bot.py:446`), non su `sniper_bot`; `USCITE_AUTOMATICHE_PER_BOT.md:263-264` | aperto |
| R-F2-10 scalper: l'auto-mode arma a freno tirato, `motivo_blocco` null | `scalper_service.py:745` (`giro_auto` prima del freno a `:750`), armamento `:455-490`, `motivo_blocco` `:494` | aperto (confermato nei 2 cicli) |
| R-F2-11 force-flat non appiattisce il residuo sotto il minimo | `scalper_session.py:1312-1321` | aperto |
| R-F2-C1 crash del runner calcio (exit 1) ×2, poi cieco dalle 10:41:41Z senza rilevamento per ~4 h | causa senza traceback; ipotesi di admin-26 `runner.py:1192` | aperto (fix delle sessioni in arrivo col riavvio 3: da verificare) |
| R-F2-C2 alert ORDER_MODE «*** LIVE *** SOLDI VERI» con effettivo PAPER | alert all'avvio del runner (live_alerts 498, 506) | aperto |
| R-F2-C3 console dell'app non su file | `runner.py:2325` basicConfig su console | mitigato: dal riavvio 2 la console va su `%TEMP%\\alphascore_console.log` |
| R-F2-18 journal: `betfair_live_journal_side_check` violato | alert 511 (15:26:53Z) | aperto |
| Uniformità a porte spente (R-F2-2): paper di Omega/Safe senza flumine | `omega_service.py:2527-2547`, `auto_follow.py:857-865` | risolto dalla configurazione: con le porte accese passano da canale+flumine |

Reperti non-KO da decidere: R-F2-1/17 (scheda tennis «solo tennis» e pulsanti Safe dagli effettivi vecchi), R-F2-3/4
(audit Omega: `p_modello` = P fusa, book non salvato), R-F2-5 (Mike entra senza dossier), R-F2-7 (ordine tennis
riscritto ogni secondo, `placed_at` NULL), R-F2-8 (Pula = cemento per default), R-F2-12 (freno consuma i tentativi
di Omega), R-F2-14/15 (due liability, definizione di «oggi»), R-F2-16/20 (specchio `source='runner'` per
Omega/Safe calcio, `source='manual'` per Safe tennis), R-F2-19 (`canale_ack_seq` ripetuto).

**Cosa ho visto fare ai bot (tutto PAPER, piazzati dalle 09:00Z, dati al 16:50Z)**
| bot | decisioni | ordini paper | regolati (V/P) | aperti | P&L netto regolato |
|---|---|---|---|---|---|
| Omega | 705 valutazioni (686 skip motivati) | 12 lay CS 1 € (2 in errore: rifiuto canale e freno) | 9 (9/0) | 1 | **+8.55** |
| Mike | 17 proposte d'uscita (nessuna eseguita), 4 partite | 12 (entrate Under, seconde entrate, coperture Over 4.5) | 6 (3/3) | 6 | **+2.90** |
| Safe esatto | 469 skip, 46 proposte opportunità non piazzate | 6 lay CS 2 € | 4 (4/0) | 1 | **+7.60** |
| Safe tennis | — | 8 back 3 € (1.02-1.11) | 5 (4/1) | 1 | **−2.76** (una back a 1.02 persa −3.00) |
| tennis_swing | 24 ingressi fra i 4 bot | 40 ordini | 7 (1/1) | 33 | **+0.15** |
| tennis_pro | | 12 | 6 (2/2) | 6 | **−0.12** |
| tennis_flb | | 11 | 4 (0/1) | 7 | **−0.04** |
| tennis_scalper | blocca in gioco (configurazione) | 0 | — | — | 0 |
| scalper calcio | 19 armamenti automatici, 4 sniper_fire | simulati (dry-run) + 1 nello specchio | — | — | solo lordo dichiarato (non nel realizzato) |

---

"""
anchor = "# E2E REALE — FASE 2"
assert anchor in s
i = s.index(anchor)
s = s[:i] + SINTESI + s[i:]
open(p, "w", encoding="utf8").write(s)
print("ok", tot, ok, ko, nc)
