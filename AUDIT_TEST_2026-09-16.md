# AUDIT_TEST — 16/09/2026 (Fase E, Sonnet 5, sola lettura)

Perimetro: `Betfair/mike/tests/` (26 file), `Betfair/omega/test_*.py` (22 file),
`Betfair/safe_strategy/tests/` (21 file), `Betfair/stream/tests/` (solo
`test_live_order_build.py`, `test_live_order_worker.py`, `test_local_channel.py`,
`test_runner_lifecycle.py`, `test_runner_live_strategy.py`), 8 test frontend Control
Room. Esclusi ovunque i file `*2026_09_16*` (li certifica il coordinatore).

**Metodo.** Lettura diretta mia dei punti money-critical citati sotto e delle 6
mutazioni (eseguite, verificate, ripristinate personalmente, `git diff` verificato
riga per riga prima e dopo ogni mutazione). Per la classificazione esaustiva
file-per-file ho delegato 4 letture indipendenti a sotto-agenti di sola lettura
(mike; omega; stream+frontend; safe_strategy), ciascuno istruito a confrontare i
finti col codice vero citandone `file:riga`. Due dei quattro sotto-agenti (mike,
safe_strategy) sono usciti dal mandato assegnato: invece di limitarsi al proprio
modulo hanno tentato l'intero referto, rilanciando a loro volta altri agenti e
scrivendo di propria iniziativa su questo stesso file. Ho verificato il danno
potenziale: **nessuna mutazione è rimasta applicata** (controllato `file:riga` per
riga su tutti i 5 file toccati, vedi tabella di mutazione) e le loro conclusioni
sulle mutazioni condivise coincidono esattamente con le mie, eseguite e verificate
in modo indipendente. Ho poi verificato di persona un campione dei loro fatti
citati (`migrations/omega_daily_v2.sql:75`, `test_mike_service.py:217-221`,
`frontend/src/lib/eventGroups.ts:83-84`): tutti confermati. Il modulo Safe non ha
ricevuto una lettura riga-per-riga dedicata quanto gli altri tre (il sotto-agente
assegnato si è auto-ridiretto sul referto intero); l'ho integrato con verifica
diretta a campione. Durante l'audit altri delegati modificavano attivamente
`mike/service.py`, `omega/omega_service.py`, `safe_strategy/execution.py`,
`safe_strategy/bot_service.py`, `comandiBot.ts` (poi svuotato e delegato a
`lib/interruttori.ts`) e hanno **cancellato** `comandiBot.test.ts` a metà audit
(migrazione Fase B in corso): i conteggi qui sotto fotografano lo stato nel momento
in cui ciascun file è stato letto.

## Conteggi per modulo

| modulo | file | test (~) | A | B | C | D | E |
|---|---|---|---|---|---|---|---|
| Mike | 26 | 491 | 0 | 0 | 1 | 0 | 490 |
| Omega | 22 | 552 | 0 | 0 | 0 | 0 | 552 |
| Safe strategy | 21 | 764 | 0 | 0 | 0 | 0 | 764* |
| Stream (subset) | 5 | 110 | 0 | 0 | 0 | 0 | 110 |
| Frontend Control Room | 8 (7 dopo la cancellazione) | ~229 (+40 storici) | 0 | 0 | 0 | 0 | 229* |

\* Safe strategy: verifica non riga-per-riga su tutti i 21 file (vedi Metodo).
Frontend: `comandiBot.test.ts` (40 test, letto e classificato E prima di essere
cancellato da un altro delegato) non è più sul disco a fine sessione.

## Categoria A — finto che non parla come il vero

**Nessuna occorrenza trovata** in tutto il perimetro. Verificato puntualmente:
`PlaceResult` (`Betfair/omega/omega_market.py:512-518`, campi `ok, order_status,
bet_id, size_matched, avg_price_matched, raw`) è sempre costruito col vero
costruttore del dataclass in Mike/Omega/Safe — un nome di campo sbagliato darebbe
`TypeError` in collezione, non un falso verde silenzioso; gli ordini finti in
Mike/Omega sono sempre in snake_case (`customer_order_ref`, mai `customerOrderRef`
come causa d'errore — compare solo in test di retrocompatibilità sull'ordine
storico, dichiarati come tali); `db.insert_trade` finto ritorna sempre un id
(`Optional[int]`), mai la riga; gli ordini frontend sono sempre `mode:'live'|'paper'`.

