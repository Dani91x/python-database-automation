# M1-TER — LA QUOTA VIVA AL PREZZO DEL BIAS DI FASCIA (17/09/2026)

> La misura che `M4M5M6_2026-09-17.md` §6-bis.4 dichiara **bloccante**: né M1 (ordini
> discreti al miglior back) né M1-bis (quota viva al prezzo del modello) avevano tenuto una
> **quota viva al miglior back**, col margine preso dal **bias di fascia misurato** invece
> che da un `k` di modello.
>
> Riproducibile: `python -m Betfair.omega.tools.misura_ingresso_passivo --politica v4ter`
> Codice: `Betfair/omega/tools/misura_ingresso_passivo.py` (modalità `--politica v4ter`)
> Dati: `Betfair/omega/data/quota_viva_bias_fascia_2026-09-17.json`
> + `quota_viva_bias_fascia_2026-09-17_quote.json.gz` (36.118 quotazioni riga per riga)
> Test + falsificazione: `Betfair/omega/tests/test_quota_viva_bias_fascia_2026_09_17.py`
>
> **Nessuna strategia di produzione toccata**, nessuna scrittura di database, nessun
> processo nuovo, nessun commit.

---

## 0. IL CRITERIO DI ARRESTO, IN TESTA, COI MIEI NUMERI

Il criterio di `M4M5M6` §0: *selezione avversa sopra **1,27** ⇒ V4 non si costruisce.*

| che cosa | valore misurato | IC 95 % a grappolo | verdetto |
|---|---:|---|---|
| selezione avversa sui fill **PASSIVI**, best back +1 tick | **1,77** | 0,00 – 3,76 | **sopra soglia**, IC non conclusivo |
| selezione avversa sui fill **PASSIVI**, best back +3 tick | **2,50** | 0,00 – 7,16 | **sopra soglia**, IC non conclusivo |
| selezione avversa su **tutti** i fill, +1 tick | 1,25 | 0,00 – 2,81 | indeciso |
| selezione avversa su **tutti** i fill, +3 tick | 0,65 | 0,00 – 1,48 | indeciso |
| **`k` realizzato sui fill passivi** | **0,26** (+1 tick) · **0,20** (+3 tick) | — | EV per 1 € = **−2,7 / −3,7 €** |
| P&L su 36 gambe, liability 30 €/gamba | **−38,48 €** (+1 tick) · **−21,39 €** (+3 tick) | — | negativo |
| drawdown massimo | **51,03 €** · **45,25 €** | — | 1,7× la liability di una gamba |

> ### Il criterio di arresto NON è risolto — e non perché manchi una misura, ma perché la finestra operativa non esiste.
> Con **2 uscite** fra i fill e **6** fra le 165 celle candidate, nessun intervallo su
> `k` o sulla selezione avversa può decidere. Ma **la domanda che M1-ter doveva chiudere
> ha una risposta netta e ben misurata**, e non è quella sperata:
>
> **Il margine di manovra sopra il miglior back è ZERO tick.**
> Il prezzo di riserva `L*_fascia` cade **esattamente sul miglior back** (mediana di 0 tick
> di distanza su 14.131 osservazioni). Salire di **1 tick** lascia sopra soglia solo il
> **43 %** delle quotazioni; di **3 tick**, il **32 %**. Non c'è la fascia di prezzo
> «qualche tick sopra il miglior back, sopra soglia e più facile da riempire» che
> `M4M5M6` §6-bis.3 punto 2 ipotizzava: **il miglior back È già il prezzo di riserva.**
>
> E al prezzo di riserva **la quota non si riempie**: **0,09 %** di fill (12 su 14.131
> quotazioni, 0,3 fill per partita). Tutto il fill in più delle varianti (b) e (c) si paga
> **rompendo il margine**, e i riempimenti che ne vengono sono o **prese al tocco**
> (dove M6 misura `k` = 0,45-0,53) o **fill passivi selezionati male** (`k` realizzato
> 0,20-0,26).

