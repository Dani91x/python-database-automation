// ============================================================================
// 07/10 - LO STRUMENTO PER IL DATABASE (`scripts/verifica_barra_replay.ts`) senza il
// database: il finto delle RPC (`__fixtures__/replayBarraDbFinto.ts`) ha le IDENTICHE
// chiavi e tipi del vero (`migrations/live_stream_rpc*.sql`, `lib/live.ts`); le
// funzioni di caricamento sono quelle VERE della pagina (`fetchReplayList`,
// `fetchReplayChunked`), solo il client di rete e' sostituito.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const stato = vi.hoisted(() => ({
    db: null as null | { rpc: (n: string, a: Record<string, unknown>) => Promise<unknown> },
}));
vi.mock('@/integrations/supabase/client', () => ({
    supabase: {
        rpc: (nome: string, args: Record<string, unknown>) => (stato.db as { rpc: (n: string, a: Record<string, unknown>) => Promise<unknown> }).rpc(nome, args),
        from: () => { throw new Error('from non deve essere chiamato'); },
        auth: { signInWithPassword: async () => ({ error: null }) },
    },
}));

import type { ReplayData } from '@/lib/live';
import {
    RPC_PERMESSE, blindaSolaLettura, fonteSupabase, refertoPartita, riepilogo, verificaPartite, clienteSupabase,
} from '@/lib/replayVerificaBarraDb';
import { esitoDaRilievi } from '@/lib/replayVerificaBarra';
import { FintoDb, pgTs } from './__fixtures__/replayBarraDbFinto';
import { eventiConFixture, RADICE_REPO, caricaFixtureCompleta, primoGolCheResta } from './__fixtures__/replayBarraTutte';

const EVENTI = eventiConFixture();
let finto: FintoDb;
beforeEach(() => {
    finto = new FintoDb(EVENTI);
    stato.db = finto;
});

describe('il finto delle RPC parla come il vero', () => {
    it('pgTs: orari come li serializza Postgres (microsecondi senza zeri finali)', () => {
        expect(pgTs('2026-07-10T16:31:46.771000+00:00')).toBe('2026-07-10T16:31:46.771+00:00');
        expect(pgTs('2026-07-10T16:31:46.000000+00:00')).toBe('2026-07-10T16:31:46+00:00');
        expect(pgTs('2026-07-10T16:31:46.585766+00:00')).toBe('2026-07-10T16:31:46.585766+00:00');
        expect(pgTs(null)).toBeNull();
    });

    it('list_replays: { rows: [...] } con le chiavi di ReplayItem', async () => {
        const r = await finto.rpc('list_replays', { p_limit: 500 });
        const rows = (r.data as { rows: Record<string, unknown>[] }).rows;
        expect(rows).toHaveLength(EVENTI.length);
        expect(Object.keys(rows[0]).sort()).toEqual([
            'ended_at', 'event_id', 'fixture_id', 'home_name', 'league_id', 'league_name', 'n_markets', 'n_snapshots', 'open_date', 'away_name', 'started_at', 'status',
        ].sort());
    });

    it('get_replay_meta: event, markets, score_timeline, ts_min, ts_max, inplay_from_ts', async () => {
        const r = await finto.rpc('get_replay_meta', { p_event_id: EVENTI[0] });
        expect(Object.keys(r.data as object).sort()).toEqual(['event', 'inplay_from_ts', 'markets', 'score_timeline', 'ts_max', 'ts_min']);
    });

    it('get_replay_frames: una finestra senza dati e\' vuota; una troppo ampia o invertita e\' un errore; sconosciuta = PGRST202', async () => {
        const f = caricaFixtureCompleta(EVENTI[0]);
        const vuota = await finto.rpc('get_replay_frames', { p_event_id: EVENTI[0], p_from_ts: '2000-01-01T00:00:00Z', p_to_ts: '2000-01-01T00:10:00Z', p_bucket_sec: 10, p_max_rows: 10000 });
        expect((vuota.data as { n: number }).n).toBe(0);
        const larga = await finto.rpc('get_replay_frames', { p_event_id: EVENTI[0], p_from_ts: f.meta.ts_min, p_to_ts: '2099-01-01T00:00:00Z', p_bucket_sec: 10, p_max_rows: 10000 });
        expect(larga.error?.message).toContain('troppo ampia');
        const ignota = await finto.rpc('altra_rpc', {});
        expect(ignota.error?.code).toBe('PGRST202');
    });
});

