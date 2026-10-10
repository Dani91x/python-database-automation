"""Registro delle tabelle del cloud (comparto G, tappa T2, consegna R23 della revisione critica).

Scopo
    UNA voce (``SpecTabella`` del contratto, avvolta in ``VoceRegistro``) per OGNI tabella del
    cloud che oggi riceve righe dal codice dell'app, dagli script del repository o dalle RPC
    che il codice chiama: le 89 tabelle di ``00_INVENTARIO.md`` par. 0, le 6 scritte solo da
    RPC (``g_copertura_tabelle.TABELLE_DA_RPC``) e quelle che la scansione del 09/10 ha
    trovato in piu' (nomi dinamici, REST diretto, RPC che delegano, la tabella nuova del
    monitor, le due tabelle del pg_cron lette dagli algoritmi). Ordine dell'utente: il
    database cloud NON perde nessun dato rispetto a oggi; il registro e' lo strumento che lo
    garantisce: ogni tabella e' registrata con chi la scrive OGGI e chi la scrivera' DOMANI.

Entrate
    Nessuna a runtime: e' un modulo DICHIARATIVO (dati + funzioni pure). I ``file:riga`` degli
    scrittori di oggi vengono dalla scansione del codice al commit ``COMMIT_SCANSIONE``
    (``.table(...)`` con insert/upsert/update/delete, ``.rpc(...)``, nomi dinamici risolti a
    mano, REST diretto), Python E frontend; le chiavi naturali, ``rev_colonna`` e
    ``dipende_da`` vengono dalle migrazioni (``migrations/*.sql``, citate per riga nelle note).

Uscite
    ``REGISTRO`` (``RegistroTabelle``): ``spec(tabella)``, ``voce(tabella)``, ``tabelle()``,
    ``rpc_scriventi()``; ``verifica_copertura(registro, scansione)`` confronta il registro con
    una ``Scansione`` del codice e restituisce errori (bloccanti) e avvisi (segnalati).

Cosa NON fa
    Non apre file, non parla col cloud, non scansiona il codice (lo fa il test
    ``tests/test_g2_registro.py`` con lo strumento dell'inventario); non decide i ritardi:
    regime e ritardo massimo sono quelli di ``G_DATI_E_ALGORITMI_DEL_CLOUD.md`` par. 4.3,
    dichiarati "proposta, da approvare con U-86" (``STATO_RITARDI``); non cambia nessuna
    scrittura di oggi (l'aggancio e' l'ondata 2).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Dict, FrozenSet, Iterable, List, Literal, Mapping, Optional, Tuple

from .contratto import Natura, Regime, SpecTabella

#: commit su cui e' stata fatta la scansione che ha prodotto i ``file:riga`` qui sotto
COMMIT_SCANSIONE = "559a96df"
#: i ritardi massimi e i regimi sono quelli di G par. 4.3: proposta, non decisione
STATO_RITARDI = "proposta, da approvare con U-86"
#: ritardo per le tabelle che NON passano dal postino (scritte direttamente nel cloud
#: dai raccoglitori, dalle RPC della UI o dal pg_cron): non applicabile
NON_APPLICABILE = math.inf

#: ritardi di G par. 4.3 (secondi)
R_CFG = 1.0          # comandi e configurazione UI -> bot (CACHE + sveglia)
R_LADDER = 2.0       # = LADDER_PUBLISH_SEC (config_stream.py:60)
R_SCALPER = 3.0      # = POLL_S dello scalper (scalper_service.py:43)
R_STATO = 5.0        # stato del denaro e stato vivo verso il cloud
R_COALESCENTE = 15.0 # heartbeat e account
R_LOG = 60.0         # log append-only

Proposta = Literal["CMD-L", "L+P", "CACHE", "CLOUD", "BATCH"]
Origine = Literal["inventario_89", "solo_rpc", "nome_dinamico", "rest", "mondo_sql", "nuova"]

#: RPC che NON scrivono e che non hanno il prefisso get_/list_ (oltre a quelle dello
#: strumento ``g_copertura_tabelle.RPC_SOLA_LETTURA``): motivo verificato sulla definizione
RPC_SOLA_LETTURA_DICHIARATE: Mapping[str, str] = {
    "monitor_salute_stato": "migrations/monitor_metrics_2026-10-09.sql:73, solo SELECT (T0A)",
    "monitor_vitalita_raccoglitori": "migrations/monitor_metrics_2026-10-09.sql:127, solo SELECT (T0A)",
    "omega_eventi_chiusi_dall_utente": "migrations/omega_chiuso_dall_utente_2026-09-16.sql:104, solo SELECT",
    # integrazione W1-G1 (09/10): le due RPC di lettura del postino. Definizioni lette: STABLE, un solo
    # EXECUTE di un SELECT (jsonb_agg sulle righe della tabella, o conteggi vera/ombra), nessun DML
    "postino_impronte": "migrations/architettura_uid_ombra_2026-10-09.sql:427, STABLE, solo SELECT "
                        "(coppie [chiave, versione] per la riconciliazione notturna, riconcilia.py:142)",
    "postino_confronta_ombra": "migrations/architettura_uid_ombra_2026-10-09.sql:491, STABLE, solo SELECT "
                               "(conteggi per giorno vera contro ombra, criterio di T8, riconcilia.py:160)",
    # decisione 10 dell'utente (10/10): la sentinella leggera dei dati calcolati dal cloud. Definizione letta:
    # plpgsql STABLE, solo SELECT (tre letture della sentinella di Omega, ponte e versione del dossier per
    # evento), nessun DML, tetto 500 eventi; chiamata da cache_cloud.SentinellaCloud ogni 5 s
    "nucleo_sentinella_cloud": "migrations/nucleo_sentinella_cloud_2026-10-10.sql:114, STABLE, solo SELECT "
                               "(impronte per giro della Sorveglianza, cache_cloud.py)",
}

#: nomi che il controllo DML delle migrazioni trova dopo INSERT/UPDATE/DELETE/TRUNCATE e che NON
#: sono tabelle del cloud che ricevono righe: ogni eccezione ha il suo motivo
ECCEZIONI_DML: Mapping[str, str] = {
    "set": "parola SQL: 'ON CONFLICT ... DO UPDATE SET' (non una tabella)",
    "nowait": "parola SQL: 'FOR UPDATE NOWAIT' (omega_models_v4.sql, omega_build_minute_transitions_step)",
    "pg_temp": "tabelle temporanee di sessione pg_temp.* (spariscono a fine transazione)",
    "tmp_fx": "tabella temporanea della costruzione una tantum (omega_models_v3.sql, CREATE TEMP TABLE)",
    "prima": "parola di un commento dentro upsert_imported_trade (personal_tracking_import.sql)",
    "senza": "parola di un commento dentro reset_personal_report (personal_tracking_rpc.sql)",
    "sicurezza_bk": "schema PRIVATO di fotografia dei permessi (sicurezza_db_2026-09-24_BLOCCO_*): "
                    "una tantum per il rollback, fuori da public",
    "public": "nome dello SCHEMA, non una tabella: falso positivo degli EXECUTE dinamici "
              "format('INSERT INTO public.%I ...', p_tabella) di postino_consegna e "
              "format('CREATE TABLE ... public.%I', ...) di _postino_crea_ombra "
              "(architettura_uid_ombra_2026-10-09.sql:113,377-392): le tabelle vere raggiunte sono quelle "
              "del registro passate in p_tabella (e le loro <tabella>_ombra), vedi RPC postino_consegna",
}

#: bucket dello Storage di Supabase scritti o letti dal codice (non sono tabelle: file dei modelli)
BUCKET_MODELLI = "ai-models-league-<league_id>"


@dataclass(frozen=True)
class VoceRegistro:
    """Una tabella del cloud: la ``SpecTabella`` del contratto piu' cio' che serve a
    dimostrare che non manca nulla (estensione additiva, proposta nel referto)."""

    spec: SpecTabella
    famiglia: str                       # T01..T17 di G par. 1.3, o "EXTRA"
    proposta: Proposta                  # CMD-L / L+P / CACHE / CLOUD / BATCH (G par. 4.3)
    origine: Origine                    # da dove viene la voce (inventario, RPC, scansione)
    rpc_scriventi: Tuple[str, ...]      # RPC che oggi la scrivono (definizione SQL)
    scrittura_fuori_codice: Optional[str]  # chi la scrive fuori dal codice scansionato
    verifica: str                       # come si verifica che non manca nulla
    note: str = ""
    schema_nel_repo: bool = True        # False: CREATE TABLE fuori dal repo, chiave NON verificabile


@dataclass(frozen=True)
class RpcScrivente:
    """Una RPC che scrive: le tabelle toccate dalla sua definizione (chiusa sulle funzioni
    che chiama) e l'ultima definizione nelle migrazioni."""

    nome: str
    tabelle: Tuple[str, ...]
    definizione: str
    nota: str = ""


@dataclass(frozen=True)
class SitoDinamico:
    """Una chiamata ``.table(<variabile>)`` (o ``.rpc(<variabile>)``) che la scansione non
    sa risolvere: le tabelle che raggiunge, provate leggendo il codice (``prova``)."""

    file: str
    nome: str                           # come lo scrive la scansione: "<dinamico:table>"
    righe: Tuple[int, ...]
    tabelle: Tuple[str, ...]            # () = sito passante o di sola lettura
    prova: str


@dataclass(frozen=True)
class Scansione:
    """Il codice di oggi visto dalla scansione (prodotta dal test, mai da questo modulo).

    ``scritture``: tabella letterale -> {"file:riga"} con insert/upsert/update/delete;
    ``dinamici``: (file, nome) -> righe dei siti di scrittura con nome non letterale;
    ``indeterminati``: (file, nome) -> righe con operazione non determinata (builder passato);
    ``rpc``: RPC letterale -> {"file:riga"} dei chiamanti; ``rpc_dinamiche``: (file, nome) ->
    righe; ``rest``: (file, tabella) -> righe di POST/PATCH/DELETE REST diretti;
    ``dml_rpc``: RPC -> tabelle toccate dalla sua definizione SQL (chiusa sulle chiamate);
    ``rpc_definite``: RPC con almeno una definizione nelle migrazioni. Comprende anche i
    workflow ``.github/**/*.yml`` (REST ``/rest/v1/rpc/<nome>`` e ``/rest/v1/<tabella>``)."""

    scritture: Mapping[str, FrozenSet[str]]
    dinamici: Mapping[Tuple[str, str], FrozenSet[int]]
    indeterminati: Mapping[Tuple[str, str], FrozenSet[int]]
    rpc: Mapping[str, FrozenSet[str]]
    rpc_dinamiche: Mapping[Tuple[str, str], FrozenSet[int]]
    rest: Mapping[Tuple[str, str], FrozenSet[int]]
    dml_rpc: Mapping[str, FrozenSet[str]]
    rpc_definite: FrozenSet[str]
    #: tabella -> {"file:funzione"|"file:cron"}: INSERT/UPDATE/DELETE/TRUNCATE dentro OGNI funzione
    #: delle migrazioni e dentro i ``cron.schedule`` (anche quelle che nessun codice chiama)
    dml_migrazioni: Mapping[str, FrozenSet[str]] = field(default_factory=dict)
    #: (file, espressione del bucket) -> righe delle chiamate ``.storage.from_(...)``
    storage: Mapping[Tuple[str, str], FrozenSet[int]] = field(default_factory=dict)


@dataclass(frozen=True)
class EsitoCopertura:
    """``errori``: il registro non copre il codice (test rosso). ``avvisi``: segnalazioni
    (righe spostate, scrittori spariti, voci senza scrittori dichiarate)."""

    errori: Tuple[str, ...]
    avvisi: Tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errori


