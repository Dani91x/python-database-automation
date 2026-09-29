# Mike - Capitolo 10: dati e conti (schede)

Schema: `10_dati_e_conti.html` (sorgente `10_dati_e_conti.workflow.json`).
Fonte dei fatti: `SCHEMI_BOT/mike/inventario/D_giro_e_conti.md` (schede D-n); rimandi a
`C_servizio_e_ordini.md` (schede C-n). Valori controllati anche su `Betfair/mike/config.py` e sulle
costanti di `Betfair/mike/service.py` righe 50-62.

**Schede dell'inventario D usate in questo file (numeri):** 4, 10, 13, 14, 15, 21, 22, 23, 28, 29,
30, 31, 32, 33, 34, 36, 37, 38, 45, 64, 65, 66, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88,
90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108.
(Alcune compaiono anche nel capitolo 9 dal punto di vista del giro; il conto completo delle 108 e'
in coda a questo file.)

Come si legge: ogni riquadro dello schema ha un numero (01-12) scritto in alto. La scheda con lo
stesso numero lo spiega. Le parole fra «» sono i messaggi che l'utente legge nell'app.

**Regola generale paper/live di questo capitolo:** ogni riga salvata (partita, ordine) porta la sua
modalita'. Stop giornaliero, tetto delle partite, capitale a rischio, profitto bloccato e P&L del
giorno si contano SEMPRE separati fra paper e live e non si sommano mai. L'unica eccezione e' un
ripiego di emergenza dei totali di sempre (riquadro 09, «Punti da decidere» n. 3).

---

## 01 - Scanner («riletto ogni 4 s»)

**Cosa fa**
- Lo scanner (il programma comune che guarda tutte le partite) scrive una riga per ogni partita di
  calcio: nomi, squadre, competizione, ora del fischio d'inizio, mercati, quote, punteggio, minuto,
  stato della partita, ora dell'ultimo aggiornamento.
- Da ogni riga Mike ricava: ora del fischio d'inizio, numero del mercato Under/Over 3.5 e 4.5,
  numero delle selezioni Under e Over riconosciute PER NOME («Under 3.5 Goals»...).
- La partita e' «completa» se ha tutte e due le linee, l'Under 3.5 e l'Over 4.5.
- Per ogni selezione Mike legge: miglior punta e importo, miglior banca e importo, stato della
  selezione (di serie aperta), in gioco, ritardo di piazzamento (di serie 0).
- Gol totali = gol casa + gol trasferta (se uno dei due manca: niente).
- Intervallo: lo stato della partita contiene «half» ed «end», oppure vale «halftime», «half_time»,
  «ht» (maiuscole ignorate).
- Date senza fuso orario = ora di Greenwich (UTC). Un numero o una data illeggibile = niente.
- Mike legge anche lo stato dello scanner: da quanto non scrive e se dichiara il flusso dei prezzi
  fermo.

**Quando**
- Al massimo ogni 4 s (10 s con il canale veloce sano, riquadro 02).
- Qui i mercati fermi o non piu' osservati NON si scartano: servono per annullare gli ordini. Lo
  scarto avviene al riquadro 05.

**Numeri**
- Linee di Mike: 3.5 e 4.5 gol.
- Rilettura: 4 s (parametro, da 0 a 30 s, app).

**Esempio con le cifre**
- Punteggio 1 e 2: 3 gol. Stato «HalfTime»: intervallo. Stato «FirstHalfEnd»: intervallo.
- «2026-09-29T19:00:00Z» = fischio alle 21:00 di Roma.
- Con 3 gol a fine partita un back Under 3.5 da 10,00 EUR a 1,90 vale +8,55 EUR netti; con 4 gol
  -10,00 EUR: per questo i gol del feed contano quando Betfair non dice il risultato (riquadro 08).

**Cosa vedi nell'app**
- Punteggio, minuto, intervallo e book sulla scheda della partita; eta' dello scanner in testata.

**Se qualcosa va storto**
- Lettura delle righe fallita: Mike la tratta come «nessuna riga» (vedi «Punti da decidere» n. 1).
- Stato dello scanner illeggibile: eta' sconosciuta.
- Partita non completa: non puo' essere armata; con una posizione aperta vedi riquadro 07.
- Paper o live: identico.

**Per il tecnico**
- D-78 `feed.py:25-51` (`EventInfo`, `complete`, `market_id`, `selection_id`, `selection_name`),
  194-215 (`event_info`); campo `open_date`.
- D-79 `parse_iso_epoch`, `_num` `feed.py:54-71`.
- D-83 `_book_for` `feed.py:218-230`.
- D-85 `ht_active_from_payload`, `goals_from_payload` `feed.py:286-301`.
- D-97 `db.fetch_scan_rows` `db.py:508-515` (tabella `safe_strategy_scan`), `scanner_status`
  518-525 (tabella `safe_strategy_status`, id `scanner`).

---

## 02 - Canale veloce («spento di serie»)

**Cosa fa**
- Con l'interruttore acceso, un lettore unico (quello di Safe) riceve dallo scanner le righe al tick,
  senza aspettare il database.
- Mike prende dal canale solo le righe di meno di 5 s.
- Se OGNI partita dell'elenco ha una riga fresca dal canale (con l'ora delle quote), Mike rilegge il
  database ogni 10 s invece di 4.
- Poi unisce: la riga del canale vince solo se e' strettamente piu' recente di quella del database.
- Il database resta la LISTA delle partite e il ripiego.

**Quando**
- A ogni giro, solo con l'interruttore acceso (di serie SPENTO). L'interruttore si rilegge a ogni
  chiamata.

**Numeri**
- Eta' massima di una riga dal canale: 5 s.
- Rilettura del database con canale sano: 10 s; altrimenti 4 s.
- Porta dello scanner: 47336.

**Esempio con le cifre**
- 12 partite in lista, tutte coperte dal canale: una lettura del database ogni 10 s invece che
  ogni 4 s. Le quote di un Under 3.5 da puntare a 1,90 per 10,00 EUR arrivano al tick.

**Cosa vedi nell'app**
- In testata «fonte» = canale o database, e quante righe arrivano dal canale.

**Se qualcosa va storto**
- Errore d'avvio del canale: avviso, Mike lavora dal database.
- Qualsiasi dubbio (una partita senza riga fresca dal canale): cadenza di sempre, 4 s.
- «Azzera» spegne e dimentica il lettore (si usa quando si svuotano le memorie temporanee).
- Paper o live: identico.

