# ⟶ MISSIONE 250 — ROADMAP OPERATIVA ⟵
### Obiettivo: €250/giorno spacchettando ogni match in PRE-MATCH + 1° TEMPO + 2° TEMPO,
### unendo TUTTA la tecnologia esistente (scalper, Omega, Poisson/ML, recorder, live_now).
### v1.0 — 2026-07-15 · Documento di missione. Le fasi hanno GATE quantitativi: si scala solo a gate verde.

---

## 0. La strategia (come dichiarata, punto per punto)

1. **Selezione**: ogni mattina N = eventi calcio listati su Betfair → target per match `T = 250/N`
   (50 eventi → €5/match). Più eventi = meno rischio richiesto al singolo match.
2. **Contesto**: ogni match ha 3 settori operativi: PRE-MATCH, PRIMO TEMPO (in-play), SECONDO TEMPO (in-play).
3. **Budget**: per evento si stanzia il necessario per chiudere T col minor rischio/tempo.
4. **Operatività**:
   - **PRE**: scalper bot, profitto a rischio ≈ 0 (validato GO nel progetto). Quanto fatto qui si
     SOTTRAE da T; una perdita si aggiunge (con cap, vedi §3.4).
   - **1T**: LAY sul **CORRECT SCORE PRIMO TEMPO**, risultato MENO PROBABILE IN ASSOLUTO,
     **stake fisso €1** (es. 2-2 HT @ 90 → vinci ~€0.95 o perdi €89). Ingresso pre-match o
     in-play a seconda della liquidità (minori → subito pre-match).
   - **2T**: stessa cosa sul **CORRECT SCORE FT** dopo l'intervallo, condizionato al risultato HT
     (es. HT 1-0 → lay 2-3 @ 110, stake €1).
   - **GAP-FILLER**: quello che manca a T si chiude con scalping iper-rapido in-play
     (es. min 51, 1-0 → BACK Under 3.5 @ 1.35, €100, target 1 tick).

---

## 1. I numeri a terra (aritmetica onesta della giornata — 50 eventi)

### 1.1 Le quattro "maniche" (sleeve) e il loro contributo atteso

| Sleeve | Contributo/match se vince | Giornata (50 match) | Rischio |
|---|---:|---:|---|
| Pre-match scalper | variabile (cert. multi-linea: +1.28€/match, n=1 giorno) | ~€40–65 | ≈0 (validato GO) |
| CS HT lay €1 | +€0.95 netto | +€47 lordi | −€60/−120 a colpo |
| CS FT lay €1 | +€0.95 netto | +€47 lordi | −€90/−150 a colpo |
| Scalp theta (gap) | +€0.70/0.80 a scalp (1 tick su €100 @ ~1.35) | il RESTO: ~€100–160 | −€15/−40 a gol subito |

### 1.2 Il punto matematico che decide tutto (sleeve CS)

100 leg CS/giorno (2×50) a quota media ~100:
- Se le quote sono **fair**: attese ~1.0 colpo/giorno → +94 di incassi vs −~100 di colpo ≈ **−€6/giorno**
  (la commissione, come da Monte Carlo Omega §9: EV≈0−c).
- Se c'è **favorite-longshot bias** (i punteggi estremi sono SOVRA-backati → quota lay 90 quando la
  probabilità reale è da quota 130+): colpi attesi ~0.77 → ≈ **+€25/giorno**.

➡️ **La sleeve CS vale tra −€6 e +€25/giorno, e la differenza è UN NUMERO MISURABILE** con i dati
che abbiamo (frequenze storiche 70k fixture + recorder). Misurarlo è il Gate G1. Con ~1 colpo al
giorno atteso su 100 leg, il colpo è la NORMA della giornata, non l'eccezione: va messo a budget.

### 1.3 Il punto operativo che decide tutto (scalp theta)

Il BACK Under X.5 in-play ha **drift strutturale a favore** (ogni minuto senza gol la quota scende):
non è lo scalping 1-tick sul muro dello spread che abbiamo falsificato — è **raccolta di theta con
rischio gol**. L'economia per scalp da 1 tick (~+€0.75) contro il riprezzo post-gol (−€15/40, col
betDelay 5s NON si esce prima della sospensione):

- Hazard gol "medio" 2° tempo (~2.6%/min), hold 90s → EV/scalp ≈ **−€0.28** ❌
- Hazard **selezionato** (finestre/partite a bassa pressione, ~1.5%/min), hold 60s → EV/scalp ≈ **+€0.36** ✅

➡️ **Il segno dell'intera gamba dipende dal GATE di hazard**: serve l'**Atlante Hazard Gol**
(P(gol nei prossimi 2-5 min | minuto, punteggio, lega) dal nostro DB) + il **costo del treno**
(distribuzione riprezzo Under post-gol, misurabile dal recorder full-depth). Gate G2.

### 1.4 Bankroll e ordini di grandezza

