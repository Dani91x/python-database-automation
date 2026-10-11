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

## 3. Checklist del PC (in quest'ordine)

1. `git fetch`; `git diff origin/master..origin/claude/mappa-flussi --stat`. File esistenti toccati (solo aggiunte,
   tutte dietro un interruttore): `Betfair/stream/auth.py`, `Betfair/client.py`, `Betfair/stream/tempi_ordine.py`,
   `Betfair/stream/local_channel.py`, `Betfair/stream/live_order_worker.py` (1 argomento di misura),
   `Betfair/stream/esiti_ordini_canale.py`, `Betfair/stream/tennis_live/tennis_runner.py`,
   `Betfair/safe_strategy/canale_scan.py`, `frontend/src/lib/localChannel.ts`, `localTransport.ts`, `salute.ts`,
   `components/live/LadderView.tsx`. Rileggerli di persona.
2. Test e mutazioni dei tre documenti (M1 par. 8, M2 par. 4 e 7.4, M3 par. 7), poi la suite intera UNA volta
   (`python -m pytest Betfair/ -q -p no:cacheprovider`), frontend `npx tsc -p tsconfig.app.json --noEmit` (0 errori) e
   `npx vitest run`.
3. **Ricertificazione dal punto d'ingresso unico** (cambia l'impronta del codice, NON la strategia):
   `python -m Betfair.stream.backtest.certifica` prima (`a3a58ad8`) e dopo, a interruttori spenti, righe uguali tolti
   i tempi, per: safe_base, safe_esatto, safe_punta, **safe_tennis**, **i 4 bot tennis** (registrazione tennis del
   PC); di controllo omega e mike su 35760084. Senza questo punto il ramo NON va su master.
4. Giro paper a interruttori SPENTI: app identica a ieri (nessuna cartella `_live_raw\_ordini`, `_logs\canale`).
5. Solo dopo la firma e il si' dell'utente: merge su master, righe nel `.env`, `npm run build` in `frontend/` AD APP
   SPENTA, riavvio dell'app da parte dell'utente; controlli dei punti "acceso" dei tre documenti.
6. Firma: chi ha rieseguito, data, numeri.

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
