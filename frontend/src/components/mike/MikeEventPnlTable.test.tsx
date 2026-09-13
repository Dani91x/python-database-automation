// ============================================================================
// La tabella che il trader guarda per sapere quanto ha fatto: una riga per
// partita, il netto davanti, il dettaglio sotto.
//
// È montata in TRE schede (Operazioni, Risultati Pre-Match, Risultati Live) e
// maneggia numeri che sono soldi: qui si certifica che non menta mai — né
// mostrando «0,00» dove non c'è ancora un risultato, né un `NaN`, né sommando
// due volte gli stessi euro.
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { MikeEventPnlTable, pnlClass } from './MikeEventPnlTable';
import { groupMikeTrades, type MikeTrade } from '@/lib/mike';

let seq = 0;
function t(over: Partial<MikeTrade> = {}): MikeTrade {
    seq += 1;
    return {
        id: seq, event_id: 'E1', event_name: 'Roma v Lazio', strategy: 'under_entry',
        role: 'under_entry', cycle_no: 0, market_type: 'OVER_UNDER_35', market_id: '1.1',
        selection_id: 1222344, side: 'back', price: 1.5, size: 10, liability: 10,
        commission: 5, mode: 'paper', status: 'won', pnl: 0, bet_id: null,
        placed_at: '2026-09-13T10:00:00Z', day_placed_at: '2026-09-13T10:00:00Z',
        settled_at: null, signal_key: `k${seq}`, meta: {}, closes_trade_id: null,
        origin: 'auto', ...over,
    } as MikeTrade;
}

function ciclo(over: Partial<MikeTrade>, pnlApre: number, pnlChiude: number, ruoloChiusura: string) {
    const apre = t({ ...over, pnl: pnlApre });
    const chiude = t({
        ...over, role: ruoloChiusura, side: 'lay', pnl: pnlChiude,
        closes_trade_id: apre.id, placed_at: '2026-09-13T10:05:00Z',
    });
    return [apre, chiude];
}

function montaCon(righe: MikeTrade[], props: Record<string, unknown> = {}) {
    return render(
        <MikeEventPnlTable
            gruppi={groupMikeTrades(righe)}
            titolo="Operazioni"
            vuoto="Nessuna operazione."
            {...props}
        />,
    );
}

describe('la riga della partita', () => {
    it('mostra il netto della partita, non quello delle singole gambe', () => {
        montaCon(ciclo({}, -10, 10.13, 'under_green'));
        const riga = screen.getByTestId('partita-E1');
        expect(riga).toHaveTextContent('Roma v Lazio');
        expect(screen.getByTestId('netto-E1')).toHaveTextContent('+0,13');
        // i due P&L di gamba (-10,00 e +10,13) NON compaiono finché non si apre
        expect(screen.queryByText(/10,13/)).toBeNull();
    });

    it('verde sopra zero, rosso sotto, grigio quando non c’è risultato', () => {
        expect(pnlClass(1)).toContain('emerald');
        expect(pnlClass(-1)).toContain('red');
        expect(pnlClass(0)).toContain('slate-300');
        expect(pnlClass(null)).toContain('slate-400');
        expect(pnlClass(undefined)).toContain('slate-400');
    });

    it('una partita senza niente di regolato mostra «—», MAI «0,00»', () => {
        montaCon([t({ status: 'open', pnl: null })]);
        const netto = screen.getByTestId('netto-E1');
        expect(netto).toHaveTextContent('—');
        expect(netto).not.toHaveTextContent('0,00');
    });

    it('dichiara che il netto è PARZIALE se la partita è ancora aperta', () => {
        montaCon([t({ pnl: -10, status: 'lost' }), t({ role: 'over_cover', status: 'open', pnl: null })]);
        expect(screen.getByTestId('partita-E1')).toHaveTextContent('ancora aperta');
        expect(screen.getByTestId('netto-E1')).toHaveTextContent('parz.');
    });

    it('una partita chiusa lo dice, e il netto non è parziale', () => {
        montaCon(ciclo({}, -10, 10.13, 'under_green'));
        expect(screen.getByTestId('partita-E1')).toHaveTextContent('chiusa');
        expect(screen.getByTestId('netto-E1')).not.toHaveTextContent('parz.');
    });

    it('conta i cicli e il capitale impegnato', () => {
        montaCon([
            ...ciclo({ cycle_no: 0 }, -10, 10.13, 'under_green'),
            ...ciclo({ cycle_no: 1 }, -10, 10.20, 'under_green'),
        ]);
        const riga = screen.getByTestId('partita-E1');
        expect(riga).toHaveTextContent('2 cicli');
        expect(riga).toHaveTextContent('20,00');     // due aperture da 10
    });
});

