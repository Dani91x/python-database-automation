# -*- coding: utf-8 -*-
"""CERTIFICAZIONE 13/09 — i difetti trovati nella verifica capillare contro il
manuale delle 4 strategie (STRATEGY S) e la separazione paper/live.

Ogni test qui sotto fissa UN difetto reale e dice quale. Non sono test di
regressione generici: sono la prova che quel difetto non puo' tornare.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from Betfair.safe_strategy import bot_db as DB
from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy import db as SCAN_DB
from Betfair.safe_strategy import engine as EN
from Betfair.safe_strategy import execution as X
from Betfair.safe_strategy import exits as XE
from Betfair.safe_strategy import scanner as SC
from Betfair.safe_strategy import service as SV

NOW = datetime(2026, 9, 13, 20, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# 1. pre_ko: la causa per cui BASE e PUNTA non scattavano mai
# ---------------------------------------------------------------------------
def test_pre_ko_utilizzabile_solo_se_la_tripla_e_completa_e_numerica():
    assert SCAN_DB.is_usable_pre_ko({"home": 1.6, "draw": 3.8, "away": 5.5})
    assert not SCAN_DB.is_usable_pre_ko(None)
    assert not SCAN_DB.is_usable_pre_ko({"home": 1.6, "draw": 3.8})
    assert not SCAN_DB.is_usable_pre_ko({"home": 1.6, "draw": 3.8, "away": None})
    assert not SCAN_DB.is_usable_pre_ko({"home": 1.6, "draw": 3.8, "away": "5.5"})
    assert not SCAN_DB.is_usable_pre_ko({"home": 1.0, "draw": 3.8, "away": 5.5})


class _ScanDbFinto:
    """Sostituto di ``safe_strategy.db`` per la reidratazione."""

    def __init__(self, salvati):
        self.salvati = salvati
        self.chiamate = []

    def load_scan_pre_ko(self, event_ids):
        # CONTRATTO (review 13/09): una chiave per OGNI evento interrogato, con
        # None quando il riferimento non c'e'. "cercato e non trovato" e' un
        # esito e non va confuso con "non ancora cercato": e' cosi' che il
        # chiamante sa quali ritentare dopo un timeout.
        self.chiamate.append(list(event_ids))
        return {e: self.salvati.get(e) for e in event_ids}


    @staticmethod
    def is_usable_pre_ko(pre):
        return SCAN_DB.is_usable_pre_ko(pre)


class _ScanDbCheEsplode(_ScanDbFinto):
    """Il DB va in timeout: nessun esito, quindi tutto da ritentare."""

    def load_scan_pre_ko(self, event_ids):
        self.chiamate.append(list(event_ids))
        raise RuntimeError("statement timeout")


def _scanner_con_eventi(eventi, monkeypatch, salvati):
    sc = SV.Scanner.__new__(SV.Scanner)          # niente rete: si costruisce a mano
    sc.dry = False
    sc.events = eventi
    sc.pre_ko_tried = set()
    finto = _ScanDbFinto(salvati)
    monkeypatch.setattr(SV, "scan_db", finto)
    return sc, finto


def test_pre_ko_si_recupera_dal_db_per_le_partite_gia_in_corso(monkeypatch):
    """IL difetto principale: ``pre_ko`` viveva solo nella RAM dello scanner.

    ``freeze_pre_ko`` lo cattura solo PRIMA del calcio d'inizio, quindi a ogni
    riavvio (app chiusa, crash + watchdog, modifica al codice) spariva per tutte
    le partite in corso, e BASE e PUNTA restavano n/d per il resto della
    giornata. Il dato era gia' salvato sul DB: adesso lo si rilegge.
    """
    pre = {"home": 1.65, "draw": 3.9, "away": 5.2, "captured_at": "x"}
    eventi = {"e1": {"sport": "calcio", "inplay": True, "pre_ko": None}}
    sc, finto = _scanner_con_eventi(eventi, monkeypatch, {"e1": pre})
    assert sc.hydrate_pre_ko() == 1
    assert eventi["e1"]["pre_ko"]["home"] == 1.65
    assert eventi["e1"]["pre_ko"]["rehydrated"] is True
    assert finto.chiamate == [["e1"]]


def test_pre_ko_un_solo_tentativo_per_evento(monkeypatch):
    """Se il riferimento non c'e' nemmeno sul DB non lo si ricerca a ogni giro."""
    eventi = {"e1": {"sport": "calcio", "inplay": True, "pre_ko": None}}
    sc, finto = _scanner_con_eventi(eventi, monkeypatch, {})
    assert sc.hydrate_pre_ko() == 0
    assert sc.hydrate_pre_ko() == 0
    assert len(finto.chiamate) == 1


def test_pre_ko_un_timeout_non_brucia_il_tentativo(monkeypatch):
    """CERT. 13/09 (review) — prima si marcava "gia' tentato" PRIMA della
    lettura: un solo timeout del DB (e il DB va in timeout spesso) bruciava il
    tentativo per TUTTE le partite in corso, per il resto della giornata. Cioe'
    il difetto che questa funzione esiste per chiudere si richiudeva da solo al
    primo intoppo.
    """
    eventi = {"e1": {"sport": "calcio", "inplay": True, "pre_ko": None}}
    sc, _ = _scanner_con_eventi(eventi, monkeypatch, {})
    rotto = _ScanDbCheEsplode({})
    monkeypatch.setattr(SV, "scan_db", rotto)
    assert sc.hydrate_pre_ko() == 0
    assert sc.hydrate_pre_ko() == 0
    assert len(rotto.chiamate) == 2, "dopo un timeout si DEVE ritentare"


def test_pre_ko_non_sovrascrive_quello_gia_congelato(monkeypatch):
    """Il riferimento catturato in diretta vale piu' di quello riletto."""
    vivo = {"home": 2.0, "draw": 3.2, "away": 3.9}
    eventi = {"e1": {"sport": "calcio", "inplay": True, "pre_ko": vivo}}
    sc, finto = _scanner_con_eventi(
        eventi, monkeypatch, {"e1": {"home": 9, "draw": 9, "away": 9}})
    assert sc.hydrate_pre_ko() == 0
    assert eventi["e1"]["pre_ko"] == vivo
    assert finto.chiamate == []


