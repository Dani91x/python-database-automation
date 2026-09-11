// ============================================================================
// mike.cert.test.tsx — CERTIFICAZIONE della pagina /mike sui DATI REALI.
// Client Supabase vero (service role, sole letture, realtime stubbato).
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
    toast: Object.assign((m: string) => { void m; }, {
        success: () => {},
        warning: () => {},
        error: (m: string, o?: { description?: string }) => {
            toasts.errors.push(`${m}${o?.description ? ` — ${o.description}` : ''}`);
        },
    }),
}));

import Mike from '@/pages/Mike';
import {
    fetchMikeState, fetchMikeRequests, splitMikeEvents, rememberLive, activeLegs,
    positionRows, type MikeEvent,
} from '@/lib/mike';
import { fetchScanStatus } from '@/lib/safeStrategyScan';
import { fetchMikeDaily, romeDay, dayLabel } from '@/lib/dailyHistory';
import { fmtMoney, fmtOdds, fmtNum } from '@/lib/format';
import { writeAttempts, CERT_RUN } from './realClient';
import { consoleCapture } from './setup.cert';
import { Report, text } from './report';

/** fuori da vitest.cert.config.ts i test si SALTANO (mai il DB reale in `npm test`) */
const d = CERT_RUN ? describe : describe.skip;
const rep = new Report('/mike — MIKE (Under 3.5 / Over 4.5)');
afterAll(() => rep.print());

function renderPage() {
    return render(
        <HelmetProvider>
            <MemoryRouter initialEntries={['/mike']}>
                <Mike />
            </MemoryRouter>
        </HelmetProvider>,
    );
}

/** KPI per ETICHETTA (l'ordine dei tile non è garantito) */
function kpi(label: string): { value: string; sub: string } {
    const all = [...document.querySelectorAll('[data-testid="stat-tile"],[data-testid^="mike-kpi-"]')];
    const found = all.find((el) => text(el.children[0]).startsWith(label));
    if (!found) throw new Error(`KPI non trovato: ${label}`);
    return { value: text(found.children[1]), sub: text(found.children[2]) };
}

async function loaded() {
    await waitFor(() => expect(screen.getAllByTestId('kpi-row')[0].getAttribute('data-loading')).toBeNull(), { timeout: 60_000 });
    await waitFor(() => expect(document.querySelector('[data-testid="mike-cards"], [data-testid="empty-state"]')).toBeTruthy(), { timeout: 60_000 });
}

