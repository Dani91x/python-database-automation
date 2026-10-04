# Seasons Catchup: perche' il debito dei buchi non converge (analisi B) e attesa dietro il Retrain (proposta C)

Solo lettura: nessun codice di produzione toccato per B e C. SELECT sul progetto dqbwaocvlzbxfrpacsac del 04/10/2026 (~10:30 UTC).
Fonte codice: `seasons_catchup.py` (`costruisci_coda`, `referto_buchi`), `season_gaps.py:8-25` (stati dei buchi).

## B. Numeri accertati

Lega-stagioni `in_progress` con `fonte=catchup` e `buchi_aperti>0`: **1.299**, **154.328** chiamate stimate.

| Dato | Valore |
|---|---|
| Stagione 2026+ (vive) | 718 lega-stagioni, 65.088 chiamate (media 91, max 522) |
| Stagione 2025 | 501 lega-stagioni, 87.389 chiamate (max 14.432: lega 667) |
| Stagioni <= 2024 | 80 lega-stagioni, 1.851 chiamate |
| `buco_aperto_dal` = 25/09 (primo giorno della funzione) | 1.220 lega-stagioni su 1.299, 136.764 chiamate. Nuovi buchi dal 26/09: 79 lega-stagioni in totale, ~17.500 chiamate (15.670 sono una sola stagione, 27/09) |
| Con almeno una partita `in_attesa` (API vuota, 1o tentativo) | 225 lega-stagioni, 1.715 partite-tabella |
| Con `errore` (errore API ripetuto) | **2** lega-stagioni |
| Con aggregati da fare (mancante/da_aggiornare/errore) | 929 lega-stagioni |
| `da_chiamare` con flag coverage False (NON contate come buchi) | 266.347 partite-tabella |
| Chiamate/giorno totali in `api_call_log` | 6.700-7.300 nelle notti 28/09-03/10, tutte `http 200`, nessuna risposta d'errore |
| Risposte vuote registrate in `fixture_detail_checks` | 19.265 partite-tabella; solo 192 con `vuoti>=2` |

Il debito NON e' gonfiato: le 154.328 chiamate stimate coincidono esattamente con la somma di `da_chiamare` sui soli endpoint con flag True.

## Le 3 cause piu' probabili

1. **Il debito iniziale e' enorme rispetto al ritmo e viene lavorato "dal piu' grande al piu' piccolo".** 1.220 lega-stagioni sono aperte dal 25/09 (136 mila chiamate), il budget e' 4-6 mila chiamate/notte (stima: 25-35 notti a ritmo pieno). `costruisci_coda` ordina P1/P2 per chiamate DECRESCENTI: ogni notte il budget va nelle lega-stagioni piu' grosse, che calano in chiamate ma restano aperte, quindi il NUMERO di lega-stagioni aperte (1.297 -> 1.278 -> 1.287) sembra fermo anche quando le chiamate scendono. Il numero di lega-stagioni e' la metrica sbagliata; contano le chiamate stimate (154k oggi, contro 156-178k nei referti precedenti: calo reale ma lentissimo).
2. **Afflusso quotidiano di nuovi buchi che compensa buona parte del lavoro.** Le partite di ogni giorno (es. 1.248 il 03/10, di cui solo 707 con eventi) entrano nelle stagioni vive con flag True; sono 718 lega-stagioni vive con 65 mila chiamate, e 12 nuovi buchi comparsi il 04/10. Stima non provata numero per numero (manca lo storico giornaliero di `buchi_aperti`): serve registrare ogni notte chiamate fatte, chiuse e aperte.
3. **Una stagione da sola pesa il 9% del debito e le chiamate vuote consumano budget senza dato.** Lega 667/2025: 14.432 chiamate (4.910 player stats, 4.897 team stats, 3.617 lineups, 1.008 events) su stagione passata con `fixtures_statistics_*` flag True: quasi certamente flag di coverage troppo ottimista (come per 129/250/255 nei log). Il 47% circa delle risposte registrate e' `vuoto` (19.265 su ~40 mila chiamate nel periodo): ogni risposta vuota costa una chiamata e chiude al massimo una partita-tabella come `vuoto_definitivo`, dopo 2 tentativi o 7 giorni.

Nota: `ultimo_esito` e' `{}` in tutte le 1.299 righe: lo stato non conserva traccia del lavoro della notte, quindi non si puo' misurare la convergenza da DB.

