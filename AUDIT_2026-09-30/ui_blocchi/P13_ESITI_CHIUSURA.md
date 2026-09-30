# P13_ESITI_CHIUSURA - referto (30/09/2026)

Worktree: `C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.claude\worktrees\agent-aef9b44f1a9ce5796`
(HEAD `4fcb867`; sopra: B2 + P13 non committati). Patch CUMULATIVA di `frontend/` (B2 + P13):
`AUDIT_2026-09-30/ui_blocchi/P13_ESITI_CHIUSURA.patch`. Master è andato avanti (P11 e altri), ma
`git diff --stat 4fcb867 master -- frontend/` non tocca nessun file del perimetro P13.

Solo presentazione: le stesse righe già in memoria, nessuna lettura nuova, `statusMetaOf`/`STATUS_META` invariati.

## 1. PRIMA -> DOPO a schermo (caso vero: Follo v Sarpsborg, 5085 con 5086 e 5093)

PRIMA (sotto la punta Under 3,5 5,00 @ 2,40):
```
↳ banca 2,36 5,08 €  ERRORE  green-up  —
↳ banca 2,36 5,08 €  ERRORE  green-up  —
FALLITA: POSIZIONE ANCORA APERTA  0% abbinato  ancora esposti 5,00 €  tutte le gambe di chiusura sono 2 annullatae: la posizione è ANCORA APERTA, nessuna contropartita è stata trovata.
```
DOPO:
```
↳ green-up: 2 tentativi, 0,00 € abbinati · 1 non abbinato (verificato su Betfair), 1 ritirato dal bot
   ↳ banca 2,36 5,08 €  NON ABBINATO (VERIFICATO SU BETFAIR)  green-up  —      (attenuata)
   ↳ banca 2,36 5,08 €  RITIRATO DAL BOT  green-up  —                          (attenuata)
FALLITA: POSIZIONE ANCORA APERTA  chiusura abbinata 0%  ancora esposti 5,00 €  le 2 gambe di chiusura sono finite senza abbinare nulla (2 annullate): la posizione è ANCORA APERTA, nessuna contropartita è stata trovata.
```
(i badge sono `uppercase` via CSS; nel DOM: «RITIRATO dal bot», «NON ABBINATO (verificato su Betfair)»). Ogni badge ha un
`title` con la spiegazione dell'esito.

Altri testi:
- title del «chiudi ora» della riga (`cr-op-chiudo-ora`): «quanto varrebbe chiudere ADESSO, per intero, al prezzo corrente · <fonte>» -> «P&L netto di commissione chiudendo ADESSO, per intero, al prezzo corrente · <fonte>»; cifra `cr-op-chiudo-ora-pnl`: nessun title -> «P&L netto di commissione se chiudi per intero adesso».
- chip «banca» in `DettaglioRigaView.tsx` (gambe di chiusura e riga della posizione): `pink` -> `rose`.
- una sola gamba fallita: «la gamba di chiusura è annullata» -> «la gamba di chiusura è finita senza abbinare nulla (annullata)».

## 2. Mappa esito -> etichetta (solo righe `status='error'`, `lib/tradeStatus.ts` `esitoOrdineMeta`)

