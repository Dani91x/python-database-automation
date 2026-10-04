"""02/10 (PARITA_SAFE_ENV) - il replay di certificazione NON dipende dal ``.env``
di chi lo lancia.

Reperto: ``certifica safe_base 35760084 --scenari rapidi --trasporto entrambi``
dava PARITA' NON RAGGIUNTA dal checkout principale (coda: 0 ordini, 1 riga
``error`` ``canale_giu:apertura_non_inviata``; canale: 2 ordini) e RAGGIUNTA con
``SAFE_ORDINI_VIA_CANALE`` spento nell'ambiente. Causa: ``trasporto.contesto``
accendeva l'interruttore per il ``canale`` ma per la ``coda`` lo lasciava
all'ambiente, e il ``.env`` vero (``SAFE_ORDINI_VIA_CANALE=1``, caricato anche a
meta' replay dal ``load_dotenv()`` di ``Betfair/stream/config_stream.py`` al
primo import) faceva usare al bot «in coda» la porta VERA del canale, giu' nel
replay.

Qui, con le funzioni di produzione (``porta_ordini.acceso``,
``porta_ordini.porta_per_sport``) e i contesti veri del banco:
(1) in coda l'interruttore e' spento per OGNI valore dell'ambiente, in canale
acceso; (2) un ``load_dotenv`` con l'interruttore acceso, a meta' replay, non lo
riaccende; (3) i 20 interruttori sono dichiarati e l'ambiente torna com'era;
(4) l'intestazione del referto e' la stessa per ogni ambiente; (5) [cert] sulla
registrazione vera la coda da' la stessa traccia con l'ambiente «principale» e
con l'ambiente vuoto.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from Betfair.safe_strategy import porta_ordini as PO
from Betfair.stream.backtest import certifica as CE
from Betfair.stream.backtest import trasporto as TRA

#: i valori dell'interruttore che un ``.env`` puo' avere (accesi e spenti)
VALORI = ["1", "true", "si", "yes", "0", "", None]


def _imposta(monkeypatch, nome, valore):
    if valore is None:
        monkeypatch.delenv(nome, raising=False)
    else:
        monkeypatch.setenv(nome, valore)


@pytest.mark.parametrize("valore", VALORI)
def test_coda_spegne_l_interruttore_per_ogni_valore_dell_ambiente(monkeypatch, valore):
    """Rottura minima: ``contesto`` che non scrive l'interruttore per la coda ->
    con ``1``/``true``/``si``/``yes`` nell'ambiente il bot usa la porta del
    canale (il reperto)."""
    _imposta(monkeypatch, PO.ENV_CANALE, valore)
    # il trasporto da solo (senza i freni del banco: ogni strato si difende)
    with TRA.contesto("safe_base", "coda"):
        assert os.environ[PO.ENV_CANALE] == "0"
        assert PO.acceso(PO.ENV_CANALE) is False
        # la funzione che il servizio usa per scegliere il trasporto
        assert PO.porta_per_sport("calcio", avvia=False) is None
    assert os.environ.get(PO.ENV_CANALE) == valore
    # e dentro i freni del banco, come in ``certifica._lavora``
    with CE._freni_da_banco():
        with TRA.contesto("safe_base", "coda"):
            assert PO.acceso(PO.ENV_CANALE) is False


@pytest.mark.parametrize("valore", VALORI)
def test_canale_accende_l_interruttore_per_ogni_valore_dell_ambiente(monkeypatch, valore):
    _imposta(monkeypatch, PO.ENV_CANALE, valore)
    with CE._freni_da_banco():
        with TRA.contesto("safe_base", "canale"):
            assert PO.acceso(PO.ENV_CANALE) is True


@pytest.mark.parametrize("bot, nome", [("omega", "OMEGA_ORDINI_VIA_CANALE"),
                                       ("safe_tennis", "SAFE_TENNIS_ORDINI_VIA_CANALE"),
                                       ("safe_esatto", "SAFE_ORDINI_VIA_CANALE"),
                                       ("safe_punta", "SAFE_ORDINI_VIA_CANALE")])
def test_ogni_bot_con_interruttore_e_spento_in_coda(monkeypatch, bot, nome):
    monkeypatch.setenv(nome, "1")
    with TRA.contesto(bot, "coda"):
        assert os.environ[nome] == "0"
    with CE._freni_da_banco():
        assert os.environ[nome] == "0"
        with TRA.contesto(bot, "canale"):
            assert os.environ[nome] == "1"
        assert os.environ[nome] == "0"
    assert os.environ[nome] == "1"   # l'ambiente dell'operatore torna com'era


def test_load_dotenv_a_meta_replay_non_riaccende(monkeypatch, tmp_path):
    """Il meccanismo esatto del reperto: il primo import di ``config_stream``
    chiama ``load_dotenv()``, che riempie le variabili ASSENTI dal ``.env`` vero.
    Con l'ambiente dichiarato nessun interruttore e' assente: il ``.env`` non
    tocca niente. Rottura minima: dichiarare ``AMBIENTE_DEL_BANCO`` senza gli
    interruttori -> qui il ``.env`` finto li riaccende."""
    from dotenv import load_dotenv

    finto = tmp_path / ".env"
    finto.write_text("".join(f"{n}=1\n" for n in CE.INTERRUTTORI_CANALE_DEL_BANCO)
                     + "LIVE_ORDER_MODE=OFF\nMIKE_LIVE_ENABLED=0\n", encoding="utf-8")
    for n in CE.INTERRUTTORI_CANALE_DEL_BANCO:
        monkeypatch.delenv(n, raising=False)
    with CE._freni_da_banco():
        with TRA.contesto("safe_base", "coda"):
            load_dotenv(str(finto))          # override=False, come config_stream
            for n in CE.INTERRUTTORI_CANALE_DEL_BANCO:
                assert os.environ[n] == "0", n
            assert os.environ["LIVE_ORDER_MODE"] == "LIVE"
            assert os.environ["MIKE_LIVE_ENABLED"] == "1"
            assert PO.porta_per_sport("calcio", avvia=False) is None


def test_ambiente_dichiarato_e_ripristinato(monkeypatch):
    """Ogni variabile dichiarata vale il valore del banco DENTRO e torna com'era
    FUORI (presenti e assenti), anche su eccezione."""
    prima = {}
    for i, k in enumerate(sorted(CE.AMBIENTE_DEL_BANCO)):
        v = None if i % 2 else "valore-operatore-%d" % i
        _imposta(monkeypatch, k, v)
        prima[k] = v
    with pytest.raises(RuntimeError):
        with CE._freni_da_banco():
            for k, v in CE.AMBIENTE_DEL_BANCO.items():
                assert os.environ[k] == v, k
            raise RuntimeError("replay esploso")
    for k, v in prima.items():
        assert os.environ.get(k) == v, k


def test_elenco_interruttori_allineato_al_conftest_e_ai_bot():
    from Betfair import conftest as BC

    assert set(CE.INTERRUTTORI_CANALE_DEL_BANCO) == set(BC.INTERRUTTORI_CANALE)
    for _bot, (_attore, nome) in TRA.ATTORI.items():
        if nome:
            assert nome in CE.INTERRUTTORI_CANALE_DEL_BANCO, nome
            assert CE.AMBIENTE_DEL_BANCO[nome] == "0"
    assert TRA.VALORE_INTERRUTTORE == {"coda": "0", "canale": "1"}


def test_intestazione_identica_per_ogni_ambiente(monkeypatch):
    righe = set()
    for v in VALORI:
        _imposta(monkeypatch, PO.ENV_CANALE, v)
        righe.add(CE.descrivi_ambiente())
    assert len(righe) == 1
    riga = righe.pop()
    for k, v in CE.AMBIENTE_DEL_BANCO.items():
        assert f"{k}={v}" in riga
    assert "coda=0 canale=1" in riga


# ---------------------------------------------------------------------------
# [cert] sulla registrazione vera: stesso referto con due ambienti
# ---------------------------------------------------------------------------
def _cartella_registrazioni() -> str:
    candidati = [os.getenv("LIVE_STREAM_DATA_DIR") or ""]
    radice = Path(__file__).resolve().parents[3]
    candidati += [str(radice / "_live_raw"), str(radice.parents[2] / "_live_raw")]
    for c in candidati:
        if c and os.path.exists(os.path.join(c, "35760084", "35760084.raw.jsonl")):
            return c
    return ""


def _riassunto(r):
    tr = dict(getattr(r, "traccia_trasporto", None) or {})
    tr.pop("durata_s", None)
    return {"pulita": r.pulita, "decisioni": r.decisioni, "azioni": r.azioni,
            "violazioni": sorted(v.codice for v in (r.violazioni or [])),
            "traccia": tr}


@pytest.mark.cert
@pytest.mark.skipif(not _cartella_registrazioni(),
                    reason="registrazione 35760084 assente su questa macchina")
def test_coda_stesso_referto_con_ambiente_principale_e_ambiente_vuoto(monkeypatch):
    """La coda dello scenario d'ordine di Safe (``ordini-manuali``) con i 20
    interruttori ACCESI nell'ambiente (come il ``.env`` del checkout principale)
    e con l'ambiente VUOTO: stesso referto, 2 ordini sulla REST del banco.
    Prima della correzione: 0 ordini e 1 riga ``error`` con l'ambiente acceso.
    Circa 90 s (due replay della partita intera)."""
    dati = _cartella_registrazioni()
    compito = ("safe_base", "35760084", dati, "ordini-manuali", 0, 0, "coda")
    for n in CE.INTERRUTTORI_CANALE_DEL_BANCO:
        monkeypatch.setenv(n, "1")
    acceso, _ = CE._lavora(compito)
    for n in CE.INTERRUTTORI_CANALE_DEL_BANCO:
        monkeypatch.delenv(n, raising=False)
    vuoto, _ = CE._lavora(compito)
    a, b = _riassunto(acceso), _riassunto(vuoto)
    assert a == b
    assert len(a["traccia"]["ordini"]) == 2, a["traccia"]
    # 04/10/2026 (regola delle punte): la chiusura in punta 2,39 parte 2,00 (prima: 2,39 al
    # centesimo, poi rifiutata dal banco come da Betfair). Il resto (0,39 @9,2) non e'
    # piazzabile: l'apertura resta 'open' col residuo dichiarato, mai 'hedged'
    assert [r["status"] for r in a["traccia"]["righe"]] == ["open", "open"]
