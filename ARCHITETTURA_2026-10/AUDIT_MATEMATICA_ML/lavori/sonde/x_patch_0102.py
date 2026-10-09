import io
def sub_between(s, start, end, new):
    i = s.index(start); j = s.index(end, i) + len(end)
    return s[:i] + new + s[j:]
Q = ("orario delle quote VERIFICATO (lavori/Q_orario_quote.md): unico scrittore today_predictions_backfill.py:893 e 2375-2395,\n"
     "  righe 'ok' mai riscritte (:2455-2459); `update` delle quote mediana 8,0 h prima del calcio d'inizio, 0/1.519 dopo la\n"
     "  generazione della previsione (le quote sono ~2 h PIU' VECCHIE della previsione), 20/1.519 dopo il KO di ~1 minuto.\n"
     "  Ripetuto il confronto solo con quote disponibili alla previsione e previsioni pre-KO (n=1.309): Poisson calibrato\n"
     "  +0,057 log-loss [0,042; 0,073] peggio delle quote: la conclusione regge e il confronto NON e' sbilanciato.")
# 01
p = "01_CATENA_POISSON.md"; s = io.open(p, encoding="utf-8").read()
s = sub_between(s, "orario delle quote non verificato", "a favore delle quote.", Q)
s = s.replace("- Orario di acquisizione delle quote di riferimento (raw_json_odds.update) e quindi l'equita' esatta del confronto.\n",
              "- `update` e' il timestamp di API-Football, non l'istante di quotazione del bookmaker (Q).\n")
s = s.replace("## 7. Cio' che non ho potuto verificare",
"""## 6-bis. Riferimenti ad ARCHITETTURA_2026-10 (mappa, riverificata dove indicato)
- Scheda G (`ARCHITETTURA_2026-10/03_SCHEDE_COMPONENTI/G_DATI_E_ALGORITMI_DEL_CLOUD.md`, riga della calibrazione):
  `weekly_poisson_calibration.yml` con cron `27 3 * * 1` e `poisson_calibration.generated_at` 05/10: coerente con il
  ricalcolo del lunedi'; oggi i workflow non hanno piu' `cron:` e la catena parte da pg_cron alle 00:12 UTC
  (E_inventario_completezza.md, CRONOSTORIA 09/10): la scheda e' superata su questo punto.
- Scheda G riga 54: `statement_timeout=8s` sul ruolo `authenticator`: ogni cruscotto di qualita' (06 n.3) deve leggere
  per finestre di data strette come le sonde di questo audit (nessun 57014 in 20 SELECT).

## 7. Cio' che non ho potuto verificare""")
io.open(p, "w", encoding="utf-8").write(s)
# 02
p = "02_CATENA_ML.md"; s = io.open(p, encoding="utf-8").read()
a = "## 7. Cio' che non ho potuto verificare"
assert s.count(a) == 1
s = s.replace(a, """## 6-bis. Orario delle quote e riferimenti ad ARCHITETTURA_2026-10
- Le quote di confronto (raw_json_odds) sono anteriori alla previsione in 1.519/1.519 casi (mediana 2 h prima) e
  anteriori al calcio d'inizio salvo 20 casi di ~1 minuto: il confronto ML contro quote non e' sbilanciato; ML +0,052
  log-loss [0,037; 0,068] sul campione con tutto pre-KO (lavori/Q_orario_quote.md).
- Scheda G (righe 45 e 136): `match_odds` ha ~92,5 milioni di righe (20 GB) scritte dal solo `football_data_scraper/`,
  lanciato a mano, con uno strumento `fix_snapshot_time.py`; `max(snapshot_time)` va in timeout (8 s). Coerente con il
  reperto ML-R4 (snapshot_time NULL nel campione): l'orario delle quote usate come feature va risolto nell'ETL prima di
  qualsiasi misura su tutta la tabella. `ml_calibration.yml` (post-calibrazione) gira ogni giorno e dopo il retrain.

""" + a)
io.open(p, "w", encoding="utf-8").write(s)
# 00
p = "00_INVENTARIO_MATEMATICO.md"; s = io.open(p, encoding="utf-8").read()
a = "## Legenda"
assert s.count(a) == 1
s = s.replace(a, """**Nota del coordinatore (dopo le verifiche finali):** le gravita' FINALI valgono in `05_ERRORI_DI_PROGETTAZIONE.md`,
che prevale su questo file. Dopo l'assemblaggio sono emersi altri ALTI: modello ML servito senza valore informativo
oltre il mercato, gate ML che seleziona sul rumore, modello tennis di Safe che usa solo il punteggio dei giochi
(lavori/Z2_tennis_residui.md). La catena hazard (P-22..P-29, X-34, SQL-23) e' analizzata in `lavori/Z1_hazard.md`;
X-20..X-24 e X-35 in `lavori/Z2_tennis_residui.md`; entrambe riassunte in `03_COMPONENTI_MATEMATICI.md` sez. 16-17.
Le citazioni `devig.py:93-100/103-110`, `seriea_model_export.py:437`, `today:1593-1594` sono state corrette in
`:12-19/22-29`, `:401`, `:1589-1590` (revisione lavori/X_revisione_coerenza.md).

""" + a)
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
