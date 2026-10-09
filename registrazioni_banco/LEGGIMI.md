# Registrazioni di mercato per i replay (copia compressa)

Partite registrate dallo stream Betfair, copiate qui COMPRESSE (gzip) perche' chi lavora senza il
PC dell'utente possa lanciare i replay di certificazione. Gli originali restano fuori dal
repository (`_live_raw/` per il calcio, `~/Desktop/tennis_rec/` per il tennis). Ogni file
decompresso e' identico byte per byte all'originale (sha256 qui sotto, verificati il 09/10/2026:
referto `ARCHITETTURA_2026-10/tappa0/T0B5_REGISTRAZIONI/REFERTO.md`).

NOTA GIT: `.gitignore` (riga 44) ignora `*.jsonl.gz`: i file compressi si aggiungono con `git add -f`.

## Elenco

Copertura e verdetto: `python -m Betfair.stream.tools.validate_recordings --json` (stesso esito
sull'originale e sulla copia decompressa).

| evento | sport | partita | verdetto (copertura) | file | sha256 del raw (decompresso) | a cosa serve |
|---|---|---|---|---|---|---|
| 35797769 | calcio | Spain - Belgium (World Cup, 10/07) 2-1 | COMPLETE (95,4%) | raw, scores, timeline | `c11894abd1a6ead302e622395bb21d76c2f9c4cee31dfbf5ee4c7ad594ba5883` | scalper calcio; pre-match lungo |
| 35760084 | calcio | FK Liepaja - Ogre United (Virsliga, 30/06) 4-0 | COMPLETE (95,2%) | raw, scores, timeline | `8037bac2504ed1ef3c58147bbcd216c5628c36725f81672b03a098b0f96dcda8` | Mike, Safe, Omega, scalper |
| 35777617 | calcio | Brazil - Norway (World Cup, 05/07) 1-2 | COMPLETE (97,1%) | raw, scores, timeline | `3914a449d91a9101e2a1d9f563ad335b2d449aff839d8490889e8934c918f1fa` | Mike: gol al 2' ANNULLATO dentro la finestra del fischio (seconda entrata) |
| 35768365 | calcio | Spain - Austria (World Cup, 02/07) 3-0 | COMPLETE (95,0%) | raw, scores, timeline | `654a6f1e5a6fc304b1f619057118aa8c92031f8cafe45072ae2deee88692c498` | Mike: gol annullato al 28', gol al 35' (re-ingresso), pre-match 106' |
| 35774000 | calcio | Taborsko - SKU Amstetten (amichevole, 30/06) 0-3 | COMPLETE (98,1%) | raw, scores, timeline | `a35071a6b214bc918e75e64d9f6710b292a6c54ba7691364683ad809252360a1` | Mike: gol al 15' dopo un probabile verde al fischio (re-ingresso) |
| 35790089 | tennis | Barrios V - Simakin (07/07), set 1-2 | COMPLETE (92,4%) | raw, score | `ffb2a523544e17d55767a67ce8f582a710dd99a1cc2d322a45f045d8b00d942b` | bot tennis, Match Odds |
| 35794049 | tennis | Sinner - Struff (07/07), set 3-0 | COMPLETE (99,1%) | raw, score | `3d5ed00f255146a0028b8e726459cfb3ac374c0c9f7cfccc986a4368de4737aa` | bot tennis, Match Odds |
| 35795993 | tennis | Donski - Gueymard Wayenbu (07/07), set 2-1 | PARTIAL (65,7%) | raw, score | `35bceb13cd1d393b2d3f8cb7f8c0800ae2bf21123a8b7dd2dd1e0aaa67dadd9b` | bot tennis, Match Odds (registrazione parziale, dichiarata) |
| 35797566 | tennis | Tenti - Mejia (07/07), registrata solo una parte | Match Odds: NO_RAW; Set Betting: PARTIAL (6,8%) | score; `setbetting_20260707/` raw e score | `9931ac405dc9f206741773cfd0cc104ac60b8c9479fb6f13465f086c7a4a81cc` (Set Betting) | NON usabile dai bot tennis (lavorano sul Match Odds, mai registrato): il banco risponde ERROR, come nel referto del 08/10 |

Le copie calcio stanno in `registrazioni_banco/<id>/`; le copie tennis in `registrazioni_banco/tennis/<giorno>/<id>/`
(stesso albero del recorder tennis, `TENNIS_RECORD_DIR/<giorno>/<id>/`), cosi' il test della barra di Match Replay
(`frontend/src/lib/replayVerificaBarra.partite.test.ts`), che scopre da solo ogni cartella calcio di primo livello e
pretende la fixture `frontend/src/lib/__fixtures__/replay_barra_<id>.json` (`python tools/replay_barra_fixture.py <id>`),
non le confonde con partite di calcio. OGNI registrazione calcio nuova qui dentro richiede la sua fixture.
I nomi sono quelli (troncati) del sidecar dei punteggi. Il tennis usa il sidecar `<id>.score.jsonl` (singolare); il calcio `<id>.scores.jsonl` (plurale)
piu' `<id>.timeline.jsonl` (non compresso).

## Ricostruire le cartelle che il banco si aspetta

Il banco calcio legge `_live_raw/<id>/` nella radice del repository (`DATA_DIR`, variabile
`LIVE_STREAM_DATA_DIR`). Il banco tennis legge `TENNIS_RECORD_DIR/<giorno>/<id>/` (di serie
`~/Desktop/tennis_rec`; il giorno e' l'ultima sottocartella numerica, qui `20260707`) e cerca la
partita anche nelle sottocartelle sorelle (`setbetting_20260707`).
Per il tennis si usa una cartella APARTE (`~/tennis_rec_banco`), cosi' sul PC dell'utente le
registrazioni vere di `~/Desktop/tennis_rec` non si toccano. Lo script non sovrascrive mai un file
che esiste gia'.

Dalla radice del repository:

```
python - <<'PY'
import gzip, os, shutil
CALCIO = "_live_raw"                                                    # cartella del banco calcio (DATA_DIR)
TENNIS = os.path.join(os.path.expanduser("~"), "tennis_rec_banco")      # radice tennis (TENNIS_RECORD_DIR)
SRC = "registrazioni_banco"

def copia(da, a):
    if os.path.exists(a):
        print("esiste gia', lasciato com'e':", a)
        return
    os.makedirs(os.path.dirname(a), exist_ok=True)
    if da.endswith(".gz"):
        with gzip.open(da, "rb") as x, open(a, "wb") as y:
            shutil.copyfileobj(x, y)
    else:
        shutil.copyfile(da, a)

# calcio: registrazioni_banco/<id>/ -> _live_raw/<id>/
for ev in sorted(os.listdir(SRC)):
    cartella = os.path.join(SRC, ev)
    if not (ev.isdigit() and os.path.isdir(cartella)):
        continue
    for nome in os.listdir(cartella):
        fuori = nome[:-3] if nome.endswith(".gz") else nome
        copia(os.path.join(cartella, nome), os.path.join(CALCIO, ev, fuori))
# tennis: registrazioni_banco/tennis/<giorno>/<id>/ -> TENNIS/<giorno>/<id>/ (stesso albero del recorder)
for radice, _dirs, files in os.walk(os.path.join(SRC, "tennis")):
    for nome in files:
        fuori = nome[:-3] if nome.endswith(".gz") else nome
        rel = os.path.relpath(radice, os.path.join(SRC, "tennis"))   # "<giorno>/<id>"
        copia(os.path.join(radice, nome), os.path.join(TENNIS, rel, fuori))
PY
```

Risultato: `_live_raw/<id>/<id>.raw.jsonl|.scores.jsonl|.timeline.jsonl` per il calcio;
`~/tennis_rec_banco/20260707/<id>/<id>.raw.jsonl|.score.jsonl` per il tennis, piu'
`~/tennis_rec_banco/20260707/35797566/35797566.score.jsonl` e
`~/tennis_rec_banco/setbetting_20260707/35797566/35797566.raw.jsonl|.score.jsonl`.

## Comandi di certificazione

Regole: i replay passano SOLO da `python -m Betfair.stream.backtest.certifica ...`, uno alla
volta; dichiarare la durata prima di lanciarlo; ogni certificazione sotto i 5 minuti (tetto 10);
mai modificare queste registrazioni, mai scriverne di finte.

Calcio (dalla radice del repository, dopo la ricostruzione):

```
python -m Betfair.stream.backtest.certifica scalper_calcio 35797769 --scenari media-under,media-under-paper,media-under-35
python -m Betfair.stream.backtest.certifica mike 35760084 --scenari tutti
python -m Betfair.stream.backtest.certifica mike 35777617 --scenari base
python -m Betfair.stream.backtest.certifica mike 35768365 --scenari base
python -m Betfair.stream.backtest.certifica mike 35774000 --scenari base
```

(Mike con `--scenari tutti` su una sola partita ha impiegato 728 s il 02/10: su queste tre
partite, piu' lunghe, si parte da `base` e si misura il tempo prima di allargare.)

Tennis (bot registrati: `tennis_pro`, `tennis_scalper`, `tennis_flb`, `tennis_swing`,
`safe_tennis`). Bash:

```
export TENNIS_RECORD_DIR="$HOME/tennis_rec_banco"
python -m Betfair.stream.backtest.certifica tennis_pro 35790089 --scenari tutti
python -m Betfair.stream.backtest.certifica tennis_scalper 35794049 --scenari tutti
python -m Betfair.stream.backtest.certifica tennis_flb 35795993 --scenari tutti
python -m Betfair.stream.backtest.certifica tennis_swing 35794049 --scenari tutti
python -m Betfair.stream.backtest.certifica safe_tennis 35795993 --scenari tutti
```

PowerShell: `$env:TENNIS_RECORD_DIR = "$HOME\tennis_rec_banco"`. In alternativa alla variabile:
`--data-dir ~/tennis_rec_banco/20260707` (in quel caso la sottocartella `setbetting_20260707` non
viene visitata).