def test_pre_ko_in_dry_non_legge_nulla(monkeypatch):
    eventi = {"e1": {"sport": "calcio", "inplay": True, "pre_ko": None}}
    sc, finto = _scanner_con_eventi(
        eventi, monkeypatch, {"e1": {"home": 2, "draw": 3, "away": 4}})
    sc.dry = True
    assert sc.hydrate_pre_ko() == 0
    assert finto.chiamate == []


def test_motore_dichiara_le_partite_senza_riferimento_pre_ko():
    """Prima BASE e PUNTA finivano in stato "nd" e il candidato veniva scartato
    in SILENZIO: nessun segnale, nessuno scarto, niente a schermo.
    """
    motore = EN.SafeEngine()
    riga = {"event_id": "e1", "sport": "calcio", "updated_at": NOW.isoformat(),
            "payload": {"inplay": True, "minute": 60, "score_home": 1, "score_away": 0,
                        "home": "A", "away": "B", "mo_status": "OPEN",
                        "odds": {"home": {"back": 1.3, "lay": 1.32},
                                 "draw": {"back": 5.0, "lay": 5.2},
                                 "away": {"back": 9.0, "lay": 9.4}}}}
    motore.evaluate([riga])
    manca = motore.pre_match_missing_events()
    assert [m["event_id"] for m in manca] == ["e1"]
    assert manca[0]["minute"] == 60


# ---------------------------------------------------------------------------
# 2. Esecuzione: place-and-trim, minimi per lato, direzione del tick
# ---------------------------------------------------------------------------
def test_minimo_di_piazzamento_dipende_dal_lato(monkeypatch):
    """Il minimo .it e' BACK 2,00 e LAY 0,50.

    Tornando 2,00 anche per il lay, ogni LAY fra 0,50 e 2,00 finiva sulla
    macchina place-and-trim, che pero' parcheggia a 0,50 e SOLLEVA: gamba persa
    su un ordine che Betfair avrebbe accettato al primo colpo.
    """
    monkeypatch.delenv("SAFE_MIN_SIZE_LIVE", raising=False)
    assert X._min_size_live("back") == 2.0
    assert X._min_size_live("lay") == 0.50
    monkeypatch.setenv("SAFE_MIN_SIZE_LIVE", "1.25")
    assert X._min_size_live("back") == X._min_size_live("lay") == 1.25


def test_pavimento_assoluto_dell_exchange():
    assert X.ABS_MIN_SIZE == 0.01


def test_scostamento_in_tick_solo_sulle_uscite_urgenti():
    """Con il bet delay un FOK mandato esattamente al best trova un mercato gia'
    diverso e viene ucciso. Sulle uscite urgenti non uscire e' peggio che pagare
    un tick; sulle altre si ritenta e il prezzo conta.
    """
    for urgente in ("loss", "mandatory", "red_card"):
        assert X.ticks_for_exit(urgente) == 1
    for tranquilla in ("profit", "time", "greenup", "manual", None, ""):
        assert X.ticks_for_exit(tranquilla) == 0


