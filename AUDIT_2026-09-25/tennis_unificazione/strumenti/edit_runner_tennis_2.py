"""Seconda passata (ripresa del diario, attesa del libro all'uscita). Lanciato una volta."""
import io

p = "Betfair/stream/tennis_live/tennis_runner.py"
s = io.open(p, encoding="utf-8").read()


def sost(old, new, n=1):
    global s
    assert s.count(old) == n, (s.count(old), old[:90])
    s = s.replace(old, new)


sost('''        session.attesa_libro.pop(str((metas.get(ev) or {}).get("market_id") or ""), None)
        if ev in espulsi and not _ET.e_comando(voluti_righe.get(ev)):
''', '''        if ev in espulsi and not _ET.e_comando(voluti_righe.get(ev)):
''')
sost('''                session.hosted.pop((e, bk), None)
                session.stopping_deadline.pop((e, bk), None)
            session.market_meta.pop(ev, None)
            session.capture.pop(ev, None)
''', '''                session.hosted.pop((e, bk), None)
                session.stopping_deadline.pop((e, bk), None)
            session.attesa_libro.pop(
                str((session.market_meta.get(ev) or {}).get("market_id") or ""), None)
            session.market_meta.pop(ev, None)
            session.capture.pop(ev, None)
''')
sost('''    motore.avvia()
    # gli eventi ``order`` nascono dallo specchio del worker tennis
''', '''    motore.avvia()
    if _gt.GUARDIA_RUNNER.attiva and _gt.GUARDIA_RUNNER.fatto:
        # la ripresa d'avvio e' gia' riuscita PRIMA che il motore esistesse: il
        # diario si verifica adesso; se Betfair non risponde la guardia si
        # RIARMA (solo cancel) e la ripresa riprova coi worker, diario compreso
        if not motore.riprendi_da_diario(
                lambda refs: session.trading.betting.list_current_orders(
                    customer_order_refs=list(refs), lightweight=True)):
            _gt.GUARDIA_RUNNER.fatto = False
            logger.error("[tennis-runner] ripresa dal diario del motore NON completa: "
                         "guardia d'avvio RIARMATA")
    # gli eventi ``order`` nascono dallo specchio del worker tennis
''')
io.open(p, "w", encoding="utf-8", newline="\n").write(s)

p = "Betfair/stream/tennis_live/guardie_tennis.py"
g = io.open(p, encoding="utf-8").read()
old = '''def arma_guardia_runner() -> None:
'''
new = '''# 25/09 (F8): la ripresa del DIARIO del motore ordini tennis (comandi in volo al
# riavvio verificati su Betfair per ref, ``MotoreOrdini.riprendi_da_diario``).
# None = motore non montato (come prima). False = guardia ARMATA, si riprova.
_RIPRESA_MOTORE: Dict[str, Any] = {"fn": None}


def imposta_ripresa_motore(fn: Any) -> None:
    _RIPRESA_MOTORE["fn"] = fn


def arma_guardia_runner() -> None:
'''
assert g.count(old) == 1
g = g.replace(old, new)
old = '''        n_stale = d.fail_stale_pending_tennis_orders(RIPRESA_ETA_MAX_S)
        n_ord, n_pos = d.chiudi_specchio_paper_orfano()
    except Exception as ex:  # noqa: BLE001 - la guardia resta armata, si riprova
        logger.error("[tennis-runner] ripresa KO: bot e coda FERMI (guardia d'avvio "
                     "armata) finche' non riesce: %s", str(ex)[:200])
        return False
'''
new = '''        n_stale = d.fail_stale_pending_tennis_orders(RIPRESA_ETA_MAX_S)
        n_ord, n_pos = d.chiudi_specchio_paper_orfano()
        fn_motore = _RIPRESA_MOTORE.get("fn")
        if fn_motore is not None and not fn_motore():
            logger.error("[tennis-runner] ripresa dal diario del motore ordini NON completa: "
                         "guardia d'avvio armata, riprovo")
            return False
    except Exception as ex:  # noqa: BLE001 - la guardia resta armata, si riprova
        logger.error("[tennis-runner] ripresa KO: bot e coda FERMI (guardia d'avvio "
                     "armata) finche' non riesce: %s", str(ex)[:200])
        return False
'''
assert g.count(old) == 1
g = g.replace(old, new)
io.open(p, "w", encoding="utf-8", newline="\n").write(g)
print("ok")
