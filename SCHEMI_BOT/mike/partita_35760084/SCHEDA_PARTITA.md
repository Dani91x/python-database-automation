# Come ha perso Mike la partita 35760084 (Liepajas Metalurgs - Ogre United, 4-0)

**Corretta due volte il 29/09 dopo revisioni indipendenti**: la prima correggeva 1 frase sbagliata e 6
punti (orari, minuto del 4o gol, fonte del referto, tabelle dei tre esiti). La seconda TOGLIE una
spiegazione ancora sbagliata (perche' le proposte si fermano dopo le 19:41) e AGGIUNGE un difetto vero
trovato da un'indagine dedicata (riquadro 7 dello schema 3: la chiusura sull'Over 4,5 viene bloccata dopo
il quarto gol). L'elenco preciso delle correzioni e' nella risposta al coordinatore; qui c'e' gia' il testo
corretto.

Scheda in parole semplici sotto i quattro schemi `01_pre_partita.html`, `02_dal_fischio_alla_copertura.html`,
`03_gol_e_finale.html`, `04_guasto_dati.html`. Leggila insieme alla pagina unica
`COME_HA_PERSO_35760084.html`, che contiene gli stessi schemi e lo stesso testo in un solo file.

**Orari**: tutti gli orari sono ITALIANI (ora legale, UTC+2). L'orario UTC della registrazione e' scritto
in piccolo una sola volta, al primo orario di riferimento (l'ingresso, 17:08:09); da li' in poi capisci
l'UTC sottraendo 2 ore da qualunque orario italiano.

**Fonti**: il referto corrente del coordinatore, `AUDIT_2026-09-29/replay/mike_tutti_P4_4_P5_1.txt`
(scenario `[base]`) — **verificato**: sui numeri chiave (5 ordini, 2 abbinamenti a 14,00 EUR ai prezzi
1,71/4,00, P&L -14,00 EUR, 17 proposte/15 decadute, gli stessi due "motivo x223"/"x159") coincide col
referto usato nella prima stesura (`mike_tutti_P2_P4_2.txt`); cambiano solo dettagli legati al tempo reale
di esecuzione (un avviso `skip`/`punteggio_assente_tornato` in piu', 129,7 s invece di 148,3 s di durata:
rumore fra due run, non la condotta). Poi: una sonda di sola lettura sullo stesso replay di produzione
(scenari `base` e `lettura-dati-ko`, vedi in fondo), la registrazione grezza della partita
(`_live_raw/35760084/`, sia `35760084.jsonl` — un book per mercato ogni aggiornamento, sia
`35760084.scores.jsonl` — minuto e punteggio), le schede di Mike in
`SCHEMI_BOT/mike/schemi/02_prima_del_fischio.schede.md` e `03_dal_fischio.schede.md`, il piano
`PIANO_MODIFICHE_MIKE_2026-09-29.md`, e **l'indagine dedicata**
`AUDIT_2026-09-29/INDAGINE_MIKE_MERCATO_DECISO.md` (fatta da un'altra sessione il 29/09: spiega il
riquadro 7 «DIFETTO TROVATO» dello schema 3 e i numeri della copertura nuova con l'interruttore acceso).
Ogni numero qui sotto viene da una di queste fonti; dove manca un dato e' scritto "non rilevato" con il
motivo.

**Risultato**: Mike ha perso **14,00 EUR** netti su questa partita: 10,00 EUR sulla punta Under 3,5 (persa,
la partita ha fatto 4 gol) e 4,00 EUR sulla copertura Over 4,5 (persa, servivano 5 gol o piu'). Commissione
pagata: 0,00 EUR, perche' nessuna delle due gambe ha vinto (la commissione del 5% si paga solo sulle
vincite).

---

## Schema 1 - Prima del fischio (`01_pre_partita.html`)

### Riquadro 1 - Mike vede la partita
- **Cosa fa**: Mike inizia a guardare la partita e a fare i controlli d'ingresso.
- **Quando**: al primo giro utile della finestra pre-partita (fino a 1 ora prima del fischio).
- **Numeri**: fischio d'inizio programmato **18:00:00**; Mike la vede alle **17:08:09**
  (UTC: 15:08:09), 52 minuti prima.
- **Esempio con le cifre**: da qui al fischio passano circa 52 minuti.
- **Cosa vedi nell'app**: la partita compare come «osservata», nessuna posizione.
- **Se qualcosa va storto**: se i controlli d'ingresso non passano, Mike riprova al giro dopo (in questa
  partita non e' successo: e' entrato al primo tentativo).
- **Per il tecnico**: `Betfair/mike/engine.py` `_entry_guard` (13 controlli); nel replay: primo giro con
  `state: WATCH -> PRE_ENTRY_PENDING`, `reason: "ingresso ciclo 1"`.

### Riquadro 2 - Punta Under 3,5
- **Cosa fa**: Mike punta 10,00 EUR sull'Under 3,5 al miglior prezzo disponibile.
- **Quando**: appena i controlli d'ingresso sono tutti positivi.
- **Numeri**: importo 10,00 EUR (lo standard di ogni ingresso), quota 1,71 (dentro la banda ammessa
  1,30-3,00).
- **Esempio con le cifre**: 10,00 EUR a 1,71: se l'Under 3,5 vince (0-3 gol) Mike incassa 7,10 EUR lordi
  (6,75 EUR netti dopo il 5% di commissione); se perde (4 gol o piu') Mike perde i 10,00 EUR.
- **Cosa vedi nell'app**: «ingresso ciclo 1», poi «ingresso abbinato».
- **Se qualcosa va storto**: non e' successo qui - la punta si e' abbinata per intero, subito.
- **Per il tecnico**: scommessa `100000000001`, ruolo `under_entry`, lato back, market `1.259475537`
  (Over/Under 3,5), selezione `1222344` (Under 3.5 Goals). Riga `mike_trades` id 1, stato finale `open`.

### Riquadro 3 - Banca appoggiata
- **Cosa fa**: appena la punta e' abbinata, Mike appoggia sul book una banca (lay) 2 tick sotto il prezzo
  medio d'ingresso, per tutta l'esposizione: se qualcuno la prende, il profitto (piccolo) e' bloccato
  subito.
- **Quando**: subito dopo l'ingresso abbinato (qui: alle 17:08:11, 2 secondi dopo).
- **Numeri**: quota 1,69 (2 tick sotto 1,71), importo 10,12 EUR. Ordine «fino al fischio» (in gergo
  Betfair: persistenza LAPSE): se nessuno la prende, Betfair la cancella da sola al passaggio in gioco.
- **Esempio con le cifre**: se la banca a 10,12 EUR a 1,69 si fosse abbinata, il risultato sarebbe stato
  bloccato a circa +0,12/+0,13 EUR netti in entrambi gli esiti (vincita o perdita dell'Under 3,5).
- **Cosa vedi nell'app**: «green resting sul book», «posizione aperta».
- **Se qualcosa va storto**: qui e' andata cosi': nessuno ha abbassato il prezzo fino a 1,69 prima del
  fischio, quindi la banca e' rimasta sola sul book, non abbinata.
- **Per il tecnico**: scommessa `100000000002`, ruolo `under_green`, lato lay, quota 1,69, importo 10,12
  EUR, persistenza LAPSE. Riga `mike_trades` id 2, stato finale `error` (mai abbinata, cancellata da
  Betfair), motivo scritto da Mike: `runner_scaduto`.

### Riquadro 4 - 10' dal fischio
- **Cosa fa**: con le regole di sempre, a 10 minuti dal fischio Mike si sarebbe chiesto se chiudere subito
  conviene, o se attivare il veto sull'Under 3,5. Con la regola decisa dall'utente il 29/09 (gia' nel
  codice di questo replay), **questo controllo non c'e' piu': la banca resta li' cosi' com'e' fino al
  fischio**, e Mike non chiude mai in perdita nel pre-partita.
- **Quando**: al segno dei 10 minuti prima del fischio, se c'e' una posizione aperta.
- **Numeri**: nessuno: e' proprio il punto, non succede nulla di nuovo.
- **Esempio con le cifre**: non applicabile: nessun ordine nuovo, nessun calcolo nuovo.
- **Cosa vedi nell'app**: lo stato del servizio resta `HOLD` con il motivo scritto una sola volta, subito
  dopo l'ingresso: «ultimo ingresso: posizione aperta, nessun altro ingresso; la banca resta fino al
  fischio».
- **Se qualcosa va storto**: non applicabile qui.
- **Per il tecnico**: regola M2.1/M2.4 del piano 29/09 (`PIANO_MODIFICHE_MIKE_2026-09-29.md`, righe
  64-151); nel replay lo stato passa `PRE_OPEN -> HOLD` con quel motivo esatto, una volta sola, molto
  prima del segno dei 10 minuti (alle 17:08, cioe' 52 minuti prima del fischio), perche' Mike era gia'
  entrato ed era gia' piatto (nessun altro ingresso da fare).

### Riquadro 5 - Fischio d'inizio
- **Cosa fa**: al passaggio in gioco, Betfair cancella da sola la banca pre-partita mai abbinata
  (persistenza LAPSE = «fino al fischio»). Mike si ritrova con la sola punta Under 3,5 abbinata, senza
  nessuna banca.
- **Quando**: al calcio d'inizio.
- **Numeri**: partita vista in gioco circa alle 18:01; gol al fischio: 0.
- **Esempio con le cifre**: in mano restano solo i 10,00 EUR a 1,71 sull'Under 3,5, nessuna copertura.
- **Cosa vedi nell'app**: «in gioco: provo l'uscita a +2 tick» (la fase cambia da pre-partita a in gioco).
- **Se qualcosa va storto**: e' cosi' che e' andata: la banca a 1,69 (riquadro 3) non si e' mai abbinata ed
  e' stata cancellata da Betfair al fischio.
- **Per il tecnico**: `engine.py:2636-2666`; stato `WATCH -> ... -> LIVE_KO_GREEN`. La riga `mike_trades`
  id 2 resta con stato `error`/`runner_scaduto` per l'annullamento subito da Betfair.

### Frecce (schema 1)
- Mike vede la partita -> Punta Under 3,5: controlli d'ingresso tutti superati.
- Punta Under 3,5 -> Banca appoggiata: ingresso abbinato per intero, subito.
- Banca appoggiata -> 10' dal fischio: nessun abbinamento della banca nel frattempo.
- 10' dal fischio -> Fischio d'inizio: la banca resta li' (regola 29/09), nessuna mossa nuova.

### Punti da decidere (schema 1)
- Le vecchie regole (veto sull'Under 3,5, chiusura al mercato a 10 minuti dal fischio, descritte in
  `SCHEMI_BOT/mike/schemi/02_prima_del_fischio.schede.md`) NON sono quelle viste in questo replay: quel
  documento descrive il comportamento di Mike PRIMA del piano del 29/09. In questa partita il
  comportamento osservato e' gia' quello nuovo (banca ferma fino al fischio, nessuna chiusura in perdita
  nel pre-partita).

---

## Schema 2 - Dal fischio alla copertura (`02_dal_fischio_alla_copertura.html`)

### Riquadro 1 - Fischio d'inizio
- **Cosa fa**: Mike annota il prezzo dell'Under al fischio (1,71) e i gol al fischio (0), poi prova a
  chiudere con una banca a 2 tick sotto, in gioco.
- **Numeri**: finestra di 3 minuti (180 secondi) da quando Mike vede il gioco. Gioco visto: circa 18:01.
- **Per il tecnico**: `engine.py:2636-2666`.

### Riquadro 2 - Prova uscita +2 tick
- **Cosa fa**: Mike appoggia una banca a 1,69 (stessa quota di prima) per chiudere in gioco. In questa
  partita ci sono stati DUE tentativi.
- **Numeri**: quota 1,69, importo 10,12 EUR, finestra 180 secondi.
- **Esempio con le cifre**:
  - 1o tentativo (scommessa `100000000003`, inviata alle **18:00:31**): resta sul book, nessuno la
    prende, **scade** da sola (motivo scritto: `runner_scaduto`).
  - 2o tentativo (scommessa `100000000004`, inviata alle **18:02:00**): questa volta e' Mike a ritirarla
    (`cancelled_by_engine`), ma Betfair NON conferma l'annullamento in tempo: la riga resta «in
    riconciliazione», e alla fine il motivo scritto e' `runner_annullato`.
- **Cosa vedi nell'app**: due righe nella scheda Trade, nessuna delle due abbinata; nell'attivita' due
  avvisi CRITICI («annullo NON confermato»).
- **Se qualcosa va storto**: questo E' il caso «qualcosa va storto»: il secondo annullamento resta incerto
  (esito `pending_reconcile`), ma non cambia il risultato finale perche' nessuna delle due banche era
  comunque abbinata.
- **Per il tecnico**: righe `mike_trades` id 3 e id 4, ruolo `ko_green`, entrambe stato finale `error`.

### Riquadro 3 - Finestra 3' scaduta
- **Cosa fa**: passati i 3 minuti dal momento in cui Mike ha visto il gioco, senza nessun gol e senza
  nessun abbinamento, Mike smette di provare a chiudere e passa alla copertura piena.
- **Numeri**: 180 secondi.
- **Cosa vedi nell'app**: «uscita non abbinata in 3': copertura Over 4.5».
- **Per il tecnico**: `engine.py:2963-2981`; stato `LIVE_KO_GREEN -> LIVE_UNCOVERED`.

### Riquadro 4 - Copertura Over 4,5
- **Cosa fa**: Mike punta sull'Over 4,5 un importo calcolato per rendere, se arrivano 5 gol o piu', 1,2
  volte la perdita che farebbe sull'Under 3,5 (al netto della commissione del 5%).
- **Numeri**: rischio Under = 10,00 EUR; obiettivo netto con 5+ gol = 12,00 EUR; miglior quota Over 4,5 al
  minuto 2 (punteggio 0-0, ore **18:03:32**) = 4,00; importo pieno = 12,00 / ((4,00-1) x 0,95) = **4,21
  EUR**.
- **Esempio con le cifre**: Mike ha chiesto 4,21 EUR a quota 4,00 (con un margine di sicurezza: l'ordine e'
  uscito con un limite di 3,90, per non perdere l'abbinamento durante l'attesa di Betfair); il mercato ne
  ha abbinati **4,00 EUR** alla quota 4,00: **0,21 EUR sono rimasti scoperti**.
- **Cosa vedi nell'app**: «copertura Over 4.5»; il conto della copertura nel diario (importo calcolato,
  importo piazzato, quota, rischio).
- **Se qualcosa va storto**: qui il "qualcosa" e' che la copertura NON si e' abbinata tutta: e' una
  conseguenza dei passi/limiti di importo di Betfair su una PUNTATA (minimo 2,00 EUR, passi da 0,50); il
  piano del 29/09 (M3.1, non ancora fatto) vuole cambiare questo lato in una BANCA sull'Under 4,5, che non
  ha questo limite (vedi «Cosa cambia con le modifiche del 29/09» in fondo).
- **Per il tecnico**: scommessa `100000000005`, ruolo `over_cover`, lato back, market `1.259475534`
  (Over/Under 4,5), selezione `1222346` (Over 4.5 Goals). `engine.py:3299-3339` (`cover_residual`).

### Riquadro 5 - Posizione coperta
- **Cosa fa**: con la copertura piazzata, Mike smette di agire e sorveglia soltanto: aspetta la fine della
  partita o un evento che cambi le carte (nuovo gol, sospensione, uscita in perdita firmata dall'utente).
- **Numeri**: esposizione ferma a 14,00 EUR (10,00 sull'Under 3,5 + 4,00 sulla copertura) da qui alla fine.
- **Cosa vedi nell'app**: stato `LIVE_COVERED`.
- **Per il tecnico**: `state: LIVE_COVER_PENDING -> LIVE_COVERED`, motivo «copertura abbinata».

### Frecce (schema 2)
- Fischio d'inizio -> Prova uscita +2 tick: in gioco, prova l'uscita con la banca a 2 tick sotto.
- Prova uscita +2 tick -> Finestra 3' scaduta: il primo tentativo scade, il secondo viene ritirato senza
  conferma; nessuno dei due si abbina.
- Finestra 3' scaduta -> Copertura Over 4,5: passati 180 secondi senza gol e senza abbinamento.
- Copertura Over 4,5 -> Posizione coperta: 4,00 EUR abbinati su 4,21 chiesti (copertura parziale, ma il
  mercato non ne offriva altro entro i suoi limiti).

### Punti da decidere (schema 2)
- Non rilevato con certezza il motivo esatto per cui il primo tentativo (id 3) e' «scaduto» mentre il
  secondo (id 4) risulta «annullato da Mike, non confermato»: il referto e la sonda concordano sui fatti
  (due tentativi, nessuno abbinato) ma non spiegano riga per riga perche' la logica ha provato due volte
  invece di una; per la risposta esatta serve leggere `engine.py:3001-3060` (`_decide_ko_green`), non
  fatto in questo lavoro (compito di sola lettura, tempo limitato).

---

## Schema 3 - I gol e il finale (`03_gol_e_finale.html`)

### Riquadro 1 - Gol 1: minuto 7 (1-0)
- **Cosa fa**: Mike non fa nulla: e' gia' coperto (schema 2) da prima di questo gol.
- **Numeri**: punteggio 1-0, ore **18:08:24**. Quota Under 3,5 poco prima del gol: circa 1,75; circa 40
  secondi dopo (il mercato si sospende per il gol e poi riapre): quota Under 3,5 back circa 2,32-2,46,
  quota Over 4,5 back circa 2,36. (Prezzi presi dalla registrazione dei book, il piu' vicino disponibile:
  vedi «Come sono stati presi i numeri».)
- **Perche' nessuna seconda puntata**: la seconda puntata su un gol precoce esiste solo se il gol arriva
  MENTRE la banca d'uscita in gioco e' ancora aperta, entro i 3 minuti dal fischio (schema 2, riquadro
  2-3). Qui il gol arriva al minuto 7: la copertura era gia' stata piazzata al minuto 2. Niente seconda
  puntata.
- **Per il tecnico**: `engine.py:3037-3050` (strada C, gol precoce) non si e' mai attivata: Mike era gia'
  in `LIVE_COVERED`.

### Riquadro 2 - Gol 2: minuto 27 (2-0)
- **Cosa fa**: Mike non fa nulla, stesso motivo.
- **Numeri**: ore **18:28:27**. Quota Under 3,5 poco prima del gol: circa 2,10; circa 55-70 secondi dopo:
  back circa 3,30-3,55. Quota Over 4,5 poco prima: circa 2,60; dopo: back circa 1,90-1,98 (l'Over 4,5
  diventa piu' probabile man mano che arrivano gol).

### Riquadro 3 - Gol 3: minuto 45 (3-0)
- **Cosa fa**: per la prima volta il conto di Mike segna una perdita se chiudesse subito: nasce la prima
  proposta di uscita in perdita.
- **Numeri**: ore **18:46:43**. Quota Under 3,5 poco prima del gol: circa 2,82; circa 30-70 secondi dopo:
  back 6,20-7,20 (si allunga molto: con 3 gol gia' fatti, l'Under 3,5 puo' vincere solo se la partita NON
  segna piu' nessun gol nei restanti 45 minuti). Quota Over 4,5 poco prima: circa 2,74; dopo: lay circa
  1,71-1,82 (l'Over 4,5 diventa molto probabile).
- **La pausa dell'intervallo**: fra le 18:48 e le 19:03 (circa 15 minuti reali) il feed dei minuti/punteggio
  non manda niente di nuovo: e' l'intervallo. Per questo il minuto "45" di Mike compare due volte: una
  volta a fine primo tempo (finestra chiamata "ht", il conto fatto proprio all'intervallo) e una volta di
  nuovo come riferimento fisso quando riprende la ripresa.
- **Per il tecnico**: evento `loss_exit_deciso`, poi `uscita_proposta` con `chiave: "chiusura|c0"`,
  `close_reason: "loss_2t"` o `"loss_ht"`.

### Riquadro 4 - 17 proposte in perdita (dalle 18:48 alle 19:41)
- **Cosa fa**: da qui alla fine dei dati disponibili, il modello di Mike ricalcola in continuazione se
  chiudere subito costa meno che tenere, e OGNI VOLTA che la risposta e' «si'» scrive una nuova proposta.
  Con le uscite manuali (impostazione di serie), NESSUNA parte da sola: serve la firma dell'utente. Nel
  replay nessuno firma mai, quindi ogni proposta resta ferma finche' non decade (il conto torna a
  convenire di piu' tenendo, oppure mancano prezzi per calcolarlo) o non arriva una proposta piu'
  aggiornata.
- **Due numeri diversi, due cose diverse (chiarimento)**: il referto del banco conta ANCHE quante volte,
  a ogni giro di controllo (circa ogni 0,5-2 secondi), il motivo scritto era «chiudere ora costa X»: su
  2464 righe di scansione in tutta la partita, 223 volte X era -2,34 EUR e 159 volte era -2,38 EUR. Questi
  due numeri NON sono nella tabella qui sotto perche' non sono mai diventati una PROPOSTA UFFICIALE
  scritta nell'attivita' del servizio (`mike_activity`): sono letture intermedie del prezzo, viste dal
  mercato ma senza mai superare la soglia/il freno che promuove un valore a proposta vera. In quale
  finestra di minuti siano cadute esattamente **non e' rilevato**: per saperlo servirebbe leggere le righe
  della scansione una per una con il loro orario, non catturate da questa sonda (che legge l'attivita' del
  servizio, non le righe dello scanner).
- **Numeri - le 17 proposte, in ordine di orario reale (non tutte nell'ordine del "minuto" di Mike, per il
  motivo dell'intervallo spiegato sopra)**:

| # | Ora (italiana) | Minuto di Mike | Gol visti | Chiuderebbe a | Decade? |
|---|---|---|---|---|---|
| 1 | 18:48:25 | 47 (2t) | 3 | -2,74 EUR | sostituita subito dalla n. 2 (nessuna riga a parte) |
| 2 | 19:03:38 | 45 (ht, intervallo) | 3 | **-2,50 EUR** | sostituita subito dalla n. 3 (nessuna riga a parte) |
| 3 | 19:07:56 | 46 (2t) | 3 | -2,48 EUR | si', "tengo" |
| 4 | 19:08:47 | 46 | 3 | -2,59 EUR | si', "tengo" |
| 5 | 19:09:03 | 47 | 3 | -2,74 EUR | si', "tengo" |
| 6 | 19:09:27 | 48 | 3 | -2,62 EUR | si', "tengo" |
| 7 | 19:19:34 | 57 | 3 | -3,16 EUR | si', "prezzi incompleti" |
| 8 | 19:20:23 | 59 | 3 | -3,50 EUR | si', "tengo" |
| 9 | 19:20:33 | 59 | 3 | -3,46 EUR | si', "tengo" |
| 10 | 19:22:48 | 61 | 3 | -3,68 EUR | si', "prezzi incompleti" |
| 11 | 19:23:48 | 61 | 3 | -3,61 EUR | si', "prezzi incompleti" |
| 12 | 19:25:33 | 64 | 4 | -2,54 EUR | si', "tengo" |
| 13 | 19:25:42 | 64 | 4 | -2,54 EUR | si', "tengo" |
| 14 | 19:27:20 | 66 | 4 | -2,63 EUR | si', "tengo" |
| 15 | 19:30:38 | 69 | 4 | -3,32 EUR | si', "tengo" (25 minuti dopo: vedi sotto) |
| 16 | 19:41:04 | 79 | 4 | -6,12 EUR | si', "tengo" |
| 17 | 19:41:34 | 79 | 4 | -6,28 EUR | si', "tengo" |

  "2t"/"ht" sono le due finestre di calcolo di Mike (secondo tempo in corso / fine primo tempo). Riga 15:
  fra la proposta delle 19:30:38 e la sua decadenza (alle **19:40:40**, circa **10 minuti** dopo, non 25
  come scritto in una stesura precedente di questa scheda) la proposta **non e' rimasta ferma**: e' stata
  RICALCOLATA a ogni giro (fra 40 e 50 volte al minuto) con l'Over 4,5 sempre vivo, e decade solo quando il
  conto cambia verso (vedi sotto il perche').
- **Le decadute**: 15 delle 17 hanno una riga di decadenza a parte (12 volte «la strategia non vuole piu'
  uscire: tengo», 3 volte «prezzi incompleti»). Le prime due (righe 1 e 2) NON hanno una riga di decadenza
  a parte: sono semplicemente sostituite dalla proposta successiva nello stesso giro. **Le ultime due
  (righe 16 e 17, minuto 79) DECADONO ANCH'ESSE** (motivo «tengo», poco dopo essere state scritte): non
  restano affatto aperte.
- **Il quarto gol (19:23:59) NON e' un guasto sul mercato Under/Over 3,5**: e' Betfair che lo CHIUDE e lo
  REGOLA, alle **19:25:25**, appena la linea e' decisa (Under 3,5 perdente, Over 3,5 vincente). Succede a
  OGNI linea Over/Under di questa partita, pochi secondi dopo che e' stata superata: la 0,5 alle 18:09:10
  (dopo il 1o gol), la 1,5 alle 18:29:42 (dopo il 2o), la 2,5 alle 18:47:57 (dopo il 3o). Non e' un
  comportamento raro: verificato uguale su altre 3 registrazioni diverse. Il file grezzo che questa scheda
  usa altrove (`35760084.jsonl`) mostra come ultima riga "SOSPESO" solo perche' non porta la chiusura vera
  e propria (quella e' in `35760084.raw.jsonl`, `marketDefinition.status`); il servizio di Mike nel replay
  vede la stessa cosa (il mercato resta "sospeso" ai suoi occhi, non "chiuso"): e' proprio QUESTO scambio
  la causa del difetto spiegato nel riquadro 7 qui sotto.
- **Il conto di Mike dopo il quarto gol e' GIUSTO**: usa l'esito CERTO della gamba ormai decisa (Under 3,5
  = -10,00, senza bisogno di nessun prezzo) piu' l'incasso dell'Over 4,5 al prezzo VIVO del momento (il
  prezzo del 3,5 non serve piu' ed e' giustamente ignorato). Esempio, proposta n. 12 (19:25:33): Under 3,5
  = -10,00 certo; Over 4,5 banca a 1,35 -> +7,46 netto; totale -2,54 EUR (combacia col referto della sonda).
- **PERCHE' non nasce piu' nessuna proposta dopo le 19:41:47**: NON e' il flusso fermo (le proposte 12-17
  nascono TUTTE con quel mercato gia' "fermo" agli occhi di Mike dalle 19:25:25) e non sono tentativi
  esauriti. E' che, minuto dopo minuto, l'Over 4,5 si allunga (banca da 1,98 a 4,8) e "chiudere ora" scende
  PIU' IN FRETTA della soglia del modello: da -6,12 a -10,75, mentre la soglia scende solo da -6,29 a
  -8,66; dalle 19:41:47 chiudere vale ormai MENO che tenere, quindi «tengo». Dal minuto 86 (primo giro
  19:49:49) la finestra delle uscite in perdita del secondo tempo (dal 46' all'85', parametri
  `h2_loss_from_min`/`h2_loss_to_min`) e' chiusa: da li' Mike scrive solo «tengo» o «prezzi incompleti»,
  mai piu' un calcolo pieno.
- **Se l'utente avesse firmato: dipende da PRIMA o DOPO il quarto gol.** PRIMA (proposte 1-11, mercato 3,5
  ancora aperto e regolare): la firma sarebbe partita senza problemi. Provato nella sonda con la firma vera
  di produzione sulla proposta delle 19:20:22 (flusso ancora vivo): la chiusura si esegue, risultato
  **-3,45 EUR**. Firmando la proposta n. 2 (19:03:38, «chiudendo al minuto 45»): **-2,50 EUR**. **DOPO**
  (proposte 12-17, mercato 3,5 chiuso e regolato da Betfair): la firma NON sarebbe bastata, per il difetto
  del riquadro 7 - vedi li' i numeri esatti.
- **Per il tecnico**: `engine.py` ramo «chiusura» di `gate_uscite` (uscite manuali); chiave `chiusura|c0`;
  il motivo per giro viene da `Decision.reason` (`engine.py:2623`, ricalcolato ogni giro, e' la fonte dei
  «motivo x223»/«x159» del referto); la proposta ufficiale (`uscita_proposta` in `mike_activity`) passa da
  un freno separato che ne scrive una nuova riga solo al cambiamento. Il conto dopo il gol decisivo:
  `selection_decided` (666-677), `cashout_value` (933-1005, la selezione decisa vale -10,00 "senza
  prezzo"), `_decide_covered` (4067-4083). La finestra delle uscite in perdita: `_loss_rule` (4057-4064),
  `config.py:300-301`. Vedi `PIANO_MODIFICHE_MIKE_2026-09-29.md` M8.1 («ogni uscita in perdita chiede la
  sua firma», gia' cosi' anche prima del piano).

### Riquadro 5 - Gol 4: minuto 62 (4-0)
- **Cosa fa**: nessuna azione di Mike; il risultato finale si fissa.
- **Numeri**: il punteggio passa a 4-0 alle **19:23:59** (minuto 62 per il feed). Il mercato Under/Over 3,5
  viene CHIUSO E REGOLATO da Betfair poco dopo, alle **19:25:25** (Under 3,5 perdente): non e' un guasto,
  e' la stessa cosa che succede a ogni linea Over/Under appena la partita la supera (vedi riquadro 4).
  Quota Over 4,5 poco prima del gol: circa 2,26; dopo: back circa 1,22-1,36.
- **Perche' e' decisivo**: con 4 gol esatti, l'Under 3,5 (che vince solo con 0-3 gol) e la copertura Over
  4,5 (che vince solo con 5 gol o piu') PERDONO ENTRAMBE. E' l'unico risultato in cui si perde su tutte e
  due le gambe (vedi tabella sotto). Ed e' anche il risultato in cui scatta il difetto del riquadro 7: solo
  quando una linea si decide DURANTE la partita (non gia' prima) Mike prova a chiudere su un mercato che
  Betfair ha appena chiuso.

### Riquadro 6 - Fine mercato
- **Cosa fa**: la partita finisce 4-0; entrambe le gambe sono chiuse in perdita dal regolamento del
  mercato (nessuna firma dell'utente e' mai arrivata).
- **Numeri**: Under 3,5 (10,00 EUR a 1,71): **-10,00 EUR**. Copertura Over 4,5 (4,00 EUR a 4,00, i soli
  davvero abbinati): **-4,00 EUR**. Totale: **-14,00 EUR**. Commissione: 0,00 EUR (nessuna vincita da
  tassare).
- **Per il tecnico**: referto certificazione, riga «P&L del replay: lordo -14.00 | commissione 0.00 (5.0%)
  | NETTO -14.00 EUR».

### Riquadro 7 - DIFETTO TROVATO (accertato, non ancora corretto)
- **Cosa fa**: dopo il gol che decide una linea (qui: il quarto gol, sul 3,5), Mike scambia il mercato
  CHIUSO E REGOLATO da Betfair per «flusso prezzi fermo» e blocca OGNI ordine sulla partita - anche la
  chiusura sull'Over 4,5, che ha prezzi VIVI e nessun problema.
- **Quando**: da quando una linea si decide DURANTE la partita (qui: il 3,5 al quarto gol, 19:25:25) fino
  alla fine.
- **Numeri**: firma di produzione vera provata dalla sonda sulla proposta n. 12 (19:25:33, «chiudendo ora
  -2,54»): **21 tentativi rifiutati** (motivo `no_fill feed_stantio` sulla banca Over 4,5 a 1,34-1,36, un
  prezzo vivo e abbinabile), poi tentativi esauriti, risultato comunque **-14,00 EUR**. Controllo: la
  STESSA firma PRIMA del quarto gol (19:20:22, flusso ancora vivo) fa partire la chiusura subito, risultato
  **-3,45 EUR**.
- **Esempio con le cifre**: senza il difetto, firmando alle 19:25:34 la proposta di -2,54 EUR, la perdita
  si sarebbe fermata li'. Col difetto, la firma non serve a niente e si arriva comunque a -14,00 EUR:
  **danno di 11,46 EUR** in questa partita (12,03 EUR se la copertura fosse gia' la banca Under 4,5 nuova,
  M3.1: vedi «Cosa cambia con le modifiche del 29/09»).
- **Cosa vedi nell'app**: la proposta di chiusura resta visibile e sembra firmabile; dopo la firma, nessuna
  conferma arriva e la posizione resta aperta - la parte piu' insidiosa del difetto, perche' l'utente non
  ha modo di saperlo dalla sola proposta.
- **Se qualcosa va storto**: lo stesso muro blocca anche il cash out manuale (pulsante) e il cash out
  automatico in profitto; il regolamento finale invece NON e' bloccato (la partita si chiude comunque a
  fine gara).
- **Stato**: difetto **ACCERTATO** e **RIPRODOTTO** da un test dedicato, correzione minima **PROPOSTA** e
  **NON ANCORA APPLICATA**: decide l'utente.
- **Per il tecnico**: catena `Betfair/mike/feed.py` `mercati_di_mike` (107-116, non distingue le linee gia'
  decise) -> `flusso_esito` (119-128) -> `snapshot_from_row` (`feed_fresh=False`, 391-431) ->
  `Betfair/mike/service.py` `execute_place` (742-750, blocca su `feed_fresh` falso, in paper E in live).
  Test nuovo (non committato): `Betfair/mike/tests/test_mike_indagine_mercato_deciso_2026_09_29.py`
  (3 rossi, 3 verdi di confine). Correzione minima proposta: `feed.py:107-116`, non passare a
  `flusso_esito` le linee gia' decise dal punteggio. **Fonte**:
  `AUDIT_2026-09-29/INDAGINE_MIKE_MERCATO_DECISO.md` (indagine dedicata del 29/09, non in questo lavoro).

### Frecce (schema 3)
- Gol 1 -> Gol 2: fuori dai 3 minuti dal fischio, niente seconda puntata.
- Gol 2 -> Gol 3: Mike aspetta, e' gia' coperto.
- Gol 3 -> 17 proposte in perdita: il modello vede il conto in rosso e comincia a proporre di chiudere.
- 17 proposte in perdita -> Gol 4: l'utente non firma mai, ogni proposta decade.
- Gol 4 -> Fine mercato: 4 gol esatti, perse entrambe le gambe.
- Gol 4 -> DIFETTO TROVATO (ramo a parte, non e' successo nel replay: nessuno firma): il mercato del 3,5,
  chiuso da Betfair, viene scambiato per fermo e blocca la chiusura sull'Over 4,5.

### Tabella - se la partita fosse finita diversamente (con i numeri REALI di questa partita: 4,00 EUR
davvero abbinati sulla copertura, non i 4,21 chiesti)

| Gol finali | Under 3,5 (10,00 EUR a 1,71) | Copertura Over 4,5 (4,00 EUR abbinati a 4,00) | Totale |
|---|---|---|---|
| 0-3 gol | +6,75 EUR (netti) | -4,00 EUR | **+2,75 EUR** |
| 4 gol (il risultato vero) | -10,00 EUR | -4,00 EUR | **-14,00 EUR** |
| 5 gol o piu' | -10,00 EUR | +11,40 EUR (netti) | **+1,40 EUR** |

Calcolo, commissione 5% inclusa dove c'e' una vincita: Under 3,5 vincente = 10,00 x (1,71-1) x 0,95 = 6,745
-> 6,75 EUR netti; perdente = -10,00 EUR (si perde lo stake, niente commissione su una perdita). Over 4,5
vincente (sui 4,00 EUR davvero abbinati) = 4,00 x (4,00-1) x 0,95 = 11,40 EUR netti; perdente = -4,00 EUR.
Questi sono i tre esiti REALI di questa partita col suo vero abbinamento parziale; la tabella con la
copertura "piena" (4,21 EUR, mai davvero abbinata) e' in fondo, nel confronto con la copertura futura.

---

## Schema 4 - Lo scenario del guasto dei dati (`04_guasto_dati.html`)

**Attenzione**: questo NON e' quello che e' successo davvero nella partita. E' un secondo replay,
richiesto apposta, sullo stesso ingresso e la stessa partita, ma con un guasto simulato nella lettura dei
dati (scenario di certificazione `lettura-dati-ko`, gia' previsto dal banco comune: serve a controllare che
Mike si comporti bene anche quando i dati si interrompono). Il risultato finale e' diverso (-17,50 EUR
invece di -14,00 EUR) perche' il guasto ritarda la copertura.

### Riquadro 1 - Fischio d'inizio
- **Cosa fa**: Mike entra in gioco con la stessa punta Under 3,5 (10,00 EUR a 1,71, stesso ingresso dello
  scenario reale) e la stessa banca pre-partita cancellata da Betfair al fischio.
- **Numeri**: fischio circa alle **18:00**.

### Riquadro 2 - Lettura dati caduta (12 minuti)
- **Cosa fa**: proprio al fischio, la lettura dei dati (`safe_strategy_scan`) smette di funzionare. Mike
  ritenta a ogni giro con l'ultima lista buona: nessuna partita viene data per sparita, nessun ordine parte
  su prezzi vecchi.
- **Numeri**: guasto dalle **18:00:30** alle **18:12:31** (720,7 secondi = 12,0 minuti).
- **Cosa vedi nell'app**: «lettura del feed FALLITA: si ritenta a ogni giro, nessuna partita viene data per
  sparita», poi «lettura del feed RIPRESA dopo 721 s».
- **Per il tecnico**: attivita' `replay_lettura_ko` (guasto=true poi guasto=false), poi `error` con
  `reason: "lettura_feed_fallita"`, poi `skip` con `reason: "lettura_feed_ripresa"`. Scenario di
  certificazione M8.7/M8.8.

### Riquadro 3 - Ripresa: un tentativo di banca in gioco
- **Cosa fa**: appena il feed torna, Mike prova UNA sola banca a 1,69 in gioco (invece dei due tentativi
  dello scenario reale: qui c'e' meno tempo utile per via del guasto).
- **Numeri**: banca inviata alle **18:12:32** (scommessa `100000000003`).
- **Esempio con le cifre**: Mike stesso la ritira (`cancelled_by_engine`); Betfair non conferma
  l'annullamento in tempo (la riga resta in riconciliazione), motivo finale scritto `runner_annullato`.

### Riquadro 4 - Copertura Over 4,5
- **Cosa fa**: passata la finestra, Mike copre sull'Over 4,5, come nello scenario reale ma piu' tardi e con
  un punteggio gia' diverso.
- **Numeri**: copertura inviata alle **18:15:32**, minuto 14, punteggio gia' 1-0 (il primo gol e' arrivato
  proprio durante il guasto). Rischio Under 10,00 EUR, obiettivo netto con 5+ gol 12,00 EUR, quota Over 4,5
  al minuto 14 = 2,64. Importo pieno = 12,00 / ((2,64-1) x 0,95) = **7,70 EUR** chiesti; abbinati **7,50
  EUR**.
- **Se qualcosa va storto**: qui la copertura arriva 12 minuti piu' tardi che nello scenario reale
  (minuto 14 invece di minuto 2): la quota Over 4,5 nel frattempo si e' gia' accorciata (da 4,00 a 2,64
  perche' un gol era gia' arrivato), quindi serve un importo molto piu' grande (7,70 invece di 4,21) per
  ottenere lo stesso obiettivo di 12,00 EUR netti.
- **Per il tecnico**: scommessa `100000000004`, ruolo `over_cover`.

### Riquadro 5 - 10 proposte in perdita
- **Cosa fa**: stesso schema dello scenario reale: dal minuto 47 al minuto 79, il modello propone 10 volte
  di chiudere in perdita (contro le 17 dello scenario reale: qui il rischio assicurato e' piu' alto fin
  dall'inizio, quindi le cifre e le soglie del modello si muovono un po' diversamente).
- **Numeri**: 8 proposte decadono per iscritto; nessuna e' mai firmata dall'utente.

### Riquadro 6 - Fine mercato
- **Cosa fa**: stesso finale a 4 gol esatti dello scenario reale.
- **Numeri**: Under 3,5 persa -10,00 EUR; copertura Over 4,5 persa (7,50 EUR a 2,64) -7,50 EUR. **Totale
  -17,50 EUR**: 3,50 EUR in piu' di perdita rispetto allo scenario reale, proprio per il ritardo della
  copertura causato dal guasto.

### Frecce (schema 4)
- Fischio d'inizio -> Lettura dati caduta: la lettura dei dati smette di funzionare.
- Lettura dati caduta -> Ripresa: un tentativo: 720,7 secondi dopo, nessuna partita data per sparita.
- Ripresa: un tentativo -> Copertura Over 4,5: la banca in gioco non si abbina, Mike copre.
- Copertura Over 4,5 -> 10 proposte in perdita: col passare dei gol il conto peggiora.
- 10 proposte in perdita -> Fine mercato: l'utente non firma mai, 4 gol esatti.

### Punti non chiariti (schema 4)
- Non rilevato con certezza perche' in questo scenario Mike prova UNA sola banca in gioco (invece di due
  come nello scenario reale): plausibile che sia solo perche' il tempo disponibile nella finestra dei 3
  minuti e' diverso dopo un guasto, ma non l'ho verificato leggendo il codice riga per riga.

---

## Cosa cambia con le modifiche decise il 29/09

Solo le parti che riguardano DAVVERO questa partita (fonte: `PIANO_MODIFICHE_MIKE_2026-09-29.md`).

### Gia' nel codice (visto in questo replay)
1. **Uscite in profitto automatiche** (banche di green pre-partita e in gioco): questo replay mostra che
   la banca pre-partita (riquadro 3, schema 1) e i due tentativi di banca in gioco (riquadro 2, schema 2)
   partono DA SOLI, senza passare per una proposta da firmare - a differenza delle uscite in PERDITA
   (schema 3, riquadro 4), che restano sempre proposte.
2. **Banca pre-partita tenuta fino al fischio** (M2.1/M2.4): il replay mostra lo stato che passa
   direttamente a «la banca resta fino al fischio» appena la punta si abbina, senza nessuna scelta
   ulteriore al segno dei 10 minuti (schema 1, riquadro 4).

### Ancora in costruzione, dietro interruttore (non ancora attiva di serie)
3. **La copertura come BANCA sull'Under 4,5, non piu' PUNTA sull'Over 4,5** (M3.1-M3.3, parametro
   `cover_form=lay_under45`). Il codice ce l'ha **gia'**, ma dietro un interruttore **spento di serie**, e
   finora provato **solo in certificazione**, non sulla partita vera. In questa partita la copertura
   davvero eseguita (schema 2, riquadro 4) e' ancora una punta Over 4,5 da 4,21 EUR chiesti, 4,00 abbinati.

**Con l'interruttore acceso, PROVATO sulla stessa partita (non un'ipotesi a mano: replay vero con
`cover_form=lay_under45`)**: la banca Under 4,5 si abbina **per intero**, 12,63 EUR a quota 1,33. Tre
risultati:

| Gol finali | Under 3,5 | Banca Under 4,5 (12,63 EUR a 1,33, abbinata per intero) | Totale | Oggi (punta Over 4,5, 4,00 EUR abbinati) |
|---|---|---|---|---|
| 0-3 gol | +6,75 EUR | -4,17 EUR | **+2,58 EUR** | +2,75 EUR |
| 4 gol (il risultato vero) | -10,00 EUR | -4,17 EUR | **-14,17 EUR** | -14,00 EUR |
| 5 gol o piu' | -10,00 EUR | +12,00 EUR | **+2,00 EUR** | +1,40 EUR |

Lettura: con la banca nuova, sui 4 gol veri la perdita sarebbe stata quasi identica (-14,17 invece di
-14,00: 0,17 EUR in piu', perche' oggi la copertura era rimasta scoperta per 0,21 EUR, un caso raro e per
questa volta favorevole). Con 5 gol o piu' avrebbe protetto un po' di piu' (+2,00 invece di +1,40).

**Attenzione, stesso difetto**: la copertura nuova NON risolve il difetto del riquadro 7. Provato sulla
stessa partita: dopo il quarto gol la chiave della posizione passa all'Over 4,5, la sua chiusura viene
bloccata allo stesso modo (stessi 37+28 avvisi «flusso fermo»); firmando la proposta equivalente
(19:25:33, «chiudendo ora -2,14») la chiusura non parte comunque, risultato **-14,17 EUR** invece di -2,14:
**danno 12,03 EUR**, leggermente piu' alto di oggi (11,46 EUR) perche' la posizione coperta e' piu' grande.

**Nessuna opinione sulla strategia**: questi sono solo i numeri che risultano dai dati della registrazione,
dalla formula scritta nel piano e dal replay con l'interruttore acceso. **Fonte**:
`AUDIT_2026-09-29/INDAGINE_MIKE_MERCATO_DECISO.md`, domanda 4.

---

## Punti non chiariti / dati non rilevati

1. **Perche' due tentativi di banca in gioco nello scenario reale** (schema 2, riquadro 2) invece di uno
   solo come nello scenario del guasto (schema 4): il replay e il referto confermano i fatti (id 3 scaduto,
   id 4 annullato da Mike e non confermato da Betfair) ma non la riga di codice esatta che ha deciso il
   secondo tentativo. Per rispondere servirebbe leggere `engine.py:3001-3060`, non fatto qui (compito di
   sola lettura).
2. **Quote esatte di mercato nell'istante preciso di ogni gol**: la registrazione (`35760084.jsonl`, 49
   MB) riporta un book ogni pochi decimi di secondo, ma il mercato spesso e' sospeso proprio nei secondi
   del gol; i numeri usati sopra sono i piu' vicini disponibili PRIMA e DOPO ogni gol (scarto dichiarato
   in ogni riquadro, fra 20 e 90 secondi). Non e' stato possibile avere il prezzo esatto al secondo del
   gol.
3. **Perche' la seconda banca in gioco (id 4) non e' mai stata confermata da Betfair**: il referto segna
   «annullo NON confermato: la riga resta in riconciliazione» piu' volte nel log tecnico; il motivo
   tecnico esatto (perche' Betfair non ha confermato) non e' stato indagato.
4. **In quale finestra di minuti cadono i "motivo x223"/"x159" (-2,34/-2,38 EUR)**: spiegato IL MECCANISMO
   (sono letture per giro, non proposte ufficiali), non individuato IL MINUTO esatto: servirebbe leggere le
   righe dello scanner con il loro orario, non catturate da questa sonda.
5. **RISOLTO in questo giro di correzioni** (non piu' un punto aperto): perche' il mercato Under 3,5 smette
   di aggiornarsi dalle 19:25:24/25 - Betfair lo chiude e lo regola, non e' un guasto (vedi riquadro 4 e 7,
   fonte `AUDIT_2026-09-29/INDAGINE_MIKE_MERCATO_DECISO.md`).
6. **Se lo scanner di PRODUZIONE (dal vivo, non nel replay) scrive davvero `CLOSED` nel blocco del mercato
   deciso**: dedotto dal codice (`safe_strategy/service.py` `_apply_opp_book` 1279-1286), non letto nessun
   dato di produzione (il DB e' vietato). Se succede, in produzione il difetto del riquadro 7 potrebbe
   presentarsi IN MODO DIVERSO (Mike legge "3,5 chiuso" come "partita finita" e resta cieco sull'Over 4,5
   finche' anche quello non chiude): da controllare in paper al prossimo 4-0 con copertura.
7. **La correzione proposta per il difetto (riquadro 7) non e' stata applicata ne' certificata**: e' stata
   solo provata per pochi minuti in un worktree separato e poi ripristinata; decide l'utente se applicarla.

---

## Come sono stati presi i numeri

- **Il riquadro 7 (DIFETTO TROVATO)**, la spiegazione corretta del riquadro 4 (perche' Betfair chiude e
  regola le linee, il conto giusto dopo il quarto gol, perche' le proposte si fermano dalle 19:41:47), e i
  numeri della copertura nuova con l'interruttore acceso vengono TUTTI da un'indagine dedicata fatta da
  un'altra sessione il 29/09: `AUDIT_2026-09-29/INDAGINE_MIKE_MERCATO_DECISO.md`. Questa scheda ne riporta
  i fatti e li cita; non li ha ricavati da sola. L'indagine ha letto `marketDefinition.status` dalla
  registrazione grezza dello STREAM (`_live_raw/35760084/35760084.raw.jsonl`, diversa dal file
  "ridotto" `35760084.jsonl` usato altrove in questa scheda, che non porta la chiusura vera dei mercati) e
  ha usato una sonda propria che avvolge `engine.decide`, `feed.flusso_esito` e `service._run_event` in
  sola lettura, con la firma vera di produzione (`service._request_approva_uscita`) per provare cosa
  succede firmando una proposta prima e dopo il quarto gol.
- Il referto corrente del coordinatore (`AUDIT_2026-09-29/replay/mike_tutti_P4_4_P5_1.txt`, scenario
  `[base]`) da' i totali (5 ordini, 2 abbinamenti, -14,00 EUR, 17 proposte/15 decadute) ma non il
  dettaglio ordine per ordine. **Verificato**: gli stessi numeri chiave erano gia' nel referto usato nella
  prima stesura di questo lavoro (`mike_tutti_P2_P4_2.txt`); coincidono; le uniche differenze sono di
  contorno (un avviso in piu' legato al tempo reale di esecuzione, durata del replay diversa).
- Per il dettaglio (minuto, prezzo, importo ed esito di OGNI ordine, e ogni voce dell'attivita' del
  servizio, comprese le date/ore reali con `proposed_at`) e' stata scritta una sonda di sola lettura nella
  cartella temporanea di lavoro (MAI nel repo): richiama **lo stesso punto d'ingresso di produzione** della
  certificazione (`Betfair.mike.tools.replay_registrazioni.certifica_scenario`, dentro
  `Betfair.stream.backtest.trasporto.contesto("mike", "canale")`, esattamente come fa
  `python -m Betfair.stream.backtest.certifica`), senza reimplementare nessuna logica: si limita a
  catturare l'istanza di `strategia` che la produzione crea, per leggere `strategia.db.trades` (le righe
  `mike_trades` vere) e `strategia.db.attivita` (il diario del servizio, `mike_activity`), che il referto
  aggregato riassume ma non elenca. La sonda e' stata rilanciata due volte: scenario `base` (la partita
  reale) e scenario `lettura-dati-ko` (il guasto, schema 4), entrambe con l'ambiente neutro richiesto
  (SUPABASE_URL finto, tutti gli interruttori canale a 0, nessuna chiamata vera a Betfair o al database).
  Tempo di esecuzione: circa 1 minuto ciascuna (in-process, piu' veloce del comando a riga di comando
  perche' non passa dal multiprocesso del banco).
- Le quote di mercato intorno a ogni gol, e la verifica dell'ultimo aggiornamento del mercato Under 3,5,
  vengono dalla registrazione grezza (`_live_raw/35760084/35760084.jsonl`, 49 MB, un book per mercato a
  ogni aggiornamento, letto riga per riga filtrando sui due market_id di Mike) e dai minuti/punteggio di
  `_live_raw/35760084/35760084.scores.jsonl`.
- Gli orari italiani si ottengono aggiungendo 2 ore (ora legale) a ogni orario UTC della registrazione.
- Il comando ufficiale indicato nel compito (`python -m Betfair.stream.backtest.certifica mike 35760084
  --scenari base --trasporto canale --worker 1 --data-dir ...`) NON e' stato rilanciato: il referto dello
  scenario base gia' disponibile coincide numero per numero con quanto trovato dalla sonda, quindi non
  serviva ripeterlo.
