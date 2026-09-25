"""seasons_catchup.py - Recupero giornaliero dei BUCHI di dati (25/09/2026).

Ordine dell'utente: il DB sempre aggiornato e SENZA BUCHI, la quota API mai
superata, tutte le leghe (anche nuove, anche nel 2027) in automatico.

Parte (action `seasons_catchup.yml`) DOPO il leagues mapper (che aggiorna i
flag di coverage), che a sua volta parte dopo il Daily. Passi:
  1. pre-controlli fail-loud: migrazione season_gaps_2026-09-25 applicata,
     contatore quota leggibile (/status o api_call_log);
  2. verifica delle lacune dai DATI (RPC season_gaps_summary a blocchi):
       - TUTTE le stagioni vive (current o finite da <= 30 gg) con almeno un
         flag per-partita True: ogni giorno;
       - stagioni passate: a rotazione, al massimo CATCHUP_MAX_VERIFICHE_PASSATE
         per notte (prima quelle gia' note con buchi, poi le mai verificate);
     e scrittura dello stato derivato in season_backfill_state;
  3. coda: P1 stagioni vive delle leghe usate dai bot (atlante hazard v3, 21
     leghe), P2 altre stagioni vive per numero di mancanze (decrescente), P3
     stagioni passate con buchi (dalla piu' economica);
  4. per ogni lega-stagione: controllo quota PRIMA, lavoro solo sulle partite
     mancanti, ricalcolo quota DOPO, stop a fine partita/lega-stagione;
  5. REFERTO BUCHI e uscita:
       0  = lavoro fatto o fermato per quota/tempo/action concorrente (dichiarato);
       1  = una lega-stagione in errore, oppure un buco aperto da piu' di
            BACKFILL_BUCHI_MAX_GIORNI giorni NONOSTANTE il budget (con la causa);
       2  = pre-controlli falliti (migrazione mancante, quota non leggibile).
"""
from __future__ import annotations

import json
import logging
import math
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

import season_backfill as sbk
import season_gaps as sg
from api_quota import GestoreQuota, QuotaNonLeggibile

logger = logging.getLogger("seasons_catchup")

ATLANTE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "Betfair", "omega", "data", "hazard_atlas_v3.json")
WORKFLOW_ESCLUSIVI_DEFAULT = ("daily_yesterday_backfill.yml", "today_predictions_backfill.yml",
                              "predictions_results_backfill.yml", "retrain_models.yml")


def _env_int(nome: str, default: int, env: Optional[Dict[str, str]] = None) -> int:
    env = os.environ if env is None else env
    grezzo = (env.get(nome) or "").strip()
    return int(grezzo) if grezzo else default


# ---------------------------------------------------------------------------
# Leghe prioritarie (usate dai bot)
# ---------------------------------------------------------------------------
def leghe_prioritarie(env: Optional[Dict[str, str]] = None, percorso: str = ATLANTE) -> Set[int]:
    """Fonte: le leghe dell'atlante hazard v3 (Betfair/omega/data/hazard_atlas_v3.json,
    chiave `by_league`: 21 leghe usate dai bot Omega/scalper). Override con
    CATCHUP_LEGHE_PRIORITARIE="135,39,...". File assente -> insieme vuoto + avviso."""
    env = os.environ if env is None else env
    grezzo = (env.get("CATCHUP_LEGHE_PRIORITARIE") or "").strip()
    if grezzo:
        return {int(x) for x in grezzo.replace(" ", "").split(",") if x}
    try:
        with open(percorso, encoding="utf-8") as f:
            return {int(k) for k in (json.load(f).get("by_league") or {})}
    except (OSError, ValueError, TypeError) as e:
        print(f"[CATCHUP] AVVISO: leghe prioritarie non lette da {percorso} ({e}): nessuna P1.")
        return set()


