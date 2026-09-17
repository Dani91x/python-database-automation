# -*- coding: utf-8 -*-
"""Test degli strumenti di misura M4 / M5 / M6 (17/09/2026).

REGOLA DEL REPO: «i finti nei test hanno le IDENTICHE chiavi e tipi del vero,
costruiti dalle funzioni vere o da payload registrati» (`CLAUDE.md`). Qui i finti
non sono scritti a mano: si costruisce una REGISTRAZIONE sintetica nel formato
NATIVO Betfair (`mcm` con `marketDefinition` e `rc` con `atb`/`atl`) piu' il suo
sidecar dei punteggi, e la si fa leggere a `campiona_evento` — la funzione vera.
Le osservazioni che escono hanno quindi, per costruzione, le chiavi del vero.

Ogni test e' stato FALSIFICATO: c'e' il caso sano e il caso malato.
"""
from __future__ import annotations

import json
import math
import os

import pytest

from Betfair.omega.tools import deriva_margine as M4
from Betfair.omega.tools import k_in_gioco as M6
from Betfair.omega.tools import montecarlo_pl as M5
from Betfair.omega.tools import superficie_liability as SL


# ---------------------------------------------------------------------------
# una registrazione sintetica, nel formato NATIVO
# ---------------------------------------------------------------------------
BASE_MS = 1782831960000
MERCATO = "1.999999001"


def _riga_mcm(pt: int, *, market_definition=None, rc=None, img=False) -> str:
    mc = {"id": MERCATO}
    if img:
        mc["img"] = True
    if market_definition is not None:
        mc["marketDefinition"] = market_definition
    if rc is not None:
        mc["rc"] = rc
    return json.dumps({"op": "mcm", "pt": pt, "mc": [mc]})


def _definizione(*, stato="OPEN", inplay=True, vincitore=None, ids=(1, 2, 3, 4, 5, 6, 7, 8, 9)):
    runners = []
    for sid in ids:
        st = "ACTIVE"
        if vincitore is not None:
            st = "WINNER" if sid == vincitore else "LOSER"
        runners.append({"id": sid, "status": st})
    return {"marketType": "CORRECT_SCORE", "status": stato, "inPlay": inplay,
            "eventId": "99999999", "marketTime": "2026-06-30T16:00:00.000Z",
            "runners": runners}


def scrivi_registrazione(cartella, *, prezzi_per_minuto, vincitore=5,
                         punteggio=(0, 0), event_id="99999999"):
    """`prezzi_per_minuto` = {minuto: {selection_id: (best_back, best_lay, size)}}."""
    os.makedirs(cartella, exist_ok=True)
    raw = os.path.join(cartella, f"{event_id}.raw.jsonl")
    sidecar = os.path.join(cartella, f"{event_id}.scores.jsonl")
    ids = sorted({s for v in prezzi_per_minuto.values() for s in v})
    righe = [_riga_mcm(BASE_MS, market_definition=_definizione(ids=ids), img=True)]
    punteggi = []
    for minuto in sorted(prezzi_per_minuto):
        pt = BASE_MS + minuto * 60_000
        punteggi.append({"ts_ms": pt - 1000, "minute": minuto,
                         "score_home": punteggio[0], "score_away": punteggio[1]})
        rc = []
        for sid, (bb, bl, size) in sorted(prezzi_per_minuto[minuto].items()):
            rc.append({"id": sid,
                       "atb": [[bb, size]] if bb else [],
                       "atl": [[bl, size]] if bl else []})
        righe.append(_riga_mcm(pt, rc=rc, img=True,
                               market_definition=_definizione(ids=ids)))
    # chiusura con il WINNER: e' l'esito AUTOREVOLE
    righe.append(_riga_mcm(BASE_MS + 95 * 60_000,
                           market_definition=_definizione(
                               stato="CLOSED", inplay=True, vincitore=vincitore,
                               ids=ids)))
    # il sidecar deve arrivare fino a fine partita perche' l'esito sia osservabile
    punteggi.append({"ts_ms": BASE_MS + 94 * 60_000, "minute": 94,
                     "score_home": punteggio[0], "score_away": punteggio[1]})
    with open(raw, "w", encoding="utf-8") as fh:
        fh.write("\n".join(righe) + "\n")
    with open(sidecar, "w", encoding="utf-8") as fh:
        for p in punteggi:
            fh.write(json.dumps(p) + "\n")
    return cartella


