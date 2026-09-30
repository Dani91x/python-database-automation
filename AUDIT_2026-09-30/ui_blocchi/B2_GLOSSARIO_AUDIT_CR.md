# B2_GLOSSARIO_AUDIT_CR - referto (30/09/2026)

Worktree: `C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.claude\worktrees\agent-aef9b44f1a9ce5796`
(HEAD `4fcb867`, detached; nessun commit). Patch: `AUDIT_2026-09-30/ui_blocchi/B2_GLOSSARIO_AUDIT_CR.patch`
(solo `frontend/`, file nuovo incluso con `git add -N`; `git apply --check -R` OK).

Solo testi e presentazione. Nessuna logica di trading, nessun dato nuovo, nessuna lettura nuova.

## 1. Reperti: PRIMA -> DOPO a schermo, prova, dove

| # | PRIMA | DOPO | Prova che il testo nuovo e' vero | File toccato |
|---|---|---|---|---|
| A9 | `cash out +1,23 € · 12,3 % / soglia 5,0 % · parziale` (title «il book non copre l'intera chiusura») | `cash out non calcolabile (manca il prezzo di una linea)`, nessuna cifra; title «una linea ancora in gioco non ha prezzo sul book: il valore di chiusura di tutta la partita non si può calcolare». Con `complete=true` invariato | `Betfair/mike/engine.py:939-968`: `complete=False` solo quando una selezione VIVA ha `plan.actionable` falso; `continue` = il netto la ESCLUDE. Card di Mike: `MikeMatchCard.tsx:1022-1024` non mostra la cifra | `components/controlroom/SchedaMike.tsx` (Voce cash out; testid `cr-mike-cashout-parziale` conservato sullo span del testo) |
| M9 | `ciclo 0 · 0 chiusi` | in gioco `ciclo 1 · 0 chiusi` (cycle_no 2 -> `ciclo 3 · 2 chiusi`); partita chiusa `ciclo 3 usati` | `service.py:5022` `cicli_chiusi = ctx.cycle_no`; `cycleText` ESPORTATA da `components/mike/MikeMatchCard.tsx:315` (importata, non duplicata). Il massimo (`pre_max_cycles`) la scheda non lo riceve: passato `null` e NON stampato il «di M» (sarebbe uscito «massimo non configurato», falso) | `SchedaMike.tsx` |
| A3 | Solo «Over 4.5» con title «...linea 4.5 (la copertura)»; nessun Under 4.5. Title P(4): «(perdono sia Under 3.5 sia Over 4.5)» | Nuova Voce `Under 4.5` back/lay (testid `cr-mike-u45`), title «qui va la copertura nella forma «banca Under 4.5» e il re-ingresso dopo un gol». Over 4.5 title: «qui va la copertura solo nella forma «punta Over 4.5»; la chiusura della copertura è una banca Over 4.5». Se la partita ha una gamba `over_cover`, i due title aggiungono «su questa partita: Copertura: banca Under 4.5» (da `roleLabelGamba`). P(4): «(perdono l’Under 3,5 e la copertura)», formula e «P(4 gol ESATTI)» invariati | `config.py:212` `cover_form='lay_under45'`; `engine.py:3977` banca `over_cover` OU45/UNDER, `:3857` punta OU45/OVER (forma vecchia), `:4351` `reentry` OU45/UNDER; chiave `service.py:5036` `f"{m}|{s}"` -> `OU45|UNDER`. `ev` non porta `cover_form`: la forma si dice solo dalla gamba vera | `SchedaMike.tsx` |
| M10 | `responsabilità 12,40 €` (SchedaMike); `· responsabilità 4,00 €` (riga orfana CR); `resp. 5,00 €` + title «responsabilita' impegnata...» (riga operazione); title Copertura «...responsabilità ancora a rischio»; cella `Responsabilità` e frase «la responsabilità qui sopra è quella che rischi» (proposta opportunità); colonna `Responsabilità` e totale `Responsabilità · LIVE` (tabella operazioni Omega/Safe/Mike); TIP investito «...non la responsabilità di una banca»; errore Omega «...responsabilita’ aperta...» | `Liability aperta 12,40 €` (totale della partita, `T.openLiability`); `· liability 4,00 €`; `liability 5,00 €` (title «liability impegnata da questa posizione», testid nuovo `cr-op-liability`); «...liability ancora a rischio»; cella `Liability`, frase «la liability qui sopra è quella che rischi»; colonna e totale `Liability aperta` / `Liability aperta · LIVE`; «...non la liability di una banca»; «...liability aperta...» | Glossario `DESIGN_SYSTEM.md` §3 (vietato «responsabilità»). Investito = somma di `open.size` (`lib/eventGroups.ts:288-290`): davvero lo stake, non la liability. `T.totLiability` ora = `T.openLiability` | `lib/tradeStatus.ts` (T.totLiability, TIP.totInvestito), `components/trading/EventPnlTable.tsx` (th -> `{T.totLiability}`), `DettaglioRigaView.tsx` (2 punti), `SchedaPropostaOpportunita.tsx` (2 punti), `pages/ControlRoom.tsx` (riga orfana), `lib/interruttori.ts` (messaggio `ParametriOmegaIgnoti`), `SchedaMike.tsx` |
| M10 Flatten | - | Nessun «Flatten» nei testi visibili del mio perimetro (verificato dalla guardia). Resta `lib/mike.ts:1773` `flatten: 'Flatten'` (MIKE_REQUEST_KIND_LABEL, fuori perimetro: NON toccato) | grep | - |
| M11 | Titolo «Mike vorrebbe uscire: X» ambra; «(in perdita)» e rosso solo con `urgente` | Sempre rosso (`border-red-500/40 bg-red-500/10`, titolo `text-red-200`). `urgente` -> «Mike vorrebbe uscire: X (IN PERDITA)»; altrimenti «Mike vorrebbe uscire: X (può chiudere IN PERDITA)» | `engine.py:2738-2741` si propone SOLO se `uscita_in_perdita(d)`; `:2606-2633`: vero per `loss*` (sicuramente in perdita, = `urgente` `:2780`), `reentry_time` con bloccato <0 o ignoto (fail-closed) e chiusura del veto (possono esserlo). Per questo il non-urgente dice «può» | `PropostaUscitaMike.tsx` |
| M12 | «chiudendo ora +1,28 €» | «chiudendo tutta la partita ora +1,28 €» | `live.cashout.net` = `cashout_value` su TUTTE le selezioni aperte (`engine.py:933-1005`). Il `per` della selezione NON l'ho usato per il re-ingresso: la banca di copertura sta sulla stessa selezione OU45/UNDER, la cifra mescolerebbe re-ingresso e copertura | `PropostaUscitaMike.tsx` |
| A12 | Tooltip per tutti: «le uscite della strategia (in profitto e in perdita) diventano PROPOSTE...» / «confermi? ...in profitto e in perdita» | Con `StatoUscite.soloUsciteInPerdita` (solo Mike): «le uscite in PERDITA della strategia diventano PROPOSTE nella scheda: le approvi tu. Le uscite in profitto (green-up, uscita al fischio, cash out in profitto) le esegue sempre il bot; le protezioni restano automatiche» / «confermi? da qui il bot esegue da solo anche le uscite in PERDITA secondo la sua strategia (quelle in profitto le esegue gia’ da solo)». Altri bot: testo IDENTICO (test) | `engine.py:2736-2741` (protezioni e uscite in profitto passano sempre); nota `lib/interruttori.ts` `NOTA_USCITE_MIKE`. Campo esplicito nuovo `soloUsciteInPerdita` in `StatoUscite`, messo SOLO da `statoUscite` per `bot==='mike'`; il componente legge lo stato, nessun `if (bot==='mike')` | `lib/interruttori.ts`, `components/controlroom/InterruttoreUscite.tsx` (funzioni `titoloPassaAManuali`, `titoloConfermaAutomatiche`) |
| B4 | Card «Mike: uscita appoggiata SPENTA in live» identica anche con Mike in paper | Card invariata + riga `cr-mike-resting-modo`: live -> «Mike è in LIVE adesso: riguarda i soldi veri di questo momento.»; paper -> «Mike ora è in PAPER: in paper non cambia niente, vale solo quando Mike è in LIVE.»; modalità non letta -> «Modalità di Mike non letta: vale solo quando Mike è in LIVE.» | `service.py:1285-1315` `_live_exit_override`: la valvola agisce solo con `mode=='live'`. SCELTA: la card resta visibile anche in paper (la valvola e' un parametro gia' spento che scatta nel momento in cui si passa a LIVE: il trader deve saperlo PRIMA, un avviso sui soldi veri non deve sparire) e dice la verità sul modo. Modo = `vm.bots[mike].modalita` (dato già nel modello di vista) | `pages/ControlRoom.tsx` (solo il blocco della card) |
| Stile | chip «banca» del «chiudi ora» nella riga orfana `bg-pink-500/15 text-pink-300` | `bg-rose-500/15 text-rose-300` (come `LATO_CLS.lay` 3 righe sopra nella stessa card) | DESIGN_SYSTEM §4 LAY = rose | `pages/ControlRoom.tsx` (una riga) |

`pages/ControlRoom.tsx`: toccati SOLO 3 hunk (card B4, testo riga orfana, chip rose).

## 2. Reperti NON corretti / limiti

- M9: il «di M» (massimo cicli) NON e' mostrato: `SchedaMike` riceve solo `ev`, i parametri non arrivano; passarli richiede di toccare `SchedaPartita.tsx` (fuori perimetro). Quindi niente «esauriti».
- A9 parte `closeNowTotal` (barra Operazioni di Mike, `lib/mike.ts`): fuori perimetro, non toccata.
- A12 nella SCHEDA PARAMETRI di Mike (`ParamsSheetBase.tsx:221` monta `InterruttoreUscite` con `uscite={{ automatiche }}` senza il campo): lì i tooltip restano «in profitto e in perdita» (accanto c'e' l'hint vero di `lib/mike.ts:514`). Correzione di una riga in `ParamsSheetBase`/`MikeParamsSheet` (fuori perimetro): passare `soloUsciteInPerdita: true` per la chiave `uscite_automatiche` di Mike.
- Chip pink rimasti in Control Room (fuori dalla riga orfana, non richiesti): `DettaglioRigaView.tsx:187` e `:286`, `SchedaPropostaOpportunita.tsx:433` e `:472`, `PosizioniChiuse.tsx:628` e `:724`, `SchedaChiusura.tsx:207`. Ora la Control Room ha due rosa per la banca: da uniformare in un blocco successivo.
- M11: una proposta VECCHIA (pre 29/09, `close_reason='profit'`) salvata in `ctx` su una partita che il motore non rigira direbbe «può chiudere IN PERDITA». Il motore la fa decadere al primo giro (`engine.py:2738-2741`, `_decadi`).

## 3. File

Toccati: `frontend/src/pages/ControlRoom.tsx`, `frontend/src/components/controlroom/SchedaMike.tsx`,
`PropostaUscitaMike.tsx`, `InterruttoreUscite.tsx`, `DettaglioRigaView.tsx`, `SchedaPropostaOpportunita.tsx`,
`frontend/src/components/trading/EventPnlTable.tsx`, `frontend/src/lib/tradeStatus.ts`, `frontend/src/lib/interruttori.ts`.
Test toccati: `components/controlroom/PropostaUscitaMike.test.tsx`, `DettaglioRigaView.test.tsx`, `dettaglioRiga.test.tsx`,
`SchedaPropostaOpportunita.test.tsx`, `components/trading/EventPnlTable.test.tsx`, `designGuard.test.ts`,
`lib/tradeStatus.test.ts`, `lib/interruttoriUscite.test.ts`, `pages/ControlRoom.test.tsx`.
Nuovi: `frontend/src/components/controlroom/B2GlossarioAuditCR.test.tsx` (14 test);
fuori da `frontend/`: `AUDIT_2026-09-30/ui_blocchi/falsifica_B2.cjs`, questo referto, STATO, patch.

## 4. Test

Nuovi: `B2GlossarioAuditCR.test.tsx` (A9 x2, M9 x3, A3 x3, M10, M11 x2, M12, A12 x2 - rosso 12/14 prima delle correzioni, i 2 verdi erano i casi «invariato»);
`designGuard.test.ts` blocco «glossario Liability nei file della Control Room» (guardia su 9 file: `responsabilit`, `resp. `, `Flatten` in righe non commento; autotest della guardia, CRLF compreso);
`EventPnlTable.test.tsx` intestazione/tooltip; `tradeStatus.test.ts` T.totLiability = T.openLiability e nessun «responsabilit» in T/TIP;
`DettaglioRigaView.test.tsx` «liability 5,00 €»; `SchedaPropostaOpportunita.test.tsx` etichetta «Liability»;
`ControlRoom.test.tsx` riga orfana (liability + chip rose) e B4 x3 (paper / live / ignota).

Test ESISTENTI cambiati (cambia il testo voluto, nessuna asserzione indebolita):
- `PropostaUscitaMike.test.tsx:64-66` titolo -> «... (può chiudere IN PERDITA)» (M11); `:73-74` -> `/^chiudendo tutta la partita ora \+1,28 €/` (M12); `:82-83` «(in perdita)» -> «(IN PERDITA)».
- `EventPnlTable.test.tsx:146` «Responsabilità» -> «Liability aperta» + `not /responsabilit/`; `:352` «Responsabilità · LIVE» -> «Liability aperta · LIVE».
- `interruttoriUscite.test.ts:45-51` `toEqual` di Mike con `soloUsciteInPerdita: true` (campo nuovo).
- `dettaglioRiga.test.tsx:261` `cr-mike-cicli` «2» -> `/^ciclo\s*3 · /` (M9; il finto ha cycle_no 2).

Comandi (da `frontend/` del worktree):
- `npx tsc -p tsconfig.app.json --noEmit` -> 0 righe di errore.
- Finale, UNA volta: `npx vitest run src/components/controlroom src/components/trading src/pages/ControlRoom.test.tsx src/lib/tradeStatus.test.ts src/lib/interruttori.test.ts src/lib/interruttoriUscite.test.ts src/lib/interruttoriScalper.test.ts src/pages/Omega.test.tsx src/pages/Omega.storico.test.tsx src/pages/Omega.certificazione.test.tsx src/pages/SafeStrategy*.test.tsx (6 file) src/pages/Mike.test.tsx src/pages/Mike.fixA.test.tsx src/components/mike/MikeEventPnlTable.test.tsx src/components/mike/MikeMatchCard.test.tsx src/components/mike/useMikeEventoAlMs.test.tsx`
  -> 88 file, 1471 passati, 1 fallito (`dettaglioRiga.test.tsx:261`, vecchio «ciclo 2», corretto sopra), 1 saltato; poi `dettaglioRiga.test.tsx` rilanciato: 31/31. Durata 294 s.
- I test `src/certification/*.cert.test.tsx` (DB vero) NON lanciati: il loro `kpi()` cerca solo `stat-tile`/`*-kpi-*`, non la barra dei totali.

## 5. Falsificazioni (`node AUDIT_2026-09-30/ui_blocchi/falsifica_B2.cjs`, copie fuori dal repo, ripristino dalla copia, confronto byte a byte)

Tutte e 23 ROSSE, tutte «RIPRISTINATO (identico alla copia)»; `git diff` dopo = identico byte per byte a prima (`cmp`).
F01 A9 cifra mostrata con complete=false -> 1 rosso · F02 M9 `{ev.cycle_no}` -> 2 · F03 A3 Under 4.5 senza book -> 1 · F04 title P(4) vecchio -> 1 ·
F05 label «responsabilità» in SchedaMike -> 2 (B2 + guardia) · F06 titolo senza «IN PERDITA» -> 2 · F07 riquadro ambra -> 2 · F08 «chiudendo ora» -> 2 ·
F09 campo `soloUsciteInPerdita` tolto -> 2 · F10 tooltip non guidato dallo stato -> 1 · F11 testo di Mike agli altri bot -> 2 ·
F12 `totLiability='Responsabilità'` -> 5 · F13 TIP investito vecchio -> 3 · F14 colonna «Responsabilità» -> 2 · F15 «resp.» nella riga -> 2 ·
F16 cella «Responsabilità» -> 2 · F17 frase opportunità -> 1 (guardia) · F18 riga orfana «responsabilità» -> 2 · F19 chip pink -> 1 ·
F20 B4 ramo paper -> 1 · F21 B4 ramo live -> 2 · F22 messaggio Omega -> 1 (guardia) · F23 «Flatten» in un testo -> 1 (guardia).

## 6. «responsabilità» / «Flatten» rimasti FUORI perimetro (non toccati)

- `components/controlroom/SchedaPartita.tsx:462-463` title «responsabilità impegnata con SOLDI VERI» + testo `resp. 9,80 €` (è la «resp.» vista dall'utente nella scheda live!), `:467` title «responsabilità impegnata in PROVA...». PRIORITARIO per il blocco di SchedaPartita.
- `lib/mike.ts:1773` `flatten: 'Flatten'` (etichetta richiesta nei toast di Mike; il pulsante si chiama «Chiudi a mercato»).
- `lib/valutaProposta.ts:157` «responsabilità oltre il tetto per operazione» (motivo mostrato).
- `components/safestrategy/InvestAction.tsx:229` e `:319`.
- `pages/ReportPersonale.tsx:293` (title) e `:324` (etichetta).
- `components/live/DutchingPanel.tsx:447`, `:559`; `GridView.tsx:509`; `LadderView.tsx:979`, `:1205`, `:1209`, `:2368` (title); `LiveTradingPanel.tsx:442`; `PlaceConfirmDialog.tsx:50`, `:107`.
- `components/watchlist/MultiTradeForm.tsx:458`, `:470`, `:503`, `:622`; `TradeForm.tsx:312`.
- Solo commenti/nomi di campo (non visibili): `lib/ladderMath.ts:80,84`, `lib/safeBot.ts:65`, `lib/scalperControlRoom.ts` (campo `responsabilita`), `safestrategy/SignalCard.tsx`, `RiskPanel.tsx`, `OpportunityGroup.tsx`.
- `T.totLiability` compare in: `components/trading/EventPnlTable.tsx` (TotaliBar + ora l'intestazione), usato da `pages/Omega.tsx` (TotaliBar), `pages/SafeStrategy.tsx` (EventPnlTable), `components/mike/MikeEventPnlTable.tsx` -> `pages/Mike.tsx`. I loro test sono nel lancio finale: verdi.

## 7. Parità paper/live

Nessun ramo per modalità nei testi cambiati, tranne B4 che DICHIARA la modalità di Mike letta dal servizio. Nessun comportamento cambiato.

## 8. COSA NON HO FATTO

- Nessun commit, nessun `npm run build`, nessuna suite intera, nessun processo, nessuna chiamata a DB o Betfair.
- Non ho toccato i file fuori perimetro elencati sopra (SchedaPartita, lib/mike.ts, ParamsSheetBase, MikeParamsSheet, pagine live/safe/watchlist/report, chip pink degli altri componenti).
- Non ho mostrato il massimo dei cicli in Control Room (M9, serve un prop da SchedaPartita).

## 9. COSA NON HO POTUTO VERIFICARE

- **L'app a schermo non l'ho vista**: lunghezza delle nuove frasi (title Under/Over 4.5, riga B4, titolo proposta) e loro resa/troncamento solo da jsdom.
- Che `live.cashout.complete` arrivi sempre come booleano dal canale al ms: se un giorno mancasse, la scheda dice «non calcolabile» (fail-closed, come la card).
- Il caso reale di una proposta d'uscita «veto pre-partita»: dedotto da `engine.py:2633`, nessun dato vivo.
- I test di certificazione su DB (`src/certification/*`) non lanciati.

## 10. Da controllare dal vivo in paper al prossimo avvio

- Control Room, scheda Mike di una partita in gioco: riga linee «Under 3.5 / Over 4.5 / Under 4.5» con prezzi; «ciclo 1 · 0 chiusi» al primo ciclo; «Liability aperta».
- Con Mike in paper e `live_resting_enabled` spento: card arancione con la riga «Mike ora è in PAPER...».
- Interruttore uscite di Mike (Control Room): passare il mouse su «passa ad automatiche»/«confermi?»: deve parlare solo delle uscite in PERDITA.
- Tabella Operazioni di Omega/Safe/Mike: colonna e totale «Liability aperta».

## Verifica del coordinatore UI (admin-07), 30/09 18:05
- Albero di verifica: `1d058a7` + C_P11 + G_P2 (+ test) + B1 + B2 impilati SENZA conflitti; le stesse patch, in questo ordine (G_P2 → G_P2_test → B1 → B2), si applicano pulite con `git apply` sul master `7bbff9b` (provato in un worktree di integrazione).
- Sull albero INTEGRATO: `npx tsc -p tsconfig.app.json --noEmit` = 0 errori; `npx vitest run src/components/controlroom src/components/trading src/pages src/components/mike` + i test di lib toccati = 111 file, 1685 test verdi, 1 saltato (737 s a PC carico).
- Diff di produzione riletto per intero (9 file): solo testi e presentazione; in `pages/ControlRoom.tsx` 3 hunk (card B4, riga orfana, chip rose).
- Mutazioni MIE: ciclo sfasato di uno (`cycle_no + 1`) -> 4 rossi; proposta non urgente dichiarata «IN PERDITA» certa -> 1 rosso; card B4 con i rami live/paper scambiati -> vedi riga sotto. Ripristino da copia con `cmp`.
- Attenzione per chi fonde: `SchedaMike.tsx` importa `cycleText` da `components/mike/MikeMatchCard.tsx`.
