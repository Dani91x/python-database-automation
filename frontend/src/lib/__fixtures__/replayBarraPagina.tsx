// ============================================================================
// Pilota di test per la pagina VERA Match Replay (07/10): la monta con un replay
// finto-vero (i dati arrivano da `fetchReplayChunked`, mockato dal test), sceglie
// la partita, muove la barra come farebbe l'utente (evento change dello slider) e
// LEGGE dal DOM cio' che l'utente vede: knob, simboli, linea del calcio d'inizio,
// segmenti di sospensione, punteggio, minuto, pannello Match Odds.
// I `data-*` letti li espone `components/replay/TimelineSlider.tsx`.
// ============================================================================
import type { ReactElement } from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';

// % orizzontale DISEGNATA (stile `left`): e' cio' che vede l'utente
const sx = (e: Element | null, k: 'left' | 'width' = 'left'): number => Number.parseFloat((e as HTMLElement | null)?.style[k] ?? 'NaN');

export interface SimboloVisto { kind: string; team: string; left: number; title: string }
export interface RigaMatchOddsVista { nome: string; back: string; lay: string }
export interface VistaBarra {
    indice: number;                 // valore dello slider
    knobLeft: number;               // % del cursore
    knobTesto: string;              // PRE / minuto / —
    punteggio: string;              // "h - a"
    testoMinuto: string;            // PRE-MATCH / 30' / 98' · FT
    simboli: SimboloVisto[];        // simboli visibili AL CURSORE (ts <= istante)
    kickoffLeft: number | null;     // % della lineetta del calcio d'inizio
    matchOddsSospeso: boolean;      // badge "Sospeso" nel pannello del Match Odds
    matchOddsChiuso: boolean;
    matchOdds: RigaMatchOddsVista[];
}
export interface PilotaPagina {
    max: number;
    iniziale: number;               // indice a cui la pagina apre il cursore
    sospesi: Set<number>;           // indici dei segmenti di sospensione disegnati
    segmenti: { indice: number; left: number; width: number }[]; // la loro geometria (% della barra)
    vai: (i: number) => Promise<void>;
    leggi: () => VistaBarra;
}

export async function apriReplay(pagina: ReactElement, nomeCasa: string): Promise<PilotaPagina> {
    const { container } = render(
        <HelmetProvider><MemoryRouter>{pagina}</MemoryRouter></HelmetProvider>,
    );
    fireEvent.click(await screen.findByText(nomeCasa, {}, { timeout: 10_000 }));
    const slider = await screen.findByLabelText('Timeline replay', {}, { timeout: 30_000 }) as HTMLInputElement;
    const max = Number(slider.max);
    // lascia girare gli effetti del caricamento (la pagina riposiziona il cursore
    // sul calcio d'inizio DOPO aver reso la barra)
    await act(async () => { await new Promise(r => setTimeout(r, 50)); });

    const leggi = (): VistaBarra => {
        const knob = screen.getByTestId('barra-knob');
        const punti = container.querySelector('span.font-display.font-black.text-2xl');
        const scheda = punti?.closest('.glass-card');
        const minuto = scheda?.querySelector('div.text-center.text-xs');
        const ko = screen.queryByTestId('barra-kickoff');
        let mo: Element | null = null;
        for (const t of Array.from(container.querySelectorAll('table'))) {
            const titolo = t.closest('.glass-card')?.querySelector('span.font-heading')?.textContent ?? '';
            if (titolo.startsWith('MATCH_ODDS')) { mo = t.closest('.glass-card'); break; }
        }
        const titoloMo = mo?.querySelector('span.font-heading')?.textContent ?? '';
        return {
            indice: Number(slider.value),
            knobLeft: sx(knob),
            knobTesto: knob.textContent ?? '',
            punteggio: punti?.textContent ?? '',
            testoMinuto: minuto?.textContent ?? '',
            simboli: screen.queryAllByTestId('barra-simbolo').map(e => ({
                kind: e.getAttribute('data-kind') ?? '',
                team: e.getAttribute('data-team') ?? '',
                left: sx(e),
                title: e.getAttribute('title') ?? '',
            })),
            kickoffLeft: ko ? sx(ko) : null,
            matchOddsSospeso: titoloMo.includes('Sospeso'),
            matchOddsChiuso: titoloMo.includes('Chiuso'),
            matchOdds: Array.from(mo?.querySelectorAll('tbody tr') ?? []).map(tr => {
                const td = Array.from(tr.querySelectorAll('td'));
                return { nome: td[0]?.textContent ?? '', back: td[2]?.textContent ?? '', lay: td[3]?.textContent ?? '' };
            }),
        };
    };

    const vai = async (i: number): Promise<void> => {
        if (Number(slider.value) === i) return;
        await act(async () => { fireEvent.change(slider, { target: { value: String(i) } }); });
        if (Number(slider.value) !== i) {
            // il primo change dopo il caricamento puo' essere assorbito dal
            // riposizionamento iniziale sul calcio d'inizio: si ripete
            await act(async () => { fireEvent.change(slider, { target: { value: String(i === 0 ? 1 : 0) } }); });
            await act(async () => { fireEvent.change(slider, { target: { value: String(i) } }); });
        }
    };

    const segmenti = screen.queryAllByTestId('barra-sospensione').map(e => ({
        indice: Number(e.getAttribute('data-indice')),
        left: sx(e),
        width: sx(e, 'width'),
    }));
    const sospesi = new Set(segmenti.map(x => x.indice));
    return { max, iniziale: Number(slider.value), sospesi, segmenti, vai, leggi };
}
