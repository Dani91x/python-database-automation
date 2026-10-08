// ============================================================================
// PosizioniAperte.tsx - 08/10 (cantiere W1, pagina «Cash Out»): i pezzi della
// scheda «Posizioni aperte» della Control Room, SPOSTATI qui dal file della
// pagina (`pages/ControlRoom.tsx`, prima :1381-1740) perche' li usa anche la
// pagina Cash Out. Codice, testid e comportamento IDENTICI: nessuna riga di
// logica cambiata, solo `export` davanti a cio' che serve fuori.
//
// In piu' (stesso spostamento): `ContestiRigheBanco`, i DUE contesti che la
// Control Room metteva attorno alle schede (`ChiusuraRigaContext` col valore
// di :176-186 e `OrdiniContoContext` di :789). Senza, il «Chiudi» di riga, il
// «Chiudi tutte le gambe» di `CashOutGlobale` e gli ordini del conto non si
// montano: le due pagine li prendono da qui, una scrittura sola.
// ============================================================================
import { useContext, useMemo, type ReactNode } from 'react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { EmptyState } from '@/components/trading/EmptyState';
import type { SportKey } from '@/components/controlroom/SplitSport';
import { SchedaPartita } from '@/components/controlroom/SchedaPartita';
import { NomiPartita } from '@/components/controlroom/NomiPartita';
import { CashOutGlobalePartita } from '@/components/controlroom/CashOutGlobale';
import { dueEsitiMike, dueEsitiPartita } from '@/lib/cashOutPartita';
import { OrdiniContoPartita, OrdiniContoContext } from '@/components/controlroom/OrdiniContoPartita';
import type { MikeEvent } from '@/lib/mike';
import {
    statoPartitaAperta, type StatoPartitaAperta, type EsitoStatoPartita,
} from '@/components/controlroom/aperte/statoPartitaAperta';
import { pnlClass } from '@/lib/tradeStatus';
import { fmtMoney, fmtOdds, fmtTime, DASH } from '@/lib/format';
import {
    BOT_LABEL, isBotTennis,
    type Bot, type GruppoCampionato, type PartitaGiornata,
} from '@/lib/controlRoom';
import type { StatoChiusuraEvento } from '@/lib/chiusuraUtente';
import type {
    ControlRoomVM, PosizioneAperta, OperazionePartita,
} from '@/components/controlroom/useControlRoom';
import { BottoneChiudiRiga, ChiusuraRigaContext, type ChiusuraRigaApi } from '@/components/controlroom/BottoneChiudiRiga';
import { prezzoAlClic, useChiusuraAlMs } from '@/components/controlroom/useChiusuraAlMs';
import type { SorgenteLadder } from '@/components/controlroom/usePrezzoAlMs';
import { sorgenteLadderAlMs } from '@/lib/localTransport';
import { StatoOrdineCompatto } from '@/components/trading/StatoOrdine';
import {
    BadgeStato, Ingresso, QuotaOra, PnlVivo, Copertura, Greenup, ModelloP, Uscita,
} from '@/components/controlroom/DettaglioRigaView';

// --------------------------------------------------------------- vocabolario
// Le parole del trader, in italiano, in un posto solo.

// Lato: le stesse parole e gli stessi colori del resto della piattaforma —
// BACK sky, LAY **rose** (non pink: il design system dichiara rose, e due
// rosa diversi per la stessa cosa rallentano la lettura).
const LATO_LABEL: Record<'back' | 'lay', string> = { back: 'BACK', lay: 'LAY' };

const LATO_CLS: Record<'back' | 'lay', string> = {
    back: 'bg-sky-500/15 text-sky-300 border-sky-500/30',
    lay: 'bg-rose-500/15 text-rose-300 border-rose-500/30',
};

export const BOT_CLS: Record<Bot, string> = {
    omega: 'text-primary',
    safe: 'text-secondary',
    mike: 'text-teal-300',
    scalper: 'text-violet-300',
    // i quattro del tennis, stessa famiglia di colore della scheda partita
    tennis_scalper: 'text-amber-300',
    tennis_pro: 'text-amber-200',
    tennis_flb: 'text-orange-300',
    tennis_swing: 'text-yellow-300',
};

// ----------------------------------------------------- contesti delle righe

