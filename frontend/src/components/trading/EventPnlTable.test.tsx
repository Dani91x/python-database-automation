// ============================================================================
// EventPnlTable — la tabella delle Operazioni condivisa dai tre bot.
//
// Certifica le due cose per cui esiste (richiesta dell'utente del 13/09):
//   · i TOTALI in testa, sempre visibili, in corpo grande e col segno colorato;
//   · UNA RIGA PER PARTITA, dettaglio chiuso di default e apribile.
// e la regola del colore che l'ha provocata: «le loss sono in nero e in
// piccolo» — una perdita deve essere ROSSA, in GRASSETTO e della stessa
// dimensione di un utile, e un dato che non c'è deve dire «—», mai «0,00 €».
//
// ATTENZIONE ai formati: il formattatore italiano emette il MENO UNICODE
// (U+2212, «−»), non il trattino ASCII. Si usa sempre `MINUS` di lib/format.
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { EventPnlTable, TotaliBar } from './EventPnlTable';
import { groupTradesIntoCicli, totaliOperazioni, groupCicliByEvent, type PnlTradeLike } from '@/lib/eventGroups';
import { MINUS } from '@/lib/format';

let seq = 0;
function t(over: Partial<PnlTradeLike> = {}): PnlTradeLike {
    seq += 1;
    return {
        id: seq, event_id: 'E1', event_name: 'Roma v Lazio',
        side: 'back', mode: 'paper', price: 1.5, size: 10, liability: 10,
        status: 'won', pnl: 0, placed_at: '2026-09-13T10:00:00Z', closes_trade_id: null,
        ...over,
    };
}

function ciclo(over: Partial<PnlTradeLike>, pnlApre: number, pnlChiude: number) {
    const apre = t({ ...over, pnl: pnlApre });
    const chiude = t({
        ...over, side: 'lay', pnl: pnlChiude,
        closes_trade_id: apre.id, placed_at: '2026-09-13T10:05:00Z',
    });
    return [apre, chiude];
}

function monta(righe: PnlTradeLike[], props: Record<string, unknown> = {}) {
    return render(
        <EventPnlTable
            cicli={groupTradesIntoCicli(righe)}
            titolo="Operazioni"
            vuoto="Nessuna operazione."
            {...props}
        />,
    );
}

// ---------------------------------------------------------------- il colore
describe('la regola del colore del P&L', () => {
    it('una PERDITA è rossa, in grassetto, e non è più piccola di un utile', () => {
        monta(ciclo({ event_id: 'P' }, -10, 5));   // netto −5,00
        const netto = screen.getByTestId('netto-P');
        expect(netto.className).toContain('text-red-400');
        expect(netto.className).toContain('font-bold');
        // la dimensione è sulla CELLA, quindi è la stessa di un utile
        expect(netto.className).toContain('text-base');
        expect(netto).toHaveTextContent(`${MINUS}5,00`);
    });

    it('un UTILE è verde e in grassetto, con la stessa dimensione', () => {
        monta(ciclo({ event_id: 'U' }, -10, 15));  // netto +5,00
        const netto = screen.getByTestId('netto-U');
        expect(netto.className).toContain('text-emerald-400');
        expect(netto.className).toContain('font-bold');
        expect(netto.className).toContain('text-base');
    });

    it('utile e perdita hanno ESATTAMENTE le stesse classi di dimensione e peso', () => {
        monta([
            ...ciclo({ event_id: 'U', event_name: 'Utile' }, -10, 15),
            ...ciclo({ event_id: 'P', event_name: 'Perdita' }, -10, 5),
        ]);
        const dim = (el: HTMLElement) => el.className
            .split(/\s+/).filter((c) => c.startsWith('text-base') || c === 'font-bold').sort();
        expect(dim(screen.getByTestId('netto-P'))).toEqual(dim(screen.getByTestId('netto-U')));
    });

    it('un dato ASSENTE non è colorato e non è in grassetto: non c’è niente da urlare', () => {
        monta([t({ status: 'open', pnl: null })]);
        const netto = screen.getByTestId('netto-E1');
        expect(netto.className).toContain('text-slate-400');
        expect(netto.className).not.toContain('font-bold');
    });
});

