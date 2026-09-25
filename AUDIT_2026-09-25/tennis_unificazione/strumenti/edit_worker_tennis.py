"""Modifiche al worker tennis per il motore ordini (F8). Lanciato una volta."""
import io

p = "Betfair/stream/tennis_live/tennis_live_order_worker.py"
s = io.open(p, encoding="utf-8").read()


def sost(old, new, n=1):
    global s
    assert s.count(old) == n, (s.count(old), old[:80])
    s = s.replace(old, new)


# 1) modo di processo: il contesto del thread (motore / banco) vale prima dell'env
sost('''    (cross-mode → error senza esecuzione, fix C1).
    """
    return os.getenv("TENNIS_LIVE_ORDER_MODE", "OFF").strip().upper()
''', '''    (cross-mode → error senza esecuzione, fix C1).

    25/09 (motore ordini tennis, F8): come ``live_order_worker._modo_processo``
    del calcio, ``_CONTESTO.modo_processo`` impostato SUL THREAD dal motore del
    banco vale al posto dell'env. Il worker (BackgroundWorker) non lo imposta
    mai: per lui nulla cambia.
    """
    from .. import live_order_worker as _low

    ov = getattr(_low._CONTESTO, "modo_processo", None)
    if ov:
        return str(ov).strip().upper()
    return os.getenv("TENNIS_LIVE_ORDER_MODE", "OFF").strip().upper()


def _strategy_ref() -> str:
    """customerStrategyRef verso Betfair: quello dell'ATTORE del comando quando
    l'ordine arriva dal motore (``_CONTESTO.strategy_ref``, es. ``safe_tennis``,
    come ``live_order_worker._strategy_ref_corrente`` del calcio); ``tennis``
    per la coda DB e il ``/order`` del desktop, come sempre."""
    from .. import live_order_worker as _low

    ref = getattr(_low._CONTESTO, "strategy_ref", None)
    return str(ref)[:15] if ref else CUSTOMER_STRATEGY_REF


def _pre_invio(order: Any, market: Any, what: str) -> None:
    """Diario write-ahead del motore (solo se impostato su questo thread): la
    riga ``ordine`` col customerOrderRef VERO PRIMA del place. Se non si
    scrive, l'ordine NON parte (ValueError = rifiuto pre-place)."""
    from .. import live_order_worker as _low

    _low._chiama_pre_invio(order, market, what)
''')

# 2) parse: time_in_force (FOK dal motore; la coda DB non lo porta)
sost('''        "params": merged.get("params") if isinstance(merged.get("params"), dict) else (src.get("params") or {}),
        "client_ref": merged.get("client_ref"),
    }
''', '''        "params": merged.get("params") if isinstance(merged.get("params"), dict) else (src.get("params") or {}),
        "client_ref": merged.get("client_ref"),
        # 25/09 (F8): FILL_OR_KILL per ordine (motore ordini: Safe tennis manda
        # FOK su ogni place normale, come sul calcio). Assente = come prima.
        "time_in_force": (str(merged["time_in_force"]).upper()
                          if merged.get("time_in_force") else None),
    }
''')

# 3) _do_place: riduzione, FOK, diario, strategy ref
sost('''    size = cmd["size"]
    if size is None and cmd.get("liability") is not None and side == "LAY" and price > 1.0:
        size = round(float(cmd["liability"]) / (price - 1.0), 2)
    if size is None:
        raise ValueError("size non derivabile")
    verdict = min_stake_rules(_jurisdiction(), side.lower(), float(price), float(size))
''', '''    size = cmd["size"]
    if size is None and cmd.get("liability") is not None and side == "LAY" and price > 1.0:
        size = round(float(cmd["liability"]) / (price - 1.0), 2)
    if size is None:
        raise ValueError("size non derivabile")
    # 25/09 (F8, come ``live_order_worker._do_place`` del calcio, CERT. 13/09):
    # una gamba di CHIUSURA (``params.reduces_liability``, messo dal motore SOLO
    # su un comando che la dichiara) e' accettata sotto il minimo di giurisdizione.
    params = cmd.get("params") if isinstance(cmd.get("params"), dict) else {}
    riduce = bool(params.get("reduces_liability"))
    tif = cmd.get("time_in_force")
    if tif not in (None, "FILL_OR_KILL"):
        raise ValueError(f"time_in_force non valido: {tif!r}")
    verdict = min_stake_rules(_jurisdiction(), side.lower(), float(price), float(size),
                              reduces_liability=riduce)
''')
sost('''    trade = Trade(market_id=market.market_id, selection_id=int(cmd["selection_id"]),
                  handicap=float(cmd.get("handicap") or 0.0), strategy=strategy)
    order = trade.create_order(
        side=side,
        order_type=LimitOrder(price=price, size=round(float(size), 2),
                              persistence_type=persistence),
    )
    if _tempi_on(): _TEMPI.place(order)  # noqa: E701 - F0: istante "place" (misura)
    ok = market.place_order(order, customer_strategy_ref=CUSTOMER_STRATEGY_REF,
                            **_client_kw(flumine, cmd["mode"]))
    if ok is False:
        raise ValueError(f"place RIFIUTATO — {_val(order, 'violation_msg') or 'violation'}")
''', '''    trade = Trade(market_id=market.market_id, selection_id=int(cmd["selection_id"]),
                  handicap=float(cmd.get("handicap") or 0.0), strategy=strategy)
    tipo = (LimitOrder(price=price, size=round(float(size), 2), persistence_type=persistence,
                       time_in_force=tif)
            if tif else
            LimitOrder(price=price, size=round(float(size), 2), persistence_type=persistence))
    order = trade.create_order(side=side, order_type=tipo)
    if riduce:
        try:
            order.context["reduces_liability"] = True   # chiusura: i control la lasciano passare
        except Exception:  # noqa: BLE001 - context assente su mock: solo metadato
            pass
    client_kw = _client_kw(flumine, cmd["mode"])
    _pre_invio(order, market, "place")   # 25/09: diario del motore (no-op per la coda)
    if _tempi_on(): _TEMPI.place(order)  # noqa: E701 - F0: istante "place" (misura)
    ok = market.place_order(order, customer_strategy_ref=_strategy_ref(), **client_kw)
    if ok is False:
        raise ValueError(f"place RIFIUTATO — {_val(order, 'violation_msg') or 'violation'}")
''')

