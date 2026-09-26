"""sonda_automode_safe_checklist.py - E2E FASE 2 (26/09), voce 7.9.7.C (referto ADMIN26_AUTOMODE_SAFE).

SOLA LETTURA. Per ogni INGRESSO automatico Safe di oggi (safe_strategy_trades origin='auto') e per ogni
SCARTO scritto dal bot (safe_strategy_activity kind='skip'), ricostruisce la riga del feed dello STESSO
ISTANTE dalla registrazione del canale 47336 fatta da sonda_automode_ascolto.py (scan_raw_*.jsonl.gz,
riga con updated_at = meta.tempi.t1_feed_ms del trade, altrimenti l'ultima <= istante della decisione) e
ricalcola in modo indipendente con le funzioni di PRODUZIONE importate:
  - engine.build_football_ctx_from_scan / build_tennis_ctx_from_scan + evaluate_* (tutti i check tranne
    la stabilita' del punteggio, che dipende dalla storia: data per vera e verificata a parte dal motore
    indipendente di sonda_automode_ascolto.py, che ha emesso lo stesso segnale)
  - veto_campionati.voce_vietata / squadra_femminile / is_round_finale / nome_indica_finale
  - h2h: fixture_predictions.raw_json (GET, stessa fonte dello scanner) + selezione.conta_scontri_diretti
    e gol subiti ultime 5, confrontati con selection_hint della riga
  - tennis: engine.tennis_sfavorito_estremo_check sulla pre_ko della riga
  - gate spread: bot_service.prices_from_row + exits.spread_ratio (max_spread_ratio dei params)
Stampa una riga per candidato con esito CONCORDA / DIVERGE e i dettagli; scrive anche JSON.
Uso: python sonda_automode_safe_checklist.py <dal_iso_utc> [<scan_raw.gz> ...]
"""
import glob
import gzip
import json
import sys
from datetime import datetime
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RADICE))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sonda_automode_db as DB  # noqa: E402
from Betfair.safe_strategy import engine as E  # noqa: E402
from Betfair.safe_strategy import veto_campionati as V  # noqa: E402
from Betfair.safe_strategy import selezione as SEL  # noqa: E402
from Betfair.safe_strategy import exits as XE  # noqa: E402
from Betfair.safe_strategy import bot_service as BS  # noqa: E402  (solo funzioni pure lette)

SCRATCH = r"C:\Users\Admin\AppData\Local\Temp\claude\C--Users-Admin\c122eed7-7d1e-4bc1-980e-b620a1c006ce\scratchpad\automode"
OUT = Path(__file__).resolve().parent / "automode_safe"


def ms(iso):
    return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp() * 1000.0


def carica_raw(files):
    idx = {}
    for fn in files:
        try:
            with gzip.open(fn, "rt", encoding="utf-8") as f:
                for line in f:
                    try:
                        r = json.loads(line)
                    except Exception:
                        break  # coda troncata del file ancora aperto
                    d = r.get("d") or {}
                    ev = str(d.get("event_id") or "")
                    if not ev or not d.get("updated_at"):
                        continue
                    idx.setdefault(ev, []).append((ms(d["updated_at"]), r["ts_ms"], d))
        except EOFError:
            pass
    for v in idx.values():
        v.sort(key=lambda x: x[0])
    return idx


def riga_a(idx, ev, t_ms, esatto_ms=None):
    rs = idx.get(str(ev)) or []
    if esatto_ms is not None:
        best = min(rs, key=lambda x: abs(x[0] - esatto_ms), default=None)
        if best is not None and abs(best[0] - esatto_ms) <= 5:
            return best[2], "esatta (updated_at = t1_feed_ms)"
    cand = [x for x in rs if x[0] <= t_ms]
    if cand:
        return cand[-1][2], "ultima <= istante (%.0f ms prima)" % (t_ms - cand[-1][0])
    return None, "non registrata"


_h2h_cache = {}