describe('la modalità è sempre dichiarata', () => {
    it('marca «soldi veri» le partite in live', () => {
        montaCon([t({ mode: 'live' })]);
        expect(screen.getByTestId('partita-E1')).toHaveTextContent('soldi veri');
    });

    it('in paper non mette nessun marchio', () => {
        montaCon([t({ mode: 'paper' })]);
        expect(screen.getByTestId('partita-E1')).not.toHaveTextContent('soldi veri');
    });

    it('grida se una partita mescola paper e soldi veri', () => {
        montaCon([t({ mode: 'paper' }), t({ mode: 'live', role: 'over_cover' })]);
        expect(screen.getByTestId('partita-E1')).toHaveTextContent('modalità mista');
    });
});

describe('il dettaglio si apre solo se lo chiedo', () => {
    it('parte chiuso', () => {
        montaCon(ciclo({}, -10, 10.13, 'under_green'));
        expect(screen.queryByTestId('dettaglio-E1')).toBeNull();
        expect(screen.getByTestId('apri-E1')).toHaveAttribute('aria-expanded', 'false');
    });

    it('un clic lo apre e mostra cicli e ordini, un altro lo richiude', () => {
        const righe = ciclo({}, -10, 10.13, 'under_green');
        montaCon(righe);
        fireEvent.click(screen.getByTestId('apri-E1'));
        expect(screen.getByTestId('apri-E1')).toHaveAttribute('aria-expanded', 'true');
        const dettaglio = screen.getByTestId('dettaglio-E1');
        expect(within(dettaglio).getByTestId(`ciclo-${righe[0].id}`)).toHaveTextContent('ciclo 1');
        expect(within(dettaglio).getByTestId(`gamba-${righe[0].id}`)).toBeInTheDocument();
        expect(within(dettaglio).getByTestId(`gamba-${righe[1].id}`)).toBeInTheDocument();
        fireEvent.click(screen.getByTestId('apri-E1'));
        expect(screen.queryByTestId('dettaglio-E1')).toBeNull();
    });

    it('il ciclo mostra il prezzo di ingresso e quello di uscita', () => {
        const righe = ciclo({}, -10, 10.13, 'under_green');
        righe[1].price = 1.48;
        montaCon(righe);
        fireEvent.click(screen.getByTestId('apri-E1'));
        const c = screen.getByTestId(`ciclo-${righe[0].id}`);
        expect(c).toHaveTextContent('1,50');
        expect(c).toHaveTextContent('1,48');
    });

    it('apre una partita sola per volta senza toccare le altre', () => {
        montaCon([
            ...ciclo({ event_id: 'A', event_name: 'Alfa' }, -10, 10.1, 'under_green'),
            ...ciclo({ event_id: 'B', event_name: 'Beta' }, -10, 10.2, 'under_green'),
        ]);
        fireEvent.click(screen.getByTestId('apri-A'));
        expect(screen.getByTestId('dettaglio-A')).toBeInTheDocument();
        expect(screen.queryByTestId('dettaglio-B')).toBeNull();
    });

    it('le gambe non ancora regolate mostrano «—», non un P&L inventato', () => {
        const viva = t({ status: 'open', pnl: null });
        montaCon([viva]);
        fireEvent.click(screen.getByTestId('apri-E1'));
        expect(screen.getByTestId(`gamba-${viva.id}`)).toHaveTextContent('—');
    });
});

