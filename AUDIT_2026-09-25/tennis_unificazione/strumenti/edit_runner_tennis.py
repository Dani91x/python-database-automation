"""Motore ordini + aggancio a comando nel runner tennis (F8). Lanciato una volta."""
import io

p = "Betfair/stream/tennis_live/tennis_runner.py"
s = io.open(p, encoding="utf-8").read()


def sost(old, new, n=1):
    global s
    assert s.count(old) == n, (s.count(old), old[:90])
    s = s.replace(old, new)


# --- import
sost('''from . import chiusura_manuale as _cm
from . import guardie_tennis as _gt
''', '''from . import chiusura_manuale as _cm
from . import esecutore_tennis as _ET
from . import guardie_tennis as _gt
''')

# --- sessione: stato dell'aggancio a comando
sost('''        self.caldo_rifiuti_annotati: set = set()
''', '''        self.caldo_rifiuti_annotati: set = set()
        # 25/09 (F8) - AGGANCIO A COMANDO (``esecutore_tennis.AgganciaTennis``):
        # le partite chieste da un ordine di un bot (event_id -> {market_id,
        # meta, ultimo_uso}), il book che flumine aveva quando la loro
        # sottoscrizione e' partita (market_id -> id(book)) e l'ultima lista dei
        # follow letta dal DB (None = mai letta: nessun allineamento a comando).
        self.comandi: Dict[str, Dict[str, Any]] = {}
        self.attesa_libro: Dict[str, Optional[int]] = {}
        self.ultimi_follows: Optional[List[Dict[str, Any]]] = None
''')

# --- catalogo: solo MATCH_ODDS tennis per un mercato chiesto da un comando
sost('''def _resolve_market(trading: Any, market_id: Optional[str], event_id: Optional[str]) -> Dict[str, Any]:
    from betfairlightweight import filters

    filt = (
        filters.market_filter(market_ids=[market_id]) if market_id
''', '''def _resolve_market(trading: Any, market_id: Optional[str], event_id: Optional[str],
                    solo_match_odds: bool = False) -> Dict[str, Any]:
    from betfairlightweight import filters

    filt = (
        # 25/09 (F8): un mercato chiesto da un COMANDO deve essere il MATCH_ODDS
        # di una partita di tennis (l'unico che il runner sottoscrive)
        filters.market_filter(market_ids=[market_id], event_type_ids=[TENNIS_EVENT_TYPE_ID],
                              market_type_codes=["MATCH_ODDS"])
        if market_id and solo_match_odds else
        filters.market_filter(market_ids=[market_id]) if market_id
''')
sost('''    dopo che la risottoscrizione e' riuscita. None = follow marcato ERROR."""
    event_id = follow["event_id"]
''', '''    dopo che la risottoscrizione e' riuscita. None = follow marcato ERROR."""
    event_id = follow["event_id"]
    # 25/09 (F8): la partita di un COMANDO porta il catalogo gia' risolto
    # dall'aggancio (nessuna seconda chiamata REST, nessuna riga di follow)
    gia = _ET.meta_da_catalogo(follow.get("_meta"))
    if gia is not None:
        return gia
''')

# --- piano al build: il comando non e' un follow a mano
sost('''    armate = _eventi_armati()
    voluti = [_IAC.Evento(ev, manuale=_AM.origine_follow(f) != _AM.ORIGINE_AUTO,
                          armata=ev in armate) for ev, f in visti.items()]
    piano = _IAC.pianifica([], voluti, tetto)
    for ev in piano.rifiutati:
        try:
''', '''    armate = _eventi_armati()
    voluti = [_IAC.Evento(ev, manuale=_manuale(f), armata=ev in armate,
                          comando=_ET.e_comando(f)) for ev, f in visti.items()]
    piano = _IAC.pianifica([], voluti, tetto)
    for ev in piano.rifiutati:
        if _ET.e_comando(visti.get(ev)):
            continue                     # nessuna riga di follow da annotare
        try:
''')
sost('''def _entro_il_tetto_al_build(follows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
''', '''def _manuale(follow: Optional[Dict[str, Any]]) -> bool:
    """Seguita a mano: ne' dal feed (``origine='auto'``) ne' da un comando."""
    return (_AM.origine_follow(follow) != _AM.ORIGINE_AUTO
            and not _ET.e_comando(follow))


def _entro_il_tetto_al_build(follows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
''')