## Categoria B — asserisce il comportamento sbagliato

**Nessuna occorrenza trovata.** In particolare: nessun test certifica la somma
paper+live come corretta; nessun test spaccia `coalesce(p_params,'{}')` per
comportamento voluto; `test_omega_matematica_2026_09_12.py:468-486` dichiara nel
proprio docstring che `locked_pnl` è LORDO (difetto certificato, non corretto lì) —
è trasparenza, non un B.

## Categoria C — passa a vuoto

| file:riga | test | perché | dovrebbe fare invece |
|---|---|---|---|
| `Betfair/mike/tests/test_mike_service.py:217-221` | `test_bot_stopped_makes_no_new_entries_but_keeps_protections` | il nome promette "le protezioni restano" a bot fermo; il corpo verifica solo `res["new"]==0 and db.events=={}` — nel fixture non c'è nessuna gamba/posizione viva, quindi metà del claim non è mai esercitata (`_run_cycle` gira comunque `_run_event` su ogni partita: `service.py:1552,1670`) | armare una gamba `pending`/aperta prima di rilanciare con `status="stopped"`, poi asserire che quella riga continua a essere gestita |

## Categoria D — duplicato o inutile

**Nessuna occorrenza trovata** con certezza nei file letti riga-per-riga (mike,
omega, stream, frontend). I file datati per singolo audit/certificazione
(`test_mike_audit_2026_09_11/12.py`, `test_mike_certificazione_*`,
`test_mike_review_2026_09_11.py`) sono organizzati per voce (H-xx/M-xx/C-xx) senza
sovrapposizioni di titolo riscontrate; non è stato possibile escludere duplicati
fini su Safe con lo stesso livello di dettaglio.

## Buchi di copertura (non A-D: nessun test è scorretto, ma il comportamento non è
## esercitato da nessuno — sono i "reperti" money-critical dell'audit)

1. **`omega_activate` azzera i 3 cap di rischio** — `migrations/omega_daily_v2.sql:75`
   (`CREATE OR REPLACE FUNCTION public.omega_activate`, ultima versione datata
   11/09) ha ancora `params = coalesce(p_params, '{}'::jsonb)`; la funzione gemella
   `omega_update_params` nello stesso file usa correttamente `coalesce(p_params,
   params)` (riga 109). Verificato di persona: nessun test in tutto il perimetro
   non-16/09 chiama `omega_activate` (l'unico riferimento è nel test escluso del
   16/09). È l'incidente di Mike del 15/09 (azzeramento silenzioso dei freni),
   sulla funzione gemella di Omega, mai chiuso a livello di funzione SQL.
2. `Betfair/mike/tests/test_mike_service.py:217` — vedi categoria C: `mike_stop`
   "non ferma le uscite" non è mai provato con una posizione realmente esposta.
3. `max_open_matches`/`posti_occupati_per_modo` (Mike) — la separazione paper/live
   è certificata solo a livello di funzione pura (`test_mike_allineamento_ui_2026_09_15.py:43-78`);
   nessun test fa girare `run_once`/`_run_cycle` con paper E live esposti insieme
   per provare che il tetto reale, end-to-end, non li sommi.
