"""BANCO 08/10 (cantiere 7) - lo SCANNER del banco: reperti RB-1 e RB-2 del 07/10
(`AUDIT_2026-10-07/OMEGA_APERTURA_35760084.md` sez. 10).

RB-1 - lo stato TERMINALE non si perde. La conflazione del banco
(`ScannerReplay.applica_book`, 1 book al secondo per mercato come lo stream
dello scanner con `conflateMs=1000`) teneva il PRIMO book del secondo e scartava
gli altri: un CLOSED nello stesso secondo di un SUSPENDED non arrivava mai, e
dopo la chiusura Betfair non manda piu' niente. Betfair consegna lo stato FUSO
piu' recente: la chiusura arriva sempre.

RB-2 - il banco consegnava allo scanner OGNI mercato a catalogo dal primo
all'ultimo book; lo scanner di produzione si sottoscrive solo ai mercati che
`Scanner.relevant_market_ids` vuole in quell'istante (l'Half Time Score dal 15'
al 45', il Correct Score dei candidati, i mercati con esposizione di un bot...).
A finestre accese il banco usa quella funzione, VERA.

Oggetti VERI: `MarketBook` di betfairlightweight costruiti dalla CACHE di
betfairlightweight (`MarketBookCache.update_cache` + `create_resource`, la
strada di flumine) sui messaggi del RAW VERO del banco
(`registrazioni_banco/35760084`), punteggi dal sidecar vero letti da
`carica_punteggi` e applicati da `Scanner.apply_score_state`. ASCII-only.
"""
from __future__ import annotations

import gzip
import json
import os
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import pytest

from Betfair.stream.backtest import banco_comune as B

RADICE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
CARTELLA = os.path.join(RADICE, "registrazioni_banco", "35760084")
EVENTO = "35760084"
MO = "1.259475525"
HT = "1.259475535"
CS = "1.259475532"


def _ms(hhmmss: str) -> int:
    """Epoch ms del 30/06/2026 (giorno della registrazione) alle hh:mm:ss[.fff] UTC."""
    ora, _, frazione = hhmmss.partition(".")
    h, m, s = (int(x) for x in ora.split(":"))
    base = datetime(2026, 6, 30, h, m, s, tzinfo=timezone.utc).timestamp()
    return int(base * 1000) + int((frazione or "0").ljust(3, "0")[:3])


_LIBRI: Dict[str, List[Tuple[int, Any]]] = {}


def _libri() -> Dict[str, List[Tuple[int, Any]]]:
    """market_id -> [(publish_time ms, MarketBook)] per MO, HT e CS: un book per
    ogni messaggio che tocca il mercato, dalla cache VERA di betfairlightweight."""
    if _LIBRI:
        return _LIBRI
    from betfairlightweight.streaming.cache import MarketBookCache

    cache: Dict[str, Any] = {}
    out: Dict[str, List[Tuple[int, Any]]] = {MO: [], HT: [], CS: []}
    with gzip.open(os.path.join(CARTELLA, EVENTO + ".raw.jsonl.gz"), "rt") as fh:
        for riga in fh:
            dati = json.loads(riga)
            pt = int(dati["pt"])
            for mc in dati.get("mc") or []:
                mid = mc.get("id")
                if mid not in out:
                    continue
                c = cache.get(mid)
                if c is None:
                    c = cache[mid] = MarketBookCache(mid, pt, False, False, False)
                c.update_cache(mc, pt, active=True)
                out[mid].append((pt, c.create_resource(1, snap=True)))
    _LIBRI.update(out)
    return _LIBRI


def _libro(mid: str, hhmmss: str) -> Any:
    """L'ULTIMO book del mercato con publish time <= hh:mm:ss[.fff]."""
    limite = _ms(hhmmss)
    scelto = None
    for pt, libro in _libri()[mid]:
        if pt > limite:
            break
        scelto = libro
    assert scelto is not None, (mid, hhmmss)
    return scelto


def _con_prezzi(libro: Any) -> bool:
    return any(getattr(r.ex, "available_to_back", None) or getattr(r.ex, "available_to_lay", None)
               for r in libro.runners)


@pytest.fixture(scope="module")
def punteggi(tmp_path_factory) -> List[Tuple[int, Dict[str, Any]]]:
    """Il sidecar VERO, decompresso dove `carica_punteggi` lo cerca."""
    dove = tmp_path_factory.mktemp("rb")
    (dove / EVENTO).mkdir()
    with gzip.open(os.path.join(CARTELLA, EVENTO + ".scores.jsonl.gz"), "rb") as a, \
            open(dove / EVENTO / (EVENTO + ".scores.jsonl"), "wb") as b:
        shutil.copyfileobj(a, b)
    return B.carica_punteggi(str(dove), EVENTO, "calcio")


