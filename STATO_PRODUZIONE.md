# STATO PRODUZIONE — checklist unica per andare LIVE
**Aggiornato: 14/09/2026 13:00 · coordinatore `admin-30`**

> **Regola d'uso: questo file è il registro condiviso. Chi chiude una riga la sposta in ✅ e ci mette
> COMMIT + EVIDENZA (numeri osservati o `file:riga`). Una riga chiusa senza evidenza non è chiusa.**
> Nessuno cancella righe: si spostano.

---

## 🔴 BLOCCANTI PER IL LIVE — senza questi non si accende

| # | Manca | Cosa succede senza | Chi |
|---|---|---|---|
| L1 | **Mike: prova sul campo dell'uscita appoggiata in live.** Codice in `02ed5d6`, mai eseguito su partita vera | Se la lay appoggiata non si abbina, Mike in live **perde su ogni ciclo** dove in paper guadagna | admin-07 |
| L2 | **Mike: `_resting_filled` onesto** (`service.py:783`). Oggi dichiara il fill appena il mercato *sfiora* il prezzo: nessuna coda, nessun volume scambiato | Il paper **sovrastima il tasso di abbinamento**: i suoi numeri non valgono come prova per il live | admin-07 |
| L3 | ~~censimento~~ **FATTO — e il difetto c'è: Omega in paper NON applica il bet delay.** `omega_engine.paper_fill` (`:280`) riempie sul book corrente, istantaneo; zero occorrenze di «delay» nella funzione. Il bet delay è citato solo per il percorso a coda (`omega_service.py:1645`), che **oggi non è attivo** (`execution_mode='rest'`). **Il metro di paragone è in casa**: Mike in paper ritarda il piazzamento di `bet_delay` (`mike/service.py:1964`), Omega no | **Il paper di Omega è più VELOCE del live**: entra ed esce a prezzi che in live, dopo 1-8 s di ritardo, potrebbero non esserci più. È una divergenza di strategia travestita da dettaglio, esattamente come sospettato. ⚠️ **La correzione NON è ovvia**: applicare il ritardo cambia i numeri storici di Omega e va deciso, non fatto di slancio | admin-07 → ⏳ utente |
| L4 | **Safe combo: guardia di abbinabilità solo in paper** (`bot_service.py:4508`). Paper salta, live piazza e poi svolge | Due strategie diverse sugli stessi dati. **DECISIONE UTENTE**: guardia anche in live (prudente, preferenza delle due sessioni) o via dal paper (fedele, più rumoroso) | ⏳ utente |
| L5 | **Tennis: finali non escluse per nome.** Unica delle 4 esclusioni del manuale non implementata | Il bot opera su finali, che il manuale esclude | admin-fa |
| L6 | **`daily_loss_stop`: valore reale non confermato** (`control.stats.params_effective.risk`) | Con i cap spenti per decisione utente è **l'unico freno rimasto**. Se assente, in live niente ferma una giornata storta | admin-30 |

## 🟠 BLOCCANTI PER LA CERTIFICAZIONE

| # | Manca | Cosa succede senza | Chi |
|---|---|---|---|
| C1 | **Omega: telemetria delle 2 gambe.** 6 partite su 89 hanno entrambe; 37 gambe mancanti **senza ragione registrata** | «Omega rispetta la regola» **non è né dimostrabile né smentibile** | admin-07 |
| C2 | **Mike: elenco numerato 1→75** dentro `COSTITUZIONE_MIKE.md` §16.4. Oggi ci sono solo i 10 blocchi. Strumento esistente: `Betfair/tools/verifica_75_condizioni_2026_09_13.py` → **39/75** in paper | Non si può dire quale condizione si sta osservando mentre accade | admin-07 |
| C3 | **Safe: tabelle di riscontro delle 4 varianti** contro `SPEC_STRATEGIA_S.md`, con `file:riga` + test + osservazione sul campo | Nessuna prova scritta che il codice corrisponda alla specifica | admin-fa |
| C4 | **Controllo del gioco: ACCESO.** Implementato su entrambi i motori con l'inversione del Risultato Esatto, ma **nasce spento**: copertura `pressure_index` non ancora misurata | **Base e Punta aprono con 3 condizioni su 4**: operazioni che il manuale rifiuterebbe | admin-fa |

