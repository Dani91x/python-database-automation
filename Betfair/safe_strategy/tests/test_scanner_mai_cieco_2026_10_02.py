"""SCANNER MAI CIECO (02/10/2026) - punti 27, 28, 29 dell'elenco dell'utente.

Ordini dell'utente: "TUTTI I BOT NON DEVONO ESSERE MAI CIECHI PER NESSUN
MOTIVO, a meno che non dipenda da Betfair"; "lo scanner deve sapere le
posizioni di tutti i bot; SOLO QUANDO I MERCATI SONO CLOSED [...] possiamo
liberare lo scanner".

27. Esposizioni di TUTTI i bot (Omega, Safe, specchio ordini/posizioni calcio e
    tennis: scalper, sniper, bot tennis, manuali), paper e live, note allo
    scanner: una partita esposta non esce mai prima del CLOSED; il tetto di 3 h
    vale solo per chi non ha esposizione.
28. Mercati esposti (CS, HT, O/U, BTTS, 1X2 1T) mai esclusi dai tetti di
    candidatura ne' dal pool: tier -1; a tetto pieno escono solo i non esposti.
29. Catalogo con tetto 1000: gli eventi esposti entrano SEMPRE (chiamata
    mirata), CRITICAL se non si puo', WARNING col conteggio per il troncamento.

Finti con le stesse chiavi e gli stessi tipi del vero: righe Supabase come le
restituisce postgrest (dict con le colonne delle migrazioni), oggetti
betfairlightweight (``market_id``, ``event.id``, ``description.market_type``,
``runners[].selection_id``), filtri di ``betfairlightweight.filters``
(camelCase: ``eventIds``, ``marketIds``). File ASCII-only.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from Betfair.safe_strategy import db as SDB
from Betfair.safe_strategy import scanner
from Betfair.safe_strategy import service as S
from Betfair.safe_strategy import stream as STREAM

# la funzione VERA, presa prima che il conftest la sostituisca per ogni test
LIST_BOT_EXPOSURES_VERA = SDB.list_bot_exposures

NOW = datetime.now(timezone.utc)
TETTO = timedelta(seconds=scanner.POST_KO_WAIT_SEC)


def iso(dt):
    return dt.isoformat()


# =============================================================== finti
class _Query:
    """Catena postgrest: table().select().in_()/gte()/eq().execute()."""

    def __init__(self, sb, tabella):
        self.sb, self.tabella, self.filtri = sb, tabella, []

    def select(self, colonne):
        self.filtri.append(("select", colonne))
        return self

    def in_(self, col, valori):
        self.filtri.append(("in", col, tuple(valori)))
        return self

    def gte(self, col, valore):
        self.filtri.append(("gte", col, valore))
        return self

    def execute(self):
        self.sb.query.append((self.tabella, list(self.filtri)))
        esito = self.sb.righe.get(self.tabella, [])
        if isinstance(esito, Exception):
            raise esito
        righe = esito
        for f in self.filtri:
            if f[0] == "in":
                righe = [r for r in righe if r.get(f[1]) in f[2]]
        return SimpleNamespace(data=[dict(r) for r in righe])


class _Sb:
    def __init__(self, righe):
        self.righe = righe
        self.query: list = []

    def table(self, nome):
        return _Query(self, nome)


def _fonti(**righe_per_fonte):
    """Risultato con la forma ESATTA di ``db.list_bot_exposures``."""
    base = {k: [] for k in ("omega", "safe", "ordini_calcio", "posizioni_calcio",
                            "ordini_tennis", "posizioni_tennis")}
    base.update(righe_per_fonte)
    return base


def _esp(eid, mid, bot, sport="calcio"):
    return {"event_id": eid, "market_id": mid, "sport": sport, "bot": bot}


def _meta(eid, mid, ko_dt, nome="A v B"):
    return {"event_id": eid, "market_id": mid, "event_name": nome, "open_date": iso(ko_dt),
            "competition": "Serie A", "runners": [], "sides": {"home": 1, "away": 2, "draw": 3}}


def _scan(dry=True, client=None):
    scan = S.Scanner(client, dry=dry, use_stream=False)
    scan.pre_ko_ou_hours = 0.0
    scan.sports["calcio"].catalogue_ts = 1.0
    scan.sports["tennis"].catalogue_ts = 1.0
    return scan


def _book(market_id, status="OPEN", inplay=True, sel=(1, 2)):
    ex = SimpleNamespace(available_to_back=[SimpleNamespace(price=2.0, size=10.0)],
                         available_to_lay=[SimpleNamespace(price=2.02, size=10.0)])
    return SimpleNamespace(market_id=market_id, status=status, inplay=inplay, bet_delay=5,
                           total_matched=100.0,
                           runners=[SimpleNamespace(selection_id=s, status="ACTIVE", ex=ex)
                                    for s in sel])


# =============================================================== 27: fonte DB
def test_db_list_bot_exposures_legge_tutte_le_fonti_paper_e_live(monkeypatch):
    sb = _Sb({
        "omega_trades": [
            {"event_id": "E_OM", "market_id": "1.CS", "status": "open"},
            {"event_id": "E_OM2", "market_id": "1.CS2", "status": "won"},       # chiusa
            {"event_id": "E_OM3", "market_id": "1.HT", "status": "pending"},
        ],
        "safe_strategy_trades": [
            {"event_id": "T_SAFE", "market_id": "1.TMO", "sport": "tennis", "status": "hedged"},
            {"event_id": "E_SAFE", "market_id": "1.OU", "sport": "calcio", "status": "lost"},
        ],
        "betfair_live_orders": [
            {"event_id": "E_SCALP", "market_id": "1.SC", "status": "EXECUTABLE"},
            {"event_id": "E_SCALP2", "market_id": "1.SC2", "status": "Executable"},
            {"event_id": "E_FATTO", "market_id": "1.F", "status": "EXECUTION_COMPLETE"},
        ],
        "betfair_live_positions": [
            {"mode": "paper", "event_id": "E_POS", "market_id": "1.P", "matched_if_win": 5.0,
             "matched_if_lose": -2.0, "unmatched_back_exposure": 0, "unmatched_lay_exposure": 0},
            {"mode": "live", "event_id": "E_REG", "market_id": "1.R", "matched_if_win": 5.0,
             "matched_if_lose": -2.0, "unmatched_back_exposure": 0, "unmatched_lay_exposure": 0},
            {"mode": "live", "event_id": "E_PARI", "market_id": "1.Z", "matched_if_win": 1.0,
             "matched_if_lose": 1.0, "unmatched_back_exposure": 0, "unmatched_lay_exposure": 0},
        ],
        "betfair_live_settled": [{"mode": "live", "market_id": "1.R"}],
        "tennis_live_orders": [{"event_id": "T_BOT", "market_id": "1.T", "status": "PENDING"}],
        "tennis_live_positions": [
            {"mode": "live", "event_id": "T_POS", "market_id": "1.TP", "matched_if_win": 0,
             "matched_if_lose": 0, "unmatched_back_exposure": 2.0, "unmatched_lay_exposure": 0},
        ],
    })
    monkeypatch.setattr(SDB, "get_supabase_client", lambda: sb)
    out = SDB._list_bot_exposures_a_fonti()        # il ripiego senza la RPC (R6)
    assert [r["event_id"] for r in out["omega"]] == ["E_OM", "E_OM3"]
    assert out["safe"] == [_esp("T_SAFE", "1.TMO", "safe", "tennis")]
    assert {r["event_id"] for r in out["ordini_calcio"]} == {"E_SCALP", "E_SCALP2"}
    assert [r["event_id"] for r in out["posizioni_calcio"]] == ["E_POS"]   # regolata e pari fuori
    assert out["ordini_tennis"] == [_esp("T_BOT", "1.T", "specchio", "tennis")]
    assert [r["event_id"] for r in out["posizioni_tennis"]] == ["T_POS"]
    # le posizioni si leggono con il limite di lettura dichiarato (mai tutta la storia)
    pos = [f for t, f in sb.query if t == "betfair_live_positions"][0]
    assert any(x[0] == "gte" and x[1] == "updated_at" for x in pos)


def test_db_una_fonte_che_cade_non_spegne_le_altre(monkeypatch):
    sb = _Sb({"omega_trades": RuntimeError("rete giu'"),
              "safe_strategy_trades": RuntimeError('relation "x" does not exist 42P01'),
              "betfair_live_orders": [{"event_id": "E1", "market_id": "1.1", "status": "EXECUTABLE"}]})
    monkeypatch.setattr(SDB, "get_supabase_client", lambda: sb)
    out = SDB._list_bot_exposures_a_fonti()
    assert out["omega"] is None                 # lettura fallita: il chiamante tiene l'ultima
    assert out["safe"] == []                    # tabella assente: bot non installato
    assert [r["event_id"] for r in out["ordini_calcio"]] == ["E1"]


def test_scanner_tiene_l_ultima_lista_buona_per_fonte(monkeypatch):
    scan = _scan(dry=False)
    esiti = [_fonti(omega=[_esp("E_OM", "1.CS", "omega")]),
             _fonti(omega=None, safe=[_esp("E_S", "1.O", "safe")])]
    monkeypatch.setattr(S.scan_db, "list_bot_exposures", lambda: esiti.pop(0))
    scan._mike_followed = lambda now_mono=None: []      # type: ignore[method-assign]
    assert set(scan._esposizioni(now_mono=100.0)) == {"E_OM"}
    assert set(scan._esposizioni(now_mono=105.0)) == {"E_OM"}          # cache 10 s
    assert set(scan._esposizioni(now_mono=111.0)) == {"E_OM", "E_S"}   # omega caduta: resta


# =============================================================== 27: riga
def _scan_con_partita(ko_dt, sport="calcio", eid="E1", mo="1.MO1"):
    scan = _scan()
    scan.sports[sport].metas = {eid: _meta(eid, mo, ko_dt)}
    scan._rebuild_market_index()
    scan.events[eid] = {"sport": sport, "inplay": False, "mo_status": "OPEN"}
    return scan


@pytest.mark.parametrize("bot,fonte", [("omega", "omega"), ("safe", "safe"),
                                       ("specchio", "ordini_calcio"),
                                       ("specchio", "posizioni_calcio")])
def test_partita_esposta_di_qualunque_bot_oltre_il_tetto_resta(bot, fonte):
    """Prima (aa5749a) solo Mike: Omega/Safe/scalper dopo 3 h perdevano la riga."""
    scan = _scan_con_partita(NOW - TETTO - timedelta(hours=1))
    scan._esposizioni_fonti = _fonti(**{fonte: [_esp("E1", "1.X", bot)]})
    _, wanted = scan.build_rows(NOW)
    assert wanted == ["E1"]


def test_tennis_esposto_oltre_il_tetto_resta():
    scan = _scan_con_partita(NOW - TETTO - timedelta(hours=2), sport="tennis", eid="T1")
    scan._esposizioni_fonti = _fonti(ordini_tennis=[_esp("T1", "1.MO1", "specchio", "tennis")])
    _, wanted = scan.build_rows(NOW)
    assert wanted == ["T1"]


def test_senza_esposizione_oltre_il_tetto_esce_ancora():
    scan = _scan_con_partita(NOW - TETTO - timedelta(seconds=1))
    scan._esposizioni_fonti = _fonti(omega=[_esp("ALTRA", "1.X", "omega")])
    _, wanted = scan.build_rows(NOW)
    assert wanted == []


def _scan_mo_chiuso_con_cs(stato_cs):
    scan = _scan_con_partita(NOW - timedelta(minutes=100))
    scan.events["E1"].update({"inplay": True, "mo_status": "CLOSED", "minute": 90})
    scan.cs_markets["E1"] = {"market_id": "1.CS", "names": {1: "1 - 0", 2: "Any Other Home Win"}}
    scan._rebuild_market_index()
    scan._apply_market_book(_book("1.CS", status=stato_cs))
    scan._esposizioni_fonti = _fonti(omega=[_esp("E1", "1.CS", "omega")])
    return scan


def test_mo_chiuso_ma_cs_esposto_ancora_aperto_la_riga_resta():
    scan = _scan_mo_chiuso_con_cs("SUSPENDED")
    _, wanted = scan.build_rows(NOW)
    assert wanted == ["E1"]
    # e il CS resta sottoscritto (davanti a tutto) finche' non arriva il suo CLOSED
    assert "1.CS" in scan.relevant_market_ids("calcio", NOW)


def test_mo_chiuso_e_cs_esposto_chiuso_la_riga_esce():
    scan = _scan_mo_chiuso_con_cs("CLOSED")
    _, wanted = scan.build_rows(NOW)
    assert wanted == []
    assert "1.CS" not in scan.relevant_market_ids("calcio", NOW)


def test_mo_chiuso_e_mercato_esposto_mai_visto_la_riga_esce():
    """Nessun fatto dice che il mercato esposto e' aperto: vale il MO CLOSED."""
    scan = _scan_con_partita(NOW - timedelta(minutes=100))
    scan.events["E1"].update({"inplay": True, "mo_status": "CLOSED"})
    scan._esposizioni_fonti = _fonti(safe=[_esp("E1", "1.MAI_VISTO", "safe")])
    _, wanted = scan.build_rows(NOW)
    assert wanted == []


