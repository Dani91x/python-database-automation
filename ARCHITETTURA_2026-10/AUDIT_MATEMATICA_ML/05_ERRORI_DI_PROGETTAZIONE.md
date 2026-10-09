# 05 - ERRORI DI PROGETTAZIONE, certificati (fase 2, 09/10/2026)

Riscritto in fase 2. Ogni reperto della fase 1 e' stato ricontrollato sul codice alle righe ATTUALI, cercato in
`CRONOSTORIA.md`, nelle costituzioni dei bot, in `PIANO_MODIFICHE_MIKE_2026-09-29.md` e negli audit precedenti, e i
numeri sono stati rifatti con codice nuovo. Prove complete, file:riga e sonde: `lavori/fase2/CERT_1_A_MA_M1-12.md`,
`CERT_2_M13-23_B1-20.md`, `CERT_3_B21-41.md`; verifiche indipendenti del coordinatore: `CERTIFICAZIONE_REFERTI.md`
sez. 2. Versione della fase 1 conservata in `lavori/fase2/05_fase1_originale.md`.

Verdetti: CONFERMATO / FALSO / RIDIMENSIONATO / SCELTA DOCUMENTATA (dell'utente o dichiarata nel codice) / GIA' NOTO
(con riferimento). Gravita': ALTO = soldi veri su un percorso vivo (anche manuale); MEDIO = numero sbagliato o
fuorviante che guida decisioni, o controllo mancante che nasconde un guasto; BASSO = incoerenza, caso limite, numero
solo mostrato; NESSUNA = non e' un errore. Gradi intermedi con motivo nella riga.

**Esito: nessun CRITICO; un solo ALTO (A1, il dutching), CORRETTO in fase 2** (`REFERTO_FIX_DUTCHING.md`).
Lo stato di certificazione dei bot si legge solo in CRONOSTORIA: Safe tennis certificato 18/18 il 09/10 sul codice
`25cab047` (CRONOSTORIA.md:5609-5618); gli altri bot non sono stati ricertificati da questo audit.

Molti reperti ML/Poisson erano GIA' in `AUDIT_2026-10-02/AUDIT_ML_POISSON.md` (CRONOSTORIA.md:4888, «Nessuna modifica
fatta»): la fase 1 non li aveva citati. Sono rimasti senza una decisione dell'utente.

## ALTO

| # | Reperto | Verdetto | Gravita' fase 1 -> certificata | Prova principale (righe attuali) |
|---|---|---|---|---|
| A1 | Dutching "variable" sul lato LAY piazzava ordini BACK | CONFERMATO; **CORRETTO in fase 2** | ALTO -> ALTO (risolto) | `live_order_worker.py:2914-2919` (ora rifiuta), `dutching.py:184-244` restituisce sempre `side="back"`; nessun bot lo usa, strumento manuale anche in LIVE |

## MEDIO-ALTO

| # | Reperto | Verdetto | Gravita' | Prova / nota |
|---|---|---|---|---|
| A2 | ML servito senza valore oltre il mercato: perde dalle quote ovunque; su Over 2.5 e BTTS non batte il tasso base (differenze non significative) | CONFERMATO, GIA' NOTO (AUDIT_2026-10-02, CRONOSTORIA.md:4888) | ALTO -> MEDIO-ALTO | consumatori: consigli UI, foglio Quant Fund, bias dello scalper, Telegram; Omega/Mike/Safe non lo leggono. Peso ottimo con le quote 0 su 1X2 e O2.5, 0,25 su BTTS (guadagno 0,0008, trascurabile) |
| A3 | Gate di affidabilita' ML su holdout troppo piccoli | CONFERMATO, GIA' NOTO; numeri corretti | ALTO -> MEDIO-ALTO | guardia unica `len<10` (`seriea_model_export.py:401`); holdout mediano ~90 righe (media ~170, 43% sotto 60); un modello perfettamente calibrato fallisce ECE<=0,10 nell'89% dei casi a n=40. «Brier 0,000 su holdout degeneri» non riscontrato su 500 modelli: tolto |
| MA2 | Il Poisson che i bot leggono non usa le quote e perde contro di esse (RPS 1X2 +0,016, IC [0,012; 0,021]) | CONFERMATO, GIA' NOTO | invariato | limite di informazione, non errore di calcolo; tocca il veto U3.5 di Mike (acceso per decisione dell'utente, CRONOSTORIA.md:3058, 3118). Effetto in euro non misurato |

