# U-60 - Misura delle letture REST del DB (i 120 ms assunti dal banco)

Data 09/10/2026. Autore: delegato (Sonnet 5.5). Sola lettura: solo GET, nessuna scrittura, nessuna RPC, nessun replay.
Il banco NON e' stato toccato. Script: `misura_letture_rest.py`. Grezzo: `misure_20261009_181627.jsonl` (1.240 righe, 20 di riscaldamento). Uscita: `uscita_misura.txt`.

## 1. Quali letture imita il banco (e quali NO)

`LATENZA_LETTURA_S = 0.120` (`banco_comune.py:1976`) e' usata in DUE punti:

- **(a) Verifica DB "del bot / fuori bot"** (`ordini_esterni_banco.py:175`, `ConfermaBanco.chiedi`): l'esito diventa visibile dopo
  `n select x 120 ms`. Le select sono quelle VERE di `esposizione_fuori_bot.proprietari_bot` (blocchi da 100 bet_id): per ogni blocco
  5 GET PostgREST con `mode=eq.live&bet_id=in.(...)`:
  `omega_trades` (bet_id), `safe_strategy_trades` (bet_id), `mike_trades` (bet_id), `betfair_live_orders` (bet_id,source),
  `betfair_live_order_requests` (bet_id,client_ref,params). **QUESTE le ho misurate**, con 1 bet_id (caso tipico: una lettura per bet_id nuovo).
- **(b) `list_current_orders` / `list_cleared_orders` / `read_book`** (`banco_comune.py:1062 _costa_una_lettura`): il commento del banco
  (righe 1967-1975) le dice REST sincrone **verso Betfair** (non verso il DB). **NON misurate**: richiedono sessione Betfair e
  il compito vietava processi/ordini nuovi; la rete verso Betfair e' un'altra cosa dalla rete verso Supabase. Il 120 ms del banco
  copre entrambe con un unico numero: qui si conosce solo la parte DB.

## 2. Metodo

5 endpoint x 60 giri x 2 modi = 600 campioni validi per modo (1.200 totali), pausa 250 ms fra una GET e l'altra, 1 GET di riscaldamento
per endpoint e modo scartata (salvata nel grezzo). Cronometro `time.perf_counter()` (da prima della richiesta a corpo letto).
- **nuova** = `urllib.request`: NON riusa la connessione (apre TCP+TLS a ogni GET). E' il caso peggiore.
- **viva** = `http.client` keep-alive su una connessione sola (1 apertura per serie, verificato): e' il caso del bot in produzione
  che tiene la sessione viva. Non ho verificato il client reale dei bot (supabase-py/httpx): assumo che riusi la connessione.
- Chiave service-role di `.env`, host Supabase `dqbwaocvlzbxfrpacsac.supabase.co`, filtro con un bet_id reale (1 riga in `safe_strategy_trades`
  da cui i 27 byte medi; le altre tabelle rispondono `[]`, 2 byte).
- Serie 1: 18:16:27 - 18:21:59. Attesa 300 s. Serie 2: 18:26:59 - 18:31:21 (orologio PC, `Get-Date`: 18:15:40 prima, 18:31:41 dopo; ora +02:00,
  sincronizzata, scarto -0,16 s dichiarato). Totale 15 min.

## 3. Risultati (ms, solo risposte HTTP 200; entrambe le serie insieme)

### Connessione VIVA (il caso di produzione)

| Endpoint | N | p50 | p90 | p99 | min | max | byte medi |
|---|---:|---:|---:|---:|---:|---:|---:|
| omega_trades | 120 | 111,5 | 148,0 | 198,4 | 87,9 | 232,7 | 2 |
| safe_strategy_trades | 120 | 109,6 | 145,4 | 451,2 | 85,0 | 471,0 | 27 |
| mike_trades | 120 | 111,7 | 148,6 | 5.231,3 | 84,5 | 9.185,5 | 2 |
| betfair_live_orders | 120 | 113,3 | 147,8 | 968,4 | 80,6 | 6.857,9 | 2 |
| betfair_live_order_requests | 120 | 108,4 | 148,3 | 234,2 | 78,7 | 407,0 | 2 |
| **TUTTI** | 600 | **110,8** | **148,2** | **471,0** | 78,7 | 9.185,5 | 7 |

### Connessione NUOVA per ogni GET (urllib)

| Endpoint | N ok (non200) | p50 | p90 | p99 | min | max | byte medi |
|---|---:|---:|---:|---:|---:|---:|---:|
| omega_trades | 120 (0) | 229,8 | 284,0 | 523,0 | 180,5 | 641,9 | 2 |
| safe_strategy_trades | 120 (0) | 226,6 | 273,9 | 470,9 | 167,1 | 1.117,6 | 27 |
| mike_trades | 119 (1) | 226,5 | 270,8 | 7.533,9 | 176,2 | 9.184,2 | 2 |
| betfair_live_orders | 119 (1) | 225,7 | 315,4 | 639,8 | 174,1 | 3.336,9 | 2 |
| betfair_live_order_requests | 120 (0) | 230,1 | 273,7 | 1.905,0 | 173,2 | 5.359,0 | 2 |
| **TUTTI** | 598 (2) | **227,7** | **278,9** | **1.810,7** | 167,1 | 9.184,2 | 7 |

Le 2 risposte "non 200" sono errori di rete/timeout lato client (codice -1, 13,2 s e 7,5 s), non HTTP 4xx/5xx: **nessun 4xx/5xx visto**.

### Per serie (tutti gli endpoint)

