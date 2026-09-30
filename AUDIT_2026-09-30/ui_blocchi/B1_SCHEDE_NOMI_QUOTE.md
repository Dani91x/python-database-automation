# B1_SCHEDE_NOMI_QUOTE — referto (30/09/2026)

Worktree: `C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.claude\worktrees\agent-a32982190acf0f4b4`
Base: `4fcb867` (HEAD detached; il worktree era nato su `15f0a33`, portato a `4fcb867` ad albero pulito).
Patch: `AUDIT_2026-09-30/ui_blocchi/B1_SCHEDE_NOMI_QUOTE.patch` (10 file, solo `frontend/`, `git apply --check -R` = 0).
Niente commit, niente build, nessun processo, nessuna lettura DB, nessuna chiamata Betfair.

## 1. Che cosa misura davvero `odds_ts_ms` (Python, sola lettura)

- `Betfair/safe_strategy/service.py:1180-1183`: `if ev.get("odds") != odds: ev["odds_ts_ms"] = ora_ms`.
  E' l'istante, sull'orologio dello SCANNER, dell'ultimo CAMBIO del blocco `odds` del Match Odds.
  Il blocco contiene per ogni lato `back`, `lay`, `back_size`, `lay_size`, `ltp`, `selection_id`
  (`service.py:1121-1125`, `scanner.price_pair`): cambia anche se si muove solo l'importo al meglio
  o l'ultimo abbinato.
- Non avanza su un book senza prezzi (`service.py:1165-1179`, incidente del 17/09).
- Pubblicato nel payload: `service.py:1903` (calcio), `:1958` (tennis).
- L'istante dell'ultima LETTURA esiste (`ev["odds_seen_ms"]`, `service.py:1197`) ma NON e' nel payload
  (le chiavi pubblicate sono elencate a `:1875-1913` e `:1940-1969`).
- Quindi: aveva ragione il commento di `latenzaQuoteS` («da quanto quel prezzo non si muove»); era
  sbagliato quello di `PartitaFeedLike.odds_ts_ms` («istante in cui lo scanner ha LETTO le quote»),
  ora corretto in `lib/controlRoom.ts`. Il commento omonimo in `lib/safeStrategyScan.ts:66-82`
  («Istante in cui lo scanner ha letto le quote») e' ancora sbagliato: file fuori dal mio perimetro,
  da correggere da chi ne ha il dominio.
- Etichetta a schermo: **«ultimo cambio: …»**, con `title` che dice «ultimo CAMBIO … non l'ultima
  lettura». Le quattro parole e i colori di `QUOTE_CLS`/`QUOTE_TESTO` sono identici a prima
  (spostati in `QuoteMercato.tsx`, riesportati da `SchedaPartita.tsx`).
- Eta' che cresce al secondo: `useControlRoom.ts:1832` (`setInterval(..., TICK_MS)`, `TICK_MS = 1_000`
  a `:204`) aggiorna `nowMs`; `giornata` e' un `useMemo` che dipende da `nowMs` (`:2189-2206`) e
  ricalcola `latenzaQuoteS` e l'eta' delle linee. Nessun timer aggiunto. Provato con un test puro
  (`costruisciGiornata` a `T0` e `T0+1 s`: 5 s -> 6 s, per quote e linee), non a schermo.

## 2. Che cosa c'e' nel blocco `ou`

Lista di blocchi `scanner.build_market_block` (`scanner.py:629-679`), ordinata per linea
(`scanner.split_opportunity_blocks`, `:825-841`), pubblicata a `service.py:1913`:
`market_id`, `status` (OPEN/SUSPENDED/CLOSED…), `inplay`, `total_matched`, `market_type`
(`OVER_UNDER_35`…), `line` (float), `bet_delay`, `ts_ms` (ultimo CAMBIO, `service.py:1309`),
`seen_ms` (ultimo book RICEVUTO, `:1285,1319`), marker `decided`/`for_mike`, e
`selections[] = {selection_id, name ("Under 3.5 Goals"/"Over 3.5 Goals"), runner_status, back, lay,
back_size, lay_size}`. I prezzi CI SONO gia' nella riga in memoria: mostrati.

