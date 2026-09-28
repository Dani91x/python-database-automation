# CANTIERE I - Sanatorie SQL e posizione fantasma 14265 (28/09/2026)

Delegato I (Sonnet), sola lettura sul checkout principale. Nessun file toccato fuori dal
perimetro della consegna. Nessuna scrittura sul DB: SOLO `SELECT`/`EXPLAIN` e catalogo
`pg_*`/`information_schema` sul progetto Supabase `dqbwaocvlzbxfrpacsac`. Strumento SQL
disponibile: `mcp__plugin_supabase_supabase__execute_sql` (via il plugin Supabase) - nessuna
voce e' rimasta senza verifica per mancanza di strumento.

**REVISIONE (28/09, dopo la verifica indipendente del coordinatore)**: 8 sezioni su 9 del
primo giro sono state confermate dai conteggi indipendenti del coordinatore. UNA era
sbagliata (1.6 sotto, `tennis_live_now`: 30 righe, non 31 - errore mio di conteggio a mano,
il dato non era cambiato). Corretti anche, su richiesta del coordinatore: (a) tutte le
guardie da "esattamente N" a "al massimo N" (tetto, non uguaglianza: vedi 4 sotto), (b)
aggiunta una sezione per 6 proposte Safe di `cashout` su partite finite (nuova 1.9), (c)
verificato nel codice se `status='CLOSED'` e' un valore che il runner scrive davvero su
`live_now`/`tennis_live_now` prima di scriverlo di mia iniziativa (nuovo dettaglio in 1.4 e
1.6). Questa versione del referto e del file SQL e' quella corretta.

Fonti lette per intero prima di lavorare: `BRIEF_STANDARD_DELEGATI.md`, `CLAUDE.md`,
`CRONOSTORIA.md` (sezioni 2026-09-26 e 2026-09-28), `AUDIT_2026-09-26/FIX_SCALPER_E_PAPER_
FILL.md`, `AUDIT_2026-09-26/FIX_UI_PAGINE_ADMIN26.md`, `migrations/PROPOSTA_pulizia_
posizione_fantasma_14265_2026-09-26.sql`, le 5 migrazioni del 26/09, le due migrazioni
`*_SOLO_SE_MANCANO_2026-09-25.sql`, `migrations/analytics_signals_kickoff_pulizia_2026-09-
26.sql`. Skill `supabase:supabase-postgres-best-practices` caricata.

## Consegna

- `migrations/sanatorie_2026-09-28.sql` - 10 sezioni, ognuna in una transazione propria
  (begin/commit indipendenti, idempotenti, guardie a TETTO), + 3 note finali senza azione SQL.
- Questo referto.

## 1. Causa radice di ogni voce, con prova

### 1.1 Posizione fantasma 14265 (`betfair_live_positions`)

**Prova**: `id 14265, mode live, event 35797769, market_id 1.259819675, selection 5851482,
selection_exposure 4.40, net_position -5.00, updated_at 2026-07-10 19:29:57Z`, in join con
`betfair_live_settled id 18, settled_at 2026-07-10 19:31:29Z, profit 105.0, mode live` sullo
stesso `market_id`. Il runner scrive le posizioni ma non le toglie alla regolazione (causa
identificata dal delegato del 26/09 in `FIX_A_SOLDI_MODALITA_2026-09-26.md`, KO4).

**Verificato di persona il 28/09** (query eseguite, non ripetute dal referto del 26/09):
- E' l'UNICA riga di `betfair_live_positions` con una regolazione nella stessa modalita' in
  `betfair_live_settled` (join dei due, 1 riga sola, sempre 14265). Totale righe
  `betfair_live_positions`: 2 paper + 1 live (proprio 14265).
- Nessun vincolo FK in tutto il DB referenzia `betfair_live_positions` (`pg_constraint` con
  `confrelid = 'public.betfair_live_positions'::regclass AND contype='f'`: 0 righe).
