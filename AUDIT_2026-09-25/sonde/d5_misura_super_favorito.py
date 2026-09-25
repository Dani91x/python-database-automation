"""D5 punto 7 (25/09) - MISURA del «super favorito» (quota back PRE-PARTITA del
favorito < 1,20 -> l'avversario e' uno «sfavorito estremo»).

SOLA LETTURA, nessuna scrittura. Tre fonti, dichiarate:
  A. TENNIS - registrazioni Betfair locali (~/Desktop/tennis_rec/*/<id>/<id>.raw.jsonl):
     quota pre-partita = miglior back dell'ultimo aggiornamento PRIMA del primo
     `inPlay: true`; vincitore = `runners[].status == WINNER` della definizione
     finale. Solo le registrazioni che contengono il pre-partita.
  B. TENNIS - DB `tennis_markets` (righe `inplay = false`, singolari): la
     DISTRIBUZIONE delle quote pre-partita del favorito (niente esito nel DB:
     la tabella non ha il vincitore). Pagine da 1000, al massimo MAX_PAGINE.
  C. CALCIO - DB `fixture_predictions` (status ok, esito noto): quota 1X2 del
     bookmaker (`raw_json_odds.bookmakers[0].bets[0]` = «Match Winner») ed
     esito `result_outcome` (H/D/A). Pagine da 1000, al massimo MAX_PAGINE.

Stampa, per soglia (1,10 / 1,15 / 1,20 / 1,25 / 1,30): quante partite hanno il
favorito sotto soglia e quante volte il favorito NON ha vinto (rimonta).
"""
from __future__ import annotations

import glob
import json
import os
import sys
from typing import Dict, List, Optional, Tuple

SOGLIE = (1.10, 1.15, 1.20, 1.25, 1.30)
MAX_PAGINE = 24


def _tab(nome: str, righe: List[Tuple[float, Optional[bool]]]) -> None:
    """righe = (quota del favorito, il favorito ha vinto? None = esito ignoto)."""
    n = len(righe)
    print(f"\n== {nome}: {n} partite")
    if not n:
        return
    q = sorted(r[0] for r in righe)
    print("   quantili quota favorito: p10 %.2f  p25 %.2f  p50 %.2f  p75 %.2f  p90 %.2f"
          % tuple(q[int(p * (n - 1))] for p in (0.10, 0.25, 0.50, 0.75, 0.90)))
    for s in SOGLIE:
        sotto = [r for r in righe if r[0] < s]
        noti = [r for r in sotto if r[1] is not None]
        persi = [r for r in noti if r[1] is False]
        quota_media = sum(r[0] for r in sotto) / len(sotto) if sotto else 0.0
        implicito = (1.0 - 1.0 / quota_media) if quota_media else 0.0
        esito = (f"favorito NON vince {len(persi)}/{len(noti)} = "
                 f"{100.0 * len(persi) / len(noti):.1f}%" if noti else "esito non disponibile")
        print(f"   fav < {s:.2f}: {len(sotto)} ({100.0 * len(sotto) / n:.1f}%)  "
              f"quota media {quota_media:.3f} (sconfitta implicita {100 * implicito:.1f}%)  {esito}")


def tennis_registrazioni() -> List[Tuple[float, Optional[bool]]]:
    radice = os.path.join(os.path.expanduser("~"), "Desktop", "tennis_rec")
    out: List[Tuple[float, Optional[bool]]] = []
    for f in sorted(glob.glob(os.path.join(radice, "*", "*", "*.raw.jsonl"))):
        # scala COMPLETA per corridore (i messaggi sono delta: prezzo -> size)
        scala: Dict[int, Dict[float, float]] = {}
        best: Dict[int, float] = {}
        pre: Optional[Dict[int, float]] = None
        visto_pre = False
        vincitore: Optional[int] = None
        doppio = False
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                try:
                    m = json.loads(line)
                except ValueError:
                    continue
                for mc in m.get("mc") or []:
                    md = mc.get("marketDefinition")
                    if md is not None:
                        if md.get("marketType") != "MATCH_ODDS":
                            continue
                        if md.get("inPlay") and pre is None and visto_pre:
                            pre = dict(best)
                        if not md.get("inPlay"):
                            visto_pre = True
                        for r in md.get("runners") or []:
                            if r.get("status") == "WINNER":
                                vincitore = int(r["id"])
                    for rc in mc.get("rc") or []:
                        atb = rc.get("atb")
                        if atb:
                            lad = scala.setdefault(int(rc["id"]), {})
                            if mc.get("img") or m.get("ct") == "SUB_IMAGE":
                                pass
                            for p, s in atb:
                                if s and s > 0:
                                    lad[float(p)] = float(s)
                                else:
                                    lad.pop(float(p), None)
                            # 1,01 con pochi euro e' la quota "di cortesia": non e' il prezzo
                            validi = [p for p, s in lad.items() if p > 1.01 or s >= 50]
                            if validi:
                                best[int(rc["id"])] = max(validi)
        del doppio
        if pre is None or len(pre) != 2 or vincitore is None:
            continue
        fav_id = min(pre, key=lambda k: pre[k])
        out.append((pre[fav_id], fav_id == vincitore))
    return out


