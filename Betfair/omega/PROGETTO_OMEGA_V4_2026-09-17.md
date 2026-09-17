# PROGETTO OMEGA V4 — «due ingressi per partita, ma a un prezzo che paga»

> 17/09/2026. Documento di **progetto** (gradini §1-§2 di `PROCESSO_STANDARD_BOT.md`: si
> progetta, si mappa; il codice viene dopo). **Nessuna riga del bot toccata**: gli unici file
> nuovi sono **tre strumenti di misura in sola lettura** (`Betfair/omega/tools/misura_prezzo_appaiata.py`,
> `superficie_liability.py`, `ev_per_liability.py`), i due JSON che producono in
> `Betfair/omega/data/`, e questo testo. Nessuna migrazione, nessun processo, nessun commit.
>
> Costruito sulla tesi del coordinatore (`Betfair/omega/VISIONE_OMEGA_V4_COORDINATORE_2026-09-17.md`,
> §1-§9) e sugli ordini dell'utente del 17/09 (`CRONOSTORIA.md`, «Decisioni dell'utente (17/09)»).
>
> **Regola di lettura.** Ogni numero qui è (a) misurato da uno script riproducibile di cui si
> cita il comando, (b) copiato da un referto precedente di cui si cita il file, oppure
> (c) marcato esplicitamente **«da misurare in Fase X»**. Non c'è una terza categoria.
> Ogni affermazione sul codice porta `file:riga`.

---

## INDICE — dove sta ogni punto del mandato

| mandato | sezione |
|---|---|
| preambolo: l'ordine · la tesi · lo stato di partenza · le misure | **§A · §B · §C · §D** |
| **il confronto fra le due misure di oggi e il criterio di arresto** | **§D.4** |
| 1. il motore predittivo live | **§1** |
| 2. la selezione continua e la quotazione viva | **§2** |
| 3. sospensioni, gol, chiusura del mercato | **§3** |
| 4. le uscite come proposte | **§4** |
| 5. massività, finestre, cap, dimensionamento | **§5** |
| 6. consapevolezza e sicurezze | **§6** |
| 7. piano di costruzione a fasi | **§7** |
| 8. rischi, non-promesse, decisioni dell'utente | **§8** |
| sintesi per la Control Room | **§9** |

## A. L'ORDINE, E COSA QUESTO PROGETTO NE FA

Ordine dell'utente del 17/09 (h11:30, riportato in `CRONOSTORIA.md`):

- **M2 sì** — «sfruttare la potenza dei dati che si aggiornano partita dopo partita; non ci sono
  tutti i dati per tutte le partite: studia o simula su una partita per tarare i pesi».
- **B1 sì, "intelligente"** — «in live il punteggio cambia e il tempo è dalla nostra parte →
  algoritmo predittivo avanzato per stimare il risultato a nostro vantaggio; il bot gestisce le
  SOSPENSIONI (ordine annullato) e i risultati IMPOSSIBILI (non più realizzabili) e ricalcola
  continuamente la miglior selezione».
- **B2 sì** — uscite come **proposte** approvate dall'utente, mai chiusure automatiche.
- **C sì «ma veloce»** — replay massivo → paper → live piccolo.
- **Massività** — autorizzato a cambiare finestre d'ingresso e tetto di quota **dopo studio
  documentato**, «per fare più ingressi possibili con la maggior probabilità di profitto».
- **Restano**: due ingressi per partita (1T `HALF_TIME_SCORE`, 2T `CORRECT_SCORE`).

E l'osservazione del 17/09 h12, che è il perno del timing: **«senza gol le quote delle scoreline
improbabili salgono e per chi banca diventano più difficili»**.

Questo progetto risponde con **una misura, non con un'opinione**, a tre domande in fila:
1. esiste un **prezzo** a cui bancare la coda ha valore atteso positivo? (§D.1: sì, ed è misurato)
2. quel prezzo si può **ottenere**? (§D.2: a volte, e la quota di fill è misurata)
3. quando e dove conviene **offrirlo**? (§D.3 e §5: superficie quota/liability per minuto)

---

## B. LA TESI IN UNA PAGINA — che cosa cambia da v2/v3 a v4

Omega **vende opzioni binarie fuori dal denaro** sul risultato esatto. Incassa un premio piccolo
e paga la liability se la scoreline esce. Il profitto di lungo periodo viene da una sola formula:

```
EV per gamba      = s · (1 − c) · (1 − 1/k)          k = p_implicita(prezzo OTTENUTO) / p_vera
EV per liability  = (1 − c) · (1 − 1/k) / (L − 1)
```

La prima riga dice che **la quota non entra nel valore atteso** (entra nella varianza). La
seconda dice che **entra eccome nel rendimento del capitale a rischio**: a parità di margine,
una quota più bassa rende di più per ogni euro di liability. Sono le due facce dell'ordine
dell'utente «non mi interessa la quota» e «senza gol le quote salgono e diventano più difficili»,
e non sono in contraddizione: la prima riguarda *se* si guadagna, la seconda *quanto capitale
serve per guadagnarlo*.

| | v2 (in produzione, `strategy_version=2`) | v3 (16/09, mai collegata al servizio) | **v4 (questo progetto)** |
|---|---|---|---|
| prezzo d'ingresso | **taker FOK** sul best `availableToLay` (`omega_market.py:666`) | taker FOK | **quotazione viva**: si prende se il mercato è già oltre il nostro prezzo di riserva, altrimenti si **appoggia** |
| margine richiesto | `p_sel < p_implied`, cioè **k = 1 → EV zero** (`omega_model.py:560`) | `k ≥ 2` al prezzo del tocco → **non apre mai** (misurato: 0 gambe su 2 partite) | `k ≥ k_soglia` **al prezzo che chiediamo noi**, che è la variabile di controllo |
| dimensionamento | `s = target_di_giornata/(1−c)` (`omega_engine.py:225`) → ordini da 131 € | stake fisso 1 € (`omega_config.py:214`) | **liability fissa per gamba**: `s = liability/(L−1)` |
| finestre | 20'-40' / 50'-80' (`omega_config.py:60-63`) | 25'-44' / 55'-85' (`omega_config.py:227-230`) | **da misura** (§5): quotazione dal 1' e dal 46', ammissibilità decisa dal margine, non dall'orologio |
| tetto di quota | `[20, 120]` (`omega_config.py:24-25`) | idem + cap di liability | **cap di liability** (per gamba, partita, giorno) al posto del tetto di quota |
| selezione | P più bassa fra chi passa il cancello | idem | **EV per unità di liability** fra chi passa il cancello |
| uscite | green-up automatico (`omega_service.py:4989`) | proposta (`omega_v3.proposta_uscita`) | **proposta**, con il default «si tiene fino al regolamento» |
| modello | Poisson-DC + mistura log-normale cv 0,30 (`omega_model.py:300`) | Gamma-Poisson vincitore del banco (`omega_v3.py:266-392`) | Gamma-Poisson **+ hazard gerarchico per lega, rossi, fusione col mercato pesata anche sul tempo dall'ultimo evento** |

**La differenza che conta.** v2 e v3 discutono di *quale cella* bancare. La misura di oggi dice
che il problema principale non era quello: **è il prezzo**. A parità di cella, di modello e di
fascia, il margine passa da 0,8x a 2,0-2,9x solo cambiando il punto del libro in cui si sta
(§D.1, quote pre-match). v4 è il progetto che rende il prezzo una **variabile di controllo** del
bot invece di un dato subìto.

⚠️ **E la differenza che potrebbe annullarla**: il prezzo migliore si ottiene **aspettando**, e
chi accetta la nostra offerta sceglie. Il referto M1 misura un fattore **2,5x** di selezione
avversa sulle celle abbinate. **Prezzo e selezione si moltiplicano**: §D.4 mette le due misure a
confronto e scrive il criterio per cui questo progetto **non si costruisce**.

---

## C. STATO DI PARTENZA — verificato di persona, `file:riga`

### C.1 Che cosa esiste già e funziona

| cosa | dove | stato |
|---|---|---|
| motore puro v3 (5 modelli, fusione, cancello k, proposte) | `Betfair/omega/omega_v3.py` (943 righe) | **scritto e verde**, 41 test falsificati (`test_omega_v3_2026_09_16.py`) |
| innesto engine → v3 | `omega_engine.py:1089-1191` (`seleziona_v3` `:1120`, `selezione_da_v3` `:1184`, `cap_di_gamba_v3` `:1112`) | scritto; **chiamato solo dal replay e dai test** |
| 17 parametri v3 | `omega_config.py:205-247`; `resolve_params` forza `greenup_mode='off'` con `strategy_version>=3` (`:331-334`) | scritti, default `strategy_version=2` (`:210`) |
| controlli di certificazione v3 | `Betfair/omega/certificazione.py` A8-A12, C5, G1, G2 + famiglia **K1-K6** | scritti; K1-K6 sollecitati **1.466 volte, 0 violazioni** (`CHECKPOINT_V3_2026-09-16.md` passo 6) |
| scenari di replay | `tools/replay_registrazioni.py`, **14 scenari** (`SCENARI` `:964-1025`), fra cui `v3` `:1018` e `rifiuti-betfair` `:1024` | funzionanti |
| banco comune | `Betfair/stream/backtest/banco_comune.py` | coda `_piq`, cancel, lapse alla sospensione, orologio ancorato al `publish_time`, bet delay: **c'è tutto** (§C.3) |
| **ordine appoggiato reale** | `omega_market.place_order_live(..., fill_or_kill=False)` (`omega_market.py:620`), già usato in produzione da Mike (`Betfair/mike/service.py:1091-1095`) | **il mattone di rete esiste già**: v4 non inventa un percorso d'ordine |
| coda proposte | `migrations/omega_proposte_uscita_2026-09-16.sql` (tabella `omega_requests` `:30-38`, RPC `omega_request_approve` `:106`, `omega_request_ignore` `:151`, `get_omega_proposte` `:189`) | **APPLICATA dall'utente il 17/09** (`CRONOSTORIA.md` checkpoint 6: «M5 `get_omega_proposte()` e `omega_requests` rispondono») |
| UI delle proposte | `frontend/src/lib/omegaProposte.ts:143,172,182`; `components/controlroom/SchedaChiusuraOmega.tsx:25`; `useControlRoom.ts:383-388` | **pronta e in attesa**: nessun produttore Python scrive righe |

### C.2 Che cosa manca (e che questo progetto deve costruire)

1. **Nessun ramo v3/v4 dentro `omega_service.py`**: `strategy_version` non compare in tutto il
   file (6.162 righe). Il raccordo è da fare per intero.
2. **Nessuna quotazione viva**: Omega piazza sempre FOK (`omega_market.py:666`); non ha stato di
   «ordine appoggiato vivo», né annullo/ripiazzo, né rilettura alla riapertura.
3. **Nessun produttore di proposte**: `omega_requests` è viva nel DB e inerte nel codice.
4. **La consapevolezza è scritta in un punto solo** (`omega_service.py:1490-1498`,
   `X.aggiorna_trade(..., consapevolezza=...)`); i rami flumine (`_flumine_confirm:1982`,
   `_poll_one_flumine_live_trade:2177`) usano `db.update_trade` diretto → **reperto R-C1**, è
   esattamente il difetto trovato su Safe il 17/09 (`CRONOSTORIA.md` checkpoint 8).
5. **Reperti aperti del motore di oggi**, trovati dal replay del 16/09 e mai chiusi:
   **J3** ×2 (il ref `omega-t1` del piazzamento non è riconducibile a nessuna riga con
   `customer_ref_for`) e **J6** ×1 (abbinato 0,0 su 7,01 chiesti senza attività `place_parziale`).
6. **Fonti dati ferme**: `omega_minute_transitions` e `omega_ht_ft_transitions` ferme all'11/09;
   `betfair_market_odds` ultimo `run_date` 11/09 (`PROGETTO_OMEGA_V3_2026-09-16.md` §2).

### C.3 Che cosa il banco simula davvero (e cosa no) - il perimetro della certificazione

Verificato riga per riga su `banco_comune.py`:

| componente | come | riga |
|---|---|---|
| coda passiva | `SimulatedOrder._piq` = size già presente al nostro prezzo sul lato opposto; consumata dal **volume scambiato** (`trd`), **metà per lato** (`traded_size/2`), la coda davanti prima di noi | `banco_comune.py:437-462`; flumine `simulatedorder.py:230-239, 457-497` |
| ordine appoggiato | `place_order_live(..., fill_or_kill=False)` → `LimitOrder` senza `timeInForce` | `banco_comune.py:504, 546` |
| **il movimento del prezzo NON riempie** | `config.simulation_available_prices = False` (default flumine): serve volume scambiato. Ramo **prudente**, dichiarato | dichiarato in `tools/misura_ingresso_passivo.py:54-57` |
| annullo | `cancel_order_live(bet_id, market_id, size_reduction)`, latenza `cancel_latency` 0,170 s, esito **riletto** dall'ordine (`size_cancelled` delta) | `banco_comune.py:630-687, 704-727` |
| lapse alla sospensione | `_lapse_alla_sospensione` a OGNI transizione verso `SUSPENDED` con `inPlay=True`; `_lapse_al_fischio` al passaggio in gioco; `PERSIST` sopravvive | `banco_comune.py:1420-1473, 1397-1418, 1490` |
| sospeso ≠ chiuso | `CLOSED` intercettato **prima** di tutto (`_process_close_market`, `return`); `SUSPENDED` prosegue il giro | `banco_comune.py:1372-1374` |
| orologio | ancorato al `publish_time`, reso **monotono** (su `35833626` il 47,3 % dei book arriva più vecchio, salti fino a 182 s) | `banco_comune.py:1057-1095, 1732-1741` |
| bet delay | si pompano book finché `elapsed > place_latency + betDelay`; interruttore di falsificazione `ATTESA_ESATTA` | `banco_comune.py:1510-1578, 1140` |
| rifiuti Betfair | `place_rifiuto` → `PlaceResult(ok=False, order_status="EXPIRED", bet_id=None)`, nessun ordine a mercato | `banco_comune.py:513-528` |
| **NON simula** | place-and-trim e minimo di giurisdizione .it; `replace_order`; `persistence_type` diverso da `LAPSE`; settlement dal book chiuso; `CHECK` delle migrazioni | `banco_comune.py:68-72, 148-175`; assenza di `replace_order` verificata |

**Conseguenza di progetto, dichiarata subito**: v4 usa **cancel + place** (mai `replaceOrders`) —
che è anche la scelta già fatta dal risk engine (`Betfair/stream/risk_engine_worker.py:684`) —
proprio perché il `replace` **non è certificabile sul banco**. E usa **`LAPSE`**, l'unica
persistenza che il banco riproduce.

---

## D. LE MISURE DI OGGI — la base di prova

Tre misure, due delle quali **nuove di questo progetto** e riproducibili con un comando.

### D.1 M0 — Il margine esiste, ma solo a un certo prezzo (misura APPAIATA, 48.280 selezioni)

> Comando: `python -m Betfair.omega.tools.misura_prezzo_appaiata --boot 2000`
> Codice: `Betfair/omega/tools/misura_prezzo_appaiata.py` (nuovo, sola lettura)
> Dati: `Betfair/omega/data/prezzo_appaiato_2026-09-17.json`

**Perché serviva.** `K_MISURATO_2026-09-16.md` confronta k al prezzo di lay (tabella a) con k
alla probabilità devigata (tabella b) e conclude «lo spread se lo mangia tutto». Ma le due
tabelle **non sono appaiate**: i secchi della (b) sono ricostruiti sulla `p_equa`, quindi
contengono celle diverse da quelli della (a). Un confronto fra due raggruppamenti diversi non
misura il guadagno del prezzo: lo mescola con un riclassamento.

Qui i secchi sono definiti **una volta sola**, sulla `p_implicita` al prezzo di lay al tocco;
stesse celle, stessi esiti, cambia **solo** il prezzo a cui si suppone di aver bancato. Il
`k prudente` è `p_implicita_media / estremo alto del bootstrap a grappolo sulle partite`
(2.000 giri, seed fisso) — cioè il k che si può difendere, non quello che fa piacere.

**k PRUDENTE (estremo basso), per prezzo d'ingresso:**

| mercato | fascia | n sel. | partite | uscite | **tocco** | 1 tick dentro | **mid spread** | **al best back** | (devigato) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Correct Score | 0,2-0,5 % | 1.147 | 656 | 6 | 0,36 | 0,38 | 1,51 | **2,66** | 1,30 |
| Correct Score | 0,5-1 % | 2.384 | 1.183 | 22 | 0,54 | 0,58 | 1,28 | **2,03** | 1,16 |
| Correct Score | 1-2 % | 5.064 | 1.768 | 76 | 0,81 | 0,87 | 1,28 | **1,74** | 1,21 |
| Correct Score | 2-5 % | 10.669 | 1.840 | 457 | 0,74 | 0,77 | 0,93 | 1,12 | 0,92 |
| Correct Score | 5-10 % | 10.417 | 1.841 | 869 | 0,81 | 0,84 | 0,93 | 1,04 | 0,93 |
| Correct Score | > 10 % | 2.461 | 1.560 | 392 | 0,81 | 0,83 | 0,90 | 0,98 | 0,89 |
| Half Time Score | 0,2-0,5 % | 281 | 240 | 1 | 0,35 | 0,36 | 1,95 | **3,54** | 1,89 |
| Half Time Score | 0,5-1 % | 1.039 | 886 | 9 | 0,49 | 0,53 | 1,72 | **2,94** | 1,68 |
| Half Time Score | 1-2 % | 1.669 | 1.085 | 22 | 0,79 | 0,85 | 1,66 | **2,53** | 1,62 |
| Half Time Score | 2-5 % | 4.213 | 1.595 | 164 | 0,75 | 0,78 | 0,98 | 1,21 | 0,98 |
| Half Time Score | 5-10 % | 3.625 | 1.595 | 363 | 0,69 | 0,71 | 0,82 | 0,96 | 0,83 |
| Half Time Score | > 10 % | 5.048 | 1.643 | 1.061 | 0,82 | 0,84 | 0,95 | 1,07 | 0,94 |

**Quattro letture, e sono il cuore del progetto.**

1. **Al tocco il margine non c'è, in nessuna fascia**: `k prudente ≤ 0,87`. Conferma
   `K_MISURATO` §3, e conferma che il cancello di v2 (`k = 1`) apre a **EV negativo**.
2. **Un tick dentro lo spread non basta**: +4-8 %. È la leva più piccola che esista.
3. **Al miglior back il margine c'è, ed è sopra 2 nella coda**: CS <= 1 % e HT <= 2 % hanno
   `k prudente` fra 2,0 e 3,5. Sulle quote pre-match, **il `k_soglia = 2` che il progetto chiede
   sarebbe raggiunto dal PREZZO**, prima ancora che il modello dica una parola.
   ⚠️ **Necessario, non sufficiente**: questa misura suppone il fill a quel prezzo e non vede la
   selezione avversa. Il referto M1 misura un fattore **2,5x** di selezione avversa e un `k` al
   tocco **in gioco** di 0,49 contro 0,80 pre-match. Il confronto completo fra le due misure, e
   il criterio di arresto del progetto, sono in **§D.4**: va letto prima di usare questa riga.
4. **Il mid spread non è la probabilità equa** (la colonna «devigato» è quasi sempre **sotto** il
   mid): il devig toglie l'overround dell'intero mercato, il mid toglie solo lo spread di una
   selezione. Chi legge `K_MISURATO` §4 come «basta stare a metà spread» legge male: nella coda
   il mid vale 1,3-1,9, il best back 2,0-3,5.

> **Limiti dichiarati.** (a) Quote **pre-match**: è il *prior* del bias, non il bias live.
> (b) La misura suppone il **fill a quel prezzo**; il fill passivo non è certo **e non è
> casuale**. Le due leve — prezzo (qui) e fill (§3.2) — **si moltiplicano, non si sommano**.
> (c) le fasce `0-0,2 %` restano non misurabili (2 uscite su 258 selezioni).

### D.2 M1 — Il fill passivo: quanto spesso, dopo quanto, e a che prezzo (39 registrazioni)

> Comando: `python -m Betfair.omega.tools.misura_ingresso_passivo`
> Codice: `Betfair/omega/tools/misura_ingresso_passivo.py` · Dati:
> `Betfair/omega/data/ingresso_passivo_2026-09-17.json` (generato oggi, 1.632 s, 39 registrazioni,
> 1.069 candidati) — misura di **un altro delegato**, qui usata e non rifatta.

Catena: `_live_raw` → flumine → `banco_comune.replay_evento` → **scanner vero** → riga di scan
vera → ordini appoggiati simulati da `SimulatedOrder` (la stessa classe del replay), con lapse
alla sospensione e al cambio punteggio, e **bet delay non regalato**. Tre livelli di prezzo:
(a) un tick sotto il best lay, (b) mid spread al tick, (c) al best back.

| | (a) 1 tick dentro | (b) mid spread | **(c) al best back** |
|---|---:|---:|---:|
| candidati / piazzati | 357 / 337 | 356 / 352 | 356 / 355 |
| **abbinati** | 38 (**11,3 %**) | 36 (**10,2 %**) | 6 (**1,7 %**) |
| attesa mediana del fill | 73,8 s | 75,9 s | 96,8 s |
| coda davanti (mediana) | 0,00 € | 0,00 € | **9,32 €** |
| tick guadagnati (mediana) | 1 | 3 | 6 |
| **leva di prezzo misurata** (mediana, stesse celle) | **×1,06** | **×1,17** (CS) / ×1,16 (HT) | **×1,44** (CS) / ×1,41 (HT) |
| fill «attraversati» (il book è sceso sotto di noi entro 60 s) | 13 (**34,2 %**) | 7 (19,4 %) | 2 (33,3 %) |
| fill entro 120 s da un gol/sospensione | 4 (10,5 %) | 4 (11,1 %) | 0 |
| k passivo realizzato | 0,234 | 0,242 | non misurabile |

**Tre cose che questa tabella dice, e una che non dice.**

