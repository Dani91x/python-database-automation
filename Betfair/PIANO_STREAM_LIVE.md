# PIANO — Betfair Stream API Live + Storico Quote/Punteggio

> Versione: 1.1 · Data: 2026-06-26
> Obiettivo dichiarato dall'utente: **"una versione a cui non dovrò più mettere mano"**.
> Principio guida: progettazione difensiva, layer disaccoppiati, formati eterni, fallback ovunque.

> **DECISIONI CONFERMATE DALL'UTENTE (2026-06-26):**
> 1. **Hosting**: tutto **in locale** per ora. Test su **UNA singola partita in programma OGGI** (post-implementazione, per verificare end-to-end). L'automazione (worker always-on) si valuterà dopo.
> 2. **Mercati**: registrare **TUTTI i mercati** di ogni evento seguito (curazione solo allo step di upload).
> 3. **Archivio grezzo**: **solo locale** per ora (cloud R2/Backblaze predisposto ma non attivato).
> 4. **Punteggio**: primario = **in-play Betfair**, fallback = **API-Football** (confermato in sessione).

---

## 0. Obiettivo e principi

### Obiettivo
Quando una partita passa a **"giocate"** nel Report Personale, abbonarla allo **Stream API Betfair** per:
- **(a)** ricevere in tempo reale l'oscillazione quote di **tutti** i mercati;
- **(b)** ricevere punteggio/eventi (gol, cartellini, minuto) — **sorgente primaria = servizio in-play Betfair** (stessi `event_id`, nessun matching con la nostra API);
- **(c)** alimentare il **motore live** che ricalcola le probabilità in-match;
- **(d)** **immagazzinare** lo storico reale dell'oscillazione, ri-processabile e backtestabile.

### Principi di design (non negoziabili)
1. **Local-first**: lo stream grezzo non tocca MAI Supabase in tempo reale (vincolo da incidente I/O 2026-06-13).
2. **Formato eterno per il livello grezzo**: si registra nel **formato nativo dello stream Betfair** (= identico allo storico ufficiale Betfair) → ri-leggibile da qualsiasi parser e dal motore di replay di flumine.
3. **Tutto astratto dietro interfacce (`Protocol`)**: sorgente punteggio, storage, sink upload. Cambiare un fornitore = cambiare una classe, non il sistema.
4. **Fallback ovunque**: punteggio (Betfair → API-Football), connessione (riconnessione automatica), upload (idempotente e ritentabile).
5. **Idempotenza**: ogni step (registrazione, curazione, upload) è ri-eseguibile senza duplicare dati.
6. **Sicurezza**: repo PUBBLICA → zero segreti nel codice, solo `.env`; certificati fuori dal repo.

---

## 1. Gate preliminare (BLOCCANTE — da verificare PRIMA di scrivere codice)

| # | Verifica | Perché blocca | Come si verifica |
|---|----------|---------------|------------------|
| G1 | **Live App Key attiva + conto finanziato** | Con Delayed Key i dati arrivano con conflation fino a **180s** → motore live inutile. La Live Key ha un costo una-tantum di attivazione (£299–£499). | Smoke test: subscription su 1 mercato live e misurare il ritardo del primo `MarketBook` vs orario reale. Se `conflateMs`=180000 o ritardo ~3min → è Delayed. |
| G2 | **App Key abilitata allo Stream** | Alcune key sono solo Betting API. | Tentativo di connessione allo stream endpoint con la key attuale. |
| G3 | **In-play service raggiungibile dall'account .it** | È non ufficiale; va confermato che risponda su account italiano. | `get_scores([event_id])` su una partita live. |

> **Esito G1 = NO** → il progetto va ripensato (es. solo storico post-match, niente motore live real-time). Da decidere insieme.

---

## 2. Architettura

