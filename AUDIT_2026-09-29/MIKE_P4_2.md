# MIKE P4 - blocco 2 (conti e dati): M8.6, M8.7, M8.8, M8.9

Patch: `AUDIT_2026-09-29/MIKE_P4_2.patch`, da applicare SOPRA `MIKE_P4_1.patch`. Nessun commit.

## 1. Difetti, causa radice, prova (test rosso su HEAD / su P4_1)

| Punto | Difetto riprodotto | Correzione |
|---|---|---|
| M8.6 | Ramo «punteggio non recuperabile ma risultato indipendente» (`_run_event`, regolamento): `SETTLED` senza `_settle_trades` -> righe `open`/`pending` per sempre. Ramo `ERROR settle_timeout`: righe aperte mute. | Ramo indipendente: le righe si regolano con `E.settle_legs(ctx.legs, 0, comm)` (qualunque totale da' lo stesso netto: e' la condizione del ramo; righe mai abbinate -> `void`), stessa ripetizione `_retry_settle_rows` degli altri rami, `meta.settle_reason="risultato_indipendente_dal_punteggio"`. Ramo ERROR: NESSUN P&L inventato (dipende dal risultato), le righe `open/pending/hedged` restano col loro stato e portano `meta.regolamento="non_determinabile"`; il log `error settle_timeout` elenca i loro id (`righe_da_regolare`). |
| M8.7 | `db.fetch_scan_rows` tornava `[]` su errore; il servizio lo metteva in cache come buono; dopo 10 minuti ogni partita risultava assente e andava al regolamento. | `fetch_scan_rows` torna `None` su errore. `_righe_del_feed`: con `None` si tiene l'ULTIMA lista buona (prezzi vecchi = `feed_fresh` falso = nessun ordine), la cache NON si rinfresca (si ritenta al giro dopo), UNA riga `error lettura_feed_fallita` a inizio episodio e UNA `skip lettura_feed_ripresa` alla fine (kind gia' dichiarati in UI). In `_run_event`, riga assente mentre la lettura sta fallendo = nessun orologio d'assenza, nessun regolamento. `_FEED_KO` e' nell'elenco delle cache di processo (banco pulito). |
| M8.8 | Riga assente (< 10 min), dati incompleti o snapshot non costruibile: il giro usciva subito, niente sorveglianza degli ordini. | I tre blocchi «gambe stantie / esiti ignoti / lay appoggiate» spostati SENZA modifiche in `_sorveglia_gambe` (il giro pieno la chiama nello stesso punto: comportamento identico); `_sorveglia_senza_dati` (esiti del runner in paper, posizione di conto, `_sorveglia_gambe`) chiamata nei tre rami d'uscita anticipata. Sospensione e mercato della copertura restano legati ai prezzi (senza prezzi non si leggono; la lay sparita dai correnti la rilegge per bet_id M6.2). Nel ramo «dati incompleti» senza selezioni aperte si salva la scheda SOLO se la sorveglianza ha cambiato qualcosa (write-on-change). |
| M8.9 | Ripiego degli aggregati: `realized_today` gia' per modalita', ma i cumulativi di sempre (`realized_total`, `won`, `lost`, `_cumulative_totals`) sommavano paper e live, e la cache era unica. | `_cumulative_totals(day_start, mode)`: filtro per modalita' e cache per modalita' (`v:<mode>`); senza modalita' identico a prima. |

