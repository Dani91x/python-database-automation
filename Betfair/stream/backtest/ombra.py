"""L'OMBRA del banco (T0C, 09/10/2026; H par. 4.3): due cassette a confronto.

    python -m Betfair.stream.backtest.ombra <cassetta_riferimento> <cassetta_nuova>
    python -m Betfair.stream.backtest.certifica <bot> <evento> --ombra <cassetta>

Il confronto e' "nuovo di oggi contro cassetta congelata", a costo di UN
replay. TOLLERANZE: ZERO, salvo le TRE normalizzazioni decise dall'utente
(U-59) e scritte, col motivo e il test che le falsifica, in
``ARCHITETTURA_2026-10/riferimenti_congelati/TOLLERANZE.md``:

  1. TEMPI: le righe dei tempi del referto (``certifica.PREFISSI_RIGHE_TEMPI``:
     ``tempo:`` con i tick/s, ``TEMPO TOTALE:``, ``LENTO:``) e la riga del picco
     di memoria (``MEMORIA:``);
  2. HASH DEL CODICE: l'impronta del codice del bot nel referto (``codice bot
     <hash> (<n> file)``) e, nella testata, ``commit``/``codice_bot``/``banco``:
     cambiano per definizione; il confronto li esclude e li STAMPA;
  3. ID D'OROLOGIO: gli identificatori che flumine deriva dall'orologio della
     macchina (``order.id`` = ``uuid1().time``, ``trade.id`` = ``uuid4``) nei
     campi di ``CAMPI_ID_OROLOGIO``: si sostituiscono con un ORDINALE per prima
     comparsa (stessa struttura, valori diversi = uguali; due ordini che si
     scambiano o condividono un id = divergenza), e lo stesso ordinale li
     sostituisce dove ricompaiono dentro altre stringhe. ``bet_id`` e i ``ref``
     del bot NON si normalizzano.

Qualunque altra differenza e' una ``Divergenza(livello, ms, chiave, vecchio,
nuovo, regola)``; ``certifica`` esce con codice != 0.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import argparse
import dataclasses
import difflib
import io
import json
import os
import re
import sys
import tempfile
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import cassetta as CAS

# ---------------------------------------------------------------------------
# le TRE tolleranze (U-59): le sole
# ---------------------------------------------------------------------------
#: (1) le righe del referto che cambiano fra due giri identici: i tempi (stessi
#: prefissi di ``certifica.PREFISSI_RIGHE_TEMPI``) e il picco di memoria
PREFISSI_RIGHE_TEMPI: Tuple[str, ...] = ("tempo:", "TEMPO TOTALE:", "LENTO:", "MEMORIA:")

#: (2) l'impronta del codice nel testo del referto e i campi della testata
RE_CODICE_BOT = re.compile(r"codice bot [0-9a-f]{6,64} \(\d+ file\)")
SEGNAPOSTO_CODICE_BOT = "codice bot <impronta esclusa: tolleranza 2>"
CAMPI_TESTATA_CODICE: Tuple[str, ...] = ("commit", "codice_bot", "banco")

#: (3) i campi che portano un identificatore derivato dall'orologio di macchina
#: (``flumine/order/order.py:78`` ``uuid1().time``; ``flumine/order/trade.py:41``
#: ``uuid4``), come li scrive la cassetta e come li scrive lo specchio
#: (``varianti_bot.campi_ordine``) e il registro dei fill attraversati
#: (``banco_comune.MotoreReplay._mercato_che_attraversa``: voce ``ordine``)
#: Si aggiungono, uno per uno e con la riga che li scrive, i campi che la prova
#: di DETERMINISMO (stesso comando due volte) ha trovato scritti con l'orologio
#: della macchina dal codice di produzione (TOLLERANZE.md, tabella 3):
#: ``settled_at``/``pnl_betfair_settled_at`` (``mike/service.py:6707,6723,6849``,
#: ``now_iso = _now().isoformat()`` a :6768), ``letto_at`` (:6892, :6899),
#: ``last_loss_exit_deciso_ts`` (``_time.time()`` a :5739: REPERTO T0C-R1);
#: ``started_at``/``stopped_at``/``heartbeat_at`` dello scalper
#: (``scalper/scalper_session.py:304`` ``_now_iso`` = ``datetime.now``, scritti a
#: :220, :255, :1517, :1524, :2209, :2393, :2424). Il ``pid`` del processo
#: (``scalper_session.py:1590``) NON e' un orologio: non si normalizza (REPERTO
#: T0C-R2).
CAMPI_ID_OROLOGIO: Tuple[str, ...] = ("ordine_id", "trade_id", "_ordine", "_trade_id",
                                      "_sostituisce", "settled_at", "pnl_betfair_settled_at",
                                      "letto_at", "last_loss_exit_deciso_ts", "started_at",
                                      "stopped_at", "heartbeat_at")
#: dentro le voci ``_fill_attraversato`` dello specchio l'id dell'ordine sta in ``ordine``
CAMPI_ID_OROLOGIO_ANNIDATI: Tuple[Tuple[str, str], ...] = (("_fill_attraversato", "ordine"),)

LIVELLI: Tuple[str, ...] = CAS.KINDS


@dataclasses.dataclass(frozen=True)
class Divergenza:
    """Una differenza fra le due cassette che nessuna tolleranza copre."""
    livello: str
    ms: int
    chiave: str
    vecchio: Any
    nuovo: Any
    regola: str


# ---------------------------------------------------------------------------
# normalizzazione
# ---------------------------------------------------------------------------
def _riga_dei_tempi(testo: str) -> bool:
    return str(testo).lstrip().startswith(PREFISSI_RIGHE_TEMPI)


def _raccogli_id(x: Any, trovati: List[str], visti: set) -> None:
    """Gli id d'orologio in ordine di comparsa (visita in profondita', chiavi
    ordinate: la forma canonica e' gia' ordinata)."""
    if isinstance(x, dict):
        for k in sorted(x):
            v = x[k]
            if k in CAMPI_ID_OROLOGIO and isinstance(v, (str, int, float)) \
                    and not isinstance(v, bool) and v != "" and str(v) not in visti:
                visti.add(str(v))
                trovati.append(str(v))
            for padre, figlio in CAMPI_ID_OROLOGIO_ANNIDATI:
                if k == padre and isinstance(v, list):
                    for e in v:
                        if isinstance(e, dict) and isinstance(e.get(figlio), (str, int)) \
                                and str(e[figlio]) not in visti:
                            visti.add(str(e[figlio]))
                            trovati.append(str(e[figlio]))
            _raccogli_id(v, trovati, visti)
    elif isinstance(x, list):
        for v in x:
            _raccogli_id(v, trovati, visti)


class _Sostituto:
    """id d'orologio -> ``#id<ordinale>``, anche dentro altre stringhe."""

    def __init__(self, ids: Sequence[str]) -> None:
        self.mappa = {v: "#id%d" % (i + 1) for i, v in enumerate(ids)}
        lunghi = sorted((v for v in ids if len(v) >= 8), key=len, reverse=True)
        self._re = re.compile("|".join(re.escape(v) for v in lunghi)) if lunghi else None
        self._minimo = min((len(v) for v in lunghi), default=0)

    def stringa(self, s: str) -> str:
        if s in self.mappa:
            return self.mappa[s]
        if self._re is not None and len(s) >= self._minimo:
            return self._re.sub(lambda m: self.mappa[m.group(0)], s)
        return s

    def valore(self, x: Any, chiave: Optional[str] = None) -> Any:
        if isinstance(x, dict):
            return {k: self.valore(v, k) for k, v in x.items()}
        if isinstance(x, list):
            return [self.valore(v) for v in x]
        if isinstance(x, str):
            return self.stringa(x)
        if isinstance(x, (int, float)) and not isinstance(x, bool) \
                and chiave in CAMPI_ID_OROLOGIO and str(x) in self.mappa:
            return self.mappa[str(x)]
        return x


