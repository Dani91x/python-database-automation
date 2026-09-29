# Mike - Documento 12: tutti i parametri

Fonte dei valori: `Betfair/mike/config.py` (`PARAM_SPEC`, righe 75-379), letto per intero il 29/09/2026. Controllo:
**106 parametri** in `config.py`, 106 righe in queste tabelle, ciascuna col suo nome interno. Confronto con
l'inventario: `A_calcoli_e_guardie.md` schede 109-128, `E_schermate_e_pulsanti.md` scheda 28 ed elenco completo
dei parametri (le 106 chiavi coincidono con quelle del pannello dell'app). Variabili d'ambiente rilette in
`Betfair/mike/service.py`.

**Come si legge.** Una riga per parametro.
- *Valore di oggi*: il valore di serie scritto nel codice. Se lo hai cambiato dal pannello, vale il tuo.
- *Minimo - massimo*: se scrivi un numero fuori, Mike lo riporta al limite piu' vicino. Per le scelte, i valori
  ammessi; un valore fuori elenco torna al valore di serie. Un valore illeggibile torna al valore di serie.
- *Dall'app*: si' = pannello «Parametri» di Mike (pagina di Mike o riga di Mike in Control Room), vale dal giro
  dopo il salvataggio, senza fermare il bot. Oggi TUTTI i 106 parametri si cambiano dall'app.
- *Schema*: lo schema della guida che tratta quella regola (01 percorso, 02 prima del fischio, 03 dal fischio,
  04 copertura, 05a uscite a posizione coperta, 05b chiusura e rientro, 06 uscite manuali e automatiche,
  07 vita di un ordine, 08 freni e protezioni, 09 giro del servizio, 10 dati e conti, 11a posizione e profitto,
  11b uscite calcolate). «nessuno» = oggi nessuno schema ne parla.
- Tre coppie devono restare in ordine (minimo <= massimo): quota minima/massima d'ingresso, gol minimi/massimi
  dell'uscita in perdita, minuto d'inizio/fine del secondo tempo. Se le inverti, tornano ENTRAMBE al valore di serie.
- Paper e live: tutti i parametri valgono uguali nelle due modalita'. L'unico che cambia qualcosa solo in live e'
  «uscita appoggiata in live» (`live_resting_enabled`).

---

## 1. Ingresso prima del fischio (11)

| Nome in parole semplici | Cosa governa | Valore di oggi | Minimo - massimo | Dall'app | Schema | Nome interno |
|---|---|---|---|---|---|---|
| Importo per puntata | Quanti euro Mike punta sull'Under 3,5 a ogni ingresso (anche sotto i 2 euro) | 10,00 euro | 0,50 - 500 euro | si' | 01, 02 | `stake` |
| Finestra prima del fischio | Da quante ore prima del fischio Mike lavora la partita | 1,0 ore | 0,25 - 12 ore | si' | 02 | `entry_hours_before_ko` |
| Filtro campionati | Quali competizioni sono ammesse (vuoto = tutte), separate da virgola | vuoto (tutte) | testo libero | si' | nessuno | `competition_filter` |
| Ingressi prima del fischio | Acceso: Mike entra prima del fischio. Spento: nessun ingresso pre-partita | acceso | acceso / spento | si' | 02, 08 | `pre_enabled` |
| Quota minima d'ingresso | Sotto questa quota dell'Under 3,5 Mike non entra | 1,30 | 1,01 - 20 | si' | 02 | `pre_entry_price_min` |
| Quota massima d'ingresso | Sopra questa quota dell'Under 3,5 Mike non entra | 3,00 | 1,01 - 20 | si' | 02 | `pre_entry_price_max` |
| Liquidita' minima al prezzo migliore | Al prezzo migliore deve esserci almeno N volte l'importo | 1,0 volte l'importo | 0,5 - 5 volte | si' | 02 | `pre_min_back_size_factor` |
| Distanza massima punta-banca | Oltre questa distanza fra punta e banca Mike non entra | 6 tick | 1 - 20 tick | si' | 02 | `pre_max_spread_ticks` |
| Vita dell'ordine d'ingresso | Dopo quanti secondi un ingresso non abbinato viene ritirato | 60 secondi | 5 - 3600 secondi | si' | 02, 07 | `pre_entry_ttl_s` |
| Giri massimi per partita | Quanti giri di trading al massimo prima del fischio | 10 giri | 0 - 100 giri | si' | 02 | `pre_max_cycles` |
| Pausa fra due giri | Secondi di attesa dopo un green prima del giro successivo | 60 secondi | 0 - 3600 secondi | si' | 01, 02 | `pre_reentry_cooldown_s` |

## 2. Green prima del fischio (3)

| Nome in parole semplici | Cosa governa | Valore di oggi | Minimo - massimo | Dall'app | Schema | Nome interno |
|---|---|---|---|---|---|---|
| Tick del green | Di quanti tick sotto la quota d'ingresso Mike banca per chiudere in profitto | 2 tick | 1 - 10 tick | si' | 02, 06 | `pre_green_ticks` |
| Modo del green | Appoggiata: la bancata va sul book subito. A mercato: chiude al prezzo migliore quando i tick ci sono | appoggiata (`resting`) | `resting` / `taker` | si' | 02, 09 | `pre_exit_mode` |
| Uscita appoggiata in live | Solo in live: spento = il green torna «a mercato», strategia diversa da quella provata in paper | acceso | acceso / spento | si' | 02, 09 | `live_resting_enabled` |

## 3. Ultimo ingresso (4)

| Nome in parole semplici | Cosa governa | Valore di oggi | Minimo - massimo | Dall'app | Schema | Nome interno |
|---|---|---|---|---|---|---|
| Minuti dell'ultimo ingresso | Quanti minuti prima del fischio Mike fa l'ultima mossa pre-partita | 10 minuti | 1 - 120 minuti | si' | 02 | `pre_last_entry_min` |
| Ultimo ingresso che resta in gioco | Acceso: l'ultimo ingresso non abbinato resta valido anche dopo il fischio | acceso | acceso / spento | si' | 02, 08, 09 | `last_entry_persist` |
| Tick sopra il prezzo migliore | Di quanti tick sopra il prezzo migliore punta l'ultimo ingresso (0 = al prezzo migliore) | 0 tick | 0 - 3 tick | si' | 02 | `last_entry_ticks_above` |
| Ritiro del residuo dopo il fischio | Dopo quanti secondi dal fischio Mike ritira la parte non abbinata dell'ultimo ingresso | 120 secondi | 0 - 900 secondi | si' | 01, 03, 07, 11b | `cancel_unmatched_after_ko_s` |

## 4. Veto sulla probabilita' dell'Under 3,5 (6)

| Nome in parole semplici | Cosa governa | Valore di oggi | Minimo - massimo | Dall'app | Schema | Nome interno |
|---|---|---|---|---|---|---|
| Veto sull'Under 3,5 | Acceso: all'ultimo ingresso Mike tiene o rientra solo se la probabilita' calibrata dell'Under e' sopra la soglia | acceso | acceso / spento | si' | 02 | `veto_p_under35_cal` |
| Soglia a quota 1,30 | Probabilita' minima dell'Under 3,5 quando la quota e' 1,30 | 0,807 (80,7 %) | 0 - 1 | si' | 02 | `veto_p_under35_soglia_130` |
| Soglia a quota 1,50 | Probabilita' minima dell'Under 3,5 quando la quota e' 1,50 | 0,684 (68,4 %) | 0 - 1 | si' | 02 | `veto_p_under35_soglia_150` |
| Soglia a quota 2,00 | Probabilita' minima dell'Under 3,5 quando la quota e' 2,00 | 0,514 (51,4 %) | 0 - 1 | si' | 02 | `veto_p_under35_soglia_200` |
| Soglia a quota 2,50 | Probabilita' minima dell'Under 3,5 quando la quota e' 2,50 | 0,385 (38,5 %) | 0 - 1 | si' | 02 | `veto_p_under35_soglia_250` |
| Soglia a quota 3,00 | Probabilita' minima dell'Under 3,5 quando la quota e' 3,00 | 0,275 (27,5 %) | 0 - 1 | si' | 02 | `veto_p_under35_soglia_300` |

Fra un nodo e l'altro la soglia e' interpolata (esempio: a quota 1,75 la soglia sta fra 0,684 e 0,514).

## 5. Uscita al fischio (4)

| Nome in parole semplici | Cosa governa | Valore di oggi | Minimo - massimo | Dall'app | Schema | Nome interno |
|---|---|---|---|---|---|---|
| Uscita al fischio | Acceso: al fischio Mike prova prima a uscire in profitto | acceso | acceso / spento | si' | 03 | `ko_green_enabled` |
| Tick dell'uscita al fischio | Di quanti tick sotto la quota d'ingresso Mike banca al fischio | 2 tick | 1 - 10 tick | si' | 01, 03, 06 | `ko_green_ticks` |
| Durata dell'uscita al fischio | Per quanti secondi dal fischio la bancata resta sul book; poi Mike copre | 180 secondi | 0 - 900 secondi | si' | 01, 03 | `ko_green_window_s` |
| Ritmo dell'uscita al fischio | NESSUN EFFETTO dal 16/09: nessun controllo lo legge piu' | 5 secondi | 1 - 60 secondi | si' | 03, 11b | `ko_green_retry_s` |

## 6. Seconda puntata dopo un gol precoce (2)

| Nome in parole semplici | Cosa governa | Valore di oggi | Minimo - massimo | Dall'app | Schema | Nome interno |
|---|---|---|---|---|---|---|
| Seconda puntata | Acceso: con un gol nella finestra dell'uscita al fischio Mike punta di nuovo l'Under 3,5 | acceso | acceso / spento | si' | 03, 08 | `second_entry_enabled` |
| Importo della seconda puntata | Percentuale dell'importo per puntata (50 % di 10 euro = 5 euro) | 50 % | 0 - 200 % | si' | 01, 03 | `second_entry_stake_pct` |

## 7. Copertura Over 4,5 (20)

| Nome in parole semplici | Cosa governa | Valore di oggi | Minimo - massimo | Dall'app | Schema | Nome interno |
|---|---|---|---|---|---|---|
| Copertura | Acceso: Mike copre l'Under con una punta sull'Over 4,5. Spento: Under senza copertura in gioco | acceso | acceso / spento | si' | 04 | `cover_enabled` |
| Fattore di profitto della copertura | Con 5 gol o piu' la copertura rende l'importo Under per questo fattore (1,2 = +20 %) | 1,2 | 1 - 3 | si' | 04, 11a | `cover_profit_factor` |
| Quando coprire | auto = Mike decide se aspettare; immediate = subito; wait = aspetta sempre fin dove ammesso | auto | `auto` / `immediate` / `wait` | si' | 11b | `cover_policy` |
| Rischio gol massimo per aspettare | Mike aspetta solo se la probabilita' di un gol nei prossimi 3 minuti e' sotto questa | 0,06 (6 %) | 0 - 1 | si' | 11b | `cover_wait_hazard_max` |
| Attesa massima della copertura | Oltre questo minuto di gioco Mike non aspetta piu' | 10 minuti | 0 - 45 minuti | si' | 11b | `cover_wait_max_min` |
| Probabilita' di 4 gol massima per aspettare | Mike aspetta solo se la probabilita' di mercato di esattamente 4 gol e' sotto questa | 0,16 (16 %) | 0 - 1 | si' | 11b | `cover_wait_p4_max` |
| Quota Over gia' buona | Se l'Over 4,5 e' gia' a questa quota o sopra, Mike copre subito | 7,0 | 1,01 - 50 | si' | 04, 11b | `cover_good_price` |
| Risparmio minimo per aspettare | Mike aspetta solo se il risparmio atteso sulla copertura e' almeno questo | 8 % | 0 - 100 % | si' | 11b | `cover_wait_min_gain_pct` |
| Orizzonte della stima | Su quanti minuti futuri Mike stima il risparmio dell'attesa | 5 minuti | 1 - 20 minuti | si' | 05a, 11b | `cover_wait_step_min` |
| Attesa dopo un gol | Secondi di attesa dopo un gol perche' le quote si riassestino | 45 secondi | 0 - 300 secondi | si' | 04, 11b | `cover_postgoal_delay_s` |
| Gol massimi per coprire | Oltre questo numero di gol Mike non compra una copertura nuova | 2 gol | 0 - 4 gol | si' | 04, 11b | `cover_max_goals` |
| Arrotondamento | Con importi esatti spenti: arrotonda per eccesso, per difetto o al piu' vicino (vale anche per le punte d'ingresso) | per eccesso (`ceil`) | `ceil` / `floor` / `nearest` | si' | 04, 11a | `cover_rounding` |
| Eccesso massimo della copertura | Con importi esatti spenti: quanto la copertura arrotondata puo' superare quella giusta | 30 % | 0 - 200 % | si' | 04, 11a | `cover_max_overshoot_pct` |
| Importi esatti al centesimo | Acceso: qualsiasi importo, anche sotto 2 euro (piazza e taglia). Spento: arrotonda ai minimi Betfair | acceso | acceso / spento | si' | 04, 11a | `exact_sizes` |
| Rifiuti prima del freno | Rifiuti di fila con lo stesso codice d'errore prima che la copertura si fermi (poi serve «Riprendi») | 3 rifiuti | 1 - 20 rifiuti | si' | 04, 08 | `cover_rifiuti_max` |
| Ritmo minimo fra due tentativi | Secondi minimi fra due tentativi di copertura | 15 secondi | 1 - 300 secondi | si' | 04, 08 | `cover_retry_min_s` |
| Cuscinetto della copertura | Di quanti tick sotto il prezzo migliore Mike piazza la copertura, per farla abbinare | 2 tick | 0 - 6 tick | si' | 04, 11a | `cover_place_at_ticks` |
| Prima tranche dopo un gol precoce | Secondi dal gol precoce alla prima meta' della copertura | 120 secondi | 0 - 900 secondi | si' | 01, 03, 04 | `early_goal_cover_delay_s` |
| Peso della prima tranche | Percentuale della copertura comprata nella prima tranche | 50 % | 0 - 100 % | si' | 04, 11a | `early_goal_cover_pct` |
| Seconda tranche | Secondi dall'abbinamento della prima tranche alla seconda (ricalcolata sul residuo) | 180 secondi | 0 - 900 secondi | si' | 01, 04, 05a, 11b | `early_goal_cover2_delay_s` |

