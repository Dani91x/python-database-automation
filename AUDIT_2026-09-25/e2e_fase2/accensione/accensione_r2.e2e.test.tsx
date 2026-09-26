// ============================================================================
// accensione.e2e.test.tsx — E2E REALE FASE 2 (26/09/2026): ACCENSIONE DEI BOT IN PAPER.
//
// Autorizzazione dell'utente (26/09 h11:20): «fate tutto il necessario SOLO PAPER». App accesa.
// Strumento: il banco della fase 1 (componente VERO `PannelloBot` + comandi VERI
// `creaComandiControlRoom` come in pages/ControlRoom.tsx, client Supabase VERO `../e2e_fase1/clientVero`).
// GUARDIA IN PIU' (fase 2): prima di arrivare al DB ogni RPC passa da `guardiaPaper`: sono ammesse SOLO
// le RPC d'accensione e le letture `get_*`; qualunque argomento che nomini `live` BLOCCA la chiamata
// (non parte). Ordine: Omega → Mike → Safe (base, esatto, punta; tennis dalla scheda tennis) →
// 4 bot tennis → scalper. Fotografia PRIMA/DOPO di ogni riga, orari in ACCENSIONE_ORA.txt.
// ============================================================================
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, fireEvent, act, cleanup, type RenderResult } from '@testing-library/react';
import { appendFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';

const AMMESSE = new Set([
    'omega_activate', 'mike_activate', 'safe_activate', 'safe_update_params',
    'tennis_bot_service_activate', 'scalper_auto_activate',
]);
const registro: { ts: string; rpc: string; args: unknown; esito: string }[] = [];
function nominaLive(x: unknown): boolean {
    if (x == null) return false;
    if (typeof x === 'string') return x.toLowerCase() === 'live';
    if (Array.isArray(x)) return x.some(nominaLive);
    if (typeof x === 'object') {
        return Object.entries(x as Record<string, unknown>).some(([k, v]) =>
            // solo le chiavi di MODALITA': p_mode, mode, strategy_modes.* (params interi contengono altre stringhe)
            ((k === 'p_mode' || k === 'mode') && nominaLive(v))
            || (k === 'strategy_modes' && v != null && typeof v === 'object' && Object.values(v as object).some(nominaLive))
            || (k === 'p_params' && nominaLive({ strategy_modes: (v as Record<string, unknown> | null)?.strategy_modes }))
            || (k === 'p_params' && (v as Record<string, unknown> | null)?.mode === 'live'));
    }
    return false;
}
vi.mock('@/integrations/supabase/client', async () => {
    const m = await import('../e2e_fase1/clientVero');
    const s = m.supabase as unknown as Record<string, unknown> & { rpc: (...a: unknown[]) => unknown };
    const vera = s.rpc;
    s.rpc = (name: unknown, args?: unknown, ...rest: unknown[]) => {
        const n = String(name);
        const lettura = /^(get_[a-z0-9_]+|betfair_live_is_owner|trading_[a-z0-9_]+)$/.test(n);
        if (!lettura && !AMMESSE.has(n)) {
            registro.push({ ts: new Date().toISOString(), rpc: n, args, esito: 'BLOCCATA: fuori accensione' });
            throw new Error(`FASE2: RPC fuori accensione BLOCCATA: ${n}`);
        }
        if (!lettura && nominaLive(args)) {
            registro.push({ ts: new Date().toISOString(), rpc: n, args, esito: 'BLOCCATA: nomina live' });
            throw new Error(`FASE2: RPC con modalita LIVE BLOCCATA: ${n}`);
        }
        if (!lettura) registro.push({ ts: new Date().toISOString(), rpc: n, args, esito: 'inviata' });
        return vera(name, args, ...rest);
    };
    return { supabase: m.supabase };
});
vi.mock('@/lib/localChannel', async (importOriginal) => {
    const orig = await importOriginal<typeof import('@/lib/localChannel')>();
    // sveglia best-effort NON inviata dal banco (il servizio rilegge il DB al suo giro)
    return { ...orig, svegliaBot: () => { /* registrata come non inviata */ } };
});

import { raw, chiamate, bloccate } from '../e2e_fase1/clientVero';
import { PannelloBot } from '@/components/controlroom/PannelloBot';
import { righeInterruttori, type StatoBotPlancia } from '@/components/controlroom/righeBot';
import { creaComandiControlRoom } from '@/components/controlroom/comandiBot';
import {
    interruttoriDiSport, importiInterruttori, usciteInterruttori, conPosizioniAperte,
    usciteSessioniScalper, type SportBot,
} from '@/lib/interruttori';
import { fetchOmegaState } from '@/lib/omega';
import { fetchSafeState } from '@/lib/safeBot';
import { fetchMikeState } from '@/lib/mike';
import { fetchTennisBotServices } from '@/lib/tennis';
import { fetchScalperControlRoom, statoBotScalper } from '@/lib/scalperControlRoom';
import { BOT_TENNIS, type Bot } from '@/lib/controlRoom';
import { leggiVarianti, leggiModiStrategia } from '@/components/controlroom/useControlRoom';

const MAIN = 'C:/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation';
const OUT = resolve(MAIN, 'AUDIT_2026-09-25/e2e_fase2');
const FOTO = resolve(OUT, 'accensione_r2');
mkdirSync(FOTO, { recursive: true });
const ORA = resolve(OUT, 'ACCENSIONE_ORA.txt');

type Riga = Record<string, unknown>;
const P = (r: Riga) => (r.params ?? {}) as Record<string, unknown>;
async function leggi(t: string, col: string, val: string): Promise<Riga> {
    const { data, error } = await raw.from(t).select('*').eq(col, val).single();
    if (error) throw new Error(`${t}: ${error.message}`);
    return data as Riga;
}
const omega = () => leggi('omega_control', 'id', '1');
const mike = () => leggi('mike_control', 'id', '1');
const safe = () => leggi('safe_strategy_control', 'id', '1');
const tennis = (k: string) => leggi('tennis_bot_service_control', 'bot_key', k);
const scalperSrv = () => leggi('scalper_service_control', 'id', '1');
const settings = () => leggi('betfair_live_settings', 'id', '1');

/** fotografia (SOLA LETTURA): select * delle righe di controllo + settings */
async function foto(nome: string) {
    const f: Riga = { ts: new Date().toISOString(), sql: 'select * from omega_control, mike_control, safe_strategy_control, tennis_bot_service_control, scalper_service_control, betfair_live_settings' };
    f.omega_control = await omega(); f.mike_control = await mike(); f.safe_strategy_control = await safe();
    f.tennis_bot_service_control = (await raw.from('tennis_bot_service_control').select('*').order('bot_key')).data;
    f.scalper_service_control = await scalperSrv(); f.betfair_live_settings = await settings();
    writeFileSync(resolve(FOTO, `${nome}.json`), JSON.stringify(f, null, 1), 'utf8');
    return f;
}
function ora(bot: string, riga: Riga, nota = '') {
    const d = new Date();
    const loc = d.toLocaleString('it-IT', { timeZone: 'Europe/Rome', hour12: false });
    const line = `${bot}\tlocale ${loc}\tUTC ${d.toISOString()}\tstatus=${riga.status}\tmode=${riga.mode}${nota ? `\t${nota}` : ''}\n`;
    appendFileSync(ORA, line, 'utf8');
}
async function attendi(pred: () => Promise<boolean>, ms = 20_000): Promise<boolean> {
    const t0 = Date.now();
    while (Date.now() - t0 < ms) { if (await pred()) return true; await new Promise((r) => setTimeout(r, 300)); }
    return false;
}
const pausa = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function caricaStato() {
    const [o, s, m, t, sc] = await Promise.all([
        fetchOmegaState(5), fetchSafeState(), fetchMikeState(), fetchTennisBotServices(), fetchScalperControlRoom(),
    ]);
    const base = (bot: Bot, c: Riga | null | undefined): StatoBotPlancia => ({
        bot, inCorsa: String(c?.status ?? '').toLowerCase() === 'running',
        modalita: c?.mode === 'live' || c?.mode === 'paper' ? (c.mode as 'live' | 'paper') : null,
        varianti: null, modiStrategia: null, stato: typeof c?.status === 'string' ? c.status : null,
        etaPushS: null, motivoBlocco: null, tettoPartite: null, partiteEsposte: null,
        stopFermaSoloAperture: (c?.stats as Riga | undefined)?.stop_ferma_solo_aperture === true,
        fermatoAllAvvioAt: null,
    });
    const sc0 = s.control as unknown as Riga | null;
    const bots: StatoBotPlancia[] = [
        base('omega', o.control as unknown as Riga),
        {
            ...base('safe', sc0),
            varianti: leggiVarianti(sc0?.params as Riga, s.params_effective as Riga | null),
            modiStrategia: leggiModiStrategia((sc0?.stats as Riga | undefined)?.params_effective as Riga | null, sc0?.params as Riga),
        },
        base('mike', m.control as unknown as Riga),
    ];
    const paramsTennis: Record<string, Riga | null> = {};
    for (const k of BOT_TENNIS) {
        const c = (t ?? []).find((x) => x.bot_key === k) as unknown as Riga | undefined;
        bots.push(base(k, c ?? null));
        paramsTennis[k] = c == null ? null : { ...((c.params as Riga) ?? {}), stake: c.stake };
    }
    const st = statoBotScalper(sc.sessioni, sc.servizio ?? null);
    bots.push({ ...base('scalper', null), inCorsa: st.inCorsa, modalita: st.modalita, stato: st.stato });
    const paramsScalper: Riga = {
        ...usciteSessioniScalper(sc.sessioni, (sc.servizio?.params ?? null) as Riga | null),
        ...(sc.servizio?.stake != null ? { stake: Number(sc.servizio.stake) } : {}),
    };
    const params = (b: Bot): Record<string, unknown> | null => {
        if (b === 'omega') return (o.control?.params ?? null) as Riga | null;
        if (b === 'safe') return (sc0?.params ?? null) as Riga | null;
        if (b === 'mike') return (m.control?.params ?? null) as Riga | null;
        if (b === 'scalper') return paramsScalper;
        return paramsTennis[b] ?? null;
    };
    const g = Number((o.control as unknown as Riga | null)?.daily_goal);
    return { bots, params, obiettivo: Number.isFinite(g) ? g : null };
}
let montato: RenderResult | null = null;
async function monta(sport: SportBot): Promise<RenderResult> {
    if (montato) { montato.unmount(); montato = null; }
    const v = await caricaStato();
    const servizio = (b: Bot) => {
        const s = v.bots.find((x) => x.bot === b);
        return s == null ? null : { inCorsa: s.inCorsa, modalita: s.modalita, varianti: s.varianti, modiStrategia: s.modiStrategia };
    };
    const comandi = creaComandiControlRoom({ params: v.params, servizio, obiettivoOmega: () => v.obiettivo }, () => {}, sport);
    const lista = interruttoriDiSport(sport);
    const righe = righeInterruttori(v.bots, sport);
    const importi = importiInterruttori(lista, v.params);
    const uscite = conPosizioniAperte(usciteInterruttori(lista, v.params), [], Date.now());
    const serviziAccesi = v.bots.filter((b) => b.inCorsa).map((b) => ({ bot: b.bot, modalita: b.modalita }));
    await act(async () => {
        montato = render(<PannelloBot righe={righe} importi={importi} comandi={comandi} uscite={uscite}
            serviziAccesi={serviziAccesi} ambito={sport} />);
    });
    return montato as unknown as RenderResult;
}
const passi: string[] = [];
async function clicca(s: RenderResult, id: string) {
    const el = s.queryByTestId(id);
    if (!el) throw new Error(`pulsante assente a video: ${id}`);
    if ((el as HTMLButtonElement).disabled) throw new Error(`pulsante DISABILITATO: ${id}`);
    passi.push(`${new Date().toISOString()} clic ${id} («${el.textContent?.trim()}»)`);
    await act(async () => { fireEvent.click(el); });
}
function salvaEsito(nome: string, extra: Riga) {
    writeFileSync(resolve(FOTO, `${nome}_esito.json`), JSON.stringify({
        ...extra, passi, rpc_registro: registro, rpc_clientVero: chiamate, bloccate,
    }, null, 1), 'utf8');
}
afterEach(() => { if (montato) { montato.unmount(); montato = null; } cleanup(); });

/** controllo comune: modo ordini effettivo paper, nessun live nelle righe */
async function nessunLive(): Promise<string[]> {
    const out: string[] = [];
    const st = await settings(); if (st.order_mode !== 'paper') out.push(`order_mode=${st.order_mode}`);
    if ((await omega()).mode !== 'paper') out.push('omega live');
    if ((await mike()).mode !== 'paper') out.push('mike live');
    const sf = await safe(); if (sf.mode !== 'paper') out.push('safe tetto live');
    for (const [k, v] of Object.entries((P(sf).strategy_modes ?? {}) as Riga)) if (v !== 'paper') out.push(`safe ${k}=${v}`);
    for (const k of BOT_TENNIS) if ((await tennis(k)).mode !== 'paper') out.push(`${k} live`);
    if ((await scalperSrv()).mode !== 'paper') out.push('scalper live');
    return out;
}

describe('FASE 2 — RIAVVIO 2 — accensione in paper', () => {
    it('G0 falsificazione della guardia: live e RPC fuori accensione NON partono', async () => {
        const { supabase } = await import('@/integrations/supabase/client');
        const rpc = (supabase as unknown as { rpc: (n: string, a?: unknown) => unknown }).rpc;
        expect(() => rpc('omega_activate', { p_mode: 'live' })).toThrow(/LIVE BLOCCATA/);
        expect(() => rpc('safe_update_params', { p_params: { strategy_modes: { base: 'live' } } })).toThrow(/LIVE BLOCCATA/);
        expect(() => rpc('set_live_order_mode', { p_mode: 'paper' })).toThrow(/fuori accensione/);
        expect(() => rpc('omega_update_params', { p_mode: 'paper' })).toThrow(/fuori accensione/);
        expect(chiamate.length).toBe(0);
        registro.length = 0;
    });

    it('A0 prerequisito: tutto fermo/paper, order_mode paper', async () => {
        appendFileSync(ORA, `# --- RIAVVIO 2 (dopo il riavvio dell'app) --- intestazione scritta ${new Date().toISOString()}
`, 'utf8');
        await foto('A0_prima_di_tutto');
        for (const [n, r] of [['omega', await omega()], ['mike', await mike()], ['safe', await safe()], ['scalper', await scalperSrv()]] as const) expect([n, r.status]).toEqual([n, 'stopped']);
        for (const k of BOT_TENNIS) expect([k, (await tennis(k)).status]).toEqual([k, 'stopped']);
        expect(await nessunLive()).toEqual([]);
    });

    it('A1 Omega → paper', async () => {
        const prima = await foto('A1_omega_prima');
        const s = await monta('calcio');
        await clicca(s, 'cr-avvia-paper-omega');
        const ok = await attendi(async () => (await omega()).status === 'running');
        const dopo = await foto('A1_omega_dopo');
        const o = dopo.omega_control as Riga;
        ora('omega', o);
        salvaEsito('A1_omega', { ok, status: o.status, mode: o.mode, prima_status: (prima.omega_control as Riga).status });
        expect([o.status, o.mode]).toEqual(['running', 'paper']);
        expect(await nessunLive()).toEqual([]);
    });

    it('A2 Mike → paper', async () => {
        await foto('A2_mike_prima');
        const s = await monta('calcio');
        await clicca(s, 'cr-avvia-paper-mike');
        const ok = await attendi(async () => (await mike()).status === 'running');
        const dopo = await foto('A2_mike_dopo');
        const m = dopo.mike_control as Riga;
        ora('mike', m);
        salvaEsito('A2_mike', { ok, status: m.status, mode: m.mode });
        expect([m.status, m.mode]).toEqual(['running', 'paper']);
        expect(await nessunLive()).toEqual([]);
    });

    it('A3 Safe → paper: tennis dalla scheda TENNIS (avvia «solo tennis»), poi base/esatto/punta dalla scheda CALCIO (si aggiungono), strategy_modes 6/6 paper', async () => {
        await foto('A3_safe_prima');
        let s = await monta('tennis');
        await clicca(s, 'cr-avvia-paper-safe-tennis');
        await attendi(async () => (await safe()).status === 'running');
        await foto('A3_safe_dopo_tennis');
        for (const v of ['base', 'esatto', 'punta'] as const) {
            await pausa(4000);
            s = await monta('calcio');
            await clicca(s, `cr-avvia-paper-safe-${v}`);
            await attendi(async () => ((P(await safe()).variants ?? []) as string[]).includes(v));
            await foto(`A3_safe_dopo_${v}`);
        }
        const f = await safe();
        const sm = (P(f).strategy_modes ?? {}) as Riga;
        ora('safe', f, `variants=${JSON.stringify(P(f).variants)} strategy_modes=${JSON.stringify(sm)}`);
        salvaEsito('A3_safe', { status: f.status, mode: f.mode, variants: P(f).variants, strategy_modes: sm });
        expect([f.status, f.mode]).toEqual(['running', 'paper']);
        expect([...((P(f).variants ?? []) as string[])].sort()).toEqual(['base', 'esatto', 'punta', 'tennis']);
        expect(['base', 'esatto', 'punta', 'tennis', 'model', 'manual'].map((k) => sm[k])).toEqual(Array(6).fill('paper'));
        expect(await nessunLive()).toEqual([]);
    });

    it('A3b Safe: riaccende base, esatto, punta dalla scheda CALCIO (la scheda tennis è «solo tennis» per costruzione, comandiBot.ts:89-99)', async () => {
        await foto('A3b_safe_prima');
        for (const v of ['base', 'esatto', 'punta'] as const) {
            await pausa(4000);
            const s = await monta('calcio');
            await clicca(s, `cr-avvia-paper-safe-${v}`);
            await attendi(async () => ((P(await safe()).variants ?? []) as string[]).includes(v));
            await foto(`A3b_safe_dopo_${v}`);
        }
        const f = await safe();
        const sm = (P(f).strategy_modes ?? {}) as Riga;
        ora('safe (riaccese base/esatto/punta)', f, `variants=${JSON.stringify(P(f).variants)} strategy_modes=${JSON.stringify(sm)}`);
        salvaEsito('A3b_safe', { status: f.status, mode: f.mode, variants: P(f).variants, strategy_modes: sm });
        expect([...((P(f).variants ?? []) as string[])].sort()).toEqual(['base', 'esatto', 'punta', 'tennis']);
        expect(['base', 'esatto', 'punta', 'tennis', 'model', 'manual'].map((k) => sm[k])).toEqual(Array(6).fill('paper'));
        expect(await nessunLive()).toEqual([]);
    });

    it('A4 4 bot tennis → paper', async () => {
        await foto('A4_tennis_prima');
        for (const k of BOT_TENNIS) {
            const s = await monta('tennis');
            await clicca(s, `cr-avvia-paper-${k}`);
            await attendi(async () => (await tennis(k)).status === 'running');
            const r = await tennis(k);
            ora(k, r, `stake=${r.stake}`);
            await pausa(1500);
        }
        const dopo = await foto('A4_tennis_dopo');
        const righe = dopo.tennis_bot_service_control as Riga[];
        salvaEsito('A4_tennis', { righe: righe.map((r) => [r.bot_key, r.status, r.mode, r.stake]) });
        expect(righe.map((r) => [r.status, r.mode, Number(r.stake)])).toEqual(Array(4).fill(['running', 'paper', 2]));
        expect(await nessunLive()).toEqual([]);
    });

    it('A5 scalper → paper (strategia di default della UI = quella della riga)', async () => {
        const prima = await foto('A5_scalper_prima');
        const s = await monta('calcio');
        await clicca(s, 'cr-avvia-paper-scalper');
        await attendi(async () => (await scalperSrv()).status === 'running');
        const dopo = await foto('A5_scalper_dopo');
        const c = dopo.scalper_service_control as Riga;
        ora('scalper', c, `strategia=${c.strategia} stake=${c.stake}`);
        salvaEsito('A5_scalper', { status: c.status, mode: c.mode, strategia_prima: (prima.scalper_service_control as Riga).strategia, strategia: c.strategia, stake: c.stake });
        expect([c.status, c.mode, c.strategia, Number(c.stake)]).toEqual(['running', 'paper', 'maker', 25]);
        expect(await nessunLive()).toEqual([]);
    });
});
