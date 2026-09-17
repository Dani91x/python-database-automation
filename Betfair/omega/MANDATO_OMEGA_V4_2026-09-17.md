# MANDATO OMEGA V4 — per il coordinatore della sessione Omega (17/09/2026, h15)

> Scritto dal coordinatore della sessione principale (`admin-6d`) su ordine dell'utente. È il
> punto d'ingresso UNICO per chi lavora su Omega da ora in poi. Si legge PRIMA di tutto, poi
> `CRONOSTORIA.md` (ultima sezione), poi i documenti in §6.

## 1. L'ordine dell'utente (17/09 h15, testuale in sostanza; vincola tutto)

- «Omega è un asset e dobbiamo usarlo. Voglio un prodotto rivoluzionario che mi permetta di
  fare piccoli profitti costantemente.»
- **Due ingressi a partita: uno nel primo tempo e uno nel secondo.**
- **Lo stake è FISSO: 1 euro in LAY, a qualunque quota.**
- **Range di quota**: «se reputi che siano PEGGIORATIVI, toglili». **Range di tempo per
  entrare**: «se reputi che siano PEGGIORATIVI, TOGLILI» — dopo analisi dei dati (fatta: §3).
- **Obiettivo**: prendere TUTTO IL PALINSESTO DI GIORNATA e ricavare un target per partita; se
  con 1 € in lay si supera il target tanto meglio, se non ci si arriva va bene uguale: ci sono
  altri bot per l'obiettivo di giornata; ogni bot che porta un risultato positivo riduce
  l'obiettivo finale.
- **REGOLE NON NEGOZIABILI**: (a) **massività**: Omega deve aprire più posizioni possibili,
  sempre tenendo conto che dobbiamo raggiungere l'obiettivo: **una loss di Omega lo compromette
  totalmente**; (b) **OMEGA DEVE AVERE LA SCHEDA DOVE L'UTENTE APPROVA LE USCITE, SIA IN PROFIT
  CHE IN LOSS**, come succede con Safe tennis (proposta con i numeri, firma dell'utente,
  chiusura dalla scheda in UI); nessuna chiusura automatica.
- Decisioni già date stamattina che restano: le uscite sono proposte; il bot ignora le
  operazioni manuali dell'utente ma riconosce il suo cash-out globale e la chiusura fuori app.

## 2. Come si lavora (il metodo, obbligatorio: è quello della sessione principale)

1. **Tu sei coordinatore e revisore, non costruttore.** Ogni task va a un delegato: **Opus 5**
   per costruzione complessa, architettura, bug money-critical, replay; **Sonnet 5** per
   revisioni, fix circoscritti, audit in sola lettura, misure, documentazione.
2. **Non ti fidi del referto**: rileggi il diff, rilanci test e replay di persona, rifai la
   falsificazione con mutazioni TUE (diverse da quelle del delegato), verifichi l'attinenza
   (fatto tutto e solo quello chiesto). Un lavoro è «certificato» solo quando l'hai verificato
   tu. Oggi ho rimandato indietro tre delegati su falsificazioni deboli: succede spesso.
3. **Brief ai delegati**: obiettivo, cosa è già escluso, file da leggere (puntatori), perimetro
   stretto, condizioni dell'utente (§1), criteri di accettazione = `PROCESSO_STANDARD_BOT.md`
   §6 (copertura del banco) e §7 (catalogo dei 37 errori), falsificazione obbligatoria dei test
   nuovi (rosso prima, verde dopo, output mostrato), finti con chiavi e tipi IDENTICI al vero,
   «niente commit, mai `git add -A`», «riporta ciò che non hai potuto verificare».
4. **Standard dei bot** (`CLAUDE.md`, `PROCESSO_STANDARD_BOT.md`): progetto → mappa di ogni
   condizione e della consapevolezza degli ordini → replay flumine sulle registrazioni reali
   con il codice di produzione (`python -m Betfair.stream.backtest.certifica omega <event>
   --scenari tutti --worker 3`) → paper come specchio → live solo se il paper conferma. Mai
   replay «a parte», mai classi di laboratorio, mai fill a mano. Le strategie cambiano SOLO su
   ordine dell'utente (qui: §1 lo dà, dentro quei limiti; ogni altra divergenza si scrive e si
   porta all'utente).
