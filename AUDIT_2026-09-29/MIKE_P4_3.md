# MIKE P4 - blocco 3: M8.4, M8.5, M8.12 (+ M8.11 solo proposta)

Patch: `AUDIT_2026-09-29/MIKE_P4_3.patch`, da applicare SOPRA P4_1 e P4_2 (catena 1+2+3 verificata su
indice temporaneo = worktree). Nessun commit. Punti rischiosi separati come chiesto: M8.12 e' un solo
ramo (`_segui_ordini_paper_su_runner`), M8.11 non e' toccato.

## 1. Difetti e correzioni (parte SERVIZIO; la parte del motore e' in sez. 7)

| Punto | Difetto riprodotto (test rosso su P4_2) | Correzione |
|---|---|---|
| M8.4 | In gioco, riga senza punteggio: nessun avviso; lo snapshot porta `goals=None` e il motore lo tratta come 0 (`engine.py`, sez. 7). | `_episodio_dato_assente` (nuovo): in gioco con punteggio assente attivita' `feed_line_missing` motivo `punteggio_assente` UNA volta per episodio (critica se c'e' posizione), `skip` `punteggio_assente_tornato` quando torna. Lo snapshot resta `goals=None` (mai zero), `live.goals` None. |
| M8.5 | Quote di una selezione aperta mancanti: avviso SUBITO al primo giro e poi ogni 45 s finche' mancavano (`_log_throttled` critico). | La quota si ricontrolla a ogni giro (i book sono riletti dalla riga di ogni giro, come prima); avviso `feed_line_missing` (stesso payload di prima + `da_secondi`) UNA volta dopo `_DATO_ASSENTE_AVVISO_S` = 10 s, `skip` `quote_assenti_tornato` quando tornano. |
| M8.12 | Paper, taker senza nessun evento dal runner per 60 s = dichiarato «non eseguito» (riga `error runner_senza_esito`). Il live nello stesso caso (timeout/eccezione) va in riconciliazione. | Ora come il live: gamba `pending_reconcile`, riga resta `pending` marcata `place_exception_reconciling` / `err=runner_senza_esito` / `runner_esito_ignoto=True` (conta nel rischio, ferma le aperture), attivita' `reconcile_pending` critica UNA volta. La chiude il primo esito certo del runner (codice gia' esistente: stesso ref o stesso bet_id). |

NON aggiunte alla scheda (`live.score_age_s`, `live.punteggio_assente`): il test di contratto UI
(`test_contratto_live_ogni_chiave_scritta_e_dichiarata_in_ui`) vuole ogni chiave di `live` dichiarata in
`MikeLive` (frontend, fuori perimetro). Proposta sez. 6.

