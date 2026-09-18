"""Falsificazione dei test nuovi di F0 (misura) e F1 (canale dello scanner).

Un test che non sa diventare rosso non certifica. Questo strumento mette il
DIFETTO nel codice VERO, una mutazione alla volta, lancia i test indicati e
PRETENDE il rosso; poi ripristina il file e verifica l'md5 prima/dopo - un
ripristino sbagliato e' peggio del difetto che si stava cercando.

Uso (dalla radice del repo):
    .venv/Scripts/python.exe -m Betfair.safe_strategy.tools.falsifica_f0_f1_2026_09_18

Esce 0 se TUTTE le mutazioni sono state catturate, 1 se una e' passata liscia,
2 se un ripristino non ha rimesso il file com'era (in quel caso si ferma
subito: il file va rimesso a mano con git).
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Any, List, Tuple

RADICE = Path(__file__).resolve().parents[3]
PY = str(RADICE / ".venv" / "Scripts" / "python.exe")

SERVICE = "Betfair/safe_strategy/service.py"
SCANNER = "Betfair/safe_strategy/scanner.py"
CANALE = "Betfair/stream/local_channel.py"
OROLOGIO = "Betfair/stream/orologio.py"

T_NUOVO = "Betfair/safe_strategy/tests/test_canale_scanner_al_ms_2026_09_18.py"
T_INCIDENTE = "Betfair/safe_strategy/tests/test_incidente_quote_2026_09_17.py"
T_BANCO = "Betfair/stream/tests/test_banco_comune_2026_09_16.py"

#: (nome, file, testo VERO, testo MUTATO, test che devono diventare rossi).
#: Al posto della coppia (vero, mutato) si puo' mettere in ``vero`` una LISTA di
#: coppie, quando il difetto si riproduce solo toccando due punti insieme; in
#: quel caso ``mutato`` viene ignorato.
MUTAZIONI: List[Tuple[str, str, Any, Any, List[str]]] = [
    # ----------------------------------------------------------------- C2
    ("M1 guardia has_any_price TOLTA da _apply_market_book", SERVICE,
     """        if not scanner.has_any_price(pairs):
            # il blocco nasce UNA volta sola, perche' la riga dica onestamente
            # "quote assenti" - ma senza timestamp di prezzo
            ev.setdefault("odds", odds)
            ev["odds_vuote_ms"] = ora_ms
            self._segna_book_vuoto(meta["market_id"], dallo_stream)
            return
""",
     """        if False:
            ev.setdefault("odds", odds)
            ev["odds_vuote_ms"] = ora_ms
            self._segna_book_vuoto(meta["market_id"], dallo_stream)
            return
