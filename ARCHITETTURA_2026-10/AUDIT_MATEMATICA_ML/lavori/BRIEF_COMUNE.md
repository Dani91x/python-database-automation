# Regole comuni per ogni delegato dell'audit matematica (09/10/2026)

Repo: C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation (radice = R).
Brief generale: R/ARCHITETTURA_2026-10/AUDIT_MATEMATICA_ML/BRIEF_AUDIT_MATEMATICA_ML.md (leggi par. 1, 5, 6).

VINCOLI (inviolabili):
- SOLA LETTURA. Non modificare NIENTE fuori da R/ARCHITETTURA_2026-10/AUDIT_MATEMATICA_ML/. Scrivi solo il tuo
  file in R/ARCHITETTURA_2026-10/AUDIT_MATEMATICA_ML/lavori/ e, se servono, script di sonda in
  R/ARCHITETTURA_2026-10/AUDIT_MATEMATICA_ML/lavori/sonde/.
- Niente git commit/checkout/stash/switch/add. Niente pip/npm install. Niente processi lasciati
  accesi, niente bot/app/runner, mai ordini Betfair, mai chiamate di rete a Betfair.
- DB Supabase: di norma NON serve. Se proprio serve, solo SELECT con LIMIT stretto (<=2000 righe),
  mai RPC che scrivono, mai scansioni pesanti (le GitHub Actions soffrono di timeout 57014).
- Le strategie dei bot non si giudicano "da cambiare": le divergenze si scrivono come tali.
- Python: usa R/.venv/Scripts/python.exe per le sonde; le sonde importano il codice di produzione
  in sola lettura (nessuna scrittura su file/DB).
- Codice e file ASCII preferibilmente; scrivi in italiano.

METODO:
- Ogni affermazione con file:riga verificata leggendo il codice. Cio' che non hai verificato
  marcalo «NON VERIFICATO» con il motivo.
- Le mappe in R/ARCHITETTURA_2026-10/ (00_INVENTARIO, 03_SCHEDE_COMPONENTI/*, 07_MISURE_OGGI,
  08_REVISIONE_CRITICA) servono da mappa, NON da verita'.
- Stato dell'arte: puoi usare WebSearch/WebFetch (carica gli strumenti con ToolSearch se serve);
  cita la fonte (URL o riferimento bibliografico) per ogni confronto. Massimo ~8 ricerche.
- Dove possibile MISURA o calcola a mano (esempi numerici) con una piccola sonda.
- Sii economico: leggi per estratti (grep + Read con offset/limit), non file interi enormi.

FORMATO DEL TUO FILE (scrivilo PRIMA di rispondere al coordinatore; aggiornalo a meta' lavoro
se il lavoro e' lungo, cosi' un'interruzione non lo perde):
1. Inventario: tabella | id | file:riga | cosa calcola (formula) | input | output | consumatore (bot/UI/consigli/report/workflow) |
2. Analisi per componente: correttezza, casi limite, confronto stato dell'arte (con fonte), verdetto.
3. Reperti: elenco numerato, ciascuno con GRAVITA' (CRITICO/ALTO/MEDIO/BASSO), file:riga, prova
   (estratto di codice o output di sonda), impatto su soldi/previsioni, NON VERIFICATO se tale.
4. Miglioramenti proposti: guadagno atteso, costo, metrica di misura, rischio, cosa tocca.
5. Decisioni che spettano all'utente (se una proposta tocca una strategia di bot).
6. Metodo di ricerca usato (comandi grep/glob, conteggi) per garantire la completezza del tuo perimetro.
Risposta finale al coordinatore: massimo 25 righe con i reperti CRITICO/ALTO e il percorso del file.
