"""IL CONGELAMENTO dei riferimenti (T0C, 09/10/2026; H par. 4.4, 05 T0C).

    python -m Betfair.stream.backtest.certifica <bot> <evento> --scenari S --cassetta giro1.jsonl
    python -m Betfair.stream.backtest.certifica <bot> <evento> --scenari S --ombra giro1.jsonl --congela
    python -m Betfair.stream.backtest.certifica --verifica-congelati
    python -m Betfair.stream.backtest.congela aggiungi --tipo registrazione --comando "..." <file> ...
    python -m Betfair.stream.backtest.congela verifica [--congelati DIR]

Il MANIFESTO (``ARCHITETTURA_2026-10/riferimenti_congelati/MANIFEST.json``) e'
SOLO AGGIUNTA: per ogni voce percorso, byte, sha256, tipo, comando esatto,
commit, versioni; le voci sono incatenate (``catena`` = sha256 della voce
precedente e di questa), cosi' una voce vecchia ritoccata a mano si scopre.
``--verifica-congelati`` ricalcola tutto e fallisce se una voce e' cambiata,
manca, o la catena non torna.

Si congela una baseline SOLO se la seconda esecuzione dello stesso comando ha
0 divergenze in ombra contro la prima (determinismo, H par. 6 passo 4): il
flag ``--congela`` lo pretende.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: la cartella dei riferimenti congelati (relativa alla radice del repository)
CARTELLA_DEFAULT = os.path.join("ARCHITETTURA_2026-10", "riferimenti_congelati")
MANIFESTO = "MANIFEST.json"
VERSIONE_MANIFESTO = 1

#: i flag che NON fanno parte del comando di riferimento (dicono dove scrivere
#: la cassetta, contro che cosa confrontarla, se congelarla)
FLAG_DELLA_CASSETTA_CON_VALORE = ("--cassetta", "--ombra", "--congelati")
FLAG_DELLA_CASSETTA_SECCHI = ("--congela", "--verifica-congelati")


class CongelamentoRifiutato(Exception):
    """Il manifesto e' SOLO AGGIUNTA: nessuna voce si riscrive."""


