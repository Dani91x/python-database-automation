// 30/09 - «il feedback visivo del pulsante Salva non funziona» (utente).
// Il pannello di Mike DICE l'esito del salvataggio (ora o errore testuale),
// il pulsante scrive «Salvataggio…» mentre aspetta, e il pallino delle
// modifiche non salvate si spegne quando il servizio ha i valori salvati
// (anche se il servizio li normalizza: il filtro competizioni arriva TRIMMATO,
// `mergeMikeParams`). Il pannello condiviso SENZA l'opzione resta identico.
import { useState } from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MikeParamsSheet } from './MikeParamsSheet';
import { ParamsSheetBase } from '@/components/trading/ParamsSheetBase';
import { MIKE_PARAM_DEFAULTS, mergeMikeParams, type MikeParams } from '@/lib/mike';

/** La pagina vera: `onSave` scrive e poi RILEGGE dal servizio (useMike.wrap). */
function Pagina({ fallisce }: { fallisce?: string }) {
    const [params, setParams] = useState<MikeParams>({ ...MIKE_PARAM_DEFAULTS });
    const onSave = async (p: MikeParams) => {
        await Promise.resolve();
        if (fallisce) throw new Error(fallisce);
        // il servizio restituisce i parametri normalizzati (mergeMikeParams)
        setParams(mergeMikeParams(p));
        // la rilettura arriva a schermo PRIMA che il salvataggio finisca (poll
        // o realtime durante la RPC): un render con la bozza ancora "toccata"
        await new Promise((r) => setTimeout(r, 0));
    };
    return <MikeParamsSheet params={params} busy={false} onSave={onSave} />;
}

async function apri(ui: React.ReactElement, trigger = 'mike-params-trigger') {
    const user = userEvent.setup();
    render(ui);
    await user.click(screen.getByTestId(trigger));
    await screen.findByTestId('params-sheet');
    return user;
}

describe('pannello parametri di Mike: riscontro del salvataggio', () => {
    it('salvataggio riuscito: «Parametri salvati alle HH:MM:SS» e pallino spento', async () => {
        const user = await apri(<Pagina />);
        const filtro = screen.getByLabelText('Filtro competizioni');
        await user.type(filtro, ' serie a ');
        expect(screen.getByTestId('params-dirty')).toBeInTheDocument();
        await user.click(screen.getByTestId('params-save'));
        const esito = await screen.findByTestId('params-esito');
        expect(esito.getAttribute('data-esito')).toBe('ok');
        expect(esito.textContent).toMatch(/^Parametri salvati alle \d{2}:\d{2}:\d{2}$/);
        // il servizio ha il valore trimmato: la bozza si riallinea, niente pallino
        await waitFor(() => expect(screen.queryByTestId('params-dirty')).toBeNull());
        expect(screen.getByLabelText('Filtro competizioni')).toHaveValue('serie a');
    });

    it('M1 (review incrociata 30/09): rilettura NON aspettata: la bozza resta sui valori SALVATI, mai i vecchi', async () => {
        // Control Room: `onSave` risolve senza cambiare `params` (la rilettura
        // arriva dopo, o non arriva). La bozza deve restare 12, non tornare 5.
        const salvati = vi.fn(async () => { await Promise.resolve(); });
        const pagina = (stake: number) => (
            <MikeParamsSheet params={{ ...MIKE_PARAM_DEFAULTS, stake }} busy={false} onSave={salvati} />
        );
        const user = userEvent.setup();
        const { rerender } = render(pagina(5));
        await user.click(screen.getByTestId('mike-params-trigger'));
        await screen.findByTestId('params-sheet');
        const stake = screen.getByLabelText('Stake Under 3.5 (€)');
        await user.clear(stake);
        await user.type(stake, '12');
        await user.click(screen.getByTestId('params-save'));
        const esito = await screen.findByTestId('params-esito');
        expect(esito.getAttribute('data-esito')).toBe('ok');
        // la bozza NON e' tornata a 5; il pallino dice onestamente che il
        // servizio non ha ancora ripubblicato
        expect(screen.getByLabelText('Stake Under 3.5 (€)')).toHaveValue(12);
        expect(screen.getByTestId('params-dirty')).toBeInTheDocument();
        // quando il servizio ripubblica, si riallinea e il pallino si spegne
        rerender(pagina(12));
        await waitFor(() => expect(screen.queryByTestId('params-dirty')).toBeNull());
        expect(screen.getByLabelText('Stake Under 3.5 (€)')).toHaveValue(12);
    });

    it('salvataggio fallito: l’errore testuale e le modifiche restano da salvare', async () => {
        const user = await apri(<Pagina fallisce="non autorizzato (owner-only)" />);
        const stake = screen.getByLabelText('Stake Under 3.5 (€)');
        await user.clear(stake);
        await user.type(stake, '12');
        await user.click(screen.getByTestId('params-save'));
        const esito = await screen.findByTestId('params-esito');
        expect(esito.getAttribute('data-esito')).toBe('errore');
        expect(esito.textContent).toBe('Salvataggio NON riuscito: non autorizzato (owner-only)');
        expect(screen.getByTestId('params-dirty')).toBeInTheDocument();
        expect(screen.getByLabelText('Stake Under 3.5 (€)')).toHaveValue(12);
    });

    it('mentre aspetta il pulsante dice «Salvataggio…» ed e’ disabilitato', async () => {
        let libera: () => void = () => {};
        const onSave = vi.fn(() => new Promise<void>((r) => { libera = r; }));
        const user = await apri(<MikeParamsSheet params={{ ...MIKE_PARAM_DEFAULTS }} busy={false} onSave={onSave} />);
        await user.click(screen.getByTestId('params-save'));
        const btn = screen.getByTestId('params-save');
        expect(btn.textContent).toBe('Salvataggio…');
        expect(btn).toBeDisabled();
        libera();
        await screen.findByTestId('params-esito');
        expect(screen.getByTestId('params-save').textContent).toBe('Salva parametri');
    });

    it('pannello condiviso SENZA l’opzione (Safe/Omega/tennis): nessun esito, come prima', async () => {
        const onSave = vi.fn(async () => {});
        const user = await apri(
            <ParamsSheetBase title="t" groups={[{ label: 'g', fields: [{ key: 'x', label: 'X', type: 'number' }] }]}
                values={{ x: 1 }} onSave={onSave} />,
            'params-trigger',
        );
        await user.click(screen.getByTestId('params-save'));
        await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
        expect(screen.queryByTestId('params-esito')).toBeNull();
        expect(screen.getByTestId('params-save').textContent).toBe('Salva parametri');
    });
});
