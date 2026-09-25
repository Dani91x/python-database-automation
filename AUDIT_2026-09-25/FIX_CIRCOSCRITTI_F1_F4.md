# FIX CIRCOSCRITTI F1-F4 (25/09/2026)

Worktree isolato su base `372158e`. Nessun commit, nessun `git add -A`, nessuna scrittura
sul DB vero. Sandbox: `SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x
SUPABASE_KEY=x`. Diff completo: `AUDIT_2026-09-25/fix_circoscritti.patch`.

File condivisi toccati (segnalati come da consegna): `frontend/src/lib/omega.ts` (2 righe
aggiunte, etichette italiane nuove, nessuna esistente toccata — vedi F3).

---

## F1 — Ref Safe tennis unificato

**Cosa faceva.** Safe tennis (attore `safe_tennis` sul canale di comando, porta 47332)
costruiva il `customer_order_ref` con la STESSA formula del calcio: `safe-t<id>`
(`bot_service.py`, `execution.py`, `porta_ordini.ref_ordine`). Il motore condiviso del
runner (`Betfair/stream/motore_ordini.py:82` `ATTORI_COMANDO`, righe 730-734 `_dispatch`)
impone pero' che il ref inizi con `f"{attore}-"`: per l'attore `safe_tennis` il prefisso
atteso e' `safe_tennis-`, mai scritto. Col canale spento (`SAFE_TENNIS_ORDINI_VIA_CANALE`,
condizione attuale) il difetto era invisibile; appena acceso, OGNI comando tennis sarebbe
stato rifiutato dal motore (`M_PARAM`, prefisso mancante) — il REPERTO aperto di
CRONOSTORIA 24/09 sera (`safe-t<id>` ≠ `safe_tennis-<id>` preteso dal motore).

**Decisione (motivata).** Unificato sul prefisso dell'ATTORE (`safe_tennis-t<id>` per il
tennis), NON sul vecchio `safe-t<id>`, perche' il motore (`motore_ordini.py`, "contratto
scritto dal coordinatore: non cambiarlo in silenzio") e' la porta money-critical condivisa
con Omega/Mike/i 4 bot tennis e la regola prefisso=attore vale gia' per TUTTI loro; e'
quindi il lato che NON si tocca. Il calcio (attore `safe`) resta `safe-t<id>`, invariato
(gia' conforme). I lettori (certificazione, replay, riconciliazione) sono Safe-specifici e
si sono aggiornati per riconoscere ANCHE la forma nuova, mantenendo il riconoscimento della
forma legacy per le registrazioni gia' fatte prima del fix (nessuna certificazione vecchia
si rompe).

**Cosa fa ora (file:riga).**
- `Betfair/safe_strategy/porta_ordini.py:178-201` — `ref_ordine(trade_id, sport="calcio")`:
  tennis -> `safe_tennis-t<id>`, calcio -> `safe-t<id>` (invariato).
- `Betfair/safe_strategy/bot_service.py:5313` (`_execute`, il piazzamento vero, unico punto
  per calcio e tennis) — `client_ref=_PO.ref_ordine(trade_id, sport=_sport_di(row))`.
- `Betfair/safe_strategy/bot_service.py:860` (`_risolvi_una_via_canale`, fallback ref) —
  sport-aware.
- `Betfair/safe_strategy/bot_service.py` — `_refs_di_safe` (conto reale/I3), 4 chiamate a
  `X.close_trade(..., table_prefix=...)` (manuale, chiusura solidale, uscita automatica,
  settle_position): tutte sport-aware, con l'aggiunta del prefisso LEGACY come candidato in
  piu' per il tennis (posizioni gia' aperte prima del fix restano riconoscibili sul conto).
- Lettori aggiornati per riconoscere ANCHE la forma nuova: `certificazione_k.py:106-131`
  (`ref_di_riga`), `certificazione_tennis.py` (J4/`_j2`), `tools/replay_tennis.py` (ruolo
  ordine, `_ordine_di`).