def test_freno_live_globale(monkeypatch):
    """``LIVE_KILL_SWITCH`` e ``LIVE_ORDER_MODE`` fermavano solo il worker della
    coda: a gate flumine chiuso la Safe Strategy ripiegava sul REST e piazzava
    soldi veri anche con il sistema dichiarato in PAPER.
    """
    monkeypatch.setenv("LIVE_ORDER_MODE", "LIVE")
    monkeypatch.setenv("LIVE_KILL_SWITCH", "false")
    assert X._live_brake() is None
    monkeypatch.setenv("LIVE_KILL_SWITCH", "true")
    assert X._live_brake() == "live_kill_switch_attivo"
    monkeypatch.setenv("LIVE_KILL_SWITCH", "false")
    monkeypatch.setenv("LIVE_ORDER_MODE", "PAPER")
    assert X._live_brake() == "live_order_mode_non_live:PAPER"


def test_il_selection_id_viaggia_col_prezzo_nel_blocco_correct_score():
    """Prima il prezzo veniva da ``build_cs_block`` (vince l'ULTIMO nome che
    matcha) e la selezione da ``engine._any_other_selection_ids`` (vince il
    PRIMO): due passaggi indipendenti con precedenze opposte.
    """
    sels = [{"selection_id": 501, "name": "Any Other Home Win", "back": 44.0, "lay": 46.0},
            {"selection_id": 502, "name": "Any Other Away Win", "back": 48.0, "lay": 50.0}]
    blk = SC.build_cs_block("1.23", "OPEN", sels)
    assert blk["any_other_home"]["selection_id"] == 501
    assert blk["any_other_away"]["selection_id"] == 502
    pair = EN.scan_pair(blk["any_other_home"])
    assert pair.selection_id == 501 and pair.lay == 46.0


# ---------------------------------------------------------------------------
# 3. Separazione paper / live
# ---------------------------------------------------------------------------
def test_aggregati_filtrati_per_modalita():
    """P&L, KPI e cap di rischio non devono MAI sommare posizioni finte e vere.

    Una settimana di paper vincente gonfiava il P&L totale di un conto che non
    aveva guadagnato un euro, e una giornata paper negativa consumava il fermo
    per perdita del live.
    """
    righe = [
        {"id": 1, "event_id": "e1", "status": "won", "pnl": 10.0, "liability": 5.0,
         "mode": "paper", "placed_at": NOW.isoformat(), "settled_at": NOW.isoformat()},
        {"id": 2, "event_id": "e2", "status": "lost", "pnl": -4.0, "liability": 8.0,
         "mode": "live", "placed_at": NOW.isoformat(), "settled_at": NOW.isoformat()},
    ]
    solo_paper = DB.aggregate_rows(righe, mode="paper")
    solo_live = DB.aggregate_rows(righe, mode="live")
    tutto = DB.aggregate_rows(righe)
    assert solo_paper["realized_total"] == 10.0
    assert solo_live["realized_total"] == -4.0
    assert tutto["realized_total"] == 6.0


def test_riga_senza_modalita_conta_come_live():
    """Fail-safe: meglio contarla fra i soldi veri che nasconderla fra i finti."""
    assert DB.row_mode({}) == "live"
    assert DB.row_mode({"mode": "PAPER"}) == "paper"
    assert DB.row_mode({"mode": "boh"}) == "live"


def test_eta_della_richiesta():
    vecchia = {"created_at": (NOW - timedelta(seconds=300)).isoformat()}
    assert S._request_age_s(vecchia, NOW) == pytest.approx(300.0, abs=1.0)
    assert S._request_age_s({}, NOW) is None


def test_ogni_riga_di_attivita_nasce_etichettata():
    """Solo 4 dei ~63 punti di log portavano la modalita': a posteriori era
    impossibile dire se un blocco di rischio riguardasse soldi veri o finti.
    """
    scritte = []

    class _Db:
        @staticmethod
        def log(kind, payload):
            scritte.append((kind, payload))

    S.set_log_mode("live")
    try:
        S._log(_Db(), "skip", {"reason": "x"})
        S._log(_Db(), "place", {"reason": "y", "mode": "paper"})
    finally:
        S.set_log_mode("")
    assert scritte[0][1]["mode"] == "live"
    assert scritte[1][1]["mode"] == "paper"


# ---------------------------------------------------------------------------
# 4. Guardie del ciclo e delle uscite
# ---------------------------------------------------------------------------
def test_aggregati_illeggibili_bloccano_i_nuovi_ingressi():
    """Prima si proseguiva con aggregati vuoti: il fermo per perdita si
    DISATTIVAVA e i cap giornalieri ripartivano da zero, in silenzio, proprio
    mentre il DB era in difficolta'.
    """

    class _Db:
        @staticmethod
        def open_trades(mode=None):
            return []

        @staticmethod
        def aggregates(mode=None):
            raise RuntimeError("statement timeout")

        @staticmethod
        def log(kind, payload):
            pass

    ctx = S.build_risk_ctx(_Db(), NOW, {}, mode="live")
    assert ctx["unavailable"] is True