# ---------------------------------------------------------------------------
# 1. Scrittori di oggi nel codice (scansione al commit COMMIT_SCANSIONE)
# ---------------------------------------------------------------------------
# Generato dalla scansione (strumento ``s03_db.analizza_py/analizza_ts`` dell'inventario,
# file di produzione Python e frontend): tabella -> ``file:riga`` delle chiamate
# ``.table("<tabella>")`` con insert/upsert/update/delete. Le righe si spostano quando il
# codice cambia: il test lo segnala come AVVISO; un FILE nuovo che scrive una tabella e'
# invece un ERRORE (lo scrittore va registrato).
_SCRITTURE_DIRETTE: Dict[str, Tuple[str, ...]] = {
    "ai_model_registry": ("Ai Engine/ai_engine/seriea_model_export.py:686",
        "Ai Engine/ai_engine/seriea_model_export.py:689", "Betfair/betfair_report_manager.py:1299",
        "cleanup_models.py:31", "reset_ai_models.py:31"),
    "analytics_signals": ("build_analytics_signals.py:402", "fix_storico_prob.py:59"),
    "analytics_snap_staging": ("enrich_analytics_snapshots.py:293", "enrich_analytics_snapshots.py:336"),
    "api_call_log": ("logger.py:86", "logger.py:91"),
    "api_coverage_by_season": ("leagues_mapper.py:325", "leagues_mapper.py:350"),
    "betfair_live_account": ("Betfair/stream/db.py:1004", "Betfair/stream/db.py:1055", "Betfair/stream/db.py:1086"),
    "betfair_live_audit": ("Betfair/stream/daily_stop_worker.py:391", "Betfair/stream/live_order_worker.py:922"),
    "betfair_live_heartbeat": ("Betfair/stream/db.py:1127",),
    "betfair_live_journal": ("Betfair/stream/db.py:988", "Betfair/stream/live_order_worker.py:1134"),
    "betfair_live_order_requests": ("Betfair/mike/db.py:694", "Betfair/omega/omega_db.py:684",
        "Betfair/safe_strategy/bot_db.py:1039", "Betfair/stream/db.py:1165", "Betfair/stream/db.py:1177",
        "Betfair/stream/live_order_worker.py:907", "Betfair/stream/live_order_worker.py:1169",
        "Betfair/stream/live_order_worker.py:1195", "Betfair/stream/live_order_worker.py:1208",
        "Betfair/stream/live_order_worker.py:2080", "Betfair/stream/live_order_worker.py:3603",
        "Betfair/stream/live_order_worker.py:3790"),
    "betfair_live_orders": ("Betfair/stream/db.py:819", "Betfair/stream/db.py:828", "Betfair/stream/db.py:1139",
        "Betfair/stream/reconcile_worker.py:380", "Betfair/stream/reconcile_worker.py:422"),
    "betfair_live_positions": ("Betfair/stream/db.py:940", "Betfair/stream/db.py:945", "Betfair/stream/db.py:1140"),
    "betfair_live_risk_rules": ("Betfair/stream/risk_engine_worker.py:189",),
    "betfair_live_risk_state": ("Betfair/stream/db.py:978",),
    "betfair_live_settled": ("Betfair/stream/db.py:963",),
    "betfair_live_xhedge": ("Betfair/stream/xhedge_worker.py:119",),
    "betfair_market_odds": ("Betfair/odds_refresh.py:254", "Betfair/odds_refresh.py:257", "betfair_full_odds.py:73",
        "betfair_full_odds.py:94"),
    "betfair_order_requests": ("Betfair/order_worker.py:48", "Betfair/order_worker.py:99",
        "Betfair/order_worker.py:106", "Betfair/order_worker.py:113", "Betfair/order_worker.py:120"),
    "betfair_refresh_requests": ("Betfair/refresh_worker.py:59", "Betfair/refresh_worker.py:66",
        "Betfair/refresh_worker.py:73"),
    "direction_pagella": ("build_direzione.py:226", "build_direzione.py:230"),
    "engine_signals": ("migrations/backfill_engine_signals.py:278",),
    "fixture_predictions": ("AGGIORNA_CAMPO_db_json_analisi.py:178", "Ai Engine/ai_engine/predict_fixture.py:1087",
        "Prediction/backfill_historical_analysis.py:120", "Prediction/predictions_results_backfill.py:504",
        "Prediction/today_predictions_backfill.py:416", "Prediction/today_predictions_backfill.py:909",
        "Prediction/today_predictions_backfill.py:971", "Prediction/today_predictions_backfill.py:1898",
        "Prediction/today_predictions_backfill.py:2173", "Prediction/today_predictions_backfill.py:2187",
        "Prediction/today_predictions_backfill.py:2219", "Prediction/today_predictions_backfill.py:2238",
        "Prediction/today_predictions_backfill.py:2285", "Prediction/today_predictions_backfill.py:2344",
        "Prediction/today_predictions_backfill.py:2364", "backfill_poisson_calibrated.py:132",
        "tactical_engine/generate_predictions.py:179", "tactical_engine/generate_predictions.py:187",
        "tactical_engine/serving.py:263", "tactical_engine/serving.py:358"),
    "injuries": ("injuries_backfill.py:209", "injuries_backfill.py:259"),
    "leads": ("frontend/src/components/landing/AuthSection.tsx:74",),
    "live_alerts": ("Betfair/stream/db.py:697", "Betfair/stream/live_order_worker.py:1071",
        "Betfair/stream/motore_ordini.py:2583", "Betfair/stream/scalper/scalper_service.py:671",
        "Betfair/stream/scalper/scalper_session.py:714", "Betfair/stream/scalper/scalper_session.py:999",
        "Betfair/stream/scalper/scalper_session.py:1215", "Betfair/stream/scalper/scalper_session.py:1839",
        "Betfair/stream/scalper/scalper_session.py:2222"),
    "live_backtest_requests": ("Betfair/stream/db.py:726", "Betfair/stream/db.py:741"),
    "live_backtest_results": ("Betfair/stream/db.py:758", "Betfair/stream/db.py:762"),
    "live_follow": ("Betfair/stream/auto_follow.py:402", "Betfair/stream/auto_follow.py:426",
        "Betfair/stream/auto_follow.py:429", "Betfair/stream/auto_follow.py:442", "Betfair/stream/db.py:164",
        "Betfair/stream/db.py:170", "Betfair/stream/db.py:197", "Betfair/stream/scalper/scalper_service.py:184"),
    "live_ladder": ("Betfair/stream/db.py:682",),
    "live_markets": ("Betfair/stream/db.py:314",),
    "live_now": ("Betfair/stream/db.py:348", "Betfair/stream/db.py:362", "Betfair/stream/db.py:528"),
    "live_run_log": ("Betfair/stream/db.py:644",),
    "live_signals": ("Betfair/stream/db.py:662",),
    "match_odds": ("football_data_scraper/fix_snapshot_time.py:45",),
    "matches": ("daily_yesterday_backfill.py:75", "fixtures_backfill.py:135"),
    "mike_activity": ("Betfair/mike/db.py:76",),
    "mike_control": ("Betfair/mike/db.py:68",),
    "mike_events": ("Betfair/mike/db.py:141", "Betfair/mike/db.py:164", "Betfair/mike/db.py:169"),
    "mike_requests": ("Betfair/mike/db.py:520", "Betfair/mike/db.py:527"),
    "mike_trades": ("Betfair/mike/db.py:176", "Betfair/mike/db.py:186"),
    "ml_post_calibration": ("compute_ml_post_calibration.py:244", "compute_ml_post_calibration.py:259"),
    "model_performance": ("retrain_all_leagues.py:363",),
    "monitor_metrics": ("Betfair/monitor/scrittore.py:93",),
    "omega_activity": ("Betfair/omega/omega_db.py:63",),
    "omega_control": ("Betfair/omega/omega_db.py:58",),
    "omega_daily_goal": ("Betfair/omega/omega_db.py:1055",),
    "omega_events": ("Betfair/omega/omega_db.py:303", "Betfair/omega/omega_db.py:442",
        "Betfair/omega/omega_db.py:446", "Betfair/omega/omega_db.py:450", "Betfair/omega/omega_db.py:476",
        "Betfair/omega/omega_db.py:545", "Betfair/omega/omega_db.py:1027"),
    "omega_manual_requests": ("Betfair/omega/omega_db.py:297", "Betfair/omega/omega_db.py:323",
        "Betfair/omega/omega_db.py:394", "Betfair/omega/omega_db.py:402", "Betfair/omega/omega_db.py:421"),
    "omega_market_snapshot": ("Betfair/omega/omega_db.py:482",),
    "omega_missions": ("Betfair/omega/omega_db.py:727",),
    "omega_trades": ("Betfair/omega/omega_db.py:76", "Betfair/omega/omega_db.py:86", "Betfair/omega/omega_db.py:94"),
    "personal_trades": ("_certify_personal_report.py:325",),
    "poisson_calibration": ("generate_dynamic_cal.py:459", "load_poisson_calibration_to_db.py:65"),
    "replay_bot_esiti": ("Betfair/stream/db.py:752",),
    "safe_strategy_activity": ("Betfair/safe_strategy/bot_db.py:89",),
    "safe_strategy_control": ("Betfair/safe_strategy/bot_db.py:84",),
    "safe_strategy_opportunities": ("Betfair/safe_strategy/bot_db.py:889", "Betfair/safe_strategy/bot_db.py:901",
        "Betfair/safe_strategy/bot_db.py:913"),
    "safe_strategy_requests": ("Betfair/safe_strategy/bot_db.py:661", "Betfair/safe_strategy/bot_db.py:669",
        "Betfair/safe_strategy/bot_db.py:688", "Betfair/safe_strategy/bot_db.py:718",
        "Betfair/safe_strategy/bot_db.py:770", "Betfair/safe_strategy/bot_db.py:778",
        "Betfair/safe_strategy/bot_db.py:795", "Betfair/safe_strategy/bot_db.py:819",
        "Betfair/safe_strategy/bot_db.py:839", "Betfair/safe_strategy/bot_db.py:857",
        "Betfair/safe_strategy/bot_db.py:865", "Betfair/safe_strategy/bot_db.py:874"),
    "safe_strategy_scan": ("Betfair/safe_strategy/db.py:198", "Betfair/safe_strategy/db.py:213"),
    "safe_strategy_status": ("Betfair/safe_strategy/db.py:228",),
    "safe_strategy_trades": ("Betfair/safe_strategy/bot_db.py:102", "Betfair/safe_strategy/bot_db.py:112",
        "Betfair/safe_strategy/bot_db.py:120"),
    "scalper_activity": ("Betfair/stream/scalper/scalper_service.py:86",
        "Betfair/stream/scalper/scalper_service.py:893", "Betfair/stream/scalper/scalper_session.py:1410",
        "Betfair/stream/scalper/scalper_session.py:1421"),
    "scalper_control": ("Betfair/stream/scalper/scalper_service.py:81",
        "Betfair/stream/scalper/scalper_service.py:195", "Betfair/stream/scalper/scalper_service.py:197",
        "Betfair/stream/scalper/scalper_service.py:208", "Betfair/stream/scalper/scalper_session.py:1360"),
    "scalper_service_control": ("Betfair/stream/scalper/scalper_service.py:102",),
    "season_backfill_state": ("season_gaps.py:571", "season_gaps.py:580", "season_gaps.py:615", "season_gaps.py:665",
        "seasons_catchup.py:460"),
    "signal_history": ("Betfair/money_management.py:2434", "Betfair/money_management.py:2471"),
    "standings": ("standings_backfill.py:239", "standings_backfill.py:289"),
    "tennis_bot_activity": ("Betfair/stream/tennis_live/tennis_db.py:521",),
    "tennis_bot_control": ("Betfair/stream/tennis_live/tennis_db.py:217",
        "Betfair/stream/tennis_live/tennis_db.py:447", "Betfair/stream/tennis_live/tennis_db.py:454",
        "Betfair/stream/tennis_live/tennis_db.py:471", "Betfair/stream/tennis_live/tennis_db.py:504",
        "Betfair/stream/tennis_live/tennis_db.py:506", "Betfair/stream/tennis_live/tennis_db.py:511",
        "Betfair/stream/tennis_live/tennis_db.py:767", "Betfair/stream/tennis_live/tennis_db.py:780"),
    "tennis_bot_service_control": ("Betfair/stream/tennis_live/tennis_db.py:713",),
    "tennis_live_follow": ("Betfair/stream/tennis_live/tennis_db.py:121",
        "Betfair/stream/tennis_live/tennis_db.py:234"),
    "tennis_live_ladder": ("Betfair/stream/tennis_live/tennis_db.py:263",),
    "tennis_live_now": ("Betfair/stream/tennis_live/tennis_db.py:295", "Betfair/stream/tennis_live/tennis_db.py:309",
        "Betfair/stream/tennis_live/tennis_db.py:316", "Betfair/stream/tennis_live/tennis_db.py:387"),
    "tennis_live_order_queue": ("Betfair/stream/tennis_live/esecutore_tennis.py:266",
        "Betfair/stream/tennis_live/tennis_db.py:552", "Betfair/stream/tennis_live/tennis_db.py:571",
        "Betfair/stream/tennis_live/tennis_db.py:583", "Betfair/stream/tennis_live/tennis_db.py:821",
        "Betfair/stream/tennis_live/tennis_db.py:834", "Betfair/stream/tennis_live/tennis_live_order_worker.py:1830"),
    "tennis_live_orders": ("Betfair/stream/tennis_live/tennis_db.py:607",
        "Betfair/stream/tennis_live/tennis_db.py:857"),
    "tennis_live_positions": ("Betfair/stream/tennis_live/tennis_db.py:630",
        "Betfair/stream/tennis_live/tennis_db.py:866"),
    "tennis_markets": ("betfair_tennis_odds.py:274", "betfair_tennis_odds.py:278"),
    "tennis_replay_eventi": ("Betfair/stream/tennis_replay/caricamento.py:131",
        "Betfair/stream/tennis_replay/caricamento.py:151", "Betfair/stream/tennis_replay/caricamento.py:184"),
    "tennis_replay_mercati": ("Betfair/stream/tennis_replay/caricamento.py:125",
        "Betfair/stream/tennis_replay/caricamento.py:156"),
    "theta_confirm_requests": ("Betfair/stream/scalper/scalper_session.py:2083",
        "Betfair/stream/scalper/scalper_session.py:2105"),
    "top_assists": ("top_assists_backfill.py:235", "top_assists_backfill.py:285"),
    "top_cards": ("top_cards_backfill.py:244", "top_cards_backfill.py:294"),
    "top_scorers": ("top_scorers_backfill.py:235", "top_scorers_backfill.py:285"),
}


