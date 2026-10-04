"""04/10 - UNA SOLA VERITA' DEL P&L DI GIORNATA (segnalazione dell'utente).

«La scheda Calcio dice LIVE -10,75 EUR CONTO BETFAIR, Posizioni chiuse -5,68.
Non abbiamo mai perso 10 euro: uniforma i dati una volta per tutte.»

Il caso di prova e' la giornata VERA del 04/10 (letta dal DB in sola lettura:
``betfair_live_account.pnl_reale_oggi``, ``mike_trades``, ``betfair_live_
orders``): 7 ordini regolati, lordo -5,13, commissione 0,02, netto -5,15.
L'ordine 445577040174 (lay Under 3.5 5,07 @1,51 su Vasalunds - FC Arlanda,
+5,07) l'ha messo l'UTENTE dal sito (nessun ref) dopo che il green di Mike
(riga 5157, bet 445572063578) era stato ritirato all'arresto: Mike lo conta
nella sua posizione (riga 5160, ``role='utente'``, ``closes_trade_id`` 5156),
il conto lo metteva in "manuale sito". Da qui -10,75 (Mike senza la chiusura)
contro -5,68 (la posizione di Mike con la chiusura).

Sotto test: ``per_fonte`` (chi ha piazzato) resta IDENTICA; le chiavi nuove
``per_posizione``/``chiusure_a_mano``/``per_sport`` tornano col conto al
centesimo. Finti con le chiavi del vero (``ClearedOrder`` di
betfairlightweight, righe con le colonne vere). Nessuna rete, nessun DB vero.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

import Betfair.stream.reconcile_worker as rw
from Betfair.stream.tests.test_pnl_betfair_reale_2026_09_24 import _bet, _mercato
from Betfair.stream.tests.test_reconcile_worker import (  # noqa: F401 - fixture riusata
    _FakeBetting, _riga, _session, env,
)

T = datetime(2026, 10, 4, 13, 8, tzinfo=timezone.utc)

# mercati veri del 04/10
FARENSE_U35 = "1.263086158"
FARENSE_U45 = "1.263086155"
MIYAZAKI_U35 = "1.263199718"
VASALUNDS_U35 = "1.263105235"
MANUALE_MKT = "1.263096939"

#: i 7 ordini regolati di oggi, coi profit (LORDI) di Betfair
ORDINI_VERI = [
    ("445568321596", -5.00, FARENSE_U35),    # Mike under_entry (5152)
    ("445572454155", -0.82, FARENSE_U45),    # Mike over_cover (5159)
    ("445568325409", 2.20, MIYAZAKI_U35),    # Mike under_entry (5154)
    ("445568328282", -2.13, MIYAZAKI_U35),   # Mike under_green (5155)
    ("445572059076", -5.00, VASALUNDS_U35),  # Mike under_entry (5156)
    ("445577040174", 5.07, VASALUNDS_U35),   # UTENTE dal sito, chiude la 5156 (riga 5160)
    ("445569572640", 0.55, MANUALE_MKT),     # UTENTE dal sito, fuori dalle posizioni dei bot
]
#: livello MERCATO (groupBy=MARKET): la commissione esiste solo qui
MERCATI_VERI = [
    _mercato(FARENSE_U35, -5.00, 0.0, 1),
    _mercato(FARENSE_U45, -0.82, 0.0, 1),
    _mercato(MIYAZAKI_U35, 0.07, 0.0, 2),
    _mercato(VASALUNDS_U35, 0.07, 0.0, 2),
    _mercato(MANUALE_MKT, 0.55, 0.02, 1),
]


def _righe_vere(env, *, con_riga_utente: bool = True) -> None:
    """Le righe LIVE di oggi con i bet_id veri (colonne lette dal runner:
    id, bet_id, role, mode; ``betfair_live_orders``: id, bet_id, source)."""
    for rid, bet, role in ((5152, "445568321596", "under_entry"),
                           (5153, "445568324077", "under_green"),
                           (5154, "445568325409", "under_entry"),
                           (5155, "445568328282", "under_green"),
                           (5156, "445572059076", "under_entry"),
                           (5157, "445572063578", "under_green"),
                           (5158, "445572154142", "ko_green"),
                           (5159, "445572454155", "over_cover")):
        _riga(env, "mike_trades", id=rid, bet_id=bet, role=role)
    if con_riga_utente:
        _riga(env, "mike_trades", id=5160, bet_id="445577040174", role="utente")
    # la COPIA dell'ordine del sito trovata sul conto (non nostra)
    _riga(env, "betfair_live_orders", id=49270, bet_id="445569572640", source="account")


def _giro(env, ordini=None, mercati=None):
    ordini = ordini if ordini is not None else [
        _bet(b, p, market_id=m, settled=T) for b, p, m in ORDINI_VERI]
    betting = _FakeBetting(cleared_pages=[ordini], market_groups=mercati or MERCATI_VERI)
    rw._sync_manual_pnl(_session(betting=betting))
    return env["pnl_reale_writes"][-1]


def test_giornata_vera_04_10_tutte_le_cifre_tornano_col_conto(env):
    """IL CASO DELL'UTENTE, numero per numero.
    FALSIFICAZIONE: togliere l'adozione (``posizione = fonte``) -> per_posizione
    di Mike torna -10,75 e la tessera mostrerebbe di nuovo -10,75 -> rosso."""
    _righe_vere(env)
    r = _giro(env)
    # il conto intero: invariato
    assert (r["ordini"], r["lordo"], r["commissione"], r["netto"]) == (7, -5.13, 0.02, -5.15)
    # CHI ha piazzato (per_fonte): IDENTICA al payload vero del 04/10
    assert r["per_fonte"]["mike"] == {"netto": -10.75, "lordo": -10.75, "ordini": 5, "senza_commissione": 0}
    assert r["per_fonte"]["manuale_sito"] == {"netto": 5.6, "lordo": 5.62, "ordini": 2, "senza_commissione": 0}
    # di quale POSIZIONE e': la chiusura dell'utente sta con Mike
    assert r["per_posizione"]["mike"] == {"netto": -5.68, "lordo": -5.68, "ordini": 6, "senza_commissione": 0}
    assert r["per_posizione"]["manuale_sito"] == {"netto": 0.53, "lordo": 0.55, "ordini": 1, "senza_commissione": 0}
    assert r["chiusure_a_mano"] == {"mike": {"netto": 5.07, "lordo": 5.07, "ordini": 1,
                                             "bet_ids": ["445577040174"]}}
    # per SPORT: il calcio e' tutto il conto di oggi, bot + a mano
    c = r["per_sport"]["calcio"]
    assert (c["ordini"], c["lordo"], c["commissione"], c["netto"]) == (7, -5.13, 0.02, -5.15)
    assert c["bot"] == {"netto": -5.68, "lordo": -5.68, "ordini": 6}
    assert c["a_mano"] == {"netto": 0.53, "lordo": 0.55, "ordini": 1}
    assert c["chiusure_a_mano"] == {"netto": 5.07, "lordo": 5.07, "ordini": 1}
    assert r["per_sport"]["tennis"]["ordini"] == 0 and r["per_sport"]["tennis"]["netto"] == 0.0
    # nessun centesimo creato o perso spostando di voce
    somma = lambda d: round(sum(v["netto"] for v in d.values()), 2)  # noqa: E731
    assert somma(r["per_fonte"]) == somma(r["per_posizione"]) == r["netto"]
    assert round(c["bot"]["netto"] + c["a_mano"]["netto"], 2) == c["netto"]


def test_chiusura_a_mano_sul_mercato_di_mike_anche_prima_della_riga_utente(env):
    """Il giro dei regolati gira PRIMA che Mike scriva la sua riga 'utente' (il
    04/10: lettura 13:08, riga 5160 alle 13:19; e il proprietario di un bet_id
    si risolve UNA volta per processo). La regola del MERCATO (ordine a mano
    sullo stesso mercato di un ordine di Mike regolato) basta da sola.
    FALSIFICAZIONE: togliere ``or market_id in mercati_adottanti`` -> rosso."""
    _righe_vere(env, con_riga_utente=False)
    r = _giro(env)
    assert r["per_posizione"]["mike"]["netto"] == -5.68
    assert r["chiusure_a_mano"]["mike"]["bet_ids"] == ["445577040174"]
    assert r["per_fonte"]["manuale_sito"]["ordini"] == 2  # chi l'ha piazzato: invariato


def test_riga_utente_di_mike_adotta_anche_su_un_mercato_senza_ordini_regolati_di_mike(env):
    """L'utente chiude la posizione di Mike su un mercato dove Mike non ha
    ordini regolati (es. il green di Mike ritirato): la riga 'utente' di Mike
    (stessa lettura di ``_proprietari``, colonna ``role``) basta.
    FALSIFICAZIONE: non ricordare ``_ADOTTATO_BET`` in ``_proprietari`` -> rosso."""
    _riga(env, "mike_trades", id=1, bet_id="900", role="under_entry")
    _riga(env, "mike_trades", id=2, bet_id="901", role="utente")
    r = _giro(env, ordini=[_bet("900", -5.0, market_id="1.1", settled=T),
                           _bet("901", 5.07, market_id="1.2", settled=T)],
              mercati=[_mercato("1.1", -5.0, 0.0, 1), _mercato("1.2", 5.07, 0.0, 1)])
    assert r["per_posizione"]["mike"] == {"netto": 0.07, "lordo": 0.07, "ordini": 2, "senza_commissione": 0}
    assert r["per_posizione"]["manuale_sito"]["ordini"] == 0
    assert r["per_fonte"]["manuale_sito"]["ordini"] == 1


def test_ordine_a_mano_sul_mercato_di_omega_resta_a_mano(env):
    """Omega non conta gli ordini dell'utente nella sua posizione (non scrive
    righe 'utente'): lo stesso mercato NON basta a farlo suo, altrimenti la
    composizione e le Posizioni chiuse di Omega direbbero cifre diverse.
    FALSIFICAZIONE: adottare per qualunque bot sullo stesso mercato -> rosso."""
    _riga(env, "omega_trades", id=3, bet_id="910")
    r = _giro(env, ordini=[_bet("910", 2.0, market_id="1.5", settled=T),
                           _bet("911", -1.0, market_id="1.5", settled=T)],
              mercati=[_mercato("1.5", 1.0, 0.1, 2)])
    assert r["per_posizione"]["omega"]["ordini"] == 1
    assert r["per_posizione"]["manuale_sito"] == {"netto": -1.0, "lordo": -1.0, "ordini": 1, "senza_commissione": 0}
    assert r["chiusure_a_mano"] == {}
    assert r["per_sport"]["calcio"]["a_mano"]["netto"] == -1.0
    assert r["per_sport"]["calcio"]["bot"]["netto"] == 1.9


def test_solo_gli_ordini_a_mano_vengono_adottati_mai_quelli_di_un_altro_bot(env):
    """Un ordine di Omega e uno di Safe calcio sullo STESSO mercato di un ordine
    di Mike regolato oggi restano nella LORO voce: l'adozione e' solo per gli
    ordini a mano (sito/app).
    FALSIFICAZIONE (coordinatore): ``if fonte in FONTI_A_MANO and (`` ->
    ``if fonte != _FONTE_CHE_ADOTTA and (`` -> rosso."""
    _riga(env, "mike_trades", id=21, bet_id="940", role="under_entry")
    _riga(env, "omega_trades", id=22, bet_id="941")
    _riga(env, "safe_strategy_trades", id=23, bet_id="942")
    r = _giro(env, ordini=[_bet("940", -5.0, market_id="1.40", settled=T),
                           _bet("941", 3.0, market_id="1.40", settled=T),
                           _bet("942", 1.0, market_id="1.40", settled=T)],
              mercati=[_mercato("1.40", -1.0, 0.0, 3)])
    pp = r["per_posizione"]
    assert pp["mike"] == {"netto": -5.0, "lordo": -5.0, "ordini": 1, "senza_commissione": 0}
    assert pp["omega"] == {"netto": 3.0, "lordo": 3.0, "ordini": 1, "senza_commissione": 0}
    assert pp["safe_calcio"] == {"netto": 1.0, "lordo": 1.0, "ordini": 1, "senza_commissione": 0}
    assert r["chiusure_a_mano"] == {}
    c = r["per_sport"]["calcio"]
    assert c["bot"] == {"netto": -1.0, "lordo": -1.0, "ordini": 3}
    assert c["chiusure_a_mano"] == {"netto": 0.0, "lordo": 0.0, "ordini": 0}
    assert c["a_mano"]["ordini"] == 0


@pytest.mark.parametrize("tabella,voce", [
    ("mike_trades", "mike"), ("omega_trades", "omega"), ("safe_strategy_trades", "safe_calcio"),
])
def test_ordine_di_un_bot_nella_sua_tabella_mai_in_manuale_sito(env, tabella, voce):
    """Contratto: un bet_id presente (LIVE) nella tabella di un bot e' di quel
    bot, per chi l'ha piazzato e per la posizione; mai "manuale sito".
    FALSIFICAZIONE: saltare la lettura della tabella -> rosso."""
    campi = {"role": "under_entry"} if tabella == "mike_trades" else {}
    _riga(env, tabella, id=11, bet_id="920", **campi)
    r = _giro(env, ordini=[_bet("920", 3.0, market_id="1.9", settled=T)],
              mercati=[_mercato("1.9", 3.0, 0.15, 1)])
    for chiave in ("per_fonte", "per_posizione"):
        assert r[chiave][voce]["ordini"] == 1, chiave
        assert r[chiave]["manuale_sito"]["ordini"] == 0, chiave
    assert r["per_sport"]["calcio"]["bot"] == {"netto": 2.85, "lordo": 3.0, "ordini": 1}


def test_ordine_a_mano_sul_tennis_conta_nel_tennis_non_nel_calcio(env):
    """Lo sport viene dall'``eventTypeId`` dell'ordine (2 = tennis), anche per
    gli ordini a mano: calcio e tennis non si mischiano.
    FALSIFICAZIONE: sport fisso 'calcio' per gli ordini a mano -> rosso."""
    r = _giro(env, ordini=[_bet("930", 1.5, market_id="1.30", event_type_id="2", settled=T),
                           _bet("931", -0.5, market_id="1.31", event_type_id="1", settled=T)],
              mercati=[_mercato("1.30", 1.5, 0.08, 1), _mercato("1.31", -0.5, 0.0, 1)])
    assert r["per_sport"]["tennis"]["a_mano"] == {"netto": 1.42, "lordo": 1.5, "ordini": 1}
    assert r["per_sport"]["tennis"]["netto"] == 1.42
    assert r["per_sport"]["calcio"]["a_mano"] == {"netto": -0.5, "lordo": -0.5, "ordini": 1}
    assert r["per_sport"]["altro"]["ordini"] == 0


def test_nessuna_lettura_in_piu_per_l_attribuzione_di_posizione(env):
    """Le chiavi nuove non costano chiamate: stesse letture DB e REST del
    giro di prima (una per tabella, una per ordine, una per mercato)."""
    _righe_vere(env)
    betting = _FakeBetting(cleared_pages=[[_bet(b, p, market_id=m, settled=T) for b, p, m in ORDINI_VERI]],
                           market_groups=MERCATI_VERI)
    rw._sync_manual_pnl(_session(betting=betting))
    letture = {n: t.reads for n, t in env["sb"].bot_tables.items()}
    # 5 tabelle lette una volta ciascuna (nessun ref <bot>-t<id> orfano)
    assert sum(letture.values()) + env["sb"].orders.reads == 5
    assert len(betting.cleared_calls) == 2
