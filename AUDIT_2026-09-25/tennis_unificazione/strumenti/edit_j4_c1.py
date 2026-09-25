"""J4 sul canale (dichiarata) + C.12a sulle righe risolte dal canale. Lanciato una volta."""
import io

p = "Betfair/safe_strategy/certificazione_tennis.py"
s = io.open(p, encoding="utf-8").read()
old = '''def _j4(oss: Osservazione) -> Optional[str]:
    for o in oss.ordini:
        ref = str(o.get("customer_order_ref") or "")
'''
new = '''def _ordine_del_motore(oss: Osservazione, o: Dict[str, Any]) -> bool:
    """25/09 (F8): l'ordine e' nato da un COMANDO sul canale del runner? Lo e'
    se non porta il ref del bot e una riga MANDATA SUL CANALE (``meta.canale_ref``)
    e' sullo stesso mercato e selezione (per bet_id quando la riga lo conosce).
    Su Betfair quell'ordine porta il customerOrderRef di flumine, non il ref del
    bot: limite del protocollo (``motore_ordini``, estensione 24/09), il legame
    ref -> ordine sta nel diario del runner e negli eventi ``order``."""
    ref = str(o.get("customer_order_ref") or "")
    if not ref or ref.startswith("safe_tennis-t") or ref.startswith("safe-t"):
        return False
    for tr in oss.trades:
        meta = tr.get("meta") or {}
        if not isinstance(meta, dict) or not meta.get("canale_ref"):
            continue
        if tr.get("bet_id") and o.get("bet_id"):
            if str(tr.get("bet_id")) == str(o.get("bet_id")):
                return True
            continue
        if (str(tr.get("market_id") or "") == str(o.get("market_id") or "")
                and str(tr.get("selection_id") or "") == str(o.get("selection_id") or "")):
            return True
    return False


def _j4(oss: Osservazione) -> Optional[str]:
    for o in oss.ordini:
        if _ordine_del_motore(oss, o):
            continue            # giudicato da J4C-DICHIARATA (canale del runner)
        ref = str(o.get("customer_order_ref") or "")
'''
assert s.count(old) == 1
s = s.replace(old, new)
old = '''@_controllo("J5", "catalogo §7.7: il `bet_id` si salva SEMPRE, anche quando "'''
new = '''@_controllo("J4C-DICHIARATA",
            "25/09 (F8), canale del runner: l'ordine nato da un comando porta su "
            "Betfair il customerOrderRef di FLUMINE, non `safe_tennis-t<id>`; il bot "
            "lo rilegge dagli eventi `order` (ref del protocollo). Oltre la scadenza "
            "senza eventi la rilettura REST per ref NON lo trova (limite del "
            "protocollo, identico al calcio: reperto aperto)",
            quando=lambda o: any(_ordine_del_motore(o, x) for x in o.ordini))
def _j4c(oss: Osservazione) -> Optional[str]:
    for o in oss.ordini:
        if _ordine_del_motore(oss, o):
            return (f"DICHIARATA: ordine {o.get('bet_id')} del canale con ref Betfair "
                    f"'{o.get('customer_order_ref')}' (flumine): rilettura per ref "
                    f"solo dagli eventi del runner")
    return None


@_controllo("J5", "catalogo §7.7: il `bet_id` si salva SEMPRE, anche quando "'''
assert s.count(old) == 1
s = s.replace(old, new)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)

p = "Betfair/safe_strategy/bot_service.py"
s = io.open(p, encoding="utf-8").read()
old = '''        pulita = dict(tr)
        pulita["meta"] = {k: v for k, v in meta.items() if k not in ("reason", "err")}
        if matched > 0:
            os_mod._flumine_confirm(pulita, db=db, matched=matched,
'''
new = '''        pulita = dict(tr)
        pulita["meta"] = {k: v for k, v in meta.items() if k not in ("reason", "err")}
        if matched > 0:
            # 25/09 (F8, C.12a): la riga risolta dal canale porta CHIESTO,
            # ABBINATO, RESIDUO e PREZZO MEDIO come quella del REST
            # (``meta.esecuzione`` + colonne via ``requested_size``): prima il
            # canale confermava senza, e la consapevolezza dell'ordine si perdeva
            # (controllo C1 del tennis, visto dal banco sul canale).
            chiesto = float(tr.get("size") or 0.0)
            medio = float(ev.get("average_price_matched") or 0.0)
            pulita["meta"].setdefault("requested_size", round(chiesto, 2))
            pulita["meta"].setdefault("esecuzione", {
                "percorso": "canale", "canale_ref": ref, "fase": fase,
                "price_richiesto": tr.get("price"),
                "price_medio": (medio if medio > 1.0 else None),
                "size_richiesta": round(chiesto, 2),
                "size_abbinata": round(matched, 2),
                "size_residua": round(float(ev.get("size_remaining") or 0.0), 2)})
            os_mod._flumine_confirm(pulita, db=db, matched=matched,
'''
assert s.count(old) == 1
s = s.replace(old, new)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
