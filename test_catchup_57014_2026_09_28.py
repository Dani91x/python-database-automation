"""Cantiere 28/09/2026 - Seasons Catchup: timeout 57014 sul riepilogo lacune.

Difetto riprodotto (run reali FALLITE: 36258896621 26/09 17:24Z, 36338805869 27/09 17:56Z,
event=schedule; run VERDI: 36301939261 27/09, 36390583106 28/09, event=workflow_run):
season_gaps.riepilogo_lacune (chiamata da seasons_catchup.esegui_catchup:590) non gestiva
l'eccezione APIError code=57014 (statement_timeout, misurato 2 min sul progetto Supabase
dqbwaocvlzbxfrpacsac, vedi AUDIT_2026-09-28/CANTIERE_E_CATCHUP_57014.md): un blocco lento
per il carico del momento (non per un bug nei dati) uccideva l'intera run con un traceback
non gestito, invece di degradare la sola lega-stagione lenta e proseguire con le altre
(ordine dell'utente: "il catchup non deve MAI morire per un timeout di riepilogo").

Nessun DB, nessuna rete. Finti con chiavi e tipi del vero:
- postgrest.exceptions.APIError vero: str() = "{'message': 'canceling statement due to
  statement timeout', 'code': '57014', 'hint': None, 'details': None}" (visto nel log reale
  della run 36258896621, season_gaps.py riga 237). Qui riprodotto con RuntimeError con lo
  STESSO messaggio (season_gaps._e_statement_timeout guarda solo str(err), come il codice
  vero: _e_funzione_mancante fa lo stesso con RuntimeError negli altri test del repo).
- client supabase-py: rpc(nome, params).execute() -> .data (lista di dict con le colonne
  vere di season_gaps_summary: league_id, season_year, tabella, stato, n).
- Per il test end-to-end si riusa il mondo di test_backfill_automatico_2026_09_25.py
  (stesso FintoDB/FintoServer/FintoClient degli altri test del catchup): si intercetta SOLO
  db.rpc (attributo di istanza, nessuna modifica al file condiviso) per far fallire con
  57014 le chiamate che contengono la lega-stagione "maledetta".
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Tuple

import pytest

os.environ["SUPABASE_URL"] = "http://127.0.0.1:9"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "x"
os.environ["SUPABASE_KEY"] = "x"
os.environ["API_FOOTBALL_KEY"] = "x"

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import season_aggregates as sa  # noqa: E402
import season_gaps as sg  # noqa: E402
import seasons_catchup as sc  # noqa: E402
from test_backfill_automatico_2026_09_25 import (  # noqa: E402,F401  (mondo e' una fixture)
    OGGI, FintoClient, coverage, mondo, quota_per,
)

MSG_57014 = ("{'message': 'canceling statement due to statement timeout', "
            "'code': '57014', 'hint': None, 'details': None}")


# ===========================================================================
# Parte A - unit: season_gaps.riepilogo_lacune, finto minimale (solo season_gaps_summary)
# ===========================================================================
class _RespPura:
    def __init__(self, data: Any) -> None:
        self.data = data


class _RpcPura:
    def __init__(self, esegui: Any) -> None:
        self._esegui = esegui

    def execute(self) -> _RespPura:
        return self._esegui()


class SbSolo57014:
    """Finto minimale con la SOLA rpc season_gaps_summary: le coppie 'maledette' vanno
    sempre in 57014 (anche da sole, come una lega-stagione davvero pesante sotto carico),
    le altre rispondono con le righe indicate (stesse chiavi di season_gaps_summary vero:
    league_id, season_year, tabella, stato, n)."""

    def __init__(self, maledette: set, righe_per_coppia: Dict[Tuple[int, int], List[Dict[str, Any]]]) -> None:
        self.maledette = set(maledette)
        self.righe = righe_per_coppia
        self.chiamate: List[List[Tuple[int, int]]] = []

    def rpc(self, nome: str, params: Dict[str, Any]) -> _RpcPura:
        assert nome == "season_gaps_summary"
        coppie = list(zip(params["p_league_ids"], params["p_season_years"]))
        self.chiamate.append(coppie)

        def esegui() -> _RespPura:
            if any(c in self.maledette for c in coppie):
                raise RuntimeError(MSG_57014)
            out = []
            for c in coppie:
                for r in self.righe.get(c, []):
                    out.append({"league_id": c[0], "season_year": c[1], **r})
            return _RespPura(out)
        return _RpcPura(esegui)


def _righe_semplici(n_da_chiamare: int) -> List[Dict[str, Any]]:
    return [{"tabella": "_partite", "stato": "ft", "n": 10},
            {"tabella": "_partite", "stato": "tutte", "n": 10},
            {"tabella": "match_events", "stato": "da_chiamare", "n": n_da_chiamare}]


def test_riepilogo_lacune_dimezza_il_blocco_e_isola_la_lega_maledetta():
    """RED prima della correzione: sb.rpc(...) alzava RuntimeError(57014) senza essere
    catturata da riepilogo_lacune -> l'eccezione risaliva fino a main() (non era ne'
    MigrazioneMancante ne' QuotaNonLeggibile) e il processo moriva con un traceback,
    invece di dichiarare la sola lega 999 stagione 2026 come non verificata e proseguire
    con le altre 7."""
    buone = [(i, 2026) for i in range(1, 8)]
    maledetta = (999, 2026)
    coppie = buone + [maledetta]
    righe = {c: _righe_semplici(3) for c in buone}
    sb = SbSolo57014({maledetta}, righe)
    log: List[str] = []

    out, degradate = sg.riepilogo_lacune(sb, coppie, blocco=8, stampa=log.append)

    assert degradate == [maledetta]
    for c in buone:
        assert out[c].n("match_events", ("da_chiamare",)) == 3
        assert out[c].ft_totali == 10
    # la maledetta resta un placeholder VUOTO (mai scambiato per "zero buchi verificati")
    assert out[maledetta].ft_totali == 0
    assert out[maledetta].conteggi == {}
    testo = "\n".join(log)
    assert "57014" in testo and "dimezzo" in testo
    assert "DEGRADATA" in testo and "999" in testo and "2026" in testo
    # dimostra il dimezzamento vero: si parte con tutte e 8, si restringe fino a isolare 999/2026
    assert sb.chiamate[0] == coppie
    assert len(sb.chiamate) > 1
    assert [maledetta] in sb.chiamate


def test_riepilogo_lacune_nessuna_lega_maledetta_un_solo_blocco_nessun_dimezzamento():
    """Controprova: senza 57014 il comportamento e' quello di sempre (un blocco, zero
    dimezzamenti, nessuna lega-stagione degradata)."""
    coppie = [(i, 2026) for i in range(1, 5)]
    righe = {c: _righe_semplici(2) for c in coppie}
    sb = SbSolo57014(set(), righe)
    out, degradate = sg.riepilogo_lacune(sb, coppie, blocco=20, stampa=lambda s: None)
    assert degradate == []
    assert len(sb.chiamate) == 1
    for c in coppie:
        assert out[c].n("match_events", ("da_chiamare",)) == 2


def test_riepilogo_lacune_migrazione_mancante_si_comporta_come_prima():
    """Il ramo MigrazioneMancante (gia' esistente) non deve essere cambiato dalla nuova
    gestione del 57014: resta un'eccezione che risale (fail-loud, gestita da main())."""
    class SbSenzaRpc:
        def rpc(self, nome: str, params: Dict[str, Any]) -> "_RpcErr":
            return _RpcErr()

    class _RpcErr:
        def execute(self) -> None:
            raise RuntimeError("{'code': 'PGRST202', 'message': 'Could not find the function public.season_gaps_summary'}")

    with pytest.raises(sg.MigrazioneMancante):
        sg.riepilogo_lacune(SbSenzaRpc(), [(1, 2026)], stampa=lambda s: None)


# ===========================================================================
# Parte B - integrazione: seasons_catchup.esegui_catchup non muore piu' per 57014
# ===========================================================================
MALEDETTA = (999, 2026)
BUONA = (135, 2026)


def _rpc_con_57014(db: Any, maledette: set) -> None:
    """Intercetta SOLO db.rpc (attributo di istanza): nessuna modifica al FintoDB
    condiviso da test_backfill_automatico_2026_09_25.py."""
    originale = db.rpc

    class _RpcErrore:
        def execute(self) -> None:
            raise RuntimeError(MSG_57014)

    def patched(nome: str, params: Dict[str, Any]) -> Any:
        if nome == "season_gaps_summary":
            coppie = list(zip(params["p_league_ids"], params["p_season_years"]))
            if any(c in maledette for c in coppie):
                return _RpcErrore()
        return originale(nome, params)
    db.rpc = patched


def test_esegui_catchup_non_muore_per_57014_degrada_la_lega_e_finisce_il_giro(mondo):
    db, server = mondo
    db.t["api_coverage_by_season"] += [coverage(*BUONA), coverage(*MALEDETTA)]
    for fid in (1, 2):
        db.partita(fid, *BUONA)
    for fid in (901, 902):
        db.partita(fid, *MALEDETTA)
    _rpc_con_57014(db, {MALEDETTA})
    client = FintoClient(server)
    q = quota_per(db, server, client)
    righe: List[str] = []

    ris = sc.esegui_catchup(db, client, q, None, env={"CATCHUP_LEGHE_PRIORITARIE": "135"},
                            oggi=OGGI, stampa=righe.append)

    # non e' morto: e' arrivato al referto finale (prova diretta: c'e' l'ultima riga del referto)
    testo = "\n".join(righe)
    assert "DB SENZA BUCHI" in testo or "BUCHI APERTI" in testo
    # la lega maledetta e' dichiarata degradata, non un errore
    assert ris.degradate_timeout == [MALEDETTA]
    assert ris.errori == []
    assert ris.codice == 0
    assert "57014" in testo and "DEGRADATA" in testo and "999" in testo
    # NESSUNO STATO FALSO scritto per la lega maledetta: puo' comparire una riga (il
    # contatore di osservabilita' R-CATCHUP-3), ma MAI un "buchi_aperti"/coverage/meta
    # v2 fabbricato da un Lacune vuoto (sarebbe "zero buchi" mentendo).
    righe_maledetta = [r for r in db.t["season_backfill_state"]
                       if r["league_id"] == MALEDETTA[0] and r["season_year"] == MALEDETTA[1]]
    for r in righe_maledetta:
        sj = r["stats_json"]
        assert "buchi_aperti" not in sj
        assert (sj.get("meta") or {}).get("version") != "v2"
        assert "degradato_57014" in sj
    # la lega buona invece e' stata verificata E lavorata normalmente (nessun impatto
    # dalla lega maledetta, che e' stata saltata a monte, prima della coda di lavoro)
    assert ris.fatte == [BUONA]
    stato_buono = next(r for r in db.t["season_backfill_state"]
                       if r["league_id"] == BUONA[0] and r["season_year"] == BUONA[1])
    assert stato_buono["status"] in ("completed", "in_progress")


def test_esegui_catchup_senza_57014_comportamento_identico_a_prima(mondo):
    """Controprova: senza nessuna lega maledetta il referto non menziona degradate e
    ris.degradate_timeout resta vuoto (nessuna regressione sul percorso normale)."""
    db, server = mondo
    db.t["api_coverage_by_season"] += [coverage(*BUONA)]
    for fid in (1, 2):
        db.partita(fid, *BUONA)
    client = FintoClient(server)
    q = quota_per(db, server, client)
    righe: List[str] = []
    ris = sc.esegui_catchup(db, client, q, None, env={"CATCHUP_LEGHE_PRIORITARIE": "135"},
                            oggi=OGGI, stampa=righe.append)
    assert ris.degradate_timeout == []
    assert "DEGRADATA" not in "\n".join(righe)


# ===========================================================================
# Parte C - verifica del coordinatore 28/09: due mutazioni sopravvissute (M2, M3)
# ===========================================================================
# M3: _e_statement_timeout deve riconoscere SOLO il 57014, non "qualunque errore".
def test_e_statement_timeout_riconosce_solo_57014_non_qualunque_errore():
    """Falsifica direttamente la mutazione del coordinatore `return True`: se
    _e_statement_timeout tornasse sempre True, TUTTI gli errori (permesso negato, rete,
    500 generico) verrebbero trattati come timeout e degradati in silenzio invece di
    risalire come l'errore vero che sono."""
    assert sg._e_statement_timeout(RuntimeError(MSG_57014))
    assert sg._e_statement_timeout(RuntimeError("statement timeout"))
    assert not sg._e_statement_timeout(
        RuntimeError("{'message': 'permission denied for table matches', 'code': '42501', "
                    "'hint': None, 'details': None}"))
    assert not sg._e_statement_timeout(
        RuntimeError("{'message': 'Internal Server Error', 'code': '500', 'hint': None, 'details': None}"))
    assert not sg._e_statement_timeout(ConnectionError("Connection refused"))


def test_riepilogo_lacune_errore_non_57014_si_propaga_come_prima():
    """Un errore VERO (permesso negato) non deve mai finire fra le degradate: deve
    risalire esattamente come prima (fail-loud), non essere inghiottito in silenzio."""
    class SbErrorePermesso:
        def rpc(self, nome: str, params: Dict[str, Any]) -> Any:
            class _R:
                def execute(self_inner) -> None:
                    raise RuntimeError("{'message': 'permission denied for table matches', "
                                      "'code': '42501', 'hint': None, 'details': None}")
            return _R()
    with pytest.raises(RuntimeError, match="42501"):
        sg.riepilogo_lacune(SbErrorePermesso(), [(1, 2026)], stampa=lambda s: None)


def test_riepilogo_lacune_errore_di_rete_si_propaga_come_prima():
    class SbRete:
        def rpc(self, nome: str, params: Dict[str, Any]) -> Any:
            class _R:
                def execute(self_inner) -> None:
                    raise ConnectionError("Connection refused")
            return _R()
    with pytest.raises(ConnectionError):
        sg.riepilogo_lacune(SbRete(), [(1, 2026)], stampa=lambda s: None)


# M2: una lega-stagione degradata NON deve mai ottenere uno stato scritto ne' entrare
# nella coda di lavoro. Il test precedente (BUONA/MALEDETTA, entrambe "vive") non basta:
# per una coppia "viva" con Lacune vuoto (placeholder mai popolato) lo skip preesistente
# `if viva and lac.ft_totali == 0: continue` maschera la mutazione `if False and k in
# degradate_set:` (il risultato osservabile e' lo stesso con o senza lo skip dedicato).
# Serve una coppia PASSATA (non viva): li' quello skip non si applica, quindi la mutazione
# del coordinatore scriverebbe uno stato (status derivato da un Lacune VUOTO, quindi
# "in_progress" con 0 buchi noti: falso) invece di non scrivere nulla.
LEGA_PASSATA_MALEDETTA = (888, 2018)


def test_esegui_catchup_lega_passata_degradata_niente_stato_scritto_niente_coda(mondo):
    db, server = mondo
    riga = coverage(*LEGA_PASSATA_MALEDETTA, current=False, fine="2019-05-30", inizio="2018-08-20")
    db.t["api_coverage_by_season"] += [riga]
    for fid in (7001, 7002, 7003):
        db.partita(fid, *LEGA_PASSATA_MALEDETTA, giorni_fa=3000)   # partite vecchie, davvero passate
    _rpc_con_57014(db, {LEGA_PASSATA_MALEDETTA})
    client = FintoClient(server)
    q = quota_per(db, server, client)
    righe: List[str] = []

    ris = sc.esegui_catchup(db, client, q, None, env={}, oggi=OGGI, stampa=righe.append)

    assert ris.degradate_timeout == [LEGA_PASSATA_MALEDETTA]
    # nessuna riga con uno stato "vero" (v2/buchi_aperti) per la lega passata degradata:
    # puo' esistere SOLO la riga del contatore R-CATCHUP-3 (senza meta v2 ne' buchi_aperti)
    righe_lega = [r for r in db.t["season_backfill_state"]
                 if r["league_id"] == LEGA_PASSATA_MALEDETTA[0] and r["season_year"] == LEGA_PASSATA_MALEDETTA[1]]
    for r in righe_lega:
        assert "buchi_aperti" not in r["stats_json"]
        assert (r["stats_json"].get("meta") or {}).get("version") != "v2"
    # non e' entrata nella coda di lavoro (non lavorata, non "rimasta": semplicemente saltata)
    assert LEGA_PASSATA_MALEDETTA not in ris.fatte
    assert LEGA_PASSATA_MALEDETTA not in ris.aperto_dal


# ===========================================================================
# Parte D - Punto 3 del coordinatore: le degradate non restano mute per sempre
# ===========================================================================
def test_degradata_persistente_oltre_la_soglia_diventa_visibile_e_rossa(mondo):
    """R-CATCHUP-3: la stessa lega-stagione degradata per PIU' giorni consecutivi (oltre
    BACKFILL_BUCHI_MAX_GIORNI, default 3) deve diventare visibile nel referto ("DEGRADATA
    PERSISTENTE") e far uscire la run con codice 1 (non piu' "non e' un errore")."""
    db, server = mondo
    db.t["api_coverage_by_season"] += [coverage(*MALEDETTA)]
    for fid in (901, 902):
        db.partita(fid, *MALEDETTA)
    _rpc_con_57014(db, {MALEDETTA})
    client = FintoClient(server)
    q = quota_per(db, server, client)

    risultati = []
    for _giorno in range(4):                       # 4 giri consecutivi, sempre la stessa maledetta
        righe: List[str] = []
        ris = sc.esegui_catchup(db, client, q, None, env={}, oggi=OGGI, stampa=righe.append)
        risultati.append((ris, "\n".join(righe)))

    consecutivi_per_giro = [ris.degradate_consecutivi.get(MALEDETTA) for ris, _ in risultati]
    assert consecutivi_per_giro == [1, 2, 3, 4]
    # primi 3 giri: non ancora persistente (soglia di default = 3, si scatta a > 3)
    for ris, testo in risultati[:3]:
        assert ris.codice == 0
        assert "DEGRADATA PERSISTENTE" not in testo
    # 4o giro: consecutivi=4 > 3 -> visibile e rossa
    ris4, testo4 = risultati[3]
    assert ris4.codice == 1
    assert "DEGRADATA PERSISTENTE" in testo4 and "999" in testo4 and "4 giorni" in testo4


def test_degradata_recupera_il_contatore_si_azzera(mondo):
    """Controprova: se la lega-stagione torna verificabile, il giro successivo NON e'
    piu' fra le degradate e il contatore sparisce (nessuna 'persistente' eterna)."""
    db, server = mondo
    db.t["api_coverage_by_season"] += [coverage(*MALEDETTA)]
    for fid in (901, 902):
        db.partita(fid, *MALEDETTA)
    _rpc_con_57014(db, {MALEDETTA})
    client = FintoClient(server)
    q = quota_per(db, server, client)
    ris1 = sc.esegui_catchup(db, client, q, None, env={}, oggi=OGGI, stampa=lambda s: None)
    assert ris1.degradate_consecutivi.get(MALEDETTA) == 1

    db.rpc = db.__class__.rpc.__get__(db)           # tolta la maledizione: torna il vero rpc
    ris2 = sc.esegui_catchup(db, client, q, None, env={}, oggi=OGGI, stampa=lambda s: None)
    assert ris2.degradate_timeout == []
    stato = next(r for r in db.t["season_backfill_state"]
                if r["league_id"] == MALEDETTA[0] and r["season_year"] == MALEDETTA[1])
    assert "degradato_57014" not in stato["stats_json"]      # azzerato: verifica riuscita


# ===========================================================================
# Parte E - stessa gestione estesa a season_aggregates.py (perimetro allargato 28/09)
# ===========================================================================
class _RespAgg:
    def __init__(self, data: Any) -> None:
        self.data = data


class SbAggregati57014:
    """Finto minimale per season_aggregates_summary: le coppie 'maledette' vanno
    sempre in 57014, le altre rispondono vuote (nessuna riga = tutto 'mancante')."""

    def __init__(self, maledette: set) -> None:
        self.maledette = set(maledette)
        self.chiamate: List[List[Tuple[int, int]]] = []

    def rpc(self, nome: str, params: Dict[str, Any]) -> Any:
        assert nome == "season_aggregates_summary"
        coppie = list(zip(params["p_league_ids"], params["p_season_years"]))
        self.chiamate.append(coppie)

        def esegui() -> _RespAgg:
            if any(c in self.maledette for c in coppie):
                raise RuntimeError(MSG_57014)
            return _RespAgg([])
        class _R:
            def execute(self_inner) -> _RespAgg:
                return esegui()
        return _R()


def test_season_aggregates_leggi_info_dimezza_e_degrada_su_57014():
    coppie = [(i, 2026) for i in range(1, 5)] + [MALEDETTA]
    sb = SbAggregati57014({MALEDETTA})
    log: List[str] = []
    info, degradate = sa.leggi_info(sb, coppie, blocco=5, stampa=log.append)
    assert degradate == [MALEDETTA]
    assert MALEDETTA in info and info[MALEDETTA] == {}     # nessuna info inventata
    assert any("57014" in r for r in log) and any("DEGRADATA" in r for r in log)


def test_season_aggregates_leggi_info_errore_non_57014_si_propaga():
    class SbErrore:
        def rpc(self, nome: str, params: Dict[str, Any]) -> Any:
            class _R:
                def execute(self_inner) -> None:
                    raise RuntimeError("{'code': '42501', 'message': 'permission denied'}")
            return _R()
    with pytest.raises(RuntimeError, match="42501"):
        sa.leggi_info(SbErrore(), [(1, 2026)], stampa=lambda s: None)


def test_season_aggregates_attacca_non_tocca_gli_aggregati_della_degradata():
    """attacca() non deve MAI scrivere lac.aggregati per una lega-stagione degradata
    (sarebbe 'tutto mancante': falso, e farebbe richiamare l'API inutilmente)."""
    sb = SbAggregati57014({MALEDETTA})
    lac_maledetta = sg.Lacune(MALEDETTA[0], MALEDETTA[1])
    lac_buona = sg.Lacune(1, 2026)
    lacune = {MALEDETTA: lac_maledetta, (1, 2026): lac_buona}
    righe_cov = {MALEDETTA: coverage(*MALEDETTA), (1, 2026): coverage(1, 2026)}
    degradate = sa.attacca(sb, lacune, righe_cov, {}, adesso=sa.adesso(), stampa=lambda s: None)
    assert degradate == [MALEDETTA]
    assert lac_maledetta.aggregati == {}                    # intoccato
    assert lac_buona.aggregati != {}                         # la buona e' stata calcolata normalmente
