# BRIEF STANDARD PER OGNI DELEGATO (ordine dell'utente, 28/09/2026)

Vale per OGNI agente che lavora su questo repo, in ogni sessione. Il brief specifico del tuo
cantiere aggiunge l'obiettivo e il perimetro; queste regole non si ripetono e non si derogano.
Leggi anche `CLAUDE.md` (radice). Se tocchi un bot: `PROCESSO_STANDARD_BOT.md` (§6 copertura,
§7 catalogo dei 35 errori) = criteri di accettazione del tuo lavoro.

Comunica in italiano. Codice ASCII-only, commenti in italiano, stile del file che tocchi.

## 1. Chi decide

- L'UTENTE e' un trader che mette soldi veri: decide lui le strategie e accende lui app e bot.
- Il COORDINATORE (sessione principale) assegna, rilegge il tuo diff, rilancia i tuoi test,
  rifa' le tue falsificazioni e ne aggiunge di sue. Il tuo lavoro e' «fatto» solo dopo la sua
  verifica. Un referto ottimista che non regge alla verifica torna indietro.

## 2. Condizioni dell'utente (permanenti)

1. **Le strategie non si alterano MAI di iniziativa**: soglie, stake, tetti, gambe, cancelli
   decisionali. Correggi i BUG. Se una correzione cambia una decisione di trading, NON farla:
   scrivila in «Decisioni per l'utente» con file:riga, effetto e proposta.
2. **Il paper e' lo SPECCHIO del live per TUTTI i bot** (ripetuto dall'utente il 28/09): stesso
   codice, stesso tipo d'ordine (FOK compreso), stesso bet delay, stessa coda, stessi parziali,
   stessi rifiuti. L'unica differenza ammessa: i soldi sono finti. Ogni ramo `paper` che si
   comporta diversamente dal live e' un BUG da correggere, non una scelta.
3. Paper e live non si sommano mai. Calcio e tennis non si mischiano.
4. All'avvio dell'app nessun bot opera; i bot li accende solo l'utente. Aiuti statistici
   ACCESI di default.
