"""Cantiere 14 (08/10): il registratore tennis scrive i nomi COMPLETI dei runner in ``_names.json``.

Caso vero 35790089: il flusso Betfair non porta i nomi e l'IPS li tronca ("Marcelo Tomas Barrios
V"). A ogni REC il tee scrive accanto al raw i nomi del catalogo (``listMarketCatalogue``) di tutti
i mercati registrati: chiave piatta ``{event: {sel: nome}}`` (compatibile con i lettori di sempre)
e chiave riservata ``_mercati`` -> ``{event: {market: {sel: nome}}}``.

I finti sono costruiti dai formati veri: ``MarketCatalogue`` di betfairlightweight (chiavi della
Betting API), il catalogo del Match Odds prodotto da ``tennis_runner._resolve_market`` (codice vero),
quello degli altri mercati da ``mercati_registrati.catalogo_mercati_evento`` (codice vero). Il file
scritto e' poi letto dai lettori VERI: ``nomi_da_cache`` (Replay Tennis), ``replay_bot.
catalogo_dichiarato`` (banco tennis) e importato con ``importa.converti_registrazione``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

import pytest
from betfairlightweight.resources.bettingresources import MarketCatalogue

from Betfair.stream.tennis_live import mercati_registrati as MR
from Betfair.stream.tennis_live import tennis_recorder as TREC
from Betfair.stream.tennis_live import tennis_runner as TR
from Betfair.stream.tennis_replay import convertitore as cv
from Betfair.stream.tennis_replay import importa as imp
from Betfair.stream.tennis_replay.tests import dati_tennis as dt

EV = "35999999"


def _mc(mid: str, tipo: str, nome: str, runner: List[tuple]) -> MarketCatalogue:
    return MarketCatalogue(**{
        "marketId": mid, "marketName": nome, "totalMatched": 1234.5,
        "event": {"id": EV, "name": "Uno Completo v Due Completo", "openDate": "2026-07-07T10:30:00.000Z",
                  "timezone": "GMT", "countryCode": "GB"},
        "description": {"bettingType": "ODDS", "bspMarket": False, "marketTime": "2026-07-07T10:30:00.000Z",
                        "suspendTime": "2026-07-07T10:30:00.000Z", "turnInPlayEnabled": True,
                        "marketType": tipo, "persistenceEnabled": True, "discountAllowed": True,
                        "marketBaseRate": 5.0, "wallet": "UK wallet"},
        "runners": [{"selectionId": sid, "runnerName": n, "handicap": 0.0, "sortPriority": j + 1}
                    for j, (sid, n) in enumerate(runner)],
    })


# i mercati della partita costruita (stessi market_id e selection_id del raw di prova)
CAT_MO = _mc(dt.MO, "MATCH_ODDS", "Match Odds", [(101, "Uno Completo"), (202, "Due Completo")])
CAT_EXTRA = [_mc(dt.SB, "SET_BETTING", "Set Betting", [(401, "Uno Completo 2 - 0"), (402, "Uno Completo 2 - 1"),
                                                      (403, "Due Completo 2 - 1"), (404, "Due Completo 2 - 0")]),
             _mc(dt.TG, "TOTAL_GAMES", "Total Games 22.5", [(301, "Under 22.5 Goals"), (302, "Over 22.5 Goals")])]


class _Betting:
    def __init__(self, righe: List[MarketCatalogue]) -> None:
        self.righe = righe

    def list_market_catalogue(self, filter: Dict[str, Any], market_projection: Any = None,
                              sort: Any = None, max_results: Any = None) -> List[MarketCatalogue]:
        return list(self.righe)


class _Trading:
    def __init__(self, righe: List[MarketCatalogue]) -> None:
        self.betting = _Betting(righe)


def meta_runner(con_extra: bool = True) -> Dict[str, Any]:
    """``market_meta[event]`` come lo costruisce il runner: Match Odds da ``_resolve_market``
    (codice vero), altri mercati da ``catalogo_mercati_evento`` (codice vero)."""
    meta = TR._resolve_market(_Trading([CAT_MO]), None, EV)
    if con_extra:
        meta[MR.CHIAVE] = MR.catalogo_mercati_evento(_Trading([CAT_MO] + CAT_EXTRA), EV, dt.MO)
    return meta


@pytest.fixture
def tee(tmp_path):
    t = TREC.TennisRawTee()
    t.dir = str(tmp_path / "20260707")
    return t


def _leggi(tee) -> Dict[str, Any]:
    with open(os.path.join(tee.dir, "_names.json"), encoding="utf-8") as fh:
        return json.load(fh)


ATTESO_PIATTO = {"101": "Uno Completo", "202": "Due Completo"}
ATTESO_MERCATI = {
    dt.MO: {"101": "Uno Completo", "202": "Due Completo"},
    dt.SB: {"401": "Uno Completo 2 - 0", "402": "Uno Completo 2 - 1", "403": "Due Completo 2 - 1", "404": "Due Completo 2 - 0"},
    dt.TG: {"301": "Under 22.5 Goals", "302": "Over 22.5 Goals"},
}


# ===========================================================================
# 1) a ogni REC i nomi completi di TUTTI i mercati registrati, nel formato concordato
# ===========================================================================
def test_rec_acceso_scrive_i_nomi_di_tutti_i_mercati(tee):
    tee.enable(EV, [dt.MO, dt.SB, dt.TG], meta=meta_runner())
    tutto = _leggi(tee)
    assert tutto[EV] == ATTESO_PIATTO                       # formato piatto di sempre (Match Odds)
    assert tutto[cv.CHIAVE_MERCATI_NOMI] == {EV: ATTESO_MERCATI}
    assert set(tutto) == {EV, "_mercati"}
    assert not os.path.exists(os.path.join(tee.dir, "_names.json.tmp"))   # scrittura atomica: nessun residuo


def test_il_file_e_letto_dai_lettori_veri(tee):
    tee.enable(EV, [dt.MO, dt.SB, dt.TG], meta=meta_runner())
    # Replay Tennis
    assert cv.nomi_da_cache(tee.dir, EV) == {"*": ATTESO_PIATTO, **ATTESO_MERCATI}
    # banco tennis (replay_bot): {nome: selection_id} del Match Odds, formato piatto invariato
    from Betfair.stream.tennis_live.tools.replay_bot import catalogo_dichiarato
    assert catalogo_dichiarato(tee.dir, EV) == {"Uno Completo": 101, "Due Completo": 202}
    # lab dei grid runner (laboratorio/, NON importabile da Betfair/: contratto strada unica): la sua
    # ``build_names_cache`` fa ``json.load`` e poi ``cache.get(ev)`` / ``ev not in cache`` per evento
    # (lab_grid_score.py:86-96): la stessa lettura piatta, che la chiave riservata non disturba
    with open(os.path.join(tee.dir, "_names.json"), encoding="utf-8") as fh:
        cache = json.load(fh)
    assert cache.get(EV) == ATTESO_PIATTO and EV in cache and "35794049" not in cache
    assert cv.CHIAVE_MERCATI_NOMI not in {EV, "35794049"}      # la chiave riservata non e' un event_id


def test_dal_raw_al_replay_nomi_completi_per_ogni_mercato(tee):
    """Percorso intero: REC -> raw + _names.json nella cartella del giorno -> import con i nomi."""
    tee.enable(EV, [dt.MO, dt.SB, dt.TG], meta=meta_runner())
    p = dt.partita_costruita()
    dt.scrivi(Path(tee.dir) / EV, f"{EV}.raw.jsonl", p["a"] + p["b"])
    voce = imp.trova_registrazioni([tee.dir])[EV]
    rt = imp.converti_registrazione(EV, voce, usa_db=False)
    per = {m["market_id"]: m for m in rt.mercati}
    assert [s["name"] for s in per[dt.MO]["selections"]] == ["Uno Completo", "Due Completo"]
    assert [s["name"] for s in per[dt.SB]["selections"]] == list(ATTESO_MERCATI[dt.SB].values())
    assert [s["name"] for s in per[dt.TG]["selections"]] == ["Under 22.5 Goals", "Over 22.5 Goals"]
    assert {s["name_source"] for m in rt.mercati for s in m["selections"]} == {"catalogo"}
    assert (rt.evento["player1_name"], rt.evento["player2_name"]) == ("Uno Completo", "Due Completo")
    assert rt.diagnostica["nomi_fonte"] == {"player1_name": "catalogo", "player2_name": "catalogo"}


# ===========================================================================
# 2) non sovrascrive; non tocca cio' che non capisce; mai un'eccezione
# ===========================================================================
def test_non_sovrascrive_le_partite_gia_presenti_e_conserva_le_altre(tee):
    os.makedirs(tee.dir)
    gia = {"35794049": {"1": "Jannik Sinner", "2": "Alexander Struff"}, EV: {"101": "Nome Del Grid Runner", "202": "Altro"}}
    with open(os.path.join(tee.dir, "_names.json"), "w", encoding="utf-8") as fh:
        json.dump(gia, fh)
    tee.enable(EV, [dt.MO, dt.SB], meta=meta_runner())
    tutto = _leggi(tee)
    assert tutto["35794049"] == gia["35794049"]                      # altra partita intatta
    assert tutto[EV] == gia[EV]                                       # voce piatta presente: non sovrascritta
    assert tutto[cv.CHIAVE_MERCATI_NOMI][EV][dt.MO] == ATTESO_MERCATI[dt.MO]   # i mercati in piu' si aggiungono


def test_di_un_mercato_gia_presente_si_aggiungono_solo_le_selezioni_mancanti(tee):
    os.makedirs(tee.dir)
    with open(os.path.join(tee.dir, "_names.json"), "w", encoding="utf-8") as fh:
        json.dump({cv.CHIAVE_MERCATI_NOMI: {EV: {dt.SB: {"401": "NOME GIA SCRITTO"}}}}, fh)
    tee.enable(EV, [dt.MO, dt.SB], meta=meta_runner())
    sb = _leggi(tee)[cv.CHIAVE_MERCATI_NOMI][EV][dt.SB]
    assert sb["401"] == "NOME GIA SCRITTO" and sb["404"] == "Due Completo 2 - 0" and len(sb) == 4


def test_file_illeggibile_non_si_tocca(tee, caplog):
    os.makedirs(tee.dir)
    path = os.path.join(tee.dir, "_names.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{non json")
    tee.enable(EV, [dt.MO], meta=meta_runner())
    with open(path, encoding="utf-8") as fh:
        assert fh.read() == "{non json"                                # intatto
    assert tee.is_enabled(EV)                                          # la registrazione non e' rotta


def test_senza_catalogo_non_scrive_nulla_e_poi_scrive_quando_arriva(tee):
    tee.enable(EV, [dt.MO])                                            # nessun meta
    tee.enable(EV, [dt.MO], meta={"market_id": dt.MO})                 # catalogo senza nomi
    assert not os.path.exists(os.path.join(tee.dir, "_names.json"))
    tee.enable(EV, [dt.MO], meta=meta_runner(con_extra=False))
    assert _leggi(tee)[EV] == ATTESO_PIATTO


def test_i_mercati_in_piu_arrivano_dopo_e_si_aggiungono(tee):
    """Il catalogo dei mercati in piu' si legge dopo il Match Odds (``record_flag_worker``)."""
    tee.enable(EV, [dt.MO], meta=meta_runner(con_extra=False))
    assert list(_leggi(tee)[cv.CHIAVE_MERCATI_NOMI][EV]) == [dt.MO]
    tee.enable(EV, [dt.MO, dt.SB, dt.TG], meta=meta_runner())
    assert _leggi(tee)[cv.CHIAVE_MERCATI_NOMI] == {EV: ATTESO_MERCATI}


