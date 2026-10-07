# -*- coding: utf-8 -*-
"""OMEGA V3 INCLUDE GLI "ANY OTHER" - 07/10/2026, DECISIONE DELL'UTENTE.

Ordine dell'utente, testuale: "io voglio che operi come ti ho detto, 1 operazione
primo tempo e 1 operazione secondo tempo (se rispetta le condizioni) deve
includere anche "Any Other"".

Che cosa si prova qui (referto `AUDIT_2026-10-07/OMEGA_ANY_OTHER.md`):

1. DISTANZA DAL PUNTEGGIO di un aggregato = gol aggiuntivi fino al punteggio
   COPERTO piu' vicino; un aggregato gia' "vinto" (il punteggio corrente e'
   dentro il suo insieme) o piu' vicino della soglia si scarta come i numerici.
   Oracolo: ricerca a forza bruta su una griglia 0..20, scritta qui.
2. P DELL'AGGREGATO = somma della griglia del modello sui punteggi FINALI della
   sua direzione NON quotati da QUEL mercato, CODA OLTRE LA GRIGLIA COMPRESA.
   Oracolo: binomiali negative di scipy su 80x80 celle, scritte qui (non la
   funzione di produzione).
3. INTERRUTTORE `v3_include_aggregate` (di serie ACCESO): spento, sui book
   VERI delle registrazioni gli scarti e le scelte delle scoreline sono quelli
   di HEAD 8226d766 (fotografia nella fixture); acceso, le differenze di scelta
   da HEAD sono elencate una per una (sui 81 campioni: nessuna).
4. USCITE: la P del bancato e la traiettoria esistono anche per un aggregato
   (prima: "selezione_aggregata", mai una proposta).
5. REGOLAMENTO con le chiavi vere del `marketDefinition` (35760084, 4-0: vince
   9063254 "Any Other Home Win").

Ogni test e' stato falsificato (vedi referto, sezione Falsificazioni).
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pytest
from scipy.stats import nbinom

from Betfair.omega import omega_config as C
from Betfair.omega import omega_engine as E
from Betfair.omega import omega_market as OM
from Betfair.omega import omega_proposte as PR
from Betfair.omega import omega_service as S
from Betfair.omega import omega_v3 as V3

_DATI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dati",
                     "cs_book_registrazioni_2026_10_07.json")

# I NOMI VERI del Correct Score Betfair (listMarketCatalogue): 16 scoreline fino
# al 3-3 e tre aggregati. Gli id seguono i gusci (k*k+1, verificati sulle
# registrazioni); gli aggregati 9063254/55/56 = Home/Away/Draw (prezzi pre-match
# della 35797769: 9063255 a 80, 9063256 a 400 -> 56 e' il pareggio 4-4+).
AOHW, AOAW, AOD = "Any Other Home Win", "Any Other Away Win", "Any Other Draw"
SID_AGG = {AOHW: 9063254, AOAW: 9063255, AOD: 9063256}


def _nome_guscio(sid: int) -> str:
    k = int(math.isqrt(sid - 1))
    pos = sid - (k * k + 1)
    return f"{k} - {pos}" if pos <= k else f"{2 * k - pos} - {k}"


NUMERICI = {sid: _nome_guscio(sid) for sid in range(1, 17)}
NOMI_CS = list(NUMERICI.values()) + [AOHW, AOAW, AOD]
QUOTATE = {(h, a) for h in range(4) for a in range(4)}


# ===========================================================================
# ORACOLI (scritti qui: non chiamano le funzioni che provano)
# ===========================================================================
def _copre_oracolo(direzione: Optional[str], cella: Tuple[int, int]) -> bool:
    h, a = cella
    if cella in QUOTATE:
        return False
    if direzione == "home":
        return h > a
    if direzione == "away":
        return a > h
    if direzione == "draw":
        return h == a
    return True


def _distanza_oracolo(direzione: Optional[str], sh: int, sa: int) -> Optional[int]:
    best = None
    for h in range(sh, 21):
        for a in range(sa, 21):
            if _copre_oracolo(direzione, (h, a)):
                d = (h - sh) + (a - sa)
                best = d if best is None else min(best, d)
    return best


def _p_oracolo(direzione: Optional[str], *, minuto: float, punteggio: Tuple[int, int],
               p: V3.Parametri, lambdas: Tuple[float, float], n: int = 80) -> float:
    """Gamma-Poisson (predittiva binomiale negativa per lato) + tau di
    Dixon-Coles allo 0-0, su n x n celle, normalizzata: la P VERA dell'insieme
    coperto, coda compresa. Le esposizioni vengono dal profilo condiviso."""
    sh, sa = punteggio
    a = float(p.forma_gamma)
    cons, res = V3.esposizione(minuto, "ft", p)
    lh0, la0 = lambdas
    d = sh - sa
    rh = res * math.exp(-p.beta_squilibrio * d)
    ra = res * math.exp(+p.beta_squilibrio * d)
    bh, ba = a / lh0 + cons, a / la0 + cons
    ph = nbinom.pmf(range(n), a + sh, bh / (bh + rh))
    pa = nbinom.pmf(range(n), a + sa, ba / (ba + ra))
    lh, la = (a + sh) / bh * rh, (a + sa) / ba * ra
    tot = 0.0
    dentro = 0.0
    for i in range(n):
        for j in range(n):
            v = float(ph[i]) * float(pa[j])
            if (sh, sa) == (0, 0) and i <= 1 and j <= 1:
                rho = p.rho
                tau = {(0, 0): 1 - lh * la * rho, (1, 0): 1 + la * rho,
                       (0, 1): 1 + lh * rho, (1, 1): 1 - rho}[(i, j)]
                v *= max(0.0, tau)
            tot += v
            if _copre_oracolo(direzione, (sh + i, sa + j)):
                dentro += v
    return dentro / tot


def _parametri() -> V3.Parametri:
    PR.svuota_le_cache()
    return PR.parametri_modello()


# ===========================================================================
# 1. LA DISTANZA DI UN AGGREGATO
# ===========================================================================
@pytest.mark.parametrize("punteggio", [(0, 0), (1, 0), (3, 0), (2, 2), (3, 3), (4, 4),
                                       (4, 0), (0, 4), (1, 3), (5, 2), (2, 5), (6, 6)])
@pytest.mark.parametrize("nome", [AOHW, AOAW, AOD])
def test_distanza_aggregato_come_l_oracolo(nome, punteggio):
    atteso = _distanza_oracolo(V3.direzione_aggregato(nome), *punteggio)
    got = V3.distanza_aggregato(nome, punteggio, V3.punteggi_quotati(NOMI_CS))
    assert got == atteso, (nome, punteggio, got, atteso)


def test_distanza_aggregato_casi_scritti_a_mano():
    """I casi del brief, con il numero scritto (non solo "come l'oracolo")."""
    q = V3.punteggi_quotati(NOMI_CS)
    casi = {((0, 0), AOHW): 4, ((0, 0), AOAW): 4, ((0, 0), AOD): 8,
            ((3, 0), AOHW): 1, ((3, 0), AOAW): 4, ((3, 0), AOD): 5,
            ((2, 2), AOHW): 2, ((2, 2), AOAW): 2, ((2, 2), AOD): 4,
            ((4, 4), AOD): 0, ((4, 4), AOHW): 1, ((3, 3), AOD): 2,
            ((4, 0), AOHW): 0}
    for (sc, nome), d in casi.items():
        assert V3.distanza_aggregato(nome, sc, q) == d, (sc, nome)


def test_distanza_aggregato_dipende_dai_runner_veri_del_mercato():
    """La griglia quotata si ricava dai runner, mai da una lista scritta a mano:
    un mercato che quota fino al 4-4 sposta l'insieme dell'aggregato."""
    piu_largo = [f"{h} - {a}" for h in range(5) for a in range(5)] + [AOHW, AOAW, AOD]
    assert V3.distanza_aggregato(AOD, (2, 2), V3.punteggi_quotati(NOMI_CS)) == 4
    assert V3.distanza_aggregato(AOD, (2, 2), V3.punteggi_quotati(piu_largo)) == 6
    # "Any Unquoted" senza direzione: e' il punteggio corrente se non e' quotato
    assert V3.distanza_aggregato("Any Unquoted", (4, 1), V3.punteggi_quotati(NOMI_CS)) == 0


def test_distanza_aggregato_oltre_il_limite_e_none():
    assert V3.distanza_aggregato(AOD, (0, 0), V3.punteggi_quotati(NOMI_CS), limite=3) is None
    assert V3.distanza_aggregato("2 - 1", (0, 0), V3.punteggi_quotati(NOMI_CS)) is None


# ===========================================================================
# 2. LA SELEZIONE: stesse condizioni dei numerici, distanza compresa
# ===========================================================================
def _runner(nome: str, prezzo: Optional[float], size: float = 50.0) -> V3.RunnerV3:
    sid = SID_AGG.get(nome) or next(s for s, n in NUMERICI.items() if n == nome)
    return V3.RunnerV3(selection_id=sid, name=nome, lay_price=prezzo, lay_size=size)


def _mercato(prezzi: Dict[str, Optional[float]]) -> List[V3.RunnerV3]:
    """Il mercato INTERO (19 runner); i numerici senza lay se non indicati."""
    return [_runner(n, prezzi.get(n)) for n in NOMI_CS]


def _valuta(runners, punteggio, *, prob: Dict[str, float], **kw):
    return V3.valuta_runner(periodo="ft", runners=runners, probabilita=prob,
                            punteggio=punteggio, distanza_minima_gol=2, k_default=1.11,
                            p_min=0.01, p_max=0.02, commissione=0.05, **kw)


def _scarto(scarti, nome):
    return next((m for n, m in scarti if n == nome), None)


@pytest.mark.parametrize("punteggio,nome,motivo", [
    ((3, 0), AOHW, "troppo_vicino_al_punteggio"),     # 4-0 a un gol
    ((4, 0), AOHW, "troppo_vicino_al_punteggio"),     # gia' "vinto": e' il corrente
    ((4, 4), AOD, "troppo_vicino_al_punteggio"),      # gia' "vinto"
    ((3, 3), AOHW, "troppo_vicino_al_punteggio"),     # 4-3 a un gol
])
def test_aggregato_troppo_vicino_si_scarta_come_un_numerico(punteggio, nome, motivo):
    """Oggi (HEAD) l'aggregato non aveva NESSUNA regola di distanza: a 3-0 il
    "Any Other Home Win" (4-0 a un gol) passava col solo margine."""
    prob = {n: 0.004 for n in NOMI_CS}
    cand, scarti = _valuta(_mercato({nome: 60.0}), punteggio, prob=prob)
    assert cand is None
    assert _scarto(scarti, nome) == motivo


@pytest.mark.parametrize("punteggio,nome", [((2, 2), AOHW), ((2, 2), AOAW), ((2, 2), AOD),
                                            ((0, 0), AOHW), ((1, 1), AOHW), ((3, 3), AOD)])
def test_aggregato_alla_distanza_giusta_e_candidato(punteggio, nome):
    prob = {n: 0.004 for n in NOMI_CS}
    cand, _scarti = _valuta(_mercato({nome: 60.0}), punteggio, prob=prob)
    assert cand is not None and cand.name == nome
    assert cand.selection_id == SID_AGG[nome]


def test_la_selezione_ricava_l_insieme_dai_runner_veri_del_mercato():
    """Un mercato che quota fino al 4-4: a 3-0 l'"Any Other Home Win" comincia
    dal 5-0, a DUE gol -> candidato. Con la griglia 0..3 data per scontata
    comincerebbe dal 4-0, a un gol, e verrebbe scartato a torto."""
    nomi = [f"{h} - {a}" for h in range(5) for a in range(5)] + [AOHW, AOAW, AOD]
    rr = [V3.RunnerV3(selection_id=100 + i, name=n,
                      lay_price=(60.0 if n == AOHW else None), lay_size=50.0)
          for i, n in enumerate(nomi)]
    prob = {n: 0.004 for n in nomi}
    cand, scarti = _valuta(rr, (3, 0), prob=prob)
    assert cand is not None and cand.name == AOHW, scarti
    cand, scarti = _valuta(rr, (3, 0), prob=prob, nomi_mercato=nomi)
    assert cand is not None and cand.name == AOHW, scarti


def test_aggregato_irraggiungibile_si_scarta_col_motivo(monkeypatch):
    """Con i nomi Betfair un aggregato e' sempre raggiungibile (l'insieme e'
    infinito); il ramo esiste per un nome senza celle raggiungibili e deve dire
    "irraggiungibile", non passare."""
    monkeypatch.setattr(V3, "distanza_aggregato", lambda *a, **k: None)
    prob = {n: 0.004 for n in NOMI_CS}
    cand, scarti = _valuta(_mercato({AOHW: 60.0}), (1, 1), prob=prob)
    assert cand is None and _scarto(scarti, AOHW) == "irraggiungibile"


def test_le_stesse_condizioni_valgono_per_l_aggregato():
    """Fascia, tetto della P, margine, liquidita', cap di gamba, cella gia'
    bancata: nessuna soglia nuova, nessuna eccezione per gli aggregati."""
    base = {n: 0.004 for n in NOMI_CS}
    sc = (1, 1)
    # fascia: quota 30 -> p_impl 3,2 % oltre il 2 %
    assert _scarto(_valuta(_mercato({AOHW: 30.0}), sc, prob=base)[1], AOHW) == "p_impl_oltre_fascia"
    # pavimento: quota 200 -> p_impl 0,48 %
    assert _scarto(_valuta(_mercato({AOHW: 200.0}), sc, prob=base)[1], AOHW) == "p_impl_sotto_fascia"
    # margine: P nostra 1,5 % contro p_impl 1,59 % / 1,11
    alta = dict(base, **{AOHW: 0.015})
    assert _scarto(_valuta(_mercato({AOHW: 60.0}), sc, prob=alta)[1], AOHW).startswith("margine")
    # liquidita'
    rr = [V3.RunnerV3(selection_id=SID_AGG[AOHW], name=AOHW, lay_price=60.0, lay_size=0.5)]
    assert _scarto(_valuta(rr, sc, prob=base, nomi_mercato=NOMI_CS)[1], AOHW) == \
        "liquidita_insufficiente"
    # cap di gamba
    assert _scarto(_valuta(_mercato({AOHW: 60.0}), sc, prob=base,
                           cap_liability_gamba=50.0)[1], AOHW) == "oltre_il_cap_di_gamba"
    # cella gia' bancata dalla prima gamba
    assert _scarto(_valuta(_mercato({AOHW: 60.0}), sc, prob=base,
                           escludi=(SID_AGG[AOHW],))[1], AOHW) == "cella_gia_bancata"


def test_interruttore_spento_scarta_gli_aggregati_col_motivo():
    prob = {n: 0.004 for n in NOMI_CS}
    cand, scarti = _valuta(_mercato({AOHW: 60.0, AOD: 60.0}), (1, 1), prob=prob,
                           includi_aggregati=False)
    assert cand is None
    assert _scarto(scarti, AOHW) == "aggregato_escluso"
    assert _scarto(scarti, AOD) == "aggregato_escluso"


def test_la_griglia_quotata_viene_dai_runner_quando_mancano_i_nomi():
    """Senza `nomi_mercato` l'insieme quotato si ricava dai runner passati: il
    mercato intero e' gia' li'."""
    prob = {n: 0.004 for n in NOMI_CS}
    cand, _ = V3.valuta_runner(periodo="ft", runners=_mercato({AOHW: 60.0}), probabilita=prob,
                               punteggio=(3, 0), distanza_minima_gol=2, k_default=1.11,
                               p_min=0.01, p_max=0.02)
    assert cand is None
    cand, _ = V3.valuta_runner(periodo="ft", runners=_mercato({AOHW: 60.0}), probabilita=prob,
                               punteggio=(2, 0), distanza_minima_gol=2, k_default=1.11,
                               p_min=0.01, p_max=0.02)
    assert cand is not None and cand.name == AOHW          # 4-0 a due gol


