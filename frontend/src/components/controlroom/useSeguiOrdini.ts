// ============================================================================
// useSeguiOrdini.ts - B17 (25/09): la scheda SEGUE il suo ordine dopo il clic
// fino all'esito terminale e lo dice con un messaggio (`lib/esitoAbbinamento`).
//
// Da dove arriva l'esito, in quest'ordine (dichiarato a video):
//  1. la RIGA dell'ordine nella mappa delle posizioni della Control Room
//     (`righePos`): messaggio del CANALE del bot al ms (overlay con `_seq`,
//     `righeCanale.ts`) oppure l'ultimo blocco del DATABASE;
//  2. finche' la riga non c'e' o non e' terminale: la coda del bot riletta per
//     id ogni 2 s (la stessa `LETTURA` del «Chiudi», `chiudiRiga.ts`) e una
//     RILETTURA MIRATA del blocco del bot (`RilettureMirate`: al massimo una
//     ogni 2 s per bot, coalescenza) - nessuna query nuova, nessun canale nuovo.
//     La rilettura mirata si chiede solo se nessun messaggio del canale ha
//     portato la riga negli ultimi 3 s, e al massimo per 90 s dal clic (poi
//     resta il giro dei 30 s e il canale): il 13/09 il DB e' caduto per IO.
//
// Paper e live: stesso percorso, stesso messaggio (`simulato` lo dice).
// ============================================================================
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Bot } from '@/lib/controlRoom';
import type { MappaRighe } from '@/lib/righeCanale';
import {
    aggiungiSeguito, esitoDelClic, idsDaRisultato, nonChiuseDaRisultato, SCADENZA_SEGUITO_MS,
    type ClicOrdine, type EsitoAbbinamento, type GambaSeguita, type ModoGambe, type RichiestaSeguita,
} from '@/lib/esitoAbbinamento';
import { fetchRichiestaSafe } from '@/lib/safeBot';
import { faseDaRichiesta, LETTURA, type BotConChiusura, type RichiestaLetta } from './chiudiRiga';

/** Oltre questo tempo dal clic non si chiedono piu' riletture mirate. */
export const RILETTURE_MAX_MS = 90_000;
/** Un messaggio del canale piu' fresco di cosi' rende inutile la rilettura. */
export const CANALE_FRESCO_S = 3;
/** Cadenza della rilettura della coda. */
export const GIRO_MS = 2_000;

export interface EsitoSeguito {
    clic: ClicOrdine;
    esito: EsitoAbbinamento;
    gambe: GambaSeguita[];
    /** 25/09 (residui B17) - come sono state trovate le gambe (id, chiave, ripiego) */
    modoGambe?: ModoGambe;
    /** 25/09 (residui B17) - la riga della coda letta (id dichiarati, posizioni non chiuse) */
    richiesta?: RichiestaSeguita | null;
}

export type LetturaRichiesta = (clic: ClicOrdine) => Promise<RichiestaLetta | null>;

/** Di serie: Safe per id (anche le proposte), gli altri bot con la `LETTURA` del «Chiudi». */
export const LEGGI_DI_SERIE: LetturaRichiesta = async (clic) => {
    if (clic.requestId === null) return null;
    if (clic.bot === 'safe') return fetchRichiestaSafe(clic.requestId);
    const leggi = LETTURA[clic.bot as BotConChiusura];
    return leggi ? leggi(clic.requestId) : null;
};

/** La riga della coda tradotta (pura: la usa anche il test). */
export function richiestaSeguita(clic: ClicOrdine, r: RichiestaLetta, lettaMs: number): RichiestaSeguita {
    const f = faseDaRichiesta(clic.bot as BotConChiusura, r);
    return {
        fase: f.fase, motivo: f.motivo, tradeIds: idsDaRisultato(r.result, clic.tipo), lettaMs,
        nonChiuse: nonChiuseDaRisultato(r.result),
    };
}

export function useSeguiOrdini(args: {
    mappa: MappaRighe<unknown>;
    nowMs: number;
    chiediRilettura: (bot: Bot) => void;
    leggi?: LetturaRichiesta;
}) {
    const { mappa, nowMs, chiediRilettura } = args;
    const leggi = args.leggi ?? LEGGI_DI_SERIE;
    const [seguiti, setSeguiti] = useState<ClicOrdine[]>([]);
    const [richieste, setRichieste] = useState<Record<string, RichiestaSeguita>>({});

    const segui = useCallback((clic: ClicOrdine) => {
        setSeguiti((p) => aggiungiSeguito(p, clic));
        setRichieste((p) => {
            if (!(clic.chiave in p)) return p;
            const n = { ...p };
            delete n[clic.chiave];
            return n;
        });
    }, []);

    const esiti = useMemo<EsitoSeguito[]>(
        () => seguiti.map((clic) => {
            const richiesta = richieste[clic.chiave] ?? null;
            return { clic, richiesta, ...esitoDelClic(clic, richiesta, mappa, nowMs) };
        }),
        [seguiti, richieste, mappa, nowMs],
    );

    // chi va ancora seguito (non terminale, non scaduto)
    const aperti = esiti.filter((e) => !e.esito.terminale && nowMs - e.clic.clicMs < SCADENZA_SEGUITO_MS);
    const firmaAperti = aperti.map((e) => e.clic.chiave).join('|');
    const apertiRef = useRef(aperti);
    apertiRef.current = aperti;
    const leggiRef = useRef(leggi);
    leggiRef.current = leggi;
    const rileggiRef = useRef(chiediRilettura);
    rileggiRef.current = chiediRilettura;
    const richiesteRef = useRef(richieste);
    richiesteRef.current = richieste;

    useEffect(() => {
        if (!firmaAperti) return undefined;
        let vivo = true;
        const giro = async () => {
            const ora = Date.now();
            const botDaRileggere = new Set<Bot>();
            for (const e of apertiRef.current) {
                // la rilettura mirata del blocco del bot: solo se il canale tace
                const dalCanale = e.gambe.some((g) => g.fonte === 'canale' && (g.etaS ?? Infinity) <= CANALE_FRESCO_S);
                if (!dalCanale && ora - e.clic.clicMs < RILETTURE_MAX_MS) botDaRileggere.add(e.clic.bot);
                const r0 = richiesteRef.current[e.clic.chiave];
                // una richiesta in stato finale non si rilegge: `result` (con gli
                // id delle righe) si scrive insieme allo stato finale
                const chiusa = r0 != null
                    && (r0.fase === 'eseguita' || r0.fase === 'rifiutata' || r0.fase === 'ignota');
                if (e.clic.requestId === null || chiusa) continue;
                try {
                    const r = await leggiRef.current(e.clic);
                    if (!vivo || !r) continue;
                    const rs = richiestaSeguita(e.clic, r, Date.now());
                    setRichieste((p) => ({ ...p, [e.clic.chiave]: rs }));
                } catch { /* il giro dopo riprova: il comando vero e' gia' scritto */ }
            }
            if (!vivo) return;
            for (const b of botDaRileggere) {
                try { rileggiRef.current(b); } catch { /* il giro dei 30 s riprova */ }
            }
        };
        void giro();
        const t = window.setInterval(() => { void giro(); }, GIRO_MS);
        return () => { vivo = false; window.clearInterval(t); };
    }, [firmaAperti]);

    const esitoPer = useCallback(
        (chiave: string): EsitoSeguito | null => esiti.find((e) => e.clic.chiave === chiave) ?? null,
        [esiti],
    );

    return { segui, esiti, esitoPer };
}
