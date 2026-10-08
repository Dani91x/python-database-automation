# CANTIERE 13 - Strumento della barra: le 13 partite incoerenti, e il rosso della fixture

Delegato di costruzione, sessione cloud, 08/10/2026. Worktree
`/home/user/python-database-automation/.claude/worktrees/agent-ad97311e16b40a5ca`, NIENTE commit.
Partenza: `4b262c4` (cantiere 12 integrato), poi `git merge --ff-only` sulla cima `3b8ce19` (C14, C15) come
chiesto dall'aggiornamento del coordinatore: i file di questo cantiere non sono toccati da quei commit
(`git diff --name-only 4b262c4 3b8ce19` non contiene barra, curator, fixture). `b5547eb` e' nella storia.

Ambiente: container Linux, 4 CPU condivise, load average 12-21 durante il lavoro (tempi gonfiati).
Python 3.13.16, betfairlightweight 2.23.2 con orjson 3.11.7 e ciso8601 2.3.3 (= `[speed]` del PC),
flumine 2.13.11. NON ci sono il database ne' le registrazioni delle 13 partite: cio' che le richiede e'
preparato (comandi, numeri attesi, tabella da riempire) e dichiarato DA RIESEGUIRE SUL PC.

---------------------------------------------------------------------------------------------------

## 1. Il rosso di `test_fixture_riproducibile_dal_raw` (35760084 e 35797769): CAUSA PROVATA

**Causa.** La fixture e' VECCHIA rispetto al curator di produzione. Le due fixture sono state generate
in `267605c` (07/10 09:17 UTC); alle 10:55 UTC dello stesso giorno `9e86c3a` ha aggiunto al curator
(`Betfair/stream/curator.py::curate_records`) la regola (d) decisa dall'utente («un cambio di status o di
inplay rispetto all'ultima riga conservata entra SEMPRE»). Il generatore usa il curator vero, quindi da
allora rigenerare dal raw da' righe in piu'; le fixture non sono mai state rigenerate. Il test sta in
`tools/`, fuori da `pytest Betfair/`: nessuna suite lo lanciava.

**Prove (comandi e file in questa cartella).**
1. Rigenerazione dal raw con il codice di oggi, due volte: byte identici fra loro
   (sha 35760084 `ad3aa718...`, 35797769 `300c8ec9...`): il generatore e' DETERMINISTICO.
2. Rigenerazione con il SOLO curator sostituito da quello di `9e86c3a^` (`rigenera_curator_vecchio.py`):
   `35760084 IDENTICA 110075 110075`, `35797769 IDENTICA 145206 145206` = byte per byte la fixture del
   repository. Quindi NON c'entrano: ambiente, versioni di librerie (betfairlightweight, orjson, ciso8601),
   arrotondamenti, fine riga, ne' `b5547eb` (tocca solo banco, varianti e due replay: `git show b5547eb --stat`).
3. Righe curate prima/dopo (`spiega_righe.py` -> `fixture_righe_curate_prima_dopo.txt`): 35760084 34441 ->
   34674 (0 tolte, 233 aggiunte: 125 OPEN->SUSPENDED, 91 SUSPENDED->OPEN, 17 SUSPENDED->CLOSED); 35797769
   91650 -> 91687 (0 tolte, 37 aggiunte: 19 OPEN->SUSPENDED, 17 SUSPENDED->CLOSED, 1 OPEN pre -> OPEN in
   gioco). Tutte righe di SOLO cambio di stato (la regola (d)); nessuna riga di prima esce.
4. Frame che la pagina riceve (campionamento di `get_replay_frames`): 5502 -> 5519 e 6914 -> 6918.

**Correzione: fixture rigenerate** (`python3 tools/replay_barra_fixture.py 35760084 35797769`), perche'
e' la fixture a essere sbagliata (vecchia), non il curator ne' il generatore. Diff spiegato riga per riga
(`fixture_diff_35760084.txt`, `fixture_diff_35797769.txt`; `meta.sorgente` invariato):

