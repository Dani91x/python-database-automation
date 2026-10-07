# CONFORMITA' AL PROGETTO DEI BOT CALCIO — audit del 07/10/2026

Delegato Opus. Worktree `/home/user/python-database-automation/.claude/worktrees/agent-a6c634efabc0dda44`
(base `8226d766`, lavoro NON committato). Ordine dell'utente (07/10): «non voglio regressioni, e i
bot tutti devono lavorare come progettati», «fixa tutto quello che incontri».

Registrazioni (`/home/user/python-database-automation/_live_raw`, entrambe COMPLETE):
- **35797769** Spagna-Belgio (Mondiali, quarti, 10/07): 1-0 al 30', 1-1 al 41', 2-1 all'88' (finale 2-1).
  Pre-partita registrato: 149 min. 1X2 pre-KO: Spagna 1,65-1,68, Belgio 6,2-6,4.
- **35760084** Liepaja-Ogre (Virsliga, 30/06): 1-0 all'8', 2-0 al 28', 3-0 al 45+1', 4-0 al 63'.
  Pre-partita registrato: 55 min. 1X2 pre-KO: Liepaja 1,36-1,39, Ogre 9,2-10,5.

Esclusi dal brief: Omega, modalita' media under dello scalper.

## 0. In una riga

**Nessun BUG di strategia trovato nel codice di Mike, Safe (base/esatto/punta), Scalper maker e
Sniper sulle due partite: ogni ingresso, non-ingresso e uscita osservati coincidono con la
specifica + le decisioni dell'utente.** Trovati: 1 difetto del BANCO di Safe (il regolamento non
e' mai esercitato: patch pronta, file fuori perimetro), 2 lacune di copertura (Mike mai
certificato sulla 35797769; Safe mai sulla 35797769), 2 documenti disallineati dal codice
(corretti), 3 dubbi di progetto per l'utente (minuti del recupero del 1° tempo; residui dello
Scalper che fanno scattare il tetto di perdita), 1 testo fuorviante dello Scalper (patch nel
referto). Nessuna modifica al codice di produzione: nessun replay «prima/dopo» dovuto.

## 1. Tabella bot x partita x condizione

Legenda verdetto: **OK** = fa cio' che la spec prevede; **SCELTA** = comportamento voluto da una
decisione scritta; **DUBBIO** = da decidere all'utente (sez. 7); **BANCO** = difetto del banco.

