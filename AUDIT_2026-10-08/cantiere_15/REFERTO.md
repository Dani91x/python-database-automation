# CANTIERE 15 - Scalper calcio sotto il banco realistico (08/10/2026)

Delegato di costruzione, worktree `agent-a4037f73f1d9aa424`, partenza dalla cima `b5547eb`
(«fix(banco): regola del mercato che attraversa»). Il worktree era fermo a `8226d76`: portato a `b5547eb`
con fast-forward, senza commit. Nessun commit, nessun `git add`.
Container cloud: 4 CPU condivise, **carico medio 25-29** durante le misure. I tempi di parete sono quindi
inaffidabili; per le prestazioni vale il **tempo CPU** (sez. 7).

## 0. Esito in una riga

**La causa è un difetto del banco, non della condotta del bot.** Il messaggio delle 17:00:06.704 non è un
burst e non è conflazione del registratore. È una **rivalutazione di cambio** dello stream: tutti i
livelli di `tradedVolume` di tre selezioni vengono moltiplicati per lo stesso fattore (x1,0000852). Non
c'è nessuno scambio. La regola del mercato che attraversa lo leggeva come volume scambiato e abbinava tre
ordini dello scalper che il mercato non aveva toccato.

Ho corretto il banco con una modifica additiva: `scambi_veri` in `banco_comune.py`. Base, paper e
rifiuti-betfair tornano **identici al riferimento del 07/10**, salvo i 2 fill per attraversamento veri
delle 17:27:29.

`chiusura-abbinata-in-parte` però **resta KO, per un'altra causa**: B2 x1, sel 58805, sbilancio **0,04**.
È la somma dei resti di due cicli: 0,017 + 0,020, ognuno dentro la tolleranza di 0,02 per ciclo che il bot
dichiara.

- K5 conta già la tolleranza per ciclo; B2 no.
- Correggerlo vuol dire o alzare la tolleranza di B2, cosa vietata dal brief, o cambiare la condotta del
  bot.
- **Mi fermo e lo porto all'utente** (sez. 8).
- Con la tolleranza per ciclo applicata a B2 in una copia fuori dal worktree, lo scenario torna OK con
  0 violazioni (sez. 5.3). L'esperimento NON è applicato.

## 1. Riproduzione del KO (punto 1)

Comando:

```
python -m Betfair.stream.backtest.certifica scalper_calcio 35797769 --scenari base,paper,chiusura-abbinata-in-parte,rifiuti-betfair,sniper-paper --worker 1
```

Le registrazioni sono decompresse da `registrazioni_banco/` in `_live_raw/` (LEGGIMI).

- Referto: `prima_35797769.txt`.
- **Identico al `calcio_dopo_5.txt` del PC.** Le uniche differenze sono il bet_id sintetico, l'encoding
  dei caratteri, il percorso e l'impronta del codice (`585a8d4a2562` qui, `fa6c7016c31e` sul PC; con ogni
  probabilità sono i fine riga CRLF di Windows).
- Risultato: KO, con B2 0,91 sulla sel 22 e CP4 1,02 contro 0,91.

### 1.1 Ricostruzione ordine per ordine, sel 22 (`traccia_KO_prima_sel22.txt`, blotter di flumine + attività)

Strumento: `strumenti/traccia_c15.py`. È il replay vero (`certifica_scenario` sotto `_freni_da_banco`) che
cattura il banco a fine referto.

