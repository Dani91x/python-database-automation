// ============================================================================
// certezzaChiusura.ts — IL GIUDIZIO «EFFETTIVAMENTE CHIUSA», PURO.
//
// Ordine dell'utente, 18/09/2026: «nella scheda "chiusure" il trader deve
// sapere se l'operazione è stata EFFETTIVAMENTE chiusa o no; oggi non succede
// né su tennis né su calcio». Questo file risponde a UNA domanda sola, per
// UNA posizione: «l'apertura è ancora esposta a mercato, sì o no, e quanto?».
//
// PERCHÉ QUESTO FILE NON SI FIDA DELLO STATO SCRITTO DAL BOT
// L'audit (18/09) trova che `Betfair/safe_strategy/execution.py:914-960`
// (`hedge_state`) calcola `hedged_size` guardando `size`/`price` di righe con
// `status in ('open','won','lost','void')` — NON `size_matched`/
// `avg_price_matched`. Una gamba di chiusura `status='open'` ma abbinata solo
// in parte viene contata come interamente abbinata, e `apply_hedge_state`
// porta l'apertura a `status='hedged'` (etichetta "CHIUSO", teal) SUBITO. È
// esattamente il §7.36 di `PROCESSO_STANDARD_BOT.md`: «un controllo che
// dipende dalla confessione del bot non certifica». Questo file quindi non
// legge `status='hedged'` come prova di niente: ricalcola da zero, sulle
// size e sui prezzi ABBINATI di ogni gamba (mai i chiesti), quanto della
// posizione resta scoperto — la stessa identità di cassa di un green-up:
//   stake-di-chiusura-che-pareggia = stake_apertura × prezzo_apertura / prezzo_chiusura
// (chi chiude a un prezzo diverso da quello d'ingresso ha bisogno di più o
// meno stake per pareggiare: è l'aritmetica di un cash-out, non un'ipotesi).
//
// NESSUNA FORMULA NUOVA PER LA LIABILITY: si usa `layLiabilityFromSize`
// (`lib/liveOrders.ts:698-701`), lo stesso specchio che il resto della
// piattaforma usa per (quota−1)×stake; per il lato BACK la liability è la
// size stessa, come in `liabilityTennis` (`useControlRoom.ts:351-362`).
//
// RIUSO PER-GAMBA: la verità di OGNI gamba (chiesto/abbinato/residuo/prezzo
// medio/fonte colonna-o-nota/quando l'ha detto Betfair) è quella di
// `lib/statoOrdine.ts` — la stessa che legge la Control Room, Omega, Safe e
// Mike. Qui non si rilegge nessun campo che `statoOrdine` non legga già.
//
// PAPER vs LIVE: in LIVE una copertura si dice CONFERMATA solo se i numeri
// di abbinamento vengono dalle COLONNE di Betfair (`fonte: 'colonna'` in
// `statoOrdine`), mai dalla nota del servizio (`meta`) — una nota è quello
// che il bot CREDE di aver fatto, non quello che Betfair ha confermato. In
// PAPER la verità è il fill simulato stesso: colonna o nota vanno bene.
//
// Tutto PURO: nessun React, nessuna chiamata di rete, nessuna nuova lettura.
// ============================================================================
import { statoOrdine, type RigaOrdine } from '@/lib/statoOrdine';
import { layLiabilityFromSize } from '@/lib/liveOrders';
import type { Modo } from '@/lib/controlRoom';

/** Tolleranza sui centesimi: sotto questa soglia un residuo non esiste
 *  (stessa soglia di `statoOrdine.ts` e di `posizioniChiuse.SOGLIA_PARI`). */
const EPS = 0.005;

