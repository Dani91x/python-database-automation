# -*- coding: utf-8 -*-
"""estrai_db - ESTRAZIONI IN SOLA LETTURA per la misura punto 8 (25/09/2026).

!!! LO LANCIA IL COORDINATORE, NON IL DELEGATO !!!  (regola dura del 21/09)

Solo ``select``: nessun insert/update/delete/upsert/rpc di scrittura. Ogni lettura
e' paginata con un ORDINE TOTALE:
  * keyset (``col > ultimo`` + ``order(col)``) dove esiste una colonna unica;
  * altrimenti a BLOCCHI di chiavi con ``in_()`` e controllo del tetto: se un
    blocco torna pieno (= potrebbe essere troncato) si DIMEZZA e si rilegge,
    mai una pagina a offset con ordine ambiguo (difetto misurato da M2 il
    17/09: 2.003 fixture lette invece di 2.018).
Ogni file d'uscita e' un .json.gz con le CHIAVI VERE delle tabelle.

Sottocomandi e file attesi (tutti in AUDIT_2026-09-25/misura_punto8_dati/):
  o1o6     quote Betfair Match Odds + Correct Score (run_date >= --da, default
           2026-09-09), esiti (`matches`), `fixture_predictions` (stesse colonne
           del campione M2), distribuzione di `omega_events.model.lambda_source`
           -> estr_o1o6.json.gz          (usato da o1_catena_lambda, o6_coda)
  o5       gol e rossi di `match_events` per le fixture del campione M2 e di
           estr_o1o6 -> estr_o5.json.gz   (usato da o5_rossi)
  m1       `markets_calibrated.over_3_5/over_4_5` + esiti su una finestra di date
           (+ formato delle chiavi, Q6) -> estr_m1.json.gz  (usato da m1_mike)
  mike_ev  p_under35_cal degli eventi del replay Mike (ponte event->fixture come
           la produzione: live_follow, poi omega_events) -> estr_mike_ev.json.gz
  t1       `tennis_markets.competition_name` degli eventi registrati
           -> estr_t1.json.gz             (usato da t1_superficie)
  x1       `direction_pagella` (globale), `ml_post_calibration`,
           `poisson_calibration`, e le righe `fixture_predictions` dei due eventi
           dello scalper -> estr_x1.json.gz (usato da x1_bias)

Uso (dal checkout principale, con il .env vero):
  python -m Betfair.stream.backtest.tools.misura_punto8.estrai_db o1o6 --out AUDIT_2026-09-25/misura_punto8_dati/estr_o1o6.json.gz
  ... (vedi il referto, sezione "Estrazioni da lanciare")
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import time
from datetime import date, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

PAGINA = 1000

# le stesse colonne (e alias) del campione M2: il lettore di O1 e' uno solo
SEL_FP = ("fixture_id,league_id,fixture_date,home_team_id,away_team_id,updated_at,"
          "lh:db_json_analisi->inputs->>lambda_home,"
          "la:db_json_analisi->inputs->>lambda_away,"
          "tlh:tactical_engine_json->>lambda_home,"
          "tla:tactical_engine_json->>lambda_away,"
          "l1h:ht_predictions->>lambda_1h,"
          "ph:percent_home,pd:percent_draw,pa:percent_away")
SEL_MATCH = ("fixture_id,league_id,season_year,fixture_date,status_short,"
             "goals_home,goals_away,halftime_home,halftime_away,"
             "home_team_id,away_team_id")


def _sb():
    from db_client import get_supabase_client
    return get_supabase_client()


TENTATIVI = 3          # su statement timeout (57014): 3 tentativi, pagina dimezzata
ATTESA_S = 2.0         # backoff: 2 s, 4 s, 8 s
_DORMI: Callable[[float], None] = time.sleep     # sostituibile nei test


def e_timeout(ex: BaseException) -> bool:
    """Lo statement timeout di Postgres (57014) come lo riporta postgrest-py."""
    return "57014" in str(getattr(ex, "code", "") or "") or "57014" in str(ex) \
        or "statement timeout" in str(ex).lower()


def esegui_con_ritentativi(costruisci: Callable[[int], Any], pagina: int) -> Tuple[List[dict], int]:
    """Esegue ``costruisci(pagina).execute()``; su 57014 aspetta (backoff
    esponenziale), DIMEZZA la pagina e riprova, fino a ``TENTATIVI`` volte.
    Ritorna (righe, pagina effettivamente usata). Ogni altro errore risale."""
    for i in range(TENTATIVI):
        try:
            return (getattr(costruisci(pagina).execute(), "data", None) or []), pagina
        except Exception as ex:  # noqa: BLE001 - si filtra sotto
            if not e_timeout(ex) or i == TENTATIVI - 1:
                raise
            _DORMI(ATTESA_S * (2 ** i))
            pagina = max(1, pagina // 2)
    raise RuntimeError("irraggiungibile")


def keyset(sb, tab: str, sel: str, chiave: str, filtri: Sequence[Callable] = (),
           pagina: int = PAGINA) -> List[dict]:
    """Paginazione KEYSET su una colonna UNICA (ordine totale per costruzione).
    Va usata SOLO dentro una finestra stretta (vedi ``keyset_per_giorno``): su
    una tabella grande filtrata per data, ``order(chiave)`` percorre l'indice
    della chiave e scarta milioni di righe -> 57014 (misurato il 25/09)."""
    fuori: List[dict] = []
    ultimo: Any = None
    while True:
        def costruisci(n: int, u: Any = ultimo):
            q = sb.table(tab).select(sel)
            for f in filtri:
                q = f(q)
            if u is not None:
                q = q.gt(chiave, u)
            return q.order(chiave).limit(n)
        righe, usata = esegui_con_ritentativi(costruisci, pagina)
        pagina = usata
        fuori.extend(righe)
        if len(righe) < pagina:
            return fuori
        ultimo = righe[-1][chiave]


def giorni(da: str, a: str) -> List[Tuple[str, str]]:
    """[(giorno, giorno+1)] ISO per ogni giorno in [da, a)."""
    d0 = date.fromisoformat(str(da)[:10])
    d1 = date.fromisoformat(str(a)[:10])
    out = []
    while d0 < d1:
        out.append((d0.isoformat(), (d0 + timedelta(days=1)).isoformat()))
        d0 += timedelta(days=1)
    return out


def keyset_per_giorno(sb, tab: str, sel: str, col_data: str, chiave: str, da: str, a: str,
                      filtri: Sequence[Callable] = (), pagina: int = PAGINA) -> List[dict]:
    """Un GIORNO di ``col_data`` alla volta (``gte(g) .lt(g+1)``: l'indice sulla
    data restringe a poche centinaia di righe), e dentro il giorno keyset su
    ``chiave``. Le finestre sono disgiunte e contigue: nessuna riga persa ne'
    duplicata."""
    fuori: List[dict] = []
    for g0, g1 in giorni(da, a):
        fuori.extend(keyset(sb, tab, sel, chiave,
                            list(filtri) + [lambda q, x=g0: q.gte(col_data, x),
                                            lambda q, x=g1: q.lt(col_data, x)],
                            pagina=pagina))
    return fuori


def a_blocchi(sb, tab: str, sel: str, colonna: str, valori: Iterable[Any],
              filtri: Sequence[Callable] = (), blocco: int = 200,
              tetto: int = PAGINA) -> List[dict]:
    """``in_(colonna, blocco)`` con controllo del TETTO: un blocco che torna con
    ``tetto`` righe potrebbe essere troncato -> si dimezza e si rilegge. Un blocco
    di UN solo valore ancora pieno e' un errore dichiarato (non si tronca in
    silenzio). Su 57014 il blocco si dimezza con backoff (``TENTATIVI``)."""
    v = sorted(set(valori))
    fuori: List[dict] = []
    coda = [v[i:i + blocco] for i in range(0, len(v), blocco)]
    timeout_di_fila = 0
    while coda:
        b = coda.pop(0)
        q = sb.table(tab).select(sel).in_(colonna, b)
        for f in filtri:
            q = f(q)
        try:
            righe = getattr(q.limit(tetto).execute(), "data", None) or []
        except Exception as ex:  # noqa: BLE001
            timeout_di_fila += 1
            if not e_timeout(ex) or timeout_di_fila >= TENTATIVI or len(b) == 1:
                raise
            _DORMI(ATTESA_S * (2 ** (timeout_di_fila - 1)))
            meta = len(b) // 2
            coda[:0] = [b[:meta], b[meta:]]
            continue
        timeout_di_fila = 0
        if len(righe) >= tetto:
            if len(b) == 1:
                raise RuntimeError(f"{tab}: {colonna}={b[0]} ha >= {tetto} righe, "
                                   f"serve una paginazione per quella chiave")
            meta = len(b) // 2
            coda[:0] = [b[:meta], b[meta:]]
            continue
        fuori.extend(righe)
    return fuori


def piccola(sb, tab: str, sel: str, filtri: Sequence[Callable] = (),
            tetto: int = 10000) -> List[dict]:
    """Tabella piccola letta in un colpo: se tocca il tetto si FERMA con errore."""
    q = sb.table(tab).select(sel)
    for f in filtri:
        q = f(q)
    righe = getattr(q.limit(tetto).execute(), "data", None) or []
    if len(righe) >= tetto:
        raise RuntimeError(f"{tab}: >= {tetto} righe, lettura in un colpo non sicura")
    return righe


def _scrivi(path: str, dati: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(dati, fh, default=str)
    print(f"scritto {path}: " + ", ".join(f"{k}={len(v)}" for k, v in dati.items()
                                           if isinstance(v, list)))


def _prezzo(liv: Any) -> Optional[float]:
    if isinstance(liv, str):
        try:
            liv = json.loads(liv)
        except ValueError:
            return None
    if not isinstance(liv, list) or not liv:
        return None
    try:
        p = float(liv[0].get("price"))
    except (TypeError, ValueError, AttributeError):
        return None
    return p if p > 1.0 else None


def quote_mo_formato_m2(righe_mo: Sequence[dict]) -> List[dict]:
    """Righe Match Odds di `betfair_market_odds` -> il formato `quote` di M2
    ({fixture_id, run_date, back_home, lay_home, ...}; sort_priority 1=casa,
    2=trasferta, 3=pareggio, come in `m2_pesi.estrai`)."""
    per: Dict[int, dict] = {}
    for r in righe_mo:
        fid = int(r["fixture_id"])
        d = per.setdefault(fid, {"fixture_id": fid, "run_date": r.get("run_date")})
        sp = r.get("sort_priority")
        lato = {1: "home", 2: "away", 3: "draw"}.get(int(sp) if sp is not None else 0)
        if lato:
            d[f"back_{lato}"] = _prezzo(r.get("back"))
            d[f"lay_{lato}"] = _prezzo(r.get("lay"))
    return list(per.values())


# ---------------------------------------------------------------------------
# sottocomandi
# ---------------------------------------------------------------------------
def estrai_o1o6(sb, da: str, a: str) -> dict:
    # un run_date alla volta; dentro il giorno fixture_id e' unico con
    # (market_name='Match Odds', sort_priority=1): keyset su fixture_id
    fids_rows = keyset_per_giorno(sb, "betfair_market_odds", "fixture_id,run_date",
                                  "run_date", "fixture_id", da, a,
                                  [lambda q: q.eq("market_name", "Match Odds"),
                                   lambda q: q.eq("sort_priority", 1)])
    fids = sorted({int(r["fixture_id"]) for r in fids_rows})
    mo = a_blocchi(sb, "betfair_market_odds",
                   "fixture_id,market_name,selection,sort_priority,back,lay,run_date",
                   "fixture_id", fids, [lambda q: q.eq("market_name", "Match Odds")])
    cs = a_blocchi(sb, "betfair_market_odds",
                   "fixture_id,market_name,selection,sort_priority,back,lay,run_date",
                   "fixture_id", fids, [lambda q: q.eq("market_name", "Correct Score")],
                   blocco=40)
    esiti = a_blocchi(sb, "matches", SEL_MATCH, "fixture_id", fids)
    fp = a_blocchi(sb, "fixture_predictions", SEL_FP, "fixture_id", fids)
    # omega_events NON ha created_at (42703 al lancio del 25/09): colonne vere
    # event_id, open_date, updated_at, fixture_id, league_id, model, ... Si
    # finestra sul giorno della partita (open_date).
    ev = keyset_per_giorno(sb, "omega_events",
                           "event_id,fixture_id,open_date,updated_at,src:model->>lambda_source",
                           "open_date", "event_id", "2026-09-01", a)
    return {"generato": "estrai_db o1o6", "da": da, "quote": quote_mo_formato_m2(mo),
            "quote_cs": cs, "esiti": esiti, "fixture_predictions": fp,
            "omega_events_lambda_source": ev}


def estrai_o5(sb, fids: Sequence[int]) -> dict:
    ev = a_blocchi(sb, "match_events",
                   "id,fixture_id,team_id,event_type,detail,minute,minute_extra",
                   "fixture_id", fids, [lambda q: q.in_("event_type", ["Goal", "Card"])],
                   blocco=40)
    return {"generato": "estrai_db o5", "eventi": ev}


def estrai_m1(sb, da: str, a: str) -> dict:
    sel = ("fixture_id,league_id,fixture_date,"
           "o35:db_json_analisi->markets_calibrated->over_3_5,"
           "o45:db_json_analisi->markets_calibrated->over_4_5,"
           "r35:db_json_analisi->markets->over_3_5,"
           "r45:db_json_analisi->markets->over_4_5")
    fp = keyset_per_giorno(sb, "fixture_predictions", sel, "fixture_date", "fixture_id", da, a)
    fids = [int(r["fixture_id"]) for r in fp]
    esiti = a_blocchi(sb, "matches", SEL_MATCH, "fixture_id", fids)
    # Q6: il FORMATO delle chiavi (5 righe intere di markets_calibrated, per chiave
    # primaria sulle fixture gia' lette: e' un campione da guardare, non da contare)
    campione_chiavi = a_blocchi(sb, "fixture_predictions",
                                "fixture_id,mc:db_json_analisi->markets_calibrated",
                                "fixture_id", sorted(fids)[-5:])
    return {"generato": "estrai_db m1", "da": da, "a": a, "fixture_predictions": fp,
            "esiti": esiti, "campione_markets_calibrated": campione_chiavi}


def estrai_mike_ev(sb, eventi: Sequence[str]) -> dict:
    ponte: Dict[str, Optional[int]] = {}
    for tab in ("live_follow", "omega_events"):
        mancanti = [e for e in eventi if ponte.get(e) is None]
        if not mancanti:
            break
        for r in a_blocchi(sb, tab, "event_id,fixture_id", "event_id", mancanti):
            if r.get("fixture_id") is not None and ponte.get(str(r["event_id"])) is None:
                ponte[str(r["event_id"])] = int(r["fixture_id"])
    fids = sorted({f for f in ponte.values() if f is not None})
    fp = a_blocchi(sb, "fixture_predictions",
                   "fixture_id,league_id,tactical_engine_json,db_json_analisi",
                   "fixture_id", fids, blocco=20)
    return {"generato": "estrai_db mike_ev", "ponte": [{"event_id": e, "fixture_id": ponte.get(e)}
                                                       for e in eventi],
            "fixture_predictions": fp}


def estrai_t1(sb, eventi: Sequence[str]) -> dict:
    tm = a_blocchi(sb, "tennis_markets",
                   "event_id,competition_id,competition_name,competition_region,open_date",
                   "event_id", eventi)
    return {"generato": "estrai_db t1", "tennis_markets": tm}


def estrai_x1(sb, eventi: Sequence[str], da: str, a: str) -> dict:
    pag = piccola(sb, "direction_pagella",
                  "engine,market,selection,league_id,prob_bucket,n,hits,hit_rate,base_rate,generated_at",
                  [lambda q: q.eq("league_id", 0)])
    mlc = piccola(sb, "ml_post_calibration", "*")
    poc = piccola(sb, "poisson_calibration", "*")
    ponte = estrai_mike_ev(sb, eventi)["ponte"]
    fids = [p["fixture_id"] for p in ponte if p["fixture_id"] is not None]
    fp = a_blocchi(sb, "fixture_predictions",
                   "fixture_id,league_id,fixture_date,created_at,updated_at,"
                   "model_predictions_json,db_json_analisi", "fixture_id", fids, blocco=5)
    # la CONCORDANZA ML/Poisson si misura partita per partita: le due mappe 1X2
    # (le stesse chiavi di `bias_resolver.extract_1x2`) + l'esito, su una finestra
    finestra = keyset_per_giorno(sb, "fixture_predictions",
                                 "fixture_id,league_id,fixture_date,"
                                 "ml:model_predictions_json->targets->target_1x2,"
                                 "ml_ft:model_predictions_json->targets->target_ft_1x2,"
                                 "po:db_json_analisi->markets->1x2",
                                 "fixture_date", "fixture_id", da, a)
    esiti = a_blocchi(sb, "matches", SEL_MATCH, "fixture_id",
                      [int(r["fixture_id"]) for r in finestra])
    return {"generato": "estrai_db x1", "direction_pagella": pag, "ml_post_calibration": mlc,
            "poisson_calibration": poc, "ponte": ponte, "fixture_predictions": fp,
            "finestra_1x2": finestra, "esiti": esiti, "da": da, "a": a}


def eventi_da_file(path: str) -> List[str]:
    """event_id da un JSON: dict con `per_evento` (t1_superficie) o lista di
    referti; accetta anche lo stdout intero di certifica (array JSON in coda)."""
    with open(path, "r", encoding="utf-8") as fh:
        testo = fh.read()
    try:
        dati = json.loads(testo)
    except ValueError:
        i = testo.rfind("\n[")
        dati = json.loads(testo[i + 1:])
    righe = dati.get("per_evento") if isinstance(dati, dict) else dati
    return sorted({str(r["event_id"]) for r in righe or [] if r.get("event_id") is not None})


def _fids_da(files: Sequence[str]) -> List[int]:
    out = set()
    for f in files:
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            d = json.load(fh)
        out |= {int(q["fixture_id"]) for q in d.get("quote") or []}
    return sorted(out)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="estrazioni in SOLA LETTURA (le lancia il coordinatore)")
    ap.add_argument("cosa", choices=["o1o6", "o5", "m1", "mike_ev", "t1", "x1"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--da", default="2026-09-09")
    ap.add_argument("--a", default="2026-09-26")
    ap.add_argument("--campioni", nargs="*", default=[],
                    help="o5: file con 'quote' da cui prendere le fixture (M2 + estr_o1o6)")
    ap.add_argument("--eventi", nargs="*", default=[], help="mike_ev/t1/x1: event_id Betfair")
    ap.add_argument("--eventi-file", default=None,
                    help="event_id da un file: l'uscita di t1_superficie (per_evento) o "
                         "lo stdout di `certifica mike ... --json` (array in coda)")
    a = ap.parse_args(argv)
    if a.eventi_file:
        a.eventi = list(a.eventi) + eventi_da_file(a.eventi_file)
    sb = _sb()
    if a.cosa == "o1o6":
        dati = estrai_o1o6(sb, a.da, a.a)
    elif a.cosa == "o5":
        dati = estrai_o5(sb, _fids_da(a.campioni))
    elif a.cosa == "m1":
        dati = estrai_m1(sb, a.da, a.a)
    elif a.cosa == "mike_ev":
        dati = estrai_mike_ev(sb, a.eventi)
    elif a.cosa == "t1":
        dati = estrai_t1(sb, a.eventi)
    else:
        dati = estrai_x1(sb, a.eventi, a.da, a.a)
    _scrivi(a.out, dati)
    return 0


if __name__ == "__main__":
    sys.exit(main())
