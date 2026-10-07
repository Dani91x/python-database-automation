// ============================================================================
// Test del GUSCIO v2 (components/shell). Cosa deve essere vero:
//   - ogni voce della sidebar porta a una rotta che ESISTE GIA' in App.tsx, e le
//     rotte dentro il guscio sono esattamente quelle protette di oggi meno il pop-out;
//   - il filtro Tutti/Calcio/Tennis nasconde solo voci; la barra si comprime;
//   - «Esci» fa cio' che fa oggi (signOut e poi la landing);
//   - la testata mostra lo stato SOLO dei canali che la pagina apre gia';
//   - «Torna alla grafica attuale» scrive ui.shell='off'; «Prova la nuova
//     grafica» compare solo sulle pagine interne e scrive 'v2';
//   - `data-nav-legacy` sta solo su elementi di navigazione, mai su comandi.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom';
import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import { join, relative } from 'node:path';

const auth = vi.hoisted(() => ({ signOut: vi.fn(async () => ({ error: null })) }));
vi.mock('@/integrations/supabase/client', () => ({ supabase: { auth } }));

const stati = vi.hoisted(() => ({ chiesti: [] as string[] }));
vi.mock('@/lib/localTransport', () => ({
    useLocalStatus: (sport: string) => {
        stati.chiesti.push(sport);
        return sport === 'omega' ? 'connected' : 'off';
    },
}));

import { AppShell } from './AppShell';
import { ProvaNuovaGrafica } from './ProvaNuovaGrafica';
import { NAV, ROTTE_NEL_GUSCIO, CANALI_DELLA_PAGINA } from './navigazione';

const SRC = (() => {
    for (const base of [process.cwd(), join(process.cwd(), 'frontend')]) {
        const p = join(base, 'src');
        if (existsSync(join(p, 'App.tsx'))) return p;
    }
    throw new Error('src/ non trovata');
})();
const APP = readFileSync(join(SRC, 'App.tsx'), 'utf-8');

function Dove() {
    const { pathname } = useLocation();
    return <div data-testid="dove">{pathname}</div>;
}

function renderGuscio(url: string) {
    return render(
        <MemoryRouter initialEntries={[url]}>
            <Routes>
                <Route path="/" element={<Dove />} />
                <Route element={<AppShell />}>
                    {ROTTE_NEL_GUSCIO.map((r) => <Route key={r} path={r} element={<Dove />} />)}
                </Route>
            </Routes>
        </MemoryRouter>,
    );
}

beforeEach(() => {
    localStorage.clear();
    stati.chiesti = [];
    auth.signOut.mockClear();
});

describe('sidebar: solo rotte esistenti', () => {
    it("ogni voce porta a una rotta gia' presente in App.tsx", () => {
        const voci = NAV.flatMap((g) => g.voci).filter((v) => v.rotta !== null);
        // 07/10: +1 «Replay tennis» (/tennis/replay) nella sezione Tennis
        expect(voci.length).toBe(24);
        for (const v of voci) {
            expect(APP, `${v.id}: la rotta ${v.rotta} non esiste in App.tsx`).toContain(`path="${v.rotta}"`);
        }
    });

    it("le rotte del guscio sono le protette di oggi tranne il pop-out, e il guscio le ha tutte", () => {
        // ramo di oggi: le rotte avvolte da ProtectedRoute
        const ramoOggi = APP.slice(APP.indexOf('function App()'));
        const oggi = [...ramoOggi.matchAll(/path="([^"]+)"\s*\n\s*element=\{\s*\n\s*<ProtectedRoute>/g)].map((m) => m[1]);
        // 07/10: +1 /tennis/replay (Replay Tennis)
        expect(oggi.length).toBe(22);
        expect([...oggi].filter((r) => r !== '/ladder-popout').sort()).toEqual([...ROTTE_NEL_GUSCIO].sort());
        // ramo del guscio: ogni rotta e' una figlia della layout route
        const guscio = APP.slice(APP.indexOf('function RotteGuscioV2'), APP.indexOf('function App()'));
        for (const r of ROTTE_NEL_GUSCIO) expect(guscio).toContain(`<Route path="${r}" element=`);
        // fuori dal guscio, sempre
        for (const r of ['/ladder-popout', '/', '/check-email', '/reset-password', '*']) {
            expect(guscio).toContain(`path="${r}"`);
        }
    });

    it('le voci portano dove dicono (clic su Omega -> /omega)', () => {
        renderGuscio('/board');
        fireEvent.click(screen.getByTestId('shell-voce-omega'));
        expect(screen.getByTestId('dove').textContent).toBe('/omega');
        expect(screen.getByTestId('shell-voce-omega').getAttribute('aria-current')).toBe('page');
    });

    it('Ladder pop-out apre la finestra a parte 560×860, come il bottone «stacca»', () => {
        const apri = vi.spyOn(window, 'open').mockImplementation(() => null);
        renderGuscio('/board');
        fireEvent.click(screen.getByTestId('shell-voce-ladder-popout'));
        expect(apri).toHaveBeenCalledWith('/ladder-popout', 'ladder_popout', expect.stringContaining('width=560,height=860'));
        expect(screen.getByTestId('dove').textContent).toBe('/board');
        apri.mockRestore();
    });
});