## MEDIO

| # | Reperto | Verdetto | Gravita' | Prova / nota |
|---|---|---|---|---|
| A4 | Safe tennis: la P(vittoria) del modello usa solo il punteggio dei giochi (hold uguali 0,75, punti del game ignorati) | CONFERMATO come fatto matematico; **FALSO** che riguardi gli ingressi e che il bot non sia certificato | ALTO -> MEDIO | gli ingressi seguono le regole dell'utente (`safe_strategy/engine.py:1567` `evaluate_tennis`, nessun uso del modello); il modello entra solo nel cancello delle uscite in PROFITTO (`bot_service.py:5295`, `_model_gate`) e nelle proposte (`auto_trade_tennis` False, `bot_service.py:193`). Effetto: possibile incasso mancato o anticipato, non ingressi sbagliati. Certificato 18/18 (CRONOSTORIA.md:5609-5618) |
| MA1 | Gate BSS contro baseline uniforme: un modello che dice solo il tasso base passa | CONFERMATO, GIA' NOTO | MEDIO-ALTO -> MEDIO | `confidence_gate.py:170-215`; consumatore a soldi = foglio Quant Fund (manuale, non bot: CRONOSTORIA.md:5384-5385) |
| M1 | 10-13% delle previsioni "pre-partita" generate dopo il calcio d'inizio (21/09-07/10) | CONFERMATO nei numeri, GIA' NOTO; **causa probabile gia' rimossa** il 09/10 (orologio pg_cron 00:12 UTC approvato, CRONOSTORIA.md:5580-5600) | MEDIO (da rimisurare) | entra in analytics (`oos_valid=True` fisso) e nella calibrazione settimanale, non nei bot. Rimisurare dopo la notte del 10/10 |
| M2 | Nessuna misura continua della qualita' del Poisson | CONFERMATO | MEDIO | `master_backtest.py` manuale e in nessun workflow; `valida_motore_poisson.py:28, 96` su 18 partite fisse |
| M6 | Quote come feature ML senza orario; edge ML contro le stesse quote | CONFERMATO nel codice (`feature_pipeline.py:35-82`); «snapshot_time NULL al 100%» NON VERIFICATO in fase 2 | MEDIO | |
| M8 | Calibratori ML fragili (isotonica su campioni piccoli) | CONFERMATO, GIA' NOTO | MEDIO | `ensemble_trainer.py:866-872`; ramo temperature NON VERIFICATO |
| M9 | Post-calibrazione ML mai valutata; il gate misura le P prima della correzione | CONFERMATO | MEDIO | `predict_fixture.py:870-909` |
| M11 | Anteprima del dutching variable diversa da cio' che il server piazza | CONFERMATO; **CORRETTO in fase 2** | MEDIO (risolto) | anteprima ora identica al piano del server (0 divergenze su 40.000 casi); residuo: multipli di 0,50 applicati da `build_order` dopo il piano (vedi DECISIONI) |
| M12 | lambda dal tattico o dal Poisson senza identificativo; Mike non rilegge il dossier | CONFERMATO, GIA' NOTO in parte (CRONOSTORIA.md:4888, «un solo motore di lambda») | MEDIO | `stream/db.py:262-285`, `mike/dossier.py:81-107`; se il tattico arrivi davvero dopo l'armo di Mike: NON VERIFICATO |
| M17 | min_edge e Kelly per euro di STAKE anche sui lay (a quota 10 un EV di 0,03 per stake = 0,33% della liability) | CONFERMATO, percorso vivo (`live_engine_pro.py:596-607`, Safe `opportunity.py:1007`); nessuna scelta documentata trovata | MEDIO (strategia: si scrive, non si cambia) | `_kelly_lay` restituisce lo stake in modo corretto |
| M19 | Theta usa l'atlante v3 (con livello squadre); v3 resta ripiego di Safe e Mike | CONFERMATO in parte | MEDIO per il ripiego, BASSO per Theta | Theta e' opt-in (`theta_mode`, `scalper_session.py:91`, `auto_mode.py:188`; uso del v3 in `theta_bot.py:546-551`); Safe e Mike sono gia' sul v4 (CRONOSTORIA.md:3045-3047); «-44% a 88-89'» NON rifatto in fase 2 |

