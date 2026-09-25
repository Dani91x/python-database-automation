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
     P4 (25/09, ordine utente "tenere PERFETTO il DB" con il margine che avanza):
     stagioni passate MAI CARICATE (0 partite in `matches`), SOLO dopo che P1-P3
     sono finite senza fermarsi e SOLO se il margine sopra il pavimento
     CATCHUP_P4_MARGINE_MINIMO (default 500) copre la stagione PER INTERO
     (ordine utente: "NON DOBBIAMO LASCIARE LEGHE A META'", vedi `decidi_p4`);
     stagioni senza fixtures_events escluse salvo CATCHUP_P4_ANCHE_SENZA_EVENTI=1;
     stagioni `current` con fine passata da > 30 gg: verifica mirata all'API
     (`verifica_current_sospette`, al massimo 1 volta a settimana per stagione);
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
import re
import sys
import time
from dataclasses import dataclass, field
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

import season_aggregates as sa
import season_backfill as sbk
import season_gaps as sg
from api_quota import GestoreQuota, QuotaConPavimento, QuotaNonLeggibile, margine_medio_log

logger = logging.getLogger("seasons_catchup")

ATLANTE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "Betfair", "omega", "data", "hazard_atlas_v3.json")
WORKFLOW_ESCLUSIVI_DEFAULT = ("daily_yesterday_backfill.yml", "today_predictions_backfill.yml",
                              "predictions_results_backfill.yml", "retrain_models.yml")
# Riserva dinamica (25/09): le 3 action giornaliere che consumano la quota API
ACTION_GIORNALIERE = WORKFLOW_ESCLUSIVI_DEFAULT[:3]
CARTELLA_WORKFLOW = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".github", "workflows")
ORA_STOP_UTC_DEFAULT = 23           # CATCHUP_ORA_STOP_UTC: dalle 23 UTC niente lega-stagioni nuove (reset 00:00)
# P4 - stagioni mai caricate
P4_PAVIMENTO_DEFAULT = 500          # CATCHUP_P4_MARGINE_MINIMO
VERIFICA_CURRENT_GIORNI = 7         # stagione 'current' con fine passata: /leagues mirata al massimo 1 volta/settimana
VERIFICA_CURRENT_MAX_DEFAULT = 100  # CATCHUP_MAX_VERIFICHE_CURRENT: chiamate di verifica per run (575 sospette oggi)
P4_GIORNI_TRA_TENTATIVI = 7         # /fixtures senza partite: si ritenta dopo 7 giorni...
P4_MAX_TENTATIVI_VUOTI = 2          # ...e dopo 2 risposte senza partite la stagione e' dichiarata "API senza partite"
P4_GIORNI_MEDIA = 7                 # margine medio degli ultimi 7 giorni (api_call_log) per la stima dei giorni


def _env_int(nome: str, default: int, env: Optional[Dict[str, str]] = None) -> int:
    env = os.environ if env is None else env
    grezzo = (env.get(nome) or "").strip()
    return int(grezzo) if grezzo else default


def _adesso_utc() -> datetime:
    """Ora UTC (punto unico: i test la fissano)."""
    return datetime.now(timezone.utc)


def _env_si(nome: str, env: Optional[Dict[str, str]] = None) -> bool:
    env = os.environ if env is None else env
    return (env.get(nome) or "").strip().lower() in ("1", "true", "si", "yes", "on")


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


