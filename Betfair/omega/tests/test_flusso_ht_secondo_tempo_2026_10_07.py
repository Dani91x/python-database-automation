"""07/10/2026 - Omega cieco per il flusso dell'HALF TIME SCORE.

Caso vero (registrazione 35760084, banco comune, scenario `apertura`): dal 25/09
la gamba 2T sul Correct Score ('3 - 3' a 300) partiva; dal commit 304a8e1d
(29/09, cantiere J2 "flusso dati interrotto") non parte piu'. Causa: dal 44'
lo scanner smette di seguire l'Half Time Score (finestra dei candidati HT) e il
blocco `ht` della riga resta SOSPESO per tutto il secondo tempo: il blocco
`flusso` della riga lo mette in `mercati_fermi`. `omega_service._flusso_feed`
valutava SEMPRE MATCH_ODDS + Correct Score + Half Time Score, quindi per tutto il
secondo tempo diceva "fermo": `_feed_fresh_for_decision` falso ->
`_live_state_for` senza stato -> `no_live_state` -> nessuna gamba 2T valutata,
mai una lettura del mercato (read_market x0 contro x108 del 25/09).
Stesso difetto nel PRIMO tempo per la V3 (di serie, solo Correct Score): un HT
senza prezzi dopo un gol (61 s al 30' e 68 s al 40' sulla 35797769, Correct
Score e Match Odds vivi) fermava anche lei.

Regola della decisione dell'utente (28/09, punto 11 del brief): "se i prezzi di
una partita non sono vivi nessun bot apre ne' chiude a mercato su QUEI prezzi".
L'HT e' il mercato della sola gamba v2 del primo tempo (e delle sue chiusure,
proposte e missioni): il suo flusso conta solo li', e solo in fase pre/1T.

Finti VERI dove conta: righe prodotte dallo SCANNER di produzione
(`build_rows`), book `MarketBook` di betfairlightweight, stati IPS della
registrazione (`KickOff`, `SecondHalfKickOff`, `FirstHalfEnd`), funzioni di
Omega di produzione (`_scan_event_legs` vero, parametri di serie da
`omega_config.resolve_params`). Nessuna rete, nessun DB.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List

from Betfair.safe_strategy.tests.test_flusso_interrotto_cantiere_j_2026_09_28 import (
    MO, CacheFinta, Orologio, book, giro, runner_dict, scanner_calcio,
)

CS = [runner_dict(1, (8.0, 50.0), (8.4, 40.0)), runner_dict(2, (300.0, 5.0), (320.0, 4.0))]
HT = [runner_dict(7, (3.0, 50.0), (3.1, 40.0)), runner_dict(8, (5.0, 20.0), (5.2, 15.0))]


def _scanner(ck: Orologio):
    scan = scanner_calcio(ck)
    scan.cs_markets["c1"] = {"market_id": "1.CS", "names": {1: "0 - 0", 2: "3 - 3"}}
    scan.ht_markets["c1"] = {"market_id": "1.HT", "names": {7: "0 - 0", 8: "1 - 0"}}
    scan._rebuild_market_index()
    return scan


def _riga(fase: str, fermo: str) -> dict:
    """Riga dello scanner vero.

    ``fase``: '1t' (minuto 32, IPS ``KickOff``) o '2t' (minuto 60, IPS
    ``SecondHalfKickOff``). ``fermo``: 'ht' = l'Half Time Score smette di
    ricevere book (blocco lasciato SOSPESO, come dal 44' nella registrazione),
    'cs' = il Correct Score smette di riceverli."""
    ck = Orologio()
    scan = _scanner(ck)
    tab: Dict[str, dict] = {}
    scan.events["c1"].update(minute=30, score_raw={"matchStatus": "KickOff"})
    for mid, rr in (("1.200", MO), ("1.CS", CS), ("1.HT", HT)):
        scan._apply_market_book(book(mid, rr))
    giro(scan, tab)
    assert tab["c1"]["payload"]["flusso"]["mercati_fermi"] == []
    if fermo == "ht":
        # ultimo book dell'HT: la sospensione, poi piu' niente
        scan._apply_market_book(book("1.HT", HT, status="SUSPENDED"))
    for _ in range(4):                                   # 4 x 30 s > soglia in gioco (45 s)
        ck.t += 30.0
        scan._apply_market_book(book("1.200", MO))
        if fermo != "cs":
            scan._apply_market_book(book("1.CS", CS))
        if fermo != "ht":
            scan._apply_market_book(book("1.HT", HT))
    if fase == "2t":
        scan.events["c1"].update(minute=60, score_raw={"matchStatus": "SecondHalfKickOff"})
    else:
        scan.events["c1"].update(minute=32, score_raw={"matchStatus": "KickOff"})
    giro(scan, tab)
    pay = tab["c1"]["payload"]
    atteso = ["1.HT"] if fermo == "ht" else ["1.CS"]
    assert pay["flusso"]["mercati_fermi"] == atteso, pay["flusso"]
    assert pay["flusso"]["vivo"] is True                 # il MATCH_ODDS e' vivo
    if fermo == "ht":
        assert pay["ht"]["status"] == "SUSPENDED"        # come nella registrazione
    return dict(tab["c1"], updated_at=datetime.now(timezone.utc).isoformat())


def _omega(monkeypatch, riga: dict):
    from Betfair.omega import omega_service as OS

    cache = CacheFinta({"c1": riga})
    monkeypatch.setattr(OS._scan_feed, "shared_cache", lambda: cache)
    for d in (OS._CACHE_FEED_RIGHE, OS._CACHE_FEED_LETTO_A, OS._CACHE_FEED_CHIESTO_A,
              OS._CACHE_SCANNER):
        d.clear()
    monkeypatch.setattr(OS, "_canale_scan_attivo", lambda: None)
    OS._SKIP_SEEN.clear()
    return OS


class _Db:
    def __init__(self) -> None:
        self.attivita: List[tuple] = []

    def log(self, kind, payload):
        self.attivita.append((kind, payload))


def _gambe(monkeypatch, riga: dict, versione: int):
    """``_scan_event_legs`` VERO sulla riga: stato, fase e veto del flusso dal
    feed. Si ferma al primo passo dopo i veti (``_leg_retry_allowed``), che
    registra quale gamba e' arrivata fin li'."""
    from Betfair.omega import omega_config

    OS = _omega(monkeypatch, riga)
    tentate: List[Any] = []
    monkeypatch.setattr(OS, "_leg_retry_allowed",
                        lambda eid, leg, now: tentate.append(leg) or False)
    params = omega_config.resolve_params({"strategy_version": versione})
    db = _Db()
    ev = SimpleNamespace(event_id="c1", open_date=None, name="Roma v Lazio")
    OS._scan_event_legs(ev=ev, events=[ev], control={}, params=params, traded_ids=set(),
                        traded_legs=set(), aggregates={}, market=OS._real_market, db=db,
                        now=datetime.now(timezone.utc), score_lookup=None, goal=0.0,
                        realized=0.0, mode="paper", commission=0.05, traded_count=0,
                        minutes_seen={})
    return tentate, db


# ---------------------------------------------------------------- 2T: il caso vero
def test_2t_ht_fermo_omega_vede_i_prezzi_vivi_e_lo_stato(monkeypatch):
    """IL CASO VERO: secondo tempo, HT lasciato sospeso dallo scanner, MATCH_ODDS
    e Correct Score vivi -> Omega ha lo stato per decidere la gamba 2T."""
    OS = _omega(monkeypatch, _riga("2t", "ht"))
    es = OS._flusso_feed("c1")
    assert es.vivo is True, es.testo
    assert OS._flusso_feed_ht("c1").vivo is True        # nel 2T l'HT non conta piu'
    assert OS._feed_fresh_for_decision(OS._real_market, "c1") is True
    assert OS._cs_from_feed(OS._real_market, "c1") is not None
    st, _status, score = OS._live_state_for(OS._real_market, SimpleNamespace(event_id="c1"),
                                            None, datetime.now(timezone.utc), decision=True)
    assert st is not None and st.minute == 60 and score == "0-0"


def test_2t_ht_fermo_la_gamba_2t_si_valuta_v2_e_v3(monkeypatch):
    """Al livello delle gambe: la gamba del secondo tempo arriva alla
    valutazione, in v2 e in v3 (prima: `no_live_state` e return)."""
    for versione in (2, 3):
        tentate, db = _gambe(monkeypatch, _riga("2t", "ht"), versione)
        assert tentate == ["ft_cs"], (versione, db.attivita)
        assert not [k for k, _p in db.attivita if k == "flusso_interrotto"]


def test_2t_cs_fermo_resta_fermo(monkeypatch):
    """Il veto del flusso NON si allenta sul mercato della gamba 2T."""
    OS = _omega(monkeypatch, _riga("2t", "cs"))
    assert OS._flusso_feed("c1").vivo is False
    assert OS._feed_fresh_for_decision(OS._real_market, "c1") is False
    assert OS._cs_from_feed(OS._real_market, "c1") is None
    for versione in (2, 3):
        tentate, _db = _gambe(monkeypatch, _riga("2t", "cs"), versione)
        assert tentate == [], versione


# ---------------------------------------------------------------- 1T
def test_1t_ht_fermo_v3_non_e_cieca(monkeypatch):
    """35797769, 30'-31' e 40'-41': HT senza prezzi, Correct Score e Match Odds
    vivi. La V3 (di serie) decide solo sul Correct Score: la gamba A si valuta."""
    OS = _omega(monkeypatch, _riga("1t", "ht"))
    assert OS._flusso_feed("c1").vivo is True
    assert OS._feed_fresh_for_decision(OS._real_market, "c1") is True
    tentate, db = _gambe(monkeypatch, _riga("1t", "ht"), 3)
    assert tentate == ["ht_cs"], db.attivita
    assert not [k for k, _p in db.attivita if k == "flusso_interrotto"]


def test_1t_ht_fermo_v2_la_gamba_ht_resta_ferma_e_lo_dice(monkeypatch):
    """La gamba v2 del primo tempo decide sull'HT: il suo flusso fermo la
    blocca come dal 28/09 e l'attivita' dice quale mercato."""
    OS = _omega(monkeypatch, _riga("1t", "ht"))
    es = OS._flusso_feed_ht("c1")
    assert es.vivo is False and es.mercati == ("1.HT",)
    tentate, db = _gambe(monkeypatch, _riga("1t", "ht"), 2)
    assert tentate == []
    fl = [p for k, p in db.attivita if k == "flusso_interrotto"]
    assert len(fl) == 1 and fl[0]["mercati"] == ["1.HT"] and fl[0]["leg"] == "ht_cs"


def test_1t_cs_fermo_blocca_v2_e_v3(monkeypatch):
    """Primo tempo col Correct Score fermo: nessuna gamba, in v2 e in v3."""
    for versione in (2, 3):
        tentate, _db = _gambe(monkeypatch, _riga("1t", "cs"), versione)
        assert tentate == [], versione


def test_chiusura_di_una_gamba_ht_guarda_l_ht(monkeypatch):
    """Green-up e proposte di una gamba SULL'HT (v2, o v2 rimasta aperta dopo
    il passaggio alla v3): prezzi del blocco HT usabili solo col flusso HT
    vivo; una gamba sul Correct Score non guarda l'HT."""
    OS = _omega(monkeypatch, _riga("1t", "ht"))
    assert OS._prezzi_del_blocco_freschi(OS._real_market, "c1", True) is False
    assert OS._prezzi_del_blocco_freschi(OS._real_market, "c1", False) is True
    OS = _omega(monkeypatch, _riga("1t", "cs"))
    assert OS._prezzi_del_blocco_freschi(OS._real_market, "c1", False) is False


