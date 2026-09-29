"""uscite_proposte - IL CANCELLO DELLE USCITE dei bot di flusso (tennis, scalper).

Ordine dell'utente (28/09/2026, testuale): "TUTTI I BOT DEVONO AVERE LA
POSSIBILITA' DI USCITE MANUALI, OVVERO APPROVATE DA ME, OPPURE, TOTALMENTE
AUTOMATICHE! [...] OGNI BOT, PER ORA, DEVE PASSARE DA ME, IO APPROVO LE USCITE".

Stesso schema di Mike (``Betfair/mike/engine.gate_uscite``), senza macchine nuove:
  * la STRATEGIA decide come sempre QUANDO uscire (target, stop, time-stop,
    uscita strutturale, scratch, timeout): nessuna soglia cambia;
  * uscite AUTOMATICHE -> l'uscita parte come prima;
  * uscite MANUALI -> non parte niente: nasce una PROPOSTA con i numeri (cosa
    chiude, a che prezzo, quanto incassa o perde se chiude ora) che il bot tiene
    in ``stats['uscite_proposte']`` (il battito la scrive gia' sulla riga di
    controllo: nessuna scrittura in piu');
  * l'utente APPROVA dalla Control Room: la RPC scrive la firma
    ``{chiave: istante}`` sulla colonna ``uscite_approvate`` della riga di
    controllo; il servizio la passa al bot (``approva``) e l'uscita parte la
    PROSSIMA volta che la strategia la decide ANCORA, sul mercato di adesso
    (stessa chiave, entro ``TTL_APPROVAZIONE_S``, lo stesso tempo di Mike);
  * una proposta la cui condizione non vale piu' SPARISCE (``conferma_vive``):
    la scheda non mostra mai un'uscita che la strategia non vuole piu'.
Le PROTEZIONI (freno/force-flat, fine finestra, tetti di perdita, "Chiudi"
dell'utente) non passano di qui: le chiama il bot come sempre.

Modulo PURO: niente I/O, niente flumine. File ASCII-only.
"""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional

#: per quanto una firma resta valida se la strategia non ridecide quell'uscita
#: (stesso valore di ``mike.engine.APPROVAZIONE_TTL_S``: nessuna soglia nuova)
TTL_APPROVAZIONE_S = 120.0

#: chiave in ``stats`` (il battito del bot) con le proposte vive
CHIAVE_STATS = "uscite_proposte"

#: chiave in ``params`` della riga di controllo (``scalper_control``,
#: ``tennis_bot_control``) dove la RPC di approvazione scrive le firme
CHIAVE_FIRME = "uscite_approvate"


def applica_firme(strategie: Iterable[Any], params: Any) -> int:
    """Le firme appena rilette dalla riga di controllo, passate ai bot VIVI
    (quelli che hanno ``cancello_uscite``). Params non letti: niente cambia.
    Ritorna a quanti bot sono state passate."""
    if not isinstance(params, dict):
        return 0
    firme = params.get(CHIAVE_FIRME)
    n = 0
    for s in strategie:
        canc = getattr(s, "cancello_uscite", None)
        if isinstance(canc, CancelloUscite):
            canc.approva(firme)
            n += 1
    return n


def _secondi(v: Any) -> Optional[float]:
    """Istante della firma: epoch in secondi o ISO (quello che scrive la RPC)."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        s = str(v).strip().replace("Z", "+00:00")
        return datetime.fromisoformat(s).timestamp()
    except (TypeError, ValueError):
        return None


def ora_s(publish_time_ms: Any) -> float:
    """L'istante del bot in secondi: il tempo del MERCATO (``publish_time``),
    altrimenti l'orologio del processo."""
    try:
        if publish_time_ms is not None:
            return float(publish_time_ms) / 1000.0
    except (TypeError, ValueError):
        pass
    import time as _t
    return _t.time()


def proposta_di(*, bot: str, motivo: str, market_id: Any, selection_id: Any,
                lato_ingresso: Any, prezzo: Any, lato_chiusura: Any = None,
                size_chiusura: Any = None, se_chiudi: Any = None,
                se_vince: Any = None, se_perde: Any = None,
                **extra: Any) -> Dict[str, Any]:
    """I NUMERI che la scheda mostra, con le stesse chiavi per ogni bot:
    cosa chiude (mercato, selezione, lato e size della chiusura), a che
    prezzo, quanto incassa o perde se chiude ORA (``se_chiudi``, spalmato sulle
    due selezioni) e cosa succede se TIENE (``se_vince``/``se_perde``)."""
    def r(v: Any, n: int = 2) -> Any:
        try:
            return None if v is None else round(float(v), n)
        except (TypeError, ValueError):
            return None
    out = {"bot": str(bot), "motivo": str(motivo),
           "urgente": str(motivo) in MOTIVI_IN_PERDITA,
           "market_id": None if market_id is None else str(market_id),
           "selection_id": selection_id, "lato_ingresso": lato_ingresso,
           "prezzo": r(prezzo), "lato_chiusura": lato_chiusura,
           "size_chiusura": r(size_chiusura), "se_chiudi": r(se_chiudi, 3),
           "se_vince": r(se_vince, 3), "se_perde": r(se_perde, 3)}
    out.update(extra)
    return out


