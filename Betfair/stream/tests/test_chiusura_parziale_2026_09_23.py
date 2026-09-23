# -*- coding: utf-8 -*-
"""SCENARIO «chiusura-abbinata-in-parte» (23/09, cancello C3) — il guasto e i
controlli CP del banco comune, provati su una registrazione VERA.

Che cosa si difende:
  1. il guasto colpisce la PRIMA chiusura di una selezione e SOLO quella:
     appoggiata -> abbinata al piu' per il 40 %, residuo VIVO a mercato; FOK
     senza `minFillSize` -> uccisa per intero (per Betfair e' tutto o niente);
     l'abbinamento resta di flumine (nessun fill scritto a mano);
  2. CP1-CP3 tacciono su una credenza ONESTA (le righe scritte come le scrive la
     produzione, con `execution.hedge_state` VERO) e parlano su una credenza
     sbagliata;
  3. la falsificazione del fix del 18/09 e' DENTRO il test: con
     `execution.chiusura_abbinata` riportata al comportamento di prima (conta il
     CHIESTO) la copertura dichiarata diventa sbagliata e CP2 diventa rosso;
  4. CP4: una chiusura nuova sopra una ancora viva sulla stessa selezione e' un
     loop, e viene detto.

Le righe hanno le STESSE chiavi di `safe_strategy_trades` (colonne del 16/09:
`size_matched`, `size_remaining`, `avg_price_matched`, `bet_id`,
`closes_trade_id`, `meta.cashout`): un finto che parla un'altra lingua
certificherebbe il difetto (catalogo §7.27). Gli ORDINI sono veri, su flumine.
"""
from __future__ import annotations

import math
import os
from typing import Any, Dict, List, Optional

import pytest

from Betfair.safe_strategy import execution as X
from Betfair.stream.backtest import banco_comune as B
from Betfair.stream.backtest import chiusura_parziale as CP


def _trova_live_raw() -> str:
    """`_live_raw` sta nella radice del checkout principale. Un worktree dei
    delegati vive in `<radice>/.claude/worktrees/<nome>`: si risale finche'
    non la si trova (sola lettura)."""
    qui = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    for _ in range(5):
        cand = os.path.join(qui, "_live_raw")
        if os.path.isdir(cand):
            return cand
        qui = os.path.dirname(qui)
    return os.path.join(qui, "_live_raw")


CALCIO_DIR = _trova_live_raw()
CALCIO_EVENTO = "35833626"          # in-play dal 15', O/U 3.5 con liquidita' vera
_ha_calcio = os.path.isfile(os.path.join(CALCIO_DIR, CALCIO_EVENTO, f"{CALCIO_EVENTO}.raw.jsonl"))