/**
 * I sei stati, ESAUSTIVI e onesti: ogni posizione/chiusura entra in UNO solo.
 *   · CHIUSA_CONFERMATA    tutte le gambe di chiusura abbinate per intero,
 *                          residuo 0; in LIVE solo se il dato viene da Betfair.
 *   · CHIUSA_PARZIALE      abbinata in parte: resta esposizione, nessuna
 *                          gamba è ancora sul book (non tornerà da sola).
 *   · CHIUSURA_IN_ATTESA   ordine di chiusura a mercato non ancora abbinato
 *                          per intero: può ancora completarsi da solo.
 *   · CHIUSURA_FALLITA     rifiutata/annullata e nessun'altra gamba copre:
 *                          la posizione è ANCORA APERTA — il caso pericoloso.
 *   · REGOLATA_DAL_MERCATO won/lost/void: nessuna esposizione, punto e basta.
 *   · NON_VERIFICABILE     dati insufficienti: MAI spacciata per chiusa.
 */
export type StatoCertezzaChiusura =
    | 'CHIUSA_CONFERMATA'
    | 'CHIUSA_PARZIALE'
    | 'CHIUSURA_IN_ATTESA'
    | 'CHIUSURA_FALLITA'
    | 'REGOLATA_DAL_MERCATO'
    | 'NON_VERIFICABILE';

/** Quanto resta ESPOSTO A MERCATO, in due valute diverse: lo stake (quanto
 *  capitale non ha ancora una contropartita) e la liability (quanto si
 *  rischia se il verdetto va contro il lato scoperto). `null` = non
 *  calcolabile con i dati che ci sono — mai uno zero inventato. */
export interface EsposizioneResidua {
    stake: number | null;
    liability: number | null;
}

const ESPOSIZIONE_NULLA: EsposizioneResidua = { stake: 0, liability: 0 };
const ESPOSIZIONE_IGNOTA: EsposizioneResidua = { stake: null, liability: null };

export interface RisultatoCertezzaChiusura {
    stato: StatoCertezzaChiusura;
    esposizione: EsposizioneResidua;
    /** frazione (0-1) dello stake d'apertura già coperta; null = non calcolabile */
    coperturaFrazione: number | null;
    /** PERCHÉ questo stato, in italiano: sempre presente, anche per CONFERMATA */
    motivo: string;
}

/** La posizione da giudicare: un'apertura e le gambe che la chiudono. */
export interface PosizioneDaGiudicare {
    /** la riga di apertura, nella forma comune ai tre bot (`RigaOrdine`) */
    apertura: RigaOrdine;
    /** le gambe di chiusura (`closes_trade_id`), nell'ordine in cui sono avvenute */
    chiusure: readonly RigaOrdine[];
    /**
     * true = OGNI gamba (apertura + tutte le chiusure) è REGOLATA dal mercato
     * (won/lost/void). È lo stesso criterio di `posizioniChiuse.ts` — non lo
     * si ricalcola qui: chi chiama lo sa già dallo stato delle righe.
     */
    regolataDalMercato: boolean;
    /** paper o live: cambia SOLO la soglia per dire CONFERMATA (v. sopra) */
    modo: Modo;
}

function cent(n: number): number {
    return Math.round(n * 100) / 100;
}

function motivoFonteInsufficiente(): string {
    return 'la copertura risulta completa SOLO dalla nota del servizio (meta), non dalle '
        + 'colonne di Betfair: in LIVE questo non basta per dire CONFERMATA (§7.36 — un '
        + 'controllo che dipende dalla confessione del bot non certifica).';
}

/**
 * Liability di UNA gamba abbinata, dato il suo lato: BACK rischia lo stake,
 * LAY rischia `(quota−1)×stake` (`layLiabilityFromSize`, `lib/liveOrders.ts`).
 * `null` = lato assente o prezzo non valido: non si inventa un lato.
 */
function liabilityDiLato(lato: 'back' | 'lay' | null, size: number, prezzo: number | null): number | null {
    if (lato === 'back') return cent(size);
    if (lato === 'lay') {
        if (prezzo == null || prezzo <= 1) return null;
        return layLiabilityFromSize(size, prezzo);
    }
    return null;
}

