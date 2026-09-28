"""R-28-2 (CANTIERE F, 28/09/2026): l'action notturna dell'Atlante Hazard
(run 36390445058, 07:13Z) e' andata ROSSA con ``HTTP Error 500`` sull'UNICA
POST che scrive la riga globale in ``hazard_atlas`` (``_Scrittore.salva_versione``,
``genera_atlante.py:943`` prima della correzione). A DB (SOLA LETTURA, sola
prova, vedi referto): il ruolo ``authenticator`` (login reale di PostgREST,
anche per le chiamate service_role: ``SET ROLE`` non azzera le sue GUC di
sessione) ha ``statement_timeout=8s``; quella notte giravano insieme Hazard
Atlas, Retrain ML Models e Monthly Leagues Mapping (stesso Daily): lo stesso
codice 57014 gia' visto da ``season_gaps.py`` quella notte. 90/185 leghe di
``hazard_atlas_leghe`` risultano scritte con successo alle 07:13:13Z (le
POST a blocchi di 20 di ``salva_leghe``, sotto il payload che fa scattare il
timeout): SOLO la POST unica del payload intero ("una sola scrittura", ~4 MB
e in crescita) e' quella che sfora. Nessun trigger/constraint su
``hazard_atlas`` (verificato: solo PK): non e' un difetto nei DATI.

Nessuna rete, nessun DB: ``urllib.request.urlopen`` e' rimpiazzato da un
finto che risponde con la sequenza di esiti dichiarata dal test (stesso
stile del resto del modulo: HTTPError con corpo leggibile via ``.read()``,
come la vera risposta di PostgREST)."""
from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

import pytest

from Betfair.stream.scalper import genera_atlante as G


# --------------------------------------------------------------- finti HTTP
class _RispostaFinta:
    """Contesto ``with ... as r: r.read()`` di una 200 OK."""

    def __init__(self, corpo: bytes = b"") -> None:
        self._corpo = corpo

    def __enter__(self) -> "_RispostaFinta":
        return self

    def __exit__(self, *a: Any) -> None:
        return None

    def read(self) -> bytes:
        return self._corpo


def _http_error(code: int, corpo: bytes = b'{"code":"57014","message":"canceled due to '
                                          b'statement timeout"}') -> urllib.error.HTTPError:
    return urllib.error.HTTPError("http://finto/rest/v1/x", code, "err", {}, io.BytesIO(corpo))


class UrlopenFinto:
    """Sequenza di esiti PER CHIAMATA (in ordine); l'ultimo esito si ripete
    se le chiamate superano la lista (comodo per "sempre KO"). Registra ogni
    richiesta (metodo, path, corpo decodificato)."""

    def __init__(self, esiti: List[Any]) -> None:
        self.esiti = esiti
        self.chiamate: List[Dict[str, Any]] = []

    def __call__(self, req: urllib.request.Request, timeout: float = 0.0) -> _RispostaFinta:
        path = req.full_url.split("/rest/v1/", 1)[-1]
        corpo = json.loads(req.data.decode("utf-8")) if req.data else None
        self.chiamate.append({"metodo": req.get_method(), "path": path, "corpo": corpo})
        i = len(self.chiamate) - 1
        esito = self.esiti[i] if i < len(self.esiti) else self.esiti[-1]
        if isinstance(esito, Exception):
            raise esito
        if isinstance(esito, (bytes, bytearray)):
            return _RispostaFinta(bytes(esito))
        # una GET (letta con json.loads da LettoreDB.get) vuole un corpo
        # JSON valido; una POST/DELETE con "return=minimal" ignora il corpo
        return _RispostaFinta(b"[]" if req.get_method() == "GET" else b"")


def _sonno_finto() -> List[float]:
    attese: List[float] = []

    def sonno(s: float) -> None:
        attese.append(s)
    sonno.attese = attese  # type: ignore[attr-defined]
    return sonno


def _atlas(n_leagues: int = 1) -> Dict[str, Any]:
    return {"meta": {"generated_at": "2026-09-28T07:13:00+00:00", "n_leagues": n_leagues,
                     "n_fixtures_used": 10, "watermark_event_id": 999},
            "global": {}, "by_league": {}, "by_team": {}, "h2h_hint": {}}


