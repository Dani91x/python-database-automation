// ============================================================================
// 07/10 - AVVISO DI COERENZA DELLA BARRA (componente). Con i dati VERI di ogni
// registrazione del repository (scoperte da sole): barra coerente = NESSUN avviso;
// barra con un difetto = avviso con i motivi. Il componente non rompe mai la pagina.
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import type { ReplayData } from '@/lib/live';
import { buildSnapshots } from '@/lib/opportunities/snapshot';
import { creaRilievo, esitoDaRilievi } from '@/lib/replayVerificaBarra';
import { AvvisoCoerenzaBarra } from './AvvisoCoerenzaBarra';
import { caricaPartita, conFonteInRitardo, eventiConFixture } from '@/lib/__fixtures__/replayBarraTutte';

const EVENTI = eventiConFixture();

// difetto nei DATI: `conFonteInRitardo` (fixture comune): dopo il primo gol che resta una seconda fonte rimette 0-0

describe.each(EVENTI)('AvvisoCoerenzaBarra - partita vera %s', (ev) => {
    it('barra coerente: non compare nulla', () => {
        const { replay, estremi } = caricaPartita(ev);
        const { container } = render(<AvvisoCoerenzaBarra replay={replay} estremi={estremi} />);
        expect(container).toBeEmptyDOMElement();
        expect(screen.queryByTestId('avviso-coerenza-barra')).toBeNull();
    });

    it('barra con un difetto: compare l\'avviso con il codice, l\'istante e la spiegazione', () => {
        const { replay, estremi } = caricaPartita(ev);
        render(<AvvisoCoerenzaBarra replay={conFonteInRitardo(replay)} estremi={estremi} />);
        const a = screen.getByTestId('avviso-coerenza-barra');
        expect(a).toHaveTextContent('Controllo coerenza della barra: 1 segnalazione');
        const voci = within(a).getAllByTestId('avviso-coerenza-voce');
        expect(voci).toHaveLength(1);
        expect(voci[0]).toHaveTextContent('TABELLONE_SCENDE');
        expect(voci[0]).toHaveTextContent(/UTC/);
        expect(voci[0]).toHaveTextContent('va avanti e indietro');
    });

    it('usa gli snapshot passati dalla pagina (non li rifa): un motore con il punteggio sbagliato compare come MOTORE_PUNTEGGIO', () => {
        const { replay, estremi } = caricaPartita(ev);
        const sbagliati = buildSnapshots(replay, 10_000).map(s => ({ ...s, scoreHome: 9, scoreAway: 9 }));
        render(<AvvisoCoerenzaBarra replay={replay} estremi={estremi} snapshots={sbagliati} />);
        expect(within(screen.getByTestId('avviso-coerenza-barra')).getAllByTestId('avviso-coerenza-voce')[0]).toHaveTextContent('MOTORE_PUNTEGGIO');
    });
});

describe('AvvisoCoerenzaBarra - casi limite', () => {
    const { replay } = caricaPartita(EVENTI[0]);

    it('nessuna partita aperta o partita senza frame: niente avviso e nessun errore', () => {
        expect(render(<AvvisoCoerenzaBarra replay={null} />).container).toBeEmptyDOMElement();
        expect(render(<AvvisoCoerenzaBarra replay={{ ...replay, frames: [] }} />).container).toBeEmptyDOMElement();
    });

    it('i dati malformati non rompono la pagina: nessun avviso, un warning in console', () => {
        const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
        // un frame nullo fa lanciare un errore al verificatore (il controllo non deve mai rompere la pagina)
        const rotto = { ...replay, frames: [null, ...replay.frames] } as unknown as ReplayData;
        const { container } = render(<AvvisoCoerenzaBarra replay={rotto} />);
        expect(container).toBeEmptyDOMElement();
        expect(warn).toHaveBeenCalled();
        warn.mockRestore();
    });

    it('elenca al massimo `massimo` segnalazioni e dice quante altre ce ne sono (singolare e plurale)', () => {
        const { estremi } = caricaPartita(EVENTI[0]);
        const sbagliati = buildSnapshots(replay, 10_000).map(s => ({ ...s, scoreHome: 9, scoreAway: 9 }));
        const doppio = conFonteInRitardo(replay);          // 2 incoerenze: tabellone che scende + motore sbagliato
        const uno = render(<AvvisoCoerenzaBarra replay={doppio} estremi={estremi} snapshots={sbagliati} massimo={1} />);
        expect(within(uno.container).getAllByTestId('avviso-coerenza-voce')).toHaveLength(1);
        expect(within(uno.container).getByTestId('avviso-coerenza-altre')).toHaveTextContent('e altre 1 segnalazione.');
        expect(uno.container).toHaveTextContent('2 segnalazioni');
        uno.unmount();
        const tutte = render(<AvvisoCoerenzaBarra replay={doppio} estremi={estremi} snapshots={sbagliati} />);
        expect(within(tutte.container).getAllByTestId('avviso-coerenza-voce')).toHaveLength(2);
        expect(within(tutte.container).queryByTestId('avviso-coerenza-altre')).toBeNull();
    });

    // 08/10 (cantiere 13): un'incoerenza dei DATI registrati (classe c) resta visibile CON il suo motivo
    it('incoerenza per dati (KickOff del feed 6 minuti prima del primo frame in gioco): avviso con il motivo dei dati', () => {
        const { estremi } = caricaPartita(EVENTI[0]);
        const k = Math.min(...replay.frames.filter(f => f.inplay).map(f => Date.parse(f.ts)));
        const prima = new Date(k - 360_000).toISOString().replace('Z', '+00:00');
        const conKickOff = { ...replay, score_timeline: replay.score_timeline.map(r => (r.event_type === 'KickOff' ? { ...r, ts: prima } : r)) };
        const { container } = render(<AvvisoCoerenzaBarra replay={conKickOff} estremi={estremi} />);
        const voci = within(container).getAllByTestId('avviso-coerenza-voce');
        expect(voci).toHaveLength(1);
        expect(voci[0]).toHaveTextContent('KICKOFF_DISCORDANTE');
        expect(within(voci[0]).getByTestId('avviso-coerenza-per-dati')).toHaveTextContent(/Dato registrato, non errore della pagina: \d+ frame registrati/);
    });

    it('un difetto della pagina NON ha la riga dei dati', () => {
        const { estremi } = caricaPartita(EVENTI[0]);
        const { container } = render(<AvvisoCoerenzaBarra replay={conFonteInRitardo(replay)} estremi={estremi} />);
        expect(within(container).getAllByTestId('avviso-coerenza-voce').length).toBeGreaterThan(0);
        expect(within(container).queryByTestId('avviso-coerenza-per-dati')).toBeNull();
    });
});

describe('AvvisoCoerenzaBarra - verificatore di un altro sport (il tennis riusa il componente)', () => {
    it('con `verifica` propria mostra le incoerenze del tennis, con il suo ambito e il suo testo', () => {
        const { replay } = caricaPartita(EVENTI[0]);
        const verificaTennis = () => esitoDaRilievi(
            [creaRilievo('SIMBOLO_POSIZIONE', 'errore', 'Il break del 3-2 e\' sul game sbagliato.', { ambito: 'tennis', passo: 12 })],
            { passi: 1, frames: 1, simboli: {}, righePunteggio: 0, righeEvento: 0 },
        );
        const { container } = render(<AvvisoCoerenzaBarra replay={replay} verifica={verificaTennis} />);
        expect(within(container).getAllByTestId('avviso-coerenza-voce')[0]).toHaveTextContent('Il break del 3-2');
    });
});