- **La leva di prezzo misurata sul book LIVE** (×1,06 / ×1,17 / ×1,44) è dello stesso ordine di
  quella pre-match di §3.1 sulla stessa popolazione di fasce (le celle di M1 stanno quasi tutte
  fra l'1 % e il 5 %, dove §D.1 dà ×1,26-1,58 a mid e ×1,52-2,16 al best back). **Le due
  misure indipendenti
  concordano**: il prezzo è una leva reale e quantificata.
- **Il prezzo migliore costa il fill**: passare da (a) a (c) moltiplica la leva per 1,36 e
  **divide la quota di abbinamento per 6,6**. È il vero compromesso di v4, e non è aggirabile.
- **La selezione avversa c'è e si misura**: un fill su tre a livello (a) è seguito, entro 60 s,
  da un book che scende sotto il nostro prezzo. `k_passivo` realizzato 0,23-0,24 su **37 esiti
  e 4 uscite**: con un intervallo a grappolo che va da 0,0 a 0,21 di `p_reale`, **quel numero non
  è una misura, è un allarme**. Va rifatto su un campione grande (Fase M1-bis).
- **Quello che NON dice**: M1 piazza ordini **discreti** su una griglia di 5 minuti, e li lascia
  vivere fino alla fine della finestra o alla morte. Non misura la **quotazione continua** — cioè
  esattamente quello che v4 farebbe. La quota di fill di una quotazione continua non è l'11 % di
  M1: **è da misurare in Fase M1-bis**, ed è il numero che decide la massività.

### D.3 M3 — La superficie quota / liability per minuto (misura nuova, 39 registrazioni)

> Comando: `python -m Betfair.omega.tools.superficie_liability --passo 5`
> Codice: `Betfair/omega/tools/superficie_liability.py` (nuovo, sola lettura)
> Dati: `Betfair/omega/data/superficie_liability_2026-09-17.json`

Ricostruisce la ladder dai `rc` **nativi** (`atb`/`atl`, con azzeramento sulle immagini `img`),
prende minuto e punteggio dal sidecar `<id>.scores.jsonl` (mai dall'orologio) e i nomi delle
celle dalla formula dei gusci sui `selectionId`; campiona **ogni 5 minuti dal 1'**, solo con
mercato `OPEN`, in gioco, runner `ACTIVE` e cella ad almeno 2 gol dal punteggio corrente.

> **Approssimazione dichiarata**: non è un replay del bot (niente flumine, niente ordini). È una
> misura di **prezzo**. La condotta si certifica solo dal banco comune.

I numeri sono in §5.1. L'anticipazione che conta: **la quota della coda sale col minuto anche
senza gol, e con essa la liability** — l'osservazione dell'utente è confermata dai dati.

---


### D.4 Le due misure a confronto — dove concordano, dove no, e che cosa resta aperto

Il referto del delegato M1 (`Betfair/omega/INGRESSO_PASSIVO_MISURA_2026-09-17.md` §0 e §5.1)
conclude che **nessuno dei tre livelli passivi basta**: il livello (a) vale +6,3 % di
`p_implicita`, (b) +16,7 %, (c) +42,9 %, e partendo da `k ≈ 0,80` «per arrivare a 2 servirebbe
+150 %: nessuno ci arriva». La misura appaiata di §D.1 sembra dire il contrario (`k prudente`
2,0-3,5 al miglior back). **Non è una contraddizione, ed è importante capire perché.**

**1. Sulla LEVA DI PREZZO le due misure concordano quasi esattamente.** M1 misura sulla
popolazione filtrata come opera Omega oggi (`price_min` 20, `price_max` 120,
`min_lay_liquidity` 5, distanza ≥ 2 gol, `parametri` del JSON di M1), che in `p_implicita`
corrisponde grossomodo alle fasce **0,5-1 %, 1-2 % e 2-5 %**. Su quelle tre fasce la misura
pre-match appaiata dà, al miglior back, una leva mediana pesata di **×1,52** (CS) — contro il
**×1,44** mediano misurato da M1 sul book **live**. Due strumenti diversi, due popolazioni
(pre-match e in gioco), lo stesso numero. **La leva di prezzo è un fatto.**

**2. La differenza sta nell'AGGREGAZIONE, non nei dati.** M1 applica **una** leva media
(+42,9 %) a **un** `k` medio (0,80) e ottiene 1,14. Ma né la leva né `k` sono costanti: **crescono
insieme** al rarefarsi della cella, perché è lì che lo spread è enorme in termini relativi. Se si
tiene la scomposizione per fascia — che è ciò che fa §D.1 — il prodotto **attraversa 1** proprio
nelle fasce di coda:

| fascia (`p_impl` al tocco) | `k` prudente al tocco | leva al miglior back | **`k` prudente al miglior back** |
|---|---:|---:|---:|
| Correct Score 2-5 % | 0,74 | ×1,52 | **1,12** |
| Correct Score 1-2 % | 0,81 | ×2,16 | **1,74** |
| Correct Score 0,5-1 % | 0,54 | ×3,76 | **2,03** |
| Half Time Score 1-2 % | 0,79 | ×3,19 | **2,53** |

**Un numero medio su una relazione non lineare dà la risposta sbagliata**: è lo stesso motivo per
cui `K_MISURATO` §4 sembrava promettere 1,53 e §3 sembrava negarlo.

**3. Su che cosa M1 ha ragione, e pesa più di tutto il resto.** Due cose che la misura pre-match
**non può vedere**, perché suppone il fill:

- **Il book IN GIOCO al tocco è peggiore del pre-match.** M1 §6.1: sulle celle in cui Omega
  opererebbe davvero, `k` complessivo al tocco vale **0,49** (IC 95 % **0,25-1,62**), contro
  0,74-0,98 pre-match. Se quel rapporto (~0,6) si trasferisse alla colonna «miglior back», le
  quattro righe qui sopra scenderebbero a 0,67 / 1,04 / 1,22 / 1,52: **solo due resterebbero
  sopra 1, e nessuna sopra 2.**
- **Chi ci prende l'ordine sa qualcosa.** M1 §7: le celle **abbinate** sono uscite il **10,3 %**
  delle volte contro il **4,1 %** di tutte le celle candidate — un fattore **2,5×** di selezione
  avversa. Un fattore 2,5 sul denominatore di `k` **cancella qualunque leva di prezzo misurata**.

**4. Quindi, in una riga.** La leva di prezzo è **necessaria** e ora è misurata due volte; **non
è sufficiente**. Il progetto v4 esiste se e solo se la selezione avversa, misurata su un campione
serio, è **sensibilmente minore** del 2,5× che M1 ha visto su 78 abbinati e 8 uscite.

| numero | stato | dove si chiude |
|---|---|---|
| leva di prezzo per fascia | **misurato due volte, concorde** | — |
| `k` pre-match per fascia e per prezzo | **misurato** (48.280 selezioni, 1.859 partite) | — |
| `k` **in gioco** per fascia | 293 celle, 20 partite, 12 uscite: IC 0,25-1,62 | **Fase M6** |
| **selezione avversa** | 78 abbinati, 8 uscite: 2,5×, IC enorme | **Fase M1-bis** |
| `phi`, quota di fill di una quotazione **continua** | mai misurato | **Fase M1-bis** |

> **Il criterio di arresto, scritto prima di cominciare.** Se la Fase M1-bis dà una selezione
> avversa che, moltiplicata per il `k` al nostro prezzo, lascia l'estremo basso dell'intervallo
> **sotto 1** in tutte le fasce, **v4 non si costruisce** — e si scrive, come il 16/09 si è
> scritto per il tocco.
---

## 1. IL MOTORE PREDITTIVO LIVE (mandato §1)

### 1.1 La forma del modello, e la letteratura da cui viene

Tutto stima la stessa cosa: la distribuzione dei **gol residui** `(dh, da)` dal minuto corrente
alla fine del periodo (45'+recupero per la gamba HT, 90'+recupero per la FT), dato il punteggio
corrente. Da lì la probabilità di **ogni** selezione del mercato — scoreline **e** aggregati
«Any Unquoted / Any Other» — è una somma di celle della griglia.

| pezzo | fonte | perché serve qui | dov'è oggi |
|---|---|---|---|
| forze di attacco/difesa, gol come Poisson | **Maher 1982**, *Statistica Neerlandica* 36 | la base: λ per squadra | `omega_v3.py:266` (`intensita_residue`) |
| correzione dei punteggi bassi `tau(0-0, 1-0, 0-1, 1-1)` | **Dixon & Coles 1997**, *Applied Statistics* 46(2) 265-280 | sull'`HALF_TIME_SCORE` quelle quattro celle sono quasi tutta la massa | `omega_v3.py:220` (`_tau_dc`); ρ per lega **non** stimato per lega |
| intensità **dipendente dal tempo e dal punteggio** | **Dixon & Robinson 1998**, *The Statistician* 47(3) 523-538 | l'hazard cresce verso fine tempo; chi è sotto attacca | `omega_v3.py:179-216` (profilo `exp(c1·u + c2·u²)`; misurato `c1 = 0,410` → al 90' l'intensità vale `e^0,41 = 1,5x` quella d'inizio) e `beta_squilibrio` `:284-286` |
| componente comune (correlazione positiva) | **Karlis & Ntzoufras 2003**, *The Statistician* 52(3) 381-393 | da provare, non da assumere | `omega_v3.py:249` — **misurato `lambda3 = 0,000` in entrambi gli split: i dati lo rifiutano.** Resta nel banco come controprova, non nel motore |
| **sovradispersione + apprendimento in corsa** | Gamma-Poisson coniugato, predittiva **binomiale negativa** | il tasso di una squadra è incerto e ogni gol visto lo aggiorna | `omega_v3.py:239` (`_negbin_pmf`), `:291-299` (posteriore `Gamma(a+gol, a/mu+esposizione)`) |
| modelli in-play a intensità piena | **Titman, Costain, Ridall & Gregory 2015**, *JRSS-C* 64(1) | la forma completa dell'in-play (effetti per squadra, dipendenza dallo stato) | **non implementato** — estensione, Fase 2 |
| effetto **cartellino rosso** | **Vecer, Kopriva & Ichiba 2009**, *J. of Quantitative Analysis in Sports* 5(1) | un rosso cambia le due intensità in modo asimmetrico e immediato | **assente in `omega_v3.py`**; esiste nel v2 via `live_engine.inplay_residual_rates` (Costituzione §11). **Da portare** |
| fusione col mercato | **Satopää et al. 2014**, *Int. J. of Forecasting* 30(2): il pool **logaritmico** batte la media aritmetica | il book sa formazioni, infortuni, soldi | `omega_v3.py:410-427` (`peso_fusione`, `fondi_col_mercato`), pesi per fascia misurati |

**Il banco ha già scelto il vincitore, fuori campione, sui nostri dati** (1,07 M transizioni da
~1,4 M partite in `omega_minute_transitions`; due split indipendenti: metà stati, e 30 leghe
contro 30). Comando: `python -m Betfair.omega.tools.banco_modelli --max-iter 600`.

| modello | log-loss OOS (split leghe) | **coda P < 2 %** |
|---|---:|---:|
| **Gamma-Poisson (vincitore)** | **1,93221** | **4,91797** |
| Dixon-Robinson 1998 | 1,93301 | 5,01694 |
| bivariato Karlis-Ntzoufras 2003 | 1,93307 | 5,01757 |
| v2 di produzione (DC + mistura log-normale cv 0,30) | 1,93904 | 5,01360 |
| Dixon-Coles 1997 | 1,93921 | 5,02951 |
| Poisson indipendente | 1,93929 | 5,03001 |

Parametri stimati e versionati in `Betfair/omega/data/parametri_vincenti_2026-09-16.json`:
`forma_gamma` 13,34 (→ `cv = 1/sqrt(a) = 0,27`), `profilo_c1` 0,410, `profilo_c2` 0,007,
`rho` −0,029 (contro il **−0,13 cablato** in `omega_model.py:41`), `gol_totali` 2,768,
`quota_casa` 0,564, `beta_squilibrio` −0,013.

**E la calibrazione della coda dice la cosa che conta per chi banca**
(`data/calibrazione_coda_2026-09-16.json`, rapporto `P prevista / P osservata`):

| fascia di P prevista | Gamma-Poisson | v2 in produzione |
|---|---:|---:|
| < 0,1 % | **1,15** (prudente) | **0,81** (sottostima di un quinto) |
| 0,1-0,2 % | 1,11 | 0,91 |
| 0,2-0,5 % | 1,11 | 0,95 |
| 0,5-1 % | 1,08 | 1,01 |
| 2-5 % | 1,02 | — |

> Il modello di **oggi** sottostima la probabilità proprio nelle celle rarissime dove Omega
> banca: e quando si sottostima la probabilità di un lay, il conto si paga con la liability
> intera. Il Gamma-Poisson sbaglia **dalla parte prudente**, che per un layer è l'unica in cui
> si può sbagliare. È il motivo tecnico per cui v4 adotta quel modello.

### 1.2 Che cosa aggiunge v4 (e che oggi non c'è)

| # | aggiunta | perché | come si misura che serve |
|---|---|---|---|
| **P1** | **hazard gerarchico per lega** (Poisson gerarchica con shrinkage verso il globale): `gol_totali`, `profilo_c1`, `rho` per lega | `dc_rho_by_league.json` copre **20** leghe, il resto usa ρ = −0,13 cablato mentre il fit globale dà −0,029 | log-loss OOS con split **per lega** (già nel banco): l'aggiunta vale solo se migliora con IC che esclude 0 |
| **P2** | **effetto rosso** (Vecer et al. 2009): moltiplicatore asimmetrico sulle due intensità residue | un rosso al 30' cambia tutto e `omega_v3` non lo vede | stima sulle transizioni con il flag rossi; controprova: log-loss OOS sui soli stati con `rossi > 0` |
| **P3** | **limite superiore, non centro** (`p_sup`): l'incertezza del modello entra nel numero che si usa | `omega_v3` prende il massimo fra modello fuso e dato storico (`omega_v3.py:607`), ma il **modello** entra col suo centro; il meccanismo esiste già nel v2 (`omega_model.uncertainty_p:425`, `select_k_se` oggi **0**, `omega_config.py:106`) | falsificazione: con `k_se = 0` i numeri del referto A10 devono cambiare |
| **P4** | **peso della fusione anche per TEMPO DALL'ULTIMO EVENTO**, non solo per fascia | il mercato è affidabile in regime stazionario, meno subito dopo un gol/rosso/rigore: è lì che il modello vale di più — ed è anche lì che si rischia la selezione avversa | `tools/banco_fusione.py` con la variabile «secondi dall'ultimo evento» |
| **P5** | **calibrazione della coda applicata** (isotonica per fascia, monotona), non solo misurata | oggi `calibrazione_coda_*.json` è un referto, non un pezzo del motore | la stessa tabella ricalcolata **dopo** la correzione deve dare rapporti ~1 e mai < 1 |
| **P6** | **fiducia della fonte lambda dentro il `cv`**: fixture/tactical alta, `market_grid` media, `live_ou` bassa | oggi la fonte è solo scritta nell'audit (`omega_model.audit_block:600`) e non cambia nulla; con M2 diventa la leva che rende il bot **prudente da solo** quando i dati mancano — `cv` più largo → `p_sup` più alto → `L*` più basso → meno ingressi | calibrazione per fonte di lambda |
| **P7** | **monitoraggio online di `k` realizzato, con CUSUM per fascia** | è l'antidoto strutturale alla maledizione dell'ottimizzatore, già fallita quattro volte qui (−5,3 % / −8,0 % / −3,5 % / −6,1 %) | scenario di replay che inietta una deriva e pretende che la fascia si spenga da sola |

### 1.3 Il prezzo di riserva — dove il modello diventa un ordine

Per ogni cella ammissibile, a ogni tick:

```
p_sup(t) = limite SUPERIORE della probabilita' della cella (modello fuso, calibrato, mai
           sotto la P empirica di omega_minute_transitions quando n >= n_min)
L*(t)    = (1 - c) / (p_sup(t) * k_soglia) + c
```

`L*` è la **quota più alta** alla quale bancare quella cella conserva il margine `k_soglia`. Si
ricava invertendo `p_implicita(L) = (1-c)/(L-c) >= p_sup · k_soglia`: lo stesso metro con cui `k`
è stato misurato (`omega_v3.p_implicita:475`, `misura_k.p_implicita:94`). **Nessuna formula
nuova: la stessa, scritta al contrario.**

Tre proprietà, che sono le richieste dell'utente in forma di equazione:

1. **«Il tempo è dalla nostra parte» sulla QUOTA.** Senza gol `p_sup(t)` decade e `L*(t)` sale:
   la quota che possiamo offrire mantenendo il margine si avvicina da sola al mercato. Chi non
   ricalcola `L*` a ogni tick non ha questo effetto: è la differenza fra un ordine «appoggiato e
   dimenticato» e una **quotazione viva**.
2. **«Il tempo è dalla nostra parte» sulla POSIZIONE.** Una lay già abbinata vede la probabilità
   del suo evento decadere ogni minuto senza gol: è la *theta* dell'opzione venduta e si incassa
   **tenendo**, non chiudendo (§7).
3. **Le «due strade» sono una regola sola.** Se `best_lay <= L*` si **prende subito**; altrimenti
   si **appoggia** a `min(L*, best_lay - 1 tick)` arrotondato al tick, che compare sul lato
   `availableToBack` come miglior offerta per chi punta.

#### 1.3-bis Il tempo, misurato: di quanto migliora il margine restando fermi

Due misure indipendenti, da incrociare.

**(a) Quanto sale la quota di MERCATO della stessa cella, senza gol** (39 registrazioni, coppie
di campioni a 5 minuti di distanza con punteggio invariato; comando: la misura M3 di §D.3 e
l'analisi delle traiettorie sulle sue osservazioni grezze (§D.3)):

| mercato | fascia | n coppie | quota ×, mediana | media |
|---|---|---:|---:|---:|
| Correct Score | 0,5-1 % | 377 | **×1,200** | 1,309 |
| Correct Score | 1-2 % | 580 | ×1,133 | 1,286 |
| Correct Score | 2-5 % | 930 | ×1,074 | 1,241 |
| Half Time Score | 0,5-1 % | 105 | **×1,333** | 1,583 |
| Half Time Score | 1-2 % | 132 | ×1,442 | 1,662 |
| Half Time Score | 2-5 % | 197 | ×1,304 | 1,619 |

**L'osservazione dell'utente è confermata dai dati**: senza gol la quota della coda sale, e sale
molto più in fretta sull'Half Time Score (il periodo residuo si accorcia in proporzione più in
fretta). Quota che sale = `p_implicita` che scende = **margine al tocco che peggiora**, a parità
di modello.

**(b) Quanto scende la P del MODELLO nello stesso intervallo** (Gamma-Poisson coi parametri
vincenti, funzione pura `omega_v3.griglia_finale`, celle a 2-3 gol di distanza):

| mercato | cella | minuto | P → P(+5') | rapporto |
|---|---|---:|---|---:|
| Correct Score | 2-1 da 0-0 | 51' | 4,18 % → 3,44 % | 0,823 |
| Correct Score | 3-1 da 0-0 | 51' | 1,15 % → 0,84 % | 0,736 |
| Correct Score | 3-1 da 1-0 | 56' | 3,81 % → 3,00 % | 0,789 |
| Half Time Score | 2-1 da 0-0 | 11' | 2,29 % → 1,71 % | 0,747 |
| Half Time Score | 2-0 da 0-0 | 11' | 5,65 % → 4,84 % | 0,858 |
| Half Time Score | 2-1 da 0-0 | 26' | 0,73 % → 0,38 % | 0,521 |

**Il confronto (a)÷(b) è il numero che decide se aspettare paga:**

| | mercato calibrato? | `p_impl` ×/5' | `p_modello` ×/5' | **margine ×/5'** |
|---|---|---:|---:|---:|
| Correct Score, 0,5-2 % | il modello decade più in fretta | 0,83-0,88 | 0,74-0,79 | **≈ +14 %** |
| Correct Score, 2-5 % | idem | 0,93 | 0,82 | **≈ +13 %** |
| Half Time Score, 1-2 % | il mercato tiene il passo | 0,69 | 0,69 | **≈ 0 %** |
| Half Time Score, 2-5 % | il mercato corre di più | 0,77 | 0,81 | **≈ −5 %** |

> **Conseguenza di progetto, e non è un dettaglio.** Sul **Correct Score** il margine al tocco
> migliora da solo di circa **+14 % ogni 5 minuti senza gol**: quotare presto e lasciare che il
> mercato venga al nostro prezzo è una strategia con un vantaggio misurato. Sull'**Half Time
> Score** non lo è: lì il mercato riprezza alla stessa velocità del modello, e il margine deve
> venire **tutto** dal prezzo (posizione nel libro) e dalla qualità delle λ pre-partita.
> ⚠️ **Limite**: (b) è calcolato su celle rappresentative con punteggio fisso, non appaiato cella
> per cella con (a). La versione appaiata è la **Fase M4** (§7): far girare il modello sulle
> registrazioni e misurare la deriva del margine *sulla stessa cella*. Fino ad allora questo è
> un **indizio forte**, non una misura.

#### 1.3-ter Il numero scomodo: con `k_soglia = 2` sul modello, `L*` non è raggiungibile

Dal replay in ombra del 16/09 (`CHECKPOINT_V3_2026-09-16.md` passo 5) il miglior margine offerto
**al tocco** su due partite vere era `0,78x` e `0,87x`, mediano `0,57x`-`0,70x`. Con
`k_soglia = 2`, `(L* − c)/(L_tocco − c) = margine_al_tocco / k_soglia ≈ 0,39-0,44`: il prezzo di
riserva starebbe al **39-44 %** della quota al tocco, mentre il **miglior back** misurato sta al
**48-80 %** (§5.1: leva 1,25-2,06 nelle fasce operative). **`L*` cadrebbe sotto il miglior back:
la quotazione non sarebbe mai in cima al libro e quasi mai abbinata** — ed è esattamente quello
che il replay ha visto (0 gambe aperte su 2 partite).

Ne discendono tre decisioni di progetto:

- **`k_soglia` non è una costante morale, è `max(2, k_prudente di fascia)` applicata a una
  misura** — e §3.1 misura `k_prudente` **al nostro prezzo**: 2,0-3,5 nella coda al miglior back.
  Dove il **prezzo** da solo porta `k` oltre 2, il modello **non deve aggiungere un altro 2x**.
  Il cancello si scrive sul `k` **complessivo ottenuto al prezzo che chiediamo noi**, non come
  «2x di modello sopra un prezzo che già ne vale 2». È la differenza operativa fra v3 (che non
  apre mai) e v4.
- **Il margine ha due sorgenti e nel referto vanno separate**:
  `k_prezzo = p_implicita(L_nostro) / p_implicita(best_lay)` (misurabile **senza modello**) e
  `k_modello = p_implicita(L_nostro) / p_sup`. Il prodotto non è il margine: il margine **è**
  `k_modello`; `k_prezzo` dice quanta parte di quel margine viene dal libro e quanta dal modello.
  Un referto che non separa le due non permette di sapere quale delle due sta smettendo di
  funzionare. **Controllo nuovo A13**: entrambe scritte su ogni gamba.
- Dove `L*` cade sotto il miglior back di più di `N` tick, la cella si **abbandona** invece di
  restare quotata a vuoto: è il criterio «il fill è improbabile» chiesto dall'ordine (§2.3).

---

## 2. LA SELEZIONE CONTINUA E LA QUOTAZIONE VIVA (mandato §2)

### 2.1 Il giro, a ogni tick del feed unico

A ogni giro del servizio (`run_once`, `omega_service.py:5597`, cadenza `poll_interval_s` 20 s,
`omega_config.py:35`; **da portare a 2-5 s per le gambe con una quotazione viva** — decisione
di dimensionamento, §5.6), e per ogni partita seguita:

1. **Stato vero**: minuto, punteggio, rossi, stato del mercato dal **feed unico** (riga di scan),
   mai dall'orologio (`_scan_event_legs`, `omega_service.py:1027-1049`).
2. **Insieme ammissibile** delle celle del mercato della gamba. Si escludono, con il motivo
   scritto:
   - **IMPOSSIBILI**: per una lay sull'`HALF_TIME_SCORE` dopo il 45'+recupero, e per qualunque
     cella `(h,a)` con `h < casa` o `a < ospiti` — matematicamente non più realizzabile
     (`omega_v3._seleziona:581-584`, motivo `irraggiungibile`);
   - **punteggio corrente e adiacenti**: distanza in gol `< distanza_minima` (`:585-588`);
   - runner non `ACTIVE` o senza lato lay;
   - celle già **realizzate** (la scoreline corrente): Betfair le sospende da sé, ma il bot non
     deve dipenderne.
3. **Probabilità** di ogni cella e di ogni **aggregato** «Any Unquoted / Any Other» — quest'ultima
   come **somma delle celle non quotate nella direzione giusta** (`omega_v3.probabilita_selezioni:433-471`).
   Gli aggregati sono la coda vera e oggi sono **esclusi** (`include_aggregate=False`,
   `omega_config.py:32`): v4 li include, perché il modello sa già calcolarli.
4. **Prezzo di riserva** `L*` per ogni cella (§1.3), e **EV per unità di liability**
   `(1−c)(1−1/k)/(L−1)` al prezzo che chiederemmo.
5. **Ordinamento**: non la quota più alta, non la P più bassa — **l'EV per unità di liability**
   fra le celle che passano il cancello. A parità di margine favorisce le quote basse; il bias
   vive nella coda; il compromesso lo fa il dimensionamento (§5.5), non l'ordinamento.
6. **Confronto con la quotazione viva** (§2.2) e, se serve, annullo/ripiazzo.

### 2.2 La macchina a stati della gamba quotata — copiata da Mike, non inventata

Mike ha già in produzione l'ordine appoggiato con consapevolezza, e le sue invarianti sono
certificate sul banco. **v4 le riusa una per una** (riferimenti a `Betfair/mike/`):

| invariante | come la fa Mike | come la fa Omega v4 |
|---|---|---|
| predicato unico «si può appoggiare adesso?» | `appoggiabile_in_gioco = operabile(bk) and bk.inplay` (`engine.py:521-531`) | identico, più «il mercato della gamba è OPEN e la finestra è aperta» |
| **la finestra non scorre** quando non si può appoggiare | `finestra_uscita_scaduta` torna False (`engine.py:2380-2398`, guardia `:2396`) | identico: la finestra d'ingresso non consuma minuti a mercato sospeso (difetto §7.17 del catalogo) |
| **mai due lay vive o in volo** | `lay_in_volo` = `side=='lay' and (is_live or needs_reconcile)` (`engine.py:1720-1736`); `_una_sola_lay` applicata come **ultima parola** di `decide()` (`engine.py:1770-1789`, chiamata `:1977-1978`) | identico, e come ultima parola del giro: copre anche i rami futuri. **«In volo» comprende l'esito IGNOTO** |
| «se non resta nessuna `place`, **lo stato non avanza**» | `engine.py:1786` | identico |
| **annullo in un giro, nuova quota al giro dopo a residuo 0 confermato** | il `cancel` resta fra le azioni, la `place` viene potata; la lay nuova ripassa solo quando `lay_in_volo` è di nuovo `None`, cioè dopo **conferma di Betfair** (`engine.py:1751`, `:1762-1764`) | identico. Sul banco l'annullo è vero (`banco_comune.py:630-687`) e l'esito si rilegge dal delta di `size_cancelled` (`:704-727`) |
| **isteresi**: se la lay viva ha già prezzo e size del piano, non si tocca | tolleranza `1e-9` sul prezzo e `0,01` sulla size (`engine.py:2536-2541`) | v4 ha bisogno di un'isteresi **più larga**, perché `L*` si muove di continuo: si sposta la quota **solo** se (a) cambia la cella migliore, oppure (b) `L*` si è mosso di **≥ N tick** (`quote_isteresi_tick`, proposto **2**), oppure (c) qualcuno si è messo davanti a noi di un tick e ci conviene ancora stare davanti |
| memoria dei **rifiuti** al posto del ritmo | `chiave_richiesta` ruolo\|ciclo\|mercato\|selezione\|lato\|finale; `tentativo_gia_rifiutato` confronta **anche prezzo e size** (`engine.py:1466-1499`) | identico: un book che si muove è una domanda nuova, un rifiuto identico no |

**Gli stati della gamba** (nomi di Mike, `engine.py:126` e contratto `:96-115`):
`pending` (quotata, viva a mercato) → `open` (abbinata in tutto o in parte e non più viva) ·
`cancelled` (mai abbinata, ritirata) · `pending_reconcile` (esito IGNOTO,
`STATUS_RECONCILE`, `engine.py:62`) · `settled`.
⚠️ **Reperto di progetto**: in Mike il vincolo `CHECK` di `mike_trades.status` **non ammette**
`cancelled`, e una gamba scaduta finisce `error` con `meta.reason='lapsed_alla_sospensione'`
(`service.py:1618-1654`). Prima di scrivere codice v4 va **verificato il `CHECK` di
`omega_trades.status`**: è il difetto §7.18 del catalogo («vincolo CHECK che non ammette uno
stato del motore → upsert rifiutato per 12 giorni»). **Fase 1, controllo di contratto.**

### 2.3 «Il tempo è dalla nostra parte»: quando aspettare, quando abbandonare

La regola operativa, con i numeri di §D.2 e §1.3-bis:

- **Si aspetta** quando la quotazione è **in cima al libro** (o entro `quote_coda_max` euro di
  coda davanti) e il margine sta **migliorando** col tempo. Sul Correct Score il margine al tocco
  migliora di ~+14 % ogni 5 minuti senza gol (§1.3-bis): **aspettare è una posizione, non una
  rinuncia**. Attesa mediana misurata del fill: **74-97 s** (M1).
- **Si abbandona la gamba** quando vale almeno una:
  1. `L*` è **sotto il miglior back di più di `quote_max_dietro_tick`** (proposto **3**): saremmo
     in fondo alla coda, con quota di fill misurata **1,7 %** (M1 livello c) e coda davanti
     mediana 9,3 €;
  2. la finestra della gamba si chiude (45'+recupero per l'HT; fine partita per la FT);
  3. il **modello** ha spostato la cella fuori dall'insieme ammissibile (gol, rosso);
  4. il libro è troppo sottile perché il fill sia credibile: size al nostro livello sotto
     `quote_min_profondita`.
- **Non si insegue mai il mercato**: se il best lay scende sotto `L*` si **prende** (siamo già
  oltre il prezzo di riserva); se sale, `L*` non lo segue — `L*` dipende solo dal modello.

### 2.4 Perché NON si usa `replaceOrders`

Il banco comune **non simula `replace_order`** (verificato: nessuna occorrenza in
`banco_comune.py`), mentre simula `place` e `cancel` con latenze distinte
(`place_latency` 0,120 s + bet delay; `cancel_latency` 0,170 s). Un percorso non simulabile non è
certificabile, e il catalogo §7.31 vieta di certificare su una copia. **v4 usa cancel + place**,
esattamente come il risk engine già in casa (`Betfair/stream/risk_engine_worker.py:684`,
macchina CANCEL→PLACE). Costo: un giro di ritardo per ogni spostamento — che è **già** la regola
«mai due lay».

Analogamente: **persistenza `LAPSE` e basta.** Il banco cabla `LAPSE` (`banco_comune.py:542`) e
rispetta `PERSIST` solo se un ordine ce l'ha (`:1490`); `MARKET_ON_CLOSE` non è mai emesso.
`PERSIST` renderebbe la quotazione sopravvissuta alla sospensione — cioè viva **durante** un
gol: esattamente lo scenario di selezione avversa peggiore. `LAPSE` è anche la scelta giusta di
strategia, non solo di certificazione.

---

## 3. SOSPENSIONI, GOL, CHIUSURA DEL MERCATO (mandato §3)

### 3.1 Il gol: Betfair sospende, e la nostra quota muore

Sequenza vera, misurata sulle registrazioni `35674515` / `35760084` / `35777617`
(`banco_comune.py:98-105`): `(OPEN, inPlay=False) → (OPEN, inPlay=True) → (SUSPENDED, inPlay=True)`.
Il banco riproduce **tre morti** dell'ordine appoggiato:

| morte | quando | dove |
|---|---|---|
| sospensione pre-match con cambio `version` | la fa già flumine (`size_lapsed += size_remaining`) | `simulatedorder.py:57-62`; `banco_comune.py:1466-1470` |
| **passaggio in gioco** | `_lapse_al_fischio`, **prima** del middleware che abbina | `banco_comune.py:1397-1418`, chiamata `:1386` |
| **sospensione in gioco** (gol, rigore, rosso) | `_lapse_alla_sospensione`, a OGNI transizione verso `SUSPENDED` con `inPlay=True` | `banco_comune.py:1420-1473`, chiamata `:1390` |

Esecutore comune `_uccidi_appoggiati` (`:1475-1497`): salta gli ordini non `LAPSE` (`:1490`) e
porta `size_remaining` a zero.

### 3.2 La procedura, giro per giro (modello Mike C.1-bis)

1. **All'ingresso in sospensione**, con una quotazione viva: si annota nel contesto
   `riapertura = {ts, refs, letto: False, esiti: {}}` — **persistito**, non in RAM
   (Mike: `MatchCtx.riapertura`, `engine.py:284`, persistito in `_CTX_FIELDS`,
   `service.py:253-254`; difetto §7.19 del catalogo: «stato in RAM perso al riavvio»). Attività
   `mercato_sospeso`.
2. **Non si decide niente** finché il mercato è sospeso: sospeso ≠ chiuso (catalogo §7.17). Le
   finestre **non scorrono**.
3. **Alla riapertura**, PRIMA di qualunque decisione, si **rilegge ogni ref**:
   `list_current_orders` e poi `order_state_by_bet_id(bet_id)` — il `bet_id` preso **dalla riga**,
   che quindi va salvato **sempre**, anche su un ordine non abbinato (catalogo §7.7: «`bet_id`
   salvato solo se abbinato: l'ordine appoggiato non si ritrova al giro dopo»).
   Mike: `_sorveglia_sospensione` (`service.py:1966-2019`) chiamata **prima** di `decide`
   (`service.py:3076-3077`) → `_rileggi_ordine_appoggiato` (`:1575-1615`).
4. **Riclassificazione** in cinque esiti dichiarati (`service.py:1531-1535`, logica `:1543-1572`),
   leggendo i campi veri: `size_matched`, `size_remaining` (**mai dedotto per differenza se
   Betfair lo dice**), `size_lapsed`, `size_cancelled`, `status`, `avg_price_matched`:
   - **VIVO** (residuo > 0,009 e `status != EXECUTION_COMPLETE`) → nessuna gamba nuova;
   - **ABBINATO** → la gamba diventa `open` col fill vero;
   - **PARZIALE** → posizione = abbinato, residuo 0, motivo dichiarato;
   - **SCADUTO** → gamba chiusa, attività critica `ordine_scaduto_alla_sospensione`;
   - **IGNOTO** (rete muta, `bet_id` assente, `found=False`) → `pending_reconcile` + log critico,
     e **mai** una gamba nuova (catalogo §7.36, controllo J4 di Mike).
5. **Ricalcolo della selezione col nuovo punteggio**: le celle diventate impossibili escono;
   una lay **già abbinata** su una cella diventata impossibile **è vinta al regolamento e si
   tiene** (non si copre: coprire sarebbe regalare); una **quotazione viva** su una cella diventata
   impossibile o svantaggiosa si **annulla subito**.
6. **Cool-down dopo la riapertura**: nessuna quota nei primi `quote_cooldown_riapertura_s`
   secondi (il book si riassesta e lì la selezione avversa è massima). **Valore da misurare in
   Fase M1-bis**: il tempo di riassestamento del book dopo un gol si legge dalle registrazioni.
   M1 misura già che il **10,5 %** dei fill a livello (a) avviene entro 120 s da un gol o da una
   sospensione: è la dimensione del problema.

### 3.3 Fine 1T e fine partita

- **45'+recupero**: il mercato `HALF_TIME_SCORE` si regola. La gamba HT non si quota più; la
  posizione va a settlement (`settle_open`, `omega_service.py:3036`). La gamba **2T sceglie
  sapendo l'esito del 1T**: il punteggio del 45' è un condizionamento vero, sia per il modello
  (griglia traslata) sia per la P empirica (`omega_ht_ft_transitions`).
- **Fine partita**: `CLOSED` è intercettato **prima** di tutto nel banco (`:1372-1374`); il
  settlement resta l'autorità (I3 della Costituzione), con commissione sul netto.
- **Mercato annullato / runner rimosso**: `void`, P&L 0, dichiarato.

---

## 4. LE USCITE SONO PROPOSTE, MAI CHIUSURE (mandato §4)

### 4.1 La regola, e perché è questa

Il 12/09 è stato misurato che **tutte e cinque le chiusure automatiche di Omega v2 erano
sbagliate**: −42,39 € contro +79,95 € fatti dalle aperture (memoria
`chiusure_distruggono_valore`). La ragione è strutturale e va scritta: su un lay **la liability è
già impegnata**; chiudere non riduce il rischio preso, lo **trasforma in perdita certa**. E
chiudere un lay significa **backare una longshot**, cioè stare dalla parte sbagliata dello stesso
bias che si è appena venduto.

**Default di v4: si tiene fino al regolamento.** Il bot **propone**; firma l'utente. È già quello
che `resolve_params` impone: con `strategy_version >= 3` forza `greenup_mode='off'` e
`greenup_enabled=False` (`omega_config.py:331-334`).

### 4.2 Con quali numeri si propone

`omega_v3.proposta_uscita` (`omega_v3.py:877-940`) è già scritta e falsificata. Confronta **tre**
numeri:

- `bloccabile` = quanto si porta a casa chiudendo adesso, **certo**: chiudere un lay `s` a `L`
  significa backare `sb = s·L/B`, profitto `s·(1 − L/B)` al netto (`profitto_bloccabile:732`);
- `ev_tenere = (1−p)·s·(1−c) − p·s·(L−1)` con la `p` di adesso (`ev_di_tenere:762`);
- `bloccabile_max_atteso` = il massimo della **traiettoria** del bloccabile se il punteggio
  regge, **pesato** con `p_punteggio_invariato` (`traiettoria_bloccabile:803-856`).

Si propone **solo** se chiudere ora batte sia tenere sia aspettare (oltre `margine_attesa`). In
tutti gli altri casi si tiene, **e si scrive perché**: `bloccabile_non_positivo` ·
`tenere_vale_di_piu` · `aspettare_vale_di_piu` · `controparte_insufficiente` ·
`nessun_prezzo_di_back`.

> ⚠️ **Difetto già trovato e corretto** nella stessa funzione, da non reintrodurre: guardare solo
> il ramo «non succede niente» diceva **sempre** «aspetta» e non si sarebbe mai chiuso niente
> (`CHECKPOINT_V3_2026-09-16.md` passo 3). Il valore dell'attesa va pesato con `p_invariato`.

**Si propone anche** — indipendentemente dall'EV — quando scatta un **cap** (liability aperta,
perdita giornaliera) o quando il modello vede il rischio salire oltre `proposta_p_lose_max`.
In quel caso il motivo è `cap` o `rischio`, non `profitto`: il trader deve sapere che non gli si
sta proponendo un affare, gli si sta chiedendo di ridurre il rischio.

### 4.3 Il raccordo esatto con quello che c'è già

| pezzo | dove | stato |
|---|---|---|
| tabella `omega_requests` (`kind`, `payload`, `status ∈ proposed/pending/processing/done/rejected/error`) | `migrations/omega_proposte_uscita_2026-09-16.sql:30-51` | **applicata** il 17/09 |
| indice unico «una proposta viva per gamba» su `payload->>'trade_id'` WHERE `status='proposed'` | stessa migrazione `:56-58` | applicata |
| campi del payload (28, documentati: `trade_id … proposed_at`) | `:70-99` | applicata |
| RPC `omega_request_approve` / `omega_request_ignore` / **`get_omega_proposte()`** | `:106-143`, `:151-184`, `:189-199` | applicate e **rispondono** (verifica del 17/09) |
| UI: elenco, approva, ignora, realtime | `frontend/src/lib/omegaProposte.ts:143,172,182`; `SchedaChiusuraOmega.tsx:25`; `useControlRoom.ts:383-388,407-412` | **pronta** |
| **produttore Python** | — | **NON ESISTE**: è il lavoro di Fase 3 |
| modello gemello già vivo | Safe: `Betfair/safe_strategy/bot_db.py:544-639` (`REQUEST_STATES` `:550`, insert `proposed` `:586`) | da copiare, non da inventare |

**Punti esatti nel giro** (`omega_service.py`): la proposta nasce nella fase 4 del giro, al posto
di `process_auto_greenup` (`:5650-5651`), riusando l'elenco già filtrato di
`_greenup_candidates` (`:4296-4356`) — che **esclude già** le righe manuali (`:4318-4324`), quelle
con `meta.chiuso_dall_utente` (`:4326-4333`), quelle su eventi chiusi dall'utente (`:4334-4340`) e
quelle con una chiusura in volo (`:4341-4342`). Il gate `_greenup_active` (`:4217`) diventa
`_proposte_attive`, e con `strategy_version >= 3` la **esecuzione** automatica è già spenta per
costruzione (`omega_config.py:331-334`).
**Controllo G1** (già scritto in `certificazione.py`): il servizio **non deve mai** drenare le
righe `proposed` — se lo facesse, avrebbe chiuso da solo.

---

## 5. MASSIVITÀ E FINESTRE: DOVE C'È MARGINE, E QUANTO NE ESCE (mandato §5)

### 5.1 La superficie misurata (M3, 38 registrazioni, 7.144 osservazioni, 5.210 usabili)

> Comando: `python -m Betfair.omega.tools.superficie_liability --passo 5`
> Celle a **≥ 2 gol** dal punteggio corrente, mercato `OPEN`, in gioco, runner `ACTIVE`.

| mercato | minuti | fascia | celle | partite | quota al tocco | **quota al best back** | **liability/€ al best back** | spread (tick) | leva |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| Correct Score | 1-15 | 0,5-1 % | 105 | 23 | 130 | 80 | **79** | 7 | 1,65 |
| Correct Score | 1-15 | 1-2 % | 188 | 28 | 65 | 46 | **45** | 5 | 1,37 |
| Correct Score | 1-15 | 2-5 % | 330 | 31 | 30 | 22 | **21** | 5 | 1,25 |
| Correct Score | 16-30 | 1-2 % | 141 | 27 | 65 | 48 | 47 | 4 | 1,31 |
| Correct Score | 31-45 | 1-2 % | 135 | 21 | 65 | 44 | 43 | 5 | 1,38 |
| Correct Score | 46-60 | 0,5-1 % | 69 | 20 | 140 | 75 | 74 | 8 | 1,78 |
| Correct Score | 46-60 | 1-2 % | 117 | 25 | 65 | 46 | 45 | 5 | 1,40 |
| Correct Score | 61-75 | 1-2 % | 70 | 22 | 72 | 48 | 47 | 6 | 1,42 |
| Correct Score | 76-90 | 1-2 % | 37 | 19 | 65 | 32 | 31 | 13 | 2,04 |
| Half Time Score | 1-15 | 0,5-1 % | 50 | 21 | 145 | 80 | 79 | 9 | 1,83 |
| Half Time Score | 1-15 | 1-2 % | 65 | 18 | 60 | 44 | **43** | 6 | 1,42 |
| Half Time Score | 1-15 | 2-5 % | 140 | 24 | 30 | 22 | 21 | 6 | 1,31 |
| Half Time Score | 16-30 | 1-2 % | 68 | 20 | 65 | 42 | 41 | 6 | 1,47 |
| Half Time Score | 31-45 | 1-2 % | 24 | 14 | 70 | 27 | 26 | 17 | 2,60 |

**Quante celle ci sono davvero, per partita** (la materia prima della massività):

| minuto | Correct Score: celle ammissibili/partita | di cui con `p_impl ≤ 2 %` | Half Time Score: ammissibili/partita | di cui `≤ 2 %` |
|---:|---:|---:|---:|---:|
| 1' | 10,7 | 4,5 | 5,3 | 2,1 |
| 11' | 11,8 | 4,5 | 4,9 | 2,5 |
| 21' | 11,2 | 4,3 | 4,5 | 3,1 |
| 31' | 11,2 | 5,2 | 3,5 | 2,8 |
| 41' | 10,2 | 5,5 | 1,2 | 1,3 |
| 51' | 9,5 | 5,0 | — | — |
| 61' | 7,5 | 4,5 | — | — |
| 71' | 5,1 | 3,4 | — | — |
| 81' | 3,6 | 2,5 | — | — |
| 86' | 2,4 | 1,9 | — | — |

> **Il Correct Score è quotabile dal 1' minuto**: ~11 celle ammissibili per partita, di cui ~4,5
> nella coda dove il bias è misurato, contro **2,4** all'86'. La finestra di oggi (50'-80')
> butta via i primi 50 minuti, che sono quelli con **più celle**, **book più profondo** e — per
> la stessa cella — **liability circa metà** (§1.3-bis: la quota della stessa cella sale di
> ×1,07-1,20 ogni 5 minuti senza gol sul CS).

### 5.2 Dove conviene quotare: EV per euro di liability

> Comando: `python -m Betfair.omega.tools.ev_per_liability --livello best_back --liability 30`
> Compone il `k` **prudente** appaiato di §D.1 con la quota mediana misurata di §5.1.

| mercato | fascia | k prudente (best back) | quota mediana | liability/€ | **EV per € di liability** | EV per gamba a 30 € di liability |
|---|---|---:|---:|---:|---:|---:|
| Half Time Score | **1-2 %** | 2,53 | 44 | 43 | **1,336 %** | **+0,401 €** |
| Half Time Score | 0,5-1 % | 2,94 | 75 | 74 | 0,847 % | +0,254 € |
| Half Time Score | 2-5 % | 1,21 | 23 | 22 | 0,738 % | +0,221 € |
| Half Time Score | 0,2-0,5 % | 3,54 | 100 | 99 | 0,689 % | +0,207 € |
| Correct Score | **1-2 %** | 1,74 | 46 | 45 | **0,900 %** | **+0,270 €** |
| Correct Score | 0,5-1 % | 2,03 | 80 | 79 | 0,610 % | +0,183 € |
| Correct Score | 2-5 % | 1,12 | 22 | 22 | 0,470 % | +0,141 € |
| Correct Score | 0,2-0,5 % | 2,66 | 135 | 134 | 0,442 % | +0,133 € |
| Correct Score | 0-0,2 % | 0,73 | 215 | 214 | **−0,166 %** | −0,050 € |
| Correct Score | > 10 % | 0,98 | 7 | 6 | −0,257 % | −0,077 € |

A livello **mid spread** la stessa tabella resta positiva solo in `≤ 2 %`
(CS 1-2 % 0,389 %, HT 1-2 % 0,734 %) e diventa **negativa** da 2-5 % in su: comando
`--livello mid`.

> **Tre conclusioni operative, tutte misurate.**
> 1. **La fascia migliore è 1-2 %**, su entrambi i mercati: è il punto in cui il bias è ancora
>    dimostrato e la liability è ancora bassa. Non è la coda estrema (0-0,2 %: `k` sotto 1 e
>    liability 214 € per euro di stake) e non è la zona liquida (>5 %: il mercato è calibrato).
> 2. **Fuori da `p_impl ≤ 5 %` non si opera**, e sopra `p_impl ≥ 10 %` l'EV è **negativo**
>    misurato: il tetto va messo sulla **probabilità**, non sulla quota.
> 3. **Il tetto di quota `[20, 120]` e' la variabile sbagliata**, e si vede su tre celle reali:
>    a quota **22** (fascia 2-5 %) e a quota **46** (fascia 1-2 %) il tetto lascia passare
>    entrambe, ma la prima rende **0,47 %/EUR** e la seconda **0,90 %/EUR**; a quota **120** in
>    fascia 0,2-0,5 % passa (EV 0,44 %/EUR) mentre a **135**, stessa fascia e stesso EV, viene
>    esclusa. Il tetto separa per PREZZO cio' che va separato per **probabilita'** (l'EV) e per
>    **liability** (il rischio). **Si sostituisce con: fascia di probabilita' ammessa + cap di
>    liability** (§5.5 e §5.7).

### 5.3 Le finestre proposte

| gamba | oggi (`omega_config.py:60-63`) | v3 (`:227-230`) | **v4 proposta** | perché, misurato |
|---|---|---|---|---|
| 1T `HALF_TIME_SCORE` | 20'-40' | 25'-44' | **1'-40'**, quotazione continua | celle ammissibili 5,3 al 1' contro 1,2 al 41'; spread 6 tick al 1' contro 17 al 31-45'; margine **non** migliora col tempo sull'HT (§1.3-bis) → non c'è ragione di aspettare |
| 2T `CORRECT_SCORE` | 50'-80' | 55'-85' | **1'-85'**, quotazione continua, con la gamba 2T **impegnabile** solo dal 46' | il mercato CS è aperto e in gioco **dal 1'**: 10,7 celle/partita, liability circa metà, e il margine migliora di ~+14 %/5' senza gol |

⚠️ **Un chiarimento necessario, e va portato all'utente (§8, decisione 5).** «Due ingressi per
partita, uno nel 1T e uno nel 2T» oggi significa *due mercati e due finestre temporali*. La
misura dice che il mercato `CORRECT_SCORE` (che si regola al 90') è **più conveniente da bancare
nel primo tempo** che nel secondo. Ci sono due letture possibili dell'ordine:
- **(a) letterale**: la gamba `CORRECT_SCORE` si quota solo dal 46'. Si perde la parte migliore
  della superficie;
- **(b) sostanziale**: due gambe restano due (una HT e una FT), ma la gamba FT **si può quotare
  dal 1'**. «Primo tempo / secondo tempo» descrive i due *mercati*, non il momento dell'ordine.
Il progetto **raccomanda (b) con motivo misurato**, e **non la applica senza ordine**.

### 5.4 Quanto ne esce: volume, P&L atteso, coda

Ingredienti, tutti dichiarati:

| ingrediente | valore | fonte |
|---|---|---|
| partite/giorno | **113** | ultimo giorno Betfair misurato (11/09), `PROGETTO_OMEGA_V3_2026-09-16.md` §4.2 |
| gambe per partita | 2 | ordine dell'utente |
| celle in fascia 1-2 % per partita e per momento | CS 4,5 · HT 2,5 | §5.1 |
| **quota di fill di una quotazione** | **da misurare (Fase M1-bis)** | M1 misura solo piazzamenti **discreti** di 2-3 minuti: 1,7 % al best back, 10,2 % a mid |
| EV per gamba abbinata (fascia 1-2 %, liability 30 €) | **+0,40 € (HT) / +0,27 € (CS)** | §5.2 |

Con `phi` = probabilità che una gamba quotata per l'intera finestra venga abbinata:

| `phi` | gambe abbinate/giorno | P&L medio/giorno | perdite attese/giorno | esposizione lorda cumulata/giorno |
|---:|---:|---:|---:|---:|
| 0,05 | 11,3 | +3,8 € | 0,10 | 339 € |
| **0,10** | **22,6** | **+7,6 €** | 0,19 | 678 € |
| 0,20 | 45,2 | +15,1 € | 0,39 | 1.356 € |
| 0,30 | 67,8 | +22,7 € | 0,58 | 2.034 € |

Conti per gamba in fascia 1-2 % a liability 30 € (quota 44, `k` 2,53): stake `s = 30/43 = 0,70 €`;
vincita `+0,66 €` con probabilità 99,14 %; perdita `−30 €` con probabilità **0,86 %**.
Con `phi = 0,10` (22,6 gambe/giorno, 678/mese): **P&L atteso mensile +229 €**, deviazione standard
mensile `sqrt(678·0,0086·0,9914)·30,66 = 74 €`; giorni senza alcuna perdita **82 %**, giorni con
una perdita 16 % (**−15 €**), con due 1,5 % (**−45 €**).

> **Questi sono conti analitici su ingredienti misurati, non una simulazione.** Il Monte Carlo
> vero — correlazione fra gambe della stessa partita, gol che uccidono più quotazioni insieme,
> code di liability simultanea — è la **Fase M5** (§7). E `phi` è **il numero che decide tutto**:
> fino a quando non è misurato, la colonna «P&L medio» è un'ipotesi con l'etichetta sopra.

### 5.5 Dimensionamento: liability fissa, non stake fisso

```
s = liability_gamba / (L - 1)
```

A quota 44 lo stake è 0,70 €, a quota 135 è 0,22 €: **il volume si adatta da solo alla quota e
l'esposizione resta costante**. È il contrario sia del v1 (stake dedotto dall'obiettivo di
giornata → ordini da 131,58 €, `PROGETTO_OMEGA_V3` §1.2) sia del v3 (stake fisso 1 € → liability
mediana 239-419 €, ivi §4.1).

⚠️ **Vincoli di piazza, da verificare prima**: il minimo di giurisdizione .it è **lay 0,50 €**
(Costituzione §2). A quota 135 con liability 30 € lo stake è 0,22 € < 0,50: serve il
**place-and-trim** (`omega_market.place_submin_live:794-975`, già scritto e testato) **oppure**
si accetta una liability più alta su quelle celle. ⊘ **Il banco NON simula il trim**
(`banco_comune.py:68-72`): quel ramo non è certificabile oggi. **Proposta**: in fascia 1-2 %
(quota 22-80) lo stake a liability 30 € vale 0,38-1,43 € — sotto il minimo solo sopra quota 61.
**Decisione dell'utente (§8.3)**: liability per gamba tale che lo stake resti ≥ 0,50 € senza
trim, oppure trim acceso e ⊘ dichiarato nel referto.

**Kelly frazionario** come tetto, non come motore: per un lay a quota `L` con margine, la frazione
ottimale di cassa in liability è circa `f* = edge/(L−1)`, usata **a 1/4**. Con 1-2 %, `edge`
per euro di liability 0,9-1,3 % → `f* /4 ≈ 0,2-0,3 %` della cassa per gamba. **Su una cassa da
10.000 € sono 20-30 € di liability per gamba**: coerente con i 30 € usati sopra, ma la **cassa di
riferimento la dà l'utente** (§8.3).

### 5.6 Il paniere di celle (opzione da sottoporre — §8.2)

Le scoreline di un mercato sono **mutuamente esclusive**: ne esce esattamente una. Bancandone `n`
con stake `s_i` a prezzo `L_i`, il caso peggiore **non** è la somma delle liability ma

```
caso_peggiore = max_j [ s_j (L_j - 1) - somma_{i != j} s_i (1 - c) ]
```

Con `n = 5` celle, liability 30 € ciascuna, quota ~44 (stake 0,70 € l'una): caso peggiore
`30 − 4·0,663 = 27,35 €` — **meno della liability di UNA gamba sola**, perché i premi delle altre
quattro incassano. EV `5 × 0,40 = +2,00 €` contro `+0,40 €`, e **cinque occasioni di fill invece
di una**: è la risposta matematica a «massività e qualità insieme».

Compatibilità con l'ordine: **rispetta «due ingressi per partita» se “ingresso” = gamba** (una HT,
una FT); **non lo rispetta se “ingresso” = una cella sola**. **Decisione dell'utente (§8.2).**

### 5.7 I cap proposti (al posto del tetto di quota)

| cap | proposto | perché |
|---|---:|---|
| **fascia di probabilità ammessa** | `p_impl` fra **0,3 %** e **5 %** | sotto 0,3 % `k` misurato < 1 e la liability esplode; sopra 5 % il mercato è calibrato e l'EV misurato è ≈ 0 o negativo (§5.2) |
| **liability per gamba** | **30 €** (Kelly/4 su 10.000 € di cassa) | §5.5 — è **il** numero dell'utente |
| **liability per paniere** (se §8.2 = sì) | **caso peggiore ≤ 30 €** | formula di §5.6, non la somma |
| **liability per partita** | **60 €** | due gambe al tetto |
| **liability aperta simultanea** | **da Monte Carlo (Fase M5)**, ordine di grandezza 600-2.000 € | oggi `max_open_liability = 0 = spento` (`omega_config.py:38`) |
| **perdita giornaliera** | **10 perdite** ≈ 300 € | oltre, si smette di **aprire**; le protezioni e le proposte continuano (controllo **C3**, `certificazione.py:488-496`) |
| `daily_goal` | **da motore a metrica** | dividere un obiettivo per le partite obbliga a operare dove non c'è margine: è l'anti-pattern che ha generato gli ordini da 131 € (**decisione §8.1**) |

---

## 6. CONSAPEVOLEZZA E SICUREZZE (mandato §6)

### 6.1 Gli stati, e cosa il bot deve SAPERE in ogni istante

Per **ogni** gamba, in ogni giro, il bot deve poter rispondere: *chiesto quanto · abbinato quanto ·
residuo quanto · a che prezzo medio · con quale `bet_id` e quale ref · quando l'ha detto Betfair*.
Le cinque colonne esistono già e sono condivise
(`Betfair/safe_strategy/execution.py:268-269`): `size_requested`, `size_matched`,
`size_remaining`, `avg_price_matched`, `betfair_updated_at`
(migrazione `migrations/trades_consapevolezza_ordine_2026-09-16.sql:40-51` per `omega_trades`).

| # | stato della gamba | cosa il bot sa | cosa fa | cosa la UI mostra |
|---|---|---|---|---|
| 1 | `quotata` (appoggiata viva) | ref, `bet_id`, prezzo, size chiesta, residuo = size | sorveglia; sposta solo con isteresi (§2.2) | «in attesa a quota X, Y € davanti» |
| 2 | `quotata` → **parziale** | `size_matched` z su x, residuo x−z | la posizione è z; il residuo resta vivo o si annulla secondo la cella | chiesto/abbinato/residuo/prezzo medio |
| 3 | **abbinata** | `size_matched` = size, `avg_price_matched` | gamba `open`, si tiene | «abbinata a Z» (il prezzo **abbinato**, non il chiesto) |
| 4 | **annullata dal bot** | delta di `size_cancelled` confermato | libera lo slot: solo ora può partire una nuova lay | «ritirata» |
| 5 | **scaduta alla sospensione** (`LAPSE`) | `size_lapsed`, `status` | chiude la gamba, attività critica | «scaduta al gol» |
| 6 | **rifiutata da Betfair** | `res.ok = False`, `error_code` | riga **mai viva**; memoria del rifiuto (§2.2) | «rifiutata: <codice>» |
| 7 | **esito IGNOTO** | niente | `pending_reconcile`, riconciliazione per `bet_id` → ref → ref storico **solo a mercato e selezione concordi** | «in riconciliazione» |
| 8 | **abbinata a prezzo MIGLIORE** | `avg_price_matched` ≠ prezzo chiesto | registra il prezzo **abbinato** | entrambi |
| 9 | **chiusa dall'utente fuori app** | posizione di conto | non gestisce ciò che non esiste più (§12 Costituzione, 16/09) | «chiusa fuori dall'app» |
| 10 | mercato **annullato** | `void` | P&L 0 | «annullato» |

### 6.2 Il reperto che va chiuso prima di scrivere v4

**R-C1** — Omega scrive la consapevolezza **in un punto solo**: `_confirm_open_trade`
(`omega_service.py:1490-1498`, `X.aggiorna_trade(..., consapevolezza=...)`). I rami flumine
(`_flumine_confirm:1982`, `_poll_one_flumine_live_trade:2177`) usano `db.update_trade` **diretto**.
È **esattamente** il difetto trovato su Safe il 17/09 (le cinque colonne NULL sulla prima
operazione live reale, `CRONOSTORIA.md` checkpoint 8), e con una quotazione viva — che passa
**necessariamente** dal percorso appoggiato — diventerebbe la regola invece che l'eccezione.
**Va chiuso in Fase 1**, con lo stesso rimedio di Safe: un solo scrittore, e il controllo che
pretende le **colonne** valorizzate, non solo `meta`.

**R-J3** (aperto dal 16/09) — il ref `omega-t1` del piazzamento non è riconducibile a nessuna riga
con `customer_ref_for`: la riconciliazione non ritroverebbe l'ordine. Con l'ordine FOK di oggi è
un rischio; con una quotazione viva per minuti è **il** rischio.
**R-J6** (aperto dal 16/09) — abbinato 0,0 su 7,01 chiesti senza attività `place_parziale`: il
trader non vede il residuo.

### 6.3 La famiglia K, e perché è l'unica che certifica

Il 16/09 sera si è misurato che **i controlli che guardano solo la DECISIONE non vedono i difetti
di consapevolezza**: i cinque difetti del 15/09 reintrodotti uno per uno lasciavano il replay
verde e il referto identico cifra per cifra (catalogo §7.36). La famiglia **K1-K6** confronta,
dopo **ogni giro**, ciò che il bot **crede** di ogni gamba con ciò che il **banco** dice degli
ordini (`certificazione.py`, `verifica_consapevolezza`): K1 abbinato e prezzo medio · K2 rifiuto →
riga mai viva · K3 ref piazzato = ref riletto · K4 `closes_trade_id` nella **colonna** · K5 riga
aperta senza ordine a mercato · K6 residuo dichiarato. Misurate: **1.466 sollecitazioni, 0
violazioni**.

**v4 aggiunge tre controlli K, perché la quotazione viva crea tre modi nuovi di mentire:**

- **K7 — «la quota che il bot crede di avere a mercato è quella che c'è»**: prezzo e size
  dell'ordine vivo, letti dal banco, uguali a quelli scritti sulla riga. Un `L*` che cambia senza
  che l'ordine cambi è una bugia al trader.
- **K8 — «mai due lay vive o in volo sulla stessa gamba»**, verificata **sullo stato del banco**,
  non sulla confessione del bot (modello J5 di Mike, `mike/certificazione.py:529-569`).
- **K9 — «dopo una sospensione con una quota viva, alla riapertura l'ordine è stato RILETTO prima
  di decidere»** (modello R1 di Mike, `mike/certificazione.py:691-711`, `quando=` sollecitato da
  `ctx.riapertura.refs`).

### 6.4 Le sicurezze già certificate che v4 non tocca

Restano come sono, e i loro controlli (O1, `CHECKPOINT_O1_2026-09-16.md`) devono restare verdi:
riconciliazione dei `pending` (`reconcile_pending`, `omega_service.py:2420`), settlement
(`settle_open:3036`), **cash-out globale dell'utente** (richieste UI, `process_manual:3482`),
**chiusura fuori app** (`sorveglia_posizione_di_conto:2757`, cadenza `conto_every_s` 120 s,
`omega_config.py:191`), guardia d'avvio (`_GUARDIA_AVVIO`, `omega_service.py:212`,
`ferma_al_nuovo_avvio:5567`), respiro del DB (§20 della Costituzione, parametri
`omega_config.py:133-204`), separazione paper/live e tetti per modalità.

⚠️ **Il respiro del DB è un vincolo di progetto, non un dettaglio**: una quotazione viva che si
sposta ha bisogno di un giro **più fitto** (2-5 s) di quello di oggi (20 s). Il 13/09 il DB è
andato giù per budget IO esaurito. **Regola**: il giro fitto vive in RAM e sul feed; sul DB si
scrive **solo** quando cambia qualcosa di money-critical (un ordine piazzato, annullato,
abbinato), mai lo stato «sto ancora aspettando». Questo è un **controllo di certificazione
nuovo, D1**: scritture al DB per minuto sotto una soglia dichiarata, misurata nel replay.

---

## 7. IL PIANO DI COSTRUZIONE, A FASI (mandato §7)

Metodo: **Opus 5 costruisce, Sonnet 5 rivede, il coordinatore certifica** sul banco, rileggendo
il diff, rilanciando replay e test di persona e provando la falsificazione. Nessuna fase è
chiusa senza il suo referto completo secondo `PROCESSO_STANDARD_BOT.md` §6.8.

| fase | che cosa | file da toccare | controlli nuovi | scenari di replay | falsificazioni obbligatorie | ore |
|---|---|---|---|---|---|---|
| **M1-bis** | **quotazione CONTINUA** invece di piazzamenti discreti: quota di fill `phi` per gamba, per fascia e per minuto; tempo di riassestamento del book dopo un gol (→ `quote_cooldown_riapertura_s`); selezione avversa su campione grande | `tools/misura_ingresso_passivo.py` (modo `--continuo`) | — (strumento) | — | ricalcolo con `simulation_available_prices=True`: il risultato **deve** peggiorare | 4-6 |
| **M6** | **`k` IN GIOCO per fascia**, su campione serio: tutte le registrazioni, tutte le celle candidate a ogni minuto, esito vero, bootstrap a grappolo. Oggi: 293 celle, 20 partite, 12 uscite (M1 §6.1) | `tools/superficie_liability.py` (aggiunta degli esiti per fascia e minuto) | — | — | celle a caso: `k` deve tornare ~1 | 3-4 |
| **M4** | deriva **appaiata** del margine: modello + mercato sulla **stessa cella**, minuto per minuto, sulle registrazioni | `tools/superficie_liability.py` + `omega_v3` | — | — | celle a caso (placebo): la deriva **deve** sparire | 3-4 |
| **M5** | **Monte Carlo** di P&L e drawdown con correlazione fra gambe della stessa partita e gol che uccidono più quote insieme | strumento nuovo in `tools/` | — | — | seme diverso → stessi intervalli | 3 |
| **0** | **chiudere i reperti**: R-C1 (consapevolezza in un solo scrittore), R-J3 (ref riconciliabile), R-J6 (`place_parziale`), `CHECK` di `omega_trades.status` per gli stati nuovi | `omega_service.py`, migrazione | K1-K6 già esistenti + contratto sul `CHECK` | `rifiuti-betfair`, `chiuso-fuori-app`, `_synth_omega_prezzo_migliore` | i 5 difetti del 15/09 col metodo dell'**md5** su `omega_service.py` (il 16/09 non si poteva: il file era di un altro delegato) | 6-8 |
| **1** | **modello**: hazard per lega (P1), effetto rosso (P2), `p_sup` (P3), calibrazione applicata (P5), fiducia della fonte λ (P6) | `omega_v3.py`, `tools/banco_modelli.py`, `data/` | — (funzioni pure: test falsificati) | — | `k_se = 0` → i numeri di A10 cambiano; rosso spento → log-loss OOS peggiora | 8-10 |
| **2** | **prezzo di riserva e quotazione viva**: `L*`, le due strade, isteresi, abbandono, macchina a stati della gamba quotata | `omega_v3.py` (puro), `omega_engine.py` (innesto), `omega_service.py` (giro), `omega_config.py` | **A13** (k_prezzo e k_modello scritti), **A14** (mai una quota oltre `L*`), **K7**, **K8**, **K9**, **D1** (scritture DB/minuto) | nuovo scenario **`quotazione`**; `esiti-ignoti`, `riavvio`, `feed-stantio`, `cap-stretto`, `bot-fermo` | quota che non si sposta quando `L*` cambia di 5 tick → A14 rosso; due lay vive → K8 rosso; rilettura saltata → K9 rosso | 12-16 |
| **3** | **proposte di uscita**: produttore Python su `omega_requests`, gate G1, raccordo con `_greenup_candidates` | `omega_service.py`, `omega_db.py` | **G2** finalmente sollecitato | `manuale-e-bot`, `cashout-globale`, `chiuso-fuori-app` | servizio che drena una riga `proposed` → G1 rosso | 5-6 |
| **4** | **finestre, fasce, cap, dimensionamento a liability fissa**, paniere se l'utente lo approva | `omega_config.py`, `omega_engine.py` | **C5** cap di gamba, **C6** cap di paniere a caso peggiore, **A15** fascia di probabilità | `cap-stretto` esteso | stake fisso al posto di liability fissa → A15 rosso | 4-6 |
| **5** | **UI**: parametri v4 nel pannello, pagina delle proposte, la quota viva visibile con chiesto/abbinato/residuo | `frontend/src/lib/omega.ts`, Control Room | contratto UI (`test_omega_ui_contratto_2026_09_11.py`) | — | — | 4-6 |
| **C-replay** | **replay massivo su TUTTE le registrazioni Omega** (39 con raw + le sintetiche dichiarate), `--scenari tutti`, referto `PROCESSO_STANDARD_BOT.md` §6.8 completo: fill rate, `k` realizzato per fascia con IC, selezione avversa, P&L, drawdown, celle della matrice ordini provocate | — | — | tutti | i punti 1-17 del catalogo, **a livello di replay** | 6-8 |
| **C-paper** | **paper via flumine (F1 di `PROGETTO_PAPER_VIA_FLUMINE_2026-09-16.md` §C3)**: stesso motore di matching del replay, parità **campo per campo** fra la riga paper e quella live | dipende da F0/F1 | parità paper/live | tutti | un campo diverso fra paper e live → rosso | dipende da F1 |
| **C-live** | **live piccolo**: una partita, una gamba, liability minima, referto forense ordine per ordine, cinque operazioni prima di dichiarare validato | — | — | — | — | — |

**Totale del lavoro di Omega: 58-74 ore**, più le fasi di paper che dipendono da F1. Le quattro
misure (**M1-bis, M4, M5, M6**) vengono **prima** di tutto, e M1-bis e M6 sono **bloccanti**:
senza la selezione avversa e il `k` in gioco su campione serio, la Fase 2 costruirebbe una
macchina di cui non si conosce il rendimento — e §D.4 dice che potrebbe essere negativo.

**Registrazioni da usare.** 39 eventi con `<id>.raw.jsonl` **e** `<id>.scores.jsonl` in
`_live_raw/` (elenco nel referto; `35823616` ha il raw ma **nessun sidecar**: minuto e gol non
arrivano mai, va dichiarata ⊘). Qualità **COMPLETE/PARTIAL** dichiarata da
`Betfair/stream/tools/validate_recordings.py` (verdetto `COMPLETE` solo con copertura ≥ 90 % **e**
un `CLOSED` su un mercato principale). Sintetiche **dichiarate** e mai contate come reali:
`_synth_omega_prezzo_migliore` (esiste già, il «3 - 3» cala di un tick vero ogni 4 s dal 50':
serve a provare l'abbinamento a prezzo **migliore** del chiesto) più **due nuove da costruire**:
(a) una cella che diventa **impossibile** mentre la nostra quota è viva; (b) un libro in cui la
coda davanti a noi si consuma lentamente, per esercitare il fill **parziale** di una quotazione.

**Registro del banco.** Omega è già registrato e certificabile
(`Betfair/stream/backtest/registro_bot.py:125-135`, moduli di produzione
`("Betfair.omega.omega_service",)`, scenari `SCENARI_DESCRITTI`, controlli
`Betfair.omega.certificazione`). Lo scenario `quotazione` va aggiunto lì, non «a parte».

---

## 8. RISCHI, COSA QUESTO PROGETTO NON PROMETTE, E LE DECISIONI DELL'UTENTE (mandato §8)

### 8.1 I rischi, in ordine di gravità

1. **Il `k` grande è PRE-MATCH; quello in gioco è piccolo e peggiore.** M1 §6.1 misura, sulle
   celle in cui Omega opererebbe davvero, `k` al tocco **0,49** (IC 95 % 0,25-1,62) contro
   0,74-0,98 pre-match. Se il rapporto (~0,6) si trasferisse al miglior back, **nessuna fascia
   resterebbe sopra 2**. Rimedi: la **Fase M6** (misura di `k` in gioco su campione serio), il
   monitoraggio online (P7, CUSUM) e un live piccolo che misuri.
2. **La selezione avversa può mangiarsi tutto — è il rischio numero uno.** M1 misura che le
   celle **abbinate** sono poi uscite il **10,3 %** delle volte contro il **4,1 %** di tutte le
   candidate: un fattore **2,5x**, che moltiplicato al denominatore di `k` cancella qualunque
   leva di prezzo. E che **un fill su tre** (livello a) è seguito entro 60 s da un book sceso
   sotto il nostro prezzo. Campione: 78 abbinati, 8 uscite — un **allarme**, non una misura.
   **Se la Fase M1-bis lo conferma su campione grande, il progetto non ha edge e va detto**,
   esattamente come il 16/09 è stato detto per il tocco (§D.4, criterio di arresto).
3. **`phi` (la quota di fill di una quotazione continua) non è misurata.** Tutta la colonna
   «quante gambe al giorno» dipende da un numero che oggi non esiste.
4. **La maledizione dell'ottimizzatore ha già vinto quattro volte in questo repo**
   (−5,3 % / −8,0 % / −3,5 % / −6,1 %). Gli antidoti sono strutturali e vanno tutti tenuti:
   limite superiore, due stime indipendenti, `n_min` per cella, `k` misurato, split temporale,
   bootstrap **a grappolo**, monitoraggio online.
5. **Fonti ferme**: `omega_minute_transitions` e `omega_ht_ft_transitions` all'11/09,
   `betfair_market_odds` all'11/09. Il veto empirico gira su dati vecchi. Vanno ricostruiti
   (migrazione) prima della Fase 1, o dichiarati.
6. **Il giro più fitto e il DB.** Una quotazione viva chiede 2-5 s di cadenza; il 13/09 il DB è
   caduto per IO. Il controllo D1 esiste per questo.
7. **Il minimo di piazza e il trim non sono certificabili sul banco** (⊘ dichiarato).
8. **Il paper via flumine (F1) non c'è ancora**: senza, «paper = specchio della realtà» non è
   verificabile per la quotazione viva, perché il fill passivo **è** il punto.

### 8.2 Cosa questo progetto NON promette

- Non promette un edge: promette **misure**, e se la Fase M1-bis dice che la selezione avversa
  cancella il margine, **non fa aprire niente**.
- Non altera la strategia di propria iniziativa: ciò che è «proposto» resta proposto, e le
  finestre, i cap e il paniere **non si toccano** senza ordine (§8.3).
- Non usa ML / Direzione / Frequenze-di-mercato come generatori di segnale: quattro misure
  indipendenti dicono che come scommessa perdono.
- Non parla di live: prima replay massivo, poi paper via flumine, poi — con i reperti chiusi —
  decide l'utente.
- Non introduce processi, registratori o runner nuovi.

### 8.3 Le decisioni che restano all'utente (poche, precise)

Le **prime quattro** sono, una per una, le decisioni gia' elencate dal coordinatore
(`VISIONE_OMEGA_V4_COORDINATORE_2026-09-17.md` §8.1-§8.4), qui riportate **con i numeri
che servono per deciderle**. La quinta e la sesta sono emerse dalle misure di oggi.

| # | decisione | i numeri per deciderla | raccomandazione del progetto |
|---|---|---|---|
| **1** | **Obiettivo giornaliero: da motore a metrica?** (oggi `daily_goal` 250 € **decide la size**, `omega_config.py:13` + `omega_engine.py:218-225`) | con una partita in programma il target di gamba vale 125 € → ordine da **131,58 €** che nessun book riempie (`PROGETTO_OMEGA_V3` §1.2). Dividere un obiettivo per le partite **obbliga a operare dove non c'è margine** | **sì**: barra di progresso, non motore |
| **2** | **Paniere di celle per gamba?** (e se sì, quante) | `n = 5` a liability 30 € l'una, quota ~44: caso peggiore **27,35 €** contro 30 € di una cella sola; EV **+2,00 €** contro +0,40 €; **cinque occasioni di fill invece di una**. Rispetta «due ingressi per partita» se “ingresso” = gamba | **sì, n = 3-5**, dentro un cap di **caso peggiore** |
| **3** | **Cassa di riferimento per Kelly, liability per gamba, cap giornaliero** | Kelly/4 in fascia 1-2 % dà 0,2-0,3 % della cassa per gamba → **20-30 € su 10.000 €**. Con liability 30 € lo stake scende sotto il minimo .it (0,50 €) sopra quota 61: o liability più alta su quelle celle, o place-and-trim (⊘ non certificabile) | cassa e cap sono **suoi**; il progetto propone liability **30 €**/gamba, **60 €**/partita, stop a **10 perdite** (~300 €)/giorno |
| **4** | **Tetto di quota `[20, 120]` sostituito dal cap di liability + fascia di probabilità `0,3 %-5 %`?** | EV per euro di liability misurato: fascia 1-2 % **+0,90 %** (CS) e **+1,34 %** (HT); fascia 0-0,2 % **−0,17 %**; fascia >10 % **−0,26 %**. Il tetto di quota non separa queste tre cose | **sì** |
| **5** | **«Un ingresso nel 1T e uno nel 2T»: due MERCATI o due MOMENTI?** | il mercato `CORRECT_SCORE` è aperto e in gioco dal 1': 10,7 celle/partita contro 2,4 all'86', book più profondo, e per la stessa cella la quota (quindi la liability) **circa metà**. Quotare la gamba FT solo dal 46' butta via la parte migliore della superficie | **due mercati**: la gamba FT si può quotare dal 1'. Ma è un'interpretazione dell'ordine, e la **decide lei** |
| **6** | **Aggregati «Any Unquoted / Any Other»**: si bancano? | oggi esclusi (`include_aggregate=False`, `omega_config.py:32`); sono **la coda vera** e il modello sa già calcolarne la P come somma di celle (`omega_v3.probabilita_selezioni:433`). Nella misura di `k` sono già valutati, non saltati | **sì**, con la stessa fascia di probabilità delle scoreline |

---

## 9. IN UNA PAGINA, PER LA CONTROL ROOM

- Omega v4 **vende opzioni binarie fuori dal denaro** e guadagna da una sola cosa: il **prezzo**
  a cui entra.
- Al prezzo che prende oggi (taker sul best lay) il margine **non c'è in nessuna fascia**
  (`k` prudente <= 0,87 su 48.280 selezioni pre-match; **0,49** sulle celle in gioco misurate
  da M1). Al **miglior back**, sempre pre-match, `k` prudente sale a **1,1-3,5** secondo la
  fascia: è la condizione **necessaria**.
- Il prezzo non si prende: **si offre**. Omega v4 tiene una **quotazione viva** al proprio prezzo
  di riserva `L*`, ricalcolato a ogni tick, e la sposta con isteresi, mai due lay insieme, con
  rilettura obbligatoria dopo ogni sospensione.
- Il tempo lavora: sul **Correct Score** il margine migliora di ~**+14 % ogni 5 minuti** senza
  gol; sull'**Half Time Score** no.
- Si opera dove l'EV per euro di liability è massimo: **fascia 1-2 %**, +0,90 %/€ (CS) e
  +1,34 %/€ (HT).
- Si dimensiona a **liability fissa**, non a stake fisso, e si sostituisce il tetto di quota con
  un cap di liability più una fascia di probabilità.
- Le uscite sono **proposte**: firma l'utente.
- **Quello che ancora non si sa**: quanto spesso una quotazione continua viene abbinata (`phi`),
  e quanto la **selezione avversa** si mangia del margine dal vivo. Sono le prime due misure del
  piano, e se rispondono male il progetto si ferma lì — scritto, non nascosto.
