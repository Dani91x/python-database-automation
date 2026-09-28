// ============================================================================
// RigaCapacitaMercati.test.tsx - 28/09 (cantiere B): la riga MERCATI della
// Control Room.
//
// Che cosa si prova (sulla fixture generata dallo stato VERO di
// `auto_follow.AutoFollow.stato()`, lib/__fixtures__/autoFollowFinti.json,
// chiavi verificate dal test Python test_fixture_ui_ha_le_chiavi_vere):
//   * capacita' esaurita: il numero delle partite FUORI, i loro nomi e il
//     motivo sono a video (mai silenzio);
//   * tutte seguite: "nessuna partita fuori", partite/mercati/connessioni;
//   * canale spento o runner di prima del 28/09: "non noto", niente numeri
//     inventati.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, act } from '@testing-library/react';

type Cb = (d: unknown) => void;
const iscritti = new Map<string, Set<Cb>>();
let stato: 'connected' | 'off' = 'off';
let helloCorrente: Record<string, unknown> | null = null;
function spingi(topic: string, d: unknown): void {
    for (const cb of iscritti.get(topic) ?? []) cb(d);
}

vi.mock('@/lib/localChannel', async (orig) => ({
    ...(await orig() as object),
    getLocalChannel: vi.fn(() => ({
        getStatus: () => stato,
        getHello: () => helloCorrente,
        onStatus: () => () => { /* nessun cambio di stato nei test */ },
        subscribe: (topic: string, cb: Cb) => {
            let s = iscritti.get(topic);
            if (!s) { s = new Set(); iscritti.set(topic, s); }
            s.add(cb);
            return () => { s.delete(cb); };
        },
        request: async () => ({ ok: true }),
    })),
}));

import { RigaCapacitaMercati } from './RigaCapacitaMercati';
import { leggiCapacitaMercati } from '@/lib/capacitaMercati';
import finti from '@/lib/__fixtures__/autoFollowFinti.json';

beforeEach(() => {
    iscritti.clear();
    stato = 'off';
    helloCorrente = null;
});

describe('leggiCapacitaMercati', () => {
    it('legge lo stato vero con le partite fuori', () => {
        const c = leggiCapacitaMercati(finti.capacita_esaurita);
        expect(c).not.toBeNull();
        expect(c!.fuoriN).toBe(finti.capacita_esaurita.partite_fuori_n);
        expect(c!.fuoriN).toBeGreaterThan(0);
        expect(c!.fuori[0].eventId).toBe(finti.capacita_esaurita.partite_fuori[0].event_id);
        expect(c!.fuori[0].nome).toBe(finti.capacita_esaurita.partite_fuori[0].nome);
        expect(c!.fuori[0].motivo).toContain("capacita' esaurita");
        expect(c!.fuori[0].dalMs).toBe(Math.round(finti.capacita_esaurita.partite_fuori[0].dal * 1000));
        expect(c!.tetto).toBe(180);
        expect(c!.motivoLimite).toContain('RUNNER_CALCIO_STREAM_CONNS');
    });

    it('tutte seguite: zero fuori, piu\' connessioni', () => {
        const c = leggiCapacitaMercati(finti.tutte_seguite)!;
        expect(c.fuoriN).toBe(0);
        expect(c.partiteSeguite).toBe(67);
        expect(c.partiteFeed).toBe(67);
        expect(c.connessioni).toBe(2);
        expect(c.tetto).toBe(540);
    });

    it('messaggio storto o runner di prima del 28/09: null', () => {
        expect(leggiCapacitaMercati(null)).toBeNull();
        expect(leggiCapacitaMercati([])).toBeNull();
        const vecchio: Record<string, unknown> = { ...finti.tutte_seguite };
        delete vecchio.partite_fuori_n;
        expect(leggiCapacitaMercati(vecchio)).toBeNull();
    });
});

describe('RigaCapacitaMercati', () => {
    it('canale spento: non noto', () => {
        const s = render(<RigaCapacitaMercati />);
        expect(s.getByTestId('cr-capacita-ignota')).toBeTruthy();
        expect(s.queryByTestId('cr-capacita-fuori')).toBeNull();
    });

    it('partite fuori: numero, nomi e motivo a video', () => {
        stato = 'connected';
        helloCorrente = { sport: 'calcio', auto_follow: finti.tutte_seguite };
        const s = render(<RigaCapacitaMercati />);
        expect(s.getByTestId('cr-capacita-fuori').textContent).toBe('nessuna partita fuori');
        expect(s.getByTestId('cr-capacita-numeri').textContent).toContain('540');
        act(() => spingi('auto_follow', finti.capacita_esaurita));
        expect(s.getByTestId('cr-capacita-fuori').textContent)
            .toBe(`${finti.capacita_esaurita.partite_fuori_n} partite FUORI`);
        const righe = s.getAllByTestId('cr-capacita-partita');
        expect(righe).toHaveLength(finti.capacita_esaurita.partite_fuori.length);
        expect(righe[0].textContent).toContain(finti.capacita_esaurita.partite_fuori[0].nome);
        expect(righe[0].textContent).toContain("capacita' esaurita");
        expect(s.getByTestId('cr-capacita-motivo').textContent).toContain('RUNNER_CALCIO_STREAM_CONNS');
        expect(s.getByTestId('cr-capacita-criterio')).toBeTruthy();
    });
});
