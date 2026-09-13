"""IL SOFTWARE DEVE LASCIAR RESPIRARE IL DATABASE — LE SCRITTURE (§17, parte 2).

Nessuna rete, nessun DB vero. File ASCII-only (console Windows cp1252).

Perche' questi test esistono
----------------------------
Il 13/09 il database Supabase e' andato giu' per esaurimento del budget di IO.
Sulle LETTURE il freno era gia' stato messo (``test_mike_respiro_db_2026_09_13``:
da 1680 a 198 letture al minuto). Ma il log dell'app accesa, la sera stessa,
diceva che il problema vero era rimasto scoperto — in SEI SECONDI:

    21:37:46,563  POST /rest/v1/mike_events?on_conflict=event_id
    21:37:46,667  POST /rest/v1/mike_events?on_conflict=event_id
    21:37:47,769  POST /rest/v1/mike_events?on_conflict=event_id
    21:37:48,270  POST /rest/v1/mike_events?on_conflict=event_id
    21:37:49,138  POST /rest/v1/mike_events?on_conflict=event_id
    21:37:49,553  PATCH /rest/v1/mike_control?id=eq.1

Su un database a corto di IO una SCRITTURA costa piu' di una lettura: l'UPSERT
riscrive la riga INTERA, aggiorna gli indici, produce WAL e da' lavoro
all'autovacuum. E la riga ``mike_events`` non e' piccola: ``live``, ``ctx``,
``positions``, ``dossier``, ``markets`` sono tutti JSON.

La causa esatta, e non era una svista di progetto: il write-on-change c'era
gia' (``service._persist`` confrontava la firma prima e dopo), ma la firma
guardava TUTTA la riga — compresi ``published_at`` / ``published_ts``, che per
costruzione valgono "adesso" a ogni giro, e ``feed_age_s`` / ``scanner_age_s``,
che sono eta' e crescono da sole. Con quattro campi cosi' dentro al confronto,
due giri identici producevano due firme diverse: il write-on-change esisteva
nel codice e non esisteva nei fatti. Misurato su cinque partite ferme, con la
stessa scena: 306 scritture al minuto prima, 8 dopo.

Il patto, identico a quello delle letture e per niente negoziabile:
  * la logica di trading NON cambia: cambia solo QUANDO si scrive;
  * una scrittura che porta un FATTO NUOVO (un ordine, una gamba abbinata, un
    cambio di stato, un regolamento) parte SUBITO, senza cadenze e senza lotti;
  * rallentare non vuol dire SCARTARE: nessuna scrittura va mai persa.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest

from Betfair.mike import config as C
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_feed import payload

NOW = datetime(2026, 9, 13, 21, 37, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


class DbScritture:
    """Un finto database che registra ogni SCRITTURA, con quante righe portava."""

    def __init__(self, params: Dict[str, Any] | None = None) -> None:
        self.params = params or {}
        self.eventi: Dict[str, Dict[str, Any]] = {}
        self.righe_feed: List[Dict[str, Any]] = []
        # ogni voce e' il NUMERO di righe di quella POST (1 = riga singola)
        self.post_eventi: List[int] = []
        self.patch_control = 0
        self.attivita: List[str] = []
        # se True l'accessore in blocco non esiste proprio (backend vecchio)
        self.senza_blocco = False
        self.blocco_esplode = False

    # -- letture -----------------------------------------------------------
    def read_control(self):
        return {"id": 1, "status": "running", "mode": "paper", "params": self.params}

    def fetch_scan_rows(self):
        return list(self.righe_feed)

    def list_events(self, states=None, since_iso=None):
        return [dict(e) for e in self.eventi.values()]

    def aggregates(self, *a, **k):
        return {"realized_today": 0.0, "open_count": 0, "open_liability": 0.0,
                "realized_total": 0.0, "won": 0, "lost": 0, "won_today": 0,
                "lost_today": 0, "cycles_today": 0, "events_today": 0}

    def scanner_status(self):
        return {"updated_at": _iso(NOW), "payload": {}}

    def pending_requests(self, limit=50):
        return []

    def open_trades(self):
        return []

    def trades_for_event(self, event_id):
        return []

    def all_trades(self):
        return []

    def get_trade(self, trade_id):
        return None

    def fail_stale_processing(self, minuti=10):
        return 0

    def fixture_id_for_event(self, event_id):
        return None

    def fixture_lambdas(self, fid):
        return None

    def fixture_analysis(self, fid):
        return None

    def ht_ft_rows(self, league_id):
        return []

    # -- scritture ---------------------------------------------------------
    def set_control(self, **kw):
        self.patch_control += 1

    def upsert_event(self, row):
        self.post_eventi.append(1)
        self.eventi[str(row["event_id"])] = dict(row)

    def __getattr__(self, nome):
        # ``senza_blocco`` simula un accessore che NON espone la scrittura in
        # blocco: ``getattr(db, "upsert_events", None)`` deve dare None.
        if nome == "upsert_events":
            if self.senza_blocco:
                raise AttributeError(nome)
            return self._upsert_events
        raise AttributeError(nome)

    def _upsert_events(self, rows):
        if self.blocco_esplode:
            raise RuntimeError("payload too large")
        self.post_eventi.append(len(rows))
        for r in rows:
            self.eventi[str(r["event_id"])] = dict(r)

    def log(self, kind, payload=None, event_id=None):
        self.attivita.append(kind)

    def insert_trade(self, row):
        return 1

    def update_trade(self, *a, **k):
        pass

    def set_request_status(self, *a, **k):
        pass

    # -- comodita' per gli assert ------------------------------------------
    @property
    def scritture_eventi(self) -> int:
        """Quante POST su ``mike_events`` (non quante righe): e' il numero che
        il database paga in andate e ritorno."""
        return len(self.post_eventi)

    @property
    def righe_scritte(self) -> int:
        return sum(self.post_eventi)


def _riga_feed(eid: str, quando: datetime, *, inplay: bool = False,
               minute: int | None = None, gol_casa: int | None = None,
               gol_ospiti: int | None = None, u35: tuple = (1.50, 1.52, 30.0, 25.0),
               ko: datetime | None = None) -> Dict[str, Any]:
    p = payload(ko=ko or (NOW + timedelta(hours=5)), inplay=inplay, minute=minute,
                sh=gol_casa, sa=gol_ospiti, u35=u35)
    p["event_name"] = "Partita %s" % eid
    return {"event_id": eid, "sport": "calcio", "payload": p, "updated_at": _iso(quando)}


def _gamba(ref: str, market: str, sel: str, price: float, role: str) -> Dict[str, Any]:
    return {"role": role, "market": market, "selection": sel, "side": "back", "price": price,
            "size": 10.0, "matched": 10.0, "avg_price": price, "ref": ref, "status": "open",
            "placed_at": (NOW - timedelta(hours=2)).timestamp(), "persistence": "LAPSE",
            "cycle_no": 0, "final": False, "archived": False}


def _partita(eid: str, *, state: str = "WATCH", inplay: bool = False,
             gambe: List[Dict[str, Any]] | None = None,
             ko: datetime | None = None) -> Dict[str, Any]:
    ko = ko or (NOW + timedelta(hours=5))
    return {
        "event_id": eid, "event_name": "Partita %s" % eid, "competition": "X", "state": state,
        "cycle_no": 0, "entry_price_initial": 1.5, "dossier": {}, "mode": "paper",
        "ko_at": _iso(ko),
        "markets": {"OU35": {"market_id": "1.35"}, "OU45": {"market_id": "1.45"}},
        "positions": [dict(g) for g in (gambe or [])], "live": {"inplay": inplay}, "ctx": {},
        "skipped": False, "settled_pnl": None,
    }


class Mercato:
    def read_book(self, market_id, names):
        return None


@pytest.fixture
def db(monkeypatch):
    """Un servizio con le cache ACCESE (nel resto della suite sono spente):
    qui si misura proprio quanto si disturba il database in un minuto vero."""
    for k, v in (("feed_cache_s", 2.0), ("events_reload_s", 60.0),
                 ("aggregates_cache_s", 20.0), ("reconcile_every_s", 30.0)):
        monkeypatch.setitem(C.DEFAULTS, k, v)
    S.svuota_le_cache()
    d = DbScritture()
    monkeypatch.setattr(S, "_real_db", d, raising=False)
    return d


def _giro(db: DbScritture, quando: datetime) -> Dict[str, Any]:
    return S.run_once(db=db, market=Mercato(), now=quando, dry=True)


# ===========================================================================
# IL CUORE: a parita' di situazione il secondo giro NON riscrive
# ===========================================================================
class TestWriteOnChange:
    def test_il_secondo_giro_a_parita_di_situazione_non_riscrive(self, db):
        """Il test che il 13/09 sarebbe stato rosso.

        Stessa partita, stesso feed, un secondo dopo: non e' successo NIENTE,
        quindi non c'e' niente da scrivere. Prima si riscriveva lo stesso,
        perche' dentro ``live`` c'erano l'ora di pubblicazione e l'eta' del
        feed — tre decine di KB di JSON per dire "sono passati mille
        millisecondi".
        """
        db.eventi = {"E1": _partita("E1")}
        db.righe_feed = [_riga_feed("E1", NOW)]
        _giro(db, NOW)
        primo = db.scritture_eventi
        assert primo >= 1, "il primo giro deve pubblicare la scheda"
        _giro(db, NOW + timedelta(seconds=1))
        assert db.scritture_eventi == primo, "niente e' cambiato: niente da scrivere"

    def test_dieci_giri_fermi_non_fanno_dieci_scritture(self, db):
        db.eventi = {"E1": _partita("E1")}
        for i in range(10):
            db.righe_feed = [_riga_feed("E1", NOW)]
            _giro(db, NOW + timedelta(milliseconds=300 * i))
        assert db.scritture_eventi == 1

    def test_la_firma_ignora_i_campi_che_cambiano_DA_SOLI(self, db):
        """La regressione, isolata: ``published_at``/``published_ts`` li ho
        aggiunti io per far ticcare l'eta' in pagina, e per costruzione valgono
        'adesso' a ogni giro. Se la firma li guarda, ogni riga risulta sempre
        cambiata e il write-on-change e' ANNULLATO."""
        base = _partita("E1")
        base["live"] = {"inplay": True, "minute": 30, "goals": 1,
                        "published_at": _iso(NOW), "published_ts": NOW.timestamp(),
                        "feed_age_s": 1.2, "scanner_age_s": 3.0}
        dopo = dict(base)
        dopo["live"] = {**base["live"], "published_at": _iso(NOW + timedelta(seconds=7)),
                        "published_ts": NOW.timestamp() + 7, "feed_age_s": 8.2,
                        "scanner_age_s": 10.0}
        assert S._signature(base) == S._signature(dopo)

    def test_la_firma_ignora_il_book_che_oscilla_di_un_tick(self, db):
        """Il miglior prezzo balla in continuazione: e' rumore, non un fatto.
        Il ladder della scheda viaggia sul battito di pubblicazione."""
        base = _partita("E1")
        base["live"] = {"inplay": True, "minute": 30, "goals": 1,
                        "books": {"OU35|UNDER": {"best_back": 1.50}},
                        "cashout": {"net": 0.42}, "hazard": 0.05}
        dopo = dict(base)
        dopo["live"] = {**base["live"], "books": {"OU35|UNDER": {"best_back": 1.51}},
                        "cashout": {"net": 0.38}, "hazard": 0.06}
        assert S._signature(base) == S._signature(dopo)

    def test_la_firma_ignora_il_motivo_dell_ultima_decisione(self, db):
        """``ctx.last_reason`` e' una frase con dentro prezzi e liquidita'
        ("liquidita 12.40 < 15.00"): cambia a ogni tick dicendo la stessa cosa.
        Non e' memoria dell'engine — non compare in ``_CTX_FIELDS`` — quindi
        non e' un fatto."""
        base = _partita("E1")
        base["ctx"] = {"attempts": 0, "last_reason": "ultimo ingresso: liquidita 12.40 < 15.00"}
        dopo = dict(base)
        dopo["ctx"] = {"attempts": 0, "last_reason": "ultimo ingresso: liquidita 12.55 < 15.00"}
        assert S._signature(base) == S._signature(dopo)

    def test_un_campo_NUOVO_e_sostanziale_finche_non_lo_si_dichiara(self, db):
        """Fail-safe dichiarato: la lista dei volatili e' una lista NERA. Un
        campo che nessuno ha classificato conta come fatto — al massimo si
        scrive una volta di troppo. Col criterio opposto un fatto nuovo
        potrebbe non essere scritto MAI, e quello costa soldi."""
        base = _partita("E1")
        base["live"] = {"inplay": True, "campo_inventato_domani": 1}
        dopo = dict(base)
        dopo["live"] = {"inplay": True, "campo_inventato_domani": 2}
        assert S._signature(base) != S._signature(dopo)


