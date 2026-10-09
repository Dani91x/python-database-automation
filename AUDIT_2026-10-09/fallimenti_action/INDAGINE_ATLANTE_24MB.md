# Indagine: perche' l'atlante hazard pesa 24 MB al giorno (09/10/2026, sola lettura)

Domanda dell'utente: «24 MB al giorno sono troppi! come mai? tutto cio' che arriva sul database deve
pesare il meno possibile SENZA PERDERE DATI O QUALITA». Nessun file modificato, DB mai toccato.
Misure fatte sull'atlante locale `Betfair/omega/data/hazard_atlas_live.json` (24.022.038 byte, scritto
oggi 10:24, 381 leghe) e sullo stato locale `hazard_atlas_stato.json` (37.482.962 byte, 404 leghe).
Sono copie locali dello stesso formato del DB, non il DB: i numeri sul DB (dimensione TOAST, righe
presenti) NON verificati.

## 0. In breve

1. Il globale (`hazard_atlas.payload`) e' una funzione pura dello stato per lega (`hazard_atlas_leghe`)
   piu' il seme v3: contiene gli STESSI dati gia' presenti per lega, riassemblati (con shrinkage).
   Peso: 24,0 MB compatto, ma solo 3,87 MB con gzip (6x di ridondanza testuale).
2. `h2h_hint` pesa 13,19 MB (55%) perche' sono 59.072 coppie squadra-squadra, ognuna con due oggetti
   `team_a`/`team_b` (id + nome) che ripetono cio' che e' gia' nella chiave `idA-idB` e in `by_team`.
3. **Nessuno legge `hazard_atlas.payload` nel funzionamento predefinito.** Il PC (modo `domanda`,
   default, `hazard_atlas_sync.py:140-152`) assembla il suo `hazard_atlas_live.json` da se' leggendo
   `hazard_atlas_leghe`, non scarica mai la riga globale. Il payload lo scarica solo il modo
   opzionale `scarica` (`hazard_atlas_sync.py:93`), che `.env` non attiva (c'e' solo
   `HAZARD_ATLAS_SYNC=1`, nessun `HAZARD_ATLAS_MODO`). Della riga globale la action legge davvero solo
   la filigrana `watermark_event_id` (`genera_atlante.py:876-878`, workflow `hazard_atlas.yml:121`).
4. Le versioni NON crescono all'infinito: se ne tengono 7 (`genera_atlante.py:1092-1115`, `tieni=7`):
   ~7 x 24 = 168 MB logici, non 9 GB l'anno. Il costo vero e' la scrittura (27 MB in una POST) e il
   ricambio (ogni notte 24 MB inseriti e 24 MB cancellati = bloat TOAST fino al vacuum).
5. Proposta: smettere di scrivere il payload globale nel DB e tenere nella riga solo la filigrana
   (par. 6).

## 1. Cosa c'e' nel payload (misurato, chiave per chiave)

Prodotto da `genera_atlante.assembla` (`genera_atlante.py:326-540`, `out` a `:531-532`) a partire dallo
stato per lega (letto da `hazard_atlas_leghe`), `incrementale` (`:802`) e il seme v3 (`:464-475`).

