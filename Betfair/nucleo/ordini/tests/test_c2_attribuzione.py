"""W1-C2 - attribuzione degli ordini del conto: PARITA' con la classificazione di oggi.

La tabella dei riferimenti NON e' scritta a mano: ``riferimenti_di_oggi()`` li
genera chiamando il codice di produzione che li scrive (motore, worker calcio e
tennis, bot REST, porte, scalper, flumine). Per ognuno si confronta l'autore con:
  (a) ``esposizione_fuori_bot.motivo_bot_da_riferimenti`` + ``bot_di`` (W2/W3a);
  (b) ``reconcile_worker._classify_cleared_order`` (classificazione storica R1);
e le DIVERGENZE sono un elenco CHIUSO (``DIVERGENZE_ATTESE``), ciascuna scritta
nel referto W1-C2 par. 9: una divergenza nuova fa diventare rosso il test.
ASCII-only.
"""
from __future__ import annotations

import ast
import pathlib
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

import pytest
from flumine import BaseStrategy
from flumine.order.ordertype import LimitOrder
from flumine.order.trade import Trade

from Betfair.nucleo.ordini import attribuzione as A
from Betfair.nucleo.ordini.tests.test_c2_aiuti import (Registro, client_supabase, correnti,
                                                       dal_conto, ordine_json)

RADICE = pathlib.Path(__file__).resolve().parents[4]
EVENTO = "34567890"


def _cor_flumine(nome: str) -> str:
    """Il customerOrderRef che flumine scrive per un ordine della strategia
    ``nome`` (``Order.customer_order_ref``: name_hash + sep + id)."""
    s = BaseStrategy(market_filter={}, name=nome)
    t = Trade(market_id="1.1", selection_id=1, handicap=0.0, strategy=s)
    o = t.create_order(side="BACK", order_type=LimitOrder(price=2.0, size=2.0))
    return str(o.customer_order_ref)


def _csr_flumine_senza_nome(nome_classe: str) -> str:
    """Il customerStrategyRef di una strategia SENZA ``name`` (i bot tennis):
    ``flumine/markets/market.py`` ``str(order.trade.strategy)[:15]``."""
    cls = type(nome_classe, (BaseStrategy,), {})
    return str(cls(market_filter={}))[:15]


def riferimenti_di_oggi() -> List[Tuple[str, Optional[str], Optional[str]]]:
    """(origine, customerStrategyRef, customerOrderRef) di OGNI percorso che
    oggi piazza un ordine, generati dal codice di produzione."""
    from Betfair.mike import config as mike_config
    from Betfair.mike import porta_ordini as mpo
    from Betfair.omega import omega_engine, omega_market
    from Betfair.safe_strategy import bot_service
    from Betfair.safe_strategy import porta_ordini as spo
    from Betfair.stream import live_order_worker as low
    from Betfair.stream import motore_ordini
    from Betfair.stream.scalper import scalper_session
    from Betfair.stream.tennis_live import tennis_live_order_worker as tlow
    from Betfair.stream.tennis_live import tennis_runner

    out: List[Tuple[str, Optional[str], Optional[str]]] = []
    cor_runner = _cor_flumine("LiveTradingStrategy")
    out.append(("runner calcio coda/desktop", low._strategy_ref_corrente(), cor_runner))
    out.append(("runner tennis coda/desktop", tlow._strategy_ref(), _cor_flumine("tennis")))
    for attore in sorted(motore_ordini.ATTORI_COMANDO):
        low._CONTESTO.strategy_ref = attore
        try:
            out.append((f"motore calcio attore {attore}", low._strategy_ref_corrente(), cor_runner))
            out.append((f"motore tennis attore {attore}", tlow._strategy_ref(), cor_runner))
        finally:
            low._CONTESTO.strategy_ref = None
    ref_omega = omega_market.ref_di_strategia(None)
    out.append(("omega REST gamba", ref_omega, omega_engine.customer_ref_for(7)))
    for tr in ({"id": 7, "origin": "manual"}, {"id": 7, "event_id": EVENTO}):
        for c in omega_engine.candidate_customer_refs(tr):
            out.append(("omega REST storico", ref_omega, c))
    out.append(("omega REST default", ref_omega, f"omega-{EVENTO}"))
    out.append(("omega REST submin default", ref_omega, f"submin-{EVENTO}"))
    out.append(("mike REST", omega_market.ref_di_strategia(mike_config.CUSTOMER_STRATEGY_REF),
                mpo.ref_ordine(7)))
    out.append(("safe calcio REST", omega_market.ref_di_strategia(bot_service.SAFE_STRATEGY_REF),
                spo.ref_ordine(7, "calcio")))
    out.append(("safe tennis REST", omega_market.ref_di_strategia(bot_service.SAFE_STRATEGY_REF),
                spo.ref_ordine(7, "tennis")))
    for storico in bot_service._SAFE_REFS_STORICI:
        out.append(("safe calcio REST storico", storico, spo.ref_ordine(7, "calcio")))
        out.append(("safe tennis REST storico", storico, spo.ref_ordine(7, "tennis")))
    out.append(("mike REST storico (pre L1)", ref_omega, mpo.ref_ordine(7)))
    for ruolo in sorted(scalper_session.PREFISSI_STRATEGIA):
        nome = scalper_session.nome_strategia(ruolo, EVENTO)
        out.append((f"scalper {ruolo}", nome, _cor_flumine(nome)))
    for chiave, voce in sorted(tennis_runner._BOT_REGISTRY.items()):
        nome = voce[0].__name__
        out.append((f"bot tennis {chiave} in flumine", _csr_flumine_senza_nome(nome),
                    _cor_flumine(nome)))
    out.append(("terminale vecchio order_exec", "watchlist", None))
    out.append(("sito Betfair", None, None))
    return out


