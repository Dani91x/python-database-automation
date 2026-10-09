# DECISIONI PER L'UTENTE - Audit matematica 09/10/2026

Questioni che spettano all'utente (strategie dei bot, regole di rischio, processi nuovi, prove con ordini veri).
L'audit non le ha decise e non ha toccato nulla: le elenca con il contesto e il riferimento al reperto (05) e alla
proposta (06). Promemoria dovuto dallo standard: ogni modifica che arriva a un bot passa da
`python -m Betfair.stream.backtest.certifica <bot> ...` (replay) -> paper -> live. **Safe tennis non risulta
certificato da questo audit**; nessun replay e' stato lanciato oggi.

## Urgenti (soldi veri o sicurezza)

| # | Decisione | Contesto | Rif. |
|---|---|---|---|
| D1 | Bloccare subito il dutching "variable" sul lato LAY (worker e UI) e controllare nello storico del conto se e' mai stato usato in LIVE | Oggi una richiesta variable+lay piazza ordini BACK sull'intero totale. E' uno strumento manuale, non una strategia: la correzione e' di sicurezza, ma la applica chi ha il permesso di toccare il codice | 05 A1; 06 n.1 |
| D2 | Safe tennis: tenerlo acceso cosi', spegnerlo finche' il modello non usa punti del game e forza dei giocatori, o farlo evolvere (06 n.29) | La P(vittoria) dipende solo dal punteggio dei giochi con hold uguali per i due giocatori (`serve_data.csv` assente); sullo 0-40 del leader al servizio usa 0,924 invece di 0,827; la soglia 0,90 cade dentro la banda di incertezza 0,76-0,98 | 05 A4 |
| D3 | Stop giornaliero: deve valere al netto della commissione e sullo stesso perimetro (conto o strategia) per realized e MTM? | Oggi realized lordo e sul conto intero, MTM solo live_strategy: scatta tardi di circa la commissione sulle vincite del giorno | 05 M22; 06 n.31 |

## Strategie dei bot (divergenze trovate, nessuna modificata)

