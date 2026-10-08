# -*- coding: utf-8 -*-
"""Falsificazione D-7: ogni mutazione del worker deve far diventare ROSSO almeno un
test (file nuovo D-7 + file del W2). Il worker si ripristina dai byte originali e se
ne verifica lo sha256 dopo OGNI mutazione e alla fine. Nessuna interruzione a meta':
il ripristino e' in ``finally``. Uso, dalla radice del worktree:
``python AUDIT_2026-10-08/decisioni_sera/W2_D7_strumenti/falsifica_d7.py``. ASCII-only."""
import hashlib
import pathlib
import re
import subprocess
import sys

RADICE = pathlib.Path(__file__).resolve().parents[3]
WORKER = RADICE / "Betfair" / "stream" / "live_order_worker.py"
TEST = ["Betfair/stream/tests/test_greenup_fuori_bot_annullo_app_2026_10_08.py",
        "Betfair/stream/tests/test_greenup_fuori_bot_2026_10_08.py"]

# (nome, vecchio, nuovo): sostituzione UNICA nel testo del worker (LF)
MUTAZIONI = [
    ("D1 nessun annullo (ordini appesi ignorati, si copre comunque)",
     'appese = (_efb_app_appese(pos["fuori"], str(pos["plan"].side))\n              if pos["plan"].actionable else [])',
     'appese = []'),
    ("D2 nessuna rilettura del conto dopo l'annullo",
     '        try:\n            pos = _efb_posizione(sb, client, market, market_id, selection_id, handicap)\n        except ValueError as ex:\n            raise ValueError(f"{nota_annullo}; poi {ex}") from ex\n',
     ''),
    ("D3 nessun controllo dell'ordine ancora vivo dopo la rilettura",
     '        if ancora:\n            o = ancora[0]',
     '        if False:\n            o = ancora[0]'),
    ("D4 cancelOrders senza betId (annulla tutto il mercato)",
     'instructions=[{"betId": b} for b in ids],',
     'instructions=None,'),
    ("D5 guardia mercato/betId tolta",
     'if not mid or not ids or len(ids) != len(righe):',
     'if False:'),
    ("D6 annullo anche degli ordini 'live' dei BOT (qui invece di fuori)",
     'appese = (_efb_app_appese(pos["fuori"], str(pos["plan"].side))',
     'appese = (_efb_app_appese(pos["qui"], str(pos["plan"].side))'),
    ("D7 lato della copertura ignorato",
     '                and str(o.get("side") or "").lower() == side)]',
     '                )]'),
    ("D8 annullo non dichiarato nel detail",
     'testa = f"{nota_annullo}; " if nota_annullo else ""',
     'testa = ""'),
    ("D9 annullati_app non nell'esito",
     '    if annullati:\n        extra["annullati_app"] = annullati\n',
     ''),
    ("D10 sizeCancelled ignorata (annullato = non abbinato)",
     'r["size_annullata"] = _f(rep.get("sizeCancelled"))',
     'r["size_annullata"] = r["non_abbinato"]'),
    ("D11 esito SUCCESS letto come fallito",
     'elif str(rep.get("status") or "").upper() == "SUCCESS":',
     'elif str(rep.get("status") or "").upper() == "SUCCESSO":'),
    ("D12 rilettura KO senza la nota dell'annullo",
     'raise ValueError(f"{nota_annullo}; poi {ex}") from ex',
     'raise'),
    ("D13 lightweight tolto (risposta = risorsa, non dict)",
     '                                    lightweight=True)',
     '                                    )'),
    ("D14 errore del piazzamento senza la coda dell'annullo",
     '        if not annullati or type(ex) not in (ValueError, RuntimeError):\n            raise\n',
     '        raise\n'),
    ("D15 la coda dell'annullo anche SENZA annullo",
     '        if not annullati or type(ex) not in (ValueError, RuntimeError):',
     '        if type(ex) not in (ValueError, RuntimeError):'),
    ("D16 ordini del SITO annullati come quelli dell'app",
     '            if (str(o.get("customerStrategyRef") or "").strip().lower()\n                == _EFB.STRATEGIA_MANUALE_APP\n                and str(o.get("status")',
     '            if (True\n                and str(o.get("status")'),
    ("D17 annullo anche con la posizione piatta (lato non considerato se non eseguibile)",
     '              if pos["plan"].actionable else [])\n    if appese:',
     '              if pos["plan"].actionable else [o for o in pos["fuori"] if str(o.get("customerStrategyRef") or "") == "live" and (_f(o.get("sizeRemaining")) or 0) > 0])\n    if appese:'),
    ("D18 rilettura con la vecchia nota in testa al detail persa (prefisso nel rifiuto 'non eseguibile')",
     'raise ValueError(f"{testa}greenup {_EFB.FUORI_BOT} NON eseguibile con "',
     'raise ValueError(f"greenup {_EFB.FUORI_BOT} NON eseguibile con "'),
    ("D19 rifiuto 'chiusa dall'utente' senza la nota dell'annullo",
     'f"{testa}greenup {_EFB.FUORI_BOT}: la copertura {side.upper()} {plan.size:.2f} "',
     'f"greenup {_EFB.FUORI_BOT}: la copertura {side.upper()} {plan.size:.2f} "'),
]


def sha(b):
    return hashlib.sha256(b).hexdigest()


def corri():
    r = subprocess.run([sys.executable, "-m", "pytest", *TEST, "-q", "-p", "no:cacheprovider",
                        "-rf"], cwd=RADICE, capture_output=True, text=True)
    ultima = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-300:]
    rossi = re.findall(r"FAILED (\S+)", r.stdout)
    return ultima, rossi


def main():
    originale = WORKER.read_bytes()
    h0 = sha(originale)
    testo = originale.decode("utf-8").replace("\r\n", "\n")
    righe = []
    try:
        for nome, vecchio, nuovo in MUTAZIONI:
            n = testo.count(vecchio)
            if n != 1:
                righe.append((nome, f"MUTAZIONE NON APPLICABILE (occorrenze {n})", []))
                continue
            WORKER.write_bytes(testo.replace(vecchio, nuovo).replace("\n", "\r\n")
                               .encode("utf-8"))
            try:
                ultima, rossi = corri()
            finally:
                WORKER.write_bytes(originale)
                assert sha(WORKER.read_bytes()) == h0, "RIPRISTINO FALLITO"
            righe.append((nome, ultima, rossi))
    finally:
        WORKER.write_bytes(originale)
    assert sha(WORKER.read_bytes()) == h0
    for nome, ultima, rossi in righe:
        print(f"{nome}\n    -> {ultima}")
        for x in rossi:
            print(f"       ROSSO {x.split('::')[-1]}")
    verdi = [n for n, u, r in righe if not r]
    print(f"\nmutazioni {len(righe)}, catturate {len(righe) - len(verdi)}, NON catturate: {verdi}")
    print("ripristino verificato sha256", h0)
    ultima, rossi = corri()
    print("dopo il ripristino:", ultima)


if __name__ == "__main__":
    main()