---

## 1. La politica, e le due modifiche dichiarate

Stesso strumento e stessa catena di M1-bis. Cambiano due cose, quelle chieste da §6-bis.4:

| | M1-bis | **M1-ter** |
|---|---|---|
| prezzo di riserva | `L* = (1−c)/(p_sup·k)+c`, `p_sup` dal **modello V3**, `k` = 2 | `L*_fascia = (1−c)/(p_equa·k_fascia)+c`, `p_equa` **devigata dal mercato**, `k_fascia` = **bias prudente misurato da M6** |
| ammissibilità | tutte le celle a ≥ 2 gol, HT e CS | **solo CORRECT\_SCORE**, e solo le fasce col bias dimostrato |
| finestra | HT 1'-44', FT 46'-89' | **1'-85'** sul solo Correct Score |
| modello | fissa il prezzo | **non entra**: `omega_v3.probabilita_selezioni` non viene mai chiamata (un test lo verifica) |
| lambda pre-KO | indispensabili (17 registrazioni su 39 escluse) | **non servono** → tutte e 39 le registrazioni entrano |

`k_fascia` è **letto dal file versionato di M6** (`data/k_in_gioco_aggregato_2026-09-17.json`,
campo `bias_equo_prudente`), non scritto qui. Le uniche due fasce col bias prudente > 1 sono
**Correct Score 0,5-1 % → 1,114** e **1-2 % → 1,110**; tutte le altre (comprese
CS 0,2-0,5 % a 0,975 e HT 2-5 % a 0,923) sono escluse per costruzione.

`p_equa` è la devigazione **identica a `tools/superficie_liability.py`**: mid dei due lati
normalizzato sui runner ATTIVI, niente devigazione sotto 6 selezioni prezzate su entrambi i
lati o con somma dei pesi ≤ 0,5, book incrociati scartati. Riuscita nell'**88,1 %** dei giri
di politica (53.896 su 61.155); **3 registrazioni su 39** non hanno mai un book devigabile.

### 1.1 Una divergenza dichiarata fra il brief e M6

Il brief chiede «ammissibilità ristretta a Correct Score con **`p_equa` in 0,5-2 %**». Ma
**M6 definisce le sue fasce sulla `p_implicita AL TOCCO`**, non su `p_equa`
(`tools/k_in_gioco.py`, righe 23-24): nella fascia M6 «0,5-1 %» la `p_equa` media vale
**1,48 %**, e nella «1-2 %» vale **2,12 %**. Le due letture selezionano celle diverse, e
`k_fascia` è misurato **solo** per la prima. Sono state quindi misurate **entrambe**:

* **`m6`** — fascia dalla `p_implicita` al tocco, ristretta a 0,5-1 % e 1-2 % (è la lettura
  per cui `k_fascia` esiste);
* **`pequa`** — la lettera del brief: `p_equa` fra 0,5 % e 2 %, sempre scartando le celle la
  cui fascia non ha un bias prudente > 1.

La differenza **non è cosmetica**: cambia il denominatore della selezione avversa e con esso
il fattore (§4.2). Va sciolta dal coordinatore.

### 1.2 I tre prezzi, e le altre regole

| variante | prezzo quotato |
|---|---|
| **a\_riserva** | esattamente `L*_fascia`, arrotondato al tick **verso il basso** |
| **b\_back1** | miglior back **+ 1 tick** |
| **c\_back3** | miglior back **+ 3 tick** (verso il mid) |

Se il prezzo voluto è già ≥ il miglior lay, si **prende al tocco** (FOK fino al limite) —
ed è un caso che conta molto, §3.2. Tutto il resto è M1-bis: liability fissa **30 €/gamba**
(`s = 30/(L−1)`, arrotondata per difetto), quota **viva** con riprezzo a ogni tick di scan
(cadenza **1 s** di tempo di mercato), isteresi di **1 tick**, annullo con latenza **300 ms**,
mai due ordini vivi sulla stessa cella, morte a sospensione / gol / cella impossibile / fine
finestra, **rientro 20 s** dopo la riapertura, matching di flumine con la coda `_piq` e il
delta di `trd`, isolamento per ordine.

