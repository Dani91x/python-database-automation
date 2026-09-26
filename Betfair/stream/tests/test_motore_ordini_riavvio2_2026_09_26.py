"""26/09 - MOTORE ORDINI via canale: i reperti del riavvio 2 (porte accese, 15:16-15:48Z).

Reperti (AUDIT_2026-09-25/E2E_FASE2_BOT_PAPER_2026-09-26.md, e2e_fase2/ADMIN26_ORDINI_SCHEDE.md
"Riavvio 2, porte accese"):
  1. JOURNAL KO (alert 511): il comando dal canale porta ``side`` "LAY"/"BACK" (stile
     API) e il motore lo passava GREZZO; ``betfair_live_journal`` e
     ``betfair_live_order_requests`` hanno ``CHECK (side IN ('back','lay'))``: insert
     rifiutato, giornale e storico della coda bucati. Ora il lato si normalizza UNA
     volta all'ingresso (``valida_comando``) e ``_journal_scrivi`` lo abbassa comunque.
  2. ``source='runner'`` nello specchio per gli ordini dei bot (R9): la riga dello
     specchio di un comando porta il nome dell'ATTORE; il desktop resta 'runner'
     (calcio) / 'manual' (tennis). Senza la migrazione del CHECK la riga si scrive
     comunque (ripiego senza ``source``): lo specchio non si perde mai.
  3. ``runner_non_agganciato`` subito dopo l'accensione (R12): a runner senza
     framework il comando e' ACCETTATO ``in_aggancio`` e servito all'arrivo del
     mercato, con scadenza dichiarata (10 s) e rifiuto CERTO oltre; mai due invii.
  4. ``seq`` uguale fra attori: e' PER ATTORE per costruzione (la porta di ogni bot
     conta i buchi sul suo seq contiguo); la risincronizzazione e' per attore.
  5. R11: i ref interni ``awlq``/``awtq`` ripartivano da 9000000000 a ogni avvio e
     in LIVE sovrascrivevano righe dello specchio di sessioni precedenti.
  6. R10: fase ``abbinato_parziale`` con l'ordine abbinato per intero.

Finti: quelli di ``test_motore_ordini_2026_09_24`` (canale VERO, client flumine VERI,
DB spia con le chiavi vere) + un DB che applica i CHECK veri delle migrazioni
(``betfair_live_pnl_journal.sql``, ``betfair_live_order_queue.sql``,
``betfair_live_account_heartbeat.sql``/``scalper_auto_mode_2026-09-25.sql``).
Nessuna rete, nessun DB vero, nessun ordine reale.
"""
from __future__ import annotations

import itertools
import time
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from Betfair.stream import db as DB
from Betfair.stream import live_order_worker as LOW
from Betfair.stream import motore_ordini as MO
from Betfair.stream.tests.test_motore_ordini_2026_09_24 import (  # noqa: F401 - fixture
    _Q, _SbSpia, _ack, _cmd, _manda, amb)


# ---------------------------------------------------------------------------
# DB finto con i CHECK VERI (testo dell'errore come PostgREST/Postgres 23514)
# ---------------------------------------------------------------------------
_CHECK_SIDE = {"betfair_live_journal": "betfair_live_journal_side_check",
               "betfair_live_order_requests": "betfair_live_order_requests_side_check"}
_SOURCE_AMMESSE_OGGI = ("runner", "account", "scalper")   # CHECK in produzione (25/09)


class _QCheck(_Q):
    def execute(self) -> Any:
        p = self._payload if isinstance(self._payload, dict) else {}
        if self._op in ("insert", "upsert"):
            vincolo = _CHECK_SIDE.get(self._tab)
            if vincolo and p.get("side") is not None and p.get("side") not in ("back", "lay"):
                self._spia.rifiutate.append((self._tab, dict(p)))
                raise Exception(  # noqa: TRY002 - forma dell'APIError di postgrest
                    {"code": "23514", "message": f'new row for relation "{self._tab}" '
                                                 f'violates check constraint "{vincolo}"'})
            if (self._tab == "betfair_live_orders" and self._spia.check_source
                    and "source" in p and p["source"] not in self._spia.source_ammesse):
                self._spia.rifiutate.append((self._tab, dict(p)))
                raise Exception(  # noqa: TRY002
                    {"code": "23514", "message": 'new row for relation "betfair_live_orders" '
                                                 'violates check constraint '
                                                 '"betfair_live_orders_source_check"'})
        return super().execute()


