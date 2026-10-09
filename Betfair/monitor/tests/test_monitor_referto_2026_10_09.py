"""T0A "Salute" (09/10/2026): il referto giornaliero (``python -m Betfair.monitor.referto``).

Le righe dei test sono costruite con ``scrittore.costruisci_riga`` (lo stesso
costruttore delle righe vere) e contatori/tratti del ``Registro`` vero: stesse
chiavi e stessi tipi di ``monitor_metrics``.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pytest

from Betfair.monitor import referto as RF
from Betfair.monitor import registro as R
from Betfair.monitor import scrittore as SC

GIORNO = "2026-10-10"
#: mezzanotte Europe/Rome del 10/10 (ora legale: UTC+2)
T0 = datetime(2026, 10, 9, 22, 0, tzinfo=timezone.utc)


def _riga(servizio: str, i: int, *, pid: int = 100, avvio: Optional[datetime] = None, cpu: float = 5.0,
          rss: float = 100.0, contatori: Optional[Dict[str, Dict[str, float]]] = None,
          tratti: Optional[Dict[str, List[float]]] = None, sistema: Optional[Dict[str, Any]] = None,
          sport: str = "calcio") -> Dict[str, Any]:
    reg = R.Registro()
    for g, d in (contatori or {}).items():
        for k, n in d.items():
            reg.conta(g, k, n)
    for k, vs in (tratti or {}).items():
        for v in vs:
            reg.tratto(k, v)
    adesso = T0 + timedelta(seconds=30 * (i + 1))
    avvio = avvio or T0
    return SC.costruisci_riga(servizio, sport, reg.fotografa_e_azzera(),
                              {"psutil": True, "cpu_pct": cpu, "rss_mb": rss, "thread": 20},
                              adesso_ms=int(adesso.timestamp() * 1000), avvio_ms=int(avvio.timestamp() * 1000),
                              finestra_s=30.0, pid=pid, sistema=sistema, host="pc")


def _giornata() -> List[Dict[str, Any]]:
    righe = []
    for i in range(2880):
        ora = i // 120
        # RSS: 90 MB nella prima ora (riscaldamento), 100 dalla seconda, 102 nell'ultima: la
        # crescita si misura fra la 2a e l'ultima ora (2%), MAI dalla prima (sarebbe 13%)
        rss = 90.0 if ora == 0 else (102.0 if ora >= 23 else 100.0)
        righe.append(_riga("mike-service", i, cpu=2.0 + (i % 10) * 0.1, rss=rss,
                           contatori={"db": {"GET mike_trades": 10}, "betfair_rest": {"certlogin": 1} if i == 0 else {}},
                           tratti={"feed_rx_pt_ms.calcio": [150.0 + (i % 5)]},
                           sistema={"pacchetti": {"flumine": "2.13.11"}} if i == 0 else None))
        righe.append(_riga("runner-calcio", i, pid=200, cpu=12.0, rss=300.0,
                           contatori={"transazioni": {"place": 2}} if ora == 15 else {},
                           tratti={"diario_fsync_ms": [0.4, 9.0]} if i % 60 == 0 else None))
    return righe


@pytest.fixture(scope="module")
def giornata():
    return _giornata()


def test_finestra_europe_rome():
    da, a = RF.finestra_del_giorno(GIORNO)
    assert da == T0 and a == T0 + timedelta(days=1)
    dentro = _riga("x", 0)
    fuori = dict(dentro, ts=(T0 - timedelta(seconds=1)).isoformat())
    assert RF.filtra_giorno([fuori, dentro], da, a) == [dentro]


def test_referto_sano_tutti_ok(giornata):
    r = RF.costruisci(GIORNO, giornata, fonte="test")
    esiti = {v["grandezza"]: v["esito"] for v in r["verdetti"]}
    assert esiti["L15 CPU p95 per servizio (% di un core)"] == "OK"
    assert esiti["L15 CPU app (somma delle medie)"] == "OK"
    assert esiti["L16 crescita RSS 2a -> ultima ora (peggiore)"] == "OK"     # 2% <= 5%
    assert esiti["L17 mike-service richieste/min"] == "OK"                   # 20/min
    assert esiti["L19 scarto orologio (limite superiore da rx - pt)"] == "NON MISURATO"   # 150 ms > 100
    m = r["servizi"]["mike-service"]
    assert m["righe"] == 2880 and m["copertura_pct"] == 100.0
    assert m["db_richieste"] == 28800 and m["db_al_minuto"] == 20.0
    assert m["login"] == 1 and m["relogin"] == 0
    c = m["crescita_rss"][0]
    assert c["rss_2a_ora_mb"] == 100.0 and c["rss_ultima_ora_mb"] == 102.0 and c["crescita_pct"] == 2.0
    # ts = FINE della finestra: l'ultima riga del 15 (ts 16:00:00) va nell'ora delle 16
    assert r["transazioni_per_ora"] == {"15:00": 238, "16:00": 2}
    assert r["tratti_app"]["diario_fsync_ms"]["n"] == 96
    assert r["tratti_app"]["diario_fsync_ms"]["p50"] == 0.5
    assert r["orologio_limite_superiore_ms"] == 150.0
    assert r["versioni_fuori_pin"] == []


def test_referto_fuori_obiettivo(giornata):
    righe = list(giornata)
    righe += [_riga("omega-service", i, cpu=45.0, rss=500.0 + (60.0 if i > 2700 else 0.0),
                    contatori={"db": {"GET omega_trades": 70}, "betfair_rest": {"certlogin": 4} if i == 5 else {},
                               "transazioni": {"place": 6000} if i == 10 else {}},
                    tratti={"feed_rx_pt_ms.scanner": [40.0]},
                    sistema={"pacchetti": {"flumine": "3.2.6"}} if i == 0 else None)
              for i in range(2880)]
    r = RF.costruisci(GIORNO, righe, fonte="test", extra={"crash": {"omega-service": 2, "_pianificati": 1}})
    esiti = {v["grandezza"]: (v["esito"], v["valore"]) for v in r["verdetti"]}
    assert esiti["L15 CPU p95 per servizio (% di un core)"] == ("FUORI", "omega-service 45.0")
    assert esiti["L16 crescita RSS 2a -> ultima ora (peggiore)"][0] == "FUORI"
    assert esiti["L17 omega-service richieste/min"][0] == "FUORI"            # 140/min
    assert esiti["L18 re-login (peggiore, nel giorno)"] == ("FUORI", "omega-service 3")
    assert esiti["L18 riavvii NON pianificati (live_alerts)"] == ("FUORI", 2)
    assert esiti["L19 scarto orologio (limite superiore da rx - pt)"] == ("OK", 40.0)
    assert esiti["transazioni Betfair per ora (massimo)"][0] == "FUORI"
    assert r["versioni_fuori_pin"] == ["omega-service: flumine 3.2.6 (pin 2.13.11)"]


def test_riavvii_dai_pid_senza_db():
    righe = [_riga("scalper-sessione-35.1", i, pid=1 + (i >= 100)) for i in range(200)]
    r = RF.costruisci(GIORNO, righe, fonte="test")
    s = r["servizi"]["scalper-sessioni"]
    assert s["vite"] == 2 and s["riavvii_pid"] == 1
    v = [x for x in r["verdetti"] if x["grandezza"].startswith("L18 riavvii")][0]
    assert v["esito"] == "NON MISURATO" and v["valore"] == 1


def test_paper_e_live_mai_sommati():
    righe = [_riga("runner-calcio", 0, contatori={"esecuzione_live": {"place": 1},
                                                  "esecuzione_paper": {"place": 9},
                                                  "transazioni": {"place": 1}})]
    r = RF.costruisci(GIORNO, righe, fonte="test")
    s = r["servizi"]["runner-calcio"]
    assert s["esecuzione_live"] == {"place": 1} and s["esecuzione_paper"] == {"place": 9}
    assert r["transazioni_per_ora"] == {"00:00": 1}


def test_stesse_righe_stessi_byte(giornata, tmp_path):
    f = tmp_path / "righe.json"
    f.write_text(json.dumps({"righe": giornata[:400], "extra": {}}), encoding="ascii")
    out1, out2 = tmp_path / "u1", tmp_path / "u2"
    assert RF.main(["--giorno", GIORNO, "--righe", str(f), "--uscita", str(out1)]) == 0
    assert RF.main(["--giorno", GIORNO, "--righe", str(f), "--uscita", str(out2)]) == 0
    for nome in (f"REFERTO_SALUTE_{GIORNO}.md", f"REFERTO_SALUTE_{GIORNO}.json"):
        assert (out1 / nome).read_bytes() == (out2 / nome).read_bytes()
    md = (out1 / f"REFERTO_SALUTE_{GIORNO}.md").read_text(encoding="utf-8")
    assert "## Verdetti" in md and "mike-service" in md
    assert RF.impronta(RF.filtra_giorno(giornata[:400], *RF.finestra_del_giorno(GIORNO))) in md
    json.loads((out1 / f"REFERTO_SALUTE_{GIORNO}.json").read_text(encoding="ascii"))


def test_righe_locali_dello_scrittore(tmp_path, monitor_acceso, monkeypatch):
    s = SC.Scrittore(servizio="runner-calcio", sport="calcio", intervallo=30.0, invia=lambda r: None,
                     cartella=str(tmp_path))
    monitor_acceso.conta("db", "GET live_follow", 3)
    riga = s.giro()
    giorno = datetime.now().strftime("%Y-%m-%d")
    lette = RF.righe_locali(tmp_path, giorno)
    assert lette == [json.loads(json.dumps(riga, sort_keys=True))]


def test_feed_per_partita_buchi_rx_e_soldi(tmp_path):
    d = tmp_path / "35.1"
    d.mkdir()
    base = int((T0 + timedelta(hours=10)).timestamp() * 1000)
    righe = [{"op": "mcm", "pt": base, "rx": base + 120, "mc": []},
             {"op": "mcm", "pt": base + 1000, "rx": base + 1180, "mc": []},
             {"op": "mcm", "pt": base + 7500, "mc": []}]
    p = d / "35.1.raw.jsonl"
    p.write_text("\n".join(json.dumps(x) for x in righe) + "\n", encoding="utf-8")
    t = (T0 + timedelta(hours=11)).timestamp()
    os.utime(p, (t, t))
    out = RF.feed_per_partita(tmp_path, *RF.finestra_del_giorno(GIORNO), {"paper": ["35.1"], "live": []})
    assert out == [{"evento": "35.1", "messaggi": 3, "buchi_oltre_5s": 1, "buco_max_s": 6.5,
                    "rx_pt_n": 2, "rx_pt_p50_ms": 120.0, "rx_pt_p99_ms": 180.0, "soldi": "paper"}]


def test_log_del_giorno(tmp_path):
    da, a = RF.finestra_del_giorno(GIORNO)
    for nome, mb in (("runner-calcio_2026-10-10.log", 60), ("mike-service_x.log", 1)):
        p = tmp_path / nome
        p.write_bytes(b"x" * (mb * 1024 * 1024))
        t = (T0 + timedelta(hours=3)).timestamp()
        os.utime(p, (t, t))
    vecchio = tmp_path / "runner-calcio_vecchio.log"
    vecchio.write_bytes(b"x" * 1024)
    t = (T0 - timedelta(days=3)).timestamp()
    os.utime(vecchio, (t, t))
    out = RF.log_del_giorno(tmp_path, da, a)
    assert out["mb_totali"] == 61.0
    assert out["mb_per_servizio"] == {"mike-service": 1.0, "runner-calcio": 60.0}
    r = RF.costruisci(GIORNO, [_riga("x", 0)], fonte="t", extra={"log": out})
    v = [x for x in r["verdetti"] if x["grandezza"] == "L18 log del giorno (MB)"][0]
    assert v["esito"] == "FUORI"


def test_pin_dei_requisiti_letti_dal_repo():
    pin = RF.pin_requisiti()
    assert pin["flumine"] == "2.13.11" and pin["betfairlightweight"] == "2.23.2"
    assert pin["psutil"] == "7.2.2"