def leghe_modelli_ml() -> Set[int]:
    """Leghe con modelli ML: stessa fonte del training (training_planner._load_eligible_leagues,
    training_eligible_leagues.json, leghe con >= 50 partite giocate). Assente -> vuoto + avviso."""
    try:
        from training_planner import _load_eligible_leagues
        return {int(x) for x in (_load_eligible_leagues() or [])}
    except Exception as e:                                  # file/modulo assenti: P4 senza fascia ML
        print(f"[CATCHUP] AVVISO: leghe dei modelli ML non lette ({e}): P4 senza fascia ML.")
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

    # -- riserva dinamica (api_quota.GestoreQuota(action_completate=...)) -------------------
    def orario_cron(self, wf: str, cartella: str = CARTELLA_WORKFLOW) -> Optional[Tuple[int, int]]:
        """(ora, minuto) UTC del cron giornaliero del workflow, letto dal suo file YAML
        (`cron: 'M H * * *'`; con piu' cron il piu' presto). Non leggibile -> None."""
        try:
            with open(os.path.join(cartella, wf), encoding="utf-8") as f:
                testo = f.read()
        except OSError:
            return None
        orari = [(int(h), int(m)) for m, h in re.findall(r"cron:\s*['\"](\d+)\s+(\d+)\s+\*\s+\*\s+\*['\"]", testo)]
        return min(orari) if orari else None

    def action_completate_oggi(self, adesso: Optional[datetime] = None) -> Optional[bool]:
        """True se OGNUNA delle 3 action giornaliere (Daily, Today, Results) ha, nel giorno UTC
        corrente, una run conclusa con SUCCESSO creata DOPO l'orario del suo cron di oggi, e
        nessuna e' in corso o in coda. False se ne manca anche una. None se non leggibile
        (token assente, GitHub in errore, cron non trovato): chi chiama tiene la riserva piena.

        Criterio scelto (il piu' semplice e sicuro, contro "orario massimo osservato + margine"):
        - lo stato vero da GitHub, niente orari stimati: il cron parte con ~5 h di ritardo e
          variabile, un orario fisso sbaglierebbe nei giorni lenti;
        - "creata dopo il cron di oggi": una run di IERI partita in ritardo dopo la mezzanotte
          (creata prima del cron di oggi) NON conta, altrimenti la riserva scenderebbe prima
          che l'action di oggi abbia girato;
        - solo `success`: un'action fallita di solito si rilancia a mano lo stesso giorno e
          deve trovare la sua quota. Un giorno con un'action fallita resta a riserva piena.
        Una volta True resta True fino a fine giorno UTC (le 3 action girano una volta al
        giorno); False si rilegge al massimo ogni `intervallo` secondi."""
        if not self.attivo:
            return None
        adesso = adesso or datetime.now(timezone.utc)
        giorno = adesso.date()
        if getattr(self, "_completate_giorno", None) == giorno:
            return True
        cache = getattr(self, "_completate_cache", None)
        if cache and cache[0] == giorno and time.time() - cache[1] < self.intervallo:
            return cache[2]
        import requests
        get = self.http_get or requests.get
        intestazioni = {"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json"}
        esito: Optional[bool] = True
        try:
            for wf in ACTION_GIORNALIERE:
                orario = self.orario_cron(wf)
                if orario is None:
                    print(f"[CATCHUP] AVVISO: cron di {wf} non letto: riserva piena")
                    return None
                url = f"https://api.github.com/repos/{self.repo}/actions/workflows/{wf}/runs"
                for stato in ("in_progress", "queued"):
                    r = get(url, params={"status": stato, "per_page": 1}, headers=intestazioni, timeout=15)
                    if getattr(r, "status_code", 0) != 200:
                        return None
                    attive = int((r.json() or {}).get("total_count") or 0)
                    if attive:                                   # in corso o in coda: non ha finito
                        esito = False
                dal = datetime(giorno.year, giorno.month, giorno.day, orario[0], orario[1], tzinfo=timezone.utc)
                r = get(url, params={"status": "success", "created": f">={dal.strftime('%Y-%m-%dT%H:%M:%SZ')}",
                                     "per_page": 1}, headers=intestazioni, timeout=15)
                if getattr(r, "status_code", 0) != 200:
                    return None
                if int((r.json() or {}).get("total_count") or 0) == 0:
                    esito = False
                if esito is False:
                    break
        except Exception as e:
            print(f"[CATCHUP] AVVISO: stato delle action del giorno non letto ({e}): riserva piena")
            return None
        self._completate_cache = (giorno, time.time(), esito)
        if esito:
            self._completate_giorno = giorno
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
        return self.lacune.chiamate_per_fixture(self.flags) + self.lacune.chiamate_aggregati()


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
        if str((sj.get("fixtures") or {}).get("matches_count")) == "0":
            conti["passate_mai_caricate"] += 1          # 0 partite in DB: coda P4 (stagioni mai caricate)
            continue
        if v2 and str((sj.get("fixtures") or {}).get("ft_count") or "0") == "0":
            conti["passate_senza_ft"] = conti.get("passate_senza_ft", 0) + 1   # partite ma nessuna FT
            continue
        (passate_note if v2 else passate_nuove).append(r)
    passate_nuove.sort(key=lambda r: -int(r["season_year"]))
    passate = (passate_note + passate_nuove)[:max_passate]
    conti["passate_non_verificate"] = len(passate_note) + len(passate_nuove) - len(passate)
    return vive, passate, conti


# ---------------------------------------------------------------------------
# P4 - stagioni mai caricate (0 partite in matches)
# ---------------------------------------------------------------------------
@dataclass
class CandidatoP4:
    row: Dict[str, Any]
    stato_prec: Optional[Dict[str, Any]]
    fascia: int                 # 0 leghe dei bot (atlante), 1 leghe con modelli ML, 2 altre
    importanza: int             # stagioni della lega con fixtures_events True in coverage
    costo: int                  # stima intera (season_backfill.stima_costo_mai_caricata)

    @property
    def chiave(self) -> Tuple[int, int]:
        return int(self.row["league_id"]), int(self.row["season_year"])


def passata_per_p4(row: Dict[str, Any], oggi: date) -> bool:
    """Passata = NON viva: `current` False (come dice l'API: il mapper lo aggiorna ogni giorno
    e, per le stagioni `current` con fine passata da > 30 gg, lo verifica il catchup con una
    chiamata mirata, `verifica_current_sospette`) e fine da oltre 30 giorni. Nessuna euristica
    sulle date che contraddica l'API (decisione utente 25/09: "dobbiamo fidarci dell'API")."""
    return not sg.e_corrente_o_recente(row, oggi)


def current_sospetta(row: Dict[str, Any], oggi: date) -> bool:
    """`current` True ma data di fine passata da oltre 30 giorni (575 stagioni sul DB vero il 25/09)."""
    fine = sg._data(row.get("season_end"))
    return bool(row.get("current")) and fine is not None and fine < oggi - timedelta(days=sg.FINESTRA_RECENTE_GIORNI)


def _current_da_api(data: Any, season_year: int) -> Optional[bool]:
    """/leagues?id=&season= -> il flag `current` della stagione, None se errore o stagione assente."""
    from per_fixture_backfill import _risposta_o_none
    lista = _risposta_o_none(data)
    if not lista:
        return None
    for lega in lista:
        for stag in (lega or {}).get("seasons") or []:
            if int(stag.get("year") or 0) == int(season_year):
                return bool(stag.get("current"))
    return None


