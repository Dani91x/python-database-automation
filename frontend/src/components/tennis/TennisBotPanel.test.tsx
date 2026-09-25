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

    it('OFF: parte con dry-run SPUNTATO, DISABILITATO, e dichiara che il runner lo forza comunque', async () => {
        const { card } = await montaPannello('OFF');
        const checkbox = card.getByRole('checkbox');
        expect(checkbox).toHaveAttribute('data-state', 'checked');
        expect(checkbox).toBeDisabled();
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

    // FIX AUDIT3 reperto b (25/09, oggi): prima di questo fix il pannello NON
    // impediva di togliere la spunta in OFF e la RPC riceveva dry_run:false
    // mentre il testo a video prometteva "dry-run forzato" (riga mentiva). Ora
    // la checkbox e' DISABILITATA e resta SEMPRE spuntata quando orderMode e'
    // OFF (useEffect in TennisBotPanel.tsx forza dryRun=true e azzera
    // dryRunTouched, come per LIVE): un click su di lei non ha alcun effetto
    // (Radix Checkbox disabled ignora l'evento) e l'armamento porta sempre
    // dry_run:true, coerente col kill-switch del runner Python
    // (Betfair/stream/tennis_live/tennis_runner.py, "OFF: dry-run FORZATO",
    // righe 654-655): la riga di tennis_bot_control non mente piu'.
    it('OFF: la checkbox e disabilitata, un click non la tocca, ARMA porta sempre dry_run=true', async () => {
        const confirmSpy = vi.spyOn(window, 'confirm');
        const { user, card } = await montaPannello('OFF');
        const checkbox = card.getByRole('checkbox');
        expect(checkbox).toBeDisabled();
        await user.click(checkbox); // disabilitata: nessun effetto
        expect(checkbox).toHaveAttribute('data-state', 'checked');
        const armaBtn = card.getByRole('button', { name: /ARMA/i });
        expect(armaBtn).not.toBeDisabled();
        await user.click(armaBtn);
        await waitFor(() => expect(mArm).toHaveBeenCalledTimes(1));
        expect(confirmSpy).not.toHaveBeenCalled();
        expect(mArm).toHaveBeenCalledWith('evt1', 'tennis_scalper', true, SCALPER.defaultStake, payloadDefaultAtteso());
    });
});

// ============================================================================
// Mutazione del coordinatore (25/09, dopo la consegna sopra): la copertura
// precedente monta il pannello GIA' in OFF, quindi non prova che il forzaggio
// avvenga nell'useEffect (riga 140) quando orderMode CAMBIA a runtime — una
// mutazione che toglie `|| orderMode === 'OFF'` da quell'effetto, lasciando
// intatto il `disabled` della checkbox, restava 12/12 verde: la checkbox
// appariva bloccata ma con lo stato interno `dryRun` rimasto quello che
// l'utente aveva scelto in PAPER (falso), quindi ARMA avrebbe comunque
// spedito dry_run:false nonostante il lucchetto a video. Caso reale: il
// pannello e' montato con orderMode PAPER (LIVE_ORDER_MODE fornito dal
// padre), l'utente sceglie ESPLICITAMENTE dry_run=false (tocca la checkbox,
// dryRunTouched=true), poi il padre passa a orderMode OFF con un rerender
// (downgrade a runtime, non un nuovo mount) — la spunta deve tornare a true
// e restare disabilitata NONOSTANTE dryRunTouched fosse gia' true.
// ============================================================================
describe('TennisBotPanel — downgrade runtime PAPER -> OFF forza dry-run (mutazione coordinatore 25/09)', () => {
    it('utente sceglie dry_run=false in PAPER (tocco esplicito), poi orderMode passa a OFF a runtime: la spunta torna true e disabilitata, ARMA porta dry_run=true', async () => {
        const confirmSpy = vi.spyOn(window, 'confirm');
        const user = userEvent.setup();
        const { rerender } = render(<TennisBotPanel eventId="evt1" marketId="mkt1" orderMode="PAPER" />);
        await screen.findByText('Tennis Scalper');
        const cardElPaper = screen.getByText('Tennis Scalper').closest('div.rounded-xl.border') as HTMLElement;
        const cardPaper = within(cardElPaper);
        const checkboxPaper = cardPaper.getByRole('checkbox');
        // default PAPER: dry-run gia' tolto (ordini simulati per costruzione). Per
        // rendere il tocco dell'utente ESPLICITO (dryRunTouched=true, condizione
        // necessaria a rendere il test sensibile alla mutazione: se non touched,
        // il ramo di fallback dell'effetto forza comunque true per qualsiasi
        // orderMode != 'PAPER', mascherando la mutazione) la spunto e la ritolgo.
        expect(checkboxPaper).toHaveAttribute('data-state', 'unchecked');
        await user.click(checkboxPaper); // la spunta: dry_run=true, touched=true
        expect(checkboxPaper).toHaveAttribute('data-state', 'checked');
        await user.click(checkboxPaper); // la ritoglie: dry_run=false, touched resta true
        expect(checkboxPaper).toHaveAttribute('data-state', 'unchecked');

        // downgrade a runtime: il padre passa orderMode='OFF' (rerender, non un nuovo mount)
        rerender(<TennisBotPanel eventId="evt1" marketId="mkt1" orderMode="OFF" />);

        const cardElOff = screen.getByText('Tennis Scalper').closest('div.rounded-xl.border') as HTMLElement;
        const cardOff = within(cardElOff);
        const checkboxOff = cardOff.getByRole('checkbox');
        await waitFor(() => expect(checkboxOff).toHaveAttribute('data-state', 'checked'));
        expect(checkboxOff).toBeDisabled();

        await user.click(cardOff.getByRole('button', { name: /ARMA/i }));
        await waitFor(() => expect(mArm).toHaveBeenCalledTimes(1));
        expect(confirmSpy).not.toHaveBeenCalled();
        expect(mArm).toHaveBeenCalledWith('evt1', 'tennis_scalper', true, SCALPER.defaultStake, payloadDefaultAtteso());
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
