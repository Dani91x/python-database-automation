# -*- coding: utf-8 -*-
"""Test del motore V3 (`omega_v3`). Ogni test e' stato FALSIFICATO: rotto a mano il
pezzo che difende, il test diventa rosso (annotato caso per caso).

I casi numerici vengono dagli esempi dell'utente (16/09 sera):
  · «si puo' bancare anche lo 0-0 HT a quota bassa se i dati confermano» -> ma con la
    griglia vera lo 0-0 al 40' sta all'82 %: NON deve essere candidato;
  · «0-1 al 38' con Any x/y in lay a 65: SI', manca pochissimo alla fine del tempo»
    -> con la griglia vera l'aggregato sta allo 0,64 % contro una p_implicita
    dell'1,46 %: margine 2,3x, candidato.
"""
from __future__ import annotations

import math

import pytest

from Betfair.omega import omega_v3 as V3


# ---------------------------------------------------------------------------
# 1. La griglia
# ---------------------------------------------------------------------------
def test_griglia_normalizzata_e_pura():
    p = V3.Parametri(modello="dixon_coles")
    g1 = V3.griglia_residua(minuto=30, punteggio=(1, 0), periodo="ft", p=p)
    assert abs(sum(g1.values()) - 1.0) < 1e-9
    # PURA: la si puo' rovinare senza che la chiamata dopo cambi (falsificato
    # restituendo il dict memoizzato invece di una copia -> rosso)
    g1[(0, 0)] = 123.0
    g2 = V3.griglia_residua(minuto=30, punteggio=(1, 0), periodo="ft", p=p)
    assert abs(sum(g2.values()) - 1.0) < 1e-9
    assert g2[(0, 0)] < 1.0


def test_griglia_finale_non_torna_mai_indietro():
    """Nessuna cella con meno gol del punteggio corrente."""
    p = V3.Parametri()
    g = V3.griglia_finale(minuto=70, punteggio=(2, 1), periodo="ft", p=p)
    assert all(h >= 2 and a >= 1 for (h, a) in g)


def test_dixon_coles_alza_lo_zero_a_zero():
    """rho negativo (1997) deve ALZARE la cella 0-0 rispetto al Poisson puro.
    Falsificato mettendo rho = 0: le due P diventano uguali e il test cade."""
    base = V3.Parametri(modello="poisson")
    dc = V3.Parametri(modello="dixon_coles", rho=-0.13)
    g0 = V3.griglia_residua(minuto=0, punteggio=(0, 0), periodo="ft", p=base)
    g1 = V3.griglia_residua(minuto=0, punteggio=(0, 0), periodo="ft", p=dc)
    assert g1[(0, 0)] > g0[(0, 0)]


def test_dixon_coles_non_si_applica_a_punteggio_diverso_da_zero_zero():
    """La correzione tau di Dixon-Coles riguarda le celle BASSE DEL RISULTATO
    FINALE: da 1-0 non c'e' piu' nessuna cella 0-0 da correggere."""
    base = V3.Parametri(modello="poisson")
    dc = V3.Parametri(modello="dixon_coles", rho=-0.40)
    g0 = V3.griglia_residua(minuto=20, punteggio=(1, 0), periodo="ft", p=base)
    g1 = V3.griglia_residua(minuto=20, punteggio=(1, 0), periodo="ft", p=dc)
    assert abs(g0[(0, 0)] - g1[(0, 0)]) < 1e-12


def test_bivariato_introduce_correlazione_positiva():
    """Karlis & Ntzoufras 2003: la componente comune lambda3 correla i due lati."""
    senza = V3.Parametri(modello="bivariato", lambda3=0.0)
    con = V3.Parametri(modello="bivariato", lambda3=0.30)

    def cov(g):
        eh = sum(h * v for (h, a), v in g.items())
        ea = sum(a * v for (h, a), v in g.items())
        return sum(h * a * v for (h, a), v in g.items()) - eh * ea

    g0 = V3.griglia_residua(minuto=0, punteggio=(0, 0), periodo="ft", p=senza)
    g1 = V3.griglia_residua(minuto=0, punteggio=(0, 0), periodo="ft", p=con)
    assert cov(g0) < 1e-9 < cov(g1)