| ora UTC | ordine | esito |
|---|---|---|
| 16:59:43 | maker BACK 25 @1,66 + LAY 25 @1,65 (LAPSE) | a riposo |
| **17:00:06.704** | le DUE gambe abbinate per intero nello stesso book: **fill per attraversamento** (scambio a 1,67 / 1,64) | posizione +0,25 se vince, 0 se perde |
| 17:00:17 | green-up: LAY 0,15 sotto il floor 0,50 (`min_bet_skip`), quindi **scavalco BACK 1,00 @1,65** | il guasto dello scenario lo colpisce come «prima chiusura» (il bot lo segna fra le uscite): tetto 0,40, abbinato 0,40, **0,60 vivo per sempre** (il tetto blocca ogni altro abbinamento di quell'ordine) |
| 17:00 - 19:00 | `_drive_flatten` vede un ordine di chiusura VIVO e non stantio (BACK 1,65 non è oltre il best lay), quindi **aspetta il fill** (`_vivo_o_in_volo`) | nessuna escalation alla finestra KO-180 s |
| 19:00:34.616 | fischio: il residuo 0,60 LAPSE scade (`lapse al fischio: 1`) | esposizione 0,91 (+0,51 / -0,40) **in gioco**: B2 |
| 19:00:34.616 | place-and-trim: parcheggio **LAY 1,00 @1,02**, poi taglio a 0,54, poi rimpiazzo @1,71 | CP4: il parcheggio «sposta il netto di 1,02» contro 0,91 |
| 19:00:44.955 | LAY 0,54 abbinata @1,68, `flatten_done` locked +0,14 | piatta 10 s dopo il fischio |

Il bot quindi **richiude in gioco il residuo LAPSE scaduto al KO, con il place-and-trim al centesimo**.
È esattamente la correzione che il brief proponeva come esempio, e c'è già. Il KO nasceva dalla catena
fill fantasma, poi scavalco colpito dal guasto, poi ordine marketable congelato dal tetto, poi fischio.
Il primo anello è il banco (sez. 2).

## 2. Il messaggio delle 17:00:06.704 (punto 2) - PROVA SCRITTA

Analisi sul raw, in sola lettura, nei file `raw_17_00_06_messaggi.txt` e
`raw_rivalutazioni_35797769.txt`.

**Struttura del messaggio:**
- Il raw contiene solo `op=mcm` (81.137 righe). Non ci sono messaggi di connessione o di stato, quindi
  il `conflateMs` della sottoscrizione **non è registrato**.
- Riga 1725, `clk AMfDAwDJpQQAhNwE`. Il messaggio precedente sul MATCH_ODDS è delle 17:00:01.312 (5,4 s
  prima); sulla sel 22 l'ultimo `trd` era delle 16:59:43.155.
- Pre-KO un intervallo di almeno 5 s sul MATCH_ODDS è normale: 308 casi su 6.230. Non è un buco del
  registratore.

**È una rivalutazione, non uno scambio:**
- Ogni livello cambiato cresce del fattore 1+8,52e-5, con scarto per livello compreso fra -0,005 e
  +0,008. Il dettaglio livello per livello è in `raw_rivalutazioni_35797769.txt`.
- Sel 22: 9 livelli da 1,64 a 1,72, +25,04 di tv. Sel 58805: 5 livelli, +6,10. Sel 29578: 5 livelli,
  +3,01.
- Uno scambio vero non distribuisce importi proporzionali al cumulato di ogni prezzo: 1,70 (63.473) +5,41;
  1,72 (1.616) +0,14; 4,4 (117,56) +0,01.

**Lo stesso fenomeno su tutta la registrazione:**
- 117 aggiornamenti di questo tipo in 36 istanti, tutti allo scoccare dell'ora: 17:00:0x con fattore
  positivo; 18:00:0x, 20:00:0x e 21:00/01 con fattore negativo.
- Su 35760084 ce ne sono 12 in 8 istanti, alle 16:00 e alle 17:00.
- È il ricalcolo orario del cumulato al cambio corrente.
- Con il fattore negativo il delta di flumine (`_calculate_traded` tiene solo i positivi) non produce
  niente. Con quello positivo produce «volume nuovo» a ogni prezzo.

**Conclusione:** il messaggio non è conflazione e non è un burst. È una rivalutazione, cioè zero euro
scambiati. I tre fill delle 17:00:06 erano un **artefatto del banco**.

**Gli altri fill per attraversamento sono scambi veri** (`strumenti/raw_verifica_fill.py`): ognuno sta su
un solo livello, con il tv che sale.

| ora | selezione | scambio |
|---|---|---|
| 17:27:29 | 47973 | +40,05 a 1,83 |
| 17:45:11 | 22 | +74,85 a 1,68 |
| 17:53:03 | 22 | 4 x +1.704,59 a 1,69: burst vero, tv 397.874 -> 402.988 in 0,5 s |
| 17:56:54 | 47972 | +1,71 a 2,20 |
| 18:04:58 | 58805 | +6,48 a 4,2 |
| 18:08:24 | 22 | +7,33 a 1,70 |
| 18:46:24 | 58805 | +32,38 a 4,2 |
| 19:50:11 | 1222344 | +3,41 a 2,12 |

## 3. La correzione (banco)

File: `Betfair/stream/backtest/banco_comune.py`. Modifica additiva; `git diff --stat` dà +96/-1.

- **Testata 6-quater, righe 178-193:** il paragrafo «LA RIVALUTAZIONE DI CAMBIO NON E' UNO SCAMBIO».
- **Righe 1848-1908:** le costanti `RIVALUTAZIONE_IGNORATA = True` (interruttore, solo per misura e
  falsificazione), `RIVALUTAZIONE_MIN_LIVELLI = 3`, `RIVALUTAZIONE_MAX_FATTORE = 0.01`,
  `RIVALUTAZIONE_TOLL = 0.03` (EUR) e la funzione pura `scambi_veri(traded, traded_volume)`. Come lavora:
  1. ricostruisce il cumulato di prima di ogni livello (`attuale - delta`);
  2. se almeno 3 livelli che avevano già volume crescono dello stesso fattore positivo e piccolo,
     riconosce una rivalutazione. Il fattore è la mediana, poi ripesata sul volume dei livelli entro il
     ±20 %. Ogni livello deve stare nel fattore entro 0,03 €;
  3. in quel caso toglie a ogni livello la parte proporzionale. Restano l'eccedenza oltre 0,03 (uno
     scambio vero arrivato nello stesso messaggio) e i livelli nuovi;
  4. altrimenti restituisce il delta così com'è.
