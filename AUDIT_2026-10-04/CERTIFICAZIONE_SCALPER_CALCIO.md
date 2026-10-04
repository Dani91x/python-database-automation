# CERTIFICAZIONE SCALPER CALCIO — 04/10/2026 (delegato, ramo del worktree agent-a8a111b7f6a26f75e, base master e578802)

VERDETTO: **NON CERTIFICATO.** Causa trovata e provata; la correzione completa richiede una
DECISIONE DI STRATEGIA dell'utente (residui di chiusura sotto 0,50 su .it). Mi sono fermato come
da brief. Nessun codice di produzione cambiato nel ramo: la correzione parziale provata e' solo
in patch (`SCALPER_CALCIO_FIX1_SOTTO_050_NON_INTEGRARE.patch`).

## 1. Causa

### 1.1 Il commit
Bisezione col replay `certifica scalper_calcio 35797769 --scenari base --worker 1` (2 passi mirati,
~50 s l'uno, alberi estratti con `git archive` in `_bis/`, non committati):

| codice | esito | azioni |
|---|---|---|
| ff555fb (29/09, ultimo referto OK: `AUDIT_2026-09-28/replay/cantiere_s4/`) | OK | 43 |
| e255676 (padre di 09072ca) | OK | 43 |
| **09072ca** (02/10 14:11, «fix(mike): chiusura della copertura...») | **KO 7** | 538 |
| e578802 (oggi) | KO 7 | 538 |

`09072ca` NON tocca lo scalper (`scalper_bot.py` e `sniper_bot.py` identici fra ff555fb e
e578802, `git diff --stat` vuoto): introduce `Betfair/stream/backtest/minimi_banco.py`, che fa
RIFIUTARE all'exchange simulato del banco (`INVALID_BET_SIZE`) gli ordini sotto i minimi .it:
diretti < 1,00 e ordini nuovi di un replace (place-and-trim) < 0,50.

### 1.2 Banco o bot? -> difetto del BOT, rivelato da un banco diventato fedele
Le 7 violazioni (sonda `AUDIT_2026-10-04/replay/scalper_calcio_base_sonda_7_violazioni.txt`):

| # | controllo | ora (UTC) | slot / ordine |
|---|---|---|---|
| 1 | K1 | 17:00:33 | ('1.259819674', 22) LOCKING segue BACK 0,30 @1,65 (sostituto del place-and-trim) che a mercato non esiste |
| 2 | K1 | 17:27:15 | ('1.259819682', 47973) LOCKING segue LAY 0,14 @1,84 inesistente |
| 3 | K5 | 17:27:53 | 47973 IDLE con esposizione 0,25 (resto del LAY 0,14 rifiutato, dimenticato al reset del ciclo) |
| 4 | K1 | 17:28:00 | ('1.259819674', 58805) LOCKING segue LAY 0,11 @4,1 inesistente |
| 5 | K1 | 17:37:04 | 47973 FLATTENING segue BACK 0,19 @1,81 inesistente |
| 6 | K5 | 17:39:17 | 22 IDLE con esposizione 0,49 (due resti BACK 0,30 rifiutati) |
| 7 | B2 | 19:00:37 (in gioco) | 22 ancora 0,49 al fischio |

Gli 11 rifiutati del banco: 10 sostituti di place-and-trim fra 0,11 e 0,30 (BACK e LAY) e 1 LAY
diretta 0,50 @4,1. Le uscite esatte dello scalper (`_place_exact`) spezzano la chiusura in parte
diretta (multipli di 0,50) + RESTO via park-trim-replace; per un resto < 0,50 Betfair .it rifiuta il
rimpiazzo: MISURATO sul conto il 13/09 (CRONOSTORIA ~1012-1040: «BACK 0,33 ... cambio quota ->
CANCELLED_NOT_PLACED:INVALID_BET_SIZE»; «LAY 0,33 ... cambio quota -> INVALID_BET_SIZE»). La
macchina `advance_submin` passa a DONE («ordine sotto-minimo a riposo») senza verificare che il
sostituto esista: il bot segue un ordine fantasma (K1, consapevolezza: catalogo §7 punti 2/4) e il
resto resta scoperto, poi dimenticato al reset del ciclo (K5, B2). Il 29/09 era OK solo perche' il
banco abbinava quei sostituti (banco ottimista, catalogo §7.8/13). La regola unica del 01-02/10
(`trading/submin.verifica_importo_finale`: importo finale >= 0,50, sotto si dichiara) la chiamano
tutti gli ingressi reali TRANNE lo scalper/sniper, che costruiscono `SubminState` a mano.
Condotta in live = stessa del replay: money-critical (resti fino a 0,49 a mercato senza padrone,
anche al fischio).

`2c5df69` (replay veloce, solo `banco_comune.py`) e' POSTERIORE a 09072ca: il KO c'e' gia' su
09072ca, quindi non e' la causa. Il suo confronto riga per riga sullo scalper NON l'ho fatto.

## 2. Stato su master e578802: tutti gli scenari del registro (15) KO
Referto `AUDIT_2026-10-04/replay/scalper_calcio_tutti_HEAD_e578802.txt` (`--scenari tutti --worker 1`):
base, paper, esiti-ignoti, rifiuti-betfair, sniper, sniper-paper, sniper-uscite-auto, auto-live:
B2x1 K1x4 K5x2 (538 azioni, identici fra loro); senza-missione B2 K1x7 K5x4; bot-fermo e
kill-switch K1x4 K5x2; riavvio B1x14 B2 K1x6 K5x6 S7x1; chiusura-abbinata-in-parte B2 CP1 CP4x2 K1x2
K5; uscite-manuali K1x1; uscite-manuali-firmate B2 K1x12 K5x5 UF2x21. 29/09 (S4): base/paper 43
azioni OK, uscite-manuali 242 OK, firmate 72 OK. Sullo sniper: 538 azioni come base, lo sniper su
questa registrazione non opera (debito noto del 29/09).
**TEMPO: 28m24s (1704 s) su 15 replay, riga LENTO** (tetto 600 s): i 5 scenari con sniper costano
225-272 s l'uno. Difetto del banco gia' noto (29/09: «--worker 1 scalper 17 minuti»), da profilare.

## 3. Correzione tentata (NON integrata, in patch)
`_place_exact` (scalper): un resto < `SUBMIN_IMPORTO_FINALE_MIN` (0,50) non avvia il place-and-trim
(stesso verdetto del motore): `min_bet_skip` + UNA riga CRITICAL `sotto_minimo_non_piazzabile` per
episodio (msg con `SOTTO_MINIMO_NON_PIAZZABILE`); `_resto_davvero_non_piazzabile` coerente (soglia
0,50 invece di 0,05). Nessuna soglia/stake/tempo di strategia toccato.
Test nuovi (nella patch, 11 casi, bot VERO su Flumine VERO con la regola `minimi_banco` montata):
11 verdi. Falsificazione: M1 soglia tolta 8 rossi; M2 ultima spiaggia a 0,05 7; M3 CRITICAL a ogni
giro 6; M4 soglia 0,30 6; M5 niente CRITICAL 8; M6 `<=` (0,50 escluso) 2. Ripristino verificato
(grep MUTAZIONE 0, diffstat uguale).
PERCHE' NON BASTA:
1. 22 test esistenti diventano rossi (`test_cantiere_s_scalper_ko` 16, `s3` 2, `s4` 2 + param.):
   asseriscono la chiusura ESATTA al centesimo via rimpiazzi < 0,50, impossibile su .it (il loro
   exchange simulato non ha minimi). Con la patch il resto e' dichiarato ma DIMENTICATO al reset
   del ciclo -> K5 nei loro invarianti. Non li ho indeboliti.
2. Il replay base con la patch NON termina: avviato 19:04, alle 19:40 ancora vivo, processo
   PID 33476 (figlio 16048) a 5,3 GB e oltre 2100 s di CPU (contro 52 s su master). Ipotesi non
   verificata: con i resti dichiarati lo slot entra in un giro di riflatten/divergenze che emette
   eventi a ogni book e il banco accumula. NON HO POTUTO fermarlo (arresto del processo negato dal
   sistema di permessi) ne' sondarlo (2,9 GB liberi, un'altra sessione con replay Mike accesi).
   **AZIONE PER TE: terminare i PID 33476 e 16048** (sono il mio replay, `certifica scalper_calcio
   35797769 --scenari base`, cwd del worktree). Sonda pronta: `_bis/sonda_loop.py` (esce al
   3000-esimo `min_bet_skip` stampando gli slot).

