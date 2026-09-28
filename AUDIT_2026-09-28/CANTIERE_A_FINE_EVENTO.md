# CANTIERE A - FINE EVENTO (28/09/2026)

Delegato (Opus), worktree `agent-af90c02a50154f8d0`, base `2eb3c1d` (contiene `0dbc127` e `07bc872`).
Niente commit, niente DB (solo test con `SUPABASE_URL=http://127.0.0.1:9`), niente processi, niente replay.
Strategie NON toccate: nessuna soglia, stake, tetto, gamba, ingresso o uscita. Si tocca solo QUANDO una
partita smette di essere seguita.

> **Seconda tornata (dopo la verifica del coordinatore, 5 punti): vedi §9 in fondo.** I numeri
> aggiornati: test nuovi 46/46 (24 calcio+scalper, 22 tennis), regressione 1617 passed / 0 failed su
> 82 file (+43 passed sui test di contratto `test_contratto_strada_unica`/`test_registro_bot`, `-m "not
> cert"`), falsificazione **49/49 ROSSE**. Nel §1-§8 la regola 2 («catalogo vuoto = finita SUBITO») e'
> superata dal §9.1 (conferma + soldi dentro).

## 0. La regola (documentazione)

- Betfair, enum `MarketStatus`: **CLOSED = "The market has been settled and is no longer available for
  betting"** (INACTIVE/OPEN/SUSPENDED gli altri). https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687455
- `listMarketCatalogue`: "Returns a list of information about published (ACTIVE/SUSPENDED) markets";
  **"listMarketCatalogue does not return markets that are CLOSED"**.
  https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687517/listMarketCatalogue
- Stream API: i mercati chiusi restano nella cache/sottoscrizione e vengono sfrattati da un job ogni 5 min dopo
  **1 ora** da chiusi; alla ri-sottoscrizione i mercati chiusi non contano nel limite.
  https://support.developer.betfair.com/hc/en-us/articles/11741143435932-Are-closed-markets-auto-removed-from-the-Stream-API-subscription
- Non esiste uno "stato evento" nelle API: l'evento e' finito quando i suoi mercati sono CLOSED (settlement
  ~5 minuti dopo la fine; runner WINNER/LOSER da listMarketBook).
  https://support.developer.betfair.com/hc/en-us/articles/115003887731
- flumine 2.13.11 (`.venv`): un book CLOSED NON va a `process_market_book` (`baseflumine.py:157-159`,
  `CloseMarketEvent` + `continue`); va a `strategy.process_closed_market` (`:378-380`), `market.closed=True`
  (`markets/market.py:58-60`); il mercato resta in `markets.markets` 3600 s in live (`baseflumine.py:401-412`);
  un book successivo lo riapre (`:154` `elif market.closed: add_market`).

**Regola scelta** (verifica dell'ipotesi dell'utente):
1. Calcio (runner, sessione scalper) e tennis: partita FINITA = **MATCH_ODDS CLOSED oppure tutti i mercati
   seguiti CLOSED** (visti dallo stream). Il MO e' l'ultimo mercato dei 90' e tutti i mercati che i bot usano
   (MO, CS, OU, HT, BTTS) sono di 90': quando il MO chiude la partita e' finita per noi. L'ipotesi "tutti i
   mercati dell'evento chiusi" e' vera ma non osservabile dallo stream (sottoscriviamo un sottoinsieme); resta
   come secondo ramo.
2. Fuori dallo stream (riavvio, follow nuovo): **catalogo REST vuoto + partita gia' iniziata = finita**
   (catalogo vuoto = nessun mercato ACTIVE/SUSPENDED = tutti CLOSED). Un errore di rete non arriva mai come
   lista vuota (`Betfair/client.py:203-254` solleva; betfairlightweight solleva).