def test_scrive_una_volta_sola_finche_il_catalogo_non_cambia(tee, monkeypatch):
    chiamate: List[str] = []
    vero = TREC.scrivi_nomi_catalogo
    monkeypatch.setattr(TREC, "scrivi_nomi_catalogo", lambda *a: (chiamate.append("x"), vero(*a))[1])
    for _ in range(5):                                                 # il worker richiama enable a ogni giro
        tee.enable(EV, [dt.MO, dt.SB, dt.TG], meta=meta_runner())
    assert len(chiamate) == 1
    tee.enable(EV, [dt.MO, dt.SB], meta=meta_runner(con_extra=False))  # catalogo diverso: riprova
    assert len(chiamate) == 2


def test_errore_di_scrittura_mai_verso_il_chiamante_e_riprova_dopo_60s(tee, monkeypatch):
    def rotto(*_a, **_k):
        raise OSError("disco pieno")

    monkeypatch.setattr(os, "replace", rotto)
    tee.enable(EV, [dt.MO], meta=meta_runner())                        # NON solleva
    assert tee.is_enabled(EV) and tee._nomi_firma == {} and EV in tee._nomi_riprova
    monkeypatch.undo()
    tee.enable(EV, [dt.MO], meta=meta_runner())                        # entro 60 s: non riprova
    assert not os.path.exists(os.path.join(tee.dir, "_names.json"))
    tee._nomi_riprova[EV] = 0.0                                        # passati i 60 s
    tee.enable(EV, [dt.MO], meta=meta_runner())
    assert _leggi(tee)[EV] == ATTESO_PIATTO