class _SbCheck(_SbSpia):
    def __init__(self, check_source: bool = False,
                 source_ammesse: tuple = _SOURCE_AMMESSE_OGGI) -> None:
        super().__init__()
        self.rifiutate: List[tuple] = []
        self.check_source = check_source
        self.source_ammesse = source_ammesse

    def table(self, nome: str) -> _QCheck:
        return _QCheck(self, nome)


def _con_db_check(amb: Any, **kw: Any) -> _SbCheck:
    sb = _SbCheck(**kw)
    amb.scrittore._sb_factory = lambda: sb
    amb.scrittore._sb = None
    return sb


def _scritte(sb: _SbSpia, tabella: str, op: str) -> List[Dict[str, Any]]:
    return [p for _t, tab, o, p in sb.chiamate if tab == tabella and o == op]


# ===========================================================================
# 1. JOURNAL: lato normalizzato all'ingresso del comando
# ===========================================================================
@pytest.mark.parametrize("lato,atteso", [("LAY", "lay"), ("BACK", "back"),
                                         ("lay", "lay"), ("back", "back")])
def test_comando_col_lato_api_scrive_giornale_e_coda_in_minuscolo(amb, lato, atteso):
    sb = _con_db_check(amb)
    ws = amb.ch.collega("omega")
    _manda(amb, ws, _cmd("omega", 1, side=lato))
    assert _ack(amb, ws)["accettato"] is True
    assert len(amb.market.calls) == 1
    order = amb.market.calls[0][0]
    assert order.side == atteso.upper()          # verso flumine/Betfair: BACK/LAY
    assert amb.scrittore.svuota(5.0)
    assert sb.rifiutate == []
    giornale = _scritte(sb, "betfair_live_journal", "insert")
    coda = _scritte(sb, "betfair_live_order_requests", "insert")
    assert len(giornale) == 1 and giornale[0]["side"] == atteso
    assert len(coda) == 1 and coda[0]["side"] == atteso
    assert not [p for p in _scritte(sb, "live_alerts", "insert")
                if p.get("code") == "JOURNAL"]


@pytest.mark.parametrize("lato", ["Lay ", "", None, "SELL", 1])
def test_lato_non_ammesso_resta_rifiutato(lato):
    with pytest.raises(MO.Rifiuto) as ex:
        MO.valida_comando("omega", _cmd("omega", 1, side=lato))
    assert ex.value.codice == MO.M_PARAM


def test_journal_scrivi_abbassa_il_lato_anche_da_solo():
    sb = _SbCheck()
    LOW._journal_scrivi(sb, {"id": 5, "market_id": "1.2", "selection_id": 3,
                             "side": "LAY", "price": 2.0, "size": 1.0,
                             "action": "place"}, "paper", {"event_id": None})
    giornale = _scritte(sb, "betfair_live_journal", "insert")
    assert sb.rifiutate == [] and giornale and giornale[0]["side"] == "lay"


@pytest.mark.parametrize("win,lose,price,size", [(-3.0, 3.0, 2.0, 3.0), (5.0, -2.0, 2.5, 2.0),
                                                  (0.0, 0.0, 2.0, 1.0), (-1.0, 1.0, 3.0, 5.0)])
def test_riduzione_uguale_per_lato_maiuscolo_e_minuscolo(win, lose, price, size):
    for lato in ("BACK", "LAY"):
        assert (MO.riduce_esposizione(win, lose, lato.lower(), price, size)
                == MO.riduce_esposizione(win, lose, lato, price, size))


# ===========================================================================
# 2. SPECCHIO: source = attore del comando
# ===========================================================================
def _riga_specchio(cust: str, **kw: Any) -> Dict[str, Any]:
    r = {"bet_id": "B1", "client_order_ref": cust, "request_id": None, "mode": "paper",
         "event_id": "E1", "market_id": "1.234", "selection_id": 47972, "handicap": 0.0,
         "side": "back", "order_type": "LIMIT", "price": 2.5, "size": 3.0,
         "size_matched": 0.0, "size_remaining": 3.0, "size_cancelled": 0.0,
         "size_lapsed": 0.0, "size_voided": 0.0, "average_price_matched": 0.0,
         "status": "EXECUTABLE", "persistence": "LAPSE", "placed_at": None,
         "matched_at": None}
    r.update(kw)
    return r


