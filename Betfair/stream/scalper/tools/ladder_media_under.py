"""TRACCIA PER IL LADDER della modalita' <<media under>> (05/10/2026).

Fa girare il replay VERO dello scalper (``replay_registrazioni.certifica_scenario``:
sessione di produzione ``run_session``, strategia ``MediaUnderStrategy``, flumine
del banco comune con coda e abbinamenti veri) su UNA registrazione e, in SOLA
LETTURA, fotografa a ogni book del mercato scelto:

  * il libro dell'Under (migliori ``livelli`` prezzi per lato, importi in EUR);
  * gli ordini della modalita' (lato, quota, importo, abbinato, resto, stato);
  * lo stato del ciclo (``stats`` della strategia) e il riquadro <<chiusura>>;
  * le attivita' emesse dal bot (ingresso, banca, rientro, massimo, live...).

Nessuna decisione e' presa qui: le prende il codice di produzione. La traccia e'
compressa (gzip) e la legge la pagina del ladder.

Compressione: un fotogramma quando cambia qualcosa (libro, ordini, stato) e
comunque al piu' uno ogni ``ogni_ms`` prima del fischio e ``ogni_ms_live`` in
gioco; i fotogrammi uguali al precedente non si scrivono.

Uso (dalla radice del repo, sul PC con le registrazioni):
    python -m Betfair.stream.scalper.tools.ladder_media_under 35797769 \\
        --scenario media-under-paper --uscita traccia.json.gz
    (``--scenario media-under-35`` per l'Under 3,5; ``--data-dir`` di serie:
    quella del banco, ``_live_raw``)

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
from typing import Any, Dict, List, Optional

from . import replay_registrazioni as R


def _f(x: Any, n: int = 2) -> Optional[float]:
    try:
        return round(float(x), n)
    except (TypeError, ValueError):
        return None


def _libro(runner: Any, livelli: int) -> Dict[str, List[List[float]]]:
    ex = getattr(runner, "ex", None)
    if ex is None:
        return {"b": [], "l": []}

    def lato(voci: Any) -> List[List[float]]:
        out = []
        for v in list(voci or [])[:livelli]:
            p = v.get("price") if isinstance(v, dict) else getattr(v, "price", None)
            s = v.get("size") if isinstance(v, dict) else getattr(v, "size", None)
            if p is not None:
                out.append([_f(p), _f(s, 0)])
        return out

    return {"b": lato(ex.available_to_back), "l": lato(ex.available_to_lay)}


def _testo(kind: str, p: Dict[str, Any]) -> str:
    """Il testo dell'attivita'; l'annullo non ha ``msg``: lo si scrive dai suoi campi."""
    msg = str(p.get("msg") or "")
    if msg or kind != "media_annullo":
        return msg
    lato = "banca" if str(p.get("side") or "").upper() == "LAY" else "punta"
    return "annullo %s @%s (resto %.2f EUR): %s" % (
        lato, _f(p.get("prezzo")), float(p.get("resto") or 0.0), str(p.get("motivo") or ""))


def _ordine(o: Any) -> List[Any]:
    ot = getattr(o, "order_type", None)
    st = getattr(o, "status", None)
    lato = str(getattr(getattr(o, "side", ""), "value", getattr(o, "side", "")) or "").upper()
    return [str(getattr(o, "id", ""))[-6:], "P" if lato == "BACK" else "B",
            _f(getattr(ot, "price", None)), _f(getattr(ot, "size", None)),
            _f(getattr(o, "size_matched", 0.0)), _f(getattr(o, "size_remaining", 0.0)),
            str(getattr(st, "value", st) or ""),
            str(getattr(ot, "persistence_type", "") or "")[:1]]


