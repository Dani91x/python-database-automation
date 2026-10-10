"""Parita' PRIMA/DOPO la decisione 5 dell'utente (10/10/2026) su ``pnl_mercato``.

Confronta il ``pnl_mercato`` di PRIMA (letto da git al commit base ``d073ddcb`` e caricato
come modulo a parte) con quello di ADESSO sugli stessi ingressi:

  A. mercati a vincitore unico: TUTTE le ``marketDefinition`` registrate in
     ``registrazioni_banco/`` (calcio e tennis) con ``bettingType`` ODDS e un vincitore,
     ordini casuali (prezzi e importi della griglia dei test), runner come int (come il
     libro li teneva prima): la ``PosizioneMercato`` e i campi comuni del
     ``CalcoloPosizione`` devono essere IDENTICI (uguale = identico, non simile);
  B. mercati NON a vincitore unico (piu' vincitori, asiatici, tipo ignoto; senza LINE):
     l'esposizione massima (stima prudente) IDENTICA a prima, i motivi di prima tutti
     presenti, il "se vince" prima vuoto e ora pieno;
  C. LINE: l'esposizione cambia (quota 2,0 e stima ordine per ordine): si contano i casi.

Uso (dalla radice del repository): ``python ARCHITETTURA_2026-10/ondata1/W1-C2/parita_decisione5.py``
Scrive l'esito accanto (``parita_decisione5.txt``). Nessuna rete, nessun DB. ASCII-only.
"""
from __future__ import annotations

import dataclasses
import gzip
import json
import pathlib
import random
import subprocess
import sys
import types

RADICE = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RADICE))

from Betfair.nucleo.ordini import pnl_mercato as NUOVO  # noqa: E402
from Betfair.nucleo.ordini.contratto import OrdineConto  # noqa: E402

BASE = "d073ddcb"
FILE = "Betfair/nucleo/ordini/pnl_mercato.py"


def _vecchio() -> types.ModuleType:
    src = subprocess.run(["git", "show", f"{BASE}:{FILE}"], cwd=RADICE, check=True,
                         capture_output=True, text=True).stdout
    mod = types.ModuleType("pnl_mercato_prima")
    sys.modules[mod.__name__] = mod          # le dataclass cercano il loro modulo
    exec(compile(src, f"{BASE}:{FILE}", "exec"), mod.__dict__)
    return mod


def _definizioni() -> list:
    out = []
    for f in sorted((RADICE / "registrazioni_banco").rglob("*.raw.jsonl.gz")):
        visti = set()
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for riga in fh:
                for mc in json.loads(riga).get("mc") or []:
                    md = mc.get("marketDefinition")
                    if md and md.get("marketType") not in visti:
                        visti.add(md.get("marketType"))
                        out.append((f.name, md))
    return out


def _oc(i: int, sel: int, lato: str, abb: float, pm: float, autore: str, hc: float = 0.0):
    return OrdineConto(bet_id=str(i), market_id="1.200", selection_id=sel, handicap=hc,
                       lato=lato, prezzo=pm, importo=abb, abbinato=abb, residuo=0.0,
                       prezzo_medio=pm, stato="abbinato", autore=autore, ref=None,
                       modo="live", aggiornato_ms=1)


def _ordini(rnd: random.Random, sel: list, hc: tuple = (0.0,)) -> list:
    return [_oc(i, rnd.choice(sel), rnd.choice(["back", "lay"]),
                round(rnd.choice([0.01, 0.5, 1.0, 2.0, 2.37, 3.37, 10.0, 50.0]), 2),
                rnd.choice([1.01, 1.5, 1.83, 2.02, 3.35, 9.2, 34.0, 1000.0]),
                rnd.choice(["desktop", "mike", "sito", "omega"]), rnd.choice(hc))
            for i in range(rnd.randint(0, 12))]


def _comuni(c) -> dict:
    return {k: getattr(c, k) for k in ("scartati", "a_linee", "supportato",
                                       "esposizione_massima", "runner_noti", "motivi",
                                       "solo_abbinato")}