def test_gamma_poisson_impara_dai_gol_gia_visti():
    """L'aggiornamento coniugato: 3 gol al 30' devono ALZARE il tasso residuo
    atteso rispetto a 0 gol al 30'. Falsificato ignorando il posteriore (usando
    il prior) -> i due tassi coincidono e il test cade."""
    p = V3.Parametri(modello="gamma_poisson", forma_gamma=5.0)
    lh0, la0 = V3.intensita_residue(minuto=30, punteggio=(0, 0), periodo="ft", p=p)
    lh1, la1 = V3.intensita_residue(minuto=30, punteggio=(2, 1), periodo="ft", p=p)
    assert lh1 + la1 > lh0 + la0


def test_gamma_poisson_ha_la_coda_piu_grassa_del_poisson():
    """Sovradispersione: la binomiale negativa mette piu' massa lontano."""
    poi = V3.Parametri(modello="poisson")
    gp = V3.Parametri(modello="gamma_poisson", forma_gamma=3.0)
    g0 = V3.griglia_residua(minuto=0, punteggio=(0, 0), periodo="ft", p=poi)
    g1 = V3.griglia_residua(minuto=0, punteggio=(0, 0), periodo="ft", p=gp)
    coda0 = sum(v for (h, a), v in g0.items() if h + a >= 6)
    coda1 = sum(v for (h, a), v in g1.items() if h + a >= 6)
    assert coda1 > coda0


def test_profilo_temporale_sposta_i_gol_verso_la_fine():
    """Dixon & Robinson 1998: con c1 > 0 gli ultimi minuti pesano di piu', quindi
    l'esposizione residua al 70' e' MAGGIORE di quella lineare."""
    piatto = V3.Parametri(profilo_c1=0.0)
    crescente = V3.Parametri(profilo_c1=0.8)
    _, r0 = V3.esposizione(70, "ft", piatto)
    _, r1 = V3.esposizione(70, "ft", crescente)
    assert r1 > r0


def test_squilibrio_fa_attaccare_chi_e_sotto():
    p = V3.Parametri(modello="dixon_robinson", beta_squilibrio=0.30)
    lh, la = V3.intensita_residue(minuto=60, punteggio=(0, 2), periodo="ft", p=p)
    assert lh > la      # la squadra di casa e' sotto di 2: attacca di piu'


# ---------------------------------------------------------------------------
# 2. Le probabilita' delle selezioni, aggregati compresi
# ---------------------------------------------------------------------------
NOMI_HT = ["0 - 0", "1 - 0", "0 - 1", "1 - 1", "2 - 0", "0 - 2",
           "2 - 1", "1 - 2", "2 - 2", "Any Unquoted"]
NOMI_CS = ["0 - 0", "1 - 0", "0 - 1", "1 - 1", "2 - 0", "0 - 2", "2 - 1", "1 - 2",
           "2 - 2", "3 - 0", "0 - 3", "3 - 1", "1 - 3", "3 - 2", "2 - 3", "3 - 3",
           "Any Other Home Win", "Any Other Away Win", "Any Other Draw"]


def test_le_selezioni_coprono_esattamente_la_probabilita():
    """Scoreline + aggregati devono fare 1: se un aggregato fosse saltato, mancherebbe
    massa. Falsificato togliendo gli aggregati dai nomi -> somma < 1 e test rosso."""
    p = V3.Parametri()
    for periodo, nomi, punteggio, minuto in (("ht", NOMI_HT, (0, 0), 10),
                                             ("ft", NOMI_CS, (1, 1), 60)):
        ps = V3.probabilita_selezioni(periodo=periodo, minuto=minuto,
                                      punteggio=punteggio, nomi=nomi, p=p)
        assert abs(sum(ps.values()) - 1.0) < 1e-9, (periodo, sum(ps.values()))


def test_zero_a_zero_al_quarantesimo_non_e_raro():
    """L'esempio dell'utente misurato sulla griglia vera: al 40' da 0-0 lo 0-0 HT
    sta sopra il 75 %. Chi lo bancasse lo farebbe contro i dati."""
    ps = V3.probabilita_selezioni(periodo="ht", minuto=40, punteggio=(0, 0),
                                  nomi=NOMI_HT, p=V3.Parametri())
    assert ps["0 - 0"] > 0.75


# ---------------------------------------------------------------------------
# 3. Il cancello del margine
# ---------------------------------------------------------------------------
def _runner(nome, prezzo, size=50.0, sid=None):
    return V3.RunnerV3(selection_id=sid or abs(hash(nome)) % 10 ** 6, name=nome,
                       lay_price=prezzo, lay_size=size, back_price=None, back_size=0.0)