**Test aggiunti.**
- `Betfair/safe_strategy/tests/test_porta_ordini_f5_2026_09_24.py::test_ref_ordine_tennis_unificato_sul_prefisso_attore`
- `Betfair/safe_strategy/tests/test_porta_ordini_f5_2026_09_24.py::test_strategy_ref_segue_l_attore_calcio_e_tennis`
  (estesa: asserisce anche `cmd_t["ref"] == "safe_tennis-t<id>"`)
- `Betfair/stream/tests/test_motore_ordini_2026_09_24.py::test_safe_tennis_ref_unificato_emesso_e_riconosciuto`
  — usa il `MotoreOrdini` VERO (stessa fixture `amb` del banco), invia il comando reale con
  il ref costruito da `porta_ordini.ref_ordine`, verifica `ack["accettato"] is True`: emesso
  e riconosciuto con lo STESSO ref dai due lati.
- `Betfair/stream/tests/test_motore_ordini_2026_09_24.py::test_falsificazione_ref_tennis_vecchia_forma_rifiutato`
  — lo stesso comando con la vecchia forma calcio (`"safe-t1"`) viene rifiutato dal motore
  VERO (`M_PARAM`).

**Falsificazione.** Rimesso `ref_ordine` a restituire sempre il prefisso calcio
(`return (PREFISSO_REF_CALCIO + "%d" % int(trade_id))[:REF_MAX]`): 3 test rossi
(`test_ref_ordine_tennis_unificato_sul_prefisso_attore`,
`test_strategy_ref_segue_l_attore_calcio_e_tennis`,
`test_safe_tennis_ref_unificato_emesso_e_riconosciuto`). Ripristinato, tutti verdi.

**Numeri della suite (file toccati).**
`test_porta_ordini_f5_2026_09_24.py` + `test_motore_ordini_2026_09_24.py`: 121 verdi.
`test_bot_service.py`: 189 verdi. `test_replay_tennis_2026_09_16.py`: 61 verdi, 2 saltati.

**Non verificato.** Transizione: una posizione tennis GIA' aperta (ref legacy `safe-t<id>`)
al momento del deploy del fix, se il suo `bet_id` non fosse ancora noto, verrebbe cercata
dal fallback di `reconcile_pending`/`_risolvi_una_via_canale` col NUOVO ref (sport-aware) —
non trovandola per ref finche' non arriva un `bet_id`. Rischio basso (il `bet_id` si scrive
alla prima conferma, il fallback per ref e' un'eccezione rara), ma non l'ho falsificato con
un replay dedicato: da verificare se ci sono posizioni tennis aperte al momento
dell'attivazione del canale.

---

## F2 — Guardia stato mercato sulla chiusura solidale sorelle combo Safe

**Cosa faceva.** `bot_service._close_combo_siblings` (chiamata da `_send_exit` quando il
parent di una combo chiude e trascina le sorelle) piazzava le chiusure SENZA controllare lo
stato del mercato — l'UNICA strada rimasta scoperta dal D2 del 24/09 (commit `baf4286`,
dichiarato esplicitamente "Resta senza guardia la chiusura solidale delle sorelle nelle
combo Safe" nel commit e in CRONOSTORIA 24/09 sera). Tutte le ALTRE strade Safe (manuale,
combo all'apertura, svolgimento di una combo incompleta via `_unwind_combo`) erano gia'
guardate con `_mercato_non_operabile`.

