# Schema 11a - I conti di Mike: posizione, profitto, copertura

Schema: `11a_posizione_e_profitto.html` (tipo dataflow). Seguito in `11b_uscite_calcolate.html`.

**Schede dell'inventario A usate in questo file**: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17,
18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44,
45, 46, 47, 48, 58, 59, 60, 61, 62, 63, 64, 66, 78, 80, 81, 109, 110, 111, 112, 113, 114, 115.
Le altre (49-57, 79, 82-87, 96, 97, 108) sono nel file `11b_uscite_calcolate.schede.md`; quelle
rimandate agli schemi 06 e 08 sono elencate in fondo a quel file e in fondo a questo.

**Come si legge lo schema.** Da sinistra a destra: i dati da cui Mike parte, la posizione che ne
ricava, i valori della partita, l'importo della copertura, l'importo che si puo' davvero piazzare e il
conto finale. Colori dei riquadri: viola = dati di partenza; verde = calcolo; azzurro = profitto
incassabile; rosa = perdita o protezione; grigio = esito finale.

**L'esempio unico.** Tutte le schede usano la stessa partita, cosi' i numeri si possono seguire da
una scheda all'altra:
- prima del fischio Mike punta **10,00 euro sull'Under 3,5 a quota 1,50**;
- in gioco compra la copertura: **2,26 euro sull'Over 4,5 a quota 6,60**;
- commissione Betfair **5%**, applicata sul guadagno netto di ogni mercato.

Tutti i conti qui sotto sono stati rifatti con la calcolatrice e confrontati con il codice
(`Betfair/mike/engine.py`).

---

## 1. Quote e mercato (viola, dati di partenza)

**Cosa fa.** Mike legge, per ogni selezione che tratta, la fotografia del momento: miglior quota a
cui si puo' puntare e quanti euro ci sono, miglior quota a cui si puo' bancare e quanti euro ci sono,
stato del mercato, se la partita e' in gioco, ritardo di piazzamento in secondi.
Le selezioni sono tre: Under 3,5 (mercato Over/Under 3,5), Over 4,5 e Under 4,5 (mercato Over/Under
4,5). Mike punta l'Under 3,5; compra la copertura sull'Over 4,5; nel re-ingresso punta l'Under 4,5.

Prima di usare un numero Mike fa quattro domande:
- La quota c'e', e' un numero vero ed e' sopra 1,00? Se no, la quota non si usa: nessuna azione.
- L'importo e' almeno 0,01 euro? Se no, l'ordine non si fa (mai ordini da 0,00).
- In che stato e' il mercato? Aperto, sospeso, chiuso o sconosciuto.
  - Aperto: si puo' mandare un ordine.
  - Sospeso: adesso no, ma riapre; si aspetta.
  - Chiuso (anche "non attivo"): e' finita; si va al regolamento.
  - Sconosciuto (stato strano o fotografia assente): non si opera, ma non si rinuncia; si aspetta.
- Per un ordine che deve RESTARE sul book: il mercato e' aperto E gia' in gioco? Se no, si
  aspetta. Motivo: al fischio Betfair sospende il mercato e cancella tutto cio' che non e'
  abbinato; un ordine appoggiato prima morirebbe subito.

**Quando.** A ogni giro il servizio ricostruisce la fotografia dal feed.

**Numeri.** Quota valida: sopra 1,00. Importo minimo di un ordine: 0,01 euro. Nessun parametro
modificabile dalla pagina.

**Esempio con le cifre.** Under 3,5: punta 1,50 (120 euro disponibili), banca 1,52 (80 euro),
mercato aperto, non ancora in gioco. Mike puo' puntare l'Under a 1,50. Non puo' ancora appoggiare
la bancata di uscita al fischio: il mercato non e' in gioco, quindi aspetta.
Una quota arrivata come 0 o vuota -> "non valida" -> nessun conto e nessun ordine su quella selezione.
Un importo di 0,004 euro -> non piazzabile; 0,01 euro -> piazzabile.

**Cosa vedi nell'app.** Le quote sulla card della partita. Nei motivi: "copertura: mercato Over 4.5
sospeso, si aspetta la riapertura".

**Se qualcosa va storto.** Feed vecchio o quota rotta: Mike non inventa numeri, non fa nulla e
ripete la domanda al giro dopo. Stato sconosciuto: trattato come "aspetta", mai come "chiuso".

**Per il tecnico.** `engine.py:30-35` (`MARKET_OU35`, `MARKET_OU45`, `SEL_UNDER`, `SEL_OVER`,
`LINE`), `81-91` (`Book`), `158-214` (`Snapshot`, `book()`), `550-569` (`stato_mercato`,
`STATO_*`), `572` (`operabile`), `577` (`appoggiabile_in_gioco`), `590` (`riaprira`), `599`
(`price_ok`), `617` (`size_ok`). Codici Betfair dei mercati e delle selezioni in `config.py:17-32`
(`OU35`, `OU45`, `EXPECTED_SEL`, `CUSTOMER_STRATEGY_REF` = marchio "mike" sugli ordini,
`LOCK_PORT_DEFAULT` 47319, `FOOTBALL_EVENT_TYPE_ID` senza uso). Inventario A: schede 1, 5, 7, 24-29, 109.
Paper e live: uguale (stesso feed).