def _client():
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", ".env"))
    from supabase import create_client

    return create_client(os.environ["SUPABASE_URL"],
                         os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_KEY"])


def _best_back(p: dict) -> Optional[float]:
    backs = [b.get("price") for b in (p or {}).get("back") or []
             if isinstance(b, dict) and (b.get("size") or 0) > 0]
    backs = [float(x) for x in backs if x]
    return max(backs) if backs else None


def tennis_db(sb) -> Tuple[List[Tuple[float, Optional[bool]]], int]:
    out: List[Tuple[float, Optional[bool]]] = []
    letture = 0
    for pag in range(MAX_PAGINE):
        r = (sb.table("tennis_markets").select("event_id,player1,player2,total_matched")
             .eq("inplay", False).gte("run_date", "2026-07-15")
             .order("run_date").range(pag * 1000, pag * 1000 + 999).execute().data)
        letture += 1
        for x in r:
            p1, p2 = x.get("player1") or {}, x.get("player2") or {}
            if "/" in str(p1.get("name")) or "/" in str(p2.get("name")):
                continue  # doppi esclusi dalla strategia
            if float(x.get("total_matched") or 0) < 100:
                continue  # prezzo senza mercato (1,01 / 1000 di cortesia)
            a, b = _best_back(p1), _best_back(p2)
            if a is None or b is None or a <= 1.0 or b <= 1.0:
                continue
            # libro sensato: somma delle probabilita' implicite fra 0,95 e 1,10
            if not 0.95 <= 1.0 / a + 1.0 / b <= 1.10:
                continue
            out.append((min(a, b), None))
        if len(r) < 1000:
            break
    return out, letture


def calcio_db(sb) -> Tuple[List[Tuple[float, Optional[bool]]], int]:
    out: List[Tuple[float, Optional[bool]]] = []
    letture = 0
    for pag in range(MAX_PAGINE):
        r = (sb.table("fixture_predictions")
             .select("fixture_id,result_outcome,mw:raw_json_odds->bookmakers->0->bets->0")
             .eq("status", "ok").not_.is_("result_outcome", "null")
             .gte("fixture_date", "2026-08-10").lt("fixture_date", "2026-09-24")
             .order("fixture_date").range(pag * 500, pag * 500 + 499).execute().data)
        letture += 1
        for x in r:
            mw = x.get("mw") or {}
            if not isinstance(mw, dict) or mw.get("name") != "Match Winner":
                continue
            q = {v.get("value"): v.get("odd") for v in mw.get("values") or [] if isinstance(v, dict)}
            try:
                h, a = float(q["Home"]), float(q["Away"])
            except (KeyError, TypeError, ValueError):
                continue
            esito = str(x.get("result_outcome") or "").upper()
            if esito not in ("H", "D", "A"):
                continue
            fav = "H" if h <= a else "A"
            out.append((min(h, a), esito == fav))
        if len(r) < 500:
            break
    return out, letture


if __name__ == "__main__":
    _tab("A. TENNIS registrazioni Betfair (esito osservato)", tennis_registrazioni())
    if "--solo-locale" in sys.argv:
        sys.exit(0)
    sb = _client()
    righe, n = tennis_db(sb)
    _tab(f"B. TENNIS tennis_markets pre-partita dal 15/07 (solo distribuzione; {n} letture)", righe)
    righe, n = calcio_db(sb)
    _tab(f"C. CALCIO fixture_predictions 10/08-23/09 (1X2 bookmaker + esito; {n} letture)", righe)
