# Mutazioni aggiuntive (eseguite da falsifica_bot_mai_ciechi.py con exec, ROOT definito)
SC = ROOT / "Betfair/safe_strategy/scanner.py"
SV = ROOT / "Betfair/safe_strategy/service.py"
BSV = ROOT / "Betfair/safe_strategy/bot_service.py"
BDB = ROOT / "Betfair/safe_strategy/bot_db.py"
MUT_EXTRA = [
    ("F7 attesa anche senza nessun book (riga inventata al riavvio)", SC,
     "or (bool(visto) and in_post_ko_wait(", "or (in_post_ko_wait("),
    ("F8 pulizia orfane senza margine dall'avvio", SV,
     "        return t - self.avvio_mono >= _ORPHAN_FIRST_GRACE_SEC", "        return True"),
    ("F9 pulizia orfane con un catalogo mancante", SV,
     "        if not all(st.catalogue_ts > 0.0 for st in self.sports.values()):\n"
     "            return False\n        return t - self.avvio_mono",
     "        return t - self.avvio_mono"),
    ("F10 catalogo sostituito per intero (comportamento vecchio)", SV,
     "tenuti = self._tieni_eventi_vivi(sport, st.metas, metas)", "tenuti = 0"),
    ("F11 catalogo che ignora l'esposizione", SV,
     "            if not (ev.get(\"inplay\") or str(eid) in esposti):",
     "            if not ev.get(\"inplay\"):"),
    ("F12 catalogo che tiene anche i mercati chiusi", SV,
     "            if ev.get(\"mo_status\") == \"CLOSED\":\n                continue\n"
     "            if not (ev.get(\"inplay\")",
     "            if not (ev.get(\"inplay\")"),
    ("F13 Safe: lettura fallita = nessuna riga (comportamento vecchio)", BSV,
     "            righe_db = list(_CANALE_SCAN.get(\"righe_db\") or [])\n"
     "            _avvisa_feed_non_letto(db, now_ts, errore=errore)",
     "            righe_db = []\n            _avvisa_feed_non_letto(db, now_ts, errore=errore)"),
    ("F14 bot_db: lettura fallita torna [] (comportamento vecchio)", BDB,
     "        logger.warning(\"[safe.db] lettura feed KO: %s\", str(ex)[:160])\n        return None",
     "        logger.warning(\"[safe.db] lettura feed KO: %s\", str(ex)[:160])\n        return []"),
    ("F15 avviso a ogni ciclo invece che a episodio", BSV,
     "    if _FEED_KO.get(\"dal\"):\n        return\n    _FEED_KO[\"dal\"] = float(now_ts)",
     "    _FEED_KO[\"dal\"] = float(now_ts)"),
]