---

## 2. Scommesse abbinate (viola, dati di partenza)

**Cosa fa.** Mike tiene in memoria ogni suo ordine (una "gamba"): a cosa serve, mercato, selezione,
punta o banca, quota chiesta, importo chiesto, importo ABBINATO, quota media abbinata, stato,
momento del piazzamento, se muore alla sospensione o resta in gioco, numero del ciclo.
Tutti i conti partono SOLO dall'importo abbinato, mai da quello chiesto.

Gli stati di una gamba:
- viva sul mercato (anche se in parte abbinata);
- a esito ignoto (Betfair non ha confermato ne' smentito);
- non piu' viva (abbinata tutta, oppure resto ritirato con una parte abbinata);
- ritirata senza nessun abbinamento;
- regolata.

Una gamba a esito ignoto, per i conti del rischio, vale come abbinata PER INTERO (peggior caso).
Una gamba di un ciclo pre-match gia' chiuso in profitto resta nei conti ma non conta piu' come soldi
a rischio ("archiviata").
Delle gambe ritirate senza abbinamento Mike tiene solo le ultime 5 per ogni tipo di ordine; le
altre le cancella dalla memoria (non entrano in nessun conto).

A cosa serve ogni gamba (11 tipi): ingresso Under, ultimo ingresso, seconda puntata dopo un gol
precoce, copertura Over 4,5, re-ingresso Under 4,5 (questi 5 AGGIUNGONO rischio); green pre-match,
uscita al fischio, chiusura Under, chiusura Over, green del re-ingresso, chiusura manuale (questi 6
lo RIDUCONO).

La memoria della partita tiene anche: fase attuale (21 fasi possibili, 3 finali: regolata, errore,
saltata), numero del ciclo, gol e quota al fischio, momento del gol precoce, stadio della copertura
(in una volta; prima tranche da comprare; prima tranche abbinata; seconda tranche), chiusura
manuale in corso, "non rientrare", proposte d'uscita.

**Quando.** Sempre: e' salvata sul database e riletta a ogni giro.

**Numeri.** Una gamba e' "abbinata tutta" se l'abbinato arriva all'importo chiesto meno 0,005 euro.
Quota dell'ordine arrotondata al tick valido piu' vicino; importo arrotondato al centesimo. Si tengono
5 gambe ritirate e mai abbinate per tipo.

**Esempio con le cifre.** Mike chiede di puntare 10,00 euro a 1,50; ne sono abbinati 6,00.
Restano 4,00 in coda. La gamba e' viva, non abbinata tutta. Per i conti vale 6,00 a 1,50.
Un ordine a esito ignoto da 100,00 euro di cui risulta abbinato 0,01 -> per il rischio conta 100,00.
Un ordine calcolato a quota 1,483 e 10,137 euro parte come 10,14 euro a 1,48.
180 coperture rifiutate e mai abbinate -> in memoria ne restano 5.

**Cosa vedi nell'app.** Le righe della scheda Trade e dell'Attivita'. "ciclo 1" nei motivi: il
bot conta i cicli da 0, ma nei testi scrive sempre da 1.

**Se qualcosa va storto.** Gamba a esito ignoto: vedi schema 08 (nessuna nuova apertura finche'
non si chiarisce).

**Per il tecnico.** `engine.py:37-44` (`STATES`, `TERMINAL_STATES`), `46-65` (`ROLES`,
`OPENING_ROLES`, `CLOSING_ROLES`, `UNDER_ROLES`, `STATUS_RECONCILE`, `EXIT_KINDS`), `94-155`
(`Leg`: `remaining`, `is_live`, `needs_reconcile`, `filled`, `fill_price`, `archived`), `217-356`
(`MatchCtx`), `359-381` (`Action`, `Decision`), `519-532` (`cycle_label`), `810` e `848-885`
(`MAX_CANCELLED_PER_ROLE`, `prune_dead_legs`), `913` (`active_legs`), `918-935`
(`_assume_matched`), `1464-1479` (`_legs`, `_last`), `1487-1491` (`_place`: tick e centesimo).
Inventario A: schede 2, 3, 6, 8, 9, 10, 23, 41, 43, 44, 64, 66. Paper e live: uguale; cambia solo
chi riempie l'abbinato (simulatore in paper, Betfair in live).

---

## 3. Gol e commissione (viola, dati di partenza)

**Cosa fa.** Mike legge minuto, gol segnati, intervallo si'/no, momento dell'ultimo gol, e i numeri
del modello: probabilita' di un gol nei prossimi 3 minuti, probabilita' che finisca con 4 gol
(mercato e modello), distribuzioni dei gol finali, pressione (corner e cartellini). La commissione
e' un parametro della pagina.
Dai gol Mike ricava due cose certe:
- Chi vince con T gol finali: l'Under vince se T e' sotto la linea; l'Over vince se T e' sopra.
- L'esito e' GIA' deciso? I gol non si tolgono. Appena i gol superano la linea l'Under ha perso e
  l'Over ha vinto, qualunque cosa faccia il mercato. Sotto la linea niente e' deciso.

**Quando.** A ogni giro.

**Numeri.** Commissione 5% (pagina: da 0 a 20). Linee 3,5 e 4,5. Gol finali contati da 0 a 8
("8" vale 8 o piu').
I parametri arrivano dalla pagina cosi': Mike parte dai valori di serie, prende SOLO i nomi che
conosce e i valori non vuoti, riporta ogni numero dentro il suo minimo e massimo, scarta le scelte
fuori elenco. Se una coppia minimo/massimo e' invertita (quota d'ingresso minima e massima, gol
minimi e massimi dell'uscita in perdita, minuti del secondo tempo), tornano entrambi ai valori di
serie. Quattro parametri vecchi (max_matches, catalogue_refresh_s, stream_extra_lines,
min_total_matched) vengono ignorati.

**Esempio con le cifre.** 4 gol segnati: Under 3,5 = gia' perso; Over 4,5 = non ancora deciso;
Under 4,5 = non ancora deciso. 5 gol: Over 4,5 = gia' vinto.
Commissione impostata a 5 -> Mike usa 0,05. Un utente scrive 30 nella commissione -> Mike usa 20
(il massimo).

**Cosa vedi nell'app.** Minuto e gol sulla card; nella tabella delle posizioni la colonna "decisa".

**Se qualcosa va storto.** Gol mancanti: "non so" per l'esito deciso. Attenzione: in due regole
d'uscita (attesa della copertura e cash out intelligente) i gol mancanti vengono contati come 0
(vedi "Punti da decidere"). Un valore "NaN" scritto in un parametro numerico non viene respinto.

**Per il tecnico.** `engine.py:628-632` (`selection_wins`), `635-646` (`selection_decided`),
`1254-1257` (`winners_from_total`); `config.py:38-66` (`env_str`, `env_int`, `env_float`,
`env_bool`), `73-379` e `426` (`Spec`, `PARAM_SPEC`, `DEFAULTS`), `429-450` (`_coerce`), `455-476`
(`_ORDERED_PAIRS`, `merge_params`), `479-480` (`commission_rate`), `398` e `424`
(`REMOVED_PARAMS`, `BACKEND_ONLY_PARAMS`). Inventario A: schede 7, 30, 31, 58, 110-115.
Paper e live: uguale.

---

## 4. Quota del green (verde, calcolo)

**Cosa fa.** Dalla quota a cui Mike ha puntato l'Under calcola la quota di chiusura in profitto: N
tick piu' in basso sulla scala ufficiale Betfair. Calcola anche quanto profitto si blocca e di
quanti tick si e' mossa la quota fra il nostro ingresso e il fischio.

La quota media d'ingresso e' la media delle punte abbinate pesata sugli importi.

**Quando.** Green pre-match, uscita al fischio, green del re-ingresso (i rami sono negli schemi 02,
03, 05).

**Numeri.** Tick del green pre-match 2, al fischio 2, del re-ingresso 2 (pagina: da 1 a 10).
Scala dei tick: da 1,01 a 2,00 un tick vale 0,01; da 2 a 3 vale 0,02; da 3 a 4 vale 0,05; da 4 a 6
vale 0,1; da 6 a 10 vale 0,2; da 10 a 20 vale 0,5; da 20 a 30 vale 1.

**Esempio con le cifre.**
- Punta 10,00 a 1,50. Quota del green: 2 tick sotto = 1,48.
- Importo della bancata = 10,00 x 1,50 / 1,48 = 10,135 -> 10,14 euro.
- Se l'Under vince: +5,00 dalla punta, -10,14 x 0,48 = -4,87 dalla bancata -> +0,13.
- Se l'Under perde: -10,00 dalla punta, +10,14 dalla bancata -> +0,14.
- Tolto il 5% di commissione: +0,13 in tutti e due i casi.
- Formula del profitto lordo bloccato: 10,00 x (1,50 / 1,48 - 1) = +0,135 euro.
- Quota media: 10,00 a 1,50 piu' 5,00 a 1,95 = 15,00 euro a (15,00 + 9,75) / 15,00 = 1,65.
- Scostamento al fischio: ingresso 1,50, al fischio 1,46 -> -4 tick (la quota e' scesa, a nostro
  favore).

**Cosa vedi nell'app.** La quota della bancata di uscita nella scheda Trade; lo scostamento al
fischio.

**Se qualcosa va storto.** Quota fuori scala: il tick viene prima arrotondato a una quota valida.

**Per il tecnico.** `engine.py:409-411` (`green_target`, usa `ticks_away` di
`live_order_build.py:95`), `414-416` (`locked_pnl_back`, usata solo a `engine.py:2842`), `684-697`
(`position`), `1672` (`_under_position`), `888-910` (`drift_ticks`). Importo del green:
`compute_greenup` in `Betfair/stream/trading/greenup.py:118-249` (importo = |se vince - se perde| /
quota). Inventario A: schede 13, 14, 35, 42, 78. Paper e live: uguale.

---

## 5. Se vince / se perde (verde, calcolo)

**Cosa fa.** Per ogni selezione Mike somma quanto guadagna se la selezione vince e quanto se
perde, usando solo gli abbinamenti e saltando le gambe archiviate.
- Una punta: se vince +importo x (quota - 1); se perde -importo.
- Una bancata: il contrario.
Una selezione e' "aperta" se i due numeri differiscono di almeno 0,01 euro. E' "ancora gestibile"
se e' aperta e il suo esito non e' gia' deciso dai gol.
Calcola anche il capitale investito: la somma delle punte di apertura abbinate (Under, seconda
puntata, copertura, re-ingresso). E' la base di molte percentuali.

**Quando.** A ogni giro.

**Numeri.** Soglia "piatta": 0,01 euro.

**Esempio con le cifre.**
- Under 3,5, punta 10,00 a 1,50: se vince +5,00; se perde -10,00. Aperta.
- Over 4,5, punta 2,26 a 6,60: se vince +2,26 x 5,60 = +12,66; se perde -2,26. Aperta.
- Capitale investito: 10,00 + 2,26 = 12,26 euro.
- Dopo il green (bancata 10,14 a 1,48): Under se vince +0,1328, se perde +0,14. Differenza
  0,0072 euro, sotto il centesimo: la selezione e' PIATTA (chiusa).
- Con 4 gol l'Under 3,5 e' aperta ma non piu' gestibile (esito deciso).

**Cosa vedi nell'app.** "se vince / se perde" sulla card; la tabella delle posizioni.

**Se qualcosa va storto.** Di una gamba a esito ignoto qui conta solo la parte abbinata gia' nota;
il rischio (riquadro 9) la conta invece per intero.

**Per il tecnico.** `engine.py:649-665` (`exposure`), `668-675` (`open_selections`), `678-681`
(`live_open_selections`), `700-704` (`invested`). Soglia `_FLAT_EPS` = 0,01 (`engine.py:67-75`).
Inventario A: schede 4, 32, 33, 34, 36. Paper e live: uguale.

---

## 6. Se chiudo ora (azzurro, profitto incassabile)

**Cosa fa.** Calcola quanti euro Mike incassa se chiude TUTTO adesso, al netto della commissione.
Per ogni selezione aperta:
- Esito gia' deciso dai gol: vale "se vince" o "se perde", senza bisogno di quota.
- Altrimenti: se "se vince" e' maggiore, Mike BANCA alla miglior quota di banca; se "se perde" e'
  maggiore, PUNTA alla miglior quota di punta. Importo = (se vince - se perde) / quota, al
  centesimo. Dopo la chiusura prende il peggiore dei due risultati.
Poi somma per mercato e toglie il 5% sul netto positivo di OGNI MERCATO (non di ogni selezione).
La commissione di un mercato si ripartisce sulle selezioni in utile in proporzione; l'eventuale
centesimo di scarto va sulla selezione di peso maggiore, cosi' le righe sommano il totale.
Se una selezione viva non ha quota, il calcolo e' "incompleto" e nessuna uscita parte.
Per ogni selezione aperta prepara anche la riga della tabella: lato netto, importo netto, quota
media, se vince / se perde, l'ordine di chiusura che farebbe il bot, "se chiudo ora", euro
disponibili a quella quota ed "eseguibile" (si' se bastano per tutto l'importo).

**Quando.** A ogni giro in gioco; e' la base delle uscite dello schema 11b.

**Numeri.** Commissione 5%. Tick "contro di noi" sulla chiusura: 0 (pagina: da 0 a 3; con N > 0 la
bancata si fa N tick piu' alta e la punta N tick piu' bassa, per abbinare subito).

**Esempio con le cifre.** Minuto 60, 1 gol. Banca Under 3,5 a 1,20; banca Over 4,5 a 20.
- Under: se vince +5,00, se perde -10,00. Differenza 15,00. Banca 15,00 / 1,20 = 12,50 euro a 1,20.
  Se vince: 5,00 - 12,50 x 0,20 = +2,50. Se perde: -10,00 + 12,50 = +2,50. Vale +2,50.
- Over: se vince +12,66, se perde -2,26. Differenza 14,92. Banca 14,92 / 20 = 0,75 euro a 20.
  Se vince: 12,66 - 0,75 x 19 = -1,59. Se perde: -2,26 + 0,75 = -1,51. Vale il peggiore: -1,59.
- Commissione: mercato 3,5 in utile di 2,50 -> 5% = 0,125. Mercato 4,5 in perdita -> niente.
- Totale netto: 2,50 - 0,125 - 1,59 = 0,785 -> **0,78 euro** (lordo 0,91).
- Righe: Under 2,375 -> 2,38, Over -1,59; somma 0,79; lo scarto di -0,01 va sull'Under -> 2,37.
- Esempio piu' semplice, solo Under: punta 10,00 a 1,50, banca a 1,30: 15,00 / 1,30 = 11,54 euro;
  risultato +1,54 su ogni esito; netto 1,54 x 0,95 = 1,46.

**Cosa vedi nell'app.** "se chiudo ora" sulla card (totale e per selezione); la colonna
"eseguibile" nella tabella delle posizioni.

**Se qualcosa va storto.** Quota mancante su una selezione viva: "prezzi incompleti", nessuna
uscita. Importo di chiusura sotto 0,01 euro: quella selezione non si chiude e resta al regolamento.
Nessuna selezione aperta: il valore e' 0,00 "completo".

**Per il tecnico.** `engine.py:384-394` (`CashoutValue`), `737-805` (`cashout_value`), `1413-1461`
(`posizione_per_selezione`); `greenup.py:56-70` (`_place_through`), `101-115` (`_hedge_size`),
`118-249` (`compute_greenup`, soglia piatta `FLAT_EPS` 0,01). Parametro `cashout_place_at_ticks`.
Inventario A: schede 11, 39, 63. Paper e live: uguale.

---

## 7. Conto per gol (verde, calcolo)

**Cosa fa.** Per ogni numero di gol finali da 0 a 8 calcola come finisce la partita: somma i due
mercati, ognuno al netto della sua commissione (5% solo se il mercato e' in utile). Qui entrano
anche le gambe dei cicli gia' chiusi.
Calcola anche:
- il contributo dei cicli gia' chiusi (differenza fra tutte le gambe e le sole aperte; deve essere
  uguale su ogni numero di gol, altrimenti "non si sa");
- il riepilogo per ciclo: importo puntato, quota media d'ingresso e d'uscita, chiuso si'/no, profitto
  (solo se chiuso), numero di gambe.

**Quando.** A ogni giro; la tabella serve al rischio, al "gia' bloccato", all'uscita in perdita a
modello (schema 11b) e al riepilogo.

**Numeri.** Gol finali da 0 a 8. Un ciclo e' "chiuso" se il suo risultato varia meno di 0,015 euro
fra 0 e 8 gol.

**Esempio con le cifre.** Under 10,00 a 1,50 + Over 2,26 a 6,60:
- 0, 1, 2 o 3 gol: Under +5,00, meno 5% = +4,75; Over -2,26. Totale **+2,49**.
- 4 gol: Under -10,00; Over -2,26 (4 non e' sopra 4,5). Totale **-12,26**.
- 5 o piu' gol: Under -10,00; Over +12,66, meno 5% = +12,02. Totale **+2,02**.
Riepilogo del ciclo pre-match chiuso in green: "ciclo 1: 10,00 a 1,50, uscita 1,48, chiuso, +0,13".

**Cosa vedi nell'app.** Il profitto per numero di gol sulla card; l'elenco dei cicli.

**Se qualcosa va storto.** Se il contributo dei cicli chiusi non torna uguale su ogni numero di gol,
il servizio non lo mostra ("non si sa") invece di dare un numero sbagliato.

**Per il tecnico.** `engine.py:707-719` (`_market_pnl_by_total`, NON salta le archiviate), `722`
(`_net`), `726-734` (`net_pnl_by_total`), `1351-1367` (`pnl_cicli_chiusi`), `1370-1410`
(`riepilogo_cicli`). Inventario A: schede 37, 38, 61, 62. Paper e live: uguale.

---

## 8. Perdita dell'Under (rosa, perdita)

**Cosa fa.** Dalla posizione NETTA abbinata sull'Under 3,5 (punte meno bancate gia' abbinate)
calcola quanti euro Mike perde se l'Under perde. E' la base della copertura. Calcola anche quanto
le coperture GIA' abbinate proteggono con 5 o piu' gol: somma il risultato con 5 gol di tutte le
gambe del mercato 4,5 non archiviate e toglie il 5% sul netto positivo del mercato.

**Quando.** Ogni volta che Mike dimensiona o riprezza la copertura.

**Numeri.** Arrotondata al centesimo, mai negativa.

**Esempio con le cifre.**
- Punta 10,00 a 1,50, nessuna bancata: perdita dell'Under **10,00**.
- Se una bancata di green ha abbinato 4,00 euro prima del fischio: -10,00 + 4,00 = perdita **6,00**.
  La copertura si calcola su 6,00, non su 10,00.
- Copertura gia' abbinata 2,26 a 6,60: con 5 gol 2,26 x 5,60 = 12,66 lordi -> 12,02 netti gia'
  garantiti.

**Cosa vedi nell'app.** Niente di diretto; compare nei dati della copertura ("liability").

**Se qualcosa va storto.** Una bancata a esito ignoto non riduce la perdita (conta solo
l'abbinato confermato).

**Per il tecnico.** `engine.py:459-465` (`under_liability`), `446-456` (`cover_matched_value`).
Chiamanti: `engine.py:3299-3300`, `3475-3476`. Inventario A: schede 18, 19. Paper e live: uguale.

---

## 9. Rischio e bloccato (rosa, protezione)

**Cosa fa.** Dalla tabella per gol ricava tre numeri:
- **Rischio vero della partita**: la perdita peggiore su 0-8 gol delle gambe non archiviate, con gli
  ordini a esito ignoto contati come abbinati per intero.
- **Gia' bloccato**: se nessuna selezione e' aperta e nessun ordine e' ignoto, il risultato (uguale su
  ogni numero di gol). Se non si e' MAI puntato: "niente" (non 0,00).
- **Risultato che non dipende dal finale**: nessun abbinamento -> 0,00; risultato uguale su 0-8 gol
  (entro 0,005) -> quel numero; altrimenti "serve il punteggio". Con un ordine ignoto -> "serve il
  punteggio". Serve a chiudere partite senza punteggio finale leggibile.
Tiene infine il **tetto di capitale per partita**: tetto meno capitale investito.

**Quando.** A ogni giro; il rischio e il bloccato vanno al database e allo stop giornaliero.

**Numeri.** Tetto per partita 0 = spento (pagina: da 0 a 100.000 euro). Tolleranza 0,005 euro.

**Esempio con le cifre.**
- Under 10,00 + Over 2,26: rischio vero = **12,26** (la riga dei 4 gol).
- Solo il ciclo in green 10,00 / 10,14: gia' bloccato **+0,13**.
- Partita senza ingressi: risultato **0,00** senza aspettare il punteggio.
- Tetto per partita 30,00 euro, investito 12,26: spazio rimasto 30,00 - 12,26 = **17,74**.

**Cosa vedi nell'app.** "liability" della partita; "gia' bloccato"; partite chiuse a 0,00 invece di
"DA SISTEMARE".

**Se qualcosa va storto.** Ordine a esito ignoto: il bloccato diventa "non si sa" e il rischio lo
conta al peggio.

**Per il tecnico.** `engine.py:938-947` (`event_liability`), `950-968` (`locked_pnl`), `813-845`
(`pnl_indipendente_dal_risultato`), `1707-1714` (`liability_room`, parametro
`max_liability_per_match`). Inventario A: schede 40, 45, 46, 81. Paper e live: uguale.

---

## 10. Importo copertura (verde, calcolo)

**Cosa fa.** Calcola quanti euro puntare sull'Over 4,5 perche', se finiscono 5 o piu' gol, il netto
dell'Over valga 1,2 volte la perdita dell'Under. Cosi' con 5+ gol la partita chiude a +20% della
perdita dell'Under.
In parole: importo = (1,2 x perdita dell'Under - quanto e' gia' garantito) / ((quota Over - 1) x
0,95). Mai negativo.
Due quote diverse:
- l'IMPORTO si calcola sulla miglior quota di punta dell'Over;
- l'ORDINE si piazza 2 tick piu' in basso, per entrare anche se la quota si muove durante il
  ritardo di piazzamento.
Dopo un gol precoce la copertura si compra in due tranche: prima il 50% dell'importo, poi il
residuo ricalcolato alla quota di quel momento.

**Quando.** Quando la regola del tempo dice "copri" (schema 11b, riquadro "Quando coprire").

**Numeri.** Fattore 1,2 (pagina: da 1 a 3). Tick sotto la quota migliore: 2 (pagina: da 0 a 6).
Prima tranche 50% (pagina: da 0 a 100). Commissione 5%.

**Esempio con le cifre.**
- Perdita Under 10,00; Over migliore 6,60; niente gia' garantito.
- Importo = 1,2 x 10,00 / (5,60 x 0,95) = 12,00 / 5,32 = 2,2556 -> **2,26 euro**.
- Ordine piazzato a 2 tick sotto 6,60 = **6,20** (fra 6 e 10 un tick vale 0,2).
- Se abbinato a 6,60: con 5+ gol 2,26 x 5,60 x 0,95 = 12,02 - 10,00 = **+2,02** (obiettivo +2,00).
- Se abbinato davvero a 6,20: 2,26 x 5,20 x 0,95 = 11,16 - 10,00 = **+1,16**. Protezione piu'
  bassa dell'obiettivo.
- Con la perdita ridotta a 6,00: 1,2 x 6,00 / 5,32 = **1,35 euro**.
- Due tranche: prima 2,2556 x 50% = 1,13 euro a 6,60 -> gia' garantiti 1,13 x 5,60 x 0,95 = 6,01.
  Tre minuti dopo l'Over e' a 8,00: residuo (12,00 - 6,01) / (7,00 x 0,95) = 5,99 / 6,65 = **0,90
  euro**. Con 5+ gol: 6,01 + 0,90 x 7,00 x 0,95 - 10,00 = +1,997 -> **+2,00**.

**Cosa vedi nell'app.** L'importo della copertura nella scheda Trade; nella nota dell'ordine
"X=2.26 legal=2.26 over=0.0% buf=2t".

**Se qualcosa va storto.** Quota Over assente o non valida: nessun calcolo (Mike aspetta). Tetto di
capitale per partita acceso: la copertura viene TAGLIATA allo spazio rimasto (17,74 nell'esempio
del riquadro 9); se lo spazio e' sotto 0,01 la copertura viene saltata.

**Per il tecnico.** `engine.py:426-435` (`cover_residual`, quella usata), `1687-1704`
(`cover_place_price`); chiamanti `3299-3339` e `3469-3496`; tranche `3240-3270`
(`frazione_copertura`, fuori area A). Mai usate in produzione: `419-423` (`cover_size`) e
`438-443` (`cover_size_residual`), solo nei test. Parametri `cover_profit_factor`,
`cover_place_at_ticks`, `early_goal_cover_pct`. Inventario A: schede 15, 16, 17, 80.
Paper e live: il calcolo e' uguale.

---

## 11. Regolamento (grigio, esito finale)

**Cosa fa.** A mercato chiuso, con il totale gol finale, calcola il risultato di ogni gamba:
- mai abbinata, o mercato annullato: nulla, 0,00;
- punta vinta: +importo x (quota - 1); punta persa: -importo; bancata: il contrario.
La commissione e' il 5% del netto positivo di ogni mercato, arrotondata al centesimo e ripartita
sulle gambe in utile. Lo scarto di arrotondamento va sulla riga piu' pesante (preferendo una in
utile), cosi' la somma delle righe fa esattamente il risultato della partita.
Ogni riga di chiusura riceve un tipo d'uscita: manuale; green (o "tempo" per la chiusura a minuto
del re-ingresso); profitto; perdita; forzata (tetto di perdita); tempo; altro. E ogni chiusura dice
quale apertura sta chiudendo (l'ultima punta abbinata della stessa selezione).

**Quando.** Quando il mercato e' chiuso e il punteggio finale e' noto (vedi schema 11b, riquadro
"Regola della fase").

**Numeri.** Commissione 5%.

**Esempio con le cifre.**
- Finale 2 gol: Under +5,00, commissione 0,25 -> +4,75; Over -2,26. Totale **+2,49**.
- Finale 4 gol: Under -10,00; Over -2,26. Totale **-12,26** (nessuna commissione).
- Finale 5 gol: Under -10,00; Over +12,66, commissione 0,63 -> +12,02. Totale **+2,02**.

**Cosa vedi nell'app.** Le righe regolate in Trade e in Regolate; "regolato T=2"; la colonna del
tipo d'uscita.

**Se qualcosa va storto.** Mercato di cui non si sa il vincitore: errore dichiarato (mai uno zero
inventato). Ordine a esito ignoto: regolamento sospeso (schema 11b).

**Per il tecnico.** `engine.py:397-403` (`SettleResult`), `1260-1262` (`settle_legs`),
`1265-1336` (`settle_legs_by_market`), `971-990` (`exit_kind_for`), `993-1001` (`opening_ref`).
Inventario A: schede 12, 47, 48, 58, 59, 60. Paper e live: uguale.

---

## 12. Importo piazzabile (verde, calcolo)

**Cosa fa.** Decide l'importo che parte davvero.
- **Importi esatti ACCESI** (di serie): l'importo calcolato arrotondato al centesimo. Un importo
  sotto 2,00 euro si piazza lo stesso con la tecnica "parcheggia, taglia, riprezza".
- **Importi esatti SPENTI**: l'importo viene portato al minimo del sito italiano (2,00 euro) e a
  multipli di 0,50, per eccesso (di serie), per difetto o al piu' vicino. Mike calcola di quanto
  (in %) si e' andati oltre. Se la copertura va oltre il 30% in piu', riprova per difetto; se e'
  ancora oltre, NON copre e aspetta.
Una chiusura si accetta da 0,01 euro in su.

**Quando.** Per ogni copertura. Con importi esatti spenti, anche per le punte di apertura (lo fa il
servizio).

**Numeri.** Minimo 2,00 euro, passo 0,50 euro. Arrotondamento "per eccesso" (pagina: per eccesso,
per difetto, al piu' vicino). Eccesso massimo della copertura 30% (pagina: da 0 a 200). Importi
esatti accesi (pagina: si'/no).

**Esempio con le cifre.**
- Importi esatti accesi: 1,354 -> **1,35 euro**, eccesso 0%.
- Importi esatti spenti: 1,35 per eccesso -> 1,50 -> alzato al minimo -> **2,00 euro**; eccesso
  2,00 / 1,35 - 1 = +48,15%. Oltre il 30%: riprova per difetto -> 1,00 -> alzato al minimo -> 2,00,
  ancora +48,15% -> copertura NON piazzata ("copertura: overshoot 48.1% oltre il tetto 30%").
- Una punta di 1,23 o 2,30 euro richiede la tecnica "parcheggia, taglia, riprezza"; 2,50 no.

**Cosa vedi nell'app.** Attivita' "size_legalized" quando il servizio legalizza un importo.

**Se qualcosa va storto.** Importo sotto 0,01: nessun ordine.
Paper o live: il calcolo e' uguale; in live un importo sotto 2,00 euro passa dal "parcheggia,
taglia, riprezza" (non ho verificato come lo simula il paper).

**Per il tecnico.** `engine.py:67-75` (`IT_BACK_MIN` 2,0, `IT_BACK_STEP` 0,5, `SUBMIN_FLOOR`
0,01), `468-483` (`legalize_back_size`), `486-506` (`cover_legal_size`), `509-516`
(`needs_submin`), `3366-3397` (tetto di eccesso `cover_max_overshoot_pct`, clamp del tetto per
partita, liquidita'); `service.py:746-751` (legalizzazione delle punte). Parametri `exact_sizes`,
`cover_rounding`, `cover_max_overshoot_pct`. Inventario A: schede 4, 20, 21, 22, 29.

---

## Frecce

- Scommesse abbinate -> Se vince / se perde: "importi" = solo gli importi abbinati e le loro quote,
  gambe archiviate escluse.
- Se vince / se perde -> Quota del green: "quota media" = media delle punte Under abbinate, 2 tick
  sotto.
- Quote e mercato -> Se chiudo ora: "miglior quota" = miglior banca (se vince > se perde) o miglior
  punta (se perde > se vince) di ogni selezione viva.
- Se vince / se perde -> Se chiudo ora: "posizione" = se vince / se perde di ogni selezione aperta.
- Se vince / se perde -> Conto per gol: "gambe" = tutte le gambe abbinate, anche dei cicli chiusi.
- Se vince / se perde -> Perdita dell'Under: "Under" = se perde dell'Under 3,5 (punte meno bancate
  abbinate).
- Conto per gol -> Rischio e bloccato: "minimo" = il risultato peggiore su 0-8 gol.
- Rischio e bloccato -> Regolamento: "finale" = mercato chiuso e totale gol noto.
- Perdita dell'Under -> Importo copertura: "x 1,2" = 1,2 x perdita meno quanto gia' garantito.
- Gol e commissione -> Importo copertura: "commissione 5%" = il netto dell'Over si calcola al 95%.
- Importo copertura -> Importo piazzabile: "arrotonda" = al centesimo (esatti accesi) o a 2,00 /
  0,50 (esatti spenti).

---

## Punti da decidere

Differenze dalla Costituzione (`Betfair/mike/COSTITUZIONE_MIKE.md`) che riguardano questi conti:
1. **Formula della copertura** (§3 Fase 3: "S = euro Under abbinati"). Il codice usa la perdita
   NETTA dell'Under (punte meno bancate abbinate) meno la protezione gia' garantita; importo
   calcolato sulla quota migliore; ordine piazzato 2 tick sotto. `engine.py:459-465`, `426-435`,
   `1687-1704`, `3299-3314`.
2. **Commissione nel cash out** (§3 Fase 4: "5% solo sulle selezioni in positivo"). Il codice la
   applica per MERCATO sul netto positivo e la ripartisce. `engine.py:778-802` (la §4.4 invece
   e' allineata al codice).
3. **Tick "contro di noi" sulla chiusura** (§6: "chiusura N tick oltre il best, appoggiata"). Nel
   codice la quota si sposta per abbinare SUBITO, non e' un ordine appoggiato. `greenup.py:56-70`.

Cose strane:
4. **Importo della copertura calcolato su una quota, ordine su un'altra.** L'importo si calcola sulla
   quota migliore (6,60), l'ordine parte 2 tick sotto (6,20). Se si abbina a 6,20 la protezione con
   5+ gol scende da +2,00 a +1,16 (esempio del riquadro 10). Il commento del codice dice il
   contrario ("la size si dimensiona su questo prezzo, mai sul best", `engine.py:1693`) e i due
   commenti a `engine.py:3303-3312` si contraddicono. Da decidere: su quale quota dimensionare.
5. **Tetto per partita misura il capitale puntato, non la perdita peggiore.** Con Under 10,00 e Over
   2,26 il tetto conta 12,26 puntati; la perdita peggiore e' anch'essa 12,26, ma dopo un green
   parziale le due cifre divergono. In piu' il tetto TAGLIA la copertura in silenzio (protezione
   minore). `engine.py:1714`, `3383-3388`.
6. **Copertura mai piazzata con importi esatti spenti.** Ogni copertura sotto circa 1,54 euro
   (2,00 / 1,30) viene alzata a 2,00, supera il 30% di eccesso anche per difetto e non parte: la
   partita resta scoperta. Vale solo con "importi esatti" spenti (di serie accesi).
   `engine.py:3373-3382`.
7. **Eccesso massimo inutile con importi esatti accesi**: l'eccesso e' sempre 0%. `engine.py:505`.
8. **L'arrotondamento della copertura vale anche per le punte d'apertura** (`service.py:751`).
9. **Funzioni senza chiamanti in produzione**: la formula base della copertura, la formula a due
   numeri del residuo (`cover_size`, `cover_size_residual`) e la chiusura forzata in un colpo solo
   (`force_flat_actions`, vedi 11b): solo nei test.
10. **Il conto per gol conta anche i cicli archiviati**, il "se vince / se perde" no: e' voluto per il
    regolamento, ma i due conti non lo dicono. `engine.py:707-719`.
11. **Nessuna selezione aperta = cash out "completo" a 0,00** (`engine.py:750`).
12. **Commento sui 2 euro sbagliato**: il commento della chiusura dice che sotto 2 euro non si tenta;
    la soglia vera e' 0,01 euro, e il secondo controllo (0,0095) non serve a niente.
    `engine.py:1765-1772`, `1734`.
13. **"NaN" in un parametro numerico** non viene respinto e arriva ai conti (`config.py:445-449`).
14. **Gol mancanti contati come zero** nell'attesa della copertura e nel cash out intelligente: vedi
    `11b_uscite_calcolate.schede.md`.

## Punti non chiariti

- Come il paper simula il "parcheggia, taglia, riprezza" sotto 2,00 euro: non letto.
- La tabella dei tick oltre 30 viene da flumine (`price_ticks_away`): non letta, riportata dalla
  scala standard Betfair.

## Schede dell'inventario rimandate ad altri schemi

- Schema 08 (guardie sugli ordini e freni): 65, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 88, 89,
  90, 91, 92, 93, 94, 95.
- Schema 06 (cancello delle uscite manuali / automatiche): 98, 99, 100, 101, 102, 103, 104, 105,
  106, 107.
