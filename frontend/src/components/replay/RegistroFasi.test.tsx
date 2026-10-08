// 08/10 (cantiere 10) — il registro operazioni e il riquadro P&L del bot divisi
// per FASE, con i cicli DEL BOT. Esiti VERI del banco e cronologie IPS VERE
// delle stesse registrazioni (35797769 calcio, 35790089 tennis); l'esito dei 4
// cicli che si toccano e' costruito da righe e cicli veri
// (`__fixtures__/registroCicliFinti.ts`).
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

vi.mock('@/integrations/supabase/client', () => ({ supabase: { rpc: vi.fn() } }));

import { RegistroOperazioniBot } from './RegistroOperazioniBot';
import { RiepilogoPnlBot } from './RiepilogoPnlBot';
import { EsitoBotPanel } from './EsitoBotPanel';
import { analizzaEsito } from '@/lib/useOperativitaBot';
import type { EsitoBot } from '@/lib/replayBot';
import { confiniCalcio, faseCalcioDaConfini, faseTennisDaEtichetta, type FaseReplay } from '@/lib/replayFasi';
import { FIXTURE_BARRA, replayDaFixture } from '@/lib/__fixtures__/replayBarra';
import { ESITO_4 } from '@/lib/__fixtures__/registroCicliFinti';
import { faseTennis, inizioInGioco, ordinaPunteggio, type TennisReplayData } from '@/lib/tennisReplay';
import tennisFixture from '@/lib/__fixtures__/replay_tennis_35790089.json';
import multi from '@/lib/__fixtures__/replay_pro/esito_media_clic_multi_69.json';
import scalper from '@/lib/__fixtures__/replay_pro/esito_scalper_base_69.json';
import tennis from '@/lib/__fixtures__/replay_pro/esito_tennis_scalper.json';

const MULTI = multi as unknown as EsitoBot;
const SCALPER = scalper as unknown as EsitoBot;
const TENNIS_ESITO = tennis as unknown as EsitoBot;
const IPS_69 = [...replayDaFixture(FIXTURE_BARRA['35797769']).score_timeline].sort((a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0));
const CONFINI_69 = confiniCalcio(IPS_69);
const fase69 = (ms: number): FaseReplay => faseCalcioDaConfini(CONFINI_69, ms);
const TENNIS = tennisFixture as unknown as TennisReplayData;
const PUNTEGGI = ordinaPunteggio(TENNIS.score_timeline);
const IN_GIOCO = inizioInGioco(TENNIS.frames);
const faseTennisAl = (ms: number): FaseReplay => faseTennisDaEtichetta(faseTennis(PUNTEGGI, new Date(ms).toISOString(), IN_GIOCO));

function monta(esito: EsitoBot, faseIstante?: (ms: number) => FaseReplay) {
    const onSeek = vi.fn();
    const a = analizzaEsito(esito, ms => `m${ms}`);
    const r = render(<RegistroOperazioniBot esito={esito} analisi={a} nowMs={Number.MAX_SAFE_INTEGER} onSeek={onSeek}
        etichettaIstante={ms => `m${ms}`} faseIstante={faseIstante} nomeMercato={m => `M${m}`} nomeSelezione={(_m, s) => `S${s}`} />);
    return { ...r, onSeek, a };
}

