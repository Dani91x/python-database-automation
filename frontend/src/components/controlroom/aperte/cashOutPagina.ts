// ============================================================================
// cashOutPagina.ts - 08/10 (cantiere W1): le regole PURE della pagina «Cash Out»
// (`pages/CashOut.tsx`). Niente React, niente letture: solo i dati che
// `useControlRoom()` ha gia' in memoria (posizioni, operazioni, partite di
// Mike, programma dello scanner, ordini del conto fuori dai bot).
//
// Cosa decide, e da dove:
//   * QUALI partite: `raggruppaAperte` (la stessa della scheda «Posizioni
//     aperte», fonte unica `vm.posizioni`) + le partite che hanno SOLO ordini
//     del conto fuori dai bot (`vm.ordiniConto`), che prima non comparivano;
//   * LA FASE (in gioco / pre-match): fonte unica `PartitaGiornata.stato`
//     (flag `inplay` dello scanner, `lib/controlRoom.ts::statoPartita`); per una
//     partita fuori dal programma, l'orario che i dati del bot gia' portano
//     (Mike: `ko_at` e `live.inplay`; Omega: `kickoff` della riga). Fase non
//     ricavabile = Pre-match con «orario non dichiarato»: mai una scatola che
//     sparisce;
//   * LA SEZIONE (08/10 sera, D-6): In gioco, Pre-match, Concluse (Match Odds
//     CHIUSO, posizioni da regolare): `sezioneScatola`;
//   * cosa DICE il pulsante di una gamba dei bot: il comando di oggi
//     (`chiudiRiga.ts`) chiude per PARTITA Mike, per partita e mercato i 4 bot
//     tennis, per SESSIONE lo scalper; Omega e Safe la sola riga;
//   * le gambe degli ordini fuori dai bot per la matematica UNICA del cash out
//     (`lib/cashOutPartita.ts`): solo l'abbinato, LIVE (sono soldi veri).
// ============================================================================
import { BOT_LABEL, isBotTennis, type GruppoCampionato, type PartitaGiornata } from '@/lib/controlRoom';
import type { MikeEvent } from '@/lib/mike';
import { r2, type GambaViva } from '@/lib/cashOutPartita';
import type { SintesiCashOut } from '@/components/controlroom/useCashOutPartita';
import type { OrdineContoFuoriBot } from '@/lib/liveOrders';
import type { OrdiniContoStato } from '@/components/controlroom/ordiniConto';
import type { OperazionePartita, PosizioneAperta } from '@/components/controlroom/useControlRoom';
import { raggruppaAperte } from '@/components/controlroom/aperte/PosizioniAperte';

export type SportScatola = 'calcio' | 'tennis';
export type FaseScatola = 'gioco' | 'pre';

/**
 * Perche' la scatola sta in quella sezione:
 *  - `in-gioco`: in gioco (scanner `inplay`, o il servizio di Mike per una
 *    partita fuori programma);
 *  - `conclusa`: Betfair ha CHIUSO il Match Odds, posizioni da regolare;
 *  - `fischio-fra`: il fischio deve ancora arrivare;
 *  - `fischio-passato`: orario passato e il feed dice NON in gioco;
 *  - `orario-passato`: orario passato, e nessun dato dice se e' in gioco;
 *  - `orario-non-dichiarato`: nessun dato in memoria porta l'orario.
 */
export type NotaFase = 'in-gioco' | 'conclusa' | 'fischio-fra' | 'fischio-passato' | 'orario-passato' | 'orario-non-dichiarato';

export interface FaseEvento {
    fase: FaseScatola;
    nota: NotaFase;
    /** istante del fischio (ms epoch); null = non dichiarato */
    koMs: number | null;
    /** chi ha dato la fase: scanner (programma), Mike, la riga del bot, nessuno */
    fonte: 'scanner' | 'mike' | 'bot' | null;
}

const msDa = (s: string | null | undefined): number | null => {
    if (!s) return null;
    const t = Date.parse(s);
    return Number.isFinite(t) ? t : null;
};

