# -*- coding: utf-8 -*-
"""La misura dell'INGRESSO PASSIVO sa diventare rossa.

Tre famiglie, come chiede `PROCESSO_STANDARD_BOT.md` §6.7 e §6.10:

  1. CONTRATTO — il book finto e' costruito con le IDENTICHE chiavi dello
     stream vero (`op`/`pt`/`mc`/`id`/`marketDefinition`/`rc`/`atb`/`atl`/
     `trd`/`tv`/`ltp`), e passa dal PARSER VERO di flumine
     (`HistoricListener`), non da un `MarketBook` scritto a mano. Il test
     confronta le chiavi del finto con quelle che compaiono davvero in
     `_live_raw` (difetto 27 del catalogo: «i finti con chiavi o tipi diversi
     dal vero certificano il difetto» — 15/09, 32 ordini veri in loop).
  2. LA REGOLA DELLA CODA — un caso in cui l'ordine appoggiato DEVE abbinarsi
     e uno in cui NON deve, perche' il volume era gia' in coda (o gia'
     scambiato) prima del nostro arrivo.
  3. FALSIFICAZIONE — rompendo la regola della coda (ignorare la quantita'
     gia' in coda; contare il volume ASSOLUTO invece del delta) il caso
     «non deve abbinarsi» si abbina: cioe' il test sa diventare rosso, e
     quindi certifica qualcosa.

Uso: `python -m pytest Betfair/omega/tests/test_ingresso_passivo_2026_09_17.py -q`
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

import pytest

from Betfair.omega.tools import misura_ingresso_passivo as MIP

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
LIVE_RAW = os.path.join(RADICE, "_live_raw")

# selectionId veri di Betfair per il Correct Score (gusci concentrici):
# 13 = "3 - 3", 1 = "0 - 0". Sono gli id VERI, non numeri inventati.
SEL_3_3 = 13
SEL_0_0 = 1

MARKET_DEFINITION: Dict[str, Any] = {
    "bspMarket": False,
    "turnInPlayEnabled": True,
    "persistenceEnabled": True,
    "marketBaseRate": 5,
    "eventId": "99999999",
    "eventTypeId": "1",
    "numberOfWinners": 1,
    "bettingType": "ODDS",
    "marketType": "CORRECT_SCORE",
    "marketTime": "2026-09-17T16:00:00.000Z",
    "suspendTime": "2026-09-17T16:00:00.000Z",
    "bspReconciled": False,
    "complete": True,
    "inPlay": True,
    "crossMatching": False,
    "runnersVoidable": False,
    "numberOfActiveRunners": 2,
    "betDelay": 5,
    "status": "OPEN",
    "runners": [
        {"status": "ACTIVE", "sortPriority": 1, "id": SEL_3_3},
        {"status": "ACTIVE", "sortPriority": 2, "id": SEL_0_0},
    ],
    "regulators": ["MR_ITA"],
    "countryCode": "IT",
    "discountAllowed": True,
    "timezone": "GMT",
    "openDate": "2026-09-17T16:00:00.000Z",
    "version": 1,
    "priceLadderDefinition": {"type": "CLASSIC"},
}


class BookFinto:
    """Book sintetico costruito col PARSER VERO dello stream Betfair.

    Non si costruisce nessun `MarketBook` a mano: si scrivono i messaggi
    `mcm` come li scrive il recorder e li si passa a `HistoricListener`, che
    e' lo stesso oggetto con cui flumine legge `_live_raw`.
    """

    def __init__(self, market_id: str = "1.999999999") -> None:
        from flumine.streams.historicalstream import HistoricListener

        self.market_id = market_id
        self.listener = HistoricListener(max_latency=None, lightweight=False)
        self.listener.register_stream(1, "marketSubscription")
        self.messaggi: List[Dict[str, Any]] = []

    def immagine(self, pt: int, rc: List[Dict[str, Any]],
                 definizione: Optional[Dict[str, Any]] = None) -> Any:
        msg = {
            "op": "mcm", "clk": "AAAAAAAA", "pt": int(pt), "ct": "SUB_IMAGE",
            "mc": [{"id": self.market_id,
                    "marketDefinition": dict(definizione or MARKET_DEFINITION),
                    "rc": rc, "img": True}],
        }
        return self._applica(msg)

    def aggiornamento(self, pt: int, rc: List[Dict[str, Any]],
                      definizione: Optional[Dict[str, Any]] = None) -> Any:
        mc: Dict[str, Any] = {"id": self.market_id, "rc": rc}
        if definizione is not None:
            mc["marketDefinition"] = definizione
        msg = {"op": "mcm", "clk": "AAAAAAAB", "pt": int(pt), "mc": [mc]}
        return self._applica(msg)

    def _applica(self, msg: Dict[str, Any]) -> Any:
        self.messaggi.append(msg)
        self.listener.on_data(json.dumps(msg))
        cache = self.listener.stream._caches[self.market_id]
        return cache.create_resource(1, snap=True)


def _runner(market_book: Any, selection_id: int) -> Any:
    return MIP.runner_di(market_book, selection_id)


def _candidato(prezzo_tocco: float, prezzo_passivo: float) -> MIP.Candidato:
    from Betfair.omega.tools import misura_k as MK

    return MIP.Candidato(
        event_id="99999999", mercato="CORRECT_SCORE", gamba="2T",
        market_id="1.999999999", selection_id=SEL_3_3, nome="3 - 3",
        minuto_ingresso=60, minuto_riga=60, punteggio=(1, 0),
        prezzo_tocco=float(prezzo_tocco), size_tocco=50.0,
        prezzo_back=26.0, size_back=10.0, spread_tick=4,
        livello="a", prezzo_passivo=float(prezzo_passivo),
        ticks_guadagnati=MIP.ticks_fra(prezzo_passivo, prezzo_tocco),
        p_impl_tocco=float(MK.p_implicita(prezzo_tocco, MIP.COMMISSIONE)),
        p_impl_passivo=float(MK.p_implicita(prezzo_passivo, MIP.COMMISSIONE)),
        fascia=MK.secchio_di(float(MK.p_implicita(prezzo_tocco, MIP.COMMISSIONE))),
        esito_cella=False)


def _cliente() -> Any:
    """Il client SIMULATO VERO, montato come lo monta il banco comune.

    Non un doppio: si costruisce un `FlumineSimulation` col client del banco,
    cosi' `client.execution` e' l'esecuzione simulata vera — la stessa che
    `BetfairOrderPackage.calc_simulated_delay` interroga."""
    from flumine import FlumineSimulation

    from Betfair.stream.backtest import banco_comune as BC

    quadro = FlumineSimulation(client=BC.cliente_simulato())
    return quadro.clients.get_default()


class _StrategiaFinta:
    """Il minimo che `BetfairOrder.customer_order_ref` chiede alla strategia:
    `name_hash`, con lo stesso tipo del vero (str)."""

    name_hash = "test"


def _appoggia(cliente: Any, book: Any, prezzo_passivo: float,
              prezzo_tocco: float) -> MIP.Appoggiato:
    cand = _candidato(prezzo_tocco, prezzo_passivo)
    ap = MIP.Appoggiato(cand, attivo_da_ms=0,
                        pt_decisione_ms=int(book.publish_time_epoch))
    ap.piazza(cliente, book, _StrategiaFinta())
    return ap


def _delta(analitica: Any, market_book: Any, selection_id: int) -> Tuple[Any, Dict[float, float]]:
    """Il delta del volume scambiato, calcolato da flumine come nel middleware."""
    runner = _runner(market_book, selection_id)
    analitica(runner)
    return runner, dict(analitica.traded)


# ---------------------------------------------------------------------------
# 1. CONTRATTO — il finto parla come il vero
# ---------------------------------------------------------------------------
def test_il_book_finto_usa_le_stesse_chiavi_dello_stream_vero() -> None:
    """Ogni chiave del messaggio finto compare davvero nelle registrazioni."""
    registrazioni = [n for n in sorted(os.listdir(LIVE_RAW))
                     if not n.startswith("_synth")] if os.path.isdir(LIVE_RAW) else []
    raw = None
    for nome in registrazioni:
        p = os.path.join(LIVE_RAW, nome, "%s.raw.jsonl" % nome)
        if os.path.isfile(p):
            raw = p
            break
    if raw is None:
        pytest.skip("nessuna registrazione reale disponibile")

    chiavi_vere_msg: set = set()
    chiavi_vere_mc: set = set()
    chiavi_vere_md: set = set()
    chiavi_vere_rc: set = set()
    with open(raw, "r", encoding="utf-8") as fh:
        for i, riga in enumerate(fh):
            if i > 4000:
                break
            try:
                d = json.loads(riga)
            except ValueError:
                continue
            chiavi_vere_msg |= set(d.keys())
            for mc in d.get("mc") or []:
                chiavi_vere_mc |= set(mc.keys())
                chiavi_vere_md |= set((mc.get("marketDefinition") or {}).keys())
                for rc in mc.get("rc") or []:
                    chiavi_vere_rc |= set(rc.keys())

    book = BookFinto()
    book.immagine(1_000_000, [{"atb": [[26, 10.0]], "atl": [[30, 50.0]], "id": SEL_3_3}])
    book.aggiornamento(1_006_000, [{"atb": [[29, 5.0], [26, 10.0]],
                                    "trd": [[29, 40.0]], "ltp": 29, "tv": 40.0,
                                    "id": SEL_3_3}])
    for msg in book.messaggi:
        assert set(msg.keys()) <= chiavi_vere_msg, set(msg.keys()) - chiavi_vere_msg
        for mc in msg["mc"]:
            assert set(mc.keys()) <= chiavi_vere_mc, set(mc.keys()) - chiavi_vere_mc
            md = mc.get("marketDefinition") or {}
            assert set(md.keys()) <= chiavi_vere_md, set(md.keys()) - chiavi_vere_md
            for rc in mc.get("rc") or []:
                assert set(rc.keys()) <= chiavi_vere_rc, set(rc.keys()) - chiavi_vere_rc
    # e le chiavi che questa misura USA ci sono davvero nello stream vero
    for chiave in ("atb", "atl", "trd", "tv", "id"):
        assert chiave in chiavi_vere_rc
    assert "marketDefinition" in chiavi_vere_mc


def test_il_parser_e_quello_di_flumine_e_i_prezzi_arrivano_dove_li_legge_la_misura() -> None:
    book = BookFinto()
    mb = book.immagine(1_000_000, [{"atb": [[26, 10.0]], "atl": [[30, 50.0]],
                                    "id": SEL_3_3}])
    runner = _runner(mb, SEL_3_3)
    assert mb.status == "OPEN"
    assert mb.market_definition.bet_delay == 5
    assert mb.market_definition.in_play is True
    assert runner.status == "ACTIVE"
    assert runner.ex.available_to_lay[0] == {"price": 30, "size": 50.0}
    assert runner.ex.available_to_back[0] == {"price": 26, "size": 10.0}


# ---------------------------------------------------------------------------
# 2. LA REGOLA DELLA CODA
# ---------------------------------------------------------------------------
def test_si_abbina_quando_il_volume_arriva_dopo_e_davanti_non_c_e_nessuno() -> None:
    """Coda davanti ZERO + 40 EUR scambiati DOPO il nostro arrivo -> abbinato."""
    from flumine.markets.middleware import RunnerAnalytics

    book = BookFinto()
    mb0 = book.immagine(1_000_000, [{"atb": [[26, 10.0]], "atl": [[30, 50.0]],
                                     "id": SEL_3_3}])
    analitica = RunnerAnalytics(_runner(mb0, SEL_3_3))
    ap = _appoggia(_cliente(), mb0, prezzo_passivo=29.0, prezzo_tocco=30.0)
    assert ap.cand.piazzato is True, ap.cand.motivo_non_piazzato
    assert ap.cand.coda_davanti == 0.0        # a 29 non c'era nessuno

    mb1 = book.aggiornamento(1_006_000, [{"atb": [[29, 5.0], [26, 10.0]],
                                          "trd": [[29, 40.0]], "ltp": 29,
                                          "tv": 40.0, "id": SEL_3_3}])
    runner, delta = _delta(analitica, mb1, SEL_3_3)
    assert delta == {29: 40.0}                # il delta e' tutto nuovo
    ap.applica(mb1, runner, dict(delta))

    assert ap.cand.abbinato is True
    assert ap.cand.size_abbinata == pytest.approx(MIP.STAKE_EUR)
    assert ap.cand.prezzo_ottenuto == pytest.approx(29.0)


def test_non_si_abbina_se_davanti_c_era_gia_la_coda() -> None:
    """A 29 c'erano gia' 100 EUR di back: 40 scambiati (20 dopo il dimezzamento
    di flumine) non bastano a superarli -> NESSUN abbinamento."""
    from flumine.markets.middleware import RunnerAnalytics

    book = BookFinto()
    mb0 = book.immagine(1_000_000, [{"atb": [[29, 100.0], [26, 10.0]],
                                     "atl": [[30, 50.0]], "id": SEL_3_3}])
    analitica = RunnerAnalytics(_runner(mb0, SEL_3_3))
    ap = _appoggia(_cliente(), mb0, prezzo_passivo=29.0, prezzo_tocco=30.0)
    assert ap.cand.piazzato is True, ap.cand.motivo_non_piazzato
    assert ap.cand.coda_davanti == 100.0

    mb1 = book.aggiornamento(1_006_000, [{"atb": [[29, 60.0], [26, 10.0]],
                                          "trd": [[29, 40.0]], "ltp": 29,
                                          "tv": 40.0, "id": SEL_3_3}])
    runner, delta = _delta(analitica, mb1, SEL_3_3)
    assert delta == {29: 40.0}
    ap.applica(mb1, runner, dict(delta))

    assert ap.cand.abbinato is False
    assert ap.cand.size_abbinata == 0.0
    # la coda si e' consumata di meta' del volume scambiato, come dice flumine
    assert ap.sim._piq == pytest.approx(80.0)


def test_non_si_abbina_se_il_volume_era_gia_stato_scambiato_prima_di_noi() -> None:
    """200 EUR gia' scambiati a 29 PRIMA del nostro arrivo, e poi piu' niente:
    il delta e' zero, quindi niente abbinamento."""
    from flumine.markets.middleware import RunnerAnalytics

    book = BookFinto()
    mb0 = book.immagine(1_000_000, [{"atb": [[26, 10.0]], "atl": [[30, 50.0]],
                                     "trd": [[29, 200.0]], "ltp": 29, "tv": 200.0,
                                     "id": SEL_3_3}])
    analitica = RunnerAnalytics(_runner(mb0, SEL_3_3))
    ap = _appoggia(_cliente(), mb0, prezzo_passivo=29.0, prezzo_tocco=30.0)
    assert ap.cand.piazzato is True, ap.cand.motivo_non_piazzato

    mb1 = book.aggiornamento(1_006_000, [{"atb": [[27, 3.0], [26, 10.0]],
                                          "id": SEL_3_3}])
    runner, delta = _delta(analitica, mb1, SEL_3_3)
    assert delta == {}                        # nessun volume NUOVO
    ap.applica(mb1, runner, dict(delta))
    assert ap.cand.abbinato is False


