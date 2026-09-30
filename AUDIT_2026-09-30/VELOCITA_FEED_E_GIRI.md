# Velocita' del feed dei punteggi e dei giri — 30/09/2026 (sera)

Esecuzione delle decisioni dell'utente delle 18:10-18:30 (dopo `INDAGINE_PUNTEGGI_AL_FISCHIO.md`):
via allo scanner; **(b)** timeline consolidata nella finestra del fischio, zero chiamate in piu';
**(c)** sveglia dei punteggi dallo stream; **(d-1)** Mike legge lo stato dello scanner dal canale;
**(e)** `MIKE_MAX_FOLLOWED` a 80 con potatura; NO API-Football; NO regola «punteggio invariato».
Costruito e certificato dalla sessione admin-bc (autorizzazione diretta dell'utente, 18:35).

## 1. Che cosa cambia, per il trader

| # | Prima (fino a `e5ec3c9`) | Dopo |
|---|---|---|
| (c) | Il giro punteggi partiva ogni 2 s a orologio: fra il fischio (o un gol) visto dallo stream al ms e la lettura del punteggio passavano da 0 a 2 s. | Un book del MATCH_ODDS che porta la partita **in gioco**, o che in gioco passa **OPEN ↔ SUSPENDED** (gol, fischio), **sveglia il giro subito**. Pavimento di 0,5 s fra due giri (mai piu' di 2 letture al secondo); senza sveglie, cadenza e respiro identici a prima. |
| (b) | Nei primi minuti dopo il fischio la partita restava «senza punteggio» finche' il fornitore (`scoresAndBroadcast`) non lo pubblicava: mediana 87 s, Follo 253 s. La timeline (`eventTimelines`), che sulla storia arriva prima (24 casi su 30), si leggeva solo ogni 30 s e non riempiva il punteggio. | Per le partite di calcio **in gioco da ≤ 300 s e ancora senza punteggio** il giro legge la **timeline** (una chiamata per lotto di 50) e, se il record porta il punteggio, lo riempie per la stessa via dei punteggi (`apply_score_state`) **al posto** della lettura dei punteggi per quelle partite. Se il record NON porta il punteggio, la partita resta nel lotto dei punteggi dello stesso giro: mai un giro senza lettura. Una riga di log per partita: «primo punteggio X dopo N s dal primo in-play, fonte timeline/scores». |
| (d-1) | Mike leggeva `safe_strategy_status` dal DB **a ogni giro** (~1/s, ~86.000 letture al giorno) per sapere se lo scanner e' vivo e il blocco `flusso`. | Con il client del canale 47336 acceso e il battito piu' fresco di 30 s, Mike legge lo **stesso payload dal canale** (`ClientScan.stato_payload`), eta' = eta' del battito; altrimenti il DB come prima. `_ULTIMO_STATO_SCANNER["fonte"]` dice da dove viene. |
| (e) | Tetto 40 partite di Mike esenti dal taglio; l'avviso «N partite seguite da Mike OLTRE il tetto» confrontava il tetto con **tutte** le partite con esposizione, anche pre-partita o finite in attesa di regolamento: il 30/09 ha gridato 10.348 volte con DUE sole partite di Mike (Vsetin chiusa, Follo pre-partita). | Tetto di serie **80** (`MIKE_MAX_FOLLOWED_DEFAULT`, override da `.env` invariato). Il tetto si confronta **solo con le partite di Mike fra i candidati** (in gioco, mercato non chiuso): l'avviso grida solo quando il tetto morde davvero. |

Nessuna chiamata REST a Betfair (API-NG) e' stata aggiunta o spostata. Nessun campo del feed e'
stato tolto o rinominato: `ips` (contatori) e `inplay_visto_mono` (stato interno, non pubblicato)
sono additivi.

## 2. Conto delle chiamate al fornitore (IPS), per giorno di 16 ore

Le chiamate ora si **contano** nello stato dello scanner (`safe_strategy_status.payload.ips`,
stessa riga di sempre, zero scritture in piu'): `scores`, `timelines`, `timelines_fischio`,
`sveglie`, `punteggi_dalla_timeline`. Da domani il conto e' letto, non stimato.

| Chiamata | Prima | Dopo | Come si legge |
|---|---|---|---|
| `scoresAndBroadcast` (lotti di 50 in gioco) | 1 ogni 2 s per lotto finche' c'e' calcio o tennis in gioco: ~28.800 per lotto | uguale, **meno** i giri in cui il lotto residuo e' vuoto (tutte le partite in gioco sono nella finestra e la timeline ha portato il punteggio); **piu'** al massimo 1 giro per sveglia (pavimento 0,5 s): stimate +2.000-3.000 | `ips.scores` |
| `eventTimelines` a cadenza (lotti di 50 calcio in gioco) | 1 ogni 30 s per lotto: ~1.900 | uguale | `ips.timelines` |
| `eventTimelines` nella finestra del fischio | 0 | 1 per giro (2 s, o sveglia) **solo** mentre almeno una partita e' nei suoi primi 300 s senza punteggio: ~45 per gruppo di fischi, ~40 gruppi ⇒ ~1.800 (tetto teorico 6.000). Quando quelle sono le sole in gioco, sostituisce la chiamata dei punteggi: zero in piu'. | `ips.timelines_fischio` |
| Betfair API-NG | invariate | **invariate** | — |
| DB Supabase, letture di Mike | ~18.000/ora | −3.600/ora (stato dello scanner dal canale) | `_ULTIMO_STATO_SCANNER["fonte"]` |

Nota onesta sul «zero chiamate in piu'»: e' esatto quando le partite nella finestra sono le sole in
gioco (tipico all'inizio della giornata e per i gruppi di fischi isolati); quando in gioco ci sono
anche partite avanzate, nella finestra c'e' **una** chiamata di timeline in piu' per giro, per al
massimo 300 s per gruppo di fischi. Il conto reale sta nei contatori.

## 3. Prove

- Test: `Betfair/safe_strategy/tests/test_velocita_feed_2026_09_30.py` — 22 test su codice di
  produzione, record IPS **veri** (copiati da `_live_raw/35760084/35760084.scores.jsonl`; il record
  della timeline e' lo stesso piu' `updateDetails` nella forma della risorsa `EventTimeline` di
  betfairlightweight). Falsificazione: **14 mutazioni, tutte rosse** (sveglia su sospensione tolta;
  timeline non consolidata; timeline senza punteggio accettata; pavimento tolto; worker sordo alla
  sveglia; istante in gioco sovrascritto; potatura tolta; tetto 40; battito vecchio accettato;
  canale ignorato; respiro 0,2 s tolto; cronologia nello stato grezzo; 2 sopravvissute al primo
  giro ⇒ 2 test aggiunti, poi rosse).
- Suite: `Betfair/safe_strategy Betfair/mike Betfair/stream/tests` nel worktree: **6586 verdi**,
  47 skip, 1 xfail (8:48).
- Replay: sezione 4.

## 4. Replay di certificazione (codice finale, commit `04b8d20`)

| Replay | Comando | Esito | Confronto col riferimento |
|---|---|---|---|
| Mike, tutti gli scenari | `certifica mike 35760084 --scenari tutti --trasporto canale` | 25 OK, 0 KO, **0 violazioni** (`replay/mike_tutti_SCANNER_VELOCITA_v3.txt`) | **25 su 25 identici** (P&L, fill, ordini, attivita') al giro precedente `mike_tutti_SCANNER_VELOCITA.txt`, a sua volta identico a `mike_tutti_FINALE.txt` salvo le 2 differenze attese (riga «utente» del P&L reale `96a2189`; scenario nuovo `ko-green-parziale` di `a86b927`). Durata 994 s con la suite frontend di admin-07 in parallelo (394 s a PC libero il pomeriggio): tempo, non esito. |
| Mike, base | `--scenari base` (codice v2) | 1 OK, 0 violazioni | identico |
| Omega | `certifica omega 35760084 --scenari rapidi --trasporto entrambi` | 13 OK (`replay/omega_SCANNER_VELOCITA_v3.txt`) | identico a `omega_FINALE.txt` (differenze solo nei tempi dei controlli) |
| Safe base | `certifica safe_base 35760084 --scenari rapidi --trasporto entrambi --worker 1` | 14 OK (`replay/safe_base_SCANNER_VELOCITA_v3.txt`) | identico a `safe_base_FINALE.txt` (solo tempi) |

Nota onesta: il banco NON esercita ne' la finestra del fischio ne' la sveglia (i punteggi
entrano dal sidecar in `apply_score_state`, il `ScoreFeedWorker` non gira): il replay certifica
che NULLA e' regredito per i bot, non che le parti nuove funzionino dal vivo (per quello: §5).

## 4b. Revisione indipendente (Sonnet, sola lettura) e correzioni

0 ALTI, 2 MEDI, 4 BASSI: TUTTI corretti prima della fusione (sveglia solo per il calcio, non per
il tennis che si sospende a ogni punto; un evento nato gia' in gioco al riavvio NON e' un
fischio; transizione valutata dopo le assegnazioni; `stop()` sveglia il worker; copia dell'elenco
eventi nell'iterazione dal thread). In piu' (review UI di admin-07): `flusso.fermi_da_ms`,
`odds_seen_ms`, `ou_blocks` di Mike che non scarta piu' una linea viva per un `seen_ms` stantio.
Falsificazione totale: 23 mutazioni, tutte rosse. Suite Python: 6586 + 4627 + 3459 verdi.

## 5. Cosa NON e' verificato e come si verifica domani

1. Che `eventTimelines` porti il blocco `score` **gia' valorizzato** al KickOff (l'indagine non
   ha potuto leggerlo: lo scanner non registra le risposte grezze). Se non lo porta, il codice
   ricade sul poll dei punteggi nello stesso giro: nessuna regressione, nessun guadagno. Si vede
   dal log «primo punteggio … fonte timeline» e da `ips.punteggi_dalla_timeline` > 0.
2. Le sveglie dal vivo: `ips.sveglie` deve crescere al fischio e ai gol; se restasse a 0 con
   partite in gioco, lo stream non sta portando le transizioni (da indagare, non da rattoppare).
3. La fonte dello stato in Mike: nel log di Mike non ci sono piu' letture di `safe_strategy_status`
   a ogni giro; `_ULTIMO_STATO_SCANNER["fonte"] == "canale"` con il canale acceso.

## 6. Configurazione

Nessuna riga `.env` necessaria: il tetto 80 e' nel codice; `MIKE_MAX_FOLLOWED` resta un override.
Riavvio dell'app necessario (scanner e Mike sono processi Python).
