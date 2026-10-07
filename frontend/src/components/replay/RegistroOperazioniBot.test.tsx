// 07/10 sera — il registro delle operazioni del bot (componente condiviso da
// Match Replay e Replay Tennis) su ESITI VERI del banco: una riga per ordine con
// gli eventi sotto, i clic col loro esito, il clic sull'evento che porta la
// timeline all'istante ESATTO, il filtro per mercato.
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

vi.mock('@/integrations/supabase/client', () => ({ supabase: { rpc: vi.fn() } }));

import { RegistroOperazioniBot } from './RegistroOperazioniBot';
import { EsitoBotPanel } from './EsitoBotPanel';
import { analizzaEsito } from '@/lib/useOperativitaBot';
import type { EsitoBot } from '@/lib/replayBot';
import multi from '@/lib/__fixtures__/replay_pro/esito_media_clic_multi_69.json';
import tennis from '@/lib/__fixtures__/replay_pro/esito_tennis_scalper.json';
import scalper from '@/lib/__fixtures__/replay_pro/esito_scalper_base_69.json';

const MULTI = multi as unknown as EsitoBot;
const TENNIS = tennis as unknown as EsitoBot;
const SCALPER = scalper as unknown as EsitoBot;

function monta(esito: EsitoBot, nowMs = Number.MAX_SAFE_INTEGER) {
    const onSeek = vi.fn();
    const a = analizzaEsito(esito, ms => `m${ms}`);
    const r = render(<RegistroOperazioniBot esito={esito} analisi={a} nowMs={nowMs} onSeek={onSeek}
        etichettaIstante={ms => `m${ms}`} nomeMercato={m => `M${m}`} nomeSelezione={(_m, s) => `S${s}`} />);
    return { ...r, onSeek, a };
}

