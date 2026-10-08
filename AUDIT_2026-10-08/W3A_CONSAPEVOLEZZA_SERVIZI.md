# W3a - I BOT SANNO SUBITO DEGLI ORDINI ESTERNI: Mike, Omega, Safe (08/10/2026)

Delegato di costruzione (Opus), worktree `.claude/worktrees/agent-ada08f62b75e0e29a`,
partenza `b5547eb` (il worktree era su `8226d76`: portato con `git merge --ff-only b5547eb`,
nessun file locale), poi - su ordine del coordinatore - portato alla cima
`claude/blissful-sagan-hri7o6` = `3b8ce19` (W2 5cc7103, C5, C12, C14, C15): modifiche messe da parte
con uno stash con etichetta unica `w3a-agent-ada08-merge-tip` (SHA b4798f12), avanzamento
fast-forward a `3b8ce19`, applicazione dello stash per SHA (nessun conflitto: `banco_comune.py`
fuso in automatico, TENUTE ENTRAMBE le modifiche - `scambi_veri` di C15 e le mie funzioni additive
`annulla_come_utente`, `pubblica_conto_al_client`, `latenza_dal_canale`, chiavi
`size_cancelled/size_lapsed` del finto), voce di stash eliminata ritrovandola per etichetta.
Poi, su secondo ordine del coordinatore, portato a `16d6c67` (cantieri 6, W1, 10) con la
stessa procedura (stash `w3a-agent-ada08-merge-16d6c67`, SHA aaf945e1, applicato per SHA senza
conflitti; file in comune con la cima: `certifica.py` e `applica_bot.py`, fusi in automatico,
tenute entrambe le modifiche; voce eliminata per etichetta). Poi ancora a `1ac69d0` (stash
`w3a-agent-ada08-merge-1ac69d0`, `applica_bot.py` fuso in automatico) e infine alla cima integrata
`d0cf8b94` (stash `w3a-agent-ada08-merge-d0cf8b9`; nessun file `Betfair/` cambia fra le due), sempre
senza conflitti, voci di stash eliminate per etichetta. **HEAD del worktree = `d0cf8b94`.**
Niente commit. NON dichiaro "certificato": va rifatto dal coordinatore.
Cartella dei referti dei replay: `AUDIT_2026-10-08/W3A_CONSAPEVOLEZZA_SERVIZI/`.
I numeri di riga della sezione 1 si riferiscono a `b5547eb` (i file dei bot non cambiano fra
b5547eb e 3b8ce19 nei punti citati).

## 1. Cause radice (verificate sul codice di `b5547eb`)

| # | Lacuna | Dove (b5547eb) | Causa |
|---|---|---|---|
| 1 | Omega e Safe non usano il canale `conto` | `omega_service.sorveglia_posizione_di_conto` (~4692, cadenza `conto_every_s`=120 s), `safe_strategy/bot_service._sorveglia_posizione_di_conto` (~1857, 30 s, max 2 mercati/ciclo) | solo REST a cadenza: 30-120 s (+ la dormita del ciclo di Omega, 20-60 s) |
| 2 | PAPER: nessun bot vede gli interventi esterni | Mike `service.py:3315` (`if mode == "paper": return False`), Omega `_gruppi_di_conto` (`mode != live` scartato), Safe (`mode != live` scartato) | il paper non aveva una fonte del "conto": il runner paper non pubblicava niente |
| 3 | Riduzione parziale dall'esterno = solo log | Mike `service.py:3389-3401`, Omega ~4752, Safe ~1931 | regola R10 del 16/09 (proteggere il residuo) contraria all'ordine dell'utente dell'08/10 |
| 4 | Mike: appoggiata annullata dal sito riletta come scaduta | `_classifica_ordine` (~2747) -> `scaduto` -> `_chiudi_gamba_scaduta` -> il motore ri-appoggia; in piu' `omega_market.order_state_by_bet_id` NON restituiva `sizeCancelled` (impossibile distinguere annullo e scadenza per bet_id) | `size_cancelled` mai usato per distinguere chi ha tolto l'ordine |
| 5 | (reperto W2 del coordinatore) verdetto in SIZE | i tre `_verdetto_di_conto`: netto BACK-LAY della selezione mescolato con gli ordini dell'utente | un green-up dell'utente di un ordine SUO con prezzo mosso cambia il netto in size: falso «ridotta»/«chiusa» |

## 2. Che cosa ho cambiato (file:riga nel worktree)

### 2.1 Il meccanismo unico — `Betfair/stream/esiti_ordini_canale.py`
* `ClientEsiti` (~238): piu' topic separati da virgola (`conto,conto_paper`, la grammatica del
  lettore di `local_channel`); rifiuta una fotografia il cui `modo` contraddice il topic.
* `payload_conto` (~757): chiave ADDITIVA `modo: "live"`.
* Costanti `MODO_LIVE/MODO_PAPER/TOPIC_CONTO_PAPER/TOPIC_CONTO_TUTTI` e `_modo_coerente` (~682-711).
* `MemoriaConto` (~840): fotografie per `(modo, mercato)` (la chiave live resta il market_id nudo:
  contratto del 30/09), `_impronta` del contenuto, callback `avvisa(market_id, modo)` chiamata FUORI
  dal lucchetto SOLO quando il contenuto cambia (gli snap ripetuti non svegliano).
* Fotografia PAPER (~960-1060): `ordine_paper_del_conto` (un ordine flumine del blotter paper ->
  grafia di `listCurrentOrders`, le STESSE chiavi di `_CAMPI_ORDINE_CONTO`+`priceSize`),
  `payload_conto_paper`, `pubblica_conto_paper`, `con_ref_del_bot` (riconoscimento per `bet_id`).
* `direzione_di_conto` + `verdetto_in_esposizione` (~1000): il verdetto in ESPOSIZIONE (vedi 2.6).
* `SorveglianzaConto` (~1110-1300): il meccanismo del 30/09 di Mike ESTRATTO (canale, versioni
  `visto`, `segnale`, `firma` anti-ripetizione, `tempi`, `latenza_ms`, `avvia` con env ACCESO di
  serie e piu' porte, `azzera`) + la SVEGLIA (`interessa`, `su_sveglia`, `sveglia_alzata`,
  `dormi(pausa, minimo_s)` col pavimento).

