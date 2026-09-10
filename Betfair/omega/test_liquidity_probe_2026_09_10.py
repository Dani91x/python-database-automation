"""Test del report di liquidità (certificazione 10/09/2026): estrazione dal
payload del feed, copertura lay, persistenza, green-up. Solo report, nessun poller."""
from __future__ import annotations

from pathlib import Path

from Betfair.omega import liquidity_probe as LP


def _sel(sid, name, lay, ls, back, bs, st="ACTIVE"):
    return {"selection_id": sid, "name": name, "lay": lay, "lay_size": ls,
            "back": back, "back_size": bs, "runner_status": st}


def _payload(sh, sa, minute, cs, ht=None, inplay=True):
    p = {"event_name": "A v B", "inplay": inplay, "minute": minute,
         "score_home": sh, "score_away": sa,
         "cs": {"market_id": "1.1", "status": "OPEN", "selections": cs}}
    if ht is not None:
        p["ht"] = {"market_id": "1.2", "status": "OPEN", "selections": ht}
    return p


def test_snapshot_lines_estrae_cs_e_ht_solo_inplay():
    cs = [_sel(1, "0 - 0", 5.0, 100, 4.8, 90), _sel(2, "2 - 1", 60.0, 40, 50.0, 3)]
    ht = [_sel(1, "0 - 0", 2.0, 500, 1.9, 400)]
    lines = LP.snapshot_lines("E1", _payload(0, 0, 33, cs, ht), ts=1000.0)
    assert [ln["blk"] for ln in lines] == ["cs", "ht"]
    assert lines[0]["sh"] == 0 and lines[0]["sel"][1]["ls"] == 40.0 and lines[0]["sel"][1]["bs"] == 3.0
    assert LP.snapshot_lines("E1", _payload(0, 0, 33, cs, inplay=False), ts=1.0) == []
    assert LP.snapshot_lines("E1", {"inplay": True, "cs": {"selections": cs}}, ts=1.0) == []  # niente punteggio


def _line(ts, sh, sa, sel, blk="cs", eid="E1", minute=40):
    return {"ts": ts, "event_id": eid, "name": "A v B", "blk": blk, "minute": minute,
            "sh": sh, "sa": sa, "sel": sel}


def _s(sid, name, lay, ls, back, bs, st="ACTIVE"):
    return {"sid": sid, "name": name, "st": st, "lay": lay, "ls": ls, "back": back, "bs": bs}


def test_eligible_observations_applica_i_vincoli_omega():
    sel = [
        _s(1, "1 - 0", 30.0, 50, 25.0, 10),        # troppo vicino allo 0-0 (1 gol)
        _s(2, "2 - 0", 40.0, 50, 30.0, 10),        # ok
        _s(3, "0 - 2", 150.0, 50, 100.0, 10),      # fuori fascia
        _s(4, "3 - 1", 80.0, 20, 60.0, 5, st="REMOVED"),
        _s(5, "Any Other Home Win", 50.0, 90, 40.0, 30),   # aggregato
    ]
    obs = LP.eligible_observations([_line(1.0, 0, 0, sel)])
    assert [o.sel_name for o in obs] == ["2 - 0"]
    obs2 = LP.eligible_observations([_line(1.0, 1, 0, [_s(9, "0 - 2", 60.0, 30, 50.0, 2)])])
    assert obs2 == []  # irraggiungibile: casa già a 1


def test_lay_coverage_e_persistenza():
    lines = [
        _line(0.0, 0, 0, [_s(2, "2 - 0", 40.0, 50, 30.0, 10), _s(3, "0 - 2", 110.0, 4, 90.0, 1)]),
        _line(5.0, 0, 0, [_s(2, "2 - 0", 40.0, 50, 30.0, 10), _s(3, "0 - 2", 110.0, 4, 90.0, 1)]),
        _line(10.0, 0, 0, [_s(2, "2 - 0", 38.0, 50, 30.0, 10), _s(3, "0 - 2", 110.0, 4, 90.0, 1)]),
    ]
    obs = LP.eligible_observations(lines)
    cov = LP.lay_coverage(obs, (6.0, 10.0))
    assert cov["n"] == 6 and cov["coverage"]["6.0"] == 0.5 and cov["lay_size_min"] == 4
    # il 3° snapshot ha lay 38 → fascia 20-40; le altre due in 40-80
    assert cov["bands"]["40-80"]["n"] == 2 and cov["bands"]["20-40"]["n"] == 1
    assert cov["bands"]["80-120"]["cov_6"] == 0.0
    per = LP.persistence(obs, 6.0)
    # solo la 2-0 ha size ≥6: 2 coppie, 1 stesso prezzo, 1 prezzo sceso (peggio per il layer)
    assert per["pairs"] == 2 and per["same_price_and_size_ok"] == 0.5 and per["price_worse_for_layer"] == 0.5