# ===========================================================================
# UN FATTO NUOVO SI SCRIVE SUBITO: nessuna cadenza, nessun lotto, nessuna cache
# ===========================================================================
class TestFattoNuovo:
    def test_un_GOL_viene_scritto_subito(self, db):
        """Il gol e' il fatto piu' importante che ci sia su una partita: cambia
        la copertura, il cash out e il rischio. Non aspetta nessun battito.

        Scena: partita in gioco con la posizione gia' coperta (Under 3.5 +
        Over 4.5 abbinati), cioe' il caso in cui il bot non ha niente da fare e
        si limita a guardare. I giri a vuoto non scrivono; il gol si'.
        """
        ko = NOW - timedelta(minutes=30)
        gambe = [_gamba("r1", "OU35", "UNDER", 1.5, "under_entry"),
                 _gamba("r2", "OU45", "OVER", 6.0, "cover")]
        db.eventi = {"E1": _partita("E1", state="LIVE_COVERED", inplay=True, gambe=gambe, ko=ko)}

        def feed(sec: int, gol: int) -> None:
            db.righe_feed = [_riga_feed("E1", NOW + timedelta(seconds=sec), inplay=True, minute=30,
                                        gol_casa=gol, gol_ospiti=0, ko=ko)]

        feed(0, 0)
        _giro(db, NOW)
        prima = db.scritture_eventi
        feed(2, 0)
        _giro(db, NOW + timedelta(seconds=2))
        assert db.scritture_eventi == prima, "senza gol non e' successo niente: niente da scrivere"
        feed(4, 1)
        _giro(db, NOW + timedelta(seconds=4))
        assert db.scritture_eventi == prima + 1, "il gol si scrive SUBITO"
        assert db.eventi["E1"]["live"]["goals"] == 1

    def test_un_fatto_nuovo_non_aspetta_la_cadenza_di_pubblicazione(self, db):
        """La proprieta', isolata: appena la firma sostanziale cambia si scrive,
        anche se il battito di pubblicazione e' appena passato. Un cambio di
        stato, una gamba abbinata, un regolamento non aspettano nessun orologio.
        """
        p = C.merge_params(None)
        ev = _partita("E1")
        t0 = NOW.timestamp()
        S._persist(db, ev, S._signature(ev), now_ts=t0, params=p)   # prima pubblicazione
        assert db.scritture_eventi == 1
        firma = S._signature(ev)
        S._persist(db, ev, firma, now_ts=t0 + 1.0, params=p)
        assert db.scritture_eventi == 1, "niente di nuovo, e la cadenza non e' passata"
        ev["state"] = "PRE_OPEN"                                    # il fatto nuovo
        S._persist(db, ev, firma, now_ts=t0 + 1.1, params=p)
        assert db.scritture_eventi == 2, "un cambio di stato parte subito"

    def test_una_partita_NUOVA_viene_scritta_subito(self, db):
        db.righe_feed = [_riga_feed("E1", NOW, ko=NOW + timedelta(hours=1))]
        _giro(db, NOW)
        assert "E1" in db.eventi

    def test_una_scrittura_immediata_non_viene_rimandata_dal_lotto(self, db):
        """Se la stessa partita aveva gia' una riscrittura di cortesia in coda,
        il fatto nuovo la sostituisce e parte comunque per conto suo: mai un
        fatto in attesa di un lotto."""
        lotto: Dict[str, Dict[str, Any]] = {}
        ev = _partita("E1")
        S._persist(db, ev, "firma-diversa", now_ts=NOW.timestamp(),
                   params=C.merge_params(None), lotto=lotto)
        assert db.scritture_eventi == 1 and lotto == {}


