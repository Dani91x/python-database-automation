"""Falsificazione: ogni mutazione reintroduce un difetto, il test indicato DEVE
diventare rosso; poi si ripristina il file e se ne verifica lo sha256."""
import hashlib
import shutil
import subprocess
import sys

W = '/home/user/python-database-automation/.claude/worktrees/agent-a1c21d4fd7008caf6/'
LOW = 'Betfair/stream/live_order_worker.py'
EFB = 'Betfair/stream/trading/esposizione_fuori_bot.py'
T = 'Betfair/stream/tests/test_greenup_fuori_bot_2026_10_08.py'


def sha(p):
    return hashlib.sha256(open(W + p, 'rb').read()).hexdigest()


MUT = [
    ("M1 instradamento fuori_bot spento", LOW,
     "    if isinstance(_p_esp, dict) and _p_esp.get(_EFB_PARAM) is not None:",
     "    if False:  # MUTAZIONE",
     ["test_solo_sito_back_si_copre_con_una_lay_al_miglior_lay"]),
    ("M2 ogni customerStrategyRef accettato", EFB,
     "    if csr and csr.lower() != STRATEGIA_MANUALE_APP:",
     "    if False:  # MUTAZIONE",
     ["test_ogni_strategia_che_non_e_dell_utente_e_esclusa",
      "test_gli_ordini_dei_bot_sulla_stessa_selezione_non_si_toccano"]),
    ("M3 tabelle dei bot non lette", LOW,
     "        for tabella in _EFB.TABELLE_BOT:",
     "        for tabella in ():  # MUTAZIONE",
     ["test_gli_ordini_dei_bot_sulla_stessa_selezione_non_si_toccano",
      "test_mike_role_utente_resta_escluso_come_nella_rpc"]),
    ("M4 source dello specchio ignorata", LOW,
     "            if src not in _EFB.SOURCE_SPECCHIO_A_MANO:",
     "            if False:  # MUTAZIONE",
     ["test_gli_ordini_dei_bot_sulla_stessa_selezione_non_si_toccano"]),
    ("M5 riga di coda ignorata", LOW,
     "            motivo = _EFB.motivo_bot_da_coda(r)",
     "            motivo = None  # MUTAZIONE",
     ["test_gli_ordini_dei_bot_sulla_stessa_selezione_non_si_toccano"]),
    ("M6 il chiesto al posto dell'abbinato", EFB,
     "    for o in ordini:\n        sm = _num(o.get(\"sizeMatched\"))\n        if sm <= 0:\n            continue\n        apm",
     "    for o in ordini:\n        sm = _num((o.get(\"priceSize\") or {}).get(\"size\"))  # MUTAZIONE\n        if sm <= 0:\n            continue\n        apm",
     ["test_parziale_conta_solo_l_abbinato"]),
    ("M7 paper non rifiutato per modalita'", LOW,
     "    if str(mode or \"\").strip().lower() != \"live\":\n        raise ValueError(f\"greenup {_EFB.FUORI_BOT}: solo LIVE",
     "    if False:  # MUTAZIONE\n        raise ValueError(f\"greenup {_EFB.FUORI_BOT}: solo LIVE",
     ["test_paper_rifiutato_con_motivo_e_nessuna_lettura"]),
    ("M8 DB illeggibile = nessun bot", LOW,
     "        dal_db = _proprietari_bot(sb, [str(o.get(\"betId\") or \"\") for o in ordini])\n    except Exception as ex:  # noqa: BLE001 - lettura KO: nessuna decisione al buio\n        raise",
     "        dal_db = _proprietari_bot(sb, [str(o.get(\"betId\") or \"\") for o in ordini])\n    except Exception as ex:  # noqa: BLE001 - lettura KO: nessuna decisione al buio\n        dal_db = {}  # MUTAZIONE\n    if False:\n        raise",
     ["test_db_illeggibile_rifiuto_esplicito"]),
    ("M9 copertura appesa non vista", LOW,
     "                and str(o.get(\"side\") or \"\").lower() == side):",
     "                and False):  # MUTAZIONE",
     ["test_copertura_dell_app_ancora_appesa_sul_lato_della_copertura_ferma_il_secondo"]),
    ("M10 «chiusa» non rifiutata", LOW,
     "    if chiuse:\n        e = chiuse[0]",
     "    if False:  # MUTAZIONE\n        e = chiuse[0]",
     ["test_mike_non_viene_mai_dichiarata_chiusa_dalla_copertura"]),
    ("M11 mercato a due esiti ignorato", LOW,
     "    if altro is not None:\n        w2, l2 = _EFB.esposizione_abbinata(",
     "    if False:  # MUTAZIONE\n        w2, l2 = _EFB.esposizione_abbinata(",
     ["test_mercato_a_due_esiti_posizione_piatta_sul_mercato"]),
    ("M12 paginazione ignorata", LOW,
     "        if not pagina or not altre:",
     "        if True:  # MUTAZIONE",
     ["test_paginazione_del_conto"]),
    ("M13 re-hedge senza esposizione", LOW,
     "            payload[\"params\"][_EFB_PARAM] = params_src.get(_EFB_PARAM)",
     "            pass  # MUTAZIONE",
     ["test_il_rehedge_di_una_copertura_fuori_bot_resta_fuori_bot"]),
    ("M14 esposizione null instradata (parita')", LOW,
     "    if isinstance(_p_esp, dict) and _p_esp.get(_EFB_PARAM) is not None:",
     "    if isinstance(_p_esp, dict) and _EFB_PARAM in _p_esp:  # MUTAZIONE",
     ["test_parita_byte_per_byte_con_il_greenup_di_b5547eb"]),
    ("M15 valore ignoto ripiega sul blotter", LOW,
     "    if valore != _EFB.FUORI_BOT:\n        raise",
     "    if valore != _EFB.FUORI_BOT:  # MUTAZIONE\n        request_row = dict(request_row, params={})\n        return _do_greenup(sb, flumine, request_row, mode, strategy, client=client)\n        raise",
     ["test_valore_di_esposizione_sconosciuto_rifiutato"]),
    ("M16 parametri del parziale ammessi", LOW,
     "        raise ValueError(f\"greenup {_EFB.FUORI_BOT}: params.{k} non ammesso \"",
     "        continue  # MUTAZIONE\n        raise ValueError(f\"greenup {_EFB.FUORI_BOT}: params.{k} non ammesso \"",
     ["test_parametri_del_greenup_parziale_e_comandi_dei_bot_rifiutati"]),
    ("M17 verso della copertura invertito nel verdetto", LOW,
     "    delta = float(plan.size) if side == \"back\" else -float(plan.size)",
     "    delta = -float(plan.size) if side == \"back\" else float(plan.size)  # MUTAZIONE",
     ["test_mike_ridotta_quando_il_prezzo_e_sceso_il_worker_lo_dice",
      "test_omega_ridotta_la_previsione_del_worker_coincide_col_verdetto_vero"]),
    ("M18 parita': il ramo vecchio tocca la persistenza", LOW,
     "    persistence = \"LAPSE\"\n    if isinstance(params, dict) and params.get(\"persistence\") is not None:",
     "    persistence = \"PERSIST\"  # MUTAZIONE\n    if isinstance(params, dict) and params.get(\"persistence\") is not None:",
     ["test_parita_byte_per_byte_con_il_greenup_di_b5547eb"]),
    ("M19 csr 'live' trattato come bot (app esclusa)", EFB,
     "STRATEGIA_MANUALE_APP = \"live\"",
     "STRATEGIA_MANUALE_APP = \"app\"  # MUTAZIONE",
     ["test_sito_e_app_si_sommano", "test_contratti_con_le_regole_esistenti"]),
]


