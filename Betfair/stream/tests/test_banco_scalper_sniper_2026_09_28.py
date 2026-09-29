"""Banco dello scalper calcio: scenario SNIPER e velocita' di S5 (cantiere D2, 28/09).

* `_buco_dentro_ms` con la ricerca binaria da' ESATTAMENTE lo stesso numero della
  somma su tutti i buchi (prima: O(battiti x buchi) a ogni giro, con la vita
  della sessione sniper il banco si fermava);
* `_Orologio.buchi` incrementale = ricalcolo completo;
* lo scenario sniper: control con `sniper_mode`, vita della sessione di
  produzione, riga `live_now` dal sidecar, linea con la funzione di produzione;
* `applica_linea_sniper` (estratta dal watcher, nessun cambio di logica).
"""
from __future__ import annotations

import json
import random
from types import SimpleNamespace

import pytest

from Betfair.stream.scalper import certificazione as CERT
from Betfair.stream.scalper import scalper_session as SS
from Betfair.stream.scalper.tools import replay_registrazioni as RR


def _buchi_casuali(rng: random.Random, n: int):
    t, out = 0, []
    for _ in range(n):
        t += rng.randint(0, 5000)
        d = rng.randint(2000, 9000)
        out.append((t, t + d))
        t += d
    return out


@pytest.mark.parametrize("seme", range(20))
def test_copertura_uguale_alla_somma_completa(seme):
    """Buchi ordinati, sovrapposti e fuori ordine (i book di mercati diversi
    arrivano in ordine sparso): stesso numero della somma su tutti i buchi."""
    rng = random.Random(seme)
    buchi = _buchi_casuali(rng, rng.randint(0, 60))
    if seme % 2:
        buchi += [(a + rng.randint(-3000, 3000), b + rng.randint(0, 4000))
                  for a, b in rng.sample(buchi, len(buchi) // 3)]
        rng.shuffle(buchi)
    cop = CERT._CoperturaBuchi(buchi) if buchi else None
    fine = max([b for _a, b in buchi], default=50000) + 10000
    for _ in range(200):
        a = rng.randint(-1000, fine)
        b = a + rng.randint(0, 40000)
        assert CERT._buco_dentro_ms(buchi, a, b, cop) == CERT._buco_dentro_ms(buchi, a, b)


def test_copertura_casi_limite():
    cop = CERT._CoperturaBuchi([(10, 20), (15, 30), (40, 40)])
    assert cop.dentro(0, 100) == 10 + 15
    assert cop.dentro(15, 20) == 10          # due buchi sovrapposti
    assert cop.dentro(20, 10) == 0
    assert CERT._CoperturaBuchi([]).dentro(0, 10) == 0


def test_buchi_incrementali_uguali_al_ricalcolo():
    o = RR._Orologio()
    rng = random.Random(7)
    t = 1_000_000
    for i in range(3000):
        t += rng.choice([100, 300, 2500, 8000])
        o.libro_ms.append(t)
        if i % 97 == 0:
            parziale = o.buchi()
            atteso = []
            prima = None
            for ms in o.libro_ms:
                if prima is not None and ms - prima >= 2000:
                    atteso.append((prima, ms))
                prima = ms
            assert parziale == atteso


def test_control_sniper_accende_lo_sniper_e_le_uscite_di_produzione():
    c = RR.control_della_ui("1", RR.SCENARIO_SNIPER)
    assert c["params"]["sniper_mode"] is True and c["dry_run"] is False
    # N3 (28/09): gli scenari esistenti girano a uscite AUTOMATICHE dichiarate;
    # le manuali hanno i loro scenari (`SCENARI_USCITE_MANUALI`)
    assert c["params"]["uscite_automatiche"] is True
    assert RR.control_della_ui("1", RR.SCENARIO_SNIPER_PAPER)["dry_run"] is True
    auto = RR.control_della_ui("1", RR.SCENARIO_SNIPER_AUTO)["params"]
    assert auto["uscite_automatiche"] is True
    assert RR.control_della_ui("1", "base")["params"]["sniper_mode"] is False
    assert set(RR.SCENARI_SNIPER) <= set(RR.SCENARI_DESCRITTI)


def test_vita_della_sessione_quella_di_produzione():
    from Betfair.stream.scalper.auto_mode import vita_sessione_s

    c = RR.control_della_ui("1", RR.SCENARIO_SNIPER)
    assert RR._vita_da_control(c) == int(vita_sessione_s({"sniper_mode": True}))
    # `base` ha sniper_mode=False ESPLICITO (control della UI): vita del maker
    assert RR._vita_da_control(RR.control_della_ui("1", "base")) == \
        int(vita_sessione_s({"sniper_mode": False, "theta_mode": False,
                             "ht_mode": False})) == 600


def test_righe_live_now_dal_sidecar(tmp_path):
    d = tmp_path / "99"
    d.mkdir()
    righe = [{"ts_ms": 2000, "minute": 3, "score_home": 1, "score_away": 0},
             {"ts_ms": 1000, "minute": 1, "score_home": 0, "score_away": 0}]
    (d / "99.scores.jsonl").write_text("\n".join(json.dumps(r) for r in righe),
                                       encoding="utf-8")
    out = RR.righe_live_now(str(tmp_path), "99")
    assert [t for t, _ in out] == [1000, 2000]
    o = RR._Orologio()
    db = RR._DbFinto(o, RR.control_della_ui("99", "sniper"), {})
    db.punteggi_live_now = out
    o.ora_s = 0.5
    assert db.live_now() is None                        # prima del primo punteggio
    o.ora_s = 1.5
    assert db.live_now() == {"score_home": 0, "score_away": 0, "minute": 1}
    o.ora_s = 5.0
    assert db.live_now()["score_home"] == 1
    # la tabella `live_now` vista dalla sessione restituisce la stessa riga
    r = db.sb.table("live_now").select("score_home,score_away,minute").eq(
        "event_id", "99").execute()
    assert r.data == [db.live_now()]


class _SniperFinto:
    def __init__(self, parallele: int = 0) -> None:
        self.parallel_lines = parallele
        self.linee = None
        self.linea = None
        self.live_minute = None

    def set_lines(self, linee):
        self.linee = list(linee)

    def set_line(self, linea):
        self.linea = linea


@pytest.mark.parametrize("h,a,par,attese", [
    (0, 0, 0, ["OVER_UNDER_15"]), (1, 1, 0, ["OVER_UNDER_35"]),
    (2, 1, 2, ["OVER_UNDER_45", "OVER_UNDER_55", "OVER_UNDER_65"]),
    (4, 3, 2, ["OVER_UNDER_85"]),
])
def test_applica_linea_sniper(h, a, par, attese):
    s = _SniperFinto(par)
    SS.applica_linea_sniper(s, {"score_home": h, "score_away": a, "minute": 12})
    assert s.linee == attese and s.live_minute == 12.0


def test_applica_linea_sniper_oltre_sette_gol_spegne():
    s = _SniperFinto()
    SS.applica_linea_sniper(s, {"score_home": 5, "score_away": 3, "minute": None})
    assert s.linea == "NONE" and s.live_minute is None


def test_il_thread_della_linea_non_parte_nel_banco():
    banco = SimpleNamespace(sniper_linea=None)
    th = RR._ThreadingSessione(banco)
    finto = th.Thread(target=lambda: None, args=("SNIPER",), daemon=True, name="sniper-line")
    finto.start()
    assert banco.sniper_linea == "SNIPER" and finto.is_alive() is False
    vero = th.Thread(target=lambda: None, name="altro")
    import threading
    assert isinstance(vero, threading.Thread)
