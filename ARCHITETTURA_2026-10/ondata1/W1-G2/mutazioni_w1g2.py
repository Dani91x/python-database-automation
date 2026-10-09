"""Mutazioni di W1-G2: rompe il codice, lancia i test, ripristina e controlla lo sha256.

Uso: python ARCHITETTURA_2026-10/ondata1/W1-G2/mutazioni_w1g2.py <radice del repo>
Ogni mutazione e' una lista di sostituzioni (vecchio -> nuovo) che devono comparire UNA volta.
"""
import hashlib
import subprocess
import sys
from pathlib import Path

R = Path(sys.argv[1])
D = R / "Betfair/nucleo/dati"
T = "Betfair/nucleo/dati/tests/"
TC, TR, TK = T + "test_g2_cloud.py", T + "test_g2_registro.py", T + "test_g2_cache_cloud.py"
RIT = "        return _db().con_ritentativi(lambda: costruisci(self._client()).execute(), etichetta=etichetta,"

M = [
    ("M1 cloud: ritenta qualunque errore (anche 4xx)", "cloud.py", [(RIT,
     "        for _i in range(len(self._politica.attese_s)):\n            try:\n                return costruisci(self._client()).execute()\n            except Exception:\n                pass\n" + RIT)], TC),
    ("M2 cloud: ritenta il 57014", "cloud.py", [(RIT,
     "        for _i in range(len(self._politica.attese_s)):\n            try:\n                return costruisci(self._client()).execute()\n            except Exception as e:\n                if '57014' not in str(getattr(e, 'code', '')):\n                    raise\n" + RIT)], TC),
    ("M3 cloud: ritenta l'insert", "cloud.py",
     [('ritenta = op == "upsert" and self.upsert_ritentabile(tabella, on_conflict, ignora_duplicati)',
       'ritenta = op in ("upsert", "insert")')], TC),
    ("M4 cloud: ritenta le RPC che scrivono", "cloud.py",
     [("        if self._registro.rpc_scrive(nome) or nome in db.RPC_NON_IDEMPOTENTI:\n            return False",
       "        return True")], TC),
    ("M4b cloud: ignora il registro delle RPC scriventi", "cloud.py",
     [("        if self._registro.rpc_scrive(nome) or nome in db.RPC_NON_IDEMPOTENTI:",
       "        if nome in db.RPC_NON_IDEMPOTENTI:")], TC),
    ("M5 cloud: cache senza scadenza", "cloud.py", [("            if self._orologio() >= voce[0]:", "            if False:")], TC),
    ("M6 registro: tolta la riga di mike_activity", "registro.py",
     [('    _v("mike_activity", "T09", "ARC", "log", "L+P", R_LOG, (), domani=D_LOG, verifica=V_LOG),\n', "")], TR),
    ("M7 registro: tolto il sito dinamico di season_aggregates", "registro.py",
     [('    SitoDinamico("season_aggregates.py", "<dinamico:nome>", (229, 238),',
       '    SitoDinamico("season_aggregates_X.py", "<dinamico:nome>", (229, 238),')], TR),
    ("M8 registro: RPC refresh_analytics_bets_range senza book_odds_cache", "registro.py",
     [('    _r("refresh_analytics_bets_range", ("analytics_bets", "book_odds_cache", "book_odds_cache_fonte"),',
       '    _r("refresh_analytics_bets_range", ("analytics_bets", "book_odds_cache_fonte"),')], TR),
    ("M9 registro: dipende_da di live_now vuoto", "registro.py",
     [('    _v("live_now", "T08", "SV", "stato_vivo", "L+P", R_LADDER, ("event_id",), coalesce=True, rev=_UA,\n       dipende=_FOLLOW,',
       '    _v("live_now", "T08", "SV", "stato_vivo", "L+P", R_LADDER, ("event_id",), coalesce=True, rev=_UA,\n       dipende=(),')], TR),
    ("M10 cache: replica mai riletta dopo la sentinella", "cache_cloud.py",
     [("                if vecchia is None:\n                    return False", "                return False")], TK),
    ("M11 cache: errore del prefetch messo in cache come []", "cache_cloud.py",
     [('            if righe is None:\n                self._conti["errori"] += 1\n                return False',
       '            if righe is None:\n                righe = []')], TK),
    ("M12 cache: lambda > 0 diventa >= 0", "cache_cloud.py",
     [("float(lh) > 0 and float(la) > 0", "float(lh) >= 0 and float(la) >= 0")], TK),
    ("M13 cache: ponte con omega_events prima di live_follow", "cache_cloud.py",
     [('        for tabella in ("live_follow", "omega_events"):', '        for tabella in ("omega_events", "live_follow"):')], TK),
    ("M14 cache: la replica restituisce la sua memoria senza copia", "cache_cloud.py",
     [("                return _copia(voce[1])", "                return voce[1]")], TK),
    ("M15 cache: bucket FT fino a 80", "cache_cloud.py",
     [("BUCKET_FT: Tuple[int, ...] = tuple(range(0, 86, 5))", "BUCKET_FT: Tuple[int, ...] = tuple(range(0, 81, 5))")], TK),
    ("M16 cache: dossier in memoria anche dopo un errore", "cache_cloud.py",
     [("            if not ok:\n                return out", "            if not ok:\n                continue")], TK),
    # --- revisione del 09/10
    ("M17 D-2: negativi del dossier in memoria", "cache_cloud.py",
     [("and lambdas_da_riga(r)[0] is not None:", ":")], TK),
    ("M18 D-2: scadenza del dossier 3600 s", "cache_cloud.py",
     [("SCADENZA_DOSSIER_S = 300.0", "SCADENZA_DOSSIER_S = 3600.0")], TK),
    ("M18b D-2: scadenza del dossier 36000 s (mutazione del revisore)", "cache_cloud.py",
     [("SCADENZA_DOSSIER_S = 300.0", "SCADENZA_DOSSIER_S = 36000.0")], TK),
    ("M19 D-3: upsert senza on_conflict ritentato", "cloud.py",
     [("        if not colonne:\n            return False", "        if not colonne:\n            return True")], TC),
    ("M19b D-3: upsert ritentato su qualunque on_conflict", "cloud.py",
     [("        return colonne == self._registro.spec(tabella).chiave_naturale", "        return True")], TC),
    ("M20 D-4: chiave mancante mai richiesta di nuovo", "cache_cloud.py",
     [("        self.richiedi_prefetch(lega, forza=False)      # lega nuova o chiave mancante: di nuovo",
       "        pass")], TK),
    ("M21 D-5: sentinella solo su omega_ht_ft_transitions", "cache_cloud.py",
     [('        letture = (("omega_transitions_state", {"select": "updated_at,published_at", "id": 1}),\n                   (',
       '        letture = ((')], TK),
    ("M22 D-6: rilettura che sostituisce (perde le leghe preparate nel frattempo)", "cache_cloud.py",
     [("                for chiave in [k for k, (g, _) in self._righe.items() if g < gen]:",
       "                for chiave in [k for k in self._righe if k[1] not in leghe or self._righe[k][0] < gen]:")], TK),
    ("M23 D-6: scrittura di una generazione vecchia accettata", "cache_cloud.py",
     [("            if gen != self._gen:", "            if False:")], TK),
    ("M24 D-7: cache non invalidata dopo scrivi", "cloud.py",
     [("            self._cache.svuota_tabella(tabella)       # anche su errore: l'esito puo' essere ambiguo",
       "            pass")], TC),
    ("M25 D-7: filtri di patch/delete solo eq/in", "cloud.py",
     [('            return applica_filtri(t.update(righe) if op == "patch" else t.delete(), filtri or {})',
       '            q = t.update(righe) if op == "patch" else t.delete()\n            for colonna, valore in (filtri or {}).items():\n                q = q.in_(colonna, list(valore)) if isinstance(valore, (list, tuple, set)) else q.eq(colonna, valore)\n            return q')], TC),
    ("M26 D-1: refresh_analytics_riepilogo dichiarata di sola lettura (mutazione del revisore)", "registro.py",
     [('    "monitor_salute_stato": "migrations/monitor_metrics_2026-10-09.sql:73, solo SELECT (T0A)",',
       '    "refresh_analytics_riepilogo": "mutazione",\n    "monitor_salute_stato": "migrations/monitor_metrics_2026-10-09.sql:73, solo SELECT (T0A)",'),
      ('    _r("refresh_analytics_riepilogo", (', '    _r("refresh_analytics_riepilogo_TOLTA", (')], TR),
    ("M27 D-1: tolta lanci_action (scritta dal pg_cron)", "registro.py",
     [('    _v("lanci_action",', '    _v("lanci_action_TOLTA",')], TR),
    ("M28 D-1: tolto un sito Storage", "registro.py",
     [('    SitoDinamico("cleanup_models.py", "<dinamico:name>", (53, 64), (BUCKET_MODELLI,),',
       '    SitoDinamico("cleanup_models_X.py", "<dinamico:name>", (53, 64), (BUCKET_MODELLI,),')], TR),
    ("M29 D-10 (K): rev_colonna di live_ladder tolto", "registro.py",
     [('       rev=_UA, dipende=_FOLLOW, domani="nucleo/betfair via postino (coalescente)",\n       note="indice UNIQUE',
       '       rev=None, dipende=_FOLLOW, domani="nucleo/betfair via postino (coalescente)",\n       note="indice UNIQUE')], TR),
    ("M30 D-10 (L): ritardo di live_markets 5 s invece di 2 s", "registro.py",
     [('    _v("live_markets", "T08", "SV", "stato_vivo", "L+P", R_LADDER,',
       '    _v("live_markets", "T08", "SV", "stato_vivo", "L+P", R_STATO,')], TR),
    ("M31 D-10: chiave di live_markets ridotta a event_id", "registro.py",
     [('    _v("live_markets", "T08", "SV", "stato_vivo", "L+P", R_LADDER, ("event_id", "market_id"),',
       '    _v("live_markets", "T08", "SV", "stato_vivo", "L+P", R_LADDER, ("event_id",),')], TR),
    ("M32 D-10: leads marcata con schema nel repo", "registro.py",
     [('"fixture_predictions", "injuries", "leads",', '"fixture_predictions", "injuries",')], TR),
    # --- seconda revisione del 09/10 (punti 1, 3, 4, 5)
    ("M33 R2-1: Storage della Edge Function non dichiarato", "registro.py",
     [('    SitoDinamico("Telegram bot/supabase/functions/make-daily-post/index.ts", "Loghi", (253, 263), ("Loghi",),',
       '    SitoDinamico("Telegram bot/X/index.ts", "Loghi", (253, 263), ("Loghi",),')], TR),
    ("M34 R2-3: il dossier non pota le voci scadute", "cache_cloud.py",
     [("                for chiave in [k for k, (t, _) in memoria.items() if adesso - t >= self._scadenza]:",
       "                for chiave in [k for k, (t, _) in memoria.items() if False]:")], TK),
    ("M35 R2-4: sentinella illeggibile per sempre cieca", "cache_cloud.py",
     [("                if self._errori_sentinella < SENTINELLA_ERRORI_MAX:", "                if True:")], TK),
    ("M36 R2-5: RPC in cache non svuotate dopo scrivi", "cloud.py",
     [('            for gruppo in (f"t:{tabella}", "r"):', '            for gruppo in (f"t:{tabella}",):'),
      ('k.startswith(prefisso) or k.startswith("r:")', "k.startswith(prefisso)")], TC),
    ("M37 R2-5: lettura in volo rimette in cache il vecchio", "cloud.py",
     [("            if self._generazioni.get(gruppo, 0) != generazione:\n                return False",
       "            if False:\n                return False")], TC),
    ("M38 R2-5: la cache non pota mai le scadute", "cloud.py",
     [("            if self._inserimenti % self.POTA_OGNI == 0:", "            if False:")], TC),
]