def test_un_solo_lato_altro_risultato_per_partita():
    """Il motore valuta ESATTO su entrambi i lati e a 0-0/1-0/1-1 passano tutti
    e due: si bancava DUE volte lo stesso Correct Score.
    """
    ctx = {"open": [{"event_id": "1.1", "strategy": "esatto"}]}
    assert S._esatto_gia_su_evento(ctx, "1.1") is True
    assert S._esatto_gia_su_evento(ctx, "1.2") is False
    altro = {"open": [{"event_id": "1.1", "strategy": "base"}]}
    assert S._esatto_gia_su_evento(altro, "1.1") is False


def test_rossi_al_piazzamento_dal_feed():
    """La base dei cartellini deve essere quella dell'INGRESSO: se il feed li
    pubblica dopo, un rosso preso nel frattempo entrava nella base e la regola
    "rosso alla favorita esci" non scattava mai.
    """
    riga = {"payload": {"red_home": 1, "red_away": 0}}
    assert S._rossi_al_piazzamento(riga) == {"red_home": 1, "red_away": 0}
    assert S._rossi_al_piazzamento({"payload": {"red_home": None, "red_away": 0}}) == {}
    assert S._rossi_al_piazzamento({"payload": {}}) == {}
    assert S._rossi_al_piazzamento(None) == {}


def test_cecita_parziale_riconosciuta():
    """La riga c'e' ma il dato per decidere no: nessuna regola di uscita girava
    e non compariva nemmeno un log.
    """
    calcio = {"sport": "calcio"}
    assert S._dato_che_manca(calcio, {"score_home": 1, "score_away": 0, "minute": 60}) is None
    assert S._dato_che_manca(calcio, {"minute": 60}) == "punteggio_assente"
    assert S._dato_che_manca(calcio, {"score_home": 1, "score_away": 0}) == "minuto_assente"
    assert S._dato_che_manca(calcio, None) == "riga_senza_payload"
    tennis = {"sport": "tennis"}
    assert S._dato_che_manca(tennis, {"sets": {}, "games": {}}) is None
    assert S._dato_che_manca(tennis, {"sets": {}}) == "punteggio_tennis_assente"


def test_riserva_paper_mai_piazzata_non_e_una_posizione():
    """``phase='reserved'`` senza segni di esecuzione = processo morto fra
    l'insert e il place. Confermarla inventava una posizione paper.
    """
    assert S._riserva_mai_piazzata({"meta": {"phase": "reserved"}}) is True
    mezzo = {"meta": {"phase": "reserved", "fill": "paper_fill:x"}}
    assert S._riserva_mai_piazzata(mezzo) is False
    assert S._riserva_mai_piazzata({"meta": {"phase": "reserved"}, "bet_id": "b1"}) is False
    assert S._riserva_mai_piazzata({"meta": {}}) is False


def test_correlazione_della_combo_sul_mercato_vero():
    """Con l'etichetta COMBO nessuna posizione risultava correlata: tutte
    pesavano il 70% e il cap per evento veniva superato.
    """
    legs = [{"side": "lay", "price": 40.0, "market_type": "CORRECT_SCORE"},
            {"side": "back", "price": 3.0, "market_type": "OVER_UNDER_25"}]
    assert S._combo_market_type(legs, [2.0, 5.0]) == "CORRECT_SCORE"
    assert S._combo_market_type([], []) == "COMBO"


def test_tennis_uscita_obbligatoria_anche_se_la_parita_viene_superata():
    """``games_level`` era l'uguaglianza ESATTA nell'istante osservato: se il
    feed passava da 5-4 a 5-6 senza mostrare il 5-5, l'uscita obbligatoria non
    scattava PIU' per tutto il set, e con i default non esiste nessun'altra
    regola di perdita per la strategia tennis.
    """
    base = {"entry_sets": [1, 0], "last_games": [5, 6], "consecutive_lost": 2}
    # 5-3 -> 5-4 -> 5-6: il 5-5 non e' mai comparso, ma il vantaggio nel set
    # c'era (max 2) e adesso non c'e' piu' -> uscita obbligatoria
    superata = {**base, "games_level": False, "set_lead_lost": True}
    assert XE._decide_tennis(superata, {}).kind == "mandatory"
    # ancora in vantaggio: nessun obbligo, anche con due game persi di fila
    avanti = {**base, "last_games": [5, 3], "games_level": False,
              "set_lead_lost": False}
    deciso = XE._decide_tennis(avanti, {})
    assert deciso is None or deciso.kind != "mandatory"
    # tracciamenti vecchi senza il campo: si ripiega sulla parita' esatta
    vecchio = {**base, "games_level": True}
    assert XE._decide_tennis(vecchio, {}).kind == "mandatory"


