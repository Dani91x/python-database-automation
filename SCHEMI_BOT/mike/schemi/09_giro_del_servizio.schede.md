# Mike - Capitolo 9: il giro del servizio (schede)

Schema: `09_giro_del_servizio.html` (sorgente `09_giro_del_servizio.workflow.json`).
Fonte dei fatti: `SCHEMI_BOT/mike/inventario/D_giro_e_conti.md` (schede D-n) e, per i rimandi,
`C_servizio_e_ordini.md` (schede C-n). Valori controllati anche su `Betfair/mike/config.py` e sulle
costanti di `Betfair/mike/service.py` righe 50-62.

**Schede dell'inventario D usate in questo file (numeri):** 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13,
14, 15, 16, 17, 18, 19, 20, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41,
42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 67, 68, 69,
70, 71, 72, 73, 74, 75, 76, 77, 89, 91, 92, 96, 97.
(Le altre - 21, 22, 23, 64, 65, 66, 78-88, 90, 93-95, 98-108 - sono nel capitolo 10, file
`10_dati_e_conti.schede.md`, che in coda porta il conto completo delle 108.)

Come si legge: ogni riquadro dello schema ha un numero (01-12) scritto in alto. La scheda con lo
stesso numero lo spiega. Le parole fra «» sono i messaggi che l'utente legge nell'app.

---

## 01 - Accensione («una copia sola»)

**Cosa fa**
- Mike prende il «posto unico»: puo' girare una sola copia di Mike alla volta.
- Mike accende il canale verso lo schermo dell'app (le quote e il P&L arrivano alla pagina senza
  passare dal database).
- Mike accende la rilettura del saldo del conto dopo ogni ordine vero o regolamento.
- Mike accende la sveglia rapida e il lettore veloce dello scanner, se i loro interruttori sono
  accesi (riquadro 10).
- Mike controlla se l'app e' stata appena riaperta (riquadro 02).
- Mike carica l'atlante dei gol (le probabilita' di gol minuto per minuto) e comincia a girare.

**Quando**
- Una volta, quando il programma di Mike parte.
- Esistono due modi di collaudo: «un giro solo e poi esce» e «a secco» (nessun ordine vero: Mike
  scrive soltanto «avrei piazzato»). Con «un giro solo» Mike non prende il posto unico e non accende
  i canali.

**Numeri**
- Posto unico sulla porta 47319 del computer.
- Canale verso lo schermo sulla porta 47333.
- Tempi massimi di attesa del database per i bot: 5 s per collegarsi, 20 s per una lettura
  (valori scritti in un commento del codice, NON verificati: vedi «Punti non chiariti»).

**Esempio con le cifre**
- Alle 14:00 l'utente apre l'app. Il servizio Mike parte, prende la porta 47319 e accende il canale
  47333. Se un'altra copia di Mike tiene gia' la porta 47319, questa seconda copia non parte.
  Nessun ordine doppio: una sola copia puo' piazzare i 10,00 EUR di un ingresso.

**Cosa vedi nell'app**
- Niente di diretto. Da questo momento la testata e le schede delle partite si aggiornano al ritmo
  del bot (riquadro 09).

**Se qualcosa va storto**
- Porta 47333 occupata o canale in errore: Mike scrive un avviso nel suo registro e continua. La
  pagina legge dal database come prima, solo piu' lenta.
- Tempi massimi del database non impostabili: avviso e si prosegue.
- Paper o live: identico.

**Per il tecnico**
- D-1, D-72. `service.py:5987-6095` (`main`); blocco `_LOCK_PORT` 5996-5997 (env `MIKE_LOCK_PORT`,
  default `config.LOCK_PORT_DEFAULT` 47319); timeout `db_client.timeout_bot` 6003-6008; canali
  6013-6027; guardia `avvio_app.Guardia` 6031-6032; `dossier.load_atlas` 6033.
- Opzioni `--once` e `--dry`. Canale: `_avvia_canale` `service.py:5555-5569`, `_PORTA_CANALE`
  5552, env `MIKE_LOCAL_WS_PORT`. Saldo: `omega_market.attiva_saldo_su_evento("mike")`.

---

## 02 - App riaperta («fermo e paper»)

**Cosa fa**
- Se il programma di Mike appartiene a un'apertura NUOVA dell'app, Mike si mette da solo in
  «fermo» e in «paper», e rimette su MANUALE l'interruttore delle uscite.
- Se invece e' solo un riavvio dopo un crash (stessa apertura dell'app), Mike non tocca niente.
- Soglie, importi e tetti NON vengono toccati.
- Le posizioni gia' aperte restano sorvegliate: coperture, uscite, ritiri e regolamento continuano.

**Quando**
- Una volta all'avvio. Se il database non risponde, Mike riprova all'inizio di ogni giro finche' non
  riesce.

**Numeri**
- Nessuno.

**Esempio con le cifre**
- Ieri sera Mike era acceso in live con un back Under 3.5 da 10,00 EUR a 1,90 su una partita
  ancora da regolare. Stamattina l'utente riapre l'app.
- Mike riparte fermo e in paper: nessuna partita nuova. La partita di ieri resta in live (la
  modalita' e' della partita, riquadro 05) e viene regolata: +8,55 EUR netti se finisce con 3 gol
  o meno, -10,00 EUR se finisce con 4 gol o piu'.

**Cosa vedi nell'app**
- Mike fermo, in paper, uscite su manuale.
- Una riga in Attivita' «i bot li accende l'utente: status=stopped, mode=paper», scritta solo se
  c'era davvero qualcosa da spegnere (Mike era acceso, in arresto, in errore o in live) o se le
  uscite sono state riportate a manuale.

**Se qualcosa va storto**
- Riga di controllo illeggibile: nessuna decisione, Mike riprova al giro dopo. Intanto Mike NON apre
  niente di nuovo (riquadro 03).
- Riga di controllo inesistente: il controllo si considera fatto.
- Paper o live: e' proprio il passaggio che riporta il live a paper.

**Per il tecnico**
- D-4. `service.py:3396-3427` (`ferma_al_nuovo_avvio`); logica in `Betfair/stream/avvio_app.py:217-330`.
- Confronto `APP_BOOT_ID` con quello timbrato nelle `stats`; scrive `status=stopped`, `mode=paper`,
  `stopped_at`, `params.uscite_automatiche` = manuale.

---

## 03 - Comandi («acceso, paper o live»)

**Cosa fa**
- A ogni giro Mike legge la riga di controllo: acceso o fermo, paper o live, tutti i parametri.
- Mike decide se in questo giro puo' APRIRE: solo se e' acceso e il controllo del riquadro 02 e'
  concluso. Se e' fermo, Mike spegne ingresso pre-partita, re-ingresso e ultimo ingresso; coperture,
  uscite, annulli e regolamento continuano.
- Mike legge in una volta sola le richieste della pagina (cash out, chiudi tutto, annulla ordini,
  salta, riprendi, approva uscita) e le esegue prima del giro delle partite.
- Mike chiude con errore le richieste rimaste «in lavorazione» da piu' di 10 minuti (erano rimaste
  appese per un crash), cosi' il pulsante torna usabile.
- Se Mike era «in arresto», a fine giro lo scrive come «fermo».

**Quando**
- A ogni giro, per primo.

