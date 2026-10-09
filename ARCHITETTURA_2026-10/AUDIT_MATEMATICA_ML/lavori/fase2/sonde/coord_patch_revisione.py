# Correzioni dalla REVISIONE_FINALE (verificate dal coordinatore) sulle consegne della fase 2.
import io
import os

AU = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
log = []


def patch(name, reps, exact=True):
    p = os.path.join(AU, name)
    s = io.open(p, encoding="utf-8", newline="").read()
    for a, b in reps:
        n = s.count(a)
        if exact and n != 1:
            raise SystemExit(f"{name}: {a[:60]!r} occorrenze={n}")
        s = s.replace(a, b)
        log.append(f"{name}: {n}x {a[:50]!r}")
    io.open(p, "w", encoding="utf-8", newline="").write(s)


patch("07_RIEPILOGO_PER_L_UTENTE.md", [
    ("1. **I conti che muovono i soldi dei bot sono giusti** (green-up, profitti e perdite back e lay, commissione, puntate,\n   scala delle quote). Nessun errore critico.",
     "1. **Le formule che muovono i soldi dei bot sono giuste** (green-up, profitti e perdite back e lay, puntate, scala delle\n   quote). Nessun errore critico. Restano piccole differenze di centesimi tra copie della stessa formula (es. la commissione\n   stimata nel cash-out di Mike: 0,62 EUR nel caso provato), elencate in 05 come BASSE."),
    ("Green-up, P&L, commissione, Kelly, scala delle quote: rifatti con le funzioni vere, tornano.",
     "Green-up, P&L, Kelly, scala delle quote: rifatti con le funzioni vere, tornano; la commissione differisce di qualche centesimo tra copie (BASSO)."),
    ("Restano: nessun bot controlla quanto e' vecchia la previsione che usa;",
     "Restano: solo Omega controlla quanto sono vecchi i gol attesi che usa (in cache); Mike no, lo scalper non verificato;"),
    ("lo confronta con una moneta invece che con la media della lega: passa e boccia quasi a caso.",
     "lo confronta con una moneta invece che con la media della lega: un modello che ripete solo la media passa, e un modello\n  perfetto viene bocciato spesso (54% delle volte con 87 partite di prova)."),
    ("le previsioni scritte a partita iniziata: la causa (orologio in ritardo) e'\n   stata tolta oggi (D20).",
     "le previsioni scritte a partita iniziata: la causa probabile (orologio delle action in\n   ritardo di 5-6 ore) e' stata tolta oggi (D20)."),
], exact=False)
patch("DECISIONI_PER_L_UTENTE.md", [
    ("La causa (cron in ritardo) e' stata rimossa il 09/10 con l'orologio pg_cron approvato (CRONOSTORIA.md:5580-5600)",
     "La causa probabile (cron GitHub in ritardo di 5-6 ore) e' stata rimossa il 09/10 con l'orologio pg_cron approvato (CRONOSTORIA.md:5580-5600); il legame e' un'inferenza, da confermare con la misura"),
    ("lo stop di conto oggi e' spento (NULL)", "lo stop di conto e' spento di serie (NULL = off nel codice; il valore sul DB non e' stato letto)"),
])
patch("05_ERRORI_DI_PROGETTAZIONE.md", [
    ("**causa gia' rimossa** il 09/10", "**causa probabile gia' rimossa** il 09/10"),
    ("Theta e' opt-in (`theta_mode`, `theta_bot.py:546-551`)", "Theta e' opt-in (`theta_mode`, `scalper_session.py:91`, `auto_mode.py:188`; uso del v3 in `theta_bot.py:546-551`)"),
    ("(`omega_advisor.py:309`)", "(`omega_advisor.py:308`)"),
])
patch("REFERTO_FIX_DUTCHING.md", [
    ("Strumento manuale dell'utente: nessun bot (Omega, Mike, Safe, tennis) usa il dutching; nessuna strategia toccata.",
     "Strumento manuale dell'utente: nessun bot usa il dutching variable (Safe usa `dutch_back` solo per le proposte COMBO,\n`safe_strategy/combos.py:43,527`, e non e' toccato); nessuna strategia toccata."),
    ("| `frontend/src/components/live/DutchingPanel.test.tsx` (+204) |", "| `frontend/src/components/live/DutchingPanel.test.tsx` (+202/-2) |"),
    ("seme diverso (424242), 2-12 gambe,", "seme diverso (424242), 2/6/10/12 gambe,"),
    ("| M5 bottone + `guardBeforeSend` + opzione tolti insieme |", "| M5 (M5b nel file) bottone + `guardBeforeSend` + opzione tolti insieme |"),
    ("azionabili inclusi; `lavori/fase2/suite/differenziale_coord_seed424242.txt`).",
     "azionabili inclusi; `lavori/fase2/suite/differenziale_coord_seed424242.txt`, prima riga; la seconda parte dello script, sulla\ngriglia dei tick, non e' stata rieseguita dal coordinatore perche' il file di riferimento del delegato non c'era piu': ENOENT nel file)."),
])
for f in ("01_CATENA_POISSON.md", "02_CATENA_ML.md", "03_COMPONENTI_MATEMATICI.md", "04_FLUSSO_FINO_AL_CONSUMATORE.md", "06_PIANO_MIGLIORAMENTI.md", "00_INVENTARIO_MATEMATICO.md"):
    patch(f, [("today_predictions_backfill.py:1493", "today_predictions_backfill.py:1494"),
              ("poisson_calibrator.py:84-90", "poisson_calibrator.py:86-92"),
              ("omega_advisor.py:309", "omega_advisor.py:308")], exact=False)
io.open(os.path.join(AU, "lavori", "fase2", "APPLICATE_REVISIONE_FINALE.md"), "w", encoding="utf-8").write(
    "# Correzioni applicate dal coordinatore dopo REVISIONE_FINALE.md\n\n" + "\n".join("- " + x for x in log) + "\n")
print("\n".join(log))