def test_tennis_a_inizio_set_perdere_due_game_NON_e_uscita_obbligatoria():
    """Correzione della correzione (review 13/09).

    La prima versione usava "parita' o peggio", e a inizio set il leader e'
    0-0: perdendo i primi due game sarebbe uscito d'obbligo a 0-2, dove il
    manuale non chiede niente. Sarebbe stato un CAMBIO DI REGOLA in una
    certificazione che dichiara di non cambiare le strategie. Costo misurato
    del falso obbligo: back 100 EUR @1,03 con quota risalita a 1,12 -> circa
    -8 EUR bloccati, dove prima il bot teneva.
    """
    tr = {"side": "p1", "entry_sets": [1, 0], "entry_games": [0, 0]}
    # set nuovo, 0-0 -> 0-1 -> 0-2: mai in vantaggio in questo set
    XE._track_tennis(tr, {}, {"sets": {"p1": 1, "p2": 0}, "games": {"p1": 0, "p2": 0}}, 0.0)
    XE._track_tennis(tr, {}, {"sets": {"p1": 1, "p2": 0}, "games": {"p1": 0, "p2": 1}}, 1.0)
    XE._track_tennis(tr, {}, {"sets": {"p1": 1, "p2": 0}, "games": {"p1": 0, "p2": 2}}, 2.0)
    assert tr["consecutive_lost"] == 2
    assert tr["set_lead_lost"] is False, "non ha mai avuto un vantaggio in questo set"
    deciso = XE._decide_tennis(tr, {})
    assert deciso is None or deciso.kind != "mandatory"


def test_tennis_vantaggio_nel_set_perso_senza_mai_vedere_la_parita():
    """Il caso che la correzione esiste per coprire: 5-3 -> 5-4 -> 5-6."""
    tr = {"side": "p1", "entry_sets": [1, 0], "entry_games": [5, 3]}
    for g2 in (3, 4, 6):
        XE._track_tennis(tr, {},
                         {"sets": {"p1": 1, "p2": 0}, "games": {"p1": 5, "p2": g2}}, float(g2))
    assert tr["games_level"] is False, "il 5-5 non e' mai comparso nel feed"
    assert tr["set_lead_lost"] is True
    assert tr["consecutive_lost"] >= 2
    assert XE._decide_tennis(tr, {}).kind == "mandatory"


def test_tennis_una_sola_stima_di_probabilita():
    """Le uscite usavano una funzione col prior di hold GONFIATO (0,792 invece
    di 0,75) e senza rischio di ritiro, mentre il motore opportunita' usava
    quella corretta: la stessa posizione risultava dentro o fuori dal tetto di
    rischio a seconda di chi la guardava.
    """
    payload = {"sets": {"p1": 1, "p2": 0}, "games": {"p1": 4, "p2": 2},
               "competition": "ATP Test"}
    from Betfair.safe_strategy.tennis_opportunity import TennisOpportunityModel
    atteso = TennisOpportunityModel().p_win(payload, "p1")
    assert S._p_tennis(payload, "p1") == pytest.approx(round(atteso, 4), abs=1e-4)


def test_la_riserva_conta_subito_nel_contesto_del_ciclo():
    """La guardia "un solo lato ESATTO per partita" si appoggia a
    ``risk_ctx['open']``: se quella lista non venisse aggiornata dopo la
    riserva, due segnali dello STESSO ciclo passerebbero entrambi e la guardia
    non servirebbe a niente.
    """
    ctx = {"open": []}
    assert S._esatto_gia_su_evento(ctx, "1.1") is False
    S._risk_commit(ctx, {"id": 1, "event_id": "1.1", "strategy": "esatto",
                         "liability": 60.0})
    assert S._esatto_gia_su_evento(ctx, "1.1") is True


# ---------------------------------------------------------------------------
# 5. Correzioni della REVIEW AVVERSARIALE (13/09 sera)
# ---------------------------------------------------------------------------
def test_la_protezione_vede_TUTTE_le_modalita():
    """La regressione piu' grave della prima tornata.

    Filtrando ``open_trades`` per modalita' e passando quella lista a
    ``process_exits``, una posizione LIVE aperta smetteva di essere gestita
    appena il servizio tornava in PAPER (e ``safe_stop`` lo fa apposta): niente
    uscita in perdita, niente uscita obbligatoria, niente rosso. Arrivava al
    settlement con la responsabilita' intera. Il contesto ora porta DUE liste:
    ``open`` (filtrata, per i cap) e ``open_all`` (tutte, per la protezione).
    """
    vive = [{"id": 1, "event_id": "e1", "mode": "live", "strategy": "esatto"},
            {"id": 2, "event_id": "e2", "mode": "paper", "strategy": "base"}]

    class _Db:
        @staticmethod
        def open_trades(mode=None):
            assert mode is None, "la protezione non deve filtrare per modalita'"
            return list(vive)

        @staticmethod
        def list_trades(_status):
            return []

        @staticmethod
        def aggregates(mode=None):
            return {"realized_today": 0.0, "day_liability": 0.0}

        @staticmethod
        def log(kind, payload):
            pass

    ctx = S.build_risk_ctx(_Db(), NOW, {}, mode="paper")
    assert [t["id"] for t in ctx["open"]] == [2], "i CAP contano solo la modalita' attiva"
    assert [t["id"] for t in ctx["open_all"]] == [1, 2], "la PROTEZIONE le vede tutte"