def test_un_prezzo_che_il_book_offre_gia_non_e_un_ingresso_passivo() -> None:
    """Appoggiare a 30 quando il best lay E' 30 e' un ordine al tocco: flumine
    lo abbina nel `place`, e la misura lo scarta invece di contarlo."""
    book = BookFinto()
    mb0 = book.immagine(1_000_000, [{"atb": [[26, 10.0]], "atl": [[30, 50.0]],
                                     "id": SEL_3_3}])
    ap = _appoggia(_cliente(), mb0, prezzo_passivo=30.0, prezzo_tocco=30.0)
    assert ap.cand.piazzato is False
    assert ap.cand.motivo_non_piazzato == "abbinato_al_place_non_passivo"


def test_la_sospensione_in_gioco_uccide_l_ordine_appoggiato() -> None:
    book = BookFinto()
    mb0 = book.immagine(1_000_000, [{"atb": [[26, 10.0]], "atl": [[30, 50.0]],
                                     "id": SEL_3_3}])
    ap = _appoggia(_cliente(), mb0, prezzo_passivo=29.0, prezzo_tocco=30.0)
    assert ap.vivo is True
    ap.uccidi("sospensione")
    assert ap.vivo is False
    assert ap.cand.abbinato is False
    assert ap.cand.morte == "sospensione"


