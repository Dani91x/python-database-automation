# -*- coding: utf-8 -*-
"""LA MEMOIZZAZIONE DEL MODELLO NON CAMBIA UN NUMERO.

Il 16/09 il profilo del replay (`certifica mike 35760084 --scenari base`) ha
detto che l'**83,6 %** del tempo stava dentro `omega_model.lambdas_from_pre_ko`:
`_poisson_grid` veniva chiamata **6.779.932 volte per 1.586 argomenti
distinti** in una sola partita, perche' la doppia bisezione si rifa a ogni giro
del bot su un `pre_ko` CONGELATO.

Le tre funzioni memoizzate sono PURE. Questo file lo mette alla prova nel modo
che conta: si prendono gli argomenti VERI con cui il replay le chiama, si
calcola il risultato con la cache e senza, e si confrontano ELEMENTO PER
ELEMENTO. Se un solo numero cambiasse, la memoizzazione non sarebbe una
memoizzazione: sarebbe una modifica della strategia.

E si falsifica: una chiave che ignora un argomento deve far comparire griglie
diverse, altrimenti questo file non sta misurando niente.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import functools

import pytest

from Betfair.omega import omega_model as M


# ---------------------------------------------------------------------------
# gli argomenti VERI con cui il replay chiama il modello
# ---------------------------------------------------------------------------
def argomenti_reali(quanti: int = 200):
    """Gli argomenti che escono dalla catena vera, non numeri scelti a mano.

    `lambdas_from_pre_ko` fa la doppia bisezione (`total_goals_from_1x2` ->
    `split_lambdas_1x2` -> `_full_match_1x2` -> `residual_grid` ->
    `_poisson_grid`) su quote 1X2 pre-KO: si registrano gli argomenti che
    arrivano davvero al fondo della catena.
    """
    visti = []
    vero = M._poisson_grid_memo.__wrapped__

    def spia(lh, la, rho, max_goals, dixon_coles):
        if len(visti) < quanti:
            visti.append((lh, la, rho, max_goals, dixon_coles))
        return vero(lh, la, rho, max_goals, dixon_coles)

    memo = M._poisson_grid_memo
    M._poisson_grid_memo = spia
    try:
        # tre partite con favoriti diversi: il pre-KO congelato e' il dato vero
        for pre in ({"home": 1.75, "draw": 3.6, "away": 4.8},
                    {"home": 2.9, "draw": 3.2, "away": 2.5},
                    {"home": 1.25, "draw": 6.0, "away": 12.0}):
            M.lambdas_from_pre_ko(pre)
            if len(visti) >= quanti:
                break
    finally:
        M._poisson_grid_memo = memo
    return visti


def test_gli_argomenti_reali_si_raccolgono():
    """Se la catena cambiasse e non arrivasse piu' al fondo, i test qui sotto
    passerebbero a vuoto: e' il difetto 29 del catalogo."""
    arg = argomenti_reali(200)
    assert len(arg) == 200, f"raccolti solo {len(arg)} argomenti reali"
    assert len({a[:2] for a in arg}) > 20, "gli argomenti sono tutti uguali"


# ---------------------------------------------------------------------------
# cache e non-cache: identici elemento per elemento
# ---------------------------------------------------------------------------
def test_poisson_grid_con_cache_identica_a_senza():
    arg = argomenti_reali(200)
    senza = M._poisson_grid_memo.__wrapped__
    for lh, la, rho, mg, dc in arg:
        a = senza(lh, la, rho, mg, dc)
        b = M._poisson_grid(lh, la, rho, mg, dc)
        assert a.keys() == b.keys()
        for k in a:
            assert a[k] == b[k], f"cella {k} diversa su ({lh},{la},{rho},{mg},{dc})"


def test_residual_grid_con_cache_identica_a_senza():
    arg = argomenti_reali(200)
    senza = M._residual_grid_memo.__wrapped__
    for lh, la, rho, mg, dc in arg:
        for cv in (0.0, M.DEFAULT_LAMBDA_CV):
            a = senza(lh, la, rho, mg, dc, cv)
            b = M.residual_grid(lh, la, rho, mg, dixon_coles=dc, cv=cv)
            assert a.keys() == b.keys()
            for k in a:
                assert a[k] == b[k], f"cella {k} diversa (cv={cv})"


def test_full_match_1x2_con_cache_identica_a_senza():
    arg = argomenti_reali(200)
    senza = M._full_match_1x2.__wrapped__
    for lh, la, rho, _mg, _dc in arg:
        assert senza(lh, la, rho) == M._full_match_1x2(lh, la, rho)


def test_la_catena_intera_da_gli_stessi_lambda():
    """Il numero che conta per i bot non e' la griglia: sono i lambda che escono
    dalla catena. Con e senza cache devono essere identici, bit per bit."""
    pre = {"home": 1.75, "draw": 3.6, "away": 4.8}
    M._poisson_grid_memo.cache_clear()
    M._residual_grid_memo.cache_clear()
    M._full_match_1x2.cache_clear()
    primo = M.lambdas_from_pre_ko(pre)          # tutte le cache vuote
    secondo = M.lambdas_from_pre_ko(pre)        # tutte le cache piene
    assert primo == secondo
    assert primo is not None and primo[0] > 0 and primo[1] > 0


