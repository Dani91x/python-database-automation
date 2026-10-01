"""ATTESA DEL FISCHIO (01/10/2026) - una partita non sparisce dal feed fra
l'orario PREVISTO del calcio d'inizio e il momento in cui Betfair la mette in
gioco.

Difetto accertato il 01/10: Greece U21 v Latvia U21 (36132210), Mike in LIVE
con 5 EUR sul mercato (punta Under 3,5 + green appoggiato). Alle 17:00:00 lo
scanner ha RIMOSSO la riga («pubblicate 17 righe, rimosse 4») perche'
``in_pre_ko_window`` chiede ``0 < delta``; la riga e' tornata alle 17:02:04
quando Betfair ha messo la partita in gioco. Due minuti senza quote ne'
punteggio con una posizione aperta, per una causa INTERNA.

Ordine dell'utente (01/10): «TUTTI I BOT NON DEVONO ESSERE MAI CIECHI PER
NESSUN MOTIVO, a meno che non dipenda da Betfair».

Nessuna rete/DB: client Betfair finto (stessa forma di ``test_pre_ko_ou.py``,
oggetti betfairlightweight con gli stessi attributi). File ASCII-only.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from Betfair.safe_strategy import scanner
from Betfair.safe_strategy import service as S

# orologio REALE: _apply_opp_book (chiamato dallo stream, senza `now`) usa
# datetime.now; tutti gli offset sono relativi
NOW = datetime.now(timezone.utc)
EID = "36132210"           # Greece U21 v Latvia U21, l'evento del 01/10
UN_SECONDO = timedelta(seconds=1)
TETTO = timedelta(seconds=scanner.POST_KO_WAIT_SEC)


def iso(dt):
    return dt.isoformat()


# ---------------------------------------------------------------- logica pura
def test_costante_tetto_allineata_a_mike():
    """Il tetto e' quello di Mike (_MATCH_OVER_S): feed e bot, stesso orologio."""
    from Betfair.mike import service as M

    assert scanner.POST_KO_WAIT_SEC == 3 * 3600
    assert float(scanner.POST_KO_WAIT_SEC) == M._MATCH_OVER_S


def test_esposto_un_secondo_dopo_il_fischio_previsto_resta_monitorabile():
    ko = iso(NOW - UN_SECONDO)
    # la finestra pre-KO da sola NON lo tiene (il difetto)
    assert scanner.in_pre_ko_window(ko, NOW) is False
    assert scanner.in_post_ko_wait(False, "OPEN", ko, NOW, esposto=True) is True
    assert scanner.is_monitorable(False, ko, NOW, 3.0, mo_status="OPEN", esposto=True) is True


def test_esattamente_all_orario_previsto_resta_monitorabile():
    ko = iso(NOW)
    assert scanner.in_pre_ko_window(ko, NOW) is False          # 0 < delta: escluso
    assert scanner.is_monitorable(False, ko, NOW, mo_status="OPEN") is True


def test_senza_esposizione_resta_fino_al_tetto_poi_esce():
    entro = iso(NOW - TETTO)                  # esattamente al tetto: dentro
    oltre = iso(NOW - TETTO - UN_SECONDO)     # un secondo oltre: fuori
    assert scanner.is_monitorable(False, entro, NOW, mo_status="OPEN") is True
    assert scanner.is_monitorable(False, oltre, NOW, mo_status="OPEN") is False
    assert scanner.is_monitorable(False, oltre, NOW, 3.0, mo_status=None) is False


def test_esposto_oltre_il_tetto_resta_finche_betfair_non_decide():
    oltre = iso(NOW - TETTO - timedelta(hours=5))
    assert scanner.is_monitorable(False, oltre, NOW, mo_status="OPEN", esposto=True) is True


def test_in_gioco_resta_monitorabile():
    ko = iso(NOW - UN_SECONDO)
    assert scanner.is_monitorable(True, ko, NOW, mo_status="OPEN") is True
    assert scanner.is_monitorable(True, iso(NOW - TETTO * 2), NOW) is True


def test_match_odds_chiuso_non_monitorabile():
    ko = iso(NOW - UN_SECONDO)
    assert scanner.in_post_ko_wait(False, "CLOSED", ko, NOW, esposto=True) is False
    assert scanner.is_monitorable(False, ko, NOW, 3.0, mo_status="CLOSED", esposto=True) is False


