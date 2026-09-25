# Residui B17 (25/09): cash out globale per ordine, "Chiudi" e combo al ms, Mike per chiave

Delegato, worktree `agent-a665665e5686d70dd`, base `099412c` (contiene `f4af173`). Niente commit.
Chiude i punti di "Non fatto" di `SCHEDE_ABBINAMENTO_PREZZO.md` (§6.2 Mike per correlazione) e di
`DRYRUN_E_ESECUZIONE_A_MERCATO.md` (cash out globale senza esito per ordine; "Chiudi" e combo non al ms).

**Rebase su `931c11b`: NON fatto.** Il commit WIP temporaneo che serviva a fare il rebase
(`git add` dei file toccati + `git commit` + `git rebase origin/master`) e' stato **rifiutato dal
classificatore dei permessi** ("Modify Shared Resources"); dopo il rifiuto anche `git status` e' stato
rifiutato. Nessun commit e' stato creato (verificato: `git diff HEAD --stat` = solo i file modificati,
nessun file nuovo in stage). Il rebase va fatto dal coordinatore (vedi §6).

## 1. Cash out globale di partita (`CashOutPartita`)

**Prima.** Il clic accodava `safe_request('cashout_event', {event_id})` e mostrava solo lo stato della
richiesta (e, col prop `esito`, la gamba piu' recente). Il servizio (`_request_cashout_event`) restituiva
`chiuse` = id delle POSIZIONI chiuse, non gli id degli ORDINI generati: la scheda non poteva sapere quali
righe erano gli ordini del cash out senza indovinarle.

**Dopo.**
- Servizio (`Betfair/safe_strategy/bot_service.py:3326-3376`): per ogni posizione chiusa (o fallita DOPO
  aver piazzato) si raccoglie il `closing_trade_id` che `execution.close_trade` gia' restituisce; il
  risultato porta in piu' `closing_trade_ids: [...]` e `gambe: [{trade_id, closing_trade_id, ok}]`, e le
  voci di `non_chiuse` portano `closing_trade_id` se l'ordine era partito. `_id_ordine` (:3370) scarta
  0/negativi/non numeri. Nessuna decisione cambia (stesse righe, stessi rami, stesso messaggio).
- Omega: non ha un `cashout_event` (kind accettati `omega_service.py:4891-4901`: refresh/load/place/
  cashout). Mike: il cash out di partita (`cashout`/`flatten`) non e' montato su `CashOutPartita` (vive in
  `MikeCashOutButton` sulla pagina Mike); il «Chiudi» di riga di Mike passa dal seguito per correlazione
  gia' esistente. `CashOutPartita` in Control Room parla solo con Safe (`ControlRoom.tsx:713,734`).
- Pagina:
  - `useControlRoom.ts:3338-3363` `cashOutEvento`: prende l'id della richiesta (`cashOutEventoSafe` lo
    restituiva gia', era ignorato) e segue il clic con chiave `safe:cashout-partita:<event>`,
    `soloIdDichiarati: true`, modalita' = quella delle righe vive di Safe sulla partita (se una sola).
  - `lib/esitoAbbinamento.ts:342-376` `gambeDelClicDettaglio`: con `soloIdDichiarati` NIENTE ripiego per
    partita (regola 2): o gli id del `result`, o nessuna gamba. `:293` `nonChiuseDaRisultato`,
    `:309` `chiaveCashOutPartita`, `:614-621` cash out eseguito senza nessun ordine = esito terminale
    (non 3 minuti di "in attesa").
  - `useSeguiOrdini.ts`: la riga della coda porta anche `nonChiuse`; ogni esito porta `richiesta` e
    `modoGambe`.
  - `EsitoAbbinamentoStriscia.tsx:90-140` `righeOrdiniCashOut` + `EsitoOrdiniCashOut`: una riga per ogni
    ordine dichiarato (stesse parole di B17) o «in attesa della riga», poi le posizioni NON chiuse.
  - `CashOutPartita.tsx:64-70,187-191`: legge il seguito dal contesto della Control Room e monta il
    dettaglio (senza contesto non monta niente).

