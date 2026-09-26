// util.tsx — strumenti comuni della fase 3 sessione B: testo visibile, attese, salvataggio evidenze.
import { writeFileSync, mkdirSync } from 'node:fs';

export const OUT = process.env.SESSB_OUT
    ?? 'C:/Users/Admin/AppData/Local/Temp/claude/C--Users-Admin/7c9759a8-053b-4dc4-992d-684a21e04a05/scratchpad/sessB';

const BLOCK = new Set(['DIV', 'P', 'SECTION', 'ARTICLE', 'HEADER', 'FOOTER', 'LI', 'TR', 'TABLE', 'H1', 'H2', 'H3', 'H4', 'H5', 'BUTTON', 'NAV', 'UL', 'OL', 'ASIDE', 'MAIN', 'DL', 'DT', 'DD', 'LABEL', 'FORM', 'SUMMARY', 'DETAILS']);

export function visibleText(root: Element): string {
    const parts: string[] = [];
    const walk = (n: Node, depth: number) => {
        if (n.nodeType === Node.TEXT_NODE) {
            const t = (n.textContent || '').replace(/\s+/g, ' ').trim();
            if (t) parts.push(t);
            return;
        }
        if (n.nodeType !== Node.ELEMENT_NODE) return;
        const el = n as HTMLElement;
        if (el.tagName === 'SCRIPT' || el.tagName === 'STYLE' || el.hidden) return;
        if (el.tagName === 'SELECT') {
            const s = el as HTMLSelectElement;
            parts.push(`<select=${s.options[s.selectedIndex]?.text ?? ''} (${s.options.length} opz.)>`);
            return;
        }
        if (el.tagName === 'INPUT') {
            const i = el as HTMLInputElement;
            parts.push(`<input ${i.type}=${i.type === 'checkbox' ? String(i.checked) : i.value}>`);
            return;
        }
        const block = BLOCK.has(el.tagName) || el.tagName === 'TD' || el.tagName === 'TH';
        if (block) parts.push('\n' + '  '.repeat(Math.min(depth, 6)));
        const tid = el.getAttribute('data-testid');
        const title = el.getAttribute('title');
        if (tid) parts.push(`[${tid}]`);
        if (title) parts.push(`{title:${title}}`);
        for (const c of Array.from(el.childNodes)) walk(c, depth + (block ? 1 : 0));
        if (el.tagName === 'TD' || el.tagName === 'TH') parts.push(' | ');
    };
    walk(root, 0);
    return parts.join(' ').replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n');
}

export const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function save(name: string, content: string | unknown) {
    mkdirSync(OUT, { recursive: true });
    writeFileSync(`${OUT}/${name}`, typeof content === 'string' ? content : JSON.stringify(content, null, 1), 'utf8');
}

/** WebSocket: si ascolta (sola lettura) ma ogni send viene bloccato e registrato */
export const wsSends: string[] = [];
export function guardWebSocket() {
    // canale locale SPENTO (come src/test/setup.ts): nessun socket verso l'app accesa; le pagine
    // leggono dal DB (ripiego dichiarato). Ogni send tentato viene registrato.
    class WsSpento {
        static CONNECTING = 0; static OPEN = 1; static CLOSING = 2; static CLOSED = 3;
        readyState = 3; url: string; onopen = null; onclose = null; onmessage = null; onerror = null;
        constructor(u: string) { this.url = u; }
        send(d: unknown) { wsSends.push(String(d).slice(0, 200)); throw new Error('SESS-B: ws.send bloccato'); }
        close() { /* niente */ }
        addEventListener() { /* niente */ }
        removeEventListener() { /* niente */ }
    }
    (globalThis as unknown as { WebSocket: unknown }).WebSocket = WsSpento;
    // polyfill d'ambiente jsdom (non del codice dell'app): IntersectionObserver (framer-motion) e
    // ResizeObserver con un riquadro 900x400 (recharts ResponsiveContainer disegna davvero).
    const g = globalThis as unknown as Record<string, unknown>;
    g.IntersectionObserver = class {
        cb: (e: unknown[]) => void;
        constructor(cb: (e: unknown[]) => void) { this.cb = cb; }
        observe(t: Element) { this.cb([{ isIntersecting: true, intersectionRatio: 1, target: t }]); }
        unobserve() { /* */ } disconnect() { /* */ } takeRecords() { return []; }
    };
    g.ResizeObserver = class {
        cb: (e: unknown[]) => void;
        constructor(cb: (e: unknown[]) => void) { this.cb = cb; }
        observe(t: Element) { setTimeout(() => this.cb([{ target: t, contentRect: { width: 900, height: 400, top: 0, left: 0 } }]), 0); }
        unobserve() { /* */ } disconnect() { /* */ }
    };
    const proto = (globalThis as unknown as { HTMLElement: { prototype: Record<string, unknown> } }).HTMLElement.prototype;
    Object.defineProperty(proto, 'clientWidth', { configurable: true, get() { return 900; } });
    Object.defineProperty(proto, 'clientHeight', { configurable: true, get() { return 400; } });
    Object.defineProperty(proto, 'offsetWidth', { configurable: true, get() { return 900; } });
    Object.defineProperty(proto, 'offsetHeight', { configurable: true, get() { return 400; } });
    if (!(globalThis as unknown as { matchMedia?: unknown }).matchMedia) {
        g.matchMedia = () => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} });
    }
    const w = globalThis as unknown as { scrollTo?: unknown };
    w.scrollTo = () => {};
    (proto as Record<string, unknown>).scrollIntoView = () => {};
}