def _banco(punteggi, fino_a: str, *, finestre: bool = False) -> B.ScannerReplay:
    """Lo scanner del banco a catalogo con MO, CS e HT (dai `marketDefinition`
    veri), col book VERO del MATCH_ODDS a ``fino_a`` e i punteggi fino a li',
    nell'ordine del giro del replay (prima i book, poi i punteggi)."""
    banco = B.ScannerReplay(sport="calcio")
    banco.finestre_di_produzione = finestre
    for mid in (MO, CS, HT):
        assert banco.registra_mercato(_libri()[mid][0][1])
    casa, fuori = B.nomi_dal_punteggio(punteggi)
    banco.dichiara_nomi(casa, fuori)
    assert _a(banco, fino_a, MO) is True
    for ts, rec in punteggi:
        if ts <= _ms(fino_a):
            banco.applica_punteggio(EVENTO, rec)
    return banco


def _dopo_un_giro(hhmmss: str) -> str:
    """L'istante ``hhmmss`` + 0,6 s: lo scanner ha rifatto la sottoscrizione
    (``GIRO_SCANNER_S``) con lo stato appena aggiornato."""
    ms = _ms(hhmmss) + 600
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%H:%M:%S.%f")[:-3]


def _a(banco: B.ScannerReplay, hhmmss: str, mid: str, libro_hhmmss: str = "") -> bool:
    banco.imposta_ora(_ms(hhmmss) / 1000.0)
    return banco.applica_book(_libro(mid, libro_hhmmss or hhmmss))


# ---------------------------------------------------------------------------
# i dati del reperto, dal raw (la sonda del 07/10 rifatta qui)
# ---------------------------------------------------------------------------
def test_raw_ht_sospeso_alle_16_47_53_e_chiuso_alle_16_47_58():
    stati = [(pt, lb.status) for pt, lb in _libri()[HT] if pt >= _ms("16:47:00")]
    assert stati == [(_ms("16:47:53.765"), "SUSPENDED"), (_ms("16:47:58.751"), "CLOSED")]
    assert _libro(HT, "16:47:58.751").status == "CLOSED"
    assert _con_prezzi(_libro(HT, "16:30:00"))


# ---------------------------------------------------------------------------
# RB-1 - lo stato terminale
# ---------------------------------------------------------------------------
def test_rb1_closed_nello_stesso_secondo_di_un_sospeso_arriva_allo_scanner(punteggi):
    """Il SUSPENDED vero e il CLOSED vero dell'HT, consegnati nello STESSO secondo
    di tempo di mercato (conflazione di serie, 1000 ms): lo scanner vede CLOSED."""
    banco = _banco(punteggi, "16:30:00")
    assert _a(banco, "16:30:00.600", HT, "16:30:00") is True
    assert banco.scan.events[EVENTO]["ht"]["status"] == "OPEN"
    assert _a(banco, "16:47:58.100", HT, "16:47:53.765") is True   # SUSPENDED
    assert banco.scan.events[EVENTO]["ht"]["status"] == "SUSPENDED"
    assert _a(banco, "16:47:58.751", HT) is True                    # CLOSED, 651 ms dopo
    assert banco.scan.events[EVENTO]["ht"]["status"] == "CLOSED"
    # flumine riconsegna il book CLOSED a ogni riga dopo: Betfair lo dichiara una
    # volta sola, e una volta sola arriva allo scanner
    assert _a(banco, "16:47:58.900", HT) is False
    assert _a(banco, "16:48:30", HT, "16:47:58.751") is False
    assert banco.scan.events[EVENTO]["ht"]["status"] == "CLOSED"


def test_rb1_la_conflazione_resta_per_gli_stati_non_terminali(punteggi):
    """Solo il TERMINALE salta la conflazione: due book nello stesso secondo
    restano uno (lo stream dello scanner e' a `conflateMs=1000`)."""
    banco = _banco(punteggi, "16:30:00")
    assert _a(banco, "16:30:00.100", HT, "16:29:00") is True
    assert _a(banco, "16:30:00.900", HT, "16:30:00") is False       # stesso secondo
    assert _a(banco, "16:30:01.200", HT, "16:30:00") is True        # finestra nuova
    assert _a(banco, "16:46:26.000", HT, "16:46:25.467") is True    # SUSPENDED
    assert _a(banco, "16:46:26.500", HT, "16:30:00") is False       # nello stesso secondo