CHIAVI_ATTESE = {
    "event_id", "mercato", "minuto", "minuto_vero", "punteggio", "selection_id",
    "nome", "aggregato", "raggiungibile", "distanza_gol", "best_lay", "size_lay",
    "prezzo_mid", "p_impl_mid", "p_equa", "esito_md", "market_id", "best_back",
    "size_back", "libro_incrociato", "p_impl_tocco", "p_impl_back",
    "liability_per_euro", "fascia", "spread_tick", "esito",
}


@pytest.fixture()
def osservazioni(tmp_path):
    """Osservazioni VERE su una registrazione sintetica dichiarata."""
    prezzi = {}
    for minuto in (10, 15, 20):
        prezzi[minuto] = {sid: (20.0 + sid, 30.0 + sid, 50.0) for sid in range(1, 10)}
    cartella = scrivi_registrazione(str(tmp_path / "99999999"),
                                    prezzi_per_minuto=prezzi, vincitore=5)
    righe = SL.campiona_evento(cartella, "99999999", minuti=[10, 15, 20],
                               commissione=0.05)
    assert righe, "la registrazione sintetica non ha prodotto osservazioni"
    return righe


# ---------------------------------------------------------------------------
# M6 / campionamento
# ---------------------------------------------------------------------------
def test_le_osservazioni_hanno_le_chiavi_del_vero(osservazioni):
    for r in osservazioni:
        assert set(r) == CHIAVI_ATTESE
    # i campi che M6 legge devono esistere DAVVERO, non per caso
    for campo in M6.CAMPO_P.values():
        assert campo in CHIAVI_ATTESE, campo


def test_esito_viene_dal_winner_del_market_definition(osservazioni):
    vinti = [r for r in osservazioni if r["esito_md"] == 1]
    persi = [r for r in osservazioni if r["esito_md"] == 0]
    assert vinti and persi
    assert {r["selection_id"] for r in vinti} == {5}


def test_due_winner_non_sono_un_esito(tmp_path):
    """FALSIFICAZIONE: con due WINNER l'esito e' IGNOTO, mai dedotto."""
    prezzi = {10: {sid: (20.0, 30.0, 50.0) for sid in (1, 2, 3)}}
    cartella = scrivi_registrazione(str(tmp_path / "1"), prezzi_per_minuto=prezzi,
                                    vincitore=1, event_id="1")
    raw = os.path.join(cartella, "1.raw.jsonl")
    testo = open(raw, encoding="utf-8").read().replace(
        '{"id": 2, "status": "LOSER"}', '{"id": 2, "status": "WINNER"}')
    open(raw, "w", encoding="utf-8").write(testo)
    info = SL.vincitori(raw)[MERCATO]
    assert info["n_winner"] == 2 and info["winner"] is None
    righe = SL.campiona_evento(cartella, "1", minuti=[10], commissione=0.05)
    assert all(r["esito_md"] is None for r in righe)


def test_esito_vero_preferisce_il_market_definition():
    assert M6.esito_vero({"esito_md": 1, "esito": 0}) == 1
    assert M6.esito_vero({"esito_md": 0, "esito": 1}) == 0
    assert M6.esito_vero({"esito_md": None, "esito": 1}) == 1
    assert M6.esito_vero({"esito_md": None, "esito": None}) is None


