"""08/10/2026 - Replay Tennis, <<Applica bot>>: la registrazione per MERCATO.

Caso vero dell'utente (07/10 sera): la partita 35797566, elencata nel Replay
Tennis, rispondeva <<registrazione assente ... in tennis_rec\\20260707>>. Sul
disco la radice ha DUE cartelle: ``20260707`` (raw del MATCH_ODDS; per alcune
partite solo ``<id>.score.jsonl``) e ``setbetting_20260707`` (raw del
SET_BETTING). Il banco cercava solo le cartelle-giorno numeriche e si fermava
alla prima con l'id, senza guardare il mercato del raw.

Qui, su una radice finta con la STESSA forma di quella vera (raw con
``marketDefinition.marketType`` veri, righe come le scrive il recorder):
  (a) una partita col Match Odds SOLO nella seconda cartella si trova;
  (b) una partita col solo Set Betting da' l'errore esatto (mercato e cartella);
  (c) una partita senza raw da' l'errore <<solo punteggi>>;
  (d) le partite col Match Odds tornano ESATTAMENTE la cartella di prima;
  (e) ``esegui`` solleva l'errore esatto prima di far girare il banco.

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import json
import os

import pytest

from Betfair.stream.backtest import applica_bot as AB
from Betfair.stream.backtest import registro_bot as REG


def _riga_md(market_id: str, market_type: str, pt: int) -> str:
    # forma di una riga del recorder (mcm del flusso Betfair, ``op``/``pt``/``mc``)
    return json.dumps({
        "op": "mcm", "clk": "AAA", "pt": pt,
        "mc": [{"id": market_id, "marketDefinition": {
            "bspMarket": False, "turnInPlayEnabled": True, "persistenceEnabled": True,
            "marketBaseRate": 5.0, "eventId": "x", "eventTypeId": "2",
            "numberOfWinners": 1, "bettingType": "ODDS", "marketType": market_type,
            "betDelay": 0, "status": "OPEN", "inPlay": False, "version": 1,
            "runners": [{"status": "ACTIVE", "sortPriority": 1, "id": 101},
                        {"status": "ACTIVE", "sortPriority": 2, "id": 202}]},
            "rc": [{"atb": [[1.5, 10.0]], "id": 101}]}]})


def _raw(radice, cartella: str, ev: str, market_type: str) -> str:
    d = radice / cartella / ev
    d.mkdir(parents=True, exist_ok=True)
    (d / ("%s.raw.jsonl" % ev)).write_text(
        _riga_md("1.%s" % ev, market_type, 1751900000000) + "\n"
        + json.dumps({"op": "mcm", "clk": "AAB", "pt": 1751900001000,
                      "mc": [{"id": "1.%s" % ev, "rc": [{"atl": [[1.6, 5.0]], "id": 101}]}]})
        + "\n", encoding="utf-8")
    (d / ("%s.score.jsonl" % ev)).write_text("", encoding="utf-8")
    return str(radice / cartella)


def _solo_punteggi(radice, cartella: str, ev: str) -> str:
    d = radice / cartella / ev
    d.mkdir(parents=True, exist_ok=True)
    (d / ("%s.score.jsonl" % ev)).write_text("{}\n", encoding="utf-8")
    return str(radice / cartella)


@pytest.fixture
def radice(tmp_path, monkeypatch):
    """La radice del recorder come quella vera: ``20260707`` + ``setbetting_20260707``."""
    # partita col Match Odds (come le 60 vere): raw MO in 20260707
    _raw(tmp_path, "20260707", "35790089", "MATCH_ODDS")
    # la stessa partita anche nel giorno prima (partita a cavallo della mezzanotte
    # UTC): la visita in profondita' la incontra PRIMA, la risoluzione di sempre
    # sceglie il giorno piu' recente - deve restare quella
    _raw(tmp_path, "20260706", "35790089", "MATCH_ODDS")
    # partita con entrambi (come la 35793960): MO in 20260707, SB nell'altra
    _raw(tmp_path, "20260707", "35793960", "MATCH_ODDS")
    _raw(tmp_path, "setbetting_20260707", "35793960", "SET_BETTING")
    # partita col solo Set Betting (come la 35797566): in 20260707 solo lo score
    _solo_punteggi(tmp_path, "20260707", "35797566")
    _raw(tmp_path, "setbetting_20260707", "35797566", "SET_BETTING")
    # partita col Match Odds SOLO nella seconda cartella (non numerica)
    _solo_punteggi(tmp_path, "20260707", "35799999")
    _raw(tmp_path, "registrazioni_extra", "35799999", "MATCH_ODDS")
    # partita senza nessun raw (solo punteggi)
    _solo_punteggi(tmp_path, "20260707", "35791111")
    # il registro tennis da' il giorno piu' recente della radice (TENNIS_RECORD_DIR)
    monkeypatch.setenv("TENNIS_RECORD_DIR", str(tmp_path))
    return tmp_path


@pytest.mark.parametrize("data_dir", [None, "radice"])
def test_a_match_odds_solo_nella_seconda_cartella_si_trova(radice, data_dir):
    reg = REG.bot("tennis_pro")
    dd = str(radice) if data_dir else None
    cartella, errore = AB.risolvi_cartella_tennis(reg, "35799999", dd)
    assert errore is None
    assert cartella == os.path.join(str(radice), "registrazioni_extra")
    assert AB.cartella_della_partita(reg, "35799999", dd) == cartella


@pytest.mark.parametrize("data_dir", [None, "radice"])
def test_b_solo_set_betting_errore_esatto(radice, data_dir):
    reg = REG.bot("tennis_pro")
    dd = str(radice) if data_dir else None
    _cartella, errore = AB.risolvi_cartella_tennis(reg, "35797566", dd)
    assert errore == ("per la partita 35797566 e' registrato solo il SET_BETTING "
                      "(cartella setbetting_20260707): i bot tennis lavorano sul Match "
                      "Odds, che non e' stato registrato")


@pytest.mark.parametrize("data_dir", [None, "radice"])
def test_c_senza_raw_errore_solo_punteggi(radice, data_dir):
    reg = REG.bot("tennis_pro")
    dd = str(radice) if data_dir else None
    _cartella, errore = AB.risolvi_cartella_tennis(reg, "35791111", dd)
    assert errore == ("registrazione senza flusso di mercato (solo punteggi) per la "
                      "partita 35791111 in 20260707: nessun 35791111.raw.jsonl, il bot "
                      "non ha prezzi su cui girare")
    assert "registrazione assente" not in errore


@pytest.mark.parametrize("bot", ["tennis_pro", "tennis_scalper", "tennis_flb",
                                 "tennis_swing", "safe_tennis"])
@pytest.mark.parametrize("ev", ["35790089", "35793960"])
@pytest.mark.parametrize("data_dir", [None, "radice", "giorno"])
def test_d_col_match_odds_la_stessa_cartella_di_prima(radice, bot, ev, data_dir):
    reg = REG.bot(bot)
    dd = {None: None, "radice": str(radice),
          "giorno": os.path.join(str(radice), "20260707")}[data_dir]
    prima = AB._cartella_come_prima(reg, ev, dd)
    cartella, errore = AB.risolvi_cartella_tennis(reg, ev, dd)
    assert errore is None
    assert cartella == prima == os.path.join(str(radice), "20260707")
    assert AB.cartella_della_partita(reg, ev, dd) == prima


def test_e_esegui_da_l_errore_esatto_prima_del_banco(radice, monkeypatch):
    chiamate = []
    reg = REG.bot("tennis_pro")
    monkeypatch.setattr(type(reg), "funzione_replay",
                        lambda self: (lambda *a, **k: chiamate.append(k)))
    with pytest.raises(ValueError) as e:
        AB.esegui({"bot": "tennis_pro", "scenario": "base", "event_id": "35797566"})
    assert str(e.value).startswith("per la partita 35797566 e' registrato solo il SET_BETTING")
    with pytest.raises(ValueError, match=r"solo punteggi"):
        AB.esegui({"bot": "tennis_pro", "scenario": "base", "event_id": "35791111"})
    assert chiamate == []


def test_il_catalogo_dichiara_i_mercati_del_bot():
    voce = AB.catalogo_del_bot("tennis_pro", con_parametri=False)
    assert voce["mercati"] == ["MATCH_ODDS"]
