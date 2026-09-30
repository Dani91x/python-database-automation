# MIKE - la banca al fischio resta a mercato 3 minuti (30/09/2026)

Cantiere del delegato (worktree `agent-ae68615542fdfa2e0`, base master `30917ed`).
Decisione dell'utente del 30/09 15:40 (priorita' assoluta), testuale: «quell'ordine deve
restare a mercato per 3 minuti come da progettazione, SOLO DOPO I 3 minuti, controlla quando
e' stato abbinato (se parziale come in questo caso) RITIRA IL RESTO, e si copre sulla
selezione 4.5 PER L'IMPORTO RIMANENTE SU UNDER 3.5».

Lavoro NON committato. Patch completa: `AUDIT_2026-09-30/MIKE_KO_GREEN_3_MINUTI.patch`
(verificata con `git apply -R --check` sul worktree). Nessun processo avviato, nessun DB
toccato, nessuna build.

## 1. Causa radice (codice di `30917ed`)

Il caso vero (36130526): banca `ko_green` 5,10 @ 2,08, abbinata 1,00 a 15:30:32, residuo
annullato nello stesso secondo, copertura a 15:30:40.

1. **L'annullo nasce nel riallineo di `_decide_ko_green`**, `Betfair/mike/engine.py:3571-3578`
   (HEAD):
   ```python
   vivo = uscita if (uscita is not None and uscita.is_live) else None
   if vivo is not None:
       if abs(float(vivo.price) - float(plan.price)) < 1e-9 and \
               abs(float(vivo.size) - float(plan.size)) < 0.01:     # :3573
           return ... "uscita a +2 tick sul book"
       _annulla(vivo)                                               # :3578
   ```
   `plan = piano_uscita_ko(ctx, params, Pe)` calcola la banca giusta da `exposure(ctx.legs)`,
   che CONTA GIA' l'abbinato della banca stessa. Col caso vero: punta 5,00 @ 2,12, banca 1,00
   abbinata -> piano 4,10; size viva 5,10 != 4,10 -> «la posizione e' cambiata» -> `cancel`.
   Il riallineo era nato per un'altra cosa (il fill del residuo PERSIST, commento a :3576) e
   scattava anche sul parziale della banca stessa. Il servizio si limita a eseguire l'annullo
   deciso dal motore: `Betfair/mike/service.py:4307` (`_esegui_annulli`, motivo
   `cancelled_by_engine`) - nessun annullo nasce in `_segui_resting_live`/`fill_resting`.
2. **La copertura anticipata nasce nel ramo A**, `Betfair/mike/engine.py:3471` e `:3483-3486`
   (HEAD): al giro dopo la banca non e' piu' viva, ha `matched > 0` e la posizione non e'
   piatta -> «fill PARZIALE consolidato» -> `LIVE_UNCOVERED` «uscita al fischio parziale: copro
   il residuo», a qualunque secondo della finestra. Lo stesso ramo copriva subito anche un
   parziale fatto SCADERE da Betfair a una sospensione dentro la finestra (punto 3 della regola).

