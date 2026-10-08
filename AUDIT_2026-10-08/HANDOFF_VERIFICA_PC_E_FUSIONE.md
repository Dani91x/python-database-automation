# VERIFICA SUL PC E FUSIONE SU MASTER — lavoro della sessione cloud dell'08/10/2026

Destinatario: l'agente sul PC dell'utente (quello con accesso al PC, alle registrazioni tennis, al DB e
all'app desktop) e l'agente che fonde su master. Autore: coordinatore della sessione cloud.
Comunicare in italiano. Regole: `CLAUDE.md`, `BRIEF_STANDARD_DELEGATI.md`, `PROCESSO_STANDARD_BOT.md` §6-§7.

> BOZZA IN CORSO: le sezioni marcate «[IN ATTESA]» si completano quando chiudono gli ultimi cantieri.
> La versione finale e' quella con la riga «STATO: COMPLETO» in testa.

Ordine dell'utente (08/10, testuale): «ALLA FINE DI TUTTI I LAVORI DOVRAI STILARE UN DOCUMENTO DETTAGLIATO PER
FAR CONTROLLARE IL TUTTO ALL'ALTRO AGENTE, TUTTE LE TASK LUNGHE CERTIFICALE E APPROVALE TU, L'ALTRO AGENTE
DOVRA OCCUPARSI DI ACCERTARSI CHE TUTTO CORRISPONDA ALLA REALTA E NON CI SIANO REGRESSIONI (NON VOGLIO REPLAY
DI SETTIMANE, STUDIATE UN MODO PER FARE IL PRIMA POSSIBILE SENZA RINUNCIARE ALLA QUALITA E ALLA
CERTIFICAZIONE.)» e «VOGLIO CHE MASTER SIA PERFETTO [...] SENZA REGRESSIONI DI NESSUN TIPO».

---------------------------------------------------------------------------------------------------

## 0. In una pagina

- Ramo da fondere: `claude/blissful-sagan-hri7o6`. Contiene TUTTO `claude/eloquent-franklin-g2nyk5` (lavoro del
  07/10 e del PC dell'08/10 fino a `b5845bc`, merge `d0cf8b94`) piu' i cantieri della sessione cloud, UN COMMIT
  PER CANTIERE, ciascuno con referto e blocco in `CRONOSTORIA.md`.
- `origin/master` e' a `8226d76` (06/10) ed e' ANTENATO del ramo: la fusione e' un avanzamento senza conflitti
  (fast-forward possibile; vedi §5 per come farla).
- Il coordinatore cloud ha gia' certificato ogni cantiere: diff riletto, test rilanciati, mutazioni PROPRIE (oltre a
  quelle del delegato), replay rifatti di persona dove la registrazione e' nel cloud. Il PC NON rifa' tutto:
  controlla che i numeri del cloud siano veri sulla macchina vera e fa SOLO cio' che nel cloud non si poteva
  (registrazioni tennis, DB, app a schermo, Windows). Stima: 2-3 ore di macchina, quasi tutte in parallelo.

## 1. Cantieri e commit

| commit | cantiere | cosa | certificato nel cloud | resta al PC |
|---|---|---|---|---|
| `5cc7103` | W2 | green-up dell'esposizione FUORI BOT letta dal conto: chiudere dall'app gli ordini fatti sul sito | 56 test, parita' su 51 scenari col worker di prima, mutazioni 19+5 | nessuna prova su Betfair vero (solo su ordine reale dell'utente, vedi §4.6) |
| `f0f14f6` | 5 | parcheggio del place-and-trim tennis dalla fonte unica (LAY 1,01-1,03), controllo B11 | 1112 test tennis, mutazioni 10+4 | replay tennis prima/dopo (§3.1) |
| `4b262c4` | 12 | test vitest rossi solo su Windows (fine riga, lancio di vite-node) | 34 test della barra, mutazioni 12+2 | i 6 test su Windows vero (§3.2) |
| `d1d4cd3` | 14 | nomi completi dei giocatori tennis in `_names.json`, fonte del nome, reimport che non declassa | 64 test Python, 16 vitest, mutazioni 26+3 | 35790089 a mano, migrazione, tooltip (§3.3) |
| `3b8ce19` | 15 | banco: la RIVALUTAZIONE ORARIA DEL CAMBIO del volume scambiato non e' uno scambio (era la causa del KO dello scalper) | prova indipendente sul raw, replay identici, mutazioni 3 | nessuna (calcio rifatto nel cloud) |
| `7633e20` | 6 | banco tennis: nomi dei giocatori nel certifica, scenari e controlli SP1-SP3 del pro, contratto di gate-aperto | 47 test + 970 collegati, mutazioni 15+3 | replay tennis (§3.1) |
| `00fbd9b` | W1 | PAGINA «CASH OUT» sotto la Control Room | tsc 0, 1404 test frontend collegati, fotografie, mutazioni 28+5 | prova a schermo (§3.4), build |
| `16d6c67` | 10 | registro del replay coi cicli del bot e diviso per fasi | 284 vitest replay, contratto Python-TS, mutazioni 16+3 | 35768297 a schermo (§3.5) |
| `6f04054` | 13 | strumento della barra: falso positivo dopo il VAR, incoerenze «per dati», fixture rigenerate | 160 vitest barra, 17 pytest tools, mutazioni 13+3 | le 38 partite del DB (§3.6) |
| `1ac69d0` | 9 | banco scalper: scavalco e rifiuti Betfair coi codici veri; UF2 riconosce il parcheggio 1,01-1,03 | 93 test, replay identici, mutazioni 24+1 | replay tennis `uscite-manuali*` (§3.1) |
| `d0cf8b94` | merge | piano di architettura del PC (`eloquent-franklin` fino a `b5845bc`) | solo documenti/strumenti, nessun file > 1 MB | — |
| [IN ATTESA] | 7 | banco di Omega RB-1..RB-5 | | |
| [IN ATTESA] | W3a | Mike/Omega/Safe sanno SUBITO degli ordini esterni (canale del conto), anche in prova | | |
| [IN ATTESA] | W3b | Scalper calcio e 4 bot tennis sanno degli ordini esterni | | |
| [IN ATTESA] | 11 | velocita' del banco | | |
| [IN ATTESA] | riferimenti | Mike/Omega/Safe/Scalper `--scenari tutti` col banco nuovo | | |