def main() -> int:
    V = _vecchio()
    rnd = random.Random(20261010)
    righe = []
    defs = _definizioni()
    singoli = [(f, md) for f, md in defs
               if md.get("bettingType") == "ODDS" and md.get("numberOfWinners") == 1]
    a_casi = a_diversi = 0
    for f, md in singoli:
        sel = [int(r["id"]) for r in md["runners"]]
        for _ in range(60):
            ordini = _ordini(rnd, sel)
            kw = dict(runner=sel if rnd.random() < 0.8 else None,
                      tipo_scommessa="ODDS", vincitori=1, tipo_mercato=md.get("marketType"))
            v, n = V.calcola("1.200", "live", ordini, **kw), NUOVO.calcola("1.200", "live",
                                                                          ordini, **kw)
            # testo JSON: NaN (esposizione non calcolabile) e' uguale a se stesso solo cosi'
            pv, pn = dataclasses.asdict(v.posizione), dataclasses.asdict(n.posizione)
            uguali = (json.dumps(pv, sort_keys=True, default=str)
                      == json.dumps(pn, sort_keys=True, default=str)
                      and _comuni(v) == _comuni(n) and n.qualita == "esatto")
            a_casi += 1
            a_diversi += not uguali
    righe.append(f"A vincitore unico: {len(singoli)} definizioni registrate, {a_casi} casi, "
                 f"diversi {a_diversi}")
    b_casi = b_diversi = 0
    tipi_b = [("ODDS", 2, "DOUBLE_CHANCE", (0.0,)), ("ODDS", 3, "PLACE", (0.0,)),
              ("ODDS", None, "PLACE", (0.0,)), (None, None, None, (0.0,)),
              ("ASIAN_HANDICAP_DOUBLE_LINE", 0, "ASIAN_HANDICAP", (-0.5, -0.25, 0.0, 0.75)),
              ("ASIAN_HANDICAP_SINGLE_LINE", 0, "TOTAL_GOALS", (0.0, 1.5, 2.5)),
              ("ODDS", 1, "MATCH_ODDS", (-1.0, 0.0))]
    for tipo, vinc, tm, hc in tipi_b:
        for _ in range(400):
            sel = [101, 102, 103]
            ordini = _ordini(rnd, sel, hc)
            kw = dict(runner=sel, tipo_scommessa=tipo, vincitori=vinc, tipo_mercato=tm)
            v, n = V.calcola("1.200", "live", ordini, **kw), NUOVO.calcola("1.200", "live",
                                                                          ordini, **kw)
            if v.supportato:          # a vincitore unico per entrambi: e' il caso A
                ok = dataclasses.asdict(v.posizione) == dataclasses.asdict(n.posizione)
            else:
                ok = (v.esposizione_massima == n.esposizione_massima
                      and v.posizione.esposizione_massima == n.posizione.esposizione_massima
                      and set(v.motivi) <= set(n.motivi) and v.posizione.se_vince == {}
                      and n.qualita == "per_selezione"
                      and (not ordini or n.se_vince_per_linea))
            b_casi += 1
            b_diversi += not ok
    righe.append(f"B non a vincitore unico (senza LINE): {b_casi} casi, esposizione o motivi "
                 f"diversi {b_diversi}")
    c_casi = c_cambiati = 0
    for _ in range(400):
        ordini = _ordini(rnd, [9001], (0.0,))
        ordini = [dataclasses.replace(o, prezzo_medio=rnd.choice([0.5 + k for k in range(1, 9)]))
                  for o in ordini]
        v = V.calcola("1.200", "live", ordini, runner=[9001], tipo_scommessa="LINE")
        n = NUOVO.calcola("1.200", "live", ordini, runner=[9001], tipo_scommessa="LINE")
        c_casi += 1
        c_cambiati += v.esposizione_massima != n.esposizione_massima
    righe.append(f"C LINE: {c_casi} casi, esposizione cambiata (quota 2,0 e stima per ordine) "
                 f"{c_cambiati}")
    testo = "\n".join(righe) + "\n"
    print(testo, end="")
    (pathlib.Path(__file__).parent / "parita_decisione5.txt").write_text(testo)
    return 0 if a_diversi == 0 and b_diversi == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
