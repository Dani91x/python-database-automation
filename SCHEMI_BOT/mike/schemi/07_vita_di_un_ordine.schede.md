# Mike - Capitolo 7: la vita di un ordine (schede)

Schema: `07_vita_di_un_ordine.html` (sorgente `07_vita_di_un_ordine.lifecycle.json`).
Fonte dei fatti: `SCHEMI_BOT/mike/inventario/C_servizio_e_ordini.md` (schede C-n), con i rimandi a
`A_calcoli_e_guardie.md` (A-n) e `D_giro_e_conti.md` (D-n). Tre punti ricontrollati sul codice:
`Betfair/safe_strategy/execution.py:514` e `:531-534`, `Betfair/omega/omega_market.py:735-746` e
`:950-1162` (piazza e riduci), `Betfair/mike/service.py:860-862`, `:905-943`, `:1395-1399`, `:2492`.

**Schede dell'inventario usate in questo file:**
- C: 1, 2, 5, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 32, 35, 36, 37, 38, 39, 40, 41,
  42, 43, 46, 47, 48, 49, 50, 51, 52, 53, 59, 60, 61, 62.
- A: 3, 4, 20, 21, 22, 29, 41, 44, 45, 65, 66, 68, 69, 70, 88, 91, 93.
- D: 30, 31, 32, 33, 40, 41, 46, 47, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 64, 65, 66.
(I freni che fermano un ordine prima dell'invio sono spiegati uno per uno nel capitolo 8,
`08_freni_e_protezioni.schede.md`.)

Come si legge: ogni riquadro dello schema porta un numero (01-12). La scheda con lo stesso numero lo
spiega. Le parole fra «» sono i messaggi o i motivi che l'utente legge nell'app. «Simulatore» e' il
programma che in paper esegue gli ordini come farebbe Betfair (ritardo, coda, abbinamenti parziali).

Parole usate in tutte le schede:
- **Ordine a mercato (tutto o niente)**: l'ordine prende subito la quota migliore; la parte che non si
  abbina in quell'istante viene cancellata. Non resta mai sul libro.