def _monta_specchio(amb: Any) -> None:
    DB.aggiungi_osservatore_ordini(amb.motore._su_riga_specchio)
    DB.aggiungi_sorgente_ordini(amb.motore.sorgente_ordine)
    DB.imposta_scrittore(amb.scrittore)


@pytest.fixture()
def smonta_sorgente():
    yield
    DB._SORGENTI_ORDINI.clear()


@pytest.mark.parametrize("attore", ["omega", "safe", "mike"])
def test_specchio_di_un_comando_porta_il_nome_del_bot(amb, smonta_sorgente, attore):
    sb = _con_db_check(amb)
    _monta_specchio(amb)
    ws = amb.ch.collega(attore)
    _manda(amb, ws, _cmd(attore, 1))
    cust = amb.ch.per_ws(ws, "order")[0]["d"]["client_order_ref"]
    DB.upsert_live_order(_riga_specchio(cust))
    # l'ordine di prima (coda DB / clic manuale): nessuna source = DEFAULT 'runner'
    DB.upsert_live_order(_riga_specchio("awlq55", bet_id="B2"))
    assert amb.scrittore.svuota(5.0)
    righe = {p["client_order_ref"]: p for p in _scritte(sb, "betfair_live_orders", "upsert")}
    assert righe[cust]["source"] == attore
    assert "source" not in righe["awlq55"]
    # l'evento al bot resta la riga dello specchio di sempre (nessuna chiave nuova)
    ev = [m["d"] for m in amb.ch.per_ws(ws, "order")]
    assert ev[-1]["client_order_ref"] == cust and "source" not in ev[-1]


def test_specchio_del_desktop_resta_runner(amb, smonta_sorgente):
    sb = _con_db_check(amb)
    _monta_specchio(amb)
    ws = amb.ch.collega("desktop")
    _manda(amb, ws, _cmd("desktop", 1))
    cust = amb.ch.per_ws(ws, "order")[0]["d"]["client_order_ref"]
    DB.upsert_live_order(_riga_specchio(cust))
    assert amb.scrittore.svuota(5.0)
    righe = _scritte(sb, "betfair_live_orders", "upsert")
    assert righe and "source" not in righe[-1]


def test_specchio_senza_migrazione_si_scrive_lo_stesso(amb, smonta_sorgente):
    """CHECK di oggi ('runner','account','scalper'): la riga del bot e' rifiutata
    con la source, si riscrive SENZA (DEFAULT 'runner'); lo specchio non si perde."""
    sb = _con_db_check(amb, check_source=True)
    _monta_specchio(amb)
    ws = amb.ch.collega("omega")
    _manda(amb, ws, _cmd("omega", 1))
    cust = amb.ch.per_ws(ws, "order")[0]["d"]["client_order_ref"]
    DB.upsert_live_order(_riga_specchio(cust))
    assert amb.scrittore.svuota(5.0)
    assert [t for t, _p in sb.rifiutate] == ["betfair_live_orders"]
    righe = [p for p in _scritte(sb, "betfair_live_orders", "upsert")
             if p["client_order_ref"] == cust]
    assert righe and "source" not in righe[-1] and righe[-1]["status"] == "EXECUTABLE"


def test_specchio_con_migrazione_applicata_tiene_la_source(amb, smonta_sorgente):
    sb = _con_db_check(amb, check_source=True,
                       source_ammesse=_SOURCE_AMMESSE_OGGI + ("omega", "safe", "mike"))
    _monta_specchio(amb)
    ws = amb.ch.collega("safe")
    _manda(amb, ws, _cmd("safe", 1))
    cust = amb.ch.per_ws(ws, "order")[0]["d"]["client_order_ref"]
    DB.upsert_live_order(_riga_specchio(cust))
    assert amb.scrittore.svuota(5.0)
    assert sb.rifiutate == []
    assert [p["source"] for p in _scritte(sb, "betfair_live_orders", "upsert")] == ["safe"]