#: motivi d'uscita che di solito chiudono in PERDITA (la scheda li marca urgenti)
MOTIVI_IN_PERDITA = ("stop", "time", "strutturale", "timeout")

#: chiave della proposta quando i numeri NON si possono calcolare (nessun
#: prezzo di chiusura mai visto): dichiarata, con il motivo
CHIAVE_NUMERI_NON_DISPONIBILI = "numeri_non_disponibili"
#: eta' (secondi di mercato) del prezzo di chiusura usato per i numeri
CHIAVE_ETA_PREZZO = "prezzo_eta_s"


class UltimiPrezzi:
    """29/09 (CANTIERE N, UM2 del replay): l'ultimo prezzo di CHIUSURA visto per
    (mercato, selezione, lato del book). Serve SOLO ai numeri della proposta:
    quando nel book di adesso manca il lato di chiusura, la proposta usa
    l'ultimo prezzo visto e ne dichiara l'eta' (``prezzo_eta_s``); se non e'
    mai stato visto lo dichiara (``numeri_non_disponibili``). L'uscita, se
    parte, parte col SUO calcolo di sempre sul mercato di adesso: nessuna
    soglia e nessun prezzo d'ordine passano di qui."""

    def __init__(self) -> None:
        self._p: Dict[Any, Any] = {}

    def annota(self, chiave: Any, prezzo: Any, now_ms: Any) -> None:
        try:
            px = float(prezzo)
            t = float(now_ms)
        except (TypeError, ValueError):
            return
        if px > 1.0:
            self._p[chiave] = (px, t)

    def per_proposta(self, chiave: Any, prezzo_vivo: Any,
                     now_ms: Any) -> "tuple[Optional[float], Dict[str, Any]]":
        """(prezzo per i numeri, chiavi da aggiungere alla proposta)."""
        try:
            vivo = float(prezzo_vivo) if prezzo_vivo is not None else None
        except (TypeError, ValueError):
            vivo = None
        if vivo is not None and vivo > 1.0:
            self.annota(chiave, vivo, now_ms)
            return vivo, {}          # prezzo vivo: nessuna chiave in piu'
        visto = self._p.get(chiave)
        if visto is not None:
            try:
                eta = max(0.0, (float(now_ms) - visto[1]) / 1000.0)
            except (TypeError, ValueError):
                eta = None
            return visto[0], {CHIAVE_ETA_PREZZO: None if eta is None else round(eta, 1)}
        return None, {CHIAVE_NUMERI_NON_DISPONIBILI: (
            "nel book manca il prezzo di chiusura (lato %s) e non e' mai stato "
            "visto per questa selezione" % (chiave[-1] if isinstance(chiave, tuple)
                                           else chiave))}


