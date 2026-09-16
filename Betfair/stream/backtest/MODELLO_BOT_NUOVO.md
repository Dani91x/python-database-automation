# Un bot nuovo: come si aggancia al banco (e perché non se ne può fare a meno)

> Ordine dell'utente, 16/09/2026: *«ogni nuovo bot, o i precedenti, se voglio
> testarli devono passare da flumine ed essere certificati; l'intero comparto
> backtest deve essere assolutamente veritiero e applicare i codici di produzione
> dei bot a partite registrate, replicandone l'esatto funzionamento che avrebbe
> in live; da oggi standard e usato di default.»*

Il banco comune è `Betfair/stream/backtest/banco_comune.py`. Non si scrive un
secondo replay: si aggancia il proprio servizio a questo.

La catena che il banco garantisce, e che nessun passo può saltare:

```
raw registrato -> flumine -> SCANNER VERO (Scanner._apply_market_book)
  -> build_rows VERA -> riga safe_strategy_scan in memoria
  -> feed VERO del bot -> servizio VERO -> ordini VERI su flumine
     (matching con la coda, FILL_OR_KILL, bet delay)
```

## I cinque passi

### 1. La spec
Scrivi *come deve comportarsi*, prima di scrivere come si comporta: un documento
con le regole numerate (es. `Betfair/mike/COSTITUZIONE_MIKE.md`,
`SPEC_STRATEGIA_S.md`). Senza spec non esistono controlli, e senza controlli il
replay dice solo «non è esploso».

### 2. Il replay per un evento
Una funzione con questa firma esatta — è il contratto del banco:

```python
def certifica_scenario(event_id: str, *, data_dir: str, scenario: str = "base",
                       ogni_ms: int = 1000, campioni_diff: int = 0) -> Referto:
```

Dentro si usa il banco, non si reinventa:

* `banco_comune.ScannerReplay` — lo `Scanner` VERO di `safe_strategy/service.py`
  con client nullo e orologio agganciato al `publish_time` del tick;
* `banco_comune.DbMemoria` — le tabelle in RAM, con le firme e i tipi di ritorno
  del DB vero;
* `banco_comune.MercatoFlumine` — `place_order_live` servito dal matching di
  flumine, con il bet delay vero;
* `banco_comune.MotoreReplay` — il ciclo di flumine che sa ASPETTARE;
* `banco_comune.replay_evento(...)` — se il bot si accontenta del giro generico
  (`servizio(db, market, now, row, banco, strategia)`), è già tutto pronto.

Poi il servizio **di produzione** (`run_once` / `_run_event` del bot), mai una
copia di laboratorio.

### 3. I controlli di condotta
Un modulo con `elenco_controlli()`, `mai_sollecitati(sollecitati)` e la classe
`Referto` (modello: `Betfair/mike/certificazione.py`). Ogni controllo **cita la
regola della spec che difende** e dichiara *quando* ha davvero un caso: «zero
violazioni» su un controllo mai sollecitato non vuol dire «sano», vuol dire
«non lo so», e il referto lo deve stampare.

### 4. La registrazione
Una scheda in `Betfair/stream/backtest/registro_bot.py`:

```python
BotRegistrato(
    nome="pippo", sport="calcio",
    descrizione="che cosa fa, in una riga",
    moduli_produzione=("Betfair.pippo.service",),   # quelli che main.js lancia
    mercati=("MATCH_ODDS",),
    replay="Betfair.pippo.tools.replay:certifica_scenario",
    scenari="Betfair.pippo.tools.replay:SCENARI_DESCRITTI",
    controlli="Betfair.pippo.certificazione",
    spec="Betfair/pippo/SPEC.md",
)
```

Finché replay o controlli mancano, la scheda si scrive lo stesso con
`replay=None` / `controlli=None` **e il motivo**: il test di contratto
`Betfair/stream/tests/test_registro_bot_2026_09_16.py` elenca i registrati senza
certificazione e diventa rosso se l'elenco cambia senza che qualcuno lo
dichiari. Lo stesso test rifiuta un bot che gira in produzione (runner di
`desktop/main.js`, variante Safe, `_BOT_REGISTRY` tennis, servizio scalper) e
non compare qui.

### 5. Il comando e il referto
Uno solo, per tutti i bot:

```
python -m Betfair.stream.backtest.certifica --elenco
python -m Betfair.stream.backtest.certifica pippo
python -m Betfair.stream.backtest.certifica pippo --complete --scenari tutti --diario diario.txt
```

Il referto dice: partite, tick, decisioni, azioni, ordini, stati visti,
violazioni per codice, **copertura dei controlli** e l'elenco di quelli mai
sollecitati. Se una registrazione non è `COMPLETE` il verdetto compare accanto
alla partita: un replay su una registrazione monca mente.

## Gli otto errori già fatti — non rifarli

1. **Fill scritto a mano.** Il matching è di flumine (coda `_piq`, volume
   scambiato). Un fill artigianale dava 11 azioni dove flumine ne dà 2.432.
2. **Ladder letto con `getattr`.** In simulazione flumine i livelli sono `dict`:
   `levels[0].price` ritorna `None` in silenzio. Si usano
   `sim_strategy._offer_price/_offer_size`, e allo scanner si passa
   `banco_comune.libro_di_produzione(book)`.
3. **`order.status` è un Enum**: `str()` dà `"OrderStatus.EXECUTABLE"`. Si legge
   `.value`.
4. **I tetti di flumine vanno aperti** (`max_live_trade_count`,
   `max_order_exposure`, `max_selection_exposure` e il `min_bet_size` del client:
   `banco_comune.cliente_simulato()`), altrimenti si certificano i limiti di
   flumine invece di quelli del bot.
5. **Il falso positivo è del controllo** finché non si è escluso: prima di dire
   che il bot viola una regola, si verifica il controllo.
6. **Niente snapshot a mano.** La riga di scan la scrive `Scanner.build_rows`.
7. **I finti parlano come il vero**: identiche chiavi, identici tipi, identica
   grafia (`customer_order_ref`, non `customerOrderRef`).
8. **Il bet delay non si salta.** Un ordine piazzato a `t` si abbina sul book di
   `t + place_latency + betDelay`: lo fa `MotoreReplay.attendi_esecuzione`.

## E poi

Un referto pulito **non** autorizza il live: dopo il replay viene il paper come
specchio della realtà, e solo se il paper conferma si parla di soldi veri
(`PROCESSO_STANDARD_BOT.md`). Le strategie non si alterano mai di iniziativa:
una divergenza trovata si scrive e si porta all'utente.