# ---------------------------------------------------------------------------
# Action concorrenti (stessa quota, stesso DB)
# ---------------------------------------------------------------------------
class ControlloConcorrenza:
    """Chiede a GitHub se Daily / Today / Results sono in corso o in coda.
    Senza GITHUB_TOKEN (lancio locale) il controllo e' spento, con avviso."""

    def __init__(self, env: Optional[Dict[str, str]] = None, http_get: Any = None,
                 intervallo_sec: int = 120) -> None:
        env = os.environ if env is None else env
        self.token = (env.get("GITHUB_TOKEN") or "").strip()
        self.repo = (env.get("GITHUB_REPOSITORY") or "").strip()
        grezzo = (env.get("CATCHUP_WORKFLOW_ESCLUSIVI") or "").strip()
        self.workflow = tuple(x for x in grezzo.split(",") if x) if grezzo else WORKFLOW_ESCLUSIVI_DEFAULT
        self.http_get = http_get
        self.intervallo = intervallo_sec
        self._ultimo = 0.0
        self._ultimo_esito: Optional[str] = None
        self.attivo = bool(self.token and self.repo)
        if not self.attivo:
            print("[CATCHUP] AVVISO: GITHUB_TOKEN/GITHUB_REPOSITORY assenti: controllo delle action concorrenti SPENTO.")

    def in_corso(self, forza: bool = False) -> Optional[str]:
        if not self.attivo:
            return None
        if not forza and time.time() - self._ultimo < self.intervallo:
            return self._ultimo_esito
        import requests
        get = self.http_get or requests.get
        esito = None
        for wf in self.workflow:
            for stato in ("in_progress", "queued"):
                url = f"https://api.github.com/repos/{self.repo}/actions/workflows/{wf}/runs"
                try:
                    r = get(url, params={"status": stato, "per_page": 1},
                            headers={"Authorization": f"Bearer {self.token}",
                                     "Accept": "application/vnd.github+json"}, timeout=15)
                    if getattr(r, "status_code", 0) == 200 and int((r.json() or {}).get("total_count") or 0) > 0:
                        esito = f"action concorrente {stato}: {wf}"
                        break
                except Exception as e:
                    print(f"[CATCHUP] AVVISO: controllo {wf} non riuscito ({e})")
            if esito:
                break
        self._ultimo, self._ultimo_esito = time.time(), esito
        return esito


# ---------------------------------------------------------------------------
# Candidati e coda
# ---------------------------------------------------------------------------
@dataclass
class Voce:
    row: Dict[str, Any]
    lacune: sg.Lacune
    priorita: int
    stato_prec: Optional[Dict[str, Any]]

    @property
    def chiave(self) -> Tuple[int, int]:
        return int(self.row["league_id"]), int(self.row["season_year"])

    @property
    def flags(self) -> Dict[str, bool]:
        return sg.flag_per_fixture(self.row)

    @property
    def chiamate(self) -> int:
        return self.lacune.chiamate_per_fixture(self.flags)


def seleziona_candidati(coperture: List[Dict[str, Any]], stati: Dict[Tuple[int, int], Dict[str, Any]],
                        max_passate: int, oggi: date) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, int]]:
    vive: List[Dict[str, Any]] = []
    passate_note: List[Dict[str, Any]] = []
    passate_nuove: List[Dict[str, Any]] = []
    conti = {"passate_mai_caricate": 0, "passate_non_verificate": 0}
    for r in coperture:
        if not any(sg.flag_per_fixture(r).values()) or not sg.stagione_iniziata(r, oggi):
            continue
        k = (int(r["league_id"]), int(r["season_year"]))
        if sg.e_corrente_o_recente(r, oggi):
            vive.append(r)
            continue
        st = stati.get(k) or {}
        sj = st.get("stats_json") or {}
        v2 = (sj.get("meta") or {}).get("version") == "v2"
        if v2 and st.get("status") == "completed":
            continue
        if v2 and str((sj.get("fixtures") or {}).get("ft_count") or "0") == "0":
            conti["passate_mai_caricate"] += 1          # 0 partite in DB: solo orchestratore a mano
            continue
        (passate_note if v2 else passate_nuove).append(r)
    passate_nuove.sort(key=lambda r: -int(r["season_year"]))
    passate = (passate_note + passate_nuove)[:max_passate]
    conti["passate_non_verificate"] = len(passate_note) + len(passate_nuove) - len(passate)
    return vive, passate, conti


def costruisci_coda(voci: List[Voce]) -> List[Voce]:
    """P1 (bot, vive) -> P2 (altre vive, piu' mancanze prima) -> P3 (passate, piu' economiche prima)."""
    con_lavoro = [v for v in voci if v.chiamate > 0]
    p1 = sorted([v for v in con_lavoro if v.priorita == 1], key=lambda v: (-v.chiamate, v.chiave))
    p2 = sorted([v for v in con_lavoro if v.priorita == 2], key=lambda v: (-v.chiamate, v.chiave))
    p3 = sorted([v for v in con_lavoro if v.priorita == 3], key=lambda v: (v.chiamate, v.chiave))
    return p1 + p2 + p3


