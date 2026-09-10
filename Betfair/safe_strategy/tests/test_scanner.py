"""Test della logica PURA dello scanner Safe Strategy (nessuna rete/DB)."""
from datetime import datetime, timedelta, timezone

from Betfair.safe_strategy import scanner, stream


def test_selection_sides_da_sort_priority():
    runners = [
        {"selection_id": 11, "name": "Nord FC", "sort_priority": 1},
        {"selection_id": 22, "name": "Sud FC", "sort_priority": 2},
        {"selection_id": 33, "name": "The Draw", "sort_priority": 3},
    ]
    assert scanner.selection_sides(runners) == {"home": 11, "away": 22, "draw": 33}


def test_selection_sides_fallback_nome_draw():
    runners = [
        {"selection_id": 11, "name": "Nord FC", "sort_priority": 1},
        {"selection_id": 22, "name": "Sud FC", "sort_priority": 2},
        {"selection_id": 33, "name": "The Draw", "sort_priority": None},
    ]
    assert scanner.selection_sides(runners)["draw"] == 33


def test_tennis_sides():
    runners = [
        {"selection_id": 1, "name": "Rossi", "sort_priority": 1},
        {"selection_id": 2, "name": "Bianchi", "sort_priority": 2},
    ]
    assert scanner.tennis_sides(runners) == {"p1": 1, "p2": 2}


def test_split_event_name():
    assert scanner.split_event_name("Udinese v Venezia") == ("Udinese", "Venezia")
    assert scanner.split_event_name("Rossi vs Bianchi") == ("Rossi", "Bianchi")
    assert scanner.split_event_name("SenzaSeparatore") == (None, None)
    assert scanner.split_event_name(None) == (None, None)


def test_is_cs_candidate_soglia_aperta_e_gol():
    # REGOLA 09/09: il minuto è una SOGLIA ("dal 30' in poi"), mai un tetto
    assert scanner.is_cs_candidate(49, 1, 0) is True
    assert scanner.is_cs_candidate(29, 1, 0) is False    # troppo presto
    assert scanner.is_cs_candidate(30, 1, 0) is True     # Omega entra dal 30'
    assert scanner.is_cs_candidate(61, 1, 0) is True     # nessun tetto di minuto
    assert scanner.is_cs_candidate(89, 0, 0) is True
    assert scanner.is_cs_candidate(49, 3, 0) is True     # 3-x è ancora una scoreline quotata
    assert scanner.is_cs_candidate(49, 4, 0) is False    # troppi gol per lato
    assert scanner.is_cs_candidate(None, 1, 0) is False  # dati mancanti
    assert scanner.is_cs_candidate(49, None, 0) is False


def test_is_hot_minute_soglia_aperta():
    assert scanner.is_hot_minute(39) is False
    assert scanner.is_hot_minute(40) is True
    assert scanner.is_hot_minute(78) is True
    assert scanner.is_hot_minute(95) is True   # recupero: ancora caldo
    assert scanner.is_hot_minute(None) is False


def test_is_relevant_market_e_rank():
    now = datetime.now(timezone.utc)
    soon = (now + timedelta(minutes=10)).isoformat()
    far = (now + timedelta(hours=3)).isoformat()
    past = (now - timedelta(minutes=30)).isoformat()
    # in-play: sempre rilevante (salvo CLOSED)
    assert scanner.is_relevant_market(True, "OPEN", far, now) is True
    assert scanner.is_relevant_market(True, "CLOSED", far, now) is False
    # pre-KO entro 20': rilevante (cattura riferimento pre-KO); KO lontano: no
    assert scanner.is_relevant_market(False, None, soon, now) is True
    assert scanner.is_relevant_market(False, None, far, now) is False
    # KO passato senza book ancora visto (inplay ignoto): rilevante
    assert scanner.is_relevant_market(None, None, past, now) is True
    # senza orario: rilevante solo finché lo stato è ignoto
    assert scanner.is_relevant_market(None, None, None, now) is True
    assert scanner.is_relevant_market(False, "OPEN", None, now) is False
    assert scanner.rank_key(True, far) < scanner.rank_key(False, soon)
    assert scanner.rank_key(False, soon) < scanner.rank_key(False, far)


