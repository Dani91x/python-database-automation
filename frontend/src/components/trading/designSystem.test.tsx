// Test dei COMPONENTI CONDIVISI del design system di trading.
// Render + data-testid + varianti: sono la rete di sicurezza per gli agenti
// che rifaranno i contenuti dei tab delle tre sezioni.
import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';

import { PageShell } from './PageShell';
import { BotHeader, BOT_IDENTITY, botStatusWithBeat } from './BotHeader';
import { ServiceHealthChip } from './ServiceHealthChip';
import { ModeToggle } from './ModeToggle';
import { ModeBanner } from './ModeBanner';
import { LiveConfirmDialog } from './LiveConfirmDialog';
import { StatTile, KpiRow, toneOf } from './StatTile';
import { DayBar } from './DayBar';
import { EmptyState, LoadingState, SectionCard } from './EmptyState';
import { ActivityFeed } from './ActivityFeed';
import { EquityCard } from './EquityCard';
import { ParamsSheetBase, clampField, clampValues, type ParamGroup } from './ParamsSheetBase';

function wrap(ui: React.ReactNode) {
    return render(<HelmetProvider><MemoryRouter>{ui}</MemoryRouter></HelmetProvider>);
}

describe('PageShell', () => {
    it('monta guscio, header e footer', () => {
        wrap(
            <PageShell title="Test | Bot" header={<div data-testid="hdr" />} footer="fonte dati: feed unico">
                <div data-testid="child" />
            </PageShell>,
        );
        expect(screen.getByTestId('page-shell')).toBeInTheDocument();
        expect(screen.getByTestId('hdr')).toBeInTheDocument();
        expect(screen.getByTestId('child')).toBeInTheDocument();
        expect(screen.getByTestId('page-footer')).toHaveTextContent('feed unico');
    });
});

