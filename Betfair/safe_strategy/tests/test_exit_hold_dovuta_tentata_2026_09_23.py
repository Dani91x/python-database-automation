# -*- coding: utf-8 -*-
"""REPERTO 23/09 (replay del banco, scenario 'chiusura-abbinata-in-parte',
evento 35794049): `bot_service._persist_exit_request` toglie `meta.exit_hold`
SOLO quando l'uscita e' stata inviata (`req.get("sent")`). Quando un'uscita
OBBLIGATORIA (kind non in `XE.PROFIT_KINDS`, cioe' 'loss'/'red_card'/
'mandatory') viene TENTATA ma l'ordine e' ucciso (es. `close_trade` torna un
errore, si logga 'cashout_error' e si va in 'exit_retry' con attesa breve),
un vecchio `exit_hold` "a modello" (lasciato da un ciclo precedente in cui il
kind era 'profit'/'time', l'unico gate che lo tocca) resta sulla riga. La UI
mostra "trattenuta dal modello" e il controllo T7 del banco
(`certificazione_tennis.py:411-433`, guarda `meta.exit_hold` PRIMA del motivo
di attesa) segna una violazione per quel giro, anche se l'uscita obbligatoria
e' stata regolarmente tentata.

CORREZIONE (bot_service._persist_exit_request, MINIMA, nessun'altra funzione
toccata): quando il `req` persistito rappresenta un tentativo REALE (non le
attese 'niente_da_chiudere'/'chiusura_in_corso', che non consumano un
tentativo e non impostano `last_error`) di un'uscita DOVUTA (kind non in
PROFIT_KINDS), si toglie `meta.exit_hold` anche se l'invio e' fallito. NON
cambia QUANDO si esce ne' COME si decide: solo il tracciamento sulla riga.

Questo file collauda `_persist_exit_request` isolata (stesso contratto della
riga vera: legge `db.get_trade`, scrive `db.update_trade` con `meta`
completo), coi TRE casi del referto:
  1. uscita DOVUTA (kind='mandatory') TENTATA e fallita (last_error valorizzato,
     come nel ramo 'if err:' di `_send_exit`): l'hold vecchio SPARISCE.
  2. uscita INVIATA (sent=True, qualunque kind): comportamento INVARIATO,
     l'hold sparisce (era gia' cosi' prima della correzione).
  3. uscita NON dovuta (kind='profit', in PROFIT_KINDS) TENTATA e fallita:
     l'hold RESTA (il gate di modello se ne occupa altrove, non qui).

FALSIFICAZIONE (obbligatoria, PROCESSO_STANDARD_BOT.md): rimettendo la
condizione originale (`if req.get("sent"): meta.pop(HOLD_KEY, None)`, senza
il ramo "dovuta tentata") il test del caso 1 torna ROSSO — vedi il referto
della sessione per l'output del giro falsificato.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy import exits as XE

HOLD_KEY = S.HOLD_KEY                 # "exit_hold"
REQUEST_KEY = XE.REQUEST_KEY          # "exit_requested"


class FakeDB:
    """Le sole firme che `_persist_exit_request` usa davvero: `get_trade`
    (rilegge il meta CORRENTE della riga, come fa close_trade nel vero DB) e
    `update_trade` (scrive il meta completo). Stesse chiavi del DB reale."""

    def __init__(self, trade: dict) -> None:
        self._trade = dict(trade)

    def get_trade(self, trade_id):
        if int(trade_id) == int(self._trade["id"]):
            return dict(self._trade)
        return None

    def update_trade(self, trade_id, **fields):
        assert int(trade_id) == int(self._trade["id"])
        self._trade.update(fields)


def _vecchio_hold() -> dict:
    """Un hold 'a modello' lasciato da un ciclo precedente (kind profit/time),
    stessa forma di `_model_gate`/`_write_model_hold`."""
    return {"reason": "incasso rifiutato: bloccherebbe +0,00 eur invece di almeno +0,01 eur",
            "code": "sotto_soglia", "kind": "profit", "exit_reason": "leader_vince_il_game",
            "p_lose": 0.42, "source": "modello", "locked": 0.0, "ev_hold": 0.01,
            "ts": "2026-09-23T10:00:00+00:00"}


def _trade_con_hold() -> dict:
    return {"id": 501, "strategy": "tennis", "side": "back", "mode": "live",
            "meta": {HOLD_KEY: _vecchio_hold()}}


# ---------------------------------------------------------------------------
# 1) uscita DOVUTA ('mandatory') TENTATA e fallita -> l'hold vecchio sparisce
# ---------------------------------------------------------------------------
def test_uscita_dovuta_tentata_e_fallita_toglie_hold_vecchio():
    trade = _trade_con_hold()
    db = FakeDB(trade)
    # stesso req che costruirebbe il ramo 'if err:' di _send_exit per
    # un'uscita 'mandatory' su cui close_trade e' tornato un errore
    # ('chiusura_non_eseguita', log 'cashout_error') dopo il primo tentativo:
    req = {"kind": "mandatory", "reason": "due_game_persi_di_fila_e_parita",
           "ts": "2026-09-23T10:05:00+00:00", "minute": None, "score": None,
           "attempts": 1, "last_attempt_ts": "2026-09-23T10:05:00+00:00",
           "sent": False, "failed": False, "last_error": "chiusura_non_eseguita",
           "detail": "insufficient funds"}

    S._persist_exit_request(db, trade, req)

    meta = db.get_trade(501)["meta"]
    assert HOLD_KEY not in meta, \
        "l'uscita obbligatoria e' stata TENTATA (last_error): l'hold vecchio non vale piu'"
    assert meta[REQUEST_KEY]["kind"] == "mandatory"
    assert meta[REQUEST_KEY]["last_error"] == "chiusura_non_eseguita"
    # anche l'oggetto trade passato per riferimento va aggiornato (come il vero)
    assert HOLD_KEY not in trade["meta"]


# ---------------------------------------------------------------------------
# 2) uscita INVIATA: comportamento invariato (l'hold sparisce, come prima)
# ---------------------------------------------------------------------------
def test_uscita_inviata_toglie_hold_come_prima():
    trade = _trade_con_hold()
    db = FakeDB(trade)
    req = {"kind": "mandatory", "reason": "due_game_persi_di_fila_e_parita",
           "sent": True, "closing_trade_id": 900, "price": 1.5, "size": 3.0,
           "pending_fill": False, "residual_after": 0.0}

    S._persist_exit_request(db, trade, req)

    meta = db.get_trade(501)["meta"]
    assert HOLD_KEY not in meta
    assert meta[REQUEST_KEY]["sent"] is True


# ---------------------------------------------------------------------------
# 3) uscita NON dovuta (kind 'profit', in PROFIT_KINDS) tentata e fallita:
#    l'hold resta (non e' compito di _persist_exit_request toglierlo qui)
# ---------------------------------------------------------------------------
def test_uscita_non_dovuta_tentata_e_fallita_lascia_hold():
    trade = _trade_con_hold()
    db = FakeDB(trade)
    req = {"kind": "profit", "reason": "leader_vince_il_game",
           "ts": "2026-09-23T10:05:00+00:00", "attempts": 1,
           "last_attempt_ts": "2026-09-23T10:05:00+00:00",
           "sent": False, "failed": False, "last_error": "chiusura_non_eseguita",
           "detail": "insufficient funds"}

    S._persist_exit_request(db, trade, req)

    meta = db.get_trade(501)["meta"]
    assert isinstance(meta.get(HOLD_KEY), dict), \
        "kind 'profit' e' in PROFIT_KINDS: non e' 'dovuta', l'hold non si tocca qui"
    assert meta[REQUEST_KEY]["last_error"] == "chiusura_non_eseguita"


# ---------------------------------------------------------------------------
# 4) attesa (niente_da_chiudere): NON e' un tentativo reale, last_error
#    assente -> l'hold resta anche se il kind e' 'mandatory'
# ---------------------------------------------------------------------------
def test_attesa_niente_da_chiudere_non_e_un_tentativo_lascia_hold():
    trade = _trade_con_hold()
    db = FakeDB(trade)
    # stesso req del ramo 'niente_da_chiudere' di _send_exit: nessun
    # last_error, gli attempts vengono anzi DECREMENTATI (non e' un tentativo)
    req = {"kind": "mandatory", "reason": "due_game_persi_di_fila_e_parita",
           "ts": "2026-09-23T10:05:00+00:00", "attempts": 0,
           "last_attempt_ts": "2026-09-23T10:05:00+00:00",
           "sent": False, "failed": False, "note": "niente_da_chiudere"}

    S._persist_exit_request(db, trade, req)

    meta = db.get_trade(501)["meta"]
    assert isinstance(meta.get(HOLD_KEY), dict), \
        "niente_da_chiudere non e' un tentativo: l'hold non si tocca"