/** La fase di UNA partita con posizioni (regole in testa al file). */
export function faseEvento(
    partita: PartitaGiornata | null,
    mike: MikeEvent | null,
    righe: readonly Pick<OperazionePartita, 'koAt'>[],
    nowMs: number,
): FaseEvento {
    if (partita) {
        // review finale 30/09 (R2-A1): «conclusa» solo se Betfair ha CHIUSO il Match Odds.
        // 08/10 sera (D-6): il Match Odds CHIUSO viene PRIMA di ogni altra fase: e'
        // lo stato definitivo di Betfair, e TUTTE le partite col mercato chiuso
        // vanno nella sezione «Concluse» (un `inplay` ancora acceso nel feed non
        // la riporta «in gioco»). `fase` resta 'gioco': per il filtro Pre-match /
        // Live una conclusa e' una partita gia' entrata in gioco, come prima.
        if (partita.statoMercato === 'CLOSED') return { fase: 'gioco', nota: 'conclusa', koMs: partita.koMs, fonte: 'scanner' };
        if (partita.stato === 'live') return { fase: 'gioco', nota: 'in-gioco', koMs: partita.koMs, fonte: 'scanner' };
        if (partita.stato === 'pre') return { fase: 'pre', nota: 'fischio-fra', koMs: partita.koMs, fonte: 'scanner' };
        return { fase: 'pre', nota: 'fischio-passato', koMs: partita.koMs, fonte: 'scanner' };
    }
    // fuori dal programma dello scanner: i dati del bot gia' in memoria
    if (mike?.live?.inplay === true) return { fase: 'gioco', nota: 'in-gioco', koMs: msDa(mike.ko_at), fonte: 'mike' };
    const koMike = msDa(mike?.ko_at);
    if (koMike != null) {
        if (koMike > nowMs) return { fase: 'pre', nota: 'fischio-fra', koMs: koMike, fonte: 'mike' };
        // `live` presente con `inplay` falso = il feed di Mike dice «non ancora in gioco»
        return { fase: 'pre', nota: mike?.live != null ? 'fischio-passato' : 'orario-passato', koMs: koMike, fonte: 'mike' };
    }
    for (const r of righe) {
        const ko = msDa(r.koAt ?? null);
        if (ko == null) continue;
        return { fase: 'pre', nota: ko > nowMs ? 'fischio-fra' : 'orario-passato', koMs: ko, fonte: 'bot' };
    }
    return { fase: 'pre', nota: 'orario-non-dichiarato', koMs: null, fonte: null };
}

/** Una partita della pagina: TUTTE le sue gambe aperte, dei bot e fuori dai bot. */
export interface ScatolaCashOut {
    eventId: string;
    /** la partita del programma di oggi; null = fuori programma (mai nascosta) */
    partita: PartitaGiornata | null;
    nome: string;
    sport: SportScatola;
    /** le posizioni APERTE dei bot (fonte unica `vm.posizioni`) */
    posizioni: PosizioneAperta[];
    /** le stesse posizioni come righe della scheda (`vm.operazioni`), stesso ordine */
    righe: OperazionePartita[];
    /** posizioni senza la loro riga nella scheda: restano con la riga compatta */
    orfane: PosizioneAperta[];
    /** TUTTE le righe della partita (aperture, chiusure, regolate): il cash out le netta */
    operazioni: OperazionePartita[];
    /** ordini del conto fuori dai bot (sito, app) su questa partita */
    fuoriBot: OrdineContoFuoriBot[];
    /** almeno una gamba non paper (live o modalita' non dichiarata) o un ordine del conto */
    live: boolean;
    fase: FaseEvento;
}

const chiaveRiga = (bot: string, id: number) => `${bot}|${id}`;

/**
 * Le scatole della pagina, una per partita. Prima quelle del programma
 * (ordine delle posizioni, come la scheda «Posizioni aperte»), poi le fuori
 * programma, poi le partite con SOLI ordini fuori dai bot.
 */