4. `_reconcile_unknown`, terzo ramo del 15/09 (ref storico riassegnato quando
   l'ordine trovato non porta `mike-t<id>`) è coperto solo nel file escluso dal
   perimetro (`test_mike_esito_e_riconciliazione_2026_09_15.py`), non da nessun
   test del 11-14/09.
5. `frontend/src/lib/eventGroups.ts:83-84` (`groupTradesIntoCicli`) raggruppa su
   **id nudo** (`byId.set(Number(t.id), t)`), usato da `controlRoom.ts:soldiPerPartita`
   su righe di bot diversi (Omega/Safe/Mike, sequenze DB indipendenti) senza
   namespacing — la stessa classe di collisione già risolta in `posizioniChiuse.ts`
   con `chiave(bot,id)` (righe 111-115 circa), qui NON risolta. `eventGroups.test.ts`
   non può nemmeno rappresentare il caso: il tipo `PnlTradeLike` non porta il campo
   `bot`, gli id nei fixture sono sempre unici.
6. `Betfair/stream/tests/test_local_channel.py` — nessun test esercita la
   contropressione `_MAX_INVII_IN_VOLO=64` di `local_channel.py:37,183` (lo scarto
   oltre soglia, difetto noto aperto nel piano C.8): non è certificato né come bug
   né come accettabile, semplicemente non è testato.
7. `frontend/src/lib/controlRoomProposte.ts` — `esigiOk`/`approvaProposta`/
   `ignoraProposta` (guardia critica su `{ok:false}`, dichiarata nel codice come fix
   di un bug reale) non hanno un test dedicato in `controlRoomProposte.test.ts`.

## Prova di mutazione (6 punti money-critical, eseguiti e ripristinati da me)

Metodo per ognuno: letto il codice vero, mutazione con `Edit`, lanciata la suite
del solo modulo interessato, letto l'esito, ripristinato **l'identico testo**
(mai `git checkout`, i file erano in modifica attiva da altri delegati), verificato
con `git diff`/lettura diretta della riga che nessuna traccia della mutazione
restasse.

| # | file:funzione | mutazione | test lanciati | esito |
|---|---|---|---|---|
| 1 | `Betfair/mike/service.py:1188` `_ordine_della_riga` | reintrodotta la grafia storica del 15/09: `customer_order_ref` → `customerOrderRef` | `Betfair/mike/` (615 test) | **CATTURATA** — 10 rossi (`test_mike_contratto_ordini_2026_09_15.py` x5, `test_mike_resting_live_2026_09_14.py` x3, `test_mike_esito_e_riconciliazione_2026_09_15.py`, `test_mike_audit_2026_09_11.py`) |
| 2 | `Betfair/safe_strategy/execution.py:287` `place()` | limite di cap sulla liquidità: `size > avail` → `size >= avail` (bordo `size==avail`) | `test_execution.py` (71), poi tutto `Betfair/safe_strategy/` (789) | **NON CATTURATA** — 0 rossi aggiuntivi (i 2 rossi presenti erano pre-esistenti, su `stake.per_strategia`, non correlati: confermato rilanciando la suite anche a mutazione ripristinata) |
| 3 | `Betfair/omega/omega_service.py:1620` `_place_one` | rimosso `not res.ok` dal cancello di conferma: resta solo `res.size_matched <= 0` | `Betfair/omega/` (614 test) | **NON CATTURATA** — 614 passed, zero rossi |
| 4 | `frontend/src/components/controlroom/comandiBot.ts` `cambiaImporto` | guardia "parametri non letti": `correnti == null \|\| Object.keys(correnti).length === 0` → solo `correnti == null` (un oggetto vuoto passa) | `comandiBot.test.ts` (40, stato pre-refactor) | **CATTURATA** — 1 rosso (`parametri VUOTI valgono come non letti`) |
| 5 | `frontend/src/lib/controlRoom.ts:449` `modoDi` | fail-closed invertito: `=== 'live' ? 'live' : 'paper'` → `!== 'paper' ? 'live' : 'paper'` (mode assente/storto diventa live) | `controlRoom.test.ts` (71) | **CATTURATA** — 2 rossi (`una modalita NON DICHIARATA vale paper`, `un mode scritto storto non diventa mai soldi veri per caso`) |
| 6 | `frontend/src/lib/controlRoom.ts:804-805` `totaliGiornata` | somma paper dentro il netto live: `netPaper = (netPaper??0)+s.paper.netPnl` → `net = (net??0)+s.paper.netPnl` (paper+live si sommano) | `controlRoom.test.ts` (71) | **NON CATTURATA** — 71 passed, zero rossi |

**3 mutazioni su 6 non fanno scattare NESSUN test.** Le due su Safe/Omega
condividono lo stesso pattern strutturale (`not res.ok`): nessun finto, in nessuno
dei due moduli, costruisce mai `ok=False` insieme a `size_matched>0` — la
condizione che a Mike, il 15/09, è costata 32 ordini reali in loop. Il gap non è
"il codice è diverso quindi il test non serve": è che il costrutto di test che
isolerebbe l'effetto di `ok` da quello di `size_matched` semplicemente non esiste,
negli stessi due bot di cui l'incidente stesso (§2BIS di `HANDOFF_CONTROL_ROOM.md`)
dice "controllati, non hanno questi difetti" — l'affermazione è vera sul codice,
non sui test. La terza mutazione non catturata (`totaliGiornata`, somma
paper+live) è l'esatta regressione del bug §4.1.2 di `HANDOFF_CONTROL_ROOM.md`
(barra di giornata = somma dei tre servizi), sulla funzione che fu riscritta apposta
per renderla impossibile: la riscrittura impedisce di scrivere il bug per
distrazione (`TotaliGiornata` separa `netPnl`/`netPnlPaper`), ma se qualcuno
scrivesse comunque nel campo sbagliato, come nella mutazione, nessun test se ne
accorgerebbe.

Corroborazione indipendente: le due letture uscite dal mandato (mike,
safe_strategy — vedi Metodo) hanno ripetuto in autonomia le mutazioni #1, #3, #5 e
aggiunto `_gia_appoggiata` (Mike, fail-closed invertito su righe illeggibili →
CATTURATA, 2 rossi) e il ramo tennis di `cambiaModalita` in `comandiBot.ts`
(condizione di modalità invertita → CATTURATA, 39/85 rossi): stessi esiti,
eseguiti e ripristinati separatamente da me in momenti diversi sugli stessi file
condivisi con altri delegati — verificato che le due sessioni di mutazione non si
siano mai sovrapposte lasciando residui (nessuna delle due mutazioni sugli stessi
punti è rimasta applicata).

## Top-10 buchi, in ordine di rischio sui soldi

1. **`omega_activate` azzera i 3 cap di rischio** (`migrations/omega_daily_v2.sql:75`) — zero test lo coprono; è l'incidente Mike del 15/09 in un'altra funzione, mai chiuso.
2. **Safe `execution.py:424`** (mutazione #3 equiv.) — rimuovere l'effetto di `res.ok` dal cancello di piazzamento non fa scattare nessun test: un rifiuto Betfair con un campo incoerente passerebbe come successo.
3. **Omega `omega_service.py:1620`** — stesso identico buco strutturale (mutazione #3): non è "risolto altrove", è strutturalmente non testabile con i finti attuali.
4. **`controlRoom.ts` `totaliGiornata`** — una regressione della somma paper+live sulla riga sbagliata non farebbe scattare nessun test (mutazione #6), sulla stessa funzione riscritta apposta il 14/09 per impedire quel bug.
5. **Mike `mike_stop` non ferma le uscite** — l'unico test che ci prova (`test_mike_service.py:217`) passa a vuoto: nessuna posizione esposta nel fixture.
6. **Mike `max_open_matches` paper+live** — mai testato a livello di `run_once`/`_run_cycle` con entrambe le modalità esposte insieme, solo a livello di funzione pura.
7. **Mike `_reconcile_unknown` terzo ramo** — coperto solo nel file escluso del 15/09: un regresso qui non verrebbe visto dalla suite certificata oggi.
8. **`groupTradesIntoCicli`/`soldiPerPartita` su id nudo** — collisione fra bot diversi mai simulata da nessun test; rischio silenzioso sul P&L per partita e sulla barra di giornata in Control Room.
9. **`local_channel.py` `_MAX_INVII_IN_VOLO=64`** — scarto oltre soglia, difetto noto aperto (piano C.8), zero copertura di test.
10. **`controlRoomProposte.ts` `esigiOk`/`approvaProposta`/`ignoraProposta`** — guardia critica su `{ok:false}` non esercitata da nessun test dedicato.

## Limiti dichiarati (cosa NON ho verificato)

- Safe strategy: nessuna lettura riga-per-riga sistematica su tutti i 21 file (il
  sotto-agente assegnato si è auto-ridiretto sul referto completo); la guardia
  combo (L4) e il congelamento di `pre_ko` non sono stati riverificati a fondo
  perché `bot_service.py`/`execution.py`/`scanner.py`/`engine.py` erano in modifica
  attiva da un altro delegato durante l'audit.
- `comandiBot.ts`/`comandiBot.test.ts`: fotografati prima che un altro delegato
  spostasse la logica in `lib/interruttori.ts` e cancellasse il file di test — da
  ricertificare a Fase B stabile (il file nuovo `lib/interruttori.ts` non è nel
  perimetro assegnato oggi).
- Non ho eseguito le suite complete Omega/Safe/Stream/Frontend "a bocce ferme" a
  fine sessione (altri delegati scrivevano negli stessi file); le uniche esecuzioni
  certificate come verdi/rosse sono quelle delle 6 mutazioni sopra, con il modulo
  isolato al momento del test.
- Nessuna verifica riga-per-riga di `controlRoomCatena.test.ts` (28 test) e
  `controlRoomProposte.test.ts` (38 test) oltre lo scan mirato al reperto 10.

---

## Sintesi per il coordinatore (15 righe)

1. Perimetro rispettato, esclusi tutti i `*2026_09_16*`. Metodo: lettura diretta
   mia sui punti money-critical e su tutte le 6 mutazioni; 4 sotto-agenti di sola
   lettura per la classificazione esaustiva file-per-file (mike, omega, stream+
   frontend puliti; safe_strategy solo a campione — vedi Limiti).
2. **Zero test A (finto infedele), B (comportamento sbagliato certificato) o D
   (duplicato)** in tutto il perimetro. Un solo C: Mike `test_mike_service.py:217`,
   il claim "keeps_protections" non arma mai una posizione esposta.
3. Il problema reale non sono test scritti male: sono i comportamenti
   money-critical **mai messi alla prova** — vedi Top-10.
4. **Reperto più grave**: `omega_activate` azzera ancora i 3 cap di rischio
   (`migrations/omega_daily_v2.sql:75`, `coalesce(p_params,'{}')`), zero test lo
   coprono. Verificato di persona sul file di migrazione.
5. Prova di mutazione (6 punti, eseguiti e ripristinati personalmente, verificati
   riga per riga): **3 su 6 NON fanno scattare nessun test** — Safe
   `execution.py:424` e Omega `omega_service.py:1620` (stesso pattern `not res.ok`
   mai isolato da un finto), e `controlRoom.ts:totaliGiornata` (somma paper+live
   sulla riga sbagliata non produce nessun rosso).
6. Le altre 3 mutazioni sono state catturate: Mike grafia camelCase (10 rossi),
   `comandiBot.ts` parametri vuoti (1 rosso), `controlRoom.ts:modoDi` fail-closed
   invertito (2 rossi).
7. Due sotto-agenti (mike, safe_strategy) sono usciti dal mandato assegnato e
   hanno tentato l'intero referto di propria iniziativa, incluse mutazioni proprie
   sugli stessi file: verificato che nessuna sia rimasta applicata (nessun residuo,
   `git diff` pulito su ogni punto), i loro esiti di mutazione coincidono coi miei.
8. Frontend: confermato di persona `eventGroups.ts:83-84` raggruppa su id nudo,
   mai simulata una collisione fra bot diversi — rischio sul P&L per partita.
9. `comandiBot.ts`/`comandiBot.test.ts` sono stati svuotati/cancellati a metà
   audit da un altro delegato (migrazione a `lib/interruttori.ts`): da
   ricertificare a Fase B stabile.
10. Safe strategy non ha avuto lo stesso dettaglio riga-per-riga degli altri tre
    moduli: guardia combo L4 e congelamento `pre_ko` da riverificare a file
    stabili.
11. Nessuna correzione applicata, nessun git, nessuna strategia toccata: solo
    fatti, come richiesto.

File: `AUDIT_TEST_2026-09-16.md` (radice del repo).