## BASSO-MEDIO

| # | Reperto | Verdetto | Prova / nota |
|---|---|---|---|
| M7 | Il modello ML servito non vede l'ultimo ~25% dei dati | CONFERMATO, SCELTA DI PROGETTO dichiarata nel codice | `seriea_model_export.py:234-262, 362-366` |
| B15 | Lordo e netto di commissione mescolati nei numeri live della UI | CONFERMATO | il «2,6% sull'hedge nello stesso mercato» NON rifatto |

## BASSO

| # | Reperto (breve) | Verdetto |
|---|---|---|
| M3 | P Poisson grezze troppo estreme sui gol (pendenza O2.5 0,44-0,47) | CONFERMATO sul numero; **FALSO** che lo scalper usi il grezzo dei gol: legge solo l'1X2, dove grezzo e calibrato differiscono di 0,0003 RPS (`bias_resolver.py:79-92`) |
| M4 | Nessuna memoria tra stagioni, minimo 5 partite | CONFERMATO; effetto NON VERIFICATO |
| M5 | Nessun aggiustamento per forza degli avversari | CONFERMATO, RIDIMENSIONATO |
| M10 | Versionamento ML debole | CONFERMATO |
| M13 | Costanti dei minimi .it incoerenti (motore 1,00, alcune UI 2,00) | CONFERMATO; la regola vera e' GIA' MISURATA E DECISA dall'utente (1,00, multipli di 0,50; CRONOSTORIA.md:4790-4793, 4947); le costanti piu' alte sono prudenti |
| M14 | market_intelligence: intervallo chiamato Wilson ma Wald | CONFERMATO; effetto sui segnali NON rifatto |
| M15 | Pagina Decisioni: denominatori diversi | CONFERMATO |
| M16 | analyze_sweet_spot: lettura non paginata, soglie in-sample | CONFERMATO, strumento CLI |
| M18 | Drawdown: 20 in SQL contro 30 in TS sulla stessa serie | CONFERMATO |
| M20 | Mike `combine_hazard` = massimo fra atlante e modello x1,25 | **SCELTA DOCUMENTATA** (`COSTITUZIONE_MIKE.md:157-158`, «comanda la fonte piu' prudente»): non e' un errore; resta solo che 1,25 non risulta calibrato |
| M21 | Omega: tabella per minuto usata per 5 minuti | CONFERMATO il meccanismo, RIDIMENSIONATO: nella finestra d'ingresso (fino all'80', v3 85') l'effetto e' circa x1,3 e solo prudente (toglie ingressi) |
| M22 | Stop giornaliero di conto lordo di commissione | CONFERMATO il lordo, RIDIMENSIONATO: lo stop di conto e' spento di serie (`daily_loss_limit` NULL = off, `config_stream.py:325`); il perimetro e' decisione dell'utente E34 (CRONOSTORIA.md:2956); gli stop propri dei bot sono separati |
| M23 | `win_prob_p1` del tennis in UI sovra-estremo | CONFERMATO, solo UI |
| B1 | `round_to_tick(NaN/inf)` = 1000 sul percorso REST manuale | CONFERMATO |
| B2 | rho -0,13 di riserva | CONFERMATO, SCELTA DICHIARATA nel codice |
| B3 | ROI dei lay su stake | CONFERMATO |
| B4 | CLV su probabilita' grezze | RIDIMENSIONATO |
| B5 | Tre versioni "calibrate" | CONFERMATO in parte; doppia vita dichiarata nel codice |
| B6 | Bias dello scalper: Poisson grezzo (1X2) contro ML calibrato | CONFERMATO (strategia); controllo d'eta' NON verificato |
| B7 | `markets_calibrated` scritto anche se la calibrazione non si carica | CONFERMATO dal coordinatore (`poisson_calibrator.py:86-92`), latente (oggi fonte "db") |
| B8 | Kelly del foglio: minimo 1,00 dopo il tetto | CONFERMATO; foglio manuale, non bot |
| B9 | Arrotondamento della commissione diverso tra copie | CONFERMATO (1 centesimo) |
| B10 | Due regole di pareggio sul tick | CONFERMATO (196 punti su 99.900, solo pareggi a mezzo tick) |
| B11 | Hedge al centesimo | CONFERMATO in parte (righe cambiate) |
| B12 | `ticks_between` in piu' copie | CONFERMATO |
| B13 | Backtest: `order_profit` detto netto ma lordo | CONFERMATO |
| B14 | De-vig moltiplicativo e 0,975 fisso | CONFERMATO |
| B16 | Metriche con lo stesso nome e definizioni diverse | CONFERMATO |
| B17 | Tennis: tie-break 0,5 e servizio non alternato tra set | CONFERMATO, latente (solo cancello delle uscite di Safe) |
| B18 | `estimate_holds(0,0,0,0)` = 0,7917 nel ripiego | CONFERMATO |
| B19 | Win rate tennis per ordine | unita' NON VERIFICATA |
| B20 | Ventaglio | CONFERMATO, solo CLI |
| B21 | Monitor di deriva | RIDIMENSIONATO: esiste un controllo settimanale `_auto_bss_check` (`money_management.py:1333, 2608`) |
| B22, B23, B24 | "edge" con due significati; euristica `v/100`; proxy O0.5 1T | RIDIMENSIONATI / scelte di progetto |
| B26 | Lettura calibrazione non paginata; cache dell'advisor Omega che memorizza anche un errore come None senza scadenza (`omega_advisor.py:308`) | CONFERMATO (cache); paginazione NON VERIFICATA |
| B27 | `lam_from_prematch(NaN)` = 50; `devig_pair` con quota opposta <=1 | CONFERMATO, latente |
| B28 | Due convenzioni della tau in-play | CONFERMATO; SCELTA DOCUMENTATA in `live_engine_pro.py:58-72`; la versione "ovunque" non e' usata da nessun bot |
| B29, B31, B36, B37 | lookahead storico; turnover/K=50; xhedge; xG in market_intelligence | CONFERMATI in parte, resto NON VERIFICATO |
| B30 | `max(es.odds)` nel report Direzioni | CONFERMATO nel codice; effetto NON VERIFICATO in fase 2 |
| B32 | `lay_size_from_target` e minimo .it | SCELTA DOCUMENTATA |
| B33 | Post-calibrazione ML in try/except | RIDIMENSIONATO (c'e' un `logger.warning`) |
| B34 | Colonne `commission` con unita' diverse | CONFERMATO |
| B35 | Cash-out di Mike: gambe archiviate escluse dalla base della commissione | CONFERMATO (0,62 EUR su un utile archiviato di 12,5) |
| B38 | Foglio: ricalcolo del P&L con la commissione attuale | RIDIMENSIONATO (solo slot del giorno) |
| B40 | Atlante v4: moltiplicatore di forza non neutro e altri tre punti | CONFERMATO in parte, GIA' NOTO in parte (`AUDIT_2026-09-25/ATLANTE_V4_FORZA_ID_SQUADRA.md`); MEDIO se l'effetto si conferma, oggi non misurato |
| B41 | Tennis: rischio ritiro fisso, liability in tre copie, `netto_size` | RIDIMENSIONATO (solo cancello delle uscite) |