describe('BotHeader', () => {
    const base = { running: false, onStart: () => {}, onStop: () => {} };
    it('identita del bot, stato e bottone Avvia', () => {
        wrap(<BotHeader bot="omega" status="idle" {...base} />);
        const h = screen.getByTestId('bot-header');
        expect(h).toHaveAttribute('data-bot', 'omega');
        expect(within(h).getByTestId('bot-name')).toHaveTextContent('OMEGA');
        expect(within(h).getByTestId('bot-status')).toHaveTextContent('INATTIVO');
        expect(within(h).getByTestId('bot-start')).toHaveTextContent('Avvia');
        expect(screen.getByRole('link', { name: /AI TERMINAL/ })).toHaveAttribute('href', '/select-sport');
    });
    it('in corsa mostra Ferma, con il prefisso di stato di Safe/Mike', () => {
        wrap(<BotHeader bot="safe" status="running" statusPrefix="BOT" {...base} running />);
        expect(screen.getByTestId('bot-status')).toHaveTextContent('BOT IN CORSA');
        expect(screen.getByTestId('bot-stop')).toHaveTextContent('Ferma');
        expect(screen.queryByTestId('bot-start')).toBeNull();
    });
    it('un colore d accento per bot (mancanza §15)', () => {
        expect(BOT_IDENTITY.omega.accent).toBe('text-primary');
        expect(BOT_IDENTITY.safe.accent).toBe('text-secondary');
        expect(BOT_IDENTITY.mike.accent).toBe('text-teal-300');
    });
    // ================= certificazione 11/09 (dati reali): stato SENZA BATTITO
    // I tre servizi erano fermi da 5 h e i badge dicevano "IN CORSA": `status`
    // e' quello che il DB DICHIARA, non quello che il servizio FA.
    const T0 = Date.parse('2026-09-11T20:00:00Z');
    const beat = (secondiFa: number) => new Date(T0 - secondiFa * 1000).toISOString();

    it('running + battito FRESCO: lo stato resta quello normale', () => {
        wrap(<BotHeader bot="omega" status="running" {...base} running heartbeatAt={beat(5)} nowMs={T0} />);
        const badge = screen.getByTestId('bot-status');
        expect(badge).toHaveTextContent('IN CORSA');
        expect(badge).not.toHaveTextContent('SENZA BATTITO');
        expect(badge).not.toHaveAttribute('data-stale');
    });

    it('running + battito VECCHIO (> 45 s): "IN CORSA · SENZA BATTITO" in rosso', () => {
        wrap(<BotHeader bot="omega" status="running" {...base} running heartbeatAt={beat(5 * 3600)} nowMs={T0} />);
        const badge = screen.getByTestId('bot-status');
        expect(badge).toHaveTextContent('IN CORSA · SENZA BATTITO');
        expect(badge).toHaveAttribute('data-stale', 'true');
        expect(badge.className).toMatch(/red/);
        // e dice quanto e cosa fare (title): mai un allarme senza rimedio
        expect(badge.getAttribute('title')).toMatch(/non batte da 5 h 00/);
        expect(badge.getAttribute('title')).toMatch(/riavvia l/);
    });

    it('running SENZA battito mai scritto: anomalo, lo dice', () => {
        wrap(<BotHeader bot="mike" status="running" statusPrefix="BOT" {...base} running heartbeatAt={null} nowMs={T0} />);
        const badge = screen.getByTestId('bot-status');
        expect(badge).toHaveTextContent('BOT IN CORSA · SENZA BATTITO');
        expect(badge.getAttribute('title')).toMatch(/mai battuto/);
    });

    it('lo stato NON running non viene giudicato dal battito', () => {
        for (const st of ['idle', 'stopped', 'error', 'stopping']) {
            const { unmount } = render(
                <HelmetProvider><MemoryRouter>
                    <BotHeader bot="safe" status={st} {...base} heartbeatAt={beat(5 * 3600)} nowMs={T0} />
                </MemoryRouter></HelmetProvider>,
            );
            expect(screen.getByTestId('bot-status'), st).not.toHaveTextContent('SENZA BATTITO');
            unmount();
        }
    });

    it('retro-compatibile: senza heartbeatAt/nowMs il badge e quello di prima', () => {
        wrap(<BotHeader bot="safe" status="running" statusPrefix="BOT" {...base} running />);
        expect(screen.getByTestId('bot-status')).toHaveTextContent('BOT IN CORSA');
        expect(screen.getByTestId('bot-status')).not.toHaveTextContent('SENZA BATTITO');
    });

    it('botStatusWithBeat: funzione PURA, la soglia e quella del chip di salute', () => {
        expect(botStatusWithBeat('running', '', beat(44), T0).stale).toBe(false);
        expect(botStatusWithBeat('running', '', beat(46), T0).stale).toBe(true);
        // senza orologio nessun giudizio (il chiamante non lo passa)
        expect(botStatusWithBeat('running', '', beat(5 * 3600), undefined).stale).toBe(false);
    });

    it('ospita salute, toggle e parametri e misura l altezza', () => {
        const onHeight = vi.fn();
        wrap(
            <BotHeader
                bot="mike" status="error" statusTestId="mike-status" {...base}
                health={<div data-testid="h" />} modeToggle={<div data-testid="m" />} params={<div data-testid="p" />}
                onHeight={onHeight}
            />,
        );
        expect(screen.getByTestId('mike-status')).toHaveTextContent('ERRORE');
        expect(screen.getByTestId('h')).toBeInTheDocument();
        expect(screen.getByTestId('m')).toBeInTheDocument();
        expect(screen.getByTestId('p')).toBeInTheDocument();
        expect(onHeight).toHaveBeenCalled();
    });
});

