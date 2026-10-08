# CANTIERE 10 — Registro operazioni e P&L del bot: fasi separate e conteggio dei cicli allineato

Delegato di costruzione (sessione cloud, 08/10/2026). Worktree
`/home/user/python-database-automation/.claude/worktrees/agent-a6c264c7010c81043`,
partenza dalla cima `b5547eb` («fix(banco): regola del mercato che attraversa»; il worktree era
nato su `8226d76` ed e' stato portato a `b5547eb` con fast-forward, nessun lavoro perso); a fine
lavoro, su ordine del coordinatore, portato sulla cima integrata `3b8ce19` (vedi §5-bis). Nessun
commit, nessun `git add`. Macchina: 4 CPU condivise con altri cantieri, load average 13-30 durante
tutto il lavoro (i tempi sotto sono misurati sotto carico).

## 1. Causa

(a) Il registro (`RegistroOperazioniBot`) elencava i cicli in un'unica lista, pre-partita e gioco
insieme: nessuna nozione di fase.

(b) Il registro usava SOLO i cicli ricavati dagli ordini (`replayOperazioni.cicliOperativi`,
regola «da posizione piatta a piatta»). In `cicliOperativi` a ogni istante si aggiungono PRIMA gli
ordini nati in quell'istante al ciclo aperto e solo DOPO si controlla se il ciclo e' chiuso
(`for (const o of nati.get(t))` prima del controllo di chiusura): se il bot chiude il ciclo N e
rientra nello stesso istante (rientro automatico alle 23:04:21 sul 35768297) la punta nuova entra
nel ciclo N, che non si chiude piu' li': due cicli del bot diventano uno. Il registro mostrava poi
«per il bot: ... lordo» del PRIMO ciclo del bot trovato (`cicloDelBot`), cosi' «Ciclo 1 +0,37»
aveva accanto «per il bot: lordo +0,18». I totali tornavano perche' il P&L dei cicli somma gli
stessi abbinamenti.

Riprodotto qui con righe e cicli dichiarati costruiti da quelli VERI (stesse chiavi e tipi):
`ESITO_4` in `frontend/src/lib/__fixtures__/registroCicliFinti.ts` (4 cicli del bot, due coppie
che si toccano nello stesso istante): la regola ricavata da' 2 cicli, il bot 4
(test «la regola "da piatto a piatto" li fonde»).

(c) Trovato strada facendo: il tipo TS `CicloDichiarato` NON aveva tre chiavi che Python scrive
(`ordini`, `rientri`, `banca`). Il nuovo test di contratto era ROSSO sul codice di partenza
(`contratto_prima_del_tipo.txt`: 6 rossi, «chiave 'banca' scritta da Python e assente nel tipo TS»).

## 2. Cosa ho cambiato (file:riga, cima del worktree)

Python: NIENTE (il bot calcola i cicli come prima: «Non fare» rispettato). Solo un test nuovo.

| File | Riga | Cosa |
|---|---|---|
| `frontend/src/lib/replayFasi.ts` (NUOVO) | 1-125 | fasi pure: `confiniCalcio`/`faseCalcioDaConfini`/`faseCalcioAl` (primo KickOff, primo FirstHalfEnd/HalfTime dopo, primo SecondHalfKickOff; dopo SecondHalfEnd resta 2T; senza KickOff l'inizio e' la prima riga col minuto = confine di `minutoDiGioco`; senza stati dei tempi «IN GIOCO (tempi IPS non registrati)», mai dedotto dal minuto), `faseTennisDaEtichetta` (da `tennisReplay.faseTennis`, riusata senza toccarla), `fasiFisse` |
| `frontend/src/lib/replayOperazioni.ts` | 27-33 | import tipi, intestazione |
| | 406 | `EventoOperazione.cicloRegistro?` (chiusura di un ciclo del bot) |
| | 752 | `contoCicli`: solo il TIPO del parametro allargato a `Pick<CicloOperativo,'lordoConto'>` (stesso codice) |
| | 788-986 | `CicloRegistro`, `RegistroCicli`, `statoDichiarato`, `registroCicli` (i cicli del bot quando `cicli_bot` non e' null, altrimenti il ripiego coi numeri di prima), `numeroDelBot`, `eventiDelRegistro`, `MetodoConto`/`metodoConto`, `SezioneFase`/`sezioniPerFase` (P&L di sezione con le STESSE funzioni dei totali: `contoCicli` o `contoRegolato`) |
| | 1071-1075 | `testoEvento`: testo della chiusura di un ciclo del bot |
| | 1148, 1172-1176 | `clicNelRegistro`: parametro opzionale `numeroCiclo` (il clic rifiutato «il ciclo N e' ancora aperto» col numero DEL BOT); senza parametro identico a prima |
| `frontend/src/lib/useOperativitaBot.ts` | 9-10, 25-26, 40-45 | `OperativitaBot.registro`; passa `numeroDelBot` quando ci sono i cicli del bot |
| `frontend/src/lib/replayBot.ts` | 170-212 | `RientroDichiarato`, `BancaDichiarata`, chiavi `ordini`/`rientri`/`banca` in `CicloDichiarato` (solo tipi) |
| `frontend/src/components/replay/RegistroOperazioniBot.tsx` | tutto il corpo | cicli da `analisi.registro`; riga `registro-fonte-cicli` («dichiarati dal bot» / «il bot non li dichiara, ricavati dagli ordini»); con `faseIstante`: sezioni fisse con cicli/ordini/P&L, «chiuso al … · FASE» per il ciclo che attraversa due fasi, ordini fuori dai cicli del bot, totale in fondo coi numeri di sempre e «✓ uguale al referto del bot / al banco», vista cronologica con le testate di fase e le chiusure di ciclo del bot. Senza `faseIstante` la vista e' quella di prima |
| `frontend/src/components/replay/RiepilogoPnlBot.tsx` | 8-15, 22-23, 42-49, 58-69 | riga «per fase» sopra «a regolamento» (intervallo solo se ha operazioni, come chiesto «pre-partita / 1T / 2T»); i tre blocchi di prima invariati |
| `frontend/src/components/replay/EsitoBotPanel.tsx` | 21, 36-37, 54, 94-97 | prop `faseIstante` passata a riquadro e registro |
| `frontend/src/pages/MatchReplay.tsx` | 42, 482-489, 1208 | `faseCalcioIstante` (memo su `sortedScoreTimeline`, la stessa cronologia di barra e tabellone) |
| `frontend/src/pages/TennisReplay.tsx` | 57, 337-343, 747 | `faseTennisIstante` (memo su `punteggiOrdinati`, `inGiocoTs`) |

Pulsante «nascondi i N cicli senza abbinamenti» e tabella ordini (`BotOrdersPanel`) invariati.

### Regole scelte (da rileggere)
- Ciclo del bot: numero = `ciclo`; inizio = `inizio_ms` del bot (la sua punta d'ingresso);
  fine = `fine_ms`; se il bot non ha fine e il ciclo e' «APERTO, regolato dal libro finale» la
  fine e' `chiuso_ms` del mercato; ordini = `ordini_id` (= `_ordine` delle righe).
- Un ciclo sta nella fase in cui e' NATO (`daMs`); gli ordini fuori dai cicli del bot nella fase
  in cui sono nati.
- P&L di sezione col METODO del conto dell'esito (`metodoConto`): media under (metodo «cicli") =
  `contoCicli` sui cicli della sezione (il lordo del bot); tutti gli altri = `contoRegolato` sugli
  ordini della sezione. Il LORDO delle sezioni somma esattamente al totale (verificato sui 9 esiti
  veri). Il NETTO no in generale: la commissione del conto si calcola sul totale (media under
  35797769: fasi +0,02/+0,10/+0,33 = +0,45, totale +0,46); il registro lo SCRIVE sotto il totale
  (`registro-totale-nota`). Vedi «Decisioni per l'utente» 1.

## 3. Test aggiunti

- `frontend/src/lib/replayRegistroFasi.test.ts` (23 test): fasi sulle cronologie IPS VERE
  35797769 e 35760084 (confini al ms; recupero del 1T = 1T; KickOff ri-emesso; FirstHalfEnd
  ri-emesso dopo la ripresa; senza stati dei tempi; senza KickOff), tennis 35790089; cicli del bot
  sui 4 esiti veri della media under (numero, istanti, lordo, ordini; regolato = chiusura del
  mercato); ripiego identico a prima sui 5 esiti senza `cicli_bot`; contratto TS (chiavi);
  `ESITO_4`: ricavati 2, registro 4, i due che si toccano restano 2, chiusure cronologiche del bot,
  clic rifiutato col numero del bot, ordini fuori ciclo; sezioni sui 9 esiti veri (fisse sempre,
  ogni ciclo e ordine una volta, lordo = totale di oggi); media under 35797769: pre [1] +0,02,
  1T [2] +0,11, intervallo [3] +0,35, 2T vuoto.
- `frontend/src/components/replay/RegistroFasi.test.tsx` (12 test): registro per fase, «chiuso al»
  (ciclo 1 nato pre-partita chiuso nel 1° TEMPO, ciclo 3 nato all'intervallo chiuso nel 2° TEMPO),
  totale +0,46 «✓», nota della somma dei netti, cronologica per fase, senza fase = come prima, 4
  cicli del bot a schermo con le origini, scalper «il bot non li dichiara», riquadro per fase
  (calcio cicli, calcio regolamento, tennis), EsitoBotPanel.
- `frontend/src/lib/__fixtures__/registroCicliFinti.ts`: l'esito `ESITO_4` (da riga e ciclo veri).
- `Betfair/stream/tests/test_contratto_cicli_bot_ts_2026_10_08.py` (8 test): contratto
  Python<->TS: `riepilogo_cicli_media` VERO (banco della media under del giro 2, ordini veri di
  flumine, esecuzione differita 1 e 4 book) + `cicli_dichiarati` -> chiavi e tipi = interfaccia
  `CicloDichiarato` letta da `replayBot.ts`; idem sui 4 esiti veri; il controllo sa diventare rosso.

Test esistenti: `replayOperazioni.test.ts`, `RegistroOperazioniBot.test.tsx`,
`ApplicaBotPanel.test.tsx`, `replayBarraPunteggio.test.tsx` VERDI SENZA nessuna modifica (nessun
numero atteso cambiato).

## 4. Falsificazione (strumento `strumenti/mutazioni.py`, esiti `mutazioni*.txt`)

Ogni mutazione applicata, test nuovi lanciati, file ripristinato e sha256 verificato IDENTICO;
`git diff` dopo tutte le mutazioni identico byte per byte a quello di prima.

| # | Mutazione | Rossi |
|---|---|---|
| M1 | registro ignora `cicli_bot` | 5 |
| M2 | cicli del rientro automatico fusi/spariti | 4 |
| M3 | istanti dagli ordini invece che dal bot | 2 |
| M4 | niente intervallo | 6 |
| M5 | ultimo KickOff invece del primo | 1 |
| M6 | fase inventata senza stati dei tempi | 1 |
| M7 | ciclo nella fase di chiusura | 9 |
| M8 | P&L di sezione sempre a regolamento | 6 |
| M9 | ordini fuori ciclo persi | 1 |
| M10 | cronologica con chiusure ricavate | 1 |
| M11 | clic col numero ricavato | 1 |
| M12 | niente «chiuso al» | 1 (ripetuta dopo la memoizzazione: 1) |
| M13 | riquadro senza intervallo | 1 (ripetuta: 1) |
| M14 | tipo TS senza `banca` | pytest contratto 6 rossi; tsc 1 errore TS2353; vitest verde (atteso: le chiavi le controlla tsc) |
| M15 | cronologica senza testate di fase | 1 |
| M16 | il ripiego non lo dice | 1 |

## 5. Comandi ed esiti VERI

PRIMA (cima `b5547eb`, nessuna modifica):
- `npx tsc -p tsconfig.app.json --noEmit`: 0 errori, 2m10s (`prima_tsc.txt`).
- `npx vitest run src/lib/replayOperazioni.test.ts src/components/replay/ src/lib/applicaBot.test.ts`:
  7 file, 92 test verdi, 34,9 s (`prima_vitest_mirati.txt`).
- `npx vitest run` intero: 2 rossi | 5299 verdi | 51 saltati (364 file), 39 min sotto carico
  (`prima_vitest_intero.txt`). I 2 rossi sono di tempo, fuori dal mio perimetro e PRE-ESISTENTI:
  `PosizioniChiuse.raggruppamento.test.tsx` «500 cicli montata in meno di 1 s» e
  `RitardiPanel.fixb.test.tsx` (waitFor scaduto).

DOPO:
- tsc: 0 errori (`dopo_tsc.txt`).
- stessi mirati + `RegistroFasi.test.tsx`: 8 file, 104 test verdi, 38,0 s
  (`dopo_vitest_mirati.txt`); per file: `RegistroOperazioniBot.test.tsx` 11,8 s -> 9,1 s,
  `replayOperazioni.test.ts` 0,47 -> 0,34 s (carico variabile: nessun rallentamento visibile).
- `replayRegistroFasi.test.ts`: 23 verdi, 5,8 s.
- `npx vitest run` intero: **0 rossi | 5336 verdi | 51 saltati** (356 file verdi, 10 saltati),
  23m51s sotto carico (`dopo_vitest_intero.txt`). 5336 = 5299 + i 2 rossi di tempo di prima (ora
  verdi: carico minore) + 35 nuovi. Nessun test esistente cambiato.
- `npm run build`: ok, 29,4 s (`dopo_build.txt`; solo l'avviso abituale sulla dimensione dei chunk).
- pytest intero `Betfair/`: VEDI §5-bis.
- pytest `test_contratto_cicli_bot_ts_2026_10_08.py` + `test_replay_professionale_2026_10_07.py` +
  `test_scalper_media_under_giro2_2026_10_05.py`: 82 verdi, 2 saltati (registrazioni grezze assenti
  nel container), 6,8 s (`pytest_mirati.txt`).
- Costo delle funzioni nuove (`misura_tempi_lib.txt`): esito piu' grande (tennis scalper, 72 ordini)
  `analizza` esistente 5,1 ms, registro+sezioni+eventi nuovi 2,1 ms; media under 0,7 / 0,3 ms.
  Le sezioni si calcolano in `useMemo` (la fase arriva dalle pagine come funzione stabile): non a
  ogni passo del cursore.

## 5-bis. pytest intero e spostamento sulla cima integrata

- Sulla cima `b5547eb` con le mie modifiche: `python3 -m pytest Betfair/ -q -p no:cacheprovider`
  **10769 verdi, 85 saltati, 6 xfail, 0 rossi**, 6m24s (`dopo_pytest_intero.txt`).
- AGGIORNAMENTO DEL COORDINATORE (comune.md, dopo il cantiere 15): il worktree e' stato portato
  sulla cima integrata `3b8ce19` (`git fetch origin claude/blissful-sagan-hri7o6` + `git merge
  --ff-only FETCH_HEAD`). L'unico mio file toccato anche dalla cima e' `pages/TennisReplay.tsx`
  (cantiere 14: nota del nome troncato, righe diverse dalle mie): ho tolto a mano i miei 3 pezzi,
  fatto il fast-forward e li ho rimessi identici (diff finale: stesse 469 righe aggiunte / 55 tolte).
  Le fixture `replay_pro`, `replay_barra_*`, `replay_tennis_*` e i file Python che il contratto
  usa NON cambiano fra le due cime.
- Sulla cima `3b8ce19` con le mie modifiche:
  - tsc 0 errori (`dopo_tsc_cima_3b8ce19.txt`);
  - vitest intero: 4 rossi | 5355 verdi | 51 saltati, 37m50s con load average 15-30
    (`dopo_vitest_intero_cima_3b8ce19.txt`). I 4 rossi sono in file che non uso e non tocco
    (`pages/SafeStrategy.test.tsx` x2, `RitardiPanel.fixb.test.tsx`, `BotParamsSheet.test.tsx`:
    «Test timed out in 20000ms» / attese scadute); rilanciati da soli: **3 file, 78 test verdi**
    (`rilancio_rossi_di_carico.txt`). Sono rossi di CARICO della macchina, non regressioni.
  - pytest mirati (contratto + replay professionale + giro 2): 83 verdi, 1 saltato
    (`pytest_mirati_cima_3b8ce19.txt`);
  - pytest intero: 1 rosso | 10958 verdi | 65 saltati | 6 xfail, 10m09s
    (`dopo_pytest_intero_cima_3b8ce19.txt`). Il rosso e'
    `test_auto_follow_2026_09_25.py::test_latenza_logica_aggancio_sotto_i_20_ms` (20,0004 ms
    contro il tetto di 20 ms: misura di tempo sotto carico; Python non toccato da questo
    cantiere); rilanciato da solo il file: **31 verdi** (`rilancio_rossi_di_carico.txt`).

## 6. Replay

Questo cantiere NON tocca Python ne' il banco: nessun replay da rifare (il «prima/dopo» dei referti
del banco e' identico per costruzione: nessun file del banco toccato). La prova di non regressione
richiesta dalle specifiche e' quella sulle fixture `replay_pro` (9 esiti veri): test esistenti
verdi senza modifiche ai numeri + test nuovi.

## 7. Cosa NON ho potuto verificare
- Il caso VERO dell'utente (Match Replay 35768297, media under, 4 cicli del bot contro 3 del
  registro): la registrazione e il DB non sono nel container. Coperto con `ESITO_4` costruito da
  righe e cicli veri. **Da rifare sul PC**: Match Replay 35768297 -> Applica bot media under
  (clic 1783034130481) -> il registro deve mostrare la riga «cicli: quelli dichiarati dal bot (N)»
  con N = `esito.cicli_bot.length` (oggi col banco «che attraversa» sono 5 cicli / 20 ordini,
  CRONOSTORIA 08/10), cicli numerati come il bot, nessuna riga «per il bot: lordo» diversa dal
  «P&L» del suo ciclo, e in fondo TOTALE «✓ uguale al referto del bot».
- Le sezioni del TENNIS sulle registrazioni 35790089/35794049 a schermo: coperte solo con la
  cronologia vera di 35790089 nella fixture (inizia a set 2: le prime righe sono PRE-PARTITA
  finche' il flag di mercato non e' in gioco, come fa gia' `faseTennis`).
- Nessuna prova a schermo (niente app nel container).

## 8. Decisioni per l'utente
1. **Netto per fase.** Il netto di ogni fase e' calcolato sulla fase da sola (commissione sul
   lordo positivo della fase); il totale in fondo resta quello di sempre (commissione sul totale).
   Quindi la somma dei netti delle fasi puo' differire di qualche centesimo dal netto totale e il
   registro lo scrive. Alternativa possibile: mostrare per fase SOLO il lordo. Nessuna strategia
   toccata.
2. **Intervallo nel riquadro.** La specifica dice «pre-partita / 1T / 2T»: l'intervallo compare
   nella riga del riquadro solo se ha operazioni (la media under 35797769 ne ha uno: nascondendolo
   si perderebbero +0,35). Nel registro le 4 sezioni ci sono sempre.

## 9. Cosa controllare a schermo sul PC
- Match Replay 35797769, media under con i 4 clic: registro «per ciclo» con PRE-PARTITA (ciclo 1,
  «chiuso al …' · 1° TEMPO»), 1° TEMPO (ciclo 2), INTERVALLO (ciclo 3, «chiuso al …' · 2° TEMPO»),
  2° TEMPO vuoto; riquadro «per fase (dei cicli, metodo del bot): pre-partita +0,02 · 1T +0,11 ·
  intervallo +0,35 · 2T 0,00»; totale +0,46 «✓ uguale al referto del bot».
- Replay Tennis 35790089, Tennis Scalper: sezioni PRE-PARTITA / SET n.

## Blocco per la cronostoria

```
### CANTIERE 10 (cloud, delegato) — registro operazioni e P&L del bot: cicli del bot e fasi
- Causa: il registro usava solo i cicli «da piatto a piatto» (cicliOperativi aggiunge al ciclo
  aperto gli ordini nati nell'istante in cui si chiude: chiusura + rientro nello stesso istante =
  un ciclo solo) e non conosceva le fasi. Trovato anche: tipo TS CicloDichiarato senza
  ordini/rientri/banca (contratto rosso prima).
- Fatto (solo frontend + test di contratto Python; Python e banco NON toccati): replayFasi.ts
  (nuovo, fasi da KickOff/FirstHalfEnd/SecondHalfKickOff e da faseTennis), registroCicli /
  sezioniPerFase / eventiDelRegistro / numeroDelBot in replayOperazioni.ts, registro e riquadro per
  fase, MatchReplay/TennisReplay passano la fase. Ripiego dichiarato a schermo.
- Test: replayRegistroFasi.test.ts 23, RegistroFasi.test.tsx 12, contratto Python 8; esistenti
  verdi senza modifiche. Mutazioni M1-M16 tutte rosse (M14 rossa su pytest e tsc), ripristino con
  sha verificato. Su b5547eb: tsc 0; vitest intero 0 rossi / 5336 verdi; build ok; pytest intero
  10769 verdi / 0 rossi. Portato sulla cima 3b8ce19 (ff): tsc 0; vitest intero 4 rossi di carico
  in file estranei (verdi rilanciati da soli, 78/78) / 5355 verdi; pytest intero 1 rosso di
  latenza (20,0004 ms, verde da solo) / 10958 verdi.
- Da rifare sul PC: caso vero 35768297 (cicli del registro = cicli_bot), prova a schermo.
- Referto: AUDIT_2026-10-08/cantiere_10/REFERTO.md
```

## Verifica del coordinatore cloud (08/10)
- Diff riletto. Applicato sulla cima (W1 compreso): `tsc` 0 errori; vitest replay (24 file) 284/284; contratto Python dei cicli 8/8.
- MIE MUTAZIONI: cicli del bot ignorati (sempre «da piatto a piatto») -> 6 rossi; ciclo messo nella fase in cui CHIUDE -> 9 rossi;
  KickOff ri-emesso preso come calcio d'inizio -> 1 rosso. Ripristino verificato.
- Decisioni per l'utente (dal referto): netto per fase calcolato sulla fase (la somma puo' differire di un centesimo dal totale, detto
  a schermo) oppure solo lordo per fase; INTERVALLO mostrato solo se ha operazioni.
- DA FARE SUL PC: 35768297 a schermo (registro con N = cicli del bot, totale «uguale»).