#: autore atteso per origine (scritto qui: e' la SPECIFICA; la parita' con oggi
#: e' sotto)
def _atteso(origine: str) -> str:
    if origine.startswith(("runner calcio", "runner tennis")):
        return "desktop"
    if origine.startswith(("motore calcio attore ", "motore tennis attore ")):
        return origine.rsplit(" ", 1)[1]
    if origine.startswith(("omega REST",)):
        return "omega"
    if origine.startswith("mike REST"):
        return "mike"
    if origine.startswith("safe calcio"):
        return "safe"
    if origine.startswith("safe tennis"):
        return "safe_tennis"
    if origine.startswith("scalper"):
        return "scalper"
    if origine.startswith("bot tennis"):
        return origine.split()[2]
    if origine.startswith("sito"):
        return "sito"
    return "sconosciuto"


#: (origine) -> tipo di divergenza con la classificazione di oggi. ELENCO CHIUSO:
#: ognuna e' nel referto W1-C2 par. 9 (D1..D4).
DIVERGENZE_ATTESE: Dict[str, str] = {
    # D1: il desktop dal motore scrive customerStrategyRef "desktop": W2 lo dice
    # "di un bot" (strategia:desktop), R1 storico "ours"
    "motore calcio attore desktop": "D1",
    "motore tennis attore desktop": "D1",
    # D2: stesso esito "di un bot", NOME piu' preciso di bot_di() (che usa il
    # solo customerStrategyRef): il customerOrderRef decide come nella lettura
    # di Safe (bot_service._SAFE_REFS_STORICI + _SAFE_PREFISSI_ORDINE) e come
    # mike/service._bind_strategy_ref documenta per Mike prima di L1
    "safe tennis REST": "D2",
    "safe calcio REST storico": "D2",
    "safe tennis REST storico": "D2",
    "mike REST storico (pre L1)": "D2",
    # D3: il terminale vecchio: oggi "altri_bot"/bot; qui sconosciuto
    "terminale vecchio order_exec": "D3",
    # D5: il terminale manuale TENNIS ("tennis"): la regola calcio di W2
    # (motivo_bot_da_riferimenti, che ammette solo "live") lo dice di un bot;
    # il tennis W3b (ordini_esterni.classifica, rif_manuali) e R1 dicono utente.
    # Qui: desktop (come W3b e R1). Divergenza GIA' presente fra due funzioni di oggi.
    "runner tennis coda/desktop": "D5",
}


def _oggi(csr: Optional[str], cor: Optional[str]) -> Tuple[Optional[str], str]:
    """(nome del bot per W2 o None se dell'utente, classe storica di R1)."""
    from Betfair.stream import reconcile_worker as rw
    from Betfair.stream.trading import esposizione_fuori_bot as efb

    motivo = efb.motivo_bot_da_riferimenti({"customerStrategyRef": csr,
                                            "customerOrderRef": cor})
    co = correnti(ordine_json("1", "BACK", 0.0, 2.0, csr=csr, cor=cor, residuo=2.0))[0]
    return (efb.bot_di(motivo) if motivo else None), rw._classify_cleared_order(co)


