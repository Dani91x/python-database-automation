"""Nucleo UNICO del place-and-trim (17/09/2026, reperto 25).

Copre: scelta del percorso (A = parcheggio alla quota target senza replace,
B = parcheggio lontano + replace), lettura dei report Betfair ANNIDATI
(il motivo VERO di un CANCELLED_NOT_PLACED), e il fatto che la macchina a
stati flumine e il percorso REST usino LO STESSO nucleo.

I finti hanno le IDENTICHE chiavi del vero: ``instructionReports``,
``placeInstructionReport``, ``cancelInstructionReport``, ``errorCode``,
``betId``, ``sizeMatched``, ``sizeCancelled``, ``status``, ``orderStatus``.
"""
from __future__ import annotations

import pytest

from Betfair.stream.trading import submin as S


# ---------------------------------------------------------------------------
# quota_non_abbinabile
# ---------------------------------------------------------------------------
def test_back_sopra_il_best_non_e_abbinabile():
    # BACK a 5.9 mentre il meglio disponibile per bancare e' 5.4: resta a riposo.
    assert S.quota_non_abbinabile("back", 5.9, best_back=5.4, best_lay=6.0) is True


def test_back_sotto_o_al_best_e_abbinabile():
    # E' il caso di Mike: la copertura si piazza SOTTO il best -> aggressiva.
    assert S.quota_non_abbinabile("back", 5.4, best_back=5.9, best_lay=6.0) is False
    assert S.quota_non_abbinabile("back", 5.9, best_back=5.9, best_lay=6.0) is False


def test_lay_sotto_il_best_non_e_abbinabile():
    assert S.quota_non_abbinabile("lay", 2.0, best_back=1.9, best_lay=2.1) is True
    assert S.quota_non_abbinabile("lay", 2.1, best_back=1.9, best_lay=2.1) is False


def test_book_ignoto_torna_none():
    assert S.quota_non_abbinabile("back", 5.9) is None
    assert S.quota_non_abbinabile("lay", 2.0) is None


# ---------------------------------------------------------------------------
# pianifica_submin
# ---------------------------------------------------------------------------
def test_percorso_a_quando_la_quota_non_e_abbinabile():
    p = S.pianifica_submin(side="back", target_price=5.9, target_size=0.79,
                           jurisdiction="it", best_back=5.4, best_lay=6.0)
    assert p.serve_trucco is True
    assert p.park_mode == S.PARK_TARGET
    assert p.park_price == 5.9          # parcheggio ALLA quota target
    assert p.park_size == 2.00          # minimo .it BACK
    assert p.size_reduction == 1.21
    assert p.serve_replace is False     # <- niente replace, niente CANCELLED_NOT_PLACED
    assert p.chiamate_mutanti == 2


def test_percorso_b_quando_la_quota_e_abbinabile():
    # Il caso REALE di Mike il 17/09: copertura aggressiva sotto il best back.
    p = S.pianifica_submin(side="back", target_price=5.4, target_size=1.21,
                           jurisdiction="it", best_back=5.9, best_lay=6.0)
    assert p.park_mode == S.PARK_FAR
    assert p.park_price == 1000.0
    assert p.serve_replace is True
    assert p.chiamate_mutanti == 3


def test_book_ignoto_sceglie_il_percorso_conservativo():
    p = S.pianifica_submin(side="back", target_price=5.9, target_size=0.79,
                           jurisdiction="it")
    assert p.park_mode == S.PARK_FAR and p.serve_replace is True


def test_replace_non_consentito_rifiuta_senza_piazzare():
    p = S.pianifica_submin(side="back", target_price=5.4, target_size=1.21,
                           jurisdiction="it", best_back=5.9,
                           consenti_replace=False)
    assert p.rifiuto and p.rifiuto.startswith("SUBMIN_REPLACE_VIETATO")
    assert p.chiamate_mutanti == 0


def test_sopra_il_minimo_nessun_trucco():
    p = S.pianifica_submin(side="back", target_price=5.4, target_size=2.50,
                           jurisdiction="it", best_back=5.9)
    assert p.serve_trucco is False and p.chiamate_mutanti == 1


def test_lay_percorso_a():
    p = S.pianifica_submin(side="lay", target_price=2.00, target_size=0.20,
                           jurisdiction="it", best_back=1.9, best_lay=2.1)
    assert p.park_mode == S.PARK_TARGET and p.park_size == 0.50
    assert p.size_reduction == 0.30 and p.serve_replace is False


def test_sotto_il_floor_assoluto_solleva():
    with pytest.raises(ValueError):
        S.pianifica_submin(side="back", target_price=5.9, target_size=0.001,
                           jurisdiction="it", best_back=5.4)