class Registratore:
    """Il fotografo: si aggancia al ponte del replay (sola lettura)."""

    def __init__(self, livelli: int, ogni_ms: int, ogni_ms_live: int) -> None:
        self.livelli = livelli
        self.ogni_ms = ogni_ms
        self.ogni_ms_live = ogni_ms_live
        self.fotogrammi: List[Dict[str, Any]] = []
        self._ultimo_ms: Optional[int] = None
        self._ultima_firma: Optional[str] = None
        self._eventi_da = 0
        self._ultima_chiusura: Optional[str] = None
        self.meta: Dict[str, Any] = {}

    def osserva(self, banco: Any, market: Any, market_book: Any, ms: int) -> None:
        mu = getattr(banco, "media", None)
        mid = getattr(banco, "media_mercato_scelto", None)
        if mu is None or mid is None or str(market.market_id) != str(mid):
            return
        under = getattr(banco, "media_under", None)
        runner = next((r for r in (market_book.runners or [])
                       if int(r.selection_id) == int(under or -1)), None)
        if runner is None:
            return
        inplay = bool(getattr(market_book, "inplay", False))
        libro = _libro(runner, self.livelli)
        try:
            ordini = [_ordine(o) for o in market.blotter.strategy_orders(mu)]
        except Exception:  # noqa: BLE001 - blotter illeggibile: nessun ordine
            ordini = []
        st = dict(getattr(mu, "stats", {}) or {})
        stato = {"stato": st.get("stato"), "rientri": st.get("rientri"),
                 "max": st.get("max_rientri"), "tot": st.get("totale_puntato"),
                 "media": st.get("quota_media"), "w": st.get("se_vince"),
                 "l": st.get("se_perde"), "cicli": st.get("cicli_chiusi"),
                 "pnl": st.get("pnl_chiuso_lordo"), "ob": st.get("obiettivo_lordo"),
                 "blocco": st.get("rientri_bloccati")}
        eventi = []
        for k, p, _t in banco.attivita_media[self._eventi_da:]:
            eventi.append([k, _testo(k, p), str(p.get("level") or "")])
        self._eventi_da = len(banco.attivita_media)
        firma = json.dumps([libro, ordini, stato, getattr(market_book, "status", "")],
                           sort_keys=True)
        passo = self.ogni_ms_live if inplay else self.ogni_ms
        if (not eventi and firma == self._ultima_firma) or (
                not eventi and self._ultimo_ms is not None and ms - self._ultimo_ms < passo):
            return
        fot: Dict[str, Any] = {"t": int(ms), "ip": inplay,
                               "st": str(getattr(market_book, "status", "") or ""),
                               "b": libro["b"], "l": libro["l"], "o": ordini, "s": stato}
        tv = getattr(getattr(runner, "ex", None), "traded_volume", None) or []
        ltp = getattr(runner, "last_price_traded", None)
        if ltp:
            fot["ltp"] = _f(ltp)
        fot["tv"] = _f(sum(float(v.get("size") or 0) for v in tv if isinstance(v, dict)), 0)
        ch = st.get("chiusura")
        firma_ch = json.dumps(ch, sort_keys=True) if ch else None
        if firma_ch != self._ultima_chiusura:
            fot["c"] = ch
            self._ultima_chiusura = firma_ch
        if eventi:
            fot["e"] = eventi
        self.fotogrammi.append(fot)
        self._ultimo_ms = ms
        self._ultima_firma = firma


def esporta(event_id: str, *, data_dir: str, scenario: str = R.SCENARIO_MEDIA_PAPER,
            livelli: int = 10, ogni_ms: int = 1000, ogni_ms_live: int = 5000) -> Dict[str, Any]:
    """Il replay VERO con il fotografo agganciato; torna la traccia (dizionario)."""
    from ...backtest.certifica import _freni_da_banco

    if scenario not in R.SCENARI_MEDIA:
        raise ValueError("scenario %r non e' della modalita' (%s)" % (scenario, R.SCENARI_MEDIA))
    reg = Registratore(livelli, ogni_ms, ogni_ms_live)
    vero = R._Ponte._giro_del_book

    def _giro(self: Any, market: Any, market_book: Any, ms: int) -> None:
        vero(self, market, market_book, ms)
        reg.osserva(self.b, market, market_book, ms)

    R._Ponte._giro_del_book = _giro
    try:
        with _freni_da_banco():
            ref = R.certifica_scenario(str(event_id), data_dir=data_dir, scenario=scenario)
    finally:
        R._Ponte._giro_del_book = vero
    definizioni, ko = R.leggi_definizioni(R.percorso_raw(data_dir, str(event_id)))
    from datetime import datetime

    ko_ms = int(datetime.fromisoformat(str(ko).replace("Z", "+00:00")).timestamp() * 1000) \
        if ko else None
    control = R.control_della_ui(str(event_id), scenario)
    return {
        "versione": 1,
        "evento": str(event_id),
        "sintetica": str(event_id).startswith("_synth"),
        "scenario": scenario,
        "mercato": R.mercato_media(scenario),
        "ko_ms": ko_ms,
        "parametri": {k: v for k, v in control["params"].items() if str(k).startswith("media_")},
        "referto": {
            "violazioni": [[v.codice, v.dettaglio] for v in ref.violazioni][:50],
            "sollecitati_m": {k: v for k, v in ref.sollecitati.items() if k.startswith("M")},
            "note": list(ref.note),
            "ordini": ref.ordini_piazzati, "abbinati": ref.ordini_abbinati,
        },
        "fotogrammi": reg.fotogrammi,
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("evento")
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--scenario", default=R.SCENARIO_MEDIA_PAPER, choices=list(R.SCENARI_MEDIA))
    ap.add_argument("--livelli", type=int, default=10)
    ap.add_argument("--ogni-ms", type=int, default=1000)
    ap.add_argument("--ogni-ms-live", type=int, default=5000)
    ap.add_argument("--uscita", default=None)
    a = ap.parse_args(argv)
    from ...backtest import registro_bot as REG

    data_dir = a.data_dir or REG.bot("scalper_calcio").cartella()
    tr = esporta(a.evento, data_dir=data_dir, scenario=a.scenario, livelli=a.livelli,
                 ogni_ms=a.ogni_ms, ogni_ms_live=a.ogni_ms_live)
    uscita = a.uscita or "traccia_media_under_%s.json.gz" % a.evento
    with gzip.open(uscita, "wt", encoding="utf-8") as fh:
        json.dump(tr, fh, separators=(",", ":"))
    print("%s: %d fotogrammi, %d violazioni, %d byte"
          % (uscita, len(tr["fotogrammi"]), len(tr["referto"]["violazioni"]),
             os.path.getsize(uscita)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