# ===========================================================================
# 3. LA P DELL'AGGREGATO, CODA OLTRE LA GRIGLIA COMPRESA
# ===========================================================================
@pytest.mark.parametrize("lambdas,minuto,punteggio", [
    ((1.45, 1.15), 60.0, (1, 1)),
    ((1.45, 1.15), 1.0, (0, 0)),          # tau di Dixon-Coles allo 0-0
    ((2.5, 2.0), 1.0, (0, 0)),            # coda pesante: 4e-4 di massa oltre 10 gol
    ((2.5, 2.0), 20.0, (2, 2)),
    ((1.2, 0.9), 70.0, (3, 0)),
])
def test_p_aggregato_uguale_all_oracolo_indipendente(lambdas, minuto, punteggio):
    p = _parametri()
    ps = V3.probabilita_selezioni(periodo="ft", minuto=minuto, punteggio=punteggio,
                                  nomi=NOMI_CS, p=p, lambdas=lambdas, includi_coda=True)
    for nome in (AOHW, AOAW, AOD):
        atteso = _p_oracolo(V3.direzione_aggregato(nome), minuto=minuto,
                            punteggio=punteggio, p=p, lambdas=lambdas)
        assert abs(ps[nome] - atteso) < 1e-10, (nome, ps[nome], atteso)


