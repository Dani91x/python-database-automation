# PROTOCOLLO PROVA DAL VIVO IN PAPER — CANTIERE H — 28/09/2026

Da eseguire in UNA sessione, appena l'utente accende l'app e i bot. Scritto da chi certifica solo con dati gia'
esistenti (nessuna app avviata durante la stesura). Ordine dei passi: NON scambiare l'ordine, ogni passo presuppone
lo stato lasciato dal precedente. Chi esegue: chi ha il permesso di avviare l'app e cliccare in Control Room
(coordinatore o utente); questo file e' il copione.

**Regola trasversale**: prima di ogni passo, fotografare lo stato (query indicate) COSI' com'e' PRIMA; dopo il
passo, rifotografare e confrontare. Ogni «atteso» qui sotto e' un numero o una riga precisa, non un'impressione.

---

## 0. Preflight (5 minuti, prima di toccare i bot)

1. `git log -1` sul checkout principale = deve essere il master con TUTTI i fix del 26/09 (`cf22d37` o successivo).
   Se l'utente ha fatto altri commit dopo il 26/09, verificare che non abbiano toccato i file dei fix elencati nel
   registro NC (§2 di `CANTIERE_H_REGISTRO_NC.md`).
2. Verificare che le 6 migrazioni del 26/09 risultino applicate (`storico_esito_a_zero`, `omega_state_per_modalita`,
   `live_positions_senza_mercati_regolati`, `analytics_rpc_veloci`, `betfair_live_orders_source_bot`,
   `analytics_signals_kickoff_pulizia`): SELECT su `pg_proc` per le firme nuove (`get_safe_state(p_mode text)`,
   `omega_aggregates_sql(boolean,text)`) — gia' confermate presenti da me il 28/09.
3. Cancellare/spostare (NON eliminare, solo rinominare) i vecchi `_logs/*.log` del 26/09 se si vuole un confronto
   pulito per riavvio di oggi (il main.js cancella comunque i `.log` con mtime > 7 giorni all'avvio: non urgente).
4. Avere pronta una finestra SQL in sola lettura per le query di questo file (tutte SELECT).
5. Avvisare che si sta per accendere l'app e i bot SOLO PAPER (nessun bot si accende da solo: verificarlo appena
   l'app e' su, `omega_control`/`mike_control`/`safe_strategy_control`/`tennis_bot_service_control`/
   `scalper_service_control` tutti `stopped`).

## 1. Accensione e Z0 (10 minuti)

1. Avviare l'app (icona o exe). Attendere le porte 47311-47338 in ascolto (~60 s).
2. Verificare `_logs/` con i 9 file nuovi (K2, gia' certificato funzionante il 26/09: qui si controlla solo che il
   meccanismo regga anche oggi).
3. Verificare `live_alerts` per il codice `ORDER_MODE` piu' recente: il messaggio deve dire l'EFFETTIVO (PAPER),
   non «*** LIVE *** SOLDI VERI» (F-9/R-F2-C2, gia' risolto: qui si riconferma che non e' regredito).
4. Accendere i bot in PAPER dalla Control Room (Omega, Mike, Safe le 4 varianti — calcio PRIMA di tennis, per
   evitare la trappola R-F2-1/R-E2E-1 del «solo tennis» che spegne il calcio — poi i 4 bot tennis, poi lo
   scalper). Annotare gli orari esatti (UTC) di ogni clic: servono per interpretare i log dopo.
5. Query di controllo Z0-dopo-accensione: tutti i `*_control.status='running'`, `mode='paper'`,
   `betfair_live_settings.order_mode='paper'`, `kill_switch=false`.

## 2. Verifica A SCHERMO sull'app desktop dei campi corretti il 26/09 (30-40 minuti)

Il 26/09 questi campi sono stati letti SOLO con un banco jsdom (Chrome non era collegato): ora che l'app e' viva
si guardano SULLO SCHERMO dell'app desktop e si confrontano col valore che la query dice. Priorita' alta = dietro
un KO gia' corretto in codice (§2.4 del registro); fare questi PRIMA.

