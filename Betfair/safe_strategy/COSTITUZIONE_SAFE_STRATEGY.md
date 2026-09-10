# ⟶ COSTITUZIONE DI «SAFE STRATEGY» ⟵

Documento vivo. Descrive cosa è Safe Strategy oggi (10/09/2026 sera), come è
costruita, cosa è stato verificato dal vivo, cosa NON funziona ancora e la strada per
il livello successivo. Nessuna parte del lavoro del 10/09 è omessa.

Regola di naming: nel codice si chiama sempre "Safe Strategy". Il manuale operativo
delle 4 strategie (ingressi, uscite, minutaggi) è il file
`C:\Users\Admin\Desktop\PYTHON DATABASE\STRATEGY S.txt` (che contiene l'URL dell'artefatto).

---

## 0. Cos'è Safe Strategy (in tre frasi)

1. Un **radar** che, sul feed unico dello scanner (`safe_strategy_scan`), valuta in tempo
   reale le 4 strategie del manuale (Base, Risultato Esatto, Tennis, Punta) su tutte le
   partite in-play di calcio e tennis.
2. Da oggi un **bot** (`bot_service.py`) che le esegue da solo, paper o live, con
   resoconto in tempo reale, cash out professionale, uscite automatiche dal manuale e
   uscite "a modello" (mai chiudere in perdita quando il margine è ampio).
3. Un **motore di opportunità** che segnala mercati "sostanzialmente improbabili" con
   piccolo profitto: modello tempo×punteggio calibrato, quote anomale, combinazioni a
   rischio zero, tennis.

---

## 1. Architettura (stato al 10/09 sera)

```
scanner (service.py/scanner.py/stream.py)  →  safe_strategy_scan (feed unico, write-on-change)
                                              ├─ UI radar (lib/safeStrategy.ts, motore TS)
                                              ├─ Omega (omega_service)
                                              ├─ runner calcio/tennis, board (scan_feed.py)
                                              └─ BOT SAFE (bot_service.py)  ← 10/09
bot ─ engine.py (port Python del motore TS, 103 test di parità)
    ─ execution.py (place / close_trade / settle_group condiviso con Omega)
    ─ exits.py (uscite manuale + decisione a modello)
    ─ risk.py (cap giornalieri/evento/correlati, stop perdita)
    ─ opportunity.py (+ calibration.py, pressure.py, anomaly.py, combos.py, tennis_opportunity.py)
    ─ bot_db.py → tabelle: safe_strategy_control / trades / activity / requests / opportunities
UI  ─ pages/SafeStrategy.tsx (Calcio|Tennis × Segnali|Opportunità|Monitor|Trade + Storico)
    ─ components/trading/CashOutButton.tsx, DailyCalendar, PerformancePanel, DayDetail
    ─ lib/safeBot.ts, lib/dailyHistory.ts
DB  ─ migrations: safe_strategy_bot.sql, betfair_live_cashout_v3.sql, omega_cashout.sql,
      daily_history.sql (tutte applicate il 10/09)
exe ─ desktop/main.js: runner `safe-strategy-bot` sotto watchdog, lock 127.0.0.1:47318
```

Regola dei processi: **nessuna chiamata Betfair duplicata**. Il bot legge SOLO il feed
(una SELECT/ciclo), piazza tramite la coda flumine del runner quando l'evento è in
follow STREAMING, altrimenti paper fill dal feed / REST FOK in live (stesso layer di Omega).