def test_il_freno_live_non_blocca_le_chiusure(monkeypatch):
    """Bloccare anche le uscite sarebbe l'opposto della protezione: la posizione
    resterebbe a sanguinare senza via di fuga, e dopo i tentativi previsti il
    bot smetterebbe pure di provarci. E' la stessa regola che il worker della
    coda applica da sempre: il kill-switch ferma le aperture, non le uscite.
    """
    monkeypatch.setenv("LIVE_ORDER_MODE", "PAPER")
    chiamate = []

    class _Market:
        @staticmethod
        def place_order_live(**kw):
            chiamate.append(kw)
            return type("R", (), {"ok": True, "size_matched": 2.0,
                                  "avg_price_matched": 3.0, "bet_id": "b1",
                                  "order_status": "EXECUTION_COMPLETE"})()

    comune = dict(db=None, market=_Market(), mode="live", event_id="e1",
                  market_id="m1", selection_id=7, side="back", price=3.0, size=2.0,
                  best_size=100.0, ladder=(), client_ref="safe-t1", trade_id=1,
                  now=NOW, params={})
    apertura = X.place(**comune, meta={})
    assert apertura.status == "error" and "live_order_mode_non_live" in (apertura.fill_note or "")
    assert chiamate == [], "un'APERTURA non deve partire col freno tirato"
    chiusura = X.place(**comune, meta={"cashout": True, "closes_trade_id": 9})
    assert chiusura.status == "open", "una CHIUSURA deve sempre poter partire"
    assert len(chiamate) == 1


def test_prezzi_del_piano_gia_su_tick_valido():
    """La size del piano e' ``diff/prezzo``: se lo snap al tick sposta il prezzo
    DOPO il calcolo, la copertura non pareggia piu'. Snappando prima, prezzo e
    size restano coerenti per costruzione."""
    # 51 non e' un tick valido: banda 50-100, passo 5
    assert X._su_tick(51.0, "lay") == 55.0
    assert X._su_tick(51.0, "back") == 50.0
    # su un tick gia' valido sono no-op esatti (il caso normale: viene dal book)
    for p in (1.01, 1.03, 1.28, 3.05, 8.4, 32.0, 46.0, 65.0, 100.0):
        assert X._su_tick(p, "lay") == p
        assert X._su_tick(p, "back") == p
    assert X._su_tick(None, "lay") is None
    assert X._su_tick(0.5, "lay") is None


def test_le_partite_di_mike_si_tagliano_dalle_meno_esposte():
    """Il tetto ``MIKE_MAX_FOLLOWED`` seguiva l'ordine dei candidati dello
    scanner — "minuti piu' avanzati per primi" — quindi tagliava le partite
    APPENA INIZIATE, cioe' quelle dove la copertura Over 4.5 serve di piu'.
    Ora l'ordine e' quello di ``followed`` (soldi a rischio decrescente): chi
    resta senza quote e' chi ha meno denaro sopra.
    """
    candidati = ["APPENA_INIZIATA", "AVANZATA_1", "AVANZATA_2"]
    seguite = ["APPENA_INIZIATA", "AVANZATA_1", "AVANZATA_2"]   # esposizione decrescente
    tenute = SC.select_opp_candidates(candidati, followed=seguite,
                                      max_events=0, max_followed=2)
    assert tenute[:2] == ["APPENA_INIZIATA", "AVANZATA_1"]
    assert "AVANZATA_2" not in tenute


def test_esposizione_di_mike_ordina_per_denaro_reale():
    grossa = {"positions": [{"status": "open", "liability": 120.0}]}
    piccola = {"positions": [{"status": "open", "liability": 8.0}]}
    archiviata = {"positions": [{"status": "open", "liability": 999.0, "archived": True}]}
    assert SCAN_DB._mike_exposure(grossa) == 120.0
    assert SCAN_DB._mike_exposure(piccola) == 8.0
    assert SCAN_DB._mike_exposure(archiviata) == 0.0
    assert SCAN_DB._mike_exposure({"positions": []}) == 0.0


