"""SONDA R9 (02/10/2026): un mercato ESPOSTO risolto su un evento SENZA book
viene richiesto a Betfair ogni 20 s?

Dati veri, sola lettura: la registrazione ``35760084`` (``--data-dir`` =
``_live_raw`` del checkout principale). Da li' gli id, i tipi, l'orario e gli
stati VERI dei mercati (marketDefinition). Lo scanner e' quello di produzione
(``Scanner`` in dry, nessuna rete): si rifa' cio' che fa il ``tick`` ogni 20 s
(catalogo CS dei candidati, poi ``refresh_mercati_esposti``), e il Match Odds
dell'evento arriva allo scanner SOLO quando e' rilevante come in produzione
(``scanner.is_relevant_market``: KO entro 20', in gioco). Esposizione
dichiarata: Omega sul Correct Score dell'evento dall'inizio della registrazione
(posizione pre-partita). Un secondo evento (finto, "ALTRA") e' in gioco al 35'
per tutto il tempo: e' il caso normale di un pomeriggio con partite in corso,
che fa girare ``refresh_cs_catalogue``.

Uso: <python> AUDIT_2026-10-02/sonda_r9.py --data-dir <principale>/_live_raw
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, RADICE)

from Betfair.safe_strategy import scanner  # noqa: E402
from Betfair.safe_strategy import service as S  # noqa: E402

EVENTO = "35760084"


def _leggi(data_dir: str):
    path = os.path.join(data_dir, EVENTO, f"{EVENTO}.raw.jsonl")
    defs = {}          # market_id -> ultima definizione
    storia = []        # (pt, market_id, status, inPlay)
    with open(path, encoding="utf-8") as f:
        for riga in f:
            msg = json.loads(riga)
            for mc in msg.get("mc") or []:
                d = mc.get("marketDefinition")
                if d:
                    defs[mc["id"]] = d
                    storia.append((msg["pt"], mc["id"], d.get("status"), d.get("inPlay")))
    return defs, storia


def _cat(mid, d, nome="A v B"):
    return SimpleNamespace(
        event=SimpleNamespace(id=d["eventId"], name=nome), market_id=mid, market_name=None,
        description=SimpleNamespace(market_type=d["marketType"]),
        runners=[SimpleNamespace(selection_id=r["id"], runner_name=str(r["id"]), sort_priority=i)
                 for i, r in enumerate(d.get("runners") or [], 1)],
        market_start_time=datetime.fromisoformat(d["marketTime"].replace("Z", "+00:00")),
        competition=SimpleNamespace(name="?"),
    )


class _Betting:
    def __init__(self, defs):
        self.defs = defs
        self.chiamate = []

    def list_market_catalogue(self, **kw):
        f = kw["filter"]
        self.chiamate.append(f)
        out = []
        for mid, d in self.defs.items():
            if d.get("status") == "CLOSED":
                continue          # listMarketCatalogue non restituisce i CLOSED
            if f.get("marketIds") and mid not in f["marketIds"]:
                continue
            if f.get("eventIds") and d["eventId"] not in f["eventIds"]:
                continue
            if f.get("marketTypeCodes") and d["marketType"] not in f["marketTypeCodes"]:
                continue
            out.append(_cat(mid, d))
        return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    a = ap.parse_args()
    defs_finali, storia = _leggi(a.data_dir)
    mo = next(m for m, d in defs_finali.items() if d["marketType"] == "MATCH_ODDS")
    cs = next(m for m, d in defs_finali.items() if d["marketType"] == "CORRECT_SCORE")
    ko = defs_finali[mo]["marketTime"]
    betting = _Betting({})
    scan = S.Scanner(SimpleNamespace(betting=betting), dry=True, use_stream=False)
    scan.pre_ko_ou_hours = 0.0
    scan.sports["calcio"].catalogue_ts = scan.sports["tennis"].catalogue_ts = 1.0
    scan.sports["calcio"].metas = {
        EVENTO: {"event_id": EVENTO, "market_id": mo, "event_name": "A v B", "open_date": ko,
                 "competition": "?", "runners": [], "sides": {"home": 1, "away": 2, "draw": 3}},
        "ALTRA": {"event_id": "ALTRA", "market_id": "1.ALTRA", "event_name": "C v D",
                  "open_date": ko, "competition": "?", "runners": [], "sides": {}},
    }
    scan.events["ALTRA"] = {"sport": "calcio", "inplay": True, "mo_status": "OPEN",
                            "minute": 35, "score_home": 0, "score_away": 0}
    scan._rebuild_market_index()
    scan._esposizioni_fonti = {"omega": [{"event_id": EVENTO, "market_id": cs,
                                          "sport": "calcio", "bot": "omega"}]}
    t0, t1 = storia[0][0], storia[-1][0]
    stato = {}
    i = 0
    passo_ms = 20_000
    per_fase = {"senza_book": [0, 0], "con_book": [0, 0]}
    t = t0
    while t <= t1:
        while i < len(storia) and storia[i][0] <= t:
            _, mid, st, ip = storia[i]
            stato[mid] = (st, ip)
            i += 1
        betting.defs = {m: {**defs_finali[m], "status": stato.get(m, (None,))[0]}
                        for m in defs_finali if m in stato}
        adesso = datetime.fromtimestamp(t / 1000, tz=timezone.utc)
        st_mo, ip_mo = stato.get(mo, (None, False))
        ev = scan.events.get(EVENTO)
        rilevante = scanner.is_relevant_market(None if ev is None else bool(ip_mo), st_mo, ko, adesso)
        if rilevante:          # in produzione: stream/REST del Match Odds
            scan._apply_market_book(SimpleNamespace(
                market_id=mo, status=st_mo, inplay=bool(ip_mo), bet_delay=0, total_matched=0.0,
                runners=[]))
        prima = len([c for c in betting.chiamate if c.get("marketIds")])
        # cio' che il tick fa ogni 20 s
        scan._safe_catalogue("correct score", scan.refresh_cs_catalogue, scan.cs_candidates())
        scan.refresh_mercati_esposti(now_mono=t / 1000.0)
        dopo = len([c for c in betting.chiamate if c.get("marketIds")])
        fase = "con_book" if EVENTO in scan.events else "senza_book"
        per_fase[fase][0] += 1
        per_fase[fase][1] += dopo - prima
        t += passo_ms
    righe = [
        f"registrazione {EVENTO}: {datetime.fromtimestamp(t0/1000, tz=timezone.utc)} -> "
        f"{datetime.fromtimestamp(t1/1000, tz=timezone.utc)}, KO previsto {ko}",
        f"esposto: Omega su CORRECT_SCORE {cs}; Match Odds {mo}",
        f"giri da 20 s SENZA book dell'evento: {per_fase['senza_book'][0]}, "
        f"chiamate marketIds: {per_fase['senza_book'][1]}",
        f"giri da 20 s CON book dell'evento: {per_fase['con_book'][0]}, "
        f"chiamate marketIds: {per_fase['con_book'][1]}",
        f"CS nella cache alla fine: {EVENTO in scan.cs_markets}",
    ]
    print("\n".join(righe))
    return 0


if __name__ == "__main__":
    sys.exit(main())
