"""M-1, revisione indipendente (11/10/2026): le prove che mancavano.

I1  mai in coda a un file non vuoto; lettore che riprende dopo un membro gzip tronco.
I2  test che rendono rosse le mutazioni del revisore (N1-N20) e le riconnessioni
    con lo STESSO listener (test del revisore, integrati e resi severi).
I3  silenzi ai bordi della sottoscrizione (iniziale, finale, nessun messaggio).
M1-M7  fork, chiusura che non aspetta, decisioni paper/live separate, latenze
    pulite, tetto della coda in byte, avvio del thread fallito, cartelle giorno,
    piu' giorni e codici annidati di replaceOrders.

Stessi finti con le chiavi vere del file principale (importati da li').
"""
from __future__ import annotations

import calendar
import gzip
import hashlib
import io
import json
import logging
import os
import random
import subprocess
import sys
import textwrap
import threading
import time
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from Betfair.monitor import analisi_ordini as AO
from Betfair.monitor import registratore_ordini as RO
from Betfair.monitor.tests.test_registratore_ordini_2026_10_11 import (  # noqa: F401
    MID,
    RICHIESTE,
    SEL,
    _avvisi_azzerati,
    _build_client,
    _istr,
    _righe,
    _SocketFinto,
    _tutti_i_file,
    acceso,
    righe_stream_ordini,
)

RADICE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
T0 = 1_760_000_000_000_000


def _info(nome: str = "f", ch: Any = None, servizio: str = "svc") -> Dict[str, Any]:
    return {"file": nome, "righe": 0, "rotte": 0, "troncato": False, "servizio": servizio,
            "pid": 1, "chiusura": ch, "byte": 0}


def _hb(seq: int, t_us: int, sid: int = 1) -> Dict[str, Any]:
    return {"k": "stream", "seq": seq, "ep_us": T0 + t_us, "mono_us": t_us, "sid": sid,
            "msg": {"op": "ocm", "id": sid, "clk": "c%d" % seq, "pt": 1, "ct": "HEARTBEAT"}}


def _sub(seq: int, t_us: int, sid: int = 1, hb_ms: Any = 5000) -> Dict[str, Any]:
    return {"k": "sub", "seq": seq, "ep_us": T0 + t_us, "mono_us": t_us, "sid": sid,
            "heartbeat_ms": hb_ms, "conflate_ms": None, "ripresa": False}


def _chiusura(t_us: int) -> Dict[str, Any]:
    return {"k": "chiusura", "seq": 0, "ep_us": T0 + t_us, "motivo": "fine_processo",
            "persi_coda": 0, "scartati_tetto": 0, "scartati_errore": 0}


# ---------------------------------------------------------------------------
# I1 - scrittore: mai in coda a un file non vuoto; lettore: riprende
# ---------------------------------------------------------------------------
def test_mai_in_coda_a_un_file_non_vuoto(tmp_path, monkeypatch):
    monkeypatch.setattr(RO, "giorno_utc", lambda ep_s=None: "20261011")
    d = tmp_path / "20261011"
    d.mkdir()
    vecchio = d / ("ordini_p_%d.jsonl.gz" % os.getpid())   # pid riusato
    vecchio.write_bytes(b"\x1f\x8b\x08 membro tronco di un processo morto")
    h0 = hashlib.sha256(vecchio.read_bytes()).hexdigest()
    scr = RO.Scrittore(cartella=str(tmp_path), servizio="p", avvia_thread=False)
    scr.metti_stream(1, '{"op":"ocm","id":1,"pt":1,"ct":"HEARTBEAT"}')
    scr.giro(forza_svuota=True)
    assert scr._percorso.endswith("ordini_p_%d_2.jsonl.gz" % os.getpid())
    # riapertura dopo un errore di disco: ancora un file NUOVO
    scr._errore_file("disco pieno (prova)")
    scr._riapri_dopo = 0.0
    scr.metti_stream(1, '{"op":"ocm","id":1,"pt":2,"ct":"HEARTBEAT"}')
    scr.giro(forza_svuota=True)
    assert scr._percorso.endswith("ordini_p_%d_3.jsonl.gz" % os.getpid())
    scr.chiudi()
    assert hashlib.sha256(vecchio.read_bytes()).hexdigest() == h0, "file altrui toccato"
    for n in ("_2", "_3"):
        righe, info = AO.leggi_file(str(d / ("ordini_p_%d%s.jsonl.gz" % (os.getpid(), n))))
        assert info["rotte"] == 0 and not info["troncato"]
        assert sum(r["k"] == "stream" for r in righe) == 1


