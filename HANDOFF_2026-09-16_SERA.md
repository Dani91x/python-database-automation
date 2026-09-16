# HANDOFF — 16 settembre 2026, sera — PUNTO DI RIPRESA ESATTO

> **Se riprendi da qui: leggi questo file, poi `PIANO_CERTIFICAZIONE_DEFINITIVA_2026-09-16.md`
> (gli «Esito …» sono la cronaca certificata della giornata) e `PROCESSO_STANDARD_BOT.md`.**
> Coordinatore della giornata: sessione Claude `admin-e2`. Metodo: Opus 5 costruisce, Sonnet 5
> rivede, il coordinatore rilegge il diff, rilancia test e replay e falsifica di persona.
> Commit locale di sicurezza fatto la sera del 16/09 (NON pushato): tutto il lavoro è nel repo.

## 1. Stato del repo alla ripresa

- Branch `master`. Commit non pushati: `dc0cc30` (mattina, altra sessione) + il commit di
  sicurezza della sera `wip: certificazione definitiva 16/09` (questo handoff compreso).
- **Nessuna migrazione applicata** oggi. Migrazioni scritte e DA APPLICARE (utente):
  `migrations/omega_activate_conserva_params_2026-09-16.sql` (**necessaria**: la RPC azzera i
  cap), `migrations/trades_consapevolezza_ordine_2026-09-16.sql` (colonne chiesto/abbinato/
  residuo/prezzo medio/aggiornato da Betfair sulle tre tabelle trade; senza, i numeri restano solo
  nelle attività), `migrations/safe_strategy_stake_per_strategia_2026-09-16.sql` (facoltativa).
- **App desktop: chiusa.** Al prossimo avvio la Fase A ferma da sola ogni bot (Mike era
  `running/live` con battito del 15/09). Frontend già ricostruito (`npm run build`).
- Suite alla sera: backend ≈ 3600 verdi (varia mentre i delegati scrivono), frontend 2503,
  `tsc` 13 errori preesistenti (non regredire). Comando: `python -m pytest Betfair/ -q -p no:cacheprovider`.

## 2. Task che erano ATTIVE al momento dell'handoff (da riprendere o verificare)

Per ciascuna: cosa era stato chiesto, cosa risulta già nel working tree, come verificare se è
finita, e il brief da ri-emettere a un delegato Opus 5 se non lo è.

### 2.1 Cache Poisson in `Betfair/omega/omega_model.py` (velocità del replay, 2,3×→5×)
- Chiesto: memoizzazione PURA (`lru_cache` su `_poisson_grid`, eventualmente `_full_match_1x2`/
  `residual_grid` se pure), chiave = argomenti già arrotondati (nessun arrotondamento nuovo),
  cache limitata, risultati immutabili (verificare i chiamanti), firma invariata; test «cache e
  non-cache identiche elemento per elemento su 200 argomenti reali»; referto `certifica mike
  35760084 --scenari base,taker` con **sha identica** prima/dopo; suite omega+mike verde;
  falsificazione (chiave che ignora un argomento → rosso). Più: latenza delle letture REST nel
  banco = 120 ms dichiarati «assunti» con riga nel referto.
- Verifica: `grep -n "lru_cache" Betfair/omega/omega_model.py`; test in `Betfair/omega/` con
  «poisson» nel nome; `scratchpad` della sessione non è più disponibile: rifare le misure.
- Se manca: ri-emettere il brief sopra (delegato «C.0-perf»).

### 2.2 Mike — regola «mai due lay a mercato» + cash-out globale (`Betfair/mike/engine.py`, `service.py`)
- Chiesto (ordine utente): in ogni ramo che sostituisce una lay (`engine.py` blocco
  `vivo`/`_annulla(vivo)` ~:2341, ko_green, under_green, reentry_green, `altre_lay`): in quel
  giro SOLO `cancel`; la nuova lay al giro dopo SOLO se `_mark_trade_cancelled` ha confermato da
  Betfair residuo 0, dimensionata sulla posizione reale; cancel ignoto/fallito → `pending_reconcile`,
  nessuna nuova lay; controllo severo J2/J5 «mai due lay vive o in volo». Poi cash-out globale:
  se l'utente chiude tutto (via bot: `_request_flatten`; o fuori dal bot: ordini spariti da
  Betfair) → stato evento terminale «chiuso dall'utente», nessuna riapertura/copertura/
  re-ingresso; controllo R2; scenario `cashout-globale` su 35760084; test + falsificazioni.
- Verifica: `grep -n "cashout-globale\|chiuso_dall_utente\|R2" Betfair/mike/tools/replay_registrazioni.py Betfair/mike/certificazione.py`; `python -m pytest Betfair/mike -q`; replay
  `python -m Betfair.mike.tools.replay_registrazioni 35777617 --scenari gol-precoce` deve dare J2 = 0.
- Già certificato prima di questa task: ko_green appoggiata (Esito C.1-bis nel piano).

