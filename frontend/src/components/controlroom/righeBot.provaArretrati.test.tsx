// ============================================================================
// righeBot.provaArretrati.test.tsx - P8bis (30/09): nella PLANCIA dei bot la
// cifra «oggi» in prova e' per partite di OGGI; gli arretrati (partite di
// giorni precedenti regolate oggi) stanno accanto, a parte, mai sommati.
// Il caso vero: Safe base in prova, 4 partite del 26/09 regolate oggi al
// riavvio (+7,60): la riga diceva «oggi +7,60», ora «oggi —» e, a parte,
// «arretrati regolati oggi: +7,60 € (4 operazioni aperte il 26/09)».
//
// Finti con le chiavi di `StatoBotPlancia` (come in fixPagine2609.giornata).
// FALSIFICAZIONE: in righeBot togliendo `arretratiProva` dalla riga, o
// rimettendo gli arretrati dentro `pnlOggi`, questi test diventano rossi.
// ============================================================================
import { describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';
import type { ComandiInterruttori } from '@/lib/interruttori';
import { righeInterruttori, type StatoBotPlancia } from './righeBot';
import { PannelloBot } from './PannelloBot';

const ARR = [{ giorno: '2026-09-26', origine: 'apertura' as const, pnl: 7.6, operazioni: 4, vinte: 4, perse: 0, partite: 4 }];

function safe(modo: 'paper' | 'live'): StatoBotPlancia {
    return {
        bot: 'safe', inCorsa: true, modalita: modo, varianti: ['base'],
        modiStrategia: { base: modo }, stato: 'running', etaPushS: 1, motivoBlocco: null,
        tettoPartite: null, partiteEsposte: null, stopFermaSoloAperture: false, fermatoAllAvvioAt: null,
        pnlOggi: null, pnlOggiPaper: null,
        pnlOggiPerStrategia: { base: { live: 0.44, paper: null, arretratiPaper: ARR } },
    };
}

describe('plancia: prova di oggi e arretrati a parte', () => {
    it('Safe base in prova: oggi «—» (niente di oggi), arretrati +7,60 accanto e mai dentro', () => {
        const [r] = righeInterruttori([safe('paper')], 'calcio').filter((x) => x.id === 'safe-base');
        expect(r.pnlOggi).toBeNull();
        expect(r.arretratiProva).toEqual(ARR);
    });

    it('in LIVE la riga mostra il suo live e NESSUN arretrato di prova', () => {
        const [r] = righeInterruttori([safe('live')], 'calcio').filter((x) => x.id === 'safe-base');
        expect(r.pnlOggi).toBe(0.44);
        expect(r.arretratiProva).toBeUndefined();
    });

    it('a schermo: «oggi —» e la riga degli arretrati con la data', () => {
        const righe = righeInterruttori([safe('paper')], 'calcio');
        const comandi: ComandiInterruttori = {
            accendi: vi.fn(async () => {}), spegni: vi.fn(async () => {}),
            cambiaModalita: vi.fn(async () => {}), cambiaImporto: vi.fn(async () => {}),
            fermaBot: vi.fn(async () => {}), scriviAccensioni: vi.fn(async () => {}),
            cambiaModalitaServizio: vi.fn(async () => {}),
        };
        const s = render(<PannelloBot righe={righe} importi={{}} comandi={comandi} />);
        expect(s.getByTestId('cr-bot-pnl-safe-base').textContent).toBe('oggi —');
        expect(s.getByTestId('cr-bot-arretrati-safe-base').textContent)
            .toBe('arretrati regolati oggi: +7,60 € (4 operazioni aperte il 26/09)');
    });
});