# ---------------------------------------------------------------------------
# 3. FALSIFICAZIONE — rompendo la regola, il test diventa rosso
# ---------------------------------------------------------------------------
def test_falsificazione_ignorare_la_coda_gia_presente_fa_abbinare() -> None:
    """Se si azzera la posizione in coda (cioe' si IGNORA la quantita' gia'
    presente a quel prezzo), lo stesso caso di
    `test_non_si_abbina_se_davanti_c_era_gia_la_coda` si abbina: quel test sa
    quindi diventare rosso, e la regola della coda e' cio' che lo tiene verde."""
    from flumine.markets.middleware import RunnerAnalytics

    book = BookFinto()
    mb0 = book.immagine(1_000_000, [{"atb": [[29, 100.0], [26, 10.0]],
                                     "atl": [[30, 50.0]], "id": SEL_3_3}])
    analitica = RunnerAnalytics(_runner(mb0, SEL_3_3))
    ap = _appoggia(_cliente(), mb0, prezzo_passivo=29.0, prezzo_tocco=30.0)
    assert ap.cand.coda_davanti == 100.0

    ap.sim._piq = 0.0                          # LA REGOLA ROTTA, di proposito

    mb1 = book.aggiornamento(1_006_000, [{"atb": [[29, 60.0], [26, 10.0]],
                                          "trd": [[29, 40.0]], "ltp": 29,
                                          "tv": 40.0, "id": SEL_3_3}])
    runner, delta = _delta(analitica, mb1, SEL_3_3)
    ap.applica(mb1, runner, dict(delta))
    assert ap.cand.abbinato is True            # con la regola rotta si abbina