**Si quotano tutte le celle ammissibili insieme** (dentro il cap di caso peggiore di 30 €),
non una sola: con 39 registrazioni una cella per gamba darebbe un campione troppo piccolo
per una selezione avversa con intervallo. È una scelta di misura, dichiarata.

---

## 2. I dati

| | |
|---|---|
| registrazioni | **39**, **0 errori di replay** |
| con almeno una quotazione | **36** |
| gambe quotate | **36** (regola `m6`) / **33** (regola `pequa`) |
| quotazioni emesse | **36.118** |
| ordini abbinati | **352** (di cui **105 passivi** e **247 presi al tocco**) |
| celle candidate distinte con esito noto | **165** (regola `m6`), con **6 uscite** |
| mercati col WINNER nel `marketDefinition` finale | **49 su 73** |
| sospensioni / rientri | 129 / 103 |
| durata | **949 s** (16 minuti) |

---

## 3. Dove cade il prezzo di riserva — la risposta a §6-bis.3 punto 2

### 3.1 Zero tick di manovra

| | valore |
|---|---|
| tick fra il **miglior back** e `L*_fascia` (positivo = riserva sopra il back) | **mediana 0**, q1 −1, q3 +2, media +2,9 |
| quotazioni con `L*_fascia` ≥ miglior back | **71 %** |
| `k` al **miglior back**, per cella | **mediana 1,14**, q1 1,07, q3 1,25 |
| celle in cui il miglior back offre `k` ≥ 1,11 | **60,9 %** |
| `k` al **tocco**, per cella | mediana **0,74** |

> `M4M5M6` §6-bis.3 stimava il margine al miglior back a **1,31-1,71** contro un requisito di
> 1,11, e ne deduceva «c'è margine di manovra». Quel numero è un **rapporto di medie**
> (`p_impl_best_back media / p_equa media`). Cella per cella il rapporto mediano è **1,14**:
> il margine c'è, ma è **appena** sopra il requisito, e in **4 celle su 10 non c'è affatto**.
> Di conseguenza il prezzo di riserva **coincide col miglior back**, e i tick di manovra
> sono **zero**.

### 3.2 Che cosa si compra salendo sopra il miglior back

| variante | quotazioni | `k` mediano al prezzo quotato | quote **sopra soglia** | **fill %** | fill |
|---|---:|---:|---:|---:|---:|
| **a\_riserva** | 14.131 | **1,140** | **100 %** | **0,09 %** | 12 |
| **b\_back1** | 5.014 | 1,088 | **43,1 %** | **1,16 %** | 58 |
| **c\_back3** | 3.202 | **1,003** | **32,3 %** | **3,47 %** | 111 |
| a\_riserva\_pequa | 9.066 | 1,144 | 100 % | 0,12 % | 11 |
| b\_back1\_pequa | 3.141 | 1,073 | 36,8 % | 1,75 % | 55 |
| c\_back3\_pequa | 1.564 | 0,983 | 21,8 % | 6,71 % | 105 |

> Il fill si compra **esattamente** con il margine: +1 tick moltiplica il fill per 13 e
> lascia sopra soglia meno della metà delle quotazioni; +3 tick lo moltiplica per 39 e ne
> lascia sopra soglia un terzo, con `k` mediano che scende a **1,00** — cioè EV zero prima
> ancora di parlare di selezione avversa.

### 3.3 E soprattutto: quei fill in più NON sono passivi