def test_pre_ko_window():
    now = datetime.now(timezone.utc)
    dentro = (now + timedelta(minutes=10)).isoformat()
    lontano = (now + timedelta(hours=3)).isoformat()
    passato = (now - timedelta(minutes=1)).isoformat()
    assert scanner.in_pre_ko_window(dentro, now) is True
    assert scanner.in_pre_ko_window(lontano, now) is False
    assert scanner.in_pre_ko_window(passato, now) is False
    assert scanner.in_pre_ko_window(None, now) is False


def test_freeze_pre_ko_congela_al_primo_inplay():
    odds = {"home": {"back": 1.65}, "draw": {"back": 4.0}, "away": {"back": 5.5}}
    ref = scanner.freeze_pre_ko(None, inplay=False, odds=odds)
    assert ref is not None and ref["home"] == 1.65 and "captured_at" in ref
    # pre-KO: si aggiorna (closing line)
    odds2 = {"home": {"back": 1.7}, "draw": {"back": 4.0}, "away": {"back": 5.2}}
    ref2 = scanner.freeze_pre_ko(ref, inplay=False, odds=odds2)
    assert ref2 is not None and ref2["home"] == 1.7
    # in-play: CONGELATO — mai quote live nel riferimento
    odds_live = {"home": {"back": 1.2}, "draw": {"back": 8.0}, "away": {"back": 15.0}}
    assert scanner.freeze_pre_ko(ref2, inplay=True, odds=odds_live) is ref2
    # 1X2 incompleto: il riferimento precedente resta
    assert scanner.freeze_pre_ko(ref2, inplay=False, odds={"home": {"back": None}}) is ref2
    # mai nato pre-KO → resta None anche in-play
    assert scanner.freeze_pre_ko(None, inplay=True, odds=odds_live) is None


def test_cadenze_adattive():
    assert scanner.books_period_calcio(any_inplay=True, any_hot=True) == 10.0
    assert scanner.books_period_calcio(any_inplay=True, any_hot=False) == 20.0
    assert scanner.books_period_calcio(any_inplay=False, any_hot=False) == 60.0
    assert scanner.books_period_tennis(True) == 10.0
    assert scanner.books_period_tennis(False) == 60.0


def test_payload_signature_stabile_e_sensibile():
    p1 = {"a": 1, "b": {"c": [1, 2]}}
    p2 = {"b": {"c": [1, 2]}, "a": 1}       # stesso contenuto, ordine diverso
    p3 = {"a": 1, "b": {"c": [1, 3]}}
    assert scanner.payload_signature(p1) == scanner.payload_signature(p2)
    assert scanner.payload_signature(p1) != scanner.payload_signature(p3)


def test_build_cs_block_riconosce_any_other():
    sels = [
        {"name": "1 - 0", "back": 3.0, "lay": 3.1},
        {"name": "Any Other Home Win", "back": 44.0, "lay": 46.0},
        {"name": "Any Other Away Win", "back": 48.0, "lay": 50.0},
    ]
    blk = scanner.build_cs_block("1.23", "OPEN", sels)
    assert blk is not None
    assert blk["any_other_home"] == {"back": 44.0, "lay": 46.0, "back_size": None, "lay_size": None}
    assert blk["any_other_away"] == {"back": 48.0, "lay": 50.0, "back_size": None, "lay_size": None}
    assert blk["selections"] == []  # senza selection_id nessuna selezione completa
    assert scanner.build_cs_block(None, "OPEN", sels) is None


def test_build_cs_block_completo_per_omega():
    sels = [
        {"selection_id": 1, "name": "0 - 0", "back": 3.0, "lay": 3.1, "back_size": 50.0, "lay_size": 20.0, "runner_status": "ACTIVE"},
        {"selection_id": 2, "name": "3 - 0", "back": 90.0, "lay": 110.0, "back_size": 2.0, "lay_size": 7.5, "runner_status": "ACTIVE"},
        {"selection_id": 3, "name": "Any Other Home Win", "back": 44.0, "lay": 46.0, "back_size": 3.5, "lay_size": 12.0},
    ]
    blk = scanner.build_cs_block("1.23", "OPEN", sels, inplay=True, total_matched=1234.5)
    assert blk["inplay"] is True and blk["total_matched"] == 1234.5
    assert [s["selection_id"] for s in blk["selections"]] == [1, 2, 3]
    assert blk["selections"][1] == {"selection_id": 2, "name": "3 - 0", "runner_status": "ACTIVE",
                                    "back": 90.0, "lay": 110.0, "back_size": 2.0, "lay_size": 7.5}
    assert blk["any_other_home"] == {"back": 44.0, "lay": 46.0, "back_size": 3.5, "lay_size": 12.0}