## 2. File toccati
- `Betfair/mike/service.py`: +62 / -23 (helper `_episodio_dato_assente` + costante, 2 chiamate, ramo M8.12).
- `Betfair/mike/tools/replay_registrazioni.py`: +51 (scenario `punteggio-ko`).
- `Betfair/mike/tests/test_mike_d1_paper_sul_runner_2026_09_29.py`: test ESISTENTE MODIFICATO
  `test_taker_senza_esito_dal_runner_non_e_eseguito`: asseriva «riga error runner_senza_esito» (il
  comportamento che l'utente ha chiesto di cambiare, punto 8 D12/M8.12); ora asserisce riconciliazione e,
  quando il runner parla, l'esito vero (abbinato).
- NUOVO `Betfair/mike/tests/test_mike_p4_dati_assenti_2026_09_29.py` (4 test).
Chiavi AGGIUNTE: `ctx.punteggio_assente`, `ctx.quote_assenti` (episodi, nel blocco `ctx` della scheda),
payload `da_secondi`. Nessun kind nuovo.

## 3. Test / mutazioni
- `pytest Betfair/mike`: **1059 passed** (1055 + 4 nuovi; 1 esistente aggiornato, sopra).
- `pytest Betfair/stream/tests -k "mike or banco or certifica"`: 293 passed, 25 skipped.
- Nuovi test rossi su P4_2 (3 su 4; il 4o e' il controllo «prima del fischio nessun avviso»).
- Mutazioni: M8.4 punteggio ignorato -> rosso; M8.5 avviso subito -> rosso; episodio ripetuto -> 2 rossi;
  M8.12 senza esito = non eseguito -> rosso. Ripristino da copia + hash OK.

## 4. Replay (codice ESATTO P4_1+P4_2+P4_3)
- `copertura-rifiutata --trasporto entrambi`: 0 violazioni, numeri di condotta identici a P4_2 (stessi
  tick, decisioni, azioni, stati, ordini); cambiano solo le attivita': un `feed_line_missing
  punteggio_assente` e un `skip punteggio_assente_tornato` al passaggio in gioco (vedi sotto). 134 s.
- `tutti --trasporto canale` (18 scenari = 17 + `punteggio-ko`): 0 violazioni. Condotta identica a P4_2
  in tutti gli scenari (tick, decisioni, azioni, stati); attivita': `feed_line_missing` sulle quote da x3 a
  x2 in alcuni scenari (avviso per episodio invece che ogni 45 s) + `quote_assenti_tornato`, e UN
  `punteggio_assente` / `punteggio_assente_tornato` per scenario. `punteggio-ko`: 151,7 s, 371 tick/s,
  «avvisi di assenza 1 | di ritorno 1». Tempo totale 832 s (LENTO, sopra 600 s; PC condiviso).
- REPERTO dei dati veri: sulla registrazione 35760084 al passaggio in gioco la riga e' `inplay=True`
  qualche giro PRIMA che arrivi il punteggio IPS: con M8.4 Mike lo dichiara (critico se ha posizione) a
  ogni fischio d'inizio. E' vero (il dato non c'e'), ma puo' essere rumore: se l'utente preferisce, basta
  passare `_DATO_ASSENTE_AVVISO_S` anche al punteggio (una riga), cosi' si avvisa solo se manca oltre 10 s.
  DECISIONE per l'utente/coordinatore.

## 5. M8.11 - PROPOSTA (non toccato)
L'attesa paper (bet delay + 3 s, max 15) resta in produzione. Nel banco `replay_registrazioni.py:456`
mette `S.ATTESA_ESITO_TAKER_MAX_S = 0` e l'esito arriva col book successivo. Per MISURARLA senza tempo vero:
nel banco lasciare 15 e sostituire l'attesa con una attesa in TEMPO DI MERCATO: `motore.consuma_tempo(0.1)`
a passi finche' l'evento terminale del runner non c'e' o il tempo di mercato supera l'attesa. Serve prima
verificare in `Betfair/stream/backtest/porta_banco.py` / `trasporto.py` (banco comune, NON mio) che la
`PortaBanco` consegni gli eventi `order` DURANTE `consuma_tempo` (oggi il client li drena al giro dopo,
`attendi_client`). Se non li consegna, la modifica va fatta nel banco comune: la lascio al coordinatore.

## 6. Proposte per il coordinatore (fuori perimetro)
- Frontend (`MikeLive` in `frontend/src/lib/mike.ts` + card): due chiavi `score_age_s` (eta' del
  punteggio = eta' della riga che lo porta, None se manca; va anche in `_LIVE_VOLATILI`) e
  `punteggio_assente` (bool). Pronte nel servizio in 7 righe (tolte per il contratto UI).
- Motore: sez. 7.

## 7. Righe del MOTORE da passare all'altro delegato (engine.py su HEAD 2768f04)
- `engine.py:1099` (`smart_cashout`): `g = int(goals or 0)` -> punteggio assente = 0 gol. Proposta:
  `if goals is None: tele["punteggio_assente"] = True; return False, "", tele` (nessuna chiusura
  «intelligente» decisa su un punteggio che non c'e'; il cash out al 5 % e' calcolato altrove e non
  dipende dai gol).
- `engine.py:1225` (`cover_timing`): `g = int(goals or 0)` -> con punteggio assente la copertura puo'
  «aspettare» come a 0 gol, o coprire con 3+ gol veri. Proposta: `if goals is None: return "wait"`
  (niente decisione sui gol senza gol; il servizio avvisa). DA DECIDERE: in alternativa «cover» (la
  docstring dice «ogni dato mancante = si copre»), ma con 3+ gol veri sarebbe una copertura vietata.
- «Prezzi incompleti» (M8.5): nessuna riga da cambiare trovata: con un book mancante le uscite non
  scattano (`cashout_value(...).complete`), il servizio ora avvisa per episodio. Se il delegato del motore
  vuole un motivo esplicito nel `reason` della decisione, e' li'.
- Gia' corretti nel motore (nessuna azione): `engine.py:642` (`selection_decided` con goals None = None),
  `:2940`, `:3544`, `:3688` (controllano None).

## 8. NON verificato / rischi
- M8.12: se il runner perde davvero l'ordine (riavvio del runner senza diario), la gamba resta in
  riconciliazione per sempre e le APERTURE di quella partita restano ferme (uscite e chiusure no), con un
  `reconcile_pending` critico ogni 45 s. E' il comportamento del live con Betfair irraggiungibile.
  Decisione per l'utente se vuole un tetto di tempo.
- M8.4/M8.5: l'eta' vera del punteggio non esiste nel feed (lo scanner non scrive quando e' arrivato
  l'ultimo record IPS): l'eta' e' quella della riga. Proposta per lo scanner: un campo `score_ts_ms`.
- Da controllare dal vivo in paper: `feed_line_missing punteggio_assente` una volta per episodio;
  `feed_line_missing` sulle quote solo dopo 10 s; un taker paper senza esito resta in verifica.