## 🟡 UI E CONTROL ROOM

| # | Manca | Cosa succede senza | Chi |
|---|---|---|---|
| U1 | **Cancelletto di approvazione**: stato `proposed` nelle tre code. **Richiede una migrazione.** Contratto in `PIANO_MAESTRO` §5.2-bis | I bot piazzano da soli: la Control Room mostra e non filtra. **È il cuore della pagina** | admin-07 + admin-fa (code) · admin-30 (pagina) |
| U2 | **Percorso di esecuzione PER PARTITA** + **tempo decisione→fill** sulla riga (oggi l'istante della decisione non è scritto) | Non si sa quale percorso ha guidato quell'ordine né quanto ci ha messo | admin-fa |
| U3 | **Certificazione delle 3 UI**: 5 domande per riquadro (fonte unica · età · netto di commissione · cosa mostra quando manca · paper e live separati) | Numeri a schermo senza provenienza dichiarata | ciascuno la propria |
| U4 | **Mike: «MODELLO ASSENTE» è FALSO** su ogni partita pre-match (`MikeMatchCard.tsx:191`; `lambda_source` è nullo perché il frame di modello è solo in-play, `service.py:1642`) | La card mente su tutte le partite prima del fischio | admin-07 |
| U5 | **Mike: ordini ANNULLATI scritti `status='error'`** (`meta.phase='cancelled'`) | La tabella accusa il bot di guasti che non ci sono | admin-07 |
| U6 | **Mike: 0,13 + 0,13 con totale 0,27** (arrotondamento 0,1341×2) | Un centesimo che non torna, sotto gli occhi | admin-07 |
| U7 | **Safe: due manopole INERTI** nella scheda parametri (`paper_fill_ttl_s`, `live_fill_deadline_s`: in Safe non sono usate). ⚠️ **In Omega sono attive** (`omega_service.py:1960`, `:2090`) | Chi le gira crede di aver cambiato qualcosa. Chi le spostasse su Omega credendole inerti farebbe danno | admin-fa |

## ⚙️ OPERATIVO — azioni dell'utente

| # | Cosa | Perché |
|---|---|---|
| O1 | **`git push`** — commit locali di `admin-30`: `296118f`, `a4072a8`, `ad68253` | Il push è bloccato dal classificatore di questa sessione. Comando: `! git push` |
| O2 | **Riavviare l'app desktop** | Senza, la Control Room non compare |
| O3 | **Runner: autospegnimento a 18 h / inattività** — il watchdog per progetto **non lo riavvia** dopo un'uscita pulita | Oggi non morde (Mike non usa la coda). Morderà il giorno in cui qualcosa dipenderà dalla coda: si fermerebbe **in silenzio** |

## ⛔ NON DIMOSTRABILE OGGI — e non per pigrizia

| | Perché |
|---|---|
| **Redditività** di qualunque strategia | Base 1 operazione, Punta 2, tennis 8 in pareggio. Servono settimane. **La metrica di oggi è il COMPORTAMENTO, non la percentuale** (conseguenza dello stake fisso deciso dall'utente) |
| **Tick sotto carico pieno** | Tre misure discordanti (p95 177 → 797 → 333 ms). Serve il picco del pomeriggio |
| **Colonna `live` delle 75 condizioni** | Si riempie solo operando con soldi veri |

---

## ✅ CHIUSO OGGI — con commit ed evidenza

| Cosa | Commit | Evidenza |
|---|---|---|
| Canale realtime locale sui 3 bot (47333/47334/47335) + testate agganciate | `c25ec21` | 31 schede + 17 testate in 25 s, primo messaggio 0,96 s; caduta socket → si torna al DB |
| Respiro del database | (13/09) | Mike letture 1680→198/min, scritture 306→8-19; Omega 126→71 |
| **Mike: l'uscita appoggiata esiste ANCHE IN LIVE** — la strategia è una sola | `02ed5d6` | Tesi «su REST il resting non esiste» **smentita**: `place_submin_live` parcheggia via REST con «NIENTE timeInForce, l'ordine DEVE restare a riposo». Il FOK era una riga cablata in `place_order_live`, non una proprietà del percorso. 14 test nuovi; 9 test riscritti (non cancellati) conservando l'invariante «in live non si simula MAI un abbinamento» |
| **Mike: storico separato paper/live** | `ff97407` + `e90b360` | `get_mike_daily('paper')` → 4 giorni · `('live')` → **0**; `mike_trades` 755 righe **tutte paper**. `get_mike_day_trades` era **ROTTO** (alias `t` invece di `o`): ora ieri 76 operazioni paper / 0 live |
| **Mike: elenco operativo 1→75** — esisteva solo a parole | `08d5e4b` + `00e0b60` | Generato dallo strumento, non scritto a mano. 4 stati (✓ · ⊗ ⊘). **5 righe marcate ⊘**: 18/19/20/21/25 avevano la spunta verde in paper su un ramo che in live non esisteva |
| **Modalità per singola strategia** (tennis live + calcio paper) | `83e8138` | Regola: ai soldi veri si arriva **scrivendolo**, mai ereditandolo. Voce assente/illeggibile → paper, con riga di diagnosi rumorosa |
| **FILL_OR_KILL mancante in paper** sulla coda | `83e8138` | Letto in `flumine/simulation/simulatedorder.py:127-165`. + test che confronta le due righe di coda **campo per campo** |
| **Mike: uscita appoggiata cablata in live su REST** | `02ed5d6` | `place_order_live(..., fill_or_kill=False)`. Il FOK era una riga cablata, non una proprietà di REST |
| Mike: storico separato per modalità | `ff97407` + migrazione **applicata** | Verifica da fare: `get_mike_daily(NULL,NULL,'live')` **deve** tornare 0 |
| Tennis: take profit sotto 1,03 e stop loss | (13/09) + osservazione 14/09 | 3 ingressi a 1,01-1,02 portati a fine match (+0,04/+0,02/+0,04); 1 take profit a 1,03 con netto +0,06; 1 stop obbligatorio −0,21 (−10,5 %, dentro la banda 5-25 % del manuale) |
| `pre_ko` reidratato dal DB | (13/09) + osservazione 14/09 | `rehydrated: True` su partita vera. **Base e Punta non sono più spente**: valutate per intero, scartate con ragione scritta |
| Tennis: taker puro su entrambi i lati → FOK è la semantica **giusta** | verificato | `engine.py:1241` ingresso al best back; `close_plan`/`_su_tick` (`execution.py:844`, `:824`) chiudono al best opposto. **Nessuna strategia Safe ha bisogno di ordini a riposo** |
| **Battito del runner** = processo vivo, non subscription su | `ad68253` | Il runner **girava** mentre il battito diceva 2 settembre. Tre stati: spento · vivo in attesa · in streaming |
| **CONTROL ROOM** `/control-room` + pulsante in SelectSport e Dashboard | `296118f`, `a4072a8`, `ad68253` | 63 test (33 matematica + 30 pagina), typecheck pulito |
| Specifica Safe estratta dall'artifact | — | `SPEC_STRATEGIA_S.md` (`STRATEGY S.txt` conteneva solo un link) |
| Specifica esecuzione live | — | `ESECUZIONE_LIVE.md` |

## ⛔ DECISIONI DELL'UTENTE — chiuse, non si riaprono

- **quota di banca: nessun limite** (deciso col 23:1 davanti) · **stake fisso** (deciso con 46→128 € di responsabilità per 2 € di stake)
  → conseguenza operativa: la «perdita tipica 8-12 %» del manuale **non è una metrica di certificazione**
- **minuti di ingresso = soglia «a partire da»**, non fascia → +43 % di aperture sul Risultato Esatto
- **«quota di entrata 1.20-1.34» = quota LIVE della FAVORITA**
- **nessun cap alle operazioni · stake 2 € modificabile · doppia conferma live sempre**
- **obiettivo giornaliero 250 €**, lo stesso di Omega
- **apertura E chiusura passano da notifica**; le proposte **non scadono** (restano vive finché non si va a mercato o si ignorano; se ignorate tornano alla prossima occasione); prezzo e liquidità si aggiornano mentre la proposta è viva