# ---------------------------------------------------------------- fase
def test_2t_ht_fermo_senza_stato_ips_decide_il_minuto(monkeypatch):
    """Senza stato IPS nella riga la fase la dice il minuto (come
    ``omega_engine.mission_phase``): 60' = secondo tempo, l'HT non conta."""
    riga = _riga("2t", "ht")
    riga["payload"] = dict(riga["payload"], score_raw=None)
    OS = _omega(monkeypatch, riga)
    assert OS._flusso_feed_ht("c1").vivo is True


def test_intervallo_lo_dice_lo_stato_ips_non_il_minuto(monkeypatch):
    """All'intervallo (IPS ``FirstHalfEnd``, minuto 45) l'Half Time Score e'
    finito anche se il minuto dice ancora primo tempo: la fase la decide lo
    stato IPS, come per la missione."""
    riga = _riga("2t", "ht")
    riga["payload"] = dict(riga["payload"], minute=45,
                           score_raw={"matchStatus": "FirstHalfEnd"})
    OS = _omega(monkeypatch, riga)
    assert OS._flusso_feed_ht("c1").vivo is True


def test_la_fase_non_dipende_dall_orologio_di_sistema(monkeypatch):
    """Nel banco l'orologio di sistema NON e' il tempo di mercato: la fase
    dell'HT deve venire solo da stato IPS e minuto (``kickoff=None``: il ramo
    dell'orologio di ``mission_phase`` non si raggiunge mai). Stessi esiti con
    l'orologio nel 1970 e nel 2100."""
    from Betfair.omega import omega_service as OS

    casi = [
        ({"score_raw": {"matchStatus": "KickOff"}, "minute": 30}, True),
        ({"score_raw": {"matchStatus": "SecondHalfKickOff"}, "minute": 60}, False),
        ({"score_raw": {"matchStatus": "FirstHalfEnd"}, "minute": 45}, False),
        ({"score_raw": None, "minute": 46}, False),
        ({"score_raw": None, "minute": 44}, True),
        ({"score_raw": None, "minute": None}, True),      # niente dati: conta, come prima
    ]
    for anno in (1970, 2100):
        class _Orologio(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(anno, 1, 1, tzinfo=tz or timezone.utc)

        monkeypatch.setattr(OS, "datetime", _Orologio)
        for payload, atteso in casi:
            assert OS._ht_ancora_in_gioco(payload) is atteso, (anno, payload)


def test_proposta_d_uscita_di_una_gamba_ht_chiede_il_flusso_dell_ht(monkeypatch):
    """`omega_proposte._una_gamba`: per una gamba SULL'HT la freschezza dei
    prezzi del blocco si chiede con ``half=True`` (anche il flusso dell'HT),
    per una gamba sul Correct Score con ``half=False``. Col blocco non fresco
    nessuna proposta coi prezzi del feed."""
    from Betfair.omega import omega_proposte as PR
    from Betfair.omega import omega_service as S
    from Betfair.omega.test_omega_proposte_2026_09_17 import (
        DbFinto, MercatoFinto, _lay, _params, _payload_feed,
    )

    chiesti: List[Any] = []
    monkeypatch.setattr(S, "_prezzi_del_blocco_freschi",
                        lambda market, eid, half: chiesti.append(half) or False)
    S.svuota_le_cache()
    pay = _payload_feed(minute=30)
    pay["ht"] = dict(pay["cs"], market_id="1.HT")
    for tr, atteso in ((_lay(market_id="1.HT", market_type="HALF_TIME_SCORE",
                             phase="ht_cs", minute_at_entry=25), True),
                       (_lay(), False)):
        chiesti.clear()
        db = DbFinto([tr])
        PR.process_proposte_uscita(params=_params(), market=MercatoFinto(), db=db,
                                   now=datetime(2026, 9, 17, 20, 30, tzinfo=timezone.utc),
                                   feed=lambda _eid: pay)
        assert chiesti == [atteso], (tr["phase"], chiesti)
        assert db.richieste == []
    S.svuota_le_cache()