def test_catalogo_tiene_tennis_esposto_da_safe_fuori_finestra():
    """Prima ``_tieni_eventi_vivi`` guardava solo Mike e solo il calcio."""
    scan = _scan()
    vecchi = {"T1": _meta("T1", "1.T", NOW - timedelta(hours=8))}
    scan.events["T1"] = {"sport": "tennis", "inplay": False, "mo_status": "OPEN"}
    scan._esposizioni_fonti = _fonti(safe=[_esp("T1", "1.T", "safe", "tennis")])
    nuovi: dict = {}
    assert scan._tieni_eventi_vivi("tennis", vecchi, nuovi, now=NOW) == 1
    assert set(nuovi) == {"T1"}


# =============================================================== 28: tetti
def _scan_in_gioco(minute, gol=(0, 0)):
    scan = _scan_con_partita(NOW - timedelta(minutes=minute + 2))
    scan.events["E1"].update({"inplay": True, "minute": minute,
                              "score_home": gol[0], "score_away": gol[1]})
    return scan


def test_cs_esposto_prima_del_30_e_sottoscritto_e_davanti():
    scan = _scan_in_gioco(10)
    scan.cs_markets["E1"] = {"market_id": "1.CS", "names": {}}
    scan._rebuild_market_index()
    assert "1.CS" not in scan.relevant_market_ids("calcio", NOW)       # tetto di candidatura
    scan._esposizioni_fonti = _fonti(omega=[_esp("E1", "1.CS", "omega")])
    ranked = scan.ranked_relevant_markets("calcio", NOW)
    assert ranked[0][0][0] == -1                                         # tier -1
    assert {mid for _, mid in ranked} == {"1.MO1", "1.CS"}


