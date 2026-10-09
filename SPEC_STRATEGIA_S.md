# SPEC — STRATEGIA S (fonte di verità per SAFE)

> Trascrizione fedele dell'artifact indicato dall'utente in `STRATEGY S.txt`
> (https://claude.ai/code/artifact/7652e448-f013-4c25-856c-9243221573c1), estratta il 14/09/2026.
> Questo file è **la specifica contro cui va certificata SAFE**. Se il codice diverge, è il codice
> che è sbagliato — salvo le eccezioni esplicite in fondo.

## REGOLA TRASVERSALE DECISA DALL'UTENTE (14/09/2026)

> **I minuti di ingresso NON sono una fascia chiusa, sono una soglia: «A PARTIRE DAL minuto X».**
> Quindi `55–62′` si legge **«dal 55′ in poi»**, `48–50′` → **«dal 48′ in poi»**,
> `66–70′` → **«dal 66′ in poi»**. Il limite superiore della fascia NON è un veto d'ingresso.
> Restano invece vincolanti i minuti di **USCITA** (80–83′, 70–75′, 83′), che sono soglie di chiusura.

Idea comune alle 4 varianti: sfruttare lo spostamento delle quote nel secondo tempo/set quando una
squadra o un giocatore è avanti e mantiene il controllo del gioco.

---

## 1 · CALCIO — BASE  (BANCA / lay · mercato 1X2)

Nel secondo tempo, quando la squadra favorita per quota è in vantaggio e domina il gioco, si
**banca (lay) la squadra che sta perdendo**. Si vince se quella squadra continua a perdere o pareggia.

| Parametro | Valore |
|---|---|
| Minuto ingresso | **dal 55′** (riferimento ideale 60′) |
| Punteggio richiesto | **1-0 · 2-1 · 2-0** |
| Quota favorita (pre-match) | **1.40–1.80** |
| Quota sfavorita (pre-match) | **4–8** |
| Quota di entrata (live) | **1.20–1.34** — ⚠️ **su QUALE selezione: vedi il riquadro qui sotto** |
| Condizione extra | la **favorita** deve avere il **controllo del gioco** |

> ### ⚠️ PUNTO AMBIGUO NEL MANUALE — «quota di entrata 1.20–1.34» riferita a chi?
>
> **Il manuale originale non lo dice**, e i suoi stessi numeri si contraddicono. Segnalato da
> `admin-fa` il 14/09 con la prova aritmetica; la mia prima trascrizione diceva «sulla selezione
> bancata» — **era una mia interpretazione, non il testo**, ed è stata tolta.
>
> L'esempio del manuale dice: *«Banchi la Squadra Sud a quota **1.28** con €100 di responsabilità →
> profitto max ≈ **€28**»*. I due numeri non possono stare insieme:
> - bancando a 1.28 con 100 € di responsabilità la puntata sarebbe 357,14 € e il **profitto massimo
>   357,14 €**, non 28;
> - un profitto di 28 € con 100 € di responsabilità corrisponde a una banca a quota **4,57** —
>   che cade dentro la banda «quota sfavorita **4–8**» dello stesso manuale;
> - 28 € di profitto su 100 € è invece **esattamente una PUNTATA di 100 € a 1.28**: l'autore ha
>   calcolato come se puntasse, e ha scritto «banchi».
>
> **Argomento decisivo, e non è aritmetico:** una squadra che sta **perdendo** 0-1 al 60′ non quota
> mai 1.28. 1.20–1.34 è il prezzo di chi sta **vincendo**.
>
> **LETTURA A (quella che il codice già implementa, `favLive`)** — 1.20–1.34 è la quota **live della
> FAVORITA**, usata come filtro di ingresso: entro solo se il mercato conferma che la favorita è
> davvero in controllo. La banca avviene poi sulla squadra che perde, al suo prezzo di mercato.
>
> **LETTURA B** — 1.20–1.34 è il prezzo a cui si banca. Incompatibile con il fatto che la selezione
> bancata sta perdendo, e incompatibile con la banda 4–8 dello stesso manuale.
>
> **DECISIONE OPERATIVA: vale la LETTURA A** finché l'utente non dice il contrario. Certificare
> contro la Lettura B dichiarerebbe non conforme un codice corretto e renderebbe la strategia
> inattivabile. → portato all'utente come punto aperto.

**Uscita in profitto**
- La favorita segna il **2° gol** → cashout, quasi massimo profitto.
- Nessun 2° gol ma si arriva all'**80°–83°** → esci comunque (gli schemi saltano nel finale).
- Il controllo passa alla sfavorita → esci in pari o piccola perdita, non rischiare oltre.

**Uscita in perdita**
- La sfavorita **pareggia** → accetta subito la perdita, NON aspettare un secondo gol a favore.
- Perdita tipica **8–12%** dello stake (fino al **20%** se si è usciti dai parametri base di selezione).
- Attendi **20–60 secondi** che le quote si stabilizzino prima di uscire.

**Cartellino rosso**: alla sfavorita è neutro/positivo. Alla favorita vale «mezzo gol subito» →
si esce nel 90% dei casi.

---

## 2 · CALCIO — RISULTATO ESATTO  (BANCA / lay · mercato Risultato Esatto)

Variante conservativa: invece del 1X2 si **banca «Altro risultato Casa/Ospite»** (Any Other Home/Away Win)
nel mercato Risultato Esatto. Ci si assicura contro un poker di gol della squadra già avanti.

| Parametro | Valore |
|---|---|
| Minuto ingresso | **dal 48′** |
| Punteggio richiesto | **0-0 · 1-0 · 1-1 · 2-1** |
| Squadra da bancare | chi ha segnato **al massimo 1 gol** |
| Quota di entrata | **30–70** |
| Condizione extra | quella squadra **NON** deve avere il controllo — **opposto della Base** |
| Selezione aggiuntiva | scontri diretti senza troppi 2-2/3-3, difesa avversaria solida |

**Uscita in profitto**: nessun altro gol della squadra bancata → esci comunque entro il **70°–75°**.

**Uscita in perdita**: la squadra bancata segna comunque (es. 1-0 → 2-0) → esci e accetta.
Perdita tipica **50–70%** dello stake (molto meno della Base: serve ancora un gol prima della
soglia di pericolo dei 4 gol totali).

---

## 3 · TENNIS  (PUNTA o BANCA · vincente incontro)

Stessa logica senza pareggio: **punti (back) chi sta vincendo** oppure **banchi (lay) chi sta perdendo**
— equivalenti, si sceglie il più comodo.

| Parametro | Valore |
|---|---|
| Momento ideale | **1° set vinto + 2–3 game di vantaggio nel 2°** |
| Quota punta (back) | **≈1.03** |
| Quota banca (lay) | **1.18–1.34** |
| Capitale iniziale | ≈200 € |
| Da evitare | finali, doppi, match troppo equilibrati, sfavoriti estremi |
| Rischio unico | **ritiro per infortunio = perdita totale dello stake** |

**Uscita in profitto**
- Chi vince prende anche il **game successivo** → cashout se non si vuole rischiare oltre.
- Per il massimo profitto (più rischio): si aspetta la fine del match.

**Uscita in perdita**
- Chi vince perde il **game successivo** → uscita conservativa con perdita ridotta.
- Se perde **due game di fila** e si arriva al **pareggio nel set** → uscita **OBBLIGATORIA, senza eccezioni**.
- Perdite dal **5%** fino al **25%** del capitale con quote molto sbilanciate.

**Ritiri**: chi si ritira perde automaticamente, anche da 5-0. Operare coi profitti già accumulati,
guardare il match, evitare gli Slam maschili (al meglio dei 5 set).

---

## 4 · CALCIO — VARIANTE PUNTA  (PUNTA / back · mercato 1X2)

Specchio della Base: si **punta (back) la favorita che sta già vincendo con due gol di scarto**.
Serve più margine perché un back vince solo se quella squadra **vince la partita** — niente rete di
sicurezza sul pareggio.

| Parametro | Valore |
|---|---|
| Minuto ingresso | **dal 66′** |
| Punteggio richiesto | **2-0 · 3-1 · 3-0** |
| Quota di entrata | **1.03–1.10** |
| Condizione extra | aspetta **3–4′ dopo il gol**: la favorita deve continuare a spingere |

**Uscita in profitto**
- Arriva il gol successivo → cashout, profitto pieno.
- Nessun altro gol ma controllo saldo → esci comunque entro l'**83°**.

**Uscita in perdita**
- La favorita **subisce un gol qualsiasi** (2-0 → 2-1) → esci **immediatamente**, anche se si sta
  ancora «vincendo» su Betfair.
- Il pareggio **non è coperto**: ogni gol subito avvicina alla perdita totale dello stake.

---

## DIFFERENZE CHIAVE (da non confondere in fase di implementazione)

1. **Controllo del gioco**: nella Base e nella Punta serve che la squadra *protetta* abbia il
   controllo. Nel **Risultato Esatto la condizione è INVERTITA**: la squadra **bancata** non deve
   avere il controllo.
2. **Base = lay** (copre anche il pareggio) · **Variante Punta = back** (paga solo la vittoria netta,
   quindi serve margine di 2 gol e uscita a ogni gol subito).
3. Il **Risultato Esatto** è l'ingresso più anticipato (dal 48′) e con la quota più alta (30–70).
4. Nel tennis l'equivalente del pareggio è il **pareggio nei game del set in corso** → uscita tassativa.
5. **Disciplina comune a tutte e quattro**: quando scatta la condizione di uscita in perdita si esce
   **subito**, mai sperare in un ribaltamento.

## ECCEZIONI GIÀ DECISE DALL'UTENTE (non sono difformità)

- **Minuti di ingresso «a partire da»** (vedi regola trasversale in testa).
- **Quota di entrata 1.20–1.34 = quota LIVE DELLA FAVORITA** (Lettura A), decisione dell'utente del
  14/09. È quello che il codice già fa (`favLive`). **Punto chiuso.**
- **QUOTA DI BANCA: NESSUN LIMITE.** Decisione dell'utente del 14/09, presa **avendo davanti il numero**
  (trade `base` bancato a 24,0: 46 € di responsabilità per 2 € di profitto, rapporto 23:1 contro il
  3,6:1 dell'esempio del manuale) e **confermando** la stessa decisione del 13/09. La banda 4–8 del
  manuale resta un **profilo descrittivo della sfavorita, non un filtro d'ingresso**.
  **Non è una difformità: è una scelta. ARGOMENTO CHIUSO, non va riaperto.**
- **STAKE FISSO, non responsabilità fissa.** Decisione dell'utente del 14/09, presa **avendo davanti il
  numero** (responsabilità reale da 46 € a 128 € per gli stessi 2 € di stake) e **confermando** la
  stessa decisione del 13/09. Conseguenza da accettare consapevolmente e da **non** trattare come bug:
  la «perdita tipica 8–12 % dello stake» del manuale **non è comparabile fra due trade** a quote diverse.
  **ARGOMENTO CHIUSO, non va riaperto.**
  *(Nota tecnica: su OMEGA la questione non si pone — lo stake non è un parametro, è derivato dal target:
  `s = target / (1 − c)`, `omega_engine.py:232-240`.)*
- Le eventuali difformità già discusse e accettate in `Betfair/safe_strategy/CERTIFICAZIONE_2026-09-13.md`
  vanno rilette e **riconfermate una per una** contro questo documento: se non c'è una decisione
  esplicita dell'utente, valgono i parametri qui sopra.