| dato sulla riga | etichetta | chi lo scrive (Python, sola lettura) |
|---|---|---|
| `meta.esito_ordine='ritirato_da_noi'` | RITIRATO dal bot | Mike `service.py:639`, `:5532-5536` (`_mark_trade_cancelled`, esito di ripiego), `:1703-1706` (runner, appoggiata annullata) |
| `meta.reason='cancelled_by_engine'` senza `esito_ordine` (righe prima del 29/09) | RITIRATO dal bot | Mike `service.py:4307` |
| `meta.reason='reconciled_not_placed'` senza `esito_ordine` | NON ABBINATO (verificato su Betfair) | Mike `service.py:5419-5424`, decisione `safe_strategy/execution.py:1056-1101` (`free`: nessun ordine con quel riferimento fra i vivi/chiusi, o chiuso con 0 abbinato; `error`: riga > 24 h non trovata) |
| `meta.esito_ordine='rifiutato'` | RIFIUTATO da Betfair: `<codice>` (codice da `statoOrdine().errorCode`: `meta.error_code`, `live_rifiutato:<C>`, `live_not_matched:<stato>:<C>`), senza codice «RIFIUTATO da Betfair (codice non dichiarato)» | Mike `service.py:640`, `:646-653`, `:974`, `:1703`, `:5534`; formati della nota `execution.py:919-921`, `:985-987` |
| `meta.esito_ordine='non_abbinato_fok'` | NON ABBINATO (tutto o niente) | Mike `service.py:641`, `:651-652`, `:1706` |
| `meta.esito_ordine='cancellato_da_betfair'` | CANCELLATO da Betfair | Mike `service.py:642`, `:2658-2660`, `:1704`, `:5535` |
| `meta.esito_ordine='fermato_da_noi'` | FERMATO dal bot (mai inviato) | Mike `service.py:643`, `:649-650` |
| qualunque altro valore / nessun campo | NESSUNA etichetta nuova: resta `statusMetaOf` («ERRORE», «ERRORE (definitivo)») | fail-closed |

Chi scrive quei campi: SOLO Mike (grep di `esito_ordine`, `cancelled_by_engine`, `reconciled_not_placed` in `Betfair/**`, test esclusi).
Omega e Safe non li scrivono: per loro nulla cambia (test con i `meta` veri di Omega `_leg_certain_failure`/`error_final` e di Safe `live_rifiutato:<C>`, `live_not_matched:<stato>`: `esitoOrdineMeta` = null e il badge di `dettaglioDi` è identico a `statusMetaOf`).
Scelta: la riga `live_rifiutato:<C>` di Safe NON diventa «RIFIUTATO da Betfair» (Safe non scrive `esito_ordine`; il vincolo era «per chi non li scrive nulla cambia»). Si può estendere dopo, su richiesta.

Nota sulla parola: il brief proponeva «NON PIAZZATO (verificato sul conto)» per `reconciled_not_placed`. Ho scritto
«NON ABBINATO (verificato su Betfair)» perché `reconcile_decision` rende `free` anche per un ordine che c'era ed è stato chiuso con 0 abbinato (lapsed/cancellato): «non piazzato» sarebbe falso in quel caso; «0 abbinato» è vero in tutti i casi. La verifica è sugli ordini di Betfair (vivi e chiusi), non sul saldo del conto.

## 3. Raggruppamento dei tentativi (`DettaglioRigaView.tsx`, `Chiusure`)

Gambe di chiusura in stato `error` con lo stesso tipo d'uscita (`meta.exit_kind`) e almeno 2: una riga
`<tipo>: N tentativi, X abbinati · <conteggio per esito>` (testid nuovo `cr-…-chiusure-gruppo`) e sotto le righe, attenuate
(`opacity-60`), ciascuna con il suo esito vero (testid `-riga` invariato). Un esito ignoto dentro un gruppo resta «ERRORE» e il
riepilogo lo conta («1 ERRORE»). «X abbinati» = somma di `statoOrdine().abbinato`; se il dato non è dichiarato vale 0 perché
i servizi scrivono `error` solo senza abbinato (Mike `service.py:5537-5548` con abbinato -> `open`; `:972` rifiuto; Safe/condiviso
`execution.py:905-925`). Una gamba sola: nessun gruppo.

## 4. Striscia «FALLITA: posizione ANCORA APERTA» (resta, §8.5)

