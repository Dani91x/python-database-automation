// misura del tempo del verificatore sulle fixture vere (mediana di 25 giri dopo 3 di riscaldamento)
import { verificaBarraReplayCalcio } from '@/lib/replayVerificaBarraCalcio';
import { caricaPartita, eventiConFixture } from '@/lib/__fixtures__/replayBarraTutte';

const etichetta = process.argv[2] ?? '?';
for (const ev of eventiConFixture()) {
    const { replay, estremi } = caricaPartita(ev);
    for (let i = 0; i < 3; i++) verificaBarraReplayCalcio(replay, { estremi });
    const t: number[] = [];
    let incoerenze = -1;
    for (let i = 0; i < 25; i++) {
        const a = performance.now();
        const e = verificaBarraReplayCalcio(replay, { estremi });
        t.push(performance.now() - a);
        incoerenze = e.incoerenze.length;
    }
    t.sort((x, y) => x - y);
    console.log(`${etichetta} ${ev}: mediana ${t[12].toFixed(1)} ms (min ${t[0].toFixed(1)}, max ${t[24].toFixed(1)}), incoerenze ${incoerenze}`);
}