### 1.1 Feed: blocchi aggiunti oggi (additivi, nessuna chiave rinominata)
- `ou` (Over/Under 0.5–7.5, solo linee non ancora decise), `btts`, `ht_result` (<45'),
  `odds_ts_ms`, `mo` selection_id già nelle coppie `odds.*`. Capacità stream rispettata
  (tier 2, max 20 eventi, 180 mercati/connessione). Calcolo inline delle opportunità nello
  scanner: opt-in `SAFE_SCAN_OPPORTUNITIES=1` (default off: lo fa il bot).

---

## 2. Le 4 strategie — ingressi (motore `engine.py`, parità col TS)

| # | id | mercato | minuto (SOGLIA) | punteggio | lato | quota ingresso | stake |
|---|----|---------|-----------------|-----------|------|----------------|-------|
| 1 | base | MATCH_ODDS | ≥55' | fav avanti 1-0/2-1/2-0, fav pre 1.40–1.80, dog pre 4–8, fav live 1.20–1.34 | LAY sfavorita | lay dog | stake.laySize (2) |
| 2 | esatto | CORRECT_SCORE "Altro risultato Casa/Ospite" | ≥48' | 0-0/1-0/1-1/2-1, bancata con ≤1 gol | LAY | 30–70 | stake.laySize |
| 3 | punta | MATCH_ODDS | ≥66' | 2-0/3-1/3-0, leader = favorita, ≥3' dal gol | BACK favorita | 1.03–1.10 | stake.backSize |
| 4 | tennis | MATCH_ODDS | — | 1 set + ≥2 game di vantaggio, singolare, no competizioni escluse | BACK leader | 1.01–1.10 | stake.backSize |

Gate d'ingresso del bot (10/09): liquidità abbinabile ≥ stake × fattore, **spread
lay/back ≤ 1.6** (il trade 12 di oggi, back 20 / lay 60, era un'entrata sbagliata),
rischio (`risk.py`), dedup per `signal_key` (= event:variant:situazione, indice univoco
parziale), anti-blip `scoreConfirmSec`.

Nota: Base e Punta oggi NON sono scattate per le partite già in corso all'avvio dello
scanner: manca la quota pre-match congelata (`pre_ko`). Il motore non entra "a occhi
chiusi": corretto, ma limita le strategie 1 e 3 alle partite viste dal calcio d'inizio.

---

## 3. Le 4 strategie — USCITE (exits.py) — DA RIVEDERE DOMANI

Regole del manuale implementate:
- **BASE**: profit se la favorita segna ancora; tempo 80'; LOSS immediata (dopo 30 s di
  stabilizzazione) se la sfavorita pareggia; rosso alla favorita → esci.
- **ESATTO**: tempo 72' (uscita "in profitto" del manuale); LOSS immediata se la squadra
  bancata segna.
- **PUNTA**: profit al gol successivo; tempo 83'; LOSS immediata a qualsiasi gol subito.
- **TENNIS**: profit al game successivo vinto (`tennis_take_profit_next_game`, default on);
  loss opzionale al game perso (default off); OBBLIGATORIA con 2 game persi di fila e set
  in parità; cambio set azzera il conteggio.

Decisione a MODELLO per le uscite a tempo/profitto (decisione utente 10/09 pom.):
`decide_time_exit(p_lose, locked, hold_profit, stake)`: locked ≥ 0 → esci;
p_lose ≤ `hold_max_risk` (2%) → tieni fino al settlement; p_lose ≥ `risk_cap` (10%) →
esci; altrimenti confronto EV(hold) vs bloccato (`ev_margin` 0,10 €). Le uscite LOSS del
manuale restano immediate e incondizionate. p_lose: calcio dalla griglia residua
(`OpportunityModel.book`), tennis da `tennis_winprob.p_match`, fallback quota di mercato.

Residuo dopo chiusura parziale (libro sottile): riprova ogni 20 s, max 15 tentativi.
Trade `model` (modello/anomalie/combo/tennis): uscita se evento avverso porta p_lose sopra
10%, tennis 2 game/set persi, take-profit all'80% del massimo, cash out quasi gratis.

**Verificato dal vivo (paper)**: trade 11 lay 60 al 72' → cash out avrebbe bloccato −9,43 →
tenuto ("P(perdita)=0,4%") → 20 s dopo chiuso a +0,44. Trade 9/14: uscite a tempo +1,40 / +0,88.
Tennis: take-profit al game successivo eseguito.

**Cose da correggere domani (indicate dall'utente):**
1. Le uscite in LOSS e in PROFIT vanno ripensate strategia per strategia con il manuale
   alla mano e con il modello: oggi il "tempo 72'" ha chiuso il trade 12 a −4 su un +1,9
   quasi certo (poi corretto con la decisione a modello, ma la regola "esci comunque a
   70-75'" resta da riscrivere come *presa di profitto*, non come chiusura cieca).
2. Per la Base manca il "controllo del gioco" (condizione del manuale): oggi non è
   misurato; `pressure.py` (corner/cartellini) è il candidato.
3. Attesa 20–60 s dopo il gol: oggi 30 s fissi; valutare "attendi che il mercato riapra e
   il prezzo si stabilizzi" (varianza dei tick) invece del timer.
4. Uscita parziale (scala) invece di tutto-o-niente su libri sottili.

---

## 4. Cash out professionale (Betfair/stream + execution.py)

- `compute_greenup(amount=)`: importo QUALSIASI anche decimale, cappato al green pieno.
- `plan_equalize`: profitto uguale su TUTTE le selezioni (side-aware, verifica di
  convergenza, minimizzazione del residuo di arrotondamento).
- Sotto-minimo Betfair (mecc. ufficiale: piazza min @1000/1.01 → cancel sizeReduction →
  replace quota) SOLO sulle gambe di chiusura, via macchina a stati `submin` collaudata;
  `allow_sub_minimum` rifiutato sulle aperture (RPC v3 + worker allineati).
- Follow-through per mercato sulle gambe equal non abbinate.
- `execution.close_trade`: gamba di chiusura con `closes_trade_id`, chiusure parziali
  ripetibili sul residuo, `hedged` solo a residuo < 0,01, `settle_group` netta tutte le
  gambe con commissione sul netto di mercato; settlement resumabile e orfani gestiti.
- UI `CashOutButton`: P&L bloccato live, 25/50/75/100 %, importo decimale, sui parziali
  mostra il CASO PEGGIORE, mode del TRADE (non della pagina), doppia conferma LIVE,
  anti doppio invio, disabilitato con feed stantio.

**Verificato dal vivo**: Safe calcio (−0,07 parziale, −0,02 totale), tennis (50%), Omega
(−6,6 parziale, −0,35 totale): pareggio esatto confermato AL SETTLEMENT al centesimo.

Limite noto: in live la chiusura è FOK; se il libro non abbina, il trade resta aperto
(riprova). Il paper riempie istantaneamente al best price: NON simula il bet delay 5 s
(gap di fedeltà demo=live ancora aperto).

---

## 5. Opportunità (opportunity.py e satelliti)

### 5.1 Modello tempo×punteggio
λ pre-partita (catena: fixture Omega → fixture per nomi+kickoff → pre-KO → default
1,35/1,15 con confidenza ×0,6) → tassi residui (`inplay_residual_rates`: curva reale dei
gol per minuto, stato partita, rossi, gialli, pressione) → griglia Dixon-Coles residua a
12 gol → probabilità di 1X2, O/U 0.5–7.5, BTTS, HT 1X2, CS, HTS. Devig, edge, EV netto
commissione, confidenza (edge, headroom, profondità, freschezza, cross-check hazard con
l'atlante), cooldown 90 s post-gol, min 20 € abbinabili.

**Calibrazione (10/09)**: 38 registrazioni con stream, 60.911 campioni, 36 tabelle;
Brier 0,0859→0,0818 (CV 0,0849), ECE 0,0143→0,0090. Il modello grezzo è buono sugli
Under alti, **ottimista sui lay** dal 60' in poi.

**Backtest P&L (10/09, stake 5, delay 5 s, commissione)**: grezzo 243 segnali, 87%
abbinati, **ROI −15%**; calibrato in-sample −0,2%, leave-one-out **−18,6%**. Perdite sui
LAY (mo/lay −66%, ou/lay −26%, ht/lay −107%); ou/back +0,1% (n=87). Conclusione onesta:
**il modello puro non ha edge dimostrato**; per questo i default di produzione sono
`max_prob_lay 0` (lay spenti), `min_prob_back 0,95`, `min_edge 0,03`, auto-trade off.

### 5.2 Quote anomale (anomaly.py) — logica di mercato, senza modello
Scala O/U incoerente (Under 7.5 a 1,10 con Under 6.5 a 1,01 → +8,9%), linee già decise dal
punteggio ancora quotate, MO vs CS incoerenti, HT ancora aperto dopo il 45', BTTS deciso.
Esecuzione "cecchino": valutate a ogni ciclo sulle righe con quote cambiate, FOK, dedup 120 s.
Sono i segnali con edge reale per costruzione; ma vivono secondi.

### 5.3 Combinazioni (combos.py) — rischio zero per costruzione
Dutching quando l'overround < 100% (riusa `trading/dutching.py`), under/over stack,
copertura CS: payoff enumerato su tutti i finali, commissione per mercato, lock ≥ 0 sul
caso peggiore, size per gamba verificata. Tutte le gambe o nessuna.

### 5.4 Tennis (tennis_opportunity.py)
Markov a game (`tennis_winprob.p_match`) + tenuta del servizio per giocatore + rischio
ritiro (2%, +1% best-of-5) + momentum (−50% se il leader ha perso gli ultimi 2 game) +
gate tie-break / set decisivo / doppi / competizioni escluse / quote stantie. Back del
leader ≥ 90% con edge ≥ 1,5%; lay dello sfavorito ≤ 10% a quota ≤ 8.

### 5.5 Rischio (risk.py)
Cap liability giornaliero 500 €, per evento 150 € (correlazione 0,7 tra mercati dello
stesso evento), max 3 trade/evento, stop a −50 € giornalieri, stake modello 5 €, cap
modello 150 €. NOTA: oggi il cap giornaliero è stato raggiunto (572 €) con 4 lay Esatto a
60 (liability 118 ciascuno): i cap vanno tarati sul tipo di strategia.

---

## 6. Dashboard (pages/SafeStrategy.tsx) — DA RIVEDERE DOMANI

Oggi: header (heartbeat scanner, stato bot, PAPER/LIVE con doppia conferma, Avvia/Ferma,
Parametri), KPI (segnali, trade, P&L oggi/totale, liability, monitorati) + pannello
rischio; tab Calcio|Tennis × Segnali (Investi)|Opportunità (chip per tipo: modello,
anomalia, combinazione, tennis; gambe e lock delle combo)|Monitor|Trade; tab Storico
(calendario mensile, statistiche, dettaglio giornata). Tabella trade: Selezione, Lato
LAY/BACK, gambe di chiusura attaccate all'apertura ("↳ Green-up di #N"), badge uscita,
"in attesa: margine ampio", P&L bloccato.

**Non verificata visivamente**: il browser dell'agente non raggiunge 127.0.0.1:47330
(permessi dell'estensione). Verifica solo tramite 1081 test vitest + RPC dal vivo.

**L'utente la giudica illeggibile** (10/09 sera): da rifare con questi criteri
1. Un trade = UNA riga: apertura, eventuale chiusura e P&L bloccato/realizzato nello
   stesso blocco, con timeline verticale (ingresso 22' 1-0 → gol 29' → green-up → esito).
2. Colonne fisse e poche: quando, partita, strategia, cosa (LAY/BACK + selezione + quota +
   stake + liability), stato, risultato (bloccato / aperto con P&L live / regolato).
3. Linguaggio del manuale, non del codice ("banca l'1-2 del 1T a 55", non "ht_cs").
4. Spiegazione a un click di OGNI decisione automatica (uscita, hold, cash out capped).
5. Vista "cosa sta facendo il bot ora": segnali attivi, uscite in attesa, motivi.

---

## 7. Storico giornaliero (daily_history.sql, lib/dailyHistory.ts)
RPC `get_safe_daily(from,to,sport)`, `get_safe_day_trades(day,sport)`: per giorno
operativo Europe/Rome P&L regolato, trade piazzati, vinti/persi, win rate, profit factor,
drawdown, streak, breakdown per strategia/sport/origine. Verificate a runtime (10/09:
10 trade, +2,15 €).

---

## 8. Test dal vivo del 10/09 (paper) — cosa ha funzionato
- Scanner: stream 104 mercati (67 nuovi), heartbeat ok; bot: heartbeat 2 s, nessun crash
  (due eccezioni transitorie Supabase gestite dal fail-closed).
- 14+ trade automatici coerenti col manuale (Esatto lay 30–70 su squadra ≤1 gol; tennis
  back 1,03–1,10 con set+2 game); skip corretti per liquidità e spread.
- Richieste manuali place/cashout, RPC di stato/storico, settlement coppie al centesimo.
- Uscite: tempo in profitto, hold su margine ampio poi chiusura in profitto, tennis
  take-profit; residuo gestito.
- Bug corretti in corsa: λ assenti per partite già in corso; statistiche che contavano le
  gambe di chiusura; entrata su spread anomalo; chiusura a tempo in perdita cieca; log
  duplicati; nome partita mancante su trade manuale Omega; isolamento test calibrazione.

---

## 9. Spunti per il livello successivo (in ordine di valore)
1. **Uscite** (§3): riscrivere profit/loss per strategia col modello e il manuale, uscita a
   scala, "controllo del gioco" da pressione, stabilizzazione adattiva.
2. **Dashboard** (§6): una riga per trade, timeline, linguaggio del manuale, spiegazioni.
3. **Fedeltà paper**: simulare bet delay 5 s e ricontrollo size; oppure instradare sempre
   sulla coda flumine (follow automatico degli eventi tradati).
4. **Base e Punta** anche per partite già in corso: recuperare la quota pre-match dal
   catalogo Betfair pre-KO (snapshot periodico dei mercati del giorno) invece del congelamento
   al calcio d'inizio.
5. **Modello**: validazione su più registrazioni (registrare ogni giorno con REC), pressione
   con dati reali, xG live se mai disponibile; tenere i lay spenti finché il backtest
   leave-one-out non è positivo.
6. **Anomalie**: misurare quante durano > 5 s (bet delay) e quante vengono abbinate; è il
   segnale con edge per costruzione ma la latenza decide tutto.
7. **Rischio**: cap per strategia (un lay a 60 non è un back a 1,05), stop perdita per
   strategia, esposizione correlata tra Safe e Omega sulla stessa partita.
8. **Certificazione liquidità lato back** (da ieri): ancora parziale; la sonda
   `liquidity_probe` è solo report; usare le registrazioni REC.
9. **Live**: mai prima di una settimana di paper con settlement e uscite tutte verificate.

---

## 10. Comandi utili
```
python -m pytest Betfair/safe_strategy -q                 # 480+ test
python -m Betfair.safe_strategy.tools.backtest_opportunity --help
python -m Betfair.safe_strategy.tools.validate_opportunity --build-cache --fit
cd frontend && npx vitest run && npx tsc --noEmit && npm run build
```
Riavvio del solo bot: terminare il figlio python `safe_strategy.bot_service` (il watchdog
lo rilancia in 10 s). Parametri: tabella `safe_strategy_control.params` (Sheet Parametri).
Commit del 10/09: 99fbff8, 5fd3fae (master).