**Cosa fa ora (file:riga).** `Betfair/safe_strategy/bot_service.py:3754-3802`
(`_close_combo_siblings`): nuovo parametro `row` (la riga di scan dell'evento, la STESSA
gia' usata da `_combo_leg_prices` per tutte le sorelle); per ogni gamba, PRIMA di
`X.close_trade`, chiama la STESSA funzione condivisa `_mercato_non_operabile` (righe
3792-3801) con la STESSA semantica delle altre strade: mercato sospeso/chiuso/senza prezzi
-> nessun ordine, log `exit_wait` (non critico: si riprova quando il parent tenta di nuovo
l'uscita), UNA riga `attesa_riapertura`. Aggiornati i due chiamanti (`bot_service.py:3733`
e `:3999`) per passare `row`.

**Test aggiunti** (`Betfair/safe_strategy/tests/test_safe_stato_mercato_2026_09_24.py`):
- `test_chiusura_solidale_sorella_mercato_sospeso_nessuna_gamba_parte` — mercato SUSPENDED
  -> nessuna `X.close_trade`, una riga `attesa_riapertura` col motivo `SUSPENDED`, la gamba
  resta `open`.
- `test_chiusura_solidale_sorella_mercato_aperto_piazza_come_prima` — mercato OPEN ->
  comportamento INVARIATO (una gamba, una `X.close_trade`).
- `test_chiusura_solidale_sorella_stato_ignoto_passa_come_oggi` — stato assente dalla riga:
  si passa, come le altre strade D2 (questo fix non irrigidisce l'ignoto).

**Falsificazione.** Rimossa la chiamata a `_mercato_non_operabile` dal loop: il test
`test_chiusura_solidale_sorella_mercato_sospeso_nessuna_gamba_parte` diventa rosso
(`assert n == 0 and chiamate == []` fallisce, `n == 1`: la gamba viene chiusa a mercato
sospeso). Ripristinato, verde.

**Numeri della suite.** `test_safe_stato_mercato_2026_09_24.py`: 11 verdi.
`test_bot_service.py`: 189 verdi (nessuna regressione sulla firma nuova di
`_close_combo_siblings`, `row` e' opzionale).

**Non verificato.** Non ho un replay reale con una combo le cui sorelle chiudono durante
una sospensione (i replay non sono stati rieseguiti per limite del brief — "niente replay
intere"): la copertura e' unit/integration sui finti, non su una registrazione vera.

---

## F3 — Consapevolezza dello stato del mercato su tutti i bot

### F3(a) — Omega: stato mancante non e' piu' OPEN

**Cosa faceva.** `omega_service._mercato_in_attesa` (D2, `baf4286`) trattava lo stato
mancante (`snapshot.status is None`, il caso tipico quando l'evento arriva dal FEED dello
scanner, che non porta sempre lo stato) come IGNOTO e IGNOTO passava — fail-open dichiarato
nel codice stesso: *"Stato mancante = IGNOTO = si passa, come oggi (fail-open storico di
Omega: irrigidirlo e' una decisione dell'utente)"*. Decisione presa oggi (25/09, (i)).

**Cosa fa ora (file:riga).** `Betfair/omega/omega_service.py:1623-1679`
(`_mercato_in_attesa`): nuovo parametro opzionale `rileggi` (un `Callable[[], Any]` a zero
argomenti). Se lo stato e' IGNOTO e `rileggi` e' fornito: UNA chiamata (righe 1655-1671),
poi si rivaluta sullo stato fresco; se resta ignoto (rete giu', mercato senza book), si
RIFIUTA e si DICHIARA (`db.log("stato_mercato_ignoto", {...})`, righe 1667-1671) — mai piu'
un pass silenzioso. Un'eccezione nella rilettura e' gestita (non solleva mai) e loggata
(`"rilettura_stato_mercato_errore"`). Il chiamante vero (`scan_and_place`,
`omega_service.py:2249-2256`) passa `rileggi=lambda: market.read_market(cs)` — la STESSA
lettura REST che il ramo REST della stessa funzione gia' fa (nessun percorso nuovo). Senza
`rileggi` (retrocompatibilita' per chi non lo passa ancora) il comportamento resta quello di
prima — nessun regresso silenzioso su chiamanti non aggiornati.

Etichette italiane nuove aggiunte al contratto UI (richieste dal test
`test_omega_ui_contratto_2026_09_11.py::test_ogni_kind_loggato_e_mappato_in_italiano`, che
e' andato rosso alla prima stesura e mi ha corretto): `frontend/src/lib/omega.ts` righe
finali di `OMEGA_ACTIVITY_EXTRA` — `stato_mercato_ignoto` (`STATO MERCATO IGNOTO · nessun
ordine`, critical) e `rilettura_stato_mercato_errore` (`RILETTURA STATO MERCATO FALLITA`).

**Test aggiunti** (`Betfair/omega/tests/test_omega_stato_mercato_2026_09_24.py`):
- `test_v1_stato_mancante_senza_rilettura_passa_come_prima_del_25_09` (rinominata dal test
  esistente, comportamento invariato per chi non passa `rileggi`)
- `test_v1_stato_mancante_rilettura_trova_lo_stato_vero` — la rilettura trova SUSPENDED:
  si comporta come se lo stato fosse arrivato sospeso, UNA sola chiamata alla rilettura.
- `test_v1_stato_mancante_rilettura_apre_come_sempre` — la rilettura trova OPEN: si piazza.
- `test_v1_stato_ancora_ignoto_dopo_la_rilettura_non_piazza_e_lo_dichiara` — la rilettura
  torna `None`: NON piazza, dichiara `stato_mercato_ignoto` con motivo `"IGNOTO"`.
- `test_v1_rilettura_che_solleva_e_gestita_come_ignoto` — la rilettura solleva
  (`RuntimeError`): gestita come ignoto, mai un'eccezione che rompe il giro.

**Falsificazione.** Disattivata la condizione della rilettura (`if False and not
stato.noto...`): 3 test rossi (rilettura mai chiamata, stato mancante torna a passare).
Ripristinato, verde. Suite UI contratto (`test_omega_ui_contratto_2026_09_11.py`) rilanciata
dopo l'aggiunta delle etichette: verde.

**Numeri della suite.** `test_omega_stato_mercato_2026_09_24.py`: 9 verdi.
`Betfair/omega/` (l'intera cartella, dato che ho toccato una funzione condivisa e le
etichette UI): **1290 verdi, 3 saltati**.

**Non verificato.** `npx tsc -p tsconfig.app.json --noEmit` su `frontend/` NON eseguito in
questo worktree: `node_modules` non presente (nessuna junction, mai fatto `npm install` per
non violare la regola "mai npm install nel checkout mentre l'app e' viva" ne' toccare il
principale). La modifica a `omega.ts` e' additiva (2 righe in un `Record<string,
ActivityMeta>` con la stessa forma delle altre 60+ voci): rischio tipizzazione basso, ma
il coordinatore deve rilanciare `tsc` nel checkout principale prima di considerarla chiusa.
Non ho verificato la cadenza REST della rilettura sotto carico reale (quante volte al minuto
Omega la farebbe con molti eventi in feed senza stato): e' UNA lettura per candidato PRIMA
dell'ordine (evento raro, non per ogni tick di scan), ma non l'ho misurato a mercato vero.

### F3(b) — Mike, Safe, scalper, 4 bot tennis: distinzione dei 4 stati

**Verificato per ispezione (nessun difetto trovato).** Tutti i bot in-flumine (scalper,
i 4 bot tennis, il worker tennis, submin) gia' condividono `stato_mercato.mercato_operabile`
/`guardia_flumine` (D2, `baf4286`): OPEN/SUSPENDED/CLOSED/INACTIVE sono 4 motivi DISTINTI
gia' provati esaustivamente e parametricamente in
`Betfair/stream/tests/test_stato_mercato_freno_2026_09_24.py::test_guardia_sugli_stati_di_betfair`
(pura, su `mercato_operabile`, la stessa funzione per TUTTI i bot) e replicati per i 4 bot
tennis in `test_tennis_sospeso_nessun_ordine_una_riga_e_riapertura(nome)`. Safe ha inoltre
`_mercato_non_operabile` (F2 sopra) con lo stesso schema.

Il 4° stato del brief, "senza prezzi" (book vuoto/quote assenti anche a mercato OPEN), NON
e' una chiave di `mercato_operabile` (che legge solo `status`/`complete` di Betfair, mai i
prezzi del book): e' un controllo SEPARATO, PRIMA di ogni tentativo di piazzamento, in
TUTTI i bot ispezionati — `scalper_bot.py:965` (`_try_enter`: `if best_back is None or
best_lay is None or mp is None: return`), lo stesso schema in `tennis_swing_bot.py:187`,
`mike/engine.py:2262` (`not price_ok(bk.best_back)`). E' un gate SILENZIOSO per disegno
(valutato a ogni tick del book, troppo frequente per un log dedicato — la stessa categoria
di `price_min`/`price_max`/`min_size`, nessuno dei quali e' loggato singolarmente), MA
strutturalmente non puo' mai essere confuso con "aperto": senza un prezzo valido il codice
non arriva MAI a costruire un ordine (`_place(price: float, ...)` fa `float(price)`, che
solleverebbe su `None`) ne' a `guardia_flumine`. Non ho trovato un punto in cui "senza
prezzi" venga dichiarato o loggato come se il mercato fosse aperto e operabile.

**Test aggiunto** (uno, rappresentativo per lo schema comune —
`Betfair/stream/tests/test_stato_mercato_freno_2026_09_24.py::test_scalper_senza_prezzi_nessun_ordine_distinto_da_sospeso`):
book OPEN ma senza prezzi (`best_back=None, best_lay=None`) su `_try_enter` -> nessun
ordine costruito, nessuna riga `attesa_riapertura` (il mercato NON e' sospeso: e' un caso
diverso), nessun `place_rifiutato` (nessun tentativo). Falsificato disattivando il gate
(`if False: return`): il test diventa rosso con un `TypeError` reale (`'<=' not supported
between float e NoneType`), la prova diretta che senza quel controllo il codice andrebbe
oltre verso un ordine con prezzo inesistente. Ripristinato, verde.

**Non verificato — dichiarato esplicitamente.** NON ho scritto un test dedicato analogo per
Mike e per i 4 bot tennis (`tennis_scalper_bot.py`, `tennis_pro_bot.py`,
`tennis_flb_bot.py`, `tennis_swing_bot.py`): ho verificato per ISPEZIONE del codice
(righe citate sopra) che seguono lo STESSO schema (gate silenzioso pre-`_place`, mai
un ordine costruito senza prezzo), ma non ho costruito un test eseguibile per ciascuno per
il tempo del brief. Se il coordinatore vuole la copertura completa (un test per bot, come
chiesto), e' il residuo aperto di questa consegna: lo schema e' identico a quello gia'
scritto per lo scalper, quindi riproducibile rapidamente da un delegato con lo stesso
pattern (`_Slot`/`_try_enter` per i bot con la struttura scalper-like; per Mike serve un
fixture diverso, `engine.py:2262`).

**Numeri della suite.** `test_stato_mercato_freno_2026_09_24.py`: 36 verdi.

---

## F4 — Test dedicato per la guardia del worker tennis

**Cosa faceva.** Il 24/09 (`baf4286`) la guardia dello stato del mercato in
`Betfair/stream/tennis_live/tennis_live_order_worker.py::_do_place` (righe 523-531 di
allora) era stata scritta ma dichiarata SENZA test dedicato ("resta il rifiuto di flumine
[come rete di sicurezza]", nota nel commit e in CRONOSTORIA). La guardia ESISTE davvero
(verificato leggendo il codice: `mercato_operabile(stato_da_mercato_flumine(market))`
subito prima di costruire il `Trade`/`LimitOrder`, righe 528-531 attuali) — non era da
implementare, solo da testare.

**Test aggiunti** (`Betfair/stream/tennis_live/tests/test_tennis_order_payload.py`, che gia'
testava `_do_place` per le altre validazioni money-critical — stesso file, stesso schema
`_fake_env`/`_place_cmd`):
- `test_place_rejects_mercato_sospeso_prima_di_flumine` — `market_book.status="SUSPENDED"`
  -> `ValueError` con "SUSPENDED" nel messaggio, PRIMA di costruire `Trade`/`Order`
  (`session.tracked_orders` resta vuoto: nessun ordine tracciato).
- `test_place_rejects_mercato_chiuso_prima_di_flumine` — idem con `CLOSED`.
- `test_place_rejects_mercato_senza_prezzi_prima_di_flumine` — `status="OPEN",
  complete=False` (lo stesso caso INCOMPLETO di `mercato_operabile`, usato dagli altri bot
  per "book non completo"/senza tutti i prezzi) -> `ValueError` con "INCOMPLETO".
- `test_place_mercato_aperto_passa_la_guardia_come_prima` — `status="OPEN", complete=True`:
  la guardia dello stato NON blocca, il codice arriva al controllo successivo (minimo
  stake) — prova che il comportamento a mercato aperto e' invariato.

**Falsificazione.** Rimossa la guardia da `_do_place` (sostituita con `pass`): i 3 test di
rifiuto diventano rossi — non con l'errore atteso, ma con un `AttributeError` reale
(`'SimpleNamespace' object has no attribute 'place_order'`), la prova che SENZA la guardia
il codice prosegue fino a `market.place_order` (verso flumine/Betfair) invece di fermarsi
prima. Ripristinato, verde.

**Numeri della suite.** `test_tennis_order_payload.py`: 16 verdi (12 preesistenti + 4 nuovi).

**Non verificato.** Non un replay reale sul worker tennis con un comando a mercato sospeso
(stesso limite dichiarato nel commit `baf4286`: "resta il rifiuto di flumine" come ultima
rete — quello NON e' cambiato e resta la garanzia di fondo anche se questa guardia avesse un
buco).

---

## Riepilogo suite (solo file toccati, non l'intera Betfair/)

| Suite | Esito |
|---|---|
| `test_porta_ordini_f5_2026_09_24.py` + `test_motore_ordini_2026_09_24.py` | 121 verdi |
| `test_bot_service.py` | 189 verdi |
| `test_safe_stato_mercato_2026_09_24.py` | 11 verdi |
| `test_replay_tennis_2026_09_16.py` | 61 verdi, 2 saltati |
| `Betfair/omega/` (intera cartella) | 1290 verdi, 3 saltati |
| `test_stato_mercato_freno_2026_09_24.py` | 36 verdi |
| `test_tennis_order_payload.py` | 16 verdi |

Nessuna suite intera (`Betfair/` completa) rilanciata, nessun replay rieseguito — per
vincolo esplicito del brief ("Test SOLO sui file toccati... niente suite intere ne'
replay").

## Non verificato — riepilogo per il coordinatore

1. `npx tsc -p tsconfig.app.json --noEmit` su `frontend/` (nessun `node_modules` in questo
   worktree).
2. Transizione ref tennis F1 per posizioni gia' aperte senza `bet_id` al momento del deploy
   (rischio basso, non falsificato con un replay).
3. F2: nessun replay reale con una combo le cui sorelle chiudono durante una sospensione.
4. F3(b): test dedicato "senza prezzi" scritto SOLO per lo scalper; Mike e i 4 bot tennis
   verificati per ispezione del codice (stesso schema, righe citate), non con un test
   eseguibile per ciascuno.
5. F3(a): cadenza/costo REST della rilettura di Omega non misurati a mercato vero.
6. Nessun `git add -A`, nessun commit: il diff e' tutto in
   `AUDIT_2026-09-25/fix_circoscritti.patch` e nel working tree del worktree.