## 8. Cash out (12)

| Nome in parole semplici | Cosa governa | Valore di oggi | Minimo - massimo | Dall'app | Schema | Nome interno |
|---|---|---|---|---|---|---|
| Soglia del cash out | Mike chiude tutto quando il netto di chiusura arriva a questa percentuale della base | 5 % | 0,5 - 50 % | si' | 01, 05a, 11b | `cashout_profit_pct` |
| Base del cash out | total = importo Under + copertura; under = solo importo Under | total | `total` / `under` | si' | 05a, 11b | `cashout_base` |
| Tick contro di noi sulla chiusura | Di quanti tick la bancata di chiusura va oltre il prezzo migliore per abbinarsi subito | 0 tick | 0 - 3 tick | si' | 05a, 06, 11a | `cashout_place_at_ticks` |
| Cash out intelligente | Acceso: Mike chiude prima della soglia quando tenere non vale il rischio | acceso | acceso / spento | si' | 05a, 11b | `cashout_smart_enabled` |
| Profitto minimo del cash out intelligente | Sotto questa percentuale della base il cash out anticipato non scatta mai | 2 % | 0 - 50 % | si' | 05a, 11b | `cashout_smart_min_pct` |
| «A un passo» dalla soglia | Quanti punti sotto la soglia contano come «a un passo» | 2 punti % | 0 - 50 punti | si' | 05a, 11b | `cashout_smart_tolerance_pct` |
| Fase calda: rischio gol | Probabilita' di gol nei prossimi 3 minuti oltre la quale la fase e' calda | 0,10 (10 %) | 0 - 1 | si' | 05a, 11b | `cashout_smart_hazard_hot` |
| Fase calda: pressione | Indice di pressione offensiva oltre il quale la fase e' calda | 1,15 | 1 - 1,25 | si' | 05a, 11b | `cashout_smart_pressure_hot` |
| Punteggio caldo | Da quanti gol il punteggio e' considerato caldo | 3 gol | 0 - 8 gol | si' | 05a, 11b | `cashout_smart_goals_hot` |
| Margine sul valore atteso | Mike chiude se aspettare vale meno di chiudere ora di almeno questi punti | 1 punto % | 0 - 50 punti | si' | 05a, 11b | `cashout_smart_ev_margin_pct` |
| Riprezzo delle chiusure | Ogni quanti secondi Mike riprezza la parte non abbinata di una chiusura | 10 secondi | 1 - 600 secondi | si' | 02, 04, 05a, 06, 08, 11b | `close_retry_s` |
| Tentativi massimi di chiusura | Quanti riprezzi al massimo; poi Mike resta in attesa senza riprezzare | 20 tentativi | 1 - 100 tentativi | si' | 02, 03, 04, 05a, 06, 08, 11b | `close_max_attempts` |

