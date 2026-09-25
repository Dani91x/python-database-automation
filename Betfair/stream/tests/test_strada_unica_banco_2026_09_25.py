"""25/09 - F4 FINITA: la porta del banco agganciata al replay + profilo rapido.

Che cosa si inchioda qui (ogni test ha la sua rottura minima, scritta nel
referto ``AUDIT_2026-09-25/STRADA_UNICA_BANCO_E_PAPER.md``):

  * il client VERO del bot (``safe_strategy.porta_ordini.PortaCanale``, col suo
    thread) parla al MOTORE VERO su ``WsBanco`` con la busta JSON vera: ack,
    eventi ``order``, nessun ``da_seq`` a vuoto;
  * REPERTO del 25/09: il motore numera i seq dall'epoch in ms; la memoria del
    client partiva da 0 e OGNI evento apriva un «buco» -> ``da_seq`` a raffica
    (tempesta). Ora il primo seq e' la base e c'e' UNA richiesta alla volta;
  * REPERTO del 25/09: Safe mandava FOK anche sotto il minimo e il motore lo
    rifiutava (``submin_non_percorribile``); la coda accoda ``place_submin``
    senza FOK. Ora il canale fa come la coda;
  * il banco LIVE serve le righe ``live`` col ``ClienteLiveBanco`` e le
    ``paper`` col client simulato, con ``_client_for_mode`` di PRODUZIONE;
  * il rapporto di parita' coda/canale: stessi ordini e righe = parita', un
    prezzo diverso o un REST sul canale = parita' NON raggiunta;
  * ``trasporto.contesto`` accende l'interruttore del bot e lo rimette com'era.

Finti: client = ``cliente_simulato()`` del banco (SimulatedClient VERO) nel
registro VERO ``flumine.clients.Clients``; Market doppio con la regola di
flumine (lo stesso di ``test_motore_ordini_2026_09_24``); il client del bot e'
quello di produzione; il DB e il mercato del bot sono i finti del test della
porta di Safe (stesse firme di ``bot_db``/``omega_market``).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, List

import pytest
from flumine import BaseStrategy, clients

from Betfair.safe_strategy import execution as X
from Betfair.safe_strategy import porta_ordini as SPO
from Betfair.stream import live_order_worker as LOW
from Betfair.stream import motore_ordini as MO
from Betfair.stream.backtest import banco_comune as B
from Betfair.stream.backtest import trasporto as TRA
from Betfair.stream.backtest.porta_banco import (ClienteLiveBanco, PortaBanco,
                                                 TOKEN_BANCO)
from Betfair.stream.tests.test_motore_ordini_2026_09_24 import _Framework, _Market

_STRAT = BaseStrategy(market_filter={}, name="banco_f4_25")


def _attendi(pred: Any, timeout: float = 3.0) -> bool:
    fine = time.monotonic() + timeout
    while time.monotonic() < fine:
        if pred():
            return True
        time.sleep(0.005)
    return bool(pred())


@pytest.fixture()
def banco(monkeypatch, tmp_path):
    monkeypatch.setenv("LIVE_ORDER_MODE", "OFF")      # il .env della macchina non conta
    monkeypatch.setattr(LOW, "_kill_switch", lambda: False)
    monkeypatch.setattr(LOW, "_jurisdiction", lambda: "it")
    monkeypatch.setattr(LOW, "_max_stake", lambda: None)
    monkeypatch.setattr(LOW, "_SETTINGS", {})
    registro = clients.Clients()
    sim = B.cliente_simulato()
    sim.eseguiti = []
    registro.add_client(sim)
    market = _Market("1.234", registro)
    market.borsa = True
    fl = _Framework({"1.234": market}, registro)
    pb = PortaBanco(fl, _STRAT, attore="safe", cartella_diario=str(tmp_path),
                    modo_processo="LIVE")
    client = SPO.PortaCanale(porta_ws=0, attore="safe", connetti=pb.connetti,
                             token_fn=lambda: TOKEN_BANCO)
    client.avvia()
    assert _attendi(client.disponibile)
    yield pb, client, market, sim
    client.ferma()
    pb.metti_giu()


def _cmd(n: int, **kw: Any) -> dict:
    d = SPO.costruisci_comando(ref="safe-t%d" % n, attore="safe", azione="place",
                               mode=kw.pop("mode", "live"), market_id="1.234",
                               selection_id=47972, side=kw.pop("side", "BACK"),
                               price=kw.pop("price", 2.5), size=kw.pop("size", 3.0),
                               persistence="LAPSE", time_in_force=kw.pop("tif", None))
    d.update(kw)
    return d


# ---------------------------------------------------------------------------
# il client VERO sul WsBanco
# ---------------------------------------------------------------------------
def test_client_vero_su_wsbanco_ack_eventi_e_nessun_da_seq(banco):
    """Rottura minima: togliere la base del primo seq in
    ``MemoriaComandi._avanza_seq`` -> ``richieste_da_seq`` > 0 e buchi > 0."""
    pb, client, market, _sim = banco
    ack = client.invia(_cmd(1))
    assert ack.arrivato and ack.accettato and ack.seq is not None
    pb.aggiorna()
    assert pb.attendi_client()
    ev = client.esiti("safe-t1")
    assert ev is not None and ev["fase"] in ("inviato", "accettato_betfair")
    assert set(MO.CHIAVI_SPECCHIO) <= set(ev)
    # la busta e' JSON vero dai due lati: il WsBanco ha ricevuto testo
    assert pb.ultimo_ws.inviati[0]["t"] == "comando"
    assert client.richieste_da_seq == 0
    assert client.memoria.buchi == 0 and not client.memoria._sopra
    assert market.calls and market.calls[0][2] is pb.cliente_live


def test_token_sbagliato_rifiutato_nessun_ordine(banco, tmp_path):
    """Rottura minima: ``WsBanco(..., token_ok=True)`` sempre -> un ordine parte."""
    pb, _client, market, _sim = banco
    intruso = SPO.PortaCanale(porta_ws=0, attore="safe", connetti=pb.connetti,
                              token_fn=lambda: "token-sbagliato-0000000000000")
    intruso.avvia()
    try:
        assert _attendi(intruso.disponibile)
        ack = intruso.invia(_cmd(2))
        assert ack.arrivato and ack.accettato is False
        assert str(ack.motivo).startswith(MO.M_TOKEN)
        assert market.calls == []
    finally:
        intruso.ferma()


def test_banco_live_serve_live_col_cliente_live_e_paper_col_simulato(banco):
    """``_client_for_mode`` di PRODUZIONE sceglie il client per il mode della
    riga. Rottura minima: ``ClienteLiveBanco.VENUE.name = "SIMULATED"`` -> la
    riga live e' rifiutata (``live_client_assente``)."""
    pb, client, market, sim = banco
    a1 = client.invia(_cmd(3, mode="live"))
    a2 = client.invia(_cmd(4, mode="paper"))
    assert a1.accettato and a2.accettato
    per_ref = {}
    for order, _sref, cl in market.calls:
        per_ref[len(per_ref)] = cl
    assert per_ref[0] is pb.cliente_live and isinstance(per_ref[0], ClienteLiveBanco)
    assert per_ref[1] is sim
    pb.aggiorna()
    assert pb.attendi_client()
    assert client.esiti("safe-t3")["mode"] == "live"
    assert client.esiti("safe-t4")["mode"] == "paper"