# 4) greenup: diario + strategy ref
sost('''    if _tempi_on(): _TEMPI.place(order)  # noqa: E701 - F0: istante "place" (misura)
    ok = market.place_order(order, customer_strategy_ref=CUSTOMER_STRATEGY_REF,
                            **_client_kw(flumine, cmd["mode"]))
    if ok is False:
        raise ValueError(f"greenup RIFIUTATO — {_val(order, 'violation_msg') or 'violation'}")
''', '''    client_kw = _client_kw(flumine, cmd["mode"])
    _pre_invio(order, market, "greenup")   # 25/09: diario del motore (no-op per la coda)
    if _tempi_on(): _TEMPI.place(order)  # noqa: E701 - F0: istante "place" (misura)
    ok = market.place_order(order, customer_strategy_ref=_strategy_ref(), **client_kw)
    if ok is False:
        raise ValueError(f"greenup RIFIUTATO — {_val(order, 'violation_msg') or 'violation'}")
''')

# 5) specchio: riga pura + osservatori
sost('''def _mirror_order(mode: str, event_id: Optional[str], cust_ref: str, order: Any,
                  cmd: Dict[str, Any], source: str = "manual",
                  status_override: Optional[str] = None,
                  pnl: Optional[float] = None,
                  commission: Optional[float] = None,
                  settled_at: Optional[str] = None) -> None:
''', '''# 25/09 (F8) - OSSERVATORI dello specchio ordini tennis: il motore ordini del
# runner (``motore_ordini.MotoreOrdini._su_riga_specchio``) trasforma ogni riga
# di un ordine nato da un comando in un evento ``order`` per l'attore (Safe
# tennis). Stesso schema di ``db.aggiungi_osservatore_ordini`` del calcio. La
# notifica avviene PRIMA della scrittura DB e non dipende da lei.
_OSSERVATORI_ORDINI: list = []


def aggiungi_osservatore_ordini(cb: Any) -> None:
    if cb not in _OSSERVATORI_ORDINI:
        _OSSERVATORI_ORDINI.append(cb)


def rimuovi_osservatore_ordini(cb: Any) -> None:
    try:
        _OSSERVATORI_ORDINI.remove(cb)
    except ValueError:
        pass


def _notifica_osservatori(riga: Dict[str, Any]) -> None:
    for cb in list(_OSSERVATORI_ORDINI):
        try:
            cb(dict(riga))
        except Exception as e:  # noqa: BLE001 - un osservatore non ferma lo specchio
            logger.debug("[tennis-order] osservatore specchio KO: %s", e)


def riga_specchio(mode: str, event_id: Optional[str], cust_ref: str, order: Any,
                  cmd: Dict[str, Any], source: str = "manual",
                  status_override: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """La riga di ``tennis_live_orders`` di un ordine (PURA, nessun I/O). None se
    l'ordine non ha ancora uno status (colonna NOT NULL, fix #6)."""
    snap = _order_snapshot(order)
    status = status_override or snap.get("status")
    if status is None:
        return None
    mode_l = str(mode or "paper").strip().lower()
    return {
        "mode": mode_l,
        "source": source,
        "client_order_ref": cust_ref,
        "request_id": _request_id_from_ref(cust_ref),
        "event_id": event_id,
        "market_id": snap.get("market_id") or cmd.get("market_id"),
        "selection_id": snap.get("selection_id") or cmd.get("selection_id"),
        "handicap": cmd.get("handicap") or 0.0,
        "side": snap.get("side") or cmd.get("side"),
        "order_type": cmd.get("order_type") or "LIMIT",
        "price": snap.get("price"),
        "size": snap.get("size"),
        "size_matched": snap.get("size_matched") or 0.0,
        "size_remaining": snap.get("size_remaining") or 0.0,
        "size_cancelled": snap.get("size_cancelled") or 0.0,
        "size_lapsed": snap.get("size_lapsed") or 0.0,
        "size_voided": snap.get("size_voided") or 0.0,
        "average_price_matched": snap.get("average_price_matched") or 0.0,
        "status": status,
        "bet_id": snap.get("bet_id"),
        "persistence": cmd.get("persistence"),
    }


def _mirror_order(mode: str, event_id: Optional[str], cust_ref: str, order: Any,
                  cmd: Dict[str, Any], source: str = "manual",
                  status_override: Optional[str] = None,
                  pnl: Optional[float] = None,
                  commission: Optional[float] = None,
                  settled_at: Optional[str] = None) -> None:
''')
sost('''    snap = _order_snapshot(order)
    status = status_override or snap.get("status")
    if status is None:
        # niente status → ordine non ancora reale (es. rimpiazzo async non materializzato):
        # NON scrivere (status è NOT NULL). Il prossimo giro di reconcile lo prenderà.
        return
    mode_l = str(mode or "paper").strip().lower()
    try:
        tennis_db.upsert_tennis_order({
            "mode": mode_l,
            "source": source,
            "client_order_ref": cust_ref,
            "request_id": _request_id_from_ref(cust_ref),
            "event_id": event_id,
            "market_id": snap.get("market_id") or cmd.get("market_id"),
            "selection_id": snap.get("selection_id") or cmd.get("selection_id"),
            "handicap": cmd.get("handicap") or 0.0,
            "side": snap.get("side") or cmd.get("side"),
            "order_type": cmd.get("order_type") or "LIMIT",
            "price": snap.get("price"),
            "size": snap.get("size"),
            "size_matched": snap.get("size_matched") or 0.0,
            "size_remaining": snap.get("size_remaining") or 0.0,
            "size_cancelled": snap.get("size_cancelled") or 0.0,
            "size_lapsed": snap.get("size_lapsed") or 0.0,
            "size_voided": snap.get("size_voided") or 0.0,
            "average_price_matched": snap.get("average_price_matched") or 0.0,
            "status": status,
            "bet_id": snap.get("bet_id"),
            "persistence": cmd.get("persistence"),
''', '''    riga = riga_specchio(mode, event_id, cust_ref, order, cmd, source=source,
                         status_override=status_override)
    if riga is None:
        # niente status → ordine non ancora reale (es. rimpiazzo async non materializzato):
        # NON scrivere (status è NOT NULL). Il prossimo giro di reconcile lo prenderà.
        return
    if _OSSERVATORI_ORDINI:
        _notifica_osservatori(dict(riga, updated_at=_now_iso()))
    try:
        tennis_db.upsert_tennis_order({
            **riga,
''')

