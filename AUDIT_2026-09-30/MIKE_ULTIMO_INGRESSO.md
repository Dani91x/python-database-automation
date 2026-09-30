# MIKE - L'ultimo ingresso si ritenta fino al fischio (30/09/2026)

Delegato di costruzione, worktree `agent-a3334b1f3ad2711b2`, base `master` = `fc0428f`.
Decisione dell'utente del 30/09: «Correggi: riprova fino al fischio».
Patch completa contro master: `AUDIT_2026-09-30/MIKE_ULTIMO_INGRESSO.patch` (4 file, `git apply --check -R` pulito).
NIENTE commit. NON certificato: il replay lo lancia il coordinatore.

## 1. Causa radice

`Betfair/mike/engine.py`, `_ultimo_ingresso` (master: righe 3263-3297). Dal segno dei 10 minuti,
con Mike piatto in `WATCH`, ogni giro passa da `_entry_guard` (righe 2853-2900). Su master
QUALSIASI motivo di rifiuto portava in `HOLD`:

```python
why = _entry_guard(ctx, snap, dict(params, pre_last_entry_min=0))
if why:
    return Decision("HOLD", [], "ultimo ingresso: %s: nessun ingresso fino al fischio" % why)
```

e in `HOLD` non nasce piu' nessun ingresso fino al fischio. Quindi:

- **(a)** banca del giro abbinata nei 60 s prima del segno: `_cycle_done` scrive
  `last_green_at = adesso` (engine.py 3205/3212), al primo giro dopo il segno `_entry_guard`
  risponde `"cooldown"` (`pre_reentry_cooldown_s` = 60, riga 2878) -> `HOLD` -> ultimo ingresso perso.
  Lo stesso succede se la banca si abbina appena prima del segno e Mike la vede al primo giro
  dopo (cadenza fino a 20 s).
