"""atlante_v4.py - ATLANTE HAZARD v4: la variante vincente del banco di validazione.

COLLEGATO (25/09/2026 sera, ordine dell'utente "D2: COLLEGALO!"): il
generatore (``genera_atlante``) e il motore a domanda accumulano lo stato v4
per lega insieme al v3 e scrivono il blocco ``atlas['v4']``; Safe
(``_hazard_check``) e Mike (``live_frame``) consultano ``consulta_atlante_v4``
col ``tempo`` dal feed (``tempo_da_payload``). Senza blocco v4 (o per una lega
non ancora nel v4) si ripiega sul v3 e lo si DICHIARA nella nota. Soglie e
decisioni delle strategie invariate. Referti:
``AUDIT_2026-09-25/VALIDAZIONE_HAZARD.md``, ``AUDIT_2026-09-25/ATLANTE_V4_COLLEGATO.md``.

Cosa cambia rispetto al v3 (misurato fuori campione, 2025, vedi referto):
  1. VERITA' A TEMPO REALE: i gol del recupero stanno nel recupero (45+e, 90+e),
     non clampati a 45/90; la finestra "prossimi k minuti" non attraversa
     l'intervallo; i minuti 88-89 contano (il v3 si fermava all'87).
  2. RECUPERO DEL 2T MODELLATO: tasso di gol per minuto di recupero r(lega, gol)
     x durata del recupero D ~ pi(lega) stimata dai dati (``status.extra`` di
     API-Football, dal 2024), per lega shrinkata verso il campione (K dal metodo
     dei momenti). Al 90+j, partita VIVA: P_k = 1 - E[exp(-r min(k, D-j)) | D > j].
     Decisione dell'utente (25/09): in live il recupero e' la stima per lega.
  3. RECUPERO DEL 1T (con ``tempo=1``): la cella 40-45 della lega, contata sulla
     verita' vera (una cella propria si stima, ma non e' validata: vedi
     ``consulta_atlante_v4``).
  6. STAGIONI SENZA RECUPERO REGISTRATO (``stagione_recupero_affidabile``): solo
     gli stati lontani dalla fine dei tempi entrano nei conteggi.
  4. STAGIONI PESATE: emivita ``EMIVITA`` stagioni (scelta in validazione).
  5. FORZA PRE-PARTITA: moltiplicatore hazard ((lambda_casa+lambda_trasf) /
     gol medi della lega) ** beta, se il chiamante passa i lambda (Safe li ha:
     ``_hazard_check(lambdas=...)``; Mike ``lambdas_con_ripiego``). Senza lambda
     il moltiplicatore e' 1 e lo si dichiara.
NON entrano (misurato: nessun guadagno fuori campione): differenza reti/chi
conduce oltre ai gol totali, moltiplicatore dei rossi, K dal metodo dei momenti
per le celle (resta 1500).

STATO GREZZO per lega (additivo, PER STAGIONE, cosi' i pesi d'eta' si applicano
all'assemblaggio e l'aggiornamento resta incrementale):
  stagioni[s] = {n_fixtures, gol, celle[NT*NG*3] (n, s2, s3), rec2[NG*2]
                 (esposizione, gol), durate{d: partite}}
PURO: nessuna rete, nessun flumine (vedi il perche' in ``hazard_atlas``).
"""
from __future__ import annotations

import datetime as _dt
import logging
import math
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np

from Betfair.stream.scalper import genera_atlante as G
from Betfair.stream.scalper.hazard_atlas import (_conf_cella, consulta_atlante, eta_atlante, etichetta_atlante,
                                                  leghe_in_preparazione)
from Betfair.stream.scalper.validazione_hazard import candidati as CA
from Betfair.stream.scalper.validazione_hazard.dati import (EXTRA_MAX_VALIDO, MIN_GOL_BLOCCO,
                                                            SOGLIA_RECUPERO_REGISTRATO, Partita, lati_gol,
                                                            posizione, quota_gol_con_extra)
from Betfair.stream.scalper.validazione_hazard.stati import stati_partita

logger = logging.getLogger(__name__)

VERSIONE = "hazard_atlas_v4"
EMIVITA = 3.0                     # stagioni (validazione 2024: migliore fra 2, 3, 5, nessuna)
K_CELLE = 1500.0                  # come il v3 (il metodo dei momenti non ha vinto)
# beta della forza pre-partita, stimato dal banco (massima verosimiglianza) su
# <=2024 coi lambda del proxy Poisson-Elo: 0,612 (2') e 0,610 (3'). ATTENZIONE
# (referto §4): coi lambda di fixture_predictions il guadagno della forza sparisce.
BETA_DEFAULT = {2: 0.612, 3: 0.610}
MIN_PARTITE_AFFIDABILE = CA.MIN_PARTITE_AFFIDABILE
NT, NG, D_MAX = CA.NT, CA.NG, CA.D_MAX
ETICHETTE_TC = ([f"{5 * b}-{5 * b + 5}" for b in range(18)] + ["45+"]
                + [f"90+{x}" for x in ("0", "1", "2", "3", "4", "5", "6-7", "8+")])


