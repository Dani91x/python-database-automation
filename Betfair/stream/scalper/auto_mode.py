"""auto_mode.py - AUTO-MODE DELLO SCALPER CALCIO (25/09/2026).

ORDINE DELL'UTENTE (25/09, testuale): «Lo scalper deve lavorare da solo su
tutte le partite del feed come gli altri bot, i suoi ordini devono finire
flaggati col nome "scalper", pubblicalo sul canale come tutti gli altri.
Questo vale per tutti i bot presenti e futuri: 1 solo canale dati che alimenta
tutti i bot.»

Qui vive SOLO logica PURA (nessun I/O, nessun database, nessuna rete): il
supervisore (``scalper_service.py``) legge e scrive, questo modulo decide.
LA STRATEGIA NON SI TOCCA: maker/sniper/theta, tick, soglie, bias restano
quelli della sessione (``scalper_session.py``). Cambia solo COME si accende
(un interruttore globale, ``scalper_service_control``), DA DOVE prende le
partite (il FEED UNICO ``safe_strategy_scan``), come si etichettano gli ordini
e come si pubblica lo stato.

1. LA LISTA PARTITE viene dal feed unico (righe ``sport='calcio'`` dello
   scanner Safe, ``safe_strategy/service.py::build_rows``): la stessa lista di
   Safe/Omega/Mike. Nessun filtro di strategia: solo ``mo_market_id`` presente
   e ``mo_status != CLOSED``. Lo scanner pubblica gia' solo partite in gioco o
   col via vicino (``scanner.is_monitorable``): le imminenti ci sono.
2. LA VITA DELLA SESSIONE. Una sessione finisce da sola a KO + vita
   (``vita_sessione_s``: 10' il maker pre-match, 70' con l'intervallo, 130'
   con sniper/theta: gli STESSI numeri che ``scalper_session`` usava inline, ora
   presi da qui da entrambi). Armare una partita gia' oltre quel limite vuol
   dire un login, un catalogo e una sessione che si chiude al primo battito:
   non e' un filtro di strategia, e' il ciclo di vita della sessione stessa.
3. IL TETTO. Ogni sessione e' un PROCESSO con il SUO login e la SUA
   connessione stream (in live anche l'order stream: due connessioni).
   Betfair: 200 mercati per connessione (lontano: 4-12 mercati a sessione) e
   **10 connessioni per app key**; lo scanner Safe ne usa 4 di serie
   (``SAFE_STRATEGY_STREAM_CONNS``), il runner calcio 1 (+1 in live), il
   runner tennis 1 (+1 in live). Restano 2 connessioni nel caso peggiore:
   default **2** sessioni, massimo **4** (oltre = errore di battitura, si
   taglia). Il tetto conta TUTTE le sessioni che tengono un processo (anche
   quelle armate a mano dalla card): il vincolo sono le connessioni, non
   l'origine. ``params.auto_max_partite`` (Control Room) > env
   ``SCALPER_AUTO_MAX_PARTITE`` > 2; 0 = auto-mode spento (solo la card).
4. COSA NON SI RIARMA MAI: una partita chiusa a mano (riga 'stopped' armata
   DOPO l'accensione corrente), in errore ('error'), conclusa ('done'), in
   attesa di consenso bias ('armed', nessun processo). Una riga 'stopped' di
   PRIMA dell'accensione corrente si riarma: spegnere e riaccendere e' un
   gesto dell'utente (come il tennis). Il follow ``live_follow`` chiuso
   (CLOSED/UPLOADED/ERROR) non si riapre.
5. PAPER E LIVE MAI INSIEME: con una sessione attiva nella modalita' opposta a
   quella dell'interruttore non si arma niente di nuovo, e lo si dice.
6. PARTITA USCITA DAL FEED: una sessione AUTOMATICA la cui partita manca dal
   feed (scanner vivo) da almeno ``ASSENZA_FEED_S`` va in 'stopping' (la
   sessione fa force-flat e attende il flat: lo stop di sempre). Feed muto o
   non letto: non si ferma niente. Le sessioni armate a mano non si toccano.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set

# riuso (nessuna seconda copia): la scelta con tetto del ponte tennis e l'eta'
from ..tennis_live.auto_mode import eta_s, scegli_partite  # noqa: F401 - riesportati

# ---------------------------------------------------------------------------
# costanti
# ---------------------------------------------------------------------------
ENV_TETTO = "SCALPER_AUTO_MAX_PARTITE"
CHIAVE_TETTO = "auto_max_partite"
TETTO_DEFAULT = 2
TETTO_MASSIMO = 4

ORIGINE_AUTO = "auto"
ORIGINE_MANUALE = "manuale"

#: stati di ``scalper_control`` con un processo di sessione dietro (o in arrivo)
STATI_CON_PROCESSO = frozenset({"requested", "arming", "running", "stopping"})
#: stati "attivi" per la Control Room (``scalper_stop`` li porta a stopping)
STATI_ATTIVI = frozenset({"requested", "arming", "armed", "running"})

#: una partita automatica assente dal feed da almeno tanto si ferma (s). Un
#: giro del supervisore (15 s) non basta: lo scanner puo' riscrivere la lista
#: a cavallo di un giro. Quattro giri = una sparizione vera.
ASSENZA_FEED_S = 60.0
#: il battito dello scanner piu' vecchio di cosi' = feed non vivo (stessa
#: soglia di ``scores/scan_feed.SCANNER_ALIVE_MAX_AGE_SEC`` e del ponte tennis)
SCANNER_VIVO_S = 30.0
FONTE_FEED = "safe_strategy_scan"

#: stati di ``live_follow`` con cui il follow e' finito: mai riaperto da qui
FOLLOW_CHIUSI = frozenset({"CLOSED", "UPLOADED", "ERROR"})

# vita della sessione dopo il kickoff (s) - numeri di ``scalper_session``
VITA_MAKER_S = 600
VITA_HT_S = 4200
VITA_SNIPER_THETA_S = 7800


# ---------------------------------------------------------------------------
# utilita'
# ---------------------------------------------------------------------------
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


def _epoch(v: Any) -> Optional[float]:
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


# ---------------------------------------------------------------------------
# 1. il tetto e i params della sessione
# ---------------------------------------------------------------------------
def tetto_partite(params: Optional[Dict[str, Any]],
                  env: Optional[Dict[str, str]] = None) -> int:
    """Precedenza: ``params.auto_max_partite`` > env > ``TETTO_DEFAULT``.
    Illeggibile o negativo = non conta (si passa al successivo); env vuota =
    default, mai ``??``. Tagliato a ``TETTO_MASSIMO``."""
    envd = os.environ if env is None else env
    for cand in ((params or {}).get(CHIAVE_TETTO), envd.get(ENV_TETTO, "")):
        n = _intero(cand)
        if n is not None:
            return min(n, TETTO_MASSIMO)
    return TETTO_DEFAULT


def params_per_sessione(params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """I params che la riga di sessione riceve: quelli dell'interruttore senza
    la chiave del tetto (e' del supervisore, non della strategia). Nessun altro
    valore cambia: la sessione applica la SUA whitelist come sempre."""
    out = dict(params or {})
    out.pop(CHIAVE_TETTO, None)
    return out


def vita_sessione_s(params: Optional[Dict[str, Any]]) -> int:
    """Secondi di vita della sessione dopo il kickoff: STESSA regola che
    ``scalper_session.run_session`` applica per chiudersi (sniper/theta fino a
    fine partita, ht_mode fino a ~70', il maker pre-match fino a KO+10')."""
    p = params or {}
    if bool(p.get("sniper_mode")) or bool(p.get("theta_mode")):
        return VITA_SNIPER_THETA_S
    if bool(p.get("ht_mode")):
        return VITA_HT_S
    return VITA_MAKER_S


def ha_ancora_vita(open_date: Any, params: Optional[Dict[str, Any]], ora: float) -> bool:
    """La sessione armata adesso avrebbe ancora vita? KO illeggibile = si'
    (la sessione, senza KO, non si chiude per eta': decide il feed)."""
    ko = _epoch(open_date)
    if ko is None:
        return True
    return float(ora) < ko + vita_sessione_s(params)


# ---------------------------------------------------------------------------
# 2. la lista partite dal feed unico
# ---------------------------------------------------------------------------
#: le chiavi del payload calcio dello scanner che servono all'auto-mode
CHIAVI_FEED = ("event_name", "home", "away", "competition", "open_date",
               "inplay", "mo_market_id", "mo_status")


def partite_dal_feed(righe: Optional[Iterable[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Le partite calcio del feed, ORDINATE (in gioco prima, poi orario
    d'inizio, poi event_id: stesso ordine del ponte tennis)."""
    out: List[Dict[str, Any]] = []
    visti: Set[str] = set()
    for r in righe or []:
        if not isinstance(r, dict):
            continue
        if str(r.get("sport") or "calcio").strip().lower() != "calcio":
            continue
        p = r.get("payload")
        ev = str(r.get("event_id") or "").strip()
        if not ev or ev in visti or not isinstance(p, dict):
            continue
        if not str(p.get("mo_market_id") or "").strip():
            continue
        if str(p.get("mo_status") or "").strip().upper() == "CLOSED":
            continue
        home = str(p.get("home") or "").strip()
        away = str(p.get("away") or "").strip()
        if not home or not away:
            # senza i nomi non si scrive un follow (colonne NOT NULL) e il
            # bias non potrebbe riconoscere le squadre: la partita non si arma
            continue
        visti.add(ev)
        out.append({
            "event_id": ev,
            "home": home,
            "away": away,
            "competition": p.get("competition"),
            "open_date": p.get("open_date"),
            "inplay": p.get("inplay") is True,
        })
    out.sort(key=lambda x: (0 if x["inplay"] else 1, str(x.get("open_date") or "~"),
                            x["event_id"]))
    return out


# ---------------------------------------------------------------------------
# 3. chi si puo' armare
# ---------------------------------------------------------------------------
def origine_riga(riga: Optional[Dict[str, Any]]) -> str:
    """``auto`` SOLO se scritto: tutto il resto (colonna assente compresa) e'
    ``manuale``, cosi' una sessione dell'utente non si ferma mai per sbaglio."""
    o = str((riga or {}).get("origine") or "").strip().lower()
    return ORIGINE_AUTO if o == ORIGINE_AUTO else ORIGINE_MANUALE


def motivo_esclusione(riga: Optional[Dict[str, Any]],
                      acceso_dal: Optional[str]) -> Optional[str]:
    """Perche' una partita del feed NON si arma adesso. ``None`` = armabile.

    ``riga`` = la sua riga di ``scalper_control`` (None = mai armata);
    ``acceso_dal`` = ``started_at`` dell'interruttore (l'accensione corrente).
    Una riga di prima dell'accensione corrente ferma ('stopped') si riarma; una
    armata DOPO e poi fermata e' stata chiusa (a mano, o dal feed): no."""
    if not riga:
        return None
    st = str(riga.get("status") or "").strip().lower()
    if st in STATI_CON_PROCESSO:
        return "attiva"
    if st == "armed":
        return "in attesa di consenso bias"
    if st == "error":
        return "in errore"
    if st == "done":
        return "conclusa"
    if st == "stopped":
        dal = _epoch(acceso_dal)
        rich = _epoch(riga.get("requested_at"))
        if dal is not None and rich is not None and rich < dal:
            return None
        return "chiusa a mano"
    return "stato sconosciuto (%s)" % (st or "vuoto")


def sessioni_con_processo(righe: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for r in righe or []
            if isinstance(r, dict)
            and str(r.get("status") or "").strip().lower() in STATI_CON_PROCESSO]


def modalita_riga(riga: Dict[str, Any]) -> str:
    """paper/live della sessione: ``dry_run`` e' l'interruttore (fail-closed:
    tutto cio' che non e' esattamente False vale paper, come la sessione)."""
    return "live" if riga.get("dry_run") is False else "paper"


def conflitto_modalita(righe_vive: Iterable[Dict[str, Any]], modalita: str) -> Optional[str]:
    """Paper e live mai insieme: la modalita' OPPOSTA di una sessione con un
    processo dietro, se c'e'."""
    for r in righe_vive or []:
        m = modalita_riga(r)
        if m != modalita:
            return m
    return None


def da_fermare_per_feed(righe_auto_attive: Iterable[Dict[str, Any]],
                        nel_feed: Set[str], assenti_dal: Dict[str, float],
                        ora: float) -> List[str]:
    """Le sessioni AUTOMATICHE da fermare perche' la partita non e' piu' nel
    feed da almeno ``ASSENZA_FEED_S``. Aggiorna ``assenti_dal`` (memoria del
    supervisore): una partita tornata nel feed si dimentica."""
    fuori: List[str] = []
    viste: Set[str] = set()
    for r in righe_auto_attive or []:
        ev = str(r.get("event_id") or "")
        if not ev:
            continue
        viste.add(ev)
        if ev in nel_feed:
            assenti_dal.pop(ev, None)
            continue
        dal = assenti_dal.setdefault(ev, float(ora))
        if float(ora) - dal >= ASSENZA_FEED_S:
            fuori.append(ev)
    for ev in [e for e in assenti_dal if e not in viste]:
        assenti_dal.pop(ev, None)
    return fuori


# ---------------------------------------------------------------------------
# 4. il messaggio (le parole che la Control Room mostra)
# ---------------------------------------------------------------------------
MOTIVO_GUARDIA = ("guardia d'avvio: aperture bloccate finche' il controllo "
                  "d'avvio dell'app non riesce")
MOTIVO_FEED_MUTO = ("feed calcio non disponibile (scanner fermo o lettura KO): "
                    "nessuna partita dal feed")
MOTIVO_FEED_VUOTO = "feed calcio vuoto: nessuna partita in gioco o imminente ora"
MOTIVO_ORIGINE_ASSENTE = ("auto-mode spento: migrazione "
                          "scalper_auto_mode_2026-09-25.sql non applicata")
MOTIVO_TETTO_ZERO = "auto-mode spento (tetto 0): solo le partite armate dalla card"


def motivo_conflitto(opposta: str) -> str:
    return ("sessioni in %s ancora attive: paper e live mai insieme, nessuna "
            "partita nuova finche' non si fermano"
            % ("soldi veri" if opposta == "live" else "prova"))


def motivo_blocco(*, acceso: bool, bloccato: bool, feed_letto: bool,
                  feed_vivo: bool, partite_feed: int, origine_ok: bool,
                  tetto: int, sessioni: int, conflitto: Optional[str],
                  armabili: int) -> Optional[str]:
    """PERCHE' lo scalper acceso non sta lavorando su nessuna partita. ``None``
    = almeno una sessione con un processo, oppure spento. Mai un motivo con una
    sessione viva: "acceso ma non apre" sarebbe falso."""
    if not acceso:
        return None
    if bloccato:
        return MOTIVO_GUARDIA
    if sessioni > 0:
        return None
    if not origine_ok:
        return MOTIVO_ORIGINE_ASSENTE
    if tetto <= 0:
        return MOTIVO_TETTO_ZERO
    if conflitto:
        return motivo_conflitto(conflitto)
    if not feed_letto or not feed_vivo:
        return MOTIVO_FEED_MUTO
    if partite_feed <= 0:
        return MOTIVO_FEED_VUOTO
    if armabili <= 0:
        return ("nessuna partita armabile fra le %d del feed (oltre la vita "
                "della sessione, chiuse a mano, concluse o in errore)"
                % int(partite_feed))
    return None
