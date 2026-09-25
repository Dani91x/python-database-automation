"""leggi_tempi_ordine.py - F0 "misura": p50/p95 dei tempi dell'ordine dal log.

Legge le righe ``tempi_ordine ...`` scritte da ``Betfair/stream/tempi_ordine.py``
(anche con prefissi davanti: orario, livello, ``[runner]`` dell'app desktop) e
stampa, per STRADA e per TRATTO, quante misure ci sono, p50, p95 e massimo.

Uso:
    python -m Betfair.stream.tools.leggi_tempi_ordine <log> [<log> ...]
    python -m Betfair.stream.tools.leggi_tempi_ordine --per-via <log>
    type runner.log | python -m Betfair.stream.tools.leggi_tempi_ordine -

Percentile: interpolazione lineare fra i ranghi vicini (come ``numpy.percentile``
di serie). I tratti elencati in ``orologi=`` confrontano due orologi diversi
(PC contro DB o Betfair): lo script li conta a parte (colonna ``misti``) perche'
portano l'errore dell'orologio del PC (~2 s il 17/09).

Sola lettura: nessun IO oltre ai file passati.
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from typing import Dict, Iterable, List, Optional, Tuple

TRATTI = ("decisione_ms", "ricezione_ms", "presa_ms", "place_ms", "risposta_ms",
          "abbinato_ms", "interno_ms", "risposta_bf_ms")

_RIGA = re.compile(r"\btempi_ordine\s+(ref=.*)$")


def analizza_riga(riga: str) -> Optional[Dict[str, str]]:
    """``k=v`` di una riga ``tempi_ordine``; None se la riga non lo e'."""
    m = _RIGA.search(riga.rstrip("\r\n"))
    if not m:
        return None
    campi: Dict[str, str] = {}
    for pezzo in m.group(1).split():
        if "=" not in pezzo:
            continue
        k, v = pezzo.split("=", 1)
        campi[k] = v
    return campi if "strada" in campi else None


def percentile(valori: List[float], q: float) -> Optional[float]:
    """Percentile ``q`` (0-100) con interpolazione lineare; None se vuoto."""
    if not valori:
        return None
    xs = sorted(valori)
    if len(xs) == 1:
        return float(xs[0])
    pos = (len(xs) - 1) * (q / 100.0)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return float(xs[lo])
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def _numero(v: Optional[str]) -> Optional[float]:
    if v is None or v == "na":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def raccogli(righe: Iterable[str], per_via: bool = False
             ) -> Dict[Tuple[str, str], Dict[str, List[float]]]:
    """{(gruppo, tratto): {"tutti": [...], "misti": [...]}}. Gruppo = strada
    (o strada/via con ``per_via``)."""
    out: Dict[Tuple[str, str], Dict[str, List[float]]] = {}
    for r in righe:
        c = analizza_riga(r)
        if c is None:
            continue
        gruppo = c["strada"]
        if per_via and c.get("via") and c.get("via") != c["strada"]:
            gruppo = f"{c['strada']}/{c['via']}"
        misti = set()
        orologi = c.get("orologi")
        if orologi and orologi != "na":
            for voce in orologi.split(","):
                misti.add(voce.split(":", 1)[0] + "_ms")
        for t in TRATTI:
            x = _numero(c.get(t))
            if x is None:
                continue
            cella = out.setdefault((gruppo, t), {"tutti": [], "misti": []})
            cella["tutti"].append(x)
            if t in misti:
                cella["misti"].append(x)
    return out


def tabella(dati: Dict[Tuple[str, str], Dict[str, List[float]]]) -> List[Dict[str, object]]:
    righe: List[Dict[str, object]] = []
    for (gruppo, tratto) in sorted(dati, key=lambda k: (k[0], TRATTI.index(k[1]))):
        xs = dati[(gruppo, tratto)]["tutti"]
        righe.append({"strada": gruppo, "tratto": tratto, "n": len(xs),
                      "misti": len(dati[(gruppo, tratto)]["misti"]),
                      "p50": percentile(xs, 50), "p95": percentile(xs, 95),
                      "max": max(xs) if xs else None})
    return righe


def _f(v: object) -> str:
    return "-" if v is None else f"{float(v):.1f}"  # type: ignore[arg-type]


def stampa(righe: List[Dict[str, object]], out=None) -> None:
    out = out if out is not None else sys.stdout
    if not righe:
        out.write("nessuna riga tempi_ordine trovata\n")
        return
    out.write(f"{'strada':<16}{'tratto':<16}{'n':>6}{'misti':>7}{'p50':>10}{'p95':>10}"
              f"{'max':>10}\n")
    for r in righe:
        out.write(f"{str(r['strada']):<16}{str(r['tratto']):<16}{r['n']:>6}{r['misti']:>7}"
                  f"{_f(r['p50']):>10}{_f(r['p95']):>10}{_f(r['max']):>10}\n")
    out.write("\nms. 'misti' = misure che confrontano due orologi (PC contro DB o Betfair): "
              "errore ~2 s se l'orologio del PC non e' sincronizzato.\n")


def _righe_da(percorsi: List[str]) -> Iterable[str]:
    for p in percorsi:
        if p == "-":
            yield from sys.stdin
            continue
        with open(p, encoding="utf-8", errors="replace") as fh:
            yield from fh


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="p50/p95 dei tempi dell'ordine dal log")
    ap.add_argument("log", nargs="+", help="file di log (o '-' per lo standard input)")
    ap.add_argument("--per-via", action="store_true",
                    help="separa le vie di una strada (tennis: canale / coda)")
    a = ap.parse_args(argv)
    stampa(tabella(raccogli(_righe_da(a.log), per_via=a.per_via)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
