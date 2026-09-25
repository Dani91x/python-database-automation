"""Profilo rapido: Safe tennis sul runner tennis (F8). Lanciato una volta."""
import io

p = "Betfair/stream/backtest/trasporto_rapido.py"
s = io.open(p, encoding="utf-8").read()


def sost(old, new, n=1):
    global s
    assert s.count(old) == n, (s.count(old), old[:90])
    s = s.replace(old, new)


sost('''  R10d mai in silenzio- mercato che non arriva mai (inesistente): dopo
                        ``aggancio_max_ms`` evento terminale ``rifiutato``
                        col motivo ``in_aggancio``, riga error, nessun ordine.
"""''', '''  R10d mai in silenzio- mercato che non arriva mai (inesistente): dopo
                        ``aggancio_max_ms`` evento terminale ``rifiutato``
                        col motivo ``in_aggancio``, riga error, nessun ordine.

25/09 (F8) - SAFE TENNIS (``certifica safe_tennis ... --scenari rapidi``): la
stessa catena sul runner TENNIS. Motore VERO con l'esecutore tennis
(``tennis_live.esecutore_tennis`` -> ``tennis_live_order_worker._dispatch``),
client VERO ``PortaCanale`` con l'attore ``safe_tennis`` e ref
``safe_tennis-t<id>``, risoluzione VERA della riga Safe (strategia ``tennis``).
Stessi scenari, con queste differenze DICHIARATE:
  R8  sotto il minimo - il runner tennis NON ha il place-and-trim: l'apertura
                        sotto il minimo e' rifiutata DICHIARANDOLO
                        (``submin_non_percorribile``), nessun ordine, riga
                        error (divergenza dalla REST di oggi: reperto);
  R10 famiglia        - l'aggancio e' ``AgganciaTennis`` di produzione
                        (priorita' COMANDO del piano ``iscrizione_a_caldo``);
                        al posto della risottoscrizione sulla connessione
                        Betfair il banco usa ``AllineaBancoTennis`` (latenza di
                        un book), come ``SottoscrittoreBanco`` per il calcio.
                        R10b/R10c usano partite «occupanti» con mercati fuori
                        registrazione (una registrazione tennis ha un solo
                        mercato): il piano le vede come partite vere.
"""''')
sost('''SCENARIO_ORDINI = {"safe_base": "ordini-manuali", "safe_esatto": "ordini-manuali",
                   "safe_punta": "ordini-manuali", "omega": "apertura"}
''', '''SCENARIO_ORDINI = {"safe_base": "ordini-manuali", "safe_esatto": "ordini-manuali",
                   "safe_punta": "ordini-manuali", "omega": "apertura",
                   # 25/09 (F8): su una registrazione tennis la strategia non ha
                   # mai le sue condizioni: l'ingresso dichiarato + le uscite
                   # sono gli unici ordini (``replay_tennis``)
                   "safe_tennis": "posizione-iniettata"}

#: prefisso del ref di riga per attore (il motore pretende ``f"{attore}-"``)
PREFISSI = {"omega": "omega-t", "safe": "safe-t", "safe_tennis": "safe_tennis-t"}
''')
sost('''    def monta_porta(self) -> None:
        self.smonta_porta()
        self.pb = self._PortaBanco(self.quadro, self.strat, attore=self.attore,
                                   modo_processo="LIVE")
''', '''    @property
    def sport(self) -> str:
        return TRA.SPORT_ATTORE.get(self.attore, "calcio")

    def monta_porta(self) -> None:
        self.smonta_porta()
        self.pb = self._PortaBanco(self.quadro, self.strat, attore=self.attore,
                                   modo_processo="LIVE", sport=self.sport)
''')
sost('''            from ...safe_strategy import porta_ordini as SPO

            self.client = SPO.PortaCanale(porta_ws=0, attore="safe", sport="calcio",
                                          connetti=self.pb.connetti,
                                          token_fn=lambda: self._TOKEN)
            self._rip = ("safe", SPO._PORTE.get("calcio"))
            SPO._PORTE["calcio"] = self.client
''', '''            from ...safe_strategy import porta_ordini as SPO

            self.client = SPO.PortaCanale(porta_ws=0, attore=self.attore, sport=self.sport,
                                          connetti=self.pb.connetti,
                                          token_fn=lambda: self._TOKEN)
            self._rip = ("safe:" + self.sport, SPO._PORTE.get(self.sport))
            SPO._PORTE[self.sport] = self.client
''')
sost('''            else:
                from ...safe_strategy import porta_ordini as SPO

                if prima is None:
                    SPO._PORTE.pop("calcio", None)
                else:
                    SPO._PORTE["calcio"] = prima
            self._rip = None
''', '''            else:
                from ...safe_strategy import porta_ordini as SPO

                sport = chi.split(":", 1)[1] if ":" in chi else "calcio"
                if prima is None:
                    SPO._PORTE.pop(sport, None)
                else:
                    SPO._PORTE[sport] = prima
            self._rip = None
''')
sost('''class _Safe:
    nome = "safe"

    def __init__(self, banco: BancoRapido) -> None:
        from ...safe_strategy.tools.replay_registrazioni import DbSafeMemoria

        self.b = banco
''', '''class _Safe:
    nome = "safe"

    def __init__(self, banco: BancoRapido) -> None:
        from ...safe_strategy.tools.replay_registrazioni import DbSafeMemoria

        self.b = banco
        # 25/09 (F8): Safe tennis = strategia 'tennis' (``exits.is_tennis``:
        # porta ``tennis``, ref ``safe_tennis-t<id>``); calcio invariato
        self.sport = banco.sport
''')
sost('''        riga = {"event_id": self.b.event_id, "market_id": self.b.market_id,
                "selection_id": None, "side": side, "price": price, "size": size,
                "status": "pending", "mode": mode, "strategy": "base",
                "meta": {"phase": "reserved"}}
''', '''        riga = {"event_id": self.b.event_id, "market_id": self.b.market_id,
                "selection_id": None, "side": side, "price": price, "size": size,
                "status": "pending", "mode": mode,
                "strategy": "tennis" if self.sport == "tennis" else "base",
                "meta": {"phase": "reserved"}}
''')
sost('''        from ...safe_strategy import execution as X

        self.db.update_trade(tid, selection_id=selection_id)
        meta: Dict[str, Any] = {"closes_trade_id": closes} if closes else {}
        return X.place(db=self.db, market=self.b.mercato_rest, mode=mode,
                       event_id=self.b.event_id, market_id=self.b.market_id,
                       selection_id=selection_id, side=side, price=price, size=size,
                       client_ref="safe-t%d" % tid, trade_id=tid, meta=meta,
''', '''        from ...safe_strategy import execution as X
        from ...safe_strategy import porta_ordini as SPO

        self.db.update_trade(tid, selection_id=selection_id)
        meta: Dict[str, Any] = {"closes_trade_id": closes} if closes else {}
        return X.place(db=self.db, market=self.b.mercato_rest, mode=mode,
                       event_id=self.b.event_id, market_id=self.b.market_id,
                       selection_id=selection_id, side=side, price=price, size=size,
                       client_ref=SPO.ref_ordine(tid, sport=self.sport), trade_id=tid,
                       meta=meta,
''')
sost('''        b.monta_porta()
        A = _Omega(b) if attore == "omega" else _Safe(b)
        pref = "omega-t" if attore == "omega" else "safe-t"
        stato: Dict[str, Any] = {}
        for nome, fn in (("R1 accettato", _r1), ("R2 freno", _r2),
                         ("R3 parziale", _r3), ("R4 canale giu'", _r4),
                         ("R5 duplicato", _r5), ("R6 comando vecchio", _r6),
                         ("R7 kill-switch", _r7), ("R8 sotto il minimo", _r8),
                         ("R9 sequenza", _r9), ("R10 mercato non seguito", _r10),
                         ("R10b tetto pieno", _r10b), ("R10c mai espulsi", _r10c),
                         ("R10d aggancio mai in silenzio", _r10d),
                         ("R2b mercato sospeso", _r2b)):
''', '''        b.monta_porta()
        A = _Omega(b) if attore == "omega" else _Safe(b)
        pref = PREFISSI[attore]
        stato: Dict[str, Any] = {}
        tennis = b.sport == "tennis"
        for nome, fn in (("R1 accettato", _r1), ("R2 freno", _r2),
                         ("R3 parziale", _r3), ("R4 canale giu'", _r4),
                         ("R5 duplicato", _r5), ("R6 comando vecchio", _r6),
                         ("R7 kill-switch", _r7),
                         ("R8 sotto il minimo", _r8_tennis if tennis else _r8),
                         ("R9 sequenza", _r9),
                         ("R10 mercato non seguito", _r10_tennis if tennis else _r10),
                         ("R10b tetto pieno", _r10b_tennis if tennis else _r10b),
                         ("R10c mai espulsi", _r10c_tennis if tennis else _r10c),
                         ("R10d aggancio mai in silenzio",
                          _r10d_tennis if tennis else _r10d),
                         ("R2b mercato sospeso", _r2b)):
''')