def test_la_coda_conta_e_senza_coda_la_p_e_sottostimata():
    """Il motivo per cui la coda c'e': con la griglia troncata a 10 gol residui
    per lato e normalizzata, la massa oltre il bordo (TUTTA degli aggregati)
    viene spalmata su tutte le celle e l'aggregato risulta MENO probabile."""
    p = _parametri()
    kw = dict(periodo="ft", minuto=1.0, punteggio=(0, 0), nomi=NOMI_CS, p=p,
              lambdas=(2.5, 2.0))
    senza = V3.probabilita_selezioni(**kw)
    con = V3.probabilita_selezioni(includi_coda=True, **kw)
    massa = V3.massa_oltre_griglia(periodo="ft", minuto=1.0, punteggio=(0, 0), p=p,
                                   lambdas=(2.5, 2.0))
    assert 1e-4 < massa < 1e-3                                   # dichiarata, e misurata
    sotto = sum(con[n] - senza[n] for n in (AOHW, AOAW, AOD))
    assert sotto > 0.5 * massa                                   # senza coda si sottostima
    # per nome: la vecchia somma SOTTOSTIMA casa e trasferta (dove sta la coda)
    # e sovrastima di poco il pareggio (la normalizzazione gli regalava massa);
    # la nuova coincide con l'oracolo, la vecchia no
    assert con[AOHW] > senza[AOHW] and con[AOAW] > senza[AOAW]
    for n in (AOHW, AOAW, AOD):
        vera = _p_oracolo(V3.direzione_aggregato(n), minuto=1.0, punteggio=(0, 0), p=p,
                          lambdas=(2.5, 2.0))
        assert abs(con[n] - vera) < 1e-10
        assert abs(senza[n] - vera) > 1e-6