describe('verificaPartite con le funzioni VERE della pagina e il finto delle RPC', () => {
    it('i frame caricati con fetchReplayChunked sono gli stessi della fixture (stesso campionamento del server)', async () => {
        for (const ev of EVENTI) {
            const { replay } = await fonteSupabase.carica(ev);
            const attesi = caricaFixtureCompleta(ev).frames.length;
            expect(replay.frames.length, `frame caricati di ${ev}`).toBe(attesi);
            expect(replay.frames.every(f => typeof f.ts === 'string' && typeof f.market_id === 'string' && typeof f.inplay === 'boolean')).toBe(true);
        }
    }, 120_000);

    it('tutte le partite del finto database: 0 incoerenze, solo RPC di lettura con i parametri della pagina', async () => {
        const risultati = await verificaPartite(fonteSupabase, { limite: 500 });
        expect(risultati.map(r => r.eventId).sort()).toEqual([...EVENTI].sort());
        for (const r of risultati) {
            expect(r.errore).toBeNull();
            expect(r.esito?.incoerenze, refertoPartita(r, true, false)).toEqual([]);
        }
        const rie = riepilogo(risultati);
        expect(rie.tutteOk).toBe(true);
        expect(rie.righe[0]).toContain(`${EVENTI.length} partite verificate: ${EVENTI.length} OK, 0 con incoerenze, 0 non verificabili`);
        expect(new Set(finto.chiamate)).toEqual(new Set(['list_replays', 'get_replay_meta', 'get_replay_frames']));
        expect([...new Set(finto.chiamate)].every(n => RPC_PERMESSE.has(n))).toBe(true);
    }, 120_000);

    it('un database con un difetto (due fonti discordanti sul punteggio) viene segnalato: riepilogo rosso e codice nel referto', async () => {
        const difettoso = new FintoDb(EVENTI, {
            modifica: (_ev: string, replay: ReplayData): ReplayData => {
                const g = primoGolCheResta(replay);
                if (!g) return replay;
                const tardi = new Date(Date.parse(g.ts) + 5000).toISOString().replace('Z', '+00:00');
                return { ...replay, score_timeline: [...replay.score_timeline, { ...g, ts: tardi, source: 'api_football', score_home: 0, score_away: 0 }] };
            },
        });
        stato.db = difettoso;
        const risultati = await verificaPartite(fonteSupabase, {});
        const rie = riepilogo(risultati);
        expect(rie.tutteOk).toBe(false);
        expect(rie.incoerenti).toBe(EVENTI.length);
        expect(rie.righe.join('\n')).toContain('TABELLONE_SCENDE');
        expect(refertoPartita(risultati[0], false, false)).toContain('[ERRORE] TABELLONE_SCENDE');
    }, 120_000);

    it('una partita che non si carica e\' NON VERIFICATA (non sparisce dal conto) e la ricerca per event_id filtra', async () => {
        const fonte = { ...fonteSupabase, carica: async (ev: string) => { if (ev === EVENTI[0]) throw new Error('timeout 57014'); return fonteSupabase.carica(ev); } };
        const risultati = await verificaPartite(fonte, { eventi: [EVENTI[0]] });
        expect(risultati).toHaveLength(1);
        expect(risultati[0].esito).toBeNull();
        const rie = riepilogo(risultati);
        expect(rie.nonVerificate).toBe(1);
        expect(rie.tutteOk).toBe(false);
        expect(rie.righe.join('\n')).toContain('timeout 57014');
    });

    it('un verificatore di un altro sport si passa con `verifica` (il tennis riusa lo strumento)', async () => {
        const chiamate: string[] = [];
        const risultati = await verificaPartite(fonteSupabase, {
            verifica: (replay, estremi) => {
                chiamate.push(`${replay.event.event_id}:${estremi.ts_min ? 'estremi' : 'senza'}`);
                return esitoDaRilievi([], { passi: 0, frames: replay.frames.length, simboli: {}, righePunteggio: 0, righeEvento: 0 });
            },
        });
        expect(chiamate.sort()).toEqual(EVENTI.map(ev => `${ev}:estremi`).sort());
        expect(riepilogo(risultati).tutteOk).toBe(true);
    }, 120_000);

    it('nessuna partita nell\'elenco: il riepilogo NON dice "tutto OK" (non si certifica il vuoto)', () => {
        expect(riepilogo([]).tutteOk).toBe(false);
    });

    // 08/10 (cantiere 13): le partite incoerenti SOLO per i dati registrati (classe c) sono dichiarate
    it('incoerenza dei DATI (KickOff del feed discorde dal flag in gioco): "INCOERENTE PER DATI" nel riepilogo, mai "OK"', async () => {
        const conKickOff = (replay: ReplayData): ReplayData => {
            const k = Math.min(...replay.frames.filter(f => f.inplay).map(f => Date.parse(f.ts)));
            const prima = new Date(k - 360_000).toISOString().replace('Z', '+00:00');
            return { ...replay, score_timeline: replay.score_timeline.map(r => (r.event_type === 'KickOff' ? { ...r, ts: prima } : r)) };
        };
        stato.db = new FintoDb(EVENTI, {
            modifica: (ev: string, replay: ReplayData): ReplayData => {
                const r = conKickOff(replay);
                if (ev !== EVENTI[EVENTI.length - 1] || EVENTI.length < 2) return r;
                // l'ultima partita ha ANCHE un difetto vero (due fonti discordanti): non e' "solo per dati"
                const g = primoGolCheResta(r);
                if (!g) return r;
                const tardi = new Date(Date.parse(g.ts) + 5000).toISOString().replace('Z', '+00:00');
                return { ...r, score_timeline: [...r.score_timeline, { ...g, ts: tardi, source: 'api_football', score_home: 0, score_away: 0 }] };
            },
        });
        const risultati = await verificaPartite(fonteSupabase, {});
        const rie = riepilogo(risultati);
        const testo = rie.righe.join('\n');
        expect(rie.tutteOk).toBe(false);
        expect(rie.incoerenti).toBe(EVENTI.length);
        const soloDati = EVENTI.length < 2 ? EVENTI.length : EVENTI.length - 1;
        expect(rie.perDati).toBe(soloDati);
        expect(testo).toContain(`di cui ${soloDati} SOLO PER DATI (dichiarate con il motivo, classe c) e ${EVENTI.length - soloDati} da correggere.`);
        expect(testo).toContain(`INCOERENTE PER DATI ${EVENTI[0]}`);
        expect(testo).toContain('KICKOFF_DISCORDANTE (per dati)');
        const di = (ev: string) => risultati.find(r => r.eventId === ev) as (typeof risultati)[number];
        expect(refertoPartita(di(EVENTI[0]), false, false)).toMatch(/^INCOERENTE PER DATI /);
        expect(refertoPartita(di(EVENTI[0]), false, false)).toContain('[PER DATI: ');
        if (EVENTI.length >= 2) {
            const ultimo = di(EVENTI[EVENTI.length - 1]);
            expect(refertoPartita(ultimo, false, false)).toMatch(/^INCOERENTE \d/);
            expect(testo).toMatch(new RegExp(`\\n  INCOERENTE ${EVENTI[EVENTI.length - 1]} .*KICKOFF_DISCORDANTE \\(per dati\\).*TABELLONE_SCENDE|\\n  INCOERENTE ${EVENTI[EVENTI.length - 1]} .*TABELLONE_SCENDE.*KICKOFF_DISCORDANTE \\(per dati\\)`));
        }
    }, 120_000);
});

