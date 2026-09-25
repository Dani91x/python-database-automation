// ============================================================================
// TennisBotPanel.test.tsx — gate ordini reali per bot (armamento singolo).
//
// Il gate money-critical vive in handleArm (TennisBotPanel.tsx:498-537): con
// orderMode LIVE e checkbox "dry-run" tolta, un window.confirm chiede
// conferma prima di chiamare armTennisBot; se negato l'ordine reale NON parte.
// In PAPER (sempre simulato per costruzione) e in LIVE con dry-run selezionato
// (default prudente) nessuna conferma nativa e' richiesta.
//
// NOTA PER IL COORDINATORE: il brief parlava di un "doppio gate" (DUE
// window.confirm). Letto il sorgente (TennisBotPanel.tsx:498-537) esiste UN
// solo window.confirm, non due — verificato con `grep -n "confirm(" `, un solo
// riscontro. Questi test certificano il gate SINGOLO realmente presente; non
// ho aggiunto un secondo confirm al componente (layout/logica UI intoccabile
// senza permesso esplicito dell'utente). Segnalare la discrepanza.
//
// I FINTI PARLANO COME IL VERO: default e parametri vengono da
// TENNIS_BOT_REGISTRY (lib/tennis.ts), non duplicati a mano.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('@/lib/tennis', async () => {
    const actual = await vi.importActual<typeof import('@/lib/tennis')>('@/lib/tennis');
    return {
        ...actual,
        fetchTennisBotsState: vi.fn(async () => ({ controls: [], activity: [] })),
        subscribeTennisBots: vi.fn(() => () => { /* no-op unsub */ }),
        armTennisBot: vi.fn(async (
            eventId: string,
            botKey: string,
            dryRun: boolean,
            stake: number,
            params: Record<string, number | string | boolean>,
        ) => ({
            event_id: eventId,
            bot_key: botKey,
            status: 'armed',
            dry_run: dryRun,
            stake,
            params,
            stats: null,
            error: null,
            requested_at: null,
            started_at: null,
            stopped_at: null,
            heartbeat_at: null,
        })),
        disarmTennisBot: vi.fn(async (eventId: string, botKey: string) => ({
            event_id: eventId,
            bot_key: botKey,
            status: 'stopping',
            dry_run: true,
            stake: 0,
            params: {},
            stats: null,
            error: null,
            requested_at: null,
            started_at: null,
            stopped_at: null,
            heartbeat_at: null,
        })),
    };
});

import { TennisBotPanel } from './TennisBotPanel';
import { armTennisBot, TENNIS_BOT_REGISTRY } from '@/lib/tennis';

const mArm = vi.mocked(armTennisBot);

const SCALPER = TENNIS_BOT_REGISTRY.find((d) => d.key === 'tennis_scalper')!;

// payload atteso quando NESSUN parametro e' stato toccato: identico a
// descriptor.defaults ma con i campi bool ('on'/'off' -> true/false), esattamente
// come fa handleToggle in TennisBotPanel.tsx:161-166 (i finti parlano come il vero:
// derivato dal registro, non ricopiato a mano).
function payloadDefaultAtteso(): Record<string, number | string | boolean> {
    const payload: Record<string, number | string | boolean> = { ...SCALPER.defaults };
    for (const f of SCALPER.params) {
        if (f.type === 'select' && f.bool) payload[f.key] = payload[f.key] === 'on';
    }
    return payload;
}

async function montaPannello(orderMode: 'OFF' | 'PAPER' | 'LIVE') {
    const user = userEvent.setup();
    render(<TennisBotPanel eventId="evt1" marketId="mkt1" orderMode={orderMode} />);
    await screen.findByText('Tennis Scalper');
    const cardEl = screen.getByText('Tennis Scalper').closest('div.rounded-xl.border') as HTMLElement;
    return { user, card: within(cardEl) };
}

beforeEach(() => {
    vi.clearAllMocks();
});