- **(b)** un controllo momentaneo al primo giro dopo il segno (libro assente, spread oltre 6 tick,
  prezzo fuori banda 1,30-3,00, liquidita' al best sotto lo stake) -> `HOLD` -> perso. Lo diceva gia'
  il commento del caso sintetico `ultimo_ingresso` (synth_mike.py, «con lo spread largo l'ultimo
  ingresso verrebbe valutato (e scartato)»): per questo quel caso usava una sospensione.
  Prezzi non vivi (`order_fresh`) e mercato SOSPESO erano gia' attesa (righe 3283-3286 di master): invariati.

## 2. Cosa ho cambiato (modifica minima, solo `_ultimo_ingresso`)

`Betfair/mike/engine.py` (+20 / -4, di cui 9 righe di docstring e commento):

- righe 3262-3266: costante `_ULTIMO_INGRESSO_RINUNCIA = frozenset({"max cicli", "cap liability partita"})`:
  i soli motivi di `_entry_guard` che all'ultimo ingresso restano rinuncia definitiva;
- righe 3293-3300: dopo `_entry_guard`
  - mercato CHIUSO -> `HOLD` (come prima: su chiuso si cambia strada, catalogo 17);
  - motivo NON di sostanza -> `WATCH`, nessuna azione, motivo `"ultimo ingresso: <motivo>: riprovo al prossimo giro"`;
    al giro dopo `WATCH` richiama `_ultimo_ingresso` (engine.py 3039-3040, invariato);
  - motivo di sostanza -> `HOLD` come prima;
- docstring di `_ultimo_ingresso` aggiornata.

Invariati (letti e rieseguiti dai test): la guardia «una gamba nata dopo il segno = gia' valutato ->
HOLD» (B6: al piu' UN ingresso dopo il segno, anche se non abbinato), l'ingresso solo da `WATCH`
(piatto), la banca che resta fino al fischio (`PRE_OPEN`/`HOLD`, D3), il veto sulla P calibrata Under
3,5 (-> `HOLD`, e dopo un veto mai piu' ingresso), stake, banda, soglie, tetti, gambe, uscite.
`_entry_guard` NON e' toccata: gli altri giri pre-partita si comportano come prima.

Classificazione dei 13 controlli di `_entry_guard` all'ultimo ingresso:

| motivo (`_entry_guard`) | prima | ora |
|---|---|---|
| `max cicli` | HOLD | HOLD (sostanza) |
| `cap liability partita` | HOLD | HOLD (sostanza) |
| veto P calibrata Under 3,5 (fuori da `_entry_guard`) | HOLD | HOLD (sostanza) |
| mercato CHIUSO (arriva come `book assente`) | HOLD | HOLD (su chiuso non si aspetta) |
| `cooldown` (pausa 60 s) | HOLD | WATCH, riprova (caso a) |
| `book assente` (libro assente/prezzo non valido/in gioco) | HOLD | WATCH, riprova |
| `spread N tick` | HOLD | WATCH, riprova |
| `prezzo X fuori banda` | HOLD | WATCH, riprova (decisione dell'utente) |
| `liquidita X < Y` | HOLD | WATCH, riprova (vedi Decisioni, punto 1) |
| `rientro disabilitato (chiusura manuale)` / `chiusura manuale in corso` | HOLD | WATCH, attesa (vedi Decisioni, punto 2) |
| `feed stantio` / mercato sospeso | WATCH | WATCH (invariato) |
| `pre_disabilitato`, `fuori finestra`, `finestra pre-match chiusa` | non raggiungibili qui (`pre_enabled` e' gia' vero, `pre_last_entry_min=0`) | idem |

## 3. Casi (a) e (b), prima e dopo

| caso | prima (master) | dopo |
|---|---|---|
| (a) banca abbinata a segno-30 s | segno+1 s: `HOLD` «cooldown: nessun ingresso fino al fischio»; nessun ingresso | segno+1 s: `WATCH` «cooldown: riprovo»; segno+30 s (fine pausa): `PRE_ENTRY_PENDING`, back Under 20 @ 1,50 LAPSE; abbinato: banca lay 20,27 @ 1,48; poi `HOLD` fino al fischio |
| (a') banca vista a segno+5 s | `HOLD` al giro dopo | `WATCH` fino a segno+65 s, poi ultimo ingresso |
| (b) spread 10 tick / libro assente / fuori banda (3,20 o 1,25) / liquidita' 5 < 20 al segno | `HOLD` | `WATCH` a ogni giro; tornato il controllo: ultimo ingresso |
| (b) spread largo fino al fischio | `HOLD` | `WATCH` a ogni giro fino al fischio, poi `IDLE_LIVE` senza azioni |

## 4. Test

Comando (ambiente neutro: `SUPABASE_URL=http://127.0.0.1:9`, `SUPABASE_SERVICE_ROLE_KEY=x`,
`SUPABASE_KEY=x`, i 20 interruttori `*_CANALE*`/`*_VIA_CANALE` di `replay_mike.sh` a 0; python del
`.venv` del checkout principale, il worktree non ha la junction `.venv`):

- `python -m pytest Betfair/mike -q -p no:cacheprovider` -> **1239 passed** (master 1222 + 17 nuovi), 72 s (rilanciata dopo il test di confine).
- banco, senza replay (`-m "not cert"`): `Betfair/stream/tests/` test_banco_comune, test_banco_flusso_interrotto_cantiere_j2,
  test_banco_identita, test_banco_uscite_manuali_n3, test_cantiere_v2_replay_veloce, test_certifica_esito_dichiarate,
  test_certifica_freni_ambiente_d1quater, test_certifica_freni_da_banco, test_certifica_replay_esploso, test_cert_banco,
  test_registro_bot, test_porta_banco_f4, test_strada_unica_banco, test_contratto_strada_unica ->
  **191 passed, 10 skipped, 22 deselected** (62 s). Gli skip sono registrazioni assenti nel worktree.
  (La cartella `Betfair/stream/backtest/` non contiene test: stanno in `Betfair/stream/tests/`.)

File nuovo `Betfair/mike/tests/test_mike_ultimo_ingresso_2026_09_30.py` (17 test, classi VERE del
motore, parametri da `config.merge_params`, controlli del banco VERI `certificazione.verifica`: a ogni
giro si asserisce che B5, B6, D2, D3 tacciono):
- `test_a_banca_abbinata_nella_pausa_prima_del_segno_l_ultimo_ingresso_arriva` [segno-30 s, segno+5 s]
- `test_b_controllo_momentaneo_al_segno_si_riprova_al_giro_dopo` [spread, libro_assente, prezzi_non_vivi, sospeso, fuori_banda_sopra, fuori_banda_sotto, liquidita]
- `test_b_si_riprova_fino_al_fischio_poi_niente`
- `test_b_ultimo_ingresso_ritentato_non_abbinato_non_si_rifa` (B6)
- `test_sostanza_max_cicli_rinuncia_definitiva`, `test_sostanza_tetto_liability_rinuncia_definitiva`,
  `test_sostanza_veto_under35_rinuncia_definitiva`, `test_sostanza_mercato_chiuso_non_si_aspetta`
- `test_con_posizione_al_segno_nessun_ingresso_invariato`
- `test_b6_confine_gamba_nata_esattamente_al_segno_conta_come_gia_valutato` (aggiunto su richiesta del coordinatore: un ingresso nato ESATTAMENTE al segno, `placed_at == KO - pre_last_entry_min`, conta come «gia' valutato»; se non si abbina -> WATCH, poi HOLD «gia' valutato», nessun secondo ingresso)

Test esistente modificato (asseriva la condotta che l'utente ha cambiato, catalogo 28):
`test_mike_p2_prepartita_2026_09_29.py::test_m2_4_ultimo_ingresso_passa_dai_controlli_d_ingresso`
(riga 157): spread al segno -> ora `WATCH`, e al giro dopo con book buono l'ultimo ingresso parte
(prima: `HOLD` e nessun ingresso).

TDD: prima della correzione i test nuovi davano **9 failed, 7 passed** (passavano gia' sospeso,
prezzi non vivi, le rinunce di sostanza e «con posizione»: sono i test di non regressione).

### Falsificazioni (engine.py mutato da copia, ripristinato da copia in `finally`, `grep -c MUTAZIONE` = 0, `git diff` identico byte per byte a prima)

| mutazione | esito |
|---|---|
| M1 condotta di master (`elif why and why not in ...` -> `elif False`) | 10 rossi: tutti i test (a) e (b) + il test P2 modificato |
| M2 tutto attesa, anche la sostanza (`frozenset()`) | 2 rossi: max cicli, tetto |
| M3 solo `max cicli` come rinuncia | 1 rosso: tetto |
| M4 chiuso trattato come sospeso (ramo CHIUSO tolto) | 1 rosso: mercato chiuso |
| M5 B6 tolto (guardia «gia' valutato» -> `if False`) | 3 rossi: ritentato non abbinato + 2 test P2 esistenti |
| M6 veto come attesa (`HOLD` -> `WATCH` nel ramo veto) | 2 rossi: veto nuovo + veto P2 esistente |
| M7 confine B6 (`placed_at >= last_entry_at` -> `>`; mutazione SOPRAVVISSUTA ai 16 test, trovata dal coordinatore) | 1 rosso: `test_b6_confine_...` (gli altri 41 verdi); ripristino da copia, `grep -c MUTAZIONE` = 0, `git diff` identico |

## 5. Registrazione sintetica nuova (per il replay del coordinatore)

`Betfair/mike/tools/synth_mike.py`: caso nuovo `ultimo_ingresso_riprova` (+66 / -1):
- da t0 (KO-40') Mike entra a 1,50 e appoggia la banca a 1,48;
- (a) da segno-45 s a segno-25 s si scambia a 1,48 (4 messaggi, `trd` cumulativo fino a 800): la banca si abbina nella pausa;
- (b) da segno-25 s a segno+90 s il best back dell'Under 3,5 resta 1,50 ma con size 1,00 (delta sulla stessa quota: nessun livello fantasma) -> liquidita' sotto lo stake anche dopo la pausa;
- da segno+90 s book pieno: atteso l'ULTIMO INGRESSO a 1,50 con banca a 1,48 non abbinata; dal fischio in poi identico a `ultimo_ingresso` (0-0).

La coda «dal fischio» del caso esistente e' stata estratta in `_coda_ultimo_ingresso`: ho generato i 4
casi esistenti con il codice di master e con quello nuovo in una cartella temporanea (copia di
35760084): **raw e scores identici byte per byte** per `reingresso`, `prezzo_migliore`,
`reingresso_2gol`, `ultimo_ingresso`. Cartella temporanea cancellata; nulla scritto in `_live_raw`.

Per il coordinatore:
```
python -m Betfair.mike.tools.synth_mike --caso ultimo_ingresso_riprova --data-dir "<principale>/_live_raw"
python -m Betfair.stream.backtest.certifica mike _synth_mike_ultimo_ingresso_riprova --scenari base --data-dir "<principale>/_live_raw"
```
Atteso: su master nessun `under_entry` dopo il segno (Mike in HOLD); con la patch UN `under_entry`
dopo il segno (a circa segno+90/110 s), B6 sollecitato e verde, D3 verde. Durata stimata: come
`ultimo_ingresso` (stessi 1622 messaggi).

## 6. Copertura §6 e catalogo §7, punto per punto (per quanto tocca questa modifica)

- §6.1 dati: la sintetica usa `marketDefinition` copiate dalla vera, `mcm`/`rc`/`trd` cumulativo, dichiarata SINTETICA dal nome. Nessun formato curato.
- §6.2 scanner/feed: non toccati.
- §6.3 servizio intero: la modifica sta nel motore chiamato da `run_once`; NON verificata col servizio a cadenza reale (replay non mio). Effetto noto sul servizio: una partita piatta in attesa dopo il segno e' ora `WATCH`, che NON conta nel tetto `max_open_matches` (service.py 3723-3727), mentre prima era `HOLD`, che contava pur senza posizione. Non cambia nessuna decisione d'ordine; lo segnalo.
- §6.4 ciclo di vita: nessun cambio a ordini, tipi, persistenza (LAPSE), bet delay, parziali. Sospeso = attesa, chiuso = rinuncia (catalogo 17) coperto da test e falsificazione M4.
- §6.5 persistenza/UI: nessuno stato nuovo (`WATCH`/`HOLD` esistono nel vincolo `CHECK`); `last_reason` e' volatile (service.py 513-518), quindi il ritentare a ogni giro non moltiplica le scritture.
- §6.6 concorrenza: vedi il tetto partite sopra.
- §6.7 scenari: caso sintetico nuovo per (a)+(b); falsificazioni M1-M6 a livello di test unitario, NON a livello di replay.
- §6.8/6.9: nessun controllo o scenario aggiunto al banco; tempi del banco invariati.
- Catalogo: 17 (sospeso/chiuso) coperto; 27 (finti) classi vere e `merge_params`; 28 (test che asserisce il comportamento sbagliato) test P2 aggiornato e dichiarato; 29 (test a vuoto) ogni test nuovo e' stato visto rosso su master o sotto mutazione; 30/35 falsificazioni M1-M6 tutte rosse; 16 (falso positivo del controllo) B6 letto riga per riga: guarda `ctx.state == "WATCH"` e le gambe nate dopo il segno, entrambe rispettate. Punti 1-15, 18-26, 31-34, 36-37: non toccati da questa modifica.

## 7. Parita' paper/live

La modifica sta solo nel motore (`decide`), identico in paper e live; nessun ramo per modalita'.

## 8. Decisioni per l'utente (divergenze da confermare)

Precisazioni richieste dal coordinatore (le porta lui all'utente):
- **(1) liquidita' al best sotto lo stake = ATTESA** all'ultimo ingresso (si riprova al giro dopo);
- **(2) chiusura manuale = ATTESA finche' l'utente non preme «Riprendi»** (fino ad allora nessun ingresso; dopo «Riprendi», se prima del fischio e nessuna gamba e' nata dopo il segno, l'ultimo ingresso puo' partire).

Dettaglio:

1. **Liquidita' al best sotto lo stake** all'ultimo ingresso: il brief elenca come «sostanza» solo
   massimo cicli, tetto e veto, e dice che la rinuncia definitiva resta «solo» per quelli. Ho quindi
   trattato la liquidita' come ATTESA (si riprova). Proposta: tenerla cosi' (il book si riempie
   spesso negli ultimi minuti). Se l'utente la vuole rinuncia: aggiungere `"liquidita"` alla costante
   (una riga, test da invertire).
2. **Chiusura manuale** (`rientro disabilitato`/`chiusura manuale in corso`) dopo il segno: prima
   HOLD definitivo; ora ATTESA: finche' l'utente non preme «Riprendi» Mike non entra (il controllo
   resta), ma se lo preme prima del fischio l'ultimo ingresso puo' partire. Proposta: tenerla cosi'
   (e' l'utente a riabilitare). Alternativa: aggiungere quei due motivi alla costante.
3. **Mercato CHIUSO** prima del fischio: resta rinuncia (come prima), non era nell'elenco del brief.

## 9. COSA NON HO POTUTO VERIFICARE

- **Nessun replay** (vietato al delegato): ne' su 35760084 ne' sulle sintetiche. Non ho visto la patch
  girare con `run_once`, cadenza reale, flumine, bet delay. In particolare non so se nella sintetica
  nuova la banca si abbina davvero entro segno-25 s con 800 di scambiato (il caso esistente usa 60 s
  di scambi): se nel replay non si abbina, il caso (a) non viene esercitato (Mike avrebbe la
  posizione al segno -> HOLD) e il referto lo mostrerebbe come «nessun under_entry dopo il segno».
  Il contenuto del file l'ho controllato leggendolo (livelli e `trd` ai tempi attesi), non replicandolo.
- La sintetica nuova NON e' stata scritta in `_live_raw` del checkout principale: va generata dal coordinatore.
- Non ho eseguito i test `-m cert` del banco (sono replay) ne' la suite intera `Betfair/`.
- Il worktree non ha la junction `.venv`: ho usato il python del `.venv` del checkout principale con
  la cartella corrente nel worktree (i moduli importati sono quelli del worktree: le modifiche e le
  mutazioni hanno cambiato l'esito dei test, quindi il codice caricato era quello giusto).
- Numero di riferimento 1222 su master preso dal brief, non rimisurato su master (1238 = 1222 + 16 nuovi torna).
- Impatto sulla Control Room: una partita piatta dopo il segno in attesa ora mostra `WATCH` con il motivo «riprovo al prossimo giro» invece di `HOLD`; non ho guardato il frontend (fuori perimetro).

## 10. Da controllare dal vivo in paper

Su una partita in cui Mike chiude un giro negli ultimi 11 minuti: dopo il segno dei 10 minuti la
riga in `mike_events` resta `WATCH` con `ctx.last_reason` «ultimo ingresso: cooldown: riprovo al
prossimo giro», e a pausa finita compare UN `under_entry` in `mike_trades` con la banca a 2 tick sotto;
nessun secondo `under_entry` fino al fischio.

## File toccati

- `Betfair/mike/engine.py` (modificato)
- `Betfair/mike/tests/test_mike_p2_prepartita_2026_09_29.py` (modificato, 1 test)
- `Betfair/mike/tools/synth_mike.py` (modificato, caso nuovo)
- `Betfair/mike/tests/test_mike_ultimo_ingresso_2026_09_30.py` (NUOVO, 17 test)
- `AUDIT_2026-09-30/MIKE_ULTIMO_INGRESSO.md`, `AUDIT_2026-09-30/MIKE_ULTIMO_INGRESSO.patch` (NUOVI)
