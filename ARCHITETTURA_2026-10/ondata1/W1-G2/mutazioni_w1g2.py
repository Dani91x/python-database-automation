"""Mutazioni di W1-G2: rompe il codice, lancia i test, ripristina e controlla lo sha256.

Uso: python ARCHITETTURA_2026-10/ondata1/W1-G2/mutazioni_w1g2.py <radice del repo>
(con G2_PG_PSQL="-h ... -p ... -U postgres" anche le mutazioni della migrazione, sul PostgreSQL usa-e-getta;
con MUTAZIONI_FILTRO=<prefisso> solo le mutazioni il cui nome inizia cosi')
Ogni mutazione e' una lista di sostituzioni (vecchio -> nuovo) che devono comparire UNA volta.
"""
import hashlib
import os
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

# --- decisione 10 dell'utente (10/10, agente D-G): dati calcolati dal cloud appena cambiano
TS = T + "test_g2_sorveglianza.py"
TP = T + "test_g2_pg_sentinella.py"            # solo con G2_PG_PSQL (PostgreSQL usa-e-getta)
MIG = "../../../migrations/nucleo_sentinella_cloud_2026-10-10.sql"
M += [
    ("D10-1 sorveglianza ogni 300 s invece di 5 s", "cache_cloud.py",
     [("INTERVALLO_RAPIDO_S = 5.0", "INTERVALLO_RAPIDO_S = 300.0")], TS),
    ("D10-2 ripiego REST ogni 300 s invece di 15 s", "cache_cloud.py",
     [("INTERVALLO_LETTURE_S = 15.0", "INTERVALLO_LETTURE_S = 300.0")], TS),
    ("D10-3 impronte mai confrontate (nessun cambio visto)", "cache_cloud.py",
     [("            cambiati = sorted(ev for ev, imp in nuove.items() if self._impronte.get(ev) != imp)",
       "            cambiati = []")], TS),
    ("D10-4 evento cambiato senza togliere le voci vecchie", "cache_cloud.py",
     [("                self._invalida(ev, _fixture_di_impronta(nuove[ev]))", "                pass")], TS),
    ("D10-5 lettura in volo della previsione rimette il vecchio", "cache_cloud.py",
     [('                    if self._gen.get(("f", int(fid)), 0) != gen_fixture[int(fid)]:',
       "                    if False:")], TS),
    ("D10-6 lettura in volo del ponte rimette il vecchio", "cache_cloud.py",
     [('                if self._gen.get(("e", ev), 0) != gen_eventi[ev]:', "                if False:")], TS),
    ("D10-7 rinnovo anche senza la versione del trigger (letture REST)", "cache_cloud.py",
     [('rinnova=ist.modo == "rpc",', "rinnova=True,")], TS),
    ("D10-8 nessun rinnovo con la RPC (rilettura ogni 300 s)", "cache_cloud.py",
     [("            if rinnova:\n", "            if False:\n")], TS),
    ("D10-9 impronta registrata anche se la rilettura fallisce", "cache_cloud.py",
     [('            if self._conti["errori"] != errori_prima:', "            if False:")], TS),
    ("D10-10 RPC assente trattata come errore (nessun ripiego REST)", "cache_cloud.py",
     [('                if str(getattr(ex, "code", "") or "") in CODICI_RPC_ASSENTE:', "                if False:")], TS),
    ("D10-11 RPC assente mai riprovata", "cache_cloud.py",
     [("            return self._rpc_assente_da is None or self._orologio() - self._rpc_assente_da >= self._riprova",
       "            return self._rpc_assente_da is None")], TS),
    ("D10-12 ogni errore della RPC fa passare alle letture", "cache_cloud.py",
     [('                self._conta("errori")\n                logger.warning("[cache_cloud] nucleo_sentinella_cloud KO: %s", str(ex)[:160])',
       "                self._segna_assente()\n                return None")], TS),
    ("D10-13 impronta di Omega della RPC in forma diversa dalle letture", "cache_cloud.py",
     [('        omega = "|".join(json.dumps(x[:1], sort_keys=True, default=str) for x in parti)',
       '        omega = "|".join(json.dumps(x[:1], default=str) for x in parti)')], TS),
    ("D10-14 errori di Omega consegnati a ogni giro (rilettura forzata dopo 15 s)", "cache_cloud.py",
     [("                if adesso - self._ultimo_errore_omega < INTERVALLO_SORVEGLIANZA_S:", "                if False:")], TS),
    ("D10-15 valore di Omega uguale riconsegnato a ogni giro", "cache_cloud.py",
     [("            elif valore == self._ultima_omega:\n                return False",
       "            elif False:\n                return False")], TS),
    ("D10-16 la replica ignora le notifiche (drena_coda)", "cache_cloud.py",
     [("                self.controlla_ricostruzione(sentinella=lega.valore)\n                continue",
       "                continue")], TS),
    ("D10-17 segui somma invece di sostituire", "cache_cloud.py",
     [("            self._seguiti = {str(e) for e in event_ids}", "            self._seguiti.update(str(e) for e in event_ids)")], TS),
    ("D10-18 precarica non segue gli eventi", "cache_cloud.py",
     [("            self._seguiti.update(eventi)\n", "            pass\n")], TS),
    ("D10-19 prendi_cambiati non consuma", "cache_cloud.py",
     [("            tutti, self._cambiati = tuple(sorted(self._cambiati)), set()",
       "            tutti = tuple(sorted(self._cambiati))")], TS),
    ("D10-20 letture REST senza updated_at nell'impronta", "cache_cloud.py",
     [("        return {ev: json.dumps([fid, fid in versioni, versioni.get(fid), grezzi",
       "        return {ev: json.dumps([fid, fid in versioni, None, grezzi")], TS),
    ("D10-21 blocco della RPC oltre il tetto di 500", "cache_cloud.py",
     [("BLOCCO_RPC = 500", "BLOCCO_RPC = 501")], TS),
    ("D10-22 registro: RPC della sentinella non dichiarata", "registro.py",
     [('    "nucleo_sentinella_cloud": "migrations/nucleo_sentinella_cloud_2026-10-10.sql:114, STABLE, solo SELECT "\n'
       '                               "(impronte per giro della Sorveglianza, cache_cloud.py)",\n', "")], TR),
    # migrazione: solo con G2_PG_PSQL (PostgreSQL usa-e-getta), altrimenti SALTATE e non contate
    ("D10-P1 trigger: versione nuova a ogni scrittura", MIG,
     [("        NEW.nucleo_versione := OLD.nucleo_versione;",
       "        NEW.nucleo_versione := nextval('public.nucleo_versione_dossier_seq');")], TP),
    ("D10-P2 trigger: db_json_analisi non guardata", MIG,
     [("    ELSIF (to_jsonb(NEW.tactical_engine_json), to_jsonb(NEW.db_json_analisi),",
       "    ELSIF (to_jsonb(NEW.tactical_engine_json), NULL::jsonb,"),
      ("          (to_jsonb(OLD.tactical_engine_json), to_jsonb(OLD.db_json_analisi),",
       "          (to_jsonb(OLD.tactical_engine_json), NULL::jsonb,")], TP),
    ("D10-P3 RPC: ponte con omega_events prima di live_follow", MIG,
     [("                   coalesce((SELECT l.fixture_id FROM public.live_follow l WHERE l.event_id = u.e),\n"
       "                            (SELECT o.fixture_id FROM public.omega_events o WHERE o.event_id = u.e)) AS fid",
       "                   coalesce((SELECT o.fixture_id FROM public.omega_events o WHERE o.event_id = u.e),\n"
       "                            (SELECT l.fixture_id FROM public.live_follow l WHERE l.event_id = u.e)) AS fid")], TP),
    ("D10-P4 RPC: impronta di Omega con una colonna in piu'", MIG,
     [("            coalesce((SELECT jsonb_agg(jsonb_build_object('built_at', t.built_at))",
       "            coalesce((SELECT jsonb_agg(jsonb_build_object('built_at', t.built_at, 'x', 1))")], TP),
    ("D10-P5 RPC eseguibile da tutti", MIG,
     [("REVOKE ALL ON FUNCTION public.nucleo_sentinella_cloud(text[], boolean) FROM public, anon, authenticated;",
       "GRANT EXECUTE ON FUNCTION public.nucleo_sentinella_cloud(text[], boolean) TO public;")], TP),
    ("D10-P6 RPC senza tetto di 500 eventi", MIG,
     [("    IF cardinality(v_eventi) > 500 THEN", "    IF cardinality(v_eventi) > 5000 THEN")], TP),
    ("D10-P7 trigger non scatta quando si forza nucleo_versione", MIG,
     [("                               away_team_id, nucleo_versione\n", "                               away_team_id\n")], TP),
    # --- revisione indipendente del 10/10 (correzioni 1-6)
    ("D10-23 ponte di un dossier cieco tenuto in memoria", "cache_cloud.py",
     [("                if riga is None or adesso - riga[0] >= self._scadenza:\n"
       "                    continue                           # dossier cieco: nessun ponte in memoria",
       "                if False:\n                    continue")], TS),
    ("D10-24 giro fallito senza annulla_rinnovi", "cache_cloud.py",
     [("            self._dossier.annulla_rinnovi()", "            pass")], TS),
    ("D10-25 annulla_rinnovi non riporta alla lettura", "cache_cloud.py",
     [("                    if letta < t:", "                    if False:")], TS),
    ("D10-26 nessun backoff dopo gli errori", "cache_cloud.py",
     [("            if self._errori_di_fila == 0:\n                return base", "            if True:\n                return base")], TS),
    ("D10-27 backoff mai azzerato dal giro riuscito", "cache_cloud.py",
     [("self._errori_di_fila = self._errori_di_fila + 1 if errore else 0",
       "self._errori_di_fila = self._errori_di_fila + 1 if errore else self._errori_di_fila")], TS),
    ("D10-28 nessuna scadenza massima con la RPC", "cache_cloud.py",
     [("SCADENZA_MASSIMA_S = 3600.0", "SCADENZA_MASSIMA_S = 1e12")], TS),
    ("D10-29 tetto raggiunto senza rilettura", "cache_cloud.py",
     [("            tetto = tetto or letto_alle > limite", "            tetto = False")], TS),
    ("D10-P8 migrazione senza lock_timeout", MIG,
     [("SET lock_timeout = '5s';   -- se scade", "-- tolto;   -- se scade")], TP),
]