| # | Decisione | Contesto | Rif. |
|---|---|---|---|
| D4 | Mike, veto Under 3.5 e p4_pre: accettare che poggino su un Poisson che il mercato batte (RPS +0,0156), oppure valutare le proposte che cambiano le P (pesi di forma, prior inter-stagionale, rho stimato, calibrazione unica, prior dalle quote) con ricertificazione | Le soglie del veto sono tarate sulle P calibrate di oggi: ogni cambio delle P obbliga a ritararle | 05 MA2, M3, M4; 06 n.9-12, 18 |
| D5 | Mike: lambda dal tattico o dal Poisson (oggi dipende dall'ora dell'armo, senza identificativo) e rilettura del dossier quando il tattico arriva | p4_pre e p_under35_cal possono venire da modelli diversi | 05 M12; 06 n.16 |
| D6 | Mike `combine_hazard` = max(atlante, modello x 1,25): tenerlo o passare a una media pesata | Il max di due stime rumorose e' distorto verso l'alto; 1,25 non calibrato | 05 M20; 06 n.30 |
| D7 | Theta: passare dall'atlante v3 (con livello squadre, trovato peggiorativo; -44% a 88-89') al v4 | Riguarda anche il ripiego v3 di Safe e Mike | 05 M19; 06 n.30 |
| D8 | Omega: tabella empirica per minuto alla risoluzione esatta (oggi sovrastima fino a x1,57 a 89', prudente per il lay) e Wilson solo come filtro | Effetto sul numero di ingressi non misurato | 05 M21 |
| D9 | Scalper calcio: bias BACK/LAY tra ML calibrato, Poisson GREZZO e mid non normalizzato; l'ML servito non batte il mercato e su O2.5/BTTS nemmeno il tasso base | Tenere la regola, usare markets_calibrated e mid normalizzato, o togliere l'ML dal bias | 05 A2, B6; 04 FL-2 |
| D10 | Convenzione della tau Dixon-Coles in-play (solo 0-0 in live_engine_pro, ovunque in value_engine/Telegram): scarto fino a 2,1 pp | Scegliere una sola convenzione | 05 B28 |
| D11 | min_edge e Kelly calcolati per euro di stake anche sui lay (a quota 10 un EV 0,03 per stake e' lo 0,33% sulla liability) | E' una scelta di strategia | 05 M17 |
| D12 | De-vig power/Shin al posto del moltiplicativo dove i lambda vengono dalle quote (Omega, live) | Migliore in modo significativo sull'1X2 (log-loss -0,0037); cambia i lambda in-play | 06 n.8 |

## Traccia ML e foglio Quant Fund

| # | Decisione | Contesto | Rif. |
|---|---|---|---|
| D13 | Gate ML con baseline climatologica e limite inferiore dell'IC al posto della baseline uniforme | Cambia quali mercati ML sono attivi e lo stake della traccia ML (oggi stake pieno con BSS >= 0,12, che un modello senza skill raggiunge sui binari sbilanciati) | 05 MA1, A3; 06 n.5 |
| D14 | La traccia Kelly del foglio Quant Fund (money_management.py) e' ancora usata? Se si': minimo 1,00 dopo il tetto e ricalcolo retroattivo del P&L con la commissione attuale | Il minimo alza ogni stake Kelly sotto 1,00; il P&L storico viene riscritto se cambia l'aliquota | 05 B8, B38; 06 n.28 |
| D15 | Mostrare in UI i consigli ML come oggi? | Il modello servito non aggiunge informazione al mercato (M_misure.md) | 05 A2 |

## Regole Betfair .it da verificare con una prova reale (solo l'utente puo' piazzare)

| # | Decisione | Contesto | Rif. |
|---|---|---|---|
| D16 | Minimo di puntata .it: 1,00 (codice, `minimi_it.py`, basato su prove vere) o 2,00 a multipli di 0,50 (documentazione developer Betfair, pagina forse stantia)? Poi una sola costante in UI e motore | Oggi motore 1,00, quattro pannelli UI 2,00, Omega 0,5, auto-hedge 2,00 | 05 M13; 06 n.7 |
| D17 | Tetto di vincita potenziale 10.000 EUR e rifiuto di back+lay nello stesso placeOrders (documentazione developer .it): ancora in vigore? | Il codice non li gestisce | 05 B39; 06 n.32 |
| D18 | Aliquota di commissione reale del conto (fonti: 4,5% o 5%) e regola di arrotondamento di Betfair | Le stime paper/replay usano il 5%; il conto reale usa la commissione vera | 05 B9; 03 sez. 7 |

## Processi, workflow, migrazioni (servono permesso o mano dell'utente)

| # | Decisione | Contesto | Rif. |
|---|---|---|---|
| D19 | Permesso per un cruscotto settimanale di qualita' (Poisson, tattico, ML, quote: log-loss, RPS, ECE) e per un monitor di deriva | Oggi nessuna metrica continua; le sonde dell'audit sono gia' pronte; attenzione al timeout di 8 s (finestre strette) | 06 n.3, 21 |
| D20 | Generare le previsioni delle partite notturne (00-08 UTC) prima del calcio d'inizio o marcarle | 10-13% delle previsioni "pre-partita" sono generate dopo il fischio | 05 M1; 06 n.4 |
| D21 | Migrazioni SQL di coerenza (drawdown da zero, ROI dei lay su liability o colonna separata, denominatori della pagina Decisioni) | Le migrazioni le applica l'utente | 05 M15, M18, B3; 06 n.17 |
| D22 | Cancellare le 409 cartelle di modelli locali vecchi (alcuni con leakage) in `Ai Engine/models_cache/league_*` | Non sono serviti; peso morto | 05 M10; 06 n.24 |
| D23 | Orario delle quote nell'ETL di `match_odds` (snapshot_time NULL nel campione; tabella da 92 milioni di righe) | Necessario per sapere se l'ML usa quote di chiusura come feature | 05 M6; 06 n.19 |

## Nota sul processo dell'audit
Un delegato ha terminato tutti i processi `grep.exe` attivi sulla macchina (anche non suoi) verso le 12:00: se un'altra
sessione ha visto un grep interrotto in quel momento, la causa e' questa (05, nota finale).