def test_cs_esposto_con_4_gol_resta_sottoscritto():
    scan = _scan_in_gioco(60, gol=(4, 0))
    scan.cs_markets["E1"] = {"market_id": "1.CS", "names": {}}
    scan._rebuild_market_index()
    scan._esposizioni_fonti = _fonti(safe=[_esp("E1", "1.CS", "safe")])
    assert "1.CS" in scan.relevant_market_ids("calcio", NOW)


def test_ht_score_esposto_nel_recupero_del_primo_tempo_resta():
    scan = _scan_in_gioco(46)
    scan.ht_markets["E1"] = {"market_id": "1.HTS", "names": {}}
    scan._rebuild_market_index()
    assert "1.HTS" not in scan.relevant_market_ids("calcio", NOW)
    scan._esposizioni_fonti = _fonti(omega=[_esp("E1", "1.HTS", "omega")])
    assert "1.HTS" in scan.relevant_market_ids("calcio", NOW)


def _scan_con_opp(minute, gol, mtype, line, mid="1.OPP"):
    scan = _scan_in_gioco(minute, gol)
    scan.opp_markets["E1"] = {mid: {"market_id": mid, "market_type": mtype, "line": line,
                                    "names": {1: "Under", 2: "Over"}}}
    scan._rebuild_market_index()
    scan._apply_market_book(_book(mid))
    return scan


