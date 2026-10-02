"""Prova indipendente della riparazione di ScalperPanel.tsx: si RIGUASTA il file
riparato (ogni carattere non ASCII -> i suoi byte UTF-8 letti in cp1252, i 5 byte
non definiti restano U+0081/8D/8F/90/9D) e lo si confronta con master, riga per
riga: devono coincidere TUTTE (cioe' la riparazione ha cambiato solo il mojibake,
nient'altro). Poi si confrontano i testi a schermo attesi del referto di verifica
(AUDIT_2026-10-02/VERIFICA_VESTE_COMPLETA.md par. 11).

Uso: python AUDIT_2026-10-02/verifica_mojibake.py
"""
import subprocess
import sys

PATH = 'frontend/src/components/live/ScalperPanel.tsx'
master = subprocess.run(['git', 'show', 'master:' + PATH], capture_output=True, check=True).stdout
master_t = master.decode('utf-8-sig').replace('\r\n', '\n')
nuovo_b = open(PATH, 'rb').read()
assert not nuovo_b.startswith(b'\xef\xbb\xbf'), 'BOM ancora presente'
nuovo_t = nuovo_b.decode('utf-8').replace('\r\n', '\n')


def guasta(s: str) -> str:
    out = []
    for c in s:
        if ord(c) < 128:
            out.append(c)
            continue
        for b in c.encode('utf-8'):
            try:
                out.append(bytes([b]).decode('cp1252'))
            except UnicodeDecodeError:
                out.append(chr(b))
    return ''.join(out)


m_righe = master_t.split('\n')
n_righe = nuovo_t.split('\n')
assert len(m_righe) == len(n_righe), (len(m_righe), len(n_righe))
diverse = [i + 1 for i, (a, b) in enumerate(zip(m_righe, n_righe)) if a != b]
non_spiegate = [i + 1 for i, (a, b) in enumerate(zip(m_righe, n_righe)) if guasta(b) != a]
print(f'righe: {len(n_righe)}; cambiate: {len(diverse)}; cambiate NON spiegate dal mojibake: {non_spiegate}')

ATTESI = {
    45: 'ARMAMENTO\u2026', 48: 'CHIUSURA\u2026', 157: '\u26a0\ufe0f CACCIA MULTI-LINEA',
    158: '(n=1) \u2014 la bibbia', 161: '\u26a0\ufe0f ATTIVARE LO SCALPER',
    162: 'piazzer\u00e0 scommesse REALI su Betfair in autonomia (stake \u20ac${stake})',
    205: "'ATTIVATO'} \u2014 ${eventName}", 225: 'corso\u2026 se una posizione resta aperta comparir\u00e0',
    239: 'Scalper Bot\u2026', 253: '\u26a0 Stato scalper NON aggiornato: {stateErr} \u2014 i dati',
    261: 'pre-match \u00b7 stop', 267: 'servizio \u2713', 272: 'ARMATO \u2014 nessun ordine', 311: 'Stake \u20ac',
    321: 'DEMO \u00b7 PAPER (ordini SIMULATI, ciclo completo \u2014 mai soldi veri)',
    343: '\u26a0\ufe0f Gamba INTERVALLO', 344: 'aggregato \u22121.74\u20ac',
    357: '+0.99\u20ac/14 eventi, worst \u22120.49', 364: 'Stake sniper \u20ac',
    382: '\u20ac/partita (n=1) \u2014 VALIDARE', 399: 'EV\u2212,', 400: '\u2014 SOLO PAPER', 408: 'Stake theta \u20ac',
    439: 'Tetto perdita \u20ac', 511: 'stake \u20ac{ctrl.stake}', 526: 'nessun consenso \u2192 neutro', 532: '\u2022 {r}',
    546: '`\u20ac${', 552: '`\u20ac${', 579: '`\u20ac${', 584: '`\u20ac${', 607: '`\u20ac${', 612: '`\u20ac${',
    569: "'\u2713' : '\u2014'", 574: "'\u2713' : '\u2014'", 627: 'Nessuna attivit\u00e0 ancora\u2026',
    660: '<> \u2014 cicli', 662: '(lordo) \u20ac{', 664: '(lordo) \u20ac{', 667: '> \u2014 {ctrl.error}',
}
mancano = [(r, t) for r, t in ATTESI.items() if t not in n_righe[r - 1]]
print(f'testi attesi del par. 11 controllati: {len(ATTESI)}; non trovati: {mancano}')
sys.exit(0 if not non_spiegate and not mancano else 1)
