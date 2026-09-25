"""auto_mode.py - AUTO-MODE dei 4 bot tennis e USCITE AUTOMATICHE/MANUALI (25/09).

ORDINE DELL'UTENTE (25/09): «I bot tennis (a esclusione di Safe) non partono
anche se li attivo [...] i bot devono partire e lavorare tramite feed unico una
volta attivati. Tutti i bot tennis devono lavorare in "auto-mode" se attivati e
gestire le uscite in automatico o in manuale sia in paper che in live.»

Il reperto: il ponte (``tennis_bot_service.riconcilia_interruttori``) armava la
coppia (partita, bot) SOLO sulle partite SEGUITE a mano nel Terminale Tennis.
Con nessuna partita seguita l'interruttore «running» non armava niente e la
Control Room scriveva «acceso, ma nessun evento tennis seguito».

Qui vive SOLO logica PURA (nessun I/O, nessun database): il ponte legge e
scrive, questo modulo decide. Cosi' i test la collaudano senza finti di rete.

1. LA LISTA PARTITE viene dal FEED UNICO (``safe_strategy_scan``, righe
   ``sport='tennis'`` scritte dallo scanner Safe, ``Betfair/safe_strategy/
   service.py::build_rows``): e' la stessa lista che legge Safe tennis
   (``bot_db.fetch_scan_rows``). Il feed NON filtra per strategia: i filtri di
   ciascun bot (quote, in-play, setup) restano i SUOI, dentro il bot.
2. IL TETTO di partite armate dal feed per bot: ogni partita seguita dal
   runner costa una riga ``tennis_live_now`` ogni ``TENNIS_SCORE_POLL_SEC``
   (2 s, scrittura NON a firma: ``tennis_runner.score_and_now_worker``) piu' la
   ladder a firma ogni 2 s. Il limite Betfair (200 mercati per connessione) e'
   lontano: il runner sottoscrive UN mercato (Match Odds) per partita su UNA
   connessione. Il vincolo vero e' l'IO del database (13/09: budget IO
   esaurito). Default 5, per bot, da ``params.auto_max_partite`` o dall'env
   ``TENNIS_AUTO_MAX_PARTITE``; 0 = auto-mode spento (solo partite seguite a
   mano, il comportamento di prima). L'ordinamento e' DETERMINISTICO e uguale
   per i 4 bot (in gioco prima, poi per orario d'inizio, poi per event_id):
   bot con lo stesso tetto scelgono le STESSE partite, cosi' l'unione resta
   entro il tetto e non entro 4 volte il tetto.
3. LE USCITE: ``uscite_automatiche`` per bot (colonna di
   ``tennis_bot_service_control``, migrazione
   ``migrations/tennis_uscite_manuali_2026-09-25.sql``). Assente o illeggibile =
   AUTOMATICHE, cioe' il comportamento di oggi. Spente = il bot NON prende
   profitto da solo; le PROTEZIONI (stop, time-stop, chiusura a fine
   partita/mercato, chiudi-ora D3, force_flat) restano SEMPRE. Lo SCALPER e'
   escluso: la sua uscita a target e' la gamba opposta piazzata insieme
   all'ingresso (``tennis_scalper_bot._manage_maker``/``_open_lock``), cioe' la
   strategia stessa - spegnerla vorrebbe dire alterarla. Portato all'utente.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Set

# ---------------------------------------------------------------------------
# 1. IL TETTO
# ---------------------------------------------------------------------------
ENV_TETTO = "TENNIS_AUTO_MAX_PARTITE"
CHIAVE_TETTO = "auto_max_partite"
TETTO_DEFAULT = 5
#: sopra questo numero la ladder + tennis_live_now da sole superano ~40
#: scritture al secondo: un tetto piu' alto e' un errore di battitura, non una
#: scelta (si taglia qui, dichiarato).
TETTO_MASSIMO = 40

ORIGINE_AUTO = "auto"
ORIGINE_MANUALE = "manuale"

#: i bot la cui uscita discrezionale E' la strategia (vedi docstring, punto 3)
BOT_USCITE_SEMPRE_AUTOMATICHE = frozenset({"tennis_scalper"})
#: chiave delle ``stats`` della riga per partita (la scrive il runner nel
#: battito): da quando la posizione di un bot a uscite MANUALI e' aperta
CHIAVE_POSIZIONE_APERTA = "posizione_aperta_dal"


def _intero(v: Any) -> Optional[int]:
    if v is None or isinstance(v, bool):
        return None
    try:
        s = str(v).strip()
        if not s:
            return None
        n = int(float(s))
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else None


def tetto_partite(params: Optional[Dict[str, Any]],
                  env: Optional[Dict[str, str]] = None) -> int:
    """Il tetto di partite armate DAL FEED per UN bot.

    Precedenza: ``params.auto_max_partite`` (dalla Control Room) > env
    ``TENNIS_AUTO_MAX_PARTITE`` > ``TETTO_DEFAULT``. Un valore illeggibile o
    negativo non conta (si passa al successivo): env vuota = default, mai
    ``??`` (regola del repo). Tagliato a ``TETTO_MASSIMO``."""
    envd = os.environ if env is None else env
    for cand in ((params or {}).get(CHIAVE_TETTO), envd.get(ENV_TETTO, "")):
        n = _intero(cand)
        if n is not None:
            return min(n, TETTO_MASSIMO)
    return TETTO_DEFAULT


def params_per_strategia(params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """I params che arrivano al BOT: quelli della riga, senza la chiave del
    tetto (e' del ponte, non della strategia). Nessun altro valore cambia."""
    out = dict(params or {})
    out.pop(CHIAVE_TETTO, None)
    return out


# ---------------------------------------------------------------------------
# 2. LA LISTA PARTITE DAL FEED UNICO
# ---------------------------------------------------------------------------
def origine_follow(riga: Optional[Dict[str, Any]]) -> str:
    """``auto`` SOLO se scritto; tutto il resto (colonna assente compresa) e'
    ``manuale``: una partita seguita dall'utente non si tratta mai come
    automatica per sbaglio."""
    o = str((riga or {}).get("origine") or "").strip().lower()
    return ORIGINE_AUTO if o == ORIGINE_AUTO else ORIGINE_MANUALE


def _ts(v: Any) -> Optional[float]:
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def eta_s(iso: Any, ora_epoch: float) -> Optional[float]:
    t = _ts(iso)
    return None if t is None else max(0.0, float(ora_epoch) - t)


def partite_dal_feed(righe: Optional[Iterable[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Le partite tennis del feed, ORDINATE, con quello che serve a seguirle.

    Tiene: riga ``sport='tennis'`` con ``payload`` dizionario, ``mo_market_id``
    presente, ``mo_status`` diverso da ``CLOSED``. Lo scanner pubblica gia'
    solo partite in gioco o col via entro 15 minuti
    (``scanner.is_monitorable``): qui non si aggiunge nessun filtro di
    strategia. Ordine: in gioco prima, poi orario d'inizio, poi event_id."""
    out: List[Dict[str, Any]] = []
    visti: Set[str] = set()
    for r in righe or []:
        if not isinstance(r, dict):
            continue
        if str(r.get("sport") or "tennis").strip().lower() != "tennis":
            continue
        p = r.get("payload")
        ev = str(r.get("event_id") or "").strip()
        if not ev or ev in visti or not isinstance(p, dict):
            continue
        mid = str(p.get("mo_market_id") or "").strip()
        if not mid:
            continue
        if str(p.get("mo_status") or "").strip().upper() == "CLOSED":
            continue
        visti.add(ev)
        out.append({
            "event_id": ev,
            "market_id": mid,
            "p1": str(p.get("p1") or "").strip() or "P1",
            "p2": str(p.get("p2") or "").strip() or "P2",
            "competition": p.get("competition"),
            "open_date": p.get("open_date"),
            "inplay": p.get("inplay") is True,
            "updated_at": r.get("updated_at"),
        })
    out.sort(key=lambda x: (0 if x["inplay"] else 1, str(x.get("open_date") or "~"),
                            x["event_id"]))
    return out


def scegli_partite(candidate: List[str], gia_armate: Iterable[str],
                   escludi: Callable[[str], bool], tetto: int) -> Dict[str, List[str]]:
    """Quali partite del feed deve avere UN bot.

    * ``tengo``: quelle gia' armate e ancora nel feed (mai buttate fuori per
      far posto a una nuova: niente giostra di armamenti);
    * ``nuove``: le prime candidate (nell'ordine del feed) non armate per cui
      ``escludi(event_id)`` e' falso, finche' ``tengo + nuove`` non arriva al
      tetto. ``escludi`` si chiama SOLO sulle candidate che servono (dietro
      c'e' una lettura al database per partita: niente letture inutili).
    Un tetto abbassato sotto le armate non ne disarma nessuna: semplicemente
    non se ne armano di nuove."""
    armate = {str(e) for e in gia_armate}
    tengo = [e for e in candidate if e in armate]
    posti = max(0, int(tetto) - len(tengo))
    nuove: List[str] = []
    for e in candidate:
        if posti <= 0:
            break
        if e in armate or escludi(e):
            continue
        nuove.append(e)
        posti -= 1
    return {"tengo": tengo, "nuove": nuove}


# ---------------------------------------------------------------------------
# 3. LE USCITE
# ---------------------------------------------------------------------------
def uscite_automatiche_riga(riga: Optional[Dict[str, Any]]) -> bool:
    """``False`` SOLO se la riga lo scrive esattamente. Colonna assente,
    ``None``, stringhe: AUTOMATICHE, cioe' il comportamento di prima."""
    return (riga or {}).get("uscite_automatiche") is not False


def uscite_automatiche_bot(bot_key: str, riga: Optional[Dict[str, Any]]) -> bool:
    """Le uscite EFFETTIVE di un bot: lo scalper e' sempre automatico."""
    if str(bot_key) in BOT_USCITE_SEMPRE_AUTOMATICHE:
        return True
    return uscite_automatiche_riga(riga)


# ---------------------------------------------------------------------------
# 4. IL MESSAGGIO (le stesse parole che la Control Room mostra)
# ---------------------------------------------------------------------------
MOTIVO_GUARDIA = ("guardia d'avvio: aperture bloccate finche' il controllo "
                  "d'avvio dell'app non riesce")
MOTIVO_FEED_VUOTO = "feed tennis vuoto: nessuna partita in-play ora"
MOTIVO_FEED_MUTO = ("feed tennis non disponibile (scanner fermo o lettura KO): "
                    "nessuna partita dal feed")
MOTIVO_ORIGINE_ASSENTE = ("auto-mode spento: migrazione "
                          "tennis_uscite_manuali_2026-09-25.sql non applicata")
MOTIVO_TETTO_ZERO = "auto-mode spento (tetto 0)"
SUFFISSO_NESSUNA_SEGUITA = " - e nessun evento seguito a mano"


def motivo_blocco(*, acceso: bool, bloccato: bool, feed_letto: bool,
                  feed_vivo: bool, partite_feed: int, origine_ok: bool,
                  tetto: int, armate: int, seguite: int) -> Optional[str]:
    """PERCHE' un bot acceso non e' armato su niente. ``None`` = armato su
    almeno una partita, oppure spento: nessun blocco da dire.

    Mai un motivo con almeno una partita armata: «acceso ma non apre» sarebbe
    falso (il bot sta guardando quella partita). ``seguite`` = partite seguite
    a mano nel Terminale: se sono zero lo si dice, e' l'altra strada con cui
    il bot si arma."""
    if not acceso:
        return None
    if bloccato:
        return MOTIVO_GUARDIA
    if armate > 0:
        return None
    coda = SUFFISSO_NESSUNA_SEGUITA if int(seguite) <= 0 else ""
    if not origine_ok:
        return MOTIVO_ORIGINE_ASSENTE + coda
    if tetto <= 0:
        return MOTIVO_TETTO_ZERO + coda
    if not feed_letto or not feed_vivo:
        return MOTIVO_FEED_MUTO + coda
    if partite_feed <= 0:
        return MOTIVO_FEED_VUOTO + coda
    return ("nessuna partita armabile fra le %d del feed (chiuse dall'utente, "
            "concluse o in errore)" % int(partite_feed)) + coda