describe('ServiceHealthChip', () => {
    const NOW = Date.parse('2026-09-11T16:05:07Z');
    it('feed vivo e servizio vivo: verde con le eta', () => {
        wrap(<ServiceHealthChip botName="Omega" nowMs={NOW} feedUpdatedAt="2026-09-11T16:05:04Z" heartbeatAt="2026-09-11T16:05:00Z" counts={{ calcio: 7, tennis: 3 }} source="stream" streamMarkets={120} />);
        const chip = screen.getByTestId('service-health');
        expect(chip).toHaveAttribute('data-feed', 'alive');
        expect(chip).toHaveAttribute('data-service', 'alive');
        expect(chip).toHaveTextContent('feed vivo (3 s)');
        expect(chip).toHaveTextContent('servizio Omega vivo (7 s)');
        expect(chip).toHaveTextContent('STREAM 120');
        expect(chip.className).toMatch(/emerald/);
    });
    it('ciclo DEGRADATO: avviso ambra, non "servizio morto"', () => {
        wrap(<ServiceHealthChip botName="Omega" nowMs={NOW} feedUpdatedAt="2026-09-11T16:05:04Z" heartbeatAt="2026-09-11T16:05:00Z" degraded="fase di regolamento interrotta" />);
        const chip = screen.getByTestId('service-health');
        expect(chip).toHaveAttribute('data-degraded', '1');
        expect(chip).toHaveAttribute('data-service', 'alive');
        expect(screen.getByTestId('service-degraded')).toHaveTextContent('CICLO DEGRADATO: fase di regolamento interrotta');
        expect(chip.className).toMatch(/amber/);
        expect(screen.queryByTestId('service-health-action')).toBeNull();
    });
    it('feed fermo: rosso e dice cosa fare', () => {
        wrap(<ServiceHealthChip botName="Safe" nowMs={NOW} feedUpdatedAt="2026-09-11T16:00:00Z" heartbeatAt={null} />);
        const chip = screen.getByTestId('service-health');
        expect(chip).toHaveAttribute('data-feed', 'stale');
        expect(chip).toHaveTextContent('feed FERMO da 5 min');
        expect(chip).toHaveTextContent('servizio Safe: nessun battito');
        expect(screen.getByTestId('service-health-action')).toHaveTextContent('riavvia l’app desktop');
        expect(chip.className).toMatch(/red/);
    });
    it('nessun dato dal feed e DRY/REST', () => {
        wrap(<ServiceHealthChip botName="Mike" nowMs={NOW} feedUpdatedAt={null} feedMissing dry source="rest" />);
        const chip = screen.getByTestId('service-health');
        expect(chip).toHaveTextContent('feed: nessun dato');
        expect(chip).toHaveTextContent('DRY');
        expect(chip).toHaveTextContent('REST');
        expect(screen.getByTestId('service-health-action')).toHaveTextContent('nessun heartbeat');
    });
    it('battito oltre 45 s = servizio morto', () => {
        wrap(<ServiceHealthChip botName="Omega" nowMs={NOW} feedUpdatedAt="2026-09-11T16:05:04Z" heartbeatAt="2026-09-11T16:04:00Z" />);
        expect(screen.getByTestId('service-health')).toHaveAttribute('data-service', 'stale');
    });
});

describe('ModeToggle', () => {
    it('due bottoni con aria-pressed (accessibilita §17)', async () => {
        const onChange = vi.fn();
        wrap(<ModeToggle mode="paper" onChange={onChange} />);
        expect(screen.getByRole('button', { name: 'PAPER' })).toHaveAttribute('aria-pressed', 'true');
        expect(screen.getByRole('button', { name: 'LIVE' })).toHaveAttribute('aria-pressed', 'false');
        await userEvent.setup().click(screen.getByRole('button', { name: 'LIVE' }));
        expect(onChange).toHaveBeenCalledWith('live');
    });
});

describe('ModeBanner', () => {
    it('PAPER verde, LIVE rosso con role alert', () => {
        const { unmount } = wrap(<ModeBanner mode="paper" liveText="live" paperText="simulazione fedele" />);
        const b = screen.getByTestId('mode-banner');
        expect(b).toHaveTextContent('MODALITÀ PAPER');
        expect(b).toHaveTextContent('simulazione fedele');
        expect(b.className).toMatch(/emerald/);
        expect(b).not.toHaveAttribute('role', 'alert');
        unmount();
        wrap(<ModeBanner mode="live" liveText="soldi veri" paperText="p" />);
        const l = screen.getByTestId('mode-banner');
        expect(l).toHaveTextContent('MODALITÀ LIVE');
        expect(l.className).toMatch(/red/);
        expect(l).toHaveAttribute('role', 'alert');
    });
    it('DRY, errore del control e migrazione assente', () => {
        wrap(<ModeBanner mode="paper" liveText="l" paperText="p" dry error="stream giù" migrationWarning="applica mike_bot.sql" testId="mike-mode-banner" />);
        const b = screen.getByTestId('mike-mode-banner');
        expect(b).toHaveTextContent('DRY');
        expect(within(b).getByTestId('mode-banner-error')).toHaveTextContent('stream giù');
        expect(within(b).getByTestId('mode-banner-migration')).toHaveTextContent('mike_bot.sql');
    });
});

