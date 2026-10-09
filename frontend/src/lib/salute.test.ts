// ============================================================================
// salute.test.ts - T0A (09/10/2026): regole pure della pagina «Salute» e
// parita' con il Python (soglie, nomi dei tratti, colonne della RPC).
// I finti hanno le chiavi e i tipi dell'output di `monitor_salute_stato`
// (migrations/monitor_metrics_2026-10-09.sql) e delle righe di Betfair/monitor.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const rpc = vi.fn();
vi.mock('@/integrations/supabase/client', () => ({ supabase: { rpc: (...a: unknown[]) => rpc(...a) } }));

import {
    OBIETTIVI, TRATTI, alMinuto, leggiRaccoglitori, leggiStatoSalute, semaforo, spiegaTratto, totali,
    trattiUltimi, versioniDesktop, type RigaSalute,
} from './salute';

const RADICE = join(__dirname, '..', '..', '..');
const ADESSO = Date.parse('2026-10-10T12:00:00Z');

function riga(over: Partial<RigaSalute> = {}): RigaSalute {
    return {
        servizio: 'mike-service', sport: 'calcio', ts: '2026-10-10T11:59:40+00:00', pid: 4321, host: 'pc',
        avvio_ts: '2026-10-10T08:00:00+00:00', uptime_s: 14380, cpu_pct: 3.5, rss_mb: 180.2,
        db_richieste: 30, rest_richieste: 2,
        metriche: {
            v: 1, finestra_s: 30,
            processo: { psutil: true, cpu_pct: 3.5, rss_mb: 180.2, thread: 21 },
            contatori: { db: { 'GET mike_trades': 30 }, betfair_rest: { listMarketBook: 2 }, log_errori: { 'ERROR x': 1 } },
            tratti: {
                'feed_rx_pt_ms.calcio': { n: 40, somma: 6000, min: 120, max: 400, p50: 200, p99: 500, secchi: [] },
                diario_fsync_ms: { n: 2, somma: 1.1, min: 0.4, max: 0.7, p50: 0.5, p99: 1, secchi: [] },
            },
            valori: {},
        },
        ...over,
    };
}

beforeEach(() => rpc.mockReset());

describe('semaforo e totali', () => {
    it('vivo / in ritardo / muto dall\'eta\' dell\'ultima riga', () => {
        expect(semaforo('2026-10-10T11:58:31Z', ADESSO)).toBe('vivo');          // 89 s
        expect(semaforo('2026-10-10T11:58:29Z', ADESSO)).toBe('ritardo');       // 91 s
        expect(semaforo('2026-10-10T11:55:00Z', ADESSO)).toBe('ritardo');       // 300 s
        expect(semaforo('2026-10-10T11:54:59Z', ADESSO)).toBe('muto');
        expect(semaforo('non una data', ADESSO)).toBe('muto');                 // illeggibile = muto
        expect(semaforo(null, ADESSO)).toBe('muto');
    });

    it('al minuto dalla finestra della riga', () => {
        expect(alMinuto(riga(), 'db')).toBe(60);
        expect(alMinuto(riga(), 'rest')).toBe(4);
        expect(alMinuto(riga({ metriche: { v: 1, finestra_s: 0 } }), 'db')).toBeNull();
    });

    it('i servizi MUTI non entrano nei totali', () => {
        const vivo = riga();
        const muto = riga({ servizio: 'omega-service', ts: '2026-10-10T10:00:00Z', cpu_pct: 90, rss_mb: 999 });
        const t = totali([vivo, muto], ADESSO);
        expect(t).toEqual({
            servizi: 2, vivi: 1, cpu: 3.5, rssMb: 180.2, dbAlMinuto: 60, restAlMinuto: 4, erroriLog: 1,
            transazioni: 0, orologioMs: 120,
        });
        expect(totali([], ADESSO).cpu).toBeNull();                              // assente non e' zero
    });

    it('tratti nell\'ordine del percorso, con la spiegazione', () => {
        const t = trattiUltimi([riga()]);
        expect(t.map((x) => x.nome)).toEqual(['feed_rx_pt_ms.calcio', 'diario_fsync_ms']);
        expect(spiegaTratto('diario_fsync_ms')).toContain('L6b');
        expect(spiegaTratto('sconosciuto')).toBe('');
    });

    it('versioni del desktop dall\'user agent', () => {
        const ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
            + 'alpha-score/1.0.0 Chrome/130.0.6723.191 Electron/33.4.11 Safari/537.36';
        expect(versioniDesktop(ua)).toEqual({ electron: '33.4.11', chrome: '130.0.6723.191' });
        expect(versioniDesktop('jsdom')).toEqual({ electron: null, chrome: null });
    });
});