def test_linea_ou_decisa_con_posizione_safe_resta_nella_riga_e_nello_stream():
    scan = _scan_con_opp(70, (2, 1), "OVER_UNDER_25", 2.5)        # 3 gol: 2,5 decisa
    rows, _ = scan.build_rows(NOW)
    assert rows[0]["payload"]["ou"] is None                         # senza esposizione: via
    scan._apply_market_book(_book("1.OPP"))
    scan._esposizioni_fonti = _fonti(safe=[_esp("E1", "1.OPP", "safe")])
    rows, _ = scan.build_rows(NOW)
    assert [b["market_id"] for b in rows[0]["payload"]["ou"]] == ["1.OPP"]
    assert rows[0]["payload"]["ou"][0].get("decided") is True       # mai prezzata come viva
    assert "1.OPP" in scan.relevant_market_ids("calcio", NOW)


def test_mercato_esposto_chiuso_esce():
    scan = _scan_con_opp(70, (2, 1), "OVER_UNDER_25", 2.5)
    scan._apply_market_book(_book("1.OPP", status="CLOSED"))
    scan._esposizioni_fonti = _fonti(safe=[_esp("E1", "1.OPP", "safe")])
    assert "1.OPP" not in scan.relevant_market_ids("calcio", NOW)
    rows, _ = scan.build_rows(NOW)
    assert rows[0]["payload"]["ou"] is None


