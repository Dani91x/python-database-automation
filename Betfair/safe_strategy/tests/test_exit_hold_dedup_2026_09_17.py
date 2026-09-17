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


def test_un_locked_che_cambia_per_davvero_riscrive_il_meta():
    """AGGIORNATO 17/09 sera: da qui in poi ``meta.exit_hold`` (per la UI, al
    centesimo) e l'ATTIVITA' (per la scheda, al SEGNO — vedi
    ``test_il_segno_del_locked_governa_lattivita_non_il_centesimo`` piu' sotto)
    hanno soglie diverse di proposito. Un vero scivolamento del bloccato deve
    sempre farsi vedere nel meta (la UI lo mostra dal vivo); l'attivita' invece
    NON duplica una riga per un peggioramento che resta dello stesso segno
    (utile che si riduce ma resta utile, o perdita che si aggrava ma resta
    perdita): quello lo denuncia il segno che cambia, non il numero."""
    db = FakeDB()
    meta: dict = {}
    _hold_riga(db, meta, best_lay=1.10)
    locked_1 = round(float(meta["exit_hold"]["locked"]), 2)
    # un lay molto peggiore del primo blocca un P&L diverso di ben piu' di un
    # centesimo: e' uno scivolamento vero, non rumore di tick — ma resta
    # NEGATIVO in entrambi i casi (stesso segno).
    _hold_riga(db, meta, best_lay=1.80)
    locked_2 = round(float(meta["exit_hold"]["locked"]), 2)
    assert locked_1 != locked_2, "il test non falsifica nulla se il locked non e' cambiato"
    assert locked_1 < 0 and locked_2 < 0, "questo test misura uno scivolamento a segno invariato"
    # meta.exit_hold segue SEMPRE il numero vero (al centesimo), per la UI
    assert round(float(meta["exit_hold"]["locked"]), 2) == locked_2
    # l'ATTIVITA' invece non duplica: stesso segno, nessuna riga in piu'
    righe = _righe_exit_hold(db)
    assert len(righe) == 1, (
        f"stesso segno ({locked_1} -> {locked_2}): l'attivita' non deve duplicare, "
        f"trovate {len(righe)} righe")


# ===========================================================================
# REPERTO 17/09 SERA: la firma dell'ATTIVITA' e' PIU' GROSSA di quella del
# meta (``_hold_firma_attivita`` vs ``_hold_firma``). Su una riga da 3 EUR il
# locked cambia centesimo quasi a ogni tick e ``_hold_firma`` lo vede sempre
# come un cambio vero: 126 righe di attivita' "tengo" in 12 minuti su due
# righe paper. Qui la sostanza dell'ATTIVITA' e' (motivo, tipo, codice del
# motivo, fonte, SEGNO del bloccato): un centesimo che balla nello stesso
# segno non scrive una riga nuova, un cambio di segno si'.
# ===========================================================================
def _trade_paper():
    return {"id": 852, "strategy": "model", "side": "back", "size": 3.0,
            "price": 1.05, "selection_id": 9, "market_id": "m2", "mode": "paper",
            "commission": 0.05, "event_id": "e2", "meta": {}}


def _info_modello(locked: float, *, why: str = "modello: tengo") -> dict:
    return {"p_lose": 0.3, "source": "model", "locked": locked, "ev_hold": 0.1,
            "hold_profit": 0.2, "loss_if_lose": 1.0, "why": why}


def test_il_segno_del_locked_governa_lattivita_non_il_centesimo():
    """Sequenza esatta del reperto: +0,00 -> -0,03 (cambio di segno, SCRIVE),
    -0,03 -> -0,05 (stesso segno, NON scrive), -0,05 -> +0,02 (cambio di
    segno, SCRIVE)."""
    db = FakeDB()
    trade = _trade_paper()
    meta: dict = {}
    S._write_model_hold(db, trade, meta, _info_modello(0.00), NOW)   # 1: prev assente, scrive
    S._write_model_hold(db, trade, meta, _info_modello(-0.03), NOW)  # 2: nonneg->neg, scrive
    S._write_model_hold(db, trade, meta, _info_modello(-0.05), NOW)  # stesso segno, NON scrive
    S._write_model_hold(db, trade, meta, _info_modello(0.02), NOW)   # 3: neg->nonneg, scrive

    righe = _righe_exit_hold(db)
    assert len(righe) == 3, f"attese 3 righe (segno cambiato 2 volte + la prima), trovate {len(righe)}: {righe}"
    lockeds = [r["locked"] for r in righe]
    assert lockeds == [0.00, -0.03, 0.02], lockeds
    # il meta (per la UI) resta AL CENTESIMO su ogni chiamata, comprese quelle
    # che non hanno scritto l'attivita': -0,03 -> -0,05 e' un cambio vero per
    # meta.exit_hold anche se l'attivita' tace.
    assert round(float(meta["exit_hold"]["locked"]), 2) == 0.02


