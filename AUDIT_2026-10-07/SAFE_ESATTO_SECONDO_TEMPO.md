# SAFE ESATTO SOLO NEL SECONDO TEMPO — referto del delegato (07/10/2026)

Cantiere: reperto **D1** di `AUDIT_2026-10-07/CONFORMITA_BOT_CALCIO.md` par. 7. Decisione
dell'utente (testuale): «No, e' tassativo nel secondo tempo, il primo tempo va escluso».
Worktree: `/home/user/python-database-automation/.claude/worktrees/agent-a4674e5bfb5783628`
(lavoro NON committato, base `8226d766`).

## 1. Causa radice (con prova)

- La finestra d'ingresso dell'ESATTO e' la sola soglia del minuto:
  `engine.DEFAULT_PARAMS["esatto"]["minuteMin"] = 48` (`Betfair/safe_strategy/engine.py:223`),
  applicata da `minute_check` (`engine.py:1129`, «vera dal minuto indicato IN POI») dentro
  `evaluate_esatto` (`engine.py:1338`). Nessun'altra condizione guardava la fase della partita.
- Il feed IPS di Betfair, nel RECUPERO del 1o tempo, da' il minuto CUMULATO. Prova sulla
  registrazione vera `_live_raw/35797769/35797769.scores.jsonl` (sonda in sola lettura):
  `19:46:43 KickOff timeElapsed 46 (reg 45, added 1)` ... `19:49:22 KickOff 48 (45, 3)` ...
  `19:50:45 FirstHalfEnd 50 (45, 5)`; poi `20:08:20 SecondHalfKickOff 46`. Sulla 35760084:
  `16:47:19 KickOff 46`, `16:48:05 KickOff 47`. Il `minute` della riga dello scanner e'
  `timeElapsed`, quindi 48' del recupero del 1T e 48' della ripresa erano indistinguibili per
  il motore: con 1-1, banca in 30-70 e punteggio stabile, il 19:49 della 35797769 sarebbe
  stato un SEGNALE (oggi non lo e' stato solo perche' la banca era 8,6-10).
- Prova TDD: il test `test_recupero_del_primo_tempo_al_48_non_entra` sul codice di partenza
  e' ROSSO (13 rossi su 17 nel primo giro, lo stato era `signal`).

### Altre varianti/uscite con la stessa finestra (NON cambiate: la decisione non le riguarda)
- `minuteMin` 48 e' usato SOLO dall'ESATTO (BASE 55, PUNTA 66: `engine.py:197`, `:278`).
- **BASE (dal 55')**: con un recupero lungo del 1T o all'intervallo il minuto del feed puo'
  arrivare a 55-56' (misura del 25/09 in `Betfair/stream/scalper/atlante_v4.py:536-541`:
  35674515, all'intervallo 45 -> 56 in 13'). La BASE potrebbe quindi entrare all'intervallo.
  Non toccata: vedi «Decisioni per l'utente».
- PUNTA (66') e uscite a tempo ESATTO/BASE/PUNTA (72'/80'/83', `exits.py:1006-1030`):
  irraggiungibili nel 1T; l'uscita ESATTO «lato bancato segna» non dipende dal minuto e una
  posizione ESATTO, da oggi, nasce solo nel 2T. Nulla da cambiare.
