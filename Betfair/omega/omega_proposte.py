"""omega_proposte — IL PRODUTTORE DELLE PROPOSTE DI USCITA DI OMEGA (17/09/2026).

ORDINE DELL'UTENTE (17/09, regola NON negoziabile del mandato §1):

    «OMEGA DEVE AVERE LA SCHEDA DOVE L'UTENTE APPROVA LE USCITE, SIA IN PROFIT
     CHE IN LOSS, come succede con Safe tennis. Nessuna chiusura automatica.»

Questo modulo e' la meta' Python di quella scheda: guarda ogni gamba lay aperta
del bot, calcola i numeri (quanto si blocca chiudendo ORA, quanto vale tenerla
fino al settlement, la P che il risultato bancato esca, la liability impegnata)
e, quando chiudere batte tenere — **in profitto o in perdita** — SCRIVE UNA
PROPOSTA. Non manda niente a mercato. La firma la mette l'utente dalla Control
Room (`SchedaChiusuraOmega.tsx`), la RPC porta la riga da 'proposed' a 'pending'
e da li' in poi il percorso e' quello di sempre: `process_manual` la drena come
un `cashout` e la esegue con `execution.close_trade`.

PERCHE' ESISTE (memoria del 12/09): tutte e cinque le chiusure automatiche di
Omega v2 erano sbagliate — -42,39 EUR contro +79,95 EUR fatti dalle aperture. Su
un lay la liability e' GIA' impegnata: chiudere non riduce il rischio preso, lo
trasforma in perdita certa. Quella decisione la prende una persona, con i numeri
davanti.

IL MODELLO E' COPIATO, NON INVENTATO. E' quello della Safe tennis, vivo e
certificato dal 14/09 (`Betfair/safe_strategy/bot_service.py:_proponi_chiusura`,
`bot_db.py:scrivi_proposta_di_chiusura`): stessa coda, stessi stati, stesso
marcatore sulla riga, stessa regola «sostanza invariata = nessuna riscrittura»,
stessi due istanti (`decided_at` fermo, `proposed_at` mobile), stessa
riproposizione dopo un «ignora» SOLO a situazione cambiata.

IL RESPIRO DEL DATABASE (§20 della Costituzione) e' un vincolo di progetto, non
un dettaglio: il 13/09 Supabase e' andato giu' per budget di IO esaurito. Questo
modulo NON scrive niente quando non e' cambiato niente, non legge il book via
REST (solo il feed unico), e rilegge la coda al massimo ogni
``_RICONTROLLO_PROPOSTA_S`` per gamba.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Optional

from . import omega_engine as E
from . import omega_model as M
from . import omega_v3 as V3

logger = logging.getLogger("omega.proposte")

# il marcatore sulla riga del trade: dice che c'e' (o c'era) una proposta viva.
# Si guarda QUESTO, non il database, perche' altrimenti servirebbe una query per
# trade a ogni ciclo per una cosa che quasi sempre non c'e'.
PROPOSTA_KEY = "exit_proposal"

# Ogni quanto si ricontrolla che la proposta sia ANCORA in attesa di firma.
# E' anche l'intervallo minimo fra una proposta ignorata e la successiva: un
# INTERVALLO, non un blocco. Senza questo ricontrollo il marcatore sulla riga
# resterebbe valorizzato per sempre e chi ignora una volta resterebbe senza
# bottone su una posizione aperta (cert. Safe 14/09).
_RICONTROLLO_PROPOSTA_S = 20.0

# Quando si RIPROPONE una chiusura che l'utente ha ignorato: su un CAMBIAMENTO,
# in bene o in male. Non a tempo fisso (sarebbe una raffica che si impara a
# ignorare) e non una volta sola.
_RIPROPOSTA_TICK = 2        # il prezzo di chiusura si e' mosso di almeno N tick
_RIPROPOSTA_EUR = 0.10      # ...oppure il bloccabile e' cambiato di almeno tanto

# I MOTIVI CHE PROPONGONO. Gli altri (`tenere_vale_di_piu`, `aspettare_vale_di_piu`,
# `bloccabile_non_positivo`, `controparte_insufficiente`, `nessun_prezzo_di_back`)
# dicono perche' si TIENE, e non scrivono niente.
MOTIVI_CHE_PROPONGONO = ("blocca_il_profitto", "protezione", "cap", "rischio")

# I motivi TRANSITORI: l'uscita si vuole ancora, ma adesso non si puo' fare
# (nessun prezzo di back, controparte troppo sottile). Non sono un cambio di
# idea del bot, sono il book che respira: una proposta viva NON decade per
# questi — decadrebbe e rinascerebbe a ogni oscillazione, perdendo ogni volta
# l'istante della decisione.
MOTIVI_TRANSITORI = ("controparte_insufficiente", "nessun_prezzo_di_back")

# I motivi per cui una gamba non arriva nemmeno al calcolo. Sono DICHIARATI: una
# gamba che salta senza motivo scritto e' il buco che §14.2 vieta.
MOTIVI_DI_SALTO = ("feed_assente", "punteggio_assente", "selezione_aggregata",
                   "prezzi_non_freschi", "prezzo_di_back_assente",
                   "mercato_sospeso", "selezione_non_attiva",
                   "selezione_non_nel_feed", "gamba_ht_finita",
                   "posizione_senza_numeri")

# i cap GLOBALI: si misurano sugli aggregati della giornata del BOT.
#   (chiave del parametro, che cosa misura)
_CAP_GLOBALI = (("v3_daily_loss_cap", "perdita"),
                ("daily_loss_cap", "perdita"),
                ("v3_max_open_liability", "aperto"),
                ("max_open_liability", "aperto"))

# i cap DI GAMBA: si misurano sulla liability della riga. `max_liability_per_match`
# sta qui e non fra i globali perche' e' cosi' che il servizio lo applica gia'
# oggi — su UNA gamba, in `_size_and_place` (`E.apply_liability_cap`).
_CAP_DI_GAMBA = ("v3_max_liability_per_leg", "v3_max_liability_per_match",
                 "max_liability_per_match")

_TOLLERANZA_CAP = 0.011     # centesimi di arrotondamento, non uno sforamento


# ---------------------------------------------------------------------------
# i parametri del modello che ha vinto il banco
# ---------------------------------------------------------------------------
_PARAMETRI_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "data", "parametri_vincenti_2026-09-16.json")
_PARAMETRI_CACHE: dict[str, Any] = {}


def parametri_modello() -> "V3.Parametri":
    """I parametri del modello che ha VINTO il banco (`tools/banco_modelli.py`),
    dal file versionato. Se il file manca si usano i default di `omega_v3`: il
    servizio non deve mai fermarsi per un file di taratura assente — ma chi
    legge deve saperlo, e il log lo dice una volta sola."""
    if "valore" in _PARAMETRI_CACHE:
        return _PARAMETRI_CACHE["valore"]
    try:
        with open(_PARAMETRI_FILE, "r", encoding="utf-8") as fh:
            valori = json.load(fh)
        campi = {k: v for k, v in valori.items()
                 if k in V3.Parametri.__dataclass_fields__}
        # dal JSON i pesi per fascia arrivano come liste; `Parametri` e' frozen e
        # vuole tuple (una lista dentro un dataclass frozen sarebbe mutabile e
        # condivisa fra i chiamanti)
        if isinstance(campi.get("peso_per_fascia"), list):
            campi["peso_per_fascia"] = tuple(tuple(x) for x in campi["peso_per_fascia"])
        out = V3.Parametri(**campi)
    except (OSError, ValueError, TypeError) as ex:  # noqa: BLE001
        logger.warning("[omega.proposte] parametri del banco non letti (%s): si usano "
                       "i default di omega_v3", str(ex)[:120])
        out = V3.Parametri()
    _PARAMETRI_CACHE["valore"] = out
    return out


def svuota_le_cache() -> None:
    """Le cache di PROCESSO di questo modulo (un riavvio le butta via)."""
    _PARAMETRI_CACHE.clear()


# ---------------------------------------------------------------------------
# utilita'
# ---------------------------------------------------------------------------
def _f(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _cap_param(params: dict[str, Any], chiave: str) -> float:
    v = _f(params.get(chiave))
    return float(v) if v and v > 0 else 0.0


def cap_di_gamba_scattato(tr: dict[str, Any], params: dict[str, Any]) -> Optional[str]:
    """Il nome del tetto di GAMBA superato da questa riga, o None.

    Non e' un'accusa al passato: un cap puo' scattare perche' l'utente lo ha
    ABBASSATO dal pannello mentre la gamba era gia' aperta. In quel caso il bot
    deve dirglielo, non fingere che vada bene."""
    liab = _f(tr.get("liability"))
    if liab is None:
        return None
    for chiave in _CAP_DI_GAMBA:
        cap = _cap_param(params, chiave)
        if cap and liab > cap + _TOLLERANZA_CAP:
            return chiave
    return None


def cap_globale_scattato(*, db: Any, params: dict[str, Any],
                         now: datetime) -> Optional[str]:
    """Il nome del tetto GLOBALE scattato (perdita giornaliera, capitale
    impegnato), o None.

    ⚠️ RESPIRO DEL DATABASE: se nessuno di questi cap e' configurato — ed e' il
    caso della produzione di oggi, dove sono tutti a ZERO (§19.5) — questa
    funzione NON legge niente. La lettura degli aggregati si paga solo quando
    c'e' davvero un tetto da misurare, e passa comunque dalla cache del giro
    (`aggregates_cache_s`)."""
    from . import omega_service as S

    attivi = [(k, come) for k, come in _CAP_GLOBALI if _cap_param(params, k)]
    if not attivi:
        return None
    try:
        _pagina, del_bot = S._aggregati_cached(db, E.day_start_utc(now), now.timestamp())
    except Exception as ex:  # noqa: BLE001 — senza aggregati non si INVENTA un cap
        logger.warning("[omega.proposte] aggregati non letti: nessun cap valutato (%s)",
                       str(ex)[:120])
        return None
    realizzato = E.realized_effective(del_bot or {})
    impegnato = E.open_liability_effective(del_bot or {})
    for chiave, come in attivi:
        cap = _cap_param(params, chiave)
        if come == "perdita" and realizzato <= -cap:
            return chiave
        if come == "aperto" and impegnato > cap + _TOLLERANZA_CAP:
            return chiave
    return None


# ---------------------------------------------------------------------------
# il giro
# ---------------------------------------------------------------------------
def proposte_attive(params: dict[str, Any]) -> bool:
    """Il produttore gira quando il green-up AUTOMATICO non gira.

    Sono due modi opposti di gestire la stessa gamba e non possono convivere: o
    il bot chiude da solo (v2, `greenup_mode='auto'`), o CHIEDE (la scheda). Con
    `strategy_version >= 3` la whitelist spegne il green-up da sola
    (`omega_config.resolve_params`), quindi in V3 questo e' sempre vero; in v2 lo
    decide l'utente dal pannello, mettendo `greenup_mode='off'`. Questo modulo
    NON cambia nessun default: la scelta resta sua."""
    from . import omega_service as S

    return not S._greenup_active(params)


def process_proposte_uscita(*, params: dict[str, Any], market: Any, db: Any,
                            now: datetime, feed: Any = None) -> int:
    """Fase 1-bis del giro quando il green-up automatico e' spento: per ogni
    gamba lay aperta calcola i numeri dell'uscita e SCRIVE UNA PROPOSTA quando
    chiudere batte tenere. Ritorna quante proposte sono state scritte o
    aggiornate in questo giro. **Non manda mai un ordine.**

    L'elenco delle gambe e' quello gia' filtrato di ``_greenup_candidates``, che
    esclude per costruzione (ordine dell'utente del 16/09, R7-R9): le righe
    MANUALI dell'utente, le partite che ha CHIUSO, le posizioni chiuse FUORI
    dall'app e quelle con una chiusura in volo.
    """
    from . import omega_service as S

    if not proposte_attive(params):
        return 0
    try:
        candidati = S._greenup_candidates(db, S.eventi_chiusi_dall_utente(db, now.timestamp()))
    except Exception as ex:  # noqa: BLE001
        db.log("error", {"reason": "proposte_candidates_failed", "err": str(ex)[:160]})
        return 0
    if not candidati:
        return 0
    if feed is None:
        feed = lambda eid: S._feed_state_bounded(market, eid, S.GREENUP_MAX_AGE_S)  # noqa: E731
    cap_globale = cap_globale_scattato(db=db, params=params, now=now)
    scritte = 0
    for tr in candidati:
        try:
            payload = feed(str(tr.get("event_id") or ""))
            if _una_gamba(tr=tr, params=params, market=market, db=db, now=now,
                          payload=payload, cap_globale=cap_globale):
                scritte += 1
        except Exception as ex:  # noqa: BLE001 — una posizione rotta non blocca le altre
            db.log("error", {"reason": "proposta_failed", "trade_id": tr.get("id"),
                             "event_id": tr.get("event_id"), "err": str(ex)[:160]})
    return scritte


def _salta(db: Any, tr: dict[str, Any], motivo: str, **extra: Any) -> None:
    """La gamba non arriva al calcolo: si dichiara perche', una volta sola
    (``_log_dedup``: la stessa ragione a ogni giro sarebbe un log che nessuno
    legge e un database che non respira)."""
    from . import omega_service as S

    S._log_dedup(db, (tr.get("id"), f"proposta_{motivo}"), "skip",
                 {"trade_id": tr.get("id"), "event_id": tr.get("event_id"),
                  "fase": "proposta_uscita", "reason": motivo, **extra})


def _una_gamba(*, tr: dict[str, Any], params: dict[str, Any], market: Any, db: Any,
               now: datetime, payload: Optional[dict],
               cap_globale: Optional[str]) -> bool:
    """Una posizione: prezzi dal feed, P dal modello, proposta o decadenza.
    True = proposta scritta o aggiornata in questo giro."""
    from . import omega_service as S

    meta = dict(tr.get("meta") or {})
    event_id = str(tr.get("event_id") or "")
    if not isinstance(payload, dict):
        _salta(db, tr, "feed_assente")
        return False
    nome = str(tr.get("runner_name") or "")
    laid = V3.parse_scoreline(nome)
    if laid is None:
        # aggregato (Any Unquoted & co.): senza un punteggio da inseguire la
        # traiettoria non e' calcolabile in modo onesto. Non si inventa.
        _decadi(db, tr, meta, "selezione aggregata: la traiettoria non e' calcolabile")
        _salta(db, tr, "selezione_aggregata", runner=nome)
        return False
    sh, sa, minuto = payload.get("score_home"), payload.get("score_away"), payload.get("minute")
    if sh is None or sa is None or minuto is None:
        _salta(db, tr, "punteggio_assente")
        return False
    sh, sa, minuto = int(sh), int(sa), int(minuto)
    prezzo_ingresso, size = _f(tr.get("price")), _f(tr.get("size"))
    if not prezzo_ingresso or prezzo_ingresso <= 1.0 or not size or size <= 0:
        _salta(db, tr, "posizione_senza_numeri", price=tr.get("price"), size=tr.get("size"))
        return False

    blocco, half = S._greenup_block(tr, payload)
    if blocco is not None and not S._feed_prices_fresh(market, event_id):
        # cert. 12/09: lo STATO puo' avere fino a GREENUP_MAX_AGE_S, ma i PREZZI
        # di una chiusura hanno il tetto del cash out. Una proposta con un prezzo
        # vecchio e' un numero sbagliato sotto gli occhi di chi deve firmare.
        blocco = None
    if blocco is None:
        # ⚠️ NESSUNA lettura REST qui. Il green-up automatico ci va perche' sta
        # per PIAZZARE; una proposta e' una domanda, e non vale una chiamata
        # Betfair per gamba e per giro (regola del feed unico).
        _salta(db, tr, "prezzi_non_freschi")
        return False
    if half and minuto > 45:
        _decadi(db, tr, meta, "gamba HALF TIME SCORE: il primo tempo e' finito")
        _salta(db, tr, "gamba_ht_finita", minute=minuto)
        return False
    sid = int(tr.get("selection_id") or 0)
    prezzi, attesa = S._greenup_prices_from_block(blocco, sid)
    if prezzi is None:
        _salta(db, tr, str(attesa or "prezzo_di_back_assente"))
        return False
    back = _f(prezzi.get("back"))
    if not back or back <= 1.0:
        _salta(db, tr, "prezzo_di_back_assente")
        return False

    periodo = "ht" if half else "ft"
    p_evento, fonte_p, lambdas = _p_del_bancato(
        db=db, tr=tr, payload=payload, nome=nome, periodo=periodo,
        minuto=minuto, punteggio=(sh, sa), params=params)
    if p_evento is None:
        # il modello non sa dire niente su questa selezione: si TIENE e lo si
        # dichiara (mai una proposta con una P inventata)
        _salta(db, tr, "posizione_senza_numeri", nota="P del bancato non calcolabile")
        return False

    commissione = _f(tr.get("commission"))
    if commissione is None:
        commissione = float(params.get("commission_pct", 5.0)) / 100.0
    posizione = V3.Posizione(
        periodo=periodo, selection_name=nome, lay_price=float(prezzo_ingresso),
        size=float(size),
        punteggio_ingresso=_punteggio_ingresso(tr, (sh, sa)),
        minuto_ingresso=float(tr.get("minute_at_entry") or 0.0))
    cap = cap_globale or cap_di_gamba_scattato(tr, params)
    proposta = V3.proposta_uscita(
        posizione, minuto=float(minuto), punteggio=(sh, sa),
        back_price=back, back_size=_f(prezzi.get("back_size")),
        p_evento=float(p_evento), p=parametri_modello(), lambdas=lambdas,
        commissione=float(commissione), cap_scattato=cap,
        # la soglia arriva in PUNTI PERCENTUALI dal pannello (come `v3_p_max_pct`);
        # `proposta_uscita` ragiona in probabilita'. Zero = spenta (default).
        p_lose_max=float(params.get("proposta_p_lose_max_pct", 0.0) or 0.0) / 100.0)

    if not proposta.proponi:
        if str(proposta.motivo_codice) in MOTIVI_TRANSITORI:
            # NON e' che il bot abbia cambiato idea: e' il book che si e'
            # assottigliato per un istante. Far decadere la proposta qui
            # vorrebbe dire ucciderla e rifarla a ogni oscillazione del book —
            # misurato sul banco (35777617): 9 proposte e 8 decadenze su una
            # gamba sola, con `decided_at` che ripartiva ogni volta e la latenza
            # della firma che non voleva piu' dire niente. Il green-up
            # automatico, nello stesso caso, ASPETTA (`_greenup_wait`).
            _salta(db, tr, "prezzo_di_back_assente"
                   if proposta.motivo_codice == "nessun_prezzo_di_back"
                   else "controparte_insufficiente")
            return False
        _decadi(db, tr, meta, f"la condizione di uscita non regge piu': "
                              f"{proposta.motivo_codice}")
        return False
    return _scrivi(db=db, tr=tr, meta=meta, proposta=proposta, prezzi=prezzi,
                   minuto=minuto, punteggio=f"{sh}-{sa}", now=now,
                   fonte_p=fonte_p, cap=cap, params=params)


def _punteggio_ingresso(tr: dict[str, Any], adesso: tuple) -> tuple:
    """Il punteggio al momento dell'apertura, dalla riga. Se non c'e' si usa
    quello di adesso: e' l'unico ripiego onesto (serve solo alla traiettoria)."""
    grezzo = str(tr.get("score_at_entry") or "")
    if "-" in grezzo:
        pezzi = grezzo.split("-", 1)
        try:
            return (int(pezzi[0].strip()), int(pezzi[1].strip()))
        except (TypeError, ValueError):
            pass
    return adesso


def _p_del_bancato(*, db: Any, tr: dict[str, Any], payload: dict, nome: str,
                   periodo: str, minuto: int, punteggio: tuple,
                   params: dict[str, Any]
                   ) -> "tuple[Optional[float], str, Optional[tuple]]":
    """(P che il risultato bancato sia quello finale, fonte, lambda usati).

    Stessa catena del resto del servizio: i lambda li risolve
    ``_prematch_lambdas`` (fixture -> evento -> quote pre-KO -> audit -> OU
    live), la griglia la calcola `omega_v3` con i parametri che hanno vinto il
    banco. Senza lambda il modello gira comunque coi suoi default e la FONTE lo
    dichiara: un numero che non sa da dove viene non e' un numero."""
    from . import omega_service as S

    yh, ya = M.yellow_cards(payload)
    state = S._state_for_model(
        M.LiveState(int(minuto), int(punteggio[0]), int(punteggio[1]),
                    int(payload.get("red_home") or 0), int(payload.get("red_away") or 0),
                    yellow_home=yh, yellow_away=ya), params)
    lam = S._prematch_lambdas(db, str(tr.get("event_id") or ""), payload,
                              state=state, params=params)
    lambdas = (float(lam[0]), float(lam[1])) if lam else None
    fonte = f"v3:{lam[3]}" if lam else "v3:senza_lambda"
    nomi = _nomi_del_mercato(payload, tr, nome)
    try:
        probabilita = V3.probabilita_selezioni(
            periodo=periodo, minuto=float(minuto), punteggio=punteggio,
            nomi=nomi, p=parametri_modello(), lambdas=lambdas)
    except Exception as ex:  # noqa: BLE001 — modello KO: nessuna proposta, mai una P finta
        logger.warning("[omega.proposte] modello KO (trade %s): %s",
                       tr.get("id"), str(ex)[:120])
        return None, "modello_ko", lambdas
    p = probabilita.get(nome)
    return (None if p is None else float(p)), fonte, lambdas


def _nomi_del_mercato(payload: dict, tr: dict[str, Any], nome: str) -> list:
    """I nomi delle selezioni del mercato della gamba, dal feed unico.

    Servono a `probabilita_selezioni` per sapere che cosa e' quotato (e quindi
    che cosa finisce negli aggregati). Se il blocco non li porta si usa almeno
    il nome della nostra selezione: la P della cella esatta resta giusta."""
    from . import omega_service as S

    blocco, _half = S._greenup_block(tr, payload)
    fuori = []
    for s in ((blocco or {}).get("selections") or []):
        if not isinstance(s, dict) or s.get("runner_status") not in (None, "ACTIVE"):
            continue
        n = str(s.get("name") or "")
        if n:
            fuori.append(n)
    return fuori or [nome]


# ---------------------------------------------------------------------------
# scrittura, decadenza, riproposizione
# ---------------------------------------------------------------------------
def _sostanza(proposta: Any, size: Optional[float], punteggio: str) -> tuple:
    """LA SOSTANZA di una proposta: il motivo, quanto c'e' da chiudere e il
    punteggio. Il PREZZO non e' sostanza — la scheda lo pesca vivo dal feed, e
    riscrivere la riga a ogni tick per aggiornare un numero che la pagina ha
    gia' sarebbe traffico su un database che a settembre e' gia' andato giu' una
    volta per esaurimento di IO (§20)."""
    return (str(proposta.motivo_codice), None if size is None else round(float(size), 2),
            str(punteggio))


def _cambiamento_sostanziale(rifiutata: dict[str, Any], prezzo: Optional[float],
                             punteggio: Optional[str],
                             bloccabile: Optional[float]) -> Optional[str]:
    """La situazione e' DIVERSA da quella che l'utente ha gia' visto e scartato?

    Ritorna il motivo (da mostrare in pagina) oppure None. «Diverso» vale in
    entrambe le direzioni: se ignoro a -0,32 EUR e dieci minuti dopo la stessa
    uscita costa -1,08, quella e' una situazione nuova e va rivista. Ma anche il
    contrario — se nel frattempo e' migliorata, l'utente vuole saperlo."""
    from Betfair.safe_strategy import execution as X

    if str(punteggio or "") != str(rifiutata.get("score") or ""):
        return "il punteggio e' cambiato"
    vecchio, nuovo = rifiutata.get("bloccabile"), bloccabile
    if isinstance(vecchio, (int, float)) and isinstance(nuovo, (int, float)):
        if abs(float(nuovo) - float(vecchio)) >= _RIPROPOSTA_EUR - 1e-9:
            verso = "migliorato" if float(nuovo) > float(vecchio) else "peggiorato"
            return f"il risultato bloccabile e' {verso}"
    # la chiusura di un LAY e' un BACK: e' quello il lato che scorre
    passi = X.scorrimento(rifiutata.get("price"), prezzo, "back")
    if passi is not None and abs(int(passi)) >= _RIPROPOSTA_TICK:
        return "il prezzo di chiusura si e' mosso"
    return None


def _scrivi_meta(db: Any, tr: dict[str, Any], meta: dict[str, Any],
                 valore: Optional[dict[str, Any]]) -> None:
    nuovo = {k: v for k, v in meta.items() if k != PROPOSTA_KEY}
    if valore is not None:
        nuovo[PROPOSTA_KEY] = valore
    db.update_trade(int(tr["id"]), meta=nuovo)
    tr["meta"] = nuovo


def _decadi(db: Any, tr: dict[str, Any], meta: dict[str, Any], motivo: str) -> None:
    """La condizione di uscita non regge piu': la proposta viva decade.

    Si guarda il MARCATORE sulla riga, non il database: senza, servirebbe una
    query per trade a ogni ciclo per una cosa che quasi sempre non c'e'. Non e'
    un rifiuto dell'utente: e' il mercato che e' cambiato, e resta la traccia di
    una chiusura PROPOSTA e mai avvenuta."""
    if not isinstance(meta.get(PROPOSTA_KEY), dict):
        return
    try:
        db.chiudi_proposta(int(tr["id"]), motivo)
    except Exception as ex:  # noqa: BLE001 — non e' money-critical: nessun ordine in ballo
        logger.warning("[omega.proposte] decadenza KO (trade %s): %s",
                       tr.get("id"), str(ex)[:120])
    _scrivi_meta(db, tr, meta, None)
    db.log("proposta_decaduta", {"trade_id": tr.get("id"), "event_id": tr.get("event_id"),
                                 "motivo": str(motivo)[:180]})


def _scrivi(*, db: Any, tr: dict[str, Any], meta: dict[str, Any], proposta: Any,
            prezzi: dict[str, Any], minuto: int, punteggio: str, now: datetime,
            fonte_p: str, cap: Optional[str], params: dict[str, Any]) -> bool:
    """Scrive (o aggiorna) la proposta. True se la proposta esiste ed e' viva."""
    prima = meta.get(PROPOSTA_KEY) if isinstance(meta.get(PROPOSTA_KEY), dict) else {}
    prima = dict(prima or {})
    size = _f(tr.get("size"))
    sostanza = _sostanza(proposta, size, punteggio)
    invariata = (int(prima.get("request_id") or 0) > 0
                 and tuple(prima.get("sostanza") or ()) == sostanza)
    bloccabile = round(float(proposta.profitto_bloccabile), 2)
    back = _f(prezzi.get("back"))
    if int(prima.get("request_id") or 0) > 0:
        # IL MARCATORE NON BASTA A DIRE CHE LA PROPOSTA E' VIVA (cert. Safe
        # 14/09): se nel frattempo l'utente l'ha IGNORATA, il marcatore resta
        # sulla riga e non ne nascerebbe mai piu' una — chi ignora una volta
        # resta senza bottone su una posizione aperta, mentre il prezzo si muove
        # contro. Ogni `_RICONTROLLO_PROPOSTA_S` si va a VEDERE, invece di
        # dedurlo da un campo scritto tempo prima.
        eta = now.timestamp() - (_ts(prima.get("ts")) or 0.0)
        if invariata and eta < _RICONTROLLO_PROPOSTA_S:
            return True          # ricontrollata da poco: nessuna lettura, nessuna scrittura
        try:
            viva = db.proposta_di_chiusura_viva(int(tr["id"]))
        except Exception:  # noqa: BLE001 — nel dubbio si RIPROPONE: una proposta in
            viva = None     # piu' non costa, una in meno lascia una posizione senza uscita
        if viva is not None:
            if invariata:
                # ancora in attesa di firma e non e' cambiato niente di sostanza:
                # si rinfresca solo il marcatore (il prezzo vivo lo pesca la pagina)
                _scrivi_meta(db, tr, meta, {**prima, "ts": now.isoformat()})
                return True
            # viva ma la SOSTANZA e' cambiata (un gol, una size diversa, un
            # motivo nuovo): la riga si riscrive coi numeri di adesso, o la
            # scheda mostrerebbe la partita di dieci minuti fa.
        else:
            # IGNORATA (o finita in errore): non si ripropone subito e nemmeno a
            # tempo, ma quando la SITUAZIONE cambia. Alla prima volta si
            # fotografa cio' che l'utente ha scartato.
            rifiutata = prima.get("rifiutata")
            if not isinstance(rifiutata, dict):
                _scrivi_meta(db, tr, meta, {**prima, "ts": now.isoformat(),
                                            "rifiutata": {"price": back, "score": punteggio,
                                                          "bloccabile": bloccabile,
                                                          "ts": now.isoformat()}})
                return True      # scartata adesso: si aspetta che cambi qualcosa
            perche = _cambiamento_sostanziale(rifiutata, back, punteggio, bloccabile)
            if perche is None:
                _scrivi_meta(db, tr, meta, {**prima, "ts": now.isoformat()})
                return True      # tutto come l'aveva vista: non si insiste
            prima = {**prima, "riproposta_perche": perche}

    # l'istante della DECISIONE si conserva: se lo si rinfrescasse, la latenza
    # misurata sarebbe sempre ~zero e il numero direbbe il contrario del vero
    # (cert. Safe 14/09; controllo G2).
    decided_at = str(prima.get("decided_at") or now.isoformat())
    corpo = _payload(tr=tr, proposta=proposta, prezzi=prezzi, minuto=minuto,
                     punteggio=punteggio, decided_at=decided_at, now=now,
                     fonte_p=fonte_p, cap=cap,
                     riproposta_perche=prima.get("riproposta_perche"))
    try:
        rid = db.scrivi_proposta_di_chiusura(int(tr["id"]), corpo)
    except Exception as ex:  # noqa: BLE001
        _guasto_di_scrittura(db, tr, ex)
        return False
    if not rid:
        db.log("error", {"reason": "proposta_senza_id", "trade_id": tr.get("id"),
                         "critical": True,
                         "nota": "la coda non ha reso un id: nessuna proposta esiste, "
                                 "si riprova al giro dopo"})
        return False
    nuovo = {"request_id": int(rid), "ts": now.isoformat(), "decided_at": decided_at,
             "sostanza": list(sostanza), "motivo": str(proposta.motivo_codice)}
    _scrivi_meta(db, tr, meta, nuovo)
    db.log("proposta_riproposta" if prima.get("riproposta_perche") else "proposta_scritta",
           {"trade_id": tr.get("id"), "event_id": tr.get("event_id"),
            "request_id": int(rid), "motivo_codice": str(proposta.motivo_codice),
            "profitto_bloccabile": corpo["profitto_bloccabile"],
            "ev_tenere": corpo["ev_tenere"], "p_evento": corpo["p_evento"],
            "liability": corpo["liability"], "minute": minuto, "score": punteggio,
            "mode": corpo["mode"],
            # una proposta in perdita o da cap NON e' un affare: e' una richiesta
            # di ridurre il rischio, e la pagina deve poterla urlare
            "critical": bool(proposta.motivo_codice in ("protezione", "cap", "rischio")),
            **({"riproposta_perche": prima["riproposta_perche"]}
               if prima.get("riproposta_perche") else {})})
    return True


def _guasto_di_scrittura(db: Any, tr: dict[str, Any], ex: BaseException) -> None:
    """La proposta NON e' stata scritta. Fail-closed: niente proposta, niente
    chiusura, e si dice perche'.

    Se l'errore parla di SCHEMA e' la migrazione che manca
    (`migrations/omega_proposte_coda_unica_2026-09-17.sql`): allora e' uno
    `schema_warn`, che nella UI e' «MIGRAZIONE MANCANTE» — lo stesso pattern di
    O1 (`_chiudi_evento`). Se e' un guasto qualunque e' un `error` e si riprova
    al giro dopo."""
    from . import omega_db

    schema = False
    try:
        schema = bool(omega_db.pare_schema_mancante(ex))
    except Exception:  # noqa: BLE001 — un finto dei test puo' non avere la funzione
        schema = False
    if schema:
        db.log("schema_warn", {
            "trade_id": tr.get("id"), "event_id": tr.get("event_id"),
            "reason": "coda_proposte_non_pronta", "critical": True,
            "err": f"{type(ex).__name__}: {ex}"[:200],
            "nota": "la coda non accetta lo stato 'proposed': applicare "
                    "migrations/omega_proposte_coda_unica_2026-09-17.sql. Finche' "
                    "manca NON si scrive nessuna proposta e NON si chiude niente "
                    "(fail-closed): la posizione resta aperta e visibile."})
        return
    db.log("error", {"reason": "proposta_scrittura_fallita", "trade_id": tr.get("id"),
                     "event_id": tr.get("event_id"), "critical": True,
                     "err": f"{type(ex).__name__}: {ex}"[:200]})


def _ts(v: Any) -> Optional[float]:
    try:
        from Betfair.safe_strategy import exits as XE

        return XE.parse_ts(v)
    except Exception:  # noqa: BLE001
        return None


def _payload(*, tr: dict[str, Any], proposta: Any, prezzi: dict[str, Any],
             minuto: int, punteggio: str, decided_at: str, now: datetime,
             fonte_p: str, cap: Optional[str],
             riproposta_perche: Optional[str] = None) -> dict[str, Any]:
    """I campi della proposta, uno per uno — quelli della migrazione, piu' i tre
    che il mandato del 17/09 esige (`liability`, `p_evento`, `motivo_codice`).

    Sono CODICI, non frasi: la traduzione in italiano vive in UN solo posto
    (`frontend/src/lib/omegaProposte.ts`). Due tabelle che traducono la stessa
    cosa prima o poi dicono due cose diverse."""
    return {
        "trade_id": int(tr["id"]),
        "event_id": tr.get("event_id"),
        "event_name": tr.get("event_name"),
        "market_id": tr.get("market_id"),
        "market_type": tr.get("market_type"),
        "selection_id": tr.get("selection_id"),
        "selection_name": tr.get("runner_name"),
        # lato dell'ordine di CHIUSURA: un lay aperto si chiude BACKando la
        # stessa selezione. Insieme a market_id e selection_id e' la chiave con
        # cui la pagina pesca il prezzo VIVO dal feed di scansione.
        "side": "back",
        "entry_side": str(tr.get("side") or "lay").lower(),
        "entry_price": _f(tr.get("price")),
        "size": _f(tr.get("size")),
        # FOTOGRAFIA al momento della decisione: serve a sapere su cosa il bot ha
        # deciso e a misurare lo scostamento. NON e' il prezzo su cui si piazza.
        "price_at_decision": _f(prezzi.get("back")),
        "size_available_at_decision": _f(prezzi.get("back_size")),
        "motivo_codice": str(proposta.motivo_codice),
        # NEGATIVO = perdita che si blocca (proposta di protezione). Chi legge
        # questo campo non puo' assumere il segno.
        "profitto_bloccabile": round(float(proposta.profitto_bloccabile), 2),
        "back_price": _f(proposta.back_price),
        "back_size": _f(proposta.back_size),
        "ev_tenere": round(float(proposta.ev_tenere), 2),
        "p_evento": round(float(proposta.p_evento), 6),
        "p_fonte": str(fonte_p),
        # quanto e' impegnato su questa gamba: con stake fisso 1 EUR la liability
        # e' `quota - 1`, ed e' IL numero che dice quanto vale la protezione
        "liability": _f(tr.get("liability")),
        "meglio_aspettare": bool(proposta.meglio_aspettare),
        "bloccabile_max_atteso": round(float(proposta.bloccabile_max_atteso), 2),
        "minuto_del_massimo": (None if proposta.minuto_del_massimo is None
                               else float(proposta.minuto_del_massimo)),
        "minute": int(minuto),
        "score": str(punteggio),
        "mode": str(tr.get("mode") or "paper"),
        # il tetto scattato, quando c'e': il trader deve sapere che non gli si
        # sta proponendo un affare, gli si sta chiedendo di ridurre il rischio
        **({"cap_scattato": str(cap)} if cap else {}),
        # CERT. 14/09 — I DUE ISTANTI CHE RENDONO MISURABILE LA LATENZA.
        # `decided_at` non si rinfresca: e' il momento in cui la regola e'
        # scattata. `proposed_at` e' l'ultimo aggiornamento. La differenza fra
        # `decided_at` e il piazzamento e' la latenza vera di una chiusura
        # approvata a mano — quella che l'utente vuole vedere.
        "decided_at": str(decided_at),
        "proposed_at": now.isoformat(),
        # perche' questa chiusura si ripresenta dopo che l'utente l'aveva
        # ignorata: la pagina deve dirlo, o sembra insistenza invece che una
        # situazione nuova
        **({"riproposta_perche": str(riproposta_perche)} if riproposta_perche else {}),
    }
