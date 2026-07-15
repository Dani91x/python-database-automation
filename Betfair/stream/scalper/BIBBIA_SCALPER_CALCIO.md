# BIBBIA — BOT SCALPING CALCIO (Betfair)

> Documento unico di verità. Aggiornato al **11/07/2026** (sessione backtest
> v1/v2 + fix contabili + sniper in-play). Se riprendi il lavoro, PARTI DA QUI:
> tutto ciò che è stato testato, certificato, bocciato o lasciato aperto è
> scritto sotto, con i numeri. NON ripetere test già fatti.

---

## 0-bis. VERDETTO OPERATORE POST-PRIMA-LIVE (10/07 sera, vincolante)

> **"Attualmente questo bot è inutile: oltre a non generare un centesimo,
> rischia solo di perdere soldi. Non ho visto nessun guadagno. Queste cose
> [posizioni-bug silenziose] non devono MAI più succedere."**

Bilancio reale della serata Spagna-Belgio (stake 25 maker / 5 sniper):
maker pre-match 14 cicli → 0€ generati (13 scratch-par su book elite, 1 stop
−0.25, 1 verde +0.49 NON spalmato e quindi cieco alla missione); sniper 2
colpi → 1 stop ~0, 1 verde +0.03; **BUG submin → posizione-bug da −10/+8
chiusa a mano dall'operatore a ~−5€.** Totale serata: **≈ −4.7€.**
Il bot fermato dall'operatore a fine serata. STOP eseguito, conto verificato
pulito (esposizione residua −0.92€ = micro-residui pre-match by-design).