def test_prima_del_fischio_niente_cambia():
    """Prima dell'orario previsto decidono SOLO le finestre di sempre."""
    lontano = iso(NOW + timedelta(hours=2))
    assert scanner.in_post_ko_wait(False, "OPEN", lontano, NOW, esposto=True) is False
    assert scanner.is_monitorable(False, lontano, NOW, mo_status="OPEN", esposto=True) is False
    assert scanner.is_monitorable(False, None, NOW, mo_status="OPEN", esposto=True) is False


# ---------------------------------------------------------------- service (finti)
class _Betting:
    def __init__(self, cats):
        self.cats = cats
        self.calls = []

    def list_market_catalogue(self, **kw):
        self.calls.append(kw)
        types = set(kw["filter"].get("marketTypeCodes") or [])
        return [c for c in self.cats if c.description.market_type in types]


def _cat(event_id, market_id, mtype, runners):
    return SimpleNamespace(
        event=SimpleNamespace(id=event_id, name="Greece U21 v Latvia U21"),
        market_id=market_id,
        market_name=None,
        description=SimpleNamespace(market_type=mtype),
        runners=[SimpleNamespace(selection_id=s, runner_name=n) for s, n in runners],
    )


def _book(market_id, inplay=False, bet_delay=0, status="OPEN", sel=(1222344, 1222345)):
    ex = SimpleNamespace(
        available_to_back=[SimpleNamespace(price=1.50, size=30.0)],
        available_to_lay=[SimpleNamespace(price=1.52, size=25.0)],
    )
    return SimpleNamespace(
        market_id=market_id, status=status, inplay=inplay, bet_delay=bet_delay,
        total_matched=1234.0,
        runners=[SimpleNamespace(selection_id=s, status="ACTIVE", ex=ex) for s in sel],
    )


CATS = [
    _cat(EID, "1.OU35", "OVER_UNDER_35", [(1222344, "Under 3.5 Goals"), (1222345, "Over 3.5 Goals")]),
    _cat(EID, "1.OU45", "OVER_UNDER_45", [(1222347, "Under 4.5 Goals"), (1222346, "Over 4.5 Goals")]),
]


def _scanner(ko_dt, seguite=()):
    """Scanner VERO in dry con il client finto. La partita ha gia' il catalogo
    O/U 3.5/4.5 (ramo pre-KO) e il Match Odds visto dallo stream (non in gioco)."""
    scan = S.Scanner(SimpleNamespace(betting=_Betting(CATS)), dry=True, use_stream=False)
    scan.pre_ko_ou_hours = 3.0
    scan.sports["calcio"].metas = {
        EID: {"event_id": EID, "market_id": "1.MO1", "event_name": "Greece U21 v Latvia U21",
              "open_date": iso(ko_dt), "competition": "UEFA U21",
              "runners": [], "sides": {"home": 11, "away": 12, "draw": 13}},
    }
    scan.sports["calcio"].catalogue_ts = 1.0
    scan.sports["tennis"].catalogue_ts = 1.0
    scan._rebuild_market_index()
    # catalogo delle due linee preso PRIMA del fischio (ramo pre-KO)
    scan.opp_markets[EID] = {
        "1.OU35": {"market_id": "1.OU35", "market_type": "OVER_UNDER_35", "line": 3.5,
                   "names": {1222344: "Under 3.5 Goals", 1222345: "Over 3.5 Goals"}},
        "1.OU45": {"market_id": "1.OU45", "market_type": "OVER_UNDER_45", "line": 4.5,
                   "names": {1222347: "Under 4.5 Goals", 1222346: "Over 4.5 Goals"}},
    }
    scan._rebuild_market_index()
    scan.events[EID] = {"sport": "calcio", "inplay": False, "mo_status": "OPEN"}
    scan._apply_market_book(_book("1.OU35"))
    scan._apply_market_book(_book("1.OU45", sel=(1222347, 1222346)))
    scan.events[EID].update({"inplay": False, "mo_status": "OPEN"})
    # partite di Mike CON esposizione: in dry ``_mike_followed`` torna questa lista
    scan._mike_followed_ids = [str(e) for e in seguite]
    return scan


def test_build_rows_mike_esposto_un_secondo_dopo_il_fischio_riga_resta():
    """Lo scenario ESATTO del 01/10: esposizione di Mike, KO previsto passato da
    1 s, Betfair non l'ha ancora messa in gioco -> la riga resta, con le linee."""
    scan = _scanner(NOW - UN_SECONDO, seguite=[EID])
    rows, wanted = scan.build_rows(NOW)
    assert wanted == [EID]
    assert len(rows) == 1
    p = rows[0]["payload"]
    assert p["inplay"] is False and p["mo_status"] == "OPEN"
    assert sorted(b["line"] for b in p["ou"]) == [3.5, 4.5]


