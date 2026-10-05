"""PARTITA SINTETICA per vedere la modalita' <<media under>> sul ladder (05/10/2026).

DICHIARATA FINTA: la cartella si chiama ``_synth_media_under`` e
``certifica.py`` stampa in testa al referto che la registrazione e' SINTETICA.
Non conta come partita reale in nessun conteggio e non certifica niente: serve a
far vedere la condotta del codice VERO (sessione + strategia + flumine del
banco) su una storia di prezzi scritta apposta, quando le registrazioni vere
(``_live_raw/``, solo sul PC dell'utente) non ci sono.

Il formato e' quello NATIVO di Betfair (messaggi ``mcm``, ``marketDefinition``,
``atb``/``atl`` e ``trd`` cumulativo), letto dallo ``HistoricalStream`` del banco
comune. Ogni messaggio e' un'immagine intera (``img``) dei tre mercati: nessun
livello vecchio resta nel libro.

LA STORIA (Under 2,5; tempi dal fischio d'inizio):
  * -70': quota 1,50 ferma, scambi su entrambi i lati;
  * -64': la quota scende a 1,48 con scambi a 1,48 (la banca puo' abbinarsi);
  * -55': risale a scatti fino a 1,54;
  * -40': torna a 1,52 con scambi a 1,52;
  * -30': sale a scatti fino a 1,64;
  * -7': stop ingressi; 0': fischio, in gioco (ritardo 5 s);
  * 12': gol, mercato sospeso 60 s, riapre con l'Under 2,5 a 2,40;
  * fino a 20' la quota scende piano (il tempo passa senza gol).

Uso:
    python -m Betfair.stream.scalper.tools.synth_media_under [--data-dir DIR]

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from flumine.utils import price_ticks_away

EVENTO = "_synth_media_under"
KO_MS = 1_759_140_000_000            # fischio d'inizio (epoch ms)
INIZIO_MS = KO_MS - 70 * 60_000
FINE_MS = KO_MS + 20 * 60_000
GOL_MS = KO_MS + 12 * 60_000
SOSPENSIONE_MS = 60_000

MERCATI = {
    # tipo -> (market_id, [(selectionId, sortPriority)])
    "MATCH_ODDS": ("1.399000001", [(11, 1), (12, 2), (58805, 3)]),
    "OVER_UNDER_25": ("1.399000025", [(47972, 1), (47973, 2)]),
    "OVER_UNDER_35": ("1.399000035", [(1222344, 1), (1222345, 2)]),
}
PROFONDITA = 500.0
LIVELLI = 3


def _iso(ms: int) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z")


def _md(tipo: str, *, status: str, inplay: bool, versione: int) -> Dict[str, Any]:
    _mid, runners = MERCATI[tipo]
    return {
        "bspMarket": False, "turnInPlayEnabled": True, "persistenceEnabled": True,
        "marketBaseRate": 5.0, "eventId": EVENTO, "eventTypeId": "1",
        "numberOfWinners": 1, "bettingType": "ODDS", "marketType": tipo,
        "marketTime": _iso(KO_MS), "suspendTime": _iso(KO_MS),
        "bspReconciled": False, "complete": True, "inPlay": bool(inplay),
        "crossMatching": True, "runnersVoidable": False,
        "numberOfActiveRunners": len(runners), "betDelay": 5 if inplay else 0,
        "status": status,
        "runners": [{"status": "ACTIVE", "sortPriority": sp, "id": sid}
                    for sid, sp in runners],
        "regulators": ["MR_INT"], "countryCode": "IT", "discountAllowed": True,
        "timezone": "Europe/Rome", "openDate": _iso(KO_MS), "version": int(versione),
    }


def quota_under(ms: int) -> float:
    """Il miglior prezzo di PUNTA dell'Under 2,5 nell'istante ``ms`` (la storia)."""
    m = (ms - KO_MS) / 60_000.0          # minuti dal fischio (negativi prima)
    if m < -64:
        return 1.50
    if m < -55:
        return 1.48
    if m < -40:
        # a scatti di un tick ogni 2 minuti: 1,49 ... 1,54
        passi = min(6, int((m + 55) // 2) + 1)
        return round(1.48 + 0.01 * passi, 2)
    if m < -30:
        return 1.52
    if m < 0:
        passi = min(12, int((m + 30) // 2) + 1)
        return round(1.52 + 0.01 * passi, 2)
    if ms < GOL_MS:
        # in gioco senza gol la quota scende piano (un tick ogni 3 minuti)
        return round(1.64 - 0.01 * int(m // 3), 2)
    # dopo il gol: 2,40 poi giu' di un tick (0,02) ogni minuto
    dopo = (ms - GOL_MS - SOSPENSIONE_MS) / 60_000.0
    return round(max(2.20, 2.40 - 0.02 * max(0, int(dopo))), 2)


def _scala(prezzo: float, verso: int, n: int) -> List[float]:
    out, p = [], prezzo
    for _i in range(n):
        out.append(round(p, 2))
        p = price_ticks_away(p, verso)
    return out


class Costruttore:
    def __init__(self) -> None:
        self.righe: List[str] = []
        self.versione = 1
        self.trd: Dict[Tuple[str, int], Dict[float, float]] = {}
        self.stato_prima: Optional[Tuple[str, bool]] = None

    def _scambia(self, mid: str, sid: int, prezzo: float, volume: float) -> None:
        tv = self.trd.setdefault((mid, sid), {})
        tv[round(prezzo, 2)] = tv.get(round(prezzo, 2), 0.0) + float(volume)

    def libro(self, mid: str, sid: int, back: float, flusso: float) -> Dict[str, Any]:
        lay = price_ticks_away(back, 1)
        if flusso:
            self._scambia(mid, sid, back, flusso)
            self._scambia(mid, sid, lay, flusso)
        riga: Dict[str, Any] = {
            "id": sid,
            "atb": [[p, PROFONDITA] for p in _scala(back, -1, LIVELLI)],
            "atl": [[p, PROFONDITA] for p in _scala(lay, 1, LIVELLI)],
        }
        tv = self.trd.get((mid, sid))
        if tv:
            riga["trd"] = [[p, round(v, 2)] for p, v in sorted(tv.items())]
            riga["ltp"] = back
            riga["tv"] = round(sum(tv.values()), 2)
        return riga

    def messaggio(self, ms: int) -> None:
        inplay = ms >= KO_MS
        sospeso = GOL_MS <= ms < GOL_MS + SOSPENSIONE_MS
        status = "SUSPENDED" if sospeso else "OPEN"
        if (status, inplay) != self.stato_prima:
            self.versione += 1
            self.stato_prima = (status, inplay)
        u = quota_under(ms)
        # il volume ai prezzi a cui la quota SCENDE: la banca appoggiata li' si abbina
        scende = {(-64, -63): 1.48, (-40, -39): 1.52}
        m = (ms - KO_MS) / 60_000.0
        mc = []
        for tipo, (mid, runners) in MERCATI.items():
            rc = []
            flusso = 0.0 if sospeso else 20.0
            for sid, sp in runners:
                if tipo == "MATCH_ODDS":
                    back = {1: 2.10, 2: 3.70, 3: 3.30}[sp]
                elif tipo == "OVER_UNDER_25":
                    back = u if sp == 1 else round(1.0 + 1.0 / (u - 1.0) - 0.06, 2)
                else:
                    base = max(1.15, round(u - 0.30, 2))
                    back = base if sp == 1 else round(1.0 + 1.0 / (base - 1.0) - 0.1, 2)
                from flumine.utils import get_nearest_price

                back = float(get_nearest_price(back))
                if tipo == "OVER_UNDER_25" and sp == 1:
                    for (a, z), prezzo in scende.items():
                        if a <= m < z:
                            self._scambia(mid, sid, prezzo, 150.0)
                rc.append(self.libro(mid, sid, back, flusso))
            mc.append({"id": mid, "img": True,
                       "marketDefinition": _md(tipo, status=status, inplay=inplay,
                                               versione=self.versione),
                       "rc": rc})
        self.righe.append(json.dumps({"op": "mcm", "id": 1, "clk": "C%d" % len(self.righe),
                                      "pt": int(ms), "mc": mc}))

    def scrivi(self, cartella: str) -> str:
        os.makedirs(cartella, exist_ok=True)
        path = os.path.join(cartella, "%s.raw.jsonl" % EVENTO)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(self.righe) + "\n")
        return path


def genera(data_dir: str, passo_ms: int = 1000) -> str:
    c = Costruttore()
    ms = INIZIO_MS
    while ms <= FINE_MS:
        c.messaggio(ms)
        ms += passo_ms
    return c.scrivi(os.path.join(data_dir, EVENTO))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-dir", default="_live_raw")
    a = ap.parse_args(argv)
    print(genera(a.data_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