describe('registro per fase (calcio, media under 35797769, 4 clic veri)', () => {
    it('sezioni fisse PRE-PARTITA / 1° TEMPO / INTERVALLO / 2° TEMPO coi cicli del bot nati in ciascuna', () => {
        const { a } = monta(MULTI, fase69);
        const sez = screen.getAllByTestId('registro-fase');
        expect(sez.map(s => s.getAttribute('data-fase'))).toEqual(['pre', '1t', 'int', '2t']);
        const cicliDi = (i: number) => within(sez[i]).queryAllByTestId('registro-ciclo').map(c => c.getAttribute('data-ciclo'));
        expect([0, 1, 2, 3].map(cicliDi)).toEqual([['1'], ['2'], ['3'], []]);
        expect(within(sez[3]).getByText('nessuna operazione in questa fase')).toBeTruthy();
        // P&L della sezione (metodo del bot: i cicli)
        expect(sez.map(s => within(s).getByTestId('registro-fase-pnl').textContent)).toEqual([
            'dei cicli: lordo +0,02 · netto +0,02', 'dei cicli: lordo +0,11 · netto +0,10',
            'dei cicli: lordo +0,35 · netto +0,33', 'dei cicli: lordo 0,00 · netto 0,00',
        ]);
        // ogni ordine compare una volta
        expect(screen.getAllByTestId('registro-ordine')).toHaveLength(a.ordini.length);
    });

    it('il ciclo che attraversa due fasi sta dove e\' nato, con «chiuso al ...» e la fase della chiusura', () => {
        const { a } = monta(MULTI, fase69);
        const cicli = screen.getAllByTestId('registro-ciclo');
        const chiuso = (i: number) => within(cicli[i]).queryByTestId('registro-ciclo-chiuso-al')?.textContent ?? null;
        expect(chiuso(0)).toBe(`chiuso al m${a.registro.cicli[0].aMs} · 1° TEMPO`);
        expect(chiuso(1)).toBeNull();
        expect(chiuso(2)).toBe(`chiuso al m${a.registro.cicli[2].aMs} · 2° TEMPO`);
    });

    it('in fondo i totali di oggi, «✓ uguale al referto del bot»', () => {
        monta(MULTI, fase69);
        const tot = screen.getByTestId('registro-totale');
        expect(within(tot).getByTestId('registro-totale-netto').textContent).toBe('+0,46');
        expect(within(tot).getByTestId('confronto-banco').getAttribute('data-ok')).toBe('1');
        // il lordo delle fasi somma al totale (+0,48); il netto no (+0,45 contro +0,46),
        // perche' la commissione del conto si calcola sul totale: la nota lo dice
        expect(screen.getByTestId('registro-totale-nota').textContent)
            .toMatch(/^somma delle fasi: lordo \+0,48 · netto \+0,45 \(la commissione si/);
    });

    it('vista cronologica divisa per fase (la fase dell\'istante di ogni evento)', () => {
        monta(MULTI, fase69);
        fireEvent.click(screen.getByRole('radio', { name: 'cronologica' }));
        const crono = screen.getByTestId('registro-cronologico');
        expect(within(crono).getAllByTestId('registro-fase-cronologica').map(x => x.getAttribute('data-fase')))
            .toEqual(['pre', '1t', 'int', '2t']);
    });

    it('senza la fase il registro e\' quello di prima (nessuna sezione, nessun totale)', () => {
        monta(MULTI);
        expect(screen.queryAllByTestId('registro-fase')).toHaveLength(0);
        expect(screen.queryByTestId('registro-totale')).toBeNull();
        expect(screen.getAllByTestId('registro-ciclo')).toHaveLength(3);
    });
});

describe('i cicli sono quelli del bot; il ripiego lo dice', () => {
    it('4 cicli del bot (due coppie nello stesso istante) -> 4 cicli nel registro, coi numeri e le origini del bot', () => {
        monta(ESITO_4, fase69);
        expect(screen.getByTestId('registro-fonte-cicli').getAttribute('data-fonte')).toBe('bot');
        expect(screen.getAllByTestId('registro-ciclo').map(c => c.getAttribute('data-ciclo'))).toEqual(['1', '2', '3', '4']);
        expect(screen.getAllByTestId('registro-ciclo-bot').map(x => x.textContent)).toEqual([
            'per il bot: partito da un clic · CHIUSO · lordo +0,18 · netto +0,17',
            'per il bot: rientro automatico pre-match · CHIUSO · lordo +0,18 · netto +0,17',
            'per il bot: partito da un clic · CHIUSO · lordo +0,18 · netto +0,17',
            'per il bot: rientro automatico pre-match · CHIUSO · lordo +0,18 · netto +0,17',
        ]);
        expect(screen.getAllByTestId('registro-ciclo-pnl').map(x => x.textContent)).toEqual(Array(4).fill('P&L +0,18'));
    });

    it('scalper (il bot non dichiara i cicli): ricavati dagli ordini, e il registro lo dice', () => {
        monta(SCALPER, fase69);
        const f = screen.getByTestId('registro-fonte-cicli');
        expect(f.getAttribute('data-fonte')).toBe('ordini');
        expect(f.textContent).toMatch(/il bot non li dichiara, ricavati dagli ordini/);
        // a regolamento: in fondo il totale del banco
        expect(within(screen.getByTestId('registro-totale')).getByTestId('confronto-banco').getAttribute('data-ok')).toBe('1');
    });
});

describe('riquadro P&L: la riga «per fase» sopra «a regolamento», il resto identico', () => {
    it('media under 35797769: pre-partita / 1T / intervallo (ha un ciclo) / 2T coi lordi dei cicli del bot', () => {
        const a = analizzaEsito(MULTI);
        render(<RiepilogoPnlBot esito={MULTI} analisi={a} nowMs={Number.MAX_SAFE_INTEGER} faseIstante={fase69} />);
        const voci = screen.getAllByTestId('pnl-fase');
        expect(voci.map(v => [v.getAttribute('data-fase'), v.textContent])).toEqual([
            ['pre', 'pre-partita +0,02 (netto +0,02)'], ['1t', '1T +0,11 (netto +0,10)'],
            ['int', 'intervallo +0,35 (netto +0,33)'], ['2t', '2T 0,00 (netto 0,00)'],
        ]);
        // la riga sta sopra «a regolamento»; i blocchi di sempre con gli stessi numeri
        const riga = screen.getByTestId('pnl-per-fase');
        const regolato = screen.getByTestId('pnl-regolato-netto');
        expect(riga.compareDocumentPosition(regolato) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
        expect(regolato.textContent).toBe('+0,47');
        expect(screen.getByTestId('pnl-cicli-netto').textContent).toBe('+0,46');
    });

    it('scalper base 35797769: a regolamento per fase, l\'intervallo vuoto non compare', () => {
        const a = analizzaEsito(SCALPER);
        render(<RiepilogoPnlBot esito={SCALPER} analisi={a} nowMs={Number.MAX_SAFE_INTEGER} faseIstante={fase69} />);
        expect(screen.getByTestId('pnl-per-fase').textContent).toMatch(/^per fase \(a regolamento\)/);
        const fasi = screen.getAllByTestId('pnl-fase').map(v => v.getAttribute('data-fase'));
        expect(fasi).toEqual(expect.arrayContaining(['pre', '1t', '2t']));
    });

    it('tennis 35790089: PRE-PARTITA / SET n dallo stesso componente', () => {
        const a = analizzaEsito(TENNIS_ESITO);
        render(<RiepilogoPnlBot esito={TENNIS_ESITO} analisi={a} nowMs={Number.MAX_SAFE_INTEGER} faseIstante={faseTennisAl} />);
        const fasi = screen.getAllByTestId('pnl-fase').map(v => v.getAttribute('data-fase'));
        expect(fasi.slice(0, 3)).toEqual(['pre', 'set1', 'set2']);
    });

    it('senza la fase il riquadro e\' quello di prima (nessuna riga «per fase»)', () => {
        render(<RiepilogoPnlBot esito={MULTI} analisi={analizzaEsito(MULTI)} nowMs={Number.MAX_SAFE_INTEGER} />);
        expect(screen.queryByTestId('pnl-per-fase')).toBeNull();
    });

    it('EsitoBotPanel passa la fase a registro e riquadro', () => {
        render(<EsitoBotPanel esito={MULTI} analisi={analizzaEsito(MULTI)} nowMs={Number.MAX_SAFE_INTEGER} faseIstante={fase69}
            inviato={{ dal_ms: MULTI.dal_ms!, clic_ms: MULTI.clic_ms! }} onSeek={() => {}}
            nomeMercato={m => m} nomeSelezione={(_m, s) => String(s)} />);
        expect(screen.getByTestId('pnl-per-fase')).toBeTruthy();
        expect(screen.getAllByTestId('registro-fase')).toHaveLength(4);
        expect(screen.getAllByTestId('confronto-banco').every(c => c.getAttribute('data-ok') === '1')).toBe(true);
    });
});
