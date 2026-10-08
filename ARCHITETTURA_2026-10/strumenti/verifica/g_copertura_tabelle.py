# -*- coding: utf-8 -*-
"""Verifica usa-e-getta (08/10/2026): le tabelle (e le RPC che scrivono) toccate dal
codice di produzione/frontend sono tutte nominate nella scheda G (tabella per tabella)?
Fonte: s03_matrice_tabelle.tsv / s03_matrice_rpc.tsv. Solo lettura. Uso: python g_copertura_tabelle.py
Exit code: 0 se 0 mancanti, 1 altrimenti."""
import csv, re, sys, os

QUI = os.path.dirname(os.path.abspath(__file__))
ARCH = os.path.normpath(os.path.join(QUI, '..', '..'))
TSV_T = os.path.join(ARCH, 'strumenti', 'inventario', 'uscite', 's03_matrice_tabelle.tsv')
TSV_R = os.path.join(ARCH, 'strumenti', 'inventario', 'uscite', 's03_matrice_rpc.tsv')
G = os.path.join(ARCH, '03_SCHEDE_COMPONENTI', 'G_DATI_E_ALGORITMI_DEL_CLOUD.md')
ID = re.compile(r'[a-z_][a-z0-9_]*')
# RPC che NON scrivono (lettura/calcolo): le altre non-get_ sono trattate come scriventi.
RPC_SOLA_LETTURA = {'betfair_live_is_owner', 'leagues_needing_retrain', 'season_aggregates_summary',
                    'season_detail_gaps', 'season_gaps_summary', 'run_strategy', 'run_strategy_rows',
                    'backtest_strategy', 'rpc', 'fetch_missing_fixture_coverage'}


# Tabelle scritte da RPC (DML nel .sql, non visibile alla matrice .table()) e fuori dalle 89:
# trovate leggendo le definizioni delle RPC scriventi in migrations/. Vanno nominate in G.
TABELLE_DA_RPC = ['betfair_live_settings', 'personal_trade_legs', 'personal_cash_movements',
                  'strategies', 'tennis_refresh_requests', 'omega_requests']


def righe(p):
    with open(p, encoding='utf-8') as f:
        return list(csv.DictReader(f, delimiter='\t'))


def sezione_tabelle(testo):
    """Sezione tabella-per-tabella: §1.3 (da 'Tabella per tabella') fino a '### 1.4', e §4.3 fino a '### 4.4'
    (compresa la sotto-sezione di aggiunte, che sta in §4.3)."""
    out = []
    for ini, fine in (('### 1.3 ', '### 1.4 '), ('### 4.3 ', '### 4.4 ')):
        a = testo.find(ini)
        b = testo.find(fine, a)
        if a < 0 or b < 0:
            print('ERRORE: sezione non trovata', ini, fine)
            sys.exit(2)
        out.append(testo[a:b])
    return '\n'.join(out)


def citata(nome, testo):
    return re.search(r'(?<![a-z0-9_])' + re.escape(nome) + r'(?![a-z0-9_])', testo) is not None


def main():
    g = open(G, encoding='utf-8').read()
    sez = sezione_tabelle(g)
    tab = [r['tabella'] for r in righe(TSV_T)
           if ID.fullmatch(r['tabella']) and int(r['n_prod']) + int(r['n_frontend']) > 0]
    man_t = [t for t in tab if not citata(t, sez)]
    # criterio stretto: nome pieno nella tabella-per-tabella (sez) E, per le sigle abbreviate,
    # nella sotto-sezione di aggiunte (che le nomina per intero)
    man_x = [t for t in TABELLE_DA_RPC if not citata(t, sez)]
    rpc = [r['rpc'] for r in righe(TSV_R)
           if ID.fullmatch(r['rpc']) and int(r['n_prod']) + int(r['n_frontend']) > 0]
    scr = [r for r in rpc if not r.startswith(('get_', 'list_')) and r not in RPC_SOLA_LETTURA]
    man_r = [r for r in scr if not citata(r, g)]
    print('tabelle nell\'elenco (prod/FE): %d | coperte: %d | mancanti: %d' % (len(tab), len(tab) - len(man_t), len(man_t)))
    for t in man_t:
        print('  MANCA tabella:', t)
    print('tabelle scritte da RPC fuori elenco: %d | citate: %d | mancanti: %d' % (len(TABELLE_DA_RPC), len(TABELLE_DA_RPC) - len(man_x), len(man_x)))
    for t in man_x:
        print('  MANCA tabella (da RPC):', t)
    print('RPC scriventi nell\'elenco: %d | citate in G: %d | mancanti: %d' % (len(scr), len(scr) - len(man_r), len(man_r)))
    for r in man_r:
        print('  MANCA rpc:', r)
    sys.exit(0 if not man_t and not man_r and not man_x else 1)


if __name__ == '__main__':
    main()
