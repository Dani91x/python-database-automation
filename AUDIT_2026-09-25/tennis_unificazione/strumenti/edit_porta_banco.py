"""PortaBanco per il runner TENNIS (F8, banco). Lanciato una volta."""
import io

p = "Betfair/stream/backtest/porta_banco.py"
s = io.open(p, encoding="utf-8").read()


def sost(old, new, n=1):
    global s
    assert s.count(old) == n, (s.count(old), old[:90])
    s = s.replace(old, new)


sost('''Differenze DICHIARATE dal vivo (nel banco non esistono):''',
     '''25/09 (F8) - IL RUNNER TENNIS (``sport="tennis"``): lo STESSO motore con
l'esecutore tennis (``tennis_live.esecutore_tennis``: il ``_dispatch`` VERO di
``tennis_live_order_worker``). Il runner del banco e' una ``SessioneTennisBanco``
(le chiavi della ``TennisLiveSession`` che il worker tennis legge: partite
seguite, capture per partita, ordini tracciati); lo specchio e' il reconcile
VERO del worker tennis (``_reconcile_tracked`` -> ``_mirror_order`` ->
osservatori), col ``tennis_db`` sostituito da un nullo SOLO per la durata della
lettura (il banco non ha DB). L'aggancio a comando e' ``AgganciaTennis`` di
produzione con ``AllineaBancoTennis`` al posto della risottoscrizione sulla
connessione Betfair (``monta_aggancio_tennis``), come ``SottoscrittoreBanco``
per il calcio.

Differenze DICHIARATE dal vivo (nel banco non esistono):''')