describe('SOLA LETTURA', () => {
    it('blindaSolaLettura: una RPC fuori elenco e ogni accesso a una tabella lanciano un errore, le RPC di lettura passano', async () => {
        const falso = {
            rpc: vi.fn(async (_nome: string, _args?: unknown) => ({ data: 1, error: null })),
            from: vi.fn((_tabella?: string) => ({ insert: vi.fn() })),
        };
        blindaSolaLettura(falso);
        expect(() => falso.rpc('segui_live_apri_partita', {})).toThrow(/NON permessa/);
        expect(() => falso.rpc('delete_event', {})).toThrow(/NON permessa/);
        expect(() => falso.from('live_follow')).toThrow(/NON permesso/);
        await expect(falso.rpc('list_replays', { p_limit: 1 })).resolves.toEqual({ data: 1, error: null });
    });

    it('il client dello strumento e\' blindato come lo blinda lo script', () => {
        blindaSolaLettura(clienteSupabase);
        expect(() => (clienteSupabase as unknown as { rpc: (n: string) => unknown }).rpc('apri_partita')).toThrow(/NON permessa/);
        expect(() => (clienteSupabase as unknown as { from: (n: string) => unknown }).from('live_follow')).toThrow(/NON permesso/);
    });

    it('i sorgenti dello strumento non contengono scritture (insert/update/delete/upsert) ne\' accessi a tabelle', () => {
        for (const rel of ['frontend/scripts/verifica_barra_replay.ts', 'frontend/src/lib/replayVerificaBarraDb.ts']) {
            const src = readFileSync(join(RADICE_REPO, rel), 'utf-8').replace(/\/\/.*$/gm, '').replace(/\/\*[\s\S]*?\*\//g, '');
            expect(src, rel).not.toMatch(/\.(insert|update|delete|upsert)\s*\(/);
            expect(src, rel).not.toMatch(/\.from\s*\(\s*['"`]/);
        }
    });
});