### 2.2 Runner — `Betfair/stream/engine/live_trading_strategy.py` (solo pubblicazione, additiva)
* `process_orders` (~207): con `mode == "paper"` chiama `_pubblica_conto_paper(market)`: la
  fotografia di TUTTI gli ordini della strategia paper sul mercato (bot e manuali dell'app) sul
  topic `conto_paper`, write-on-change (firma per mercato, tetto 2000), mai solleva. La strategia
  LIVE non pubblica il paper; `start` (montaggio del 30/09) invariato.

### 2.3 Mike — `Betfair/mike/service.py`
* Stato del conto (~2967-2985): `_CONTO = SorveglianzaConto("mike", MIKE_CONTO_CANALE)`; i nomi
  di modulo `_CONTO_CANALE/_CONTO_VISTO/_CONTO_SEGNALE/_CONTO_FIRMA` sono GLI STESSI oggetti.
* `_verdetto_di_conto` (~3200): stessa aritmetica + il metro in esposizione (2.6), chiave
  `metro` nel dettaglio.
* `_segnale_conto_dal_canale(modo=...)` (~3245) sul meccanismo unico; `_ref_per_bet_di_mike`.
* `_sorveglia_posizione_di_conto` (~3330): annullo esterno in attesa -> stop; in paper
  `_sorveglia_conto_paper`; RIDOTTA = stop (`come='ridotta'`); `canale_non_confermato` anche per
  la riduzione; registro `_MERCATI_CONTO` (sveglia).
* `_chiuso_dall_utente_mike` (~3500): le conseguenze UNE per tutte le strade (annullo gambe vive,
  `no_reentry`, niente ordini nuovi), `come`/`dove`.
* `_sorveglia_conto_paper` (~3520): la fotografia del blotter paper decide (conferma dichiarata:
  "blotter paper del runner (fonte di verita' del paper)").
* Annullo esterno: `_ESITO_ANNULLATO`, `ESITO_ANNULLATO_DALL_UTENTE`, `_annullato_da_altri`
  (`size_cancelled` meno il taglio del place-and-trim), `_annota_annullo_esterno`,
  `_ferma_per_annullo_esterno`, `_chiudi_gamba_annullata`; punti di lettura:
  `_classifica_ordine` (~2800), `_applica_esito_riapertura` (~2930), `_segui_resting_live`
  (correnti con annullo parziale, ~2700; e la rilettura per bet_id), `_segui_ordini_paper_su_runner`
  (paper, ~1845); lo stop scatta PRIMA della decisione dello stesso giro
  (`_sorveglia_posizione_di_conto` e coda di `_sorveglia_gambe`).
* Dormita (`_dormi_o_sveglia`): con il canale del conto `SorveglianzaConto.dormi(pausa, 1 s)`;
  con la sveglia accesa il conto alza `_SVEGLIA`. `avvia_conto_dal_canale` legge `conto,conto_paper`.
* `_CACHE_DI_PROCESSO` + `_ANNULLI_ESTERNI`, `_MERCATI_CONTO`.

### 2.4 Omega — `Betfair/omega/omega_service.py`, `omega_market.py`
* `_verdetto_di_conto` (estratto, stessa aritmetica + esposizione), `_CONTO`, `_MERCATI_CONTO`,
  `_righe_della_fotografia` (normalizzatore del MODULO `omega_market`), `_segnale_dal_canale`.
* `sorveglia_posizione_di_conto`: segnale PRIMA della cadenza (`_FASE_ESEGUITA_A` timbrato: la
  lettura sostituisce la successiva), RIDOTTA = stop (`_marca_chiuso_dall_utente` + `_chiudi_evento`,
  `come`), `canale_non_confermato`, latenza.
* `_sorveglia_conto_paper` (paper dal blotter), `_gruppi_di_conto(modo=...)`,
  `_puo_essere_vivo/annulla_ordini_vivi_del_bot/_chiudi_evento(modo=...)` +
  `_DA_ANNULLARE_PAPER` (annullo paper SOLO dalla porta del runner, mai REST live).
* `_dormi_o_sveglia`: fette di 1 s interrotte dalla sveglia del conto dopo 1 s; con la sveglia
  accesa il conto alza `_SVEGLIA`. `main` avvia il lettore. `svuota_le_cache` azzera il conto.
* `omega_market.order_state_by_bet_id`: chiavi ADDITIVE `size_cancelled`, `size_lapsed` (correnti)
  e `bet_status`, `size_cancelled` (regolati CANCELLED).

### 2.5 Safe — `Betfair/safe_strategy/bot_service.py`
* `_verdetto_di_conto` (estratto + esposizione), `_CONTO`, `_MERCATI_CONTO`, `_segnale_dal_canale`.
* `_sorveglia_posizione_di_conto`: segnale PRIMA di cadenza e tetto di 2 mercati/ciclo, RIDOTTA =
  stop (marcatore `verdetto='ridotta'`, riga viva regolata da `settle_open`), latenza.
* `_sorveglia_conto_paper` (`come='app_paper'`), riconoscimento per bet_id -> `safe-t<id>` /
  `safe_tennis-t<id>`.
* Sveglia: `_CONTO.su_sveglia(_SVEGLIA.set)`, evento passato all'attesa anche senza la sveglia UI.
* `_avvia_conto_dal_canale`: lettore su 47331 (calcio) E 47332 (tennis) nella stessa memoria.

### 2.6 Il verdetto in ESPOSIZIONE (reperto W2 del coordinatore)
La decisione intera/ridotta/chiusa si prende sulla parte DIREZIONALE (win - lose) degli ordini del
bot contro quelli altrui (`+size*prezzo` back, `-size*prezzo` lay, = `calculate_matched_exposure`
di flumine), la stessa formula `vivo` di sempre; il risultato e' riportato in size equivalente al
prezzo medio del bot. Un green-up dell'utente di un ordine SUO ha direzione ~0: il bot resta
intero. Una chiusura a pari size a un prezzo diverso resta «chiusa». Dati mancanti (abbinato senza
prezzo medio, posizione del bot mista di segno) -> l'aritmetica in size di prima (dichiarato con
`metro`). I due esempi numerici del coordinatore sono test (Mike, Omega, Safe).

### 2.7 Banco (solo additivo)
* `banco_comune.MercatoFlumine.annulla_come_utente(ref)`; `order_state_by_bet_id` del banco con
  `size_cancelled/size_lapsed` (gemello del vero); `pubblica_conto_al_client(..., modo)` (live dallo
  stream con `OrderBookCache` VERA, paper dal blotter del `Market`); `latenza_dal_canale` (controllo
  della latenza al primo giro, come R3-CANALE).
* `certifica.trasporto_dello_scenario`: un trasporto obbligato `canale` vale anche senza
  `--trasporto` (nessuno scenario ne aveva prima).
* Mike: `_pubblica_conto` sulla porta comune; scenari NUOVI `ridotto-fuori-app` (R3-RIDOTTA),
  `annullato-dal-sito` (R3-ANNULLO), `manuale-app-paper` <canale> (R3-CANALE con il blotter paper).