| variante | quotazioni **passive** | fill | fill % | quotazioni **al tocco** | fill | fill % |
|---|---:|---:|---:|---:|---:|---:|
| a\_riserva | 14.125 | 9 | **0,06 %** | 6 | 3 | 50,0 % |
| b\_back1 | 4.982 | 38 | **0,76 %** | 32 | 20 | 62,5 % |
| c\_back3 | 3.062 | 11 | **0,36 %** | 140 | 100 | 71,4 % |

> **247 dei 352 fill sono PRESE AL TOCCO**, non riempimenti passivi: sono i momenti in cui
> lo spread si chiude a 1-3 tick e il prezzo che volevamo era già disponibile. Sono, per
> definizione, ingressi da **taker** — quelli che M6 misura a `k` = 0,45-0,53 e che M1 e
> M1-bis avevano già bocciato. La quota viva, **come quota**, riempie lo **0,06-0,76 %**.

---

## 4. `k` realizzato e selezione avversa

### 4.1 `k` realizzato, separando passivi e prese

| variante | tipo di fill | n | partite | uscite | `p_impl` media | `p_reale` | **`k`** |
|---|---|---:|---:|---:|---:|---:|---:|
| b\_back1 | **passivo** | 31 | 10 | 2 | 0,0169 | 0,0645 | **0,262** |
| b\_back1 | tocco | 13 | 8 | 0 | 0,0153 | 0,0000 | — |
| c\_back3 | **passivo** | 11 | 7 | 1 | 0,0183 | 0,0909 | **0,202** |
| c\_back3 | tocco | 74 | 18 | 1 | 0,0150 | 0,0135 | 1,112 |

> I fill **passivi** — gli unici che la politica vuole davvero — hanno `k` realizzato
> **0,20-0,26**: la cella bancata è uscita **3-5 volte più spesso** di quanto il prezzo
> ottenuto dicesse. Su 31 e 11 celle con 2 e 1 uscite, è un indizio, non una sentenza; ma è
> **lo stesso indizio** che M1 misurava (k passivo 0,27 su 78 fill) e che M6 misura al
> tocco. Il `k` = 1,112 delle prese al tocco poggia su **1 uscita su 74** ed è rumore.

### 4.2 Selezione avversa — il numero che decide, e perché qui non decide

Unità = **cella distinta per gamba** (una cella riquotata 400 volte è una candidata, non
400: è il conto di M1 §7). IC 95 % con bootstrap a grappolo sulle **partite**, numeratore e
denominatore ricampionati **insieme**.

| variante | celle candidate | uscite | freq. | celle abbinate | uscite | freq. | **fattore** | IC 95 % | vs 1,27 |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| a\_riserva | 165 | 6 | 3,64 % | 10 | 0 | 0,00 % | **0,00** | 0,00 – 0,00 | sotto |
| b\_back1 | 165 | 6 | 3,64 % | 44 | 2 | 4,55 % | **1,25** | 0,00 – 2,81 | indeciso |
| c\_back3 | 165 | 6 | 3,64 % | 85 | 2 | 2,35 % | **0,65** | 0,00 – 1,48 | indeciso |
| **b\_back1, solo passivi** | 165 | 6 | 3,64 % | **31** | **2** | 6,45 % | **1,77** | 0,00 – 3,76 | **sopra** |
| **c\_back3, solo passivi** | 165 | 6 | 3,64 % | **11** | **1** | 9,09 % | **2,50** | 0,00 – 7,16 | **sopra** |
| b\_back1\_pequa | 130 | 2 | 1,54 % | 41 | 2 | 4,88 % | **3,17** | 2,03 – 5,45 | **sopra (arresto)** |
| c\_back3\_pequa | 130 | 2 | 1,54 % | 80 | 2 | 2,50 % | **1,62** | 1,36 – 2,02 | **sopra (arresto)** |
| c\_back3\_pequa (1-2 %) | 106 | 2 | 1,89 % | 69 | 2 | 2,90 % | **1,54** | 1,29 – 1,88 | **sopra (arresto)** |

**Tre letture, e vanno date tutte e tre.**

