# Mappatura dei flussi reali - consegna per la FIRMA del PC (11/10/2026)

Scopo (ordine dell'utente, 10/10 sera): "voglio che mappi qualsiasi cosa per poi fare la v2 al pari dei competitor".
L'app si usa da domani con operazioni reali; questi strumenti REGISTRANO e MISURANO i flussi veri senza cambiare
nulla del comportamento. Tutto e' **spento di serie**: senza le righe nel `.env` l'app e' identica a master.

Ramo: `claude/mappa-flussi` (= `mappa/integrazione`), nato da `origin/master` `a3a58ad8`. Nessuna strategia toccata
(soglie, stake, tetti, gambe). Nessuna connessione nuova a Betfair, nessun processo nuovo.

## 1. Cosa contiene

| Pezzo | Interruttore (`.env`) | Cosa registra / misura | Documento |
|---|---|---|---|
| M-1 registratore ordini | `REGISTRO_ORDINI=1` | righe grezze dello stream ORDINI (ocm, battiti, status) e ogni REST con soldi (place/cancel/replace/update) di desktop, bot, Omega/Mike, con istanti e attore; decisione -> customerOrderRef | `M1_REGISTRATORE_ORDINI.md` |
| M-2 misure | `MONITOR_SALUTE=1` (gia' di T0A) + `npm run build` | M1 messaggio Betfair -> ladder a schermo (calcio e tennis); M2 decisione -> risposta di placeOrders per attore/strada/modo; clic dal ladder; ocm al secondo; latenza canale -> bot ed esito -> bot; pesi REST | `M2_MISURE.md` |
| M-3 canale e mappa | `REGISTRA_CANALE=1` | ogni messaggio del canale locale ws (chi pubblica, chi riceve, comandi ed esiti) + lo strumento `mappa_flussi` che unisce canale, raw, Salute e ordini in una mappa della giornata | `M3_CANALE_E_MAPPA.md` |
| Agganci M-1 <-> M-2 | (dei due sopra) | ocm in Salute anche a registratore spento; esito -> bot (paper/live separati); `invio` della strada canale | `M2_MISURE.md` par. 7, `M1_REGISTRATORE_ORDINI.md` par. 10 |

Peso su disco stimato: M-1 1-6 MB/giorno (tetto 512 MB); M-3 50-300 MB/giorno (tetto 1 GB, 7 giorni). Da confermare
sul PC dopo un giorno.

## 2. Verifiche gia' fatte nel cloud (coordinatore + revisori indipendenti)

- Ogni pezzo: referto dell'agente, verifica personale del coordinatore (diff, test, mutazioni proprie), revisione
  indipendente avversa, correzioni, seconda verifica del coordinatore.
- Difetti trovati e corretti prima della consegna: doppia chiamata REST non rilevata dai test (M-1, ora 1 sola
  richiesta HTTP per chiamata provata su 40 casi); file gzip illeggibile dopo riavvio (M-1 e M-3: mai append, lettore
  tollerante); stream morto non visto dall'analisi (M-1); misura a schermo falsa all'apertura del ladder (M-2);
  mappa che non leggeva i file di M-1 e sommava paper e live (M-3); scrittura che rallentava il canale sotto carico
  (M-3: p99 del loop da 56 ms a 3,5 ms acceso contro 2,7 ms spento).
- Mutazioni: M-1 80/80 rosse, M-2 33/34 (1 equivalente dichiarata) + frontend 12/12, M-3 45/46 (M19 rifatta rossa
  3/3), agganci 20/20.
- Prova di capo a capo: un file scritto dallo scrittore VERO di M-1 letto dalla mappa di M-3 (sezione 4 della mappa).
- Replay a monitor spento: safe_base, safe_esatto, safe_punta su 35760084: 132/132 righe uguali tolti i tempi; mike
  identico al referto T0A.
- Suite intera sul ramo unito: vedi par. 5.

## 3. Checklist del PC (in quest'ordine) - VERSIONE LEGGERA, decisione dell'utente del 12/10/2026

Decisione dell'utente (12/10): "non voglio perdere giorni a rifare i test (abbiamo certificato tutto piu' volte):
se aggiungiamo solo righe di codice di TRACCIAMENTO non servono i replay, perche' non abbiamo cambiato nulla; gli
unici test sono di corretto e uguale funzionamento". Quindi per QUESTO ramo NON si rifanno replay ne' ricertificazioni
ne' la suite intera (gia' eseguita: par. 5). Al loro posto una prova meccanica che il codice di prima, a interruttori
spenti, e' IDENTICO.

