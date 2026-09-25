# Scalper calcio — sniper_mode ACCESO di default (25/09 sera)

**NON VERIFICATO SUL BANCO**: nessun replay `certifica` e' stato rieseguito con
`sniper_mode` acceso di default. Lo sniper (S16) era gia' in produzione da
prima (voce SC3 di `AIUTI_SPENTI_DI_DEFAULT_2026-09-25.md`: backtest +0,99 EUR
su 14 eventi, worst -0,49, **ma la voce chiedeva la validazione fuori
campione PRIMA di accenderlo di default**). Questo lavoro NON fa quella
validazione: applica solo la decisione dell'utente (25/09 sera, testuale:
**«scalper, modalita' sniper: Acceso»**, piu' la regola generale **«tutti i
bot devono avere gli aiuti e le migliorie accese di default»**), cambiando
DOVE nasce il default (chiave assente = ON) senza toccare la strategia
sniper stessa (soglie, stake-fallback, tetto profitto: bibbia §6, S16,
INVARIATI). Il fuori-campione resta un debito aperto, non azzerato da questo
diff.

## Cosa fa lo sniper in pratica (per il trader)

Strategia SEPARATA dal maker, accanto ad esso nella stessa sessione: quando
la sessione arma un evento, lo sniper osserva il book dell'Under (gol totali
+ 1).5 (la linea si sposta coi gol: per questo la sessione, con lo sniper
acceso, si iscrive a TUTTE le linee Over/Under 0.5..8.5 a catalogo/stream,
non solo a quelle del maker) e aspetta il momento giusto letto dal book
(cadenza + coda + spread): un solo tick, poi si ferma (S16 mono, certificata
10/07). E' ALTERNATIVO alla gamba HT (intervallo): i due non possono stare
insieme nella stessa sessione (bibbia §5, `RuntimeError` se entrambi True).
In DEMO (dry_run) piazza ordini SIMULATI a ciclo completo (regola specchio,
non uno snapshot). Lo stake sniper e' indipendente da quello del maker (vedi
sotto): un evento con lo sniper acceso ha DUE esposizioni distinte in
parallelo (maker + sniper), ciascuna col proprio tetto.

## Cosa faceva prima -> cosa fa ora

| Punto | Prima (25/09 pomeriggio) | Ora (25/09 sera) |
|---|---|---|
| Sessione per-evento (card manuale) | `sniper_mode` letto `bool(...get("sniper_mode"))`: chiave assente = **False** (spento) | Chiave assente = **True** (acceso); `sniper_mode=false` ESPLICITO resta l'unico modo di spegnerlo |
| Auto-mode (interruttore globale, feed) | La finestra di vita usata per scegliere le partite armabili (`vita_sessione_s`/`ha_ancora_vita`) assumeva sniper spento con params vuoti -> finestra corta (600s, solo maker) | Stessa finestra ora assume sniper acceso con params vuoti -> finestra lunga (7800s, sniper/theta): **coerente** con cio' che la sessione arma davvero (altrimenti l'auto-mode avrebbe escluso dal feed partite che la sessione avrebbe comunque armato con lo sniper attivo) |
| UI (card per evento, `ScalperPanel.tsx`) | Checkbox "SNIPER in-play" nasce SPUNTATA=false (`useState(false)`) | Checkbox nasce SPUNTATA=true (`useState(true)`); l'utente la spegne dalla card se non la vuole (invariata la mutua esclusione con HT/Theta gia' presente) |
| Stake sniper | Fallback backend `sniper_stake or 10.0`; UI `useState(10)` | **INVARIATO**: gia' un default non-inerte (10 EUR, non zero), coerente tra Python e UI. Nessuno stake nuovo inventato (come richiesto: non si tocca cio' che gia' funziona) |
| `sniper_profit_target` | `_sniper_profit_target`: assente=0.01, 0 esplicito preservato | **INVARIATO** (nessun cambio richiesto, la voce SC3 riguardava solo `sniper_mode`) |

## Dove nasce il default (file:riga)