# ===========================================================================
# L'ORA DI PUBBLICAZIONE: rallentata, MAI tolta
# ===========================================================================
class TestBattitoDiPubblicazione:
    def test_published_at_si_rinfresca_alla_sua_cadenza(self, db):
        """``published_at`` non si puo' togliere: la scheda ci calcola sopra
        un'eta' che TICKA ed e' il semaforo dei bottoni che mandano ordini
        veri. Si rallenta, e basta — e la cadenza e' la sua, non quella del
        ciclo."""
        p = C.merge_params(None)
        ogni = float(p["publish_heartbeat_s"])
        ev = _partita("E1", state="PRE_OPEN",
                      gambe=[_gamba("r1", "OU35", "UNDER", 1.5, "under_entry")])
        t0 = NOW.timestamp()
        S._persist(db, ev, S._signature(ev), now_ts=t0, params=p)
        assert db.scritture_eventi == 1
        firma = S._signature(ev)
        for i in range(1, int(ogni)):
            S._persist(db, ev, firma, now_ts=t0 + i, params=p)
        assert db.scritture_eventi == 1, "entro la cadenza non si riscrive"
        S._persist(db, ev, firma, now_ts=t0 + ogni + 0.1, params=p)
        assert db.scritture_eventi == 2, "passata la cadenza si rinfresca"

    def test_la_cadenza_resta_sotto_la_soglia_che_spegne_i_bottoni(self):
        """L'equilibrio, in numeri. La card somma l'eta' CONGELATA del feed al
        tempo passato dalla pubblicazione (``mike.ts::etaQuoteS``) e oltre 20 s
        il badge diventa rosso "FEED FERMO", che SPEGNE il cash out.
        ``publish_heartbeat_s`` deve stare cosi' sotto da lasciare spazio
        all'eta' del feed senza mai far scattare il rosso."""
        soglia_rosso_s = 20.0
        feed_tipico_s = 3.0
        assert float(C.DEFAULTS["publish_heartbeat_s"]) + feed_tipico_s < soglia_rosso_s

    def test_una_partita_solo_OSSERVATA_ha_il_battito_largo(self):
        """Senza posizione non c'e' niente da chiudere: nessun bottone da
        illuminare, l'eta' e' cosmetica. Sono la maggioranza delle righe nelle
        ore pre-partita, ed erano loro a riempire il log di POST."""
        p = C.merge_params(None)
        osservata = _partita("E1")
        con_soldi = _partita("E2", state="PRE_OPEN",
                             gambe=[_gamba("r1", "OU35", "UNDER", 1.5, "under_entry")])
        assert S._cadenza_pubblicazione(osservata, p) == p["publish_idle_heartbeat_s"]
        assert S._cadenza_pubblicazione(con_soldi, p) == p["publish_heartbeat_s"]
        assert S._cadenza_pubblicazione(con_soldi, p) < S._cadenza_pubblicazione(osservata, p)

    def test_una_partita_TERMINALE_non_si_riscrive_piu(self):
        """Regolata o saltata: l'ultima scrittura e' gia' la verita' definitiva
        e la card non ha bottoni. Zero = mai piu'."""
        finita = _partita("E1", state="SETTLED",
                          gambe=[_gamba("r1", "OU35", "UNDER", 1.5, "under_entry")])
        assert S._cadenza_pubblicazione(finita, C.merge_params(None)) == 0.0

    def test_a_cadenza_zero_si_torna_al_puro_write_on_change(self, db):
        """Ogni valore e' un parametro: a zero il battito di cortesia sparisce
        del tutto e restano SOLO le scritture dei fatti."""
        db.params = {"publish_heartbeat_s": 0, "publish_idle_heartbeat_s": 0}
        db.eventi = {"E1": _partita("E1")}
        for i in range(120):
            # il feed si aggiorna davvero (altrimenti a un certo punto diventa
            # stantio, e QUELLO e' un fatto: va scritto)
            db.righe_feed = [_riga_feed("E1", NOW + timedelta(seconds=i))]
            _giro(db, NOW + timedelta(seconds=i))
        assert db.scritture_eventi == 1