- «0% abbinato» -> «chiusura abbinata 0%» (title «quota della posizione che le gambe di chiusura hanno abbinato»), testid nuovo `…-copertura`.
- refuso: nasceva da `lib/certezzaChiusura.ts` (`annullata${n>1?'e':''}` -> «annullatae», stesso difetto per «rifiutatae»). Frase nuova: «le N gambe di chiusura sono finite senza abbinare nulla (2 annullate)».
- «protetta dalla copertura sulla linea 4,5»: NON scritto. La riga (`OperazionePartita` di 5085) porta solo le sue gambe di chiusura (`closes_trade_id`); la banca Under 4,5 (5094) è un'altra operazione della partita, non collegata alla riga né al dettaglio. Per dirlo servono le altre righe della partita (`SchedaPartita.tsx`/`useControlRoom.ts`, fuori perimetro) o un campo del servizio: da decidere.
- Nota: `statoOrdine` classifica le due gambe come «annullate» (`meta.phase='cancelled'`); non l'ho toccato (fuori perimetro). La frase dice «annullate» anche per 5086 (non abbinata per riconciliazione): vero nel senso dell'ordine (fase `cancelled` scritta dal servizio).

## 5. File

Toccati in P13: `frontend/src/lib/tradeStatus.ts` (solo aggiunta `esitoOrdineMeta`/`EsitoOrdineMeta`), `frontend/src/components/controlroom/dettaglioRiga.ts`,
`DettaglioRigaView.tsx`, `StrisciaEsitoChiusura.tsx`, `frontend/src/lib/certezzaChiusura.ts`.
Nuovi: `frontend/src/components/controlroom/P13EsitiChiusura.test.tsx` (13 test); fuori da `frontend/`: `AUDIT_2026-09-30/ui_blocchi/falsifica_P13.cjs`, questo referto, STATO.
Test esistenti cambiati in P13: nessuno.

## 6. Test e numeri