def test_falsificazione_contare_il_volume_assoluto_invece_del_delta_fa_abbinare() -> None:
    """Se al posto del DELTA di volume scambiato si passasse il volume
    ASSOLUTO (cioe' anche quello scambiato prima del nostro arrivo), il caso
    `..._volume_era_gia_stato_scambiato_prima_di_noi` si abbinerebbe."""
    book = BookFinto()
    mb0 = book.immagine(1_000_000, [{"atb": [[26, 10.0]], "atl": [[30, 50.0]],
                                     "trd": [[29, 200.0]], "ltp": 29, "tv": 200.0,
                                     "id": SEL_3_3}])
    ap = _appoggia(_cliente(), mb0, prezzo_passivo=29.0, prezzo_tocco=30.0)
    mb1 = book.aggiornamento(1_006_000, [{"atb": [[27, 3.0], [26, 10.0]],
                                          "id": SEL_3_3}])
    runner = _runner(mb1, SEL_3_3)
    assoluto = {float(x["price"]): float(x["size"])
                for x in runner.ex.traded_volume}    # IL VOLUME ASSOLUTO: sbagliato
    assert assoluto == {29.0: 200.0}
    ap.applica(mb1, runner, dict(assoluto))
    assert ap.cand.abbinato is True             # con la regola rotta si abbina