# ===========================================================================
# LA SCRITTURA IN BLOCCO: una POST invece di una per partita
# ===========================================================================
class TestScritturaInBlocco:
    def test_le_riscritture_di_cortesia_viaggiano_in_UNA_sola_post(self, db):
        db.eventi = {"E%d" % i: _partita("E%d" % i) for i in range(5)}
        db.righe_feed = [_riga_feed("E%d" % i, NOW) for i in range(5)]
        _giro(db, NOW)
        db.post_eventi.clear()
        oltre = NOW + timedelta(seconds=float(C.DEFAULTS["publish_idle_heartbeat_s"]) + 1)
        db.righe_feed = [_riga_feed("E%d" % i, oltre) for i in range(5)]
        _giro(db, oltre)
        assert db.post_eventi == [5], "cinque righe, UNA sola andata e ritorno"

    def test_senza_accessore_in_blocco_si_scrive_riga_per_riga(self, db):
        """Backend vecchio (o parametro spento): si ripiega, non si perde
        niente. MAI una scrittura sacrificata a un'ottimizzazione."""
        db.senza_blocco = True
        db.eventi = {"E%d" % i: _partita("E%d" % i) for i in range(3)}
        db.righe_feed = [_riga_feed("E%d" % i, NOW) for i in range(3)]
        _giro(db, NOW)
        db.post_eventi.clear()
        oltre = NOW + timedelta(seconds=float(C.DEFAULTS["publish_idle_heartbeat_s"]) + 1)
        db.righe_feed = [_riga_feed("E%d" % i, oltre) for i in range(3)]
        _giro(db, oltre)
        assert db.post_eventi == [1, 1, 1]
        assert db.righe_scritte == 3

    def test_se_il_blocco_fallisce_le_righe_partono_lo_stesso(self, db):
        """Il caso che fa perdere soldi se gestito male: la POST in blocco
        esplode (payload troppo grosso, timeout) e le righe restano nel
        cassetto. Qui si ripiega riga per riga."""
        db.blocco_esplode = True
        lotto = {"E1": _partita("E1"), "E2": _partita("E2")}
        S._svuota_lotto(db, lotto, C.merge_params(None))
        assert db.righe_scritte == 2 and lotto == {}

    def test_il_lotto_non_sopravvive_al_giro_nemmeno_se_il_ciclo_esplode(self, db):
        """Una partita rotta non deve portarsi dietro le scritture delle altre:
        lo svuotamento sta in un ``finally``."""
        db.eventi = {"E%d" % i: _partita("E%d" % i) for i in range(3)}
        db.righe_feed = [_riga_feed("E%d" % i, NOW) for i in range(3)]
        _giro(db, NOW)
        db.post_eventi.clear()
        originale = S._run_event

        def esplode_sulla_seconda(**kw):
            if str(kw["ev"].get("event_id")) == "E1":
                raise RuntimeError("partita rotta")
            return originale(**kw)

        S._run_event = esplode_sulla_seconda        # type: ignore[assignment]
        try:
            oltre = NOW + timedelta(seconds=float(C.DEFAULTS["publish_idle_heartbeat_s"]) + 1)
            db.righe_feed = [_riga_feed("E%d" % i, oltre) for i in range(3)]
            _giro(db, oltre)
        finally:
            S._run_event = originale                # type: ignore[assignment]
        assert db.righe_scritte == 2, "le due partite sane sono state scritte lo stesso"