3. Casi limite: **SUSPENDED non e' mai fine** (gol, VAR, pioggia; sospensione lunga, partita rinviata:
   restano seguite finche' Betfair non chiude/annulla - annullata = CLOSED/void, quindi finita). Mercati che
   chiudono prima (HT, Over gia' deciso): escono dalla sottoscrizione singolarmente (auto-follow gia' lo
   faceva; ora anche i manuali), la partita resta seguita. Coppa con supplementari: MO chiude a 90', "To
   Qualify" continua: la partita e' finalizzata come prima (regola F4 esistente) ma il mercato ancora aperto
   RESTA sottoscritto finche' non chiude. Mercato che non arriva mai a CLOSED sullo stream (chiuso da ore
   quando lo si sottoscrive: Betfair non lo manda): auto-follow lo toglie dopo 120 s (`MAI_ARRIVATO_S`, ora
   valido anche dopo una ricostruzione); manuali: al riavvio regola 2.

## 1. Difetti trovati (causa radice, prova)

| # | Difetto | Causa (base 2eb3c1d) |
|---|---|---|
| A1 | Uscita ordinata del runner calcio (vita massima, stallo escluso, Ctrl+C, idle) chiudeva TUTTI i follow manuali (CLOSED + Replay caricato a meta'): il consolidato 26/09 "il finally del riavvio ordinato chiude i follow manuali" | `runner.py:2502-2511` finalize di ogni evento catalogato |
| A2 | Righe `origine='auto'` STREAMING restavano dopo l'uscita (R-28-3: 29 righe ad app spenta) | `runner.py` finally: `auto.ferma()` ma nessuna chiusura righe; si chiudevano solo al successivo avvio (`chiudi_orfani`) |
| A3 | `live_now` di una partita finita mai chiusa (26/09: 48 righe in-play dal 26/06) | `_finalize_event` (`runner.py:766-805`) scriveva solo `live_follow`; `score_worker` scriveva `inplay=true` anche da un book CLOSED (`:353-356`, flag dell'ultimo book) |
| A4 | Mercati di una partita manuale finita restavano sottoscritti e nel tetto dei 180 per tutta la vita del processo | `imposta_manuali` aggiornato solo alla ricostruzione; la ricostruzione usava `session.all_market_ids()` (finite comprese, `runner.py:2250`) |
| A5 | Follow manuale di partita finita (a runner riavviato) restava STREAMING/PENDING fino a 3 ore dopo il via, e nel frattempo il sub-worker lo ricontava come "nuovo" (ricostruzioni ripetute) | `_catalog_events` finalizzava solo se `_is_finished_stale` (3 h, `runner.py:1600`) |
| A6 | Dopo OGNI ricostruzione del framework l'auto-follow buttava fuori le partite automatiche sottoscritte da > 120 s (follow CLOSED, riaperto 30 s dopo dal feed) | `auto_follow.py:583-589` `aggancia` non azzerava `_inviato_ts`; `_pulisci` (`:829-833`) vede il mercato assente dal framework nuovo (immagine non ancora arrivata) con orario d'invio vecchio -> "mai arrivato". Mercati della build senza `_inviato_ts` invece non uscivano MAI |
| A7 | Sessione scalper viva su partita finita fino a KO+130' (sniper, default) o per sempre senza KO: connessione e posto del tetto (2 sessioni) occupati | `scalper_session.py` ciclo del battito: solo stop/freno/vita |
| T1 | Tennis: partita a MANO finita mai chiusa (follow STREAMING, bot armati a mano running) | 26/09 divergenza 3 lasciata all'utente; ponte `tennis_bot_service.py:554` escludeva le manuali |
| T2 | Tennis: partita automatica CLOSED non chiusa a scanner fermo | ponte: chiusure solo dentro `if feed["vivo"]` (26/09 divergenza 2) |
| T3 | Tennis al riavvio: partita finita ad app spenta -> relogin Betfair (1 login per partita finita) e follow ERROR, che `ensure_follows_for_bots` ricreava PENDING se una riga armata restava (giro ogni 15 s con catalogo REST + relogin) | `tennis_runner.py:639-652` |
| T4 | Tennis: riga armata su partita finita senza follow attivo -> 'stopping' eterno (nessun runner la ospita) | ponte (nessun ramo) |

## 2. Cosa ho cambiato (righe del worktree)

Calcio - runner (`Betfair/stream/runner.py`):
- `_finalize_event` (:777): dopo il CLOSED del follow -> `_chiudi_live_now_sicuro` (:825, UPDATE di `live_now`) e
  `_rilascia_mercati_finiti` (:887).
- `mercati_manuali_vivi` (:834): mercati manuali da tenere = partite non finite tutti; finite solo i NON chiusi
  (recorder). `_rilascia_mercati_finiti` li passa al piano dell'auto-follow (tetto) -> il thread
  dell'auto-follow risottoscrive A CALDO senza i chiusi. Chiamato anche a ogni giro di `finalize_worker` (:755)
  per i mercati che chiudono dopo (To Qualify).
- `mercati_manuali_da_sottoscrivere` (:863) usato alla ricostruzione (:2421): niente mercati di partite finite.
- `_finito_senza_mercati` (:1725) sostituisce la soglia 3 h in `_catalog_events` (:1762). `_is_finished_stale`
  resta definito (ora non usato).
- `chiudi_alla_uscita` (:902) nel `finally` (:2680): drena il recorder, finalizza le finite, rimette **PENDING**
  le vive; poi `auto.chiudi_righe()` (:2694). Vale anche per l'uscita per stallo (prima: nessun cambio di stato).
- `score_worker` (:340): `inplay` esclude i book CLOSED; non riscrive se l'evento e' stato finalizzato nel
  frattempo (race col finalize_worker).
- avvio: `_chiudi_live_now_orfani_all_avvio` (:873, chiamato a :2242).
Calcio - altri: `recorder.py:153` `mercati_chiusi(event_id)`; `db.py:331` `chiudi_live_now` (UPDATE + canale
`now`), `db.py:358` `chiudi_live_now_orfani`; `auto_follow.py:583` `aggancia` azzera l'orario d'invio,
`auto_follow.py:644` `chiudi_righe` (solo le righe scritte da lui, non quelle dello scalper).
Scalper (`scalper/scalper_session.py`): `partita_finita` (:380) + ramo nel battito (:1457), stessa uscita del
fine-vita (force-flat, attesa flat 30 s, dichiarazione non-flat, stato finale 'done' = non si riarma).
Tennis: `tennis_bot_service.py` lettura unica `stato_now` (:499, `_stato_now` :721) su follow + righe attive;
righe attive su partita finita -> 'stopping' (con follow attivo) o 'stopped' con `MOTIVO_PARTITA_FINITA` (senza)
(:561); nessun armamento su partite finite, a mano (:574) o dal feed (:604); follow finiti chiusi a righe ferme,
manuali compresi (:678); `ensure_follows_for_bots` non riapre le finite (:185). `tennis_runner.py`:
`MercatoNonInCatalogo` (:580), `_partita_iniziata` (:588), `_chiudi_follow_finito` (:603), ramo in
`_risolvi_follow` (:680: iniziata -> CLOSED senza relogin; futura -> strada di prima); pulizia
`tennis_live_now` orfane all'avvio (:2729). `tennis_db.py:295` `chiudi_tennis_now` (UPDATE; riga minima CLOSED
solo se assente), `:323` `chiudi_tennis_now_orfani`.

**File toccati**: `Betfair/stream/runner.py`, `auto_follow.py`, `db.py`, `recorder.py`,
`scalper/scalper_session.py`, `tennis_live/tennis_bot_service.py`, `tennis_live/tennis_runner.py`,
`tennis_live/tennis_db.py`; test esistenti adattati: `tests/test_stream_stallo_2026_09_26.py` (controllo di
sorgente del finally), `tests/test_scalper_freno_origine_2026_09_26.py` (3 rami non-flat invece di 2),
`tests/test_record_optin_2026_07_17.py` e `tests/test_punto6_b_...tennis_2026_09_25.py` (monkeypatch delle
nuove scritture DB), `tennis_live/tests/test_tennis_chiusura_2026_09_26.py`
(`test_ponte_la_seguita_a_mano_non_si_chiude` -> caso SUSPENDED; il caso CLOSED ora si chiude per ordine
dell'utente), `tennis_live/tests/test_tennis_auto_mode_2026_09_25.py` (`test_scanner_fermo_...` -> caso
SUSPENDED; il CLOSED ora chiude anche a scanner fermo).
**File nuovi**: `Betfair/stream/tests/test_fine_evento_2026_09_28.py` (15 test),
`Betfair/stream/tennis_live/tests/test_fine_evento_tennis_2026_09_28.py` (14 test),
`AUDIT_2026-09-28/falsifica_fine_evento.py`, `AUDIT_2026-09-28/patch_prima.diff`, questo referto.

## 3. Test e falsificazione

Comandi (radice del worktree, bash):
```
export SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_KEY=x
.venv/Scripts/python.exe -m pytest Betfair/stream/tests/test_fine_evento_2026_09_28.py Betfair/stream/tennis_live/tests/test_fine_evento_tennis_2026_09_28.py -q -p no:cacheprovider
.venv/Scripts/python.exe AUDIT_2026-09-28/falsifica_fine_evento.py          # opz.: codici, es. M17 T4
```
- Nuovi: 15 + 14 = **29 passed** (~1-10 s). Flumine VERO (paper, `_process_market_books`/`_process_close_market`,
  messaggi `mcm` Betfair con marketDefinition CLOSED e runner WINNER/LOSER) per runner, recorder e scalper.
- Regressione: 82 file di test che importano i moduli toccati (esclusi banco/replay: `test_backtest*`,
  `test_cert_banco`, `test_registro_bot`, `test_contratto_strada_unica`, `test_paper_live_stesso_processo`,
  `test_scalper_certificazione`) -> **1600 passed, 0 failed** in 89 s.
- Falsificazione: **27/27 mutazioni ROSSE** (M1-M17 calcio/scalper, T1-T10 tennis; elenco nello script). Prima
  tornata: M13 e M17 VERDI -> test rafforzati (MO chiuso con CS ancora aperto; finalize simulato DENTRO il giro
  del score_worker) e rilanciati ROSSI. Ripristino dai byte originali con sha256; `grep -c MUTAZIONE` = 0 su
  tutti i file; `git diff` identico a `patch_prima.diff` (cmp).

## 4. Migrazioni
Nessuna. Nessuna colonna nuova (live_now.status non ha CHECK; tennis_live_now idem).

## 5. Parita' paper/live
Nessun ramo per modalita': fine partita, rilascio dei mercati, righe di follow e `live_now` sono identici in
paper e live (stesso segnale dallo stream). Unica differenza di flumine: in paper `_remove_market(clear=False)`,
in live il mercato chiuso resta 3600 s; il codice legge `closed`/`status` in entrambi i casi (test sul client
paper; il caso live e' lo stesso attributo). La sessione scalper chiude con lo stesso ramo in paper e live.

## 6. Cosa NON ho fatto / NON verificato
- **R-28-3 ad app SPENTA non e' risolvibile dai processi Python**: `desktop/main.js:417-423` uccide i figli con
  `taskkill /T /F` (niente `finally`). Il mio codice chiude le righe alle uscite ORDINATE e al successivo avvio
  (auto: `chiudi_orfani`, gia' esistente; manuali: ricatalogate, finite -> CLOSED subito). Per zero righe
  STREAMING ad app spenta serve uno spegnimento ordinato da `main.js` (fuori perimetro): proposta nel §7.
- `chiudi_orfani` all'avvio resta SOLO con auto-follow acceso: renderlo incondizionato in OFF chiuderebbe le
  righe PENDING `origine='auto'` scritte dallo scalper, da cui dipende `live_now` letto dal suo watcher sniper.
  Non toccato. Nota: le righe PENDING dello scalper sono trattate dal runner come follow manuali (catalogo
  intero) - comportamento preesistente, fuori perimetro.
- Nessun replay (`certifica`): il banco NON esegue il ciclo di `run_session` dello scalper (registro_bot.py:186),
  quindi il ramo nuovo della sessione e' coperto solo da test (regola su flumine vero + cablaggio): ⊘ banco.
- Non verificato su Betfair vero: che il messaggio di chiusura arrivi sempre prima dello sfratto (1 h) anche
  dopo una riconnessione; che `listMarketCatalogue` con `marketIds` di un mercato appena chiuso risponda subito
  vuoto (documentato, non provato).
- Partita rinviata con mercati SUSPENDED per giorni: resta seguita (per regola) finche' Betfair non annulla.
- Il canale locale `now` riceve la riga CLOSED calcio solo se la riga esisteva (UPDATE che ritorna la riga).
- Watchlist (`resolve_and_register`) riscrive `status=PENDING` sui follow futuri a ogni giro: preesistente, non
  riguarda le finite (listEvents non restituisce eventi senza mercati aperti), non toccato.

## 7. Decisioni per l'utente
1. **Tennis a mano**: da oggi una partita seguita A MANO e FINITA (CLOSED) si chiude e i bot armati a mano su di
   essa vanno in chiusura a flat (il 26/09 era "da decidere"). L'ho applicato per il tuo ordine di oggi. Una
   partita a mano SOSPESA non si tocca mai.
2. **CLOSED a scanner fermo** (tennis): ora chiude (il CLOSED viene dallo stream del runner, non dallo scanner).
3. **Scalper**: una sessione (anche armata dalla card) termina 'done' quando Betfair chiude il MATCH_ODDS, invece
   di restare accesa fino a KO+130'. Nessuna decisione di trading cambia (a mercato chiuso non si puo' tradare).
4. **Spegnimento dell'app**: proposta (fuori perimetro, `desktop/main.js`): prima del `taskkill /F` mandare un
   arresto ordinato ai runner (o eseguire la chiusura "vive->PENDING, auto->CLOSED") con attesa di pochi secondi.

## 8. Controlli dal vivo in paper (prossimo avvio)
1. All'avvio, log runner calcio: "N righe live_now di partite non piu' seguite portate a CLOSED" (atteso ~48 la
   prima volta: le righe `inplay=true` con follow CLOSED/UPLOADED/ERROR); log tennis analogo. Query:
   `select count(*) from live_now n join live_follow f using(event_id) where (n.inplay or n.status<>'CLOSED') and f.status not in ('PENDING','STREAMING')` -> 0.
   Da solo il codice chiude: le `live_now`/`tennis_live_now` di follow non attivi; i follow manuali calcio e
   tennis di partite gia' iniziate e senza mercati in catalogo (CLOSED); le righe auto calcio (chiudi_orfani,
   come prima). NON chiude: follow attivi di partite ancora nel catalogo; righe `scalper_control` vecchie.