describe('letture (una RPC sul client che c\'e\' gia\')', () => {
    it('monitor_salute_stato con p_ore; forma della risposta', async () => {
        rpc.mockResolvedValueOnce({ data: { adesso: '2026-10-10T12:00:00Z', ore: 6, ultimi: [riga()], serie: [], sistema: [] }, error: null });
        const r = await leggiStatoSalute(6);
        expect(rpc).toHaveBeenCalledWith('monitor_salute_stato', { p_ore: 6 });
        expect(r.errore).toBeNull();
        expect(r.stato?.ultimi[0].servizio).toBe('mike-service');
    });

    it('migrazione non applicata: errore detto, nessuno stato inventato', async () => {
        rpc.mockResolvedValueOnce({ data: null, error: { message: 'Could not find the function public.monitor_salute_stato' } });
        const r = await leggiStatoSalute();
        expect(r).toEqual({ stato: null, errore: 'Could not find the function public.monitor_salute_stato' });
        rpc.mockResolvedValueOnce({ data: null, error: null });
        expect((await leggiStatoSalute()).stato).toBeNull();
    });

    it('raccoglitori', async () => {
        rpc.mockResolvedValueOnce({ data: { adesso: 'x', tabelle: [{ tabella: 'matches', colonna: 'updated_at', max: null, errore: 'timeout' }] }, error: null });
        const r = await leggiRaccoglitori();
        expect(rpc).toHaveBeenCalledWith('monitor_vitalita_raccoglitori');
        expect(r.tabelle[0].tabella).toBe('matches');
    });
});

describe('parita\' col Python e con la migrazione', () => {
    const referto = readFileSync(join(RADICE, 'Betfair', 'monitor', 'referto.py'), 'utf-8');
    const sql = readFileSync(join(RADICE, 'migrations', 'monitor_metrics_2026-10-09.sql'), 'utf-8');

    it('stesse soglie di Betfair/monitor/referto.py::OBIETTIVI', () => {
        for (const [k, v] of Object.entries(OBIETTIVI)) {
            const m = new RegExp(`"${k}":\\s*([0-9.]+)`).exec(referto);
            expect(m, `${k} assente in referto.py`).not.toBeNull();
            expect(Number(m?.[1])).toBe(v);
        }
    });

    it('stessi prefissi dei tratti del referto', () => {
        const blocco = referto.split('_TRATTI_SPIEGATI = (')[1].split('\n)\n')[0];
        const py = [...blocco.matchAll(/^\s+\("([a-z_.]+)", "/gm)].map((m) => m[1]);
        expect(py.length).toBeGreaterThan(5);
        expect(TRATTI.map((t) => t.prefisso)).toEqual(py);
    });

    it('le colonne di «ultimi» della RPC sono quelle di RigaSalute', () => {
        const blocco = sql.split('SELECT DISTINCT ON (m.servizio)')[1].split('FROM public.monitor_metrics')[0];
        const colonne = [...blocco.matchAll(/m\.([a-z_]+)/g)].map((m) => m[1]);
        const chiavi = Object.keys(riga());
        for (const k of chiavi) expect(colonne, `colonna ${k} non restituita dalla RPC`).toContain(k);
    });
});