## 2. Il metodo rapido (perche' non servono replay di settimane)

1. **Impronte prima dei replay.** Per ogni bot il referto del banco stampa l'impronta del codice («codice bot»). Se
   l'impronta sul PC coincide con quella del referto cloud e il banco e' lo stesso commit, il replay sul PC deve
   dare righe identiche: basta UNO scenario per bot per provare che la macchina e' coerente, non `tutti`.
2. **Solo cio' che il cloud non poteva fare.** Le registrazioni calcio del banco (35760084, 35797769) sono state
   rigiocate nel cloud dal coordinatore e dalle sessioni parallele: sul PC NON si rifanno per intero.
3. **Parallelo.** `certifica` accetta `--worker N`: per la verifica rapida si lanciano processi separati per bot e
   per registrazione (uno per CPU), non in fila. [IN ATTESA cantiere 11: se il referto con `--worker N>1` e'
   identico a `--worker 1`, diventa la via ufficiale.]
4. **Mutazioni a campione.** Per ogni cantiere UNA mutazione scelta da chi verifica (non fra quelle del referto):
   deve diventare rossa. Se resta verde: reperto, il cantiere non e' certificato.
5. **Confronto, non lettura.** I referti si confrontano con `diff` esclusi tempi e hash, contro i file del cloud
   indicati per ogni cantiere; ogni riga diversa va spiegata.

## 3. Cosa fare sul PC, cantiere per cantiere

### 3.1 Replay tennis (cantieri 5, 6, 9) — UNA corsa sola che li copre tutti
Le registrazioni tennis 35790089 e 35794049 stanno in `C:\Users\Admin\Desktop\tennis_rec\20260707`.
- PRIMA: sul commit `3b8ce19^` NON serve: i referti del mattino del 07/10
  (`AUDIT_2026-10-07/riferimenti_coordinatore/finale/tennis_finale_<bot>.txt`) sono il PRIMA dei cantieri 5/6/9.
- DOPO, sulla cima del ramo, in parallelo (un processo per riga):
  `python -m Betfair.stream.backtest.certifica <bot> 35790089 --data-dir C:\Users\Admin\Desktop\tennis_rec\20260707 --scenari tutti --worker 1`
  per `tennis_scalper`, `tennis_pro`, `tennis_flb`, `tennis_swing`, `safe_tennis`; poi `tennis_pro` e
  `tennis_scalper` su 35794049.
- ATTESO (dai referti): 0 violazioni; controlli attivi 22 -> 23 (B11) per i 4 bot tennis; tennis_pro 17 -> 20 scenari
  (tre setup coi nomi; su 35790089 escono NE «nomi ASSENTI»); righe in testa «nomi» e «parametri cambiati dallo
  scenario»; parcheggi LAY con resto 0,50-0,62 da 1,01 a 1,02 e 0,63-0,79 da 1,01 a 1,03; tick, decisioni, azioni,
  esiti e netti IDENTICI. Dettagli: `cantiere_5/REFERTO.md` §6, `cantiere_6/REFERTO.md` §7, `cantiere_9/REFERTO.md` §7.
