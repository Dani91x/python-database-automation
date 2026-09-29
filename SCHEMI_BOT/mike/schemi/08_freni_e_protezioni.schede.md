# Mike - Capitolo 8: freni e protezioni (schede)

Schema: `08_freni_e_protezioni.html` (sorgente `08_freni_e_protezioni.workflow.json`).
Fonte dei fatti: `SCHEMI_BOT/mike/inventario/C_servizio_e_ordini.md` (C-n), `A_calcoli_e_guardie.md`
(A-n), `D_giro_e_conti.md` (D-n), `B_strategia.md` (B-n). Ricontrollati sul codice:
`Betfair/mike/service.py:905-943` (rifiuto da freno), `Betfair/mike/feed.py:316-431` (prezzi vivi).

**Schede dell'inventario usate in questo file:**
- C: 1, 3, 5, 17, 18, 19, 22, 25, 26, 28, 29, 31, 33, 34, 36, 37, 42, 44, 45, 54, 55, 56, 57, 58.
- A: 3, 24, 25, 27, 44, 45, 71, 72, 73, 74, 75, 76, 77, 81, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94,
  95, 96, 97, 98, 99, 107, 116, 117, 121, 122, 125.
- D: 1, 3, 4, 5, 6, 10, 11, 13, 15, 17, 18, 21, 23, 34, 36, 37, 38, 45, 63, 81, 86, 87.
- B: 1, 43 e la premessa (regole che valgono sempre).

Come si legge: lo schema segue il percorso di un'APERTURA (ingresso, ultimo ingresso, seconda puntata,
copertura, rientro) dalla testa del giro fino all'invio. Ogni riquadro e' un freno: la freccia verso
destra o verso il basso e' il «via libera». Le chiusure entrano dal riquadro 11 e saltano i freni che
valgono solo per le aperture. Ogni riquadro porta la scritta «riquadro NN»: la scheda con lo stesso
numero lo spiega.

Per ogni freno la scheda dice: **cosa lo fa scattare** (coi numeri), **cosa blocca esattamente**,
**cosa resta permesso**, **come si sblocca**, **cosa vedi**.

Tabella riassuntiva (dettaglio nelle schede):

| Riquadro | Freno | Blocca aperture | Blocca copertura | Blocca chiusure | Si sblocca |
|---|---|---|---|---|---|
| 01 | Bot fermo / app appena aperta | ingresso, ultimo ingresso, rientro | no | no | Avvia |
| 01 | Arresto ordinato dell'app | tutto (Mike esce) | si' | si' | riaprire l'app |
| 02 | Stop giornaliero | ingresso, ultimo ingresso, rientro, partite nuove | no | no | mezzanotte di Roma |
| 03 | Ordine a esito ignoto | tutte | si' | no | da solo, a verifica fatta |
| 04 | Aperture ferme | tutte | si' | no | da solo, quando la causa sparisce |
| 05 | Freno coperture | - | si' | no | Riprendi (o motivo diverso) |
| 06 | Una banca sola / mai sovracopertura | la banca nuova | la copertura nuova | la banca nuova, per un giro | da solo, al giro dopo |
| 07 | Posto libero | tutte, sulle partite nuove | si', sulle partite nuove | no | da solo, quando un posto si libera |
| 08 | Prezzi non vivi | tutte | si' | SI' | da solo, quando i prezzi tornano |
| 08 | Flusso interrotto | ingresso, ultimo ingresso, seconda puntata, rientro | no | no | da solo |
| 09 | Freno unico e modo ordini | tutte | si' | no | spegnere il freno / rimettere LIVE |
| 10 | Interruttore soldi veri | tutto in live | si' | SI' (anche i ritiri) | accenderlo nel file di configurazione |

---

## 01 - Bot in marcia? (interruttore generale, avvio e arresto dell'app)

**Cosa fa**
- Mike apre posizioni nuove solo se il bot e' «in marcia» (pulsante Avvia) e l'app non e' appena
  stata riaperta.
- Con il bot fermo Mike spegne per il giro: ingresso prima del fischio, ultimo ingresso, rientro.
  Coperture, uscite, ritiri e regolamento continuano.
- All'apertura NUOVA dell'app Mike si rimette da solo fermo, in paper, con le uscite manuali. Soglie,
  importi e tetti non vengono toccati. Un riavvio dopo un crash (stessa apertura dell'app) non tocca
  niente.
- Arresto ordinato: quando chiudi l'app, Mike finisce il giro in corso ed esce.
- Paper o live: ogni partita tiene per sempre la modalita' che il bot aveva quando l'ha presa. Se
  cambi modalita' al bot, le partite gia' prese continuano nella loro.

**Quando**
- A ogni giro (circa ogni 1 secondo con movimento, 5 secondi a riposo).
- Il controllo dell'app appena aperta: una volta all'avvio e, finche' non riesce, all'inizio di ogni
  giro.

**Numeri**
- Tolleranza sull'ora del file d'arresto: 2 secondi.
- Una sola copia di Mike puo' girare (porta 47319 del computer).

**Esempio con le cifre**
- Ieri sera Mike era acceso in live. Stamattina apri l'app: Mike riparte fermo e in paper. La partita
  con la punta Under 3,5 da 10,00 euro gia' aperta continua a coprirsi e a uscire; nessuna partita
  nuova parte.
- Premi «Ferma» con una partita in gioco e l'Under aperto: Mike continua a coprire con l'Over 4,5 e a
  proporre le uscite; nessun ingresso nuovo.

**Cosa blocca / cosa resta permesso / come si sblocca**
- Blocca: ingresso del giro, ultimo ingresso, rientro, e l'armamento di partite nuove.
- NON blocca: seconda puntata dopo un gol presto (Punti da decidere 3), copertura, uscite, ritiri,
  regolamento.
- Si sblocca: premi «Avvia». Per il live scegli live tu: all'apertura dell'app torna sempre paper.
- Arresto ordinato: dopo l'uscita NESSUNA protezione gira finche' non riapri l'app.

**Cosa vedi nell'app**
- Il bot fermo. In testata l'indicazione che «Ferma» ferma solo le aperture.
- All'avvio dell'app una riga «i bot li accende l'utente: fermo, paper» (solo se c'era qualcosa da
  spegnere).
