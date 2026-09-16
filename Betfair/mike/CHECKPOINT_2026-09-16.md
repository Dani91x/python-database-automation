# CHECKPOINT — Mike, 16/09/2026 (delegato Opus 5)

Stato alla consegna: **FATTO**. Suite `Betfair/` **3898 verdi, 0 rossi** (mike 665);
`frontend/`: `npx vitest run src/lib` 1426 verdi, `npm run build` OK.
Working tree coerente, **nessun commit**, nessuna migrazione.

Tre ordini dell'utente eseguiti, in quest'ordine:

1. **h13** — `ko_green` = lay **appoggiata** in ogni modalita';
2. **h16:15** — «non devono mai esserci 2 lay a mercato, se si abbinano siamo scoperti»;
3. **h18:20** — «se chiudo io TUTTE le operazioni, al controllo dopo il bot lo capisce e NON FA ALTRO».

---

## 1. ko_green appoggiata (ordine h13) — FATTO

| dove | cosa |
|---|---|
| `service.py:946` `_is_resting_leg` | `ko_green` -> sempre `True`; `pre_exit_mode` governa solo `under_green`/`reentry_green` |
| `service.py:862` `_live_exit_override` | la valvola `live_resting_enabled` non tocca piu' `ko_green` |
| `service.py:1118` | rifiuto pulito del resting -> `_rifiutata(ctx,...)`: e' il freno che sostituisce il ritmo tolto |
| `engine.py:2337-2381` | **tolta** la ri-presentazione ogni `ko_green_retry_s`; al suo posto `tentativo_gia_rifiutato` (`:2370`) |
| `engine.py:505` `appoggiabile_in_gioco` | `operabile(bk) and bk.inplay`; usata in `_decide_ko_green:2299` e `finestra_uscita_scaduta:2203` |
| `engine.py:2328-2340` | «in volo» include `pending_reconcile`: con una `ko_green` IGNOTA non si appoggia nulla (J2/J4) |
| `engine.py:284` `MatchCtx.riapertura` | persistito in `service._CTX_FIELDS:224` |
| `config.py:152`, `COSTITUZIONE §6/§15.8`, `frontend/src/lib/mike.ts:449` | `ko_green_retry_s` **dichiarato senza effetto** |

**Consapevolezza alla riapertura** — `service._sorveglia_sospensione:1662`, chiamata a
`service.py:2772` **prima** di `E.decide`; rilettura in `_rileggi_ordine_appoggiato:1522`
(`list_current_orders` per bet_id/`mike-t<id>`, poi `order_state_by_bet_id`), classifica in
`_classifica_ordine:1490`, applica in `_applica_esito_riapertura:1604`:
(a) vivo -> resta; (b) scaduto -> attivita' `ordine_scaduto_alla_sospensione` + `_chiudi_gamba_scaduta:1565`,
poi il motore ri-appoggia se la finestra e' aperta, altrimenti copertura; (c) abbinato -> posizione;
(d) parziale -> abbinato = posizione, residuo dichiarato scaduto; **ignoto/rete muta** -> `pending_reconcile`
oppure `letto=False` e si riprova. Controllo **R1** in `certificazione.py:526-546`.
`RITMI_DICHIARATI` svuotata (`certificazione.py:677`): una serie di `ko_green` identici torna a essere P1/P3.

Vincolo DB dichiarato: `mike_trades.status` non ammette `cancelled` (nessuna migrazione), quindi una
gamba scaduta senza abbinato resta `error` sulla riga; il motivo sta in
`meta.reason='lapsed_alla_sospensione'` / `meta.phase='lapsed'` e nell'attivita'.

---

## 2. «Mai due lay a mercato» (ordine h16:15) — FATTO

**Come**: una guardia SOLA, applicata da `decide()` come ultima parola —
`engine._una_sola_lay` (definita a `engine.py:1704`, applicata a `engine.py:1885`), piu'
`engine.lay_in_volo:1686` («in volo» = `is_live` **o** `needs_reconcile`).

