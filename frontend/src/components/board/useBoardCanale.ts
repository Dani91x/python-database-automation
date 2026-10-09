// ============================================================================
// useBoardCanale.ts - 09/10/2026 (Programma del giorno).
//
// TUTTO dal canale locale che esiste gia' (`getLocalChannel(sport)`, un
// singleton per sport, porta 47331 calcio / 47332 tennis): «non voglio 40
// connessioni da gestire, tutto deve essere centralizzato» (utente, 09/10).
// Nessun socket, poller o realtime nuovo: solo sottoscrizioni a topic che il
// canale riceve gia' e UNA richiesta di sola lettura.
//
//   push `board`         -> righe MATCH_ODDS + tipi di mercato (contratto §1-§2)
//   push `board_mercato` -> righe del mercato scelto (contratto §3)
//   req  `board_mercato` -> {market_type}, rinnovata ogni 30 s finche' la
//                           scelta resta (il worker dimentica a 75 s); MAI per
//                           MATCH_ODDS; ripetuta subito a ogni riconnessione
//   `hello`/`modo_ordini`/`now` -> il modo ordini che il runner applica
//
// LA MEMORIA PER SPORT: le schede si rimontano quando si cambia sport, ma il
// `modo_ordini` arriva SOLO AL CAMBIO e il tabellone al giro del worker: chi
// si sottoscrive dopo li perderebbe. Un solo insieme di sottoscrizioni per
// sport (come lo store di `lib/localTransport`) tiene l'ULTIMO tabellone e
// l'ultimo modo; la scheda parte da li'. Le quote del mercato scelto NON si
// tengono: dopo 75 s senza rinnovo il worker smette di mandarle e una quota
// vecchia mostrata come viva e' peggio di un «caricamento».
//
// Canale giu': tutto torna «non noto» (mai un tabellone congelato spacciato
// per vivo, mai un modo ordini di prima della caduta).
// ============================================================================
import { useEffect, useState } from 'react';
import { getLocalChannel, type LocalStatus } from '@/lib/localChannel';
import { useLocalStatus } from '@/lib/localTransport';
import { leggiModoDalNow, leggiModoOrdiniCanale, type ModoOrdiniCanale } from '@/lib/runnerCanale';
import {
    MATCH_ODDS, RINNOVO_MERCATO_MS, frenoDa, leggiBoard, leggiBoardMercato, piuRecente,
    type MercatoScelto, type SportBoard, type Tabellone,
} from './boardDati';

export interface ModoDalCanale {
    /** l'ultimo `modo_ordini` (topic o hello), al cambio */
    alCambio: ModoOrdiniCanale | null;
    /** `kill_switch` dello STESSO messaggio di `alCambio` (mai unione) */
    freno: boolean | null;
    /** l'ultimo modo letto da un `now` (calcio) */
    dalNow: ModoOrdiniCanale | null;
}

const MODO_IGNOTO: ModoDalCanale = { alCambio: null, freno: null, dalNow: null };

export interface StatoBoardCanale {
    stato: LocalStatus;
    tabellone: Tabellone | null;
    /** l'ultimo `board_mercato` del tipo scelto; null = non ancora arrivato */
    mercato: MercatoScelto | null;
    /** la richiesta `board_mercato` e' stata rifiutata o non e' partita */
    erroreMercato: string | null;
    modo: ModoDalCanale;
}

function aggiornaAlCambio(p: ModoDalCanale, d: unknown): ModoDalCanale {
    const m = leggiModoOrdiniCanale(d);
    if (m == null) return p;
    const nuovo = piuRecente(p.alCambio, m);
    // vince il messaggio piu' recente, INTERO: modo e freno insieme
    return nuovo === p.alCambio ? p : { ...p, alCambio: nuovo, freno: frenoDa(d) };
}

const helloModo = (h: unknown): unknown => (h && typeof h === 'object'
    ? (h as Record<string, unknown>).modo_ordini : null);

// ------------------------------------------------------- memoria per sport
interface Memoria {
    tabellone: Tabellone | null;
    modo: ModoDalCanale;
    ascolta: Set<() => void>;
}

const memorie = new Map<SportBoard, Memoria>();