def test_falsificazione_senza_la_firma_grossa_lattivita_scrive_ogni_centesimo(monkeypatch):
    """Rimessa ``_hold_firma`` (al centesimo) al posto di ``_hold_firma_attivita``
    sull'ATTIVITA' (il difetto del 17/09 sera), la STESSA sequenza scrive una
    riga per OGNI chiamata: e' il rumore che il reperto denuncia (126 righe in
    12 minuti)."""
    monkeypatch.setattr(S, "_hold_firma_attivita", S._hold_firma)
    db = FakeDB()
    trade = _trade_paper()
    meta: dict = {}
    S._write_model_hold(db, trade, meta, _info_modello(0.00), NOW)
    S._write_model_hold(db, trade, meta, _info_modello(-0.03), NOW)
    S._write_model_hold(db, trade, meta, _info_modello(-0.05), NOW)
    S._write_model_hold(db, trade, meta, _info_modello(0.02), NOW)
    righe = _righe_exit_hold(db)
    assert len(righe) == 4, (
        "senza la firma grossa dell'attivita', ogni centesimo diverso scrive: "
        f"attese 4 righe, trovate {len(righe)}")


def test_exit_hold_porta_il_mode_del_trade_anche_col_servizio_in_live():
    """Una riga PAPER deve portare ``mode='paper'`` nell'attivita' 'exit_hold'
    ANCHE quando il ciclo del servizio e' etichettato live (``_LOG_MODE``):
    prima del fix il timbro del servizio sovrascriveva quello del trade e 107
    righe su 127 di trade paper finivano etichettate LIVE."""
    S.set_log_mode("live")
    try:
        db = FakeDB()
        trade = _trade_paper()
        meta: dict = {}
        S._write_model_hold(db, trade, meta, _info_modello(0.10), NOW)
        righe = _righe_exit_hold(db)
        assert len(righe) == 1
        assert righe[0]["mode"] == "paper", (
            f"riga paper etichettata '{righe[0].get('mode')}' col servizio in live")
    finally:
        S.set_log_mode("")


def test_falsificazione_senza_il_mode_sulla_riga_il_servizio_la_timbra_live():
    """Tolto ``mode`` dal payload di ``_write_model_hold`` (il difetto vero),
    ``_log`` timbra il modo del SERVIZIO: una riga paper risulterebbe live."""
    S.set_log_mode("live")
    try:
        db = FakeDB()
        trade = _trade_paper()
        meta: dict = {}
        why = "modello: tengo"
        info = _info_modello(0.10, why=why)
        code = XE.hold_code(why)
        hold = {"reason": why, "code": code, "kind": "model", "p_lose": info.get("p_lose"),
                "source": info.get("source"), "locked": info.get("locked"),
                "ev_hold": info.get("ev_hold"), "ts": NOW.isoformat()}
        S._write_meta_key(db, trade, meta, S.HOLD_KEY, hold)
        # lo stesso _log del vero, ma SENZA "mode" nel payload (il difetto)
        S._log(db, "exit_hold", {"trade_id": trade.get("id"), "event_id": trade.get("event_id"),
                                 "kind": "model", "reason": why, "msg": why,
                                 **{k: info.get(k) for k in
                                    ("p_lose", "source", "locked", "ev_hold",
                                     "hold_profit", "loss_if_lose")}})
        righe = _righe_exit_hold(db)
        assert righe[0]["mode"] == "live", (
            "senza 'mode' nel payload il servizio in live avrebbe dovuto timbrare live")
    finally:
        S.set_log_mode("")
