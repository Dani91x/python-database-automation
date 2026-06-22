"""analytics_market_stats.py — logica PURA per FREQUENZE e RITARDI point-in-time
per OGNI (lega × mercato × selezione), replica ESATTA della matematica certificata
degli RPC get_market_frequency / get_market_delays.

⚠️ SOLDI IN GIOCO: gli utenti scommettono su questi numeri. La matematica qui DEVE
combaciare riga-per-riga con gli RPC (certificato in test_analytics_market_stats.py).

PRINCIPIO PER-SELEZIONE: freq/ritardo sono DIVERSI per ogni selezione.
  "Over 2.5" ≠ "Under 2.5"; "H" ≠ "D" ≠ "A". Ogni (fixture, market, selection)
  riceve lo snapshot DELLA SUA selezione, calcolato sulla SUA serie binaria.

──────────────────────────────────────────────────────────────────────────────
MATEMATICA REPLICATA (1:1 con gli RPC):

FREQUENZE (get_market_frequency, sql/market_frequency_rpc.sql):
  serie binaria cronologica (ORDER BY fixture_date, fixture_id) degli esiti validi
  (outcome non-None). idx = 1..M.
    baseline       = avg(outcome) su TUTTA la serie (mode='all')
    freq_current   = mm10 = media mobile a finestra PIENA su 10 punti
                     (None per idx < 10 — esattamente come l'RPC)
    freq_deviation = mm10 - baseline   (None se mm10 None)

  NULLITÀ HT: i mercati HT senza primo tempo hanno outcome None → la riga è
  ESCLUSA dalla serie (identico all'RPC, che esclude le righe senza HT). Questo
  è ciò che produce hit() di analytics_settlement (None su HT mancante).

RITARDI (get_market_delays, sql/market_delays_rpc.sql — riproduzione 1:1 Excel):
  serie binaria cronologica degli esiti validi (outcome non-None). idx = 1..M.
    last_hit(i)    = max idx j<=i con outcome=1   (0 se nessuno)
    rit(i)         = i - last_hit(i)              ← ritardo corrente a quella riga
    suc(hit q)     = (q - prev_hit) - 1           ← lunghezza serie chiusa
    delay_current  = rit alla riga di QUELLA fixture (point-in-time)
    delay_record   = max(suc) su tutte le occorrenze   (scalare, tutta la serie)
    delay_avg      = avg(rit) sulle righe con rit != 0  (scalare, = media_ritardi)

  DIVERGENZA HT (volontaria, fedele agli RPC): get_market_delays NON esclude le
  righe senza HT — le tratta con HT=0 (coalesce, comportamento letterale Excel).
  get_market_frequency invece le ESCLUDE. Perciò per i mercati HT-dipendenti la
  SERIE DEI RITARDI usa una settlement che coalesce HT mancante a (0,0), mentre la
  SERIE DELLE FREQUENZE usa hit() (None-escludente). Per i mercati FT le due serie
  COINCIDONO. delay_record/delay_avg sono scalari di serie → uguali per tutte le
  selezioni dello stesso mercato? NO: dipendono dalla selezione (serie diversa).
──────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from analytics_settlement import ft_score_90, ht_score, hit

# Mercati il cui esito dipende dal primo tempo (per la divergenza HT freq vs delay).
_HT_DEPENDENT = (
    "ht_1x2",
    "first_half_btts",
    "first_half_double_chance",
    "ht_ft",
)


def _is_ht_dependent(market: str) -> bool:
    return market in _HT_DEPENDENT or market.startswith("first_half_over_")


@dataclass(frozen=True)
class Snapshot:
    """Snapshot point-in-time per UNA fixture su UNA (market, selection)."""
    freq_baseline: Optional[float]
    freq_current: Optional[float]
    freq_deviation: Optional[float]
    delay_current: Optional[int]
    delay_record: Optional[int]
    delay_avg: Optional[float]


def chrono_key(match: dict) -> tuple:
    """Chiave di ordinamento DETERMINISTICA = (fixture_date, fixture_id),
    identica all'ORDER BY degli RPC. Guardia: fixture_date NULL → stringa vuota
    (ordina prima, niente TypeError None<str); fixture_id NULL → 0."""
    return (match.get("fixture_date") or "", match.get("fixture_id") or 0)


def _hit_freq(market: str, selection: str, match: dict) -> Optional[bool]:
    """Esito per la SERIE FREQUENZE: hit() di settlement (HT mancante → None →
    riga esclusa, identico a get_market_frequency)."""
    ft = ft_score_90(match)
    ht = ht_score(match)
    return hit(market, selection, ft, ht)


def _hit_delay(market: str, selection: str, match: dict) -> Optional[bool]:
    """Esito per la SERIE RITARDI: identico a get_market_delays. Per i mercati
    HT-dipendenti l'RPC tratta il primo tempo mancante come (0,0) (coalesce,
    comportamento letterale del foglio Excel) invece di escludere la riga.
    Per i mercati FT è identico a _hit_freq."""
    ft = ft_score_90(match)
    if ft is None:
        return None  # senza punteggio 90' non è un evento DATI MATCH (RPC: escluso)
    ht = ht_score(match)
    if ht is None and _is_ht_dependent(market):
        ht = (0, 0)  # coalesce(HT,0) come get_market_delays
    return hit(market, selection, ft, ht)


def _baseline_mm10(series: list[Optional[int]]) -> tuple[Optional[float], list[Optional[float]]]:
    """baseline (avg su tutta la serie) + mm10 a finestra PIENA per ogni punto.
    series = lista di 0/1 (già filtrata: solo outcome validi). Replica l'RPC
    frequenze: mm10 None per idx<10 (i primi 9 punti)."""
    n = len(series)
    if n == 0:
        return None, []
    baseline = sum(series) / n
    mm10: list[Optional[float]] = []
    for i in range(n):
        if i + 1 >= 10:  # idx (1-based) >= 10  →  almeno 10 punti
            window = series[i - 9 : i + 1]
            mm10.append(sum(window) / 10.0)
        else:
            mm10.append(None)
    return baseline, mm10


def _delays(series: list[int]) -> tuple[list[int], Optional[int], Optional[float]]:
    """Macchina a stati dei ritardi (replica get_market_delays).
    series = lista di 0/1 (outcome validi, ordine cronologico). idx 1-based.
      rit(i)  = i - last_hit(i)        last_hit running-max idx con out=1 (0 se nessuno)
      suc     = (idx_hit - prev_hit) - 1   per ogni occorrenza
      record  = max(suc)               (None se nessuna occorrenza)
      media   = avg(rit) su rit != 0   (None se tutti rit==0)
    Ritorna (lista rit per ogni riga, record, media_ritardi)."""
    rits: list[int] = []
    sucs: list[int] = []
    last_hit = 0          # idx 1-based dell'ultima occorrenza (0 = nessuna)
    prev_hit = 0          # idx 1-based dell'occorrenza PRECEDENTE (per suc)
    for i, out in enumerate(series, start=1):
        if out == 1:
            sucs.append((i - prev_hit) - 1)
            prev_hit = i
            last_hit = i
        rits.append(i - last_hit)
    record = max(sucs) if sucs else None
    nonzero = [r for r in rits if r != 0]
    media = (sum(nonzero) / len(nonzero)) if nonzero else None
    return rits, record, media


def _freq_in_entrata(series: list[int]) -> list[tuple]:
    """Per ogni posizione k (1-based), (baseline, mm10) IN ENTRATA = calcolati
    sulle SOLE partite PRECEDENTI (o_1..o_{k-1}). NIENTE LOOK-AHEAD: la partita k
    NON contribuisce al proprio snapshot (è ciò che il mercato "sapeva" prima del
    kickoff). None dove la storia precedente è insufficiente (mm10: < 10 partite)."""
    out: list[tuple] = []
    csum = 0
    for k in range(1, len(series) + 1):
        cnt = k - 1
        baseline = (csum / cnt) if cnt > 0 else None
        mm10 = (sum(series[k - 11:k - 1]) / 10.0) if cnt >= 10 else None
        out.append((baseline, mm10))
        csum += series[k - 1]
    return out


def _delays_in_entrata(series: list[int]) -> list[tuple]:
    """Per ogni posizione k (1-based), (rit, record, media) IN ENTRATA = stato dei
    ritardi DOPO le partite precedenti (o_1..o_{k-1}), PRIMA di o_k. La partita k
    non si include → il delay_current non è più tautologico con l'esito.
    Coerente con compute_current_state: lo snapshot di k == stato dopo k-1 partite."""
    out: list[tuple] = []
    last_hit = 0; prev_hit = 0
    sucs: list[int] = []; rits_acc: list[int] = []
    for k in range(1, len(series) + 1):
        rit_e = (k - 1 - last_hit) if k > 1 else None
        rec_e = max(sucs) if sucs else None
        nz = [r for r in rits_acc if r != 0]
        med_e = (sum(nz) / len(nz)) if nz else None
        out.append((rit_e, rec_e, med_e))
        if series[k - 1] == 1:
            sucs.append((k - prev_hit) - 1); prev_hit = k; last_hit = k
        rits_acc.append(k - last_hit)
    return out


def compute_market_snapshots(
    market: str,
    selection: str,
    matches: list[dict],
) -> dict[int, Snapshot]:
    """Calcola, per OGNI fixture settlata di `matches`, lo Snapshot point-in-time
    di (market, selection). Una sola passata cronologica.

    `matches`: lista di righe `matches` (status_short, fulltime_*, goals_*,
    halftime_*, fixture_id, fixture_date). Verranno ordinate deterministicamente.

    Ritorna {fixture_id: Snapshot}. Solo le fixture il cui esito è valido (entra
    nella serie) compaiono nel risultato (le altre non hanno snapshot definito).
    """
    ordered = sorted(matches, key=chrono_key)

    # ---- SERIE FREQUENZE (hit None-escludente) ----
    freq_fids: list[int] = []
    freq_series: list[int] = []
    for m in ordered:
        h = _hit_freq(market, selection, m)
        if h is None:
            continue
        freq_fids.append(m["fixture_id"])
        freq_series.append(1 if h else 0)
    freq_in = _freq_in_entrata(freq_series)        # (baseline, mm10) PRE-MATCH per posizione

    # ---- SERIE RITARDI (HT-dipendenti: coalesce HT=0) ----
    delay_fids: list[int] = []
    delay_series: list[int] = []
    for m in ordered:
        h = _hit_delay(market, selection, m)
        if h is None:
            continue
        delay_fids.append(m["fixture_id"])
        delay_series.append(1 if h else 0)
    delay_in = _delays_in_entrata(delay_series)    # (rit, record, media) PRE-MATCH per posizione

    # ---- assembla per-fixture: ogni partita riceve lo stato IN ENTRATA
    #      (pre-match, dalle partite PRECEDENTI). Identico a ciò che il forward
    #      (compute_current_state) avrebbe dato guardando QUELLA partita prima del
    #      kickoff → niente look-ahead (delay_current non più tautologico). ----
    out: dict[int, Snapshot] = {}
    freq_map: dict[int, tuple] = {}
    for fid, (bl, mm) in zip(freq_fids, freq_in):
        dev = (mm - bl) if (mm is not None and bl is not None) else None
        freq_map[fid] = (bl, mm, dev)
    delay_map: dict[int, tuple] = {fid: t for fid, t in zip(delay_fids, delay_in)}

    for fid in set(freq_map) | set(delay_map):
        bl, mm, dev = freq_map.get(fid, (None, None, None))
        rit_e, rec_e, med_e = delay_map.get(fid, (None, None, None))
        out[fid] = Snapshot(
            freq_baseline=_r(bl),
            freq_current=_r(mm),
            freq_deviation=_r(dev),
            delay_current=rit_e,
            delay_record=rec_e,
            delay_avg=_r(med_e),
        )
    return out


def compute_current_state(
    market: str,
    selection: str,
    matches: list[dict],
) -> Snapshot:
    """STATO CORRENTE del mercato (lo snapshot "in entrata") da applicare alle
    fixture FUTURE / non-settlate della lega — un punto in più ALLA FINE della
    stessa serie cronologica delle settlate.

    ⚠️ POINT-IN-TIME: una partita non ancora giocata NON ha un suo esito. Il suo
    freq/ritardo è lo STATO del mercato dopo l'ULTIMA partita settlata:
      delay_current = ritardo corrente = (n. esiti della serie) - last_hit
                      = il ritardo "standing" dopo l'ultima settlata
                      = rit dell'ultima riga della serie ritardi (rits[-1])
      freq_current  = mm10 corrente = media mobile sugli ultimi 10 esiti settlati
                      (= mm10[-1]; None se < 10 settlate)
      freq_baseline = baseline sull'INTERA serie settlata
      delay_record/delay_avg = scalari di tutta la serie settlata (invariati)

    NESSUNA MATEMATICA NUOVA: riusa _baseline_mm10 e _delays sulla stessa serie
    binaria che costruisce compute_market_snapshots. È la continuazione naturale
    della serie (il "next index").

    `matches`: SOLO le partite SETTLATE a 90' della lega (la storia su cui si
    basa lo stato corrente). Le non-settlate NON entrano nella serie.
    Ritorna uno Snapshot scalare (lo stesso valore per tutte le fixture future).
    """
    ordered = sorted(matches, key=chrono_key)

    # ---- SERIE FREQUENZE (hit None-escludente) — identica a compute_market_snapshots
    freq_series: list[int] = []
    for m in ordered:
        h = _hit_freq(market, selection, m)
        if h is None:
            continue
        freq_series.append(1 if h else 0)
    baseline, mm10 = _baseline_mm10(freq_series)
    freq_current = mm10[-1] if mm10 else None  # mm10 corrente = ultimo punto

    # ---- SERIE RITARDI (HT-dipendenti: coalesce HT=0) — identica a sopra
    delay_series: list[int] = []
    for m in ordered:
        h = _hit_delay(market, selection, m)
        if h is None:
            continue
        delay_series.append(1 if h else 0)
    rits, record, media = _delays(delay_series)
    delay_current = rits[-1] if rits else None  # ritardo standing dopo l'ultima settlata

    dev = (freq_current - baseline) if (freq_current is not None and baseline is not None) else None
    return Snapshot(
        freq_baseline=_r(baseline) if freq_series else None,
        freq_current=_r(freq_current),
        freq_deviation=_r(dev),
        delay_current=delay_current,
        delay_record=record if delay_series else None,
        delay_avg=_r(media) if delay_series else None,
    )


def _r(v: Optional[float], nd: int = 4) -> Optional[float]:
    return round(v, nd) if v is not None else None