describe('LiveConfirmDialog', () => {
    it('titolo unico, avvertenza per bot e i due bottoni', async () => {
        const onConfirm = vi.fn();
        const onOpenChange = vi.fn();
        wrap(<LiveConfirmDialog open onOpenChange={onOpenChange} onConfirm={onConfirm} intro="Omega piazzerà lay reali" warning="coda pesante" />);
        expect(await screen.findByText('Passare a LIVE (soldi veri)?')).toBeInTheDocument();
        expect(screen.getByText('Omega piazzerà lay reali')).toBeInTheDocument();
        expect(screen.getByText('coda pesante')).toBeInTheDocument();
        const user = userEvent.setup();
        await user.click(screen.getByRole('button', { name: 'Annulla' }));
        expect(onOpenChange).toHaveBeenCalledWith(false);
        await user.click(screen.getByTestId('live-confirm-ok'));
        expect(onConfirm).toHaveBeenCalled();
    });
});

describe('StatTile / KpiRow', () => {
    it('toni e sottotitolo', () => {
        wrap(
            <KpiRow>
                <StatTile label="P&L oggi" value="+12,50 €" tone="pos" sub="giornata operativa" testId="t1" />
                <StatTile label="Liability aperta" value="480,00 €" tone="danger" />
            </KpiRow>,
        );
        expect(screen.getByTestId('kpi-row')).toBeInTheDocument();
        const t1 = screen.getByTestId('t1');
        expect(t1).toHaveTextContent('P&L oggi');
        expect(t1).toHaveTextContent('+12,50 €');
        expect(t1.querySelector('.text-emerald-400')).not.toBeNull();
        expect(screen.getByText('480,00 €').className).toMatch(/text-orange-400/);
    });
    it('skeleton uniforme in caricamento', () => {
        wrap(<KpiRow loading tiles={3} />);
        expect(screen.getByTestId('kpi-row')).toHaveAttribute('data-loading', '1');
        expect(screen.queryAllByTestId('stat-tile')).toHaveLength(0);
    });
    it('toneOf dal segno', () => {
        expect(toneOf(1)).toBe('pos');
        expect(toneOf(-1)).toBe('neg');
        expect(toneOf(null)).toBe('pos');
    });
});

describe('DayBar', () => {
    it('bot con obiettivo: barra, resta, contatori, liability', () => {
        wrap(<DayBar dayLabel="giovedì 10 settembre 2026" realized={60} realizedTotal={900} goal={250} matches={3} operations={4} won={2} lost={1} live={1} openLiability={480} lockedPnl={-22.1} />);
        const bar = screen.getByTestId('day-bar');
        expect(bar).toHaveTextContent('Giornata operativa');
        expect(screen.getByTestId('day-bar-day')).toHaveTextContent('giovedì 10 settembre 2026');
        const line = screen.getByTestId('day-bar-line');
        expect(line).toHaveTextContent('Obiettivo di oggi 250,00 €');
        expect(line).toHaveTextContent('realizzato oggi +60,00 €');
        expect(screen.getByTestId('day-bar-remaining')).toHaveTextContent('190,00 €');
        expect(screen.getByTestId('day-bar-counts')).toHaveTextContent('partite 3 · operazioni 4 · 2V 1P · 1 vive');
        expect(screen.getByTestId('day-bar-liability')).toHaveTextContent('480,00 €');
        expect(screen.getByTestId('day-bar-locked')).toHaveTextContent('−22,10 €');
        expect(line).toHaveTextContent('totale storico +900,00 €');
        const pb = screen.getByRole('progressbar');
        expect(pb).toHaveAttribute('aria-valuenow', '24');
        expect(bar).toHaveTextContent('24,0 %');   // §1: UNA forma per le percentuali (fmtPctPoints)
    });
    it('obiettivo centrato', () => {
        wrap(<DayBar dayLabel="oggi" realized={260} goal={250} />);
        expect(screen.getByTestId('day-bar-goal-hit')).toHaveTextContent('CENTRATO');
        expect(screen.getByTestId('day-bar-line')).toHaveTextContent('+10,00 € oltre');
        expect(screen.queryByTestId('day-bar-remaining')).toBeNull();
    });
    it('bot senza obiettivo: nessuna barra, solo giornata e contatori', () => {
        wrap(<DayBar dayLabel="oggi" realized={-5} operations={2} />);
        expect(screen.queryByRole('progressbar')).toBeNull();
        expect(screen.getByTestId('day-bar-line')).toHaveTextContent('realizzato oggi −5,00 €');
        expect(screen.getByTestId('day-bar-line')).not.toHaveTextContent('Obiettivo');
    });
    it('testid personalizzabili (le pagine conservano i loro storici)', () => {
        wrap(<DayBar dayLabel="oggi" realized={1} goal={10} testId="omega-daily-mission" ids={{ line: 'omega-mission-line', day: 'omega-operating-day', remaining: 'omega-remaining' }} />);
        expect(screen.getByTestId('omega-daily-mission')).toBeInTheDocument();
        expect(screen.getByTestId('omega-mission-line')).toBeInTheDocument();
        expect(screen.getByTestId('omega-operating-day')).toBeInTheDocument();
        expect(screen.getByTestId('omega-remaining')).toBeInTheDocument();
    });
});