def _salva_verifica_current(sb: Any, k: Tuple[int, int], esito: Dict[str, Any]) -> bool:
    """Scrive stats_json.verifica_current SENZA toccare il resto (lettura dello stats_json
    completo di quella sola riga + update). Nessuna riga di stato -> non si crea (False)."""
    resp = (sb.table("season_backfill_state").select("stats_json")
            .eq("league_id", k[0]).eq("season_year", k[1]).limit(1).execute())
    righe = list(getattr(resp, "data", None) or [])
    if not righe:
        return False
    sj = dict(righe[0].get("stats_json") or {})
    sj["verifica_current"] = esito
    sb.table("season_backfill_state").update({"stats_json": sj}).eq("league_id", k[0]).eq("season_year", k[1]).execute()
    return True


def verifica_current_sospette(sb: Any, client: Any, quota: Any, coperture: List[Dict[str, Any]],
                              stati: Dict[Tuple[int, int], Dict[str, Any]], env: Dict[str, str], oggi: date,
                              stampa: Callable[[str], None]) -> Dict[str, int]:
    """Decisione utente (25/09): per le stagioni ancora `current` ma con fine passata da > 30 gg
    il catchup chiede all'API (`/leagues?id=<lega>&season=<anno>`, 1 chiamata, contata nella
    quota) se e' vero, al massimo una volta a settimana per stagione; l'esito va in
    stats_json.verifica_current {at, current} e la stagione e' trattata come dice l'API
    (la riga di coverage in memoria prende il `current` verificato). Esito della settimana gia'
    noto -> nessuna chiamata. Errore/assente -> resta come dice il DB, si ritenta al giro dopo.
    Tetto di chiamate per run: CATCHUP_MAX_VERIFICHE_CURRENT (default 100)."""
    tetto = _env_int("CATCHUP_MAX_VERIFICHE_CURRENT", VERIFICA_CURRENT_MAX_DEFAULT, env)
    conti = {"sospette": 0, "chiamate": 0, "da_memoria": 0, "confermate_current": 0, "chiuse": 0, "rinviate": 0}
    for r in coperture:
        if not current_sospetta(r, oggi):
            continue
        conti["sospette"] += 1
        k = (int(r["league_id"]), int(r["season_year"]))
        sj = ((stati.get(k) or {}).get("stats_json")) or {}
        nota = sj.get("verifica_current") or {}
        quando = sg._data(nota.get("at"))
        if quando is not None and (oggi - quando).days < VERIFICA_CURRENT_GIORNI and "current" in nota:
            conti["da_memoria"] += 1
            valore = bool(nota["current"])
        else:
            if conti["chiamate"] >= tetto or quota.margine() < 1:
                conti["rinviate"] += 1
                continue
            data = client.call("/leagues", params={"id": k[0], "season": k[1]})
            conti["chiamate"] += 1
            valore_api = _current_da_api(data, k[1])
            if valore_api is None:
                stampa(f"[CATCHUP] verifica current lega {k[0]} stagione {k[1]}: API senza risposta valida, "
                       f"resta come nel DB (current=True)")
                continue
            valore = valore_api
            esito = {"at": oggi.isoformat(), "current": valore}
            stati.setdefault(k, {}).setdefault("stats_json", {})["verifica_current"] = esito
            _salva_verifica_current(sb, k, esito)
            stampa(f"[CATCHUP] verifica current lega {k[0]} stagione {k[1]} (fine {r.get('season_end')}): "
                   f"API current={valore} -> trattata come {'viva' if valore else 'passata'}")
        r["current"] = valore                       # in memoria: la stagione e' trattata come dice l'API
        conti["confermate_current" if valore else "chiuse"] += 1
    return conti