""",
     [T_NUOVO, T_INCIDENTE]),

    ("M2 odds_pt_ms SOPRA la guardia (l'incidente del 17/09 con un campo in piu')",
     SERVICE,
     """        bd = scanner.num_or_none(getattr(book, "bet_delay", None))
        if bd is not None:
            ev["bet_delay"] = int(bd)
        ora_ms = int(self._ora() * 1000)""",
     """        bd = scanner.num_or_none(getattr(book, "bet_delay", None))
        if bd is not None:
            ev["bet_delay"] = int(bd)
        ev["odds_pt_ms"] = scanner.publish_time_ms(book)
        ora_ms = int(self._ora() * 1000)""",
     [T_NUOVO]),

    ("M3 bet_delay SOTTO la guardia (un mercato di sole definizioni resta senza)",
     SERVICE,
     """        bd = scanner.num_or_none(getattr(book, "bet_delay", None))
        if bd is not None:
            ev["bet_delay"] = int(bd)
        ora_ms = int(self._ora() * 1000)""",
     """        ora_ms = int(self._ora() * 1000)""",
     [T_NUOVO]),

    ("M4 bet_delay assente diventa zero (int(bd or 0))", SERVICE,
     """        if bd is not None:
            ev["bet_delay"] = int(bd)""",
     """        ev["bet_delay"] = int(bd or 0)""",
     [T_NUOVO]),

    ("M5 odds_pt_ms fuori dal ramo del cambio di quota: campo VOLATILE nella firma",
     SERVICE,
     """            ev["odds_pt_ms"] = scanner.publish_time_ms(book)
        ev["odds"] = odds""",
     """            pass
        ev["odds_pt_ms"] = scanner.publish_time_ms(book)
        ev["odds"] = odds""",
     [T_NUOVO]),

    # ------------------------------------------------------- publish_time_ms
    ("M6 publish_time_ms torna 0 invece di None", SCANNER,
     """    if book is None:
        return None
    epoch = getattr(book, "publish_time_epoch", None)""",
     """    if book is None:
        return 0
    epoch = getattr(book, "publish_time_epoch", None)""",
     [T_NUOVO]),

    ("M7 publish_time_ms scambia un booleano per un istante", SCANNER,
     """    if isinstance(epoch, (int, float)) and not isinstance(epoch, bool):""",
     """    if isinstance(epoch, (int, float)):""",
     [T_NUOVO]),

    ("M8 publish_time_ms ignora publish_time_epoch", SCANNER,
     """    epoch = getattr(book, "publish_time_epoch", None)
    if isinstance(epoch, (int, float)) and not isinstance(epoch, bool):
        return int(epoch)""",
     """    epoch = None""",
     [T_NUOVO]),

    # ------------------------------------------------------------- orologio
    ("M9 orologio senza il flag impossibile", OROLOGIO,
     """    out["impossibile"] = float(riferimento) < 0.0
    return out""",
     """    return out""",
     [T_NUOVO]),

    ("M10 orologio non e' piu' un modulo puro (import flumine)", OROLOGIO,
     """import os
from datetime import datetime, timezone""",
     """import os
import flumine  # noqa: F401 - MUTAZIONE
from datetime import datetime, timezone""",
     [T_NUOVO]),

    # ------------------------------------------------------------------- D2
    ("M11 interruttore col verso di a321: variabile assente = ACCESO", SERVICE,
     """    return (os.getenv(_CANALE_ENV) or "").strip().lower() in _CANALE_VALORI_ACCESI""",
     """    return (os.getenv(_CANALE_ENV) or "").strip().lower() not in ("0", "false", "no")""",
     [T_NUOVO]),

    # L'interruttore letto PRIMA degli import di progetto, cioe' prima di
    # ``load_dotenv()``: e' il difetto che il test dell'Appendice H esiste per
    # catturare. (La prima versione di questa mutazione - rendere pigro il solo
    # import di ``auth`` - passava liscia, e il motivo e' un REPERTO: vedi il
    # checkpoint §8. Il `.env` arriva per DUE strade, non una.)
    ("M12 l'interruttore letto PRIMA di load_dotenv", SERVICE,
     [("""from Betfair.stream.auth import build_client, keep_alive, safe_logout""",
       """_ACCESO_PRECOCE = (os.getenv("SAFE_SCAN_CANALE") or "").strip().lower() in ("1", "true", "si", "yes")