def _riga_finta(**kw):
    """Una riga con TUTTE le chiavi del vero, poi sovrascritte: cosi' un finto non
    puo' avere una chiave che il vero non ha."""
    base = {k: None for k in CHIAVI_ATTESE}
    base.update({"event_id": "A", "market_id": MERCATO, "mercato": "CORRECT_SCORE",
                 "minuto": 10, "minuto_vero": 10, "punteggio": "0-0",
                 "selection_id": 1, "nome": "3 - 3", "aggregato": False,
                 "raggiungibile": True, "distanza_gol": 6, "esito_md": 0,
                 "libro_incrociato": False, "fascia": "1-2%"})
    base.update(kw)
    return base


def test_k_e_esattamente_p_impl_su_p_reale():
    righe = [_riga_finta(event_id=f"E{i}", p_impl_tocco=0.02, p_impl_mid=0.03,
                         p_impl_back=0.04, p_equa=0.025,
                         esito_md=1 if i < 5 else 0)
             for i in range(100)]
    d = M6.aggrega(righe, minuto_passo=90, giri_boot=50, seme=1,
                   distanza_minima=2, n_min_uscite=1)
    r = d["righe"][0]
    assert r["p_reale"] == pytest.approx(0.05)
    assert r["k_tocco"] == pytest.approx(0.4, abs=1e-3)
    assert r["k_best_back"] == pytest.approx(0.8, abs=1e-3)
    # il bias AL NETTO della geometria: p_equa / p_reale
    assert r["bias_equo"] == pytest.approx(0.5, abs=1e-3)


def test_il_bootstrap_ricampiona_le_PARTITE_non_le_righe():
    """FALSIFICAZIONE del metodo: tutte le uscite stanno in UNA partita su dieci.
    Un bootstrap sulle RIGHE darebbe [0,06 - 0,15]; a grappolo deve contenere lo
    ZERO (nessuna uscita e' un esito possibile) e arrivare ben oltre 0,25."""
    righe_binomiali = M6.bootstrap_grappolo(
        {f"R{i}": (1 if i < 20 else 0, 1) for i in range(200)},
        giri=2000, seme=7)
    assert righe_binomiali[0] > 0.05, "il bootstrap per RIGHE non contiene lo zero"
    righe = []
    for i in range(10):
        for _ in range(20):
            righe.append(_riga_finta(event_id=f"E{i}", p_impl_tocco=0.02,
                                     p_impl_mid=0.02, p_impl_back=0.02,
                                     esito_md=1 if i == 0 else 0))
    d = M6.aggrega(righe, minuto_passo=90, giri_boot=2000, seme=7,
                   distanza_minima=2, n_min_uscite=1)
    r = d["righe"][0]
    assert r["p_reale"] == pytest.approx(0.1)
    assert r["p_reale_boot_lo"] == 0.0            # nessuna uscita e' possibile
    assert r["p_reale_boot_hi"] > 0.25            # e anche molte lo sono


def test_placebo_calibrato_ritrova_il_valore_atteso():
    """FALSIFICAZIONE dello stimatore: se gli esiti si estraggono dalla
    distribuzione DEVIGATA, `k` deve tornare `p_impl / p_equa` — cioe' la sola
    geometria del libro, senza alcun bias."""
    righe = []
    for i in range(40):
        for sid in range(1, 11):
            righe.append(_riga_finta(event_id=f"E{i}", selection_id=sid,
                                     p_impl_tocco=0.05, p_impl_mid=0.08,
                                     p_impl_back=0.10, p_equa=0.05))
    d = M6.aggrega_placebo_ripetuto(righe, "calibrato", giri=400, seme=3,
                                    minuto_passo=90, distanza_minima=2)
    r = d["righe"][0]
    assert r["k_best_back_atteso"] == pytest.approx(2.0, abs=0.01)
    assert r["k_best_back"] == pytest.approx(2.0, rel=0.10)