### Safe BASE (lay della sfavorita sul 1X2; `engine.evaluate_base`, `engine.py:1161`)
| partita | condizione (spec) | prevista | presente nei dati | fatto dal bot | verdetto |
|---|---|---|---|---|---|
| 35797769 | favorita pre 1,40-1,80 / sfavorita 4-8 (cost. §2, `pre_bands_checks`) | si' | Spagna 1,65-1,68, Belgio 6,2-6,4: SI' | favPre/dogPre ok | OK |
| 35797769 | dal 55', favorita avanti 1-0/2-1/2-0 | si' | dal 55' all'87' 1-1 (NO); 2-1 solo dall'88' | `score:no` x2788 | OK |
| 35797769 | banca sfavorita 20-34 (Q1 25/09) | si' | dopo il 2-1 Belgio in banca 420-1000+ (NO) | `dogLay:no` x3518 | OK |
| 35797769 | nessun ingresso al minuto di uscita (80') o dopo (Q8) | si' | il 2-1 arriva all'88' | 0 ordini | OK (doppio no) |
| 35760084 | bande pre-partita | si' | Liepaja 1,36-1,39 < 1,40; Ogre 9-10,5 > 8 (NO) | `favPre:no`/`dogPre:no` x3046 | OK |
| 35760084 | punteggio dal 55' | si' | 3-0 e 4-0 (NO) | `score:no` | OK |
| **esito** | | | | **0 ordini su entrambe** | **OK** |

### Safe PUNTA (back della favorita avanti; `engine.evaluate_punta`, `engine.py:1352`)
| partita | condizione | presente nei dati | fatto | verdetto |
|---|---|---|---|---|
| 35797769 | dal 66', 2-0/3-1/3-0 | dal 66' 1-1 poi 2-1 (NO) | `score:no` x3387, `leadFav:no` | OK |
| 35760084 | bande pre-partita (Q10: quelle della BASE) | favorita 1,36-1,39 (NO) | `favPre:no` x3046 | OK |
| 35760084 | dal 66', 2-0/3-1/3-0 | dal 63' 4-0 (NO); 3-0 solo fra il 45+1' e il 63' (<66') | `score:no` | OK |
| **esito** | | | **0 ordini su entrambe** | **OK** |

### Safe ESATTO (lay «Altro risultato» sul Correct Score; `engine.evaluate_esatto`, `engine.py:1258`)
| partita | condizione | presente nei dati | fatto | verdetto |
|---|---|---|---|---|
| 35797769 | dal 48', 0-0/1-0/1-1/2-1, lato bancato <=1 gol | 1-1 dal 46' all'87': SI' | segnale | OK |
| 35797769 | banca «Altro risultato Casa» (9063254) 30-70 | 30 al 66', 30-32 fino al 70', 36-70 dal 71' | **1 ordine: banca 2,00 @ 32,0**, abbinata per intero (liability 62) | OK |
| 35797769 | «Altro risultato Ospite» 30-70 | 85-890, mai in banda | nessun ordine | OK |
| 35797769 | un solo lato per partita (E7), dedup `signal_key` | 338 segnali | 1 ordine | OK |
| 35797769 | nessun ingresso dal 72' (Q8) | banda ancora valida 72'-77' | `minuto_ingresso_oltre_uscita` x2 | OK (SCELTA Q8) |
| 35797769 | uscita a tempo al 72' (cost. §3) | 72', lato bancato senza gol | decisione `time` dal 72'; PROPOSTA all'utente (uscite manuali di serie) | OK / SCELTA (25/09 sera) |
| 35797769 | uscita in perdita se segna il lato bancato | Spagna segna il 2-1 all'87'-88' | decisione `loss lato_bancato_segna` (30 s di assestamento); PROPOSTA all'utente | OK / SCELTA |
| 35797769 | regolamento a mercato chiuso | CS CLOSED, «Altro risultato Casa» LOSER (2-1) | riga rimasta `open` a fine replay | **BANCO** (sez. 2.1) |
| 35797769 | dal 48' anche nel RECUPERO del 1° tempo | il feed segna 46'-50' con `matchStatus=KickOff` (19:46-19:50) | minuto valido per il motore (banca 8,6-10: fuori banda, nessun ingresso) | **DUBBIO D1** |
| 35760084 | punteggio | 2-0 dal 28', 3-0 dal 45+1' (NO) | `score:no` x4110 | OK |
| **esito** | | | **1 ordine sulla 35797769, 0 sulla 35760084 = GIUSTO** | |

Con il regolamento esercitato (patch simulata, sez. 2.1) la riga esce `won`, P&L **+1,90** netto =
P&L del banco (+2,00 lordi, commissione 0,10): il codice di regolamento della Safe e' corretto.

### MIKE (Under 3,5 pre-KO + copertura Under 4,5 in banca; `engine.py`)
| partita | condizione (cost. §3 + piano 29/09) | presente nei dati | fatto | verdetto |
|---|---|---|---|---|
| 35797769 | finestra KO-60' / KO-10' (15/09: 1 h) | registrazione da KO-149' | `fuori finestra` x2388 prima | OK |
| 35797769 | back Under 3,5 1,30-3,00, liquidita' al best >= 10, spread <= 6 tick | 1,44-1,47; al best 1-37 EUR (spesso < 10) | **ingresso ciclo 1: punta 10,00 @ 1,46** | OK |
| 35797769 | banca appoggiata a -2 tick (1,44), mai in perdita pre-partita (M2.2) | Under 3,5 fermo a 1,44-1,47 | banca 10,14 @ 1,44 appoggiata, abbinata dopo il segno dei 10' (HOLD) | OK |
| 35797769 | al segno dei 10' con posizione: nessun altro ingresso (decisione 6 del 29/09, M2.4) | posizione aperta al segno | HOLD, poi «nessuna posizione, aspetto il fischio» x380 | OK / SCELTA |
| 35797769 | KO senza posizione -> IDLE_LIVE -> SETTLED | piatto al fischio | IDLE_LIVE, SETTLED, **+0,13 netti** (regolato dal conto = interno) | OK |
| 35760084 | ingresso, banca non abbinata, HOLD, copertura dopo la finestra di 180 s senza gol (strada B, §15.2) | primo gol all'8' | punta 10 @ 1,71; copertura banca Under 4,5 12,63 @ 1,33 (prezzo < banca Under 3,5: regola 04/10) | OK (referto certificato `AUDIT_2026-10-04/replay/finale_05_10/mike_tutti.txt`) |
| 35760084 | uscite in perdita a modello HT e 46'-85' con 2-4 gol | 3-0 all'intervallo, 4-0 al 63' | `loss_exit_deciso` x3 -> PROPOSTE (uscite manuali di serie), mai eseguite; -14,17 | OK / SCELTA |
| 35760084 | finestra «2t» dal 46' | 45+1' e 46'-47' del recupero del 1° tempo con `matchStatus=KickOff` | `_loss_rule` (`engine.py:4939`) la considera 2° tempo | **DUBBIO D2** |
| 35797769 | idem | recupero del 1° tempo 46'-50' | Mike era piatto: non sollecitato | DUBBIO D2 |

### SCALPER CALCIO — maker pre-partita (solo audit; `scalper_bot.py`)
| partita | condizione (bibbia §2-3) | presente nei dati (campioni ogni 10 s fino a KO-7') | fatto | verdetto |
|---|---|---|---|---|
| 35760084 | quota 1,50-4,6 + >= 300 EUR su ENTRAMBI i best + spread <= 2 tick | 0 campioni su 220 con 300 EUR sui due best, su tutti i 9 runner | 0 azioni, slot sempre IDLE | OK («book morto -> zero operazioni») |
| 35797769 | habitat | Spagna 1X2 660/680 campioni; pareggio 523/680; Under 2,5 105/680 | 167 azioni, 19 cicli chiusi | OK |
| 35797769 | ciclo felice / scratch / stop; missione «1 tick» (`one_green_per_phase`) | — | **0 cicli verdi**, 11 scratch a pari, 2 flatten a 0 al force-flat, 6 cicli chiusi con RESIDUO accettato (-0,195 / 0,00 / -0,1675 / -0,29 / -0,376 / -0,5856) | OK per il codice; vedi **DUBBIO D3** |
| 35797769 | tetto di perdita evento 1,5 -> force-flat (§2.4) | somma dei peggiori esiti dei residui -1,61 | `loss_cap` alle 18:19 (KO-42'), poi nessun ingresso, piatto al fischio | OK / **DUBBIO D3** |
| 35797769 | residuo sotto 0,50 dichiarato e ricordato (decisione 04/10) | 6 residui | 6 `residuo_ricordato` CRITICAL | OK / SCELTA; testo fuorviante (sez. 4) |

### SNIPER (in gioco, S16; `sniper_bot.py`)
| partita | condizione (bibbia §6.2-6.4) | presente nei dati | fatto | verdetto |
|---|---|---|---|---|
| 35797769 | linea Under (gol+1),5 dinamica | 1-0 -> OU25, 1-1 -> OU35, 2-1 -> OU45 | `sniper_lines` OU25 -> OU35 -> OU45 | OK |
| 35797769 | regime + innesco + spread 1 tick -> punta taker; uscita -1 tick, stop 2, timeout 300 s | Under 3,5 2,22 al 46' (recupero del 1° t.), 1,59 al ~60' | fuoco 1: 10 @ 2,22, timeout 300 s, piatto +0,67; fuoco 2: 10 @ 1,59, verde +0,06 | OK |
| 35797769 | primo verde -> evento chiuso | — | `sniper_mission_done` pnl +0,73 | OK |
| 35760084 | idem | non eseguito oggi (lo sniper registrato e certificato solo sulla 35797769) | — | ⊘ (non chiesto dal banco) |

## 2. Reperti del BANCO (file fuori perimetro: patch e proposte)

### 2.1 Regolamento della Safe MAI esercitato nei replay (BANCO, money-critical per la copertura)
- **Prova**: in TUTTI i referti Safe calcio esistenti nessuna riga arriva a `won`/`lost`
  (`grep "righe per stato"` sui referti `AUDIT_2026-09-2*/`, `AUDIT_2026-10-0*/`; Safe base sulla
  35760084: solo `open`/`error`). Sulla 35797769 la banca ESATTO resta `open`, P&L 0,00, mentre
  il banco calcola +2,00.
- **Causa radice** (diagnostica `AUDIT_2026-10-07/strumenti/diag_safe2.py`, uscita in
  `replay_conformita/diag_safe_esatto_35797769_senza_patch.txt`): `settle_open` legge il mercato
  20:59:26-21:09:13 e `MercatoSafe.read_market` risponde SEMPRE `SUSPENDED`, anche dopo il CLOSED
  delle 21:01-21:02. Flumine non consegna i book CLOSED a `process_market_book` ma solo a
  `process_closed_market`; il replay della Safe (`Betfair/safe_strategy/tools/replay_registrazioni.py:1026-1034`,
  classe `SafeCert`) non ha `process_closed_market`, quindi `registra_definizione` non vede mai
  la definizione chiusa coi WINNER/LOSER. Mike ha lo stesso rimedio dal 30/09
  (`Betfair/mike/tools/replay_registrazioni.py:612`).
- **Patch** (NON applicata, file vietato al mio perimetro perche' toccato oggi da un altro
  delegato): `AUDIT_2026-10-07/patch/safe_replay_mercato_chiuso.diff` (10 righe: un
  `process_closed_market` che chiama `self.mercato.registra_definizione`). `git apply --check`
  OK sulla base `8226d766`. **Simulata** (stesso metodo applicato da fuori, `strumenti/diag_safe3.py`):
  lettura CLOSED alle 21:01:38, riga `won`, pnl **+1,90** = banco. Effetto atteso sui referti:
  le righe Safe aperte a fine partita passano a `won`/`lost`; nessun altro numero cambia.
  Da fare dopo l'applicazione: `--scenari tutti` di safe_base sulle due partite e confronto
  (cambiano solo «righe per stato» e i P&L scritti). Non verificato: il tennis della Safe
  (`replay_tennis.py`) potrebbe avere lo stesso buco.
- Non c'e' un controllo che lo avrebbe colto: proposta per il coordinatore un controllo «RG»
  per Safe come `RG1` di Mike (a mercato chiuso ogni riga viva regolata con l'esito del banco).

### 2.2 Copertura delle partite
- **Mike mai certificato sulla 35797769** (solo 35760084 dal 16/09, `CRONOSTORIA.md:1778`). Oggi
  `certifica mike 35797769 --scenari base`: OK, 0 violazioni, 2 azioni, 148 s
  (`replay_conformita/mike_base_35797769.txt`), stati visti WATCH, PRE_ENTRY_PENDING, PRE_OPEN,
  HOLD, IDLE_LIVE, SETTLING, SETTLED; 26 controlli su 50 non sollecitati (la partita non porta
  in gioco nessuna posizione). Proposta: aggiungerla al giro di certificazione di Mike; con 26
  scenari a ~150 s il totale (~65 min) supera il tetto di 600 s: va fatta per gruppi o col
  profilo rapido.
- **Safe base mai certificata sulla 35797769** prima di oggi (nessun referto `BOT: safe_base` che
  la contenga). E' l'unica delle due partite in cui una delle tre strategie entra: senza, la
  certificazione della Safe calcio non ha nessuna posizione viva vera. Proposta: includerla.

### 2.3 La SPEC citata dal banco non e' nel repository
`registro_bot.py` (`spec="SPEC_STRATEGIA_S.md"`) e `certificazione.py` citano un file che non e'
versionato (`AUDIT_2026-09-25/FEDELTA_SAFE_TRASCRIZIONI.md:510`: «resta NON versionato»): fuori dal
PC dell'utente (qui, in cloud) la spec della Safe non esiste. Le condizioni le ho prese da
`COSTITUZIONE_SAFE_STRATEGY.md` §2-3, dalle descrizioni dei controlli in `certificazione.py`, dal
codice e dalle decisioni del 25/09. Proposta: versionarla (e' testo dell'utente: decide lui).

## 3. Cosa ho cambiato (solo documentazione, nel perimetro)

| file | cosa | perche' |
|---|---|---|
| `Betfair/safe_strategy/COSTITUZIONE_SAFE_STRATEGY.md` (§2, +19 righe) | nota datata 07/10 sotto la tabella delle 4 strategie: BASE banca 20-34 (Q1), PUNTA con le bande della BASE (Q10), ESATTO selezione accesa (Q7/D5), veto campionati e finali (Q4/D5), nessun ingresso al minuto di uscita (Q8), tennis 1,02 (Q5), SPEC non versionata | la tabella diceva ancora «fav live 1,20-1,34» per la BASE: (c) documento diverso dal codice e dalle decisioni |
| `Betfair/mike/COSTITUZIONE_MIKE.md` (Fase 3, +17 righe) | nota datata 07/10: forma `lay_under45` di serie, copertura a prezzo coerente (04/10), seconda condizione (04/10, `22e8638`) | le tre regole erano solo in CRONOSTORIA e nel codice |

File nuovi: `AUDIT_2026-10-07/CONFORMITA_BOT_CALCIO.md` (questo), `AUDIT_2026-10-07/patch/safe_replay_mercato_chiuso.diff`,
`AUDIT_2026-10-07/replay_conformita/` (6 referti/diagnostiche, 56 KB), `AUDIT_2026-10-07/strumenti/`
(`ladder.py`, `habitat.py` = lettura del raw senza codice di produzione; `diag_safe2.py`,
`diag_safe3.py`, `diag_scalper.py` = scenario del banco con funzioni VERE avvolte per stampare,
nessun file del repo modificato). Nessun file di codice di produzione toccato: l'impronta del
codice dei bot e' invariata (i .md non entrano in `certifica.impronta`).

## 4. Reperto minore dello Scalper (solo audit, patch proposta)
`scalper_bot._ricorda_residuo` (`scalper_bot.py:2349-2372`) e `_msg_residuo` (`:121-125`) scrivono
«residuo 1.07 non accettato da Betfair .it»: 1,07 e' |se vince - se perde| (P&L), non l'importo.
L'ordine che servirebbe e' 1,07 / 2,20 = **0,48** (sotto 0,50: davvero non piazzabile). Il trader
legge «1,07» e pensa a un importo piazzabile. Proposta (testo, nessuna logica): aggiungere
l'importo dell'ordine e la quota, es. «ordine di chiusura 0,48 @ 2,20 sotto il minimo .it
(differenza fra gli esiti 1,07)». File riservato all'altro delegato: non toccato.

## 5. Test, replay e tempi (tutti con `--worker 1`, uno alla volta)
| comando | esito | tempo |
|---|---|---|
| `certifica safe_base 35797769 35760084 --scenari base` | OK x2, 0 violazioni; 1 ordine (35797769), 0 (35760084) | 176 s (prima del fermo del coordinatore) |
| diagnostica Safe base 35797769 (3 giri: decisioni, letture, patch simulata) | come sopra; con la patch riga `won` +1,90 | ~110 s l'uno |
| `certifica mike 35797769 --scenari base` | OK, 0 violazioni, 2 azioni, +0,13 | 154 s |
| diagnostica scalper_calcio 35797769 `base` (via `certifica.main`) | OK, 167 azioni (identico a `AUDIT_2026-10-05/replay/giro2_coord/A1.txt`) | 74 s |
| diagnostica scalper_calcio 35797769 `sniper` | OK, 167 azioni; sniper 2 fuochi, missione +0,73 (identico a `giro2_coord/B1.txt`) | 254 s |
Nessun test pytest lanciato: nessun file `.py` modificato. Nessuna falsificazione dovuta (nessun
test nuovo); la patch del banco e' stata provata nei due versi (senza: `open`; con: `won`).

## 6. Parita' paper/live
Nessun cambiamento di codice. I referti usati girano in live (coda); la parita' paper/live dello
Scalper e' nel referto (86 parametri, 0 diversi). Safe/Mike in paper non rilanciati oggi.

## 7. Decisioni per l'utente (nessuna toccata da me)
- **D1 — Safe ESATTO nel recupero del 1° tempo.** Soglia «dal 48'» (`esatto.minuteMin`,
  `engine.py:218`, `minute_check` `engine.py:1095`): il feed Betfair nel recupero del 1° tempo
  segna 46'-50' (`matchStatus=KickOff`), quindi l'ESATTO puo' entrare al «48'» del PRIMO tempo.
  Sulla 35797769 e' successo per 4 minuti (19:46-19:50, 1-1) senza ingresso solo perche' la banca
  era 8,6-10 (fuori 30-70). Proposta: chiedere all'utente se il 48' del manuale e' il 2° tempo;
  se si', aggiungere «e non nel 1° tempo» (dato gia' nel feed: `matchStatus`).
- **D2 — Mike, finestra d'uscita «2t» dal 46'** (`h2_loss_from_min`, `engine.py:4939-4946`): vale
  anche nel recupero del 1° tempo (46'-50' con `matchStatus=KickOff`). La cost. §3 Fase 5 dice
  «intervallo e dal 46' all'85'», titolo «nel 2° tempo». Sulla 35760084 Mike era in posizione
  nel 45+1'-47' (3-0): la regola «2t» valutabile prima dell'intervallo. Proposta: stessa domanda
  di D1; la decisione resta a modello, cambia solo da quando.
- **D3 — Scalper maker: il tetto di perdita scatta sui RESIDUI.** Sulla 35797769 (Spagna-Belgio,
  stake 25) 0 cicli verdi, 11 scratch, 6 residui sotto 0,50 non chiudibili (regola .it del 04/10)
  contati al loro esito PEGGIORE: somma -1,61 -> `loss_cap` 1,5 alle 18:19, 42' prima del KO,
  sessione ferma; i 6 residui restano all'utente («li chiudo io», 04/10). Il valore atteso dei
  residui e' circa zero (es. -0,59 se vince / +0,48 se perde). Il codice fa cio' che e' scritto
  (FIX 10/07: residuo nel `pnl_locked` al peggiore). Proposta: lasciare (e' prudente) oppure
  contare i residui a parte dal tetto: decide l'utente.

## 8. Cosa NON ho fatto / NON ho potuto verificare
- Nessun `--scenari tutti` (nessuna correzione di codice): ho usato `base` e diagnostiche mirate,
  piu' i referti certificati del 04-06/10 per gli altri scenari (Mike 35760084 26 scenari,
  Scalper 15+2, Safe base 22 sulla 35760084).
- Patch del banco NON applicata (file fuori perimetro); `replay_tennis.py` non controllato.
- Veto statistico di Mike (`p_under35_cal`) e selezione aggiuntiva dell'ESATTO (H2H/gol subiti)
  NON esercitabili: dati dal DB, assenti nel replay (dichiarato dai referti). In produzione su
  Spagna-Belgio l'ESATTO potrebbe essere escluso dai dati H2H: non verificabile qui.
- Sniper sulla 35760084 e Scalper maker in gioco: non rilanciati.
- `SPEC_STRATEGIA_S.md` non letto (non esiste in questo ambiente).

## 9. Da controllare dal vivo in prova
- Safe ESATTO: dopo una partita con posizione, la riga passa a `won`/`lost` col P&L (scheda
  Regolate): e' il pezzo che il banco non ha mai provato.
- Mike: alla posizione aperta al segno dei 10', nessun secondo ingresso (attivita' `state` HOLD).
- Scalper: il testo dei `residuo_ricordato` (importo vs differenza fra esiti).
