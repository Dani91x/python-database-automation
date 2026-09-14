# RISCONTRO CALCIO — le tre varianti contro `SPEC_STRATEGIA_S.md`

> Pacchetto [3.1]. Verifica parametro per parametro delle tre varianti calcio
> (Base, Risultato Esatto, Punta) contro la specifica, al commit `90a72cc` del
> 14/09/2026. **Non si migliora: si verifica, e dove il codice diverge si
> corregge il codice.**
>
> Metodo: tre verifiche indipendenti, una per variante, ognuna obbligata a
> citare `file:riga` per ogni affermazione. I punti caldi sono stati poi
> ricontrollati a mano. Le righe dove i tre verificatori concordavano fra loro
> valgono più delle altre, e sono segnate.

## La scala dei verdetti

Quattro verdetti, non tre — la distinzione fra le ultime due è **operativa**:
una si chiude scrivendo codice, l'altra no.

| | significato |
|---|---|
| **✓ CONFORME** | il codice fa quello che dice la specifica, ed è fissato da un test |
| **⊗ DA PROVOCARE** | manca, e **si può fare oggi**: è lavoro, non attesa |
| **⊘ NON ESERCITABILE** | implementato ma **non attivo perché manca un dato di terzi**. Si chiude quando arriva il dato, non scrivendo codice. Va sempre con la **causa per nome**. |
| **▣ ECCEZIONE DECISA** | difforme dal manuale **per scelta esplicita del proprietario del capitale**. Non è un difetto. Argomento chiuso. |

Una casella `⊘` senza la causa scritta accanto è un buco travestito da diagnosi.

---

## 1 · CALCIO BASE — banca (lay) la squadra che perde, mercato 1X2

### Ingresso

| voce della specifica | valore nella specifica | nel codice | valore nel codice | test | verdetto |
|---|---|---|---|---|---|
| Mercato | 1X2 | `engine.py:886` | `MATCH_ODDS` | `test_engine.py:362` | ✓ |
| Lato | BANCA (lay) | `engine.py:882` → `1699` → `bot_service.py:3494` → `execution.py:320` | `lay` fino all'exchange, nessun punto della catena lo inverte | `test_engine.py:266`, `:870` | ✓ |
| Selezione bancata | la squadra che perde | `engine.py:861-888` | la sfavorita pre-match, che il check `score` impone anche in svantaggio | `test_engine.py:263`, `:309`, `:868` | ✓ |
| Minuto ingresso | dal 55′ | `engine.py:190` | 55, soglia aperta | `test_engine.py:271`, `:277` | ▣ soglia · valore ✓ |
| Punteggio | 1-0 · 2-1 · 2-0 | `engine.py:191`, check `engine.py:789` | identico, orientato sulla favorita | `test_engine.py:282` | ✓ |
| Quota favorita pre-match | 1.40–1.80 | `engine.py:192-193`, check `engine.py:812` | 1.4–1.8, estremi inclusi | `test_engine.py:290` | ✓ |
| Quota sfavorita pre-match | 4–8 | `engine.py:194-195`, check `engine.py:813` | 4–8 | **`test_cert_2026_09_13.py` §11** (nuovo il 14/09) | ✓ |
| Quota di entrata live | 1.20–1.34 sulla **favorita** (Lettura A) | `engine.py:196-197`, check `engine.py:840` | 1.2–1.34 sul back della favorita | `test_engine.py:286` | ▣ · banda ✓ |
| Quota di **banca** | nessun limite | nessun filtro (`engine.py:867`: basta che il lay esista) | nessun limite; unico tetto indiretto `max_liability_per_trade` | `test_engine.py:349` | ▣ |
| **Controllo del gioco alla favorita** | **obbligatorio** | `engine.py:783` + `control_check` `engine.py:704`; default `engine.py:188` `requireControl: False` | implementato, **spento** | `test_cert_2026_09_13.py` §9 | **⊘** — causa: **statistiche IPS (corner/cartellini) non disponibili dal provider**; copertura in misura dal 14/09 |
| Dimensionamento | responsabilità fissa | `engine.py:240`, `:1699` | stake fisso 2 €, responsabilità derivata | `test_engine.py:871` | ▣ |

**Controlli in più rispetto alla specifica** (tutti restringono, nessuno allarga): in-play `engine.py:779`; mercato aperto `engine.py:839`; punteggio stabile ≥30 s `engine.py:851`; nessun rosso alla favorita all'ingresso `engine.py:853`; lay disponibile `engine.py:867`.

### Uscite