# ---------------------------------------------------------------------------
# Esecuzione
# ---------------------------------------------------------------------------
@dataclass
class Risultato:
    fatte: List[Tuple[int, int]] = field(default_factory=list)
    rimaste: List[Tuple[int, int]] = field(default_factory=list)
    errori: List[str] = field(default_factory=list)
    fermato_per: Optional[str] = None
    chiamate: int = 0
    lacune_dopo: Dict[Tuple[int, int], sg.Lacune] = field(default_factory=dict)
    aperto_dal: Dict[Tuple[int, int], Optional[str]] = field(default_factory=dict)
    fermate_per: Dict[Tuple[int, int], Optional[str]] = field(default_factory=dict)
    codice: int = 0


def esegui_catchup(sb: Any, client: Any, quota: Any, concorrenza: Any = None,
                   env: Optional[Dict[str, str]] = None, oggi: Optional[date] = None,
                   stampa: Callable[[str], None] = print, orologio: Callable[[], float] = time.time) -> Risultato:
    env = os.environ if env is None else env
    oggi = oggi or datetime.now(timezone.utc).date()
    max_min = _env_int("CATCHUP_MAX_MINUTI", 150, env)
    max_passate = _env_int("CATCHUP_MAX_VERIFICHE_PASSATE", 150, env)
    max_giorni = _env_int("BACKFILL_BUCHI_MAX_GIORNI", 3, env)
    t0 = orologio()
    ris = Risultato()

    # 1) pre-controlli (fail-loud: li gestisce main)
    sg.verifica_migrazione(sb)
    st = quota.aggiorna()
    stampa(f"[CATCHUP] quota all'avvio: {st.riga()}")

    # 2) verifica lacune dai dati
    prioritarie = leghe_prioritarie(env)
    coperture = sg.leggi_coverage(sb)
    stati = sg.leggi_stati(sb)
    vive, passate, conti = seleziona_candidati(coperture, stati, max_passate, oggi)
    stampa(f"[CATCHUP] candidati: {len(vive)} stagioni vive, {len(passate)} passate da verificare "
           f"(non verificate stanotte: {conti['passate_non_verificate']}, "
           f"passate mai caricate: {conti['passate_mai_caricate']})")
    righe_per_k = {(int(r["league_id"]), int(r["season_year"])): r for r in vive + passate}
    lacune = sg.riepilogo_lacune(sb, list(righe_per_k))
    voci: List[Voce] = []
    stati_da_scrivere: List[Dict[str, Any]] = []
    for k, row in righe_per_k.items():
        lac = lacune[k]
        viva = sg.e_corrente_o_recente(row, oggi)
        if viva and lac.ft_totali == 0:
            continue                                     # nessuna partita FT ancora: nulla da recuperare
        prio = 3 if not viva else (1 if k[0] in prioritarie else 2)
        voce = Voce(row, lac, prio, stati.get(k))
        voci.append(voce)
        sj = sg.costruisci_stats_json(row, lac, voce.stato_prec, "catchup", None, oggi)
        ris.aperto_dal[k] = sj.get("buco_aperto_dal")
        stati_da_scrivere.append({"league_id": k[0], "season_year": k[1],
                                  "status": sg.calcola_stato(row, lac, oggi), "stats_json": sj})
    sg.scrivi_stati(sb, stati_da_scrivere)
    coda = costruisci_coda(voci)
    stampa(f"[CATCHUP] coda: {len(coda)} lega-stagioni con partite da chiamare "
           f"(P1 {sum(1 for v in coda if v.priorita == 1)}, P2 {sum(1 for v in coda if v.priorita == 2)}, "
           f"P3 {sum(1 for v in coda if v.priorita == 3)}), ~{sum(v.chiamate for v in coda)} chiamate per-partita")

    def deve_fermarsi() -> Optional[str]:
        if (orologio() - t0) / 60.0 >= max_min:
            return f"tempo massimo {max_min} min"
        return concorrenza.in_corso() if concorrenza is not None else None

    # 3) lavoro
    for i, voce in enumerate(coda):
        k = voce.chiave
        if ris.fermato_per:
            ris.rimaste.append(k)
            continue
        motivo = concorrenza.in_corso(forza=True) if concorrenza is not None else None
        if (orologio() - t0) / 60.0 >= max_min:
            motivo = f"tempo massimo {max_min} min"
        if motivo:
            ris.fermato_per = motivo
            ris.rimaste.append(k)
            stampa(f"[CATCHUP] STOP prima di lega {k[0]} stagione {k[1]}: {motivo}")
            continue
        try:
            piano = sbk.pianifica(sb, voce.row, voce.stato_prec, includi_mai_caricate=False, oggi=oggi,
                                  fisse_su_stagione_viva=False)
            decisione = sbk.decidi(piano, quota)
            stampa(f"[CATCHUP] P{voce.priorita} lega {k[0]} stagione {k[1]}: costo ~{piano.costo}, "
                   f"margine {quota.margine()} -> {decisione}")
            if decisione == "niente":
                ris.lacune_dopo[k] = piano.lacune
                continue
            if decisione == "mi_fermo":
                ris.fermato_per = "quota"
                ris.rimaste.append(k)
                continue
            es = sbk.esegui(sb, client, quota, piano, voce.stato_prec, "catchup", deve_fermarsi, oggi)
            ris.chiamate += es.chiamate
            ris.fatte.append(k)
            ris.fermate_per[k] = es.fermato_per
            if es.errore:
                ris.errori.append(f"lega {k[0]} stagione {k[1]}: {es.errore}")
            if es.fermato_per and es.fermato_per != "errori_api":
                ris.fermato_per = es.fermato_per         # quota / tempo / action concorrente: stop della run
            ris.lacune_dopo[k] = sg.lacune_stagione(sb, k[0], k[1])
            quota.aggiorna()                               # RICALCOLO dopo ogni lega-stagione
            prossima = coda[i + 1].chiamate if i + 1 < len(coda) else None
            stampa("[CATCHUP] " + sbk.riga_log_dopo(es, quota, prossima))
        except (sg.MigrazioneMancante, QuotaNonLeggibile):
            raise
        except Exception as e:                             # DB giu' ecc.: la run prosegue, exit 1 alla fine
            ris.errori.append(f"lega {k[0]} stagione {k[1]}: {type(e).__name__}: {e}")
            if k not in ris.fatte:
                ris.rimaste.append(k)

    # 4) referto e codice d'uscita
    ris.codice = referto_buchi(voci, ris, quota, max_giorni, conti, stampa, oggi)
    return ris