- `Betfair/stream/scalper/auto_mode.py:154-170` — nuova funzione
  `sniper_mode_acceso(params)`: **UNICO punto di risoluzione** del default
  (chiave assente -> `True`; `sniper_mode=false` esplicito -> `False`;
  `sniper_mode=None` esplicito -> `True`, "non dichiarato" come per
  `_sniper_profit_target`). Usata sia da `vita_sessione_s` (righe 172-183,
  la finestra di vita per l'armamento auto-mode) sia dalla sessione.
- `Betfair/stream/scalper/scalper_session.py:611` — import
  `from .auto_mode import sniper_mode_acceso, vita_sessione_s`.
- `Betfair/stream/scalper/scalper_session.py:657-663` — `sniper_mode =
  sniper_mode_acceso(control.get("params") or {})` (prima:
  `bool((control.get("params") or {}).get("sniper_mode"))`).
- `frontend/src/components/live/ScalperPanel.tsx:78-86` —
  `useState(true)` (prima `useState(false)`), commento con la decisione
  dell'utente e il rimando allo stesso default Python.
- `frontend/src/components/live/ScalperPanel.tsx:355-360` — hint aggiornato
  ("ACCESO di default (decisione utente 25/09): si spegne qui, per questa
  sessione").
- **Whitelist/lista params INVARIATE**: `scalper_session.py:80`
  (`UI_PARAM_WHITELIST`) e `scalper_session.py:295-304`
  (`_sniper_profit_target`) — nessun cambio, il default nasceva e nasce
  ancora nella RISOLUZIONE del valore, non nella whitelist dei campi.

## Perche' anche `auto_mode.vita_sessione_s` (non solo la sessione)

L'auto-mode (interruttore globale, feed unico, ordine dell'utente 25/09
mattina) arma le partite del feed usando i params della riga
`scalper_service_control` (default `params='{}'` dalla migrazione
`scalper_auto_mode_2026-09-25.sql`) SENZA passare dal default della
sessione: `scalper_service.giro_auto` chiama
`AM.ha_ancora_vita(open_date, params_GREZZI, ora)` PRIMA di armare, per
decidere se una partita del feed ha ancora vita a sufficienza. Se questo
calcolo avesse continuato ad assumere "sniper spento" mentre la sessione
vera lo arma acceso di default, l'auto-mode avrebbe scartato dal feed
partite gia' avanzate (es. 11' dopo il KO) che la sessione, una volta armata,
avrebbe comunque tenuto viva fino a fine partita grazie allo sniper. Per
questo `sniper_mode_acceso` e' UNA funzione condivisa, non duplicata: i due
punti (sessione e finestra di armamento auto-mode) vedono sempre lo stesso
acceso/spento.

## Test

Falsificazione fatta (rimesso il default a `False`/`useState(false)`,
verificato il rosso, ripristinato — `git diff` pulito dopo, vedi comandi).

- `Betfair/stream/tests/test_scalper_auto_mode_2026_09_25.py`:
  - **nuovo** `test_sniper_mode_acceso_di_default`: chiave assente -> True,
    `None` esplicito -> True, `sniper_mode=False` esplicito -> False.
  - `test_vita_della_sessione_numeri_di_prima` **adeguato** (dichiarato):
    prima assumeva `vita_sessione_s({}) == 600` (sniper spento di default);
    ora `vita_sessione_s({}) == 7800` (acceso di default); il ramo "solo
    maker" (600s) resta raggiungibile SOLO con `sniper_mode: False`
    esplicito nei params, cosi' come `ht_mode` (4200s), che ora richiede
    ANCH'ESSO `sniper_mode: False` esplicito per non collidere col default
    (mutua esclusione gia' presente lato UI e lato sessione — invariata,
    solo resa esplicita nel test).
  - `test_partita_oltre_la_vita_non_si_arma` **adeguato** (dichiarato): la
    riga che prima provava "sniper esplicito acceso arma una partita 11' oltre
    il KO" ora prova lo stesso risultato con params VUOTI (default), e la
    riga che prova "il taglio corto esclude una partita 11' oltre il KO" ora
    dichiara `sniper_mode: False` esplicito (prima non serviva, il default
    la spegneva da solo).
  - **nuovo** `test_la_sessione_usa_lo_stesso_default_sniper`: verifica per
    sorgente che la sessione non abbia reintrodotto un `bool()` locale che
    riporterebbe il default a spento.