def test_aggregati_stantii_si_riusano_per_poco_invece_di_bloccare(monkeypatch):
    """Con il DB che va in timeout, bloccare a ogni ciclo avrebbe fermato il bot
    quasi sempre e inondato lo stesso DB di righe critiche. Entro un TTL breve
    si riusano gli ultimi numeri buoni: possono solo SOTTOSTIMARE la
    responsabilita' del giorno, e le riserve del ciclo la ricompongono."""
    S._AGG_ULTIMO_BUONO.clear()
    stato = {"rompi": False}

    class _Db:
        @staticmethod
        def open_trades(mode=None):
            return []

        @staticmethod
        def list_trades(_s):
            return []

        @staticmethod
        def aggregates(mode=None):
            if stato["rompi"]:
                raise RuntimeError("statement timeout")
            return {"realized_today": -12.0, "day_liability": 300.0}

        @staticmethod
        def log(kind, payload):
            pass

    buono = S.build_risk_ctx(_Db(), NOW, {}, mode="live")
    assert buono.get("unavailable") is not True
    stato["rompi"] = True
    subito = S.build_risk_ctx(_Db(), NOW, {}, mode="live")
    assert subito.get("unavailable") is not True
    assert subito["realized_today"] == -12.0 and subito["agg_stantio"] is True
    # oltre il TTL si blocca davvero
    tardi = S.build_risk_ctx(_Db(), NOW + timedelta(seconds=S._AGG_TTL_S + 5), {}, mode="live")
    assert tardi["unavailable"] is True


# ---------------------------------------------------------------------------
# 6. Feed: battito, peso delle scritture, prezzi morti (diagnosi condivisa 13/09)
# ---------------------------------------------------------------------------
def test_il_contatore_di_scambiato_non_riscrive_la_riga():
    """``total_matched`` si muove a OGNI scambio e non e' un gate per nessuno
    (Mike lo dichiara "diagnostica"; Safe/Omega/frontend lo mostrano e basta).
    Tenendolo nella firma, una partita molto scambiata riscriveva ~12 KB di
    JSONB ogni pochi secondi: la tabella e' TOASTata e pubblicata su realtime,
    quindi ogni UPDATE costa heap + TOAST + indice + WAL + decodifica logica.
    Il valore resta NEL payload, esce solo dalla FIRMA.
    """
    base = {"minute": 55, "total_matched": 1000.0,
            "cs": {"status": "OPEN", "total_matched": 50.0}}
    solo_scambiato = {"minute": 55, "total_matched": 999999.0,
                      "cs": {"status": "OPEN", "total_matched": 77777.0}}
    assert SC.payload_signature(base) == SC.payload_signature(solo_scambiato)
    # un cambio VERO continua a riscrivere
    col_gol = {**base, "minute": 56}
    assert SC.payload_signature(base) != SC.payload_signature(col_gol)


def test_il_momento_dell_ultima_osservazione_non_riscrive_la_riga():
    """``seen_ms`` serve a distinguere "prezzo fermo" da "mercato non piu'
    osservato" — senza, un blocco uscito dal feed resta in cache col prezzo
    VECCHIO e ci si puo' coprire o uscire sopra. Sta nel payload, ma nella
    firma riscriverebbe la riga a ogni poll."""
    a = {"ou": [{"line": 3.5, "ts_ms": 1000, "seen_ms": 1000}]}
    b = {"ou": [{"line": 3.5, "ts_ms": 1000, "seen_ms": 99999}]}
    assert SC.payload_signature(a) == SC.payload_signature(b)
    mosso = {"ou": [{"line": 3.5, "ts_ms": 5000, "seen_ms": 1000}]}
    assert SC.payload_signature(a) != SC.payload_signature(mosso)


# ---------------------------------------------------------------------------
# 7. TENNIS: il take profit non ha senso a QUALSIASI quota (decisione 14/09)
# ---------------------------------------------------------------------------
def _tr_tennis(**kw):
    base = {"side": "p1", "entry_sets": [1, 0], "entry_games": [2, 0],
            "last_games": [3, 0], "last_game": "won", "consecutive_lost": 0,
            "set_lead_lost": False}
    base.update(kw)
    return base


def test_sotto_la_soglia_di_quota_il_take_profit_non_scatta():
    """Misurato su operazioni reali: a 1,01-1,02 il profitto massimo (2-4
    centesimi su 2 EUR) e' piu' piccolo dello spread che si paga per uscire,
    quindi chiudere e' una perdita GARANTITA. Su 17 uscite osservate a quelle
    quote, TUTTE E 17 sarebbero state migliori tenute e nessuna avrebbe perso.
    Sotto la soglia si porta a termine.
    """
    par = dict(XE.DEFAULT_EXIT_PARAMS)
    assert par["tennis_take_profit_min_odds"] == 1.03
    for q in (1.01, 1.02):
        assert XE._decide_tennis(_tr_tennis(entry_price=q), par) is None, q
    for q in (1.03, 1.05, 1.10):
        d = XE._decide_tennis(_tr_tennis(entry_price=q), par)
        assert d is not None and d.kind == "profit", q