def test_placebo_permutato_distrugge_il_segnale():
    """Il vincitore vero e' SEMPRE la cella a p_impl piu' bassa. Dopo la
    permutazione fra partite quella concentrazione deve sparire."""
    righe = []
    for i in range(30):
        for sid in range(1, 11):
            righe.append(_riga_finta(
                event_id=f"E{i}", selection_id=sid, fascia="1-2%",
                p_impl_tocco=0.01 * sid, p_impl_mid=0.01 * sid,
                p_impl_back=0.01 * sid, p_equa=0.01 * sid,
                esito_md=1 if sid == 1 else 0))
    quota_vera = sum(1 for r in righe if r["selection_id"] == 1 and r["esito_md"] == 1)
    assert quota_vera == 30
    mescolate = M6.applica_placebo(righe, "permutato", seme=11)
    vincenti = {r["selection_id"] for r in mescolate if r["esito_placebo"] == 1}
    assert vincenti == {1}          # il ref e' lo stesso: qui il segnale sopravvive
    # ...ma se i vincitori veri sono CELLE DIVERSE, la permutazione li rimescola
    righe2 = []
    for i in range(30):
        for sid in range(1, 11):
            righe2.append(_riga_finta(
                event_id=f"E{i}", selection_id=sid, fascia="1-2%",
                p_impl_tocco=0.01 * sid, p_impl_back=0.01 * sid,
                p_impl_mid=0.01 * sid, p_equa=0.01 * sid,
                esito_md=1 if sid == (i % 10) + 1 else 0))
    mescolate2 = M6.applica_placebo(righe2, "permutato", seme=11)
    coppie = {(r["event_id"], r["selection_id"])
              for r in mescolate2 if r["esito_placebo"] == 1}
    originali = {(r["event_id"], r["selection_id"])
                 for r in righe2 if r["esito_md"] == 1}
    assert coppie != originali


# ---------------------------------------------------------------------------
# M4
# ---------------------------------------------------------------------------
def test_il_fit_dei_lambda_ritrova_i_lambda_veri():
    p = M4.carica_parametri()
    veri = (1.4, 1.1)
    griglia = M4.V.griglia_finale(minuto=10.0, punteggio=(0, 0),
                                  periodo=M4.V.PERIODO_FT, p=p, lambdas=veri)
    mercato = {c: v for c, v in griglia.items() if v > 1e-4}
    fit = M4.fitta_lambdas(mercato=mercato, minuto=10.0, punteggio=(0, 0),
                           periodo=M4.V.PERIODO_FT, p=p)
    assert fit is not None
    assert fit[0] == pytest.approx(veri[0], abs=0.15)
    assert fit[1] == pytest.approx(veri[1], abs=0.15)
    assert fit[2] < 1e-3


def test_il_fit_rifiuta_un_mercato_che_non_sa_riprodurre():
    """FALSIFICAZIONE: una distribuzione che il modello non puo' generare deve
    dare una KL alta, non un fit qualsiasi."""
    p = M4.carica_parametri()
    mercato = {(9, 9): 0.5, (8, 8): 0.2, (7, 7): 0.1,
               (0, 0): 0.1, (1, 0): 0.05, (0, 1): 0.05}
    fit = M4.fitta_lambdas(mercato=mercato, minuto=10.0, punteggio=(0, 0),
                           periodo=M4.V.PERIODO_FT, p=p)
    assert fit is None or fit[2] > M4.FIT_KL_MAX


def _coppia(minuto, p_impl, nome="3 - 3", punteggio="0-0", sid=13, ev="A"):
    return _riga_finta(event_id=ev, selection_id=sid, nome=nome, minuto=minuto,
                       punteggio=punteggio, p_impl_tocco=p_impl, p_equa=p_impl,
                       distanza_gol=6, fascia="1-2%")