# ---------------------------------------------------------------------------
# 4. I PREZZI PASSIVI E LA MATEMATICA
# ---------------------------------------------------------------------------
def test_i_tre_livelli_stanno_dentro_lo_spread_e_sulla_scala_tick() -> None:
    p = MIP.prezzi_passivi(26.0, 30.0)
    assert p["a"] == 29.0                       # un tick sotto il best lay
    assert p["c"] == 26.0                       # al best back
    assert 26.0 <= p["b"] < 30.0
    # il mid di 26/30 e' 28, che e' un tick valido nella banda 20-30 (passo 1)
    assert p["b"] == 28.0
    for livello in ("a", "b", "c"):
        assert p[livello] < 30.0                # mai al tocco


def test_senza_spread_non_esiste_nessun_livello_b_o_c() -> None:
    p = MIP.prezzi_passivi(29.0, 30.0)          # spread di un tick
    assert p["a"] == 29.0
    assert p["c"] == 29.0
    assert p["b"] == 29.0
    p2 = MIP.prezzi_passivi(None, 30.0)
    assert p2["a"] == 29.0 and p2["b"] is None and p2["c"] is None


def test_la_scala_tick_e_quella_di_betfair_anche_ai_bordi_di_banda() -> None:
    assert MIP.prezzi_passivi(95.0, 100.0)["a"] == 95.0    # 100 -> 95 (passo 5)
    assert MIP.prezzi_passivi(18.0, 20.0)["a"] == 19.5     # 20 -> 19,5 (passo 0,5)
    assert MIP.ticks_fra(29.0, 30.0) == 1
    assert MIP.ticks_fra(95.0, 100.0) == 1
    assert MIP.ticks_fra(30.0, 29.0) is None               # ordine invertito