# --- allineamento a caldo: comando, protezione del comando recente, attesa del libro
sost('''    seguiti = [
        _IAC.Evento(ev,
                    manuale=(ev in voluti_righe
                             and _AM.origine_follow(voluti_righe[ev]) != _AM.ORIGINE_AUTO),
                    armata=(ev in armate or ev in attivi),
                    posizioni=_evento_con_posizioni(flumine, session, ev))
        for ev in list(session.market_meta)
    ]
    voluti = [_IAC.Evento(ev, manuale=_AM.origine_follow(f) != _AM.ORIGINE_AUTO,
                          armata=ev in armate)
              for ev, f in voluti_righe.items()]
''', '''    seguiti = [
        _IAC.Evento(ev,
                    manuale=(ev in voluti_righe and _manuale(voluti_righe[ev])),
                    armata=(ev in armate or ev in attivi),
                    # 25/09 (F8): un comando appena chiesto e' protetto come una
                    # posizione (il suo ordine e' in volo o parcheggiato)
                    posizioni=(_evento_con_posizioni(flumine, session, ev)
                               or _ET.comando_recente(session, ev, ora)),
                    comando=(ev in voluti_righe and _ET.e_comando(voluti_righe[ev])))
        for ev in list(session.market_meta)
    ]
    voluti = [_IAC.Evento(ev, manuale=_manuale(f), armata=ev in armate,
                          comando=_ET.e_comando(f))
              for ev, f in voluti_righe.items()]
''')
sost('''        session.caldo_rifiuti_annotati.add(ev)
        logger.warning("[tennis-follow] %s in attesa: tetto di %d mercati pieno e nessuna "
                       "partita espellibile (posizioni vive, a mano o piu' prioritarie).",
                       ev, tetto)
        try:
''', '''        session.caldo_rifiuti_annotati.add(ev)
        logger.warning("[tennis-follow] %s in attesa: tetto di %d mercati pieno e nessuna "
                       "partita espellibile (posizioni vive, a mano o piu' prioritarie).",
                       ev, tetto)
        if _ET.e_comando(voluti_righe.get(ev)):
            continue                     # comando: nessuna riga di follow da annotare
        try:
''')
sost('''        stream = _IAC.stream_di_mercato(fw, caldo.capture)
        if sorted({str(m) for m in mids}) != _IAC.mercati_dello_stream(stream):
            _IAC.sottoscrivi(fw, stream, mids)
''', '''        stream = _IAC.stream_di_mercato(fw, caldo.capture)
        if sorted({str(m) for m in mids}) != _IAC.mercati_dello_stream(stream):
            # 25/09 (F8): il book che flumine ha ORA dei mercati che entrano
            # (siamo nel suo ciclo: nessun book nuovo puo' arrivare prima della
            # sottoscrizione). Un comando in attesa parte solo con un book NUOVO.
            mercati_fw = getattr(getattr(fw, "markets", None), "markets", {}) or {}
            attesa = {}
            for ev in entrano:
                mid_n = str(metas[ev]["market_id"])
                m_fw = mercati_fw.get(mid_n) if isinstance(mercati_fw, dict) else None
                libro = getattr(m_fw, "market_book", None) if m_fw is not None else None
                attesa[mid_n] = id(libro) if libro is not None else None
            _IAC.sottoscrivi(fw, stream, mids)
            session.attesa_libro.update(attesa)
''')
sost('''    for ev in esito.get("entrati", []):
        session.caldo_rifiuti_annotati.discard(ev)
        try:
            tennis_db.set_tennis_follow_status(ev, "STREAMING")
''', '''    for ev in esito.get("entrati", []):
        session.caldo_rifiuti_annotati.discard(ev)
        if _ET.e_comando(voluti_righe.get(ev)):
            continue                     # comando: nessuna riga di follow
        try:
            tennis_db.set_tennis_follow_status(ev, "STREAMING")
''')
sost('''    for ev in esito.get("usciti", []):
        assenti.pop(ev, None)
        if ev in espulsi:
''', '''    for ev in esito.get("usciti", []):
        assenti.pop(ev, None)
        session.attesa_libro.pop(str((metas.get(ev) or {}).get("market_id") or ""), None)
        if ev in espulsi and not _ET.e_comando(voluti_righe.get(ev)):
''')