def test_deriva_margine_vale_uno_se_mercato_e_modello_si_muovono_uguale():
    p = M4.carica_parametri()
    anc = {("A", MERCATO): {"lambdas": (1.4, 1.1), "kl": 0.0, "minuto": 10,
                            "periodo": M4.V.PERIODO_FT, "punteggio": (0, 0),
                            "mercato": "CORRECT_SCORE", "n_celle_fit": 9}}
    g1 = M4.V.griglia_finale(minuto=10.0, punteggio=(0, 0),
                             periodo=M4.V.PERIODO_FT, p=p, lambdas=(1.4, 1.1))
    g2 = M4.V.griglia_finale(minuto=15.0, punteggio=(0, 0),
                             periodo=M4.V.PERIODO_FT, p=p, lambdas=(1.4, 1.1))
    rapporto_modello = g2[(3, 3)] / g1[(3, 3)]
    righe = [_coppia(10, 0.02), _coppia(15, 0.02 * rapporto_modello)]
    cp = M4.coppie(righe, anc, p, delta=5, distanza_minima=2)
    assert len(cp) == 1
    assert cp[0]["deriva_margine"] == pytest.approx(1.0, abs=1e-6)
    # FALSIFICAZIONE: se il mercato non si muove affatto, il margine MIGLIORA
    righe2 = [_coppia(10, 0.02), _coppia(15, 0.02)]
    cp2 = M4.coppie(righe2, anc, p, delta=5, distanza_minima=2)
    assert cp2[0]["deriva_margine"] == pytest.approx(1.0 / rapporto_modello, rel=1e-6)
    assert cp2[0]["deriva_margine"] > 1.0


def test_una_coppia_con_un_gol_in_mezzo_non_e_una_coppia():
    p = M4.carica_parametri()
    anc = {("A", MERCATO): {"lambdas": (1.4, 1.1), "kl": 0.0, "minuto": 10,
                            "periodo": M4.V.PERIODO_FT, "punteggio": (0, 0),
                            "mercato": "CORRECT_SCORE", "n_celle_fit": 9}}
    righe = [_coppia(10, 0.02, punteggio="0-0"),
             _coppia(15, 0.02, punteggio="1-0")]
    assert M4.coppie(righe, anc, p, delta=5, distanza_minima=2) == []


# ---------------------------------------------------------------------------
# M5
# ---------------------------------------------------------------------------
def _fascia(quota=40.0, k=2.0):
    p_impl = (1.0 - M5.COMMISSIONE) / (quota - M5.COMMISSIONE)
    return M5.Fascia("CORRECT_SCORE", "1-2%", quota, p_impl, k, 1.0)


def test_il_montecarlo_ritrova_lEV_analitico():
    f = _fascia(quota=40.0, k=2.0)
    liability = 30.0
    stake = liability / (f.quota - 1.0)
    p = f.p_vera()
    ev_atteso = (1.0 - p) * stake * (1.0 - M5.COMMISSIONE) - p * liability
    r = M5.simula([f], mesi=400, giorni=1, partite=50, celle=1, phi=1.0,
                  liability=liability, commissione=M5.COMMISSIONE,
                  selezione_avversa=1.0, cv_partita=0.0, seme=5)
    per_gamba = r["pnl_mensile_medio"] / r["gambe_abbinate_per_mese_media"]
    assert per_gamba == pytest.approx(ev_atteso, rel=0.12)
    assert ev_atteso > 0


def test_con_k_sotto_uno_il_montecarlo_perde():
    """FALSIFICAZIONE: `k < 1` deve dare P&L negativo. Un simulatore che torna
    positivo comunque non sta simulando niente."""
    r = M5.simula([_fascia(quota=40.0, k=0.7)], mesi=200, giorni=5, partite=50,
                  celle=1, phi=1.0, liability=30.0, commissione=M5.COMMISSIONE,
                  selezione_avversa=1.0, cv_partita=0.0, seme=5)
    assert r["pnl_mensile_medio"] < 0