| partita | riga della fixture | prima -> dopo | spiegazione (riga curata aggiunta dalla regola d) |
|---|---|---|---|
| 35760084 | Match Odds 16:04:34.412 (3') | -> 16:04:33.686, back 86159298 9.4 | riapertura SUSPENDED->OPEN del Match Odds alle 16:04:33.686: e' ora la prima riga del suo bucket del server (16 s) |
| 35760084 | fantasma in piu' 16:28:17.071 (27') | aggiunta | FIRST_HALF_GOALS_25 SUSPENDED->OPEN: primo frame di un bucket da 10 s della barra |
| 35760084 | fantasma 17:47:28.685 (85') | -> 17:47:28.187 | BOTH_TEAMS_TO_SCORE OPEN->SUSPENDED alle 17:47:28.187, prima nel bucket |
| 35797769 | fantasma in piu' 21:01:45.036 (97') | aggiunta | OVER_UNDER_35 SUSPENDED->CLOSED |
| 35797769 | `meta.ts_max` 21:09:11.034 | -> 21:09:14.501 | FIRST_GOAL_SCORER SUSPENDED->CLOSED: ultima riga della registrazione |

Frame della fixture: 1107 -> 1108 e 1360 -> 1361; `meta` 35760084 invariato. Dopo: `tools/test_replay_barra_fixture.py`
15 passed (prima della mia aggiunta di 2 test; ora 17, vedi par. 6). Il partite test vitest resta verde sulle
fixture nuove (0 incoerenze, D1-D4 ancora rossi).

**Sul PC.** Il referto del cantiere 12 scrive «verde sul PC»: NON e' verificato e per la prova 2 non puo'
esserlo (stesso codice, stesso curator): sul PC il test era rosso anche lui. Comando:
`python -m pytest tools/test_replay_barra_fixture.py -q -p no:cacheprovider` -> atteso 17 passed.

---------------------------------------------------------------------------------------------------

## 2. Le 13 partite incoerenti: criteri di classificazione (scritti e provati)

Fonte: `AUDIT_2026-10-07/certificazione_db/verifica_barra_tutte.txt` (PC, 38 partite, 25 OK, 13 INCOERENTI).

### 2.1 SIMBOLO_GOL_SENZA_AUMENTO dopo un VAR (classe a, verificatore) - CORRETTO

Quattro delle cinque partite con ERRORE hanno lo stesso schema nel referto del PC: una
`TABELLONE_CORREZIONE_FEED` della STESSA squadra PRIMA del simbolo segnalato:
35787218 (0-2 -> 0-1 alle 17:24:25, poi «Gol Egypt» 67' alle 17:30:58), 35777617 (0-1 -> 0-0 alle 20:03:49,
poi «Gol Norway» 80'), 35768297 (1-1 -> 0-1 alle 00:21:24, poi «Gol Portugal» 68' alle 00:27:27),
35768365 (1-0 -> 0-0 alle 19:30:01, poi «Gol Spain» 36' alle 19:36:24).
Il verificatore (`replayVerificaBarraCalcio.ts`, passo 4) contava i gol attesi contro il MASSIMO visto
(regola nata per non contare due volte il ritardo di una seconda fonte): dopo un gol annullato il gol
VERO riporta il punteggio a un valore gia' visto e non era «atteso», quindi il suo simbolo (giusto: la
pagina lo disegna dal Goal della timeline) restava «senza aumento». Falso positivo del verificatore.
Riprodotto in `replayVerificaBarra.classi.test.ts` (A1): sintetico come 35787218, sintetico come 35768297
(due correzioni), e sulla partita VERA 35760084 con un gol annullato inserito 8 minuti prima di un gol
vero (righe con le chiavi della fixture). Prima della correzione: ROSSI con il testo identico a quello
del PC («C'e' un simbolo di gol ("Gol Ospiti", 33' ...) ma il punteggio non aumenta ...»).

**Correzione** (`frontend/src/lib/replayVerificaBarraCalcio.ts` righe 234-265 e 306-317): gli aumenti
VERI non attesi (la risalita dopo una correzione della STESSA fonte; un aumento fuori dalla barra) si
raccolgono a parte e servono SOLO a giustificare un simbolo rimasto senza abbinamento, della stessa
squadra, entro 3 minuti, uno a uno. Non diventano gol pretesi: nessun GOL_SENZA_SIMBOLO nuovo possibile.
La nota GOL_ANNULLATO resta com'era (si controlla prima). Restano rossi (provato): due Goal per una
risalita, la risalita di una squadra per il Goal dell'altra, la risalita dopo una discesa fra DUE fonti
(che resta anche TABELLONE_SCENDE), un Goal senza nessun aumento.

### 2.2 SIMBOLO_GOL_SENZA_AUMENTO a registrazione appena iniziata (35812264, classe a IPOTIZZATA)

35812264 inizia al 56' (INIZIO_IN_CORSO) e il simbolo e' al passo 2 (12:36:22, «55'»). Schema compatibile:
il punteggio sale PRIMA del primo frame (fuori dalla barra, non atteso) e il Goal della timeline arriva
dentro la barra. Stessa correzione (aumento fuori barra entro 3 minuti dal simbolo). Riprodotto (A2) e
provato il limite (oltre 3 minuti resta errore). **Non provato sui dati veri**: lo dice `--dettaglio` sul PC.

### 2.3 KICKOFF_DISCORDANTE (classe c, dati) - DICHIARATO PER DATI

Il controllo confronta DUE DATI registrati: il flag in gioco del mercato (che la pagina usa per la
lineetta) e il KickOff della timeline del feed. La lineetta della pagina e' gia' controllata a parte
(KICKOFF_FUORI_POSTO, errore). Quindi una discordanza e' SEMPRE dei dati. Nuovo campo `perDati` (motivo
per il trader) sul rilievo, impostato in `replayVerificaBarra.ts` (riga 452, funzione
`motivoKickoffDiscordante` righe 539-563) con tre motivi:
- **buco**: nessun frame fra l'inizio dichiarato e il primo frame in gioco (35817305, 35817978, 35817332,
  35828026: buco 14:58 -> 15:06:49 su TUTTE e quattro, cioe' un fermo della registrazione);
- **flag discorde**: frame registrati con il mercato NON in gioco dopo l'inizio dichiarato (35794996: frame
  17:50:35-17:54:28 al 50' con il mercato non in gioco; 35796477: frame 17:02:58-17:09:24 al 6');
- il mercato in gioco PRIMA del KickOff del feed.
L'incoerenza RESTA (gravita' avviso, partita non OK, uscita 1): non e' mai silenziosa.