* Omega: scenari NUOVI `chiuso-fuori-app-canale`, `ridotto-fuori-app-canale` (cadenza VERA 120 s,
  sveglia del giro modellata: primo book dopo il pavimento di 1 s; E5-CANALE, E5-RIDOTTA); motore v2
  e banda di `apertura` (l'unico assetto in cui Omega apre su 35760084). La punta dell'utente
  rispetta la regola delle punte .it (multipli di 0,50). I due scenari girano SUBITO DOPO
  `apertura` e PRIMA di `paper` (ordine di `SCENARI_DESCRITTI`): reperto PREESISTENTE del banco,
  con `--worker 1` uno scenario v2 LIVE che segue `paper` nello stesso processo non apre piu'
  (provato su `3b8ce19` intatto: `--scenari paper,apertura` -> `apertura` 0 azioni; da solo o dopo
  `apertura`, `manuale-e-bot`, `bot-fermo`, `cashout-globale`, `chiuso-fuori-app` apre). Nel primo
  giro DOPO (su 3b8ce19) i due scenari, messi in coda, NON erano esercitati e il referto li dava
  OK: ora uno scenario del canale senza posizione si dichiara **NE** (`non_esercitato`), mai OK.
  Il difetto del banco (stato di processo lasciato da `paper`) NON e' corretto qui: va al
  cantiere del banco Omega (C7).
* Safe: scenario NUOVO `chiusura-fuori-app-canale` (T14-CANALE); `chiusura-fuori-app-ridotta` ora
  dichiara l'istante a T14 (la riduzione ferma il bot).

## 3. Test

File nuovi: `Betfair/stream/tests/test_conto_w3a_2026_10_08.py` (14),
`Betfair/mike/tests/test_mike_w3a_consapevolezza_2026_10_08.py` (16),
`Betfair/omega/tests/test_omega_w3a_conto_canale_2026_10_08.py` (14),
`Betfair/safe_strategy/tests/test_safe_w3a_conto_canale_2026_10_08.py` (14).

Test ESISTENTI modificati (ognuno per una decisione esplicita del brief):
* `mike/tests/test_mike_conto_e_sovracopertura_2026_09_16.py::test_la_chiusura_PARZIALE_dellutente_*`
  (ora ferma il bot) e il contratto delle chiavi di `order_state_by_bet_id` (+2 chiavi);
* `mike/tests/test_mike_p4_ordini_2026_09_29.py::test_stesse_chiavi_del_finto_del_banco` (+2 chiavi);
* `mike/tests/test_mike_conto_dal_canale_2026_09_30.py`: i due test degli snap/fotografia
  ripetuta usano ora una riduzione NON confermata dalla REST (la proprieta' provata e' la stessa:
  nessuna REST fuori cadenza sulla stessa fotografia);
* `omega/test_omega_chiuso_dall_utente_2026_09_16.py::test_una_chiusura_PARZIALE_*` (ora ferma);
* `safe_strategy/tests/test_chiusura_dell_utente_2026_09_16.py::test_copertura_solo_parziale_*` (ora ferma).

Esiti (comandi esatti, ambiente cloud, Python 3.13 di sistema):
* Test nuovi: `python3 -m pytest <i 4 file nuovi> -q -p no:cacheprovider` -> **58 passed**.
* Suite intera sulla base FINALE `d0cf8b94` + W3a: `python3 -m pytest Betfair/ -q -p no:cacheprovider`
  -> **4 failed, 11158 passed, 64 skipped, 6 xfailed in 342 s** (`scratchpad/w3a/suite_d0cf8b9.txt`);
  stessi 4 rossi su `16d6c67` (4 failed, 11061 passed) e su `3b8ce19` (4 failed, 11006 passed),
  spiegati qui sotto. `pytest Betfair/safe_strategy Betfair/omega` dopo la correzione NE: 3856 passed.
  Mutazioni rieseguite su `1ac69d0` (= `d0cf8b94` sotto `Betfair/`): 22/22 ROSSE.
  Banco + test nuovi su 16d6c67: `pytest <4 file nuovi> Betfair/stream/backtest
  Betfair/stream/tests/test_banco_mike_ondata2_2026_09_30.py` -> 121 passed.
  I 4 rossi sono TUTTI in `Betfair/stream/tests/test_greenup_fuori_bot_2026_10_08.py` (W2, entrato
  con la cima; sulla copia PRIMA `3b8ce19` intatta: 56 passed) e sono la conseguenza VOLUTA del
  reperto del coordinatore (verdetto in esposizione):
  * `test_mike_ridotta_quando_il_prezzo_e_sceso_il_worker_lo_dice`: asserisce che il verdetto VERO
    di Mike dica «ridotta 9,64» nell'esempio del coordinatore (Mike back 10, sito back 5 @1,50
    coperto LAY 5,36 @1,40): e' esattamente il falso «ridotta» da togliere; ora Mike resta intera.
  * `test_mike_non_viene_mai_dichiarata_chiusa_dalla_copertura`: la coda del test prova che la
    copertura ipotetica farebbe dire «chiusa» a Mike (secondo esempio del coordinatore): ora Mike
    resta intera (il rifiuto del worker resta, prudente ma non piu' necessario).
  * `test_omega_ridotta_la_previsione_del_worker_coincide_col_verdetto_vero`: Omega LAY 5,26 @3, il
    sito LAY 5 @3 coperto BACK 6 @2,5 (direzione dell'utente 0): ora Omega resta intera.
  * `test_contratto_con_i_verdetti_dei_bot`: contratto sul TESTO di
    `OS.sorveglia_posizione_di_conto`/`SS._sorveglia_posizione_di_conto`; la formula del `vivo` e'
    ora (identica) in `OS._verdetto_di_conto`/`SS._verdetto_di_conto` (estratti).
  Primo giro: file di W2 non toccati, proposta di riallineamento consegnata. **Secondo giro**: col
  permesso del coordinatore il riallineamento e' APPLICATO (test ed `effetto_sui_bot`, sez. 10.2)
  e la suite intera e' a 0 rossi (sez. 10.3).
* Prima della fusione con la cima (su `b5547eb` + W3a): 1 failed (il test di tempo
  `test_motore_ordini_2026_09_24.py::test_latenza_logica_comando_place_sotto_20_ms`, modulo non
  toccato, sotto carico; VERDE nel giro sulla cima), 10839 passed, 64 skipped, 6 xfailed.

### Falsificazioni (`AUDIT_2026-10-08/W3A_CONSAPEVOLEZZA_SERVIZI/mutazioni.txt`)
Script `scratchpad/w3a/mutazioni.py` (ripristino dal contenuto salvato, sha confrontato, diff
completo identico prima/dopo, 0 `MUTAZIONE` nei file toccati). 22 mutazioni, 22 ROSSE (la M22
della prima stesura non era raggiungibile - ancora dopo un `return` - ed e' stata sostituita con
una mutazione vera: la sorveglianza che legge la fotografia dell'altro modo; ROSSA).
Rieseguite TUTTE e 22 su `3b8ce19` e di nuovo sulla base finale `16d6c67` (file del referto
sovrascritto dall'ultimo giro): 22/22 ROSSE in entrambi,
sha di ogni file identico prima della mutazione e dopo il ripristino, 0 righe `MUTAZIONE` rimaste,
`git diff --stat` identico prima/dopo (18 file, +2159/-258), dopo il ripristino 58 passed.

| # | Difetto reintrodotto | File | Esito |
|---|---|---|---|
| M1 | verdetto in esposizione spento (torna la size) | esiti_ordini_canale | ROSSO |
| M2 | Mike: la riduzione parziale non ferma | mike/service | ROSSO |
| M3 | Omega: la riduzione parziale non ferma | omega_service | ROSSO |
| M4 | Safe: la riduzione parziale non ferma | safe bot_service | ROSSO |
| M5 | Omega: il canale non salta la cadenza | omega_service | ROSSO |
| M6 | Safe: il canale non salta cadenza e tetto | safe bot_service | ROSSO |
| M7 | Mike: l'annullo esterno torna una scadenza | mike/service | ROSSO |
| M8 | Mike: il taglio del place-and-trim contato come annullo | mike/service | ROSSO |
| M9 | paper accettato sul topic live | esiti_ordini_canale | ROSSO |
| M10 | memoria senza modo (paper e live sulla stessa chiave) | esiti_ordini_canale | ROSSO |
| M11 | sveglia a ogni fotografia (snap compresi) | esiti_ordini_canale | ROSSO |
| M12 | dormita senza pavimento | esiti_ordini_canale | ROSSO |
| M13 | runner paper pubblica anche senza cambi | live_trading_strategy | ROSSO |
| M14 | runner paper non pubblica | live_trading_strategy | ROSSO |
| M15-17 | Mike/Omega/Safe: in paper il conto non si guarda | i tre servizi | ROSSO x3 |
| M18 | ordini del bot non riconosciuti per bet_id in paper | esiti_ordini_canale | ROSSO |
| M19 | Omega: la dormita ignora la sveglia del conto | omega_service | ROSSO |
| M20 | sportello per bet_id senza sizeCancelled (prod) | omega_market | ROSSO |
| M21 | sveglia della Safe non collegata al conto | safe bot_service | ROSSO |
| M22 | la sorveglianza legge la fotografia dell'altro modo | esiti_ordini_canale | ROSSO |

## 4. Replay PRIMA/DOPO (`certifica <bot> <evento> --scenari tutti --worker 1`)
**Base finale `16d6c67`**: per ordine del coordinatore il PRIMA NON lo lancio io: i referti PRIMA
sono quelli delle tre sessioni cloud (`AUDIT_2026-10-08/riferimenti_cloud/` sui rami
`claude/blissful-sagan-hri7o6-rif-{mike,omega,safe}`). Il DOPO: archivio di `16d6c67` + i 22 file del
worktree sovrapposti + registrazioni decompresse in `_live_raw/` (`scratchpad/w3a/dopo16_src`), coda
staccata `scratchpad/w3a/orchestra_dopo.py`, uno alla volta, `--worker 1`.

Giro precedente (superato, tenuto come prova di invarianza): PRIMA da un archivio di `3b8ce19`
(registrazioni decompresse in `_live_raw/`), DOPO = la stessa copia + i 22 file del worktree
(verificato file per file: PRIMA identico a `HEAD:<file>`, DOPO identico al worktree;
`scratchpad/w3a/verifica_copie.py`). Coda unica staccata (`scratchpad/w3a/orchestra.py`), UN replay
alla volta, `--worker 1`; fermata alle 12:40 UTC sull'ordine del coordinatore (completate le coppie
Mike e Omega 35760084).
Macchina con 4 CPU e carico 10-15 (altri cantieri in parallelo, piu' la suite intera per un tratto):
i TEMPI sono gonfiati dal carico. Confronto con `scratchpad/w3a/confronta.py` (escluse le righe di
tempo, memoria, percorsi e comando; ogni altra riga diversa e' elencata e spiegata sotto).

**Terzo ordine del coordinatore (13:50 UTC circa)**: niente piu' replay lunghi nel worktree; il
worktree e' portato alla cima integrata `d0cf8b94` (fra `1ac69d0` e `d0cf8b94` nessun file sotto
`Betfair/` cambia) e il DOPO lo lancia il coordinatore. Le code DOPO su `16d6c67` e `1ac69d0` sono
state FERMATE (la seconda durante Mike 35760084). Quello che e' stato misurato davvero:

| Bot / evento | PRIMA | DOPO | Esito |
|---|---|---|---|
| Mike 35760084 | 3b8ce19: 26 OK (1 NE preesistente `cashout-dopo-copertura`), 2026 s | 3b8ce19+W3a: 29 OK, 1945 s; 16d6c67+W3a: 29 OK, 1251 s | 26 scenari esistenti IDENTICI; 3 NUOVI OK. DOPO 3b8ce19 e DOPO 16d6c67 identici riga per riga |
| Omega 35760084 | 3b8ce19: 20 OK, 534 s | 16d6c67+W3a (con riordino): 22 OK, 436 s | 20 esistenti IDENTICI; 2 NUOVI OK ed ESERCITATI (E5 da `?? x0` a x218: E5 non era MAI sollecitato su Omega) |
| Safe base 35760084 | b5547eb: 22 OK, 1116 s | 16d6c67+W3a: 23 OK, 659 s | 22 esistenti IDENTICI; `chiusura-fuori-app-canale` OK ma NON esercitato (la Safe base non apre su 35760084): con la correzione successiva si dichiara NE |
| Safe base 35797769 | (prova mirata, codice pre-esposizione) | `chiusura-fuori-app`, `-ridotta`, `-canale`: OK, T14 x919 ciascuno, latenza 0 ms | da rifare col codice finale |
| Mike, Omega 35797769; Safe esatto/punta | non misurati col codice finale | | da lanciare (elenco sotto) |

Righe diverse nella CODA (copertura) e spiegazione: i contatori (A1, A3, B2, B4, B5, C1-C3, D1-D3,
E1, L1, L3, J2, J3, R3, S2, K1-K4, M1, RG1 di Mike; A1-A7, B1-B4, E1, E5, J3, J5, F1, K1-K7 di Omega;
B1-B11, E1-E11, P1... della Safe) crescono SOLO per i giri degli scenari NUOVI (es. Mike R3 da x5854 a
x23415 = 4 scenari x ~5854); ESITO cresce del numero di scenari nuovi; la TESTA cambia solo
nell'elenco `SCENARI`. Nessuno scenario esistente ha una riga diversa. Referti e confronti:
`W3A_CONSAPEVOLEZZA_SERVIZI/giro_3b8ce19/` e `giro_16d6c67/`.

Codice dei giri misurati rispetto al finale: identico per Mike e Omega (16d6c67+W3a); per la Safe
il finale aggiunge SOLO la dichiarazione NE dello scenario del canale non esercitato
(`safe_strategy/tools/replay_registrazioni.py::_nota_conto_canale`).

### 4.1 Comandi `certifica` per il DOPO (dal worktree su `d0cf8b94`, registrazioni in `_live_raw/`)
Tutti `--worker 1`, uno per macchina:
```
python -m Betfair.stream.backtest.certifica mike        35760084 --scenari tutti --worker 1
python -m Betfair.stream.backtest.certifica mike        35797769 --scenari tutti --worker 1
python -m Betfair.stream.backtest.certifica omega       35760084 --scenari tutti --worker 1
python -m Betfair.stream.backtest.certifica omega       35797769 --scenari tutti --worker 1
python -m Betfair.stream.backtest.certifica safe_base   35760084 --scenari tutti --worker 1
python -m Betfair.stream.backtest.certifica safe_base   35797769 --scenari tutti --worker 1
python -m Betfair.stream.backtest.certifica safe_esatto 35760084 --scenari tutti --worker 1
python -m Betfair.stream.backtest.certifica safe_esatto 35797769 --scenari tutti --worker 1
python -m Betfair.stream.backtest.certifica safe_punta  35760084 --scenari tutti --worker 1
python -m Betfair.stream.backtest.certifica safe_punta  35797769 --scenari tutti --worker 1
```
(`--data-dir <cartella>/_live_raw` se le registrazioni non sono nel percorso di serie.)
Scenari NUOVI dentro `tutti` (per un controllo mirato veloce, stessi comandi con `--scenari`):
* mike: `ridotto-fuori-app,annullato-dal-sito,manuale-app-paper` (`manuale-app-paper` gira da solo
  sul trasporto `canale`: trasporto obbligato, nessun `--trasporto` serve);
* omega: `chiuso-fuori-app-canale,ridotto-fuori-app-canale` (in `tutti` girano subito dopo
  `apertura`; in un comando mirato NON metterli dopo `paper`, vedi 2.7);
* safe_base/safe_esatto/safe_punta: `chiusura-fuori-app-canale`; scenario ESISTENTE con condotta
  cambiata: `chiusura-fuori-app-ridotta` (la riduzione ora ferma il bot: istante dichiarato a T14).
Atteso: tutti gli esistenti IDENTICI al PRIMA salvo `chiusura-fuori-app-ridotta` della Safe dove apre
(35797769); i nuovi OK, oppure NE con causa dichiarata dove il bot non apre (Safe su 35760084).
Controlli nuovi da guardare: Mike R3-RIDOTTA, R3-ANNULLO, R3-CANALE; Omega E5-CANALE, E5-RIDOTTA;
Safe T14-CANALE.
Un primo giro PRIMA era stato misurato su `b5547eb` (Mike 35760084 26 OK 1949 s, Omega 35760084
20 OK 908 s, Safe base 35760084 22 OK 1116 s): superato da questo, sulla cima nuova.

## 5. Latenze misurate
* Banco (tempo di mercato, primo giro dopo la pubblicazione del canale):
  * Mike 35760084 (`ridotto-fuori-app`, `manuale-app-paper` in paper): dal canale al verdetto
    **1620 ms, tutti di attesa del primo giro del servizio** (nel banco il giro lo danno i book delle
    linee); verdetto al PRIMO giro dopo il messaggio (R3-CANALE verde). `annullato-dal-sito`:
    verdetto `annullata` alla rilettura per bet_id, 0 ordini di Mike dopo l'annullo.
  * Omega 35760084 (`chiuso-fuori-app-canale`, `ridotto-fuori-app-canale`): **0 ms** dal canale al
    verdetto (la sveglia porta il giro subito dopo il pavimento di 1 s; prima: fino a 120 s di
    cadenza REST + dormita del ciclo).
  * Safe 35797769 (prova mirata): **0 ms** (T14-CANALE verde).
* Test con canale VERO (socket locale, test del 30/09 `test_capo_coda...`): dallo stream al
  verdetto < 1000 ms (asserito), invariato.
* Produzione attesa: Mike come il 30/09 (~1-2 s: giro in gioco ~1 s + conferma REST); Omega da
  20-120 s (dormita fino a 60 s + REST ogni 120 s) a circa 1-2 s (sveglia dopo il pavimento di 1 s +
  2 letture REST); Safe da fino a 30 s (+ tetto 2 mercati) a ~2 s (giro) + REST. In paper: la
  fotografia arriva al primo giro (nessuna REST).

## 6. Parita' paper/live
* LIVE: cambia QUANDO si rilegge la REST (subito su segnale) e che la riduzione/l'annullo esterno
  fermano il bot; la decisione resta della REST (mai dal solo canale).
* PAPER: prima nessun intervento esterno era visto; ora l'ordine manuale dell'app sul runner paper
  ferma il bot come il sito in live. Fonte di verita' dichiarata: il blotter della strategia paper
  del runner (contiene ogni ordine paper dalla sua partenza); un runner riavviato ha il blotter
  vuoto -> gambe non ritrovate -> nessuna decisione (conservativo, come il live). Paper e live:
  topic diversi, memoria per (modo, mercato), filtro del client sul `modo`, consumatori per modo
  (test e mutazioni M9, M10, M22).

### 6.1 La fonte gemella del paper (per W3b: interfaccia, topic, chiavi)
* **Produttore**: `LiveTradingStrategy` in `mode == "paper"` (`Betfair/stream/engine/live_trading_strategy.py`,
  `process_orders` -> `_pubblica_conto_paper(market)`): a ogni giro degli ordini, per ogni mercato,
  prende `blotter.strategy_orders(strategy)` filtrati sul mercato (ordini dei bot E manuali dell'app),
  calcola una firma (`_order_signature` per ordine) e pubblica SOLO se cambia (cache
  `_conto_paper_sig`, tetto 2000 mercati). Mai solleva.
* **Funzioni** (`Betfair/stream/esiti_ordini_canale.py`):
  `pubblica_conto_paper(market_id, ordini_flumine, pubblica, *, adesso_ms=None) -> bool`
  (chiama `pubblica("conto_paper", payload)`), `payload_conto_paper(market_id, ordini, *, ricevuto_ms)`,
  `ordine_paper_del_conto(ordine_flumine) -> dict | None` (None senza `bet_id`).
* **Topic**: `conto_paper` (`TOPIC_CONTO_PAPER`), sul canale locale del runner (47331 calcio,
  47332 tennis); lettore: `ws://127.0.0.1:<porta>/lettore/conto,conto_paper`
  (`PERCORSO_CONTO_TUTTI`). Il topic live `conto` resta com'era (+ chiave additiva `modo: "live"`).
* **Payload** (un mercato per messaggio):
  `{"market_id": str, "ordini": [riga...], "fonte": "blotter_paper", "modo": "paper",
  "ricevuto_ms": int, "pnl_letto_at": ISO-ms "Z", "publish_time_ms": int (= ricevuto_ms), "snap": False}`.
* **Riga** (grafia `listCurrentOrders`, le STESSE chiavi del topic live): `betId` (str), `marketId`,
  `selectionId` (int), `handicap`, `side` ("BACK"/"LAY"), `status` ("EXECUTABLE" se lo stato flumine e'
  PENDING/EXECUTABLE/CANCELLING/UPDATING/REPLACING e `sizeRemaining` > 0, altrimenti
  "EXECUTION_COMPLETE"), `orderType` ("LIMIT"), `persistenceType`, `sizeMatched`, `sizeRemaining`,
  `sizeCancelled`, `sizeLapsed`, `sizeVoided` (float a 2 decimali), `averagePriceMatched` (float > 0 o
  None), `customerOrderRef` (il ref dato dal runner, `awlq<id>`, da `context/notes["customer_order_ref"]`),
  `customerStrategyRef` (None), `placedDate` (ISO "Z" o None), `matchedDate` (None),
  `priceSize` (`{"price", "size"}`).
* **Consumatore**: `MemoriaConto.ricevi(payload)` (chiave `paper|<market_id>`, la live resta il
  market_id nudo; un client sul topic `conto_paper` scarta un payload senza `modo: "paper"`);
  `SorveglianzaConto.fotografie(chiave, market_ids, modo="paper")`. Il bot riconosce i SUOI ordini per
  `bet_id` (`con_ref_del_bot(righe, ref_per_bet)`), tutto il resto e' «altrui».
* **In-process** (come la prova di W3b): basta chiamare
  `pubblica_conto_paper(market_id, ordini, lambda _t, p: memoria.ricevi(p))` con gli ordini flumine
  della strategia paper; il banco lo fa con `banco_comune.pubblica_conto_al_client(..., modo="paper")`.

## 7. Cosa NON ho fatto / NON ho potuto verificare
* **Omega e Safe: annullo dal sito di un ordine IN ATTESA non distinto** (Mike si'): oggi un ordine
  pendente annullato dall'esterno e' letto come «non abbinato» (`_flumine_no_fill_error`) e il budget
  dei tentativi puo' ri-piazzarlo. Non toccato: e' la logica di ripiazzamento di Omega/Safe, va
  progettato con l'utente (la lettura `size_cancelled` per bet_id ora c'e' in `omega_market`).
* **Banco paper di Omega e Safe**: non aggiunto. Safe paper sul trasporto canale e' KO K7 GIA' su
  `b5547eb` (`certifica safe_base 35797769 --scenari paper --trasporto canale`: K7 x3424, difetto
  preesistente, non mio): lo scenario Safe `manuale-app-paper` l'ho scritto e poi TOLTO per non
  mescolare un KO preesistente. Il paper di Omega/Safe e' coperto dai test di unita' (M16, M17).
* **Omega `chiuso-fuori-app` (lo scenario vecchio) non e' mai esercitato su 35760084** (il v3 non
  apre): reperto preesistente. I miei scenari Omega usano il motore v2 + banda di apertura.
* **Safe base non apre su 35760084**: gli scenari fuori-app vi restano non esercitati; esercitati su
  35797769.
* **Tennis**: registrazioni tennis assenti nel cloud -> Safe tennis solo test (lettore su 47332).
* **Frontend**: il nuovo `meta.esito_ordine = "annullato_dall_utente"` (Mike, riga `status='error'`,
  `reason='annullato_dall_utente'`) non ha etichetta in UI (fuori perimetro):
  `frontend/src/lib/mike.ts` `MIKE_ESITO_ORDINE_LABEL` -> `null` e `tradeStatus.ts:~287`
  («esito nuovo, non conosciuto: fail-closed») -> la pagina resta col testo generico della riga
  in errore, nessun esito inventato. Va aggiunta l'etichetta («annullato dall'utente») dal cantiere UI.
* ~~W2 da riallineare~~: FATTO nel secondo giro (sez. 10.2).
* **Live vero**: nessuna verifica con Betfair (vietata): le latenze di produzione sono stime.
* ~~Ordini di un altro bot contati come «altrui»~~: CHIUSO nel secondo giro (sez. 10.1).
* Il fermo per DB illeggibile vale per la PARTITA, non per la sola selezione (piu' prudente).
* Mike in PAPER: la selezione in verifica si rigiudica a ogni giro (fotografia del blotter); non
  c'e' un test dedicato del ritorno dal paper (c'e' quello del live).
* Test flaky di tempo `test_motore_ordini_2026_09_24.py::test_latenza_logica_comando_place_sotto_20_ms`
  (modulo non toccato) puo' fallire sotto carico.

## 8. Decisioni per l'utente
1. **Riduzione parziale = stop** (ordine dell'08/10) sostituisce la regola R10 del 16/09
   (proteggere il residuo). Applicata ai tre bot; tre test del 16/09 riscritti di conseguenza.
   Confermare.
2. ~~Ordini di un altro bot~~: decisa dal coordinatore e fatta (sez. 10.1). Resta da confermare:
   con il DB illeggibile il fermo vale per l'INTERA partita del bot (anche le chiusure
   protettive aspettano fino a 30 s per ogni ritentativo), non per la sola selezione.
3. **Metro in esposizione** (reperto W2): il green-up dell'utente dei SUOI ordini non ferma il bot;
   se i dati mancano (prezzo medio assente, posizione mista) si torna alla size (dichiarato con
   `metro`). W2 riallineato sulla stessa funzione (sez. 10.2). Una copertura del worker che fa dire
   «ridotta» a un bot ora lo FERMA (riduzione = stop): il worker la piazza e lo dichiara. Va
   rifiutata anche quella?
4. **Verita' del paper = blotter del runner paper** (nessuna REST in paper). Un runner paper
   riavviato perde il blotter -> nessuna decisione (conservativo). Confermare.
5. **Annullo esterno in Omega/Safe** (ordine in attesa): progettare se deve fermare il bot come in
   Mike (oggi puo' essere ri-piazzato).
6. **Safe paper sul canale (K7 preesistente)**: aprire un cantiere a parte.

## 9. Da controllare dal vivo al prossimo avvio
* Log runner calcio: `[conto-ws] ... (topic conto)` (live, invariato) e, in paper, messaggi
  `conto_paper` (nessun log per messaggio: vedere `local_channel.statistiche`).
* Log Mike/Omega/Safe all'avvio: `posizione di conto dallo stream ordini del runner:
  ws://127.0.0.1:47331/lettore/conto,conto_paper` (Safe anche 47332).
* Intervento manuale dall'app in PROVA su una partita di un bot: attivita' `chiuso_dall_utente`
  con `dove = "dall'app (ordine manuale sul runner paper)"` e `latenza_ms.dal_runner` ~1-2 s; in
  live dal sito `dove = "fuori dall'app (stream ordini)"`.
* Un green-up dell'utente di un ordine SUO sulla selezione di un bot: NESSUN `chiuso_dall_utente`.

## 10. Secondo giro (revisione del coordinatore, 08/10 sera)
Base: worktree portato a `31fa6433` (cima integrata; da `d0cf8b94` cambia solo un documento),
stash con etichetta `w3a-agent-ada08-merge-31fa6433` applicato per SHA, nessun conflitto. Niente
commit. Nessun replay lungo (ordine del coordinatore): solo tre controlli mirati, sotto.

### 10.1 L'ordine di un ALTRO bot non e' dell'utente (decisione n.2 chiusa)
* Classificazione = quella di W2, nessuna regola nuova:
  1. riferimenti dell'ordine (`motivo_bot_da_riferimenti`: `customerStrategyRef` diverso da
     assente/'live', `customerOrderRef` con il prefisso di un bot), senza DB;
  2. poi il DB, SOLO per i bet_id mai visti: `esposizione_fuori_bot.proprietari_bot(sb, bet_ids,
     mode=...)`, cioe' tabelle dei bot, specchio e riga della coda del runner (`motivo_bot_da_coda`).
     La lettura e' stata SPOSTATA dal worker in `esposizione_fuori_bot` (una funzione, col `modo`
     live/paper). `live_order_worker._proprietari_bot(sb, ids)` ora la chiama soltanto: firma
     invariata, quindi W3b, che la usa, non cambia.
* Ogni bot la legge con `db.proprietari_bot_conto(bet_ids, modo)`, aggiunta identica in
  `mike/db.py`, `omega/omega_db.py` e `safe_strategy/bot_db.py`. La memoria e' per (modo, bet_id)
  (`esiti_ordini_canale.ProprietariConto`, dentro `SorveglianzaConto.separa_altrui`): una lettura
  per bet_id nuovo, nel giro della sorveglianza del conto e mai nel piazzamento. Gli ordini senza
  abbinato non si classificano, perche' non spostano il verdetto.
* Nel verdetto (Mike, Omega e Safe `_verdetto_di_conto`) gli ordini degli altri bot si TOLGONO sia
  dagli «altrui» sia dal netto di conto, e il dettaglio lo dice (`ordini_di_altri_bot`).
* DB illeggibile:
  - l'ordine resta IGNOTO e la selezione va IN VERIFICA, senza nessun verdetto «chiuso dall'utente»;
  - la cosa si scrive UNA volta (Mike e Safe `posizione_di_conto` con `verdetto='in_verifica'`,
    Omega `diagnosi`: kind gia' dichiarati in UI) e alla fine si scrive `verificato`;
  - la lettura del DB si ritenta dopo `RIPROVA_PROPRIETARI_S` = 30 s.
* Nessun ordine nuovo sulla partita finche' la verifica dura:
  - Mike: `_ferma_piazzamenti_in_verifica` toglie i piazzamenti dalla decisione (restano gli
    annulli, lo stato non avanza) e la differita aspetta;
  - Omega: niente aperture (`scan_and_place_legs`, e il motore v1) e niente green-up o proposte
    (`_greenup_candidates`); il gruppo si rilegge ogni 30 s invece dei 120 s della cadenza;
  - Safe: niente apertura (prima della riserva) e niente uscite o gambe di combo. Il collo di
    bottiglia `_execute` rifiuta con `conto_in_verifica` SENZA consumare tentativi (la stessa regola
    del runner non raggiungibile).
* Granularita': il fermo vale per la PARTITA, non per la sola selezione. E' piu' prudente di quanto
  chiesto (vedi decisioni).
* Altre modifiche additive:
  - `omega_market._riga_corrente` porta `customer_strategy_ref` (anche il finto del banco, a `None`);
  - `DbMemoria.proprietari_bot_conto` del banco torna `{}` (nel replay gira un solo bot) e lo
    dichiara come «NON ESERCITABILE», come gia' fa `proprietari_bet`.

### 10.2 W2 riallineato (permesso del coordinatore)
* La regola e' UNA: `esiti_ordini_canale.verdetto_posizione` (parte direzionale, poi la size se i
  dati mancano). La chiamano i tre bot e la chiama `esposizione_fuori_bot.effetto_sui_bot`, la cui
  firma nuova e' `effetto_sui_bot(ordini_bot, ordini_fuori, copertura)` con
  `riga_copertura(side, size, price)`. Il worker (`_do_greenup_fuori_bot`) passa gli ordini di
  ciascun bot e i soli ordini fuori bot, come fanno i bot.
* Effetto:
  - le coperture che i bot accettano non si rifiutano piu'. Il caso di W2, Mike back 2 con il sito
    back 10 @5 coperto LAY 33,33 @1,50, ora si piazza e Mike resta intero;
  - si rifiuta ancora quella che chiuderebbe un bot: la posizione dell'utente sull'ALTRO esito del
    mercato a due esiti, coperta sulla selezione del bot (test nuovo
    `test_il_worker_rifiuta_ancora_la_copertura_che_chiuderebbe_mike`).
* `test_greenup_fuori_bot_2026_10_08.py`: 4 test riallineati e rinominati (le previsioni «ridotta» e
  «chiusa» in size erano il falso del reperto), il contratto dei verdetti riscritto su
  `verdetto_posizione`, `test_effetto_sui_bot` riscritto con gli ordini veri e 2 test nuovi (la spia
  «una sola funzione» e il rifiuto che resta).
* Nota per l'utente: con la riduzione = stop, una copertura che fa dire «ridotta» a un bot lo FERMA.
  Il worker oggi la DICHIARA nell'esito e la piazza; rifiuta solo la «chiusa» (regola W2 invariata).

### 10.3 Test e falsificazioni (seconda tappa)
* Suite intera `python3 -m pytest Betfair/ -q -p no:cacheprovider` su `31fa6433` + W3a: **11183
  passed, 64 skipped, 6 xfailed, 0 failed** in 333 s (`scratchpad/w3a/suite_31fa_g2.txt`).
* Test nuovi (in coda ai miei 4 file): conto 21, Mike 21, Omega 17, Safe 18, cioe' 77, tutti verdi.
  Quelli chiesti dal coordinatore:
  - ordine di Omega sulla selezione di Mike -> Mike non si ferma (per riferimenti, nessuna lettura
    del DB);
  - ordine dalla coda del runner di un altro bot -> lo dice il DB, Mike continua, una sola lettura;
  - ordine manuale dell'app -> Mike si ferma;
  - DB giu' -> nessun verdetto, selezione in verifica, la decisione perde i piazzamenti, poi al
    ritorno del DB il verdetto (stessi casi per Omega e Safe, con i loro cancelli).
* Mutazioni: 15/15 ROSSE (`W3A_CONSAPEVOLEZZA_SERVIZI/mutazioni_seconda_tappa.txt`: N1-N15, fra cui
  riferimenti ignorati, DB bot letto come utente, DB giu' come utente, verifica ignorata da ogni bot,
  cancelli tolti, il rifiuto Safe che consuma tentativi, `effetto_sui_bot` di nuovo in size, il `modo`
  ignorato nella lettura del DB, il worker che non rifiuta piu' la «chiusa»). Le 22 della prima tappa
  sono state rieseguite: 22/22 ROSSE. Per M5 e M6 il testo e' stato aggiornato al codice nuovo.
  `git diff` identico prima e dopo, 0 `MUTAZIONE` nel diff.

### 10.4 Replay: controlli mirati (dal worktree, `--worker 1`) e comandi per il DOPO
* Mike 35760084, `chiuso-fuori-app,ridotto-fuori-app,annullato-dal-sito,manuale-app-paper`: 4 OK.
  Verdetti e latenze sono identici al giro su 16d6c67 (2707/1620/1620 ms). L'unica riga nuova e' la
  nota «NON ESERCITABILE: proprietari_bot_conto» negli scenari con ordini dell'utente.
* Omega 35760084, `apertura,chiuso-fuori-app-canale,ridotto-fuori-app-canale`: 3 OK, E5 x218,
  latenza 0 ms (identici).
* Safe base 35797769, `chiusura-fuori-app,chiusura-fuori-app-ridotta,chiusura-fuori-app-canale`:
  3 OK, T14 x919 ciascuno (x2757 in tutto), canale `chiusa` con latenza 0 ms (265 s).
* Comandi del DOPO: quelli della 4.1, invariati (stesso elenco, stessi scenari nuovi). Righe
  diverse attese rispetto al PRIMA, oltre a quelle della 4.1: la nota «NON ESERCITABILE:
  proprietari_bot_conto» in ogni scenario in cui, alla lettura del conto, un ordine abbinato che
  non e' del bot sta sulla sua selezione (chiuso/ridotto fuori app, manuale-app-paper, i
  chiusura-fuori-app* della Safe, gli scenari del canale di Omega). Nient'altro deve cambiare.
* Il difetto del banco Omega «`paper` prima di `apertura`» e' corretto dal cantiere 7 (RB-5),
  secondo il coordinatore. Il mio riordino (i due scenari del canale subito dopo `apertura`) resta
  innocuo: lo si puo' togliere quando C7 e' integrato.

## Blocco per la cronostoria
```
### W3a - consapevolezza degli ordini esterni: Mike, Omega, Safe (08/10, delegato Opus)
- Worktree .claude/worktrees/agent-ada08f62b75e0e29a, base 31fa6433 (cima blissful-sagan-hri7o6),
  NON committato. 24 file modificati + 4 file di test nuovi (77 test). Referto:
  AUDIT_2026-10-08/W3A_CONSAPEVOLEZZA_SERVIZI.md (+ cartella con referti PRIMA/DOPO e confronti).
- Secondo giro: l'ordine di un ALTRO bot non e' dell'utente (classificazione W2: riferimenti, poi DB
  per i bet_id nuovi, in memoria); DB illeggibile -> partita in verifica, nessun verdetto e nessun
  ordine nuovo. W2 riallineato: effetto_sui_bot usa la funzione dei bot (verdetto_posizione).
  Suite 11183 passed / 0 failed; mutazioni 15/15 + 22/22 ROSSE.
- Meccanismo UNICO estratto da Mike 30/09: esiti_ordini_canale.SorveglianzaConto + MemoriaConto
  per (modo, mercato) + sveglia del ciclo; Omega e Safe lo usano (segnale -> REST subito ->
  verdetto); paper: il runner paper pubblica la fotografia del blotter sul topic `conto_paper`.
- Verdetto di conto in ESPOSIZIONE (reperto W2): green-up dell'utente dei SUOI ordini non tocca
  il bot. Riduzione parziale dall'esterno = STOP (sostituisce R10 16/09). Mike: appoggiata
  annullata dal sito = stop (esito nuovo `annullato_dall_utente`), mai ri-appoggiata.
- Primo giro: 4 rossi VOLUTI nel test W2 (asseriva il falso «ridotta/chiusa» in size): riallineati
  nel secondo giro su permesso del coordinatore.
- Aperti: annullo esterno di ordini in attesa in Omega/Safe; Safe paper su canale K7 preesistente;
  mappa UI dell'esito `annullato_dall_utente`; tennis senza registrazioni (solo test).
- Ripresa: il coordinatore rilegge il diff, rilancia suite e `certifica` (vedi sez. 4), decide
  sulle 6 decisioni della sez. 8, poi commit dal worktree.
```

## Verifica del coordinatore cloud (08/10)
- Diff riletto (meccanismo unico `esiti_ordini_canale`: SorveglianzaConto, ProprietariConto, `verdetto_posizione`, topic
  `conto_paper` pubblicato dal runner paper; Mike/Omega/Safe agganciati; classificazione «del bot / fuori bot» di W2; verdetto in
  ESPOSIZIONE; banco solo additivo). Strategie non toccate (soglie, stake, tetti, gambe).
- Test W3a nel checkout integrato verdi; suite complete sulla `b4d91ed` in cloud (`suite_cloud_b4d91ed/`): vitest 5447, tsc 0,
  build ok, pytest tools 17/17, pytest Betfair 11247 verdi e 1 rosso NON deterministico
  (`test_auto_follow_rifiuto_betfair_rientra_e_dichiara`) = difetto vero dei frammenti di mercato, CORRETTO in `71e56de`
  (id() riciclato). Suite Betfair completa sulla cima `66fee096` (W3a + correzione + lavoro del PC): **11273 passed, 0 failed**.
- REPLAY DOPO su due macchine cloud separate (`W3A_DOPO_CLOUD/`, `--scenari tutti`, 10 referti): **0 KO, 0 violazioni**.
  Mike 29 scenari (3 nuovi OK su entrambe), Omega 22 (35760084 `apertura`/`paper` 467/2 IDENTICI al cantiere 7; i 2 nuovi
  `*-canale` OK su 35760084, NE con causa su 35797769 dove Omega non apre), Safe base/esatto/punta 23 (nuovo `-canale` OK su
  35797769; `chiusura-fuori-app-ridotta` ora FERMA il bot = regola «riduzione = stop», T14 x919 conforme).
- DUE DIFFERENZE NON ATTESE, INDAGATE DI PERSONA (sonde in sola lettura in `W3A_DOPO_CLOUD/verifica_coordinatore/`):
  1. Mike 35797769: la voce `posizione_di_conto` (x95-x319 per scenario) sparisce in 17 scenari esistenti, righe di esito identiche.
     CAUSA (rigiocato `base` sul PRIMA `1ac69d0` e sul DOPO con la sonda): nel PRIMA erano 284 avvisi CRITICAL FALSI
     «ridotta_dall_utente» (atteso 10, netto di conto 9,86, «altrui» -0,14) prodotti dagli ordini del CICLO PRECEDENTE di Mike
     stesso (`mike-t1` punta 10 @1,46 e `mike-t2` banca 10,14 @1,44: un green-up gia' chiuso) che non stanno fra i ref della gamba
     corrente. Nel DOPO `separa_altrui` li riconosce come ordini di bot (ref `mike-`) e li toglie: verdetto «intera», 0 voci.
     E' una CORREZIONE: col PRIMA e la regola nuova «riduzione = stop» Mike si sarebbe fermato da solo a ogni rientro.
  2. Safe 35797769 (tre bot): la nota «metodi ASSENTI dal banco: save_event_model» / «NON ESERCITABILE get_event» passa da
     `chiusura-abbinata-in-parte` a `manuale-e-bot`, esiti identici. CAUSA: `omega_service._LAMBDA_CACHE` (usata dalla Safe) ha un
     TTL di 900 s di orologio di PARETE e il banco della Safe non la azzera fra scenari: scade nello scenario che gira a ~900 s di
     orologio, e il DOPO girava piu' lento (4 processi su 4 CPU: 2409 s contro 1422 s). Artefatto del banco, non di W3a, non
     cambia decisioni; reperto per il banco (§ D-13 del documento di verifica): stesso rimedio di RB-5 di Omega.
- W3a CERTIFICATO. Decisioni per l'utente: §8 (1, 2, 3, 4, 5, 6).