def test_p_implicita_e_la_stessa_formula_della_produzione():
    assert abs(V3.p_implicita(65.0, 0.05) - (0.95 / (65.0 - 0.05))) < 1e-12
    assert V3.p_implicita(float("nan"), 0.05) is None
    assert V3.p_implicita(1.0, 0.05) is None


def test_esempio_utente_0_1_al_38_any_unquoted_a_65_e_candidato():
    """«0-1 al 38' con Any x/y in lay a 65: SI'». Con la griglia vera l'aggregato
    sta allo 0,6 % contro l'1,46 % implicito: margine oltre 2, passa."""
    p = V3.Parametri()
    ps = V3.probabilita_selezioni(periodo="ht", minuto=38, punteggio=(0, 1),
                                  nomi=NOMI_HT, p=p)
    runners = [_runner("Any Unquoted", 65.0)]
    c = V3.candidato(periodo="ht", runners=runners, probabilita=ps,
                     punteggio=(0, 1), k_default=2.0, distanza_minima_gol=1)
    assert c is not None
    assert c.name == "Any Unquoted"
    assert c.size == 1.0
    assert c.margine >= 2.0
    assert c.ev > 0


def test_il_margine_k_e_un_cancello_vero():
    """FALSIFICAZIONE del cancello: la stessa selezione con k = 1 passa, con k = 4 no.
    Se il cancello fosse inerte i due esiti sarebbero uguali."""
    p = V3.Parametri()
    ps = V3.probabilita_selezioni(periodo="ht", minuto=38, punteggio=(0, 1),
                                  nomi=NOMI_HT, p=p)
    runners = [_runner("Any Unquoted", 65.0)]
    assert V3.candidato(periodo="ht", runners=runners, probabilita=ps,
                        punteggio=(0, 1), k_default=1.0, distanza_minima_gol=1) is not None
    assert V3.candidato(periodo="ht", runners=runners, probabilita=ps,
                        punteggio=(0, 1), k_default=4.0, distanza_minima_gol=1) is None


def test_mai_il_risultato_corrente():
    """Il punteggio di adesso non si banca MAI: fra un attimo potrebbe essere il
    risultato finale del periodo e la liability e' gia' impegnata."""
    p = V3.Parametri()
    ps = V3.probabilita_selezioni(periodo="ht", minuto=40, punteggio=(1, 1),
                                  nomi=NOMI_HT, p=p)
    # prezzo assurdamente generoso: solo la regola puo' scartarlo
    runners = [_runner("1 - 1", 900.0)]
    c = V3.candidato(periodo="ht", runners=runners, probabilita=ps, punteggio=(1, 1),
                     k_default=2.0, distanza_minima_gol=1)
    assert c is None


def test_mai_un_risultato_irraggiungibile():
    p = V3.Parametri()
    ps = V3.probabilita_selezioni(periodo="ft", minuto=60, punteggio=(2, 1),
                                  nomi=NOMI_CS, p=p)
    c = V3.candidato(periodo="ft", runners=[_runner("1 - 0", 500.0)], probabilita=ps,
                     punteggio=(2, 1), k_default=2.0)
    assert c is None


def test_la_quota_piu_alta_non_vince_per_diritto():
    """Il contrario del motore v1 (`select_lay_runner` = quota piu' alta, `omega_engine.py:127`):
    fra due selezioni vince quella con P piu' bassa che passa il margine, anche se e'
    quella con la quota PIU' BASSA. E' l'ordine dell'utente: «NON MI INTERESSA LA QUOTA».

    Da 1-1 al 60': «Any Other Draw» vuol dire 4-4 o oltre (0,012 %), mentre il 3-3 e'
    quaranta volte piu' probabile (0,47 %). Quotando l'aggregato 40 e il 3-3 600, vince
    l'aggregato a quota 40."""
    p = V3.Parametri()
    ps = V3.probabilita_selezioni(periodo="ft", minuto=60, punteggio=(1, 1),
                                  nomi=NOMI_CS, p=p)
    assert ps["Any Other Draw"] < ps["3 - 3"]
    runners = [_runner("3 - 3", 600.0), _runner("Any Other Draw", 40.0)]
    c = V3.candidato(periodo="ft", runners=runners, probabilita=ps, punteggio=(1, 1),
                     k_default=2.0)
    assert c is not None
    assert c.name == "Any Other Draw"
    assert c.price == 40.0
    # il 3-3 a 600 e' stato scartato, e per il motivo giusto: margine insufficiente
    assert any(n == "3 - 3" and m.startswith("margine") for n, m in c.scartati)