Quante linee: pre-KO solo 3,5 e 4,5 (`PRE_KO_OU_MARKET_TYPES`, `scanner.py:66`); in gioco tutte le linee
ancora indecise fra 0,5 e 7,5 (`OU_MARKET_TYPES`, `scanner.py:44-47`: fino a 8). Regola applicata
(come da brief): **1-4 linee si mostrano, oltre 4 la scheda non ne mostra nessuna** (scegliere quali
sarebbe una decisione inventata). Vedi «Proposte».

`seen_ms` non distingue «mercato fermo» da «non piu' osservato» (lo stream manda book solo ai cambi):
l'eta' delle linee e' **grigia, senza giudizio** («ultimo book: 3 s fa» / «ultimo book: età ignota»);
il giudizio resta al badge del flusso (`FlussoLineeMikeBadge`, invariato).

## 3. PRIMA -> DOPO a schermo (testo che legge il trader)

Le celle sono riquadri con etichetta grigia, BACK in azzurro (`sky-300`), LAY in rosa (`rose-300`),
cifre mono 12,5 px semibold (prima: testo grigio 10 px).

### Scheda pre-partita (calcio)
| caso | PRIMA | DOPO |
|---|---|---|
| nomi con loghi | 2 righe, logo 16 px, 12,5 px normale | 2 righe, logo 16 px, 13 px medium (= scheda in gioco) |
| nomi senza loghi | 2 righe con uno spazio vuoto di 16 px a sinistra | 2 righe, nessuno spazio (lo spazio resta solo se l'altra squadra ha il logo) |
| quote presenti, eta' 2 s | `1 40,00/50,00 · X 15,00/18,00 · 2 1,08/1,10 … 2 s` | `[1 40,00/50,00] [X 15,00/18,00] [2 1,08/1,10] ultimo cambio: 2 s` |
| un prezzo assente (X assente, LAY del 2 assente) | `1 1,90/1,92 · 2 4,20/—` (la X spariva) | `[1 1,90/1,92] [X —/—] [2 4,20/—]` |
| prezzo fermo | `fermo 40 s` (grigio) | `ultimo cambio: fermo 40 s` (grigio) |
| prezzo vecchio | `vecchio 2 min` (arancione) | `ultimo cambio: vecchio 2 min` (arancione) |
| quote presenti, eta' ignota | nessuna eta' (non si mostrava) | `ultimo cambio: età ignota` (arancione) |
| mercato sospeso | non mostrato in pre-partita (invariato) | invariato |
| linee Under/Over (1-4) | non mostrate | `U/O 3,5 [Under 1,50/1,52] [Over 2,60/2,70] ultimo book: 36 s fa` per linea; `SOSPESO` / `decisa dai gol` se del caso |
| tennis | `P1 1,50/1,52 · P2 2,60/2,65` | `[P1 1,50/1,52] [P2 2,60/2,65] ultimo cambio: …` (P1/P2 restano: vedi §6) |

### Scheda in gioco / aperte (calcio)
| caso | PRIMA | DOPO |
|---|---|---|
| nomi | `Seychelles v Sri Lanka` su una riga, 13 px medium, senza loghi | due righe `Seychelles` / `Sri Lanka`, stesso componente e markup della pre-partita, loghi dove ci sono |
| quote presenti | riga pulsanti: `… 3 s`; sotto: `1 40,00/50,00 · X … · 2 …` grigio 10 px | sotto i pulsanti: `[1 …] [X …] [2 …] ultimo cambio: 3 s  vol. …  punteggio 12 s` (l'eta' delle quote e' ACCANTO alle quote) |
| un prezzo assente | `X —/—` | `[X —/—]` |
| mercato sospeso | `SOSPESO` + quote | `SOSPESO` + celle (invariato il badge) |
| prezzo fermo / vecchio / eta' ignota | `fermo 40 s` / `vecchio 2 min` / `età ignota` senza etichetta | `ultimo cambio: fermo 40 s` / `ultimo cambio: vecchio 2 min` / `ultimo cambio: età ignota` (stessi colori) |
| senza quote | `3 s` nella riga pulsanti | `ultimo cambio: 3 s` nella riga pulsanti |
| linee Under/Over (1-4) | non mostrate | come in pre-partita, dentro il blocco in gioco |
| liability | `resp. 9,80 €` · `prova 4,00 €` (title «responsabilità …») | `liability 9,80 €` · `prova 4,00 €` (title «liability impegnata con SOLDI VERI» / «liability impegnata in PROVA: non sono soldi veri e non si sommano») |

### Scheda in gioco / aperte (tennis)
| caso | PRIMA | DOPO |
|---|---|---|
| nomi | `Federer R. – Nadal R.` su una riga | due righe `Federer R.` / `Nadal R.` |
| barra tennis, quote | `Federer R. 1,50/1,52 · Nadal R. 2,94/—` grigio 10 px | `[Federer R. 1,50/1,52] [Nadal R. 2,94/—]` |
| barra tennis, eta' | `3 s · canale` | `punteggio 3 s · canale` (senza punteggio: `riga 3 s · db`); il title dice che NON e' l'eta' delle quote |
| eta' quote (riga pulsanti) | `3 s` / `età ignota` | `ultimo cambio: 3 s` / `ultimo cambio: età ignota` |

## 4. File

Toccati: `frontend/src/components/controlroom/SchedaPreMatch.tsx`, `frontend/src/components/controlroom/SchedaPartita.tsx`,
`frontend/src/lib/controlRoom.ts` (commento `odds_ts_ms` corretto; nuovi `LatiOu`, `LineaOuScheda`,
`lineeOuScheda`; campo OPZIONALE `PartitaGiornata.lineeOu`, mappato in `costruisciGiornata`),
`frontend/src/lib/controlRoom.test.ts`, `frontend/src/components/controlroom/SchedaPartita.test.tsx`,
`frontend/src/components/controlroom/SchedaPreMatch.test.tsx`.
Nuovi: `frontend/src/components/controlroom/NomiPartita.tsx`, `NomiPartita.test.tsx`, `QuoteMercato.tsx`
(`QuoteMercato`, `EtaQuote`, `LineeOu`, `celleMatchOdds`, `MAX_LINEE_OU`, `QUOTE_CLS`, `QUOTE_TESTO`,
`TITOLO_ETA_QUOTE`), `QuoteMercato.test.tsx`.
Fuori da `frontend/` (non nella patch): questo referto, `B1_SCHEDE_NOMI_QUOTE.STATO.md`, `falsifica_b1.ps1`.

`data-testid`: tutti i preesistenti conservati (`cr-partita`, `cr-pre-match`, `cr-pre-orario`, `cr-pre-manca`,
`cr-pre-quote`, `cr-calcio-vivo`, `cr-calcio-vivo-quote`, `cr-calcio-vivo-mercato`, `cr-calcio-vivo-volume`,
`cr-calcio-vivo-eta-punteggio`, `cr-latenza` (uno solo per scheda: accanto alle quote se ci sono, altrimenti
nella riga pulsanti), `cr-tennis-vivo*`, `data-event-id`). Nuovi: `cr-nomi-partita`, `cr-nome-squadra`,
`cr-logo-vuoto`, `cr-quota-cella`, `cr-quota-back`, `cr-quota-lay`, `cr-pre-quote-mo`, `cr-pre-latenza`
(+`-valore`), `cr-latenza-valore`, `cr-pre-quote-ou`, `cr-calcio-vivo-ou`, `cr-quote-ou-linea`,
`cr-quote-ou-mercato`, `cr-quote-ou-decisa`, `cr-quote-ou-prezzi`, `cr-quote-ou-eta`, `cr-liability-partita`.

Nota su `pages/ControlRoom.test.tsx` (non toccato): cerca il nome INTERO nella scheda in gioco
(`getByText('Milan – Inter')`) e i due nomi SEPARATI nella pre-partita (`getByText('Girona')`). Entrambi
restano veri: le due righe visibili portano i nomi separati, e un testo `sr-only` (le righe visibili sono
`aria-hidden`) porta il nome intero una volta sola. E' anche l'accessibilita' corretta, non un ripiego.

## 5. Test

Nuovi (tutti scritti PRIMA del codice; i 17 delle schede visti ROSSI prima dell'integrazione):
- `controlRoom.test.ts` +5 (`lineeOuScheda`: mappa, seen_ms assente = null, decisa/sospeso, malformati, eta' che cresce con `nowMs`).
- `QuoteMercato.test.tsx` 11; `NomiPartita.test.tsx` 7.
- `SchedaPreMatch.test.tsx` +6; `SchedaPartita.test.tsx` +12 (markup dei nomi e delle celle IDENTICO fra le due schede, eta' accanto alle quote, liability).
Test esistenti cambiati: **nessuno** (solo import aggiunti: `within`, `SchedaPreMatch`, `lineeOuScheda`).

Falsificazioni (`AUDIT_2026-09-30/ui_blocchi/falsifica_b1.ps1`; copia prima della mutazione in
`%TEMP%\claude\...\scratchpad\b1_copie`, fuori dal repo; ripristino dalla copia; hash identico; `git diff`
identico a prima, verificato con hash del diff):
| id | mutazione | test | esito |
|---|---|---|---|
| M1 | scheda in gioco torna a `<span>{p.nome}</span>` | SchedaPartita | ROSSO (3) |
| M2 | quota 0 mostrata come `0,00` | QuoteMercato | ROSSO (1) |
| M3 | BACK grigio invece di sky | SchedaPreMatch | ROSSO (1) |
| M4 | eta' senza «ultimo cambio:» | SchedaPartita | ROSSO (3) |
| M5 | `LineeOu` mostra piu' di 4 linee | QuoteMercato | ROSSO (1) |
| M6 | cella X tolta quando manca | SchedaPreMatch | ROSSO (3) |
| M7 | spazio-logo anche senza loghi | NomiPartita | ROSSO (1) |
| M8 | `seen_ms` assente = 0 s | controlRoom | ROSSO (1) |
| M9 | `decided` ignorato | controlRoom | ROSSO (1) |
| M10 | `costruisciGiornata` senza linee | controlRoom | ROSSO (1) |
| M11 | torna «resp.» | SchedaPartita | ROSSO (1) |
| M12 | eta' lontana dalle quote | SchedaPartita | ROSSO (1) |
| M13 | eta' barra tennis senza etichetta | SchedaPartita | ROSSO (1) |
| M14 | eta' nascosta quando ignota (pre) | SchedaPreMatch | ROSSO (1) |
| M15 | linee O/U tolte in gioco | SchedaPartita | ROSSO (1) |
| M16 | barra tennis senza il componente quote | SchedaPartita | ROSSO (1) |
Nota onesta: M5 la prima volta l'ho provata contro `SchedaPreMatch.test` ed e' sopravvissuta, perche'
la scheda ha la sua guardia `<= MAX_LINEE_OU` oltre a quella di `LineeOu` (doppia guardia: mutarne una
sola non cambia lo schermo). Contro il test del componente e' rossa. Incidente: la prima esecuzione
dello script si e' interrotta su M1 (stderr di `npx` con `ErrorAction Stop`) PRIMA del ripristino;
`SchedaPartita.tsx` ripristinato subito dalla copia, `git diff` verificato identico (hash), script
corretto con `try/finally`, poi rieseguito da capo.

Comandi e numeri (da `frontend/` del worktree):
- `npx tsc -p tsconfig.app.json --noEmit` -> 0 errori.
- `npx vitest run src/components/controlroom/SchedaPartita.test.tsx src/components/controlroom/SchedaPreMatch.test.tsx src/components/controlroom/QuoteMercato.test.tsx src/components/controlroom/NomiPartita.test.tsx src/lib/controlRoom.test.ts` -> 5 file, 147/147.
- una volta alla fine: `npx vitest run src/components/controlroom src/pages/ControlRoom.test.tsx src/components/trading/StatoOrdine.montaggio.test.tsx src/lib/flussoLineeMike.test.tsx src/lib/controlRoom.test.ts` -> **58 file, 976/976 verdi**, 197 s.

## 6. COSA NON HO FATTO
- Linee Under/Over quando sono piu' di 4 (tipico in gioco a inizio partita, fino a 8): non mostrate.
  Dato gia' presente (nessuna lettura in piu' servirebbe); manca una DECISIONE su quali mostrare.
- Tennis in gioco SENZA posizione: nessuna quota (come prima). Il dato c'e' gia' (`PartitaGiornata.odds.p1/p2`
  dallo scanner, lo stesso della pre-partita), ma la barra tennis con posizione ha le quote da UN'ALTRA fonte
  (`tennis_live_now` del runner): mostrarle entrambe darebbe due prezzi da due fonti sulla stessa scheda. Non fatto.
- Eta' delle QUOTE nella barra tennis: non mostrata. Servirebbe `row.state.updated_ms` (istante di scrittura
  dello stato mercati del runner, `Betfair/stream/tennis_live/tennis_runner.py:1501`) trasformato in eta'
  dentro `useTennisVivo.ts` (fuori perimetro). Ho solo etichettato quella esistente come «punteggio»/«riga».
- Tennis: le celle della pre-partita dicono P1/P2 (dallo scanner, `sortPriority` 1/2), quelle della barra
  in gioco il NOME (dal runner, nome e prezzo nella stessa selezione). Non ho scritto nomi su P1/P2: nessun
  codice lega `sortPriority` all'ordine dei nomi nell'`event_name` (stesso limite dichiarato in `TennisVivoBar`).
- Commento sbagliato su `odds_ts_ms` in `lib/safeStrategyScan.ts:66-67`: file fuori perimetro, non toccato.
- Nessun lampeggio, freccia, spread o profondita' (come da brief).

## 7. COSA NON HO POTUTO VERIFICARE
- **L'app a schermo non l'ho vista**: niente build, niente app. Tutto e' verificato in jsdom (classi,
  testi, markup). Da guardare dal vivo: ingombro delle celle su schede strette (le celle vanno a capo con
  `flex-wrap`), leggibilita' di sky-300/rose-300 sullo sfondo, allineamento dei nomi fra partite con e senza
  loghi nella stessa lista (ora chi non ha loghi non ha lo spazio vuoto a sinistra).
- Che l'eta' salga a schermo ogni secondo: provato sul codice (`useControlRoom.ts` + test puro), non sull'app.
- Quante linee O/U porta davvero oggi una riga in gioco: non ho letto il DB (non serviva al lavoro).
- La correttezza dei nomi selezione «Under X Goals»/«Over X Goals» su tutti i mercati: dal codice (`names`
  del catalogo Betfair); una selezione con nome diverso resta `—/—`, mai un prezzo attribuito a caso.

## 8. Proposte per l'utente
1. Linee O/U oltre 4: mostrare le 2 linee attorno ai gol attuali (es. gol+0,5 e gol+1,5) o una tendina
   «tutte le linee». Serve la sua scelta.
2. Tennis in gioco senza posizione: mostrare P1/P2 dello scanner (fonte unica, come la pre-partita).
3. Eta' delle quote nella barra tennis da `state.updated_ms` (piccola aggiunta in `useTennisVivo.ts`).
4. (Rinviate dal brief) lampeggio al cambio prezzo, freccia di direzione, spread in tick.

## 9. Da controllare dal vivo al prossimo avvio
- Pre-partita di una partita di Mike (linee 3,5/4,5): due righe `U/O 3,5` e `U/O 4,5` con celle e «ultimo book».
- Scheda in gioco calcio: celle 1·X·2 e accanto «ultimo cambio: N s» che sale ogni secondo; «punteggio N s» a destra.
- Stessa partita in «pre» e poi in «live»: nomi identici (due righe, stessi loghi).
- Riga dei bot: «liability 9,80 €», non piu' «resp.».

## Verifica del coordinatore UI (admin-07), 30/09 18:05
- Albero di verifica: `1d058a7` + C_P11 + G_P2 (+ test) + B1 + B2 impilati SENZA conflitti; le stesse patch, in questo ordine (G_P2 → G_P2_test → B1 → B2), si applicano pulite con `git apply` sul master `7bbff9b` (provato in un worktree di integrazione).
- Sull albero INTEGRATO: `npx tsc -p tsconfig.app.json --noEmit` = 0 errori; `npx vitest run src/components/controlroom src/components/trading src/pages src/components/mike` + i test di lib toccati = 111 file, 1685 test verdi, 1 saltato (737 s a PC carico).
- Diff riletto riga per riga (2 componenti nuovi, 2 schede, `lib/controlRoom.ts` solo additivo + commento di `odds_ts_ms` corretto). Test mirati 147/147.
- Mutazioni MIE, tutte ROSSE, ripristino da copia con `cmp`: Under e Over scambiati nella lettura delle selezioni (2 rossi); BACK e LAY scambiati nelle celle delle linee (2); quota 1,00 mostrata come prezzo valido (1); eta sempre col colore del fresco (3); nome completo tolto dal title (3).
- Rilievi miei, affidati allo stesso delegato come aggiunta **B1bis** (non blocca B1): con piu di 4 linee Under/Over la scheda non ne mostra nessuna (in gioco possono essere 8); tennis in gioco senza posizione senza quote; spazio del logo non piu riservato quando nessuna squadra ha il logo (lista disallineata rispetto a prima).
- Dato che manca dal backend: `odds_seen_ms` (istante dell ultima LETTURA del Match Odds) non e nel payload: a schermo si puo dire solo «ultimo cambio: N s».