# --- follow_worker: i comandi fanno parte della lista, e non forzano il restart
sost('''def follow_worker(context: dict, flumine: Any, session: TennisLiveSession) -> None:  # noqa: ARG001
    try:
        follows = tennis_db.list_pending_tennis_follows()
    except Exception as e:  # noqa: BLE001
        logger.warning("[tennis-follow] list KO: %s", e)
        return
''', '''def follow_worker(context: dict, flumine: Any, session: TennisLiveSession) -> None:  # noqa: ARG001
    try:
        follows = tennis_db.list_pending_tennis_follows()
    except Exception as e:  # noqa: BLE001
        logger.warning("[tennis-follow] list KO: %s", e)
        return
    # 25/09 (F8): l'ultima lista del DB (per l'aggancio a comando) e le partite
    # dei comandi dentro la lista (altrimenti uscirebbero dopo la grazia)
    session.ultimi_follows = list(follows)
    follows = _ET.follows_con_comandi(session, follows)
''')
sost('''        if all(_AM.origine_follow(f) == _AM.ORIGINE_AUTO for f in new):
''', '''        if all(not _manuale(f) for f in new):
''')

# --- motore ordini: stato di processo + costruzione
sost('''def _stop_framework(flumine: Any) -> None:
''', '''# ---------------------------------------------------------------------------
# 25/09 (F8) - MOTORE ORDINI del runner tennis (``esecutore_tennis``): lo stesso
# ``MotoreOrdini`` del calcio sul canale 47332, col ``_dispatch`` vero del worker
# tennis, e l'aggancio a comando. SPENTO di serie: ``MOTORE_ORDINI_CANALE_TENNIS=1``.
# ---------------------------------------------------------------------------
_MOTORE_TENNIS: Dict[str, Any] = {"motore": None, "aggancio": None}


def _cartella_diario_tennis() -> str:
    from ..config_stream import DATA_DIR

    return (os.getenv("TENNIS_MOTORE_DIARIO_DIR", "").strip()
            or os.path.join(DATA_DIR, "_diario_ordini", "tennis"))


def _catalogo_comando(session: TennisLiveSession, market_id: str) -> Optional[Dict[str, Any]]:
    """Il catalogo del mercato di un comando (REST, thread dell'aggancio): SOLO
    un MATCH_ODDS di tennis. Un relogin e un secondo tentativo, poi None (il
    comando scade ``in_aggancio``, il bot ripete). Nessuna scrittura."""
    for tentativo in (1, 2):
        try:
            return _resolve_market(session.trading, market_id, None, solo_match_odds=True)
        except ValueError:
            return None                  # non e' un MATCH_ODDS di tennis
        except Exception as e:  # noqa: BLE001
            logger.warning("[tennis-aggancio] catalogo %s KO (tentativo %d): %s",
                           market_id, tentativo, str(e)[:120])
            if tentativo == 1:
                try:
                    session.trading.login()
                except Exception:  # noqa: BLE001
                    return None
    return None


def _allinea_per_comando(session: TennisLiveSession) -> None:
    """L'aggancio ha una partita nuova: lo stream si allinea SUBITO (non al giro
    del follow_worker), sulla stessa connessione. Senza framework vivo non si
    fa niente: la prossima build include le partite dei comandi."""
    ag = _MOTORE_TENNIS.get("aggancio")
    fw = getattr(ag, "_framework", None) if ag is not None else None
    if fw is None or session.ultimi_follows is None:
        return
    caldo = _caldo_attivo(fw, session)
    if caldo is None:
        # iscrizione a caldo spenta: la partita entra alla prossima ricostruzione
        _request_restart(fw, session, "partita chiesta da un comando", forza=False)
        return
    with session.caldo_lock:
        _allinea_follow_a_caldo(fw, session, caldo,
                                _ET.follows_con_comandi(session, session.ultimi_follows))


def _monta_motore_tennis(ch: Any, session: TennisLiveSession) -> None:
    """Costruisce e avvia aggancio e motore (una volta per processo)."""
    def _manuali() -> set:
        return {str(f.get("event_id")) for f in (session.ultimi_follows or [])
                if _manuale(f)}

    def _posizioni(ev: str) -> bool:
        ag = _MOTORE_TENNIS.get("aggancio")
        return _evento_con_posizioni(getattr(ag, "_framework", None), session, ev)

    ag = None
    if _IAC.acceso():
        ag = _ET.AgganciaTennis(
            session, risolvi=lambda mid: _catalogo_comando(session, mid),
            allinea=lambda: _allinea_per_comando(session),
            manuali=_manuali, posizioni=_posizioni)
        ag.avvia()
    else:
        logger.warning("[tennis-runner] iscrizione a caldo SPENTA: il motore rifiuta gli "
                       "ordini sulle partite non seguite")
    motore = _ET.costruisci_motore(
        ch, cartella_diario=_cartella_diario_tennis(),
        guardia_armata=lambda: bool(_gt.GUARDIA_RUNNER.blocca_aperture),
        motivo_guardia_order=_gt.MOTIVO_GUARDIA_LOCALE, aggancio=ag)
    # la ripresa d'avvio non disarma la guardia finche' il diario del motore non
    # e' verificato (comandi in volo al riavvio: listCurrentOrders per ref)
    _gt.imposta_ripresa_motore(
        lambda: motore.riprendi_da_diario(
            lambda refs: session.trading.betting.list_current_orders(
                customer_order_refs=list(refs), lightweight=True)))
    motore.avvia()
    # gli eventi ``order`` nascono dallo specchio del worker tennis
    from .tennis_live_order_worker import aggiungi_osservatore_ordini
    aggiungi_osservatore_ordini(motore._su_riga_specchio)
    _MOTORE_TENNIS.update({"motore": motore, "aggancio": ag})
    logger.info("[tennis-runner] motore ordini ATTIVO sul canale %s (diario %s), aggancio "
                "a comando %s", getattr(ch, "port", "?"), motore.diario.cartella,
                "ATTIVO" if ag is not None else "SPENTO")


def _smonta_motore_tennis() -> None:
    motore = _MOTORE_TENNIS.get("motore")
    ag = _MOTORE_TENNIS.get("aggancio")
    if ag is not None:
        ag.ferma()
    if motore is not None:
        try:
            from .tennis_live_order_worker import rimuovi_osservatore_ordini
            rimuovi_osservatore_ordini(motore._su_riga_specchio)
            motore.scrittore.svuota(5.0)
            motore.ferma()
        except Exception:  # noqa: BLE001
            logger.exception("[tennis-runner] arresto del motore ordini KO")
    _gt.imposta_ripresa_motore(None)
    _MOTORE_TENNIS.update({"motore": None, "aggancio": None})


def _stop_framework(flumine: Any) -> None:
''')