- Esposizione CS a regime: 10-15 match sovrapposti × ~€200 liability = **€2.000–3.000 aperti** nei picchi.
- Scalp: €100 a rotazione, raramente >3-4 simultanei.
- Bankroll operativo consigliato: **≥ €4.000–5.000** (250/die su 5k = 5%/die: nessuno lo sostiene
  senza edge misurato — per questo il target finale sarà **adattivo**, §3.4).

---

## 2. Cosa abbiamo già in casa (nessuna tecnologia da inventare)

| Pezzo | Stato | Ruolo nella missione |
|---|---|---|
| Scalper bot pre-match (multi-linea SNIPER+Atlante) | ✅ GO certificato | Sleeve PRE |
| **Omega** (CS lay, reserve-first, riconciliazione, FOK, ledger giornaliero Europe/Rome) | ✅ appena auditato, 114 test | Motore delle sleeve CS (da estendere: HT + stake fisso) |
| live_now (minuto+punteggio condivisi) | ✅ | Gating finestre |
| Poisson DC + ML (70k fixture, per-lega) | ✅ | Hazard pre-match per il gate scalp |
| Recorder full-depth + Match Replay + matching engine | ✅ | Misura FL-bias e "costo del treno" |
| Frequenze mercati per lega (RPC + UI) | ✅ | Prob. storiche CS estremi |
| DB-as-bus + dashboard | ✅ | Il Regista si costruisce sopra questo pattern |

---

## 3. ROADMAP (6 fasi, ~5-7 settimane al LIVE pieno)

### FASE 0 — Numeri a terra (2-3 giorni) · SOLO analisi, zero codice di trading
- **D0.1 Atlante Hazard Gol**: da match_events/fixtures → P(gol entro 2/3/5 min | minuto, punteggio,
  lega). Heatmap + tabella parametrica. È il gate d'ingresso degli scalp theta.
- **D0.2 Frequenze CS estremi**: distribuzione storica HT-CS e FT-CS per lega (2-2 HT, 2-3 FT, ecc.)
  → prima stima del FL-bias confrontando frequenze reali vs quote tipiche di mercato.
- **D0.3 Costo del treno**: dal recorder, distribuzione del riprezzo Under 1.5/2.5/3.5 nei 60s
  post-gol (quanti tick si perdono DAVVERO al colpo, betDelay incluso).
- **D0.4 Simulatore di giornata**: Monte Carlo della giornata intera con i numeri D0.1-D0.3
  (50 eventi, 4 sleeve) → distribuzione P&L/die, drawdown, bankroll richiesto.
- **GATE G0**: il simulatore con parametri MISURATI (non sperati) mostra mediana ≥ 0. Altrimenti si
  ricalibra la composizione delle sleeve prima di costruire.

### FASE 1 — IL REGISTA (mission ledger per match, 2-4 giorni)
- Tabella `match_missions`: event_id, target_base T, realized per sleeve (pre/ht_cs/ft_cs/scalp),
  liability aperta, stato (in_corso/chiuso/target_raggiunto), adjustments.
- Il Regista **non piazza**: contabilizza in tempo reale chi ha già portato quanto, e pubblica il
  "gap residuo" per match — è il segnale che gli altri bot leggono.
- UI: pannello missione giornaliera (N eventi, T, barra per match, sleeve breakdown) — pattern Omega.
- **Regole anti-rincorsa (non negoziabili)**: target per match cap **2×T**; una perdita CS resta
  nel match dove è avvenuta (NON si ridistribuisce sul resto della giornata → niente martingala di
  portafoglio); a stop-loss giornaliero raggiunto il Regista mette tutto in sola-chiusura.