Riprodotto prima della correzione: `test_parziale_a_30_secondi_resta_a_mercato` rosso con
«uscita appoggiata a 2.08 (lay 'ko_green' rimandata: 'ko_green-0-3' e' ancora viva...)» e
`cancel ['ko_green-0-3']`; il ciclo vero del servizio
(`test_servizio_parziale_al_fischio_resta_fino_allo_scadere`) rosso a 29 s con la gamba gia'
`open` (annullata); sul banco, codice di oggi = KG1 x2 «residuo della banca 'ko_green-0-3'
(4.04 su 10.12) annullato a 6 s dal fischio» (vedi par. 5).

## 2. Cosa cambia (modifica minima)

`Betfair/mike/engine.py` (solo `piano_uscita_ko` e `_decide_ko_green`):
- `piano_uscita_ko(..., legs=None)`: parametro opzionale per calcolare il piano SENZA una gamba.
- riallineo (:3598 ora): la banca viva si confronta col piano calcolato **senza il suo stesso
  abbinato** (`legs=[l for l in ctx.legs if l is not vivo]`). Un suo parziale non la tocca
  piu'; un fill di un'altra gamba (residuo PERSIST) la fa ancora riallineare come prima.
- ramo A (:3479-3482): il parziale NON vivo copre solo se la finestra e' scaduta
  (`finestra_uscita_scaduta`); dentro la finestra si scende al piazzamento e si riappoggia
  la banca per il RESIDUO (l'esposizione conta gia' il parziale). Tutta abbinata -> FLAT
  come prima.
- ramo B (finestra scaduta): stesso annullo e stessa copertura di prima; cambia solo il
  motivo scritto quando la banca e' abbinata in parte («uscita al fischio abbinata in parte
  (x su y) in 3': ritiro il resto, copro il residuo») e la telemetria `ko_green.abbinato`.

Invariati: prezzo (2 tick sotto l'ingresso), finestra 180 s e suo orologio (non scorre a
mercato non appoggiabile), strada C (gol precoce: annullo + seconda puntata), esito ignoto,
mercato chiuso, J5 (mai due lay), la copertura (forma di serie banca Under 4,5, dimensionata
su `under_liability`, che e' gia' al netto della banca abbinata: verificato, 4,00 x 1,2 / 0,95
= 5,05 nei test e nel banco 5,96 x 1,2 / 0,95 = 7,53). L'annullo allo scadere e' confermato
come oggi (`_mark_trade_cancelled` sincrono prima del giro della copertura).

Parita' paper/live: la modifica e' solo nel motore puro (`engine.decide`), che e' lo stesso
per paper e live; nessun ramo per modalita'. Il test sul ciclo vero gira in paper sul runner
finto (protocollo vero); il banco sul canale.

## 3. Banco

- `Betfair/mike/certificazione.py`: controllo nuovo **KG1** «la banca al fischio abbinata in
  parte resta a mercato fino allo scadere della finestra; il residuo si annulla solo dopo, e
  la copertura vale il rischio residuo (ordine dell'utente 30/09)». Ha il caso quando la
  banca al fischio e' abbinata in parte (in `LIVE_KO_GREEN`) o quando si piazza la copertura
  dopo una banca al fischio abbinata. Rosso se: annullo della banca parziale viva prima dei
  180 s (senza gol, mercato non chiuso, posizione d'ingresso invariata: conto proprio,
  `netto/prezzo`); passaggio a `LIVE_UNCOVERED` prima dei 180 s; copertura banca Under 4,5
  oltre `(1,2 x rischio residuo - gia' coperto) / 0,95` (rischio residuo calcolato dalle
  gambe, non con `under_liability`).
- `Betfair/stream/backtest/chiusura_parziale.py`: parametro opzionale `bersaglio` del guasto
  comune (assente = identico a prima per tutti i bot): colpisce solo le chiusure indicate.
- `Betfair/mike/tools/replay_registrazioni.py`: scenario **`ko-green-parziale`** (nessun
  parametro cambiato): il guasto `chiusura-abbinata-in-parte` con spinta dichiarata colpisce
  SOLO la banca al fischio (`e_banca_al_fischio`: dalla riga `mike_trades` via `mike-t<id>`
  sulla coda; sul canale l'ordine porta `awlq<id>` del runner e la riga si riconosce dalla
  stessa domanda mercato/selezione/lato/prezzo/importo). Contatore-chiave: senza parziale o
  senza KG1 lo scenario e' NON ESERCITATO. Sorveglianza CP accesa come nel CP.

## 4. Test

Ambiente neutro (variabili di `ereditato_29_09/scratchpad_admin_e7/replay_mike.sh`).
- Nuovo `Betfair/mike/tests/test_mike_ko_green_3_minuti_2026_09_30.py`, 16 test, classi vere
  (`E.decide`, `CERT.verifica`, `S.run_once` con `FakeDB`/`FakeMarket` di `test_mike_service`
  e runner finto): parziale a 30 s resta (nessun annullo, `LIVE_KO_GREEN`); parziale a prezzo
  migliore resta; allo scadere annullo + copertura 5,05; non abbinata allo scadere annullo +
  6,32; tutta abbinata a 60 s FLAT; parziale scaduto da Betfair a 60 s -> riappoggio 4,10 @
  2,08; lo stesso a finestra chiusa -> copertura; gol con parziale -> strada C; fill PERSIST
  -> riallineo; ciclo vero del servizio (banca 5,10, parziale 1,00 a 29 s, nessun annullo fino
  a 170 s, annullo a 182 s, copertura banca Under 4,5 5,05); KG1 x4; predicato dello scenario.
  Rossi prima della correzione: 4 su 11 (i 4 dei parziali dentro la finestra), gli altri sono
  guardie contro la correzione eccessiva (falsificate sotto).
- **Test esistenti aggiornati** (fissavano la copertura anticipata o usavano il parziale della
  banca come veicolo):
  - `test_mike_flusso_fischio_2026_09_13.py::test_strada_A_fill_parziale_copre_solo_il_residuo`:
    voleva la copertura del parziale a 60 s dal fischio; ora la guarda allo scadere della
    finestra (stessa asserzione sul residuo).
  - `test_mike_ko_green_appoggiata_2026_09_16.py::test_sostituire_una_lay_viva_emette_SOLO_l_annullamento`
    e `::test_con_l_annullamento_FALLITO_nessuna_lay_nuova_e_si_ritenta`: provano J5 (mai due
    lay nello stesso giro); il veicolo era il parziale 8,15/10,14 della banca, che ora NON la
    fa riallineare. Veicolo nuovo: un cambio vero di posizione (residuo PERSIST abbinato a
    1,60, stesso del test gemello `..._CONFERMATO_...`). Asserzioni J5 invariate.
- Suite `Betfair/mike`: **1367 passati** (riferimento 1351 + 16 nuovi), 0 falliti, 61 s.
- `Betfair/stream/tests/test_banco_mike_ondata2_2026_09_30.py`, `test_chiusura_parziale_2026_09_23.py`,
  `test_cp1_campi_non_scritti_2026_09_23.py`, `test_registro_bot_2026_09_16.py`: 56 passati.

## 5. Falsificazioni

Script `AUDIT_2026-09-30/ko_green_3_minuti/falsifica_ko_green_3_minuti.py`, esito in
`falsifica_ko_green_3_minuti.out`: 14 mutazioni, **14 ROSSO come atteso**, `MUTAZIONE` rimaste
0, 19 test verdi dopo il ripristino, `git diff` identico byte per byte a prima.
M1 riallineo sul piano col parziale (codice di oggi) · M2 parziale non vivo copre subito
(codice di oggi) · M3 nessun annullo allo scadere · M4 mai riallineo · M5 finestra mai
scaduta · M6 gol ignorato · M7 tutta abbinata non FLAT · M8 copertura sullo stake lordo ·
M9 J5 spento (i due test aggiornati) · K1 KG1 cieco · K2 KG1 accusa il riallineo legittimo ·
K3 KG1 non guarda l'importo · P1/P2 predicato dello scenario.

Falsificazione del BANCO sul codice di oggi: `engine.py` riportato a HEAD
(`git checkout --`), scenario `ko-green-parziale` -> **KO, KG1 x2** («residuo della banca
'ko_green-0-3' (4.04 su 10.12) annullato a 6 s dal fischio, prima dello scadere dei 180 s»,
seconda: copertura dentro la finestra), P&L -8,60. Ripristino con `git apply --include`
dalla patch salvata; `git diff --stat` identico a prima. Referto:
`ko_green_3_minuti/mike_ko_green_parziale_CODICE_DI_OGGI.txt`.

## 6. Replay singoli (35760084, canale, worker 0, uno alla volta)

| scenario | esito | tempo | confronto |
|---|---|---|---|
| `base` | OK, 0 violazioni | 130 s | sezione del referto **identica riga per riga** a `replay/mike_tutti_FINALE.txt` (tolta la riga del tempo): stessi 5861 decisioni, 6 azioni, P&L -14,17. Unica differenza nel referto: il controllo nuovo KG1 compare in copertura come `?? x0` (qui la banca al fischio non si abbina mai), «controlli attivi» 47 invece di 46 |
| `chiusura-abbinata-in-parte` | OK, 0 violazioni | 101 s | identica a FINALE (colpita la banca pre-partita 10,12 -> 4,04, P&L -8,44); la sola riga in piu' e' la nota NON ESERCITABILE `ht_ft_rows`, che in FINALE mancava perche' con `--worker 3` il processo l'aveva gia' in memoria da uno scenario precedente (non dipende da questo lavoro) |
| `ko-green-parziale` | **OK**, 0 violazioni, KG1 x72 sollecitato | 104 s | banca al fischio 10,12 @ 1,69 colpita: 4,04 abbinati, residuo 6,08 scaduto da Betfair alla sospensione -> riappoggiato 6,08 (regola 3) -> allo scadere copertura banca Under 4,5 **7,53** = 5,96 x 1,2 / 0,95. P&L -8,44 |
| `ko-green-parziale` sul codice di oggi | **KO**, KG1 x2 | 103 s | vedi par. 5 |

Referti in `AUDIT_2026-09-30/ko_green_3_minuti/mike_*.txt`. Tempi: il primo giro dello
scenario nuovo (prima della correzione del predicato, guasto senza effetto) ha fatto 56,7 s,
come i 48,7 s di FINALE; i 100-130 s degli altri giri li attribuisco al PC condiviso (altri
processi Python attivi nello stesso momento), non al controllo nuovo, che costa un confronto
per decisione - non l'ho dimostrato con un profilo.

## 7. Cosa NON ho fatto / NON ho potuto verificare

- Non ho profilato il tempo del replay: i tempi variano 57-130 s col carico del PC; tutti
  sotto il tetto di 10 minuti per scenario singolo, ma la «tutti gli scenari in 5 minuti»
  non l'ho misurata (non richiesta: solo scenari singoli).
- Non ho rilanciato `--scenari tutti`. La registrazione 36130526 NON e' in `_live_raw`
  (81 cartelle, verificato): il caso vero e' riprodotto coi suoi numeri nei test unitari e
  nel ciclo vero del servizio, non su un replay di quella partita.
- Reperto non corretto (fuori perimetro): sul CANALE `chiusura_parziale.ruolo_da_righe` non
  legge il ruolo (l'ordine porta `awlq<id>`, non `mike-t<id>`) e il guasto ripiega sul verso
  del mercato; per lo scenario nuovo l'ho aggirato col confronto della domanda, non ho
  toccato la funzione comune (cambierebbe gli altri scenari).
- Il file `replay_registrazioni.py` nel worktree ha fine riga LF (le altre copie di lavoro
  CRLF, repo LF): `git diff` e' pulito, la patch e' normalizzata.
- Esito ignoto dell'annullo allo scadere: resta il comportamento di oggi (la gamba va in
  riconciliazione e conta nel rischio); non ho aggiunto casi.

## 8. Decisioni per l'utente

Nessuna nuova: la regola e' quella ordinata. Da sapere: dentro la finestra, se Betfair fa
scadere il residuo a una sospensione (non gol), Mike riappoggia la banca per il RESIDUO
(punto 3 della regola) - prima copriva subito.

## 9. Da controllare dal vivo (paper, prossimo avvio)

Su una partita con banca al fischio abbinata in parte: nessun `cancel` della `ko_green` in
`mike_activity` prima di 180 s dal fischio; allo scadere un solo `cancel` con esito `open`
(abbinato conservato), poi `cover` sul mercato Under 4,5 con importo = rischio residuo
Under 3,5 x 1,2 / 0,95; motivo della decisione «uscita al fischio abbinata in parte (x su y)
in 3': ritiro il resto, copro il residuo».

## File

Modificati: `Betfair/mike/engine.py`, `Betfair/mike/certificazione.py`,
`Betfair/mike/tools/replay_registrazioni.py`, `Betfair/stream/backtest/chiusura_parziale.py`,
`Betfair/mike/COSTITUZIONE_MIKE.md` (par. 15.2, una frase),
`Betfair/mike/tests/test_mike_flusso_fischio_2026_09_13.py`,
`Betfair/mike/tests/test_mike_ko_green_appoggiata_2026_09_16.py`.
Nuovi: `Betfair/mike/tests/test_mike_ko_green_3_minuti_2026_09_30.py`,
`AUDIT_2026-09-30/MIKE_KO_GREEN_3_MINUTI.md`, `AUDIT_2026-09-30/MIKE_KO_GREEN_3_MINUTI.patch`,
`AUDIT_2026-09-30/ko_green_3_minuti/` (script di falsificazione e sonde, referti dei replay).