def test_greenup_need_rischio_equalizzato():
    need, loss = LP.greenup_need(6.0, 60.0, 12.0)
    assert need == 30.0 and loss == 24.0   # 6·60/12 = 30 back; perdita 6·(5−1) = 24


def test_greenup_cases_trigger_e_liquidita_back_dopo_il_gol():
    # 0-0: layato 2-0 @60 (2 gol di distanza). Gol casa → 1-0: 2-0 a 1 gol → trigger.
    lines = [
        _line(0.0, 0, 0, [_s(7, "2 - 0", 60.0, 50, 55.0, 2), _s(8, "3 - 0", 90.0, 50, 80.0, 1)]),
        _line(30.0, 1, 0, [_s(7, "2 - 0", 14.0, 60, 12.0, 8), _s(8, "3 - 0", 40.0, 50, 35.0, 5)]),   # back 8 < need 30
        _line(45.0, 1, 0, [_s(7, "2 - 0", 13.0, 60, 12.5, 40), _s(8, "3 - 0", 40.0, 50, 35.0, 5)]),  # back 40 ≥ need 28.8
        _line(300.0, 1, 0, [_s(7, "2 - 0", 13.0, 60, 12.5, 40)]),  # fuori finestra
    ]
    cases = LP.greenup_cases(lines, size_need=6.0)
    assert [c.sel_name for c in cases] == ["2 - 0"]   # il 3-0 resta a 2 gol: nessun trigger
    c = cases[0]
    assert c.score_before == (0, 0) and c.score_after == (1, 0) and c.lay_price == 60.0
    assert [s["ok"] for s in c.samples] == [False, True]
    assert c.first_ok_dt == 15.0 and c.samples[1]["loss"] == 22.8
    summ = LP.greenup_summary(cases)
    assert summ["with_samples"] == 1 and summ["closable_within_60s"] == 1.0


def test_greenup_gamba_vinta_non_genera_caso():
    # 0-0 layato 0-2 @70; gol CASA → 1-0: lo 0-2 è irraggiungibile → nessun caso
    lines = [
        _line(0.0, 0, 0, [_s(5, "0 - 2", 70.0, 30, 60.0, 3)]),
        _line(20.0, 1, 0, [_s(5, "0 - 2", 1000.0, 1, 900.0, 1)]),
    ]
    assert LP.greenup_cases(lines) == []


def test_verdict_dati_insufficienti_e_pass():
    rep = LP.build_report([])
    v = LP.verdict(rep)
    assert all("INSUFFICIENTI" in x for x in v)
    big = [_line(float(i * 5), 0, 0, [_s(2, "2 - 0", 40.0, 50, 30.0, 10)]) for i in range(60)]
    rep2 = LP.build_report(big)
    v2 = LP.verdict(rep2)
    assert v2[0].startswith("LAY 6 €: PASS") and v2[1].startswith("PERSISTENZA ~5s: PASS")
    assert "GREEN-UP 6 €: DATI INSUFFICIENTI" in v2[2]
    txt = LP.format_report(rep2, cases=LP.greenup_cases(big))
    assert "Lato LAY per fascia prezzo" in txt


def test_read_lines_ordina_e_ignora_righe_rotte(tmp_path: Path):
    f = tmp_path / "x.jsonl"
    f.write_text('{"ts": 5, "event_id": "E", "blk": "cs"}\nrotta\n{"ts": 1, "event_id": "E", "blk": "cs"}\n', encoding="utf-8")
    assert [ln["ts"] for ln in LP.read_lines([f])] == [1, 5]