from Betfair.stream.auth import build_client, keep_alive, safe_logout"""),
      ("""_CANALE_ACCESO = _letto_acceso()""",
       """_CANALE_ACCESO = _ACCESO_PRECOCE""")],
     None,                       # ignorato: le coppie stanno nel campo sopra
     [T_NUOVO]),

    # ------------------------------------------------------------------- D1
    ("M13 start_channel torna il canale vecchio su una porta diversa", CANALE,
     """        if int(port) != _CHANNEL.port:""",
     """        if False:""",
     [T_NUOVO]),

    # ------------------------------------------------------------------- D3
    # esattamente il codice di a321: si spinge PRIMA, e il blocco opportunita'
    # viene aggiunto allo stesso dizionario DOPO - troppo tardi, perche' il
    # canale ha gia' serializzato e spedito
    ("M14 push PRIMA del blocco opportunities (riga del canale monca, come a321)",
     SERVICE,
     """                if sport == "calcio" and _opportunities_enabled():
                    payload["opportunities"] = self.opportunities(payload)
                riga = {
                    "event_id": eid,
                    "sport": sport,
                    "payload": payload,
                    "updated_at": self._ora_iso(),
                }
                # LO STESSO OGGETTO va sul canale e nel database: chiavi, tipi e
                # valori non possono divergere perche' non ci sono due oggetti.
                self._spingi_riga(sport, riga)""",
     """                riga = {
                    "event_id": eid,
                    "sport": sport,
                    "payload": payload,
                    "updated_at": self._ora_iso(),
                }
                self._spingi_riga(sport, riga)
                if sport == "calcio" and _opportunities_enabled():
                    payload["opportunities"] = self.opportunities(payload)""",
     [T_NUOVO]),

    ("M15 sul canale una COPIA della riga invece della riga", SERVICE,
     """                self._spingi_riga(sport, riga)""",
     """                self._spingi_riga(sport, dict(riga))""",
     [T_NUOVO]),

    ("M16 il canale non riceve la riga frenata (push dopo il freno)", SERVICE,
     """                self._spingi_riga(sport, riga)
                if frenata:
                    continue""",
     """                if frenata:
                    continue
                self._spingi_riga(sport, riga)""",
     [T_NUOVO]),

    # ------------------------------------------------------------------ B12
    ("M17 topic unico per i due sport", SERVICE,
     """_TOPIC_SCAN = {"calcio": "scan_calcio", "tennis": "scan_tennis"}""",
     """_TOPIC_SCAN = {"calcio": "safe_scan", "tennis": "safe_scan"}""",
     [T_NUOVO]),

    # ------------------------------------------------------------------- B3
    ("M18 _spingi_riga senza try/except: il canale morto ferma lo scanner", SERVICE,
     """        try:
            canale.publish(topic, riga)
        except Exception as ex:  # noqa: BLE001 - mostrare non ferma mai lo scanner
            logger.debug("[safe-scan] push della riga KO: %s", str(ex)[:120])""",
     """        canale.publish(topic, riga)""",
     [T_NUOVO]),

    # ------------------------------------------------------------------- D4
    ("M19 contropressione GLOBALE invece che per client", CANALE,
     """                if self._in_volo_ws.get(ws, 0) > _MAX_INVII_IN_VOLO:""",
     """                if self._in_volo > _MAX_INVII_IN_VOLO:""",
     [T_NUOVO]),

    ("M20 nessuna uscita anticipata: il salto non si conta piu'", CANALE,
     """        if self._client_pronti <= 0:""",
     """        if False:""",
     [T_NUOVO]),

    # ------------------------------------------------------------------- B8
    ("M21 bind su 0.0.0.0", CANALE,
     """            async with serve(self._handler, "127.0.0.1", self.port):""",
     """            async with serve(self._handler, "0.0.0.0", self.port):""",
     [T_NUOVO]),

    # --------------------------------------------------------------- banco C21
    ("M22 il payload perde bet_delay (contratto del banco)", SERVICE,
     """                        "odds_pt_ms": ev.get("odds_pt_ms"),
                        "bet_delay": ev.get("bet_delay"),
                        # MERCATI A GOL del motore opportunità (chiavi ADDITIVE):""",
     """                        "odds_pt_ms": ev.get("odds_pt_ms"),
                        # MERCATI A GOL del motore opportunità (chiavi ADDITIVE):""",
     [T_NUOVO, T_BANCO]),

    # ---------------------------------------------- il canale che comanda
    ("M23 il canale dello scanner accetta comandi (solo_lettura=False)", SERVICE,
     """            ch = _lc.start_channel(porta, "safe-scan", solo_lettura=True)""",
     """            ch = _lc.start_channel(porta, "safe-scan", solo_lettura=False)""",
     [T_NUOVO]),

    # ---------------------------------------------- il canale dentro il banco
    ("M24 il canale si accende anche senza stream (cioe' nel banco di replay)",
     SERVICE,
     """            self._avvia_canale() if (use_stream and canale_voluto) else None""",
     """            self._avvia_canale() if canale_voluto else None""",
     [T_NUOVO]),

    # ------------------------------------------------------------ stato onesto
    ("M25 lo stato non dichiara piu' l'interruttore", SERVICE,
     """            "canale_acceso": self.canale is not None,""",
     """            "canale_acceso": False,""",
     [T_NUOVO]),
]


