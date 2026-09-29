"""Cantiere V (29/09/2026) - replay di certificazione dello scalper calcio VELOCE
senza cambiare di una virgola cio' che il banco giudica.

S5 ricostruiva a ogni giro la copertura di TUTTI i buchi della registrazione e
rigiudicava TUTTE le coppie di battiti (misurato: meta' del tempo del replay,
costo quadratico nella vita della sessione). Ora:

* ``_CoperturaCrescente``: la copertura vive fra i giri e si aggiorna solo coi
  buchi nuovi; stesso numero della formula di riferimento
  ``sum(_sovrapposizione_ms(...))`` per QUALUNQUE elenco (sovrapposti, fuori
  ordine, vuoti, degeneri, aggiunti un po' alla volta, elenco cambiato);
* ``RegistroBuchi``/``VistaBuchi``: il replay passa i buchi come vista di un
  registro solo-in-aggiunta (niente copia a ogni giro, prefisso per costruzione);
* ``_s5`` con lo stato della ``Memoria``: STESSO testo di oggi, giro per giro
  (la versione di oggi e' copiata qui sotto, ``_s5_di_oggi``, come riferimento).
"""
from __future__ import annotations

import random
from typing import Any, List, Optional, Tuple

import pytest

from Betfair.stream.scalper import certificazione as CERT
from Betfair.stream.scalper.tools import replay_registrazioni as RR


# ---------------------------------------------------------------------------
# il riferimento: S5 com'era il 29/09 prima del cantiere V (copia fedele)
# ---------------------------------------------------------------------------
def _s5_di_oggi(o: CERT.Osservazione) -> Optional[str]:
    battiti = sorted(o.heartbeat_ms)
    massimo = int((o.heartbeat_cadenza_s + 1.0) * 1000)
    buchi = list(o.buchi_registrazione_ms or [])
    copertura = CERT._CoperturaBuchi(buchi) if buchi else None
    for a, b in zip(battiti, battiti[1:]):
        scarto = (b - a) - CERT._buco_dentro_ms(buchi, a, b, copertura)
        if scarto > massimo:
            return ("heartbeat fermo per %d ms di mercato EFFETTIVO (fra %d e "
                    "%d, %d ms sono silenzio della registrazione), la cadenza "
                    "del servizio e' %.0f s"
                    % (scarto, a, b, (b - a) - scarto, o.heartbeat_cadenza_s))
    if (o.sessione_viva and o.stop_richiesto_ms is None and battiti):
        scarto = (o.ms - battiti[-1]) - CERT._buco_dentro_ms(buchi, battiti[-1], o.ms, copertura)
        if scarto > massimo:
            return ("ultimo heartbeat %d ms fa di mercato EFFETTIVO, la "
                    "cadenza del servizio e' %.0f s" % (scarto, o.heartbeat_cadenza_s))
    for k in ("orders_placed", "cycles", "pnl_locked"):
        if k not in (o.stats or {}):
            return "le stats scritte non portano la chiave '%s'" % k
    return None


_STATS = {"orders_placed": 0, "cycles": 0, "pnl_locked": 0.0}


def _oss(**kw: Any) -> CERT.Osservazione:
    base = dict(scenario="test", quando="t", ms=1_000_000, modalita="live",
                running_da_ms=0, stats=dict(_STATS))
    base.update(kw)
    return CERT.Osservazione(**base)


def _s5_del_banco(oss: CERT.Osservazione, mem: CERT.Memoria,
                  soll: Optional[dict] = None) -> Optional[str]:
    """Il dettaglio di S5 come esce da ``verifica`` con la Memoria del replay."""
    for v in CERT.verifica(oss, soll if soll is not None else {}, mem):
        if v.codice.startswith("S5"):
            return v.dettaglio
    return None


def _riferimento(buchi: List[Tuple[int, int]], a: int, b: int) -> int:
    return sum(CERT._sovrapposizione_ms(a, b, ga, gb) for ga, gb in buchi)


