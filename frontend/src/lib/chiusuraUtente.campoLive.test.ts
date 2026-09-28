// ============================================================================
// chiusuraUtente.campoLive.test.ts — CANTIERE G, voce 6, U0240 («chiusa da te»).
//
// Campo che esiste SOLO su righe mode='live' (in paper l'utente non chiude mai
// "fuori app" su Betfair vero): letto da `DettaglioRigaView.tsx:246` via
// `statoChiusuraEvento`/`marcatoreRiga` (questo file).
//
// Il finto: RIGA VERA letta in SOLA LETTURA dal progetto Supabase
// dqbwaocvlzbxfrpacsac, tabella `safe_strategy_trades`, `id=335`
// (`mode='live'`, `meta ? 'chiuso_dall_utente'`), 28/09/2026 — stesse chiavi e
// tipi dell'oggetto vero (verificato via query SQL diretta, nessuna scrittura).
// ============================================================================
import { describe, it, expect } from 'vitest';
import { marcatoreRiga, statoChiusuraEvento, type RigaConMeta } from './chiusuraUtente';

// riga vera, id=335, safe_strategy_trades, mode='live' (letta il 28/09/2026)
const RIGA_VERA_335: RigaConMeta = {
    event_id: '36093424',
    meta: {
        chiuso_dall_utente: {
            come: 'fuori_app',
            altrui: -3.15,
            atteso: 3,
            quando: '2026-09-22T13:38:44.626973+00:00',
            event_id: '36093424',
            trade_id: 335,
            market_id: '1.262660508',
            selection_id: 11422707,
            netto_di_conto: -0.15,
        },
    },
};

describe('U0240 — "chiusa da te" su una riga LIVE vera (id=335)', () => {
    it('marcatoreRiga legge come/quando dalla riga reale', () => {
        const m = marcatoreRiga(RIGA_VERA_335);
        expect(m).not.toBeNull();
        expect(m?.come).toBe('fuori_app');
        expect(m?.quando).toBe('2026-09-22T13:38:44.626973+00:00');
        // il dettaglio porta il resto, IDENTICO all'oggetto vero (nessun campo perso)
        expect(m?.dettaglio.netto_di_conto).toBe(-0.15);
        expect(m?.dettaglio.market_id).toBe('1.262660508');
    });

    it('statoChiusuraEvento (fonte "righe", Safe non pubblica un elenco di servizio) risulta chiusa', () => {
        const s = statoChiusuraEvento({ eventId: '36093424', righe: [RIGA_VERA_335], eventiDalServizio: null });
        expect(s.chiusa).toBe(true);
        expect(s.fonte).toBe('righe');
        expect(s.marcatore?.come).toBe('fuori_app');
    });

    it('un evento DIVERSO (nessuna riga corrispondente) non risulta chiuso: nessun contagio fra partite', () => {
        const s = statoChiusuraEvento({ eventId: '99999999', righe: [RIGA_VERA_335], eventiDalServizio: null });
        expect(s.chiusa).toBe(false);
        expect(s.fonte).toBeNull();
    });
});