// 25/09 (residui B17) - la sorgente del ladder al ms per il "se chiudo ora"
// delle righe (la stessa delle schede delle proposte)
export const SORGENTE_LADDER_RIGHE: SorgenteLadder = (sport) => sorgenteLadderAlMs(sport);

/**
 * I due contesti delle righe, come la Control Room li metteva attorno alle sue
 * schede: il «Chiudi» per singolo bot (B16) e gli ordini del conto fuori dai
 * bot (W_T/P14). Il contesto non disegna niente: porta solo comandi e dati.
 */
export function ContestiRigheBanco({ vm, children }: { vm: ControlRoomVM; children: ReactNode }) {
    // B16 (24/09) — il «Chiudi» per singolo bot, portato alle righe dal contesto
    const chiusuraRiga = useMemo<ChiusuraRigaApi>(
        () => ({
            chiudi: vm.chiudi, stato: vm.statoChiusuraRiga,
            // B17 (25/09) — l'esito dell'ordine dopo il clic (assenti nei finti storici)
            esito: vm.esitoChiusuraRiga, seguiClic: vm.seguiClic, esitoOrdine: vm.esitoOrdine,
            esitiOrdini: vm.esitiOrdini,
            // 25/09 (residui B17) - "Chiudi" di riga al prezzo del ms
            sorgenteLadder: SORGENTE_LADDER_RIGHE,
        }),
        [vm.chiudi, vm.statoChiusuraRiga, vm.esitoChiusuraRiga, vm.seguiClic, vm.esitoOrdine, vm.esitiOrdini],
    );
    return (
        <ChiusuraRigaContext.Provider value={chiusuraRiga}>
            {/* W_T/P14: gli ordini del conto fuori dai bot per le schede
                (assenti dal modello di vista = nessun contesto, niente a schermo) */}
            <OrdiniContoContext.Provider value={vm.ordiniConto ? { stato: vm.ordiniConto, nowMs: vm.nowMs } : null}>
                {children}
            </OrdiniContoContext.Provider>
        </ChiusuraRigaContext.Provider>
    );
}

// ------------------------------------------------------------- tab «Aperte»

/**
 * TASK 5 (18/09) — «Aperte» con la STESSA geometria di «Live»: `SchedaPartita`
 * per ogni partita del programma di oggi che ha una posizione (live o paper),
 * conservando ogni comando che offriva `ColonnaPosizioni`. Una posizione su
 * un evento SCONOSCIUTO al programma (fail-open: non deve MAI sparire) resta
 * visibile in fondo con la vecchia riga compatta, «Chiudi» compreso — perché
 * `SchedaPartita`/`AzioniPartita`/`CashOutPartita` offrono solo il cash-out
 * AGGREGATO di partita (`safe.onCashOut`), non la chiusura di UNA SOLA
 * posizione (`onChiudi(tradeId)`, che quindi resta qui, non perso).
 */