## Irrecuperabili per costruzione

- Ripetere un'API vuota non e' "per sempre": `season_gaps.py` gia' chiude da solo (`vuoto_definitivo`, "NON e' un buco") dopo 2 risposte vuote o 7 giorni dalla partita. I buchi `in_attesa` (1.715 partite-tabella in 225 lega-stagioni) sono quindi transitori: escono in 2-7 giorni se la lega-stagione viene raggiunta in coda.
- Irrecuperabili senza ritorno: quote di partite oltre 7 giorni (`non_disponibili`, gia' escluse dai buchi) e tabelle con flag coverage False (266 mila partite-tabella, escluse). Non c'e' bisogno di marcarle: non contano nel debito.
- Candidati a "chiusa per mancanza di dato": le lega-stagioni in cui TUTTE le chiamate residue riguardano endpoint con 1 sola risposta vuota storica. Non stimabile oggi senza uno storico (quanti in `in_attesa` si stanno ancora per chiudere).

## Correzione proposta (NON applicata) e rischio

1. Misurare prima: scrivere a fine corsa una riga di serie temporale (chiamate stimate, chiamate fatte, chiuse, nuove aperte) in `season_backfill_state` o in un log; popolare `ultimo_esito`. Rischio: nullo sui dati.
2. Ordinare la coda per **chiusura di lega-stagioni** (piu' economiche prime anche in P2) invece che per chiamate decrescenti, cosi' il numero di aperte scende ogni notte. Rischio: basso, cambia solo l'ordine, non i dati letti/scritti; le grandi (667) resterebbero in fondo. Da confermare con l'utente (e' una scelta di priorita').
3. Per le stagioni passate con flag True ma quasi tutte risposte vuote (es. 667/2025): una verifica a campione di 20 partite per endpoint prima di spendere 14 mila chiamate; se vuote, tabella marcata `vuoto_definitivo` d'ufficio. Rischio: medio (si potrebbe saltare dato presente); mitigare con campione casuale e soglia 100% vuoto.
4. Aumentare il budget notturno solo con decisione dell'utente (quota API-Football condivisa con Daily/Today/Results).

## C. Attesa di 90 minuti dietro il Retrain (proposta, NON applicata)

Fatto: il Catchup agganciato a "Monthly Leagues Mapping" (`workflow_run`) parte subito dopo il mapper, trova il Retrain in corso e aspetta fino a 90 min; il Retrain si auto-rilancia fino a 8 volte (`retrain_models.yml:371`), quindi spesso trova sempre "in corso". Il 04/10 ha fatto 95 min di runner con 0 chiamate.

| Opzione | Pro | Contro |
|---|---|---|
| A. Solo cron 13:47 UTC (togliere `workflow_run`) | Zero attesa sprecata; i run del 02 e 03/10 hanno lavorato proprio cosi' (4.3-5.9 mila chiamate); semplice | Il cron GitHub parte con ritardo mediano di ore (reale ~18-19 UTC); i flag aggiornati dal mapper del mattino sono comunque gia' letti; se il cron si perde un giorno, nessuna rete |
| B. Agganciare alla fine della catena del Retrain (`workflow_run` su `retrain_models.yml`) | Parte solo quando i modelli sono pronti, senza attese | Il Retrain ha 8 rilanci; ogni `completed` farebbe partire un Catchup (la `concurrency` ne tiene 1 in coda), rischio di molti run a vuoto; dipende dal nome del workflow |
| C. Lasciare com'e' ma ridurre l'attesa massima (es. 90 -> 15 min) | Modifica minima | Il Retrain puo' ancora bloccare la corsa; si perde il giro del mattino |

Raccomandazione: A (cron 13:47 UTC + dispatch manuale), eventualmente con attesa massima breve come rete. Nessun effetto sui dati. Va concordato con l'altro delegato che modifica il nome di "Monthly Leagues Mapping" e la riga `workflow_run.workflows` di `seasons_catchup.yml`.

## Non verificato

- Il ritmo reale di chiusura e l'afflusso giornaliero (manca lo storico di `buchi_aperti`; causa 2 e' una stima).
- Quante delle 225 lega-stagioni con `in_attesa` appartengono a P1/P2/P3 (la priorita' non e' salvata nello stato).
- Percentuale di risposte vuote per singola lega-stagione di grandi dimensioni (667/2025): non si e' chiamata alcuna API.