# Le 10 mutazioni del revisore (scratchpad/rev_dg/mut_rev.py), adattate al codice corretto dove il testo e' cambiato
M += [
    ("REV-DG R1 trigger: versione anche senza cambi", MIG,
     [("    ELSIF (to_jsonb(NEW.tactical_engine_json), to_jsonb(NEW.db_json_analisi),",
       "    ELSIF TRUE OR (to_jsonb(NEW.tactical_engine_json), to_jsonb(NEW.db_json_analisi),")], TP),
    ("REV-DG R2a generazione fixture ignorata", "cache_cloud.py",
     [('                    if self._gen.get(("f", int(fid)), 0) != gen_fixture[int(fid)]:', "                    if False:")], TS),
    ("REV-DG R2b generazione evento (ponte) ignorata", "cache_cloud.py",
     [('                if self._gen.get(("e", ev), 0) != gen_eventi[ev]:', "                if False:")], TS),
    ("REV-DG R2c _invalida non alza le generazioni", "cache_cloud.py",
     [("            self._gen[chiave] = self._gen.get(chiave, 0) + 1\n", "            pass\n")], TS),
    ("REV-DG R3 ripiego REST spento", "cache_cloud.py",
     [("        return self._leggi_rest(omega, eventi_ord)", '        return Istantanea(None, None, "letture")')], TS),
    ("REV-DG R4a tetto 500 tolto dalla RPC", MIG,
     [("    IF cardinality(v_eventi) > 500 THEN", "    IF cardinality(v_eventi) > 100000000 THEN")], TP),
    ("REV-DG R4b tetto 500 tolto dal client (BLOCCO_RPC)", "cache_cloud.py",
     [("BLOCCO_RPC = 500", "BLOCCO_RPC = 100000")], TS),
    ("REV-DG R5 prendi_cambiati restituisce anche i dossier pieni", "cache_cloud.py",
     [("        return tuple(ev for ev in tutti if ev in dossier_dei_bot and dossier_cieco(dossier_dei_bot[ev]))",
       "        return tuple(ev for ev in tutti if ev in dossier_dei_bot)")], TS),
    ("REV-DG R6 rinnovo anche in modo letture", "cache_cloud.py",
     [('rinnova=ist.modo == "rpc"', "rinnova=True")], TS),
    ("REV-DG R7 errore della RPC trattato come assente (cambio modo)", "cache_cloud.py",
     [('                self._conta("errori")\n                logger.warning("[cache_cloud] nucleo_sentinella_cloud KO: %s", '
       'str(ex)[:160])\n                return Istantanea(None, None, "rpc")',
       "                self._segna_assente()\n                return None")], TS),
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


PG = bool((os.environ.get("G2_PG_PSQL") or "").strip())
FILTRO = (os.environ.get("MUTAZIONI_FILTRO") or "").strip()   # es. "D10": solo le mutazioni che iniziano cosi'
if FILTRO:
    M = [m for m in M if m[0].startswith(FILTRO)]
rossi = saltate = 0
for nome, f, sostituzioni, test in M:
    p = D / f
    if test == TP and not PG:
        saltate += 1
        print(f"SALTATA | {nome} | G2_PG_PSQL assente (PostgreSQL usa-e-getta)")
        continue
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
print(f"mutazioni rosse {rossi}/{len(M) - saltate} (saltate senza PostgreSQL: {saltate})")
