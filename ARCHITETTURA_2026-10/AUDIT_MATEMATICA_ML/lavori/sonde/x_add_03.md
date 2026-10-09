

---------------------------------------------------------------------------------------------------
(Sezioni 16-18 aggiunte dal coordinatore dopo l'ondata finale; gravita' finali in 05_ERRORI_DI_PROGETTAZIONE.md, che
prevale sulla tabella 14: dopo la scrittura di questo file sono emersi altri ALTI, tra cui il modello tennis di sez. 17.)

## 16. Catena hazard in-play e stimatori empirici (lavori/Z1_hazard.md, sonde z1_*)

Componenti: atlante v3 (`Betfair/stream/scalper/genera_atlante.py`, `hazard_atlas.py:271-372`), atlante v4
(`atlante_v4.py`: forza `lh=mu_h*exp(att_h+dif_a)`, `_p_recupero2`, `assembla_v4`, `consulta_atlante_v4`), taratura
(`validazione_hazard/forza.py`, `candidati.py`), `combine_hazard` di Mike (`mike/dossier.py:114-123`), stimatori Omega
(`omega/omega_empirical.py`: Wilson unilaterale z=1,64 con shrink, `max(P_modello, P_empirica)`), tabelle di
transizione SQL (`migrations/omega_transitions_*`).
- Correttezza: `_p_recupero2` e `shrunk_upper` ricalcolati a mano coincidono (esempio del docstring 1,265%). Nei bucket
  regolari atlante v3 e Poisson con CDF dei gol (value_engine/goal_timing.py) concordano entro il 5% (rapporto 1,01-1,06).
- Leakage: nessuno nel live; validazione walk-forward per stagione (addestra <=2023 valuta 2024, poi <=2024 valuta 2025).
- Limiti (MEDIO): il v3 sottostima l'hazard a 88-89' del 44% (M_MAX=87, recupero schiacciato a 90; genera_atlante.py:81,
  :154-170) e Theta usa ancora il v3 con il livello squadre che la validazione ha trovato peggiorativo (theta_bot.py:550);
  tabella Omega per minuto usata per b..b+4: P dei gol residui sovrastimata fino a x1,57 a 89' (omega_empirical.py:150-155,
  direzione prudente per il lay ma non documentata); limite di Wilson usato anche per il ranking (premia n grandi);
  `combine_hazard` = massimo di due stime rumorose, quindi distorto verso l'alto, con pressione x1,25 non calibrata
  applicata alla probabilita' invece che al tasso.
