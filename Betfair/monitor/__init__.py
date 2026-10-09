"""Betfair.monitor - il modulo "Salute" (tappa T0A della migrazione, 09/10/2026).

Contatori in memoria, una riga ogni 30 s per servizio in ``monitor_metrics``,
referto giornaliero in ``AUDIT_MONITOR/``. Interruttore ``MONITOR_SALUTE=0|1``,
di serie 0. Vedi ``COSA_FA.md``.

Gli agganci importano il modulo ``sonde`` (mai i suoi nomi) e controllano
``_mon.ATTIVO`` prima di chiamare qualunque cosa::

    from Betfair.monitor import sonde as _mon
    if _mon.ATTIVO:
        _mon.tratto("diario_fsync_ms", ms)

Questo pacchetto non importa ne' flumine ne' betfairlightweight ne' il client
del DB al caricamento: importarlo non cambia nulla nel processo.
"""