def test_la_coda_non_tocca_le_scoreline():
    """Le scoreline restano quelle di oggi al bit: la coda e' solo degli aggregati."""
    p = _parametri()
    kw = dict(periodo="ft", minuto=30.0, punteggio=(1, 0), nomi=NOMI_CS, p=p,
              lambdas=(1.6, 1.1))
    senza = V3.probabilita_selezioni(**kw)
    con = V3.probabilita_selezioni(includi_coda=True, **kw)
    for n in NUMERICI.values():
        assert con[n] == senza[n]


def test_massa_oltre_la_griglia_estesa_e_trascurabile():
    """La griglia estesa dell'aggregato non e' a sua volta troncata in modo
    rilevante: oltre MAX_GOL_CODA resta meno di 1e-12 anche coi lambda estremi."""
    p = _parametri()
    fuori = V3.massa_oltre_griglia(periodo="ft", minuto=1.0, punteggio=(0, 0), p=p,
                                   lambdas=(3.5, 3.0), max_gol=V3.MAX_GOL_CODA["ft"],
                                   max_gol_estesa=90)
    assert fuori < 1e-12


# ===========================================================================
# 4. IL RACCORDO E L'INTERRUTTORE, SUI BOOK VERI DELLE REGISTRAZIONI
# ===========================================================================
LAMBDAS_FIXTURE = (1.45, 1.15)


def _campioni() -> List[dict]:
    with open(_DATI, "r", encoding="utf-8") as fh:
        return json.load(fh)["campioni"]


def _score_runners(c: dict, con_aggregati: bool = True) -> List[E.ScoreRunner]:
    return [E.ScoreRunner(selection_id=sid, name=nome, lay_price=lp, lay_size=ls,
                          back_price=bp, back_size=bs)
            for sid, nome, lp, ls, bp, bs in c["runners"]
            if con_aggregati or not V3.e_aggregato(nome)]