```
                          ┌─────────────────────────────────────────────┐
   Report Personale       │              WATCHLIST LIVE                   │
   (partita → "giocata") ─┼──► tabella `live_follow` (event_id, stato)   │
                          └───────────────────┬─────────────────────────┘
                                              │ legge gli event_id da seguire
                                              ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │                        PROCESSO LIVE (flumine, long-running)               │
   │                                                                            │
   │   Auth cert .it (riuso client esistente)                                   │
   │                                                                            │
   │   ┌────────────────────┐         ┌───────────────────────────────────┐    │
   │   │ MarketStream        │         │ ScoreProvider (Protocol)          │    │
   │   │ (flumine, push)     │         │  ├─ BetfairInPlay  (PRIMARIO)     │    │
   │   │ tutti i mercati     │         │  └─ ApiFootball    (FALLBACK)     │    │
   │   │ degli event seguiti │         │  poll ~10-15s, circuit breaker    │    │
   │   └─────────┬──────────┘         └──────────────────┬────────────────┘    │
   │             │ MarketBook (delta)                     │ ScoreSnapshot       │
   │             ▼                                         ▼                     │
   │   ┌─────────────────────┐              ┌──────────────────────────────┐    │
   │   │ RawRecorder          │              │ MOTORE LIVE                   │    │
   │   │ (file nativo + .meta)│              │ ricalcola prob. in-match      │    │
   │   │ source of truth      │              │ (Poisson/ML) → segnali        │    │
   │   └─────────┬───────────┘              └──────────────────────────────┘    │
   └─────────────┼──────────────────────────────────────────────────────────────┘
                 │ a partita CHIUSA (market CLOSED / fine eventi)
                 ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │  CURATOR + UPLOADER (batch post-match, idempotente)                        │
   │  legge file grezzo → estrae snapshot write-on-change (~10s) solo mercati   │
   │  tradati + timeline gol/stato → upload Supabase (tabelle strette)          │
   └──────────────────────────────────────────────────────────────────────────┘

   ARCHIVIO GREZZO: locale (+ opz. Cloudflare R2 / Backblaze via smart_open)
```

### Decisioni chiave e razionale

| Decisione | Scelta | Razionale |
|-----------|--------|-----------|
| Framework | **flumine** (sopra betfairlightweight) | Recorder nativo + replay/backtest + riconnessione gestita. Attivo (mag 2026), Py 3.13/3.14, stessa auth cert. |
| Punteggio primario | **Servizio in-play Betfair** (`get_scores`/`get_event_timeline`) | Stessi `event_id` dello stream → **zero matching** con la nostra API. (Scelta esplicita utente.) |
| Punteggio fallback | **API-Football** (già pagata) dietro `ScoreProvider` | In-play Betfair è non ufficiale e può rompersi. Il fallback garantisce continuità. |
| Mapping fallback | Riuso di `betfair_match.py` (fuzzy esistente) | Betfair event_id → API-Football fixture_id serve SOLO quando scatta il fallback; riusa codice money-critical già testato. |
| Formato grezzo | **Nativo stream Betfair** (file per evento, gzip) | Eterno, replayable, = storico ufficiale Betfair. |
| Storage real-time | **MAI Supabase** — solo locale (+R2 opz.) | Vincolo incidente I/O. |
| Storage curato | Supabase, tabelle **strette append-only**, JSONB | Solo mercati tradati, write-on-change ~10s. |
| Cadenza upload | **Post-match batch** | Niente carico continuo sul DB. |

---

## 3. Schema Supabase (tabelle nuove, strette, append-only)

> Prefisso `live_` per isolarle. Tutte con RLS coerente all'auth lockdown esistente (anon → 401).

### 3.1 `live_follow` — watchlist delle partite da seguire
```sql
create table if not exists live_follow (
  event_id        text primary key,          -- Betfair event_id (autoritativo)
  fixture_id      bigint,                     -- nostra fixture (se nota; null = solo Betfair)
  home_name       text not null,
  away_name       text not null,
  open_date       timestamptz not null,       -- kickoff (Betfair openDate)
  status          text not null default 'PENDING'  -- PENDING|STREAMING|CLOSED|UPLOADED|ERROR
                  check (status in ('PENDING','STREAMING','CLOSED','UPLOADED','ERROR')),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);
```

### 3.2 `live_market_snapshots` — quote curate (write-on-change)
```sql
create table if not exists live_market_snapshots (
  id            bigint generated always as identity primary key,
  event_id      text not null references live_follow(event_id),
  market_id     text not null,
  market_type   text not null,                -- MATCH_ODDS, OVER_UNDER_25, ...
  ts            timestamptz not null,         -- publish time del delta
  inplay        boolean not null,
  status        text not null,                -- OPEN|SUSPENDED|CLOSED
  ladder        jsonb not null,               -- {selection_id: {back:[[price,size]...], lay:[...], ltp, tv}}
  created_at    timestamptz not null default now()
);
create index on live_market_snapshots (event_id, market_id, ts);
```