- **Ordine in coda**: l'ordine resta sul libro alla quota chiesta e aspetta che qualcuno lo prenda.
- **Cade alla sospensione**: se il mercato si sospende (gol, fischio d'inizio) la parte non abbinata
  viene cancellata da Betfair.
- **Riga dell'ordine**: la riga che compare nella scheda Trade. Mike la scrive PRIMA di mandare
  l'ordine.

---

## 01 - Ordine deciso

**Cosa fa**
- A ogni giro Mike guarda la partita e decide cosa fare: puntare, bancare, ritirare un ordine, o
  niente.
- Ogni ordine deciso ha un ruolo (a cosa serve), una selezione, un lato (punta o banca), una quota e un
  importo.
- La quota viene portata al gradino valido piu' vicino della scala Betfair. L'importo viene
  arrotondato al centesimo.

**Quando**
- A ogni giro della partita: circa ogni 1 secondo quando c'e' movimento, ogni 5 secondi a riposo.

**Numeri**
- Importo minimo di un qualunque ordine: 0,01 euro. Sotto, Mike non manda niente.
- Una quota vale solo se esiste, e' un numero e supera 1,00.
- I ruoli sono 11. Cinque APRONO rischio: ingresso del giro, ultimo ingresso, seconda puntata,
  copertura Over 4,5, rientro. Sei lo RIDUCONO: banca di green del giro, uscita al fischio, chiusura
  dell'Under, chiusura dell'Over, banca di green del rientro, chiusura chiesta dall'utente.

**Esempio con le cifre**
- Mike decide di bancare l'Under 3,5 a 1,483 per 10,137 euro. L'ordine diventa: banca 10,14 euro a
  1,48.
- Se si abbina e Mike aveva puntato 10,00 euro a 1,50: con 0-3 gol Mike incassa +5,00 dalla punta e
  paga -4,87 sulla banca = +0,13 euro. Con 4 o piu' gol perde -10,00 sulla punta e incassa +10,14
  sulla banca = +0,14 euro (prima della commissione).

**Cosa vedi nell'app**
- Nella scheda della partita il motivo della decisione (per esempio «uscita proposta all'utente»).
- Con le uscite manuali (di serie) un'uscita decisa NON diventa un ordine: diventa una proposta che
  approvi tu. Lo spiega il capitolo delle uscite.

**Se qualcosa va storto**
- Quota non valida o importo sotto 0,01 euro: nessun ordine.
- Se la stessa identica richiesta (stessa quota, stesso importo) e' gia' stata rifiutata dal mercato,
  Mike non la ripropone uguale: aspetta che quota o importo cambino.

**Paper o live**
- Identico.

**Per il tecnico**
- `engine.decide` (`engine.py:2164-2216`), `_place` (`engine.py:1487-1491`), ruoli
  `OPENING_ROLES`/`CLOSING_ROLES` (`engine.py:46-65`), `price_ok`/`size_ok` (`engine.py:599-625`),
  memoria dei rifiuti `registra_rifiuto`/`tentativo_gia_rifiutato` (`engine.py:1501-1555`), motivo
  «gia' rifiutata a mercato (...) non si ripropone identica» (`motivo_del_rifiuto`, `engine.py:1558`).
  Inventario A-3, A-4, A-29, A-66, A-68, A-69, A-70.

---

## 02 - Controlli prima dell'invio

**Cosa fa**
- Prima di scrivere la riga e mandare un ordine a mercato, Mike fa questi controlli, in quest'ordine.
  Al primo «no» si ferma: l'ordine non nasce (riquadro 12).
  1. Mercato e selezione sono noti?
  2. Se e' una chiusura: c'e' gia' una chiusura uguale (stesso ruolo, stesso giro, stesso lato) in
     attesa? Se si', la nuova non parte.
  3. Se e' la copertura: il freno delle coperture e' scattato? Se si', non parte.
  4. Il mercato e' APERTO? Sospeso, chiuso o sconosciuto: non parte.
  5. I prezzi arrivano dalla lettura diretta di Betfair (flusso dei prezzi interrotto) e l'ordine
     apre rischio? Se si', non parte. Chiusure e copertura invece partono.
  6. I prezzi sono vivi? Se no, NESSUN ordine parte, nemmeno le chiusure.
  7. La quota voluta c'e' ancora? Per una punta la miglior quota di punta deve essere almeno quella
     voluta; per una banca la miglior quota di banca deve essere al massimo quella voluta.
  8. Modalita' prova («a secco»)? Mike scrive soltanto «avrei piazzato».
  9. Se gli «importi esatti» sono spenti: una punta sotto 2,00 euro viene alzata al minimo legale.
  10. In paper: il simulatore e' raggiungibile?
  11. Mike scrive la riga dell'ordine. Se la scrittura fallisce, l'ordine non parte.
- Per la banca che resta in coda i controlli sono gli stessi nella sostanza (prezzi vivi, mercato
  aperto, niente doppioni, freno d'emergenza sulle aperture), in un ordine un poco diverso.

**Quando**
- Per ogni ordine nuovo, subito dopo la decisione, nello stesso giro.

**Numeri**
- Prezzi vivi: la riga dei prezzi ha al massimo 45 secondi, oppure lo scanner ha scritto entro 75
  secondi; oltre 180 secondi mai.
- Freno delle coperture: 3 rifiuti con lo stesso motivo, e almeno 15 secondi fra due tentativi.
- Importi esatti: accesi di serie. Da spenti: minimo 2,00 euro, passi da 0,50 euro, arrotondamento
  per eccesso.

**Esempio con le cifre**
- Mike vuole chiudere bancando l'Under 3,5 a 1,40. La miglior quota di banca e' 1,42: la quota voluta
  non c'e' piu'. Nessuna riga, nessun ordine; nell'attivita' «non abbinabile: disponibile 1,42».
- Con importi esatti spenti, una copertura da 1,35 euro diventa 2,00 euro (+48 per cento).

**Cosa vedi nell'app**
- Nell'attivita' una riga col motivo: mercato sospeso, flusso interrotto, prezzi vecchi, quota non
  disponibile, importo alzato, chiusura gia' in volo.

**Se qualcosa va storto**
- Righe della partita non leggibili al controllo 2: Mike fa come se la chiusura fosse gia' in volo
  (nel dubbio, nessun ordine).
- Ogni «no» e' spiegato nel capitolo 8, riquadro per riquadro.

**Paper o live**
- I controlli 1-9 sono identici. Il 10 esiste solo in paper. In live, dopo la riga, ci sono altri due
  freni: freno d'emergenza e modo ordini (solo sulle aperture), poi l'interruttore dei soldi veri (su
  ogni ordine). Vedi capitolo 8, riquadri 09 e 10.

**Per il tecnico**
- `execute_place` `service.py:618-943` (ordine dei controlli `:656-753`); anti-doppione
  `_gia_appoggiata` `:1349-1387`; seconda barriera del freno copertura `:677-690`; mercato, ripiego
  REST, feed stantio, prezzo `:691-740`; `APERTURE_MIKE` `:1154`; legalizzazione `:746-753`
  (`engine.legalize_back_size`, `engine.needs_submin`); freschezza `feed.feed_fresh`
  (`feed.py:316`, uso `:428-431`). Banca in coda: `_run_event` `service.py:4461-4515`.
  Attivita': `skip`, `no_fill` (`feed_stantio`, `flusso_interrotto`), `place_saltato`,
  `size_legalized`, `would_place`, `error reserve_failed`. Inventario C-15..C-20, C-36, C-43, A-20,
  A-22, D-47.

---

## 03 - Inviato

**Cosa fa**
- Mike scrive prima la riga dell'ordine, «in attesa», e SOLO DOPO manda l'ordine. Cosi' un ordine
  non puo' esistere sul mercato senza una riga che lo racconti.
- Poi manda l'ordine: in paper al simulatore, in live a Betfair.
- Ogni ordine porta un riferimento «mike-t» + numero della riga, e in live il marchio «mike». Serve a
  ritrovarlo fra gli ordini del conto.

**Quando**
- Subito dopo i controlli del riquadro 02.

**Numeri**
- Riferimento dell'ordine: al massimo 32 caratteri.
- Paper: dopo l'invio di un ordine a mercato Mike ASPETTA la risposta del simulatore fino a 15
  secondi (il minore fra 15 secondi e il ritardo d'invio del mercato piu' 3 secondi). Durante questa
  attesa tutto il giro e' fermo, anche le altre partite.
- Paper: un ordine a mercato senza nessuna notizia dal simulatore per 60 secondi viene dichiarato
  non eseguito.
- Un ordine a mercato ancora «in attesa» dopo 120 secondi viene ritirato (se l'esito e' noto) o
  mandato in verifica (se l'esito e' ignoto).

**Tabella: che tipo di ordine parte davvero, per ogni ruolo**

| Ruolo (a cosa serve) | Come parte DAVVERO su Betfair e sul simulatore | Parte non abbinata | Rifiutato | Esito ignoto |
|---|---|---|---|---|
| Ingresso del giro (punta Under 3,5 prima del fischio) | a mercato, tutto o niente, cade alla sospensione | cancellata subito | niente posizione; non si ripete uguale | verifica, niente aperture |
| Ultimo ingresso (punta Under 3,5 a 10 minuti dal fischio) | a mercato, tutto o niente, cade alla sospensione. La regola dice «resta in gioco»: NON succede (Punti da decidere 1) | cancellata subito | come sopra | come sopra |
| Seconda puntata (Under 3,5 dopo un gol presto) | a mercato, tutto o niente, cade alla sospensione | cancellata subito | come sopra | come sopra |
| Copertura (punta Over 4,5) | a mercato, tutto o niente; sotto 2,00 euro con «piazza e riduci», sempre tutto o niente | cancellata subito | come sopra, e conta per il freno delle coperture | verifica, nessun conteggio |
| Rientro (punta Under 4,5) | a mercato, tutto o niente, cade alla sospensione | cancellata subito | come sopra | come sopra |
| Banca di green del giro (prima del fischio) | di serie IN CODA sul libro, cade alla sospensione. Con l'uscita «a mercato» scelta dall'utente: tutto o niente | resta in coda | riga chiusa, non si ripete uguale | verifica |
| Uscita al fischio (banca 2 tick sotto l'ingresso) | SEMPRE in coda sul libro, cade alla sospensione | resta in coda | come sopra | verifica |
| Banca di green del rientro | come la banca di green del giro | resta in coda | come sopra | verifica |
| Chiusure (cash out, uscite in perdita, tetto di perdita, chiusura dell'utente) | a mercato, tutto o niente, segnata «riduce l'esposizione». I freni delle aperture non la fermano | cancellata subito | niente; al giro dopo Mike ripropone a un'altra quota | verifica |
| Ritiro di un ordine | annullo vero: al simulatore in paper, a Betfair in live | - | annullo non confermato: verifica | verifica |

- In live, con la valvola «banca in coda in live» spenta dall'utente, anche le banche di green del giro
  e del rientro partono a mercato. L'uscita al fischio resta sempre in coda.

**«Piazza e riduci»: come si piazza un importo sotto il minimo di Betfair**
- Betfair Italia non accetta una punta sotto 2,00 euro (per la banca il codice usa 0,50 euro). Mike
  con gli «importi esatti» accesi punta anche 1,26 euro. Ci arriva cosi':
  1. Mike parcheggia una punta da 2,00 euro a una quota che nessuno puo' prendere (per esempio 1000).
  2. Mike riduce quell'ordine di 0,74 euro: restano 1,26 euro. Mike rilegge l'ordine da Betfair per
     essere sicuro che il taglio ci sia.
  3. Mike cambia la quota da 1000 a quella vera, per esempio 3,90.
  4. Tutto o niente: la parte che non si abbina subito viene ritirata.
- Esempio: copertura Over 4,5 da 1,26 euro a 3,90. Se si abbina: con 5 o piu' gol +1,26 x 2,90 =
  +3,65 euro lordi; con 0-4 gol -1,26 euro.
- Se un passo fallisce: se il parcheggio e' rifiutato, nessun ordine e' nato (rifiuto certo). Se il
  taglio non e' confermato, Mike ritira il parcheggio; se il ritiro riesce e' un rifiuto certo,
  altrimenti l'esito e' ignoto e si va in verifica.
- In gioco il cambio di quota con un importo sotto il minimo e' stato rifiutato da Betfair 171 volte
  su 171 («non piazzato»): e' il caso tipico che fa scattare il freno delle coperture (capitolo 8,
  riquadro 05).
- In paper il simulatore fa la stessa sequenza, sempre tutto o niente. Se il libro dice gia' che non
  si puo' abbinare, rifiuto certo senza mandare niente.

**Esempio con le cifre**
- Paper, in gioco, ritardo d'invio 5 secondi: Mike punta 10,00 euro sull'Under 3,5 a 1,50. Aspetta
  fino a 8 secondi. Il simulatore risponde «abbinato 10,00 a 1,50». La riga passa ad aperta.

**Cosa vedi nell'app**
- Nella scheda Trade una riga «in attesa», poi aperta o chiusa.
- Nell'attivita': ordine piazzato, ordine in attesa, oppure il motivo del rifiuto.

**Se qualcosa va storto**
- Paper, simulatore spento o non collegato: ordine NON eseguito, detto chiaramente, al massimo una
  volta al minuto per partita; le aperture della partita si fermano (capitolo 8, riquadro 04).
- Il primo ordine paper dopo l'avvio del programma accende il collegamento al simulatore: finche'
  non e' collegato l'ordine risulta «simulatore non raggiungibile».
- Live, interruttore soldi veri spento: l'ordine non parte e resta in verifica (riquadro 06).

**Paper o live**
- Paper: il simulatore applica ritardo, coda e abbinamenti parziali come Betfair. Mike aspetta fino a
  15 secondi la risposta.
- Live: l'ordine va a Betfair direttamente, con la sessione di Omega, marchiato «mike».

**Per il tecnico**
- Riga di riserva `_trade_row` `service.py:546-580`, `_insert_trade_row` `:597-615`; paper
  `:754-883`, attesa `:860-862`, `ATTESA_ESITO_TAKER_MAX_S` 15 s `:1399`, `_SCADENZA_TAKER_PAPER_S`
  60 s `:1395`; live `:780-781`, `:884-943`; `_PENDING_STALE_S` 120 s `:50`, uso `_run_event:4330-4344`.
- Tipo d'ordine: paper `execution.py:514` (`persistence="LAPSE"`), `:531-534` (FOK anche sotto il
  minimo per la porta di Mike, `porta_ordini.py:129` `submin_fill_or_kill`); banca in coda senza FOK
  `porta_ordini.py:77-78`; live `omega_market.py:735` (`persistenceType: LAPSE` fisso), `:746`
  (FOK). Valvola `_live_exit_override` `service.py:1235-1265`; banca in coda `_is_resting_leg`
  `:1330-1346`.
- Piazza e riduci: `omega_market.place_submin_live` `:950-1162` (parcheggio `:1027-1071`, taglio
  `:1073-1097`, verifica `:1104-1125`, riprezzo `:1143-1162`, commento dei 171 rifiuti `:1144-1147`);
  minimi `SUBMIN_MIN_BACK` 2,00 / `SUBMIN_MIN_LAY` 0,50 `:823-825`; paper `execution._rifiuto_submin_fok`.
- Riferimenti `mike-t<id>` e `mike-c<bet_id>` `porta_ordini.py:36-60`. Inventario C-14, C-15, C-21,
  C-22, C-24, C-32, C-35, C-37, C-59..C-62.

---

## 04 - Abbinato

**Cosa fa**
- L'ordine si e' abbinato: Mike ha la posizione.
- Mike scrive sulla riga la quota media vera, l'importo abbinato, l'esposizione e il numero della
  scommessa. La riga diventa «aperta».
- Mike scrive anche tre colonne: importo chiesto, importo abbinato, residuo.

**Quando**
- Ordine a mercato: subito, alla risposta di Betfair o del simulatore.
- Banca in coda: quando Betfair o il simulatore dicono che si e' abbinata tutta (riquadro 08).

**Numeri**
- Esposizione di una punta = importo. Esposizione di una banca = importo x (quota - 1).
- Commissione scritta sulla riga: 5 per cento (parametro).

**Esempio con le cifre**
- Copertura Over 4,5 da 2,26 euro a 6,6, abbinata. Con la punta Under 3,5 da 10,00 a 1,50 gia' in
  mano: con 0-3 gol +2,49 euro; con 4 gol -12,26 euro; con 5 o piu' gol +2,02 euro (netti).

**Cosa vedi nell'app**
- La riga nella scheda Trade diventa aperta, con quota e importo veri.
- Nell'attivita' «piazzato», con chiesto e residuo; per la banca in coda «abbinata tutta».

**Se qualcosa va storto**
- Live: se la scrittura sul database fallisce, l'ordine resta comunque abbinato su Betfair; Mike
  scrive un avviso critico. La riparazione ogni 30 secondi riscrive la riga mancante con importo e
  quota abbinati.

**Paper o live**
- Identico; cambia solo chi risponde (simulatore o Betfair).

**Per il tecnico**
- Live `service.py:884-906` (`X.aggiorna_trade`); paper `_segui_ordini_paper_su_runner`
  `:1595-1662`; banca in coda `_aggiorna_riga_resting` `:2092-2121`; riparazione dello specchio
  `_reconcile_trades` `:4874-4974`. Attivita' `place`, `fill_resting`, `reconcile_fix`.
  Inventario C-22, C-23, C-40, C-47, A-38, D-59.

---

## 05 - Chiuso nei conti

**Cosa fa**
- A fine partita Mike legge da Betfair chi ha vinto nei due mercati e scrive su ogni riga: vinta,
  persa o nulla, e il profitto o la perdita netti di commissione.
- Le righe mai abbinate (ritirate, scadute, rifiutate) sono gia' chiuse a zero.

**Quando**
- A mercato chiuso. Mike rilegge i risultati da Betfair al massimo ogni 60 secondi finche' Betfair
  non li dichiara.

**Numeri**
- Lettura dei risultati: ogni 60 secondi (parametro; minimo 5 secondi; con 0 diventa 30 secondi).
- Dopo 2 ore senza risultato: Mike usa l'ultimo punteggio visto; se non c'e' e il risultato non
  dipende dai gol chiude lo stesso; altrimenti la partita va in «da sistemare».
- Commissione: quella scritta sulle righe al momento dell'ordine, non quella di oggi.
- Se la scrittura delle righe fallisce Mike riprova fino a 5 volte, poi chiude la partita e grida.

**Esempio con le cifre**
- Punta Under 3,5 10,00 a 1,50 e copertura Over 4,5 2,26 a 6,6. Finisce 3-2 (5 gol): l'Under 3,5
  perde -10,00 (nessuna commissione su un mercato in perdita); l'Over 4,5 vince +2,26 x 5,6 =
  +12,66 lordi, meno il 5 per cento = +12,02 netti. Totale partita +2,02 euro.
- Se Betfair annulla il mercato 4,5: la copertura vale 0, l'Under 3,5 si regola col suo risultato.

**Cosa vedi nell'app**
- La partita passa a regolata; ogni riga porta esito e profitto o perdita.

**Se qualcosa va storto**
- Con un ordine a esito ignoto il regolamento aspetta: prima si chiarisce l'ordine (riquadro 07).
- Nel ramo «risultato che non dipende dai gol» e nel ramo «da sistemare» le righe NON vengono
  aggiornate (Punti da decidere 15).

**Paper o live**
- Identico: anche in paper i risultati si leggono da Betfair.

**Per il tecnico**
- `settle_plan`, `market_winner`, `market_voided`, `final_total_from_books` `service.py:1010-1090`;
  regolamento `_run_event` `:4073-4185`; `_settle_trades` `:5256-5362`; `_retry_settle_rows`
  `:5189-5217`; commissione dalle righe `:5220-5253`; `_SETTLE_MAX_WAIT_S` 7200 s.
  Inventario C-27, D-30..D-33, D-64..D-66, A-108.

---

## 06 - Esito ignoto

**Cosa fa**
- Mike ha mandato l'ordine ma non sa se esiste: la risposta si e' persa (rete caduta, tempo scaduto,
  nessuna conferma).
- Mike NON lo dichiara «non piazzato» e NON lo ritira per tempo: potrebbe essere vivo o abbinato.
- Finche' non e' chiarito: l'ordine conta nel rischio come abbinato per intero; nessuna apertura
  nuova sulla partita (nemmeno la copertura); il regolamento aspetta. Chiusure e ritiri continuano.

**Quando**
- Live: errore dopo l'invio, tempo scaduto, nessun resoconto, interruttore soldi veri spento.
- Paper: il simulatore riporta «errore» (esito dubbio, per esempio un «piazza e riduci» interrotto).
- Banca in coda: non e' piu' fra gli ordini vivi di Betfair senza una sospensione in corso; oppure
  alla riapertura dopo una sospensione Betfair non sa dire cosa e' successo.
- Un ritiro che Betfair non conferma.
- Una riga scritta ma la cui risposta si e' persa («riserva orfana»).

**Numeri**
- Nessuna soglia: nessun limite di tempo, mai ritirato per tempo.
- Nel rischio conta l'importo PIENO. Esempio: ordine da 100 euro con 0,01 abbinato noto: conta 100.

**Esempio con le cifre**
- Live, Mike manda la banca di green 10,10 euro a 1,86 e la rete cade. La riga resta «in verifica».
  Il rischio della partita conta quella banca come abbinata tutta. Nessun nuovo ingresso.

**Cosa vedi nell'app**
- Nell'attivita' un avviso critico «ordine in verifica» (al massimo una volta ogni 45 secondi).
- Nella scheda della partita il motivo «(ordine a esito ignoto: nessuna apertura)».
- In testata il numero delle partite in verifica.

**Se qualcosa va storto**
- Se la verifica non riesce mai a leggere Betfair, la partita resta bloccata sulle aperture e il
  regolamento resta sospeso: serve guardare a mano.

**Paper o live**
- Paper: la risposta la da' il simulatore. Un ordine a mercato paper senza NESSUNA notizia per 60
  secondi viene invece dichiarato non eseguito (Punti da decidere 8).
- Live: la risposta la da' Betfair (riquadro 07).

**Per il tecnico**
- Stato `pending_reconcile` (`engine.STATUS_RECONCILE`); `has_unknown_orders` `engine.py:1822`;
  `_strip_openings` `:1854-1879`; `_assume_matched` `:918-935`; `event_liability` `:938-947`.
  Live `service.py:907-918`; paper `:1543-1594`; banca in coda `:1903-2089` (punti 5-6), `:2318-2401`;
  riserve orfane `:4813-4871`; `_esito_ignoto` `:4722-4736`.
  Attivita' `reconcile_pending`. Inventario C-22, C-39, C-46, C-50, C-53, A-44, A-45, A-88, A-90,
  D-40, D-54, D-58.

---

## 07 - Verifica (si rilegge l'ordine)

**Cosa fa**
- Mike rilegge l'ordine alla fonte per sapere com'e' andata. Tre risposte possibili:
  - **confermato**: l'ordine esiste ed e' abbinato: diventa posizione (riquadro 04) con importo e
    quota veri;
  - **mai piazzato**: l'ordine non esiste: la riga si chiude a zero (riquadro 10);
  - **ancora non si sa**: si riprova piu' tardi.
- Mike riconosce il suo ordine in tre modi: dal numero della scommessa scritto sulla riga, dal
  riferimento «mike-t» + numero della riga, o dal vecchio riferimento della gamba (solo se mercato e
  selezione coincidono).

**Quando**
- Al massimo una volta ogni 60 secondi per partita, finche' c'e' un ordine a esito ignoto.

**Numeri**
- Ritmo della verifica: il maggiore fra 5 secondi e il tempo di lettura del regolamento (60 secondi
  di serie).

**Esempio con le cifre**
- Live: la banca di green 10,10 euro a 1,86 era in verifica. Betfair la mostra abbinata 10,10 a 1,86:
  confermata, riga aperta, e Mike non manda una seconda banca.

**Cosa vedi nell'app**
- Nell'attivita' «riparazione: confermata», «riparazione: mai piazzata», oppure l'avviso critico
  «Betfair non raggiungibile».

**Se qualcosa va storto**
- Betfair non raggiungibile: nessuna ipotesi, si riprova.
- Banca in coda sparita alla sospensione, in live: Mike dovrebbe rileggerla per numero di scommessa,
  ma lo sportello di Mike verso Betfair non ha quella lettura. Risultato: in live quella banca va
  SEMPRE in verifica invece di essere dichiarata scaduta (Punti da decidere 5).

**Paper o live**
- Paper: se l'ordine e' sul simulatore decide il simulatore; se non e' mai arrivato al simulatore,
  Mike lo dichiara mai piazzato subito.
- Live: decide Betfair (ordini vivi e ordini chiusi di Mike).

**Per il tecnico**
- `_reconcile_unknown` `service.py:4977-5074` (regola comune `X.reconcile_decision`), ritmo
  `:4351-4359`; `_ordine_della_riga` `:2229-2289`, `_ordine_di` `:2290-2315`, `campo_ordine`
  `:2168`; `_rileggi_ordine_appoggiato` `:2467-2507` con `getattr(market, "order_state_by_bet_id")`
  `:2492`: `_RealMarket` (`:120-231`) non la espone. Attivita' `reconcile_fix`, `reconcile_pending`
  «betfair_non_raggiungibile». Inventario C-48, C-49, C-52, D-41, D-60.

---

## 08 - In coda (banca appoggiata)

**Cosa fa**
- La banca d'uscita resta sul libro alla quota chiesta e aspetta chi la prenda. Mike non paga lo
  spread: se lo fa pagare.
- Mike la segue a ogni giro: quanto si e' abbinata e quanto resta.
- Ogni banca in coda cade alla sospensione: al gol o al fischio Betfair cancella la parte non
  abbinata.

**Quando**
- Uscita al fischio: SEMPRE in coda.
- Banca di green del giro prima del fischio e banca di green del rientro: in coda di serie (uscita
  «appoggiata»). Con l'uscita «a mercato» partono tutto o niente.
- Mike non appoggia la banca se il mercato non e' operabile (sospeso, chiuso, sconosciuto): aspetta la
  riapertura. L'uscita al fischio si appoggia solo a mercato aperto E gia' in gioco.

**Numeri**
- Live: a ogni giro Mike chiede a Betfair gli ordini vivi di Mike (una lettura per banca per giro).
- Soglia per dire «ancora viva»: residuo oltre 0,009 euro.

**Esempio con le cifre**
- Uscita al fischio: banca 10,14 euro a 1,48. Betfair accetta, abbinato 0: riga in attesa con il
  numero della scommessa, residuo 10,14. Al 2' Betfair dice abbinato 10,14: riga aperta, «abbinata
  tutta». Risultato bloccato: +0,13 / +0,14 euro sui due esiti (prima della commissione).

**Cosa vedi nell'app**
- Nell'attivita' «banca appoggiata», poi «abbinata tutta» o «parziale x su y, residuo r vivo».
- Nella scheda Trade la riga in attesa con chiesto, abbinato, residuo.

**Se qualcosa va storto**
- Lettura di Betfair fallita: si riprova al giro dopo, niente inventato.
- La banca non e' piu' fra gli ordini vivi e non c'e' una sospensione: verifica (riquadro 06).
- Sospensione con banca viva: Mike lo annota e alla riapertura rilegge l'ordine: ancora viva, abbinata,
  in parte, scaduta, oppure ignota.
- Stessa banca gia' in attesa (stesso ruolo, giro e lato): la nuova non nasce.
- Betfair rifiuta la banca senza lasciare tracce: riga chiusa, rifiuto annotato. Con tracce (numero
  di scommessa o abbinato presenti): verifica.

**Paper o live**
- Paper: la banca sta sul libro del simulatore; alla sospensione Mike la fa SEMPRE scadere (regola di
  Betfair applicata a mano). Senza notizie dal simulatore aspetta senza limite (Punti da decidere 10).
- Live: la banca sta su Betfair, che decide lui quando farla scadere.

**Per il tecnico**
- `_is_resting_leg` `service.py:1330-1346`; paper `_piazza_resting_paper` `:1665-1724`; live
  `_piazza_resting_live` `:1903-2089`; `_segui_resting_live` `:2318-2401`; `_resting_in_attesa`
  `:1762-1798`; sospensione `_sorveglia_sospensione` `:2872-2962`; `engine.appoggiabile_in_gioco`
  `engine.py:577-587`. Attivita' `place_resting`, `fill_resting`, `attesa_riapertura`,
  `mercato_sospeso`, `rilettura_alla_riapertura`. Inventario C-35, C-36, C-41, C-43, C-46, C-50, C-51,
  A-26, D-42.

---

## 09 - Abbinato in parte

**Cosa fa**
- Solo una parte dell'importo si e' abbinata. La posizione vale per la parte abbinata.
- Il resto:
  - ordine a mercato (tutto o niente): la parte non abbinata e' gia' cancellata;
  - banca in coda: la parte non abbinata resta sul libro e Mike continua a seguirla.

**Quando**
- Ordine a mercato: se Betfair riporta un abbinamento parziale.
- Banca in coda: quando qualcuno ne prende solo un pezzo.
- Alla riapertura dopo una sospensione: la banca si era abbinata in parte prima di scadere.

**Numeri**
- Soglia: abbinato oltre 0,009 euro ma meno del chiesto meno 0,009 euro.

**Esempio con le cifre**
- Banca in coda 10,14 euro a 1,48: abbinati 4,00, residuo 6,14 vivo. La riga resta in attesa con
  importo 4,00. Se poi il mercato si sospende e la banca scade: 4,00 restano posizione, 6,14 cancellati.
- Ritiro di una banca 10,10 a 1,86: Betfair conferma annullati 6,10 e abbinati 4,00 nel frattempo:
  restano 4,00 a 1,86 di posizione.

**Cosa vedi nell'app**
- Nell'attivita' «parziale x su y, residuo r» (critica se viene da un ordine a mercato).

**Se qualcosa va storto**
- Dopo un abbinamento in parte il motore decide il resto al giro dopo: ri-appoggia se la finestra e'
  aperta, altrimenti copre.

**Paper o live**
- Paper: in paper, alla riapertura, una banca abbinata in parte e poi annullata viene chiamata
  «abbinata» e non «parziale» (Punti da decidere 12). I numeri sulla riga sono comunque quelli veri.
- Live: come descritto.

**Per il tecnico**
- Live `execution.py:933-944` (attivita' `place_parziale`); `_classifica_ordine` `service.py:2435-2465`;
  `_chiudi_gamba_scaduta` `:2510-2548`; `_applica_esito_riapertura` `:2549-2604`; mappa paper
  `:2934`. Inventario C-22, C-38, C-47, C-50, C-52, C-53, D-61.

---

## 10 - Ritirato o scaduto

**Cosa fa**
- L'ordine non e' piu' sul mercato e non si e' abbinato (o si e' abbinato solo in parte): la riga si
  chiude. La parte non abbinata vale zero nei conti.
- Tre strade:
  - **ritirato**: Mike (o l'utente) lo annulla. Prima Mike annulla sul mercato, poi scrive la riga;
  - **scaduto alla sospensione**: la banca in coda e' caduta al gol o al fischio;
  - **mai piazzato**: la verifica ha stabilito che l'ordine non e' mai esistito.

**Quando**
- Il motore decide un ritiro (per esempio l'ultimo ingresso non abbinato, la chiusura da riprezzare).
- L'utente preme «Annulla ordini», «Cash out» o «Flatten».
- Un ordine a mercato resta in attesa oltre 120 secondi con esito noto.
- Il mercato si sospende con una banca in coda viva.

**Numeri**
- Delle righe ritirate e mai abbinate Mike tiene in memoria solo le ultime 5 per ruolo (la riga nel
  database resta).

**Esempio con le cifre**
- Uscita al fischio: banca 10,14 euro a 1,48, mai abbinata; gol al 2', mercato sospeso, la banca
  scade. Riga chiusa «scaduta alla sospensione». Al giro dopo il motore ne appoggia una nuova se i
  180 secondi della finestra non sono finiti.

**Cosa vedi nell'app**
- Nell'attivita' «annullo richiesto» e «esito dell'annullo», oppure «ordine scaduto alla
  sospensione» (critica), oppure «riparazione: mai piazzata».
- «Annulla ordini»: «Annullati N ordini sul book», con avviso se qualche annullo non e' confermato.

**Se qualcosa va storto**
- Annullo non confermato: l'ordine forse e' vivo: verifica (riquadro 06). Mai dichiarato ritirato un
  ordine forse vivo.
- Abbinato durante l'annullo: la parte abbinata resta posizione (riquadro 09).
- Paper, simulatore che non ha ancora dato il numero della scommessa: Mike segna «annullo richiesto»,
  manda l'ordine in verifica e annulla appena conosce il numero.

**Paper o live**
- Paper: annullo sul simulatore. Alla sospensione la banca scade sempre, per regola.
- Live: annullo su Betfair. Alla sospensione decide Betfair.

**Per il tecnico**
- `_mark_trade_cancelled` `service.py:5077-5186`; `_request_cancel` `:3253-3280`; ritiri del motore
  `_run_event:4446-4457`; `engine._cancel_live` `engine.py:1482-1484`; `prune_dead_legs`
  `engine.py:848-885` (`MAX_CANCELLED_PER_ROLE` 5); scaduta `_chiudi_gamba_scaduta`
  `service.py:2510-2548` (`meta.phase="lapsed"`). Attivita' `cancel`, `cancel_richiesto`,
  `cancel_esito`, `ordine_scaduto_alla_sospensione`. Inventario C-38, C-51, C-53, A-41, A-65, D-40,
  D-46, D-61, D-62.

---

## 11 - Rifiutato dal mercato

**Cosa fa**
- Betfair (o il simulatore) risponde con un «no» definitivo: nessun ordine e' nato.
- La riga si chiude in errore col motivo.
- Mike ricorda il rifiuto: la stessa identica richiesta (stessa quota, stesso importo) non si ripete.
- Se e' la copertura, il rifiuto conta per il freno delle coperture: 3 rifiuti con lo stesso motivo
  fermano la copertura (capitolo 8, riquadro 05).

**Quando**
- Ordine a mercato tutto o niente non abbinato, codice d'errore di Betfair, istruzione non accettata.
- Paper: il simulatore risponde «rifiutato», «annullato» o «scaduto» senza abbinamento.

**Numeri**
- Freno delle coperture: 3 rifiuti con lo stesso motivo (parametro, da 1 a 20).

**Esempio con le cifre**
- Copertura 2,26 euro a 6,6 tutto o niente: Betfair risponde «non abbinato». Riga in errore, rifiuto
  1 su 3. Al giro dopo, se la quota o l'importo sono cambiati, Mike ritenta dopo almeno 15 secondi.

**Cosa vedi nell'app**
- Nell'attivita' «rifiutato» critico con codice e conteggio «1/3», poi «non abbinato».
- In paper: «non abbinato» con fase e conteggio.

**Se qualcosa va storto**
- Anche un «no» che viene da un freno (freno d'emergenza, modo ordini) passa di qui e conta come
  rifiuto del mercato (Punti da decidere 6).

**Paper o live**
- Paper: il simulatore non da' codici d'errore: il motivo contato e' la fase («annullato»,
  «scaduto», «rifiutato»).
- Live: il motivo contato e' il codice di Betfair.

**Per il tecnico**
- Live `service.py:921-943`; `_rifiutata` `:1304-1327`; `_esito_rifiuto_mercato` `:946-1004`;
  paper `:1595-1662`; `engine.registra_rifiuto_copertura` `engine.py:1595-1615`. Attivita'
  `place_rifiutato`, `no_fill`, `skip`. Inventario C-22, C-25, C-26, C-40, A-68, A-72.

---

## 12 - Fermato da un freno

**Cosa fa**
- Un controllo del riquadro 02 (o un freno del capitolo 8) dice «no» prima che l'ordine parta.
- Nessun ordine va al mercato. Se il «no» arriva prima della riga, nessuna riga nasce. Se arriva dopo
  la riga (freno d'emergenza, modo ordini, simulatore giu'), la riga si chiude in errore.
- Il motore resta libero di riproporre l'ordine al giro dopo, salvo tre casi: prezzo non piu'
  disponibile, chiusura gia' in volo, e rifiuto dei freni live (questi vengono ricordati come rifiuti).

**Quando**
- A ogni ordine, nei controlli del riquadro 02 e, in live, nei freni finali.

**Numeri**
- Vedi capitolo 8 per ogni freno.

**Esempio con le cifre**
- Prezzi vecchi di 60 secondi con lo scanner muto da 90 secondi: Mike voleva puntare 10,00 euro a 1,50
  sull'Under 3,5. Nessuna riga, nessun ordine; attivita' «prezzi vecchi».

**Cosa vedi nell'app**
- Nell'attivita' la riga col motivo del freno. Per le aperture fermate da un freno che non e' il
  mercato, una sola riga critica «aperture ferme», poi silenzio fino alla ripresa.

**Se qualcosa va storto**
- Vedi capitolo 8.

**Paper o live**
- Vedi capitolo 8: alcuni freni valgono solo in live (modo ordini, interruttore soldi veri), uno solo
  in paper (simulatore raggiungibile).

**Per il tecnico**
- `execute_place` `service.py:656-753`, `:829-853` (`blocco_paper`), live `execution._live_brake`
  `execution.py:134-214`, `:872-874`; `_ferma_aperture` `service.py:1826-1850`. Inventario C-16..C-21,
  C-44, C-45.

---

## Frecce

- 01 Ordine deciso -> 02 Controlli: sempre, per ogni ordine nuovo del giro.
- 02 Controlli -> 03 Inviato: tutti i controlli del riquadro 02 dicono si' e la riga e' scritta.
- 02 Controlli -> 12 Fermato da un freno: il primo controllo che dice no (prezzi non vivi, mercato non
  aperto, quota sparita, freno delle coperture, chiusura gia' in volo, flusso interrotto su
  un'apertura, simulatore giu', riga non scritta).
- 03 Inviato -> 04 Abbinato: ordine a mercato abbinato per intero alla risposta.
- 03 Inviato -> 06 Esito ignoto: nessuna risposta certa (errore dopo l'invio, tempo scaduto, niente
  resoconto; paper: fase «errore» del simulatore; live: interruttore soldi veri spento).
- 03 Inviato -> 08 In coda: ruolo di banca d'uscita appoggiata (uscita al fischio sempre; banche di
  green con uscita «appoggiata») e Betfair o il simulatore l'accettano.
- 03 Inviato -> 11 Rifiutato: «no» definitivo (tutto o niente non abbinato, codice d'errore, freno
  live dopo la riga).
- 03 Inviato -> 09 Abbinato in parte: ordine a mercato con abbinamento parziale riportato (non
  disegnata).
- 03 Inviato -> 10 Ritirato o scaduto: ordine a mercato ancora in attesa dopo 120 secondi con esito
  noto; paper: nessuna notizia dal simulatore per 60 secondi (non disegnata).
- 06 Esito ignoto -> 07 Verifica: sempre, al massimo ogni 60 secondi.
- 07 Verifica -> 10 Ritirato o scaduto: l'ordine non e' mai esistito («mai piazzato»).
- 07 Verifica -> 04 Abbinato: l'ordine esiste abbinato («confermato») (non disegnata).
- 07 Verifica -> 07 Verifica: Betfair non raggiungibile o risposta «attesa»: si riprova.
- 08 In coda -> 04 Abbinato: abbinata tutta.
- 08 In coda -> 09 Abbinato in parte: abbinata in parte, residuo vivo.
- 08 In coda -> 10 Ritirato o scaduto: ritirata (dal motore o dall'utente) o scaduta alla sospensione.
- 08 In coda -> 06 Esito ignoto: sparita dagli ordini vivi senza sospensione, rilettura alla
  riapertura con esito ignoto (in live sempre, se non abbinata), annullo non confermato (non
  disegnata).
- 09 Abbinato in parte -> 05 Chiuso nei conti: la parte abbinata si regola a fine partita.
- 04 Abbinato -> 05 Chiuso nei conti: mercato chiuso e risultati letti da Betfair.
- 10 Ritirato o scaduto -> 05 Chiuso nei conti: riga chiusa a zero (non disegnata).
- 11 Rifiutato e 12 Fermato: fine. Il motore puo' decidere un ordine NUOVO al giro dopo (tranne la
  stessa identica richiesta gia' rifiutata).

---

## Punti da decidere

Differenze dalla Costituzione (`Betfair/mike/COSTITUZIONE_MIKE.md`) e cose strane degli inventari che
riguardano la vita degli ordini.

1. **Ultimo ingresso «resta in gioco» ma cade al fischio.** Costituzione §3 Fase 2, §5, §15.1:
   l'ultimo ingresso a 10' dal fischio resta valido in gioco. Codice: la riga porta «resta in gioco»,
   ma l'ordine vero parte tutto o niente e cade alla sospensione, in paper (`execution.py:514`,
   `:531`) e in live (`omega_market.py:735` fisso, `:746`). Nessun residuo puo' restare in gioco; il
   ritiro del residuo 120 secondi dopo il fischio (`cancel_unmatched_after_ko_s`) non ha oggetto.
   Verificato anche dal coordinatore. La stessa Costituzione §7 dice «rinviato alla fase F6».
2. **Ingresso «TTL 60 secondi».** Costituzione §3 Fase 1: l'ingresso resta 60 secondi poi si
   annulla. Codice: tutto o niente, non resta mai sul libro; il parametro `pre_entry_ttl_s` (60) non
   ha oggetto per l'ordine vero.
3. **Paper «abbinato guardando il libro».** Costituzione §2 e §7: in paper l'abbinamento si deduce dal
   libro, ritardato del ritardo d'invio. Codice: dal 29/09 il paper passa dal simulatore; niente
   abbinamenti «in casa».
4. **Banca in coda in live.** Costituzione §7: in live non esiste, si usa sempre l'uscita a mercato.
   Codice: esiste ed e' di serie; si forza a mercato solo con la valvola spenta.
5. **La rilettura per numero di scommessa manca in live.** Alla riapertura dopo una sospensione Mike
   cerca la lettura dell'ordine per numero (`service.py:2492`), ma lo sportello di produzione
   (`_RealMarket`, `service.py:120-231`) non la ha. In live una banca non abbinata e scaduta alla
   sospensione finisce SEMPRE in verifica («mercato senza lettura») invece di «scaduta»: niente
   aperture finche' la verifica non chiarisce. Nel banco di replay il finto HA questa lettura
   (`banco_comune.py:836`): il replay esercita una strada che la produzione non ha.
6. **Il rifiuto di un freno contato come rifiuto del mercato.** In `execute_place` un «no» del freno
   d'emergenza, del modo ordini, dei freni illeggibili o del freno paper passa da `_rifiutata`
   (`service.py:927`) e da `_esito_rifiuto_mercato` (`:934`) PRIMA di fermare le aperture (`:939-942`).
   Effetti: la richiesta identica non si ripete; per la copertura il freno conta un rifiuto che non
   viene dal mercato, e con 3 uguali la copertura resta bloccata anche dopo aver tolto il freno,
   finche' l'utente non preme «Riprendi».
7. **Attesa fino a 15 secondi dopo ogni ordine paper.** Dopo ogni ordine a mercato paper il giro
   intero si ferma fino a 15 secondi (`service.py:860-862`): le altre partite aspettano. Nel banco di
   replay l'attesa e' 0 (`mike/tools/replay_registrazioni.py:456`): il replay non misura questo
   ritardo.
8. **Ordine senza notizie in paper dichiarato non eseguito.** Costituzione §4.11: un ordine a esito
   ignoto non e' mai dato per non piazzato. Codice paper: un ordine a mercato senza notizie dal
   simulatore per 60 secondi viene chiuso «senza esito», riga in errore (`service.py:1494-1508`).
   Costituzione §5 dice invece «in paper si risolve subito».
9. **Paper sotto il minimo.** Costituzione §15.5: in paper nessun minimo, l'importo esatto si abbina.
   Codice: il simulatore fa «piazza e riduci» tutto o niente come il live; rifiuto certo se il libro
   dice che non si abbina.
10. **Banca in coda paper senza notizie: nessun limite di tempo** (`service.py:1496` vale solo per gli
    ordini a mercato; il controllo dei 120 secondi esclude le banche in coda). Dopo un riavvio del
    programma, se la memoria del collegamento al simulatore si perde, la banca puo' restare «in
    attesa» a lungo.
11. **Sospensione letta solo dall'Under 3,5.** Costituzione §15.6: «a ogni sospensione». Codice: lo
    stato si legge solo dal mercato 3,5 (`service.py:2881`), anche per la banca del rientro che sta
    sull'Under 4,5. Se il mercato passa da sospeso a chiuso la memoria resta «non letta» per sempre.
    In paper la banca scade a OGNI sospensione, in live decide Betfair: possibile differenza.
12. **Paper, alla riapertura, «abbinata» invece di «parziale»** per una banca abbinata in parte e poi
    annullata (`service.py:2934`).
13. **Riga della banca in coda**: `meta.phase="open"` anche quando resta in attesa; la colonna importo
    vale l'abbinato (0 appena appoggiata); l'esposizione non si aggiorna (`service.py:2092-2121`).
14. **«Resta in gioco» della gamba solo sulla riga**: la persistenza della gamba finisce nella riga
    (`service.py:572`), mai sull'ordine vero (vedi punto 1).
15. **Regolata senza aggiornare le righe**: nei rami «risultato indipendente dai gol» e «da
    sistemare» (`service.py:4143-4161`) la partita si chiude ma le righe dei giri gia' chiusi restano
    aperte per sempre.
16. **Ritiro non mandato al mercato se la riga non e' «in attesa»** (`service.py:5103-5105`): se una
    riga fosse gia' aperta con un residuo vivo, il residuo non verrebbe annullato (non so se il caso
    esiste: vedi Punti non chiariti).
17. **Importi alzati al minimo per OGNI punta** con importi esatti spenti, non solo le aperture come
    dice il commento (`service.py:746-753`); anche la copertura segue l'arrotondamento della copertura.
18. **Primo ordine paper dopo l'avvio**: il collegamento al simulatore si accende al primo uso; finche'
    non e' collegato l'ordine risulta «simulatore non raggiungibile» e le aperture si fermano per quel
    giro.
19. **Messaggio di «Annulla ordini» impreciso**: conta come annullati anche gli ordini abbinati durante
    l'annullo (`service.py:3268-3271`).
20. **Freno copertura in paper**: fasi diverse del simulatore («annullato», «scaduto», «rifiutato»)
    azzerano il conteggio l'una con l'altra: il freno puo' non scattare mai.

## Punti non chiariti

1. Betfair, ordine tutto o niente senza importo minimo di abbinamento: puo' tornare abbinato in parte?
   Non verificato sulla documentazione. Mike gestisce comunque il parziale (`execution.py:933-944`).
2. In paper `execution.place` riduce l'importo alla liquidita' disponibile alla quota migliore
   (inventario C-21 punto 6). Non ho verificato se la stessa riduzione vale in live.
3. «Piazza e riduci» percorso A (parcheggio gia' alla quota voluta, senza cambio di quota,
   `omega_market.py:1127-1141`): con tutto o niente acceso non ho verificato se il pianificatore
   (`piano_submin_live`) lo esclude o se l'ordine puo' restare a riposo.
4. Un ordine scaduto senza abbinamento sparisce dagli ordini vivi di Betfair? Presupposto dal codice,
   non verificato.
5. Come la pagina traduce i nomi delle attivita' (area E, non letta per questo capitolo): i messaggi
   fra «» sono il senso, non sempre il testo esatto.
6. Il punto 16 dei Punti da decidere dipende da come la riga viene aggiornata agli abbinamenti
   parziali: non verificato.
