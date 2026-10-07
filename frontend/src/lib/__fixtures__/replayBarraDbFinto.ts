// ============================================================================
// FINTO delle RPC di Match Replay (`migrations/live_stream_rpc.sql` e
// `live_stream_rpc_chunked.sql`) per provare lo strumento sul database SENZA il
// database. Stesse chiavi, stessi tipi e stesse regole del vero:
//   list_replays(p_limit)  -> { rows: [{event_id, fixture_id, league_id, league_name,
//                              home_name, away_name, open_date, status, n_markets,
//                              n_snapshots, started_at, ended_at}] }   (UPLOADED, ordine open_date DESC)
//   get_replay_meta(p_event_id) -> { event, markets, score_timeline, ts_min, ts_max, inplay_from_ts }
//   get_replay_frames(p_event_id, p_from_ts, p_to_ts, p_bucket_sec, p_max_rows)
//                          -> { frames: [{market_id, ts, minute, inplay, status, ladder}], n }
//                              (DISTINCT ON (market_id, floor(epoch/bucket)) ORDER BY market_id,
//                               bucket, ts; LIMIT clamp 100..10000; finestre > 12 h rifiutate)
// Gli orari escono come li serializza Postgres in jsonb (ISO con '+00:00', microsecondi
// senza zeri finali), non come li scrive il curator.
// Le "tabelle" sono le fixture di `registrazioni_banco` (`replay_barra_<event>.json`).
// ============================================================================
import { createServer, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import type { Frame, ReplayData, ScoreEvent } from '@/lib/live';
import { ID_MERCATO_FANTASMA, replayDaFixture } from './replayBarraConversione';
import { caricaFixtureCompleta, type FixtureBarraCompleta } from './replayBarraTutte';

/** orario come lo serializza Postgres (timestamptz in jsonb): frazione senza zeri finali */
export function pgTs(iso: string | null): string | null {
    if (iso == null) return null;
    return iso.replace(/(\.\d*?)0+(\+|Z)/, (_m, f: string, z: string) => (f === '.' ? z : `${f}${z}`));
}

interface RigaPartita {
    fixture: FixtureBarraCompleta;
    replay: ReplayData;
}

export interface OpzioniFintoDb {
    /** per costruire un database DIFETTOSO: modifica le righe della partita prima dell'uso */
    modifica?: (eventId: string, replay: ReplayData) => ReplayData;
}

export class FintoDb {
    private partite = new Map<string, RigaPartita>();
    /** nomi delle RPC chiamate, nell'ordine */
    chiamate: string[] = [];

    constructor(eventi: ReadonlyArray<string>, opz: OpzioniFintoDb = {}) {
        for (const ev of eventi) {
            const fixture = caricaFixtureCompleta(ev);
            let replay = replayDaFixture(fixture);
            // la fixture riunisce i frame "fantasma" (che definiscono la griglia della barra) in UN
            // mercato: nel database vero appartengono a mercati diversi e il campionamento del server
            // (1 frame per mercato e bucket) non li fonde. Ogni fantasma ha il suo id di mercato.
            let k = 0;
            replay = { ...replay, frames: replay.frames.map(f => (f.market_id === ID_MERCATO_FANTASMA ? { ...f, market_id: `9.${k++}` } : f)) };
            if (opz.modifica) replay = opz.modifica(ev, replay);
            this.partite.set(ev, { fixture, replay });
        }
    }

    /** catalogo dei mercati come lo vede il server: il Match Odds + tanti segnaposto quanti ne ha la
     *  partita vera (il numero dei mercati decide i bucket del campionamento di `fetchReplayChunked`) */
    private catalogo(p: RigaPartita): ReplayData['markets'] {
        const n = p.fixture.meta.n_mercati ?? p.replay.markets.length;
        const veri = p.replay.markets.filter(m => m.market_id !== ID_MERCATO_FANTASMA);
        const segnaposto = Array.from({ length: Math.max(0, n - veri.length) }, (_, i) => ({
            market_id: `8.${i}`, market_type: 'OVER_UNDER_25', market_name: 'OVER_UNDER_25', sort_priority: 10 + i, selections: [],
        }));
        return [...veri, ...segnaposto];
    }

    private riga(eventId: unknown): RigaPartita {
        const p = this.partite.get(String(eventId));
        if (!p) throw new Error(`event_id ${String(eventId)} non trovato in live_follow`);
        return p;
    }

    listReplays(limite: number | null): unknown {
        const lim = Math.min(Math.max(limite ?? 100, 1), 500);
        const rows = [...this.partite.values()]
            .map((p) => ({ fixture: p.fixture, replay: p.replay, n: this.catalogo(p).length }))
            .map(({ fixture, replay, n }) => ({
                event_id: fixture.event.event_id,
                fixture_id: fixture.event.fixture_id,
                league_id: null,
                league_name: fixture.event.league_name,
                home_name: fixture.event.home_name,
                away_name: fixture.event.away_name,
                open_date: fixture.event.open_date,
                status: 'UPLOADED',
                n_markets: n,
                n_snapshots: replay.frames.length,
                started_at: pgTs(fixture.meta.ts_min),
                ended_at: pgTs(fixture.meta.ts_max),
            }))
            .sort((a, b) => (a.open_date < b.open_date ? 1 : a.open_date > b.open_date ? -1 : 0))
            .slice(0, lim);
        return { rows };
    }

    getReplayMeta(eventId: unknown): unknown {
        const riga = this.riga(eventId);
        const { fixture, replay } = riga;
        const score_timeline = replay.score_timeline
            .map((t: ScoreEvent) => ({
                ts: pgTs(t.ts), minute: t.minute, score_home: t.score_home, score_away: t.score_away,
                event_type: t.event_type, source: t.source, payload: t.payload,
            }))
            .sort((a, b) => ((a.ts as string) < (b.ts as string) ? -1 : (a.ts as string) > (b.ts as string) ? 1 : 0));
        return {
            event: { ...fixture.event },
            markets: this.catalogo(riga).map(m => ({
                market_id: m.market_id, market_type: m.market_type, market_name: m.market_name,
                sort_priority: m.sort_priority, selections: m.selections,
            })),
            score_timeline,
            ts_min: pgTs(fixture.meta.ts_min),
            ts_max: pgTs(fixture.meta.ts_max),
            inplay_from_ts: pgTs(fixture.meta.inplay_from_ts),
        };
    }

    getReplayFrames(args: Record<string, unknown>): unknown {
        const { replay } = this.riga(args.p_event_id);
        const da = Date.parse(String(args.p_from_ts));
        const a = Date.parse(String(args.p_to_ts));
        if (!Number.isFinite(da) || !Number.isFinite(a) || a <= da) throw new Error('finestra temporale non valida');
        if (a - da > 12 * 3600_000) throw new Error('finestra temporale troppo ampia');
        const bucket = Math.min(Math.max(Number(args.p_bucket_sec ?? 10), 1), 600);
        const max = Math.min(Math.max(Number(args.p_max_rows ?? 6000), 100), 10_000);
        const scelti = new Map<string, Frame>();
        for (const f of replay.frames) {
            const t = Date.parse(f.ts);
            if (t < da || t >= a) continue;
            const k = `${f.market_id}\u0000${Math.floor(t / 1000 / bucket)}`;
            const cur = scelti.get(k);
            if (!cur || t < Date.parse(cur.ts)) scelti.set(k, f);
        }
        const ordinati = [...scelti.entries()]
            .map(([k, f]) => ({ m: f.market_id, b: Number(k.split('\u0000')[1]), f }))
            .sort((x, y) => (x.m < y.m ? -1 : x.m > y.m ? 1 : x.b - y.b))
            .slice(0, max)
            .map(x => ({
                market_id: x.f.market_id, ts: pgTs(x.f.ts), minute: x.f.minute, inplay: x.f.inplay, status: x.f.status, ladder: x.f.ladder,
            }));
        return { frames: ordinati, n: ordinati.length };
    }

    /** come `supabase.rpc`: ritorna `{ data, error }` */
    async rpc(nome: string, args: Record<string, unknown> = {}): Promise<{ data: unknown; error: { message: string; code?: string } | null }> {
        this.chiamate.push(nome);
        try {
            if (nome === 'list_replays') return { data: this.listReplays(args.p_limit as number | null), error: null };
            if (nome === 'get_replay_meta') return { data: this.getReplayMeta(args.p_event_id), error: null };
            if (nome === 'get_replay_frames') return { data: this.getReplayFrames(args), error: null };
            return { data: null, error: { message: `Could not find the function public.${nome} in the schema cache`, code: 'PGRST202' } };
        } catch (e) {
            return { data: null, error: { message: e instanceof Error ? e.message : String(e), code: 'P0001' } };
        }
    }
}

// ----------------------------------------------------------------------------
// finto PostgREST su HTTP (solo localhost, solo per la durata di un test): il client
// vero di supabase-js, lo stesso del frontend, parla con questo server.
// ----------------------------------------------------------------------------
export interface ServerFinto {
    url: string;
    /** richieste ricevute: metodo + percorso */
    richieste: string[];
    chiudi(): Promise<void>;
}

export async function avviaServerFinto(db: FintoDb): Promise<ServerFinto> {
    const richieste: string[] = [];
    const server: Server = createServer((req, res) => {
        const pezzi: Buffer[] = [];
        req.on('data', c => pezzi.push(c as Buffer));
        req.on('end', () => {
            richieste.push(`${req.method} ${req.url}`);
            const m = /^\/rest\/v1\/rpc\/([a-z_]+)/.exec(req.url ?? '');
            if (req.method !== 'POST' || !m) {
                res.writeHead(404, { 'content-type': 'application/json' });
                res.end(JSON.stringify({ message: 'non trovato', code: 'PGRST125' }));
                return;
            }
            const args = pezzi.length ? (JSON.parse(Buffer.concat(pezzi).toString('utf-8')) as Record<string, unknown>) : {};
            void db.rpc(m[1], args).then(({ data, error }) => {
                res.writeHead(error ? 400 : 200, { 'content-type': 'application/json' });
                res.end(JSON.stringify(error ?? data));
            });
        });
    });
    await new Promise<void>(ok => server.listen(0, '127.0.0.1', ok));
    const porta = (server.address() as AddressInfo).port;
    return {
        url: `http://127.0.0.1:${porta}`,
        richieste,
        chiudi: () => new Promise<void>(ok => { server.close(() => ok()); server.closeAllConnections?.(); }),
    };
}