| voce della specifica | valore | nel codice | verdetto |
|---|---|---|---|
| Profitto — la favorita segna il 2° gol | cashout | `exits.py:953` | ✓ (ma vedi ⚠️ sotto) |
| Profitto — nessun 2° gol, si arriva all'80°–83° | esci comunque | `exits.py:69` (80), `exits.py:963` | valore ✓ (ma vedi ⚠️) |
| Profitto — **il controllo passa alla sfavorita** | esci in pari o piccola perdita | `_controllo_perso` `exits.py:925`, regola `exits.py:957`; parametri `exits.py:78-79` | **implementata il 14/09**, prima non esisteva. Nasce spenta → **⊘** stessa causa |
| Perdita — la sfavorita pareggia | accetta subito | `exits.py:951` (copre pareggio e sorpasso, ed è il primo controllo) | ✓ |
| Perdita — non aspettare un secondo gol a favore | — | `exits.py:951` precede `:953` | ✓ |
| Perdita — attendi 20–60 s | ritardo | `exits.py:72` = 30 s, applicato `bot_service.py:1775` | ✓ |
| Rosso alla **favorita** | esci | `exits.py:956`, lato = favorita via `position_side` `exits.py:679` | ✓ |
| Rosso alla **sfavorita** | neutro | nessun ramo: il codice **distingue** i due casi | ✓ `test_exits.py:159` |
| Perdita tipica 8–12 % | descrittivo | nessun controllo | ▣ — conseguenza diretta dello stake fisso: la percentuale **non è comparabile fra due trade a quote diverse**, quindi non è una metrica di certificazione |

---

## 2 · CALCIO RISULTATO ESATTO — banca «Altro risultato Casa/Ospite»

### Ingresso

| voce della specifica | valore | nel codice | valore nel codice | test | verdetto |
|---|---|---|---|---|---|
| Mercato e lato | LAY su Risultato Esatto | `engine.py:964-968` | `LAY` su `CORRECT_SCORE`, prezzo = **solo** il lay | `test_engine.py:370`, `:415` | ✓ |
| Minuto ingresso | dal 48′ | `engine.py:203` | 48, soglia aperta | `test_engine.py:380` | ▣ soglia · valore ✓ |
| Punteggio | 0-0 · 1-0 · 1-1 · 2-1 | `engine.py:204`, check `engine.py:919` | identico, e in **qualsiasi orientamento** (`score_in_list_any_order`, `engine.py:174`) | `test_engine.py:400`, `:183` | ✓ |
| Squadra da bancare | chi ha segnato ≤1 gol | `engine.py:205`, check `engine.py:912` | `side_goals <= 1` | `test_engine.py:391` | ✓ |
| Quota di entrata | 30–70 | `engine.py:206-207`, check `engine.py:943` | 30–70, estremi inclusi, sul lay | `test_engine.py:386`, `:405` | ✓ |
| **Controllo INVERTITO** — la bancata NON deve averlo | **obbligatorio** | `engine.py:906` chiama `control_check(..., side, deve_avere=False, ...)` — **`side` è la squadra BANCATA, non la favorita**. Tre chiamate distinte, non una copia. | inversione corretta su entrambi gli assi (quale squadra, e in che verso) | `test_cert_2026_09_13.py` §9 e §11 | logica ✓ · **⊘** stessa causa |
| Selezione aggiuntiva | scontri diretti senza troppi 2-2/3-3, difesa solida | nessuna occorrenza in tutto `Betfair/safe_strategy/` | assente | — | **⊗ DA PROVOCARE** — non manca un dato di terzi: manca il codice. È un filtro di selezione delle partite, allarga il paniere, non sbaglia un ordine già preso |
| Dimensionamento | responsabilità fissa | `engine.py:242` | stake fisso (a quota 70: 138 € di responsabilità per 2 € di stake) | `test_bot_service.py:2122` | ▣ |

### Uscite

| voce | valore | nel codice | verdetto |
|---|---|---|---|
| Profitto — entro il 70°–75° | soglia | `exits.py:70` = 72, regola `exits.py:973` | valore ✓ (ma vedi ⚠️) |
| Perdita — la bancata segna comunque | esci e accetta | `exits.py:970` — solo il gol del lato bancato, il gol dell'altro non muove nulla | ✓ `test_exits.py:186` |
| Perdita — incondizionata | sì | `loss` ∉ `PROFIT_KINDS`: **mai filtrata dal modello** | ✓ |
| Perdita tipica 50–70 % | descrittivo | nessun controllo | ▣ (come sopra) |