def test_cliente_live_banco_delega_ma_non_e_simulato():
    sim = B.cliente_simulato()
    viva = ClienteLiveBanco(sim)
    assert LOW._is_paper_client(sim) is True
    assert LOW._is_paper_client(viva) is False
    assert viva.execution is sim.execution          # stessa esecuzione simulata
    assert viva.username == sim.username


# ---------------------------------------------------------------------------
# REPERTO 1 - la tempesta di da_seq
# ---------------------------------------------------------------------------
class _WsSpia:
    def __init__(self) -> None:
        self.mandati: List[dict] = []

    def send(self, testo: str) -> None:
        self.mandati.append(json.loads(testo))


def _porta_con_spia() -> tuple:
    p = SPO.PortaCanale(porta_ws=0, attore="safe", connetti=lambda *_a: None,
                        token_fn=lambda: "x")
    ws = _WsSpia()
    p._ws = ws
    p.collegato = True
    return p, ws


def _ev(seq: int, ref: str = "safe-t1", fase: str = "inviato") -> str:
    return json.dumps({"t": "order", "d": {"ref": ref, "seq": seq, "fase": fase}})


def test_primo_seq_e_la_base_nessun_da_seq_su_flusso_contiguo():
    """Il motore numera dall'epoch in ms (``_base_seq``). Rottura minima:
    togliere ``if self.seq_visto == 0 and not self._sopra: seq_visto = seq - 1``
    -> ogni evento chiede ``da_seq`` (qui: 5 richieste invece di 0)."""
    p, ws = _porta_con_spia()
    base = int(time.time() * 1000)
    p.incassa(json.dumps({"t": "ack", "d": {"ref": "safe-t1", "seq": base + 1,
                                            "accettato": True, "motivo": None,
                                            "ricevuto_ms": base}}))
    for i in range(2, 7):
        p.incassa(_ev(base + i))
    assert [m for m in ws.mandati if m["t"] == "da_seq"] == []
    assert p.memoria.seq_visto == base + 6 and p.memoria.buchi == 0