# ---------------------------------------------------------------------------
# Report Betfair: esterno E INTERNO
# ---------------------------------------------------------------------------
_REPLACE_RIFIUTATO = {
    "status": "SUCCESS",
    "marketId": "1.123456789",
    "instructionReports": [{
        "status": "FAILURE",
        "errorCode": "CANCELLED_NOT_PLACED",
        "cancelInstructionReport": {
            "status": "SUCCESS",
            "sizeCancelled": 1.21,
            "cancelledDate": "2026-09-17T16:03:52.000Z",
        },
        "placeInstructionReport": {
            "status": "FAILURE",
            "errorCode": "INVALID_BET_SIZE",
            "orderStatus": None,
        },
    }],
}


def test_esito_istruzione_legge_anche_il_report_interno():
    e = S.esito_istruzione(_REPLACE_RIFIUTATO)
    assert e["error_code"] == "CANCELLED_NOT_PLACED"       # esterno
    assert e["place_error_code"] == "INVALID_BET_SIZE"     # INTERNO: il motivo vero
    assert e["cancel_status"] == "SUCCESS"
    assert e["size_cancelled"] == 1.21


def test_codice_rifiuto_unisce_esterno_e_interno():
    e = S.esito_istruzione(_REPLACE_RIFIUTATO)
    assert S.codice_rifiuto(e) == "CANCELLED_NOT_PLACED:INVALID_BET_SIZE"


def test_esito_istruzione_su_place_riuscito():
    rep = {
        "status": "SUCCESS",
        "instructionReports": [{
            "status": "SUCCESS",
            "betId": "443221432246",
            "orderStatus": "EXECUTABLE",
            "sizeMatched": 0.0,
            "placedDate": "2026-09-17T16:03:52.000Z",
        }],
    }
    e = S.esito_istruzione(rep)
    assert e["bet_id"] == "443221432246"
    assert e["size_matched"] == 0.0
    assert e["order_status"] == "EXECUTABLE"
    assert S.codice_rifiuto(e) is None


def test_esito_istruzione_su_report_vuoto_non_esplode():
    e = S.esito_istruzione(None)
    assert e["error_code"] is None and e["size_matched"] == 0.0


# ---------------------------------------------------------------------------
# La macchina a stati flumine passa dallo STESSO nucleo
# ---------------------------------------------------------------------------
class _OpsFinte:
    def __init__(self):
        self.chiamate = []

    def place(self, market, *, side, price, size, customer_order_ref):
        self.chiamate.append(("place", side, price, size))
        return _OrdineFinto(bet_id="1", price=price, size_remaining=size)

    def cancel(self, market, order, size_reduction):
        self.chiamate.append(("cancel", size_reduction))

    def replace(self, market, order, new_price):
        self.chiamate.append(("replace", new_price))


class _OrdineFinto:
    def __init__(self, bet_id=None, price=None, size_remaining=None,
                 size_matched=0.0, status="EXECUTABLE"):
        self.bet_id = bet_id
        self.size_matched = size_matched
        self.size_remaining = size_remaining
        self.status = status
        self.side = "back"
        self.order_type = type("OT", (), {"price": price, "size": size_remaining})()


def test_start_submin_percorso_a_parcheggia_alla_quota_target():
    st = S.start_submin(side="back", target_price=5.9, target_size=0.79,
                        jurisdiction="it", best_back=5.4, best_lay=6.0)
    assert st.park_price == 5.9 and st.serve_replace is False
    assert st.prezzo_parcheggio == 5.9


def test_start_submin_senza_book_resta_al_comportamento_storico():
    st = S.start_submin(side="back", target_price=5.4, target_size=1.21,
                        jurisdiction="it")
    assert st.serve_replace is True
    assert st.prezzo_parcheggio == 1000.0


def test_macchina_percorso_a_non_chiama_mai_replace():
    ops = _OpsFinte()
    st = S.start_submin(side="back", target_price=5.9, target_size=0.79,
                        jurisdiction="it", best_back=5.4, best_lay=6.0)
    # step1: place alla quota TARGET
    st = S.advance_submin(object(), st, order=None, jurisdiction="it",
                          customer_order_ref="ref", ops=ops)
    assert st.step == S.SubminStep.PLACED
    assert ops.chiamate[0] == ("place", "back", 5.9, 2.00)
    # step2: cancel parziale, poi osservazione del residuo al target
    ord_park = _OrdineFinto(bet_id="1", price=5.9, size_remaining=2.00)
    st = S.advance_submin(object(), st, order=ord_park, jurisdiction="it",
                          customer_order_ref="ref", ops=ops, now_ms=1_000)
    assert ("cancel", 1.21) in ops.chiamate
    ord_trim = _OrdineFinto(bet_id="1", price=5.9, size_remaining=0.79)
    st = S.advance_submin(object(), st, order=ord_trim, jurisdiction="it",
                          customer_order_ref="ref", ops=ops, now_ms=2_000)
    assert st.step == S.SubminStep.TRIMMED
    # step3: NESSUN replace, si passa diretti a REPRICED
    st = S.advance_submin(object(), st, order=ord_trim, jurisdiction="it",
                          customer_order_ref="ref", ops=ops, now_ms=3_000)
    assert st.step == S.SubminStep.REPRICED
    assert not any(c[0] == "replace" for c in ops.chiamate)
    st = S.advance_submin(object(), st, order=ord_trim, jurisdiction="it",
                          customer_order_ref="ref", ops=ops, now_ms=4_000)
    assert st.step == S.SubminStep.DONE