# ---------------------------------------------------------------------------
# 2. Nomi dinamici, siti passanti, REST diretto (risolti leggendo il codice)
# ---------------------------------------------------------------------------
SITI_DINAMICI: Tuple[SitoDinamico, ...] = (
    SitoDinamico("Betfair/stream/db.py", "<dinamico:table>", (572, 596),
                 ("live_market_snapshots", "live_score_timeline", "tennis_replay_punteggio",
                  "tennis_replay_snapshots"),
                 "delete_event_rows/insert_rows_resilient: Betfair/stream/db.py:629-635 (snapshot e "
                 "timeline del calcio), Betfair/stream/tennis_replay/caricamento.py:33-36,163-170"),
    SitoDinamico("Betfair/stream/db.py", "<dinamico:tabella>", (1114,),
                 ("betfair_live_orders", "mike_trades", "omega_trades", "safe_strategy_trades",
                  "tennis_live_orders"),
                 "update_pnl_betfair ammette solo TABELLE_PNL_BETFAIR (Betfair/stream/db.py:1093-1096); "
                 "chiamante reconcile_worker.py:1101"),
    SitoDinamico("football_data_scraper/backfill.py", "<dinamico:table>", (342,),
                 ("match_odds", "match_team_stats"), "_insert_rows: chiamanti :460-461"),
    SitoDinamico("merge_engine_signals.py", "<dinamico:table>", (215,),
                 ("analytics_decisions", "analytics_signals"), "_upsert: chiamanti :259-260"),
    SitoDinamico("per_fixture_backfill.py", "<dinamico:t>", (219,),
                 ("match_events", "match_lineups", "match_player_stats", "match_team_stats"),
                 "elenco delle tabelle per fixture :209-213"),
    SitoDinamico("per_fixture_backfill.py", "<dinamico:table>", (264, 943),
                 ("match_events", "match_lineups", "match_odds", "match_player_stats", "match_team_stats"),
                 "insert_rows/_sostituisci_righe: mappa :916-920"),
    SitoDinamico("season_aggregates.py", "<dinamico:nome>", (229, 238),
                 ("injuries", "standings", "top_assists", "top_cards", "top_scorers"),
                 "esegui_aggregato: _mappa :192-203"),
)

#: il client generico del nucleo: scrive solo tabelle del registro (``ClienteCloud.scrivi`` rifiuta le
#: altre) e chiama RPC passate dai chiamanti; le tabelle sono le voci stesse del registro
SITI_DINAMICI = SITI_DINAMICI + (
    SitoDinamico("Betfair/nucleo/dati/cloud.py", "<dinamico:tabella>", (256,), (),
                 "ClienteCloud.scrivi: ValueError su tabella non registrata (test_scrittura_solo_su_tabelle_del_registro)"),
)

#: builder restituiti senza operazione (la scansione non vede insert/upsert...): passanti
SITI_PASSANTI: Tuple[SitoDinamico, ...] = (
    SitoDinamico("Betfair/stream/live_order_worker.py", "<dinamico:name>", (3735,), (),
                 "adattatore del comando locale: table(name) inoltra al client vero le tabelle dei "
                 "chiamanti, gia' scansionate per nome (:3725-3738)"),
    SitoDinamico("Betfair/stream/scalper/genera_atlante.py", "<dinamico:rest>", (593, 969), (),
                 "LettoreDB.get (:593, GET) e _Scrittore._req (:969): le scritture sono le chiamate _req "
                 "con metodo e tabella letterali, registrate in SCRITTURE_REST"),
    SitoDinamico("Betfair/stream/scalper/hazard_atlas_sync.py", "<dinamico:rest>", (57,), (),
                 "_get: method='GET' (:57), sola lettura"),
    SitoDinamico("valida_motore_poisson.py", "<dinamico:rest>", (48,), (), "_get: urlopen senza dati = GET"),
    SitoDinamico("ventaglio_segnali.py", "<dinamico:rest>", (59,), (),
                 "_get (:58-61) GET; le RPC passano da _rpc, gia' scansionate per nome"),
    SitoDinamico(".github/workflows/hazard_atlas.yml", "<dinamico:rest>", (108,), (),
                 "leggi(path): GET con ritentativi del passo di controllo (:103-118), nessuna scrittura"),
)

#: ``.rpc(<variabile>)``: nessuna scrive (verificato leggendo il chiamante)
RPC_DINAMICHE: Tuple[SitoDinamico, ...] = (
    SitoDinamico("Betfair/stream/live_order_worker.py", "<dinamico:*a>", (3738,), (),
                 "passante: rpc(*a) inoltra al client vero le RPC dei chiamanti (gia' scansionate)"),
    SitoDinamico("Betfair/nucleo/dati/cloud.py", "<dinamico:nome>", (234,), (),
                 "ClienteCloud.rpc: ritenta solo le RPC di lettura; le scriventi sono nel registro"),
    SitoDinamico("frontend/src/certification/realClient.ts", "<dinamico>", (155,), (),
                 "probeRpc: sonde di forma, sempre in lettura (:150-158)"),
    SitoDinamico("frontend/src/lib/__fixtures__/replayBarraDbFinto.ts", "<dinamico>", (185,), (),
                 "server finto delle prove del replay: inoltra al DB finto"),
    SitoDinamico("frontend/src/lib/chiuseGiornata.ts", "<dinamico>", (146,), (),
                 "RPC_CHIUSE_GIORNATA = get_posizioni_chiuse_giornata (:37), lettura"),
    SitoDinamico("frontend/src/lib/live.ts", "<dinamico>", (386,), (),
                 "fetchReplayFramesWindow: RPC dei frame del replay, lettura"),
)

#: scritture REST dirette (urllib, fuori da supabase-py)
SCRITTURE_REST: Tuple[SitoDinamico, ...] = (
    SitoDinamico("Betfair/stream/scalper/genera_atlante.py", "hazard_atlas_leghe", (1046,),
                 ("hazard_atlas_leghe",), "POST hazard_atlas_leghe?on_conflict=league_id"),
    SitoDinamico("Betfair/stream/scalper/genera_atlante.py", "hazard_atlas", (1114, 1134),
                 ("hazard_atlas",), "POST (ripiego) e DELETE delle versioni vecchie"),
)

#: ``.storage.from_(...)``: file dei modelli ML nei bucket ``ai-models-league-<league_id>``
#: (non tabelle; restano nel cloud, raccoglitori invariati). ``tabelle`` = il bucket, ``prova`` = operazione
SITI_STORAGE: Tuple[SitoDinamico, ...] = (
    SitoDinamico("Ai Engine/ai_engine/seriea_model_export.py", "<dinamico:bucket>", (679,), (BUCKET_MODELLI,),
                 "SCRIVE: upload del modello (upsert) dopo create_bucket (:55-58); riga in ai_model_registry :689"),
    SitoDinamico("cleanup_models.py", "<dinamico:name>", (53, 64), (BUCKET_MODELLI,),
                 "CANCELLA: list + remove di tutti i file (script manuale di pulizia)"),
    SitoDinamico("reset_ai_models.py", "<dinamico:bucket_name>", (63, 80), (BUCKET_MODELLI,),
                 "CANCELLA: list + remove a blocchi di 100 (script manuale)"),
    SitoDinamico("Ai Engine/ai_engine/predict_fixture.py", "<dinamico:bucket>", (83,), (BUCKET_MODELLI,),
                 "legge: download del modello"),
    SitoDinamico("Betfair/betfair_report_manager.py", "<dinamico:bucket>", (1335,), (BUCKET_MODELLI,),
                 "legge: download del modello"),
    # seconda revisione del 09/10: Edge Function di Supabase (Deno, fuori dall'app, pg_cron make-daily-post)
    SitoDinamico("Telegram bot/supabase/functions/make-daily-post/index.ts", "Loghi", (253, 263), ("Loghi",),
                 "SCRIVE: upload del logo con upsert (:253); getPublicUrl (:263); resta nel cloud, invariato"),
)


# ---------------------------------------------------------------------------
# 3. RPC che scrivono (definizione SQL chiusa sulle funzioni chiamate)
# ---------------------------------------------------------------------------
def _r(nome: str, tabelle: Tuple[str, ...], definizione: str, nota: str = "") -> RpcScrivente:
    return RpcScrivente(nome, tuple(sorted(tabelle)), "migrations/" + definizione, nota)