- Mike (D2, `h2_loss_from_min` dal 46') ha lo stesso problema: fuori perimetro, non toccato.

## 2. Cosa ho cambiato e perche'

Fonte della fase: **riuso** di `atlante_v4.tempo_da_stato_ips` (stessa funzione che Safe usa
gia' per la nota del modello, `opportunity.py:694`, e Mike in `dossier.py:339`; tarata sulle
60 registrazioni vere il 25/09: 1T = `KickOff`, intervallo = `FirstHalfEnd`, 2T =
`SecondHalfKickOff`, stato vecchio `KickOff` oltre il 60' = ambiguo). Nessuna funzione nuova di
fase; `omega_engine.mission_phase` scartata perche' senza stato deduce il 2T dal minuto > 45
(proprio l'errore da evitare).

- `engine.py`
  - import di `tempo_da_stato_ips` (`:52`); costante `DEG` (`:69`).
  - `FootballMatchCtx`: campi additivi `tempo`, `stato_ips`, `stato_ips_presente` (default
    None/None/False: i costruttori esistenti non cambiano).
  - `build_football_ctx_from_scan` -> `_fase_da_scan` (`:789`): legge `score_raw` della riga
    (lo stato IPS che lo scanner pubblica, `service.py:1796`, `:2584`). **Senza `score_raw`
    nessuna deduzione dal solo minuto** (anche al 92': fail-closed come da brief).
  - `secondo_tempo_check` (`:1144`), check id `secondHalf` «Solo nel 2o tempo»: True solo se
    tempo = 2; False con valore «recupero del 1o tempo (KickOff)» / «intervallo
    (FirstHalfEnd)» / «1o tempo»; None (n/d) con «n/d: stato IPS assente» o «n/d: fase non
    riconosciuta (stato)». `state_from_checks`: False -> `no`, None -> `nd`: in entrambi i
    casi nessun candidato (`football_candidates` prende solo `signal`).
  - `evaluate_esatto`: il check e' aggiunto subito dopo quello del minuto (`:1339`). **Soglia
    48 invariata**, nessun parametro nuovo (la parita' dei default col TS resta intatta).
  - `SafeEngine.esatto_fase_ignota_events` (`:2148`): partite in gioco, dal 48' in poi, con il
    check della fase n/d.
- `bot_service.py`: `_log_esatto_fase_ignota` (`:6917`), chiamata in `scan_and_place`
  (`:7058`) prima dell'uscita su «nessun segnale», come `pre_ko_assente`: scarto
  `reason="esatto_fase_ignota"`, `strategy="esatto"`, `fase`, minuto; throttlato da
  `_log_skip`; solo se la variante ESATTO e' accesa.
- `certificazione.py`: controllo di condotta **E11** (`:842`, quando = ogni valutazione
  ESATTO): violazione se il check `secondHalf` sparisce, se c'e' un segnale senza stato IPS o
  con tempo != 2, o se il check e' vero con tempo != 2.
- `COSTITUZIONE_SAFE_STRATEGY.md` par. 2: nota datata 07/10 con la decisione.
- `tools/replay_registrazioni.py`: **patch del banco** del coordinatore applicata come
  autorizzata (`AUDIT_2026-10-07/conformita_calcio/patch/safe_replay_mercato_chiuso.diff`,
  `process_closed_market`), senza altre modifiche.

### File toccati (esatti)
- `Betfair/safe_strategy/engine.py`
- `Betfair/safe_strategy/bot_service.py`
- `Betfair/safe_strategy/certificazione.py`
- `Betfair/safe_strategy/COSTITUZIONE_SAFE_STRATEGY.md`
- `Betfair/safe_strategy/tools/replay_registrazioni.py` (solo la patch del coordinatore)
- `Betfair/safe_strategy/tests/test_engine.py` (finto: vedi sotto)
- `Betfair/safe_strategy/tests/test_certificazione_c3_2026_09_16.py` (finto: vedi sotto)
- NUOVO `Betfair/safe_strategy/tests/test_esatto_secondo_tempo_2026_10_07.py` (18 test)
- NUOVO questo referto.

### Finti aggiornati (catalogo par. 7.27)
67 test esistenti sono diventati rossi col cambio perche' i finti NON parlavano come il vero:
`test_engine.calcio_payload` non aveva `score_raw`, `test_certificazione_c3.payload` lo
metteva a `None` con la partita in gioco. Nel feed vero la riga in gioco porta SEMPRE lo
stato IPS. Aggiunto `test_engine.stato_ips_calcio` (chiavi e tipi della registrazione vera:
gol come stringhe, `timeElapsedSeconds` tolto come fa `scanner.strip_volatile_state`,
`elapsedAddedTime` solo nel recupero) e lo stato di serie: in gioco `SecondHalfKickOff` oltre
il 45', `KickOff` fino al 45', pre-partita nessuno (parametro `match_status` per forzarlo).
Nessuna asserzione dei test esistenti e' stata cambiata. I tre stati del test nuovo sono gli
stati veri della 35797769 (19:49:22, 19:50:45, 20:10:25) e
`test_i_finti_hanno_le_chiavi_del_vero` confronta la loro forma con la registrazione.

## 3. Test e falsificazioni

- `python3 -m pytest Betfair/safe_strategy -q -p no:cacheprovider`: **2257 passati, 8 saltati,
  1 xfail, 0 rossi** (39,5 s). Prima della correzione dei finti: 67 rossi (tutti per
  `score_raw` assente nei finti, elenco nel par. 2).
- Test esterni che usano il motore Safe (`Betfair/stream/tests/test_live_market_types_2026_09_25.py`,
  `test_cert_banco_2026_09_16.py`, `test_banco_ambiente_dichiarato_2026_10_02.py`,
  `test_registro_impronta_2026_09_30.py`, `test_trasporto_parita_mode_d1ter_2026_09_28.py`,
  `Betfair/tests/test_consapevolezza_ordine_2026_09_16.py`,
  `Betfair/tests/test_contratto_safe_request_barriera_2026_09_17.py`,
  `Betfair/test_realtime_contratto_2026_09_12.py`): **134 passati, 11 saltati** (82,6 s).
- Falsificazione (script `scratchpad/falsifica.py`: copia di riserva, mutazione, test mirato,
  ripristino con confronto sha256 e `grep MUTAZIONE` = 0): **10 mutazioni, 10 ROSSE**
  - M1 check della fase tolto dall'ESATTO -> 2 rossi
  - M2 1T accettato (tempo 1 -> ok) -> rosso
  - M3 stato assente: fase dal solo minuto -> 3 rossi (48/66/92')
  - M4 fase ignota = ok (fail-open) -> rosso
  - M5 regola estesa anche alla BASE -> rosso
  - M6 E11 muto sul segnale -> rosso (al primo giro era VERDE: il test prendeva solo il ramo
    «check sparito»; test rifatto con due casi, poi rosso)
  - M6b E11 cieco al check sparito -> rosso
  - M7 diagnostica fase ignota spenta nel motore -> rosso
  - M8 attivita' scritta anche con ESATTO spento -> rosso
  - M9 il giro del bot non chiama la diagnostica -> rosso
  Ripristino verificato su tutti i file dopo ogni mutazione.

## 4. Migrazioni SQL
Nessuna.

## 5. Parita' paper/live
Il check vive nel motore (`evaluate_esatto`), a monte della scelta della modalita'
(`scan_and_place` -> `_modalita_di`): paper e live vedono la stessa valutazione, lo stesso
scarto e lo stesso controllo E11. Nessun ramo `paper`/`live` toccato.

## 6. Cosa NON ho fatto / NON ho potuto verificare
- **REPLAY DEL BANCO NON ESEGUITI.** Dopo il «via libera replay» ho lanciato il «prima»
  (snapshot del codice di partenza in `scratchpad/prima/`), poi e' arrivata l'aggiunta della
  patch del banco: l'ho fermato (era il mio, appena partito), ho applicato la patch allo
  snapshot e al worktree e il rilancio e' stato **NEGATO dal classificatore dei permessi**
  («Modify Shared Resources»). Non l'ho aggirato. Quindi NON ho: il confronto prima/dopo,
  l'identita' dell'ingresso 66'-70' della 35797769, l'esito del regolamento della riga ESATTO
  (atteso `won` +1,90), i tempi. Pronti per il coordinatore:
  - prima (codice di partenza + patch del banco, senza la mia correzione):
    `bash <scratchpad>/replay.sh <scratchpad>/prima prima`
  - dopo (worktree): `bash <scratchpad>/replay.sh <worktree> dopo`
  dove `replay.sh` lancia `python3 -m Betfair.stream.backtest.certifica safe_esatto 35797769
  35760084 --scenari tutti --worker 1 --data-dir /home/user/python-database-automation/_live_raw`
  (PYTHONPATH = worktree, per `tactical_engine`) e scrive `replay/<etichetta>.txt`.
  Atteso: 35797769 un solo ordine ESATTO, banca 2,00 @ 32,0 dal 66' (2T,
  `SecondHalfKickOff`), identico al prima; nessuna differenza di ordini sulla 35760084;
  differenze attese solo nei conteggi dei check (nuovo `secondHalf`) e nel controllo E11
  sollecitato (zero violazioni).
- **Gemello TS della pagina (`frontend/src/lib/safeStrategy.ts:1069`, `evaluateEsatto`)**
  fuori perimetro e NON toccato: la pagina non mostra il check «Solo nel 2o tempo» e nel
  recupero del 1T puo' indicare l'ESATTO «pronto» mentre il bot (corretto) non entra.
  Proposta: stesso check nel TS da `score_raw` (la riga della pagina e' la stessa).
  I test di parita' esistenti (default dei parametri) restano verdi perche' nessun parametro
  e' cambiato.
- Lo scarto `esatto_fase_ignota` nell'attivita' e' provato da test unitari (funzione e punto
  di chiamata), non visto in un replay ne' dal vivo.
- Suite intera del repo non lanciata (solo Safe + test esterni collegati).

## 7. Decisioni per l'utente
1. **BASE «dal 55'» e l'intervallo** (stesso difetto di D1): all'intervallo il minuto del feed
   continua a contare (misurato fino a 56'), quindi la BASE puo' entrare a partita ferma prima
   del 2o tempo. Proposta: stessa regola («solo 2o tempo», stessa funzione, una riga) anche per
   la BASE. Non fatto: la decisione di oggi riguarda solo l'ESATTO.
2. **Stato IPS vecchio**: se Betfair lascia `KickOff` con un minuto da 2T (35833626, 88'), la
   fonte unica lo dichiara ambiguo e l'ESATTO NON entra (n/d, scarto scritto). E' il
   fail-closed richiesto; da sapere: in quelle partite l'ESATTO resta fermo.

## 8. Da controllare dal vivo in paper al prossimo avvio
- Una partita in recupero del 1T con 0-0/1-0/1-1/2-1 dal 48': nella scheda Safe la
  valutazione ESATTO del bot deve avere «Solo nel 2o tempo = recupero del 1o tempo
  (KickOff)», stato no, nessuna riga in `safe_strategy_trades`.
- Dopo `SecondHalfKickOff`, dal 48': check «2o tempo (SecondHalfKickOff)» vero; ingresso
  come prima se la banca e' in 30-70.
- Attivita' Safe: nessuno scarto `esatto_fase_ignota` sulle partite col punteggio IPS
  normale; se compare, leggere `fase` (stato assente o non riconosciuto).