- **Righe 2126-2129:** il contatore `MotoreReplay.rivalutazioni_ignorate`.
- **Righe 2243 e 2259-2273:** in `_mercato_che_attraversa` il volume guardato passa da `scambi_veri`,
  calcolato una volta per runner e per book.

**Cosa NON tocca:**
- la coda di flumine (`_process_traded`). La coda prende ancora la quota della rivalutazione al prezzo
  dell'ordine: il test `test_motore_senza_la_correzione_abbinava` mostra 2,66 di 25 dati dalla coda. È un
  limite dichiarato (sez. 8, D3);
- `ATTRAVERSAMENTO`, che resta acceso;
- le tolleranze di B2 e CP4;
- la strategia, lo scalper e `submin.py`. `scalper_bot.py` ha lo sha `039903df...` identico alla partenza.

## 4. Test nuovi e falsificazione

### `Betfair/stream/tests/test_banco_rivalutazione_cambio_2026_10_08.py`, 13 verdi

Oggetti veri (scena del test di attraversamento: `FlumineSimulation`, `SimulatedMiddleware`,
`MotoreReplay`, `MarketBook` di betfairlightweight) e raw vero del banco (`registrazioni_banco/35797769`,
gz). I casi coperti:
- la rivalutazione del reperto vale `{}`;
- rivalutazione + scambio vero di 7,00 a 1,67: resta solo 1,67 (circa 7,00);
- un livello nuovo resta;
- uno sweep vero su 3 livelli non proporzionali resta intero;
- con 1-2 livelli resta scambio;
- l'interruttore spento ripristina la via di prima;
- sul raw, la riga 1725 è una rivalutazione su 3 selezioni e i cumulati coincidono con quelli del test;
- sul raw, la riga 1704 (scambio vero su un livello) resta;
- nel motore, BACK 1,66 e LAY 1,65 non sono abbinate per attraversamento sulla rivalutazione;
- nel motore, senza la correzione lo erano (il reperto);
- nel motore, rivalutazione + scambio vero: abbinata.

Mutazioni su `banco_comune.py`, ripristino verificato ogni volta con sha `3ef9a5ae3b65929a...` IDENTICO:

| mutazione | rossi |
|---|---|
| M1 `RIVALUTAZIONE_IGNORATA = False` | 6 |
| M2 il motore non usa `scambi_veri` | 2 |
| M3 lo scambio vero nella rivalutazione si perde | 2 |
| M4 il livello nuovo si perde | 1 |
| M5 senza la verifica di adattamento al fattore | 1 |
| M6 `MIN_LIVELLI = 1` | 3 |
| M7 `TOLL = 0.0` | 6 |

### `Betfair/stream/tests/test_scalper_fill_simultanei_2026_10_08.py`, 6 verdi (punto 2, fill simultanei)

Riusa il banco vero del cantiere S: bot vero con `VALIDATED_PARAMS`, `Flumine` vero con il client paper
della sessione, book mcm passati da `StreamListener`, esecuzione differita di 1 e di 4 book. Gli
abbinamenti li fa flumine.

Casi:
- (a) le due gambe del maker abbinate nello **stesso book**, intere oppure con la LAY in parte;
- (b) close + aggiunta della pre-dimensione (due chiusure) abbinate nello **stesso book**.

A ogni book (compreso quello del fill) si verificano:
- K5/K6/B2 del banco;
- **mai sovracopertura**: il netto non cambia segno;
- nessuna `ledger_divergence`;
- alla fine: piatto o resto dichiarato, nessun ordine vivo, slot chiuso.

Esito: **il bot regge**. Nel caso (a) intere fa scavalco BACK 1,00, poi LAY 1,22 al centesimo: piatto
(0,21 / 0,22). Nel caso (a) con la LAY in parte fa flatten LAY 10,14: piatto.

Mutazioni su `scalper_bot.py`, ripristino con sha `039903dfc2a6858e...` IDENTICO:

| mutazione | rossi |
|---|---|
| BM1 doppio fill dichiarato DONE invece del flatten | 4 |
| BM2 residui delle gambe non ritirati | **0, verde atteso**: guardia ridondante, perché `_drive_flatten` ritira comunque le gambe d'ingresso (come M3b del cantiere precedente) |
| BM3 il flatten non aspetta gli ordini in volo | 2 (latenza 4) |
| BM4 pre-dimensione senza la riduzione della close | 2 |
| BM5 il netto conta una gamba sola | 4 |

## 5. Replay prima/dopo (punto 3), `--worker 1`

- PRIMA: albero estratto con `git archive b5547eb` fuori dal worktree.
- DOPO: il worktree.
- Diff esclusi tempi, hash, percorso e bet_id: `diff_5_scenari.txt`.

### 5.1 Esito per registrazione

**35760084** (`prima_35760084.txt`, `dopo_35760084.txt`)
- 5/5 OK, prima e dopo. **Diff vuoto.**
- Lo scalper non opera su questa registrazione: 0 azioni, 0 fill per attraversamento.

**35797769** (`prima_35797769.txt`, `dopo_35797769.txt`)

| scenario | PRIMA | DOPO |
|---|---|---|
| base | OK, 18 azioni | OK, **44** azioni |
| paper | OK, 18 | OK, 44 |
| chiusura-abbinata-in-parte | **KO** 112 (B2 0,91 + CP4) | **KO** 213 (B2 0,04, sel 58805) |
| rifiuti-betfair | OK, 30 | OK, 56 |
| sniper-paper | OK, 18 | OK, 44 |

### 5.2 Spiegazione delle righe diverse

Tutte le righe diverse vengono dalla stessa causa: **spariscono i 3 fill per attraversamento delle
17:00:06**, perché erano una rivalutazione. Dal confronto DOPO contro il riferimento del 07/10
(`banco_attraversa/calcio_prima.txt`, banco senza attraversamento):

- **base, paper, rifiuti-betfair:** identici al 07/10 salvo 3 righe:
  - la nota `fill per mercato che attraversa: 2` (17:27:29, sel 47973, LAY 0,68 e 1,14 @1,84, scambio vero
    a 1,83);
  - le righe di specchio, 130.552 contro 130.529: sono i 2 fill veri, che cambiano l'istante di qualche
    riga.
  - Azioni, motivi e stati sono identici: 44 / x23 place / x5 cycle / x5 submin_step / x4 close_presize /
    x4 scratch / x2 submin_start; FLATTENING mai visto, come il 07/10.