def test_publish_non_rimuove_la_riga_al_fischio_previsto():
    """«pubblicate 17 righe, rimosse 4»: la riga scritta prima del fischio NON
    va fra le rimosse un secondo dopo l'orario previsto."""
    scan = _scanner(NOW + timedelta(minutes=5), seguite=[EID])
    scritte, rimosse = scan.publish(NOW)
    assert scritte == 1 and rimosse == 0
    scan.written_sig[EID] = "firma-precedente"
    dopo = NOW + timedelta(minutes=5) + UN_SECONDO
    _, rimosse = scan.publish(dopo)
    assert rimosse == 0


def test_build_rows_senza_esposizione_oltre_il_tetto_esce():
    scan = _scanner(NOW - TETTO - UN_SECONDO, seguite=())
    rows, wanted = scan.build_rows(NOW)
    assert wanted == [] and rows == []


def test_build_rows_senza_esposizione_entro_il_tetto_resta():
    scan = _scanner(NOW - timedelta(minutes=2), seguite=())
    _, wanted = scan.build_rows(NOW)
    assert wanted == [EID]


def test_build_rows_esposto_oltre_il_tetto_resta():
    scan = _scanner(NOW - TETTO - timedelta(hours=1), seguite=[EID])
    _, wanted = scan.build_rows(NOW)
    assert wanted == [EID]


def test_build_rows_in_gioco_resta():
    scan = _scanner(NOW - UN_SECONDO, seguite=[EID])
    scan.events[EID].update({"inplay": True, "minute": 1, "score_home": 0, "score_away": 0})
    _, wanted = scan.build_rows(NOW)
    assert wanted == [EID]


def test_build_rows_match_odds_chiuso_esce_anche_se_esposto():
    scan = _scanner(NOW - UN_SECONDO, seguite=[EID])
    scan.events[EID]["mo_status"] = "CLOSED"
    _, wanted = scan.build_rows(NOW)
    assert wanted == []


# ---------------------------------------------------------------- stream
def test_linee_di_mike_restano_nello_stream_durante_l_attesa_del_fischio():
    """Le due linee della posizione (3.5/4.5) restano nella sottoscrizione fra
    il fischio previsto e l'in-play, al tier 1.5 (mai tagliate dallo shard)."""
    scan = _scanner(NOW - UN_SECONDO, seguite=[EID])
    ranked = scan._opp_ranked_market_ids(NOW)
    assert sorted(mid for _, mid in ranked) == ["1.OU35", "1.OU45"]
    assert all(key[0] == 1.5 for key, _ in ranked)
    assert {"1.OU35", "1.OU45"} <= set(scan.relevant_market_ids("calcio", NOW))
    # ... e il Match Odds c'era gia' (is_relevant_market: KO passato e non CLOSED)
    assert "1.MO1" in scan.relevant_market_ids("calcio", NOW)
    # nessuna chiamata a Betfair per tenerle
    assert scan.client.betting.calls == []


def test_linee_non_seguite_non_entrano_nello_stream_dopo_il_fischio():
    """Senza esposizione nulla cambia nel peso dello stream: le linee a gol di
    una partita non seguita restano fuori come prima."""
    scan = _scanner(NOW - UN_SECONDO, seguite=())
    assert scan._opp_ranked_market_ids(NOW) == []


def test_linee_di_mike_pre_ko_al_tier_della_posizione():
    """Pre-KO con posizione di Mike: tier 1.5 (prima tier 2, uscivano per prime
    a pool pieno). Senza posizione resta tier 2 come prima."""
    seguita = _scanner(NOW + timedelta(hours=1), seguite=[EID])
    assert {key[0] for key, _ in seguita._opp_ranked_market_ids(NOW)} == {1.5}
    libera = _scanner(NOW + timedelta(hours=1), seguite=())
    assert {key[0] for key, _ in libera._opp_ranked_market_ids(NOW)} == {2}


def test_linee_escono_dallo_stream_a_match_odds_chiuso():
    scan = _scanner(NOW - UN_SECONDO, seguite=[EID])
    scan.events[EID]["mo_status"] = "CLOSED"
    assert scan._opp_ranked_market_ids(NOW) == []