export function AperteTab({
    giornata, posizioni, sport, registrazioni, registratori, operazioni, mikeEventi, safe,
}: {
    giornata: GruppoCampionato[];
    posizioni: PosizioneAperta[];
    sport: SportKey | null;
    registrazioni: Set<string>;
    registratori: { calcio: boolean | null; tennis: boolean | null };
    operazioni: ControlRoomVM['operazioni'];
    mikeEventi?: ControlRoomVM['mikeEventi'];
    safe: {
        modalita: 'paper' | 'live' | null;
        statoChiusura: (eventId: string) => StatoChiusuraEvento;
        onCashOut: (eventId: string) => Promise<void>;
        onRiprendi: (eventId: string) => Promise<void>;
    };
}) {
    // `vm.posizioni` resta l'UNICA fonte di verità di "che cosa è aperto"
    // (stessa lista che alimenta il contatore della linguetta): qui si
    // raggruppa per partita SOLO per scegliere la geometria — una card
    // `SchedaPartita` se l'evento è nel programma di oggi, altrimenti la
    // riga compatta di sempre. Derivarla da `giornata.soldi.aperta` invece
    // di `posizioni` creerebbe una SECONDA fonte di verità, che può
    // divergere (es. la riga cambia prima che il programma la rilegga).
    // W_T/P15 (30/09): per PARTITA (evento), con la sua scheda se e' nel
    // programma, altrimenti la scheda "fuori programma" con la stessa grafica.
    // Una partita va fra le LIVE se ha almeno una gamba NON paper (una
    // modalita' non dichiarata potrebbe essere soldi veri: fail-safe).
    const eventi = useMemo(() => raggruppaAperte(giornata, posizioni), [giornata, posizioni]);
    const liveEv = eventi.filter((e) => e.live);
    const provaEv = eventi.filter((e) => !e.live);
    const gambeLive = posizioni.filter((p) => p.modalita === 'live').length;
    const vuoto = eventi.length === 0;

    const scheda = (e: EventoAperto, conStato: boolean) => {
        const ops = operazioni.get(e.eventId) ?? [];
        const mike = mikeEventi?.get(e.eventId) ?? null;
        return (
            <div key={e.eventId} className="space-y-1" data-testid={`cr-aperta-${e.eventId}`}>
                {conStato && (
                    <StatoPartitaRiga
                        esito={statoPartitaAperta(ops, {
                            // review finale 30/09 (R2-A1): «DA REGOLARE» solo se Betfair ha CHIUSO il
                            // Match Odds; «chiusa» da sola vale anche per ritardi e rinvii
                            chiusa: e.partita?.stato === 'chiusa' && e.partita?.statoMercato === 'CLOSED',
                            // review finale 30/09 (R2-4): nel tennis il Match Odds e' a DUE esiti
                            // (P1/P2 si nettano), come nella scheda in gioco
                            dueEsiti: dueEsitiPartita(e.partita?.sport === 'tennis' ? 'tennis' : 'calcio', e.partita?.marketId, dueEsitiMike(mike)),
                        })}
                        testId={`cr-aperta-stato-${e.eventId}`} />
                )}
                {e.partita ? (
                    <SchedaPartita
                        p={e.partita} scheda="aperte"
                        operazioni={ops}
                        mike={mike}
                        registra={registrazioni.has(e.eventId)}
                        registratoreVivo={registratori[e.partita.sport === 'tennis' ? 'tennis' : 'calcio']}
                        safe={{
                            modalita: safe.modalita,
                            chiusa: safe.statoChiusura(e.eventId),
                            onCashOut: safe.onCashOut,
                            onRiprendi: safe.onRiprendi,
                        }}
                    />
                ) : (
                    <SchedaFuoriProgramma posizioni={e.posizioni} operazioni={ops} mike={mike} />
                )}
            </div>
        );
    };

    return (
        <Card className="glass-card border-white/10 p-0 overflow-hidden" data-testid="cr-posizioni">
            <div className="px-3 py-2 border-b border-white/10 flex items-center justify-between">
                <span className="text-[11px] uppercase tracking-wider text-white/60">
                    Posizioni aperte{sport && <span className="text-white/35 normal-case tracking-normal"> · solo {sport}</span>}
                </span>
                <span className="text-[11px] text-white/40" data-testid="cr-aperte-conteggi">
                    <span className={liveEv.length ? 'text-red-300 font-semibold' : ''}>{liveEv.length} LIVE</span>
                    {' · '}{provaEv.length} prova
                </span>
            </div>

            {gambeLive > 0 && (
                <div className="px-3 py-1.5 border-b border-orange-500/30 bg-orange-500/10 text-[11px] text-orange-300"
                    data-testid="cr-aperte-banner-live">
                    {liveEv.length} {liveEv.length === 1 ? 'partita' : 'partite'} con posizione LIVE
                    {' · '}{gambeLive} {gambeLive === 1 ? 'gamba' : 'gambe'} con soldi veri
                </div>
            )}

            <div className="max-h-[calc(100vh-240px)] overflow-y-auto p-3 space-y-3">
                {vuoto && (
                    <EmptyState>{sport
                        ? `Nessuna posizione aperta sul ${sport}. Clicca di nuovo la tessera per rivedere tutti gli sport.`
                        : 'Nessuna posizione aperta. Quando un bot va a mercato, compare qui.'}</EmptyState>
                )}

                {liveEv.length > 0 && (
                    <section className="space-y-2" data-testid="cr-aperte-live">
                        <h3 className="text-[10px] uppercase tracking-wider font-bold text-red-300 flex items-center gap-2">
                            LIVE: soldi veri
                            <span className="font-mono px-1 rounded bg-red-500/20" data-testid="cr-aperte-live-conta">{liveEv.length}</span>
                        </h3>
                        {liveEv.map((e) => scheda(e, true))}
                    </section>
                )}

                {provaEv.length > 0 && (
                    <section className="space-y-2" data-testid="cr-aperte-prova">
                        <h3 className="text-[10px] uppercase tracking-wider text-white/40 flex items-center gap-2">
                            PROVA: simulato, mai sommato
                            <span className="font-mono px-1 rounded bg-white/10" data-testid="cr-aperte-prova-conta">{provaEv.length}</span>
                        </h3>
                        {provaEv.map((e) => scheda(e, false))}
                    </section>
                )}
            </div>
        </Card>
    );
}

