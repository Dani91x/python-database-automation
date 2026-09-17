# SESSIONE LIVE — BOT TENNIS · 14/09/2026
**La storia del bot, per poterla ricostruire.** Punto 7 del goal dell'utente.

> Regola di questo registro: **si scrive quello che è successo, con i numeri, anche quando è brutto.**
> Un registro che racconta solo le operazioni riuscite non serve a certificare niente.

---

## ACCENSIONE — 15:20-15:45

| | |
|---|---|
| Modalità servizio | `live` (`safe_strategy_control.mode`) |
| Strategie in LIVE | **solo `tennis`**. `base`, `esatto`, `punta`, `model`, `manual` → `paper` |
| Mike / Omega | `paper` sulle proprie righe di control. `MIKE_LIVE_ENABLED` assente |
| Stake | **`stake.backSize = 3,00 €`** — è questo che muove il tennis |
| *(secondo motore)* | `risk.model_stake = 3,00 €` — governa le **opportunità** di modello, che restano in paper |
| Entrate | **automatiche** (`auto_trade_tennis = true`; era **spento**) |
| Uscite | **cancelletto acceso** (`tennis_exit_approval = true`): le approva l'operatore in Control Room |
| Cap di responsabilità | **spenti** per decisione dell'utente (`daily_liability_cap = 0`, `max_open_trades = null`) |
| **Unico freno rimasto** | **`daily_loss_stop = −50,00 €`** |
| Interruttore globale | `LIVE_ORDER_MODE` portato da `PAPER` a **`LIVE`** (`.env`) |
| Kill switch globale | `LIVE_KILL_SWITCH` assente → `false` |

> **NOTA 17/09 sera (reperto Pieczonka v Trungelliti, event_id 36077210).** La riga
> «Entrate | automatiche (`auto_trade_tennis = true`)» qui sopra si leggeva, a torto, come
> l'interruttore delle entrate della **Strategia S tennis** (quella che ha piazzato quel
> 14/09). Non lo è mai stato: `auto_trade_tennis` governa SOLO il **secondo motore** — le
> righe `strategy='model'`, `meta.kind='tennis'` della riga *(secondo motore)* appena sopra
> (`risk.model_stake`), oggi sempre in paper. La Strategia S tennis (righe `strategy='tennis'`)
> si accende esclusivamente da `params.variants` (qui: «Strategie in LIVE: solo `tennis`»).
> La Control Room («scheda Solo tennis») forzava `auto_trade_tennis = true` a ogni avvio
> credendo servisse a queste entrate: il 17/09 sera il trader ha visto 3 righe sullo stesso
> match (2 paper del modello + 1 live della Strategia S) e ha creduto a 3 ingressi della
> stessa strategia. Corretto in `frontend/src/components/controlroom/soloTennis.ts`
> (la scheda non tocca più `auto_trade_tennis`) e in `Betfair/safe_strategy/bot_service.py`
> (etichette `mode` sulle righe di attività `exit_hold`/`exit_wait`/ecc., prima timbrate col
> modo del servizio anche per un trade paper).

### Cosa ha bloccato l'avvio, e perché è istruttivo
I primi **6 tentativi di ordine live fallirono tutti** con `live_order_mode_non_live:PAPER`.
**Non era la strategia**: i nove controlli passavano tutti. Era il freno globale nel `.env`, che il
percorso REST non può scavalcare **per progetto**. Tre tentativi con backoff, poi `place_exhausted`.

> **Il bot si è comportato bene anche mentre falliva**: ha ritentato con backoff, ha registrato il
> motivo per esteso su ogni riga, e si è fermato invece di insistere. Il difetto era di
> configurazione, non di codice — e si è visto **subito** perché il motivo era scritto, non dedotto.

### Due riavvii, e perché sono serviti entrambi
| ora | cosa entrava |
|---|---|
| 15:20 | il **cancelletto** (`1c0b8de`, pushato alle 15:11) — già dentro, funzionante |
| 15:45 | `LIVE_ORDER_MODE=LIVE` · **catena dei tempi** (`9c996fc`) · **stake visibile** (`951cd71`) |

Il codice pushato **dopo** l'avvio di un processo non è nel processo: `9c996fc` è delle 15:25, i
processi erano partiti alle 15:20. Cinque minuti di differenza, e i tempi non si registravano.

---

## CONDIZIONE 4 — ADERENZA ALLA STRATEGIA · verificata

Riscontro completo in **`RISCONTRO_TENNIS_2026-09-14.md`**. Tre riferimenti **ricontrollati dal
coordinatore sul sorgente**, non presi per buoni:

