// ============================================================================
// useOperativitaBot — l'analisi dell'esito «Applica bot» (07/10 sera), una
// volta per esito: ordini, cicli, eventi, clic. Usata IDENTICA dal Match
// Replay (calcio) e dal Replay Tennis: nessuna logica per bot o per sport.
// ============================================================================
import { useMemo } from 'react';
import type { EsitoBot } from '@/lib/replayBot';
import {
    analizza, clicNelRegistro, contoCicli, contoRegolato, numeroDelBot, registroCicli,
    type ClicRegistro, type CicloOperativo, type EventoOperazione, type OrdineBot, type RegistroCicli,
} from '@/lib/replayOperazioni';

export interface OperativitaBot {
    ordini: OrdineBot[];
    perChiave: Map<string, OrdineBot>;
    cicli: CicloOperativo[];
    eventi: EventoOperazione[];
    clic: ClicRegistro[];
    /** P&L a regolamento ricavato dalle righe (deve coincidere col banco) */
    regolato: ReturnType<typeof contoRegolato>;
    /** P&L dei cicli col metodo del banco della media under */
    cicliConto: ReturnType<typeof contoCicli>;
    aliquota: number;
    /** 08/10 (cantiere 10): i cicli del REGISTRO, quelli del bot quando li dichiara */
    registro: RegistroCicli;
}

/** L'analisi PURA dell'esito (fuori da React: la usano anche i test). */
export function analizzaEsito(esito: EsitoBot, etichetta?: (ms: number) => string,
    runnerDi?: (marketId: string) => ReadonlyArray<number> | undefined): OperativitaBot {
    const { ordini, cicli, eventi } = analizza(esito.righe, esito.esiti_mercati ?? null, runnerDi);
    const aliquota = esito.conto_dichiarato?.aliquota
        ?? Object.values(esito.esiti_mercati ?? {}).find(e => e.aliquota != null)?.aliquota
        ?? 0.05;
    return {
        ordini,
        perChiave: new Map(ordini.map(o => [o.chiave, o])),
        cicli,
        eventi,
        clic: clicNelRegistro(esito.clic_bot ?? null, ordini, cicli, etichetta,
            esito.cicli_bot ? numeroDelBot(esito.cicli_bot) : undefined),
        regolato: contoRegolato(ordini, esito.esiti_mercati ?? null),
        cicliConto: contoCicli(cicli, aliquota),
        aliquota,
        registro: registroCicli(ordini, cicli, esito.cicli_bot, esito.esiti_mercati ?? null),
    };
}

export function useOperativitaBot(esito: EsitoBot | null, etichetta?: (ms: number) => string,
    runnerDi?: (marketId: string) => ReadonlyArray<number> | undefined): OperativitaBot | null {
    // l'etichetta e i runner cambiano identita' a ogni render della pagina: l'analisi
    // dipende solo dall'esito (le etichette servono ai testi dei clic)
    // eslint-disable-next-line react-hooks/exhaustive-deps
    return useMemo(() => (esito ? analizzaEsito(esito, etichetta, runnerDi) : null), [esito]);
}