## 2. File toccati (righe, rispetto a P4_1)
- `Betfair/mike/service.py`: vedi `git diff --stat` nel messaggio (M8.8 sposta ~55 righe in una funzione: righe identiche).
- `Betfair/mike/db.py`: 2 funzioni (`fetch_scan_rows` torna None su errore; `_cumulative_totals` per modalita').
- `Betfair/mike/tools/replay_registrazioni.py`: scenario `lettura-dati-ko`.
- NUOVO `Betfair/mike/tests/test_mike_p4_conti_dati_2026_09_29.py` (8 test).

Collegamenti controllati: `fetch_scan_rows` (unico chiamante: `_righe_del_feed`; i finti dei test ritornano liste; `DbMemoria` del banco invariata); `_cumulative_totals` (solo `aggregates`); `_CACHE_DI_PROCESSO` (test `test_mike_legge_canale` controlla solo `_CANALE_FEED`); `_settle_trades` (chiave `senza_punteggio` letta solo li'); kinds `error`/`skip`/`feed_line_missing` gia' in `mike.ts`.

## 3. Test / mutazioni / replay
- `python -m pytest Betfair/mike -q -p no:cacheprovider` (P4_1+P4_2): **1055 passed** (1020 + 24 + 11), 0 test esistenti modificati.
- `python -m pytest Betfair/stream/tests -k "mike or banco or certifica"`: 293 passed, 25 skipped.
- Nuovi test (11): 8 rossi su P4_1 per i difetti M8.6-M8.9; 3 (richiesta del coordinatore, reperto Y6 sul blocco 1) verdi sul codice e rossi con la mutazione Y6: nessun comportamento diverso da quello descritto, nessuna correzione.
- Mutazioni (ripristino da copia + hash, `MUTAZIONE`=0):
  M8.6a righe non regolate nel ramo indipendente -> rosso; M8.6b nessuna marcatura in ERROR -> rosso;
  M8.7a `fetch_scan_rows` torna [] -> rosso; M8.7b lista buona non tenuta -> rosso; M8.7c guardia d'assenza tolta -> rosso;
  M8.8 `_sorveglia_senza_dati` spenta -> 2 rossi; M8.9 cumulativi senza filtro -> rosso;
  Y6 (coordinatore) pre-controllo della riapertura tolto -> 3 rossi.
- Falsificazione A LIVELLO DI REPLAY di M8.7: guardia tolta -> `lettura-dati-ko` KO (violazione M8.7, stato SETTLING durante il guasto). Col codice corretto OK.
- Replay (codice ESATTO P4_1+P4_2):
  - `copertura-rifiutata --trasporto entrambi`: 0 violazioni, parita' coda/canale come nel riferimento (NON RAGGIUNTA anche li', RC 1). Canale identico. Coda: tick 54673->54688, decisioni 5589->5584, giri senza riga 19->18, conteggi dei controlli di pochi casi. Causa: M8.8 fa girare la sorveglianza (letture REST del banco da 120 ms di tempo di mercato) anche nei 19 giri senza riga del passaggio in gioco: l'orologio del replay si sposta di poco. Stesse letture totali (766), stesse azioni, stessi stati. Tempo 124 s.
  - `tutti --trasporto canale` (17 scenari): 0 violazioni; i 16 scenari del blocco 1 IDENTICI (sui 15 del riferimento identici anch'essi); nuovo `lettura-dati-ko`: 140 s, 402 tick/s, «avvisi [lettura_feed_fallita, lettura_feed_ripresa] | stato di regolamento durante il guasto: nessuno», 563 giri senza riga senza regolamento. Tempo totale 735 s (LENTO: sopra il tetto di 600 s; riferimento 446 s su 15 scenari; PC condiviso con un altro delegato).

## 4. Parita' paper/live
M8.6/M8.7/M8.9 identici nei due modi. M8.8: in paper la sorveglianza include gli esiti del runner, in live la posizione di conto e le letture Betfair: gli stessi pezzi del giro pieno, per modalita'.

## 5. NON fatto / NON verificato
- M8.7: all'avvio del processo con il database gia' giu' non esiste una «ultima lista buona»: le righe mancano, la guardia evita il regolamento e la sorveglianza gira (provato da test); nel replay lo scenario `lettura-dati-ko` cade proprio in questo caso (la riga della partita manca dal feed nei secondi del passaggio in gioco quando parte il guasto): 12 minuti di riga assente senza regolamento.
- M8.6 ramo ERROR: le righe restano da regolare a mano (P&L sconosciuto): decisione per l'utente se preferisce una regola diversa.
- Il `seen_inplay`/`last_goals` fallback (2 h) non e' toccato.

## 6. Rischi per le partite in corso
- Partite gia' SETTLED con righe aperte (difetto vecchio) NON vengono ripulite: servono a mano o con una migrazione.
- M8.7: durante un guasto lungo del database Mike non regola partite finite: lo fara' al ritorno della lettura.

## 7. Righe del motore
Nessuna per questo blocco.