1. **Sui fill PASSIVI** — gli unici che contano per una politica di quotazione — il fattore
   è **1,77** e **2,50**, cioè sopra la soglia e in linea con il **2,5×** di M1. È la lettura
   che io ritengo pertinente.
2. **Su tutti i fill** (passivi + prese al tocco) il fattore scende a 1,25 e **0,65**: le
   prese al tocco *diluiscono* la selezione avversa, perché sono ingressi non selezionati.
   Ma sono anche gli ingressi con `k` ≈ 0,5-0,7: migliorare la selezione avversa prendendo
   al tocco è comprare un problema per risolverne un altro.
3. **Con l'ammissibilità `pequa`** il fattore sale a 1,62-3,17 con **IC interamente sopra
   1,27**. Non perché cambino gli abbinati (le uscite al numeratore sono le stesse 2) ma
   perché il **denominatore** perde 35 celle e 4 uscite: la frequenza di base scende da
   3,64 % a 1,54 %. **Il fattore è dominato dalla definizione della popolazione candidata**,
   ed è la ragione per cui §1.1 va sciolto prima di usare questo numero per decidere.

> **Numeratore: 2 uscite.** Qualunque intervallo costruito su due eventi è largo quanto la
> differenza fra «niente» e «disastro». Il fattore di selezione avversa **non è misurabile**
> con 39 registrazioni: servono, a occhio, dieci volte tante.

---

## 5. P&L e drawdown

| variante | gambe nel P&L | fill con esito | vinti | persi | **P&L** | P&L/gamba | **drawdown massimo** |
|---|---:|---:|---|---|---:|---:|---:|
| a\_riserva | 5 | 10 | 10 (+5,24 €) | 0 | **+5,24 €** | +1,05 € | 0,00 € |
| b\_back1 | 12 | 44 | 42 (+20,82 €) | **2 (−59,30 €)** | **−38,48 €** | −3,21 € | **51,03 €** |
| c\_back3 | 18 | 85 | 83 (+37,75 €) | **2 (−59,14 €)** | **−21,39 €** | −1,19 € | **45,25 €** |

Le due celle perse sono le stesse in tutte le varianti che riempiono: **«1 - 2» al 59'** e
**«3 - 2» al 51'-62'**. Con liability fissa a 30 € ciascuna costa −29,4/−29,9 €, mentre
ogni cella vinta rende **0,45-0,50 €**: **servono 60 celle vinte per pagarne una persa**, e
in questo campione ne sono arrivate 42 e 83. È il conto di `k` < 1, visto in euro.

> Il `+5,24 €` della variante (a) non è un risultato: sono 10 fill di cui **zero** usciti.
> Con 0,3 fill per partita quella variante non produce nemmeno abbastanza eventi per perdere.

**Chiusura al 85'**: nessuna posizione aveva un prezzo di back utilizzabile al minuto di
chiusura in questo campione — il confronto col 12/09 resta non misurato.

---

## 6. Costo operativo e minimi di giurisdizione

| variante | quotazioni per gamba | operazioni al minuto per gamba | in un giorno da 20 partite (20 gambe CS) |
|---|---:|---:|---:|
| a\_riserva | **393** | 4,7 | **~15.700 piazzamenti + annulli** |
| b\_back1 | 139 | 1,7 | ~5.600 |
| c\_back3 | 89 | 1,1 | ~3.600 |

**35 % delle quotazioni (12.476 su 36.118) avrebbe uno stake sotto il minimo .it (0,50 €)**:
è l'effetto della liability fissa a quote alte (a 110 lo stake è 0,27 €). In produzione le
salverebbe il place-and-trim, che su flumine non esiste (LIMITE 3 del banco): qui sono
contate, non applicate.

> La variante che rispetta il margine al 100 % (a) è anche quella che **riquota 393 volte per
> gamba**: il prezzo di riserva insegue `p_equa`, e `p_equa` si muove a ogni tick del book.
> Con l'isteresi a 1 tick il traffico verso Betfair è il vincolo prima ancora dell'EV.

