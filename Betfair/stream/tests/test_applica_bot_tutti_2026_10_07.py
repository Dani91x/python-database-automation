"""07/10/2026 - "Applica bot" per TUTTI i bot: contratto comune.

Ordini dell'utente (07/10): <<portare TUTTI I BOT nella sezione "applica bot">> e
<<devo poter modificare i parametri di ognuno cosi' da provare altre varianti
SENZA CAMBIARE LA STRATEGIA>>.

Qui:
  * il CONTRATTO del registro: ogni bot in produzione registra il catalogo dei
    parametri (``parametri``), la sua funzione di replay accetta ``parametri`` e
    ``dal_ms``, il suo modulo espone ``ordini_specchio`` (un bot senza -> il
    test lo NOMINA);
  * il catalogo: voci con le chiavi e i tipi del contratto, default dentro il
    dominio e uguali al valore con cui lo scenario gira davvero;
  * ogni scenario del registro e' classificato (applicabile o scartato col
    motivo) e il file TS del frontend e' allineato al catalogo generato;
  * ``varianti_bot``: validazione, accensione, specchio degli ordini con
    oggetti VERI di flumine e la funzione VERA dello specchio;
  * sulla registrazione tennis VERA (se presente): con ``parametri``/``dal_ms``
    assenti la cronologia e' quella di sempre; con ``dal_ms`` nessun ordine
    prima dell'accensione; con lo stake cambiato gli ordini portano lo stake.

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import inspect
import io
import os
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from Betfair.stream.backtest import applica_bot as AB
from Betfair.stream.backtest import registro_bot as REG
from Betfair.stream.backtest import varianti_bot as VB

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
FILE_TS = os.path.join(RADICE, "frontend", "src", "lib", "replayBotCatalogo.ts")
TENNIS_DIR = os.environ.get("APPLICA_BOT_TENNIS_DIR",
                            "/home/user/python-database-automation/_live_raw_tennis")
EVENTO_TENNIS = "35790089"


def _c_e_tennis() -> bool:
    return os.path.isfile(os.path.join(TENNIS_DIR, "20260707", EVENTO_TENNIS,
                                       "%s.raw.jsonl" % EVENTO_TENNIS))


# ---------------------------------------------------------------------------
# il contratto del registro
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("scheda", REG.elenco(), ids=lambda b: b.nome)
def test_ogni_bot_in_produzione_registra_il_catalogo_dei_parametri(scheda):
    assert scheda.parametri, ("%s: bot in produzione senza `parametri` nel registro "
                              "(catalogo di Applica bot)" % scheda.nome)
    f = scheda.funzione_parametri()       # ValueError parlante se manca nel modulo
    assert callable(f), scheda.nome


@pytest.mark.parametrize("scheda", REG.elenco(), ids=lambda b: b.nome)
def test_la_funzione_di_replay_accetta_parametri_e_dal_ms(scheda):
    f = scheda.funzione_replay()
    firma = inspect.signature(f).parameters
    for nome in ("parametri", "dal_ms"):
        assert nome in firma, "%s: la funzione di replay non accetta `%s`" % (scheda.nome, nome)
        assert firma[nome].default is None, "%s: `%s` deve valere None di serie" % (
            scheda.nome, nome)


@pytest.mark.parametrize("scheda", REG.elenco(), ids=lambda b: b.nome)
def test_il_replay_espone_ordini_specchio(scheda):
    modulo = inspect.getmodule(scheda.funzione_replay())
    assert "ordini_specchio" in inspect.getsource(modulo), (
        "%s: il replay non espone `ordini_specchio` nel referto" % scheda.nome)


def test_le_safe_calcio_accendono_solo_la_loro_variante():
    for nome, var in (("safe_base", "base"), ("safe_esatto", "esatto"), ("safe_punta", "punta")):
        assert dict(REG.bot(nome).argomenti_applica) == {"strategie": (var,)}


def test_catalogo_mancante_e_un_errore_parlante():
    finto = REG.BotRegistrato(nome="x", sport="calcio", descrizione="x",
                              parametri="Betfair.stream.backtest.varianti_bot:non_esiste")
    with pytest.raises(ValueError, match="non espone ancora"):
        finto.funzione_parametri()
    senza = REG.BotRegistrato(nome="y", sport="calcio", descrizione="y")
    with pytest.raises(ValueError, match="non registra il catalogo"):
        senza.funzione_parametri()


# ---------------------------------------------------------------------------
# gli scenari
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("nome", sorted(REG.REGISTRO), ids=str)
def test_ogni_scenario_del_registro_e_classificato(nome):
    assert AB.non_classificati(nome) == [], (
        "%s: scenari del registro non classificati per Applica bot" % nome)
    registrati = set(REG.bot(nome).elenco_scenari())
    assert set(AB.SCENARI_APPLICABILI[nome]) <= registrati, "scenari non piu' nel registro"
    assert set(AB.SCENARI_SCARTATI.get(nome, {})) <= registrati
    assert not (set(AB.SCENARI_APPLICABILI[nome]) & set(AB.SCENARI_SCARTATI.get(nome, {})))
    for sc, motivo in AB.SCENARI_SCARTATI.get(nome, {}).items():
        assert motivo.strip(), (nome, sc)
    assert AB.scenari_del_bot(nome), "%s: nessuno scenario applicabile" % nome


def test_le_famiglie_hanno_al_piu_una_scenario_per_modalita():
    for nome, tavola in AB.SCENARI_APPLICABILI.items():
        visti: Dict[Any, str] = {}
        for sc, (famiglia, modalita, _n) in tavola.items():
            assert modalita in (AB.PROVA, AB.SOLDI_VERI), (nome, sc)
            k = (famiglia, modalita)
            assert k not in visti, "%s: %s e %s nella stessa famiglia e modalita'" % (
                nome, sc, visti.get(k))
            visti[k] = sc


# ---------------------------------------------------------------------------
# il catalogo dei parametri
# ---------------------------------------------------------------------------
def _cataloghi() -> List[Any]:
    out = []
    for scheda in REG.elenco():
        try:
            f = scheda.funzione_parametri()
        except ValueError:
            continue           # lo nomina il test del registro
        for sc in AB.scenari_del_bot(scheda.nome):
            out.append((scheda.nome, sc["scenario"], f))
    return out


@pytest.mark.parametrize("nome,scenario,f", _cataloghi(),
                         ids=lambda x: x if isinstance(x, str) else "")
def test_le_voci_del_catalogo_rispettano_il_contratto(nome, scenario, f):
    voci = f(scenario)
    assert voci, (nome, scenario)
    chiavi = [v["chiave"] for v in voci]
    assert len(chiavi) == len(set(chiavi)), "chiavi doppie in %s" % nome
    for v in voci:
        assert tuple(v) == VB.CHIAVI_VOCE
        assert v["tipo"] in VB.TIPI and v["gruppo"] in VB.GRUPPI
        assert v["etichetta"].strip() and v["etichetta"].isascii()
        if v["tipo"] in ("int", "float"):
            assert v["min"] <= v["default"] <= v["max"], v
            assert v["passo"] > 0, v
        elif v["tipo"] == "bool":
            assert isinstance(v["default"], bool)
        else:
            assert v["default"] in v["scelte"]
        # il default si riaccetta come sostituzione (la UI lo rimanda tale e quale)
        assert VB.valida(voci, {v["chiave"]: v["default"]}) == {v["chiave"]: v["default"]}


def test_default_di_mike_dalla_whitelist_e_dallo_scenario():
    from Betfair.mike import config as C
    from Betfair.mike.tools import replay_registrazioni as R

    base = {v["chiave"]: v for v in R.parametri_modificabili("base")}
    assert base["stake"]["default"] == C.DEFAULTS["stake"]
    assert base["stake"]["min"] == C.PARAM_SPEC["stake"][2]
    assert base["pre_exit_mode"]["scelte"] == list(C.PARAM_SPEC["pre_exit_mode"][4])
    taker = {v["chiave"]: v for v in R.parametri_modificabili("taker")}
    assert taker["pre_exit_mode"]["default"] == "taker"


def test_default_omega_seguono_il_motore_dello_scenario():
    from Betfair.omega.tools import replay_registrazioni as R

    v4 = {v["chiave"] for v in R.parametri_modificabili("v4")}
    v2 = {v["chiave"]: v for v in R.parametri_modificabili("apertura")}
    assert "v3_stake_eur" in v4 and "price_max" not in v4
    assert v2["price_max"]["default"] == 500.0          # lo scenario allarga la banda
    assert v2["daily_goal"]["default"] == R.GOAL_UNA_PARTITA


def test_default_tennis_dall_istanza_vera_del_bot():
    from Betfair.stream.tennis_live.tools import replay_bot as R

    base = {v["chiave"]: v["default"] for v in R.parametri_modificabili_tennis_swing("base")}
    aperto = {v["chiave"]: v["default"]
              for v in R.parametri_modificabili_tennis_swing("gate-aperto")}
    assert base["zin"] == 2.0 and aperto["zin"] == 1.0        # lo scenario apre i gate
    s = R._bot_dello_scenario("tennis_swing", "base")
    assert base["er_max"] == s.er_max and base["stake"] == s.stake


# ---------------------------------------------------------------------------
# varianti_bot: validazione e accensione
# ---------------------------------------------------------------------------
_CAT = [VB.voce("a", "A", "int", 3, gruppo="Ingresso", minimo=1, massimo=5, passo=1),
        VB.voce("b", "B", "float", 1.5, gruppo="Uscita", minimo=1.01, massimo=2.0, passo=0.01),
        VB.voce("c", "C", "bool", True, gruppo="Filtri"),
        VB.voce("d", "D", "scelta", "x", gruppo="Uscita", scelte=("x", "y"))]


@pytest.mark.parametrize("par,msg", [
    ({"z": 1}, "non modificabili"),
    ({"a": 6}, "fuori dal dominio"),
    ({"a": 0}, "fuori dal dominio"),
    ({"a": 2.5}, "intero"),
    ({"a": True}, "numero"),
    ({"b": "1.6"}, "numero"),
    ({"b": float("nan")}, "non finito"),
    ({"c": 1}, "vero/falso"),
    ({"d": "w"}, "scelte"),
])
def test_valida_rifiuta_con_motivo(par, msg):
    with pytest.raises(ValueError, match=msg):
        VB.valida(_CAT, par)


def test_valida_accetta_e_parametri_usati():
    assert VB.valida(_CAT, None) == {}
    s = VB.valida(_CAT, {"a": 5, "b": 1.01, "c": False, "d": "y"})
    assert s == {"a": 5, "b": 1.01, "c": False, "d": "y"} and isinstance(s["a"], int)
    assert VB.parametri_usati(_CAT, {"a": 4}) == {"a": 4, "b": 1.5, "c": True, "d": "x"}


def test_voce_incoerente_non_arriva_alla_ui():
    with pytest.raises(ValueError):
        VB.voce("a", "A", "int", 9, gruppo="Ingresso", minimo=1, massimo=5, passo=1)
    with pytest.raises(ValueError):
        VB.voce("a", "A", "int", 1, gruppo="Inventato", minimo=1, massimo=5, passo=1)


def test_accensione():
    acc = VB.Accensione(1000)
    assert not acc.acceso(999) and acc.acceso(1000)
    assert not acc.scatta(999) and acc.scatta(1500) and not acc.scatta(2000)
    assert acc.scattata_ms == 1500
    sempre = VB.Accensione(None)
    assert sempre.acceso(0) and not sempre.scatta(10) and not sempre.attiva
    for brutto in (-1, 1.5, "3", True):
        with pytest.raises(ValueError):
            VB.controlla_dal_ms(brutto)


def test_applica_annidato_non_butta_la_sezione():
    par = {"esatto": {"requireSelection": True}, "variants": ["esatto"]}
    VB.applica_annidato(par, "esatto.minuteMin", 50)
    VB.applica_annidato(par, "exits.esatto_exit_minute", 70)
    assert par["esatto"] == {"requireSelection": True, "minuteMin": 50}
    assert par["exits"] == {"esatto_exit_minute": 70}
    assert VB.leggi_annidato(par, "esatto.minuteMin") == 50
    assert VB.leggi_annidato(par, "esatto.nulla") is None


# ---------------------------------------------------------------------------
# lo specchio: ordini VERI di flumine, funzione VERA dello specchio
# ---------------------------------------------------------------------------
def _ordine_vero(strategia: Any, mercato: str, lato: str, prezzo: float, size: float,
                 utente: bool = False) -> Any:
    from flumine.order.ordertype import LimitOrder
    from flumine.order.trade import Trade

    t = Trade(market_id=mercato, selection_id=47972, handicap=0.0, strategy=strategia)
    o = t.create_order(side=lato, order_type=LimitOrder(price=prezzo, size=size,
                                                        persistence_type="LAPSE"))
    if utente:
        o.notes["utente"] = True
    return o


def test_specchio_ordini_righe_del_vero_e_cambi_di_stato():
    from flumine import BaseStrategy
    from flumine.markets.blotter import Blotter

    from Betfair.stream.engine.live_trading_strategy import LiveTradingStrategy

    s = BaseStrategy(market_filter={}, name="prova")
    bl = Blotter("1.1")
    mercato = SimpleNamespace(market_id="1.1", event_id="E1", blotter=bl)
    o1 = _ordine_vero(s, "1.1", "BACK", 2.0, 4.0)
    ou = _ordine_vero(s, "1.1", "LAY", 2.0, 3.0, utente=True)
    bl[o1.id] = o1
    bl[ou.id] = ou
    sp = VB.SpecchioOrdini(sorgente="mike", modo="live", event_id="E1")
    sp.osserva_mercato(mercato, 500)                   # status None: non e' una riga
    o1.placing()
    ou.placing()                                       # l'ordine dell'utente e' VIVO: fuori lo stesso
    sp.osserva_mercato(mercato, 1000)
    sp.osserva_mercato(mercato, 2000)                  # niente cambiato: nessuna riga
    o1.executable()
    sp.osserva_mercato(mercato, 3000)
    o1.execution_complete()
    sp.osserva_mercato(mercato, 4000)
    righe = sp.chiudi([mercato], 5000)
    attese = LiveTradingStrategy._order_row(SimpleNamespace(mode="live"), o1,
                                            event_id="E1", market_id="1.1")
    assert set(righe[0]) == set(attese) | {"source", "_ms"}
    for k, v in attese.items():                        # stessi tipi del vero
        assert type(righe[-1][k]) is type(v), k
    assert [r["_ms"] for r in righe] == [1000, 3000, 4000]
    assert [r["status"] for r in righe] == ["PENDING", "EXECUTABLE", "EXECUTION_COMPLETE"]
    assert all(r["source"] == "mike" and r["mode"] == "live" for r in righe)
    assert all(r["client_order_ref"] == attese["client_order_ref"] for r in righe)


def test_specchio_aggancio_al_motore_legge_soltanto():
    sp = VB.SpecchioOrdini(sorgente="omega", modo="paper", event_id="E")
    visti: List[Any] = []
    sp.osserva_mercato = lambda m, ms: visti.append((m, ms))  # type: ignore[assignment]
    from datetime import datetime, timezone

    mercato = object()
    motore = SimpleNamespace(_ora_mercato=datetime(2026, 1, 1, tzinfo=timezone.utc),
                             _a_flumine=lambda mb: (mercato, False))
    sp.aggancia(motore)
    assert motore._a_flumine("book") == (mercato, False)
    assert visti == [(mercato, 1767225600000)]
    motore._a_flumine = lambda mb: (None, False)
    sp.aggancia(motore)
    assert motore._a_flumine("book") == (None, False) and len(visti) == 1


# ---------------------------------------------------------------------------
# applica_bot: richieste non valide, cartella tennis, file TS
# ---------------------------------------------------------------------------
def _registrazione_finta(radice, giorno: str, ev: str) -> str:
    d = radice / giorno / ev
    d.mkdir(parents=True)
    (d / ("%s.raw.jsonl" % ev)).write_text("")
    return str(radice / giorno)


@pytest.mark.parametrize("params,msg", [
    ({"bot": "inventato", "scenario": "base", "event_id": "1"}, "non applicabile"),
    ({"bot": "mike", "scenario": "riavvio", "event_id": "1"}, "guasto o trasporto"),
    ({"bot": "omega", "scenario": "inventato", "event_id": "1"}, "scenario non disponibile"),
    ({"bot": "mike", "scenario": "base", "event_id": ""}, "event_id mancante"),
])
def test_richieste_non_valide(params, msg):
    with pytest.raises(ValueError, match=msg):
        AB.esegui(params)


def test_parametro_non_ammesso_rifiutato_prima_di_partire(tmp_path, monkeypatch):
    cartella = _registrazione_finta(tmp_path, "x", "777")
    chiamate: List[Any] = []
    scheda = REG.bot("mike")
    monkeypatch.setattr(REG.BotRegistrato, "funzione_replay",
                        lambda self: (lambda *a, **k: chiamate.append(k)))
    with pytest.raises(ValueError, match="non modificabili"):
        AB.esegui({"bot": "mike", "scenario": "base", "event_id": "777",
                   "parametri": {"inventato": 1}}, data_dir=cartella)
    with pytest.raises(ValueError, match="fuori dal dominio"):
        AB.esegui({"bot": "mike", "scenario": "base", "event_id": "777",
                   "parametri": {"stake": 10000.0}}, data_dir=cartella)
    assert chiamate == [] and scheda.nome == "mike"


def test_argomenti_passati_alla_funzione_di_replay(tmp_path, monkeypatch):
    cartella = _registrazione_finta(tmp_path, "x", "778")
    chiamate: List[Dict[str, Any]] = []

    def replay(event_id, *, data_dir, scenario="base", ogni_ms=0, campioni_diff=0,
               strategie=None, parametri=None, dal_ms=None):
        chiamate.append(dict(event_id=event_id, data_dir=data_dir, scenario=scenario,
                             strategie=strategie, parametri=parametri, dal_ms=dal_ms))
        return SimpleNamespace(note=["ACCENSIONE dell'utente a ..."], violazioni=[],
                               ordini_specchio=[{"client_order_ref": "r", "_ms": 5,
                                                 "status": "EXECUTABLE"}])

    monkeypatch.setattr(REG.BotRegistrato, "funzione_replay", lambda self: replay)
    esito = AB.esegui({"bot": "safe_esatto", "scenario": "base", "event_id": "778",
                       "parametri": {"esatto.minuteMin": 50}, "dal_ms": 1234},
                      data_dir=cartella)
    assert chiamate == [dict(event_id="778", data_dir=cartella, scenario="base",
                             strategie=("esatto",), parametri={"esatto.minuteMin": 50},
                             dal_ms=1234)]
    assert esito["parametri_cambiati"] == {"esatto.minuteMin": 50}
    assert esito["parametri_usati"]["esatto.minuteMin"] == 50
    assert esito["dal_ms"] == 1234 and esito["ordini"] == 1
    assert esito["accensione"].startswith("ACCENSIONE")
    # senza parametri e senza dal_ms: la chiamata di sempre (piu' la variante Safe)
    chiamate.clear()
    AB.esegui({"bot": "safe_esatto", "scenario": "base", "event_id": "778"},
              data_dir=cartella)
    assert chiamate[0]["parametri"] is None and chiamate[0]["dal_ms"] is None
    # clic_ms a un bot che non lo dichiara: rifiutato col motivo
    with pytest.raises(ValueError, match="non accetta ancora `clic_ms`"):
        AB.esegui({"bot": "safe_esatto", "scenario": "base", "event_id": "778",
                   "clic_ms": [10]}, data_dir=cartella)


def test_cartella_tennis_trova_il_giorno_della_partita(tmp_path):
    giorno = _registrazione_finta(tmp_path, "20260707", "35790089")
    _registrazione_finta(tmp_path, "20260801", "1")
    reg = REG.bot("tennis_flb")
    assert AB.cartella_della_partita(reg, "35790089", str(tmp_path)) == giorno
    assert AB.cartella_della_partita(reg, "35790089", giorno) == giorno
    calcio = REG.bot("mike")
    assert AB.cartella_della_partita(calcio, "35790089", str(tmp_path)) == str(tmp_path)


def test_il_file_ts_del_catalogo_e_allineato_al_registro():
    assert os.path.isfile(FILE_TS), "manca %s: rigeneralo" % FILE_TS
    atteso = AB.catalogo_ts()
    reale = io.open(FILE_TS, encoding="utf-8").read()
    assert reale == atteso, ("frontend/src/lib/replayBotCatalogo.ts NON e' allineato al "
                             "registro: python -m Betfair.stream.backtest.applica_bot "
                             "--catalogo-ts > frontend/src/lib/replayBotCatalogo.ts")


def test_il_catalogo_separa_gli_sport():
    cat = {v["bot"]: v for v in AB.catalogo()}
    assert {b for b, v in cat.items() if v["sport"] == "tennis"} == {
        "safe_tennis", "tennis_scalper", "tennis_pro", "tennis_flb", "tennis_swing"}
    assert {b for b, v in cat.items() if v["sport"] == "calcio"} == {
        "mike", "omega", "safe_base", "safe_esatto", "safe_punta", "scalper_calcio"}


# ---------------------------------------------------------------------------
# la STRADA dei parametri e dell'accensione in ogni modulo di replay: la
# funzione del banco riceve i parametri dello scenario CON le sostituzioni,
# nella forma della riga di controllo di produzione
# ---------------------------------------------------------------------------
def _cattura(monkeypatch, modulo, nome="certifica_evento"):
    visti: List[Dict[str, Any]] = []

    def finto(*a, **k):
        visti.append(dict(k, _a=a))
        return SimpleNamespace(note=[], non_esercitato=[], sollecitati={}, contatori={})

    monkeypatch.setattr(modulo, nome, finto)
    return visti


def test_mike_parametri_e_accensione_arrivano_al_control(monkeypatch):
    from Betfair.mike.tools import replay_registrazioni as R

    visti = _cattura(monkeypatch, R)
    R.certifica_scenario("1", data_dir="x", scenario="taker",
                         parametri={"stake": 4.0, "pre_green_ticks": 3}, dal_ms=99)
    assert visti[0]["params"]["stake"] == 4.0 and visti[0]["params"]["pre_green_ticks"] == 3
    assert visti[0]["params"]["pre_exit_mode"] == "taker"      # lo scenario resta
    assert visti[0]["dal_ms"] == 99
    R.certifica_scenario("1", data_dir="x", scenario="base")
    assert visti[1]["params"] == R._parametri_dello_scenario("base") and visti[1]["dal_ms"] is None
    with pytest.raises(ValueError, match="minimo supera il massimo"):
        R.certifica_scenario("1", data_dir="x", parametri={"pre_entry_price_min": 2.9,
                                                            "pre_entry_price_max": 2.0})


def test_omega_parametri_obiettivo_e_accensione(monkeypatch):
    from Betfair.omega.tools import replay_registrazioni as R

    visti = _cattura(monkeypatch, R)
    R.certifica_scenario("1", data_dir="x", scenario="apertura",
                         parametri={"daily_goal": 20.0, "price_max": 300.0}, dal_ms=7)
    assert visti[0]["goal"] == 20.0 and visti[0]["params"]["price_max"] == 300.0
    assert visti[0]["dal_ms"] == 7
    R.certifica_scenario("1", data_dir="x", scenario="v4")
    assert visti[1]["dal_ms"] is None and visti[1]["params"]["strategy_version"] == 3


def test_safe_parametri_nella_sezione_della_variante(monkeypatch):
    from Betfair.safe_strategy.tools import replay_registrazioni as R

    visti = _cattura(monkeypatch, R)
    R.certifica_scenario("1", data_dir="x", scenario="base", strategie=("esatto",),
                         parametri={"esatto.minuteMin": 50, "exits.esatto_exit_minute": 70},
                         dal_ms=5)
    par = visti[0]["params_grezzi"]
    assert par["esatto"]["minuteMin"] == 50 and par["exits"]["esatto_exit_minute"] == 70
    assert par["variants"] == ["esatto"] and visti[0]["dal_ms"] == 5
    with pytest.raises(ValueError, match="UNA variante"):
        R.certifica_scenario("1", data_dir="x", parametri={"esatto.minuteMin": 50})
    with pytest.raises(ValueError, match="non modificabili"):
        R.certifica_scenario("1", data_dir="x", strategie=("punta",),
                             parametri={"esatto.minuteMin": 50})


def test_safe_tennis_parametri_e_accensione(monkeypatch, tmp_path):
    from Betfair.safe_strategy.tools import replay_tennis as R

    visti: List[Dict[str, Any]] = []
    monkeypatch.setattr(R, "replay_evento", lambda **k: visti.append(k) or SimpleNamespace())
    monkeypatch.setattr(R, "giri_dopo_il_fischio", lambda *a, **k: 0)
    monkeypatch.setattr(R._Stato, "chiudi", lambda self, esito: None)
    d = tmp_path / "1"
    d.mkdir()
    (d / "1.raw.jsonl").write_text("")
    ref = R.certifica_scenario("1", data_dir=str(tmp_path), scenario="base",
                               parametri={"tennis.backMax": 1.2}, dal_ms=3)
    db = visti[0]["db"]
    assert db.control["params"]["tennis"]["backMax"] == 1.2
    assert db.control["status"] == "stopped"          # acceso solo a dal_ms
    assert ref.ordini_specchio == []
    visti.clear()
    R.certifica_scenario("1", data_dir=str(tmp_path), scenario="base")
    assert visti[0]["db"].control["status"] == "running"


# ---------------------------------------------------------------------------
# sulla registrazione tennis VERA (banco comune, codice di produzione)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def tennis_di_serie():
    if not _c_e_tennis():
        pytest.skip("registrazione tennis 35790089 assente")
    return AB.esegui({"bot": "tennis_scalper", "scenario": "gate-aperto",
                      "event_id": EVENTO_TENNIS}, data_dir=TENNIS_DIR)


@pytest.mark.cert
def test_tennis_cronologia_di_serie(tennis_di_serie):
    e = tennis_di_serie
    assert e["ordini"] > 10 and e["violazioni"] == []
    assert e["parametri_cambiati"] == {} and e["dal_ms"] is None
    assert all(r["source"] == "tennis_scalper" and r["mode"] == "paper" for r in e["righe"])
    assert [r["_ms"] for r in e["righe"]] == sorted(r["_ms"] for r in e["righe"])


@pytest.mark.cert
def test_tennis_accensione_e_stake(tennis_di_serie):
    primo = min(r["_ms"] for r in tennis_di_serie["righe"])
    dal = primo + 30 * 60 * 1000
    e = AB.esegui({"bot": "tennis_scalper", "scenario": "gate-aperto",
                   "event_id": EVENTO_TENNIS, "dal_ms": dal,
                   "parametri": {"stake": 4.0}}, data_dir=TENNIS_DIR)
    assert e["righe"], "acceso a meta' partita il bot deve ancora operare"
    assert min(r["_ms"] for r in e["righe"]) >= dal
    assert e["parametri_cambiati"] == {"stake": 4.0}
    aperture = [r for r in e["righe"] if r["status"] == "PENDING"]
    assert aperture and aperture[0]["size"] == 4.0
    assert e["accensione"] and "NON esisteva" in e["accensione"]


# ---------------------------------------------------------------------------
# Mike acceso a meta' pre-partita sulla registrazione calcio VERA (lungo: ~3 min,
# solo con APPLICA_BOT_LUNGHI=1). Il 07/10, senza la correzione dei parametri del
# giro (``service._params_for`` a bot spento), la punta partiva 1 minuto PRIMA
# dell'accensione: questa prova era rossa.
# ---------------------------------------------------------------------------
CALCIO_DIR = "/home/user/python-database-automation/_live_raw"


@pytest.mark.cert
@pytest.mark.skipif(os.environ.get("APPLICA_BOT_LUNGHI") != "1"
                    or not os.path.isfile(os.path.join(CALCIO_DIR, "35797769",
                                                       "35797769.raw.jsonl")),
                    reason="prova lunga: APPLICA_BOT_LUNGHI=1 e registrazione 35797769")
def test_mike_acceso_dopo_il_suo_ingresso_non_entra_prima():
    dal = 1783706460890                     # un minuto dopo l'ingresso di serie (18:00:00,890)
    e = AB.esegui({"bot": "mike", "scenario": "base", "event_id": "35797769",
                   "dal_ms": dal}, data_dir=CALCIO_DIR)
    assert e["righe"] and min(r["_ms"] for r in e["righe"]) >= dal
    assert e["accensione"].startswith("ACCENSIONE")
