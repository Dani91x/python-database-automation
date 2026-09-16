# -*- coding: utf-8 -*-
"""LA CERTIFICAZIONE GIRA NELLA SUITE (`pytest -m cert`).

Ordine dell'utente del 16/09: il banco e' «da oggi standard e usato di default».
Un banco che gira solo quando qualcuno se lo ricorda non protegge niente: qui la
certificazione di OGNI bot registrato viene rieseguita su un CAMPIONE RIDOTTO di
registrazioni reali a ogni giro della suite. Se una modifica al bot gli fa
violare una regola della sua spec, il rosso arriva subito.

Campione: poche partite scelte perche' il bot ci fa davvero qualcosa (apre,
copre, esce) e perche' sono corte. Il replay completo resta il comando:

    python -m Betfair.stream.backtest.certifica <bot> --complete --diario ...
"""
from __future__ import annotations

import os

import pytest

from Betfair.stream.backtest import registro_bot as REG

pytestmark = pytest.mark.cert

_RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

# CAMPIONE per bot: {nome bot: (event_id, ...)}. Poche partite CORTE in cui il
# bot opera davvero — una partita in cui non fa niente non certifica niente.
CAMPIONE = {
    # 35823616: 2.2k tick, Mike arma pre-KO e piazza 2 ordini (ingresso + lay
    # appoggiata). E' la partita piu' corta del corpus in cui apre.
    "mike": ("35823616",),
    # SAFE TENNIS (C.4, 16/09): partita di riferimento delle USCITE (COMPLETE 93,9 %).
    "safe_tennis": ("35790650",),
    # SAFE CALCIO (C.3, 16/09): campione di sola catena (come Omega), stessa registrazione corta.
    "safe_base": ("35823616",),
    "safe_esatto": ("35823616",),
    "safe_punta": ("35823616",),
    # OMEGA (C.2, 16/09) — la stessa registrazione corta, ma per Omega e' un
    # campione di SOLA CATENA: 25k tick in ~10 s, zero violazioni, e Omega non
    # opera (la registrazione e' PARTIAL e si ferma prima del gioco, quindi il
    # feed non viene mai letto). Serve a far scattare il rosso se qualcuno rompe
    # il collegamento scanner -> feed -> `run_once` -> ordini; NON certifica la
    # condotta. Quella sta nel comando, sulla partita di riferimento:
    #   python -m Betfair.stream.backtest.certifica omega 35760084 --scenari tutti
    # Un campione in cui Omega APRE davvero non esiste ancora nel corpus: sulla
    # 35760084 apre solo con la banda di quota allargata (scenario `apertura`) e
    # costa ~6 minuti, troppo per la suite. Da rivedere quando ci saranno
    # registrazioni piu' corte con gioco dentro.
    "omega": ("35823616",),
}


def _registrazione_c_e(bot, event_id: str) -> bool:
    cartella = bot.cartella()
    return os.path.isfile(os.path.join(cartella, event_id, f"{event_id}.raw.jsonl"))


@pytest.mark.parametrize(
    "nome", sorted(b.nome for b in REG.elenco() if b.certificabile))
def test_il_bot_certificabile_passa_il_campione(nome):
    """Zero violazioni sul campione, negli scenari base e riavvio."""
    from Betfair.stream.backtest import certifica

    scheda = REG.bot(nome)
    eventi = [e for e in CAMPIONE.get(nome, ()) if _registrazione_c_e(scheda, e)]
    if not eventi:
        pytest.skip(f"campione assente per {nome}: registrazioni non su questa macchina")
    esito = certifica.main([nome, *eventi, "--scenari", "base,riavvio"])
    assert esito == 0, (
        f"la certificazione di {nome} sul campione ha trovato violazioni. "
        f"Rilancia: python -m Betfair.stream.backtest.certifica {nome} {' '.join(eventi)}"
    )


def test_ogni_bot_certificabile_ha_un_campione_dichiarato():
    """Un bot certificabile senza campione girerebbe solo a mano: e' il modo in
    cui una certificazione smette di essere «di default»."""
    senza = sorted(b.nome for b in REG.elenco() if b.certificabile
                   and not CAMPIONE.get(b.nome))
    assert not senza, (
        f"bot certificabili senza campione in CAMPIONE: {senza}. "
        f"Aggiungi 1-2 registrazioni CORTE in cui il bot opera davvero."
    )