**Punto da guardare, non una difformità.** Sullo **0-0** entrambi i lati hanno 0 gol e passano il check: nascono due candidati, e a fermare il doppio ordine è solo la guardia «un solo lato per evento» (`bot_service.py:3363`, `:3469`). *Quale* dei due si banchi è deciso dall'ordinamento della chiave (`engine.py:1458`), cioè **alfabeticamente** → l'ospite. Deterministico, ma arbitrario: la condizione che sceglierebbe con un criterio — chi **non** ha il controllo — è proprio quella spenta. Accendendola, la scelta torna motivata.

**Fragilità segnalata, non corretta.** Il riconoscimento di «Any Other Home/Away Win» nello scanner (`scanner.py:186`) è una regex **solo inglese**, mentre `bot_service.py:2015` prevede anche `altro`. Se il catalogo tornasse in italiano la variante resterebbe muta per sempre — non pericolosa, ma invisibile. Non l'ho toccata: allargare una regex di riconoscimento selezioni senza una prova che il feed mandi l'italiano introdurrebbe un rischio peggiore di quello che chiude.

---

## 3 · CALCIO PUNTA — punta (back) la favorita avanti di due gol

### La trappola, verificata per prima

La Punta è un **back**: non ha la rete di sicurezza del pareggio. La specifica impone di uscire a **qualsiasi** gol subito, «anche se si sta ancora vincendo su Betfair».

**✓ CONFORME, e per costruzione.** `exits.py:980`: `if dog > dog_e` — «l'altra squadra ha segnato almeno una volta da quando siamo dentro». Non è un confronto col pareggio, non è un confronto col P&L. È la **prima** condizione della funzione, quindi su 2-0 → 3-1 nello stesso giro vince la perdita. E non passa dal gate a modello (`bot_service.py:2220`: i kind diversi da `profit`/`time` escono subito), né dal backoff dei ritentativi (`bot_service.py:1579`, `loss` è urgente). **Nessuna decisione può tenerla.**

Unica precisazione onesta: l'uscita parte a **+30 s** dal gol, non all'istante (`exits.py:72`, `bot_service.py:1775`). È una necessità dell'exchange dichiarata a `exits.py:49` — dopo un gol il mercato è sospeso, e un ordine inviato subito fallirebbe in live o userebbe in paper un prezzo che non esiste più. Rientra nella finestra 20–60 s che il manuale stesso concede alla Base.

### Ingresso

| voce | valore | nel codice | valore nel codice | test | verdetto |
|---|---|---|---|---|---|
| Lato | PUNTA (back) | `engine.py:1069` → `bot_service.py:3561` | `BACK` end-to-end | `test_engine.py:444` | ✓ |
| Selezione | la favorita in vantaggio | `engine.py:1037`, `:1070`; check `leadFav` `engine.py:1008` impone `lead == fav` | ✓ | `test_engine.py:443`, `:495` | ✓ |
| Minuto ingresso | dal 66′ | `engine.py:213` | 66, soglia aperta | `test_engine.py:448` | ▣ soglia · valore ✓ |
| Punteggio | 2-0 · 3-1 · 3-0 | `engine.py:214`, check `engine.py:991` | orientato sul leader: uno 0-2 conta come 2-0 per l'ospite | `test_engine.py:495` + **`test_cert_2026_09_13.py` §11** (3-1 e 3-0, nuovi il 14/09) | ✓ |
| Quota di entrata | 1.03–1.10 | `engine.py:215-216`, check `engine.py:1040` | estremi inclusi, sul back del leader | **`test_cert_2026_09_13.py` §11** (nuovo il 14/09) | ✓ |
| Aspetta 3–4′ dopo il gol | ≥3′ | `engine.py:217`, check `engine.py:1055` | 3′ | `test_engine.py:454`, `:459` | ✓ |
| **La favorita deve continuare a spingere** | **obbligatorio** | `engine.py:987` + `control_check` | implementato, **spento** | `safeStrategy.test.ts` §controllo | **⊘** stessa causa |
| Riferimento pre-KO | non citato | `engine.py:979`, `:1008` | senza `pre_ko` la variante esce `nd` e non scatta mai | `engine.py:1652` lo dichiara | ✓ (requisito di dato) |
| Dimensionamento | responsabilità fissa | `engine.py:243` | stake fisso | — | ▣ |

**Aggiunta rispetto alla specifica, e aiuta:** il check `noRedLead` (`engine.py:1028`) blocca l'ingresso se chi si punta ha un rosso. Su un back a 1,03–1,10 il guadagno massimo è il 3–10 % dello stake contro una perdita potenziale del 100 %: giocare quel rapporto con la squadra puntata in dieci è il caso peggiore esatto della strategia. È applicato **solo se il dato cartellini è esposto**, quindi non spegne la strategia quando il feed tace (`test_engine.py:489`).

