// ============================================================================
// omega.cert.test.tsx — CERTIFICAZIONE della pagina /omega sui DATI REALI.
//
// Il client Supabase è quello vero (service role, SOLE letture, realtime
// stubbato): nessun dato è inventato. Si confronta ogni numero mostrato con il
// valore che la RPC ha appena restituito.
// ============================================================================
import { describe, it, expect, afterAll, vi } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';

vi.mock('@/integrations/supabase/client', async () => {
    const { supabase } = await import('./realClient');
    return { supabase };
});
const toasts = vi.hoisted(() => ({ errors: [] as string[] }));
vi.mock('sonner', () => ({
    toast: Object.assign(
        (m: string) => { void m; },
        {
            success: () => {},
            warning: () => {},
            error: (m: string, o?: { description?: string }) => {
                toasts.errors.push(`${m}${o?.description ? ` — ${o.description}` : ''}`);
            },
        },
    ),
}));

import Omega from '@/pages/Omega';
import { fetchOmegaState, fetchOmegaTrades } from '@/lib/omega';
import { fetchOmegaDaily } from '@/lib/dailyHistory';
import { groupTradesByMatch, filterMatchesForDay } from '@/lib/omegaMatches';
import { romeDay, dayLabel } from '@/lib/dailyHistory';
import { fmtMoney, fmtNum, fmtPctPoints } from '@/lib/format';
import { writeAttempts, CERT_RUN } from './realClient';
import { consoleCapture } from './setup.cert';
import { Report, text } from './report';

/** fuori da vitest.cert.config.ts i test si SALTANO (mai il DB reale in `npm test`) */
const d = CERT_RUN ? describe : describe.skip;
const rep = new Report('/omega — OMEGA (Correct Score LAY)');
afterAll(() => rep.print());

function renderPage() {
    return render(
        <HelmetProvider>
            <MemoryRouter initialEntries={['/omega']}>
                <Omega />
            </MemoryRouter>
        </HelmetProvider>,
    );
}