# ---------------------------------------------------------------------------
# il risultato consegnato e' MUTABILE senza danno: e' una copia
# ---------------------------------------------------------------------------
def test_chi_modifica_la_griglia_non_corrompe_la_cache():
    """La griglia e' un `dict`: se si consegnasse l'oggetto memorizzato, un
    chiamante che lo modifica avvelenerebbe tutte le chiamate successive."""
    prima = M._poisson_grid(1.4, 1.1, M.DEFAULT_RHO, 10, True)
    prima[(0, 0)] = -999.0
    prima.pop((1, 1), None)
    dopo = M._poisson_grid(1.4, 1.1, M.DEFAULT_RHO, 10, True)
    assert dopo[(0, 0)] != -999.0 and (1, 1) in dopo

    prima_r = M.residual_grid(1.4, 1.1, M.DEFAULT_RHO, 10, dixon_coles=True)
    prima_r[(0, 0)] = -999.0
    dopo_r = M.residual_grid(1.4, 1.1, M.DEFAULT_RHO, 10, dixon_coles=True)
    assert dopo_r[(0, 0)] != -999.0


def test_il_tetto_della_cache_e_dichiarato_e_limitato():
    """Una cache senza tetto su un servizio che gira per giorni e' una perdita
    di memoria. Il tetto e' dimensionato sui 1.586 argomenti distinti misurati."""
    assert M.CACHE_GRIGLIE >= 1586 * 2, "margine troppo stretto sul misurato"
    assert M.CACHE_GRIGLIE <= 8192, "tetto troppo largo: ~16 KB per griglia"
    for f in (M._poisson_grid_memo, M._residual_grid_memo, M._full_match_1x2):
        assert f.cache_info().maxsize == M.CACHE_GRIGLIE


# ---------------------------------------------------------------------------
# FALSIFICAZIONE: una chiave che perde un argomento deve far rosso
# ---------------------------------------------------------------------------
# Ogni argomento cambia la griglia: se una chiave ne ignorasse uno, due
# chiamate DIVERSE si prenderebbero la stessa griglia. Qui lo si provoca:
# per ogni posizione si costruisce un secondo argomento che differisce SOLO in
# quella posizione, e si verifica (a) che la funzione vera dia griglie diverse,
# (b) che la cache monca dia la stessa — cioe' che sarebbe un difetto, e che il
# confronto elemento per elemento lo vede.
_PERTURBA = {
    0: lambda a: (a[0] * 1.1, a[1], a[2], a[3], a[4]),
    1: lambda a: (a[0], a[1] * 1.1, a[2], a[3], a[4]),
    2: lambda a: (a[0], a[1], -0.05, a[3], a[4]),
    3: lambda a: (a[0], a[1], a[2], 8, a[4]),
    4: lambda a: (a[0], a[1], a[2], a[3], not a[4]),
}


@pytest.mark.parametrize("ignora", sorted(_PERTURBA))
def test_falsificazione_una_chiave_che_ignora_un_argomento(ignora):
    senza = M._poisson_grid_memo.__wrapped__
    memoria = {}

    def sbagliata(*arg):
        chiave = tuple(v for i, v in enumerate(arg) if i != ignora)
        if chiave not in memoria:
            memoria[chiave] = senza(*arg)
        return memoria[chiave]

    arg = argomenti_reali(200)
    viste_diverse = 0
    difetti = 0
    for a in arg:
        b = _PERTURBA[ignora](a)
        ga, gb = senza(*a), senza(*b)
        if ga.keys() != gb.keys() or any(ga[k] != gb[k] for k in ga):
            viste_diverse += 1
            fa, fb = sbagliata(*a), sbagliata(*b)
            if fa is fb or (fa.keys() == fb.keys() and all(fa[k] == fb[k] for k in fa)):
                difetti += 1
    assert viste_diverse > 0, (
        f"cambiare l'argomento {ignora} non cambia mai la griglia: allora non "
        f"e' un argomento che conta, e il campione non serve a falsificare")
    assert difetti == viste_diverse, (
        f"la cache monca sull'argomento {ignora} avrebbe dovuto restituire la "
        f"STESSA griglia a chiamate diverse in tutti i {viste_diverse} casi, "
        f"ne ha sbagliati {difetti}")


def test_falsificazione_arrotondare_la_chiave_cambierebbe_i_numeri():
    """La chiave e' fatta dagli argomenti COSI' COME ARRIVANO. Arrotondarli
    sarebbe una modifica di comportamento travestita da ottimizzazione: qui si
    mostra che cambierebbe davvero le griglie."""
    senza = M._poisson_grid_memo.__wrapped__
    arg = argomenti_reali(200)
    cambiate = 0
    for lh, la, rho, mg, dc in arg:
        vera = senza(lh, la, rho, mg, dc)
        arrotondata = senza(round(lh, 2), round(la, 2), rho, mg, dc)
        if any(vera[k] != arrotondata[k] for k in vera):
            cambiate += 1
    assert cambiate > len(arg) // 2, (
        f"arrotondare la chiave cambierebbe solo {cambiate} griglie su "
        f"{len(arg)}: il campione non e' rappresentativo")