| Serie | modo | N | p50 | p90 | p99 | max | media | campioni > 500 ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | viva | 300 | 108,7 | 149,2 | 5.231 | 9.185 | 196,6 | 5 |
| 1 | nuova | 298 | 219,7 | 310,3 | 5.359 | 9.184 | 327,4 | 11 |
| 2 | viva | 300 | 115,2 | 147,2 | 169,6 | 258,1 | 120,7 | 0 |
| 2 | nuova | 300 | 231,1 | 273,6 | 330,1 | 337,0 | 234,2 | 0 |

**Episodio anomalo**: nella serie 1 fra le 18:19:29 e le 18:20:50 (~80 s) ci sono stati ripetuti rallentamenti da 1,5 a 13 s su tutti e due i
modi (10 campioni > 1,5 s, 2 timeout) e poi tutto e' rientrato. Causa NON accertata (rete locale, gateway Supabase o Postgres: non ho
accesso ai log di Supabase in questa misura). La serie 2, 5 minuti dopo, non mostra nulla del genere (max 337 ms).

Riscaldamento (connessione aperta): nuova mediana 233 ms; viva primo GET 302 ms (apertura TCP+TLS+richiesta), poi mediana 116 ms.
Quota di campioni <= 120 ms: viva 64,8 %; nuova 0 %.

## 4. Confronto con i 120 ms assunti

- Connessione viva (produzione): p50 110,8 ms = **9 ms SOTTO** i 120 (-8 %); p90 148,2 = +28 ms (+23 %); p99 471 ms (3,9 x) per la coda dell'episodio.
  Escluso l'episodio (solo serie 2): p50 115,2, p90 147,2, p99 169,6 ms: i 120 ms cadono fra p50 e p90.
- Connessione nuova a ogni GET: p50 227,7 ms = **108 ms SOPRA** (+90 %, quasi il doppio).
- Il costo e' dominato dal giro di rete, non dalla query: tutte e 5 le tabelle danno lo stesso p50 (108-113 ms vivo) e la risposta e' di pochi byte.
- **Incoerenza con la misura precedente** (`07_MISURE_OGGI.md` §4.3): `GET /rest/v1/` su connessione viva dava p50 21,3 ms (rete+gateway senza query)
  e TCP 15,4 / TLS 50,5 ms. Oggi, con query vera e connessione viva, il minimo e' 78,7 ms e il p50 111 ms: ~90 ms in piu' del solo giro. Possibili cause (NON
  verificate): tempo in Postgres/PostgREST (autenticazione JWT, RLS, piano della query) di ~70-90 ms contro i 13 ms medi di `pg_stat_statements`
  per SELECT di `analytics_signals`; rete del PC piu' lenta oggi (CPU del PC alta, vedi sotto); il run di `m07_lab_rete.py` senza chiave (401) esce prima del
  lavoro vero. Va letto con cautela: la differenza fra le due misure e' piu' grande della differenza da 120 ms.

## 5. Stato della macchina durante la misura

- App: **spenta**. `tasklist` (18:15): nessun `AlphaScore Trading.exe` ne' `electron`; solo 2 `python.exe` (34212, 34724, non miei: l'ambiente di sessione).
  Quindi il DB non aveva il traffico dei bot (~700-1300 richieste/min delle misure del 02-08/10) e gli endpoint rispondevano senza concorrenza dell'app.
  Non e' il carico di produzione: in produzione i p99 possono essere peggiori.
- CPU totale (`Win32_Processor.LoadPercentage`, 5 campioni da 1 s): 28/83/44/25/27 % prima della misura; **100 % x 5 campioni dopo**. Contatore
  `Get-Counter` non disponibile (nomi localizzati in italiano). A fine misura il processo con piu' CPU cumulata e' `find` (PID 28660, 20.293 s di CPU: un
  `find.exe` di Windows fuori controllo, NON lanciato da me), seguito da Creative Cloud. Non l'ho toccato. Puo' aver sporcato i tempi di una macchina
  Ryzen 7 3750H; la serie 2 (piu' stabile) e' comunque venuta dopo la serie 1 con lo stesso carico possibile, quindi non c'e' prova che sia la causa dell'episodio.
- Rete: PC dell'utente (stessa macchina e rete dell'app), Wi-Fi/cavo non verificato.

## 6. Cio' che NON ho potuto misurare / verificare

- Le letture verso **Betfair** (`list_current_orders`, `list_cleared_orders`, `read_book`): nessuna misura (vedi 1b).
- Con l'**app accesa** e il DB sotto carico dei bot.
- Il client HTTP reale dei bot (supabase-py/httpx, pool, HTTP/2): ho misurato `urllib` (nuova) e `http.client` (viva), che sono i due estremi.
- Query con molti bet_id (blocchi fino a 100): misurato solo 1 bet_id (il caso tipico di `ConfermaBanco`); l'URL e il filtro `in` piu' lunghi non sono misurati.
- La causa dell'episodio di 80 s e della differenza con i 21 ms del 04/10; il tempo in Postgres per le 5 tabelle (non ho letto `pg_stat_statements`).
- Orari diversi del giorno: due serie in 15 minuti, alle 18:16-18:31 di un venerdi' (09/10).

## 7. Raccomandazione (la decisione e' dell'utente; nel banco non e' stato cambiato nulla)

**Per la parte DB, confermare i 120 ms come valore centrale: la mediana a connessione viva e' 111 ms (p90 148 ms) e quella a connessione nuova 228 ms; l'incertezza va dichiarata come "110-150 ms tipico, 230 ms se il bot non riusa la connessione, code di secondi in rari episodi" e il valore va rimisurato con l'app accesa e per le letture Betfair prima di toglierlo dalla lista delle assunzioni.**