nuovi = '''

# ---------------------------------------------------------------------------
# 25/09 (F8) - gli scenari del runner TENNIS che differiscono dal calcio
# ---------------------------------------------------------------------------
def _motivo_esito_diario(b: BancoRapido, ref: str) -> str:
    mot = b.pb.motore
    esiti = [r for r in mot.diario.leggi(mot._giorni_diario())
             if r.get("tipo") == "esito" and r.get("ref") == ref]
    return str((esiti[-1].get("errore") if esiti else "") or "")


def _r8_tennis(b: BancoRapido, A: Any, pref: str, e: _Esito, stato: Dict[str, Any]) -> None:
    """Il runner tennis NON ha il place-and-trim: un'apertura sotto il minimo
    non parte e lo si DICE (``submin_non_percorribile``). Divergenza dichiarata
    dalla REST di oggi (place-and-trim REST): reperto per l'utente."""
    sel, prezzo_b, _d = b.quota("back")
    size = 1.50                                 # BACK sotto il minimo .it (2,00)
    tid = A.riserva(side="back", price=prezzo_b, size=size)
    ref = "%s%d" % (pref, tid)
    ord0, rest0 = len(b.ordini_del_motore()), _conta_rest(b)
    A.invia(tid, selection_id=sel, side="back", price=prezzo_b, size=size)
    fase = _aspetta_terminale(b, ref, secondi=5.0)
    motivo = _motivo_esito_diario(b, ref)
    e.controlla("evento terminale 'rifiutato' (mai in silenzio)", fase == "rifiutato", fase)
    e.controlla("motivo dichiarato 'submin_non_percorribile' nel diario del runner",
                motivo.startswith("submin_non_percorribile"), motivo[:160])
    e.controlla("nessun ordine, nessun REST",
                len(b.ordini_del_motore()) == ord0 and _conta_rest(b) == rest0,
                (len(b.ordini_del_motore()) - ord0, b.rest[rest0:]))
    e.controlla("nessun place-and-trim appeso", not b.pb.motore._submin,
                list(b.pb.motore._submin))
    riga = A.risolvi(tid)
    e.controlla("riga 'error' (nessun fill inventato)", riga.get("status") == "error",
                riga.get("status"))
    stato["r8_tennis_motivo"] = motivo[:200]


def _r10_tennis(b: BancoRapido, A: Any, pref: str, e: _Esito, stato: Dict[str, Any]) -> None:
    """Il runner tennis NON segue la partita: il comando di Safe tennis sul
    MATCH_ODDS vero e' accettato ``in_aggancio``, la partita entra nel piano
    a priorita' COMANDO e l'ordine parte al primo book NUOVO."""
    from ..tennis_live import iscrizione_a_caldo as IAC

    ag = b.pb.monta_aggancio_tennis(tetto=IAC.tetto_mercati(), seguiti={})
    try:
        sel, prezzo, _d = b.quota("lay")
        tid = A.riserva(side="lay", price=prezzo, size=2.0)
        ref = "%s%d" % (pref, tid)
        rest0, ord0 = _conta_rest(b), len(b.ordini_del_motore())
        e.controlla("prima del comando il runner NON segue il mercato",
                    not ag.servibile(b.market_id), dict(b.pb.sessione.market_meta))
        out = A.invia(tid, selection_id=sel, side="lay", price=prezzo, size=2.0)
        ack = _ack_di(b, ref)
        e.controlla("esito dell'invio 'pending' (il bot attende l'esito)",
                    getattr(out, "status", None) == "pending", out)
        e.controlla("ack ACCETTATO con motivo 'in_aggancio' (dichiarato)",
                    ack.get("accettato") is True
                    and str(ack.get("motivo") or "").startswith("in_aggancio"), ack)
        fase = _aspetta_terminale(b, ref)
        comandi = b.pb.sessione.comandi
        e.controlla("partita nel piano come COMANDO, con l'event_id vero del catalogo",
                    str(b.event_id) in comandi
                    and comandi[str(b.event_id)]["market_id"] == b.market_id,
                    {k: v.get("market_id") for k, v in comandi.items()})
        chiamate = ag.allinea_banco.chiamate
        e.controlla("sottoscrizione (allineamento) col mercato del comando",
                    bool(chiamate) and b.market_id in chiamate[-1], chiamate[-1:])
        e.controlla("evento terminale arrivato al client", fase is not None, fase)
        e.controlla("UN solo ordine su flumine per il comando",
                    len(b.ordini_del_motore()) - ord0 == 1,
                    len(b.ordini_del_motore()) - ord0)
        e.controlla("nessuna chiamata REST", _conta_rest(b) == rest0, b.rest[rest0:])
        tutte = " ".join(str(x.get("motivo") or x.get("error") or "")
                         for x in (b.pb.esiti(ref) or []))
        e.controlla("mai 'non sottoscritto' negli eventi", "non sottoscritto" not in tutte,
                    tutte[:200])
        riga = A.risolvi(tid)
        if fase == "abbinato":
            e.controlla("riga 'open' con l'abbinato del runner",
                        riga.get("status") == "open", riga.get("status"))
        else:
            e.controlla("FOK non abbinato: riga 'error' (esito vero, non un rifiuto del "
                        "runner)", riga.get("status") == "error" and fase != "rifiutato",
                        (riga.get("status"), fase))
        stato["r10_fase"] = fase
        stato["r10_aggancio"] = ag.stato()
    finally:
        b.pb.smonta_aggancio_tennis()


def _r10b_tennis(b: BancoRapido, A: Any, pref: str, e: _Esito, stato: Dict[str, Any]) -> None:
    """Tetto pieno (1): una partita candidata SENZA posizioni occupa il posto; il
    comando di Safe tennis sul MATCH_ODDS la espelle ed e' eseguito."""
    ag = b.pb.monta_aggancio_tennis(tetto=1, seguiti={"E-candidata": "1.000000001"})
    try:
        tid = A.riserva(side="lay", price=1.01, size=2.0)
        ref = "%s%d" % (pref, tid)
        ord0 = len(b.ordini_del_motore())
        sel, _p, _d = b.quota("lay")
        A.invia(tid, selection_id=sel, side="lay", price=1.01, size=2.0)
        ack = _ack_di(b, ref)
        e.controlla("ack accettato in_aggancio", ack.get("accettato") is True
                    and str(ack.get("motivo") or "").startswith("in_aggancio"), ack)
        fase = _aspetta_terminale(b, ref)
        meta = b.pb.sessione.market_meta
        e.controlla("la candidata SENZA posizioni e' espulsa, entra la partita del comando",
                    "E-candidata" not in meta and ag.allinea_banco.espulsi == ["E-candidata"]
                    and [v["market_id"] for v in meta.values()] == [b.market_id],
                    (dict(meta), ag.allinea_banco.espulsi))
        sul_cmd = [o for o in b.ordini_del_motore()[ord0:]
                   if str(getattr(o, "market_id", "")) == b.market_id]
        e.controlla("comando eseguito dopo l'espulsione: ordine ed evento terminale",
                    len(sul_cmd) >= 1 and fase is not None, (len(sul_cmd), fase))
        e.controlla("mai piu' partite del tetto",
                    all(len(c) <= 1 for c in ag.allinea_banco.chiamate),
                    ag.allinea_banco.chiamate)
        A.risolvi(tid)
    finally:
        b.pb.smonta_aggancio_tennis()


def _r10c_tennis(b: BancoRapido, A: Any, pref: str, e: _Esito, stato: Dict[str, Any]) -> None:
    """Tetto pieno (1) di partite NON espellibili: il MATCH_ODDS con gli ordini
    degli scenari precedenti (posizioni), poi una partita seguita A MANO. Niente
    espulso: rifiuto dichiarato ``tetto_mercati_pieno``, nessun ordine."""
    try:
        n_ord = len(list(iter(b.market.blotter)))
    except Exception:  # noqa: BLE001
        n_ord = 0
    if n_ord == 0:
        e.na = "il MATCH_ODDS non ha ordini dagli scenari precedenti"
        return
    sel, prezzo, _d = b.quota("lay")
    for caso, seguiti, manuali, mercato in (
            ("posizioni", {str(b.event_id): b.market_id}, (), "1.000000002"),
            ("manuale", {"E-a-mano": "1.000000001"}, ("E-a-mano",), b.market_id)):
        ag = b.pb.monta_aggancio_tennis(tetto=1, seguiti=seguiti, manuali=manuali)
        try:
            prima = dict(b.pb.sessione.market_meta)
            tid = A.riserva(side="lay", price=1.01, size=2.0)
            ref = "%s%d" % (pref, tid)
            ord0, rest0 = len(b.ordini_del_motore()), _conta_rest(b)
            out = _invia_su(b, A, tid, mercato, sel, 1.01)
            b.pompa(0.5)
            ack = _ack_di(b, ref)
            e.controlla("[%s] rifiuto dichiarato 'tetto_mercati_pieno'" % caso,
                        ack.get("accettato") is False
                        and str(ack.get("motivo") or "").startswith("tetto_mercati_pieno"),
                        ack)
            e.controlla("[%s] niente espulso: le partite seguite sono quelle di prima" % caso,
                        dict(b.pb.sessione.market_meta) == prima
                        and not ag.allinea_banco.espulsi, dict(b.pb.sessione.market_meta))
            e.controlla("[%s] nessun ordine, nessun REST" % caso,
                        len(b.ordini_del_motore()) == ord0 and _conta_rest(b) == rest0,
                        (len(b.ordini_del_motore()) - ord0, b.rest[rest0:]))
            e.controlla("[%s] esito certo negativo per il bot" % caso,
                        getattr(out, "status", None) == "error"
                        and "tetto_mercati_pieno" in str(getattr(out, "fill_note", "")),
                        out)
        finally:
            b.pb.smonta_aggancio_tennis()


def _r10d_tennis(b: BancoRapido, A: Any, pref: str, e: _Esito, stato: Dict[str, Any]) -> None:
    """Il mercato chiesto non esiste (il catalogo non lo risolve): il comando
    accettato ``in_aggancio`` NON scade in silenzio."""
    from ..tennis_live import iscrizione_a_caldo as IAC

    ag = b.pb.monta_aggancio_tennis(tetto=IAC.tetto_mercati(), seguiti={})
    prima_max = b.pb.motore.aggancio_max_ms
    b.pb.motore.aggancio_max_ms = 300
    try:
        sel, prezzo, _d = b.quota("lay")
        tid = A.riserva(side="lay", price=prezzo, size=2.0)
        ref = "%s%d" % (pref, tid)
        ord0, rest0 = len(b.ordini_del_motore()), _conta_rest(b)
        _invia_su(b, A, tid, "1.999999999", sel, prezzo)
        ack = _ack_di(b, ref)
        e.controlla("ack accettato in_aggancio", ack.get("accettato") is True
                    and str(ack.get("motivo") or "").startswith("in_aggancio"), ack)
        fine = time.monotonic() + 5.0
        ev: Dict[str, Any] = {}
        while time.monotonic() < fine:
            if b.un_book() is None:
                b.pb.aggiorna()
            ev = b.client.esiti(ref) or {}
            if ev.get("fase") == "rifiutato":
                break
            time.sleep(0.005)
        motivo = _motivo_esito_diario(b, ref)
        e.controlla("evento terminale 'rifiutato' (mai in silenzio)",
                    ev.get("fase") == "rifiutato", ev.get("fase"))
        e.controlla("esito nel diario del runner col motivo 'in_aggancio'",
                    motivo.startswith("in_aggancio"), motivo[:160])
        e.controlla("catalogo non risolto contato (mercato inesistente)",
                    ag.conti["catalogo_ko"] >= 1, ag.conti)
        e.controlla("nessun ordine, nessun REST",
                    len(b.ordini_del_motore()) == ord0 and _conta_rest(b) == rest0,
                    (len(b.ordini_del_motore()) - ord0, b.rest[rest0:]))
        e.controlla("nessun comando rimasto parcheggiato", not b.pb.motore._in_aggancio,
                    list(b.pb.motore._in_aggancio))
        riga = A.risolvi(tid)
        e.controlla("riga 'error'", riga.get("status") == "error", riga.get("status"))
        stato["r10d_motivo"] = motivo[:200]
    finally:
        b.pb.motore.aggancio_max_ms = prima_max
        b.pb.smonta_aggancio_tennis()
'''
marker = '''# ---------------------------------------------------------------------------
# l'ingresso da certifica
# ---------------------------------------------------------------------------'''
assert s.count(marker) == 1
s = s.replace(marker, nuovi.strip("\n") + "\n\n\n" + marker)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
