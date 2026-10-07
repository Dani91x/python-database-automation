# SPECIFICA — Scalper calcio, modalita' nuova «MEDIA UNDER» (05/10/2026)

Documento per chi COSTRUISCE la modalita'. Chi verifica e integra e' il coordinatore del repo
(sessione locale dell'utente). Le frasi fra «» sono parole dell'utente: non si reinterpretano.

## 0. Prima di toccare qualunque file

Leggi, in quest'ordine: `CLAUDE.md` (radice), `PROCESSO_STANDARD_BOT.md` (tutto; §6 copertura
obbligatoria del banco, §7 catalogo dei 35 errori gia' visti: sono i criteri di accettazione),
`Betfair/stream/scalper/BIBBIA_SCALPER_CALCIO.md`, le sezioni `## 2026-10-04` e `## 2026-10-05` di
`CRONOSTORIA.md`, `AUDIT_2026-10-04/CERTIFICAZIONE_SCALPER_CALCIO.md` (com'e' fatto oggi lo scalper
dopo le correzioni sui minimi, sui residui e sui soldi veri), `AUDIT_2026-10-04/MINIMI_PUNTE_E_MIKE_CHIUSURA.md`
(la regola dei minimi), `SCHEMI_BOT/REGOLE_DI_CHIAREZZA.md` (testi per un non tecnico).

Cosa NON hai nel tuo ambiente: le registrazioni di mercato (`_live_raw/`, non sono nel repo), il
database, il `.env`, l'app desktop. Quindi: NON puoi lanciare i replay di certificazione e NON devi
provarci con dati finti. Tu consegni codice, test unitari e scenari/controlli del banco PRONTI; i replay
li lancia il coordinatore. Scrivi nel referto che cosa non hai potuto eseguire.

## 1. Obiettivo (una frase)

Una modalita' in piu' dello Scalper calcio, spenta di serie, che l'utente accende a mano su UNA partita
e su UN mercato (Under 2,5 oppure Under 3,5): in pre-match punta l'Under, appoggia subito la banca che
chiude in profitto, e se la quota gli va contro media la posizione fino a 5 volte; in live NON opera:
lascia la banca appoggiata e SEGNALA all'utente gli importi esatti per chiudere.

## 2. Perimetro: si AGGIUNGE, non si cambia

- Nessuna modifica al comportamento di cio' che esiste: maker (`scalper_bot.ScalperStrategy`), Sniper
  (`sniper_bot.SniperStrategy`), Theta (`theta_bot.ThetaStrategy`), auto-mode (`auto_mode.py`),
  supervisore (`scalper_service.py`). Con la modalita' spenta il referto dei replay di oggi deve restare
  IDENTICO riga per riga (lo verifica il coordinatore sui 15 scenari certificati).
- La modalita' vive in un file suo (precedenti da imitare: `sniper_bot.py`, `theta_bot.py`) ed e' agganciata
  alla sessione (`scalper_session.run_session`, dove nascono `sniper` e `theta`, righe ~1130-1460) con un
  parametro esplicito. Una sessione «media under» NON arma il maker ne' lo Sniper (precedente:
  `theta_only`; attenzione: `auto_mode.sniper_mode_acceso` considera lo Sniper ACCESO se la chiave manca).
- L'AUTO-MODE NON DEVE MAI armare questa modalita': «questo bot non sara' automatico, scelgo io le partite».
- File vietati: `Betfair/stream/trading/minimi_it.py`, `Betfair/stream/backtest/minimi_banco.py`,
  `Betfair/stream/live_order_build.py`, `Betfair/stream/trading/submin.py`, `Betfair/stream/motore_ordini.py`,
  `Betfair/mike/**`, `Betfair/safe_strategy/**`, `Betfair/omega/**`, i bot tennis. Se ti serve una modifica
  li': patch a parte in `AUDIT_2026-10-05/patch/` e la descrivi nel referto.
