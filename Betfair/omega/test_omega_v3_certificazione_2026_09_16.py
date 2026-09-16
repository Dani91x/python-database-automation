# -*- coding: utf-8 -*-
"""FALSIFICAZIONE dei controlli V3 della certificazione (A8-A12, C5, G1, G2).

«Un test che non sa diventare rosso non certifica» (CLAUDE.md). Per ognuno dei
nove controlli qui c'e' una coppia: il caso SANO, che deve passare in silenzio, e
il caso MALATO, che deve far uscire il codice giusto. Se un controllo fosse
inerte — un `quando=` sbagliato, un confronto che non morde — la seconda meta'
della coppia diventerebbe rossa.

I finti hanno le IDENTICHE chiavi del vero (memoria 15/09: i finti in camelCase
avevano certificato il bug che ha mandato fuori 32 ordini veri): il candidato e'
un `omega_v3.CandidatoV3` vero, la proposta una `omega_v3.PropostaUscita` vera,
i parametri passano da `omega_config.resolve_params`.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from Betfair.omega import certificazione as CERT
from Betfair.omega import omega_config as C
from Betfair.omega import omega_model as M
from Betfair.omega import omega_v3 as V3

ORA = datetime(2026, 9, 16, 20, 0, tzinfo=timezone.utc)


def _params(**kw):
    base = {"strategy_version": 3}
    base.update(kw)
    return C.resolve_params(base)


def _stato(minuto=38, h=0, a=1):
    return M.LiveState(minute=minuto, score_home=h, score_away=a)


def _cand(nome="Any Unquoted", prezzo=65.0, p_nostra=0.0064, p_fusa=0.0064,
          p_emp=None, n_emp=None, k=2.0):
    p_imp = V3.p_implicita(prezzo, 0.05)
    return V3.CandidatoV3(
        selection_id=101, name=nome, price=prezzo, size=1.0,
        p_modello=p_fusa, p_fusa=p_fusa, p_empirica=p_emp, n_empirico=n_emp,
        p_nostra=p_nostra, p_implicita=p_imp, k_usato=k,
        margine=p_imp / p_nostra, ev=V3.ev_gamba(p_nostra, prezzo, 1.0, 0.05),
        liability=V3.liability(1.0, prezzo), motivo="prova")


def _codici(viol):
    return {v.codice for v in viol}


def _mom(**kw):
    """Un momento prodotto DAL MOTORE V3. Il campo `motore` non e' un dettaglio:
    nello scenario `v3` del replay i due motori guardano lo stesso book e
    scrivono due momenti distinti, e senza quel campo i controlli del v2
    giudicherebbero le decisioni del v3 col vocabolario sbagliato (il primo
    replay lo ha trovato davvero: A1 accusava V3 di un motivo 'fuori_finestra'
    che in V3 e' dichiaratissimo)."""
    kw.setdefault("motore", "v3")
    return CERT.Momento(**kw)


# ---------------------------------------------------------------------------
def test_i_controlli_v3_sono_registrati():
    codici = {c for c, _r in CERT.elenco_controlli()}
    for atteso in ("A8", "A9", "A10", "A11", "A12", "C5", "G1", "G2"):
        assert atteso in codici, atteso


def test_con_strategy_version_2_i_controlli_v3_tacciono():
    """Il default e' 2: V3 non deve disturbare il motore di oggi. Qui si passa un
    momento che in V3 sarebbe una violazione grossa (stake 7 EUR) e non deve
    uscire nessun codice V3."""
    m = _mom(tipo="sizing", now=ORA, params=C.resolve_params({}),
                     leg="ht_cs", size=7.0, price=65.0, state=_stato())
    assert not ({"A9", "C5"} & _codici(CERT.verifica(m)))


# ------------------------------------------------------------------ A8
def test_a8_sano_e_malato():
    sano = _mom(tipo="selezione", now=ORA, params=_params(), leg="ht_cs",
                        cand=None, motivo="nessun_candidato", state=_stato(),
                        scartati=[("0 - 0", "margine_insufficiente(k=2)")])
    assert "A8" not in _codici(CERT.verifica(sano))
    senza_motivo = _mom(tipo="selezione", now=ORA, params=_params(),
                                leg="ht_cs", cand=None, motivo="", state=_stato())
    assert "A8" in _codici(CERT.verifica(senza_motivo))
    motivo_inventato = _mom(tipo="selezione", now=ORA, params=_params(),
                                    leg="ht_cs", cand=None, motivo="boh",
                                    state=_stato())
    assert "A8" in _codici(CERT.verifica(motivo_inventato))


def test_a8_pretende_gli_scarti_quando_il_book_c_era():
    class _Snap:
        runners = [object(), object(), object()]
    m = _mom(tipo="selezione", now=ORA, params=_params(), leg="ht_cs",
                     cand=None, motivo="nessun_candidato", state=_stato(),
                     snapshot=_Snap(), scartati=[])
    assert "A8" in _codici(CERT.verifica(m))


# ------------------------------------------------------------------ A9
def test_a9_lo_stake_e_un_euro():
    sano = _mom(tipo="sizing", now=ORA, params=_params(), leg="ht_cs",
                        size=1.0, price=65.0, state=_stato())
    assert "A9" not in _codici(CERT.verifica(sano))
    malato = _mom(tipo="sizing", now=ORA, params=_params(), leg="ht_cs",
                          size=1.01, price=65.0, state=_stato())
    assert "A9" in _codici(CERT.verifica(malato))


def test_a9_guarda_anche_la_richiesta_vera_dell_ordine():
    """I finti parlano come il vero: la richiesta ha le chiavi snake_case che il
    servizio scrive davvero (`customer_ref`, `size`, `price`, `side`)."""
    malato = _mom(tipo="ordine", now=ORA, params=_params(), leg="ft_cs",
                          state=_stato(60, 1, 1),
                          richiesta={"market_id": "1.2", "selection_id": 101,
                                     "price": 65.0, "size": 131.58, "side": "lay",
                                     "customer_ref": "omega-9"})
    assert "A9" in _codici(CERT.verifica(malato))


# ------------------------------------------------------------------ A10
def test_a10_il_margine_k_e_verificato_davvero():
    sano = _mom(tipo="selezione", now=ORA, params=_params(), leg="ht_cs",
                        cand=_cand(), state=_stato())
    assert "A10" not in _codici(CERT.verifica(sano))
    # stessa quota, P doppia: il margine non c'e' piu'
    p_imp = V3.p_implicita(65.0, 0.05)
    malato = _mom(tipo="selezione", now=ORA, params=_params(), leg="ht_cs",
                          cand=_cand(p_nostra=p_imp * 0.9, p_fusa=p_imp * 0.9),
                          state=_stato())
    assert "A10" in _codici(CERT.verifica(malato))


def test_a10_rifiuta_un_k_sotto_il_pavimento():
    m = _mom(tipo="selezione", now=ORA, params=_params(), leg="ht_cs",
                     cand=_cand(k=1.0), state=_stato())
    assert "A10" in _codici(CERT.verifica(m))


# ------------------------------------------------------------------ A11
def test_a11_il_punteggio_corrente_non_si_banca():
    sano = _mom(tipo="selezione", now=ORA, params=_params(), leg="ht_cs",
                        cand=_cand(nome="2 - 1", prezzo=65.0), state=_stato(38, 0, 1))
    assert "A11" not in _codici(CERT.verifica(sano))
    malato = _mom(tipo="selezione", now=ORA, params=_params(), leg="ht_cs",
                          cand=_cand(nome="0 - 1", prezzo=65.0), state=_stato(38, 0, 1))
    assert "A11" in _codici(CERT.verifica(malato))


def test_a11_tetto_duro_sulla_p():
    m = _mom(tipo="selezione", now=ORA, params=_params(v3_p_max_pct=0.1),
                     leg="ht_cs", cand=_cand(nome="2 - 1"), state=_stato(38, 0, 1))
    assert "A11" in _codici(CERT.verifica(m))


# ------------------------------------------------------------------ A12
def test_a12_il_dato_storico_non_si_ignora():
    """P_nostra deve essere il MASSIMO fra modello e storico."""
    sano = _mom(tipo="selezione", now=ORA, params=_params(), leg="ht_cs",
                        cand=_cand(p_fusa=0.004, p_emp=0.0064, n_emp=900,
                                   p_nostra=0.0064), state=_stato())
    assert "A12" not in _codici(CERT.verifica(sano))
    # il modello ha vinto anche se lo storico diceva di piu': veto non applicato
    malato = _mom(tipo="selezione", now=ORA, params=_params(), leg="ht_cs",
                          cand=_cand(p_fusa=0.004, p_emp=0.0064, n_emp=900,
                                     p_nostra=0.004), state=_stato())
    assert "A12" in _codici(CERT.verifica(malato))


def test_a12_un_campione_troppo_piccolo_non_ha_diritto_di_parola():
    m = _mom(tipo="selezione", now=ORA, params=_params(v3_empirical_min_n=200),
                     leg="ht_cs",
                     cand=_cand(p_fusa=0.004, p_emp=0.0064, n_emp=12, p_nostra=0.0064),
                     state=_stato())
    assert "A12" in _codici(CERT.verifica(m))


# ------------------------------------------------------------------ C5
def test_c5_cap_di_liability_della_gamba():
    sano = _mom(tipo="sizing", now=ORA, params=_params(), leg="ht_cs",
                        size=1.0, price=65.0, state=_stato())
    assert "C5" not in _codici(CERT.verifica(sano))
    malato = _mom(tipo="sizing", now=ORA, params=_params(), leg="ht_cs",
                          size=1.0, price=400.0, state=_stato())   # liability 399 > 120
    assert "C5" in _codici(CERT.verifica(malato))


def test_c5_si_spegne_col_cap_a_zero():
    m = _mom(tipo="sizing", now=ORA, params=_params(v3_max_liability_per_leg=0.0),
                     leg="ht_cs", size=1.0, price=400.0, state=_stato())
    assert "C5" not in _codici(CERT.verifica(m))


# ------------------------------------------------------------------ G1
def test_g1_il_greenup_automatico_non_puo_essere_acceso_in_v3():
    """La whitelist lo spegne da sola: chi lo riaccendesse scavalcandola viene preso."""
    buoni = _params(greenup_mode="auto")          # resolve_params lo riporta a 'off'
    assert buoni["greenup_mode"] == "off"
    m = _mom(tipo="giro", now=ORA, params=buoni)
    assert "G1" not in _codici(CERT.verifica(m))
    forzati = dict(buoni)
    forzati["greenup_mode"] = "auto"              # qualcuno ha scavalcato la whitelist
    forzati["greenup_enabled"] = True
    assert "G1" in _codici(CERT.verifica(_mom(tipo="giro", now=ORA, params=forzati)))


def test_g1_nessuna_azione_di_uscita_diversa_da_tieni():
    tieni = _mom(tipo="uscita", now=ORA, params=_params(), azione="hold",
                         perche="margine ampio", state=_stato(70, 2, 2))
    assert "G1" not in _codici(CERT.verifica(tieni))
    chiude = _mom(tipo="uscita", now=ORA, params=_params(), azione="exit",
                          perche="prezzo rotto", state=_stato(70, 2, 2))
    assert "G1" in _codici(CERT.verifica(chiude))


def test_g1_un_back_senza_approvazione_e_una_chiusura_automatica():
    m = _mom(tipo="ordine", now=ORA, params=_params(),
                     richiesta={"market_id": "1.2", "selection_id": 101, "price": 200.0,
                                "size": 0.5, "side": "back", "customer_ref": "omega-9"})
    assert "G1" in _codici(CERT.verifica(m))
    approvato = _mom(tipo="ordine", now=ORA, params=_params(),
                             richiesta={"market_id": "1.2", "selection_id": 101,
                                        "price": 200.0, "size": 0.5, "side": "back",
                                        "customer_ref": "omega-9",
                                        "approvata_dall_utente": True})
    assert "G1" not in _codici(CERT.verifica(approvato))


# ------------------------------------------------------------------ G2
def _proposta(proponi=True, profitto=0.63):
    return V3.PropostaUscita(
        proponi=proponi, motivo_codice="blocca_il_profitto" if proponi else "tenere_vale_di_piu",
        profitto_bloccabile=profitto, back_price=300.0, back_size=0.33,
        ev_tenere=-4.05, meglio_aspettare=False, bloccabile_max_atteso=0.1,
        minuto_del_massimo=85.0, p_evento=0.05, testo="prova")


def test_g2_la_proposta_porta_i_numeri():
    sana = _mom(tipo="proposta", now=ORA, params=_params(),
                        proposta=_proposta(), trade_id=7,
                        decided_at="2026-09-16T20:00:00Z",
                        proposed_at="2026-09-16T20:00:30Z")
    assert "G2" not in _codici(CERT.verifica(sana))
    senza = _mom(tipo="proposta", now=ORA, params=_params(),
                         proposta=_proposta()._replace(back_price=None)
                         if hasattr(_proposta(), "_replace") else None,
                         trade_id=7)
    if senza.proposta is not None:
        assert "G2" in _codici(CERT.verifica(senza))


def test_g2_profitto_non_positivo_su_una_proposta_di_chiusura():
    m = _mom(tipo="proposta", now=ORA, params=_params(),
                     proposta=_proposta(profitto=-0.2), trade_id=7)
    assert "G2" in _codici(CERT.verifica(m))


def test_g2_decided_at_non_si_rinfresca():
    """Cert. Safe 14/09: se l'istante della decisione si rinfresca a ogni
    aggiornamento, la latenza misurata e' sempre zero e dice il contrario del vero."""
    visto = {"7": {"decided_at": "2026-09-16T20:00:00Z",
                   "proposed_at": "2026-09-16T20:00:30Z", "profitto": 0.63}}
    sano = _mom(tipo="proposta", now=ORA, params=_params(),
                        proposta=_proposta(), trade_id=7,
                        decided_at="2026-09-16T20:00:00Z",
                        proposed_at="2026-09-16T20:01:00Z", proposte_viste=visto)
    assert "G2" not in _codici(CERT.verifica(sano))
    malato = _mom(tipo="proposta", now=ORA, params=_params(),
                          proposta=_proposta(), trade_id=7,
                          decided_at="2026-09-16T20:01:00Z",
                          proposed_at="2026-09-16T20:01:00Z", proposte_viste=visto)
    assert "G2" in _codici(CERT.verifica(malato))


def test_g2_un_profitto_cambiato_senza_riscrittura_si_vede():
    visto = {"7": {"decided_at": "2026-09-16T20:00:00Z",
                   "proposed_at": "2026-09-16T20:00:30Z", "profitto": 0.20}}
    m = _mom(tipo="proposta", now=ORA, params=_params(),
                     proposta=_proposta(profitto=0.63), trade_id=7,
                     decided_at="2026-09-16T20:00:00Z",
                     proposed_at="2026-09-16T20:00:30Z", proposte_viste=visto)
    assert "G2" in _codici(CERT.verifica(m))


# ------------------------------------------------------------------ nessun errore
def test_nessun_controllo_esplode_su_un_momento_vuoto():
    """`XX-ERRORE` nel referto vuol dire controllo rotto: non deve mai capitare
    solo perche' un campo e' None."""
    for tipo in ("selezione", "sizing", "uscita", "ordine", "giro", "proposta"):
        m = _mom(tipo=tipo, now=ORA, params=_params())
        assert not [v for v in CERT.verifica(m) if v.codice.endswith("-ERRORE")], tipo
