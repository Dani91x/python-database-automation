# CANTIERE U (29/09/2026) - proposte d'uscita con importo di chiusura 0,00

Bot: `tennis_pro` (reperto), poi `tennis_swing`, `tennis_flb` (stesso difetto latente).
Lavoro nel worktree `agent-a07926ba4040499ed`, NON committato. Patch:
`AUDIT_2026-09-28/CANTIERE_U.patch` (`git diff origin/master` dei 5 file di codice + il test nuovo;
i file `Betfair/` di HEAD e di origin/master sono identici, la patch si applica su master).

## In una riga

Lo 0,00 e' un numero VERO ma di una posizione che NON esiste: il bot legge la posizione sommando
TUTTI i suoi ordini sulla selezione, anche quelli dei trade gia' chiusi. Dopo il primo trade chiuso
resta un residuo di centesimi; il trade NUOVO, con l'ingresso ancora in coda (0 abbinato), viene
scambiato per una posizione abbinata e il bot "decide" scaglione / target / strutturale su quel
residuo. La chiusura che ne esce vale 0,0013-0,0040 EUR -> scheda "chiudi 0,00". Alla firma NON
parte nessun ordine di chiusura (il `_place` scarta tutto cio' che arrotondato e' sotto 0,01), ma il
trade nuovo viene chiuso (`_finish`: annulla l'ingresso se ancora in coda, stato CLOSING) oppure lo
scaglione viene "consumato" senza ordine. **Difetto: si'.**

## 1. Dove nasce lo 0,00 (codice di origin/master)

`tennis_pro_bot.py`, tutti i punti che costruiscono una proposta passano da `_cancello_lascia`
(righe 263-283 di master):

| motivo | chiamata (master) | prezzo | size_chiusura | lato_chiusura | se_chiudi | se_vince / se_perde |
|---|---|---|---|---|---|---|
| scaglione | `_manage` 851-858 | `mkt` = best-lay (trade BACK) / best-back (LAY) | `compute_green(nw,nl,mkt)[1] * staged_frac` | `g[0]` | `g[2]*frac` | `nw`, `nl` dal blotter |
| target | 860-864 | idem | `g[1]` | `g[0]` | `g[2]` | idem |
| stop | 865-869 | idem | `g[1]` | `g[0]` | `g[2]` | idem |
| strutturale | 872-877 | idem | `g[1]` | `g[0]` | `g[2]` | idem |
| time | non esiste nel PRO (e' dello swing) | | | | | |

`nw, nl` vengono da `_position` (master 384-408), che somma **ogni** ordine della strategia con
quella `selection_id`, senza distinguere il trade. `proposta_di` (`uscite_proposte.py:86-108`)
arrotonda `size_chiusura` a 2 decimali: 0,0033 diventa 0,0.

E' un numero **vero** (non un "mancante scritto come zero"): la size e' calcolata subito, ed e'
davvero ~0,003 EUR. Ma e' la chiusura del **residuo del trade precedente**, non del trade per cui
nasce la proposta. La proposta nasce perche' il ramo "ingresso non ancora abbinato" di `_manage`
(master 778: `if (b + l) <= _EPS`) non scatta: `b + l` vale 4,06 EUR di ordini vecchi gia' pareggiati.

## 2. Cosa parte alla firma (dal replay, con la sonda)

Alla firma `_cancello_lascia` torna True e:
* **scaglione**: `_close_at(frac=0.4)` -> `_place(size 0,0013)` -> arrotondato 0,00 -> `None`: nessun
  ordine. `staged_done=True`: lo scaglione di QUESTO trade e' bruciato senza aver coperto niente.
* **target / strutturale**: `_full_close` -> `_close_at` -> `_place(size 0,0033)` -> nessun ordine;
  poi `_finish`: annulla `trade["order"]` (l'ingresso nuovo, se ancora in coda), conta un green o
  uno scratch con `locked` = -0,057 (il residuo vecchio), stato CLOSING; la sorveglianza trova la
  selezione "pari" e dichiara FLAT.

In automatico la stessa decisione scatta nello stesso istante (senza i 5 s della firma) con lo
stesso esito: nessun ordine, trade nuovo chiuso. Quindi la firma "coincide" con l'automatico, ma
entrambi sbagliano: la strategia avrebbe dovuto trattare quel trade come un ingresso non abbinato
(attesa, timeout di 25 s, ingresso morto = game libero). L'utente firma una scheda che dice 0,00 e
che in realta' **chiude il trade nuovo**: approva al buio.

## 3. Quante e in che situazioni (replay 35794049, Sinner-Struff 07/07)

Comando (autorizzato) lanciato una volta senza modifiche:
`python -m Betfair.stream.backtest.certifica tennis_pro 35794049 --data-dir "C:/Users/Admin/Desktop/tennis_rec/20260707" --scenari uscite-manuali,uscite-manuali-firmate --worker 1 --diario AUDIT_2026-09-28/cantiere_u/diario_prima.jsonl`
(ambiente: SUPABASE finte, LIVE_ORDER_MODE=LIVE, LIVE_KILL_SWITCH=false, i 20 interruttori
`*_CANALE*` di `Betfair/conftest.py:108-116` a 0). Esito: 2 OK, 0 violazioni, 29,7 s. Referto:
`cantiere_u/replay_prima.txt`. Il diario del banco non contiene le proposte, per cui ho rilanciato
LO STESSO comando dentro una sonda che avvolge (senza sostituire) `_cancello_lascia`, `_place` e
`proposta_di`: `cantiere_u/sonda_proposte.py` -> `cantiere_u/sonda_prima.jsonl`, lettura con
`cantiere_u/analizza_sonda.py` (elenco completo: una riga per decisione con importo 0).
**Nota: sono DUE esecuzioni del replay, non una** (la seconda identica alla prima, solo osservata).

Numeri:
* scenario `uscite-manuali` (nessuna firma): 28 proposte nate, **0 a zero** (il primo trade non si
  chiude mai, quindi nessun residuo).
* scenario `uscite-manuali-firmate`: 41 proposte nate, **30 a zero** (scaglione 11, strutturale 16,
  target 3); uscite firmate eseguite 31, di cui **24 a zero** (scaglione 7, strutturale 15, target 2):
  24 chiamate di copertura con size 0,0006-0,0040 scartate da `_place`, nessun ordine partito.
* tutte sulla selezione 10372252, tutte con l'ingresso del trade nuovo non ancora abbinato.

Posizione del bot al momento (dal blotter; i residui crescono perche' ogni trade chiuso ne lascia uno):

| dalle | abbinato sulla selezione | se vince | se perde | importo chiusura |
|---|---|---|---|---|
| 12:41:32 | BACK 2,06 @1,060 + LAY 2,00 @1,090 | -0,056 | -0,060 | 0,0033 (0,0013 lo scaglione) |
| 13:26:44 | BACK 6,06 @1,050 + LAY 5,93 @1,073 | -0,132 | -0,130 | 0,0019 |
| 13:40:00 | BACK 10,12 @1,056 + LAY 9,93 @1,076 | -0,188 | -0,190 | 0,0015 |
| 14:07:05 | BACK 12,18 @1,052 + LAY 11,93 @1,073 | -0,247 | -0,250 | 0,0033 |
| 14:30:00 | BACK 14,18 @1,047 + LAY 13,91 @1,067 | -0,266 | -0,270 | 0,0039 |

Esempio in euro (12:44:25 -> firma 12:44:32): scheda "strutturale, chiudi LAY 0,00 a 1,10, se
chiudi -0,057"; alla firma: `_place(LAY 1,10, 0,0033)` scartato, trade chiuso; il bot rientra alle
12:44:33 con un BACK 2,00 @1,11 nuovo.

## 4. Gli altri bot (lettura del codice)

| bot | stesso difetto? | perche' (file:riga, codice corretto) |
|---|---|---|
| `tennis_swing_bot.py` | **SI' (latente)** | `_pos` 211-230 somma tutti gli ordini della selezione; ramo ingresso `(b+l) <= _EPS` (master 470); proposta in `_cancello_lascia` 144-170 (master 148-157). Un secondo trade sulla stessa selezione dopo uno chiuso ha lo stesso fantasma. |
| `tennis_flb_bot.py` | **SI' (latente, modalita' "green")** | `_matched` 161-178 per selezione; in "green" la selezione torna DONE e si ri-arma (359-362): l'ingresso nuovo sopra il residuo fa nascere un green a 0,00 (proposta 520-535). In piu' il ramo PENDING (master 414) scambiava il residuo per un "cancel perso" e riapriva il trade. |
| `tennis_scalper_bot.py` | no | la posizione e' quella degli ordini DELLO slot (`_matched_position(entry, ...)` 2338 e seg.), non della selezione; proposte in `_lascia_uscire` 2063-2082. Uno zero puo' nascere solo con abbinati sotto il centesimo (non visti): lo coglie ora UM2. |
| `scalper/scalper_bot.py` | no | idem, `_matched_position` 2147 per slot; proposte `_lascia_uscire` 1918-1957. |
| `scalper/sniper_bot.py` | no | posizione dagli `pos.entries` del ciclo (`_matched` 729), azzerati a ogni green (534-537); proposte `_lascia_uscire` 631-668. |

## 5. Perche' UM2 non l'ha segnalato

`uscite_manuali.difetti_proposta` (master 104-114) controllava solo che le chiavi ci fossero e non
fossero `None`: uno `0.0` e' "un numero presente". UF2 confronta l'importo della proposta (0,00) con
gli ordini partiti (0,00): uguali, quindi "esatto". Il banco non poteva vederlo.

## 6. Correzione (nessuna soglia di strategia toccata)

1. `tennis_scalper_bot.py:183` **`green_piazzabile(nw, nl, prezzo, frazione)`** (nuova): la chiusura
   che partirebbe davvero = `compute_green` x frazione arrotondata al centesimo (la stessa
   `round(size, 2)` di `_place`); `None` se sotto 0,01 o prezzo non valido.
2. `tennis_pro_bot.py`
   * `_cancello_lascia` (276): la proposta usa `green_piazzabile`; se `None` la proposta NON nasce e
     l'uscita non parte (in manuale e in automatico).
   * `_close_at` (533): l'ordine usa lo stesso `green_piazzabile` -> la firma manda esattamente il
     `size_chiusura` visto dall'utente.
   * `_manage` (801) + `_niente_da_chiudere` (905): una posizione senza niente di piazzabile da
     chiudere al prezzo d'uscita e' un ingresso non abbinato: timeout 25 s, ingresso morto = game
     libero, come da strategia.
3. `tennis_swing_bot.py`: proposta (153) e chiusura (319) con `green_piazzabile`; fantasma nel ramo
   ingresso (485-487).
4. `tennis_flb_bot.py`: proposta del green (531) e `_green` (290) con `green_piazzabile` (la stima
   del locked resta quella di prima); fantasma nel ramo ingresso e nel ramo PENDING (416-437).
5. `backtest/uscite_manuali.py:104-127` UM2: `size_chiusura` <= 0 (o non numerica) = numero
   mancante, senza eccezioni (nemmeno `numeri_non_disponibili`).

Effetto sulle decisioni: nessuna soglia cambia. Cambia solo che il bot non prende piu' per
"abbinato" un trade il cui ingresso non lo e': e' la correzione della consapevolezza degli ordini
(§7), non un cambio di strategia. Dove prima la firma chiudeva un trade senza ordini, ora il trade
aspetta il suo ingresso come previsto.

File toccati: `Betfair/stream/tennis_scalper/tennis_scalper_bot.py`, `tennis_pro_bot.py`,
`tennis_swing_bot.py`, `tennis_flb_bot.py`, `Betfair/stream/backtest/uscite_manuali.py`.
File nuovi: `Betfair/stream/tennis_scalper/tests/test_cantiere_u_proposte_a_zero_2026_09_29.py`;
`AUDIT_2026-09-28/cantiere_u/` (sonda, analisi, script di falsificazione, esiti, diari).

## 7. Test e falsificazione

* Nuovi: `python -m pytest Betfair/stream/tennis_scalper/tests/test_cantiere_u_proposte_a_zero_2026_09_29.py -q -p no:cacheprovider`
  -> **15 passed** (~4 s). Tutti dal bot vero via `process_market_book`; finti degli ordini con le
  chiavi del `BetfairOrder` (`status` = Enum `OrderStatus` vero, `size_remaining`, `order_type`);
  il caso PRO riproduce il residuo reale del replay (BACK 2,06 @1,06 + LAY 2,00 @1,09).
* Sul codice di master (4 file ripristinati, helper lasciato; prima versione del file, 12 test):
  **9 failed, 3 passed** (i 3 verdi
  sono il test dell'helper, UM2 con importo vero, e la parita' proposta = ordine su posizione vera).
* Falsificazione: `python AUDIT_2026-09-28/cantiere_u/falsifica_u.py` (esito in
  `cantiere_u/falsifica_u_esito.txt`): **8 mutazioni, 8 ROSSE**, "MUTAZIONE rimaste: 0", `git diff`
  identico a prima (0 righe diverse). M1 soglia del centesimo tolta (10 rossi); M2 fantasma PRO (2);
  M3 proposta con importo diverso dall'ordine (1); M4 fantasma swing (1); M5 fantasma FLB (1);
  M6 "cancel perso" FLB (1); M7 UM2 accetta lo zero (3); M8 proposta a zero nel cancello PRO (1).
* Regressione: `Betfair/stream/tennis_scalper/tests` -> **268 passed** (6,7 s); test collegati in
  `tennis_live/tests` (4 file), `stream/tests` (5 file: banco N3, firma TTL, proposte coi numeri,
  strada unica, freno) e `misura_punto8` -> **306 passed** (26 s). Un test esistente
  (`test_flb_green_est_exact_with_partial_fraction`) era diventato rosso con una mia prima versione
  che cambiava la stima del locked FLB: ripristinata la stima di prima, verde.

### 7-bis. v2 (revisione del coordinatore): 3 mutazioni sopravvissute, SOLO test nuovi

Codice dei bot invariato (parte di codice di `CANTIERE_U_v2.patch` identica riga per riga a
`CANTIERE_U.patch`). 4 test nuovi nel file (19 in tutto), script
`cantiere_u/falsifica_u_v2.py`, esito `cantiere_u/falsifica_u_v2_esito.txt`: ripristino da copia,
hash SHA-256 uguale dopo ogni mutazione, "MUTAZIONE rimaste: 0".
* M7 swing (`_cancello_lascia`, `g ... or (side, 0.0, 0.0)`): ROSSO con
  `test_swing_dry_run_uscita_sotto_il_centesimo_non_diventa_proposta`. Prova di raggiungibilita':
  fuori dal dry-run il punto NON e' raggiungibile, perche' il ramo `vuota` di `_manage_trade` usa lo
  stesso prezzo (`px_uscita` = `px`, stessa formula maker/lato) e la stessa `green_piazzabile`
  senza frazione: se la chiusura e' sotto il centesimo si esce prima. Lo e' solo in dry-run
  (posizione virtuale stake 2,00 @ prezzo d'ingresso, `vuota` spento), con un'uscita oltre ~400
  volte il prezzo d'ingresso (test: ingresso 1,01, uscita 1000 -> 0,002). Guardia difensiva.
* M10 flb (green): ROSSO con i due `test_flb_green_frazionato_sotto_il_centesimo_*`. Raggiungibile
  davvero in modalita' hybrid: abbinato parziale reale 0,01 di un LAY a 1,05, green totale a 1,07 =
  0,0098 -> 0,01 (il ramo `vuota` non scatta), green al 50% = 0,0049 -> 0,00.
* M12 pro (`_niente_da_chiudere`, lati scambiati): ROSSO con
  `test_pro_il_lato_del_prezzo_decide_niente_da_chiudere`: sbilancio 0,0052, spread 1,01 / 1,10;
  al best-lay (giusto) 0,0047 -> niente da chiudere e l'ingresso morto libera il trade (FLAT); al
  best-back 0,0051 -> 0,01, il trade resta OPEN sulla posizione fantasma. La media 1,0574 del LAY
  e' un prezzo medio di piu' fill (come 1,047/1,067 nel replay), non un gradino della ladder.
* `Betfair/stream/tennis_scalper/tests`: 272 passed (6,6 s).

## 8. Parita' paper / live

Nessun ramo nuovo per modalita'. `green_piazzabile` usa lo stesso arrotondamento di `_place`, che e'
lo stesso in paper e live; in live (e in paper, `self.live` vale per entrambi dal 28/09) una
copertura sotto il minimo continua a passare da `UsciteEsatte.piazza` con lo stesso importo
arrotondato di prima.

## 9. Cosa NON ho fatto / NON ho potuto verificare

* **Replay dopo la correzione NON eseguito** (l'autorizzazione era per un replay; ne ho gia' usati
  due). Da lanciare (coordinatore), stesso ambiente, per vedere 0 proposte a zero e UM2 pulito:
  `python AUDIT_2026-09-28/cantiere_u/sonda_proposte.py AUDIT_2026-09-28/cantiere_u/sonda_dopo.jsonl tennis_pro 35794049 --data-dir "C:/Users/Admin/Desktop/tennis_rec/20260707" --scenari uscite-manuali,uscite-manuali-firmate --worker 1`
  poi `python AUDIT_2026-09-28/cantiere_u/analizza_sonda.py AUDIT_2026-09-28/cantiere_u/sonda_dopo.jsonl`
  (con `PYTHONPATH` = radice del worktree). Atteso: nessuna riga "ZERO"; il numero di trade e il
  P&L del replay firmato CAMBIANO (i trade nuovi non vengono piu' chiusi dalla firma a zero):
  confrontarli con `sonda_prima.txt`.
* Swing e FLB: difetto dimostrato solo coi test (nessun replay lanciato su quei bot).
* Non ho verificato se sulle registrazioni esistono abbinati sotto il centesimo per lo scalper
  tennis / calcio / sniper (lo zero li' e' solo teorico): lo dira' UM2 al prossimo replay del banco.
* Non ho cambiato `_position` per contare solo gli ordini del trade: il residuo vecchio (<= 0,02)
  resta sommato alla posizione nuova quando l'ingresso si abbina; la chiusura include quei centesimi
  (e' denaro vero esposto sulla selezione, quindi e' corretto chiuderli insieme).
* UI Control Room: non toccata; con la correzione la scheda "chiudi 0,00" non puo' piu' arrivarle.

## 10. Decisioni per l'utente

Nessuna: nessuna soglia, stake o gamba cambiata. Da sapere: in manuale, finche' la patch non e'
sul master, una scheda "chiudi 0,00" del PRO **non va firmata** (chiude il trade nuovo senza ordini).

## 11. Da controllare dal vivo in paper al prossimo avvio

Nella Control Room, tennis PRO a uscite manuali: nessuna proposta con importo 0,00 dopo il primo
trade chiuso su una partita; nel diario del bot, dopo un trade chiuso, un nuovo ingresso non
abbinato deve dare `entry_timeout` o `entry_scaduta` (non `exit` con `locked` di centesimi).