def _seleziona(c: dict, params: dict, con_aggregati: bool = True):
    rr = _score_runners(c, con_aggregati)
    m = int(c["minuto"])
    return E.seleziona_v3(rr, periodo="ft", minuto=float(m),
                          punteggio=tuple(c["punteggio"]), params=params,
                          lambdas=LAMBDAS_FIXTURE, parametri_modello=_parametri(),
                          k_tab=None, finestra=(1, 44) if m <= 44 else (46, 85),
                          p_mercato=V3.p_mercato_devigata(rr))


def test_di_serie_l_interruttore_e_acceso_e_parametri_v3_lo_legge():
    p = C.resolve_params({})
    assert p["v3_include_aggregate"] is True
    assert C.parametri_v3(p)["include_aggregate"] is True
    assert C.parametri_v3(C.resolve_params({"v3_include_aggregate": "false"}))[
        "include_aggregate"] is False
    assert C.parametri_v3(C.resolve_params({"v3_include_aggregate": False}))[
        "include_aggregate"] is False


def test_spento_la_selezione_e_identica_a_oggi_sui_numerici():
    """NESSUNA REGRESSIONE: interruttore SPENTO, mercato INTERO (come lo passa il
    servizio: la fusione deviga sul book intero, aggregati compresi), contro la
    fotografia di HEAD nella fixture, campione per campione:
      * gli scarti di OGNI scoreline identici, motivo per motivo;
      * dove HEAD sceglieva una scoreline (o niente), la stessa scelta, con la
        stessa P al bit;
      * dove HEAD sceglieva un aggregato (35797769, 75' e 77'), la scoreline
        migliore fra quelle che HEAD non scartava: e' la "3 - 2", la stessa che
        HEAD sceglieva sul mercato senza aggregati.
    Gli aggregati: tutti `aggregato_escluso`."""
    params = C.resolve_params({"v3_include_aggregate": False})
    campioni = _campioni()
    assert len(campioni) == 81
    sostituiti = []
    for c in campioni:
        cand, scarti = _seleziona(c, params)
        oggi = c["oggi_con_aggregati"]["candidato"]
        chi = (c["event_id"], c["minuto"])
        numerici = [[n, m] for n, m in scarti if not V3.e_aggregato(n)]
        oggi_num = [[n, m] for n, m in c["oggi_con_aggregati"]["scarti"]
                    if not V3.e_aggregato(n)]
        assert numerici == oggi_num, chi
        for n, m in scarti:
            if V3.e_aggregato(n):
                assert m == "aggregato_escluso", chi
        if oggi is None:
            assert cand is None, chi
        elif not V3.e_aggregato(oggi["name"]):
            assert cand is not None, chi
            assert (cand.name, cand.selection_id, cand.price) == \
                (oggi["name"], oggi["selection_id"], oggi["price"]), chi
            assert cand.p_nostra == oggi["p_nostra"], chi
        else:
            assert cand is not None and not V3.e_aggregato(cand.name), chi
            assert cand.name not in {n for n, _m in oggi_num}, chi
            assert cand.name == c["oggi_senza_aggregati"]["candidato"]["name"], chi
            sostituiti.append((c["event_id"], c["minuto"], cand.name))
    assert sostituiti == [("35797769", 75, "3 - 2"), ("35797769", 77, "3 - 2")]


# Le DIFFERENZE di selezione con l'interruttore ACCESO rispetto a HEAD, sui 81
# campioni veri, una per una (spiegate nel referto, sezione 4): nessuna. I due ingressi
# su "Any Other Home Win" (35797769, 1-1, 75' e 77') c'erano gia' con HEAD e
# restano: la cella coperta piu' vicina e' 4-1, a TRE gol (soglia 2).
DIFFERENZE_ACCESO: Dict[Tuple[str, int], Tuple[Optional[str], Optional[str]]] = {}


def test_acceso_le_differenze_da_oggi_sono_quelle_elencate():
    params = C.resolve_params({})
    viste: Dict[Tuple[str, int], Tuple[Optional[str], Optional[str]]] = {}
    aggregati_scelti = []
    for c in _campioni():
        cand, scarti = _seleziona(c, params)
        oggi = c["oggi_con_aggregati"]["candidato"]
        nuovo = None if cand is None else cand.name
        prima = None if oggi is None else oggi["name"]
        if nuovo != prima:
            viste[(c["event_id"], c["minuto"])] = (prima, nuovo)
        if cand is not None and V3.e_aggregato(cand.name):
            aggregati_scelti.append((c["event_id"], c["minuto"], cand.name))
            # la distanza dichiarata nel motivo e' quella vera
            d = V3.distanza_aggregato(cand.name, tuple(c["punteggio"]),
                                      V3.punteggi_quotati([r[1] for r in c["runners"]]))
            assert d is not None and d >= 2
            assert f"distanza {d} gol" in cand.motivo
            assert "coda oltre la griglia" in cand.motivo
        for n, m in scarti:
            assert m != "aggregato_escluso"
    assert viste == DIFFERENZE_ACCESO
    assert aggregati_scelti == [("35797769", 75, AOHW), ("35797769", 77, AOHW)]