### 3.3 `live_score_timeline` — punteggio/eventi nel tempo
```sql
create table if not exists live_score_timeline (
  id            bigint generated always as identity primary key,
  event_id      text not null references live_follow(event_id),
  ts            timestamptz not null,
  source        text not null,                -- 'betfair' | 'api_football'
  minute        int,
  score_home    int,
  score_away    int,
  event_type    text,                         -- GOAL|RED_CARD|... (se disponibile)
  payload       jsonb,                        -- raw del provider, per audit
  created_at    timestamptz not null default now()
);
create index on live_score_timeline (event_id, ts);
```

### 3.4 `live_run_log` — osservabilità per partita
```sql
create table if not exists live_run_log (
  event_id        text primary key references live_follow(event_id),
  started_at      timestamptz,
  ended_at        timestamptz,
  raw_file_path   text,
  raw_bytes       bigint,
  n_markets       int,
  n_snapshots     int,
  score_source    text,                       -- sorgente effettivamente usata
  fallback_count  int default 0,
  notes           text
);
```

---

## 4. Struttura moduli (codice)

Tutto sotto `Betfair/stream/` per isolamento.

```
Betfair/
  stream/
    __init__.py
    config_stream.py        # costanti: dir locale, cadenza poll, soglie circuit breaker, ecc.
    auth.py                 # costruisce APIClient betfairlightweight con cert (riusa config.py)
    watchlist.py            # CRUD live_follow; trigger da Report Personale ("giocata"→PENDING)
    recorder.py             # flumine: MarketSubscription per eventId + RawRecorder strategy
    scores/
      base.py               # ScoreProvider(Protocol) + ScoreSnapshot(dataclass frozen)
      betfair_inplay.py     # PRIMARIO: get_scores/get_event_timeline by event_id
      api_football.py       # FALLBACK: live endpoint; usa betfair_match per fixture_id
      poller.py             # loop ~10-15s, circuit breaker, scrive live_score_timeline
    engine/
      live_engine.py        # consuma prezzi+punteggio → ricalcolo prob in-match → segnali
    curator.py              # legge file grezzo → snapshot write-on-change (solo tradati)
    uploader.py             # upsert idempotente su Supabase (snapshots+timeline+run_log)
    runner.py               # entrypoint long-running: orcheststaria stream+poller+engine
    archive.py              # (opz.) push file grezzo su R2/Backblaze via smart_open
  tests/
    test_scores_base.py
    test_betfair_inplay.py
    test_api_football_fallback.py
    test_curator.py
    test_uploader_idempotent.py
    test_recorder_replay.py   # usa un file grezzo registrato come fixture
```

### Interfaccia punteggio (cuore del disaccoppiamento)
```python
# scores/base.py
from typing import Protocol
from dataclasses import dataclass

@dataclass(frozen=True)
class ScoreSnapshot:
    event_id: str
    ts: str                # ISO8601 UTC
    minute: int | None
    score_home: int | None
    score_away: int | None
    source: str            # 'betfair' | 'api_football'
    event_type: str | None # GOAL|RED_CARD|... se disponibile
    payload: dict          # raw provider per audit

class ScoreProvider(Protocol):
    name: str
    def get_score(self, event_id: str) -> ScoreSnapshot | None: ...
    def healthcheck(self) -> bool: ...
```

### Logica di fallback (circuit breaker)
- Il `poller` interroga **Betfair in-play** ogni ~10-15s.
- Conta i fallimenti consecutivi. Soglia (es. 3) → **apre il circuito** → passa ad **API-Football** e logga `fallback_count++`, `score_source='api_football'`.
- Ogni N minuti ritenta Betfair (half-open); se torna sano, richiude.
- Il fallback API-Football necessita `fixture_id`: risolto **una volta** all'inizio via `betfair_match.py` (cache su `live_follow.fixture_id`).

---

## 5. Fasi implementative (con gate e deliverable)

> Metodo TDD (test prima), un blocco alla volta, certificazione prima di procedere. Niente push finché un blocco non è verde.

### FASE 0 — Gate & setup (mezza giornata)
- [ ] G1/G2/G3 verificati (sezione 1). **Se G1 NO → STOP e ridecidere.**
- [ ] `pip install flumine` + aggiunta a `requirements.txt` (pin di versione).
- [ ] `auth.py`: APIClient betfairlightweight da `config.py` (cert .it). Smoke: login OK.
- **Deliverable**: report del gate (ritardo misurato, in-play risponde sì/no).