- Avviso rosso se restano partite vive nell'altra modalita' (per esempio partite live mentre il bot
  e' tornato in paper).

**Se qualcosa va storto**
- Se Mike non riesce a leggere la sua riga di controllo, salta il giro INTERO: niente aperture ma
  anche niente protezioni, finche' la lettura non torna.
- Se non riesce a leggere il controllo dell'app appena aperta, la guardia blocca le aperture finche'
  non ci riesce.

**Paper o live**
- Identico. All'apertura dell'app il live torna paper.

**Per il tecnico**
- `run_once` `service.py:3433-3453` (`running` = stato `running` e guardia d'avvio non bloccante);
  `_params_for` `:1268-1276` (spegne `pre_enabled`, `reentry_enabled`, `last_entry_persist`);
  `_GUARDIA_AVVIO` `:3396-3427`, `avvio_app.py:217-330`; arresto `_ciclo_persistente` `:5971-5984`;
  stato `stopping` -> `stopped` `:3667-3673`; partite nell'altra modalita' `:3547-3551`,
  `:3898-3908`; statistica `stop_ferma_solo_aperture`. Inventario C-33, D-1, D-3, D-4, D-5, D-6, D-11,
  D-13, D-17, D-18.

---

## 02 - Stop giornaliero

**Cosa fa**
- Mike somma il realizzato di oggi e il profitto gia' bloccato delle partite piazzate oggi. Se la
  somma arriva a -50 euro o peggio, Mike non apre piu' niente fino a domani.

**Quando**
- A ogni giro. «Oggi» comincia a mezzanotte di Roma e conta il giorno in cui la posizione e' stata
  piazzata.
- Conta SOLO la modalita' del bot in quel momento: il paper non ferma il live e viceversa.

**Numeri**
- Stop: 50 euro (parametro, da 0 a 100.000; 0 = spento).
- I numeri del giorno si rileggono al massimo ogni 20 secondi, e subito dopo ogni ordine.

**Esempio con le cifre**
- Realizzato oggi -38,40 euro, bloccato su partite ancora da pagare -12,10 euro. Totale -50,50: e'
  peggio di -50, quindi STOP.

**Cosa blocca / cosa resta permesso / come si sblocca**
- Blocca: partite nuove, ingresso del giro, ultimo ingresso, rientro.
- NON blocca: chiusure, coperture, seconda puntata (stessa regola del bot fermo), ritiri.
- Si sblocca: da solo al cambio di giornata (mezzanotte di Roma), oppure alzando o spegnendo lo stop.

**Cosa vedi nell'app**
- In testata «stop giornaliero» acceso e il P&L del giorno.
- Nell'attivita' una riga «stop giornaliero» una volta al giorno, con realizzato, bloccato e soglia.

**Se qualcosa va storto**
- Se il database non risponde, Mike usa l'ultimo valore buono della stessa modalita' (non zero). Se
  non ne ha mai letto uno, lo stop non vede niente.

**Paper o live**
- Ogni modalita' ha il suo stop.

**Per il tecnico**
- `run_once` `service.py:3538-3565`; `_aggregates_cached` `:1099-1146`; giornata `:3801-3815`;
  bloccato `:3911-3946`; `daily_loss_stop` (config). Attivita' `daily_stop`. Inventario C-28, D-10,
  D-21, D-23, A-125.

---

## 03 - Esito ignoto? (ordine in verifica)

**Cosa fa**
- Se la partita ha un ordine di cui Mike non conosce l'esito (capitolo 7, riquadro 06), Mike toglie
  dalla decisione TUTTE le aperture.
- L'ordine dubbio conta nel rischio come abbinato per intero. Il regolamento aspetta.

**Quando**
- A ogni giro, dopo la decisione del motore, finche' c'e' un ordine in verifica.

**Numeri**
- Verifica al massimo ogni 60 secondi. Avviso critico al massimo ogni 45 secondi.

**Esempio con le cifre**
- La banca di green 10,10 euro a 1,86 e' in verifica. Il motore vorrebbe la copertura Over 4,5 da
  2,26 euro: tolta. Resta la chiusura, se serve.

**Cosa blocca / cosa resta permesso / come si sblocca**
- Blocca: ingresso, ultimo ingresso, seconda puntata, COPERTURA, rientro. Se dopo il taglio non resta
  nessun ordine, la partita resta nella fase di prima.
- NON blocca: ritiri, chiusure.
- Si sblocca: da solo, quando la verifica chiarisce l'ordine (confermato o mai piazzato). «Riprendi»
  non lo sblocca.

**Cosa vedi nell'app**
- Nella scheda della partita il motivo «(ordine a esito ignoto: nessuna apertura)».
- Nell'attivita' l'avviso critico «ordine in verifica»; in testata le partite in verifica.

**Se qualcosa va storto**
- Se Betfair non si legge mai, la copertura non parte mai: la partita resta scoperta.

**Paper o live**
- Identico.

**Per il tecnico**
- `engine.decide` punto 4 `engine.py:2164-2216`; `has_unknown_orders` `:1822-1824`;
  `_strip_openings` `:1854-1879`; `_assume_matched` `:918-935`; regolamento sospeso `_dispatch`
  `:2435-2491`; ritmo `service.py:4351-4359`. Inventario A-3, A-44, A-45, A-88, A-90, A-97, D-41.

---

## 04 - Aperture ferme (dopo un freno che non e' il mercato)

**Cosa fa**
- Quando un'apertura e' fermata da un freno che non e' il mercato (freno d'emergenza, modo ordini non
  LIVE, freni illeggibili, simulatore giu' in paper), Mike lo dice UNA volta e ferma tutte le
  aperture della partita finche' la causa non cambia. Cosi' il motore non le ripropone a ogni giro.
- Prima di ogni decisione Mike rilegge la causa: se non c'e' piu', le aperture ripartono.

**Quando**
- Scatta: dopo il primo «no» di un freno non di mercato su un'apertura.
- Si ricontrolla: a ogni giro, prima della decisione del motore.

**Numeri**
- Nessuna soglia. Il motivo viene scritto fino a 120 caratteri.

**Esempio con le cifre**
- Live, modo ordini PAPER nel file di configurazione. La prima punta d'ingresso da 10,00 euro a 1,50 e'
  rifiutata «modo ordini non live». Una riga critica «aperture ferme». Nessuna riproposta finche' il
  modo non torna LIVE. Le chiusure continuano.

**Cosa blocca / cosa resta permesso / come si sblocca**
- Blocca: ingresso, ultimo ingresso, seconda puntata, copertura, rientro.
- NON blocca: chiusure, ritiri.
- Si sblocca: da solo quando la causa sparisce (simulatore di nuovo raggiungibile, freno d'emergenza
  spento, modo ordini tornato LIVE) oppure quando cambia la modalita' della partita. Se la causa non
  si riesce a valutare, restano ferme.

**Cosa vedi nell'app**
- Nell'attivita' una riga critica «aperture ferme» col motivo; poi «aperture riprese».
- Nella scheda della partita il motivo «(aperture ferme (...))».

**Se qualcosa va storto**
- Il «no» del freno e' anche contato come rifiuto del mercato (Punti da decidere 2).

**Paper o live**
- Paper: la causa si rilegge sul simulatore e sul freno d'emergenza.
- Live: la causa si rilegge su tutti i freni live (freno d'emergenza e modo ordini).

**Per il tecnico**
- `_rifiuto_non_di_mercato` `service.py:1821`, `_ferma_aperture` `:1826-1850`,
  `_causa_aperture_ferme` `:1851`, `_aggiorna_aperture_ferme` `:1862-1884` (uso `_run_event:4428`);
  prefissi `live_order_mode_non_live`, `live_kill_switch_attivo`, `db_kill_switch_attivo`,
  `kill_switch_illeggibile`, `freni_live_non_letti`, note di simulatore giu'. Memoria `aperture_ferme`.
  Attivita' `skip` (critica, `aperture_ferme=True`), `state aperture_riprese`. Inventario C-45, A-90,
  A-97, D-44.

---

## 05 - Freno delle coperture (3 rifiuti, 15 secondi)

**Cosa fa**
- Due regole sulla sola copertura Over 4,5:
  - **3 rifiuti con lo stesso motivo**: la copertura viene BLOCCATA. Un rifiuto con un motivo diverso
    fa ripartire il conteggio da 1 (e toglie il blocco).
  - **Ritmo minimo**: fra due tentativi di copertura passano almeno 15 secondi.
- Quando scatta, Mike toglie dalla decisione TUTTE le azioni della copertura (anche il ritiro della
  vecchia). Se la partita doveva passare ad «attesa della copertura» e non c'e' una copertura viva,
  torna «scoperta».
- All'invio c'e' una seconda barriera identica: se il freno e' scattato la copertura non parte.

**Quando**
- A ogni decisione che contiene una copertura, e a ogni invio di una copertura.
- Il conteggio cresce a ogni «no» definitivo sulla copertura. Mai su un esito ignoto.

**Numeri**
- Rifiuti prima del blocco: 3 (parametro, da 1 a 20).
- Ritmo minimo: 15 secondi (parametro, da 1 a 300; 0 = nessun ritmo).
- Il motivo viene confrontato sui primi 60 caratteri.

**Esempio con le cifre**
- Copertura 1,26 euro a 3,90 (sotto il minimo, «piazza e riduci»): Betfair rifiuta «non piazzato» tre
  volte di fila. Al terzo rifiuto la copertura e' BLOCCATA. La punta Under 3,5 da 10,00 euro resta
  scoperta: con 5 o piu' gol perdi -10,00 euro invece di +2,02.
- Tentativo alle 18:00:00, adesso 18:00:05: «copertura: ritento fra 10 s».

**Cosa blocca / cosa resta permesso / come si sblocca**
- Blocca: la sola copertura.
- NON blocca: uscite, chiusure, cash out, tetto di perdita.
- Si sblocca: con «Riprendi» (riquadro 12), oppure con un rifiuto dal motivo diverso. Il ritmo dei 15
  secondi si sblocca da solo.

**Cosa vedi nell'app**
- Nell'attivita': «rifiutato ... 1/3», «2/3», poi l'errore critico «copertura bloccata: serve un
  intervento (Riprendi) o un codice d'errore diverso».
- Nella scheda della partita: «copertura FERMATA dal freno: 3 rifiuti con lo stesso codice (...) -
  serve l'utente» oppure «copertura: ritento fra N s».

**Se qualcosa va storto**
- Anche un «no» del freno d'emergenza o del modo ordini conta come rifiuto (Punti da decidere 2).
- In paper il motivo contato e' la fase del simulatore: fasi diverse azzerano il conteggio
  (Punti da decidere 9).

**Paper o live**
- Stessa regola. Paper: motivo = fase del simulatore. Live: motivo = codice di Betfair.

**Per il tecnico**
- `engine._freno_copertura` `engine.py:2023-2074`; `registra_rifiuto_copertura` `:1595-1615`;
  `copertura_bloccata` `:1618-1621`; `segna_tentativo_copertura` `:1624-1635`;
  `attesa_ritento_copertura` `:1638-1650`; `sblocca_copertura` `:1653-1658`; `COVER_BLOCCATA` =
  `LIVE_COVER_BLOCKED`; memoria `cover_rifiuti`. Seconda barriera `service.py:677-690`; conteggio
  `_esito_rifiuto_mercato` `:946-1004`. Parametri `cover_rifiuti_max`, `cover_retry_min_s`.
  Inventario C-18, C-25, A-71..A-77, A-95, A-121.

---

## 06 - Una banca sola, mai sovracopertura (e niente doppioni)

**Cosa fa**
- **Una banca sola**: se su una selezione c'e' gia' una banca viva o in verifica, una banca nuova
  viene rimandata al giro dopo. Parte solo il ritiro della vecchia. La nuova arriva a ritiro
  confermato, calcolata sulla posizione vera.
- **Mai sovracopertura**: stessa regola per la copertura Over 4,5: mai una copertura nuova mentre ce
  n'e' una viva o in verifica.
- **Niente doppioni all'invio**: una chiusura o una banca in coda non parte se c'e' gia' una riga «in
  attesa» con lo stesso ruolo, lo stesso giro e lo stesso lato.
- **Niente richieste identiche gia' rifiutate**: stessa quota e stesso importo gia' rifiutati dal
  mercato non si ripropongono.

**Quando**
- A ogni decisione (una banca sola, mai sovracopertura) e a ogni invio (doppioni).

**Numeri**
- Richiesta identica: stessa quota, stesso importo entro 0,005 euro.

**Esempio con le cifre**
- 15/09, Beijing Guoan: 32 banche di green identiche da 5,07 euro a 1,43 in loop. Con questi freni ne
  resta una.
- 15/09, Trinec: 60 righe di chiusura da 0,20 euro. Con il freno doppioni ne nasce una.

**Cosa blocca / cosa resta permesso / come si sblocca**
- Blocca: la banca nuova (anche una chiusura) o la copertura nuova, per un giro.
- NON blocca: il ritiro della vecchia, le punte di chiusura, gli altri ordini.
- Si sblocca: da solo, al giro dopo il ritiro confermato.

**Cosa vedi nell'app**
- Nella scheda della partita: «(lay ... rimandata: ... e' ancora viva / a esito ignoto sulla stessa
  selezione (mai due lay a mercato))» oppure «(copertura rimandata ... (mai sovracopertura))».
- Nell'attivita' la riga critica «saltato: gamba gia' in volo» col numero della riga in attesa.

**Se qualcosa va storto**
- Se le righe della partita non si leggono, Mike fa come se il doppione ci fosse: nessun ordine.

**Paper o live**
- Identico.

**Per il tecnico**
- `lay_in_volo` `engine.py:1882-1898`, `_una_sola_lay` `:1901-1951`, `copertura_in_volo`
  `:1954-1969`, `_mai_sovracopertura` `:1972-2020`; `tentativo_gia_rifiutato` `:1522-1555`.
  Doppioni `service.py:656-669`, `_gia_appoggiata` `:1349-1387`, `_freno_gia_appoggiata` `:1727-1748`.
  Attivita' `place_saltato`. Inventario C-17, C-36, A-69, A-91..A-94, B premessa.

---

## 07 - Posto libero? (tetto delle partite)

**Cosa fa**
- Mike tiene aperte al massimo 10 partite con soldi sopra, contate SEPARATAMENTE per paper e per live.
- Una partita che non ha ancora soldi sopra puo' aprire solo se nella sua modalita' c'e' un posto.
  Una partita gia' esposta non viene mai bloccata.
- Appena una partita si espone, il posto e' occupato subito per le partite seguenti dello stesso giro.

**Quando**
- A ogni giro, per ogni partita. Il taglio avviene dopo la decisione del motore.

**Numeri**
- Tetto: 10 partite (parametro, da 1 a 90).
- Altro tetto, spento di serie: capitale puntato per partita (0 = spento). Se acceso, l'ingresso non
  parte se l'importo supera lo spazio rimasto.

**Esempio con le cifre**
- 10 partite esposte in paper. L'undicesima vorrebbe entrare a 1,85 con 10,00 euro: niente ingresso
  finche' un posto non si libera.
- Tetto 1 e una vecchia partita paper ancora viva: in live il posto e' libero.

**Cosa blocca / cosa resta permesso / come si sblocca**
- Blocca: tutte le aperture (compresa la copertura) sulle partite non ancora esposte, e l'armamento di
  partite nuove.
- NON blocca: ritiri, uscite, chiusure, cash out, e niente sulle partite gia' esposte.
- Si sblocca: da solo, quando una partita della stessa modalita' si chiude.

**Cosa vedi nell'app**
- Nell'attivita' «tetto partite» (motivo, tetto, stato).
- In testata: tetto, partite esposte (live e paper), aperture bloccate, «tetto partite raggiunto: N su
  M in live».

**Se qualcosa va storto**
- L'armamento delle partite nuove usa un altro conto del tetto (Punti da decidere 14).

**Paper o live**
- Conti separati.

**Per il tecnico**
- `service.py:3625-3656`, `posti_occupati_per_modo` `:3841-3861`, taglio `_run_event:4441-4445`;
  `engine.ha_esposizione` `engine.py:1827-1851`; `liability_room` `:1707-1714`; parametri
  `max_open_matches`, `max_liability_per_match`. Attivita' `tetto_partite`. Inventario A-81, A-89,
  B-1, D-13, D-15, D-45.

---

## 08 - Prezzi vivi? (prezzi vecchi, flusso interrotto, mercato sospeso)

**Cosa fa**
- **Prezzi vecchi**: se i prezzi non sono vivi, NESSUN ordine parte: ne' aperture ne' chiusure, in
  paper e in live (decisione dell'utente del 28/09).
- **Flusso dei prezzi interrotto** (lo scanner dichiara fermi i prezzi delle linee 3,5 o 4,5): con
  una posizione aperta Mike legge i prezzi direttamente da Betfair e li usa SOLO per chiudere, coprire
  e bancare il green. Ingresso, ultimo ingresso, seconda puntata e rientro restano bloccati.
- **Mercato non aperto** (sospeso, chiuso, sconosciuto): nessun ordine. La banca in coda aspetta la
  riapertura.
- **Quota sparita**: la quota voluta non c'e' piu': nessun ordine, e la stessa richiesta non si ripete
  identica.
- **Linee assenti dal feed** con una posizione aperta: niente copertura, niente cash out, niente
  uscite possibili; Mike lo grida.

**Quando**
- A ogni ordine, al momento dell'invio. Il controllo del flusso a ogni giro.

**Numeri**
- Prezzi vivi per un ordine: riga dei prezzi di al massimo 45 secondi, oppure scanner che ha scritto
  entro 75 secondi; oltre 180 secondi mai. Con la lettura diretta di Betfair i prezzi valgono come vivi.
- Per l'ingresso prima del fischio e per il cash out dell'utente la regola e' piu' severa: 20 secondi,
  oppure scanner entro 30 secondi.
- Lettura diretta di Betfair: al massimo una ogni 10 secondi per mercato.
- Flusso fermo: giro dello scanner fermo oltre 45 secondi.

**Esempio con le cifre**
- Under 3,5 aperto da 10,00 euro, flusso fermo da 70 secondi: Mike legge Betfair, trova 1,55/1,57 e
  puo' chiudere; non puo' aprire un giro nuovo.
- Prezzi di 60 secondi, scanner muto da 90 secondi: la banca di green non parte. Anche la chiusura non
  parte.

**Cosa blocca / cosa resta permesso / come si sblocca**
- Prezzi vecchi: blocca TUTTO. Resta permesso: niente ordini nuovi; i ritiri decisi dal motore non
  passano da questo controllo.
- Flusso interrotto: blocca le aperture tranne la copertura; chiusure, green e copertura passano coi
  prezzi di Betfair. Se la lettura diretta non da' niente, la posizione resta senza chiusura e senza
  copertura finche' un prezzo vivo non torna.
- Si sblocca: da solo, quando i prezzi tornano vivi o il mercato riapre.

**Cosa vedi nell'app**
- Nell'attivita' «prezzi vecchi», «flusso interrotto» (critica se c'e' posizione), «lettura diretta
  Betfair» (al massimo una al minuto), «flusso interrotto senza lettura diretta» con l'esposizione in
  euro, «attesa riapertura», «linee assenti dal feed».
- Nella pagina il semaforo del feed; il cash out rifiutato «Feed non aggiornato».

**Se qualcosa va storto**
- Se la riga della partita manca dal feed da meno di 10 minuti, il giro della partita finisce subito:
  non girano ritiri, verifica, sorveglianza della sospensione (Punti da decidere 16).

**Paper o live**
- Identico (anche il paper legge Betfair per la lettura diretta).

**Per il tecnico**
- `execute_place` `service.py:691-740`; `APERTURE_MIKE` `:1154`; `_books_ripiego_rest` `:1163-1190`;
  `_run_event:4186-4296`, banca in coda `:4464-4478`; `feed.feed_fresh` `feed.py:316-336`,
  `feed.order_fresh` `:339-371`, uso `:428-431`; flusso `feed.py:98-128`, `flusso_prezzi.py:147-237`.
  Parametri `feed_max_age_s`, `scanner_alive_max_s`, `order_max_age_s`, `order_scanner_max_s`; env
  `SCAN_FEED_HARD_MAX_AGE_SEC`. Attivita' `no_fill` (`feed_stantio`, `flusso_interrotto`),
  `flusso_interrotto`, `ripiego_rest`, `flusso_interrotto_senza_rest`, `attesa_riapertura`,
  `feed_line_missing`. Inventario C-19, C-29, C-31, C-43, C-55, A-24, A-25, A-27, D-34, D-36, D-37,
  D-38, D-81, D-86, D-87.

---

## 09 - Freno unico e modo ordini

**Cosa fa**
- **Freno d'emergenza unico**: un interruttore di tutto il sistema, acceso dalla Control Room (o dal
  file di configurazione). Se e' tirato, nessuna apertura parte, in paper e in live. Se non si riesce
  a leggerlo, Mike frena.
- **Modo ordini** (solo live): un tetto nel file di configurazione e la scelta della Control Room. Se
  non e' LIVE, nessuna apertura con soldi veri.
- Dopo il primo «no» le aperture della partita si fermano (riquadro 04).

**Quando**
- A ogni apertura, al momento dell'invio, dopo la riga dell'ordine.

**Numeri**
- Il freno scritto nel database viene riletto con una memoria di circa 2 secondi.

**Esempio con le cifre**
- Accendi il freno dalla Control Room. La punta d'ingresso paper da 10,00 euro successiva non parte;
  la banca di chiusura si'.

**Cosa blocca / cosa resta permesso / come si sblocca**
- Blocca: ingresso, ultimo ingresso, seconda puntata, COPERTURA, rientro.
- NON blocca: chiusure (cash out, uscite, tetto di perdita, green), ritiri.
- Si sblocca: spegni il freno, oppure rimetti il modo ordini su LIVE. Le aperture ripartono da sole al
  giro dopo (riquadro 04). Se pero' la copertura ha preso 3 «no» dal freno, resta bloccata finche' non
  premi «Riprendi» (Punti da decidere 2).

**Cosa vedi nell'app**
- Nell'attivita' la riga col motivo (freno attivo, modo ordini non live, freni illeggibili) e poi
  «aperture ferme».

**Se qualcosa va storto**
- Freni non leggibili: niente apertura (prudenza).

**Paper o live**
- Paper: solo il freno d'emergenza.
- Live: freno d'emergenza e modo ordini.
- Banca in coda: il freno vale solo sulle aperture; oggi tutte le banche in coda sono chiusure, quindi
  non scatta mai.

**Per il tecnico**
- Live `execution._live_brake` `execution.py:134-214`, uso `:872-874`; paper `blocco_paper`
  `service.py:839-841`; `_freno_aperture_rest` `:1801-1810`; `controls.motivo_kill_switch`
  `controls.py:107-132`; `_freno_resting_paper` `:1887-1900`; env `LIVE_KILL_SWITCH`,
  `LIVE_ORDER_MODE`, tabella `betfair_live_settings.kill_switch`. Inventario C-22, C-42, C-44, C-45.

---

## 10 - Soldi veri? (interruttore del live)

**Cosa fa**
- E' l'ultima barriera prima di Betfair. Se l'interruttore dei soldi veri nel file di configurazione
  del computer non e' acceso, NESSUN ordine reale parte: punta, banca, ritiro.
- Mike lo rilegge a ogni ordine: spegnerlo ha effetto subito.

**Quando**
- A ogni ordine reale di Mike, chiusure e ritiri compresi. Il paper non passa di qui.

**Numeri**
- Spento di serie. Si accende con 1, true, yes, on.

**Esempio con le cifre**
- Partita in live, Mike decide la copertura Over 4,5 da 2,26 euro. Interruttore vuoto: nessuna
  chiamata a Betfair; la riga resta in verifica e le aperture della partita si fermano.

**Cosa blocca / cosa resta permesso / come si sblocca**
- Blocca: OGNI ordine reale, anche le chiusure e i ritiri. L'ordine fermato diventa «esito ignoto»
  (riquadro 03).
- NON blocca: le letture (ordini vivi, risultati, prezzi).
- Si sblocca: scrivi l'interruttore acceso nel file di configurazione.

**Cosa vedi nell'app**
- In testata l'indicazione «live abilitato» si' o no.
- Nel registro del programma una riga critica «ORDINE REALE BLOCCATO ... impostare l'interruttore e
  riavviare l'app».

**Se qualcosa va storto**
- Con l'interruttore spento un ordine gia' vivo su Betfair non si puo' ritirare da Mike (Punti da
  decidere 6).

**Paper o live**
- Solo live.

**Per il tecnico**
- `mike_live_abilitato` `service.py:92-98`, `_LiveNonAbilitato` `:101-103`, `_pretendi_live_abilitato`
  `:106-114`, chiamate `:144`, `:162`, `:184`; env `MIKE_LIVE_ENABLED` (`config.py:62-66`);
  statistica `live_abilitato`. Inventario C-1, C-2, D-18.

---

## 11 - Chiusure protette (tetto di perdita, cash out, chiusura fatta da te)

**Cosa fa**
- Le chiusure entrano nel percorso dopo i freni delle aperture: NON le fermano bot fermo, stop
  giornaliero, esito ignoto, aperture ferme, freno coperture, posti, freno unico, modo ordini.
- Le fermano ancora: una banca sola / niente doppioni (riquadro 06), prezzi non vivi (riquadro 08),
  interruttore soldi veri (riquadro 10).
- **Tetto di perdita della partita**: a posizione coperta, se la perdita che si bloccherebbe chiudendo
  arriva al 100 per cento della base, Mike chiude tutto. E' SEMPRE automatico, anche con le uscite
  manuali.
- **Chiusura forzata** (Cash out o Flatten dalla pagina): Mike ritira subito tutti gli ordini vivi,
  poi chiude la posizione netta. Riprezza le chiusure ogni 10 secondi, fino a 20 tentativi. Prima del
  fischio la partita non rientra piu' finche' non premi «Riprendi».
- **Chiusura fatta da te fuori dall'app** (solo live): ogni 30 secondi Mike confronta la sua posizione
  con il conto. Se l'hai chiusa tu, Mike ritira i suoi ordini vivi e smette di gestire la partita.

**Quando**
- Tetto di perdita: nella fase «coperta», a ogni giro.
- Chiusura forzata: quando premi Cash out o Flatten.
- Chiusura fatta da te: al massimo ogni 30 secondi per partita, in live.

**Numeri**
- Tetto di perdita della partita: 100 per cento della base (parametro, da 0 a 500).
- Riprezzo delle chiusure: ogni 10 secondi; tentativi: 20.
- Posizione di conto: soglia 0,05 euro.

**Esempio con le cifre**
- Tetto: punta Under 10,00 + copertura 2,26 = base 12,26 euro. Mike chiude solo se il netto
  bloccabile e' -12,26 euro o peggio.
- Cash out: Under 3,5 aperto a 1,90 prima del fischio, banca di green in coda. Premi Cash out: la
  banca viene ritirata e parte la chiusura; «netto stimato +0,15 EUR».
- Chiusura fatta da te: Mike ha la punta Under da 10,00 euro; sul conto c'e' anche una tua banca da
  10,00: netto 0, «chiusa dall'utente»; da qui Mike non tocca piu' la partita.

**Cosa blocca / cosa resta permesso / come si sblocca**
- Queste sono protezioni: non bloccano, chiudono.
- Cash out rifiutato se: la partita non e' nel feed («Quote non disponibili»), prezzi vecchi («Feed
  non aggiornato»), flusso interrotto senza lettura diretta, richiesta di un'altra partita o di
  un'altra modalita' («paper e live non si mischiano»).
- Divieto di rientro dopo il cash out prima del fischio: si toglie con «Riprendi».

**Cosa vedi nell'app**
- «cap perdita evento: X»; «Cash out: annullati N ordini sul book, chiusura in corso (netto stimato X
  EUR)»; «chiusura manuale: annullo gli ordini vivi / attendo il fill / riprezzo / completata»;
  «chiuso dall'utente» (critica).

**Se qualcosa va storto**
- Finiti i 20 tentativi, il cash out resta «attendo il fill» senza piu' riprezzare (Punti da
  decidere 12).