def seleziona_p4(coperture: List[Dict[str, Any]], stati: Dict[Tuple[int, int], Dict[str, Any]],
                 lacune_note: Dict[Tuple[int, int], sg.Lacune], oggi: date, prioritarie: Set[int],
                 leghe_ml: Set[int], anche_senza_eventi: bool = False) -> Tuple[List[CandidatoP4], Dict[str, int]]:
    """(lega, stagione) con almeno un flag per-partita True, iniziate, passate per data e con
    ZERO partite in `matches`: dai conteggi verificati stanotte (season_gaps_summary) se ci
    sono, altrimenti da season_backfill_state.stats_json.fixtures.matches_count (confrontato
    col conteggio vivo del DB vero il 25/09: 2.651 su 2.692 uguali, mai ">0 nello stato e 0 in DB").
    Ordine: fascia (bot, ML, altre), importanza della lega (desc), stagione piu' recente, lega."""
    importanza = Counter(int(r["league_id"]) for r in coperture if r.get("fixtures_events"))
    # partite stimate: la stagione piu' grande della stessa lega gia' in DB (min 380), cosi' una
    # lega da 552 partite non viene sottostimata e poi lasciata a meta'
    partite_lega: Dict[int, int] = {}
    for (lid, _), st in stati.items():
        try:
            n = int(((st.get("stats_json") or {}).get("fixtures") or {}).get("matches_count") or 0)
        except (TypeError, ValueError):
            continue
        partite_lega[lid] = max(partite_lega.get(lid, 0), n)
    conti = {"senza_eventi": 0, "api_senza_partite": 0, "in_attesa_ritentativo": 0}
    out: List[CandidatoP4] = []
    for r in coperture:
        if (not any(sg.flag_per_fixture(r).values()) or not sg.stagione_iniziata(r, oggi)
                or not passata_per_p4(r, oggi)):
            continue
        k = (int(r["league_id"]), int(r["season_year"]))
        st = stati.get(k) or {}
        sj = st.get("stats_json") or {}
        lac = lacune_note.get(k)
        if lac is not None:
            zero = lac.partite_totali == 0
        else:
            zero = str((sj.get("fixtures") or {}).get("matches_count")) == "0"
        if not zero:
            continue
        if not r.get("fixtures_events") and not anche_senza_eventi:
            conti["senza_eventi"] += 1                  # non caricabili: API senza eventi
            continue
        tent = sj.get("mai_caricata") or {}
        if int(tent.get("tentativi") or 0) >= P4_MAX_TENTATIVI_VUOTI:
            conti["api_senza_partite"] += 1             # /fixtures senza partite 2 volte: dichiarata
            continue
        ultimo = sg._data(tent.get("ultimo_at"))
        if ultimo is not None and (oggi - ultimo).days < P4_GIORNI_TRA_TENTATIVI:
            conti["in_attesa_ritentativo"] += 1
            continue
        fascia = 0 if k[0] in prioritarie else (1 if k[0] in leghe_ml else 2)
        partite = max(sbk.STIMA_PARTITE_STAGIONE_VUOTA, partite_lega.get(k[0], 0))
        out.append(CandidatoP4(r, stati.get(k), fascia, importanza[k[0]],
                               sbk.stima_costo_mai_caricata(r, oggi, partite)))
    out.sort(key=lambda c: (c.fascia, -c.importanza, -c.chiave[1], c.chiave[0]))
    return out, conti


def decidi_p4(piano: Any, quota_p4: Any, costo_minimo: int = 0) -> Tuple[str, int]:
    """-> (decisione, costo). `quota_p4` e' la vista con il pavimento (margine - pavimento).
    Decisione dell'utente (25/09): "NON DOBBIAMO LASCIARE LEGHE A META'": la P4 parte SOLO se
    il margine copre la stagione PER INTERO (niente spezzoni):
    - margine P4 >= costo intero -> 'procedo';
    - altrimenti 'non_entra' (nessuna chiamata; la coda prova la stagione successiva, che
      potrebbe entrare per intero).
    costo = max(stima del piano, stima della coda con le partite reali della lega)."""
    if not piano.c_e_lavoro:
        return "niente", 0
    costo = max(int(piano.costo), int(costo_minimo))
    if quota_p4.margine() >= costo:
        return "procedo", costo
    return "non_entra", costo


def _segna_tentativo_p4(sb: Any, piano: Any, es: Any, prec: Optional[Dict[str, Any]], oggi: date) -> None:
    """/fixtures chiamata ma ancora 0 partite: memoria in stats_json.mai_caricata, cosi' la
    stagione non si richiama ogni giorno (ritentativo dopo 7 gg, poi dichiarata)."""
    sj_prec = (prec or {}).get("stats_json") or {}
    vecchio = sj_prec.get("mai_caricata") or {}
    nuovo = {"tentativi": int(vecchio.get("tentativi") or 0) + 1, "ultimo_at": oggi.isoformat(),
             "esito": "fixtures_senza_partite"}
    prec2 = {**(prec or {}), "stats_json": {**sj_prec, "mai_caricata": nuovo}}
    sg.scrivi_stato(sb, piano.league_id, piano.season_year, es.stato or "in_progress",
                    sg.costruisci_stats_json(piano.coverage_row, es.lacune_dopo, prec2, "catchup_p4",
                                             {"chiamate_fatte": es.chiamate}, oggi,
                                             tentativi_aggregati=(es.stats or {}).get("aggregati")))


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
    # P4 - stagioni mai caricate
    p4_candidati: List[Any] = field(default_factory=list)
    p4_conti: Dict[str, int] = field(default_factory=dict)
    p4_caricate: List[Tuple[int, int]] = field(default_factory=list)       # per intero
    p4_spezzoni: List[Tuple[int, int]] = field(default_factory=list)       # interrotte (partite oltre la stima)
    p4_non_entrate: List[Tuple[int, int]] = field(default_factory=list)    # non coperte per intero oggi
    verifiche_current: Dict[str, int] = field(default_factory=dict)
    p4_senza_partite: List[Tuple[int, int]] = field(default_factory=list)  # /fixtures senza partite oggi
    p4_chiamate: Dict[Tuple[int, int], int] = field(default_factory=dict)
    p4_non_partita: Optional[str] = None
    p4_pavimento: int = P4_PAVIMENTO_DEFAULT


