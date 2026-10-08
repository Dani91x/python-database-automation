# BRIEF COMUNE PER I DELEGATI DEL PIANO DI ARCHITETTURA (08/10/2026)

Coordinatore: sessione a crediti API (Opus). Tu sei un delegato. Lingua: italiano.
Leggi PRIMA, per intero: `ARCHITETTURA_2026-10/BRIEF_PIANO_ARCHITETTURA_2026-10-08.md` (il brief del piano,
soprattutto §0, §2, §8 e §9 che vale su tutto), `CLAUDE.md`, `BRIEF_STANDARD_DELEGATI.md` (§2 condizioni
dell'utente e §3 divieti: valgono per te). Per i bot: `PROCESSO_STANDARD_BOT.md` §6 e §7 (criteri di
accettazione di ogni futura tappa: le tue sezioni «Parita'» li devono citare per numero).

## Regole ferree

1. **Solo documenti**. Scrivi SOLO il file (o i file) che il tuo compito indica, dentro `ARCHITETTURA_2026-10/`.
   Script di misura usa-e-getta SOLO in `ARCHITETTURA_2026-10/strumenti/` (ASCII-only, commenti in italiano,
   rieseguibili, mai importati dall'app, nessuna scrittura fuori da `ARCHITETTURA_2026-10/`).
   Nessuna modifica a codice, test, migrazioni, `.env`, `frontend/`, `desktop/`, `CRONOSTORIA.md`.
2. **Git**: niente commit, niente add, niente checkout/reset/stash/clean. Il coordinatore committa.
3. **DB Supabase: sola lettura** (solo SELECT/EXPLAIN, se lo usi). Nessuna chiamata a Betfair o API-Football.
   Non eseguire codice di produzione (servizi, runner, `main()`, script di radice): `load_dotenv()` trova il `.env` vero.
   Nessun processo in background. Niente pip/npm install. Niente suite intere ne' replay del banco.
   Log grandi (c'e' un log da 3 GB): mai leggerli interi; `tail`, `grep -c`, lettura a flusso.
4. **Ogni affermazione cita la fonte**: `percorso/file.py:riga` (o intervallo `:120-145`), numero misurato con lo
   strumento che l'ha prodotto, tabella del DB, URL pubblico. Vietati «credo», «probabilmente», «di solito».
   Righe contate con `wc -l` sui file tracciati (`git ls-files`). Le ipotesi del brief (§1 righe, §4 architettura)
   NON sono vere finche' non le verifichi nel codice: se il codice dice altro, scrivi cio' che dice il codice.
5. **La logica di trading e' intoccabile**: soglie, stake, tetti, gambe, cancelli restano IDENTICI. Si
   riducono gli strati attorno (servizio, DB, UI, banco, duplicati), mai le regole. Una riduzione che
   cambierebbe una decisione non si propone: si scrive come «decisione per l'utente».
6. **Nessuna funzionalita' persa**: l'elenco delle funzionalita' deve essere COMPLETO, letto riga per riga
   (anche dalla UI: pannelli, pulsanti, parametri editabili, allarmi, attivita' scritte). Meglio lungo e vero.
7. Non superficiale: una scheda senza funzionalita' con `file:riga`, senza numeri, senza parita' e senza stima
   delle righe viene rimandata indietro. Il coordinatore verifica a campione le tue citazioni contro il codice:
   una citazione falsa = scheda respinta.

## Formato della SCHEDA DI COMPONENTE (sempre queste sezioni, in quest'ordine)

Intestazione: nome del componente, perimetro (file inclusi con righe), data, autore (delegato Sonnet).

1. **Oggi** — file e righe (`wc -l`); responsabilita' REALI lette dal codice; dipendenze in entrata (chi lo
   importa: `grep -rn "import ..."`) e in uscita; tabelle del DB lette/scritte (con `file:riga` della chiamata e,
   se misurata, la frequenza — fonte: `SCHEMI_BOT/sistema/MISURE_2026-10-02.md` o tua misura); canali locali;
   processi; stato condiviso; orologi; thread; chiamate di rete nel percorso critico.
2. **Funzionalita'** — elenco numerato con prefisso della scheda (es. `A-001`, `A-002`...), TUTTE, ognuna con
   `file:riga` e una riga che dice cosa fa per l'utente o per gli altri componenti. Indica quali sono visibili
   nella UI (con il file del pannello) e quali sono parametri editabili.
3. **Difetti strutturali** — duplicazioni (con le righe gemelle negli altri moduli: `file:riga` di entrambe),
   accoppiamenti, lavoro ripetuto, attese di rete nel percorso critico, dati copiati, stato in piu' posti.
   Conteggi con lo strumento usato (es. `grep -c`).
4. **Domani** — dove vive ogni funzionalita' nella struttura nuova (UNA cartella per componente, UN contratto con
   tipi, UN `COSA_FA.md`); il contratto proposto (interfaccia Python/TS con i tipi: firme, eventi esposti e
   consumati); stima delle righe DOPO con il calcolo (cosa diventa condiviso, cosa sparisce perche' ripetuto,
   cosa resta perche' e' strategia); confronto «per sostituire questo componente OGGI tocco i file ... / DOMANI
   tocco solo la cartella ... e i suoi test di contratto»; cosa e' gia' in una libreria matura (flumine,
   betfairlightweight) e oggi e' riscritto (con `file:riga` del nostro e riferimento alla libreria).
5. **Parita'** — il test o replay che dimostra «stessa identica cosa»: registrazione (`registrazioni_banco/`,
   `_live_raw/`), scenari del banco (`Betfair/stream/backtest/`), numeri che devono coincidere (decisioni,
   ordini, importi, istanti, P&L), fotografie della UI; quali voci di §6 e §7 di `PROCESSO_STANDARD_BOT.md` copre.