def test_upsert_sincrono_senza_scrittore_ripiega_senza_source(monkeypatch, smonta_sorgente):
    sb = _SbCheck(check_source=True)
    monkeypatch.setattr(DB, "get_supabase_client", lambda: sb)
    DB.imposta_scrittore(None)
    DB.aggiungi_sorgente_ordini(lambda _p: "omega")
    DB.upsert_live_order(_riga_specchio("awlq1790000000000001"))
    righe = _scritte(sb, "betfair_live_orders", "upsert")
    assert len(sb.rifiutate) == 1 and righe and "source" not in righe[-1]


def test_migrazione_source_ammette_i_bot_e_non_il_desktop():
    import pathlib
    radice = pathlib.Path(__file__).resolve().parents[3]
    testo = (radice / "migrations" / "betfair_live_orders_source_bot_2026-09-26.sql").read_text(
        encoding="utf-8")
    assert "betfair_live_orders_source_check" in testo and "NOT VALID" in testo
    for v in ("'runner'", "'account'", "'scalper'", "'omega'", "'safe'", "'mike'"):
        assert v in testo
    assert "'desktop'" not in testo


def test_tennis_track_manual_source_dell_attore():
    from Betfair.stream.tennis_live import tennis_live_order_worker as TW

    sess = SimpleNamespace(tracked_orders={}, framework_gen=0)
    try:
        for attore, atteso in (("safe_tennis", "safe_tennis"), ("desktop", "manual"),
                               (None, "manual")):
            LOW._CONTESTO.strategy_ref = attore
            TW._track_manual(sess, f"awtq{attore}", object(), "paper", "E1")
            assert sess.tracked_orders[f"awtq{attore}"]["source"] == atteso
    finally:
        LOW._CONTESTO.strategy_ref = None


def test_reconcile_voce_della_source_del_bot():
    from Betfair.stream import reconcile_worker as RW

    o = SimpleNamespace(event_type_id="1")
    t = SimpleNamespace(event_type_id="2")
    assert RW._fonte_di("betfair_live_orders", {"source": "omega"}, o) == "omega"
    assert RW._fonte_di("betfair_live_orders", {"source": "safe"}, o) == "safe_calcio"
    assert RW._fonte_di("betfair_live_orders", {"source": "mike"}, o) == "mike"
    assert RW._fonte_di("betfair_live_orders", {"source": "runner"}, o) == "manuale_app"
    assert RW._fonte_di("tennis_live_orders", {"source": "safe_tennis"}, t) == "safe_tennis"
    assert RW._fonte_di("tennis_live_orders", {"source": "manual"}, t) == "manuale_app"
    assert RW._fonte_di("tennis_live_orders", {"source": "tennis_pro"}, t) == "bot_tennis"


# ===========================================================================
# 3. AGGANCIO: runner senza framework = accettato in_aggancio, servito all'arrivo
# ===========================================================================
class _AgganciaFinto:
    """Stessa interfaccia di ``auto_follow.AutoFollow`` (``servibile``/``richiedi``)."""

    def __init__(self) -> None:
        self.pronti: set = set()
        self.chiesti: List[tuple] = []
        self.no: Optional[str] = None

    def servibile(self, market_id: Optional[str]) -> bool:
        return str(market_id or "") in self.pronti

    def richiedi(self, market_id: str, *, event_id: Optional[str] = None,
                 motivo: str = "comando") -> Optional[str]:
        self.chiesti.append((market_id, motivo))
        return self.no


def test_aggancio_di_serie_dimensionato_sui_tempi_veri():
    # dal vivo: 1113 ms e 2176 ms quando riuscito, 3000 ms non bastavano (omega-t124)
    assert MO.AGGANCIO_MAX_MS_DEFAULT == 10000