# ---------------------------------------------------------------------------
# 1) la partita: righe del DB -> Partita (stesse regole della produzione)
# ---------------------------------------------------------------------------
def partita_v4(match: Dict[str, Any], eventi: Iterable[Dict[str, Any]], *,
               eventi_recupero: bool = False) -> Tuple[Optional[Partita], str]:
    """(Partita, 'ok') o (None, motivo). Accettazione IDENTICA a
    ``genera_atlante.sequenza_partita``. In piu' servono: ``match['extra']``
    (= raw_json->fixture->status->extra, il recupero del 2T) e, per il
    recupero del 1T, gli eventi NON-gol con ``minute_extra`` (``eventi_recupero``).
    Con i soli gol (la lettura di oggi del generatore) il recupero del 2T usa
    ``extra`` e i gol, quello del 1T resta al ripiego."""
    evs = list(eventi)
    gol_rows = [e for e in evs if str(e.get("event_type")) == "Goal"]
    seq, motivo = G.sequenza_partita(match, gol_rows)
    if seq is None:
        return None, motivo
    lati = lati_gol(match, gol_rows)
    if lati is None:
        return None, "lati_incoerenti"
    p = Partita(fixture_id=int(seq["fixture_id"]), league_id=int(seq["league_id"]), season=int(seq["season"]),
                date=str(seq.get("date") or ""), home_id=int(seq["home_id"]), away_id=int(seq["away_id"]),
                home_name=seq.get("home_name"), away_name=seq.get("away_name"), ft=(int(seq["ft"][0]),
                                                                                   int(seq["ft"][1])))
    for r, lato in lati:
        pos = posizione(r.get("minute"), r.get("minute_extra"))
        p.gol.append((pos[0], pos[1], lato))
    p.gol.sort(key=lambda g: (g[0], g[1]))
    lb2 = lb1 = 0
    for e in evs:
        pos = posizione(e.get("minute"), e.get("minute_extra"))
        if pos is None or pos[1] <= 45:
            continue
        if pos[0] == 2:
            lb2 = max(lb2, pos[1] - 45)
        elif str(e.get("event_type")) != "Goal":
            lb1 = max(lb1, pos[1] - 45)
    try:
        ex = int(match.get("extra")) if match.get("extra") is not None else None
    except (TypeError, ValueError):
        ex = None
    if ex is not None and 0 <= ex <= EXTRA_MAX_VALIDO:
        p.d2 = max(ex, lb2)
    p.eventi_recupero = bool(eventi_recupero)
    p.s1_vivo = lb1 if eventi_recupero else 0
    return p, "ok"


# ---------------------------------------------------------------------------
# 2) stato grezzo per lega (additivo, per stagione)
# ---------------------------------------------------------------------------
def stato_lega_v4_vuoto(league_id: int, league_name: Optional[str] = None) -> Dict[str, Any]:
    return {"league_id": int(league_id), "league_name": league_name, "stagioni": {}, "fixtures": []}


def _blocco_stagione() -> Dict[str, Any]:
    return {"n_fixtures": 0, "gol": 0, "celle": [0.0] * (NT * NG * 3), "rec2": [0.0] * (NG * 2),
            "durate": {}}


def stagione_recupero_affidabile(goal_rows: Iterable[Dict[str, Any]]) -> bool:
    """La (lega, stagione) registra il minuto di recupero dei gol? Reperto del
    25/09: nella stagione 2025 delle leghe europee i gol del recupero sono nel DB
    come 45'/90' SENZA ``minute_extra`` (anche ``raw_json.time.extra`` NULL): la
    quota di gol di fine tempo con extra e' 0,00-0,28 contro 0,73-0,96 di tutte
    le stagioni 2016-2024. Sotto ``SOGLIA_RECUPERO_REGISTRATO`` (0,6) con almeno
    ``MIN_GOL_BLOCCO`` gol di fine tempo la stagione NON e' affidabile per la fine
    dei tempi. Pochi gol di fine tempo: si presume affidabile."""
    con, tot = quota_gol_con_extra(goal_rows)
    return tot < MIN_GOL_BLOCCO or (con / tot) >= SOGLIA_RECUPERO_REGISTRATO