2. Partita calcio seguita a mano che finisce alle hh:mm: entro ~5 min Betfair chiude il MO; entro
   `LIVE_FINALIZE_POLL_SEC` (10 s) dal CLOSED: `live_follow.status=CLOSED`, `live_now.inplay=false,
   status='CLOSED'`; log auto-follow "sottoscrizione a caldo: ... -k" con k = mercati chiusi della partita.
3. Partita automatica calcio finita: riga `origine='auto'` CLOSED entro 1 giro dell'auto-follow dal CLOSED
   (log "non piu' seguito (mercati chiusi)"); `stato().mercati_seguiti` scende.
4. Dopo un ricambio del runner (vita massima o stallo): le partite manuali ancora vive tornano PENDING e poi
   STREAMING da sole; nessuna CLOSED; le automatiche NON escono subito dopo la ricostruzione (prima uscivano e
   rientravano 30 s dopo: nessun "ESPULSO"/"non piu' seguito (mercati chiusi)" nel minuto dopo il rebuild).
5. Tennis: partita finita (a mano o auto) -> `tennis_live_now` CLOSED (gia' dal 26/09), bot 'stopping' ->
   'stopped', follow CLOSED entro 2 giri del ponte (~30 s), mercato fuori dallo stream dopo la grazia.
6. Scalper: sessione su partita finita -> attivita' "partita finita (mercato Betfair CLOSED): fine sessione",
   `scalper_control.status='done'` entro `HEARTBEAT_S` dal CLOSED.

## 9. Seconda tornata - i 5 punti del coordinatore

### 9.1 MONEY-CRITICAL: catalogo vuoto, due guardie (calcio e tennis)
"Catalogo vuoto" non basta: con `LIVE_MARKET_TYPES` valorizzata puo' voler dire "nessun mercato dei tipi in
lista ancora aperto"; una risposta vuota anomala e' possibile. Ora una partita INIZIATA col catalogo vuoto
passa per `_valuta_catalogo_vuoto` (calcio, `runner.py:1853`) / `_valuta_catalogo_vuoto_tennis`
(`tennis_runner.py:658`), esiti `in_conferma` | `trattenuta` | `finita` (solo l'ultimo ritira):
- **(a) CONFERMA**: alla prima lettura vuota si annota l'orario e basta; si ritira solo a una SECONDA lettura
  vuota fatta almeno `FINE_CONFERMA_S` = **120 s** dopo (`runner.py:1794`, env `LIVE_FINE_CONFERMA_S`; tennis
  `tennis_runner.py:622`, `TENNIS_FINE_CONFERMA_S`). Perche' 120 s: Betfair regola il MO ~5 min dopo la fine,
  quindi una fine vera resta vuota per sempre e 2 min in piu' non costano; un vuoto anomalo isolato non si
  ripete a 2 minuti di distanza; con il mercato sottoscritto lo stream porta comunque il CLOSED da solo.
  Un catalogo tornato pieno annulla la conferma. Niente ricostruzioni in loop durante l'attesa: la partita
  in conferma/trattenuta NON e' "nuova" per il sub-worker (`runner.py:1124`); la rilegge `_ricontrolla_fine`
  (`:1894`, dal sub-worker `:1011`) solo al suo momento, SENZA ricostruire lo stream. Tennis:
  `fine_da_rileggere` (`:645`) evita la chiamata REST prima del momento e la ricostruzione nel follow_worker
  senza iscrizione a caldo (`:2595`).
- **(b) SOLDI DENTRO**: alla lettura confermata, con denaro sull'evento la partita NON si ritira: resta com'era
  (PENDING/STREAMING), alert `CRITICAL FINE_PARTITA_CON_SOLDI` UNA volta, ricontrollo ogni
  `FINE_RIVERIFICA_SOLDI_S` = 300 s; si ritira quando il denaro non c'e' piu'. Fonti, paper E live:
  calcio `db.soldi_sull_evento` (`db.py:390`): `betfair_live_orders` in stato vivo
  (PENDING/EXECUTABLE/CANCELLING/UPDATING/REPLACING); `betfair_live_positions` con esposizione aperta
  (abbinata non pareggiata o non abbinata) SENZA regolazione nella stessa modalita' in `betfair_live_settled`;
  `betfair_live_order_requests` pending/processing sui mercati dell'evento (`live_markets`); piu' i comandi
  PARCHEGGIATI nel motore ordini in RAM (`_soldi_sull_evento`, `runner.py:1832`). Tennis
  `tennis_db.soldi_sull_evento_tennis` (`tennis_db.py:323`): `tennis_live_orders` vivi,
  `tennis_live_positions` aperte, `tennis_live_order_queue` pending/processing sul suo mercato. Lettura KO =
  "denaro non verificabile" = trattenuta (mai al buio). Il blotter flumine non serve qui: il catalogo si
  legge solo a framework ricostruito (a flat, `_lifecycle_blockers`) o all'avvio, quindi il denaro sta nello
  specchio.
- Limite dichiarato: il tennis non ha tabella di regolazione; un'esposizione rimasta sullo specchio tiene la
  partita "trattenuta" (con un alert) finche' lo specchio non la azzera.
- Test: 7 calcio + 5 tennis; mutazioni G1-G13 ROSSE.

### 9.2 `mercati_manuali_vivi` con recorder illeggibile
Test `test_recorder_illeggibile_non_rilascia_niente` (se `mercati_chiusi` solleva si tengono TUTTI i
mercati; recorder assente idem). Mutazione P2 (`chiusi = set(tenuti)` nel ramo d'errore) ROSSA. La mutazione
del coordinatore probabilmente non si applicava per l'indentazione del `try` annidato (`runner.py:852-858`).

### 9.3 `live_now` di eventi senza follow
- `live_now.event_id` e' FK su `live_follow(event_id)` (`migrations/live_stream.sql:60`),
  `tennis_live_now.event_id` su `tennis_live_follow` (`migrations/tennis_live.sql:57-58`): una riga senza
  follow non puo' esistere.
- Scrittori di `live_now` in Python: solo `db.update_live_now` (`db.py:302`, runner) e le due funzioni nuove.
  Lettori, tutti per `event_id`, in sola lettura: `omega/omega_db.py:585-602` (`read_live_now`),
  `stream/live_order_worker.py:1102-1110`, `scalper/scalper_session.py:1104` (watcher HT), `:1219` e `:1261`
  (watcher sniper). Nessuno scrive `live_now`.
- Comunque RISTRETTO: la pulizia chiude solo le righe con un follow LETTO in stato terminale
  (CLOSED/UPLOADED/ERROR: `db.py:439`, `tennis_db.chiudi_tennis_now_orfani`). Test con una riga senza follow
  letto (non toccata); mutazioni P3, P3b, M9, T10 ROSSE. Effetto sui lettori: `minute`/`score_*`
  conservati (UPDATE di `inplay`/`status` soltanto).

### 9.4 Spegnimento ordinato
Specifica per `main.js`: `AUDIT_2026-09-28/SPEC_SPEGNIMENTO_ORDINATO.md` (file `ARRESTO`, attesa massima
25 s dei due runner, poi `taskkill`; stato atteso sul DB: 0 STREAMING, vive PENDING, automatiche CLOSED).
Lato Python realizzato: `Betfair/stream/arresto_ordinato.py` (NUOVO; file ignorato se piu' vecchio
dell'avvio), `arresto_worker` nei due runner (`runner.py:1641`, `tennis_runner.py:1956`, ogni 1 s) + controllo
in cima al ciclo (`runner.py:2487`, `tennis_runner.py:2892`) -> exit 0 (watchdog 'clean', nessun rilancio).
Tennis: nuovo `chiudi_alla_uscita_tennis` nel `finally` (`tennis_runner.py:1969`, `:3155`): finite CLOSED,
automatiche CLOSED solo all'arresto dell'app (al ricambio del processo PENDING), le altre PENDING. Calcio:
`chiudi_alla_uscita` rimette PENDING anche le partite in conferma/trattenute. Mutazioni A1-A6 ROSSE.
NON verificato con un processo vero (nessun processo lanciato, per brief).

### 9.5 Per chi fa il rebase del cantiere B (piu' connessioni di mercato)
1. **Ricostruzione** (`setup_and_run`, `runner.py:2597-2606`): NON usare `session.all_market_ids()`. I
   mercati manuali sono `mercati_manuali_da_sottoscrivere(session)` (`runner.py:864`, esclude le finite); il
   PRIMO frammento (e ogni frammento) si calcola dall'unione `mercati_manuali_da_sottoscrivere(session) |
   auto.mercati_da_sottoscrivere()` DOPO `auto.imposta_manuali({ev: ms ... if ev not in
   session.finished_events})` e `auto.rientra_nel_tetto()`.
2. **A caldo**: i manuali del piano li aggiorna `_rilascia_mercati_finiti` (`runner.py:888`) con
   `mercati_manuali_vivi(session)` (`:835`), da `_finalize_event` e a ogni giro di `finalize_worker`. Con un
   piano/tetto PER connessione questa chiamata deve alimentare lo stesso piano (o ripartire i manuali), o i
   mercati chiusi restano nel tetto.
3. **`AutoFollow.aggancia`** (`auto_follow.py:583-602`): non perdere `for mid in self._applicati:
   self._inviato_ts[mid] = ora`. Con piu' connessioni ogni aggancio azzera l'orario d'invio dei mercati
   INIZIALI del suo frammento senza toccare `_applicati` degli altri; senza, dopo ogni ricostruzione le
   partite automatiche escono come "mai arrivate" (difetto A6 del §1, test
   `test_dopo_la_ricostruzione_i_mercati_automatici_non_sono_mai_arrivati`).
4. **Recorder**: `mercati_manuali_vivi`, `chiudi_alla_uscita` e `finalize_worker` leggono `session.recorder`
   (`mercati_chiusi`, `drain_finished`): con un recorder per connessione vanno uniti su tutti.
5. Nel `finally` restano `chiudi_alla_uscita(session)` e `auto.chiudi_righe()`; `arresto_worker` va
   registrato su ogni framework (o su uno solo se `_stop_framework` li ferma tutti).

### 9.6 Numeri e file della seconda tornata
- Nuovi: `test_fine_evento_2026_09_28.py` 24, `test_fine_evento_tennis_2026_09_28.py` 22 -> **46 passed**.
- Regressione: 82 file (quelli che importano i moduli toccati, esclusi banco/replay) **1617 passed, 0
  failed** (111 s); `test_contratto_strada_unica` + `test_registro_bot` con `-m "not cert"` 43 passed.
- Falsificazione: `falsifica_fine_evento.py` (49 mutazioni; eseguibili anche per codice, es. `... G1 A6`).
  Tornata completa in `AUDIT_2026-09-28/falsifica_esito.txt`: 46/48 ROSSE e 2 "non applicabili" (M9/T10:
  l'ancora era il codice prima del §9.3); ancore aggiornate e rilanciate M9, T10, A6 (nuova), M6, M7:
  5/5 ROSSE. Totale **49/49 ROSSE**. Ripristino byte per byte, `git diff` = `patch_prima.diff` (cmp).
- File in piu': `Betfair/stream/arresto_ordinato.py` (NUOVO), `AUDIT_2026-09-28/SPEC_SPEGNIMENTO_ORDINATO.md`
  (NUOVO); modificati di nuovo `runner.py`, `db.py`, `tennis_live/tennis_runner.py`, `tennis_live/tennis_db.py`.

### 9.7 Controlli dal vivo aggiuntivi
- Partita finita ad app spenta: al riavvio log "catalogo vuoto (prima lettura)", ~120 s dopo "confermato
  ... -> finita". Con posizione aperta sullo specchio: alert `FINE_PARTITA_CON_SOLDI`, la partita resta seguita.
- Dopo l'integrazione in `main.js`: 0 righe STREAMING ad app chiusa (query in SPEC §3).