function memoria(sport: SportBoard): Memoria {
    const gia = memorie.get(sport);
    if (gia) return gia;
    const ch = getLocalChannel(sport);
    const m: Memoria = {
        tabellone: null,
        modo: aggiornaAlCambio(MODO_IGNOTO, helloModo(ch.getHello())),
        ascolta: new Set(),
    };
    const avvisa = () => { for (const f of m.ascolta) f(); };
    ch.subscribe('board', (d) => {
        const t = leggiBoard(d, sport);
        if (t) { m.tabellone = t; avvisa(); }
    });
    ch.subscribe('hello', (d) => { m.modo = aggiornaAlCambio(m.modo, helloModo(d)); avvisa(); });
    ch.subscribe('modo_ordini', (d) => { m.modo = aggiornaAlCambio(m.modo, d); avvisa(); });
    ch.subscribe('now', (d) => {
        const n = leggiModoDalNow(d);
        if (!n || (m.modo.dalNow != null && m.modo.dalNow.ms >= n.ms)) return;
        m.modo = { ...m.modo, dalNow: n };
        avvisa();
    });
    ch.onStatus((st) => {
        if (st === 'connected') return;
        // canale caduto: niente di cio' che sapevamo vale ancora
        m.tabellone = null;
        m.modo = MODO_IGNOTO;
        avvisa();
    });
    memorie.set(sport, m);
    return m;
}

/**
 * La pagina la chiama per ENTRAMBI gli sport al montaggio: cio' che arriva
 * sulla scheda non aperta (il tabellone, il modo ordini al cambio) resta in
 * memoria per quando la si apre. Idempotente; nessuna connessione in piu'
 * (i due canali la pagina li apre gia' per i pallini di stato delle schede).
 */
export function avviaMemoriaBoard(sport: SportBoard): void {
    memoria(sport);
}

/** SOLO PER I TEST: dimentica le memorie (insieme a __resetLocalChannels). */
export function __resetBoardMemoria(): void {
    memorie.clear();
}

export function useBoardCanale(sport: SportBoard, tipo: string): StatoBoardCanale {
    const stato = useLocalStatus(sport);
    const [vista, setVista] = useState(() => {
        const m = memoria(sport);
        return { tabellone: m.tabellone, modo: m.modo };
    });
    const [mercato, setMercato] = useState<MercatoScelto | null>(null);
    const [erroreMercato, setErroreMercato] = useState<string | null>(null);

    // tabellone e modo ordini: dalla memoria dello sport
    useEffect(() => {
        const m = memoria(sport);
        const copia = () => setVista({ tabellone: m.tabellone, modo: m.modo });
        copia();
        m.ascolta.add(copia);
        return () => { m.ascolta.delete(copia); };
    }, [sport]);

    // push del mercato scelto (solo il tipo scelto; il resto si ignora)
    useEffect(() => {
        setMercato(null);
        setErroreMercato(null);
        if (tipo === MATCH_ODDS) return undefined;
        const ch = getLocalChannel(sport);
        const offMercato = ch.subscribe('board_mercato', (d) => {
            const m = leggiBoardMercato(d);
            if (m && m.market_type === tipo) setMercato(m);
        });
        const offStato = ch.onStatus((st) => { if (st !== 'connected') setMercato(null); });
        return () => { offMercato(); offStato(); };
    }, [sport, tipo]);

    // la richiesta: subito, poi ogni 30 s, e di nuovo a ogni riconnessione
    useEffect(() => {
        if (tipo === MATCH_ODDS || stato !== 'connected') return undefined;
        let vivo = true;
        const chiedi = () => {
            getLocalChannel(sport).request('board_mercato', { market_type: tipo }).then((res) => {
                if (!vivo) return;
                setErroreMercato(res.ok ? null : (res.e ?? 'richiesta rifiutata dal runner'));
            }, () => {
                // trasporto (timeout/caduta): il messaggio del canale parla di
                // ordini, qui e' una lettura -> si dice semplicemente cosa e' successo
                if (!vivo) return;
                setErroreMercato('la richiesta non ha avuto risposta dal canale locale');
            });
        };
        chiedi();
        const t = window.setInterval(chiedi, RINNOVO_MERCATO_MS);
        return () => { vivo = false; window.clearInterval(t); };
    }, [sport, tipo, stato]);

    return { stato, tabellone: vista.tabellone, mercato, erroreMercato, modo: vista.modo };
}