def radice_repo() -> str:
    """La radice del repository (questo file sta in ``Betfair/stream/backtest``)."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def sha256_file(percorso: str) -> Tuple[int, str]:
    h = hashlib.sha256()
    n = 0
    with open(percorso, "rb") as fh:
        for blocco in iter(lambda: fh.read(1 << 20), b""):
            h.update(blocco)
            n += len(blocco)
    return n, h.hexdigest()


def _git(*args: str) -> Optional[str]:
    try:
        out = subprocess.run(["git", *args], cwd=radice_repo(), capture_output=True,
                             text=True, timeout=30, check=False)
    except Exception:  # noqa: BLE001 - git assente: il manifesto lo dice
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def commit_corrente() -> Dict[str, Any]:
    """Il commit di HEAD e se l'albero di ``Betfair/`` ha modifiche non
    committate (un riferimento prodotto da un albero sporco non e' rifacibile)."""
    sporco = _git("status", "--porcelain", "--untracked-files=no", "--", "Betfair")
    return {"commit": _git("rev-parse", "HEAD"), "sporco": bool(sporco)}


def impronta_banco() -> Dict[str, Any]:
    """sha256 dei sorgenti del banco (``Betfair/stream/backtest/*.py``, nome e
    contenuto, in ordine): cambia se cambia il metro."""
    cartella = os.path.dirname(os.path.abspath(__file__))
    h = hashlib.sha256()
    n = 0
    for nome in sorted(os.listdir(cartella)):
        if not nome.endswith(".py"):
            continue
        h.update(nome.encode("ascii", errors="replace") + b"\0")
        with open(os.path.join(cartella, nome), "rb") as fh:
            h.update(fh.read())
        n += 1
    return {"sha256": h.hexdigest(), "file": n}


def versioni_complete() -> Dict[str, Any]:
    """Python, flumine, betfairlightweight, l'impronta di ``pip freeze`` (dalle
    distribuzioni installate) e di ``requirements.txt``."""
    out: Dict[str, Any] = {"python": sys.version.split()[0]}
    try:
        import betfairlightweight
        import flumine

        out["flumine"] = str(getattr(flumine, "__version__", "?"))
        out["betfairlightweight"] = str(getattr(betfairlightweight, "__version__", "?"))
    except Exception as ex:  # noqa: BLE001
        out["flumine"] = "non importabile: %s" % str(ex)[:60]
    try:
        from importlib import metadata

        righe = sorted("%s==%s" % (d.metadata["Name"], d.version)
                       for d in metadata.distributions() if d.metadata["Name"])
        out["pip_freeze_sha256"] = hashlib.sha256("\n".join(righe).encode("utf-8")).hexdigest()
        out["pip_freeze_voci"] = len(righe)
    except Exception as ex:  # noqa: BLE001
        out["pip_freeze_sha256"] = "non calcolabile: %s" % str(ex)[:60]
    req = os.path.join(radice_repo(), "requirements.txt")
    if os.path.isfile(req):
        out["requirements_sha256"] = sha256_file(req)[1]
    return out


def argomenti_del_comando(argv: Sequence[str]) -> List[str]:
    """Il comando senza i flag della cassetta (la cassetta osserva, non cambia
    il replay: due giri con file di cassetta diversi sono lo STESSO comando)."""
    out: List[str] = []
    salta = False
    for x in argv:
        if salta:
            salta = False
            continue
        if x in FLAG_DELLA_CASSETTA_CON_VALORE:
            salta = True
            continue
        if any(x.startswith(f + "=") for f in FLAG_DELLA_CASSETTA_CON_VALORE):
            continue
        if x in FLAG_DELLA_CASSETTA_SECCHI:
            continue
        out.append(str(x))
    return out


def comando_esatto(argv: Sequence[str]) -> str:
    return "python -m Betfair.stream.backtest.certifica " + " ".join(argomenti_del_comando(argv))


# ---------------------------------------------------------------------------
# il manifesto
# ---------------------------------------------------------------------------
def cartella_assoluta(cartella: Optional[str]) -> str:
    c = cartella or CARTELLA_DEFAULT
    return c if os.path.isabs(c) else os.path.join(radice_repo(), c)


def _canonico(x: Any) -> str:
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _anello(precedente: str, voce: Dict[str, Any]) -> str:
    senza = {k: v for k, v in voce.items() if k != "catena"}
    return hashlib.sha256((precedente + _canonico(senza)).encode("ascii")).hexdigest()


def leggi_manifesto(cartella: Optional[str]) -> Dict[str, Any]:
    p = os.path.join(cartella_assoluta(cartella), MANIFESTO)
    if not os.path.isfile(p):
        return {"versione": VERSIONE_MANIFESTO, "voci": []}
    with open(p, encoding="ascii") as fh:
        return json.load(fh)


def _percorso_relativo(assoluto: str) -> str:
    """Relativo alla radice se ci sta dentro (con ``/``), altrimenti assoluto."""
    rad = radice_repo()
    a = os.path.abspath(assoluto)
    if os.path.commonpath([rad, a]) == rad:
        return os.path.relpath(a, rad).replace(os.sep, "/")
    return a


def _assoluto(percorso: str) -> str:
    return percorso if os.path.isabs(percorso) else os.path.join(radice_repo(), percorso)


def voce_file(percorso: str, *, tipo: str, comando: str,
              extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    n, sha = sha256_file(percorso)
    voce: Dict[str, Any] = {
        "percorso": _percorso_relativo(percorso), "byte": n, "sha256": sha, "tipo": tipo,
        "comando": comando, "commit": commit_corrente(), "versioni": versioni_complete(),
        "banco": impronta_banco(),
        "data": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if extra:
        voce.update(extra)
    return voce


def aggiungi_voci(cartella: Optional[str], nuove: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Aggiunge in coda (SOLO AGGIUNTA). Una voce con lo stesso percorso e lo
    stesso sha256 non si ripete; con sha256 diverso e' RIFIUTATA. Prima di
    scrivere si verifica la catena delle voci esistenti."""
    dove = cartella_assoluta(cartella)
    man = leggi_manifesto(cartella)
    voci: List[Dict[str, Any]] = list(man.get("voci") or [])
    rotte = verifica_catena(voci)
    if rotte:
        raise CongelamentoRifiutato("catena del manifesto rotta (%s): niente si aggiunge "
                                    "a un manifesto ritoccato" % "; ".join(rotte))
    per_percorso = {v["percorso"]: v for v in voci}
    aggiunte: List[Dict[str, Any]] = []
    for v in nuove:
        gia = per_percorso.get(v["percorso"])
        if gia is not None:
            if gia["sha256"] == v["sha256"]:
                continue
            raise CongelamentoRifiutato("%s e' gia' nel manifesto con sha256 %s (nuovo %s): "
                                        "il manifesto e' solo aggiunta"
                                        % (v["percorso"], gia["sha256"], v["sha256"]))
        precedente = voci[-1]["catena"] if voci else ""
        v = dict(v)
        v["catena"] = _anello(precedente, v)
        voci.append(v)
        per_percorso[v["percorso"]] = v
        aggiunte.append(v)
    if aggiunte:
        os.makedirs(dove, exist_ok=True)
        man = {"versione": VERSIONE_MANIFESTO, "voci": voci}
        tmp = os.path.join(dove, MANIFESTO + ".tmp")
        with open(tmp, "w", encoding="ascii", newline="\n") as fh:
            json.dump(man, fh, indent=1, sort_keys=True, ensure_ascii=True)
            fh.write("\n")
        os.replace(tmp, os.path.join(dove, MANIFESTO))
    return aggiunte


def verifica_catena(voci: Sequence[Dict[str, Any]]) -> List[str]:
    rotte: List[str] = []
    precedente = ""
    for i, v in enumerate(voci):
        atteso = _anello(precedente, v)
        if v.get("catena") != atteso:
            rotte.append("voce %d (%s)" % (i, v.get("percorso")))
        precedente = str(v.get("catena") or "")
    return rotte


def verifica(cartella: Optional[str]) -> List[Tuple[str, bool, str]]:
    """Ogni voce: ``(percorso, ok, motivo)``. Ricalcola byte e sha256 e la catena."""
    man = leggi_manifesto(cartella)
    voci = list(man.get("voci") or [])
    out: List[Tuple[str, bool, str]] = []
    rotte = set(verifica_catena(voci))
    for i, v in enumerate(voci):
        p = _assoluto(str(v.get("percorso")))
        etichetta = "voce %d (%s)" % (i, v.get("percorso"))
        if etichetta in rotte:
            out.append((str(v.get("percorso")), False, "catena rotta: voce ritoccata"))
            continue
        if not os.path.isfile(p):
            out.append((str(v.get("percorso")), False, "file assente"))
            continue
        n, sha = sha256_file(p)
        if sha != v.get("sha256") or n != v.get("byte"):
            out.append((str(v.get("percorso")), False, "cambiato: %d byte sha256 %s (atteso %s "
                        "byte sha256 %s)" % (n, sha, v.get("byte"), v.get("sha256"))))
            continue
        out.append((str(v.get("percorso")), True, "ok"))
    return out


def verifica_e_stampa(cartella: Optional[str]) -> int:
    dove = os.path.join(cartella_assoluta(cartella), MANIFESTO)
    esiti = verifica(cartella)
    print("VERIFICA DEI RIFERIMENTI CONGELATI: %s (%d voci)" % (dove, len(esiti)))
    if not os.path.isfile(dove):
        print("!! manifesto assente")
        return 1
    for percorso, ok, motivo in esiti:
        print("  %s %s%s" % ("OK" if ok else "KO", percorso, "" if ok else " | " + motivo))
    ko = sum(1 for _p, ok, _m in esiti if not ok)
    print("ESITO: %d voci integre, %d cambiate o assenti" % (len(esiti) - ko, ko))
    return 1 if ko else 0


# ---------------------------------------------------------------------------
# il congelamento di un giro di certifica
# ---------------------------------------------------------------------------
def nome_del_giro(argv: Sequence[str], bot: str) -> str:
    """Un nome di file leggibile e stabile per il comando (senza i flag della
    cassetta)."""
    argomenti = argomenti_del_comando(argv)
    testo = "_".join(argomenti) or bot
    pulito = re.sub(r"[^A-Za-z0-9_.,=-]+", "-", testo).strip("-")
    return pulito[:120]


def congela_giro(*, cartella: Optional[str], bot: str, argv: Sequence[str], cassetta: str,
                 testo_referto: str, riferimento_determinismo: str) -> List[Dict[str, Any]]:
    """Copia la cassetta e il referto nella cartella dei riferimenti e li
    aggiunge al manifesto. Mai sopra un file esistente."""
    from . import cassetta as CAS

    dove = cartella_assoluta(cartella)
    nome = nome_del_giro(argv, bot)
    # la cassetta congelata e' SEMPRE compressa e deterministica (``.jsonl.gz``,
    # gzip senza data): stesso contenuto, stessi byte
    dest_c = os.path.join(dove, "cassette", nome + ".jsonl.gz")
    dest_r = os.path.join(dove, "referti", nome + ".txt")
    for p in (dest_c, dest_r):
        if os.path.exists(p):
            raise CongelamentoRifiutato("%s esiste gia': il congelamento e' solo aggiunta"
                                        % _percorso_relativo(p))
    os.makedirs(os.path.dirname(dest_c), exist_ok=True)
    os.makedirs(os.path.dirname(dest_r), exist_ok=True)
    CAS.scrivi(dest_c, CAS.leggi(cassetta))
    with open(dest_r, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(testo_referto)
    comando = comando_esatto(argv)
    det = {"determinismo": {"primo_giro_sha256": sha256_file(riferimento_determinismo)[1],
                            "divergenze": 0}}
    voci = [voce_file(dest_c, tipo="cassetta", comando=comando, extra=det),
            voce_file(dest_r, tipo="referto", comando=comando, extra=det)]
    return aggiungi_voci(cartella, voci)


# ---------------------------------------------------------------------------
# riga di comando (registrazioni, software, verifica)
# ---------------------------------------------------------------------------
def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Riferimenti congelati del banco (solo aggiunta)")
    sub = p.add_subparsers(dest="cosa", required=True)
    ag = sub.add_parser("aggiungi", help="aggiunge file al manifesto (registrazioni, software)")
    ag.add_argument("file", nargs="+")
    ag.add_argument("--tipo", required=True,
                    help="registrazione | software | referto_storico | cassetta | altro")
    ag.add_argument("--comando", default="", help="il comando che ha prodotto il file, se c'e'")
    ag.add_argument("--congelati", default=None)
    ve = sub.add_parser("verifica", help="ricalcola gli hash del manifesto")
    ve.add_argument("--congelati", default=None)
    a = p.parse_args(argv)
    if a.cosa == "verifica":
        return verifica_e_stampa(a.congelati)
    voci = [voce_file(os.path.abspath(f), tipo=a.tipo, comando=a.comando) for f in a.file]
    try:
        aggiunte = aggiungi_voci(a.congelati, voci)
    except CongelamentoRifiutato as ex:
        print("!! RIFIUTATO: %s" % ex)
        return 1
    for v in aggiunte:
        print("CONGELATO: %s | %d byte | sha256 %s" % (v["percorso"], v["byte"], v["sha256"]))
    print("voci aggiunte: %d (gia' presenti e identiche: %d)" % (len(aggiunte),
                                                                 len(voci) - len(aggiunte)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
