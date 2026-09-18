// ============================================================================
// RigaOperazioneNomeTennis.test.tsx — TASK A2 (18/09, raccordo): il nome
// della selezione tennis, risolto dal chiamante e passato già pronto.
//
// FALSIFICAZIONE (verificata a mano): sostituire `o.selezione ?? nomeSelezioneRisolto`
// con `o.selezione` da solo fa restare "—" anche col nome risolto — rosso.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RigaOperazione } from './DettaglioRigaView';
import type { RigaOrdine } from '@/lib/statoOrdine';
import type { OperazionePartita } from './useControlRoom';

function ordine(): RigaOrdine {
    return {
        status: 'open', side: 'back', price: 2.0, size: 10,
        size_requested: 10, size_matched: 10, size_remaining: 0,
        avg_price_matched: 2.0, betfair_updated_at: '2026-09-18T10:00:00.000Z',
        meta: null,
    };
}

function rigaTennis(over: Partial<OperazionePartita> = {}): OperazionePartita {
    return {
        bot: 'tennis_scalper', id: 1, selezione: null, lato: 'back', prezzo: 2.0,
        size: 10, stato: 'open', pnl: null, modalita: 'live',
        at: '2026-09-18T10:00:00.000Z', quale: null,
        ordine: ordine(),
        dettaglio: null, marketId: 'm1', selectionId: 123, liability: null,
        vivo: null, etaQuoteS: null, chiusura: null, chiusureOrdini: [],
        ...over,
    };
}

describe('RigaOperazione: nome della selezione tennis risolto dal chiamante', () => {
    it('bot tennis senza o.selezione ma con nome risolto lo mostra', () => {
        render(<RigaOperazione o={rigaTennis()} nomeSelezioneRisolto="Sinner J." />);
        expect(screen.getByText('Sinner J.')).toBeInTheDocument();
    });

    it('bot tennis senza nome risolvibile resta "—" col motivo nel title', () => {
        render(<RigaOperazione o={rigaTennis()} nomeSelezioneRisolto={null} />);
        // la riga porta PIÙ trattini (selezione E pnl non regolato): si isola
        // per title, non per testo, altrimenti la query e' ambigua.
        const cella = screen.getByTitle(/feed tennis vivo/);
        expect(cella).toHaveTextContent('—');
    });

    it('bot non tennis: comportamento INVARIATO senza il prop nuovo', () => {
        render(<RigaOperazione o={rigaTennis({ bot: 'safe', selezione: 'Juventus' })} />);
        expect(screen.getByText('Juventus')).toBeInTheDocument();
    });
});