describe('EmptyState / LoadingState / SectionCard', () => {
    it('box vuoto tratteggiato', () => {
        wrap(<EmptyState>Nessuna partita seguita.</EmptyState>);
        const e = screen.getByTestId('empty-state');
        expect(e).toHaveTextContent('Nessuna partita seguita.');
        expect(e.className).toMatch(/border-dashed/);
    });
    it('caricamento con testo', () => {
        wrap(<LoadingState label="caricamento Omega…" />);
        expect(screen.getByTestId('loading-state')).toHaveTextContent('caricamento Omega…');
    });
    it('card di sezione: titolo, contatore, nota, azioni', async () => {
        const onClick = vi.fn();
        wrap(
            <SectionCard title="Partite di oggi" count={3} note="· 4 operazioni" actions={<button onClick={onClick}>mostra tutte</button>} testId="sec">
                <div data-testid="body" />
            </SectionCard>,
        );
        const c = screen.getByTestId('sec');
        expect(c).toHaveTextContent('Partite di oggi (3)');
        expect(c).toHaveTextContent('· 4 operazioni');
        expect(screen.getByTestId('body')).toBeInTheDocument();
        await userEvent.setup().click(screen.getByRole('button', { name: 'mostra tutte' }));
        expect(onClick).toHaveBeenCalled();
    });
});

describe('ActivityFeed', () => {
    const rows = [
        { id: 1, ts: '2026-09-11T16:05:07Z', kind: 'place', event_name: 'Roma v Lazio', payload: { side: 'lay', selection_name: '3 - 2', size: 5.26, price: 110 } },
        { id: 2, ts: '2026-09-11T16:06:00Z', kind: 'cashout_failed', event_name: 'Milan v Inter', payload: { err: 'INVALID_BET_SIZE' } },
    ];
    it('ora di Roma, badge italiano, riga generica', () => {
        wrap(<ActivityFeed rows={rows} />);
        const r = screen.getAllByTestId('activity-row');
        expect(r).toHaveLength(2);
        expect(r[0]).toHaveTextContent('18:05');
        expect(r[0]).toHaveTextContent('ORDINE');
        expect(r[0]).toHaveTextContent('Roma v Lazio · lay 3 - 2 · 5,26 € @ 110,00');
    });
    it('le righe critiche sono in rosso e marcate', () => {
        wrap(<ActivityFeed rows={rows} />);
        const r = screen.getAllByTestId('activity-row');
        expect(r[1]).toHaveAttribute('data-critical', '1');
        expect(r[1]).toHaveTextContent('CASH OUT FALLITO');
        expect(r[1].querySelector('.text-red-300')).not.toBeNull();
    });
    it('vuoto con messaggio unico', () => {
        wrap(<ActivityFeed rows={[]} />);
        expect(screen.getByTestId('activity-feed')).toHaveTextContent('nessuna attività oggi');
    });
    it('filtro per evento opzionale', async () => {
        wrap(<ActivityFeed rows={rows} filterable />);
        expect(screen.getByTestId('activity-filter')).toBeInTheDocument();
        await userEvent.setup().click(screen.getByRole('button', { name: 'Milan v Inter' }));
        expect(screen.getAllByTestId('activity-row')).toHaveLength(1);
    });
    it('metaOf e lineOf della sezione hanno la precedenza', () => {
        wrap(<ActivityFeed rows={rows} metaOf={() => ({ label: 'CUSTOM', cls: '' })} lineOf={() => 'riga mia'} />);
        expect(screen.getAllByTestId('activity-row')[0]).toHaveTextContent('CUSTOM');
        expect(screen.getAllByTestId('activity-row')[0]).toHaveTextContent('riga mia');
    });
});