RPC_SCRIVENTI_ELENCO: Tuple[RpcScrivente, ...] = (
    _r("ack_alert", ("live_alerts",), "live_backtest_rpc.sql:169"),
    _r("add_personal_trade", ("personal_trades", "personal_watchlist"), "personal_tracking_rpc.sql:368"),
    _r("add_to_watchlist", ("personal_watchlist",), "personal_tracking_rpc.sql:18"),
    _r("add_trade_leg", ("personal_trade_legs", "personal_trades"), "personal_tracking_rpc.sql:505"),
    _r("bulk_update_prediction_results", ("fixture_predictions",), "predictions_results_bulk_update_rpc.sql:30"),
    _r("cancel_live_risk_rule", ("betfair_live_risk_rules",), "betfair_live_risk_rules.sql:152"),
    _r("delete_from_watchlist", ("personal_watchlist",), "personal_tracking_rpc.sql:890"),
    _r("delete_strategy", ("strategies",), "analytics_strategies_store.sql:60"),
    _r("flush_analytics_prob_staging", ("analytics_prob_staging", "analytics_signals"),
       "analytics_prob_staging.sql:22", "nessun chiamante nel codice di oggi (dormiente)"),
    _r("flush_analytics_snap_staging", ("analytics_signals", "analytics_snap_staging"),
       "analytics_snap_staging.sql:58"),
    _r("hazard_atlas_salva_versione", ("hazard_atlas",), "hazard_atlas_rpc_scrittura_2026-09-28.sql:52",
       "chiamata via REST da genera_atlante.py:1103"),
    _r("live_order_mode_avvio", ("betfair_live_settings",), "live_order_mode_control_2026-09-24.sql:109"),
    _r("mike_activate", ("mike_control",), "mike_bot.sql:183"),
    _r("mike_request", ("mike_requests",), "uscite_automatiche_mike_2026-09-25.sql:42"),
    _r("mike_stop", ("mike_control",), "mike_bot.sql:205"),
    _r("mike_update_params", ("mike_control",), "mike_bot.sql:224"),
    _r("omega_activate", ("omega_control", "omega_daily_goal"), "omega_daily_v2.sql:53"),
    _r("omega_evento_riprendi", ("omega_activity", "omega_events"), "omega_chiuso_dall_utente_2026-09-16.sql:70"),
    _r("omega_mission_activate", ("omega_missions",), "omega_missions.sql:78"),
    _r("omega_mission_follow", ("live_follow",), "omega_missions.sql:176"),
    _r("omega_mission_stop", ("omega_missions",), "omega_missions.sql:143"),
    _r("omega_request", ("omega_manual_requests",), "omega_manual.sql:120"),
    _r("omega_request_approve", ("omega_manual_requests", "omega_requests"),
       "omega_request_approve_contesto_2026-09-25.sql:33"),
    _r("omega_request_ignore", ("omega_manual_requests", "omega_requests"),
       "omega_proposte_uscita_2026-09-16.sql:151"),
    _r("omega_stop", ("omega_control",), "omega_bot.sql:155"),
    _r("omega_update_params", ("omega_control", "omega_daily_goal"), "omega_daily_v2.sql:89"),
    _r("record_fixture_detail_checks", ("fixture_detail_checks",), "season_gaps_2026-09-25.sql:96",
       "NON idempotente (db_client.RPC_NON_IDEMPOTENTI)"),
    _r("refresh_analytics_riepilogo", ("analytics_riepilogo_decisioni", "analytics_riepilogo_meta",
                                       "analytics_riepilogo_segnali"), "analytics_rpc_veloci_2026-09-26.sql:196",
       "chiamata ogni notte via curl da .github/workflows/predictions_results_backfill.yml:200"),
    _r("refresh_analytics_bets_range", ("analytics_bets", "book_odds_cache", "book_odds_cache_fonte"),
       "refresh_analytics_bets_range_v2_2026-09-24.sql:277",
       "delega a refresh_analytics_bets_range_diag (stesso file): book_odds_cache e "
       "book_odds_cache_fonte NON erano nell'elenco delle 6 di g_copertura"),
    _r("postino_consegna", ("postino_versioni",), "architettura_uid_ombra_2026-10-09.sql:245",
       "porta generica del postino (W1-G1): scrive postino_versioni e, con EXECUTE dinamico, la tabella "
       "p_tabella (o <p_tabella>_ombra in ombra): SOLO tabelle del registro, perche' il postino consegna "
       "solo voci di tabelle che l'archivio riconosce e che NON sono solo locali (postino.drena: "
       "TABELLE_SOLO_LOCALI, poi archivio.spec) e il client rifiuta le altre prima della rete "
       "(cloud.RPC_CON_TABELLA); il nome 'public' che la scansione vede e' in ECCEZIONI_DML"),
    _r("request_backtest", ("live_backtest_requests",), "live_backtest_rpc.sql:23"),
    _r("request_betfair_live_order", ("betfair_live_order_requests",), "betfair_live_order_queue.sql:201"),
    _r("request_betfair_order", ("betfair_order_requests",), "betfair_order_queue.sql:50"),
    _r("request_betfair_refresh", ("betfair_refresh_requests",), "betfair_refresh_queue.sql:37"),
    _r("request_live_risk_rule", ("betfair_live_risk_rules",), "betfair_live_risk_rules_v4.sql:42"),
    _r("request_tennis_live_order", ("tennis_live_order_queue",), "tennis_orders.sql:149"),
    _r("request_tennis_refresh", ("tennis_refresh_requests",), "tennis_markets.sql:145"),
    _r("reset_personal_report", ("personal_trade_legs", "personal_trades", "personal_watchlist"),
       "personal_tracking_rpc.sql:934"),
    _r("safe_activate", ("safe_strategy_control",), "safe_strategy_bot.sql:171"),
    _r("safe_request", ("safe_strategy_requests",), "safe_strategy_paper_live_2026-09-13.sql:731"),
    _r("safe_request_approve", ("safe_strategy_requests",), "safe_strategy_proposed_2026-09-14.sql:44"),
    _r("safe_request_ignore", ("safe_strategy_requests",), "safe_strategy_proposed_2026-09-14.sql:90"),
    _r("safe_stop", ("safe_strategy_control",), "safe_strategy_paper_live_2026-09-13.sql:634"),
    _r("safe_update_params", ("safe_strategy_control",), "safe_strategy_bot.sql:227"),
    _r("save_strategy", ("strategies",), "analytics_strategies_store.sql:27"),
    _r("scalper_activate", ("scalper_control",), "scalper_bot.sql:69"),
    _r("scalper_approva_uscita", ("scalper_control",), "uscite_approva_bot_flusso_2026-09-28.sql:73"),
    _r("scalper_auto_activate", ("scalper_service_control",), "scalper_auto_mode_2026-09-25.sql:99"),
    _r("scalper_auto_stop", ("scalper_control", "scalper_service_control"), "scalper_auto_mode_2026-09-25.sql:162"),
    _r("scalper_auto_update", ("scalper_service_control",), "scalper_auto_mode_2026-09-25.sql:199"),
    _r("scalper_media_attiva_adesso", ("scalper_control",), "media_under_attiva_adesso_2026-10-07.sql:27"),
    _r("scalper_stop", ("scalper_control",), "scalper_bot.sql:135"),
    _r("scalper_stop_sessione", ("scalper_control",), "scalper_control_room_2026-09-24.sql:145"),
    _r("scalper_uscite_automatiche", ("scalper_control", "scalper_service_control"),
       "uscite_automatiche_scalper_2026-09-25.sql:22"),
    _r("segui_live_apri_partita", ("live_follow",), "segui_live_apri_partita_2026-10-06.sql:17"),
    _r("set_follow_record", ("live_follow",), "live_follow_record.sql:45"),
    _r("set_live_journal_note", ("betfair_live_journal",), "betfair_live_pnl_journal.sql:201"),
    _r("set_live_kill_switch", ("betfair_live_settings",), "betfair_live_controls.sql:85"),
    _r("set_live_order_mode", ("betfair_live_settings",), "live_order_mode_control_2026-09-24.sql:68"),
    _r("set_live_settings", ("betfair_live_settings",), "betfair_live_risk_limits_v4.sql:47"),
    _r("set_trade_time_operative", ("personal_trades",), "personal_tracking_import.sql:157"),
    _r("set_watchlist_decision", ("personal_watchlist",), "personal_tracking_rpc.sql:213"),
    _r("set_watchlist_follow_live", ("personal_watchlist",), "watchlist_follow_live.sql:28"),
    _r("settle_personal_trade", ("personal_trades",), "personal_tracking_rpc.sql:552"),
    _r("tennis_bot_approva_uscita", ("tennis_bot_control",), "uscite_approva_bot_flusso_2026-09-28.sql:31"),
    _r("tennis_bot_arm", ("tennis_bot_control",), "tennis_bots_arm_guard.sql:18"),
    _r("tennis_bot_disarm", ("tennis_bot_control",), "tennis_bots.sql:179"),
    _r("tennis_bot_service_activate", ("tennis_bot_service_control",), "tennis_bot_service_control_2026-09-17.sql:49"),
    _r("tennis_bot_service_set_uscite", ("tennis_bot_service_control",), "tennis_uscite_manuali_2026-09-25.sql:84"),
    _r("tennis_bot_service_stop", ("tennis_bot_service_control",), "tennis_bot_service_control_2026-09-17.sql:78"),
    _r("tennis_bot_service_update_params", ("tennis_bot_service_control",),
       "tennis_bot_service_control_2026-09-17.sql:131"),
    _r("tennis_follow_event", ("tennis_live_follow",), "tennis_uscite_manuali_2026-09-25.sql:115"),
    _r("tennis_set_follow_record", ("tennis_live_follow",), "tennis_follow_record.sql:34"),
    _r("upsert_cash_movement", ("personal_cash_movements",), "personal_cash_movements.sql:32"),
    _r("upsert_imported_trade", ("personal_trades",), "personal_tracking_import.sql:44"),
)


# ---------------------------------------------------------------------------
# 4. Le tabelle: una voce per tabella
# ---------------------------------------------------------------------------
V1 = ("V1 (G par. 4.3): outbox vuota entro il ritardo + riconcilia notturno (count e hash di "
      "chiave/updated_at sull'ultimo giorno) + watermark seq senza buchi")
V_LOG = V1 + "; per i log senza chiave: conteggio per (giorno, kind, event_id) +/- 0 dopo la colonna uid (U-50)"
V_CLOUD = ("invariato: scritta direttamente nel cloud come oggi (raccoglitore, RPC o script); "
           "vitalita' = max(data) per tabella (G par. 7)")
D_INVARIATO = "invariato (resta com'e', fuori dal postino)"
D_UI = "invariato: RPC della UI; il bot legge da dati/cache_cloud.py + sveglia (fuori dal ciclo)"
D_ORDINI = "nucleo/ordini via Archivio (stato_denaro) + postino"
D_RUNTIME = "runtime/persistenza via Archivio + postino"
D_LOG = "chi scrive oggi, via Archivio (log) + postino; colonna uid (U-50)"


#: tabelle il cui CREATE TABLE NON e' nel repo (00 par. 3.4: "usate e non definite"): la chiave naturale
#: viene dagli ``on_conflict`` del codice dove ci sono, altrimenti e' vuota perche' NON VERIFICABILE
#: (diverso dai log senza chiave, che hanno lo schema nel repo e davvero non ne hanno una)
SENZA_SCHEMA_NEL_REPO: FrozenSet[str] = frozenset({
    "ai_model_registry", "api_call_log", "api_coverage_by_season", "fixture_predictions", "injuries", "leads",
    "match_events", "match_lineups", "match_odds", "match_player_stats", "match_team_stats", "matches",
    "ml_post_calibration", "model_performance", "season_backfill_state", "standings", "top_assists",
    "top_cards", "top_scorers",
})


def _v(nome: str, famiglia: str, natura: Natura, regime: Regime, proposta: Proposta,
       ritardo: float, chiave: Tuple[str, ...], *, domani: str, coalesce: bool = False,
       rev: Optional[str] = None, dipende: Tuple[str, ...] = (), origine: Origine = "inventario_89",
       fuori: Optional[str] = None, verifica: str = V1, note: str = "") -> VoceRegistro:
    spec = SpecTabella(nome=nome, chiave_naturale=chiave, natura=natura, regime=regime,
                       ritardo_max_s=ritardo, coalesce=coalesce, rev_colonna=rev,
                       dipende_da=dipende, scrittori_oggi=(), scrittore_domani=domani)
    return VoceRegistro(spec=spec, famiglia=famiglia, proposta=proposta, origine=origine,
                        rpc_scriventi=(), scrittura_fuori_codice=fuori, verifica=verifica, note=note,
                        schema_nel_repo=nome not in SENZA_SCHEMA_NEL_REPO)


_NOTTE = ("pg_cron omega_transitions_nightly alle 04:00 UTC -> omega_transitions_step/_publish "
          "(omega_transitions_catchup_2026-09-25.sql)")
_FOLLOW = ("live_follow",)
_FOLLOW_T = ("tennis_live_follow",)
_UA = "updated_at"