### FASE 2 — Sleeve CS dentro Omega (3-5 giorni)
- Estensioni Omega (il grosso c'è già): mercato **HALF_TIME_SCORE** oltre a CORRECT_SCORE;
  modalità **stake fisso €1** (oggi c'è il target-sizing); **seconda entrata FT post-intervallo**
  condizionata al punteggio HT (via live_now); scheduling liquidità (leghe minori → entrata
  pre-match immediata, altrimenti in-play).
- Selezione "meno probabile IN ASSOLUTO" = quota lay più alta disponibile (già implementata:
  basta alzare price_max; il range resta configurabile).
- L'entrata 2T si piazza **durante l'intervallo** (mercato FT aperto, zero rischio gol mentre entri).
- Integrazione Regista: ogni fill/settlement CS aggiorna il ledger del match.
- **GATE G1 (in FASE 5)**: su ≥1000 leg PAPER+storico, hit-rate reale ≤ 80% dell'implicito
  (FL-bias conferma) → sleeve CS promossa; tra 80-100% → neutra (si tiene solo se il resto regge);
  >100% → sleeve CS TAGLIATA (il piano vive sulle altre tre).

### FASE 3 — Scalp theta gap-filler (1-2 settimane) · il cuore nuovo
- Nuovo modulo nello scalper: BACK Under X.5 con **gate hazard** (Atlante D0.1 pre-computato +
  correzione live: punteggio, minuto, lega; Poisson per il tasso base della partita).
- Regole: entra SOLO se hazard < soglia (dal D0.4); hold massimo 60-90s; take 1 tick; a gol subito
  → uscita al riprezzo (perdita DEFINITA, mai media al ribasso); size = f(gap residuo del match,
  cap fisso); **mai** oltre min ~78-80' (hazard in crescita) né nel recupero.
- Furbizie dalla ricerca già fatta: entrata preferita **post-gol sull'overshoot** (l'Under si
  riprezza oltre il fair per 30-60s → entri meglio: è l'idea "over-reaction post-gol" già a
  roadmap); preferenza per partite "morte" (0-0 con xG basso, favoriti in controllo).
- **GATE G2**: ≥300 scalp PAPER: EV/scalp > 0 con IC 95%, e P&L della gamba positivo includendo
  TUTTI i colpi. Kill-switch automatico se hit-rate gol osservato > previsto dall'Atlante.

### FASE 4 — Risk layer (in parallelo, 2-3 giorni)
- Cap globali sul Regista: liability aperta max, stop-loss giornaliero, max match concorrenti,
  max scalp simultanei. Report giornaliero automatico per sleeve (il "pagellino" della missione).
- Calcolo bankroll: dal simulatore D0.4, bankroll = max drawdown 99° percentile × 2.

### FASE 5 — CERTIFICAZIONE PAPER (2-3 settimane di giornate INTERE)
- Tutte le sleeve insieme, orchestrate dal Regista, su giornate reali complete.
- Campioni minimi: ≥1000 leg CS, ≥300 scalp, ≥10 giornate piene.
- **GATE G3**: mediana giornaliera ≥ 60% del target simulato; nessuna violazione dei cap;
  ogni sleeve ≥ break-even post-commissione (quelle sotto si tagliano, non si "aggiustano").

### FASE 6 — LIVE graduale
- Settimana 1: target 10% (€25/die, stake CS €1 → resta €1, scalp €10-20).
- Settimana 2-3: 25% → 50% se ogni settimana chiude ≥ 0 e i numeri restano nei range PAPER.
- 100% solo con 3 settimane consecutive coerenti col simulatore.
- **Target adattivo a regime**: `250 → min(250, f(N eventi, edge misurato))` — il numero lo
  decidono i dati, il tetto lo decidi tu.

---

## 4. Pensieri fuori dagli schemi (da valutare lungo il percorso)

1. **L'intervallo è oro**: è l'unico momento in-play a rischio zero — entrata 2T CS, riassetto
   scalp, ricalcolo gap. Il Regista deve trattare i minuti 45-46 come una finestra privilegiata.
2. **Overshoot post-gol** come entrata standard degli scalp (non solo theta "in quiete"):
   il riprezzo eccessivo dei 30-60s dopo un gol è la stessa dinamica del tuo SNIPER pre-match.
3. **Selezione eventi, non solo conteggio**: N non deve essere "tutti i listati" ma i listati
   OPERABILI (liquidità CS ≥ soglia, lega nell'Atlante). Meglio T=€6.25 su 40 buoni che €5 su 50
   di cui 10 illiquidi che falliscono la loro quota.
4. **Il 2-2 HT è il FL-bias più estremo del listino** — se il bias esiste, si vede prima lì.
   Il test G1 va stratificato per selezione, non solo aggregato.
5. **Correlazione tra sleeve dello stesso match**: un gol fa perdere lo scalp E avvicina il CS al
   colpo. Il Regista deve conteggiare il "rischio gol composito" per match, non per singola gamba.
6. **Registrare TUTTO da subito** (anche in PAPER): ogni leg CS con quota+esito e ogni scalp con
   hazard stimato+esito è il dataset che decide i gate. La misura È il prodotto delle prime fasi.

---

## 5. Sintesi esecutiva

Il piano è costruibile al 100% con la tecnologia già in casa; nessun pezzo va inventato, tre vanno
estesi (Omega→HT+stake fisso, scalper→modulo theta, nuovo Regista). La fattibilità dei €250/die
non si decide a tavolino: si decide su **tre numeri misurabili** — FL-bias delle quote CS estreme
(G1), hazard gol nelle finestre selezionate (G2), tenuta della giornata intera in PAPER (G3).
La roadmap è disegnata perché ognuno di questi numeri emerga **prima** di rischiare un euro vero,
e perché ogni sleeve che non si guadagna il posto venga tagliata senza pietà. La disciplina che
chiedi al metodo, il sistema la impone da solo: cap anti-rincorsa, stop-loss, kill-switch.

_«Il target di giornata è una promessa che si mantiene un match alla volta — o si taglia.»_
