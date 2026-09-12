// FOTOGRAFIA DELLA UI SUI DATI REALI (certificazione 12/09).
//
// Monta /omega, /safe-strategy e /mike col DB vero (sola lettura) e salva il
// TESTO VISIBILE di ogni scheda — vista iniziale, schede di primo livello e
// sotto-schede — in file di testo. Serve a rivedere quello che il trader vede
// davvero, senza doverlo leggere a schermo: e' cosi' che sono stati trovati i
// conteggi contraddittori, le etichette inglesi e gli zeri inventati.
//
//   cd frontend && npx vitest run --config vitest.cert.config.ts //       src/certification/zz_dump.cert.test.tsx
//
// I file finiscono nella cartella indicata da OUT (sotto): uno per sezione.
// Non asserisce nulla: e' uno strumento di ispezione, non un test di esito.
import { describe, it, expect, vi } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';
import { writeFileSync, mkdirSync } from 'node:fs';

vi.mock('@/integrations/supabase/client', async () => {
    const { supabase } = await import('./realClient');
    return { supabase };
});
vi.mock('sonner', () => ({
    toast: Object.assign((m: string) => { void m; }, { success: () => {}, warning: () => {}, error: () => {}, info: () => {} }),
}));

import Mike from '@/pages/Mike';
import Omega from '@/pages/Omega';
import SafeStrategy from '@/pages/SafeStrategy';
import { SafeStrategyProvider } from '@/components/safestrategy/SafeStrategyProvider';
import { CERT_RUN } from './realClient';

const OUT = 'C:/Users/Admin/AppData/Local/Temp/claude/C--Users-Admin/87f62b3b-5f21-4731-acbc-43bb282b246c/scratchpad/ui_dump';
const d = CERT_RUN ? describe : describe.skip;
const BLOCK = new Set(['DIV', 'P', 'SECTION', 'ARTICLE', 'HEADER', 'FOOTER', 'LI', 'TR', 'TABLE', 'H1', 'H2', 'H3', 'H4', 'H5', 'BUTTON', 'NAV', 'UL', 'OL', 'ASIDE', 'MAIN', 'DL', 'DT', 'DD', 'LABEL', 'FORM', 'SUMMARY', 'DETAILS']);

function visibleText(root: Element): string {
    const parts: string[] = [];
    const walk = (n: Node, depth: number) => {
        if (n.nodeType === Node.TEXT_NODE) {
            const t = (n.textContent || '').replace(/\s+/g, ' ').trim();
            if (t) parts.push(t);
            return;
        }
        if (n.nodeType !== Node.ELEMENT_NODE) return;
        const el = n as HTMLElement;
        if (el.tagName === 'SCRIPT' || el.tagName === 'STYLE' || el.tagName === 'SVG' || el.hidden) return;
        if (el.getAttribute('aria-hidden') === 'true') return;
        const block = BLOCK.has(el.tagName) || el.tagName === 'TD' || el.tagName === 'TH';
        if (block) parts.push('\n' + '  '.repeat(Math.min(depth, 6)));
        const tid = el.getAttribute('data-testid');
        const title = el.getAttribute('title');
        const aria = el.getAttribute('aria-label');
        if (tid) parts.push(`[${tid}]`);
        if (aria) parts.push(`{aria:${aria}}`);
        if (title) parts.push(`{title:${title}}`);
        for (const c of Array.from(el.childNodes)) walk(c, depth + (block ? 1 : 0));
        if (el.tagName === 'TD' || el.tagName === 'TH') parts.push(' | ');
    };
    walk(root, 0);
    return parts.join(' ').replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n');
}

async function settle(ms = 12_000) {
    await new Promise((r) => setTimeout(r, ms));
}

async function dumpPage(name: string, el: React.ReactElement, path: string) {
    mkdirSync(OUT, { recursive: true });
    const r = render(<HelmetProvider><MemoryRouter initialEntries={[path]}>{el}</MemoryRouter></HelmetProvider>);
    await waitFor(() => expect(document.querySelectorAll('[data-loading="true"]').length).toBe(0), { timeout: 90_000 }).catch(() => {});
    await settle();
    const out: string[] = [`===== ${name} — vista iniziale =====\n`, visibleText(document.body)];
    // tutte le schede/tab e i toggle principali
    // Schede di PRIMO livello (la barra piu' esterna) e, dentro ciascuna, i
    // suoi sotto-tab: si ri-legge la lista a ogni passo perche' il DOM cambia.
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    const topLabels = Array.from(document.querySelectorAll('[role="tablist"]'))
        .slice(0, 1)
        .flatMap((tl) => Array.from(tl.querySelectorAll('[role="tab"]')))
        .map((t) => (t.textContent || '').trim())
        .filter(Boolean);
    for (const label of topLabels) {
        const tab = Array.from(document.querySelectorAll('[role="tab"]'))
            .find((t) => (t.textContent || '').trim() === label) as HTMLElement | undefined;
        if (!tab) continue;
        try {
            await user.click(tab);
            await settle(8_000);
            out.push(`

===== ${name} — scheda "${label}" =====
`, visibleText(document.body));
        } catch (e) {
            out.push(`

===== ${name} — scheda "${label}" NON cliccabile: ${String(e).slice(0, 160)}`);
            continue;
        }
        // sotto-tab DENTRO la scheda attiva
        const panel = document.querySelector('[role="tabpanel"][data-state="active"]')
            ?? document.querySelector('[role="tabpanel"]:not([hidden])');
        const innerLabels = panel
            ? Array.from(panel.querySelectorAll('[role="tab"]'))
                .map((t) => (t.textContent || '').trim()).filter(Boolean)
            : [];
        for (const inner of innerLabels) {
            const it = panel
                ? Array.from(panel.querySelectorAll('[role="tab"]'))
                    .find((t) => (t.textContent || '').trim() === inner) as HTMLElement | undefined
                : undefined;
            if (!it) continue;
            try {
                await user.click(it);
                await settle(5_000);
                out.push(`

===== ${name} — "${label}" › "${inner}" =====
`, visibleText(document.body));
            } catch (e) {
                out.push(`

===== ${name} — sotto-scheda "${inner}" KO: ${String(e).slice(0, 160)}`);
            }
        }
    }
    writeFileSync(`${OUT}/${name}.txt`, out.join(''), 'utf8');
    r.unmount();
}

d('dump UI sui dati reali', () => {
    it('mike', async () => { await dumpPage('mike', <Mike />, '/mike'); }, 300_000);
    it('omega', async () => { await dumpPage('omega', <Omega />, '/omega'); }, 300_000);
    it('safe', async () => { await dumpPage('safe', <SafeStrategyProvider><SafeStrategy /></SafeStrategyProvider>, '/safe-strategy'); }, 300_000);
});
