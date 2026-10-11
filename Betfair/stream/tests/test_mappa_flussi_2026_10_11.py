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
import sys
import time
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
    ch._on_message(desk, json.dumps({"id": 7, "m": "order",
                                     "p": {"action": "place", "mode": "live"}}))
    # STESSO id da un altro client, mai risposto: l'esito di desk non e' il suo
    ch._on_message(intruso, json.dumps({"id": 7, "m": "snapshot"}))
    req = ch.pop_requests()
    assert req[0].ws is desk
    ch.respond(req[0], True, {"ok": True, "bet_id": "B9"})
    # paper e live dello stesso metodo: righe SEPARATE, mai sommate
    ch._on_message(desk, json.dumps({"id": 11, "m": "order",
                                     "p": {"action": "place", "mode": "paper"}}))
    ch.respond(ch.pop_requests()[0], True, {"ok": True, "bet_id": "P1"})
    ch._on_message(desk, json.dumps({"id": 12, "m": "order",
                                     "p": {"action": "place", "mode": "LIVE"}}))
    ch.respond(ch.pop_requests()[0], False, None, "INSUFFICIENT_FUNDS")
    ch._on_message(desk, json.dumps({"id": 8, "m": "boh"}))
    ch._on_message(intruso, json.dumps({"id": 9, "m": "order", "p": {}}))
    ch._on_message(desk, json.dumps({"id": 10, "m": "snapshot"}))      # mai risposto
    # id RIUSATO dallo stesso client: la risposta al primo (arrivata PRIMA del
    # secondo) non e' l'esito del secondo
    ch._on_message(desk, json.dumps({"id": 20, "m": "boh"}))
    ch._on_message(desk, json.dumps({"id": 20, "m": "snapshot"}))      # mai risposto
    # stesso id su DUE connessioni, l'altra PRIMA: la risposta al desktop non e'
    # l'esito del comando dell'intruso
    ch._on_message(intruso, json.dumps({"id": 30, "m": "snapshot"}))   # mai risposto
    ch._on_message(desk, json.dumps({"id": 30, "m": "boh"}))
    ch.pop_requests()
    ch._on_message(cmd, json.dumps({"t": "comando", "d": {"ref": "R1", "azione": "place",
                                                          "mode": "live"}}))
    ch._on_message(cmd, json.dumps({"t": "comando", "d": {"ref": "R2", "azione": "place",
                                                          "mode": "paper"}}))
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
    tab = {(r["genere"], r["metodo"], r["modo"]): r for r in c["comandi"]["tabella"]}
    riga = tab[("desktop", "order:place", "live")]
    assert (riga["n"], riga["ok"], riga["rifiutati"]) == (2, 1, 1), "live"
    riga = tab[("desktop", "order:place", "paper")]
    assert (riga["n"], riga["ok"], riga["rifiutati"]) == (1, 1, 0), "paper sommato al live?"
    assert tab[("desktop", "order", "-")]["rifiutati"] == 1        # senza token
    assert tab[("desktop", "boh", "-")]["rifiutati"] == 3
    assert tab[("desktop", "snapshot", "-")]["senza_esito"] == 4, \
        "l'esito di un altro client, o di un comando precedente, e' stato attribuito"
    assert (tab[("comando", "comando:comando:place", "live")]["ok"],
            tab[("comando", "comando:comando:place", "paper")]["rifiutati"]) == (1, 1)
    assert not any(r["modo"] not in ("live", "paper", "-") for r in c["comandi"]["tabella"])
    motivi = dict(c["comandi"]["motivi_rifiuto"])
    assert motivi["INSUFFICIENT_FUNDS"] == 1
    assert motivi["fondi_insufficienti"] == 1
    assert motivi["metodo sconosciuto: boh"] == 3
    assert any("token di sessione" in m for m in motivi)
    p = c["processi"][0]
    assert p["seq_mancanti"] == 0 and p["conti"]["scartati_coda"] == 0
    coll = {(v["genere"], v["chi"]): v["max_insieme"] for v in c["collegati"]}
    assert coll == {("desktop", "-"): 3, ("lettore", "order"): 1, ("comando", "omega"): 1}
    testo = mf.markdown(d)
    assert "| 47999 | calcio | ladder | 30 |" in testo
    assert "30 invii saltati in 30 giri su 30" in testo
    assert "fondi_insufficienti" in testo
    assert "| 47999 | desktop | order:place | paper | 1 | 1 | 0 | 0 |" in testo


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
    assert "tronca" in mf.markdown(d2) or "illeggibil" in mf.markdown(d2)


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


def test_salute(tmp_path):
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
    d = mf.genera(giorno, salute=tmp_path / "monitor")
    s = d["salute"]["servizi"][0]
    assert (s["righe"], s["n_buchi"], s["db"], s["rest"]) == (11, 1, 22, 11)
    assert s["rss_max"] == 320.0 and s["buco_max_s"] == 330.0
    assert "| runner_calcio | 11 |" in mf.markdown(d)


