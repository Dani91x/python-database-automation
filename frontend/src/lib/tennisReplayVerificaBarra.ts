// ============================================================================
// tennisReplayVerificaBarra - VERIFICATORE della barra del REPLAY TENNIS
// (gemello tennis di `replayVerificaBarraCalcio.ts`; il calcio non lo usa).
//
// Ordine dell'utente (07/10/2026): la coerenza barra / simboli / tabellone e' uno
// standard per tutte le partite, presenti e future; il Replay Tennis ha le stesse
// funzioni del Match Replay, quindi anche questo controllo.
//
// DUE LIVELLI, come il calcio:
//  1. la barra COSI' COME LA DISEGNA LA PAGINA `TennisReplay.tsx`: passi
//     (`costruisciTimeline`), inizio del gioco (`inizioInGioco` + `indiceDiPasso`),
//     simboli (`simboliTennis`) e segmenti di sospensione (`sospesoPerPasso`) sono
//     calcolati con le STESSE funzioni della pagina, poi passati ai controlli
//     generici (`verificaBarraGenerica`: estremi, ordine, simboli fuori barra o prima
//     del loro istante, inizio del gioco, sospensioni, buchi), che hanno oracoli
//     scritti dalla regola con un codice diverso;
//  2. CONTROLLI DI DOMINIO del tennis, con oracoli indipendenti dal convertitore:
//     - ogni evento di gioco delle righe di punteggio (break, inizio/fine set,
//       tie-break, fine partita, salto) ha il SUO simbolo sulla barra e ogni simbolo
//       ha il suo evento (l'unico simbolo senza riga e' il passaggio in gioco);
//     - un break dichiarato e' un game vinto da chi RICEVEVA nella riga precedente
//       (fuori dal tie-break), e un game vinto da chi riceveva e' un break;
//     - una fine set dichiarata fa salire i set di uno e un set in piu' e' dichiarato;
//     - un tie-break dichiarato passa il tabellone in tie-break;
//     - i set vinti non scendono mai.
//
// GRAVITA (comuni): errore = la barra o i simboli mentono; avviso = il dato del
// punteggio non torna (da guardare a mano); nota = fatto dichiarato.
// ============================================================================
import type { TennisScoreState } from '@/lib/tennis';
import {
    costruisciTimeline, framesPerMercato, indiceDiPasso, inizioInGioco, ordinaPunteggio, simboliTennis, sospesoPerPasso,
    type TennisReplayData, type TennisScoreRow, type TipoSimbolo,
} from '@/lib/tennisReplay';
import {
    BUCKET_BARRA_MS, creaRilievo, esitoDaRilievi, idMercatiSospensione, oraUtc, verificaBarraGenerica,
    type CodiceRilievo, type EsitoVerificaBarra, type EstremiRegistrazione, type GravitaRilievo, type Rilievo,
    type SimboloBarra,
} from '@/lib/replayVerificaBarra';

/** evento di gioco della riga di punteggio -> simbolo della barra (regola del convertitore) */
const SIMBOLO_DI_EVENTO: Readonly<Record<string, TipoSimbolo>> = {
    BREAK: 'break', SET_END: 'set_end', SET_START: 'set_start', TIEBREAK_START: 'tiebreak',
    MATCH_END: 'match_end', SALTO: 'salto',
};

export interface OpzioniVerificaTennis {
    /** estremi della registrazione dichiarati dal server, se la pagina li ha */
    estremi?: EstremiRegistrazione | null;
    /** sostituisce `simboliTennis` (solo per la falsificazione nei test) */
    simboli?: typeof simboliTennis;
}

/** Il testo dei controlli generici parla di "calcio d'inizio": nel tennis e' l'inizio del gioco. */
function allaTennis(r: Rilievo): Rilievo {
    return { ...r, spiegazione: r.spiegazione.replace(/calcio d'inizio/g, 'inizio del gioco').replace(/fischio d'inizio/g, 'primo punto') };
}

/** chi ha vinto il passaggio fra due righe (1|2), oppure null se nessuno o non deducibile */
function vincitore(prev: TennisScoreState, cur: TennisScoreState): 1 | 2 | null {
    const ds1 = cur.sets.p1 - prev.sets.p1;
    const ds2 = cur.sets.p2 - prev.sets.p2;
    if (ds1 < 0 || ds2 < 0 || ds1 + ds2 > 1) return null;
    if (ds1 === 1) return 1;
    if (ds2 === 1) return 2;
    const dg1 = cur.games.p1 - prev.games.p1;
    const dg2 = cur.games.p2 - prev.games.p2;
    if (dg1 === 1 && dg2 === 0) return 1;
    if (dg1 === 0 && dg2 === 1) return 2;
    return null;
}

