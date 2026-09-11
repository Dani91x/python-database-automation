// Test COMPONENTE del pannello Rischio: liability vs cap (barra), stop
// perdita (rosso quando attivo) e conteggi per tipo di opportunita'.
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RiskPanel } from './RiskPanel';

describe('RiskPanel', () => {
    it('liability giornaliera vs cap con barra e percentuale; stop non attivo', () => {
        render(<RiskPanel risk={{ daily_liability: 125, daily_cap: 500, loss_stop_active: false, daily_loss_stop: -50 }} opps={{ model: 3, anomaly: 1, combo: 2, tennis: 0 }} />);
        expect(screen.getByTestId('risk-liability')).toHaveTextContent('125,00 €');
        expect(screen.getByText('impegnato oggi / cap 500,00 €')).toBeInTheDocument();
        expect(screen.getByRole('progressbar', { name: 'Liability giornaliera rispetto al cap' })).toHaveAttribute('aria-valuenow', '25');
        expect(screen.getByTestId('loss-stop')).toHaveTextContent('stop ok');
        expect(screen.getByTestId('risk-panel')).toHaveAttribute('data-loss-stop', 'off');
        expect(screen.getByTestId('loss-stop').title).toMatch(/scatta sotto −50,00 €/);
        const counts = screen.getByTestId('risk-opp-counts');
        expect(counts).toHaveTextContent('MODELLO 3');
        expect(counts).toHaveTextContent('ANOMALIA 1');
        expect(counts).toHaveTextContent('COMBINAZIONE 2');
        expect(counts).toHaveTextContent('TENNIS 0');
    });

    it('stop perdita attivo: badge rosso pulsante e pannello marcato', () => {
        render(<RiskPanel risk={{ daily_liability: 480, daily_cap: 500, loss_stop_active: true, daily_loss_stop: -50 }} opps={null} />);
        expect(screen.getByTestId('risk-panel')).toHaveAttribute('data-loss-stop', 'active');
        expect(screen.getByTestId('loss-stop')).toHaveTextContent('STOP PERDITA');
        expect(screen.getByTestId('loss-stop').className).toMatch(/red/);
        expect(screen.getByTestId('loss-stop').title).toMatch(/SCATTATO/);
    });

    it('senza stats.risk: cap dai parametri, conteggi calcolati dalla UI', () => {
        render(<RiskPanel risk={null} opps={null} fallbackCounts={{ model: 1, anomaly: 0, combo: 0, tennis: 4 }} paramDailyCap={300} paramLossStop={-20} />);
        expect(screen.getByText('impegnato oggi / cap 300,00 €')).toBeInTheDocument();
        expect(screen.getByTestId('risk-liability')).toHaveTextContent('0,00 €');
        expect(screen.getByTestId('risk-opp-counts')).toHaveTextContent('TENNIS 4');
    });
});

// ---------------------------------------------------------------------------
// Senza safe_strategy_bot_v2.sql l'impegnato di giornata non viene dal
// servizio: e' sommato dal client sulle righe caricate. Il pannello lo DICHIARA
// invece di mostrarlo come un numero del servizio.
// ---------------------------------------------------------------------------
describe('RiskPanel — impegnato stimato dal client (senza migrazione v2)', () => {
    it('dayFromUi: avviso esplicito che cita la migrazione', () => {
        render(<RiskPanel risk={null} opps={null} dayLiability={125} openLiability={60} dayFromUi paramDailyCap={500} />);
        const nota = screen.getByTestId('risk-day-estimated');
        expect(nota).toHaveTextContent(/stimato dal client/);
        expect(nota).toHaveTextContent(/safe_strategy_bot_v2\.sql/);
        expect(nota.title).toMatch(/righe caricate/);
        // il numero si vede comunque: si dichiara la provenienza, non si nasconde
        expect(screen.getByTestId('risk-liability')).toHaveTextContent('125,00 €');
    });

    it('con i numeri del servizio (v2) nessun avviso', () => {
        render(<RiskPanel risk={{ daily_liability: 125, daily_cap: 500, loss_stop_active: false }} opps={{ model: 1 }} />);
        expect(screen.queryByTestId('risk-day-estimated')).toBeNull();
    });
});
