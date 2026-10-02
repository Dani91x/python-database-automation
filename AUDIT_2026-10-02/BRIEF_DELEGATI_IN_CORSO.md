# Brief dei delegati in corso al 02/10/2026 (copia su disco per la ripresa dopo interruzione)

Regole comuni a OGNI brief (ordini dell'utente): nessuna regressione; strategie intoccabili; modifica minima; TDD
con finti con chiavi e tipi identici al vero; falsificazione di ogni test nuovo (rimetti il difetto -> rosso ->
ripristina) in uno script `AUDIT_2026-10-02/falsifica_*.py` + `_out.txt`; paper = specchio del live; mai `git add -A`,
niente commit su master, niente push, nessun ordine vero, nessuna scrittura sul DB, nessuna junction (interprete del
principale con percorso assoluto `.venv/Scripts/python.exe`, replay con `--data-dir "<principale>\_live_raw"`),
mai `git worktree remove`; test mirati soltanto (suite intera e replay li fa il coordinatore); referto con
sezione «NON VERIFICATO». Il coordinatore rilegge il diff, rilancia test e replay, fa mutazioni proprie, poi integra.

## 1. RUNNER MINIMI .it — worktree `.claude/worktrees/agent-a0274ee823e0cae47`, ramo `verifica-runner` (base 67261b9)
Stato: patch del 01/10 + correzioni 1-10 consegnate (`AUDIT_2026-10-02/RUNNER_MINIMI_CORREZIONI.{md,patch}`,
commit cf7fed5); verificate dal coordinatore su master (ramo `verifica-runner-master` e4c93e0 nel worktree
scratchpad `verifica-runner`). IN CORSO: punto 11 = traduzione (equivalente sull'altra selezione) ammessa SOLO per
gli attori in `ATTORI_CON_TRADUZIONE` (in `minimi_it.py`; oggi NESSUNO di Safe/Omega; Mike fuori: fa da se'; ordini
manuali fuori finche' il green-up del ladder non e' confermato); per gli altri: diretto -> place-and-trim finale
>= 0,50 -> rifiuto `SOTTO_MINIMO_NON_PIAZZABILE` con residuo + UN CRITICAL per episodio; test per attore;
falsificazione (insieme svuotato / attore aggiunto -> rossi); 5 righe per l'utente sul green-up del ladder con
posizioni su entrambe le selezioni (prima/dopo, esempio in euro). Consegna: patch rigenerata da `git diff 67261b9`.
Se interrotto: `git log 67261b9..verifica-runner`; se il punto 11 manca, rilanciare SOLO il punto 11 su quel ramo.

## 2. RICONCILIAZIONE ORDINI TRADOTTI (Safe, Omega) — worktree `agent-a3ca98366163157e2`, ramo `riconciliazione-tradotti` (base `verifica-runner-master` e4c93e0)
D1 Omega `omega_service.py:3131-3221` (ripiego > 20 s marca fallita una chiusura tradotta abbinata -> doppia
chiusura); D2 Safe `bot_service.py:1473-1503` (scrive sulla riga Over i numeri dell'ordine vero); D3 = punto 4 del
runner (equivalente anche su coda e REST di Safe: le tre vie stesso verdetto). Riprodurre ciascuno con test rosso,
correggere (approccio A: specchio con i termini chiesti; B: funzione unica `traduci_in_termini_chiesti`), test di
integrazione del caso money-critical (chiusura tradotta, esito oltre 20 s, nessuna seconda chiusura, P&L giusto al
centesimo), falsificazione. Consegna `AUDIT_2026-10-02/RICONCILIAZIONE_TRADOTTI.{md,patch}` (diff da
`verifica-runner-master`). Dopo: aggiungere Safe/Omega ad `ATTORI_CON_TRADUZIONE` solo se certificato.

## 3. MIKE CHIUSURA COPERTURA — worktree `agent-a8610ee7565537849`, ramo `mike-chiusura` (base e4c93e0)
Fase 1: applicare `AUDIT_2026-10-01/MIKE_CHIUSURA_COPERTURA.patch` (copia LF via `git show`), conflitto solo
`minimi_it.py` (tenere il runner, Mike importa); revisione riga per riga con le decisioni dell'utente 12 (chiusura
sulla STESSA selezione di serie: banca -> punta stessa selezione S*q/p, punta -> banca; l'altra selezione solo ripiego
se la stessa non e' piazzabile, mai sotto minimo; tabella via di chiusura -> selezione -> test, in profitto E in
perdita), 13 (residuo non chiudibile = LIVE_CLOSING fino al regolamento, senza rientri, CRITICAL + proposta), 14 (il
cash out vale la punta che parte davvero); guardia unica su ogni via; calcolo Ashdod a mano (banca Under 4,5
6,32@1,23 -> punta Under 4,5 7,55@1,03, P&L +0,33); mai lo stesso strumento dopo INVALID_BET_SIZE; M15; codice del
rifiuto su strada asincrona; L1/L2; 16 test vecchi; 21 mutazioni del delegato + >= 4 proprie.
Fase 2: BANCO OTTIMISTA (punto 3): il simulatore rifiuta gli ordini sotto minimo con INVALID_BET_SIZE, controllo di
certificazione + replay sintetico Ashdod, falsificazione. Fase 3: punto 25 (riga assente dallo scanner: rilettura REST,
annullo solo se CLOSED o oltre tetto esplicito) + R1 Mike (annullo degli ordini non abbinati all'arresto, diario +
CRITICAL per le posizioni). Fase 4: replay `mike base,riavvio,feed-stantio` (confronto con 5879/6/-14,17/602),
`sintetiche`, `coperture`, confronto numero per numero con `AUDIT_2026-10-01/replay/mike_*_CHIUSURA_COPERTURA.txt`;
profilo di un replay (5 punti caldi). Consegna `AUDIT_2026-10-02/MIKE_CHIUSURA_INTEGRATA.{md,patch}`.

## 4. FRONTEND MINORI — worktree `agent-a625321199874f716`, ramo `frontend-minori` (base 61f73a6)
Consegnati e verificati dal coordinatore (commit 3d45ea8): 31, 32, 33, 35, mojibake, doppio «Parametri», «LIVE ·
REALE», R-07; R-08 e R-10 lasciati con motivo. IN CORSO: reperto 1 (foglio Safe non legge `exits.base_control_exit`
e `_max` dal DB: `BotParamsSheet.tsx:83-131,234,732`) e reperto 2 (campo svuotato negli altri fogli: Mike
`lib/mike.ts:619-620` salva al minimo, tennis `TennisBotServiceParamsSheet.tsx:107-108` salva 0, Omega
`lib/omega.ts:1273-1282` salva ""): regola unica «chiave omessa = valore di serie del servizio», verificato nel
Python (tabella campo -> valore di serie file:riga; senza valore di serie -> salvataggio rifiutato «campo
obbligatorio»); test per ogni campo; tsc, suite intera a macchina scarica, fotografia invariata, build, `npm ci`
senza flag. Consegna `AUDIT_2026-10-02/FRONTEND_MINORI.{md,patch}` (`git diff master...HEAD`).

## 5. TEST ISOLAMENTO 2 — worktree `agent-aeeddf0df21d81001`, ramo `test-isolamento-2` (base master cccb4ab)
`test_audit_2026_09_11.py::test_l14_ttl_della_cache_lambda` rosso dopo il batch `/tmp/runner_tests_master.txt`
(35 file; bisezione), verde da solo: causa alla radice (cache/TTL di modulo o orologio non ripristinato), fixture di
ripristino, falsificazione, 3 giri col plugin di ordine casuale (`AUDIT_2026-10-02/ordine_test_plugin.py`); piu'
TUTTI i `delenv` di variabili presenti nel `.env` (es. `test_porta_ordini_f5_2026_09_24.py:815-816,831`) ->
`setenv` al valore spento. Consegna `AUDIT_2026-10-02/TEST_ISOLAMENTO_2.{md,patch}`.

## 6. REPLAY VELOCE — worktree `agent-a3973176466e94888`, ramo `replay-veloce` (base master 4220397)
`certifica mike 35760084 --scenari tutti --worker 0` oggi 489-720 s: obiettivo <= 300 s, tetto 600, referto IDENTICO
numero per numero (script di confronto che ignora solo i tempi); profilo cProfile prima/dopo con 10 punti caldi;
correzioni SOLO nel banco (cache di parsing, JSON ripetuto, log costruiti sempre, copie inutili, attese reali); punti
caldi dentro il motore di Mike: fermarsi e riportare; tempi prima/dopo anche di mike base, safe rapidi entrambi,
omega base; falsificazione per ogni cache (book stantio -> rosso). Consegna `AUDIT_2026-10-02/REPLAY_VELOCE.{md,patch}`.

## Ordine di integrazione (coordinatore)
runner (pt 11) -> riconciliazione (sopra il runner) -> Mike (sopra il runner) -> isolamento 2 -> replay veloce ->
frontend minori (merge, poi BUILD). Dopo ogni integrazione: regressione (replay Mike base/riavvio/feed-stantio,
Omega base, Safe rapidi entrambi; pytest delle aree toccate). Alla fine: suite Python intera + suite frontend intera,
elenco migrazioni (oggi: `migrations/scanner_list_bot_exposures_2026-10-02.sql` + eventuali nuove), push, poi
l'utente riavvia l'app e fa il test dal vivo di Mike con ordini piccoli.

## Come riprendere dopo un'interruzione
1. Leggere l'ultima sezione di `CRONOSTORIA.md` (punto di ripresa) e questo file.
2. Per ogni ramo qui sopra: `git log <base>..<ramo>` e il referto in `AUDIT_2026-10-02/` del suo worktree
   (`.claude/worktrees/agent-*/AUDIT_2026-10-02/`). Referto presente = verificare e integrare; assente = rilanciare
   il brief corrispondente su quel ramo (lavoro gia' committato nel ramo: non si perde).
3. Verifiche del coordinatore gia' fatte e i loro referti: `AUDIT_2026-10-02/verifica_*.txt`, `replay/*_coord.txt`.