sost('''class PortaBanco:
    """Porta ordini del banco = motore ordini di produzione su FlumineSimulation."""
''', '''class _TennisDbNullo:
    """Il ``tennis_db`` del banco: lo specchio non scrive (nessun DB)."""

    def __init__(self) -> None:
        self.righe: List[Dict[str, Any]] = []

    def upsert_tennis_order(self, riga: Dict[str, Any]) -> None:
        self.righe.append(dict(riga))

    def __getattr__(self, nome: str) -> Any:
        def _nulla(*_a: Any, **_k: Any) -> None:
            return None
        return _nulla


class _CaptureTutte(dict):
    """``session.capture`` del banco: ogni partita seguita ha come capture la
    strategia del banco (quella sotto cui vive anche la REST del banco)."""

    def __init__(self, sessione: "SessioneTennisBanco", strategia: Any) -> None:
        super().__init__()
        self._sessione = sessione
        self._strategia = strategia

    def get(self, chiave: Any, default: Any = None) -> Any:  # noqa: D401
        return self._strategia if str(chiave) in self._sessione.market_meta else default


class SessioneTennisBanco:
    """Le chiavi della ``tennis_runner.TennisLiveSession`` che l'esecutore e il
    worker tennis leggono. ``seguiti_tutti``: ogni MATCH_ODDS della registrazione
    e' seguito (il banco di sempre); altrimenti le partite seguite sono SOLO
    quelle in ``market_meta`` (aggancio a comando)."""

    def __init__(self, framework: Any, strategia: Any, *, seguiti_tutti: bool = True) -> None:
        self._framework = framework
        self.seguiti_tutti = seguiti_tutti
        self._meta: Dict[str, Dict[str, Any]] = {}
        self.capture = _CaptureTutte(self, strategia)
        self.tracked_orders: Dict[str, Any] = {}
        self.order_sig_cache: Dict[str, Any] = {}
        self.framework_gen = 0
        self.order_mode: Optional[str] = None
        self.hosted: Dict[tuple, Any] = {}
        self.comandi: Dict[str, Dict[str, Any]] = {}
        self.attesa_libro: Dict[str, Optional[int]] = {}
        self.positions_written: Dict[tuple, Any] = {}

    @property
    def market_meta(self) -> Dict[str, Dict[str, Any]]:
        if not self.seguiti_tutti:
            return self._meta
        out: Dict[str, Dict[str, Any]] = {}
        mercati = getattr(getattr(self._framework, "markets", None), "markets", None) or {}
        for mid, m in list(mercati.items()):
            md = getattr(getattr(m, "market_book", None), "market_definition", None)
            if md is not None and str(getattr(md, "market_type", "")) != "MATCH_ODDS":
                continue
            ev = str(getattr(m, "event_id", None) or mid)
            out.setdefault(ev, {"market_id": str(mid)})
        return out

    def segui_solo(self, per_evento: Dict[str, str]) -> None:
        """Da qui in poi il runner del banco segue SOLO queste partite."""
        self.seguiti_tutti = False
        self._meta = {str(ev): {"market_id": str(mid)} for ev, mid in per_evento.items()}


def meta_da_mercato_banco(framework: Any, market_id: str) -> Optional[Dict[str, Any]]:
    """Il «catalogo» del banco per un mercato: le chiavi di
    ``tennis_runner._resolve_market`` lette dal market definition VERO della
    registrazione. Mercato mai visto o non MATCH_ODDS: None (come il catalogo)."""
    mercati = getattr(getattr(framework, "markets", None), "markets", None) or {}
    m = mercati.get(str(market_id))
    md = getattr(getattr(m, "market_book", None), "market_definition", None) if m else None
    if md is None or str(getattr(md, "market_type", "")) != "MATCH_ODDS":
        return None
    runners = list(getattr(md, "runners", []) or [])
    nomi = {str(getattr(r, "selection_id", "")): str(getattr(r, "name", "") or
                                                      getattr(r, "selection_id", ""))
            for r in runners}
    return {"market_id": str(market_id), "event_id": str(getattr(m, "event_id", "") or ""),
            "market_type": "MATCH_ODDS", "market_name": "Match Odds",
            "name_to_sel": {v: int(k) for k, v in nomi.items() if k},
            "selection_names": nomi}


class AllineaBancoTennis:
    """L'``allinea`` dell'aggancio tennis nel banco: il piano VERO
    (``iscrizione_a_caldo.pianifica``, priorita' comando) applicato alla
    ``SessioneTennisBanco``. La «risposta di Betfair» e' il primo book NUOVO del
    mercato dopo la sottoscrizione (``attesa_libro``, latenza di un book), come
    fa il runner nel ciclo di flumine."""

    def __init__(self, porta: "PortaBanco", *, tetto: int,
                 manuali: Optional[Any] = None) -> None:
        self.porta = porta
        self.tetto = int(tetto)
        self.manuali = set(manuali or ())
        self.chiamate: List[List[str]] = []
        self.espulsi: List[str] = []

    def posizioni(self, ev: str) -> bool:
        mid = (self.porta.sessione.market_meta.get(str(ev)) or {}).get("market_id")
        mercati = getattr(getattr(self.porta.framework, "markets", None), "markets", None) or {}
        m = mercati.get(str(mid)) if mid else None
        if m is None:
            return False
        try:
            return len(list(iter(m.blotter))) > 0
        except Exception:  # noqa: BLE001 - nel dubbio: protetta
            return True

    def __call__(self) -> None:
        from ..tennis_live import esecutore_tennis as ET
        from ..tennis_live import iscrizione_a_caldo as IAC

        s = self.porta.sessione
        seguiti = [IAC.Evento(ev, manuale=ev in self.manuali, comando=ev in s.comandi,
                              posizioni=self.posizioni(ev) or ET.comando_recente(s, ev))
                   for ev in list(s.market_meta)]
        voluti = [IAC.Evento(e.event_id, e.manuale, comando=e.comando) for e in seguiti]
        voluti += [IAC.Evento(ev, comando=True) for ev in s.comandi if ev not in s.market_meta]
        piano = IAC.pianifica(seguiti, voluti, self.tetto)
        for ev in list(piano.togli) + list(piano.espulsi):
            s.market_meta.pop(ev, None)
        self.espulsi.extend(piano.espulsi)
        mercati = getattr(getattr(self.porta.framework, "markets", None), "markets", None) or {}
        for ev in piano.aggiungi:
            voce = s.comandi.get(ev)
            if voce is None:
                continue
            mid = str(voce["market_id"])
            m = mercati.get(mid)
            libro = getattr(m, "market_book", None) if m is not None else None
            s.attesa_libro[mid] = id(libro) if libro is not None else None
            s.market_meta[ev] = {"market_id": mid}
        self.chiamate.append(sorted(str(v["market_id"]) for v in s.market_meta.values()))


class PortaBanco:
    """Porta ordini del banco = motore ordini di produzione su FlumineSimulation."""
''')