4-bis. **USCITE: OGNI BOT, NESSUNO ESCLUSO, HA UN PULSANTE** (ribadito il 28/09, gia' detto il
   17/09 e il 25/09: NON richiederlo MAI all'utente). Due posizioni: MANUALE = l'uscita, in
   profitto o in perdita, diventa una proposta che l'utente approva; AUTOMATICO = il bot
   chiude da solo. Di serie e dopo ogni riavvio: MANUALE. Nessuna eccezione «per strategia»
   (nemmeno scalper, sniper, scalper tennis). Restano automatiche solo le protezioni di
   sicurezza (freno, chiusura forzata a fine finestra, divergenza dello specchio, tetti).
5. UN canale dati per tutti i bot, nessuna chiamata Betfair duplicata; tutto passa dai canali
   al millisecondo, il DB a 30 s e' solo ripiego.
6. **Resilienza**: dopo una caduta di rete o un riavvio ogni componente torna a funzionare da
   sola, senza doppi ordini e senza perdere lo stato.
7. **Volume**: nessuna partita idonea resta fuori per limiti tecnici nostri.
8. Si usa SOLO l'app desktop: nessun lavoro su login o uso dal browser.
9. Un errore trovato si corregge subito, con test, nella stessa consegna.
10. **Le chiusure sono sempre PERFETTE**: importo esatto al centesimo (mai gonfiato, mai
    arrotondato al minimo) e profitto o perdita SPALMATI su entrambe le selezioni (green-up).
    Solo le APERTURE sotto il minimo si portano al minimo accettato da Betfair.
11. **Flusso dati interrotto** (decisione del 28/09): se i prezzi di una partita non sono vivi
    nessun bot apre ne' chiude a mercato su quei prezzi; un punteggio che si aggiorna non
    rende «fresco» un prezzo fermo.
12. Replay e test: veloci e mirati (profili rapidi del banco), mai giorni di attesa.

## 3. DIVIETI ASSOLUTI

- **Git**: niente commit, niente push, mai `git add -A` ne' `git add <cartella>`, niente
  `checkout`/`reset`/`stash`/`clean` sul checkout principale. Il lavoro resta NON committato
  nel tuo worktree. Nessun file > 1 MB nel repo (registrazioni, jsonl, log: fuori).
- **DB di produzione: SOLA LETTURA.** Solo `SELECT`/`EXPLAIN`. Nessun INSERT/UPDATE/DELETE/DDL.
  Le modifiche al DB si scrivono come file in `migrations/` e le applica l'utente.
  ATTENZIONE: `load_dotenv()` risale le cartelle e trova il `.env` vero anche dal worktree:
  NON eseguire codice di produzione che scrive (`main()`, `run_once`, `run_for_date`,
  `store=True`, servizi, runner, script della radice), nemmeno «per provare».
- **Nessuna chiamata vera a Betfair o ad API-Football** (login, ordini, quote, quota contata).
  La documentazione si legge dal web o dalle note del repo.
- **Nessun processo nuovo**: niente app, runner, registratori, server, watcher in background.
  Non rilanciare action GitHub (`gh workflow run`, `gh run rerun` vietati; `gh run view` si').
- Niente `pip install`, `npm install`, `npm ci`. Non ricompilare l'exe.
- **Carico del PC (8 core, 16 GB)**: test SOLO sui file toccati e collegati, con timeout.
  NIENTE suite intere, NIENTE replay del banco: li lancia il coordinatore, uno alla volta.
- **Worktree**: `.venv` e `frontend/node_modules` sono JUNCTION verso il checkout principale
  (`cmd /c mklink /J .venv "<principale>\.venv"`). Mai cancellazioni ricorsive, mai
  `git worktree remove`, mai `rmdir /s`. A fine lavoro lascia il worktree com'e'.
- Non uscire dal perimetro di file del tuo brief. Se serve un file fuori perimetro: fermati su
  quel punto, scrivilo nel referto, continua con il resto.

## 4. Metodo

1. **Prima leggi**: cosa dice `CRONOSTORIA.md` di quel pezzo (cerca il nome del file o del
   reperto), il referto che l'ha trovato, il codice vero riga per riga. Non fidarti dei numeri
   di riga dei referti: il codice e' cambiato, ritrovali.
2. **Cerca prima di creare**: se esiste gia' un modulo, una funzione o una risorsa condivisa
   che fa il lavoro, usala. Documentazione ufficiale prima delle ipotesi (Betfair Exchange
   Stream API e Betting API; flumine installato = 2.13.11, betfairlightweight del `.venv`).
3. **TDD**: test ROSSO che riproduce il difetto, poi la correzione, poi VERDE.
4. **Falsificazione obbligatoria di ogni test nuovo**: introduci nel codice la mutazione che
   reintroduce il difetto, il test deve diventare rosso. Prima di mutare salva
   `git diff > patch_prima.diff`; ripristina con `git checkout -- <file>` +
   `git apply --include='<file>' patch_prima.diff`; verifica `grep -c MUTAZIONE` = 0 e
   `git diff --stat` uguale a prima. Mai interrompere a meta' uno script di falsificazione.
5. **I finti parlano come il vero**: stesse chiavi, stessi tipi, stessi valori possibili
   (maiuscole/minuscole comprese) dell'oggetto vero. Un finto comodo nasconde il bug.
6. Frontend: `npx tsc -p tsconfig.app.json --noEmit` = 0 errori, mai `@ts-ignore` ne' `any`.
7. Importi: qualsiasi importo al centesimo e' gestibile; rispetta i minimi di Betfair come da
   documentazione e da decisione dell'utente scritta nel brief.
8. Consegna parziale ma verificata batte consegna completa in ritardo: se il cantiere e'
   grande consegna a blocchi e scrivi `STATO_RIPRESA.md` con cio' che resta.

## 5. Consegna (referto in `AUDIT_<data>/<NOME_CANTIERE>.md`)

1. Causa radice di ogni difetto, con prova (file:riga, log, query, documentazione con link).
2. Cosa hai cambiato e perche'; ELENCO ESATTO dei file toccati e dei file nuovi.
3. Test: comando esatto, numeri (passati/falliti), tempi. Falsificazioni: mutazione, esito.
4. Migrazioni SQL scritte (NON applicate) e in che ordine vanno applicate.
5. **Parita' paper/live**: cosa cambia in paper, cosa in live, prova che sono uguali.
6. **Cosa NON hai fatto** e **cosa NON hai potuto verificare** (obbligatorio, mai vuoto per
   cortesia: se e' tutto verificato scrivi come).
7. **Decisioni per l'utente**: solo cio' che tocca una strategia, in parole semplici, con la
   tua proposta.
8. Cosa va controllato dal vivo in paper al prossimo avvio dell'app (controllo, dato atteso,
   dove leggerlo).

Messaggio finale al coordinatore: massimo 20 righe (fatto, numeri, non fatto, non verificato,
decisioni). Il dettaglio sta nel referto.