def test_runner_senza_framework_accetta_in_aggancio_e_serve_all_arrivo(amb):
    ag = _AgganciaFinto()
    amb.motore._aggancio = ag
    fl, strat = amb.fl, amb.motore._strategie
    amb.motore.sgancia()
    ws = amb.ch.collega("safe_tennis")
    _manda(amb, ws, _cmd("safe_tennis", 346))
    ack = _ack(amb, ws)
    assert ack["accettato"] is True and ack["motivo"].startswith(MO.M_IN_AGGANCIO)
    assert ag.chiesti and ag.chiesti[0][0] == "1.234" and len(ag.chiesti) == 1
    assert amb.market.calls == [] and "safe_tennis-t346" in amb.motore._in_aggancio
    assert amb.motore.avanza_aggancio() == 0            # ancora senza framework
    # il framework parte col mercato (il runner lo ha aggiunto al piano)
    amb.motore.aggancia(fl, strat)
    assert amb.motore.avanza_aggancio() == 0            # mercato non ancora servibile
    ag.pronti.add("1.234")
    assert amb.motore.avanza_aggancio() == 1
    assert amb.motore.avanza_aggancio() == 0 and amb.motore.drena() == 0
    assert len(amb.market.calls) == 1                   # UN solo invio
    fasi = [m["d"]["fase"] for m in amb.ch.per_ws(ws, "order")]
    assert fasi == ["inviato"]


def test_runner_senza_framework_scadenza_rifiuto_certo_senza_ordine(amb, monkeypatch):
    ag = _AgganciaFinto()
    amb.motore._aggancio = ag
    amb.motore.sgancia()
    ws = amb.ch.collega("omega")
    _manda(amb, ws, _cmd("omega", 124))
    assert _ack(amb, ws)["accettato"] is True
    ora = [int(time.time() * 1000) + 10]
    monkeypatch.setattr(amb.motore, "_ora_ms", lambda: ora[0])
    ora[0] += amb.motore.aggancio_max_ms - 100
    assert amb.motore.avanza_aggancio() == 0
    ora[0] += 200
    assert amb.motore.avanza_aggancio() == 1
    ev = [m["d"] for m in amb.ch.per_ws(ws, "order")]
    assert [e["fase"] for e in ev] == ["rifiutato"]
    assert amb.paper.eseguiti == [] and amb.reale.eseguiti == [] and amb.market.calls == []
    assert not amb.motore._in_aggancio


def test_eta_del_comando_contata_all_arrivo_non_durante_l_aggancio(amb, monkeypatch):
    ag = _AgganciaFinto()
    amb.motore._aggancio = ag
    strat = amb.motore._strategie
    amb.motore.sgancia()
    ws = amb.ch.collega("omega")
    _manda(amb, ws, _cmd("omega", 7, max_eta_ms=3000))
    ora = [int(time.time() * 1000) + 6000]              # 6 s di aggancio > max_eta_ms
    monkeypatch.setattr(amb.motore, "_ora_ms", lambda: ora[0])
    amb.motore.aggancia(amb.fl, strat)
    ag.pronti.add("1.234")
    assert amb.motore.avanza_aggancio() == 1
    assert len(amb.market.calls) == 1


def test_runner_senza_framework_tetto_pieno_rifiuto_dichiarato(amb):
    ag = _AgganciaFinto()
    ag.no = "tetto dei mercati pieno"
    amb.motore._aggancio = ag
    amb.motore.sgancia()
    ws = amb.ch.collega("omega")
    _manda(amb, ws, _cmd("omega", 9))
    ack = _ack(amb, ws)
    assert ack["accettato"] is False and ack["motivo"].startswith(MO.M_AGGANCIO)
    assert "tetto" in ack["motivo"] and amb.market.calls == []


def test_runner_senza_framework_cancel_resta_rifiutato(amb):
    amb.motore._aggancio = _AgganciaFinto()
    amb.motore.sgancia()
    ws = amb.ch.collega("omega")
    _manda(amb, ws, _cmd("omega", 10, azione="cancel", bet_id="123"))
    ack = _ack(amb, ws)
    assert ack["accettato"] is False and ack["motivo"].startswith(MO.M_AGGANCIO)


# ===========================================================================
# 4. seq PER ATTORE (scelta documentata): uguale fra attori, contiguo per attore
# ===========================================================================
def test_seq_per_attore_contiguo_e_da_seq_per_attore(amb):
    wo = amb.ch.collega("omega")
    wsf = amb.ch.collega("safe")
    _manda(amb, wo, _cmd("omega", 1))
    _manda(amb, wsf, _cmd("safe", 1))
    _manda(amb, wo, _cmd("omega", 2))
    seq_o = [m["d"]["seq"] for m in amb.ch.per_ws(wo) if m["t"] in ("ack", "order")]
    seq_s = [m["d"]["seq"] for m in amb.ch.per_ws(wsf) if m["t"] in ("ack", "order")]
    # contigui per attore: la porta del bot conta i buchi su QUESTO seq
    assert seq_o == list(range(seq_o[0], seq_o[0] + len(seq_o)))
    assert seq_s == list(range(seq_s[0], seq_s[0] + len(seq_s)))
    assert seq_o[0] == seq_s[0]                          # stesso numero, attori diversi
    # risincronizzazione: solo i messaggi DELL'attore che la chiede
    prima = len(amb.ch.per_ws(wsf))
    _manda(amb, wsf, {"seq": seq_s[0] - 1}, t="da_seq")
    rimandati = amb.ch.per_ws(wsf)[prima:]
    refs = {m["d"].get("ref") for m in rimandati if m["t"] in ("ack", "order")}
    assert refs == {"safe-t1"}


