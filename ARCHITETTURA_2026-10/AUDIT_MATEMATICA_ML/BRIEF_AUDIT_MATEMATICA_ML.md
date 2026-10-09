# BRIEF — Audit della matematica: Poisson, ML e tutti i componenti matematici (09/10/2026)

Sessione autonoma su crediti API (Agent SDK). Tetto circa 80 USD: il lavoro va FINITO con
questi crediti (pianifica la spesa per tappe, vedi par. 7). Nessuno risponde alle domande.

## 1. Obiettivo (parole dell'utente)

L'utente vuole sapere se stiamo sfruttando il nostro stack al massimo, se si puo'
migliorare, se tutti i componenti arrivano correttamente a bot, UI, previsioni e consigli,
e NON vuole errori di progettazione. Tre perimetri, nessuno escluso, NIENTE va omesso:

1. **Tutta la catena Poisson** (dai dati grezzi alla probabilita' mostrata o usata).
   Domande: siamo al miglior livello matematico possibile? Abbiamo omesso qualcosa? Si
   puo' migliorare ancora? Sono le migliori pratiche in assoluto?
2. **Tutta la catena ML**: addestramento, utilizzo in produzione, struttura, strumenti.
   Domande: e' al massimo livello possibile? Abbiamo omesso qualcosa? Si puo' fare meglio?
   Ci sono pratiche non usate che migliorano performance, tempi e risultati?
3. **Tutti i componenti matematici** che alimentano bot, UI, consigli, motori, scanner,
   report (es. valore atteso, prezzi equi, calibrazioni, Kelly/stake, green-up/hedge,
   P&L, commissioni, xG, Elo/rating, probabilita' implicite e rimozione del margine,
   statistiche live, soglie, aggregazioni). Domande: sono al massimo livello? Si puo'
   fare meglio? Abbiamo omesso qualcosa? E' la soluzione migliore per performance e
   risultati di livello?

Per OGNI componente porsi domande mirate, confrontare con lo stato dell'arte (letteratura,
pratiche dei professionisti del betting e del trading sull'exchange, librerie mature),
documentarsi (WebSearch/WebFetch ammessi, con fonte citata) e verificare sul codice.

## 2. Punto di partenza (rileggere prima di tutto)

- `ARCHITETTURA_2026-10/README.md` e i documenti 00-08 della stessa cartella (inventario,
  funzionalita', competitor, architettura obiettivo, misure, revisione critica): usarli
  come mappa e per non rifare lavoro, ma NON come verita': ogni affermazione si riverifica
  sul codice.
- `CLAUDE.md`, `PROCESSO_STANDARD_BOT.md` (par. 6 e 7), ultima sezione di `CRONOSTORIA.md`.
- Puntatori iniziali (incompleti di proposito: l'inventario lo fai tu, con grep su tutto il
  repo): `value_engine/` (poisson_total, calibrate), `tactical_engine/` (dixon_coles,
  model, generate_predictions), `Ai Engine/ai_engine/`, `update_poisson_calibration.py`,
  `valida_motore_poisson.py`, `training_planner.py`, `tools/omega_validate_models.py`,
  `Betfair/` (omega, mike, safe, stream, scanner, tennis), `frontend/src` (calcoli lato UI),
  `.github/workflows/` (addestramenti e calcoli pianificati), `sql/` e `migrations/`
  (funzioni SQL che calcolano), script `tmp_*` solo per capire la storia.

## 3. Consegne (tutte dentro `ARCHITETTURA_2026-10/AUDIT_MATEMATICA_ML/`)

- `00_INVENTARIO_MATEMATICO.md`: OGNI componente matematico (file:riga, cosa calcola,
  input, output, chi lo consuma: bot / UI / consigli / report / workflow). Nessuna
  omissione: in coda, il metodo di ricerca usato per garantirlo (grep, pattern, conteggi).
- `01_CATENA_POISSON.md`: catena dai dati al consumo, diagramma testuale, formule
  effettive, parametri e loro origine, calibrazione, validazione; confronto con lo stato
  dell'arte (es. Dixon-Coles con decadimento temporale, Poisson bivariata, binomiale
  negativa/sovradispersione, inflazione degli 0-0, modelli bayesiani gerarchici, forza
  dinamica, vantaggio del campo per lega, uso delle quote di mercato come prior,
  calibrazione e metriche: log-loss, Brier, RPS, curve di affidabilita'); verdetto per
  ogni domanda del par. 1.1.
- `02_CATENA_ML.md`: dataset, feature, perdita di informazione dal futuro (leakage),
  split temporali, validazione, calibrazione delle probabilita', scelta dei modelli e degli
  iperparametri, riaddestramento e deriva, versionamento dei modelli, riproducibilita',
  tempi e costi, come il modello arriva in produzione e chi lo legge; confronto con le
  migliori pratiche (es. walk-forward, ensembling/stacking, calibrazione isotonica/Platt,
  feature dalle quote, SHAP, tracciamento esperimenti, monitoraggio della deriva);
  verdetto per ogni domanda del par. 1.2.
- `03_COMPONENTI_MATEMATICI.md`: per ogni componente del par. 1.3, correttezza della
  formula (esempi numerici calcolati a mano vs codice), casi limite (quote 1.01/1000,
  importi minimi .it, commissione, arrotondamenti al tick e al centesimo, divisioni per
  zero, NaN), coerenza tra copie della stessa formula in Python, SQL e frontend.
- `04_FLUSSO_FINO_AL_CONSUMATORE.md`: per ogni numero mostrato in UI o usato da un bot,
  la tracciatura end-to-end dalla sorgente al consumatore: arriva corretto? arriva in
  tempo? stessa unita' e stesso significato? valori stantii, fallback silenziosi, default
  che mascherano un buco, campi calcolati ma mai letti, campi letti ma mai calcolati.
- `05_ERRORI_DI_PROGETTAZIONE.md`: reperti ordinati per gravita' (CRITICO / ALTO / MEDIO /
  BASSO), ciascuno con file:riga, prova, impatto su soldi/previsioni, cosa NON hai potuto
  verificare.
- `06_PIANO_MIGLIORAMENTI.md`: miglioramenti proposti ordinati per guadagno atteso /
  costo, con stima dell'effetto, metrica con cui misurarlo, rischio, e cosa tocca.
  Nessuna proposta altera di iniziativa le strategie dei bot: se un miglioramento le
  tocca, va nel file decisioni.
- `07_RIEPILOGO_PER_L_UTENTE.md`: risposta diretta, in italiano chiaro per un non
  tecnico, a OGNI domanda del par. 1 (si'/no/in parte + perche'), poi le prime 10 azioni.
- `DECISIONI_PER_L_UTENTE.md`, `COSTI.md`, `FATTO.txt` (regole nel prompt di sessione).

## 4. Metodo

- Coordinatore Opus; delegati Sonnet per inventario, schede per componente e ricerca
  sullo stato dell'arte; sintesi e verdetti li scrivi tu dopo aver verificato i reperti
  sul codice (file:riga). Un reperto non verificato si marca «NON VERIFICATO».
- Ogni affermazione «e' gia' allo stato dell'arte» va motivata con fonte esterna e confronto.
- Dove possibile, misura: script di sonda e piccoli backtest di calibrazione SOLO dentro
  questa cartella, in sola lettura sui dati.

## 5. Condizioni dell'utente (vincolanti)

- AUDIT IN SOLA LETTURA: nessuna modifica a codice di produzione, test, workflow,
  migrazioni, DB, app. Si scrive solo in `ARCHITETTURA_2026-10/AUDIT_MATEMATICA_ML/`.
- DB: solo SELECT leggere e con LIMIT o filtri stretti; mai scansioni pesanti, mai
  scritture, mai chiamate a RPC che scrivono. Le GitHub Actions girano sullo stesso DB e
  soffrono di timeout (57014): non caricarlo.
- Mai ordini Betfair, mai avviare bot, app, registratori, runner o processi che restano
  accesi; mai ricompilare l'app; mai `npm install`/`pip install`.
- Le strategie dei bot non si alterano: le divergenze si scrivono e si portano all'utente.
- Niente commit, mai `git add -A`, mai push.

## 6. Criteri di accettazione

- Inventario dichiaratamente completo con metodo verificabile; ogni componente compare in
  almeno una scheda.
- Ogni domanda del par. 1 ha un verdetto esplicito con prove.
- Ogni reperto ha file:riga e gravita'; nessuna proposta senza metrica di misura.
- Riletti e citati, dove utili, i documenti di `ARCHITETTURA_2026-10/`.

## 7. Budget

Circa 80 USD in tutto. Ripartizione indicativa: inventario 12, Poisson 15, ML 15,
componenti 12, flusso fino al consumatore 10, sintesi/errori/piano/riepilogo 10, margine 6.
Aggiorna `COSTI.md` a ogni tappa; se una tappa sfora, comprimi le successive ma consegna
comunque TUTTI i file del par. 3 (meglio sintetico che mancante).