5. **Cronostoria**: a ogni task certificata aggiungi un checkpoint in `CRONOSTORIA.md`
   (sezione del giorno, sottosezione «Omega — sessione dedicata»); a fine sessione «punto di
   ripresa». Un lavoro non scritto lì non è finito.
6. **Vincoli operativi**: l'app desktop è VIVA con soldi veri (Mike e Safe tennis live) sul
   checkout principale → **lavora in un worktree** (`isolation: worktree` per i delegati) e
   porta su master solo lavoro verificato; **nessun processo, registratore, runner o job nuovo
   senza permesso dell'utente**; DB solo in lettura (le migrazioni si scrivono in `migrations/`
   e le applica l'utente); mai `git add -A`; commit e push solo quando l'utente lo chiede; mai
   toccare `.env`; niente chiamate Betfair duplicate (feed unico).
7. **Coordinamento con la sessione principale** (`admin-6d`, che tiene Safe, Mike, UI, banco):
   dominio Omega = `Betfair/omega/**`, `frontend/src/components/omega/**`, `frontend/src/lib/
   omega*.ts`, `components/controlroom/SchedaChiusuraOmega.tsx`, migrazioni `omega_*`. File
   CONDIVISI da toccare solo avvisando `admin-6d` via SendMessage prima: `Betfair/safe_strategy/
   execution.py` (settlement, aggiorna_trade), `Betfair/omega/omega_market.py` (usato anche da
   Safe/Mike per le letture di conto), `Betfair/stream/backtest/*` (banco), `Betfair/stream/
   local_channel.py`, `live_order_worker.py`, `runner.py`, `frontend/src/lib/interruttori.ts`,
   `frontend/src/components/controlroom/*` (tranne la scheda Omega). In corso oggi da
   `admin-6d`: percorso tennis «al ms» + F1 relay + F2 paper Safe (worktree), audit dei 4 bot
   tennis (worktree), UI stati di attesa Safe.

## 3. Lo stato dei fatti (tutto misurato oggi; i referti sono nel repo)

- **Motore in produzione**: v2 (`strategy_version`=2), `paper/stopped`; apre a margine 1,00×
  (EV zero). v3 nel codice, spenta, non collegata al servizio. Cap tutti a zero nel DB.
- **Misure** (`K_MISURATO`, `INGRESSO_PASSIVO_MISURA`, `M1BIS_POLITICA_V4`,
  `M1TER_QUOTA_VIVA_BEST_BACK`, `M4M5M6`, `M2_DATI_E_PESI`, tutte 2026-09-17, in `Betfair/omega/`,
  strumenti in `tools/`, dati in `data/`, test falsificati): al TOCCO bancare le scoreline di
  coda perde in ogni fascia (k 0,5-0,98); il bias favourite-longshot esiste alla probabilità
  equa (in gioco 2,5× nelle fasce 0,5-2 % del Correct Score, estremo prudente 1,11) ma lo spread
  se lo mangia; il prezzo di riserva dal bias cade esattamente sul miglior back, dove la quota
  viva si riempie lo 0,09 %; salendo di tick si rompe il margine e i fill sono prese al tocco;
  selezione avversa 1,6-2,5 contro soglia di arresto 1,27 (Monte Carlo); fascia 2-5 % e tutto
  l'Half Time a EV negativo; nessun dato storico del DB aggiunge informazione al mercato
  (M2: pesi zero; λ = quote devigate; la catena attuale usa prima la fixture, fonte peggiore).
  Limiti: 11 giorni di registrazioni, 12-25 uscite per fascia, 2 uscite fra i fill, quote
  pre-match sul 3 % delle partite (job manuale fermo dall'11/09).
- **Conseguenze per il mandato §1**: (i) le **finestre 20'-40' / 50'-80' sono PEGGIORATIVE**:
  aspettano che le quote salgano; il Correct Score è quotabile dal 1' (10,7 celle vs 2,4
  all'86') e per la stessa cella la liability a inizio è metà → **si tolgono** (gamba HT dal 1',
  gamba FT dal 1' con impegno dal minuto che l'utente sceglie: decisione 19); (ii) il **tetto
  di quota 20-120 è PEGGIORATIVO** (non separa le fasce che rendono da quelle che perdono) →
  **si toglie**, al suo posto la fascia di probabilità equa e il cap di liability; (iii) con
  **stake fisso 1 €** la liability è `quota − 1`: a quota 100 sono 99 € su un premio di 0,95 €;
  «una loss compromette l'obiettivo» → la selezione delle celle DEVE tenere conto della
  liability e la scheda delle uscite deve proporre la protezione con i numeri (EV di tenere vs
  bloccabile) PRIMA che la cella diventi raggiungibile.