_VOCI: Tuple[VoceRegistro, ...] = (
    # --- T01-T04: ordini e denaro (G par. 4.3; 04 par. 6.2)
    _v("betfair_live_order_requests", "T01", "CMD", "stato_denaro", "CMD-L", R_STATO, ("client_ref",),
       domani=D_ORDINI, note="client_ref UNIQUE (betfair_live_order_queue.sql:35); 0 ms in locale, mirror <= 5 s; "
       "nessuna colonna di versione: rev da aggiungere (R02)"),
    _v("betfair_live_orders", "T02", "SV", "stato_denaro", "L+P", R_STATO, ("mode", "client_order_ref"),
       rev=_UA, domani=D_ORDINI + " (specchio)", note="unique (mode, client_order_ref) betfair_live_order_queue.sql"),
    _v("betfair_live_positions", "T03", "SV", "stato_denaro", "L+P", R_STATO,
       ("mode", "market_id", "selection_id", "handicap"), rev=_UA, domani=D_ORDINI),
    _v("betfair_live_settled", "T03", "SV", "stato_denaro", "L+P", R_STATO, ("mode", "market_id"), rev=_UA,
       domani="nucleo/contabilita via Archivio + postino"),
    _v("betfair_live_risk_state", "T03", "SV", "stato_denaro", "L+P", R_STATO, ("id",), rev=_UA,
       domani="nucleo/contabilita via Archivio + postino", note="singleton id=1"),
    _v("betfair_live_account", "T03", "SV", "stato_vivo", "L+P", R_COALESCENTE, ("id",), coalesce=True, rev=_UA,
       domani="nucleo/contabilita via Archivio + postino (coalescente)", note="singleton id=1"),
    _v("betfair_live_heartbeat", "T03", "SV", "stato_vivo", "L+P", R_COALESCENTE, ("id",), coalesce=True, rev=_UA,
       domani="runtime via Archivio + postino (coalescente)", note="singleton id=1"),
    _v("betfair_live_xhedge", "T03", "SV", "stato_denaro", "L+P", R_STATO, ("event_id", "mode"), rev=_UA,
       domani=D_ORDINI),
    _v("betfair_live_risk_rules", "T04", "CFG", "stato_denaro", "L+P", R_STATO, ("client_ref",), rev=_UA,
       domani="nucleo/ordini/controlli.py via postino (autorita' locale, U-51)"),
    # --- T05: impostazioni del live (solo RPC)
    _v("betfair_live_settings", "T05", "CFG", "cache", "CACHE", R_CFG, ("id",), coalesce=True, rev=_UA,
       origine="solo_rpc", domani="invariato: RPC della UI; il runner legge da dati/cache_cloud.py (1 s)",
       note="singleton id=1; scritta SOLO da RPC (g_copertura riga B)"),
    # --- T06: log
    _v("betfair_live_journal", "T06", "ARC", "log", "L+P", R_LOG, (), domani=D_LOG, verifica=V_LOG),
    _v("betfair_live_audit", "T06", "ARC", "log", "L+P", R_LOG, (), domani=D_LOG, verifica=V_LOG),
    _v("live_alerts", "T06", "ARC", "log", "L+P", R_LOG, (), dipende=_FOLLOW, domani=D_LOG, verifica=V_LOG),
    _v("live_run_log", "T06", "ARC", "log", "L+P", R_LOG, ("event_id",), rev=_UA, dipende=_FOLLOW,
       domani=D_LOG, note="upsert per event_id: gia' idempotente"),
    _v("signal_history", "T06", "ARC", "log", "L+P", R_LOG, ("signal_id",), rev=_UA, domani=D_LOG),
    _v("theta_confirm_requests", "T06", "ARC", "log", "L+P", R_LOG, (), domani=D_LOG, verifica=V_LOG,
       note="letta dallo scalper (scalper_session.py:1947): e' anche una coda"),
    # --- T07: follow e watchlist
    _v("live_follow", "T07", "SV", "stato_vivo", "L+P", R_STATO, ("event_id",), rev=_UA,
       dipende=("personal_watchlist",), domani="nucleo/betfair (auto-follow) via Archivio + postino"),
    _v("personal_watchlist", "T07", "SV", "cloud", "CLOUD", NON_APPLICABILE, ("fixture_id",), rev=_UA,
       domani="invariato: RPC della UI; il runner la legge in cache (poll 120 s)", verifica=V_CLOUD),
    # --- T08: display remoto
    _v("live_now", "T08", "SV", "stato_vivo", "L+P", R_LADDER, ("event_id",), coalesce=True, rev=_UA,
       dipende=_FOLLOW, domani="nucleo/betfair e stato_partita via postino (coalescente)"),
    _v("live_markets", "T08", "SV", "stato_vivo", "L+P", R_LADDER, ("event_id", "market_id"), coalesce=True,
       dipende=_FOLLOW, domani="nucleo/betfair via postino (coalescente)"),
    _v("live_ladder", "T08", "SV", "stato_vivo", "L+P", R_LADDER, ("event_id", "market_id"), coalesce=True,
       rev=_UA, dipende=_FOLLOW, domani="nucleo/betfair via postino (coalescente)",
       note="indice UNIQUE non parziale (live_ladder.sql:56)"),
    _v("live_signals", "T08", "SV", "stato_vivo", "L+P", R_LADDER, ("event_id",), coalesce=True, rev=_UA,
       dipende=_FOLLOW, domani="stato_partita via postino (coalescente)"),
    # --- T09: Mike
    _v("mike_control", "T09", "CFG", "cache", "CACHE", R_CFG, ("id",), coalesce=True, rev=_UA, domani=D_UI),
    _v("mike_requests", "T09", "CMD", "cache", "CACHE", R_CFG, ("id",), rev=_UA, domani=D_UI),
    _v("mike_trades", "T09", "SV", "stato_denaro", "L+P", R_STATO, ("id",), dipende=("mike_trades",),
       domani=D_RUNTIME + " (trade_uid, U-80)",
       note="id del cloud = customerOrderRef e closes_trade_id (mike_bot.sql:109): serve trade_uid"),
    _v("mike_events", "T09", "SV", "stato_vivo", "L+P", R_STATO, ("event_id",), rev=_UA, domani=D_RUNTIME),
    _v("mike_activity", "T09", "ARC", "log", "L+P", R_LOG, (), domani=D_LOG, verifica=V_LOG),
    # --- T10: Omega
    _v("omega_control", "T10", "CFG", "cache", "CACHE", R_CFG, ("id",), coalesce=True, rev=_UA, domani=D_UI),
    _v("omega_trades", "T10", "SV", "stato_denaro", "L+P", R_STATO, ("id",), dipende=("omega_trades",),
       domani=D_RUNTIME + " (trade_uid, U-80)", note="closes_trade_id (omega_cashout.sql:50)"),
    _v("omega_events", "T10", "SV", "stato_vivo", "L+P", R_STATO, ("event_id",), rev=_UA, domani=D_RUNTIME),
    _v("omega_manual_requests", "T10", "CMD", "cache", "CACHE", R_CFG, ("id",), rev=_UA, domani=D_UI,
       note="updated_at da omega_proposte_coda_unica_2026-09-17.sql:69"),
    _v("omega_missions", "T10", "CFG", "cache", "CACHE", R_CFG, ("event_id",), rev=_UA, domani=D_UI),
    _v("omega_market_snapshot", "T10", "SV", "stato_vivo", "L+P", R_STATO, ("market_id",), rev=_UA,
       domani=D_RUNTIME),
    _v("omega_daily_goal", "T10", "SV", "stato_vivo", "L+P", R_STATO, ("day",), rev=_UA, domani=D_RUNTIME),
    _v("omega_activity", "T10", "ARC", "log", "L+P", R_LOG, (), domani=D_LOG, verifica=V_LOG),
    _v("omega_requests", "T10", "CMD", "cloud", "CLOUD", NON_APPLICABILE, ("id",), rev=_UA, origine="solo_rpc",
       domani="da chiarire (G par. 4.3 riga B): CMD-L come omega_manual_requests se un bot la legge",
       verifica=V_CLOUD, note="scritta SOLO da RPC della UI (omegaProposte.ts)"),
    # --- T11: Safe e scanner
    _v("safe_strategy_control", "T11", "CFG", "cache", "CACHE", R_CFG, ("id",), coalesce=True, rev=_UA,
       domani=D_UI),
    _v("safe_strategy_requests", "T11", "CMD", "cache", "CACHE", R_CFG, ("id",), rev=_UA,
       domani="transizione locale + mirror (G par. 4.3 T11)"),
    _v("safe_strategy_trades", "T11", "SV", "stato_denaro", "L+P", R_STATO, ("id",),
       dipende=("safe_strategy_trades",), domani=D_RUNTIME + " (trade_uid, U-80)",
       note="closes_trade_id (safe_strategy_bot.sql:73); uq_safe_trades_signal_mode"),
    _v("safe_strategy_opportunities", "T11", "SV", "stato_vivo", "L+P", R_STATO, ("event_id",), rev=_UA,
       domani=D_RUNTIME),
    _v("safe_strategy_activity", "T11", "ARC", "log", "L+P", R_LOG, (), domani=D_LOG, verifica=V_LOG),
    _v("safe_strategy_status", "T11", "SV", "cache", "CACHE", R_CFG, ("id",), coalesce=True, rev=_UA,
       domani="scanner via postino (coalescente)"),
    _v("safe_strategy_scan", "T11", "SV", "stato_vivo", "L+P", R_STATO, ("event_id",), coalesce=True, rev=_UA,
       domani="scanner via postino (coalescente); canale 47336 come via principale"),
    # --- T12: scalper
    _v("scalper_control", "T12", "CFG", "cache", "CACHE", R_SCALPER, ("event_id",), coalesce=True, rev=_UA,
       dipende=_FOLLOW, domani="invariato: RPC della UI; il servizio legge in cache con poll 3 s"),
    _v("scalper_service_control", "T12", "CFG", "cache", "CACHE", R_SCALPER, ("id",), coalesce=True, rev=_UA,
       domani="invariato: RPC della UI; il servizio legge in cache con poll 3 s"),
    _v("scalper_activity", "T12", "ARC", "log", "L+P", R_LOG, (), domani=D_LOG + "; conservazione U-54",
       verifica=V_LOG),
    # --- T13: tennis
    _v("tennis_live_follow", "T13", "SV", "stato_vivo", "L+P", R_STATO, ("event_id",), rev=_UA,
       domani="nucleo/betfair tennis via postino"),
    _v("tennis_live_now", "T13", "SV", "stato_vivo", "L+P", R_STATO, ("event_id",), coalesce=True, rev=_UA,
       dipende=_FOLLOW_T, domani="nucleo/betfair tennis via postino (coalescente)"),
    _v("tennis_live_ladder", "T13", "SV", "stato_vivo", "L+P", R_STATO, ("market_id",), coalesce=True, rev=_UA,
       dipende=_FOLLOW_T, domani="nucleo/betfair tennis via postino (coalescente)"),
    _v("tennis_markets", "T13", "SV", "cloud", "CLOUD", NON_APPLICABILE, ("event_id",),
       domani="invariato: job betfair_tennis_odds.py (0,1/min)", verifica=V_CLOUD),
    _v("tennis_live_orders", "T13", "SV", "stato_denaro", "L+P", R_STATO, ("mode", "client_order_ref"), rev=_UA,
       domani=D_ORDINI + " (tennis)"),
    _v("tennis_live_positions", "T13", "SV", "stato_denaro", "L+P", R_STATO,
       ("mode", "market_id", "selection_id", "handicap"), rev=_UA, domani=D_ORDINI + " (tennis)"),
    _v("tennis_live_order_queue", "T13", "CMD", "stato_denaro", "CMD-L", R_STATO, ("client_ref",),
       domani=D_ORDINI + " (tennis)", note="client_ref UNIQUE (tennis_orders.sql:51)"),
    _v("tennis_bot_control", "T13", "CFG", "cache", "CACHE", R_CFG, ("event_id", "bot_key"), coalesce=True,
       rev=_UA, domani="invariato: RPC della UI; cache + sveglia (canale 47337)"),
    _v("tennis_bot_service_control", "T13", "CFG", "cache", "CACHE", R_CFG, ("bot_key",), coalesce=True,
       rev=_UA, domani="invariato: RPC della UI; cache + sveglia (canale 47337)"),
    _v("tennis_bot_activity", "T13", "ARC", "log", "L+P", R_LOG, (), domani=D_LOG, verifica=V_LOG),
    _v("tennis_refresh_requests", "T13", "CMD", "cloud", "CLOUD", NON_APPLICABILE, ("id",), origine="solo_rpc",
       domani=D_INVARIATO + "; si rivaluta con T14", verifica=V_CLOUD,
       note="scritta SOLO dalla RPC request_tennis_refresh (tennis.ts:123)"),
    # --- T14: code manuali legacy
    _v("betfair_order_requests", "T14", "CMD", "cloud", "CLOUD", NON_APPLICABILE, ("client_ref",),
       domani=D_INVARIATO + "; assorbita solo con U-14", verifica=V_CLOUD),
    _v("betfair_refresh_requests", "T14", "CMD", "cloud", "CLOUD", NON_APPLICABILE, ("id",),
       domani=D_INVARIATO + "; assorbita solo con U-14", verifica=V_CLOUD),
    _v("betfair_market_odds", "T14", "SV", "cloud", "CLOUD", NON_APPLICABILE,
       ("fixture_id", "market_name", "selection"), domani=D_INVARIATO, verifica=V_CLOUD),
    # --- T15: banco, replay, snapshot
    _v("live_backtest_requests", "T15", "CMD", "cloud", "CLOUD", NON_APPLICABILE, ("id",), rev=_UA,
       domani="invariato: coda del banco (worker)", verifica=V_CLOUD),
    _v("live_backtest_results", "T15", "ARC", "cloud", "CLOUD", NON_APPLICABILE, ("id",),
       dipende=("live_backtest_requests",), domani="invariato: worker del banco", verifica=V_CLOUD),
    _v("replay_bot_esiti", "T15", "ARC", "cloud", "CLOUD", NON_APPLICABILE, ("request_id",),
       dipende=("live_backtest_requests",), domani="invariato: worker del banco", verifica=V_CLOUD),
    _v("live_market_snapshots", "T15", "ARC", "cloud", "CLOUD", NON_APPLICABILE, (), dipende=_FOLLOW,
       origine="nome_dinamico", domani="invariato: curatore a lotti (insert_rows_resilient)",
       verifica="conteggi per evento a fine partita", note="2,4 GB; conservazione U-54"),
    _v("live_score_timeline", "T15", "ARC", "cloud", "CLOUD", NON_APPLICABILE, (), dipende=_FOLLOW,
       origine="nome_dinamico", domani="invariato: curatore a lotti", verifica="conteggi per evento"),
    _v("tennis_replay_eventi", "T15", "ARC", "cloud", "CLOUD", NON_APPLICABILE, ("event_id",), rev=_UA,
       domani="invariato: caricamento a lotti del Replay Tennis", verifica="conteggi per evento"),
    _v("tennis_replay_mercati", "T15", "ARC", "cloud", "CLOUD", NON_APPLICABILE, ("event_id", "market_id"),
       dipende=("tennis_replay_eventi",), domani="invariato: caricamento a lotti",
       verifica="il caricamento rilegge (caricamento.py:97) e confronta"),
    _v("tennis_replay_snapshots", "T15", "ARC", "cloud", "CLOUD", NON_APPLICABILE, (),
       dipende=("tennis_replay_eventi",), origine="nome_dinamico", domani="invariato: caricamento a lotti",
       verifica="conteggi per evento"),
    _v("tennis_replay_punteggio", "T15", "ARC", "cloud", "CLOUD", NON_APPLICABILE, (),
       dipende=("tennis_replay_eventi",), origine="nome_dinamico", domani="invariato: caricamento a lotti",
       verifica="conteggi per evento"),
    # --- T16: statistiche e analisi (cloud, raccoglitori e RPC)
    _v("personal_trades", "T16", "STA", "cloud", "CLOUD", NON_APPLICABILE, ("id",), rev=_UA,
       dipende=("personal_watchlist",), domani="invariato: RPC della UI e import", verifica=V_CLOUD),
    _v("personal_trade_legs", "T16", "SV", "cloud", "CLOUD", NON_APPLICABILE, ("id",),
       dipende=("personal_trades",), origine="solo_rpc", domani="invariato: RPC della UI", verifica=V_CLOUD),
    _v("personal_cash_movements", "T16", "ARC", "cloud", "BATCH", NON_APPLICABILE, ("transaction_id",),
       origine="solo_rpc", domani="invariato: import_betfair_operations.py", verifica=V_CLOUD),
    _v("strategies", "T16", "CFG", "cloud", "CLOUD", NON_APPLICABILE, ("name",), rev=_UA, origine="solo_rpc",
       domani="invariato: RPC della UI (Analytics)", verifica=V_CLOUD),
    _v("bet_features", "T16", "STA", "cloud", "CLOUD", NON_APPLICABILE, (),
       fuori="VISTA (migrations/analytics_features.sql:10): nessuno la scrive, si legge soltanto",
       domani="invariato (vista)", verifica="nessuna riga propria: e' una vista"),
    _v("direction_pagella", "T16", "STA", "cloud", "BATCH", NON_APPLICABILE,
       ("engine", "market", "selection", "league_id", "prob_bucket"), domani=D_INVARIATO, verifica=V_CLOUD),
    _v("engine_signals", "T16", "STA", "cloud", "BATCH", NON_APPLICABILE, ("signal_uid",), rev=_UA,
       domani=D_INVARIATO, verifica=V_CLOUD),
    _v("analytics_bets", "T16", "STA", "cloud", "BATCH", NON_APPLICABILE, ("fixture_id", "market", "selection"),
       domani=D_INVARIATO, verifica=V_CLOUD, note="scritta dalla RPC refresh_analytics_bets_range (delegata)"),
    _v("analytics_decisions", "T16", "STA", "cloud", "BATCH", NON_APPLICABILE, ("decision_uid",), rev=_UA,
       domani=D_INVARIATO, verifica=V_CLOUD, note="scritta per nome dinamico (merge_engine_signals.py:259)"),
    _v("analytics_snap_staging", "T16", "STA", "cloud", "BATCH", NON_APPLICABILE,
       ("fixture_id", "market", "selection"), domani=D_INVARIATO, verifica=V_CLOUD),
    _v("analytics_signals", "T16", "STA", "cloud", "BATCH", NON_APPLICABILE, ("signal_uid",), rev=_UA,
       domani=D_INVARIATO, verifica=V_CLOUD),
    _v("poisson_calibration", "T16", "STA", "cloud", "BATCH", NON_APPLICABILE, ("league_id",), rev=_UA,
       domani=D_INVARIATO, verifica=V_CLOUD),
    _v("ml_post_calibration", "T16", "STA", "cloud", "BATCH", NON_APPLICABILE, (), domani=D_INVARIATO,
       verifica=V_CLOUD, note="schema fuori dal repo"),
    _v("ai_model_registry", "T16", "STA", "cloud", "BATCH", NON_APPLICABILE, (), domani=D_INVARIATO,
       verifica=V_CLOUD, note="schema fuori dal repo"),
    _v("model_performance", "T16", "STA", "cloud", "BATCH", NON_APPLICABILE, ("league_id", "target"),
       domani=D_INVARIATO, verifica=V_CLOUD, note="on_conflict league_id,target (retrain_all_leagues.py:374)"),
    _v("book_odds_cache", "T16", "STA", "cloud", "BATCH", NON_APPLICABILE, ("fixture_id", "market", "selection"),
       origine="solo_rpc", domani=D_INVARIATO, verifica=V_CLOUD,
       note="trovata dalla chiusura della RPC refresh_analytics_bets_range: assente dalle 6 di g_copertura"),
    _v("book_odds_cache_fonte", "T16", "STA", "cloud", "BATCH", NON_APPLICABILE, ("fixture_id",),
       origine="solo_rpc", domani=D_INVARIATO, verifica=V_CLOUD,
       note="come book_odds_cache (refresh_analytics_bets_range_v2_2026-09-24.sql:170)"),
    # --- T17: storico e statistiche di contorno (raccoglitori)
    _v("matches", "T17", "STA", "cloud", "BATCH", NON_APPLICABILE, ("fixture_id",), domani=D_INVARIATO,
       verifica=V_CLOUD, note="schema fuori dal repo"),
    _v("match_odds", "T17", "ARC", "cloud", "BATCH", NON_APPLICABILE, (), domani=D_INVARIATO, verifica=V_CLOUD,
       note="92,5 M righe, 20 GB; football_data_scraper senza lancio automatico"),
    _v("match_events", "T17", "ARC", "cloud", "BATCH", NON_APPLICABILE, (), domani=D_INVARIATO,
       verifica=V_CLOUD, note="scritta per nome dinamico (per_fixture_backfill.py)"),
    _v("match_lineups", "T17", "ARC", "cloud", "BATCH", NON_APPLICABILE, (), origine="nome_dinamico",
       domani=D_INVARIATO, verifica=V_CLOUD),
    _v("match_player_stats", "T17", "ARC", "cloud", "BATCH", NON_APPLICABILE, (), origine="nome_dinamico",
       domani=D_INVARIATO, verifica=V_CLOUD),
    _v("match_team_stats", "T17", "ARC", "cloud", "BATCH", NON_APPLICABILE, (), domani=D_INVARIATO,
       verifica=V_CLOUD),
    _v("fixture_predictions", "T17", "STA", "cloud", "BATCH", NON_APPLICABILE, ("fixture_id",),
       domani=D_INVARIATO + "; letta dagli algoritmi da dati/cache_cloud.py", verifica=V_CLOUD,
       note="colonna nucleo_versione scritta SOLO dal trigger trg_nucleo_versione_dossier "
            "(nucleo_sentinella_cloud_2026-10-10.sql, decisione 10): nessuno scrittore nuovo nel codice"),
    _v("standings", "T17", "STA", "cloud", "BATCH", NON_APPLICABILE, (), domani=D_INVARIATO, verifica=V_CLOUD),
    _v("injuries", "T17", "STA", "cloud", "BATCH", NON_APPLICABILE, (), domani=D_INVARIATO, verifica=V_CLOUD),
    _v("top_scorers", "T17", "STA", "cloud", "BATCH", NON_APPLICABILE, (), domani=D_INVARIATO, verifica=V_CLOUD),
    _v("top_assists", "T17", "STA", "cloud", "BATCH", NON_APPLICABILE, (), domani=D_INVARIATO, verifica=V_CLOUD),
    _v("top_cards", "T17", "STA", "cloud", "BATCH", NON_APPLICABILE, (), domani=D_INVARIATO, verifica=V_CLOUD),
    _v("api_coverage_by_season", "T17", "STA", "cloud", "BATCH", NON_APPLICABILE, (), domani=D_INVARIATO,
       verifica=V_CLOUD),
    _v("api_call_log", "T17", "ARC", "cloud", "BATCH", NON_APPLICABILE, (), domani=D_INVARIATO,
       verifica=V_CLOUD, note="2,75 M righe; conservazione U-54"),
    _v("season_backfill_state", "T17", "STA", "cloud", "BATCH", NON_APPLICABILE, ("league_id", "season_year"),
       domani=D_INVARIATO, verifica=V_CLOUD),
    _v("fixture_detail_checks", "T17", "STA", "cloud", "BATCH", NON_APPLICABILE, ("fixture_id", "tabella"),
       domani=D_INVARIATO, verifica=V_CLOUD, note="scritta SOLO dalla RPC record_fixture_detail_checks"),
    _v("leads", "T17", "ARC", "cloud", "CLOUD", NON_APPLICABILE, (), domani="invariato: landing (frontend)",
       verifica=V_CLOUD),
    # --- EXTRA: fuori dalle 89 dell'inventario (trovate dalla scansione o lette dagli algoritmi)
    _v("hazard_atlas", "EXTRA", "STA", "cloud", "BATCH", NON_APPLICABILE, ("id",), origine="rest",
       domani="invariato: genera_atlante.py (REST)", verifica=V_CLOUD),
    _v("hazard_atlas_leghe", "EXTRA", "STA", "cloud", "BATCH", NON_APPLICABILE, ("league_id",), rev=_UA,
       origine="rest", domani="invariato: genera_atlante.py (REST)", verifica=V_CLOUD),
    _v("monitor_metrics", "EXTRA", "ARC", "cloud", "CLOUD", NON_APPLICABILE, (), origine="nuova",
       domani="invariato: scrittore del modulo Salute (T0A) a lotti",
       verifica="conservazione 7 giorni (decisione 09/10, RPC monitor_metrics_pulizia)",
       note="NUOVA (T0A, 09/10): non era nelle 89 dell'inventario del 08/10"),
    _v("omega_ht_ft_transitions", "EXTRA", "STA", "cloud", "CLOUD", NON_APPLICABILE, ("league_id", "ht", "ft"),
       origine="mondo_sql", fuori="pg_cron omega_transitions_nightly alle 04:00 UTC "
       "(omega_transitions_catchup_2026-09-25.sql:446): nessuno scrittore nel codice",
       domani="invariato (pg_cron); letta da dati/cache_cloud.py dopo built_at", verifica=V_CLOUD),
    _v("omega_minute_transitions", "EXTRA", "STA", "cloud", "CLOUD", NON_APPLICABILE,
       ("league_id", "bucket", "target", "score", "result"), origine="mondo_sql",
       fuori="pg_cron omega_transitions_nightly alle 04:00 UTC: nessuno scrittore nel codice",
       domani="invariato (pg_cron); letta da dati/cache_cloud.py per lega", verifica=V_CLOUD),
    # --- EXTRA dalla revisione del 09/10 (D-1): scritte lato server o dai workflow
    _v("analytics_riepilogo_segnali", "T16", "STA", "cloud", "BATCH", NON_APPLICABILE, (), origine="solo_rpc",
       domani=D_INVARIATO, verifica=V_CLOUD, note="ricostruita per intero dalla RPC refresh_analytics_riepilogo "
       "(predictions_results_backfill.yml:200, ogni notte): nessuna chiave, riepilogo aggregato"),
    _v("analytics_riepilogo_decisioni", "T16", "STA", "cloud", "BATCH", NON_APPLICABILE, (), origine="solo_rpc",
       domani=D_INVARIATO, verifica=V_CLOUD, note="come analytics_riepilogo_segnali"),
    _v("analytics_riepilogo_meta", "T16", "STA", "cloud", "BATCH", NON_APPLICABILE, ("chiave",), origine="solo_rpc",
       domani=D_INVARIATO, verifica=V_CLOUD),
    _v("analytics_prob_staging", "T16", "STA", "cloud", "BATCH", NON_APPLICABILE, ("signal_uid",),
       origine="solo_rpc", domani=D_INVARIATO, verifica=V_CLOUD,
       fuori="dormiente: nessun codice del repo la riempie ne' chiama flush_analytics_prob_staging "
       "(analytics_prob_staging.sql:11,22)"),
    _v("omega_ht_ft_transitions_raw", "EXTRA", "STA", "cloud", "CLOUD", NON_APPLICABILE, ("league_id", "ht", "ft"),
       origine="mondo_sql", fuori=_NOTTE, domani="invariato (pg_cron)", verifica=V_CLOUD),
    _v("omega_minute_transitions_raw", "EXTRA", "STA", "cloud", "CLOUD", NON_APPLICABILE,
       ("league_id", "bucket", "target", "score", "result"), origine="mondo_sql", fuori=_NOTTE,
       domani="invariato (pg_cron)", verifica=V_CLOUD),
    _v("omega_transitions_league_counts", "EXTRA", "STA", "cloud", "CLOUD", NON_APPLICABILE, ("league_id",),
       rev=_UA, origine="mondo_sql", fuori=_NOTTE, domani="invariato (pg_cron)", verifica=V_CLOUD),
    _v("omega_transitions_ledger", "EXTRA", "STA", "cloud", "CLOUD", NON_APPLICABILE, ("fixture_id",),
       origine="mondo_sql", fuori=_NOTTE, domani="invariato (pg_cron)", verifica=V_CLOUD),
    _v("omega_transitions_runs", "EXTRA", "ARC", "cloud", "CLOUD", NON_APPLICABILE, ("id",),
       origine="mondo_sql", fuori=_NOTTE, domani="invariato (pg_cron)", verifica=V_CLOUD,
       note="referto per giro del pg_cron"),
    _v("omega_transitions_state", "EXTRA", "STA", "cloud", "CLOUD", NON_APPLICABILE, ("id",), rev=_UA,
       origine="mondo_sql", fuori=_NOTTE, domani="invariato (pg_cron); sentinella di dati/cache_cloud.py",
       verifica=V_CLOUD, note="singleton id=1: updated_at a ogni giro del pg_cron"),
    _v("omega_minute_league_counts", "EXTRA", "STA", "cloud", "CLOUD", NON_APPLICABILE, ("league_id",),
       origine="mondo_sql", fuori=_NOTTE + " e costruzione v3/v4 a mano (omega_models_v3.sql, v4.sql)",
       domani="invariato (SQL)", verifica=V_CLOUD),
    _v("omega_build_jobs", "EXTRA", "STA", "cloud", "CLOUD", NON_APPLICABILE, ("job",), rev=_UA,
       origine="mondo_sql", fuori="costruzione a passi della tabella per minuto (omega_models_v3.sql:93, "
       "omega_models_v4.sql:166), lanciata a mano", domani="invariato (SQL)", verifica=V_CLOUD),
    # --- EXTRA dall'integrazione W1-G1 (09/10): tabella tecnica della migrazione dell'architettura
    _v("postino_versioni", "EXTRA", "STA", "cloud", "CLOUD", NON_APPLICABILE, ("tabella", "chiave", "origine"),
       origine="nuova", domani="invariato: la scrive SOLO la RPC postino_consegna, nel cloud (mai il postino "
       "direttamente)", verifica="pulizia dentro la RPC: righe piu' vecchie di 90 giorni, al massimo 100 per "
       "chiamata (architettura_uid_ombra_2026-10-09.sql:210-213,327-330)",
       note="NUOVA (W1-G1, 09/10): versione locale piu' alta applicata per (tabella, chiave, origine), R1; "
       "PRIMARY KEY (tabella, chiave, origine) architettura_uid_ombra_2026-10-09.sql:214-221"),
    _v("lanci_action", "EXTRA", "ARC", "cloud", "CLOUD", NON_APPLICABILE, ("giorno", "workflow_file"),
       origine="mondo_sql", fuori="pg_cron orologio_daily/orologio_verifica_* (orologio_action_notturne_2026-10-09.sql"
       ":208-355,525-533)", domani="invariato (pg_cron)", verifica=V_CLOUD),
)


