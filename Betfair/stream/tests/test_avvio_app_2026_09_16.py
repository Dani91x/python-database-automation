"""FASE A — all'avvio dell'app nessun bot opera (16/09/2026).

Qui si certifica il MECCANISMO condiviso (``Betfair/stream/avvio_app.py``) piu'
i due percorsi per riga: bot tennis per evento e sessioni scalper per partita.

⚠️ I FINTI PARLANO COME IL VERO. Le righe di controllo di questi test NON sono
scritte a memoria: ``riga_control`` le costruisce leggendo le COLONNE VERE dalle
migrazioni (``migrations/*.sql``), e ``test_le_colonne_sono_quelle_vere``
fallisce se una colonna cambia. E' la stessa regola che il 15/09 e' costata 32
ordini veri: un finto con le chiavi sbagliate certifica il difetto invece di
prenderlo.

File ASCII-only (console Windows cp1252).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

import pytest

from Betfair.stream import avvio_app as AA

RADICE = Path(__file__).resolve().parents[3]
MIGRAZIONI = {
    "mike_control": RADICE / "migrations" / "mike_bot.sql",
    "omega_control": RADICE / "migrations" / "omega_bot.sql",
    "safe_strategy_control": RADICE / "migrations" / "safe_strategy_bot.sql",
    "tennis_bot_control": RADICE / "migrations" / "tennis_bots.sql",
    "scalper_control": RADICE / "migrations" / "scalper_bot.sql",
}
_NON_COLONNE = ("primary", "unique", "check", "constraint", "foreign", "--")


def colonne_vere(tabella: str) -> list[str]:
    """Le colonne della tabella, lette dalla MIGRAZIONE (non dalla memoria)."""
    sql = MIGRAZIONI[tabella].read_text(encoding="utf-8", errors="replace")
    inizio = sql.index(f"CREATE TABLE IF NOT EXISTS public.{tabella} (")
    corpo = sql[inizio:]
    corpo = corpo[corpo.index("(") + 1: corpo.index("\n);")]
    fuori: list[str] = []
    for riga in corpo.splitlines():
        r = riga.strip()
        if not r or r.lower().startswith(_NON_COLONNE):
            continue
        nome = re.split(r"[\s(]", r, maxsplit=1)[0].strip().strip(",")
        if nome and nome not in fuori and re.fullmatch(r"[a-z_][a-z0-9_]*", nome):
            fuori.append(nome)
    return fuori


def riga_control(tabella: str, **valori: Any) -> dict[str, Any]:
    """Una riga di controllo con TUTTE e SOLE le colonne vere della tabella.

    I valori non passati valgono ``None``, che e' esattamente quello che
    Supabase restituisce per una colonna mai scritta (``stats``, ``error``,
    ``stopped_at``...). Chi scrive un test non puo' dimenticarsi una chiave ne'
    inventarne una: la costruzione parte dallo schema.
    """
    riga = {c: None for c in colonne_vere(tabella)}
    ignote = set(valori) - set(riga)
    assert not ignote, f"colonne inesistenti su {tabella}: {sorted(ignote)}"
    riga.update(valori)
    return riga


# ---------------------------------------------------------------------------
# Lo schema: se cambia, questi test lo dicono
# ---------------------------------------------------------------------------
def test_le_colonne_sono_quelle_vere():
    assert colonne_vere("mike_control") == [
        "id", "status", "mode", "params", "stats", "error",
        "started_at", "stopped_at", "heartbeat_at", "updated_at", "created_at"]
    assert colonne_vere("safe_strategy_control") == colonne_vere("mike_control")
    # Omega ha in piu' l'obiettivo del giorno, che vive FUORI da params
    assert "daily_goal" in colonne_vere("omega_control")
    # le due tabelle PER RIGA su cui si appoggiano tennis e scalper
    assert "stats" in colonne_vere("tennis_bot_control")
    assert "stats" in colonne_vere("scalper_control")


def test_nessuna_colonna_nuova_da_migrare():
    """L'id dell'avvio vive dentro ``stats``, che ESISTE GIA' su tutte e cinque
    le tabelle: nessuna migrazione da applicare per la FASE A."""
    for tabella in MIGRAZIONI:
        assert "stats" in colonne_vere(tabella), tabella


# ---------------------------------------------------------------------------
# Le decisioni pure
# ---------------------------------------------------------------------------
def test_boot_id_assente_vale_avvio_nuovo(monkeypatch):
    monkeypatch.delenv(AA.ENV_BOOT_ID, raising=False)
    assert AA.boot_id_ambiente() == ""
    # due assenze non fanno un'uguaglianza: e' il fail-closed
    assert AA.stesso_avvio({"boot_id": ""}, "") is False
    assert AA.stesso_avvio(None, "") is False


def test_boot_id_vuoto_o_spazi_e_come_assente(monkeypatch):
    monkeypatch.setenv(AA.ENV_BOOT_ID, "   ")
    assert AA.boot_id_ambiente() == ""


def test_stesso_avvio_solo_con_id_identici():
    assert AA.stesso_avvio({"boot_id": "B1"}, "B1") is True
    assert AA.stesso_avvio({"boot_id": "B1"}, "B2") is False
    assert AA.stesso_avvio({}, "B1") is False
    assert AA.stesso_avvio({"boot_id": None}, "B1") is False


def test_timbra_non_perde_le_altre_stats():
    g = AA.Guardia("x")
    g.fatto, g.boot_id, g.fermato_at = True, "B9", "2026-09-16T07:00:00+00:00"
    fuori = g.timbra({"realized_today": 1.5, "motivo_blocco": None})
    assert fuori["realized_today"] == 1.5 and fuori["motivo_blocco"] is None
    assert fuori["boot_id"] == "B9"
    assert fuori["fermato_all_avvio_at"] == "2026-09-16T07:00:00+00:00"


def test_timbra_non_tocca_niente_prima_del_controllo():
    g = AA.Guardia("x")
    prima = {"realized_today": 1.5}
    assert g.timbra(prima) is prima


def test_blocca_aperture_solo_da_servizio():
    g = AA.Guardia("x")
    assert g.blocca_aperture is False          # run_once da un test/banco: nessun effetto
    g.attiva = True
    assert g.blocca_aperture is True           # servizio, controllo non ancora fatto
    g.fatto = True
    assert g.blocca_aperture is False


# ---------------------------------------------------------------------------
# Il controllo sulla riga singleton
# ---------------------------------------------------------------------------
class Scritture:
    """Raccoglie le scritture come farebbe il DB (nessuna rete)."""

    def __init__(self, riga: dict[str, Any]) -> None:
        self.riga = riga
        self.set_calls: list[dict[str, Any]] = []
        self.log_calls: list[tuple[str, dict[str, Any]]] = []

    def set_control(self, **campi: Any) -> None:
        self.set_calls.append(dict(campi))
        self.riga.update(campi)

    def log(self, kind: str, payload: Optional[dict[str, Any]] = None) -> None:
        self.log_calls.append((kind, dict(payload or {})))


def test_avvio_nuovo_ferma_e_riporta_in_prova():
    riga = riga_control("mike_control", id=1, status="running", mode="live",
                        params={"stake": 5}, stats={"boot_id": "IERI", "realized_today": 3.0})
    db = Scritture(riga)
    g = AA.Guardia("mike")
    esito = AA.ferma_al_nuovo_avvio(g, control=riga, set_control=db.set_control,
                                    log=db.log, now_iso="2026-09-16T07:00:00+00:00",
                                    boot_id="OGGI")
    assert esito and esito["azzerato"] is True
    assert db.riga["status"] == "stopped" and db.riga["mode"] == "paper"
    assert db.riga["stats"]["boot_id"] == "OGGI"
    assert db.riga["stats"]["realized_today"] == 3.0     # le altre stats restano
    assert db.riga["stats"]["fermato_all_avvio_at"] == "2026-09-16T07:00:00+00:00"
    assert db.riga["params"] == {"stake": 5}             # LE STRATEGIE NON SI TOCCANO
    assert "params" not in db.set_calls[0]
    assert db.log_calls[0][0] == AA.KIND_ATTIVITA
    assert db.log_calls[0][1]["status_precedente"] == "running"
    assert db.log_calls[0][1]["mode_precedente"] == "live"


def test_stesso_avvio_non_scrive_niente():
    riga = riga_control("mike_control", id=1, status="running", mode="live",
                        params={"stake": 5}, stats={"boot_id": "OGGI"})
    db = Scritture(riga)
    g = AA.Guardia("mike")
    assert AA.ferma_al_nuovo_avvio(g, control=riga, set_control=db.set_control,
                                   log=db.log, now_iso="2026-09-16T07:00:00+00:00",
                                   boot_id="OGGI") is None
    assert db.set_calls == [] and db.log_calls == []
    assert riga["status"] == "running" and riga["mode"] == "live"
    assert g.fatto is True and g.blocca_aperture is False


def test_controllo_una_volta_sola_per_processo():
    riga = riga_control("mike_control", id=1, status="running", mode="live",
                        params={}, stats=None)
    db = Scritture(riga)
    g = AA.Guardia("mike")
    AA.ferma_al_nuovo_avvio(g, control=riga, set_control=db.set_control, log=db.log,
                            now_iso="2026-09-16T07:00:00+00:00", boot_id="OGGI")
    # l'utente riaccende: il secondo giro NON deve rispegnerlo
    riga["status"], riga["mode"] = "running", "live"
    AA.ferma_al_nuovo_avvio(g, control=riga, set_control=db.set_control, log=db.log,
                            now_iso="2026-09-16T07:00:10+00:00", boot_id="OGGI")
    assert len(db.set_calls) == 1
    assert riga["status"] == "running"


def test_bot_gia_fermo_non_scrive_attivita_ma_salva_l_id():
    riga = riga_control("mike_control", id=1, status="stopped", mode="paper",
                        params={}, stats=None)
    db = Scritture(riga)
    esito = AA.ferma_al_nuovo_avvio(AA.Guardia("mike"), control=riga,
                                    set_control=db.set_control, log=db.log,
                                    now_iso="2026-09-16T07:00:00+00:00", boot_id="OGGI")
    assert esito["azzerato"] is False
    assert db.log_calls == []                       # non e' stato «fermato all'avvio»
    assert db.riga["stats"]["boot_id"] == "OGGI"    # ma l'id c'e': il crash dopo non ricomincia
    assert "fermato_all_avvio_at" not in db.riga["stats"]


def test_scrittura_fallita_lascia_la_guardia_chiusa():
    riga = riga_control("mike_control", id=1, status="running", mode="live", params={})
    g = AA.Guardia("mike")
    g.attiva = True

    def esplode(**_campi: Any) -> None:
        raise RuntimeError("supabase giu'")

    with pytest.raises(RuntimeError):
        AA.ferma_al_nuovo_avvio(g, control=riga, set_control=esplode,
                                now_iso="2026-09-16T07:00:00+00:00", boot_id="OGGI")
    assert g.fatto is False and g.blocca_aperture is True


# ---------------------------------------------------------------------------
# TENNIS — righe per evento (tennis_bot_control)
# ---------------------------------------------------------------------------
class TennisFinto:
    """Specchio in memoria di ``tennis_db`` (stessi nomi e stesse firme)."""

    def __init__(self, righe: list[dict[str, Any]]) -> None:
        self.righe = righe
        self.stati: list[tuple] = []
        self.attivita: list[tuple] = []

    def list_tennis_bot_controls(self, event_id=None, statuses=None):
        return [dict(r) for r in self.righe
                if (statuses is None or r.get("status") in statuses)]

    def set_tennis_bot_status(self, event_id, bot_key, status, *, error=None,
                              stats=None, heartbeat=False, started=False, stopped=False,
                              mode=None, dry_run=None):
        self.stati.append((event_id, bot_key, status, error, stats, stopped))
        for r in self.righe:
            if r["event_id"] == event_id and r["bot_key"] == bot_key:
                r["status"] = status
                if stats is not None:
                    r["stats"] = stats
                if mode is not None:
                    r["mode"] = mode
                if dry_run is not None:
                    r["dry_run"] = dry_run

    def write_tennis_bot_activity(self, event_id, bot_key, kind, payload):
        self.attivita.append((event_id, bot_key, kind, dict(payload)))

    def _now_iso(self):
        return "2026-09-16T07:00:00+00:00"


def _riga_tennis(**over: Any) -> dict[str, Any]:
    base = dict(event_id="EV1", bot_key="tennis_scalper", status="armed",
                dry_run=True, stake=5, params={"soglia": 2}, stats=None)
    return riga_control("tennis_bot_control", **{**base, **over})


def test_tennis_bot_armato_ieri_si_ferma_al_nuovo_avvio(monkeypatch):
    from Betfair.stream.tennis_live import tennis_bot_service as TB

    finto = TennisFinto([_riga_tennis(stats={"boot_id": "IERI", "entries": 2})])
    monkeypatch.setattr(TB, "tennis_db", finto)
    fermate = TB.ferma_bot_al_nuovo_avvio(boot_id="OGGI", db=finto)
    assert len(fermate) == 1
    assert finto.righe[0]["status"] == "stopped"
    assert finto.righe[0]["stats"]["boot_id"] == "OGGI"
    assert finto.righe[0]["stats"]["entries"] == 2          # le stat del bot restano
    assert finto.attivita[0][2] == AA.KIND_ATTIVITA
    assert finto.attivita[0][3]["status_precedente"] == "armed"


def test_tennis_bot_di_questo_avvio_non_si_tocca(monkeypatch):
    from Betfair.stream.tennis_live import tennis_bot_service as TB

    finto = TennisFinto([_riga_tennis(status="running", stats={"boot_id": "OGGI"})])
    monkeypatch.setattr(TB, "tennis_db", finto)
    assert TB.ferma_bot_al_nuovo_avvio(boot_id="OGGI", db=finto) == []
    assert finto.righe[0]["status"] == "running"
    assert finto.stati == [] and finto.attivita == []


def test_tennis_senza_boot_id_in_ambiente_si_ferma(monkeypatch):
    from Betfair.stream.tennis_live import tennis_bot_service as TB

    monkeypatch.delenv(AA.ENV_BOOT_ID, raising=False)
    finto = TennisFinto([_riga_tennis(status="requested", stats={"boot_id": "IERI"})])
    monkeypatch.setattr(TB, "tennis_db", finto)
    assert len(TB.ferma_bot_al_nuovo_avvio(db=finto)) == 1
    assert finto.righe[0]["status"] == "stopped"


def test_tennis_i_params_della_riga_non_si_toccano(monkeypatch):
    """R2 (25/09, decisione dell'utente): params e stake restano identici, ma la
    riga torna in PROVA (``mode='paper'``, ``dry_run=True``): prima del 25/09
    qui si collaudava che ``dry_run=False`` sopravvivesse al nuovo avvio."""
    from Betfair.stream.tennis_live import tennis_bot_service as TB

    finto = TennisFinto([_riga_tennis(params={"soglia": 2}, stake=25, dry_run=False)])
    monkeypatch.setattr(TB, "tennis_db", finto)
    TB.ferma_bot_al_nuovo_avvio(boot_id="OGGI", db=finto)
    assert finto.righe[0]["params"] == {"soglia": 2}
    assert finto.righe[0]["stake"] == 25
    assert finto.righe[0]["dry_run"] is True and finto.righe[0]["mode"] == "paper"


# ---------------------------------------------------------------------------
# SCALPER — righe per partita (scalper_control)
# ---------------------------------------------------------------------------
class ScalperFinto:
    """Specchio in memoria di ``scalper_service.Db`` (stesse firme)."""

    def __init__(self, righe: list[dict[str, Any]]) -> None:
        self.righe = righe
        self.set_calls: list[tuple[str, dict[str, Any]]] = []
        self.attivita: list[tuple] = []

    def controls(self):
        return [dict(r) for r in self.righe
                if r.get("status") in ("requested", "arming", "running", "stopping")]

    def set_control(self, event_id, **campi):
        self.set_calls.append((event_id, dict(campi)))
        for r in self.righe:
            if r["event_id"] == event_id:
                r.update(campi)

    def activity(self, event_id, kind, payload):
        self.attivita.append((event_id, kind, dict(payload)))


def _riga_scalper(**over: Any) -> dict[str, Any]:
    base = dict(event_id="34567", status="requested", mode="maker", dry_run=True,
                stake=25, params={"tick": 2}, stats=None, heartbeat_at=None,
                started_at=None)
    return riga_control("scalper_control", **{**base, **over})


def test_scalper_richiesta_di_ieri_non_riparte_da_sola():
    from Betfair.stream.scalper import scalper_service as SS

    finto = ScalperFinto([_riga_scalper(stats={"boot_id": "IERI"})])
    fermate = SS.ferma_sessioni_al_nuovo_avvio(finto, boot_id="OGGI")
    assert len(fermate) == 1
    assert finto.righe[0]["status"] == "stopped"
    assert finto.righe[0]["stats"]["boot_id"] == "OGGI"
    assert finto.righe[0]["params"] == {"tick": 2}          # params intatti
    assert finto.righe[0]["stake"] == 25 and finto.righe[0]["mode"] == "maker"
    assert finto.attivita[0][1] == AA.KIND_ATTIVITA


def test_scalper_sessione_viva_non_si_tocca():
    """Una sessione figlia SOPRAVVIVE al supervisore: con l'heartbeat fresco sta
    operando davvero e non la si spegne da qui (lo fa il trader dalla sua
    pagina, con la chiusura flat)."""
    from datetime import datetime, timezone

    from Betfair.stream.scalper import scalper_service as SS

    adesso = datetime.now(timezone.utc).isoformat()
    finto = ScalperFinto([_riga_scalper(status="running", heartbeat_at=adesso)])
    assert SS.ferma_sessioni_al_nuovo_avvio(finto, boot_id="OGGI") == []
    assert finto.righe[0]["status"] == "running"
    assert finto.set_calls == []


def test_scalper_riga_di_questo_avvio_non_si_tocca():
    from Betfair.stream.scalper import scalper_service as SS

    finto = ScalperFinto([_riga_scalper(stats={"boot_id": "OGGI"})])
    assert SS.ferma_sessioni_al_nuovo_avvio(finto, boot_id="OGGI") == []
    assert finto.righe[0]["status"] == "requested"


def test_scalper_senza_boot_id_in_ambiente_si_ferma(monkeypatch):
    from Betfair.stream.scalper import scalper_service as SS

    monkeypatch.delenv(AA.ENV_BOOT_ID, raising=False)
    finto = ScalperFinto([_riga_scalper(stats={"boot_id": "IERI"})])
    assert len(SS.ferma_sessioni_al_nuovo_avvio(finto)) == 1


# ---------------------------------------------------------------------------
# Il watchdog deve poter passare l'ambiente al figlio
# ---------------------------------------------------------------------------
def test_il_watchdog_non_sostituisce_l_ambiente_del_figlio():
    """EVIDENZA della propagazione: ``run_watchdog`` chiama ``popen(cmd, cwd=...)``
    e NON passa ``env=``, quindi il figlio eredita l'``APP_BOOT_ID`` che l'app
    ha messo nell'ambiente del watchdog. Se qualcuno aggiungesse un ``env``
    ripulito, un crash diventerebbe un «avvio nuovo» e spegnerebbe il bot."""
    from Betfair.stream import watchdog as W

    visti: list[dict[str, Any]] = []

    class Figlio:
        returncode = 0

        def poll(self):
            return 0

    def popen_finto(cmd, **kw):
        visti.append(dict(kw))
        return Figlio()

    W.run_watchdog([], popen=popen_finto, sleep=lambda _s: None,
                   now=lambda: 100.0, alert=lambda *_a: None,
                   heartbeat=lambda: None, telegram=lambda *_a: None)
    assert visti and "env" not in visti[0]