def _membro(n0: int, n: int, chiudi: bool = True) -> bytes:
    buf = io.BytesIO()
    g = gzip.GzipFile(fileobj=buf, mode="wb")
    for i in range(n0, n0 + n):
        g.write((json.dumps({"k": "stream", "seq": i, "pad": "%x" % random.getrandbits(256)})
                 + "\n").encode())
    if chiudi:
        g.close()
    else:
        g.flush()          # Z_SYNC_FLUSH e poi il processo muore: niente coda
    return buf.getvalue()


def test_lettore_riprende_dopo_un_membro_tronco(tmp_path):
    """Il caso e4 del revisore (100 righe tronche + 10 in un membro dopo) e uno
    piu' grande, con membri oltre il blocco di lettura."""
    p = tmp_path / "a.jsonl.gz"
    p.write_bytes(_membro(0, 100, chiudi=False) + _membro(100, 10))
    righe, info = AO.leggi_file(str(p))
    assert info["troncato"] is True
    assert sorted(r["seq"] for r in righe) == list(range(110)), "righe perse dopo il membro tronco"
    q = tmp_path / "b.jsonl.gz"
    q.write_bytes(_membro(0, 2000) + _membro(2000, 1500, chiudi=False) + _membro(3500, 3000)
                  + _membro(6500, 10, chiudi=False))
    righe, info = AO.leggi_file(str(q))
    assert sorted(r["seq"] for r in righe) == list(range(6510)) and info["rotte"] == 0


# ---------------------------------------------------------------------------
# I3 - silenzi ai bordi
# ---------------------------------------------------------------------------
def test_silenzio_finale_fino_alla_chiusura():
    rows = [{"k": "avvio", "seq": 0}, _sub(1, 0), _hb(2, 5_000_000), _hb(3, 10_000_000),
            _chiusura(3600 * 1_000_000)]
    a = AO.analizza([(rows, _info(ch=rows[-1]))])
    s = a["buchi"][0]["silenzi"]
    assert [(x["tipo"], x["secondi"]) for x in s] == [("finale", 3590.0)]
    assert a["ci_sono_buchi"] is True
    assert "BUCHI: SI" in AO.formatta(a)


def test_silenzio_iniziale_e_sottoscrizione_muta():
    rows = [_sub(1, 0), _hb(2, 60_000_000), _hb(3, 62_000_000),
            _sub(4, 63_000_000, sid=2), _chiusura(200_000_000)]
    a = AO.analizza([(rows, _info(ch=rows[-1]))])
    tipi = [(x["sid"], x["tipo"]) for x in a["buchi"][0]["silenzi"]]
    assert (1, "iniziale") in tipi, tipi
    assert (2, "nessun_messaggio") in tipi, tipi


def test_silenzio_finale_di_un_processo_morto_misurato_sul_giorno():
    """Senza chiusura, la fine e' l'ultimo istante visto in QUALUNQUE file."""
    morto = [_sub(1, 0), _hb(2, 1_000_000)]
    vivo = [_sub(1, 0, sid=7), *[_hb(i + 2, i * 4_000_000, sid=7) for i in range(30)],
            _chiusura(120_000_000)]
    a = AO.analizza([(morto, _info("morto")), (vivo, _info("vivo", ch=vivo[-1]))])
    b = {x["file"]: x for x in a["buchi"]}
    assert [x["tipo"] for x in b["morto"]["silenzi"]] == ["finale"]
    assert b["morto"]["silenzi"][0]["secondi"] == 119.0
    assert b["vivo"]["silenzi"] == []