| Chiave | Byte (compatto) | gzip -6 | Cosa e' |
|---|---|---|---|
| `h2h_hint` | 13.190.029 (55%) | 1.529.715 | 59.072 coppie `idA-idB` (>=3 scontri, `MIN_H2H=3`, `:80`): `n_meetings`, `team_a{id,name}`, `team_b{id,name}`, `ft_scores_a_b{"2-0":n,...}`, `ht_scores_a_b{...}` |
| `by_team` | 6.140.671 (26%) | 1.292.604 | 8.745 squadre (`MIN_TEAM_MATCHES=10`, `:79`): `team_name`, `league_id`, `n_matches`, `att_`/`def_goals_per_match_by_bucket` (18 fasce da 5') |
| `by_league` | 2.541.783 (11%) | 337.488 | 381 leghe: `meta` + `grid` (fasce x gol -> `p_goal_next_3min`, `p_goal_next_2min`, `n`) |
| `v4` | 2.024.397 (8%) | 703.905 | blocco v4 (quasi tutto `v4.by_league`, 2,02 MB) |
| `meta` | 119.817 | 9.443 | 27 campi; `per_league` 117.745 byte |
| `global` | 5.280 | 1.005 | griglia globale |
| totale | 24.022.038 | 3.874.588 | |

Dettaglio `h2h_hint` (59.072 coppie, media 210 byte/coppia):
- chiavi `idA-idB`: 774.052 byte; nomi dei campi ripetuti (`n_meetings`, `team_a`, `team_b`,
  `ft_scores_a_b`, `ht_scores_a_b`, `id`, `name`): 5.128.591 byte di sole etichette (39% di `h2h_hint`).
- `team_a`/`team_b` ripetono l'id gia' nella chiave. 7.167 squadre distinte compaiono in 118.144 slot
  (media 16 ripetizioni). In 943 slot il nome in `h2h_hint` DIFFERISCE dal `team_name` di `by_team`
  (varianti di scrittura): i nomi non si possono cancellare e ricavare da `by_team`; vanno tenuti
  (anche una volta sola, in un dizionario id -> nome).
- `n_meetings` e' sempre uguale alla somma di `ft_scores_a_b` (59.072/59.072): campo derivabile.
- scontri per coppia: 4 scontri 17.728 coppie, 3: 8.448, >=10: 10.575.
- nessun `null`, nessuna lista vuota, 225 `{}`; nessun float con molti decimali.
Riduzioni lossless misurate: solo togliere `team_a`/`team_b` -> 8,08 MB (gzip 1,04 MB); forma ad array
`[n, ft, ht]` senza nomi -> 5,42 MB (gzip 0,95 MB); con dizionario nomi ~5,6 MB.

Dettaglio `by_team`: i due blocchi di 18 fasce valgono 2,48 MB ciascuno (4,97 MB = 81%). Le 18 chiavi
fascia sono identiche e nello stesso ordine in tutte le 8.745 squadre (verificato). I valori hanno gia'
al piu' 5 decimali (283.377 su ~315.000 float ne hanno 5, 28.252 ne hanno 4): non c'e' margine sui
decimali. Forma ad array di 18 numeri: 2,80 MB (gzip 0,93 MB), nessun dato perso.
`by_league`: 396 `null`, irrilevanti.

## 2. Perche' una versione globale intera ogni giorno

- E' una ISTANTANEA completa: `salva_versione` (`genera_atlante.py:1092-1100`) inserisce una riga nuova
  con l'atlante assemblato intero; non esiste un delta. La action aggiorna lo stato SOLO delle leghe
  toccate (`salva_leghe`, blocchi da 20) ma riassembla e riscrive SEMPRE tutto il globale.
- Versioni conservate: 7 (`tieni=7`, commento migrazione `hazard_atlas_2026-09-24.sql:19`); la potatura
  (`:1101-1115`) cancella con DELETE gli id oltre i primi 7 e non fa mai fallire la scrittura buona.
  Quindi ~168 MB in tabella, non 9 GB. Rischio reale: dead tuples nel TOAST finche' il vacuum non li
  libera (non misurabile senza DB).
- La migrazione del 24/09 stimava ~4 MB a riga (7 = ~30 MB). Oggi e' 6x (381 leghe, h2h, v4); crescita
  ~75 KB/lega (misura del 28/09 in `hazard_atlas_rpc_scrittura_2026-09-28.sql`).
- `hazard_atlas_leghe` NON duplica il globale: contiene lo STATO GREZZO per lega (conteggi additivi,
  `fixtures` gia' contati), da cui il globale e' derivato. Peso sullo stato locale (404 leghe): `h2h`
  21,48 MB, `teams` 8,21 MB, `fixtures` 3,47 MB, `v4` 3,47 MB, `cells` 0,55 MB: ~37,5 MB. E' la FONTE;
  il globale e' la derivata, ridondante rispetto a essa. La derivata si riassembla in locale
  (`atlante_a_domanda._scrivi_live`, `atlante_a_domanda.py:525`).

## 3. Chi legge il payload e come

| Lettore | Cosa legge | Frequenza |
|---|---|---|
| PC, modo `domanda` (default), `atlante_a_domanda.py:219` | per lega nuova: `hazard_atlas_leghe` (`stato,fixtures`, una GET per lega); assembla in locale `hazard_atlas_live.json` | ciclo 600 s, solo leghe delle partite osservate |
| PC, modo `scarica` (non attivo), `hazard_atlas_sync.py:85-93` | 1 GET da 1 riga ogni 1800 s; se piu' nuova scarica `payload` (timeout 180 s) | mai nel setup attuale |
| Action `leggi_stato_db` (`genera_atlante.py:869-879`) | TUTTE le righe `hazard_atlas_leghe.stato` (senza `fixtures`) + SOLO `watermark_event_id` dell'ultima riga globale | ogni notte |
| Workflow prerequisiti (`hazard_atlas.yml:121`) | solo `watermark_event_id` | ogni notte |
| App/frontend/desktop | nessun accesso alle tabelle `hazard_atlas*` (grep: solo un campo numerico `hazard_atlas` in `frontend/src/lib/mike.ts:218`) | - |

Il file locale `hazard_atlas_live.json` e' letto in memoria dai bot: `by_team`
(`hazard_atlas.py:206-225`, `safe_strategy/selezione.py:130,156`), `h2h_hint`
(`omega_advisor.py:204-231`, `selezione.py:182`: UNA coppia per chiave `min-max`), `by_league`/`global`.
I bot usano `h2h_hint` una coppia alla volta e `by_team` due squadre alla volta. Il payload nel DB e'
dunque dato scritto e mai letto nel setup attuale, a parte la filigrana.

## 4. Opzioni (per guadagno/costo)

| # | Opzione | Byte scritti per notte | Cosa cambia per chi legge |
|---|---|---|---|
| (a) | Non scrivere il payload: la riga globale tiene solo filigrana e conteggi (`payload` minimo, es. solo `meta`+`global` ~125 KB) | ~0,13 MB invece di 24 | Nessuno nel modo `domanda` (default). Il modo `scarica` smette di servire (`_valido()` in `hazard_atlas_sync.py:68` rifiuta il payload vuoto): va disabilitato esplicitamente o rifatto assemblando da `hazard_atlas_leghe`. La RPC resta |
| (b) | Normalizzare senza perdite: dizionario id->nome, `n_meetings` derivato, array a 18 numeri in `by_team` | ~24,0 -> ~13,4 MB (h2h 5,6 + by_team 2,80 + by_league 2,54 + v4 2,02 + meta 0,12) | Cambia il FORMATO: `omega_advisor`, `selezione`, `hazard_atlas` da adattare e ricertificare; rischio regressioni sulle strategie |
| (c) | gzip in bytea o Storage, in tabella solo la filigrana | ~3,87 MB (gzip -6); in bytea via PostgREST diventa base64, ~5,2 MB | Il lettore `scarica` deve decomprimere; nessun cambio di formato dei dati |
| (d) | Delta rispetto alla versione precedente | ~2-8 MB (cambiano ~20-150 leghe su 381 a notte, `hazard_atlas_2026-09-24.sql:24`) | Il lettore ricostruisce una catena di delta: complessita' alta, nessun lettore lo richiede |
| (e) | Tenere 1-2 versioni invece di 7 | scrittura invariata (24 MB), tabella 168 -> 24-48 MB | Nessuno (serve solo l'ultima filigrana). Non risolve i 520 |

Combinando (b)+(c) il payload scenderebbe a ~1,9 MB se mai servisse davvero.

## 5. Vincoli Supabase/PostgREST (con fonti)

- Timeout statement (https://supabase.com/docs/guides/database/postgres/timeouts): anon 3 s,
  authenticated 8 s, service_role «none (defaults to the `authenticator` role's 8s timeout if unset)»,
  postgres «none (capped by default global timeout to be 2min)». Un timeout per funzione si imposta con
  `set statement_timeout TO '4s'`: e' la RPC `hazard_atlas_salva_versione` (120 s, migrazione del
  28/09). Risolve il 500/57014, NON il 520.
- Compute Micro (https://supabase.com/docs/guides/platform/compute-and-disk): 1 GB di RAM, 60
  connessioni massime (Small: 2 GB, 90).
- Errore 520 Cloudflare (https://developers.cloudflare.com/support/troubleshooting/http-status-codes/
  cloudflare-5xx-errors/error-520/): «l'origin restituisce una risposta vuota, sconosciuta o
  inattesa»; cause: crash dell'origin, risposta vuota/malformata, HTTP/2 mal configurato. Non cita un
  limite di dimensione del corpo.
- Un limite documentato di dimensione del corpo di richiesta di PostgREST/Supabase NON l'ho trovato:
  la pagina https://supabase.com/docs/guides/platform/limits risponde 404. Non asserisco una soglia.
  Inferenza (non provata): un corpo da ~27 MB viene letto e parsato da PostgREST/Postgres su 1 GB di
  RAM con 60 connessioni; con altre action in coda sul DB il processo cede e Cloudflare risponde 520.
  Il fatto misurato (REFERTO.md par. 1.2) e' la coincidenza di secondo con le altre run rosse, non la
  causa esatta.

## 6. Tabella finale e proposta

| Parte del payload | MB | Letta da | Opzione consigliata |
|---|---|---|---|
| `h2h_hint` | 13,19 | file locale dei bot (una coppia per volta); NON dalla riga DB | non scrivere nel DB (a); se serve: (b) -> 5,6 |
| `by_team` | 6,14 | file locale (due squadre per partita); NON dalla riga DB | (a); se serve: array a 18 -> 2,80 |
| `by_league` | 2,54 | file locale; NON dalla riga DB | (a) |
| `v4` | 2,02 | file locale | (a) |
| `meta` | 0,12 | action: `watermark_event_id`, `generated_at`, conteggi (anche colonne della riga) | tenere |
| `global` | 0,005 | file locale | tenere |

**Proposta unica: opzione (a).** La riga `hazard_atlas` conserva `generated_at`, `n_leghe`,
`n_partite`, `watermark_event_id` e un payload minimo (`meta`+`global`, ~125 KB). Motivi: (1) nessun
lettore del setup attuale usa il payload; (2) nessun dato si perde, perche' la fonte
(`hazard_atlas_leghe`) resta e il globale si riassembla da essa; (3) toglie ~24-27 MB dalla POST che
va in 520 ogni giorno, la parte strutturalmente fragile; (4) nessun cambio di formato dei lettori,
quindi nessun rischio sulle strategie. Prima di applicarla: confermare con l'utente che il modo
`scarica` non serve (e' spento) e che nessun altro processo fuori repo legge `hazard_atlas.payload`
(non verificabile dal codice). Da affrontare a parte: `hazard_atlas_leghe` pesa ~37 MB (h2h 21 MB) ed
e' letta per intero (`stato`) ogni notte da `leggi_stato_db`; li' l'opzione (b) varrebbe 2-3x ma tocca
il formato dello stato e richiede ricertificazione.

Non verificato: dimensione su DB (TOAST/pglz) di `hazard_atlas` e `hazard_atlas_leghe`, numero di
versioni realmente presenti, dead tuples, limite di corpo documentato.