- Migrazioni SQL: solo come file in `migrations/` (le applica l'utente). Preferisci NON averne: i
  parametri stanno gia' in `scalper_control.params`, lo stato in `stats`.

## 3. Comportamento (decisioni dell'utente)

Testo dell'utente: «il bot entra pre-match sui mercati BACK UNDER 2.5 O UNDER 3.5 se c'e' abbastanza
liquidita' come ora (solo su questi due mercati), inizia a costruire la posizione, SE PUO' CHIUDERE IN
GREEN UP APPOGGIANDO IL LAY EQUIVALENTE, LO FA. Poi ricomincia il ciclo, se il prezzo va contro (PRE MATCH
di almeno 2 tick) media la posizione con l'importo necessario PER CHIUDERE TUTTO SPALMANDO IL PROFITTO A 2
TICK, se il prezzo continua ad andare contro va avanti a mediare per un massimo di 5 volte. Se raggiunge
il massimo dei tentativi, si ferma e aspetta che la partita passi in live, APPOGGIANDO GIA' L'ESATTO
IMPORTO IN LAY IN MODALITA' "PERSIST" PER CHIUDERE SEMPRE A 2 TICK IN PROFIT, SPALMANDO IL PROFITTO
UNIFORMEMENTE, QUINDI I CALCOLI DEL LAY VANNO FATTI IN BASE A QUANTI CICLI DI RIENTRO HA FATTO IL BOT.»

Macchina a stati (per la selezione Under scelta):

1. `FERMO` -> `INGRESSO` (solo pre-match). Condizioni: mercato aperto e non in-play; quota di punta
   dentro l'intervallo configurato; liquidita' e flusso come i controlli di oggi dello scalper (stessi
   concetti di `min_size`, `min_flow`, `max_spread_ticks`: parametri PROPRI della modalita' con gli stessi
   valori di serie); fuori dalla finestra «stop nuovi ingressi prima del fischio». Azione: PUNTA lo stake
   base alla miglior quota disponibile.
2. `IN POSIZIONE`. Appena la punta e' abbinata (anche in parte): appoggia la BANCA DI CHIUSURA sulla
   stessa selezione, a `quota dell'ultimo ingresso - N tick di chiusura`, per l'importo che rende uguale
   il profitto sui due esiti (§4), con persistenza PERSIST. Una sola banca di chiusura viva per volta.
   **07/10**: la banca puo' essere fatta di PIU' ordini alla STESSA quota (la banca spostata col
   replace + le integrazioni, §14); la regola diventa: la somma delle banche vive non supera MAI la
   posizione da coprire (al centesimo) e mai due banche vive a quote diverse oltre l'istante dello
   spostamento.
3. `CHIUSA IN PROFITTO`: la banca e' abbinata per intero e la posizione e' pari -> ciclo chiuso, si
   registra, si torna a `FERMO` e «ricomincia il ciclo» (nuovo primo ingresso con lo stake base), finche'
   si e' in pre-match e dentro la finestra degli ingressi.
4. `RIENTRO` (solo pre-match): se la miglior quota di punta e' salita di almeno `N tick di rientro`
   rispetto al prezzo dell'ULTIMO ingresso e i rientri fatti sono meno del massimo.
   **Dal 07/10/2026 (ordine dell'utente, sostituisce la regola di prima «annullo + nuovo
   piazzamento, mai `replaceOrders`»)**. Testo dell'utente: «la banca deve aspettare che si abbini il
   rientro prima di fare qualsiasi cosa. Però non voglio rischiare doppi ordini di banca, quindi
   (...) facciamo in modo di MODIFICARE l'ordine banca e spostarlo a seconda dei rientri
   effettivamente abbinati»; «voglio una soluzione definitiva per questa banca». La regola nuova
   (dettagli e casi limite al §14):
   (a) ricalcola sulla posizione VERA abbinata (una banca abbinata in parte conta) e PUNTA subito
   l'importo di rientro (§4) al miglior prezzo, con la banca viva INTATTA (nessun annullo, nessun
   ripiazzo); la quota si ricontrolla sul book corrente;
   (b) finche' la punta di rientro e' viva (non abbinata o abbinata in parte) la banca NON si tocca;
   allo scadere del TTL il resto non abbinato della punta si annulla, come prima;
   (c) a punta TERMINATA con un abbinato, la banca si SPOSTA una volta sulla posizione vera: `L` =
   banca esatta alla quota `c` (quota dell'ultimo rientro abbinato - N tick, o sotto la media);
   `R` = resto vivo della banca; PRIMA l'integrazione `L - R` alla quota `c` (PERSIST), POI
   `replaceOrders` del resto `R` alla quota `c` (Betfair non aumenta l'importo di un ordine). In
   nessun istante la somma delle banche vive supera `L`.
   Il difetto che la regola chiude (dati veri, richiesta 9a30d0a2, evento 35768297; banco,
   35797769): se fra l'annullo e la punta la quota tornava giu', il rientro non partiva e la banca si
   rimetteva IDENTICA in fondo alla coda (ping-pong, ~60 s senza banca in gioco).
5. `MASSIMO RAGGIUNTO`: dopo l'ultimo rientro consentito non punta piu'. Resta appoggiata la banca di
   chiusura esatta, PERSIST, calcolata su tutti i rientri fatti. Lo dice una volta (attivita' critica).
6. `LIVE` (dal passaggio in-play): la modalita' NON piazza, NON annulla e NON riprezza niente. La banca
   PERSIST gia' appoggiata resta dov'e'. Testo dell'utente: «no gestisco io il live se succede qualcosa,
   il bot deve solo segnalarmi L'ESATTO IMPORTO DA PIAZZARE PER CHIUDERE IN BASE AL NUMERO DI TICK DI
   PROFIT IMPOSTATO [...] da adattare all'importo reale in quel momento e alla quota media». Vedi §6.
7. Fine: posizione pari (banca abbinata o chiusura fatta dall'utente) oppure mercato regolato -> si
   registra l'esito del ciclo e la sessione chiude come le altre sessioni dello scalper.

Regole fisse:
- La chiusura forzata prima del fischio dello scalper (`flatten_before_s`) NON vale per questa modalita':
  la posizione deve arrivare al live con la sua banca PERSIST.
- Il rientro si misura dall'ultimo INGRESSO abbinato, non dalla quota media.
- «Contro» = la quota dell'Under SALE.
- Se una punta d'ingresso o di rientro non si abbina entro il suo tempo: si annulla, si aspetta che sia
  morta, si rivaluta dal book corrente. Mai inseguire, mai due punte vive insieme.
- I tre controlli «rumore o informazione» discussi dall'utente in chat (mercati collegati, finestra delle
  formazioni, persistenza) e il filtro del prezzo giusto da modello NON fanno parte di questa consegna:
  non costruirli. Se vuoi predisporre il punto d'aggancio, un parametro spento e nient'altro.

## 4. Formule (sono il cuore: ogni numero qui sotto diventa un test)

Posizione VERA sulla selezione, dagli ordini abbinati (punte `b_i @ p_i`, banche `l_j @ r_j`):

    se_vince = somma(b_i * (p_i - 1)) - somma(l_j * (r_j - 1))
    se_perde = somma(l_j) - somma(b_i)

Senza banche abbinate: `S = somma(b_i)`, `P = somma(b_i * (p_i - 1))`, `se_vince = P`, `se_perde = -S`,
quota media = `1 + P / S`.

- Banca di chiusura alla quota `c`:  `L = (se_vince - se_perde) / c`  (senza banche: `(S + P) / c`).
  Profitto lordo uguale sui due esiti: `se_perde + L`. Netto: lordo x (1 - commissione) se positivo.
- Importo di RIENTRO alla quota `q`, per chiudere a `c = q - N tick` con profitto lordo `T`:

      X = (c * (T - se_perde) - (se_vince - se_perde)) / (q - c)

  (senza banche abbinate e' la formula dell'utente: `X = (c * (S + T) - S - P) / (q - c)`).
- `T` lordo = obiettivo netto / (1 - commissione).
- Obiettivo: parametro in EURO NETTI (es. 0,30). Valore speciale «automatico» = il profitto lordo che
  danno gli N tick sul PRIMO ingresso del ciclo, tenuto uguale nei rientri.
- Tick: la scala VERA di Betfair (0,01 fino a 2,00; 0,02 fino a 3,00; 0,05 fino a 4,00; ...). Usa gli
  aiuti che il repo ha gia' (`live_order_build.round_to_tick`, `ticks_away`, `flumine.utils.price_ticks_away`):
  non riscrivere la scala.
- MINIMI Betfair.it (regola dell'utente, fonte UNICA `Betfair/stream/trading/minimi_it.importo_piazzabile`,
  mai numeri copiati): una PUNTA da 1,00 EUR in su parte solo a multipli di 0,50, arrotondata per DIFETTO;
  la BANCA va al centesimo, minimo diretto 1,00. Quindi: `X` si arrotonda per difetto al multiplo di 0,50,
  e la banca si RICALCOLA al centesimo su cio' che e' davvero abbinato. Il profitto reale puo' essere di
  qualche centesimo sotto l'obiettivo: va mostrato quello reale, non l'obiettivo.

Vettori di prova (calcolati, commissione 5%):

A) base 10,00 @1,50, obiettivo automatico, N=2, punte a multipli di 0,50

| passo | quota | X esatto | punta | totale puntato | quota media | banca di chiusura | lordo |
|---|---|---|---|---|---|---|---|
| ingresso | 1,50 | - | 10,00 | 10,00 | 1,5000 | 10,14 @1,48 | 0,1351 |
| rientro 1 | 1,52 | 10,14 | 10,00 | 20,00 | 1,5100 | 20,13 @1,50 | 0,1333 |
| rientro 2 | 1,54 | 20,27 | 20,00 | 40,00 | 1,5250 | 40,13 @1,52 | 0,1316 |
| rientro 3 | 1,56 | 40,41 | 40,00 | 80,00 | 1,5425 | 80,13 @1,54 | 0,1299 |
| rientro 4 | 1,58 | 80,54 | 80,50 | 160,50 | 1,5613 | 160,63 @1,56 | 0,1346 |
| rientro 5 | 1,60 | 160,68 | 160,50 | 321,00 | 1,5807 | 321,13 @1,58 | 0,1329 |

B) esempio dell'utente: base 10,00 @1,35, obiettivo netto 0,30, N=2, SENZA arrotondamento:
rientri 21,32 @1,37 / 31,63 @1,39 / 63,27 @1,41 (l'utente: 21,30 / 31,70 / 63,50), totale puntato 126,22,
quota media 1,3935, banca 126,54 @1,39, netto 0,3000.

C) come B con le punte a multipli di 0,50: 21,00 / 31,50 / 62,50 / 125,50 / 251,00; totale 501,50; banca
501,81 @1,43; netto fra 0,294 e 0,299.

D) segnalazione in live, esempio dell'utente (commissione 0): punta 10,00 @1,32, quota attuale 1,67.
Chiudere adesso: banca 7,90 @1,67 -> -2,10. Per chiudere a 1,65 (2 tick sotto): pareggio -> puntare
165,00 (rischio totale 175,00, nuova media 1,6500); +0,30 -> 189,75 (199,75; 1,6525); +1,00 -> 247,50
(257,50; 1,6564).

