"""D1-ter (28/09) - BLOCCO 5: la parita' coda/canale del banco e il ``mode``.

Per Mike il trasporto «coda» e' la strada REST LIVE e il «canale» la strada
PAPER del runner: le righe differiscono per costruzione solo nel ``mode`` e il
rapporto diceva «NON RAGGIUNTA» (scarto (b) del coordinatore, replay 35760084).
Per Mike ``mode`` esce dal confronto; per Omega e Safe il confronto resta
IDENTICO a prima (rapporto byte per byte uguale a quello della versione
precedente della funzione, ricostruita qui dalle sue righe).

Tracce con le stesse chiavi di ``trasporto.traccia`` (ordini con ``fok``, righe
con ``_CHIAVI_RIGA``).
"""
from __future__ import annotations

from typing import Any, Dict

import pytest

from Betfair.stream.backtest import trasporto as T

ORDINE = {"azione": "place", "ref": "x-t2", "market_id": "1.259475534",
          "selection_id": 1222346, "side": "BACK", "price": 3.9, "size": 1.26,
          "fok": True, "t_mercato": "2026-06-30T16:03:32.382000+00:00"}


def _riga(mode: str, status: str = "error") -> Dict[str, Any]:
    r = {"id": 2, "status": status, "side": "back", "market_id": "1.259475534",
         "selection_id": 1222346, "price": 3.9, "size": 1.26, "mode": mode}
    assert tuple(r) == T._CHIAVI_RIGA
    return r


def _tracce(bot: str, mode_coda: str, mode_canale: str, status_canale: str = "error"):
    coda = {"trasporto": "coda", "bot": bot, "ordini": [dict(ORDINE)],
            "righe": [_riga(mode_coda)], "durata_s": 1.0, "rest_sul_canale": []}
    canale = {"trasporto": "canale", "bot": bot, "ordini": [dict(ORDINE)],
              "righe": [_riga(mode_canale, status_canale)], "durata_s": 1.0,
              "rest_sul_canale": []}
    return coda, canale


def _confronta_prima(coda: Dict[str, Any], canale: Dict[str, Any]) -> Dict[str, Any]:
    """La funzione com'era PRIMA di D1-ter (origin/master 0e637c2), per il
    confronto: righe confrontate con TUTTE le chiavi."""
    a = [o for o in coda.get("ordini") or []]
    b = [o for o in canale.get("ordini") or []]
    ka, kb = [T._chiave(o) for o in a], [T._chiave(o) for o in b]
    primo = None
    for i in range(max(len(ka), len(kb))):
        if i >= len(ka) or i >= len(kb) or ka[i] != kb[i]:
            primo = i
            break
    scarti_t = [s for s in (T._secondi(x.get("t_mercato"), y.get("t_mercato"))
                            for x, y in zip(a, b)) if s is not None]
    ra = {r.get("id"): r for r in coda.get("righe") or []}
    rb = {r.get("id"): r for r in canale.get("righe") or []}
    righe_diverse = []
    for rid in sorted(set(ra) | set(rb), key=lambda x: (x is None, x)):
        x, y = ra.get(rid), rb.get(rid)
        if x != y:
            righe_diverse.append({"id": rid, "coda": x, "canale": y})
    ordini_uguali = primo is None
    parita = ordini_uguali and not righe_diverse and not canale.get("rest_sul_canale")
    return {
        "parita": parita,
        "ordini_coda": len(a), "ordini_canale": len(b),
        "ordini_uguali": ordini_uguali,
        "primo_scarto": primo,
        "scarto_coda": (a[primo] if primo is not None and primo < len(a) else None),
        "scarto_canale": (b[primo] if primo is not None and primo < len(b) else None),
        "righe_coda": len(ra), "righe_canale": len(rb),
        "righe_diverse": righe_diverse,
        "rest_sul_canale": len(canale.get("rest_sul_canale") or []),
        "scarto_tempi_s": ({"max": max(scarti_t), "min": min(scarti_t),
                            "n": len(scarti_t)} if scarti_t else None),
        "durata_s": {"coda": coda.get("durata_s"), "canale": canale.get("durata_s")},
        "client": canale.get("client"), "motore": canale.get("motore"),
        "costo_banco_s": canale.get("costo_banco_s"), "book": canale.get("book"),
    }


def test_mike_righe_diverse_solo_per_mode_sono_pari():
    r = T.confronta(*_tracce("mike", "live", "paper"))
    assert r["parita"] is True and r["righe_diverse"] == []
    assert r["chiavi_fuori_confronto"] == ["mode"]


def test_mike_un_esito_diverso_resta_uno_scarto():
    r = T.confronta(*_tracce("mike", "live", "paper", status_canale="open"))
    assert r["parita"] is False and len(r["righe_diverse"]) == 1


@pytest.mark.parametrize("bot", ["omega", "safe_base", "safe_esatto", "safe_punta",
                                 "safe_tennis"])
@pytest.mark.parametrize("modi", [("live", "paper"), ("paper", "paper"), ("live", "live")])
def test_omega_e_safe_rapporto_identico_a_prima(bot, modi):
    coda, canale = _tracce(bot, *modi)
    assert T.confronta(coda, canale) == _confronta_prima(coda, canale)
    if modi[0] != modi[1]:
        assert T.confronta(coda, canale)["parita"] is False   # mode conta ancora


def test_solo_mike_nel_registro_live_paper():
    assert T.BOT_CODA_LIVE_CANALE_PAPER == frozenset({"mike"})