def tabella_parita() -> List[Dict[str, Any]]:
    righe = []
    for origine, csr, cor in riferimenti_di_oggi():
        a = A.attribuisci_riferimenti(csr, cor)
        w2, r1 = _oggi(csr, cor)
        righe.append({"origine": origine, "csr": csr, "cor": cor, "autore": a.autore,
                      "motivo": a.motivo, "w2": w2 or "utente", "r1": r1,
                      "divergenza": DIVERGENZE_ATTESE.get(origine, "")})
    return righe


def _concorda(autore: str, w2: Optional[str], r1: str) -> bool:
    utente = autore in A.AUTORI_UTENTE
    if utente != (w2 is None):
        return False
    if w2 is not None and w2 in A.AUTORI and w2 != autore:
        return False
    attesa_r1 = {"desktop": "manual_app", "sito": "manual", "sconosciuto": "ambiguous"}.get(
        autore, "ours")
    return r1 == attesa_r1


def test_tabella_generata_copre_ogni_percorso_e_ogni_autore():
    righe = riferimenti_di_oggi()
    assert len(righe) >= 40
    from Betfair.stream import motore_ordini

    origini = {r[0] for r in righe}
    for attore in motore_ordini.ATTORI_COMANDO:
        assert f"motore calcio attore {attore}" in origini
    autori = {A.attribuisci_riferimenti(c, o).autore for _, c, o in righe}
    # tutti gli autori del contratto tranne "risk" (solo da indizio: la coda)
    assert autori == set(A.AUTORI) - {"risk"}


@pytest.mark.parametrize("origine,csr,cor", riferimenti_di_oggi())
def test_autore_di_ogni_riferimento_di_oggi(origine, csr, cor):
    a = A.attribuisci_riferimenti(csr, cor)
    assert a.autore == _atteso(origine), (origine, csr, cor, a)
    assert a.conflitto is None


@pytest.mark.parametrize("origine,csr,cor", riferimenti_di_oggi())
def test_parita_con_la_classificazione_di_oggi(origine, csr, cor):
    a = A.attribuisci_riferimenti(csr, cor)
    w2, r1 = _oggi(csr, cor)
    if origine in DIVERGENZE_ATTESE:
        assert not _concorda(a.autore, w2, r1), f"divergenza {origine} sparita: aggiornare"
    else:
        assert _concorda(a.autore, w2, r1), (origine, csr, cor, a.autore, w2, r1)


def test_regole_dalle_costanti_di_oggi():
    from Betfair.mike import config as mike_config
    from Betfair.omega import omega_config
    from Betfair.safe_strategy import bot_service
    from Betfair.stream import live_order_worker as low
    from Betfair.stream import motore_ordini
    from Betfair.stream import reconcile_worker as rw
    from Betfair.stream.tennis_live import tennis_live_order_worker as tlow
    from Betfair.stream.tennis_scalper import ordini_esterni as oe
    from Betfair.stream.trading import esposizione_fuori_bot as efb

    r = A.regole_di_oggi()
    assert r.rif_manuali == {low.CUSTOMER_STRATEGY_REF, tlow.CUSTOMER_STRATEGY_REF}
    assert r.rif_manuali == set(rw._MANUAL_APP_STRATEGY_REFS)
    assert r.rif_manuali == {oe.RIF_MANUALE_CALCIO, oe.RIF_MANUALE_TENNIS}
    assert set(motore_ordini.ATTORI_COMANDO) <= set(r.rif_attori.values())
    for ref, bot in ((omega_config.CUSTOMER_STRATEGY_REF, "omega"),
                     (mike_config.CUSTOMER_STRATEGY_REF, "mike"),
                     (bot_service.SAFE_STRATEGY_REF, "safe")):
        assert r.rif_attori[ref] == bot
    assert set(rw._REF_BOT_CON_TABELLA) <= set(r.rif_attori)
    assert {p for p, _ in r.prefissi_ref} == set(efb.prefissi_ref_bot())
    assert set(r.tabelle_bot) == set(efb.TABELLE_BOT) == set(rw._TABELLE_BOT)
    assert set(r.rif_attori.values()) | set(r.rif_classi_flumine.values()) <= set(A.AUTORI)
    assert A.regole_di_oggi() is r                    # una volta per processo