# Le 15 mutazioni del revisore (seconda revisione, scratchpad/rev_w1g2_2/mie_mutazioni.py), riprese tali e quali
M_REVISORE = [
    ("REV A1 D-2: _fresca non scade mai", [("            if voce is None or self._orologio() - voce[0] >= self._scadenza:", "            if voce is None:")]),
    ("REV A2 D-2: ponte/fixture negativi (tupla sempre non None)", [("and lambdas_da_riga(r)[0] is not None:", "and lambdas_da_riga(r) is not None:")]),
    ("REV A3 D-2: scadenza ignorata", [("        self._scadenza = float(scadenza_s)", "        self._scadenza = 1e12")]),
    ("REV B1 D-4: ritardo riprefetch infinito", [("RITARDO_RIPREFETCH_S = 60.0", "RITARDO_RIPREFETCH_S = 1e12")]),
    ("REV B2 D-4: ritardo 0", [("RITARDO_RIPREFETCH_S = 60.0", "RITARDO_RIPREFETCH_S = 0.0")]),
    ("REV B3 D-4: richiedi_incomplete non riaccoda", [("        incomplete = [lega for lega, n in per_lega.items() if n < CHIAVI_PER_LEGA]", "        incomplete = []")]),
    ("REV B4 D-4: ritardo 3600 s", [("RITARDO_RIPREFETCH_S = 60.0", "RITARDO_RIPREFETCH_S = 3600.0")]),
    ("REV C1 D-5: sentinella senza omega_transitions_state", [('        letture = (("omega_transitions_state", {"select": "updated_at,published_at", "id": 1}),\n                   (', '        letture = ((')]),
    ("REV C2 D-5: sentinella senza omega_ht_ft_transitions", [('                   ("omega_ht_ft_transitions", {"select": "built_at", "order": "built_at.desc", "limit": 1}),\n', '')]),
    ("REV C3 D-5: sentinella senza omega_build_jobs", [('                   ("omega_build_jobs", {"select": "job,updated_at", "order": "updated_at.desc", "limit": 1}))', '                   )')]),
    ("REV C4 D-5: sentinella ignora published_at", [('"select": "updated_at,published_at"', '"select": "updated_at"')]),
    ("REV D1 D-6: _servi memorizza con la generazione corrente", [("        self._memorizza(chiave, righe, gen)\n        return _copia(righe)", "        self._memorizza(chiave, righe, self._gen)\n        return _copia(righe)")]),
    ("REV D2 D-6: prefetch_lega memorizza con la generazione corrente", [("            self._memorizza(chiave, righe, gen)\n            lette += righe is not None", "            self._memorizza(chiave, righe, self._gen)\n            lette += righe is not None")]),
    ("REV D3 D-6: rilettura non toglie le voci vecchie", [("                for chiave in [k for k, (g, _) in self._righe.items() if g < gen]:\n                    del self._righe[chiave]", "                pass")]),
    ("REV D4 D-6: scarto solo se gen < corrente-1", [("            if gen != self._gen:\n                self._conti[\"scartate\"] += 1", "            if gen < self._gen - 1:\n                self._conti[\"scartate\"] += 1")]),
]
M += [(nome, "cache_cloud.py", sostituzioni, TK) for nome, sostituzioni in M_REVISORE]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


rossi = 0
for nome, f, sostituzioni, test in M:
    p = D / f
    originale = p.read_bytes()
    h0 = sha(p)
    testo = originale.decode()
    for vecchio, nuovo in sostituzioni:
        assert testo.count(vecchio) == 1, (nome, vecchio[:60], testo.count(vecchio))
        testo = testo.replace(vecchio, nuovo)
    p.write_text(testo)
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", test, "-q", "-p", "no:cacheprovider", "-x"],
                           cwd=R, capture_output=True, text=True, timeout=900)
        riga = [x for x in r.stdout.splitlines() if " passed" in x or " failed" in x or "error" in x][-1:]
    finally:
        p.write_bytes(originale)
    ok = sha(p) == h0
    rosso = r.returncode != 0
    rossi += rosso
    print(f"{'ROSSO' if rosso else 'VERDE!!'} | {nome} | {riga[0] if riga else '?'} | "
          f"ripristino sha256 {'uguale' if ok else 'DIVERSO'} {h0[:12]}")
print(f"mutazioni rosse {rossi}/{len(M)}")