def test_il_raccordo_usa_la_p_dell_aggregato_con_la_coda():
    """`seleziona_v3` (il raccordo del servizio) chiede a `omega_v3` la P CON la
    coda per gli aggregati: fusione spenta, la P del candidato e' quella."""
    params = C.resolve_params({"v3_fusione_mercato": "off"})
    p = _parametri()
    rr = [E.ScoreRunner(selection_id=SID_AGG.get(n) or
                        next(s for s, x in NUMERICI.items() if x == n),
                        name=n, lay_price=(60.0 if n == AOAW else None),
                        lay_size=(50.0 if n == AOAW else 0.0)) for n in NOMI_CS]
    cand, _ = E.seleziona_v3(rr, periodo="ft", minuto=5.0, punteggio=(0, 0),
                             params=params, lambdas=(1.0, 0.7), parametri_modello=p,
                             finestra=(1, 44))
    assert cand is not None and cand.name == AOAW, _
    attesa = V3.probabilita_selezioni(periodo="ft", minuto=5.0, punteggio=(0, 0),
                                      nomi=NOMI_CS, p=p, lambdas=(1.0, 0.7),
                                      includi_coda=True)[AOAW]
    senza = V3.probabilita_selezioni(periodo="ft", minuto=5.0, punteggio=(0, 0),
                                     nomi=NOMI_CS, p=p, lambdas=(1.0, 0.7))[AOAW]
    assert cand.p_modello == attesa and attesa != senza


def test_acceso_un_aggregato_a_un_gol_sul_book_vero_si_scarta():
    """Il book vero della 35760084 al 49' (3-0) con il lay dell'"Any Other Home
    Win" rimesso in fascia: e' il caso che HEAD lasciava passare (4-0 a un gol)."""
    c = next(x for x in _campioni() if x["event_id"] == "35760084" and x["minuto"] == 49)
    c = json.loads(json.dumps(c))
    for r in c["runners"]:
        if r[1] == AOHW:
            r[2], r[3] = 60.0, 20.0
    cand, scarti = _seleziona(c, C.resolve_params({}))
    assert (cand is None or cand.name != AOHW)
    assert _scarto(scarti, AOHW) == "troppo_vicino_al_punteggio"


# ===========================================================================
# 5. LE USCITE: traiettoria e proposta anche per un aggregato
# ===========================================================================
def test_traiettoria_di_un_aggregato_con_i_nomi_del_mercato():
    p = _parametri()
    pos = V3.Posizione(periodo="ft", selection_name=AOHW, lay_price=60.0, size=1.0,
                       punteggio_ingresso=(1, 1), minuto_ingresso=50.0)
    traj = V3.traiettoria_bloccabile(pos, minuto=60.0, punteggio=(1, 1), p=p,
                                     lambdas=(1.45, 1.15), nomi_mercato=NOMI_CS)
    assert traj, "nessun punto: l'aggregato non ha una traiettoria"
    attesa = V3.probabilita_selezioni(periodo="ft", minuto=60.0, punteggio=(1, 1),
                                      nomi=NOMI_CS, p=p, lambdas=(1.45, 1.15),
                                      includi_coda=True)[AOHW]
    assert abs(traj[0].p_evento - attesa) < 1e-12
    # col tempo che passa, a punteggio fermo, l'aggregato diventa meno probabile
    assert traj[-1].p_evento < traj[0].p_evento
    # senza i nomi del mercato non si inventa: nessun punto, come prima
    assert V3.traiettoria_bloccabile(pos, minuto=60.0, punteggio=(1, 1), p=p,
                                     lambdas=(1.45, 1.15)) == []


def test_proposta_uscita_di_un_aggregato_non_rompe_e_ha_un_motivo():
    p = _parametri()
    pos = V3.Posizione(periodo="ft", selection_name=AOD, lay_price=60.0, size=1.0,
                       punteggio_ingresso=(2, 2), minuto_ingresso=50.0)
    pe = V3.probabilita_selezioni(periodo="ft", minuto=70.0, punteggio=(3, 3),
                                  nomi=NOMI_CS, p=p, lambdas=(1.45, 1.15),
                                  includi_coda=True)[AOD]
    prop = V3.proposta_uscita(pos, minuto=70.0, punteggio=(3, 3), back_price=12.0,
                              back_size=100.0, p_evento=pe, p=p, lambdas=(1.45, 1.15),
                              nomi_mercato=NOMI_CS)
    # il 3-3 al 70' porta il 4-4 a due gol: chiudere costa ma tenere costa di piu'
    assert prop.motivo_codice in ("protezione", "bloccabile_non_positivo")
    assert prop.p_evento == pe


ADESSO = datetime(2026, 10, 7, 20, 30, tzinfo=timezone.utc)


