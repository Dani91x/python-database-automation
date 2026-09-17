# M1-BIS — LA POLITICA V4 (quota viva) misurata sulle registrazioni vere

> 17/09/2026. M1 (`INGRESSO_PASSIVO_MISURA_2026-09-17.md` §11) diceva: l'unica speranza
> dell'ingresso passivo non e' il prezzo, e' la **vita dell'ordine** — riprezzo, rientro
> dopo la sospensione, finestre piu' lunghe. Qui quella vita e' stata costruita e misurata.
>
> Riproducibile: `python -m Betfair.omega.tools.misura_ingresso_passivo --politica v4`
> Codice: `Betfair/omega/tools/misura_ingresso_passivo.py` (modalita' `--politica v4`)
> Dati versionati: `Betfair/omega/data/politica_v4_2026-09-17.json` (aggregati, diagnostica
> per registrazione e gli 11 fill) + `politica_v4_2026-09-17_quote.json.gz` (tutte e
> 13.281 le quotazioni, riga per riga)
> Test + falsificazione: `Betfair/omega/tests/test_politica_v4_2026_09_17.py`
>
> **Nessuna strategia di produzione toccata**, nessuna scrittura di database, nessun
> processo nuovo, nessun commit. E' uno strumento di misura.
>
> **Seguito**: `M1TER_QUOTA_VIVA_BEST_BACK_2026-09-17.md` rifa' la stessa politica col
> prezzo di riserva preso dal **bias di fascia misurato** invece che dal modello.

---

## 0. La risposta, in cinque righe

1. **La quota viva non si abbina quasi mai: 11 fill su 13.281 quotazioni emesse (0,08 %).**
   Nella variante a una cella (A) e' **un fill solo** su 973 quotazioni e 34 gambe.
2. **Il motivo non e' lo spread, e' la distanza.** Il prezzo di riserva `L*` del modello a
   k = 2 sta, in mediana, a **1/2,63 del miglior lay di mercato** — cioe' **21-84 tick sotto**.
   Non e' una quota «dentro lo spread»: e' una quota in un altro quartiere del book.
3. **Il mercato, al suo prezzo, offre k = 0,70** (mediana su 11.530 osservazioni
   cella x istante; 0,57-0,59 dentro la banda 20-120). **Solo lo 0,16 % delle celle
   candidate ha k >= 2 al prezzo del book.** E' la stessa risposta di `K_MISURATO`
   (k ~ 0,8 pre-match) e di M1 (k = 0,49 in gioco), ottenuta per una terza strada
   indipendente: qui la probabilita' la mette il **modello V3**, non la frequenza storica.
4. **«Il tempo e' dalla nostra parte» non chiude il divario.** Senza gol `L*` sale, ma il
   prezzo di mercato della cella sale con lui: la superficie fill% x minuto e' **0,0 % in
   quasi ogni fascia**, dal 1' all'89'.
5. **Il paniere aumenta i fill ma non li rende utili**, e costa: B5 porta le gambe con almeno
   un fill dal 2,9 % (A) al **5,9 %** al prezzo di **144 quotazioni per gamba**, cioe'
   ~11.550 piazzamenti+annulli in un giorno da 20 partite.

> Con 11 fill e **zero** celle uscite, **k realizzato e P&L non sono misurabili**. Tutto
> quello che segue su P&L e drawdown va letto come «non pervenuto», non come «positivo».

---

## 1. La politica simulata

Esattamente quella del brief e di `VISIONE_OMEGA_V4_COORDINATORE_2026-09-17.md` §2/§4/§9.

| | |
|---|---|
| finestre | gamba HT (HALF\_TIME\_SCORE) **1'-44'**, gamba FT (CORRECT\_SCORE) **46'-89'** |
| cella ammissibile | scoreline raggiungibile, a **>= 2 gol** dal punteggio (`v3_distanza_minima_gol`), mai la corrente ne' le adiacenti, mai una gia' impossibile; aggregati mai |
| modello | `omega_v3.probabilita_selezioni` (**quello di produzione**), parametri vincenti del banco (`data/parametri_vincenti_2026-09-16.json`: gamma-Poisson, gol\_totali 2,768, quota\_casa 0,564) |
| `p_sup` | `p_centro x 1,25` — **dichiarato**: con una sola fonte di lambda non esiste una SE per cella |
| prezzo di riserva | `L* = (1-c)/(p_sup x k) + c` con `c = 5 %`, `k = 2`; arrotondato al tick **verso il basso** (un tick sopra `L*` sarebbe margine sotto soglia) |
| se `best lay <= L*` | si **prende** al tocco: FOK a `L*`, col bet delay (`place_latency + betDelay`) |
| altrimenti | si **appoggia** a `min(L*, best lay - 1 tick)` |
| isteresi | la quota si sposta solo se il prezzo obiettivo cambia di **>= 1 tick** o la cella esce dalle migliori; **annullo con latenza 300 ms** e nuovo ordine al giro dopo: **mai due vivi** sulla stessa cella |
| sospensione | ordine morto (LAPSE, come oggi); **rientro 20 s dopo la riapertura**, ricalcolando tutto sul punteggio nuovo |
| fine finestra | annullo |
| dimensione | **liability fissa 30 EUR/gamba**: `s = 30/(L-1)`, arrotondata **per difetto** al centesimo |
| ordinamento | **EV per unita' di liability**: `(1-c)(1-1/k)/(L-1)` |
| cadenza | **10 s di tempo di mercato** (il brief lo consente: «o ogni 10 s se troppo») |
| uscite | si tiene **fino al regolamento**; la chiusura al 44'/89' e' registrata a parte e **non entra nel P&L** |

**Varianti** (mondi indipendenti, tutti nello stesso replay, ognuno col suo isolamento per
ordine come in M1):

| variante | celle quotate insieme | dimensione | banda di prezzo |
|---|---:|---|---|
| **A** | 1 | liability 30 EUR | nessuna |
| **B3** | 3 (paniere) | liability 30 EUR | nessuna |
| **B5** | 5 (paniere) | liability 30 EUR | nessuna |
| **A\_stake1** | 1 | **stake 1,00 EUR** | nessuna |
| **A\_coda** * | 1 | liability 30 EUR | **20-120** |
| **B5\_coda** * | 5 (paniere) | liability 30 EUR | **20-120** |

\* Le due varianti `_coda` **non sono nel brief**: sono una sensibilita' aggiunta da questa
misura e dichiarata. Servono perche' l'ordinamento per EV/liability, **con k incollato alla
soglia**, e' monotono decrescente in `L` e quindi sceglie **sempre** la cella ammissibile
con la quota piu' bassa: senza banda, la variante A quota a un prezzo mediano di **2,1** —
cioe' esce dalla coda, che e' l'identita' di Omega e il posto dove il bias vive
(`K_MISURATO` §4: k\_equo 1,53 sul CS 0,5-1 %). Il §4 della visione lo prevede
(«favorisce le quote basse... il compromesso lo fa Kelly») ma **Kelly non c'e'**: finche'
non c'e', l'ordinamento e' degenere. Vedi §7.1.

### 1.1 Il paniere

Cap di **caso peggiore** `max_j [ s_j (L_j - 1) - somma_{i != j} s_i (1-c) ] <= 30 EUR`
(le scoreline di un mercato sono mutuamente esclusive). Il paniere resta quotato finche'
quel massimo resta sotto il cap; **tutti i fill contano**, non solo il primo.

### 1.2 Che cosa NON e' cambiato rispetto a M1

La catena (`banco_comune.replay_evento` -> scanner vero -> riga di scan -> minuto e
punteggio dal sidecar IPS) e il **matching**: sempre
`flumine.simulation.simulatedorder.SimulatedOrder` 2.13.11 con la coda `_piq`, il delta di
`trd` da `RunnerAnalytics`, `simulation_available_prices=False` e isolamento per ordine.
La regola della coda e' descritta per esteso in `INGRESSO_PASSIVO_MISURA_2026-09-17.md` §2
e non e' stata toccata.

### 1.3 I lambda: da dove vengono, e quante volte non ci sono

`omega_model.lambdas_from_pre_ko(payload["pre_ko"])` — il **gradino 3** della catena vera
di `omega_service._prematch_lambdas`: le quote 1X2 **pre-KO congelate dallo scanner**. I
gradini 1-2 e 4 vogliono il database (che nel replay non esiste) e il gradino 5 (O/U live)
non e' pre-partita. **Senza lambda non si quota**: mai a occhi chiusi.

> **17 registrazioni su 39 non hanno il `pre_ko`** — sono quelle che cominciano a partita
> gia' in corso, e lo scanner congela il riferimento 1X2 solo prima del fischio
> (`safe_strategy/scanner.freeze_pre_ko`). Su quelle la politica non emette **nessuna**
> quota. Restano **22 registrazioni utili**, di cui 21 con almeno una quota.

---

## 2. I dati

| | |
|---|---|
| registrazioni lette | **39** (le stesse di M1), **0 errori di replay** |
| con lambda pre-KO utilizzabili | **22** |
| con almeno una quota | **21** |
| gambe quotate | **32-34** per variante (su 42 possibili: 21 eventi x 2) |
| quotazioni emesse (tutte le varianti) | **13.281** |
| sospensioni in gioco viste | **196**, con **145 rientri** dopo il riassestamento |
| ordini abbinati | **11** |
| mercati col WINNER nel `marketDefinition` finale | **49 su 73** |
| durata del giro completo | **914 s** (15 minuti) |

**Come muore una quotazione** (variante A / A\_coda / B5\_coda):

| morte | A | A\_coda | B5\_coda |
|---|---:|---:|---:|
| **annullata dal riprezzo** (isteresi o cambio di cella) | 887 | 930 | 2.392 |
| sospensione in gioco | 31 | 24 | 50 |
| gol (punteggio cambiato) | 14 | 11 | 24 |
| fine finestra | 17 | 9 | 16 |
| registrazione finita | 5 | 4 | 9 |
| FOK senza controparte | 0 | 2 | 2 |
| **abbinata** | **1** | **1** | **4** |

> Il 92-95 % delle quotazioni muore perche' **la politica stessa la sposta**. La quota e'
> viva, vivissima; e' il mercato che non la tocca.

---

## 3. Il numero che spiega tutto: quanto e' lontano il prezzo di riserva

| variante | osservazioni | **best lay / `L*`** (mediana) | q1 - q3 | tick fra la quota e il best lay (mediana) |
|---|---:|---:|---|---:|
| A (nessuna banda) | 916 | **2,63** | 2,38 - 3,03 | **84** |
| A\_coda (20-120) | 816 | **3,53** | 2,70 - 4,60 | **22** |
| B5\_coda (20-120) | 2.019 | **3,41** | 2,57 - 4,59 | **21** |

**Quotazioni in cui il book offriva gia' un lay accettabile (`best lay <= L*`, quindi si
prende al tocco): 18 su 13.281 = 0,14 %.**
E 1.751 quotazioni su 13.281 (13 %) sono state emesse su celle che **non avevano nemmeno
un best lay**: il lato lay del book era vuoto.