describe('sidebar: filtro e compressione', () => {
    it('Calcio nasconde il gruppo Tennis, Tennis nasconde il gruppo Calcio, Tutti li mostra', () => {
        renderGuscio('/board');
        expect(screen.getByTestId('shell-gruppo-calcio')).toBeInTheDocument();
        expect(screen.getByTestId('shell-gruppo-tennis')).toBeInTheDocument();
        fireEvent.click(screen.getByTestId('shell-filtro-calcio'));
        expect(screen.queryByTestId('shell-gruppo-tennis')).toBeNull();
        expect(screen.getByTestId('shell-gruppo-calcio')).toBeInTheDocument();
        fireEvent.click(screen.getByTestId('shell-filtro-tennis'));
        expect(screen.queryByTestId('shell-gruppo-calcio')).toBeNull();
        expect(screen.getByTestId('shell-gruppo-tennis')).toBeInTheDocument();
        // le voci comuni restano sempre
        expect(screen.getByTestId('shell-voce-control-room')).toBeInTheDocument();
        fireEvent.click(screen.getByTestId('shell-filtro-tutti'));
        expect(screen.getByTestId('shell-gruppo-calcio')).toBeInTheDocument();
        // il contenuto della pagina non cambia mai
        expect(screen.getByTestId('dove').textContent).toBe('/board');
    });

    it('la barra si comprime e si riespande; da compressa le voci hanno ancora un nome', () => {
        const { container } = renderGuscio('/board');
        const radice = container.querySelector('[data-shell="v2"]') as HTMLElement;
        expect(radice.getAttribute('data-compressa')).toBe('false');
        fireEvent.click(screen.getByTestId('shell-comprimi'));
        expect(radice.getAttribute('data-compressa')).toBe('true');
        expect(screen.getByRole('link', { name: 'Omega' })).toBeInTheDocument();
        fireEvent.click(screen.getByTestId('shell-comprimi'));
        expect(radice.getAttribute('data-compressa')).toBe('false');
    });

    it('Esci: signOut e poi la landing, come oggi', async () => {
        renderGuscio('/control-room');
        fireEvent.click(screen.getByTestId('shell-voce-esci'));
        await waitFor(() => expect(screen.getByTestId('dove').textContent).toBe('/'));
        expect(auth.signOut).toHaveBeenCalledTimes(1);
    });
});