La crescita e' quasi un raddoppio a ogni rientro: e' voluta e l'utente la conosce. NON aggiungere di tua
iniziativa tetti, riduzioni o stop: i limiti sono i parametri del §5.

## 5. Parametri (tutti modificabili dall'utente dalla UI: «devo poter personalizzare io i filtri»)

| parametro (nome proposto) | di serie | origine |
|---|---|---|
| `media_mode` | false | interruttore della modalita' |
| `media_mercato` | nessuno: obbligatorio all'avvio (`OVER_UNDER_25` o `OVER_UNDER_35`) | utente: «scelgo io quale» |
| `media_stake` (stake base, EUR) | 10,00 | esempio dell'utente |
| `media_obiettivo` (EUR netti; 0 o assente = automatico) | automatico | proposta, da confermare all'utente |
| `media_tick_chiusura` | 2 | utente |
| `media_tick_rientro` | 2 | utente |
| `media_max_rientri` | 5 | utente |
| `media_rischio_max` (EUR totali puntati; 0 = spento) | 0 | dal riepilogo dell'utente: «blocco dei rientri quando lo stake supera il rischio massimo, con log dell'evento» |
| `media_quota_min` / `media_quota_max` | 1,20 / 4,00 | utente (per l'Under 3,5; stessi valori di serie per l'Under 2,5) |
| `media_min_size`, `media_min_flow`, `media_max_spread_ticks` | come lo scalper oggi (300 / 10 / 2) | utente: «liquidita' come ora» |
| `media_stop_ingressi_s` (stop nuovi ingressi e rientri prima del fischio) | 420 | come `entry_stop_before_s` di oggi |
| `media_ttl_punta_ms` (attesa della punta prima dell'annullo) | scegli e motiva | - |
| `media_obiettivi_live` (lista per la segnalazione, EUR) | [0, 0,30, 1,00] | esempio dell'utente |
| commissione | quella gia' usata dalla sessione | - |

I nomi vanno aggiunti alla lista dei parametri ammessi dalla UI (`scalper_session.UI_PARAM_WHITELIST`).
Un parametro mancante o non valido = la sessione NON parte e dice perche' (mai un valore inventato).

## 6. In live: solo segnalazione

Dal passaggio in-play, e in pre-match dopo il massimo dei rientri, la modalita' pubblica (stats della
sessione, lette dalla UI; e una attivita' a ogni cambio rilevante: gol/sospensione, riapertura, banca
annullata da Betfair, banca abbinata) un riquadro «chiusura» ricalcolato a ogni book con:

- posizione reale: totale puntato, quota media, banche abbinate, `se_vince` / `se_perde`;
- banca appoggiata: importo, quota, viva / abbinata / caduta (se Betfair l'ha annullata alla sospensione
  va detto in chiaro: «la banca non e' piu' a mercato»);
- «chiudere adesso»: banca di `L` EUR alla quota di banca attuale e il P&L che ne esce;
- per ogni obiettivo della lista (pareggio, +0,30, +1,00): quanto PUNTARE alla quota attuale per chiudere
  `N tick` sotto, a multiplo di 0,50 (e l'importo esatto fra parentesi), il rischio totale che ne
  risulta, la nuova quota media e la banca da appoggiare dopo.

«Importo reale»: i numeri devono riflettere la posizione VERA sul conto per quella selezione, compresi
gli ordini che l'utente mette a mano dal sito o dal terminale. Studia come il repo vede gia' gli ordini
manuali (specchio degli ordini del conto, `reconcile_worker`, righe `role='utente'`): se la sessione
dello scalper non puo' vederli, NON fingere: il riquadro dichiara «solo ordini del bot» e tu lo scrivi nel
referto come limite, con la proposta per chiuderlo.

Nessun ordine in live, mai: nemmeno «di sicurezza». Se la sessione muore in live vale quello che c'e'
gia' (`scalper_service.marca_orfana`: avviso critico, li chiude l'utente).

