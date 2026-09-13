"""IL COLLAUDO NON DEVE CHIAMARE IL DATABASE DI PRODUZIONE (13/09/2026).

Il 13/09 undici test di questa cartella sono falliti tutti insieme, e per ore
abbiamo creduto — in due sessioni indipendenti — che fossero rossi pre-esistenti
su master, poi che fossero fantasmi di bytecode stantio. Erano sbagliate
entrambe le spiegazioni comode.

La causa vera: ``runner._lifecycle_blockers`` importa ``db_client`` e interroga
DAVVERO ``betfair_live_risk_rules`` su Supabase. Se quella chiamata solleva,
la funzione risponde «regole di rischio non verificabili (prudenza: resto
acceso)» e lo spegnimento viene rinviato — comportamento GIUSTO in produzione,
dove il denaro viene prima del comfort, ma che in un test trasforma la salute
del database in un verdetto sul codice. Alle 21:37 il database era a 503
(budget di IO su disco esaurito) e quei test sono diventati rossi.

Dimostrato a comando, con i ``__pycache__`` svuotati in entrambi i casi:

    database raggiungibile              ->  47 passati,  0 falliti
    SUPABASE_URL=https://127.0.0.1:9    ->  36 passati, 11 falliti

e gli undici nomi coincidono esattamente con quelli della prima misura.

Da qui due regole, che questa fixture fa rispettare:

  1. **Nessuna chiamata di rete implicita**, ma SOLO per i moduli che quel
     percorso lo attraversano senza volerlo misurare (``_MODULI_DA_ISOLARE``
     qui sotto). Chi le regole di rischio le prova DAVVERO —
     ``test_review_finale_2026_07_17``, ``test_net_retry``,
     ``test_risk_engine_worker``, ``test_reconcile_worker`` — resta fuori e
     continua a girare sul codice vero: un primo tentativo piu' largo di questo
     li aveva fatti cadere tutti e tre, ed e' il modo giusto di scoprire che si
     stava spegnendo troppo.

  2. **Nessuno stato di modulo che si trascina.** ``_RISK_RULES_BLOCKED_UNTIL``
     e' una variabile globale con una validita' di 15 secondi: un test che la
     sporca puo' far fallire quello dopo, e i due nemmeno si conoscono. E' il
     modo piu' rapido per avere un rosso intermittente che nessuno riesce a
     riprodurre.

E la lezione che ci e' costata la serata, scritta qui perche' non si ripeta:
**una misura che non si riesce a riprodurre a comando non e' una misura.**
Prima di dire «pre-esistente» o «era la cache», si costruisce l'esperimento che
accende e spegne il fenomeno.
"""
from __future__ import annotations

import pytest

from Betfair.stream import runner as _runner

# I moduli che misurano il CICLO DI VITA del runner (si spegne? si riavvia?) e
# che quindi attraversano ``_lifecycle_blockers`` senza volerlo mettere alla
# prova. Sono esattamente gli undici test che il 13/09 sono caduti col database
# a 503.
#
# La lista e' ESPLICITA e non un carattere jolly, di proposito: chi scrive un
# test nuovo che tocca le regole di rischio deve DECIDERE da che parte sta,
# invece di ereditare in silenzio una finzione. E i moduli che quel percorso lo
# provano davvero — ``test_review_finale_2026_07_17`` per la cache del verdetto,
# ``test_net_retry`` per il client per thread, ``test_risk_engine_worker`` e
# ``test_reconcile_worker`` che si costruiscono il loro database finto — restano
# FUORI e continuano a girare sul codice vero.
_MODULI_DA_ISOLARE = frozenset({
    "test_runner_lifecycle",
    "test_sub_worker_flat_guard_2026_07_17",
    "test_stream_heartbeat_stall_2026_07_17",
    "test_raw_recmeta_stall",
})


@pytest.fixture(autouse=True)
def _niente_database_nel_collaudo(request: pytest.FixtureRequest,
                                  monkeypatch: pytest.MonkeyPatch):
    """Azzera lo stato di modulo per TUTTI, toglie la rete solo a chi serve."""
    # Questo vale sempre: ``_RISK_RULES_BLOCKED_UNTIL`` e' una globale con una
    # validita' di 15 secondi, e un test che la sporca puo' far cadere quello
    # dopo senza che i due si conoscano.
    monkeypatch.setattr(_runner, "_RISK_RULES_BLOCKED_UNTIL", 0.0, raising=False)

    if request.module.__name__.rsplit(".", 1)[-1] not in _MODULI_DA_ISOLARE:
        yield
        return

    reale = _runner._lifecycle_blockers

    def _blocchi_senza_rete(flumine, fresh: bool = False):
        """Gli stessi blocchi di ``_lifecycle_blockers``, meno la lettura remota.

        Il giro sul blotter — l'unica cosa che questi test misurano davvero, cioe'
        "ci sono ancora ordini vivi?" — resta identico al codice di produzione.
        Cade solo la domanda a Supabase sulle regole di rischio, che qui vale
        sempre "nessuna regola armata": e' lo stato normale di un conto senza
        protezioni attive, ed e' il presupposto di questi scenari.
        """
        try:
            for market in flumine.markets:
                blotter = getattr(market, "blotter", None)
                vivi = list(getattr(blotter, "live_orders", None) or []) if blotter is not None else []
                if vivi:
                    return f"{len(vivi)} ordini vivi sul mercato {getattr(market, 'market_id', '?')}"
        except Exception:  # noqa: BLE001 — stessa prudenza del codice vero
            return "blotter non leggibile (prudenza: resto acceso)"
        return None

    monkeypatch.setattr(_runner, "_lifecycle_blockers", _blocchi_senza_rete)
    yield
