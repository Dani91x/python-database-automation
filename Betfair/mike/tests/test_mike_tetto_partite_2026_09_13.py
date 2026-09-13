"""IL TETTO DELLE PARTITE VA DOVE NASCONO I SOLDI (13/09/2026).

``max_open_matches`` era controllato in UN SOLO punto del repo, al momento in cui
si ARMA una partita, e li' lo stato ``WATCH`` non contava — per una ragione che
in se' e' giusta: osservare non costa niente.

Il difetto e' che il conto si rifaceva da zero a ogni giro. Primo giro: arma
dieci ``WATCH``, e le partite con posizione sono zero. Secondo giro: sempre zero,
e ne arma altre dieci. E cosi' via fino a esaurire il feed. Poi, quando ognuna di
quelle ``WATCH`` arriva alla propria finestra d'ingresso, ENTRA — perche' al
momento dell'ingresso non c'era nessun controllo.

Misurato il 13/09 alle 21:37: **44 partite esposte con un tetto scritto "10"**.
Con 10 EUR di stake sono 440 EUR impegnati invece di 100. E lo scanner serve le
quote in gioco solo alle prime 40, quindi le ultime restavano senza copertura e
senza uscita.

La regola che questi test fissano:

    si blocca solo una via d'INGRESSO, mai una via d'uscita.
"""
from __future__ import annotations

from Betfair.mike import engine as E


def _gamba(**kw):
    base = dict(ref="r1", role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                side="back", price=1.50, size=10.0, matched=0.0, status="open")
    base.update(kw)
    return E.Leg(**base)


# ---------------------------------------------------------------------------
# chi occupa un posto e chi no
# ---------------------------------------------------------------------------
def test_chi_guarda_e_basta_non_occupa_un_posto():
    assert E.ha_esposizione("WATCH", []) is False
    assert E.ha_esposizione("IDLE_LIVE", []) is False


def test_chi_ha_uno_stato_operativo_occupa_un_posto():
    for st in ("PRE_ENTRY_PENDING", "PRE_OPEN", "HOLD", "LIVE_UNCOVERED",
               "LIVE_COVER_PENDING", "LIVE_KO_GREEN"):
        assert E.ha_esposizione(st, []) is True, st


def test_una_partita_REGOLATA_libera_il_posto():
    for st in E.TERMINAL_STATES:
        assert E.ha_esposizione(st, [_gamba(matched=10.0)]) is False, st


def test_una_gamba_ABBINATA_occupa_il_posto_anche_in_WATCH():
    """Caso limite reale: lo stato e' tornato a WATCH ma una gamba e' rimasta
    abbinata. I soldi sono sul mercato: il posto e' occupato."""
    assert E.ha_esposizione("WATCH", [_gamba(matched=10.0, status="open")]) is True


def test_un_ordine_VIVO_occupa_il_posto_anche_senza_abbinato():
    viva = _gamba(matched=0.0, status="pending")
    assert viva.is_live, "presupposto del test"
    assert E.ha_esposizione("WATCH", [viva]) is True


def test_una_gamba_archiviata_non_occupa_piu_il_posto():
    """Il ciclo e' stato chiuso: il capitale non e' piu' a rischio e il posto si
    libera. E' la stessa regola con cui lo scanner decide chi ha diritto alle
    quote in gioco: due tetti che contassero cose diverse si darebbero torto a
    vicenda, e una partita potrebbe restare esposta senza quote."""
    assert E.ha_esposizione("WATCH", [_gamba(matched=10.0, archived=True)]) is False


# ---------------------------------------------------------------------------
# cosa si toglie e cosa NON si tocca mai
# ---------------------------------------------------------------------------
def _decisione(*azioni, stato="WATCH"):
    return E.Decision(state=stato, actions=list(azioni), reason="prova")


def test_col_tetto_pieno_si_toglie_l_apertura():
    d = _decisione(E.Action(kind="place", role="under_entry", market=E.MARKET_OU35,
                            selection=E.SEL_UNDER, side="back", price=1.5, size=10.0))
    out = E._strip_openings(d, "tetto partite aperte raggiunto", "WATCH")
    assert out.actions == []
    assert out.state == "WATCH", "senza ordini da piazzare lo stato NON avanza"
    assert "tetto" in out.reason


def test_col_tetto_pieno_l_USCITA_passa_sempre():
    """La regola che conta: non si blocca mai una via d'uscita. Un cash-out, un
    green, una copertura non sono aperture e devono passare anche a tetto pieno —
    bloccarli lascerebbe una posizione senza modo di chiudersi."""
    uscita = E.Action(kind="place", role="under_green", market=E.MARKET_OU35,
                      selection=E.SEL_UNDER, side="lay", price=1.45, size=10.0)
    out = E._strip_openings(_decisione(uscita, stato="PRE_OPEN"), "tetto", "PRE_OPEN")
    assert out.actions == [uscita]


def test_col_tetto_pieno_l_ANNULLO_passa_sempre():
    annullo = E.Action(kind="cancel", ref="r1", role="under_entry",
                       market=E.MARKET_OU35, selection=E.SEL_UNDER)
    out = E._strip_openings(_decisione(annullo, stato="PRE_OPEN"), "tetto", "PRE_OPEN")
    assert out.actions == [annullo]


def test_la_COPERTURA_e_un_apertura_ma_su_una_partita_gia_dentro():
    """``over_cover`` sta in OPENING_ROLES, quindi ``_strip_openings`` la
    toglierebbe. Non e' un problema: il servizio non applica MAI il tetto a una
    partita gia' esposta, e una copertura esiste solo su una partita esposta.
    Questo test fissa il presupposto, perche' se un domani il servizio applicasse
    il tetto anche alle partite dentro, si smetterebbe di coprire — e coprire e'
    la cosa che riduce il rischio."""
    assert "over_cover" in E.OPENING_ROLES


def test_le_uscite_non_sono_aperture():
    for ruolo in ("under_green", "ko_green", "over_green"):
        if ruolo in E.ROLES:
            assert ruolo not in E.OPENING_ROLES, ruolo
