# INGRESSO PASSIVO — la misura sulle registrazioni vere (17/09/2026)

> **La domanda.** Omega oggi entra prendendo il best `availableToLay` (FOK, attraversando
> lo spread). `K_MISURATO_2026-09-16.md` dice che a quel prezzo il bias non basta: k < 1 in
> ogni fascia. `REFERTO_V3_2026-09-16.md` §7.5 chiama «la cosa vera» capire se si puo'
> entrare **dentro** lo spread. Qui c'e' la misura, sulle registrazioni reali.
>
> Riproducibile: `python -m Betfair.omega.tools.misura_ingresso_passivo`
> Codice: `Betfair/omega/tools/misura_ingresso_passivo.py`
> Dati versionati: `Betfair/omega/data/ingresso_passivo_2026-09-17.json`
> Test + falsificazione: `Betfair/omega/tests/test_ingresso_passivo_2026_09_17.py`
>
> **Questa misura non tocca la strategia, il servizio, il motore, le migrazioni, il
> frontend, e non scrive una riga di database.** E' uno strumento di misura e basta.

---

## 0. La risposta, in quattro righe

1. **Appoggiare una lay dentro lo spread si abbina di rado**: **11,3 %** delle volte un tick
   sotto il best lay, **10,2 %** a meta' spread, **1,7 %** al best back. Nove volte su dieci
   l'ordine muore senza fill (sospensione, fine finestra, gol).
2. **Il prezzo che si guadagna quando si abbina e' piccolo dove si abbina, e grande dove
   non si abbina**: +6,3 % di `p_implicita` al livello (a), +16,7 % a (b), +42,9 % a (c).
3. **Per portare k da 0,80 a 1,00 (solo pareggio) servirebbe +25 % di `p_implicita`; per
   arrivare a 2 servirebbe +150 %.** Nessuno dei tre livelli ci arriva: (a) e (b) non
   raggiungono neppure il pareggio, e (c) — l'unico che ci andrebbe vicino — si abbina
   1,7 volte su 100.
4. **E chi si abbina e' selezionato male.** Le celle che si sono abbinate sono uscite
   **10,3 %** delle volte, contro **4,1 %** dell'insieme di partenza: chi ci prende
   l'ordine, mediamente, sa qualcosa. 27,5 % dei fill ha visto il book scendere sotto il
   nostro prezzo entro un minuto; 10 % e' stato abbinato nei due minuti prima di un gol.

> **Sui numeri di k e di EV gli intervalli sono enormi (8 partite, 8 uscite): sono un
> PRIOR, non un verdetto.** Cio' che invece e' solido, perche' non dipende dagli esiti, e'
> la percentuale di abbinamento e il miglioramento di prezzo: §4 e §5.

---

## 1. Metodo

### 1.1 La catena e' quella di produzione

```
_live_raw/<id>/<id>.raw.jsonl     stream NATIVO Betfair registrato
  -> flumine 2.13.11               FlumineSimulation + HistoricalStream
  -> banco_comune.replay_evento    lo stesso driver del replay di Omega
  -> SCANNER VERO                  safe_strategy.service.Scanner
  -> riga di scan VERA             minuto e punteggio dal sidecar IPS
  -> questa misura                 candidati e ordini appoggiati
```

Il minuto e il punteggio **non vengono mai dall'orologio**: vengono dal `payload` della
riga di scan, che li prende dal sidecar dei punteggi passando da `apply_score_state`, la
stessa funzione di `poll_scores` in produzione. Il catalogo dei nomi delle scoreline e'
quello di `replay_registrazioni.leggi_catalogo` (formula dei gusci, gia' verificata).

### 1.2 Chi e' un candidato

Per ogni registrazione, per ogni gamba, a ciascun **minuto d'ingresso** (griglia di 5' dentro
la finestra: **1T 20-40'** su HALF\_TIME\_SCORE, **2T 50-80'** su CORRECT\_SCORE — i valori
sono letti da `omega_config.DEFAULTS`, non scritti qui), ogni runner che:

* ha stato `ACTIVE` e mercato `OPEN` e in gioco;
* ha un best `availableToLay` **in banda** `price_min`..`price_max` = **20..120**;
* ha almeno `min_lay_liquidity` = **5,00 EUR** disponibili a quel prezzo;
* **e' una scoreline** (mai gli aggregati «Any Other/Any Unquoted», come `select_by_model`);
* **non e' il punteggio corrente ne' adiacente**: raggiungibile (`h >= casa`, `a >= ospiti`)
  e a distanza `(h - casa) + (a - ospiti) >= model_min_goal_distance` = **2** gol.

Sono le stesse condizioni del filtro di `omega_model.select_by_model`. Non si applica il
cancello di valore (`p_modello <= p_implicita / k`): qui non si sta scegliendo una gamba, si
sta misurando il **book**.

### 1.3 I tre prezzi passivi

Scala tick **ufficiale Betfair** (`flumine.utils.get_nearest_price` / `price_ticks_away`, la
stessa che usa gia' lo scalper del repo — non ne e' stata riscritta un'altra).

| livello | prezzo | dove ci si mette |
|---|---|---|
| **a** | un tick sotto il best lay | davanti a tutta la coda dei back, il piu' vicino al tocco |
| **b** | mid fra best back e best lay, al tick | in mezzo allo spread |
| **c** | al best back | **dietro** alla coda dei back gia' presente |

Un prezzo passivo di lay sta **strettamente sotto** il best lay (se no e' un ordine al tocco:
flumine lo abbina nel `place`, e la misura lo scarta dichiarandolo —
`abbinato_al_place_non_passivo`, 25 casi su 1.069) e **mai sotto** il best back.

### 1.4 Stake e commissione

Lay **1,00 EUR**, sempre (lo stake della gamba V3), commissione **5 %**. `p_implicita` e'
`(1-c)/(L-c)`, la formula del motore. EV per 1 EUR di stake = `0,95 · (1 - 1/k)`
(PROGETTO §3.3).

---

## 2. LA REGOLA DELLA CODA USATA — e' quella di flumine, non una nostra

Il matching lo fa **`flumine.simulation.simulatedorder.SimulatedOrder`** (flumine 2.13.11),
cioe' la stessa classe che abbina gli ordini di Omega nel banco comune. Non e' stata
riscritta: viene istanziata e chiamata. In dettaglio:

1. **Arrivo in coda** — `SimulatedOrder.place` (`simulatedorder.py:64-240`). Per un LAY a
   prezzo `P`: se `best availableToLay <= P` si abbina subito (scartato, v. §1.3); se
   `P < best availableToLay` l'ordine si accoda e la sua **posizione in coda** `_piq` e' la
   size gia' presente a `P` sul lato `availableToBack` — esattamente «la quantita' che era
   gia' in coda a quel prezzo quando siamo arrivati».
2. **Abbinamento** — `_process_traded` / `_calculate_process_traded`
   (`simulatedorder.py:457-496`). A ogni aggiornamento si prende il **delta** del volume
   scambiato (`trd`/`tv` dello stream), calcolato da
   `flumine.markets.middleware.RunnerAnalytics`. Per un LAY conta il volume a prezzo
   `<= P`; di quel volume flumine ne prende **meta'** (`traded_size / 2`: il `trd` di
   Betfair conta le due gambe dello stesso abbinamento) e lo usa **prima** per consumare
   `_piq`, e solo per l'eccedenza per riempire noi. Finche' la coda davanti non e' finita,
   non si prende un centesimo.
3. **`config.simulation_available_prices` resta `False`** (il default di flumine): il
   semplice fatto che il book si muova attraverso il nostro prezzo **non** ci abbina; serve
   volume scambiato. E' il ramo prudente, ed e' dichiarato.
