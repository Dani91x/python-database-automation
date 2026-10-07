# Match Replay: la barra di avanzamento e' coerente con i simboli? (controllo aggiuntivo, 07/10/2026)

Ordine dell'utente (07/10): «assicurati che la barra di avanzamento della partita sia perfettamente
coerente con i simboli (lo avevi gia' controllato ieri, fai un controllo aggiuntivo se e' tutto ok)».
Delegato in worktree cloud, NON committato. Perimetro rispettato: `MatchReplay.tsx` NON toccato.

## 0. Esito in breve

- **Posizione dei simboli sulla barra: TUTTO COERENTE.** Su due partite vere, per ognuno dei 7+7
  simboli gol/cartellino e dei 6+15 angoli, la posizione mostrata e' quella attesa dalla regola
  (passo = primo istante con ts >= istante del dato), il simbolo compare scorrendo esattamente a quel
  passo e mai prima, il cursore sul simbolo sta sullo stesso punto, il minuto del cursore e' quello
  del simbolo. Estremi, linea del calcio d'inizio, segmenti di sospensione e ladder del Match Odds
  al cursore: tutti coerenti con i dati (tabelle sotto).
- **TROVATO UN DIFETTO REALE sul tabellone, non sulla posizione dei simboli: il punteggio mostrato
  torna a 0-0 dopo ogni riga-evento** (gol, giallo, fine primo tempo, fine partita). Per l'intera
  pausa (50+ passi di barra) e a fine replay («98' · FT» con «0 - 0» invece di 2-1, e 4-0 nell'altra
  partita). Il punteggio entra anche nel regolamento dei mercati a fine replay (`SettleCtx`).
  Stesso difetto nel motore opportunita' (`lib/opportunities/snapshot.ts`). Correzione pronta nella
  libreria di mia competenza; le due patch ai file fuori perimetro sono in §6 e **vanno applicate dal
  coordinatore**. I test che lo dimostrano sono ROSSI finche' non si applicano (e verdi con la patch:
  provato su copie, §7).
- Corretti nel mio perimetro (con test rossi prima, verdi dopo, falsificati) due difetti minori ai
  casi limite: simboli incollati a 0%/100% per fatti fuori registrazione; gol presente nel punteggio
  ma perso dalla timeline discreta = nessun simbolo.
- Nessuna decisione di trading toccata. Nessuna strategia, nessun bot.

## 1. Come costruisce la barra la pagina (letto sul codice, non sui referti)

Orologio: **orologio di parete UTC dei frame registrati** (`ts` ISO del frame = publish time Betfair
dello snapshot), mai il minuto di gioco.

1. `MatchReplay.tsx` `timeline` (riga ~238): un PASSO per ogni bucket da 10 s di orologio
   (`floor(ms/10000)`) in cui esiste almeno un frame di un mercato qualsiasi; il passo prende il
   ts e il minuto del primo frame del bucket nell'ordine di arrivo (il server li da' per finestra e
   per mercato, non per tempo: il ts del passo puo' essere fino a 10 s dopo il primo frame del bucket)
   e il primo minuto non nullo. Passi ordinati per ts. **La barra e' a INDICE, non a tempo**: il
   passo i sta a `i / (passi-1)`; dove non ci sono frame (silenzi dello stream, mercato sospeso fermo)
   i passi sono radi e la barra "salta".
2. Cursore (`TimelineSlider`): `(value-min)/(max-min)*100`. Estremi = primo e ultimo passo.
3. Simboli: `timelineEventMarkers` (`lib/replayTimelineEvents.ts`). Gol e cartellini dagli eventi
   discreti della timeline Betfair (righe `live_score_timeline` con `event_type`), con ri-posizionamento
   per minuto delle ri-emissioni; angoli sempre dai conteggi del punteggio; senza timeline discreta
   tutto dai delta. Posizione = `stepIndexFor(timeline, ts)` = primo passo con ts >= ts del fatto,
   diviso `timeline.length-1`. La pagina mostra un simbolo solo se `m.ts <= ts del cursore`.
4. Calcio d'inizio: primo frame con `inplay === true` (flag di mercato) -> primo passo con ts >=;
   lineetta a `kickoffIndex/maxIndex`; la pagina si apre su quel passo; sotto, «PRE».
5. Sospensioni: per ogni passo, stato dell'ultimo frame del Match Odds con ts <= passo
   (== SUSPENDED); segmento largo un passo che parte dalla posizione del cursore su quel passo.