describe('EquityCard', () => {
    it('titolo unico + ambito, e il vuoto spiegato', () => {
        wrap(<EquityCard series={[]} scope="giornata 10 settembre" emptyLabel="nessun match ancora regolato" />);
        const c = screen.getByTestId('equity-card');
        expect(c).toHaveTextContent('Equity curve · P&L cumulato regolato');
        expect(c).toHaveTextContent('giornata 10 settembre');
        expect(c).toHaveTextContent('nessun match ancora regolato');
    });
    it('con dati disegna la curva', () => {
        wrap(<EquityCard series={[{ t: 1, v: 2, iso: 'a' }, { t: 2, v: -1, iso: 'b' }]} label="Equity Omega" />);
        expect(screen.getByRole('img', { name: 'Equity Omega' })).toBeInTheDocument();
    });
});

describe('ParamsSheetBase', () => {
    const GROUPS: ParamGroup[] = [{
        label: 'Ingressi',
        fields: [
            { key: 'stake', label: 'Importo €', type: 'number', min: 0.5, max: 100, step: 0.5, hint: 'stake per gamba' },
            { key: 'greenup', label: 'Green-up attivo', type: 'boolean' },
            { key: 'source', label: 'Sorgente minuto', type: 'select', options: [{ value: 'score', label: 'score' }, { value: 'clock', label: 'clock' }] },
        ],
    }];

    it('clampField / clampValues sono puri e dichiarano il clamp', () => {
        const f = GROUPS[0].fields[0];
        expect(clampField(f, 200)).toEqual({ value: 100, clamped: true });
        expect(clampField(f, 0.1)).toEqual({ value: 0.5, clamped: true });
        expect(clampField(f, 10)).toEqual({ value: 10, clamped: false });
        const r = clampValues(GROUPS, { stake: 999, greenup: true, source: 'score' });
        expect(r.values.stake).toBe(100);
        expect(r.clamped).toEqual({ stake: 100 });
    });

    it('apre lo sheet, mostra i gruppi e salva', async () => {
        const onSave = vi.fn();
        const user = userEvent.setup();
        wrap(<ParamsSheetBase title="Parametri Omega" groups={GROUPS} values={{ stake: 10, greenup: true, source: 'score' }} onSave={onSave} />);
        await user.click(screen.getByTestId('params-trigger'));
        expect(await screen.findByTestId('params-sheet')).toBeInTheDocument();
        expect(screen.getByTestId('params-group')).toHaveAttribute('data-group', 'Ingressi');
        expect((screen.getByLabelText('Importo €') as HTMLInputElement).value).toBe('10');
        expect(screen.getByRole('checkbox', { name: 'Green-up attivo' })).toBeChecked();
        await user.click(screen.getByTestId('params-save'));
        expect(onSave).toHaveBeenCalledWith({ stake: 10, greenup: true, source: 'score' });
    });

    it('clamp VISIBILE e indicatore di modifiche non salvate', async () => {
        const user = userEvent.setup();
        wrap(<ParamsSheetBase title="P" groups={GROUPS} values={{ stake: 10, greenup: false, source: 'score' }} onSave={vi.fn()} />);
        await user.click(screen.getByTestId('params-trigger'));
        const input = await screen.findByLabelText('Importo €');
        await user.clear(input);
        await user.type(input, '999');
        expect(screen.getByTestId('params-clamped')).toHaveTextContent('clampato a 100 (ammesso 0,50 … 100)');
        expect(screen.getByTestId('params-dirty')).toHaveTextContent('Salva parametri');
    });

    it('Default ripristina i valori di fabbrica', async () => {
        const user = userEvent.setup();
        wrap(<ParamsSheetBase title="P" groups={GROUPS} values={{ stake: 10, greenup: false, source: 'score' }} onSave={vi.fn()} onReset={() => ({ stake: 2, greenup: true, source: 'clock' })} />);
        await user.click(screen.getByTestId('params-trigger'));
        await user.click(await screen.findByTestId('params-reset'));
        expect((screen.getByLabelText('Importo €') as HTMLInputElement).value).toBe('2');
        expect(screen.getByRole('checkbox', { name: 'Green-up attivo' })).toBeChecked();
    });
});