# ---------------------------------------------------------------------------
# i file VERI di M-1 (registratore dello stream ordini e delle REST)
# ---------------------------------------------------------------------------
#: M-1 chiuso a questo commit del ramo ``mappa/m1-ordini`` (letto, mai toccato)
COMMIT_M1 = "3bb418fe"


def _modulo_da_git(percorso: str, nome: str) -> Any:
    """Un modulo di M-1 com'e' al commit ``COMMIT_M1`` (``git show``, sola
    lettura), compilato nel pacchetto ``Betfair.monitor``. ``None`` se git o il
    commit non ci sono."""
    import importlib.util
    import subprocess

    try:
        r = subprocess.run(["git", "show", "%s:%s" % (COMMIT_M1, percorso)], cwd=str(RADICE),
                           capture_output=True, text=True, timeout=30)
    except Exception:  # noqa: BLE001
        return None
    if r.returncode != 0:
        return None
    spec = importlib.util.spec_from_loader(nome, loader=None)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "Betfair.monitor"
    mod.__file__ = str(RADICE / percorso)
    exec(compile(r.stdout, "<%s:%s>" % (COMMIT_M1, percorso), "exec"), mod.__dict__)  # noqa: S102
    return mod


def _modulo_m1(nome: str) -> Any:
    """Il modulo VERO di M-1: dal pacchetto se c'e' (dopo l'unione su MASTER),
    altrimenti dal commit ``COMMIT_M1``."""
    import importlib

    try:
        return importlib.import_module("Betfair.monitor.%s" % nome)
    except ImportError:
        return _modulo_da_git("Betfair/monitor/%s.py" % nome, "_m1_%s_prova" % nome)


def _iso_us(testo: str) -> int:
    from datetime import datetime as _dt
    return int(_dt.fromisoformat(testo).timestamp() * 1_000_000)


class _OrdineFlumine:
    """Le due chiavi che ``decisione`` di M-1 legge da un ordine flumine."""

    def __init__(self, cor: str, oid: str) -> None:
        self.customer_order_ref = cor
        self.id = oid


