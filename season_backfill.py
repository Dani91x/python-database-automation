"""season_backfill.py - Elaborazione di UNA lega-stagione (25/09/2026).

Mattone unico usato dall'orchestratore a mano (league_orchestrator.py) e dal
recupero giornaliero (seasons_catchup.py): stessi controlli, stesso stato.

Sequenza (mai a meta' partita, ripartibile):
  1. lacune dai DATI (season_gaps.lacune_stagione, 1 RPC);
  2. costo stimato = partite/endpoint da chiamare + 1 /fixtures (se c'e' lavoro
     per-partita e la stagione non e' viva nel recupero) + aggregati DA FARE
     (season_aggregates: solo quelli mancanti/da aggiornare/in errore, per cadenza);
  3. controllo quota PRIMA (margine >= costo, vedi `decidi`);
  4. /fixtures della stagione (1 chiamata: allinea `matches`, anche partite
     saltate da un Daily fallito), ricalcolo lacune, per-fixture SOLO sulle
     mancanti, aggregati;
  5. ricalcolo lacune e scrittura di season_backfill_state (stato derivato).
Nessuna chiamata API se non manca nulla.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Dict, Optional

import season_aggregates as sa
import season_gaps as sg

logger = logging.getLogger(__name__)

STIMA_PARTITE_STAGIONE_VUOTA = 380   # solo per stimare il costo di una stagione mai caricata


@dataclass
class Piano:
    league_id: int
    season_year: int
    coverage_row: Dict[str, Any]
    lacune: sg.Lacune
    flags: Dict[str, bool]
    serve_fixtures: bool           # stagione iniziata senza partite in DB (mai caricata)
    chiamate_partite: int
    chiamate_fisse: int
    stato_attuale: Optional[str]
    stato_calcolato: str
    chiamate_aggregati: int = 0

    @property
    def costo(self) -> int:
        return self.chiamate_partite + self.chiamate_fisse + self.chiamate_aggregati

    @property
    def c_e_lavoro(self) -> bool:
        return self.costo > 0


@dataclass
class Esito:
    league_id: int
    season_year: int
    eseguita: bool = False
    chiamate: int = 0
    fermato_per: Optional[str] = None
    errore: Optional[str] = None
    stato: Optional[str] = None
    buchi_aperti: int = 0
    stats: Dict[str, Any] = field(default_factory=dict)
    lacune_dopo: Optional[sg.Lacune] = None


def pianifica(sb: Any, coverage_row: Dict[str, Any], stato_prec: Optional[Dict[str, Any]] = None,
              includi_mai_caricate: bool = True, oggi: Optional[date] = None,
              fisse_su_stagione_viva: bool = True) -> Piano:
    """fisse_su_stagione_viva=False (recupero giornaliero): sulle stagioni vive
    NON si rifa' /fixtures (le partite le scrive il Daily). Gli aggregati NON sono
    piu' "fissi": si chiamano solo quelli DA FARE secondo le lacune degli
    aggregati (season_aggregates), anche sulle stagioni vive (25/09: il Daily non
    li ha MAI chiamati, vedi referto par. 9)."""
    league_id, season_year = int(coverage_row["league_id"]), int(coverage_row["season_year"])
    lac = sg.lacune_stagione(sb, league_id, season_year)
    flags = sg.flag_per_fixture(coverage_row)
    n_attivi = sum(1 for v in flags.values() if v)
    serve_fixtures = (includi_mai_caricate and lac.partite_totali == 0
                      and sg.stagione_iniziata(coverage_row, oggi))
    chiamate_partite = lac.chiamate_per_fixture(flags)
    if serve_fixtures:
        # stagione passata: le quote delle sue partite sono fuori dalla finestra API (7 gg) e non si chiamano
        if flags.get("odds") and not sg.e_corrente_o_recente(coverage_row, oggi):
            n_attivi -= 1
        chiamate_partite = STIMA_PARTITE_STAGIONE_VUOTA * n_attivi
    fisse = 1 if (chiamate_partite > 0 or serve_fixtures) else 0
    if not fisse_su_stagione_viva and sg.e_corrente_o_recente(coverage_row, oggi):
        fisse = 0
    k = (league_id, season_year)
    sa.attacca(sb, {k: lac}, {k: coverage_row}, {k: stato_prec or {}}, sa.adesso())
    return Piano(league_id, season_year, coverage_row, lac, flags, serve_fixtures,
                 chiamate_partite, fisse, (stato_prec or {}).get("status"),
                 sg.calcola_stato(coverage_row, lac, oggi), lac.chiamate_aggregati())


def decidi(piano: Piano, quota: Any) -> str:
    """'niente' | 'procedo' | 'procedo_a_spezzoni' | 'mi_fermo'.
    - margine >= costo -> procedo;
    - costo > capacita' di un giorno intero (limit_day - riserva) e margine per
      almeno una partita -> procedo a spezzoni (fermo a fine partita quando il
      margine finisce; domani si riprende da cio' che manca). Senza questa regola
      una lega-stagione enorme non partirebbe mai;
    - altrimenti mi fermo (la lega-stagione resta in coda per domani)."""
    if not piano.c_e_lavoro:
        return "niente"
    margine = quota.margine()
    if margine >= piano.costo:
        return "procedo"
    if piano.costo > quota.capacita_giornaliera() and margine >= piano.chiamate_fisse + 5:
        return "procedo_a_spezzoni"
    return "mi_fermo"


def _aggregati(sb: Any, client: Any, quota: Any, piano: Piano) -> Dict[str, Dict[str, Any]]:
    """Solo gli aggregati DA FARE, con il client condiviso (chiamate contate nella
    quota), controllo quota prima di ciascuno. -> {nome: {at, esito}}."""
    tentativi: Dict[str, Dict[str, Any]] = {}
    for nome in piano.lacune.agg_da_fare():
        if quota is not None and not quota.copre(sa.COSTO[nome]):
            logger.warning("Quota: aggregato %s rinviato (margine %s)", nome, quota.margine())
            break
        try:
            esito = sa.esegui_aggregato(sb, client, nome, piano.league_id, piano.season_year)
        except Exception as e:
            logger.error("aggregato %s lega %s stagione %s: %s", nome, piano.league_id, piano.season_year, e)
            esito = "errore"
        tentativi[nome] = {"at": sa.adesso().isoformat(timespec="seconds"), "esito": esito}
    return tentativi


def esegui(sb: Any, client: Any, quota: Any, piano: Piano, stato_prec: Optional[Dict[str, Any]],
           fonte: str, deve_fermarsi: Optional[Callable[[], Optional[str]]] = None,
           oggi: Optional[date] = None) -> Esito:
    """Esegue il piano (chi chiama ha gia' deciso 'procedo'/'procedo_a_spezzoni')."""
    from fixtures_backfill import backfill_fixtures_for_league_season
    from per_fixture_backfill import backfill_per_fixture_for_league_season

    lid, sy = piano.league_id, piano.season_year
    es = Esito(lid, sy, eseguita=True)
    prima = int(getattr(client, "richieste_http", 0) or 0)
    fisse_fatte = 0
    con_fisse = piano.chiamate_fisse > 0
    try:
        # 1) partite della stagione (1 chiamata): allinea matches
        if con_fisse:
            backfill_fixtures_for_league_season(lid, sy)
            fisse_fatte += 1
        lac = sg.lacune_stagione(sb, lid, sy)
        # 2) per-fixture SOLO sulle mancanti, SOLO endpoint con flag True
        st = backfill_per_fixture_for_league_season(
            lid, sy, lacune=lac, coverage=piano.flags, client=client, quota=quota,
            deve_fermarsi=deve_fermarsi, registro_obbligatorio=True) or {}
        es.fermato_per = st.get("fermato_per")
        # 3) aggregati DA FARE (solo se non ci si e' fermati per quota)
        agg: Dict[str, Any] = {}
        if es.fermato_per != "quota":
            agg = _aggregati(sb, client, quota, piano)
        es.stats = {"per_fixture": st, "aggregati": agg}
    except sg.MigrazioneMancante:
        raise
    except Exception as e:
        es.errore = f"{type(e).__name__}: {e}"
        logger.error("lega %s stagione %s: ERRORE %s", lid, sy, es.errore)
    # chiamate: quelle del client condiviso (per-partita e aggregati) + /fixtures (client suo)
    es.chiamate = int(getattr(client, "richieste_http", 0) or 0) - prima + fisse_fatte
    if hasattr(quota, "aggiungi_chiamate_esterne"):
        quota.aggiungi_chiamate_esterne(fisse_fatte)
    # 4) stato DERIVATO dai dati dopo il lavoro
    lac_dopo = sg.lacune_stagione(sb, lid, sy)
    tentativi = (es.stats.get("aggregati") or {})
    prec_agg = {**(stato_prec or {})}
    prec_agg["stats_json"] = {**((stato_prec or {}).get("stats_json") or {})}
    prec_agg["stats_json"]["aggregati_tentativi"] = {
        **(prec_agg["stats_json"].get("aggregati_tentativi") or {}), **tentativi}
    k = (lid, sy)
    sa.attacca(sb, {k: lac_dopo}, {k: piano.coverage_row}, {k: prec_agg}, sa.adesso())
    es.stato = sg.calcola_stato(piano.coverage_row, lac_dopo, oggi)
    es.buchi_aperti = lac_dopo.aperti(piano.flags)
    esito_json = {"chiamate_fatte": es.chiamate, "fermato_per": es.fermato_per, "errore": es.errore,
                  "vuoti": (es.stats.get("per_fixture") or {}).get("vuoti", 0),
                  "errori_api": (es.stats.get("per_fixture") or {}).get("errori_api", 0),
                  "aggregati": es.stats.get("aggregati", {})}
    sg.scrivi_stato(sb, lid, sy, es.stato,
                    sg.costruisci_stats_json(piano.coverage_row, lac_dopo, stato_prec, fonte, esito_json, oggi,
                                             tentativi_aggregati=tentativi))
    es.lacune_dopo = lac_dopo
    return es


def scrivi_stato_senza_lavoro(sb: Any, piano: Piano, stato_prec: Optional[Dict[str, Any]], fonte: str,
                              oggi: Optional[date] = None) -> None:
    """Stato derivato anche per le lega-stagioni senza lavoro (riapre i
    `completed` falsi, chiude quelle finite e piene): zero chiamate API."""
    sg.scrivi_stato(sb, piano.league_id, piano.season_year, piano.stato_calcolato,
                    sg.costruisci_stats_json(piano.coverage_row, piano.lacune, stato_prec, fonte, None, oggi))


def riga_log_dopo(es: Esito, quota: Any, prossima_costo: Optional[int]) -> str:
    st = quota.stato
    contatore = f"{st.current}/{st.limit_day}" if st else "?"
    if prossima_costo is None:
        decisione = "fine coda"
    else:
        decisione = "continuo" if quota.margine() >= prossima_costo else "mi fermo"
    return (f"lega {es.league_id} stagione {es.season_year}: chiamate fatte {es.chiamate}, "
            f"contatore API ora {contatore}, margine {quota.margine()}, "
            f"prossima costa ~{prossima_costo if prossima_costo is not None else 0} -> {decisione}")