**Per il tecnico**
- D-76 `service.py:5754-5825` (env `MIKE_LEGGE_CANALE`, `_RISINC_FEED_S` = 10, `_CANALE_FEED`,
  `avvia_client_scan`, `azzera_canale_scan`).
- D-77 `service.py:5828-5919` (`_canale_copre_tutte`, `_righe_del_feed`, `statistiche_canale_scan`;
  `CS.MAX_ETA_CONTESTO_S` = 5).

---

## 03 - Betfair diretto («solo ripiego»)

**Cosa fa**
- Mike legge i book direttamente da Betfair solo in due casi:
  - flusso dei prezzi fermo con una posizione aperta (e cash out dell'utente con flusso fermo);
  - partita a mercato chiuso, per sapere i vincitori (riquadro 08).
- Il book letto da Betfair viene trasformato nello stesso formato del feed (prezzi e importi punta e
  banca per selezione), con il ritardo di piazzamento preso dal feed; solo se il mercato e' aperto e
  ha selezioni.
- Con quei prezzi Mike puo' solo chiudere, coprire o proteggere. Le APERTURE restano bloccate.

**Quando**
- Flusso fermo: al massimo una lettura ogni 10 s per mercato; mai nel modo «a secco».
- Mercato chiuso: al massimo ogni 60 s.

**Numeri**
- 10 s fra due letture dello stesso mercato (fisso).
- Promemoria critico ogni 60 s.

**Esempio con le cifre**
- Under 3.5 aperto da 10,00 EUR a 1,90, flusso fermo da 70 s: Mike legge il book, trova 1,55/1,57 e
  puo' chiudere in profitto; non aprirebbe un nuovo ciclo.

**Cosa vedi nell'app**
- In Attivita': «flusso interrotto», «lettura diretta da Betfair» (al massimo una riga ogni 60 s),
  oppure «flusso interrotto senza lettura» con l'esposizione in euro.

**Se qualcosa va storto**
- Betfair non risponde: la posizione resta senza chiusura ne' copertura finche' un prezzo vivo non
  torna.
- Paper o live: identico; anche il paper legge Betfair per il ripiego.

**Per il tecnico**
- D-36 `service.py:4235-4274`, `_books_ripiego_rest` 1163-1190, `_RIPIEGO_REST_MIN_S` = 10.
- D-82 `feed.blocco_da_rest` `feed.py:143-161`.
- Regolamento: `final_total_from_books` `service.py:1027-1037` (inventario C-27).

---

## 04 - Dossier («gol attesi»)

**Cosa fa**
- **Dossier pre-partita** (quando la partita viene armata): Mike cerca la partita nel catalogo dei
  modelli e raccoglie: lega, gol attesi di casa e di trasferta, correlazione fra i gol, squadre,
  probabilita' di esattamente 4 gol (dalla griglia dei risultati fino a 8 gol), probabilita'
  calibrata dell'Under 3.5 e da dove viene, fonte («fixture» o «nessuna»).
- **Ritentativo**: se mancano i gol attesi, Mike riprova ogni 5 minuti.
- **Catena di ripiego dei gol attesi**: dal catalogo dei modelli; se mancano, dalle quote 1X2
  pre-partita congelate dallo scanner; se mancano e si conoscono minuto e punteggio, dal mercato
  Under/Over in gioco; altrimenti niente.
- **Atlante dei gol**: tabella comune delle probabilita' di gol nei prossimi minuti, ricaricata se il
  file cambia.
- **Quadro dal vivo** (ogni giro in gioco): distribuzione dei gol finali, probabilita' di gol nei
  prossimi 3 minuti (atlante e modello), pressione (angoli e cartellini), probabilita' di 4 gol,
  probabilita' dell'Over 4.5 adesso e fra 5 minuti senza gol, risparmio atteso sulla copertura,
  probabilita' in tre scenari (adesso / dopo / gol subito).
- **Probabilita' di gol prudente**: la piu' alta fra atlante e modello (il modello moltiplicato per
  la pressione, almeno x1, al massimo 1).
- **Tabella empirica intervallo -> fine gara**: dato il punteggio dell'intervallo, la distribuzione
  dei gol finali, lega e globale fuse; usata solo se il punteggio e' ancora quello dell'intervallo.

**Quando**
- Pre-partita all'armamento e al ritentativo; quadro dal vivo a ogni giro con partita in gioco.

**Numeri**
- Correlazione di serie: -0,13. Griglia fino a 8 gol.
- Ritentativo del dossier: 300 s. Ritentativo della tabella empirica: 600 s.
- Orizzonte della probabilita' di gol: 3 minuti. Passo d'attesa della copertura: 5 minuti
  (parametro, app); minuto massimo 90.
- Tabella empirica: casi minimi 200 (parametro, da 20 a 5000, app); peso della lega =
  casi lega / (casi lega + 50).

**Esempio con le cifre**
- Gol attesi 1,6 e 1,2 trovati: fonte «fixture», probabilita' di 4 gol calcolata dalla griglia.
- Probabilita' di gol: atlante 0,05; modello 0,04 x pressione 1,2 = 0,048: vale 0,05.
- Probabilita' dell'Over 4.5 adesso 0,10, fra 5 minuti senza gol 0,08: risparmio atteso sulla
  copertura 21,74%. Su una copertura Over 4.5 da 2,40 EUR vuol dire circa 0,52 EUR in meno se si
  aspetta e non segna nessuno.
- Casi della lega 150: peso della lega 150 / 200 = 0,75.
- Partita di lega minore armata alle 19:00 senza fixture; alle 19:15 il catalogo e' popolato: il
  ritentativo trova 1,4 e 1,1 e il modello si accende.

**Cosa vedi nell'app**
- Fonte del modello e fonte dei gol attesi; probabilita' di 4 gol pre-partita e dal vivo; probabilita'
  di gol (atlante e modello); risparmio atteso; probabilita' del modello ed empiriche.
- Riga «dossier risolto» in Attivita'.

**Se qualcosa va storto**
- Ogni pezzo che fallisce resta vuoto; nessun blocco.
- Atlante mancante: avviso una sola volta; senza probabilita' di gol il motore copre SUBITO.
- Catalogo senza la partita: tutte le voci vuote, fonte «nessuna».
- Paper o live: identico.

**Per il tecnico**
- D-98 `db.py:531-595` (`fixture_id_for_event`: `live_follow` poi `omega_events`;
  `fixture_lambdas` da `fixture_predictions`; `fixture_analysis`; `ht_ft_rows`).
- D-101 `load_atlas` `dossier.py:22-39` (`_AVVISATO`).
- D-102 `build_prematch` `dossier.py:42-111` (`DEFAULT_RHO`, `MAX_GOALS`, `_p_total`,
  `p4_from_lambdas`, `_id_int`; `p_over45_cal` sempre vuoto; sorgente `calibrated`/`raw`).
- D-103 `lambdas_con_ripiego` `dossier.py:241-295` (`pre_ko_odds`, `live_ou`, `none`).
- D-104 `live_frame` `dossier.py:298-411`; D-105 `combine_hazard` 114-123; D-106 `cover_gain_pct`
  126-133; D-107 `get_empirical`, `p_total_empirical` 136-210 (`_EMPIRICAL_RETRY_S`);
  D-108 `p_total_from_grid`, `_p_le`, `model_probs_from_grids` 174-180, 213-238.
- D-14 `_retry_dossier` `service.py:5387`.

---

## 05 - Freschezza («45 s, 20 s, 180 s»)

**Cosa fa**
Mike giudica ogni riga con tre domande, piu' severe per ordinare che per decidere.
- **Per DECIDERE**:
  - La riga ha piu' di 180 s? Si': mai buona.
  - La riga ha al massimo 45 s? Si': buona.
  - Lo scanner ha battuto negli ultimi 75 s? Si': buona lo stesso (lo scanner scrive solo cio' che
    cambia). No: vecchia.