4. **Isolamento per ORDINE.** Ogni candidato e' un mondo a se': nel controfattuale «se
   avessi appoggiato QUESTO ordine» esiste un ordine solo, quindi ogni `SimulatedOrder`
   riceve la **sua copia** del delta scambiato. Se i tre livelli competessero fra loro (che
   e' cio' che farebbe l'isolamento per strategia, il default di flumine), il livello piu'
   alto mangerebbe il volume del piu' basso e la misura direbbe una cosa che nel
   controfattuale non succede. **Dichiarato perche' e' una scelta, non un dettaglio.**

### 2.1 Tre morti in piu' di quelle che flumine da' da solo

Vanno tutte nella direzione **prudente** (meno abbinati), e le prime due sono le stesse del
banco comune (`MotoreReplay._lapse_alla_sospensione`, che documenta le fonti Betfair):

* **sospensione in gioco** (gol, rigore, rosso): l'ordine LAPSE non abbinato viene cancellato
  prima che il mercato riapra. Applicata **prima** del matching sul book della sospensione;
* **cambio di punteggio** visto dallo scanner: stessa cosa, anche quando la sospensione in
  quella registrazione non si vede. Questa e' una morte **in piu'** rispetto a Betfair;
* **fine finestra**: oltre il minuto di chiusura della gamba l'ordine non vale piu'.

### 2.2 Il bet delay non e' regalato

L'ordine viene **deciso** al minuto d'ingresso sul book di quell'istante (come farebbe il
bot), ma **arriva a mercato** solo sul primo book successivo a `place_latency + betDelay`
— la stessa formula che flumine usa per i pacchetti (`orderpackage.calc_simulated_delay`:
0,120 s + betDelay del `marketDefinition`, tipicamente 5 s in gioco). Se in quel momento il
mercato e' sospeso, l'ordine **non entra affatto**.

### 2.3 Che cosa vuol dire «abbinato»

Fill **pieno** di 1,00 EUR. I fill parziali non contano come abbinati (sono contati a parte
in `size_abbinata`): e' la scelta prudente.

---

## 3. I dati