# 6) un solo thread alla volta piazza/annulla (il motore gira su un thread suo)
sost('''            status = "done"
            try:
                cmd_parsed = parse_order_payload({"payload": cmd, "id": sid})
                result = _dispatch(flumine, session, cmd_parsed, cust_ref)
''', '''            status = "done"
            try:
                cmd_parsed = parse_order_payload({"payload": cmd, "id": sid})
                # 25/09 (F8): stesso lucchetto del motore ordini (un thread alla volta)
                with _lucchetto_ordini():
                    result = _dispatch(flumine, session, cmd_parsed, cust_ref)
''')
sost('''        result = None
        try:
            cmd = parse_order_payload(row)
            result = _dispatch(flumine, session, cmd, cust_ref)
''', '''        result = None
        try:
            cmd = parse_order_payload(row)
            with _lucchetto_ordini():   # 25/09 (F8): stesso lucchetto del motore
                result = _dispatch(flumine, session, cmd, cust_ref)
''')
sost('''def _dispatch(flumine: Any, session: Any, cmd: Dict[str, Any], cust_ref: str) -> Dict[str, Any]:
''', '''def _lucchetto_ordini() -> Any:
    """25/09 (F8): il lucchetto ordini del calcio (``LUCCHETTO_ORDINI``, RLock):
    col motore ordini montato DUE thread possono piazzare nel runner tennis (il
    BackgroundWorker di questo modulo e il thread del motore). Uno alla volta."""
    from .. import live_order_worker as _low

    return _low.LUCCHETTO_ORDINI


def _dispatch(flumine: Any, session: Any, cmd: Dict[str, Any], cust_ref: str) -> Dict[str, Any]:
''')
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