def test_tetto_dei_20_eventi_non_esclude_una_partita_esposta(monkeypatch):
    monkeypatch.setattr(scanner, "OPP_MAX_EVENTS", 0)       # tetto pieno
    scan = _scan_con_opp(30, (0, 0), "BOTH_TEAMS_TO_SCORE", None, mid="1.BTTS")
    assert "1.BTTS" not in scan.relevant_market_ids("calcio", NOW)
    scan._esposizioni_fonti = _fonti(ordini_calcio=[_esp("E1", "1.BTTS", "specchio")])
    assert "1.BTTS" in scan.relevant_market_ids("calcio", NOW)


def test_pool_pieno_escono_solo_i_mercati_senza_esposizione():
    """Con il pool stream pieno (shard da 1) resta il mercato esposto, non
    quello in gioco senza esposizione che prima aveva tier 0."""
    scan = _scan_in_gioco(50)
    scan.sports["calcio"].metas["E2"] = _meta("E2", "1.MO2", NOW - timedelta(minutes=55))
    scan.cs_markets["E1"] = {"market_id": "1.CS", "names": {}}
    scan._rebuild_market_index()
    scan.events["E2"] = {"sport": "calcio", "inplay": True, "mo_status": "OPEN", "minute": 50}
    scan._esposizioni_fonti = _fonti(omega=[_esp("E1", "1.CS", "omega")])
    ranked = [mid for _, mid in scan.ranked_relevant_markets("calcio", NOW)]
    # 1.CS (esposto) e 1.MO1 (riga dell'evento esposto) davanti al MO non esposto
    assert ranked.index("1.MO2") > ranked.index("1.CS")
    assert ranked.index("1.MO2") > ranked.index("1.MO1")
    piano = STREAM.plan_shards(ranked, 1, 2)
    assert "1.MO2" not in piano[0] and {"1.CS", "1.MO1"} <= set(piano[0])


class _PoolFinto:
    def __init__(self, fuori):
        self.fuori = set(fuori)
        self.ultimi: list = []

    def set_markets(self, ids):
        self.ultimi = list(ids)

    def planned_ids(self):
        return {m for m in self.ultimi if m not in self.fuori}


def test_diario_del_pool_critical_solo_per_gli_esposti():
    scan = _scan_in_gioco(50)
    scan.cs_markets["E1"] = {"market_id": "1.CS", "names": {}}
    scan._rebuild_market_index()
    scan._esposizioni_fonti = _fonti(omega=[_esp("E1", "1.CS", "omega")])
    scan.stream = _PoolFinto(fuori={"1.CS"})
    scan.refresh_stream_set(NOW)
    codici = [(a["level"], a["code"]) for a in scan._avvisi_in_attesa]
    assert codici == [("CRITICAL", "SCANNER_ESPOSTI_NON_SOTTOSCRITTI")]
    assert "1.CS" in scan._avvisi_in_attesa[0]["message"]
    scan.refresh_stream_set(NOW)                       # stesso episodio: niente raffica
    assert len(scan._avvisi_in_attesa) == 1
    scan._avvisi_in_attesa.clear()
    scan.stream = _PoolFinto(fuori={"1.MO1"})          # fuori un non esposto? MO1 e' della riga esposta
    scan._esposizioni_fonti = _fonti()                 # nessuna esposizione
    scan.refresh_stream_set(NOW)
    assert list(scan._avvisi_in_attesa) == []          # solo WARNING nel log


# ------------------------------------------------- 28: catalogo per market_id
class _BettingCat:
    def __init__(self, risposta=None, errore=None):
        self.risposta = list(risposta or [])
        self.errore = errore
        self.calls: list = []

    def list_market_catalogue(self, **kw):
        self.calls.append(kw)
        if self.errore is not None:
            raise self.errore
        f = kw["filter"]
        out = list(self.risposta)
        if f.get("marketIds"):
            out = [c for c in out if c.market_id in f["marketIds"]]
        if f.get("eventIds"):
            out = [c for c in out if c.event.id in f["eventIds"]]
        return out


def _cat(eid, mid, mtype, ko_dt=None, runners=((1, "1 - 0"), (2, "0 - 0"))):
    return SimpleNamespace(
        event=SimpleNamespace(id=eid, name="A v B"), market_id=mid, market_name=None,
        description=SimpleNamespace(market_type=mtype),
        runners=[SimpleNamespace(selection_id=s, runner_name=n, sort_priority=i)
                 for i, (s, n) in enumerate(runners, 1)],
        market_start_time=ko_dt or NOW, competition=SimpleNamespace(name="Serie A"),
    )