def esegui_catchup(sb: Any, client: Any, quota: Any, concorrenza: Any = None,
                   env: Optional[Dict[str, str]] = None, oggi: Optional[date] = None,
                   stampa: Callable[[str], None] = print, orologio: Callable[[], float] = time.time,
                   adesso_utc: Optional[Callable[[], datetime]] = None) -> Risultato:
    env = os.environ if env is None else env
    oggi = oggi or datetime.now(timezone.utc).date()
    max_min = _env_int("CATCHUP_MAX_MINUTI", 150, env)
    max_passate = _env_int("CATCHUP_MAX_VERIFICHE_PASSATE", 150, env)
    max_giorni = _env_int("BACKFILL_BUCHI_MAX_GIORNI", 3, env)
    ora_stop = _env_int("CATCHUP_ORA_STOP_UTC", ORA_STOP_UTC_DEFAULT, env)
    ora_utc = adesso_utc or _adesso_utc
    t0 = orologio()

    def fine_giornata() -> Optional[str]:
        """Dalle `ora_stop` UTC niente lavoro nuovo: il contatore API si azzera alle 00:00 UTC e
        con la riserva residua (300) un lavoro a cavallo del reset mangerebbe la quota del
        giorno dopo, prima del Daily."""
        h = ora_utc().hour
        return f"fine giornata UTC (ore {h} >= {ora_stop}: reset quota alle 00:00)" if h >= ora_stop else None
    ris = Risultato()

    # 1) pre-controlli (fail-loud: li gestisce main)
    sg.verifica_migrazione(sb)
    sa.verifica_migrazione(sb)
    st = quota.aggiorna()
    stampa(f"[CATCHUP] quota all'avvio: {st.riga()}")

    # 2) verifica lacune dai dati
    prioritarie = leghe_prioritarie(env)
    coperture = sg.leggi_coverage(sb)
    stati = sg.leggi_stati(sb)
    # stagioni 'current' con fine passata da > 30 gg: si chiede all'API (decisione utente 25/09)
    ris.verifiche_current = verifica_current_sospette(sb, client, quota, coperture, stati, env, oggi, stampa)
    if ris.verifiche_current.get("sospette"):
        vc = ris.verifiche_current
        stampa(f"[CATCHUP] stagioni 'current' con fine passata da > 30 gg: {vc['sospette']} (verificate ora "
               f"{vc['chiamate']} chiamate /leagues, note della settimana {vc['da_memoria']}, confermate current "
               f"{vc['confermate_current']}, chiuse dall'API {vc['chiuse']}, rinviate {vc['rinviate']})")
        if vc["chiamate"]:
            quota.aggiorna()                               # le verifiche sono nel budget
    vive, passate, conti = seleziona_candidati(coperture, stati, max_passate, oggi)
    stampa(f"[CATCHUP] candidati: {len(vive)} stagioni vive, {len(passate)} passate da verificare "
           f"(non verificate stanotte: {conti['passate_non_verificate']}, "
           f"passate mai caricate: {conti['passate_mai_caricate']})")
    righe_per_k = {(int(r["league_id"]), int(r["season_year"])): r for r in vive + passate}
    lacune = sg.riepilogo_lacune(sb, list(righe_per_k))
    # aggregati di TUTTE le stagioni verificate (vive ogni giorno, per cadenza): il Daily non li fa
    sa.attacca(sb, lacune, righe_per_k, stati, sa.adesso())
    voci: List[Voce] = []
    stati_da_scrivere: List[Dict[str, Any]] = []
    for k, row in righe_per_k.items():
        lac = lacune[k]
        viva = sg.e_corrente_o_recente(row, oggi)
        if viva and lac.ft_totali == 0:
            continue                                     # nessuna partita FT ancora: nulla da recuperare
        prio = 3 if not viva else (1 if k[0] in prioritarie else 2)
        voce = Voce(row, lac, prio, stati.get(k))
        sj = sg.costruisci_stats_json(row, lac, voce.stato_prec, "catchup", None, oggi)
        stati_da_scrivere.append({"league_id": k[0], "season_year": k[1],
                                  "status": sg.calcola_stato(row, lac, oggi), "stats_json": sj})
        if not viva and lac.partite_totali == 0:
            continue                                     # mai caricata: coda P4 (dopo P1-P3), non un buco P3
        voci.append(voce)
        ris.aperto_dal[k] = sj.get("buco_aperto_dal")
    sg.scrivi_stati(sb, stati_da_scrivere)
    coda = costruisci_coda(voci)
    stampa(f"[CATCHUP] coda: {len(coda)} lega-stagioni con partite da chiamare "
           f"(P1 {sum(1 for v in coda if v.priorita == 1)}, P2 {sum(1 for v in coda if v.priorita == 2)}, "
           f"P3 {sum(1 for v in coda if v.priorita == 3)}), ~{sum(v.chiamate for v in coda)} chiamate "
           f"(per-partita + aggregati)")

    def deve_fermarsi() -> Optional[str]:
        if (orologio() - t0) / 60.0 >= max_min:
            return f"tempo massimo {max_min} min"
        if fine_giornata():
            return fine_giornata()
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
        motivo = motivo or fine_giornata()
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
            ris.lacune_dopo[k] = es.lacune_dopo or sg.lacune_stagione(sb, k[0], k[1])
            quota.aggiorna()                               # RICALCOLO dopo ogni lega-stagione
            prossima = coda[i + 1].chiamate if i + 1 < len(coda) else None
            stampa("[CATCHUP] " + sbk.riga_log_dopo(es, quota, prossima))
        except (sg.MigrazioneMancante, QuotaNonLeggibile):
            raise
        except Exception as e:                             # DB giu' ecc.: la run prosegue, exit 1 alla fine
            ris.errori.append(f"lega {k[0]} stagione {k[1]}: {type(e).__name__}: {e}")
            if k not in ris.fatte:
                ris.rimaste.append(k)

    # 3b) P4: stagioni mai caricate, solo con il margine che avanza dopo P1-P3
    esegui_p4(sb, client, quota, ris, coperture, stati, lacune, prioritarie, env, oggi, stampa,
              deve_fermarsi, concorrenza, lambda: (orologio() - t0) / 60.0 >= max_min, max_min, fine_giornata)

    # 4) referto e codice d'uscita
    def media() -> Optional[float]:
        st_q = quota.stato
        riserva = getattr(quota, "riserva_minima", st_q.riserva if st_q else 0)
        return margine_medio_log(sb, st_q.limit_day, riserva, P4_GIORNI_MEDIA) if st_q else None
    ris.codice = referto_buchi(voci, ris, quota, max_giorni, conti, stampa, oggi, margine_medio=media)
    return ris