/** W_T/P15: la linguetta «Posizioni aperte · 3 LIVE · 2 prova» (partite). */
export function ContaAperte({ posizioni }: { posizioni: readonly PosizioneAperta[] }) {
    const live = new Set<string>();
    const tutte = new Set<string>();
    for (const p of posizioni) {
        tutte.add(p.eventId);
        if (p.modalita !== 'paper') live.add(p.eventId);
    }
    const prova = tutte.size - live.size;
    return (
        <span className="ml-1.5 font-mono text-[10px] normal-case" data-testid="cr-tab-aperte-conta"
            title="partite con posizione aperta: LIVE (soldi veri) e in prova, mai sommate">
            <span className={live.size ? 'text-red-300 font-bold' : 'text-white/40'}>{live.size} LIVE</span>
            <span className="text-white/40">{' · '}{prova} prova</span>
        </span>
    );
}

/** W_T/P15: una partita con posizione (evento), dalla lista UNICA `vm.posizioni`. */
export interface EventoAperto {
    eventId: string;
    /** la partita del programma di oggi; null = fuori programma (mai nascosta) */
    partita: PartitaGiornata | null;
    posizioni: PosizioneAperta[];
    /** almeno una gamba non paper (live o modalita' non dichiarata) */
    live: boolean;
}

export function raggruppaAperte(giornata: GruppoCampionato[], posizioni: readonly PosizioneAperta[]): EventoAperto[] {
    const partiteMap = new Map<string, PartitaGiornata>();
    for (const g of giornata) for (const p of g.partite) partiteMap.set(p.event_id, p);
    const out = new Map<string, EventoAperto>();
    for (const p of posizioni) {
        const e = out.get(p.eventId) ?? {
            eventId: p.eventId, partita: partiteMap.get(p.eventId) ?? null, posizioni: [], live: false,
        };
        e.posizioni.push(p);
        if (p.modalita !== 'paper') e.live = true;
        out.set(p.eventId, e);
    }
    // prima quelle del programma (ordine delle posizioni), poi le fuori programma
    const tutte = Array.from(out.values());
    return [...tutte.filter((e) => e.partita), ...tutte.filter((e) => !e.partita)];
}

const STATO_APERTA_CLS: Record<StatoPartitaAperta, string> = {
    'A RISCHIO': 'bg-red-500/20 text-red-300 border-red-500/40',
    'IN VERDE': 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
    PAREGGIATA: 'bg-teal-500/15 text-teal-300 border-teal-500/40',
    'DA REGOLARE': 'bg-amber-500/15 text-amber-300 border-amber-500/40',
    'NON CALCOLABILE': 'bg-orange-500/15 text-orange-300 border-orange-500/40',
};

/** Lo stato della partita LIVE in una parola; i numeri nel title. */
export function StatoPartitaRiga({ esito, testId }: { esito: EsitoStatoPartita; testId: string }) {
    return (
        <div className="flex items-center gap-2 text-[10.5px]">
            <span className={`px-1.5 py-0.5 rounded border font-bold uppercase tracking-wider text-[9.5px] ${STATO_APERTA_CLS[esito.stato]}`}
                data-testid={testId} title={esito.dettaglio}>
                {esito.stato}
            </span>
            {esito.casoPeggiore != null && (
                <span className="text-white/45 font-mono tabular-nums" title="caso peggiore fra gli esiti, gambe LIVE dei bot (non i soldi fuori dai bot)">
                    caso peggiore {fmtMoney(esito.casoPeggiore, { signed: true })}
                </span>
            )}
        </div>
    );
}

/**
 * W_T/P15: una partita FUORI dal programma di oggi con la STESSA grafica delle
 * altre: nomi (`NomiPartita`, dal nome della riga del bot), riquadro del cash
 * out della partita (`CashOutGlobalePartita`, con le sue operazioni); sotto,
 * per gamba, la riga di sempre con il suo UNICO «Chiudi» (`RigaPosizioneOrfana`).
 */