**CONDIZIONI PER IL PROSSIMO LIVE (non negoziabili, in quest'ordine):**
1. Fix BUG submin (§12.1) + **riconciliazione bot↔conto a ogni heartbeat
   con freeze automatico su divergenza >0.5€** — MAI più posizioni invisibili.
2. Stake pre-dimensionati per il green simmetrico (direttiva §12.1) — il
   submin diventa un caso raro invece che la norma.
3. Flatten KO−3′ GARANTITO (termina sempre, contabilizza sempre).
4. Telemetria onesta (scalp=tick vero; specchio senza righe stantie).
4c. **Registrazione Spagna 10/07**: book PARSATO completo (440MB, pre-match→97′)
   ✓ = fonte per Replay e review. Il tee RAW NATIVO si è fermato alle 19:12
   (riavvii dello stack durante il crash UI): l'Atlante/mcm e il backtest
   flumine sui raw nativi NON coprono l'in-play di Spagna → per il conteggio
   occasioni serve un loader del formato parsato (ladder depth presente).
   Fix: il tee nativo deve riarmarsi a ogni (ri)avvio del runner + heartbeat
   "recorder vivo" per ENTRAMBI i formati (bytes scritti/min in telemetria).
4b. **"Segui live" con conferma esplicita** (danno del 10/07: DUE partite
   irlandesi cliccate durante il crash UI → follow MAI registrato, dati
   PERSI per sempre — l'operatore credeva di registrarle): il click deve
   mostrare ack visibile (riga in live_follow verificata + toast di
   conferma/errore), e la pagina Segui Live deve mostrare lo stato del
   follow (PENDING/STREAMING) entro pochi secondi. Un fallimento silenzioso
   di registrazione = dati irrecuperabili.
5. Replay-vs-live sui raw del 10/07 + conteggio ufficiale delle occasioni.
6. SOLO DOPO: le celle nuove del mostro (§11-bis) — multi-linea, multi-colpo,
   pre-posizionamento — validate sull'Atlante e portate live UNA alla volta.

La difesa ha retto (loss cap, stop, zero gambe nude vere); l'attacco non
esiste ancora e l'esecuzione ha un bug money-critical: il bot NON torna
live finché 1-4 non sono fatti e provati in paper.

> **STATO 11/07 (review massiva eseguita)**: condizioni **1-4 IMPLEMENTATE**
> (commit `802040f` esecuzione blindata, `41bb60c` recorder+ack, `041cd0b`
> multi-linea/colpo+risk manager; 807 pytest + 656 vitest verdi, dettagli in
> §13). Condizione **5 FATTA**: replay-vs-live → **modello fill AFFIDABILE**
> (replay +0.29 vs live +0.24, stessa firma; problema = solo habitat elite).
> Condizione **6**: multi-linea/multi-colpo CABLATI ma SPENTI di default
> (S16 intatta) — si armano dai params per il paper out-of-sample.
> **Manca SOLO la certificazione paper (§13 F6) prima del ritorno live.**

**MISSIONE DELLA PROSSIMA SESSIONE (ordine dell'operatore, 10/07 notte):
"renderlo REALMENTE uno sniper" — deve GUADAGNARE. Obiettivo unico: da
1 colpo/partita a N colpi VERI (multi-linea, multi-colpo, gate ricalibrati
sulle celle, pre-posizionamento anti-betDelay), su esecuzione blindata
(condizioni 1-4). Metrica di successo: euro incassati per partita in paper
sui raw registrati — non eleganza architetturale.**

## 0. STATO IN UNA RIGA

**PRE-MATCH: VALIDATO e operativo** (missione `one_green_per_phase` + `min_size
300`) · **INTERVALLO HT: BOCCIATO** (`ht_mode` SPENTO) · **SNIPER IN-PLAY:
CABLATO, testato in DEMO LIVE (3 trigger perfetti, §6.5) e CONFERMATO
DALL'ATLANTE come cella migliore dell'archivio (§6.7) → codice da NON
toccare**; prima dei soldi veri: out-of-sample su partite nuove (§10).
Ogni idea nuova passa dal **Registro Ipotesi (§11)** — mai validare due
volte, mai implementare senza numeri.

---

## 1. ARCHITETTURA (file di produzione)

| File | Ruolo |
|---|---|
| `Betfair/stream/scalper/scalper_bot.py` | **Il bot** (`ScalperStrategy`): maker two-sided mean-reversion, gate, cicli, contabilità, protezioni. Fix contabili 11/07 INCLUSI. |
| `Betfair/stream/scalper/scalper_session.py` | Sessione live: `VALIDATED_PARAMS`, whitelist UI, `ht_mode` (opt-in), watcher intervallo, `SESSION_MARKET_TYPES`. |
| `Betfair/stream/scalper/sniper_bot.py` | **Sniper in-play** (`SniperStrategy`, config S16): 1 tick sull'Under coi gate di microstruttura; dry-run = demo. Test: `tests/test_sniper_bot_2026_07_10.py`. |
| `Betfair/stream/scalper/run_scalper.py` | **Harness di backtest FEDELE** (`run_scalper(config)`): FlumineSimulation + metrica ufficiale. |
| `Betfair/stream/scalper/scalper_service.py` / `run_scalper_live.py` | Runner live (avvio dalla UI). |
| `Betfair/stream/backtest/run_backtest.py` | `aggregate_results` = metrica ufficiale (Σ `order.simulated.profit`, commissione 5% per-mercato sul netto vincente). |
| `Betfair/stream/scalper/SCALPER_BOT_DOSSIER.md` | Dossier storico v1/v2 (02/07). Questa bibbia lo AGGIORNA e prevale dove i numeri differiscono. |

**Avvio**: dalla UI come sempre (ScalperPanel → RPC `scalper_activate` →
`scalper_control` → sessione dedicata). La sessione costruisce
`ScalperStrategy` con `VALIDATED_PARAMS` + override whitelisted; col toggle
**"SNIPER in-play"** aggiunge anche `SniperStrategy` (S16) accanto al maker
(`sniper_mode`/`sniper_stake` whitelisted; incompatibile con `ht_mode`).
`dry_run` default TRUE = DEMO: il maker logga le quote, lo sniper emette i
trigger `sniper_dry_fire` senza ordini. Vita sessione: KO+10′ (pre-match),
fino a fine partita con sniper (KO+130′). Mercati sottoscritti:
`MATCH_ODDS, OVER_UNDER_15, OVER_UNDER_25, OVER_UNDER_35`.

---

## 2. COME FUNZIONA IL BOT (pre-match)

1. **Gate di habitat**: quota 1.50–4.6, spread ≤2 tick, `min_size` 300€ ai due
   best, flusso ≥10€/lato in 90s, warmup 60s. Se il book è morto → ZERO
   operazioni (by design: le 4 partite "morte" del campione = 0 ordini).
2. **Ciclo**: due gambe in coda (join/maker), cattura 1 tick (`scalp_ticks 1`),
   scratch a pari se il book gira, stop a 1 tick avverso, requote a 2 tick.
3. **Chiusure garantite**: ogni ciclo finisce PIATTO (equalizzazione;
   micro-residuo ≤0.25€ accettato e CONTABILIZZATO — fix 11/07).
4. **Protezioni evento**: target 1€ con cricchetto (giveback 0.30), loss cap
   1.5€ pre-match (força-flat), stop ingressi a KO−420s, flatten a KO−180s,
   MAI posizioni aperte al KO (0 gambe nude in 148 backtest).
5. **Missione "1 tick per fase"** (`one_green_per_phase=True`, dalla UI): al
   PRIMO ciclo verde (locked ≥0.05€) della fase, stop ingressi di fase.
   **Questa è la modalità VALIDATA per il prodotto "1 tick a partita".**

### 2.1 COME OPERA — spiegazione operativa col ladder (pre-match)

La scena: Match Odds, quota del pareggio, un'ora al KO. Tick da 0.02 in zona 2.xx.

```
              IL LADDER (book del Pareggio)
  PREZZO   |  chi vuole LAYARE      |  chi vuole BACKARE
           |  (offre BACK a te)     |  (offre LAY a te)
  ---------+------------------------+--------------------
   2.26    |                        |   1.410 €
   2.24    |                        |     890 €
   2.22    |                        |     615 €   ← best LAY
   2.20    |     540 €              |             ← best BACK
   2.18    |     720 €              |
   2.16    |   1.130 €              |
```

**Criteri per entrare** (i gate del punto 1 di §2 visti sul ladder — tutti
insieme, sennò niente): quota 1.50–4.6 ✓; spread ≤2 tick (qui 1 ✓); **≥300€
su ENTRAMBI i best** (540 e 615 ✓); flusso ≥10€/lato in 90s (il mercato deve
STAMPARE scambi sui due lati: è il cibo del maker); più di 7′ al KO.

**La mossa: due gambe IN CODA, mai inseguire.**

```
   2.22    |                        |  615€ + [NOSTRO BACK 25€]  ← in fila DIETRO i 615
   2.20    |  540€ + [NOSTRO LAY 25€]                            ← in fila DIETRO i 540
```

Non prendiamo il prezzo di nessuno: ci mettiamo in fila. Chi ha fretta (il
taker) paga lo spread — noi siamo quelli che lo incassano.

**Ciclo felice (scalp)**: un taker aggressivo consuma i 615€ davanti a noi →
il nostro BACK @2.22 si riempie; un altro consuma i 540€ → il nostro LAY
@2.20 si riempie. Comprato 2.22, venduto 2.20 = **1 tick**; il bot equalizza
(~0.23€ di size) → **+0.22€ verdi su qualsiasi risultato**, posizione PIATTA.

**Cicli difensivi**: *scratch* (il più frequente, ~1 per scalp): riempita una
sola gamba e book spostato → esce A PARI, costo ~0; *stop*: book scappa 1
tick contro → fuori, ~−0.25€; *requote*: quote inevase e book spostato di 2
tick → cancella e si rimette in fila ai nuovi touch.

**Missione "1 tick"**: al primo ciclo verde stop ingressi — tick fatto,
partita chiusa (numeri: §4).

**Perché funziona**: pre-match non c'è rischio evento (nessun gol può
gapparti); l'unico avversario è la coda — per questo servono book liquidi
(300€) che stampano su entrambi i lati.

### Fix contabili 11/07 (in produzione, suite 747 test verde)
- Tolleranza di equalizzazione **0.02€** (era 1e-9) su roundtrip QUOTING2 e
  completamento flatten → gli stop/scratch non restano più nel limbo
  FLATTENING e vengono CONTABILIZZATI (`pnl_locked`, `_on_cycle_closed`,
  breaker). `locked = min(net_win, net_lose)`.
- Accettazione micro-residuo (floor −0.25€) **incondizionata** (prima era
  gated su size_step/live_min_bet/exact_exits → mai attiva in sim).
- Parziali QUOTING2: stop avverso ≥ `stop_ticks` (oltre al TTL).
- Effetto misurato (re-run 74 backtest): ledger = settlement (lock ≈ net),
  greens popolati, missione og1 ATTIVA (prima era inerte: locked sempre 0),
  loss cap che si arma davvero. Gli slot sbloccati fanno 3-5× più cicli.

---

## 3. CONFIGURAZIONE OPERATIVA CERTIFICATA

```
VALIDATED_PARAMS (scalper_session.py) + dalla UI:
  one_green_per_phase = True      ← missione "1 tick pre-match"
  ht_mode             = OFF       ← NON attivare (vedi §5)
  stake               = 25
  (min_size resta 300 — NON abbassarlo: 150 → −1.99 nel backtest v2)
```

Protezioni SOLO-live che restano attive in produzione ma vanno **spente nei
backtest** (distorcono il simulatore): `exact_exits`, `size_step`,
`live_min_bet`, `max_txn_hour` (usa wall-clock → nel replay scatta a vuoto).
Evidenza: con `exact_exits=True` in sim i park/submin generano fill spurii →
false gambe nude di 2.5–5.5€.

---

## 4. PRE-MATCH — NUMERI CERTIFICATI (backtest v2, 11/07)

Harness: `run_scalper` fedele, commissione **0.05** (il default è 0: passarla
SEMPRE), fill conservativi, betDelay dai raw applicato DA FLUMINE (0 pre-match,
5s in-play — MAI aggiungere delay a mano), latenze default 0.12/0.17s.
6 eventi × min_size {150,300,400,500} × og {off,on} = 48 run, audit 0
violazioni, 0 gambe nude vere.

### Modalità continua (og=off) — net per evento
| Evento | ms300 | note |
|---|---|---|
| 35768297 Portugal-Croatia | **+0.75** | 22 cicli, 1° verde a 27′ dal primo book |
| 35764745 Ivory-Norway | **+1.16** | 18 cicli, 1° verde a 16′ |
| 35768365 Spain-Austria | 0.00 | book elite congelato: gate fuori (corretto) |
| 35765620 Australia-Egypt | **−0.94** | l'unico rosso: mercato ostile |
| 35777617 Brazil-Norway | **+0.44** | 23′ di pre-match bastano |
| 35787327 Swiss-Colombia | 0.00* | *settlement assente nei raw; ledger +1.44 |
| **TOTALE** | **+1.41** | (ms150 −1.99 · ms400 +0.70 · ms500 +0.41) |

### Modalità MISSIONE (og=on) — il prodotto
| min_size | Net 6 eventi | Eventi col tick | Tempo al 1° verde |
|---|---|---|---|
| **300** | **+0.93** | **5/6** (+0.14…+0.21 cad.) | 3.5′–27′, mediana ~16′ |

**Zero eventi in rosso** in missione (unica eccezione ms150 su book morto).
Il continuo rende di più ma si mangia il −0.94; la missione è il profilo
giusto per "1 tick e stop".

⚠️ Campione = 6 partite: edge reale ma da confermare in paper su 20-30 match
prima di considerarlo reddito.

---

## 5. INTERVALLO HT — BOCCIATO (non riaprire senza dati nuovi)

1. **Backtest solo-HT** (13 eventi, finestra HT reale ±60s, ht_mode di
   produzione: slots 3, breaker 0.50, cap 1.0): aggregato **−2.54** (og0) /
   **−1.74** (og1); verdi in 3/13; 8/13 intervalli senza liquidità (gate
   correttamente fuori). Loss cap si arma (2 eventi) e limita, ma non salva.
2. **Misura fisica** (13 HT, mid Under OU15/25/35): durante l'intervallo
   l'Under **NON decade — sale** di +0.5…+4 tick. Il theta matura col tempo
   di GIOCO, non col cronometro: all'HT non c'è nulla da raccogliere.
3. Conclusione: **`ht_mode` resta un toggle disponibile ma NON va attivato.**
   (Il rilevatore reale dell'intervallo e il watcher restano nel codice e
   funzionano; è l'opportunità che non esiste.)

---

## 6. IN-PLAY — LA STRADA GIUSTA: THETA + SNIPER (prototipo)

### 6.1 La fisica (misure su 19 segmenti 0-0, 13+ eventi)
- Decay dell'Under a 0-0: **OU15 ≈ −1.5 tick/min**, OU25 −1.3, OU35 −0.5,
  Draw −0.5. Oltre OU45 ~0.
- Hazard gol (66 gol/19 match): cresce col minuto; zone calde 45-65′ e 85′+.
- Maker resting a lungo sull'Under = **lotteria** (fill dentro il gap del gol:
  visto +10.82 fortuito — da NON considerare edge).
- Sweep theta "sempre in mercato": la MEDIA di tutte le config PERDE (taker
  −7.8€); finestra 20-40′ su OU15 con target 2 tick = miglior famiglia
  (+3.74/13 eventi) ma 4.4 min medi di esposizione.

### 6.2 Lo SNIPER (prototipo scratchpad, sweep 14 eventi, stake 10)
Armato TUTTA la partita; il momento lo scelgono i gate di microstruttura:
1. **Regime**: ≥2 tick-down del best-back negli ultimi 240s, l'ultimo ≤90s;
2. **Innesco**: size al best-back ≤35% del massimo visto al livello corrente
   (il livello sta per rompersi);
3. **Costo**: spread ≤1 tick → ingresso TAKER.
Uscita: close a entry−1 tick; stop 2 tick; timeout 300s → scratch; **primo
verde → evento chiuso**.

Config migliore **S16** (OU15, stop 2, timeout 300s): **+0.99 netti/14
eventi, 4 ev+ / 1 ev−, worst −0.49, posizione mediana ~114s**, verdi al
18.4′/19.6′/37.5′ (+ scratch positivi). Controllo senza gate: **−3.45** →
il timing È l'edge. Verità fisiche: (a) il tick si incassa in ~2-5 min (la
coda del nuovo livello va consumata; uscire taker = −2 tick = sempre
negativo); (b) ~metà dei match registrati non offre MAI spread ≤1 tick con
coda ≥50€ sull'Under → lo sniper spara solo dove il book è vivo.

### 6.3 COME OPERA LO SNIPER — spiegazione operativa col ladder

La scena: minuto 18, 0-0, Under 1.5. A punteggio fermo l'Under scende da solo
(~1.5 tick/min, §6.1). Tick da 0.05 in zona 3.xx.

```
        UNDER 1.5 — book alle 18:02          e 40 secondi dopo:
   3.50 |              |  1.800 €        3.50 |              |  2.100 €
   3.45 |              |    950 €        3.45 |              |    980 €
   3.40 |    420 €     |             →   3.40 |     95 € ⚠️  |
   3.35 |    880 €     |                 3.35 |    905 €     |
   3.30 |  1.240 €     |                 3.30 |  1.260 €     |
```

**I 3 criteri per sparare** (i gate di §6.2 visti sul ladder — tutti verdi
insieme):
1. **REGIME**: ≥2 tick-down già fatti negli ultimi 4′ (3.50→3.45 alle 17:58,
   3.45→3.40 alle 18:01), l'ultimo entro 90s → il decay lavora ADESSO, non è
   un book congelato;
2. **INNESCO**: la coda al best back è passata da 420€ a **95€** (<35% del
   massimo del livello) → il livello 3.40 sta per rompersi verso il basso;
3. **COSTO**: spread = 1 tick (3.40↔3.45) → entrare da taker costa il minimo.

**La mossa**:

```
  BACK 10€ @3.40 DA TAKER (fill immediato, delay in-play 5.12s)
  e SUBITO in coda l'uscita: LAY 10€ @3.35 (1 tick sotto)

   3.40 |   (rotto) → il livello cede...
   3.35 |   905€ + [NOSTRO LAY in coda]  ← quando 3.35 diventa il nuovo best,
                                            il flusso lo consuma e ci riempie
```

Il tick si incassa quando la coda del NUOVO livello viene mangiata: ~2 minuti
tipici in posizione (mediana 114s, §6.2). Verde ≈ +0.10€ a stake 10 →
**evento CHIUSO, un solo tick per partita**.

**Le difese (in-play il nemico è il GOL)**: stop 2 tick se l'Under sale
contro; timeout 300s → scratch a costo ~0; il gol nei ~2 minuti di
esposizione resta il rischio vero (gap 10-30 tick a mercato sospeso, lo stop
NON esiste) → esposizione minima, un solo tentativo a segno per partita, MAI
ordini maker lasciati a marcire in coda (§6.1: lotteria).

**Perché funziona**: non prevediamo nulla — leggiamo dal book il momento in
cui il movimento già in corso sta per fare il prossimo passo, ci mettiamo
davanti per UN tick e usciamo. Il controllo senza gate perde dove lo sniper
guadagna (§6.2): l'edge è tutto nel QUANDO.

### 6.4 CABLAGGIO IN PRODUZIONE (fatto il 10/07)
- **`sniper_bot.py`**: porting autonomo di S16 (gate cadenza/coda/spread,
  taker, close a −1 tick, stop 2, timeout 300s, primo verde → evento chiuso,
  loss cap 1.0, `force_flat`/`is_flat` per lo stop sicuro, LAPSE-aware).
  **dry_run**: nessun ordine, trigger `sniper_dry_fire` (anti-spam 120s) con
  prezzo/coda/minuto — la DEMO mostra quando e a che prezzo avrebbe sparato.
- **Sessione** (`scalper_session.py`): `sniper_mode`+`sniper_stake`
  whitelisted; sniper AGGIUNTO accanto al maker; `sniper_mode`+`ht_mode`
  insieme → errore esplicito; vita sessione KO+130′; stop/fine-vita fanno
  force-flat su ENTRAMBE le strategie; stats sniper nel heartbeat con
  prefisso `sniper_*`.
- **UI** (`ScalperPanel.tsx`): toggle "🎯 SNIPER in-play (S16)" + stake
  dedicato (default 10); mutuamente esclusivo col toggle HT; typecheck ok.
- **Esecuzione live .it (10/07 sera, prerequisito per i SOLDI VERI)**: lo
  sniper ha ora le STESSE protezioni del maker — `size_step` 0,50, minimi
  per lato (BACK 2 / LAY 0,50), **`exact_exits` con park-trim-replace
  (stesso `trading/submin.py` di produzione)** → uscite a QUALSIASI importo
  e green SPALMATO al centesimo sui due esiti (resti <0,05€ accettati come
  micro, semantica identica allo scalper); micro-residuo ≤0,30 accettato
  dal flatten (niente inseguimenti infiniti). Formula di equalizzazione
  documentata e testata: chiusura con size x=(net_win−net_lose)/prezzo →
  profitto IDENTICO sui due esiti (`compute_green` + test dedicato).
- **Test**: `tests/test_sniper_bot_2026_07_10.py` (18 test: gate, dry-run,
  timeout, verde/missione, loss cap, force-flat, linea dinamica, formula
  green, size .it, submin, micro-residuo). Suite completa: **782 verdi**.

### 6.5 DEMO LIVE ESEGUITA (10/07, CSL Shandong-Yunnan 4-1, dry-run)
Esito: **il cecchino funziona in live**. Evidenze certificate:
- sessione armata con `sniper_mode` (dry_run), 5 mercati a catalogo (le OU
  basse erano gia' CHIUSE al 4-1 — da qui il fix della linea dinamica);
- **linea dinamica**: watcher punteggi → `sniper_line OVER_UNDER_65` in 5s;
- **3 trigger `sniper_dry_fire` perfetti** al 69-74′ reale su Under 6.5:
  @1.28→@1.26→@1.24 (spread 1 tick, code al best 75/64/56€ = innesco coda,
  exit −1 tick, anti-spam 120s ✓). Il decay reale (2 tick in 2′) avrebbe
  incassato TUTTI e tre i tick;
- fine vita sessione a KO+130′ con chiusura pulita (`done`), zero ordini
  reali, zero errori del bot.

**Fix di progettazione trovato E risolto in demo**: la linea Under era
hardcoded OU15 (morta a partita avviata) → ora e' DINAMICA: Under
(gol totali+1).5 via watcher `live_now` (`SniperStrategy.set_line`),
sottoscrizione estesa `SNIPER_MARKET_TYPES` (OU05..OU85), maker blindato
sui tipi storici, posizioni su linea vecchia sempre gestite. +2 test
(suite 775 verdi).

### 6.6 Cosa manca per i SOLDI VERI (ORDINE) + spunti dalla demo
1. **Out-of-sample**: registrare partite nuove e rigirare S16 a parametri
   CONGELATI (campione backtest: 14 match, 6 verdi — fragile).
2. **Clock di gioco reale**: `minute` dei trigger e vita sessione derivano
   dal marketTime, ma il KO reale puo' ritardare (visto: +40′ in CSL) →
   passare a `live_now.minute` per finestre e fine-vita (rischio: sessione
   che muore al ~90′ reale con KO molto ritardato).
3. **Stats sniper nel control**: in demo risultavano 0 nonostante i fire —
   riverificare in una demo pulita (tabelle contaminate dai test E2E di un
   altro agente: righe activity cancellate, status riscritto). Regola: i
   test E2E usino event_id sintetici dedicati.
4. In dry-run non esistono fill: il ciclo completo entry→close→verde si
   certifica solo con stake minimo reale (o paper-mode che simuli il fill
   al touch).
5. Solo dopo (1): ordini reali con stake piccolo (conferma money-critical
   gia' nel pannello).

### 6.7 L'ATLANTE — la pagella dei momenti (metodo + risultati v0, 10/07)

**Cos'e'**: mining offline dell'archivio raw — ogni 10s di in-play, per ogni
linea Under con book valido, si simula l'operazione sniper col modello di
esecuzione certificato (taker al best back, uscita in coda a −1 tick con
PIQ, traded dimezzato, delay 5.12s, sospensione letale) e si registra
features + esito (fill/stop/gol-sospensione/timeout). E' il sostituto delle
opinioni: ogni idea di filtro si legge in tabella PRIMA di diventare codice.

**v0: 28.310 momenti, 12 partite con book OU vivo (su 22 registrate).**

| Cella | n | Fill | t2fill med | Stop | Gol/Susp |
|---|---|---|---|---|---|
| Baseline "spara quando capita" | 28.310 | 20.7% | 113s | 17.1% | 14.7% |
| Solo 3 gate S16 | 439 | 19.6% | 83s | **0.9%** | 15.0% |
| **S16 + linea k≤1.5 (gol+1.5) = LA CELLA** | **76** | **51%** | **67s** | **3%** | **7%** |
| S16 + k=2.5 | 117 | 31.6% | 100s | 0.9% | 20.5% |
| S16 + k=3.5 | 129 | 5.4% | — | — | — |

**Verdetti v0** (vedi anche §11 Registro Ipotesi):
- i 3 gate S16 sono la DIFESA: stop 17.1%→0.9% (20x meno);
- la LINEA domina la resa: (gol+1).5 = 2.5x di fill vs gate generici, con
  fill distribuiti dal 15′ al 97′ → **niente finestre orarie hardcoded**;
- il filtro "decay osservato" e il filtro "traded" NON aggiungono nulla
  sopra la cella (falsificati in v0);
- k=0.5 mostra 100% fill ma su n=12 e con 26% di stop senza gate: VIETATO
  costruirci sopra finche' la miniera non cresce.
- **Conclusione operativa: il bot cablato (3 gate + linea dinamica) E' la
  cella migliore dell'archivio → NON toccare il codice.**

**Come si aggiorna** (ogni nuova infornata di registrazioni):
`python atlas_v0.py all` + `python atlas_report.py` (oggi in scratchpad
`bt_calcio\` — da portare in `Betfair/stream/scalper/tools/` alla prossima
sessione). Ogni refresh: aggiornare la tabella qui sopra e il §11.

---

## 7. HARNESS DI BACKTEST — REGOLE D'ORO (violarle = numeri falsi)

1. Usare `run_scalper.run_scalper(config)` (importa il bot di PRODUZIONE).
   MAI `scalper_lab/bt_lab.py` (copia stantia).
2. Passare SEMPRE `"commission_rate": 0.05` (default = 0!).
3. MAI aggiungere delay a mano: flumine applica `place_latency` (0.120) +
   betDelay REGISTRATO nei raw (0 pre-match, 5s in-play). Delay operativo
   in-play misurato: 5.12–5.8s su 16.614 ordini.
4. `simulation_available_prices=False` (fill solo su volume scambiato,
   dimezzato, con coda PIQ) = maker onesto.
5. In sim spegnere le protezioni solo-live: `exact_exits=False, size_step=0,
   live_min_bet=0, max_txn_hour=0`.
6. Metrica = `aggregate_results` (Σ `order.simulated.profit`). Per mercati OU
   che non settlano nel replay: mark-to-market via `compute_green` al last
   mid (pattern sweep theta). MAI ricalcolare il P&L a mano.
7. Semantica flumine (certificata contro il sorgente 2.13.11): un BACK a
   prezzo ≤ best-available-to-back matcha AL PLACE (taker); un BACK sopra
   resta in coda (maker, PIQ = size visibile). L'ordine LAPSE cade in
   sospensione (gol) e va ripiazzato.
8. Gambe nude: controllare l'esposizione residua PER SELEZIONE sugli ordini
   regolati (|net_win − net_lose| > 0.30 = vera gamba nuda; ≤0.30 =
   micro-residuo accettato by-design).

---

## 8. DOVE SONO I TEST (sessione 10-11/07)

> Lo scratchpad è di sessione: i numeri che contano sono GIÀ in questa bibbia.
> Percorsi (finché vivi): `...\Temp\claude\C--Users-Admin\8e6fa7c0-...\scratchpad\`
- `bt_calcio\` — wrapper fedele + audit (`bt_common.py`), driver (`run_all.py`),
  risultati v2 (`results\`, 74 JSON con audit per-run), v1 pre-fix
  (`results_v1_prefix\`), confronto (`compare_v2.py`), sniper
  (`sniper_strategy.py`, `sweep_sniper.py`, `out_sniper\`).
- `theta_decay\` — misure decay/hazard/HT (`out\a_results.json`,
  `hazard.json`, `ht_decay.json`), sweep theta certificato (`sweep_b.py`,
  `theta_strategy_fixed.py` con FIX semantica maker/taker), audit delay.
- `inventory_calcio\inventory.json` — inventario per-evento (finestre, HT
  osservato da matchStatus, liquidità, gol). Dati raw: `_live_raw\<event>\`.
- **ATLANTE (§6.7): portato nel repo il 10/07** →
  `Betfair/stream/scalper/tools/` (`atlas_v0.py`, `atlas_report.py`,
  `mcm.py` = parser MCM certificato). Uso: `python atlas_v0.py all` poi
  `python atlas_report.py`. I campioni v0 (jsonl) erano nello scratchpad:
  rigenerabili in ~15 min dai raw; i NUMERI sono gia' in §6.7/§11.

## 9. REGISTRO DECISIONI (non ridiscutere senza dati nuovi)

| Data | Decisione | Perché |
|---|---|---|
| 02/07 | In-play maker meccanico NO | −11.26 su 6 match (dossier §9.5) |
| 07-08/07 | `min_size` 300 (non 150) | 150 → rosso, 300 → verde (riconfermato v2: −1.99 vs +1.41) |
| 10/07 | Niente delay extra negli harness | flumine applica già betDelay+latency (audit 2.13.11) |
| 11/07 | Fix contabili in produzione | limbo FLATTENING + locked=0: missione/cap erano ciechi |
| 11/07 | **PRE-MATCH GO** (og1 + ms300) | 5/6 eventi col tick, zero rossi, mediana 16′ |
| 11/07 | **HT NO-GO** | theta assente all'intervallo (misurato), −2.54/13 eventi |
| 11/07 | Sniper in-play: promosso a candidato | +0.99/14 ev, worst −0.49, gate = +4.4€ vs no-gate; MA out-of-sample obbligatorio |
| 11/07 | Maker resting in-play vietato | fill nel gap del gol = lotteria (+10.82 outlier) |
| 10/07 | Sniper CABLATO (bot+sessione+UI, dry-run default) | richiesta demo; 10 test dedicati; soldi veri solo dopo demo+out-of-sample |
| 10/07 | Linea sniper DINAMICA (gol+1).5 + OU05..85 a stream | demo live CSL: al 4-1 la OU15 hardcoded era morta; fix validato in live (OU65 in 5s) |
| 10/07 | **DEMO LIVE OK** (CSL 4-1, dry-run) | 3 dry-fire perfetti @1.28/1.26/1.24 (tutti sarebbero stati verdi), chiusura pulita, 0 ordini reali |
| 10/07 | Regola contesto "blowout=GO" BOCCIATA | la partita della demo (4-1→4-3, 7 gol) l'ha falsificata lo stesso giorno: mai regole calcistiche hardcoded |
| 10/07 | **ATLANTE v0** (28.310 momenti, 12 partite) | conferma con misura: bot cablato = cella migliore; filtri decay/traded falsificati; NON toccare il codice |
| 10/07 | Sniper: esecuzione .it completa (exact_exits/submin come il maker) | prerequisito soldi veri: un'uscita rifiutata = gamba nuda; green spalmato esatto sui 2 esiti; 18 test, suite 782 |
| 10/07 | Ordini sul ladder stile tool-pro: GIA' esistente (reconcile A2), solo config | `.env`: LIVE_ORDER_MODE=LIVE + LIVE_RECONCILE_POLL_SEC=5 → ordini del BOT sul ladder come 'account' (entro ~5-7s), manuali dal ladder istantanei; evidenziati finche' non matchano |

## 10. PROSSIMI PASSI — IL CICLO OPERATIVO (in ordine, nessun salto)

1. **Registrare** ogni giorno tutte le partite tradabili (il runner c'e'
   gia'): ogni partita ingrossa l'Atlante gratis.
2. **Paper pre-match** con og1+ms300 su 20-30 partite habitat (target ~+0.15
   ±0.10/evento, zero gambe nude) — criterio GO/NO-GO per lo stake reale.
3. **Out-of-sample sniper** sulle nuove registrazioni (config CONGELATA =
   quella cablata) + refresh Atlante (§6.7) a ogni infornata.
4. Se (3) regge ≥ meta' del backtest → ordini reali sniper a stake piccolo
   (conferma money-critical gia' nel pannello).
5. Live con monitoraggio `cycle_log`/naked/`sniper_*` (ledger = realta') e
   pagella per cella: le celle che perdono si spengono, mai a sentimento.

## 11. REGISTRO IPOTESI (il cuore del monitoraggio — aggiornare SEMPRE qui)

> Ogni idea passa di qui con uno stato. **Non si valida due volte, non si
> ridiscute il falsificato senza dati nuovi, non si implementa il
> "da validare".** Stati: ✅ VALIDATA · ❌ FALSIFICATA · 🔬 DA VALIDARE.

| Ipotesi | Stato | Evidenza | Data |
|---|---|---|---|
| Maker pre-match con min_size 300 + missione og1 | ✅ VALIDATA | backtest v2: 5/6 eventi col tick, zero rossi (§4) | 11/07 |
| Fix contabili (tolleranza 0.02, residuo, stop parziali) | ✅ VALIDATA | v1→v2: ledger=settlement, missione attiva (§2) | 11/07 |
| 3 gate sniper (cadenza+coda+spread) | ✅ VALIDATA | sweep 14 ev (+0.99 vs −3.45 no-gate) + demo live + Atlante (stop 0.9%) | 10/07 |
| Linea Under DINAMICA (gol+1).5 | ✅ VALIDATA | demo live (OU65 in 5s) + Atlante: fill 51% in 67s, la cella migliore (§6.7) | 10/07 |
| Theta all'intervallo HT | ❌ FALSIFICATA | l'Under all'HT non decade, sale (+0.5..+4 tick); BT −2.54/13 ev (§5) | 11/07 |
| Maker resting in-play | ❌ FALSIFICATA | fill nel gap del gol = lotteria (+10.82 outlier) (§6.1) | 11/07 |
| Regola contesto hardcoded (blowout=GO, warm-up 15′) | ❌ FALSIFICATA | demo: 4-1→4-3 lo stesso giorno; primi 15′ = hazard MINIMO (5/66 gol) | 10/07 |
| Filtro "decay osservato ≤−1" come permesso | ❌ FALSIFICATA (v0) | Atlante: 18.6% fill vs 28.6% del suo contrario (n piccoli: rivalutare solo con miniera 5x) | 10/07 |
| Filtro "traded ≥100€/min" sopra la cella | ❌ FALSIFICATA (v0) | Atlante: 52% vs 51%, gol/susp peggiore | 10/07 |
| Linea k=0.5 (gol+0.5) | 🔬 DA VALIDARE | Atlante: 100% fill ma n=12; senza gate 26% stop. Servono ≥100 campioni | 10/07 |
| Fuoco nelle interruzioni di gioco (mercato OPEN) | 🔬 DA VALIDARE | logica forte (decay con P(gol)=0) ma serve: latenza feed misurata + celle Atlante dedicate | 10/07 |
| Tripwire pre-gol (firma del book prima dei gol) | 🔬 DA VALIDARE | costruire `pregoal_atlas` sui 66+ gol registrati; falso allarme 1 tick vs salvataggio 10-30 | 10/07 |
| Profondita' dietro il best (cuscino/coda) come gate | 🔬 DA VALIDARE | aggiungere le feature all'Atlante al prossimo refresh | 10/07 |
| Clock di gioco da live_now.minute (non marketTime) | 🔬 DA VALIDARE | KO reale ritardato +40′ in demo; fix piccolo, serve test | 10/07 |
| Stats sniper nel control row | 🔬 DA VALIDARE | in demo risultavano 0 (tabelle contaminate da test E2E terzi): rifare demo pulita | 10/07 |
| Uscita a scadenza dinamica (fill-or-kill sul ritmo coda) | 🔬 DA VALIDARE | riduce il time-in-market: misurabile dall'Atlante (t2fill vs previsione) | 10/07 |
| Linea prudente (gol+2).5 | ❌ SCONSIGLIATA | Atlante: fill 31.6% e gol/susp 20.5% (peggio di k≤1.5 su entrambi) | 10/07 |
| **Join queue-aware del maker** (entrare in coda SOLO quando la fila davanti si assottiglia — gate coda <35% stile sniper, o stima t2fill < orizzonte requote da PIQ+tasso di consumo) | 🔬 DA VALIDARE (idea #1 dalla live 10/07) | Live Spagna: su book elite il 100% dei cicli chiude a 0 (scratch-par) perché la coda davanti ai nostri 25€ non si consuma mai prima dello shift. Misurabile dai raw di stasera (PIQ vs consumo). | 10/07 |
| Filtro habitat "coda che stampa" (non solo size ≥300 ai best, ma RAPPORTO consumo/coda: code profonde senza consumo = habitat sterile elite) | 🔬 DA VALIDARE (live 10/07) | I verdi in backtest venivano da book che stampano (16-27′ al 1° verde); l'elite passa i gate attuali ma non riempie mai. Il gate flusso≥10€/90s è troppo blando rispetto a code da migliaia di €. | 10/07 |
| Scala orizzontale: 3-5 partite habitat a sera in parallelo (il reddito = ripetizione del tick, non target più grandi) | 🔬 DA VALIDARE (operativo) | La sessione live conferma la sicurezza della macchina (0€ persi su 7 cicli); il collo di bottiglia è il rendimento per-partita su habitat sbagliato. | 10/07 |
| Attrito minimi .it in live: 40 `min_bet_skip` + 8 `submin_step` in 50 eventi di log | 🔬 DA ANALIZZARE (journal di stasera) | Path solo-live mai osservato in sim (exact_exits spento nei backtest): capire se gli skip costano opportunità o sono solo rumore della gestione submin. | 10/07 |
| **Sniper MULTI-COLPO** (osservazione live 10/07: "innumerevoli occasioni"): dopo il verde, riarmare con gli stessi 3 gate + cap colpi/evento e cooldown, invece di "primo verde → chiuso" | 🔬 MISURATO v0 (n=1), CABLATO SPENTO (`sniper_max_shots`/`sniper_cooldown_s`) | Conteggio 11/07: sulla SOLA linea dinamica il riarmo vale **+0.17 vs +0.10** (poco: tick da 3 cent a quote 1.3-1.6). Il reddito vero è il multi-LINEA (riga sotto): il multi-colpo è il suo complemento, non il prodotto da solo. | 11/07 |
| **Pre-posizionamento anti-betDelay**: invece di sparare da taker DOPO la rottura del livello (pagando 5.12s di delay in cui il mondo si muove), appoggiare l'ordine al livello sotto QUANDO la coda inizia ad assottigliarsi, TTL breve, cancel se l'innesco rientra | 🔬 DA VALIDARE (Atlante: durata mediana delle finestre di innesco vs betDelay; quota di trigger "mangiati" dal delay) | Se le finestre di innesco durano <5s, il betDelay in-play uccide il taker per costruzione: l'unico modo di essere "veloci" su Betfair è essere GIÀ sul book. Rischio = resting breve (gol), da prezzare. | 10/07 |
| **Sniper multi-LINEA**: sorvegliare in parallelo (gol+1).5 E (gol+2).5 E il pareggio (decay −1.5/−1.3/−0.5 t/min) — più superficie di trigger per partita invece di una sola linea | 🔬 DA VALIDARE (Atlante per-linea già pronto: la cella k=2.5 era peggio come singola, ma come SECONDA canna con cap globale va rimisurata) | Live 10/07: per 20+ minuti la OU15 non ha mai allineato i 3 gate mentre altre linee non erano nemmeno guardate. **In più fixa la cecità post-gol (riga sotto): con lo storico multi-linea sempre vivo, al cambio linea i gate sono già caldi.** | 10/07 |
| **Cooldown post-gol sui gate sniper** (dal primo colpo reale, 43.5′): il fire è partito 2′ dopo il pareggio 1-1 — regime "2 tick-down" tecnicamente vero ma dentro la TURBOLENZA post-gol, non nel decay ordinato → stop in 16s (−0.09€). Distinguere "decay che lavora" da "riassestamento post-gol" (cooldown fisso post-gol, o gate di volatilità: range ultimi 60s ≤ X tick) | ✅ CABLATO 11/07 come **risk manager evento (F5)**: sospensione in-play → stop ingressi di TUTTE le strategie per `risk_cooldown_s` (default 120s) + cap perdita GLOBALE evento (`event_global_cap`, default 2€) | Conteggio 11/07 pro-cooldown: l'unico stop2 del multi-colpo era il trigger post-gol-2 in turbolenza (range60=7 tick) → col semaforo si evitava SENZA perdere fill. Taratura fine (cella "minuti dal gol") resta da Atlante. | 11/07 |
| **CECITÀ POST-GOL del regime** (difetto meccanico scoperto live 10/07, gol 30′): al cambio linea (`set_line` OU15→OU25 in 3s ✓) lo storico tick del gate di regime riparte da ZERO → lo sniper è cieco per ~4 min ESATTAMENTE nella finestra post-gol. Fix: tracking tick continuo su tutte le linee OU (non solo quella attiva) | ✅ FIXATA 11/07 (F4a, commit 041cd0b): check_market_book accetta TUTTI gli OU, `set_line` non azzera più lo storico → al cambio linea i gate sono GIÀ caldi. L'ipotesi "ingresso post-gol" resta 🔬 (Atlante) | Ipotesi operatore da misurare PRIMA (mai regole calcistiche a sentimento, cfr. blowout falsificata): (a) over-reaction del nuovo Under post-gol; (b) hazard "gol dopo gol" reale — calcolare P(gol entro N min da un gol) dai 66+ gol registrati. Se (a)+(b) reggono, la finestra post-gol diventa una cella dedicata dell'Atlante. | 10/07 |
| **Theta-riding nella finestra calda (20-40′ OU15): target 2 tick / trailing invece di 1** | 🔬 DA VALIDARE (era già la miglior famiglia dello sweep: +3.74/13 eventi — mai portata in produzione) | Il decay a 0-0 è il movimento più prevedibile del calcio: 1 tick lo sottosfrutta se la finestra è quella giusta. Esposizione media 4.4 min = rischio gol da prezzare contro il tick extra. | 10/07 |
| **Maker-in-spread in-play a vita breve** (spread 2 tick tipo 4.2/4.4 di stasera: quotare 4.3 con TTL ~30s e cancel aggressivo, mai resting lungo) | ❌ FALSIFICATA (v0, n=1 — non riaprire senza dati NUOVI dall'Atlante) | Conteggio 11/07 sui raw Spagna: 40 finestre, 21 entry fill (52.5%) ma **−1.13€ totali** — 6 stop a spread 2 tick bruciano i 13 tick incassati (0 gol subiti in posizione: rischio non osservato, non assente). | 11/07 |
| **Certificazione replay-vs-live** (idea operatore 10/07): rigirare il backtest fedele (stessa config VALIDATED, commissione 0.05, protezioni live spente) sui raw REGISTRATI DURANTE la sessione live e confrontare ciclo-per-ciclo col ledger reale | ✅ FATTA 11/07 — **modello fill AFFIDABILE** (semmai conservativo sulle uscite) | Replay finestra-live **+0.29€** vs live **+0.24€** (13×0.00 −0.25 +0.49), stessa firma; ZERO fill simulati senza coda consumata; il problema è SOLO l'habitat elite (code 0.5-10k€ vs 25€) → rafforza "join queue-aware"/"habitat che stampa". Attrito .it: nessun ciclo live avrebbe cambiato segno senza minimi (solo verde non spalmato). Report: `_validazione_20260711/replay_vs_live/`. | 11/07 |
| **Sniper MULTI-LINEA a canne parallele** (dinamica + N sopra, stessi gate S16 per-linea) | 🔬 NUMERI v0 FORTISSIMI, CABLATA SPENTA (`sniper_parallel_lines`) — falsificare out-of-sample PRIMA del live | Conteggio 11/07 (Spagna, n=1): **multi-linea +1.28€/partita vs +0.10 mono** (19 colpi, fill 74%, stop 5%); i soldi erano su OU25/OU35/DRAW mentre **OU15 = 0 trigger su 4.582 update** (i 4 gate mai verdi insieme). 11 occasioni ignorate dopo il done del mono (61.6'). Report: `_validazione_20260711/occasioni/`. | 11/07 |
| **REQUISITO GLOBALE: telemetria REAL-TIME stile tool-pro** (ordini bot+manuali sul ladder ≤1s, mai solo polling REST) | 🔬 DA FARE (impegno preso) | design: eventi ordine → coda locale → publisher su thread separato (MAI scritture bloccanti nel loop di trading) → specchio/canale locale. Interim 10/07: reconcile a 5s (`LIVE_RECONCILE_POLL_SEC=5`). Vale per TUTTI i componenti (scalper, sniper, tennis, manuale) | 10/07 |

## 11-bis. IL MOSTRO — blueprint per la review massiva (definito live 10/07)

> Visione operatore (dal vivo, 1-1 al 41′): "stiamo lasciando sul piatto una
> marea di soldi — al 1-1 pre-HT un tick è immensamente probabile su QUALSIASI
> mercato idoneo. Rendere il bot un mostro." Il progetto, in 4 pezzi:

1. **Da bot mono-strategia a MOTORE DI OPPORTUNITÀ per-evento.** Un solo
   processo per partita che valuta TUTTI i mercati liquidi (MO per selezione,
   tutte le linee OU, DC) a ogni tick, e un MENU di micro-strategie con gate
   propri: sniper-taker (validato), pre-posizionamento anti-betDelay,
   mid-spread TTL breve, theta-riding 2 tick. Il motore spara dove la CELLA
   corrente ha EV misurato > 0. La strategia non è più il prodotto: il
   prodotto è la pagella delle celle.
2. **Lo STATO-PARTITA come contesto.** Le celle dell'Atlante v1 diventano
   (punteggio × fascia minuto × mercato × spread × stato coda): "1-1 min
   40-45" è una cella con la sua fisica (misurabile: stasera l'abbiamo
   registrata dal vivo). La claim dell'operatore — "al 1-1 pre-HT il tick è
   quasi certo su almeno un mercato" — è un numero da estrarre, non
   un'opinione: P(≥1 fill-1-tick | stato, menu strategie) dai raw.
3. **RISK MANAGER evento-centrico (il guinzaglio del mostro).** L'unico
   killer è il gol: UN semaforo unico per evento (hazard modello + tripwire
   book §11) che sospende TUTTE le micro-strategie nei momenti caldi e riarma
   dopo. È il pezzo che permette multi-colpo × multi-mercato senza
   moltiplicare il rischio: N strategie, UN rischio.
4. **La pagella comanda.** Ogni cella che perde si spegne da sola (§10.5);
   ogni cella nuova entra SOLO dopo l'Atlante. Il mostro cresce per
   accumulo di celle validate, mai per entusiasmo.

Ordine di costruzione proposto per domani: (a) conteggio ufficiale occasioni
di stasera per cella/strategia → (b) fix esecuzione (stake pre-dimensionati,
flatten garantito, telemetria onesta) → (c) replay-vs-live → (d) prime 2
celle nuove del menu (multi-colpo sniper + multi-linea con storico caldo) →
(e) risk manager unico → (f) il resto a pagella.

## 12. SESSIONE 10/07 SERA — PRIMA VOLTA SOLDI VERI (Spagna, KO 21:00)

Checklist (attivazione dalle 18:00):
1. **Riavviare il .exe** (deve rileggere il .env: `LIVE_ORDER_MODE=LIVE`,
   `LIVE_RECONCILE_POLL_SEC=5` — ordini del bot visibili sul ladder ≤5-7s).
2. Pannello Scalper sulla partita → **Maker stake 25 + Missione ON +
   SNIPER ON stake 5** → togliere "Solo ARMATO" → confermare ORDINI REALI.
3. Protezioni gia' attive: maker og1 (primo verde→stop, cap 1.5, flat a
   KO−3′); sniper 1-tick-e-stop (stop 2 tick, timeout 300s, cap 1.0).
   **Perdita massima teorica ≈ 2.5€** + slippage-gol.
4. Aspettative: elite pre-match spesso congelata → maker fuori = gate che
   lavora; in-play book liquido = habitat sniper. Obiettivo della serata:
   CERTIFICARE il funzionamento (fill reali, green spalmato, ledger=realta',
   ordini sul ladder), non il profitto.
5. Post-partita: la registrazione entra nell'Atlante; aggiornare §6.7/§11 e
   il registro decisioni con l'esito (fill/green/stop, stats `sniper_*`,
   naked=0 atteso).

### 12.1 OSSERVAZIONI LIVE 10/07 (in corso — armato 19:36, soldi veri)

**Pre-match, fotografia alle 20:05** (KO 21:00): 7 cicli chiusi **TUTTI a
0.00€** (scratch a pari), 9 scratch difensivi, 34 ordini reali, **0 gambe
nude, 0€ persi, 0 tick veri catturati**. Il bot APRE nei punti giusti
(conferma visiva dell'operatore sul ladder) ma su book elite la coda davanti
ai nostri 25€ non si consuma mai prima dello shift di prezzo → scratch
seriale. DIFESA certificata al 100%; ATTACCO sterile su questo habitat.

**Scoperte di stasera (nessun bug di soldi):**
1. `locked: 0.0` sui cicli è CORRETTO (nw=nl=0, chiusura a pari): nessun
   problema contabile in live. Però l'esito nel log/stats dice "scalp" anche
   per gli scratch-par → **etichetta bugiarda**: `scalps` conta roundtrip
   completati, non tick catturati. Fix telemetria domani (scalp = locked>0).
2. La missione og1 correttamente NON scatta (nessun verde vero): su habitat
   sterile il bot cicla fino a KO−7′ — comportamento previsto, costo zero.
3. Macchina minimi .it molto attiva (40 `min_bet_skip`/50 eventi log): prima
   osservazione reale di questo path (in sim è spento) — da analizzare.
3c. **BUG REALE (il migliore scovato stasera, 20:45): residuo in terra di
   nessuno.** Il primo stop della serata ha lasciato residui da equalizzare di
   BACK 0.31€ e 0.14€ — sopra la soglia di accettazione micro (0.25-0.30€) o
   comunque non accettati, ma SOTTO il minimo .it (BACK 2€) → `min_bet_skip`
   in loop (12+ retry in 6s), ciclo MAI contabilizzato (stops=1 ma
   pnl_locked fermo), stats bugiarde finché il force-flat non interviene.
   Fix domani: se la size di equalizzazione < minimo exchange E non
   park-trim-abile → accettare SUBITO come micro-residuo (allargare il floor
   al caso "sotto-minimo non eseguibile") e contabilizzare il ciclo.
   **Conferma live 20:57 (richiesta operatore, PRIORITÀ #1 domani)**: ciclo
   chiuso col verde NON spalmato (+0.49 Under / 0.00 Over invece di
   ~+0.24/+0.24) — la gamba di greening sotto-minimo è stata skippata.
   Il maker deve avere la STESSA esecuzione .it dello sniper (§6.4:
   exact_exits + park-trim-replace via `trading/submin.py`) anche
   sull'equalizzazione dei cicli, non solo sulle uscite: quando si abbinano
   entrambi i lati, profitto SEMPRE spalmato al centesimo sui due esiti.
   **DIRETTIVA DI DESIGN (operatore, 10/07 sera): il greening si risolve
   NEGLI STAKE INIZIALI, non con una terza gamba correttiva.** Quando si
   abbina il BACK, il LAY di uscita deve essere GIÀ dimensionato per spalmare
   il profitto uniformemente: `lay_size = back_size × back_price / lay_price`
   (es. BACK 25@2.22 → LAY 25.23@2.20 = verde ~+0.23 su entrambi gli esiti).
   Due gambe totali, mai size sotto-minimo, contabilità `locked` esatta,
   missione og1 che vede il verde. Da gestire nel fix: fill PARZIALI della
   entry (uscita ridimensionata dinamicamente sul matched reale), step size
   .it 0.50 (il resto di centesimi va in park-trim o accettato come micro),
   scratch invariato (uscita a pari, stessa size). Idem speculare LAY→BACK.
   **PROVA DEFINITIVA + DIRETTIVA FLATTEN (20:58, post KO−3′)**: il force-flat
   è rimasto in skip-loop su TRE residui sotto-minimo (BACK 0.31 sel Spagna,
   BACK 0.14 sel Draw, LAY 0.22 sull'Under 2.5 = la gamba di greening del
   +0.49) → micro-posizioni ancora vive DOPO la deadline, `flattens=0`,
   promessa "mai posizioni aperte al KO" violata alla lettera (esposizione:
   centesimi). **Direttiva operatore: a KO−3′ il flatten deve equalizzare
   TUTTO, qualunque sia l'esito** — (a) con gli stake pre-dimensionati i
   residui sotto-minimo non nascono proprio; (b) se un residuo esiste
   comunque: park-trim-replace, e se nemmeno quello è possibile →
   ACCETTARLO e contabilizzarlo SUBITO (mai loop di retry infinito: il
   flatten deve TERMINARE, sempre, con ledger chiuso).
3b. **Reconcile rumoroso col bot attivo**: gli ordini dello SCALPER vengono
   etichettati "ordine ESTERNO (dal sito?)" dal reconcile del runner (che non
   li ha piazzati lui), e i cancel rapidi del maker (requote/scratch) lasciano
   righe specchio "EXECUTABLE ASSENTE da 2 cicli" → pioggia di WARN in-app
   (~1 ogni 30-60s). Nessun rischio soldi, ma il feed alert diventa inutile
   proprio quando serve. Miglioria: il reconcile deve riconoscere gli ordini
   delle sessioni bot (per market/selection/strategia) e marcare i cancel.
4. Bug UI trovati e fixati stasera (2× TDZ `mode` in `SeguiLive.tsx` →
   pagina bianca al click partita; tsc/vitest NON li rilevano — riprodotti
   con Playwright headless). ⚠️ Fix nel working tree, DA COMMITTARE.

**Idee → §11 Registro Ipotesi** (join queue-aware, filtro habitat consumo/
coda, scala orizzontale, attrito minimi): da sviluppare DOMANI sui raw di
stasera. Stasera NESSUNA modifica (decisione operatore).

**🔴🔴 BUG CRITICO #1 DELLA SERATA — SUBMIN CHE SI ABBINA INTERO (scoperto
22:35 dallo specchio ordini, segnalato dall'operatore dall'esposizione):**
il park-trim-replace del residuo sotto-minimo ha piazzato l'ordine-parcheggio
da 2€ che si è ABBINATO PER INTERO prima del trim — QUATTRO volte di fila
(21:43:57, 21:44:29, 21:45:00, 21:46:09, tutte LAY ~2.34-2.46 su OU35) —
mentre il log interno diceva "trimmed/done ✓". Ogni iterazione creava un
NUOVO squilibrio → nuovo submin → nuovo 2€ abbinato: **loop
auto-amplificante**. Risultato: ledger interno "+0.03 flat ✓" contro conto
reale SHORT Under ~10€ (−10.32/+7.84). In più: l'uscita originale LAY 5@2.24
mai cancellata, rimasta VIVA sul book per 40+ min; stop exit da 4.5 invece
di 5. **Ledger ≠ realtà: la certificazione è FALLITA su questa macchina**
(ed è servita esattamente a scoprirlo prima di alzare gli stake).
FIX OBBLIGATORIO PRIMA DI QUALSIASI ALTRO LIVE: (a) verificare il matched
REALE dell'ordine park DOPO ogni step (mai fidarsi del "cancel ok"); (b) se
il park si abbina oltre il residuo target → compensazione IMMEDIATA lato
opposto + stop del loop; (c) cancel confermato dell'exit precedente prima
di piazzare quello nuovo; (d) riconciliazione posizione bot↔conto (per
selezione) nel heartbeat: divergenza > 0.5€ → alert CRITICAL + freeze.
Con gli stake pre-dimensionati (direttiva operatore) il submin quasi
sparisce; ma la (d) è irrinunciabile comunque.

**🎯 22:22 — MISSIONE SNIPER COMPIUTA (primo verde con SOLDI VERI):**
fire BACK 5€@1.59 su OU35 (min reale 59, log "81.9" = clock marketTime che
conta l'HT → conferma live §6.6.2, passare a live_now.minute), uscita in
coda consumata in 59s, **green +0.032€ SPALMATO sui due esiti** (formula .it
al centesimo ✓), `mission_done`. Il residuo del 1° stop si è chiuso a ~pari
(+0.035/0.00) → sniper POSITIVO netto. **Ciclo end-to-end certificato:
fire → fill → coda → green → ledger. L'obiettivo della serata è raggiunto.**

**Verdetto operatore in-play (21:25, min 21+ a 0-0): "SIAMO TROPPO LENTI —
in questi minuti avremmo chiuso decine di occasioni."** Il mono-colpo
super-selettivo era giusto per certificare, NON è il prodotto-reddito.
DOMANI: review massiva + soluzione definitiva. Primo deliverable della
review: **il CONTEGGIO UFFICIALE delle occasioni della serata dai raw**
(momenti-cella S16, fill possibili mid-spread, colpi multi-sniper, finestre
per linea OU e per il pareggio) — decidono i numeri, non le impressioni.

---

## 13. PIANO 11/07 — REVIEW MASSIVA (giornata "si finisce il bot")

> Ordine operatore: affrontare OGNI cosa emersa il 10/07 e rendere il bot
> una macchina che GUADAGNA. Metrica unica di successo: **euro incassati per
> partita in paper sui raw registrati** — non eleganza architetturale.
> Gate finale: certificazione paper stasera su partite vere.

### FASE 0 — Messa in sicurezza (subito, ~30′)
- **Commit del working tree** in commit separati e sensati: fix TDZ
  `SeguiLive.tsx` (pagina bianca) + dist ricompilata; fix contabili 11/07;
  cablaggio sniper; tools Atlante. Da ieri sera tutto è NON committato:
  un crash disco oggi = perdere i fix money-critical.
- Igiene ambiente: nessun processo orfano (`Win32_Process` cmdline+parent),
  nessun scalper_service doppio, .env coerente.

### FASE 1 — ESECUZIONE BLINDATA (condizioni §0-bis 1-4: gate per OGNI live)
1. **Stake pre-dimensionati per green simmetrico nel maker** (direttiva
   §12.1): quando si abbina la entry, l'uscita è GIÀ dimensionata
   `exit_size = entry_size × entry_price / exit_price` (verde spalmato al
   centesimo, mai gambe sotto-minimo). Gestire: fill PARZIALI (uscita
   ridimensionata sul matched reale), step .it 0.50 (resto → park-trim o
   micro accettato), scratch INVARIATO (pari, stessa size), speculare
   LAY→BACK. Con questo il submin diventa raro invece che la norma.
2. **Submin blindato** (`trading/submin.py`, vale per sniper E maker):
   (a) matched REALE del park verificato dopo OGNI step — mai fidarsi del
   "cancel ok"; (b) park abbinato oltre il residuo target → compensazione
   IMMEDIATA lato opposto + stop del loop; (c) cancel CONFERMATO dell'exit
   precedente prima di piazzare il nuovo. Test che riproduce ESATTAMENTE
   il caso 21:43 (park 2€ abbinato intero ×4, loop auto-amplificante).
3. **Riconciliazione bot↔conto per selezione a ogni heartbeat**: divergenza
   >0.5€ → alert CRITICAL + FREEZE ordini della sessione. MAI più posizioni
   invisibili: questa è la rete anche per i bug che non conosciamo ancora.
4. **Flatten KO−3′ (e force-flat loss-cap) che TERMINA sempre**: residuo
   sotto-minimo → park-trim-replace; se non possibile → ACCETTATO e
   contabilizzato SUBITO (floor micro allargato al caso "sotto-minimo non
   eseguibile", fix del bug 20:45 "terra di nessuno"). Mai retry-loop
   infinito; a fine flatten il ledger è CHIUSO, sempre.
5. **Telemetria onesta**: `scalps` = solo locked>0 (scratch-par ≠ scalp);
   ciclo con residuo accettato contabilizzato subito (stops/pnl coerenti);
   reconcile che riconosce gli ordini delle sessioni bot e i cancel rapidi
   (basta pioggia di WARN "ordine ESTERNO"/"EXECUTABLE ASSENTE");
   clock partita da `live_now.minute` (non marketTime: ieri "81.9" al 59′).
- Metodo: TDD su ogni fix, suite completa verde a fine fase.

### FASE 2 — DATI: loader parsato + CONTEGGIO UFFICIALE OCCASIONI (parallela a F1)
1. **Loader del book PARSATO** (440MB Spagna, pre-match→97′) → formato
   momenti compatibile Atlante/mcm (il tee nativo era fermo dalle 19:12:
   senza loader l'in-play di ieri non esiste per l'analisi).
2. **Conteggio ufficiale delle occasioni della serata** (primo deliverable
   della review, richiesto dall'operatore): momenti-cella S16 su TUTTE le
   linee OU + pareggio; colpi multi-sniper possibili (con cap+cooldown
   simulati); finestre mid-spread TTL 30s; finestra "minuti dal gol"
   (ipotesi over-reaction post-gol + hazard gol-dopo-gol sui 66+ gol).
   Output: **€ lasciati sul tavolo per strategia/cella** → decide cosa si
   costruisce in F4. Decidono i numeri, non le impressioni.
3. **Recorder blindato**: tee raw nativo riarmato a ogni (ri)avvio del
   runner + heartbeat "recorder vivo" (bytes/min in telemetria) per
   ENTRAMBI i formati; "Segui live" con ack esplicito (riga live_follow
   verificata + toast ok/errore + stato PENDING/STREAMING visibile) —
   mai più partite credute registrate e perse (le 2 irlandesi).

### FASE 3 — REPLAY-VS-LIVE (dopo F1+F2, priorità alta)
- Backtest fedele (config VALIDATED, commissione 0.05, protezioni live
  spente) sui raw della sessione live → confronto CICLO-PER-CICLO col
  ledger reale. Esiti possibili: replay>live → il modello di fill (PIQ
  dimezzato) è ottimista e/o l'attrito live (minimi .it, cancel latency)
  costa → misurarlo PRIMA di fidarsi di qualsiasi backtest futuro;
  replay=live → il problema è solo l'habitat elite.
- Analisi dei 40 `min_bet_skip`/50 eventi: costo reale in opportunità.

### FASE 4 — L'ATTACCO: da 1 colpo a N colpi VERI (solo celle con EV>0 dalla F2)
a. **Multi-linea con storico caldo**: tracking tick CONTINUO su tutte le
   linee OU (non solo l'attiva) → fixa la cecità post-gol (~4′ cieco al
   cambio linea) e dà più superficie di trigger.
b. **Multi-colpo**: dopo il verde, riarmo con gli stessi 3 gate + cap
   colpi/evento + cooldown (dimensionati dai numeri F2).
c. **Gate post-gol**: cooldown fisso o gate di volatilità (range 60s ≤ X
   tick) — distingue decay ordinato da turbolenza (il colpo 43.5′ di ieri).
d. Solo se F2 li promuove (Atlante PRIMA del codice, una cella alla
   volta): mid-spread TTL 30s, theta-riding 2 tick finestra 20-40′,
   pre-posizionamento anti-betDelay.
- Vincolo: la config S16 validata NON si tocca; il multi-X è un layer
  sopra (riarmo/multi-linea), mai una modifica dei gate certificati.

### FASE 5 — RISK MANAGER unico per evento (versione minima oggi)
- UN semaforo per evento: post-gol/interruzioni/turbolenza → sospende
  TUTTE le micro-strategie e riarma dopo; cap perdita GLOBALE per evento
  (non per strategia). È ciò che rende multi-colpo × multi-linea sicuro:
  N strategie, UN rischio.

### FASE 6 — CERTIFICAZIONE PAPER + GO/NO-GO
- Replay paper della macchina nuova (F1+F4) sui raw (Spagna + archivio):
  euro/partita, ledger=settlement al centesimo, flatten termina sempre,
  0 posizioni invisibili simulate.
- **Stasera: sessione PAPER su partite vere** (registrandole! il runner
  ingrossa l'Atlante gratis), telemetria a video. GO al prossimo live con
  soldi SOLO se: ledger=realtà su tutta la sessione, flatten/submin senza
  anomalie, colpi catturati coerenti col conteggio F2.

### Linea di taglio e note
- **Irrinunciabili oggi**: F0, F1, F2, F3. **Obiettivo del giorno**: +F4a/b
  +F5. F4c/d a pagella se il tempo regge.
- **Maker pre-match**: resta og1+ms300 (validato §4) ma ieri su habitat
  elite = 0€: la selezione partite ("coda che stampa", join queue-aware)
  si misura in F2/F3 — NIENTE modifiche ai gate maker senza quei numeri.
- Telemetria real-time ≤1s stile tool-pro (impegno §11): resta requisito
  globale, non blocca il GO paper di stasera (interim: reconcile 5s).

### ESITO 11/07 (pomeriggio) — F0-F5 COMPLETATE, resta la F6

**Fatto e pushato** (807 pytest + 656 vitest verdi, dist ricompilata):
- `1ab3f43` fix TDZ pagina bianca (committato il fix di ieri sera)
- `802040f` **esecuzione blindata**: submin a verifica OSSERVATA (mai più
  "trimmed ✓" di fiducia; replace VIETATO con residuo oltre target; timeout
  → full cancel + abort; ABORT con matched → flatten certificato + CRITICAL),
  stake pre-dimensionati (close verde-simmetrica al fill, coda conservata:
  riduzione = cancel parziale, aumento = micro top-up exact), flatten che
  TERMINA sempre (ultima-spiaggia contabilizzata), rete ledger↔ordini su
  OGNI book per maker E sniper (auto-heal + CRITICAL >0.5€, 3 divergenze →
  freeze force-flat, alert in live_alerts), reconcile che riconosce gli
  ordini bot (stop pioggia WARN), scalp=tick vero, clock live_now.minute.
- `41bb60c` **recorder blindato**: tee raw con self-heal (write KO → riapre,
  prima moriva in silenzio) + heartbeat bytes/ultimo-write + alert se fermo
  >120s con stream vivo; "Segui live" con ACK verificato (badge REC/in
  coda/⚠ non confermata + warning a 4 min senza presa in carico).
- `041cd0b` **attacco cablato (spento)**: multi-linea a storico caldo (F4a),
  multi-colpo cap+cooldown (F4b), risk manager evento (F5: semaforo
  sospensione→halt ingressi 120s + cap globale 2€).
- **.env portato a PAPER** (era rimasto LIVE): torna LIVE solo al GO.

**Verdetti analisi (report in `_validazione_20260711/`)**:
- Replay-vs-live: modello fill AFFIDABILE, problema = habitat elite (§11).
- Conteggio occasioni: mono +0.10 / multi-colpo +0.17 / **multi-linea +1.28
  €/partita** (n=1) / mid-spread ❌ −1.13. OU15 = 0 trigger tutta la partita.

### F6 — CHECKLIST PAPER STASERA (unico gate rimasto per il live)

1. Riavviare l'exe (rilegge `.env`: LIVE_ORDER_MODE=**LIVE** — ripristinato
   su ordine operatore 11/07 pomeriggio; il pannello parte comunque in
   "Solo ARMATO" + conferma ORDINI REALI). Cap/cooldown caccia = PER LINEA
   (fix 9e8b49b, fedele alla cella misurata).
2. Scegliere 1-3 partite con book che STAMPA (no elite congelata — lezione
   F3) + attivare "Segui live" e VERIFICARE il badge **● REC** (ack nuovo).
3. Pannello Scalper: Maker stake 25 + Missione ON; **SNIPER ON stake 5 +
   toggle "🔫 CACCIA MULTI-LINEA"** (commit d809496: un click arma
   parallel_lines=2, max_shots=10, cooldown 120s, profit_target=0;
   semaforo post-gol 120s e cap globale 2€ sono sempre attivi di default).
4. GO al prossimo live SOLO se su TUTTA la sessione paper: ledger=realtà
   (zero `ledger_divergence`), flatten sempre terminato, zero submin-abort
   con matched, colpi/fill coerenti col conteggio F2.2, alert puliti.
5. Post-sessione: raw nell'Atlante (refresh §6.7), pagella per cella,
   aggiornare §11 — multi-linea si valida (o si falsifica) LÌ.