class _Lvl:
    def __init__(self, price, size):
        self.price = price
        self.size = size


class _Ex:
    def __init__(self, atb, atl):
        self.available_to_back = atb
        self.available_to_lay = atl


def test_price_pair_con_size_abbinabili():
    ex = _Ex([_Lvl(1.28, 152.4), _Lvl(1.27, 900.0)], [_Lvl(1.3, 41.257)])
    assert scanner.price_pair(ex) == {"back": 1.28, "lay": 1.3, "back_size": 152.4, "lay_size": 41.26}
    empty = {"back": None, "lay": None, "back_size": None, "lay_size": None}
    assert scanner.price_pair(_Ex([], None)) == empty
    assert scanner.price_pair(None) == empty


def test_build_cs_block_porta_le_size():
    sels = [{"name": "Any Other Home Win", "back": 44.0, "lay": 46.0, "back_size": 3.5, "lay_size": 12.0}]
    blk = scanner.build_cs_block("1.23", "OPEN", sels)
    assert blk["any_other_home"] == {"back": 44.0, "lay": 46.0, "back_size": 3.5, "lay_size": 12.0}


def test_critical_signature_ignora_le_quote():
    base = {"inplay": True, "mo_status": "OPEN", "minute": 50, "score_home": 1, "score_away": 0,
            "red_home": 0, "red_away": 0, "odds": {"home": {"back": 1.3}}, "cs": {"status": "OPEN"}}
    solo_quote = {**base, "odds": {"home": {"back": 1.35}}}
    gol = {**base, "score_home": 2}
    cs_sospeso = {**base, "cs": {"status": "SUSPENDED"}}
    assert scanner.critical_signature("calcio", base) == scanner.critical_signature("calcio", solo_quote)
    assert scanner.critical_signature("calcio", base) != scanner.critical_signature("calcio", gol)
    assert scanner.critical_signature("calcio", base) != scanner.critical_signature("calcio", cs_sospeso)
    t = {"inplay": True, "mo_status": "OPEN", "sets": {"p1": 1, "p2": 0}, "games": {"p1": 3, "p2": 1}, "odds": {}}
    assert scanner.critical_signature("tennis", t) == scanner.critical_signature(
        "tennis", {**t, "odds": {"p1": {"back": 1.05}}}
    )
    assert scanner.critical_signature("tennis", t) != scanner.critical_signature(
        "tennis", {**t, "games": {"p1": 4, "p2": 1}}
    )


def test_media_flags_da_broadcasts_ips():
    bc = {"tv": [], "isLiveVideoAvailable": False, "isDataVisualizationAvailable": True, "channel": "WEB"}
    assert scanner.media_flags(bc) == {"video": False, "viz": True}
    assert scanner.media_flags({"isLiveVideoAvailable": "yes"}) == {"video": None, "viz": None}  # mai inventare
    assert scanner.media_flags(None) == {"video": None, "viz": None}
    assert scanner.media_flags({}) == {"video": None, "viz": None}


# ----------------------------------------------------------- sharding stream
def test_shard_index_stabile_e_indipendente_dal_processo():
    assert stream.shard_index("1.262210470", 4) == 262210470 % 4
    assert stream.shard_index("1.262210470", 1) == 0
    assert stream.shard_index("abc", 3) == 0  # nessuna cifra: shard 0, mai eccezione


def test_plan_shards_rispetta_il_cap_per_connessione():
    ids = [f"1.{100000 + i}" for i in range(500)]
    plan = stream.plan_shards(ids, max_conns=4, per_conn=180)
    assert len(plan) == 4
    assert all(len(b) <= 180 for b in plan)
    assert sum(len(b) for b in plan) == 500          # tutti coperti (capacità 720)
    assert len({m for b in plan for m in b}) == 500  # nessun duplicato


def test_plan_shards_pochi_mercati_una_sola_connessione():
    ids = [f"1.{100000 + i}" for i in range(50)]
    plan = stream.plan_shards(ids, max_conns=4, per_conn=180)
    assert [len(b) for b in plan] == [50, 0, 0, 0]