def affidabile_da_quota(con: int, tot: int) -> bool:
    """La stessa regola di ``stagione_recupero_affidabile`` sui conteggi
    (gol di fine tempo con extra, gol di fine tempo): serve all'incrementale,
    che vede la stagione a pezzi e ne tiene i conteggi CUMULATI nello stato."""
    return int(tot) < MIN_GOL_BLOCCO or (int(con) / int(tot)) >= SOGLIA_RECUPERO_REGISTRATO


def stato_v4_vuoto() -> Dict[str, Any]:
    """Il blocco v4 DENTRO lo stato grezzo di una lega del generatore
    (``stato['v4']``). Niente lista di fixture_id propria: l'idempotenza e'
    quella del v3 (``aggiungi_partita``), la partita entra nel v4 solo se il v3
    l'ha appena contata. ``quota_extra[stagione] = [con, tot]`` (gol di fine
    tempo con/senza minute_extra) e ``affidabile[stagione]`` servono alla
    regola del reperto 6; ``scarti`` conta le partite che il v3 ha preso e il
    v4 no (atteso: zero, stesse regole)."""
    return {"versione": 1, "stagioni": {}, "quota_extra": {}, "affidabile": {}, "scarti": {}}


def aggiungi_partita_v4(stato: Dict[str, Any], p: Partita, visti: Optional[set] = None, *,
                        recupero_affidabile: bool = True, registra_fixture: bool = True) -> bool:
    """Somma una partita. False se gia' contata (idempotenza per fixture_id).

    ``recupero_affidabile=False`` (vedi ``stagione_recupero_affidabile``): si
    contano SOLO gli stati le cui finestre non toccano la fine del tempo
    (t <= 41 in ogni tempo); niente recupero, niente durata. I gol del recupero
    registrati al 45'/90' altrimenti gonfierebbero le celle 40-45/85-90 e
    svuoterebbero il recupero.

    ``registra_fixture=False`` (generatore, 25/09 sera): il fixture_id NON si
    aggiunge a ``stato['fixtures']`` (l'idempotenza e' del v3: niente seconda
    lista di ~40 KB per lega). I conteggi si salvano INTERI (sono conteggi:
    stesso valore, JSON piu' corto)."""
    if visti is None:
        visti = set(stato.get("fixtures") or [])
    if p.fixture_id in visti:
        return False
    S = stati_partita(p, 0)
    if not recupero_affidabile:
        tieni = (S["stop"] == 0) & (S["t"] <= 41)
        S = {k: v[tieni] for k, v in S.items()}
    idx = np.arange(S["y3"].size)
    tc = CA.cella_tempo(S, idx)
    gk = CA.gol_key(S, idx)
    blk = stato["stagioni"].setdefault(str(p.season), _blocco_stagione())
    celle = np.asarray(blk["celle"], dtype=float).reshape(NT, NG, 3)
    np.add.at(celle, (tc, gk, 0), 1.0)
    np.add.at(celle, (tc, gk, 1), S["y2"].astype(float))
    np.add.at(celle, (tc, gk, 2), S["y3"].astype(float))
    blk["celle"] = _conteggi(celle)
    rec = (S["stop"] == 1) & (S["tempo"] == 2)
    if rec.any():
        r2 = np.asarray(blk["rec2"], dtype=float).reshape(NG, 2)
        np.add.at(r2, (gk[rec], 0), 1.0)
        np.add.at(r2, (gk[rec], 1), S["g1"][rec].astype(float))
        blk["rec2"] = _conteggi(r2)
        d = str(min(int(p.d2 or 0), D_MAX))
        blk["durate"][d] = int(blk["durate"].get(d, 0)) + 1
    blk["n_fixtures"] += 1
    blk["gol"] += int(sum(p.ft))
    if registra_fixture:
        stato.setdefault("fixtures", []).append(p.fixture_id)
    visti.add(p.fixture_id)
    return True


def _conteggi(a: np.ndarray) -> List[Any]:
    """Conteggi (interi per costruzione) come lista JSON: interi se lo sono."""
    piatto = np.asarray(a, dtype=float).reshape(-1)
    if np.all(piatto == np.round(piatto)):
        return piatto.astype(np.int64).tolist()
    return piatto.tolist()


# ---------------------------------------------------------------------------
# 3) assemblaggio: dagli stati grezzi al blocco "v4" dell'atlante
# ---------------------------------------------------------------------------
def _peso(stagione: int, rif: int, emivita: Optional[float]) -> float:
    if not emivita:
        return 1.0
    return 0.5 ** ((rif - stagione) / float(emivita))