def esegui_p4(sb: Any, client: Any, quota: Any, ris: Risultato, coperture: List[Dict[str, Any]],
              stati: Dict[Tuple[int, int], Dict[str, Any]], lacune: Dict[Tuple[int, int], sg.Lacune],
              prioritarie: Set[int], env: Dict[str, str], oggi: date, stampa: Callable[[str], None],
              deve_fermarsi: Callable[[], Optional[str]], concorrenza: Any, tempo_scaduto: Callable[[], bool],
              max_min: int, fine_giornata: Callable[[], Optional[str]] = lambda: None) -> None:
    """P4 dopo P1-P3. Regole: parte solo se P1-P3 NON si sono fermate (quota, tempo, action
    concorrente); ogni stagione parte solo se (margine - pavimento) la copre per intero o
    almeno per uno spezzone (decidi_p4); dentro, stop a fine partita quando il margine
    scenderebbe sotto il pavimento (QuotaConPavimento); ricalcolo quota DOPO ogni stagione."""
    pavimento = _env_int("CATCHUP_P4_MARGINE_MINIMO", P4_PAVIMENTO_DEFAULT, env)
    ris.p4_pavimento = pavimento
    cand, ris.p4_conti = seleziona_p4(coperture, stati, lacune, oggi, prioritarie, leghe_modelli_ml(),
                                      _env_si("CATCHUP_P4_ANCHE_SENZA_EVENTI", env))
    ris.p4_candidati = cand
    if not cand:
        return
    if ris.fermato_per:
        ris.p4_non_partita = f"P1-P3 non finite (fermate per {ris.fermato_per}): la P4 usa solo il margine che avanza"
        stampa(f"[CATCHUP] P4 non parte: {ris.p4_non_partita}")
        return
    q4 = QuotaConPavimento(quota, pavimento)
    for i, c in enumerate(cand):
        k = c.chiave
        motivo = None if concorrenza is None else concorrenza.in_corso(forza=True)
        if tempo_scaduto():
            motivo = f"tempo massimo {max_min} min"
        motivo = motivo or fine_giornata()
        if motivo:
            ris.p4_non_partita = motivo
            stampa(f"[CATCHUP] P4 STOP prima di lega {k[0]} stagione {k[1]}: {motivo}")
            return
        if quota.margine() < pavimento:
            ris.p4_non_partita = f"margine {quota.margine()} sotto il pavimento {pavimento}"
            stampa(f"[CATCHUP] P4 STOP prima di lega {k[0]} stagione {k[1]}: {ris.p4_non_partita}")
            return
        try:
            piano = sbk.pianifica(sb, c.row, c.stato_prec, includi_mai_caricate=True, oggi=oggi,
                                  fisse_su_stagione_viva=True)
            if not piano.serve_fixtures:
                # lo stato diceva 0 partite ma in DB ci sono (es. Daily): non e' una mai caricata.
                # Stato riscritto dai dati (0 chiamate): da domani la verifica la vede come P3.
                sbk.scrivi_stato_senza_lavoro(sb, piano, c.stato_prec, "catchup_p4", oggi)
                stampa(f"[CATCHUP] P4 lega {k[0]} stagione {k[1]}: partite gia' in DB "
                       f"({piano.lacune.partite_totali}), stato aggiornato, passa alla P3")
                continue
            decisione, costo = decidi_p4(piano, q4, c.costo)
            stampa(f"[CATCHUP] P4 lega {k[0]} stagione {k[1]} (MAI CARICATA, fascia {c.fascia}): "
                   f"costo ~{costo}, margine {quota.margine()} - pavimento {pavimento} = {q4.margine()} "
                   f"-> {decisione}")
            if decisione == "niente":
                continue
            if decisione == "non_entra":
                ris.p4_non_entrate.append(k)            # per intero o niente: prova la successiva
                continue
            es = sbk.esegui(sb, client, q4, piano, c.stato_prec, "catchup_p4", deve_fermarsi, oggi)
            ris.chiamate += es.chiamate
            ris.p4_chiamate[k] = es.chiamate
            if es.errore:
                ris.errori.append(f"P4 lega {k[0]} stagione {k[1]}: {es.errore}")
            lac_dopo = es.lacune_dopo
            if lac_dopo is not None and lac_dopo.partite_totali > 0:
                (ris.p4_spezzoni if es.fermato_per else ris.p4_caricate).append(k)
            elif es.chiamate > 0 and not es.errore and lac_dopo is not None:
                ris.p4_senza_partite.append(k)
                _segna_tentativo_p4(sb, piano, es, c.stato_prec, oggi)
            quota.aggiorna()                                 # RICALCOLO dopo ogni lega-stagione
            prossima = cand[i + 1].costo if i + 1 < len(cand) else None
            stampa("[CATCHUP] P4 " + sbk.riga_log_dopo(es, q4, prossima))
            if es.fermato_per and es.fermato_per != "errori_api":
                ris.p4_non_partita = f"fermata a fine partita: {es.fermato_per}"
                return
        except (sg.MigrazioneMancante, QuotaNonLeggibile):
            raise
        except Exception as e:                               # la P4 non abbatte la run: exit 1 alla fine
            ris.errori.append(f"P4 lega {k[0]} stagione {k[1]}: {type(e).__name__}: {e}")
    if ris.p4_non_entrate and not ris.p4_non_partita:
        ris.p4_non_partita = (f"{len(ris.p4_non_entrate)} stagioni non entrano PER INTERO nel margine di oggi "
                              f"(margine {quota.margine()} - pavimento {pavimento}): nessuna lasciata a meta'")