def test_macchina_percorso_b_chiama_il_replace():
    ops = _OpsFinte()
    st = S.start_submin(side="back", target_price=5.4, target_size=1.21,
                        jurisdiction="it", best_back=5.9, best_lay=6.0)
    st = S.advance_submin(object(), st, order=None, jurisdiction="it",
                          customer_order_ref="ref", ops=ops)
    assert ops.chiamate[0] == ("place", "back", 1000.0, 2.00)
    ord_trim = _OrdineFinto(bet_id="1", price=1000.0, size_remaining=1.21)
    st = S.advance_submin(object(), st, order=ord_trim, jurisdiction="it",
                          customer_order_ref="ref", ops=ops, now_ms=1_000)
    assert st.step == S.SubminStep.TRIMMED
    st = S.advance_submin(object(), st, order=ord_trim, jurisdiction="it",
                          customer_order_ref="ref", ops=ops, now_ms=2_000)
    assert ("replace", 5.4) in ops.chiamate
    assert st.step == S.SubminStep.REPRICED


# ---------------------------------------------------------------------------
# "Il parcheggio non espone mai piu' del cap" (17/09, money-critical)
# ---------------------------------------------------------------------------
def test_liability_del_parcheggio_lay_alla_quota_target():
    # 2,00 EUR di parcheggio a quota 95 impegnano 188,00 EUR fino al taglio.
    assert S.liability_parcheggio("lay", 95.0, 2.00) == 188.00
    assert S.liability_parcheggio("lay", 1.01, 0.50) == 0.01
    assert S.liability_parcheggio("back", 95.0, 2.00) == 2.00


def test_lay_percorso_a_vietato_se_il_parcheggio_sfonda_il_cap():
    # LAY a 95: percorso A impegnerebbe 0,50*(95-1) = 47,00 EUR, cap 10,00.
    p = S.pianifica_submin(side="lay", target_price=95.0, target_size=0.20,
                           jurisdiction="it", best_back=90.0, best_lay=100.0,
                           max_stake=10.0)
    assert p.park_mode == S.PARK_FAR and p.park_price == 1.01
    assert p.serve_replace is True
    assert "oltre il cap" in p.motivo


def test_cap_sfondato_e_replace_vietato_rifiuta_senza_piazzare():
    p = S.pianifica_submin(side="lay", target_price=95.0, target_size=0.20,
                           jurisdiction="it", best_back=90.0, best_lay=100.0,
                           max_stake=10.0, consenti_replace=False)
    assert p.rifiuto and p.rifiuto.startswith("SUBMIN_CAP_PARCHEGGIO")
    assert p.chiamate_mutanti == 0


def test_cap_capiente_lascia_il_percorso_a():
    p = S.pianifica_submin(side="lay", target_price=2.00, target_size=0.20,
                           jurisdiction="it", best_back=1.9, best_lay=2.1,
                           max_stake=10.0)
    assert p.park_mode == S.PARK_TARGET and p.serve_replace is False


def test_guardia_cap_parcheggio_solleva():
    with pytest.raises(ValueError, match="oltre il cap"):
        S.guardia_cap_parcheggio("lay", 95.0, 2.00, 10.0)
    # cap ignoto non blocca; BACK non e' mai a rischio liability
    S.guardia_cap_parcheggio("lay", 95.0, 2.00, None)
    S.guardia_cap_parcheggio("back", 1000.0, 2.00, 10.0)


def test_la_macchina_flumine_ri_valida_il_cap_al_place():
    class _OpsCap(_OpsFinte):
        max_stake = 10.0

    ops = _OpsCap()
    st = S.start_submin(side="lay", target_price=95.0, target_size=0.20,
                        jurisdiction="it", best_back=90.0, best_lay=100.0)
    # senza cap il piano sceglie il percorso A: la guardia deve fermare il place
    assert st.park_price == 95.0
    with pytest.raises(ValueError, match="oltre il cap"):
        S.advance_submin(object(), st, order=None, jurisdiction="it",
                         customer_order_ref="ref", ops=ops)
    assert ops.chiamate == []