def assembla_v4(stati: Dict[str, Dict[str, Any]], *, generated_at: str, stagione_rif: int,
                emivita: Optional[float] = EMIVITA, k_celle: float = K_CELLE,
                beta: Optional[Dict[int, float]] = None) -> Dict[str, Any]:
    """Il blocco ``v4`` (da mettere in ``atlas['v4']`` accanto ai blocchi v3,
    che restano per i consumatori di oggi). ``stagione_rif``: la stagione a peso
    1 (quella in corso: la prima NON contata)."""
    beta = dict(beta or BETA_DEFAULT)
    leghe = sorted(stati, key=int)
    L = len(leghe)
    n = np.zeros((L, NT, NG))
    s = {2: np.zeros((L, NT, NG)), 3: np.zeros((L, NT, NG))}
    E = np.zeros((L, NG))
    Gs = np.zeros((L, NG))
    dur = np.zeros((L, D_MAX + 1))
    part = np.zeros(L)
    part_w = np.zeros(L)
    gol_w = np.zeros(L)
    for i, lid in enumerate(leghe):
        for st, blk in (stati[lid].get("stagioni") or {}).items():
            w = _peso(int(st), stagione_rif, emivita)
            c = np.asarray(blk["celle"], dtype=float).reshape(NT, NG, 3)
            n[i] += w * c[:, :, 0]
            s[2][i] += w * c[:, :, 1]
            s[3][i] += w * c[:, :, 2]
            r2 = np.asarray(blk["rec2"], dtype=float).reshape(NG, 2)
            E[i] += w * r2[:, 0]
            Gs[i] += w * r2[:, 1]
            for d, k in (blk.get("durate") or {}).items():
                dur[i, min(int(d), D_MAX)] += w * float(k)
            part[i] += int(blk["n_fixtures"])
            part_w[i] += w * int(blk["n_fixtures"])
            gol_w[i] += w * int(blk["gol"])
    affid = part >= MIN_PARTITE_AFFIDABILE
    n_affid = int(part[affid].sum())
    # 25/09 sera (collegamento): il globale v4 si stima sulle leghe affidabili
    # come nel banco; e' "solido" (usabile per una lega che il v4 non ha, o
    # per shrinkare una lega piccola) solo da MIN_FIXTURES_GLOBALE partite,
    # la stessa soglia del globale v3 (sotto, il v3 usa il seme; qui il
    # consumatore ripiega sul v3 e lo dichiara). Nessuna lega affidabile:
    # il globale si stima su tutte (come il v3, ``base = coperte or stati``),
    # mai una cella NaN.
    globale_solido = n_affid >= G.MIN_FIXTURES_GLOBALE
    if L and not affid.any():
        affid = np.ones(L, dtype=bool)
    out: Dict[str, Any] = {"meta": {
        "name": VERSIONE, "generated_at": generated_at, "stagione_rif": stagione_rif,
        "emivita": emivita, "k_celle": k_celle, "beta": {str(k): v for k, v in beta.items()},
        "n_leghe": L, "n_leghe_affidabili": int((part >= MIN_PARTITE_AFFIDABILE).sum()),
        "n_partite_affidabili": n_affid, "globale_solido": bool(globale_solido),
        "min_partite_globale": int(G.MIN_FIXTURES_GLOBALE), "ripieghi": [],
        "etichette_tc": ETICHETTE_TC,
        "metodo": "vedi docstring di Betfair/stream/scalper/atlante_v4.py e "
                  "AUDIT_2026-09-25/VALIDAZIONE_HAZARD.md"}, "global": {}, "by_league": {}}
    glob: Dict[str, Any] = {}
    p_lega: Dict[int, np.ndarray] = {}
    for k in (2, 3):
        nn, ss = n.copy(), s[k].copy()
        ng, sg = nn[affid].sum(0), ss[affid].sum(0)
        with np.errstate(invalid="ignore", divide="ignore"):
            pg = np.where(ng > 0, sg / np.maximum(ng, 1e-12), np.nan)
        for tcx, rip in [(CA.TC_REC1, 8)] + [(CA.TC_REC2 + b, 17) for b in range(CA.N_JB)]:
            vuote = ~np.isfinite(pg[tcx]) | (ng[tcx] <= 0)
            pg[tcx] = np.where(vuote, pg[rip], pg[tcx])
            if vuote.any():
                if k == 3:
                    out["meta"]["ripieghi"].append([ETICHETTE_TC[tcx], ETICHETTE_TC[rip]])
                nn[:, tcx] = np.where(vuote[None, :], nn[:, rip], nn[:, tcx])
                ss[:, tcx] = np.where(vuote[None, :], ss[:, rip], ss[:, tcx])
        pg = np.where(np.isfinite(pg), pg, np.nanmean(pg))
        glob[f"p{k}"] = pg
        p_lega[k] = (ss + k_celle * pg[None]) / (nn + k_celle)
        if k == 3:
            n_eff = nn
    # recupero del 2T: tasso per minuto e durata
    Eg, Gg = E[affid].sum(0), Gs[affid].sum(0)
    if Eg.sum() <= 0:
        Eg, Gg = E.sum(0), Gs.sum(0)
    tot_r = Gg.sum() / max(Eg.sum(), 1e-12)
    rg = np.where(Eg > 0, Gg / np.maximum(Eg, 1e-12), tot_r)
    r_lega = (Gs + k_celle * rg[None]) / (E + k_celle)
    pool = dur.sum(0)
    ha_durate = pool.sum() > 0
    pool = pool / pool.sum() if ha_durate else pool
    medie, var_c, nl = [], [], []
    dd = np.arange(D_MAX + 1)
    for i in range(L):
        tot = dur[i].sum()
        if tot >= 30:
            mu = (dur[i] * dd).sum() / tot
            medie.append(mu)
            var_c.append(((dur[i] * (dd - mu) ** 2).sum() / tot) / tot)
            nl.append(tot)
    kd = 50.0
    if len(medie) >= 3:
        tau2 = float(np.var(medie, ddof=1) - np.mean(var_c))
        sig2 = float(np.mean(np.array(var_c) * np.array(nl)))
        kd = sig2 / tau2 if tau2 > 0 else 1e9
    pi_lega = (dur + kd * pool[None]) / (dur.sum(1, keepdims=True) + kd)
    gol_medi = np.where(part_w > 0, gol_w / np.maximum(part_w, 1e-12), np.nan)
    gol_medi_glob = float(np.nanmean(gol_medi)) if np.isfinite(gol_medi).any() else 2.7
    out["meta"].update({"k_durata": kd, "recupero_2T_noto": bool(ha_durate),
                        "durata_media_campione": float((pool * dd).sum()) if ha_durate else None})
    out["global"] = {"p2": _r(glob["p2"]), "p3": _r(glob["p3"]), "r_rec2": _r(rg),
                     "pi_durata": _r(pool) if ha_durate else None, "gol_medi": round(gol_medi_glob, 5)}
    for i, lid in enumerate(leghe):
        out["by_league"][lid] = {
            "league_name": stati[lid].get("league_name"), "n_fixtures": int(part[i]),
            "affidabile": bool(part[i] >= MIN_PARTITE_AFFIDABILE),
            "p2": _r(p_lega[2][i]), "p3": _r(p_lega[3][i]), "n": _r(n_eff[i], 1),
            "r_rec2": _r(r_lega[i]), "esposizione_rec2": _r(E[i], 1),
            "pi_durata": _r(pi_lega[i]) if ha_durate else None,
            "durata_media": round(float((pi_lega[i] * dd).sum()), 3) if ha_durate else None,
            "gol_medi": round(float(gol_medi[i]), 5) if np.isfinite(gol_medi[i]) else None}
    return out