d('/omega sui dati reali', () => {
    it('forma della RPC + fallback della UI per i campi assenti', async () => {
        const st = await fetchOmegaState(60);
        const agg = (st.aggregates ?? {}) as Record<string, unknown>;
        rep.note(`get_omega_state: control=${st.control ? 'presente' : 'ASSENTE'} · aggregates=[${Object.keys(agg).sort().join(', ')}] · activity=${st.activity.length}`);
        rep.mark('goal_today (RPC)', 'numero', String(st.goal_today), st.goal_today != null);
        rep.mark('goal_snapshot (RPC v5)', 'true', String(st.goal_snapshot), st.goal_snapshot === true);
        if (st.goal_snapshot !== true) {
            rep.finding('MEDIUM', 'pages/Omega.tsx:475-479 (DayBar note)',
                "goal_snapshot assente → la barra mostra la nota «obiettivo non ancora storicizzato». FALLBACK PRESENTE (lib/omega.ts:957 forza false).");
        }
        rep.mark('activity_more (RPC v5)', 'numero', String(st.activity_more), true);
        rep.mark('activity_day (RPC v5)', 'YYYY-MM-DD', String(st.activity_day), st.activity_day != null);
        if (st.activity_day == null) {
            rep.finding('MEDIUM', 'pages/Omega.tsx:585-588 + Omega.tsx:391-394',
                "activity_day assente → filtro di giornata lato client (romeDayOf). FALLBACK PRESENTE, dichiarato nella UI.");
        }
        for (const k of ['locked_pnl_open', 'locked_pnl_open_today', 'reconciling_liability', 'live_now']) {
            const has = k in agg;
            rep.mark(`aggregates.${k}`, 'presente', has ? 'presente' : 'ASSENTE', has);
        }
        if (!('locked_pnl_open' in agg)) {
            rep.finding('HIGH', 'pages/Omega.tsx:519 (KpiRow condizionale)',
                'aggregates.locked_pnl_open assente e control.stats.locked_pnl_open assente → la RIGA KPI «P&L bloccato» + «In verifica su Betfair» NON viene renderizzata affatto (lockedOpen === null). Fallback = nascondere il dato, non stimarlo: serve omega_models_v5.sql.');
        }
        if (!('reconciling_liability' in agg)) {
            rep.finding('MEDIUM', 'pages/Omega.tsx:358',
                'aggregates.reconciling_liability assente → 0 (fallback presente): il sottotitolo della liability dice sempre «esposizione a coda», mai «in verifica su Betfair».');
        }
        expect(st.control).toBeTruthy();
    });

    it('render completo: nessun crash, nessun console.error, guscio presente', async () => {
        renderPage();
        await waitFor(() => expect(screen.queryByTestId('loading-state')).toBeNull(), { timeout: 60_000 });
        expect(screen.getByTestId('page-shell')).toBeInTheDocument();
        expect(screen.getByTestId('omega-daily-mission')).toBeInTheDocument();
        expect(screen.getAllByTestId('kpi-row')[0]).toBeInTheDocument();

        // header + chip di salute + banner di modalità + tab
        const status = text(screen.getByTestId('bot-status'));
        rep.mark('header stato bot (chip)', 'IN CORSA/FERMO/…', status || '(vuoto)', status.length > 0);
        expect(screen.getByTestId('bot-header')).toBeInTheDocument();
        const health = screen.getByTestId('service-health');
        rep.mark('chip salute servizio', 'presente', text(health).slice(0, 70), true);
        const banner = document.querySelector('[data-mode]');
        rep.mark('banner di modalità', 'presente (paper/live)', banner?.getAttribute('data-mode') ?? 'ASSENTE', Boolean(banner));
        expect(banner).toBeTruthy();
        for (const t of ['Missione', 'Automatico', 'Manuale', 'Storico']) {
            expect(screen.getByLabelText(t)).toBeInTheDocument();
        }
        rep.mark('tab presenti', 'Missione/Automatico/Manuale/Storico', 'tutti', true);

        rep.mark('console.error durante il render', '0', String(consoleCapture.errors.length), consoleCapture.errors.length === 0);
        if (consoleCapture.errors.length) {
            rep.finding('CRITICAL', 'pages/Omega.tsx (render)', `console.error: ${consoleCapture.errors.slice(0, 4).join(' | ')}`);
        }
        rep.mark('toast.error durante il caricamento', '0', String(toasts.errors.length), toasts.errors.length === 0);
        if (toasts.errors.length) {
            rep.finding('CRITICAL', 'pages/Omega.tsx (reload)', `toast.error: ${toasts.errors.slice(0, 3).join(' | ')}`);
        }
        rep.mark('tentativi di SCRITTURA sul DB', '0', String(writeAttempts.length), writeAttempts.length === 0);
        expect(writeAttempts).toEqual([]);
        expect(consoleCapture.errors).toEqual([]);
    });

    it('KPI e barra giornata = valori della RPC, formato italiano', async () => {
        const [st, trades] = await Promise.all([fetchOmegaState(60), fetchOmegaTrades(1200)]);
        const agg = (st.aggregates ?? {}) as Record<string, number | null>;
        const stats = (st.control?.stats ?? {}) as Record<string, number | null | boolean>;
        const realized = Number(agg.realized_today ?? stats.realized_today ?? 0);
        const realizedTotal = Number(agg.realized_profit ?? stats.realized_profit ?? 0);
        const goal = Number(st.goal_today ?? st.control?.daily_goal ?? 250);
        const openLiability = Number(agg.open_liability ?? stats.open_liability ?? 0);
        // `stats` può contenere booleani (bot_running): i contatori si leggono
        // come NUMERI o null, mai come "boolean passato a un formatter"
        const n = (v: unknown): number | null =>
            typeof v === 'number' && Number.isFinite(v) ? v : null;
        const legsToday = n(agg.legs_today) ?? n(stats.legs_today);
        const eventsToday = n(agg.events_today) ?? n(stats.events_today);
        const wonToday = n(agg.won_today) ?? n(stats.won_today);
        const lostToday = n(agg.lost_today) ?? n(stats.lost_today);
        const matchesTraded = Number(agg.matches_traded ?? stats.matches_traded ?? 0);

        renderPage();
        await waitFor(() => expect(screen.queryByTestId('loading-state')).toBeNull(), { timeout: 60_000 });

        // --- KPI «P&L oggi»
        const kpiPnl = screen.getByTestId('omega-kpi-pnl');
        rep.check('KPI «P&L oggi» (valore)', fmtMoney(realized, { signed: true }), text(kpiPnl.children[1]));
        rep.check('KPI «P&L oggi» (sottotitolo totale)', `totale storico ${fmtMoney(realizedTotal, { signed: true })}`, text(kpiPnl.children[2]));
        expect(text(kpiPnl.children[1])).toBe(fmtMoney(realized, { signed: true }));

        // --- KPI «Liability aperta»
        const kpiLiab = screen.getByTestId('omega-kpi-liability');
        rep.check('KPI «Liability aperta»', fmtMoney(openLiability), text(kpiLiab.children[1]));
        expect(text(kpiLiab.children[1])).toBe(fmtMoney(openLiability));

        // --- KPI «Operazioni oggi»
        const kpiLegs = screen.getByTestId('omega-kpi-legs');
        rep.check('KPI «Operazioni oggi» (valore)', legsToday != null ? fmtNum(legsToday) : '—', text(kpiLegs.children[1]));
        rep.check('KPI «Operazioni oggi» (V/P/vive/storico)',
            `${wonToday ?? 0}V · ${lostToday ?? 0}P · ${agg.live_now ?? stats.live_now ?? agg.matches_open ?? 0} partite vive · storico ${fmtNum(matchesTraded)}`,
            text(kpiLegs.children[2]));

        // --- KPI «Target / operazione» e «Eventi in finestra»
        rep.check('KPI «Target / operazione»', fmtMoney((stats.target_leg ?? stats.target_match) as number), text(screen.getByTestId('omega-kpi-target').children[1]));
        const running = st.control?.status === 'running' || st.control?.status === 'stopping';
        const statsFresh = stats.bot_running !== false && running;
        rep.check('KPI «Eventi in finestra»', statsFresh ? String(stats.events_total ?? '—') : '—', text(screen.getByTestId('omega-kpi-events').children[1]));

        // --- riga KPI «P&L bloccato» (solo con omega_models_v5)
        const lockedOpen = agg.locked_pnl_open ?? (stats.locked_pnl_open as number | null) ?? null;
        const lockedTile = screen.queryByTestId('omega-kpi-locked');
        rep.mark('KPI «P&L bloccato» presente', lockedOpen != null ? 'presente' : 'assente (atteso: RPC senza il campo)',
            lockedTile ? 'presente' : 'assente', (lockedOpen != null) === Boolean(lockedTile));

        // --- barra della giornata
        const bar = screen.getByTestId('omega-daily-mission');
        rep.check('Barra giornata — giorno operativo', dayLabel(romeDay(), { weekday: true }), text(screen.getByTestId('omega-operating-day')));
        const line = text(screen.getByTestId('omega-mission-line'));
        const counts = text(screen.getByTestId('omega-today-legs'));
        rep.check('Barra giornata — contatori partite/operazioni/V/P',
            `partite ${eventsToday} · operazioni ${legsToday} · ${wonToday ?? 0}V ${lostToday ?? 0}P`
            + (Number(agg.live_now ?? stats.live_now ?? agg.matches_open ?? 0) > 0
                ? ` · ${agg.live_now ?? stats.live_now ?? agg.matches_open} vive` : ''),
            counts);
        rep.mark('Barra giornata — obiettivo', `Obiettivo di oggi ${fmtMoney(goal)}`,
            line.includes(`Obiettivo di oggi ${fmtMoney(goal)}`) ? `Obiettivo di oggi ${fmtMoney(goal)}` : line.slice(0, 60),
            line.includes(`Obiettivo di oggi ${fmtMoney(goal)}`));
        rep.mark('Barra giornata — realizzato oggi', fmtMoney(realized, { signed: true }),
            line.includes(`realizzato oggi ${fmtMoney(realized, { signed: true })}`) ? fmtMoney(realized, { signed: true }) : line.slice(0, 80),
            line.includes(`realizzato oggi ${fmtMoney(realized, { signed: true })}`));
        const remaining = Math.max(0, goal - realized);
        if (remaining > 0) {
            rep.check('Barra giornata — «resta»', fmtMoney(remaining), text(within(bar).getByTestId('omega-remaining')));
        } else {
            rep.check('Barra giornata — obiettivo centrato', 'CENTRATO', text(within(bar).getByTestId('omega-goal-hit')));
        }
        // percentuale con la virgola
        const pct = fmtPctPoints(Math.max(0, Math.min(100, (realized / goal) * 100)), 1);
        const barText = text(bar);
        rep.mark('Barra giornata — percentuale (virgola)', pct, barText.includes(pct) ? pct : '(non trovata)', barText.includes(pct));
        rep.note(`riga giornata: ${line}`);

        // --- tabella partite: UNA riga per partita della giornata
        const user = userEvent.setup();
        await user.click(screen.getByLabelText('Automatico'));
        await waitFor(() => expect(screen.getByTestId('omega-matches-card')).toBeInTheDocument(), { timeout: 20_000 });
        const groups = filterMatchesForDay(groupTradesByMatch(trades), romeDay());
        const rows = screen.queryAllByTestId('omega-match-row');
        rep.check('Tabella partite — righe = partite di oggi', String(groups.length), String(rows.length));
        const eventIdsShown = rows.map((r) => r.getAttribute('data-event'));
        rep.check('Tabella partite — una riga per partita (event_id unici)', String(new Set(eventIdsShown).size), String(rows.length));
        rep.mark('Tabella partite — event_id = quelli raggruppati',
            groups.map((g) => g.event_id).join(','), eventIdsShown.join(','),
            groups.map((g) => g.event_id).sort().join(',') === [...eventIdsShown].sort().join(','));
        expect(rows.length).toBe(groups.length);

        // --- attività di oggi
        const activityRows = screen.queryAllByTestId('omega-activity-row');
        const todayActivity = st.activity.filter((a) => {
            if (!a.ts) return true;
            const d = new Date(a.ts);
            return new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Rome' }).format(d) === romeDay();
        });
        rep.check('Attività di oggi — righe', String(todayActivity.length), String(activityRows.length));

        // --- italiano: nessuno stato inglese nudo nella pagina
        const body = text(document.body);
        const naked = ['PENDING', 'HEDGED', ' OPEN ', 'SETTLED', 'CANCELLED'].filter((w) => body.includes(w));
        rep.mark('testi in italiano (nessun stato inglese nudo)', 'nessuno', naked.join(',') || 'nessuno', naked.length === 0);
        if (naked.length) rep.finding('LOW', 'pages/Omega.tsx (testi visibili)', `stati inglesi nudi a schermo: ${naked.join(', ')}`);
        rep.mark('formato denaro italiano (virgola + €)', 'sì', /\d,\d{2}\s€/.test(body) ? 'sì' : 'NO', /\d,\d{2}\s€/.test(body));
        expect(consoleCapture.errors).toEqual([]);
    });

    it('Storico (calendario): get_omega_daily risponde e goal_snapshot è rispettato', async () => {
        const to = romeDay();
        const from = `${to.slice(0, 8)}01`;
        const rows = await fetchOmegaDaily(from, to);
        rep.mark('get_omega_daily — giorni restituiti', '>=0', String(rows.length), true);
        const snap = rows.filter((r) => r.goal_snapshot === true).length;
        rep.mark('get_omega_daily — giorni con goal_snapshot=true', 'informativo', `${snap}/${rows.length}`, true);
        if (rows.length && snap === 0) {
            rep.finding('MEDIUM', 'migrations/omega_daily_v2.sql (storicizzazione obiettivo)',
                `nessuno dei ${rows.length} giorni ha goal_snapshot=true: lo Storico giudica «centrato» sull'obiettivo CORRENTE, non su quello di quel giorno.`);
        }

        renderPage();
        await waitFor(() => expect(screen.queryByTestId('loading-state')).toBeNull(), { timeout: 60_000 });
        const user = userEvent.setup();
        await user.click(screen.getByLabelText('Storico'));
        await waitFor(() => expect(screen.getByTestId('trading-history')).toBeInTheDocument(), { timeout: 30_000 });
        // il fetch dello storico è già partito: si attende che compaia il calendario
        await new Promise((r) => setTimeout(r, 4_000));
        const err = screen.queryByTestId('history-error');
        rep.mark('Storico — nessun errore di caricamento', 'nessuno', err ? text(err).slice(0, 140) : 'nessuno', !err);
        if (err) rep.finding('CRITICAL', 'pages/Omega.tsx → TradingHistory(variant=omega)', text(err));
        expect(consoleCapture.errors).toEqual([]);
    });
});
