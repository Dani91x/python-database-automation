# OMEGA V4 — LA TESI DEL COORDINATORE (17/09/2026)

> Ordine dell'utente: «voglio il massimo della tecnologia, della matematica e delle scienze
> predittive; Omega deve portare in profitto nel lungo periodo, adattarsi al live, fare
> massività con la maggior probabilità di profitto». Questo documento è la tesi su cui i
> delegati costruiscono. Ogni numero qui è o già misurato (K_MISURATO, REFERTO_V3) o
> marcato «da misurare». Vincola i progetti v4 e M2.

## 1. Che cosa è Omega, detto da trader

Omega **vende opzioni binarie fuori dal denaro** sul mercato del risultato esatto: banca
una scoreline rara. Incassa un premio piccolo (lo stake al netto della commissione) e paga
la liability se la scoreline esce. Il profitto nel lungo periodo viene da UNA sola cosa:

```
EV per gamba = s · (1 − c) · (1 − 1/k)        k = p_implicita(prezzo ottenuto) / p_vera
```

**La quota non entra nel valore atteso** (entra nella liability, cioè nella varianza). Il
prodotto è quindi fatto di quattro leve, e in quest'ordine di peso:

1. **il prezzo a cui si entra** (k al tocco < 1 in ogni fascia: attraversare lo spread perde;
   a metà spread k 1,08-1,53 nelle fasce di coda: dentro lo spread si guadagna);
2. **la stima di p_vera** (calibrata, con incertezza, aggiornata a ogni tick);
3. **la scelta della cella** (EV per unità di liability, non «la P più bassa»);
4. **la dimensione** (Kelly frazionario sulla liability, cap, diversificazione).

