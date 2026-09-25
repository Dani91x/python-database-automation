# Validazione fuori campione dell'Atlante Hazard (25/09/2026)

Delegato del coordinatore, worktree `agent-a6eb18085de040ec8`, base `372158e`. Nessun commit, nessuna
scrittura sul DB, nessuna modifica a Safe/Omega/Mike o alle soglie. Referto scritto per fasi
(se si interrompe, le sezioni presenti sono complete).

## 0. Sintesi (numeri del test 2025 sull'insieme pulito, IC 95% per partita; dettaglio in §4)
- **Il v3 di oggi (A0) è tarato male proprio dove si decidono i lay dell'Under e i green-up.**
  - Nel recupero del 2T dice 14% di gol nei prossimi 3', sempre uguale da 90+0 a 90+8. Il vero è 10,7%
    a 90+0 e scende a 3,0% oltre il 90+8 (ECE 0,063).
  - Alla cella 40-45 dice 11,2% (vero 8,0%). Il gonfiore viene dai gol del recupero schiacciati sul 45'.
- **A\*** (verità vera + recupero modellato per lega + stagioni pesate + forza pre-partita) batte A0:
  - log-loss 3' −0,00156 [−0,00224, −0,00082] su tutto, −0,0212 [−0,0281, −0,0135] nel recupero 2T
    (−7,3%), dove l'ECE scende da 0,063 a 0,008;
  - su tutto il 2025, stati lontani dalla fine dei tempi: −0,00067 [−0,00084, −0,00049].
  - È implementato in `Betfair/stream/scalper/atlante_v4.py` (NON collegato). Il modulo dà gli stessi
    numeri del candidato validato: differenza massima 2,6·10⁻⁶.
- **B1** (LightGBM sulla stessa verità) batte anche A\*: −0,00107 [−0,00160, −0,00056] sul 3', e nel
  75-89' −0,00157 [−0,00280, −0,00030]. È la strada di massimo livello, ma pesa di più (§7).
- **Non vincono**: differenza reti (A3), moltiplicatore rossi (A4), K dal metodo dei momenti (A6).
- **Il livello squadre del v3 PEGGIORA** le previsioni: +0,00120 [+0,00066, +0,00173]. Oggi scatta
  quando i nomi Betfair coincidono.
- **I λ pre-partita di `fixture_predictions`** (quelli di Safe) predicono i gol peggio di un
  Poisson-Elo di 30 righe: log-verosimiglianza −1,817 contro −1,774 a partita, correlazione 0,58. Con
  quei λ il guadagno della forza (A5) sparisce.