### 2.4 CARTELLINI_DIVERSI con la timeline discreta (classe c SOLO se la pagina e' fedele)

Con la timeline discreta i cartellini della barra vengono dalla timeline, i conteggi da un'altra fonte.
Criterio (`replayVerificaBarraCalcio.ts` righe 362-379): se la barra disegna ESATTAMENTE i cartellini
della timeline (righe-evento dentro la registrazione, uno per minuto) la pagina e' fedele e la differenza
e' fra le due fonti del feed -> `perDati`. Se la barra ne perde o ne aggiunge rispetto alla timeline NON e'
per dati (resta da guardare: possibile classe b). Provato: giallo in piu' nella timeline (per dati), pagina
che perde un giallo (non per dati), pagina che ne aggiunge uno (non per dati), cartellino ri-emesso dal
feed nello stesso minuto 15 minuti dopo (la pagina lo scarta, nessuna incoerenza).

### 2.5 Codici che sono NOTE (non incoerenze) nel referto del PC

BUCO_REGISTRAZIONE 67, TABELLONE_CORREZIONE_FEED 9, INIZIO_IN_CORSO 9, SOSPENSIONE_NON_VISIBILE 4,
CONTEGGI_ASSENTI 3, GOL_ANNULLATO 2, PUNTEGGIO_ASSENTE 1: sono gia' dichiarati (gravita' nota) e non
rendono incoerente una partita. Non toccati.

---------------------------------------------------------------------------------------------------

## 3. Tabella delle 13 partite (DA RIEMPIRE SUL PC con l'esito vero)

Classe e esito «atteso» sono quelli che i criteri provati qui danno SE i dati sono come li descrive il
referto del PC; la colonna «esito vero» la scrive il coordinatore dopo il comando del par. 4.