---

## 7. Che cosa questa misura NON dice

1. **Non risolve il criterio di arresto.** 2 uscite fra gli abbinati, 6 fra le 165 candidate.
   Ogni IC sulla selezione avversa contiene 1,27 (o dipende dalla definizione della
   popolazione, §4.2). Il campione atteso dal brief — 12-25 uscite per fascia — è quello di
   **M6**, che guarda TUTTE le celle a ogni minuto; qui le uscite sono solo quelle delle
   celle **abbinate**, e sono due.
2. **Il fattore di selezione avversa dipende dal denominatore.** Le due ammissibilità danno
   1,77/2,50 e 3,17/1,62. Finché §1.1 non è sciolto, il numero non è confrontabile con la
   soglia in modo univoco.
3. **`k_fascia` poggia su 12 e 25 uscite** (M6 §6-bis.3 lo dichiara). Se il bias vero fosse
   1,0 invece di 1,11, il prezzo di riserva salirebbe di ~10 % e i fill aumenterebbero —
   ed è esattamente ciò che la falsificazione del §8 mostra.
4. **Niente modello, quindi niente veto.** In M1-ter il modello non entra: non c'è la
   funzione (c) di §6-bis.3 («veto quando è più pessimista del mercato»). Una politica vera
   lo avrebbe, e toglierebbe alcune delle celle che qui sono state quotate.
5. **Niente Kelly, niente cap di partita/giorno, niente stop giornaliero.** C'è solo il cap
   di caso peggiore per gamba.
6. **Si quotano tutte le celle ammissibili insieme.** Serve al campione; una politica vera
   ne quoterebbe poche, e con meno celle il P&L e il drawdown cambierebbero (in meglio o in
   peggio: non è misurato).
7. **La devigazione fallisce nell'11,9 % dei giri e in 3 registrazioni su 39**: dove il book
   è troppo sottile per devigare, questa politica **non può nemmeno formulare un prezzo**.
   È un limite strutturale, non un difetto di misura.
8. **Nessun impatto di mercato**: stake da 0,27 a 0,73 €.
9. **L'annullo può ritardare (300 ms) ma non fallire**, e le prese al tocco sono FOK che non
   possono essere rifiutate da un controllo di rischio.
10. **Esiti mancanti per 24 mercati su 73**: quelle celle sono escluse, mai contate come
    «non uscite».
11. **11 giorni di calendario, 39 partite.** Non è un mese di trading.

---

## 8. Riproducibilità e falsificazione

```
# la misura (16 minuti sulle 39 registrazioni, 6 varianti in un passaggio)
python -m Betfair.omega.tools.misura_ingresso_passivo --politica v4ter

# una registrazione sola, altra liability
python -m Betfair.omega.tools.misura_ingresso_passivo --politica v4ter \
    --eventi 35777617 --liability 50

# M1 e M1-bis restano invariati
python -m Betfair.omega.tools.misura_ingresso_passivo
python -m Betfair.omega.tools.misura_ingresso_passivo --politica v4

# i test: M1 (19) + M1-bis (14) + M1-ter (16)
python -m pytest Betfair/omega/tests -q
```

Il banco è quello di M1: book sintetico **nativo** (chiavi identiche allo stream vero,
parsato dal `HistoricListener` VERO di flumine), con gli **spread larghi** e l'**overround**
di un Correct Score vero — senza quelli `p_equa` esce sballata e con lei il prezzo di riserva.