describe('TennisBotPanel — gate ordini reali (tennis_scalper)', () => {
    it('1) servizio PAPER: ARMA senza toccare nulla -> nessuna conferma, arma con dry_run=false (PAPER e\' sempre simulato)', async () => {
        const confirmSpy = vi.spyOn(window, 'confirm');
        const { user, card } = await montaPannello('PAPER');
        await user.click(card.getByRole('button', { name: /ARMA/i }));
        await waitFor(() => expect(mArm).toHaveBeenCalledTimes(1));
        expect(confirmSpy).not.toHaveBeenCalled();
        expect(mArm).toHaveBeenCalledWith('evt1', 'tennis_scalper', false, SCALPER.defaultStake, payloadDefaultAtteso());
    });

    it('2) servizio LIVE, checkbox dry-run NON tolta (default prudente): ARMA senza conferma, dry_run=true', async () => {
        const confirmSpy = vi.spyOn(window, 'confirm');
        const { user, card } = await montaPannello('LIVE');
        expect(card.getByRole('checkbox')).toHaveAttribute('data-state', 'checked');
        await user.click(card.getByRole('button', { name: /ARMA/i }));
        await waitFor(() => expect(mArm).toHaveBeenCalledTimes(1));
        expect(confirmSpy).not.toHaveBeenCalled();
        expect(mArm).toHaveBeenCalledWith('evt1', 'tennis_scalper', true, SCALPER.defaultStake, payloadDefaultAtteso());
    });

    it('3) servizio LIVE, checkbox dry-run TOLTA: ARMA chiede conferma; negata -> NON arma con ordini reali', async () => {
        const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
        const { user, card } = await montaPannello('LIVE');
        await user.click(card.getByRole('checkbox')); // toglie il dry-run
        expect(card.getByRole('checkbox')).toHaveAttribute('data-state', 'unchecked');
        await user.click(card.getByRole('button', { name: /ARMA/i }));
        expect(confirmSpy).toHaveBeenCalledTimes(1);
        expect(String(confirmSpy.mock.calls[0][0])).toMatch(/ORDINI REALI/i);
        expect(mArm).not.toHaveBeenCalled();
    });

    it('4) servizio LIVE, checkbox dry-run TOLTA, conferma ACCETTATA: arma con dry_run=false esplicito', async () => {
        const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
        const { user, card } = await montaPannello('LIVE');
        await user.click(card.getByRole('checkbox'));
        await user.click(card.getByRole('button', { name: /ARMA/i }));
        expect(confirmSpy).toHaveBeenCalledTimes(1);
        await waitFor(() => expect(mArm).toHaveBeenCalledTimes(1));
        expect(mArm).toHaveBeenCalledWith('evt1', 'tennis_scalper', false, SCALPER.defaultStake, payloadDefaultAtteso());
    });

    it('5) armTennisBot riceve gli argomenti nel TIPO esatto (dry_run booleano, non stringa \'on\'/\'off\')', async () => {
        vi.spyOn(window, 'confirm').mockReturnValue(true);
        const { user, card } = await montaPannello('LIVE');
        await user.click(card.getByRole('checkbox'));
        await user.click(card.getByRole('button', { name: /ARMA/i }));
        await waitFor(() => expect(mArm).toHaveBeenCalledTimes(1));
        const [eventId, botKey, dryRun, stake, params] = mArm.mock.calls[0];
        expect(eventId).toBe('evt1');
        expect(botKey).toBe('tennis_scalper');
        expect(typeof dryRun).toBe('boolean');
        expect(dryRun).toBe(false);
        expect(typeof stake).toBe('number');
        const p = params as Record<string, unknown>;
        expect(typeof p.one_tick_per_phase).toBe('boolean');
        expect(p.one_tick_per_phase).not.toBe('on');
        expect(p.one_tick_per_phase).not.toBe('off');
    });
});

// ============================================================================
// AUDIT3 (25/09) — casi aggiuntivi del reperto «nessun test di componente per
// il pannello per-partita». Il file sopra (bfd4d1f, gia' su master) copre gia'
// il gate LIVE con checkbox spuntata/tolta; qui si completano: il default per
// OGNI modalita' (incluso OFF, mai testato), la scelta ESPLICITA dell'utente
// in PAPER, il caso OFF per intero e il payload completo (nessuna scrittura
// parziale verso `tennis_bot_arm`).
// ============================================================================

describe('TennisBotPanel — default protetto per modalita (AUDIT3 caso 1)', () => {
    it('PAPER: parte con dry-run TOLTO e lo dichiara a video (ordini simulati, visibili sul ladder)', async () => {
        const { card } = await montaPannello('PAPER');
        expect(card.getByRole('checkbox')).toHaveAttribute('data-state', 'unchecked');
        expect(card.getByText(/ORDINI SIMULATI/i)).toBeTruthy();
    });

    it('LIVE: parte con dry-run SPUNTATO (default prudente), nessun avviso "ordini reali"', async () => {
        const { card } = await montaPannello('LIVE');
        expect(card.getByRole('checkbox')).toHaveAttribute('data-state', 'checked');
        expect(card.queryByText(/ORDINI REALI/i)).toBeNull();
    });

    it('OFF: parte con dry-run SPUNTATO e dichiara che il runner lo forza comunque', async () => {
        const { card } = await montaPannello('OFF');
        expect(card.getByRole('checkbox')).toHaveAttribute('data-state', 'checked');
        expect(card.getByText(/runner OFF: dry-run forzato/i)).toBeTruthy();
    });
});