def test_il_veto_empirico_puo_bloccare_un_ingresso():
    """P_nostra = max(modello, dato storico). Falsificato usando il solo modello:
    l'ingresso passa e il test cade."""
    p = V3.Parametri()
    ps = V3.probabilita_selezioni(periodo="ht", minuto=38, punteggio=(0, 1),
                                  nomi=NOMI_HT, p=p)
    runners = [_runner("Any Unquoted", 65.0)]
    senza = V3.candidato(periodo="ht", runners=runners, probabilita=ps,
                         punteggio=(0, 1), k_default=2.0, distanza_minima_gol=1)
    assert senza is not None
    con = V3.candidato(periodo="ht", runners=runners, probabilita=ps, punteggio=(0, 1),
                       k_default=2.0, distanza_minima_gol=1,
                       p_empirica=lambda nome: (0.012, 900))   # 1,2 % > 1,46 %/2
    assert con is None


def test_la_tabella_k_per_secchio_viene_usata():
    """Con un k alto SOLO nel secchio della selezione, l'ingresso deve sparire."""
    p = V3.Parametri()
    ps = V3.probabilita_selezioni(periodo="ht", minuto=38, punteggio=(0, 1),
                                  nomi=NOMI_HT, p=p)
    runners = [_runner("Any Unquoted", 65.0)]
    p_imp = V3.p_implicita(65.0, 0.05)
    etichetta = "fascia_x"
    c = V3.candidato(periodo="ht", runners=runners, probabilita=ps, punteggio=(0, 1),
                     distanza_minima_gol=1, secchio_di=lambda _p: etichetta,
                     k_tab={("ht", etichetta): 10.0}, k_default=2.0)
    assert c is None
    assert p_imp is not None


def test_il_cap_di_liability_di_gamba_scarta_la_selezione():
    p = V3.Parametri()
    ps = V3.probabilita_selezioni(periodo="ft", minuto=60, punteggio=(1, 1),
                                  nomi=NOMI_CS, p=p)
    runners = [_runner("Any Other Draw", 300.0)]
    assert V3.candidato(periodo="ft", runners=runners, probabilita=ps, punteggio=(1, 1),
                        k_default=2.0, cap_liability_gamba=0.0) is not None
    assert V3.candidato(periodo="ft", runners=runners, probabilita=ps, punteggio=(1, 1),
                        k_default=2.0, cap_liability_gamba=120.0) is None


def test_lo_stake_e_sempre_un_euro():
    p = V3.Parametri()
    ps = V3.probabilita_selezioni(periodo="ht", minuto=38, punteggio=(0, 1),
                                  nomi=NOMI_HT, p=p)
    c = V3.candidato(periodo="ht", runners=[_runner("Any Unquoted", 65.0)],
                     probabilita=ps, punteggio=(0, 1), distanza_minima_gol=1,
                     k_default=2.0)
    assert c is not None and c.size == V3.STAKE_STANDARD == 1.0
    assert abs(c.liability - (65.0 - 1.0)) < 1e-9


def test_ev_della_gamba_e_quello_della_formula():
    """EV = (1-P)*s*(1-c) - P*s*(L-1), e con P = p_implicita/k vale s(1-c)(1-1/k)."""
    L, c, s, k = 65.0, 0.05, 1.0, 2.0
    p_imp = V3.p_implicita(L, c)
    ev = V3.ev_gamba(p_imp / k, L, s, c)
    assert abs(ev - s * (1 - c) * (1 - 1.0 / k)) < 1e-6


# ---------------------------------------------------------------------------
# 4. La finestra
# ---------------------------------------------------------------------------
def test_finestre_di_ingresso():
    assert V3.in_finestra("ht", 30) and not V3.in_finestra("ht", 10)
    assert V3.in_finestra("ft", 60) and not V3.in_finestra("ft", 90)
    assert not V3.in_finestra("ht", None)
    f = V3.finestra_ingresso("ft", minuto_min=80, minuto_max=55)
    assert (f.minuto_min, f.minuto_max) == (55, 80)     # si riordina, non si rompe


