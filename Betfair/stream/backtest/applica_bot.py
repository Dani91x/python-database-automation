"""applica_bot.py - "APPLICA BOT" del Match Replay (06/10/2026).

Fa girare un bot sulla registrazione di una partita con il CODICE DI
PRODUZIONE, dallo stesso punto d'ingresso del banco comune
(``registro_bot.bot(nome).funzione_replay()``, cioe' quello che usa
``python -m Betfair.stream.backtest.certifica``): flumine simulato, coda,
latenza e bet delay del banco, minimi .it. Nessun replay "a parte".

Ne esce la CRONOLOGIA DEGLI ORDINI del bot: le righe dello specchio
``betfair_live_orders`` (le stesse che la sessione vera scrive e che il ladder
legge), ciascuna con l'istante ``_ms`` del banco (= publish time Betfair, lo
stesso orologio dei frame del replay). Si tengono solo le righe in cui lo stato
dell'ordine CAMBIA (la sessione le riscrive a ogni giro dello specchio).

Per ora: lo Scalper calcio (maker, sniper, media under). Gli altri bot si
aggiungono a ``SCENARI_VISIVI`` quando il loro banco espone lo specchio.

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

#: bot -> scenario -> etichetta mostrata nel menu "Applica bot" del replay
SCENARI_VISIVI: Dict[str, Dict[str, str]] = {
    "scalper_calcio": {
        "media-under-paper": "Scalper - Media Under 2,5 (prova)",
        "media-under-35": "Scalper - Media Under 3,5",
        "media-under": "Scalper - Media Under 2,5 (soldi veri simulati)",
        "paper": "Scalper - maker (prova)",
        "base": "Scalper - maker (soldi veri simulati)",
        "sniper-paper": "Scalper - sniper (prova)",
    },
}

#: cadenza del banco: quella di ``certifica`` (``--ogni-ms`` 0 = cadenza del servizio)
OGNI_MS = 0

#: i campi che, se cambiano, fanno una riga nuova della cronologia
_CAMPI_STATO = ("status", "price", "size", "size_matched", "size_remaining",
                "size_cancelled", "size_lapsed", "size_voided",
                "average_price_matched", "bet_id")


def _chiave(r: Dict[str, Any]) -> str:
    return str(r.get("client_order_ref") or r.get("bet_id") or id(r))


def cronologia(righe: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Le righe dello specchio (in ordine di scrittura) ridotte ai CAMBI di
    stato di ogni ordine, ordinate per istante. PURA."""
    ultimo: Dict[str, tuple] = {}
    out: List[Dict[str, Any]] = []
    for r in righe or []:
        if not isinstance(r, dict) or r.get("_ms") is None:
            continue
        k = _chiave(r)
        firma = tuple(r.get(c) for c in _CAMPI_STATO)
        if ultimo.get(k) == firma:
            continue
        ultimo[k] = firma
        out.append(dict(r))
    out.sort(key=lambda x: int(x["_ms"]))
    return out


def esegui(params: Dict[str, Any], data_dir: Optional[str] = None) -> Dict[str, Any]:
    """Esegue lo scenario chiesto e torna ``{"righe": [...], "note": [...],
    "segno": "OK|KO|NE", ...}``. Solleva ValueError su una richiesta non valida
    (bot o scenario fuori elenco, registrazione assente)."""
    from .registro_bot import bot as _bot

    nome = str(params.get("bot") or "")
    scenario = str(params.get("scenario") or "")
    event_id = str(params.get("event_id") or "")
    if nome not in SCENARI_VISIVI:
        raise ValueError("bot non applicabile al replay: %r (disponibili: %s)"
                         % (nome, ", ".join(sorted(SCENARI_VISIVI))))
    if scenario not in SCENARI_VISIVI[nome]:
        raise ValueError("scenario non disponibile per %s: %r" % (nome, scenario))
    if not event_id:
        raise ValueError("event_id mancante")
    from . import minimi_banco as _MB
    from .certifica import _freni_da_banco

    registrato = _bot(nome)
    funzione = registrato.funzione_replay()
    cartella = data_dir or registrato.cartella()
    # lo STESSO ambiente di ``certifica`` (``_uno``): registro dell'exchange
    # simulato azzerato, freni e ambiente del banco (soldi veri simulati serviti)
    _MB.REGISTRO.azzera()
    with _freni_da_banco():
        ref = funzione(event_id, data_dir=cartella, scenario=scenario, ogni_ms=OGNI_MS)
    note = list(getattr(ref, "note", []) or [])
    if any(str(n).startswith("registrazione assente") for n in note):
        raise ValueError("registrazione assente per la partita %s in %s: il bot si "
                         "applica solo alle partite registrate (Segui live con REC)"
                         % (event_id, cartella))
    righe = cronologia(list(getattr(ref, "ordini_specchio", []) or []))
    violazioni = [getattr(v, "codice", str(v)) for v in (getattr(ref, "violazioni", []) or [])]
    return {
        "bot": nome, "scenario": scenario, "event_id": event_id,
        "etichetta": SCENARI_VISIVI[nome][scenario],
        "righe": righe,
        "ordini": len({_chiave(r) for r in righe}),
        "violazioni": violazioni,
        "note": [str(n)[:300] for n in note[-12:]],
    }