def _buco_casuale(rng: random.Random, fine: int) -> Tuple[int, int]:
    tipo = rng.random()
    ga = rng.randint(-5000, fine)
    if tipo < 0.1:
        return (ga, ga - rng.randint(0, 3000))          # degenere (gb <= ga)
    if tipo < 0.15:
        return (ga, ga)                                  # vuoto
    return (ga, ga + rng.randint(1, 20000))


# ===========================================================================
# 1. la copertura crescente = la formula di riferimento
# ===========================================================================
@pytest.mark.parametrize("seme", range(25))
@pytest.mark.parametrize("come_vista", [False, True])
def test_copertura_crescente_uguale_alla_formula_lenta_giro_per_giro(seme, come_vista):
    """Buchi aggiunti un po' alla volta fra un giro e l'altro, fuori ordine,
    sovrapposti, vuoti e degeneri; a volte tanti insieme (si ricostruisce la
    parte statica), a volte uno solo (resta in coda): stesso numero."""
    rng = random.Random(1000 + seme)
    cop = CERT._CoperturaCrescente()
    registro = CERT.RegistroBuchi()
    tutti: List[Tuple[int, int]] = []
    fine = 200_000
    for _giro in range(40):
        for _ in range(rng.choice([0, 0, 1, 2, 5, 70, 300])):
            ga, gb = _buco_casuale(rng, fine)
            tutti.append((ga, gb))
            registro.aggiungi(ga, gb)
        elenco = registro.vista() if come_vista else list(tutti)
        assert cop.allinea(elenco) is True
        for _ in range(30):
            a = rng.randint(-10_000, fine + 10_000)
            b = a + rng.randint(-2000, 60_000)
            assert cop.dentro(a, b) == _riferimento(tutti, a, b), (a, b)


def test_copertura_crescente_casi_limite():
    cop = CERT._CoperturaCrescente()
    assert cop.allinea([]) is True
    assert cop.dentro(0, 100) == 0
    assert cop.allinea([(10, 20), (15, 30), (40, 40), (60, 50)]) is True
    assert cop.dentro(0, 100) == 10 + 15
    assert cop.dentro(15, 20) == 10
    assert cop.dentro(20, 10) == 0
    # un buco arrivato DOPO, fuori ordine e prima di tutti gli altri
    assert cop.allinea([(10, 20), (15, 30), (40, 40), (60, 50), (0, 5)]) is True
    assert cop.dentro(0, 100) == 10 + 15 + 5


@pytest.mark.parametrize("seme", range(10))
def test_copertura_crescente_elenco_cambiato_riparte_da_zero(seme):
    """Se l'elenco NON prolunga quello visto (buchi tolti o cambiati) la
    copertura lo dice (False) e riparte: stesso numero dell'elenco nuovo."""
    rng = random.Random(seme)
    cop = CERT._CoperturaCrescente()
    elenco = [_buco_casuale(rng, 100_000) for _ in range(rng.randint(3, 200))]
    assert cop.allinea(elenco) is True
    cambiato = list(elenco)
    i = rng.randrange(len(cambiato))
    cambiato[i] = (cambiato[i][0] - 1, cambiato[i][1] + 5000)
    assert cop.allinea(cambiato) is False
    assert cop.allinea(elenco[:-1]) is False             # accorciato
    for _ in range(50):
        a = rng.randint(-5000, 110_000)
        b = a + rng.randint(0, 40_000)
        assert cop.dentro(a, b) == _riferimento(elenco[:-1], a, b)


def test_copertura_crescente_vista_di_un_altro_registro_non_e_un_prolungamento():
    """Due replay diversi (due registri): la vista dell'altro registro, anche
    piu' lunga, non si prende per un prolungamento di quello visto."""
    a, b = CERT.RegistroBuchi(), CERT.RegistroBuchi()
    for x in range(5):
        a.aggiungi(x * 10_000, x * 10_000 + 3000)
        b.aggiungi(x * 10_000 + 500, x * 10_000 + 9000)
    b.aggiungi(90_000, 95_000)
    cop = CERT._CoperturaCrescente()
    assert cop.allinea(a.vista()) is True
    assert cop.allinea(b.vista()) is False
    assert cop.dentro(0, 100_000) == _riferimento(list(b.vista()), 0, 100_000)
    b.aggiungi(96_000, 99_000)
    assert cop.allinea(b.vista()) is True
    assert cop.dentro(0, 100_000) == _riferimento(list(b.vista()), 0, 100_000)


