# Indagine: il punteggio al fischio (partita 36132117 Follo-Sarpsborg, 30/09)

Delegato di indagine in SOLA LETTURA. Base del worktree: `15f0a33` (il brief diceva
`30917ed`, che non e' antenato di questo HEAD: ho lavorato sull'ultimo master).
Orari in ora italiana, salvo dove e' scritto Z (UTC). Sonde riproducibili in `_sonda_tmp/`.

## In breve

- **Causa del ritardo di 253 s: il FORNITORE** (servizio in-play IPS di Betfair). Lo
  scanner interrogava la partita ogni 2 s dal fischio: nessun errore IPS in tutto il log
  del giorno, il parser ha letto il punteggio appena e' arrivato, e il punteggio e'
  arrivato alle 16:04:00 con l'orologio del fornitore gia' al **4'**. Il fornitore ha la
  partita, ma la pubblica solo minuti dopo. Sulle registrazioni storiche e' la norma: su
  15 fischi registrati il primo punteggio IPS arriva con una **mediana di 87 s** dopo
  l'entrata in gioco (da 13 a 150 s).
- **Il nostro tratto** va dal punteggio pubblicato dal fornitore alla decisione di Mike e
  vale da **1 a 3,5 s** (poll IPS fino a 2 s, giro dello scanner fino a 0,5 s, giro di Mike
  fino a 1,4 s). Il 30/09 Mike ha deciso **0,37 s** dopo aver visto il punteggio.