- Tetto al 100 per cento: scatta solo quando non c'e' piu' niente da salvare (Punti da decidere 10).

**Paper o live**
- Tetto e cash out: identici. Chiusura fatta da te: solo live.

**Per il tecnico**
- Tetto `loss_cap` `engine.py` ramo `LIVE_COVERED` (B-43), `MOTIVI_PROTEZIONE` `engine.py:2225-2240`,
  `gate_uscite` `:2337-2431`; cash out `_request_flatten` `service.py:3283-3393`, `force_flat_plan`
  `engine.py:1786-1805`, `_decide_flatten` `:2077-2161`, `_close_actions` `:1754-1783`; controllo
  della richiesta `_richiesta_non_di_questa_partita` `service.py:3032-3074`; posizione di conto
  `_sorveglia_posizione_di_conto` `:2760-2869` (`_CONTO_EPS` 0,05). Parametri `event_loss_cap_pct`,
  `close_retry_s`, `close_max_attempts`, `reconcile_every_s`. Inventario A-84, A-85, A-96, A-98, A-107,
  B-43, C-3, C-54, C-56, C-57, D-63.

---

## 12 - Riprendi (pulsante dell'utente)

**Cosa fa**
- Su una partita saltata: la rimette in osservazione e toglie divieto di rientro e chiusura manuale.
- Su una partita con divieto di rientro, chiusura manuale in corso o copertura BLOCCATA: toglie tutti
  e tre (azzera il freno delle coperture). La fase della partita resta quella di prima.