def normalizza(righe: Sequence[str]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Le voci della cassetta dopo le TRE tolleranze (e senza il sigillo, che si
    verifica a parte). Torna ``(voci, escluso)``: ``escluso`` e' cio' che la
    tolleranza 2 ha tolto (si stampa)."""
    voci = []
    for r in righe:
        if not r:
            continue
        try:
            voci.append(json.loads(r))
        except ValueError:
            # una riga rotta (byte cambiato, gzip illeggibile) e' una voce che
            # diverge, non un'eccezione: il sigillo la dichiara gia'
            voci.append({"kind": "referto", "ms": 0, "chiave": "riga illeggibile",
                         "dati": {"riga": r[:200]}})
    if voci and voci[-1].get("chiave") == CAS.CHIAVE_SIGILLO:
        voci = voci[:-1]
    escluso: Dict[str, Any] = {}
    ids: List[str] = []
    visti: set = set()
    out: List[Dict[str, Any]] = []
    for v in voci:
        _raccogli_id(v.get("dati"), ids, visti)
    sost = _Sostituto(ids)
    for v in voci:
        dati = v.get("dati")
        if v.get("chiave") == CAS.CHIAVE_TESTATA and isinstance(dati, dict):
            dati = dict(dati)
            for k in CAMPI_TESTATA_CODICE:
                if k in dati:
                    escluso[k] = dati.pop(k)
        if v.get("chiave") == CAS.CHIAVE_TESTO and isinstance(dati, dict):
            testo = str(dati.get("riga", ""))
            if _riga_dei_tempi(testo):                      # tolleranza 1
                continue
            m = RE_CODICE_BOT.search(testo)
            if m:                                           # tolleranza 2
                escluso.setdefault("codice_bot_referto", m.group(0))
                testo = RE_CODICE_BOT.sub(SEGNAPOSTO_CODICE_BOT, testo)
            dati = {"riga": testo}
        if v.get("kind") == "referto" and v.get("chiave", "").endswith("|esito") \
                and isinstance(dati, dict):
            note = dati.get("note")
            if isinstance(note, list):
                dati = dict(dati, note=[RE_CODICE_BOT.sub(SEGNAPOSTO_CODICE_BOT, str(n))
                                        for n in note])
        out.append({"kind": v.get("kind"), "ms": v.get("ms"),
                    "chiave": sost.stringa(str(v.get("chiave", ""))),
                    "dati": sost.valore(dati)})
    return out, escluso


# ---------------------------------------------------------------------------
# il confronto
# ---------------------------------------------------------------------------
def _flusso(voce: Dict[str, Any]) -> Tuple[str, str]:
    chiave = str(voce.get("chiave", ""))
    compito = chiave.split("|", 1)[0] if "|" in chiave else ""
    return compito, str(voce.get("kind"))


def _piatto(x: Any, prefisso: str = "") -> Dict[str, Any]:
    if isinstance(x, dict):
        out: Dict[str, Any] = {}
        for k, v in x.items():
            out.update(_piatto(v, "%s.%s" % (prefisso, k) if prefisso else str(k)))
        if not x:
            out[prefisso] = {}
        return out
    if isinstance(x, list):
        out = {}
        for i, v in enumerate(x):
            out.update(_piatto(v, "%s[%d]" % (prefisso, i)))
        if not x:
            out[prefisso] = []
        return out
    return {prefisso: x}


def _differenze_campo(a: Dict[str, Any], b: Dict[str, Any], quanti: int = 6) -> str:
    pa, pb = _piatto(a), _piatto(b)
    diversi = [k for k in sorted(set(pa) | set(pb)) if pa.get(k, "<assente>") != pb.get(k, "<assente>")]
    parti = ["%s: %s -> %s" % (k, json.dumps(pa.get(k, "<assente>"))[:80],
                                json.dumps(pb.get(k, "<assente>"))[:80]) for k in diversi[:quanti]]
    if len(diversi) > quanti:
        parti.append("... (%d campi diversi)" % len(diversi))
    return "; ".join(parti)


def _canon(v: Dict[str, Any]) -> str:
    return CAS.canonica(v)


def confronta_voci(vecchie: Sequence[Dict[str, Any]],
                   nuove: Sequence[Dict[str, Any]]) -> List[Divergenza]:
    """Le divergenze fra due sequenze di voci GIA' normalizzate, flusso per
    flusso (compito x livello), nell'ordine in cui le voci sono state scritte."""
    per_v: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    per_n: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    ordine: List[Tuple[str, str]] = []
    for sorgente, dest in ((vecchie, per_v), (nuove, per_n)):
        for v in sorgente:
            k = _flusso(v)
            if k not in per_v and k not in per_n:
                ordine.append(k)
            dest.setdefault(k, []).append(v)
    out: List[Divergenza] = []
    for k in ordine:
        a = per_v.get(k, [])
        b = per_n.get(k, [])
        ca = [_canon(x) for x in a]
        cb = [_canon(x) for x in b]
        if ca == cb:
            continue
        # prefisso e suffisso comuni: il confronto fine solo dove serve
        i = 0
        while i < len(ca) and i < len(cb) and ca[i] == cb[i]:
            i += 1
        j = 0
        while j < len(ca) - i and j < len(cb) - i and ca[-1 - j] == cb[-1 - j]:
            j += 1
        sa, sb = ca[i:len(ca) - j], cb[i:len(cb) - j]
        va, vb = a[i:len(a) - j], b[i:len(b) - j]
        sm = difflib.SequenceMatcher(None, sa, sb, autojunk=False)
        livello = k[1]
        for op, a0, a1, b0, b1 in sm.get_opcodes():
            if op == "equal":
                continue
            n = max(a1 - a0, b1 - b0)
            for t in range(n):
                x = va[a0 + t] if a0 + t < a1 else None
                y = vb[b0 + t] if b0 + t < b1 else None
                if x is not None and y is not None:
                    regola = "valore diverso: " + _differenze_campo(x, y)
                elif x is None:
                    regola = "voce in piu' nel nuovo"
                else:
                    regola = "voce mancante nel nuovo"
                rif = y if y is not None else x
                out.append(Divergenza(livello=livello, ms=int((rif or {}).get("ms") or 0),
                                      chiave=str((rif or {}).get("chiave", "")),
                                      vecchio=x, nuovo=y, regola=regola))
    return out


@dataclasses.dataclass
class Esito:
    divergenze: List[Divergenza]
    sigillo_riferimento: Optional[str]
    sigillo_nuova: Optional[str]
    escluso_vecchio: Dict[str, Any]
    escluso_nuovo: Dict[str, Any]
    voci_vecchie: int
    voci_nuove: int

    @property
    def pulito(self) -> bool:
        return not self.divergenze and self.sigillo_riferimento is None \
            and self.sigillo_nuova is None


def confronta_righe(riferimento: Sequence[str], nuova: Sequence[str]) -> Esito:
    s_rif = CAS.verifica_sigillo(riferimento)
    s_nuo = CAS.verifica_sigillo(nuova)
    vv, ev = normalizza(riferimento)
    vn, en = normalizza(nuova)
    return Esito(divergenze=confronta_voci(vv, vn), sigillo_riferimento=s_rif,
                 sigillo_nuova=s_nuo, escluso_vecchio=ev, escluso_nuovo=en,
                 voci_vecchie=len(vv), voci_nuove=len(vn))


def confronta_file(riferimento: str, nuova: str) -> Esito:
    return confronta_righe(CAS.leggi(riferimento), CAS.leggi(nuova))


def descrivi(es: Esito, massimo: int = 30) -> List[str]:
    """Le righe del rapporto d'ombra."""
    righe: List[str] = []
    if es.sigillo_riferimento:
        righe.append("!! SIGILLO DEL RIFERIMENTO ROTTO: %s" % es.sigillo_riferimento)
    if es.sigillo_nuova:
        righe.append("!! SIGILLO DELLA CASSETTA NUOVA ROTTO: %s" % es.sigillo_nuova)
    per_livello: Dict[str, int] = {}
    for d in es.divergenze:
        per_livello[d.livello] = per_livello.get(d.livello, 0) + 1
    righe.append("OMBRA: %d divergenze su %d/%d voci (riferimento/nuova) | per livello: %s"
                 % (len(es.divergenze), es.voci_vecchie, es.voci_nuove,
                    ", ".join("%s %d" % (k, per_livello.get(k, 0)) for k in LIVELLI)))
    escl = sorted(set(es.escluso_vecchio) | set(es.escluso_nuovo))
    if escl:
        righe.append("  escluso dal confronto (tolleranza 2, si stampa): "
                     + "; ".join("%s %s -> %s" % (k, es.escluso_vecchio.get(k, "-"),
                                                  es.escluso_nuovo.get(k, "-")) for k in escl))
    for d in es.divergenze[:massimo]:
        righe.append("  DIVERGENZA [%s] ms=%d %s | %s" % (d.livello, d.ms, d.chiave[:90],
                                                          d.regola[:400]))
    if len(es.divergenze) > massimo:
        righe.append("  ... e altre %d" % (len(es.divergenze) - massimo))
    righe.append("OMBRA: " + ("0 divergenze, sigilli integri" if es.pulito
                              else "DIVERGENTE (exit code != 0)"))
    return righe


# ---------------------------------------------------------------------------
# certifica con la cassetta (``--cassetta``, ``--ombra``, ``--congela``)
# ---------------------------------------------------------------------------
class _Tee:
    """Scrive a schermo E in memoria: il testo del referto entra nella cassetta.
    Il resto (``encoding``, ``isatty``...) e' quello dello schermo."""

    def __init__(self, a: Any) -> None:
        self.a = a
        self.b = io.StringIO()

    def write(self, s: str) -> int:
        self.a.write(s)
        self.b.write(s)
        return len(s)

    def flush(self) -> None:
        self.a.flush()

    def __getattr__(self, nome: str) -> Any:
        return getattr(self.a, nome)


def _versioni() -> Dict[str, str]:
    out = {"python": sys.version.split()[0]}
    try:
        import betfairlightweight
        import flumine

        out["flumine"] = str(getattr(flumine, "__version__", "?"))
        out["betfairlightweight"] = str(getattr(betfairlightweight, "__version__", "?"))
    except Exception as ex:  # noqa: BLE001
        out["flumine"] = "non importabile: %s" % str(ex)[:60]
    return out


#: exit code di ``certifica`` quando il replay e' pulito ma l'ombra diverge
EXIT_OMBRA = 3


def certifica_con_cassetta(a: Any, esegui: Callable[[Any], int],
                           argv: Optional[Sequence[str]]) -> int:
    """Esegue ``certifica`` (``esegui(a)``, IL percorso di sempre) con la
    cassetta accesa, la scrive, e poi l'ombra e/o il congelamento."""
    from . import certifica as CERTIFICA
    from . import congela as CON
    from . import registro_bot as REG

    if a.congela and not a.ombra:
        print("--congela vuole la prova di DETERMINISMO: prima un giro con "
              "--cassetta <file>, poi lo STESSO comando con --congela --ombra <file> "
              "(si congela solo a 0 divergenze; H par. 6 passo 4)")
        return 2
    riferimento: Optional[List[str]] = None
    if a.ombra:
        if not os.path.isfile(a.ombra):
            print("--ombra: cassetta di riferimento assente: %s" % a.ombra)
            return 2
        riferimento = CAS.leggi(a.ombra)
    argv_l = list(sys.argv[1:] if argv is None else argv)
    with tempfile.TemporaryDirectory(prefix="cassetta_") as segmenti:
        prima = os.environ.get(CAS.ENV_DIR)
        os.environ[CAS.ENV_DIR] = segmenti
        tee = _Tee(sys.stdout)
        vecchio_out = sys.stdout
        sys.stdout = tee
        try:
            rc = esegui(a)
        finally:
            sys.stdout = vecchio_out
            if prima is None:
                os.environ.pop(CAS.ENV_DIR, None)
            else:
                os.environ[CAS.ENV_DIR] = prima
        try:
            scheda = REG.bot(a.bot)
            codice = CERTIFICA.impronta(scheda).get("codice_bot")
        except Exception:  # noqa: BLE001 - bot ignoto: lo ha gia' detto certifica
            codice = None
        testata = {
            "bot": a.bot, "eventi": list(a.eventi or []), "scenari": a.scenari,
            "trasporto": a.trasporto, "ogni_ms": a.ogni_ms, "worker": a.worker,
            "complete": bool(a.complete),
            "argomenti": [x for x in CON.argomenti_del_comando(argv_l)],
            "versioni": _versioni(), "exit_code_certifica": rc,
            # tolleranza 2: si scrivono, il confronto li esclude e li stampa
            "commit": CON.commit_corrente(), "codice_bot": codice,
            "banco": CON.impronta_banco(),
        }
        testo_referto = tee.b.getvalue()
        righe = CAS.assembla(segmenti, testata, testo_referto)
    percorso = a.cassetta
    temporanea = None
    if not percorso:
        temporanea = tempfile.NamedTemporaryFile(prefix="cassetta_", suffix=".jsonl",
                                                 delete=False)
        temporanea.close()
        percorso = temporanea.name
    sha = CAS.scrivi(percorso, righe)
    conta: Dict[str, int] = {}
    for r in righe:
        k = json.loads(r)["kind"]
        conta[k] = conta.get(k, 0) + 1
    print()
    print("CASSETTA: %s | sha256 %s | %d voci (%s)" % (
        percorso, sha, len(righe), ", ".join("%s %d" % (k, conta.get(k, 0)) for k in LIVELLI)))
    esito_ombra: Optional[Esito] = None
    if riferimento is not None:
        esito_ombra = confronta_righe(riferimento, righe)
        print("OMBRA contro %s:" % a.ombra)
        for riga in descrivi(esito_ombra):
            print(riga)
        if not esito_ombra.pulito:
            rc = rc or EXIT_OMBRA
    if a.congela:
        if esito_ombra is None or not esito_ombra.pulito:
            print("!! CONGELAMENTO RIFIUTATO: l'ombra contro il primo giro non e' a 0 "
                  "divergenze (determinismo non provato): niente entra nel manifesto")
            return rc or EXIT_OMBRA
        try:
            voci = CON.congela_giro(cartella=a.congelati, bot=a.bot, argv=argv_l,
                                    cassetta=percorso, testo_referto=testo_referto,
                                    riferimento_determinismo=a.ombra)
        except CON.CongelamentoRifiutato as ex:
            print("!! CONGELAMENTO RIFIUTATO: %s" % ex)
            return rc or 2
        for v in voci:
            print("CONGELATO: %s | %d byte | sha256 %s" % (v["percorso"], v["byte"], v["sha256"]))
    return rc


# ---------------------------------------------------------------------------
# riga di comando: due cassette a confronto
# ---------------------------------------------------------------------------
def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Ombra: confronta due cassette del banco")
    p.add_argument("riferimento")
    p.add_argument("nuova")
    p.add_argument("--massimo", type=int, default=30, help="divergenze stampate")
    a = p.parse_args(argv)
    es = confronta_file(a.riferimento, a.nuova)
    for riga in descrivi(es, a.massimo):
        print(riga)
    return 0 if es.pulito else 1


if __name__ == "__main__":
    sys.exit(main())