def test_soglia_del_silenzio_dal_battito_della_sottoscrizione():
    """N15: battito 500 ms -> soglia 1,5 s; un buco di 2 s si vede."""
    rows = [_sub(1, 0, hb_ms=500), _hb(2, 100_000), _hb(3, 2_100_000), _hb(4, 2_500_000),
            _chiusura(2_600_000)]
    a = AO.analizza([(rows, _info(ch=rows[-1]))])
    assert [x["tipo"] for x in a["buchi"][0]["silenzi"]] == ["intermedio"]


def test_immagini_piene_ripetute_sono_un_buco():
    """N14: due SUB_IMAGE sulla stessa sottoscrizione."""
    img = lambda s, t: {"k": "stream", "seq": s, "ep_us": T0 + t, "mono_us": t, "sid": 1,  # noqa: E731
                        "msg": {"op": "ocm", "id": 1, "clk": "x", "pt": 1, "ct": "SUB_IMAGE"}}
    rows = [_sub(1, 0), img(2, 1000), img(3, 2000), _chiusura(3000)]
    a = AO.analizza([(rows, _info(ch=rows[-1]))])
    assert a["buchi"][0]["immagini_ripetute"] == 1 and a["ci_sono_buchi"] is True


# ---------------------------------------------------------------------------
# I2 - le mutazioni del revisore
# ---------------------------------------------------------------------------
def test_segreti_vuoti_o_corti_non_toccano_la_riga(acceso):
    """N2: un segreto vuoto o corto non si 'oscura' (rovinerebbe ogni riga)."""
    acceso.metti_record({"k": "rest", "x": "abc def 1234567"},
                        segreti=("", "abc", None, "1234567"))
    r = [x for x in _righe(acceso) if x["k"] == "rest"][0]
    assert r["x"] == "abc def 1234567"


def test_giorno_e_utc_anche_con_un_fuso_diverso(monkeypatch):
    """N4: alle 20:00 UTC a Tokyo e' gia' domani; il file va nel giorno UTC."""
    if not hasattr(time, "tzset"):
        pytest.skip("tzset non disponibile")
    vecchio = os.environ.get("TZ")
    os.environ["TZ"] = "Asia/Tokyo"
    time.tzset()
    try:
        ep = calendar.timegm((2026, 10, 11, 20, 0, 0, 0, 0, 0))
        assert time.strftime("%Y%m%d", time.localtime(ep)) == "20261012"
        assert RO.giorno_utc(ep) == "20261011"
    finally:
        if vecchio is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = vecchio
        time.tzset()


def _rest(seq, metodo, t, dur, csr, params, res, via="bflw", errore=None, eccezione=None):
    return {"k": "rest", "seq": seq, "via": via, "metodo": metodo, "ep_us": T0 + t,
            "mono_us": t, "risposta_ep_us": T0 + t + dur, "risposta_mono_us": t + dur,
            "durata_ms": dur / 1000, "market_id": "1.1",
            "attore": RO.attore_da({"customerStrategyRef": csr}) if csr else "?", "csr": csr,
            "cref": None, "corefs": [], "richiesta": params,
            "risposta": {"jsonrpc": "2.0", "result": res, "id": 1},
            "stato": res.get("status"), "errore": errore, "codici": [], "eccezione": eccezione}


def _ocm(seq, t, bet, status, sm, sr, rfo=None, rfs=None, sc=0):
    uo = {"id": bet, "p": 2.5, "s": 4, "side": "B", "status": status, "sm": sm, "sr": sr,
          "sl": 0, "sc": sc, "sv": 0}
    if rfo:
        uo["rfo"] = rfo
    if rfs:
        uo["rfs"] = rfs
    return {"k": "stream", "seq": seq, "ep_us": T0 + t, "mono_us": t, "sid": 1,
            "msg": {"op": "ocm", "id": 1, "clk": "x", "pt": 1,
                    "oc": [{"id": "1.1", "orc": [{"id": 9, "uo": [uo]}]}]}}


def _place_ok(bet, cor):
    return {"status": "SUCCESS", "instructionReports": [{
        "status": "SUCCESS", "betId": bet,
        "instruction": {"selectionId": 9, "side": "BACK",
                        "limitOrder": {"price": 2.5, "size": 4}, "customerOrderRef": cor}}]}