- `Betfair/stream/tests/test_scalper_session_gates_2026_07_16.py`: NESSUNA
  modifica necessaria (`_sniper_profit_target` invariato, gia' testato).
- `frontend/src/components/live/ScalperPanel.test.tsx`: **nuovo** describe
  "sniper ACCESO di default" — (1) il form nasce con la checkbox spuntata e
  manda `sniper_mode: true` esplicito all'attivazione; (2) spegnendo la
  checkbox manda `sniper_mode: false` esplicito (mai assente dal payload:
  gesto dell'utente sempre tracciabile).

## Comandi eseguiti ed esito

```
SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_KEY=x \
  python -m pytest Betfair/stream/tests/test_scalper_auto_mode_2026_09_25.py \
    Betfair/stream/tests/test_scalper_session_gates_2026_07_16.py \
    Betfair/stream/tests/test_sniper_bot_2026_07_10.py \
    Betfair/stream/tests/test_theta_bot_2026_07_15.py \
    Betfair/stream/tests/test_scalper_pnl_settled_2026_07_16.py \
    Betfair/stream/tests/test_contratto_strada_unica_2026_09_25.py \
    Betfair/stream/tests/test_risk_semaphore_2026_07_11.py \
    -q -p no:cacheprovider
=> 180 passed

cd frontend && npx vitest run src/components/live/ScalperPanel.test.tsx \
    src/lib/scalperControlRoom.test.ts \
    src/components/controlroom/PannelloBotScalper.test.tsx \
    src/lib/interruttoriScalper.test.ts src/lib/composizioneScalper.test.ts
=> 5 test file passed (45 test)

cd frontend && npx tsc -p tsconfig.app.json --noEmit
=> 0 errori

Falsificazione (Python): sniper_mode_acceso rimesso a "return False if sm is
None" -> 3 test rossi (test_sniper_mode_acceso_di_default,
test_vita_della_sessione_numeri_di_prima, test_partita_oltre_la_vita_non_si_arma);
ripristinato, di nuovo 84/84 verdi.

Falsificazione (UI): useState(true) rimesso a useState(false) -> 2 test
rossi nel nuovo describe; ripristinato, di nuovo 4/4 verdi.
```

Nessuna suite intera, nessun replay, nessun DB vero toccato (solo pytest
mirato sui file di dominio e vitest/tsc sui file toccati, per istruzione).

## File toccati

- `Betfair/stream/scalper/auto_mode.py` — nuova `sniper_mode_acceso`,
  `vita_sessione_s` la usa.
- `Betfair/stream/scalper/scalper_session.py` — import + risoluzione di
  `sniper_mode` via `sniper_mode_acceso` (era `bool(...)` locale).
- `Betfair/stream/tests/test_scalper_auto_mode_2026_09_25.py` — 1 test
  nuovo sulla risoluzione, 1 test nuovo sulla wiring per sorgente, 2 test
  esistenti adeguati e dichiarati (vita della sessione, armamento oltre la
  vita).
- `frontend/src/components/live/ScalperPanel.tsx` — default della checkbox
  sniper a `true`, hint aggiornato.
- `frontend/src/components/live/ScalperPanel.test.tsx` — nuovo describe con
  2 test (acceso di default, spento esplicito se l'utente lo spegne).
- `AUDIT_2026-09-25/SCALPER_SNIPER_ACCESO_2026-09-25.md` — questo referto.

## Cosa NON e' stato toccato (fuori perimetro, dichiarato)

- `ht_mode`, `theta_mode`, `sniper_hunt` (caccia multi-linea F4), stake
  sniper/maker, tetto profitto sniper: **INVARIATI**, nessuna decisione
  dell'utente li riguarda in questo giro.
- Nessun replay/certificazione rieseguito: la voce SC3 chiedeva il fuori
  campione PRIMA di accendere di default; questa task applica solo il
  gesto esplicito dell'utente («Acceso»), il debito di validazione resta
  scritto qui e in `AIUTI_SPENTI_DI_DEFAULT_2026-09-25.md` (SC3).
- `Betfair/stream/scalper/tools/replay_registrazioni.py:169-170` — resta
  con `sniper_mode: False` esplicito (tool di replay/laboratorio, non e'
  il banco comune di certificazione: fuori dal perimetro di questa task,
  non toccato).