def test_registro_solo_in_aggiunta_e_vista_ferma():
    """La vista presa a un giro non cambia quando il registro cresce e si
    legge come la lista di prima (uguaglianza, fette, indici, bool)."""
    reg = CERT.RegistroBuchi()
    assert not reg.vista() and reg.vista() == []
    reg.aggiungi(1, 5)
    reg.aggiungi(7, 9)
    v = reg.vista()
    reg.aggiungi(20, 30)
    assert len(v) == 2 and v == [(1, 5), (7, 9)] and list(v) == [(1, 5), (7, 9)]
    assert v[-1] == (7, 9) and v[:1] == [(1, 5)] and v[1:] == [(7, 9)]
    with pytest.raises(IndexError):
        v[2]
    assert reg.vista() == [(1, 5), (7, 9), (20, 30)]


def test_orologio_vista_buchi_uguale_alla_lista_e_prefisso_stabile():
    """`_Orologio.vista_buchi` porta gli STESSI buchi di `buchi()` (che resta
    una lista), e ogni vista presa prima e' un prefisso delle seguenti."""
    o = RR._Orologio()
    rng = random.Random(11)
    t = 5_000_000
    viste: List[Any] = []
    for i in range(4000):
        t += rng.choice([100, 300, 2500, 8000, -1500])   # anche fuori ordine
        o.libro_ms.append(t)
        if i % 83 == 0:
            v = o.vista_buchi()
            assert isinstance(v, CERT.VistaBuchi)
            assert v == o.buchi() and isinstance(o.buchi(), list)
            # ricalcolo completo, indipendente dal codice del replay
            atteso, prima = [], None
            for ms in o.libro_ms:
                if prima is not None and ms - prima >= 2000:
                    atteso.append((prima, ms))
                prima = ms
            assert list(v) == atteso
            viste.append((v, list(v)))
    for v, fotografia in viste:
        assert list(v) == fotografia                    # non e' cambiata
    ultima = viste[-1][0]
    for v, _f in viste:
        assert list(ultima)[:len(v)] == list(v)


@pytest.mark.parametrize("seme", range(12))
def test_running_e_battiti_incrementale_uguale_al_ricalcolo(seme):
    """Le scritture VERE del DB finto del replay (`_DbFinto.set_control`):
    running che cambia (riavvio), stop che arriva e cambia, heartbeat prima e
    dopo lo stop, scritture rifiutate dal CHECK: stesso (running, battiti) del
    ricalcolo completo, giro per giro."""
    from types import SimpleNamespace

    rng = random.Random(500 + seme)
    o = RR._Orologio()
    db = RR._DbFinto(o, {"status": "armed"}, {})
    banco = SimpleNamespace(db=db, stop_ms=None)
    t = 1_000.0
    for _ in range(400):
        t += rng.choice([0.0, 0.5, 1.0, 5.0])
        o.ora_s = t
        r = rng.random()
        if r < 0.05:
            db.set_control("1", status="running")
        elif r < 0.07:
            db.set_control("1", status="bogus")          # rifiutata dal CHECK
        elif r < 0.6:
            db.set_control("1", heartbeat_at="x", stats={"cycles": 0})
        elif r < 0.65:
            db.set_control("1", status="stopping")
        if rng.random() < 0.03:
            banco.stop_ms = int(t * 1000) - rng.randint(0, 20_000)
        if rng.random() < 0.01:
            banco.stop_ms = None
        veloce = RR._Banco.running_e_battiti(banco)
        lento = RR._Banco.running_e_battiti_lento(banco)
        assert veloce == lento