def test_ev_e_quello_del_progetto() -> None:
    """EV per 1 EUR = 0,95 (1 - 1/k) — PROGETTO_OMEGA_V3 §3.3."""
    assert MIP.ev_per_euro(1.0) == pytest.approx(0.0)
    assert MIP.ev_per_euro(2.0) == pytest.approx(0.475)
    assert MIP.ev_per_euro(1.5) == pytest.approx(0.3167, abs=5e-4)
    assert MIP.ev_per_euro(0.8) == pytest.approx(-0.2375)
    assert MIP.ev_per_euro(None) is None


def test_appoggiare_piu_in_basso_alza_la_p_implicita_e_quindi_k() -> None:
    """Il senso di tutta la misura: una lay a prezzo PIU' BASSO ha una
    `p_implicita` PIU' ALTA, cioe' un k piu' alto a parita' di frequenza."""
    from Betfair.omega.tools import misura_k as MK

    p_tocco = MK.p_implicita(30.0, MIP.COMMISSIONE)
    p_passivo = MK.p_implicita(26.0, MIP.COMMISSIONE)
    assert p_passivo > p_tocco
    frequenza = 0.02
    assert (p_passivo / frequenza) > (p_tocco / frequenza)


# ---------------------------------------------------------------------------
# 5. L'ESITO DELLA CELLA VIENE DAL marketDefinition FINALE
# ---------------------------------------------------------------------------
def test_l_esito_della_cella_viene_dal_market_definition_finale() -> None:
    class _Catalogo:
        tipi = {"1.1": "CORRECT_SCORE", "1.2": "MATCH_ODDS"}
        definizioni = {
            "1.1": [
                (1000, "OPEN", True, {SEL_3_3: "ACTIVE", SEL_0_0: "ACTIVE"}),
                (2000, "CLOSED", True, {SEL_3_3: "LOSER", SEL_0_0: "WINNER"}),
            ],
            "1.2": [(2000, "CLOSED", True, {1: "WINNER"})],
        }

    esiti = MIP.esiti_dal_catalogo(_Catalogo())
    assert esiti == {"1.1": SEL_0_0}            # MATCH_ODDS non e' una griglia