| pagina | campo a schermo | valore atteso (query) | dove leggerlo |
|---|---|---|---|
| Safe Strategy | tile «P&L totale · PAPER» | = `SELECT sum(pnl_netto) FROM safe_strategy_trades WHERE mode='paper' AND status IN ('won','lost','void')` (NON deve piu' includere le righe `mode='live'`) | tab principale Safe |
| Safe Strategy | Storico (filtro Modalita') | selezionare PAPER: il totale deve combaciare con la stessa somma sopra; selezionare LIVE: deve mostrare SOLO le righe live | tab Storico |
| Control Room | P&L «oggi» per Omega e Mike | deve mostrare un numero (non «—») appena c'e' almeno una posizione REGOLATA oggi; confrontare con `SELECT sum(pnl_netto) FROM omega_trades WHERE status IN ('won','lost') AND settled_at::date = current_date` | riga bot |
| Control Room | riga «in prova ±X su N operazioni» / tessere Calcio-Tennis | deve comparire (non piu' «giornata non ancora letta») quando `get_safe_daily` per oggi torna righe; se torna 0 righe deve dire «nessuna operazione oggi», non «non ancora letta» | Posizioni/tessere |
| Control Room | tick di movimento sulle posizioni aperte (Omega/Mike) | segno concorde col segno di «chiudi ora»: un LAY che guadagna quando la quota sale deve mostrare tick VERDE quando «chiudi ora» e' positivo | riga posizione aperta |
| Control Room | riga con punteggio d'ingresso Mike | mai piu' «None-None»: se il punteggio non c'e' deve mostrare «—» o essere assente | riga operazione Mike |
| Control Room | proposte Safe (colonna Opportunita') | nessuna proposta con `created_at` piu' vecchia di ~12h deve comparire con «Piazza» attivo | colonna opportunita' |
| Control Room | «P del mercato» su una scheda SENZA prezzo vivo | P mercato e Vantaggio devono essere coerenti (P modello − P mercato = Vantaggio, stessa unita') | scheda proposta |
| Control Room | Volume Match Odds sulle partite in gioco | NON deve piu' essere fisso a «0,00 €» quando il ladder della stessa partita (Segui Live) mostra un Matched > 0 | riga scan / confronto con Segui Live |
| Market Watch | badge stato di una partita di tennis FINITA | deve dire «FINITA»/chiuso, MAI «LIVE», e il punteggio deve avere TUTTI i set (compreso il 3°, non troncato) | scheda Market Watch |
| Tennis Terminal | apertura pagina su una partita NON seguita | NON deve piu' partire un `tennis_follow_event` da sola: deve comparire «partita non seguita: premi Segui»; controllare `tennis_live_follow` che NON nasca una riga nuova al solo apertura pagina | header pagina |
| Control Room | scheda uscita Safe («Chiudere adesso» vs «Tenere») | entrambi i numeri devono essere NETTI (stessa base, commissione 5% su entrambi) | scheda cashout |
| Mike | title «probabilita' di N gol» sulla scheda P(4) | deve dire «esattamente 4», non «4+» | scheda Mike |
| Mike | pagina `/mike`, posizione con uscita proposta | deve comparire il pulsante APPROVA uscita direttamente su `/mike` (prima solo in Control Room) | pagina Mike |
| Live P&L | «posizioni aperte» col filtro Mode qualunque | NON deve piu' comparire la riga fantasma (mercato 1.259819675, evento 35797769): GIA' VERIFICATO da me a DB (0 righe residue con la query della funzione), qui si conferma A SCHERMO | pagina Live P&L |
| Live P&L | sezione tennis con filtro Mode=LIVE | non deve mostrare posizioni PAPER | pagina Live P&L |
| Dashboard | ML, riquadro «Previsione»/«classe prevista» | i due verdetti non devono piu' essere opposti sullo stesso target (o, se lo sono per costruzione statistica, va dichiarato a schermo) | scheda Modelli ML |
| Dashboard | Direzione, colonna quota | deve dichiarare se e' quota Betfair o quota bookmaker (non un unico numero ambiguo) | scheda Direzione |
| Omega | card «storico N partite» | N deve essere partite DISTINTE, non il numero di aperture | Missione/Performance |
| Mike | Storico, conteggio V/P | i trade con P&L a ZERO (scratch) non devono piu' essere contati come «V» | Storico Mike |
| Analytics | tab Performance Motori | deve caricare (niente «canceling statement due to timeout»); `get_analytics_filters` deve rispondere in pochi ms (gia' misurato dal coordinatore: 10 ms) | Analytics |
| Dashboard/Analytics | Studio Ritardi su una lega grande (es. 667) | deve caricare lo storico «Tutto» senza errore di timeout | Studio Ritardi |

## 3. Freno su TUTTI i bot con tentativo VERO garantito

Il 26/09 il freno e' stato tirato in 3 finestre, ma Safe, Mike e i 3 bot tennis (oltre a swing una volta) NON hanno
MAI avuto un tentativo di apertura nella finestra (nessun dato: «non certificato», non un pass). Qui l'obiettivo e'
diverso: **prima di tirare il freno, verificare che OGNI bot abbia una condizione quasi pronta a entrare**, poi
tirare il freno nel momento in cui l'ingresso scatterebbe, cosi' il rifiuto e' un rifiuto VERO, non un'assenza di
occasione.

### 3.1 Come scegliere il momento (da ripetere finche' non si trova la finestra buona)

Interrogare, poco prima di tirare il freno (query ripetibili ogni 1-2 minuti mentre si aspetta):

- **Omega**: `SELECT * FROM omega_activity ORDER BY id DESC LIMIT 20` — cercare `skip` con motivo VICINO a un
  ingresso (es. `p_margine_insufficiente` di poco, non `no_market`/`sospeso`): quello e' il segnale che a breve
  potrebbe entrare. In alternativa, con molte partite di sabato/weekend in corso la probabilita' di un candidato
  entro 5-10 minuti e' alta.
- **Safe (base/esatto/punta)**: `SELECT * FROM safe_strategy_opportunities ORDER BY updated_at DESC LIMIT 20` —
  cercare `valida=true` con un prezzo vivo: e' un'opportunita' che il servizio piazzerebbe al giro successivo.
- **Safe tennis**: `SELECT * FROM safe_strategy_scan WHERE sport='tennis' AND payload->>'back_min' IS NOT NULL
  ORDER BY updated_at DESC LIMIT 10` — un mercato con back disponibile vicino a 1.02-1.11 e' un candidato pronto.
- **Mike**: PRIMA condizione necessaria: `SELECT stats->>'motivo_blocco' FROM mike_control` deve essere DIVERSO da
  «tetto partite raggiunto» (se e' pieno, aspettare che una partita chiuda o scegliere un momento con meno
  partite aperte). Poi cercare in `SELECT * FROM mike_events WHERE state IN ('PRE_OPEN') ORDER BY updated_at
  DESC LIMIT 10` una partita entro la finestra di ingresso (`entry_hours_before_ko`, default 1h prima del KO).
- **Tennis (4 bot)**: `SELECT * FROM tennis_bot_control WHERE status='armed' ORDER BY updated_at DESC` — con
  partite armate in corso, un punto di swing (break point, inizio set) e' un'occasione entro pochi minuti;
  guardare anche `tennis_live_now` per partite appena iniziate (piu' probabilita' di ingressi nei primi game).
- **Scalper**: gia' certificato OK il 26/09 (force-flat pulito, 0 armamenti a freno tirato): non serve una
  finestra dedicata, ma tirarlo nella stessa finestra degli altri per completezza.

**Se non si trova UNA finestra buona per tutti insieme** (probabile: i bot hanno condizioni diverse), fare 2-3
finestre brevi dedicate: una per Omega+Safe calcio (tanti segnali nel weekend), una per Mike (a ridosso di un
kickoff con lo slot libero), una per i 4 bot tennis (durante un game in corso). Ogni finestra segue lo stesso
schema del punto 3.2.

### 3.2 Schema della prova (per ogni finestra)

1. Fotografare PRIMA: `SELECT * FROM omega_trades/mike_trades/safe_strategy_trades/tennis_live_orders WHERE
   created_at > now() - interval '2 minutes'` (deve essere vuoto o gia' noto) + `betfair_live_settings.kill_switch`
   (false).
2. Tirare il freno (1 clic, `set_live_kill_switch(true)`). Annotare l'ora esatta UTC.
3. Attendere il tentativo del bot scelto (di solito entro 1-3 minuti se la condizione era «quasi pronta»).
4. Verificare: **NESSUNA riga nuova** nelle tabelle sopra durante il freno; **DEVE comparire** un `skip`/rifiuto
   esplicito nella tabella di attivita' del bot con un motivo che cita il freno/kill_switch (es.
   `kill_switch`, `db_kill_switch_attivo`, «FRENO TIRATO»); per lo scalper: force-flat entro 2 s delle sessioni
   vive, 0 `auto_armata` nuove.
5. Verificare che il rifiuto NON abbia consumato un tentativo permanente di Omega (R-F2-12, gia' corretto: la
   stessa gamba deve poter riprovare dopo il rilascio, non essere scartata per «max_attempts» raggiunto).
6. Rilasciare il freno (3 clic se necessario, come il 26/09: dopo 2 puo' restare tirato). Annotare l'ora.
7. Attendere 2-5 minuti e verificare che il bot che era «quasi pronto» ORA tenti/entri davvero (prova che il
   rilascio funziona, non solo il blocco).
8. Ripetere per ogni bot/gruppo che non ha avuto un tentativo nella finestra precedente.

**Cosa NON deve succedere in nessuna finestra**: nessun ordine piazzato durante il freno (su nessuna tabella),
nessuna riga doppia dopo il rilascio, nessun bot che «dimentica» di riprovare dopo il rilascio.

## 4. Caduta di rete VERA

Due prove separate, con almeno 1 posizione paper aperta su calcio E una su tennis prima di iniziare (aprire
volontariamente un piccolo trade se non ce ne sono gia', es. lasciare Omega/Safe accesi finche' non aprono).

### 4.1 Stacco di 60 secondi

1. Fotografare PRIMA: posizioni aperte (tutte le tabelle `*_trades`/`tennis_live_orders` status aperto), ultimo
   `battito`/heartbeat di ogni canale (47331-47338), `live_alerts` (ultimo id).
2. Staccare la rete DAVVERO (disattivare l'adattatore di rete di Windows, o staccare il cavo/Wi-Fi: NON un
   firewall software che potrebbe non toccare tutte le connessioni). Cronometrare 60 secondi esatti.
3. Ricollegare la rete.
4. **Atteso** (per costruzione del fix, `FIX_STREAM_STALLO.md`): 60 s e' SOTTO la soglia di escalation (180 s di
   stallo EFFETTIVO dopo un tentativo di ricostruzione): i servizi devono riconnettersi DA SOLI senza un riavvio
   di processo (nessun `RUNNER_WATCHDOG CRASHATO`, nessuna uscita 75). Il battito sui canali deve ripartire entro
   pochi secondi dal ripristino della rete (tipicamente < 30 s: riconnessione flumine/Supabase). Un alert
   `RAW_RECORDER`/`CRITICAL` di stallo PUO' comparire (dipende se lo stallo effettivo supera la soglia interna
   prima del ripristino) ma NON deve seguirlo un riavvio di processo per uno stacco cosi' breve.
5. **Cosa NON deve succedere**: doppi ordini nelle tabelle (confrontare PRIMA/DOPO), posizioni sparite o
   duplicate, «cecita' silenziosa» (se il canale resta muto piu' di qualche minuto SENZA che compaia nessun alert,
   e' un difetto: il rilevamento deve parlare).
6. Tempo di ritorno: annotare in secondi da quando la rete torna a quando ricompare il primo `battito` fresco su
   ciascun canale (47331 calcio, 47332 tennis, 47336 scanner) e a quando i bot tornano a fare cicli normali
   (`omega_stato`/`mike_stato`/`safe_stato` con `last_cycle` che avanza).

### 4.2 Stacco di 5 minuti

1. Stessa fotografia PRIMA del punto 4.1.
2. Staccare la rete per **300 secondi esatti** (cronometrati), poi ricollegare.
3. **Atteso**: 300 s SUPERA la soglia di escalation (180 s di stallo effettivo dopo la ricostruzione fallita):
   il runner calcio e il runner tennis devono uscire con **exit code 75** (non un crash: un'uscita pianificata) e
   il watchdog li deve rilanciare (tipicamente entro 10-20 s dal `RUNNER CRASHATO`/uscita, come gia' osservato nei
   log del 26/09 per altri riavvii). Dopo il rilancio: nuovo login, nuova sottoscrizione, `RUNNER_RESUME` con
   «specchio paper pulito» e `RECONCILE` con il conteggio delle posizioni riprese.
4. **ECCEZIONE dichiarata dal fix**: se ci sono ordini vivi/regole armate al momento in cui scatterebbe
   l'escalation, il codice NON forza il riavvio (guardia money-critical `_lifecycle_blockers`): resta un alert
   CRITICAL ogni 5 minuti finche' non si sblocca. Se si vede questo invece del riavvio, NON e' un difetto: e' il
   comportamento prudente dichiarato — annotarlo comunque, perche' significa che con posizioni aperte il runner
   puo' restare cieco piu' a lungo (decisione gia' presa dal delegato del fix, da confermare all'utente che la
   preferisce cosi').
5. **Cosa NON deve succedere**: doppi ordini, posizioni perse tra prima e dopo il riavvio automatico, il freno
   di prima che si «dimentica» di essere stato rilasciato o tirato, nessun alert affatto (cecita' muta = KO).
6. Tempo di ritorno: come al punto 4.1, ma qui aspettarsi minuti (riconnessione + riavvio processo + resubscribe +
   `RECONCILE`), non secondi. Annotare il numero esatto.
7. Verificare `tennis_bot_activity` e `tennis_bot_control`: i 4 bot devono tornare a scrivere decisioni entro
   pochi minuti dal ripristino (non restare fermi per ore come il 26/09 prima del fix).

## 5. Riavvio dell'app con posizioni paper aperte

1. Prima di chiudere: fotografare tutte le posizioni aperte (tutti i bot).
2. Chiudere l'app in modo ORDINATO (stessa via usata il 26/09: chiusura della finestra principale, non "uccidere"
   il processo a forza).
3. Riaprire l'app.
4. **Atteso**: `RUNNER_RESUME` con «specchio paper pulito (N ordini, M posizioni)» nei log/alert; `RECONCILE` con
   il conteggio giusto; le posizioni aperte PRIMA della chiusura devono comparire ancora nelle tabelle dei bot
   (nessuna persa), NESSUNA riga duplicata (stesso `client_order_ref`/id).
5. Verificare in particolare i 4 bot tennis: `tennis_bot_control` deve tornare `stopped`/`paper` per le righe
   vecchie (non restare `running` a vuoto), e le partite di IERI non si devono riarmare da sole (gia' testato con
   test unitari il 26/09, qui la controprova dal vivo).
6. Verificare che i follow automatici (`live_follow` origine='auto') vengano chiusi correttamente dal
   `riconcilia_interruttori` quando non piu' occupati (non restino STREAMING per sempre: R-28-3 del 28/09 mostra
   29 righe ancora STREAMING ad app spenta dal riavvio ordinato precedente — verificare se e' regredito o se e'
   un comportamento noto del `finally`).

## 6. Verifiche rimaste a meta' (obbligatorie, dal brief)

1. **`source` = nome del bot sugli ordini NUOVI**: dopo un ordine nuovo di Omega o Safe via canale (basta
   aspettare che entrino durante l'osservazione normale, o usare uno degli ingressi del punto 3), leggere
   `SELECT source FROM betfair_live_orders ORDER BY id DESC LIMIT 5`: deve dire `'omega'`/`'safe'`/`'safe_tennis'`
   (o simile), NON `'runner'`. Il 26/09 la migrazione e' stata applicata ma NESSUN ordine e' passato dopo: questo
   e' il primo controllo davvero decisivo rimasto aperto dal cantiere motore ordini.
2. **Ritmo delle righe `loss_exit_deciso` in `mike_activity`**: `SELECT count(*), min(ts), max(ts) FROM
   mike_activity WHERE activity_type='loss_exit_deciso' AND ts > now() - interval '10 minutes' GROUP BY
   event_id`. Atteso dopo il fix (`cf22d37`, firma senza numeri + minimo 5 minuti per evento): AL MASSIMO 1 riga
   ogni 5 minuti per partita, non piu' una al secondo. Il 26/09 la finestra era troppo corta (5 minuti prima
   della chiusura) per essere sicuri: oggi va vista su una finestra piu' lunga (almeno 30-60 minuti con una
   partita aperta).
3. **Pulsante «avvia» di Safe al primo clic**: R-F2-17/R-E2E-1, mai risolto (non era nel perimetro dei fix di
   codice: e' un comportamento dichiarato «solo tennis» della UI). Aprire la scheda Safe TENNIS con Safe CALCIO
   gia' acceso e cliccare avvia: verificare se lo stesso comportamento («solo tennis» spegne base/esatto/punta) si
   ripete. Se l'utente lo considera un difetto (non solo un uso scomodo), va scritto come KO nuovo da correggere;
   se lo conferma voluto, si chiude come «comportamento accettato».

## 6bis. JOURNAL su volume vero + chiusura VERA di una partita tennis (richiesti dal coordinatore, 28/09)

1. **JOURNAL (R-F2-18) su un volume vero**: il 26/09 il fix e' stato verificato su SOLI 2 ordini (nessuna
   ricorrenza dell'alert `JOURNAL` dopo il fix, ma campione troppo piccolo). Oggi (28/09) confermato ancora
   `SELECT count(*) FROM live_alerts WHERE code='JOURNAL'` = 4 righe totali, l'ultima delle 15:26:53Z del 26/09
   (PRIMA del fix): nessuna nuova da allora. **In questa sessione**: dopo che sono passati almeno 15-20 ordini
   veri via canale (calcio + tennis, non solo Safe), ripetere la stessa query filtrando `created_at > <ora di
   inizio sessione>`: deve restare 0. Se compare anche 1 sola riga nuova, e' una regressione del fix
   `FIX_MOTORE_ORDINI_CANALE` (`b0fe3b1`): fermarsi e segnalarlo, non e' un dettaglio.
2. **Chiusura VERA di una partita tennis, `tennis_live_now` → CLOSED dal runner** (R-FA-1): **attenzione**, oggi
   28/09 `tennis_live_now` mostra gia' 30 righe `CLOSED` (`CANTIERE_H_REGISTRO_NC.md` §8.5), ma sono tutte allo
   STESSO `updated_at` al millisecondo (2026-09-28 13:28:48Z): e' una sanatoria/correzione applicata in blocco,
   NON una prova che il runner lo scriva da solo. Prima di iniziare questo passo, fotografare
   `SELECT status, count(*), max(updated_at) FROM tennis_live_now GROUP BY status` (deve dare gia' 30/5/1 con
   `updated_at` vecchio se la sanatoria non e' stata toccata di nuovo). Poi, con l'app accesa e almeno un bot
   tennis armato su una partita che sta per finire, attendere la fine REALE della partita e verificare: (a) la
   riga di QUELLA partita passa a `CLOSED` con un `updated_at` FRESCO (di quell'istante, non 13:28:48Z); (b) i bot
   tennis chiudono/annullano le posizioni residue su quel mercato; (c) il tetto (`tennis_bot_control`, R-F2-6)
   scende di conseguenza. Se la partita finisce e la riga resta `OPEN`/`SUSPENDED` con `updated_at` vecchio, il
   fix NON funziona dal vivo nonostante la sanatoria storica: e' un reperto nuovo, va al coordinatore.

## 7. Controlli (b) del registro da riprendere qui

Vedi `CANTIERE_H_REGISTRO_NC.md` §5.4 per l'elenco completo per id. In ordine di priorita' durante questa sessione:
1. tutti i campi di §2 sopra (gia' inclusi, priorita' massima);
2. K1 — confrontare le size a video con `payload.valuta='EUR'` nelle righe nuove di `safe_strategy_scan` (senza
   chiamare Betfair: solo leggere se il tag c'e', poi chi ha il permesso confronta col REST);
3. O-4 — query sulle leghe 36, 850, 637 nell'atlante rigenerato di oggi per lo `stagione_rif` per lega;
4. R-FA-2/3 — un frame Mike nuovo e un dossier nuovo, verificare le 4 chiavi v4 e lega/id squadra;
5. tutto il resto del blocco (b) del registro, se il tempo lo consente (bassa urgenza, nessun money impact
   diretto).

## 8. Consegna della sessione

Scrivere in `CRONOSTORIA.md` (sezione del giorno) ogni passo con esito e ora esatta, aggiornare
`CANTIERE_H_REGISTRO_NC.md` spostando ogni voce da (b) a chiuso/KO con la prova, e riportare all'utente: quanti
campi confermati a schermo, quanti ancora divergenti (nuovi KO, se emergono, vanno al coordinatore con file:riga
prima di qualunque correzione), esito delle 2 prove di rete, esito del freno su tutti i bot, esito del riavvio con
posizioni aperte.