## 9. Chi esegue le uscite (1)

| Nome in parole semplici | Cosa governa | Valore di oggi | Minimo - massimo | Dall'app | Schema | Nome interno |
|---|---|---|---|---|---|---|
| Uscite automatiche | Spento (manuale): ogni uscita nuova diventa una proposta da approvare. Acceso: Mike esce da solo. Torna spento a ogni avvio nuovo dell'app | spento (manuale) | acceso / spento | si' (con conferma per accendere) | 05a, 06, 09 | `uscite_automatiche` |

## 10. Uscite in perdita all'intervallo e nel secondo tempo (13)

| Nome in parole semplici | Cosa governa | Valore di oggi | Minimo - massimo | Dall'app | Schema | Nome interno |
|---|---|---|---|---|---|---|
| Modo dell'uscita in perdita | model = confronta chiudere ora con tenere fino alla fine; fixed = solo la regola della perdita tollerata | model | `model` / `fixed` | si' | 01, 05a, 11b | `loss_exit_mode` |
| Premio al rischio | Quanto Mike toglie al valore del tenere per il rischio dei 4 gol | 10 % | 0 - 300 % | si' | 05a, 11b | `loss_exit_risk_premium_pct` |
| Probabilita' di 4 gol prudente | Acceso: Mike usa la stima piu' pessimista fra modello, storico e mercato | acceso | acceso / spento | si' | 05a, 11b | `loss_exit_p4_prudent` |
| Tetto «non chiudere oltre» | Oltre questa perdita percentuale Mike tiene invece di chiudere (0 = spento) | 0 % (spento) | 0 - 100 % | si' | 05a, 11b | `loss_exit_max_pct` |
| Casi minimi dello storico | Quante partite servono nella tabella intervallo -> finale perche' Mike la usi | 200 partite | 20 - 5000 partite | si' | 11b | `loss_exit_emp_min_n` |
| Uscita all'intervallo | Acceso: la regola vale all'intervallo | acceso | acceso / spento | si' | 05a, 11b | `ht_loss_exit_enabled` |
| Perdita tollerata all'intervallo | Regola fissa: Mike chiude se la perdita e' entro questa percentuale della base | 25 % | 0 - 100 % | si' | 05a, 11b | `ht_loss_pct` |
| Gol minimi | Da quanti gol vale l'uscita in perdita (intervallo e secondo tempo) | 3 gol | 0 - 8 gol | si' | 05a, 11b | `ht_loss_goals_min` |
| Gol massimi | Fino a quanti gol vale l'uscita in perdita (intervallo e secondo tempo) | 4 gol | 0 - 8 gol | si' | 05a, 11b | `ht_loss_goals_max` |
| Uscita nel secondo tempo | Acceso: la regola vale anche nel secondo tempo | acceso | acceso / spento | si' | 05a, 11b | `h2_loss_exit_enabled` |
| Perdita tollerata nel secondo tempo | Regola fissa del secondo tempo | 25 % | 0 - 100 % | si' | 05a, 11b | `h2_loss_pct` |
| Inizio finestra secondo tempo | Minuto da cui vale la regola del secondo tempo | 46' | 45' - 100' | si' | 05a, 11b | `h2_loss_from_min` |
| Fine finestra secondo tempo | Minuto fino a cui vale la regola del secondo tempo | 85' | 45' - 100' | si' | 05a, 11b | `h2_loss_to_min` |

