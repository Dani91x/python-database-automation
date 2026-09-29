# CANTIERE MIKE-MOTORE - Pacchetto P1: il cancello delle uscite (29/09/2026)

Base: master `2768f04`. Patch: `AUDIT_2026-09-29/MIKE_P1.patch` (verificata con
`git apply --cached --check` sull'indice = master: applica pulita). Nessun commit.

## 1. Cosa e' cambiato (righe toccate)

| File | + / - | Cosa |
|---|---|---|
| `Betfair/mike/engine.py` | +48 / -6 | vedi sotto |
| `Betfair/mike/certificazione.py` | +60 / -0 | controlli di banco G2, G3 |
| test esistenti (5 file) | +211 / -102 | aggiornati uno per uno (par. 3) |
| `Betfair/mike/tests/test_mike_p1_cancello_uscite_2026_09_29.py` | nuovo, 28 test | |

`engine.py`, funzione per funzione:
- **nuova `uscita_in_perdita(d)`** (18 righe, quasi tutte commento): l'uscita della decisione
  puo' chiudere IN PERDITA? Si' se `close_reason` e' `loss_*` o `reentry_time`, o se un ordine
  porta la nota `VETO_U35_NOTE` (chiusura del veto pre-partita, che P2 toglie). Tutto il resto
  (green pre-partita, `ko_green`, cash out `profit` a soglia e intelligente, green del rientro)
  e' uscita in profitto.
- **`gate_uscite`**: dopo il controllo delle protezioni, `if not uscita_in_perdita(d): return
  _decadi(...)` -> M1.1, M4.1, M4.2, M4.3, M4.4. L'uscita in profitto parte con l'interruttore
  su manuale o automatico; una proposta rimasta viva decade (telemetria
  `uscita_proposta_decaduta`, come a interruttore acceso). L'interruttore governa ormai solo le
  uscite in perdita, che restano proposta urgente (chiave `chiusura|cN` invariata).
- **`_uscita_gia_in_corso`** (M8.1): per un'uscita in perdita la regola "esiste gia' una gamba
  dello stesso ruolo nel ciclo" non vale piu': ogni uscita in perdita chiede la sua firma. Resta
  la regola dello stato di chiusura in corso (`LIVE_CLOSING`, ...): riprezzo e residuo di
  un'uscita firmata non chiedono altre firme.
- **`_decide_covered`** (M4.5): tolto il ramo `loss_cap` (5 righe) e scritto perche'.
- **`_decide_flatten`** (FUORI PIANO, reperto del replay, vedi par. 6): la chiusura manuale non
  piazza la sua lay se sulla stessa selezione c'e' una lay di un altro ruolo in volo (viva o a
  esito ignoto): aspetta l'esito. E' la regola dell'utente «mai due lay a mercato» (16/09).

Nessuna firma di funzione esistente cambiata, nessun nome di stato, ruolo, chiave di parametro,
chiave di telemetria cambiati. `MOTIVI_PROTEZIONE = ("loss_cap",)` resta (nessuno lo produce
piu'; una partita gia' in `LIVE_CLOSING` per `loss_cap` finisce la sua chiusura come prima).

## 2. Collegamenti controllati (grep prima di toccare)
- `USCITE_DISCREZIONALI`, `categoria_uscita`, `chiave_uscita`, `STATI_USCITA_IN_CORSO`,
  `_uscita_gia_in_corso`, `_stessa_uscita_firmata`, `gate_uscite`: solo `engine.py`; il servizio
  usa `E.USCITE_DISCREZIONALI` (`_chiave_gamba`, service.py:3211) e la telemetria
  `uscita_eseguita_su_approvazione` / `uscita_proposta(_decaduta)` (service.py:3200, 4425-4551):
  invariati; `_request_approva_uscita` (service.py:3216) invariato.
- `uscita_proposta`/`uscita_approvata`: persistiti in `service._CTX_FIELDS` (service.py:279);
  frontend `PropostaUscitaMike.tsx`, `lib/mike.ts`: leggono le stesse chiavi; la proposta
  `green_pre`/`ko_green`/`reentry_green` non nasce piu' (la scheda semplicemente non la riceve).
- `event_loss_cap_pct`: `config.py:309` (resta, vedi par. 7), `engine.py` (tolto),
  `certificazione.py:414` (commento di G1, invariato), frontend `lib/mike.ts:542,588` (pannello).
- `close_reason`: `exit_kind_for` (engine.py:971, invariato), `_decide_closing`
  (`reentry_allowed` solo con `profit`, invariato).
- banco: i controlli UM1-UM4/UF1-UF3 citati nel piano vivono in
  `Betfair/stream/backtest/uscite_manuali.py` e osservano `CancelloUscite` dei bot di flusso
  (tennis, scalper): Mike NON ci passa (ha il suo cancello nel motore). Per Mike ho aggiunto G2 e
  G3 in `Betfair/mike/certificazione.py`.

## 3. Test esistenti aggiornati (motivo: decisioni 13, 16, 18 del piano)

| Test (file) | Diceva | Dice ora | Decisione |
|---|---|---|---|
| `test_spento_il_green_pre_match_diventa_proposta` -> `test_spento_il_green_pre_match_parte_da_solo` (uscite_automatiche) | green pre-partita = proposta | parte da solo, identico all'acceso | M1.1 |
| nuovo nello stesso file `test_spento_l_uscita_in_perdita_diventa_proposta` | - | la meccanica della proposta (nascita, chiave, istante fermo, nessun log ripetuto) sull'uscita in perdita | 16 |
| `test_spento_il_cash_out_in_profitto_resta_fermo_e_propone` -> `..._parte_da_solo` | cash out profit = proposta | LIVE_CLOSING con le chiusure | M4.1 |
| `test_spento_il_cap_perdita_partita_chiude_lo_stesso` -> `..._non_chiude_piu` | il cap chiudeva anche in manuale | non chiude, non propone | M4.5 |
| `test_fuori_da_uno_stato_di_chiusura_la_stessa_decisione_si_propone` | veicolo `profit` | veicolo `loss_2t` | 13/16 |
| `test_approvata_passa_esattamente_la_decisione_della_strategia` | firma sul green pre-partita | firma sull'uscita in perdita | 13/16 |
| `test_approvazione_di_un_altra_chiave_non_sblocca_e_si_cancella` | idem | idem | 13/16 |
| `test_approvazione_scaduta_non_sblocca` | idem | idem | 13/16 |
| `test_spento_la_finestra_del_fischio_corre_e_poi_la_proposta_decade` -> `..._e_l_uscita_parte_da_sola` | ko_green proposta poi decaduta | ko_green piazzata, a finestra scaduta ritirata e copertura | M4.2 |
| `test_riaccendere_a_caldo_esegue_e_fa_decadere_la_proposta` | veicolo green | veicolo uscita in perdita | 13/16 |
| `test_servizio_spento_nessuna_green_e_proposta_nel_contesto` -> `test_servizio_spento_la_green_parte_da_sola_e_nessuna_proposta` + nuovo `test_servizio_spento_l_uscita_in_perdita_e_proposta_nel_contesto` | green non a mercato | green a mercato; la proposta si prova sull'uscita in perdita (run_once, partita seminata coperta, 2 gol al 60') | M1.1/16 |
| `test_servizio_approvazione_dalla_scheda_manda_la_green` -> `..._manda_l_uscita_in_perdita` | firma -> green | firma -> under_close + over_close | 16 |
| `test_servizio_approvazione_su_proposta_cambiata_rifiutata` | veicolo green | veicolo uscita in perdita | 16 |
| `test_servizio_riaccendere_a_caldo` | veicolo green | veicolo uscita in perdita | 16 |
| `test_la_green_approvata_porta_la_chiave_della_richiesta` -> `test_l_uscita_approvata_porta_la_chiave_della_richiesta` (chiave_approvazione_b17) | green firmata porta `approvazione_id` | le chiusure firmate lo portano | 16 |
| `test_firma_sulla_stessa_uscita_passa` (firma_stesso_motivo) | profit/profit | loss_ht/loss_ht | 13 |
| `test_firma_senza_proposta_non_esegue_niente` (idem) | veicolo profit | veicolo loss_ht | 13 |
| `test_firma_rimasta_dopo_la_decadenza_non_esegue_un_altra_uscita` (coordinatore) | firma profit, poi loss_ht | firma loss_ht, poi loss_2t | 13 |
| `test_la_decadenza_della_proposta_porta_via_la_firma` (coordinatore) | veicolo profit | veicolo loss_ht | 13 |
| `test_selezione_decisa_non_pretende_prezzo_e_non_congela` (engine_cert) | chiusura provocata dal cap 10 % | chiusura provocata dall'uscita 2T a regola fissa 50 % (stesso scopo: selezione decisa senza prezzo) | M4.5 |