### 2.3 Safe calcio — partita nelle bande, manuali ignorate, cash-out globale (`Betfair/safe_strategy/`)
- Chiesto: (a) scansione di `_live_raw/*` (escluse `_synth_*`) con le funzioni vere per trovare
  partite con favorita 1,40-1,80 e sfavorita 4-8 (BASE), sfavorita 4-8 con entrata 1,03-1,10
  (PUNTA), punteggi 3-1/3-0 (ESATTO); classifica e replay `base` sulla migliore → seconda
  partita di riferimento calcio per Safe; (b) T12 ristretto alle lay del BOT (`origin='auto'`),
  controllo T13 «le manuali non alterano le decisioni del bot e il bot non le tocca» + scenario
  `manuale-e-bot`; (c) controllo T14 + scenario `cashout-globale` (percorso manuale vero).
- Verifica: `grep -n "T13\|T14\|manuale-e-bot\|cashout-globale" Betfair/safe_strategy/certificazione.py Betfair/safe_strategy/tools/replay_registrazioni.py`; `python -m pytest Betfair/safe_strategy -q`.

## 3. Consegnato e CERTIFICATO oggi (dettagli negli «Esito» del piano)

Fase 0 · Fase A (avvio senza bot automatici, `Betfair/stream/avvio_app.py`) · Fase B-1
(6 interruttori + stake per strategia + pagine singole allineate, `frontend/src/lib/interruttori.ts`)
· F0 runner paper+live per riga · C.0 banco comune + C.0-bis (middleware unico, cancel simulato,
orologio monotono, LAPSE al fischio e alla sospensione, commissione, fill nel referto) · C.0-perf
(memo dei book, pool `--worker`, test di identità, fedeltà del tempo) · C.12a/b consapevolezza
ordini backend + UI · patch Safe (parziali, cancel prima del terminale, guardia combo L4 uniforme)
· C.1 taker Mike · C.1-bis ko_green appoggiata + riapertura · C.2 Omega sul banco (+ manuali/
cash-out) · C.3 Safe calcio sul banco · C.4 Safe tennis sul banco (+ terna di riferimento,
validatore per sport) · E.1 audit test · C.8 progetto paper-via-flumine (C3 scelta) · C.9 · C.10 ·
inventario flumine. Registro: **6 bot certificabili su 11** (`certifica --elenco`).

## 4. Partite di riferimento (ordine utente: niente massivi finché il setup non è finito)
Calcio `35760084` (COMPLETE; Mike opera; Omega/Safe non entrano per le bande) · gol precoce
`35777617` · Mike 535× `35674515` · Tennis: `35792939` ingresso (COMPLETE) · `35795560` uscite
in perdita/obbligatoria · `35790650` uscite in profitto. Comando unico:
`python -m Betfair.stream.backtest.certifica <bot> <event_id> --scenari tutti --worker 3`.

## 5. Decisioni dell'utente prese oggi (non riaprire)
1-8 nel piano §5 (boot azzera anche il live; taker Mike risolto; paper via flumine per tutti;
guardia combo uniforme; tutto dalla UI; stake per bot; migrazioni le dice il coordinatore;
perimetro = tutti i bot) · 9 ko_green appoggiata · 10 manuali ignorate, cash-out globale = non
fare altro · **mai due lay a mercato del bot** · Mike e Safe tennis saltano il paper: live dopo
certificazione replay, stake piccolo, referto forense · una partita di riferimento fino a setup
chiuso · velocità senza perdere dati.

## 6. Reperti aperti per l'utente / da correggere PRIMA di un live
- **Omega R9 (pericoloso)**: chiusura fatta sul sito Betfair mai riletta → il green-up coprirebbe
  una posizione inesistente (`settle_open:2580`). R6 aggregati con le manuali; R7 green-up sulle
  righe manuali (§12 vs ordine h18); R8 nessuno stato «chiuso dall'utente» (migrazione).
- Omega: cap tutti a zero nel DB; lay a 300 con 5,26 € = 1.572 € di liability; il banco mostra un
  giorno con una partita sola (serve multi-evento per certificare Omega).
- Safe calcio: E10 «selezione aggiuntiva» di ESATTO non implementata; ingressi non esercitabili
  sulla 35760084 (bande).
- Mike: re-ingresso mai esercitato dalle registrazioni (H1/H2 «non lo so»); ramo «scaduto alla
  sospensione» mai capitato sui dati reali (R1 «non lo so»).
- Banco ⊘ ancora aperti: `run_once` per Mike (stop giornaliero/tetto), parità paper/live nel
  replay, multi-evento, place-and-trim/minimo .it, rifiuti Betfair provocati, settlement da
  `process_closed_market` (Mike), `CHECK` in `DbMemoria`, void.
- C.7 falsificazione indipendente (5 difetti del 15/09 su ogni bot) non ancora fatta;
  UI: `placedOrderState` classifica un esito assente come `unmatched`; Mike non pubblica
  `size_remaining` nello stato.

## 7. Ordine dei prossimi passi
1. Chiudere/verificare le tre task del §2. 2. Scenari completi di Mike (A2, B2, F1, F2) con la
pool. 3. C.7 falsificazione indipendente. 4. Referti finali Mike e Safe tennis → **«pronti a
provarli in live»** (migrazioni applicate, push, riavvio app, Fase A dal vivo, Control Room
verificata, cancel reale mai provato contro Betfair: prima operazione con stake minimo e
referto forense). 5. Paper via flumine (relay F1 → driver → gate → parità) per Omega e Safe
calcio. 6. Scalper/sniper/tennis bot sul banco. 7. Fase D carico DB. 8. Massivi su tutti i bot.