# ---------------------------------------------------------------------------
# 4-bis. Tabelle SOLO LOCALI (archivio di W1-G1, MAI il cloud) - integrazione W1-C1, 09/10
# ---------------------------------------------------------------------------
#: la destinazione delle tabelle di ``TABELLE_SOLO_LOCALI``: il file locale, nessun postino
DESTINAZIONE_SOLO_LOCALE = "solo locale"


def _solo_locale(nome: str, chiave: Tuple[str, ...], domani: str) -> SpecTabella:
    """Una tabella SOLO LOCALE: regime ``stato_denaro`` (``denaro.sqlite3``, WAL
    ``synchronous=FULL``), nessun ritardo verso il cloud (non ci va), nessuna versione."""
    return SpecTabella(nome=nome, chiave_naturale=chiave, natura="SV", regime="stato_denaro",
                       ritardo_max_s=NON_APPLICABILE, coalesce=False, rev_colonna=None, dipende_da=(),
                       scrittori_oggi=(), scrittore_domani=domani)


#: tabelle che vivono SOLO nell'archivio locale di W1-G1 e NON sono tabelle del cloud: non
#: stanno nel ``REGISTRO`` (che e' il registro del cloud: il client le rifiuta), non hanno uno
#: schema in ``migrations/``. L'archivio le legge da qui (``ArchivioLocale.spec``, prima del
#: registro iniettato) e per loro: righe nel file ``denaro`` con durabilita' PIENA, NESSUNA voce
#: in outbox (il postino non le vede mai), nessuna riconciliazione notturna col cloud e quindi
#: nessuna pulizia (la pulizia toglie solo righe riconciliate ``ok``): restano finche' c'e' il file.
#: Fonti: referto W1-C1 par. 11-12 (tabelle della porta), referto W1-G1 par. 12 (regime).
TABELLE_SOLO_LOCALI: Mapping[str, SpecTabella] = {
    "ordini_ref_visti": _solo_locale(
        "ordini_ref_visti", ("ref",),
        "nucleo/ordini/porta.py: PortaLocale._registra_ack e _rifiuto_dopo_seq (scrivi), _dedup (leggi); "
        "colonne ref, attore, accettato, seq, motivo, ts_ms"),
    "ordini_seq": _solo_locale(
        "ordini_seq", ("chiave",),
        "nucleo/ordini/porta.py: PortaLocale._nuovo_seq (scrivi, ogni BLOCCO_SEQ seq), apri (leggi); "
        "una riga sola, chiave='seq', colonne chiave, fino_a"),
}