| | |
|---|---|
| registrazioni lette | **39** su 51 cartelle vere di `_live_raw/` (12 non hanno il file `.raw.jsonl`; i 9 `_synth_*` sono esclusi perche' finti) |
| errori di replay | **0** |
| registrazioni con almeno un candidato | **29** (10 non hanno mai un runner in banda con liquidita' nella finestra) |
| istanti-candidato (runner x minuto d'ingresso) | **357** |
| candidati misurati (x 3 livelli) | **1.069** |
| candidati con esito noto | **877** su 1.069 (il `marketDefinition` finale non porta un WINNER per 24 mercati su 73) |
| ordini piazzati davvero | **1.044** (25 scartati: il prezzo era gia' disponibile, non era un ingresso passivo) |
| ordini abbinati | **80** |
| durata del giro completo | **1.632 s** (27 minuti) |

Il book e' **sottile**: lo spread mediano fra best back e best lay sui candidati e' di **6
tick** (quartili 5 e 10, media 8,2). Solo **2 candidati su 357** avevano uno spread di un
tick. Il prezzo mediano al tocco e' **60,0** (min 20, max 120).

E la coda davanti, a quei prezzi, **non c'e'**: al livello (a) il **99,4 %** degli ordini
e' arrivato con coda ZERO, al livello (b) il **99,1 %**. Solo al livello (c) — al best back
— c'e' davvero qualcuno davanti (mediana **9,3 EUR**, media 16,4; coda zero solo nel 4,5 %
dei casi). Questo spiega da solo la tabella §4: dove non c'e' coda davanti si e' primi, e
si viene abbinati quando passa traffico; al best back si e' ultimi.

---

## 4. Quanto spesso si viene abbinati, e dopo quanto

IC 95 % con **bootstrap a grappolo sulle PARTITE** (4.000 ricampionamenti): gli ordini della
stessa partita non sono indipendenti.

| livello | ordini piazzati | abbinati | **% abbinati** | IC 95 % (grappolo) | attesa mediana |
|---|---:|---:|---:|---|---:|
| **a** — un tick sotto il best lay | 337 | 38 | **11,3 %** | 3,8 % – 20,3 % | **74 s** |
| **b** — mid dello spread | 352 | 36 | **10,2 %** | 3,6 % – 18,4 % | **76 s** |
| **c** — al best back | 355 | 6 | **1,7 %** | 0,3 % – 3,5 % | **97 s** |

Attesa complessiva degli 80 abbinati: mediana **80 s**, minimo 6 s, massimo 713 s.

**Come muore chi non si abbina** (livello a / b / c):

| morte | a | b | c |
|---|---:|---:|---:|
| sospensione in gioco | 118 | 125 | 150 |
| fine finestra | 126 | 135 | 139 |
| gol (punteggio cambiato) | 40 | 41 | 45 |
| registrazione finita | 15 | 15 | 15 |
| **abbinato** | **38** | **36** | **6** |

> Il 35-42 % degli ordini appoggiati muore per **sospensione**: su un Correct Score in gioco
> il mercato si ferma continuamente, e ogni fermata cancella l'ordine LAPSE. E' la ragione
> strutturale per cui l'ingresso passivo su questo mercato e' difficile, e non dipende dal
> prezzo scelto.

### 4.1 Per mercato

| mercato | livello | piazzati | abbinati | % abbinati | attesa mediana |
|---|---|---:|---:|---:|---:|
| CORRECT\_SCORE (2T) | a | 214 | 26 | 12,2 % | 52 s |
| CORRECT\_SCORE (2T) | b | 225 | 25 | 11,1 % | 61 s |
| CORRECT\_SCORE (2T) | c | 228 | 4 | 1,8 % | 83 s |
| HALF\_TIME\_SCORE (1T) | a | 123 | 12 | 9,8 % | 121 s |
| HALF\_TIME\_SCORE (1T) | b | 127 | 11 | 8,7 % | 102 s |
| HALF\_TIME\_SCORE (1T) | c | 127 | 2 | 1,6 % | 144 s |

---

## 5. Quanto prezzo si guadagna

Mediane su tutti i candidati; il «guadagno» e' quello che conta per un lay: un prezzo piu'
basso alza la `p_implicita`, cioe' alza il k a parita' di frequenza reale.

| livello | tick guadagnati (mediana) | guadagno assoluto di `p_implicita` | **guadagno RELATIVO** (mediana) | idem, sui soli abbinati |
|---|---:|---:|---:|---:|
| **a** | 1 | +0,0010 | **+6,3 %** | +5,9 % |
| **b** | 3 | +0,0027 | **+16,7 %** | +11,4 % |
| **c** | 6 | +0,0076 | **+42,9 %** | +34,0 % |

### 5.1 Il conto che decide tutto

`K_MISURATO` misura, sulle quote pre-match, **k ~ 0,80** al prezzo di lay (media delle
fasce operative del CS). Per un lay:

| obiettivo | aumento di `p_implicita` necessario | il livello che ci arriva |
|---|---:|---|
| k da 0,80 a **1,00** (solo pareggio, EV zero) | **+25 %** | (c), e solo lui — (a) e (b) no |
| k da 0,80 a **2,00** (il cancello di V3) | **+150 %** | **nessuno** |

> Il livello (a) — quello che si abbina 11 volte su 100 — vale **+6 %**: non copre neppure
> un quarto della strada verso il pareggio. Il livello (c) — che varrebbe **+43 %**, cioe'
> porterebbe k da 0,80 a ~1,14, ancora sotto il cancello di 2 — si abbina **1,7 volte su
> 100**. **I due estremi della stessa leva sono entrambi insufficienti, e per ragioni
> opposte.**

---

## 6. k al tocco contro k passivo (con intervalli)

Bootstrap a grappolo sulle partite, 4.000 ricampionamenti, commissione 5 %.

### 6.1 Al tocco, su TUTTE le celle candidate (e' quello che Omega fa oggi, in gioco)

| celle | partite | uscite | `p_impl` media | frequenza reale | **k** | IC 95 % di k | EV / 1 EUR |
|---:|---:|---:|---:|---:|---:|---|---:|
| 293 | 20 | 12 | 0,0201 | **0,0410** | **0,49** | 0,25 – 1,62 | **−0,98 EUR** |

Per fascia (stessi secchi di `K_MISURATO`):

| mercato | fascia | celle | partite | uscite | `p_impl` | `p_reale` | k | k prudente |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Correct Score | 0,5-1 % | 20 | 10 | 0 | 0,0086 | 0,0000 | — | — |
| Correct Score | 1-2 % | 99 | 16 | 3 | 0,0136 | 0,0303 | 0,45 | 0,16 |
| Correct Score | 2-5 % | 75 | 15 | 8 | 0,0316 | 0,1067 | 0,30 | 0,15 |
| Half Time Score | 0,5-1 % | 16 | 12 | 0 | 0,0086 | 0,0000 | — | — |
| Half Time Score | 1-2 % | 44 | 15 | 0 | 0,0135 | 0,0000 | — | — |
| Half Time Score | 2-5 % | 39 | 16 | 1 | 0,0328 | 0,0256 | 1,28 | 0,38 |

> **Il book in gioco e' peggiore di quello pre-match, come `K_MISURATO` §5.3 temeva.** Al
> tocco, sulle celle in cui Omega opererebbe davvero (in gioco, in banda, a due gol di
> distanza), k complessivo e' **0,49** contro lo 0,8-0,98 misurato pre-match. Con 12 uscite
> su 20 partite l'intervallo e' enorme — non e' un verdetto, e' un avvertimento.

### 6.2 Passivo contro tocco, **sulle stesse celle** (gli 80 abbinati)

| | celle | partite | uscite | `p_impl` media | frequenza reale | **k** | IC 95 % di k | EV / 1 EUR |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| **al prezzo PASSIVO ottenuto** | 78 | 8 | 8 | 0,0278 | 0,1026 | **0,27** | 0,16 – 2,61 | −2,56 EUR |
| **al tocco, stesse celle** | 78 | 8 | 8 | 0,0246 | 0,1026 | **0,24** | 0,14 – 2,31 | −3,02 EUR |

Il passivo **migliora** k del **+13 %** (0,24 -> 0,27) — coerente con il §5, visto che gli
abbinamenti arrivano quasi tutti dai livelli (a) e (b), che valgono +6 % e +11 % — ma parte
da un punto disastroso e ci resta. **Il dettaglio per fascia e' nel JSON
(`passivo.righe`); nessuna riga raggiunge le 30 celle abbinate con esito, quindi nessuna e'
marcata `misurabile: true`.**

---

## 7. Selezione avversa — misurata, e c'e'

Tre numeri, tutti sugli 80 abbinati:

| | valore | definizione operativa |
|---|---:|---|
| **frequenza di uscita delle celle ABBINATE** | **10,3 %** (8 su 78) | il risultato bancato e' poi uscito davvero |
| frequenza di uscita di TUTTE le celle candidate | **4,1 %** (12 su 293) | lo stesso conto sull'insieme di partenza |
| **rapporto** | **2,5x** | chi ci prende l'ordine sceglie le celle che escono |

| | valore | definizione operativa |
|---|---:|---|
| **abbinati «perche' il mercato ci e' passato attraverso»** | **27,5 %** (22 su 80) | entro 60 s dal fill il best `availableToLay` del runner e' sceso **sotto** il nostro prezzo abbinato |
| **abbinati subito prima di un gol** | **10,0 %** (8 su 80) | il fill e' avvenuto entro 120 s da un cambio di punteggio o da una sospensione in gioco |

Per livello: attraversati **34,2 %** (a), **19,4 %** (b), **33,3 %** (c); pre-gol **10,5 %**
(a), **11,1 %** (b), **0 %** (c).

> E' il meccanismo, non un'opinione: l'ordine appoggiato viene preso **quando conviene
> all'altro**. Le celle che restano appese fino alla fine finestra sono quelle su cui
> nessuno voleva la controparte; quelle che si riempiono sono quelle che il mercato stava
> gia' rivalutando. Il 2,5x di frequenza reale e' la stessa cosa vista sull'esito.

---

## 8. EV per 1 EUR di stake — al tocco contro passivo

`EV = 0,95 · (1 − 1/k)`.

| | k | **EV per 1 EUR** |
|---|---:|---:|
| al tocco, tutte le celle candidate in gioco (§6.1) | 0,49 | **−0,98 EUR** |
| al tocco, sulle celle poi abbinate passivamente (§6.2) | 0,24 | **−3,02 EUR** |
| passivo, al prezzo ottenuto (§6.2) | 0,27 | **−2,56 EUR** |
| *(riferimento pre-match, `K_MISURATO` §3)* | *0,80* | *−0,24 EUR* |
| *(cancello di V3)* | *2,00* | *+0,475 EUR* |

Il passivo migliora l'EV di **+0,46 EUR** rispetto al tocco **sulle stesse celle** — ma
quelle celle sono esattamente quelle sbagliate (§7), e restano a EV fortemente negativo.

---

## 9. Che cosa NON dice questa misura

1. **Non dice che l'ingresso passivo e' inutile.** Dice che, con **questa** griglia di
   candidati (banda 20-120, distanza 2 gol, finestre 20-40' e 50-80') e su **queste** 39
   registrazioni, il guadagno di prezzo ottenibile e' troppo piccolo dove si abbina e la
   probabilita' di abbinarsi e' troppo bassa dove il guadagno sarebbe grande. Una griglia
   diversa (quote piu' basse, spread piu' larghi, mercati piu' liquidi, finestre diverse) e'
   una misura che non e' stata fatta.
2. **Non e' un verdetto su k.** 8 partite e 8 uscite fra gli abbinati; 20 partite e 12 uscite
   al tocco. Gli intervalli a grappolo vanno da 0,14 a 2,6: contengono sia «disastro» sia
   «ottimo». **Solo la percentuale di abbinamento e il miglioramento di prezzo (§4 e §5)
   hanno un campione decente**, perche' non dipendono dagli esiti.
3. **Non misura un ordine che si sposta.** Qui l'ordine viene appoggiato una volta e lasciato
   li' fino alla morte. Un ingresso passivo vero probabilmente **riprezza** (segue il book,
   rientra dopo la sospensione, alza il prezzo quando il tempo stringe). Quella e' una
   strategia, e non e' stata misurata: `LEG_RETRY_MAX` e il riprezzo non esistono in questa
   misura.
4. **Non misura il nostro impatto sul mercato.** Un ordine da 1,00 EUR non muove niente, ma
   nemmeno viene notato: con stake piu' grandi la coda davanti e la selezione avversa
   cambiano, e non in meglio.
5. **Non tiene conto del costo-opportunita' completo.** Un ordine appoggiato che non si
   abbina non costa soldi, ma occupa una gamba: se Omega aspetta e non entra, quella partita
   e' persa. Il confronto «FOK sempre» contro «passivo 11 % delle volte» va fatto a livello
   di **giornata**, non di singola cella, e qui non c'e'.
6. **Non c'e' il place-and-trim, ne' il minimo di giurisdizione .it.** Su flumine il place e'
   diretto (LIMITE 3 del banco comune). Con 1,00 EUR di stake la cosa non morde, ma va detta.
7. **Gli esiti mancano per 24 mercati su 73.** Il `marketDefinition` finale con il WINNER non
   c'e' quando la registrazione finisce prima del settlement (e' il limite gia' noto di
   `validate_recordings`). Quelle celle sono **scartate**, mai contate come «non uscite»:
   contarle gonfierebbe k dalla parte sbagliata.
8. **Non tiene conto della latenza di cancellazione.** Le morti per sospensione e per gol qui
   sono istantanee. In produzione l'ordine muore comunque (LAPSE lo cancella Betfair), quindi
   la direzione e' giusta, ma il conto esatto dei book di margine non e' stato misurato.
9. **Il ramo `simulation_available_prices` e' spento.** Se il book scende sotto il nostro
   prezzo senza che passi volume scambiato, qui non si viene abbinati. E' la scelta prudente:
   accendendolo la percentuale di abbinamento salirebbe, e con essa la selezione avversa
   (§7), perche' quegli abbinamenti sono per costruzione quelli in cui il mercato ci e'
   passato attraverso.
10. **Un solo ordine per volta, e nessuna interazione fra i nostri ordini.** Ogni candidato e'
    un controfattuale isolato (§2.4). In produzione Omega piazza una gamba per partita, quindi
    la cosa e' realistica; ma i numeri dei tre livelli **non si sommano**: sono tre mondi
    alternativi, non tre ordini contemporanei.

---

## 10. Riproducibilita' e falsificazione

```
# la misura (27 minuti sulle 39 registrazioni)
python -m Betfair.omega.tools.misura_ingresso_passivo

# una sola registrazione, griglia dei minuti piu' fitta
python -m Betfair.omega.tools.misura_ingresso_passivo --eventi 35777617 --passo-minuti 2

# i test, compresa la falsificazione della regola della coda
python -m pytest Betfair/omega/tests/test_ingresso_passivo_2026_09_17.py -q
```

**La falsificazione.** Il banco di test costruisce un book sintetico con le **identiche
chiavi dello stream vero** (`op`/`pt`/`mc`/`id`/`marketDefinition`/`rc`/`atb`/`atl`/`trd`/
`tv`/`ltp`) e lo fa parsare dal **parser vero** di flumine (`HistoricListener`); un test di
contratto verifica che ogni chiave del finto compaia davvero in `_live_raw`. Poi:

* `test_si_abbina_quando_il_volume_arriva_dopo_e_davanti_non_c_e_nessuno` — coda davanti
  zero, 40 EUR scambiati dopo l'arrivo: **deve** abbinarsi;
* `test_non_si_abbina_se_davanti_c_era_gia_la_coda` — 100 EUR gia' in coda a quel prezzo,
  40 EUR scambiati dopo: **non deve** abbinarsi (`_piq` scende a 80);
* `test_non_si_abbina_se_il_volume_era_gia_stato_scambiato_prima_di_noi` — 200 EUR scambiati
  **prima** del nostro arrivo, poi nulla: **non deve** abbinarsi;
* `test_falsificazione_ignorare_la_coda_gia_presente_fa_abbinare` e
  `test_falsificazione_contare_il_volume_assoluto_invece_del_delta_fa_abbinare` — rompendo
  la regola, gli stessi casi si abbinano.

E il rosso e' stato **verificato di persona**: sostituendo
`SimulatedOrder._calculate_process_traded` con una versione che ignora `_piq`, la suite
diventa `1 failed, 17 passed` e il test che cade e' esattamente
`test_non_si_abbina_se_davanti_c_era_gia_la_coda`.

---

## 11. Che cosa questa misura consegna a chi decide

* La strada (ii) del §1 del `REFERTO_V3` — «entrare passivamente invece di attraversare lo
  spread» — **su queste registrazioni non recupera il bias**: il prezzo che si guadagna
  dove si abbina vale +6 %, e ne servirebbero +25 % solo per il pareggio.
* Il fattore che la strozza non e' il prezzo, e' la **vita dell'ordine**: il 35-42 % muore
  per sospensione e il 37-39 % per fine finestra. Un ingresso passivo che valga qualcosa
  deve prima risolvere **quello** (riprezzo, rientro dopo la sospensione, finestre piu'
  lunghe), e nessuna di quelle cose e' stata misurata qui.
* La **selezione avversa e' reale e quantificata** (2,5x sulla frequenza di uscita): va messa
  nel conto di qualunque progetto di ingresso passivo, non scoperta dopo.
* Resta vero cio' che diceva `K_MISURATO` §5.2: **il cancello k = 2 non si tocca**, e anzi
  in gioco il prezzo al tocco e' peggiore che pre-match (k 0,49 contro 0,80), con l'avvertenza
  che l'intervallo e' larghissimo.
