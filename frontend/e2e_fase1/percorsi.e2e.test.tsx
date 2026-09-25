// ============================================================================
// percorsi.e2e.test.tsx — E2E REALE FASE 1 (APP SPENTA, BOT FERMI), 25/09/2026.
//
// Piano: PIANO_TEST_E2E_REALE_2026-09-25.md §3 (P01-P32). Ogni percorso:
//   1. fotografia PRIMA (python e2e.py foto Pxx_prima, SOLA LETTURA)
//   2. AZIONE dalla UI: componente VERO (`PannelloBot`, `RigaOrdiniReali`,
//      `RigaFreno`) montato in jsdom con i comandi VERI della Control Room
//      (`creaComandiControlRoom`, stesse funzioni di `pages/ControlRoom.tsx:286`)
//      e il client Supabase VERO (service role, `./clientVero.ts`); il clic e'
//      sul `data-testid` del piano. Dove il componente non e' montabile ad app
//      spenta si chiama la STESSA funzione TS della UI (dichiarato nel percorso).
//   3. riga DOPO dal DB (python e2e.py foto Pxx_dopo) e confronto con l'attesa
//   4. SONDA: le funzioni VERE dei servizi Python (sonda.py), senza avviarli
//   5. RIPRISTINO: gesto UI del piano + ripristino esatto del testo grezzo della
//      riga (python e2e.py ripristina Pxx_prima) e confronto byte per byte
//   6. esito con i numeri in e2e_fase1/Pxx_esito.json
// NESSUN servizio avviato, NESSUN ordine, nessuna riga `pending` lasciata.
// ============================================================================
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, fireEvent, act, cleanup, type RenderResult } from '@testing-library/react';
import { execFileSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

vi.mock('@/integrations/supabase/client', async () => {
    const m = await import('./clientVero');
    return { supabase: m.supabase };
});
const sveglie: { bot: string; motivo: string }[] = [];
vi.mock('@/lib/localChannel', async (importOriginal) => {
    const orig = await importOriginal<typeof import('@/lib/localChannel')>();
    return {
        ...orig,
        svegliaBot: (bot: string, motivo: string) => { sveglie.push({ bot, motivo }); },
    };
});

import { raw, chiamate, bloccate } from './clientVero';
import { PannelloBot } from '@/components/controlroom/PannelloBot';
import { RigaOrdiniReali } from '@/components/controlroom/RigaOrdiniReali';
import { RigaFreno } from '@/components/controlroom/RigaFreno';
import { righeInterruttori, type StatoBotPlancia } from '@/components/controlroom/righeBot';
import { creaComandiControlRoom } from '@/components/controlroom/comandiBot';
import {
    interruttoriDiSport, importiInterruttori, usciteInterruttori, conPosizioniAperte,
    usciteSessioniScalper, creaInterruttori, type SportBot,
} from '@/lib/interruttori';
import {
    fetchOmegaState, activateOmega, updateOmegaParams, stopOmega, omegaParamsPatch, OMEGA_PARAM_DEFAULTS,
} from '@/lib/omega';
import { fetchSafeState } from '@/lib/safeBot';
import { fetchMikeState, requestMike } from '@/lib/mike';
import {
    fetchTennisBotServices, setTennisBotUscite, armTennisBot, disarmTennisBot, requestTennisChiudiBot,
} from '@/lib/tennis';
import { fetchScalperControlRoom, statoBotScalper, attivaScalperAuto } from '@/lib/scalperControlRoom';
import { activateScalper } from '@/lib/scalper';
import { approvaPropostaOpportunita } from '@/lib/safeBot';
import { approvaProposta } from '@/lib/controlRoomProposte';
import { approvaPropostaOmega } from '@/lib/omegaProposte';
import { requestSafe } from '@/lib/safeBot';
import { BOT_TENNIS, type Bot } from '@/lib/controlRoom';
import { leggiVarianti, leggiModiStrategia } from '@/components/controlroom/useControlRoom';

// ------------------------------------------------------------------ percorsi file
const WT = resolve(__dirname, '../..');
const OUT = resolve(WT, 'AUDIT_2026-09-25/e2e_fase1');
const PY = resolve(WT, '.venv/Scripts/python.exe');
const E2E = resolve(OUT, 'strumenti/e2e.py');
const SONDA = resolve(OUT, 'strumenti/sonda.py');

function py(args: string[]): Record<string, unknown> {
    const out = execFileSync(PY, args, { cwd: WT, encoding: 'utf8', timeout: 120_000 });
    const righe = out.trim().split(/\r?\n/);
    return JSON.parse(righe[righe.length - 1]);
}
/** la fotografia PRIMA del percorso in corso: se il percorso si interrompe, afterEach ripristina a questa */
let primaAttiva: string | null = null;
const foto = (n: string) => {
    const r = py([E2E, 'foto', n]);
    if (n.endsWith('_prima') && primaAttiva == null) primaAttiva = n;
    return r;
};
const sonda = (n: string, quali: string) => py([SONDA, n, quali]);
const ripristinaA = (n: string) => py([E2E, 'ripristina', n]);
const confronta = (a: string, b: string) => py([E2E, 'confronta', a, b]) as {
    n_valori: number; n_grezzo: number; valori: { campo: string; prima: unknown; dopo: unknown }[]; grezzo_diversi: string[];
};
const imposta = (t: string, k: string, v: string, json: string) => py([E2E, 'imposta', t, k, v, json]);

// ------------------------------------------------------------------ referto
interface Esito {
    percorso: string; titolo: string; azione: string; passi: string[];
    asserzioni: { nome: string; atteso: unknown; ottenuto: unknown; ok: boolean }[];
    rpc: typeof chiamate; bloccate: string[]; sveglie: typeof sveglie;
    ripristino?: unknown; confronto_con_prima?: unknown; confronto_con_fotografia_iniziale?: unknown;
    esito?: 'OK' | 'KO';
}
let E: Esito;
/** rifiuti non gestiti dei comandi (`void esegui(...)` nella plancia): evidenza, non rumore */
const rifiuti: string[] = [];
process.on('unhandledRejection', (r) => { rifiuti.push(r instanceof Error ? `${r.name}: ${r.message}` : String(r)); });
function inizia(percorso: string, titolo: string, azione: string) {
    chiamate.length = 0; bloccate.length = 0; sveglie.length = 0; rifiuti.length = 0;
    E = { percorso, titolo, azione, passi: [], asserzioni: [], rpc: chiamate, bloccate, sveglie };
}
function passo(s: string) { E.passi.push(`${new Date().toISOString()} ${s}`); }
function verifica(nome: string, atteso: unknown, ottenuto: unknown, ok?: boolean) {
    const esito = ok ?? JSON.stringify(atteso) === JSON.stringify(ottenuto);
    E.asserzioni.push({ nome, atteso, ottenuto, ok: esito });
    return esito;
}
function chiudi(prima: string) {
    primaAttiva = null;
    E.ripristino = ripristinaA(prima);
    foto(`${E.percorso}_ripristino`);
    const c1 = confronta(prima, `${E.percorso}_ripristino`);
    // BASE: la fotografia di riferimento del giro (dopo la migrazione uscite_manuali_default applicata
    // dall'utente alle 18:45:22 UTC la base e' `fotografia_post_migrazione`)
    const BASE = process.env.E2E_BASE ?? 'fotografia_iniziale';
    const c2 = confronta(BASE, `${E.percorso}_ripristino`);
    E.confronto_con_prima = c1; E.confronto_con_fotografia_iniziale = { base: BASE, ...c2 };
    verifica('ripristino byte per byte = fotografia PRIMA (valori, testo grezzo)', [0, 0], [c1.n_valori, c1.n_grezzo]);
    verifica(`ripristino = fotografia di base ${BASE} (valori, testo grezzo)`, [0, 0], [c2.n_valori, c2.n_grezzo]);
    verifica('nessuna RPC fuori piano, nessuna scrittura diretta della UI', [], [...bloccate]);
    E.esito = E.asserzioni.every((a) => a.ok) ? 'OK' : 'KO';
    E.rpc = [...chiamate]; E.bloccate = [...bloccate]; E.sveglie = [...sveglie];
    (E as unknown as Riga).rifiuti_non_gestiti = [...rifiuti];
    writeFileSync(resolve(OUT, `${E.percorso}_esito.json`), JSON.stringify(E, null, 1), 'utf8');
    return E;
}

// ------------------------------------------------------------------ DB (letture)
type Riga = Record<string, unknown>;
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
const P = (r: Riga) => (r.params ?? {}) as Record<string, unknown>;

async function attendi(pred: () => Promise<boolean>, ms = 15_000, nome = 'condizione'): Promise<boolean> {
    const t0 = Date.now();
    while (Date.now() - t0 < ms) {
        if (await pred()) return true;
        await new Promise((r) => setTimeout(r, 250));
    }
    passo(`TIMEOUT in attesa di: ${nome}`);
    return false;
}
const pausa = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** chiavi di primo livello diverse fra due oggetti params */
function chiaviDiverse(a: Record<string, unknown>, b: Record<string, unknown>): string[] {
    const ks = new Set([...Object.keys(a), ...Object.keys(b)]);
    return [...ks].filter((k) => JSON.stringify(a[k]) !== JSON.stringify(b[k])).sort();
}
/** uguaglianza semantica profonda (ordine chiavi indifferente) */
function uguali(a: unknown, b: unknown): boolean {
    if (a === b) return true;
    if (typeof a !== typeof b || a == null || b == null) return false;
    if (Array.isArray(a)) return Array.isArray(b) && a.length === b.length && a.every((x, i) => uguali(x, (b as unknown[])[i]));
    if (typeof a === 'object') {
        const ka = Object.keys(a as object).sort(); const kb = Object.keys(b as object).sort();
        return uguali(ka, kb) && ka.every((k) => uguali((a as Riga)[k], (b as Riga)[k]));
    }
    return false;
}

// ------------------------------------------------------------------ la plancia VERA
interface Vista {
    bots: StatoBotPlancia[];
    params: (b: Bot) => Record<string, unknown> | null;
    obiettivo: number | null;
}
/**
 * 'effettivi' = come la Control Room (useControlRoom.ts:2199-2203): varianti e modi di Safe dai parametri
 * EFFETTIVI pubblicati dal servizio (`stats.params_effective`), ripiego `control.params`.
 * 'control' = SIMULA il servizio che ha gia' ripubblicato gli effettivi (= control.params) al suo giro:
 * ad app spenta gli effettivi sono quelli del 24/09 16:06 e non cambiano (reperto dichiarato in P11).
 */
let fonteSafe: 'effettivi' | 'control' = 'effettivi';
async function caricaStato(): Promise<Vista> {
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
            // STESSE funzioni di useControlRoom.ts:2199-2203
            varianti: leggiVarianti(sc0?.params as Riga,
                fonteSafe === 'effettivi' ? s.params_effective as Riga | null : null),
            modiStrategia: leggiModiStrategia(
                fonteSafe === 'effettivi' ? (sc0?.stats as Riga | undefined)?.params_effective as Riga | null : null,
                sc0?.params as Riga),
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
    bots.push({
        ...base('scalper', null), inCorsa: st.inCorsa, modalita: st.modalita, stato: st.stato,
        nota: 'riga scalper (useControlRoom.ts:2303-2361)',
    });
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
async function monta(sport: SportBot, conOrdini = false): Promise<RenderResult> {
    if (montato) { montato.unmount(); montato = null; }
    const v = await caricaStato();
    const servizio = (b: Bot) => {
        const s = v.bots.find((x) => x.bot === b);
        return s == null ? null : { inCorsa: s.inCorsa, modalita: s.modalita, varianti: s.varianti, modiStrategia: s.modiStrategia };
    };
    // STESSA costruzione di pages/ControlRoom.tsx:264-304
    const comandi = creaComandiControlRoom({
        params: v.params, servizio,
        // ControlRoom.tsx:289: obiettivoGiorno della riga Omega (= control.daily_goal) ?? vm.obiettivo
        obiettivoOmega: () => v.obiettivo,
    }, () => { /* vm.ricarica: il test rimonta a ogni passo */ }, sport);
    const lista = interruttoriDiSport(sport);
    const righe = righeInterruttori(v.bots, sport);
    const importi = importiInterruttori(lista, v.params);
    const uscite = conPosizioniAperte(usciteInterruttori(lista, v.params), [], Date.now());
    const serviziAccesi = v.bots.filter((b) => b.inCorsa).map((b) => ({ bot: b.bot, modalita: b.modalita }));
    await act(async () => {
        montato = render(
            <PannelloBot righe={righe} importi={importi} comandi={comandi} uscite={uscite}
                serviziAccesi={serviziAccesi} ambito={sport}
                ordiniReali={conOrdini ? <><RigaOrdiniReali /><RigaFreno /></> : undefined} />,
        );
    });
    return montato as unknown as RenderResult;
}
async function clicca(s: RenderResult, id: string) {
    const el = s.queryByTestId(id);
    if (!el) throw new Error(`pulsante assente a video: ${id}`);
    if ((el as HTMLButtonElement).disabled) throw new Error(`pulsante DISABILITATO: ${id}`);
    passo(`clic ${id} («${el.textContent?.trim()}»)`);
    await act(async () => { fireEvent.click(el); });
}
async function scrivi(s: RenderResult, id: string, valore: string) {
    const el = s.getByTestId(id);
    passo(`scrive «${valore}» in ${id}`);
    await act(async () => { fireEvent.change(el, { target: { value: valore } }); });
}
const testoDi = (s: RenderResult, id: string) => s.queryByTestId(id)?.textContent?.trim() ?? null;

afterEach(async () => {
    if (montato) { montato.unmount(); montato = null; }
    cleanup();
    fonteSafe = 'effettivi';
    await pausa(300);
    if (primaAttiva != null) {
        // percorso INTERROTTO (eccezione): ripristino esatto comunque, esito KO con l'evidenza
        const prima = primaAttiva;
        passo(`percorso interrotto: ripristino a ${prima}`);
        chiudi(prima);
        E.esito = 'KO';
        writeFileSync(resolve(OUT, `${E.percorso}_esito.json`), JSON.stringify(E, null, 1), 'utf8');
    }
});

// ============================================================================
describe('FASE 1 — percorsi UI -> RPC -> DB -> servizio (app spenta)', () => {

    // ------------------------------------------------------------- OMEGA
    it('P01-P03 Omega: avvia in prova, doppio consenso soldi veri, passa a prova, ferma', async () => {
        inizia('P01_P03', 'Omega avvia/modalita/ferma', 'UI jsdom: PannelloBot (Control Room, scheda calcio) + comandi veri');
        foto('P01_prima');
        const o0 = await omega();
        // P01
        let s = await monta('calcio');
        verifica('P01 riga Omega a video prima: stato', 'fermo', testoDi(s, 'cr-bot-stato-omega'));
        await clicca(s, 'cr-avvia-paper-omega');
        await attendi(async () => (await omega()).status === 'running', 15_000, 'omega running');
        foto('P01_dopo');
        const o1 = await omega();
        verifica('P01 status', 'running', o1.status);
        verifica('P01 mode', 'paper', o1.mode);
        verifica('P01 daily_goal = fotografia', o0.daily_goal, o1.daily_goal);
        verifica('P01 params IDENTICI alla fotografia (chiavi diverse)', [], chiaviDiverse(P(o0), P(o1)));
        verifica('P01 error NULL', null, o1.error);
        verifica('P01 stopped_at NULL', null, o1.stopped_at);
        verifica('P01 started_at aggiornato (entro 60 s)', true,
            Date.now() - Date.parse(String(o1.started_at)) < 60_000);
        const rpc01 = chiamate.find((c) => c.rpc === 'omega_activate');
        verifica('P01 RPC omega_activate con p_mode=paper, p_daily_goal=obiettivo, p_params INTERI', true,
            !!rpc01 && (rpc01.args as Riga).p_mode === 'paper' && (rpc01.args as Riga).p_daily_goal === o0.daily_goal
            && uguali((rpc01.args as Riga).p_params, P(o0)));
        const og = await raw.from('omega_daily_goal').select('*').order('day', { ascending: false }).limit(1);
        E.passi.push(`effetto collaterale omega_snapshot_daily_goal: ${JSON.stringify(og.data)}`);
        const s01 = sonda('P01_sonda', 'omega');
        verifica('P01 SONDA read_control: running paper', ['running', 'paper'],
            [(s01.omega as Riga).status, (s01.omega as Riga).mode]);
        s = await monta('calcio');
        verifica('P01 riga a video dopo la rilettura: stato/modalita', ['in esecuzione', 'prova'],
            [testoDi(s, 'cr-bot-stato-omega'), testoDi(s, 'cr-bot-modalita-omega')]);

        // P02 — un SOLO clic su «passa a soldi veri» non scrive niente
        const prima02 = await omega();
        await clicca(s, 'cr-a-live-omega');
        const conf = s.queryByTestId('cr-conferma-live-omega') as HTMLButtonElement | null;
        verifica('P02 conferma comparsa e INERTE subito (troppoPresto)', [true, true], [!!conf, !!conf?.disabled]);
        await pausa(1500);
        const dopoUnClic = await omega();
        verifica('P02 un solo clic: mode e updated_at invariati', [prima02.mode, prima02.updated_at],
            [dopoUnClic.mode, dopoUnClic.updated_at]);
        foto('P02_prima');
        await clicca(s, 'cr-conferma-live-omega');
        await attendi(async () => (await omega()).mode === 'live', 15_000, 'omega live');
        foto('P02_dopo_live');
        const o2 = await omega();
        verifica('P02 dopo conferma: mode live, status invariato, params invariati', ['live', 'running', []],
            [o2.mode, o2.status, chiaviDiverse(P(o0), P(o2))]);
        const rpc02 = chiamate.filter((c) => c.rpc === 'omega_update_params').pop();
        verifica('P02 RPC omega_update_params(p_mode=live) senza p_params ne p_daily_goal', true,
            !!rpc02 && (rpc02.args as Riga).p_mode === 'live' && (rpc02.args as Riga).p_params == null
            && (rpc02.args as Riga).p_daily_goal == null);
        const s02 = sonda('P02_sonda_live', 'omega');
        verifica('P02 SONDA fra i due clic: running live', ['running', 'live'],
            [(s02.omega as Riga).status, (s02.omega as Riga).mode]);
        s = await monta('calcio');
        await clicca(s, 'cr-a-paper-omega');
        await attendi(async () => (await omega()).mode === 'paper', 15_000, 'omega paper');
        foto('P02_dopo_paper');
        const o3 = await omega();
        verifica('P02 passa a prova: mode paper, running', ['paper', 'running'], [o3.mode, o3.status]);

        // P03 — ferma
        s = await monta('calcio');
        const titolo = s.getByTestId('cr-ferma-omega').getAttribute('title');
        E.passi.push(`P03 title del pulsante ferma: ${titolo}`);
        await clicca(s, 'cr-ferma-omega');
        await attendi(async () => (await omega()).status !== 'running', 15_000, 'omega non running');
        foto('P03_dopo');
        const o4 = await omega();
        verifica('P03 status stopping (servizio spento: resta cosi), mode invariato', ['stopping', 'paper'], [o4.status, o4.mode]);
        const s03 = sonda('P03_sonda', 'omega');
        verifica('P03 SONDA: stopping', 'stopping', (s03.omega as Riga).status);
        s = await monta('calcio');
        verifica('P03 a video: «sta fermandosi» e nessun avvia', ['sta fermandosi', true, false],
            [testoDi(s, 'cr-bot-stato-omega'), !!s.queryByTestId('cr-in-arresto-omega'), !!s.queryByTestId('cr-avvia-paper-omega')]);
        const e = chiudi('P01_prima');
        expect(e.esito).toBe('OK');
    });

    it('P04 Omega: importo «stake minimo»', async () => {
        inizia('P04', 'Omega stake minimo', 'UI jsdom: PannelloBot, campo cr-importo-omega-min-stake + salva');
        foto('P04_prima');
        const o0 = await omega();
        const vecchio = Number(P(o0).min_stake);
        const nuovo = Math.round((vecchio + 0.1) * 100) / 100;
        let s = await monta('calcio');
        await scrivi(s, 'cr-importo-omega-min-stake', String(nuovo));
        await clicca(s, 'cr-importo-omega-min-stake-salva');
        await attendi(async () => Number(P(await omega()).min_stake) === nuovo, 15_000, 'min_stake nuovo');
        foto('P04_dopo');
        const o1 = await omega();
        verifica('P04 solo min_stake cambiato', ['min_stake'], chiaviDiverse(P(o0), P(o1)));
        verifica('P04 status/mode/daily_goal invariati', [o0.status, o0.mode, o0.daily_goal], [o1.status, o1.mode, o1.daily_goal]);
        const s04 = sonda('P04_sonda', 'omega');
        verifica('P04 SONDA resolve_params min_stake', nuovo, (s04.omega as Riga).min_stake_resolved);
        // ripristino dal campo stesso
        s = await monta('calcio');
        await scrivi(s, 'cr-importo-omega-min-stake', String(vecchio));
        await clicca(s, 'cr-importo-omega-min-stake-salva');
        await attendi(async () => Number(P(await omega()).min_stake) === vecchio, 15_000, 'min_stake vecchio');
        const o2 = await omega();
        verifica('P04 ripristino dal campo: params = fotografia', [], chiaviDiverse(P(o0), P(o2)));
        const e = chiudi('P04_prima');
        expect(e.esito).toBe('OK');
    });

    it('P05 Omega: uscite automatiche / manuali', async () => {
        inizia('P05', 'Omega uscite', 'UI jsdom: PannelloBot, blocco cr-uscite-omega');
        foto('P05_prima');
        const o0 = await omega();
        let s = await monta('calcio');
        const stato0 = testoDi(s, 'cr-uscite-stato-omega');
        verifica('P05 a video prima = DB (avvisa_e_proponi -> manuali)',
            P(o0).uscite_protezione === 'automatico' ? 'automatiche' : 'manuali', (stato0 ?? '').split(' ')[0]);
        // verso automatiche: serve la conferma (secondo clic)
        await clicca(s, 'cr-uscite-cambia-omega');
        await pausa(800);
        const invariato = await omega();
        verifica('P05 primo clic (passa ad automatiche) non scrive', o0.updated_at, invariato.updated_at);
        await clicca(s, 'cr-uscite-conferma-omega');
        await attendi(async () => P(await omega()).uscite_protezione === 'automatico', 15_000, 'automatico');
        foto('P05_dopo_automatiche');
        const o1 = await omega();
        verifica('P05 uscite_protezione = automatico e nient\'altro', ['uscite_protezione'], chiaviDiverse(P(o0), P(o1)));
        const s05 = sonda('P05_sonda_automatiche', 'omega');
        verifica('P05 SONDA modo_uscite', 'automatico', (s05.omega as Riga).modo_uscite);
        s = await monta('calcio');
        verifica('P05 a video dopo: automatiche', 'automatiche', (testoDi(s, 'cr-uscite-stato-omega') ?? '').split(' ')[0]);
        await clicca(s, 'cr-uscite-cambia-omega');
        await attendi(async () => P(await omega()).uscite_protezione === 'avvisa_e_proponi', 15_000, 'avvisa');
        foto('P05_dopo_manuali');
        const o2 = await omega();
        // la fotografia puo' NON avere la chiave (vale il default del servizio, omega_config): il ritorno la
        // scrive ESPLICITA con lo stesso valore. Si verifica l'equivalenza col servizio (sonda) e si dichiara.
        const dd = chiaviDiverse(P(o0), P(o2));
        E.passi.push(`P05 ritorno: chiavi diverse dalla fotografia ${JSON.stringify(dd)}; uscite_protezione foto=${JSON.stringify(P(o0).uscite_protezione)} dopo=${JSON.stringify(P(o2).uscite_protezione)}`);
        verifica('P05 ritorno a manuali: params = fotografia, salvo uscite_protezione resa esplicita col valore di default',
            true, dd.length === 0 || (dd.length === 1 && dd[0] === 'uscite_protezione' && P(o0).uscite_protezione === undefined
                && P(o2).uscite_protezione === 'avvisa_e_proponi'));
        const s05b = sonda('P05_sonda_manuali', 'omega');
        verifica('P05 SONDA modo_uscite dopo', 'avvisa_e_proponi', (s05b.omega as Riga).modo_uscite);
        const e = chiudi('P05_prima');
        expect(e.esito).toBe('OK');
    });

    it('P06 Omega dalla pagina dedicata: stessa riga, stessi params', async () => {
        inizia('P06', 'Omega pagina dedicata', 'FUNZIONI TS della pagina: pages/Omega.tsx:168-173 (serverParams = control.params; params = {...OMEGA_PARAM_DEFAULTS, ...control.params}) e :286 activateOmega(mode, goal, omegaParamsPatch(serverParams, params)); stopOmega. Pagina intera non montata (sottoscrizioni, grafici).');
        foto('P06_prima');
        const o0 = await omega();
        const server = P(o0);
        const statoPagina = { ...(OMEGA_PARAM_DEFAULTS as unknown as Riga), ...server };
        const patch = omegaParamsPatch(server, statoPagina);
        verifica('P06 omegaParamsPatch(server, stato pagina) = params del server (nessuna chiave tolta o aggiunta)', true, uguali(patch, server));
        E.passi.push(`P06 chiavi del patch diverse dal server: ${JSON.stringify(chiaviDiverse(server, patch))}`);
        await activateOmega('paper', Number(o0.daily_goal), patch as never);
        const o1 = await omega();
        verifica('P06 stessa riga di P01: running paper, params identici', ['running', 'paper', []],
            [o1.status, o1.mode, chiaviDiverse(P(o0), P(o1))]);
        await updateOmegaParams({ mode: 'paper' });
        await stopOmega();
        const o2 = await omega();
        verifica('P06 stop dalla pagina: stopping', 'stopping', o2.status);
        const e = chiudi('P06_prima');
        expect(e.esito).toBe('OK');
    });

    // ------------------------------------------------------------- MIKE
    it('P07-P10 Mike: avvia prova, avvia soldi veri (doppio consenso), cambio modalita, ferma, uscite', async () => {
        inizia('P07_P10', 'Mike', 'UI jsdom: PannelloBot (scheda calcio) + comandi veri');
        foto('P07_prima');
        const m0 = await mike();
        let s = await monta('calcio');
        await clicca(s, 'cr-avvia-paper-mike');
        await attendi(async () => (await mike()).status === 'running', 15_000, 'mike running');
        foto('P07_dopo_paper');
        const m1 = await mike();
        verifica('P07 running paper, params identici', ['running', 'paper', []], [m1.status, m1.mode, chiaviDiverse(P(m0), P(m1))]);
        const r07 = chiamate.find((c) => c.rpc === 'mike_activate');
        verifica('P07 RPC mike_activate(p_mode=paper) SENZA p_params', true,
            !!r07 && (r07.args as Riga).p_mode === 'paper' && (r07.args as Riga).p_params == null);
        const s07 = sonda('P07_sonda', 'mike');
        verifica('P07 SONDA', ['running', 'paper'], [(s07.mike as Riga).status, (s07.mike as Riga).mode]);
        // P08 cambio modalita a caldo (doppio consenso)
        s = await monta('calcio');
        const u0 = (await mike()).updated_at;
        await clicca(s, 'cr-a-live-mike');
        await pausa(1200);
        verifica('P08 un clic su «passa a soldi veri» non scrive', u0, (await mike()).updated_at);
        await pausa(100);
        await clicca(s, 'cr-conferma-live-mike');
        await attendi(async () => (await mike()).mode === 'live', 15_000, 'mike live');
        foto('P08_dopo_live');
        const m2 = await mike();
        verifica('P08 live, status invariato, params identici', ['live', 'running', []], [m2.mode, m2.status, chiaviDiverse(P(m0), P(m2))]);
        const r08 = chiamate.filter((c) => c.rpc === 'mike_update_params').pop();
        verifica('P08 RPC mike_update_params(p_params INTERI letti, p_mode=live)', true,
            !!r08 && (r08.args as Riga).p_mode === 'live' && uguali((r08.args as Riga).p_params, P(m0)));
        const s08 = sonda('P08_sonda_live', 'mike');
        verifica('P08 SONDA live', ['running', 'live'], [(s08.mike as Riga).status, (s08.mike as Riga).mode]);
        s = await monta('calcio');
        await clicca(s, 'cr-a-paper-mike');
        await attendi(async () => (await mike()).mode === 'paper', 15_000, 'mike paper');
        // P09 ferma
        s = await monta('calcio');
        await clicca(s, 'cr-ferma-mike');
        await attendi(async () => (await mike()).status === 'stopping', 15_000, 'mike stopping');
        foto('P09_dopo');
        verifica('P09 stopping, paper', ['stopping', 'paper'], [(await mike()).status, (await mike()).mode]);
        // avvio con soldi veri da fermo: doppio consenso
        await imposta('mike_control', 'id', '1', JSON.stringify({ status: 'stopped' }));
        E.passi.push('preparazione: mike_control.status stopping -> stopped (lo farebbe il servizio al giro dopo)');
        s = await monta('calcio');
        const u1 = (await mike()).updated_at;
        await clicca(s, 'cr-avvia-live-mike');
        const c = s.queryByTestId('cr-conferma-avvio-live-mike') as HTMLButtonElement | null;
        verifica('P07 avvia soldi veri: conferma comparsa e inerte', [true, true], [!!c, !!c?.disabled]);
        await pausa(1200);
        verifica('P07 un clic su «avvia con soldi veri» non scrive', u1, (await mike()).updated_at);
        await clicca(s, 'cr-conferma-avvio-live-mike');
        await attendi(async () => (await mike()).status === 'running', 15_000, 'mike live running');
        foto('P07_dopo_live');
        const m3 = await mike();
        verifica('P07 dopo conferma: running live, params identici', ['running', 'live', []], [m3.status, m3.mode, chiaviDiverse(P(m0), P(m3))]);
        s = await monta('calcio');
        await clicca(s, 'cr-ferma-mike');
        await attendi(async () => (await mike()).status === 'stopping', 15_000, 'mike stopping 2');
        // P10 uscite
        s = await monta('calcio');
        const st10 = testoDi(s, 'cr-uscite-stato-mike');
        const s10a = sonda('P10_sonda_prima', 'mike');
        verifica('P10 a video = servizio (merge_params) prima', (s10a.mike as Riga).uscite_automatiche ? 'automatiche' : 'manuali',
            (st10 ?? '').split(' ')[0]);
        const auto0 = (s10a.mike as Riga).uscite_automatiche === true;
        await clicca(s, 'cr-uscite-cambia-mike');
        if (!auto0) { await pausa(300); await clicca(s, 'cr-uscite-conferma-mike'); }
        await attendi(async () => P(await mike()).uscite_automatiche === !auto0, 15_000, 'mike uscite');
        foto('P10_dopo');
        const m4 = await mike();
        verifica('P10 solo uscite_automatiche cambiata', ['uscite_automatiche'], chiaviDiverse(P(m0), P(m4)));
        const s10 = sonda('P10_sonda_dopo', 'mike');
        verifica('P10 SONDA merge_params uscite_automatiche', !auto0, (s10.mike as Riga).uscite_automatiche);
        s = await monta('calcio');
        await clicca(s, 'cr-uscite-cambia-mike');
        if (auto0) { await pausa(300); await clicca(s, 'cr-uscite-conferma-mike'); }
        await attendi(async () => P(await mike()).uscite_automatiche === auto0, 15_000, 'mike uscite ritorno');
        const e = chiudi('P07_prima');
        expect(e.esito).toBe('OK');
    });

    // ------------------------------------------------------------- SAFE
    it('P11-P14 + P16 + P17 + P18 Safe calcio', async () => {
        inizia('P11_P18', 'Safe calcio', 'UI jsdom: PannelloBot (scheda calcio) + creaComandiControlRoom (rilettura fresca di Safe dal DB)');
        foto('P11_prima');
        const f0 = await safe();
        const MODI6 = ['base', 'esatto', 'punta', 'tennis', 'model', 'manual'];
        // P16(a): model/manual a servizio FERMO -> rifiuto, nessuna scrittura
        let s = await monta('calcio');
        const haModel = !!s.queryByTestId('cr-avvia-paper-safe-model');
        E.passi.push(`P16a pulsante avvia in prova safe-model presente a servizio fermo: ${haModel}`);
        if (haModel) {
            await clicca(s, 'cr-avvia-paper-safe-model');
            await pausa(1500);
            verifica('P16a servizio fermo: nessuna scrittura (updated_at)', f0.updated_at, (await safe()).updated_at);
            verifica('P16a rifiuto SafeFermoPerStrumento dal comando', true, rifiuti.some((r) => /SafeFermoPerStrumento|fermo/i.test(r)));
            E.passi.push(`P16a rifiuti: ${JSON.stringify(rifiuti)}`);
        }
        // P11
        s = await monta('calcio');
        await clicca(s, 'cr-avvia-paper-safe-base');
        await attendi(async () => (await safe()).status === 'running', 15_000, 'safe running');
        foto('P11_dopo');
        const f1 = await safe();
        const sm1 = (P(f1).strategy_modes ?? {}) as Riga;
        verifica('P11 running paper variants=[base]', ['running', 'paper', ['base']], [f1.status, f1.mode, P(f1).variants]);
        verifica('P11 strategy_modes con TUTTE e 6 le chiavi, tutte paper', MODI6.map(() => 'paper'), MODI6.map((k) => sm1[k]));
        verifica('P11 resto dei params identico (solo variants/strategy_modes cambiano)', true,
            chiaviDiverse(P(f0), P(f1)).every((k) => ['variants', 'strategy_modes'].includes(k)));
        E.passi.push(`P11 chiavi params cambiate: ${chiaviDiverse(P(f0), P(f1)).join(',')}`);
        const s11 = sonda('P11_sonda', 'safe');
        verifica('P11 SONDA: running paper, variants [base], modalita tutte paper', ['running', 'paper', ['base'], true],
            [(s11.safe as Riga).status, (s11.safe as Riga).mode, (s11.safe as Riga).variants,
                Object.values((s11.safe as Riga).modalita_per_strategia as Riga).every((x) => x === 'paper')]);
        // P12: esatto sulla STESSA plancia (snapshot vecchio: servizio fermo, solo il DB e' fresco) entro 1-2 s
        await clicca(s, 'cr-avvia-paper-safe-esatto');
        await attendi(async () => JSON.stringify(P(await safe()).variants) !== JSON.stringify(['base']), 15_000, 'variants cambiate');
        foto('P12_dopo');
        const f2 = await safe();
        verifica('P12 reperto A: variants = [base, esatto] (base NON sparito)', ['base', 'esatto'], [...(P(f2).variants as string[])].sort());
        verifica('P12 started_at invariato (safe_update_params, non activate)', f1.started_at, f2.started_at);
        const r12 = chiamate.filter((c) => c.rpc.startsWith('safe_')).pop();
        verifica('P12 RPC safe_update_params', 'safe_update_params', r12?.rpc);
        // OSSERVAZIONE (app spenta): la plancia legge varianti/modi dagli EFFETTIVI del servizio.
        fonteSafe = 'effettivi';
        s = await monta('calcio');
        E.passi.push(`OSS-EFF a video con gli effettivi del servizio (vecchi, 24/09): base=${testoDi(s, 'cr-bot-stato-safe-base')} `
            + `esatto=${testoDi(s, 'cr-bot-stato-safe-esatto')} punta=${testoDi(s, 'cr-bot-stato-safe-punta')}`);
        verifica('OSS-EFF: ad app spenta la riga «Safe punta» appare «in esecuzione» anche se il DB dice variants=[base,esatto] (effettivi del 24/09)',
            'in esecuzione', testoDi(s, 'cr-bot-stato-safe-punta'));
        fonteSafe = 'control';
        E.passi.push('da qui la plancia di Safe si costruisce da control.params (come dopo il giro del servizio)');
        // P16(b): model live con doppio consenso a servizio acceso
        s = await monta('calcio');
        const idLiveModel = s.queryByTestId('cr-a-live-safe-model') ? 'cr-a-live-safe-model' : 'cr-avvia-live-safe-model';
        E.passi.push(`P16b pulsante soldi veri di safe-model: ${idLiveModel}`);
        await clicca(s, idLiveModel);
        const idConfModel = idLiveModel === 'cr-a-live-safe-model' ? 'cr-conferma-live-safe-model' : 'cr-conferma-avvio-live-safe-model';
        await pausa(500);
        await clicca(s, idConfModel);
        await attendi(async () => ((P(await safe()).strategy_modes ?? {}) as Riga).model === 'live', 15_000, 'model live');
        foto('P16_dopo_model_live');
        const f3 = await safe();
        const sm3 = P(f3).strategy_modes as Riga;
        verifica('P16b model live: tetto live, base/esatto paper, variants invariate', ['live', 'live', 'paper', 'paper', ['base', 'esatto']],
            [f3.mode, sm3.model, sm3.base, sm3.esatto, [...(P(f3).variants as string[])].sort()]);
        const s16 = sonda('P16_sonda_model_live', 'safe');
        const mps16 = (s16.safe as Riga).modalita_per_strategia as Riga;
        verifica('P16b SONDA modalita_di_strategia: model live, base paper, manual paper', ['live', 'paper', 'paper'],
            [mps16.model, mps16.base, mps16.manual]);
        s = await monta('calcio');
        await clicca(s, 'cr-a-paper-safe-model');
        await attendi(async () => (await safe()).mode === 'paper', 15_000, 'tetto paper');
        const f4 = await safe();
        verifica('P16c ritorno a prova: model paper, tetto paper', ['paper', 'paper'], [(P(f4).strategy_modes as Riga).model, f4.mode]);
        // P13 punta: accesa in prova, poi soldi veri
        s = await monta('calcio');
        await clicca(s, 'cr-avvia-paper-safe-punta');
        await attendi(async () => (P(await safe()).variants as string[]).includes('punta'), 15_000, 'punta accesa');
        s = await monta('calcio');
        await clicca(s, 'cr-a-live-safe-punta');
        await pausa(500);
        await clicca(s, 'cr-conferma-live-safe-punta');
        await attendi(async () => (await safe()).mode === 'live', 15_000, 'punta live');
        foto('P13_dopo_live');
        const f5 = await safe();
        const sm5 = P(f5).strategy_modes as Riga;
        verifica('P13 tetto live, punta live, base/esatto paper, tennis/model/manual invariati, running',
            ['live', 'live', 'paper', 'paper', sm1.tennis, 'paper', sm1.manual, 'running'],
            [f5.mode, sm5.punta, sm5.base, sm5.esatto, sm5.tennis, sm5.model, sm5.manual, f5.status]);
        const s13 = sonda('P13_sonda_live', 'safe');
        const mps = (s13.safe as Riga).modalita_per_strategia as Riga;
        verifica('P13 SONDA modalita_di_strategia punta live, base paper', ['live', 'paper'], [mps.punta, mps.base]);
        s = await monta('calcio');
        await clicca(s, 'cr-a-paper-safe-punta');
        await attendi(async () => (await safe()).mode === 'paper', 15_000, 'punta paper');
        const f6 = await safe();
        verifica('P13 passa a prova: punta paper, tetto paper', ['paper', 'paper'], [(P(f6).strategy_modes as Riga).punta, f6.mode]);
        // P17 uscite per strategia (base) e P18 stake per strategia (base)
        s = await monta('calcio');
        const st17 = testoDi(s, 'cr-uscite-stato-safe-base');
        const s17a = sonda('P17_sonda_prima', 'safe');
        const u0 = ((s17a.safe as Riga).uscite_per_strategia as Riga).base === true;
        verifica('P17 a video = servizio prima (base)', u0 ? 'automatiche' : 'manuali', (st17 ?? '').split(' ')[0]);
        const pUscPrima = await safe();
        await clicca(s, 'cr-uscite-cambia-safe-base');
        if (!u0) { await pausa(300); await clicca(s, 'cr-uscite-conferma-safe-base'); }
        await attendi(async () => ((P(await safe()).uscite_automatiche ?? {}) as Riga).base === !u0, 15_000, 'uscite base');
        foto('P17_dopo');
        const f7 = await safe();
        verifica('P17 cambia solo uscite_automatiche', ['uscite_automatiche'], chiaviDiverse(P(pUscPrima), P(f7)));
        const s17 = sonda('P17_sonda_dopo', 'safe');
        verifica('P17 SONDA uscite_automatiche_di(base)', !u0, ((s17.safe as Riga).uscite_per_strategia as Riga).base);
        s = await monta('calcio');
        const stakeId = 'cr-importo-safe-base-stake-per-strategia-base';
        const pStake = await safe();
        const vecchio = Number(((P(pStake).stake as Riga)?.per_strategia as Riga)?.base);
        const nuovo = vecchio + 0.5;
        await scrivi(s, stakeId, String(nuovo));
        await clicca(s, `${stakeId}-salva`);
        await attendi(async () => Number(((P(await safe()).stake as Riga)?.per_strategia as Riga)?.base) === nuovo, 15_000, 'stake base');
        foto('P18_dopo');
        const f8 = await safe();
        verifica('P18 solo la chiave stake cambia', ['stake'], chiaviDiverse(P(pStake), P(f8)));
        const ps0 = (P(pStake).stake as Riga); const ps1 = (P(f8).stake as Riga);
        verifica('P18 dentro stake cambia solo per_strategia.base', [['per_strategia'], ['base']],
            [chiaviDiverse(ps0, ps1), chiaviDiverse(ps0.per_strategia as Riga, ps1.per_strategia as Riga)]);
        const s18 = sonda('P18_sonda', 'safe');
        verifica('P18 SONDA stake per_strategia.base', nuovo, ((s18.safe as Riga).stake_per_strategia as Riga).base);
        // P14: spegnere tutto, l'ultima per ultima
        for (const id of ['safe-esatto', 'safe-punta']) {
            s = await monta('calcio');
            if (s.queryByTestId(`cr-ferma-${id}`)) {
                await clicca(s, `cr-ferma-${id}`);
                await pausa(1500);
            }
        }
        const f9 = await safe();
        verifica('P14 dopo aver spento esatto e punta: variants=[base], running', [['base'], 'running'], [P(f9).variants, f9.status]);
        s = await monta('calcio');
        await clicca(s, 'cr-ferma-safe-base');
        await attendi(async () => (await safe()).status !== 'running', 15_000, 'safe stop');
        foto('P14_dopo');
        const f10 = await safe();
        verifica('P14 status stopping, mode paper, variants NON vuote (ultima scrittura)', ['stopping', 'paper', ['base']],
            [f10.status, f10.mode, P(f10).variants]);
        verifica('P14 RPC safe_stop (mai variants: [])', true, chiamate.some((c) => c.rpc === 'safe_stop')
            && !chiamate.some((c) => Array.isArray(((c.args as Riga)?.p_params as Riga | undefined)?.variants)
                && (((c.args as Riga).p_params as Riga).variants as unknown[]).length === 0));
        fonteSafe = 'effettivi';
        const e = chiudi('P11_prima');
        expect(e.esito).toBe('OK');
    });

    it('P16m Safe «a mano»: solo modalita, spegni rifiutato', async () => {
        inizia('P16m', 'Safe a mano', 'UI jsdom: PannelloBot scheda calcio (righe safe-base, safe-manual)');
        foto('P16m_prima');
        let s = await monta('calcio');
        await clicca(s, 'cr-avvia-paper-safe-base');
        await attendi(async () => (await safe()).status === 'running', 15_000, 'safe running');
        fonteSafe = 'control';
        s = await monta('calcio');
        verifica('P16m a mano: nessun pulsante «ferma» (StrumentoSenzaSpegnimento) o, se presente, rifiutato', true, true);
        E.passi.push(`P16m pulsanti safe-manual: ferma=${!!s.queryByTestId('cr-ferma-safe-manual')} a-live=${!!s.queryByTestId('cr-a-live-safe-manual')} uscite=${!!s.queryByTestId('cr-uscite-safe-manual')}`);
        verifica('P16m «a mano» non ha il blocco uscite', false, !!s.queryByTestId('cr-uscite-safe-manual'));
        if (s.queryByTestId('cr-ferma-safe-manual')) {
            const u = (await safe()).updated_at;
            await clicca(s, 'cr-ferma-safe-manual');
            await pausa(1500);
            verifica('P16m ferma su «a mano»: rifiutato, nessuna scrittura', [true, u],
                [rifiuti.some((r) => /StrumentoSenzaSpegnimento|spegn/i.test(r)), (await safe()).updated_at]);
            E.passi.push(`P16m rifiuti: ${JSON.stringify(rifiuti)}`);
            s = await monta('calcio');
        }
        await clicca(s, 'cr-a-live-safe-manual');
        await pausa(500);
        await clicca(s, 'cr-conferma-live-safe-manual');
        await attendi(async () => ((P(await safe()).strategy_modes ?? {}) as Riga).manual === 'live', 15_000, 'manual live');
        foto('P16m_dopo_live');
        const f1 = await safe();
        const sm = P(f1).strategy_modes as Riga;
        verifica('P16m manual live: tetto live, base paper, model paper, variants [base]', ['live', 'live', 'paper', 'paper', ['base']],
            [f1.mode, sm.manual, sm.base, sm.model, P(f1).variants]);
        const sd = sonda('P16m_sonda_live', 'safe');
        const mps = (sd.safe as Riga).modalita_per_strategia as Riga;
        verifica('P16m SONDA: manual live, base paper', ['live', 'paper'], [mps.manual, mps.base]);
        s = await monta('calcio');
        await clicca(s, 'cr-a-paper-safe-manual');
        await attendi(async () => (await safe()).mode === 'paper', 15_000, 'paper');
        verifica('P16m ritorno: manual paper, tetto paper', ['paper', 'paper'], [(P(await safe()).strategy_modes as Riga).manual, (await safe()).mode]);
        s = await monta('calcio');
        await clicca(s, 'cr-ferma-safe-base');
        await attendi(async () => (await safe()).status === 'stopping', 15_000, 'stopping');
        const e = chiudi('P16m_prima');
        expect(e.esito).toBe('OK');
    });

    it('P15 Safe tennis dalla scheda tennis («solo tennis»)', async () => {
        inizia('P15', 'Safe tennis solo tennis', 'UI jsdom: PannelloBot scheda TENNIS + creaComandiControlRoom(sport=tennis)');
        foto('P15_prima');
        const f0 = await safe();
        let s = await monta('tennis');
        verifica('P15 nessuna riga calcio nella scheda tennis', [false, false, false],
            [!!s.queryByTestId('cr-bot-riga-omega'), !!s.queryByTestId('cr-bot-riga-mike'), !!s.queryByTestId('cr-bot-riga-safe-base')]);
        await clicca(s, 'cr-avvia-paper-safe-tennis');
        await attendi(async () => (await safe()).status === 'running', 15_000, 'safe running');
        foto('P15_dopo');
        const f1 = await safe();
        const sm = P(f1).strategy_modes as Riga;
        verifica('P15 variants=[tennis], tutte le 6 modalita paper (model/manual portati a paper)',
            [['tennis'], 'paper', 'paper', 'paper', 'paper', 'paper', 'paper'],
            [P(f1).variants, sm.base, sm.esatto, sm.punta, sm.tennis, sm.model, sm.manual]);
        verifica('P15 stake.per_strategia.tennis = 3 (extraSoloTennis)', 3, ((P(f1).stake as Riga).per_strategia as Riga).tennis);
        const diverse = chiaviDiverse(P(f0), P(f1));
        verifica('P15 chiavi cambiate solo variants/strategy_modes/stake', true, diverse.every((k) => ['variants', 'strategy_modes', 'stake'].includes(k)));
        E.passi.push(`P15 chiavi cambiate: ${diverse.join(',')}`);
        const s15 = sonda('P15_sonda', 'safe');
        verifica('P15 SONDA variants [tennis], tennis paper', [['tennis'], 'paper'],
            [(s15.safe as Riga).variants, ((s15.safe as Riga).modalita_per_strategia as Riga).tennis]);
        // live e ritorno a prova: solo la modalita' del tennis cambia
        fonteSafe = 'control';
        E.passi.push('da qui la plancia di Safe si costruisce da control.params (effettivi del servizio vecchi ad app spenta, vedi P11 OSS-EFF)');
        s = await monta('tennis');
        await clicca(s, 'cr-a-live-safe-tennis');
        await pausa(500);
        await clicca(s, 'cr-conferma-live-safe-tennis');
        await attendi(async () => (await safe()).mode === 'live', 15_000, 'tennis live');
        foto('P15_dopo_live');
        const f2 = await safe();
        verifica('P15 live: tetto live, tennis live, altre paper', ['live', 'live', 'paper', 'paper'],
            [f2.mode, (P(f2).strategy_modes as Riga).tennis, (P(f2).strategy_modes as Riga).base, (P(f2).strategy_modes as Riga).model]);
        s = await monta('tennis');
        const pPrimaPaper = await safe();
        await clicca(s, 'cr-a-paper-safe-tennis');
        await attendi(async () => (await safe()).mode === 'paper', 15_000, 'tennis paper');
        const f3 = await safe();
        verifica('P15 passa a prova: cambia solo strategy_modes (stake ed entrate NON toccati)', ['strategy_modes'],
            chiaviDiverse(P(pPrimaPaper), P(f3)));
        s = await monta('tennis');
        await clicca(s, 'cr-ferma-safe-tennis');
        await attendi(async () => (await safe()).status === 'stopping', 15_000, 'safe stopping');
        const e = chiudi('P15_prima');
        expect(e.esito).toBe('OK');
    });

    // ------------------------------------------------------------- TENNIS
    it('P19-P21 bot tennis: interruttore, uscite, arma per partita', async () => {
        inizia('P19_P21', 'Bot tennis', 'UI jsdom: PannelloBot scheda TENNIS (P19); funzione TS setTennisBotUscite (P20: il componente UsciteTennis compare solo con stats.auto scritto dal ponte acceso); funzione TS armTennisBot/disarmTennisBot di TennisBotPanel (P21)');
        foto('P19_prima');
        const K = 'tennis_flb';
        const t0 = await tennis(K);
        const altri0 = await Promise.all(BOT_TENNIS.filter((b) => b !== K).map((b) => tennis(b)));
        let s = await monta('tennis');
        verifica('P19 riga stopping dal 24/09: a video «sta fermandosi», NESSUN avvia', ['sta fermandosi', true, false],
            [testoDi(s, `cr-bot-stato-${K}`), !!s.queryByTestId(`cr-in-arresto-${K}`), !!s.queryByTestId(`cr-avvia-paper-${K}`)]);
        await imposta('tennis_bot_service_control', 'bot_key', K, JSON.stringify({ status: 'stopped' }));
        E.passi.push(`preparazione: ${K} stopping -> stopped (come ripresa_ponte all'avvio dell'app)`);
        s = await monta('tennis');
        await clicca(s, `cr-avvia-paper-${K}`);
        await attendi(async () => (await tennis(K)).status === 'running', 15_000, 'tennis running');
        foto('P19_dopo_avvio');
        const t1 = await tennis(K);
        verifica('P19 running paper, stake/params conservati', ['running', 'paper', t0.stake, true],
            [t1.status, t1.mode, t1.stake, uguali(t1.params, t0.params)]);
        const altri1 = await Promise.all(BOT_TENNIS.filter((b) => b !== K).map((b) => tennis(b)));
        verifica('P19 gli altri tre invariati', true, altri0.every((a, i) => a.updated_at === altri1[i].updated_at));
        const s19 = sonda('P19_sonda_avvio', 'tennis');
        verifica('P19 SONDA stato_desiderato acceso paper', [true, 'paper'],
            [((s19.tennis as Riga)[K] as Riga).acceso, ((s19.tennis as Riga)[K] as Riga).mode]);
        s = await monta('tennis');
        await clicca(s, `cr-a-live-${K}`);
        await pausa(500);
        await clicca(s, `cr-conferma-live-${K}`);
        await attendi(async () => (await tennis(K)).mode === 'live', 15_000, 'tennis live');
        const t2 = await tennis(K);
        verifica('P19 cambio modalita: live, status running invariato', ['live', 'running'], [t2.mode, t2.status]);
        const r19 = chiamate.filter((c) => c.rpc === 'tennis_bot_service_update_params').pop();
        verifica('P19 RPC tennis_bot_service_update_params(p_mode=live, stake/params null)', true,
            !!r19 && (r19.args as Riga).p_mode === 'live' && (r19.args as Riga).p_stake == null && (r19.args as Riga).p_params == null);
        s = await monta('tennis');
        await clicca(s, `cr-a-paper-${K}`);
        await attendi(async () => (await tennis(K)).mode === 'paper', 15_000, 'tennis paper');
        s = await monta('tennis');
        const nuovoStake = Number(t0.stake) + 0.5;
        await scrivi(s, `cr-importo-${K}-stake`, String(nuovoStake));
        await clicca(s, `cr-importo-${K}-stake-salva`);
        await attendi(async () => Number((await tennis(K)).stake) === nuovoStake, 15_000, 'stake tennis');
        const t3 = await tennis(K);
        verifica('P19 stake colonna cambiata, status/mode/params invariati', [nuovoStake, 'running', 'paper', true],
            [Number(t3.stake), t3.status, t3.mode, uguali(t3.params, t0.params)]);
        s = await monta('tennis');
        await clicca(s, `cr-ferma-${K}`);
        await attendi(async () => (await tennis(K)).status === 'stopping', 15_000, 'tennis stopping');
        foto('P19_dopo_ferma');
        const t4 = await tennis(K);
        verifica('P19 ferma: stopping, stopped_at valorizzato', ['stopping', true], [t4.status, t4.stopped_at != null]);
        // P20 uscite tennis (funzione della UI)
        const u0 = t0.uscite_automatiche === true;
        await setTennisBotUscite(K, !u0);
        const t5 = await tennis(K);
        verifica('P20 uscite_automatiche invertita, nient\'altro (status/mode/stake/params)', [!u0, t4.status, t4.mode, Number(t4.stake), true],
            [t5.uscite_automatiche, t5.status, t5.mode, Number(t5.stake), uguali(t5.params, t4.params)]);
        const s20 = sonda('P20_sonda', 'tennis');
        verifica('P20 SONDA stato_desiderato uscite_automatiche', !u0, ((s20.tennis as Riga)[K] as Riga).uscite_automatiche);
        await setTennisBotUscite(K, u0);
        verifica('P20 ritorno', u0, (await tennis(K)).uscite_automatiche);
        // P21 arma per partita
        const EV = '36063889';
        await armTennisBot(EV, K, true, 2, {});
        const a1 = await leggiTbc(EV, K);
        verifica('P21 arma dry_run=true: requested, mode paper, dry_run true', ['requested', 'paper', true], [a1?.status, a1?.mode, a1?.dry_run]);
        let rearm: string | null = null;
        try { await armTennisBot(EV, K, false, 2, {}); } catch (e) { rearm = (e as Error).message; }
        verifica('P21 guardia anti re-arm su riga attiva', true, !!rearm && /attivo|chiusura/i.test(rearm));
        E.passi.push(`P21 re-arm rifiutato: ${rearm}`);
        await disarmTennisBot(EV, K);
        const a2 = await leggiTbc(EV, K);
        verifica('P21 disarmo: requested -> stopping', 'stopping', a2?.status);
        await raw.from('tennis_bot_control').update({ status: 'stopped' }).eq('event_id', EV).eq('bot_key', K);
        E.passi.push('preparazione: tennis_bot_control di prova stopping -> stopped (§5.1), poi riarmo con dry-run TOLTO');
        await armTennisBot(EV, K, false, 2, {});
        const a3 = await leggiTbc(EV, K);
        verifica('P21 (R1) dry-run tolto: la riga nasce COMUNQUE mode=paper, dry_run=false', ['requested', 'paper', false],
            [a3?.status, a3?.mode, a3?.dry_run]);
        foto('P21_dopo');
        await disarmTennisBot(EV, K);
        const e = chiudi('P19_prima');
        expect(e.esito).toBe('OK');
    });

    // ------------------------------------------------------------- SCALPER
    it('P22-P24 Scalper calcio: interruttore globale, rifiuto live a caldo, stake, uscite, card per partita', async () => {
        inizia('P22_P24', 'Scalper calcio', 'UI jsdom: PannelloBot scheda calcio (P22, P23); funzione TS attivaScalperAuto per il caso negativo (la UI non offre il cambio); funzione TS activateScalper della card (P24)');
        foto('P22_prima');
        const c0 = await scalperSrv();
        let s = await monta('calcio');
        await clicca(s, 'cr-avvia-paper-scalper');
        await attendi(async () => (await scalperSrv()).status === 'running', 15_000, 'scalper running');
        foto('P22_dopo_avvio');
        const c1 = await scalperSrv();
        verifica('P22 running paper, stake/strategia/params conservati', ['running', 'paper', c0.stake, c0.strategia, true],
            [c1.status, c1.mode, c1.stake, c1.strategia, uguali(c1.params, c0.params)]);
        const s22 = sonda('P22_sonda', 'scalper');
        verifica('P22 SONDA Db().servizio()', ['running', 'paper'], [(s22.scalper as Riga).status, (s22.scalper as Riga).mode]);
        s = await monta('calcio');
        verifica('P22 a video: nota «modalita solo all\'avvio» e nessun «passa a soldi veri»', [true, false],
            [!!s.queryByTestId('cr-modalita-all-avvio-scalper'), !!s.queryByTestId('cr-a-live-scalper')]);
        const u1 = c1.updated_at;
        let neg: string | null = null;
        try { await attivaScalperAuto('live'); } catch (e) { neg = (e as Error).message; }
        verifica('P22 negativo: live con interruttore acceso in paper -> eccezione, nessuna scrittura', [true, u1],
            [!!neg, (await scalperSrv()).updated_at]);
        E.passi.push(`P22 rifiuto: ${neg}`);
        await scrivi(s, 'cr-importo-scalper-stake', String(Number(c0.stake) + 5));
        await clicca(s, 'cr-importo-scalper-stake-salva');
        await attendi(async () => Number((await scalperSrv()).stake) === Number(c0.stake) + 5, 15_000, 'stake scalper');
        const c2 = await scalperSrv();
        verifica('P22 stake: solo la colonna, status/mode invariati', [Number(c0.stake) + 5, 'running', 'paper'],
            [Number(c2.stake), c2.status, c2.mode]);
        // P23 uscite
        s = await monta('calcio');
        const st23 = testoDi(s, 'cr-uscite-stato-scalper');
        E.passi.push(`P23 a video: ${st23}`);
        const auto0 = (c0.params as Riga | null)?.uscite_automatiche === true;
        await clicca(s, 'cr-uscite-cambia-scalper');
        if (!auto0) { await pausa(300); await clicca(s, 'cr-uscite-conferma-scalper'); }
        await attendi(async () => ((await scalperSrv()).params as Riga | null)?.uscite_automatiche === !auto0, 15_000, 'uscite scalper');
        foto('P23_dopo');
        const r23 = chiamate.filter((c) => c.rpc === 'scalper_uscite_automatiche').pop();
        verifica('P23 RPC scalper_uscite_automatiche, esito ok', ['ok', !auto0], [r23?.esito, (r23?.args as Riga)?.p_automatiche]);
        const s23 = sonda('P23_sonda', 'scalper');
        verifica('P23 SONDA params.uscite_automatiche', !auto0, (s23.scalper as Riga).uscite_automatiche);
        // ferma
        s = await monta('calcio');
        await clicca(s, 'cr-ferma-scalper');
        await attendi(async () => (await scalperSrv()).status === 'stopped', 15_000, 'scalper stopped');
        foto('P22_dopo_ferma');
        await attendi(async () => chiamate.some((c) => c.rpc === 'scalper_auto_stop'), 5_000, 'esito RPC registrato');
        const r22 =chiamate.filter((c) => c.rpc === 'scalper_auto_stop').pop();
        verifica('P22 ferma: stopped; scalper_auto_stop ok', ['stopped', 'ok'], [(await scalperSrv()).status, r22?.esito]);
        // P24 card per partita: evento non seguito -> rifiuto, nessuna riga
        const n0 = (await raw.from('scalper_control').select('event_id', { count: 'exact', head: true })).count;
        let neg24: string | null = null;
        // ScalperPanel.tsx:174 passa la modalita' di STRATEGIA (maker/bias/both) e dry_run=true (prova)
        try { await activateScalper('E2E_NON_SEGUITO_25092026', 'maker', true, 25, {}); } catch (e) { neg24 = (e as Error).message; }
        const n1 = (await raw.from('scalper_control').select('event_id', { count: 'exact', head: true })).count;
        verifica('P24 evento non seguito: eccezione «non seguito», nessuna riga', [true, n0], [!!neg24 && /seguit/i.test(neg24), n1]);
        E.passi.push(`P24 rifiuto: ${neg24}`);
        const e = chiudi('P22_prima');
        expect(e.esito).toBe('OK');
    });

    // ------------------------------------------------------------- TRASVERSALI
    it('P25 FERMA TUTTI', async () => {
        inizia('P25', 'Ferma tutti', 'UI jsdom: PannelloBot scheda calcio, cr-ferma-tutti (serviziAccesi da tutti i bot, come ControlRoom.tsx)');
        foto('P25_prima');
        const K = 'tennis_flb';
        let s = await monta('calcio');
        for (const id of ['cr-avvia-paper-omega', 'cr-avvia-paper-mike', 'cr-avvia-paper-safe-base', 'cr-avvia-paper-scalper']) {
            s = await monta('calcio');
            await clicca(s, id);
            await pausa(1500);
        }
        await imposta('tennis_bot_service_control', 'bot_key', K, JSON.stringify({ status: 'stopped' }));
        s = await monta('tennis');
        await clicca(s, `cr-avvia-paper-${K}`);
        await attendi(async () => (await tennis(K)).status === 'running', 15_000, 'tennis running');
        await attendi(async () => (await scalperSrv()).status === 'running' && (await safe()).status === 'running'
            && (await mike()).status === 'running' && (await omega()).status === 'running', 15_000, 'tutti accesi');
        foto('P25_accesi');
        const acc = [(await omega()).status, (await mike()).status, (await safe()).status, (await tennis(K)).status, (await scalperSrv()).status];
        verifica('P25 preparazione: 5 servizi accesi in prova', ['running', 'running', 'running', 'running', 'running'], acc);
        s = await monta('calcio');
        await clicca(s, 'cr-ferma-tutti');
        await attendi(async () => (await scalperSrv()).status === 'stopped' && (await tennis(K)).status === 'stopping'
            && (await omega()).status === 'stopping' && (await mike()).status === 'stopping' && (await safe()).status === 'stopping',
        20_000, 'tutti fermi');
        foto('P25_dopo');
        verifica('P25 Omega/Mike/Safe stopping, Safe mode paper, tennis stopping, scalper stopped',
            ['stopping', 'stopping', 'stopping', 'paper', 'stopping', 'stopped'],
            [(await omega()).status, (await mike()).status, (await safe()).status, (await safe()).mode, (await tennis(K)).status, (await scalperSrv()).status]);
        verifica('P25 nessun «non fermati» a video', false, !!s.queryByTestId('cr-non-fermati'));
        const e = chiudi('P25_prima');
        expect(e.esito).toBe('OK');
    });

    it('P26 Ordini reali OFF/PAPER/LIVE e P27 freno (kill-switch) dalla Control Room', async () => {
        inizia('P26_P27', 'Ordini reali + freno', 'UI jsdom: RigaOrdiniReali e RigaFreno montate dentro PannelloBot (prop ordiniReali, come ControlRoom.tsx:612)');
        foto('P26_prima');
        const b0 = await settings();
        let s = await monta('calcio', true);
        await attendi(async () => !!s.queryByTestId('cr-ordini-reali-effettivo'), 10_000, 'riga ordini letta');
        E.passi.push(`P26 a video al primo disegno (prima della lettura): effettivo=${testoDi(s, 'cr-ordini-reali-effettivo')} tetto=${testoDi(s, 'cr-ordini-reali-tetto')} non-letto=${testoDi(s, 'cr-ordini-reali-non-letto')}`);
        await attendi(async () => !(s.getByTestId('cr-ordini-reali-off') as HTMLButtonElement).disabled, 10_000, 'off abilitato');
        E.passi.push(`P26 a video dopo la lettura: effettivo=${testoDi(s, 'cr-ordini-reali-effettivo')} tetto=${testoDi(s, 'cr-ordini-reali-tetto')} fonte=${testoDi(s, 'cr-ordini-reali-fonte')} chi=${testoDi(s, 'cr-ordini-reali-chi')}`);
        verifica('P26 a video dopo la lettura = DB (scelta paper, tetto live -> effettivo PAPER)', true,
            /PAPER/i.test(testoDi(s, 'cr-ordini-reali-effettivo') ?? ''));
        E.passi.push(`P27 a video freno: stato=${testoDi(s, 'cr-freno-stato')} fonte=${testoDi(s, 'cr-freno-fonte')}`);
        await clicca(s, 'cr-ordini-reali-off');
        await attendi(async () => (await settings()).order_mode === 'off', 15_000, 'off');
        const b1 = await settings();
        verifica('P26 OFF: order_mode off, kill_switch INVARIATO', ['off', b0.kill_switch], [b1.order_mode, b1.kill_switch]);
        E.passi.push(`P26 order_mode_updated_by dopo OFF: ${JSON.stringify(b1.order_mode_updated_by)}`);
        const s26 = sonda('P26_sonda_off', 'ordini');
        verifica('P26 SONDA descrivi(env, db): effettivo OFF', 'OFF', ((s26.ordini as Riga).descrivi as Riga).effettivo);
        await attendi(async () => !(s.getByTestId('cr-ordini-reali-paper') as HTMLButtonElement).disabled, 10_000, 'paper abilitato');
        await clicca(s, 'cr-ordini-reali-paper');
        await attendi(async () => (await settings()).order_mode === 'paper', 15_000, 'paper');
        await attendi(async () => !!s.queryByTestId('cr-ordini-reali-live') && !(s.getByTestId('cr-ordini-reali-live') as HTMLButtonElement).disabled, 10_000, 'live abilitato');
        const ul = (await settings()).order_mode_updated_at;
        await clicca(s, 'cr-ordini-reali-live');
        const cl = s.queryByTestId('cr-ordini-reali-conferma-live') as HTMLButtonElement | null;
        verifica('P26 LIVE: conferma comparsa e inerte', [true, true], [!!cl, !!cl?.disabled]);
        await pausa(1200);
        verifica('P26 un clic su live non scrive', ul, (await settings()).order_mode_updated_at);
        await clicca(s, 'cr-ordini-reali-conferma-live');
        await attendi(async () => (await settings()).order_mode === 'live', 15_000, 'live');
        foto('P26_dopo_live');
        const bl = await settings();
        E.passi.push(`P26 riga dopo LIVE: order_mode=${bl.order_mode} updated_by=${JSON.stringify(bl.order_mode_updated_by)} tetto=${bl.order_mode_tetto} kill=${bl.kill_switch}`);
        await attendi(async () => /LIVE/i.test(testoDi(s, 'cr-ordini-reali-effettivo') ?? ''), 10_000, 'effettivo LIVE a video');
        verifica('P26 a video dopo LIVE: effettivo LIVE', true, /LIVE/i.test(testoDi(s, 'cr-ordini-reali-effettivo') ?? ''));
        const s26b = sonda('P26_sonda_live', 'ordini');
        verifica('P26 SONDA con scelta LIVE: effettivo = min(tetto .env LIVE, LIVE)', 'LIVE', ((s26b.ordini as Riga).descrivi as Riga).effettivo);
        await attendi(async () => !(s.getByTestId('cr-ordini-reali-paper') as HTMLButtonElement).disabled, 10_000, 'paper abilitato 2');
        await clicca(s, 'cr-ordini-reali-paper');
        await attendi(async () => (await settings()).order_mode === 'paper', 15_000, 'paper finale');
        const b2 = await settings();
        verifica('P26 finale PAPER, kill_switch invariato', ['paper', b0.kill_switch], [b2.order_mode, b2.kill_switch]);
        // P27 freno
        s = await monta('calcio', true);
        await attendi(async () => !!s.queryByTestId('cr-freno-tira'), 10_000, 'freno letto');
        const om = (await settings()).order_mode;
        await clicca(s, 'cr-freno-tira');
        await attendi(async () => (await settings()).kill_switch === true, 15_000, 'kill on');
        foto('P27_dopo_on');
        verifica('P27 tira il freno (nessuna conferma): kill_switch true, order_mode invariato', [true, om],
            [(await settings()).kill_switch, (await settings()).order_mode]);
        const s27 = sonda('P27_sonda_on', 'ordini');
        verifica('P27 SONDA motivo_kill_switch', 'db_kill_switch_attivo', (s27.ordini as Riga).motivo_kill_switch);
        await attendi(async () => !!s.queryByTestId('cr-freno-rilascia'), 10_000, 'rilascia');
        await clicca(s, 'cr-freno-rilascia');
        await pausa(500);
        await clicca(s, 'cr-freno-conferma-1');
        await pausa(500);
        verifica('P27 dopo 2 clic su 3 il freno e\' ancora tirato', true, (await settings()).kill_switch);
        await clicca(s, 'cr-freno-conferma-2');
        await attendi(async () => (await settings()).kill_switch === false, 15_000, 'kill off');
        verifica('P27 rilascio con doppia conferma: false', false, (await settings()).kill_switch);
        const s27b = sonda('P27_sonda_off', 'ordini');
        verifica('P27 SONDA motivo_kill_switch None', null, (s27b.ordini as Riga).motivo_kill_switch);
        const aud = await raw.from('betfair_live_audit').select('id').order('id', { ascending: false }).limit(1);
        E.passi.push(`C230 betfair_live_audit ultimo id dopo P26/P27: ${JSON.stringify(aud.data)} (fotografia: 96)`);
        const e = chiudi('P26_prima');
        expect(e.esito).toBe('OK');
    });

    it('P28-P31 contratti negativi delle richieste manuali (nessuna riga nuova)', async () => {
        inizia('P28_P31', 'Richieste manuali: contratto negativo', 'FUNZIONI TS della UI: approvaPropostaOpportunita/approvaProposta (safeBot.ts, controlRoomProposte.ts), approvaPropostaOmega (omegaProposte.ts), requestSafe, requestMike (mike.ts), requestTennisChiudiBot (tennis.ts)');
        foto('P28_prima');
        const err = async (f: () => Promise<unknown>) => { try { await f(); return null; } catch (e) { return (e as Error).message; } };
        const r1 = await err(() => approvaPropostaOpportunita(999999999));
        verifica('P28 safe_request_approve id inesistente -> eccezione «inesistente»', true, !!r1 && /inesistente/i.test(r1));
        const r2 = await err(() => approvaProposta(256));
        verifica('P28 proposta gia chiusa (id 256) -> errore a video (esigiOk)', true, !!r2);
        const r2b = await err(() => approvaPropostaOpportunita(256, { prezzoVisto: 1.5, contesto: { e2e: true } }));
        verifica('P28 proposta chiusa con prezzo/contesto -> errore', true, !!r2b);
        const r3 = await err(() => requestSafe('kind_inventato' as never, {}));
        verifica('P28 safe_request kind inventato -> «kind non valido»', true, !!r3 && /kind/i.test(r3));
        const r4 = await err(() => approvaPropostaOmega(999999999));
        verifica('P29 omega_request_approve id inesistente -> eccezione', true, !!r4);
        const r5 = await err(() => approvaPropostaOmega(48, { prezzoVisto: 2, contesto: { e2e: true } }));
        verifica('P29 proposta Omega non proposed (48) -> errore', true, !!r5);
        const r6 = await err(() => requestMike('approva_uscita' as never, { event_id: 'x' }));
        verifica('P30 mike approva_uscita senza chiave -> eccezione', true, !!r6 && /chiave/i.test(r6));
        const r7 = await err(() => requestMike('cashout' as never, {}));
        verifica('P30 mike cashout senza event_id -> eccezione', true, !!r7 && /event_id/i.test(r7));
        const r8 = await err(() => requestTennisChiudiBot({ bot: 'bot_inventato', event_id: '1', market_id: '1.1', mode: 'paper' }));
        verifica('P31 chiudi_bot bot non valido -> eccezione', true, !!r8 && /bot/i.test(r8));
        const r9 = await err(() => requestTennisChiudiBot({ bot: 'tennis_flb', event_id: '', market_id: '', mode: 'paper' }));
        verifica('P31 chiudi_bot senza event_id/market_id -> eccezione', true, !!r9);
        E.passi.push(`messaggi: ${JSON.stringify({ r1, r2, r2b, r3, r4, r5, r6, r7, r8, r9 })}`);
        foto('P28_dopo');
        const c = confronta('P28_prima', 'P28_dopo');
        verifica('P28-P31 nessuna riga nuova e nessuna riga toccata (max id code, righe 256/48/257/49)', [0, 0], [c.n_valori, c.n_grezzo]);
        const e = chiudi('P28_prima');
        expect(e.esito).toBe('OK');
    });
});

describe('SCOPERTI esercitabili ad app spenta', () => {
    it('C295 login/ruoli: /control-room senza sessione -> landing; RPC owner-only con chiave anon -> rifiutata', async () => {
        inizia('C295', 'Login e ruoli', 'UI jsdom: ProtectedRoute VERO con useAuth VERO (client senza sessione) su MemoryRouter; RPC owner-only con la chiave ANON di frontend/.env');
        const { MemoryRouter, Routes, Route } = await import('react-router-dom');
        const { ProtectedRoute } = await import('@/components/ProtectedRoute');
        let s!: RenderResult;
        await act(async () => {
            s = render(
                <MemoryRouter initialEntries={['/control-room']}>
                    <Routes>
                        <Route path="/" element={<div data-testid="landing">landing</div>} />
                        <Route path="/control-room" element={<ProtectedRoute><div data-testid="cr">CONTROL ROOM</div></ProtectedRoute>} />
                    </Routes>
                </MemoryRouter>,
            );
        });
        await attendi(async () => !!s.queryByTestId('landing') || !!s.queryByTestId('cr'), 10_000, 'rotta risolta');
        verifica('C295 /control-room senza sessione -> landing, Control Room NON mostrata', [true, false],
            [!!s.queryByTestId('landing'), !!s.queryByTestId('cr')]);
        const { isOwnerEmail } = await import('@/lib/auth-config');
        verifica('C295 isOwnerEmail: owner si, altro no', [true, false],
            [isOwnerEmail('daniele.ritrovato@gmail.com'), isOwnerEmail('qualcuno@example.com')]);
        const { readFileSync } = await import('node:fs');
        const fe = readFileSync(resolve(__dirname, '../../../../../frontend/.env'), 'utf8');
        const url = /VITE_SUPABASE_URL=(.*)/.exec(fe)?.[1]?.trim() ?? '';
        const anon = /VITE_SUPABASE_ANON_KEY=(.*)/.exec(fe)?.[1]?.trim() ?? '';
        const { createClient } = await import('@supabase/supabase-js');
        const ca = createClient(url, anon, { auth: { persistSession: false, autoRefreshToken: false } });
        const r1 = await ca.rpc('get_safe_state', {});
        const r2 = await ca.rpc('get_live_settings', {});
        const r3 = await ca.from('omega_control').select('id,status').limit(1);
        E.passi.push(`anon get_safe_state: ${r1.error?.message ?? 'DATI: ' + JSON.stringify(r1.data).slice(0, 80)}`);
        E.passi.push(`anon get_live_settings: ${r2.error?.message ?? 'DATI: ' + JSON.stringify(r2.data).slice(0, 80)}`);
        E.passi.push(`anon select omega_control: ${r3.error?.message ?? 'RIGHE: ' + JSON.stringify(r3.data)}`);
        verifica('C295/C275 chiave anon: RPC owner-only rifiutate, tabella di controllo non leggibile', [true, true, true],
            [!!r1.error, !!r2.error, !!r3.error || (Array.isArray(r3.data) && r3.data.length === 0)]);
        E.esito = E.asserzioni.every((a) => a.ok) ? 'OK' : 'KO';
        (E as unknown as Riga).rifiuti_non_gestiti = [...rifiuti];
        writeFileSync(resolve(OUT, 'C295_esito.json'), JSON.stringify(E, null, 1), 'utf8');
        expect(E.esito).toBe('OK');
    });
});

async function leggiTbc(ev: string, k: string): Promise<Riga | null> {
    const { data } = await raw.from('tennis_bot_control').select('*').eq('event_id', ev).eq('bot_key', k).maybeSingle();
    return (data as Riga | null) ?? null;
}
// tiene il riferimento a creaInterruttori (le pagine dei bot lo usano senza la rilettura fresca)
void creaInterruttori;
