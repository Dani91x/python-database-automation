// ============================================================================
// 07/10 - LO SCRIPT PER IL DATABASE, LANCIATO DAVVERO. `scripts/verifica_barra_replay.ts`
// gira come lo lancera' l'agente con il database (`npx vite-node ...`), con il client
// VERO di supabase-js, contro un finto PostgREST su localhost (solo per la durata del
// test) che risponde con le identiche chiavi e tipi delle RPC vere
// (`__fixtures__/replayBarraDbFinto.ts`). Si controlla: l'esito e il codice di uscita,
// le richieste fatte (solo POST alle tre RPC di lettura), le credenziali solo da ambiente.
// ============================================================================
import { describe, it, expect, afterEach } from 'vitest';
import { spawn } from 'node:child_process';
import { resolve } from 'node:path';
import type { ReplayData } from '@/lib/live';
import { FintoDb, avviaServerFinto, type ServerFinto } from './__fixtures__/replayBarraDbFinto';
import { eventiConFixture } from './__fixtures__/replayBarraTutte';
import { comandoViteNode } from './replayVerificaBarraLancio';

const FRONTEND = resolve(__dirname, '../..');
const EVENTI = eventiConFixture();
const CHIAVE_FINTA = 'chiave-finta-solo-per-il-test';
// 08/10 (cantiere 12): prima 120-180 s, e se il figlio non partiva (Windows, spawn ENOENT) il rosso arrivava
// solo dopo il timeout. Ora il mancato avvio cade subito (evento `error` del figlio) e il timeout e' solo la
// rete di sicurezza: misurato 9-19 s per caso su 4 CPU con load average 28, quindi 40 s lascia il doppio.
const TEMPO_MAX_MS = 40_000;

let server: ServerFinto | null = null;
afterEach(async () => { await server?.chiudi(); server = null; });

function lancia(args: string[], env: Record<string, string>): Promise<{ codice: number; out: string; err: string }> {
    // ambiente pulito: nessuna credenziale vera puo' filtrare dal processo di test
    const base: Record<string, string> = {};
    for (const [k, v] of Object.entries(process.env)) {
        if (v != null && !/SUPABASE|VERIFICA_/i.test(k)) base[k] = v;
    }
    // 08/10 (cantiere 12): il comando lo costruisce la funzione comune con lo script (su Windows `npx.cmd`
    // con shell e argomenti tra virgolette; prima `spawn('npx')` senza shell dava ENOENT e poi il timeout)
    const cmd = comandoViteNode(['scripts/verifica_barra_replay.ts', ...args], process.platform);
    return new Promise((ok) => {
        const p = spawn(cmd.comando, cmd.argomenti, { cwd: FRONTEND, env: { ...base, ...env }, shell: cmd.shell });
        let out = '', err = '';
        p.stdout.on('data', d => { out += String(d); });
        p.stderr.on('data', d => { err += String(d); });
        // se il figlio non parte (ENOENT...) il test cade SUBITO con il motivo, senza aspettare il timeout
        p.on('error', e => ok({ codice: -1, out, err: `${err}\nil processo figlio non e' partito: ${e.message}` }));
        p.on('close', c => ok({ codice: c ?? -1, out, err }));
    });
}

const RICHIESTA_AMMESSA = /^POST \/rest\/v1\/rpc\/(list_replays|get_replay_meta|get_replay_frames)(\?.*)?$/;