**Numeri**
- Richieste lette: fino a 50 in attesa + 200 in lavorazione (250 in tutto, le piu' vecchie prima).
- Richiesta appesa: oltre 10 minuti.
- Parametri: ognuno ha un valore di serie, un minimo e un massimo; un valore fuori limite viene
  tagliato al limite; una coppia minimo/massimo invertita torna tutta al valore di serie.
- Modalita' diversa da paper o live: diventa paper.

**Esempio con le cifre**
- Pre-partita, l'utente ha un back Under 3.5 da 10,00 EUR a 1,90 e una lay di chiusura da 10,10 EUR
  appoggiata a 1,88. Preme «Cash out».
- Mike annulla la lay appoggiata e arma la chiusura: «Cash out: annullati 1 ordini sul book,
  chiusura in corso (netto stimato 0,15 EUR).» Da quel momento la partita non rientra piu' prima del
  fischio finche' l'utente non preme «Riprendi».
- L'utente preme «Ferma»: la partita con il back Under aperto continua a essere coperta e chiusa,
  ma nessuna partita nuova parte.

**Cosa vedi nell'app**
- L'esito di ogni richiesta, per esempio «Nessun ordine vivo da annullare.», «Annullati 2 ordini sul
  book.», «Nessuna posizione da chiudere.», «Quote non disponibili...», «Feed non aggiornato».
- Una richiesta appesa diventa «richiesta interrotta (servizio riavviato): riprova».
- Nelle statistiche: «il pulsante Ferma blocca solo le aperture».

**Se qualcosa va storto**
- Riga di controllo illeggibile o inesistente: il giro intero salta (riquadro 12).
- Lettura unica delle richieste fallita: Mike torna alle due letture separate; il giro continua.
- Cash out rifiutato quando la partita non e' nel feed o e' incompleta, quando la fotografia del
  mercato non si costruisce, quando i prezzi sono troppo vecchi per un ordine. Con il flusso dei
  prezzi fermo Mike prova a leggere il book da Betfair: se ci riesce chiude con quei prezzi, se no
  rifiuta.
- «Annulla ordini»: un annullo non confermato da Betfair viene detto chiaramente («ATTENZIONE: 1
  annullamenti non confermati da Betfair, in verifica»): l'ordine potrebbe essere ancora vivo.
- Paper o live: identico. Gli annulli vanno a Betfair (live) o al simulatore paper (riquadro 07).

**Per il tecnico**
- D-5 `service.py:3433-3448` (`control_unreadable`, `no_control`, `config.merge_params`).
- D-6 `service.py:3452-3453`, `_params_for` 1268-1276: `running` = `status=="running"` e guardia non
  bloccante; se falso `pre_enabled`, `reentry_enabled`, `last_entry_persist` a False.
- D-7 `service.py:3462-3484`; `db.requests_da_lavorare` `db.py:422-451`, `fail_stale_processing`
  474-502; `_STALE_REQUEST_MIN` = 10.
- D-12 `service.py:3567-3570` (`process_requests` `service.py:3077`, area C-56).
- D-17 `service.py:3667-3673`: `stopping` -> `stopped`, attivita' `stop`.
- D-62 `_request_cancel` `service.py:3253-3280`; D-63 `_request_flatten` 3283-3393 (rifiuti
  `feed_assente`, `snapshot_assente`, `flusso_interrotto`, `feed_stantio`; motivo `cancelled_manual`).
- D-91 `db.read_control`/`set_control` `db.py:59-68`; D-96 `db.py:417-502` (stato `rejected` non
  ammesso dal vecchio schema -> `error`). Statistica `stop_ferma_solo_aperture`.

---

## 04 - Prezzi («feed ogni 4 s»)

**Cosa fa**
- Mike prende le righe di tutte le partite di calcio pubblicate dallo scanner (il «feed unico»):
  quote, punteggio, minuto, stato del mercato.
- Mike misura da quanti secondi lo scanner non scrive il suo stato (eta' dello scanner) e se il
  flusso dei prezzi e' dichiarato fermo.
- Mike rilegge l'elenco delle partite che segue: tutte quelle non chiuse, di qualunque eta', e quelle
  chiuse (regolate, in errore, saltate) nelle ultime 48 ore.
- Se l'interruttore del canale veloce e' acceso, Mike prende anche le righe che lo scanner spinge al
  tick e usa quella piu' recente fra canale e database.

**Quando**
- Righe del feed: rilette dal database al massimo ogni 4 s; ogni 10 s se il canale veloce copre
  TUTTE le partite con righe di meno di 5 s.
- Elenco delle partite seguite: riletto al massimo ogni 60 s; in mezzo Mike usa la copia in memoria
  (solo Mike scrive quella tabella).

**Numeri**
- Rilettura del feed: 4 s (parametro, da 0 a 30 s, modificabile dall'app).
- Con canale veloce sano: 10 s.
- Eta' massima di una riga dal canale: 5 s.
- Elenco partite: 60 s (parametro, da 0 a 600 s, modificabile dall'app); partite chiuse tenute 48
  ore.

**Esempio con le cifre**
- Lo scanner riscrive la riga di una partita ogni 22 s circa; Mike la rilegge ogni 4 s. La
  freschezza si giudica sull'ora scritta nella riga, non sull'ora della lettura (capitolo 10,
  riquadro 05).
- Una partita con un Under 3.5 da 10,00 EUR aperto, finita tre giorni fa a servizio spento, torna
  nel giro (non e' chiusa) e viene regolata: +8,55 EUR se 3 gol o meno, -10,00 EUR se 4 o piu'.

**Cosa vedi nell'app**
- Eta' dello scanner in testata; con il canale acceso «fonte» = canale o database e quante righe
  arrivano dal canale.

**Se qualcosa va storto**
- Lettura del feed fallita: Mike la tratta come «nessuna riga» e la tiene come buona (vedi «Punti da
  decidere» n. 1: dopo 10 minuti ogni partita va in regolamento).
- Stato dello scanner illeggibile: eta' sconosciuta.
- Scanner di una versione che non dichiara il flusso: una sola riga critica in Attivita'.
- Elenco partite illeggibile: riga di errore in Attivita'; se c'e' una copia in memoria Mike
  continua con quella (una posizione aperta non resta senza guardia); se non c'e', il giro salta.
- Paper o live: identico. Una partita senza modalita' salvata riceve quella attuale del bot.

**Per il tecnico**
- D-8 `service.py:3493-3496`; `_scanner_age` `service.py:1216-1232`; stato `safe_strategy_status`
  id `scanner`; attivita' `flusso_non_dichiarato`; statistiche `scanner_age_s`, `fonte_scan`,
  `righe_dal_canale`.
- D-9 `service.py:3504-3532`; `db.filtro_finestra_eventi` `db.py:91-113`; `events_reload_s` = 60;
  finestra `48 * 3600`; attivita' `error` motivo `events_failed`; salto `events_unreadable`.
- D-76 `service.py:5754-5825` (`ENV_MIKE_LEGGE_CANALE`, `_RISINC_FEED_S` = 10, `_CANALE_FEED`,
  `_canale_feed_acceso`, `avvia_client_scan`, `azzera_canale_scan`), porta 47336.
- D-77 `service.py:5828-5919` (`_canale_copre_tutte`, `_righe_del_feed`,
  `statistiche_canale_scan`); `CS.MAX_ETA_CONTESTO_S` = 5; `feed_cache_s` = 4,0.
- D-97 `db.fetch_scan_rows` `db.py:508-515`, `scanner_status` 518-525.

---

## 05 - Partite nuove («tetto e stop»)

**Cosa fa**
- Mike somma il P&L del giorno (realizzato + profitto bloccato) della modalita' attuale. Se e'
  uguale o peggiore di -50 EUR, Mike non apre piu' niente fino a domani (capitolo 10, riquadro 09).
- Mike cerca le partite che hanno messo i soldi in una modalita' diversa da quella attuale (per
  esempio partite live ancora aperte con il bot tornato in paper) e lo grida.
- Mike arma le partite nuove, solo se e' acceso e senza stop giornaliero. Una partita entra se tutte
  le risposte sono si':
  - Ha entrambe le linee, Under/Over 3.5 e Under/Over 4.5, con l'Under 3.5 e l'Over 4.5?
  - Ha l'ora del fischio d'inizio?
  - Il nome della competizione contiene uno dei testi del filtro (filtro vuoto = tutte)?
  - Non e' ancora in gioco?
  - Il fischio d'inizio e' fra adesso e 1 ora?
  - Le partite gia' «operative» della modalita' attuale sono meno di 10?
- Per ogni partita armata Mike prepara il dossier pre-partita (capitolo 10, riquadro 04) e la mette
  in osservazione con la modalita' di quel momento, che la partita tiene per sempre.
- Mike ritenta ogni 5 minuti il dossier delle partite che non hanno i gol attesi.
- Mike avvisa se la finestra d'ingresso e' piu' larga della finestra in cui lo scanner pubblica le
  linee pre-partita (Mike vedrebbe zero partite senza dirlo).

**Quando**
- A ogni giro, dopo le richieste della pagina.

**Numeri**
- Stop giornaliero: 50,00 EUR (parametro, da 0 a 100.000, app; 0 = spento).
- Tetto partite: 10 (parametro, da 1 a 90, app).
- Finestra d'ingresso: 1,0 ora prima del fischio (parametro, da 0,25 a 12 ore, app).
- Filtro competizioni: vuoto = tutte.
- Ritentativo del dossier: 300 s (5 minuti), fisso nel codice.
- Finestra dello scanner: variabile d'ambiente, per Mike di serie 0 (= spenta).

**Esempio con le cifre**
- Fischio fra 50 minuti, entrambe le linee nel feed, non in gioco: la partita entra in osservazione.
  Fischio fra 70 minuti: non ancora.
- Realizzato di oggi -38,40 EUR, bloccato sulle partite non ancora pagate -12,10 EUR: P&L del giorno
  -50,50 EUR, peggiore di -50: STOP. Nessun nuovo ingresso da 10,00 EUR fino a mezzanotte di Roma;
  le chiusure continuano.
- Partita armata in live alle 15:00; alle 15:30 l'utente rimette paper; quella partita continua a
  coprirsi con soldi veri e la pagina mostra l'avviso.

**Cosa vedi nell'app**
- La nuova scheda partita «in osservazione» e una riga in Attivita' «partita presa in carico» con
  nome, fischio d'inizio e dossier.
- Stop scattato: in testata «stop giornaliero», il P&L del giorno; in Attivita' una riga una volta
  sola per giornata.
- Avviso rosso con il numero di partite nell'altra modalita'.
- Dossier trovato piu' tardi: riga «dossier risolto» e la scheda passa da «nessun modello» a modello
  attivo.
- Finestra troppo larga: riga critica in Attivita', per esempio «Finestra di ingresso 2 h piu' ampia
  del ramo pre-KO dello scanner (1 h)».

**Se qualcosa va storto**
- Errore nel ritentativo del dossier: non ferma niente.
- Il conto delle partite «operative» che frena l'armamento NON e' lo stesso conto che frena le
  aperture (riquadro 06): vedi «Punti da decidere» n. 9.
- Il filtro «serie a» accetta anche «Serie A Women» e «Serie A2» (basta che il nome lo contenga).
- Paper o live: stop e tetto contati a parte; il P&L del paper non ferma il live e viceversa.

**Per il tecnico**
- D-10 `service.py:3538-3565` (attivita' `daily_stop` con `day_pnl`, `realized_today`,
  `locked_open`, `stop`, `day`); `_aggregates_cached` `service.py:1099-1146`.
- D-11 `service.py:3547-3551`, `partite_di_modalita_diversa` 3898-3908; statistica
  `eventi_altra_modalita`.
- D-13 `service.py:3572-3601`: stato `WATCH`, ciclo 0; conto per il tetto esclude terminali,
  `WATCH`, `IDLE_LIVE` (3580-3583); attivita' `armed`.
- D-89 `feed.is_candidate` `feed.py:443-460`.
- D-14 `service.py:3612`, `dossier_da_ritentare` 5369, `_retry_dossier` 5387, `_DOSSIER_RETRY_SEC`
  5366; attivita' `dossier_risolto`.
- D-15 `service.py:3625-3656`, `posti_occupati_per_modo` 3841-3861 (dettaglio nel capitolo 10,
  riquadro 10).
- D-24 `_config_warn` `service.py:3949-3974`; env `SAFE_PRE_KO_OU_HOURS`; attivita' `config_warn`.

---

## 06 - Giro partita («una alla volta»)

**Cosa fa**
Per ogni partita seguita, in quest'ordine:
1. La partita e' gia' regolata, in errore o saltata? Si': Mike non la guarda piu'.
2. Mike prende le regole della modalita' della PARTITA (non quella del bot). Partita live con la
   lay appoggiata spenta dall'utente: le uscite del ciclo pre-partita e del re-ingresso diventano a
   mercato.
3. Ogni 30 s Mike ripara lo specchio fra cio' che crede delle sue gambe e le righe salvate
   (riquadro 07).
4. Il mercato e' chiuso? Mike lo considera chiuso se una di queste risposte e' si':
   - La linea 3.5 (o, se manca, il mercato principale) e' «CLOSED» nel feed?
   - La riga manca dal feed da almeno 10 minuti?
   - Il fischio d'inizio e' noto e sono passate piu' di 3 ore?
   - La partita e' stata vista in gioco e sono passati almeno 100 minuti dal fischio?
   Si': regolamento (riquadro 08). Riga assente da meno di 10 minuti: Mike si segna da quando manca
   e la partita FINISCE qui per questo giro.
5. Mancano linee nel feed con una posizione aperta? Mike lo grida e la partita finisce qui per questo
   giro.
6. Mike aggiorna gol, ora dell'ultimo gol, «vista in gioco», punteggio all'intervallo (fissato la
   prima volta che il feed dice intervallo) e, in gioco, il quadro del modello.
7. Mike controlla se il flusso dei prezzi delle sue due linee e' vivo. Se e' fermo e c'e' una
   posizione, legge i book da Betfair (al massimo ogni 10 s per mercato) e li usa SOLO per chiudere,
   coprire o proteggere; le aperture restano bloccate.
8. Mike costruisce la fotografia del mercato. Se non si costruisce (per esempio manca l'ora del
   fischio) lo scrive e la partita finisce qui.
9. Con una posizione, per ogni selezione ancora in gioco senza prezzo, Mike lo grida; il giro
   continua.
10. Sorveglianze (rimandi al capitolo del servizio e degli ordini): in paper legge dal simulatore
    l'esito dei suoi ordini; controlla sospensione e riapertura del mercato; controlla lo stato del
    mercato della copertura Over 4.5; ogni 30 s controlla la posizione del conto su Betfair (se
    l'utente ha chiuso a mano fuori dall'app).
11. Seguito degli ordini (riquadro 07).
12. Il motore decide: nuovo stato, ordini da piazzare o annullare, notizie.
13. La partita e' bloccata dal tetto (capitolo 10, riquadro 10)? Si': Mike toglie dalla decisione le
    sole APERTURE (ingresso Under, ultimo ingresso, seconda entrata, copertura Over, re-ingresso);
    annulli, uscite, coperture gia' in corso e cash out passano sempre.
14. Annulli e piazzamenti (riquadro 07).
15. Mike scrive in Attivita' le notizie del motore e il cambio di stato (solo se lo stato cambia
    davvero). La decisione ripetuta di uscita in perdita si scrive solo quando cambia o ogni 5
    minuti.
16. Mike calcola la scheda dal vivo della partita (gia' netta di commissione) e la salva
    (riquadro 09).

**Quando**
- A ogni giro, per ogni partita. Un errore su una partita non ferma le altre.

**Numeri**
- Specchio: ogni 30 s per partita (parametro, da 0 a 600 s, app).
- Riga assente: 10 minuti (600 s); partita finita: 3 ore dal fischio; vista in gioco: 100 minuti dal
  fischio. Tutti fissi nel codice.
- Lettura diretta di Betfair con flusso fermo: al massimo ogni 10 s per mercato; promemoria critico
  ogni 60 s.
- Scanner considerato fermo (soglie dello scanner): giro fermo oltre 45 s, conferma in gioco 45 s,
  pre-partita 125 s.
- Freno delle righe ripetute in Attivita': 300 s (parametro, app), 45 s per quelle critiche.
- Decisione di uscita in perdita ripetuta: una riga ogni 300 s (fisso).
- Passo del modello: 5 minuti; casi minimi della tabella empirica: 200 (parametri, app).
- Soglia del «se chiudo ora»: 5% (parametro, app); scostamento del prezzo di chiusura: 0 tick.

**Esempio con le cifre**
- Al fischio il feed passa dal blocco pre-partita a quello in gioco e la riga sparisce per 4 minuti:
  NON e' un regolamento (servono 10 minuti).
- Under 3.5 aperto da 10,00 EUR a 1,90, flusso fermo da 70 s: Mike legge il book da Betfair, trova
  1,55/1,57 e puo' chiudere; non potrebbe aprire un nuovo ciclo.
- Tetto: 10 partite esposte in paper; l'undicesima vorrebbe entrare a 1,85 per 10,00 EUR: niente
  ingresso finche' un posto non si libera; al giro dopo Mike riprova.
- Scheda dal vivo: back Under 10,00 EUR + copertura Over 4.5 2,40 EUR (base 12,40 EUR); «se chiudo
  ora» +0,65 EUR netti = 5,24% della base, sopra la soglia del 5%.
- Due righe «regola fissa: -9.05 entro 30% di 8.90» e «regola fissa: -9.10 entro 30% di 8.90» hanno
  la stessa firma: una sola riga ogni 5 minuti.

**Cosa vedi nell'app**
- La scheda della partita: minuto, gol, punteggio e intervallo, eta' delle quote, «se chiudo ora»,
  rischio, bloccato, probabilita', P&L per numero di gol, cicli, book.
- Linee mancanti: allarme rosso sulla scheda (per esempio «OU45|OVER mancante»).
- In Attivita': linea mancante, flusso interrotto, lettura diretta da Betfair, flusso interrotto
  senza lettura («la posizione resta senza chiusura ne' copertura finche' un prezzo vivo non
  torna»), tetto partite, cambio di stato, notizie del motore (ciclo pre-partita, copertura, attesa
  copertura, cash out, tentativi esauriti, chiusura dell'utente, uscita in perdita, proposta
  d'uscita nata/decaduta/eseguita, veto sulla probabilita' dell'Under).
- Partita rotta: riga di errore in Attivita' su quella partita.

**Se qualcosa va storto**
- Riga assente da meno di 10 minuti, oppure linee mancanti: la partita esce dal giro PRIMA dei
  ritiri a 120 s, della riconciliazione, della sorveglianza della sospensione e del seguito delle lay
  appoggiate (vedi «Punti da decidere» n. 2).
- Si chiude solo la linea 4.5: la partita non entra in regolamento (vedi «Punti da decidere» n. 11).
- Flusso fermo e Betfair illeggibile: la posizione resta senza chiusura ne' copertura finche' un
  prezzo vivo non torna; riga critica con l'esposizione in euro.
- Paper o live: ogni partita segue la SUA modalita'. La lettura diretta da Betfair si fa anche in
  paper (non con «a secco»).

**Per il tecnico**
- D-26 `service.py:4008-4021`, `_live_exit_override` 1235-1265 (`live_resting_enabled`,
  `pre_exit_mode=resting` -> `taker`).
- D-27 `service.py:4028-4032` (`reconcile_every_s`).
- D-28 `service.py:4039-4055` (`_ROW_MISSING_GRACE_S`, `_MATCH_OVER_S`, `_MATCH_LIKELY_OVER_S`,
  `extra.row_missing_since`).
- D-34 `service.py:4186-4207` (`feed_line_missing`, `lines_missing`, `feed_incomplete`,
  `_log_throttled` 1279-1301, `skip_log_interval_s` = 300, `_CRITICAL_LOG_EVERY_S` = 45).
- D-35 `service.py:4210-4231` (`ht_score`, `seen_inplay`, `last_goals`, `dossier.live_frame`).
- D-36 `service.py:4235-4274`, `_books_ripiego_rest` 1163-1190, `_RIPIEGO_REST_MIN_S` = 10,
  `flusso_prezzi.AVVISO_CRITICO_OGNI_S` = 60; attivita' `flusso_interrotto`, `ripiego_rest`,
  `flusso_interrotto_senza_rest`.
- D-37 `service.py:4275-4283` (`snapshot_non_costruibile`); D-38 `service.py:4289-4296`.
- D-39 `service.py:4304-4322` (`_segui_ordini_paper_su_runner` 1456, `_sorveglia_sospensione` 2872,
  `_sorveglia_mercato_copertura` 2965, `_sorveglia_posizione_di_conto` 2760; inventario C-38..C-55).
- D-44 `service.py:4425-4430` (`engine.decide`, `_aggiorna_aperture_ferme` 1862,
  `_approvazione_eseguita` 3192).
- D-45 `service.py:4441-4445`, `engine.OPENING_ROLES` `engine.py:50`; attivita' `tetto_partite`.
- D-48 `service.py:4529-4578`; D-25 `_LOSS_EXIT_DECISO_MIN_S` = 300, `_firma_loss_exit_deciso`
  `service.py:3979-3991`, uso 4563-4576.
- D-49 `service.py:4582-4584` (attivita' `state`); D-50 `service.py:4587-4679`
  (`cashout_place_at_ticks` = 0, `cashout_profit_pct` = 5).
- D-16 `service.py:3635-3665` (attivita' `error` motivo `event_cycle`).

---

## 07 - Ordini («piazza e segue»)

**Cosa fa**
- **Ordini fermi da troppo.** Un ordine in coda da piu' di 120 s (non una lay appoggiata, che puo'
  restare sul book per ore) viene:
  - messo «in verifica» se il suo esito e' ignoto (riga illeggibile, riga assente, oppure riga che
    dice «eccezione durante il piazzamento»): nel dubbio Mike non cancella mai un ordine che potrebbe
    essere vivo;
  - altrimenti ritirato DAVVERO: Mike manda prima l'annullo al mercato e solo dopo scrive la riga.
- **Ordini a esito ignoto.** Mike prova a chiarirli al massimo ogni 60 s:
  - live: legge gli ordini correnti e regolati da Betfair e riconosce l'ordine della riga; esito
    «confermato» (era abbinato: gamba aperta con importo e prezzo veri), «mai piazzato» (gamba
    annullata), oppure «ancora in attesa»;
  - paper con ordine sul simulatore: decide il simulatore;
  - paper senza ordine sul simulatore: «mai piazzato», subito.
  Intanto il giro continua con tutte le azioni che riducono il rischio; le aperture le toglie il
  motore.
- **Lay appoggiate.** In live Mike legge dal book ordini di Betfair se si e' abbinata (mai dedotto
  dal prezzo). In paper l'abbinamento lo dice il simulatore.
- **Annulli** decisi dal motore: Mike manda l'annullo al mercato.
- **Piazzamenti.** Per una lay APPOGGIATA (uscita al fischio sempre; chiusura del ciclo pre-partita
  e del re-ingresso se l'utente ha scelto «appoggiata»):
  - Prezzi non vivi, o prezzi letti da Betfair col flusso fermo per un'APERTURA? Nessun ordine, gamba
    annullata.
  - Mercato sospeso? Nessun ordine; la gamba torna al motore.
  - Modo «a secco»? Solo la scritta «avrei piazzato».
  - Live: ordine vero appoggiato su Betfair.
  - Paper: se c'e' gia' una lay dello stesso ruolo e ciclo in attesa, la nuova viene saltata;
    altrimenti ordine sul book del simulatore.
  Per le altre gambe: ordine a mercato.
- **Specchio gambe/righe** (ogni 30 s per partita):
  - Gamba abbinata senza riga: la riga viene RISCRITTA con importo e prezzo abbinati.
  - Riga aperta senza gamba: in paper chiusa in errore; in live solo marcata «orfana» e gridata.
  - Riga scritta ma risposta persa («riserva orfana»): la gamba torna in verifica e decide la
    riconciliazione con la fonte vera.
  - Se tutto combacia Mike non legge niente.

**Quando**
- A ogni giro della partita, dopo le sorveglianze e intorno alla decisione del motore.

**Numeri**
- Ordine fermo: 120 s (fisso).
- Riconciliazione: ogni 60 s (parametro «conferma regolamento», app); 30 s se il parametro e' 0;
  minimo 5 s.
- Specchio: ogni 30 s (parametro, app).
- Vecchia coda differita: grazia di 30 s sul prezzo (fisso).
- Righe aperte lette in pagine da 1000.

**Esempio con le cifre**
- Ingresso Under 3.5 a 1,90 da 10,00 EUR: gamba a mercato; subito dopo il fill, lay di chiusura
  appoggiata a 1,88 (2 tick sotto: sotto quota 2 il passo e' 0,01).
- Lay da 10,10 EUR a 1,86 in attesa, annullata: Betfair conferma annullati 6,10 EUR e abbinati 4,00
  EUR. La gamba resta aperta per 4,00 EUR a 1,86.
- Live, chiusura inviata, rete caduta: Betfair la mostra abbinata 10,10 EUR a 1,86: «confermata», e
  Mike non manda una seconda chiusura.
- Crash dopo un fill da 10,00 EUR a 1,92 prima della scrittura della riga: al riavvio la riga viene
  ricostruita aperta, 10,00 EUR a 1,92, rischio 10,00 EUR.

**Cosa vedi nell'app**
- Righe in Trade; in Attivita': annullo richiesto, esito dell'annullo, abbinato durante l'annullo,
  riparazione fatta, verifica in corso, «nessun abbinamento per quote vecchie», «avrei piazzato»,
  piazzamento saltato. Statistica «in riconciliazione».

**Se qualcosa va storto**
- Betfair non raggiungibile durante la riconciliazione: riga critica, nessuna ipotesi.
- Righe della partita illeggibili: nessuna riparazione («righe illeggibili»); Mike risponde «non so»,
  mai «nessuna riga» (cosi' non reinserisce righe e non raddoppia il P&L).
- Annullo non confermato: la gamba resta in verifica, mai dichiarata ritirata.
- Riga gia' «aperta» con un residuo ancora vivo: Mike non manda l'annullo al mercato (vedi «Punti non
  chiariti» n. 3).
- Paper o live: live -> Betfair; paper -> simulatore (stessa regola); paper senza simulatore -> solo
  la riga.

**Per il tecnico**
- D-40 `service.py:4330-4344` (`_PENDING_STALE_S` = 120, motivo `pending_stale`).
- D-41 `service.py:4351-4359` (`max(5, settle_confirm_s)`, `extra.reconcile_next_ts`).
- D-42 `service.py:4366-4382` (`_segui_resting_live` 2318).
- D-43 `service.py:4387-4419` (`extra.deferred`, `closes_id` 4389-4394, grazia riga 4410).
- D-46 `service.py:4446-4457` (motivo `cancelled_by_engine`, attivita' `cancel`).
- D-47 `service.py:4458-4528` (`_is_resting_leg` 1330-1346, `_piazza_resting_live` 1903,
  `_piazza_resting_paper` 1665, `execute_place` 618; attivita' `no_fill` `feed_stantio`,
  `would_place`, `place_saltato`).
- D-51 `_event_rows` 4682-4700; D-52 `_trade_ids_by_ref` 4703-4711; D-53 `_trade_row_for_leg`
  4714-4719; D-54 `_trade_unknown_outcome` 4722-4736; D-55 `_open_refs_by_event` 4739-4756
  (`db.open_trades` `db.py:196-207`, `PAGE_SIZE` 1000); D-56 `_mirror_is_aligned` 4759-4772;
  D-57 `_gamba_dalla_riga` 4775-4810; D-58 `_aggancia_riserve_orfane` 4813-4871 (`riserva_orfana`);
  D-59 `_reconcile_trades` 4874-4974 (`orphan_paper`, `riga_ricostruita`,
  `closes_trade_id_ripristinato`, `riga_orfana`); D-60 `_reconcile_unknown` 4977-5074
  (`X.reconcile_decision`, `betfair_non_raggiungibile`, `reconciled_not_placed`); D-61
  `_mark_trade_cancelled` 5077-5186 (`cancel_richiesto`, `cancel_esito`, `fill_resting`).
- Stati della gamba: `pending`, `open`, `cancelled`, `settled`, `pending_reconcile`, `archived`.

---

## 08 - Regolamento («mercato chiuso»)

**Cosa fa**
- A mercato chiuso Mike legge da Betfair i vincitori delle due linee e scrive l'esito e il P&L netto
  su ogni riga; poi la partita diventa «regolata».
- Il dettaglio completo (come si decide chi ha vinto, mercato annullato, 2 ore senza esito,
  commissione, righe non aggiornate) sta nel capitolo 10, riquadro 08.
- Se la riga della partita torna nel feed con il mercato aperto e non sono passate 3 ore dal fischio,
  Mike annulla il falso regolamento e riporta la partita nello stato coerente con le sue posizioni.

**Quando**
- Quando il riquadro 06 dice «mercato chiuso». Letture di Betfair al massimo ogni 60 s.

**Numeri**
- Lettura dei vincitori: ogni 60 s (parametro, da 0 a 600 s, app); minimo 5 s; 30 s se il parametro
  e' 0.
- Falso regolamento: solo entro 3 ore dal fischio.

**Esempio con le cifre**
- Fischio finale alle 22:47, mercato chiuso: letture alle 22:47, 22:48, 22:49... finche' Betfair
  dichiara i vincitori. Back Under 3.5 da 10,00 EUR a 1,90: con 3 gol +9,00 lordi, commissione 5%
  0,45, +8,55 EUR netti; con 5 gol -10,00 EUR.
- Riga sparita 12 minuti prima del fischio con un Under 3.5 aperto: Mike era andato in regolamento;
  la riga torna: la partita torna «Under aperto pre-partita».

**Cosa vedi nell'app**
- Stato «in regolamento», poi «regolata» con il P&L; riga «riga tornata nel feed, mercato aperto» se
  il regolamento viene annullato.

**Se qualcosa va storto**
- Vedi capitolo 10, riquadro 08.
- Paper o live: identico; i vincitori si leggono sempre da Betfair.

**Per il tecnico**
- D-29 `service.py:4058-4072` (`SETTLING` -> `LIVE_COVERED` / `REENTRY_OPEN` / `LIVE_UNCOVERED` /
  `PRE_OPEN` / `IDLE_LIVE` / `WATCH`; attivita' `settling_reverted`).
- D-30..D-33 `service.py:4073-4185` (dettaglio nel capitolo 10).

---

## 09 - Battito («testata dell'app»)

**Cosa fa**
- Mike calcola i numeri della testata: partite nel feed, seguite, per stato, righe aperte, capitale
  a rischio, realizzato di oggi e totale, bloccato, P&L del giorno, vinte e perse di oggi, cicli e
  partite di oggi, partite in gioco, eta' dello scanner, tetto e posti, stop giornaliero, modalita',
  interruttore dei soldi veri, partite in verifica, cadenza del battito.
- Mike decide se c'e' «fretta» per il prossimo giro. C'e' fretta se una di queste risposte e' si':
  - C'e' almeno una richiesta della pagina?
  - C'e' una partita non chiusa in gioco?
  - C'e' un ordine in coda o in verifica?
- Mike scrive statistiche e ora del battito sulla riga di controllo, ma non a ogni giro.
- Mike dichiara alla pagina la sua cadenza peggiore, cosi' la pagina giudica «vivo o morto» con il
  metro giusto.
- Per ogni partita Mike spinge SEMPRE la scheda sullo schermo; sul database la scrive subito se e'
  cambiato un fatto (stato, gamba, gol, regolamento), altrimenti a cadenza, tutte insieme in una
  sola scrittura a fine giro.

**Quando**
- A fine di ogni giro. Dopo azioni, regolamenti o richieste, conti e bloccato vengono ricalcolati
  subito.

**Numeri**
- Statistiche: al massimo ogni 10 s se qualcosa e' cambiato; battito almeno ogni 20 s (parametri,
  da 0 a 300 s, app; 0 = a ogni giro).
- Cadenza dichiarata = il piu' grande fra passo attivo (1 s), riposo (5 s) e battito (20 s): con i
  valori di serie 20,0 s.
- Scheda partita non cambiata: ogni 5 s se ha soldi sul tavolo o e' in gioco; ogni 60 s se e' solo
  osservata; mai se e' chiusa (parametri, app).
- Scrittura in blocco: accesa (parametro, app), usata solo con piu' di una scheda.

**Esempio con le cifre**
- 3 partite in gioco, 2 regolate oggi (+4,20 EUR e -1,10 EUR): realizzato di oggi +3,10 EUR.
- Il P&L cambia ogni secondo: Mike scrive al piu' ogni 10 s; niente cambia: una scrittura ogni 20 s.
- L'utente porta il battito a 30 s: la pagina aspetta 30 s prima di dichiarare il servizio lento.
- Il book oscilla di un tick: nessuna scrittura sul database; entra un gol: scrittura subito.
- 8 partite osservate da rinfrescare: una sola scrittura.

**Cosa vedi nell'app**
- Tutta la testata; il segnale di salute del servizio; le schede delle partite aggiornate a ogni giro
  attraverso il canale locale.
- L'eta' delle quote sulla scheda: oltre 20 s diventa rossa e spegne il cash out.

**Se qualcosa va storto**
- Scrittura del battito fallita: solo un avviso nel registro.
- Scheda della partita rifiutata dal database: riga critica e riga di errore in Attivita' «stato non
  scritto»; Mike continua, ma senza memoria salvata di dove si trova quella partita.
- Scrittura in blocco fallita o spenta: Mike scrive scheda per scheda (nessuna scrittura persa).
- Una riga di Attivita' che non si scrive si perde (resta l'avviso nel registro): non ferma mai il
  bot.
- Paper o live: conti, bloccato e rischio della testata sono della modalita' attuale del bot.

**Per il tecnico**
- D-18 `service.py:3675-3753` (statistica `live_abilitato` da `MIKE_LIVE_ENABLED`; `live_now`
  3713).
- D-19 `service.py:3772-3795` (`stats_min_s` = 10, `heartbeat_min_s` = 20, `stats` timbrate con
  `APP_BOOT_ID`, `heartbeat_at`).
- D-20 `_cadenza_battito` `service.py:3864-3895` (`_num` 3881-3891).
- D-67 `_gambe_vive` 5411-5421; D-68 `_cadenza_pubblicazione` 5424-5435 (`publish_heartbeat_s` = 5,
  `publish_idle_heartbeat_s` = 60); D-69 `_scrivi_evento` 5438-5471 (`stato_non_scritto`); D-70
  `_persist` 5474-5516 (firma 486-526); D-71 `_svuota_lotto` 5519-5540 (`events_batch_write`);
  D-73 `_FUORI_DAL_PUSH` 5950, `_pubblica_evento` 5953, `_pubblica_stato` 5961.
- D-92 `db.log` `db.py:71-80` (tabella attivita').

---

## 10 - Dormita («1 s o 5 s»)

**Cosa fa**
- Dopo ogni giro Mike dorme.
- Dorme poco (passo attivo) se c'e' fretta, se ci sono state azioni o regolamenti.
- Dorme di piu' (riposo) se non succede niente.
- Se l'interruttore della sveglia e' acceso, lo scanner puo' svegliare Mike prima della fine della
  dormita quando cambia una partita che Mike segue; anche la pagina puo' svegliarlo (solo un
  «svegliati», nessun ordine passa di qui).
- Per quante sveglie arrivino, fra l'inizio di un giro e il successivo passa almeno il passo attivo.
- Prima di dormire Mike ricarica l'atlante dei gol se il file e' cambiato (se il file sparisce resta
  l'ultimo buono).

**Quando**
- A fine di ogni giro, sempre, anche dopo un giro fallito.

**Numeri**
- Passo attivo = il piu' grande fra 1 s e (intervallo minimo di decisione x 2). Intervallo minimo di
  serie 500 ms (parametro, da 100 a 5000 ms, app): passo attivo 1,0 s.
- Riposo: 5,0 s (parametro, da 1 a 60 s, app).
- Passo di sicurezza se il giro esplode prima di calcolare: 2,0 s.
- Minimo fra due sveglie dalla pagina: 1,0 s.
- Sveglia: interruttore di serie SPENTO. Porta dello scanner 47336.

**Esempio con le cifre**
- Di notte, nessuna partita in gioco e nessun ordine: un giro ogni 5 s. Alle 20:45 una partita va in
  gioco: un giro ogni 1 s.
- Gol alle 21:14:03.200 con la sveglia accesa: lo scanner lo pubblica e Mike si sveglia invece di
  aspettare la fine della dormita; se la sveglia arriva 0,3 s dopo l'inizio del giro precedente,
  Mike aspetta fino a 1,0 s e riparte.

**Cosa vedi nell'app**
- Niente di diretto; con la sveglia accesa le sue statistiche in testata.

**Se qualcosa va storto**
- Canale dello scanner non raggiungibile: Mike dorme la pausa solita.
- Paper o live: identico.

**Per il tecnico**
- D-2 `_un_giro` `service.py:6035-6082` (passo 6051, fretta 6061-6062, dormita 6081; errore
  6070-6077 attivita' `error` `cycle_exception`); `decide_min_interval_ms` = 500, `idle_cycle_s` = 5.
- D-74 `service.py:5584-5617` (`_SVEGLIA`, `_ASCOLTO_SCAN`, `_AlzaSveglia`, `_evento_seguito`),
  5635-5646 (`_su_sveglia_dal_canale`), 5649-5685 (`_avvia_sveglia`); env `MIKE_SVEGLIA_CANALE`,
  `SAFE_SCAN_WS_PORT`; `sveglia_canale.MINIMO_UI_S` = 1,0.
- D-75 `_pavimento_sveglia` 5620-5632, `_client_scan_alza_sveglia` 5688, `statistiche_sveglia` 5697,
  `_dormi_o_sveglia` 5712-5718.

---

## 11 - Arresto («chiesto dall'app»)

**Cosa fa**
- Prima di ogni giro Mike controlla se l'app ha chiesto di spegnere i servizi in modo ordinato. Se
  si', Mike esce senza iniziare un altro giro e libera il posto unico (porta 47319). Il guardiano
  dell'app non lo rilancia.
- Un giro gia' iniziato non viene interrotto.

**Quando**
- Prima di ogni giro (non nel collaudo «un giro solo»).

**Numeri**
- La richiesta vale se il file d'arresto e' stato scritto dopo l'avvio di questo processo, con 2 s di
  tolleranza.

**Esempio con le cifre**
- L'utente chiude l'app mentre Mike sta piazzando una lay da 10,10 EUR a 1,88: il giro finisce (la
  lay parte e la riga viene scritta), al controllo successivo Mike esce.

**Cosa vedi nell'app**
- Niente (riga nel registro del processo «ARRESTO ORDINATO richiesto dall'app: esco»).

**Se qualcosa va storto**
- Ctrl+C nella finestra del processo: fine immediata.
- Paper o live: identico. Le posizioni aperte restano sul mercato; al prossimo avvio Mike riparte
  fermo e in paper ma le sorveglia (riquadro 02).

**Per il tecnico**
- D-3 `_ciclo_persistente` `service.py:5971-5984` (`arresto_ordinato.richiesto`); chiamata 6089;
  rilascio blocco 6090-6095.

---

## 12 - Giro saltato («database muto»)

**Cosa fa**
Questa scheda raccoglie cosa succede quando un pezzo del giro fallisce.
- Riga di controllo illeggibile o assente: il giro intero salta. Nessuna azione, NEMMENO le
  protezioni (coperture, uscite, ritiri, regolamento). Mike riprova al giro dopo (1-5 s).
- Elenco delle partite illeggibile senza copia in memoria: il giro salta.
- Un giro solleva un errore imprevisto: Mike lo registra, scrive una riga di errore in Attivita' e
  NON muore; dorme e riprova.
- Una partita solleva un errore: Mike passa alla successiva; le scritture di fine giro partono
  comunque.
- Controllo dell'apertura dell'app non concluso (database muto all'avvio): Mike non apre niente di
  nuovo finche' non riesce.

**Quando**
- In qualunque giro.

**Numeri**
- Nuovo tentativo: al giro dopo, 1 s o 5 s (riquadro 10); 2,0 s se il giro esplode prima di
  calcolare il passo.

**Esempio con le cifre**
- Database irraggiungibile per 90 s con un back Under 3.5 da 10,00 EUR aperto in gioco: per 90 s
  Mike non copre e non chiude (il giro salta). Se nel frattempo entrano 2 gol e la partita arriva a
  4, la perdita resta -10,00 EUR invece della copertura.
- Una scheda con una gamba illeggibile solleva un errore: le altre 9 partite continuano normalmente.

**Cosa vedi nell'app**
- Il battito smette di aggiornarsi; la pagina dichiara il servizio lento dopo la cadenza dichiarata
  (20 s con i valori di serie).
- In Attivita': errore del giro, errore della partita, lettura delle partite fallita.

**Se qualcosa va storto**
- E' gia' il riquadro dei guasti. Vedi «Punti da decidere» n. 3.
- Paper o live: identico.

**Per il tecnico**
- D-5 (`control_unreadable`, `no_control`), D-9 (`events_unreadable`, `events_failed`), D-2
  (`cycle_exception`), D-16 (`event_cycle`), D-4 (guardia `avvio_app`).

---

## Frecce

- 01 Accensione -> 02 App riaperta: l'identificativo dell'apertura dell'app e' diverso da quello
  salvato (o manca).
- 01 Accensione -> 03 Comandi: sempre, dopo il caricamento dell'atlante.
- 03 Comandi -> 04 Prezzi: riga di controllo letta.
- 03 Comandi -> 12 Giro saltato: riga di controllo illeggibile o assente.
- 12 Giro saltato -> 03 Comandi: al giro dopo, fra 1 s e 5 s.
- 04 Prezzi -> 05 Partite nuove: righe del feed ed elenco partite pronti (anche dalla copia in
  memoria).
- 05 Partite nuove -> 06 Giro partita: per ogni partita seguita, una alla volta.
- 06 Giro partita -> 07 Ordini: il motore ha deciso ordini da piazzare o annullare, o ci sono ordini
  in coda da piu' di 120 s o a esito ignoto.
- 07 Ordini -> 08 Regolamento: mercato chiuso (linea 3.5 chiusa, riga assente 10 minuti, 3 ore dal
  fischio, oppure 100 minuti dal fischio con partita vista in gioco). Nel codice questo controllo
  avviene all'inizio del giro della partita, prima degli ordini.
- 06 Giro partita -> 09 Battito: tutte le partite fatte.
- 09 Battito -> 10 Dormita: sempre.
- 10 Dormita -> 03 Comandi: dopo 1 s (fretta) o 5 s (riposo), o prima se arriva una sveglia (ma non
  prima di 1 s).
- 10 Dormita -> 11 Arresto: l'app ha scritto la richiesta d'arresto dopo l'avvio di Mike.

---

## Punti da decidere (capitolo 9)

Differenze dalla Costituzione (`Betfair/mike/COSTITUZIONE_MIKE.md`) e cose strane dell'inventario D
che riguardano il giro. Nessuna e' stata corretta: le decide l'utente.

1. **Feed illeggibile trattato come vuoto (dopo 10 minuti tutto in regolamento).** Se la lettura
   delle righe dello scanner fallisce, Mike la tratta come «nessuna riga» e la tiene per buona. Se il
   database dello scanner non risponde per piu' di 10 minuti, OGNI partita risulta «assente da 10
   minuti» e va in regolamento con letture da Betfair. Per le righe di ordine invece Mike distingue
   «non so» da «vuoto». (Cosa strana 2; `db.py:513-515`, `service.py:5891`, `4042-4047`.)
2. **Nessuna sorveglianza con riga assente o dati incompleti.** Con la riga assente da meno di 10
   minuti, o con una linea mancante, il giro della partita esce presto: non girano i ritiri a 120 s,
   la riconciliazione degli ignoti, la sorveglianza della sospensione, il seguito delle lay
   appoggiate. Gira solo la riparazione dello specchio. (Cosa strana 3; `service.py:4052-4055`,
   `4186-4207`.)
3. **Database muto = anche le protezioni si fermano.** Riga di controllo illeggibile: il giro salta
   per intero, coperture e uscite comprese (D-5).
4. **Costituzione §3 «il servizio gira ogni 1-2 secondi»**: il codice gira a 1,0 s con movimento e
   a 5 s a riposo, svegliabile (diff. 1).
5. **Costituzione §6 battito 10 s / statistiche 5 s e §12 H5 «battito al massimo ogni 10 s»**: il
   codice usa battito 20 s e statistiche 10 s; la stessa Costituzione §17.5 riporta 10/20, in
   contraddizione con se stessa (diff. 4).
6. **Costituzione §12 H2, §9, §10.A.2 «riconciliazione righe/gambe a OGNI ciclo»**: il codice la fa
   ogni 30 s per partita (diff. 6); anche la descrizione nel codice dice «a OGNI ciclo» (cosa
   strana 8).
7. **Costituzione §5 «stato riletto dal database a ogni ciclo»**: la riga di controllo si', le
   partite ogni 60 s (diff. 13).
8. **Costituzione §2 «Atlante caricato una volta»**: il codice lo richiede a ogni giro e lo ricarica
   se il file cambia (diff. 8).
9. **Due conti diversi per il tetto.** L'armamento delle partite nuove conta le partite non in
   osservazione e non «in gioco senza posizione»; il blocco delle aperture conta le partite con soldi
   sopra, anche in osservazione con un ordine vivo. Il numero che frena l'armamento puo' essere piu'
   basso di quello che frena le aperture (cosa strana 9; diff. 14 per la Costituzione §5 «max 10
   partite con POSIZIONE», che nel codice e' separato per paper e live).
10. **Costituzione §5 e §10.B.2 «in paper un ordine senza esito si risolve subito»**: per un ordine
    paper mandato al simulatore Mike NON risolve, aspetta il simulatore; un annullo paper senza
    numero scommessa porta la gamba in verifica (diff. 9).
11. **Stato del mercato chiuso preso solo dalla linea 3.5** (poi dal mercato principale): se chiude
    solo la 4.5 la partita non entra in regolamento (cosa strana 20).
12. **Costituzione §7 «in paper e in gioco il fill e' DIFFERITO... la lay appoggiata si considera
    abbinata quando il back supera il suo prezzo»**: dal 29/09 gli ordini paper e le lay appoggiate
    paper stanno sul book del simulatore; la vecchia coda differita non e' piu' alimentata da nessuno
    e l'abbinamento «simulato in casa» non esiste piu' (diff. 10). La coda viene ancora lavorata su
    dati vecchi e, dopo 30 s senza prezzo, piazza comunque con prezzo assente (cosa strana 4).
13. **Costituzione §7, §12 H3, §10.C.2 «in LIVE la lay appoggiata non esiste»**: nel codice la lay
    appoggiata live esiste; il passaggio a ordine a mercato avviene solo se l'utente spegne la lay
    appoggiata live; l'uscita al fischio e' appoggiata sempre (diff. 11; la descrizione nel codice
    dice ancora «sempre a mercato», cosa strana 8).
14. **Costituzione §5 e §7 «riconciliazione per riferimento `mike-t<id>`»**: il codice riconosce
    l'ordine per numero scommessa, riferimento `mike-t<id>` o riferimento storico a mercato
    concorde (diff. 16).
15. **Costituzione §12 H1 e §5 «con feed stantio il cash out viene RIFIUTATO»**: con il flusso
    interrotto Mike prova la lettura diretta da Betfair e, se legge il book, chiude con quei prezzi
    (diff. 18).
16. **Costituzione §2 e §11 «le sole chiamate a Betfair sono il book a mercato chiuso e la
    riconciliazione»**: la lettura diretta con flusso fermo aggiunge letture durante la partita
    (diff. 21).
17. **Costituzione §6 variabili d'ambiente**: il codice usa anche l'interruttore dei soldi veri, la
    porta del canale, la sveglia, il canale veloce, il canale delle posizioni, la porta dello
    scanner, il tetto assoluto del feed; la finestra dello scanner letta da Mike vale 0 di serie
    (diff. 19).
18. **Costituzione §16.4-bis blocchi 9-10**: i riferimenti alle righe del codice non corrispondono
    piu' (diff. 20).
19. **Orologio del freno dell'uscita in perdita**: usa l'ora del computer invece dell'ora del giro;
    in un replay il freno dei 5 minuti misura il tempo reale, non quello simulato (cosa strana 5).
20. **Messaggio di «Annulla ordini» impreciso**: conta come annullati anche gli ordini abbinati
    durante l'annullo (cosa strana 6).
21. **Ritiro non mandato al mercato se la riga non e' «in coda»**: con una riga gia' «aperta» e un
    residuo ancora vivo, il residuo non verrebbe annullato sul mercato (cosa strana 7; vedi «Punti
    non chiariti» n. 3).
22. **Righe di chiusura mai marcate orfane**, nemmeno in live (cosa strana 10).
23. **Riconciliazione con parametro a 0**: diventa 30 s, non 5 s, mentre la Costituzione e il
    commento dicono «minimo 5 s» (cosa strana 11).
24. **«Partite in gioco» in testata** conta anche partite chiuse che avevano «in gioco» salvato
    (cosa strana 15).
25. **«Stato non scritto»** dichiara «posizione aperta» anche se c'e' solo una gamba annullata
    (cosa strana 16).
26. **Commenti superati nel codice** (cosa strana 8): «2 s di default contro i 15 s» (reali 4 s e
    45 s); descrizione del modulo «in PAPER e in gioco il fill viene DIFFERITO».

## Punti non chiariti (capitolo 9)

1. Il motore (`engine.py`: decisione, applicazione, cash out, P&L per numero di gol) non e' stato
   letto in quest'area: le schede 06 e 07 lo trattano come «il motore decide» (inventario D, «Non ho
   capito» 1; dettagli negli altri capitoli).
2. Le funzioni dell'area del servizio e degli ordini (richieste, piazzamento, seguito paper e live,
   sospensione, posizione di conto) sono solo richiamate: dettaglio in `C_servizio_e_ordini.md`.
3. Non si sa se una riga di ordine possa diventare «aperta» mentre la gamba ha ancora un residuo vivo
   sul mercato: se non succede mai, il punto 21 e' innocuo.
4. I tempi massimi del database (5 s / 20 s) vengono da un commento, non dal codice di
   `db_client.timeout_bot`.
5. Moduli esterni non letti: canale dello scanner, canale locale, ascolto della sveglia, guardia
   dell'avvio app, saldo del conto.
6. Cosa fa esattamente l'app con le statistiche e le schede spinte sul canale: capitolo delle
   schermate.