describe('«—» e mai «0,00 €»', () => {
    it('una partita senza niente di regolato mostra il trattino', () => {
        monta([t({ status: 'open', pnl: null })]);
        const netto = screen.getByTestId('netto-E1');
        expect(netto).toHaveTextContent('—');
        expect(netto).not.toHaveTextContent('0,00');
    });

    it('ma un P&L davvero pari a zero su una riga regolata resta «0,00»', () => {
        monta([t({ status: 'won', pnl: 0 })]);
        expect(screen.getByTestId('netto-E1')).toHaveTextContent('0,00');
    });

    it('una gamba non ancora regolata mostra «—» nel dettaglio', () => {
        const viva = t({ status: 'open', pnl: null });
        monta([viva]);
        fireEvent.click(screen.getByTestId('apri-E1'));
        expect(screen.getByTestId(`gamba-${viva.id}`)).toHaveTextContent('—');
    });

    it('senza operazioni i totali dicono «—», non zero euro', () => {
        monta([]);
        const realizzato = screen.getByTestId('event-pnl-totali-realizzato');
        expect(realizzato).toHaveTextContent('—');
        expect(realizzato).not.toHaveTextContent('0,00');
        expect(screen.getByTestId('event-pnl-totali-investito')).toHaveTextContent('—');
    });
});

// ---------------------------------------------------------------- i totali
describe('i totali delle operazioni, in testa e sempre visibili', () => {
    it('ci sono anche quando la tabella è vuota: non si nascondono mai', () => {
        monta([]);
        expect(screen.getByTestId('event-pnl-totali')).toBeInTheDocument();
        expect(screen.getByTestId('event-pnl-vuoto')).toHaveTextContent('Nessuna operazione.');
    });

    it('contano le POSIZIONI, non le gambe', () => {
        monta([
            ...ciclo({ event_id: 'A' }, -10, 10.13),
            ...ciclo({ event_id: 'B' }, -10, 9),
        ]);
        // 4 righe in tutto, ma 2 posizioni su 2 partite
        expect(screen.getByTestId('event-pnl-totali-operazioni')).toHaveTextContent('2');
        expect(screen.getByTestId('event-pnl-totali-operazioni')).toHaveTextContent('2 partite');
    });

    it('mostrano realizzato, investito e responsabilità con le parole giuste', () => {
        monta([
            ...ciclo({ event_id: 'A' }, -10, 10.13),
            t({ event_id: 'B', status: 'open', pnl: null, size: 7, liability: 21 }),
        ]);
        const barra = screen.getByTestId('event-pnl-totali');
        expect(barra).toHaveTextContent('Operazioni');
        expect(barra).toHaveTextContent('P&L realizzato');
        expect(barra).toHaveTextContent('Se chiudo ora');
        expect(barra).toHaveTextContent('Investito');
        expect(barra).toHaveTextContent('Responsabilità');
        expect(screen.getByTestId('event-pnl-totali-realizzato')).toHaveTextContent('+0,13');
        expect(screen.getByTestId('event-pnl-totali-investito')).toHaveTextContent('17,00');
        expect(screen.getByTestId('event-pnl-totali-liability')).toHaveTextContent('21,00');
    });

    it('il realizzato negativo è rosso e in grassetto anche nei totali', () => {
        monta(ciclo({ event_id: 'P' }, -10, 5));
        const cella = screen.getByTestId('event-pnl-totali-realizzato')
            .querySelector('.font-display') as HTMLElement;
        expect(cella.className).toContain('text-red-400');
        expect(cella.className).toContain('font-bold');
    });

    it('«se chiudo ora» senza stima dice «—»: non finge uno zero', () => {
        monta([t({ status: 'open', pnl: null })]);
        expect(screen.getByTestId('event-pnl-totali-aperto')).toHaveTextContent('—');
    });

    it('«se chiudo ora» mostra la stima quando il chiamante la passa', () => {
        monta([t({ status: 'open', pnl: null })], { apertoOra: -3.5 });
        const aperto = screen.getByTestId('event-pnl-totali-aperto');
        expect(aperto).toHaveTextContent(`${MINUS}3,50`);
        expect((aperto.querySelector('.font-display') as HTMLElement).className).toContain('text-red-400');
    });
});