## 7. Ordini: regole che valgono per tutti i bot del repo

- Soldi veri solo col pulsante dell'utente: stessa catena dello scalper dopo il 04/10
  (`scalper_session.non_partire_senza_soldi_veri`, `freno_soldi_veri`, `strategy.freno_live` sulle
  aperture). Prova (paper) = stesso identico percorso senza ordini veri.
- Consapevolezza dell'ordine: la modalita' sa sempre se ogni suo ordine e' vivo, abbinato (quanto),
  annullato, rifiutato, ignoto. Esito ignoto = non si ripiazza. Mai un ordine seguito che non esiste.
- Rifiuto per taglia (`INVALID_BET_SIZE`): freno, mai un ripiazzo a ogni giro (vedi
  `scalper_bot._leggi_rifiuti_taglia`).
- Residuo non piazzabile (sotto 0,50): si dichiara UNA volta con la proposta e resta ricordato; lo chiude
  l'utente (`scalper_bot._ricorda_residuo`).
- Riavvio della sessione a posizione aperta: la posizione e gli ordini vivi si RICOSTRUISCONO dagli
  ordini veri (mai da memoria vuota): rientri fatti, ultimo ingresso, banca viva. Se non e' ricostruibile:
  nessun ordine, avviso critico.
- Mai cieco con soldi a mercato: flusso dei prezzi fermo o mercato sospeso = nessun ordine nuovo, stato
  dichiarato.

## 8. Interfaccia (frontend)

`frontend/src/components/live/ScalperPanel.tsx` e `frontend/src/lib/scalper.ts` (dove vivono oggi
`sniper_mode` e `theta_mode`). Servono: l'interruttore della modalita' con la scelta del mercato (Under 2,5
/ Under 3,5), i parametri del §5, lo stato del ciclo (rientri fatti su massimo, totale puntato, quota
media, banca appoggiata), il riquadro «chiusura» del §6. Testi in italiano chiari per un non tecnico,
nessuna etichetta ambigua, ogni cifra dice da dove viene. Modifiche chirurgiche: lo stile e' quello che
c'e'. `npx vitest run` verde e `npx tsc -p tsconfig.app.json --noEmit` a 0 errori (mai `any` o
`@ts-ignore` per zittire).

## 9. Test, banco, falsificazione

- Test unitari con gli oggetti VERI (strategia flumine vera, ordini flumine veri, la regola dei minimi
  del banco montata come nei test `test_scalper_residui_e_soldi_veri_2026_10_04.py`). I finti hanno chiavi e
  tipi identici al vero.
- Ogni vettore del §4 e' un test. In piu', almeno: banca abbinata in parte prima di un rientro; punta di
  rientro non abbinata; rientro bloccato dal massimo e dal rischio massimo (con la riga di log); nessun
  rientro in live; banca PERSIST che sopravvive al passaggio in-play e punta LAPSE che cade; nessuna
  chiusura forzata prima del fischio; mai due chiusure vive insieme; riavvio a posizione aperta; soldi
  veri fermati senza «Ordini reali»; l'auto-mode non arma la modalita'; modalita' spenta = nessun effetto.
- FALSIFICAZIONE obbligatoria: per ogni test nuovo una mutazione del codice che lo fa diventare rosso;
  tabella mutazione -> test rossi nel referto; ripristino con `git checkout`, mai a memoria.