def test_un_buco_una_sola_richiesta_finche_il_motore_non_risponde():
    """Rottura minima: togliere il controllo ``_da_seq_in_corso`` -> tre buchi
    di fila fanno tre richieste (la tempesta, in piccolo)."""
    p, ws = _porta_con_spia()
    base = 1_727_000_000_000
    p.incassa(_ev(base + 1))
    for s in (base + 5, base + 6, base + 7):         # manca base+2..4
        p.incassa(_ev(s, fase="abbinato_parziale"))
    richieste = [m for m in ws.mandati if m["t"] == "da_seq"]
    assert len(richieste) == 1 and richieste[0]["d"]["seq"] == base + 1
    # il motore rimanda i mancanti e poi risponde: la contiguita' si chiude
    for s in (base + 2, base + 3, base + 4):
        p.incassa(_ev(s, ref="safe-t9"))
    p.incassa(json.dumps({"t": "da_seq", "d": {"dal": base + 1, "fino_a": base + 7,
                                               "inviati": 3, "completo": True}}))
    assert p.memoria.seq_visto == base + 7 and not p.memoria._sopra
    assert p._da_seq_in_corso is False
    # un buco NUOVO si puo' chiedere di nuovo (una volta)
    p.incassa(_ev(base + 10))
    assert len([m for m in ws.mandati if m["t"] == "da_seq"]) == 2


def test_da_seq_incompleto_riparte_da_fino_a_e_lo_conta():
    """Dopo un riavvio del runner la memoria del motore non ha piu' i vecchi
    seq (``completo`` False): il buco non si colma, si riparte da ``fino_a``
    invece di chiedere all'infinito. Rottura minima: ignorare ``t="da_seq"``
    in ``incassa`` -> ``seq_visto`` resta indietro e ogni evento richiede."""
    p, ws = _porta_con_spia()
    p.incassa(_ev(1000))
    nuova_base = 5000
    p.incassa(_ev(nuova_base + 1))                   # runner riavviato: buco
    p.incassa(json.dumps({"t": "da_seq", "d": {"dal": 1000, "fino_a": nuova_base + 1,
                                               "inviati": 1, "completo": False}}))
    assert p.memoria.seq_visto == nuova_base + 1
    assert p.memoria.buchi_non_colmati == 1
    p.incassa(_ev(nuova_base + 2))
    assert len([m for m in ws.mandati if m["t"] == "da_seq"]) == 1


def test_tempesta_assente_col_motore_vero(banco):
    """Il caso intero: client vero + motore vero, 5 ordini e i loro eventi.
    Prima della correzione ogni evento chiedeva ``da_seq`` dal seq 0 e il
    motore rimandava tutta la memoria (fino a 500 messaggi) ogni volta."""
    pb, client, _market, _sim = banco
    for n in range(10, 15):
        assert client.invia(_cmd(n)).accettato
        pb.aggiorna()
        assert pb.attendi_client()
    assert client.richieste_da_seq == 0
    assert len([m for m in pb.ultimo_ws.inviati if m["t"] == "da_seq"]) == 0