- **L'ordine** ha impiegato altri **5,4 s**. Non e' colpa nostra: il mercato Over/Under
  in gioco ha `bet_delay` 5 (e' scritto nella riga dello scanner) e Betfair trattiene
  l'ordine per quei 5 s.
- **La leva piu' forte per il fornitore** usa lo stesso fornitore senza chiamate a pioggia.
  Nella risposta *timeline* IPS, che lo scanner scarica gia' ogni 30 s, il `KickOff` compare
  prima del primo punteggio in 24 registrazioni su 30, **di mediana circa 80 s prima**.
  Proposta (b): leggere la timeline in una finestra corta dopo il fischio. Non e' applicata.

## 1. Da dove viene il punteggio, con che latenza (catena con file:riga)

| Passo | Dove | Cadenza e latenza |
|---|---|---|
| Stream Betfair MATCH_ODDS → `ev["inplay"]`, `ev["mo_status"]` | `Betfair/safe_strategy/service.py:1135-1136` (`_apply_market_book`) | al ms (push) |
| Thread punteggi `ScoreFeedWorker` | `service.py:2534-2568`; periodo `_SCORES_PERIOD_SEC = 2.0` (`service.py:131`), timeline `_TIMELINE_PERIOD_SEC = 30.0` (`:136`) | cadenza fissa 2 s: attesa media 1 s, massima 2 s |
| `poll_scores`: SOLO gli eventi con `ev["inplay"]` | `service.py:1392-1415`; IPS `scoresAndBroadcast` (`:166`, `_ips_batch` `:1349-1387`), blocchi da 50 id, ripiego `get_scores` se l'endpoint va in errore | ~70 ms a chiamata + 0,1 s di respiro fra i blocchi |
| «stato assente = punteggio precedente resta» | `service.py:1411` | se l'IPS non restituisce la partita, `score_home` resta `None` |
| `apply_score_state` → `parse_score_dict` | `service.py:1417-1458`; `Betfair/stream/scores/betfair_inplay.py:50-126` (`score.home.score` → `_to_int`: `""` o assente → `None`) | istantaneo |
| Pubblicazione: la firma critica contiene `score_home/away/minute/score_raw` | `Betfair/safe_strategy/scanner.py:526, 540-560`; riga identica su canale 47336 e DB (`service.py` ~2011-2016); giro dello scanner ogni 0,5 s (`_ciclo_persistente`) | entro 0,5 s, fuori dal freno di 2,5 s |
| Mike: client del canale (`MIKE_LEGGE_CANALE=1`) e sveglia (`MIKE_SVEGLIA_CANALE=1`), entrambi accesi nel `.env` | `Betfair/mike/service.py:6160-6200`; pavimento `max(1.0, 2 x decide_min_interval_ms)` = 1,0 s (`service.py:6011-6023`, `Betfair/stream/sveglia_canale.py:172-220`) | sveglia immediata, ma non prima di 1 s dall'inizio del giro precedente |
| Mike legge i gol | `Betfair/mike/feed.py:322-330` `goals_from_payload` | — |

**Cosa decide «punteggio assente» in Mike.** Il test e': `payload.inplay` vero **e**
`goals_from_payload(payload) is None`. Vale `None` se manca la chiave oppure se il valore
e' null, su `score_home` o su `score_away` (`feed.py:322-330`). L'eta' del punteggio non
entra: l'eta' della riga la giudica a parte `feed_fresh`, con il tetto
`HARD_MAX_AGE_SEC = 180` di `scan_feed.py:63`. L'episodio si dichiara dopo 10 s
(`_DATO_ASSENTE_AVVISO_S`, `mike/service.py:1355`, chiamata a `:4621-4630`). La regola
«senza punteggio non si copre» sta nel motore (`engine.py:1326`).

**API-Football** entra solo nel `ScorePoller` del runner calcio (`scores/poller.py`,
`scores/api_football.py`), come ripiego dopo 3 errori IPS e con un `fixture_id`. Lo
scanner non la usa, quindi **Mike non ha una seconda fonte**. `scan_feed.py` serve ai
runner: leggono la riga dello scanner e, se manca, chiamano l'IPS direttamente.

## 2. Che cosa e' successo davvero fra 15:59:47 e 16:04:00

Fatti letti (`mike_activity` dell'evento, log `mike-service`/`safe-strategy-service`/`runner-calcio` del 30/09, riga `safe_strategy_scan` in sola lettura):

| Ora | Fatto | Fonte |
|---|---|---|
| 15:59:47,623 | stato HOLD → LIVE_KO_GREEN («in gioco»): la riga dello scanner dice `inplay` | `mike_activity` |
| 15:59:49,097 | `place_resting` ko_green (lay 2,36, 5,08 €) | `mike_activity` |
| 15:59:57,821 | `feed_line_missing` `punteggio_assente` `da_secondi 10.7` | `mike_activity` |
| 15:55-16:05 | **nessun** «scoresAndBroadcast KO», «punteggi IPS KO» o «giro punteggi KO»: **0 nel giorno intero** | log dello scanner (grep) |
| 16:02:47,72 → 16:02:49,34 | annullo della ko_green, confermato (1,6 s) | `mike_activity` |
| 16:02:49,633 | LIVE_UNCOVERED («uscita non abbinata in 3'»): senza punteggio non si copre | `mike_activity` |
| 16:04:00,095 | `skip punteggio_assente_tornato`, `da_secondi 253` | `mike_activity` |
| 16:04:00,462 | POST `mike_trades` (intenzione di copertura), **0,37 s** dopo | log `mike-service` |
| 16:04:06,29 | esito `EXECUTION_COMPLETE` (lay 6,32 @ 1,76); la copertura porta **`minute: 4`** | log e `mike_activity` |
| 16:09 (riga superstite) | `score_raw.matchStatus = KickOff`, squadre «Home»/«Away», timeline `[KickOff min 0]`, `bet_delay 5` su tutte le linee O/U | `safe_strategy_scan` |

**Conclusione: e' il FORNITORE.**

- Il nostro poll girava: la partita era `inplay` per lo scanner, perche' e' da quella riga
  che Mike l'ha vista in gioco, e `poll_scores` interroga ogni evento in gioco ogni 2 s.
- Non ci sono stati errori di rete o IPS.
- Il parser ha letto il punteggio appena c'era.
- Il punteggio e' arrivato con l'orologio IPS gia' al 4': il fornitore aveva la partita in
  corso, ma lo stato non era pubblicato.
- Le squadre generiche «Home»/«Away» fanno pensare a una copertura dati di serie minore.
- La cache non l'ha trattenuto: lo `skip ..._tornato` e l'intenzione d'ordine cadono nello
  stesso giro di Mike, a 0,37 s l'uno dall'altra.

Non si puo' escludere al 100 % una variante: che l'IPS restituisse lo stato con il
punteggio vuoto (`""`). Anche in quel caso il difetto sarebbe del fornitore. Lo scanner
non registra le risposte IPS per partita (vedi «Cosa non ho potuto verificare»).

**Riprova sulla storia** (`_sonda_tmp/q5_registrazioni.py`, registrazioni reali `_live_raw`,
solo quelle iniziate almeno 60 s prima del fischio): ritardo fra il primo `inPlay=true`
dello stream e il primo punteggio IPS valido, in secondi:
13,2 · 30,7 · 35,8 · 40,8 · 48,1 · 66,0 · 72,9 · 87,1 · 93,8 · 96,4 · 97,7 · 107,3 · 108,1 · 125,3 · 150,0.
**Mediana 87 s**; 10 fischi su 15 sopra i 60 s.

- L'orologio IPS parte da 7 a 50 s dopo l'entrata in gioco.
- Il primo record pubblicato ha gia' un tempo trascorso da 17 a 116 s.
- In nessuna registrazione l'IPS ha restituito un record con il punteggio vuoto: prima del
  primo punteggio non restituiva niente.
- Risoluzione: poll del runner di allora, 5 s.

Oggi il comportamento e' identico, solo piu' lungo (253 s).

**La timeline arriva prima** (`_sonda_tmp/q6_timeline.py`): su 30 registrazioni, il
`KickOff` della timeline IPS compare prima del primo punteggio in 24, con queste
anticipazioni in secondi: 6 · 30 · 31 · 32 · 33 · 45 · 45 · 56 · 66 · 75 · 76 · 85 · 86 ·
87 · 89 · 92 · 92 · 99 · 107 · 110 · 114 · 115 · 116 · 123. Nelle altre 6 compare insieme
o subito dopo, fra −13 e 0 s.

## 3. Quanto e' normale: ritardi di oggi

| Partita (Mike) | In gioco visto | Primo punteggio | Ritardo | Episodi `punteggio_assente` |
|---|---|---|---|---|
| 36130526 Vsetin-Bohemians | 15:29:45,94 | entro 15:29:55,9 (nessun episodio; la copertura delle 15:30:40 porta `minute 0`) | **< 10 s** | 0 |
| 36132117 Follo-Sarpsborg | 15:59:47,62 | 16:04:00,10 | **252,5 s** | 1 (253 s) |

Le altre partite armate da Mike oggi (92 righe di diario dalle 14:40) non sono andate in
gioco con una posizione. Sono passate a IDLE_LIVE o sono ancora in attesa: nessun altro
episodio. Storico: vedi §2 (mediana 87 s, 15 fischi). Per Safe e Omega non ho i diari:
vedi «Cosa non ho potuto verificare».

**I nostri giri, misurati sul log di oggi** (`_sonda_tmp/q7_giri_mike.py`, 14:41-16:10):

| Tratto | Misura |
|---|---|
| giro di Mike | 4.293 giri; mediana **1,003 s**, p90 1,058 s, massimo 18,1 s |
| chiamate DB per giro | ~6,3: `mike_trades` 2,34, `mike_control` 1, `mike_requests` 1, `safe_strategy_status` 1, `mike_events` 0,48, `safe_strategy_scan` 0,27. Totale 27.066 in 89' (~18.000/ora) |
| inizio giro → decisione (Follo) | 16:03:59,866 → 16:04:00,297: **0,43 s** (sono le letture DB prima della decisione) |
| punteggio visto → intenzione d'ordine (Follo) | **0,37 s** |
| UNCOVERED → intenzione d'ordine (Vsetin) | 15:30:34,13 → 15:30:35,34: **1,2 s** (un giro) |
| intenzione → esito, **in gioco** | 5,84 s e 5,62 s, di cui `get_live_settings` → esito **5,38/5,39 s**: il `bet_delay` 5 del mercato |
| intenzione → esito, pre-partita | 0,08-0,98 s |
| annullo in gioco richiesto → confermato | 1,6 s (Follo), 0,8 s (Vsetin) |

## 4. Che cosa si puo' fare, in ordine di costo e rischio (NIENTE applicato)

Le modifiche al codice di produzione mi sono state **negate dal classificatore dei
permessi** (vedi in fondo). Qui sotto ci sono solo le proposte, da portare all'utente.

| # | Proposta | Cosa cambia per il trader | Rischio | Prova sul banco |
|---|---|---|---|---|
| (b) | **Timeline IPS nella finestra del fischio.** Per le partite di calcio in gioco da ≤ 300 s e ancora senza punteggio, `get_event_timelines` in batch a ogni giro punteggi (2 s) invece che ogni 30 s. Se il record porta `score.home/away.score` numerici (la risorsa `EventTimeline` ha il campo `score`: `betfairlightweight/resources/inplayserviceresources.py:117-131`), si riempiono `minute/score_home/score_away/red_*` **solo se sono ancora `None`**, con lo stesso `parse_score_dict`. `score_raw` non si tocca (resta il parlato dello `scoresAndBroadcast`). Una riga di log per partita: «primo punteggio dopo X s, fonte scores/timeline» | stesso fornitore; sulla storia il segnale arriva di mediana ~80 s prima | basso: si riempie solo un vuoto e l'IPS «scores» sovrascrive appena arriva. Da verificare dal vivo: che il `score` della timeline sia gia' valorizzato al `KickOff` | test con un record `eventTimelines` di forma vera, falsificato (score vuoto ⇒ niente; score presente ⇒ riempito; mai sopra un punteggio esistente); scenario del banco con il sidecar IPS in ritardo |
| (c) | **Sveglia del giro punteggi dallo stream**: `threading.Event` alzato in `_apply_market_book` (subito dopo `service.py:1136`) quando una partita passa in gioco o quando il MATCH_ODDS in gioco passa fra OPEN e SUSPENDED; il `ScoreFeedWorker` aspetta l'evento invece di `_stop.wait` fisso (`service.py:2567`), con un pavimento di 0,5 s fra due giri | −1 s in media (−2 s al massimo) fra la pubblicazione IPS e la riga, al fischio e ai gol | basso: al massimo 1 chiamata IPS in piu' per transizione, mai piu' di 2 al secondo | test della sveglia con un orologio finto e un book finto a chiavi vere; test della cadenza di pavimento |
| (d-1) | **Mike: lo stato dello scanner dal canale.** In `_scanner_age` (`mike/service.py:1266-1283`), con `MIKE_LEGGE_CANALE` acceso e il battito fresco (`ClientScan.eta_stato_s() <= 30`), payload ed eta' si prendono da `ClientScan.stato_payload` (lo stesso payload che va su `safe_strategy_status`, `canale_scan.py:442-450`); altrimenti si legge il DB come oggi | −1 lettura DB al secondo (~86.000 al giorno), −~80 ms per giro | basso: ripiego automatico sul DB; il replay non cambia (canale spento in ambiente neutro) | replay `--scenari base` 35760084 identico a `mike_tutti_FINALE.txt`; test con un `ClientScan` vero alimentato da `incassa()` |
| (a) | **Regola candidata per l'utente**: se dal primo in-play visto il mercato non si e' mai sospeso (lo stream lo porta al ms) e il flusso dei prezzi e' vivo, il punteggio vale quello pre-partita (0-0) | copertura allo scadere dei 3' invece di aspettare il fornitore | medio: gol nei primi secondi con un messaggio di sospensione perso, riconnessione dello stream, VAR. Tocca la decisione dell'utente «senza punteggio non si copre» ⇒ **solo lui** | scenari del banco: gol al 1' con l'IPS in ritardo; stream che riconnette al fischio |
| (d-2) | **Seconda fonte API-Football** solo nella finestra del fischio, solo per le partite con posizione, e solo quando il `fixture_id` c'e' gia' (Follo: `fixture_id` 1637883 nel dossier) | forse prima dell'IPS sulle serie minori | medio: la cadenza del fornitore (~15 s) e i limiti del piano non li ho verificati; matching delle partite | sonda passiva di confronto IPS/API-Football per una settimana |
| (e) | Letture di `mike_control`/`mike_requests` a ogni giro (2 su ~6): potrebbero seguire la sveglia della UI (canale 47333) | −2 letture al secondo | medio: i comandi di arresto dell'utente devono restare immediati | — |
| (f) | Pavimento della sveglia di Mike a 0,5 s | −0,5 s al massimo | alto sul DB: raddoppia le letture per giro («respiro DB» del 13/09). **Sconsigliato** finche' (d-1) ed (e) non tolgono le letture dal giro | — |
| — | `bet_delay` 5 s | irriducibile per un ordine che abbina subito (e' Betfair). Da verificare nella documentazione: se il mercato dichiara modelli di ritardo «passivi» (`betDelayModels`), un ordine che non abbina subito potrebbe non subirlo | — | — |

**Chiamate al fornitore e a Betfair, per giorno.** Stime calcolate sul codice: lo scanner
non conta le chiamate IPS nel log (la proposta (b) aggiunge il contatore).

| Chiamata | Oggi | Con (b)+(c)+(d-1) |
|---|---|---|
| IPS `scoresAndBroadcast` (batch di 50) | 1 ogni 2 s per blocco finche' c'e' calcio o tennis in gioco: ~28.800 per blocco in 16 h | + ≤ 1 per transizione in gioco/sospensione/riapertura, con pavimento 0,5 s: stimate + 2.000-3.000 |
| IPS `eventTimelines` (batch di 50) | 1 ogni 30 s per blocco: ~1.900 in 16 h | + 1 ogni 2 s **solo** mentre una partita e' nei suoi primi 300 s senza punteggio: ~45 per gruppo di fischi, ~40 gruppi al giorno ⇒ **~1.800** (tetto teorico 6.000) |
| Betfair API-NG (listMarketBook, listCurrentOrders, placeOrders ...) | invariate | **invariate**: nessuna chiamata REST nuova |
| DB Supabase, Mike | ~18.000/ora con Mike attivo | −3.600/ora con (d-1) |

## Reperto a margine

Alle 15:55 lo scanner ripete due volte al secondo: «2 partite seguite da Mike OLTRE il
tetto 40: restano senza quote in gioco [...] il tetto va alzato: MIKE_MAX_FOLLOWED». Due
partite seguite da Mike potevano restare senza quote in gioco. Il messaggio va portato
all'utente; non ho verificato di quali partite si tratti.

## COSA NON HO POTUTO VERIFICARE

1. **Le risposte IPS grezze per 36132117** fra 15:59:47 e 16:04:00: lo scanner non le
   registra e oggi non c'e' una registrazione `_live_raw` della partita (app ferma alle
   16:09). Il «fornitore» e' dedotto dagli indizi del §2 e dalla storia, non da una risposta
   letta.
2. **Che il `score` della timeline sia gia' valorizzato quando compare il `KickOff`.** Le
   registrazioni salvano la timeline gia' normalizzata, senza il campo `score`.
3. **I diari di Safe e di Omega** (`safe_strategy_activity`, `omega_activity`): la sonda
   `_sonda_tmp/q8_eventi_oggi.py` e' pronta, ma il lancio mi e' stato negato dal
   classificatore dei permessi. La tabella del §3 copre quindi solo Mike.
4. **L'istante esatto** in cui la riga con il punteggio e' uscita dallo scanner: lo
   scanner non logga le righe.
5. **Il mandato esteso** (COSTRUIRE le modifiche A e B, test, falsificazione, replay,
   `VELOCITA_FEED_E_GIRI.md` + `.patch`): **non eseguito**. Le prime modifiche a
   `Betfair/safe_strategy/service.py` sono state negate dal classificatore dei permessi
   («Modify Shared Resources»). Come prescritto, non l'ho aggirato. Serve il via libera
   esplicito dell'utente a modificare lo scanner di produzione e `mike/service.py` in
   questo worktree. Nessun file del repo e' stato modificato: solo questo referto e
   `_sonda_tmp/`.
6. I limiti di chiamata del piano API-Football e quelli non dichiarati dell'IPS: non letti.
