# TENNIS: iscrizione e armamento a caldo (25/09/2026)

Lavoro di un delegato del coordinatore, worktree rebased su `origin/master` = `2781e9c`.
L'auto-follow del calcio (`Betfair/stream/auto_follow.py`) NON era ancora su master: il
meccanismo di `SottoscrittoreStream.applica` è stato replicato 1:1 (da unificare quando entra).
Niente commit, niente DB vero, nessun processo nuovo, nessun replay lanciato. Strategie dei 4 bot
non toccate (nessuna modifica in `Betfair/stream/tennis_scalper/`). File del calcio
(`runner`, `live_order_worker`, `motore_ordini`, `auto_follow`) non toccati.

Ordine dell'utente: «TUTTI I BOT UNA VOLTA ARMATI DEVONO OPERARE SU TUTTE LE PARTITE IDONEE DA SOLI».

- Patch dei file tracciati: `AUDIT_2026-09-25/tennis_auto_follow.patch` (solo `tennis_runner.py`).
- File nuovi:
  - `Betfair/stream/tennis_live/iscrizione_a_caldo.py`: piano, sottoscrittore, lavoro nel thread di flumine;
  - `Betfair/stream/tennis_live/tests/test_tennis_iscrizione_a_caldo_2026_09_25.py`: 46 test;
  - `AUDIT_2026-09-25/mutazioni_tennis_iscrizione_a_caldo.py` ed esito in
    `AUDIT_2026-09-25/falsificazione_tennis_iscrizione_a_caldo.txt`.

## 1. Cosa fa ora → dopo

Righe: PRIMA = `origin/master` `2781e9c`; DOPO = il worktree.