| partita | codice (PC 07/10) | classe | correzione | esito atteso | esito vero |
|---|---|---|---|---|---|
| 35812264 Beijing - Liaoning | SIMBOLO_GOL_SENZA_AUMENTO | a (ipotesi 2.2) | verificatore | sparisce se l'aumento e' entro 3 min prima dell'inizio | |
| 35812264 | CARTELLINI_DIVERSI (gialli Liaoning 2 vs 3) | c se la barra = timeline | dichiarato | per dati | |
| 35817305 Elimai - Alashkert | KICKOFF_DISCORDANTE | c (buco) | dichiarato | per dati | |
| 35817978 Astana - Dinamo Tirana | KICKOFF_DISCORDANTE | c (buco) | dichiarato | per dati | |
| 35817332 Inter - Sarajevo | KICKOFF_DISCORDANTE | c (buco) | dichiarato | per dati | |
| 35828026 Gorica - Epicentr | KICKOFF_DISCORDANTE | c (buco) | dichiarato | per dati | |
| 35823368 Copenhagen - Viborg | CARTELLINI_DIVERSI (gialli 2 vs 1) | c se la timeline ne ha 1; b se ne ha 2 | dichiarato / pagina | per dati, oppure da correggere | |
| 35804974 Legia - Trencin | CARTELLINI_DIVERSI (gialli 2 vs 1) | come sopra | come sopra | come sopra | |
| 35794996 Vardar - KuPS | KICKOFF_DISCORDANTE | c (flag discorde) | dichiarato | per dati | |
| 35796477 Shelbourne - Celtic | KICKOFF_DISCORDANTE | c (flag discorde) | dichiarato | per dati | |
| 35787218 Argentina - Egypt | SIMBOLO_GOL_SENZA_AUMENTO | a (VAR, 2.1) | verificatore | sparisce | |
| 35787218 | CARTELLINI_DIVERSI x2 (0 vs 1, 3 vs 4) | c se la barra = timeline | dichiarato | per dati | |
| 35777617 Brazil - Norway | SIMBOLO_GOL_SENZA_AUMENTO | a (VAR) | verificatore | OK | |
| 35768297 Portugal - Croatia | SIMBOLO_GOL_SENZA_AUMENTO | a (VAR) | verificatore | OK (le note restano) | |
| 35768365 Spain - Austria | SIMBOLO_GOL_SENZA_AUMENTO | a (VAR) | verificatore | OK | |

**Atteso sul PC, se i criteri reggono sui dati veri:** `RIEPILOGO: 38 partite verificate: 28 OK, 10 con
incoerenze` e `di cui 10 SOLO PER DATI (dichiarate con il motivo, classe c) e 0 da correggere.`; le 25
coerenti restano OK (la correzione toglie solo SIMBOLO_GOL_SENZA_AUMENTO e aggiunge solo `perDati` a
rilievi gia' presenti: nessun rilievo nuovo puo' nascere). Ogni scarto da questo atteso = una partita da
guardare con `--dettaglio` (par. 4) e da classificare con i criteri del par. 2; se una CARTELLINI_DIVERSI
non e' per dati, la pagina perde o aggiunge un cartellino della timeline (classe b): reperto, non correggere
alla cieca.

---------------------------------------------------------------------------------------------------

## 4. Comandi per il PC (sola lettura)

Da `frontend/`, in cmd (credenziali come nel cantiere E, solo da ambiente):

```
npx vite-node scripts/verifica_barra_replay.ts --env-file ../.env --senza-note > verifica_barra_tutte_dopo.txt
npx vite-node scripts/verifica_barra_replay.ts --env-file ../.env --solo-incoerenti --dettaglio ^
    --evento 35812264 --evento 35817305 --evento 35817978 --evento 35817332 --evento 35828026 ^
    --evento 35823368 --evento 35804974 --evento 35794996 --evento 35796477 --evento 35787218 ^
    --evento 35777617 --evento 35768297 --evento 35768365 > verifica_barra_13_dettaglio.txt
```

`--dettaglio` (nuovo) stampa sotto ogni incoerenza le PROVE: righe del punteggio (fonte, minuto, punteggio,
conteggi gialli/rossi/angoli) e righe-evento entro 5 minuti, i simboli disegnati, per i gol ogni cambio del
punteggio per fonte e ogni Goal della timeline, per i cartellini tutte le righe-evento di cartellini e i cambi
dei conteggi, per il calcio d'inizio il KickOff, il primo frame in gioco e i passi attorno alla lineetta.

Prova della «cura» dal raw (se il raw della partita c'e' in `_live_raw/<event>/<event>.raw.jsonl`), dalla
radice, senza toccare il database ne' il repository:

```
python tools/replay_barra_fixture.py --registrazioni _live_raw --uscita %TEMP%\barra13 35787218 35768297 ...
cd frontend && npx vite-node scripts/verifica_barra_fixture.ts %TEMP%\barra13\replay_barra_35787218.json --dettaglio
```

