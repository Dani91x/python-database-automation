# PIANO DI OTTIMIZZAZIONE GLOBALE (deciso dall'utente il 02/10/2026, da fare)

Obiettivo: un'app professionale che gira h24 con tutti i bot accesi, **senza perdere nessuna
funzionalita' attuale**: i processi che decidono lavorano IN MEMORIA, il DB cloud (Supabase) resta
come ARCHIVIO e per le statistiche storiche (resta obbligatorio per alcuni processi: storici,
analisi, app). Niente riscritture: riordino a blocchi, un bot alla volta, sempre certificato dal banco
(replay identici numero per numero) e dalle suite.

## Le misure di partenza (02/10, 17:20, solo Mike acceso in live su 2 partite)

| Fonte | Richieste al DB | Nota |
|---|---|---|
| Supabase lato server (tutto) | 6.700-7.200 ogni 5 min ≈ 1.400/min ≈ 2 milioni/giorno | 0 errori, progetto sano |
| Mike (log) | 269/min: `mike_trades` x121, `mike_requests` x59, `mike_control` x59, `mike_events` POST x24, `safe_strategy_scan` x14 | rilegge ogni giro cio' che ha scritto |
| Safe bot (paper, non opera) | 255/min | idem |
| Omega | 13/min | |
| runner, scanner, tennis, scalper, app | non misurabili dai log (non registrano le chiamate) | = il resto delle 1.400 |

Diagnosi: i prezzi dello stream gia' NON passano dal DB (runner → canali locali → bot e app). Passano
dal DB a ritmo di giro: lo stato e le posizioni dei bot (riletti ogni giro), i comandi e il controllo
dall'app (`*_control`, `*_requests`), l'elenco delle partite dello scanner (`safe_strategy_scan`).
Il DB e' usato come POSTINO fra processi, non come archivio. Avvisi Supabase: nessuno grave.

## Fase 0 (1 giorno): modulo di monitoraggio «Salute»

Un modulo Python unico `Betfair/monitor/` importato da ogni servizio (contatori in memoria, aggancio ai
client DB e Betfair gia' esistenti, `psutil` per il processo), una riga ogni 30 s per servizio in
`monitor_metrics` (migrazione), una pagina «Salute» nell'app (una chiamata ogni 10 s, semafori a
soglie dichiarate), un referto giornaliero in `AUDIT_MONITOR/`. Misura: CPU, memoria e crescita, giri al
minuto e durata, eta' del feed per partita con soldi a mercato, chiamate DB per tabella e tipo, REST
Betfair per endpoint, messaggi stream, riconnessioni, ordini per bot e modalita' (paper/live separati),
rifiuti con codice, CRITICAL per codice, disco, dimensione log, deriva dell'orologio. Spento nel banco
per costruzione. In seconda tappa: CRITICAL a Telegram, uno per episodio.

## Fase 1 (2-3 settimane): i blocchi, nell'ordine

1. **Memoria del processo + persistenza come archivio** (pilota: Mike, poi Safe, Omega, tennis,
   scalper): stato e posizioni in memoria; rilettura del DB solo dopo una propria scrittura, un
   regolamento, o ogni 30 s di sicurezza; scritture solo se cambia qualcosa; ritenti e timeout
   uniformi in uno strato unico. Opzione avanzata: archivio locale SQLite (WAL) per stato e diario,
   con copia a lotti verso Supabase. Al riavvio il processo si ricostruisce da archivio + Betfair
   PRIMA di decidere (prove obbligatorie: uccidere il processo con posizioni aperte in paper).
2. **Comandi sui canali locali**: «ferma», «modalita'», «approva uscita» come messaggio (ms), DB come
   storia e riserva (rilettura ogni 30 s).
3. **Scanner come blocco proprio** (oggi dentro `safe_strategy/service.py`): un solo feed partite per
   tutti via canale, esposizioni di tutti i bot gia' dentro (fatto il 02/10).
4. **Porta unica degli ordini**: vie laterali (REST diretti dei bot, `order_exec` manuale, Mike live
   diretto) dietro il motore del runner; paper come adattatore della stessa porta.
5. **Riconciliazione unica** nel blocco ordini (chiude il reperto 2 di Safe: posizione nettizzata per
   selezione).
6. **Bot come plugin** con valori di serie in un posto solo (Python e frontend).
7. **Test di contratto**: nessun file fuori dagli adattatori importa `betfairlightweight`, `supabase`
   o il client dei punteggi.

## Fase 2 (1 settimana, in parallelo): indurimento h24

Supervisore con riavvio automatico + arresto ordinato (fatto il 02/10 per scalper/Mike/Safe/Omega);
sessione Betfair rinnovata da sola; scenario del banco «Betfair giu' 5 minuti»; rotazione dei log e
tetto di memoria; riavvio notturno solo senza posizioni; cambio di giorno senza riavvio (stop, obiettivo,
storici); riconciliazione notturna col conto; pagina di salute unica.

## Regole del programma

- Ogni passo entra su master solo con: suite Python e frontend verdi, replay di TUTTI i bot identici,
  parita' paper/live, falsificazione dei test nuovi, referto di monitoraggio uguale o migliore.
- Mai due blocchi sullo stesso file. Il live gira sulla versione certificata; il riordino su rami.
- L'utente riavvia l'app a ogni passo integrato, mai con posizioni aperte.
- Stima totale: 3-4 settimane. Primo passo: fase 0 + blocco 1 su Mike come pilota.

## Riferimenti

`CRONOSTORIA.md` sezione 02/10 (misure e decisioni), `SCHEMI_BOT/sistema/ARCHITETTURA_ATTUALE.html`
(schema interattivo dell'architettura attuale, in costruzione il 02/10 sera), `PROCESSO_STANDARD_BOT.md`.