- **Recupero (decisione dell'utente: stima per lega).**
  - Il prezzo del dato mancante (recupero annunciato non nel feed) è 0,0067 di log-loss per stato di
    recupero (−2,5%): A\* 0,26912 contro l'oracolo 0,26246.
  - La distribuzione per lega batte la sola media per lega di 0,0013.
- **Difetto dei dati da portare all'utente**: stagione 2025 europea senza minuti di recupero sui gol
  (§1, reperto 6).

## 1. Dati: letture del DB (sola lettura, una volta, in cache)

Cache: `AUDIT_2026-09-25/validazione_hazard/cache/*.json.gz` (in `.gitignore`), scritta da
`python -m Betfair.stream.scalper.validazione_hazard.raccogli --env <.env principale>`. Il `.env` è
letto a mano, mai con `load_dotenv`. Lettore: il `LettoreDB` del generatore (solo GET).

| passo | richieste | righe | secondi |
|---|---|---|---|
| sonde (colonne, filtri, copertura, conteggi leghe piccole, minute_extra 2025) | 17 | ~9.200 | ~5 |
| coverage (15 leghe) | 1 | 223 | 0,3 |
| matches (15 leghe × 2016-2025, + `raw_json->fixture->status->extra`, `periods`) | 45 | 44.749 | 32,2 |
| match_events (gol + rossi; per il 2024-25 anche ogni evento con `minute_extra`) | 194 | 132.876 | 66,2 |
| fixture_predictions (λ del motore Poisson, stagioni 2024-25) | 45 | 2.408 | 11,9 |
| supplemento leghe piccole 306, 835 (`--supplemento`) | 14 | 3.459 | 4,9 |
| **totale** | **316** | **~192.900** | **~121** |

Leghe: 12 grandi (40, 71, 140, 39, 135, 62, 61, 78, 88, 94, 144, 179), stagioni 2016-2025, più le
piccole 833, 834, 835, 306 (storico < 300 partite prima del 2025). La 395 era prevista ma la regola
di copertura della produzione (eventi sul ≥60% delle partite con gol) la esclude: eventi sull'1,7%.
Partite nel banco dopo le regole di produzione (FT, gol eventi = punteggio, copertura): **42.882**;
stati a rischio (partite-minuto): **3.912.771**.

### Reperti sui dati (misurati)
1. **Il DB ha la durata del recupero del 2T** in `matches.raw_json.fixture.status.extra`, ma solo dal
   2024: 2024 3.357/4.566 partite, 2025 4.098/4.394, prima 0. Media 6,33' (2024) e 6,36' (2025).
   Controllo di coerenza sulle stagioni con gli eventi in recupero: l'ultimo evento del recupero
   supera `extra` in 56 partite su ~7.450 (+1..+4'). Quindi `extra` è il recupero giocato (o quasi),
   e il banco usa `d2 = max(extra, ultimo evento)`. Un valore 86 è stato scartato (soglia 30).
2. **Il recupero del 1T non è nel DB.** `periods.first/second` sono nominali (differenza sempre
   esattamente 60'). Il banco misura il recupero del 1T solo dove un evento non-gol successivo prova
   che la partita era viva (campione parziale, dichiarato).
3. **λ pre-partita del motore Poisson** (`fixture_predictions.db_json_analisi.inputs`, la fonte che
   Safe usa in live) esistono solo per il 2025: 2.371 partite del campione (generate da 02/2026 in
   poi). Il 2024 ne ha zero. Quindi un modello non può *imparare* da quei λ. B1/A5 usano un
   *proxy* costruito senza guardare il futuro (§3), e sul 2025 si sostituiscono i λ veri (B2).
4. `Second Yellow card` non compare mai: API-Football registra il doppio giallo come `Red Card`
   (8.660 rossi nel campione, 0,20 a partita).
6. **DIFETTO DEI DATI (grave, scoperto dal banco): nella stagione 2025 delle 12 leghe europee i gol del
   recupero sono registrati SENZA `minute_extra`.** Quota dei gol al 45'/90' che ha l'extra:
   - 2016-2024: 0,73-0,96 per lega-stagione;
   - leghe piccole 2025 (306, 833-835, a calendario solare): 0,76-0,83;
   - 12 grandi leghe 2025: 0,00-0,28. Per mese: ago 2025 0,14, set 2025 - gen 2026 0,00-0,02, feb 0,26,
     mar-apr 0,66-0,70, mag 2026 0,34.

   Sonda sul DB (`sonde/sonda6_minute_extra.py`, 2 GET): 90 gol di fine tempo della Premier 2025, tutti con
   `minute_extra` NULL **e anche `raw_json.time.extra` NULL**. Quindi è l'API al momento
   dell'ingestione (righe create 12/2025-01/2026), e il dato non si recupera dal DB. Gli eventi non-gol
   delle stesse partite hanno invece l'extra: il 60% delle partite ha almeno un evento in recupero.

   Effetti:
   - **sull'atlante v3 di oggi, nessuno**: clampa tutto a 45/90;
   - **sulla verità del test 2025**: i gol del recupero finiscono al 90' regolare. La cella 85-90
     osservata sale a 0,155 (0,088-0,103 nelle stagioni prima) e il recupero si svuota. La prima corsa del
     test ne è uscita falsata;
   - **su qualunque atlante futuro che usi il recupero**: con la stagione 2025 in addestramento
     imparerebbe «niente gol nel recupero, molti al 90'».

   Contromisure: il banco valuta il test su (a) blocchi lega-mese che registrano il recupero (≥60% dei gol
   di fine tempo con extra, `dati.recupero_registrato`), come insieme **primario**; (b) tutto il 2025 ma
   solo sugli stati le cui finestre non toccano la fine del tempo (t ≤ 41). Il modulo v4 ha la regola
   `stagione_recupero_affidabile`: una stagione sotto soglia conta solo gli stati t ≤ 41.
   **Da portare all'utente**: la fonte (API-Football o `daily_yesterday_backfill`) per i gol 2025-26, e se
   rileggere quegli eventi.
5. Tasso grezzo (stati regolari, 2016-2024): P(gol entro 3') = 0,0807-0,0831 per stagione.
   **2024, l'ultima stagione pulita e completa:**
   - 85-89': 0,0889 (21.980 stati);
   - recupero del 2T: 0,0773 (21.585 stati), e scende col minuto di recupero perché la partita finisce;
   - recupero del 1T (vivo provato): 0,0349.

   L'atlante di oggi, al 90+j, usa la sua cella 85-90, gonfiata dal clamp (≈0,14). Un primo conteggio
   su 2024+2025 dava 0,046 per il recupero 2T, ma era falsato dal reperto 6.

### Parità A0 ↔ v3 (il candidato A0 è l'atlante di produzione)
A0 non è una riscrittura: `produzione.py` chiama `genera_atlante.bootstrap` + `assembla` veri con un
lettore finto che serve la cache con gli stessi parametri PostgREST. Contro il v3 committato
(`hazard_atlas_v3.json`), sulle 11 leghe con le stesse stagioni (la 71 nel v3 ha anche il 2026):
**n_fixtures e n_goals identici; 792 celle su 792 con `n` identico; side_rate identici; successi s3/s2
ricostruiti dal v3 entro l'arrotondamento a 5 decimali (errore massimo 0,074 conteggi).**
Sonda: `AUDIT_2026-09-25/validazione_hazard/sonde/prova_parita.py`. Quindi la cache coincide con il DB che
ha prodotto il v3, e A0 coincide con la produzione.

## 2. Il banco: verità, stati, candidati

### La verità misurata (quello che serve al trader)
Stato = «t minuti giocati nel tempo h». y_k = 1 se nel **tempo h** c'è almeno un gol nei prossimi k minuti
di gioco (posizioni t < p ≤ t+k). Il recupero sta nel recupero: 45+2 è la posizione 47 del 1T, 90+3 la
posizione 48 del 2T. Una finestra al 44' comprende 45', 45+1, 45+2. Il 46' no, perché è nell'altro tempo.
Il v3 invece clampa tutto a 45/90: al suo 87' la finestra 3' contiene tutti i gol del recupero.
Stati a rischio (`stati.py`):
- **regolari**: 0..89 sempre;
- **recupero 2T**: 90+j per j < d2, solo dove d2 è noto (2024+);
- **recupero 1T**: 45+j solo dove un evento non-gol successivo prova che la partita era viva. È un
  campione parziale e dichiarato.

Il minuto passato ai candidati è quello del feed live: 0..89, 90+j. Per il recupero del 1T, A0 riceve 45
(cella 40-45) nella versione «generosa». La variante `A0_1T_cumulato` passa 45+j, cioè la cella 45-50
che il v3 userebbe se il feed Betfair desse il minuto cumulato: il feed **non è verificato**.

### Candidati (stessa pipeline, stessi stati)
| candidato | cosa | serve in live | il runtime oggi lo ha? |
|---|---|---|---|
| A0 | atlante di produzione (codice vero, parità provata) | minuto, gol, lega | sì |
| A0_squadre | A0 col livello squadre (id API-Football) | + id squadre | **no**: Safe/Mike passano nomi Betfair |
| A1 | celle sulla verità vera (niente clamp, minuti 88-89 contati) + recupero 1T proprio + **recupero 2T modellato**: r(lega, gol) per minuto × durata D ~ π(lega) (per lega, shrinkata verso il campione con K dal metodo dei momenti; decisione dell'utente) | minuto (≥90 = recupero), gol, lega; per il 1T anche il tempo (1/2) | minuto sì; il **tempo** va passato dal feed (`matchStatus`), oggi non arriva all'atlante |
| A2 | + pesi per età della stagione (emivita 2/3/5/nessuna) | — | sì |
| A3 | + differenza reti / chi conduce (moltiplicatore sul globale) | punteggio per lato | sì |
| A4 | + rossi per lato (moltiplicatori stimati) | rossi casa/trasferta | sì (Safe `red_home/red_away`) |
| A5 | + forza pre-partita: ((λc+λt)/gol medi della lega)^β | λ pre-partita | **sì**: Safe li ha in `_hazard_check(lambdas=...)`, Mike in `lambdas_con_ripiego` |
| A6 | K delle celle dal metodo dei momenti (cluster per partita) invece di 1500 | — | sì |
| B1 | LightGBM binario per orizzonte sulla stessa verità; variabili: tempo, t, recupero, j, gol, diff, rossi per lato, minuti dall'ultimo gol, lega (categorica), stagione, λc, λt (monotone) | come A5 + rossi + minuto dell'ultimo gol | quasi: manca il minuto dell'ultimo gol (c'è nella timeline IPS di Safe) |
| B2 | B1 con i λ VERI del motore Poisson (`fixture_predictions`) al posto del proxy | λ del motore | sì (Safe `source=fixture`) |

**Proxy dei λ** (`forza.py`): un «Poisson-Elo» cronologico che per ogni partita predice λc, λt solo dal
passato e poi aggiorna i rating. η=0,015 e rientro=1,0 sono scelti su 2018-2023 per verosimiglianza di
Poisson. Sul 2025 si confronta con i λ veri (§4).
**A7** (fusione graduale seme↔stato del globale) non è un candidato di previsione su questo campione,
perché le leghe affidabili sommano sempre più di 10.000 partite. Vedi §6.

## 3. Validazione (addestra ≤2023, valuta 2024: 4.396 partite, 420.150 stati)

Log-loss media per stato (orizzonte 3'; ultima colonna: tutti, 2'). Le varianti della catena sono
cumulative: A3/A4 = A1+A2+x, A6 = A1+A2+A5+x.

| candidato | tutti 3' | 0-74' | 75-89' | recupero 2T | recupero 1T | tutti 2' |
|---|---|---|---|---|---|---|
| A0 | 0.28434 | 0.28247 | 0.29635 | 0.28963 | 0.18622 | 0.21311 |
| A1 | 0.28242 | 0.28203 | 0.29263 | 0.27341 | 0.16294 | 0.21279 |
| A2 emivita 2 / 3 / 5 | 0.28235 / 0.28235 / 0.28237 | 0.28200 | 0.29242 / 0.29246 / 0.29250 | 0.27283 / 0.27292 / 0.27307 | | 0.21275 |
| A3 (+diff) | 0.28237 | 0.28202 | 0.29242 | 0.27292 | 0.16424 | 0.21277 |
| A4 (+rossi) | 0.28239 | 0.28201 | 0.29255 | 0.27311 | 0.16437 | 0.21277 |
| A5 (+forza) = **A\*** | **0.28190** | 0.28154 | 0.29201 | 0.27218 | 0.16708 | 0.21245 |
| A6 (+K mdm) | 0.28193 | 0.28156 | 0.29196 | 0.27225 | 0.16888 | 0.21247 |
| B1 | **0.28154** | 0.28126 | 0.29157 | 0.27118 | 0.16422 | 0.21210 |

**Catena greedy.** Una variante entra solo se Δ log-loss (2'+3') ha un IC 95% per partita tutto sotto zero:
| passo | Δ log-loss 2'+3' per stato [IC 95%] | esito |
|---|---|---|
| A0 → A1 | −0,00224 [−0,00263, −0,00190] (solo regolari −0,00122 [−0,00146, −0,00098]) | vince |
| + A2 emivita 2 / **3** / 5 | −0,00010 [−0,00023, +0,00001] / **−0,00011 [−0,00020, −0,00002]** / −0,00009 [−0,00014, −0,00003] | entra emivita 3 (la migliore puntuale con IC < 0) |
| + A3 differenza reti | +0,00003 [−0,00004, +0,00010] | fuori |
| + A4 rossi | +0,00005 [0,00000, +0,00011] (peggiora; moltiplicatori stimati 1,04-1,10) | fuori |
| + A5 forza pre-partita (β = 0,63) | −0,00075 [−0,00100, −0,00050] | vince |
| + A6 K metodo dei momenti (K ≈ 2.960 per 3', 3.400 per 2'; celle con τ²≤0: 13 su 68) | +0,00005 [−0,00001, +0,00012] | fuori: K=1500 resta |

**B1**: iperparametri scelti in validazione (`taratura_b1.py`, `taratura_b1.json`) fra tre configurazioni.
Vince «regolarizzato» (num_leaves 15, min_data_in_leaf 3000, lr 0,03; 213/206 giri con arresto
anticipato sul 2024): somma log-loss 0,493643 contro 0,493683 della base e 0,493720 senza la variabile
stagione.

Nota sul recupero in validazione. Nel ≤2023 il DB non ha la durata del recupero (`extra` nasce nel 2024).
Il recupero 2T di A1 in validazione è quindi il ripiego (cella 85-90 contata sulla verità vera,
dichiarato in `ripieghi`), e il modello r×π entra solo nel test. Anche così A1 batte A0 nel recupero
(0,27341 contro 0,28963).

Scelte congelate per il test (`risultati_validazione.json`):
- **A\* = A1 + A2 (emivita 3) + A5**, K=1500;
- B1 «regolarizzato» con i giri riscalati sulla quantità di dati;
- proxy dei λ con η=0,015 e rientro 1,0.

## 4. Test (addestra ≤2024, valuta 2025)

**Prima corsa invalidata dal difetto dei dati** (§1, reperto 6). Sul 2025 intero la cella 85-90 osservata
era 0,155 contro 0,088-0,103 delle stagioni precedenti, e il recupero risultava vuoto. È così perché i
gol del recupero europei 2025 sono registrati al 90'. I numeri dell'«intero» restano in
`risultati_test.json` → `metriche_intero_verita_falsata`, solo per trasparenza. Il test si legge su
due insiemi fissati **prima** di guardare gli esiti dei candidati. Il criterio è la registrazione del
recupero, non i gol.

| insieme | definizione | partite | stati |
|---|---|---|---|
| **pulito** (primario) | blocchi lega-mese con ≥60% dei gol di fine tempo con extra | 1.021 | 97.827 |
| **regolari sicuri** | tutto il 2025, stati t ≤ 41 in ogni tempo: le finestre non toccano la fine del tempo | 4.524 | 380.016 |

Il pulito è fatto per lo più dalle leghe piccole (tutto il 2025) e da mar-apr 2026 delle grandi.

### 4.1 Insieme pulito: log-loss per stato (3'), e differenza da A0 [IC 95% per partita]
| candidato | tutti | 0-74' | 75-89' | recupero 2T | recupero 1T* |
|---|---|---|---|---|---|
| A0 (v3) | 0.30633 | 0.30143 | 0.33610 | 0.29030 | 0.36090 |
| A0_squadre | 0.30752 (**peggio** +0.00120 [+0.00066, +0.00173]) | 0.30263 | 0.33728 | 0.29134 | 0.36737 |
| A1 | 0.30481 (−0.00151 [−0.00219, −0.00082]) | 0.30106 | 0.33515 | 0.26948 (−0.02082 [−0.02798, −0.01331]) | 0.43606 |
| A1+A2 / +A3 / +A4 / +A5 / +A6 | 0.30488 / 0.30481 / 0.30477 / 0.30470 / 0.30488 | | | | |
| **A\*** = A1+A2+A5 | **0.30477 (−0.00156 [−0.00224, −0.00082])** | 0.30096 (−0.00047 [−0.00086, −0.00009]) | 0.33540 (−0.00070 [−0.00293, +0.00163]) | **0.26912 (−0.02118 [−0.02810, −0.01353])** | 0.44195 |
| V4_modulo (codice di produzione proposto) | 0.30477 (identico ad A\*) | | | | |
| A\* recupero = media per lega | 0.30485 | | | 0.27045 | |
| A\* recupero = oracolo (recupero vero) | 0.30438 | | | 0.26246 (−0.02784) | |
| **B1** | **0.30370 (−0.00263 [−0.00333, −0.00188])** | 0.30003 (−0.00140) | 0.33384 (−0.00227 [−0.00467, +0.00002]) | 0.26911 (−0.02120) | 0.39359 |

*Recupero 1T: 197 stati, campione parziale e distorto per costruzione (§2). Nessuna differenza ha IC che
esclude lo zero. Il modulo usa per default la cella 40-45 (§5).

**B1 contro A\*** (pulito): 3' −0,00107 [−0,00160, −0,00056]; 2' −0,00082 [−0,00120, −0,00044];
75-89' 3' −0,00157 [−0,00280, −0,00030]; recupero 2T pari (−0,00002 [−0,00246, +0,00254]).

**Orizzonte 2'** (pulito, differenze da A0):
- A\*: −0,00018 [−0,00045, +0,00009] su tutto, **non significativo**. Sugli 0-74' −0,00032
  [−0,00058, −0,00006].
- B1: −0,00100 [−0,00141, −0,00060].

### 4.2 Regolari sicuri (tutto il 2025, 4.524 partite): differenza da A0
| candidato | 3' tutti | 3' 75-89' (t≤41 → 75-86') | 2' tutti |
|---|---|---|---|
| A1 | −0.00038 [−0.00049, −0.00027] | −0.00164 [−0.00221, −0.00106] | −0.00010 [−0.00015, −0.00004] |
| A1+A5 | −0.00062 [−0.00079, −0.00045] | −0.00207 | −0.00026 |
| **A\*** | **−0.00067 [−0.00084, −0.00049]** | −0.00199 [−0.00277, −0.00125] | −0.00029 [−0.00040, −0.00018] |
| **B1** | **−0.00128 [−0.00154, −0.00103]** | −0.00288 [−0.00372, −0.00204] | −0.00084 [−0.00104, −0.00066] |
| A0_squadre | +0.00176 [+0.00142, +0.00204] (peggio) | +0.00164 | +0.00119 |

### 4.3 Calibrazione (pulito, 3'): prevista A0 | A\* | B1 contro osservata
| minuto | n | A0 | A\* | B1 | osservata |
|---|---|---|---|---|---|
| 0-5 | 5105 | 0.0665 | 0.0670 | 0.0704 | 0.0756 |
| 20-25 | 5105 | 0.0774 | 0.0773 | 0.0826 | 0.0878 |
| 40-45 | 5105 | **0.1122** | 0.0782 | 0.0828 | 0.0799 |
| 45-50 | 5105 | 0.0840 | 0.0835 | 0.0883 | 0.0907 |
| 60-65 | 5105 | 0.0917 | 0.0910 | 0.0956 | 0.0977 |
| 75-80 | 5105 | 0.0913 | 0.0890 | 0.0947 | 0.1032 |
| 80-85 | 5105 | 0.0926 | 0.0902 | 0.0949 | 0.1017 |
| 85-90 | 5105 | **0.1395** | 0.0917 | 0.0952 | 0.1087 |
| 90+0 | 968 | **0.1399** | 0.0879 | 0.0950 | 0.1074 |
| 90+1 | 951 | 0.1398 | 0.0866 | 0.0934 | 0.0988 |
| 90+2 | 935 | 0.1398 | 0.0827 | 0.0900 | 0.0845 |
| 90+3 | 871 | 0.1397 | 0.0753 | 0.0817 | 0.0631 |
| 90+4 | 736 | 0.1399 | 0.0674 | 0.0732 | 0.0571 |
| 90+5 | 506 | 0.1397 | 0.0610 | 0.0689 | 0.0573 |
| 90+6-7 | 540 | 0.1401 | 0.0563 | 0.0671 | 0.0611 |
| 90+8+ | 233 | 0.1423 | 0.0548 | 0.0628 | 0.0300 |

Decili (pulito, 3', prevista→osservata):
- A0: primo 0,067→0,079, ultimo 0,142→0,095 (sovrastima in cima);
- A\*: primo 0,063→0,078, ultimo 0,103→0,114;
- B1: primo 0,061→0,068, ultimo 0,118→0,127.

ECE su tutto:

| | A0 | A\* | B1 |
|---|---|---|---|
| pulito | 0,0130 | 0,0084 | 0,0064 |
| regolari sicuri | 0,0043 | 0,0022 | 0,0019 |

Il pulito del 2025 segna qualche gol in più dell'addestramento, soprattutto nelle leghe piccole: tutti i
candidati sottostimano un poco a metà partita.

**AUC** (pulito, 3'): A0 0,521 [0,513, 0,530], A\* 0,540 [0,530, 0,548], B1 0,550 [0,541, 0,561].
Differenze: A\*−A0 +0,019 [+0,010, +0,027]; B1−A\* +0,011 [+0,004, +0,020]. **Onestà**: sotto 0,56
per tutti. Un gol nei prossimi 2-3' è quasi imprevedibile dallo stato. Il valore per il trader è il
**livello** (calibrazione), soprattutto a fine tempo e nel recupero, non la capacità di separare i casi.

### 4.4 Leghe piccole (shrinkage) e per lega
Log-loss 3', differenza A\* − A0 [IC], nell'ordine: pulito; regolari sicuri. Storico prima del 2025 fra
parentesi.
- 833 (~130): −0,00096 [−0,00255, +0,00064]; −0,00039 [−0,00133, +0,00054].
  B1: −0,00578 [−0,00824, −0,00298], la differenza grande.
- 834 (~135): −0,00003 [−0,00246, +0,00285]; **+0,00114 [+0,00010, +0,00219]**, cioè A\* peggio.
- 835 (240): −0,00239 [−0,00362, −0,00115]; −0,00078 [−0,00138, −0,00018].
- 306 (~130): −0,00154 [−0,00418, +0,00150]; −0,00080 [−0,00167, +0,00020].

Sulle leghe grandi (regolari sicuri) A\* − A0 è negativo in 11 su 12, e significativo in 7 (71, 88,
94, 135, 140, 144, 40). Tabella completa: `validazione_hazard/per_lega_test.json`.

Lettura: con poco storico l'empirico shrinkato non ha nulla da dire oltre il globale. Il metodo dei
momenti (A6) non ha aiutato. B1 invece, con i λ e la lega come variabili, coglie le leghe «da gol»
(833).

### 4.5 La forza pre-partita coi λ veri (quelli che Safe usa in live)
- 2.382 partite 2025 hanno i λ del motore Poisson (`fixture_predictions`). Rispetto al proxy
  Poisson-Elo:
  - correlazione dei totali 0,58;
  - log-verosimiglianza di Poisson dei gol −1,817 (λ veri) contro −1,774 (proxy);
  - medie 2,73 contro 2,74 (gol veri 2,76).
- Su queste partite (regolari sicuri, 3', differenza da A0):
  - A\* col proxy −0,00060 [−0,00086, −0,00034];
  - **A\* coi λ veri −0,00034 [−0,00062, −0,00005]**, come A1 (−0,00033): la forza non aggiunge nulla;
  - B1 col proxy −0,00108;
  - **B2 (B1 coi λ veri) −0,00081 [−0,00121, −0,00041]**, peggio del proxy ma sempre meglio di A\*;
  - modello live di Safe (`event_goal_hazard`, λ veri) −0,00013 [−0,00059, +0,00036]: non distinguibile
    da A0.
- Su quelle del pulito (562 partite, 3'):
  - modello live 0,29259, A0 0,29255, A\* 0,29146, B2 0,29086;
  - nel recupero 2T: modello live 0,28979, A0 0,30111, A\* 0,28502, B2 0,28405.
- β della forza stimato su ≤2024 col proxy: 0,61. **In live coi λ di oggi la A5 è innocua ma inutile.**
  Per averne il guadagno servono λ migliori: il proxy Poisson-Elo, che però vuole gli id squadra
  collegati (§7).

### 4.6 «Divergenza spuria» contro il modello live di Safe (`event_goal_hazard`, 3', λ veri)
Soglie di Safe: `hazard_warn` 30% (confidenza dimezzata) e `hazard_drop` 60% (segnale scartato); più il
35% del brief. Si misura la quota di stati in divergenza, e fra questi quelli in cui la frequenza
osservata (per decile del rapporto modello/atlante) sta più vicina al modello che all'atlante.

Regolari sicuri, 2.382 partite, 200.088 stati:

| atlante | >30%: quota stati; ragione al modello | >35% | >60% (scarto) |
|---|---|---|---|
| A0 | 10,1%; **80%** | 5,4%; **100%** | 0,16%; 40% |
| A\* | 5,1%; 60% | 2,5%; 70% | 0,07%; 50% |
| B1 | 5,5%; 10% | 3,1%; 0% | 0,64%; 20% |

Pulito con recupero, 562 partite:

| atlante | >30% | >60% |
|---|---|---|
| A0 | 14,9%; 50% | 1,3%; **70%** |
| A\* | 12,1%; 30% | 3,6%; 30% |
| B1 | 11,9%; 10% | 3,7%; 0% |

Lettura:
- con l'atlante di oggi il controincrocio di Safe dimezza la confidenza su 1 stato su 10, e nella
  maggior parte di quei casi ha torto l'atlante;
- con A\* le divergenze si dimezzano;
- con B1, quando diverge, ha ragione B1.

Log-loss sugli stati segnalati >30% (regolari sicuri):
- A0: modello 0,2906, atlante 0,2936;
- A\*: 0,2883 contro 0,2882;
- B1: 0,2550 contro 0,2492.

Misura grezza (per decili): va letta come indicazione, non come conteggio esatto.

### 4.7 Recupero: il prezzo del dato mancante (decisione dell'utente)
In live il recupero annunciato non arriva, e A\* usa la distribuzione della durata **per lega**
(shrinkata verso il campione, K_durata = 12,6 dal metodo dei momenti). Le medie per lega stimate su
≤2024 vanno da 5,5' (135) a 7,3' (71); campione 6,34'.

| recupero 2T (pulito) | log-loss 3' | log-loss 2' |
|---|---|---|
| A\* distribuzione per lega (in produzione) | 0.26912 | 0.22179 |
| A\* sola media condizionata per lega | 0.27045 (+0,00133) | 0.22240 |
| A\* col recupero VERO (oracolo, a posteriori) | 0.26246 (−0,00666) | 0.21912 |

Il dato mancante costa 0,0067 di log-loss per stato di recupero (2,5%). È il guadagno disponibile se il
feed desse il recupero annunciato. Betfair IPS ha `elapsedAddedTime`, cioè quanto recupero è stato
giocato, non quanto ne è stato annunciato: da verificare se esiste un campo dell'annunciato.

## 5. Il modulo pronto: `Betfair/stream/scalper/atlante_v4.py` (NON collegato)

**Interfacce** (pure, niente rete, niente flumine):
- `partita_v4(match_row, event_rows, eventi_recupero=False)`: accettazione identica a
  `genera_atlante.sequenza_partita`.
- `stato_lega_v4_vuoto`, `aggiungi_partita_v4(stato, partita, recupero_affidabile=True)`: stato grezzo
  **additivo per stagione**, idempotente per `fixture_id`.
- `stagione_recupero_affidabile(goal_rows)`: la regola del reperto 6.
- `assembla_v4(stati, generated_at=..., stagione_rif=..., emivita=3, k_celle=1500, beta=...)`: restituisce
  il blocco da mettere in `atlas["v4"]`. I blocchi v3 restano, così i consumatori di oggi non cambiano.
- `consulta_atlante_v4(atlas, minute, goals, league_id, *, tempo=None, lambda_home=None,
  lambda_away=None, horizon=..., usa_cella_recupero_1t=False)`:
  - **stesse chiavi** di `consulta_atlante` (p, fonte, livello, n, confidenza, lega, atlante,
    eta_giorni, nota) **più** `versione`, `fase` (regolare/recupero_1T/recupero_2T), `p_2min`,
    `p_3min`, `recupero_atteso_min` e `forza{moltiplicatore, usata}`;
  - senza blocco v4 ripiega su `consulta_atlante` e lo dichiara (`versione='v3'`);
  - mai eccezioni.

**Cosa serve per collegarlo** (lavoro del coordinatore; non fatto qui):
1. Generatore/motore a domanda: `matches` deve leggere anche
   `extra:raw_json->fixture->status->extra`. I gol li legge già con `minute_extra` (`COLONNE_GOL`).
   Facoltativo: gli eventi con `minute_extra` non nullo (per il recupero 1T, che il modulo per default
   non usa). Per ogni (lega, stagione) va applicata `stagione_recupero_affidabile` ai gol.
2. Lo stato v4 per stagione è piccolo: 28×4×3 + 8 numeri + durate, circa 4 KB per lega-stagione.
   Si somma per partita come il v3 (incrementale, idempotente).
3. Consumatori:
   - Safe `_hazard_check` passerebbe `lambda_home/lambda_away` (li ha) e `tempo` (dal `matchStatus`
     IPS, da collegare) e `minute` come oggi;
   - Mike idem;
   - Omega usa solo `h2h_hint`, che resta.
   - **Le soglie `hazard_warn`/`hazard_drop` non sono toccate.** Le divergenze cambieranno (§4.6): è una
     decisione dell'utente.
4. Il livello squadre del v3 va spento (§4, `A0_squadre` peggiora). v4 non ha livello squadre.

**Parità col candidato validato.** Il banco chiama il modulo con `usa_cella_recupero_1t=True`, per
essere identico ad A\*. Il default di produzione (cella 40-45 nel recupero 1T) cambia solo gli stati del
recupero 1T, ed è ciò che la validazione 2024 ha misurato come ripiego (A1 0,16294 contro A0 0,18622).
- Sul test il modulo dà gli stessi numeri di A\* su 436.041 stati: differenza massima 2,6·10⁻⁶, dovuta
  all'arrotondamento a 7 decimali nel blocco.
- Due test di parità sui dati sintetici, con e senza forza, verificano gli stessi numeri stato per stato.

**Costo** (misurato, `sonde/costo_modulo.py`, PC di sviluppo; Championship, 9 stagioni, 5.005 partite):

| voce | misura |
|---|---|
| conteggio | 2,74 s (0,55 ms a partita) |
| assemblaggio | 1 ms |
| consultazione | 0,037 ms (due orizzonti) |
| stato grezzo | 56 KB, di cui 38 KB di fixture_id come nel v3 |
| blocco assemblato per lega | 7 KB |

Nel banco: 38.000 partite + assemblaggio di 16 leghe + 436.041 consultazioni in 91 s complessivi.
Compatibile col motore a domanda: calcolo per lega in pochi secondi, incrementale.

## 6. Cosa non vince, e perché conta
- **A3, differenza reti / chi conduce**: +0,00003 in validazione, ±0 nel test. L'informazione «chi conduce» oltre ai gol totali, in una tabella empirica, non si
  vede. B1 la usa (importanza 2-3%). I numeri del test sono ricavati da A1+A3 contro A1:
  pulito 0,30481 contro 0,30481; sicuri +0,00002.
- **A4, rossi**: moltiplicatori stimati 1,04-1,10 (più gol con un rosso), ma in validazione peggiora.
  I rossi sono rari (5% degli stati) e l'effetto dipende da chi è in dieci e dal punteggio. Il modello
  live li tratta (`red_card_multipliers`); l'atlante no.
- **A6, K dal metodo dei momenti**: K ≈ 3.000 contro 1.500, e nessun guadagno. 13 celle su 68 con varianza
  fra leghe ≤0: le leghe grandi si somigliano molto nel tasso per minuto.
- **A7, fusione graduale seme↔stato del globale: NON misurata.** Nel campione il globale ha sempre più di
  10.000 partite affidabili, quindi lo scatto a 10.000 non si attraversa mai. Misurarla richiede di
  simulare stati parziali (1, 3, 5... leghe) e un seme indipendente dal test. Proposta, non validata:
  peso del globale di stato w = N/(N + K_g), con K_g dal metodo dei momenti sulle celle globali.
- **Livello squadre del v3 (A0_squadre)**: peggiora in tutti gli insiemi (+0,0012 / +0,0018, IC
  sopra zero). Il profilo att/def per bucket di 5' con K=12 è rumore. La forza della squadra entra meglio
  come λ pre-partita (A5/B1).
- **Recupero 1T con cella propria**: non validabile (manca la durata) e non vince. Il modulo usa la cella
  40-45.

## 7. Raccomandazione
1. **Subito: v4 = A\*** (modulo `atlante_v4.py`).
   - Correggere la verità (clamp) e modellare il recupero per lega vale da solo quasi tutto il guadagno
     tardo. Nel recupero 2T l'errore di calibrazione passa da 0,063 a 0,008. Il v3 sovrastima il rischio
     di gol dal 90': +30% al 90+0, +145% al 90+5, quasi ×5 oltre il 90+8.
   - È empirico, additivo per stagione, leggero, e ha parità provata col candidato validato.
   - Nel collegamento, passare `lambda_home/lambda_away` **solo** con una fonte buona. Con i λ di oggi
     (`fixture_predictions`) la forza non aggiunge nulla, ma neanche toglie (§4.5).
2. **Prossimo passo (massimo livello): B1**. Batte A\* di −0,00107 [−0,00160, −0,00056] (pulito) e
   −0,00061 (sicuri), ed è l'unico che vince anche sul 2' e nel 75-89'. Quando diverge dal modello live
   ha ragione (§4.6).

   | voce | B1 |
   |---|---|
   | addestramento | 3 modelli × 2 orizzonti, 1.036 s su 3,5 M stati (8 thread); notturno, globale, non per lega |
   | file dei modelli | ~450 KB l'uno (testo LightGBM) |
   | previsione | microsecondi per stato |
   | libreria | `lightgbm` 4.6.0, già nel .venv |
   | variabili live | minuto, tempo, recupero giocato, punteggio per lato, rossi per lato, minuti dall'ultimo gol (timeline IPS), lega, λ pre-partita |

   Non è «per lega in pochi secondi»: è un modello unico notturno. Il motore a domanda resterebbe per i
   conteggi (seme/ripiego), B1 per il numero.
   Prima di usarlo servono:
   - (a) **gli id squadra collegati** in Safe/Mike, per il proxy Poisson-Elo. Con i λ di oggi B2 vale
     −0,00081 contro −0,00108;
   - (b) il minuto dell'ultimo gol dal feed;
   - (c) un'action di riaddestramento con lo stesso banco come controllo d'ingresso: un modello nuovo
     entra solo se batte il precedente fuori campione.
3. **Da portare all'utente (decisioni, non prese qui)**:
   - il difetto dei dati 2025 (reperto 6): fonte e rilettura dei gol;
   - lo spegnimento del livello squadre del v3;
   - le soglie di divergenza di Safe, perché con v4 le divergenze si dimezzano;
   - la qualità dei λ del motore Poisson: peggiori di un Elo di Poisson, e riguarda anche i segnali di
     Safe/Omega, non solo l'atlante.

## 8. Test e falsificazione

**Suite nuove.** Sandbox `SUPABASE_URL=http://127.0.0.1:9`, `SUPABASE_SERVICE_ROLE_KEY=x`,
`SUPABASE_KEY=x` esportata prima di pytest.
- `Betfair/stream/tests/test_validazione_hazard_2026_09_25.py`: 38 test. Coprono posizioni del
  recupero, partite, regola di copertura, autogol, verità e stati, finestre che non attraversano
  l'intervallo, minuti dall'ultimo gol, metriche (AUC contro sklearn coi pareggi), bootstrap, lettore
  finto, parità di A0 con `aggiungi_partita`, `consulta_atlante` usata da A0, recupero (distribuzione,
  media condizionata, oracolo, partita viva), pesi, celle, forza senza sbirciare, blocchi di recupero
  registrato.
- `Betfair/stream/tests/test_atlante_v4_2026_09_25.py`: 11 test. Coprono accettazione come la
  produzione, idempotenza, **parità col candidato validato** (con e senza forza), fasi, ripiego del
  recupero 1T, monotonia nel recupero, forza dichiarata, chiavi di `consulta_atlante` e ripiego v3,
  ripieghi senza durate, stagione senza recupero registrato, mai eccezioni.

I finti hanno le chiavi e i tipi veri: un test verifica che il finto di `matches` porti esattamente le
colonne che `raccogli.COLONNE_MATCH_BANCO` chiede, e quello di `match_events` le `COLONNE_GOL` +
`player_id`.

Esecuzione: le due suite nuove più `test_genera_atlante_2026_09_24`, `test_atlante_a_domanda_2026_09_25` e
`safe_strategy/tests/test_atlante_note_livello_2026_09_25`: **79 passati** (38 + 11 nuovi + 30 esistenti).

**Falsificazione** (`validazione_hazard/falsificazioni.py` + `rotture_v4.py`). Per ogni rottura: una
sostituzione minima, pytest, ripristino **dal testo in memoria** (mai git checkout) con verifica
dell'hash.
- Giro 1 (`falsificazioni_esito_giro1.txt`): 31 rosse su 34. **Tre VERDI**:
  - M12, il lettore finto ignora `event_type`;
  - M17, l'oracolo sbaglia di un minuto;
  - M18, la media non condizionata.

  Ho aggiunto `test_lettore_cache_filtra_come_postgrest`, il caso oracolo con 2' residui e
  `test_media_condizionata_su_partita_viva`.
- Giro 2 (`falsificazioni_esito.txt`): **34 rosse su 34, ripristini tutti OK, suite verde dopo i
  ripristini.** Rotture: 22 sul banco (M1-M22: posizioni, durate, copertura, autogol, finestre, `<=`,
  minuti di recupero, AUC, bootstrap, lettore, orizzonti, partita viva, pesi, trasformazione hazard,
  oracolo, media, celle, blocchi, sbirciata della forza) e 12 sul modulo (V1-V12: pesi, partita viva,
  beta, tempo, idempotenza, soglia affidabile, durata, K, ripiego, stagione non affidabile, regola
  sempre vera, cella 1T per default).

**Suite intere e replay: NON eseguiti.** Il modulo non è collegato e nessun file di produzione è toccato
(il diff tracciato è solo `.gitignore`).

## 9. Non verificato, e perché
- **Formato del minuto Betfair nel recupero del 1T**: `timeElapsed` = 45+j cumulato, oppure 45 fisso?
  Non ci sono registrazioni IPS a portata nel banco. La variante `A0_1T_cumulato` misura il caso
  cumulato: differenza non significativa.
- **Il recupero annunciato nel feed IPS** (`elapsedAddedTime` è quello giocato): non verificato.
- **A7** (fusione graduale del globale): non misurata (§6).
- **B1 in live**: nessuna prova di integrazione. Le variabili `dal_gol` e `tempo` non sono oggi
  collegate all'atlante.
- **Il test del recupero 2T** si regge sull'insieme pulito: 1.021 partite, 5.740 stati di recupero, in
  prevalenza leghe piccole e mar-apr 2026. Le leghe grandi del 2025 non danno una verità di fine tempo
  affidabile.
- **Il recupero del 1T** è misurato su un campione parziale e selezionato («vivo provato da un evento
  non-gol successivo»): nessuna conclusione forte.
- **`fixture_predictions`**: i λ esistono solo per il 2025 (2.382 partite, generate da 02/2026). Il
  confronto col proxy vale per quelle.
- **Leghe piccole**: 833/834/835/306. La 395 (prevista) è esclusa dalla regola di copertura della
  produzione. Il loro storico è di 1-3 stagioni: la stima dello shrinkage per lega piccola ha pochi punti.
- **Il DB**: 316 richieste in sola lettura in tutto (285 raccolta + 14 supplemento + 17 sonde, tetto
  ~400). Il difetto 2025 è verificato con 2 GET sulla sola Premier. L'estensione alle altre leghe è
  misurata dalla cache, non con letture dedicate.

## 10. Consegna
- Referto: questo file.
- Banco (CLI riproducibile, legge solo la cache):
  `python -m Betfair.stream.scalper.validazione_hazard.banco --da-cache [--fase validazione|test|tutto] [--fumo]`.
  Corsa completa ≈ 65 min, di cui il B1 del test ≈ 17-48 min secondo il carico; i modelli B1 restano in
  cache e vengono ricaricati.
  - Taratura B1 (solo validazione): `python -m Betfair.stream.scalper.validazione_hazard.taratura_b1`.
  - Tabelle: `python AUDIT_2026-09-25/validazione_hazard/tabelle_test.py`, per lega: `per_lega.py`.
  - Raccolta dal DB (una volta): `python -m Betfair.stream.scalper.validazione_hazard.raccogli --env <.env principale> [--supplemento]`.
- Esiti:
  - `AUDIT_2026-09-25/validazione_hazard/risultati_validazione.json`;
  - `risultati_test.json` (insiemi `metriche` = pulito, `metriche_regolari_sicuri`,
    `metriche_intero_verita_falsata`, sottoinsiemi coi λ veri, divergenze, calibrazioni);
  - `taratura_b1.json`, `per_lega_test.json`, `tabelle_test.md`;
  - log `log_*.txt`.
- Patch: `AUDIT_2026-09-25/validazione_hazard.patch`, con il diff di `.gitignore` e tutti i file nuovi
  .py/.md, cache esclusa.
- Nessun commit, nessun `git add`, nessun push, nessuna scrittura sul DB, nessun file di Safe/Omega/Mike
  toccato, nessuna soglia cambiata.