class _Db:
    """I metodi che il produttore delle proposte usa, con le colonne vere di
    `omega_trades` e della coda `omega_manual_requests` (stesso finto del test
    delle proposte del 17/09, ridotto)."""

    def __init__(self, trades: List[dict]) -> None:
        self.trades = [dict(t) for t in trades]
        self.richieste: List[dict] = []
        self.attivita: List[tuple] = []

    def open_trades(self) -> List[dict]:
        return [t for t in self.trades if t.get("status") == "open"]

    def list_trades(self, status: Optional[str] = None) -> List[dict]:
        return [t for t in self.trades if status is None or t.get("status") == status]

    def trades_for_event(self, event_id: str, **_k: Any) -> List[dict]:
        return [t for t in self.trades if str(t.get("event_id")) == str(event_id)]

    def get_trade(self, trade_id: int) -> Optional[dict]:
        return next((t for t in self.trades if int(t["id"]) == int(trade_id)), None)

    def update_trade(self, trade_id: int, **campi: Any) -> None:
        r = self.get_trade(trade_id)
        if r is not None:
            r.update(campi)

    def log(self, kind: str, payload: Optional[dict] = None, **_k: Any) -> None:
        self.attivita.append((kind, dict(payload or {})))

    def event_user_state(self, event_id: str) -> Optional[dict]:
        return None

    def user_closed_event_ids(self, since_iso: Optional[str] = None) -> set:
        return set()

    def get_event(self, event_id: str) -> Optional[dict]:
        return None

    def save_event_model(self, event_id: str, model: dict) -> bool:
        return True

    def aggregates(self, day_start: Any = None) -> dict:
        return {"realized_profit": 0.0, "realized_today": 0.0, "open_liability": 0.0,
                "locked_pnl_open": 0.0, "locked_pnl_open_today": 0.0,
                "reconciling_liability": 0.0, "matches_traded": 1, "matches_open": 1,
                "settled_count": 0, "total_count": 1, "matches_traded_today": 1,
                "events_today": 1}

    def aggregates_coppia(self, day_start: Any = None):
        return dict(self.aggregates()), dict(self.aggregates())

    def proposta_di_chiusura_viva(self, trade_id: int) -> Optional[dict]:
        return next((dict(r) for r in self.richieste if r["status"] == "proposed"
                     and int(r["payload"]["trade_id"]) == int(trade_id)), None)

    def scrivi_proposta_di_chiusura(self, trade_id: int, payload: Dict[str, Any]) -> int:
        self.richieste.append({"id": len(self.richieste) + 1, "kind": "cashout",
                               "status": "proposed",
                               "payload": {**payload, "trade_id": int(trade_id)},
                               "result": None, "created_at": ADESSO.isoformat(),
                               "updated_at": ADESSO.isoformat(), "processed_at": None})
        return len(self.richieste)

    def chiudi_proposta(self, trade_id: int, motivo: str) -> None:
        for r in self.richieste:
            if r["status"] == "proposed" and int(r["payload"]["trade_id"]) == int(trade_id):
                r["status"] = "rejected"


class _Mercato:
    fresco = True

    def read_book(self, *a: Any, **k: Any):          # pragma: no cover
        raise AssertionError("il produttore NON legge il book via REST")


@pytest.fixture()
def _pulito(monkeypatch: pytest.MonkeyPatch):
    S.svuota_le_cache()
    PR.svuota_le_cache()
    monkeypatch.setattr(S, "_feed_prices_fresh", lambda market, eid: True)
    yield
    S.svuota_le_cache()
    PR.svuota_le_cache()


def _trade_aggregato(**kw: Any) -> dict:
    riga = {"id": 7, "event_id": "35797769", "event_name": "Casa v Fuori",
            "market_id": "1.259819681", "market_type": "CORRECT_SCORE",
            "selection_id": SID_AGG[AOHW], "runner_name": AOHW, "side": "lay",
            "size": 1.0, "price": 60.0, "status": "open", "mode": "paper",
            "origin": "auto", "phase": "ft_cs", "bet_id": "100000000007",
            "liability": 59.0, "commission": 0.05, "closes_trade_id": None,
            "minute_at_entry": 75, "score_at_entry": "1-1",
            "meta": {"runners": {str(s): n for s, n in NUMERICI.items()}}}
    riga.update(kw)
    return riga


def _payload_cs(*, con_numerici: bool = True) -> dict:
    sel = []
    for sid, nome in NUMERICI.items():
        if con_numerici:
            sel.append({"selection_id": sid, "name": nome, "runner_status": "ACTIVE",
                        "back": 20.0, "back_size": 50.0, "lay": 21.0, "lay_size": 50.0})
    for nome, sid in SID_AGG.items():
        sel.append({"selection_id": sid, "name": nome, "runner_status": "ACTIVE",
                    "back": 150.0, "back_size": 50.0, "lay": 160.0, "lay_size": 20.0})
    return {"event_id": "35797769", "minute": 80, "score_home": 1, "score_away": 1,
            "red_home": 0, "red_away": 0, "inplay": True,
            "cs": {"market_id": "1.259819681", "status": "OPEN", "inplay": True,
                   "selections": sel}}