Regola: finche' su quella selezione c'e' una lay VIVA o IN VOLO, **una lay nuova non si emette**.
L'annullamento si', e parte nel giro corrente; la lay nuova arriva al **giro dopo** e solo se la
vecchia non e' piu' viva (= annullamento CONFERMATO da Betfair), dimensionata sulla posizione
REALE (la parte gia' abbinata resta posizione: `exposure`/`under_liability` la contano). Se non
resta nessun ordine da piazzare **lo stato non avanza** (stessa regola di `_strip_openings`).

**Rami coperti** (tutti, per costruzione: la guardia e' a valle di `_dispatch`, quindi vale anche
per i rami futuri): `_decide_ko_green` (`engine.py:2341-2350`), riprezzo green taker
(`engine.py:2069`), ultimo ingresso (`engine.py:1995`), riprezzo re-ingresso (`engine.py:3014`),
chiusure `_close_actions` (`engine.py:1599-1604`), `altre_lay` del `ko_green`.

**Rami NON coperti, dichiarati**: `over_cover` (`_decide_cover_pending`, `engine.py:2704`) si
riprezza ancora con `cancel` + `place` nello stesso giro, ma sono due **BACK** sull'Over 4.5:
due back abbinati sono sovracopertura, non una posizione scoperta. Non toccato di iniziativa.

**Controllo J5** (`certificazione.py`, prima della sezione R): «mai due lay VIVE o IN VOLO sullo
stesso mercato/selezione», `quando=` a ogni decisione con una lay in volo. Guarda lo **stato**
(due lay insieme, anche per un solo giro) **e** la **decisione** (una lay nuova dove ce n'e' gia'
una, anche se lo stesso giro la annulla).

---

## 3. Cash-out globale dell'utente (ordine h18:20) — FATTO (con un limite dichiarato)

**Cosa ho trovato**
* Il cash-out dell'utente passa da `service.process_requests` -> `_request_flatten:1855`
  (kind `cashout` o `flatten`): annulla subito gli ordini vivi (`_mark_trade_cancelled`, che
  arriva davvero a Betfair) e ARMA `ctx.flatten_pending`; la chiusura la guida l'engine
  (`_decide_flatten:1774`).
* **Pre-KO** funzionava gia': `no_reentry=True` -> `decide():1875` spegne
  `pre_enabled`/`reentry_enabled`/`last_entry_persist`.
* **In gioco NO**: il divieto era solo implicito (`reentry_done=True`). Nessuno stato diceva
  «l'ha chiusa l'utente» e niente lo difendeva.

**Cosa ho cambiato** (consapevolezza, non strategia)
* `engine._decide_flatten`: al completamento della chiusura manuale `no_reentry=True` **anche in
  gioco**, insieme a `reentry_allowed=False`/`reentry_done=True`; idem sul ramo «resta una
  posizione gia' decisa». Telemetria **`chiuso_dall_utente`** (whitelist in `service.py` nel
  loop `d.telemetry`), etichetta italiana in `frontend/src/lib/mike.ts`
  (`MIKE_ACTIVITY_KINDS` + `MIKE_ACTIVITY_EXTRA` + `mikeActivityLine`), kind dichiarato in
  `tests/test_mike_audit_2026_09_11.py` (L5).
* Si riaccende SOLO con «Riprendi» (`service.process_requests` -> `resume_event`).
  Le **chiusure** restano sempre permesse. La partita **non** diventa terminale: resta FLAT
  (o WATCH pre-KO) e arriva a `SETTLED` col mercato chiuso, altrimenti il P&L non si
  contabilizzerebbe.