- **sniper-paper:**
  - maker identico al 07/10;
  - fill veri 3 (i due delle 17:27:29 + 19:50:11, sel 1222344, LAY 10,09 @2,20, scambio a 2,12);
  - lo SNIPER segue il percorso del dopo-PC (orders 2, greens 1, pnl 0,09), cioè quello dettato dal fill
    vero delle 19:50:11, già presente nel `calcio_dopo_5` del PC;
  - piatto a fine sessione: True.
- **chiusura-abbinata-in-parte** (contro il 07/10: 213 contro 215 azioni):
  - 7 fill veri per attraversamento: 17:45:11 e 17:53:03 sel 22; 17:56:54 sel 47972; 18:04:58 x2 sel
    58805; 18:08:24 sel 22; 18:46:24 sel 58805;
  - 6 chiusure colpite contro 5;
  - B2 x1 nuovo (sez. 5.3).
- **Copertura** (diff nelle ultime righe): i conteggi B1, B3, B4, B6, K1, K4, K5, K7, CP1, CP3 e CP4
  cambiano perché ci sono più ordini e più cicli. Violazioni totali: 2, ora 1.

### 5.3 Il B2 rimasto, sel 58805, ricostruito ordine per ordine (`traccia_KO_dopo_sel58805.txt`)