Lo spread misurato in M1 e' di **6 tick** in mediana. Qui la distanza da colmare e' di
**21-84 tick**. **La quota passiva non sta «dentro lo spread»: sta a un ordine di grandezza
di distanza.** Nessun riprezzo colma un divario che non e' lo spread, ma il **requisito di
margine** stesso.

### 3.1 La stessa cosa detta in k

Con `p_implicita(best lay) / p_sup` — cioe' il margine che il mercato offre, secondo il
modello di produzione:

| variante | osservazioni | **k al tocco (mediana)** | q1 - q3 | quote con k >= 2 | EV/1 EUR al tocco |
|---|---:|---:|---|---:|---:|
| A | 916 | **0,75** | 0,65 - 0,82 | 0,11 % | −0,322 EUR |
| A\_coda | 816 | **0,57** | 0,43 - 0,74 | 0,25 % | −0,730 EUR |
| B5\_coda | 2.019 | **0,59** | 0,44 - 0,78 | 0,15 % | −0,671 EUR |
| **tutte le celle candidate** | **11.530** | **0,70** | | **0,16 %** | **−0,405 EUR** |

> **Terza misura indipendente, stessa risposta.** `K_MISURATO` (frequenza storica,
> pre-match): k ~ 0,8. M1 (frequenza reale sulle registrazioni, in gioco): k = 0,49. Qui
> (probabilita' del **modello V3**, in gioco, a ogni istante): k = 0,70. Il prezzo di lay
> che il mercato offre su queste celle e' **a EV negativo**, e lo dicono tre strade che non
> condividono ne' i dati ne' il metodo.

---

## 4. Risultati per variante

`k realizzato`, `P&L` e `drawdown` sono riportati per completezza ma **non sono
misurabili**: 11 fill, di cui **nessuno uscito** (0 su 11 celle bancate si e' verificata).
Tutti i P&L positivi sono il premio incassato su 11 lay che non sono uscite — rumore.

| variante | quote | gambe quotate | gambe con fill | % gambe con fill | fill | attesa mediana | prezzo medio ottenuto | P&L (EUR) | gambe nel P&L | DD max | quote per gamba |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **A** | 973 | 34 | 1 | **2,9 %** | 1 | 6 s | 1,9 | +20,64 | 1 | 0,00 | 28,6 |
| **B3** | 2.913 | 34 | 1 | 2,9 % | 1 | 6 s | 1,9 | +20,64 | 1 | 0,00 | 85,7 |
| **B5** | 4.909 | 34 | 2 | **5,9 %** | 3 | 6 s | 43,6 | +21,95 | 2 | 0,00 | 144,4 |
| **A\_stake1** | 973 | 34 | 1 | 2,9 % | 1 | 6 s | 1,9 | +0,95 | 1 | 0,00 | 28,6 |
| **A\_coda** | 993 | 32 | 1 | 3,1 % | 1 | 16 s | 36,0 | +0,81 | 1 | 0,00 | 31,0 |
| **B5\_coda** | 2.520 | 32 | 2 | 6,2 % | 4 | 22 s | 68,8 | +2,37 | 2 | 0,00 | 78,8 |

Per mercato (gambe con fill / gambe quotate):

| variante | CORRECT\_SCORE (2T) | HALF\_TIME\_SCORE (1T) |
|---|---|---|
| A · B3 · A\_stake1 | 0 / 15 | 1 / 19 |
| B5 | 1 / 15 | 1 / 19 |
| A\_coda | 0 / 14 | 1 / 18 |
| B5\_coda | 1 / 14 | 1 / 18 |

### 4.1 Gli undici fill, uno per uno (sei celle distinte)

| variante | mercato | cella | min. quota -> fill | modo | prezzo | `L*` | `p_sup` | size | liability | esito | P&L | attesa | attraversato | pre-gol |
|---|---|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---|---|
| A · B3 · B5 | HT | 2 - 2 | 30,0 -> 30,1 | tocco | 1,88 | 2,4 | 0,2037 | **21,73** | 19,12 | non uscita | +20,64 | 5,6 s | no | **si** |
| A\_stake1 | HT | 2 - 2 | 30,0 -> 30,1 | tocco | 1,88 | 2,4 | 0,2037 | 1,00 | 0,88 | non uscita | +0,95 | 5,6 s | no | **si** |
| B5 · B5\_coda | CS | 2 - 1 | 85,0 -> 85,1 | tocco | 29,0 | 29,9 | 0,0159 | 1,07 | 29,96 | non uscita | +1,02 | 5,7 s | no | no |
| B5 · B5\_coda | CS | 0 - 3 | 87,0 -> 87,4 | passivo | 100 | 108,6 | 0,0044 | 0,30 | 29,70 | non uscita | +0,29 | 26,5 s | no | **si** |
| B5\_coda | CS | 3 - 2 | 51,0 -> 62,0 | passivo | 110 | 111,6 | 0,0043 | 0,27 | 29,43 | non uscita | +0,26 | **661 s** | no | no |
| A\_coda · B5\_coda | HT | 2 - 2 | 7,0 -> 7,3 | passivo | 36,0 | 37,9 | 0,0126 | 0,85 | 29,75 | non uscita | +0,81 | 16,5 s | **si** | no |

**Selezione avversa** (stessa metrica di M1): su 11 fill, **2 attraversati** (il book e'
sceso sotto il prezzo abbinato entro 60 s) e **4 pre-gol** (abbinati entro 2 minuti da un
gol o da una sospensione). Il campione e' troppo piccolo per una quota: si riporta il conto
crudo, non una percentuale che fingerebbe precisione.

**Due fill sono reperti in se'**: il lay a **1,88** su «2 - 2» al 30' — che con la liability
fissa produce uno **stake di 21,73 EUR**, l'esatto opposto del problema dello stake sotto il
minimo (§7.3) — e il lay passivo a **110** con `p_sup` 0,43 %, riempito dopo **11 minuti** di
attesa. Sono due modi diversi di uscire dalla strategia: uno per l'ordinamento degenere del
§7.1, l'altro per l'eccesso di fiducia nella coda del modello (§7.2).

### 4.2 La chiusura al 44' / 89'

Registrata a parte, **non nel P&L**: in questo campione nessuna delle 11 posizioni aveva un
prezzo di back utilizzabile al minuto di chiusura. Il confronto col 12/09 (le chiusure
distruggono valore) resta **non falsificato e non confermato** da questa misura.

---

## 5. La superficie: fill% e k per minuto d'ingresso x fascia di `p_sup`

Tabella completa nel JSON (`superficie.righe`); le quotazioni riga per riga nel sidecar
compresso. La sintesi e' che **non c'e' superficie**:

* **variante A** (nessuna banda), **15** celle minuto x fascia: **una sola** diversa da zero
  (30-39' x `p_sup` > 10 %, **0,8 %**);
* **variante A\_coda** (banda 20-120), **30** celle: **una sola** (0-9' x 1-2 %, **1,2 %**);
* **variante B5\_coda**, **36** celle: **quattro** — 0-9' x 1-2 % (1,0 %), 50-59' x
  0,2-0,5 % (4,8 %), 80-89' x 0,2-0,5 % (2,2 %), 80-89' x 1-2 % (1,1 %);
* senza banda: B5 ha 3 celle non nulle su 53, B3 una su 40.

**`k` per cella della superficie e' sempre indeterminato** (0 uscite). Non esiste, su questi
dati, una zona di minuto o di probabilita' in cui la quota viva funzioni: **non c'e' un
ingresso «presto» che renda** (la §9.1 della visione), perche' dal 1' al 44' la fill% e'
zero quasi ovunque.

---

## 6. Quante gambe al giorno, e quanto costano

10 giorni di calendario coperti. Il tasso misurato e' **per partita**; il numero di partite
di un giorno tipo e' un'**assunzione dichiarata** (20), e serve solo a scalare.

| variante | gambe quotate / partita | gambe con fill / partita | fill / partita | gambe con fill in un giorno da 20 partite | fill / giorno | liability impegnata / giorno | **piazzamenti + annulli / giorno** |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 0,872 | 0,026 | 0,026 | **0,5** | 0,5 | 10 EUR | 2.290 |
| B3 | 0,872 | 0,026 | 0,026 | 0,5 | 0,5 | 10 EUR | 6.854 |
| B5 | 0,872 | 0,051 | 0,077 | **1,0** | 1,5 | 40 EUR | **11.550** |
| A\_stake1 | 0,872 | 0,026 | 0,026 | 0,5 | 0,5 | 0 EUR | 2.290 |
| A\_coda | 0,821 | 0,026 | 0,026 | 0,5 | 0,5 | 15 EUR | 2.482 |
| B5\_coda | 0,821 | 0,051 | 0,103 | 1,0 | 2,0 | 61 EUR | 6.300 |

> **La massivita' non c'e'**: la variante che il brief mette per prima (A, una cella) farebbe
> **mezza gamba al giorno**. La piu' aggressiva (B5) ne farebbe **una**, muovendo **11.550
> operazioni d'ordine al giorno** — un ordine di grandezza sopra la cadenza a cui questo
> repo ha mai lavorato, e da confrontare con i limiti di transazione di Betfair prima ancora
> che con l'EV.

---

## 7. Tre reperti che il coordinatore deve vedere

### 7.1 L'ordinamento per EV/liability, con k incollato alla soglia, e' DEGENERE

Quotando sempre **al** prezzo di riserva, `k` vale esattamente 2 per costruzione, quindi

```
EV / liability = (1 - c)(1 - 1/k) / (L - 1) = 0,475 / (L - 1)
```

e' una funzione **monotona decrescente di L**: l'ordinamento sceglie sempre la cella
ammissibile con la **quota piu' bassa**. Misurato: le varianti A e A\_stake1 quotano a un
prezzo mediano di **2,1** (minimo 1,37, massimo 12), e il loro «EV/liability medio» (0,46)
e' altissimo proprio perche' il denominatore e' piccolo. **Non e' Omega**: e' un bot che
banca «2 - 2» a quota 1,88 al 30'. Il §4 della visione lo prevede e rimanda a Kelly;
**finche' Kelly non c'e', o c'e' una banda, l'ordinamento non e' usabile**. Le varianti
`_coda` di questa misura (prezzo mediano 28 e 40) sono il tampone minimo.

### 7.2 Il modello, sulla coda estrema, autorizza qualunque prezzo

`p_sup` scende sotto lo 0,5 % su celle come «3 - 2» al 51', e `L*` sale oltre 110; nel
campione grezzo si arriva a `L*` di ordine 10.000 e a quotazioni a **1.000**. E' la stessa
famiglia di errore del §3.4 del progetto (optimizer's curse): dove il modello e' piu' sicuro
e' anche dove sbaglia di piu', e nessuno lo sta contraddicendo. Serve un **tetto di prezzo**
o un **pavimento su `p_sup`**, e non c'e'.

### 7.3 La liability fissa sbaglia da tutte e due le parti

`s = 30/(L-1)` a quota 110 vale **0,27 EUR**: sotto il minimo .it per un LAY (0,50 EUR) —
misurato, **27 %** delle quote di B5\_coda e **6 %** di quelle di A\_coda. Ma lo stesso
dimensionamento **a quota 1,88 produce uno stake di 21,73 EUR**, cioe' ventuno volte quello
di V3. In produzione il primo caso lo salverebbe il place-and-trim
(`omega_market.place_submin_live`), che su flumine **non esiste** (LIMITE 3 del banco); il
secondo non lo salva nessuno, ed e' una conseguenza diretta di §7.1.

---

## 8. Che cosa questa misura NON dice

1. **Non e' un verdetto su k o sul P&L.** 11 fill, **zero** celle uscite, 22 registrazioni
   utili: k realizzato e drawdown non esistono. Cio' che e' solido sono i numeri che **non
   dipendono dagli esiti**: la distanza `best lay / L*` (§3), il k al tocco secondo il
   modello (§3.1), la percentuale di fill (§4) e il costo operativo (§6).
2. **Non dice che la quota viva sia inutile in assoluto.** Dice che, con **k = 2**,
   `p_sup = 1,25 x p_centro` e **questo** modello, la riserva sta 2,6-3,5 volte sotto il
   mercato e non viene mai raggiunta. E' **una misura della distanza, non un teorema**:
   `M1TER_...` misura la stessa politica con un prezzo di riserva diverso.
3. **Non misura il vero ingresso «presto» della visione §9.1**, perche' 17 registrazioni su
   39 non hanno le lambda pre-KO e quindi il 1'-44' e' coperto solo da 22 partite. E dove e'
   coperto, la fill% e' quasi sempre zero.
4. **`p_sup` non e' una SE.** E' `p_centro x 1,25`, come chiesto dal brief. Un vero limite
   superiore (due stime indipendenti, `k_se`) sposterebbe `L*` e quindi tutto il resto.
5. **Le lambda vengono da un solo gradino della catena** (quote 1X2 pre-KO). La catena vera
   parte dalla fixture del database (tactical\_engine / Poisson xG-DC), che nel replay non
   c'e'. E' **M2** che deve dire quanto valgono le lambda.
6. **Nessun impatto di mercato.** Stake da 0,27 a 21,73 EUR: i primi non muovono niente ma
   non attirano nessuno; il secondo, a quota 1,88, in un book vero avrebbe un impatto — e
   qui non e' modellato.
7. **Nessun Kelly, nessun cap di partita/giorno, nessuno stop.** La visione §4 li prevede;
   qui c'e' solo il cap di caso peggiore per gamba. Con 11 fill non avrebbero morso.
8. **Cadenza 10 s, non a ogni tick.** Il brief lo consente; con una cadenza piu' fitta il
   riprezzo seguirebbe meglio il book, ma il divario del §3 e' di 21-84 tick e non si chiude
   con la reattivita'.
9. **L'annullo e' modellato come latenza (300 ms), non come rifiuto.** In produzione un
   annullo puo' fallire, e l'ordine puo' abbinarsi nel frattempo: qui puo' farlo (l'ordine
   resta a mercato fino alla scadenza della latenza), ma non puo' **fallire**.
10. **Esiti mancanti per 24 mercati su 73** (registrazione finita prima del settlement):
    quelle posizioni sono escluse dal P&L, mai contate come «non uscite».
11. **Il confronto con la chiusura al 44'/89' non esiste** in questo campione.

---

## 9. Riproducibilita' e falsificazione

```
# la misura (15 minuti sulle 39 registrazioni, 6 varianti in un solo passaggio)
python -m Betfair.omega.tools.misura_ingresso_passivo --politica v4

# una registrazione sola, cadenza piu' fitta, altra liability
python -m Betfair.omega.tools.misura_ingresso_passivo --politica v4 \
    --eventi 35777617 --cadenza-s 2 --liability 50 --k-soglia 1.5

# M1 resta com'era (nessun numero del 17/09 mattina e' cambiato)
python -m Betfair.omega.tools.misura_ingresso_passivo

# i test: M1 (19) + politica V4 (14) + M1-ter (16)
python -m pytest Betfair/omega/tests -q
```

**Il banco di prova** e' quello di M1: book sintetico con le **identiche chiavi dello stream
vero** (`op`/`pt`/`mc`/`id`/`marketDefinition`/`rc`/`atb`/`atl`/`trd`/`tv`/`ltp`), parsato
dal **parser vero** di flumine (`HistoricListener`), e `MercatoFinto` che espone gli stessi
due attributi che `MisuraV4` legge da un `flumine.markets.Market` (`context`, `flumine`) con
le analitiche VERE (`RunnerAnalytics`).

| test | che cosa pretende |
|---|---|
| `test_la_quota_sale_col_prezzo_di_riserva_e_si_abbina_all_incrocio` | book fermo, niente gol: su ogni cella la quota si muove **solo verso l'alto**, almeno una si muove, e **all'incrocio col mercato** si prende al tocco e si abbina a un prezzo `<= L*` |
| **`test_falsificazione_senza_riprezzo_il_fill_all_incrocio_non_avviene`** | con `RIPREZZO_ATTIVO = False` (la quota «appoggiata e dimenticata» di M1) lo stesso scenario emette una sola quota per cella e **non si abbina mai** |
| `test_la_sospensione_uccide_la_quota_e_il_rientro_aspetta_i_20_secondi` | la sospensione in gioco uccide la quota; per 20 s dopo la riapertura **non si quota**; poi si rientra **sul punteggio nuovo**, con la cella ricalcolata a >= 2 gol dal nuovo punteggio |
| **`test_falsificazione_senza_attesa_si_quota_dentro_il_riassestamento`** | con attesa 0 la quota rientra subito: il test qui sopra **sa diventare rosso** |
| `test_il_prezzo_quotato_non_supera_mai_il_prezzo_di_riserva` | per ogni quota, `p_implicita(prezzo)/p_sup >= k` |
| `test_il_paniere_non_supera_il_cap_di_caso_peggiore` | `max_j[...] <= 30 EUR` su posizioni + quote vive |
| `test_caso_peggiore_del_paniere` | la formula: 5 celle a quota 100 con stake 1 -> `99 - 4 x 0,95`, **non** 5 x 99 |
| `test_mai_due_ordini_vivi_sulla_stessa_cella` | una quota per cella, al massimo `n` per mondo |
| `test_dimensione_a_liability_fissa` | `s = 30/(L-1)` arrotondata per difetto; la liability non supera mai 30 |
| `test_i_lambda_vengono_dalla_catena_vera_e_senza_di_essi_non_si_quota` | `lambdas_from_pre_ko` e il silenzio senza lambda |
| `test_la_variante_di_coda_resta_in_banda_quella_libera_no` | il reperto §7.1, inchiodato a un test |

**Il rosso e' stato verificato di persona** anche sul matching (M1): sostituendo
`SimulatedOrder._calculate_process_traded` con una versione che ignora `_piq`, la suite
diventa `1 failed, 17 passed` e cade esattamente
`test_non_si_abbina_se_davanti_c_era_gia_la_coda`.

---

## 10. Che cosa consegna questa misura a chi decide

* **La strada (ii) del `REFERTO_V3` §1 — entrare dentro lo spread — resta chiusa anche con
  la quota viva, se il prezzo lo fissa il modello.** M1 aveva mostrato che il prezzo
  guadagnato appoggiandosi vale +6 % (livello a) e ne servono +25 % per il pareggio. M1-bis
  mostra **perche'** il riprezzo non colma la differenza: il prezzo di riserva a k = 2 non e'
  un tick sotto il mercato, e' **2,6-3,5 volte** sotto.
* **Il divario e' il margine, non lo spread.** Finche' `k_soglia = 2` e il modello dice
  quello che dice, non esiste politica di esecuzione che chiuda un fattore 2,6. Le leve che
  restano sono **due**: (i) un `p_sup` piu' basso — cioe' un modello che veda la coda davvero
  piu' rara del mercato, ed e' quello che **M2** deve dimostrare sulle lambda; (ii) un prezzo
  di riserva che non venga dal modello ma dal **bias di fascia misurato** — ed e' esattamente
  cio' che `M1TER_QUOTA_VIVA_BEST_BACK_2026-09-17.md` misura.
* **Prima di qualunque altro esperimento di esecuzione, vanno chiusi i tre reperti del §7**
  (ordinamento degenere, nessun tetto di prezzo sulla coda estrema, liability fissa che
  sbaglia da entrambe le parti): sono difetti della politica, non del mercato, e falserebbero
  ogni misura futura.
* **Il costo operativo va messo nel progetto adesso**: 2.300-11.550 operazioni d'ordine al
  giorno non sono un dettaglio implementativo, sono un vincolo di Betfair.