def _cause(lac: sg.Lacune, flags: Dict[str, bool], fermato: Optional[str]) -> str:
    cause = []
    if lac.errori(flags):
        cause.append(f"errore API ripetuto su {lac.errori(flags)} partite-tabella")
    if lac.in_attesa(flags):
        cause.append(f"API vuota su {lac.in_attesa(flags)} partite-tabella (in attesa del 2o tentativo)")
    if fermato == "errori_api":
        cause.append("10 partite di fila con tutti gli endpoint in errore")
    agg = [f"{n}={a.get('stato')}" for n, a in lac.aggregati.items() if n in lac.agg_da_fare()]
    if agg:
        cause.append("aggregati ancora da fare: " + ", ".join(agg))
    if not cause:
        cause.append("partite da chiamare NON tentate nonostante il budget (da indagare)")
    spenti = [sg.ENDPOINTS[c][0] for c, on in flags.items() if not on]
    if spenti:
        cause.append("flag coverage False (non richieste): " + ",".join(spenti))
    return "; ".join(cause)


def referto_p4(ris: Risultato, stampa: Callable[[str], None],
               margine_medio: Optional[Callable[[], Optional[float]]] = None) -> None:
    """Sezione STAGIONI MAI CARICATE del referto: quante, caricate oggi, quante restano,
    stima dei giorni con il margine medio degli ultimi 7 giorni (api_call_log)."""
    cand = ris.p4_candidati
    conti = ris.p4_conti or {}
    pav = ris.p4_pavimento
    toccate = set(ris.p4_caricate) | set(ris.p4_spezzoni)
    restano = [c for c in cand if c.chiave not in toccate]
    costo_rest = sum(c.costo for c in restano)
    stampa("-" * 110)
    stampa(f"STAGIONI MAI CARICATE (0 partite in DB; P4 dopo P1-P3, solo PER INTERO con il margine sopra il "
           f"pavimento {pav})")
    stampa(f"  in coda P4: {len(cand)} (leghe bot {sum(1 for c in cand if c.fascia == 0)}, "
           f"leghe ML {sum(1 for c in cand if c.fascia == 1)}, altre {sum(1 for c in cand if c.fascia == 2)}), "
           f"~{sum(c.costo for c in cand)} chiamate stimate")
    stampa(f"  caricate oggi: {len(ris.p4_caricate)} per intero, {len(ris.p4_spezzoni)} interrotte (partite oltre "
           f"la stima: il resto lo chiude la P3 dal prossimo giro); chiamate P4 oggi: {sum(ris.p4_chiamate.values())}")
    stampa(f"  restano: {len(restano)} stagioni, ~{costo_rest} chiamate")
    stampa(f"  escluse: {conti.get('senza_eventi', 0)} senza fixtures_events (non caricabili: API senza eventi; "
           f"CATCHUP_P4_ANCHE_SENZA_EVENTI=1 per includerle), {conti.get('api_senza_partite', 0)} API senza "
           f"partite (/fixtures vuota {P4_MAX_TENTATIVI_VUOTI} volte), "
           f"{conti.get('in_attesa_ritentativo', 0) + len(ris.p4_senza_partite)} in attesa di ritentativo "
           f"(/fixtures vuota: si riprova dopo {P4_GIORNI_TRA_TENTATIVI} gg)")
    if ris.p4_non_partita:
        stampa(f"  P4 ferma: {ris.p4_non_partita}")
    if not restano:
        return
    media: Optional[float] = None
    errore = None
    if margine_medio is not None:
        try:
            media = margine_medio()
        except Exception as e:                               # e' una stima, non un errore della run
            errore = f"{type(e).__name__}: {e}"
    if media is None:
        stampa("  stima giorni al completamento: non disponibile (margine medio da api_call_log non letto"
               + (f": {errore})" if errore else ")"))
    elif media - pav <= 0:
        stampa(f"  stima giorni al completamento: non stimabile (margine medio ultimi {P4_GIORNI_MEDIA} gg "
               f"{media:.0f} <= pavimento {pav}: nessun margine per la P4)")
    else:
        stampa(f"  stima giorni al completamento: ~{math.ceil(costo_rest / (media - pav))} giorni (margine medio "
               f"ultimi {P4_GIORNI_MEDIA} gg da api_call_log {media:.0f} - pavimento {pav} = "
               f"{media - pav:.0f} chiamate/giorno per la P4)")
    stampa("  prossime: " + ", ".join(f"lega {c.chiave[0]} stagione {c.chiave[1]} ~{c.costo}" for c in restano[:5]))