- Banco di certificazione: il modulo nuovo va registrato (`Betfair/stream/backtest/registro_bot.py`,
  `_MODULI_SCALPER_CALCIO`: il test di contratto rifiuta un modulo di produzione non registrato). Aggiungi
  gli scenari in `Betfair/stream/scalper/tools/replay_registrazioni.py` (almeno: `media-under` in soldi
  veri simulati, `media-under-paper`, uno per mercato) e i controlli di condotta in
  `Betfair/stream/scalper/certificazione.py` (almeno: nessuna punta fuori dai due mercati; mai piu' rientri
  del massimo; ogni rientro ad almeno N tick dall'ultimo ingresso; importo del rientro = formula; una sola
  banca di chiusura viva; banca = formula sulla posizione vera; nessun ordine in live; parita' paper/live).
  Non potendo lanciarli, falli almeno caricare e girare a vuoto nei test (scenario riconosciuto,
  controlli elencati).
- Suite: `python -m pytest Betfair/ -q -p no:cacheprovider` (da te molti test del banco risultano
  «skipped» perche' mancano le registrazioni: riporta i numeri e dillo).

## 10. Consegna

- Ramo `feature/scalper-media-under` da `master`, pull request verso `master`. Niente push su `master`.
  Commit con percorsi espliciti: MAI `git add -A` (nel repo ci sono file enormi non tracciati).
- Messaggi di commit `tipo: descrizione` (feat, fix, test, docs), senza righe di attribuzione.
- Codice ASCII-only, commenti in italiano, annotazioni di tipo sulle firme.
- Referto `AUDIT_2026-10-05/SCALPER_MEDIA_UNDER.md`: cosa hai aggiunto (file:riga), mappa di ogni stato e
  di ogni condizione, tabella delle mutazioni, numeri delle suite, elenco di cio' che NON hai potuto
  verificare (replay, UI a schermo, ordini manuali, DB), e le scelte che hai dovuto fare dove questa
  specifica non decideva.
- Aggiorna `Betfair/stream/scalper/BIBBIA_SCALPER_CALCIO.md` con una sezione sulla modalita'.

## 11. Quando fermarti e chiedere

Se per rispettare questa specifica devi cambiare il comportamento di una modalita' esistente, toccare un
file vietato, aggiungere una regola di strategia non scritta qui (un tetto, uno stop, un filtro), o
scegliere fra due letture diverse di una frase dell'utente: NON decidere. Scrivi il caso con un esempio
in euro nel referto e nella pull request e lascia quel punto non fatto.

## 12. Per chi verifica (coordinatore)

Studio precedente sulla stessa idea: backtest del 16/07/2026 su 26 partite (memoria
`project_scalper_avgdown_backtest_2026-07-16`, rapporto locale `SCALPER_AVGDOWN_REPORT_2026-07-16.md`, non
tracciato): mediazione solo pre-match negativa in media; mediazione pre-match PORTATA oltre il fischio
sull'Under positiva in tutte le varianti (14 partite, fill ottimistici). La modalita' passa dal processo
intero: replay su registrazioni vere -> prova -> soldi veri solo se la prova conferma.

## 13. 07/10/2026 - <<ATTIVA ADESSO>> (DIVERGENZA VOLUTA, ordine dell'utente)

Cambio di strategia CHIESTO DALL'UTENTE il 07/10 (non un'iniziativa di chi costruisce). Testo dell'utente:
<<1. Voglio poter attivare il bot in un momento specifico della partita (sia pre-match che live). 2. Quando
lo attivo il bot piazza immediatamente al miglior prezzo disponibile la prima puntata back e poi opera
normalmente come progettato. 3. In questo modo posso attivarlo io in determinati periodi specifici, e andare
a "ritroso" sulle condizioni che c'erano in quel momento, cosi' da ottimizzarlo una volta per tutte.>>;
<<in gioco opera come pre match, e' lo stesso identico bot>>; <<una volta che il bot ha piazzato, deve
gestire la posizione, indipendentemente dai filtri>>; <<Anche nell'app vera, voglio un lavoro completo>>.
REGOLA DEFINITIVA sui nuovi cicli (07/10, confermata punto per punto, sostituisce la correzione del
<<riavviare cliccando nuovamente>>):

1. Avvio SOLO col clic su <<Attiva adesso>> (pre-match o in gioco): prima punta immediata al miglior prezzo
   di punta (lo stake base, LAPSE), poi gestione della posizione come progettato SENZA i filtri d'ingresso
   (quota, liquidita', flusso, spread, finestra di stop prima del fischio). Restano tetti e protezioni:
   massimo dei rientri, rischio massimo, mercato aperto (nessun ordine a mercato sospeso o chiuso), prezzi
   vivi (regola 11: flusso interrotto = nessun ordine), minimi di Betfair, freno dei soldi veri, stop/freno
   della sessione, attesa dopo un rifiuto di Betfair, una sola punta e una sola banca vive.
2. Ciclo chiuso PRE-MATCH (avviato col pulsante): la modalita' RIENTRA DA SOLA con un nuovo ciclo. Di serie
   SENZA filtri (nuova prima punta subito al miglior prezzo, anche dentro la finestra di stop prima del
   fischio). Parametro nuovo del pulsante `media_rientro_auto_filtri` (booleano, di serie False): se True il
   nuovo ciclo pre-match entra solo quando i filtri d'ingresso progettati lo permettono.
3. Ciclo chiuso IN GIOCO: nessun rientro da solo; ATTESA DEL CLIC (stato `ATTESA_CLIC`, detto in UI); un
   nuovo clic riparte con una prima punta immediata.
4. Ciclo aperto pre-match e ancora aperto al fischio: in gioco la gestione continua come progettato (banca,
   rientri, massimo, rischio massimo); chiuso in gioco -> punto 3.
5. Tutto questo vale SOLO per l'avvio col pulsante. La modalita' accesa nel modo di sempre (senza pulsante)
   NON cambia in nulla (par.3, par.6: in gioco nessun ordine, solo segnalazione).

### 13.1 Il comando
- Il clic e' un comando `media_attiva_adesso = {"id": <unico>, "ts": <istante del clic>}` nei params della
  riga `scalper_control`, la stessa strada dei parametri: sessione accesa = RPC
  `scalper_media_attiva_adesso` (`migrations/media_under_attiva_adesso_2026-10-07.sql`); sessione ferma = la
  RPC di sempre `scalper_activate` coi params della modalita' + `media_a_clic: true` (sessione armata dal
  pulsante: non entra mai da sola) + il comando.
- La sessione lo legge al battito (5 s) o all'avvio (`scalper_session.consegna_comando_media`). Un id gia'
  consumato non fa nulla. Un id nuovo e' CONSUMATO subito e mai accodato: scaduto (oltre 120 s dal clic),
  prezzi fermi (sorveglianza del flusso `vivo = False`) o mercato sospeso all'ultimo prezzo visto =
  rifiutato col motivo; valido = l'id si REGISTRA nelle stats della riga e solo a scrittura riuscita la
  modalita' lo esegue al prossimo prezzo (un riavvio non riesegue mai lo stesso clic: l'id consumato si
  rilegge dalle stats della sessione di prima). Al prezzo: posizione aperta, punta o banca vive, sessione
  bloccata/in ripresa, mercato sospeso/chiuso, stop della sessione, nessun prezzo di punta, attesa dopo un
  rifiuto = rifiutato col motivo (attivita' `media_comando_rifiutato`, stats `media_comando`). In soldi veri
  la punta del clic passa dal freno dei soldi veri come ogni apertura.
- Stats nuove: `media_comando` (id, esito ricevuto/eseguito/rifiutato, motivo, prezzo, importo, in gioco),
  `media_a_clic`, `media_origine_ciclo` (clic / rientro_automatico), `media_in_gioco`,
  `media_rientro_auto_filtri`. Attivita' nuove: `media_comando_eseguito`, `media_comando_rifiutato`,
  `media_rientro_automatico`, `media_attesa_clic`; `media_ingresso` porta `origine` per i cicli del pulsante.

### 13.2 Divergenze dalla spec di prima (scritte per l'utente)
- par.3.1 <<solo pre-match>> e filtri d'ingresso: per il clic e per il rientro automatico senza filtri non
  valgono (punti 1-2).
- par.3.4 rientro <<solo pre-match>> e par.5 `media_stop_ingressi_s` <<stop nuovi ingressi E RIENTRI>>: per
  un ciclo avviato col pulsante i rientri si fanno anche dentro la finestra di stop e in gioco.
- par.3.6 e par.6 <<in live nessun ordine>>: per un ciclo avviato col pulsante in gioco si opera come
  pre-match (il riquadro <<chiusura>> resta pubblicato, informativo).
- Banco: controlli M12-M18 (registro separato) per le sessioni <<a clic>>; M7 (nessun ordine in gioco) e la
  finestra di M9 non si applicano agli ordini dei cicli avviati col pulsante; M6 e M11 valgono anche in gioco
  per loro. Con la modalita' di sempre i controlli e i referti restano identici.

## 14. 07/10/2026 - LA BANCA SI SPOSTA, NON SI RIPIAZZA (ordine dell'utente)

Testo dell'utente (07/10 sera): «la strategia resta identica ad ora (...) quello che mi interessa e'
che la banca deve aspettare che si abbini il rientro prima di fare qualsiasi cosa. Pero' non voglio
rischiare doppi ordini di banca, quindi (...) facciamo in modo di MODIFICARE l'ordine banca e
spostarlo a seconda dei rientri effettivamente abbinati»; «voglio una soluzione definitiva per questa
banca».

Strategia IDENTICA: stesse soglie, stessi importi di rientro (`rientro_esatto`, `punta_a_multiplo`),
stessa quota di chiusura (`quota_della_banca`), stesse persistenze (punte LAPSE, banca PERSIST), stesso
TTL della punta, stessi tetti, stessa regola dei resti (giro 3) per la punta d'ingresso. Cambia SOLO
la gestione dell'ordine
di banca (`media_under_bot._allinea_banche`):

1. Condizione di rientro vera -> la punta di rientro parte subito, con la banca viva INTATTA. Si
   aspetta solo che uno spostamento gia' chiesto sia concluso (mai due quote diverse vive mentre una
   punta di rientro e' sul mercato).
2. Finche' la punta di rientro e' viva (non abbinata o abbinata in parte) la banca non si tocca; allo
   scadere del TTL il resto della punta si annulla, come prima. La regola del giro 3 (<<resti non
   abbinati annullati>> quando la banca si appoggia) vale per la punta d'ingresso; per il rientro la
   banca si sposta solo a punta terminata, quindi un resto della punta di rientro vive fino al TTL.
   Prima del 07/10 quel resto si annullava alla prima parte abbinata (perche' la banca si
   riappoggiava li'): sulla 35797769 (`media-under`) una prima versione di questo lavoro che lo
   faceva ancora abbinava 0,30 su 10,00 e chiudeva il ciclo a +0,00 invece di +0,17.
3. A punta terminata (abbinata per intero o resto annullato) con un abbinato, la banca si sposta UNA
   volta, sulla posizione vera, un passo per book e senza mai superare `L`:
   - operazione sulla banca in volo (banca non ancora sul book, riduzione o replace in viaggio,
     sostituto non ancora arrivato) -> si aspetta;
   - `D = L - R` (al centesimo; entro 0,01 = pari, la tolleranza di sempre);
   - `D >= 1,00` -> integrazione `D` alla quota `c` e, nello stesso book, `replaceOrders` delle banche
     vive a un'altra quota (nessun `marketVersion`: la banca PERSIST resta anche dopo un gol);
   - `0 < D < 1,00` (sotto il minimo .it di una banca) -> si RIDUCE una banca viva di `1,00 - D`
     (`cancelOrders` con `sizeReduction`: Betfair permette di ridurre un ordine) cosi' al book dopo
     l'integrazione vale 1,00 al centesimo; se nessuna banca viva regge la riduzione restando >= 1,00
     la parte mancante si DICHIARA una volta (CRITICAL, `media_residuo`) e si sposta solo cio' che c'e'.
     Scelta di chi ha costruito (il brief diceva place-and-trim fra 0,50 e 1,00): il parcheggio del
     place-and-trim (1,00 a una quota lontana) supererebbe per qualche istante la posizione da coprire
     e sarebbe LAPSE nella macchina condivisa (`trading/submin.FlumineSubminOps`); la riduzione della
     banca esistente e' la stessa tecnica di Betfair (ridurre un ordine sotto il minimo) senza nessun
     ordine in piu' e senza mai superare `L`;
   - `D < 0` (caso anomalo: la posizione ne vuole meno) -> prima la riduzione, poi il replace;
   - `D` pari e quota uguale -> niente; quota diversa -> solo il replace.
4. Replace fallito nella parte di PIAZZAMENTO (Betfair: «the cancellations will not be rolled back»):
   la banca vecchia e' morta senza sostituto -> `media_banca_spostamento_fallito` CRITICAL una volta e
   al book dopo si ripiazza SUBITO cio' che manca per arrivare a `L` alla quota nuova. Replace fallito
   nella parte di ANNULLO (la banca vecchia di nuovo sul book alla sua quota) -> si riprova col freno
   dei rifiuti (1, 2, 4, 8, 16, 30 s). Banca abbinata per intero prima dello spostamento -> si
   ricalcola sulla posizione vera.
5. La banca vecchia si abbina per intero mentre la punta di rientro e' viva (ciclo gia' chiuso dalla
   banca) -> si annulla SUBITO il resto della punta; se la punta aveva gia' abbinato qualcosa, quello e'
   una posizione nuova gestita come sempre sulla posizione vera (banca a quota abbinata - tick, o sotto
   la media).
6. In gioco (ciclo avviato col pulsante) la gestione e' identica al pre-match: integrazione e replace
   passano dal bet delay; nessun `marketVersion` sulle banche. Nella modalita' di sempre in gioco la
   modalita' non tocca niente (par.3.6).

Conseguenze dichiarate: dopo `k` spostamenti la banca puo' essere fatta di `k + 1` ordini alla stessa
quota (il replace sposta ogni ordine vivo; `replaceOrders` li manda insieme in una chiamata). Il
riquadro e le stats sommano gli ordini alla quota corrente (`banca.importo`, `banca.abbinato`,
`banca.ordini`).

Banco (`certificazione.py`, famiglia M): M5 al posto di «una sola banca viva» controlla che la somma
delle banche vive non superi mai la posizione da coprire (al centesimo); M6 e M11 accettano piu'
ordini alla stessa quota; M4 giudica il rientro sulla posizione del momento in cui e' nato
(fotografia del banco); nuovi M19 (mai due quote diverse oltre lo spostamento), M20 (nessuna banca
annullata e ripiazzata identica), M21 (posizione aperta senza banca viva oltre `reazione_ms`, misurata
dal banco, con i secondi totali nel referto).