## NESSUNA (non sono errori)

| # | Reperto | Verdetto |
|---|---|---|
| B25 | Campi mai valorizzati (`p_over45_cal` ecc.) | CONFERMATO ma campo morto senza effetto |
| B39 | Regole .it non gestite (tetto di vincita 10.000 EUR, back+lay nello stesso placeOrders) | **FALSO**: tetto gestito in `live_order_build.py:99, 875-886` («sempre attivo»); ogni ordine di produzione e' una transazione separata, quindi back+lay misti non possono partire. Resta NON VERIFICATO se i bot che piazzano direttamente passino dalla guardia del tetto (irraggiungibile con le loro puntate) |

## Concordanza degli identificativi
A1-A4, MA1-MA2, M1-M23, B1-B41 = questo file. P-R* (01), ML-R* (02), FL-* (04) corrispondono come nella versione
della fase 1 (`lavori/fase2/05_fase1_originale.md`, ultima tabella); le gravita' di 01, 02, 04 sono state allineate a
questo file in fase 2 (registro `lavori/fase2/APPLICATE_01_02_04_06.md`).

## Nota sul processo dell'audit
Nella fase 1 un delegato ha terminato tutti i processi `grep.exe` attivi sulla macchina, anche non suoi (riportato
anche in CRONOSTORIA, checkpoint delle 12:56 del 09/10). Nella fase 2 e' vietato terminare processi.