def test_vita_ms_in_memoria_segue_ogni_cambio_degli_interruttori(monkeypatch):
    """`_Banco.vita_ms` (chiamata a ogni book) tiene il risultato finche'
    interruttori e costanti di produzione non cambiano: stesso numero della
    funzione di produzione a ogni cambio, anche di una costante."""
    from types import SimpleNamespace

    from Betfair.stream.scalper import auto_mode as AM

    o = RR._Orologio()
    db = RR._DbFinto(o, {"status": "armed", "params": {}}, {})
    banco = SimpleNamespace(db=db)

    def atteso() -> int:
        p = db.control.get("params") or {}
        return int(1000 * AM.vita_sessione_s({k: bool(p.get(k)) for k in
                                              ("sniper_mode", "theta_mode", "ht_mode")}))

    combinazioni = [{}, {"sniper_mode": True}, {"sniper_mode": False},
                    {"sniper_mode": False, "ht_mode": True},
                    {"sniper_mode": False, "theta_mode": True},
                    {"sniper_mode": False, "ht_mode": True, "theta_mode": True},
                    {"sniper_mode": False}, None]
    for p in combinazioni + list(reversed(combinazioni)):
        db.control["params"] = p
        assert RR._Banco.vita_ms(banco) == atteso()
        assert RR._Banco.vita_ms(banco) == atteso()
    db.control["params"] = {"sniper_mode": False, "ht_mode": True}
    assert RR._Banco.vita_ms(banco) == atteso()
    monkeypatch.setattr(AM, "VITA_HT_S", AM.VITA_HT_S + 123)
    assert RR._Banco.vita_ms(banco) == atteso()


# ===========================================================================
# 2. S5 con lo stato della Memoria = S5 di oggi, giro per giro
# ===========================================================================
def test_s5_heartbeat_fermo_dentro_un_buco_e_fuori():
    """Fermo 12 s: dentro un silenzio della registrazione di 9 s non e' un
    difetto; lo stesso fermo senza buco (o con il buco altrove) lo e', con
    lo STESSO testo della versione di oggi."""
    a, b = 1_000_000, 1_012_000
    dentro = _oss(heartbeat_ms=[a, b], ms=b + 1000, buchi_registrazione_ms=[(a + 1000, a + 10_000)])
    fuori = _oss(heartbeat_ms=[a, b], ms=b + 1000, buchi_registrazione_ms=[(b + 5000, b + 20_000)])
    senza = _oss(heartbeat_ms=[a, b], ms=b + 1000)
    coda = _oss(heartbeat_ms=[a], ms=a + 9000)
    coda_nel_buco = _oss(heartbeat_ms=[a], ms=a + 9000, buchi_registrazione_ms=[(a + 500, a + 7000)])
    for oss in (dentro, fuori, senza, coda, coda_nel_buco):
        assert _s5_del_banco(oss, CERT.Memoria()) == _s5_di_oggi(oss)
        assert CERT._s5(oss) == _s5_di_oggi(oss)
    assert _s5_di_oggi(dentro) is None and _s5_di_oggi(coda_nel_buco) is None
    assert "heartbeat fermo per 12000" in (_s5_di_oggi(fuori) or "")
    assert "ultimo heartbeat 9000" in (_s5_di_oggi(coda) or "")