# ---------------------------------------------------------------------------
# REPERTO 2 - place-and-trim dal canale (Safe)
# ---------------------------------------------------------------------------
def test_safe_sotto_minimo_dal_canale_va_nel_place_and_trim(banco):
    """Rottura minima: in ``execution._place_via_canale`` rimettere
    ``time_in_force=PO.FOK`` anche sotto il minimo -> il motore VERO rifiuta
    ``submin_non_percorribile`` e la riga va in errore."""
    from Betfair.safe_strategy.tests.test_porta_ordini_f5_2026_09_24 import (
        FakeDB, FakeMarket, NOW, _riserva)

    pb, client, market, _sim = banco
    db, mkt = FakeDB(), FakeMarket()
    tr = _riserva(db, mode="live", side="back")
    out = X.place(db=db, market=mkt, mode="live", event_id=tr["event_id"],
                  market_id="1.234", selection_id=47972, side="back", price=3.0,
                  size=1.5, best_size=100.0, ladder=((3.0, 100.0),),
                  client_ref="safe-t%d" % tr["id"], trade_id=tr["id"],
                  meta=dict(tr["meta"]), now=NOW, params={}, porta=client)
    assert out.status == "pending", out
    cmd = [m for m in pb.ultimo_ws.inviati if m["t"] == "comando"][-1]["d"]
    assert cmd["time_in_force"] is None and cmd["size"] == 1.5
    ack = pb._ack["safe-t%d" % tr["id"]]
    assert ack["accettato"] is True
    # la macchina vera: parcheggio al minimo (2,00) e subito il taglio di 0,50
    # (il doppio del Market riduce la size sull'ordine, come Betfair il residuo)
    assert market.calls[0][2] is pb.cliente_live
    assert market.calls[1][0] == "cancel" and market.calls[1][2] == 0.5


def test_safe_sopra_il_minimo_resta_fok():
    """La regola di prima non cambia sopra il minimo (FOK su ogni place)."""
    from Betfair.safe_strategy.tests.test_porta_ordini_f5_2026_09_24 import (
        FakeDB, FakeMarket, NOW, _riserva)

    mandati: List[dict] = []

    class _P:
        via_canale = True
        attore = "safe"

        def disponibile(self) -> bool:
            return True

        def invia(self, comando: dict) -> Any:
            mandati.append(comando)
            return SPO.Ack(comando["ref"], 1, True, None, 0)

    db = FakeDB()
    tr = _riserva(db, mode="live", side="back")
    X.place(db=db, market=FakeMarket(), mode="live", event_id=tr["event_id"],
            market_id="1.234", selection_id=47972, side="back", price=3.0, size=4.0,
            best_size=100.0, ladder=((3.0, 100.0),), client_ref="safe-t%d" % tr["id"],
            trade_id=tr["id"], meta=dict(tr["meta"]), now=NOW, params={}, porta=_P())
    assert mandati[-1]["time_in_force"] == "FILL_OR_KILL"


# ---------------------------------------------------------------------------
# la parita' coda/canale
# ---------------------------------------------------------------------------
def _traccia(tr: str, prezzo: float = 12.0, t: str = "2026-06-30T16:00:35+00:00",
             stato: str = "open", rest: Any = None) -> dict:
    return {"trasporto": tr, "bot": "safe_base", "durata_s": 1.0,
            "ordini": [{"azione": "place", "ref": "safe-t1", "market_id": "1.2",
                        "selection_id": 7, "side": "LAY", "price": prezzo, "size": 1.72,
                        "fok": True, "t_mercato": t}],
            "righe": [{"id": 1, "status": stato, "side": "lay", "market_id": "1.2",
                       "selection_id": 7, "price": 11.0, "size": 1.72, "mode": "live"}],
            "rest_sul_canale": rest or []}


def test_parita_raggiunta_con_scarto_solo_nei_tempi():
    r = TRA.confronta(_traccia("coda"),
                      _traccia("canale", t="2026-06-30T16:00:37.100000+00:00"))
    assert r["parita"] is True and r["primo_scarto"] is None
    assert r["scarto_tempi_s"] == {"max": 2.1, "min": 2.1, "n": 1}


def test_parita_rotta_da_prezzo_esito_o_rest_sul_canale():
    """Rottura minima: togliere il prezzo da ``trasporto._chiave`` -> un ordine
    a quota diversa passa per parita'."""
    assert TRA.confronta(_traccia("coda"), _traccia("canale", prezzo=12.5))["parita"] is False
    r = TRA.confronta(_traccia("coda"), _traccia("canale", prezzo=12.5))
    assert r["primo_scarto"] == 0 and r["scarto_canale"]["price"] == 12.5
    assert TRA.confronta(_traccia("coda"), _traccia("canale", stato="error"))["parita"] is False
    assert TRA.confronta(_traccia("coda"),
                         _traccia("canale", rest=[{"azione": "place"}]))["parita"] is False
    meno = _traccia("canale")
    meno["ordini"] = []
    assert TRA.confronta(_traccia("coda"), meno)["parita"] is False


