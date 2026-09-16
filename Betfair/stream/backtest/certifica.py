"""CERTIFICA — il punto d'ingresso UNICO per certificare un bot sul banco.

    python -m Betfair.stream.backtest.certifica <bot> [event_id ...]
    python -m Betfair.stream.backtest.certifica mike --complete --diario diario.txt
    python -m Betfair.stream.backtest.certifica mike --scenari tutti
    python -m Betfair.stream.backtest.certifica --elenco

Un solo comando per TUTTI i bot: chi ci sia, che cosa gli serve e come lo si fa
rivivere lo dice il REGISTRO (`registro_bot.py`). Il replay passa dal BANCO
COMUNE (`banco_comune.py`), cioe' dal codice di PRODUZIONE del bot applicato
alle partite registrate: stream registrato -> scanner vero -> riga di scan vera
-> feed vero -> servizio vero -> ordini veri su flumine, col matching e il bet
delay di flumine.

Il referto NON misura il profitto: misura la CONDOTTA. Per ogni controllo dice
anche quante volte ha avuto un caso da giudicare, perche' «zero violazioni» su
un controllo mai sollecitato non vuol dire «sano», vuol dire «non lo so».

Questo file e' l'UNICA implementazione del referto: `Betfair/mike/tools/
replay_registrazioni.py` conserva soltanto i pezzi SPECIFICI di Mike (la
strategia flumine, gli scenari) e il suo `main()` chiama questo.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

from . import registro_bot as REG

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# le registrazioni
# ---------------------------------------------------------------------------
def eventi_disponibili(data_dir: str) -> List[str]:
    """Le cartelle `<data_dir>/<event_id>/<event_id>.raw.jsonl`.
    Le `_synth_*` (registrazioni sintetiche) restano fuori: un banco che
    certifica su dati inventati non certifica niente."""
    out: List[str] = []
    if not os.path.isdir(data_dir):
        return out
    for nome in sorted(os.listdir(data_dir)):
        if nome.startswith("_"):
            continue
        if os.path.exists(os.path.join(data_dir, nome, f"{nome}.raw.jsonl")):
            out.append(nome)
    return out


def verdetti_registrazioni(data_dir: str, eventi: List[str]) -> Dict[str, str]:
    """Verdetto di `validate_recordings` per ogni evento (COMPLETE / PARTIAL /
    ...): una registrazione monca fa mentire il replay e il referto lo dichiara.

    ⚠️ 16/09 — la versione precedente di questa funzione (dentro il replay di
    Mike) chiamava `validate_all(eventi, data_dir=…)`, ma la firma vera e'
    `validate_all(data_dir, *, min_coverage_pct=…)`: usciva un `TypeError` che
    il broad except ingoiava, il dizionario tornava vuoto e `--complete` NON
    FILTRAVA NULLA. Qui si passa da `validate_event`, uno per uno.
    """
    try:
        from ..tools.validate_recordings import validate_event
    except Exception as ex:  # noqa: BLE001 - il verdetto e' un di piu', non un gate
        logger.warning("validate_recordings non importabile: %s", ex)
        return {}
    out: Dict[str, str] = {}
    for ev in eventi:
        try:
            rep = validate_event(data_dir, str(ev))
        except Exception as ex:  # noqa: BLE001 - un evento illeggibile non ferma il giro
            logger.warning("validate_recordings su %s KO: %s", ev, str(ex)[:120])
            continue
        out[str(ev)] = str(getattr(rep, "verdict", None) or "?")
    return out


# ---------------------------------------------------------------------------
# riproducibilita' (PROCESSO_STANDARD_BOT §6.8)
# ---------------------------------------------------------------------------
def impronta(scheda: "REG.BotRegistrato") -> Dict[str, str]:
    """Versioni e IMPRONTA DEL CODICE del bot: un referto che non si puo' rifare
    identico non e' un referto, e' un ricordo.

    L'impronta e' lo sha1 dei sorgenti dei moduli di produzione del bot piu' del
    suo modulo di controlli: se domani il referto non torna, si sa subito se e'
    cambiato il bot, il metro, o i dati.
    """
    import hashlib

    fuori: Dict[str, str] = {}
    try:
        import betfairlightweight
        import flumine

        fuori["flumine"] = str(getattr(flumine, "__version__", "?"))
        fuori["betfairlightweight"] = str(getattr(betfairlightweight, "__version__", "?"))
    except Exception as ex:  # noqa: BLE001
        fuori["flumine"] = f"non importabile: {str(ex)[:60]}"
    h = hashlib.sha1()  # noqa: S324 — impronta di identita', non firma
    contati = 0
    for nome in list(scheda.moduli_produzione) + [scheda.controlli or ""]:
        if not nome:
            continue
        percorso = os.path.join(*nome.split(".")) + ".py"
        if not os.path.isfile(percorso):
            continue
        with open(percorso, "rb") as fh:
            h.update(fh.read())
        contati += 1
    fuori["codice_bot"] = f"{h.hexdigest()[:12]} ({contati} file)" if contati else "ignoto"
    return fuori


# ---------------------------------------------------------------------------
# PIU' PROCESSI — un processo per coppia evento x scenario
# ---------------------------------------------------------------------------
# La simulazione e' CPU-bound e il GIL rende i thread inutili (lo dice anche la
# doc di flumine). Gli eventi sono INDIPENDENTI fra loro — ognuno e' un file
# raw e un servizio che nasce e muore — e `flumine.config` e' di PROCESSO:
# separarli in processi non e' solo piu' veloce, e' anche piu' ISOLATO di come
# girano oggi in serie nello stesso interprete.
#
# Il referto NON cambia: i risultati si raccolgono e si stampano nell'ORDINE
# CANONICO (per scenario, poi per evento) che avevano prima, e il `--diario`
# resta una riga per evento nello stesso ordine.
def _lavora(compito: tuple) -> Any:
    """UN replay, in un processo suo. Deve stare a livello di modulo per essere
    inviabile a un processo figlio (su Windows la pool usa `spawn`)."""
    bot, ev, data_dir, scenario, ogni_ms, campioni_diff = compito
    scheda = REG.bot(str(bot))
    certifica_evento = scheda.funzione_replay()
    CERT = scheda.modulo_controlli()
    try:
        r = certifica_evento(ev, data_dir=data_dir, scenario=scenario,
                             ogni_ms=ogni_ms, campioni_diff=campioni_diff)
    except Exception as ex:  # noqa: BLE001 — un replay che esplode E' un referto
        r = CERT.Referto(event_id=ev)
        r.note.append(f"replay fallito: {type(ex).__name__}: {ex}")
    # la memoria viaggia A PARTE, non dentro il referto: il referto deve restare
    # IDENTICO a quello in serie, e il picco di un processo cambia da giro a giro
    return r, picco_memoria_mb()


def picco_memoria_mb() -> float:
    """Il PICCO di memoria del processo corrente, in MB.

    Serve a dire quante partite reggono davvero in parallelo: ogni worker e' un
    processo intero e `_read_loop` tiene TUTTO il file raw in RAM
    (`historicalstream.py:267-268`), piu' le cache dei mercati, piu' le righe
    del database in memoria che crescono per tutta la partita. Su Windows il
    picco lo tiene il sistema (`peak_wset`): un campionamento a mano lo
    mancherebbe."""
    try:
        import psutil

        info = psutil.Process().memory_info()
        picco = getattr(info, "peak_wset", None) or getattr(info, "rss", 0)
        return round(float(picco) / (1024.0 * 1024.0), 1)
    except Exception:  # noqa: BLE001 - la memoria e' una diagnostica, non un gate
        return 0.0


def _prepara_figlio() -> None:
    """Lo stesso livello di log del padre: un figlio piu' chiacchierone
    cambierebbe i tempi e sporcherebbe il referto."""
    logging.basicConfig(level=logging.WARNING)


WORKER_DEFAULT = 3


def core_fisici() -> int:
    """I core VERI, non i thread. Su questa macchina (Ryzen 7 3750H) sono 4 e i
    thread 8: dimensionare sui thread vorrebbe dire mettere due replay CPU-bound
    sullo stesso core e non guadagnare niente, pagando pero' la RAM di due
    processi. Senza `psutil` si stima meta' dei logici (SMT)."""
    try:
        import psutil

        n = psutil.cpu_count(logical=False)
        if n:
            return int(n)
    except Exception:  # noqa: BLE001 - psutil e' un di piu'
        pass
    return max(1, (os.cpu_count() or 2) // 2)


def quanti_processi(richiesti: int, compiti: int) -> int:
    """Quanti worker usare davvero. 0 = il default (3), MAI oltre `core - 1`.

    Il tetto e' `core_fisici() - 1` e non e' negoziabile nemmeno se lo si chiede
    piu' alto: il replay e' CPU-bound, un core va lasciato alla macchina, e due
    worker sullo stesso core fisico non guadagnano niente.

    LA MEMORIA NON E' IL LIMITE, MISURATA (16/09, Ryzen 7 3750H, 15,8 GB):
    ogni worker e' un processo intero e `_read_loop` tiene TUTTO il file raw in
    RAM (`historicalstream.py:267-268`), ma il picco resta modesto — 151 MB
    sulla registrazione da 7 MB, **176 MB su quella da 25 MB** (la piu' grossa
    del corpus), contro ~141 MB di soli import. Con 7 GB liberi ne
    starebbero decine: a fermare la pool sono i core, non i giga. Il referto
    stampa comunque il picco per worker misurato nel giro corrente, perche' un
    numero dichiarato e non misurato non vale.

    ⚠️ DENTRO LA SUITE L'AUTOMATICO E' SPENTO. Su Windows la pool usa `spawn`:
    il figlio RI-IMPORTA il `__main__` del padre, e sotto `pytest` quel
    `__main__` e' pytest stesso — il figlio rilancerebbe la suite. La
    certificazione nella suite (`pytest -m cert`) e' un campione corto e non ha
    bisogno di worker; chi li vuole lo stesso li chiede a mano con `--worker N`.
    """
    if compiti <= 1:
        return 1
    tetto = max(1, core_fisici() - 1)
    if richiesti and int(richiesti) > 0:
        return max(1, min(int(richiesti), tetto, compiti))
    if "pytest" in sys.modules:
        return 1
    return max(1, min(WORKER_DEFAULT, tetto, compiti))


def _esegui_compiti(compiti: List[tuple], processi: int, picchi: List[float]):
    """Esegue i compiti e li restituisce NELL'ORDINE IN CUI SONO STATI DATI.

    Con un processo solo si resta in casa (nessun costo di avvio, ed e' il caso
    del singolo evento). Con piu' processi si sottomette tutto subito e si
    raccoglie nell'ordine canonico: cosi' la stampa e il diario escono come
    prima, in ordine, e restano osservabili mentre il lavoro procede.
    """
    if processi <= 1:
        for c in compiti:
            yield _lavora(c)[0]
        return
    from concurrent.futures import ProcessPoolExecutor

    with ProcessPoolExecutor(max_workers=processi,
                             initializer=_prepara_figlio) as pool:
        futuri = [pool.submit(_lavora, c) for c in compiti]
        for f in futuri:
            referto, memoria = f.result()
            if memoria:
                picchi.append(memoria)
            yield referto


# ---------------------------------------------------------------------------
# il referto
# ---------------------------------------------------------------------------
def _stampa_elenco() -> int:
    print("BOT REGISTRATI — chi opera in produzione e come si certifica")
    print()
    for b in REG.elenco():
        segno = "OK" if b.certificabile else "??"
        print(f"  {segno} {b.nome:<16} {b.sport:<7} {b.descrizione}")
        print(f"       moduli    : {', '.join(b.moduli_produzione) or '-'}")
        print(f"       mercati   : {', '.join(b.mercati) or '-'}")
        print(f"       spec      : {b.spec or '-'}")
        print(f"       replay    : {b.replay or 'ASSENTE'}")
        print(f"       controlli : {b.controlli or 'ASSENTI'}")
        if not b.certificabile:
            print(f"       ?? NON CERTIFICATO: {b.motivo_senza_controlli}")
    mancanti = REG.senza_certificazione()
    print()
    print(f"CERTIFICABILI: {len(REG.elenco()) - len(mancanti)} su {len(REG.elenco())}. "
          f"Sugli altri il banco non dice «sano», dice «non lo so».")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Certificazione di un bot sulle registrazioni reali (banco comune)")
    p.add_argument("bot", nargs="?", help="nome del bot registrato (vedi --elenco)")
    p.add_argument("eventi", nargs="*", help="event_id (vuoto = tutti)")
    p.add_argument("--elenco", action="store_true", help="elenca i bot registrati e esce")
    p.add_argument("--data-dir", default=None)
    p.add_argument("--ogni-ms", type=int, default=0,
                   help="cadenza di decisione in ms. 0 (default) = LA CADENZA DEL "
                        "SERVIZIO, letta dai suoi parametri di produzione: il bot "
                        "nel replay deve girare ne' piu' ne' meno di quanto gira "
                        "in live, altrimenti vede piu' (o meno) di quello che "
                        "vedrebbe")
    p.add_argument("--complete", action="store_true",
                   help="solo le registrazioni giudicate COMPLETE")
    p.add_argument("--json", dest="come_json", action="store_true")
    p.add_argument("--scenari", default="base",
                   help="elenco separato da virgole, oppure 'tutti'")
    p.add_argument("--diff", type=int, default=0, metavar="N",
                   help="confronta il payload SCRITTO A MANO con quello dello "
                        "SCANNER VERO sui primi N giri utili di ogni partita")
    p.add_argument("--worker", type=int, default=0,
                   help="quanti worker: 0 (default) = 3, un processo per coppia "
                        "evento x scenario, MAI oltre core_fisici-1 (qui 3: la "
                        "macchina ha 4 core e ogni worker tiene la sua "
                        "registrazione in RAM). 1 = tutto nello stesso "
                        "processo, come prima. Il referto e il diario NON "
                        "cambiano: stesso ordine, stessi numeri")
    p.add_argument("--diario", default=None,
                   help="file in cui scrivere il referto DOPO OGNI partita: senza, "
                        "un run lungo resta cieco fino alla fine")
    a = p.parse_args(argv)

    logging.basicConfig(level=logging.WARNING)
    if a.elenco or not a.bot:
        return _stampa_elenco()

    try:
        scheda = REG.bot(a.bot)
    except KeyError as ex:
        print(str(ex))
        return 2
    if not scheda.replay:
        print(f"IL BOT '{scheda.nome}' NON HA ANCORA UN REPLAY SUL BANCO.")
        print(f"  motivo: {scheda.motivo_senza_controlli or 'non dichiarato'}")
        print("  il banco comune c'e' (Betfair/stream/backtest/banco_comune.py): "
              "manca l'aggancio del suo servizio. Vedi MODELLO_BOT_NUOVO.md.")
        return 2
    # si risolve QUI, nel padre: se il replay del bot non e' importabile lo si
    # deve sapere subito, non dentro N processi figli. Il replay poi lo esegue
    # `_lavora`, che lo ri-risolve nel SUO processo.
    scheda.funzione_replay()
    CERT = scheda.modulo_controlli()
    if CERT is None:
        print(f"IL BOT '{scheda.nome}' NON HA CONTROLLI DI CONDOTTA: "
              f"{scheda.motivo_senza_controlli or 'motivo non dichiarato'}")
        return 2

    data_dir = a.data_dir or scheda.cartella()
    eventi = a.eventi or eventi_disponibili(data_dir)
    verdetti = verdetti_registrazioni(data_dir, eventi)
    if a.complete and verdetti:
        eventi = [e for e in eventi if verdetti.get(e) == "COMPLETE"]

    noti = scheda.elenco_scenari()
    scelti = (list(noti) if a.scenari.strip().lower() == "tutti"
              else [x.strip() for x in a.scenari.split(",") if x.strip()])
    for sc in scelti:
        if sc not in noti:
            print(f"scenario sconosciuto per {scheda.nome}: {sc} "
                  f"(noti: {', '.join(noti)})")
            return 2

    imp = impronta(scheda)
    print(f"BOT: {scheda.nome} | spec: {scheda.spec or '-'} | "
          f"registrazioni: {len(eventi)} in {data_dir}")
    print(f"controlli attivi: {len(CERT.elenco_controlli())} | "
          f"flumine {imp.get('flumine')} | "
          f"betfairlightweight {imp.get('betfairlightweight')} | "
          f"codice bot {imp.get('codice_bot')}")
    print(f"comando: python -m Betfair.stream.backtest.certifica {scheda.nome} "
          + " ".join(a.eventi) + (" --complete" if a.complete else "")
          + f" --scenari {a.scenari}"
          + (f" --ogni-ms {a.ogni_ms}" if a.ogni_ms else ""))
    qualita: Dict[str, int] = {}
    for e in eventi:
        v = verdetti.get(e, "?")
        qualita[v] = qualita.get(v, 0) + 1
    if qualita:
        print("qualita' delle registrazioni: "
              + ", ".join(f"{k} x{n}" for k, n in sorted(qualita.items())))
    if len(scelti) > 1:
        print(f"SCENARI: {', '.join(scelti)}")
        # LA REGOLA DEL TEMPO, dichiarata dove serve: qui si confrontano scenari.
        print("        i numeri di scenari diversi sono confrontabili SOLO dove "
              "la sequenza di chiamate e' identica fino al punto confrontato: "
              "ogni chiamata bloccante consuma tempo di mercato (in produzione "
              "come nel replay) e sposta il book su cui abbina tutto cio' che "
              "viene dopo")
    print()

    sollecitati_tot: Dict[str, int] = {}
    referti: List[Any] = []
    # L'ORDINE CANONICO: per scenario, poi per evento. E' quello di prima, ed e'
    # quello in cui il referto e il diario devono uscire, qualunque sia il
    # numero di processi.
    compiti = [(scheda.nome, ev, data_dir, sc, a.ogni_ms, int(a.diff or 0))
               for sc in scelti for ev in eventi]
    processi = quanti_processi(int(a.worker or 0), len(compiti))
    if processi > 1:
        print(f"worker: {processi} su {core_fisici()} core fisici (un processo "
              f"per coppia evento x scenario, {len(compiti)} coppie; il referto "
              f"resta nello stesso ordine)")
        print()
    picchi: List[float] = []
    risultati = _esegui_compiti(compiti, processi, picchi)
    for sc in scelti:
        for ev in eventi:
            r = next(risultati)
            if len(scelti) > 1:
                r.event_id = f"{ev} [{sc}]"
            referti.append(r)
            for cod, n in r.sollecitati.items():
                sollecitati_tot[cod] = sollecitati_tot.get(cod, 0) + n
            if a.diario:
                # si scrive SUBITO, partita per partita: un run da ore che non
                # dice niente finche' non finisce non e' osservabile, e un lavoro
                # non osservabile non si sa nemmeno se sta andando bene.
                with io.open(a.diario, "a", encoding="utf-8") as f:
                    f.write(f"{'OK' if r.pulita else 'KO'} {ev} tick={r.tick} "
                            f"decisioni={r.decisioni} azioni={r.azioni} "
                            f"ordini={r.ordini_piazzati} "
                            f"stati={','.join(r.stati_visti)}" + chr(10))
                    for v in r.violazioni[:6]:
                        f.write(f"    {v.codice}: {v.dettaglio}" + chr(10))
                    f.flush()
            segno = "OK " if r.pulita else "KO "
            print(f"{segno} {r.event_id}  tick={r.tick:>6} decisioni={r.decisioni:>5} "
                  f"azioni={r.azioni:>4} stati={','.join(r.stati_visti) or '-'} "
                  f"[{verdetti.get(ev, '?')}]")
            for nota in r.note:
                print(f"      nota: {nota}")
            for motivo, n in sorted(r.motivi.items(), key=lambda x: -x[1])[:6]:
                print(f"      motivo x{n}: {motivo}")
            for cod, n in sorted(r.per_codice().items()):
                esempio = next(v for v in r.violazioni if v.codice == cod)
                print(f"      {cod} x{n}: {esempio.regola}")
                print(f"           es. {esempio.dettaglio}")

    if picchi:
        # QUANTE PARTITE IN PARALLELO REGGONO: la memoria e' il limite vero, non
        # il processore. Ogni worker tiene in RAM il file raw intero
        # (`_read_loop` fa `readlines()`), le cache dei mercati e le righe del
        # database in memoria.
        piu_grosso = max(picchi)
        try:
            import psutil

            libera = psutil.virtual_memory().available / (1024.0 * 1024.0)
        except Exception:  # noqa: BLE001
            libera = 0.0
        quante = int(libera // piu_grosso) if piu_grosso > 0 and libera else 0
        print()
        print(f"MEMORIA: picco per worker {min(picchi):.0f}-{piu_grosso:.0f} MB "
              f"(media {sum(picchi) / len(picchi):.0f} MB su {len(picchi)} repliche)"
              + (f" | RAM libera adesso {libera:.0f} MB -> {quante} worker "
                 f"reggerebbero senza swap, tetto di processo {max(1, core_fisici() - 1)}"
                 if libera else ""))
    print()
    tot = sum(len(r.violazioni) for r in referti)
    pulite = sum(1 for r in referti if r.pulita and r.decisioni > 0)
    mute = sum(1 for r in referti if r.decisioni == 0)
    print(f"ESITO: {pulite} partite senza violazioni, "
          f"{len(referti) - pulite - mute} con violazioni, {mute} senza decisioni")
    print(f"       {tot} violazioni totali")
    print()
    print("COPERTURA DEI CONTROLLI — quante volte ognuno ha avuto un caso:")
    for cod, reg in CERT.elenco_controlli():
        n = sollecitati_tot.get(cod, 0)
        segno = "  " if n else "??"
        print(f"  {segno} {cod:3} x{n:<7} {reg[:66]}")
    mai = CERT.mai_sollecitati(sollecitati_tot)
    if mai:
        print()
        print(f"?? MAI SOLLECITATI: {len(mai)} controlli su "
              f"{len(CERT.elenco_controlli())}. Su questi il referto NON dice "
              f"«sano», dice «non lo so»:")
        for cod, reg in mai:
            print(f"     {cod}: {reg}")
    if a.come_json:
        print(json.dumps([{
            "event_id": r.event_id, "tick": r.tick, "decisioni": r.decisioni,
            "azioni": r.azioni, "stati": r.stati_visti, "note": r.note,
            "violazioni": [v.__dict__ for v in r.violazioni],
        } for r in referti], indent=1, default=str))
    return 0 if tot == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