def referto_buchi(voci: List[Voce], ris: Risultato, quota: Any, max_giorni: int, conti: Dict[str, int],
                  stampa: Callable[[str], None], oggi: date,
                  margine_medio: Optional[Callable[[], Optional[float]]] = None) -> int:
    stampa("=" * 110)
    stampa("REFERTO BUCHI (partite FT senza dati e aggregati da fare; solo flag di coverage True)")
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
        costo = lac.chiamate_per_fixture(flags) + lac.chiamate_aggregati()
        costo_tot += costo
        dal = ris.aperto_dal.get(k) or oggi.isoformat()
        giorni = (oggi - date.fromisoformat(dal[:10])).days
        piu_vecchio = max(piu_vecchio, giorni)
        per_t = " ".join(f"{lac.n(sg.ENDPOINTS[c][0], sg.STATI_DA_CHIAMARE):>4}" if flags[c] else "   -"
                         for c in sg.ENDPOINTS)
        stampa(f"{k[0]:>6} {k[1]:>5} {v.priorita}  {lac.ft_totali:>5}  {per_t}   {lac.in_attesa(flags):>4}  "
               f"{costo:>7}  {dal} ({giorni} gg)")
        if lac.agg_da_fare():
            stampa("                aggregati da fare: " + ", ".join(
                f"{n}={lac.aggregati[n]['stato']}({str(lac.aggregati[n].get('ultimo') or '-')[:10]})"
                for n in lac.agg_da_fare()))
        if giorni > max_giorni:
            fermata = ris.fermate_per.get(k)
            if k in rimaste or (fermata and fermata != "errori_api"):
                rinviati.append(f"lega {k[0]} stagione {k[1]} aperto da {giorni} gg: rinviato "
                                f"({ris.fermato_per or ris.fermate_per.get(k)}), ~{costo} chiamate")
            else:
                falliti.append(f"lega {k[0]} stagione {k[1]} aperto da {giorni} gg (> {max_giorni}) "
                               f"con budget disponibile: {_cause(lac, flags, ris.fermate_per.get(k))}")
    stampa("-" * 110)
    stampa("AGGREGATI (lega-stagioni verificate stanotte): cadenza standings dopo ogni giornata, injuries ogni "
           "giorno (stagioni vive), top_* settimanale")
    for nome in sa.ORDINE:
        conta: Dict[str, int] = {}
        for v in voci:
            a = ris.lacune_dopo.get(v.chiave, v.lacune).aggregati.get(nome)
            if a:
                conta[a["stato"]] = conta.get(a["stato"], 0) + 1
        stampa(f"  {nome:<12} " + ", ".join(f"{st} {n}" for st, n in sorted(conta.items()))
               + "   (flag_false = coverage False: NON chiamato; vuoto_api = l'API non ha dati: dichiarato)")
    stampa(f"Chiamate fatte stanotte: {ris.chiamate}. Lega-stagioni lavorate: {len(ris.fatte)}, "
           f"rimaste in coda: {len(ris.rimaste)}. Quota: {quota.stato.riga() if quota.stato else '?'}")
    if ris.fermato_per:
        stampa(f"Fermato per: {ris.fermato_per} (NON e' un errore: si riprende al prossimo giro da cio' che manca).")
    stampa(f"Vuoti definitivi dell'API (non buchi, l'API non ha il dato): {vuoti_def} partite-tabella.")
    stampa(f"Quote fuori finestra API (partite di oltre 7 gg: storico quote API 7 gg, NON recuperabili, "
           f"non chiamate): {non_disp} partite.")
    stampa(f"Stagioni passate non ancora verificate (a rotazione, {len(voci)} verificate stanotte): "
           f"{conti.get('passate_non_verificate', 0)}; passate con 0 partite in DB gia' note: "
           f"{conti.get('passate_mai_caricate', 0)} (vedi STAGIONI MAI CARICATE).")
    for r in rinviati:
        stampa(f"RINVIATO (quota/tempo/action concorrente): {r}")
    if rinviati:
        stampa(f"Stima per chiudere i buchi aperti con la capacita' giornaliera ({capacita} chiamate): "
               f"~{math.ceil(costo_tot / capacita)} giorni.")
    for e in ris.errori:
        stampa(f"ERRORE: {e}")
    for f in falliti:
        stampa(f"BUCO VECCHIO: {f}")
    referto_p4(ris, stampa, margine_medio)
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
    concorrenza = ControlloConcorrenza()
    # riserva dinamica: piena finche' Daily/Today/Results di oggi non hanno finito, poi residua
    quota = GestoreQuota(sb=sb, api_key=API_FOOTBALL_KEY, client=client,
                         action_completate=getattr(concorrenza, "action_completate_oggi", None))
    try:
        ris = esegui_catchup(sb, client, quota, concorrenza)
    except (QuotaNonLeggibile, sg.MigrazioneMancante) as e:
        print(f"CATCHUP NON PARTITO: {e}")
        return 2
    return ris.codice


if __name__ == "__main__":
    sys.exit(main())