def test_lo_stop_loss_resta_attivo_anche_sotto_la_soglia():
    """La soglia di quota tocca SOLO l'incasso volontario. L'uscita obbligatoria
    (due game persi di fila + vantaggio perso nel set) non e' condizionata a
    niente: e' lo stop loss e deve poter scattare sempre."""
    par = dict(XE.DEFAULT_EXIT_PARAMS)
    tr = _tr_tennis(entry_price=1.01, consecutive_lost=2, set_lead_lost=True,
                    last_game="lost")
    d = XE._decide_tennis(tr, par)
    assert d is not None and d.kind == "mandatory"


def test_la_quota_di_ingresso_finisce_nel_tracciamento():
    """Senza la quota d'ingresso la regola non sarebbe applicabile."""
    tr = {}
    trade = {"price": 1.02, "score_at_entry": "set 1-0 · game 2-0"}
    XE._track_tennis(tr, trade, {"sets": {"p1": 1, "p2": 0}, "games": {"p1": 2, "p2": 0}}, 0.0)
    assert tr.get("entry_price") == 1.02


def test_la_soglia_e_configurabile_e_clampata():
    par = XE.merge_exit_params({"tennis_take_profit_min_odds": 1.20,
                                "tennis_take_profit_min_eur": 0.50})
    assert par["tennis_take_profit_min_odds"] == 1.20
    assert par["tennis_take_profit_min_eur"] == 0.50
    assert XE._decide_tennis(_tr_tennis(entry_price=1.10), par) is None
    # valori assurdi non passano
    assert XE.merge_exit_params({"tennis_take_profit_min_odds": 99})["tennis_take_profit_min_odds"] == 2.0
    assert XE.merge_exit_params({"tennis_take_profit_min_eur": -5})["tennis_take_profit_min_eur"] == 0.0


def _gate_tennis(best_lay, minimo=0.01):
    """Chiama ``_model_gate`` su un incasso tennis, con le sole finte necessarie."""
    trade = {"id": 1, "strategy": "tennis", "side": "back", "size": 2.0, "price": 1.05,
             "selection_id": 7, "market_id": "m1", "mode": "paper", "commission": 0.05,
             "event_id": "e1", "meta": {}}

    class _Db:
        @staticmethod
        def closing_trades_for(_ids):
            return []

        @staticmethod
        def log(kind, payload):
            pass

        @staticmethod
        def update_trade(*a, **k):
            pass

    xp = XE.merge_exit_params({"tennis_take_profit_min_eur": minimo})
    return S._model_gate(
        db=_Db(), trade=trade, meta={},
        decision=XE.ExitDecision("profit", "leader_vince_il_game", 0.0),
        prices={"back": 1.04, "lay": best_lay}, payload={},
        params={"commission_pct": 5.0}, xp=xp, now=NOW, opp_mod=None, opps_state=None)


def test_incasso_tennis_rifiutato_se_non_blocca_un_profitto():
    """Decisione dell'utente, 14/09: "il take profit deve garantire un profitto".

    La decisione a modello confronta VALORI ATTESI, quindi poteva accettare una
    chiusura con il P&L bloccato NEGATIVO se l'alternativa sembrava peggio. Su
    un incasso VOLONTARIO non ha senso: un «take profit» che porta a casa una
    perdita non e' un take profit.
    """
    # back 2,00 @1.05 chiuso a lay 1.10: si bloccherebbe una PERDITA -> si tiene
    tenere, info = _gate_tennis(best_lay=1.10)
    assert tenere is True, "un incasso in perdita non deve essere accettato"
    assert "incasso rifiutato" in str(info.get("why"))
    assert float(info["locked"]) < 0

    # stesso trade chiuso a lay 1.02: profitto vero -> si incassa
    tenere, info = _gate_tennis(best_lay=1.02)
    assert tenere is False, "un profitto vero va incassato"
    assert float(info["locked"]) > 0


def test_la_soglia_di_profitto_minimo_e_rispettata():
    """Con una soglia alta, un profitto piccolo non basta a giustificare
    l'uscita: si continua."""
    tenere, info = _gate_tennis(best_lay=1.02, minimo=5.00)
    assert tenere is True
    assert "almeno" in str(info.get("why"))


def test_lo_stop_loss_non_passa_MAI_dal_gate_del_profitto():
    """Invariante: le uscite in perdita e quelle obbligatorie non sono in
    ``PROFIT_KINDS``, quindi nessuna condizione di profitto puo' trattenerle."""
    for kind in ("loss", "mandatory", "red_card"):
        assert kind not in XE.PROFIT_KINDS