# ---------------------------------------------------------------------------
# 5. L'uscita: profitto bloccabile, traiettoria, proposta
# ---------------------------------------------------------------------------
def test_profitto_bloccabile_e_la_formula_del_green_up():
    pos = V3.Posizione("ft", "3 - 3", lay_price=100.0, size=1.0)
    b = V3.profitto_bloccabile(pos, back_price=200.0, back_size=10.0, commissione=0.05)
    assert b is not None
    assert abs(b.back_size - 0.5) < 1e-9          # sb = s*L/B = 1*100/200
    assert abs(b.profitto - 0.5 * 0.95) < 1e-6    # (s - sb) al netto


def test_bloccare_in_perdita_col_rischio_ancora_basso_non_si_propone():
    """Prezzo mosso CONTRO (back 50 su un lay a 100): il bloccabile e' negativo.

    Finche' TENERE vale piu' di quella perdita certa, non si propone niente: e'
    la memoria del 12/09 («le chiusure distruggono valore») scritta in codice.
    Qui la P del bancato e' lo 0,5%: l'EV di tenere e' POSITIVO, chiudere
    sarebbe regalare un euro."""
    pos = V3.Posizione("ft", "3 - 3", lay_price=100.0, size=1.0)
    b = V3.profitto_bloccabile(pos, back_price=50.0, back_size=100.0)
    assert b is not None and b.profitto < 0
    pr = V3.proposta_uscita(pos, minuto=70, punteggio=(2, 2), back_price=50.0,
                            back_size=100.0, p_evento=0.005, p=V3.Parametri())
    assert pr.ev_tenere > pr.profitto_bloccabile
    assert pr.proponi is False
    assert pr.motivo_codice == "bloccabile_non_positivo"


def test_in_perdita_si_propone_la_PROTEZIONE_quando_tenere_costa_di_piu():
    """ORDINE DELL'UTENTE 17/09: «la scheda dove approvo le uscite, SIA IN PROFIT
    CHE IN LOSS».

    Stessa posizione del test qui sopra, stesso prezzo, stesso bloccabile
    negativo: cambia SOLO la P che il risultato bancato esca (il gol che ha
    avvicinato la cella). A P=30% tenere vale -29,03 EUR contro -1,00 EUR di
    perdita certa: chiudere e' il male minore, e il bot lo deve CHIEDERE.
    Fino al 17/09 questo caso usciva da `bloccabile_non_positivo` e la Control
    Room non vedeva niente — una gamba che stava perdendo restava muta."""
    pos = V3.Posizione("ft", "3 - 3", lay_price=100.0, size=1.0)
    pr = V3.proposta_uscita(pos, minuto=70, punteggio=(2, 2), back_price=50.0,
                            back_size=100.0, p_evento=0.30, p=V3.Parametri())
    assert pr.proponi is True
    assert pr.motivo_codice == "protezione"
    assert pr.profitto_bloccabile < 0          # e' una PERDITA che si blocca
    assert pr.ev_tenere < pr.profitto_bloccabile
    # i numeri che la scheda deve mostrare ci sono tutti
    assert pr.back_price == 50.0 and pr.back_size > 0 and pr.p_evento == 0.30


def test_un_cap_scattato_propone_a_prescindere_dall_EV():
    """Un tetto di rischio non chiede all'EV il permesso: chiede di ridurre il
    rischio, e il motivo lo dice al trader (`cap`, non `profitto`)."""
    pos = V3.Posizione("ft", "3 - 3", lay_price=100.0, size=1.0)
    senza = V3.proposta_uscita(pos, minuto=70, punteggio=(2, 2), back_price=50.0,
                               back_size=100.0, p_evento=0.005, p=V3.Parametri())
    assert senza.proponi is False              # senza cap: si tiene
    con = V3.proposta_uscita(pos, minuto=70, punteggio=(2, 2), back_price=50.0,
                             back_size=100.0, p_evento=0.005, p=V3.Parametri(),
                             cap_scattato="v3_daily_loss_cap")
    assert con.proponi is True and con.motivo_codice == "cap"
    assert "v3_daily_loss_cap" in con.testo