* **Controllo R2** (`certificazione.py`), `quando=` sui giri successivi
  (`no_reentry` + `close_reason='manual'` + non piu' `flatten_pending`): nessuna **apertura**.

**LIMITE DICHIARATO — cash-out fatto FUORI dal bot** (da portare all'utente):
se l'utente chiude la posizione direttamente su Betfair con una **sua** lay, Mike **non se ne
accorge**: `omega_market.list_current_orders` filtra per `customerStrategyRef` e quella lay non
e' sua, quindi continua a vedere il proprio back abbinato e a gestirlo. Se invece l'utente
**annulla ordini di Mike**, quello si' viene visto (l'ordine sparisce dai correnti ->
`pending_reconcile` -> riconciliazione). Accorgersi del primo caso richiede leggere la posizione
**di conto** sul mercato (chiamata Betfair nuova): **non fatto**, fuori mandato.

---

## 4. Test

Nuovo file: `Betfair/mike/tests/test_mike_ko_green_appoggiata_2026_09_16.py` — **41 test, verdi**.
Sezioni: appoggiata in ogni modalita' · `ko_green_retry_s` senza effetto · solo aperto+in gioco ·
finestra ferma · le 4 reazioni alla riapertura + ignoto + rete muta + paper · R1 ·
persistenza · **mai due lay** (annullamento confermato / ignoto / fallito, J5) · **cash-out
globale** (R2, chiusure permesse, `quando=`).

Aggiornati alla regola nuova (prima codificavano quella vecchia):
`test_mike_engine.py` (7 test + helper `conferma_annulli`), `test_mike_flusso_fischio_2026_09_13.py` (3),
`test_mike_paper_vs_live_2026_09_13.py` (1), `test_mike_mercato_sospeso_2026_09_15.py` (3 book `inplay=True`),
`test_mike_audit_2026_09_11.py` (4 kind nuovi).

**Falsificazioni eseguite (tutte rosse, poi ripristinate)**
| falsificazione | esito |
|---|---|
| tolta la rilettura alla riapertura | **6 rossi** |
| rimessa la ri-presentazione taker di `ko_green` | **6 rossi** |
| `decide()` senza `_una_sola_lay` (cancel+place nello stesso giro) | **9 rossi** |
| `_decide_flatten` che non accende `no_reentry`/`reentry_done` | **1 rosso** |
| `decide()` che ignora `ctx.no_reentry` (sul REPLAY) | **NON rosso** — vedi sotto |

**Buco chiuso dopo la falsificazione del coordinatore (16/09, sera)**
Il coordinatore ha mutato `engine.lay_in_volo` (`not (l.is_live or l.needs_reconcile)` ->
`not l.is_live`: una lay a esito IGNOTO non conta piu' come in volo) e i **97 test restavano
VERDI**. Causa: `_decide_ko_green` ha un freno suo sulle gambe ignote (`engine.py:2333`) che
scatta **prima**, quindi su quel ramo `_una_sola_lay` non veniva mai esercitata e nessun test
provava la guardia **da sola**.
Aggiunta la sezione 10 di `test_mike_ko_green_appoggiata_2026_09_16.py` (**7 test**, tutti
parametrizzati su `pending` **e** `pending_reconcile`): `lay_in_volo` vede entrambe le forme di
«in volo» (e non confonde altra selezione / gamba morta / `escludi`); `_una_sola_lay` toglie la
lay nuova e **non fa avanzare lo stato**; lascia passare **l'annullamento**; non tocca i BACK ne'
le altre selezioni; lascia passare la lay quando non c'e' nessuna in volo.
**Verifica**: con la mutazione del coordinatore -> **3 ROSSI**
(`test_lay_in_volo_vede_sia_la_VIVA_sia_la_IGNOTA[pending_reconcile]`,
`test_una_sola_lay_toglie_la_nuova_e_NON_fa_avanzare_lo_stato[pending_reconcile]`,
`test_una_sola_lay_lascia_passare_l_ANNULLAMENTO[pending_reconcile]`); col codice attuale
**tutti verdi**. File nuovo a **48 test**; `Betfair/` **3906 verdi**.

⚠️ L'ultima falsificazione della tabella e' inconcludente **per progetto**: `no_reentry` e' difeso in TRE punti
(`engine.py:1875` in `decide`, `:1950` in `_decide_prematch` — motivo «rientro disabilitato
(chiusura manuale): premi Riprendi» — e `:2967` in `_decide_flat`). Patchandone uno solo il
replay da' un referto IDENTICO. La falsificazione che conta e' quella alla sorgente
(`_decide_flatten`), ed e' rossa.

---

## 5. Replay eseguiti (banco comune, punto d'ingresso unico)

| registrazione / scenario | PRIMA | DOPO |
|---|---|---|
| **35760084 base** (ko_green appoggiata) | azioni 12 / ordini 10, 0 violazioni | **identico** |
| **35760084 taker** | **KO** — azioni 39 / ordini 7, `no_fill x32`, `P1-DICHIARATA: ko_green ripresentata 32 volte`, `P3 6x` | **OK** — azioni 10 / ordini 9, 0 violazioni, `place_resting x2`. **32 ri-presentazioni -> 1** |
| **35674515 base** (reperto del coordinatore) | **KO** — `J2` + `J4`: «nuova ko_green mentre ko_green-0-3 e' a esito IGNOTO (0.0/10.12)» | **OK** — 0 violazioni; J2 x4 e J4 x3 sollecitati e verdi |
| **35760084 base** (guardia due lay) | — | **OK**, `azioni 12 / ordini 10` identico; **J5 x901** verde, R1 x4764 |
| **35777617 gol-precoce** | **KO** — `J2 x1` + `J5 x1`: «nuova lay ko_green ... annullata nello STESSO giro: l'annullamento emesso non e' un annullamento confermato»; azioni 6 / ordini 4, stati fermi a `LIVE_KO_GREEN,FLAT` | **OK** — **0 violazioni**, azioni 9 / ordini 7, la partita arriva fino a `LIVE_CLOSING,FLAT`; J5 x631 verde |
| **35760084 cashout-globale** | — | **OK** — 0 violazioni, `chiuso_dall_utente x1`, `replay_cashout_utente x1`, «rientro disabilitato (chiusura manuale): premi Riprendi» x973, **R2 x5835** verde, 2 ordini (entrambi PRIMA del cash-out) |

R1 sollecitato **x9528** (35760084) e **x1773** (35674515), sempre verde: la catena
sospensione -> memoria -> rilettura gira davvero sui dati reali.
**Non verificato**: il ramo (b) «scaduto alla sospensione» non e' mai capitato sulle
registrazioni provate (`LAPSE 0` su tutti i contatori del banco, nessun
`ordine_scaduto_alla_sospensione`). Coperto solo dai test unitari.
`R1 x0` su 35777617: li' la sospensione con una lay appoggiata viva non capita.

### Comandi per rifarli
```
python -m Betfair.stream.backtest.certifica mike 35760084 --scenari base,taker   --diario <file>
python -m Betfair.stream.backtest.certifica mike 35674515 --scenari base         --diario <file>
python -m Betfair.stream.backtest.certifica mike 35777617 --scenari gol-precoce  --diario <file>
python -m Betfair.stream.backtest.certifica mike 35760084 --scenari cashout-globale --diario <file>
python -m pytest Betfair/ -q -p no:cacheprovider
cd frontend && npx vitest run src/lib && npm run build
```
Gli script A/B usati per il prima/dopo (nello scratchpad di sessione, riproducibili):
`kogreen_prima_dopo.py`, `unalay_prima_dopo.py`, `dimentica_cashout.py` — tutti ripristinati su `dopo`.

### Scenari nuovi in `Betfair/mike/tools/replay_registrazioni.py`
* `gol-precoce` (`:121-132`, descritto `:720`, nota che DICHIARA quante volte R1 ha avuto un caso `:769`):
  parametri identici a `base`, cambia la REGISTRAZIONE (35777617 = 2', 36006953 = 4', 35760084 = 7').
* `cashout-globale`: manda la richiesta `cashout` **vera** a `service.process_requests`, come dalla UI.

---

## 6. Documentazione

`COSTITUZIONE_MIKE.md`: §15.6 riscritta (riquadro datato «ORDINE DELL'UTENTE 16/09 h13»,
le 4 reazioni, R1, vincolo DB) · §15.7 con i due riquadri «MAI DUE LAY A MERCATO» (h16:15, J5,
`over_cover` escluso e dichiarato) e «SE CHIUDO TUTTO IO, IL BOT SI FERMA» (h18:20, R2, limite
del cash-out fuori dal bot) · §6 e §15.8 sul parametro senza effetto.

## 7. Fuori dal mio perimetro (segnalati, non toccati)

* `Betfair/stream/tests/test_banco_comune_2026_09_16.py::test_lordine_scaduto_alla_sospensione_lo_racconta_come_betfair`
  era ROSSO alle 16:41 (lavoro in corso di un altro delegato su `banco_comune.py`,
  `size_lapsed == 0.0`). All'ultima esecuzione (3898 verdi) e' verde.
* `over_cover`: `cancel` + `place` nello stesso giro (due BACK) — vedi §2.
* Cash-out fatto fuori dal bot — vedi §3.