def h2h_indipendente(fid):
    if fid in _h2h_cache:
        return _h2h_cache[fid]
    r = DB.get("fixture_predictions?select=fixture_id,h2h:raw_json->response->0->h2h,"
               "ch:raw_json->response->0->teams->home->last_5->goals->against->>average,"
               "ca:raw_json->response->0->teams->away->last_5->goals->against->>average,"
               "th:raw_json->response->0->teams->home->>name,ta:raw_json->response->0->teams->away->>name"
               f"&fixture_id=eq.{int(fid)}&limit=1")
    out = None
    if r:
        x = r[0]
        c = SEL.conta_scontri_diretti(x.get("h2h"), escludi_fixture=int(fid))
        out = {"conta": c, "conceded": {"home": x.get("ch"), "away": x.get("ca")},
               "squadre_api": [x.get("th"), x.get("ta")]}
    _h2h_cache[fid] = out
    return out


def verifica_calcio(row, params, variant, sub_id):
    p = row.get("payload") or {}
    ctx = E.build_football_ctx_from_scan(str(row["event_id"]), p, p.get("minute"), 10 ** 6)
    pm = E.merge_params(params)
    if variant == "base":
        ev = E.evaluate_base(ctx, pm["base"])
    elif variant == "esatto":
        ev = E.evaluate_esatto(ctx, pm["esatto"], sub_id)
    else:
        ev = E.evaluate_punta(ctx, pm["punta"], pm["base"])
    ind = {}
    comp = p.get("competition")
    voce = V.voce_vietata(comp) if comp else None
    ind["veto_competizione"] = None if voce is None else V.motivo(voce)
    ind["femminile_nome_squadra"] = bool(V.squadra_femminile(ctx.home) or V.squadra_femminile(ctx.away))
    ind["round"] = p.get("fixture_round")
    ind["finale_round"] = bool(p.get("fixture_round") and V.is_round_finale(p.get("fixture_round")))
    ind["finale_nome"] = bool(not p.get("fixture_round") and V.nome_indica_finale(p.get("event_name")))
    hint = p.get("selection_hint") if isinstance(p.get("selection_hint"), dict) else None
    if hint and hint.get("fixture_id"):
        h = h2h_indipendente(hint["fixture_id"])
        ind["h2h_hint"] = [hint.get("h2h_meetings"), hint.get("h2h_many_goals"), hint.get("conceded")]
        ind["h2h_db"] = h
        if h and h.get("conta"):
            ok_cnt = (h["conta"]["incontri"] == hint.get("h2h_meetings")
                      and h["conta"]["tanti_gol"] == hint.get("h2h_many_goals"))
            ind["h2h_hint_uguale_db"] = ok_cnt
    ind["checks_non_ok"] = [[c.id, c.ok, c.value] for c in ev.checks if c.ok is not True]
    return ev, ind


def verifica_tennis(row, params):
    p = row.get("payload") or {}
    ctx = E.build_tennis_ctx_from_scan(str(row["event_id"]), p, 10 ** 6)
    pm = E.merge_params(params)
    ev = E.evaluate_tennis(ctx, pm["tennis"])
    ind = {"pre_ko": p.get("pre_ko"), "checks_non_ok": [[c.id, c.ok, c.value] for c in ev.checks
                                                         if c.ok is not True]}
    pre = E._tennis_pre_match(p.get("pre_ko"))
    if pre:
        sets = p.get("sets") or {}
        leader = 1 if (sets.get("p1") or 0) > (sets.get("p2") or 0) else 2
        ind["sfavorito_estremo"] = E.tennis_sfavorito_estremo_check(
            pre, leader, float(pm["tennis"]["favSuperMax"]), "x").ok
    return ev, ind


def spread(row, market_type, sel, market_id):
    fp = BS.prices_from_row(row, market_type=market_type, selection_id=int(sel), market_id=market_id)
    return fp, XE.spread_ratio(fp)