def run(tests):
    sel = [f"{T}::{t}" for t in tests]
    r = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', *sel],
                       cwd=W, capture_output=True, text=True, timeout=600)
    righe = [l for l in r.stdout.splitlines() if ' passed' in l or ' failed' in l]
    return r.returncode, (righe[-1] if righe else r.stdout[-300:])


orig = {p: sha(p) for p in (LOW, EFB)}
backup = {p: open(W + p).read() for p in (LOW, EFB)}
esiti = []
for nome, f, vecchio, nuovo, tests in MUT:
    src = backup[f]
    assert src.count(vecchio) == 1, f"{nome}: pattern trovato {src.count(vecchio)} volte"
    open(W + f, 'w').write(src.replace(vecchio, nuovo))
    try:
        rc, riga = run(tests)
    finally:
        open(W + f, 'w').write(backup[f])
    assert sha(f) == orig[f], f"{nome}: ripristino NON riuscito"
    assert 'MUTAZIONE' not in open(W + f).read()
    esiti.append((nome, rc != 0, riga))
    print(f"{'ROSSO' if rc != 0 else 'VERDE(!)'} | {nome} | {riga}", flush=True)

rc, riga = run([])
print("ripristinato, file intero:", riga)
for p in (LOW, EFB):
    print(p, sha(p))
print("mutazioni non catturate:", [n for n, rosso, _ in esiti if not rosso])
