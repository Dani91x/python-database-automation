# TENNIS_SOLDI_VERI_COERENTE — «soldi veri» ha solo due esiti (04/10/2026)

Ramo: `worktree-agent-a2fd2012b8a292274` (base `c9eb58c` = master). Commit:
`8a4b105` (Safe, condotta di catena) · `d47347e` (UI, gesto veritiero) · `88a9495` (banco R11/R11b)
+ commit finale del referto. Niente push, niente master, niente DB scritto, nessun processo.

## 1. Causa confermata
- Rifiuto: `Betfair/stream/motore_ordini.py:1074-1076` (`mode not in LOW._servable_modes(proc)` ->
  `mode_non_servibile`). Tetto tennis = `TENNIS_LIVE_ORDER_MODE` (`tennis_live_order_worker.py:56-74`,
  default OFF), forzato a `'PAPER'` da `desktop/main.js:382`; il `.env` del principale NON ha la chiave
  (`LIVE_ORDER_MODE=LIVE` e' solo calcio) e `load_dotenv()` non sovrascrive. Nessun gesto UI arma il tennis.
- Tentativi bruciati: `bot_service._place_fail` contava `canale_rifiutato:mode_non_servibile` come esito
  di mercato (3 tentativi per segnale -> `place_retry` x2 + `place_exhausted` CRITICAL), un CRITICAL per
  tentativo in `execution._place_via_canale`, e `stats.motivo_blocco` (solo tetto operazioni) restava null.
- UI: nessun controllo sul gesto (`interruttori.ts` accendi/cambiaModalita/cambiaModalitaServizio).

## 2. PUNTO 1 NON APPLICATO — reperti bloccanti (proposta del coordinatore)
Alzare il tetto tennis (main.js non forza PAPER, ripiego su `LIVE_ORDER_MODE=LIVE`) manderebbe soldi veri
PER EREDITA' su almeno due strade:
- **B1 – Ladder/Grid del Tennis Terminal**: la modalita' degli ordini a mano E' il tetto del runner
  (`TennisLadderColumn.tsx:121` <- `tennis_live_now.state.order_mode` = `live_order_mode()`,
  `tennis_runner.py:1500`; `LadderView.tsx:1468-1471`, `GridView.tsx:178`). Il worker accetta SOLO righe
  con `mode == tetto` (`tennis_live_order_worker.py:1397` canale, `:1561` coda DB). Tetto LIVE => ogni
  clic sul ladder e' REALE al primo avvio, senza nessun gesto (e il ladder in prova sparisce). Nel calcio
  invece il ladder segue il modo EFFETTIVO (`runner.py:319`, riportato a PAPER a ogni avvio).
- **B2 – paper e live sommati nell'esposizione**: nel runner tennis ordini paper e live vivono sotto la
  STESSA capture-strategy della partita (`esecutore_tennis._strategy_for_mode`, `:138-147`, «una sola per
  tutte le modalita'»). `_read_matched_exposures` (`tennis_live_order_worker.py:736-755`,
  `blotter.get_exposures(strategy, ...)`) non filtra per client: green-up del desktop e verifica
  `reduces_liability` del motore conterebbero insieme le gambe paper (Safe tennis in prova, ladder) e quelle
  reali. Catalogo §7.21. Latente oggi solo perche' il runner tennis non e' mai LIVE.
- Gia' sano: i 4 bot tennis (riga `mode` esplicita, `guardie_tennis.modalita_esecuzione_bot`, all'avvio
  `ferma_bot_al_nuovo_avvio`, arm da scheda sempre `paper`); Safe tennis (`strategy_modes.tennis` scritto).