## 11. Rientro sull'Under 4,5 (7)

| Nome in parole semplici | Cosa governa | Valore di oggi | Minimo - massimo | Dall'app | Schema | Nome interno |
|---|---|---|---|---|---|---|
| Rientro | Acceso: dopo un gol e una chiusura in profitto Mike puo' rientrare sull'Under 4,5 | acceso | acceso / spento | si' | 01, 05b, 08, 09 | `reentry_enabled` |
| Tick del green del rientro | Di quanti tick sotto la quota del rientro Mike banca | 2 tick | 1 - 10 tick | si' | 05b, 06 | `reentry_green_ticks` |
| Gol massimi per rientrare | Con quanti gol al massimo vale il rientro (1 = linea 4,5, l'unica nel feed) | 1 gol | 0 - 1 gol | si' | 01, 05b | `reentry_max_goals` |
| Minuto massimo del rientro | Entro quale minuto di gioco Mike puo' rientrare | 45' | 0' - 100' | si' | 01, 05b | `reentry_until_min` |
| Chiusura a tempo del rientro | Minuto in cui Mike chiude comunque il rientro (0 = mai: la bancata resta fino alla fine) | 0 (mai) | 0' - 100' | si' | 05b | `reentry_exit_until_min` |
| Quota del rientro sopra il primo ingresso | Acceso: Mike rientra solo se la quota supera quella del primo ingresso | acceso | acceso / spento | si' | 05b | `reentry_price_min_over_entry` |
| Tieni se in perdita | Con la chiusura a tempo impostata: acceso = se in perdita tiene invece di chiudere | spento | acceso / spento | si' | 05b | `reentry_hold_if_loss` |

## 12. Rischio e tetti (6)

| Nome in parole semplici | Cosa governa | Valore di oggi | Minimo - massimo | Dall'app | Schema | Nome interno |
|---|---|---|---|---|---|---|
| Commissione | Percentuale Betfair sul netto positivo di ogni mercato, usata in tutti i conti | 5 % | 0 - 20 % | si' | 04, 11a | `commission_pct` |
| Partite con posizione al massimo | Quante partite con soldi sopra insieme; oltre, niente aperture nuove | 10 partite | 1 - 90 partite | si' | 08, 10 | `max_open_matches` |
| Stop giornaliero | Perdita del giorno oltre la quale Mike non apre piu' (0 = spento) | 50,00 euro | 0 - 100.000 euro | si' | 08, 10 | `daily_loss_stop` |
| Capitale massimo per partita | Euro puntati al massimo su una partita (0 = spento) | 0 (spento) | 0 - 100.000 euro | si' | 02, 08, 11a | `max_liability_per_match` |
| Tetto di perdita della partita | Chiusura forzata quando il netto di chiusura arriva a -N % della base; sempre automatica | 100 % | 0 - 500 % | si' | 01, 05a, 06, 08, 11b | `event_loss_cap_pct` |
| Lettura a mercato chiuso | Secondi fra due letture del book a mercato chiuso per il regolamento (minimo reale 5 secondi) | 60 secondi | 0 - 600 secondi | si' | 09, 10 | `settle_confirm_s` |

## 13. Cadenze del servizio e del database (12)

| Nome in parole semplici | Cosa governa | Valore di oggi | Minimo - massimo | Dall'app | Schema | Nome interno |
|---|---|---|---|---|---|---|
| Intervallo fra due decisioni | Tempo minimo fra due decisioni sulla stessa partita | 500 millisecondi | 100 - 5000 millisecondi | si' | 02, 09, 11b | `decide_min_interval_ms` |
| Ripetizione dei messaggi | Lo stesso messaggio ripetuto si scrive al massimo una volta ogni N secondi | 300 secondi | 10 - 3600 secondi | si' | 09 | `skip_log_interval_s` |
| Rilettura del feed | Ogni quanti secondi Mike rilegge il feed delle quote dal database | 4 secondi | 0 - 30 secondi | si' | 09 | `feed_cache_s` |
| Rilettura delle partite | Ogni quanti secondi Mike rilegge l'elenco completo delle partite | 60 secondi | 0 - 600 secondi | si' | 09 | `events_reload_s` |
| Ricalcolo dei totali | Ogni quanti secondi Mike ricalcola i totali del giorno (per lo stop giornaliero) | 20 secondi | 0 - 300 secondi | si' | 10 | `aggregates_cache_s` |
| Riparazione ordini e righe | Ogni quanti secondi Mike riallinea le sue scommesse con le righe salvate e controlla il conto | 30 secondi | 0 - 600 secondi | si' | 08, 09 | `reconcile_every_s` |
| Giro a riposo | Cadenza del giro quando non si muove niente | 5 secondi | 1 - 60 secondi | si' | 09 | `idle_cycle_s` |
| Aggiornamento partita con posizione | Ogni quanti secondi Mike riscrive l'ora di una partita con soldi sopra | 5 secondi | 0 - 120 secondi | si' | 09 | `publish_heartbeat_s` |
| Aggiornamento partita osservata | Ogni quanti secondi Mike riscrive l'ora di una partita solo osservata | 60 secondi | 0 - 600 secondi | si' | 09 | `publish_idle_heartbeat_s` |
| Scrittura in blocco | Acceso: una sola scrittura per tutte le partite a ogni giro | acceso | acceso / spento | si' | 09 | `events_batch_write` |
| Statistiche | Ogni quanti secondi Mike riscrive le statistiche in testa alla pagina | 10 secondi | 0 - 300 secondi | si' | 09 | `stats_min_s` |
| Battito del servizio | Ogni quanti secondi Mike dice «sono vivo» | 20 secondi | 0 - 300 secondi | si' | 09 | `heartbeat_min_s` |

## 14. Freschezza dei dati (5)

| Nome in parole semplici | Cosa governa | Valore di oggi | Minimo - massimo | Dall'app | Schema | Nome interno |
|---|---|---|---|---|---|---|
| Eta' massima dei dati per guardare | Oltre questa eta' della riga del feed Mike non valuta la partita (salvo scanner vivo) | 45 secondi | 3 - 180 secondi | si' | 08, 10 | `feed_max_age_s` |
| Scanner vivo | Riga vecchia ma scanner che ha battuto entro N secondi = prezzo ancora valido | 75 secondi | 10 - 300 secondi | si' | 08 | `scanner_alive_max_s` |
| Eta' massima del book | Un book visto piu' di N secondi fa vale come assente | 90 secondi | 5 - 600 secondi | si' | 10 | `book_seen_max_s` |
| Eta' massima per mandare un ordine | Soglia stretta: oltre questa eta' Mike non manda ordini (ne' le tue chiusure) | 20 secondi | 3 - 120 secondi | si' | 02, 08 | `order_max_age_s` |
| Scanner vivo per mandare un ordine | Oltre l'eta' sopra, Mike manda l'ordine solo se lo scanner ha battuto entro N secondi | 30 secondi | 5 - 120 secondi | si' | 02, 08 | `order_scanner_max_s` |

Totale: 11 + 3 + 4 + 6 + 4 + 2 + 20 + 12 + 1 + 13 + 7 + 6 + 12 + 5 = **106**.

---

## Variabili d'ambiente (file `.env`, NON dall'app)

Si cambiano solo nel file `.env` e valgono al riavvio del servizio. Riletto in `Betfair/mike/service.py`.

| Nome in parole semplici | Cosa governa | Valore di oggi | Minimo - massimo | Dall'app | Schema | Nome interno |
|---|---|---|---|---|---|---|
| Soldi veri permessi | Acceso: Mike puo' mandare ordini veri in live. Spento: niente soldi veri | spento | acceso / spento | no | 08 | `MIKE_LIVE_ENABLED` (`service.py:98`) |
| Coda ordini flumine | Acceso: in live gli ordini passano dalla coda flumine; spento: chiamate dirette | spento | acceso / spento | no | 07 | `MIKE_USE_FLUMINE_QUEUE` (`service.py:781`) |
| Porta del lucchetto | Porta che impedisce di avviare due Mike insieme | 47319 | numero di porta | no | nessuno | `MIKE_LOCK_PORT` (`service.py:47`) |
| Porta del canale locale | Porta del canale diretto fra Mike e l'app desktop | 47333 | numero di porta | no | nessuno | `MIKE_LOCAL_WS_PORT` (`service.py:5560`, letta senza gli aiuti di config) |
| Ore pre-fischio dello scanner | Da quante ore prima del fischio lo scanner pubblica le linee Over/Under. Se e' piu' corta della finestra d'ingresso, Mike lo scrive nell'attivita' | nel codice 0 (= ramo spento, avviso); il valore vero e' quello del `.env` | ore | no | 02 | `SAFE_PRE_KO_OU_HOURS` (`service.py:3953`) |

## Costanti fisse (non sono parametri, non si cambiano dall'app)

| Nome in parole semplici | Cosa governa | Valore | Nome interno |
|---|---|---|---|
| Durata di una firma d'uscita | Quanto vale la tua approvazione di un'uscita, dal clic | 120 secondi | `APPROVAZIONE_TTL_S` (`engine.py:2240`) |
| Marchio degli ordini | Etichetta degli ordini di Mike su Betfair | «mike» | `CUSTOMER_STRATEGY_REF` (`config.py:30`) |
| Porta del lucchetto di serie | Valore usato se `MIKE_LOCK_PORT` manca | 47319 | `LOCK_PORT_DEFAULT` (`config.py:32`) |
| Codici dei mercati | Le due linee operate | Over/Under 3,5 e Over/Under 4,5 | `OU35`, `OU45` (`config.py:17-18`) |
| Codici delle selezioni | Solo documentazione e prove, mai usati dal bot | Under 3,5 = 1222344, Over 3,5 = 1222345, Over 4,5 = 1222346, Under 4,5 = 1222347 | `EXPECTED_SEL` (`config.py:26`) |
| Sport | Codice del calcio, non usato dal bot | 1 | `FOOTBALL_EVENT_TYPE_ID` (`config.py:19`) |
| Armamento del Cash out in live | Dopo quanto decade il primo clic della doppia conferma | 10 secondi | `MIKE_LIVE_ARM_TIMEOUT_MS` (frontend) |
| Armamento di Chiudi a mercato in live | Idem, costante separata con lo stesso valore | 10 secondi | `MIKE_FLATTEN_ARM_TIMEOUT_MS` (frontend) |

---

## Parametri che esistono ma nessuno legge

1. **Ritmo dell'uscita al fischio** (`ko_green_retry_s`, 5 secondi): nessun controllo lo legge dal 16/09. Il pannello
   lo mostra ancora e si puo' cambiare, senza nessun effetto (il testo d'aiuto lo dice).
2. **Quattro parametri tolti l'11/09** (`REMOVED_PARAMS`, `config.py:398`): `max_matches`, `catalogue_refresh_s`,
   `stream_extra_lines`, `min_total_matched`. Non sono fra i 106: se arrivano dall'app vengono scartati in
   silenzio.
3. **Funzionano solo a condizione.** `cover_max_overshoot_pct` e `cover_rounding` lavorano solo con «Importi esatti al
   centesimo» spento (oggi acceso): oggi non hanno effetto. `reentry_hold_if_loss` lavora solo con
   `reentry_exit_until_min` diverso da 0 (oggi 0): oggi non ha effetto. `loss_exit_max_pct` a 0 e
   `max_liability_per_match` a 0 sono spenti.
4. **In pratica spento.** `event_loss_cap_pct` a 100 % scatta solo quando la chiusura vale -100 % della base, cioe'
   quando non c'e' piu' niente da salvare.

## Parametri il cui commento dice un valore diverso da quello vero

Nel codice:
1. **Uscite automatiche.** Il commento del cancello dice «interruttore ACCESO (default)» (`engine.py:2340`); il valore
   vero e' SPENTO, cioe' manuale (`config.py:254`, `engine.py:2247`).
2. **Veto sull'Under 3,5.** Un commento del motore dice «interruttore `veto_p_under35_cal` SPENTO» (`engine.py:352`) e
   uno dell'app dice «PREPARATO, SPENTO» (`frontend/src/lib/mike.ts:461-463`); il valore vero e' ACCESO
   (`config.py:152`).
3. **Ritmo dell'uscita al fischio.** Il commento di `tentativo_gia_rifiutato` dice che l'uscita al fischio aspetta
   `ko_green_retry_s` (`engine.py:1525-1529`); non e' piu' vero dal 16/09.
4. **Cuscinetto della copertura.** Il commento dice che l'importo si calcola sulla quota del cuscinetto
   (`engine.py:1693`); il codice lo calcola sulla quota migliore (`engine.py:3313`).
5. **Tick contro di noi sulla chiusura.** La Costituzione e il testo del pannello lo descrivono come «N tick oltre il
   prezzo migliore, appoggiata»; nel codice la quota si sposta contro di noi per abbinare subito
   (`greenup.py:55-70`): non e' un ordine appoggiato.
6. **Ore pre-fischio dello scanner.** L'inventario E indica 1 ora di serie per `SAFE_PRE_KO_OU_HOURS`; nel codice di
   Mike, se la variabile manca, vale 0 (ramo spento, con avviso). Il valore vero dipende dal `.env` (non letto).

Nella Costituzione di Mike (paragrafo 6 e altri), rimasta indietro rispetto al codice:
7. Parametri: 72 nella Costituzione, 106 nel codice.
8. `feed_max_age_s`: 15 secondi nella Costituzione, 45 nel codice.
9. `ht_loss_goals_min`: 2 gol nella Costituzione, 3 nel codice (cambiato il 13/09 su richiesta dell'utente).
10. `entry_hours_before_ko`: 3 ore nei paragrafi 1 e 3, 1 ora nel codice (il paragrafo 6 e' gia' allineato).
11. `settle_confirm_s`: «ogni 30 secondi» nella Costituzione, 60 secondi nel codice.
12. Battito del servizio: costante fissa di 10 secondi nella Costituzione, oggi parametro `heartbeat_min_s` a 20
    secondi.
13. `live_resting_enabled`: la Costituzione dice che in live l'uscita e' sempre «a mercato»; nel codice lo diventa solo
    se questo parametro e' spento (di serie acceso).
14. `uscite_automatiche`: assente nella Costituzione, che dice le uscite di Mike automatiche; nel codice sono manuali di
    serie.
15. Non documentati nella Costituzione: `cover_rifiuti_max`, `cover_retry_min_s`, `cover_place_at_ticks`,
    `veto_p_under35_*`, `live_resting_enabled`, `uscite_automatiche`, `book_seen_max_s`, `order_max_age_s`,
    `order_scanner_max_s`, `scanner_alive_max_s`.

## Punti non chiariti

- Il valore attuale di `SAFE_PRE_KO_OU_HOURS` nel `.env` non e' stato letto (fuori perimetro).
- I valori salvati oggi nel database (`mike_control.params`) non sono stati letti: se l'utente ha cambiato un
  parametro dal pannello, vale quello e non il valore di serie di queste tabelle.
- La colonna «Schema» e' stata ricavata cercando il nome interno negli schemi gia' scritti e, dove manca, dall'argomento
  (05b e 02 per i parametri non ancora citati per nome). Gli schemi 05b e 13 erano ancora in scrittura.
- Altre variabili d'ambiente lette fuori da `Betfair/mike` (freno unico, ordini reali OFF/PAPER/LIVE, identificativo
  dell'avvio dell'app) governano anche Mike ma non sono nell'elenco: vedi schema 08.