def test_plan_shards_oltre_capacita_tiene_le_priorita_alte():
    # 1000 mercati, capacità 2×180=360: ogni shard tiene i suoi primi 180 per
    # ordine di priorità (in-play prima); il resto va al fallback REST
    ids = [f"1.{100000 + i}" for i in range(1000)]
    plan = stream.plan_shards(ids, max_conns=2, per_conn=180)
    assert [len(b) for b in plan] == [180, 180]
    kept = {m for b in plan for m in b}
    assert all(m in kept for m in ids[:100])  # priorità massima: tutti dentro


def test_plan_shards_stabile_quando_si_aggiunge_un_mercato():
    ids = [f"1.{100000 + i}" for i in range(300)]
    before = stream.plan_shards(ids, max_conns=4, per_conn=180)
    after = stream.plan_shards(ids + ["1.999999"], max_conns=4, per_conn=180)
    # stesso numero di shard: nessun mercato cambia shard, UNO solo ricrea la subscription
    changed = sum(1 for a, b in zip(before, after) if set(a) != set(b))
    assert changed == 1


def test_strip_volatile_state_e_num_or_none():
    st = {"timeElapsed": 58, "timeElapsedSeconds": 3491, "score": {"home": {"score": "1"}}}
    out = scanner.strip_volatile_state(st)
    assert out == {"timeElapsed": 58, "score": {"home": {"score": "1"}}}
    assert st["timeElapsedSeconds"] == 3491  # copia, mai mutazione
    assert scanner.strip_volatile_state(None) is None
    assert scanner.num_or_none(3) == 3.0 and scanner.num_or_none("3") is None and scanner.num_or_none(None) is None


def test_critical_signature_include_lo_stato_ips_grezzo():
    base = {"inplay": True, "mo_status": "OPEN", "sets": {"p1": 1, "p2": 0}, "games": {"p1": 3, "p2": 1},
            "score_raw": {"score": {"home": {"score": "30"}}}}
    punto = {**base, "score_raw": {"score": {"home": {"score": "40"}}}}
    # un punto tennis (solo nel raw) è un cambio critico: pubblicazione immediata
    assert scanner.critical_signature("tennis", base) != scanner.critical_signature("tennis", punto)


def test_ht_candidate_e_firma_critica_ht():
    """Omega v2: HALF TIME SCORE sotto quote solo nel 1T (15'-44'); il suo stato
    mercato è critico (pubblicazione immediata) come quello del CS."""
    assert not scanner.is_ht_candidate(None) and not scanner.is_ht_candidate(14)
    assert scanner.is_ht_candidate(15) and scanner.is_ht_candidate(44)
    assert not scanner.is_ht_candidate(45) and not scanner.is_ht_candidate(60)
    base = {"inplay": True, "minute": 30, "ht": {"status": "OPEN"}}
    changed = {**base, "ht": {"status": "SUSPENDED"}}
    assert scanner.critical_signature("calcio", base) != scanner.critical_signature("calcio", changed)


# ------------------------------------------------- mercati OPPORTUNITA' (a gol)
def test_ou_line_from_market_type():
    assert scanner.ou_line_from_market_type("OVER_UNDER_25") == 2.5
    assert scanner.ou_line_from_market_type("OVER_UNDER_05") == 0.5
    assert scanner.ou_line_from_market_type("OVER_UNDER_75") == 7.5
    assert scanner.ou_line_from_market_type("BOTH_TEAMS_TO_SCORE") is None
    assert scanner.ou_line_from_market_type(None) is None
    # tutte le linee dichiarate sono parsabili
    assert [scanner.ou_line_from_market_type(t) for t in scanner.OU_MARKET_TYPES] == [
        0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5
    ]


def test_is_opp_candidate_solo_in_play():
    assert scanner.is_opp_candidate(True, 1) is True
    assert scanner.is_opp_candidate(True, 90) is True     # nessun tetto di minuto
    assert scanner.is_opp_candidate(True, 0) is False     # kickoff appena dato
    assert scanner.is_opp_candidate(False, 50) is False   # pre-match: nulla da dire
    assert scanner.is_opp_candidate(True, None) is False
    assert scanner.is_opp_candidate(None, 50) is False


def test_is_ht_result_candidate():
    assert scanner.is_ht_result_candidate(1) is True
    assert scanner.is_ht_result_candidate(44) is True
    assert scanner.is_ht_result_candidate(45) is False    # mercato ormai regolato
    assert scanner.is_ht_result_candidate(0) is False
    assert scanner.is_ht_result_candidate(None) is False


