"""Test della MAPPA DEI FLUSSI REALI (M-3, 11/10/2026).

Le registrazioni del canale le scrive il REGISTRATORE VERO agganciato al
``LocalChannel`` di produzione (loop finto che esegue subito, ws finti hashabili:
le chiavi sono quelle del vero); il raw dei prezzi e' la registrazione VERA di
``registrazioni_banco/35760084`` (sola lettura); le righe di Salute sono
costruite con ``Betfair.monitor.scrittore.costruisci_riga`` (le colonne vere).

Si inchioda: numeri esatti (destinatari, saltati, cadenze, comandi ed esiti),
fonti mancanti DICHIARATE, buchi nella sequenza visti, file troncato detto,
referto riproducibile (stessi file = stessi byte). ASCII-only.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from Betfair.monitor.scrittore import costruisci_riga
from Betfair.stream import local_channel
from Betfair.stream import mappa_flussi as mf
from Betfair.stream import registratore_canale as reg
from Betfair.stream.local_channel import LocalChannel

RADICE = Path(__file__).resolve().parents[3]
RAW_BANCO = RADICE / "registrazioni_banco"
TOKEN = "z" * 64


class _Ws:
    def __init__(self, nome: str) -> None:
        self.nome = nome

    def __hash__(self) -> int:
        return hash(self.nome)


class _Loop:
    def __init__(self) -> None:
        self.creati: List[str] = []

    def call_soon_threadsafe(self, fn: Any) -> None:
        fn()

    def create_task(self, coro: Any) -> None:
        self.creati.append(getattr(coro, "__qualname__", "invio"))
        coro.close()


@pytest.fixture(autouse=True)
def _pulito(monkeypatch):
    # nella suite intera il banco e' gia' caricato da altri test: il controllo
    # vero del banco e' provato in un processo a parte (test del registratore)
    monkeypatch.setattr(reg, "nel_banco", lambda: False)
    reg.spegni()
    reg.azzera_per_test()
    yield
    reg.spegni()
    reg.azzera_per_test()


def _giornata(base: Path, coda_max: int = 100000) -> Dict[str, Any]:
    """Una giornata finta ma passata dal codice VERO: canale di produzione,
    registratore vero, comandi veri."""
    assert reg.accendi(cartella=str(base), _consenti_in_test=True, _senza_thread=True,
                       coda_max=coda_max, campione=10)
    ch = LocalChannel(47999, sport="calcio", token=TOKEN)
    ch._loop = _Loop()
    desk, lett, lento, cmd, intruso = (_Ws("desk"), _Ws("lett"), _Ws("lento"), _Ws("cmd"),
                                       _Ws("intruso"))
    ch._clients = {desk, lett, lento, cmd, intruso}
    ch._lettori = {lett: frozenset({"order"}), cmd: frozenset()}
    ch._comando_ws = {cmd: ("omega", True)}
    ch._autorizzati = {desk}
    ch._n_clients = 5
    ch._ricalcola_lettori()
    ch._in_volo_ws[lento] = local_channel._MAX_INVII_IN_VOLO + 1
    ch._ricalcola_pronti()
    ch.set_su_comando(lambda: None)
    for i in range(30):
        ch.publish("ladder", {"market_id": "1.%d" % (i % 3), "i": i})
    ch.publish("order", {"bet_id": "B1", "status": "EXECUTION_COMPLETE"})
    ch._on_message(desk, json.dumps({"id": 7, "m": "order", "p": {"action": "place"}}))
    # STESSO id da un altro client, mai risposto: l'esito di desk non e' il suo
    ch._on_message(intruso, json.dumps({"id": 7, "m": "snapshot"}))
    req = ch.pop_requests()
    assert req[0].ws is desk
    ch.respond(req[0], True, {"ok": True, "bet_id": "B9"})
    ch._on_message(desk, json.dumps({"id": 8, "m": "boh"}))
    ch._on_message(intruso, json.dumps({"id": 9, "m": "order", "p": {}}))
    ch._on_message(desk, json.dumps({"id": 10, "m": "snapshot"}))      # mai risposto
    ch._on_message(cmd, json.dumps({"t": "comando", "d": {"ref": "R1"}}))
    ch._on_message(cmd, json.dumps({"t": "comando", "d": {"ref": "R2"}}))
    ch.pop_comandi()
    ch.invia(cmd, {"t": "ack", "d": {"ref": "R1", "seq": 1, "accettato": True}})
    ch.invia_attore("omega", {"t": "ack", "d": {"ref": "R2", "seq": 2, "accettato": False,
                                                "motivo": "fondi_insufficienti"}})
    reg.scrivi_ora()
    reg.spegni()
    return {"ch": ch}


def test_canale_numeri_esatti(tmp_path):
    _giornata(tmp_path / "canale")
    giorno = reg.giorno_locale()
    d = mf.genera(giorno, canale=tmp_path / "canale")
    c = d["canale"]
    assert c["mancante"] is None
    lad = [t for t in c["topic"] if t["topic"] == "ladder"][0]
    # desk e intruso (desktop senza token) ricevono, lento saltato, lettore (solo
    # order) e comando (nessun topic) esclusi
    assert (lad["n"], lad["dest_p50"], lad["dest_max"], lad["saltati"]) == (30, 2.0, 2, 30)
    assert lad["con_payload"] == 3 and lad["client_max"] == 5 and lad["lettori_max"] == 2
    assert lad["cad_p50"] is not None and lad["cad_p50"] >= 0
    order = [t for t in c["topic"] if t["topic"] == "order"][0]
    assert (order["n"], order["dest_max"], order["con_payload"]) == (1, 3, 1)
    tab = {(r["genere"], r["metodo"]): r for r in c["comandi"]["tabella"]}
    assert (tab[("desktop", "order")]["n"], tab[("desktop", "order")]["ok"],
            tab[("desktop", "order")]["rifiutati"]) == (2, 1, 1)
    assert tab[("desktop", "boh")]["rifiutati"] == 1
    assert tab[("desktop", "snapshot")]["senza_esito"] == 2, \
        "l'esito di un client e' stato attribuito al comando di un altro"
    assert (tab[("comando", "comando:comando")]["ok"],
            tab[("comando", "comando:comando")]["rifiutati"]) == (1, 1)
    motivi = dict(c["comandi"]["motivi_rifiuto"])
    assert motivi["fondi_insufficienti"] == 1
    assert motivi["metodo sconosciuto: boh"] == 1
    assert any("token di sessione" in m for m in motivi)
    p = c["processi"][0]
    assert p["seq_mancanti"] == 0 and p["conti"]["scartati_coda"] == 0
    coll = {(v["genere"], v["chi"]): v["max_insieme"] for v in c["collegati"]}
    assert coll == {("desktop", "-"): 3, ("lettore", "order"): 1, ("comando", "omega"): 1}
    testo = mf.markdown(d)
    assert "| 47999 | calcio | ladder | 30 |" in testo
    assert "30 invii saltati in 30 giri su 30" in testo
    assert "fondi_insufficienti" in testo


def test_buchi_della_sequenza_e_file_troncato(tmp_path):
    """Coda piena (10 record): la mappa conta i record mancanti; un file
    troncato si dice."""
    _giornata(tmp_path / "canale", coda_max=10)
    giorno = reg.giorno_locale()
    d = mf.genera(giorno, canale=tmp_path / "canale")
    p = d["canale"]["processi"][0]
    assert p["record"] == 10 and p["seq_mancanti"] > 0
    assert p["conti"]["scartati_coda"] == p["seq_mancanti"]
    testo = mf.markdown(d)
    assert "record mancanti nella sequenza" in testo and "scartati_coda" in testo
    f = next((tmp_path / "canale" / giorno).glob("canale_*.jsonl.gz"))
    dati = f.read_bytes()
    f.write_bytes(dati[:-12])
    d2 = mf.genera(giorno, canale=tmp_path / "canale")
    assert d2["canale"]["file"][0]["errore"]
    assert "troncato" in mf.markdown(d2) or "illeggibil" in mf.markdown(d2)


def test_fonti_mancanti_dichiarate(tmp_path):
    d = mf.genera("2026-10-12", canale=tmp_path / "no", raw=tmp_path / "no",
                  salute=tmp_path / "no", ordini=None)
    testo = mf.markdown(d)
    for fonte in ("canale", "raw", "salute", "ordini (M-1)"):
        assert "| %s |" % fonte in testo
    assert testo.count("MANCA:") == 4
    assert "cartella non indicata (--ordini)" in testo
    assert "Nessun buco rilevato" not in testo


@pytest.mark.skipif(not (RAW_BANCO / "35760084").is_dir(), reason="registrazioni_banco assente")
def test_raw_vero_del_banco(tmp_path):
    """Registrazione VERA (sola lettura): messaggi del giorno, heartbeat,
    cadenza; il giorno dopo non ha messaggi e lo dice."""
    d = mf.genera("2026-06-30", raw=RAW_BANCO)
    evs = {e["evento"]: e for e in d["raw"]["eventi"]}
    assert "35760084" in evs
    e = evs["35760084"]
    n_veri = 0
    a, b = mf.limiti_giorno("2026-06-30")
    with gzip.open(RAW_BANCO / "35760084" / "35760084.raw.jsonl.gz", "rt") as fh:
        for linea in fh:
            pt = json.loads(linea).get("pt")
            if pt is not None and a <= pt < b:
                n_veri += 1
    assert e["messaggi"] == n_veri and n_veri > 1000
    assert e["cad_p50"] is not None and e["cad_p50"] <= e["cad_p95"] <= e["cad_p99"]
    vuoto = mf.genera("2026-07-15", raw=RAW_BANCO)
    assert vuoto["raw"]["mancante"] and "35760084" not in str(vuoto["raw"]["eventi"])


def test_salute_e_ordini_m1(tmp_path):
    giorno = "2026-10-12"
    a, _ = mf.limiti_giorno(giorno)
    sal = tmp_path / "monitor" / giorno
    sal.mkdir(parents=True)
    righe = []
    for i in list(range(10)) + [20]:          # buco fra la 10a e la 21a riga
        righe.append(costruisci_riga("runner_calcio", "calcio",
                                     {"contatori": {"db": {"x": 2}, "betfair_rest": {"y": 1}}},
                                     {"cpu_pct": 10.0 + i, "rss_mb": 300.0 + i},
                                     adesso_ms=a + 3600_000 + i * 30_000, avvio_ms=a,
                                     finestra_s=30.0, pid=1, host="pc"))
    (sal / "runner_calcio.jsonl").write_text("".join(json.dumps(r) + "\n" for r in righe))
    ordd = tmp_path / "m1" / giorno
    ordd.mkdir(parents=True)
    with gzip.open(ordd / "stream_ordini.jsonl.gz", "wt") as fh:
        for i in range(5):
            fh.write(json.dumps({"epoca_ms": a + 1000 * i, "tipo": "ocm"}) + "\n")
        fh.write(json.dumps({"epoca_ms": a + 500_000, "tipo": "ocm"}) + "\n")
        fh.write(json.dumps({"tipo": "senza_tempo"}) + "\n")
    d = mf.genera(giorno, salute=tmp_path / "monitor", ordini=tmp_path / "m1")
    s = d["salute"]["servizi"][0]
    assert (s["righe"], s["n_buchi"], s["db"], s["rest"]) == (11, 1, 22, 11)
    assert s["rss_max"] == 320.0 and s["buco_max_s"] == 330.0
    f = d["ordini"]["file"][0]
    g = f["generi"][0]
    assert (g["genere"], g["n"], g["n_buchi"], f["senza_tempo"]) == ("ocm", 6, 1, 1)
    assert g["cad_p50"] == 1000.0
    testo = mf.markdown(d)
    assert "| runner_calcio | 11 |" in testo and "M-1 stream_ordini.jsonl.gz/ocm" in testo


def test_referto_riproducibile_e_cli(tmp_path):
    """Stessi file = stessi byte (md e json), anche dalla riga di comando."""
    _giornata(tmp_path / "canale")
    giorno = reg.giorno_locale()
    args = ["--giorno", giorno, "--canale", str(tmp_path / "canale"), "--raw",
            str(tmp_path / "no"), "--salute", str(tmp_path / "no")]
    assert mf.main(args + ["--uscita", str(tmp_path / "a.md"), "--json",
                           str(tmp_path / "a.json")]) == 0
    assert mf.main(args + ["--uscita", str(tmp_path / "b.md"), "--json",
                           str(tmp_path / "b.json")]) == 0
    assert (tmp_path / "a.md").read_bytes() == (tmp_path / "b.md").read_bytes()
    assert (tmp_path / "a.json").read_bytes() == (tmp_path / "b.json").read_bytes()
    (tmp_path / "a.md").read_bytes().decode("ascii")


def test_percentile_a_rango():
    assert mf.percentile([], 50) is None
    assert mf.percentile([5.0], 99) == 5.0
    v = [float(x) for x in range(1, 101)]
    assert (mf.percentile(v, 50), mf.percentile(v, 95), mf.percentile(v, 99)) == (50.0, 95.0, 99.0)
    assert mf.percentile([3.0, 1.0, 2.0], 50) == 2.0