def _stati_toccate(n: int, base: int = 1) -> tuple:
    stati = {}
    toccate = []
    for i in range(n):
        lid = str(base + i)
        stati[lid] = {"league_name": f"Lega {lid}", "n_fixtures": 1, "last_fixture_date": None,
                     "updated_at": "2026-09-28T07:13:00+00:00", "fixtures": [i]}
        toccate.append(lid)
    return stati, toccate


# --------------------------------------------------- 1) _req: ritentativi
def test_req_ritenta_su_500_e_va_a_buon_fine(monkeypatch: pytest.MonkeyPatch) -> None:
    """500 poi 500 poi 200: due attese, poi la scrittura passa (era: un solo
    500 rendeva rossa l'intera run, vedi run 36390445058)."""
    finto = UrlopenFinto([_http_error(500), _http_error(500), None])
    monkeypatch.setattr(urllib.request, "urlopen", finto)
    sonno = _sonno_finto()
    s = G._Scrittore("http://finto", "k", attese=(1.0, 2.0, 3.0), sleep=sonno)
    s._req("POST", "hazard_atlas", {"a": 1}, "return=minimal")   # non deve alzare
    assert len(finto.chiamate) == 3
    assert sonno.attese == [1.0, 2.0]                            # due attese, poi ok


def test_req_non_ritenta_su_4xx(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un 4xx e' un dato/richiesta invalidi (deterministico): niente attesa,
    si propaga SUBITO (ritentare non lo aggiusterebbe)."""
    finto = UrlopenFinto([_http_error(400, b'{"message":"bad request"}')])
    monkeypatch.setattr(urllib.request, "urlopen", finto)
    sonno = _sonno_finto()
    s = G._Scrittore("http://finto", "k", attese=(1.0, 2.0), sleep=sonno)
    with pytest.raises(urllib.error.HTTPError) as ex:
        s._req("POST", "hazard_atlas", {"a": 1})
    assert ex.value.code == 400
    assert len(finto.chiamate) == 1
    assert sonno.attese == []


def test_req_esaurisce_i_tentativi_e_rialza(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sempre 500: dopo tutte le attese si rialza (non un silenzio)."""
    finto = UrlopenFinto([_http_error(500)])
    monkeypatch.setattr(urllib.request, "urlopen", finto)
    sonno = _sonno_finto()
    s = G._Scrittore("http://finto", "k", attese=(1.0, 2.0), sleep=sonno)
    with pytest.raises(urllib.error.HTTPError) as ex:
        s._req("POST", "hazard_atlas", {"a": 1})
    assert ex.value.code == 500
    assert len(finto.chiamate) == 3                               # 1 + 2 ritentativi
    assert sonno.attese == [1.0, 2.0]


# ------------------------------------------------ 2) salva_leghe a blocchi
def test_salva_leghe_un_blocco_ko_non_ferma_gli_altri(monkeypatch: pytest.MonkeyPatch) -> None:
    """45 leghe -> 3 blocchi (20/20/5). Il blocco DI MEZZO resta sempre KO
    (500): i blocchi 1 e 3 si scrivono comunque (R-28-2: 'una lega che
    fallisce non ferma le altre'), e alla fine si alza
    ScritturaLegheParziale con l'elenco ESATTO delle 20 leghe non scritte."""
    stati, toccate = _stati_toccate(45)
    # blocco1 ok (chiamata 0); blocco2 KO sui suoi 2 tentativi (attese=(0.1,)
    # -> 1 ritentativo: chiamate 1 e 2); blocco3 ok (chiamata 3)
    esiti = [None, _http_error(500), _http_error(500), None]
    finto = UrlopenFinto(esiti)
    monkeypatch.setattr(urllib.request, "urlopen", finto)
    sonno = _sonno_finto()
    s = G._Scrittore("http://finto", "k", attese=(0.1,), sleep=sonno)
    with pytest.raises(G.ScritturaLegheParziale) as ex:
        s.salva_leghe(stati, toccate)
    assert ex.value.non_scritte == toccate[20:40]                 # blocco di mezzo, per intero
    assert ex.value.scritte == 25                                 # 20 (blocco1) + 5 (blocco3)
    # 3 blocchi tentati: blocco2 ritenta 1 volta (attese=(0.1,)) e resta KO
    percorsi = [c["path"].split("?")[0] for c in finto.chiamate]
    assert percorsi.count("hazard_atlas_leghe") == 4               # 1+2(ritentativo)+1


def test_salva_leghe_tutto_ok_ritorna_le_righe_come_prima(monkeypatch: pytest.MonkeyPatch) -> None:
    """Contratto INVARIATO per chi non fallisce mai (atlante_a_domanda.py
    legge un ``int``, non una tupla): nessuna riscrittura dei chiamanti."""
    stati, toccate = _stati_toccate(3)
    finto = UrlopenFinto([None])
    monkeypatch.setattr(urllib.request, "urlopen", finto)
    s = G._Scrittore("http://finto", "k", attese=(), sleep=lambda s: None)
    scritte = s.salva_leghe(stati, toccate)
    assert scritte == 3
    assert isinstance(scritte, int)


# ------------------------------------------- 3) _scrivi_riga: RPC + ripiego
def test_scrivi_riga_usa_la_rpc_se_c_e(monkeypatch: pytest.MonkeyPatch) -> None:
    """Punto 2 del coordinatore (28/09): la riga globale e' 14+ MB di testo
    JSON (misura reale sul DB, 27/09) sotto 8 s di statement_timeout: si usa
    PRIMA la RPC dedicata (statement_timeout piu' alto, SOLO per questa
    scrittura, migrations/hazard_atlas_rpc_scrittura_2026-09-28.sql)."""
    finto = UrlopenFinto([None])   # la RPC risponde subito ok
    monkeypatch.setattr(urllib.request, "urlopen", finto)
    s = G._Scrittore("http://finto", "k", attese=(), sleep=lambda s: None)
    s._scrivi_riga("2026-09-28T07:13:00+00:00", 185, 12345, 999, _atlas(185))
    assert len(finto.chiamate) == 1
    c = finto.chiamate[0]
    assert c["metodo"] == "POST" and c["path"] == "rpc/hazard_atlas_salva_versione"
    assert c["corpo"]["p_generated_at"] == "2026-09-28T07:13:00+00:00"
    assert c["corpo"]["p_n_leghe"] == 185 and c["corpo"]["p_watermark_event_id"] == 999
    assert c["corpo"]["p_payload"] == _atlas(185)


def test_scrivi_riga_ripiega_sulla_post_diretta_se_manca_la_rpc(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Migrazione NON ancora applicata (RPC assente -> 404, PGRST202/42883):
    si ripiega SUBITO sulla POST diretta di oggi, stesso corpo/chiavi di
    prima (``generated_at``, ``n_leghe``, ..., ``payload``). Il codice puo'
    andare su master prima che l'utente applichi la migrazione."""
    finto = UrlopenFinto([_http_error(404, b'{"code":"PGRST202","message":"function not found"}'),
                          None])
    monkeypatch.setattr(urllib.request, "urlopen", finto)
    s = G._Scrittore("http://finto", "k", attese=(), sleep=lambda s: None)
    atlas = _atlas(185)
    s._scrivi_riga("2026-09-28T07:13:00+00:00", 185, 12345, 999, atlas)
    assert len(finto.chiamate) == 2
    assert finto.chiamate[0]["path"] == "rpc/hazard_atlas_salva_versione"
    ripiego = finto.chiamate[1]
    assert ripiego["metodo"] == "POST" and ripiego["path"] == "hazard_atlas"
    assert ripiego["corpo"] == {"generated_at": "2026-09-28T07:13:00+00:00", "n_leghe": 185,
                                "n_partite": 12345, "watermark_event_id": 999, "payload": atlas}


def test_scrivi_riga_rpc_500_ritenta_e_non_ripiega_subito(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un 500 sulla RPC (es. il payload sfora anche i 120 s dedicati, o un
    guasto transitorio) si ritenta SULLA RPC (stessa politica di ``_req``),
    NON si ripiega alla cieca sulla POST diretta: solo un 404 (migrazione
    assente) fa ripiegare."""
    finto = UrlopenFinto([_http_error(500), None])   # RPC KO poi RPC ok (ritentativo)
    monkeypatch.setattr(urllib.request, "urlopen", finto)
    sonno = _sonno_finto()
    s = G._Scrittore("http://finto", "k", attese=(0.1,), sleep=sonno)
    s._scrivi_riga("g", 1, 1, 1, _atlas())
    assert len(finto.chiamate) == 2
    assert all(c["path"] == "rpc/hazard_atlas_salva_versione" for c in finto.chiamate)
    assert sonno.attese == [0.1]


def test_scrivi_riga_rpc_500_esaurito_non_ripiega_alla_cieca(monkeypatch: pytest.MonkeyPatch) -> None:
    """Con i ritentativi della RPC esauriti (500 persistente), l'errore deve
    uscire cosi' com'e' (nessun ripiego): un ripiego su QUALSIASI errore
    (non solo il 404 di RPC assente) nasconderebbe in silenzio un 500 vero
    dietro una scrittura diretta riuscita per caso, mascherando il guasto
    reale della RPC. Con ``attese=()`` la RPC fallisce in un solo tentativo
    e non deve mai arrivare a toccare ``hazard_atlas`` in POST diretta."""
    finto = UrlopenFinto([_http_error(500), None])   # la seconda entry (POST diretta) NON va usata
    monkeypatch.setattr(urllib.request, "urlopen", finto)
    s = G._Scrittore("http://finto", "k", attese=(), sleep=lambda s: None)
    with pytest.raises(urllib.error.HTTPError) as ex:
        s._scrivi_riga("g", 1, 1, 1, _atlas())
    assert ex.value.code == 500
    assert len(finto.chiamate) == 1                   # nessun ripiego tentato
    assert finto.chiamate[0]["path"] == "rpc/hazard_atlas_salva_versione"


# --------------------------------------------------- 4) salva_versione
def test_salva_versione_pulizia_lettura_ko_non_blocca(monkeypatch: pytest.MonkeyPatch) -> None:
    """La RPC/POST buona (riga nuova) passa; la GET di pulizia delle
    versioni vecchie resta sempre KO: e' manutenzione, non deve far sparire
    la scrittura appena fatta ne' far fallire il run."""
    finto = UrlopenFinto([None, _http_error(500)])   # riga ok, poi GET pulizia sempre KO
    monkeypatch.setattr(urllib.request, "urlopen", finto)
    sonno = _sonno_finto()
    s = G._Scrittore("http://finto", "k", attese=(0.1,), sleep=sonno)
    s.salva_versione(_atlas(), tieni=7)                # non deve alzare
    metodi = [c["metodo"] for c in finto.chiamate]
    assert metodi[0] == "POST"
    assert "GET" in metodi


def test_salva_versione_pulizia_delete_ko_non_blocca(monkeypatch: pytest.MonkeyPatch) -> None:
    """La GET di pulizia TROVA 2 versioni vecchie da cancellare; la DELETE
    della prima (e della seconda) resta sempre KO: non deve alzare (la
    scrittura buona e' gia' fatta), e la seconda DELETE si tenta comunque
    (un blocco KO non ferma gli altri, stesso principio di salva_leghe).
    Falsificato dal coordinatore: un ``raise`` messo prima del
    ``logger.warning`` nel ramo DELETE lasciava 13/13 test verdi -> qui si
    chiude il buco."""
    vecchie_json = json.dumps([{"id": 1}, {"id": 2}]).encode("utf-8")
    # 0: riga nuova (RPC) ok - 1: GET pulizia (2 righe) - 2: DELETE id=1 KO - 3: DELETE id=2 KO
    finto = UrlopenFinto([None, vecchie_json, _http_error(500), _http_error(500)])
    monkeypatch.setattr(urllib.request, "urlopen", finto)
    s = G._Scrittore("http://finto", "k", attese=(), sleep=lambda s: None)
    s.salva_versione(_atlas(), tieni=7)                # non deve alzare
    metodi_path = [(c["metodo"], c["path"].split("?")[0]) for c in finto.chiamate]
    assert metodi_path == [("POST", "rpc/hazard_atlas_salva_versione"), ("GET", "hazard_atlas"),
                           ("DELETE", "hazard_atlas"), ("DELETE", "hazard_atlas")]


def test_salva_versione_scrive_il_payload_intero_atomico(monkeypatch: pytest.MonkeyPatch) -> None:
    finto = UrlopenFinto([None, None])   # riga ok (RPC), GET pulizia 0 righe
    monkeypatch.setattr(urllib.request, "urlopen", finto)
    s = G._Scrittore("http://finto", "k", attese=(), sleep=lambda s: None)
    atlas = _atlas(n_leagues=185)
    s.salva_versione(atlas, tieni=7)
    prima = finto.chiamate[0]
    assert prima["metodo"] == "POST" and prima["path"] == "rpc/hazard_atlas_salva_versione"
    assert prima["corpo"]["p_payload"] == atlas
    assert prima["corpo"]["p_n_leghe"] == 185


# --------------------------------------------------- 5) salva: rosso solo se resta KO
def test_salva_prova_comunque_la_versione_globale_se_una_lega_e_ko(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """R-28-2: anche con leghe rimaste KO, la versione globale (che fa
    avanzare la filigrana) si tenta comunque."""
    stati, toccate = _stati_toccate(5)
    # blocco leghe (1 sola POST, 5 righe < 20) sempre KO; poi riga versione ok
    finto = UrlopenFinto([_http_error(500), None])
    monkeypatch.setattr(urllib.request, "urlopen", finto)
    s = G._Scrittore("http://finto", "k", attese=(), sleep=lambda s: None)
    non_scritte = s.salva(stati, toccate, _atlas(), tieni=7)
    assert non_scritte == toccate                                  # le 5 leghe, elenco esatto
    percorsi = [c["path"].split("?")[0] for c in finto.chiamate]
    assert "rpc/hazard_atlas_salva_versione" in percorsi            # versione tentata comunque


def test_salva_pulizia_lettura_ko_non_conta_come_non_scritto(monkeypatch: pytest.MonkeyPatch) -> None:
    """La pulizia (lettura delle versioni vecchie) fallita NON deve mai
    contare come 'non scritta': la scrittura vera e propria e' gia' andata a
    buon fine. Falsificato: un ``raise`` al posto del ``logger.warning`` nel
    ramo di lettura fa rientrare l'errore in ``salva()`` come
    ``versione_globale`` KO, anche se la riga e' stata scritta."""
    stati, toccate = _stati_toccate(0)
    finto = UrlopenFinto([None, _http_error(500)])   # riga ok, GET pulizia sempre KO
    monkeypatch.setattr(urllib.request, "urlopen", finto)
    s = G._Scrittore("http://finto", "k", attese=(), sleep=lambda s: None)
    non_scritte = s.salva(stati, toccate, _atlas(), tieni=7)
    assert non_scritte == []


def test_salva_pulizia_delete_ko_non_conta_come_non_scritto(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stessa cosa per il ramo DELETE: la pulizia fallita non deve mai
    trasformarsi in un 'versione_globale' non scritta."""
    stati, toccate = _stati_toccate(0)
    vecchie_json = json.dumps([{"id": 5}]).encode("utf-8")
    finto = UrlopenFinto([None, vecchie_json, _http_error(500)])
    monkeypatch.setattr(urllib.request, "urlopen", finto)
    s = G._Scrittore("http://finto", "k", attese=(), sleep=lambda s: None)
    non_scritte = s.salva(stati, toccate, _atlas(), tieni=7)
    assert non_scritte == []


def test_salva_tutto_ok_non_scritte_vuoto(monkeypatch: pytest.MonkeyPatch) -> None:
    stati, toccate = _stati_toccate(3)
    finto = UrlopenFinto([None, None, None])
    monkeypatch.setattr(urllib.request, "urlopen", finto)
    s = G._Scrittore("http://finto", "k", attese=(), sleep=lambda s: None)
    non_scritte = s.salva(stati, toccate, _atlas(), tieni=7)
    assert non_scritte == []


def test_salva_versione_globale_ko_si_dichiara_in_non_scritte(
        monkeypatch: pytest.MonkeyPatch) -> None:
    stati, toccate = _stati_toccate(2)
    finto = UrlopenFinto([None, _http_error(500)])   # leghe ok, versione globale sempre KO
    monkeypatch.setattr(urllib.request, "urlopen", finto)
    s = G._Scrittore("http://finto", "k", attese=(), sleep=lambda s: None)
    non_scritte = s.salva(stati, toccate, _atlas(), tieni=7)
    assert non_scritte == ["versione_globale"]


# --------------------------------------------------- 5) main(): rosso/verde
def _finto_stato_db_vuoto(monkeypatch: pytest.MonkeyPatch, *, watermark: int = 500) -> None:
    """L'incrementale di main() legge da leggi_stato_db/LettoreDB.tutte: qui
    lo forziamo a "niente di nuovo" cosi' il test isola SOLO la scrittura."""
    monkeypatch.setattr(G, "leggi_stato_db", lambda lettore: ({}, watermark))
    monkeypatch.setattr(G, "incrementale",
                        lambda lettore, stati, wm, nomi, adesso, **kw: (wm, {}, []))


class _ScrittoreFinto:
    """Stub di ``_Scrittore`` per i test di ``main()``: qui NON si ritesta la
    politica dei ritentativi (gia' coperta sopra, con ``sleep`` finto
    iniettato nel costruttore vero); si testa SOLO che ``main()`` decida
    verde/rosso in base a cio' che ``salva()`` ritorna, senza alcuna attesa
    reale (il costruttore di ``_Scrittore`` lega ``sleep=time.sleep`` come
    default al MOMENTO dell'import: un ``monkeypatch`` su ``time.sleep`` dopo
    non lo tocca piu', quindi qui si sostituisce la classe intera)."""

    ultima_istanza: "Optional[_ScrittoreFinto]" = None

    def __init__(self, url: str, key: str) -> None:
        self.url, self.key = url, key
        _ScrittoreFinto.ultima_istanza = self

    def salva(self, stati: Any, toccate: Any, atlas: Any, tieni: int = 7) -> List[str]:
        return _ScrittoreFinto.RISPOSTA


def test_main_verde_se_i_ritentativi_bastano(monkeypatch: pytest.MonkeyPatch,
                                             capsys: pytest.CaptureFixture) -> None:
    """``salva()`` e' arrivata in fondo senza niente di irrisolto (i
    ritentativi sono bastati, o non serviva scrivere nulla): la run resta
    VERDE (era: un solo 500 sulla POST unica rendeva rossa TUTTA la run,
    run 36390445058)."""
    monkeypatch.setenv("SUPABASE_URL", "http://finto")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "k")
    _finto_stato_db_vuoto(monkeypatch)
    _ScrittoreFinto.RISPOSTA = []
    monkeypatch.setattr(G, "_Scrittore", _ScrittoreFinto)
    rc = G.main(["--stato-db", "--incrementale", "--solo-leghe-in-stato", "--scrivi-db"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["leghe_non_scritte"] == []


def test_main_rosso_solo_se_resta_qualcosa_non_scritto(monkeypatch: pytest.MonkeyPatch,
                                                        capsys: pytest.CaptureFixture) -> None:
    """Dopo TUTTI i ritentativi resta davvero qualcosa di non aggiornato:
    SOLO allora la run e' rossa, con l'elenco esatto nel log/riepilogo."""
    monkeypatch.setenv("SUPABASE_URL", "http://finto")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "k")
    _finto_stato_db_vuoto(monkeypatch)
    _ScrittoreFinto.RISPOSTA = ["versione_globale"]
    monkeypatch.setattr(G, "_Scrittore", _ScrittoreFinto)
    rc = G.main(["--stato-db", "--incrementale", "--solo-leghe-in-stato", "--scrivi-db"])
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert out["leghe_non_scritte"] == ["versione_globale"]


def test_main_senza_scrivi_db_non_chiama_lo_scrittore(monkeypatch: pytest.MonkeyPatch,
                                                       capsys: pytest.CaptureFixture) -> None:
    """Senza ``--scrivi-db`` (uso locale/sviluppo) non si tocca il DB in
    scrittura: verde, elenco vuoto, nessuna istanza creata."""
    monkeypatch.setenv("SUPABASE_URL", "http://finto")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "k")
    _finto_stato_db_vuoto(monkeypatch)
    _ScrittoreFinto.ultima_istanza = None
    monkeypatch.setattr(G, "_Scrittore", _ScrittoreFinto)
    rc = G.main(["--stato-db", "--incrementale", "--solo-leghe-in-stato"])
    assert rc == 0
    assert _ScrittoreFinto.ultima_istanza is None
    out = json.loads(capsys.readouterr().out)
    assert out["leghe_non_scritte"] == []