def test_linee_gia_decise_non_servono_piu():
    # 1-1 (2 gol): Under/Over 0.5 e 1.5 sono decisi, dal 2.5 in su no
    assert scanner.is_live_ou_line(0.5, 1, 1) is False
    assert scanner.is_live_ou_line(1.5, 1, 1) is False
    assert scanner.is_live_ou_line(2.5, 1, 1) is True
    assert scanner.is_live_ou_line(7.5, 3, 4) is True
    assert scanner.is_live_ou_line(7.5, 4, 4) is False
    assert scanner.is_live_ou_line(None, 1, 1) is False
    assert scanner.is_live_ou_line(2.5, None, 1) is False
    # Gol/NoGol: deciso appena segnano entrambe
    assert scanner.is_live_btts(0, 0) is True
    assert scanner.is_live_btts(3, 0) is True
    assert scanner.is_live_btts(1, 1) is False
    assert scanner.is_live_btts(None, 0) is False


def test_is_opp_market_live_per_tipo():
    live = scanner.is_opp_market_live
    assert live("OVER_UNDER_25", 2.5, 60, 1, 1) is True
    assert live("OVER_UNDER_15", 1.5, 60, 1, 1) is False
    assert live(scanner.BTTS_MARKET_TYPE, None, 60, 1, 0) is True
    assert live(scanner.BTTS_MARKET_TYPE, None, 60, 1, 1) is False
    assert live(scanner.HT_RESULT_MARKET_TYPE, None, 30, 0, 0) is True
    assert live(scanner.HT_RESULT_MARKET_TYPE, None, 50, 0, 0) is False
    assert live("CORRECT_SCORE", None, 30, 0, 0) is False   # non e' un mercato opp
    assert live(None, None, 30, 0, 0) is False


def test_opp_rank_key_sempre_dopo_i_mercati_core():
    """Il pool stream (cap 180/connessione) deve riempirsi prima coi mercati core:
    i mercati opportunità sono tier 2, e tra loro vince il minuto più avanzato."""
    core_inplay = scanner.rank_key(True, "2026-09-10T18:00:00+00:00")
    core_preko = scanner.rank_key(False, "2026-09-10T18:00:00+00:00")
    opp_80 = scanner.opp_rank_key(80, "2026-09-10T18:00:00+00:00")
    opp_20 = scanner.opp_rank_key(20, "2026-09-10T18:00:00+00:00")
    assert core_inplay < core_preko < opp_80 < opp_20
    assert scanner.opp_rank_key(None, None) > opp_20


def test_build_market_block_generico():
    sels = [
        {"selection_id": 901, "name": "Over 7.5", "runner_status": "ACTIVE",
         "back": 9.0, "lay": 12.0, "back_size": 15.0, "lay_size": 8.0},
        {"selection_id": 902, "name": "Under 7.5", "runner_status": "ACTIVE",
         "back": 1.1, "lay": 1.12, "back_size": 120.0, "lay_size": 90.0},
        {"name": "senza id", "back": 2.0},          # scartata: niente selection_id
    ]
    blk = scanner.build_market_block(
        "1.777", "OPEN", sels, inplay=True, total_matched=999.5,
        market_type="OVER_UNDER_75", line=7.5, ts_ms=1_700_000_000_000,
    )
    assert blk["market_id"] == "1.777" and blk["status"] == "OPEN"
    assert blk["inplay"] is True and blk["total_matched"] == 999.5
    assert blk["market_type"] == "OVER_UNDER_75" and blk["line"] == 7.5
    assert blk["ts_ms"] == 1_700_000_000_000
    assert [s["selection_id"] for s in blk["selections"]] == [901, 902]
    assert blk["selections"][1] == {
        "selection_id": 902, "name": "Under 7.5", "runner_status": "ACTIVE",
        "back": 1.1, "lay": 1.12, "back_size": 120.0, "lay_size": 90.0,
    }
    assert scanner.build_market_block(None, "OPEN", sels) is None
    # senza i campi opzionali il blocco resta quello storico del Correct Score
    nudo = scanner.build_market_block("1.23", "OPEN", sels)
    assert set(nudo) == {"market_id", "status", "inplay", "total_matched", "selections"}