def _client_ref_letterali(percorso: pathlib.Path) -> List[str]:
    """I prefissi letterali dei ``client_ref`` scritti in un sorgente
    (chiave ``"client_ref"`` di un dict o argomento ``client_ref=``)."""
    albero = ast.parse(percorso.read_text(encoding="utf-8"))
    out: List[str] = []

    def _prefisso(v: ast.AST) -> Optional[str]:
        if isinstance(v, ast.JoinedStr) and v.values and isinstance(v.values[0], ast.Constant):
            return str(v.values[0].value)
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            return v.value
        return None

    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.Dict):
            for k, v in zip(nodo.keys, nodo.values):
                if isinstance(k, ast.Constant) and k.value == "client_ref":
                    p = _prefisso(v)
                    if p is not None:
                        out.append(p)
        if isinstance(nodo, ast.keyword) and nodo.arg == "client_ref":
            p = _prefisso(nodo.value)
            if p is not None:
                out.append(p)
    return out


def test_prefisso_del_risk_engine_ricavato_dai_sorgenti():
    """Il prefisso ``risk`` non e' una costante del codice di oggi: si ricava dai
    ``client_ref`` letterali del risk engine; nessun altro produttore lo usa."""
    risk = _client_ref_letterali(RADICE / "Betfair/stream/risk_engine_worker.py")
    assert len(risk) >= 7
    assert all(p.startswith(A.PREFISSO_CODA_RISCHIO) for p in risk), risk
    altri = []
    for f in (RADICE / "Betfair").rglob("*.py"):
        s = str(f)
        if ("/tests/" in s or "/test_" in s or "laboratorio" in s or "/backtest/" in s
                or f.name == "risk_engine_worker.py" or "/nucleo/" in s):
            continue
        try:
            altri += [(f.name, p) for p in _client_ref_letterali(f)]
        except SyntaxError:
            continue
    assert altri, "nessun altro produttore trovato: il test non vedrebbe niente"
    assert not [x for x in altri if x[1].startswith(A.PREFISSO_CODA_RISCHIO)], altri


def test_indizi_coda_risk_attore_source():
    o = dal_conto(ordine_json("5", "LAY", 2.0, 3.0, csr="live", cor="abc-1"))
    assert A.attribuisci(o).autore == "desktop"
    assert A.attribuisci(o, A.indizi_da_riga_coda({"client_ref": "risk12s", "params": {}})).autore == "risk"
    assert A.attribuisci(o, A.indizi_da_riga_coda(
        {"client_ref": "local3", "params": {"comando": {"attore": "omega"}}})).autore == "omega"
    assert A.attribuisci(o, A.indizi_da_riga_coda(
        {"client_ref": "local3", "params": {"source": "scalper"}})).autore == "scalper"
    assert A.attribuisci(o, A.indizi_da_riga_coda({"client_ref": "mike-t4", "params": {}})).autore == "mike"
    assert A.indizi_da_riga_coda({"client_ref": "local3", "params": {}}) == ()
    assert A.indizi_da_riga_coda({"client_ref": "ft3m1.2r0", "params": {}}) == ()


def test_indizi_tabella_vince_e_il_conflitto_si_scrive():
    # Safe via REST col ref di Omega SENZA il suo customerOrderRef: la tabella non mente
    o = dal_conto(ordine_json("6", "BACK", 2.0, 3.0, csr="omega", cor="omega-34567890"))
    assert A.attribuisci(o).autore == "omega"
    a = A.attribuisci(o, [A.indizio_da_riga_bot("safe_strategy_trades", {"bet_id": "6"})])
    assert (a.autore, a.fonte) == ("safe", "indizio")
    assert a.conflitto and "omega" in a.conflitto
    # tabella di Safe + ordine del terminale tennis: e' Safe tennis
    t = dal_conto(ordine_json("7", "BACK", 2.0, 3.0, csr="tennis", cor="x-1"))
    assert A.attribuisci(t, [A.Indizio("tabella", "safe_strategy_trades")]).autore == "safe_tennis"
    # riga "utente" di mike_trades: resta dell'utente (reconcile_worker._proprietari)
    u = dal_conto(ordine_json("8", "BACK", 2.0, 3.0))
    a = A.attribuisci(u, [A.indizio_da_riga_bot("mike_trades", {"bet_id": "8", "role": "utente"})])
    assert a.autore == "sito"
    # specchio: runner/account non spostano; scalper e bot:<csr> si'
    assert A.attribuisci(u, [A.Indizio("specchio", "account")]).autore == "sito"
    assert A.attribuisci(u, [A.Indizio("specchio", "scalper")]).autore == "scalper"
    assert A.attribuisci(u, [A.Indizio("specchio", "bot:TennisProStrate")]).autore == "tennis_pro"
    assert A.attribuisci(u, [A.Indizio("specchio_tennis", "tennis_flb")]).autore == "tennis_flb"
    assert A.attribuisci(u, [A.Indizio("specchio_tennis", "manual")]).autore == "sito"