def main(dal, files):
    idx = carica_raw(files or sorted(glob.glob(SCRATCH + r"\scan_raw_*.jsonl.gz")))
    ctl = DB.get("safe_strategy_control?select=params&limit=1")[0]["params"]
    max_spread = float(ctl.get("max_spread_ratio") or 1.6)
    trades = DB.get("safe_strategy_trades?select=id,event_id,event_name,sport,strategy,side,price,size,"
                    "market_id,market_type,selection_id,signal_key,placed_at,status,origin,mode,meta"
                    f"&placed_at=gte.{dal}&origin=eq.auto&order=id.asc&limit=500")
    risultati = []
    for t in trades:
        meta = t.get("meta") or {}
        tempi = meta.get("tempi") or {}
        t3 = tempi.get("t3_deciso_ms") or ms(t["placed_at"])
        row, come = riga_a(idx, t["event_id"], t3, tempi.get("t1_feed_ms"))
        rec = {"tipo": "ingresso", "trade_id": t["id"], "event_id": t["event_id"],
               "event_name": t["event_name"], "variant": meta.get("variant") or t["strategy"],
               "signal_key": t["signal_key"], "price": t["price"], "placed_at": t["placed_at"],
               "riga": come}
        if row is None:
            rec["esito"] = "NON RICOSTRUIBILE (riga non registrata)"
            risultati.append(rec)
            continue
        rec["riga_updated_at"] = row.get("updated_at")
        if t["sport"] == "tennis":
            ev, ind = verifica_tennis(row, ctl)
        else:
            sub = t["signal_key"].split(":")[2] if t["strategy"] == "esatto" else None
            ev, ind = verifica_calcio(row, ctl, t["strategy"], sub)
        fp, ratio = spread(row, t["market_type"], t["selection_id"], t["market_id"])
        rec.update({"stato_ricalcolato": ev.state, "entry_ricalcolata": ev.entry_odds,
                    "indipendenti": ind, "spread": ratio, "prezzi_feed": fp})
        diverge = []
        if ev.state != "signal":
            diverge.append("ricalcolo != signal")
        if ev.entry_odds is not None and abs(float(ev.entry_odds) - float(t["price"])) > 1e-9:
            diverge.append("prezzo ingresso %s != entry ricalcolata %s" % (t["price"], ev.entry_odds))
        if ind.get("veto_competizione") or ind.get("femminile_nome_squadra") or ind.get("finale_round") \
                or ind.get("finale_nome"):
            diverge.append("veto violato")
        if ind.get("h2h_hint_uguale_db") is False:
            diverge.append("h2h del feed diverso dal DB")
        if ind.get("sfavorito_estremo") is False:
            diverge.append("sfavorito estremo non escluso")
        if ratio is None or ratio > max_spread:
            diverge.append("spread %s oltre %s" % (ratio, max_spread))
        rec["esito"] = "DIVERGE: " + "; ".join(diverge) if diverge else "CONCORDA"
        risultati.append(rec)

    skips = DB.get("safe_strategy_activity?select=ts,kind,payload&kind=eq.skip"
                   f"&ts=gte.{dal}&order=ts.asc&limit=3000")
    visti = set()
    for s in skips:
        pl = s.get("payload") or {}
        motivo = pl.get("reason")
        key = pl.get("signal_key")
        k = (pl.get("event_id"), key, motivo)
        if k in visti:
            continue
        visti.add(k)
        t_ms = ms(s["ts"])
        row, come = riga_a(idx, pl.get("event_id"), t_ms)
        rec = {"tipo": "scarto", "ts": s["ts"], "event_id": pl.get("event_id"), "signal_key": key,
               "motivo": motivo, "riga": come}
        if row is None:
            rec["esito"] = "NON RICOSTRUIBILE (riga non registrata)"
            risultati.append(rec)
            continue
        p = row.get("payload") or {}
        verdetto = None
        if motivo == "pre_ko_assente":
            verdetto = p.get("pre_ko") in (None, {}) and p.get("inplay") is True
            rec["dato"] = {"pre_ko": p.get("pre_ko"), "inplay": p.get("inplay")}
        elif motivo in ("spread_anomalo", "book_senza_lato_back", "book_senza_lato_lay"):
            parti = (key or "").split(":")
            var = parti[1] if len(parti) > 1 else ""
            if var == "esatto":
                blk = (p.get("cs") or {}).get("any_other_home" if parti[2] == "home" else "any_other_away") or {}
                fp, ratio = spread(row, "CORRECT_SCORE", blk.get("selection_id") or 0,
                                   (p.get("cs") or {}).get("market_id"))
            else:
                fp, ratio = None, None
            rec["dato"] = {"prezzi": fp, "ratio": ratio, "max": max_spread,
                           "bot": {k2: pl.get(k2) for k2 in ("back", "lay", "spread_ratio")}}
            if motivo == "spread_anomalo":
                verdetto = ratio is not None and ratio > max_spread
            else:
                verdetto = ratio is None
        elif motivo == "variante_non_abilitata":
            verdetto = None
            rec["dato"] = "dipende dai params del momento (variants), vedi _params_safe in bot_msgs"
        elif motivo == "minuto_ingresso_oltre_uscita":
            verdetto = int(pl.get("minuto")) >= int(pl.get("minuto_uscita"))
            rec["dato"] = {"minuto_feed": p.get("minute"), "bot": [pl.get("minuto"), pl.get("minuto_uscita")]}
        else:
            rec["dato"] = pl
        rec["esito"] = ("CONCORDA" if verdetto is True else "DIVERGE" if verdetto is False
                        else "non ricalcolato")
        risultati.append(rec)
    # MANCATI INGRESSI: per OGNI partita calcio registrata, i dati della selezione (h2h, difesa)
    # e i veti ricalcolati in modo indipendente sull'ultima riga, contro il check del motore.
    pm = E.merge_params(ctl)
    for ev, lst in sorted(idx.items()):
        d = lst[-1][2]
        if d.get("sport") != "calcio":
            continue
        p = d.get("payload") or {}
        ctx = E.build_football_ctx_from_scan(ev, p, p.get("minute"), 10 ** 6)
        rec = {"tipo": "selezione_partita", "event_id": ev, "event_name": p.get("event_name"),
               "competition": p.get("competition"), "riga_updated_at": d.get("updated_at")}
        vc = E.campionato_check(ctx.competition, pm["esatto"], home=ctx.home, away=ctx.away,
                                fixture_round=ctx.fixture_round, event_name=ctx.event_name)
        fem = bool(V.squadra_femminile(ctx.home) or V.squadra_femminile(ctx.away))
        voce = V.voce_vietata(ctx.competition) if ctx.competition else None
        atteso_veto = bool(fem or voce is not None or (ctx.fixture_round and V.is_round_finale(ctx.fixture_round))
                           or (not ctx.fixture_round and V.nome_indica_finale(ctx.event_name)))
        rec["veto_motore"] = None if vc is None else [vc.ok, vc.value]
        rec["veto_atteso"] = atteso_veto
        div = []
        if atteso_veto and (vc is None or vc.ok is not False):
            div.append("veto atteso ma il check del motore non scarta")
        if not atteso_veto and vc is not None and vc.ok is False:
            div.append("il motore scarta ma nessun veto indipendente")
        hint = p.get("selection_hint") if isinstance(p.get("selection_hint"), dict) else None
        if hint and hint.get("fixture_id"):
            h = h2h_indipendente(hint["fixture_id"])
            rec["h2h_hint"] = [hint.get("h2h_meetings"), hint.get("h2h_many_goals"), hint.get("conceded")]
            rec["h2h_db"] = h
            if h and h.get("conta") is not None and (
                    h["conta"]["incontri"] != hint.get("h2h_meetings")
                    or h["conta"]["tanti_gol"] != hint.get("h2h_many_goals")):
                div.append("h2h hint != DB")
            if h:
                for lato in ("home", "away"):
                    try:
                        a = None if h["conceded"][lato] is None else float(h["conceded"][lato])
                    except (TypeError, ValueError):
                        a = None
                    b = (hint.get("conceded") or {}).get(lato)
                    if a != (None if b is None else float(b)):
                        div.append("gol subiti %s: hint %s != DB %s" % (lato, b, a))
        else:
            rec["h2h_hint"] = "assente"
        rec["esito"] = "DIVERGE: " + "; ".join(div) if div else "CONCORDA"
        risultati.append(rec)
    OUT.mkdir(exist_ok=True)
    (OUT / "safe_checklist_esito.json").write_text(json.dumps(risultati, indent=1, ensure_ascii=False,
                                                              default=str), encoding="utf-8")
    for r in risultati:
        print(json.dumps({k: r.get(k) for k in ("tipo", "trade_id", "ts", "placed_at", "event_id",
                                                "event_name", "signal_key", "motivo", "price", "riga",
                                                "esito")}, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "2026-09-26T09:13:00Z", sys.argv[2:])
