"""Sonda in SOLA LETTURA contro il DB vero (08/10): il codice nuovo di resilienza sulle
chiamate vere della catena, per UNA lega-stagione. Nessuna scrittura (solo RPC `stable` e
SELECT), nessuna chiamata ad API-Football. Rinnovo preventivo a 3 richieste per vedere il
rinnovo del client funzionare davvero."""
import logging
import os
import sys
import time

REPO = sys.argv[1]
sys.path.insert(0, REPO)
os.chdir(REPO)
logging.basicConfig(level=logging.WARNING)

import db_client  # noqa: E402
import season_gaps as sg  # noqa: E402

db_client.attiva_rinnovo_connessioni(3)
sb = db_client.ClientResiliente()
t0 = time.time()
lac = sg.lacune_stagione(sb, 135, 2025)
print(f"lacune_stagione(135, 2025): FT {lac.ft_totali}, partite {lac.partite_totali}, "
      f"tabelle {sorted(lac.per_tabella)}")
out, degradate = sg.riepilogo_lacune(sb, [(135, 2025), (39, 2025)], stampa=print, rinviate_rete=[])
print(f"riepilogo_lacune: {[(k, v.ft_totali) for k, v in out.items()]}, degradate {degradate}")
cov = sg.leggi_coverage(sb, 135)
st = sg.leggi_stati(sb, 135)
print(f"leggi_coverage(135): {len(cov)} righe; leggi_stati(135): {len(st)} righe")
r = sb.table("season_backfill_state").select("league_id,season_year,status").eq("league_id", 135).limit(2).execute()
print(f"proxy select: {r.data}")
print(f"client creati/rinnovati: {db_client.STATISTICHE_RETE['rinnovi_client']} rinnovi")
print(f"Rete PostgREST: {db_client.riepilogo_rete()}")
print(f"tempo: {time.time() - t0:.1f} s")