Esempio (testi inchiodati in `ResiduiB17.schede.test.tsx`):
```
ordine #1001: ABBINATO TOTALMENTE a prezzo medio 2,30 (Δ vs visto —, vs segnale —), size 5,00 €
ordine #1002: ABBINATO PARZIALMENTE: 1,50 € su 4,00 € a 3,10 (Δ vs visto —, vs segnale —), resto 2,50 € in attesa sul book
posizione #903 NON chiusa: rifiutato: stato hedged
ordine #1002: in attesa della riga dell'ordine
nessun ordine di chiusura partito: cash out globale: 0 posizioni chiuse, 0 riserve annullate, 1 NON chiuse (vedi dettaglio)
```
Δ «—»: il cash out globale non ha un prezzo visto per ordine (e' un gesto di partita).

## 2. «Chiudi» di riga e gambe delle combo al ms PRIMA del clic

**Prima.** «chiudi ora» (prezzo e P&L bloccabile) veniva da `chiusuraViva` sul feed dello scanner
(`useControlRoom.ts`, `prezzoVivo`); le gambe delle combo da `prezziViviGambe` (scanner); la scheda combo
passava `sorgente: isCombo ? null : ...` (nessun ladder al ms per le combo).

**Dopo.**
- `lib/chiusuraAlMs.ts` (nuovo, puro): `chiusuraAlPrezzo` (stessa `greenPrice`/`partialLockedPnl` di
  sempre), `ripiegoScanner`, `testoFonte`, `valutaComboAlMs`.
- `useControlRoom.ts:2479-2530` `chiusuraViva` aggiunge `alMs` = esposizione (win/lose), market/selection,
  sport, i due lati dello scanner e il loro istante (`odds_ts_ms`, se no `updated_at`).
- `components/controlroom/useChiusuraAlMs.ts` (nuovo): `usePrezzoAlMs` sul mercato della riga (stessa
  sorgente delle schede proposte), P&L ricalcolato a ogni tick; ripiego scanner dichiarato.
- `DettaglioRigaView.tsx:277-280,330-356,362` (righe della scheda partita) e `ControlRoom.tsx:1419-1507`
  (posizioni orfane): prezzo, P&L, fonte ed eta' al ms; al clic il prezzo A VIDEO + contesto va alla
  scheda (`BottoneChiudiRiga.prezzoAlClic`, `chiudiRiga.ts:81-82` `prezzoVisto/contestoVisto`,
  `useControlRoom.ts:3239`). **Il payload della richiesta NON cambia** (`INVIO` costruisce il payload campo
  per campo; test dedicato).
- La sorgente arriva dal contesto (`ChiusuraRigaApi.sorgenteLadder`, `ControlRoom.tsx` `SORGENTE_LADDER_RIGHE`).
- Combo: `usePrezzoAlMs.ts:78-127` `usePrezziAlMs` (una sottoscrizione per mercato, N gambe);
  `SchedaPropostaOpportunita.tsx:224-255` prezzi per gamba al ms con ripiego scanner, tick vs proposta,
  fonte per gamba (`cr-opp-combo-gamba-fonte`); semaforo e EV ricalcolati (`:258`, `:271-274`, `:521-533`);
  al clic partono i prezzi a video con la fonte PEGGIORE fra le gambe e l'eta' della piu' vecchia.

**EV della combo, cosa e' e cosa non e'.** Il motore (`combos._evaluate`) pubblica `ev` = profitto netto
bloccato nel caso PEGGIORE per euro. Gli esiti della partita non sono sulla proposta, quindi la scheda NON
ricalcola il lock esatto: mostra un **limite inferiore certo** `evMinimo = ev - somma(size*|Δp|)/S` sulle
sole gambe mosse CONTRO (back scesa, lay salita; la commissione non amplifica una perdita). Semaforo:
SI = nessuna gamba contro; QUASI = qualche gamba contro, limite > 0; NO = limite <= 0 o prezzo mancante.
E' una lettura prudente, non un criterio nuovo della strategia (PIAZZA resta acceso, decide il servizio).

Esempi:
```
chiudi ora 1,80 +1,11 € ladder al ms, 0,4 s fa
chiudi ora 1,90 +0,52 € prezzo dello scanner, 12 s fa (il canale non porta questo mercato)
gamba 1: 1,90  proposta 2,00 (-10 tick contro)  0,4 s fa · canale al ms
gamba 3: 5,00  proposta 5,00                     8,0 s fa · feed scanner (mercato non seguito dal runner)
EV ora (almeno): 0,010 (proposta 0,050) · semaforo QUASI
⚠ combinazione al prezzo di adesso: profitto bloccato almeno 0,010 per euro (proposta 0,050): almeno una gamba si e' mossa contro: il profitto bloccato e' sceso
```

## 3. Mike: gambe dell'approvazione per CHIAVE

**Prima.** La scheda (`PropostaUscitaMike` -> `seguiClic`) attribuiva al clic le righe NUOVE di Mike sulla
partita coi ruoli proposti: una protezione nata nello stesso istante veniva presa per l'uscita approvata.

**Dopo (servizio, `Betfair/mike/service.py`; `engine.py` NON toccato).** Righe del mio diff su
`mike/service.py` (per il delegato R3 del kill-switch):
- `:502-514` `_trade_row(..., approvazione_id=None)` -> `meta.approvazione_id`;
- `:580` `execute_place(..., approvazione_id=None)`, `:695-696` lo passa a `_trade_row`;
- `:1198` `_piazza_resting_live(..., approvazione_id=None)`, `:1246-1247` lo passa a `_trade_row`
  (il blocco kill-switch di `_piazza_resting_live` NON e' toccato);
- `:2385` `process_requests` passa `request_id=rid` ad `approva_uscita`;
- `:2445-2478` `_id_approvazione`, `_approvazione_eseguita`, `_chiave_gamba` (nuove);
- `:2482-2506` `_request_approva_uscita` salva `request_id` in `ctx.uscita_approvata`;
- `:3602` gambe differite (paper con bet delay) portano la chiave; `:3606-3612` si legge l'approvazione
  PRIMA di `E.decide` e, se la telemetria `uscita_eseguita_su_approvazione` ha la STESSA chiave, si ha l'id;
  `:3666,3671,3681-3683,3691` la chiave va SOLO sulle gambe di ruolo `E.USCITE_DISCREZIONALI`;
  `:3693-3697` l'attivita' `uscita_eseguita_su_approvazione` porta `approvazione_id`.

**Pagina.** `esitoAbbinamento.ts:369-372`: prima le righe con `approvazioneId === requestId` (modo
`chiave`); solo se nessuna riga la porta, il ripiego per correlazione, che esclude le righe con la chiave
di un'ALTRA approvazione; `EsitoAbbinamentoStriscia.tsx:57-64` lo dichiara a video:
```
gambe: ordini con la chiave dell'approvazione, scritta dal servizio sulla riga
gambe: RIPIEGO: righe nuove del bot sulla partita dopo il clic (nessuna riga porta la chiave della richiesta)
```

## 4. Test e falsificazioni

- vitest (file toccati + vicini, 23 file): **475 test, tutti verdi** dopo 2 adeguamenti di contratto:
  `ControlRoom.test.tsx` (vm.chiudi riceve in piu' `prezzoVisto`/`contestoVisto`, solo per la scheda) e
  nessuna modifica a `esitoAbbinamento.test.ts` (la chiave `approvazioneId` compare solo sulle righe che
  la portano). Nuovi: `lib/chiusuraAlMs.test.ts` (10), `ResiduiB17.schede.test.tsx` (15),
  `useControlRoom.test.tsx` +1 ("residui B17").
- `npx tsc -p tsconfig.app.json --noEmit`: **0 errori**.
- pytest (sandbox SUPABASE a 127.0.0.1:9): nuovi `test_cashout_event_ids_b17_2026_09_25.py` (9) e
  `test_mike_chiave_approvazione_b17_2026_09_25.py` (18); `test_chiusura_dell_utente_2026_09_16.py`
  (32), `mike/test_mike_service`, `uscite_automatiche`, `certificazione_ui`, `allineamento_ui` (109) e i
  file Mike che toccano `execute_place`/`_piazza_resting_live`/`_trade_row` (211): tutti verdi.
- Falsificazione: `AUDIT_2026-09-25/mutazioni_schede_residui.py`, log `falsificazione_schede_residui.txt`
  (vedi §5).

## 5. Falsificazione (20 mutazioni)

Controllo senza mutazioni: i 5 comandi VERDI. **20/20 mutazioni ROSSE, md5 ripristinato** (14 TS, 6 PY):
TS1 cash out per correlazione invece che per id · TS2 Mike chiave ignorata · TS3 chiave altrui nel
ripiego · TS4 cash out senza ordini = attesa infinita · TS5 posizioni non chiuse taciute · TS6
`non_chiuse` non lette dalla coda · TS7 clic senza `soloIdDichiarati` · TS8 P&L del «Chiudi» dallo
scanner invece che dal ms · TS9 ripiego non dichiarato · TS10 prezzo visto non passato al clic · TS11
prezzo visto finito nel payload · TS12 gamba contro non contata nell'EV combo · TS13 combo senza ladder
al ms · TS14 combo: al clic i prezzi dello scanner · PY1/PY2 Safe senza `closing_trade_ids` · PY3 chiave
anche sulle coperture · PY4 `request_id` non salvato · PY5 chiave senza confronto · PY6 chiave non
scritta sulla riga. Log: `falsificazione_schede_residui.txt`.

## 6. Non fatto / non verificato

1. **Rebase su `931c11b` non fatto** (permesso negato al commit WIP, §0). `931c11b` tocca
   `mike/service.py` e `safe_strategy/bot_service.py` (`resolve_event_lambdas` ~:6658 + funzione nuova):
   le mie modifiche su `bot_service.py` sono in `_request_cashout_event` (~:3290-3376, lontano) e su
   `mike/service.py` nelle righe elencate al §3. Da rifare: `git stash`/WIP, rebase, rilancio dei test.
2. Mike: la chiave copre gli ordini nati nel giro dell'approvazione. I **seguiti** della stessa uscita
   nei giri dopo (riprezzo/residuo, `engine._uscita_gia_in_corso`) non portano la chiave: la scheda
   segue la prima gamba; i riprezzi restano visibili nelle righe della partita. Dare la chiave anche a
   quelli richiederebbe tenere "l'approvazione in corso" nel servizio oltre il giro: non l'ho fatto.
3. Il cash out globale non ha un prezzo visto per ordine: Δ = «—» (e' un gesto di partita).
4. «Chiudi» di Mike: le righe di Mike hanno `market_id/selection_id` dal 23/09; le righe storiche senza
   restano sul prezzo dello scanner dichiarato ("eta' non pubblicata").
5. EV combo: limite inferiore, non il lock esatto (gli esiti della partita non sono sulla proposta).
6. Non rieseguiti: banco/replay, suite intere, `npm run build`, prova nell'app viva.
7. Junction `frontend/node_modules` e `.venv` create nel worktree: toglierle con `cmd /c rmdir`, mai
   `--force`.

## 7. File

`git diff > AUDIT_2026-09-25/schede_residui.patch` (file tracciati). Nuovi:
- `frontend/src/lib/chiusuraAlMs.ts` + `chiusuraAlMs.test.ts`
- `frontend/src/components/controlroom/useChiusuraAlMs.ts`
- `frontend/src/components/controlroom/ResiduiB17.schede.test.tsx`
- `Betfair/safe_strategy/tests/test_cashout_event_ids_b17_2026_09_25.py`
- `Betfair/mike/tests/test_mike_chiave_approvazione_b17_2026_09_25.py`
- `AUDIT_2026-09-25/mutazioni_schede_residui.py`, `falsificazione_schede_residui.txt`, questo file.