describe('paper e live non si sommano', () => {
    const misto = [
        ...ciclo({ event_id: 'A', event_name: 'Alfa', mode: 'paper' }, -10, 12),  // +2 simulati
        ...ciclo({ event_id: 'B', event_name: 'Beta', mode: 'live' }, -10, 5),    // −5 veri
    ];

    it('i totali valgono per la modalità dichiarata e lo scrivono in etichetta', () => {
        monta(misto, { modalita: 'paper' });
        const barra = screen.getByTestId('event-pnl-totali');
        expect(barra).toHaveTextContent('P&L realizzato · PAPER');
        expect(screen.getByTestId('event-pnl-totali-realizzato')).toHaveTextContent('+2,00');
        // i −5,00 della riga LIVE NON sono nel totale
        expect(screen.getByTestId('event-pnl-totali-realizzato')).not.toHaveTextContent(`${MINUS}3,00`);
    });

    it('la stessa vista in LIVE dà l’altro totale', () => {
        monta(misto, { modalita: 'live' });
        expect(screen.getByTestId('event-pnl-totali-realizzato')).toHaveTextContent(`${MINUS}5,00`);
    });

    it('le righe dell’altra modalità restano in tabella e il conto lo dichiara', () => {
        monta(misto, { modalita: 'paper' });
        // nessuna posizione sparisce: sono soldi o rischi veri
        expect(screen.getByTestId('partita-A')).toBeInTheDocument();
        expect(screen.getByTestId('partita-B')).toBeInTheDocument();
        expect(screen.getByTestId('event-pnl-fuori-modalita'))
            .toHaveTextContent(/1 operazione in un.altra modalità/);
    });

    it('senza modalità dichiarata non filtra e non promette niente', () => {
        monta(misto);
        expect(screen.getByTestId('event-pnl-totali-realizzato')).toHaveTextContent(`${MINUS}3,00`);
        expect(screen.queryByTestId('event-pnl-fuori-modalita')).toBeNull();
        expect(screen.getByTestId('event-pnl-totali')).not.toHaveTextContent('· PAPER');
    });
});

// ------------------------------------------------------------ una riga/partita
describe('una riga per PARTITA', () => {
    it('i cicli della stessa partita stanno in UNA riga col netto della partita', () => {
        monta([
            ...ciclo({}, -10, 10.13),
            ...ciclo({}, -10, 10.20),
        ]);
        expect(screen.getAllByTestId(/^partita-/)).toHaveLength(1);
        expect(screen.getByTestId('netto-E1')).toHaveTextContent('+0,33');
    });

    it('i P&L delle singole gambe non si vedono finché non apro', () => {
        monta(ciclo({}, -10, 10.13));
        expect(screen.queryByText(/10,13/)).toBeNull();
    });

    it('mostra investito e responsabilità della partita', () => {
        monta([t({ status: 'open', pnl: null, size: 12, liability: 36 })]);
        const riga = screen.getByTestId('partita-E1');
        expect(riga).toHaveTextContent('12,00');
        expect(screen.getByTestId('liability-E1')).toHaveTextContent('36,00');
    });

    it('dichiara «ancora aperta» e marca il netto come parziale', () => {
        monta([t({ status: 'lost', pnl: -10 }), t({ status: 'open', pnl: null })]);
        expect(screen.getByTestId('partita-E1')).toHaveTextContent('ancora aperta');
        expect(screen.getByTestId('netto-E1')).toHaveTextContent('parz.');
    });

    it('una partita chiusa lo dice e il netto non è parziale', () => {
        monta(ciclo({}, -10, 10.13));
        expect(screen.getByTestId('partita-E1')).toHaveTextContent('chiusa');
        expect(screen.getByTestId('netto-E1')).not.toHaveTextContent('parz.');
    });

    it('marca «soldi veri» il live e grida sulla modalità mista', () => {
        monta([t({ event_id: 'L', event_name: 'Live', mode: 'live' })]);
        expect(screen.getByTestId('partita-L')).toHaveTextContent('soldi veri');
    });

    it('grida se una partita mescola paper e soldi veri', () => {
        monta([t({ mode: 'paper' }), t({ mode: 'live' })]);
        expect(screen.getByTestId('partita-E1')).toHaveTextContent('modalità mista');
    });
});

