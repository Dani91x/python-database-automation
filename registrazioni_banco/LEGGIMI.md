# Registrazioni di mercato per i replay (copia compressa)

Due partite registrate dallo stream Betfair, le stesse usate per certificare lo Scalper calcio.
Sono qui (compresse, 5 MB) perche' chi lavora senza il PC dell'utente possa lanciare i replay di
certificazione. `_live_raw/` resta fuori dal repository.

| evento | contenuto | mercati utili |
|---|---|---|
| 35797769 | partita intera, pre-match lungo (stream completo 95,4%) | Esito finale, Under/Over 1,5 - 2,5 - 3,5 |
| 35760084 | partita intera | come sopra (usata anche da Mike, Safe, Omega) |

## Come usarle

Dalla radice del repository:

```
python - <<'PY'
import gzip, os, shutil
for ev in ("35797769", "35760084"):
    dst = os.path.join("_live_raw", ev)
    os.makedirs(dst, exist_ok=True)
    src = os.path.join("registrazioni_banco", ev)
    for nome in os.listdir(src):
        if nome.endswith(".gz"):
            with gzip.open(os.path.join(src, nome), "rb") as a, open(os.path.join(dst, nome[:-3]), "wb") as b:
                shutil.copyfileobj(a, b)
        else:
            shutil.copy(os.path.join(src, nome), dst)
PY
python -m Betfair.stream.backtest.certifica scalper_calcio 35797769 --scenari media-under,media-under-paper,media-under-35
```

Regole: i replay passano SOLO da `python -m Betfair.stream.backtest.certifica ...`, uno alla volta;
ogni replay sotto i 5 minuti (tetto 10); mai modificare queste registrazioni, mai scriverne di finte.