describe('TennisBotPanel — PAPER: scelta ESPLICITA di togliere la spunta (AUDIT3 caso 4)', () => {
    it('PAPER, spunta/tolta a mano (gia\' tolta di default: la rimette e la ritoglie) e arma: nessun confirm, dry_run=false', async () => {
        const confirmSpy = vi.spyOn(window, 'confirm');
        const { user, card } = await montaPannello('PAPER');
        const checkbox = card.getByRole('checkbox');
        expect(checkbox).toHaveAttribute('data-state', 'unchecked');
        await user.click(checkbox); // la spunta (dry_run=true)
        expect(checkbox).toHaveAttribute('data-state', 'checked');
        await user.click(checkbox); // la toglie di nuovo: scelta esplicita dell'utente
        expect(checkbox).toHaveAttribute('data-state', 'unchecked');
        await user.click(card.getByRole('button', { name: /ARMA/i }));
        await waitFor(() => expect(mArm).toHaveBeenCalledTimes(1));
        expect(confirmSpy).not.toHaveBeenCalled();
        expect(mArm).toHaveBeenCalledWith('evt1', 'tennis_scalper', false, SCALPER.defaultStake, payloadDefaultAtteso());
    });
});

describe('TennisBotPanel — orderMode OFF (AUDIT3 caso 5)', () => {
    it('OFF, default (dry-run spuntato): ARMA senza conferma, dry_run=true', async () => {
        const confirmSpy = vi.spyOn(window, 'confirm');
        const { user, card } = await montaPannello('OFF');
        await user.click(card.getByRole('button', { name: /ARMA/i }));
        await waitFor(() => expect(mArm).toHaveBeenCalledTimes(1));
        expect(confirmSpy).not.toHaveBeenCalled();
        expect(mArm).toHaveBeenCalledWith('evt1', 'tennis_scalper', true, SCALPER.defaultStake, payloadDefaultAtteso());
    });

    // REPERTO (non e' un blocco applicativo, e' un comportamento reale da
    // dichiarare al coordinatore): in OFF il pannello NON impedisce di
    // togliere la spunta e armare. Nessun window.confirm scatta (la guardia
    // in handleArm controlla solo `orderMode === 'LIVE'`) e la RPC riceve
    // dry_run:false. Il backend forza comunque dry_run=True per il
    // kill-switch di modalita' (Betfair/stream/tennis_live/tennis_runner.py,
    // commento "OFF: dry-run FORZATO (kill-switch, il control non puo'
    // aggirarlo)", righe 654-655): quindi NON parte nessun ordine reale, ma
    // il pannello scrive comunque una riga di control con dry_run:false
    // senza alcun avviso, mentre il testo a video promette "dry-run forzato".
    it('OFF, utente toglie la spunta e arma: nessun confirm, e la RPC riceve dry_run=false (backend lo forza comunque)', async () => {
        const confirmSpy = vi.spyOn(window, 'confirm');
        const { user, card } = await montaPannello('OFF');
        const checkbox = card.getByRole('checkbox');
        expect(checkbox).not.toHaveProperty('disabled', true);
        await user.click(checkbox);
        expect(checkbox).toHaveAttribute('data-state', 'unchecked');
        const armaBtn = card.getByRole('button', { name: /ARMA/i });
        expect(armaBtn).not.toHaveProperty('disabled', true);
        await user.click(armaBtn);
        await waitFor(() => expect(mArm).toHaveBeenCalledTimes(1));
        expect(confirmSpy).not.toHaveBeenCalled();
        expect(mArm).toHaveBeenCalledWith('evt1', 'tennis_scalper', false, SCALPER.defaultStake, payloadDefaultAtteso());
    });
});

describe('TennisBotPanel — payload completo, nessuna scrittura parziale (AUDIT3 caso 7)', () => {
    it('il payload di armamento porta OGNI chiave che descriptor.params dichiara', async () => {
        const { user, card } = await montaPannello('PAPER');
        await user.click(card.getByRole('button', { name: /ARMA/i }));
        await waitFor(() => expect(mArm).toHaveBeenCalledTimes(1));
        const params = mArm.mock.calls[0][4] as Record<string, unknown>;
        for (const f of SCALPER.params) {
            expect(params).toHaveProperty(f.key);
        }
    });
});