describe('testata globale: sola lettura, nessun canale in piu\'', () => {
    it('sulle pagine senza canali non chiede lo stato di nessun canale', () => {
        renderGuscio('/analytics');
        expect(screen.queryByTestId('shell-canali')).toBeNull();
        expect(stati.chiesti).toEqual([]);
    });

    it('su Omega chiede solo il canale di Omega (quello che la pagina apre gia\') e lo dice com\'e\'', () => {
        renderGuscio('/omega');
        const c = screen.getByTestId('shell-canali');
        expect(within(c).getByTestId('shell-canale-omega').getAttribute('data-stato')).toBe('connesso');
        expect([...new Set(stati.chiesti)]).toEqual(['omega']);
    });

    it('in Control Room gli otto canali; spento = spento, mai verde finto', () => {
        renderGuscio('/control-room');
        expect([...new Set(stati.chiesti)].sort()).toEqual([...CANALI_DELLA_PAGINA['/control-room']].sort());
        expect(screen.getByTestId('shell-canale-calcio').getAttribute('data-stato')).toBe('spento');
    });

    it('«Torna alla grafica attuale» scrive ui.shell=off', () => {
        renderGuscio('/board');
        fireEvent.click(screen.getByTestId('shell-torna-grafica-attuale'));
        expect(localStorage.getItem('ui.shell')).toBe('off');
    });

    it('la testata dice dove sei', () => {
        renderGuscio('/storico/tennis');
        const t = screen.getByTestId('shell-testata');
        expect(within(t).getByText('Storico tennis')).toBeInTheDocument();
        expect(within(t).getByText('Tennis')).toBeInTheDocument();
    });
});

describe('«Prova la nuova grafica» (app attuale)', () => {
    function renderBottone(url: string) {
        return render(
            <MemoryRouter initialEntries={[url]}>
                <ProvaNuovaGrafica />
            </MemoryRouter>,
        );
    }

    it('compare su ogni pagina interna e scrive ui.shell=v2', () => {
        for (const r of ROTTE_NEL_GUSCIO) {
            const { unmount } = renderBottone(r);
            expect(screen.getByTestId('shell-prova-nuova-grafica'), r).toBeInTheDocument();
            unmount();
        }
        renderBottone('/control-room');
        fireEvent.click(screen.getByTestId('shell-prova-nuova-grafica'));
        expect(localStorage.getItem('ui.shell')).toBe('v2');
    });

    it('non compare su accesso, servizio, 404 e pop-out del ladder', () => {
        for (const r of ['/', '/check-email', '/reset-password', '/ladder-popout', '/nessuna']) {
            const { unmount } = renderBottone(r);
            expect(screen.queryByTestId('shell-prova-nuova-grafica'), r).toBeNull();
            unmount();
        }
    });
});

describe('data-nav-legacy: solo navigazione, mai comandi', () => {
    function sorgenti(dir: string): string[] {
        const out: string[] = [];
        for (const n of readdirSync(dir)) {
            const p = join(dir, n);
            if (statSync(p).isDirectory()) out.push(...sorgenti(p));
            else if (/\.tsx$/.test(n) && !/\.test\.tsx$/.test(n)) out.push(p);
        }
        return out;
    }

    it('ogni elemento marcato porta a una rotta (Link to= o navigate(...)) e nient\'altro', () => {
        const trovati: string[] = [];
        for (const f of sorgenti(SRC)) {
            const righe = readFileSync(f, 'utf-8').split(/\r?\n/);
            righe.forEach((riga, i) => {
                if (!/\bdata-nav-legacy\b/.test(riga) || /^\s*(\/\/|\*|\/\*)/.test(riga)) return;
                if (f.endsWith(join('shell', 'AppShell.tsx'))) return;
                const intorno = righe.slice(Math.max(0, i - 3), i + 4).join('\n');
                const naviga = /<Link to="\/[a-z-/]*"/.test(intorno) || /onClick=\{\(\) => navigate\('\/[a-z-/]*'\)\}/.test(intorno);
                expect(naviga, `${relative(SRC, f)}:${i + 1} data-nav-legacy su un elemento che non e' navigazione`).toBe(true);
                // mai su comandi operativi (l'elemento stesso e le sue righe vicine)
                const elemento = righe.slice(Math.max(0, i - 2), i + 3).join('\n');
                expect(elemento).not.toMatch(/signOut|handleLogout|bot-start|bot-stop|onStart|onStop|KILL|cashOut|cash-out|ModeToggle|setMode/);
                trovati.push(`${relative(SRC, f)}:${i + 1}`);
            });
        }
        // 6 brand + 5 «Dashboard» + Analytics «Dashboard» + Watchlist «Report» + Report «Watchlist»
        // + 4 bottoni del Cruscotto + brand e 5 bottoni di TennisNav (07/10: +«Replay») + brand di BotHeader
        expect(trovati.length).toBe(25);
    });
});
