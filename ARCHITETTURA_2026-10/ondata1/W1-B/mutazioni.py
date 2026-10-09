"""Mutazioni di W1-G2: rompe il codice, lancia i test, ripristina e controlla lo sha256."""
import hashlib
import subprocess
import sys
from pathlib import Path

R = Path(sys.argv[1])
D = R / "Betfair/nucleo/dati"
T = "Betfair/nucleo/dati/tests/"

M = [
    ("M1 cloud: ritenta qualunque errore (anche 4xx)", "cloud.py",
     "        return _db().con_ritentativi(lambda: costruisci(self._client()).execute(), etichetta=etichetta,",
     "        for _i in range(len(self._politica.attese_s)):\n            try:\n                return costruisci(self._client()).execute()\n            except Exception:\n                pass\n        return _db().con_ritentativi(lambda: costruisci(self._client()).execute(), etichetta=etichetta,",
     T + "test_g2_cloud.py"),
    ("M2 cloud: ritenta il 57014", "cloud.py",
     "        return _db().con_ritentativi(lambda: costruisci(self._client()).execute(), etichetta=etichetta,",
     "        for _i in range(len(self._politica.attese_s)):\n            try:\n                return costruisci(self._client()).execute()\n            except Exception as e:\n                if '57014' not in str(getattr(e, 'code', '')):\n                    raise\n        return _db().con_ritentativi(lambda: costruisci(self._client()).execute(), etichetta=etichetta,",
     T + "test_g2_cloud.py"),
    ("M3 cloud: ritenta l'insert", "cloud.py",
     'risposta = self._esegui(costruisci, f"{op} {tabella}", op == "upsert")',
     'risposta = self._esegui(costruisci, f"{op} {tabella}", op in ("upsert", "insert"))',
     T + "test_g2_cloud.py"),
    ("M4 cloud: ritenta le RPC che scrivono", "cloud.py",
     "        if self._registro.rpc_scrive(nome) or nome in db.RPC_NON_IDEMPOTENTI:\n            return False",
     "        return True",
     T + "test_g2_cloud.py"),
    ("M4b cloud: ignora il registro delle RPC scriventi", "cloud.py",
     "        if self._registro.rpc_scrive(nome) or nome in db.RPC_NON_IDEMPOTENTI:",
     "        if nome in db.RPC_NON_IDEMPOTENTI:", T + "test_g2_cloud.py"),
    ("M5 cloud: cache senza scadenza", "cloud.py",
     "            if self._orologio() >= voce[0]:", "            if False:", T + "test_g2_cloud.py"),
    ("M6 registro: tolta la riga di mike_activity", "registro.py",
     '    _v("mike_activity", "T09", "ARC", "log", "L+P", R_LOG, (), domani=D_LOG, verifica=V_LOG),\n', "",
     T + "test_g2_registro.py"),
    ("M7 registro: tolto il sito dinamico di season_aggregates", "registro.py",
     '    SitoDinamico("season_aggregates.py", "<dinamico:nome>", (229, 238),',
     '    SitoDinamico("season_aggregates_X.py", "<dinamico:nome>", (229, 238),', T + "test_g2_registro.py"),
    ("M8 registro: RPC refresh_analytics_bets_range senza book_odds_cache", "registro.py",
     '    _r("refresh_analytics_bets_range", ("analytics_bets", "book_odds_cache", "book_odds_cache_fonte"),',
     '    _r("refresh_analytics_bets_range", ("analytics_bets", "book_odds_cache_fonte"),', T + "test_g2_registro.py"),
    ("M9 registro: dipende_da di live_now vuoto", "registro.py",
     '    _v("live_now", "T08", "SV", "stato_vivo", "L+P", R_LADDER, ("event_id",), coalesce=True, rev=_UA,\n       dipende=_FOLLOW,',
     '    _v("live_now", "T08", "SV", "stato_vivo", "L+P", R_LADDER, ("event_id",), coalesce=True, rev=_UA,\n       dipende=(),',
     T + "test_g2_registro.py"),
    ("M10 cache: replica mai riletta dopo built_at", "cache_cloud.py",
     "        if vecchio == nuovo:\n            return False", "        if True:\n            return False",
     T + "test_g2_cache_cloud.py"),
    ("M11 cache: errore del prefetch messo in cache come []", "cache_cloud.py",
     "                if righe is None:\n                    self._conti[\"errori\"] += 1\n                else:\n                    self._righe[chiave] = righe",
     "                self._righe[chiave] = righe if righe is not None else []",
     T + "test_g2_cache_cloud.py"),
    ("M12 cache: lambda > 0 diventa >= 0", "cache_cloud.py",
     "float(lh) > 0 and float(la) > 0", "float(lh) >= 0 and float(la) >= 0", T + "test_g2_cache_cloud.py"),
    ("M13 cache: ponte con omega_events prima di live_follow", "cache_cloud.py",
     '        for tabella in ("live_follow", "omega_events"):', '        for tabella in ("omega_events", "live_follow"):',
     T + "test_g2_cache_cloud.py"),
    ("M14 cache: la replica restituisce la sua memoria senza copia", "cache_cloud.py",
     "                self._conti[\"colpi\"] += 1\n                return _copia(righe)",
     "                self._conti[\"colpi\"] += 1\n                return righe", T + "test_g2_cache_cloud.py"),
    ("M15 cache: bucket FT fino a 80", "cache_cloud.py",
     "BUCKET_FT: Tuple[int, ...] = tuple(range(0, 86, 5))", "BUCKET_FT: Tuple[int, ...] = tuple(range(0, 81, 5))",
     T + "test_g2_cache_cloud.py"),
    ("M16 cache: dossier mette in memoria anche dopo un errore", "cache_cloud.py",
     "            if not ok:\n                return out", "            if not ok:\n                continue",
     T + "test_g2_cache_cloud.py"),
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


rossi = 0
for nome, f, vecchio, nuovo, test in M:
    p = D / f
    originale = p.read_bytes()
    h0 = sha(p)
    testo = originale.decode()
    assert testo.count(vecchio) == 1, (nome, testo.count(vecchio))
    p.write_text(testo.replace(vecchio, nuovo))
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", test, "-q", "-p", "no:cacheprovider", "-x"],
                           cwd=R, capture_output=True, text=True, timeout=900)
        riga = [x for x in r.stdout.splitlines() if " passed" in x or " failed" in x or "error" in x][-1:]
    finally:
        p.write_bytes(originale)
    ok = sha(p) == h0
    rosso = r.returncode != 0
    rossi += rosso
    print(f"{'ROSSO' if rosso else 'VERDE!!'} | {nome} | {riga[0] if riga else '?'} | ripristino sha256 {'uguale' if ok else 'DIVERSO'} {h0[:12]}")
print(f"mutazioni rosse {rossi}/{len(M)}")
