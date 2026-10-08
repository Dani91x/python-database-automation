# CANTIERE 5 - Parcheggio del place-and-trim nei bot TENNIS: uniformato al calcio

Delegato di costruzione, sessione cloud, 08/10/2026. Worktree
`.claude/worktrees/agent-ae472689cfc08c6bc`, partenza `b5547eb` (contiene «fix(banco): regola
del mercato che attraversa»; il worktree era a `8226d76`, portato a `b5547eb` con
`git merge --ff-only`, nessun commit nuovo). Lavoro NON committato.

## 1. Causa

Il calcio (cantiere L, 07/10, `scalper_bot.stato_parcheggio`) parcheggia la banca alla quota di
`trading/submin.quota_parcheggio_lontano`: la quota piu' bassa con la banca residua (dopo il
taglio) dentro la banda INVALID_PROFIT_RATIO 0,80-1,25. I bot tennis no:

| dove (b5547eb) | cosa faceva |
|---|---|
| `tennis_scalper_bot.py` `_place_exact` (~2724) | `SubminState(...)` a mano SENZA `park_price` -> `prezzo_parcheggio` = `initial_place_price` = LAY 1,01 fissa |
| `condotta_ordini.py` `UsciteEsatte.piazza` (~399) | idem, piu' `placed_size=IT_BACK_MIN_STAKE` (valore giusto, 1,00, ma la costante della PUNTA anche per la banca) |
| `tennis_scalper_bot.py` `_drive_flatten` (~2227) | riconosce il parcheggio dalla quota `p <= 1.011` |
| `certificazione_bot.py:220` | `_QUOTA_PARCHEGGIO = {"BACK": 1000.0, "LAY": 1.01}` fissa (B8, catena del sostituto) |

Con resto 0,50-0,79 il taglio lascia una banca a 1,01 con liability arrotondata fuori banda
(0,70 @1,01 = 0,007 -> 0,01, +43 %): Betfair rifiuta il taglio (INVALID_PROFIT_RATIO) e il resto
resta scoperto. Il banco NON simula INVALID_PROFIT_RATIO (`minimi_banco` solo taglia), quindi
nei replay la sequenza a 1,01 risultava riuscita: il difetto era invisibile.

Chi usa il place-and-trim nel tennis: scalper (`_place_exact`), pro / FLB / swing
(`UsciteEsatte`, via `_place(..., copertura=True)`), green-up del worker tennis
(`tennis_live_order_worker._uscite_esatte_di` -> `UsciteEsatte`). **safe_tennis NON e' toccato**:
il suo place-and-trim passa da `place_submin_live` / coda `place_submin` -> `submin.
pianifica_submin`, che usa GIA' `quota_parcheggio_lontano` (submin.py:726); il motore tennis
rifiuta `place_submin` (`esecutore_tennis.MOTIVO_SUBMIN`).

## 2. Cosa ho cambiato (file:riga nel worktree)

1. `Betfair/stream/tennis_scalper/condotta_ordini.py`
   - :75 import `place_min_size, quota_parcheggio_lontano` da `trading/submin`.
   - :171 `stato_parcheggio(side, price, target, note)`: gemello tennis di
     `scalper_bot.stato_parcheggio` (non importato dal calcio: calcio e tennis non si
     mischiano, e lo scalper calcio e' il perimetro di C15). Chiama SOLO le funzioni di submin:
     `placed_size = place_min_size("it", lato)`, `park_price = quota_parcheggio_lontano(lato,
     target)`, `serve_replace=True`; None se la quota non c'e'.
   - :200-215 `QUOTE_PARCHEGGIO_LAY` (calcolate da `quota_parcheggio_lontano` sui resti
     0,50..0,99 = `FLOOR_PLACE_AND_TRIM`..`place_min_size` escluso: oggi (1,01, 1,02, 1,03)),
     `QUOTA_PARCHEGGIO_LAY_ALTA` (1,03), `QUOTA_PARCHEGGIO_BACK` (1000). Nessun numero a mano.
   - :404 `UsciteEsatte._dichiara_resto`: il blocco di dichiarazione del resto (gia' esistente
     nel ramo «sotto il floor») spostato tale e quale in un metodo, per riusarlo.
   - :439-454 `piazza`: lo stato della sequenza viene da `stato_parcheggio`; se None ->
     NESSUN ordine, attivita' `uscita_esatta_senza_parcheggio` (CRITICAL, lato, scoperto,
     nota) e resto dichiarato come quello sotto il floor. :471 `state = stato`.