def test_build_cs_block_resta_compatibile_col_builder_generico():
    """Il blocco `cs` letto da Omega non cambia forma: stesse chiavi di sempre."""
    sels = [{"selection_id": 1, "name": "0 - 0", "back": 3.0, "lay": 3.1,
             "back_size": 50.0, "lay_size": 20.0, "runner_status": "ACTIVE"},
            {"selection_id": 9, "name": "Any Other Home Win", "back": 44.0, "lay": 46.0,
             "back_size": 3.5, "lay_size": 12.0}]
    blk = scanner.build_cs_block("1.23", "OPEN", sels, inplay=True, total_matched=1.0)
    assert set(blk) == {"market_id", "status", "inplay", "total_matched",
                        "selections", "any_other_home", "any_other_away"}


def test_split_opportunity_blocks():
    blocks = {
        "1.3": {"market_id": "1.3", "market_type": "OVER_UNDER_25", "line": 2.5},
        "1.1": {"market_id": "1.1", "market_type": "OVER_UNDER_05", "line": 0.5},
        "1.9": {"market_id": "1.9", "market_type": "BOTH_TEAMS_TO_SCORE"},
        "1.8": {"market_id": "1.8", "market_type": "HALF_TIME"},
        "1.7": {"market_id": "1.7", "market_type": "CORRECT_SCORE"},   # ignorato
    }
    out = scanner.split_opportunity_blocks(blocks)
    assert [b["line"] for b in out["ou"]] == [0.5, 2.5]      # ordinati per linea
    assert out["btts"]["market_id"] == "1.9"
    assert out["ht_result"]["market_id"] == "1.8"
    vuoto = scanner.split_opportunity_blocks(None)
    assert vuoto == {"ou": None, "btts": None, "ht_result": None}


def test_critical_signature_copre_i_blocchi_opportunita():
    base = {"inplay": True, "mo_status": "OPEN", "minute": 60, "score_home": 1,
            "score_away": 1, "red_home": 0, "red_away": 0,
            "ou": [{"market_id": "1.7", "status": "OPEN", "selections": []}],
            "btts": {"market_id": "1.9", "status": "OPEN"},
            "ht_result": None}
    solo_quote = {**base, "ou": [{"market_id": "1.7", "status": "OPEN",
                                  "selections": [{"back": 1.1}]}]}
    sospeso = {**base, "ou": [{"market_id": "1.7", "status": "SUSPENDED", "selections": []}]}
    btts_giu = {**base, "btts": {"market_id": "1.9", "status": "CLOSED"}}
    sig = scanner.critical_signature
    assert sig("calcio", base) == sig("calcio", solo_quote)   # le quote aspettano
    assert sig("calcio", base) != sig("calcio", sospeso)      # lo stato no
    assert sig("calcio", base) != sig("calcio", btts_giu)


# ---------------------------------------------- integrazione scanner ↔ payload
class _Runner:
    def __init__(self, sid, back=None, lay=None, back_size=None, lay_size=None,
                 status="ACTIVE"):
        self.selection_id = sid
        self.status = status
        self.ex = _Ex(
            [_Lvl(back, back_size)] if back else [],
            [_Lvl(lay, lay_size)] if lay else [],
        )


class _Book:
    def __init__(self, market_id, runners, status="OPEN", inplay=True, total_matched=10.0):
        self.market_id = market_id
        self.runners = runners
        self.status = status
        self.inplay = inplay
        self.total_matched = total_matched


def _scanner_con_evento():
    from Betfair.safe_strategy import service

    scan = service.Scanner(api_client=object(), dry=True, use_stream=False)
    meta = {
        "event_id": "e1", "market_id": "1.100", "event_name": "Nord FC v Sud FC",
        "open_date": "2026-09-10T18:00:00+00:00", "competition": "Serie Z",
        "runners": [], "sides": {"home": 11, "away": 22, "draw": 33},
    }
    scan.sports["calcio"].metas = {"e1": meta}
    scan.events["e1"] = {
        "sport": "calcio", "inplay": True, "mo_status": "OPEN", "minute": 65,
        "score_home": 1, "score_away": 1, "red_home": 0, "red_away": 0,
        "pre_ko": {"home": 2.0, "draw": 3.4, "away": 4.0, "captured_at": "x"},
        "odds": {
            "home": {"back": 2.7, "lay": 2.74, "back_size": 300.0, "lay_size": 250.0},
            "draw": {"back": 2.1, "lay": 2.12, "back_size": 400.0, "lay_size": 300.0},
            "away": {"back": 6.4, "lay": 6.6, "back_size": 120.0, "lay_size": 90.0},
        },
    }
    scan.opp_markets["e1"] = {
        "1.777": {"market_id": "1.777", "market_type": "OVER_UNDER_75", "line": 7.5,
                  "names": {901: "Over 7.5", 902: "Under 7.5"}},
        "1.115": {"market_id": "1.115", "market_type": "OVER_UNDER_15", "line": 1.5,
                  "names": {801: "Over 1.5", 802: "Under 1.5"}},
        "1.900": {"market_id": "1.900", "market_type": "BOTH_TEAMS_TO_SCORE",
                  "line": None, "names": {1: "Yes", 2: "No"}},
    }
    scan._rebuild_market_index()
    return scan