export function SchedaFuoriProgramma({ posizioni, operazioni, mike }: {
    posizioni: PosizioneAperta[];
    operazioni: OperazionePartita[];
    mike: MikeEvent | null;
}) {
    const nome = posizioni[0]?.partita ?? DASH;
    const tennis = posizioni.some((p) => isBotTennis(p.bot));
    return (
        <Card className="glass-card border-white/10 p-0 overflow-hidden" data-testid="cr-scheda-fuori-programma">
            <div className="px-2.5 pt-2 flex items-start gap-2">
                <NomiPartita nome={nome} />
                <span className="text-[9.5px] uppercase tracking-wider text-white/35"
                    title="una posizione su un evento non presente nel programma di oggi: mai nascosta">
                    fuori dal programma di oggi
                </span>
            </div>
            <CashOutGlobalePartita sport={tennis ? 'tennis' : 'calcio'} operazioni={operazioni} mike={mike} />
            {posizioni[0] && <OrdiniContoPartita eventId={posizioni[0].eventId} sport={tennis ? 'tennis' : 'calcio'} />}
            {/* review finale 30/09 (R2-5): UNA riga per gamba, con UN solo «Chiudi»
                (`RigaPosizioneOrfana`, testid di sempre): prima la stessa gamba LIVE
                compariva due volte, con due pulsanti di chiusura */}
            <div className="p-2.5 space-y-2">
                {posizioni.map((p) => <RigaPosizioneOrfana key={`${p.bot}-${p.id}`} p={p} />)}
            </div>
        </Card>
    );
}

/** la vecchia card compatta di `ColonnaPosizioni` (18/09): sopravvive SOLO
 *  per le posizioni orfane (vedi `AperteTab`) — stesso markup, stessi
 *  testid, stesso comando "Chiudi" per singola posizione: nessuna
 *  regressione sul contenuto, solo sul quando compare. */