def _blocco_vivo(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Il blocco O/U 3.5 aperto, in gioco, con back E lay (e size) su ENTRAMBE
    le selezioni: serve aprire due posizioni e chiuderle."""
    if row is None or not row["payload"].get("inplay"):
        return None
    b = {x["line"]: x for x in (row["payload"].get("ou") or [])}.get(3.5)
    if not b or b.get("status") != "OPEN":
        return None
    sels = b.get("selections") or []
    if len(sels) < 2 or not all(s.get("back") and (s.get("back_size") or 0) >= 3
                                and s.get("lay") and (s.get("lay_size") or 0) >= 3
                                for s in sels[:2]):
        return None
    return b


def _riga_apertura(tid: int, mid: str, sid: int, ordine: Any) -> Dict[str, Any]:
    return {"id": tid, "event_id": CALCIO_EVENTO, "market_id": mid, "selection_id": sid,
            "side": "back", "price": float(ordine.average_price_matched),
            "size": float(ordine.size_matched), "status": "open", "mode": "live",
            "bet_id": str(ordine.bet_id), "closes_trade_id": None,
            "size_requested": float(ordine.order_type.size),
            "size_matched": float(ordine.size_matched), "size_remaining": 0.0,
            "avg_price_matched": float(ordine.average_price_matched),
            "commission": 0.05, "meta": {}}


def _riga_chiusura(tid: int, apre: int, mid: str, sid: int, ordine: Any, *,
                   abbinato: Optional[float] = None) -> Dict[str, Any]:
    """La riga della gamba di chiusura come la scrive `close_trade` dopo il
    piazzamento (`aggiorna_trade` con la consapevolezza). `abbinato` diverso dal
    vero = la credenza BUGIARDA di CP1."""
    m = float(ordine.size_matched) if abbinato is None else float(abbinato)
    return {"id": tid, "event_id": CALCIO_EVENTO, "market_id": mid, "selection_id": sid,
            "side": "lay", "price": float(ordine.order_type.price),
            "size": float(ordine.order_type.size), "status": "open", "mode": "live",
            "bet_id": str(ordine.bet_id), "closes_trade_id": apre,
            "size_requested": float(ordine.order_type.size),
            "size_matched": m, "size_remaining": float(ordine.size_remaining),
            "avg_price_matched": (float(ordine.average_price_matched)
                                  if ordine.average_price_matched else None),
            "commission": 0.05,
            "meta": {"cashout": True, "closes_trade_id": apre}}


def _con_hedge(apertura: Dict[str, Any], chiusure: List[Dict[str, Any]],
               sul_chiesto: bool = False) -> Dict[str, Any]:
    """L'apertura con `meta.hedged_size` e lo stato scritti da `hedge_state`
    VERO (come fa `apply_hedge_state`). `sul_chiesto=True` = la
    FALSIFICAZIONE: `chiusura_abbinata` torna quella di prima del 18/09."""
    vera = X.chiusura_abbinata
    if sul_chiesto:
        X.chiusura_abbinata = lambda c: c          # type: ignore[assignment]
    try:
        st = X.hedge_state(apertura, chiusure)
    finally:
        X.chiusura_abbinata = vera                 # type: ignore[assignment]
    out = dict(apertura)
    out["meta"] = {**(apertura.get("meta") or {}), "hedged_size": st["hedged_size"],
                   "residual_size": st["residual_size"]}
    if st["complete"] and not st["blocked"]:
        out["status"] = "hedged"
    return out


@pytest.fixture(scope="module")
def corsa() -> Dict[str, Any]:
    if not _ha_calcio:
        pytest.skip("registrazione calcio assente")
    from flumine.utils import price_ticks_away

    g = CP.GuastoChiusuraParziale()
    sorv = {"onesta": CP.Sorveglianza(g), "sul_chiesto": CP.Sorveglianza(g),
            "bugiarda": CP.Sorveglianza(g)}
    out: Dict[str, Any] = {"guasto": g, "viol": {k: [] for k in sorv},
                           "soll": {k: {} for k in sorv}, "fase": 0}

    def servizio(*, market, row, strategia, **_):
        if market.motore is not None and market.motore.guasto_chiusure is None:
            market.motore.guasto_chiusure = g
        f = out["fase"]
        if f == 0:
            b = _blocco_vivo(row)
            if b is None or str(b["market_id"]) not in strategia.mercati:
                return
            mid = str(b["market_id"])
            a, bb = b["selections"][0], b["selections"][1]
            # due APERTURE (back FOK al tocco): nessuna e' una chiusura
            ra = market.place_order_live(market_id=mid, selection_id=int(a["selection_id"]),
                                         price=float(a["back"]), size=2.0,
                                         event_id=CALCIO_EVENTO, side="back",
                                         customer_ref="cp-apre-a")
            rb = market.place_order_live(market_id=mid, selection_id=int(bb["selection_id"]),
                                         price=float(bb["back"]), size=2.0,
                                         event_id=CALCIO_EVENTO, side="back",
                                         customer_ref="cp-apre-b")
            if not (ra.size_matched >= 2.0 and rb.size_matched >= 2.0):
                return                                  # si riprova al giro dopo
            out.update(mid=mid, sid_a=int(a["selection_id"]), sid_b=int(bb["selection_id"]),
                       apre_a=market.ordini["cp-apre-a"], apre_b=market.ordini["cp-apre-b"])
            out["fase"] = 1
            return
        mid = out["mid"]
        if f == 1:
            b = {x["line"]: x for x in (row["payload"].get("ou") or [])}.get(3.5) if row else None
            if not b or b.get("status") != "OPEN":
                return
            per_sel = {int(s["selection_id"]): s for s in b["selections"]}
            la, lb = per_sel[out["sid_a"]].get("lay"), per_sel[out["sid_b"]].get("lay")
            if not la or not lb:
                return
            # CHIUSURA A: appoggiata (non FOK), size del green-up, prezzo che
            # attraversa il libro di tre tick: senza il guasto si abbinerebbe
            p_a = price_ticks_away(float(la), 3)
            s_a = round(2.0 * float(out["apre_a"].average_price_matched) / p_a, 2)
            market.place_order_live(market_id=mid, selection_id=out["sid_a"], price=p_a,
                                    size=s_a, event_id=CALCIO_EVENTO, side="lay",
                                    customer_ref="cp-chiude-a", fill_or_kill=False)
            # CHIUSURA B: FOK, stessa costruzione
            p_b = price_ticks_away(float(lb), 3)
            s_b = round(2.0 * float(out["apre_b"].average_price_matched) / p_b, 2)
            market.place_order_live(market_id=mid, selection_id=out["sid_b"], price=p_b,
                                    size=s_b, event_id=CALCIO_EVENTO, side="lay",
                                    customer_ref="cp-chiude-b", fill_or_kill=True)
            out.update(chiude_a=market.ordini["cp-chiude-a"],
                       chiude_b=market.ordini["cp-chiude-b"])
            # istantanea SUBITO dopo il piazzamento (prima che il mercato cambi)
            ca = out["chiude_a"]
            out["a_subito"] = (float(ca.size_matched), float(ca.size_remaining),
                               CP.vivo(ca), float(ca.order_type.size))
            cb = out["chiude_b"]
            out["b_subito"] = (float(cb.size_matched), float(cb.size_cancelled),
                               float(cb.order_type.size))
            out["fase"] = 2
            return
        if 2 <= f <= 4 or f == 6:
            ap = _riga_apertura(1, mid, out["sid_a"], out["apre_a"])
            ch = _riga_chiusura(2, 1, mid, out["sid_a"], out["chiude_a"])
            righe = {
                "onesta": [_con_hedge(ap, [ch]), ch],
                "sul_chiesto": [_con_hedge(ap, [ch], sul_chiesto=True), ch],
                "bugiarda": [dict(ap, status="hedged", meta={"hedged_size": ap["size"]}),
                             _riga_chiusura(2, 1, mid, out["sid_a"], out["chiude_a"],
                                            abbinato=float(out["chiude_a"].order_type.size))],
            }
            for k, s in sorv.items():
                out["viol"][k].extend(s.verifica(CP.credenze_da_righe(righe[k]),
                                                 out["soll"][k]))
            out["fase"] = f + 1
            return
        if f == 5:
            # CP4: una SECONDA chiusura sulla stessa selezione mentre la prima
            # ha ancora il residuo vivo a mercato
            out["a_vivo_prima_della_seconda"] = CP.vivo(out["chiude_a"])
            market.place_order_live(market_id=mid, selection_id=out["sid_a"],
                                    price=float(out["chiude_a"].order_type.price),
                                    size=float(out["chiude_a"].size_remaining or 0.5),
                                    event_id=CALCIO_EVENTO, side="lay",
                                    customer_ref="cp-chiude-a2", fill_or_kill=False)
            out["fase"] = 6
            return

    esito = B.replay_evento(event_id=CALCIO_EVENTO, cartella=CALCIO_DIR,
                            servizio=servizio, sport="calcio", ogni_ms=5000)
    assert not esito.errori, esito.errori
    assert out["fase"] >= 7, f"la corsa si e' fermata alla fase {out['fase']}"
    return out


def _codici(violazioni: List[Any]) -> List[str]:
    return [v[0] for v in violazioni]


# ---------------------------------------------------------------------------
# 1. il guasto
# ---------------------------------------------------------------------------
def test_la_chiusura_appoggiata_si_abbina_al_piu_per_il_40_e_il_residuo_resta_vivo(corsa):
    m, rem, vivo, chiesto = corsa["a_subito"]
    tetto = math.floor(chiesto * CP.FRAZIONE * 100 + 1e-9) / 100
    assert 0 < m <= tetto + 1e-9, (m, tetto)
    assert rem == pytest.approx(chiesto - m, abs=0.011)
    assert vivo, "il residuo della chiusura appoggiata deve restare VIVO a mercato"
    # l'abbinato e' di flumine: ogni fill ha un publish time e un prezzo veri
    assert corsa["chiude_a"].simulated.matched
    assert all(r[0] > 0 for r in corsa["chiude_a"].simulated.matched)


def test_la_chiusura_fok_muore_per_intero(corsa):
    m, canc, chiesto = corsa["b_subito"]
    assert m == 0.0
    assert canc == pytest.approx(chiesto, abs=0.001)


def test_colpite_solo_le_prime_chiusure_e_non_le_aperture(corsa):
    g = corsa["guasto"]
    colpiti = [c["ordine"] for c in g.colpiti]
    assert colpiti == [corsa["chiude_a"], corsa["chiude_b"]]
    assert corsa["apre_a"] not in colpiti and corsa["apre_b"] not in colpiti
    assert [c["fok"] for c in g.colpiti] == [False, True]


# ---------------------------------------------------------------------------
# 2. i controlli sulla credenza
# ---------------------------------------------------------------------------
def test_la_credenza_onesta_non_viola_ed_e_sollecitata(corsa):
    cod = _codici(corsa["viol"]["onesta"])
    assert not [c for c in cod if c in ("CP1", "CP2", "CP3")], corsa["viol"]["onesta"]
    soll = corsa["soll"]["onesta"]
    for c in ("CP1", "CP2", "CP3", "CP4"):
        assert soll.get(c, 0) > 0, (c, soll)


def test_hedge_state_sul_chiesto_diventa_rosso_cp2(corsa):
    """LA FALSIFICAZIONE DEL FIX DEL 18/09, dentro il test: con
    `chiusura_abbinata` che conta il CHIESTO la copertura dichiarata sale al
    chiesto (tutta la posizione «coperta» con il 60 % ancora a rischio).
    L'apertura NON passa a 'hedged' solo perche' il residuo della chiusura e'
    ancora vivo (`chiusura_con_residuo_vivo` -> `blocked`): per questo qui CP3
    tace, e il caso «dichiarata chiusa» lo prova la riga bugiarda."""
    cod = _codici(corsa["viol"]["sul_chiesto"])
    assert "CP2" in cod, corsa["viol"]["sul_chiesto"]
    assert "sul chiesto sarebbe" in corsa["viol"]["sul_chiesto"][0][2]


def test_la_riga_bugiarda_viola_cp1(corsa):
    cod = _codici(corsa["viol"]["bugiarda"])
    assert "CP1" in cod and "CP3" in cod, corsa["viol"]["bugiarda"]


def test_una_chiusura_sopra_una_viva_e_un_loop_cp4(corsa):
    assert corsa["a_vivo_prima_della_seconda"]
    cp4 = [v for v in corsa["viol"]["onesta"] if v[0] == "CP4"]
    assert cp4 and "VIVA" in cp4[0][2], corsa["viol"]["onesta"]


def test_le_violazioni_escono_una_volta_sola(corsa):
    cod = _codici(corsa["viol"]["sul_chiesto"])
    assert cod.count("CP2") == 1
    cod_b = _codici(corsa["viol"]["bugiarda"])
    assert cod_b.count("CP1") == 1 and cod_b.count("CP3") == 1


# ---------------------------------------------------------------------------
# 3. pezzi puri
# ---------------------------------------------------------------------------
def test_il_libro_assottigliato_tronca_solo_il_lato_che_abbina():
    class _Ex:
        available_to_back = [{"price": 2.0, "size": 5.0}, {"price": 1.98, "size": 9.0}]
        available_to_lay = [{"price": 2.02, "size": 7.0}]

    class _Runner:
        selection_id = 11
        handicap = 0.0
        status = "ACTIVE"
        ex = _Ex()

    class _Libro:
        runners = [_Runner()]
        status = "OPEN"

    v = CP.libro_assottigliato(_Libro(), 11, 0.0, "BACK", 6.5)
    assert v.status == "OPEN"
    assert v.runners[0].ex.available_to_back == [{"price": 2.0, "size": 5.0},
                                                 {"price": 1.98, "size": 1.5}]
    assert v.runners[0].ex.available_to_lay == [{"price": 2.02, "size": 7.0}]
    assert v.runners[0].selection_id == 11


def test_fok_si_riconosce_dall_istruzione_vera():
    assert CP._e_fok({"limitOrder": {"timeInForce": "FILL_OR_KILL", "minFillSize": None}})
    assert not CP._e_fok({"limitOrder": {"timeInForce": None}})
    # con `minFillSize` il FOK non e' piu' tutto-o-niente: non si tratta cosi'
    assert not CP._e_fok({"limitOrder": {"timeInForce": "FILL_OR_KILL", "minFillSize": 1.0}})


def test_ruolo_da_righe_legge_closes_trade_id_dal_ref():
    righe = [{"id": 7, "closes_trade_id": None, "meta": {}},
             {"id": 8, "closes_trade_id": 7, "meta": {"cashout": True}}]
    ruolo = CP.ruolo_da_righe(lambda: righe)

    class _O:
        def __init__(self, ref):
            self.notes = {"bot_ref": ref}
            self.customer_order_ref = None

    assert ruolo(_O("safe-t7")) == "ingresso"
    assert ruolo(_O("omega-t8")) == "uscita"
    assert ruolo(_O("mike-t99")) is None
    assert ruolo(_O("utente-1")) is None


def test_credenze_da_righe_hanno_le_chiavi_dello_schema_vero():
    ap = {"id": 1, "market_id": "1.2", "selection_id": 5, "side": "lay", "price": 3.0,
          "size": 10.0, "status": "hedged", "bet_id": "b1", "closes_trade_id": None,
          "meta": {"hedged_size": 4.17}}
    ch = {"id": 2, "market_id": "1.2", "selection_id": 5, "side": "back", "price": 2.5,
          "size": 12.0, "status": "open", "bet_id": "b2", "closes_trade_id": 1,
          "size_matched": 5.0, "size_remaining": 0.0, "avg_price_matched": 2.5,
          "meta": {"cashout": True, "closes_trade_id": 1}}
    cr = CP.credenze_da_righe([ap, ch])
    assert len(cr) == 1
    c = cr[0]
    assert c["chiave"] == ("1.2", 5) and c["chiusa"] is True and c["coperto"] == 4.17
    assert c["chiusure"][0]["bet_id"] == "b2"
    assert c["chiusure"][0]["size_matched"] == 5.0


def test_lo_scenario_esiste_in_tutte_e_cinque_le_liste():
    from Betfair.mike.tools import replay_registrazioni as MIKE
    from Betfair.omega.tools import replay_registrazioni as OMEGA
    from Betfair.safe_strategy.tools import replay_registrazioni as SAFE
    from Betfair.safe_strategy.tools import replay_tennis as SAFE_T
    from Betfair.stream.tennis_live.tools import replay_bot as TENNIS

    for mod in (MIKE, OMEGA, SAFE, SAFE_T, TENNIS):
        assert CP.SCENARIO in mod.SCENARI_DESCRITTI, mod.__name__


def test_senza_guasto_il_motore_non_tocca_i_pacchetti():
    class _Quadro:
        handler_queue: list = []

    m = B.MotoreReplay(_Quadro())
    assert m.guasto_chiusure is None
    m._prepara_pacchi([object()])      # nessun guasto: nessun effetto, nessun errore