def test_scanner_mercati_opportunita_nel_payload():
    """Il book di un mercato a gol finisce nei blocchi ADDITIVI ou/btts e le
    chiavi storiche del payload restano tutte al loro posto."""
    from datetime import datetime, timezone

    scan = _scanner_con_evento()
    scan.events["e1"].update(score_home=1, score_away=0)   # Gol/NoGol ancora vivo
    scan._apply_market_book(_Book("1.777", [
        _Runner(901, back=9.0, lay=12.0, back_size=15.0, lay_size=8.0),
        _Runner(902, back=1.10, lay=1.12, back_size=120.0, lay_size=90.0),
    ]))
    scan._apply_market_book(_Book("1.900", [
        _Runner(1, back=1.02, lay=1.04, back_size=500.0, lay_size=500.0),
        _Runner(2, back=40.0, lay=60.0, back_size=10.0, lay_size=5.0),
    ]))
    rows, wanted = scan.build_rows(datetime.now(timezone.utc))
    assert wanted == ["e1"] and len(rows) == 1
    payload = rows[0]["payload"]
    # chiavi storiche: nessuna persa (feed multi-consumer)
    for key in ("odds", "minute", "score_home", "score_away", "red_home", "red_away",
                "inplay", "pre_ko", "cs", "ht", "timeline", "score_raw", "mo_status"):
        assert key in payload
    # blocchi nuovi
    assert payload["btts"]["market_id"] == "1.900"
    assert [b["line"] for b in payload["ou"]] == [7.5]
    ou = payload["ou"][0]
    assert ou["market_type"] == "OVER_UNDER_75" and ou["status"] == "OPEN"
    assert ou["ts_ms"] > 0
    assert [s["name"] for s in ou["selections"]] == ["Over 7.5", "Under 7.5"]
    assert ou["selections"][1]["back"] == 1.10 and ou["selections"][1]["back_size"] == 120.0
    assert payload["ht_result"] is None          # dopo il 45' non serve
    assert payload["odds_ts_ms"] is None         # quote arrivate senza book MATCH_ODDS
    # la VALUTAZIONE non gira nel feed: la fa bot_service.py
    assert "opportunities" not in payload


def test_scanner_opportunita_in_linea_solo_col_flag(monkeypatch):
    """SAFE_SCAN_OPPORTUNITIES: spento di default (anche da variabile VUOTA),
    acceso solo per collaudo — allora la chiave compare col segnale reale."""
    from datetime import datetime, timezone

    from Betfair.safe_strategy import service

    for spento in ("", "   ", "0", "false", "no"):
        monkeypatch.setenv(service._OPPORTUNITIES_ENV, spento)
        assert service._opportunities_enabled() is False
    monkeypatch.delenv(service._OPPORTUNITIES_ENV, raising=False)
    assert service._opportunities_enabled() is False

    monkeypatch.setenv(service._OPPORTUNITIES_ENV, "1")
    assert service._opportunities_enabled() is True
    scan = _scanner_con_evento()
    scan._apply_market_book(_Book("1.777", [
        _Runner(901, back=9.0, lay=12.0, back_size=15.0, lay_size=8.0),
        _Runner(902, back=1.10, lay=1.12, back_size=120.0, lay_size=90.0),
    ]))
    rows, _ = scan.build_rows(datetime.now(timezone.utc))
    opps = rows[0]["payload"]["opportunities"]
    under = [o for o in opps if o["selection_name"] == "Under 7.5"]
    assert under and under[0]["side"] == "back" and under[0]["market_id"] == "1.777"
    assert all(o["rationale"].isascii() for o in opps)