- Nuovo `P13EsitiChiusura.test.tsx` (13): mappa (6 casi, compreso fail-closed e Omega/Safe invariati), caso vero 5085/5086/5093 (nessun «ERRORE» nel DOM, «green-up: 2 tentativi, 0,00 € abbinati», le due righe con l'esito vero, striscia `CHIUSURA_FALLITA` con «ANCORA APERTA», «chiusura abbinata 0%», «ancora esposti 5,00 €», niente «annullatae»), riga principale, tentativo singolo, esito ignoto nel gruppo, chip rose (chiusure e riga LAY), title netti.
- Finti: chiavi di `_trade_row` (`service.py:563-590`: phase, leg_ref, final, exit_kind, exit_reason, closes_ref) + reason/esito_ordine/reconciled come li scrivono `:5422-5424` e `:5532-5548`; colonne di consapevolezza.
- `npx tsc -p tsconfig.app.json --noEmit`: 0 errori.
- Vitest finale mirato: vedi §8 (numeri inseriti a fine lancio).

## 7. Falsificazioni (`node AUDIT_2026-09-30/ui_blocchi/falsifica_P13.cjs`; copie fuori dal repo, ripristino dalla copia, confronto byte a byte; `git diff` dopo = identico a prima, `cmp`)

17/17 ROSSE, tutte «RIPRISTINATO (identico alla copia)»:
P01 chiusure col badge di prima -> 2 rossi · P02 riga principale senza esito -> 1 · P03 ritirato non riconosciuto -> 4 · P04 riconciliato non riconosciuto -> 4 ·
P05 esito anche su righe non 'error' -> 1 · P06 esito ignoto reso «tranquillo» -> 3 · P07 Omega/Safe `live_*` rimappati -> 1 · P08 niente gruppo -> 2 ·
P09 conteggio tentativi sbagliato -> 1 · P10 abbinati sbagliati -> 1 · P11 striscia senza «chiusura» -> 1 · P12 refuso «annullatae» -> 1 · P13 frase gamba singola -> 1 ·
P14 chip pink nelle chiusure -> 1 · P15 chip pink sulla riga -> 1 (al primo giro era verde: mancava il test di una riga LAY, aggiunto e rilanciato) · P16 title «chiudi ora» -> 1 · P17 title cifra -> 1.

## 8. Vitest finale

`npx vitest run --maxWorkers=2 src/components/controlroom src/components/trading src/pages/ControlRoom.test.tsx src/lib/tradeStatus.test.ts src/lib/certezzaChiusura.test.ts src/lib/statoOrdine.test.ts src/lib/interruttori.test.ts src/lib/interruttoriUscite.test.ts src/pages/Omega.test.tsx src/pages/SafeStrategy.test.tsx src/pages/SafeStrategy.audit.test.tsx src/pages/Mike.test.tsx src/components/mike/MikeEventPnlTable.test.tsx`
-> **81 file, 1399 passati, 1 saltato, 0 falliti** (583 s), sull'albero B2 + P13.
Test di certificazione `src/certification/*.cert.test.tsx`: non usano `dettaglioDi`, `Chiusure`, `StrisciaEsitoChiusura`, `certezzaChiusura` né `esitoOrdineMeta` (grep), e `statusMetaOf` non è cambiato: nessun significato toccato. Non lanciati (DB vero).
Patch cumulativa: 23 file di `frontend/` (B2 + P13), `git apply --check -R` OK.

## 9. COSA NON HO FATTO

- «protetta dalla copertura sulla linea 4,5» (vedi §4): il dato non è nella riga.
- Nessuna modifica a `statoOrdine.ts` (la striscia chiama ancora «annullata» una gamba non abbinata per riconciliazione), a `SchedaPartita`, `useControlRoom`, `lib/mike.ts` (`MIKE_ESITO_ORDINE_LABEL` resta la mappa della pagina di Mike: stesse cose con parole un po' diverse, «ritirato da Mike» contro «RITIRATO dal bot»; da unificare in un blocco su `lib/mike.ts`).
- Safe `live_rifiutato:<C>` resta «ERRORE (definitivo)» (vedi §2).
- Nessun commit, build, suite intera.

## 10. COSA NON HO POTUTO VERIFICARE

- **App non vista a schermo** (lunghezza della riga di riepilogo, resa dell'attenuazione).
- Le righe vere 5085/5086/5093 NON le ho lette dal DB (nessuna lettura, da brief): i finti seguono il codice che le scrive e il referto del progetto (§0); in particolare non so se 5086 ha `size_matched` a null o 0 (il test copre null su 5086 e 0 su 5093).
- Su questo albero (base 4fcb867) il «chiudi ora» col prezzo al ms è ancora LORDO: il title «netto di commissione» diventa vero con P11 (`e300949`, già su master). Da non integrare senza P11.

## Verifica del coordinatore UI (admin-07), 30/09 18:55
- Terzo giro, albero integrato (`1d058a7` + C_P12a + B1bis + P13 + T_P4 + G_P7): `npx tsc -p tsconfig.app.json --noEmit` = 0 errori; `npx vitest run src/components/controlroom src/components/trading src/pages/ControlRoom.test.tsx` + 9 test di lib toccati = 91 file, 1478 test verdi.
- La patch in QUESTA cartella e l INCREMENTALE ricavato da me sul master `f58b595`; ordine di applicazione: `B1bis.patch` → `P13_ESITI_CHIUSURA.patch` → `T_P4.patch` → `G_P7.patch` (fusione a tre vie senza conflitti; su ogni file toccato il risultato e identico byte per byte all albero verificato).
- `esitoOrdineMeta` letta per intero: si applica SOLO a righe `error`; esito ignoto o assente = resta ERRORE (fail-closed). Mutazioni MIE (oltre le 17 del delegato), ROSSE: ogni riga error diventa «RITIRATO dal bot» (8 rossi); l esito applicato anche a righe non error (1).
- Da sapere: «NON ABBINATO (verificato su Betfair)» al posto di «NON PIAZZATO» e una scelta motivata del delegato (`reconcile_decision` restituisce free anche per un ordine chiuso con 0 abbinato). Resta da unificare con le parole di `MIKE_ESITO_ORDINE_LABEL` in `lib/mike.ts` (file dell altra sessione).