Nessun test cancellato o saltato. `test_firma_in_profitto_non_esegue_un_uscita_in_perdita`
resta com'e' (verde): copre una firma su una proposta `profit` rimasta da PRIMA
dell'aggiornamento.

## 4. Test nuovi (28, file `test_mike_p1_cancello_uscite_2026_09_29.py`)
Green pre-partita resting e taker, banca al fischio, cash out a soglia, cash out intelligente,
green del rientro: partono in manuale con gli STESSI ordini dell'automatico; proposta in
perdita che decade quando la strategia chiude in profitto; uscita in perdita = proposta urgente;
uscita in perdita firmata parte; `reentry_time` e chiusura del veto restano governate; cap di
perdita tolto (manuale e automatico); M8.1 (difetto D1 riprodotto ROSSO prima della modifica:
2 test); seguito di un'uscita firmata non chiede altre firme; M8.2 (4 prove); chiusura manuale
con banca a esito ignoto; banco G2/G3 (4 test, falsificazione dei controlli).

Suite: `Betfair/mike` **1050 verdi** (1020 di riferimento + 30);
`pytest Betfair/mike Betfair/stream/tests -k "mike or banco or certifica or uscite"`: 1402
verdi, 25 saltati (prima della correzione J5; rilanciata `Betfair/mike` dopo: 1050 verdi).