1. `git fetch`; `git checkout claude/mappa-flussi` (o un worktree).
2. `python ARCHITETTURA_2026-10/mappa/verifica_solo_tracciamento.py` (circa 1 minuto). Cosa fa:
   - per ogni file di produzione gia' esistente toccato, confronta l'ALBERO del codice (AST) della base `a3a58ad8`
     con quello del ramo dopo aver tolto SOLO gli import del tracciamento e i blocchi `if <interruttore>:`; se resta
     una differenza qualsiasi, ROSSO. Unica eccezione dichiarata: l'argomento di misura `invio=req.ricevuto_ms`
     (0 a monitor spento = nessuna misura, provato);
   - frontend: ogni riga aggiunta deve essere tracciamento riconosciuto (guardata da `misuraAccesa()`), nessuna
     riga tolta;
   - lancia i 312 test "spento = identico, acceso = stesso esito" dei quattro pezzi.
   Deve finire con `ESITO: VERDE - solo tracciamento`. Falsificata nel cloud: una chiamata non guardata, un ramo
   "spento" cambiato, una riga TS in piu' e una riga TS cambiata escono ROSSE.
3. `cd frontend && npx tsc -p tsconfig.app.json --noEmit` -> 0 errori.
4. Un giro di 5 minuti con l'app COSI' COM'E' (interruttori spenti, dopo il merge e prima di accendere): tutto
   come ieri.
5. Riferire all'utente il risultato; merge su master SOLO col suo si' (gia' dato il 12/10 "dopo la firma").
6. Accensione (la fa l'utente, vedi par. 4): migrazione `migrations/monitor_metrics_2026-10-09.sql`, tre righe nel
   `.env`, `npm run build` in `frontend/` AD APP CHIUSA, riavvio dell'app. Controlli "acceso" ai par. 8 di M1, 4 di
   M2, 7 di M3 (solo i punti di osservazione, non i replay).

Nota per chi verra' dopo: questa via leggera vale SOLO per cambi di puro tracciamento che passano
`verifica_solo_tracciamento.py`. Un cambio che tocca il comportamento (anche di una riga) segue lo standard pieno di
`PROCESSO_STANDARD_BOT.md`.

## 4. Da dire all'utente prima dell'accensione

- I registratori scrivono su disco LOCALE comandi, ordini (prezzi, stake, bet_id) in chiaro; nessuna credenziale
  (token e app key oscurati, provato dai test). Niente va al cloud.
- Lato tennis la misura del clic sulla strada canale resta vuota (il file e' nell'impronta dei bot tennis: non
  toccato).
- Nota superata in `M1_REGISTRATORE_ORDINI.md` par. 9 ("Interfaccia con M-3: oggi non li legge"): risolta da M-3
  (`1d13973f`), provata di capo a capo.

## 5. Suite intera sul ramo unito

Eseguita dal coordinatore l'11/10 sul ramo unito (M-1 + M-2 + agganci + M-3): `python -m pytest Betfair/ -q -p no:cacheprovider`
-> **11.771 passati, 87 saltati, 6 xfailed, 0 rossi** (415 s). Prova di capo a capo M-1 -> mappa di M-3 eseguita a mano.