def test_senza_winner_l_esito_resta_ignoto_e_non_si_conta_come_non_uscito() -> None:
    class _Catalogo:
        tipi = {"1.1": "HALF_TIME_SCORE"}
        definizioni = {"1.1": [(1000, "OPEN", True, {SEL_3_3: "ACTIVE"})]}

    assert MIP.esiti_dal_catalogo(_Catalogo()) == {"1.1": None}


# ---------------------------------------------------------------------------
# 6. LE BANDE E LE FINESTRE VENGONO DA omega_config, NON DA QUI
# ---------------------------------------------------------------------------
def test_bande_finestre_e_distanza_vengono_da_omega_config() -> None:
    from Betfair.omega import omega_config

    d = omega_config.DEFAULTS
    par = MIP.parametri_di_produzione()
    assert par["price_min"] == d["price_min"]
    assert par["price_max"] == d["price_max"]
    assert par["min_lay_liquidity"] == d["min_lay_liquidity"]
    assert par["min_goal_distance"] == d["model_min_goal_distance"]
    assert par["finestre"]["HALF_TIME_SCORE"] == (d["ht_entry_min"], d["ht_entry_max"])
    assert par["finestre"]["CORRECT_SCORE"] == (d["ft_entry_min"], d["ft_entry_max"])
    assert par["minuti"]["HALF_TIME_SCORE"][0] == d["ht_entry_min"]
    assert max(par["minuti"]["CORRECT_SCORE"]) < d["ft_entry_max"]


def test_le_registrazioni_finte_sono_escluse() -> None:
    eventi = MIP.eventi_disponibili(LIVE_RAW)
    assert all(not e.startswith("_synth") for e in eventi)
    if eventi:
        assert all(os.path.isfile(os.path.join(LIVE_RAW, e, "%s.raw.jsonl" % e))
                   for e in eventi)


# ---------------------------------------------------------------------------
# 7. CERTIFICAZIONE — lo strumento gira davvero sulla catena di produzione
# ---------------------------------------------------------------------------
@pytest.mark.cert
def test_cert_la_misura_gira_su_una_registrazione_vera() -> None:
    """Un giro intero su una registrazione vera: nessun errore del replay, e
    ogni candidato che risulta abbinato ha un prezzo ottenuto <= al tocco."""
    eid = "35833626"
    if not os.path.isfile(os.path.join(LIVE_RAW, eid, "%s.raw.jsonl" % eid)):
        pytest.skip("registrazione %s assente" % eid)
    par = MIP.parametri_di_produzione()
    candidati, diagnostica = MIP.misura_evento(eid, LIVE_RAW, parametri=par)
    assert diagnostica["errori"] == [], diagnostica["errori"]
    assert diagnostica["giri"] > 0
    # questa registrazione DEVE produrre candidati: se smettesse di produrne,
    # il test starebbe certificando il nulla
    assert candidati, "nessun candidato: la catena non sta piu' misurando niente"
    assert all(c.livello in MIP.LIVELLI for c in candidati)
    for c in candidati:
        assert par["price_min"] <= c.prezzo_tocco <= par["price_max"]
        assert c.prezzo_passivo < c.prezzo_tocco or c.prezzo_passivo == c.prezzo_tocco
        h, a = MIP._scoreline(c.nome)
        sh, sa = c.punteggio
        assert (h - sh) + (a - sa) >= par["min_goal_distance"]
        if c.abbinato:
            assert c.prezzo_ottenuto is not None
            assert c.prezzo_ottenuto <= c.prezzo_tocco + 1e-9
            assert c.attesa_s is not None and c.attesa_s >= 0