### FASE 1 — Persistenza event_id & watchlist (mezza giornata)
- [ ] Migrazione SQL `live_follow` (sezione 3.1).
- [ ] `watchlist.py`: quando una partita diventa "giocata" nel Report Personale → upsert `PENDING`. Salva `event_id` (oggi salviamo solo market_id; `betfair_match.py` ha già `event["id"]`).
- [ ] Test: trigger crea riga corretta; idempotente.
- **Deliverable**: una partita "giocata" compare in `live_follow`.

### FASE 2 — Registrazione grezza (1 giorno) ⭐ CUORE
- [ ] `recorder.py`: flumine `MarketSubscription` con `market_filter(event_ids=[...])`, `market_data_filter` (EX_ALL_OFFERS + EX_TRADED + EX_MARKET_DEF), `conflate_ms` ragionevole.
- [ ] `RawRecorder`: scrive stream grezzo nativo su file per evento (gzip) + `.meta` (manifest: event_id, market_ids, start/end, n_updates).
- [ ] Gestione limite **200 market data points/subscription**: se un evento supera, split in più subscription.
- [ ] Riconnessione/recovery verificata (staccare la rete → riprende).
- [ ] **Registrare UNA partita intera** → misurare mole reale (pre-match + in-play + sospensioni).
- **Deliverable**: file grezzo completo di 1 partita + dimensione reale misurata. **Gate per fissare lo schema curato.**

### FASE 3 — Punteggio con fallback (1 giorno)
- [ ] `scores/base.py` (Protocol + dataclass).
- [ ] `scores/betfair_inplay.py` (primario).
- [ ] `scores/api_football.py` (fallback, riusa `betfair_match.py` per fixture_id).
- [ ] `scores/poller.py` (loop + circuit breaker) → scrive `live_score_timeline`.
- [ ] Migrazione `live_score_timeline`.
- [ ] Test: simulare fallimento Betfair → switch ad API-Football, log corretto.
- **Deliverable**: timeline punteggio di 1 partita con prova di fallback funzionante.

### FASE 4 — Curazione & upload (1 giorno)
- [ ] Migrazioni `live_market_snapshots`, `live_run_log`.
- [ ] `curator.py`: file grezzo → snapshot write-on-change (~10s) solo mercati tradati.
- [ ] `uploader.py`: upsert idempotente (riesecuzione non duplica). Aggiorna `live_follow.status='UPLOADED'`.
- [ ] Test idempotenza: doppio upload = stesso stato.
- **Deliverable**: 1 partita completa curata su Supabase, verificata coerente col grezzo.

### FASE 5 — Motore live (1-2 giorni)
- [ ] `engine/live_engine.py`: consuma prezzi (da flumine) + punteggio (da poller) → ricalcola prob. in-match (Poisson/ML) → emette segnali "direzione".
- [ ] Riusa la logica del ventaglio/cruscotto direzione esistente, in versione in-play.
- [ ] Test su replay (file grezzo Fase 2 + timeline Fase 3).
- **Deliverable**: segnali live coerenti su una partita ri-giocata in replay.

### FASE 6 — Orchestrazione & resilienza (1 giorno)
- [ ] `runner.py`: entrypoint che legge `live_follow` (PENDING/oggi), avvia stream+poller+engine, gestisce fine partita → trigger curator+uploader.
- [ ] Recovery da crash: ripartendo, riprende dai file locali e ricurva solo il mancante.
- [ ] Decisione hosting (sezione 7).
- **Deliverable**: ciclo end-to-end automatico su una giornata reale.

### FASE 7 — Code review, hardening, docs
- [ ] `code-reviewer` + `security-reviewer` (segreti, repo pubblica).
- [ ] Doc operativa breve (come avviare, dove sono i file, come ri-curare).
- [ ] Certificazione finale + push.

---

## 6. Testing (TDD, ≥80% sui moduli core)

- **Unit**: `ScoreProvider` (entrambi), circuit breaker, curator (write-on-change), uploader (idempotenza).
- **Replay-based**: un file grezzo registrato in Fase 2 diventa **fixture di test permanente** → si testano curator + engine ri-giocando la partita (deterministico, offline, gratis). Questo è ciò che rende il sistema "non più da toccare": ogni futura modifica si valida sul replay.
- **Integration (smoke, manuale)**: gate G1/G2/G3 su partita live reale.
- **Idempotenza**: ogni step ri-eseguito non duplica.

---

## 7. Orchestrazione / hosting