def _r(a: np.ndarray, nd: int = 7) -> Any:
    return np.round(np.asarray(a, dtype=float), nd).tolist()


# ---------------------------------------------------------------------------
# 4) consultazione in live
# ---------------------------------------------------------------------------
# Il TEMPO (1T/2T) dal feed. MISURATO il 25/09 sulle 60 registrazioni vere dei
# punteggi IPS Betfair (``_live_raw/<id>/<id>.scores.jsonl``, 7.539 righe;
# sonda ``AUDIT_2026-09-25/sonde/sonda_minuto_ips_recupero.py``):
#   * ``matchStatus`` nel 1T e' 'KickOff' (mai 'FirstHalf' sul vero; 'FirstHalf'
#     solo nei sintetici), all'intervallo 'FirstHalfEnd', nel 2T
#     'SecondHalfKickOff', a fine partita 'Finished';
#   * nel RECUPERO del 1T il minuto e' CUMULATO: timeElapsed 46, 47, ... con
#     elapsedRegularTime 45 e elapsedAddedTime 1, 2, ... (NON 45 fisso); il
#     ``minute`` del feed e' timeElapsed. Senza il tempo un 46' del recupero
#     del 1T e' indistinguibile dal 46' della ripresa;
#   * nel recupero del 2T: timeElapsed 91.. con elapsedRegularTime 90 e
#     elapsedAddedTime = minuto - 90 (il GIOCATO, non l'annunciato: la durata
#     annunciata non c'e', quindi resta la stima per lega);
#   * all'INTERVALLO ('FirstHalfEnd') timeElapsed riparte da 45 e continua a
#     contare (35674515: 45 -> 56 in 13'): e' ancora tempo 1 (nessun atlante
#     modella l'intervallo; il v4 da' la cella 40-45, il v3 dava 45-55);
#   * uno stato puo' restare VECCHIO (35833626: 'KickOff' con timeElapsed 88 e
#     elapsedRegularTime 35): un 1T IN GIOCO dichiarato con un minuto oltre
#     ``_MAX_MINUTO_1T`` non si crede, si torna alla regola del minuto.
_MAX_MINUTO_1T = 60          # 45 + 15 di recupero: oltre, uno stato "1T in gioco" e' vecchio
_STATI_INTERVALLO = ("firsthalfend", "halftime")
_STATI_1T = ("firsthalf",)
_STATI_2T = ("secondhalf", "extratime", "penalt")