### Uscite

| voce | valore | nel codice | verdetto |
|---|---|---|---|
| Profitto — arriva il gol successivo | cashout | `exits.py:982` | ✓ (ma vedi ⚠️) |
| Profitto — entro l'83° | soglia | `exits.py:71` = 83, regola `exits.py:985` | valore ✓ (ma vedi ⚠️) |
| Perdita — **qualsiasi** gol subito | esci immediatamente | `exits.py:980` | ✓ — vedi sopra |
| Rosso alla favorita | **non previsto per la Punta** | nessun `_red_to` in `_decide_punta` | ✓, ed è esplicitamente testato (`test_exits.py:219`) |

---

## ⚠️ Il punto che vale per tutte e tre, e che non è mio da decidere

Le uscite in **profitto** e **a tempo** (`profit`, `time` ∈ `PROFIT_KINDS`, `exits.py:122`) passano dalla **decisione a modello** (`bot_service.py:1808` → `decide_time_exit` `exits.py:415`). Con il P&L bloccato negativo e una probabilità di perdere ≤ 2 %, il modello può rispondere **HOLD** e tenere la posizione fino al settlement.

La specifica dice «esci **comunque**» all'80°–83° (Base), «entro il 70°–75°» (Esatto), «entro l'**83°**» (Punta). Il codice può non uscire.

**Non lo classifico né come difformità da correggere né come eccezione decisa**, e la ragione è precisa: questa deviazione è stata discussa e accettata dall'utente il 13/09 (`CERTIFICAZIONE_2026-09-13.md` §6.4), ma la specifica del 14/09 impone in coda (righe 181-183) che **ogni eccezione vada riconfermata una per una contro questo documento**, e questa non è fra le tre riconfermate. È l'unica riga di tutto il riscontro che aspetta una parola dell'utente.

Le uscite in **perdita**, il **rosso** e l'**obbligo del tennis** restano incondizionate in ogni caso: nessuna decisione a modello può tenerle. Il danno possibile è un mancato incasso, mai una perdita non fermata.

---

## Cosa è cambiato il 14/09 per effetto di questo riscontro

1. **Il controllo del gioco esiste**, su entrambi i motori, con l'inversione del Risultato Esatto — prima non era implementato in nessuna variante.
2. **L'uscita della Base «il controllo passa alla sfavorita» esiste** — era l'unica uscita preventiva della Base e non c'era: fra l'ingresso e il pareggio della sfavorita non esisteva nessuna via d'uscita anticipata.
3. **Un solo numero per due motori**: `pressure_index` lo calcola lo scanner e viaggia nel payload. Nessun ricalcolo locale di ripiego, nemmeno dove sarebbe possibile — una rete che esiste da un lato solo non è una rete, è una divergenza.
4. **La pagina dichiara che il filtro non sta girando**, invece di ometterlo. Una scheda di segnale può nominare solo i filtri che hanno effettivamente girato su quella riga: l'omissione si legge come «superata».
5. **La parità dei due motori è meccanica**: un test legge i default dal sorgente TypeScript e li confronta con quelli Python, e nomina il parametro che diverge.
6. **Quattro bande del manuale non erano difese da nessun test** (sfavorita 4–8, entrata Punta 1.03–1.10, punteggi 3-1 e 3-0, inversione del Risultato Esatto end-to-end). Ora lo sono, e ogni nuovo test è stato **falsificato** spostando il parametro e verificando che diventi rosso.

## Cosa resta aperto

| | cosa | causa | chi lo chiude |
|---|---|---|---|
| **⊘** | controllo del gioco spento nelle tre varianti, e uscita della Base che ne dipende | statistiche IPS (corner/cartellini) del provider: copertura non ancora misurata — al 14/09 ore 11:20 nessuna partita in gioco | il tempo: il servizio misura da solo e scrive la copertura fra le attività come MISURA ogni 300 s |
| **⊗** | «selezione aggiuntiva» del Risultato Esatto (scontri diretti, difesa solida) | manca il codice, non il dato | si può fare |
| ⚠️ | uscite a tempo filtrate dal modello | decisione dell'utente del 13/09, non riconfermata contro la specifica del 14/09 | l'utente, con una parola |
| — | regex inglese per «Any Other …» nello scanner | nessuna prova che il feed mandi l'italiano | da riaprire solo con una prova sul campo |
