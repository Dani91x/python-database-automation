# Rapporto di fine giornata 30/09/2026 — cosa fare stasera, cosa vedere domani in live

_(bozza dalle 21:25; si chiude con il commit F2 e il push)_

## 1. Migrazioni da applicare STASERA (SQL editor di Supabase, in questo ordine)

| # | File | Obbligatoria? | A cosa serve | Verifica dopo |
|---|---|---|---|---|
| 1 | `migrations/mike_state_arretrati_prova_2026-09-30.sql` | SI' (**non applicata**: verificato sul DB alle 20:25, `get_mike_state` non porta `arretrati_prova`) | la pagina di Mike e la Control Room separano «oggi» dagli arretrati paper regolati oggi | `select public.get_mike_state() ? 'arretrati_prova';` → true |
| 2 | `migrations/live_orders_account_open_2026-09-30.sql` | SI' (nuova) | la Control Room mostra gli ordini fatti da te dal sito/app per partita («ordini fuori dai bot») e la testata sa dire «N partite a rischio vero» | `select public.get_live_orders_account_open();` → `{rows:[...], letto_at:...}` (oggi torna i 3 ordini di Vsetin finche' l'app non rilegge il regolamento) |
| 3 | `migrations/mike_storico_giorno_regolamento_2026-09-29.sql` | SI' — dichiarata applicata da te alle 12:xx: **confermalo** | storico di Mike per giorno del regolamento (l'etichetta «per regolamento» a schermo e' vera solo se e' applicata) | `select jsonb_array_length(public.get_mike_day_trades(current_date, 'paper'));` senza errore |
| 4 | `migrations/tennis_bot_daily_giorno_partita_2026-09-30.sql` | facoltativa | storico dei bot tennis per giorno della partita (sui dati di oggi il risultato non cambia) | — |
| 5 | `migrations/tennis_paper_voided_residuo_zero_2026-09-30.sql` | facoltativa | ordini tennis VOIDED non piu' contati come posizioni aperte | — |
| — | `migrations/mike_reentry_max_goals_2026-09-29.sql` | no-op se gia' applicata | — | — |

`.env`: **nessuna riga nuova** (il tetto 80 delle partite di Mike e' nel codice; `MIKE_MAX_FOLLOWED` resta solo un override).

Poi: `npm run build` lo faccio io a fine review (ti dico quando); **riavvio dell'app** da parte tua dopo le migrazioni e il build (scanner e Mike sono processi Python: il codice nuovo parte solo al riavvio). All'avvio nessun bot opera: Mike lo accendi tu.

## 2. Cosa e' cambiato oggi (per il trader)

- **Mike**: 3 minuti pieni al fischio anche con abbinamento parziale, poi ritiro del resto e copertura sul 4,5 per l'importo rimasto; vede in tempo reale (stream ordini del conto) se chiudi tu dal sito; P&L = quello del conto Betfair (anche le tue chiusure manuali, riga «TUO»); mercato deciso dai gol; ultimo ingresso riprova fino al fischio; banca Under 4,5 di serie; regolamento al centesimo come Betfair.
- **Velocita' dei punteggi** (senza una chiamata in piu' a Betfair): al fischio e ai gol lo scanner legge i punteggi SUBITO (sveglia dallo stream) invece che entro 2 s; nei primi 5 minuti dopo il fischio, se il fornitore non da' ancora il punteggio, legge la cronologia (timeline), che sulla storia arriva prima (24 casi su 30). Mike legge lo stato dello scanner dal canale locale invece che dal DB ogni secondo. Tetto delle partite di Mike a 80 e avviso «oltre il tetto» solo quando morde davvero.
- **UI** (tutte le sezioni del tuo elenco): fascia SOLDI VERI ADESSO in testata; Obiettivo di oggi senza lorda e senza stime; cash out della partita = somma esatta delle gambe vive, netto commissione, con la fonte; cash out globale; schede sport a due corsie LIVE/PROVA; scheda pre-match e live con linee O/U, esiti VERI delle chiusure («RITIRATO dal bot», «RIFIUTATO da Betfair: codice»), chip dei bot veri (FERMO / IN ARRESTO / ERRORE, LIVE col suo colore anche a bot fermo); freni per bot; posizioni aperte LIVE e PROVA separate; **Conferma della chiusura live inerte per 400 ms su tutti i bot** (doppio clic = niente soldi veri per sbaglio); etichette «copertura sulla linea 4,5» ovunque; badge delle linee ferme con l'eta' vera.

## 3. Domani, live di Mike: checklist (nell'ordine)

1. Dopo il riavvio: nel log dello scanner niente piu' «partite seguite da Mike OLTRE il tetto» a ripetizione; stato scanner con il blocco `ips` (contatori).
2. Al primo fischio di una partita seguita: nel log dello scanner «primo punteggio <id> dopo N s dal primo in-play, fonte timeline|scores» — e' la misura del guadagno; `ips.sveglie` che cresce.
3. Nel log di Mike niente letture di `safe_strategy_status` a ogni giro (stato dal canale).
4. Nel log del runner niente piu' errori `23514 ... betfair_live_orders_source_check`.
5. Sulla scheda live: cash out della partita con la riga «solo ordini dei bot»; se chiudi tu dal sito, Mike lo segna entro pochi secondi (non piu' 90).
6. Ai 3 minuti dal fischio con banca parziale: ritiro del resto e copertura 4,5 per l'importo rimasto (regola tua di oggi).

## 4. Limiti dichiarati (non verificabili senza il vivo)

- Che il fornitore metta il punteggio nella timeline gia' al fischio: se no, tutto come prima (nessuna regressione, nessun guadagno).
- Le due funzioni SQL nuove non sono state compilate dal server (vietato scrivere sul DB): se una migrazione da' errore, mandami il testo.
- Un ordine tuo dal sito su un mercato mai seguito dall'app, regolato ad app chiusa, resta «aperto» nella RPC finche' non lo si rilegge (dichiarato a schermo).

## 5. Riferimenti

`CRONOSTORIA.md` 30/09 (blocchi admin-bc e admin-07) · `AUDIT_2026-09-30/REVIEW_FINALE_PRIMA_DELLA_CONSEGNA.md` ·
`VELOCITA_FEED_E_GIRI.md` · `BACKEND_PER_UI.md` · `PREPARAZIONE_PAPER.md` · `COME_SI_COMPORTA_MIKE_35760084.md`.