@pytest.mark.parametrize("lettore", ["m1", "assente"])
def test_ordini_m1_scritti_dallo_scrittore_vero(tmp_path, monkeypatch, lettore):
    """Il formato di M-1 scritto dal SUO Scrittore (commit ``COMMIT_M1``):
    cartelle ``AAAAMMGG`` UTC, ``ep_us`` in microsecondi, ``risposta_ep_us``
    nelle REST, ``dec`` con ``mode``. Il giorno LOCALE 2026-10-12 (Europe/Rome)
    copre due cartelle UTC: si leggono entrambe e si tengono solo le righe
    dentro il giorno (una REST delle 23:00 locali dell'11 sta nella cartella
    20261011 ma NON e' del 12). Con il lettore di M-1 (``leggi_file``,
    ``analizza_giorni``) e senza (la mappa lo dice e prosegue): stessi numeri."""
    m1 = _modulo_m1("registratore_ordini")
    if m1 is None:
        pytest.skip("modulo di M-1 non disponibile (ne' nel pacchetto ne' al commit %s)"
                    % COMMIT_M1)
    if mf.NOME_FUSO != "Europe/Rome":
        pytest.skip("tzdata assente: il giorno locale non e' quello di Roma")
    if lettore == "m1":
        ao = _modulo_m1("analisi_ordini")
        if ao is None:
            pytest.skip("lettore di M-1 non disponibile")
        monkeypatch.setitem(sys.modules, "Betfair.monitor.analisi_ordini", ao)
    else:
        monkeypatch.setitem(sys.modules, "Betfair.monitor.analisi_ordini", None)
    base = tmp_path / "_ordini"
    orologio = {"ep_us": 0}
    monkeypatch.setattr(m1, "adesso_us", lambda: (orologio["ep_us"], orologio["ep_us"]))
    monkeypatch.setattr(m1, "giorno_utc", lambda ep_s=None: time.strftime(
        "%Y%m%d", time.gmtime(orologio["ep_us"] / 1e6 if ep_s is None else ep_s)))
    monkeypatch.setattr(m1, "attivo", lambda: True)
    s = m1.Scrittore(cartella=str(base), servizio="runner_calcio", avvia_thread=False)
    m1._azzera_per_test(s)
    ok = {"result": {"status": "SUCCESS", "instructionReports": [{"errorCode": None}]}}

    def rest(metodo: str, csr: str, invio_us: int, durata_ms: int) -> None:
        m1.registra_rest(via="flumine", method="SportsAPING/v1.0/" + metodo,
                         params={"marketId": "1.1", "customerStrategyRef": csr,
                                 "instructions": [{"customerOrderRef": "r1"}]},
                         invio=(invio_us, invio_us), risposta=(invio_us + durata_ms * 1000,
                                                               invio_us + durata_ms * 1000),
                         esito=ok)

    try:
        # 23:00 locali dell'11 (21:00 UTC): cartella 20261011, FUORI dal 12
        orologio["ep_us"] = _iso_us("2026-10-11T21:00:00+00:00")
        rest("placeOrders", "live", orologio["ep_us"], 999)
        m1.decisione(_OrdineFlumine("r0", "o0"), {"chiave": "c0", "mode": "live"})
        s.giro(forza_svuota=True)
        # 00:30 locali del 12 (22:30 UTC dell'11): cartella 20261011, DENTRO
        orologio["ep_us"] = _iso_us("2026-10-11T22:30:00+00:00")
        for i in range(3):
            orologio["ep_us"] += 10_000
            s.metti_stream(1, json.dumps({"op": "ocm", "clk": "A%d" % i, "pt": 1}))
        m1.decisione(_OrdineFlumine("r1", "o1"), {"chiave": "c1", "mode": "live"})
        m1.decisione(_OrdineFlumine("r2", "o2"), {"chiave": "c2", "mode": "paper"})
        rest("placeOrders", "live", orologio["ep_us"], 40)
        s.giro(forza_svuota=True)
        # 12:00 locali del 12 (10:00 UTC): cartella 20261012, DENTRO
        orologio["ep_us"] = _iso_us("2026-10-12T10:00:00+00:00")
        s.metti_stream(1, json.dumps({"op": "ocm", "clk": "B", "pt": 2}))
        m1.decisione(_OrdineFlumine("r3", "o3"), {"chiave": "c3", "mode": "paper"})
        rest("cancelOrders", "omega", orologio["ep_us"], 30)
        s.giro(forza_svuota=True)
    finally:
        s.chiudi()
        m1._azzera_per_test(None)
    assert sorted(p.name for p in base.iterdir()) == ["20261011", "20261012"]

    d = mf.genera("2026-10-12", ordini=base)
    o = d["ordini"]
    assert o["mancante"] is None and o["cartelle_utc"] == ["20261011", "20261012"]
    assert len(o["file"]) == 2
    rest_tab = {(r["metodo"], r["attore"]): r for r in o["rest"]}
    assert set(rest_tab) == {("placeOrders", "desktop"), ("cancelOrders", "bot:omega")}
    assert (rest_tab[("placeOrders", "desktop")]["n"],
            rest_tab[("placeOrders", "desktop")]["p50"]) == (1, 40.0), \
        "la REST delle 23:00 dell'11 e' stata contata nel 12, o la durata e' sbagliata"
    assert rest_tab[("cancelOrders", "bot:omega")]["p50"] == 30.0
    generi: Dict[str, int] = {}
    for f in o["file"]:
        for g in f["generi"]:
            generi[g["genere"]] = generi.get(g["genere"], 0) + g["n"]
    assert generi["stream"] == 4 and generi["rest"] == 2
    assert (generi["dec:live"], generi["dec:paper"]) == (1, 2), "decisioni paper e live sommate"
    assert all(f["chiuso"] for f in o["file"])
    testo = mf.markdown(d)
    assert "| placeOrders | desktop | 1 | 0 | 40.0 |" in testo
    assert "20261011, 20261012" in testo
    if lettore == "m1":
        assert o["lettore"] == "M-1"
        assert o["referto_m1"] and "REGISTRO ORDINI" in o["referto_m1"]
        assert "4.3 Referto del lettore di M-1" in testo
    else:
        assert o["referto_m1"] is None
        assert "ordini: lettore M-1 assente" in testo


def test_comando_della_ui_verso_la_rest():
    """Latenza UI -> REST: il comando LIVE si accoppia alla prima REST del
    desktop dello stesso metodo dopo di lui; il paper non va a Betfair."""
    t = 1_000_000.0
    ui = [{"epoca_ms": t, "azione": "place", "modo": "live"},
          {"epoca_ms": t + 1, "azione": "place", "modo": "paper"},
          {"epoca_ms": t + 100, "azione": "cancel", "modo": "live"}]
    rest = [{"invio_ms": t - 50, "risposta_ms": t - 10, "metodo": "placeOrders",
             "attore": "desktop"},
            {"invio_ms": t + 5, "risposta_ms": t + 45, "metodo": "placeOrders",
             "attore": "desktop"},
            {"invio_ms": t + 110, "risposta_ms": t + 160, "metodo": "cancelOrders",
             "attore": "bot:omega"}]
    tab = {r["metodo"]: r for r in mf.ui_verso_rest(ui, rest)["tabella"]}
    assert (tab["placeOrders"]["comandi"], tab["placeOrders"]["accoppiati"]) == (1, 1)
    assert tab["placeOrders"]["risposta_p50"] == 45.0 and tab["placeOrders"]["invio_p50"] == 5.0
    assert (tab["cancelOrders"]["comandi"], tab["cancelOrders"]["accoppiati"]) == (1, 0), \
        "una REST di un bot non e' l'esito di un comando della UI"


def test_cartelle_utc_del_giorno_locale():
    if mf.NOME_FUSO != "Europe/Rome":
        pytest.skip("tzdata assente")
    assert mf.cartelle_utc("2026-10-12") == ["20261011", "20261012"]
    assert mf.cartelle_utc("2026-07-01") == ["20260630", "20260701"]


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