describe('RegistroOperazioniBot', () => {
    it('media under: i 4 clic col loro esito, i cicli del bot, una riga per ordine', () => {
        const { a } = monta(MULTI);
        const clic = screen.getAllByTestId('registro-clic-voce');
        expect(clic.map(c => c.getAttribute('data-esito'))).toEqual(['eseguito', 'rifiutato', 'eseguito', 'eseguito']);
        expect(clic[1].textContent).toMatch(/RIFIUTATO: il ciclo 1 è ancora aperto: BANCA 11,52 @ 2,20/);
        expect(screen.getAllByTestId('registro-ciclo')).toHaveLength(3);
        expect(screen.getAllByTestId('registro-ciclo-bot').map(x => x.textContent))
            .toEqual(a.cicli.map(() => expect.stringMatching(/partito da un clic · CHIUSO · lordo/)));
        expect(screen.getAllByTestId('registro-ordine')).toHaveLength(a.ordini.length);
    });

    it('clic su un evento: la timeline va all\'istante ESATTO dell\'evento, sul suo mercato', () => {
        const { onSeek, a } = monta(MULTI);
        const ev = a.eventi.find(e => e.tipo === 'abbinato_totale' && e.lato === 'lay')!;
        const bottone = screen.getAllByTestId('registro-evento').find(b => b.getAttribute('data-ms') === String(ev.ms)
            && b.getAttribute('data-tipo') === 'abbinato_totale')!;
        fireEvent.click(bottone);
        expect(onSeek).toHaveBeenCalledWith({ ms: ev.ms, marketId: ev.marketId, selectionId: ev.selectionId });
    });

    it('il clic RIFIUTATO porta all\'istante del clic; l\'eseguito alla prima riga della prima punta', () => {
        const { onSeek, a } = monta(MULTI);
        const voci = screen.getAllByTestId('registro-clic-voce');
        fireEvent.click(voci[1]);
        expect(onSeek).toHaveBeenLastCalledWith({ ms: MULTI.clic_bot![1].clic_ms, marketId: a.cicli[0].marketId, selectionId: null });
        fireEvent.click(voci[2]);
        expect(onSeek.mock.lastCall![0].ms).toBe(a.perChiave.get(`o:${MULTI.clic_bot![2].prima_punta!.ordine}`)!.primoMs);
    });

    it('tennis (stesso componente): il riprezzo di Betfair e\' una riga di registro', () => {
        monta(TENNIS);
        fireEvent.click(screen.getByRole('radio', { name: 'cronologica' }));
        const righe = within(screen.getByTestId('registro-cronologico')).getAllByTestId('registro-evento');
        expect(righe.some(r => /BANCA SPOSTATA da 1,01 a 1,69 \(riprezzo, 0,79\) \(replace di Betfair\)/.test(r.textContent ?? ''))).toBe(true);
    });

    it('scalper su due mercati: il filtro per mercato tiene solo quel mercato', () => {
        const { a } = monta(SCALPER);
        const mercati = [...new Set(a.ordini.map(o => o.marketId))];
        expect(mercati.length).toBeGreaterThan(1);
        fireEvent.click(screen.getByRole('radio', { name: 'cronologica' }));
        fireEvent.change(screen.getByTestId('registro-filtro-mercato'), { target: { value: mercati[0] } });
        const testi = within(screen.getByTestId('registro-cronologico')).getAllByTestId('registro-evento').map(r => r.textContent ?? '');
        expect(testi.length).toBe(a.eventi.filter(e => e.marketId === mercati[0]).length);
        expect(testi.every(t => !t.includes(`M${mercati[1]}`))).toBe(true);
    });

    it('l\'evento attuale (ultimo <= cursore) e\' evidenziato; i futuri sono attenuati', () => {
        const { a } = monta(MULTI, MULTI.righe[3]._ms);
        fireEvent.click(screen.getByRole('radio', { name: 'cronologica' }));
        const righe = within(screen.getByTestId('registro-cronologico')).getAllByTestId('registro-evento');
        const futuri = righe.filter(r => Number(r.getAttribute('data-ms')) > MULTI.righe[3]._ms);
        expect(futuri.length).toBeGreaterThan(0);
        expect(futuri.every(r => r.className.includes('opacity-50'))).toBe(true);
        expect(righe.filter(r => r.className.includes('ring-amber-400'))).toHaveLength(1);
        void a;
    });
});

describe('EsitoBotPanel con l\'esito vero: P&L confrontato col banco', () => {
    it('i confronti col banco sono tutti «uguale»', () => {
        render(<EsitoBotPanel esito={MULTI} analisi={analizzaEsito(MULTI)} nowMs={Number.MAX_SAFE_INTEGER}
            inviato={{ dal_ms: MULTI.dal_ms!, clic_ms: MULTI.clic_ms! }} onSeek={() => {}}
            nomeMercato={m => m} nomeSelezione={(_m, s) => String(s)} />);
        expect(screen.queryByTestId('avvisi-banco')).toBeNull();
        const conf = screen.getAllByTestId('confronto-banco');
        expect(conf.length).toBeGreaterThanOrEqual(2);
        expect(conf.every(c => c.getAttribute('data-ok') === '1')).toBe(true);
        expect(screen.getByTestId('pnl-regolato-netto').textContent).toBe('+0,47');
        expect(screen.getByTestId('pnl-cicli-netto').textContent).toBe('+0,46');
    });
    it('un clic mandato e NON ricevuto dal banco -> avviso', () => {
        render(<EsitoBotPanel esito={MULTI} analisi={analizzaEsito(MULTI)} nowMs={0}
            inviato={{ dal_ms: MULTI.dal_ms!, clic_ms: [...MULTI.clic_ms!, 1783715000000] }} onSeek={() => {}}
            nomeMercato={m => m} nomeSelezione={(_m, s) => String(s)} />);
        expect(screen.getByTestId('avvisi-banco').textContent).toMatch(/NON ha ricevuto il clic «Attiva adesso»/);
    });
});