def _scan_client(betting, minute=10):
    scan = S.Scanner(SimpleNamespace(betting=betting), dry=True, use_stream=False)
    scan.pre_ko_ou_hours = 0.0
    scan.sports["calcio"].catalogue_ts = 1.0
    scan.sports["tennis"].catalogue_ts = 1.0
    scan.sports["calcio"].metas = {"E1": _meta("E1", "1.MO1", NOW - timedelta(minutes=minute))}
    scan._rebuild_market_index()
    scan.events["E1"] = {"sport": "calcio", "inplay": True, "mo_status": "OPEN", "minute": minute,
                         "score_home": 0, "score_away": 0}
    return scan


def test_mercato_esposto_ignoto_entra_con_una_chiamata_per_market_id():
    betting = _BettingCat([_cat("E1", "1.CS", "CORRECT_SCORE"),
                           _cat("E1", "1.HT1", "HALF_TIME")])
    scan = _scan_client(betting)
    assert scan.refresh_mercati_esposti(now_mono=0.0) == 0
    assert betting.calls == []                                   # niente esposto: 0 chiamate
    scan._esposizioni_fonti = _fonti(omega=[_esp("E1", "1.CS", "omega")],
                                     safe=[_esp("E1", "1.HT1", "safe")])
    assert scan.refresh_mercati_esposti(now_mono=0.0) == 2
    assert sorted(betting.calls[0]["filter"]["marketIds"]) == ["1.CS", "1.HT1"]
    assert scan.cs_markets["E1"]["market_id"] == "1.CS"
    assert "1.HT1" in scan.opp_markets["E1"]
    assert {"1.CS", "1.HT1"} <= set(scan.relevant_market_ids("calcio", NOW))
    assert scan.refresh_mercati_esposti(now_mono=1.0) == 0 and len(betting.calls) == 1


def test_mercato_esposto_di_tipo_non_pubblicato_critical_solo_per_i_bot_sul_feed():
    betting = _BettingCat([_cat("E1", "1.AH", "ASIAN_HANDICAP"), _cat("E1", "1.AH2", "ASIAN_HANDICAP")])
    scan = _scan_client(betting)
    scan._esposizioni_fonti = _fonti(omega=[_esp("E1", "1.AH", "omega")],
                                     ordini_calcio=[_esp("E1", "1.AH2", "specchio")])
    scan.refresh_mercati_esposti(now_mono=0.0)
    critici = [a for a in scan._avvisi_in_attesa if a["level"] == "CRITICAL"]
    assert len(critici) == 1 and "1.AH " in critici[0]["message"]
    scan.refresh_mercati_esposti(now_mono=10_000.0)
    assert len(betting.calls) == 1                     # tipo non pubblicato: mai richiesto


def test_mercato_esposto_non_restituito_e_chiuso_niente_critical_niente_raffica():
    betting = _BettingCat([])
    scan = _scan_client(betting)
    scan._esposizioni_fonti = _fonti(safe=[_esp("E1", "1.CHIUSO", "safe")])
    scan.refresh_mercati_esposti(now_mono=0.0)
    scan.refresh_mercati_esposti(now_mono=10.0)
    assert len(betting.calls) == 1
    assert list(scan._avvisi_in_attesa) == []
    scan.refresh_mercati_esposti(now_mono=S._CATALOGUE_TTL_SEC + 1.0)
    assert len(betting.calls) == 2                     # si richiede dopo il TTL


# =============================================================== 29: catalogo
def test_catalogo_troncato_l_esposto_entra_sempre_e_warning_col_conteggio(monkeypatch):
    monkeypatch.setattr(S, "_MAX_MARKETS", 2)
    betting = _BettingCat([_cat("E_A", "1.A", "MATCH_ODDS"), _cat("E_B", "1.B", "MATCH_ODDS"),
                           _cat("E_FUORI", "1.F", "MATCH_ODDS")])
    principale = [betting.risposta[0], betting.risposta[1]]           # il tetto morde

    def lmc(**kw):
        betting.calls.append(kw)
        if kw["filter"].get("eventIds"):
            return [c for c in betting.risposta if c.event.id in kw["filter"]["eventIds"]]
        return list(principale)

    betting.list_market_catalogue = lmc
    scan = S.Scanner(SimpleNamespace(betting=betting), dry=True, use_stream=False)
    scan._esposizioni_fonti = _fonti(omega=[_esp("E_FUORI", "1.CSF", "omega")])
    scan.refresh_catalogue("calcio")
    assert set(scan.sports["calcio"].metas) == {"E_A", "E_B", "E_FUORI"}
    assert betting.calls[1]["filter"]["eventIds"] == ["E_FUORI"]
    assert betting.calls[1]["filter"]["marketTypeCodes"] == ["MATCH_ODDS"]
    avvisi = [(a["level"], a["code"]) for a in scan._avvisi_in_attesa]
    assert avvisi == [("WARN", "CATALOGO_TRONCATO")]
    assert "1 esposti aggiunti" in scan._avvisi_in_attesa[0]["message"]
    scan.refresh_catalogue("calcio")                                  # stesso episodio
    assert len(scan._avvisi_in_attesa) == 1


