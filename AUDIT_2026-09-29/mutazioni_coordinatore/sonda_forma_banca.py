"""SONDA DEL COORDINATORE (sola lettura, non e' la certificazione): fa girare il
replay di Mike con la copertura nella FORMA NUOVA (``cover_form=lay_under45``)
passando dal punto d'ingresso unico del banco, in UN solo processo.

La taratura degli scenari viene cambiata SOLO IN MEMORIA (nessun file toccato):
a ogni scenario scelto si aggiunge ``cover_form``. I controlli del banco tarati
sulla forma vecchia (E2, J6, S2...) possono segnalare violazioni: qui interessa
cosa fa Mike (ordini, importi, quote, abbinamenti, risultato).

uso: python sonda_forma_banca.py <evento> [<evento> ...] -- <scenario,scenario>
"""
from __future__ import annotations

import sys

from Betfair.mike.tools import replay_registrazioni as RR
from Betfair.stream.backtest import certifica


def main() -> int:
    argv = sys.argv[1:]
    sep = argv.index("--")
    eventi, scenari = argv[:sep], argv[sep + 1]
    for nome in scenari.split(","):
        tar = dict(RR.SCENARI.get(nome, {}))
        tar["cover_form"] = "lay_under45"
        RR.SCENARI[nome] = tar
    print("SONDA: scenari con cover_form=lay_under45 (solo in memoria):",
          {n: RR.SCENARI[n] for n in scenari.split(",")}, flush=True)
    args = ["mike", *eventi, "--scenari", scenari, "--trasporto", "canale", "--worker", "1",
            "--data-dir",
            r"C:/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation/_live_raw"]
    try:
        return int(certifica.main(args) or 0)
    except SystemExit as ex:
        return int(ex.code or 0)


if __name__ == "__main__":
    sys.exit(main())