6. **Migrazione** — passi nel guscio (interruttore, periodo «ombra» con confronto automatico, taglio del
   vecchio), ordine rispetto agli altri componenti, rischi, ritorno indietro.
7. **Misure** — numeri prima (oggi, con fonte) e obiettivo dopo: latenza, richieste al DB al minuto, memoria,
   CPU, righe. Se un numero non esiste, scrivi lo strumento che lo misurerebbe.

In coda: **Decisioni per l'utente** (se ce ne sono) e **Cosa ho verificato di persona / cosa non ho potuto verificare**.

## Consegna

Quando hai finito, rispondi al coordinatore con: percorso del file scritto, numero di funzionalita' elencate,
righe oggi / stima dopo, i 3-5 difetti principali, cio' che non hai potuto verificare. Breve.

## Ripresa ed efficienza (aggiunta alle 14:40 dell'08/10, vincolante)

- Il primo giro di delegati e' stato interrotto alle 12:37 prima di scrivere le schede. Sul disco restano
  script e uscite utili: `ARCHITETTURA_2026-10/strumenti/inventario/uscite/` (righe per file `s01_*`, grafo degli
  import e candidati morti `s02_*`, matrice tabelle/RPC `s03_*`, funzioni duplicate `s04_*`, radice `k01_*`),
  `strumenti/dati_g1/uscite/` (chiamate DB Python/frontend, schema SQL, gemelle), `strumenti/dati_J/`,
  `strumenti/misure/uscite/` (feed dalle registrazioni), `strumenti/*_gemell*.py` e `h_*_output.txt`.
  PARTI DA LI': rieseguili se servono, verifica a campione 2-3 righe contro il codice, citali come fonte.
- Budget stretto: lavora per grep, `sed -n 'a,bp'`, indici di funzioni (`grep -n "^def \|^class \|^    def "`),
  non leggere per intero file > 1.500 righe. Tetto indicativo: 70 chiamate di strumenti. Scheda di 400-900 righe:
  densa di `file:riga` e numeri, niente prosa di riempimento.
- Scrivi la scheda PRESTO (bozza completa dopo l'esplorazione) e poi raffinala: un'interruzione non deve
  lasciare il file vuoto.