- Possibile SP3 su 35794049: il pro entra in break point anche nel tie-break (decisione dell'utente, §6 D-6).

### 3.2 Windows (cantiere 12)
`cantiere_12/REFERTO.md` §8: `git ls-files --eol` sui `.timeline.jsonl` (atteso `i/lf w/crlf`), i 4 file vitest
della barra (atteso 38/38), `npx vite-node scripts/verifica_barra_replay.ts --evento 35797769 --json` dal percorso con
lo spazio («PYTHON DATABASE»), mutazioni M1, M5, P1, S1 a campione.

### 3.3 Nomi tennis (cantiere 14)
`cantiere_14/REFERTO.md` §4. Migrazione `migrations/replay_tennis_fonte_nomi_2026-10-08.sql` DOPO
`replay_tennis_mercati_elenco_2026-10-08.sql` (§4). 35790089: nome intero scritto a mano in `_names.json`, poi
`python -m Betfair.stream.tennis_replay.importa --evento 35790089 --solo-nomi`: `n_snapshots` e `n_score` IDENTICI a
prima nel DB; tooltip «nome dall'IPS, troncato» sparito per quella partita.

### 3.4 Pagina Cash Out (W1) — a schermo, in PROVA
Dopo `npm run build` ad APP CHIUSA (regola del PC), l'utente riavvia l'app.
- Voce «Cash Out» subito sotto «Control Room»; pagina con riepilogo LIVE/PROVA mai sommati, filtri sport, Pre-match/
  Live, soldi; una scatola per partita con tutte le gambe.
- In PROVA con un bot acceso: la gamba compare nella sezione giusta; al calcio d'inizio la scatola passa da
  «Pre-match» a «In gioco» senza sparire; «Cash out» su una gamba di Omega/Safe chiude solo quella; su Mike dice
  «tutte le N gambe di Mike» e chiude il ciclo; il bot dopo il clic non rientra (marcatore «chiusa da te»).
- Ladder: si apre la finestra 560x860 del mercato della gamba. Statistiche: apre il Cruscotto e «Torna» riporta su
  Cash Out (non sulla Control Room).
- Control Room INVARIATA (stesse schede, stessi pulsanti; il ritorno al punto ora scorre davvero sulla partita).

### 3.5 Registro del replay (cantiere 10)
`cantiere_10/REFERTO.md` §9: 35768297 media under, il registro mostra N = numero dei cicli del bot e il totale
«uguale al banco»; sezioni per fase.

### 3.6 Strumento della barra (cantiere 13)
`cantiere_13/REFERTO.md` §3-§4: `npx vite-node scripts/verifica_barra_replay.ts --env-file ../.env --senza-note` sulle 38
partite (atteso: 28 OK, 10 «solo per dati», 0 da correggere) e la tabella delle 13.

### 3.7 [IN ATTESA] cantieri 7, W3a, W3b, 11

## 4. Migrazioni (le applica l'utente, nell'ordine)
Verificare in sola lettura quali sono gia' applicate, poi applicare le mancanti in quest'ordine:
1. `segui_live_apri_partita_2026-10-06.sql`, `ack_allarmi_replay_cambio_2026-10-06.sql`, `replay_applica_bot_2026-10-06.sql` (06/10)
2. `replay_tennis_2026-10-07.sql`, `media_under_attiva_adesso_2026-10-07.sql` (07/10)
3. `replay_tennis_mercati_elenco_2026-10-08.sql` POI `replay_tennis_fonte_nomi_2026-10-08.sql` (08/10; la seconda
   contiene anche `market_types`: riapplicare la prima dopo toglie `nomi_fonte`)
4. [IN ATTESA: eventuali migrazioni di W3a/W3b]

## 5. Fusione su master — procedura esatta
[IN ATTESA: si completa a lavori chiusi]

## 6. Decisioni aperte per l'utente
- D-1 (cantiere 15) `chiusura-abbinata-in-parte` KO solo B2 0,04 (due resti per ciclo sotto la tolleranza per ciclo):
  B2 per ciclo come K5 (patch pronta, non applicata) o il bot dichiara la polvere della selezione.
- D-2 (cantiere 9) MONEY-CRITICAL: dopo un `replaceOrders` rifiutato il place-and-trim (`trading/submin.py`, comune a
  scalper, sniper, bot tennis e worker) passa a DONE e il bot crede chiusa per ~25 s una posizione aperta.
- D-3 (cantiere 6) il pro entra in break point anche nel tie-break (0-3/1-3 per chi riceve).
- D-4 (cantiere 6) `gate-aperto` apre soglie che la UI non espone (dichiarate).
- D-5 (cantiere 10) netto per fase calcolato sulla fase (somma diversa di un centesimo dal totale, detto a schermo) o solo lordo.
- D-6 (W1) partita col mercato CLOSED e posizioni non regolate: oggi in «In gioco» con «conclusa».
- D-7 (W2) un ordine dell'app non abbinato sul lato della copertura blocca la chiusura degli ordini del sito (oggi:
  rifiuto con motivo; alternativa: annullarlo in automatico).
- D-8 rami non fusi: `audit-ml` (doc), `schema-architettura` (doc), `feature/scalper-media-under` (ladder con partita
  sintetica, «solo se l'utente lo vuole»).
- [IN ATTESA: decisioni di W3a, W3b (D1, D3, D4, D5, D6 del referto), 7, 11]