Il bot dichiara 0,02 per ciclo (`tolleranza_slot`). B2 confronta il totale della selezione con 0,02
**senza** contare i cicli; K5 invece li conta (`certificazione.py:741-744`: «la tolleranza e' PER CICLO»).

| ciclo | ordini abbinati | se vince | se perde | resto |
|---|---|---|---|---|
| 1 (16:43-17:52) | LAY 25 @4,2; BACK 10 @4,2 (chiusura colpita); BACK 14,50 @4,1; BACK 0,87 @4,1 (place-and-trim) | -0,353 | -0,370 | **0,017** |
| 2 (18:04) | LAY 24,81 @4,1; BACK 24,00 + 0,81 @4,1 | 0 | 0 | 0 |
| 3 (18:45) | BACK 25 @4,1; LAY 24,40 @4,2 (verde: 25 x 4,1 / 4,2 = 24,405, quindi 24,40) | -0,58 | -0,60 | **0,020** |
| **selezione** | | **-0,933** | **-0,970** | **0,037**, cioè 0,04 nel referto |

- Ogni ciclo è chiuso entro la tolleranza che il bot dichiara.
- Chiudere 0,037 richiederebbe una LAY da circa 0,01: sotto il floor di legge e sotto la «polvere» di
  0,05 dello scavalco. Nessun ordine legale lo chiude.
- **Esperimento**, nella copia `esperimento_b2` fuori dal worktree, con
  `esperimento_B2_per_ciclo_NON_applicato.patch`: B2 con la stessa tolleranza per ciclo di K5 dà lo
  scenario **OK, 0 violazioni, 213 azioni** (`esperimento_B2_per_ciclo_NON_applicato.txt`).
- **Non applicato**: il brief vieta di alzare le tolleranze di B2/CP4. Va in sez. 8.

## 6. Comandi e numeri veri

**Suite Python e frontend**
- `python3 -m pytest Betfair/ -q -p no:cacheprovider`: vedi `pytest_betfair_dopo.txt` e il paragrafo
  «Suite» in fondo.
- Frontend non toccato: né vitest né tsc lanciati.

**Test mirati**
- `python3 -m pytest Betfair/stream/tests/test_banco_rivalutazione_cambio_2026_10_08.py Betfair/stream/tests/test_banco_attraversa_2026_10_08.py -q -p no:cacheprovider`:
  **24 passed**.
- `python3 -m pytest Betfair/stream/tests/test_scalper_fill_simultanei_2026_10_08.py -q -p no:cacheprovider`:
  **6 passed**.

## 7. Tempi (macchina carica: load average 25-29 su 4 CPU)

**Tempi di parete dei 5 scenari su 35797769**
- PRIMA 7m36s, DOPO 18m44s.
- Con questo carico il dato non è confrontabile: su 35760084, che ha esito identico, è PRIMA 138 s e
  DOPO 128 s.

**Misura CPU** (`strumenti/cpu_certifica.py`, scenario `base` su 35797769)
- PRIMA 40,5 s, DOPO 44,3 s.
- Il DOPO fa 44 azioni invece di 18: è il percorso del 07/10, quindi più lavoro del bot.

**Costo della correzione** (`strumenti/costo_scambi_veri.py`, `base`)
- `scambi_veri`: 146 chiamate, 0,001 s in tutto, pari allo **0,00 %** di 41,5 s di CPU.
- `_mercato_che_attraversa`: 57.180 chiamate, 0,65 s.
- **Nessun rallentamento dovuto al codice.**

## 8. Decisioni per l'utente (non fatte da me)

**D1 - B2 contro K5 sui resti per ciclo** (blocca il verde di `chiusura-abbinata-in-parte`)

Due strade alternative:
- (a) **Banco:** B2 usa la tolleranza per ciclo come K5. Patch pronta: `esperimento_B2_per_ciclo_NON_applicato.patch`.
  Esito misurato: OK. È un «alzare la tolleranza di B2», quindi lo decide l'utente o il coordinatore.
- (b) **Bot:** alla finestra KO lo slot guarda l'esposizione dell'intera selezione (tutti i cicli) e
  dichiara/ricorda la polvere accumulata (`residuo_ricordato`). Sopra la soglia dello scavalco piazzerebbe
  ordini, quindi è una decisione di trading.

Non scelgo.

**D2 - Condotta latente vista sul percorso fantasma** (sez. 1.1)

- Il fatto: un ordine di chiusura vivo, marketable e non stantio viene aspettato all'infinito anche dentro
  la finestra di flatten (KO-180 s), senza escalation.
- Nella realtà un ordine a quel prezzo si abbina. Nel banco lo congela il tetto del guasto «chiusura
  abbinata in parte», che blocca ogni ulteriore abbinamento dell'ordine colpito.
- Esito: il bot attraversa il fischio con 0,91 e richiude in 10 s in gioco.
- Un timeout o escalation sul flatten vicino al KO cambierebbe prezzi e tempi delle uscite: è una
  **decisione di trading**, quindi non l'ho fatto.
- Va valutato anche se il guasto debba congelare per ore un ordine marketable: è un realismo dello
  scenario da discutere.

**D3 - CP4 e il parcheggio LAY del place-and-trim**

- Il fatto: il parcheggio LAY 1,00 @1,02 (minimo .it) conta 1,02 di netto contro 0,91 da chiudere.
- CP4 esenta solo il parcheggio BACK @1000.
- È il rischio teorico già scritto il 07/10 (`SCALPER_TENNIS_CP4.md`): sotto 1,00 non c'è un parcheggio
  più piccolo.
- Sul percorso corretto non si presenta.

**D4 - La coda di flumine prende ancora la rivalutazione al prezzo dell'ordine** (pochi euro all'ora per
livello)

- Correggerlo cambierebbe i riferimenti di tutti i bot: lo propongo come cantiere a parte, non l'ho fatto.

**D5 - Altri bot sul banco comune**

- `scambi_veri` vale per TUTTI i bot che passano da `MotoreReplay` con `ATTRAVERSAMENTO`: Mike, Omega e
  Safe su 35760084 (12 rivalutazioni alle 16:00 e 17:00) e i bot tennis.
- Un loro riferimento cambia solo se avevano un ordine vivo al momento di una rivalutazione.
- Non li ho rilanciati: è il punto 4 delle specifiche, coordinato dopo. Comando:
  `python -m Betfair.stream.backtest.certifica <mike|omega|safe_*> 35760084 --scenari tutti --worker 1`,
  prima e dopo.

## 9. Punto 4 - nuovo riferimento `--scenari tutti`