def test_il_tee_dei_messaggi_non_aspetta_il_disco(tee, monkeypatch):
    """La scrittura dei nomi sta FUORI dal lock del tee: mentre scrive, ``write_message`` passa."""
    visto: List[bool] = []

    def lenta(cartella, ev, meta):
        visto.append(tee._lock.acquire(blocking=False))                 # se il lock fosse preso: False
        if visto[-1]:
            tee._lock.release()
        return TREC.ESITO_INVARIATO

    monkeypatch.setattr(TREC, "scrivi_nomi_catalogo", lenta)
    tee.enable(EV, [dt.MO], meta=meta_runner())
    assert visto == [True]


# ===========================================================================
# 3) il percorso reale del runner: sync_record_flags -> enable -> file
# ===========================================================================
def test_sync_record_flags_scrive_i_nomi_solo_per_gli_eventi_con_rec(tee):
    metas = {EV: meta_runner(), "35888888": dict(meta_runner(), market_id="1.5", selection_names={"7": "Altro"})}
    follows = [{"event_id": EV, "record": True}, {"event_id": "35888888", "record": False}]
    assert TREC.sync_record_flags(follows, metas, tee=tee) == {EV}
    tutto = _leggi(tee)
    assert "35888888" not in tutto and EV in tutto
    assert "35888888" not in tutto[cv.CHIAVE_MERCATI_NOMI]