# ===========================================================================
# mike_control: il battito e le stats hanno una cadenza, ed e' un parametro
# ===========================================================================
class TestControl:
    def test_le_stats_non_si_riscrivono_a_ogni_giro(self, db):
        db.eventi = {"E1": _partita("E1")}
        for i in range(30):
            db.righe_feed = [_riga_feed("E1", NOW)]
            _giro(db, NOW + timedelta(seconds=i))
        # 30 secondi: al massimo un battito ogni ``stats_min_s``
        atteso = 30.0 / float(C.DEFAULTS["stats_min_s"]) + 1
        assert db.patch_control <= atteso, "PATCH mike_control: %d" % db.patch_control

    def test_il_battito_resta_ben_dentro_la_soglia_di_servizio_morto(self):
        """``ServiceHealthChip.SERVICE_STALE_S`` = 45 s: la UI dichiara il
        servizio morto oltre quella. Il battito nudo deve lasciare margine per
        saltarne uno senza che il badge diventi rosso."""
        assert float(C.DEFAULTS["heartbeat_min_s"]) * 2 < 45.0

    def test_le_cadenze_del_control_sono_parametri(self, db):
        db.params = {"stats_min_s": 0.0, "heartbeat_min_s": 1.0}
        db.eventi = {"E1": _partita("E1")}
        for i in range(5):
            db.righe_feed = [_riga_feed("E1", NOW)]
            _giro(db, NOW + timedelta(seconds=i))
        assert db.patch_control >= 4, "a cadenza aperta si torna al battito di prima"