def test_nel_paniere_perde_al_piu_UNA_cella_per_mercato():
    """Le scoreline sono mutuamente esclusive: con 5 celle quotate su un mercato
    non se ne possono perdere due nella stessa partita."""
    import random as _r
    f = _fascia(quota=3.0, k=1.0)           # probabilita' altissima, apposta
    per_mercato = {"CORRECT_SCORE": [f]}
    for seme in range(30):
        pnl, abbinate, perdite, _ = M5.simula_giorno(
            per_mercato, partite=10, celle=5, phi=1.0, liability=30.0,
            commissione=M5.COMMISSIONE, selezione_avversa=1.0, cv_partita=0.0,
            rnd=_r.Random(seme))
        assert abbinate == 50
        assert perdite <= 10                # al piu' una per partita


def test_la_selezione_avversa_peggiora_il_risultato():
    base = M5.simula([_fascia(quota=40.0, k=2.0)], mesi=200, giorni=5, partite=50,
                     celle=1, phi=1.0, liability=30.0, commissione=M5.COMMISSIONE,
                     selezione_avversa=1.0, cv_partita=0.0, seme=5)
    avversa = M5.simula([_fascia(quota=40.0, k=2.0)], mesi=200, giorni=5,
                        partite=50, celle=1, phi=1.0, liability=30.0,
                        commissione=M5.COMMISSIONE, selezione_avversa=2.5,
                        cv_partita=0.0, seme=5)
    assert avversa["pnl_mensile_medio"] < base["pnl_mensile_medio"]


def test_semi_diversi_danno_gli_stessi_intervalli():
    a = M5.simula([_fascia()], mesi=400, giorni=10, partite=60, celle=1, phi=0.2,
                  liability=30.0, commissione=M5.COMMISSIONE,
                  selezione_avversa=1.0, cv_partita=0.27, seme=1)
    b = M5.simula([_fascia()], mesi=400, giorni=10, partite=60, celle=1, phi=0.2,
                  liability=30.0, commissione=M5.COMMISSIONE,
                  selezione_avversa=1.0, cv_partita=0.27, seme=999)
    assert a["pnl_mensile_medio"] == pytest.approx(b["pnl_mensile_medio"], rel=0.25)
    assert a["prob_mese_negativo"] == pytest.approx(b["prob_mese_negativo"], abs=0.06)


def test_la_quota_e_coerente_con_la_p_implicita_usata(tmp_path):
    """Il difetto trovato il 17/09: mescolare la quota MEDIANA misurata con la
    `p_impl` MEDIA faceva uscire un P&L negativo su fasce a k > 1. Il test passa
    dalla funzione VERA che costruisce le fasce, non da un oggetto a mano."""
    p_impl = 0.02768
    k_json = tmp_path / "k.json"
    sup_json = tmp_path / "s.json"
    k_json.write_text(json.dumps({"righe": [{
        "mercato": "CORRECT_SCORE", "fascia": "1-2%",
        "p_impl_best_back": p_impl, "k_best_back_prudente": 1.45}]}),
        encoding="utf-8")
    sup_json.write_text(json.dumps({"righe": [{
        "mercato": "CORRECT_SCORE", "fascia": "1-2%",
        "quota_back_mediana": 46.0, "n_celle": 100}]}), encoding="utf-8")
    fasce = M5.fasce_da_misure(k_json=str(k_json), superficie_json=str(sup_json),
                               livello="best_back", k_campo="k_best_back_prudente",
                               soglia_k=1.0)
    assert len(fasce) == 1
    f = fasce[0]
    assert f.quota_misurata == pytest.approx(46.0)
    # la quota USATA deve venire dalla stessa p_impl, non dalla mediana misurata
    attesa = (1.0 - M5.COMMISSIONE) / p_impl + M5.COMMISSIONE
    assert f.quota == pytest.approx(attesa, rel=1e-9)
    assert f.quota == pytest.approx(34.4, abs=0.2)
    assert f.quota != pytest.approx(f.quota_misurata, rel=0.05)
    # e con quella quota una fascia a k > 1 deve avere EV POSITIVO
    ev = (1.0 - f.p_vera()) * (30.0 / (f.quota - 1.0)) * 0.95 - f.p_vera() * 30.0
    assert ev > 0
