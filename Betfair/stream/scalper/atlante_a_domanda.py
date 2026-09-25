"""atlante_a_domanda.py - l'Atlante Hazard guidato dalle PARTITE DA OSSERVARE.

Ordine dell'utente (25/09/2026): "L'Atlante deve essere leggero e adattabile
in base alle PARTITE LIVE che ci sono: deve conoscere lo storico di quella
lega e di quella specifica partita, DEVE AGGIORNARSI man mano che le partite
e le stagioni avanzano. VELOCE, EFFICIENTE e che NON PESI TROPPO SUL DB."

Niente bootstrap massivo. Il motore gira SUL PC dentro il thread gia'
esistente di ``hazard_atlas_sync`` (processo dello scanner Safe) e a ogni
ciclo:

  1. legge le partite da osservare: ``fixture_predictions`` nella finestra
     [ora - 36h, ora + 36h] (la STESSA fonte che Safe e Omega usano per le
     fixture del giorno, ``omega_db.fixtures_for_window``), 5 colonne, UNA GET;
  2. una lega che compare per la PRIMA volta si prepara UNA volta sola:
     stato gia' in memoria/file locale -> nessuna richiesta; stato gia' sul DB
     (``hazard_atlas_leghe``) -> una GET; altrimenti si calcola: stagioni con
     ``fixtures_events = true`` in coverage (una GET) e, per ciascuna delle
     ultime ``stagioni_max``, partite + gol (``genera_atlante.bootstrap``,
     il metodo e' quello del v1/v2/v3: nessun cambio statistico). Tetto per
     ciclo e per ora, pausa fra le leghe; mentre e' in coda la lega e'
     dichiarata "in preparazione" nel meta del file live e il lookup usa il
     globale dicendolo;
  3. INCREMENTALE per lega: le partite della finestra gia' finite e non
     ancora contate (fixture_id fuori dallo stato) -> GET per fixture_id
     (matches + gol), a blocchi di 100. Una partita finita i cui eventi non
     sono ancora nel DB resta IN ATTESA (si riprova) fino a
     ``attesa_eventi_h``; uno 0-0 conta solo se ha almeno un evento (senza
     eventi non si distingue da "eventi mancanti": e' la stessa distorsione
     che la soglia di copertura del v1 impedisce);
  4. STAGIONI CHE AVANZANO: una volta ogni ``ricontrollo_stagioni_h`` una GET
     sulla coverage delle leghe osservate negli ultimi ``giorni_inattiva``
     giorni: una stagione diventata ``fixtures_events = true`` e non ancora
     acquisita si acquisisce (stesso bootstrap, solo quella stagione);
  5. riassembla l'atlante (``genera_atlante.assembla`` con il v3 come SEME
     del globale finche' le leghe affidabili non bastano) e lo scrive ATOMICO
     in ``hazard_atlas_live.json`` solo se qualcosa e' cambiato (o ogni 12 h,
     perche' l'eta' dichiarata resti vera); lo stato grezzo va nel file locale
     e, per le leghe toccate, su ``hazard_atlas_leghe`` (upsert per
     league_id) se la scrittura su DB e' accesa.

Le leghe non osservate da ``giorni_inattiva`` giorni non si aggiornano piu'
(restano nello stato e nell'atlante). Nessun flumine importato (incidente
17/09, vedi hazard_atlas.py). ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, Set

from . import genera_atlante as G
from . import hazard_atlas as HA

logger = logging.getLogger("atlante_a_domanda")

# parametri di default (sovrascrivibili da env in hazard_atlas_sync)
PARAMETRI_DEFAULT: Dict[str, float] = {
    "tetto_ciclo": 10,             # leghe NUOVE calcolate per ciclo
    "tetto_ora": 40,               # leghe NUOVE calcolate per ora (finestra mobile)
    "pausa_lega_s": 5.0,           # pausa fra una lega calcolata e la successiva
    "stagioni_max": 10,            # stagioni con eventi (le piu' recenti) per lega
    "giorni_inattiva": 7,          # oltre: la lega non si aggiorna piu'
    "ricontrollo_stagioni_h": 24,  # ogni quanto si guarda la coverage per stagioni nuove
    "finestra_indietro_h": 36,     # partite da osservare: da ora - 36 h ...
    "finestra_avanti_h": 36,       # ... a ora + 36 h
    "fine_partita_min": 150,       # una partita si considera finita dopo 150' dal calcio d'inizio
    # oltre: una finita senza eventi si chiude qui (la conta poi la rete
    # notturna, guidata dagli eventi, se arrivano); < finestra_indietro_h
    "attesa_eventi_h": 34,
    "riscrivi_h": 12,              # il file live si riscrive almeno ogni 12 h (eta' vera)
    "lotto": 100,                  # fixture_id per GET nell'incrementale
    "riprova_attesa_min": 60,      # una partita in attesa di eventi si riprova ogni 60'
    "scrivi_db_ogni_h": 6,         # leghe aggiornate: su hazard_atlas_leghe a blocchi ogni 6 h
}

# stati di partita che non diventeranno MAI 'FT': la partita si chiude
_STATI_CHIUSI = {"AET", "PEN", "AWD", "WO", "CANC", "PST", "ABD"}


def _iso(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat(timespec="seconds")


def _ts(iso: Optional[str]) -> Optional[float]:
    if not iso:
        return None
    try:
        d = dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.timestamp()
    except ValueError:
        return None


class MotoreAtlante:
    """Il motore dell'atlante a domanda. ``lettore`` e' un ``G.LettoreDB``
    (solo GET), ``scrittore`` un ``G._Scrittore`` o None (niente DB in
    scrittura). ``orologio``/``sleep`` iniettabili per i test."""

    def __init__(self, lettore: G.LettoreDB, *, scrittore: Any = None,
                 path_live: Optional[str] = None, path_stato: Optional[str] = None,
                 path_seme: Optional[str] = None,
                 parametri: Optional[Dict[str, float]] = None,
                 orologio: Callable[[], float] = time.time,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.lettore = lettore
        self.scrittore = scrittore
        self.path_live = path_live or HA.ATLAS_LIVE_PATH
        self.path_stato = path_stato or HA.ATLAS_STATO_PATH
        self.path_seme = path_seme or HA.ATLAS_V3_PATH
        self.p = dict(PARAMETRI_DEFAULT)
        self.p.update(parametri or {})
        self.orologio = orologio
        self.sleep = sleep
        self.leghe: Dict[str, Dict[str, Any]] = {}     # lid -> stato grezzo (con fixtures)
        self.osservate: Dict[str, float] = {}          # lid -> ultima volta vista (ts)
        self.in_attesa: Dict[str, float] = {}          # fixture_id -> prima volta finita (ts)
        self.tentativi: Dict[str, float] = {}          # fixture_id -> ultimo tentativo (ts)
        self.chiuse: Set[str] = set()                  # fixture_id esaminati e non contabili
        self.senza_dati: Dict[str, float] = {}         # lid -> ts (nessuna stagione con eventi)
        self.calcolate_ts: List[float] = []            # tetto orario (finestra mobile)
        self.ultimo_ricontrollo = 0.0
        self.ultima_scrittura = 0.0
        self.ultimo_salvataggio = 0.0
        self.da_scrivere: Set[str] = set()             # leghe toccate non ancora sul DB
        self.ultimo_flush = 0.0
        self.in_preparazione: List[str] = []
        self._seme: Optional[Dict[str, Any]] = None
        self._caricato = False
        self.ultimo_giro: Dict[str, Any] = {}

    # ------------------------------------------------------------ persistenza
    def carica(self) -> None:
        """Stato locale (file) una volta sola. Un file rotto = si riparte da
        vuoto (lo stato vero e' anche sul DB, riletto lega per lega)."""
        if self._caricato:
            return
        self._caricato = True
        try:
            if os.path.exists(self.path_stato):
                with open(self.path_stato, "r", encoding="utf-8") as fh:
                    d = json.load(fh)
                self.leghe = {str(k): v for k, v in (d.get("leghe") or {}).items()
                              if isinstance(v, dict) and isinstance(v.get("fixtures"), list)}
                self.osservate = {str(k): float(v) for k, v in (d.get("osservate") or {}).items()}
                self.in_attesa = {str(k): float(v) for k, v in (d.get("in_attesa") or {}).items()}
                self.tentativi = {str(k): float(v) for k, v in (d.get("tentativi") or {}).items()}
                self.da_scrivere = {str(x) for x in (d.get("da_scrivere") or []) if str(x) in self.leghe}
                self.ultimo_flush = float(d.get("ultimo_flush") or 0.0)
                self.chiuse = {str(x) for x in (d.get("chiuse") or [])}
                self.senza_dati = {str(k): float(v) for k, v in (d.get("senza_dati") or {}).items()}
                self.calcolate_ts = [float(x) for x in (d.get("calcolate_ts") or [])]
                self.ultimo_ricontrollo = float(d.get("ultimo_ricontrollo") or 0.0)
        except Exception as ex:  # noqa: BLE001
            logger.warning("[atlante-domanda] stato locale illeggibile, si riparte: %s", str(ex)[:120])
            self.leghe = {}

    def _salva_stato(self) -> None:
        G.scrivi_json_atomico(self.path_stato, {
            "versione": 1, "leghe": self.leghe, "osservate": self.osservate,
            "in_attesa": self.in_attesa, "tentativi": self.tentativi, "chiuse": sorted(self.chiuse),
            "da_scrivere": sorted(self.da_scrivere), "ultimo_flush": self.ultimo_flush,
            "senza_dati": self.senza_dati, "calcolate_ts": self.calcolate_ts,
            "ultimo_ricontrollo": self.ultimo_ricontrollo})

    def seme(self) -> Optional[Dict[str, Any]]:
        if self._seme is None:
            try:
                with open(self.path_seme, "r", encoding="utf-8") as fh:
                    self._seme = json.load(fh)
            except Exception as ex:  # noqa: BLE001 - senza seme il globale viene dallo stato
                logger.warning("[atlante-domanda] seme non leggibile: %s", str(ex)[:120])
                self._seme = {}
        return self._seme or None

    # ----------------------------------------------------- partite osservate
    def partite_osservate(self, adesso: float) -> List[Dict[str, Any]]:
        """Le partite di ``fixture_predictions`` nella finestra: UNA GET."""
        lo = _iso(adesso - float(self.p["finestra_indietro_h"]) * 3600.0)
        hi = _iso(adesso + float(self.p["finestra_avanti_h"]) * 3600.0)
        rows = self.lettore.get("fixture_predictions", {
            "select": "fixture_id,league_id,home_team_id,away_team_id,fixture_date",
            "fixture_date": f"gte.{lo}", "and": f"(fixture_date.lt.{hi})",
            "order": "fixture_date.asc", "limit": "3000"})
        return [r for r in rows if G._int(r.get("league_id")) is not None
                and G._int(r.get("fixture_id")) is not None]

    # --------------------------------------------------------- lega nuova
    def _da_db(self, lid: str) -> Optional[Dict[str, Any]]:
        """Lo stato della lega gia' sul DB (calcolato da un altro giro o dalla
        action): UNA GET. None se non c'e'."""
        try:
            rows = self.lettore.get("hazard_atlas_leghe", {"select": "league_id,stato,fixtures",
                                                           "league_id": f"eq.{int(lid)}"})
        except Exception as ex:  # noqa: BLE001 - tabella assente/illeggibile: si calcola
            logger.info("[atlante-domanda] stato della lega %s non letto dal DB: %s", lid, str(ex)[:120])
            return None
        if not rows or not isinstance(rows[0].get("stato"), dict):
            return None
        st = dict(rows[0]["stato"])
        st["fixtures"] = [int(x) for x in (rows[0].get("fixtures") or [])]
        return st

    def prepara_lega(self, lid: str, adesso: float) -> str:
        """'db' (adottata dal DB), 'calcolata', 'senza_dati'. La lega calcolata
        si scrive su DB (se acceso) e nello stato locale."""
        st = self._da_db(lid)
        if st is not None:
            self.leghe[lid] = st
            return "db"
        cov = G.stagioni_con_eventi(self.lettore, [int(lid)]).get(lid, [])
        stagioni = cov[-int(self.p["stagioni_max"]):]
        if not stagioni:
            self.senza_dati[lid] = adesso
            return "senza_dati"
        tmp: Dict[str, Dict[str, Any]] = {}
        G.bootstrap(self.lettore, tmp, [int(lid)], stagioni, {}, _iso(adesso))
        st = tmp.get(lid) or G.stato_lega_vuoto(int(lid))
        st["bootstrapped"] = stagioni
        st["stagioni_coverage"] = cov          # stagioni con eventi dichiarati (tutte)
        st["updated_at"] = _iso(adesso)
        self.leghe[lid] = st
        self.senza_dati.pop(lid, None)
        if self.scrittore is not None:
            self.scrittore.salva_leghe(self.leghe, [lid])
        return "calcolata"

    def _budget(self, adesso: float) -> int:
        self.calcolate_ts = [t for t in self.calcolate_ts if adesso - t < 3600.0]
        return max(0, min(int(self.p["tetto_ciclo"]),
                          int(self.p["tetto_ora"]) - len(self.calcolate_ts)))

    # ------------------------------------------------------- stagioni nuove
    def stagioni_nuove(self, adesso: float, budget: int) -> Dict[str, List[int]]:
        """Una GET di coverage per le leghe attive; per ciascuna le stagioni
        con eventi non ancora acquisite (le vecchie scartate/vuote non si
        riprovano: solo le ultime due annate). Ritorna {lid: stagioni fatte}."""
        fatte: Dict[str, List[int]] = {}
        if adesso - self.ultimo_ricontrollo < float(self.p["ricontrollo_stagioni_h"]) * 3600.0:
            return fatte
        limite = adesso - float(self.p["giorni_inattiva"]) * 86400.0
        attive = [l for l in self.leghe if self.osservate.get(l, 0.0) >= limite]
        self.ultimo_ricontrollo = adesso
        if not attive:
            return fatte
        cov = G.stagioni_con_eventi(self.lettore, [int(l) for l in attive])
        anno = dt.datetime.fromtimestamp(adesso, dt.timezone.utc).year
        for lid in attive:
            if budget <= 0:
                self.ultimo_ricontrollo = 0.0      # il resto al prossimo ciclo
                break
            st = self.leghe[lid]
            st["stagioni_coverage"] = cov.get(lid, [])
            acquisite = set(st.get("stagioni_acquisite") or st.get("seasons") or [])
            ritenta_da = anno - 1
            mancanti = [y for y in cov.get(lid, [])[-int(self.p["stagioni_max"]):]
                        if y not in acquisite
                        and (y >= ritenta_da or (str(y) not in (st.get("stagioni_scartate") or {})
                                                 and y not in (st.get("stagioni_vuote") or [])))]
            if not mancanti:
                continue
            tmp = {lid: st}
            G.bootstrap(self.lettore, tmp, [int(lid)], mancanti, {}, _iso(adesso))
            self.leghe[lid] = tmp[lid]
            fatte[lid] = mancanti
            self.calcolate_ts.append(adesso)       # conta nel tetto orario
            budget -= 1
        return fatte

    # ------------------------------------------------------- incrementale
    def incrementale(self, partite: List[Dict[str, Any]], adesso: float) -> Dict[str, Any]:
        """Partite della finestra finite e non ancora contate, per le SOLE
        leghe nello stato. Ritorna conteggi e leghe toccate."""
        fine = float(self.p["fine_partita_min"]) * 60.0
        attesa = float(self.p["attesa_eventi_h"]) * 3600.0
        conti: Dict[str, Any] = {"aggiunte": 0, "in_attesa": 0, "chiuse": 0, "scartate": 0,
                                 "toccate": []}
        visti = {lid: set(int(x) for x in (st.get("fixtures") or [])) for lid, st in self.leghe.items()}
        da_leggere: List[int] = []
        for r in partite:
            lid = str(G._int(r.get("league_id")))
            fid = G._int(r.get("fixture_id"))
            ko = _ts(r.get("fixture_date"))
            if lid not in self.leghe or fid is None or ko is None or adesso - ko < fine:
                continue
            if fid in visti[lid] or str(fid) in self.chiuse:
                continue
            # in attesa di eventi: si riprova ogni riprova_attesa_min, non a ogni ciclo
            ult = self.tentativi.get(str(fid))
            if ult is not None and adesso - ult < float(self.p["riprova_attesa_min"]) * 60.0:
                continue
            da_leggere.append(fid)
        toccate: Set[str] = set()
        lotto = int(self.p["lotto"])
        for i in range(0, len(da_leggere), lotto):
            blocco = da_leggere[i:i + lotto]
            lista = ",".join(str(f) for f in blocco)
            matches = self.lettore.get("matches", {"select": G.COLONNE_MATCH,
                                                   "fixture_id": f"in.({lista})"})
            gol = self.lettore.get("match_events", {"select": G.COLONNE_GOL,
                                                    "fixture_id": f"in.({lista})",
                                                    "event_type": "eq.Goal"})
            per_f: Dict[int, List[Dict[str, Any]]] = {}
            for g in gol:
                f = G._int(g.get("fixture_id"))
                if f is not None:
                    per_f.setdefault(f, []).append(g)
            # 0-0 finiti: contano solo se hanno ALMENO un evento nel DB
            zero = [int(m["fixture_id"]) for m in matches if str(m.get("status_short")) == "FT"
                    and (G._int(m.get("goals_home")) or 0) + (G._int(m.get("goals_away")) or 0) == 0]
            con_eventi: Set[int] = set()
            # partita osservata ma non ancora in ``matches``: si aspetta
            presenti = {G._int(m.get("fixture_id")) for m in matches}
            for fid in blocco:
                if fid not in presenti:
                    self._attendi(fid, adesso, attesa, conti)
            if zero:
                ev = self.lettore.get("match_events", {
                    "select": "fixture_id", "fixture_id": f"in.({','.join(str(z) for z in zero)})",
                    "limit": str(len(zero) * 60)})
                con_eventi = {int(e["fixture_id"]) for e in ev if G._int(e.get("fixture_id")) is not None}
            for m in matches:
                fid = G._int(m.get("fixture_id"))
                lid = str(G._int(m.get("league_id")))
                if fid is None or lid not in self.leghe:
                    continue
                stato_p = str(m.get("status_short") or "")
                if stato_p != "FT":
                    if stato_p in _STATI_CHIUSI:
                        self._chiudi(fid)
                        conti["chiuse"] += 1
                    else:
                        self._attendi(fid, adesso, attesa, conti)
                    continue
                gg = per_f.get(fid, [])
                tot_gol = (G._int(m.get("goals_home")) or 0) + (G._int(m.get("goals_away")) or 0)
                senza_eventi = (not gg) if tot_gol > 0 else (fid not in con_eventi)
                if senza_eventi:
                    cov_l = self.leghe[lid].get("stagioni_coverage")
                    anno_m = G._int(m.get("season_year"))
                    if cov_l is not None and anno_m is not None and anno_m not in cov_l:
                        # la coverage dice che per questa stagione gli eventi
                        # non arrivano: inutile riprovare (la acquisira'
                        # stagioni_nuove quando la coverage cambia)
                        self._chiudi(fid)
                        conti["chiuse"] += 1
                        continue
                    self._attendi(fid, adesso, attesa, conti)
                    continue
                seq, motivo = G.sequenza_partita(m, gg)
                st = self.leghe[lid]
                if seq is None:
                    G.scarta(st, motivo)
                    self._chiudi(fid)
                    conti["scartate"] += 1
                    toccate.add(lid)
                    continue
                if G.aggiungi_partita(st, seq, visti[lid]):
                    st["updated_at"] = _iso(adesso)
                    conti["aggiunte"] += 1
                    toccate.add(lid)
                self.in_attesa.pop(str(fid), None)
                self.tentativi.pop(str(fid), None)
        conti["toccate"] = sorted(toccate, key=int)
        return conti

    def _chiudi(self, fid: int) -> None:
        self.chiuse.add(str(fid))
        self.in_attesa.pop(str(fid), None)
        self.tentativi.pop(str(fid), None)

    def _attendi(self, fid: int, adesso: float, attesa: float, conti: Dict[str, Any]) -> None:
        primo = self.in_attesa.setdefault(str(fid), adesso)
        if adesso - primo > attesa:
            self._chiudi(fid)
            conti["chiuse"] += 1
        else:
            self.tentativi[str(fid)] = adesso
            conti["in_attesa"] += 1

    # ------------------------------------------------------------- ciclo
    def ciclo(self) -> Dict[str, Any]:
        """Un giro completo. Mai eccezioni verso il chiamante (il thread di
        sync lo chiama in un try); il riepilogo dice cosa e' successo."""
        self.carica()
        t0 = self.orologio()
        adesso = t0
        r0, n0 = self.lettore.n_richieste, self.lettore.n_righe
        cambiato = False
        partite = self.partite_osservate(adesso)
        osservate_ora = []
        primo_ko: Dict[str, float] = {}
        for r in partite:
            lid = str(G._int(r.get("league_id")))
            self.osservate[lid] = adesso
            ko = _ts(r.get("fixture_date")) or adesso
            if lid not in primo_ko:
                osservate_ora.append(lid)
            primo_ko[lid] = min(primo_ko.get(lid, ko), ko)
        # leghe nuove, prima quelle che giocano prima (in-play in testa)
        nuove = [l for l in osservate_ora if l not in self.leghe
                 and adesso - self.senza_dati.get(l, -1e18) > 86400.0]
        nuove.sort(key=lambda l: primo_ko.get(l, adesso))
        budget = self._budget(adesso)
        scelte = nuove[:budget]
        esiti: Dict[str, str] = {}
        if nuove != self.in_preparazione:
            self.in_preparazione = list(nuove)
            if scelte:
                # si DICHIARA prima di lavorare: i bot vedono "in preparazione"
                self._scrivi_live(adesso)
        for i, lid in enumerate(scelte):
            try:
                esiti[lid] = self.prepara_lega(lid, adesso)
            except Exception as ex:  # noqa: BLE001 - una lega rotta non ferma le altre
                esiti[lid] = f"errore: {str(ex)[:80]}"
                logger.warning("[atlante-domanda] lega %s KO: %s", lid, str(ex)[:120])
                continue
            if esiti[lid] == "calcolata":
                self.calcolate_ts.append(adesso)
            if esiti[lid] in ("calcolata", "db"):
                cambiato = True
            logger.info("[atlante-domanda] lega %s (%d/%d): %s - richieste %d, righe %d, %.1f s",
                        lid, i + 1, len(scelte), esiti[lid], self.lettore.n_richieste - r0,
                        self.lettore.n_righe - n0, self.orologio() - t0)
            if i + 1 < len(scelte) and float(self.p["pausa_lega_s"]) > 0:
                self.sleep(float(self.p["pausa_lega_s"]))
        self.in_preparazione = [l for l in nuove if l not in esiti or esiti[l].startswith("errore")]
        stagioni = self.stagioni_nuove(adesso, self._budget(adesso))
        if stagioni:
            cambiato = True
        inc = self.incrementale(partite, adesso)
        if inc["toccate"]:
            cambiato = True
        # memoria limitata alla finestra: fuori finestra non si riprova nulla
        in_finestra = {str(G._int(r.get("fixture_id"))) for r in partite}
        self.in_attesa = {k: v for k, v in self.in_attesa.items() if k in in_finestra}
        self.tentativi = {k: v for k, v in self.tentativi.items() if k in in_finestra}
        self.chiuse &= in_finestra
        # SCRITTURA SU DB A BLOCCHI: una riga di hazard_atlas_leghe e' lo stato
        # intero della lega (~50-100 KB jsonb con i fixture_id): riscriverla a
        # ogni partita finita costerebbe decine di MB al giorno. Le leghe
        # toccate si segnano e si scrivono insieme ogni ``scrivi_db_ogni_h``
        # ore (la lega appena calcolata si scrive subito, in prepara_lega). Il
        # file locale resta la verita' del PC fra una scrittura e l'altra.
        self.da_scrivere |= set(inc["toccate"]) | set(stagioni)
        if not self.ultimo_flush:
            self.ultimo_flush = adesso             # l'orologio dei blocchi parte dal primo ciclo
        if (self.scrittore is not None and self.da_scrivere
                and adesso - self.ultimo_flush >= float(self.p["scrivi_db_ogni_h"]) * 3600.0):
            try:
                self.scrittore.salva_leghe(self.leghe, sorted(self.da_scrivere, key=int))
                self.da_scrivere = set()
                self.ultimo_flush = adesso
            except Exception as ex:  # noqa: BLE001 - si riprova al prossimo ciclo
                logger.warning("[atlante-domanda] scrittura DB KO: %s", str(ex)[:120])
        riscrivi = cambiato or (adesso - self.ultima_scrittura > float(self.p["riscrivi_h"]) * 3600.0)
        if riscrivi or not os.path.exists(self.path_live):
            self._scrivi_live(adesso)
        # il file di stato (~10-15 MB a regime) si riscrive solo se serve
        if (cambiato or esiti or inc["in_attesa"] or inc["chiuse"]
                or adesso - self.ultimo_salvataggio > 3600.0 or not os.path.exists(self.path_stato)):
            self._salva_stato()
            self.ultimo_salvataggio = adesso
        self.ultimo_giro = {
            "partite_osservate": len(partite), "leghe_osservate": len(osservate_ora),
            "leghe_nuove": len(nuove), "preparate": esiti, "in_preparazione": list(self.in_preparazione),
            "stagioni_nuove": stagioni, "incrementale": inc,
            "richieste": self.lettore.n_richieste - r0, "righe": self.lettore.n_righe - n0,
            "secondi": round(self.orologio() - t0, 1), "scritto": bool(riscrivi)}
        return self.ultimo_giro

    def _scrivi_live(self, adesso: float) -> None:
        atlas = G.assembla(self.leghe, generated_at=_iso(adesso), seme=self.seme())
        atlas["meta"]["modo"] = "a_domanda"
        atlas["meta"]["generator"] = "Betfair/stream/scalper/atlante_a_domanda.py"
        atlas["meta"]["leghe_in_preparazione"] = [int(x) for x in self.in_preparazione]
        atlas["meta"]["leghe_senza_dati"] = sorted(int(x) for x in self.senza_dati)
        G.scrivi_json_atomico(self.path_live, atlas)
        self.ultima_scrittura = adesso