| controllo | atteso dalla specifica | nel codice | esito |
|---|---|---|---|
| 1 set di vantaggio + 2 game | `setsLeadMin 1`, `gamesLeadMin 2` | `engine.py:220-221` | ✓ |
| quota back ≈1.03 | banda `1.01–1.10` | `engine.py:222-223` | ✓ |
| un solo set giocato | `setsPlayedMax 1` | `engine.py:233` | ✓ |
| doppi esclusi · Slam maschili esclusi | `excludeDoubles`, `excludeBestOf5` | `engine.py:224,228` | ✓ |
| **uscita obbligatoria**: due game di fila **E** pareggio nel set | le due condizioni in **AND** | `exits.py:1002` | ✓ |
| take profit solo sopra 1.03 | sotto è una perdita garantita | `exits.py:1005-1011` | ✓ |
| uscita al game perso | **facoltativa** nel manuale → default spento | `exits.py:1014` | ✓ |

**⊘ Finali non escluse.** Causa per nome: **Betfair non pubblica il turno per il tennis** — verificato
su **399 mercati in 3 giorni**, zero con `final/semi/quarter/round/R16/QF/SF`. Non è codice mancante:
è un dato di terzi che non esiste. L'euristica «finale = ultima partita della competizione»
scambierebbe i quarti per finali. **Decisione dell'utente, in sospeso.**

### Prova sul campo in paper, stessa giornata
8 operazioni su 6 partite, **−0,05 €** (pareggio). Le tre regole che contano, viste funzionare:
- tre ingressi a **1,01–1,02** → **portati a fine partita**, il take profit non è scattato (+0,04 · +0,02 · +0,04);
- un ingresso a **1,06** → take profit a 1,03 con profitto **vero**: netto **+0,06**;
- un ingresso a **1,02** → **uscita obbligatoria** a 1,14: **−0,21 = −10,5 %** dello stake, dentro la banda 5-25 % del manuale.

> Sei partite non dicono niente sulla **redditività**. Dicono tutto sul **comportamento** — che è la
> metrica stabilita quando l'utente ha confermato lo **stake fisso**: con quello, la «perdita tipica
> 8-12 %» non è comparabile fra due trade a quote diverse, quindi **si certifica il comportamento,
> non la percentuale**.

---

## LA CATENA DEI TEMPI — cosa si misura, e perché sette istanti e non uno

```
 t0  quote lette da Betfair      payload.odds_ts_ms
 t1  riga scritta sul feed       safe_strategy_scan.updated_at
 t2  riga LETTA dal bot          payload.t2_letto_ms        ← latenza invisibile a chi guarda solo le quote
 t3  DECISIONE presa             payload.decided_at
 t4  ordine inviato              meta.esecuzione.t4_inviato
 t5  risposta di Betfair         meta.esecuzione.t5_risposta
 t6  fill confermato             meta.t6_fill
```
`esecuzione.betfair_ms` = t5−t4, **l'unico tratto che non dipende da noi**.
Con un totale soltanto si vede *che* c'è un collo di bottiglia; con sette istanti si vede **dove**.

**Sospetto dichiarato prima della misura** (così non lo si può aggiustare dopo): il tratto grosso sarà
**t1→t2**, cioè il ritardo del database più la cadenza del ciclo. Ragione: la fase più lenta dello
scanner è la **scrittura su Postgres** (152 ms sul 95° percentile), non Betfair.

### Scorrimento del book sulle chiusure — la domanda esatta dell'utente
Su ogni riga di chiusura: `meta.price_segnale` (chiesto) · `esecuzione.price_medio` (ottenuto) ·
`esecuzione.scorrimento_tick` (**positivo = ho pagato di più**, stesso verso per back e lay) ·
`esecuzione.livelli` (size entrata a ciascun livello: **una riga = tutto al best**, due o più = l'uscita
ha pagato più del segnale).
⚠️ In live Betfair **non** restituisce il dettaglio per livello: si conserva la fotografia del book
all'invio come `livelli_previsti`, **etichettata previsione, non fatto**.

---

## OPERAZIONI LIVE

> Cinque operazioni (positive o negative) chiudono il goal. Si annota **ognuna**, con i tempi e lo
> scorrimento, anche quelle che vanno male — soprattutto quelle.

| # | ora | partita | lato | prezzo segnale | prezzo ottenuto | scorr. | stake | esito | t0→t6 | note |
|---|---|---|---|---|---|---|---|---|---|---|
| — | — | *in attesa del primo segnale live* | | | | | | | | |

## CHIUSURE APPROVATE

| # | ora proposta | ora clic | prezzo proposta | prezzo al clic | prezzo abbinato | scorr. | bloccato | note |
|---|---|---|---|---|---|---|---|---|
| — | — | *nessuna ancora* | | | | | | |

---

## COSA SORVEGLIA LA SENTINELLA
Ogni 15 s, e **emette su ogni evento, non solo sulle buone notizie**: nuovo ordine (prezzo, size),
cambio di stato, **errore con il motivo**, proposta di chiusura (motivo, urgenza), prezzo medio e
scorrimento all'abbinamento, **bot senza battito oltre 90 s**, **bot che esce dalla modalità live**.
*Un filtro che tace su un guasto non distingue «tutto bene» da «sono morto».*