#: perche' ognuna resta sul PC (oggi l'equivalente e' il diario del motore, file locali)
MOTIVI_SOLO_LOCALI: Mapping[str, str] = {
    "ordini_ref_visti": "dedup per ref della porta degli ordini: oggi vive nel diario locale del motore "
                        "(motore_ordini._carica_visti); nessuna tabella del cloud la riceve oggi",
    "ordini_seq": "blocco dei seq prenotato (seq mai indietro dopo un riavvio): stato interno della porta, "
                  "oggi in memoria del motore; nessuna tabella del cloud la riceve oggi",
}


def controlla_solo_locali(registro: RegistroTabelle) -> Tuple[str, ...]:
    """Le tabelle solo locali: mai nel registro del cloud, regime ``stato_denaro``, nessun
    ritardo verso il cloud, un motivo ciascuna. Ritorna gli errori (vuoto = coerenti)."""
    errori: List[str] = []
    cloud = set(registro.tabelle())
    for nome, s in sorted(TABELLE_SOLO_LOCALI.items()):
        if s.nome != nome:
            errori.append(f"{nome}: nome della spec diverso ({s.nome})")
        if nome in cloud:
            errori.append(f"{nome}: tabella SOLO LOCALE registrata anche come tabella del cloud")
        if s.regime != "stato_denaro":
            errori.append(f"{nome}: regime {s.regime} invece di stato_denaro (durabilita' piena)")
        if s.ritardo_max_s != NON_APPLICABILE or s.coalesce or s.dipende_da:
            errori.append(f"{nome}: ritardo, coalescenza o dipendenze verso il cloud su una tabella solo locale")
        if not s.chiave_naturale:
            errori.append(f"{nome}: senza chiave naturale")
        if not MOTIVI_SOLO_LOCALI.get(nome):
            errori.append(f"{nome}: nessun motivo dichiarato in MOTIVI_SOLO_LOCALI")
    return tuple(errori)