describe('script verifica_barra_replay.ts lanciato davvero (finto PostgREST su localhost)', () => {
    it('database coerente: esce con 0, referto per partita e riepilogo; SOLO richieste di lettura alle tre RPC', async () => {
        server = await avviaServerFinto(new FintoDb(EVENTI));
        const r = await lancia([], { VITE_SUPABASE_URL: server.url, SUPABASE_SERVICE_ROLE_KEY: CHIAVE_FINTA });
        expect(r.codice, `${r.out}\n${r.err}`).toBe(0);
        expect(r.out).toContain(`RIEPILOGO: ${EVENTI.length} partite verificate: ${EVENTI.length} OK, 0 con incoerenze, 0 non verificabili`);
        for (const ev of EVENTI) expect(r.out).toContain(ev);
        expect(r.out).toContain('Sola lettura');
        expect(server.richieste.length).toBeGreaterThan(5);
        for (const q of server.richieste) expect(q, `richiesta non ammessa: ${q}`).toMatch(RICHIESTA_AMMESSA);
        expect(server.richieste.some(q => q.includes('list_replays'))).toBe(true);
        expect(server.richieste.some(q => q.includes('get_replay_meta'))).toBe(true);
        expect(server.richieste.some(q => q.includes('get_replay_frames'))).toBe(true);
    }, TEMPO_MAX_MS);

    it('database con un difetto sul punteggio: esce con 1 e dice quale partita e quale codice', async () => {
        const difettoso = new FintoDb(EVENTI, {
            modifica: (_ev: string, replay: ReplayData): ReplayData => {
                const g = replay.score_timeline.find(x => (x.score_home ?? 0) > 0);
                if (!g) return replay;
                const tardi = new Date(Date.parse(g.ts) + 5000).toISOString().replace('Z', '+00:00');
                return { ...replay, score_timeline: [...replay.score_timeline, { ...g, ts: tardi, source: 'api_football', score_home: 0, score_away: 0 }] };
            },
        });
        server = await avviaServerFinto(difettoso);
        const r = await lancia(['--solo-incoerenti', '--senza-note'], { VITE_SUPABASE_URL: server.url, SUPABASE_SERVICE_ROLE_KEY: CHIAVE_FINTA });
        expect(r.codice, `${r.out}\n${r.err}`).toBe(1);
        expect(r.out).toContain('INCOERENTE');
        expect(r.out).toContain('TABELLONE_SCENDE');
        expect(r.out).toContain(`0 OK, ${EVENTI.length} con incoerenze`);
        for (const q of server.richieste) expect(q).toMatch(RICHIESTA_AMMESSA);
    }, TEMPO_MAX_MS);

    // 08/10 (cantiere 13): incoerenza dei DATI dichiarata, e le prove con --dettaglio
    it('KickOff del feed discorde (dato): esce con 1, "INCOERENTE PER DATI" e "SOLO PER DATI"; --dettaglio stampa le prove', async () => {
        const discorde = new FintoDb(EVENTI, {
            modifica: (_ev: string, replay: ReplayData): ReplayData => {
                const k = Math.min(...replay.frames.filter(f => f.inplay).map(f => Date.parse(f.ts)));
                const prima = new Date(k - 360_000).toISOString().replace('Z', '+00:00');
                return { ...replay, score_timeline: replay.score_timeline.map(r => (r.event_type === 'KickOff' ? { ...r, ts: prima } : r)) };
            },
        });
        server = await avviaServerFinto(discorde);
        const r = await lancia(['--evento', EVENTI[0], '--dettaglio', '--senza-note'], { VITE_SUPABASE_URL: server.url, SUPABASE_SERVICE_ROLE_KEY: CHIAVE_FINTA });
        expect(r.codice, `${r.out}\n${r.err}`).toBe(1);
        expect(r.out).toContain(`INCOERENTE PER DATI ${EVENTI[0]}`);
        expect(r.out).toContain('[PER DATI: ');
        expect(r.out).toContain('di cui 1 SOLO PER DATI (dichiarate con il motivo, classe c) e 0 da correggere.');
        expect(r.out).toContain('>> prove di KICKOFF_DISCORDANTE');
        for (const q of server.richieste) expect(q).toMatch(RICHIESTA_AMMESSA);
    }, TEMPO_MAX_MS);

    it('--evento filtra una sola partita; --json stampa un documento leggibile da una macchina', async () => {
        server = await avviaServerFinto(new FintoDb(EVENTI));
        const r = await lancia(['--evento', EVENTI[0], '--json'], { VITE_SUPABASE_URL: server.url, SUPABASE_SERVICE_ROLE_KEY: CHIAVE_FINTA });
        expect(r.codice, `${r.out}\n${r.err}`).toBe(0);
        const j = JSON.parse(r.out) as { riepilogo: { partite: number; ok: number }; partite: { event_id: string; ok: boolean; incoerenze: unknown[] }[] };
        expect(j.riepilogo).toMatchObject({ partite: 1, ok: 1 });
        expect(j.partite[0].event_id).toBe(EVENTI[0]);
        expect(j.partite[0].incoerenze).toEqual([]);
    }, TEMPO_MAX_MS);

    it('credenziali SOLO da ambiente: senza esce con 2 e lo dice; con la sola chiave anonima chiede anche l\'utente', async () => {
        // 09/10: il figlio gira con cwd=frontend e vite-node carica `frontend/.env` (sul PC ci sono
        // VITE_SUPABASE_URL e VITE_SUPABASE_ANON_KEY): Vite NON sovrascrive una variabile gia' presente
        // nell'ambiente, quindi si passano VUOTE: il caso 'senza credenziali' e' lo stesso ovunque.
        const senza = await lancia([], { VITE_SUPABASE_URL: '', SUPABASE_URL: '', VITE_SUPABASE_ANON_KEY: '', SUPABASE_SERVICE_ROLE_KEY: '' });
        expect(senza.codice).toBe(2);
        expect(senza.err).toContain('Credenziali mancanti');
        const anon = await lancia([], { VITE_SUPABASE_URL: 'http://127.0.0.1:9', VITE_SUPABASE_ANON_KEY: CHIAVE_FINTA });
        expect(anon.codice).toBe(2);
        expect(anon.err).toContain('VERIFICA_EMAIL');
        const uso = await lancia(['--limite', '0'], { VITE_SUPABASE_URL: 'http://127.0.0.1:9', SUPABASE_SERVICE_ROLE_KEY: CHIAVE_FINTA });
        expect(uso.codice).toBe(2);
    }, TEMPO_MAX_MS);
});