| test | che cosa pretende |
|---|---|
| `test_p_equa_e_la_devigazione_di_superficie_liability` | la formula riga per riga, somma a 1 sui runner attivi |
| `test_sotto_sei_selezioni_non_si_deviga` · `test_un_book_incrociato_non_e_un_prezzo` | le due guardie di `superficie_liability` |
| `test_il_prezzo_di_riserva_viene_dal_bias_misurato_da_m6` | `L* = (1−c)/(p_equa·k_fascia)+c`, `k_fascia` dal file di M6, riserva **sotto il tocco** e **sopra il miglior back** |
| `test_il_bias_di_fascia_si_legge_dal_file_versionato_di_m6` | le sole due fasce operabili sono CS 0,5-1 % e 1-2 % |
| `test_la_quota_segue_il_prezzo_di_riserva_del_bias_e_poi_si_abbina` | il book si muove → `p_equa` cambia → `L*` cambia → **la quota si sposta**; poi passa volume scambiato al nostro prezzo e la quota si abbina |
| `test_il_margine_al_prezzo_quotato_non_scende_sotto_il_bias_di_fascia` | l'invariante del margine |
| **`test_falsificazione_k_fascia_uguale_a_uno_fa_scendere_la_quota_al_tocco`** | con `k_fascia = 1` la quota **sale verso il lato lay**, i fill **non diminuiscono** e l'invariante del margine è **violata**: il test verde qui sopra sa diventare rosso |
| `test_il_modello_non_entra_nel_prezzo` | `omega_v3.probabilita_selezioni` non viene mai chiamata |
| `test_solo_correct_score_e_solo_le_fasce_col_bias_dimostrato` · `test_la_finestra_e_dal_primo_all_ottantacinquesimo` | l'ammissibilità e la finestra |
| `test_selezione_avversa_e_il_rapporto_di_due_frequenze` · `..._senza_selezione_vale_uno` · `test_una_cella_riquotata_conta_UNA_volta` | la metrica, su casi costruiti a mano con la risposta nota (4,00 · 2,00 · unità = cella) |
| **`test_l_esito_della_cella_c_e_anche_senza_fill`** | il denominatore della selezione avversa ha bisogno dell'esito delle celle **non** abbinate — senza, il rapporto varrebbe 1,00 per costruzione (**è un difetto che questa misura ha davvero avuto, ed è stato trovato così**) |

---

## 9. Che cosa consegno al coordinatore

1. **Il margine di manovra sopra il miglior back non esiste: zero tick.** Il prezzo di
   riserva del bias di fascia **coincide** col miglior back, e al miglior back il margine è
   1,14 in mediana contro un requisito di 1,11 — con il 39 % delle celle già sotto. Il punto
   2 di `M4M5M6` §6-bis.3 va corretto: il rapporto di medie (1,31-1,71) sovrastima il
   rapporto mediano per cella (1,14).
2. **Al prezzo di riserva la quota non si riempie**: 0,09 %, cioè 0,3 fill per partita. Una
   gamba ogni tre partite non è una strategia: su 36 gambe quotate, **7** hanno avuto
   almeno un fill e **5** un esito valutabile.
3. **Il fill in più si compra solo rompendo il margine**, e i riempimenti che arrivano sono
   in maggioranza **prese al tocco** (247 su 352) — l'esatto contrario della politica.
4. **I fill passivi sono selezionati male**: `k` realizzato 0,20-0,26, fattore di selezione
   avversa 1,77-2,50. Coerente con M1 (2,5×) e con M6 al tocco.
5. **Il P&L è negativo in ogni variante che riempie**, con un drawdown di 45-51 € su 36
   gambe da 30 € di liability, e due celle perse che mangiano 60-80 celle vinte.
6. **La decisione di §1.1 (quale definizione di fascia) è ora bloccante**: il fattore di
   selezione avversa passa da 0,65 a 1,62 solo cambiando la popolazione candidata.
7. **Nessuno di questi numeri autorizza a costruire v4**, e nessuno lo vieta con un
   intervallo. Ma il numero ben misurato — zero tick di manovra e 0,09 % di fill al prezzo
   che rispetta il margine — dice che **la politica proposta non ha un punto di lavoro**,
   indipendentemente da come si risolverà la selezione avversa.