def test_la_soglia_di_rischio_e_SPENTA_per_default():
    """`p_lose_max` = 0 (default): il ramo `rischio` non esiste. Accendendola,
    esiste. Nessuna soglia nuova accesa di iniziativa (regola dell'utente)."""
    pos = V3.Posizione("ft", "3 - 3", lay_price=100.0, size=1.0)
    spenta = V3.proposta_uscita(pos, minuto=70, punteggio=(2, 2), back_price=400.0,
                                back_size=100.0, p_evento=0.40, p=V3.Parametri())
    assert spenta.motivo_codice != "rischio"
    accesa = V3.proposta_uscita(pos, minuto=70, punteggio=(2, 2), back_price=400.0,
                                back_size=100.0, p_evento=0.40, p=V3.Parametri(),
                                p_lose_max=0.25)
    assert accesa.proponi is True and accesa.motivo_codice == "rischio"


def test_senza_controparte_non_si_propone():
    pos = V3.Posizione("ft", "3 - 3", lay_price=100.0, size=1.0)
    pr = V3.proposta_uscita(pos, minuto=88, punteggio=(2, 2), back_price=400.0,
                            back_size=0.05, p_evento=0.001, p=V3.Parametri())
    assert pr.proponi is False and pr.motivo_codice == "controparte_insufficiente"


def test_la_traiettoria_del_bloccabile_cresce_se_il_punteggio_regge():
    """E' il cuore dell'uscita di V3: il tempo che passa lavora per il layer."""
    pos = V3.Posizione("ft", "3 - 3", lay_price=100.0, size=1.0)
    traj = V3.traiettoria_bloccabile(pos, minuto=60, punteggio=(2, 2),
                                     p=V3.Parametri(), passo=5)
    assert len(traj) >= 3
    assert traj[-1].p_evento < traj[0].p_evento
    assert traj[-1].bloccabile_atteso > traj[0].bloccabile_atteso


def test_quando_il_quadro_peggiora_si_propone_di_bloccare():
    """IL CASO VERO in cui una proposta ha senso: un gol ha reso il risultato bancato
    vicino (3-2 al 75' su un lay del 3-3), la P e' schizzata al 15 % e tenere ha EV
    NEGATIVO, mentre il book offre ancora un back che blocca un profitto positivo.
    E' il contrario delle 5 chiusure sbagliate del 12/09: li' si chiudeva con la P
    bassa e l'EV alto."""
    pos = V3.Posizione("ft", "3 - 3", lay_price=100.0, size=1.0)
    pr = V3.proposta_uscita(pos, minuto=75, punteggio=(3, 2), back_price=130.0,
                            back_size=50.0, p_evento=0.15, p=V3.Parametri())
    assert pr.ev_tenere < 0
    assert pr.profitto_bloccabile > 0
    assert pr.proponi is True
    assert pr.motivo_codice == "blocca_il_profitto"
    assert "blocca" in pr.testo


def test_con_la_p_bassa_si_tiene_anche_col_prezzo_ottimo():
    """Il 12/09 misurato: su un lay la liability e' GIA' impegnata, quindi con una P
    bassa tenere vale quasi l'incasso pieno e quasi nessun prezzo di chiusura lo
    batte. Falsificato togliendo il confronto con `ev_tenere`: si proporrebbe, e
    sarebbe la perdita del 12/09 rifatta."""
    pos = V3.Posizione("ft", "3 - 3", lay_price=100.0, size=1.0)
    pr = V3.proposta_uscita(pos, minuto=89, punteggio=(2, 2), back_price=900.0,
                            back_size=50.0, p_evento=0.0005, p=V3.Parametri())
    assert pr.profitto_bloccabile > 0.8       # sarebbe pure un bel gruzzolo
    assert pr.ev_tenere > pr.profitto_bloccabile
    assert pr.proponi is False
    assert pr.motivo_codice == "tenere_vale_di_piu"


def test_se_aspettare_vale_di_piu_non_si_propone():
    """FALSIFICAZIONE della traiettoria: al 50' da 0-0 il bloccabile (0,22 EUR) batte
    gia' l'EV di tenere (0,15 EUR) — chi guardasse solo quei due numeri proporrebbe.
    Ma se il punteggio regge, fra cinque minuti se ne bloccano 0,83: si aspetta."""
    pos = V3.Posizione("ft", "3 - 3", lay_price=100.0, size=1.0)
    pr = V3.proposta_uscita(pos, minuto=50, punteggio=(0, 0), back_price=130.0,
                            back_size=50.0, p_evento=0.008, p=V3.Parametri())
    assert pr.profitto_bloccabile > pr.ev_tenere      # i due numeri "facili" direbbero SI'
    assert pr.meglio_aspettare is True
    assert pr.proponi is False
    assert pr.motivo_codice == "aspettare_vale_di_piu"