**35760084**
- Lanciato in background: `AUDIT_2026-10-08/riferimenti/scalper_calcio_35760084_tutti.txt`, con il
  diario e il tempo nei file accanto.
- Numeri nel paragrafo «Riferimento» in fondo.

**35797769**
- **Non lanciato per intero.** Sul PC 47 scenari richiedono 115 min; qui, con la macchina carica, almeno
  2,5 ore. Supera il tetto di 2 ore: lo chiedo al coordinatore.
- Comando: `python -m Betfair.stream.backtest.certifica scalper_calcio 35797769 --scenari tutti --worker 1 --diario AUDIT_2026-10-08/riferimenti/scalper_calcio_35797769_tutti.diario.txt > AUDIT_2026-10-08/riferimenti/scalper_calcio_35797769_tutti.txt`.
- In alternativa, a blocchi:
  - blocco 1, maker: `base,paper,senza-missione,bot-fermo,kill-switch,esiti-ignoti,rifiuti-betfair,riavvio,chiusura-abbinata-in-parte,sniper,sniper-paper,sniper-uscite-auto,uscite-manuali,uscite-manuali-firmate,auto-live`
    (circa 40 min sul PC);
  - blocco 2: gli scenari `media-*`.

**Numeri attesi su 35797769**
- I 4 scenari dei 5 qui sopra come in sez. 5.
- `chiusura-abbinata-in-parte` KO per B2 0,04 finché D1 non è decisa.
- `riavvio` e `uscite-manuali-firmate` erano già KO nel `prima_tutti` del PC: KO preesistenti, fuori da
  questo cantiere.

## 10. Limiti dichiarati / cosa non ho verificato

- Non ho registrazioni tennis né il DB: per i bot tennis nessun replay (D5).
- Il riconoscimento richiede almeno 3 livelli. Una rivalutazione su una selezione con 1-2 livelli
  scambiati resta «scambio», cioè la via prudente di prima.
- Uno scambio vero sotto 0,03 € arrivato nello stesso messaggio di una rivalutazione viene ignorato.
- Le rivalutazioni negative non generano delta (flumine tiene solo i positivi): invariato.
- Il `conflateMs` non è nel raw. La prova che non è conflazione è la proporzionalità esatta dei livelli,
  non la sottoscrizione.

## Blocco per la cronostoria

```
### 08/10 - Cantiere 15 (scalper calcio sotto il banco realistico) - delegato cloud
- Causa del KO di chiusura-abbinata-in-parte (B2 0,91 + CP4) su 35797769: DIFETTO DEL BANCO.
  Il messaggio delle 17:00:06.704 e' una RIVALUTAZIONE DI CAMBIO oraria (tutti i livelli di
  tradedVolume x1,0000852; 117 casi in 36 istanti, tutti allo scoccare dell'ora), non un burst
  ne' conflazione: la regola del mercato che attraversa abbinava 3 ordini mai toccati.
- Fix: banco_comune.scambi_veri (6-quater in coda), additivo; ATTRAVERSAMENTO acceso, B2/CP4
  intatti, strategia intatta (scalper_bot.py identico). Test: test_banco_rivalutazione_cambio
  (13, M1-M7 rossi), test_scalper_fill_simultanei (6, BM1/3/4/5 rossi, BM2 ridondante).
- Replay prima/dopo 5 scenari --worker 1: 35760084 identico; 35797769 base/paper/rifiuti
  tornano al riferimento del 07/10 (+2 fill veri 17:27:29); sniper-paper come il dopo-PC.
- RESTA KO chiusura-abbinata-in-parte: B2 0,04 sel 58805 = resti di due cicli (0,017+0,020)
  dentro la tolleranza per ciclo del bot; K5 la conta, B2 no. DECISIONE D1 all'utente
  (patch B2 per ciclo pronta e misurata OK, NON applicata). D2-D5 nel referto.
- Punto di ripresa: decidere D1; riferimento --scenari tutti di 35797769 (oltre 2 h) da lanciare
  sul PC o a blocchi; punto 4 (altri bot) col banco corretto.
```