| Pezzo | Prima | Dopo |
|---|---|---|
| Follow nuovo (auto o a mano) | `follow_worker` (prima `:1653`) chiede `_request_restart` (`:1669`/`:1671`). Con un bot qualunque non flat il restart si RINVIA (`:930`): la partita nuova non entra e i suoi bot non si armano | `follow_worker` (`:2067`) → `_allinea_follow_a_caldo` (`:1817`), sotto `session.caldo_lock`:<br>- il piano (`iscrizione_a_caldo.pianifica`, `:161`);<br>- il catalogo REST FUORI dal ciclo di flumine (`_risolvi_follow`, `:557`);<br>- nel ciclo di flumine (`_applica`, `:1896`): posizioni ricontrollate, poi `sottoscrivi` (`iscrizione_a_caldo.py:300`) con un nuovo `marketSubscription` sulla STESSA connessione; SOLO se riesce si aggiornano `market_meta`/`capture`;<br>- fuori dal ciclo: follow `STREAMING` e armamento a caldo dei bot della partita (`_arma_a_caldo`) |
| Bot richiesto su partita seguita | `bot_control_worker` alza `need_restart`/`serve_armare` (prima `:1341`, `:1423`), poi `_request_restart` (prima `:1516`) | `bot_control_worker` (`:1333`, contesto a `:1357`): raccoglie i richiesti non ospitati (anche i riarmati dopo l'uscita dell'istanza vecchia da `hosted`) e chiama `_arma_a_caldo` (`:1979`) → `return` (`:1554`), senza nessun restart |
| Armamento | Solo alla build (`setup_and_run`, ciclo `_instantiate_bot`) | `_arma_a_caldo`:<br>- istanza costruita fuori dal ciclo con la STESSA `_instantiate_bot` e gli stessi argomenti della build (`data_filter`, modalità CATTURATA al build, `client_paper` affiancato), presi da `ContestoCaldo` (`:1690`);<br>- `add_strategy` dentro il ciclo (`_aggiungi`, `:2014`) via `aggiungi_strategia_sullo_stream` (`iscrizione_a_caldo.py:343`): stesso stream o errore;<br>- stati DB `arming` → `running` (o `error`) come alla build, più la riga di attività `modalita` |
| Disarmo (`stopping`) | Bot disabilitato, poi restart di pulizia (`forza=False`) | Bot disabilitato come prima; nessun restart di pulizia. L'istanza inerte resta in `hosted` (lo specchio ordini ne legge ancora gli ordini e il P&L regolato) finché l'utente non riarma (`requested` → l'istanza vecchia esce da `hosted` → si arma la nuova a caldo) |
| Follow chiuso (partita finita, «smetti di seguire») | Restava nello stream fino alla build successiva | Dopo la grazia `TENNIS_USCITA_GRAZIA_S` (30 s di serie) esce dalla sottoscrizione SOLO se senza posizioni. I suoi bot si disabilitano (sono flat per costruzione) e vanno `stopped` con il motivo «partita non piu' seguita (follow chiuso): bot fermato a posizione flat». Con posizioni resta, e si riprova al giro dopo |
| Build | Tutti i follow, filtro nell'ordine di `market_meta` | `_entro_il_tetto_al_build` (`:1788`, chiamato a `:2250`): la build rientra nel tetto. Filtro CANONICO ordinato (`:2308`). `session.caldo` impostato a `:2401` e azzerato a framework fermo (`:2417`, `:2420`, `reset_streams` `:502`) |

Interruttore: `TENNIS_ISCRIZIONE_A_CALDO`, ACCESO di serie. Con `0`/`false`/`no`/`off` il
comportamento torna identico a prima, riletto a ogni giro (`_caldo_attivo`, `:1708`).

**Perché il lavoro gira nel ciclo di flumine** (`esegui_nel_thread_di_flumine`,
`iscrizione_a_caldo.py:248`): `CustomEvent` sulla `handler_queue` VERA, eseguito da
`_process_custom_event` fra un MarketBook e l'altro.
- Nessuna strategia viene aggiunta mentre flumine itera `self.strategies`.
- Nessuno `stream_id` cambia a metà di un book.
- Timeout di 5 s: il lavoro non ancora partito viene ANNULLATO (mai eseguito dopo), e si
  riprova al giro seguente.

## 2. Tetto e priorità

Il tetto è `TENNIS_TETTO_MERCATI` (180 di serie, stesso margine di `HARD_MARKET_CAP` del
calcio, ma con env tennis dedicata). Mai oltre 200 (limite Betfair per connessione), mai
sotto 1. Il tennis sottoscrive UN mercato per partita (Match Odds), quindi partite = mercati.
La connessione è una sola: nessuna connessione in più.

Priorità (`iscrizione_a_caldo.Evento.priorita`):
1. **posizioni vive**: mai espulse né tolte. Fonte: il blotter flumine del mercato
   (`_mercato_con_posizioni`, `:1719`), cioè un ordine vivo o un'esposizione abbinata non pari
   di QUALUNQUE strategia, bot o ordini manuali della ladder, oppure un «chiudi ora» in corso
   (`_evento_con_posizioni`, `:1764`). Nel dubbio la partita è protetta;
2. **seguita a mano**: mai espulsa;
3. **armata** (almeno una riga in `requested/arming/armed/running`);
4. **candidata**;
5. per ultima, la partita **in uscita**: follow sparito, in grazia, cede il posto per prima.

Espulsione:
- solo per una partita nuova di priorità STRETTAMENTE più alta, così fra pari non c'è
  giostra;
- esce la meno prioritaria, e a parità la più vecchia;
- i bot della partita espulsa vanno `stopped` con il motivo «tolta per far posto (tetto N)»;
- il follow torna `PENDING` con quella nota.

Niente di espellibile: rifiuto DICHIARATO.
- Log una volta per episodio.
- Follow `PENDING` con «in attesa: tetto di N mercati sulla connessione pieno».
- La partita rientra appena si libera un posto.

Un tetto abbassato non espelle nessuno.

## 3. Quando resta la ricostruzione

- All'avvio e al ricambio del runner (build iniziale e watchdog).
- A un errore di `framework.run`: il ciclo di `setup_and_run` ricostruisce.
- Quando la lista dei follow si svuota: un `marketSubscription` vuoto vorrebbe dire «tutto»,
  quindi si ricostruisce verso l'attesa con `_request_restart(..., forza=False)`. È sicuro,
  perché senza posizioni.
- Con l'interruttore spento: il comportamento di prima.
- Cambio della modalità del runner (OFF/PAPER/LIVE): la modalità si legge alla build, e
  cambiarla vuol dire riavviare il processo, come oggi.
- Auto-spegnimento e vita massima (`lifecycle_worker`): invariati.

## 4. Safe tennis e la porta via canale: solo diagnosi

`SAFE_TENNIS_ORDINI_VIA_CANALE` deve restare SPENTO. Nel runner tennis mancano:
1. **Il motore ordini.** `grep motore_ordini Betfair/stream/tennis_live/` dà 0 risultati:
   `/comando/safe_tennis` sul 47332 non ha nessuno che esegua (`motore_non_attivo`). Non
   montato, come da brief.
2. **Un aggancio a comando.** Safe tennis non scrive `tennis_live_follow`, quindi il suo
   mercato (il `mo_market_id` del feed, lo stesso MATCH_ODDS che il runner sottoscrive per
   partita) entra nello stream solo se la partita è già seguita (a mano o dal ponte).
   - Con questo lavoro l'ingresso non richiede più una ricostruzione.
   - Manca l'equivalente di `AutoFollow.richiedi` del calcio, cioè il motore che chiede il
     mercato con priorità «comando».
   - Il punto d'innesto c'è: `_allinea_follow_a_caldo`/`pianifica` accettano una voce in
     più. Servirebbero una priorità «comando» e un parcheggio del comando fino al primo book.
3. **Già a posto:**
   - il ref ha il prefisso dell'attore (`safe_tennis-t<id>`, F1 del 25/09);
   - la connessione unica e il tetto sono quelli di questo lavoro.

## 5. Test e falsificazione

**`test_tennis_iscrizione_a_caldo_2026_09_25.py`: 46 test, verdi.** Classi VERE:
- `Flumine` con il `BetfairClient` di `build_order_client` (PAPER o LIVE, più il client paper
  affiancato);
- capture `_make_capture` / `TennisRecMarketStream` / listener tennis;
- bot `_instantiate_bot`;
- `BetfairStream` di betfairlightweight: solo il socket è finto e registra i
  `marketSubscription`;
- mcm Betfair con il market definition completo;
- `Trade`/`LimitOrder`/`Blotter` di flumine per le posizioni abbinate.

Il ciclo di flumine è una pompa che passa gli eventi della `handler_queue` vera a
`_process_custom_event` vero. Il DB è un finto con le firme di `tennis_db` e le righe con le
chiavi di `tennis_live_follow` e `tennis_bot_control`.

Casi coperti:
- **Caso dell'utente.** Bot FLB con posizione abbinata sulla 101, follow 102 con pro
  richiesto:
  - nessun restart e nessuna terminazione, `framework_gen` invariato;
  - un `marketSubscription` con `["1.101","1.102"]` e id +1;
  - UNA sola MarketStream;
  - tutte le strategie sul nuovo `stream_id` e sul filtro nuovo;
  - pro armato nello stesso stream (`arming` → `running`), follow `STREAMING`;
  - l'FLB è la stessa istanza, non disabilitata, niente `force_flat`;
  - ordine ed esposizione nel blotter IDENTICI;
  - il book della 102 arriva sul nuovo id.
- **Per contrasto:** con l'interruttore spento la 102 non entra (il prima).
- Bot nuovo su una partita seguita: armato senza sottoscrizione.
- Disarmo senza restart.
- Riarmo dopo lo stop: istanza nuova, parametri nuovi.
- **Tetto:**
  - l'armata espelle la candidata;
  - la pari viene rifiutata e dichiarata;
  - mai oltre il tetto su nessun messaggio;
  - mai espulse la partita con posizioni o quella a mano;
  - la partita a mano espelle un'armata flat (bot `stopped` col motivo).
- **Uscita:**
  - il follow chiuso esce e disarma a flat;
  - con posizione resta, ed esce appena il lay pareggia;
  - la grazia protegge da una lettura a vuoto;
  - lista vuota → ricostruzione, mai un filtro vuoto.
- **Posizione aperta durante il catalogo:** ricontrollata nel ciclo di flumine; la partita
  resta e la nuova non sfora il tetto.
- **Paper/live:**
  - runner LIVE: riga paper instradata sul client simulato; riga live con `dry_run=False`
    esplicito → reale; riga live senza → dry-run;
  - impronta identica a un bot della build con la stessa riga;
  - runner PAPER con riga live → esecuzione PAPER.
- **Guardia d'avvio armata:** la partita entra, nessun bot si arma.
- **Robustezza e piano:**
  - stream non connesso: niente cambia, riprova;
  - ciclo di flumine fermo: lavoro annullato e mai eseguito dopo;
  - bot con data_filter o conflate diversi: rifiutato, nessuno stream o strategia spuria;
  - sottoscrizione vuota o oltre 200 rifiutata;
  - book della vecchia sottoscrizione scartato;
  - filtro canonico anche con la partita nuova che viene prima;
  - piano puro in 8 casi, tetto e interruttore parametrizzati, build dentro il tetto, e nessuna
    lettura in più sotto il tetto.

**Falsificazione** (`mutazioni_tennis_iscrizione_a_caldo.py`, esito in
`falsificazione_tennis_iscrizione_a_caldo.txt`): **22/22 mutazioni ROSSE**.
- Ripristino dai BYTE con sha1 verificato.
- Base verde, e verde dopo il ripristino.
- Nella prima passata erano cieche due mutazioni:
  - **M5 (filtro non ordinato):** era un doppio ordinamento ridondante. L'ordinamento è
    rimasto solo in `filtro_mercati`, e M5 ora è rossa.
  - **M9 (manuali espellibili):** è equivalente per priorità, perché la manuale è già la più
    alta. Sono stati aggiunti controlli diretti su `espellibile`, e M9 ora è rossa.

**Test dei file che importano il runner** (`Betfair/stream/tennis_live/tests` più i 6 di
`Betfair/stream/tests` che lo importano: contratto strada unica, ladder canale, registro bot,
saldo evento, stop framework, watchdog): **582 passed**. I 536 di prima sono invariati, più i
46 nuovi.

## 6. Replay (NON lanciati: comandi per il coordinatore, uno alla volta)

```
python -m Betfair.stream.backtest.certifica tennis_scalper --scenari tutti --worker 1
python -m Betfair.stream.backtest.certifica tennis_pro     --scenari tutti --worker 1
python -m Betfair.stream.backtest.certifica tennis_flb     --scenari tutti --worker 1
python -m Betfair.stream.backtest.certifica tennis_swing   --scenari tutti --worker 1
```

**Atteso:** esiti IDENTICI all'ultimo referto (22/22), stessi numeri scenario per scenario.
- Il replay usa dal runner solo `_instantiate_bot`, `_disable_strategy`,
  `_strategy_is_flat`, `TennisLiveSession` e `SCORE_POLL_SEC`/`BOT_CONTROL_POLL_SEC`: nessuna
  di queste funzioni è cambiata. `TennisLiveSession` ha solo attributi in più.
- **Cambia l'impronta `codice_bot`** del referto: `replay_bot.py:446` include
  `tennis_runner.py` nell'hash. È attesa e non è una regressione.

## 7. Non verificato

- **La risottoscrizione contro Betfair vero.** È provata con le classi vere su un socket
  finto, come il calcio. Da vedere dal vivo:
  - il SUB_IMAGE immediato;
  - la latenza;
  - la riconnessione di flumine con il filtro nuovo.
- **Scrittura sul socket SSL dal thread principale di flumine** mentre il thread di lettura
  di betfairlightweight legge. È lo stesso punto aperto del calcio.
- **Collisione di `stream_id`** dopo 9999 risottoscrizioni nella vita di un framework
  (flumine distanzia gli stream di 10000). Dichiarata, non gestita.
- **Le istanze disabilitate restano nel framework** (inerti: `check_market_book` è False)
  fino alla build successiva: il ricambio a vita massima, 18 h. Il costo è una chiamata per
  book per istanza. Non misurato su una giornata piena.
- **Il P&L regolato di un bot la cui partita esce** si scrive solo se lo specchio ordini
  (1 s) passa dopo la chiusura del mercato e prima dell'uscita. La grazia di 30 s lo copre,
  ma non l'ho osservato dal vivo.
- **`tennis_live_now`/ladder di una partita uscita** restano all'ultimo valore: il follow
  è CLOSED.
- **Race teorica.** Un ordine manuale della ladder inviato dal worker ordini fra il
  ricontrollo delle posizioni e la risottoscrizione, sulla stessa partita in uscita, nello
  stesso giro. La finestra è di microsecondi, dentro il ciclo di flumine; non coperta da un
  test.
- **Banco tennis.** Il replay non passa dal ponte né dal `follow_worker`/`bot_control_worker`:
  il ciclo di vita a caldo è coperto dai test unitari con classi vere, non da un banco
  end-to-end.
- **App vera, DB vero, paper dal vivo:** nulla eseguito.
