# SCALPER CALCIO — «MEDIA UNDER», secondo giro (05/10/2026)

Delegato (sessione cloud). Ramo `feature/scalper-media-under-giro2` da `master` `369e6c4`.
Specifica: `Betfair/stream/scalper/SPEC_MEDIA_UNDER_GIRO2_2026-10-05.md` (resta valida in
tutto `SPEC_MEDIA_UNDER_2026-10-05.md`). Nessun ordine vero, nessuna chiamata a Betfair,
nessun accesso al DB vero, nessun `.env`, app non avviata, nessun processo lasciato acceso.
Replay solo da `python -m Betfair.stream.backtest.certifica`, uno alla volta (`--worker 1`),
sulle due registrazioni VERE di `registrazioni_banco/` (scompattate in `_live_raw/`, mai
toccate). La partita sintetica del primo giro NON e' in questo ramo.

## 0. IN EVIDENZA — cio' che NON ho potuto verificare

1. **Due sole partite, e sulla 35760084 la modalita' non entra mai.** Sull'Under 2,5 e
   sull'Under 3,5 di quella partita il primo filtro che ferma l'ingresso e' la
   liquidita' (meno di 300 EUR sul miglior prezzo): tutti i suoi 14 scenari della
   modalita' escono **NE** (non esercitati) col motivo. Anche `media-under-35` sulla
   35797769 esce NE (stesso motivo). Tutta la condotta osservata sul banco viene da UNA
   partita (35797769, Under 2,5).
2. **Su quella partita la modalita' fa al piu' 1 rientro coi valori di serie.** Il
   massimo dei rientri (5) e il rischio massimo non si vedono mai sul banco:
   `media-under-rischio-30` e' identico a `media-under` (si arriva a 20 EUR puntati, mai
   a 30). Il blocco per rischio massimo e' provato solo dai test su flumine vero. Il
   massimo si vede in `media-under-rientri-1` (massimo = 1).
3. **Ordini messi a mano (2.3): mai provati su Supabase vero.** Nel banco la tabella
   `betfair_live_orders` finta risponde sempre vuota: il replay prova SOLO che le
   letture si fanno quando devono (M10: in prova zero, in soldi veri al piu' una per
   battito, solo a riquadro pubblicato) e che una lettura non rompe la sessione. Il
   calcolo del riquadro con righe a mano e' provato solo dai test, con righe nella forma
   VERA della tabella (`reconcile_worker._account_order_row`). Quali `source` contare
   come «a mano» e' una mia scelta (§4, Q2).
4. **L'ora del dato** («letti alle hh:mm:ss») e' l'ora locale del PC della sessione
   (`datetime.fromtimestamp`): non vista su Windows dell'utente.
5. **Interfaccia: nessun cambio, mai vista a schermo.** Il riquadro mostra gia' il testo
   della fonte (`ScalperPanel.tsx`: «Chiusura — {fonte}»). Suite frontend non rilanciata
   (nessun file del frontend toccato).
6. **Ambiente diverso dal PC dell'utente**: Python 3.11 (l'utente 3.13).
7. **La modalita' NON e' certificata**: mancano prova (paper) e soldi veri, e i tre punti
   in attesa dell'utente (P1, P8, P13) restano come sono (§4).

## 1. Esito per punto della specifica

### 2.1 — I due buchi nei test

Nuovi test in `Betfair/stream/tests/test_scalper_media_under_giro2_2026_10_05.py`:

- `test_quota_su_di_meno_di_n_tick_la_banca_resta_ferma`: punta 10 @1,50, banca 10,14 @1,48;
  la quota sale di UN tick (1,51) per 40 book: a ogni book stato `IN_POSIZIONE`, sempre
  la stessa banca viva, nessun annullo, nessun ordine nuovo.