export function scatoleCashOut(args: {
    giornata: GruppoCampionato[];
    posizioni: readonly PosizioneAperta[];
    operazioni: ReadonlyMap<string, OperazionePartita[]>;
    mikeEventi: ReadonlyMap<string, MikeEvent>;
    ordiniConto: OrdiniContoStato | null | undefined;
    nowMs: number;
}): ScatolaCashOut[] {
    const partite = new Map<string, PartitaGiornata>();
    for (const g of args.giornata) for (const p of g.partite) partite.set(p.event_id, p);
    const conto = args.ordiniConto?.stato === 'letti' ? args.ordiniConto.perEvento : new Map<string, OrdineContoFuoriBot[]>();
    const eventi = raggruppaAperte(args.giornata, args.posizioni).map((e) => ({ ...e }));
    const visti = new Set(eventi.map((e) => e.eventId));
    for (const [eventId] of conto) {
        if (visti.has(eventId)) continue;
        visti.add(eventId);
        eventi.push({ eventId, partita: partite.get(eventId) ?? null, posizioni: [], live: true });
    }
    return eventi.map((e) => {
        const operazioni = args.operazioni.get(e.eventId) ?? [];
        const perChiave = new Map(operazioni.map((o) => [chiaveRiga(o.bot, o.id), o]));
        const righe: OperazionePartita[] = [];
        const orfane: PosizioneAperta[] = [];
        for (const p of e.posizioni) {
            const o = perChiave.get(chiaveRiga(p.bot, p.id));
            if (o) righe.push(o); else orfane.push(p);
        }
        const fuoriBot = conto.get(e.eventId) ?? [];
        const mike = args.mikeEventi.get(e.eventId) ?? null;
        const sport: SportScatola = e.partita
            ? (e.partita.sport === 'tennis' ? 'tennis' : 'calcio')
            : (e.posizioni.some((p) => isBotTennis(p.bot)) ? 'tennis' : 'calcio');
        return {
            eventId: e.eventId,
            partita: e.partita,
            nome: e.partita?.nome ?? e.posizioni[0]?.partita ?? fuoriBot.find((r) => r.event_name)?.event_name ?? e.eventId,
            sport,
            posizioni: e.posizioni,
            righe,
            orfane,
            operazioni,
            fuoriBot,
            live: e.live || fuoriBot.length > 0,
            fase: faseEvento(e.partita, mike, righe, args.nowMs),
        };
    });
}

/**
 * Filtri della testata: sport, fase e soldi, `null` = tutti (come le tessere
 * sport della Control Room). Soldi: una partita e' LIVE se ha almeno una gamba
 * non paper o un ordine del conto (`ScatolaCashOut.live`, stessa regola
 * fail-safe di `raggruppaAperte`), altrimenti e' PROVA.
 */
export function filtraScatole(
    scatole: readonly ScatolaCashOut[],
    filtro: { sport: SportScatola | null; fase: 'pre' | 'live' | null; soldi?: 'live' | 'prova' | null },
): ScatolaCashOut[] {
    const soldi = filtro.soldi ?? null;
    return scatole.filter((s) => (filtro.sport == null || s.sport === filtro.sport)
        && (filtro.fase == null || (filtro.fase === 'live') === (s.fase.fase === 'gioco'))
        && (soldi == null || (soldi === 'live') === s.live));
}

// ---------------------------------------------------------------- riepilogo

/**
 * La cifra «se chiudo tutto adesso» di UNA modalita' sulle scatole mostrate,
 * dalle sintesi che le scatole hanno gia' calcolato (`useRiportaSintesi`):
 *  - `calcolo`: almeno una scatola mostrata non ha ancora riportato la sua cifra;
 *  - `non-calcolabile`: almeno una scatola ha gambe in quella modalita' e la
 *    sua cifra e' non calcolabile -> nessuna somma (una somma monca e' una
 *    bugia, come `CashOutGlobale`), coi motivi per partita;
 *  - `nessuna`: nessuna gamba abbinata in quella modalita';
 *  - `ok`: la somma al centesimo, l'eta' del prezzo piu' vecchio.
 */
export interface TotaleModalita {
    stato: 'calcolo' | 'non-calcolabile' | 'nessuna' | 'ok';
    netto: number | null;
    motivi: string[];
    etaPrezziS: number | null;
    etaIgnota: boolean;
}