export function RigaPosizioneOrfana({ p }: {
    p: PosizioneAperta;
}) {
    // 25/09 (residui B17) - "chiudi ora" AL MS prima del clic (ripiego dichiarato)
    const ch = useChiusuraAlMs(p.chiusura, useContext(ChiusuraRigaContext)?.sorgenteLadder ?? null);
    return (
        <div className="rounded border border-white/10 bg-white/[0.02] px-2.5 py-2" data-testid="cr-posizione">
            <div className="flex items-baseline gap-2">
                <span className={`text-[10px] font-bold uppercase tracking-wider ${BOT_CLS[p.bot]}`}>{BOT_LABEL[p.bot]}</span>
                {p.modalita === 'live'
                    ? <Badge variant="outline" className="h-4 px-1 text-[9px] border-orange-500/40 text-orange-300">live</Badge>
                    : <Badge variant="outline" className="h-4 px-1 text-[9px] border-white/20 text-white/40">paper</Badge>}
                <span className="ml-auto font-mono text-[11px] text-white/40">{fmtTime(p.piazzataAt)}</span>
            </div>
            {/* W_T/P15: il nome della partita sta ora nella testata della scheda
                fuori programma (`NomiPartita`), non ripetuto per gamba */}
            <div className="flex items-baseline gap-2 mt-1 text-[11px] text-white/60">
                {p.lato && (
                    <span className={`px-1.5 py-0.5 rounded border text-[9px] font-bold uppercase tracking-wider ${LATO_CLS[p.lato]}`}>
                        {LATO_LABEL[p.lato]}
                    </span>
                )}
                <span className="truncate">{p.selezione ?? DASH}</span>
                <span className="font-mono ml-auto">{fmtOdds(p.prezzo)}</span>
            </div>
            <div className="text-[11px] text-white/40 mt-0.5">
                importo <span className="font-mono">{fmtMoney(p.size)}</span>
                {p.liability != null && <> · liability <span className="font-mono">{fmtMoney(p.liability)}</span></>}
            </div>
            {/* ── IL DETTAGLIO CHE LA SCHEDA DEL BOT MOSTRA GIÀ (17/09) ──
                chiesto/abbinato/residuo, quota di adesso e tick, minuto e
                punteggio d'ingresso, stato ricco, P&L vivo, green-up, modello.
                Tutto dalle stesse righe già in memoria: nessuna lettura in più. */}
            <div className="mt-1 flex items-baseline gap-x-2 gap-y-0.5 flex-wrap">
                <StatoOrdineCompatto riga={p.ordine} testId="cr-pos-stato-ordine" />
                {p.vivo && <QuotaOra v={p.vivo} testId="cr-pos-quota-viva" />}
            </div>
            {p.dettaglio && (
                <div className="mt-0.5 flex items-baseline gap-x-2 gap-y-0.5 flex-wrap"
                    data-testid="cr-pos-dettaglio">
                    <BadgeStato d={p.dettaglio} testId="cr-pos-stato" />
                    <Greenup d={p.dettaglio} testId="cr-pos-greenup" />
                    <Uscita d={p.dettaglio} testId="cr-pos-uscita" />
                    <Ingresso d={p.dettaglio} testId="cr-pos-ingresso" />
                    <Copertura d={p.dettaglio} testId="cr-pos-copertura" />
                    <PnlVivo d={p.dettaglio} testId="cr-pos-pnl-vivo" />
                    <ModelloP d={p.dettaglio} testId="cr-pos-modello" />
                </div>
            )}
            {/* QUANTO VALE CHIUDERE ADESSO — il bot propone solo quando la
                regola del manuale scatta, e fa bene. Ma una posizione può
                essere in profitto molto prima, e va VISTO in continuo invece
                che scoperto per caso. Mostrarlo non cambia la strategia. */}
            {ch && (
                <div className="mt-1.5 pt-1.5 border-t border-white/10 flex items-baseline gap-2 flex-wrap"
                    data-testid="cr-chiusura-viva" data-fonte={ch.fonte ?? ''}>
                    <span className="text-[10px] uppercase tracking-wider text-white/40">chiudi ora</span>
                    {ch.prezzo == null ? (
                        <span className="text-[11px] text-orange-400">prezzo non disponibile</span>
                    ) : (
                        <>
                            <span className={`text-[9px] font-bold uppercase tracking-wider px-1 rounded ${
                                ch.lato === 'lay' ? 'bg-rose-500/15 text-rose-300' : 'bg-sky-500/15 text-sky-300'
                            }`}>{ch.lato === 'lay' ? 'banca' : 'punta'}</span>
                            <span className="font-mono text-[12px]" data-testid="cr-chiusura-prezzo">{fmtOdds(ch.prezzo)}</span>
                            <span className={`font-mono text-[13px] tabular-nums ${pnlClass(ch.bloccabile)}`}
                                data-testid="cr-bloccabile"
                                title="P&L garantito chiudendo per intero adesso: identico sui due esiti">
                                {fmtMoney(ch.bloccabile, { signed: true })}
                            </span>
                            {ch.abbinabile != null && (
                                <span className="text-[10px] text-white/35">
                                    {fmtMoney(ch.abbinabile)} abbinabili
                                </span>
                            )}
                            <span className={`text-[10px] ${ch.alMs ? 'text-white/30' : 'text-orange-300/80'}`}
                                data-testid="cr-chiusura-fonte">
                                {ch.testoFonte}
                            </span>
                            {/* B16 (24/09) — stesso posto, stesso testid: ora il
                                comando va al bot DELLA RIGA, non a Safe per tutti */}
                            <BottoneChiudiRiga
                                riga={{
                                    bot: p.bot, id: p.id, eventId: p.eventId,
                                    modalita: p.modalita, stato: p.ordine?.status ?? '',
                                    // 24/09 - scalper: firma della sessione e residuo
                                    ...(p.firma != null ? { firma: p.firma } : {}),
                                    ...(p.residuo ? { residuo: true } : {}),
                                }}
                                testId="cr-chiudi" variante="orfana"
                                prezzoAlClic={() => prezzoAlClic(ch, Date.now())}
                                stimaOra={ch.bloccabile}
                            />
                        </>
                    )}
                </div>
            )}
        </div>
    );
}

// ------------------------------------------------------------------ filtri

export function filtra(
    gruppi: GruppoCampionato[],
    opt: { sport?: SportKey | null },
): GruppoCampionato[] {
    if (opt.sport == null) return gruppi;
    const out: GruppoCampionato[] = [];
    for (const g of gruppi) {
        const partite = g.partite.filter(
            (p) => (p.sport === 'tennis' ? 'tennis' : 'calcio') === opt.sport,
        );
        if (partite.length) out.push({ ...g, partite });
    }
    return out;
}