def test_figlio_di_una_replace_ha_l_attore_del_padre_e_codici_annidati():
    """N6 e M7: la replace non porta il customerStrategyRef; il figlio prende
    l'attore del padre. Il codice annidato del place della replace si conta."""
    rows = [
        _rest(1, "placeOrders", 100_000, 40_000, "omega",
              {"marketId": "1.1", "customerStrategyRef": "omega",
               "instructions": [{"customerOrderRef": "c1"}]}, _place_ok("B1", "c1")),
        _rest(2, "replaceOrders", 400_000, 50_000, None,
              {"marketId": "1.1", "instructions": [{"betId": "B1", "newPrice": 2.6}]},
              {"status": "SUCCESS", "instructionReports": [{
                  "status": "SUCCESS",
                  "cancelInstructionReport": {"status": "SUCCESS",
                                              "instruction": {"betId": "B1"},
                                              "sizeCancelled": 3.0},
                  "placeInstructionReport": {"status": "SUCCESS", "betId": "B2",
                                             "instruction": {"selectionId": 9, "side": "BACK",
                                                             "limitOrder": {"price": 2.6,
                                                                            "size": 3}}}}]}),
        _rest(3, "replaceOrders", 900_000, 50_000, None,
              {"marketId": "1.1", "instructions": [{"betId": "B2", "newPrice": 2.7}]},
              {"status": "FAILURE", "instructionReports": [{
                  "status": "FAILURE",
                  "cancelInstructionReport": {"status": "SUCCESS",
                                              "instruction": {"betId": "B2"}},
                  "placeInstructionReport": {"status": "FAILURE",
                                             "errorCode": "BET_TAKEN_OR_LAPSED"}}]}),
    ]
    a = AO.analizza([(rows, _info(ch={"motivo": "fine_processo"}))])
    seq = {r["bet_id"]: r for r in a["sequenze"]}
    assert seq["B2"]["nato_da"] == "B1" and seq["B2"]["attore"] == "bot:omega"
    assert a["errori_rest"].get("replaceOrders BET_TAKEN_OR_LAPSED") == 1, a["errori_rest"]


def test_riga_stream_verbatim_al_byte(acceso):
    """N9: la riga di Betfair si scrive COSI' COM'E' (spazi e ordine delle chiavi)."""
    grezza = '{"pt": 5, "op": "ocm",  "id": 3, "clk": "AB==", "ct": "HEARTBEAT"}'
    acceso.metti_stream(4, grezza)
    _righe(acceso)
    dati = b"".join(gzip.open(p, "rb").read() for p in _tutti_i_file(acceso.cartella()))
    assert ('"sid":4,"msg":' + grezza + "}").encode() in dati


def test_avvio_ha_la_versione_e_la_durata_e_dal_monotono(acceso):
    """N19 e N10."""
    RO.registra_rest(via="bflw", method="placeOrders", params={}, invio=(1_000, 5_000),
                     risposta=(9_000, 6_000), esito={})
    righe = _righe(acceso)
    assert righe[0]["k"] == "avvio" and righe[0]["versione"] == RO.VERSIONE_FORMATO
    rest = [r for r in righe if r["k"] == "rest"][0]
    assert rest["durata_ms"] == 1.0, "durata dall'epoca e non dal monotono"


def test_svuotamento_periodico_rende_leggibile_il_file_aperto(tmp_path, monkeypatch):
    """N20: senza chiusura, le righe sono su disco dopo SVUOTA_GZIP_S."""
    monkeypatch.setattr(RO, "SVUOTA_GZIP_S", 0.0)
    scr = RO.Scrittore(cartella=str(tmp_path), servizio="p", avvia_thread=False)
    for i in range(5):
        scr.metti_stream(1, '{"op":"ocm","id":1,"pt":%d,"ct":"HEARTBEAT"}' % i)
    scr.giro()                       # niente forza_svuota: e' il giro normale
    righe, info = AO.leggi_file(scr._percorso)
    assert sum(r["k"] == "stream" for r in righe) == 5
    scr.chiudi()