2. `Betfair/stream/tennis_scalper/tennis_scalper_bot.py`
   - :72, :80 import `QUOTA_PARCHEGGIO_LAY_ALTA`, `stato_parcheggio` da `condotta_ordini`.
   - :2229-2232 `_drive_flatten`: il parcheggio si riconosce con `p <= QUOTA_PARCHEGGIO_LAY_ALTA
     + 0.001` (prima `p <= 1.011`). **Necessario**: senza, un parcheggio LAY a 1,02/1,03 in
     sequenza veniva preso per un flatten stantio e ANNULLATO (mutazione M3: il caso CP4 del
     07/10 non si chiude piu'). Struttura della condizione invariata (sequenza in corso o
     REPLACING), come per 1,01.
   - :2656-2668 docstring + import (`FlumineSubminOps, quota_parcheggio_lontano`).
   - :2701-2713 `_place_exact`: nessuna quota sicura -> nessun ordine, resto ricordato e
     dichiarato come sotto il floor (`slot.resto_np`, `residual_ok`, `min_bet_skip` con
     `motivo`).
   - :2749 `state = stato_parcheggio(side, price, rest, note="exact exit")`.
3. `Betfair/stream/tennis_live/certificazione_bot.py` (banco tennis)
   - :53 import `QUOTA_PARCHEGGIO_LAY_MAX` (tetto dichiarato del parcheggio lontano, 1,20).
   - :225-231 `_QUOTA_PARCHEGGIO` = BACK (1000,), LAY `CD.QUOTE_PARCHEGGIO_LAY`;
     `_quota_di_parcheggio`. B8 riconosce la catena legittima con il parcheggio nella banda.
   - :267 `_quota_parcheggio_attesa` (memoizzata), :275 `parcheggio_di(ordine)`: dal BLOTTER
     (non dalle attivita' del bot) il parcheggio RIDOTTO (BACK >= 999 o LAY 1,00-1,20, size >=
     minimo, `size_cancelled` > 0), il resto (size del rimpiazzo nello stesso Trade, oppure
     size - size_cancelled se il parcheggio e' vivo in attesa del rimpiazzo) e la quota attesa.
   - :354 `riga_ordine` porta la chiave `parcheggio` (None per ogni altro ordine).
   - :864-890 **nuovo controllo B11** (quando = c'e' un parcheggio ridotto fra gli ordini):
     la quota del parcheggio DEVE essere `quota_parcheggio_lontano(lato, resto)`; quota diversa
     = violazione; quota attesa None (nessuna quota sicura) = violazione «l'ordine non doveva
     partire». Controlli attivi del banco tennis: 22 -> 23.
4. Test
   - NUOVO `Betfair/stream/tennis_live/tests/test_cantiere5_parcheggio_tennis_2026_10_08.py`
     (57 test, bot VERI sul runner paper vero del banco dell'iscrizione a caldo, esecuzione
     simulata sincrona; finti solo dove gia' esistevano con le chiavi del vero):
     tabella 0,50/0,70/0,79/0,80/0,99 -> 1,02/1,03/1,03/1,01/1,01 (e BACK 1000) per
     `stato_parcheggio`, pro, FLB, swing (ordine VERO a mercato) e scalper (stato + ordine VERO
     dopo `_drive_submins`); sequenza completa pro/FLB/swing con B8 verde e B11 sollecitato
     verde; flusso CP4 dello scalper (flatten 0,60 -> parcheggio 1,02, rimpiazzo avvenuto,
     B8/B11 verdi); falsificazione «parcheggio a 1,01 con resto 0,70» (condotta di prima
     iniettata) -> B11 ROSSO; parcheggio tagliato in attesa del rimpiazzo giudicato; senza
     quota sicura: nessun ordine + riga CRITICAL + resto dichiarato (UsciteEsatte e scalper),
     B11 rosso; B8 riconosce 1,01/1,02/1,03 e non 1,04/1,10.
   - ADATTATO `test_scalper_tennis_cp4_parcheggio_2026_10_07.py`: il test del 07/10 fissava il
     parcheggio LAY del resto 0,60 a 1,01; ora 1,02 = `quota_parcheggio_lontano("lay", 0.6)`
     (motivo scritto nel test). Nessun altro test esistente cambiato.

**Non cambiato** (ordine «Non fare»): quando e quanto si chiude, `spezza_esatta`, la sequenza
place-and-trim (`advance_submin`), TTL, anti-cascata (30 s, tetto 5, raddoppio), soglie, stake.
Solo quota e importo del parcheggio, dalla fonte unica.

## 3. Test e numeri VERI (container cloud, 4 CPU condivise con altri cantieri)

| comando | prima (b5547eb) | dopo |
|---|---|---|
| `pytest Betfair/stream/tennis_live/tests Betfair/stream/tennis_scalper/tests -q -p no:cacheprovider` | 1055 passed, 4 skipped, 5 xfailed, 63,6 s (`test_tennis_prima.txt`) | 1112 passed, 4 skipped, 5 xfailed, 69,1 s (`test_tennis_dopo.txt`; +57 = i test nuovi) |
| `pytest Betfair/ -q -p no:cacheprovider` | 1 failed, 10758 passed, 87 skipped, 6 xfailed, 468,8 s (`suite_python_prima.txt`) | 2 failed, 10814 passed, 87 skipped, 6 xfailed, 502,4 s (`suite_python_dopo_completa.txt`) |

I rossi sono SOLO misure di latenza su macchina carica, nessun legame col cantiere (non
importano nessun file toccato): PRIMA `test_motore_ordini_2026_09_24.py::
test_latenza_logica_comando_place_sotto_20_ms` (p95 20,05 ms contro 20,0); DOPO lo stesso (24,1 ms)
e `test_auto_follow_2026_09_25.py::test_latenza_logica_aggancio_sotto_i_20_ms` (20,16 ms).
Rilanciati da soli: auto_follow VERDE, motore_ordini ancora rosso (lo era anche PRIMA). Conteggio:
prima 10759 test, dopo 10816 = +57 (i test nuovi).
ATTENZIONE: la suite completa DOPO e' partita prima delle ultime tre modifiche (uscita anticipata
per quota in `parcheggio_di`, due commenti resi ASCII, uno spazio in `condotta_ordini`). Dopo quelle
ho rilanciato: suite tennis (1112 passed), `test_registro_bot` + `Betfair/stream/backtest` +
`test_banco_uscite_manuali_n3` + `test_submin_contratto_chiamanti` (155 passed, 1 skipped) e
tutte le mutazioni. La suite completa sul codice finale va rilanciata dal coordinatore.

Frontend: nessun file toccato -> `tsc`/`vitest`/`build` non pertinenti (non lanciati).

## 4. Falsificazione (`mutazioni.py`, esito in `mutazioni_esito.txt`)

`python AUDIT_2026-10-08/cantiere_5/mutazioni.py .` applica ogni mutazione, lancia i test del
cantiere + il test CP4, ripristina e verifica lo sha del file.

| mutazione | rossi |
|---|---|
| M1 `stato_parcheggio` con quota `initial_place_price` (condotta di prima) | 25 |
| M2 importo del parcheggio 2,00 a mano | 44 |
| M3 flatten scalper con soglia 1,011 | 3 (flusso CP4 x2 latenze + flusso B11) |
| M4 scalper senza ramo «nessuna quota» | 1 |
| M5 UsciteEsatte senza ramo «nessuna quota» | 2 |
| M6 B11 spento | 2 |
| M7 B8 riconosce solo 1,01 | 6 |
| M8 resto del parcheggio vivo = size | 1 |
| M9 B11 con tolleranza 0,05 | 1 |
| M10 banda LAY calcolata male (solo 1,01) | 9 |

Ripristino: sha IDENTICO dopo ogni mutazione (righe «ripristino» in `mutazioni_esito.txt`).
Sha dei file PRIMA in `sha_prima.txt`; sha DOPO in `sha_dopo.txt`.

## 5. Prestazioni

- Test tennis: prima 63,6 s, dopo 69,1 s (macchina carica, 57 test in piu').
- Costo del banco per giro (`riga_ordine` + `verifica`, la parte toccata), `misura_riga_ordine.py`,
  minimo di 7 misure alternate: blotter realistico (100 ordini, 2 catene) PRIMA 1,763 / DOPO 1,773 ms per giro (+0,6 %, nel rumore); blotter denso (100 ordini, 20 catene place-and-trim tutte tagliate) PRIMA 1,616 / DOPO 1,935 ms (+19,7 %, +0,3 ms per giro) (`misura_riga_ordine_esito.txt`). Il costo in piu' e' solo sui parcheggi ridotti (attraversamento del Trade): dichiarato, da confermare sul PC con `TEMPO TOTALE` dei replay. Il rischio era la nuova chiave `parcheggio`
  calcolata per ogni ordine a ogni giro: `parcheggio_di` esce al primo confronto di quota per
  ogni ordine che non sta a 1,00-1,20 o >= 999, la quota attesa e' memoizzata.
- Tempo dei replay: NON misurabile qui (nessuna registrazione tennis). Sul PC: confrontare le
  righe `TEMPO TOTALE` prima/dopo (sezione 6).

## 6. Replay: NON eseguiti qui -> DA RIESEGUIRE SUL PC

Nel container ci sono solo le registrazioni calcio. Le registrazioni tennis (35790089,
35794049) stanno sul PC in `tennis_rec`. Nessun «conforme» a vuoto: la prova di non
regressione del cantiere va fatta sul PC.

Comandi (PowerShell, radice del repo; PRIMA = `b5547eb`, DOPO = questo lavoro):

```
$D = "C:\Users\Admin\Desktop\tennis_rec\20260707"
$O = "AUDIT_2026-10-08\cantiere_5"
foreach ($b in "tennis_scalper","tennis_pro","tennis_flb","tennis_swing","safe_tennis") {
  python -m Betfair.stream.backtest.certifica $b 35790089 --data-dir $D --scenari tutti --worker 1 *> "$O\${b}_35790089_<prima|dopo>.txt"
}
foreach ($b in "tennis_pro","tennis_scalper") {
  python -m Betfair.stream.backtest.certifica $b 35794049 --data-dir $D --scenari tutti --worker 1 *> "$O\${b}_35794049_<prima|dopo>.txt"
}
```
Confronto: `diff` dei referti escluse le righe `tempo:`, `TEMPO TOTALE`, `codice bot`.

ATTESO (e solo questo):
1. `controlli attivi: 22` -> `23` e una riga nuova `B11 xN` nella copertura (tutti e quattro i
   bot tennis; per safe_tennis nessuna differenza: banco e bot diversi). Se un bot non fa mai
   un place-and-trim con taglio su quella partita, B11 compare fra i «MAI SOLLECITATI»
   (`?? B11 x0`, 3 -> 4 mai sollecitati): e' un «non lo so», non un «sano».
2. 0 violazioni, prima e dopo.
3. Le quote dei parcheggi LAY con resto 0,50-0,79: 1,01 -> 1,02 (0,50-0,62) o 1,03 (0,63-0,79),
   dove il referto le mostra (righe di attivita' `submin_*`/`uscita_esatta_*`, JSON).
4. tick, decisioni, azioni, stati, esiti, netti IDENTICI. Unica eccezione possibile e
   spiegabile: lo stesso parcheggio a quota piu' alta di 1-2 tick. A 1,02/1,03 non si abbina
   nelle registrazioni note (il mercato non scambia a quelle quote); se una riga cambia per
   questo, va elencata col parcheggio che la causa.

Se compare una differenza NON spiegata da questo elenco -> cantiere fermo, reperto.

## 7. Limiti dichiarati e reperti

1. **Replay tennis non eseguiti** (sez. 6). La copertura qui e' dei test sui bot VERI nel
   runner paper vero (stessa catena flumine), non della registrazione.
2. **REPERTO fuori perimetro - `Betfair/stream/backtest/uscite_manuali.py:63` `e_parcheggio`**:
   riconosce il parcheggio SOLO a `initial_place_price` (BACK 1000, LAY 1,01). Con il parcheggio
   LAY a 1,02/1,03 (tennis da questo cantiere, calcio GIA' dal 07/10) negli scenari
   `uscite-manuali` / `uscite-manuali-firmate` UF2 (a) non aggancia i rimpiazzi della catena
   nati dopo la finestra di 5 s e (b) conta il residuo del parcheggio vivo come importo
   d'uscita: possibile UF2 falso rosso (o falso verde) su un'uscita firmata il cui resto e'
   0,50-0,79 di banca. Il file e' del banco COMUNE (calcio e tennis) e non e' nel perimetro del
   cantiere 5: non toccato. Correzione proposta (una riga, per il coordinatore): in
   `e_parcheggio`, per la LAY accettare `prezzo <= max(quota_parcheggio_lontano("lay", c/100)
   for c in range(50, 100))` (oggi 1,03) invece della sola 1,01; per la BACK invariato. Va
   falsificata con un parcheggio LAY a 1,03 in UF2. Se sul PC UF2 cambia nei due scenari
   manuali, la causa e' questa.
3. **CP4 del banco comune** (`chiusura_parziale.py:625` `_cap`) conta il parcheggio LAY come
   capacita' `1,00 x quota`: 1,02/1,03 al posto di 1,01 = +0,01/+0,02. Un CP4 «sovrarichiesta»
   al margine potrebbe comparire nello scenario `chiusura-abbinata-in-parte`; sarebbe
   spiegato da questo (il parcheggio e' lo stesso, 1-2 tick piu' su). Non toccato.
4. Il caso «nessuna quota sicura» oggi non accade per nessun resto 0,50-0,99 (tabella
   completa in `test_quote_del_parcheggio_lay_dalla_fonte_unica`): il ramo e' la guardia, coperto
   solo da test con la fonte forzata a None.
5. B11 giudica il parcheggio solo DOPO il taglio (prima del taglio il resto non e' leggibile dal
   blotter). Un parcheggio piazzato e mai tagliato non e' giudicato (la sequenza si e' fermata:
   lo giudicano K5/K6).

## 8. Decisioni per l'utente

- Nessuna decisione di trading cambiata: stessa sequenza, stessi momenti, stessi importi
  d'uscita; cambia solo la quota del parcheggio LAY per i resti 0,50-0,79 (1,01 -> 1,02/1,03),
  che con 1,01 Betfair avrebbe rifiutato al taglio.
- Da decidere col coordinatore: il reperto 7.2 (`uscite_manuali.e_parcheggio`, banco comune,
  vale anche per il calcio dal 07/10).

## Blocco per la cronostoria

```
### 08/10 - Cantiere 5: parcheggio del place-and-trim nei bot tennis (delegato cloud)
- Partenza b5547eb. Fonte unica: `condotta_ordini.stato_parcheggio` (place_min_size +
  quota_parcheggio_lontano, come `scalper_bot.stato_parcheggio` del calcio) per scalper tennis
  (`_place_exact`), pro/FLB/swing e green-up del worker (`UsciteEsatte`). LAY 0,50 -> 1,02,
  0,70/0,79 -> 1,03, 0,80/0,99 -> 1,01; BACK 1000; nessuna quota sicura -> nessun ordine,
  riga CRITICAL, resto dichiarato. safe_tennis gia' conforme (pianifica_submin), non toccato.
- Scalper tennis: il flatten riconosce il parcheggio fino a 1,03 (prima 1,011: un parcheggio
  a 1,02 veniva annullato come flatten stantio, mutazione M3).
- Banco tennis: B8 riconosce la catena nella banda 1,01-1,03; nuovo B11 (quota del
  parcheggio = quota_parcheggio_lontano del resto; senza quota = violazione). 22 -> 23 controlli.
- Test: nuovo test_cantiere5_parcheggio_tennis_2026_10_08.py (57), adattato il CP4 del 07/10
  (1,01 -> 1,02). Mutazioni M1-M10 tutte rosse, sha ripristinati.
- Suite: prima 1 rosso / dopo 2 rossi, solo latenze <20 ms su macchina carica (10759 -> 10816 test). Replay tennis DA RIESEGUIRE SUL PC (referto sez. 6).
- Reperto aperto: `backtest/uscite_manuali.e_parcheggio` riconosce solo LAY 1,01 (UF2; vale
  anche per il calcio dal 07/10). Referto: AUDIT_2026-10-08/cantiere_5/REFERTO.md.
```

## Verifica del coordinatore cloud (08/10)
- Diff riletto (4 file): fonte unica `stato_parcheggio` (stessi default di `SubminState`, `serve_replace=True` come il calcio);
  `placed_size` passa da `IT_BACK_MIN_STAKE` a `place_min_size(lato)` (oggi 1,00 per entrambi: nessuna differenza di importo).
- Test rilanciati nel checkout integrato: `tennis_live/tests` + `tennis_scalper/tests` 1112 verdi, 4 saltati, 5 xfail.
- MIE MUTAZIONI: M1 B11 cieco alla quota -> 1 rosso; M2 parcheggio fisso a 1,01 -> 37 rossi; M3 soglia del flatten 1,011 -> 3 rossi;
  M4 bersaglio del parcheggio di `UsciteEsatte` sbagliato -> 3 rossi. Ripristino verificato (diff identico).
- Reperto 7.2 (`backtest/uscite_manuali.e_parcheggio` solo LAY 1,01): assegnato al cantiere 9 (banco scalper) con replay prima/dopo.
- Replay tennis prima/dopo: DA RIESEGUIRE SUL PC (registrazioni assenti nel cloud), comandi e attesi alla sez. 6.