- Altrimenti rifiuta: «stato non riprendibile».

**Quando**
- Quando premi «Riprendi». Mike lo esegue al giro successivo, prima delle partite.

**Numeri**
- Nessuno.

**Esempio con le cifre**
- La copertura Over 4,5 da 1,26 euro e' bloccata dopo 3 rifiuti. Premi Riprendi: il freno si azzera,
  al giro dopo Mike ritenta la copertura (almeno 15 secondi dopo l'ultimo tentativo).

**Cosa blocca / cosa resta permesso / come si sblocca**
- NON sblocca: stop giornaliero, esito ignoto, aperture ferme, freno unico, modo ordini, interruttore
  soldi veri, bot fermo, tetto delle partite. Quelli si sbloccano da soli o dai loro interruttori.
- Su una partita in errore («da sistemare») non la riattiva (Punti da decidere 7).

**Cosa vedi nell'app**
- «Rientro riabilitato» e, se c'era, il verbale del freno delle coperture sbloccato.
- Oppure il rifiuto «stato non riprendibile».

**Se qualcosa va storto**
- Una partita regolata o in errore rifiuta ogni richiesta tranne Riprendi, che pero' non cambia la
  fase.

**Paper o live**
- Identico.

**Per il tecnico**
- `process_requests` `service.py:3077-3178` (ramo `resume` `:3134-3170`); `engine.sblocca_copertura`
  `engine.py:1653-1658`; codici `_REJECT_CODES` `:3012-3029`. Attivita' `resume_event`. Inventario
  C-56, A-76.

---

## Frecce

- 01 Bot in marcia -> 02 Stop giornaliero: bot «in marcia» e guardia dell'app conclusa. Se no: niente
  ingresso, ultimo ingresso, rientro; la copertura e la seconda puntata proseguono.
- 02 Stop giornaliero -> 03 Esito ignoto: realizzato di oggi + bloccato sopra -50 euro (o stop spento).
- 03 Esito ignoto -> 04 Aperture ferme: nessun ordine della partita in verifica.
- 04 Aperture ferme -> 05 Freno coperture: nessuna memoria di aperture ferme, o causa sparita.
- 05 Freno coperture -> 06 Una banca sola: meno di 3 rifiuti uguali e almeno 15 secondi dall'ultimo
  tentativo (vale solo se l'ordine e' una copertura; gli altri passano).
- 06 Una banca sola -> 07 Posto libero: nessuna banca o copertura viva o in verifica sulla stessa
  selezione, nessun doppione in attesa.
- 07 Posto libero -> 08 Prezzi vivi: partita gia' esposta, oppure meno di 10 partite esposte nella sua
  modalita'.
- 08 Prezzi vivi -> 09 Freno unico: prezzi vivi (45 s / 75 s / mai oltre 180 s), mercato aperto, quota
  ancora disponibile, e (per le aperture) flusso non interrotto.
- 09 Freno unico -> 10 Soldi veri: freno d'emergenza spento e, in live, modo ordini LIVE. In paper
  l'ordine va al simulatore e il riquadro 10 non vale.
- 10 Soldi veri -> Betfair: interruttore acceso.
- 11 Chiusure protette -> 06 Una banca sola: le chiusure entrano qui; saltano i riquadri 01-05, 07 e 09.
- 12 Riprendi -> 05 Freno coperture: azzera il freno (e toglie divieto di rientro e chiusura manuale).

Nota sull'ordine: nel programma il taglio del tetto delle partite (07) avviene dopo la decisione del
motore e prima dell'invio, quindi dopo i riquadri 03-06; i controlli 08-10 avvengono all'invio. Lo
schema segue questo ordine.

---

## Punti da decidere

Differenze dalla Costituzione (`Betfair/mike/COSTITUZIONE_MIKE.md`) e cose strane degli inventari che
riguardano freni e protezioni.

1. **La copertura e' frenata come un'apertura.** Per il codice la copertura Over 4,5 e' un'apertura:
   la fermano esito ignoto, aperture ferme, tetto delle partite, freno d'emergenza e modo ordini
   (`execution.py:872`, `service.py:839-841`, `_ferma_aperture` include la copertura). Con il flusso
   interrotto invece e' trattata come protezione e parte (`APERTURE_MIKE`, `service.py:1154`). Due
   regole diverse per la stessa gamba. Effetto pratico: con un freno tirato una punta Under gia' aperta
   resta scoperta.
2. **Il «no» di un freno contato come rifiuto del mercato.** `service.py:927` e `:934` prima di
   `:939-942`: il freno delle coperture conta i «no» del freno d'emergenza e del modo ordini; dopo 3
   la copertura resta bloccata anche a freno spento, finche' «Riprendi». Il commento di `_rifiutata`
   dice che si scrive solo per risposte definitive del mercato.
3. **Bot fermo e stop giornaliero non fermano la seconda puntata.** Costituzione §5: con il bot fermo
   nessun ingresso. Codice: si spengono ingresso, rientro e ultimo ingresso, NON la seconda puntata
   dopo un gol presto (`service.py:1268-1276`; `engine.py:3044` guarda solo `second_entry_enabled`).
4. **Prezzi vecchi: chiusure bloccate.** Costituzione §5: «nessun ingresso; chiusure permesse».
   Codice: nessun ordine, chiusure comprese, paper e live (`service.py:709-717`), per decisione
   dell'utente del 28/09. La Costituzione va aggiornata o la regola rivista.
5. **Mike e il modo ordini.** Costituzione §16.1: Mike non e' coperto dal modo ordini. Codice: le
   aperture live passano dal freno live (freno d'emergenza + modo ordini); la banca in coda live solo
   dal freno d'emergenza e solo sulle aperture; le chiusure solo dall'interruttore soldi veri.
6. **Interruttore soldi veri spento blocca anche ritiri e chiusure** (`service.py:144`, `:162`,
   `:184`): un ordine gia' vivo su Betfair resta vivo e ogni tentativo va in verifica. Il messaggio
   dice «riavviare l'app», ma il valore si rilegge a ogni ordine.
7. **«Riprendi» su una partita in errore.** Costituzione §5: raggiungibile anche su errore e partita
   saltata. Codice: su errore non cambia la fase; funziona solo se c'e' divieto di rientro, chiusura
   manuale o copertura bloccata (`service.py:3134-3170`).
8. **Il freno delle coperture non e' nella Costituzione** (§15.7-ter cita solo «mai sovracopertura»);
   nel codice viene prima di «una banca sola», e dopo «una banca sola» vengono ancora «mai
   sovracopertura» e il cancello delle uscite (la Costituzione chiama «una banca sola» l'ultima
   parola).
9. **Freno coperture in paper**: il motivo contato e' la fase del simulatore; fasi diverse azzerano il
   conteggio: il freno puo' non scattare mai. Inoltre QUALSIASI motivo diverso sblocca la copertura
   senza «Riprendi».
10. **Tetto di perdita della partita al 100 per cento**: scatta solo quando la perdita bloccabile e'
    pari alla base intera, cioe' quando non c'e' piu' niente da salvare: in pratica spento.
11. **Il freno delle coperture scarta TUTTI gli aggiornamenti della decisione**, non solo quelli della
    copertura come dice il commento (`engine.py:2073`).
12. **Cash out a tentativi finiti** (20): resta «attendo il fill» senza riprezzare (`engine.py:2100-2103`).
13. **Freni sulla banca in coda mai usati oggi**: tutte le banche in coda sono chiusure, quindi i rami
    di freno d'emergenza (`service.py:1933-1942`, `_freno_resting_paper`) non scattano mai; l'ordine
    fra freno e doppioni e' diverso fra paper e live (senza effetto oggi).
14. **Due conti diversi per il tetto delle partite**: l'armamento delle partite nuove conta le partite
    non in osservazione; il taglio delle aperture conta anche una partita in osservazione con un ordine
    vivo (`service.py:3580-3583` contro `engine.py:1827-1850`). Costituzione §5: tetto unico, non
    separato per modalita'.
15. **Soglie dei prezzi vivi.** Costituzione §5-§6: riga oltre 15 secondi E scanner muto oltre 30
    secondi. Codice: 45 s / 75 s per gli ordini, 20 s / 30 s per ingresso e cash out, tetto 180 s.
16. **Riga assente dal feed per meno di 10 minuti**: il giro della partita esce presto; non girano il
    ritiro degli ordini fermi da 120 secondi, la verifica degli ignoti, la sorveglianza della
    sospensione, il seguito delle banche in coda. Feed illeggibile = feed vuoto: dopo 10 minuti ogni
    partita va in regolamento.
17. **Riga di controllo illeggibile**: il giro intero viene saltato, protezioni comprese.
18. **Uscite manuali.** Costituzione §15.7-ter: le uscite di Mike restano automatiche. Codice: uscite
    manuali di serie; restano automatiche la copertura e il tetto di perdita.
19. **Stop giornaliero, numeri di ripiego**: quando manca la procedura del database i totali cumulati
    (non quelli del giorno) sommano paper e live (`db.py:394`, `:401-411`).

## Punti non chiariti

1. Non ho letto `execution._live_brake` riga per riga (inventario C lo riassume): l'ordine esatto fra
   freno d'emergenza e modo ordini e il testo dei motivi vengono dall'inventario.
2. Non ho verificato in quale file di configurazione si imposta il modo ordini ne' i valori ammessi
   oltre a OFF / PAPER / LIVE.
3. La memoria di circa 2 secondi del freno nel database viene da un commento, non verificata.
4. Come la pagina mostra i messaggi (area E non letta per questo capitolo): i testi fra «» sono il
   senso o il testo dell'inventario, non sempre quello esatto sullo schermo.
5. Se esiste oggi una decisione che mette insieme un'uscita e un'apertura: con le uscite manuali il
   cancello toglierebbe anche l'apertura o la copertura (inventario A, Cose strane 10). Non verificato.
