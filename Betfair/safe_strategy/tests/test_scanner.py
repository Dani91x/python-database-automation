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
    # REGOLA 09/09: il minuto è una SOGLIA ("dal 40' in poi"), mai un tetto
    assert scanner.is_cs_candidate(49, 1, 0) is True
    assert scanner.is_cs_candidate(39, 1, 0) is False    # troppo presto
    assert scanner.is_cs_candidate(61, 1, 0) is True     # nessun tetto di minuto
    assert scanner.is_cs_candidate(89, 0, 0) is True
    assert scanner.is_cs_candidate(49, 3, 0) is False    # troppi gol per lato
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
    assert scanner.build_cs_block(None, "OPEN", sels) is None


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
