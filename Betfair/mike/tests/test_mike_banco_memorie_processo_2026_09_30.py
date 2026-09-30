"""BANCO 30/09 - MEMORIE DI PROCESSO NON AZZERATE fra due replay.

Il banco (``replay_registrazioni._certifica_evento``) fa girare piu' scenari
della STESSA partita nello stesso processo, uno dopo l'altro, e fra l'uno e
l'altro chiama SOLO ``service.azzera_cache_di_processo``. Quella funzione non
azzerava le quattro memorie dei cantieri J/J2 (28/09): ``_RIPIEGO_REST_ULTIMO``
(tetto del ripiego REST, per mercato, con l'ora del giro),
``_ULTIMO_STATO_SCANNER``, ``_FLUSSO_CRITICO``, ``_FLUSSO_RIPIEGO``. Il secondo
scenario ripartiva dall'ora d'inizio con l'ora di fine del primo gia' scritta:
il tetto "al piu' una lettura ogni 10 s" non si apriva mai (referti del 29/09:
150 letture REST nei primi scenari, 0 negli altri).

Qui si riproduce il riuso con due "partite" identiche nello stesso processo,
sul ciclo VERO (``run_once`` via ``run`` di ``test_mike_service``), con
``azzera_cache_di_processo`` in mezzo come fa il banco (NON ``svuota_le_cache``,
che la conftest usa e che nasconderebbe il difetto).

Finti: ``FakeDB``/``FakeMarket`` di ``test_mike_service``, righe del feed di
``test_mike_feed``, blocco ``flusso`` e book REST come in
``test_mike_flusso_cantiere_j2_2026_09_28`` (chiavi vere). ASCII-only.
"""
from __future__ import annotations

from datetime import timedelta

from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_feed import payload, row
from Betfair.mike.tests.test_mike_flusso_cantiere_j2_2026_09_28 import (
    _con_flusso, _rest_vivo, _scanner_nuovo)
from Betfair.mike.tests.test_mike_service import NOW, FakeDB, FakeMarket, legs, run


def _una_partita():
    """Posizione aperta coi prezzi vivi, poi le linee si fermano: il servizio
    legge il ripiego REST (una lettura per mercato). Torna il mercato finto."""
    db = FakeDB(params={"stake": 10})
    _scanner_nuovo(db)
    mk = FakeMarket()
    run(db, mk, NOW, [row(_con_flusso(payload(), []))])
    assert legs(db)[0]["status"] == "open", "precondizione: ingresso abbinato"
    _rest_vivo(mk)
    dopo = NOW + timedelta(seconds=2)
    _scanner_nuovo(db, calcolato=dopo)
    run(db, mk, dopo, [row(_con_flusso(payload(), ["1.35", "1.45"], dopo), updated=dopo)])
    return db, mk


def test_due_partite_nello_stesso_processo_leggono_lo_stesso_ripiego_rest():
    db1, mk1 = _una_partita()
    assert "1.35" in mk1.calls, "precondizione: la prima partita legge il REST"
    S.azzera_cache_di_processo()          # come il banco fra uno scenario e l'altro
    db2, mk2 = _una_partita()
    assert mk2.calls.count("1.35") == mk1.calls.count("1.35"), (
        f"seconda partita: letture REST {mk2.calls} contro {mk1.calls} della prima "
        "(tetto del ripiego ereditato dal replay precedente)")
    rip1 = [p for k, p, _e in db1.activity if k == "ripiego_rest"]
    rip2 = [p for k, p, _e in db2.activity if k == "ripiego_rest"]
    assert rip1 and len(rip2) == len(rip1), (rip1, rip2)


def test_l_azzeramento_nomina_le_quattro_memorie_e_le_svuota():
    S._RIPIEGO_REST_ULTIMO["1.35"] = 999.0
    S._ULTIMO_STATO_SCANNER["v"] = {"flusso": {}}
    assert S._FLUSSO_CRITICO.dovuto("E1", 1000.0)
    assert S._FLUSSO_RIPIEGO.dovuto("E1", 1000.0)
    azzerati = S.azzera_cache_di_processo()
    for nome in ("_RIPIEGO_REST_ULTIMO", "_ULTIMO_STATO_SCANNER",
                 "_FLUSSO_CRITICO", "_FLUSSO_RIPIEGO"):
        assert nome in azzerati, nome
    assert S._RIPIEGO_REST_ULTIMO == {} and S._scanner_stato() is None
    # un'ora PRIMA di quella memorizzata (secondo replay che riparte da capo)
    assert S._FLUSSO_CRITICO.dovuto("E1", 10.0)
    assert S._FLUSSO_RIPIEGO.dovuto("E1", 10.0)