def test_la_gamba_aggregata_arriva_alla_proposta_con_la_p_dell_aggregato(_pulito):
    """Prima: `selezione_aggregata`, la gamba non arrivava MAI al calcolo (nessun
    pulsante di uscita per un aggregato, contro la regola 4-bis). Ora la P del
    bancato e' quella dell'aggregato sul mercato vero e la proposta si scrive.
    Soglia di rischio accesa al minimo solo per avere una proposta certa."""
    params = C.resolve_params({"strategy_version": 3, "proposta_p_lose_max_pct": 0.01})
    db = _Db([_trade_aggregato()])
    n = PR.process_proposte_uscita(params=params, market=_Mercato(), db=db, now=ADESSO,
                                   feed=lambda _e: _payload_cs())
    motivi = [p.get("reason") for k, p in db.attivita if k == "skip"]
    assert "selezione_aggregata" not in motivi, db.attivita
    assert n == 1, db.attivita
    pay = db.richieste[0]["payload"]
    assert pay["selection_name"] == AOHW and pay["motivo_codice"] == "rischio"
    # la P scritta e' quella dell'aggregato, coda compresa, sul mercato del feed
    # (finto senza fixture ne' quote pre-KO: il modello gira coi suoi default e
    # la fonte lo dichiara)
    assert pay["p_fonte"] == "v3:senza_lambda", pay["p_fonte"]
    attesa = V3.probabilita_selezioni(periodo="ft", minuto=80.0, punteggio=(1, 1),
                                      nomi=[s["name"] for s in _payload_cs()["cs"]["selections"]],
                                      p=PR.parametri_modello(), lambdas=None,
                                      includi_coda=True)[AOHW]
    assert abs(float(pay["p_evento"]) - round(attesa, 6)) < 1e-12
    # la P di un aggregato a TRE gol (4-1) e' piccola ma non zero: mai None -> 0
    assert 0.0 < float(pay["p_evento"]) < 0.05


def test_aggregato_senza_scoreline_note_non_inventa_una_p(_pulito):
    """Il feed senza numerici e la riga senza `meta.runners`: l'insieme coperto
    non e' ricavabile -> nessuna proposta, motivo dichiarato (mai il vecchio
    ripiego `[nome]`, che avrebbe dato all'aggregato TUTTA la griglia)."""
    params = C.resolve_params({"strategy_version": 3, "proposta_p_lose_max_pct": 0.01})
    db = _Db([_trade_aggregato(meta={})])
    n = PR.process_proposte_uscita(params=params, market=_Mercato(), db=db, now=ADESSO,
                                   feed=lambda _e: _payload_cs(con_numerici=False))
    assert n == 0 and db.richieste == []
    motivi = [p.get("reason") for k, p in db.attivita if k == "skip"]
    assert "posizione_senza_numeri" in motivi, db.attivita


# ===========================================================================
# 6. IL REGOLAMENTO, con le chiavi vere del marketDefinition
# ===========================================================================
# 35760084 (finale 4-0), CORRECT_SCORE 1.259475532: l'ultimo `marketDefinition`
# della registrazione, runner con le chiavi dello stream (`id`, `status`).
MD_35760084 = {"status": "CLOSED", "inPlay": True, "runners": (
    [{"id": i, "status": "LOSER"} for i in range(1, 17)]
    + [{"id": 9063254, "status": "WINNER"}, {"id": 9063255, "status": "LOSER"},
       {"id": 9063256, "status": "LOSER"}])}


def _snapshot_regolato(md: dict):
    """Il book REST che il servizio legge (`selectionId`/`status`), costruito dal
    `marketDefinition` come fa il replay (`_book_rest`)."""
    mercato = OM.CorrectScoreMarket(
        market_id="1.259475532", event_id="35760084", event_name="",
        market_start_time=None,
        runner_names={**NUMERICI, **{v: k for k, v in SID_AGG.items()}})
    libro = {"status": md["status"], "inplay": md["inPlay"],
             "runners": [{"selectionId": r["id"], "status": r["status"],
                          "ex": {"availableToBack": [], "availableToLay": []}}
                         for r in md["runners"]]}
    return OM._snapshot_from_book(mercato, libro)


@pytest.mark.parametrize("nome,stato,pnl", [(AOHW, "lost", -59.0), (AOAW, "won", 0.95),
                                            (AOD, "won", 0.95)])
def test_aggregato_bancato_regolato_dal_market_definition_vero(nome, stato, pnl):
    snap = _snapshot_regolato(MD_35760084)
    assert snap.closed and not snap.voided and snap.winner_selection_id == 9063254
    got = E.settle_pnl(our_selection_id=SID_AGG[nome],
                       winner_selection_id=snap.winner_selection_id,
                       size=1.0, price=60.0, commission=0.05)
    assert got == (stato, pnl)
    # e la strada del paper senza mercato (risultato vero) dice la stessa cosa
    runners = E.scoreline_names(snap.runners)
    assert E.vince_col_risultato(nome, "4-0", runners) is (stato == "lost")


@pytest.mark.parametrize("nome,risultato,atteso", [
    ("Any Unquoted Home", "4-4", False),      # HEAD: True (unquoted vinceva sempre)
    ("Any Unquoted Home", "5-1", True),
    ("Any Unquoted Draw", "4-4", True),
    ("Any Unquoted Away", "0-4", True),
    ("Any Unquoted Away", "4-4", False),      # HEAD: True
    ("Any Other Half Time Score", "4-0", True),   # HEAD: None (mai regolato)
    ("Any Other Half Time Score", "1-0", False),
    ("Any Unquoted", "4-3", True),
])
def test_vince_col_risultato_legge_la_direzione_prima_di_unquoted(nome, risultato, atteso):
    """I nomi del replay del banco (`replay_registrazioni._ALTRI`) sono
    "Any Unquoted Home/Draw/Away" e "Any Other Half Time Score": la regola
    "unquoted vince sempre" guardava il nome prima della direzione."""
    runners = {str(s): n for s, n in NUMERICI.items()}
    assert E.vince_col_risultato(nome, risultato, runners) is atteso