def md5(percorso: Path) -> str:
    return hashlib.md5(percorso.read_bytes()).hexdigest()


def leggi(percorso: Path) -> str:
    """Il file COSI' COM'E'. ``newline=""`` disattiva la traduzione universale
    dei fine riga: senza, un file con ``\\n`` verrebbe riscritto con ``\\r\\n``
    su Windows e il ripristino non sarebbe byte-esatto (visto il 18/09: l'md5
    di ``orologio.py`` cambiava al ripristino pur essendo il contenuto
    identico)."""
    with percorso.open("r", encoding="utf-8", newline="") as f:
        return f.read()


def scrivi(percorso: Path, testo: str) -> None:
    with percorso.open("w", encoding="utf-8", newline="") as f:
        f.write(testo)


def main() -> int:
    guasti: List[Tuple[str, str]] = []
    for nome, rel, vero, mutato, test in MUTAZIONI:
        p = RADICE / rel
        prima = md5(p)
        testo = leggi(p)
        # il testo da cercare e' scritto con ``\n``: se il file e' a CRLF va
        # tradotto, altrimenti non lo si trova e la mutazione verrebbe
        # dichiarata "punto non unico" invece di essere applicata
        a_capo = "\r\n" if "\r\n" in testo else "\n"
        # una mutazione e' una coppia (vero, mutato) oppure una LISTA di coppie:
        # certi difetti si riproducono solo toccando due punti insieme
        coppie = vero if isinstance(vero, list) else [(vero, mutato)]
        nuovo_testo = testo
        saltata = False
        for v, m in coppie:
            v_f, m_f = v.replace("\n", a_capo), m.replace("\n", a_capo)
            quante = nuovo_testo.count(v_f)
            if quante != 1:
                print(f"[SALTATA] {nome}: un punto da mutare compare {quante} volte",
                      flush=True)
                guasti.append((nome, "punto da mutare non unico"))
                saltata = True
                break
            nuovo_testo = nuovo_testo.replace(v_f, m_f)
        if saltata:
            continue
        scrivi(p, nuovo_testo)
        try:
            res = subprocess.run(
                [PY, "-m", "pytest", *test, "-q", "-p", "no:cacheprovider", "-x",
                 "--no-header", "-W", "ignore"],
                capture_output=True, text=True, cwd=str(RADICE), timeout=3600)
            rosso = res.returncode != 0
            coda = [r for r in res.stdout.strip().splitlines() if r.strip()][-1:]
            print(f"[{'ROSSO' if rosso else 'VERDE!'}] {nome} -> {coda}", flush=True)
            if not rosso:
                guasti.append((nome, "mutazione NON catturata"))
        finally:
            scrivi(p, testo)
        dopo = md5(p)
        if dopo != prima:
            print(f"[FERMO] {nome}: md5 {prima} -> {dopo}", flush=True)
            return 2
        print(f"         md5 {rel} = {prima} (invariato)", flush=True)
    print("\n=== GUASTI ===" if guasti else "\n=== TUTTE CATTURATE ===", flush=True)
    for g in guasti:
        print("   ", g, flush=True)
    return 1 if guasti else 0


if __name__ == "__main__":
    sys.exit(main())