Confronto: un'incoerenza presente nel database e ASSENTE nella fixture dal raw = difetto dei dati caricati
(classe c curabile: la ricarica dal raw e' una scrittura nel database, la decide l'utente); presente in
entrambe = verificatore, pagina, o dato gia' nel raw (buco del registratore). Se in `_live_raw` c'e' solo
`<event>.jsonl` (libri del recorder) e NON il raw dello stream, lo strumento non si applica: si classifica
con `--dettaglio` sul database.

---------------------------------------------------------------------------------------------------

## 5. Cosa ho cambiato (file:riga) e perche'

| file | cosa |
|---|---|
| `frontend/src/lib/__fixtures__/replay_barra_35760084.json`, `..._35797769.json` | rigenerate (par. 1) |
| `frontend/src/lib/replayVerificaBarraCalcio.ts` 27, 143-147, 234-265, 306-317, 362-379 | 2.1/2.2 risalite e aumenti fuori barra; 2.4 `perDati` dei cartellini |
| `frontend/src/lib/replayVerificaBarra.ts` 78-81, 175-189, 288-293, 452, 539-563 | campo `perDati` (solo quando serve: i rilievi di sempre restano identici, provato), `soloPerDati`, motivo del calcio d'inizio |
| `frontend/src/lib/replayVerificaBarraTesto.ts` 7, 18-20, 25-26 | `[PER DATI: motivo]` nel rilievo, `INCOERENTE PER DATI` nella riga di esito |
| `frontend/src/lib/replayVerificaBarraDb.ts` 20-22, 72-73, 85-86, 107, 122-123, 133-145, 157 | riepilogo «di cui N SOLO PER DATI», opzione `dettaglio` |
| `frontend/scripts/verifica_barra_replay.ts` 17, 32-34, 47, 52, 62, 71, 138, 152-158 | `--dettaglio`, `per_dati` e `perDati` nel JSON |
| `frontend/src/components/replay/AvvisoCoerenzaBarra.tsx` 91-96 | la riga «Dato registrato, non errore della pagina: <motivo>» sotto la voce (avviso visibile) |
| `frontend/src/lib/replayVerificaBarraDettaglio.ts` (nuovo) | le prove di ogni incoerenza |
| `frontend/src/lib/replayVerificaBarraFixture.ts` (nuovo), `frontend/scripts/verifica_barra_fixture.ts` (nuovo) | verifica di una fixture dal raw |
| `tools/replay_barra_fixture.py` 33-38, 78-91, 173, 183, 235-238, 365-370, 444, 458-490 | `--registrazioni`, `--uscita` (di serie: percorsi identici a prima, provato dal test di riproducibilita') |
| test: `replayVerificaBarra.classi.test.ts` (nuovo, 20), `replayVerificaBarraFixture.test.ts` (nuovo, 8), `replayVerificaBarraDb.test.ts` (+1), `replayVerificaBarraScript.test.ts` (+1), `AvvisoCoerenzaBarra.test.tsx` (+2), `tools/test_replay_barra_fixture.py` (+2) | |

Nessuna strategia, nessun bot, nessun file del banco toccato. La PAGINA Match Replay (barra, simboli,
tabellone) NON e' cambiata: cambia solo l'avviso (una riga in piu' quando c'e' il motivo dei dati).

---------------------------------------------------------------------------------------------------

## 6. Test, falsificazioni, tempi (esiti VERI)

Carico della macchina: load average 12-21 su 4 CPU per tutto il lavoro (`suite_carico.txt`).

**Suite (file in questa cartella).**
- `python3 -m pytest Betfair/ -q -p no:cacheprovider`: **10951 passed, 65 skipped, 6 xfailed, 0 failed**, 10 min 49 s (`pytest_betfair_dopo.txt`).
- `python3 -m pytest tools/test_replay_barra_fixture.py -q -p no:cacheprovider`: **17 passed** (15 di prima + 2 nuovi),
  2 min 11 s (`pytest_tools_dopo.txt`). Sulla partenza: 2 rossi (i due `riproducibile_dal_raw`).
- `npx tsc -p tsconfig.app.json --noEmit`: **0 errori** (`tsc_dopo.txt`). `npm run build`: **riuscito** (`build_dopo.txt`).
- `npx vitest run` completo: **2 failed | 5354 passed | 51 skipped** (368 file, 31 min 36 s, `vitest_completo_dopo.txt`).
  I 2 rossi sono in file NON toccati (`RitardiPanel.fixb.test.tsx`: elemento non trovato; `SafeStrategy.test.tsx`
  tennis): rilanciati da soli **31 passed** (`vitest_2_rossi_rilancio.txt`) = rossi da carico (lo stesso SafeStrategy
  era rosso da carico anche nel vitest completo del cantiere 14). Da rilanciare sul PC.
- Insieme barra (verificatore, partite, pagina, avviso, simboli, punteggio, tennis, script, db, impronte, lancio):
  prima 15 file **174 passed | 1 skipped**; dopo 17 file **206 passed | 1 skipped** (+32 test nuovi, 0 rossi)
  (`vitest_barra_prima.txt`, `vitest_barra_dopo.txt`). Mutanti `replayBarraMutanti.ts` (D1-D4) ancora tutti rilevati
  (il partite test, verde, li pretende rossi).

**Test nuovi (32 vitest + 2 pytest):** `replayVerificaBarra.classi.test.ts` 20 (A1 x8, A2 x2, C1 x5, C2 x5),
`replayVerificaBarraFixture.test.ts` 8, `replayVerificaBarraDb.test.ts` +1, `replayVerificaBarraScript.test.ts` +1
(script lanciato davvero contro il finto PostgREST), `AvvisoCoerenzaBarra.test.tsx` +2,
`tools/test_replay_barra_fixture.py` +2. TDD: i casi A1/A2 erano ROSSI prima della correzione, con il testo del PC.

**Falsificazione** (`muta.py`, esito in `mutazioni.txt`; ogni mutazione ripristinata dalla copia con sha256 verificato;
alla fine `sha256sum -c` OK sui 4 file, `grep -c MUTAZIONE` = 0, `git diff` identico byte per byte a quello di prima):

| id | mutazione | esito |
|---|---|---|
| M1 | la risalita / l'aumento fuori barra non giustifica il simbolo (= difetto di partenza) | 7 rossi |
| M2 | una discesa fra DUE fonti abbassa il livello come un VAR | 1 rosso |
| M3 | la risalita di una squadra giustifica il Goal dell'altra | 1 rosso |
| M4 | una risalita giustifica piu' simboli | 1 rosso |
| M5 | nessun limite di 3 minuti | 1 rosso |
| M6 | l'aumento prima del primo frame non conta | 1 rosso |
| M7 | KICKOFF_DISCORDANTE senza motivo dei dati | 9 rossi |
| M8 | CARTELLINI_DIVERSI sempre per dati | 2 rossi |
| M9 | "solo per dati" con `some` invece di `every` | 2 rossi |
| M10 | il buco descritto come flag discorde | 1 rosso |
| M11 | il generatore ignora `--registrazioni` per punteggi e timeline | 1 rosso |
| M12 | il generatore ignora `--uscita` | 1 rosso |
| M13 | curator senza la regola (d) (la causa del rosso rimessa) | 2 rossi (`riproducibile_dal_raw` x2) |

**Tempi.** Verificatore sulle due fixture vere, stesse fixture, codice di HEAD e nuovo alternati due volte
(mediana di 25 giri): PRIMA 82.2 e 67.9 ms / 66.5 e 82.0 ms, DOPO 82.5 e 70.8 ms / 71.9 e 69.2 ms (35760084 / 35797769):
nessuna differenza oltre il rumore del carico. Generatore: 53 s le due partite (stesso codice di lettura). I tempi
dei test vitest dell'insieme barra sono raddoppiati anche nei file NON toccati (es. `replayBarraPunteggio` 105 s ->
207 s) col load average salito da ~13 a ~21: non confrontabili.

---------------------------------------------------------------------------------------------------

## 7. Limiti, cosa NON ho fatto, cosa NON ho potuto verificare

- Le 13 partite NON sono nel cloud: la classe di ciascuna e' DEDOTTA dal referto del PC e provata su
  riproduzioni con i formati veri; l'esito vero si scrive sul PC (par. 3-4).
- 2.2 (35812264) e' un'ipotesi: se l'aumento e' oltre 3 minuti prima del simbolo, resta l'errore e va
  guardato con `--dettaglio`.
- Strumento di CURA che RICARICA la partita nel database: NON costruito (sarebbe una scrittura nel
  database, vietata ai delegati; la ricarica la decide l'utente). Costruita la parte in sola lettura:
  rigenerazione dal raw con il curatore unico + verifica (par. 4).
- Punto cieco CONDIVISO da pagina e verificatore (non toccato, nessuna delle 13 lo mostra): senza timeline
  discreta la pagina disegna i gol dai delta contro il MASSIMO visto, quindi un gol vero DOPO un gol
  annullato non avrebbe simbolo; e il verificatore, che non pretende la risalita, non lo segnalerebbe.
  Proposta (da decidere): abbassare il massimo della pagina e del verificatore su una correzione della
  STESSA fonte; prima va provato sulle 38 partite del PC.
- Una risalita prodotta da una seconda fonte in ritardo DOPO una correzione VAR (0-1 corretto, l'altra
  fonte mostra ancora 0-2) potrebbe giustificare un simbolo vicino: in quel caso c'e' comunque
  TABELLONE_SCENDE (errore), quindi la partita resta incoerente.
- Le suite complete qui sono gonfiate dal carico (vedi par. 6); i tempi assoluti non si confrontano.

## 8. Decisioni per l'utente

Nessuna decisione di trading (nessuna strategia toccata). Due decisioni sulla pagina, NON prese:
1. Cartellini persi dalla timeline (se il PC trova CARTELLINI_DIVERSI non «per dati»): disegnarli dai
   conteggi come gia' si fa per i gol (D4 del 07/10)? Proposta: si', con lo stesso criterio dei 3 minuti.
2. Ricaricare dal raw le partite i cui dati caricati risultano difettosi e curabili (par. 4)?

---------------------------------------------------------------------------------------------------

## Blocco per la cronostoria

**08/10 - CANTIERE 13 (cloud, delegato; NON committato, worktree agent-ad97311e16b40a5ca, base 3b8ce19).**
Rosso `tools/test_replay_barra_fixture.py::test_fixture_riproducibile_dal_raw` (1108 vs 1107 frame): CAUSA PROVATA =
fixture vecchie, generate in 267605c PRIMA della regola (d) del curator (9e86c3a); col curator di 9e86c3a^ la
rigenerazione da' byte identici alle fixture (ambiente, librerie e b5547eb esclusi). Fixture rigenerate, diff spiegato
riga per riga (solo righe di cambio stato). Le 13 partite: (a) SIMBOLO_GOL_SENZA_AUMENTO dopo un VAR della stessa
squadra (35787218, 35777617, 35768297, 35768365) = falso positivo del verificatore, corretto; (a, ipotesi) 35812264;
(c) KICKOFF_DISCORDANTE (6 partite) e CARTELLINI_DIVERSI con barra = timeline: dichiarati con `perDati` (motivo nel
referto, "INCOERENTE PER DATI", riga nell'avviso della pagina), mai silenziosi. Nuovi: `--dettaglio` nello strumento del
DB, `scripts/verifica_barra_fixture.ts`, `--registrazioni/--uscita` nel generatore. Test: pytest Betfair 10951 passed 0
rossi; tools 17 passed; tsc 0; build ok; vitest 5354 passed + 2 rossi da carico in file non toccati (verdi da soli);
13 mutazioni tutte rosse. DA FARE SUL PC: `verifica_barra_replay.ts --senza-note` sulle 38 (atteso 28 OK + 10 solo per
dati) e `--dettaglio` sulle 13; riempire la tabella del par. 3 del referto. Punto di ripresa: quella tabella.

## Verifica del coordinatore cloud (08/10)
- Diff riletto. Applicato sulla cima (W1, C10 compresi): `tsc` 0; vitest della barra (13 file) 160/160; `tools/test_replay_barra_fixture.py`
  17/17 (il rosso «riproducibile dal raw» della partenza e' chiuso: la fixture rigenerata coincide con quanto produce il generatore
  attuale dal raw; causa = fixture generate prima della regola (d) del curator, come dimostrato nel referto).
- MIE MUTAZIONI: risalita dopo il VAR ignorata -> 4 rossi; «solo per dati» con UNA sola incoerenza per dati -> 2 rossi; finestra di
  abbinamento del gol 30 minuti invece di 3 -> 1 rosso. Ripristino verificato.
- DA FARE SUL PC: le 38 partite del DB e la tabella delle 13 incoerenti (par. 3-4).