# ===========================================================================
# 5. R11: ref interni univoci fra un avvio e il successivo
# ===========================================================================
def test_rid_di_due_avvii_successivi_mai_uguali():
    t0 = 1_790_434_467_069
    primo = itertools.count(LOW._base_rid_avvio(t0))
    usati = [next(primo) for _ in range(900)]           # 900 comandi in 1 ms di vita
    secondo = itertools.count(LOW._base_rid_avvio(t0 + 1))
    assert next(secondo) > usati[-1]
    assert not set(usati) & {LOW._base_rid_avvio(t0 + 1) + i for i in range(900)}


def test_rid_valido_per_bigint_json_e_ref_betfair():
    rid = next(LOW._LOCAL_RID)
    assert rid > 9_999_999_999                          # mai piu' la serie 9000000000
    assert rid < 2 ** 53                                # intero esatto anche in JS
    assert len(LOW._cust_ref(rid)) <= 32
    assert len(LOW._leg_ref(rid, "x999")) <= 32 and LOW._leg_ref(rid, "x999").endswith("x999")
    from Betfair.stream.engine import live_trading_strategy as LTS
    assert LTS._request_id_from_ref(LOW._cust_ref(rid)) == rid


def test_rid_tennis_univoco_fra_avvii():
    from Betfair.stream.tennis_live import tennis_live_order_worker as TW

    sid = next(TW._LOCAL_SID)
    assert 9_999_999_999 < sid < 2 ** 53
    assert len(TW._cust_ref(sid)) <= 32 and TW._request_id_from_ref(TW._cust_ref(sid)) == sid
    assert TW._base_sid_avvio(1_790_434_467_069) == LOW._base_rid_avvio(1_790_434_467_069)


def test_eventi_dallo_specchio_con_ref_lunghi_e_gambe(amb):
    """Il riconoscimento dei ref interni non dipende piu' da 10 cifre fisse."""
    DB.aggiungi_osservatore_ordini(amb.motore._su_riga_specchio)
    DB.imposta_scrittore(amb.scrittore)
    ws = amb.ch.collega("safe")
    _manda(amb, ws, _cmd("safe", 1))
    cust = amb.ch.per_ws(ws, "order")[0]["d"]["client_order_ref"]
    assert len(cust) > 14                                # awlq + piu' di 10 cifre
    DB.upsert_live_order(_riga_specchio(cust, bet_id="B1"))
    DB.upsert_live_order(_riga_specchio(cust + "x1", bet_id="B2"))   # gamba di cash-out
    # un ref che PROLUNGA le cifre non e' lo stesso comando
    DB.upsert_live_order(_riga_specchio(cust + "7", bet_id="B3"))
    ev = [m["d"] for m in amb.ch.per_ws(ws, "order")]
    assert [e["bet_id"] for e in ev[1:]] == ["B1", "B2"]


# ===========================================================================
# 6. R10: fase dall'esito reale
# ===========================================================================
@pytest.mark.parametrize("riga,fase", [
    ({"status": "EXECUTABLE", "bet_id": "1", "size": 3.0, "size_matched": 3.0,
      "size_remaining": 0.0}, "abbinato"),
    ({"status": "EXECUTABLE", "bet_id": "1", "size": 3.0, "size_matched": 2.0,
      "size_remaining": 1.0}, "abbinato_parziale"),
    ({"status": "EXECUTABLE", "bet_id": "1", "size_matched": 0.5}, "abbinato_parziale"),
])
def test_fase_segue_l_abbinato_reale(riga, fase):
    assert MO.fase_da_riga(riga) == fase