export function totaleModalita(
    scatole: readonly { eventId: string; nome: string }[],
    sintesi: ReadonlyMap<string, SintesiCashOut | null>,
    modalita: 'live' | 'paper',
): TotaleModalita {
    const out: TotaleModalita = { stato: 'nessuna', netto: null, motivi: [], etaPrezziS: null, etaIgnota: false };
    let somma = 0;
    let conGambe = 0;
    for (const s of scatole) {
        if (!sintesi.has(s.eventId)) return { ...out, stato: 'calcolo' };
        const x = sintesi.get(s.eventId)?.[modalita];
        if (!x || (x.nGambe === 0 && x.mancanti.length === 0)) continue;
        conGambe += 1;
        if (x.netto == null) {
            out.motivi.push(`${s.nome}: ${x.mancanti.join('; ') || 'cifra non calcolabile'}`);
            continue;
        }
        somma += x.netto;
        if (x.etaIgnota) out.etaIgnota = true;
        if (x.etaPrezziS != null) out.etaPrezziS = Math.max(out.etaPrezziS ?? 0, x.etaPrezziS);
    }
    if (out.motivi.length > 0) return { ...out, stato: 'non-calcolabile' };
    if (conGambe === 0) return out;
    return { ...out, stato: 'ok', netto: r2(somma) };
}

/** Gambe aperte e partite per modalita' (mai sommate): gambe dei bot + selezioni abbinate fuori dai bot. */
export function contaPerModalita(scatole: readonly ScatolaCashOut[]): Record<'live' | 'paper', { gambe: number; partite: number }> {
    const out = { live: { gambe: 0, partite: 0 }, paper: { gambe: 0, partite: 0 } };
    for (const s of scatole) {
        const fuori = selezioniFuoriBot(s.fuoriBot).filter((x) => x.abbinato).length;
        const live = s.posizioni.filter((p) => p.modalita !== 'paper').length + fuori;
        const paper = s.posizioni.filter((p) => p.modalita === 'paper').length;
        out.live.gambe += live;
        out.paper.gambe += paper;
        if (live > 0) out.live.partite += 1;
        if (paper > 0) out.paper.partite += 1;
    }
    return out;
}

// ------------------------------------------------------------ sezioni (D-6)

/**
 * 08/10 sera (D-6, decisione dell'utente: «quelle concluse: crea una sezione
 * apposta e spostale li'»). La sezione di una scatola:
 *  - `concluse`: Betfair ha CHIUSO il Match Odds e ci sono ancora posizioni da
 *    regolare (TUTTE e SOLE le scatole con `nota === 'conclusa'`);
 *  - `gioco` / `pre`: la fase di sempre.
 * Ogni scatola sta in UNA sola sezione: il passaggio la sposta, non la toglie.
 */
export type SezioneScatola = 'gioco' | 'pre' | 'concluse';

export function sezioneScatola(s: Pick<ScatolaCashOut, 'fase'>): SezioneScatola {
    if (s.fase.nota === 'conclusa') return 'concluse';
    return s.fase.fase === 'gioco' ? 'gioco' : 'pre';
}

/** Il testo della fase di una conclusa, nella testata della scatola. */
export const TESTO_CONCLUSA = 'conclusa · posizioni da regolare';

/**
 * Perche' i pulsanti di cash out di una scatola conclusa sono spenti: col
 * Match Odds CHIUSO Betfair non accetta ordini, le posizioni le regola Betfair.
 * Lo stesso meccanismo dei pulsanti di soldi spenti (`motivoPrezziFermi`):
 * un testo, mai un `disabled` muto. `null` = la partita non e' conclusa.
 */
export function motivoCashOutConclusa(s: Pick<ScatolaCashOut, 'fase'>): string | null {
    return s.fase.nota === 'conclusa'
        ? 'partita conclusa: Betfair ha CHIUSO il mercato, il cash out non e\' possibile (le posizioni le regola Betfair)'
        : null;
}

/** Ordine dentro una sezione: prima le LIVE (soldi veri), poi per fischio (ignoto in fondo). */
export function ordinaScatole(scatole: readonly ScatolaCashOut[]): ScatolaCashOut[] {
    return [...scatole].sort((a, b) => {
        if (a.live !== b.live) return a.live ? -1 : 1;
        const ka = a.fase.koMs ?? Number.POSITIVE_INFINITY;
        const kb = b.fase.koMs ?? Number.POSITIVE_INFINITY;
        return ka - kb;
    });
}

/**
 * Cosa DICE il pulsante di una gamba dei bot (decisione dell'utente, 08/10):
 * il comando e' quello di oggi (`chiudiRiga.ts`), il testo dice quanto chiude.
 *  - Mike: tutta la sua posizione sulla PARTITA;
 *  - 4 bot tennis: la loro posizione sulla partita e su quel mercato;
 *  - scalper calcio: ferma la SESSIONE (tutta la sua posizione);
 *  - Omega e Safe: la sola riga.
 * Le gambe si contano fra le righe aperte della scatola, nella STESSA
 * modalita' (paper e live mai insieme).
 */
