// ============================================================================
// safe.cert.test.tsx — CERTIFICAZIONE della pagina /safe-strategy sui DATI REALI.
//
// UNICO mock oltre al client: `@/hooks/useAuth`. Il SafeStrategyProvider carica
// il feed dello scanner solo se `user` esiste (SafeStrategyProvider.tsx:236-238):
// con il service role non c'è sessione, quindi senza questo stub il radar
// resterebbe vuoto e non si certificherebbe nulla. I DATI restano quelli veri.
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
vi.mock('@/hooks/useAuth', () => ({
    useAuth: () => ({
        user: { id: 'cert-owner', email: 'cert@local' },
        session: { access_token: 'cert' },
        loading: false,
    }),
}));
const toasts = vi.hoisted(() => ({ errors: [] as string[] }));
vi.mock('sonner', () => ({
    toast: Object.assign((m: string) => { void m; }, {
        success: () => {},
        warning: () => {},
        error: (m: string, o?: { description?: string }) => {
            toasts.errors.push(`${m}${o?.description ? ` — ${o.description}` : ''}`);
        },
    }),
}));

import SafeStrategy from '@/pages/SafeStrategy';
import { SafeStrategyProvider } from '@/components/safestrategy/SafeStrategyProvider';
import {
    fetchSafeState, fetchSafeTrades, fetchSafeActivity, fetchOpportunities,
    groupClosingLegs, isLivePosition, safeTradeBook, type SafeTrade,
} from '@/lib/safeBot';
import { fetchScanRows, fetchScanStatus } from '@/lib/safeStrategyScan';
import { fetchSafeDaily, romeDay, dayLabel } from '@/lib/dailyHistory';
import { groupTradesByMatch, filterMatchesForDay, summarizeMatches } from '@/lib/omegaMatches';
import { fmtMoney, fmtOdds } from '@/lib/format';
import { writeAttempts, CERT_RUN } from './realClient';
import { consoleCapture } from './setup.cert';
import { Report, text } from './report';

/** fuori da vitest.cert.config.ts i test si SALTANO (mai il DB reale in `npm test`) */
const d = CERT_RUN ? describe : describe.skip;
const rep = new Report('/safe-strategy — SAFE STRATEGY (radar + bot)');
afterAll(() => rep.print());

function renderPage() {
    return render(
        <HelmetProvider>
            <MemoryRouter initialEntries={['/safe-strategy']}>
                <SafeStrategyProvider>
                    <SafeStrategy />
                </SafeStrategyProvider>
            </MemoryRouter>
        </HelmetProvider>,
    );
}

async function loaded() {
    await waitFor(() => expect(screen.getAllByTestId('kpi-row')[0].getAttribute('data-loading')).toBeNull(), { timeout: 60_000 });
}

/** KPI per ETICHETTA (l'ordine dei tile cambia con i campi condizionali) */
function kpi(label: string): { value: string; sub: string } {
    const all = [...document.querySelectorAll('[data-testid="stat-tile"],[data-testid^="safe-kpi-"]')];
    const found = all.find((el) => text(el.children[0]).startsWith(label));
    if (!found) throw new Error(`KPI non trovato: ${label}`);
    return { value: text(found.children[1]), sub: text(found.children[2]) };
}

/** il radar carica 90 righe di scanner: si attende che i monitor arrivino */
async function waitRadar() {
    await waitFor(() => {
        expect(kpi('Partite monitorate').value).not.toBe('0');
    }, { timeout: 60_000 });
}