// ---------------------------------------------------------------- dettaglio
describe('il dettaglio si apre solo se lo chiedo', () => {
    it('parte CHIUSO', () => {
        monta(ciclo({}, -10, 10.13));
        expect(screen.queryByTestId('dettaglio-E1')).toBeNull();
        expect(screen.getByTestId('apri-E1')).toHaveAttribute('aria-expanded', 'false');
    });

    it('un clic lo apre con posizioni e ordini, un altro lo richiude', () => {
        const righe = ciclo({}, -10, 10.13);
        monta(righe);
        fireEvent.click(screen.getByTestId('apri-E1'));
        expect(screen.getByTestId('apri-E1')).toHaveAttribute('aria-expanded', 'true');
        const d = screen.getByTestId('dettaglio-E1');
        expect(within(d).getByTestId(`ciclo-${righe[0].id}`)).toBeInTheDocument();
        expect(within(d).getByTestId(`gamba-${righe[0].id}`)).toBeInTheDocument();
        expect(within(d).getByTestId(`gamba-${righe[1].id}`)).toBeInTheDocument();
        fireEvent.click(screen.getByTestId('apri-E1'));
        expect(screen.queryByTestId('dettaglio-E1')).toBeNull();
    });

    it('apre una partita sola per volta', () => {
        monta([
            ...ciclo({ event_id: 'A', event_name: 'Alfa' }, -10, 10.1),
            ...ciclo({ event_id: 'B', event_name: 'Beta' }, -10, 10.2),
        ]);
        fireEvent.click(screen.getByTestId('apri-A'));
        expect(screen.getByTestId('dettaglio-A')).toBeInTheDocument();
        expect(screen.queryByTestId('dettaglio-B')).toBeNull();
    });

    it('il bottone dice cosa fa e su quale partita', () => {
        monta([t()]);
        const b = screen.getByTestId('apri-E1');
        expect(b).toHaveAttribute('aria-label', expect.stringContaining('Roma v Lazio'));
        fireEvent.click(b);
        expect(screen.getByTestId('apri-E1')).toHaveAttribute('aria-label', expect.stringContaining('Chiudi'));
    });

    it('il chiamante può montare il PROPRIO dettaglio (Safe: la tabella ricca)', () => {
        monta(ciclo({}, -10, 10.13), {
            renderDettaglio: (e: { event_id: string; cicli: unknown[] }) => (
                <div data-testid="mio-dettaglio">tabella di {e.event_id} · {e.cicli.length}</div>
            ),
        });
        fireEvent.click(screen.getByTestId('apri-E1'));
        expect(screen.getByTestId('mio-dettaglio')).toHaveTextContent('tabella di E1 · 1');
        // i livelli di serie non vengono montati
        expect(screen.queryAllByTestId(/^ciclo-/)).toHaveLength(0);
    });

    it('il nome della partita porta alla scheda senza aprire il dettaglio', () => {
        const vai = vi.fn();
        monta([t()], { onApriScheda: vai });
        fireEvent.click(screen.getByTestId('vai-alla-scheda-E1'));
        expect(vai).toHaveBeenCalledWith('E1');
        expect(screen.queryByTestId('dettaglio-E1')).toBeNull();
    });
});

// ------------------------------------------------------------------ robustezza
describe('non mostra mai numeri rotti', () => {
    it('size e prezzo non numerici non producono NaN', () => {
        monta([t({ size: 'tanto' as unknown as number, price: undefined })]);
        fireEvent.click(screen.getByTestId('apri-E1'));
        const testo = screen.getByTestId('dettaglio-E1').textContent ?? '';
        expect(testo).not.toMatch(/NaN|Infinity|undefined/);
    });

    it('un filtro di fase mostra solo i cicli che passano', () => {
        monta([
            ...ciclo({ event_id: 'A', event_name: 'Alfa' }, -10, 10.1),
            ...ciclo({ event_id: 'B', event_name: 'Beta' }, -10, 9),
        ], { filtro: (c: { open: PnlTradeLike }) => c.open.event_id === 'A' });
        expect(screen.getByTestId('partita-A')).toBeInTheDocument();
        expect(screen.queryByTestId('partita-B')).toBeNull();
    });
});

// --------------------------------------------------------------- barra sola
describe('la barra dei totali usata da sola (Omega)', () => {
    it('scrive la modalità accanto a ogni etichetta', () => {
        const tot = totaliOperazioni(groupCicliByEvent(groupTradesIntoCicli(ciclo({}, -10, 5))));
        render(<TotaliBar tot={tot} modalita="live" testId="omega-tot" />);
        const barra = screen.getByTestId('omega-tot');
        expect(barra).toHaveTextContent('P&L realizzato · LIVE');
        expect(barra).toHaveTextContent('Responsabilità · LIVE');
        expect(screen.getByTestId('omega-tot-realizzato')).toHaveTextContent(`${MINUS}5,00`);
    });
});