def test_catalogo_esposto_mancante_chiamata_fallita_critical_con_elenco():
    betting = _BettingCat([_cat("E_A", "1.A", "MATCH_ODDS")])
    scan = S.Scanner(SimpleNamespace(betting=betting), dry=True, use_stream=False)
    scan.refresh_catalogue("calcio")
    betting.errore = RuntimeError("TOO_MUCH_DATA")
    scan._esposizioni_fonti = _fonti(safe=[_esp("E_X", "1.X", "safe")])
    metas = dict(scan.sports["calcio"].metas)
    assert scan._aggiungi_esposti_mancanti("calcio", metas, now_mono=0.0) == 0
    critici = [a for a in scan._avvisi_in_attesa if a["level"] == "CRITICAL"]
    assert len(critici) == 1 and "E_X" in critici[0]["message"]


def test_catalogo_esposto_che_betfair_non_restituisce_e_chiuso_niente_critical():
    betting = _BettingCat([])
    scan = S.Scanner(SimpleNamespace(betting=betting), dry=True, use_stream=False)
    scan._esposizioni_fonti = _fonti(safe=[_esp("E_CHIUSO", "1.X", "safe")])
    metas: dict = {}
    scan._aggiungi_esposti_mancanti("calcio", metas, now_mono=0.0)
    scan._aggiungi_esposti_mancanti("calcio", metas, now_mono=30.0)
    assert len(betting.calls) == 1 and metas == {}
    assert list(scan._avvisi_in_attesa) == []


def test_catalogo_senza_esposti_mancanti_zero_chiamate_in_piu():
    betting = _BettingCat([_cat("E_A", "1.A", "MATCH_ODDS")])
    scan = S.Scanner(SimpleNamespace(betting=betting), dry=True, use_stream=False)
    scan._esposizioni_fonti = _fonti(omega=[_esp("E_A", "1.CS", "omega")])
    scan.refresh_catalogue("calcio")
    assert len(betting.calls) == 1
    assert list(scan._avvisi_in_attesa) == []


# =============================================================== R6: una RPC
class _Rpc:
    def __init__(self, esito):
        self.esito = esito

    def execute(self):
        if isinstance(self.esito, Exception):
            raise self.esito
        return SimpleNamespace(data=self.esito)


class _SbRpc(_Sb):
    """Client con la RPC (``sb.rpc(nome, params).execute()``) e le tabelle del
    ripiego; conta le chiamate."""

    def __init__(self, esito_rpc, righe=None):
        super().__init__(righe or {})
        self.esito_rpc = esito_rpc
        self.rpc_chiamate: list = []

    def rpc(self, nome, params):
        self.rpc_chiamate.append((nome, dict(params)))
        return _Rpc(self.esito_rpc)


def _assente():
    from postgrest.exceptions import APIError

    return APIError({"code": "PGRST202", "details": None, "hint": None,
                     "message": "Could not find the function public.list_bot_exposures "
                                "without parameters in the schema cache"})


@pytest.fixture
def rpc_pulita(monkeypatch):
    monkeypatch.setitem(SDB._RPC_ESPOSIZIONI_STATO, "assente_ts", None)
    monkeypatch.setitem(SDB._RPC_ESPOSIZIONI_STATO, "avvisato", False)
    yield


def test_rpc_ok_una_sola_chiamata_nessuna_tabella(monkeypatch, rpc_pulita):
    sb = _SbRpc({"rows": [{"event_id": "E1", "market_id": "1.CS", "bot": "omega",
                           "modalita": "live", "sport": "calcio"},
                          {"event_id": "T1", "market_id": "1.T", "bot": "tennis_scalper",
                           "modalita": "paper", "sport": "tennis"}]})
    monkeypatch.setattr(SDB, "get_supabase_client", lambda: sb)
    out = LIST_BOT_EXPOSURES_VERA(now_ts=0.0)
    assert sb.rpc_chiamate == [("list_bot_exposures", {})]
    assert sb.query == []                                   # nessuna SELECT per fonte
    assert out == {"rpc": [_esp("E1", "1.CS", "omega"),
                           _esp("T1", "1.T", "tennis_scalper", "tennis")]}