# ===========================================================================
# IL CONTO COMPLESSIVO: quante SCRITTURE in un minuto di lavoro
# ===========================================================================
def test_un_minuto_di_lavoro_non_deve_costare_trecento_scritture(db):
    """La misura che riassume tutto, sulla scena del log del 13/09.

    Cinque partite, sessanta giri da un secondo, il book che oscilla di un tick
    ogni due secondi (la vita normale di un mercato). Prima: 300 POST su
    ``mike_events`` piu' 6 PATCH su ``mike_control`` = 306 scritture al minuto,
    ognuna delle quali riscriveva la riga INTERA con tutti i suoi JSON.
    """
    db.eventi = {"E%d" % i: _partita("E%d" % i) for i in range(5)}
    for g in range(60):
        prezzo = (1.50, 1.52, 30.0, 25.0) if (g // 2) % 2 == 0 else (1.51, 1.53, 30.0, 25.0)
        quando = NOW + timedelta(seconds=(g // 2) * 2)
        db.righe_feed = [_riga_feed("E%d" % i, quando, u35=prezzo) for i in range(5)]
        _giro(db, NOW + timedelta(seconds=g))
    totale = db.scritture_eventi + db.patch_control
    assert db.scritture_eventi <= 10, "POST su mike_events: %s" % db.post_eventi
    assert totale <= 20, "scritture in un minuto: %d (POST %s, PATCH %d)" % (
        totale, db.post_eventi, db.patch_control)