Lo stream è una **connessione persistente** → non gira su cron GitHub Actions.

**DECISIONE CONFERMATA**: per ora **tutto in locale**. Si esegue `runner.py` sul PC durante la partita di test. L'automazione (worker always-on Render/Fly/VPS, ~€5-7/mese) si valuterà **dopo** aver verificato il funzionamento end-to-end su una partita reale. Il codice è identico nei due scenari: cambia solo *dove* gira `runner.py`, quindi questa scelta non comporta refactoring futuri.

| Opzione | Pro | Contro | Stato |
|---------|-----|--------|-------|
| **PC locale** (durante la partita) | Costo 0, semplice | Devi tenerlo acceso; no 24/7 | ✅ **scelto ora** |
| **Worker always-on** (Render/Fly/VPS) | 24/7, affidabile | ~€5-7/mese | ⏳ da valutare dopo il test |

---

## 8. Resilienza & edge case (checklist "non toccare più")

- [ ] **Riconnessione stream** (gestita da flumine; verificata staccando la rete).
- [ ] **Crash recovery**: file locale = source of truth; al riavvio si ricostruisce.
- [ ] **In-play Betfair rotto**: circuit breaker → API-Football, logga, ritenta.
- [ ] **Partita rinviata/annullata**: market CLOSED senza in-play → chiusura pulita, niente upload spazzatura.
- [ ] **Mercato SUSPENDED prolungato**: gestito (lo stream è "muto", il punteggio arriva dal poller).
- [ ] **Limite 200 points/subscription**: split automatico per eventi con molti mercati.
- [ ] **Upload fallito**: stato resta `CLOSED` → ri-tentabile; idempotente.
- [ ] **event_id senza fixture nostra**: funziona comunque (punteggio Betfair non richiede mapping); fallback disabilitato con warning.
- [ ] **Disco pieno**: rotazione/archivio R2 + alert.
- [ ] **Conflation/delay inatteso**: il runner logga `conflateMs` ad ogni avvio (sentinella per regressioni sulla key).

---

## 9. Sicurezza (repo PUBBLICA)

- Nessun segreto nel codice: solo `.env` (già il pattern del progetto).
- Certificati `.crt/.key` **fuori dal repo** (path in `.env`), mai committati. Verificare `.gitignore`.
- RLS sulle nuove tabelle coerente con auth lockdown (anon → 401).
- `security-reviewer` prima del push.

---

## 10. Config / env (aggiunte a `.env`)

```
# già presenti: BETFAIR_*, API_FOOTBALL_KEY, SUPABASE_*
LIVE_STREAM_DATA_DIR=./_live_raw         # dir file grezzi locali
LIVE_SCORE_POLL_SEC=12                    # cadenza poll punteggio
LIVE_FALLBACK_THRESHOLD=3                 # fallimenti consecutivi → fallback
LIVE_UPLOAD_CADENCE_SEC=10               # write-on-change min interval in curazione
# opzionale archivio:
LIVE_ARCHIVE_BUCKET=                      # VUOTO = solo locale (scelta confermata)
```

---

## 11. Decisioni: stato

| # | Punto | Stato |
|---|-------|-------|
| 1 | **Gate G1** — app key Live vs Delayed | ⏳ **da verificare allo smoke test (Fase 0)** sulla partita di oggi |
| 2 | **Mercati da registrare** | ✅ **TUTTI** (curazione al solo upload) |
| 3 | **Hosting** | ✅ **Locale** ora; worker always-on da valutare dopo il test |
| 4 | **Archivio grezzo** | ✅ **Solo locale** (cloud predisposto, non attivo) |
| 5 | **Punteggio** | ✅ **In-play Betfair** primario, **API-Football** fallback |

> Unico punto ancora aperto = **G1** (Live App Key): non si può sapere a priori, si misura allo smoke test della Fase 0 contro la partita reale di oggi. Se risultasse Delayed (conflation 180s) → il motore live va ripensato e ne riparliamo.

---

## Riferimenti
- flumine: betcode-org/flumine (MarketRecorder, simulation). Attivo mag 2026, Py 3.13/3.14.
- betfairlightweight: streaming + in_play_service (non ufficiale).
- Vincolo I/O Supabase: incidente 2026-06-13 (vedi memoria progetto).
- Direzione+timing+dinamica (non edge/CLV): feedback trader 2026-06-20.
- Matcher esistente riusato per fallback: `Betfair/betfair_match.py`.
