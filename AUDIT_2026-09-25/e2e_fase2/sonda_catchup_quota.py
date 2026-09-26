"""sonda_catchup_quota.py - Verifica indipendente 7.9.4.B / 7.4 (SOLA LETTURA).

Delegato admin-26 fase 2, perimetro 7.9.4 (catchup/quota). Nessuna scrittura sul DB:
solo .select()/.rpc() su RPC dichiarate STABLE (season_detail_gaps). Nessuna
chiamata API-Football (vietata dal brief specifico di questo delegato).

Uso:  .venv\\Scripts\\python.exe AUDIT_2026-09-25\\e2e_fase2\\sonda_catchup_quota.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")
from db_client import get_supabase_client  # noqa: E402

sb = get_supabase_client()

CAMPIONI = [(78, 2026), (39, 2026), (10, 2026)]
TABELLE = ["match_events", "match_lineups", "match_player_stats", "match_team_stats", "match_odds"]
STATI_DA_CHIAMARE = ("da_chiamare", "errore", "da_richiamare")
STATI_APERTI = STATI_DA_CHIAMARE + ("in_attesa",)


def chunk(lst, n=400):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def esistenti(tabella, fixture_ids):
    """Set dei fixture_id presenti in `tabella` (per match_odds: solo snapshot_type='api_football').

    NB: le tabelle di dettaglio hanno PIU' righe per fixture_id (eventi, formazioni...):
    non basta un select con limit = n(fixture) per chunk, serve paginare (range) finche'
    la pagina torna piena, altrimenti si sottostima la presenza (bug osservato e corretto
    nella prima stesura di questa sonda: vedi nota nel referto)."""
    out = set()
    PAGINA = 1000
    for c in chunk(fixture_ids):
        offset = 0
        while True:
            q = sb.table(tabella).select("fixture_id").in_("fixture_id", c)
            if tabella == "match_odds":
                q = q.eq("snapshot_type", "api_football")
            resp = q.range(offset, offset + PAGINA - 1).execute()
            righe = resp.data or []
            for r in righe:
                out.add(int(r["fixture_id"]))
            if len(righe) < PAGINA:
                break
            offset += PAGINA
    return out


def classifica(fixture_id, fixture_date, tabella, check, adesso):
    """Riproduzione fedele del CASE della RPC season_detail_gaps (migrations/season_gaps_2026-09-25.sql:171-183)."""
    if tabella == "match_odds" and fixture_date < adesso - timedelta(days=7):
        return "non_disponibile"
    if check is None:
        return "da_chiamare"
    esito, vuoti, ultimo = check["esito"], check["vuoti"], check["ultimo_controllo_at"]
    if esito in ("errore", "parziale"):
        return "errore"
    if vuoti >= 2 or ultimo >= fixture_date + timedelta(days=7):
        return "vuoto_definitivo"
    if ultimo > adesso - timedelta(days=2):
        return "in_attesa"
    return "da_richiamare"


def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def main():
    adesso = datetime.now(timezone.utc)
    referto = {"generato_at": adesso.isoformat(), "campioni": []}
    for lid, sy in CAMPIONI:
        print(f"\n=== lega {lid} stagione {sy} ===")
        rpc = sb.rpc("season_detail_gaps", {"p_league_id": lid, "p_season_year": sy,
                                            "p_fixture_ids": None}).execute()
        rpc_righe = rpc.data or []
        rpc_conti = {}
        ft_totali = None
        for r in rpc_righe:
            if r["tabella"] == "_partite":
                if r["stato"] == "ft":
                    ft_totali = r["n"]
                continue
            rpc_conti[(r["tabella"], r["stato"])] = r["n"]

        # ricalcolo indipendente -----------------------------------------------------
        matches = sb.table("matches").select("fixture_id,fixture_date") \
            .eq("league_id", lid).eq("season_year", sy) \
            .in_("status_short", ["FT", "AET", "PEN"]).limit(5000).execute()
        rows = matches.data or []
        ft_ids = [int(r["fixture_id"]) for r in rows]
        fdate = {int(r["fixture_id"]): parse_ts(r["fixture_date"]) for r in rows}
        print(f"  FT/AET/PEN diretti: {len(ft_ids)}  (RPC _partite/ft: {ft_totali})")

        checks_resp = sb.table("fixture_detail_checks").select(
            "fixture_id,tabella,esito,vuoti,ultimo_controllo_at") \
            .eq("league_id", lid).eq("season_year", sy).limit(5000).execute()
        checks = {}
        for r in (checks_resp.data or []):
            checks[(int(r["fixture_id"]), r["tabella"])] = {
                "esito": r["esito"], "vuoti": r["vuoti"],
                "ultimo_controllo_at": parse_ts(r["ultimo_controllo_at"])}

        mio_conti = {}
        for tabella in TABELLE:
            pres = esistenti(tabella, ft_ids)
            for fid in ft_ids:
                check = checks.get((fid, tabella))
                presente = fid in pres
                parziale = check is not None and check["esito"] == "parziale"
                if presente and not parziale:
                    continue  # riga NON in "senza" -> non conta come lacuna
                stato = classifica(fid, fdate[fid], tabella, check, adesso)
                mio_conti[(tabella, stato)] = mio_conti.get((tabella, stato), 0) + 1

        # confronto -------------------------------------------------------------------
        chiavi = sorted(set(rpc_conti) | set(mio_conti))
        tutto_ok = True
        dettaglio = []
        for k in chiavi:
            a, b = rpc_conti.get(k, 0), mio_conti.get(k, 0)
            ok = (a == b)
            tutto_ok &= ok
            dettaglio.append({"tabella_stato": list(k), "rpc": a, "ricalcolo": b, "ok": ok})
            flag = "OK" if ok else "MISMATCH"
            print(f"  {k[0]:<20} {k[1]:<16} rpc={a:<5} ricalcolo={b:<5} {flag}")

        # da_chiamare/aperti aggregati per tabella attiva (colonna "da chiamare" del referto)
        somma_da_chiamare_rpc = sum(v for (t, s), v in rpc_conti.items() if s in STATI_DA_CHIAMARE)
        somma_da_chiamare_mio = sum(v for (t, s), v in mio_conti.items() if s in STATI_DA_CHIAMARE)
        print(f"  TOTALE da_chiamare+errore+da_richiamare: rpc={somma_da_chiamare_rpc} "
              f"ricalcolo={somma_da_chiamare_mio} {'OK' if somma_da_chiamare_rpc==somma_da_chiamare_mio else 'MISMATCH'}")

        referto["campioni"].append({
            "league_id": lid, "season_year": sy, "ft_totali_rpc": ft_totali,
            "ft_totali_diretti": len(ft_ids), "esito_globale": "PASS" if tutto_ok else "FAIL",
            "somma_da_chiamare_rpc": somma_da_chiamare_rpc, "somma_da_chiamare_ricalcolo": somma_da_chiamare_mio,
            "dettaglio": dettaglio,
        })

    with open("AUDIT_2026-09-25/e2e_fase2/sonda_catchup_quota_output.json", "w", encoding="utf-8") as f:
        json.dump(referto, f, ensure_ascii=False, indent=2, default=str)
    print("\nScritto AUDIT_2026-09-25/e2e_fase2/sonda_catchup_quota_output.json")


if __name__ == "__main__":
    main()
