"""Sonda di debug (NON certificazione): dove il guasto dello scenario
``ko-green-parziale`` vede passare gli ordini di Mike, e che cosa ne pensa.

uso: python AUDIT_2026-09-30/ko_green_3_minuti/sonda_guasto_banca_fischio.py <data-dir>
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from Betfair.stream.backtest import chiusura_parziale as CP
from Betfair.mike.tools import replay_registrazioni as R

orig = CP.GuastoChiusuraParziale._al_piazzamento


def spia(self, ordine, sim, market_book, instruction):
    note = getattr(ordine, "notes", None) or {}
    pt = getattr(market_book, "publish_time", None)
    b = self.bersaglio(ordine) if self.bersaglio else None
    print("PLACE", pt, dict(note), dict(getattr(ordine, "context", None) or {}),
          getattr(ordine, "side", None),
          self._ruolo_di(ordine), "bersaglio=", b,
          "prezzo", getattr(ordine.order_type, "price", None),
          "size", getattr(ordine.order_type, "size", None), file=sys.stderr, flush=True)
    out = orig(self, ordine, sim, market_book, instruction)
    print("   colpiti", len(self.colpiti), "viste", self.chiusure_viste,
          file=sys.stderr, flush=True)
    return out


CP.GuastoChiusuraParziale._al_piazzamento = spia
from Betfair.stream.backtest.certifica import main  # noqa: E402

main(["mike", "35760084", "--scenari", "ko-green-parziale", "--trasporto", "canale",
      "--worker", "0", "--data-dir", sys.argv[1]])