def test_riconnessioni_con_lo_stesso_listener(monkeypatch, acceso):
    """N7, N16, N17 (test del revisore, reso severo): flumine rifa' ``run`` sullo
    STESSO OrderStream (retry di tenacity): un tee solo, un sid per ripartenza,
    ogni riga col sid della SUA sottoscrizione."""
    from betfairlightweight.streaming.betfairstream import BetfairStream
    from flumine import clients
    from flumine.streams.orderstream import OrderStream

    c = _build_client(monkeypatch)
    client = clients.BetfairClient(c, order_stream=True, paper_trade=False,
                                   min_bet_validation=False)
    st = OrderStream(flumine=SimpleNamespace(), stream_id=1000, conflate_ms=None,
                     streaming_timeout=0.25, client=client)
    st._output_thread = SimpleNamespace(is_alive=lambda: True)
    tot = 0
    for _giro in range(3):
        righe = righe_stream_ordini(st.stream_id + 1, st.stream_id + 2)
        sock = _SocketFinto(righe)
        monkeypatch.setattr(BetfairStream, "_create_socket", lambda self, s=sock: s)
        with pytest.raises(Exception):
            OrderStream.run.__wrapped__(st)
        tot += len(righe)
    righe = sorted((r for r in _righe(acceso) if r.get("seq")), key=lambda r: r["seq"])
    stream = [r for r in righe if r["k"] == "stream"]
    sub = [r for r in righe if r["k"] == "sub"]
    assert len(stream) == tot, "tee montato %s volte" % (len(stream) / max(1, tot))
    sids = [s["sid"] for s in sub]
    assert len(sids) == 3 and sids == sorted(set(sids)), sids
    corrente = None
    for r in righe:
        if r["k"] == "sub":
            corrente = r["sid"]
        elif r["k"] == "stream":
            assert r["sid"] == corrente, "riga stream col sid di un'altra sottoscrizione"


def test_due_client_stesso_processo(monkeypatch, acceso):
    c1 = _build_client(monkeypatch)
    c2 = _build_client(monkeypatch)
    n0 = len(RICHIESTE)
    for c in (c1, c2):
        c.betting.place_orders(market_id=MID, instructions=[_istr()], customer_ref="a" * 32,
                               customer_strategy_ref="live")
    assert len(RICHIESTE) - n0 == 2
    assert len([r for r in _righe(acceso) if r["k"] == "rest"]) == 2
    assert c1.betting.request is not c2.betting.request


def test_aggancio_ripetuto_stesso_client(monkeypatch, acceso):
    """N18: agganciare due volte lo stesso client non avvolge due volte."""
    c = _build_client(monkeypatch)
    RO.aggancia_api_client(c)
    RO.aggancia_api_client(c)
    n0 = len(RICHIESTE)
    c.betting.place_orders(market_id=MID, instructions=[_istr()], customer_ref="a" * 32)
    assert len(RICHIESTE) - n0 == 1
    assert len([r for r in _righe(acceso) if r["k"] == "rest"]) == 1


# ---------------------------------------------------------------------------
# N8 e M1 - fine del processo vera (atexit) e fork, in un processo a parte
# ---------------------------------------------------------------------------
_PROGRAMMA = textwrap.dedent('''
    import os, sys, time
    sys.path.insert(0, sys.argv[1])
    os.environ["REGISTRO_ORDINI_DIR"] = sys.argv[2]
    from Betfair.monitor import registratore_ordini as RO
    RO.giorno_utc = lambda ep_s=None: "20261011"
    s = RO.scrittore()
    for i in range(50):
        s.metti_stream(1, '{"op":"ocm","id":1,"clk":"padre","pt":%d,"ct":"HEARTBEAT"}' % i)
    if sys.argv[3] == "fork":
        s.giro(forza_svuota=True)
        pid = os.fork()
        if pid == 0:
            for i in range(5):
                s.metti_stream(1, '{"op":"ocm","id":1,"clk":"FIGLIO","pt":%d}' % i)
            time.sleep(0.3)
            sys.exit(0)        # atexit del figlio: NON deve scrivere niente
        os.waitpid(pid, 0)
        for i in range(50, 100):
            s.metti_stream(1, '{"op":"ocm","id":1,"clk":"padre","pt":%d,"ct":"HEARTBEAT"}' % i)
    sys.exit(0)                # atexit del padre: chiusura fine_processo
''')