d('/safe-strategy sui dati reali', () => {
    it('forma della RPC + fallback della UI', async () => {
        const st = await fetchSafeState();
        const agg = (st.aggregates ?? {}) as Record<string, unknown>;
        rep.note(`get_safe_state: aggregates=[${Object.keys(agg).sort().join(', ')}] · trades=${st.trades.length} · activity=${(st.activity ?? []).length}`);
        for (const [k, v, mig] of [
            ['activity', (st.activity ?? []).length ? 'popolata' : 'VUOTA', 'safe_strategy_bot_v2.sql'],
            ['params_effective', st.params_effective ? 'presente' : 'ASSENTE', 'safe_strategy_bot_v2.sql'],
            ['operating_day', st.operating_day ?? 'ASSENTE', 'safe_strategy_bot_v2.sql'],
        ] as [string, string, string][]) {
            const ok = v !== 'ASSENTE' && v !== 'VUOTA';
            rep.mark(`get_safe_state.${k}`, `presente (${mig})`, String(v), ok);
        }
        if (!st.params_effective) {
            rep.finding('MEDIUM', 'pages/SafeStrategy.tsx:352 / 646 / 705',
                'params_effective assente → min_stake ripiega su 2, opps_stake/commission_pct sui parametri LOCALI della UI, non su quelli realmente in uso dal servizio. FALLBACK PRESENTE ma il numero mostrato può non essere quello del servizio.');
        }
        if (!st.operating_day) {
            rep.finding('MEDIUM', 'pages/SafeStrategy.tsx:113',
                'operating_day assente → giornata calcolata dal client con romeDay(). FALLBACK PRESENTE (stessa TZ), ma è il client a decidere il giorno, non il DB.');
        }
        for (const k of ['won_today', 'lost_today', 'legs_today', 'events_today', 'reconciling_liability', 'day_liability']) {
            const has = k in agg;
            rep.mark(`aggregates.${k}`, 'presente (v2)', has ? 'presente' : 'ASSENTE', has);
        }
        rep.finding('HIGH', 'pages/SafeStrategy.tsx:338-345 (V/P, operazioni, partite di giornata)',
            'get_safe_state.aggregates NON ha won_today/lost_today/legs_today/events_today: barra e KPI usano il conteggio LOCALE dai trade caricati (summarizeMatches/groupClosingLegs). Fallback presente, ma i numeri non vengono più dal DB come dichiara la nota della barra.');

        // attività: la RPC dedicata non esiste → fallback in SELECT sulla tabella
        const activity = await fetchSafeActivity(100).catch((e: Error) => e);
        if (activity instanceof Error) {
            rep.mark('fetchSafeActivity (fallback SELECT)', 'righe', `ERRORE: ${activity.message}`, false);
            rep.finding('HIGH', 'lib/safeBot.ts:911-924', `né get_safe_activity né la SELECT su safe_strategy_activity funzionano: ${activity.message}`);
        } else {
            rep.mark('fetchSafeActivity (fallback SELECT su safe_strategy_activity)', 'righe', String(activity.length), true);
        }
        expect(st.control).toBeTruthy();
    });

    it('render completo: nessun crash, nessun console.error, guscio presente', async () => {
        renderPage();
        await loaded();
        expect(screen.getByTestId('page-shell')).toBeInTheDocument();
        expect(screen.getByTestId('bot-header')).toBeInTheDocument();
        rep.mark('header stato bot (chip)', 'IN CORSA/FERMO/…', text(screen.getByTestId('bot-status')), true);
        rep.mark('chip salute servizio', 'presente', text(screen.getByTestId('service-health')).slice(0, 70), true);
        const banner = document.querySelector('[data-mode]');
        rep.mark('banner di modalità', 'presente', banner?.getAttribute('data-mode') ?? 'ASSENTE', Boolean(banner));
        expect(screen.getByTestId('day-bar')).toBeInTheDocument();
        for (const t of ['Calcio', 'Tennis', 'Storico']) {
            expect(screen.getByLabelText(new RegExp(`^${t}`))).toBeInTheDocument();
        }
        rep.mark('tab principali', 'Calcio/Tennis/Storico', 'tutti', true);
        rep.mark('console.error durante il render', '0', String(consoleCapture.errors.length), consoleCapture.errors.length === 0);
        if (consoleCapture.errors.length) {
            rep.finding('CRITICAL', 'pages/SafeStrategy.tsx (render)', `console.error: ${consoleCapture.errors.slice(0, 4).join(' | ')}`);
        }
        rep.mark('toast.error durante il caricamento', '0', String(toasts.errors.length), toasts.errors.length === 0);
        rep.mark('tentativi di SCRITTURA sul DB', '0', String(writeAttempts.length), writeAttempts.length === 0);
        expect(writeAttempts).toEqual([]);
        expect(consoleCapture.errors).toEqual([]);
    });

    it('KPI e barra giornata = valori della RPC', async () => {
        const [st, scanRows, scanStatus] = await Promise.all([fetchSafeState(), fetchScanRows(), fetchScanStatus()]);
        let trades = st.trades;
        if (!trades.length) trades = await fetchSafeTrades(300);
        const agg = (st.aggregates ?? {}) as Record<string, number | null>;
        const stats = (st.control?.stats ?? {}) as Record<string, number | null | Record<string, number>>;
        const realizedToday = Number(agg.realized_today ?? stats.realized_today ?? 0);
        const realizedTotal = Number(agg.realized_total ?? stats.realized_total ?? 0);
        const openLiability = Number(agg.open_liability ?? stats.open_liability ?? 0);
        const openCount = agg.open_count ?? trades.filter(isLivePosition).length;
        const operatingDay = st.operating_day ?? romeDay();

        // contatori di giornata come li calcola la pagina (fallback locale)
        const groups = filterMatchesForDay(groupTradesByMatch(trades), operatingDay);
        const dayEventIds = new Set(groups.map((g) => g.event_id));
        const dayTrades = trades.filter((t) => dayEventIds.has(t.event_id));
        const sumCalcio = summarizeMatches(groups.filter((g) => g.legs[0]?.trade.sport === 'calcio'));
        const sumTennis = summarizeMatches(groups.filter((g) => g.legs[0]?.trade.sport === 'tennis'));
        const wonToday = agg.won_today ?? (sumCalcio.won + sumTennis.won);
        const lostToday = agg.lost_today ?? (sumCalcio.lost + sumTennis.lost);
        const legsToday = agg.legs_today ?? groupClosingLegs(dayTrades).length;
        const eventsToday = agg.events_today ?? dayEventIds.size;

        renderPage();
        await loaded();

        await waitRadar();
        rep.check('KPI «P&L oggi»', fmtMoney(realizedToday, { signed: true }), kpi('P&L oggi').value);
        rep.check('KPI «P&L oggi» — sottotitolo giornata/V-P',
            `giornata operativa ${dayLabel(operatingDay, { year: false })} · Europe/Rome · ${wonToday}V ${lostToday}P`,
            text(screen.getByTestId('safe-operating-day')));
        rep.check('KPI «Trade aperti»', String(openCount), kpi('Trade aperti').value);
        rep.check('KPI «Liability aperta»', fmtMoney(openLiability), kpi('Liability aperta').value);
        rep.check('KPI «P&L totale»', fmtMoney(realizedTotal, { signed: true }), kpi('P&L totale').value);
        expect(text(screen.getByTestId('safe-kpi-liability').children[1])).toBe(fmtMoney(openLiability));

        const bar = screen.getByTestId('day-bar');
        rep.check('Barra giornata — giorno operativo', dayLabel(operatingDay, { weekday: true }), text(screen.getByTestId('day-bar-day')));
        rep.check('Barra giornata — contatori',
            `partite ${eventsToday} · operazioni ${legsToday} · ${wonToday}V ${lostToday}P`
            + (Number(openCount) > 0 ? ` · ${openCount} vive` : ''),
            text(screen.getByTestId('day-bar-counts')));
        const barText = text(bar);
        rep.mark('Barra giornata — realizzato oggi', fmtMoney(realizedToday, { signed: true }),
            barText.includes(`realizzato oggi ${fmtMoney(realizedToday, { signed: true })}`) ? fmtMoney(realizedToday, { signed: true }) : '(non trovato)',
            barText.includes(`realizzato oggi ${fmtMoney(realizedToday, { signed: true })}`));
        if (openLiability > 0) {
            rep.check('Barra giornata — liability aperta', fmtMoney(openLiability), text(screen.getByTestId('day-bar-liability')));
        }
        rep.mark('Barra giornata — nessun obiettivo (Safe non ne ha)', 'assente',
            barText.includes('Obiettivo di oggi') ? 'PRESENTE' : 'assente', !barText.includes('Obiettivo di oggi'));
        rep.note(`barra: ${barText.slice(0, 260)}`);

        // partite monitorate = righe dello scanner (calcio + tennis)
        const calcio = scanRows.filter((r) => r.sport === 'calcio').length;
        const tennis = scanRows.filter((r) => r.sport === 'tennis').length;
        rep.check('KPI «Partite monitorate»', String(calcio + tennis), kpi('Partite monitorate').value);
        rep.check('KPI «Partite monitorate» — sottotitolo', `⚽ ${calcio} · 🎾 ${tennis}`, kpi('Partite monitorate').sub);
        rep.note(`safe_strategy_status.payload: monitored=${scanStatus?.payload?.monitored} calcio_inplay=${scanStatus?.payload?.calcio_inplay} tennis_inplay=${scanStatus?.payload?.tennis_inplay} updated_at=${scanStatus?.updated_at}`);
        expect(consoleCapture.errors).toEqual([]);
    });

    it('tab Trade = posizioni della giornata; cash out prezzato sui trade O/U aperti', async () => {
        const st = await fetchSafeState();
        let trades = st.trades;
        if (!trades.length) trades = await fetchSafeTrades(300);
        const scanRows = await fetchScanRows();
        const payloadByEvent: Record<string, unknown> = {};
        for (const r of scanRows) payloadByEvent[r.event_id] = r.payload;
        const operatingDay = st.operating_day ?? romeDay();
        const groups = filterMatchesForDay(groupTradesByMatch(trades), operatingDay);
        const dayEventIds = new Set(groups.map((g) => g.event_id));
        const dayCalcio = trades.filter((t) => t.sport !== 'tennis' && dayEventIds.has(t.event_id));
        const expectedRows = groupClosingLegs(dayCalcio).length;

        renderPage();
        await loaded();
        await waitRadar();
        const user = userEvent.setup();
        await user.click(screen.getByText(/^Trade \(/));
        await waitFor(() => expect(screen.getByTestId('safe-trades-card')).toBeInTheDocument(), { timeout: 20_000 });

        const rows = screen.queryAllByTestId('safe-trade-row');
        rep.check('Tab Trade (calcio) — posizioni della giornata', String(expectedRows), String(rows.length));
        rep.note(`trade totali dalla RPC: ${trades.length} · giornata ${operatingDay}: calcio ${dayCalcio.length} righe → ${expectedRows} posizioni`);

        // --- R1: cash out prezzato sui trade O/U ancora aperti (es. #39/#40)
        const ouOpen = trades.filter(
            (t) => t.status === 'open' && String(t.market_type ?? '').toUpperCase().includes('OVER_UNDER'),
        );
        rep.note(`trade O/U aperti sul DB: ${ouOpen.map((t) => `#${t.id} ${t.selection_name} @${t.price}`).join(' · ') || 'nessuno'}`);
        if (!ouOpen.length) {
            rep.mark('R1 cash out O/U', 'almeno un trade O/U aperto', 'nessuno sul DB ora', false);
            rep.finding('INFO', 'R1', 'nessun trade O/U aperto al momento della certificazione: verifica non eseguibile.');
        }
        for (const t of ouOpen) {
            const payload = payloadByEvent[t.event_id] as never;
            const book = safeTradeBook(t as SafeTrade, payload);
            const feedRow = scanRows.find((r) => r.event_id === t.event_id);
            rep.mark(`R1 #${t.id} — feed dell'evento presente`, 'presente', feedRow ? `sì (${feedRow.updated_at})` : 'ASSENTE', Boolean(feedRow));
            rep.mark(`R1 #${t.id} — book della selezione (${t.selection_name})`,
                'back/lay dal feed',
                book ? `back ${fmtOdds(book.back ?? null)} / lay ${fmtOdds(book.lay ?? null)}` : 'NON RISOLTO',
                Boolean(book));
            if (!book) {
                rep.finding('HIGH', `lib/safeBot.ts:1408 safeTradeBook — trade #${t.id}`,
                    `nessun book per ${t.market_type} sel=${t.selection_id} (${t.selection_name}) sull'evento ${t.event_id}: la colonna «chiudendo ora» e il bottone Cash out restano senza prezzo.`);
            }
            // il prezzo mostrato in tabella deve essere quello del feed
            const row = rows.find((r) => text(r).includes(String(t.selection_name ?? '')));
            if (row && book) {
                const shownNow = text(within(row).queryByTestId('safe-price-now'));
                const expectNow = t.side === 'back' ? fmtOdds(book.lay ?? null) : fmtOdds(book.back ?? null);
                rep.mark(`R1 #${t.id} — «prezzo ora» in tabella`, expectNow, shownNow || '(vuoto)', shownNow.includes(expectNow));
            }
        }

        // --- attività (fetch in background: si attende che arrivi)
        await waitFor(() => expect(screen.getByTestId('safe-activity-card')).toBeInTheDocument());
        await waitFor(
            () => expect(screen.getByTestId('safe-activity').getAttribute('data-empty')).toBeNull(),
            { timeout: 30_000 },
        ).catch(() => {});
        const activityCard = screen.getByTestId('safe-activity-card');
        const actRows = within(activityCard).queryAllByTestId('activity-row');
        const empty = within(activityCard).queryByTestId('safe-activity')?.getAttribute('data-empty') === '1';
        rep.mark('Attività del servizio', 'righe presenti', empty ? 'VUOTA' : `${actRows.length} righe`, !empty);
        if (empty) {
            rep.finding('HIGH', 'pages/SafeStrategy.tsx:989-1000 + lib/safeBot.ts:911',
                'sezione «Attività» vuota: get_safe_activity non esiste e la SELECT su safe_strategy_activity non restituisce righe (tabella assente o vuota). Il trader non vede perché il bot è entrato o no.');
        }

        // --- italiano + formati
        const body = text(document.body);
        const naked = ['PENDING', 'HEDGED', 'SETTLED', 'CANCELLED'].filter((w) => body.includes(w));
        rep.mark('testi in italiano (nessuno stato inglese nudo)', 'nessuno', naked.join(',') || 'nessuno', naked.length === 0);
        if (naked.length) rep.finding('LOW', 'pages/SafeStrategy.tsx (testi visibili)', `stati inglesi nudi: ${naked.join(', ')}`);
        rep.mark('formato denaro italiano', 'sì', /\d,\d{2}\s€/.test(body) ? 'sì' : 'NO', /\d,\d{2}\s€/.test(body));
        expect(consoleCapture.errors).toEqual([]);
    });

    it('Storico: get_safe_daily risponde e il calendario non va in errore', async () => {
        const to = romeDay();
        const from = `${to.slice(0, 8)}01`;
        const rows = await fetchSafeDaily(from, to, null);
        rep.mark('get_safe_daily — giorni restituiti', '>=0', String(rows.length), true);
        renderPage();
        await loaded();
        const user = userEvent.setup();
        await user.click(screen.getByLabelText('Storico'));
        await waitFor(() => expect(screen.getByTestId('trading-history')).toBeInTheDocument(), { timeout: 30_000 });
        await new Promise((r) => setTimeout(r, 4_000));
        const err = screen.queryByTestId('history-error');
        rep.mark('Storico — nessun errore di caricamento', 'nessuno', err ? text(err).slice(0, 140) : 'nessuno', !err);
        if (err) rep.finding('CRITICAL', 'pages/SafeStrategy.tsx → TradingHistory(variant=safe)', text(err));
        expect(consoleCapture.errors).toEqual([]);
    });

    it('opportunità del modello: righe reali normalizzate e visibili', async () => {
        const opps = await fetchOpportunities();
        const totals = opps.reduce((n, r) => n + (Array.isArray(r.payload?.opps) ? r.payload.opps.length : 0), 0);
        rep.mark('safe_strategy_opportunities — righe / opportunità', 'informativo', `${opps.length} righe · ${totals} opportunità`, true);
        rep.note(`opps per sport: calcio ${opps.filter((r) => r.sport !== 'tennis').length} · tennis ${opps.filter((r) => r.sport === 'tennis').length}`);
        if (opps.length && totals === 0) {
            rep.finding('HIGH', 'lib/safeBot.ts:973 normalizeOppRow',
                `${opps.length} righe di opportunità sul DB ma nessuna opportunità dentro payload.opps: la normalizzazione non sta trovando la chiave.`);
        }
        expect(Array.isArray(opps)).toBe(true);
    });
});