class CancelloUscite:
    """Le proposte vive e le firme di UN bot (una istanza per strategia).

    REGOLA DELLA FIRMA (29/09, verifica del coordinatore): una firma vale per la
    proposta che l'utente ha VISTO, e per nessun'altra:
      * ``approva`` accetta una firma SOLO se in quel momento esiste la proposta
        con quella chiave e la firma e' successiva alla sua nascita
        (``decided_at``); altrimenti la firma e' scartata (e segnata come usata,
        cosi' rileggere la riga di controllo non la rimette);
      * se la proposta DECADE (``conferma_vive``, ``tieni_solo``,
        ``chiudi_posizione``) la firma cade con lei: quando la condizione torna
        nasce una proposta NUOVA (``decided_at`` nuovo) e va firmata di nuovo.
    Thread: ``approva`` arriva dal battito, il resto dal thread del mercato. Tutto
    passa da un lock: nessuna iterazione su un dizionario che cambia.
    """

    def __init__(self, emetti: Optional[Callable[..., Any]] = None) -> None:
        self._emetti = emetti
        self._lock = threading.RLock()
        self.proposte: Dict[str, Dict[str, Any]] = {}
        self.approvate: Dict[str, float] = {}
        # firme gia' usate o scartate (una firma vale UNA uscita: rileggere la
        # stessa riga di controllo al battito dopo non deve farla ripartire)
        self._consumate: Dict[str, float] = {}

    # ------------------------------------------------------------- le firme
    def approva(self, firme: Any) -> None:
        """Le firme lette dalla riga di controllo (``uscite_approvate``):
        ``{chiave: istante}``. Tutto cio' che non e' un dizionario si ignora
        (colonna assente = migrazione non applicata = nessuna firma)."""
        if not isinstance(firme, dict):
            return
        with self._lock:
            for chiave, quando in list(firme.items()):
                t = _secondi(quando)
                if t is None or not chiave:
                    continue
                k = str(chiave)
                if self._consumate.get(k) == t or self.approvate.get(k) == t:
                    continue
                viva = self.proposte.get(k)
                nata = _secondi((viva or {}).get("decided_at"))
                if viva is None or (nata is not None and t < nata):
                    # firma senza la sua proposta (decaduta, o data a una
                    # proposta precedente con la stessa chiave): non vale
                    self._consumate[k] = t
                    continue
                self.approvate[k] = t

    # ------------------------------------------------------ il cancello vero
    def lascia_uscire(self, *, automatiche: bool, chiave: str, now_s: float,
                      proposta: Dict[str, Any]) -> bool:
        """True = l'uscita decisa dalla strategia PARTE adesso.

        ``proposta``: i numeri che l'utente vede (motivo, lato, prezzo, size,
        bloccabile, ...). A uscite manuali, senza firma valida, si registra la
        proposta (una attivita' ``uscita_proposta`` alla nascita, mai a ogni
        book) e si ritorna False."""
        with self._lock:
            if automatiche:
                self.proposte.pop(chiave, None)
                self.approvate.pop(chiave, None)
                return True
            firma = self.approvate.get(chiave)
            if firma is not None and now_s - firma <= TTL_APPROVAZIONE_S:
                self.approvate.pop(chiave, None)
                self._consumate[chiave] = firma
                viva = self.proposte.pop(chiave, None)
                self._emit("uscita_eseguita_su_approvazione", chiave=chiave,
                           approvata_at=firma, motivo=(proposta or {}).get("motivo"),
                           decisa_at=(viva or {}).get("decided_at"))
                return True
            if firma is not None:
                # firma scaduta: si firma di nuovo sul presente (come Mike)
                self.approvate.pop(chiave, None)
                self._consumate[chiave] = firma
            prima = self.proposte.get(chiave)
            corpo = {k: v for k, v in (proposta or {}).items()}
            corpo["chiave"] = chiave
            corpo["decided_at"] = (prima or {}).get("decided_at") or now_s
            corpo["proposed_at"] = now_s
            self.proposte[chiave] = corpo
            if prima is None:
                self._emit("uscita_proposta", **{k: v for k, v in corpo.items()
                                                 if k not in ("proposed_at",)})
            return False

    def _togli(self, k: str) -> None:
        """Proposta e firma se ne vanno INSIEME (lock gia' preso)."""
        self.proposte.pop(k, None)
        firma = self.approvate.pop(k, None)
        if firma is not None:
            self._consumate[k] = firma

    def conferma_vive(self, prefisso: str, vive: Iterable[str]) -> None:
        """Le proposte di QUESTA posizione (``prefisso``) la cui condizione non e'
        piu' vera in questo giro decadono, e con loro le firme (la scheda non
        mostra un'uscita che la strategia non vuole piu', e una firma data a
        quella proposta non vale per la prossima)."""
        tenere = set(vive)
        with self._lock:
            chiavi = set(self.proposte) | set(self.approvate)
            for k in [k for k in chiavi if k.startswith(prefisso) and k not in tenere]:
                c_era = k in self.proposte
                self._togli(k)
                if c_era:
                    self._emit("uscita_proposta_decaduta", chiave=k,
                               motivo="la condizione di uscita non vale piu'")

    def chiudi_posizione(self, prefisso: str) -> None:
        """Posizione chiusa (da un'uscita, dal "Chiudi", da una protezione): le
        sue proposte e firme non servono piu'."""
        with self._lock:
            for k in [k for k in set(self.proposte) | set(self.approvate)
                      if k.startswith(prefisso)]:
                self._togli(k)

    def tieni_solo(self, prefissi: Iterable[str]) -> None:
        """Solo le proposte delle posizioni ancora aperte restano (una
        posizione chiusa da una protezione o dal "Chiudi" porta via le sue)."""
        pref = tuple(prefissi)
        with self._lock:
            for k in [k for k in set(self.proposte) | set(self.approvate)
                      if not (pref and k.startswith(pref))]:
                self._togli(k)

    def firmata(self, chiave: str) -> bool:
        """C'e' una firma valida (non ancora usata) per questa chiave?"""
        with self._lock:
            return chiave in self.approvate

    def vive(self) -> List[Dict[str, Any]]:
        """Le proposte vive, pronte per ``stats`` (ordinate per nascita)."""
        with self._lock:
            copie = [dict(p) for p in list(self.proposte.values())]
        return sorted(copie, key=lambda p: float(p.get("decided_at") or 0.0))

    # ------------------------------------------------------------- interni
    def _emit(self, ev: str, **p: Any) -> None:
        if self._emetti is None:
            return
        try:
            self._emetti(ev, p)
        except Exception:  # noqa: BLE001 - un log non ferma mai un'uscita
            pass