def _processo(tmp_path, modo: str):
    prog = tmp_path / "prog.py"
    prog.write_text(_PROGRAMMA, encoding="ascii")
    env = {k: v for k, v in os.environ.items() if k != "PYTEST_CURRENT_TEST"}
    r = subprocess.run([sys.executable, str(prog), RADICE, str(tmp_path / "o"), modo],
                       capture_output=True, text=True, timeout=60, env=env)
    assert r.returncode == 0, r.stderr[-800:]
    files = _tutti_i_file(str(tmp_path / "o"))
    assert len(files) == 1, files
    return AO.leggi_file(files[0])


def test_fine_processo_scrive_la_chiusura(tmp_path):
    """N8: all'uscita normale (atexit) la coda si svuota e c'e' la chiusura."""
    righe, info = _processo(tmp_path, "semplice")
    assert sum(r["k"] == "stream" for r in righe) == 50
    assert info["chiusura"] and info["chiusura"]["motivo"] == "fine_processo"
    assert not info["troncato"] and info["rotte"] == 0


@pytest.mark.skipif(not hasattr(os, "fork"), reason="fork solo POSIX")
def test_fork_il_figlio_non_scrive_mai_sul_file_del_padre(tmp_path):
    """M1: il figlio di un fork non scrive righe ne' chiusure sul file del padre."""
    righe, info = _processo(tmp_path, "fork")
    stream = [r for r in righe if r["k"] == "stream"]
    assert len(stream) == 100 and all(r["msg"]["clk"] == "padre" for r in stream)
    assert [r["k"] for r in righe].count("chiusura") == 1
    assert info["chiusura"]["motivo"] == "fine_processo"
    assert not info["troncato"] and info["rotte"] == 0