Tutto il resto (finestre, tetti di quota, target giornaliero) è un vincolo ereditato che va
sostituito da queste quattro leve. Il target giornaliero diviso per le partite (v1) è un
**anti-pattern**: obbliga a operare dove non c'è margine. In v4 il target diventa una metrica
di rendiconto, non un motore di decisione. *(Decisione dell'utente da confermare: §8.)*

## 2. Il meccanismo che rende: market making con prezzo di riserva del modello

Per ogni cella ammissibile, a ogni tick, il modello dà `p_sup(t)` (limite superiore, non
centro) e il **prezzo di riserva**:

```
L*(t) = (1 − c) / (p_sup(t) · k_soglia) + c        (k_soglia = max(2, k_prudente di fascia))
```

Regola unica delle «due strade» dell'utente:

- se il miglior lay disponibile è **≤ L*(t)** → si prende subito (fill con margine);
- altrimenti si **appoggia** una lay a `min(L*(t), best_lay − 1 tick)`, arrotondata al tick,
  sul lato back del book: diventiamo la miglior offerta per chi punta. Si abbina quando un
  puntatore accetta la nostra quota.

**«Il tempo è dalla nostra parte», in formula.** Senza gol, `p_sup(t)` decade e `L*(t)`
sale: la quota che possiamo offrire mantenendo il margine si avvicina da sola al mercato.
Il fill arriva all'incrocio, con il margine intatto. Chi non ricalcola il prezzo di riserva a
ogni tick non ha questo effetto: è la differenza fra un ordine «appoggiato e dimenticato» e
una quotazione viva. Vale per la POSIZIONE (una volta abbinati, il decadimento lavora per
noi: è la theta dell'opzione venduta) e per la QUOTA (che sale con L*).

**Selezione avversa, misurata e controllata.** Un fill passivo avviene anche quando il
mercato scende verso di noi perché la cella è diventata più probabile (gol, rosso, dominio).
Difese: (a) a ogni evento (sospensione, cambio punteggio, rosso) la quota è STALE: annullo
immediato o, se Betfair l'ha già cancellata, rilettura per `bet_id` alla riapertura
(Mike C.1-bis); (b) nessuna quota nei primi N secondi dopo la riapertura (N da misurare in
M1: tempo di riassestamento del book); (c) isteresi: la quota si sposta solo se `L*` cambia
di ≥ 1 tick o la cella migliore cambia, con annullo in un giro e nuovo ordine al giro dopo a
residuo 0 confermato («mai due lay»); (d) M1 riporta la quota di fill «attraversati dal
mercato»: se supera la soglia (da fissare sui dati) la fascia si chiude.

**Celle impossibili e realizzate.** Dopo un gol, ogni scoreline sotto il punteggio è
impossibile: p = 0, nessuno la punta, si toglie dalla quotazione (se avevamo una lay già
abbinata lì, è vinta al regolamento: si tiene). Il punteggio corrente e gli adiacenti restano
esclusi. La gamba HT muore al 45'+recupero; la gamba FT sceglie sapendo l'esito HT.

## 3. Il modello predittivo (stato dell'arte, fattibile qui)

Base bivariata a intensità dipendenti da tempo e stato — Dixon & Robinson (1998), esteso
alla Titman, Costain, Ridall & Gregory (2015) per l'in-play — con:

- **hazard di gol** `h_i(t | punteggio, rossi, lega, regime di ritardo)` stimato con
  regressione di Poisson gerarchica (shrinkage per lega) sulla tabella delle 1,07 M
  transizioni già in casa (`omega_validate.py`), profilo temporale non uniforme (hazard
  crescente verso fine tempo e nel recupero) e effetto rosso (Vecer, Kopriva & Ichiba 2009);
- **sovradispersione** Gamma-Poisson/NegBin (già vincitore del banco: log-loss 1,932 contro
  1,939 della v2), che **impara dai gol visti** (posterior sulla forza residua);
- **correzione dei punteggi bassi** Dixon-Coles (ρ per lega) dove conta (HT);
- **fusione col mercato** in log-odds (pool logaritmico, Satopää 2014) con pesi per fascia
  e per «tempo dall'ultimo evento»: il mercato è affidabile in regime stazionario e meno
  subito dopo un evento — da misurare, è lì che il modello vale di più;
- **calibrazione della coda**: affidabilità per fasce di p prevista, isotonic sulle fasce,
  operatività sul **limite superiore** (Wilson) e non sul centro: sbagliare per difetto costa
  la liability intera;
- **M2** (intensità pre-partita): prior di lega → forza attacco/difesa (Maher/Dixon-Coles su
  storico) → forma → h2h → quote devigate (fonte più forte); pesi tarati SOLO fuori campione;
  un peso che non migliora con IC che esclude 0 vale 0; degradazione dichiarata quando una
  fonte manca (cv più largo → p_sup più alto → L* più basso → meno ingressi: il modello
  diventa prudente da solo).

Antidoti alla maledizione dell'ottimizzatore (già fallita tre volte in questo repo): limite
superiore, due stime indipendenti sotto soglia, n_min per cella, k misurato, split temporale,
bootstrap, e — nuovo — **monitoraggio online**: k realizzato per fascia con CUSUM; se scende
sotto 1 con IC, la fascia si spegne da sola.

## 4. Scelta della cella e dimensione

- Ordinamento per **EV per unità di liability**: `(1−c)(1−1/k) / (L−1)`; favorisce le
  quote basse a parità di margine, il bias vive nella coda: il compromesso lo fa Kelly.
- **Kelly frazionario per lay**: frazione della cassa in liability `f* = edge/(L−1)`
  circa, usata a 1/4; cap di liability per gamba, per partita e per giorno; stop giornaliero.
- **Paniere (decisione dell'utente, §8).** Le scoreline di un mercato sono mutuamente
  esclusive: bancandone n con stake `s_i` a prezzo `L_i`, il caso peggiore è
  `max_j [ s_j(L_j−1) − Σ_{i≠j} s_i(1−c) ]`, NON la somma delle liability. Quotare più celle
  di coda insieme dentro un cap di caso peggiore aumenta la probabilità di fill (massività)
  con rischio limitato per costruzione. Rispetta «due ingressi per partita» se «ingresso» =
  gamba (HT, FT); non lo rispetta se «ingresso» = una sola cella. Da decidere.

## 5. Uscite

Solo **proposte** con i numeri: `EV(tengo) = p_win·s(1−c) − p_lose·liability` contro
`bloccabile ora`; si propone quando chiudere batte tenere, o quando scatta un cap di
drawdown; mai automatiche (12/09: le chiusure automatiche hanno distrutto valore). Il
cash-out globale dell'utente e la chiusura fuori app restano come O1 (posizione di conto).

## 6. Massività con la maggior probabilità di profitto

Finestre e tetto di quota vanno sostituiti da: **cella ammissibile ⇔ margine k ≥ soglia al
nostro prezzo, liability ≤ cap, book abbastanza profondo**. Se lo studio (v4 §5) mostra
margine dal 1' al 44' e dal 46' all'89', le finestre si aprono; se in certe fasce (5-10 %)
non c'è mai margine, restano chiuse per costruzione. Il volume è un **risultato** del
margine, non un obiettivo. Ogni allargamento va misurato prima (replay massivo, Monte Carlo
di P&L e drawdown) e poi in paper via flumine con la stessa coda del replay.

## 7. Come si prova (scienze predittive, non fede)

Replay su TUTTE le registrazioni Omega col banco comune (coda simulata, cancel, lapse alla
sospensione): fill rate, k realizzato per fascia con IC, selezione avversa, P&L, drawdown;
grafici di affidabilità; test placebo (celle a caso) e permutazioni; controllo dei test
multipli; poi paper via flumine (F1) con parità campo per campo; poi live piccolo con
referto forense. Ogni fase certificata dal coordinatore con falsificazione.

## 8. Decisioni che restano all'utente (poche)

1. Target giornaliero: da motore a metrica (sì/no).
2. Paniere di celle per gamba dentro un cap di caso peggiore (sì/no; se sì, quante celle).
3. Cassa di riferimento per Kelly e cap giornaliero di liability (numeri).
4. Tetto di quota: sostituito dal cap di liability (sì/no).

## 9. ADDENDUM (osservazione dell'utente, 17/09 h12): «senza gol le quote salgono e prenderle diventa più difficile»

È vero, ed è la chiave del timing. Per chi banca, quota più alta = liability più alta a parità
di stake. Il valore atteso per unità di liability è

```
EV / liability = (1 − c)(1 − 1/k) / (L − 1)
```

quindi, a parità di margine k, **prima si entra (quota più bassa) e più rende ogni euro di
liability**. Le finestre attuali (20'-40' e 50'-80') aspettano che le quote SALGANO: sono
orientate al contrario. Conseguenze per v4, da misurare in §5 del progetto:

1. **Ingresso presto** (dal 1' per HT, dal 46' per FT) su celle a ≥ 2 gol di distanza dal
   punteggio, quando la quota è bassa, il book è più profondo e la liability è contenuta; il
   modello in quel momento è quasi tutto PRE-PARTITA → **M2 (qualità delle λ pre-match) è
   l'abilitatore dell'ingresso presto**, l'in-play serve per ricalcolare, spostare e uscire.
2. **Dimensionamento a liability fissa, non a stake fisso**: `s = liability_gamba / (L − 1)`.
   A quota 40 lo stake è 0,77 € su 30 € di liability, a quota 200 è 0,15 €: il volume si
   adatta da solo alla quota e l'esposizione resta costante.
3. **Il passivo non «prende» le quote alte: le riceve.** Il bias favourite-longshot è
   letteralmente gente che paga troppo per le code: sono loro a colpire la nostra offerta.
   Più alta la quota, più forte il bias (k_equo 1,53 sotto l'1 %), più la liability pesa: il
   compromesso lo fanno la liability fissa e Kelly, non una finestra.
4. **Il paniere moltiplica la massività a caso peggiore quasi invariato.** Bancando n
   scoreline mutuamente esclusive a quota ~100 con stake 1 €: caso peggiore
   `99 − (n−1)·0,95`, premio incassato `n·0,95`, P(una esce) ≈ n·p. Con n = 5 e k = 2:
   caso peggiore 95,2 € (contro 99 di una sola), EV ≈ +0,76 € contro +0,47 € della cella
   singola, e cinque occasioni di fill invece di una. È la risposta matematica a «massività e
   qualità insieme». *(Decisione dell'utente: §8.2.)*
5. **La rotazione del capitale è già nel mercato scelto**: HT si regola al 45', FT al 90'.
   Chiudere prima comprando la coda a quota salita costa il bias al contrario (backare
   longshot è −EV: è il 12/09) → per default si tiene fino al regolamento; si propone la
   chiusura solo se il modello vede il rischio salire o per cap.
6. **Il tempo lavora sulla POSIZIONE**, non sulla quota ferma: una lay abbinata presto vede la
   sua probabilità decadere ogni minuto senza gol; è l'unico posto dove «il tempo è dalla
   nostra parte» in senso stretto. Sulla quota, il tempo la allontana: per questo la quota è
   viva (L* ricalcolato) e per questo si entra presto.