- La pagina `/live-pnl` e' GIA' corretta alla fonte da `get_live_positions_all()`
  (`migrations/live_positions_senza_mercati_regolati_2026-09-26.sql`, applicata secondo il
  coordinatore): questa sanatoria e' SOLO igiene della tabella, non necessaria per la UI.

**Conclusione**: la `PROPOSTA_pulizia_posizione_fantasma_14265_2026-09-26.sql` esistente e'
CORRETTA (guardie strette su id+mode+market_id+EXISTS sul settled) e tocca SOLO quella riga.
Ripresa nella sezione 1 del file consolidato con una sola modifica: il conteggio atteso da
`v_n <> 1` a `v_n NOT IN (0,1)` per renderla idempotente a un secondo lancio (il file va
incollato una volta, ma se l'utente lo rilanciasse per errore non deve fallire).

### 1.2 `live_follow` scalper senza `origine='auto'` (26/09)

**Causa** (da `FIX_SCALPER_E_PAPER_FILL.md` p.2, gia' corretta nel codice): `scalper_
service.py` upsertava il follow SENZA la chiave `origine`, che quindi restava sul default
`'manuale'` della migrazione `live_follow_origine_2026-09-25.sql:30`.

**Verificato a DB il 28/09** (finestra esplicita 2026-09-26 00:00-24:00 Europe/Rome, NON
"oggi": oggi e' il 28/09): 9 righe, tutte `status='CLOSED'`, `origine='manuale'`, senza
`fixture_id`/`watchlist_id`/`record`, ciascuna con un evento `auto_armata` in
`scalper_activity` entro 1 minuto dalla creazione del follow (stessa condizione della query
gia' scritta dal delegato del 26/09, solo con la finestra di data esplicita invece di
`date_trunc('day', now())`). Event_id: 36090788, 36090854, 36090936, 36090937, 36090941,
36111764, 36111770, 36109062, 36111427.

### 1.3 R-28-3 (calcio): `live_follow` `origine='auto'` ancora `STREAMING` ad app spenta

**Causa**: l'app e' spenta dal 26/09 ~19:40 (PC) - confermato dal coordinatore nello stato di
partenza del 28/09 (0 processi python, 0 porte 47330-47338). Il codice che chiude gli orfani
al riavvio (`auto_follow.FollowDb.chiudi_orfani`, citato in `FIX_SCALPER_E_PAPER_FILL.md`
p.1 "rischi residui") gira SOLO all'avvio del runner: non e' mai girato perche' l'app non e'
stata riavviata.

**Verificato a DB il 28/09**: 29 righe `origine='auto' AND status='STREAMING'`, `created_at`
tra le 15:55:30Z e le 17:38:36Z del 26/09, `updated_at` mai oltre le 17:38:36Z (nessun
aggiornamento da quando l'app e' spenta: prova che nessun processo le sta davvero seguendo).

### 1.4 `live_now`: righe "in-play" mai ripulite dal 26/06

**Causa**: nessun processo azzera `live_now.inplay` quando il `live_follow` collegato si
chiude (CASCADE su DELETE, non su UPDATE di stato: `migrations/live_stream.sql:60`).

**Verificato a DB il 28/09**: 50 righe con `inplay=true`, `updated_at` dal 2026-06-26
13:36:45Z al 2026-09-26 16:54:19Z (distribuzione per giorno nel referto interno). TUTTE e 50
hanno il `live_follow` collegato in stato TERMINALE (`CLOSED` o `UPLOADED`): nessuna e'
legata a un follow ancora `STREAMING`, quindi nessuna e' una partita davvero in corso.

**`status` NON toccato (verifica chiesta dal coordinatore, file:riga)**: il runner calcio
scrive SOLO `'OPEN'` o `'SUSPENDED'` su `live_now.status`
(`Betfair/stream/runner.py:365-368` e `:392`: `db.update_live_now(event_id, ...,
status="OPEN" if inplay else "SUSPENDED", ...)`); `'CLOSED'` non e' MAI prodotto dal runner
calcio su questa tabella (e' scritto solo su `live_follow.status`, via `_safe_set_status`,
`runner.py:774`, tabella diversa). Letto anche il lato consumo: `MarketWatch.tsx:139-141` e
`:437` usano `now.inplay` per il badge LIVE, non `now.status`; nessuna occorrenza di
`live_now.status` di primo livello ne' in `MarketWatch.tsx` ne' in
`useControlRoom.ts` (`state.markets[].status`, letto a `MarketWatch.tsx:140`, e' un campo
DIVERSO: lo stato del singolo mercato Betfair dentro il JSON `state`, non la colonna
`live_now.status`). Scrivere `'CLOSED'` qui sarebbe un valore che il codice di produzione
non produce mai: la sezione 4 azzera SOLO `inplay`, `status` resta com'e'.

### 1.5 Equivalente tennis di 1.3: `tennis_live_follow` ancora `STREAMING`

**Verificato a DB il 28/09**: 4 righe (`36117569, 36117343, 36117739, 36117538`), `created_at`
tra le 16:06:29Z e le 17:05:17Z del 26/09, `updated_at` mai oltre le 17:23:39Z. Stessa causa
di 1.3 (app spenta, nessun riavvio del servizio tennis dopo).

### 1.6 Equivalente tennis di 1.4: `tennis_live_now` in-play orfane

**CORREZIONE (28/09, dopo la verifica indipendente del coordinatore)**: il primo giro di
questo referto diceva "31 righe; 28 con follow gia' CLOSED/ERROR". ERRATO: la query non e'
cambiata e il dato sul DB non e' cambiato, l'errore era mio, nel contare a mano l'elenco
restituito dalla query invece di far contare `count(*)` al DB. Ricontato con `count(*)` e
riverificato riga per riga il 28/09: sono **30** righe `inplay=true` in totale (non 31), di
cui **3** con `tennis_live_follow.status='CLOSED'`, **24** con `status='ERROR'` (27 gia' con
follow terminale, non 28) e **3** (`36117569, 36117343, 36117739`) con follow ancora
`STREAMING` - le stesse 3 chiuse dalla sezione 5 del file: dopo quella sezione, tutte e 30
rientrano nella guardia della sezione 6. Una quarta riga `STREAMING` in
`tennis_live_follow` (`36117538`) non ha alcuna riga in `tennis_live_now`: nessuna azione
necessaria per quella. La guardia della sezione 6 nel file e' stata corretta a tetto 30.

**`status='CLOSED'` scritto QUI (a differenza di `live_now`/sezione 4), con prova
file:riga**: il runner TENNIS scrive davvero `'CLOSED'` come stato terminale di
`tennis_live_now.status`:
- `Betfair/stream/tennis_live/tennis_runner.py:416-431`, `process_closed_market` (fix
  R-FA-1 del 26/09): quando flumine chiude un mercato, scrive `rec["status"] = "CLOSED"` nel
  record che finisce in `tennis_live_now`.
- `tennis_runner.py:554-557` (commento + `self.now_chiusi`): *"eventi con
  `tennis_live_now.status='CLOSED'` gia' scritto (stato terminale: non si riscrive, NON si
  svuota a `reset_streams`)"* - il codice tratta esplicitamente `'CLOSED'` come valore noto e
  definitivo, gia' prodotto e gia' consumato in produzione.
Scrivere `'CLOSED'` in questa tabella e' quindi coerente con cio' che il runner tennis
produce da solo, a differenza del caso calcio (1.4): qui la sezione 6 azzera `inplay` E
imposta `status='CLOSED'`.

**Nota per il cantiere che tocca il codice (non questo)**: la stessa causa di 1.4/1.6 per il
LATO CALCIO (nessun azzeramento di `inplay` alla chiusura del follow, e nessuna scrittura di
uno stato terminale su `live_now.status`) e' un difetto ricorrente, non corretto qui (fuori
perimetro: qui si sanano i dati, non si cambia codice di produzione). Il lato tennis ha gia'
la propria correzione di codice (R-FA-1, 26/09): resta solo la sanatoria dei dati vecchi,
fatta qui.

### 1.7 `mike_trades` "ingresso None-None" (F-5)

**Causa** (gia' corretta nel codice, `Betfair/mike/service.py:522-533`,
`_punteggio_ingresso`): la f-string `f"{casa}-{ospiti}"` senza guardia scriveva la stringa
letterale `'None-None'` in `mike_trades.score_at_entry` quando i punteggi mancavano
(pre-partita). Il commento nel codice vivo lo dichiara esplicitamente come reperto F-5 gia'
risolto "da qui in avanti"; le righe scritte PRIMA restano sporche.

**Verificato a DB il 28/09**: 456 righe (407 `paper` + 49 `live`) con
`score_at_entry = 'None-None'` esatto, `placed_at` dal 2026-09-11 14:06:34Z al 2026-09-26
15:18:51Z. Nessuna altra variante sporca (`ILIKE '%none%'` da' lo stesso totale: 456, tutte
la stringa esatta). Campo puramente informativo: "nessuna decisione di Mike legge questo
campo" (commento nel codice, confermato leggendo `service.py` e `engine.py`: non e' letto in
nessuna condizione di trading).

### 1.8 Proposte Safe scadute ancora `proposed` (F-6)

**Causa**: la UI/servizio decade le proposte `kind='place'` piu' vecchie di 12 ore SOLO se il
servizio e' vivo (`Betfair/safe_strategy/bot_db.py:759`, `scadi_proposte_opportunita`, gia'
in produzione dal 26/09: F-6). Con l'app spenta dal 26/09 19:40 la funzione non gira dal
primo ciclo utile.

**Verificato a DB il 28/09**: 17 righe `kind='place' AND status='proposed' AND created_at <
now()-12h`, id 291, 292, 295, 297, 303, 304, 305, 306, 307, 308, 310, 312, 313, 314, 316,
317, 322; tutte `created_at` il 2026-09-26 tra le 16:15:35Z e le 17:34:49Z; `result` NULL su
tutte quelle controllate (nessuna perdita di dati sovrascrivendo `result`). **La #257 del
24/09 citata nel brief e' GIA' risolta**: `status='rejected'`, `updated_at` 26/09 14:43:49Z
(corretta dal delegato UI del 26/09, `FIX_UI_PAGINE_ADMIN26.md`) - non e' nell'elenco.

**Le 6 proposte Safe di `cashout` scadute** (viste nel primo giro e lasciate fuori) sono ora
sanate a parte nella sezione 1.9, su richiesta esplicita del coordinatore, con una prova per
riga invece di un pattern generico: la funzione di produzione `scadi_proposte_opportunita`
decade SOLO `kind='place'` (il `cashout` non decade mai da solo), quindi qui non basta
l'eta' - serve la prova che la partita sia davvero finita, verificata riga per riga.

### 1.9 Proposte Safe di CASHOUT su partite finite (id 311, 315, 318, 319, 320, 321)

**Causa**: 6 proposte `kind='cashout' AND status='proposed'`, tutte `payload.mode='paper'`,
`created_at` il 26/09 tra le 16:54:19Z e le 17:33:25Z (piu' vecchie di 12 ore oggi). Il
servizio Safe non le decade mai per eta' (`scadi_proposte_opportunita`,
`Betfair/safe_strategy/bot_db.py:759`, filtra `kind='place'`): restano `proposed` per
sempre, con il pulsante "Piazza" attivo, anche se la partita e la posizione a cui si
riferiscono sono finite da giorni. **Questo e' un difetto di CODICE aperto, non corretto
qui** (sola lettura): segnalato per il cantiere che tocca Safe.

**Verificato a DB il 28/09, riga per riga (come chiesto)**, la prova PIU' SOLIDA disponibile
per ciascuna delle 6:

| id | sport | event_id | trade collegato | prova |
|---|---|---|---|---|
| 311 | calcio | 36107016 | `safe_strategy_trades.id=354` | `status='lost'`, **settled_at 2026-09-26 17:31:50Z** - posizione REGOLATA |
| 315 | tennis | 36117452 | `safe_strategy_trades.id=350` | `status='won'`, **settled_at 2026-09-26 17:16:05Z** - posizione REGOLATA |
| 318 | calcio | 35926090 | `safe_strategy_trades.id=359` | trade ancora `status='open'` (nessun settlement) - prova: evento nella lista dei 29 `live_follow` STREAMING chiusi dalla sezione 3 |
| 319 | calcio | 35925583 | `safe_strategy_trades.id=363` | idem: trade `open`, evento nella lista della sezione 3 |
| 320 | calcio | 36090836 | `safe_strategy_trades.id=361` | idem: trade `open`, evento nella lista della sezione 3 |
| 321 | calcio | 36114311 | `safe_strategy_trades.id=362` | idem: trade `open`, evento nella lista della sezione 3 |

Per 318/319/320/321 il TRADE resta `open` (nessuna regolazione scritta in tabella): la
sanatoria non lo tocca, chiude SOLO la proposta scaduta. Rifiutare una proposta vecchia di
un'uscita non chiude la posizione: toglie solo un pulsante "Piazza" su un suggerimento non
piu' attuale (la partita e' finita, per football una partita non dura 2 giorni: il tempo
reale trascorso dal 26/09 al 28/09 e' di per se' prova che l'evento e' concluso, oltre alla
prova a DB). Il trade `open` senza regolazione e' materia del cantiere Safe/parita', non di
questa sanatoria.

**Condizione nel file** (sezione 9, DOPO le sezioni 3 e 5 per dipendenza): `id IN (311, 315,
318, 319, 320, 321) AND kind='cashout' AND status='proposed' AND created_at < now()-12h AND
(trade.settled_at IS NOT NULL OR live_follow.status='CLOSED' OR
tennis_live_follow.status='CLOSED')` - un OR delle tre prove, cosi' la stessa condizione vale
sia per 311/315 (prova diretta, gia' vera oggi) sia per 318-321 (prova indiretta, vera dopo
la sezione 3). Marca identica alle altre sanatorie: `rejected` + `result.decaduta`.

### 1.10 `analytics_signals` / `analytics_decisions`: kickoff sporco

**Causa** (dal referto E2E fase 3 sessione B, corretta a monte nel codice):
`merge_engine_signals.py` e `build_analytics_signals.py` scrivevano il kickoff
dall'istantanea di `engine_signals`/dalla data PROGRAMMATA di `fixture_predictions`, non
dalla riga vera di `matches` - una partita rinviata restava con la data vecchia.

**Messaggio del coordinatore (verificato di persona, riportato qui perche' cambia la
diagnosi rispetto al referto del 26/09)**: `migrations/analytics_signals_kickoff_pulizia_
2026-09-26.sql` e' una PROPOSTA con la CORREZIONE COMMENTATA; il 26/09 e' stata eseguita
SOLO la diagnosi. Il 28/09 la diagnosi da' numeri piu' alti di quelli del 26/09 (778 partite
/ 33.251 righe in `analytics_signals`, 402 partite / 6.278 righe in `analytics_decisions`,
contro 255/14.034 e 511 righe su una finestra di 60 giorni il 26/09): la finestra piu' ampia
(tutta la tabella, non 60 giorni) spiega la differenza, non una regressione del fix. Il
coordinatore ha inoltre confermato in modo indipendente la STABILITA' del fix: 84.535 righe
create dal 27/09 in avanti, 0 sporche; le ultime righe sporche risalgono al 24/09 (prima del
fix a monte), nessuna sporca creata dopo.

**Verificato di persona il 28/09 che il fix a monte e' su master e usato dal job** (altrimenti
la correzione qui sotto verrebbe disfatta dal prossimo giro):
- `merge_engine_signals.py:157` (radice del repo): `kickoff = (match or {}).get("fixture_date") or es.get("kickoff")`
- `build_analytics_signals.py:241` (radice del repo): `"kickoff": (match or {}).get("fixture_date") or fp.get("fixture_date")`
- entrambi richiamati da `.github/workflows/predictions_results_backfill.yml` (grep
  positivo sul file).
- `git rev-parse HEAD` sul checkout principale = `2eb3c1d`, uguale al master verificato dal
  coordinatore all'inizio della sessione del 28/09: i file letti sono quelli di master, non
  di un worktree.

**Conclusione**: la sezione 10 del file scrive la CORREZIONE VERA (non commentata), in
transazione, con conteggio prima (sopra) e controllo dopo (deve dare 0 e 0, altrimenti
ROLLBACK per eccezione), seguita da `select public.refresh_analytics_riepilogo();` fuori
dalla transazione (aggiorna anche i riepiloghi letti da `get_analytics`/`get_decisions`,
altrimenti resterebbero con i vecchi numeri finche' non gira il job delle 03:23 UTC). Questa
sezione non ha un tetto sul numero di righe (l'`UPDATE` corregge tutte le righe sporche
trovate al momento, non un elenco fisso di id): la garanzia e' il controllo "dopo", che deve
dare zero su entrambe le tabelle o va in `ROLLBACK` automatico.

## 2. Cosa ho cambiato e perche' - elenco esatto dei file

**File nuovi** (nessun file esistente toccato):
- `migrations/sanatorie_2026-09-28.sql` (consegna)
- `AUDIT_2026-09-28/CANTIERE_I_SANATORIE_SQL.md` (questo referto)

Nessun altro file toccato. Nessun codice di produzione modificato (i fix di F-5/F-6/scalper
sono GIA' in produzione, verificati leggendo il codice: qui si sanano solo i dati vecchi).

## 3. Test / verifiche eseguite

Nessun test automatico applicabile (lavoro di sola lettura su DB + scrittura di file SQL/MD).
Falsificazione sostituita da: per ogni voce, la query di conteggio e' stata eseguita PRIMA
(riportata sopra e nei commenti del file SQL) e la condizione dell'UPDATE/DELETE nel file e'
ESATTAMENTE la stessa usata per il conteggio (nessuna condizione piu' larga scritta "per
sicurezza" e poi ristretta nei commenti). Il file non e' stato eseguito (SOLA LETTURA
tassativa): la certificazione che l'esecuzione dia i numeri scritti spetta a chi lo applica
(l'utente) e a chi rilegge (il coordinatore), con la query di controllo "DOPO" incorporata in
ogni sezione (si auto-verifica: se il residuo non e' zero la sezione fallisce da sola con
`RAISE EXCEPTION` e va in ROLLBACK).

## 4. Migrazioni SQL scritte (NON applicate) e ordine

Un solo file, `migrations/sanatorie_2026-09-28.sql`, 10 sezioni indipendenti (ognuna
begin/commit propria) piu' 3 note. Ordine di incollaggio: come scritto nel file (1->10); le
sezioni 4 e 6 vanno dopo le sezioni 3 e 5 rispettivamente, la sezione 9 (cashout) va dopo le
sezioni 3 e 5 (dipendenza logica, spiegata nei commenti), le altre sono indipendenti tra
loro. Tutte idempotenti: un secondo incollaggio dopo un'esecuzione riuscita non tocca piu'
nulla (i controlli "dopo" tornano zero anche alla seconda esecuzione).

**GUARDIE A TETTO (corretto su richiesta del coordinatore)**: nel primo giro ogni sezione
falliva se il numero di righe toccate non era ESATTAMENTE quello verificato (`v_n NOT IN (0,
N)`). Difetto: se l'utente accende l'app prima di incollare il file, la pulizia automatica
del codice di produzione (`chiudi_orfani`, `avvio_app`, `scadi_proposte_opportunita`) puo'
aver gia' ridotto alcune di queste righe - un bene, non un errore - e la sezione si sarebbe
fermata senza motivo. Ora ogni guardia e' un TETTO: `IF v_n > N THEN RAISE EXCEPTION`.
Solleva eccezione (e fa ROLLBACK) SOLO se le righe toccate sono PIU' del numero verificato
oggi (segno che la condizione ha preso righe non previste), MAI se sono di meno. Il numero
verificato oggi resta scritto nel commento di ogni sezione per il controllo di chi rilegge.

## 5. Parita' paper/live

Nessuna sezione distingue un comportamento paper da uno live per una STRATEGIA: le sezioni
1, 4, 6 toccano dati "mode-aware" ma solo per COERENZA di quella riga con la sua stessa
modalita' (mai per cambiare cosa fa un bot); le sezioni 7 e 8 toccano sia paper che live nello
stesso modo (F-5 sui 407 paper + 49 live identico; F-6 non distingue mode). La sezione 9
(cashout) tocca solo righe `payload.mode='paper'` (le 6 verificate lo sono tutte: non
essendoci proposte `cashout` `proposed` scadute in `live` oggi, non era il caso di scrivere
apposta una condizione mode-aware che non e' mai stata provata). Nessuna riga attiva o
proposta VIVA (mercato ancora apribile) viene toccata: tutte le condizioni escludono
esplicitamente cio' che non e' gia' in stato terminale o palesemente scaduto.

## 6. Cosa NON ho fatto e cosa NON ho potuto verificare

- **NON ho eseguito il file SQL** (vincolo tassativo del cantiere: sola lettura sul DB).
  L'esecuzione e la verifica dei numeri REALI dopo l'incollaggio spettano all'utente e al
  coordinatore.
- **NON ho toccato `tennis_bot_service_control`** (righe `running`/`stopping` ad app spenta,
  4 righe: `tennis_swing`, `tennis_pro`, `tennis_flb` running; `tennis_scalper` stopping,
  tutte `heartbeat_at` 26/09 17:40Z): verificato nel codice (`Betfair/stream/avvio_app.py`,
  usato da `tennis_bot_service.py`) che il meccanismo si AUTOCORREGGE al prossimo avvio
  dell'app (confronto `APP_BOOT_ID`, il bot si ferma da solo se l'avvio e' nuovo). Una
  sanatoria SQL qui sarebbe superflua e rischiosa (potrebbe correre in mezzo a un avvio vero).
  Non ho controllato le tabelle equivalenti calcio (`omega_control`, `safe_strategy_control`,
  `mike_control`, `scalper_control`): stessa logica documentata nello stesso modulo, non
  riverificata riga per riga per limite di tempo del cantiere - se il coordinatore vuole la
  controprova puntuale la faccio.
- **NON ho esteso la decadenza a TUTTI i `cashout` scaduti**, solo ai 6 id verificati uno per
  uno (vedi 1.9): il servizio non decade i `cashout` per eta' da solo (scelta di disegno, ora
  segnalata come difetto di codice aperto), quindi una condizione generica "tutti i cashout
  scaduti" senza la prova di partita-finita per ciascuno sarebbe stata piu' larga di quanto
  verificato.
- **NON ho ri-verificato le 5 migrazioni del 26/09** (storico_esito_a_zero,
  omega_state_per_modalita, live_positions_senza_mercati_regolati, analytics_rpc_veloci,
  betfair_live_orders_source_bot): il coordinatore le ha verificate applicate di persona e mi
  ha chiesto esplicitamente di non ripetere, solo citarlo.
- **NON ho creato i 9 indici facoltativi**: verificato che 4 esistono gia' col nome previsto
  (aggregati_idx) e che i restanti 5 (detail_fixture_idx) sono coperti da indici equivalenti
  con altro nome su tutte le 5 tabelle (`idx_match_events_fixture` e i 4 gemelli, piu' un
  indice `(league_id, season_year, fixture_id)` su ognuna): crearli sarebbe un doppione,
  costoso in spazio (`match_odds` pesa 20 GB da sola). Non ho misurato query lente dal vivo
  (l'app e' spenta, nessun traffico da profilare oggi): la mia conclusione si basa sulla
  presenza dell'indice equivalente, non su un EXPLAIN di una query reale in produzione.
- **NON ho cercato sanatorie oltre a quelle in `AUDIT_2026-09-25/` e `AUDIT_2026-09-26/`**
  citate nel brief: ho comunque cercato con grep (`sanatoria`, `UPDATE public\.`,
  `DELETE FROM public\.`) in entrambe le cartelle e non ho trovato altri blocchi SQL "non
  eseguiti" oltre a quelli gia' coperti (F-5, F-6, origine scalper).
- **NON verificabile da me**: se le 9/17/29/50/456/... righe saranno ESATTAMENTE le stesse al
  momento in cui l'utente incolla il file (il tempo passa, l'app potrebbe essere riavviata
  nel frattempo da un'altra sessione): per questo ogni sezione accetta 0 come esito valido
  (gia' applicata o condizione nel frattempo sistemata da un riavvio reale) oltre al numero
  misurato oggi, e comunque si auto-verifica con il controllo "dopo".

## 7. Decisioni per l'utente

1. **Posizione fantasma 14265**: pulizia di igiene, non necessaria alla correttezza della
   pagina (gia' corretta a monte). Se l'utente vuole tenere la storia grezza della tabella
   (per un audit futuro) puo' NON incollare la sezione 1 e lasciare la riga.
2. **Decadenza dei `cashout` in generale**: qui sono state sanate solo le 6 proposte
   verificate con prova di partita finita (sezione 9). Il difetto di CODICE (il servizio
   decade per eta' solo `kind='place'`, mai `kind='cashout'`) resta aperto: va il servizio
   esteso a decadere anche i `cashout` (con quale prova di "partita finita", visto che oggi
   il servizio non la controlla) o si preferisce lasciarli senza scadenza automatica e
   affidarsi solo al controllo manuale? Decisione per il cantiere Safe, non presa qui.
3. **`live_now`/`tennis_live_now` in-play orfane**: la causa (nessun azzeramento di `inplay`
   alla chiusura del follow, lato calcio nemmeno uno stato terminale su `live_now.status`) si
   ripresentera' a ogni chiusura di partita finche' non viene corretta nel codice di
   produzione (fuori perimetro di questo cantiere, sola lettura): segnalo la necessita' di un
   cantiere di codice, la sanatoria di oggi e' un pareggio dei conti, non una cura. Il lato
   tennis ha gia' la correzione di codice (R-FA-1, 26/09: scrive `status='CLOSED'` da solo);
   il lato calcio no.

## 8. Cosa controllare dal vivo al prossimo avvio dell'app (in paper)

- Dopo aver incollato il file: `SELECT count(*) FROM public.betfair_live_positions WHERE id
  = 14265;` deve dare 0; `/live-pnl` non deve mostrare piu' righe rispetto a prima
  (la pagina le escludeva gia').
- Control Room / Segui Live: nessuna partita del 26/09 deve apparire come "in corso" (era
  l'effetto visibile delle righe orfane di `live_now`/`tennis_live_now`).
- Storico Mike: nessuna riga con "ingresso None-None" a video su nessuna pagina che lo mostri.
- Safe, tab proposte: le 17 proposte `place` e le 6 `cashout` del 26/09 (id 311, 315, 318,
  319, 320, 321) non devono piu' comparire con "Piazza".
- Analytics: `get_analytics_filters()`/`get_league_seasons` restano rapide (< 8 s, come
  gia' misurato dal coordinatore dopo le migrazioni del 26/09); i numeri di Analytics/
  Decisioni per una lega con partite rinviate devono corrispondere alla data VERA della
  partita (`matches.fixture_date`), non a quella programmata.
