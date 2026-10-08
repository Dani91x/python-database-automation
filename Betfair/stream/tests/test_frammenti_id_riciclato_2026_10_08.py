"""08/10/2026 (coordinatore cloud): la memoria «visto dal» dei frammenti di mercato
non si fa ingannare da un id() riciclato.

Prima la chiave era il solo ``id(stream)``: un frammento chiuso da flumine (non da
``GestoreFrammenti._chiudi``) lasciava la sua voce, e un frammento NUOVO con lo
stesso id() ne ereditava il «dal» (test instabile
``test_auto_follow_rifiuto_betfair_rientra_e_dichiara``, rosso a caso nel cloud).
Qui il riciclo dell'id() si FORZA (``id`` del modulo sostituito), quindi il caso
e' deterministico."""
from __future__ import annotations

from types import SimpleNamespace

from Betfair.stream import frammenti_mercato as FM


def _gestore() -> FM.GestoreFrammenti:
    return FM.GestoreFrammenti(per_conn=10, max_conn=2)


def test_frammento_nuovo_con_lo_stesso_id_non_eredita_il_dal(monkeypatch):
    monkeypatch.setattr(FM, "id", lambda _o: 42, raising=False)   # id() riciclato
    g = _gestore()
    vecchio = SimpleNamespace(stream_id=7)
    assert g._dal_visto(vecchio, 100.0) == 100.0
    # il vecchio sparisce SENZA passare da _chiudi (lo chiude flumine): la voce resta
    nuovo = SimpleNamespace(stream_id=8)
    assert g._dal_visto(nuovo, 500.0) == 500.0, "il frammento nuovo ha il SUO «dal»"


def test_lo_stesso_frammento_tiene_il_suo_dal(monkeypatch):
    monkeypatch.setattr(FM, "id", lambda _o: 42, raising=False)
    g = _gestore()
    s = SimpleNamespace(stream_id=7)
    assert g._dal_visto(s, 100.0) == 100.0
    assert g._dal_visto(s, 900.0) == 100.0, "lo stesso frammento non ricomincia"
