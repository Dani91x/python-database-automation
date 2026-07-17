# BIBBIA — BOT SCALPING TENNIS (Betfair)

> Documento unico di verità del TENNIS. Creato il **10/07/2026** (missione
> "1 tick tennis": fisica misurata + Atlante + baseline rifatte con harness
> certificato). Se riprendi il lavoro, PARTI DA QUI: tutto ciò che è stato
> misurato, certificato o bocciato è scritto sotto, coi numeri e con l'n del
> campione. NON ripetere test già fatti. Gemella metodologica di
> `Betfair/stream/scalper/BIBBIA_SCALPER_CALCIO.md` — ma il tennis ha la SUA
> fisica: qui non c'è nulla di copiato dal calcio senza una misura tennis.

---

## 0. STATO IN UNA RIGA

**PRE-MATCH: GO, solo main-draw liquidi** (missione og1: 2/2 verdi dove c'è
flusso, +0.11/+0.18 locked, zero gambe nude) · **IN-PLAY MATCH_ODDS: NO-GO
STRUTTURALE su TUTTE le 11 famiglie meccaniche misurate** (maker touch
1/34 · maker finestra-sicura post-game 0% cicli completi · taker chase
Atlante v1 tutte le celle EV<0 · fade resting sulle escursioni = fill solo
sui break veri 53/54 · sollievo post-BP-salvato inesistente · momentum
post-break non converte · theta inesistente · cross-book lock 0 episodi
catturabili in 85h · SET_BETTING morto · FLB 0/4 · Pro/Swing rossi) ·
La ragione è UNA: **l'oscillazione tennis è informazione (courtsider), non
rumore — col feed IPS in ritardo 3-8s siamo strutturalmente la controparte**
· Porte rimaste: feed punteggi sub-secondo (infrastruttura) e swing
direzionale multi-punto (≠ tick, serve campagna modello) · Config di
produzione GIÀ allineata (`inplay_tick_enabled: off`). Ogni idea nuova passa
dal **Registro Ipotesi (§11)**.

---

## 1. ARCHITETTURA (file di produzione)

| File | Ruolo |
|---|---|
| `tennis_scalper_bot.py` | **Il bot armabile** (`TennisScalperStrategy`): maker two-sided, gate, cicli, contabilità (fix 11/07 inclusi: tolleranza 0.02, residuo incondizionato, stop parziali). |
| `run_tennis_scalper.py` | `TENNIS_PARAMS` (preset live: `inplay_tick_enabled: off`). |
| `tennis_flb_bot.py` / `tennis_swing_bot.py` / `tennis_pro_bot.py` | Strategie direzionali (FLB ⭐ unica tesi con struttura, non provata; Swing e Pro: rosse, tenute per riferimento). |
| `tennis_lab.py` / `tennis_lab_score.py` | Motore sweep di RICERCA. ⚠️ `bet_delay_ms="auto"` = **DOPPIO delay** con flumine (che il betDelay lo applica già) e **maker/taker con etichette INVERTITE** (righe ~271-279): usarlo solo con `bet_delay_ms=0` e rileggendo le etichette. |
| `tests/test_harness_golden.py` | Golden-rule dell'harness (8 scenari sintetici) — PERMANENTE. |
| `Betfair/stream/tennis_live/` | Runner live single-stream + order worker (OFF/PAPER/LIVE). |
| `_validazione_tennis_1tick_20260710/` (root repo, non tracciato) | **Questa missione**: fisica (`fisica.py`, `out_fisica/`, `fisica_report.txt`), Atlante (`atlas_tennis.py`, `out_atlas/`, `atlas_report.txt`), baseline (`baseline.py`, `out_baseline/`), scan set betting. |
| `_validazione_20260711/bt_tennis/` | Harness fedele v2 con audit per-run (betDelay visti, parametri effettivi, fill, naked) — è il riferimento per i backtest del bot armabile. |

---

## 2. COME OPERA — il tick PRE-MATCH (l'unico validato)

La scena: MATCH_ODDS di un main-draw liquido (es. Osaka–Muchova), 1-3 ore al
via. Book stretto, flusso vero. Il bot maker si mette in coda sui due lati:

```
        FAVORITO — book pre-match (tick 0.01)
  PREZZO |  offre BACK a te   |  offre LAY a te
  1.42   |                    |   890 €
  1.41   |                    |   615 €  ← best LAY
  1.40   |    540 €           |          ← best BACK
  1.39   |    720 €           |

  mossa: BACK 25€ in coda @1.41  +  LAY 25€ in coda @1.40
  ciclo felice: entrambe consumate dal flusso = 1 tick incassato
  → equalizza → +0.11/+0.18 € VERDI su qualsiasi risultato → STOP (missione)
  cicli difensivi: scratch a pari / stop 1 tick / requote
```