def tempo_da_stato_ips(raw: Optional[Dict[str, Any]], minute: Optional[float]) -> Optional[int]:
    """1 o 2 (tempo in corso) dallo stato IPS grezzo (``score_raw``) e dal
    minuto del feed; None se non si sa (il v4 allora fa come il v3: dal 46'
    e' ripresa). PURO, mai eccezioni."""
    try:
        m = int(minute) if minute is not None else None
    except (TypeError, ValueError):
        m = None
    st = ""
    if isinstance(raw, dict):
        st = "".join(ch for ch in str(raw.get("matchStatus") or raw.get("status") or "").lower()
                     if ch.isalpha())
    if st:
        if any(k in st for k in _STATI_2T):
            return 2
        if any(k in st for k in _STATI_INTERVALLO):
            return 1
        if any(k in st for k in _STATI_1T) or st == "kickoff":
            if m is None or m <= _MAX_MINUTO_1T:
                return 1
    if isinstance(raw, dict):
        try:
            reg = raw.get("elapsedRegularTime")
            reg = int(reg) if reg is not None else None
        except (TypeError, ValueError):
            reg = None
        if reg is not None and raw.get("elapsedAddedTime") is not None and reg in (45, 90) \
                and (m is None or m <= reg + 30):
            return 1 if reg == 45 else 2
    if m is None:
        return None
    if m < 45:
        return 1
    if m >= 90:
        return 2
    return None               # 45-89 senza stato: ambiguo, si lascia la regola del v3


def tempo_da_payload(payload: Optional[Dict[str, Any]]) -> Optional[int]:
    """``tempo_da_stato_ips`` sul payload del feed unico (``score_raw`` +
    ``minute``), la riga che Safe e Mike ricevono."""
    if not isinstance(payload, dict):
        return None
    return tempo_da_stato_ips(payload.get("score_raw"), payload.get("minute"))


def _fase(minute: float, tempo: Optional[int]) -> Tuple[str, int, int]:
    """(fase, cella di tempo, j). tempo=1 e minuto >= 45: recupero del 1T;
    minuto >= 90: recupero del 2T (j = minuto - 90); altrimenti bucket regolare.
    Senza ``tempo`` un 46' e' secondo tempo (come il v3)."""
    m = max(0, int(minute))
    if tempo == 1 and m >= 45:
        return "recupero_1T", CA.TC_REC1, m - 45
    if m >= 90:
        j = m - 90
        return "recupero_2T", CA.TC_REC2 + int(CA.J_BIN[min(j, 8)]), j
    return "regolare", m // 5, 0


def _p_recupero2(r: float, pi: Optional[List[float]], j: int, k: int) -> Tuple[float, Optional[float]]:
    """(P, minuti di recupero attesi ancora da giocare) al 90+j, partita viva."""
    if not pi:
        return 1.0 - math.exp(-r), None
    pi_a = np.asarray(pi, dtype=float)
    d = np.arange(pi_a.size)
    vivo = d > j
    massa = float((pi_a * vivo).sum())
    if massa <= 0:
        return 1.0 - math.exp(-r), None
    resto = np.minimum(k, np.maximum(d - j, 0))
    sopr = float((pi_a * vivo * np.exp(-r * resto)).sum())
    atteso = float((pi_a * vivo * (d - j)).sum() / massa)
    return 1.0 - sopr / massa, atteso