## 4. Decisione per l'utente (residui sotto 0,50 su .it) — serve PRIMA di certificare
Con i minimi veri un resto di chiusura < 0,50 NON si chiude via API (punta: solo multipli di 0,50;
replace < 0,50 rifiutato). Il bot oggi ne crea a ogni flatten che attraversa ticks. Alternative:
- A. Ricordarlo e dichiararlo (nessun ordine in piu'): la selezione porta il residuo dichiarato oltre
  il reset del ciclo, CRITICAL + proposta, lo chiude l'utente (coerente con la decisione 15 del
  02/10 «chiudo io quando serve»); il controllo K5/B2 conta la tolleranza dichiarata.
- B. Portarlo nel ciclo dopo: la chiusura del ciclo successivo include il residuo (spesso torna
  sopra 0,50 e si chiude esatta). Cambia le size delle chiusure.
- C. Fermare la selezione finche' c'e' un residuo (meno cicli).
- D. Arrotondare la chiusura al multiplo di 0,50 superiore: VIETATO dalla condizione 10 (mai gonfiare).
Proposta mia: A (zero ordini diversi), con la sonda del punto 3.2 prima di integrare.
Lo stesso schema e' nello sniper (`sniper_bot._place_exact`, identico): stessa decisione.

## 5. Mappa: auto-mode in SOLDI VERI (letta nel codice, non provata dal vivo)
- Interruttore `scalper_service_control` (status running, mode live) scritto dalla UI con
  `scalper_auto_activate(p_mode)`; a ogni avvio NUOVO dell'app `avvio_app.ferma_al_nuovo_avvio` lo
  rimette `stopped`/`paper` (scalper_service.py:382-397) e `controllo_avvio` (:250) ferma le righe
  sessione di un avvio precedente: nessun live ereditato.