sost('''        self._orologio = orologio_ms or (lambda: int(time.time() * 1000))
        self._cartella = cartella_diario or tempfile.mkdtemp(prefix="diario_banco_")
        self.motore = MO.MotoreOrdini(
            sport, canale=self.canale, diario=MO.Diario(self._cartella),
            scrittore=_ScrittoreNullo(), orologio_ms=self._orologio,
            modo_processo=modo_processo, blocco_modo=lambda *_a: None,
            eta_settings=lambda: 0.0)
        self.framework = framework
        self.strategia = strategia
''', '''        self._orologio = orologio_ms or (lambda: int(time.time() * 1000))
        self._cartella = cartella_diario or tempfile.mkdtemp(prefix="diario_banco_")
        self.sport = str(sport or "calcio")
        # 25/09 (F8): il runner TENNIS del banco = esecutore tennis + sessione
        esecutore = None
        self.sessione: Optional[SessioneTennisBanco] = None
        if self.sport == "tennis":
            from ..tennis_live import esecutore_tennis as esecutore
            self.sessione = SessioneTennisBanco(framework, strategia)
        self.motore = MO.MotoreOrdini(
            sport, canale=self.canale, diario=MO.Diario(self._cartella),
            scrittore=_ScrittoreNullo(), orologio_ms=self._orologio,
            modo_processo=modo_processo, blocco_modo=lambda *_a: None,
            eta_settings=lambda: 0.0, esecutore=esecutore)
        self.framework = framework
        self.strategia = strategia
''')
sost('''            self.cliente_live = ClienteLiveBanco(self.cliente_simulato)
            vista = _QuadroBanco(framework, [self.cliente_live, self.cliente_simulato])
            self.motore.aggancia(vista, {"live": strategia, "paper": strategia})
        else:
            self.motore.aggancia(framework, {"paper": strategia})
''', '''            self.cliente_live = ClienteLiveBanco(self.cliente_simulato)
            vista = _QuadroBanco(framework, [self.cliente_live, self.cliente_simulato])
            self.vista = vista
            self.motore.aggancia(vista, self.sessione if self.sessione is not None
                                 else {"live": strategia, "paper": strategia})
        else:
            self.vista = framework
            self.motore.aggancia(framework, self.sessione if self.sessione is not None
                                 else {"paper": strategia})
''')
sost('''        # 25/09: l'auto-follow di produzione montato sul motore (None = come prima)
        self.auto_follow: Any = None
''', '''        # 25/09: l'auto-follow di produzione montato sul motore (None = come prima)
        self.auto_follow: Any = None
        # 25/09 (F8): l'aggancio a comando del runner tennis (None = come prima)
        self.aggancio_tennis: Any = None
        self.tennis_db_nullo = _TennisDbNullo()
''')
sost('''            self.auto_follow.giro()
        if self.motore._in_aggancio:
''', '''            self.auto_follow.giro()
        if self.aggancio_tennis is not None:
            # il thread dell'aggancio, nel banco chiamato a ogni book
            self.aggancio_tennis.giro()
        if self.motore._in_aggancio:
''')
sost('''    def smonta_auto_follow(self) -> None:
        if self.auto_follow is not None:
            self.auto_follow.sgancia()
        self.auto_follow = None
        self.motore._aggancio = None
        self.motore._in_aggancio.clear()
''', '''    def smonta_auto_follow(self) -> None:
        if self.auto_follow is not None:
            self.auto_follow.sgancia()
        self.auto_follow = None
        self.motore._aggancio = None
        self.motore._in_aggancio.clear()

    def monta_aggancio_tennis(self, *, tetto: int, seguiti: Optional[Dict[str, str]] = None,
                              manuali: Any = ()) -> Any:
        """25/09 (F8): ``AgganciaTennis`` di PRODUZIONE sul motore del banco
        tennis. Il runner del banco segue SOLO ``seguiti`` (event_id -> market_id,
        vuoto = nessuna partita), il resto entra per comando."""
        from ..tennis_live import esecutore_tennis as ET

        if self.sessione is None:
            raise ValueError("aggancio tennis su un banco non tennis")
        self.sessione.segui_solo(dict(seguiti or {}))
        self.sessione.comandi.clear()
        self.sessione.attesa_libro.clear()
        allinea = AllineaBancoTennis(self, tetto=tetto, manuali=manuali)
        ag = ET.AgganciaTennis(
            self.sessione, risolvi=lambda mid: meta_da_mercato_banco(self.framework, mid),
            allinea=allinea, manuali=lambda: set(allinea.manuali),
            posizioni=allinea.posizioni, tetto=lambda: allinea.tetto)
        ag.allinea_banco = allinea
        ag.aggancia(self.vista)
        self.aggancio_tennis = ag
        self.motore._aggancio = ag
        return ag

    def smonta_aggancio_tennis(self) -> None:
        if self.aggancio_tennis is not None:
            self.aggancio_tennis.sgancia()
        self.aggancio_tennis = None
        self.motore._aggancio = None
        self.motore._in_aggancio.clear()
        if self.sessione is not None:
            self.sessione.seguiti_tutti = True
            self.sessione.comandi.clear()
            self.sessione.attesa_libro.clear()
''')
sost('''        from ..engine.live_trading_strategy import LiveTradingStrategy

        if self._sporco:
            self._sporco = False
''', '''        if self.sessione is not None:
            self._specchio_tennis()
            return
        from ..engine.live_trading_strategy import LiveTradingStrategy

        if self._sporco:
            self._sporco = False
''')
s = s.rstrip("\n") + '''

    def _specchio_tennis(self) -> None:
        """25/09 (F8): lo specchio del runner tennis, nel banco = il reconcile
        VERO del worker tennis (``_reconcile_tracked``: ordini tracciati da
        ``_track_manual``, write-on-change, terminali potati) con il motore fra
        gli osservatori (``_mirror_order`` -> ``_su_riga_specchio``) e il
        ``tennis_db`` nullo SOLO per questa lettura."""
        from ..tennis_live import tennis_live_order_worker as TW

        self._sporco = False
        for cust, rec in list(self.sessione.tracked_orders.items()):
            o = rec.get("order") if isinstance(rec, dict) else None
            if o is None or not str(cust).startswith("awtq"):
                continue
            chiave = str(getattr(o, "id", id(o)))
            if chiave not in self.ordini_visti:
                self.ordini_visti[chiave] = o
                self.ordini_nuovi.append(o)
        if not self.sessione.tracked_orders:
            return
        vero_db = TW.tennis_db
        TW.tennis_db = self.tennis_db_nullo
        TW.aggiungi_osservatore_ordini(self.motore._su_riga_specchio)
        try:
            TW._reconcile_tracked(self.sessione, self.vista)
        finally:
            TW.rimuovi_osservatore_ordini(self.motore._su_riga_specchio)
            TW.tennis_db = vero_db
'''
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