def test_scanner_ts_ms_cambia_solo_al_cambio_prezzo():
    scan = _scanner_con_evento()
    book = _Book("1.777", [_Runner(902, back=1.10, lay=1.12, back_size=120.0, lay_size=90.0)])
    scan._apply_market_book(book)
    primo = scan.events["e1"]["opp"]["1.777"]["ts_ms"]
    scan._apply_market_book(book)                       # stesso book: ts fermo
    assert scan.events["e1"]["opp"]["1.777"]["ts_ms"] == primo
    scan._apply_market_book(_Book("1.777", [
        _Runner(902, back=1.11, lay=1.12, back_size=120.0, lay_size=90.0)]))
    assert scan.events["e1"]["opp"]["1.777"]["ts_ms"] >= primo
    assert scan.events["e1"]["opp"]["1.777"]["selections"][0]["back"] == 1.11


def test_scanner_priorita_e_linee_decise():
    """I mercati opportunità entrano DOPO i core e solo se la linea è indecisa."""
    from datetime import datetime, timezone

    scan = _scanner_con_evento()             # 1-1 al 65'
    ids = scan.relevant_market_ids("calcio", datetime.now(timezone.utc))
    assert ids[0] == "1.100"                 # MATCH_ODDS sempre per primo (tier 0)
    assert "1.777" in ids                    # Over/Under 7.5: ancora indeciso
    assert "1.115" not in ids                # Over/Under 1.5: 2 gol, deciso
    assert "1.900" not in ids                # Gol/NoGol: hanno segnato entrambe
    # sull'1-0 tornano utili sia la linea 1.5 sia il Gol/NoGol
    scan.events["e1"].update(score_home=1, score_away=0)
    ids = scan.relevant_market_ids("calcio", datetime.now(timezone.utc))
    assert {"1.115", "1.900", "1.777"} <= set(ids)
    assert ids.index("1.100") < ids.index("1.777")


def test_scanner_candidati_opportunita_con_tetto():
    from Betfair.safe_strategy import service

    scan = service.Scanner(api_client=object(), dry=True, use_stream=False)
    for i in range(scanner.OPP_MAX_EVENTS + 5):
        scan.events[f"e{i}"] = {"sport": "calcio", "inplay": True, "minute": i + 1,
                                "mo_status": "OPEN", "score_home": 0, "score_away": 0}
    scan.events["pre"] = {"sport": "calcio", "inplay": False, "minute": None}
    scan.events["chiuso"] = {"sport": "calcio", "inplay": True, "minute": 90,
                             "mo_status": "CLOSED"}
    scan.events["tennis"] = {"sport": "tennis", "inplay": True, "minute": 50}
    cands = scan.opp_candidates()
    assert len(cands) == scanner.OPP_MAX_EVENTS
    assert "pre" not in cands and "chiuso" not in cands and "tennis" not in cands
    # i posti vanno ai minuti più avanzati
    minuti = [scan.events[e]["minute"] for e in cands]
    assert minuti == sorted(minuti, reverse=True)


def test_scanner_write_on_change_non_dipende_dalle_opportunita(monkeypatch):
    """Le opportunità sono un DERIVATO (la confidenza dipende anche dall'orologio):
    anche accese in linea non devono entrare nella firma, o la riga si
    riscriverebbe a ogni tick."""
    from datetime import datetime, timezone

    from Betfair.safe_strategy import service

    monkeypatch.setenv(service._OPPORTUNITIES_ENV, "1")
    scan = _scanner_con_evento()
    scan._apply_market_book(_Book("1.777", [
        _Runner(902, back=1.10, lay=1.12, back_size=120.0, lay_size=90.0)]))
    now = datetime.now(timezone.utc)
    primo, _ = scan.build_rows(now)
    assert len(primo) == 1 and "opportunities" in primo[0]["payload"]
    secondo, _ = scan.build_rows(now)
    assert secondo == []                     # nulla e' cambiato: nessuna riscrittura
    # solo-quote: cambia la firma ma il throttle per-evento la fa aspettare
    scan._apply_market_book(_Book("1.777", [
        _Runner(902, back=1.12, lay=1.14, back_size=120.0, lay_size=90.0)]))
    assert scan.build_rows(now) == ([], ["e1"])
    # un GOL e' un cambio critico: pubblicazione immediata, throttle saltato
    scan.events["e1"].update(score_home=2, score_away=1)
    quarto, _ = scan.build_rows(now)
    assert len(quarto) == 1
    assert quarto[0]["payload"]["score_home"] == 2