/**
 * IL GIUDIZIO. Una sola funzione, per qualunque bot: Omega, Safe (calcio e
 * tennis), Mike, i quattro bot tennis — tutti scrivono (in colonna o in
 * nota) la stessa cosa che `statoOrdine` legge.
 */
export function certezzaChiusura(pos: PosizioneDaGiudicare): RisultatoCertezzaChiusura {
    // 1. IL MERCATO HA GIÀ DECISO: vince su tutto, non c'è più niente in ballo.
    if (pos.regolataDalMercato) {
        return {
            stato: 'REGOLATA_DAL_MERCATO',
            esposizione: ESPOSIZIONE_NULLA,
            coperturaFrazione: 1,
            motivo: 'il mercato si è regolato (vinta, persa o void): nessuna esposizione residua.',
        };
    }

    // 2. NESSUN TENTATIVO DI CHIUSURA: non c'è niente da giudicare come chiusura
    //    (è semplicemente una posizione aperta). Mai dedurre una chiusura che
    //    non è stata nemmeno tentata.
    if (pos.chiusure.length === 0) {
        return {
            stato: 'NON_VERIFICABILE',
            esposizione: ESPOSIZIONE_IGNOTA,
            coperturaFrazione: null,
            motivo: 'nessuna gamba di chiusura registrata per questa posizione: non c\'è '
                + 'niente da giudicare come chiusura.',
        };
    }

    const so = statoOrdine(pos.apertura);
    const abbApertura = so.abbinato.valore;
    const prezzoApertura = so.prezzoMedio.valore;
    const latoApertura = pos.apertura.side === 'lay' ? 'lay' as const
        : pos.apertura.side === 'back' ? 'back' as const : null;

    if (abbApertura == null || abbApertura <= EPS || prezzoApertura == null) {
        return {
            stato: 'NON_VERIFICABILE',
            esposizione: ESPOSIZIONE_IGNOTA,
            coperturaFrazione: null,
            motivo: 'la size o il prezzo medio ABBINATO dell\'apertura non sono dichiarati: '
                + 'senza questi due numeri la copertura non è calcolabile.',
        };
    }

    const gambe = pos.chiusure.map((g) => ({ ordine: g, s: statoOrdine(g) }));
    const latoChiusura = latoApertura === 'back' ? 'lay' as const
        : latoApertura === 'lay' ? 'back' as const
            : (gambe.find((g) => g.ordine.side)?.ordine.side === 'lay' ? 'lay' as const : 'back' as const);

    const abbinatoTotale = cent(gambe.reduce((s, g) => s + (g.s.abbinato.valore ?? 0), 0));

    // 3. FALLIMENTO: OGNI gamba è in stato terminale negativo (rifiutata o
    //    annullata) e NESSUNA ha abbinato un centesimo. La posizione non ha
    //    mai avuto una contropartita: è ANCORA APERTA, tutto lo stake
    //    d'apertura resta esposto — è il caso da gridare.
    const tutteFallite = gambe.every((g) => g.s.esito === 'rifiutato' || g.s.esito === 'annullato');
    if (abbinatoTotale <= EPS && tutteFallite) {
        const nRifiutate = gambe.filter((g) => g.s.esito === 'rifiutato').length;
        const nAnnullate = gambe.filter((g) => g.s.esito === 'annullato').length;
        const dettaglio = [
            nRifiutate > 0 ? `${nRifiutate} rifiutata${nRifiutate > 1 ? 'e' : ''} da Betfair` : null,
            nAnnullate > 0 ? `${nAnnullate} annullata${nAnnullate > 1 ? 'e' : ''}` : null,
        ].filter(Boolean).join(' e ');
        return {
            stato: 'CHIUSURA_FALLITA',
            esposizione: {
                stake: abbApertura,
                liability: liabilityDiLato(latoApertura, abbApertura, prezzoApertura),
            },
            coperturaFrazione: 0,
            motivo: `${gambe.length === 1 ? 'la gamba di chiusura è' : 'tutte le gambe di chiusura sono'} `
                + `${dettaglio}: la posizione è ANCORA APERTA, nessuna contropartita è stata trovata.`,
        };
    }

    const cePendente = gambe.some((g) => (
        g.s.esito === 'appoggiato' || g.s.esito === 'parziale'
        || g.s.esito === 'riconciliazione' || g.s.esito === 'ignoto'
    ));

    // 4. NESSUN ABBINAMENTO ANCORA, MA C'È UN ORDINE SUL BOOK (non è un
    //    fallimento: può ancora completarsi da solo). Non esiste un prezzo di
    //    chiusura da pesare — non serve: senza copertura l'esposizione è
    //    ancora TUTTA quella dell'apertura, la stessa aritmetica di §3.
    if (abbinatoTotale <= EPS && cePendente) {
        return {
            stato: 'CHIUSURA_IN_ATTESA',
            esposizione: {
                stake: abbApertura,
                liability: liabilityDiLato(latoApertura, abbApertura, prezzoApertura),
            },
            coperturaFrazione: 0,
            motivo: 'nessuna gamba di chiusura ha ancora abbinato qualcosa: almeno una è '
                + 'ancora sul book, l\'esposizione dell\'apertura è ancora intera.',
        };
    }

    // 5. QUANTO SERVIREBBE PER PAREGGIARE (identità di cassa del cash-out):
    //    stake_chiusura_necessario = stake_apertura × prezzo_apertura / prezzo_chiusura.
    //    Si usa il prezzo medio PESATO delle sole gambe che hanno abbinato
    //    qualcosa: una gamba ancora a zero non ha un prezzo "vero" da pesare.
    const pesate = gambe.filter((g) => (g.s.abbinato.valore ?? 0) > EPS && g.s.prezzoMedio.valore != null);
    const pesoTotale = pesate.reduce((s, g) => s + (g.s.abbinato.valore as number), 0);
    const prezzoChiusuraMedio = pesate.length && pesoTotale > 0
        ? pesate.reduce((s, g) => s + (g.s.abbinato.valore as number) * (g.s.prezzoMedio.valore as number), 0) / pesoTotale
        : null;

    if (prezzoChiusuraMedio == null || prezzoChiusuraMedio <= 1) {
        return {
            stato: 'NON_VERIFICABILE',
            esposizione: ESPOSIZIONE_IGNOTA,
            coperturaFrazione: null,
            motivo: 'il prezzo medio ABBINATO delle gambe di chiusura non è dichiarato: la '
                + 'percentuale di copertura non è calcolabile.',
        };
    }

    const richiesto = cent(abbApertura * prezzoApertura / prezzoChiusuraMedio);
    const coperturaFrazione = richiesto > 0 ? Math.min(1, abbinatoTotale / richiesto) : 1;
    const residuoInChiusura = Math.max(0, cent(richiesto - abbinatoTotale));
    const esposizioneResidua: EsposizioneResidua = {
        stake: residuoInChiusura,
        liability: liabilityDiLato(latoChiusura, residuoInChiusura, prezzoChiusuraMedio),
    };

    // 6. COPERTURA COMPLETA (entro il centesimo).
    if (coperturaFrazione >= 1 - EPS) {
        const daBetfair = so.abbinato.fonte !== 'nota'
            && gambe.every((g) => g.s.abbinato.fonte !== 'nota');
        if (pos.modo === 'live' && !daBetfair) {
            return {
                stato: 'NON_VERIFICABILE',
                esposizione: ESPOSIZIONE_NULLA,
                coperturaFrazione: 1,
                motivo: motivoFonteInsufficiente(),
            };
        }
        return {
            stato: 'CHIUSA_CONFERMATA',
            esposizione: ESPOSIZIONE_NULLA,
            coperturaFrazione: 1,
            motivo: 'le gambe di chiusura coprono per intero, ad abbinato, lo stake dell\'apertura.',
        };
    }

    const percento = Math.round(coperturaFrazione * 100);

    // 7. ALMENO UNA GAMBA È ANCORA SUL BOOK: può ancora completarsi da sola.
    if (cePendente) {
        return {
            stato: 'CHIUSURA_IN_ATTESA',
            esposizione: esposizioneResidua,
            coperturaFrazione,
            motivo: `copertura al ${percento}%: almeno una gamba di chiusura è ancora sul `
                + 'book, non abbinata per intero.',
        };
    }

    // 8. NESSUNA GAMBA PENDENTE, COPERTURA NON COMPLETA, NON TUTTE FALLITE:
    //    è definitivo (es. residuo abbandonato, o parziale + fallita mista).
    return {
        stato: 'CHIUSA_PARZIALE',
        esposizione: esposizioneResidua,
        coperturaFrazione,
        motivo: `copertura al ${percento}%: restano esposti ${cent(esposizioneResidua.stake ?? 0)} `
            + '€ di stake, nessuna gamba di chiusura è ancora sul book per completarla da sola.',
    };
}