export function verificaBarraTennis(dati: TennisReplayData, opzioni: OpzioniVerificaTennis = {}): EsitoVerificaBarra {
    const frames = dati.frames ?? [];
    const righe: TennisScoreRow[] = ordinaPunteggio(dati.score_timeline ?? []);
    const p1 = dati.event?.player1_name ?? '';
    const p2 = dati.event?.player2_name ?? '';

    // --- la barra come la disegna la pagina (stesse funzioni) ---
    const passi = costruisciTimeline(frames, BUCKET_BARRA_MS);
    const inGiocoTs = inizioInGioco(frames);
    const kickoffIndex = inGiocoTs && passi.length > 0 ? indiceDiPasso(passi, inGiocoTs) : 0;
    const simboliPagina = (opzioni.simboli ?? simboliTennis)(righe, passi, p1, p2, inGiocoTs);
    const sospesi = sospesoPerPasso(passi, framesPerMercato(frames), dati.markets ?? []);
    const simboli: SimboloBarra[] = simboliPagina.map(s => ({
        ts: s.ts, pctLeft: s.pctLeft, kind: s.tipo, minute: null, label: s.label,
    }));

    const rilievi: Rilievo[] = verificaBarraGenerica({
        passi, simboli, frames, kickoffTs: inGiocoTs, kickoffIndex, sospesi,
        mercatiSospensione: idMercatiSospensione(dati.markets ?? []),
        estremi: opzioni.estremi ?? null,
        ambito: 'tennis',
    }).map(allaTennis);

    const R = (codice: CodiceRilievo, gravita: GravitaRilievo, spiegazione: string, istante: string | null = null, occorrenze = 1) => {
        rilievi.push(creaRilievo(codice, gravita, spiegazione, { ambito: 'tennis', istante, occorrenze }));
    };

    if (frames.length > 0 && passi.length > 0) {
        // --- simboli <-> eventi delle righe di punteggio ---
        const chiave = (ts: string, tipo: string) => `${ts}|${tipo}`;
        const attesi = new Map<string, number>();
        for (const r of righe) {
            for (const ev of r.event_types ?? []) {
                const tipo = SIMBOLO_DI_EVENTO[ev];
                if (tipo) attesi.set(chiave(r.ts, tipo), (attesi.get(chiave(r.ts, tipo)) ?? 0) + 1);
            }
        }
        const disegnati = new Map<string, number>();
        let inplay = 0;
        for (const s of simboliPagina) {
            if (s.tipo === 'inplay') { inplay += 1; continue; }
            disegnati.set(chiave(s.ts, s.tipo), (disegnati.get(chiave(s.ts, s.tipo)) ?? 0) + 1);
        }
        for (const [k, n] of attesi) {
            const d = disegnati.get(k) ?? 0;
            if (d < n) {
                const [ts, tipo] = k.split('|');
                R('TENNIS_EVENTO_SENZA_SIMBOLO', 'errore',
                    `Il punteggio registrato dichiara "${tipo}" alle ${oraUtc(ts)} ma la barra non ne disegna il simbolo.`, ts, n - d);
            }
        }
        for (const [k, d] of disegnati) {
            const n = attesi.get(k) ?? 0;
            if (d > n) {
                const [ts, tipo] = k.split('|');
                R('TENNIS_SIMBOLO_SENZA_EVENTO', 'errore',
                    `La barra disegna "${tipo}" alle ${oraUtc(ts)} ma nessuna riga di punteggio registrata dichiara quel fatto.`, ts, d - n);
            }
        }
        const inizioDopoPrimoPasso = inGiocoTs != null && inGiocoTs > passi[0].ts;
        if (inizioDopoPrimoPasso && inplay !== 1) {
            R('TENNIS_INPLAY_SIMBOLO', 'errore',
                `La registrazione parte prima del gioco ma la barra ha ${inplay} simboli di passaggio in gioco invece di uno (primo frame in gioco alle ${oraUtc(inGiocoTs)}).`,
                inGiocoTs);
        } else if (!inizioDopoPrimoPasso && inplay > 0) {
            R('TENNIS_INPLAY_SIMBOLO', 'errore',
                'La barra disegna un passaggio in gioco ma la registrazione parte gia\' in gioco.', inGiocoTs);
        }
    }

    // --- controlli di dominio sul punteggio (oracoli dalla regola del tennis) ---
    if (righe.length === 0) {
        R('PUNTEGGIO_ASSENTE', 'nota', 'La partita non ha righe di punteggio registrate: la barra non ha simboli di gioco.');
    }
    let salti = 0;
    for (let i = 1; i < righe.length; i++) {
        const prev = righe[i - 1].score;
        const cur = righe[i].score;
        const ts = righe[i].ts;
        const ev = new Set(righe[i].event_types ?? []);
        if (ev.has('SALTO')) salti += 1;
        if (cur.sets.p1 < prev.sets.p1 || cur.sets.p2 < prev.sets.p2) {
            R('TENNIS_SET_SCENDONO', 'avviso',
                `I set vinti scendono alle ${oraUtc(ts)} (${prev.sets.p1}-${prev.sets.p2} -> ${cur.sets.p1}-${cur.sets.p2}): il feed del punteggio ha corretto o perso dati.`, ts);
            continue;
        }
        const dsTot = cur.sets.p1 + cur.sets.p2 - (prev.sets.p1 + prev.sets.p2);
        if (ev.has('SET_END') && dsTot < 1) {
            R('TENNIS_FINE_SET_INCOERENTE', 'avviso',
                `Fine set dichiarata alle ${oraUtc(ts)} ma i set vinti non salgono (${prev.sets.p1}-${prev.sets.p2} -> ${cur.sets.p1}-${cur.sets.p2}).`, ts);
        } else if (!ev.has('SET_END') && dsTot >= 1) {
            R('TENNIS_FINE_SET_INCOERENTE', 'avviso',
                `I set vinti salgono alle ${oraUtc(ts)} (${prev.sets.p1}-${prev.sets.p2} -> ${cur.sets.p1}-${cur.sets.p2}) ma la fine del set non e' dichiarata: manca il simbolo.`, ts);
        }
        if (ev.has('TIEBREAK_START') && !(cur.tiebreak && !prev.tiebreak)) {
            R('TENNIS_TIEBREAK_INCOERENTE', 'avviso',
                `Tie-break dichiarato alle ${oraUtc(ts)} ma il tabellone ${cur.tiebreak ? 'era gia\' in tie-break' : 'non e\' in tie-break'}.`, ts);
        } else if (!ev.has('TIEBREAK_START') && cur.tiebreak && !prev.tiebreak) {
            R('TENNIS_TIEBREAK_INCOERENTE', 'avviso',
                `Il tabellone entra in tie-break alle ${oraUtc(ts)} ma il tie-break non e' dichiarato: manca il simbolo.`, ts);
        }
        if (ev.has('SALTO')) continue; // piu' game fra due righe: nessun break deducibile (dichiarato)
        const v = vincitore(prev, cur);
        const servizio = prev.server;
        const breakAtteso = v != null && (servizio === 1 || servizio === 2) && servizio !== v && !prev.tiebreak;
        if (ev.has('BREAK') && !breakAtteso) {
            R('TENNIS_BREAK_INCOERENTE', 'avviso',
                `Break dichiarato alle ${oraUtc(ts)} ma il game ${v == null ? 'non ha un vincitore deducibile' : `e' vinto da chi serviva (${v === 1 ? 'giocatore 1' : 'giocatore 2'})`}${prev.tiebreak ? ' o era un tie-break' : ''}.`, ts);
        } else if (!ev.has('BREAK') && breakAtteso) {
            R('TENNIS_BREAK_INCOERENTE', 'avviso',
                `Alle ${oraUtc(ts)} il game e' vinto da chi riceveva (giocatore ${v}) ma il break non e' dichiarato: manca il simbolo.`, ts);
        }
    }
    if (salti > 0) {
        R('TENNIS_SALTO', 'nota',
            `${salti} passaggi del punteggio saltano piu' di un game fra due righe registrate: li segna il simbolo "buco", nessun break e' dedotto li'.`, null, salti);
    }

    const contaSimboli: Record<string, number> = {};
    for (const s of simboli) contaSimboli[s.kind] = (contaSimboli[s.kind] ?? 0) + 1;
    return esitoDaRilievi(rilievi, {
        passi: passi.length, frames: frames.length, simboli: contaSimboli,
        righePunteggio: righe.length,
        righeEvento: righe.filter(r => (r.event_types ?? []).length > 0).length,
    });
}