**Variante sicura proposta (cantiere a parte, DECISIONE PER L'UTENTE):** (a) tetto tennis = `TENNIS_LIVE_ORDER_MODE`
esplicito, altrimenti `LIVE_ORDER_MODE`, altrimenti PAPER; (b) modo EFFETTIVO tennis = LIVE solo se tetto
LIVE **e** una scelta UI LIVE letta e valida PER QUESTO AVVIO (`order_mode_boot_id`), altrimenti PAPER (la
prova del tennis non cambia mai); la lettura e' gia' gratis (`guardie_tennis.aggiorna_impostazioni` ->
`modo_ordini.registra_settings`, ~1/s); (c) `esecutore_tennis._blocco_apertura_modo` come il calcio;
`tennis_live_now.state.order_mode` = effettivo (+ `order_mode_tetto`), il worker accetta righe per
`_servable_modes(tetto)` + blocco aperture, specchio con il `mode` della riga; (d) capture-strategy PER
MODALITA' (come `_strategy_for_mode` del calcio). **Domanda:** quale interruttore governa il tennis in live —
(i) lo stesso «Ordini reali» del calcio (zero migrazioni; la riga va riscritta «calcio e tennis») oppure
(ii) un interruttore tennis separato (colonna + RPC + riga UI, migrazione)?
Senza la decisione, oggi vale l'esito (b) del brief: il gesto «soldi veri» sul tennis e' RIFIUTATO.

## 3. Che cosa ho cambiato (modifica minima, nessuna strategia toccata)
- `Betfair/safe_strategy/execution.py` (dopo `_critico_una_volta`): `PREFISSI_CATENA`, `blocco_di_catena`,
  `testo_blocco_catena`, `CATENA_PROVA_S=60`, `_episodio_catena`/`chiudi_episodi_catena`; in
  `_place_via_canale` CRITICAL una volta per episodio, episodio chiuso alla prima apertura accettata.
- `Betfair/safe_strategy/bot_service.py`: `_place_fail` -> `_place_fail_catena` (nessun tentativo consumato,
  segnale mai `final`, attesa 60 s), `_CATENA` per (sport, modalita'), `_catena_bloccata` (una sonda ogni
  60 s, nessuna riserva nell'attesa) in `scan_and_place`, `_BLOCCO["motivo"]=_motivo_catena()` a ogni giro,
  `_catena_ripristinata` in `_execute`, `_CATENA` in `svuota_le_cache`. Le chiusure non passano di qui.
- `Betfair/safe_strategy/tools/replay_registrazioni.py`: `_CATENA` nell'elenco esplicito delle cache.
- `frontend/src/lib/interruttori.ts`: `CatenaLive`, `SoldiVeriNonServiti`, `motivoSoldiVeriNonServiti`,
  `assicuraSoldiVeriServiti`; guardia PRIMA di scrivere in `accendi`, `cambiaModalita` (strategie),
  `cambiaModalitaServizio` (Omega, Mike, 4 bot tennis). Solo verso `live`; la prova non legge niente.
- `frontend/src/components/controlroom/comandiBot.ts`: guardia nel gesto «solo tennis».
- `frontend/src/pages/ControlRoom.tsx`: `catenaLive` = runner tennis dal canale (gia' in memoria,
  `vm.runnerTennis`, via ref) + «Ordini reali» letto UNA volta al gesto (`leggiModoOrdini`).
- `frontend/src/components/safestrategy/safeActivity.ts`: traduzione del motivo `blocco_di_catena`.
- `Betfair/stream/backtest/trasporto_rapido.py`: scenari R11/R11b in CODA (gli altri identici).

## 4. Che cosa vede il trader
(a) catena armata: nessun messaggio nuovo, il gesto scrive come prima (test «catena armata»).
(b) gesto rifiutato (errore della Control Room, niente scritto), es. Safe tennis oggi:
«Safe tennis: soldi veri NON attivati — il runner tennis gira solo in PROVA (PAPER): i soldi veri sul tennis
non sono abilitati in questa installazione e ogni ordine reale verrebbe rifiutato. Accendi il bot in prova.
Non ho scritto niente: il bot resta com'era.» Calcio: «... «Ordini reali» e' su PAPER: gli ordini reali
verrebbero rifiutati. Porta prima «Ordini reali» a LIVE (riga in cima ai bot), poi rifai il gesto ...»;
runner tennis muto / «Ordini reali» illeggibile: rifiuto fail-closed con «riprova».
(c) blocco sopravvenuto (Safe, riga del bot «acceso ma non apre: ...»): «tennis live: aperture in soldi veri
FERME: il runner tennis gira solo in PAPER e non puo' piazzare ordini in soldi veri. Porta il bot in prova,
oppure abilita il runner tennis ai soldi veri e riavvia l'app. Le chiusure non si fermano; si riprova da solo
ogni 60 s.» (varianti per «Ordini reali» e per il freno).

## 5. MATRICE (13 interruttori) — strada, governo, casi a/b/c
| Interruttore | Strada ordini | Governo live | (a) opera | (b) gesto rifiutato | (c) blocco sopravvenuto |
|---|---|---|---|---|---|
| Omega | canale 47331 (`omega_service.py:2982-2991`; REST se `execution_mode='rest'`) | motore: tetto+effettivo+kill (`motore_ordini.py:1074-1116`) | R1 rapido omega OK | `soldiVeriCatena.test.ts` (omega) | ⚠ NON fatto: `mode_non_servibile` consuma `LEG_RETRY_MAX` (`_RIFIUTI_PRIMA_DEL_MERCATO` :2141), nessun `motivo_blocco`; trasporto R11/R11b OK, condotta N/A |
| Mike | live = REST dal processo (`service.py:883`, `_RealMarket.place_order_live`); paper = canale | `_live_brake` (tetto+effettivo+kill) + `MIKE_LIVE_ENABLED` | gia' live oggi; `test_mike_paper_vs_live_2026_09_13.py` | `soldiVeriCatena.test.ts` (mike) | GIA' coperto in parte: `aperture_ferme`, 1 CRITICAL per motivo/partita, nessun tentativo bruciato (`test_mike_aperture_ferme_d1quater_2026_09_29.py`); ⚠ `stats.motivo_blocco` non lo riporta (:4241) |
| Scalper calcio | flumine PROPRIO (`scalper_session.py:682-697`) | `dry_run` di sessione, freno | ⊘ qui | ⊘: non passa da runner ne' «Ordini reali» (guardia `null`, testata) | freno gia' coperto (`test_scalper_freno_origine_2026_09_26.py`); ⚠ auto-mode arma SEMPRE `dry_run=True` (`auto_mode.py:311-332`) = «soldi veri» senza ordini |
| Safe base / esatto / punta | canale 47331 (`porta_ordini.py:742-767`) | motore; REST: `_live_brake` | R1 rapido safe_base OK | `soldiVeriCatena.test.ts` (safe-base + tabella) | FATTO: `test_soldi_veri_catena_2026_10_04.py` + R11/R11b safe_base |
| Safe modello / a mano | stesso `_execute` di Safe | idem | come sopra | tabella del test UI | FATTO lato servizio (stesso `_place_fail`); pre-blocco solo in `scan_and_place` (le richieste a mano partono e ricevono il loro rifiuto) |
| Safe tennis | canale 47332 (`SAFE_TENNIS_ORDINI_VIA_CANALE=1`) | tetto runner tennis (nessun effettivo) | ⊘ finche' il punto 1 non e' deciso (oggi il tetto e' PAPER) | `soldiVeriCatena.test.ts` (incidente, scheda tennis) | FATTO: test + R11 safe_tennis (R11b N/A dichiarato) |
| tennis Scalper/Pro/FLB/Swing | ospitati nel runner tennis (`tennis_runner.py:847-913`) | tetto runner + riga `mode` + `dry_run` per partita | ⊘ (tetto PAPER) | `soldiVeriCatena.test.ts` (accendi + cambiaModalitaServizio) | ⊘ tetto non cambia a runner vivo; ⚠ da Control Room il live arma con `dry_run=True` (doppio gesto per partita, `tennis_bot_service.py:874`) e `motivo_blocco` non lo dice |

## 6. Test
Nuovi: `Betfair/safe_strategy/tests/test_soldi_veri_catena_2026_10_04.py` (25 casi),
`frontend/src/lib/soldiVeriCatena.test.ts` (14). Modificati: nessun test esistente.
- `pytest Betfair/safe_strategy Betfair/stream/backtest -q -p no:cacheprovider`: **2261 passed**, 3 skipped,
  1 xfailed (191 s). (Prima del ritocco: 1 rosso H-16 sul kind nuovo `catena_ripristinata` -> tolto il kind,
  il ripristino va solo nel log del processo: contratto H-16 invariato.)
- `npx tsc -p tsconfig.app.json --noEmit` = 0. `npx vitest run src/components/controlroom src/lib
  src/components/safestrategy src/pages src/fotografia`: **247 file, 4130 passed**, 1 skipped (514 s);
  fotografie invariate (nessuna rigenerata).
- NON lanciata la suite Python intera (solo i pacchetti toccati + backtest); `stream/tennis_live` non toccato.

Falsificazione (`AUDIT_2026-10-04/strumenti/falsifica.py`, ripristino `git checkout`, `git status` pulito):
| Mutazione | Esito |
|---|---|
| M1 catena mai riconosciuta | ROSSO |
| M2 CRITICAL a ogni tentativo | ROSSO |
| M3 episodio mai chiuso all'accettazione | ROSSO |
| M4 nessun blocco (raffica) | ROSSO |
| M5 motivo_blocco non pubblicato | ROSSO |
| M6 blocco mai chiuso dopo un'apertura | ROSSO |
| M7 tentativi consumati sul blocco | ROSSO |
| U1 tennis: tetto ignorato · U2 «Ordini reali» ignorato · U3 runner muto = via libera | ROSSO ×3 |
| U4 accendi / U5 cambiaModalita / U6 cambiaModalitaServizio / U7 scheda tennis senza guardia | ROSSO ×4 |
| U8 guardia anche in prova | ROSSO |
| B1 banco: catena mai riconosciuta (replay safe_tennis canale) | ROSSO (R11 KO) |
| B2 banco: CRITICAL a ogni tentativo | ROSSO (R11 KO) |
| B3 banco: tolto il controllo del tetto nel motore | VERDE: seconda rete `_client_for_mode` (`live_client_assente`), stesso codice `mode_non_servibile` — non reintroduce il difetto |

## 7. Replay (punto d'ingresso unico, uno alla volta)
- `certifica safe_tennis 35795993 --scenari rapidi --trasporto entrambi`: 48 s. R1..R2b IDENTICI al referto
  del coordinatore (14 OK, stessi controlli); nuovi R11 OK (9 controlli), R11b N/A dichiarato; 16 scenari,
  KO 0. Parita' coda/canale RAGGIUNTA: coda 1053 decisioni / 2 azioni, canale 1054 / 2 (identico).
  `replay/safe_tennis_rapidi_entrambi_DOPO.txt`.
- `certifica safe_base 35760084 ... --data-dir <principale>\_live_raw`: 163 s, 16 OK; parita' 3508/3512 2/2
  (identica ai referti del 02/10, `PARITA_SAFE_ENV`). `certifica omega 35760084 ...`: 68 s, 15 OK + R8 N/A
  (come prima), parita' 438/438 0/0. Nessun referto MASTER di oggi per questi due: confronto col 02/10.

## 8. Carico
Servizio Safe: zero chiamate nuove; MENO comandi al runner (una sonda ogni 60 s invece di 3 tentativi per
segnale), righe `skip` deduplicate (`_log_skip`). UI: tennis 0 chiamate (canale gia' aperto); calcio +1
`get_live_settings` SOLO al clic «soldi veri» (nessun polling). Betfair: 0.

## 9. Che cosa deve fare l'utente
Niente migrazioni, niente `.env`. Per attivarlo: `npm run build` in `frontend/` e riavvio dell'app (a
posizioni live chiuse). Effetto: «soldi veri» sul tennis sara' rifiutato col motivo finche' non decide il
punto 2; sul calcio passa se «Ordini reali» e' LIVE (oggi lo e').

## 10. Reperti fuori perimetro
1. Omega: `mode_non_servibile` brucia `LEG_RETRY_MAX`, nessun `motivo_blocco`; REST live di Omega non legge
   il modo effettivo (`omega_service.py:2739-2747`, solo kill-switch).
2. Mike: `stats.motivo_blocco` non riporta `aperture_ferme` (`service.py:4241`).
3. Scalper calcio: in live l'auto-mode arma sempre `dry_run=True` (`auto_mode.py:311-332`).
4. 4 bot tennis: «soldi veri» da Control Room = `dry_run=True` per partita (doppio gesto, migrazione del
   24/09): il bot «acceso in soldi veri» non piazza finche' l'utente non toglie il dry-run partita per partita.
5. Runner tennis: `_pubblica_modo_ordini_se_cambiato` pubblica sul 47332 `modo_ordini.stato_corrente()`, che
   usa `LIVE_ORDER_MODE` (tetto CALCIO): sul canale tennis il topic `modo_ordini` puo' dire LIVE col runner
   tennis in PAPER.
6. Le pagine dei singoli bot (`SafeStrategy.tsx`, `Omega.tsx`, `useSafeBot.ts`, `useMike.ts`) non passano
   ancora `catenaLive`: la guardia vale dalla Control Room (dove l'utente ha agito oggi).
7. `TennisLadderColumn.tsx:163` suggerisce ancora «imposta TENNIS_LIVE_ORDER_MODE=PAPER e riavvia».

## 11. Non fatto / non verificato
- Punto 1 (tetto tennis) e test di contratto su `main.js`: NON fatti (reperti B1/B2, decisione).
- Punto 2 (runner che dichiara tetto+effettivo): l'hello/battito del 47332 dichiara gia' il tetto ed e' cio'
  che la guardia usa; l'effettivo tennis non esiste finche' non si decide il punto 2.
- Condotta (c) per Omega, Mike (`motivo_blocco`), bot tennis: non cambiata (reperti 1-4).
- Blocco dopo un comando PARCHEGGIATO `in_aggancio` e poi rifiutato per modo (evento `rifiutato` invece
  dell'ack): non classificato come catena.
- Non verificato dal vivo (app, ladder, Control Room reale); suite Python intera non lanciata.

## 13. PASSO 1 della revisione — il buco in_aggancio (commit `0001e86`, `b5a25ff` R11c)
**Dove nasce davvero l'asincrono.** Nel motore il controllo del modo (`_controlla`, `motore_ordini.py:983`)
viene PRIMA di `_serve_aggancio` (`:984`): con il framework vivo un mercato non seguito riceve il rifiuto
`mode_non_servibile` SUBITO. Il rifiuto asincrono nasce solo a runner SENZA framework (`_controlla`
`:1047-1068`: `flumine is None` -> aggancio chiesto, `attende_runner`, `return` PRIMA del modo/freno), poi
`avanza_aggancio` (`:1623`) rifa' le guardie ed emette l'evento terminale `rifiutato` con `errore`/`error_code`
(`_estremi_errore`, `:1527-1531`). E' esattamente il runner tennis dell'incidente (in attesa, nessuna partita):
nel servizio arrivava a `_risolvi_una_via_canale` -> `_flumine_no_fill_error(reason="canale_rifiutato")`
(il `flumine_no_fill` dei log), poi i ritenti sincroni.
**Correzione (servizio Safe, nessuna chiamata in piu': legge l'evento gia' in memoria della porta):**
- `execution.PlaceOutcome.catena_servita` (default False): True solo con ack accettato SENZA motivo (guardie
  di modo e freno gia' passate). `_place_via_canale` chiude l'episodio solo in quel caso (`elif not is_closing
  and not ack.motivo`), mai sull'ack `in_aggancio`.
- `bot_service._execute`: ripristino solo se `out.status == "open" or out.catena_servita` (prima: ogni pending).
- `bot_service._risolvi_una_via_canale` (aperture): evento non-rifiuto (fase fuori da `rifiutato`/`errore`) di
  un ordine mandato DOPO l'inizio del blocco (`meta.canale_inviato_at` >= `_CATENA.dal`) = prova certa ->
  ripristino; evento terminale `rifiutato` con errore di catena -> `X.rifiuto_catena_asincrono` (stesso
  episodio dell'ack sincrono, chiave (attore, mode, codice)) + `_place_fail_catena`: riga 'error'
  `blocco_catena`, nessun tentativo, nessun `flumine_no_fill`.
- Test esistente MODIFICATO (dichiarato): `test_soldi_veri_catena_2026_10_04.py::test_apertura_partita_chiude_il_blocco`
  asseriva che un `pending` qualunque chiude il blocco (comportamento sbagliato, catalogo §7.28): ora asserisce che
  NON lo chiude e che lo chiude il `pending` con `catena_servita=True`.
- Test nuovi: `test_soldi_veri_catena_aggancio_2026_10_04.py` (6, `PortaCanale` vera, eventi da
  `riga_specchio_da_esito` + `_estremi_errore`). Banco: **R11c** (Safe calcio e tennis; Omega N/A): sonde dal
  SERVIZIO VERO (`BS._execute`), 2 asincrone a runner senza framework (la seconda col blocco gia' in corso) + 1
  sincrona: 15 controlli (motivo mai sparito, 1 CRITICAL, nessun retry/exhausted/no_fill, budget intatto,
  nessuna «catena ripristinata», nessun ordine/REST).
- Falsificazione: A1 pending ripristina · A2 ack in_aggancio chiude l'episodio · A3 asincrono non
  classificato · A4 ordine di prima del blocco lo chiude · A5 evento 'rifiutato' ripristina: test unitari
  ROSSI tutte e 5; banco R11c ROSSO su A1, A2, A3, A5; A4 VERDE nel banco (nessun ordine anteriore al blocco
  nello scenario: coperta dal test unitario).
- Numeri: pytest `safe_strategy + stream/backtest + omega` **3711 passed**, 6 skipped, 1 xfail (91 s).
  Replay: safe_tennis 17 scenari KO 0, parita' 1053/2 · 1054/2 (identica); safe_base 17 KO 0, 3508/3512 2/2;
  omega 15 OK + R8, R11c N/A, 438/438 0/0.

**Punto 3 — verificare il modo PRIMA di parcheggiare (NON applicato, decide il coordinatore).**
Proposta: nel ramo `flumine is None` di `_controlla`, prima dell'aggancio: `mode not in _servable_modes(proc)`
-> `Rifiuto(M_MODE)` (vale anche per le chiusure: il processo non ha comunque il client), e per le sole APERTURE
non `riduce` anche `_blocco_modo` e kill-switch. Pro: rifiuto sincrono anche a runner fermo (una sola strada,
niente `in_aggancio` da distinguere); soprattutto NESSUN aggancio inutile: oggi ogni sonda live su una partita
nuova fa partire/risottoscrivere lo stream del runner (`ag.richiedi`) per un comando gia' destinato al rifiuto =
carico Betfair per niente; il modo e' di processo, non dipende dal mercato. Contro: tocca la strada di TUTTI i
bot (Safe, Omega, Mike paper, ordini a mano sul canale); le riduzioni dichiarate non si possono verificare senza
framework (restano parcheggiate come oggi); i test del motore che si aspettano `in_aggancio` a runner fermo
vanno rivisti; il banco R10/R11c cambierebbe esito (R11c diventerebbe sincrono). La difesa del servizio resta
comunque necessaria (ack vecchi, riavvii).

**Punto 5 — righe per sonda.** Si': ogni sonda e' una riserva in `safe_strategy_trades` chiusa 'error'
(`scan_and_place` -> `db.insert_trade` prima di `_execute`), piu' un `canale_rifiutato` (non critico) in
attivita'. Con segnali continui e blocco tutto il giorno: fino a 1.440 righe/giorno per (sport, modalita'),
in entrambe le tabelle. NON applicato (non e' minimo): opzioni per il coordinatore — (a) dopo il rifiuto di
catena cancellare la riserva della sonda (come Omega `_leg_certain_failure`), lasciando la PRIMA dell'episodio
e la traccia in attivita' con `tentativo_nell_episodio`; non tocca P&L (riga senza ordine), ne' tetti
(`_counts_as_placed` esclude le 'error'), ne' `_traded_keys` (esclude le 'error'); costo: la riserva cancellata
non e' piu' interrogabile e il diario del runner punta a un id assente. (b) sonda piu' rada (es. 5 min) = 288/giorno,
nessun cambio di struttura. (c) sonda senza riserva: comando con un ref di sonda non legato a una riga —
cambia il protocollo, sconsigliato.

## 14. Dopo la verifica del coordinatore (passo 1 verificato su 20ff0ae)
- `_apertura` fissata (commit `64760bb`): 4 casi nuovi (chiusura con `closes_trade_id` in colonna e nel
  `meta`): l'evento positivo di una CHIUSURA a blocco in corso non toglie il blocco ne' chiude l'episodio;
  il `rifiutato` terminale di una chiusura non registra un blocco. Mutazioni: `_apertura` sempre True (quella
  del coordinatore) -> 4 rossi su 10; solo colonna -> rosso; solo meta -> rosso. 10/10 verdi ripristinato.
- DECISIONI: punto 3 (modo prima dell'aggancio nel motore) NON applicato, resta proposta (§13). Punto 5
  REPERTO APERTO: una riga `error` + un `canale_rifiutato` per sonda (60 s) finche' dura il blocco, opzioni
  (a)/(b)/(c) in §13. Punto E: l'utente ha scelto lo STESSO «Ordini reali» del calcio per il tennis; il
  cantiere del tetto tennis e' di un altro delegato (file esclusi da questo ramo: `desktop/main.js`,
  `Betfair/stream/tennis_live/**`, `motore_ordini.py`, `modo_ordini.py`, `frontend/src/components/tennis/**`).

## 15. Passi A-D (dopo 8fabe7a) — «per tutti i bot: soldi veri = ordini veri»
Commit: A `2ac7464` · B `a209114` + `ac21028` + contratto · C `deb09d9` + `34cd4e4` · D `217e237` ·
prova strada diretta Safe `test(safe): strada diretta...` · script falsificazione aggiornato a ogni passo.

### A. Omega (`Betfair/omega/omega_service.py`)
- `_RIFIUTI_PRIMA_DEL_MERCATO` + `mode_non_servibile`: il rifiuto del runner per modalita' non consuma
  `LEG_RETRY_MAX`. Stato `_CATENA_OMEGA` (per modalita'): `_registra_catena`, `_catena_omega_bloccata` (prima
  della riserva: nessuna riga/comando fra due sonde, una ogni `X.CATENA_PROVA_S`), `_catena_omega_ripristinata`
  (prova certa: ack senza motivo, freni REST passati, evento non-rifiuto di un ordine mandato dopo l'inizio).
- REST live (`_freno_rest_live` = kill-switch poi `execution._live_brake`): rispetta «Ordini reali» come il canale
  (prima solo kill-switch: con «Ordini reali» PAPER il REST di Omega mandava soldi veri). Stesso freno sul manuale
  live REST. CRITICAL una volta per episodio (prima uno per tentativo).
- `_chiudi_da_evento`: rifiuto asincrono dopo l'aggancio (aperture) = `X.rifiuto_catena_asincrono` (stesso episodio)
  + riga no_fill senza tentativo; chiusure escluse.
- `stats.motivo_blocco` solo a blocco in corso (assente = nessun blocco: le tracce golden restano identiche).
- Test nuovi `omega/tests/test_omega_soldi_veri_catena_2026_10_04.py` (6). MODIFICATI (dichiarati):
  `omega/conftest.py` (+ fixture `_freni_live_dichiarati`: tetto LIVE + «Ordini reali» LIVE in memoria, come il
  conftest di Safe; senza, i test del REST live leggerebbero il .env e il DB), `test_omega_freno_non_consuma_
  tentativi_2026_09_26.py::_giro` (passo fra i giri portato oltre `CATENA_PROVA_S`: fra due sonde non parte
  nessuna riserva, voluto; asserzioni invariate). `_CATENA_OMEGA` nei reset (conftest, replay).
- Falsificazione O1-O7 tutte ROSSE (mode consuma, raffica, REST senza modo, motivo non pubblicato, asincrono non
  classificato, CRITICAL a ogni tentativo, chiusura trattata come apertura).
- Replay omega rapidi entrambi: 15 OK + R8/R11c N/A, parita' 438/438 0/0 (identica). `base`/`apertura` su
  35760084: 0 azioni (come prima: la registrazione non fa aprire Omega). La prova «parte un ordine vero» e' il
  test `test_rest_live_rispetta_ordini_reali` (riapre «Ordini reali» -> `place_lay_live`) + R1 rapido (canale live).

### B. Guardia del gesto nelle pagine + strada dichiarata da Safe
- Punti d'ingresso al live nel frontend (grep `activate*`/`creaInterruttori`): `ControlRoom.tsx`
  (`creaComandiControlRoom`), `pages/Omega.tsx` (`handleStart` -> `activateOmega`, `applyMode`),
  `components/mike/useMike.ts` (`start` -> `activateMike`, `setMode`), `components/safestrategy/useSafeBot.ts`
  (`start` -> `activateSafe`, `setMode`), `pages/SafeStrategy.tsx` (`comandiStrategie`). Tutti passano da
  `verificaSoldiVeri`/`verificaSoldiVeriSafe`/`catenaLive` (codice unico in `interruttori.ts`). Fuori dal
  perimetro (tennis, altro delegato): `TennisBotPanel.armTennisBot`, `TennisBotServiceParamsSheet`. Lo scalper
  per partita (`lib/scalper.ts::activateScalper`, scheda Segui Live) non passa da «Ordini reali» (flumine proprio).
- Safe pubblica `stats.strade_ordini` (`bot_service.strade_ordini`: `runner_calcio`/`runner_tennis`/`diretta`
  dall'interruttore d'ambiente, zero IO); la UI la legge (`useControlRoom.stradaTennis`, `leggiStradaOrdini`).
  Safe tennis: strada `diretta` -> decide «Ordini reali» (il runner tennis NON c'entra: il caso di oggi con
  `SAFE_TENNIS_ORDINI_VIA_CANALE=0`); `runner_tennis` -> tetto del runner tennis; non dichiarata -> accettato solo
  se ENTRAMBE le catene servono, altrimenti rifiuto col motivo.
- Test: `soldiVeriCatena.test.ts` (21; MODIFICATO: ARMATA/INCIDENTE con `stradaSafeTennis: 'runner_tennis'`),
  `soldiVeriPuntiIngresso.test.ts` (10, contratto sul sorgente), pytest `test_il_servizio_dichiara_la_strada...`
  (3, `run_once` vero). MODIFICATO `pages/Mike.test.tsx`: `getLiveSettings` dichiarato armato (riga vera), il
  test portava Mike in live senza «Ordini reali»: la guardia lo rifiutava (fail-closed, corretto).
- Falsificazione V1-V9 ROSSE (V2 rifatta con mutazione valida; V8/V9 rese rosse aggiungendo il contratto).

### C. Mike (commit separato, solo pubblicazione)
- `service.py`: `motivo_aperture_ferme(tracked)` + `_unisci_motivi`; `stats.motivo_blocco` = tetto partite E
  aperture ferme (per modalita' e causa, con il numero di partite). Condotta invariata. Testo da
  `execution.spiega_blocco_catena` (estratta da `testo_blocco_catena`, testo di Safe identico).
- Test `mike/tests/test_mike_motivo_blocco_catena_2026_10_04.py` (3: pura, `run_once` vero, flusso D1-quater vero
  con ordine VERO che parte quando «Ordini reali» torna LIVE). Mutazioni C1-C3 ROSSE (C3 dopo aver rafforzato
  l'asserzione).
- Replay `certifica mike 35760084 --scenari base,riavvio,feed-stantio --trasporto canale`: 249 s; base e riavvio
  5879 decisioni / 6 azioni / P&L -14,17; feed-stantio 1024 / 0; 3 OK. Diff riga per riga con
  `AUDIT_2026-10-02/replay/mike_base_riavvio_feedstantio_INTEGRATA.txt`: solo l'impronta del codice cambia.

### D. Scalper calcio (i 4 bot tennis tolti: altro delegato)
- Prova del difetto: `scalper/auto_mode.py` `dry_run_alla_nascita` ritornava SEMPRE True (D3 del 25/09):
  interruttore in soldi veri -> sessioni `dry_run=True` (client `paper_trade=True`, `scalper_session.py:1077`):
  nessun ordine vero; la Control Room diceva «nascono in dry-run ... finche' non lo togli per partita».
- Correzione: `dry_run_alla_nascita(m) = m != 'live'` (fail-closed); `conflitto_modalita` di nuovo simmetrico
  (in live una sessione in prova viva blocca l'armamento: paper e live mai insieme). Il gesto resta esplicito
  (`scalper_auto_activate(p_mode)`), all'avvio nuovo l'interruttore si spegne (`ferma_al_nuovo_avvio`), strategia
  e stake invariati. UI: `notaAutoScalper` dice cio' che il supervisore dichiara (`nascono_in_dry_run`) e il conflitto.
- Test MODIFICATI (asserivano D3, ora vietato): `test_scalper_auto_mode_2026_09_25.py::test_conflitto_modalita`,
  `test_d3_dry_run_alla_nascita_sempre_vero` -> `test_dry_run_alla_nascita_segue_la_modalita_scritta`,
  `test_live_nasce_in_dry_run` -> `test_live_nasce_live`, `test_live_con_sessioni_in_dry_run_continua_ad_armare`
  -> `test_live_con_una_sessione_in_prova_viva_non_arma_e_lo_dice`; `scalperAuto.test.ts` (frase esatta).
- Banco: scenario nuovo `auto-live` (riga dal supervisore, controllo AL1). Replay `scalper_calcio 35797769
  --scenari base,auto-live --worker 1`: 252 s; auto-live = base numero per numero (121012 decisioni, 538 azioni,
  ordini 47, dry_run=False). Mutazioni D1-D5 ROSSE (D1 anche sul banco: AL1).
- **REPERTO APERTO (non mio)**: `base` e' KO su master c9eb58c IDENTICO (B2 x1, K1 x4, K5 x2; il 30/09 era OK):
  `replay/scalper_calcio_base_MASTER_c9eb58c.txt`. Lo scalper calcio NON e' certificato oggi.

### Numeri finali (su 441ae99 + 1a1e155)
- pytest `safe_strategy + omega + mike + stream/backtest + stream/tests`: 8718 passed, 3 failed, 31 skipped
  (1006 s). Dei 3: `test_strada_unica_banco...::test_profilo_rapido_verde...[safe_base|omega]` contavano 14
  scenari del profilo rapido -> MODIFICATO a 17 (R11/R11b/R11c, commit 1a1e155), dichiarato; `test_canale_scan_f4
  ::test_il_client_col_canale_giu_non_solleva_e_si_riaggancia` verde da solo (temporizzazione sotto carico,
  file non toccato). Rilanciati: 59/59 verdi.
- vitest controlroom+lib+safestrategy+mike+pages+fotografia: 4285 passed, 2 failed, 1 skipped (261 file); i 2
  (`SafeStrategy.test.tsx` tab tennis, `BotParamsSheet.test.tsx` campo 35) verdi da soli 75/75 (timeout sotto
  carico). tsc = 0. Fotografie invariate.
- Replay finale safe_tennis rapidi entrambi: 17 scenari KO 0, parita' 1053/2 · 1054/2 (identica), 61 s.

### Matrice finale «soldi veri scelto + catena armata -> parte un ordine VERO»
| Interruttore | Prova (a) | Gesto (b) | Blocco sopravvenuto (c) |
|---|---|---|---|
| Omega | `test_rest_live_rispetta_ordini_reali` (finale) + R1 rapido | test UI + contratto | A (test + O1-O7) |
| Mike | `test_la_causa_sparisce_e_le_aperture_ripartono`, `test_ordini_reali_off_il_motivo...` | test UI + contratto | condotta D1-quater + C |
| Scalper calcio | replay `auto-live` (AL1) + `test_live_nasce_live` | ⊘ («Ordini reali» non lo governa: flumine proprio) | freno gia' coperto; conflitto detto |
| Safe base/esatto/punta/modello/a mano | `test_strada_diretta...[calcio]` + R1 safe_base | test UI | Safe (test + R11/R11b/R11c) |
| Safe tennis | `test_strada_diretta...[tennis]` (strada diretta, oggi) | test UI (strada dichiarata) | Safe + R11/R11c |

## 12. Dal vivo al prossimo avvio
Control Room, scheda tennis: «soldi veri» su Safe tennis -> errore rosso col testo del §4(b), riga del bot
invariata (DB `safe_strategy_control.params.strategy_modes.tennis` resta com'era). Con un bot Safe calcio in
live e «Ordini reali» portato a PAPER: riga del bot «acceso ma non apre: calcio live: aperture in soldi veri
FERME ...», UN `canale_rifiutato` critical, nessun `place_exhausted`.