def _cause(lac: sg.Lacune, flags: Dict[str, bool], fermato: Optional[str]) -> str:
    cause = []
    if lac.errori(flags):
        cause.append(f"errore API ripetuto su {lac.errori(flags)} partite-tabella")
    if lac.in_attesa(flags):
        cause.append(f"API vuota su {lac.in_attesa(flags)} partite-tabella (in attesa del 2o tentativo)")
    if fermato == "errori_api":
        cause.append("10 partite di fila con tutti gli endpoint in errore")
    if not cause:
        cause.append("partite da chiamare NON tentate nonostante il budget (da indagare)")
    spenti = [sg.ENDPOINTS[c][0] for c, on in flags.items() if not on]
    if spenti:
        cause.append("flag coverage False (non richieste): " + ",".join(spenti))
    return "; ".join(cause)


def referto_buchi(voci: List[Voce], ris: Risultato, quota: Any, max_giorni: int, conti: Dict[str, int],
                  stampa: Callable[[str], None], oggi: date) -> int:
    stampa("=" * 110)
    stampa("REFERTO BUCHI (partite FT senza dati, solo tabelle con flag di coverage True)")
    stampa(f"{'Lega':>6} {'Stag':>5} P  {'FT':>5}  da chiamare ev/fo/sg/ss/qu   att.  {'costo~':>7}  aperto da")
    aperte = 0
    costo_tot = 0
    piu_vecchio = 0
    vuoti_def = 0
    non_disp = 0
    falliti: List[str] = []
    rinviati: List[str] = []
    rimaste = set(ris.rimaste)
    capacita = max(1, quota.capacita_giornaliera())
    for v in sorted(voci, key=lambda v: (v.priorita, v.chiave)):
        k = v.chiave
        lac = ris.lacune_dopo.get(k, v.lacune)
        flags = v.flags
        vuoti_def += sum(lac.n(t, ("vuoto_definitivo",)) for t in lac.tabelle_attive(flags))
        non_disp += lac.non_disponibili(flags)
        n_aperti = lac.aperti(flags)
        if n_aperti == 0:
            continue
        aperte += 1
        costo = lac.chiamate_per_fixture(flags)
        costo_tot += costo
        dal = ris.aperto_dal.get(k) or oggi.isoformat()
        giorni = (oggi - date.fromisoformat(dal[:10])).days
        piu_vecchio = max(piu_vecchio, giorni)
        per_t = " ".join(f"{lac.n(sg.ENDPOINTS[c][0], sg.STATI_DA_CHIAMARE):>4}" if flags[c] else "   -"
                         for c in sg.ENDPOINTS)
        stampa(f"{k[0]:>6} {k[1]:>5} {v.priorita}  {lac.ft_totali:>5}  {per_t}   {lac.in_attesa(flags):>4}  "
               f"{costo:>7}  {dal} ({giorni} gg)")
        if giorni > max_giorni:
            fermata = ris.fermate_per.get(k)
            if k in rimaste or (fermata and fermata != "errori_api"):
                rinviati.append(f"lega {k[0]} stagione {k[1]} aperto da {giorni} gg: rinviato "
                                f"({ris.fermato_per or ris.fermate_per.get(k)}), ~{costo} chiamate")
            else:
                falliti.append(f"lega {k[0]} stagione {k[1]} aperto da {giorni} gg (> {max_giorni}) "
                               f"con budget disponibile: {_cause(lac, flags, ris.fermate_per.get(k))}")
    stampa("-" * 110)
    stampa(f"Chiamate fatte stanotte: {ris.chiamate}. Lega-stagioni lavorate: {len(ris.fatte)}, "
           f"rimaste in coda: {len(ris.rimaste)}. Quota: {quota.stato.riga() if quota.stato else '?'}")
    if ris.fermato_per:
        stampa(f"Fermato per: {ris.fermato_per} (NON e' un errore: si riprende al prossimo giro da cio' che manca).")
    stampa(f"Vuoti definitivi dell'API (non buchi, l'API non ha il dato): {vuoti_def} partite-tabella.")
    stampa(f"Quote fuori finestra API (partite di oltre 7 gg: storico quote API 7 gg, NON recuperabili, "
           f"non chiamate): {non_disp} partite.")
    stampa(f"Stagioni passate non ancora verificate (a rotazione, {len(voci)} verificate stanotte): "
           f"{conti.get('passate_non_verificate', 0)}; passate con 0 partite in DB (solo orchestratore a mano): "
           f"{conti.get('passate_mai_caricate', 0)}.")
    for r in rinviati:
        stampa(f"RINVIATO (quota/tempo/action concorrente): {r}")
    if rinviati:
        stampa(f"Stima per chiudere i buchi aperti con la capacita' giornaliera ({capacita} chiamate): "
               f"~{math.ceil(costo_tot / capacita)} giorni.")
    for e in ris.errori:
        stampa(f"ERRORE: {e}")
    for f in falliti:
        stampa(f"BUCO VECCHIO: {f}")
    if aperte == 0:
        stampa("DB SENZA BUCHI")
    else:
        stampa(f"BUCHI APERTI: {aperte} lega-stagioni, ~{costo_tot} chiamate, il piu' vecchio da {piu_vecchio} giorni")
    return 1 if (ris.errori or falliti) else 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    for flusso in (sys.stdout, sys.stderr):          # emoji degli script vecchi su console cp1252
        try:
            flusso.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    logging.basicConfig(level=logging.INFO)
    from api_client import APIFootballClient
    from config import API_FOOTBALL_KEY
    from db_client import get_supabase_client
    sb = get_supabase_client()
    client = APIFootballClient()
    quota = GestoreQuota(sb=sb, api_key=API_FOOTBALL_KEY, client=client)
    try:
        ris = esegui_catchup(sb, client, quota, ControlloConcorrenza())
    except (QuotaNonLeggibile, sg.MigrazioneMancante) as e:
        print(f"CATCHUP NON PARTITO: {e}")
        return 2
    return ris.codice


if __name__ == "__main__":
    sys.exit(main())