## 5. Falsificazione (`AUDIT_2026-09-29/mike_p1/falsifica_mike_p1.py`, ripristino da copia in memoria + hash)

| Mutazione | Esito |
|---|---|
| M1 uscite in profitto di nuovo proposte | ROSSO, 12 test |
| M2 una gamba precedente autorizza l'uscita in perdita (D1) | ROSSO, 3 test (M8.1 x2 + veto) |
| M3 cap di perdita rimesso | ROSSO, 3 test |
| M4 `reentry_time` trattata come profitto | ROSSO, 1 test |
| M7 chiusura manuale senza la guardia J5 | ROSSO, 1 test |
| M5 G2 muto / M6 G3 muto | ROSSO, 2 / 1 test |
Ripristino verificato: hash identici, nessuna `MUTAZIONE` nei file.

## 6. Replay (`AUDIT_2026-09-29/mike_p1/replay_p1_mike_tutti.txt`, comando del brief, 3 worker)
- **14/15 OK, 1 violazione: J5 nello scenario `cashout-globale`** («nuova lay `manual_close` su
  OU35|UNDER mentre `under_green-0-2` e' ancora in volo»). Causa: la banca pre-partita ora e' a
  mercato anche in manuale; il cash out dell'utente ne chiede l'annullamento, l'annullamento non
  e' confermato (esito ignoto) e `_decide_flatten` (che non passa da `_una_sola_lay`) piazzava
  comunque la chiusura. Difetto LATENTE di prima (con le uscite automatiche accese capitava
  uguale), portato allo scoperto da P1. Corretto (par. 1), test + mutazione M7.
- Rilanciato il SOLO scenario `cashout-globale` dopo la correzione
  (`replay_p1_cashout_globale_dopo_fix_j5.txt`): **OK, 0 violazioni**, 84,9 s, 662 tick/s.
- Tempi del giro completo (per scenario, s | tick/s): base 179,7|312; taker 180,2|311;
  cap-stretto 181,1|310; bot-fermo 112,5|500; senza-seconda-puntata 147,7|381; feed-stantio
  99,1|568; esiti-ignoti 134,4|418; taker-esiti-ignoti 123,1|457; riavvio 123,8|454; gol-precoce
  114,0|493; cashout-globale 105,7|532; chiuso-fuori-app 120,1|468; copertura-rifiutata
  137,3|410; rifiuti-betfair 136,9|411; chiusura-abbinata-in-parte 126,0|446. **Totale 747 s
  (riga LENTO, tetto 600)** contro 446 s del riferimento: sullo stesso PC girava l'altro
  delegato; non ho misurato il replay di riferimento nelle stesse condizioni, quindi NON so dire
  quanto del rallentamento e' mio (piu' ordini, piu' giri di riconciliazione).
- Differenze attese rispetto al riferimento: azioni 2 -> 7 (base): la green pre-partita e
  l'uscita al fischio ora vanno a mercato; `place_resting` x3, `cancel` x2; motivi "uscita
  proposta ... green resting appoggiata" x761 e "... uscita appoggiata a 1.69" x144 sostituiti
  da "posizione aperta, green resting sul book" x761 e "uscita a +2 tick sul book" x142; restano
  proposte le sole uscite in perdita (uscita a modello 2T). G3 sollecitato 25.404 volte, 0
  violazioni; G2 mai sollecitato (nel replay nessuno firma: nessuna uscita in perdita parte, che
  e' il comportamento voluto) -> "non lo so" su G2 a livello di replay, coperto dai test.
- DA GUARDARE (non e' mio perimetro): nel replay compaiono righe
  `CRITICAL ... annullo NON confermato su under_green-0-2 / ko_green-0-4 -> riconciliazione`
  (annullamenti in paper via canale di comando del runner, "socket del banco chiuso"). La
  riconciliazione poi chiude il caso (K1-K4 a 0), ma e' il servizio/banco (pacchetto P4).

## 7. Stati, ruoli e parametri rimasti senza uso
- Motivo `loss_cap` e `MOTIVI_PROTEZIONE`: non piu' prodotti; il ramo del cancello resta.
- Parametro `event_loss_cap_pct` (config.py:309, pannello `lib/mike.ts:542` «Cap perdita per
  partita %, oltre: chiusura forzata»): resta nella whitelist ma NON governa piu' niente. Il
  pannello mostra ancora 100 %: **va tolto o rietichettato nella UI (pacchetto P6)**; non l'ho
  toccato (fuori perimetro, e cambiare il default non basterebbe: il valore salvato nel DB
  vincerebbe).
- Categoria di proposta `green_pre`, `ko_green`, `reentry_green`: non nascono piu' (restano nel
  codice per la chiusura del veto pre-partita fino a P2 e per `reentry_time`).

## 8. Cosa NON ho potuto verificare
- Il comportamento in LIVE vero: solo test e replay paper/canale.
- Il replay con una FIRMA dell'utente: il banco di Mike non firma (manca uno scenario
  "uscite firmate" per Mike). M8.1 e la firma sono provati nei test del motore e del servizio
  (`run_once` + richiesta `approva_uscita`), non sul replay.
- Il tempo del replay a macchina scarica (vedi par. 6).

## 9. Rischi per le partite gia' in corso all'aggiornamento
- Una proposta `green_pre`/`ko_green`/`reentry_green`/`chiusura profit` viva nel contesto:
  al primo giro decade (telemetria `uscita_proposta_decaduta`) e l'uscita parte da sola.
- Una firma data a una proposta in profitto e non ancora eseguita: l'uscita parte comunque
  (senza consumare la firma, che poi decade con la proposta).
- Una partita in `LIVE_CLOSING` per `loss_cap`: finisce la chiusura (stato in corso).
- In manuale, dal primo giro dopo l'aggiornamento, su ogni partita in PRE_OPEN la banca a 2 tick
  sotto va a mercato: e' il comportamento ordinato (M1.1), ma e' un cambiamento visibile.

## 10. Decisioni per l'utente
- Nessuna nuova sulla strategia. Da confermare: la chiusura a tempo del rientro
  (`reentry_time`, spenta di serie: `reentry_exit_until_min` 0) l'ho lasciata tra le uscite da
  firmare perche' puo' chiudere in perdita.