- Giro (3 s, armamento ogni AUTO_GIRO_S): partite dal feed `safe_strategy_scan` con scanner vivo
  (<=30 s), tetto sessioni `auto_max_partite` (default 2, max 4, conta TUTTE le sessioni con
  processo), mai con freno o guardia d'avvio, mai con una sessione viva nella modalita' opposta.
  Ogni sessione nasce `dry_run = (mode != 'live')` (:489) -> in soldi veri processo con login
  proprio e client flumine `paper_trade=False` (`_order_client_kwargs`): ORDINI VERI su tutte le
  partite armate.
- In sessione: `event_loss_cap` 1,5 (1,0 in ht_mode) -> force-flat totale; flatten a KO-180 s,
  stop ingressi a KO-420 s; tetto esposizione `stake x (price_max-1) x 2`; stop UI (stopping) /
  kill-switch (file STOP_SCALPER, arresto ordinato, `controls.motivo_kill_switch` env+DB) ->
  force-flat e fine; partita uscita dal feed 60 s -> stopping; interruttore spento -> stop delle
  sole sessioni auto.
- **BUCO (da portare all'utente, NON bloccante per la regola «senza gesto»)**: lo scalper NON legge
  «Ordini reali» (`betfair_live_settings.order_mode` / tetto `LIVE_ORDER_MODE`, regola di
  `modo_ordini`, `execution._live_brake`): con «Ordini reali» in PROVA e l'interruttore scalper in
  soldi veri partono ordini veri. E' lo stesso difetto chiuso oggi per Omega (A). Un gesto
  dell'utente in questo avvio c'e' sempre (interruttore scalper o scheda con conferma), quindi non
  ho trovato una strada di soldi veri SENZA gesto; ma «soldi veri solo quando lo scelgo io» con UN
  interruttore globale non e' rispettato. Proposta: alla nascita della sessione live e prima di ogni
  APERTURA, `_live_brake` come Omega (chiusure sempre servite).
- Sessione figlia che sopravvive a un crash del supervisore: governata da heartbeat/orfane e da
  `controllo_avvio` al nuovo avvio; non verificato con un crash vero.

## 6. Punte che lo scalper puo' mandare (regola: via API solo multipli di 0,50)
| ordine | formula | multiplo di 0,50? |
|---|---|---|
| ingresso maker BACK / pipeline / adozione | `max(stake, 2,00)` arrotondato a `size_step` 0,50 (`_place`, floor_min) | si' (stake non multiplo viene ARROTONDATO al piu' vicino, anche in su: B4) |
| chiusura/scratch/presize/flatten diretta | `compute_green` -> se multiplo e >= 2,00 diretta | si' |
| parte diretta di `_place_exact` | floor(size/0,5)*0,5 se >= 2,00 | si' |
| parcheggio del place-and-trim | 2,00 @1000 | si' |
| **sostituto del place-and-trim BACK** | resto = size - parte diretta; se la chiusura e' < 2,00 il resto e' TUTTA la size (0,05-1,99) | **NO**: ogni resto non in {0,50, 1,00, 1,50} verrebbe rifiutato in live (misura 13/09: «BACK 1,21 -> INVALID_BET_SIZE») |
| presize aggiuntivo LAY->BACK | delta al centesimo, via `_place_exact` | come sopra |
| sniper: ingresso `sniper_stake` (10) | size_step 0,50 | si' |
| sniper: uscite | stesso `_place_exact` | come sopra: resto BACK non multiplo -> rifiutato |
| theta | in live forzato dry-run | n/a |
Proposta: nel place-and-trim una PUNTA ha target = floor al multiplo di 0,50 (0,50/1,00/1,50), il
resto (<0,50) segue la decisione del punto 4. Inoltre lo scalper considera LAY diretta da 0,50
(`_side_min`), il banco oggi da 1,00 (`minimi_it`): la LAY 0,50 @4,1 del replay e' rifiutata dal
banco; la misura del 13/09 dice LAY >= 0,50 al centesimo. Da allineare nella tua correzione di
`minimi_it`/`minimi_banco` (non toccati).

## 7. Non fatto / non verificato
- Nessuna correzione integrata; nessuna seconda registrazione (35760084) rilanciata (memoria).
- Causa della non-terminazione del replay con la patch: ipotesi, non provata.
- Confronto numero per numero col referto OK: fatto solo su azioni/esito (43 contro 538).
- Mappa del punto 5 solo da lettura del codice.
File: `AUDIT_2026-10-04/CERTIFICAZIONE_SCALPER_CALCIO.md`, `..._FIX1_SOTTO_050_NON_INTEGRARE.patch`,
`replay/scalper_calcio_tutti_HEAD_e578802.txt`, `replay/scalper_calcio_base_sonda_7_violazioni.txt`.
Strumenti non committati in `_bis/` (prova.sh, tutti.sh, sonde, mut.py, falsifica.sh).