**Gate che decidono (misurati, non a sentimento)**: il book deve STAMPARE
sui due lati — sul campione del 07/07 solo i main-draw ATP/WTA hanno flusso
pre-match (Osaka 7.6k€ scambiati pre, Djokovic 18.6k€); i 4 ITF pre-match =
zero volume = zero ingressi (gate corretto, 0 ordini). Pre-match betDelay=0:
nessun rischio evento, l'unico avversario è la coda.

**Numeri (harness v2 certificato, commissione 5%, fill conservativi):**

| Evento | pre_locked | tempo al verde | naked |
|---|---|---|---|
| 35793859 Osaka–Muchova | **+0.11** | 63′ | 0 |
| 35793960 Djokovic–Auger | **+0.18** | 166′ (pre-match lungo) | 0 |
| altri 4 con pre-match (ITF) | 0.00 | book morto: gate fuori | 0 |

⚠️ n=2 verdi: profilo identico al pre-match calcio (5/6) ma campione piccolo
→ prima dei soldi veri: paper su 20-30 main-draw liquidi.

---

## 3. CONFIGURAZIONE OPERATIVA CERTIFICATA

```
TENNIS_PARAMS (run_tennis_scalper.py) — già allineata l'11/07:
  one_tick_per_phase   = True    ← missione "1 tick"
  inplay_tick_enabled  = OFF     ← NON riattivare senza dati nuovi (§5)
  runner_filter        = favorite
  stake                = 25
Protezioni solo-live da SPEGNERE nei backtest: size_step=0, live_min_bet=0,
max_txn_hour alto (il wall-clock nel replay scatta a vuoto).
```

---

## 4. BASELINE ONESTE delle strategie esistenti (rifatte 10/07, delay VERO)

Harness: FlumineSimulation + `simulation_available_prices=False`, betDelay
applicato DA FLUMINE (bot armabili senza delay interno → nessun doppio
delay), commissione 5% sul netto vincente, metrica = Σ `order.simulated.profit`
dal blotter + **locked** = min(P&L se vince sel1, P&L se vince sel2).
Archivio: 59 eventi in-play del 07/07 (100 registrati, 60 con raw+score).

| Strategia (config prod.) | n eventi con fill | Net TOT | Locked TOT | Verdetto |
|---|---|---|---|---|
| Scalper maker in-play (v2, 11/07) | 34 | — | **−66.46** (1 verde/34, mediana ciclo −0.79) | ❌ NO-GO strutturale |
| Scalper maker pre-match missione (v2) | 2 liquidi | +0.29 | **+0.29** | ✅ GO (n piccolo) |
| FLB lay≤1.05 hold | 3 | −0.30 | −0.30 | 🔬 0 crolli sul campione |
| FLB lay≤1.10 hold | 4 | −0.68 | −0.68 | 🔬 idem (storico +1.84 era su 2 match scelti, senza commissione) |
| FLB lay≤1.10 hybrid | 4 | −0.52 | −0.52 | 🔬 idem |
| Swing z2.0 maker | 2 | −10.19 | −10.19 | ❌ conferma rosso |
| Swing z2.0 taker | 4 | −7.05 | −7.32 | ❌ conferma rosso |
| Pro (6 setup, grass) | 1 | −0.20 | −0.19 | ❌ quasi mai fill, e perde |
| SET_BETTING (scan 24 reg.) | — | — | — | ❌ book morto: spread p50 27 tick, trd top 4.8k poi ~0 |

**FLB resta l'unica tesi con struttura** (liability ~0.10-0.16 vs upside 2€
sul crollo) ma il breakeven implica ≥7-9% di crolli del quasi-certo: sul
07/07 = 0 crolli su 4 lay. Serve un campione GRANDE (≥50 lay) prima di
qualsiasi verdetto. Non è comunque un "tick": è direzionale (locked<0).

---

## 5. LA FISICA DEL TENNIS (misurata su 59 eventi, 56 con score utile)

Il riferimento: `_validazione_tennis_1tick_20260710/fisica_report.txt`.
È QUESTA la sezione da rileggere prima di ogni nuova idea in-play.

1. **Il tennis non sospende**: 4 micro-sospensioni (0.2s) su 59 match. Il
   rischio evento non è la sospensione (calcio) ma il **salto-punto col
   mercato APERTO e betDelay 3s** (5s su alcuni ITF: 52 eventi @3s, 7 @5s
   — SEMPRE letto dai raw, mai assunto).