/** Solo per il badge: verde pieno SOLO per questi due stati. */
export function eCertezzaVerde(stato: StatoCertezzaChiusura): boolean {
    return stato === 'CHIUSA_CONFERMATA' || stato === 'REGOLATA_DAL_MERCATO';
}

/** true = il trader DEVE accorgersene: c'è ancora un rischio non dichiarato. */
export function eCertezzaAllarme(stato: StatoCertezzaChiusura): boolean {
    return stato === 'CHIUSURA_FALLITA' || stato === 'NON_VERIFICABILE';
}

export interface RiepilogoCertezza {
    n: number;
    confermate: number;
    parziali: number;
    inAttesa: number;
    fallite: number;
    regolate: number;
    nonVerificabili: number;
    /** somma degli stake ancora esposti fra parziali/in attesa/fallite/non verificabili */
    esposizioneStakeTotale: number;
}

const RIEPILOGO_VUOTO: RiepilogoCertezza = {
    n: 0, confermate: 0, parziali: 0, inAttesa: 0, fallite: 0, regolate: 0,
    nonVerificabili: 0, esposizioneStakeTotale: 0,
};

/**
 * Il riepilogo di UNA modalità (paper O live), MAI le due insieme: sommare
 * un'esposizione vera con una simulata userebbe un numero di soldi finti per
 * decidere quanto rischio reale c'è a mercato — la stessa regola di
 * `riepilogoChiuse` (`lib/posizioniChiuse.ts`) applicata alla certezza.
 *
 * Una riga con `modo` diverso da quello richiesto viene IGNORATA (non
 * sommata): il chiamante può passare l'intero elenco senza pre-filtrare, e
 * ottiene comunque un numero che non mischia le due contabilità.
 */
export function riepilogoCertezza(
    righe: readonly { modo: Modo; risultato: RisultatoCertezzaChiusura }[],
    modo: Modo,
): RiepilogoCertezza {
    const out = { ...RIEPILOGO_VUOTO };
    for (const r of righe) {
        if (r.modo !== modo) continue;
        out.n += 1;
        switch (r.risultato.stato) {
            case 'CHIUSA_CONFERMATA': out.confermate += 1; break;
            case 'CHIUSA_PARZIALE': out.parziali += 1; break;
            case 'CHIUSURA_IN_ATTESA': out.inAttesa += 1; break;
            case 'CHIUSURA_FALLITA': out.fallite += 1; break;
            case 'REGOLATA_DAL_MERCATO': out.regolate += 1; break;
            case 'NON_VERIFICABILE': out.nonVerificabili += 1; break;
        }
        if (r.risultato.stato !== 'REGOLATA_DAL_MERCATO' && r.risultato.stato !== 'CHIUSA_CONFERMATA') {
            out.esposizioneStakeTotale = cent(out.esposizioneStakeTotale + (r.risultato.esposizione.stake ?? 0));
        }
    }
    return out;
}
