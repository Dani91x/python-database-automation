// ============================================================================
// useChiusuraAlMs.ts - 25/09 (residui B17): il "se chiudo ora" di UNA riga AL
// PREZZO DEL MS, prima del clic su "Chiudi".
//
// Prima il prezzo e il P&L bloccabile della riga venivano dal feed dello
// scanner (`useControlRoom.chiusuraViva`, eta' di secondi). Ora: il ladder del
// mercato al ms (`usePrezzoAlMs` -> `sorgenteLadderAlMs`, la stessa sorgente
// delle schede delle proposte), P&L ricalcolato al tick con la stessa
// matematica (`lib/chiusuraAlMs.chiusuraAlPrezzo`); dove il canale non porta
// quel mercato, il prezzo dello scanner DICHIARATO ("prezzo dello scanner,
// X s fa"). La sorgente arriva dal contesto della Control Room: senza (test
// storici, altre pagine) resta lo scanner, dichiarato.
//
// Cosa NON fa: non cambia il payload del "Chiudi" (il servizio chiude a
// mercato come prima); il prezzo visto va solo alla scheda, per il delta
// dopo l'abbinamento.
// ============================================================================
import { usePrezzoAlMs, type SorgenteLadder } from './usePrezzoAlMs';
import {
    aliquotaAlMs, chiusuraAlPrezzo, ripiegoScanner, testoFonte,
} from '@/lib/chiusuraAlMs';
import type { ContestoPrezzoVisto, FontePrezzo } from '@/lib/schedaAlMs';
import type { PosizioneAperta } from './useControlRoom';

export interface ChiusuraMostrata {
    lato: 'back' | 'lay';
    prezzo: number | null;
    abbinabile: number | null;
    bloccabile: number | null;
    /** chi ha portato il prezzo: canale/db = ladder al ms, scanner = ripiego */
    fonte: FontePrezzo | null;
    istanteMs: number | null;
    /** "ladder al ms, 0,4 s fa" / "prezzo dello scanner, 12 s fa (...)" */
    testoFonte: string;
    /** true = il prezzo viene dal ladder al ms (canale o DB) */
    alMs: boolean;
    /**
     * 30/09 (P11) - l'aliquota con cui `bloccabile` e' NETTO (solo ramo al ms;
     * nel ramo senza dati del ms `bloccabile` e' quello dello scanner, gia'
     * netto con la stessa aliquota: qui `null`). `aliquotaDiRipiego` = la riga
     * non la portava e si e' usato il 5 % di `aliquotaDi`.
     */
    aliquota?: number | null;
    aliquotaDiRipiego?: boolean;
}

/** Il prezzo e il contesto che partono col clic (solo per la scheda). */
export function prezzoAlClic(c: ChiusuraMostrata, clicMs: number): { prezzo: number | null; contesto: ContestoPrezzoVisto } {
    return {
        prezzo: c.prezzo,
        contesto: {
            eta_ms: c.istanteMs == null ? null : Math.max(0, clicMs - c.istanteMs),
            fonte: c.fonte,
            prezzo_vivo_assente: c.prezzo == null,
            clic_ms: clicMs,
        },
    };
}

export function useChiusuraAlMs(
    chiusura: PosizioneAperta['chiusura'] | null | undefined,
    sorgente: SorgenteLadder | null | undefined,
): ChiusuraMostrata | null {
    const d = chiusura?.alMs ?? null;
    const lato = chiusura?.lato ?? null;
    // hook chiamato SEMPRE: senza dati (o senza sorgente) non si sottoscrive niente
    const { prezzo: p } = usePrezzoAlMs({
        sorgente: d ? sorgente : null, sport: d?.sport ?? 'calcio',
        marketId: d?.marketId ?? null, selectionId: d?.selectionId ?? null,
        lato, ripiego: ripiegoScanner(d),
    });
    if (!chiusura) return null;
    if (!d) {
        // riga senza i dati del ms (Mike senza mercato, righe storiche): il
        // numero dello scanner di prima, dichiarato
        return {
            lato: chiusura.lato, prezzo: chiusura.prezzo, abbinabile: chiusura.abbinabile,
            bloccabile: chiusura.bloccabile, fonte: chiusura.prezzo == null ? null : 'scanner',
            istanteMs: null,
            testoFonte: chiusura.prezzo == null ? 'prezzo non disponibile'
                : 'prezzo dello scanner, eta\' non pubblicata (la riga non porta mercato e selezione)',
            alMs: false,
        };
    }
    // 30/09 (P11) - NETTO di commissione con l'aliquota della riga, come il
    // ramo dello scanner (`chiusuraViva`): stessa gamba, stessa cifra.
    const aliquota = aliquotaAlMs(d);
    const c = chiusuraAlPrezzo(d.win, d.lose, chiusura.lato, p, aliquota);
    const nowMs = Date.now();
    return {
        ...c,
        aliquota,
        aliquotaDiRipiego: !(typeof d.aliquota === 'number' && Number.isFinite(d.aliquota) && d.aliquota > 0),
        fonte: c.prezzo == null ? null : p.fonte,
        istanteMs: c.prezzo == null ? null : p.istanteMs,
        testoFonte: c.prezzo == null ? 'prezzo non disponibile' : testoFonte(p, nowMs),
        alMs: c.prezzo != null && (p.fonte === 'canale' || p.fonte === 'db'),
    };
}