# ---------------------------------------------------------------------------
# RB-2 - le finestre di sottoscrizione della produzione
# ---------------------------------------------------------------------------
def test_rb2_finestre_spente_il_banco_di_sempre_l_ht_arriva_dopo_il_45(punteggi):
    banco = _banco(punteggi, "16:46:10")
    assert banco.scan.events[EVENTO]["minute"] >= 45
    assert _a(banco, _dopo_un_giro("16:46:10"), HT, "16:46:10") is True
    assert banco.book_fuori_finestra == {}


def test_rb2_finestre_accese_l_ht_non_arriva_dal_45(punteggi):
    """Dal 45' `is_ht_candidate` e' falso: lo scanner VERO non tiene l'HT sotto
    quote e il suo book non arriva; il MATCH_ODDS si'."""
    banco = _banco(punteggi, "16:46:10", finestre=True)
    assert banco.scan.events[EVENTO]["minute"] >= 45
    t = _dopo_un_giro("16:46:10")
    assert _a(banco, t, HT, "16:46:10") is False
    assert _a(banco, "16:46:11.200", MO) is True        # passato il secondo della conflazione
    assert _a(banco, "16:46:11.200", HT, "16:46:10") is False
    assert banco.book_fuori_finestra == {HT: 2}
    assert HT not in banco.scan.relevant_market_ids("calcio", banco.adesso())


def test_rb2_finestre_accese_l_ht_arriva_dentro_la_sua_finestra(punteggi):
    banco = _banco(punteggi, "16:30:00", finestre=True)
    assert 15 <= banco.scan.events[EVENTO]["minute"] < 45
    assert _a(banco, _dopo_un_giro("16:30:00"), HT, "16:30:00") is True
    assert banco.scan.events[EVENTO]["ht"]["status"] == "OPEN"
    assert banco.book_fuori_finestra == {}


def test_rb2_un_esposizione_di_omega_tiene_l_ht_oltre_il_45(punteggi):
    """Una gamba di Omega viva sull'HT (la forma di `list_bot_exposures`): lo
    scanner di produzione lo tiene sotto quote fino al CLOSED."""
    banco = _banco(punteggi, "16:46:10", finestre=True)
    banco.fonte_esposizioni = lambda: {"omega": [
        {"event_id": EVENTO, "market_id": HT, "sport": "calcio", "bot": "omega"}]}
    t = _dopo_un_giro("16:46:10")
    banco.imposta_ora(_ms(t) / 1000.0 + 10.0)    # oltre il TTL delle esposizioni
    assert banco.applica_book(_libro(HT, "16:46:10")) is True
    assert banco.book_fuori_finestra == {}
    assert _a(banco, "16:47:58.751", HT) is True                    # e il CLOSED arriva
    assert banco.scan.events[EVENTO]["ht"]["status"] == "CLOSED"


def test_rb2_la_registrazione_conferma_solo_i_mercati_sottoscritti(punteggi):
    """Gli heartbeat di produzione confermano le sottoscrizioni della
    connessione: un mercato fuori finestra non viene confermato."""
    banco = _banco(punteggi, "16:44:00", finestre=True)
    assert _a(banco, _dopo_un_giro("16:44:00"), HT, "16:44:00") is True
    banco.pubblica()
    conferma_ht = banco.scan.flusso_conferma.get(HT)
    assert conferma_ht is not None
    assert _a(banco, "16:46:10", MO) is True
    for ts, rec in punteggi:
        if _ms("16:44:00") < ts <= _ms("16:46:10"):
            banco.applica_punteggio(EVENTO, rec)
    banco.imposta_ora(_ms(_dopo_un_giro("16:46:10")) / 1000.0)
    banco.pubblica()
    assert banco.scan.flusso_conferma.get(HT) == conferma_ht         # non confermato
    assert banco.scan.flusso_conferma.get(MO) == pytest.approx(
        _ms(_dopo_un_giro("16:46:10")) / 1000.0)


def test_rb2_i_voluti_si_rifanno_alla_cadenza_del_giro_dello_scanner(punteggi):
    banco = _banco(punteggi, "16:30:00", finestre=True)
    chiamate: List[float] = []
    vera = banco.scan.relevant_market_ids

    def contata(sport, now):
        chiamate.append(now.timestamp())
        return vera(sport, now)

    banco.scan.relevant_market_ids = contata
    for passo in range(1, 21):                   # 20 book in 2 s di mercato
        banco.imposta_ora(_ms("16:30:00") / 1000.0 + 0.1 * passo)
        banco.sottoscritto(HT)
    assert len(chiamate) == 4                    # uno ogni GIRO_SCANNER_S (0,5 s)
    assert B.GIRO_SCANNER_S == 0.5