## 4. Il programma (30 punti, nell'ordine; ogni fase chiusa sul banco con criterio di arresto
scritto PRIMA)

**Fase 0 — Fondamenta dati**: (1) job giornaliero quote Betfair pre-partita (chiedere il
permesso all'utente: è un processo); (2) raccolta quote in gioco per fascia/minuto dalle
registrazioni del runner; (3) catch-up transizioni + pg_cron (migrazione, permesso); (4)
dimensione cartellini nelle transizioni.
**Fase 1 — Motore**: (5) λ dalle quote devigate per prime, fixture/tattico come ripiego con
incertezza più larga (inversione della catena `_prematch_lambdas`, `omega_service.py:~613`);
(6) incertezza che cresce senza mercato; (7) hazard di gol per lega/minuto/punteggio/rosso
sulle transizioni; (8) fusione col mercato per fascia e tempo dall'ultimo evento; (9)
calibrazione della coda, operatività sul limite superiore; (10) il modello fa SOLO:
ammissibilità, fascia, veto, proposte di uscita.
**Fase 2 — Quota viva**: (11) prezzo di riserva dal bias di fascia sulla p_equa, ricalcolato a
ogni tick, k di fascia letto dai dati; (12) due strade in una regola (prendi se il mercato lo
offre, altrimenti appoggia); (13) macchina a stati della gamba quotata copiata da Mike
(`Betfair/mike/CHECKPOINT_2026-09-16.md` §1-2: annullo in un giro, nuovo ordine al giro dopo a
residuo confermato, mai due lay vive, rilettura per bet_id alla riapertura); (14) difese dalla
selezione avversa (annullo a evento, cool-down misurato, isteresi, CUSUM che spegne la fascia);
(15) celle impossibili/realizzate escluse, aggregati Any Unquoted ammessi; (16) verifica dal
vivo dei «passive bet delays» Betfair (ordini appoggiati senza ritardo?).
**Fase 3 — Rischio con stake fisso 1 €**: (17) cap di LIABILITY per gamba/partita/giorno (la
leva è quale cella, non quanto stake); (18) Kelly frazionario come tetto sulla cassa che dà
l'utente; (19) paniere di celle mutuamente esclusive sotto cap di caso peggiore (decisione
utente 16); (20) obiettivo di giornata = target per partita come METRICA e barra, non come
dimensione degli ordini (decisione 15: l'utente lo ha appena confermato in §1); (21)
place-and-trim non serve con stake 1 € (minimo .it 0,50 €) — dichiararlo.
**Fase 4 — Uscite e consapevolezza**: (22) **LA SCHEDA DELLE USCITE** (regola non negoziabile):
produttore Python su `omega_requests` (migrazione applicata oggi, `get_omega_proposte`,
`omega_request_approve/ignore` esistono; UI `SchedaChiusuraOmega.tsx` pronta) con proposta in
PROFIT (bloccabile > 0) e in LOSS (protezione quando la cella si avvicina: gol, quota
dimezzata, EV di tenere < bloccabile), numeri: EV tengo, bloccabile, p_lose, liability; firma
dell'utente; esecuzione via `execution.close_trade`; modello Safe tennis
(`bot_service._uscita_del_bot_approvata`, `safe_strategy_proposed_2026-09-14.sql`); (23)
consapevolezza completa: buco `reconcile_pending`, `CHECK` stati `cancelled`/`lapsed`
(migrazione), famiglia K + K8/K9/K10, controlli A13-A15; (24) finestre: HT dal 1', FT dal 1'.
**Fase 5 — Prova**: (25) replay massivo su tutte le registrazioni Omega (39 con raw + sintetiche
dichiarate) via `certifica`, con fill, k realizzato per fascia con IC, selezione avversa, P&L,
drawdown, celle della matrice ordini provocate; (26) criterio di arresto scritto prima di ogni
fase (oggi 1,27); (27) paper via flumine (F1 relay C3, in costruzione da `admin-6d`: chiedere
lo stato prima di costruire in parallelo); (28) live piccolo: una partita, una gamba, referto
forense, cinque operazioni.
**Fase 6 — UI**: (29) parametri v4 nel pannello, quota viva visibile (chiesto/abbinato/residuo/
prezzo di riserva/fascia/motivo di scarto per cella); (30) rischio a due numeri e storico
separato paper/live (fatto oggi: `migrations/storico_sport_2026-09-17.sql` applicata).

## 5. Decisioni dell'utente: chiuse e aperte

Chiuse (17/09): 2 ingressi per partita; stake fisso 1 € lay; range di quota e di tempo si
tolgono se peggiorativi (lo sono: §3); massività; scheda delle uscite con firma in profit e in
loss; nessuna chiusura automatica; bot ignora le manuali, riconosce cash-out globale e chiusura
fuori app; obiettivo di giornata come target per partita (metrica). Aperte (porta i numeri,
non riaprire quelle chiuse): 16 paniere sì/no e quante celle; 17 cassa di riferimento e cap di
liability per gamba/partita/giorno; 19 minuto d'impegno della gamba FT; 20 aggregati Any
Unquoted; 21-23 job quote, catch-up transizioni, inversione catena (sono processi/motore:
chiedere il via esplicito prima di lanciare o toccare).

## 6. Documenti da leggere, nell'ordine

`CLAUDE.md` · `CRONOSTORIA.md` (17/09) · `PROCESSO_STANDARD_BOT.md` · `Betfair/omega/
VISIONE_OMEGA_V4_COORDINATORE_2026-09-17.md` (tesi + addendum §9) · `PROGETTO_OMEGA_V4_2026-09-17.md`
(progetto a fasi con controlli e scenari) · `M4M5M6_2026-09-17.md` (criterio di arresto, prezzo di
riserva riscritto) · `M1TER_QUOTA_VIVA_BEST_BACK_2026-09-17.md` · `M2_DATI_E_PESI_2026-09-17.md` ·
`INGRESSO_PASSIVO_MISURA_2026-09-17.md` · `K_MISURATO_2026-09-16.md` · `REFERTO_V3_2026-09-16.md` ·
`COSTITUZIONE_OMEGA.md` (§0, §1 invarianti, §11, §12 con il riquadro del 16/09, §16-17) ·
`CHECKPOINT_O1_2026-09-16.md`, `CHECKPOINT_V3_2026-09-16.md` · `Betfair/mike/CHECKPOINT_2026-09-16.md`
§1-2 (ordine appoggiato) · `PROGETTO_PAPER_VIA_FLUMINE_2026-09-16.md` §C3.
Strumenti pronti: `tools/misura_ingresso_passivo.py` (modi m1/v4/v4ter), `misura_prezzo_appaiata.py`,
`superficie_liability.py`, `k_in_gioco.py`, `deriva_margine.py`, `montecarlo_pl.py`, `m2_pesi.py`,
`misura_k.py`; test in `Betfair/omega/tests/` e `Betfair/omega/test_*.py`. Suite Omega oggi: 960 verdi.

## 7. Come si comincia (prima ora)

1. Leggi §6, verifica di persona lo stato (git, suite Omega, registro `certifica --elenco`).
2. Apri in `CRONOSTORIA.md` la sottosezione «Omega — sessione dedicata (coordinatore: <nome>)».
3. Chiedi all'utente le decisioni aperte di §5 che servono alla Fase 0-1 (permessi per job e
   catch-up, via all'inversione della catena) e la cassa di riferimento.
4. Primo delegato Opus 5: Fase 0/1 (5-6-7-9-10) con test falsificati e banco dei modelli
   fuori campione; primo delegato Sonnet 5: reperti di consapevolezza (23) e migrazione degli
   stati. In parallelo, il produttore delle proposte (22) è la prima cosa che l'utente vedrà.
5. Ogni fase: replay `certifica omega` prima e dopo, numeri nel checkpoint, criterio di
   arresto scritto prima.
