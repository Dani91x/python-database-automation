"""Certificazione OMEGA — CASH OUT e FEED FERMO (11/09/2026, checklist 3).

La dashboard spegne il bottone «Cash out» quando la riga del feed di quella
partita ha più di 20 s (`MatchTradesTable.FEED_STALE_S`). Il SERVIZIO deve
avere lo stesso tetto: una richiesta già in coda, o una UI aperta in un'altra
finestra, non deve poter chiudere una posizione ai prezzi di un book
CONGELATO. Lo scanner può essere vivo (heartbeat ok) e la riga di QUELLA
partita ferma da minuti: mercato sospeso, evento uscito dalla finestra dei
venti in-play, stream caduto per quel solo mercato.

Prima di questa certificazione `_cashout_prices` leggeva il feed senza tetto
duro (solo il bypass "scanner vivo"): un lay da 300 € di liability poteva
essere «chiuso» al prezzo di dieci minuti prima, e il P&L bloccato scritto a
DB era una bugia. Ora oltre il tetto la riga del feed viene IGNORATA e si passa
al book REST (autoritativo); se nemmeno quello è utilizzabile, il cash out
viene RIFIUTATO con `prezzi_non_disponibili`.

Nessuna rete, nessun DB: fake market/db e `_feed_row` sostituito.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from Betfair.omega import omega_market as M
from Betfair.omega import omega_service as S

NOW = datetime(2026, 9, 11, 20, 0, 0, tzinfo=timezone.utc)

# prezzi del FEED (quelli "congelati" nello scenario stantio) e prezzi REST
# (quelli veri adesso): devono essere distinguibili a occhio nei confronti.
FEED_LAY = 110.0
REST_LAY = 300.0


def _feed_payload() -> dict:
    return {
        "event_name": "Nord v Sud", "inplay": True, "minute": 52,
        "score_home": 1, "score_away": 0,
        "cs": {
            "market_id": "1.777", "status": "OPEN", "inplay": True, "total_matched": 500.0,
            "selections": [
                {"selection_id": 2, "name": "3 - 0", "back": 90.0, "lay": FEED_LAY,
                 "back_size": 2, "lay_size": 7.5, "runner_status": "ACTIVE"},
            ],
        },
    }


def _trade(**over) -> dict:
    base = {
        "id": 1, "event_id": "ev1", "market_id": "1.777", "selection_id": 2,
        "runner_name": "3 - 0", "side": "lay", "status": "open", "mode": "paper",
        "price": 110.0, "size": 3.0, "liability": 327.0, "phase": "ft_cs",
        "kickoff": None, "meta": {},
    }
    base.update(over)
    return base


class _Market:
    """Market REST fake: risponde con prezzi DIVERSI da quelli del feed."""

    def __init__(self, book: object = "default") -> None:
        self.book = book
        self.calls: list[str] = []

    def read_book(self, market_id, _opts):
        self.calls.append(str(market_id))
        if self.book != "default":
            return self.book
        return {
            "status": "OPEN",
            "runners": [{"selection_id": 2, "back_price": 250.0, "back_size": 4.0,
                         "lay_price": REST_LAY, "lay_size": 6.0, "lay_ladder": ()}],
        }


# --------------------------------------------------------------- il tetto duro
def test_il_tetto_del_servizio_e_quello_della_ui() -> None:
    """Se qualcuno alza il tetto di uno dei due lati, il bottone e il servizio
    smettono di essere d'accordo: la UI spegne e il servizio chiude (o
    viceversa). Il numero è UNO e sta scritto in entrambi i posti."""
    from pathlib import Path

    tsx = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "components"
           / "omega" / "MatchTradesTable.tsx")
    if not tsx.exists():                      # pragma: no cover
        pytest.skip("frontend assente")
    import re

    m = re.search(r"export const FEED_STALE_S = (\d+)", tsx.read_text(encoding="utf-8"))
    assert m, "FEED_STALE_S non trovato nella tabella di Omega"
    assert float(m.group(1)) == S.CASHOUT_FEED_MAX_AGE_S, (
        f"tetto divergente: UI={m.group(1)} s, servizio={S.CASHOUT_FEED_MAX_AGE_S} s"
    )


def test_cs_dal_feed_propaga_il_tetto_duro(monkeypatch) -> None:
    visti: list[object] = []

    def _row(event_id, hard_max_age=None):
        visti.append(hard_max_age)
        return _feed_payload(), "2026-09-11T20:00:00+00:00"

    monkeypatch.setattr(S, "_feed_row", _row)
    S._cs_from_feed(S._real_market, "ev1", max_age=S.CASHOUT_FEED_MAX_AGE_S)
    assert visti == [S.CASHOUT_FEED_MAX_AGE_S], (
        "il tetto duro non arriva al lettore del feed: la riga stantia passerebbe"
    )


# ------------------------------------------------------- prezzi del cash out
def _as_real(monkeypatch, mk: "_Market"):
    """Il feed lo legge SOLO il market REALE (i fake dei test vanno a REST per
    contratto, e il modulo reale fornisce anche le dataclass dello snapshot):
    per esercitare il percorso feed si passa il MODULO vero come market e gli
    si sostituisce il solo `read_book`.

    Ritorna (market da passare, fake su cui contare le chiamate REST).
    """
    monkeypatch.setattr(M, "read_book", mk.read_book)
    return M, mk


def test_feed_FRESCO_prezza_dal_feed_senza_chiamare_betfair(monkeypatch) -> None:
    """Il caso normale: riga fresca → prezzi del feed, ZERO chiamate REST
    (regola del feed unico: nessuna chiamata Betfair duplicata)."""
    monkeypatch.setattr(
        S, "_feed_row",
        lambda eid, hard_max_age=None: (_feed_payload(), "2026-09-11T20:00:00+00:00"),
    )
    market, mk = _as_real(monkeypatch, _Market())
    prices = S._cashout_prices(market, _trade())
    assert prices is not None
    assert prices["lay"] == FEED_LAY, prices
    assert mk.calls == [], "chiamata REST inutile con il feed fresco"


def test_feed_FERMO_ignora_i_prezzi_congelati_e_usa_il_book_REST(monkeypatch) -> None:
    """Riga oltre il tetto: `_feed_row` con `hard_max_age` risponde (None, ts).
    I prezzi NON possono essere quelli congelati: si va al book autoritativo.

    Il market è quello "reale" (percorso feed ATTIVO): senza il tetto duro
    questo test tornerebbe i prezzi congelati del feed.
    """
    def _row(eid, hard_max_age=None):
        # il feed AVREBBE il dato, ma la riga è vecchia: col tetto si scarta
        if hard_max_age is not None:
            return None, "2026-09-11T19:50:00+00:00"
        return _feed_payload(), "2026-09-11T19:50:00+00:00"

    monkeypatch.setattr(S, "_feed_row", _row)
    market, mk = _as_real(monkeypatch, _Market())
    prices = S._cashout_prices(market, _trade())
    assert prices is not None
    assert prices["lay"] == REST_LAY, (
        f"cash out prezzato sul feed CONGELATO ({prices['lay']}) invece del book REST"
    )
    assert mk.calls == ["1.777"], "il book REST non è stato letto"


def test_senza_il_tetto_il_feed_congelato_passerebbe(monkeypatch) -> None:
    """Controprova: è PROPRIO il tetto a fare la differenza. Con `max_age=None`
    (comportamento pre-certificazione) lo stesso feed congelato torna i suoi
    prezzi vecchi — cioè il bug che questa certificazione chiude."""
    monkeypatch.setattr(
        S, "_feed_row",
        lambda eid, hard_max_age=None: (
            (None, "t") if hard_max_age is not None else (_feed_payload(), "t")
        ),
    )
    market, _mk = _as_real(monkeypatch, _Market())
    senza_tetto = S._cs_from_feed(market, "ev1")
    col_tetto = S._cs_from_feed(market, "ev1", max_age=S.CASHOUT_FEED_MAX_AGE_S)
    assert senza_tetto is not None, "il percorso feed non è attivo: test inutile"
    assert col_tetto is None, "il tetto duro non scarta la riga stantia"


def test_feed_FERMO_e_REST_muto_RIFIUTA_il_cash_out(monkeypatch) -> None:
    """Feed fermo + REST che non risponde = nessun prezzo affidabile. Il cash
    out si RIFIUTA: meglio una liability viva e dichiarata che una chiusura a
    prezzi inventati."""
    monkeypatch.setattr(S, "_feed_row", lambda eid, hard_max_age=None: (None, None))

    class _Boom(_Market):
        def read_book(self, market_id, _opts):
            raise RuntimeError("timeout")

    assert S._cashout_prices(_Boom(), _trade()) is None


def test_feed_FERMO_e_mercato_SOSPESO_RIFIUTA_il_cash_out(monkeypatch) -> None:
    """Il mercato non OPEN (SUSPENDED nel post-gol) non produce prezzi: né dal
    feed né dal REST. È lo scenario in cui il trader clicca proprio perché ha
    paura, ed è quello in cui chiudere a prezzi vecchi costa di più."""
    monkeypatch.setattr(S, "_feed_row", lambda eid, hard_max_age=None: (None, None))
    mk = _Market(book={"status": "SUSPENDED", "runners": [
        {"selection_id": 2, "back_price": 1.5, "lay_price": 1.6},
    ]})
    assert S._cashout_prices(mk, _trade()) is None


def test_manual_cashout_rifiuta_e_LO_DICE_con_il_feed_fermo(monkeypatch) -> None:
    """Il percorso completo della richiesta manuale: l'esito torna alla UI come
    `prezzi_non_disponibili` (M-01: un motivo leggibile, non un silenzio)."""
    monkeypatch.setattr(S, "_feed_row", lambda eid, hard_max_age=None: (None, None))

    class _Db:
        def __init__(self) -> None:
            self.logs: list[tuple] = []

        def get_trade(self, tid):
            return _trade(id=int(tid))

        def list_trades(self, *_a, **_k):     # pragma: no cover - non serve
            return []

        def read_control(self):
            return {"params": {}}

        def log(self, kind, payload=None):
            self.logs.append((kind, payload))

    class _Muto(_Market):
        def read_book(self, market_id, _opts):
            return None

    db = _Db()
    out = S._manual_cashout(market=_Muto(), db=db, payload={"trade_id": 1}, now=NOW)
    assert out.get("error") == "prezzi_non_disponibili", out
    # e NESSUNA riga di chiusura è stata creata: la posizione resta intera
    assert not any(k == "cashout_manual" for k, _ in db.logs), db.logs


def test_il_cash_out_non_tocca_una_gamba_non_aperta(monkeypatch) -> None:
    """Guardia già presente, certificata qui: una gamba 'hedged' o 'pending'
    non si richiude (sarebbe una seconda copertura sulla stessa posizione)."""
    monkeypatch.setattr(
        S, "_feed_row",
        lambda eid, hard_max_age=None: (_feed_payload(), "2026-09-11T20:00:00+00:00"),
    )

    class _Db:
        def __init__(self, status: str) -> None:
            self.status = status

        def get_trade(self, tid):
            return _trade(id=int(tid), status=self.status)

        def list_trades(self, *_a, **_k):
            return []

        def read_control(self):
            return {"params": {}}

        def log(self, *_a, **_k):
            pass

    for status in ("hedged", "pending", "won", "error"):
        out = S._manual_cashout(market=_Market(), db=_Db(status),
                                payload={"trade_id": 1}, now=NOW)
        assert out.get("error") == f"trade_non_aperto:{status}", (status, out)
