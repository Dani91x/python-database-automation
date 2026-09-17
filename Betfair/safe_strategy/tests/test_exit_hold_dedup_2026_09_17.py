# -*- coding: utf-8 -*-
"""REPERTO LIVE 17/09 (h10:49-10:52, trade #297, tennis): dopo che l'utente ha
ignorato la proposta di uscita #12, il bot ha scritto in
`safe_strategy_activity` la STESSA riga 'exit_hold' («incasso rifiutato:
bloccherebbe +0,00 € invece di almeno +0,01 €», reason leader_vince_il_game,
locked 0.0) ogni 15-30 s per due minuti (righe 2097-2102, identiche a parte
back 1.01/None). Con 5 posizioni aperte sono decine di scritture al minuto:
e' la stessa lezione del 13/09 (budget IO del DB esaurito, PGRST002).

Il meccanismo (M-28, `bot_service._model_gate`/`_write_model_hold`) gia'
confrontava un CODICE senza numeri (`exits.hold_code`) per non riscrivere a
ogni tick — ma cosi' facendo perdeva di vista un `locked` che si sposta per
davvero (il messaggio-modello "incasso rifiutato: bloccherebbe # invece di
almeno #" resta identico anche quando il numero dentro cambia). La sostanza
adesso e' (motivo, tipo di uscita, messaggio senza numeri, LOCKED AL
CENTESIMO, fonte) — `bot_service._hold_firma`: un tick di back/lay che non
sposta il centesimo non riscrive nulla, un centesimo che si muove per davvero
si'.

Questo test chiama `_model_gate` (la funzione che scrive 'exit_hold' per le
uscite in PROFITTO) 3 volte con la STESSA situazione, riusando lo stesso
`meta` fra le chiamate (come sulla riga vera: `_write_meta_key` lo aggiorna in
place a ogni giro): si aspetta UNA sola riga di attivita'. Poi cambia il P&L
bloccato di piu' di un centesimo: si aspetta una SECONDA riga.

FALSIFICAZIONE (obbligatoria, PROCESSO_STANDARD_BOT.md): con la deduplica
disattivata (confronto forzato sempre "diverso") il test torna ROSSO — vedi il
referto della sessione per l'output del giro falsificato.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

from datetime import datetime, timezone

from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy import exits as XE

NOW = datetime(2026, 9, 17, 10, 49, tzinfo=timezone.utc)


class FakeDB:
    """Le sole firme che `_model_gate`/`_write_meta_key` usano davvero:
    `closing_trades_for` (nessuna gamba di chiusura nota), `log` (l'attivita',
    catturata per l'assert), `update_trade` (no-op: il `meta` lo teniamo noi,
    come fa `_write_meta_key` sull'oggetto passato)."""

    def __init__(self) -> None:
        self.activity: list[tuple[str, dict]] = []

    def closing_trades_for(self, _ids):
        return []

    def log(self, kind, payload):
        self.activity.append((kind, dict(payload)))

    def update_trade(self, *_a, **_k):
        pass


def _trade():
    return {"id": 297, "strategy": "tennis", "side": "back", "size": 3.0,
            "price": 1.03, "selection_id": 7, "market_id": "m1", "mode": "live",
            "commission": 0.05, "event_id": "e1", "meta": {}}


def _hold_riga(db, meta, *, best_lay):
    """Una valutazione dell'uscita, stesso contratto di `_process_exit_one`:
    stesso trade e stesso `meta` (riusato fra le chiamate), solo il prezzo di
    chiusura (`best_lay`) cambia, come farebbe il feed a ogni tick."""
    xp = XE.merge_exit_params({"tennis_take_profit_min_eur": 0.01})
    return S._model_gate(
        db=db, trade=_trade(), meta=meta,
        decision=XE.ExitDecision("profit", "leader_vince_il_game", 0.0),
        prices={"back": 1.01, "lay": best_lay}, payload={},
        params={"commission_pct": 5.0}, xp=xp, now=NOW, opp_mod=None, opps_state=None)


def _righe_exit_hold(db) -> list[dict]:
    return [p for k, p in db.activity if k == "exit_hold"]


def test_lo_stesso_hold_non_si_riscrive_tre_volte():
    db = FakeDB()
    meta: dict = {}
    for _ in range(3):
        _hold_riga(db, meta, best_lay=1.10)
    righe = _righe_exit_hold(db)
    assert len(righe) == 1, f"3 chiamate identiche hanno scritto {len(righe)} righe: {righe}"
    assert righe[0]["reason"] == "leader_vince_il_game"
    assert "exit_hold" in meta, "il meta della UI deve comunque portare l'ultimo hold"


def test_un_locked_che_cambia_per_davvero_scrive_una_seconda_riga():
    db = FakeDB()
    meta: dict = {}
    _hold_riga(db, meta, best_lay=1.10)
    locked_1 = round(float(meta["exit_hold"]["locked"]), 2)
    # un lay molto peggiore del primo blocca un P&L diverso di ben piu' di un
    # centesimo: e' uno scivolamento vero, non rumore di tick.
    _hold_riga(db, meta, best_lay=1.80)
    locked_2 = round(float(meta["exit_hold"]["locked"]), 2)
    assert locked_1 != locked_2, "il test non falsifica nulla se il locked non e' cambiato"
    righe = _righe_exit_hold(db)
    assert len(righe) == 2, f"il locked e' cambiato ({locked_1} -> {locked_2}) ma le righe sono {len(righe)}"