def test_indizi_dai_motivi_della_lettura_di_oggi_sul_client_vero():
    """``esposizione_fuori_bot.proprietari_bot`` (client supabase VERO su
    MockTransport) -> motivi -> indizi -> stesso bot di ``bot_di``."""
    from Betfair.stream.trading import esposizione_fuori_bot as efb

    def risposte(req):
        u = str(req.url)
        if "omega_trades" in u:
            return [{"bet_id": "11"}]
        if "betfair_live_orders" in u:
            return [{"bet_id": "12", "source": "scalper"}, {"bet_id": "13", "source": "runner"}]
        if "betfair_live_order_requests" in u:
            return [{"bet_id": "14", "client_ref": "safe_tennis-t9", "params": {}},
                    {"bet_id": "15", "client_ref": "local1",
                     "params": {"comando": {"attore": "tennis_pro"}}}]
        return []

    reg = Registro(risposte)
    motivi = efb.proprietari_bot(client_supabase(reg), ["11", "12", "13", "14", "15"])
    assert set(motivi) == {"11", "12", "14", "15"}
    for bet, motivo in motivi.items():
        ind = A.indizio_da_motivo(motivo)
        o = dal_conto(ordine_json(bet, "BACK", 1.0, 2.0, csr="live"))
        assert A.attribuisci(o, [ind]).autore == efb.bot_di(motivo), (bet, motivo)
    assert A.indizio_da_motivo("strano") is None


def test_dichiarato_paper():
    o = dal_conto(ordine_json("9", "BACK", 1.0, 2.0))
    assert A.attribuisci_dichiarato("mike", o).autore == "mike"
    a = A.attribuisci_dichiarato("pippo", o)
    assert a.autore == "sito" and "pippo" in (a.conflitto or "")
    assert A.attribuisci_dichiarato(None, o).fonte == "riferimenti"


def test_casi_limite_riferimenti():
    assert A.attribuisci_riferimenti(None, "zzz").autore == "sconosciuto"
    assert A.attribuisci_riferimenti("boh", None).autore == "sconosciuto"
    assert A.attribuisci_riferimenti("  ", " ").autore == "sito"
    # il ref manuale col customerOrderRef di un bot: del bot (come W2)
    assert A.attribuisci_riferimenti("live", "mike-t3").autore == "mike"
    # ref di un bot e customerOrderRef di un altro: vince il ref, conflitto scritto
    a = A.attribuisci_riferimenti("mike", "safe-t3")
    assert a.autore == "mike" and a.conflitto
    # maiuscole: Betfair restituisce il ref come scritto (confronto senza maiuscole)
    assert A.attribuisci_riferimenti("LIVE", None).autore == "desktop"
    assert A.attribuisci_riferimenti("scm12a", None).autore == "sconosciuto"


def test_importare_il_modulo_non_importa_il_codice_di_oggi():
    codice = ("import sys, threading; import Betfair.nucleo.ordini.attribuzione, "
              "Betfair.nucleo.ordini.libro_conto, Betfair.nucleo.ordini.pnl_mercato, "
              "Betfair.nucleo.ordini.riconciliazione; "
              "print(sorted(m for m in sys.modules if m.startswith('Betfair.stream')), "
              "threading.active_count())")
    out = subprocess.run([sys.executable, "-c", codice], cwd=str(RADICE), capture_output=True,
                         text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "[] 1"