- **Per ORDINARE**:
  - La riga ha piu' di 180 s? Si': mai.
  - La riga ha al massimo 20 s? Si': si puo' ordinare.
  - Lo scanner ha battuto negli ultimi 30 s? Si': si puo' ordinare. No: niente ordine.
- **Linea ancora osservata**: una linea (3.5 o 4.5) il cui ultimo book ricevuto dallo scanner ha piu'
  di 90 s viene trattata come ASSENTE quando si decide. Uno scanner vecchio che non scrive l'ora
  del book = linea osservata.
- **Flusso vivo**: Mike chiede alla regola comune del flusso (solo per le linee 3.5 e 4.5, non per il
  mercato principale): il giro dello scanner e' bloccato, o una delle due linee e' dichiarata
  ferma? Si': il flusso NON e' vivo e quella linea non ha prezzi.

**Quando**
- A ogni fotografia (riquadro 06), a ogni cash out, a ogni giro della partita.

**Numeri**
- Per decidere: 45 s (parametro, da 3 a 180 s, app); scanner vivo 75 s (parametro, app).
- Per ordinare: 20 s; scanner 30 s (parametri, app).
- Tetto assoluto: 180 s (variabile d'ambiente, di serie 180).
- Linea osservata: 90 s (parametro, da 5 a 600 s, app).
- Giro dello scanner fermo: oltre 45 s.

**Esempio con le cifre**
- Riga di 60 s, scanner battuto 20 s fa: buona per decidere (60 s supera 45 s, ma lo scanner ha
  battuto entro 75 s) e buona per ordinare (60 s supera 20 s, ma lo scanner ha battuto entro 30 s).
- Riga di 60 s, scanner battuto 40 s fa: buona per decidere, NON per ordinare. Mike non piazza il
  back Under 3.5 da 10,00 EUR a 1,90 finche' non arriva una riga piu' fresca.
- Riga di 25 s, scanner battuto 12 s fa: si puo' ordinare.
- Riga di 200 s: mai, qualunque cosa dica lo scanner.
- La 4.5 non e' piu' ricevuta da 3 minuti ma la riga si aggiorna per minuto e punteggio: la 4.5 e'
  assente; niente copertura Over 4.5 da 2,40 EUR su quella quota.

**Cosa vedi nell'app**
- Il semaforo del feed sulla scheda; linea mancante in rosso.
- Cash out rifiutato con «Feed non aggiornato».

**Se qualcosa va storto**
- Riga senza dati di flusso: «non noto» = vivo (condotta di prima), salvo che lo scanner nuovo
  dichiari il flusso e la riga no: allora NON vivo.
- Paper o live: identico.

**Per il tecnico**
- D-86 `_hard_max_age`, `feed_fresh` `feed.py:304-336` (env `SCAN_FEED_HARD_MAX_AGE_SEC`).
- D-87 `order_fresh` `feed.py:339-371`.
- D-80 `blocco_osservato` `feed.py:74-95`, `payload_blocchi_ou` 131-140, `ou_blocks` 164-191
  (`book_seen_max_s` = 90).
- D-81 `mercati_fermi`, `mercati_di_mike`, `flusso_esito` `feed.py:98-128`; `flusso_prezzi.py:147-237`
  (`STATO_CALCOLO_MAX_S` = 45).

---

## 06 - Fotografia («quote vive»)

**Cosa fa**
- Mike costruisce la fotografia del mercato su cui il motore decide: book di Under 3.5, Over 4.5,
  Under 4.5 (solo linee osservate e con flusso vivo; con il giro dello scanner bloccato nessun book;
  col ripiego i book di Betfair), in gioco, stato del mercato (dalla 3.5, poi dal mercato principale,
  di serie aperto), minuto (solo se intero), gol, intervallo, freschezza per decidere e per
  ordinare (col ripiego: decidere si', ordinare no), fonte dei prezzi, probabilita' di gol,
  probabilita' di 4 gol di mercato e di modello, ultimo gol, risparmio atteso, pressione,
  probabilita' calibrata dell'Under 3.5, scambiato (solo informazione).
- **Probabilita' del mercato**: dalle quote di punta delle due linee, tolto il margine, Mike calcola
  la probabilita' dell'Over 3.5 e dell'Over 4.5; la probabilita' di esattamente 4 gol e' la
  differenza; poi la distribuzione in tre classi (3 o meno, 4, 5 o piu').

**Quando**
- A ogni giro della partita e a ogni cash out.

**Numeri**
- Vedi riquadro 05 (45 s, 20 s, 90 s, 180 s).

**Esempio con le cifre**
- Over 3.5 a 2,10 e Under 3.5 a 1,90: probabilita' Over 3.5 = 0,475. Over 4.5 a 3,60 e Under 4.5 a
  1,38: probabilita' Over 4.5 = 0,277. Probabilita' di esattamente 4 gol = 0,198.
- Con un back Under 3.5 da 10,00 EUR a 1,90 e una copertura Over 4.5 da 2,40 EUR, 4 gol e'
  l'unico esito in cui perdono entrambe: -12,40 EUR, con probabilita' di mercato circa 20%.

**Cosa vedi nell'app**
- La scheda della partita: book, probabilita' di 4 gol di mercato, freschezza.

**Se qualcosa va storto**
- Riga senza dati o senza ora del fischio: nessuna fotografia; la partita non viene decisa e Mike lo
  scrive (riquadro 07).
- Un prezzo mancante: la probabilita' corrispondente resta vuota.
- Paper o live: identico.

**Per il tecnico**
- D-88 `snapshot_from_row` `feed.py:374-440` (freschezze 428-431).
- D-84 `implied_p4`, `market_totals` (ognuna col suo `p_over`) `feed.py:233-283`.

---

## 07 - Linea assente («niente ordini»)

**Cosa fa**
- **Riga sparita dal feed.** Mike si segna da quando manca. Meno di 10 minuti: e' un buco
  passeggero (per esempio al fischio il feed cambia blocco); la partita salta il giro. Dopo 10
  minuti: mercato considerato chiuso -> regolamento (riquadro 08).
- **Linea assente con posizione aperta** (manca la 3.5 o la 4.5, o l'Under 3.5, o l'Over 4.5): Mike
  lo grida. Niente copertura, niente cash out, niente uscita possibili su quella linea. La partita
  salta il resto del giro.
- **Fotografia non costruibile** (per esempio manca l'ora del fischio): Mike lo scrive; la partita
  salta il giro.
- **Selezione ancora in gioco senza prezzo** (dopo la fotografia, con una posizione): Mike lo grida;
  il giro continua.

**Quando**
- A ogni giro della partita.

**Numeri**
- Riga assente: 10 minuti (600 s, fisso).
- Freno delle righe ripetute in Attivita': 300 s (parametro, app); 45 s per le critiche.

**Esempio con le cifre**
- Lo scanner ha tolto la 4.5 dal suo tetto di mercati. Mike ha un back Under 3.5 da 10,00 EUR a
  1,90 in gioco e deve coprire: la scheda mostra «OU45|OVER mancante» in rosso e la copertura non
  parte. Senza copertura: +8,55 EUR con 3 gol o meno, -10,00 EUR con 4 gol, -10,00 EUR con 5 o piu'
  (con la copertura Over 4.5 da 2,40 EUR a 5,00 sarebbe stata -0,88 EUR con 5 o piu').

**Cosa vedi nell'app**
- Allarme sulla scheda della partita («linee assenti dal feed», «flusso prezzi interrotto») e riga
  critica in Attivita' con le selezioni mancanti.

**Se qualcosa va storto**
- Mentre la partita salta il giro NON girano: il ritiro degli ordini fermi da 120 s, la
  riconciliazione degli ignoti, la sorveglianza della sospensione, il seguito delle lay appoggiate
  (vedi capitolo 9, «Punti da decidere» n. 2).
- Scanner illeggibile per piu' di 10 minuti: TUTTE le partite risultano sparite (vedi «Punti da
  decidere» n. 1).
- Paper o live: identico.

**Per il tecnico**
- D-28 `service.py:4039-4055` (`_ROW_MISSING_GRACE_S`, `extra.row_missing_since`).
- D-34 `service.py:4186-4207` (attivita' `feed_line_missing`, scheda `lines_missing`,
  `feed_incomplete`).
- D-37 `service.py:4275-4283` (`snapshot_non_costruibile`); D-38 `service.py:4289-4296`.

---

## 08 - Regolamento («vincitori da Betfair»)

**Cosa fa**
1. **Mercato chiuso?** Si' se la linea 3.5 (o il mercato principale) e' chiusa nel feed, o la riga
   manca da 10 minuti, o sono passate 3 ore dal fischio, o 100 minuti dal fischio con la partita
   vista in gioco.
2. **Lettura dei vincitori.** Mike legge da Betfair i book delle due linee (una lettura per
   mercato) e ne ricava un totale gol «rappresentativo»:
   - 3 = vince l'Under 3.5 (e l'Under 4.5);
   - 4 = vincono l'Over 3.5 e l'Under 4.5;
   - 5 = vince l'Over 4.5 (e l'Over 3.5).
3. **Mercato annullato da Betfair** (una linea annullata, oppure chiusa senza vincitore e con tutte
   le selezioni rimosse): le gambe di QUELLA linea valgono zero; l'altra linea si regola coi suoi
   vincitori.
4. **Due ore senza esito leggibile** dalla prima lettura:
   - la partita e' stata vista in gioco e si conosce l'ultimo punteggio del feed? Mike usa quello;
   - no, ma il risultato non dipende dal punteggio (nessuna posizione, o solo cicli gia' chiusi)?
     Mike chiude la partita con quel risultato, SENZA aggiornare le righe di ordine (vedi «Punti da
     decidere» n. 2);
   - altrimenti: partita in ERRORE, «regolamento non determinabile», da sistemare a mano.
5. **Commissione.** Mike regola con la commissione scritta sulle righe al momento del piazzamento,
   non con quella attuale.
6. **Scrittura sulle righe.** Su ogni riga: esito (vinta / persa / nulla), P&L netto, lordo,
   commissione pagata, commissione del mercato, motivo «mercato annullato» se annullato. Righe gia'
   chiuse non vengono toccate. Due righe con lo stesso riferimento: il P&L va solo sulla piu'
   vecchia, l'altra diventa errore «doppione».
7. **Quando e' «regolata».** Solo quando le righe sono state aggiornate. Se l'aggiornamento
   fallisce, la partita torna «in regolamento» e Mike riprova alla lettura dopo; al quinto
   fallimento la chiude lo stesso, gridando «righe da sistemare a mano».

**Quando**
- Letture di Betfair al massimo ogni 60 s dal momento in cui il mercato risulta chiuso.

**Numeri**
- Lettura: 60 s (parametro, da 0 a 600 s, app); minimo 5 s; 30 s se il parametro e' 0.
- Attesa massima dell'esito: 7200 s (2 ore, fisso).
- Tentativi di aggiornare le righe: 5 (fisso).
- Commissione: 5% (parametro, app), ma vale quella scritta sulle righe.
- Gamba senza riga: allarme se il suo P&L supera 0,005 EUR.

**Esempio con le cifre**
Back Under 3.5 da 10,00 EUR a 1,90 + copertura back Over 4.5 da 2,40 EUR a 5,00, commissione 5%:
- 3 gol: Under +9,00 lordi, commissione 0,45, +8,55 netti; Over -2,40. Partita +6,15 EUR.
- 4 gol: Under -10,00; Over -2,40. Partita -12,40 EUR.
- 5 gol: Under -10,00; Over +9,60 lordi, commissione 0,48, +9,12 netti. Partita -0,88 EUR.
- La linea 4.5 viene annullata, 3 gol: Under 3.5 +8,55, copertura 0,00. Partita +8,55 EUR.
- Righe scritte al 5%, oggi il parametro e' 2%: si regola al 5%.
- Fischio finale alle 22:47: letture alle 22:47, 22:48, 22:49... finche' Betfair dichiara i
  vincitori.

**Cosa vedi nell'app**
- Stato «in regolamento», poi «regolata» con il P&L; P&L su ogni riga in Trade e Storico.
- In Attivita': partita regolata (con totale, P&L, gambe, eventuale annullo), regolamento dal
  punteggio del feed, commissione mista, gambe non piazzate, errori di scrittura, «da sistemare».

**Se qualcosa va storto**
- Righe illeggibili al momento della commissione: si usa la commissione attuale. Righe con
  commissioni diverse fra loro: commissione attuale e riga critica «commissione mista».
- Righe illeggibili al momento della scrittura: riga critica, esito «non scritto».
- Gamba regolata senza riga con P&L diverso da zero: riga critica; tutte a zero: solo cronaca.
- Totale non ancora deducibile: la partita resta «in regolamento» e Mike riprova alla lettura dopo.
- Riga tornata nel feed con mercato aperto entro 3 ore dal fischio: il regolamento si annulla
  (capitolo 9, riquadro 08).
- Paper o live: identico; i vincitori si leggono sempre da Betfair.

**Per il tecnico**
- D-29 `service.py:4058-4072`; D-30 `service.py:4073-4097` (`settle_confirm_s`, `_SETTLE_RETRY_S`,
  `extra.settle_next_ts`, `settle_first_ts`, `final_total_from_books` 1027-1037); D-31
  `service.py:4109-4130` (`settle_plan` 1069-1090, `market_voided` 1047-1066, `mercato_annullato`);
  D-32 `service.py:4131-4161` (`_SETTLE_MAX_WAIT_S`, `settle_fallback`, ramo indipendente
  4143-4155, `settle_timeout` 4156-4161); D-33 `service.py:4162-4185`.
- D-64 `_SETTLE_ROWS_MAX_TRIES` = 5, `_retry_settle_rows` `service.py:5189-5217`
  (`settle_rows_retry`, `settle_rows_failed`).
- D-65 `_settle_params` `service.py:5220-5253` (`settle_commissione_mista`).
- D-66 `_settle_trades` `service.py:5256-5362` (`_pnl_of` 5342-5350; `pnl_gross`,
  `commission_paid`; `duplicate_signal_key`; `settle_rows_unreadable`, `settle_update_failed`,
  `settle_leg_senza_riga`, `settle_gambe_non_piazzate`; soglia 0,005).
- Stati `SETTLING`, `SETTLED`, `ERROR`; righe `won`, `lost`, `void`, `error`.

---

## 09 - Stop del giorno («-50 euro»)

**Cosa fa**
- **La giornata** comincia a mezzanotte di Roma. La data della giornata si calcola sull'ora di
  inizio + 12 ore, cosi' vicino alla mezzanotte non si sbaglia giorno.
- **Il giorno di una posizione** e' il giorno del suo PRIMO piazzamento; una chiusura eredita il
  giorno della sua apertura.
- **Realizzato di oggi**: somma del P&L gia' netto delle righe regolate della giornata.
- **Profitto bloccato**: somma del risultato gia' certo delle partite non ancora regolate che non
  hanno piu' esposizione (ciclo chiuso in verde o in perdita), solo se il primo piazzamento e' di
  oggi. Una partita con una selezione ancora aperta, una gamba in verifica o mai giocata non conta.
- **P&L del giorno** = realizzato di oggi + bloccato.
- **Stop**: se il P&L del giorno e' uguale o peggiore di -50 EUR, Mike non apre piu' niente fino a
  mezzanotte di Roma: niente partite nuove, niente ingressi, niente ultimo ingresso, niente
  re-ingressi. Le chiusure continuano.
- **Totali (aggregati)**: Mike li chiede a una procedura del database, filtrata per modalita'. Se la
  procedura non esiste, Mike passa per sempre a un ripiego che somma le righe da solo.

**Quando**
- A ogni giro. I totali si rinfrescano al massimo ogni 20 s, e subito dopo ogni azione.

**Numeri**
- Stop: 50,00 EUR (parametro, da 0 a 100.000, app; 0 = spento).
- Totali: ogni 20 s (parametro, app). Totali di sempre nel ripiego: tenuti 300 s (5 minuti).
- Commissione per il bloccato: 5%.
- +12 ore per la data della giornata (fisso).

**Esempio con le cifre**
- Realizzato di oggi -38,40 EUR, bloccato -12,10 EUR: P&L del giorno -50,50 EUR <= -50: STOP.
- Bloccato: back 10,00 EUR a 2,00 e banca 10,10 EUR a 1,98. Se vince l'Under: +10,00 - 9,90 =
  +0,10 EUR; se perde: -10,00 + 10,10 = +0,10 EUR (prima della commissione). Bloccato +0,10 EUR.
- 28/09 alle 23:30 di Greenwich = 29/09 alle 01:30 di Roma: la giornata e' cominciata il 28/09 alle
  22:00 di Greenwich e si chiama «2026-09-29».
- Chiusura alle 00:05 di un trade aperto alle 23:50: conta nel giorno prima.

**Cosa vedi nell'app**
- In testata: realizzato di oggi e totale, bloccato, P&L del giorno, vinte e perse, «stop
  giornaliero».
- In Attivita', una volta per giornata, la riga dello stop con P&L del giorno, realizzato,
  bloccato, soglia e data.

**Se qualcosa va storto**
- Procedura dei totali in guasto temporaneo: Mike usa l'ultimo valore buono.
- Dopo un riavvio la riga dello stop puo' essere riscritta una volta.
- Paper o live: ogni modalita' ha il suo stop; il P&L del paper non ferma il live e viceversa.
  ECCEZIONE: nel ripiego (procedura assente) i totali di sempre (realizzato totale, vinte, perse)
  sommano paper e live (vedi «Punti da decidere» n. 3). Lo stop usa i numeri di oggi, che restano
  separati.

**Per il tecnico**
- D-21 `_operating_day_start_ts`, `_operating_day_key` `service.py:3801-3815`;
  `safe_strategy/risk.py:123-136` (Europe/Rome).
- D-23 `_first_placed_at`, `_locked_open_pnl` `service.py:3911-3946`; `engine.locked_pnl`
  `engine.py:950`.
- D-10 `service.py:3538-3565` (attivita' `daily_stop`; `daily_loss_stop`, `aggregates_cache_s`).
- D-95 `db.aggregate_rows` (`_placed_at`, `_in_day`), `_rpc_assente`, `aggregates`,
  `_cumulative_totals` `db.py:252-411` (procedura `get_mike_aggregates`, `_TOTALS_TTL_S` = 300;
  mescolanza a `db.py:394`, `401-411`).

---

## 10 - Posti («10 partite»)

**Cosa fa**
- **Posti occupati**: Mike conta le partite che hanno davvero soldi sopra (stato operativo, oppure
  una gamba viva o abbinata non ancora archiviata), separate per paper e live.
- **Nel giro**: una partita puo' aprire solo se nella SUA modalita' le partite esposte sono meno del
  tetto. Appena una partita si espone, il posto e' occupato subito per le partite successive dello
  stesso giro. Una partita gia' esposta non viene mai bloccata.
- **Dove nascono i soldi**: se una partita non puo' aprire, Mike toglie dalla decisione le sole
  aperture (ingresso Under, ultimo ingresso, seconda entrata, copertura Over, re-ingresso); annulli,
  uscite, coperture gia' in corso e cash out passano sempre.
- **Armamento delle partite nuove**: usa un altro conto (partite non in osservazione e non «in gioco
  senza posizione») - capitolo 9, riquadro 05.
- **Capitale a rischio**: per ogni partita non chiusa della modalita' attuale Mike somma la perdita
  peggiore possibile della posizione NETTA (una punta coperta da una banca conta il residuo; gli
  ordini a esito ignoto contano come abbinati).

**Quando**
- A ogni giro, per ogni partita, prima del suo giro. Capitale a rischio a fine giro.

**Numeri**
- Tetto: 10 partite per modalita' (parametro, da 1 a 90, app). Tetto 0 o negativo = nessun tetto nel
  giro.
- Commissione per il rischio: 5%.

**Esempio con le cifre**
- Tetto 1, una vecchia partita paper ancora viva: in live il posto e' libero (i soldi finti non
  occupano il posto di quelli veri).
- 10 partite esposte in paper; l'undicesima vorrebbe puntare 10,00 EUR sull'Under a 1,85: niente
  ingresso finche' un posto non si libera. Se entrasse, vincerebbe +8,08 EUR netti con 3 gol o meno
  e perderebbe -10,00 EUR con 4 o piu'.
- Back Under 3.5 da 10,00 EUR a 2,00 senza copertura: capitale a rischio 10,00 EUR.

**Cosa vedi nell'app**
- In testata: tetto, partite esposte (in tutto, live, paper), aperture bloccate, motivo («tetto
  partite raggiunto: N su M in live»), capitale a rischio.
- In Attivita': riga «tetto partite» sulla partita bloccata (frenata).

**Se qualcosa va storto**
- I due conti diversi (armamento e aperture): vedi capitolo 9, «Punti da decidere» n. 9.
- Paper o live: conti separati per modalita'.

**Per il tecnico**
- D-15 `service.py:3625-3656`, `posti_occupati_per_modo` 3841-3861, `engine.ha_esposizione`
  `engine.py:1827-1850`; statistiche `tetto_partite`, `partite_esposte`, `partite_esposte_live`,
  `partite_esposte_paper`, `aperture_bloccate`, `motivo_blocco`.
- D-45 `service.py:4441-4445` (`engine.OPENING_ROLES`, attivita' `tetto_partite`, motivo
  `max_open_matches`).
- D-13 conto dell'armamento `service.py:3580-3583`.
- D-22 `_ctx_legs_of`, `_open_liability` `service.py:3818-3838`; `engine.event_liability`
  `engine.py:938`; statistica `open_liability`.

---

## 11 - Database («5 tabelle»)

**Cosa fa**
Mike salva tutto in cinque tabelle:
- **Riga di controllo** (una sola): acceso o fermo, paper o live, parametri, statistiche, ora del
  battito. Ogni scrittura aggiunge l'ora di aggiornamento.
- **Schede delle partite** (una per partita): stato, gambe, dati dal vivo, memoria del motore,
  dossier, mercati. Ogni scrittura impone l'ora di aggiornamento = adesso. Piu' schede si scrivono
  in una volta sola.
- **Righe di ordine** (una per gamba): lato, quota, importo, abbinato, stato, modalita', esito, P&L,
  commissione, collegamento chiusura -> apertura.
- **Attivita'**: una riga per ogni fatto (tipo, dati, partita). Se la scrittura fallisce la riga si
  perde; il bot non si ferma mai per questo.
- **Richieste della pagina**: cash out, annulla, salta, riprendi, approva; con il loro esito.
- Mike legge in sola lettura anche lo scanner, il catalogo dei modelli e, per il percorso degli
  ordini paper sul simulatore, la coda condivisa degli ordini (accodamento, lettura, revoca di una
  richiesta ancora in coda, specchio degli ordini).
- Con l'interruttore «canale posizioni» acceso, le righe scritte escono anche sul canale verso lo
  schermo, DOPO la scrittura riuscita.

**Quando**
- Sempre. Letture a pagine da 1000 righe.

**Numeri**
- Pagine da 1000 righe. Richieste: fino a 50 + 200 per giro; appese oltre 10 minuti chiuse.
- Stati chiusi di una partita: regolata, errore, saltata.
- Interruttore «canale posizioni»: di serie spento.

**Esempio con le cifre**
- Un back Under 3.5 da 10,00 EUR a 1,90 e la sua banca di chiusura da 10,10 EUR a 1,88 sono due
  righe di ordine; la seconda porta il numero della prima. A fine partita la prima riceve +8,55 EUR
  (3 gol) o -10,00 EUR (4 o piu'), la seconda il suo esito opposto.

**Cosa vedi nell'app**
- Trade, Storico, Attivita', la testata e le schede delle partite leggono queste tabelle.

**Se qualcosa va storto**
- Errori di lettura o scrittura di controllo e righe: risalgono a chi ha chiamato (vedi capitolo 9,
  riquadri 09 e 12).
- Lettura delle righe di ordine fallita: Mike risponde «non so», mai «nessuna riga».
- Paper o live: una sola tabella per tipo; la modalita' e' scritta su ogni riga.

**Per il tecnico**
- D-90 `db.py:24-53`: `mike_control` (id 1), `mike_events` (`positions`, `live`, `ctx`, `dossier`,
  `markets`), `mike_trades` (colonna `mode`, `signal_key`, `closes_trade_id`), `mike_activity`,
  `mike_requests`; `PAGE_SIZE` = 1000; env `MIKE_CANALE_POSIZIONI`.
- D-91 `read_control`, `set_control` `db.py:59-68`. D-92 `log` `db.py:71-80`.
- D-93 `db.py:88-169` (`STATI_TERMINALI`, `filtro_finestra_eventi`, `list_events`, `upsert_event`,
  `upsert_events`; `get_event` e `delete_events` non usati).
- D-94 `db.py:175-249` (`insert_trade`, `update_trade`, `get_trade`, `open_trades`,
  `trades_for_event`, `live_trades`, `all_trades`).
- D-96 `db.py:417-502` (`pending_requests`, `requests_da_lavorare`, `set_request_status`,
  `fail_stale_processing`).
- D-99 `db.py:601-644` (`live_follow`, `betfair_live_heartbeat` id 1, procedura
  `request_betfair_live_order`, `betfair_live_order_requests`, `betfair_live_orders`; revoca
  «revocata da mike (deadline live)»).

---

## 12 - Riavvio («cosa si rilegge»)

**Cosa fa**
- Al riavvio Mike non ha memoria propria: rilegge dal database
  - la riga di controllo (a ogni giro);
  - le partite seguite: tutte le non chiuse di qualunque eta', piu' le chiuse delle ultime 48 ore,
    con gambe, memoria del motore, dossier e dati dal vivo salvati;
  - le righe di ordine quando servono.
- Si perdono e ripartono da zero solo le memorie interne: orologi della riparazione, della
  scrittura, delle righe frenate in Attivita', memorie temporanee di feed e totali, «stop gia'
  scritto oggi», stato della sveglia e del canale.
- Se l'app e' stata riaperta, Mike riparte fermo, in paper, uscite su manuale (capitolo 9,
  riquadro 02).

**Quando**
- Primo giro dopo l'avvio.

**Numeri**
- Partite chiuse rilette: ultime 48 ore.

**Esempio con le cifre**
- Crash alle 21:10 con un back Under 3.5 da 10,00 EUR a 1,92 appena abbinato ma riga non scritta: al
  riavvio la riparazione dello specchio parte subito (orologio a zero) e ricostruisce la riga,
  10,00 EUR a 1,92, rischio 10,00 EUR. A fine partita la riga riceve +8,74 EUR netti (3 gol o meno)
  o -10,00 EUR (4 o piu').

**Cosa vedi nell'app**
- Le stesse partite, gambe e righe di prima; eventualmente una seconda riga di stop giornaliero nella
  stessa giornata; righe di riparazione in Attivita'.

**Se qualcosa va storto**
- Database muto al riavvio: il controllo dell'apertura dell'app non si conclude e Mike non apre
  niente di nuovo finche' non riesce.
- Paper o live: identico; ogni partita riletta tiene la sua modalita'.

**Per il tecnico**
- D-100 `service.py:3504-3530`, `db.py:99-113`; memorie di processo `service.py:345-386`.
- D-4 `ferma_al_nuovo_avvio` `service.py:3396-3427`.

---

## Frecce

- 01 Scanner -> 05 Freschezza: ogni riga del feed, con l'ora del suo aggiornamento.
- 02 Canale veloce -> 05 Freschezza: solo con l'interruttore acceso, righe di meno di 5 s; vince se
  strettamente piu' recente.
- 05 Freschezza -> 06 Fotografia: riga non oltre 180 s e (45 s o scanner battuto entro 75 s); linee
  osservate entro 90 s e con flusso vivo.
- 04 Dossier -> 06 Fotografia: gol attesi, probabilita' di gol, probabilita' di 4 gol del modello.
- 03 Betfair diretto -> 06 Fotografia: flusso fermo E posizione aperta; al massimo ogni 10 s per
  mercato; solo per chiudere, coprire, proteggere.
- 06 Fotografia -> 07 Linea assente: linea 3.5 o 4.5 assente, non osservata da oltre 90 s o col
  flusso fermo, con una posizione aperta; oppure fotografia non costruibile.
- 06 Fotografia -> 08 Regolamento: mercato chiuso (linea 3.5 chiusa, riga assente 10 minuti, 3 ore
  dal fischio, 100 minuti dal fischio con partita vista in gioco). I vincitori vengono letti da
  Betfair (riquadro 03) al massimo ogni 60 s: nello schema questa freccia non e' disegnata per non
  incrociare le altre.
- 08 Regolamento -> 09 Stop del giorno: il P&L netto delle righe regolate entra nel realizzato del
  giorno di PIAZZAMENTO.
- 09 Stop del giorno -> 10 Posti: P&L del giorno <= -50 EUR: nessuna apertura fino a mezzanotte di
  Roma; altrimenti le aperture passano se i posti della modalita' sono meno di 10.
- 08 Regolamento -> 11 Database: esito, P&L, lordo e commissione su ogni riga; partita regolata.
- 11 Database -> 12 Riavvio: al primo giro dopo l'avvio Mike rilegge controllo, partite (non chiuse
  + chiuse delle ultime 48 ore) e righe.

---

## Punti da decidere (capitolo 10)

Differenze dalla Costituzione e cose strane che riguardano dati e conti. Nessuna e' stata corretta:
le decide l'utente.

1. **Feed illeggibile trattato come vuoto dopo 10 minuti.** Una lettura fallita dello scanner vale
   «nessuna riga» ed e' tenuta come buona: dopo 10 minuti di database dello scanner muto OGNI
   partita va in regolamento con letture da Betfair (cosa strana 2; anche capitolo 9, punto 1).
2. **Partita regolata con le righe ancora aperte.** Nel ramo «2 ore senza esito, punteggio non
   recuperabile, ma il risultato non dipende dal punteggio» la partita diventa regolata SENZA
   aggiornare le righe di ordine: le righe di eventuali cicli chiusi restano «aperte» o «in coda»
   per sempre e contano nelle righe aperte e nel rischio sommato dalle righe. Lo stesso vale per il
   ramo ERRORE «regolamento non determinabile». E' contro la regola scritta nel codice stesso («una
   partita non puo' diventare chiusa con righe non aggiornate») (cosa strana 1; `service.py:4143-4161`).
3. **Totali che nel ripiego mescolano paper e live.** Se la procedura dei totali manca nel database,
   il ripiego filtra per modalita' le righe della giornata ma aggiunge i totali di sempre calcolati
   su TUTTE le righe: realizzato totale, vinte e perse sommano paper e live (cosa strana 12;
   `db.py:394`, `401-411`).
4. **Numeri della Costituzione superati dal codice - freschezza**: Costituzione §5 «riga > 15 s E
   scanner muto > 30 s» e §6 `feed_max_age_s` = 15; il codice usa 45 s e 75 s per decidere, 20 s e
   30 s per ordinare, tetto 180 s, piu' il controllo del flusso dei prezzi (diff. 2).
5. **Numeri della Costituzione superati - rilettura del feed**: Costituzione §17.3 2 s; il codice 4 s,
   10 s con il canale sano (diff. 3). Costituzione §2 «una lettura per ciclo»: una lettura ogni 4 s
   o 10 s, con possibile fonte dal canale 47336 (diff. 15).
6. **Numeri della Costituzione superati - regolamento**: Costituzione §2 e §3 Fase 7 «ogni 30 s»; il
   codice 60 s (30 s solo se il parametro e' 0) (diff. 5).
7. **Costituzione §3 Fase 7 «dopo 2 ore: ultimo punteggio, altrimenti ERRORE»**: il codice ha un
   terzo esito prima dell'errore (chiusura se il risultato non dipende dal punteggio), che e' proprio
   il ramo del punto 2 (diff. 17).
8. **Costituzione §10.B.1 «3.5 UNDER e 4.5 annullata -> la 4.5 regolata come UNDER»**: il codice
   gestisce l'annullo mercato per mercato prima del totale: il rischio descritto non c'e' piu'; la
   Costituzione non e' aggiornata (diff. 12).
9. **Costituzione §2 «ponte partita -> fixture solo da `live_follow`»**: il codice cerca in
   `live_follow` e poi in `omega_events`; anche i commenti del dossier citano solo `live_follow`
   (diff. 7, cosa strana 8).
10. **Probabilita' calibrata dell'Over 4.5 sempre vuota** nel dossier: la voce esiste ma nessuno la
    riempie (cosa strana 13).
11. **Codice non usato da Mike**: lettura di una sola partita e cancellazione di partite non sono
    chiamate da nessun file di produzione (cosa strana 14).
12. **Commissione riletta due volte**: per ogni tentativo di regolamento Mike rilegge le righe dal
    database fino a due volte, senza la memoria del giro (cosa strana 17).
13. **Riga sparita pre-partita per 10 minuti con posizione**: la partita va in regolamento (mercato
    aperto, totale assente) e resta «in regolamento» finche' la riga non torna; se non torna, dopo 2
    ore senza essere mai stata vista in gioco finisce regolata «indipendente» (punto 2) o in errore
    (cosa strana 18).
14. **Filtro competizioni per «contiene»**: «serie a» accetta anche «Serie A Women» o «Serie A2»
    (cosa strana 19).

## Punti non chiariti (capitolo 10)

1. Le procedure del database (`get_mike_aggregates`, `request_betfair_live_order`) e i vincoli delle
   tabelle non sono stati letti (divieto di interrogare il database; migrazioni non aperte).
2. I moduli dei modelli (griglie dei risultati, gol attesi dalle quote, probabilita' di gol dal vivo,
   atlante v4, pressione) non sono stati letti: il tetto x1,25 della pressione risulta solo da un
   commento.
3. Il valore della probabilita' di 4 gol pre-partita dipende dalla griglia del modello Omega: non
   ricalcolato qui, per questo l'esempio del riquadro 04 non riporta la cifra.
4. La regola comune della riconciliazione e quella del flusso dei prezzi (moduli condivisi con Safe)
   sono lette solo nelle righe citate dall'inventario.
5. Quando esattamente il percorso di esecuzione condiviso usa la coda degli ordini (riquadro 11) non
   e' verificato (inventario D, «Non ho capito» 7).

---

## Conto delle 108 schede dell'inventario D

| Schede D | Dove (capitolo, riquadro) |
|---|---|
| 1 | 9-01 |
| 2 | 9-10 (e 9-12) |
| 3 | 9-11 |
| 4 | 9-02, 10-12 |
| 5, 6, 7, 12, 17 | 9-03 (5 anche in 9-12) |
| 8, 9 | 9-04 (9 anche in 9-12) |
| 10 | 9-05, 10-09 |
| 11, 24, 89 | 9-05 |
| 13 | 9-05, 10-10 |
| 14 | 9-05, 10-04 |
| 15 | 9-05, 10-10 |
| 16 | 9-06, 9-12 |
| 18, 19, 20, 67, 68, 69, 70, 71, 73 | 9-09 |
| 21, 23, 95 | 10-09 |
| 22, 45 | 10-10 (45 anche in 9-06) |
| 25, 26, 27, 35, 39, 44, 48, 49, 50 | 9-06 |
| 28 | 9-06, 10-07 |
| 29 | 9-08, 10-08 |
| 30, 31, 32, 33 | 10-08 (riassunte in 9-08) |
| 34, 37, 38 | 10-07 (e 9-06) |
| 36 | 9-06, 10-03 |
| 40, 41, 42, 43, 46, 47, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61 | 9-07 |
| 62, 63 | 9-03 |
| 64, 65, 66 | 10-08 |
| 72 | 9-01 |
| 74, 75 | 9-10 |
| 76, 77 | 9-04, 10-02 |
| 78, 79, 83, 85, 97 | 10-01 (97 anche in 9-04) |
| 80, 81, 86, 87 | 10-05 |
| 82 | 10-03 |
| 84, 88 | 10-06 |
| 90, 93, 94, 99 | 10-11 |
| 91, 96 | 9-03, 10-11 |
| 92 | 9-09, 10-11 |
| 98, 101, 102, 103, 104, 105, 106, 107, 108 | 10-04 |
| 100 | 10-12 |

**Numeri rimasti fuori da entrambi i capitoli: nessuno.** Tutte le 108 schede compaiono in almeno
una scheda di riquadro. Differenze dalla Costituzione 1-21 e cose strane 1-20 dell'inventario D:
tutte riportate nei «Punti da decidere» del capitolo 9 o del capitolo 10.