## Suite

**Esito di `python3 -m pytest Betfair/ -q -p no:cacheprovider`** (DOPO, file `pytest_betfair_dopo.txt`)
- **1 failed, 10799 passed, 65 skipped, 6 xfailed** in 11m08s.
- L'unico rosso è `test_motore_ordini_2026_09_24.py::test_latenza_logica_comando_place_sotto_20_ms`.

**Perché quel rosso non viene da questo cantiere**
- È una misura di tempo di parete: p95 sotto i 20 ms.
- Rilanciato da solo 3 volte nel worktree: rosso, rosso, verde.
- Rilanciato 3 volte sull'albero di partenza `b5547eb`: rosso, rosso, verde (p95 16,74 ms nel verde).
- È **instabile per il carico** (load 19-29 su 4 CPU), già sull'albero di partenza.
- Non ho toccato il motore ordini.
- Va riconfermato sul PC.

## Riferimento (punto 4), scalper calcio 35760084 `--scenari tutti`, banco corretto

File in `AUDIT_2026-10-08/riferimenti/`: `scalper_calcio_35760084_tutti.txt`, `.diario.txt`, `.tempo.txt`.

**Esito**
- **47 scenari: 46 senza violazioni, 1 con violazioni (1 violazione totale).**
- Tempo: parete 40m27s, CPU 1.425 s (macchina carica).

**L'unico KO: `auto-live`, AL1**
- Il dettaglio: «dry_run=False, client reali 1 su 1, ordini 0». Su questa partita lo scalper non piazza
  nessun ordine, quindi il controllo non trova l'ordine vero che cerca.
- **È preesistente:** lo stesso scenario sull'albero di partenza `b5547eb` dà lo stesso KO, con le stesse
  righe (`scalper_calcio_35760084_auto-live_PRIMA_b5547eb.txt`).
- Non dipende da questo cantiere: 0 azioni e 0 fill per attraversamento.
- Va giudicato a parte: è il controllo AL1 su una registrazione senza ingressi.

**Fill per attraversamento**
- Negli scenari `media-*` ce ne sono (16:16, 16:22, 16:24, 16:25 UTC): sono fuori dall'ora tonda,
  quindi scambi veri e non rivalutazioni.
- Negli altri scenari: 0.

**35797769 `tutti`: NON lanciato** (oltre 2 ore di macchina, vedi sez. 9). Lo chiedo al coordinatore.

## Verifica del coordinatore cloud (08/10)
- PROVA INDIPENDENTE sul raw della 35797769 (script mio, soglia stretta 2e-5): 15 messaggi in cui >=3 livelli gia' scambiati di un
  runner sono moltiplicati per LO STESSO fattore, tutti allo scoccare dell'ora e uguali su TUTTI i mercati (17:00:06.704 x1,0000852 su
  sel 22/58805/29578 del MATCH_ODDS, 17:00:08.992 x1,000085 su un altro mercato, 18:00:07.009 x0,9997444 ...): e' la rivalutazione
  oraria del cambio del volume scambiato, non uno scambio. La diagnosi (difetto del banco, non condotta del bot) regge.
- Test rilanciati: rivalutazione + attraversa + fill simultanei 30 verdi. MIE MUTAZIONI: M1 livello nuovo ignorato -> 1 rosso;
  M2 scambio vero nello stesso messaggio perso -> 2 rossi; M3 rivalutazione di nuovo trattata da scambio -> 2 rossi. Ripristino verificato.
- MIO REPLAY (checkout integrato, `--worker 1`, `verifica_coordinatore_35797769.txt`): `base` OK 44 azioni, `chiusura-abbinata-in-parte`
  KO B2 213 azioni: IDENTICI al referto del delegato.
- DECISIONE DELL'UTENTE APERTA (D1, sez. 8): il B2 residuo (0,04 su sel 58805, somma di due resti per ciclo dentro la tolleranza che
  il bot dichiara per ciclo). Il cantiere e' integrato con il banco che dice la verita' e lo scenario KO dichiarato: nessuna
  tolleranza alzata, nessuna condotta cambiata.