d('/mike sui dati reali', () => {
    it('forma della RPC + fallback della UI', async () => {
        const st = await fetchMikeState();
        const agg = (st.aggregates ?? {}) as Record<string, unknown>;
        rep.note(`get_mike_state: eventi=${st.events.length} · trades=${st.trades.length} · activity=${st.activity.length} · aggregates=[${Object.keys(agg).sort().join(', ')}]`);
        for (const k of ['requests', 'day_start', 'day_by'] as const) {
            const v = k === 'requests' ? (st.requests.length ? 'presente' : 'VUOTA/ASSENTE') : (st[k] ?? 'ASSENTE');
            const ok = String(v) !== 'ASSENTE' && String(v) !== 'VUOTA/ASSENTE';
            rep.mark(`get_mike_state.${k}`, 'presente (mike_bot_v2)', String(v), ok);
        }
        if (!st.day_start) {
            rep.finding('HIGH', 'components/mike/useMike.ts:108 + pages/Mike.tsx (dayStartMs)',
                'day_start assente → dayStartMs = null: il tab Trade e la equity curve NON filtrano per giornata operativa (groupsOfDay con null) e la curva "di oggi" è in realtà tutto il caricato. Serve mike_bot_v2.sql.');
        }
        if (!st.requests.length) {
            rep.mark('fallback richieste (SELECT su mike_requests)', 'righe', 'verifico', true);
            const reqs = await fetchMikeRequests(50).catch((e: Error) => e);
            if (reqs instanceof Error) {
                rep.mark('fetchMikeRequests (fallback)', 'righe', `ERRORE ${reqs.message}`, false);
                rep.finding('HIGH', 'lib/mike.ts:1162', `SELECT su mike_requests fallita: ${reqs.message}`);
            } else {
                rep.mark('fetchMikeRequests (fallback SELECT su mike_requests)', 'righe', String(reqs.length), true);
            }
        }
        for (const k of ['won_today', 'lost_today', 'cycles_today', 'events_today', 'live_now', 'reconciling', 'liability_source']) {
            const has = k in agg;
            rep.mark(`aggregates.${k}`, 'presente (mike_bot_v2)', has ? 'presente' : 'ASSENTE', has);
        }
        expect(st.control).toBeTruthy();
    });

    it('render completo: nessun crash, nessun console.error, guscio presente', async () => {
        renderPage();
        await loaded();
        expect(screen.getByTestId('page-shell')).toBeInTheDocument();
        rep.mark('header stato bot (chip)', 'BOT IN CORSA/FERMO/…', text(screen.getByTestId('mike-status')), true);
        rep.mark('chip salute servizio', 'presente', text(screen.getByTestId('service-health')).slice(0, 70), true);
        rep.mark('banner di modalità', 'presente', screen.getByTestId('mike-mode-banner').getAttribute('data-mode') ?? 'ASSENTE', true);
        expect(screen.getByTestId('day-bar')).toBeInTheDocument();
        const migr = screen.queryByTestId('mode-banner-migration');
        rep.mark('avviso migrazione nel banner', 'assente (tabelle Mike presenti)', migr ? text(migr) : 'assente', !migr);
        for (const t of [/^Partite/, /^Trade/, /^Attività/, /^Regolate/, /^Storico/]) {
            expect(screen.getByLabelText(t)).toBeInTheDocument();
        }
        rep.mark('tab presenti', 'Partite/Trade/Attività/Regolate/Storico', 'tutti', true);
        rep.mark('console.error durante il render', '0', String(consoleCapture.errors.length), consoleCapture.errors.length === 0);
        if (consoleCapture.errors.length) {
            rep.finding('CRITICAL', 'pages/Mike.tsx (render)', `console.error: ${consoleCapture.errors.slice(0, 4).join(' | ')}`);
        }
        rep.mark('toast.error durante il caricamento', '0', String(toasts.errors.length), toasts.errors.length === 0);
        rep.mark('tentativi di SCRITTURA sul DB', '0', String(writeAttempts.length), writeAttempts.length === 0);
        expect(writeAttempts).toEqual([]);
        expect(consoleCapture.errors).toEqual([]);
    });

    it('KPI e barra giornata = valori della RPC', async () => {
        const [st, scanStatus] = await Promise.all([fetchMikeState(), fetchScanStatus()]);
        const agg = (st.aggregates ?? {}) as Record<string, number | string | boolean | null>;
        const stats = (st.control?.stats ?? {}) as Record<string, number | string | boolean | null>;
        const sticky = rememberLive(st.events, new Set<string>());
        const sections = splitMikeEvents(st.events, sticky);
        const active = [...sections.pre, ...sections.live, ...sections.fix];
        const withPosition = active.filter((e) => activeLegs(e).some((l) => l.matched > 0)).length;
        const realizedToday = Number(agg.realized_today ?? stats.realized_today ?? 0);
        const realizedTotal = Number(agg.realized_total ?? stats.realized_total ?? 0);
        const openLiability = Number(agg.open_liability ?? stats.open_liability ?? 0);
        const lockedPnl = Math.round(active.reduce((s, e) => s + Number(e.live?.locked ?? 0), 0) * 100) / 100;

        renderPage();
        await loaded();

        rep.check('KPI «Partite seguite»', String(active.length), kpi('Partite seguite').value);
        rep.check('KPI «Partite seguite» — sottotitolo',
            `${sections.pre.length} pre-match · ${sections.live.length} live · ${withPosition} con posizione`,
            kpi('Partite seguite').sub);
        rep.check('KPI «Posizioni aperte»', String(agg.open_count ?? stats.trades_open ?? 0), kpi('Posizioni aperte').value);
        rep.check('KPI «P&L oggi»', fmtMoney(realizedToday, { signed: true }), kpi('P&L oggi').value);
        rep.check('KPI «P&L totale»', fmtMoney(realizedTotal, { signed: true }), kpi('P&L totale').value);
        rep.check('KPI «Liability aperta»', fmtMoney(openLiability), kpi('Liability aperta').value);
        rep.check('KPI «P&L bloccato» (somma live.locked delle partite vive)', fmtMoney(lockedPnl, { signed: true }), kpi('P&L bloccato').value);
        rep.check('KPI «Ultimo ciclo» — età feed',
            stats.scanner_age_s != null ? `feed ${fmtNum(stats.scanner_age_s as number, 0)} s` : 'feed: nessun dato',
            kpi('Ultimo ciclo').sub);
        // coerenza fra il KPI (fotografia congelata di control.stats) e il chip
        // di salute (updated_at del feed vs Date.now())
        const scanAgeS = scanStatus?.updated_at ? (Date.now() - Date.parse(scanStatus.updated_at)) / 1000 : null;
        const healthText = text(screen.getByTestId('service-health'));
        rep.mark('coerenza «feed» KPI vs chip di salute',
            `chip: età reale ${scanAgeS != null ? Math.round(scanAgeS) : '—'} s`,
            `KPI: ${kpi('Ultimo ciclo').sub} · chip: ${healthText.slice(0, 40)}`,
            !(scanAgeS != null && scanAgeS > 60 && String(stats.scanner_age_s ?? '') !== '' && Number(stats.scanner_age_s) < 60));
        if (scanAgeS != null && scanAgeS > 60 && stats.scanner_age_s != null && Number(stats.scanner_age_s) < 60) {
            rep.finding('MEDIUM', 'pages/Mike.tsx:311-315 (StatTile «Ultimo ciclo»)',
                `il sottotitolo dice «feed ${fmtNum(stats.scanner_age_s as number, 0)} s» perché legge control.stats.scanner_age_s, che è la fotografia CONGELATA dell'ultimo ciclo del servizio; il feed reale ha ${Math.round(scanAgeS)} s (il chip di salute lo dice giustamente). Due numeri opposti sulla stessa schermata: a servizio fermo il KPI va dichiarato stantio come fa Omega con statsFresh (Omega.tsx:377).`);
        }
        expect(kpi('Liability aperta').value).toBe(fmtMoney(openLiability));

        // barra della giornata
        rep.check('Barra giornata — giorno operativo', dayLabel(romeDay(), { weekday: true }), text(screen.getByTestId('day-bar-day')));
        const matches = agg.events_today ?? active.length;
        const operations = agg.cycles_today ?? st.trades.length;
        const won = agg.won_today ?? null;
        const lost = agg.lost_today ?? null;
        const live = agg.live_now ?? sections.live.length;
        // DayBar mostra il blocco V/P solo se won o lost non sono null
        // (DayBar.tsx:95): senza mike_bot_v2 sono ENTRAMBI null → non compare
        rep.check('Barra giornata — contatori',
            `partite ${matches} · operazioni ${operations}`
            + (won != null || lost != null ? ` · ${won ?? 0}V ${lost ?? 0}P` : '')
            + (Number(live) > 0 ? ` · ${live} vive` : ''),
            text(screen.getByTestId('day-bar-counts')));
        rep.mark('Barra giornata — blocco V/P presente',
            'V/P della giornata', won == null && lost == null ? 'ASSENTE (won_today/lost_today null)' : `${won ?? 0}V ${lost ?? 0}P`,
            won != null || lost != null);
        if (won == null && lost == null) {
            rep.finding('HIGH', 'pages/Mike.tsx:131-132 → DayBar (components/trading/DayBar.tsx:95)',
                `aggregates.won_today/lost_today assenti → wonToday=lostToday=null e il blocco «V/P» SPARISCE dalla barra della giornata, anche se aggregates.won=${agg.won} / aggregates.lost=${agg.lost} sono disponibili. Il ripiego su agg.won/agg.lost esiste solo nel riepilogo del tab Trade (Mike.tsx:395-396), non sulla barra: manca il fallback.`);
        }
        rep.check('Barra giornata — P&L bloccato', fmtMoney(lockedPnl, { signed: true }), text(screen.getByTestId('day-bar-locked')));
        if (openLiability > 0) {
            rep.check('Barra giornata — liability aperta', fmtMoney(openLiability), text(screen.getByTestId('day-bar-liability')));
        }
        rep.note(`scanner: updated_at=${scanStatus?.updated_at} · calcio_inplay=${scanStatus?.payload?.calcio_inplay} · source=${scanStatus?.payload?.source}`);
        expect(consoleCapture.errors).toEqual([]);
    });

    it('sezioni PRE-MATCH / LIVE / DA SISTEMARE: conteggi e ordine dai dati reali', async () => {
        const st = await fetchMikeState();
        const sticky = rememberLive(st.events, new Set<string>());
        const sections = splitMikeEvents(st.events, sticky);

        renderPage();
        await loaded();
        expect(screen.getByTestId('mike-cards')).toBeInTheDocument();

        // intestazioni con i conteggi
        rep.check('Sezione PRE-MATCH — intestazione',
            `⏱ PRE-MATCH (${sections.pre.length}) · per calcio d’inizio`,
            text(within(screen.getByTestId('mike-section-pre')).getAllByRole('heading')[0]));
        rep.check('Sezione LIVE — intestazione',
            `🔴 LIVE (${sections.live.length}) · in gioco`,
            text(within(screen.getByTestId('mike-section-live')).getAllByRole('heading')[0]));
        const fix = screen.queryByTestId('mike-section-fix');
        rep.mark('Sezione DA SISTEMARE',
            sections.fix.length ? `presente (${sections.fix.length})` : 'assente (nessun ERROR/SKIPPED)',
            fix ? text(within(fix).getAllByRole('heading')[0]) : 'assente',
            Boolean(fix) === sections.fix.length > 0);

        // conteggio card per sezione
        const preCards = screen.queryByTestId('mike-cards-pre');
        const liveCards = screen.queryByTestId('mike-cards-live');
        rep.check('Card PRE-MATCH', String(sections.pre.length), String(preCards ? within(preCards).queryAllByTestId('mike-match-card').length : 0));
        rep.check('Card LIVE', String(sections.live.length), String(liveCards ? within(liveCards).queryAllByTestId('mike-match-card').length : 0));
        rep.check('Tab «Partite» — contatore',
            `⚽ Partite (${sections.pre.length + sections.live.length + sections.fix.length})`,
            text(screen.getByLabelText(/^Partite/)));
        rep.check('Tab «Regolate» — contatore', `✅ Regolate (${sections.settled.length})`, text(screen.getByLabelText(/^Regolate/)));

        // ORDINE stabile: pre e live sono ordinate per calcio d'inizio crescente
        const shownPre = preCards ? within(preCards).queryAllByTestId('mike-match-card').map((c) => text(c).slice(0, 0)) : [];
        void shownPre;
        const koOf = (e: MikeEvent) => (e.ko_at ? Date.parse(e.ko_at) : Number.POSITIVE_INFINITY);
        const preSorted = sections.pre.every((e, i, a) => i === 0 || koOf(a[i - 1]) <= koOf(e));
        const liveSorted = sections.live.every((e, i, a) => i === 0 || koOf(a[i - 1]) <= koOf(e));
        rep.mark('Ordine PRE-MATCH per calcio d’inizio', 'crescente', preSorted ? 'crescente' : 'NON ordinato', preSorted);
        rep.mark('Ordine LIVE per calcio d’inizio', 'crescente', liveSorted ? 'crescente' : 'NON ordinato', liveSorted);

        // ORDINE STABILE a stati cambiati: una partita già vista in gioco non
        // torna in PRE-MATCH nemmeno se il feed perde `inplay` (memoria sticky)
        const mutated: MikeEvent[] = st.events.map((e) => (
            e.live?.inplay ? { ...e, live: { ...e.live, inplay: false } } : e
        ));
        const after = splitMikeEvents(mutated, sticky);
        const sameLive = after.live.map((e) => e.event_id).join(',') === sections.live.map((e) => e.event_id).join(',');
        rep.mark('Ordine stabile al 2º giro (inplay perso dal feed)',
            sections.live.map((e) => e.event_id).join(',') || '(nessuna live)',
            after.live.map((e) => e.event_id).join(',') || '(nessuna live)', sameLive);
        expect(sameLive).toBe(true);
        // una PRE che va in gioco entra in LIVE e le altre non si mescolano
        const firstPre = sections.pre[0];
        if (firstPre) {
            const promoted = splitMikeEvents(
                st.events.map((e) => (e.event_id === firstPre.event_id
                    ? { ...e, live: { ...(e.live ?? {}), inplay: true } } as MikeEvent : e)),
                new Set(sticky),
            );
            const preTailStable = promoted.pre.map((e) => e.event_id).join(',')
                === sections.pre.filter((e) => e.event_id !== firstPre.event_id).map((e) => e.event_id).join(',');
            rep.mark('Promozione PRE→LIVE senza rimescolare le altre', 'resto invariato',
                preTailStable ? 'resto invariato' : 'RIMESCOLATO', preTailStable);
            expect(preTailStable).toBe(true);
        }
        expect(consoleCapture.errors).toEqual([]);
    });

    it('ogni card: nome, quote U3.5/O4.5/U4.5 = live.books, posizioni = positions con matched>0', async () => {
        const st = await fetchMikeState();
        const sticky = rememberLive(st.events, new Set<string>());
        const sections = splitMikeEvents(st.events, sticky);
        const active = [...sections.pre, ...sections.live, ...sections.fix];

        renderPage();
        await loaded();
        const cards = screen.queryAllByTestId('mike-match-card');
        rep.check('Card renderizzate nel tab Partite', String(active.length), String(cards.length));

        let nameKo = 0; let quoteKo = 0; let posKo = 0; const details: string[] = [];
        for (let i = 0; i < active.length; i += 1) {
            const ev = active[i];
            const card = cards[i];
            if (!card) { nameKo += 1; continue; }
            const t = text(card);
            // nome della partita
            const name = ev.event_name ?? ev.event_id;
            if (!t.includes(name)) { nameKo += 1; details.push(`${ev.event_id}: nome «${name}» non mostrato`); }
            // quote delle tre linee
            const books = (ev.live?.books ?? {}) as Record<string, { best_back?: number | null; best_lay?: number | null } | undefined>;
            const quotes: [string, string][] = [
                ['mike-quote-ou35', 'OU35|UNDER'],
                ['mike-quote-ou45', 'OU45|OVER'],
                ['mike-quote-ou45-under', 'OU45|UNDER'],
            ];
            for (const [tid, key] of quotes) {
                const node = within(card).queryByTestId(tid);
                const shown = text(node);
                const b = books[key];
                const back = fmtOdds(b?.best_back ?? null);
                const lay = fmtOdds(b?.best_lay ?? null);
                if (!shown.includes(back) || !shown.includes(lay)) {
                    quoteKo += 1;
                    details.push(`${ev.event_id} ${key}: atteso back ${back} / lay ${lay} — mostrato «${shown}»`);
                }
            }
            // posizioni: una riga per selezione con capitale a rischio
            const expectedRows = positionRows(ev).length;
            const shownRows = within(card).queryAllByTestId('mike-pos-row').length;
            if (expectedRows !== shownRows) {
                posKo += 1;
                details.push(`${ev.event_id}: posizioni attese ${expectedRows}, mostrate ${shownRows}`);
            }
        }
        rep.mark('Card — nome partita corretto', `${active.length}/${active.length}`, `${active.length - nameKo}/${active.length}`, nameKo === 0);
        rep.mark('Card — quote U3.5 / O4.5 / U4.5 = live.books', `${active.length * 3} confronti OK`, `${active.length * 3 - quoteKo} OK`, quoteKo === 0);
        rep.mark('Card — righe posizione = positionRows(ev)', `${active.length}/${active.length}`, `${active.length - posKo}/${active.length}`, posKo === 0);
        if (details.length) {
            rep.finding('CRITICAL', 'components/mike/MikeMatchCard.tsx', details.slice(0, 8).join(' | '));
        }
        // dettaglio delle partite con posizione: la matematica del bloccato
        const withPos = active.filter((e) => activeLegs(e).some((l) => l.matched > 0));
        rep.note(`partite con posizione: ${withPos.length} → ${withPos.map((e) => `${e.event_name} (${positionRows(e).length} sel, bloccato ${fmtMoney(e.live?.locked ?? null, { signed: true })}, liability ${fmtMoney(e.live?.liability ?? null)})`).join(' · ') || 'nessuna'}`);
        const noLiab = withPos.filter((e) => e.live?.liability == null);
        rep.mark('Card — liability per partita valorizzata dal servizio',
            `${withPos.length}/${withPos.length}`, `${withPos.length - noLiab.length}/${withPos.length}`, noLiab.length === 0);
        if (noLiab.length) {
            rep.finding('MEDIUM', 'get_mike_state → events[].live.liability / live.locked (servizio Mike)',
                `${noLiab.length} partite su ${withPos.length} hanno posizioni abbinate ma live.liability e live.locked a null: la card mostra «—» su «Liability aperta» e «P&L bloccato» mentre l'aggregato di pagina dichiara ${fmtMoney(Number((st.aggregates ?? {}).open_liability ?? 0))}. Il trader non sa QUALE partita porta l'esposizione. Il dato lo scrive il servizio, non la UI (che ha il fallback «—»).`);
        }
        for (const ev of withPos.slice(0, 6)) {
            const card = cards[active.indexOf(ev)];
            if (!card) continue;
            rep.check(`Card ${ev.event_id} — «P&L bloccato» della partita`,
                ev.live?.locked != null ? fmtMoney(ev.live.locked, { signed: true }) : '—',
                text(within(card).queryByTestId('mike-locked')));
            rep.check(`Card ${ev.event_id} — «Liability aperta» della partita`,
                ev.live?.liability != null ? fmtMoney(ev.live.liability) : '—',
                text(within(card).queryByTestId('mike-liability')));
        }
        expect(nameKo + quoteKo + posKo).toBe(0);
    });

    it('attività, tab Trade e Storico', async () => {
        const st = await fetchMikeState();
        renderPage();
        await loaded();
        const user = userEvent.setup();

        await user.click(screen.getByLabelText(/^Attività/));
        await waitFor(() => expect(screen.getByTestId('mike-activity')).toBeInTheDocument());
        const actRows = screen.queryAllByTestId('mike-activity-row');
        rep.check('Attività — righe = get_mike_state.activity', String(st.activity.length), String(actRows.length));

        await user.click(screen.getByLabelText(/^Trade/));
        await waitFor(() => expect(screen.getByLabelText(/^Trade/)).toHaveAttribute('data-state', 'active'));
        rep.check('Tab «Trade» — contatore', `📋 Trade (${st.trades.length})`, text(screen.getByLabelText(/^Trade/)));

        // Storico: get_mike_daily è rotto sul DB (overload ambiguo) → deve
        // almeno dichiararlo, non morire in silenzio
        const daily = await fetchMikeDaily('2026-09-05', romeDay()).catch((e: Error) => e);
        const dailyBroken = daily instanceof Error;
        rep.mark('get_mike_daily', 'righe dello storico', dailyBroken ? `ERRORE: ${daily.message}` : `${daily.length} giorni`, !dailyBroken);
        await user.click(screen.getByLabelText(/^Storico/));
        await waitFor(() => expect(screen.getByTestId('trading-history')).toBeInTheDocument(), { timeout: 30_000 });
        await new Promise((r) => setTimeout(r, 4_000));
        const err = screen.queryByTestId('history-error');
        rep.mark('Storico — errore dichiarato in pagina', dailyBroken ? 'banner di errore' : 'nessuno',
            err ? text(err).slice(0, 160) : 'nessuno', dailyBroken ? Boolean(err) : !err);
        if (dailyBroken) {
            rep.finding('CRITICAL', 'pages/Mike.tsx:442 → TradingHistory(variant=mike) → get_mike_daily / get_mike_day_trades',
                `lo STORICO di Mike non funziona sul DB attuale: ${daily.message}. Causa: coesistono le versioni a 7 e 8 argomenti di public.trading_daily_history (e 3/4 di trading_day_trades) — va applicata migrations/mike_history_v2.sql, che le droppa e ricrea una sola firma.`);
        }

        // italiano
        const body = text(document.body);
        const naked = ['PENDING', 'HEDGED', 'SETTLED', 'CANCELLED', 'PRE_OPEN', 'IDLE_LIVE'].filter((w) => body.includes(w));
        rep.mark('testi in italiano (nessuno stato tecnico nudo)', 'nessuno', naked.join(',') || 'nessuno', naked.length === 0);
        if (naked.length) rep.finding('LOW', 'pages/Mike.tsx / MikeMatchCard', `stati tecnici nudi a schermo: ${naked.join(', ')}`);
        rep.mark('formato denaro italiano', 'sì', /\d,\d{2}\s€/.test(body) ? 'sì' : 'NO', /\d,\d{2}\s€/.test(body));
        rep.mark('quote con la virgola', 'sì', /\d,\d{2}/.test(body) ? 'sì' : 'NO', /\d,\d{2}/.test(body));
    });
});