def _motivo_ripiego_v3(atlas: Dict[str, Any], v4: Dict[str, Any], league_id: Optional[Any]) -> Optional[str]:
    """Perche' questa consultazione va sul v3 (None = si usa il v4).

    Solo quando l'atlante porta ANCHE i blocchi v3 (``global``: in produzione
    sempre, nel banco mai - li' il comportamento resta quello validato):
      * la lega non e' nel v4 ma il v3 la conosce (stato di prima del
        collegamento non ancora ricalcolato, o lega del seme): la lega del v3
        batte il globale v4 per la parte regolare, ed e' cio' che si usava ieri;
      * la lega non e' nel v4 e il globale v4 non e' ancora solido;
      * la lega e' nel v4 con poche partite (non affidabile) e il globale v4,
        verso cui la si shrinka, non e' ancora solido.
    ``meta.globale_solido`` assente (blocco del banco) = solido."""
    if not isinstance((atlas or {}).get("global"), dict) or not atlas.get("global"):
        return None
    meta = v4.get("meta") or {}
    solido = bool(meta.get("globale_solido", True))
    lid = str(league_id) if league_id is not None else None
    lg = (v4.get("by_league") or {}).get(lid) if lid is not None else None
    if isinstance(lg, dict):
        if lg.get("affidabile") or solido:
            return None
        return f"lega {lid} con {lg.get('n_fixtures')} partite nel v4 e globale v4 non ancora solido"
    if lid is not None and lid in (atlas.get("by_league") or {}):
        return f"lega {lid} non ancora nel v4"
    if not solido:
        return (f"globale v4 non ancora solido ({meta.get('n_partite_affidabili')} partite "
                f"< {meta.get('min_partite_globale')})")
    return None


def _ripiego_v3(atlas: Optional[Dict[str, Any]], minute: float, goals: int, league_id: Optional[Any],
                motivo: str, *, tempo: Optional[int], horizon: str, adesso: Optional[_dt.datetime],
                **kw_v3: Any) -> Dict[str, Any]:
    """``consulta_atlante`` (v3) con le chiavi del v4 e il ripiego DICHIARATO.
    Il minuto al v3 e' quello di sempre (il v3 non conosce il tempo: un 46' del
    recupero del 1T per il v3 e' la ripresa, com'era ieri)."""
    out = consulta_atlante(atlas, minute, goals, league_id, horizon=horizon, adesso=adesso, **kw_v3)
    try:
        fase = _fase(minute, tempo)[0]
    except (TypeError, ValueError):
        fase = None
    k = "p_goal_next_2min" if "2min" in horizon else "p_goal_next_3min"
    out.update(versione="v3", fase=fase, recupero_atteso_min=None,
               p_2min=out["p"] if k.endswith("2min") else None,
               p_3min=out["p"] if k.endswith("3min") else None,
               forza={"moltiplicatore": 1.0, "usata": False}, ripiego_v3=motivo)
    out["nota"] = f"{out.get('nota')} [atlante v3: recupero non modellato ({motivo})]"
    return out