6. Tabellone: ultima riga di `score_timeline` con ts <= cursore (qui il difetto, §5).

## 2. Cosa era gia' verificato ieri (06/10) e cosa NON rifaccio

Cronostoria riga 5015 e `lib/replayTimelineEvents.test.ts`: conteggi dei simboli (2+1 gol, 2+2 gialli,
5+1 angoli sulla 35797769), nessun doppione, fasi senza simbolo, punteggio da due fonti che torna
indietro, tipi `kindDiTipo`. Verificato solo sulla funzione pura e su UNA partita; mai la posizione sulla
barra, mai la pagina, mai il tabellone.

Aggiungo (tutto sulla pagina VERA con dati veri): posizione di ogni simbolo, comparsa scorrendo, cursore
sul simbolo, estremi, calcio d'inizio e PRE, sospensioni (geometria e pannello), ladder al cursore e dopo
il gol, punteggio al cursore, casi limite (registrazione che inizia a partita in corso / finisce prima /
buco dello stream / gol perso dalla timeline), geometria del componente isolato, e la seconda partita.

## 3. Dati e metodo (riproducibile)

Partite: `_live_raw/35797769` (Spagna-Belgio 2-1, 10/07, **2h30 di pre-match**, 7 buchi dello stream da
76 s a 545 s, recupero fino al 98') e `_live_raw/35760084` (Liepaja-Ogre 4-0, 30/06, 4 buchi, 15 angoli).

I file `*.raw.jsonl` sono lo STREAM grezzo (mcm), non i frame del database. Ho ricostruito i dati come li
riceve la pagina: libro per mercato dallo stream -> **curator VERO** (`Betfair/stream/curator.py::curate_event`,
cadenza 10 s, minuto dalla mappa del punteggio come `uploader.py`) -> campionamento del server
(`get_replay_frames`: 1 frame per mercato e per bucket, primo del bucket; bucket pre/in-play e finestre
come `fetchReplayChunked`) -> `ReplayData` con le righe `score_timeline` = righe `*.scores.jsonl` +
righe-evento `*.timeline.jsonl` (come `uploader.py`). Pagina `MatchReplay` VERA montata in jsdom con
`fetchReplayChunked` finto-vero, barra mossa con l'evento change dello slider, letto il DOM.

Fixture (sotto 150 KB ciascuna): tutti i frame del Match Odds + i soli frame degli altri mercati che
DEFINISCONO la griglia della barra (marcati «fantasma», mercato 9.0). **Provato equivalente al completo**:
esplorazione di TUTTI i passi (1122 e 861) col dato completo (6914 e 5502 frame) e col ridotto:
**0 differenze** su simboli, cursore, minuto, punteggio, sospensioni, linea del calcio d'inizio e pannello
Match Odds. Limiti della ricostruzione: i libri sono miei (non le righe del DB di produzione, che non ho),
nomi dei partecipanti/selezioni non presenti nello stream (si usano gli id).

## 4. Risultati per simbolo (partite vere, pagina vera)

«Posizione attesa» = primo passo con ts >= istante del dato, / (passi-1). «Mostrata» = `left` (stile disegnato) del simbolo
sulla barra a fine replay. «Punteggio mostrato oggi» = tabellone della pagina al passo del simbolo SENZA la
patch; «Punteggio vero» = ultima riga del punteggio Betfair con ts <= passo.


#### Partita 35797769: 1122 passi, da 16:31:46 a 21:09:04 UTC

| Simbolo | Minuto | Istante del dato (UTC) | Passo (ts) | Posizione attesa | Mostrata | Minuto al cursore | Punteggio mostrato oggi | Punteggio vero | Esito posizione |
|---|---|---|---|---|---|---|---|---|---|
| Gol home | 30' | 19:30:09.586 | 623 (19:30:11) | 55.575% | 55.575% | 30' | 0 - 0 | 1 - 0 | OK |
| Gol away | 41' | 19:40:56.665 | 680 (19:40:57) | 60.660% | 60.660% | 41' | 0 - 0 | 1 - 1 | OK |
| Giallo home | 43' | 19:43:27.196 | 694 (19:43:29) | 61.909% | 61.909% | 43' | 0 - 0 | 1 - 1 | OK |
| Giallo away | 85' | 20:47:03.159 | 1048 (20:47:08) | 93.488% | 93.488% | 85' | 0 - 0 | 1 - 1 | OK |
| Gol home | 88' | 20:49:44.187 | 1064 (20:49:54) | 94.915% | 94.915% | 88' | 0 - 0 | 2 - 1 | OK |
| Giallo home | 93' | 20:54:49.474 | 1091 (20:55:03) | 97.324% | 97.324% | 93' | 0 - 0 | 2 - 1 | OK |
| Giallo away | 95' | 20:56:39.648 | 1100 (20:56:44) | 98.127% | 98.127% | 95' | 0 - 0 | 2 - 1 | OK |
| Angolo home (n.1) | 34' | 19:35:21.245 | 651 (19:35:34) | 58.073% | 58.073% | 34' | 1 - 0 | 1 - 0 | OK |
| Angolo home (n.2) | 46' | 19:46:43.988 | 715 (19:46:58) | 63.782% | 63.782% | 46' | 1 - 1 | 1 - 1 | OK |
| Angolo home (n.3) | 46' | 19:47:03.729 | 717 (19:47:18) | 63.961% | 63.961% | 46' | 1 - 1 | 1 - 1 | OK |
| Angolo away (n.1) | 49' | 20:12:13.695 | 859 (20:12:18) | 76.628% | 76.628% | 49' | 1 - 1 | 1 - 1 | OK |
| Angolo home (n.4) | 51' | 20:14:15.492 | 871 (20:14:23) | 77.698% | 77.698% | 51' | 1 - 1 | 1 - 1 | OK |
| Angolo home (n.5) | 62' | 20:24:24.522 | 926 (20:24:39) | 82.605% | 82.605% | 62' | 1 - 1 | 1 - 1 | OK |

#### Partita 35760084: 861 passi, da 15:05:52 a 17:54:13 UTC

| Simbolo | Minuto | Istante del dato (UTC) | Passo (ts) | Posizione attesa | Mostrata | Minuto al cursore | Punteggio mostrato oggi | Punteggio vero | Esito posizione |
|---|---|---|---|---|---|---|---|---|---|
| Gol home | 8' | 16:08:13.500 | 298 (16:08:18) | 34.651% | 34.651% | 8' | 0 - 0 | 0 - 0 | OK |
| Gol home | 28' | 16:28:28.063 | 410 (16:29:21) | 47.674% | 47.674% | 28' | 2 - 0 | 2 - 0 | OK |
| Giallo away | 33' | 16:33:17.931 | 433 (16:33:20) | 50.349% | 50.349% | 33' | 0 - 0 | 2 - 0 | OK |
| Gol home | 46' | 16:46:34.487 | 507 (16:46:45) | 58.953% | 58.953% | 45' | 3 - 0 | 3 - 0 | OK |
| Gol home | 63' | 17:23:59.876 | 719 (17:25:17) | 83.605% | 83.605% | 63' | 4 - 0 | 4 - 0 | OK |
| Giallo away | 72' | 17:32:58.737 | 764 (17:33:04) | 88.837% | 88.837% | 72' | 0 - 0 | 4 - 0 | OK |
| Giallo home | 92' | 17:52:21.076 | 854 (17:52:28) | 99.302% | 99.302% | 92' | 0 - 0 | 4 - 0 | OK |
| Angolo away (n.1) | 2' | 16:03:13.040 | 268 (16:03:14) | 31.163% | 31.163% | 2' | 0 - 0 | 0 - 0 | OK |
| Angolo home (n.1) | 5' | 16:06:41.298 | 290 (16:06:56) | 33.721% | 33.721% | 5' | 0 - 0 | 0 - 0 | OK |
| Angolo home (n.2) | 14' | 16:15:03.481 | 334 (16:15:15) | 38.837% | 38.837% | 14' | 1 - 0 | 1 - 0 | OK |
| Angolo home (n.3) | 15' | 16:16:24.434 | 341 (16:16:32) | 39.651% | 39.651% | 15' | 1 - 0 | 1 - 0 | OK |
| Angolo away (n.2) | 23' | 16:24:04.330 | 385 (16:24:16) | 44.767% | 44.767% | 23' | 1 - 0 | 1 - 0 | OK |
| Angolo away (n.3) | 24' | 16:24:55.943 | 390 (16:25:04) | 45.349% | 45.349% | 24' | 1 - 0 | 1 - 0 | OK |
| Angolo away (n.4) | 27' | 16:27:54.394 | 407 (16:27:54) | 47.326% | 47.326% | 27' | 1 - 0 | 1 - 0 | OK |
| Angolo home (n.4) | 30' | 16:31:08.062 | 420 (16:31:12) | 48.837% | 48.837% | 30' | 2 - 0 | 2 - 0 | OK |
| Angolo away (n.5) | 48' | 17:09:12.308 | 634 (17:09:18) | 73.721% | 73.721% | 48' | 3 - 0 | 3 - 0 | OK |
| Angolo home (n.5) | 54' | 17:16:00.618 | 675 (17:16:01) | 78.488% | 78.488% | 54' | 3 - 0 | 3 - 0 | OK |
| Angolo away (n.6) | 56' | 17:17:45.908 | 685 (17:17:52) | 79.651% | 79.651% | 56' | 3 - 0 | 3 - 0 | OK |
| Angolo away (n.7) | 73' | 17:34:30.254 | 772 (17:34:32) | 89.767% | 89.767% | 73' | 4 - 0 | 4 - 0 | OK |
| Angolo home (n.6) | 75' | 17:36:18.668 | 782 (17:36:18) | 90.930% | 90.930% | 75' | 4 - 0 | 4 - 0 | OK |
| Angolo home (n.7) | 78' | 17:39:33.628 | 797 (17:39:36) | 92.674% | 92.674% | 78' | 4 - 0 | 4 - 0 | OK |
| Angolo home (n.8) | 82' | 17:43:53.077 | 820 (17:43:53) | 95.349% | 95.349% | 82' | 4 - 0 | 4 - 0 | OK |

Lettura:
- **Posizione: 7/7 + 7/7 gol e cartellini e 6/6 + 15/15 angoli OK**, nessun simbolo in piu' o in meno.
- Il minuto del cursore sul simbolo coincide col minuto del simbolo (46' del Liepaja = 45' al cursore: e' il
  45+1 del recupero; scarto fra i due feed al massimo 1 minuto).
- **Il punteggio mostrato e' sbagliato in tutti i casi in cui la riga-evento viene dopo l'ultima riga di
  punteggio** (colonna «mostrato oggi» a 0 - 0 con punteggio vero 1-0, 1-1, 2-1, 2-0, 4-0): e' il difetto D1.
- Scarto fra i due feed, NON difetto di codice: il Goal della timeline e la riga del punteggio non sono
  simultanei. Sulla 35797769 il punteggio sale gia' al passo del simbolo (scarto <= 1,2 s); sulla 35760084 la
  riga del punteggio segue il Goal di 10,8 s (8') e 8,9 s (46'): il simbolo ⚽ compare 1 passo PRIMA che il
  tabellone passi a 1-0 / 3-0 (a 8' il cursore mostra 0 - 0 sul simbolo e 1 - 0 al passo dopo). Resta cosi' con
  la correzione D1: dipende dai due feed (il mercato si sospende ancora prima: 10-14 s prima del Goal della timeline).

### 4.1 Estremi, kickoff, intervallo, fine, sospensioni, ladder

| Controllo | 35797769 (pre-match lungo) | 35760084 | Esito |
|---|---|---|---|
| Passo 0 = primo frame; ultimo passo | 16:31:46 = primo frame; 21:09:04 = ultimo frame | 15:05:52 = primo frame; 17:54:13 (ultimo frame 17:54:19: < 1 bucket) | OK |
| Cursore a 0% e 100% | 0 e 100 | 0 e 100 | OK |
| Calcio d'inizio (lineetta) | primo frame in-gioco 19:00:34.6 -> passo 453 = 40,410% (mostrata 40,410%) | 16:00:25.3 -> passo 251 = 29,186% | OK |
| La pagina si apre sul kickoff; «PRE» solo prima | si', PRE ai passi 0-452 | si', PRE ai passi 0-250 | OK |
| KickOff della timeline Betfair vs lineetta | evento 19:01:02 (passo 454): la lineetta e' 28 s PRIMA (flag in-gioco del mercato, per scelta documentata) | evento 16:00:46: 21 s dopo la lineetta | coerente con la regola |
| Intervallo (FirstHalfEnd -> SecondHalfKickOff) | passi 736 -> 833 (65,66% -> 74,31%), 97 passi, nessun simbolo (fasi non disegnate), tabellone vero solo con la patch | passi 512 -> 617 | OK/vedi D1 |
| Fine partita (SecondHalfEnd) | 20:59:23 -> passo 1110 (99,02%); «FT» solo all'ultimo passo (21:09:04, 10 min dopo) | 17:53:15 -> passo 859 | OK |
| Sospensioni del Match Odds (insieme dei passi segnati = passi con ultimo frame SUSPENDED) | 4 passi segnati (21:00:18-21:01:10); le 3 sospensioni da gol (3-6 s) cadono fra due passi e NON si vedono; badge «Sospeso» del pannello = segmenti su tutti i passi campionati | 5 passi segnati (17:47:28-17:47:49, 17:53:02-17:54:13) | OK (0 discordanze con lo stato dello stream) |
| Ladder Match Odds al cursore | = ultimo frame <= passo, 0 discordanze (prezzo e lay di ogni selezione) su tutti i passi campionati | idem | OK |
| Ladder prima/dopo il gol | 30': ripreziato gia' al passo del simbolo (1,71 -> 1,27); 41': ancora PRE-gol al passo del simbolo (1,22), ripreziato al passo dopo (1,72); 88': ripreziato 1 passo PRIMA del simbolo | casa che segna: back casa scende / ospite: sale, verificato su tutti i gol non gia' a 1,01 | OK (vedi O3) |

## 5. Difetti trovati

### D1 (REALE, sul tabellone, NON risolto qui: file di un altro delegato) — punteggio a 0-0 dopo ogni riga-evento
Causa radice: `frontend/src/pages/MatchReplay.tsx` (blocco «punteggio + minuto all'istante corrente», ~496-508):
`currentScoreEntry` = ultima riga di `score_timeline` con `ts <= cursore` di QUALUNQUE tipo, poi
`currentScore = { home: entry.score_home ?? 0, away: entry.score_away ?? 0 }`. Le righe-evento della timeline
(`uploader.py::_read_timeline_events`, righe 55-82: `"score_home": None, "score_away": None`) non portano il
punteggio: ogni Goal, YellowCard, FirstHalfEnd, SecondHalfEnd azzera il tabellone fino alla riga del punteggio
successiva — per tutta la pausa — e a fine replay.
Prova (pagina vera, dati veri, `replayBarraPunteggio.test.tsx` senza patch): 35797769, 143 passi su 669 (dal fischio) con
punteggio sbagliato (es. passo 623 19:30:11 «0 - 0», vero 1-0; tutto l'intervallo 19:50:48-20:07 «0 - 0», vero
1-1; fine «98' · FT» «0 - 0», vero 2-1); 35760084, 115 passi su 610 (intervallo «0 - 0» vero 3-0; fine «0 - 0», vero
4-0). `ctx: SettleCtx = { home: currentScore.home, away: currentScore.away, finished }` (riga ~666): a fine
replay il regolamento dei mercati usa il punteggio sbagliato (da verificare dal vivo, §9).
Perche' non era visto: i test esistenti di `opportunities/snapshot.test.ts` usano righe-evento CON punteggio
(`event_type: 'GOAL', score_home: 1`) che nel vero non esistono (finto con chiavi diverse dal vero).
Correzione: funzione pura `punteggioAlTs(righeOrdinate, ts)` in `lib/replayTimelineEvents.ts` (punteggio =
ultima riga CHE LO PORTA, minuto = ultima riga di qualunque tipo, come prima).
**PATCH da applicare a `frontend/src/pages/MatchReplay.tsx`** (verificata su una copia: 8/8 test verdi, §7):

```diff
-import { timelineEventMarkers } from '@/lib/replayTimelineEvents';
+import { punteggioAlTs, timelineEventMarkers } from '@/lib/replayTimelineEvents';
@@ ~496
-    const currentScoreEntry = useMemo(() => {
-        if (!currentTs) return null;
-        let best: typeof sortedScoreTimeline[number] | null = null;
-        for (const ev of sortedScoreTimeline) {
-            if (ev.ts <= currentTs) best = ev; else break;
-        }
-        return best;
-    }, [sortedScoreTimeline, currentTs]);
-
-    const currentScore = currentScoreEntry
-        ? { home: currentScoreEntry.score_home ?? 0, away: currentScoreEntry.score_away ?? 0 }
-        : { home: 0, away: 0 };
-    const displayMinute = currentScoreEntry?.minute ?? currentMinute;
+    const currentScoreEntry = useMemo(
+        () => punteggioAlTs(sortedScoreTimeline, currentTs),
+        [sortedScoreTimeline, currentTs],
+    );
+    const currentScore = { home: currentScoreEntry.home, away: currentScoreEntry.away };
+    const displayMinute = currentScoreEntry.minute ?? currentMinute;
```
(con `currentTs` vuoto `punteggioAlTs` restituisce 0-0 e minuto null: stesso comportamento di prima.)

### D2 (REALE, stesso difetto nel motore opportunita', file fuori perimetro)
`frontend/src/lib/opportunities/snapshot.ts` (~139-146): `scoreHome = sc.score_home ?? 0` sull'ultima riga di
qualunque tipo: dopo una riga-evento il motore opportunita' vede 0-0 (196/133 bucket sbagliati sulle due
partite, `replayTimelineEvents.barra.test.ts`, ROSSO finche' non patchato). Effetto: i rilevatori che
dipendono dal punteggio lavorano su un punteggio sbagliato nel replay. **PATCH** (verificata su una copia:
test dei due file 19/19 e `snapshot.test.ts` esistente 7/7 verdi):

```diff
         const sIdx = bisectLast(scoresSorted, bucketEnd, (s) => tsMs(s.ts));
         if (sIdx >= 0) {
-            const sc = scoresSorted[sIdx];
-            scoreHome = sc.score_home ?? 0;
-            scoreAway = sc.score_away ?? 0;
-            scoreMinute = sc.minute;
+            scoreMinute = scoresSorted[sIdx].minute;
+            // il punteggio e' quello dell'ultima riga CHE LO PORTA: le righe-evento
+            // della timeline (Goal, FirstHalfEnd, SecondHalfEnd, ...) hanno score null
+            for (let k = sIdx; k >= 0; k--) {
+                const r = scoresSorted[k];
+                if (r.score_home != null && r.score_away != null) { scoreHome = r.score_home; scoreAway = r.score_away; break; }
+            }
         }
```

### D3 (corretto) — fatto fuori registrazione incollato a 0% o 100%
`timelineEventMarkers` posizionava un fatto con ts coerente ma prima del primo frame al passo 0 e uno dopo
l'ultimo all'ultimo passo (la pagina filtra `m.ts <= cursore`, quindi i primi comparivano sempre a 0%).
Il punto (c) del commento di 06/10 («prima della registrazione -> nessun marker») valeva solo per le
ri-emissioni. Ora nessun simbolo prima del primo passo o oltre un bucket (10 s) dopo l'ultimo; dentro l'ultimo
bucket il ts si porta all'ultimo passo (visibile). Test: `replayTimelineEvents.barra.test.ts`
(INIZIA a partita in corso / FINISCE prima), su entrambe le partite.

### D4 (corretto) — gol nel punteggio ma assente dalla timeline discreta
Con la timeline discreta presente i gol si leggevano SOLO da essa: se un poll perde un Goal il tabellone
sale ma sulla barra non c'e' nessun simbolo. Ora un gol del punteggio senza un Goal discreto della stessa
squadra entro 3 minuti (scarti visti sui dati: <= 11 s) si disegna dal punteggio, una sola volta (i Goal
discreti gia' presenti vengono «presi» uno a uno: nessun doppione, provato). Test: Goal del Belgio al 41'
tolto dalla partita vera -> il simbolo c'e' ed e' al passo della riga 1-1.

## 6. Osservazioni, NON difetti (da sapere / eventuale decisione)

- **O1 La barra e' a indice, non a tempo.** Passo mediano 11 s, ma il piu' largo e' 545 s (35797769, 17:12:26,
  pre-match) e 131-350 s ai buchi dello stream; nel finale di 35797769 il passo del fischio finale (99,02%) e'
  largo 55 s. I simboli stanno al primo passo >= istante: sempre coerenti, ma la distanza in pixel fra due
  simboli non e' proporzionale al tempo.
- **O2 Le sospensioni brevi non si vedono.** I Match Odds si sospendono 3-6 s sui gol (35797769): cadono fra due
  passi (>= 10 s) e non disegnano nessun segmento; le sospensioni lunghe si vedono ma iniziano al primo passo
  CON frame (21:00:18 per una sospensione cominciata alle 20:59:14: nessun frame dello stream in mezzo).
- **O3 Il ladder al simbolo dipende dal campionamento del server** (`get_replay_frames`: primo frame di ogni
  19 s per mercato). Cosi' al gol 41' il ladder al passo del simbolo e' ancora quello PRE-gol e si ripreziona al
  passo dopo; all'88' si e' gia' ripreziato 1 passo prima. Il codice mostra sempre l'ultimo frame <= passo: e'
  la risoluzione del dato. Sullo stesso meccanismo (primo frame del bucket) l'ultimo passo di 35760084 mostra
  «Sospeso» invece di «Chiuso» (il frame CLOSED cade nello stesso bucket del SUSPENDED precedente).
- **O4 Minuto «a singhiozzo»** (35797769, passi 458-459: 2' poi 1'): i due provider danno minuti diversi
  (api_football 2', Betfair 1') e il cursore prende l'ultima riga di qualunque fonte. Cosmetico.
- **O5 Intervallo, fine tempo, inizio ripresa e fine partita non hanno un simbolo sulla barra** (solo la
  lineetta del calcio d'inizio). Non e' un'incoerenza (i tipi `FirstHalfEnd` ecc. sono dichiarati «fasi»), ma
  se l'utente li vuole sono gia' nei dati: posizione passi 736/833/1110 e 512/617/859. Non aggiunti.
- **O6** Gli ultimi < 10 s di registrazione stanno dopo l'ultimo passo: nessun passo li mostra.

## 7. Cosa ho cambiato

File MODIFICATI (2):
- `frontend/src/lib/replayTimelineEvents.ts`: `punteggioAlTs` (nuovo, D1); guardia fuori registrazione (D3);
  gol dal punteggio non presenti nella timeline (D4); intestazione aggiornata.
- `frontend/src/components/replay/TimelineSlider.tsx`: SOLO attributi `data-testid` / `data-kind` /
  `data-team` / `data-indice` su simboli, cursore, lineetta e segmenti
  (nessun cambio di aspetto o di calcolo; leggono i test).

File NUOVI (8):
- `frontend/src/lib/replayBarraSimboli.test.tsx` (pagina vera, simboli/estremi/kickoff/sospensioni/ladder, 2 partite)
- `frontend/src/lib/replayBarraPunteggio.test.tsx` (pagina vera, punteggio al cursore: ROSSO fino alla patch D1)
- `frontend/src/lib/replayTimelineEvents.barra.test.ts` (funzioni pure: `punteggioAlTs`, casi limite D3/D4,
  `buildSnapshots` D2: i 2 test D2 ROSSI fino alla patch)
- `frontend/src/components/replay/TimelineSlider.test.tsx` (geometria del componente)
- `frontend/src/lib/__fixtures__/replayBarra.ts` (fixture + oracoli), `.../replayBarraPagina.tsx` (pilota della pagina),
  `.../replay_barra_35797769.json` (145 KB), `.../replay_barra_35760084.json` (110 KB)

## 8. Test e falsificazioni

Comandi (dalla cartella `frontend/` del worktree), eseguiti da me:

- `npx tsc -p tsconfig.app.json --noEmit` -> **0 errori** (nessun `any`, nessun `@ts-ignore`).
- `npx vitest run src/lib/replayBarraSimboli.test.tsx src/lib/replayBarraPunteggio.test.tsx src/lib/replayTimelineEvents.barra.test.ts src/lib/replayTimelineEvents.test.ts src/components/replay src/lib/trainingLadder.replay.test.tsx src/lib/opportunities`
  -> 20 file, **249 test: 240 verdi, 9 ROSSI ATTESI** (60 s). I 9 rossi sono TUTTI e SOLI i test dei difetti
  D1/D2 che richiedono le patch ai file fuori perimetro: 7 in `replayBarraPunteggio.test.tsx` (il test «ogni gol»
  della 35760084 passa anche senza patch) e 2 in `replayTimelineEvents.barra.test.ts` (`buildSnapshots`).
- Con le due patch applicate su COPIE (`pages/_MatchReplayPatchProva.tsx`, `lib/opportunities/_snapshotProva.ts`,
  poi cancellate): `replayBarraPunteggio` 8/8 verdi (tutti i passi dal fischio, FT 2-1 e 4-0, intervallo 1-1 e 3-0),
  `replayTimelineEvents.barra` 19/19 verdi, `snapshot.test.ts` esistente 7/7 verdi.
- Nuovi verdi: `replayBarraSimboli` 12/12 (~9 s), `replayTimelineEvents.barra` 17/19 (i 2 D2 rossi),
  `TimelineSlider.test` 10/10. Esistenti `replayTimelineEvents.test` 5/5, `trainingLadder.replay` e tutti i test
  di `components/replay` e `lib/opportunities` verdi (nessuna regressione dai soli attributi `data-*`).
- Fixture: provata l'equivalenza completo/ridotto passo per passo (§3), 0 differenze.

Falsificazione (mutazione nel codice -> numero di test rossi; base = 2 rossi D2 sullo stesso gruppo di 4 file;
ogni mutazione ripristinata dalla copia salvata e verificata con `cmp` e `grep -c MUTAZIONE` = 0; script
`falsifica.py`/`falsifica2.py` fuori dal repo, nel mio scratchpad):

| Mutazione | Rossi (base 2) | Dove diventa rosso |
|---|---|---|
| MU1 `stepIndexFor` +1 (simboli un passo dopo) | 7 | pagina (posizione) + pure |
| MU2 tolta la guardia «prima del primo frame» | 4 | pure (INIZIA a partita in corso, 2 partite) |
| MU3 tolta la guardia «dopo l'ultimo frame» | 4 | pure (FINISCE prima, 2 partite) |
| MU4 gol dal punteggio mai «preso» dal Goal discreto (doppio simbolo) | 13 | pagina + pure + test del 06/10 |
| MU5 gol dal punteggio mai disegnato | 3 | pure (gol perso dalla timeline) |
| MU6 `punteggioAlTs` come il vecchio codice (riga qualunque, `?? 0`) | 7 | pure |
| MU7 angoli non derivati | 5 | pagina + pure + test del 06/10 |
| MU8 il giallo non e' piu' un simbolo | 13 | pagina + pure + test del 06/10 |
| MU9 cursore su `span+1` | 11 | componente + pagina (estremo 100%) + pure |
| MU10 simboli a x0,98 (solo lo stile) | 6 | componente + pagina |
| MU11 segmento di sospensione sul passo dopo (solo lo stile) | 5 | componente + pagina |
| MU12 lineetta del calcio d'inizio a x0,5 | 5 | componente + pagina |
| MU13 simboli senza clamp 0..100 | 3 | componente |
| MU14 segmento senza clamp (esce dalla barra) | 4 | componente + pagina |

Prima versione dei test (leggevano `data-left` invece dello stile disegnato): MU11 e MU14 NON diventavano rossi;
ho tolto i `data-left`/`data-width` dal componente e fatto leggere ai test lo STILE reale (`style.left/width`),
poi rifatte le 6 mutazioni del componente (MU9-MU14, tabella sopra). MU1-MU8 sono state fatte sulla prima
versione dei test; il codice di `replayTimelineEvents.ts` non e' cambiato dopo. I test D1/D2 sono la
falsificazione di se' stessi (rossi sul codice vero, verdi con la patch).

## 9. Cosa NON ho fatto / NON ho potuto verificare

- NON toccato `MatchReplay.tsx` ne' `lib/opportunities/snapshot.ts` (fuori perimetro): D1 e D2 non sono
  chiusi finche' il coordinatore non applica le due patch; i tre test rossi lo dicono.
- NON verificato dal vivo: l'effetto di D1 sul regolamento dei mercati a fine replay (letto dal codice,
  `ctx` -> `settleOrCashOut`; non ho eseguito la simulazione di una scommessa a fine replay).
- NON usato il database ne' le registrazioni «curate» di produzione (non le ho): i frame sono ricostruiti dallo
  stream grezzo con il curator vero e il campionamento del server replicato in Python (lo scarto fra il mio
  replicato e il server vero non e' verificabile qui); nomi di squadre/selezioni assenti dallo stream.
- NON verificati: i rombi verdi degli arbitraggi sulla barra (usano lo stesso `stepIndexFor` ma dipendono dal
  motore opportunita', che D2 sbaglia); la barra con la pagina in un browser/app reale (solo jsdom: nessun
  controllo di pixel, scorrimento col mouse, riproduzione automatica); partite con tempi supplementari o rigori
  (non nelle due registrazioni).
- Numeri di tempo del referto: cronometri del sandbox cloud.

## 10. Decisioni per l'utente

Nessuna che tocchi una strategia. Due scelte di visualizzazione, solo se le vuoi: (a) un simbolo per
intervallo/fine/ripresa sulla barra (O5); (b) far apparire il simbolo ⚽ nello stesso passo in cui cambia il
tabellone (oggi il simbolo segue il Goal della timeline, il tabellone la riga del punteggio: fino a 11 s di
scarto su 35760084). Proposta: lasciare com'e' (a meno che non desideri (a)).

## 11. Da controllare dal vivo al prossimo avvio dell'app (dopo l'applicazione delle patch)

Aprire Match Replay su 35797769 (Spagna-Belgio): al passo del gol 30' il tabellone deve dire «1 - 0», durante
l'intervallo «1 - 1» (non «0 - 0»), all'ultimo passo «2 - 1 · FT». Dove leggerlo: riquadro in alto della pagina.