def test_rpc_assente_ripiega_avvisa_una_volta_e_riprova_dopo(monkeypatch, rpc_pulita, caplog):
    sb = _SbRpc(_assente(), {"omega_trades": [{"event_id": "E1", "market_id": "1.CS",
                                                "status": "open"}]})
    monkeypatch.setattr(SDB, "get_supabase_client", lambda: sb)
    caplog.set_level("WARNING")
    out = LIST_BOT_EXPOSURES_VERA(now_ts=0.0)
    assert [r["event_id"] for r in out["omega"]] == ["E1"]          # ripiego per fonte
    LIST_BOT_EXPOSURES_VERA(now_ts=10.0)
    assert len(sb.rpc_chiamate) == 1                                # niente RPC a ogni giro
    avvisi = [r for r in caplog.records if "non disponibile" in r.getMessage()]
    assert len(avvisi) == 1                                         # una volta sola
    LIST_BOT_EXPOSURES_VERA(now_ts=SDB._RPC_ESPOSIZIONI_RIPROVA_S + 1.0)
    assert len(sb.rpc_chiamate) == 2                                # riprovata dopo


def test_rpc_errore_tiene_l_ultima_lista_buona(monkeypatch, rpc_pulita):
    sb = _SbRpc({"rows": [{"event_id": "E1", "market_id": "1.CS", "bot": "omega"}]})
    monkeypatch.setattr(SDB, "get_supabase_client", lambda: sb)
    monkeypatch.setattr(S.scan_db, "list_bot_exposures", LIST_BOT_EXPOSURES_VERA)
    scan = _scan(dry=False)
    scan._mike_followed = lambda now_mono=None: []      # type: ignore[method-assign]
    assert set(scan._esposizioni(now_mono=100.0)) == {"E1"}
    sb.esito_rpc = RuntimeError("57014 statement timeout")
    assert LIST_BOT_EXPOSURES_VERA(now_ts=1.0) == {"rpc": None}
    assert sb.query == []                                           # errore != assente
    assert set(scan._esposizioni(now_mono=111.0)) == {"E1"}         # ultima buona


def test_passaggio_dal_ripiego_alla_rpc_non_lascia_righe_vecchie(monkeypatch):
    scan = _scan(dry=False)
    scan._mike_followed = lambda now_mono=None: []      # type: ignore[method-assign]
    esiti = [_fonti(omega=[_esp("VECCHIA", "1.X", "omega")]),
             {"rpc": [_esp("NUOVA", "1.Y", "omega")]}]
    monkeypatch.setattr(S.scan_db, "list_bot_exposures", lambda: esiti.pop(0))
    assert set(scan._esposizioni(now_mono=100.0)) == {"VECCHIA"}
    assert set(scan._esposizioni(now_mono=111.0)) == {"NUOVA"}


# =============================================================== R9: cache
def test_mercato_esposto_non_esce_dalla_cache_senza_book():
    """Verificato su 35760084 (``AUDIT_2026-10-02/sonda_r9.py``): prima 103
    richieste in 34 minuti per un CS esposto prima del fischio."""
    betting = _BettingCat([_cat("E1", "1.CS", "CORRECT_SCORE"), _cat("E2", "1.CS2", "CORRECT_SCORE")])
    scan = _scan_client(betting)
    del scan.events["E1"]                          # pre-partita: nessun book
    scan.events["ALTRA"] = {"sport": "calcio", "inplay": True, "minute": 35,
                            "score_home": 0, "score_away": 0, "mo_status": "OPEN"}
    scan.cs_markets["E2"] = {"market_id": "1.CS2", "names": {}}   # non esposto, senza book
    scan._esposizioni_fonti = _fonti(omega=[_esp("E1", "1.CS", "omega")])
    assert scan.refresh_mercati_esposti(now_mono=0.0) == 1
    scan.refresh_cs_catalogue(scan.cs_candidates())
    assert "E1" in scan.cs_markets                 # esposto: resta
    assert "E2" not in scan.cs_markets             # non esposto: esce come prima
    assert scan.refresh_mercati_esposti(now_mono=20.0) == 0
    assert len([c for c in betting.calls if c["filter"].get("marketIds")]) == 1