def test_contesto_accende_e_rimette_l_interruttore(monkeypatch):
    """Rottura minima: non ripristinare l'env all'uscita -> l'interruttore resta
    acceso per i replay successivi dello stesso processo."""
    monkeypatch.delenv("SAFE_ORDINI_VIA_CANALE", raising=False)
    monkeypatch.setenv("OMEGA_ORDINI_VIA_CANALE", "0")
    with TRA.contesto("safe_base", "canale") as st:
        assert os.environ["SAFE_ORDINI_VIA_CANALE"] == "1" and st["attore"] == "safe"
    assert "SAFE_ORDINI_VIA_CANALE" not in os.environ
    with TRA.contesto("omega", "canale"):
        assert os.environ["OMEGA_ORDINI_VIA_CANALE"] == "1"
    assert os.environ["OMEGA_ORDINI_VIA_CANALE"] == "0"
    with TRA.contesto("safe_base", "coda"):
        assert "SAFE_ORDINI_VIA_CANALE" not in os.environ
    assert TRA.attivo() is None


def test_bot_senza_porta_non_passa_dal_canale():
    for bot in ("mike", "safe_tennis"):
        with pytest.raises(ValueError):
            with TRA.contesto(bot, "canale"):
                pass
    # fuori dal contesto l'aggancio del replay e' nullo
    assert TRA.su_esegui(object(), object()) is None


# ---------------------------------------------------------------------------
# il profilo rapido su una registrazione VERA (se presente su questa macchina)
# ---------------------------------------------------------------------------
def _cartella_registrazioni() -> str:
    candidati = [os.getenv("LIVE_STREAM_DATA_DIR") or ""]
    radice = Path(__file__).resolve().parents[3]
    candidati += [str(radice / "_live_raw"), str(radice.parents[2] / "_live_raw")]
    for c in candidati:
        if c and os.path.exists(os.path.join(c, "35760084", "35760084.raw.jsonl")):
            return c
    return ""


@pytest.mark.skipif(not _cartella_registrazioni(),
                    reason="registrazione 35760084 assente su questa macchina")
@pytest.mark.parametrize("bot", ["safe_base", "omega"])
def test_profilo_rapido_verde_sulla_registrazione_vera(bot):
    """Il profilo «di minuti» del trasporto (R1-R9 + R2b) sulla registrazione
    di riferimento: tutto verde (o N/A col motivo). Qualche secondo per bot."""
    from Betfair.stream.backtest import certifica as C
    from Betfair.stream.backtest import trasporto_rapido as TRR

    with C._freni_da_banco():
        esiti = TRR.esegui_scenari(bot, "35760084", _cartella_registrazioni())
    ko = [(e.nome, [c for c in e.controlli if not c[1]], e.errore)
          for e in esiti if not e.ok and not e.na]
    assert not ko, ko
    nomi = [e.nome for e in esiti]
    assert len(nomi) == 11 and nomi[0] == "R1 accettato"


def test_ordini_del_canale_adottati_nella_vista_di_conto(banco):
    """Gli ordini del MOTORE esistono sul conto come quelli della REST: la
    vista del banco (``MercatoFlumine.ordini``, letta dai controlli K4/K7) li
    deve vedere, col ``customerOrderRef`` VERO di flumine (mai il ref del bot).
    Rottura minima: ``trasporto._adotta`` che non adotta -> nel replay
    ``ordini-manuali`` di Safe sul canale K4 x2808 (misurato il 25/09)."""
    from types import SimpleNamespace

    pb, client, market, _sim = banco
    strategia = SimpleNamespace(mercato=SimpleNamespace(ordini={}))
    st: dict = {}
    assert client.invia(_cmd(20)).accettato
    pb.aggiorna()
    TRA._adotta(st, pb, strategia)
    ordine = market.calls[0][0]
    assert list(strategia.mercato.ordini.values()) == [ordine]
    cor = next(iter(strategia.mercato.ordini))
    assert cor == str(ordine.customer_order_ref)[:32] and not cor.startswith("safe-")
    # una seconda passata non duplica
    pb.aggiorna()
    TRA._adotta(st, pb, strategia)
    assert len(strategia.mercato.ordini) == 1