# --- setup_and_run: montaggio dopo il canale
sost('''    if _ch is not None:
        _ch.set_hello(mode=live_order_mode())
    _avvia_sveglia_armamento(session)   # 24/09, interruttore spento di serie
''', '''    if _ch is not None:
        _ch.set_hello(mode=live_order_mode())
    # 25/09 (F8) - motore ordini sul 47332 (opt-in): montato PRIMA del primo
    # framework; senza framework rifiuta (``runner_non_agganciato``).
    if (_ch is not None and live_order_mode() in ("PAPER", "LIVE") and _ET.acceso()
            and not only_event):
        try:
            _monta_motore_tennis(_ch, session)
        except Exception as ex:  # noqa: BLE001 - senza motore: percorso di prima
            logger.error("[tennis-runner] motore ordini NON avviato (%s): /comando/ "
                         "rifiutato come prima", str(ex)[:200])
            _smonta_motore_tennis()
    _avvia_sveglia_armamento(session)   # 24/09, interruttore spento di serie
''')
sost('''            session.restart_requested.clear()
            follows = tennis_db.list_pending_tennis_follows()
            if only_event:
                follows = [f for f in follows if f["event_id"] == only_event]
''', '''            session.restart_requested.clear()
            follows = tennis_db.list_pending_tennis_follows()
            if only_event:
                follows = [f for f in follows if f["event_id"] == only_event]
            else:
                # 25/09 (F8): le partite chieste dai comandi dei bot entrano con la build
                session.ultimi_follows = list(follows)
                follows = _ET.follows_con_comandi(session, follows)
''')
sost('''            for event_id in session.market_meta:
                tennis_db.set_tennis_follow_status(event_id, "STREAMING")
''', '''            for event_id in session.market_meta:
                if event_id in session.comandi and not any(
                        str(f.get("event_id")) == event_id and not _ET.e_comando(f)
                        for f in follows):
                    continue             # 25/09 (F8): partita di un comando, nessuna riga
                tennis_db.set_tennis_follow_status(event_id, "STREAMING")
''')
sost('''            logger.info("[tennis-runner] stream avviato: %d eventi, %d bot ospitati, "
                        "1 connessione Betfair (%d mercati).",
                        len(session.market_meta), len(session.hosted), len(all_market_ids))
            try:
                framework.run()
''', '''            logger.info("[tennis-runner] stream avviato: %d eventi, %d bot ospitati, "
                        "1 connessione Betfair (%d mercati).",
                        len(session.market_meta), len(session.hosted), len(all_market_ids))
            # 25/09 (F8): il motore e l'aggancio lavorano su QUESTO framework
            # (i comandi delle modalita' servibili: ``orders_enabled``)
            _motore = _MOTORE_TENNIS.get("motore")
            _aggancio = _MOTORE_TENNIS.get("aggancio")
            if _motore is not None and orders_enabled:
                session.attesa_libro.clear()     # book del framework di prima: morti
                _motore.aggancia(framework, session)
                if _aggancio is not None:
                    _aggancio.aggancia(framework)
            try:
                framework.run()
''')
sost('''            session.caldo = None     # framework fermo: niente piu' lavori a caldo
''', '''            session.caldo = None     # framework fermo: niente piu' lavori a caldo
            if _MOTORE_TENNIS.get("motore") is not None:
                _MOTORE_TENNIS["motore"].sgancia()   # framework morto: comandi rifiutati
                if _MOTORE_TENNIS.get("aggancio") is not None:
                    _MOTORE_TENNIS["aggancio"].sgancia()
''')
sost('''    finally:
        try:
            RAW_TEE.close()  # chiusura pulita dei file di registrazione (best-effort)
''', '''    finally:
        _smonta_motore_tennis()          # 25/09 (F8): no-op se non montato
        try:
            RAW_TEE.close()  # chiusura pulita dei file di registrazione (best-effort)
''')
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