def consulta_atlante_v4(atlas: Optional[Dict[str, Any]], minute: float, goals: int,
                        league_id: Optional[Any] = None, *, tempo: Optional[int] = None,
                        lambda_home: Optional[float] = None, lambda_away: Optional[float] = None,
                        horizon: str = "p_goal_next_3min", usa_cella_recupero_1t: bool = False,
                        adesso: Optional[_dt.datetime] = None, **kw_v3: Any) -> Dict[str, Any]:
    """Stesse chiavi di ``hazard_atlas.consulta_atlante`` (p, fonte, livello, n,
    confidenza, lega, atlante, eta_giorni, nota) + ``versione``, ``fase``
    ('regolare'|'recupero_1T'|'recupero_2T'), ``p_2min``, ``p_3min``,
    ``recupero_atteso_min`` (solo 2T), ``forza`` {'moltiplicatore', 'usata'}.
    Senza blocco v4 nell'atlante: ripiego su ``consulta_atlante`` (dichiarato,
    ``versione='v3'``). Mai eccezioni.

    Recupero del 1T (serve ``tempo=1``): per DEFAULT si usa la cella 40-45 della
    lega (``usa_cella_recupero_1t=False``). La cella propria del recupero 1T non
    e' mai stata validata (il DB non ha la durata del recupero del 1T; il
    campione "vivo per evento successivo" e' parziale) e sul test 2025 non vince
    (referto §4): resta disponibile solo per misure."""
    v4 = (atlas or {}).get("v4")
    if not isinstance(v4, dict):
        return _ripiego_v3(atlas, minute, goals, league_id, "blocco v4 assente", tempo=tempo,
                           horizon=horizon, adesso=adesso, **kw_v3)
    motivo = _motivo_ripiego_v3(atlas, v4, league_id)
    if motivo:
        return _ripiego_v3(atlas, minute, goals, league_id, motivo, tempo=tempo, horizon=horizon,
                           adesso=adesso, **kw_v3)
    k_req = 2 if "2min" in horizon else 3
    out: Dict[str, Any] = {"p": None, "fonte": "none", "livello": "nessuno", "n": None, "confidenza": None,
                           "lega": {"coperta": False, "in_preparazione": False, "n_partite": None,
                                    "confidenza": None, "nome": None, "affidabile": False, "da_seme": False},
                           "atlante": etichetta_atlante(atlas, adesso), "eta_giorni": None,
                           "nota": "atlante assente", "versione": "v4", "fase": None,
                           "p_2min": None, "p_3min": None, "recupero_atteso_min": None,
                           "forza": {"moltiplicatore": 1.0, "usata": False}, "ripiego_v3": None}
    try:
        e = eta_atlante(atlas, adesso)
        out["eta_giorni"] = round(e["giorni"], 2) if e["giorni"] is not None else None
        meta = v4.get("meta") or {}
        fase, tc, j = _fase(minute, tempo)
        if fase == "recupero_1T" and not usa_cella_recupero_1t:
            tc = 8                              # cella 40-45 della lega (vedi docstring)
        gk = min(max(0, int(goals)), 3)
        out["fase"] = fase
        lid = str(league_id) if league_id is not None else None
        lg = (v4.get("by_league") or {}).get(lid) if lid is not None else None
        glob = v4.get("global") or {}
        src = lg if isinstance(lg, dict) else glob
        fonte = "league" if isinstance(lg, dict) else "global"
        if isinstance(lg, dict):
            nf = lg.get("n_fixtures")
            out["lega"].update(coperta=True, n_partite=nf, nome=lg.get("league_name"),
                               affidabile=bool(lg.get("affidabile")),
                               confidenza="alta" if (nf or 0) >= MIN_PARTITE_AFFIDABILE else
                               ("media" if (nf or 0) >= 100 else "bassa"))
        elif lid is not None and lid in leghe_in_preparazione(atlas):
            out["lega"]["in_preparazione"] = True     # il motore a domanda la sta calcolando
        ref = (lg or {}).get("gol_medi") or glob.get("gol_medi")
        mult = 1.0
        if lambda_home and lambda_away and ref:
            try:
                lt = float(lambda_home) + float(lambda_away)
                if lt > 0 and math.isfinite(lt):
                    mult = min(5.0, max(0.2, lt / float(ref)))
                    out["forza"]["usata"] = True
            except (TypeError, ValueError):
                mult = 1.0
        beta = meta.get("beta") or {}
        ps = {}
        for k in (2, 3):
            if fase == "recupero_2T" and src.get("r_rec2") is not None and meta.get("recupero_2T_noto"):
                p, att = _p_recupero2(float(src["r_rec2"][gk]), src.get("pi_durata") or glob.get("pi_durata"),
                                      j, k)
                out["recupero_atteso_min"] = round(att, 2) if att is not None else None
            else:
                p = float(src[f"p{k}"][tc][gk])
            if out["forza"]["usata"]:
                b = float(beta.get(str(k), BETA_DEFAULT[k]))
                out["forza"]["moltiplicatore"] = round(mult ** b, 4)
                p = 1.0 - (1.0 - p) ** (mult ** b)
            ps[k] = p
        out["p_2min"], out["p_3min"] = ps[2], ps[3]
        out["p"] = ps[k_req]
        out["fonte"] = fonte
        out["livello"] = {"league": "lega", "global": "globale"}[fonte]
        if fase != "recupero_2T" and isinstance(lg, dict):
            out["n"] = lg["n"][tc][gk]
        elif fase == "recupero_2T" and isinstance(lg, dict):
            out["n"] = lg["esposizione_rec2"][gk]
        if out["n"] is not None:
            conf = _conf_cella(out["n"], float(meta.get("k_celle") or K_CELLE))
            if out["lega"]["confidenza"]:
                ordine = {"bassa": 0, "media": 1, "alta": 2}
                conf = min(conf, out["lega"]["confidenza"], key=lambda c: ordine[c])
            out["confidenza"] = conf
        out["nota"] = _nota(out, lid)
    except Exception as ex:  # noqa: BLE001 - l'atlante non ferma mai nessuno
        logger.debug("[atlante-v4] consulta KO: %s", str(ex)[:120])
        out.update(p=None, fonte="none", livello="nessuno", nota="atlante v4 illeggibile")
    return out


def _nota(c: Dict[str, Any], lid: Optional[str]) -> str:
    lega = c["lega"]
    chi = lega.get("nome") or (f"lega {lid}" if lid else "lega n/d")
    base = (f"storico v4 {chi} ({c['livello']}, {lega.get('n_partite')} partite)" if c["fonte"] == "league"
            else f"storico v4 globale (lega {lid or 'n/d'} senza dati)")
    extra = [c["fase"]]
    if c.get("recupero_atteso_min") is not None:
        extra.append(f"recupero atteso ancora {c['recupero_atteso_min']}'")
    extra.append(f"forza x{c['forza']['moltiplicatore']}" if c["forza"]["usata"] else "forza non usata")
    if c.get("confidenza"):
        extra.append(f"confidenza {c['confidenza']}")
    if c.get("atlante"):
        extra.append(c["atlante"])
    return base + " [" + "; ".join(extra) + "]"