- `test_punta_abbinata_in_due_tempi_la_banca_si_riallinea`: rientro a 1,52 (punta 10,00)
  con 4 sul book: si abbina 4, la banca va sulla posizione di quel momento; poi gli
  scambi abbinano il resto: la banca vecchia si annulla (motivo «banca da riallineare»),
  si aspetta che sia morta, la nuova e' 20,13 @1,50 (la posizione vera, 20 puntati). Mai
  due banche vive (invarianti del banco a ogni book).

**Il doppio controllo del rientro resta.** `_forse_rientro` decide (quota su di almeno N
tick dall'ultimo ingresso) e ritira la banca; `_punta_di_rientro` ricontrolla sul book
CORRENTE quando la banca e' morta. Fra le due possono passare piu' book (latenza
dell'annullo) e la quota puo' essere tornata giu': la specifica dice «si rivaluta dal
book corrente». Togliere il secondo controllo cambierebbe il comportamento (rientro alla
quota vecchia); toglierlo dal primo produce l'annullo a ogni book (la mutazione G1).

### 2.2 — Il referto dei replay della modalita'

- **Azioni**: la riga dello scenario conta gli ORDINI piazzati dalla modalita' (contatore
  `stats.ordini` della strategia, letto dal ponte del replay a ogni book; gli annulli non
  contano). Prima: `azioni= 0`; ora `media-under` sulla 35797769: `azioni= 5`.
- **Riepilogo per ciclo, in euro, dagli ORDINI veri** (`riepilogo_cicli_media`): ingresso
  (importo, quota, abbinato, minuto), ogni rientro (quota, importo esatto, piazzato,
  abbinato), totale puntato massimo, banca finale (importo, quota, persistenza, abbinato,
  dove si e' abbinata: pre-match o minuto di gioco, e com'e' finita: viva, abbinata,
  non piu' a mercato), profitto lordo e netto, poi la riga `NETTO` come gli altri bot.
  Esempio (`media-under`, 35797769):
  `ciclo 1: ingresso 10.00 @2.18 (... 83'49" al fischio); rientro 1 @2.22: esatto 10.19,
  piazzato 10.00, abbinato 10.00; totale puntato massimo 20.00; banca finale 20.18 @2.18
  PERSIST, abbinata 20.18 (ultimo abbinamento: in gioco al 9'53") ...; profitto lordo
  +0.18, netto +0.17 [CHIUSO]` e `P&L del replay: lordo +0.18 | commissione 0.01 (5.0%) |
  NETTO +0.17 EUR`.
- **NE**: uno scenario della modalita' senza nessun ordine esce `NE` (non esercitato) col
  filtro che l'ha fermata piu' spesso (`Referto.non_esercitato`, letto da
  `certifica.segno_referto`). `media-under-35` sulla 35797769: prima `OK`, ora `NE` con
  «liquidita' sotto il minimo al miglior prezzo (min size) (x22051)».
- **Motivi di non ingresso**: la strategia conta, book per book, il PRIMO filtro che
  ferma l'ingresso (stats `non_ingresso`, chiave `media_non_ingresso` nella riga del
  control): freno, fischio non leggibile, finestra prima del fischio, attesa dopo un
  rifiuto, prezzi mancanti, quota fuori intervallo, liquidita', spread, riscaldamento,
  flusso, punta non partita. Stessi controlli nello stesso ordine di prima: cambia solo
  che il motivo ha un nome (`_perche_non_entra`).

### 2.3 — Ordini messi a mano nel riquadro «chiusura»

`scalper_session.leggi_ordini_conto_media`, chiamata UNA volta nel ciclo del battito:

- solo in **soldi veri** (in prova ritorna subito: nessuna query);
- solo con **posizione aperta e riquadro pubblicato** (massimo dei rientri o in gioco:
  prima nessuno lo vede — limite piu' stretto di quello della specifica, deciso dopo il
  replay: 65 letture inutili in pre-match nel `kill-switch`);
- legge `betfair_live_orders` (`mode=live`, mercato e selezione della modalita');
- le righe con `source` 'account' (dal sito) o 'runner' (terminale dell'app) e qualcosa
  di abbinato entrano **SOLO nel riquadro** (`MediaUnderStrategy._fonte_e_posizione`):
  mai negli ordini, nei cicli o nelle stats della modalita';
- il riquadro scrive «ordini del bot + ordini del conto letti alle hh:mm:ss (N a mano su
  questa selezione)»; se la lettura fallisce torna a «solo ordini del bot (lettura degli
  ordini del conto fallita alle hh:mm:ss: motivo)»;
- qualunque errore resta dentro la funzione: il battito non si rompe mai.
- Nuovo controllo **M10** (registro della modalita'): in prova nessuna lettura, in soldi
  veri al piu' una per battito. Il banco conta le select per tabella del DB finto.

## 2. Difetti trovati dai replay (prima -> dopo)

| # | Dove | Prima | Dopo | Test che lo riproduce (falsificato) |
|---|---|---|---|---|
| D1 | lettura degli ordini del conto | `time.strftime`: la sessione vede del modulo `time` solo `time` e `sleep` (contratto col banco, `_TempoSessione`). Sulla 35797769 `media-under` **KO**: sessione morta in errore alla prima lettura con la banca appoggiata, S3 rosso (`replay/giro2/prima_della_correzione/media_35797769.txt`); stesso KO su tutte le varianti e i guasti | `datetime.fromtimestamp(time.time())` e tutta la funzione dentro un `try`: `media-under` OK, NETTO +0,17 | `test_la_lettura_usa_solo_il_tempo_che_il_banco_conosce`, `test_la_lettura_non_rompe_mai_il_battito` (G26, G27) |
| D2 | testo del ciclo chiuso | `media-under-tick-1`, ciclo 2: chiuso a **-0,25** e l'attivita' diceva «ciclo chiuso in profitto» (`prima_della_correzione/varianti_35797769_secondo_giro.txt`) | «ciclo chiuso in PERDITA: lordo -0.25 ...» (la regola della banca NON e' toccata: §4 Q1) | `test_ciclo_chiuso_in_perdita_lo_dice` (G28) |
| D3 | referto, riavvio | banca della sessione morta abbinata dopo il riavvio: «ultimo abbinamento: ?» | i tempi si seguono anche per gli ordini delle sessioni morte (`_Banco.medie`) | lettura del referto `guasti_35797769.txt` |

## 3. I replay (referti in `AUDIT_2026-10-05/replay/giro2/`)

Comando unico: `bash AUDIT_2026-10-05/strumenti/replay_giro2.sh` (UN replay alla volta,
`--worker 1`); riepilogo in `riepilogo.log`. Tempi per scenario fra 9 e 160 s (sotto i 5
minuti; i tempi esatti sono nelle righe `tempo:` di ogni referto).

### 3.1 Non regressione (modalita' spenta)

`python AUDIT_2026-10-05/strumenti/confronta_non_regressione.py`: i 15 scenari dello
Scalper sulla 35797769 e `base,paper` sulla 35760084 hanno le righe OK/KO **identiche**
ai referti del revisore (`replay/scalper_15_con_media_spenta/`), gruppi A1, A2, B1, B2,
B3, C.

### 3.2 La modalita'

| Partita | Scenario | Esito | Azioni | Cicli | NETTO | M mai sollecitati |
|---|---|---|---|---|---|---|
| 35797769 | `media-under` | OK | 5 | 1 chiuso (in gioco al 9'53") | +0,17 | nessuno |
| 35797769 | `media-under-paper` | OK | 5 | uguale (paper = live) | +0,17 | nessuno |
| 35797769 | `media-under-35` | **NE** (liquidita') | 0 | - | 0 | M1-M9 |
| 35797769 | `media-under-obiettivo-030` | OK | 5 | 1 (rientro 17,00 esatto 17,21) | +0,29 | nessuno |
| 35797769 | `media-under-rientri-1` | OK | 5 | 1, MASSIMO raggiunto | +0,17 | nessuno |
| 35797769 | `media-under-rischio-30` | OK | 5 | 1 (20 EUR, mai al tetto) | +0,17 | nessuno |
| 35797769 | `media-under-tick-1` | OK | 19 | 2: +0,09 e **-0,25** | -0,16 | nessuno |
| 35797769 | `media-under-riavvio` | OK | 2 | 1 (banca della sessione morta abbinata) | +0,17 | M2, M3, M4 |
| 35797769 | `media-under-rifiuti-betfair` | OK | 11 | 1 (6 rifiuti, attese 1-32 s) | +0,17 | nessuno |
| 35797769 | `media-under-esiti-ignoti` | OK | 10 | 2 | +0,34 | nessuno |
| 35797769 | `media-under-kill-switch` | OK | 2 | 0, posizione aperta | ignoto | M2, M3, M4, M7 |
| 35797769 | `media-under-bot-fermo` | OK | 2 | 0, posizione aperta | ignoto | M2, M3, M4, M7 |
| 35760084 | tutti i 12 | **NE** (liquidita') | 0 | - | 0 | (M10 soltanto) |

(Il dettaglio di ogni ciclo, coi minuti e la banca finale, e' nelle note di ogni referto.)

### 3.3 I guasti con la modalita' accesa (35797769)

- **riavvio**: processo ucciso con la posizione aperta (10 @2,18 e banca 10,19 @2,14
  PERSIST). Gli ordini del processo morto restano a mercato; la sessione nuova parte
  `BLOCCATA` («riavvio a posizione aperta: posizione non ricostruibile... nessun
  ordine», punto P13 dell'utente, non toccato) e non piazza niente. La banca rimasta si
  abbina da sola: ciclo +0,17.
- **rifiuti-betfair**: 6 piazzamenti rifiutati; la modalita' frena (1, 2, 4, 8, 16 s ...),
  conta «attesa dopo un rifiuto» fra i motivi, poi entra; nessun ripiazzo a ogni book.
- **esiti-ignoti**: 6 piazzamenti senza esito per 20 s; mai un secondo ordine sopra uno
  in volo; 2 cicli chiusi.
- **kill-switch / bot-fermo**: stop a meta' della finestra pre-match con la posizione
  aperta. Dopo il blocco **nessun ordine** (M9). Resta 10 @2,18 SENZA banca: la banca
  PERSIST e' tolta dall'arresto (punto **P1** dell'utente, non toccato). S3 verde: il
  servizio dichiara la posizione non piatta. Vedi la riga «banca finale ... a fine
  replay» del referto.

## 4. Punti dove la specifica non decide (non fatti: per l'utente)

- **Q1 — Rientro abbinato IN PARTE e chiusura in perdita.** La spec: banca a «quota
  dell'ultimo ingresso - N tick», importo che pareggia la posizione VERA. Se un rientro
  si abbina solo in parte la quota media resta piu' bassa di quella su cui era fatto il
  conto e la banca puo' chiudere in perdita. Visto sulla partita vera
  (`media-under-tick-1`, ciclo 2): 10 @2,18 + 10 @2,20 + 20 @2,22 + 2,99 @2,24 (rientro da
  40,00 abbinato per 2,99) -> banca 42,75 @2,22 -> ciclo chiuso a **-0,25 EUR**. Con i
  valori di serie (2 tick) succede meno (la chiusura a 2 tick sotto l'ultimo ingresso
  copre di piu'), ma puo' succedere. Alternative (da decidere): chiudere a «media - N
  tick», o rifare il rientro per il resto. Non cambiato.
- **Q2 — Quali ordini sono «a mano».** Contati: `source` 'account' (visto solo sul conto,
  dal sito) e 'runner' (terminale manuale dell'app). NON contati: lo specchio della
  sessione stessa ('scalper'), gli altri bot ('mike', 'omega', 'safe', 'bot:<ref>' ...).
  Esempio: posizione del bot 20 @1,51; a mano dal sito 30 @1,80 abbinati -> il riquadro
  calcola su 50 puntati; un ordine di Mike sulla stessa selezione resta fuori.
- **Q3 — Azioni = ordini piazzati** (anche quelli rifiutati), annulli esclusi.
- **Q4 — NETTO**: commissione per mercato sul netto vincente (come `banco_comune.pnl` e
  Betfair). La somma dei netti dei cicli puo' differire di un centesimo dalla riga NETTO.
- **P1, P8, P13**: in attesa dell'utente, non toccati.

## 5. Falsificazione

`python AUDIT_2026-10-05/strumenti/mutazioni_media_under_giro2.py` (stessa macchina del
primo giro: una sostituzione per volta, test dei due giri, ripristino con `git checkout`).
Esito in `AUDIT_2026-10-05/strumenti/mutazioni_media_under_giro2_esito.json`.

TABELLA_MUTAZIONI

## 6. Test

- `Betfair/stream/tests/test_scalper_media_under_giro2_2026_10_05.py`: NUMERO_TEST casi
  (flumine VERO col client paper della sessione, book nativi Betfair, esecuzione
  differita di 1 e 4 book, minimi .it del banco; righe di `betfair_live_orders` nella
  forma vera).
- Primo giro: `test_scalper_media_under_2026_10_05.py` (unico cambio: l'elenco dei
  controlli M ha M10).
- Suite `Betfair/stream/`: ESITO_SUITE.

## 7. File toccati

| File | Cosa |
|---|---|
| `Betfair/stream/scalper/media_under_bot.py` | motivi di non ingresso (`_perche_non_entra`, `MOTIVI_NON_INGRESSO`, stats `non_ingresso`); ordini del conto (`righe_a_mano`, `posizione_con_righe`, `posizione_aperta`, `serve_ordini_conto`, `imposta_ordini_conto`, `_fonte_e_posizione`); testo del ciclo chiuso in perdita |
| `Betfair/stream/scalper/scalper_session.py` | `leggi_ordini_conto_media` e la sua chiamata nel battito |
| `Betfair/stream/scalper/certificazione.py` | `Referto.non_esercitato`; `OsservazioneMedia` (prova, letture, battiti); controllo M10 |
| `Betfair/stream/scalper/tools/replay_registrazioni.py` | azioni = ordini della modalita'; `riepilogo_cicli_media`; `_referto_media` (riepilogo, NETTO, motivi, letture, NE); varianti e guasti dichiarati (`SCENARI_MEDIA_VARIANTI`, `guasto_dello_scenario`); letture del DB finto; tempi degli ordini; `_posizione_aperta` per la modalita' |
| `Betfair/stream/tests/banco_media_under.py` | `book(ponte=...)`: il ponte vero del replay |
| `Betfair/stream/tests/test_scalper_media_under_giro2_2026_10_05.py` | NUOVO |
| `Betfair/stream/tests/test_scalper_media_under_2026_10_05.py` | M10 nell'elenco |
| `Betfair/stream/scalper/BIBBIA_SCALPER_CALCIO.md` | §14 aggiornato |
| `AUDIT_2026-10-05/strumenti/` | `mutazioni_media_under_giro2.py` (+ esito), `replay_giro2.sh`, `confronta_non_regressione.py` |
| `AUDIT_2026-10-05/replay/giro2/` | i referti (e `prima_della_correzione/`) |

Nessun file vietato toccato (`minimi_it.py`, `minimi_banco.py`, `live_order_build.py`,
`submin.py`, `motore_ordini.py`, `Betfair/mike/**`, `Betfair/safe_strategy/**`,
`Betfair/omega/**`, bot del tennis). Nessuna migrazione. Nessuna regola di strategia
aggiunta: soglie, stake, tetti e gambe invariati.