# ---------------------------------------------------------------------------
# M2 - chiudi non aspetta un disco appeso
# ---------------------------------------------------------------------------
def test_chiudi_non_resta_appeso(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(RO, "CHIUDI_ATTESA_S", 0.2)
    scr = RO.Scrittore(cartella=str(tmp_path), servizio="p", avvia_thread=False)
    scr._io.acquire()                          # il thread di scrittura "appeso"
    fatto = threading.Event()
    t = threading.Thread(target=lambda: (scr.chiudi(), fatto.set()), daemon=True)
    with caplog.at_level(logging.WARNING, logger=RO.__name__):
        t.start()
        t.join(1.5)
    ok = fatto.is_set()
    scr._io.release()
    t.join(2)
    assert ok, "chiudi() appeso dietro al thread di scrittura"
    assert "chiudo senza svuotare" in caplog.text


# ---------------------------------------------------------------------------
# M3 - decisioni paper e live separate
# ---------------------------------------------------------------------------
def test_decisioni_paper_e_live_mai_sommate():
    rows = [
        {"k": "dec", "seq": 1, "cor": "c1", "mode": "paper", "decisione_ms": T0 / 1000 - 50},
        {"k": "dec", "seq": 2, "cor": "c2", "mode": "live", "decisione_ms": T0 / 1000 + 50},
        _rest(3, "placeOrders", 100_000, 40_000, "live",
              {"marketId": "1.1", "customerStrategyRef": "live",
               "instructions": [{"customerOrderRef": "c1"}]}, _place_ok("B1", "c1")),
        _rest(4, "placeOrders", 200_000, 40_000, "live",
              {"marketId": "1.1", "customerStrategyRef": "live",
               "instructions": [{"customerOrderRef": "c2"}]}, _place_ok("B2", "c2")),
    ]
    a = AO.analizza([(rows, _info(ch={"motivo": "fine_processo"}))])
    assert a["conteggi"]["decisioni"] == {"live": 1, "paper": 1}
    seq = {r["bet_id"]: r for r in a["sequenze"]}
    assert "decisione" not in seq["B1"], "decisione PAPER legata a una REST live"
    assert seq["B2"]["decisione_invio_ms"] == 150.0
    assert a["latenze"]["decisione_invio_rest_ms"]["n"] == 1


# ---------------------------------------------------------------------------
# M4 - latenze REST pulite
# ---------------------------------------------------------------------------
def test_percentili_solo_sulle_chiamate_pulite():
    p = {"marketId": "1.1", "customerStrategyRef": "watchlist", "instructions": [{}]}
    rows = [
        _rest(1, "placeOrders", 0, 50_000, "watchlist", p, _place_ok("B1", None),
              via="rest_nostro"),
        _rest(2, "placeOrders", 0, 2_500_000, "watchlist", p, _place_ok("B2", None),
              via="rest_nostro"),
        _rest(3, "placeOrders", 0, 300_000, "watchlist", p,
              {"status": "FAILURE", "errorCode": "INSUFFICIENT_FUNDS",
               "instructionReports": []}, via="rest_nostro"),
        _rest(4, "placeOrders", 0, 2_500_000, "live", p, _place_ok("B4", None)),
    ]
    a = AO.analizza([(rows, _info(ch={"motivo": "fine_processo"}))])
    lat = a["latenze"]
    assert lat["rest_ms_per_metodo"]["placeOrders"]["n"] == 2   # 50 ms nostro + bflw
    assert lat["rest_ms_escluse"]["probabile_ritentativo placeOrders"]["n"] == 1
    assert lat["rest_ms_escluse"]["con_errore placeOrders"]["n"] == 1
    assert lat["rest_ms_per_via"]["rest_nostro placeOrders"]["max"] == 50.0
    assert "ESCLUSE dai percentili" in AO.formatta(a)


# ---------------------------------------------------------------------------
# M5 - tetto della coda in byte; avvio del thread fallito
# ---------------------------------------------------------------------------
def test_tetto_della_coda_in_byte(tmp_path, monkeypatch):
    monkeypatch.setattr(RO, "CODA_MAX_BYTE", 100)
    scr = RO.Scrittore(cartella=str(tmp_path), servizio="p", avvia_thread=False)
    riga = '{"op":"ocm","id":1,"pt":1,"ct":"HEARTBEAT","x":"' + "a" * 10 + '"}'
    for _ in range(3):
        scr.metti_stream(1, riga)
    assert len(scr._coda) == 2 and scr.persi_coda == 1
    scr.giro(forza_svuota=True)
    scr.metti_stream(1, riga)
    assert len(scr._coda) == 1 and scr.persi_coda == 1, "la coda svuotata non riaccetta"
    scr.chiudi()


def test_avvio_del_thread_fallito_non_arriva_al_bot(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(threading.Thread, "start", lambda self: (_ for _ in ()).throw(
        RuntimeError("can't start new thread")))
    scr = RO.Scrittore(cartella=str(tmp_path), servizio="p")
    with caplog.at_level(logging.WARNING, logger=RO.__name__):
        scr.metti_stream(1, '{"op":"ocm"}')
        scr.metti_stream(1, '{"op":"ocm"}')
    assert scr._thread is None and scr.avvii_falliti == 1, "riprova a ogni riga"
    assert "thread di scrittura non avviato" in caplog.text
    monkeypatch.undo()
    scr.chiudi()


# ---------------------------------------------------------------------------
# M6 - solo le cartelle giorno del registratore
# ---------------------------------------------------------------------------
def test_cartelle_vuote_tolte_solo_se_giorno(tmp_path):
    (tmp_path / "20261001").mkdir()
    (tmp_path / "altro").mkdir()
    (tmp_path / "2026100").mkdir()
    RO.Scrittore._togli_cartelle_vuote(str(tmp_path))
    assert not (tmp_path / "20261001").exists()
    assert (tmp_path / "altro").exists() and (tmp_path / "2026100").exists()


# ---------------------------------------------------------------------------
# M7 - piu' giorni insieme (ordine a cavallo della mezzanotte)
# ---------------------------------------------------------------------------
def _scrivi_giorno(base, giorno, righe_stream, monkeypatch, rest=None):
    monkeypatch.setattr(RO, "giorno_utc", lambda ep_s=None: giorno)
    scr = RO.Scrittore(cartella=base, servizio="r" + giorno, avvia_thread=False)
    RO._azzera_per_test(scr)
    if rest:
        RO.registra_rest(**rest)
    for r in righe_stream:
        scr.metti_stream(1, r)
    scr.giro(forza_svuota=True)
    scr.chiudi()
    RO._azzera_per_test(None)


def test_analisi_su_piu_giorni(tmp_path, monkeypatch, capsys):
    from Betfair.monitor.tests.test_registratore_ordini_2026_10_11 import _risultato, _uo

    base = str(tmp_path)
    params = {"marketId": MID, "instructions": [_istr()], "customerRef": "a" * 32,
              "customerStrategyRef": "live"}
    ocm = lambda uo: json.dumps({"op": "ocm", "id": 1, "clk": "x", "pt": 1,  # noqa: E731
                                 "oc": [{"id": MID, "orc": [{"id": SEL, "uo": [uo]}]}]})
    _scrivi_giorno(base, "20261011", [ocm(_uo("381200000001", "E", 0, 4))], monkeypatch,
                   rest=dict(via="bflw", method="placeOrders", params=params,
                             invio=RO.adesso_us(), risposta=RO.adesso_us(),
                             esito=_risultato("placeOrders", params)))
    _scrivi_giorno(base, "20261012", [ocm(_uo("381200000001", "EC", 4, 0))], monkeypatch)
    uno = AO.analizza_giorno(base, "20261012")
    assert {r["bet_id"]: r for r in uno["sequenze"]}["381200000001"]["origine"] != "nostro"
    due = AO.analizza_giorni(base, AO.giorni_fra("20261011", "20261012"))
    o = {r["bet_id"]: r for r in due["sequenze"]}["381200000001"]
    assert o["origine"] == "nostro" and o["stato_finale"] == "EXECUTION_COMPLETE"
    assert AO.main(["--cartella", base, "--dal", "20261011", "--al", "20261012"]) == 0
    assert "file: 2" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# disco in errore (e5 del revisore): niente file nuovo a ogni riga, perdite
# contate e scritte nella chiusura
# ---------------------------------------------------------------------------
def test_dopo_un_errore_di_file_si_aspetta_e_si_conta(tmp_path, monkeypatch):
    monkeypatch.setattr(RO, "giorno_utc", lambda ep_s=None: "20261011")
    scr = RO.Scrittore(cartella=str(tmp_path), servizio="p", avvia_thread=False)
    scr.metti_stream(1, '{"op":"ocm","id":1,"pt":0,"ct":"HEARTBEAT"}')
    scr.giro(forza_svuota=True)
    scr._errore_file("disco pieno (prova)")
    for i in range(3):
        scr.metti_stream(1, '{"op":"ocm","id":1,"pt":%d,"ct":"HEARTBEAT"}' % (i + 1))
    scr.giro(forza_svuota=True)
    assert scr.scartati_errore == 3 and scr._fh is None
    assert len(_tutti_i_file(str(tmp_path))) == 1, "un file nuovo a ogni riga"
    scr.chiudi()
    chiusure = [AO.leggi_file(p)[1]["chiusura"] for p in _tutti_i_file(str(tmp_path))]
    assert [c["scartati_errore"] for c in chiusure if c] == [3], chiusure


def test_potatura_non_tocca_mai_il_file_proprio_anche_se_vecchio(tmp_path, monkeypatch):
    """N12: anche senza la guardia del "file recente", il file aperto resta."""
    monkeypatch.setattr(RO, "RECENTE_S", 0.0)
    monkeypatch.setattr(RO, "POTATURA_S", 0.0)
    scr = RO.Scrittore(cartella=str(tmp_path), servizio="p", tetto=10, avvia_thread=False)
    scr.metti_stream(1, '{"op":"ocm","id":1,"pt":1,"ct":"HEARTBEAT"}')
    scr.giro(forza_svuota=True)
    os.utime(scr._percorso, (1_000_000, 1_000_000))       # "vecchio"
    scr._potatura()
    assert os.path.exists(scr._percorso), "potato il file aperto da questo processo"
    assert scr._pieno
    scr.chiudi()