def test_il_valore_dell_attesa_e_pesato_con_la_tenuta_del_punteggio():
    """LA CORREZIONE CHE IL BANCO HA IMPOSTO: guardando solo il ramo «non succede
    niente» aspettare conviene SEMPRE, e non si chiuderebbe mai. Il valore
    dell'attesa va pesato con P(il punteggio regge), e nell'altro ramo si torna a
    valere quello che vale tenere oggi. Falsificato mettendo `p_invariato = 1`:
    `valore_attesa` coincide con `bloccabile_atteso` e il test cade."""
    pos = V3.Posizione("ft", "3 - 3", lay_price=100.0, size=1.0)
    traj = V3.traiettoria_bloccabile(pos, minuto=55, punteggio=(2, 2),
                                     p=V3.Parametri(), passo=5, p_evento_ora=0.02)
    assert traj[0].p_invariato == pytest.approx(1.0)
    assert traj[-1].p_invariato < 0.6          # trenta minuti da 2-2: spesso si segna
    assert all(traj[i].p_invariato >= traj[i + 1].p_invariato for i in range(len(traj) - 1))
    ev_ora = V3.ev_di_tenere(pos, p_evento=0.02)
    for t in traj:
        lo, hi = min(t.bloccabile_atteso, ev_ora), max(t.bloccabile_atteso, ev_ora)
        assert lo - 1e-9 <= t.valore_attesa <= hi + 1e-9
    # e il peso morde: alla fine il valore atteso e' PIU' BASSO del ramo fortunato
    assert traj[-1].valore_attesa < traj[-1].bloccabile_atteso


def test_la_proposta_non_esegue_niente():
    """G1: in V3 non esiste una funzione che chiuda. `proposta_uscita` ritorna un
    verdetto e dei numeri; il modulo non ha ne' I/O ne' piazzamenti."""
    import inspect
    sorgente = inspect.getsource(V3)
    for vietata in ("place_order", "requests.", "supabase", "def chiudi", "def esegui"):
        assert vietata not in sorgente, vietata


# ---------------------------------------------------------------------------
# 6. Robustezza agli ingressi sporchi (i finti parlano come il vero)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("prezzo", [None, float("nan"), float("inf"), 1.0, 0.5, -3.0])
def test_prezzi_impossibili_non_diventano_candidati(prezzo):
    p = V3.Parametri()
    ps = V3.probabilita_selezioni(periodo="ht", minuto=38, punteggio=(0, 1),
                                  nomi=NOMI_HT, p=p)
    r = V3.RunnerV3(selection_id=1, name="Any Unquoted", lay_price=prezzo, lay_size=50.0)
    assert V3.candidato(periodo="ht", runners=[r], probabilita=ps, punteggio=(0, 1),
                        distanza_minima_gol=1, k_default=2.0) is None


def test_size_non_finita_non_passa_la_liquidita():
    p = V3.Parametri()
    ps = V3.probabilita_selezioni(periodo="ht", minuto=38, punteggio=(0, 1),
                                  nomi=NOMI_HT, p=p)
    r = V3.RunnerV3(selection_id=1, name="Any Unquoted", lay_price=65.0,
                    lay_size=float("nan"))
    assert V3.candidato(periodo="ht", runners=[r], probabilita=ps, punteggio=(0, 1),
                        distanza_minima_gol=1, k_default=2.0) is None


def test_fusione_col_mercato_sta_in_mezzo():
    p = V3.Parametri(peso_modello=0.5)
    fusa = V3.fondi_col_mercato(0.01, 0.04, p)
    assert 0.01 < fusa < 0.04
    # senza prezzo di mercato non si inventa nulla
    assert V3.fondi_col_mercato(0.01, None, p) == 0.01
    # peso 1 = solo modello
    assert V3.fondi_col_mercato(0.01, 0.04, V3.Parametri(peso_modello=1.0)) == 0.01


def test_peso_per_fascia_vince_sul_peso_unico():
    p = V3.Parametri(peso_modello=1.0, peso_per_fascia=((0.02, 0.0), (1.01, 1.0)))
    assert V3.peso_fusione(0.01, p) == 0.0
    assert V3.peso_fusione(0.50, p) == 1.0