export function testoCashOutRiga(o: Pick<OperazionePartita, 'bot' | 'modalita' | 'marketId'>,
    righe: readonly Pick<OperazionePartita, 'bot' | 'modalita' | 'marketId'>[]): { etichetta: string; ambito: string } {
    const nome = BOT_LABEL[o.bot];
    if (o.bot === 'omega' || o.bot === 'safe') return { etichetta: 'Cash out', ambito: 'solo questa gamba' };
    if (o.bot === 'scalper') return { etichetta: `Cash out ${nome}`, ambito: 'ferma la sessione: tutta la sua posizione' };
    const n = righe.filter((r) => r.bot === o.bot && r.modalita === o.modalita
        && (o.bot === 'mike' || r.marketId === o.marketId)).length;
    const dove = o.bot === 'mike' ? '' : ' su questo mercato';
    return {
        etichetta: `Cash out ${nome}`,
        ambito: n > 1 ? `tutte le ${n} gambe di ${nome}${dove}` : `la gamba di ${nome}${dove}: tutta la sua posizione`,
    };
}

/** Chi ha fatto l'ordine fuori dai bot: «Sito» (trovato sul conto) o «App» (dal ladder). */
export function origineFuoriBot(r: Pick<OrdineContoFuoriBot, 'source'>): 'Sito' | 'App' {
    return r.source === 'runner' ? 'App' : 'Sito';
}

/** Gli ordini fuori dai bot per SELEZIONE: il comando del contratto chiude per selezione. */
export interface SelezioneFuoriBot {
    chiave: string;
    marketId: string;
    selectionId: number;
    selezione: string | null;
    mercato: string | null;
    ordini: OrdineContoFuoriBot[];
    origini: ('Sito' | 'App')[];
    /** qualcosa di abbinato: senza, il green-up non ha niente da chiudere */
    abbinato: boolean;
}

export function selezioniFuoriBot(righe: readonly OrdineContoFuoriBot[]): SelezioneFuoriBot[] {
    const out = new Map<string, SelezioneFuoriBot>();
    for (const r of righe) {
        const k = `${r.market_id}|${r.selection_id}`;
        const s = out.get(k) ?? {
            chiave: k, marketId: String(r.market_id), selectionId: Number(r.selection_id),
            selezione: null, mercato: null, ordini: [], origini: [], abbinato: false,
        };
        s.ordini.push(r);
        s.selezione = s.selezione ?? r.selection_name;
        s.mercato = s.mercato ?? r.market_name;
        const o = origineFuoriBot(r);
        if (!s.origini.includes(o)) s.origini.push(o);
        if (r.price_matched != null && r.size_matched > 0) s.abbinato = true;
        out.set(k, s);
    }
    return Array.from(out.values());
}

/**
 * Gli ordini fuori dai bot come gambe della matematica UNICA del cash out
 * (`lib/cashOutPartita.ts`): solo l'ABBINATO (`price_matched` nullo = nulla
 * abbinato, mai una quota), sempre LIVE. `dueEsiti` = stessa regola delle
 * gambe dei bot della partita.
 */
export function gambeFuoriBot(
    righe: readonly OrdineContoFuoriBot[], dueEsiti?: (marketId: string) => boolean,
): GambaViva[] {
    const out: GambaViva[] = [];
    for (const r of righe) {
        if (r.price_matched == null || !(r.size_matched > 0)) continue;
        const marketId = String(r.market_id);
        out.push({
            id: `conto ${r.bet_id}`, bot: origineFuoriBot(r), modalita: 'live',
            marketId, selectionId: Number(r.selection_id), selezione: r.selection_name,
            lato: r.side === 'LAY' ? 'lay' : 'back',
            abbinato: r.size_matched, prezzoMedio: r.price_matched,
            // l'aliquota del conto non arriva con l'ordine: ripiego 5 % dichiarato dalla matematica
            aliquota: null,
            dueEsiti: dueEsiti?.(marketId) === true,
        });
    }
    return out;
}