- Stato dell'arte: modelli di intensita' in-play dipendenti da minuto e punteggio (Dixon & Robinson 1998, "A birth process
  model for association football matches", The Statistician; [ricerca] in Z1) e empirical Bayes per tassi con poche
  osservazioni: l'atlante v4 (forza + shrink + validazione walk-forward) e' ALLINEATO nell'impianto; il v3 e il max() no.
- Verdetto: corretto con limiti; si puo' fare meglio togliendo il v3 dove resta e sostituendo il max() con una media pesata
  per varianza (decisione utente: strategie Theta e Mike).

## 17. Tennis (lavori/Z2_tennis_residui.md, sonde z2_*) e matematica residua dei servizi

- **ALTO (strategia, da portare all'utente)**: la P(vittoria) di Safe tennis non usa i punti del game in corso: letti in
  `_state` (tennis_opportunity.py:219) e mai usati da `_p_raw_p1` (:250-261) [C]. Esempio: leader al servizio sul 4-2 con un
  set di vantaggio, sullo 0-40: P corretta 0,827, P usata 0,924 (sonda z2_punti_nel_game). L'edge apparente e' massimo
  proprio sui break point.
- **ALTO (strategia)**: hold uguale per i due giocatori (prior 0,75) perche' `serve_data.csv` non esiste
  (tennis_opportunity.py:223-242 [C]): la P dipende solo dal punteggio; sullo stesso stato varia da 0,757 a 0,978 al
  variare degli hold veri. La soglia 0,90 e il min_edge 0,015 operano dentro questa banda; contro quote che conoscono la
  forza dei giocatori il segnale e' esposto a selezione avversa. Effetto in soldi NON VERIFICATO (nessun esito reale letto).
- Gia' noti e confermati: tie-break fisso 0,5 e servizio non alternato tra set (sez. 11, latenti finche' gli hold sono
  simmetrici); ripiego `estimate_holds(0,0,0,0)` = 0,7917 (bot_service.py:5233).
- MEDIO: `win_prob_p1` mostrato in UI sovra-estremo (serviceBreaks sempre 0 nel sidecar, hold fino a 0,95; best_of=3 fisso;
  tennis_runner.py:318-319): solo UI.
- MEDIO: stop giornaliero (`Betfair/stream/trading/daily_pnl.py`) con realized LORDO di commissione (reconcile_worker.py:555,
  simulatedorder.py:564): con +200 lordi lo stop a -50 equivale a circa -60 netti; perimetro asimmetrico (realized = conto
  intero, MTM = solo live_strategy, MTM senza profondita' del book).
- Corretti (sonde): `hold_from_serve_point` contro programmazione dinamica esatta; Theta: locked>0 implica netto>0 su 282
  coppie; conversione GBP->EUR (valuta.py) con errore <= 0,005 EUR per livello. BASSI: rischio ritiro additivo fisso
  2%/3% (prudente per back leader), liability in tre copie con tolleranze diverse, `netto_size` che annulla back e lay a
  prezzi diversi (esposizione_fuori_bot.py:272-282).
- Stato dell'arte: modelli a catena di Markov punto-gioco-set con probabilita' al servizio per giocatore (Newton & Keller
  2005; Klaassen & Magnus 2003; Barnett & Clarke 2005: citati in Z2 per nome, FONTE NON APERTA). L'impianto e' quello
  giusto ma senza i due ingressi che lo rendono informativo (punti, forza dei giocatori): INDIETRO.

## 18. Verdetto di sintesi per il par. 1.3 del brief (componenti matematici)

| Domanda | Verdetto | Perche' |
|---|---|---|
| Sono al massimo livello? | **IN PARTE** | La matematica dell'esecuzione (green-up S*B/L, P&L back/lay, commissione sul netto per mercato, Kelly al netto, scala dei tick, liability, conversione valuta) e' corretta sui conti a mano e coerente con la documentazione Betfair e con flumine. Sotto il livello: de-vig solo moltiplicativo (power/Shin migliori, misurato), modello tennis senza punti e senza forza dei giocatori, hazard v3 ancora in uso, stima `max()` distorta in Mike. |
| Si puo' fare meglio? | **SI'** | Regola unica per commissione e tick; de-vig power/Shin; tennis con punti e hold per giocatore; v4 al posto del v3; metriche di report con una sola definizione (06). |
| Abbiamo omesso qualcosa? | **SI'** | Regole .it della documentazione developer (tetto vincita 10.000 EUR, rifiuto back+lay nello stesso placeOrders) non gestite; commissione nello stop giornaliero; CLV de-viggato. |
| E' la soluzione migliore per performance e risultati? | **NO per i segnali, SI' per l'esecuzione** | Dove il numero decide se entrare (edge, P tennis, hazard max) l'informazione e' inferiore al mercato o distorta; dove il numero esegue (stake, hedge, P&L) la matematica e' giusta. Unico errore di esecuzione con soldi veri: dutching variable+lay (sez. 6). |

xG: non e' calcolato da noi; si usa l'xG di API-Football (`match_team_stats.expected_goals`) nel blend del Poisson
(peso 0,4, non tarato: 01 sez. 2) e come termine euristico nell'edge di market_intelligence (xG*abs(rho)*0,10,
edge_scorer.py:316-380); l'ML non lo usa (B). Verdetto: uso corretto ma non tarato.

Kelly: il foglio usa frazione 0,10, piu' prudente della forchetta 1/4-1/2 di Kelly citata in letteratura
(MacLean-Thorp-Ziemba, FONTE NON APERTA): non e' "allineato", e' piu' conservativo; con probabilita' meno informate del
mercato e' la scelta coerente.