# ---------------------------------------------------------------------------
# 5. Composizione: scrittori di oggi = codice diretto + nomi dinamici + REST + RPC
# ---------------------------------------------------------------------------
def _siti_per_tabella(siti: Iterable[SitoDinamico]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for s in siti:
        for t in s.tabelle:
            out.setdefault(t, []).extend(f"{s.file}:{r}" for r in s.righe)
    return out


def _componi(voci: Iterable[VoceRegistro], rpc: Iterable[RpcScrivente]) -> Tuple[VoceRegistro, ...]:
    """Riempie ``scrittori_oggi`` (file:riga del codice, poi ``rpc:<nome>``) e ``rpc_scriventi``."""
    dinamici = _siti_per_tabella(SITI_DINAMICI)
    rest = _siti_per_tabella(SCRITTURE_REST)
    per_tabella: Dict[str, List[str]] = {}
    for r in rpc:
        for t in r.tabelle:
            per_tabella.setdefault(t, []).append(r.nome)
    out = []
    for v in voci:
        nome = v.spec.nome
        codice = list(_SCRITTURE_DIRETTE.get(nome, ())) + dinamici.get(nome, []) + rest.get(nome, [])
        nomi_rpc = tuple(sorted(per_tabella.get(nome, [])))
        scrittori = tuple(dict.fromkeys(codice)) + tuple(f"rpc:{n}" for n in nomi_rpc)
        out.append(replace(v, spec=replace(v.spec, scrittori_oggi=scrittori), rpc_scriventi=nomi_rpc))
    return tuple(out)


def file_di(scrittori: Iterable[str]) -> FrozenSet[str]:
    """I file (senza riga) fra gli scrittori di oggi; esclusi ``rpc:``."""
    return frozenset(s.rsplit(":", 1)[0] for s in scrittori if not s.startswith("rpc:"))


class RegistroTabelle:
    """Il registro: interrogabile per nome (``spec``, contratto G par. 4.5) e confrontabile
    con il codice (``verifica_copertura``). Immutabile; ``senza`` ne fa una copia ridotta
    (usata per falsificare il test di copertura)."""

    def __init__(self, voci: Iterable[VoceRegistro], rpc: Iterable[RpcScrivente]) -> None:
        self._rpc: Dict[str, RpcScrivente] = {}
        for r in rpc:
            if r.nome in self._rpc:
                raise ValueError(f"RPC registrata due volte: {r.nome}")
            self._rpc[r.nome] = r
        self._voci: Dict[str, VoceRegistro] = {}
        for v in _componi(voci, self._rpc.values()):
            if v.spec.nome in self._voci:
                raise ValueError(f"tabella registrata due volte: {v.spec.nome}")
            self._voci[v.spec.nome] = v

    def spec(self, tabella: str) -> SpecTabella:
        return self.voce(tabella).spec

    def voce(self, tabella: str) -> VoceRegistro:
        try:
            return self._voci[tabella]
        except KeyError:
            raise KeyError(f"tabella non registrata: {tabella} (Betfair/nucleo/dati/registro.py)") from None

    def tabelle(self) -> Tuple[str, ...]:
        return tuple(sorted(self._voci))

    def voci(self) -> Tuple[VoceRegistro, ...]:
        return tuple(self._voci[n] for n in self.tabelle())

    def rpc_scriventi(self) -> Mapping[str, RpcScrivente]:
        return dict(self._rpc)

    def rpc_scrive(self, nome: str) -> bool:
        """True se la RPC e' registrata come scrivente (il client non la ritenta mai)."""
        return nome in self._rpc

    def senza(self, *tabelle: str, rpc: Tuple[str, ...] = ()) -> "RegistroTabelle":
        """Copia del registro senza le voci (e le RPC) indicate."""
        voci = [replace(v, spec=replace(v.spec, scrittori_oggi=()), rpc_scriventi=())
                for n, v in self._voci.items() if n not in tabelle]
        return RegistroTabelle(voci, [r for n, r in self._rpc.items() if n not in rpc])


def e_rpc_di_lettura(nome: str, sola_lettura_strumento: Iterable[str] = ()) -> bool:
    """Regola dello strumento ``g_copertura_tabelle`` (prefissi get_/list_ e il suo elenco)
    piu' le RPC dichiarate qui (``RPC_SOLA_LETTURA_DICHIARATE``)."""
    return (nome.startswith(("get_", "list_")) or nome in RPC_SOLA_LETTURA_DICHIARATE
            or nome in set(sola_lettura_strumento))


# ---------------------------------------------------------------------------
# 6. Il confronto registro <-> codice
# ---------------------------------------------------------------------------
def _chiavi_siti(siti: Iterable[SitoDinamico]) -> Dict[Tuple[str, str], SitoDinamico]:
    return {(s.file, s.nome): s for s in siti}


def _controlla_dinamici(registro: RegistroTabelle, scansione: Scansione,
                        errori: List[str], avvisi: List[str]) -> None:
    registrate = set(registro.tabelle())
    for gruppo, dichiarati, cosa in ((scansione.dinamici, SITI_DINAMICI, "scrittura .table"),
                                     (scansione.indeterminati, SITI_PASSANTI, "builder senza operazione"),
                                     (scansione.rpc_dinamiche, RPC_DINAMICHE, ".rpc dinamica")):
        noti = _chiavi_siti(dichiarati)
        for chiave, righe in sorted(gruppo.items()):
            sito = noti.get(chiave)
            if sito is None and chiave[1] in registrate:
                continue                      # builder di una tabella letterale gia' registrata
            if sito is None:
                errori.append(f"NOME DINAMICO NON RISOLTO ({cosa}): {chiave[0]}:{sorted(righe)} {chiave[1]} "
                              f"-> leggere il codice e dichiararlo in registro.py")
            elif set(righe) != set(sito.righe):
                avvisi.append(f"righe spostate {chiave[0]} {chiave[1]}: registro {sorted(sito.righe)}, "
                              f"codice {sorted(righe)}")


def _controlla_rpc(registro: RegistroTabelle, scansione: Scansione, sola_lettura: Iterable[str],
                   errori: List[str], avvisi: List[str]) -> None:
    sola_lettura = set(sola_lettura)
    noti = registro.rpc_scriventi()
    tabelle = set(registro.tabelle())
    for nome, chiamanti in sorted(scansione.rpc.items()):
        dml = set(scansione.dml_rpc.get(nome, frozenset()))
        if nome in noti:
            continue
        if e_rpc_di_lettura(nome, sola_lettura):
            if dml:
                errori.append(f"RPC DI LETTURA CHE SCRIVE: {nome} tocca {sorted(dml)} "
                              f"(chiamanti {sorted(chiamanti)[:3]}): registrarla in RPC_SCRIVENTI_ELENCO")
            continue
        errori.append(f"RPC SCRIVENTE ASSENTE DAL REGISTRO: {nome} (chiamanti {sorted(chiamanti)[:3]}, "
                      f"tabelle {sorted(dml) or 'definizione non trovata'})")
    for nome, r in sorted(noti.items()):
        fuori = set(r.tabelle) - tabelle
        if fuori:
            errori.append(f"RPC {nome}: tabelle non registrate {sorted(fuori)}")
        if nome in scansione.rpc_definite:
            # i nomi di ECCEZIONI_DML non sono tabelle (motivo per ciascuno): valgono anche qui, come
            # in _controlla_migrazioni; nessun'altra tabella trovata nella definizione si ignora
            dml = set(scansione.dml_rpc.get(nome, frozenset())) - set(ECCEZIONI_DML)
            mancano = dml - set(r.tabelle)
            if mancano:
                errori.append(f"RPC {nome}: la definizione SQL scrive anche {sorted(mancano)} (registro: "
                              f"{list(r.tabelle)})")
            if set(r.tabelle) - dml:
                avvisi.append(f"RPC {nome}: dichiarate {sorted(set(r.tabelle) - dml)} che la definizione "
                              f"non tocca")
        if nome not in scansione.rpc:
            avvisi.append(f"RPC {nome} registrata ma nessun chiamante nel codice")


def _scrittori_trovati(registro: RegistroTabelle, scansione: Scansione) -> Dict[str, set]:
    """tabella -> {"file:riga"} trovati nel codice (diretti + siti dinamici + REST)."""
    trovati: Dict[str, set] = {t: set(v) for t, v in scansione.scritture.items()}
    for gruppo, dichiarati in ((scansione.dinamici, SITI_DINAMICI), (scansione.rest, SCRITTURE_REST)):
        noti = _chiavi_siti(dichiarati)
        for chiave, righe in gruppo.items():
            sito = noti.get(chiave)
            for t in (sito.tabelle if sito else ()):
                trovati.setdefault(t, set()).update(f"{chiave[0]}:{r}" for r in righe)
    return trovati


def _controlla_rest(scansione: Scansione, errori: List[str]) -> None:
    noti = _chiavi_siti(SCRITTURE_REST)
    for chiave, righe in sorted(scansione.rest.items()):
        if chiave not in noti:
            errori.append(f"SCRITTURA REST NON REGISTRATA: {chiave[0]}:{sorted(righe)} -> {chiave[1]}")


def _controlla_tabelle(registro: RegistroTabelle, scansione: Scansione,
                       errori: List[str], avvisi: List[str]) -> None:
    trovati = _scrittori_trovati(registro, scansione)
    registrate = set(registro.tabelle())
    for t in sorted(set(trovati) - registrate):
        errori.append(f"TABELLA SCRITTA DAL CODICE E ASSENTE DAL REGISTRO: {t} "
                      f"(scrittori {sorted(trovati[t])[:4]})")
    rpc_chiamate = set(scansione.rpc)
    for v in registro.voci():
        t = v.spec.nome
        codice = trovati.get(t, set())
        dichiarati = [s for s in v.spec.scrittori_oggi if not s.startswith("rpc:")]
        nuovi = file_di(codice) - file_di(dichiarati)
        if nuovi:
            errori.append(f"SCRITTORE NON REGISTRATO per {t}: " +
                          ", ".join(sorted(s for s in codice if s.rsplit(':', 1)[0] in nuovi)))
        spariti = file_di(dichiarati) - file_di(codice)
        if spariti:
            avvisi.append(f"{t}: scrittore registrato che non scrive piu': {sorted(spariti)}")
        elif set(dichiarati) != codice:
            avvisi.append(f"{t}: righe spostate (registro {sorted(set(dichiarati) - codice)[:3]}, "
                          f"codice {sorted(codice - set(dichiarati))[:3]})")
        dal_sql = t in scansione.dml_migrazioni and v.scrittura_fuori_codice is not None
        if v.origine == "mondo_sql" and t not in scansione.dml_migrazioni:
            avvisi.append(f"{t}: dichiarata scritta dal SQL ma nessun DML nelle migrazioni")
        vive = codice or (set(v.rpc_scriventi) & rpc_chiamate) or dal_sql
        if not vive:
            if v.scrittura_fuori_codice:
                avvisi.append(f"{t}: nessuno la scrive dal codice (dichiarato: {v.scrittura_fuori_codice})")
            else:
                errori.append(f"VOCE SENZA SCRITTORI NON DICHIARATA: {t} (nessuna scrittura nel codice ne' RPC "
                              f"chiamata): dichiarare scrittura_fuori_codice o togliere la voce")


def _controlla_migrazioni(registro: RegistroTabelle, scansione: Scansione, errori: List[str]) -> None:
    """Ogni tabella con INSERT/UPDATE/DELETE/TRUNCATE in una funzione o in un ``cron.schedule``
    delle migrazioni e' registrata o e' un'eccezione motivata (``ECCEZIONI_DML``)."""
    registrate = set(registro.tabelle())
    for t, dove in sorted(scansione.dml_migrazioni.items()):
        if t in registrate and t in ECCEZIONI_DML:
            errori.append(f"ECCEZIONE DML SU UNA TABELLA REGISTRATA: {t}")
        elif t not in registrate and t not in ECCEZIONI_DML:
            errori.append(f"TABELLA SCRITTA DA FUNZIONI SQL/PG_CRON E ASSENTE DAL REGISTRO: {t} ({sorted(dove)[:3]})")


def _controlla_storage(scansione: Scansione, errori: List[str], avvisi: List[str]) -> None:
    noti = _chiavi_siti(SITI_STORAGE)
    for chiave, righe in sorted(scansione.storage.items()):
        sito = noti.get(chiave)
        if sito is None:
            errori.append(f"STORAGE NON DICHIARATO: {chiave[0]}:{sorted(righe)} {chiave[1]} -> SITI_STORAGE")
        elif set(righe) != set(sito.righe):
            avvisi.append(f"righe spostate (storage) {chiave[0]}: registro {sorted(sito.righe)}, codice {sorted(righe)}")


def verifica_copertura(registro: RegistroTabelle, scansione: Scansione,
                       sola_lettura_strumento: Iterable[str] = ()) -> EsitoCopertura:
    """Confronta il registro con il codice di oggi (Python, frontend, workflow, migrazioni).
    ERRORI: tabella scritta (dal codice o da una funzione SQL/pg_cron) e non registrata,
    file scrittore non registrato, nome dinamico o REST non risolto, RPC scrivente non
    registrata o che scrive tabelle non dichiarate, voce senza scrittori non dichiarata.
    AVVISI: righe spostate, scrittori spariti, voci senza scrittori ma dichiarate."""
    errori: List[str] = []
    avvisi: List[str] = []
    _controlla_dinamici(registro, scansione, errori, avvisi)
    _controlla_rest(scansione, errori)
    _controlla_rpc(registro, scansione, sola_lettura_strumento, errori, avvisi)
    _controlla_tabelle(registro, scansione, errori, avvisi)
    _controlla_migrazioni(registro, scansione, errori)
    _controlla_storage(scansione, errori, avvisi)
    return EsitoCopertura(tuple(errori), tuple(avvisi))


def controlla_coerenza(registro: RegistroTabelle) -> Tuple[str, ...]:
    """Coerenza interna (senza il codice): dipendenze registrate, ritardi coerenti col regime,
    chiavi e tipi del contratto. Ritorna gli errori (vuoto = coerente)."""
    errori: List[str] = []
    nomi = set(registro.tabelle())
    for v in registro.voci():
        s = v.spec
        if not isinstance(s.chiave_naturale, tuple) or not all(isinstance(c, str) for c in s.chiave_naturale):
            errori.append(f"{s.nome}: chiave_naturale non e' una tupla di stringhe")
        if s.ritardo_max_s < 0:
            errori.append(f"{s.nome}: ritardo negativo")
        if (s.regime == "cloud") != (s.ritardo_max_s == NON_APPLICABILE):
            errori.append(f"{s.nome}: regime {s.regime} con ritardo {s.ritardo_max_s} (cloud <=> non applicabile)")
        if s.regime == "log" and s.ritardo_max_s != R_LOG:
            errori.append(f"{s.nome}: log con ritardo {s.ritardo_max_s} invece di {R_LOG}")
        fuori = set(s.dipende_da) - nomi
        if fuori:
            errori.append(f"{s.nome}: dipende da tabelle non registrate {sorted(fuori)}")
        if not s.scrittore_domani:
            errori.append(f"{s.nome}: scrittore_domani mancante")
        if not s.scrittori_oggi and not v.scrittura_fuori_codice:
            errori.append(f"{s.nome}: nessuno scrittore di oggi e nessuna dichiarazione")
    return tuple(errori)


#: il registro di oggi
REGISTRO = RegistroTabelle(_VOCI, RPC_SCRIVENTI_ELENCO)
