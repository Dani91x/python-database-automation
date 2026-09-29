"""Sonda UF2 (N3, 29/09): rilancia UNO scenario `uscite-manuali-firmate` di un
bot tennis e, per ogni uscita firmata, scrive gli ordini nuovi di quella
selezione (prezzo, size chiesta, abbinato, residuo, cancellato, stato, ref) a
+5 s (quando UF2 giudica) e a fine replay. Sola lettura: nessun codice di
produzione cambia, nessuna scrittura fuori dal file d'uscita.

Uso: python AUDIT_2026-09-28/cantiere_n/sonda_uf2.py <bot> <file.jsonl> <data_dir> <ogni_ms>
"""
from __future__ import annotations

import json
import sys

from Betfair.stream.backtest import uscite_manuali as UM
from Betfair.stream.tennis_live.tools import replay_bot as RB


def _o(o):
    ot = getattr(o, "order_type", None)
    st = getattr(o, "status", None)
    return {"id": str(getattr(o, "id", "")), "side": str(getattr(o, "side", "")),
            "price": getattr(ot, "price", None), "size": getattr(ot, "size", None),
            "matched": getattr(o, "size_matched", None),
            "remaining": getattr(o, "size_remaining", None),
            "cancelled": getattr(o, "size_cancelled", None),
            "avg": getattr(o, "average_price_matched", None),
            "status": str(getattr(st, "value", st)),
            "ref": getattr(o, "customer_order_ref", None)}


def main() -> int:
    bot, out_path = sys.argv[1], sys.argv[2]
    righe = []
    tutte = []
    vero = UM.Osservatore._giudica_importi

    def _nuovi(oss, pend):
        return [o for o in list(oss._ordini_di(pend["strategia"]) or ())
                if str(getattr(o, "id", "")) not in pend["ids_prima"]
                and str(getattr(o, "selection_id", "")) == str(pend["selection_id"])]

    def _spia(self, fine):
        for pend in list(self._pendenti):
            if not fine and self.ora_ms - pend["da_ms"] < UM.FINESTRA_ORDINI_S * 1000:
                continue
            righe.append({"quando": "+5s", "chiave": pend["chiave"], "size": pend["size"],
                          "lato": pend["lato"], "da_ms": pend["da_ms"],
                          "ora_ms": self.ora_ms,
                          "ordini": [_o(o) for o in _nuovi(self, pend)]})
            tutte.append((pend, self))
        return vero(self, fine)

    UM.Osservatore._giudica_importi = _spia
    try:
        ref = RB.certifica_scenario(RB.EVENTO_DI_RIFERIMENTO,
                                    data_dir=sys.argv[3], ogni_ms=int(sys.argv[4]),
                                    scenario=UM.SCENARIO_FIRMATE, bot=bot)
    finally:
        UM.Osservatore._giudica_importi = vero
    for pend, oss in tutte:
        righe.append({"quando": "fine", "chiave": pend["chiave"], "size": pend["size"],
                      "lato": pend["lato"], "ordini": [_o(o) for o in _nuovi(oss, pend)]})
    with open(out_path, "w", encoding="utf-8") as f:
        for r in righe:
            f.write(json.dumps(r, default=str) + "\n")
        f.write(json.dumps({"note_um": [n for n in ref.note if "USCITE MANUALI" in n],
                            "sollecitati": {k: v for k, v in ref.sollecitati.items() if k.startswith("U")}}) + "\n")
        f.write(json.dumps({"violazioni": [(v.codice, v.dettaglio)
                                           for v in ref.violazioni]}, default=str) + "\n")
    print("scritte", len(righe), "violazioni", len(ref.violazioni))
    return 0


if __name__ == "__main__":
    sys.exit(main())