def _sequenza(seme: int, *, riavvio: bool = False, accorcia: bool = False):
    """Una vita di sessione sintetica: battiti ogni 5 s con ritardi veri e
    ritardi dentro i silenzi; i buchi arrivano un po' alla volta, a volte in
    RITARDO (coprono coppie di battiti gia' giudicate) e fuori ordine."""
    rng = random.Random(seme)
    t0 = 10_000_000
    ms = t0
    battiti: List[int] = [t0]
    buchi: List[Tuple[int, int]] = []
    tardivi: List[Tuple[int, int]] = []
    giri = []
    for g in range(260):
        ms += 1000
        ultimo = battiti[-1]
        r = rng.random()
        if ms - ultimo >= 5000:
            if r < 0.80:
                battiti.append(ms)
            elif r < 0.90:
                # silenzio della registrazione: il battito arriva tardi, il buco
                # lo spiega (subito o qualche giro dopo)
                d = rng.randint(7000, 20_000)
                ms += d
                battiti.append(ms)
                buco = (ms - d - rng.randint(0, 800), ms)
                (tardivi if rng.random() < 0.5 else buchi).append(buco)
            elif r < 0.95:
                # battito tardivo SENZA silenzio: difetto vero
                ms += rng.randint(2000, 9000)
                battiti.append(ms)
        if tardivi and rng.random() < 0.3:
            buchi.append(tardivi.pop(rng.randrange(len(tardivi))))
        if rng.random() < 0.05:
            buchi.append(_buco_casuale(rng, ms))
        if riavvio and g == 150:
            battiti = [ms]                       # il conto riparte
        elenco = list(buchi)
        if accorcia and g == 200 and elenco:
            elenco = elenco[:-3]                 # elenco NON prolungato
            buchi = list(elenco)
        giri.append(_oss(heartbeat_ms=list(battiti), ms=ms,
                         buchi_registrazione_ms=elenco,
                         sessione_viva=rng.random() > 0.05))
    return giri


@pytest.mark.parametrize("seme", range(30))
@pytest.mark.parametrize("variante", ["normale", "riavvio", "accorcia", "vista"])
def test_s5_con_memoria_uguale_a_oggi_giro_per_giro(seme, variante):
    giri = _sequenza(seme, riavvio=variante == "riavvio", accorcia=variante == "accorcia")
    mem = CERT.Memoria()
    soll_nuovo: dict = {}
    registro = CERT.RegistroBuchi()
    visti = 0
    for oss in giri:
        atteso = _s5_di_oggi(oss)
        if variante == "vista":
            elenco = list(oss.buchi_registrazione_ms)
            for ga, gb in elenco[visti:]:
                registro.aggiungi(ga, gb)
            visti = len(elenco)
            oss.buchi_registrazione_ms = registro.vista()   # type: ignore[assignment]
        assert _s5_del_banco(oss, mem, soll_nuovo) == atteso
    assert soll_nuovo.get("S5") == len(giri)


def test_s5_un_buco_tolto_rende_di_nuovo_difettosa_una_coppia_gia_sana():
    """La coppia giudicata sana grazie a un buco NON resta sana se l'elenco
    cambia e il buco sparisce (il ricordo delle coppie sane si butta)."""
    a, b = 1_000_000, 1_012_000
    mem = CERT.Memoria()
    con = _oss(heartbeat_ms=[a, b], ms=b + 1000, buchi_registrazione_ms=[(a + 1000, a + 10_000)])
    assert _s5_del_banco(con, mem) is None
    senza = _oss(heartbeat_ms=[a, b], ms=b + 1000, buchi_registrazione_ms=[])
    assert _s5_del_banco(senza, mem) == _s5_di_oggi(senza)
    assert "heartbeat fermo per 12000" in (_s5_del_banco(senza, mem) or "")


def test_s5_un_buco_tardivo_sana_una_coppia_come_oggi():
    """Una coppia difettosa NON si ricorda: se il buco che la spiega arriva un
    giro dopo, da quel giro non e' piu' un difetto (come oggi)."""
    a, b = 1_000_000, 1_012_000
    mem = CERT.Memoria()
    prima = _oss(heartbeat_ms=[a, b], ms=b + 1000, buchi_registrazione_ms=[(0, 10)])
    dopo = _oss(heartbeat_ms=[a, b], ms=b + 2000,
                buchi_registrazione_ms=[(0, 10), (a + 1000, a + 10_000)])
    assert _s5_del_banco(prima, mem) == _s5_di_oggi(prima) and _s5_di_oggi(prima)
    assert _s5_del_banco(dopo, mem) == _s5_di_oggi(dopo) is None