2. **Il "gol del tennis" è il punto, e il mercato lo prezza PRIMA di noi**:
   attorno all'evento IPS il movimento mediano è già fatto all'82-88%
   (punto −4.5 tick già corsi; break −6.5; hold −2.5). Chi è in campo
   (courtsider) muove il book 2-8s prima che il nostro feed lo sappia.
   → ogni segnale score-driven parte battuto in partenza.
3. **Tra i punti la quiete è VERA**: |Δmid| in 15s senza eventi = p50 0.0,
   p90 1.5 tick. Ma quiete = zero scambi = zero fill per il maker: il
   resting si riempie solo DENTRO il movimento (adverse selection — è il
   perché del 1/34).
4. **Niente theta**: drift del favorito tra un game e l'altro p50 = **0.0
   tick/min** (−0.3 se serve il fav, +0.3 se riceve: rumore). Il motore del
   calcio (decay dell'Under) **nel tennis MATCH_ODDS non esiste**: la quota
   si muove SOLO a stati discreti (punti), in due direzioni.
5. **Gap**: %(salto ≥2 tick in 5s) = 4.8% dei campioni; p99 = 5.5-7 tick;
   max 25-42 tick (break/set). Piccoli ma CONTINUI: il book respira ogni
   punto — lo stop a 1-2 tick è sempre in gioco.
6. **Book per fascia prezzo del favorito** (in-play): 1.01-1.20 spread p50
   2 tick (35% del tempo ≤1); 1.20-1.50 → 4 tick; 1.50-2.00 → 7 tick;
   size ai best ~60-140€. Fuori dalla zona 1.01-1.5 il 1-tick non ha
   nemmeno il campo da gioco.
7. **Il flusso è a raffiche**: mediana degli scambi nei 10s attorno a un
   punto ≈ 0€ anche nei match liquidi (base media 93€/10s concentrata in
   burst attorno ai game). t2fill mediano dell'uscita a −1 tick: 45-90s.
8. **Continuazione post-break** (|pre|≥3 tick): 66% continua dopo il
   segnale IPS (set: 71%) — l'UNICO pattern direzionale post-feed. Ma
   l'Atlante dice che NON si converte in un tick incassato (§6): la coda
   dell'uscita perde la corsa contro lo stop anche lì.
9. **Il break point SALVATO non ha "rally di sollievo"** (n=167, match con
   flusso): pre10 −8 tick (già corso), post15 mediano −0.5, continua/reverte
   48%/41% = indistinguibile da un punto normale. Il salvataggio è prezzato
   PRIMA che l'IPS ce lo dica.
10. **Le escursioni grandi sono INFORMATE, non over-reaction**: un ordine
    resting a +3/+5 tick dal best si riempie nel 41-48% delle finestre nei
    match vivi, ma quando si riempie sul runner del servitore **il game
    finisce in BREAK 53 volte su 54** (hold ~1-2%!). Il mercato non
    sovra-reagisce alla scala raggiungibile: chi consuma il book fino al
    nostro livello SA (courtsider). EV −6/−8 tick per fill, in ogni cella
    (K, fascia, stato) — vedi `out_fade/` + `fade_report.txt`.
11. **Regole Betfair 2025-26 (fonti in fondo)**: dal 2025 gli ordini
    PASSIVI tennis NON hanno bet delay (il 3-5s resta solo per chi prende
    il prezzo); le cancellazioni sono sempre istantanee; nel 2026 Betfair
    testa delay dinamici 1s ai cambi campo. NB: flumine applica il betDelay
    a TUTTI gli ordini simulati → i backtest maker sono PESSIMISTI
    sull'ingresso; non cambia i verdetti (il problema è l'adverse
    selection, non il timing d'ingresso).
12. **Cross-book lock (back-back / lay-lay sui 2 runner)**: 2 episodi in
    85 ore in-play, durata max 0.9s, 0 catturabili (il cross-matching
    Betfair li chiude prima del nostro delay). Non è una strada.
13. **Maker in FINESTRA SICURA (post-game/cambio campo, passivo istantaneo
    per regole 2025)**: 791 finestre su 56 match — il ciclo completo dei
    due lati NON avviene MAI (0.0% a 15s; 0.4% a 25s; 2.9-4.4% solo con
    spread≤1, n piccoli), una gamba sola si riempie 7-30% con scratch
    avverso mediano 1-1.5 tick → EV −0.08/−0.44 tick per finestra, negativo
    in TUTTE le celle. Il flusso non informato bilaterale nella quiete
    tennis ≈ NON ESISTE (coerente col §5.7): tra i punti non scambia
    nessuno, dentro i punti scambiano gli informati.

---

## 6. L'ATLANTE TENNIS — la pagella dei momenti (v0, 10/07)

**Metodo** (ereditato dal calcio, esecuzione ricalibrata sul tennis): ogni
10s di in-play, per OGNI runner con book valido, si simula l'operazione
"taker 1 tick" col modello certificato — BACK taker al best, vivo dopo
betDelay reale (3s/5s dai raw) + 0.12s latenza, all'attivazione se il prezzo
è scappato = entry_miss; uscita LAY resting a −1 tick con PIQ, fill sul
traded DIMEZZATO; stop a +2 tick; timeout 300s. Features: microstruttura +
punteggio ALLINEATO ALL'INFO-SET LIVE (timestamp IPS, zero lookahead).

**v0: 28.839 momenti, 59 eventi, 6 "vivi" (trd mediano ≥50€/min).**

| Cella (eventi vivi) | n | fill | stop | EV tick/occ. |
|---|---|---|---|---|
| Baseline tutto l'archivio | 28.839 | 3.0% | 58% | −1.53 |
| Solo eventi vivi | 4.491 | 8.8% | 57% | −1.32 |
| spread≤1 | 1.298 | 9.4% | 39% | −0.87 |
| S16-analog calcio (spr≤1+cadenza+coda<35%) | 120 | 11.7% | 42% | −1.09 |
| tra i punti (5-25s dal punto) | 1.623 | 9.1% | 58% | −1.37 |
| post-BREAK a favore (≤120s) | 106 | 10.4% | 56% | −1.20 |
| spr≤1 + post-BREAK a favore | 47 | 14.9% | 45% | −0.90 |
| spr≤1 + beneficiario ultimo punto + p<1.2 | 340 | 2.1% | 29% | **−0.62 (best)** |
| ...tutte le altre 20+ celle | — | — | — | tutte negative |

**Verdetto v0: NESSUNA cella positiva o vicina allo zero.** Per pareggiare
un'operazione 1-tick serve stop-rate < fill%/2 (≈5% con fill 10%): la cella
migliore del tennis fa 29-39% di stop, il calcio (S16+linea) faceva **0.9%**.
La differenza è la fisica: nel calcio il decay spinge in UNA direzione e lo
stop è un evento raro; nel tennis il mid oscilla ±diversi tick a ogni punto
e la corsa "coda a −1 tick vs stop a +2" si perde SEMPRE, in ogni stato del
punteggio, in ogni fascia, in ogni direzione. Anche il post-break (l'unico
momentum vero, §5.8) muore qui — stavolta col delay VERO 3s, non col doppio
delay dei vecchi sweep: il verdetto storico era giusto per la ragione giusta.

**Come si aggiorna**: `python atlas_tennis.py all` + `atlas_report.py`
(in `_validazione_tennis_1tick_20260710/`) su ogni nuova infornata di
registrazioni (`record_multi.py`). Ogni refresh: aggiornare la tabella e §11.

---

## 7. HARNESS — REGOLE D'ORO TENNIS (violarle = numeri falsi)

1. flumine 2.13.11 **APPLICA il betDelay in simulazione** (certificato dal
   sorgente l'11/07): MAI delay a mano nei bot/harness. `tennis_lab` con
   `bet_delay_ms="auto"` = doppio delay (~6.1s invece di 3s) → usarlo solo
   con `bet_delay_ms=0`.
2. betDelay tennis: **3s** (5s su alcuni ITF) — SEMPRE letto dai raw
   (`marketDefinition.betDelay`), mai hardcoded. Pre-match = 0.
3. Commissione: flumine NON la applica (`commission_base=0`) → **5%**
   per-mercato sul netto vincente, esplicita nel report.
4. `simulation_available_prices=False` (fill solo su volume tradato,
   dimezzato, con coda PIQ) = maker onesto. Il taker si modella
   all'attivazione: prezzo scappato = entry_miss, non inseguire.
5. Metrica = Σ `order.simulated.profit` dal blotter (mai ricostruita) +
   **locked** = min sui 2 esiti. `simulated.profit` è valido SOLO se il
   mercato è CLOSED nel raw (settlement presente).
6. Punteggio nei backtest: iniettare la timeline `.score.jsonl` ai timestamp
   IPS (info-set live, ±3s poll +2-8s latenza feed) — MAI condizioni
   sub-secondo sul punteggio: quel timing non l'abbiamo (§5.2).
7. Mappa sel→giocatore: dal WINNER a settlement × set finali dello score
   (offline) o dal catalogo nomi (live). Fail-safe: senza mappa niente
   feature side-aware, il bot score-driven NON entra.
8. Golden-rule PRIMA di credere a un numero: `pytest
   Betfair/stream/tennis_scalper/tests/ -q` (82 verdi, incl. 8 harness golden).
9. Gambe nude: |net_win − net_lose| > 0.30 per selezione sugli ordini
   regolati = violazione. Audit per-run come `bt_tennis/bt_harness.py`.
10. Gate liquidità in diagnostica APERTI (min_matched=0) per distinguere
    "gate blocca" da "nessun segnale" (bug #6 storico).

---

## 8. DOVE SONO I TEST (missione 10/07)

- `_validazione_tennis_1tick_20260710/` (root repo, NON tracciato):
  `fisica.py` + `out_fisica/` (60 JSON) + `fisica_report.txt` · `atlas_tennis.py`
  + `out_atlas/` (28.839 campioni) + `atlas_report.txt` · `baseline.py` +
  `out_baseline/{flb,swing,pro}.jsonl` · `setbetting_scan.py` · `mcm.py`
  (parser MCM certificato) · `score_tl.py` (timeline punteggio → eventi) ·
  **seconda ondata**: `atlas_fade.py` + `out_fade/` (5.934 bracket) +
  `fade_report.txt` · `safewindow.py` + `out_safewin/` (791 finestre) ·
  `crossbook.py` + `out_crossbook/`.
- `_validazione_20260711/bt_tennis/` — harness v2 del bot armabile (audit
  per-run completo), `results_v2.json` (89 run).
- Dati: `C:\Users\Admin\Desktop\tennis_rec\20260707` (100 eventi MATCH_ODDS,
  60 con raw+score) + `setbetting_20260707` (24-27 registrazioni).

## 9. REGISTRO DECISIONI (non ridiscutere senza dati nuovi)

| Data | Decisione | Perché |
|---|---|---|
| 07/07 | No edge meccanico in-play (~1100 combo, 9 famiglie) | campagna esaustiva, harness golden-rule, metrica locked |
| 11/07 | **PRE-MATCH GO solo main-draw liquidi** | v2: 2/2 verdi (+0.11/+0.18), ITF a zero volume correttamente fuori |
| 11/07 | **IN-PLAY maker NO-GO strutturale** (`inplay_tick_enabled: off`) | 1/34, locked −66, delay 3s > gap-guard, adverse selection |
| 10/07 | **IN-PLAY taker 1-tick NO-GO** (questa missione) | Atlante 28.839 momenti: OGNI cella EV<0 (best −0.62), stop 29-65% vs 0.9% del calcio |
| 10/07 | Momentum post-break NON converte NEMMENO col delay vero 3s | cella dedicata: fill 10-15%, stop 45-56%, EV −0.9/−1.2 |
| 10/07 | **SET_BETTING chiuso su .it** | scan 24 reg.: spread p50 27 tick, trd ≈ 0 |
| 10/07 | Swing e Pro confermate rosse a delay corretto | baseline: −10.2/−7.1 (Swing), −0.20 con 1 solo evento con fill (Pro) |
| 10/07 | FLB: né promossa né chiusa | 0 crolli su 4 lay (−0.68); breakeven ≥7-9% crolli: serve n≥50 |
| 10/07 | Niente regole calcio senza misura tennis | fisica: no sospensioni, no theta, oscillazione bidirezionale per punto |
| 10/07 | **Seconda ondata "trova il modo" (richiesta utente): 5 meccaniche nuove misurate, tutte ❌** | fade escursioni (fill=break veri 53/54) · sollievo BP-salvato (inesistente) · maker finestra sicura passivo-istantaneo (0% cicli) · cross-book lock (0 catturabili/85h) · +letteratura pro concorde | 10/07 |
| 10/07 | **La diagnosi unificante: col feed IPS (3-8s tardi) siamo la controparte dei courtsider in OGNI meccanica** | misura: 82-88% del movimento pre-IPS; escursioni raggiungibili = informate; flusso quieto ≈ 0 | 10/07 |
| 10/07 | In-play si riapre SOLO con feed sub-secondo o con campagna swing multi-punto dedicata | è infrastruttura/modello, non parametri; premio feed misurato: 4.5-8 tick/punto | 10/07 |

## 10. PROSSIMI PASSI — IL CICLO OPERATIVO (in ordine)

1. **Paper pre-match** og1 su 20-30 main-draw liquidi (ATP/WTA con flusso
   pre ≥1k€): criterio GO/NO-GO per lo stake reale del tick pre-match.
   Selezione partite = la vera leva (il bot già filtra col gate).
   **Timing (misurato, n=3 liquidi)**: accendere **~3h prima del via**
   (minimo 90′); book tradabile a finestre da 1.5-4h prima; il tick storico
   arriva 60-100′ PRIMA del via; il volume grosso è negli ultimi 30′ ma
   negli ultimi 15′ il book PEGGIORA (spread riallargato, tradabile 4-12%).
2. **Registrare MIRATO ai match GIGANTI** (`record_multi.py` nelle serate
   Slam/Masters/finali, target ≥500k€ matched): è il test dell'ultima
   porta in-play (ipotesi liquidità-estrema, §11) — con spread stabile a
   1 tick la matematica di ogni meccanica cambia. Quando l'archivio ha
   10-20 match così: rigirare TUTTA la batteria (atlante v1/v2,
   safewindow, swing_break) su quel sotto-archivio. Ogni partita ingrossa
   anche il campione FLB gratis.
3. **FLB**: accumulare lay≤1.10 sul registrato fino a n≥50 (contatore in
   §11); solo allora verdetto.
4. In-play: NON riaprire con le stesse meccaniche sull'archivio attuale —
   12 famiglie falsificate (§11). Niente feed a pagamento (§10.1). L'unica
   riapertura legittima è il punto 2.
5. Ogni refresh dell'Atlante: aggiornare §6 e §11.

### 10.1 FEED VELOCE — costi reali (ricerca 10/07, fonti in fondo a §11)

| Opzione | Latenza vs punto | Costo | Privati? |
|---|---|---|---|
| Betfair IPS (attuale) | ~2-8s | gratis | — |
| **Bet Angel Pro feed tennis** | ~1-2s dal pulsante umpire (≈2-5s di vantaggio su IPS) | **£150/ANNO** | ✅ |
| BetsAPI (specchio bet365) | ~2-5s | $150/mese | ✅ (zona grigia) |
| tennis-api.com | "sub-secondo" NON verificato | ~$30-300/mese | ✅ (trial) |
| Goalserve | 5s (≥ IPS, inutile) | $150/mese | ✅ |
| TDI/Sportradar (ufficiale ATP) | ~1-3s (umpire) | $10k+/mese | ❌ solo B2B licenziati |
| Courtsiding | ~0.5s | migliaia €/mese | ❌ ToS/legale |

**Verità di catena**: il feed "ufficiale" parte dal TABLET dell'umpire
(+1-3s di gesto umano) — nessun feed comprabile da privato è davvero
sub-secondo, e il courtsider fisico (0.5s) resta imbattibile. Nemmeno
Bet Angel possiede i dati: li LICENZIA da un provider B2B e li rivende
spalmati sugli abbonati.

**ESPERIMENTO DECISIVO (10/07, costo 0€)** — Atlante rigirato con la
timeline punteggi ANTICIPATA di 4s e 8s (= simulare un feed più veloce
di qualunque cosa sia in vendita): **nessuna cella score-driven gira
positiva nemmeno a +8s** (benef. punto: EV −1.30→−1.24; spr≤1+benef:
−0.85→−0.80; post-break: invariato). Il collo di bottiglia NON è il feed:
è l'operazione 1-tick stessa (corsa coda-vs-stop in mercato oscillante).
→ **NON comprare NESSUN feed per il tick in-play: non lo sbloccherebbe.**
(`shift_compare.py`, `out_atlas_shift{4,8}/`). L'unica op che un feed
velocissimo abilita è lo sniping degli ordini stale altrui (= FARE il
courtsider): infrastruttura fisica, ToS/legale, fuori perimetro.
Il feed veloce resterebbe utile solo in DIFESA (cancel pre-pick-off) per
un eventuale maker futuro — ma il maker è senza carburante (§5.13).

## 11. REGISTRO IPOTESI (aggiornare SEMPRE qui)

> Stati: ✅ VALIDATA · ❌ FALSIFICATA · 🔬 DA VALIDARE. Non si valida due
> volte, non si ridiscute il falsificato senza dati nuovi.

| Ipotesi | Stato | Evidenza | Data |
|---|---|---|---|
| Tick pre-match maker su main-draw liquidi (og1) | ✅ VALIDATA (n=2!) | +0.11/+0.18 locked, 63′/166′, 0 naked; ITF correttamente fuori | 11/07 |
| Tick in-play maker (resting two-sided, continuo) | ❌ FALSIFICATA | 1/34, locked −66, mediana ciclo −0.79 (v2) | 11/07 |
| Tick in-play taker (sniper-analog, ogni condizionamento) | ❌ FALSIFICATA | Atlante 28.839 momenti: tutte le celle EV<0; stop-rate 29-65% | 10/07 |
| Theta/decay strutturale su MATCH_ODDS tennis | ❌ FALSIFICATA | drift tra game p50 = 0.0 tick/min (n=364 segmenti) | 10/07 |
| Fuoco "tra i punti" (quiete = opportunità, taker) | ❌ FALSIFICATA | quiete vera ma zero scambi: fill 9.1%, stop 58%, EV −1.37 | 10/07 |
| Momentum post-break convertibile col delay vero 3s | ❌ FALSIFICATA | continuazione 66% ESISTE ma non si incassa: EV −0.9/−1.2 | 10/07 |
| Anticipo del break (entrare SUL break point) | ❌ FALSIFICATA | cella BP/SP: fill 8.5%, stop 56%, EV −1.4; spread NON si allarga sotto BP (4=4 tick) | 10/07 |
| SET_BETTING come mercato alternativo per il tick | ❌ FALSIFICATA (.it) | spread p50 27 tick, trd top 4.8k€ poi ~0 (24 reg.) | 10/07 |
| **FADE dell'escursione (resting BACK a +3/+5 tick, "il mercato sovra-reagisce")** | ❌ FALSIFICATA | Atlante v2 (5.934 bracket): i fill sono i BREAK VERI (hold 1/54 quando servo io!), EV −6/−8 tick/fill in ogni cella; le escursioni raggiungibili sono informate, non emotive | 10/07 |
| **Rally di sollievo post-BP-salvato (entrare al segnale IPS del salvataggio)** | ❌ FALSIFICATA | n=167: post15 mediano −0.5 tick, cont/rev 48/41 = punto normale; tutto prezzato pre-IPS | 10/07 |
| **Maker in finestra sicura post-game/cambio campo (passivo istantaneo, regole 2025)** | ❌ FALSIFICATA | 791 finestre/56 match: cicli completi 0.0% (15s) / 0.4% (25s); una gamba 7-30% con scratch avverso; EV<0 ovunque. Il flusso bilaterale non informato nella quiete NON esiste | 10/07 |
| **Cross-book lock (back-back/lay-lay sui 2 runner)** | ❌ FALSIFICATA | 2 episodi in 85h in-play, durata ≤0.9s, 0 catturabili col delay | 10/07 |
| Entrare a 30-40 (un punto = break) | ❌ SCONSIGLIATA (letteratura pro) | convergenza fonti practitioner: solo 0-40/15-40; MAI 30-40 | 10/07 |
| FLB lay del favorito estremo, no stop | 🔬 DA VALIDARE | 0 crolli/4 lay (−0.68) su 07/07; storico +1.84 su 2 match scelti; serve n≥50 lay | 10/07 |
| Feed punteggi più veloce ribalta il TICK in-play | ❌ FALSIFICATA | Atlante con timeline anticipata +4s/+8s (feed courtsider-grade simulato): NESSUNA cella positiva, EV quasi invariato. Il limite è l'op, non l'informazione. NON comprare feed per questo | 10/07 |
| Sniping ordini stale col feed sub-secondo (= fare il courtsider) | 🔬 FUORI PERIMETRO | unica op che il feed veloce abilita; richiede infra fisica sul campo, viola ToS tornei (ban), non simulabile dai nostri raw | 10/07 |
| Swing direzionale multi-punto (Weston: lay leader +3 nel tie-break; compression points; lay del vincitore del set 1) | 🔬 DA VALIDARE | letteratura pro concorde: l'edge retail in-play è a orizzonte multi-punto (latenza irrilevante); è una SCOMMESSA modellata (locked<0), non un tick: serve campagna dedicata con base-rate | 10/07 |
| SEGUIRE il break (swing taker multi-game, feed IPS) | ❌ FALSIFICATA | `swing_break.py`: 908 trade naive = disastro (−2.1/trade); versione onesta (gate spread≤2, stop 15 dal mid, uscite g1/g2/g4/set): **negativa in TUTTE le varianti, train e test concordi** (best g4: −0.49/trade, n=101, 37 ev). Il momentum c'è (1-3 tick) ma < costo round-trip (spread 4-7 tick + delay). Riapribile SOLO sotto l'ipotesi liquidità-estrema (sotto) | 10/07 |
| **In-play su LIQUIDITÀ ESTREMA (Slam/Masters serali, ≥500k€ matched, spread stabile 1 tick)** | 🔬 DA VALIDARE (ultima porta) | il muro di OGNI meccanica misurata è lo spread 4-7 tick; nel nostro archivio (1 giorno, max 146k€) i match a spread 1 sono quasi assenti. Con spread 1 la matematica di maker/swing CAMBIA. Azione: registrare i match giganti e rigirare TUTTA la batteria (atlante v1/v2, safewindow, swing) su quell'archivio. Costo 0 | 10/07 |
| Overreaction su eventi ad ALTA SORPRESA (underdog breakka/vince set vs fortissimo favorito), finestra 20s-5min | 🔬 DA VALIDARE | documentata solo sul calcio (Angelini 2022, Choi-Hui 2014); mai testata sul tennis; campione 07/07 troppo piccolo per la coda "alta sorpresa" | 10/07 |
| Delay dinamico 1s ai cambi campo (rollout Betfair 2026) | 🔬 MONITORARE | riduce il costo taker nelle finestre sicure, ma il flusso lì misurato ≈ 0: da rimisurare SE il rollout cambia il comportamento del book | 10/07 |
| Pre-match: quanto generalizza oltre n=2 | 🔬 DA VALIDARE | paper 20-30 main-draw liquidi (passo 1 di §10) | 10/07 |
| Telemetria real-time stile tool-pro (requisito globale) | 🔬 DA FARE | vale anche per il tennis (vedi bibbia calcio §11) | 10/07 |

### Fonti accademiche (ricerca 10/07 — convergono con le nostre misure)
- **Easton & Uylangco 2010 (IJF)** — UNICO studio punto-per-punto su Betfair
  tennis: correlazione altissima modello-mercato; i prezzi ANTICIPANO il
  break fino a 4 punti prima della fine del game; unica anomalia =
  **SOTTO-reazione al momentum post-break** (semmai si SEGUE il break, non
  se ne fa il fade). Contro-evidenza diretta alla tesi "overreaction".
- **Bizzozero, Flepp & Franck 2018 (JEBO)** — i fast trader (courtsider)
  fanno il **60-70% dell'intera reazione di prezzo entro ~5s** e prezzano
  correttamente (no overshoot). = il nostro 82-88% pre-IPS, misurato da
  altri su altri anni/tornei.
- **O'Malley 2008 / Klaassen-Magnus 2001-03** — i salti sui punti chiave
  sono FAIR VALUE meccanico (hold da 30-40 ≈50% vs ~83% a inizio game; un
  BP decisivo vale 19-27 punti di probabilità). K&M NON parlano di
  overreaction del mercato (chi lo cita così estrapola); le deviazioni
  dall'i.i.d. dei punti sono PICCOLE (~1-3 p.p.).
- **Brown 2012 / Brown & Yang 2014** — chi profitta in-play lo fa per
  VELOCITÀ, non per analisi; il mispricing vero in-play sta nel lag
  match-odds → set-betting (5,3% medio) — mercato che su .it è MORTO
  (nostra misura, §4).
- **Angelini et al. 2022 + Choi & Hui 2014 (calcio)** — l'overreaction
  esiste solo su eventi MOLTO sorprendenti, finestra 20s-5min (mai
  documentata sul tennis): eventuale analogo tennis = underdog che breakka
  il fortissimo favorito, orizzonte swing, NON tick.
- **Kovalchik 2016** — nessun modello pubblicato batte i bookmaker
  (accuracy: il mercato è il benchmark).

### Fonti practitioner/regole exchange (ricerca 10/07)
- Passive bet delay tennis 100% tornei (2025) + test delay dinamico 1s ai
  cambi campo (2026): newsletter ufficiali Betfair Exchange (ago 2025,
  gen 2026); spiegazione Bet Angel "betfair-passive-bet-delay".
- Bet delay 3s dal 2020 (5s su alcuni tornei/ITF) — coerente coi nostri raw.
- Forum Bet Angel (Peter Webb/LeTiss): scalping punto-per-punto = pasto dei
  courtsider; operare solo tra i punti/game/cambi campo; ordini resting
  raccolti quando la probabilità vera è già oltre il prezzo (= il nostro
  fade 53/54). Strategia 15-40 (mai 30-40), tie-break Weston (lay leader
  +3: recupero 16% ATP / 20% WTA), bot pubblici back/lay-the-server senza
  profitti documentati.