describe('il totale in cima', () => {
    /**
     * SOSTITUISCE il test che cercava `mike-event-pnl-totale`, cioè il totale
     * che stava nella NOTA dell'intestazione (una riga di testo da 11px accanto
     * al titolo).
     *
     * Perché è cambiato: richiesta dell'utente del 13/09 — «Io voglio i totali
     * delle operazioni ben chiari». I totali ora sono una BARRA in testa alla
     * sezione, sempre visibile e in corpo grande, con cinque numeri invece di
     * uno (operazioni, realizzato, se chiudo ora, investito, responsabilità).
     * Il componente è quello condiviso `trading/EventPnlTable`, quindi i testid
     * seguono il suo schema: `<testId>-totali-<grandezza>`.
     */
    it('somma solo le partite con un risultato e dichiara le aperte', () => {
        montaCon([
            ...ciclo({ event_id: 'A' }, -10, 10.13, 'under_green'),
            ...ciclo({ event_id: 'B' }, -10, 9.00, 'under_green'),
            t({ event_id: 'C', status: 'open', pnl: null }),
        ]);
        expect(screen.getByTestId('mike-event-pnl-totali-realizzato')).toHaveTextContent('−0,87');
        const sezione = screen.getByTestId('mike-event-pnl');
        expect(sezione).toHaveTextContent('1 in utile');
        expect(sezione).toHaveTextContent('1 in perdita');
        expect(sezione).toHaveTextContent('1 ancora aperta');
    });

    /**
     * SOSTITUISCE «senza partite … e nessun totale»: la barra dei totali ora
     * c'è SEMPRE (è il punto della richiesta: non deve sparire né nascondersi
     * dentro un accordion). Quello che non deve mai comparire è un numero
     * inventato: senza operazioni il realizzato è «—», mai «0,00 €».
     */
    it('senza partite mostra il messaggio di vuoto e un totale che non mente', () => {
        montaCon([]);
        expect(screen.getByTestId('mike-event-pnl-vuoto')).toHaveTextContent('Nessuna operazione.');
        const realizzato = screen.getByTestId('mike-event-pnl-totali-realizzato');
        expect(realizzato).toHaveTextContent('—');
        expect(realizzato).not.toHaveTextContent('0,00');
    });
});

describe('il filtro di fase alimenta le due schede Risultati', () => {
    const righe = [
        ...ciclo({ event_id: 'E1', role: 'under_entry' }, -10, 10.13, 'under_green'),
        ...ciclo({ event_id: 'E1', role: 'under_last' }, 8.75, -9.20, 'under_close'),
    ];

    it('pre-match vede solo i cicli chiusi prima del fischio', () => {
        montaCon(righe, { fase: 'pre' });
        expect(screen.getByTestId('netto-E1')).toHaveTextContent('+0,13');
    });

    it('live vede solo quello che è successo in gioco', () => {
        montaCon(righe, { fase: 'live' });
        expect(screen.getByTestId('netto-E1')).toHaveTextContent('−0,45');
    });
});

describe('non mostra mai numeri rotti', () => {
    it('size e prezzo non numerici non producono NaN', () => {
        const rotto = t({ size: 'tanto' as unknown as number, price: undefined as unknown as number });
        montaCon([rotto]);
        fireEvent.click(screen.getByTestId('apri-E1'));
        const html = screen.getByTestId('dettaglio-E1').textContent ?? '';
        expect(html).not.toMatch(/NaN/);
        expect(html).not.toMatch(/Infinity/);
        expect(html).not.toMatch(/undefined/);
    });

    it('una partita di sole gambe in errore non inventa un netto', () => {
        montaCon([t({ status: 'error', pnl: 0 })]);
        expect(screen.getByTestId('netto-E1')).toHaveTextContent('—');
    });

    it('un P&L nullo su una riga regolata vale zero, non NaN', () => {
        montaCon([t({ status: 'won', pnl: null })]);
        expect(screen.getByTestId('netto-E1')).toHaveTextContent('0,00');
    });
});

describe('accessibilità e comodità', () => {
    it('il bottone dice cosa fa e su quale partita', () => {
        montaCon([t()]);
        const b = screen.getByTestId('apri-E1');
        expect(b).toHaveAttribute('aria-label', expect.stringContaining('Roma v Lazio'));
        fireEvent.click(b);
        expect(screen.getByTestId('apri-E1')).toHaveAttribute('aria-label', expect.stringContaining('Chiudi'));
    });

    it('il nome della partita porta alla sua scheda senza aprire il dettaglio', () => {
        const vai = vi.fn();
        montaCon([t()], { onApriScheda: vai });
        fireEvent.click(screen.getByTestId('vai-alla-scheda-E1'));
        expect(vai).toHaveBeenCalledWith('E1');
        expect(screen.queryByTestId('dettaglio-E1')).toBeNull();
    });

    it('il nome per esteso resta leggibile nel title anche se troncato', () => {
        const lungo = 'Squadra Con Un Nome Lunghissimo v Altra Squadra Altrettanto Lunga';
        montaCon([t({ event_name: lungo })], { onApriScheda: vi.fn() });
        expect(screen.getByTestId('vai-alla-scheda-E1')).toHaveAttribute(
            'title', expect.stringContaining(lungo));
    });

    it('mostra l’avviso se le righe sono state troncate', () => {
        montaCon([t()], { avviso: <p data-testid="avviso">righe troncate</p> });
        expect(screen.getByTestId('avviso')).toBeInTheDocument();
    });
});
