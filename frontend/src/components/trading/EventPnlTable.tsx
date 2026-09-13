// ============================================================================
// EventPnlTable.tsx — LA TABELLA DELLE OPERAZIONI, una sola per i tre bot.
//
// Richiesta dell'utente (13/09), testuale: «voglio che la sezione operazioni e
// i dati delle operazioni sia uniformata con più informazioni possibili ed
// estremamente CHIARA!!! Su safe non si capisce un cazzo (le loss sono in nero
// e in piccolo) Io voglio i totali delle operazioni ben chiari».
//
// Due cose, quindi, e nessuna delle due è un dettaglio estetico:
//
//   1. I TOTALI IN TESTA, SEMPRE VISIBILI (mai dentro un accordion): quante
//      operazioni, quanto ho realizzato, quanto vale se chiudo ora, quanto ho
//      investito, quanta responsabilità è ancora a rischio. In corpo grande,
//      col segno colorato, `tabular-nums`, etichette in italiano.
//
//   2. UNA RIGA PER PARTITA col netto davanti, il dettaglio sotto CHIUSO di
//      default e apribile. Prima Safe elencava le gambe una per una: l'apertura
//      di una posizione e la sua chiusura comparivano come due operazioni
//      scollegate, a due ore di distanza in tabella, e nessuna delle due
//      diceva quanto avesse reso la partita.
//
// Il colore del P&L viene da `pnlClass()` di lib/tradeStatus.ts — UNA regola
// sola: positivo verde grassetto, negativo ROSSO grassetto della STESSA
// dimensione, zero neutro, assente «—» (mai «0,00 €», che significherebbe
// «ho chiuso in pari» invece di «non c'è ancora un risultato»).
//
// Il dettaglio apribile è personalizzabile (`renderDettaglio`): Mike mostra i
// suoi cicli e i suoi ordini, Safe ci monta la sua tabella ricca con i bottoni
// di cash out. Il LIVELLO 1 — quello che si legge a colpo d'occhio — è lo
// stesso per tutti, ed è esattamente il punto.
// ============================================================================
import { useMemo, useState, type ReactNode } from 'react';
import { ChevronRight } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { SectionCard, EmptyState } from '@/components/trading/EmptyState';
import { fmtMoney, fmtOdds, fmtTime } from '@/lib/format';
import { statusMetaOf, sideMeta, pnlClass, T, TIP } from '@/lib/tradeStatus';
import {
    groupCicliByEvent, totaliOperazioni, isSettled,
    type CicloGroup, type EventGroup, type PnlTradeLike, type TotaliOperazioni,
} from '@/lib/eventGroups';

// ------------------------------------------------------------------ totali
/** Modalità dichiarata NELL'ETICHETTA: «P&L realizzato · PAPER». */
function suffissoModalita(mode: string | null | undefined): string {
    const m = String(mode ?? '').trim().toUpperCase();
    return m ? ` · ${m}` : '';
}

function Totale({ label, value, cls, hint, testId, sub }: {
    label: string; value: ReactNode; cls?: string; hint?: string; testId: string; sub?: ReactNode;
}) {
    return (
        <div className="min-w-[7.5rem] flex-1" data-testid={testId} title={hint}>
            <div className="text-[10px] uppercase tracking-wide text-slate-400">{label}</div>
            <div className={`font-display text-xl md:text-2xl tabular-nums ${cls ?? 'text-white/90 font-bold'}`}>
                {value}
            </div>
            {sub && <div className="text-[10px] text-slate-500 tabular-nums">{sub}</div>}
        </div>
    );
}

export interface TotaliBarProps {
    tot: TotaliOperazioni;
    /**
     * Modalità a cui si riferiscono QUESTI totali. Sommare euro veri ed euro
     * simulati è una bugia: se il chiamante filtra per modalità lo deve DIRE,
     * e l'etichetta lo scrive («P&L realizzato · PAPER»).
     */
    modalita?: string | null;
    /**
     * Quanto si bloccherebbe chiudendo ADESSO tutto quello che è ancora vivo.
     * Assente = `—`: è una stima che dipende dai prezzi del feed e solo il
     * chiamante sa se li ha. MAI zero al posto di «non lo so».
     */
    apertoOra?: number | null;
    testId?: string;
}

/**
 * La barra dei totali. Vive FUORI da qualunque accordion, in testa alla
 * sezione: sono i cinque numeri per cui si apre la pagina.
 */
export function TotaliBar({ tot, modalita, apertoOra, testId = 'totali-operazioni' }: TotaliBarProps) {
    const suff = suffissoModalita(modalita);
    return (
        <div
            className="flex flex-wrap items-start gap-x-6 gap-y-3 border-b border-white/5 bg-black/20 px-4 py-3"
            data-testid={testId}
            data-mode={String(modalita ?? '').trim().toLowerCase() || undefined}
        >
            <Totale
                testId={`${testId}-operazioni`}
                label={T.totOperazioni}
                hint={TIP.totOperazioni}
                value={tot.operazioni}
                sub={`${tot.partite} ${tot.partite === 1 ? 'partita' : 'partite'}`}
            />
            <Totale
                testId={`${testId}-realizzato`}
                label={`${T.totRealizzato}${suff}`}
                hint={TIP.totRealizzato}
                value={fmtMoney(tot.realizzato, { signed: true })}
                cls={pnlClass(tot.realizzato)}
                sub={
                    <>
                        <span className="text-emerald-400">{tot.vinte} in utile</span>
                        {' · '}
                        <span className="text-red-400">{tot.perse} in perdita</span>
                    </>
                }
            />
            <Totale
                testId={`${testId}-aperto`}
                label={`${T.totAperto}${suff}`}
                hint={TIP.totAperto}
                value={fmtMoney(apertoOra, { signed: true })}
                cls={pnlClass(apertoOra)}
                sub={tot.partiteAperte > 0
                    ? <span className="text-sky-300">{tot.partiteAperte} ancora {tot.partiteAperte === 1 ? 'aperta' : 'aperte'}</span>
                    : 'niente di aperto'}
            />
            <Totale
                testId={`${testId}-investito`}
                label={`${T.totInvestito}${suff}`}
                hint={TIP.totInvestito}
                value={tot.operazioni > 0 ? fmtMoney(tot.investito) : fmtMoney(null)}
            />
            <Totale
                testId={`${testId}-liability`}
                label={`${T.totLiability}${suff}`}
                hint={TIP.totLiability}
                // niente di aperto = niente a rischio: qui lo ZERO è un dato
                // vero, non un buco. Ma senza NESSUNA operazione si dice «—».
                value={tot.operazioni > 0 ? fmtMoney(tot.liability) : fmtMoney(null)}
                cls={tot.liability > 0 ? 'text-orange-400 font-bold' : 'text-slate-300 font-bold'}
            />
        </div>
    );
}

// =============================================================== livello 3
/** Come si chiama, in italiano, quello che questa riga di gamba rappresenta. */
export interface RigheLabels<T extends PnlTradeLike> {
    /** ruolo/fase della gamba ("ingresso Under 3.5", "copertura"…) */
    ruolo?: (t: T) => string;
    /** selezione/mercato in chiaro */
    selezione?: (t: T) => string;
    /** badge extra accanto al ruolo (manuale, modalità…) */
    badge?: (t: T) => ReactNode;
    /** badge extra accanto allo STATO (uscita, green-up…) */
    statoExtra?: (t: T) => ReactNode;
    /** tooltip del P&L (lordo, commissione…) */
    pnlTitle?: (t: T) => string;
    /** minuto e punteggio d'ingresso, se il bot li registra */
    ingresso?: (t: T) => string | null;
}

function RigaGamba<T extends PnlTradeLike>({ t, lab }: { t: T; lab: RigheLabels<T> }) {
    const st = statusMetaOf(t as { status: string; meta?: Record<string, unknown> | null });
    const side = sideMeta(t.side);
    const regolata = isSettled(t.status);
    const ing = lab.ingresso?.(t) ?? null;
    return (
        <tr className="border-t border-white/5 text-[11px]" data-testid={`gamba-${t.id}`}>
            <td className="py-1 pl-10 pr-2 tabular-nums text-slate-400">{fmtTime(t.placed_at, { seconds: true })}</td>
            <td className="px-2 text-slate-300">
                {lab.ruolo?.(t) ?? '—'}
                {lab.badge?.(t)}
            </td>
            <td className="px-2">
                <span className={side.cls}>{side.label}</span>{' '}
                <span className="text-slate-400">{lab.selezione?.(t) ?? '—'}</span>
                {ing && <span className="ml-1 text-slate-500 tabular-nums" title="minuto e punteggio all'ingresso">({ing})</span>}
            </td>
            <td className="px-2 text-right tabular-nums text-slate-300">{fmtMoney(t.size, { currency: '' })}</td>
            <td className="px-2 text-right tabular-nums text-slate-300">{fmtOdds(t.price)}</td>
            <td className="px-2">
                <span className={st.cls}>{st.label}</span>
                {lab.statoExtra?.(t)}
            </td>
            <td
                className={`px-2 py-1 text-right tabular-nums ${pnlClass(regolata ? Number(t.pnl ?? 0) : null)}`}
                title={lab.pnlTitle?.(t) ?? 'P&L netto della commissione'}
            >
                {regolata ? fmtMoney(t.pnl ?? 0, { signed: true }) : fmtMoney(null)}
            </td>
        </tr>
    );
}

// =============================================================== livello 2
/** prezzo medio pesato delle gambe che aprono / chiudono un ciclo.
 *  Una size o un prezzo non numerici escludono la riga: meglio una media su
 *  meno gambe che una quota `NaN` in faccia al trader. */
function medio(righe: readonly PnlTradeLike[]): number | null {
    const vive = righe.filter((r) => r.status !== 'error'
        && Number.isFinite(Number(r.size)) && Number(r.size) > 0
        && Number.isFinite(Number(r.price)) && Number(r.price) > 0);
    const tot = vive.reduce((s, r) => s + Number(r.size), 0);
    if (!(tot > 0)) return null;
    const m = vive.reduce((s, r) => s + Number(r.size) * Number(r.price), 0) / tot;
    return Number.isFinite(m) ? m : null;
}

function RigheCiclo<T extends PnlTradeLike>({ g, n, lab, unita }: {
    g: CicloGroup<T>; n: number; lab: RigheLabels<T>; unita: { uno: string; molti: string };
}) {
    const righe = [g.open, ...g.closes];
    const aperture = righe.filter((r) => !r.closes_trade_id);
    const chiusure = righe.filter((r) => r.closes_trade_id);
    const pIn = medio(aperture);
    const pOut = medio(chiusure);
    return (
        <>
            <tr className="border-t border-white/10 bg-white/[0.02] text-[11px]" data-testid={`ciclo-${g.open.id}`}>
                <td className="py-1 pl-6 pr-2 font-heading uppercase tracking-wide text-slate-400">
                    {g.orphan ? 'chiusura orfana' : `${unita.uno} ${n}`}
                </td>
                <td className="px-2 text-slate-400" colSpan={4}>
                    {pIn != null && <>ingresso <span className="tabular-nums text-slate-300">{fmtOdds(pIn)}</span></>}
                    {pOut != null && <> → uscita <span className="tabular-nums text-slate-300">{fmtOdds(pOut)}</span></>}
                    {pIn == null && pOut == null && <span className="italic">nessuna gamba abbinata</span>}
                </td>
                <td className="px-2 text-slate-500">{righe.length} {righe.length === 1 ? 'ordine' : 'ordini'}</td>
                <td className={`px-2 py-1 text-right tabular-nums ${pnlClass(g.netPnl)}`}>
                    {fmtMoney(g.netPnl, { signed: true })}
                </td>
            </tr>
            {righe
                .slice()
                .sort((a, b) => Date.parse(a.placed_at) - Date.parse(b.placed_at))
                .map((t) => <RigaGamba key={t.id} t={t} lab={lab} />)}
        </>
    );
}

// =============================================================== livello 1
function RigaPartita<T extends PnlTradeLike>({
    e, aperta, onToggle, onApriScheda, unita, lab, renderDettaglio,
}: {
    e: EventGroup<T>;
    aperta: boolean;
    onToggle: () => void;
    onApriScheda?: (eventId: string) => void;
    unita: { uno: string; molti: string };
    lab: RigheLabels<T>;
    renderDettaglio?: (e: EventGroup<T>) => ReactNode;
}) {
    const n = e.cicli.length;
    return (
        <>
            <tr
                className="cursor-pointer border-t border-white/10 transition-colors hover:bg-white/[0.04]"
                onClick={onToggle}
                data-testid={`partita-${e.event_id}`}
            >
                <td className="w-6 py-2 pl-2 pr-1">
                    <button
                        type="button"
                        aria-expanded={aperta}
                        aria-label={aperta ? `Chiudi il dettaglio di ${e.event_name}` : `Apri il dettaglio di ${e.event_name}`}
                        onClick={(ev) => { ev.stopPropagation(); onToggle(); }}
                        className="grid h-5 w-5 place-items-center rounded text-slate-400 hover:bg-white/10 hover:text-slate-200"
                        data-testid={`apri-${e.event_id}`}
                    >
                        <ChevronRight className={`h-3.5 w-3.5 transition-transform ${aperta ? 'rotate-90' : ''}`} />
                    </button>
                </td>
                <td className="px-2 py-2 font-medium text-slate-100">
                    {onApriScheda ? (
                        <button
                            type="button"
                            onClick={(ev) => { ev.stopPropagation(); onApriScheda(e.event_id); }}
                            className="max-w-[22rem] truncate text-left underline-offset-2 hover:underline"
                            title={`${e.event_name} — apri la scheda della partita`}
                            data-testid={`vai-alla-scheda-${e.event_id}`}
                        >
                            {e.event_name}
                        </button>
                    ) : (
                        <span className="max-w-[22rem] truncate" title={e.event_name}>{e.event_name}</span>
                    )}
                    {e.mode === 'live' && (
                        <Badge className="ml-2 border-amber-400/50 bg-amber-500/20 px-1.5 py-0 text-[9px] text-amber-200">
                            soldi veri
                        </Badge>
                    )}
                    {e.mode === 'mista' && (
                        <Badge
                            className="ml-2 border-red-400/50 bg-red-500/20 px-1.5 py-0 text-[9px] text-red-200"
                            title="questa partita ha righe in paper E in live: il netto mescola due mondi"
                        >
                            modalità mista
                        </Badge>
                    )}
                </td>
                <td className="px-2 py-2 text-right tabular-nums text-slate-400">
                    {n} {n === 1 ? unita.uno : unita.molti}
                </td>
                <td className="px-2 py-2 text-right tabular-nums text-slate-400" title={TIP.totInvestito}>
                    {e.investito > 0 ? fmtMoney(e.investito) : fmtMoney(null)}
                </td>
                <td
                    className={`px-2 py-2 text-right tabular-nums ${e.liability > 0 ? 'text-orange-400' : 'text-slate-600'}`}
                    title={TIP.totLiability}
                    data-testid={`liability-${e.event_id}`}
                >
                    {e.liability > 0 ? fmtMoney(e.liability) : fmtMoney(null)}
                </td>
                <td className="px-2 py-2">
                    {e.apertaAncora ? (
                        <Badge
                            className="border-sky-400/50 bg-sky-500/20 px-1.5 py-0 text-[10px] text-sky-200"
                            title={`${e.righeAperte} ${e.righeAperte === 1 ? 'ordine ancora aperto' : 'ordini ancora aperti'}: il netto qui a destra è PARZIALE`}
                        >
                            ancora aperta
                        </Badge>
                    ) : (
                        <Badge variant="outline" className="px-1.5 py-0 text-[10px] text-slate-400">chiusa</Badge>
                    )}
                </td>
                <td
                    className={`px-2 py-2 text-right text-base tabular-nums ${pnlClass(e.netPnl)}`}
                    title={e.apertaAncora
                        ? 'netto delle operazioni GIÀ regolate: la partita non è finita'
                        : 'netto di tutte le operazioni della partita, commissione già tolta'}
                    data-testid={`netto-${e.event_id}`}
                >
                    {fmtMoney(e.netPnl, { signed: true })}
                    {e.apertaAncora && e.netPnl != null && <span className="ml-1 text-[10px] font-normal text-slate-500">parz.</span>}
                </td>
            </tr>
            {aperta && (
                <tr data-testid={`dettaglio-${e.event_id}`}>
                    <td colSpan={7} className="p-0">
                        {renderDettaglio ? renderDettaglio(e) : (
                            <table className="w-full">
                                <tbody>
                                    {e.cicli.map((g, i) => (
                                        <RigheCiclo key={g.open.id} g={g} n={e.cicli.length - i} lab={lab} unita={unita} />
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </td>
                </tr>
            )}
        </>
    );
}

// =============================================================== componente
export interface EventPnlTableProps<T extends PnlTradeLike> {
    /** cicli già filtrati (giornata, fase…) dal chiamante */
    cicli: readonly CicloGroup<T>[];
    /** filtro sui cicli: alimenta le schede «Risultati Pre-Match / Live» */
    filtro?: (c: CicloGroup<T>) => boolean;
    titolo: string;
    icona?: ReactNode;
    /** riga di spiegazione sotto la tabella */
    nota?: ReactNode;
    /** mostrato quando non c'è niente */
    vuoto: ReactNode;
    /** avviso (per esempio il tetto di righe della RPC) */
    avviso?: ReactNode;
    /** clic sul nome della partita: porta alla sua scheda */
    onApriScheda?: (eventId: string) => void;
    /** modalità dei totali: dichiarata nell'etichetta («P&L realizzato · PAPER») */
    modalita?: string | null;
    /** P&L che si bloccherebbe chiudendo ora; assente = «—» */
    apertoOra?: number | null;
    /** come si chiama un raggruppamento di secondo livello (Mike: ciclo) */
    unita?: { uno: string; molti: string };
    /** etichette in italiano delle righe di gamba (dipendono dal bot) */
    etichette?: RigheLabels<T>;
    /** dettaglio su misura al posto dei livelli ciclo/gamba di serie */
    renderDettaglio?: (e: EventGroup<T>) => ReactNode;
    /** azioni nell'intestazione della card (toggle, filtri…) */
    azioni?: ReactNode;
    testId?: string;
}

export function EventPnlTable<T extends PnlTradeLike>({
    cicli, filtro, titolo, icona, nota, vuoto, avviso, onApriScheda,
    modalita, apertoOra, unita = { uno: 'posizione', molti: 'posizioni' },
    etichette = {}, renderDettaglio, azioni, testId = 'event-pnl',
}: EventPnlTableProps<T>) {
    const [aperte, setAperte] = useState<Set<string>>(new Set());
    const eventi = useMemo(() => groupCicliByEvent(cicli, { filtro }), [cicli, filtro]);

    // SEPARAZIONE PAPER / LIVE NEI TOTALI (richiesta del 13/09).
    // Un totale che somma euro veri ed euro simulati è una bugia: il backend
    // tiene le due contabilità separate e la barra deve fare lo stesso. Le
    // RIGHE dell'altra modalità restano però in tabella — nasconderle sarebbe
    // peggio, sono posizioni vere — e una riga d'avviso dice quante sono e che
    // NON sono nel totale. Senza `modalita` non si filtra e non si dichiara.
    const modo = String(modalita ?? '').trim().toLowerCase();
    const eventiTot = useMemo(() => (
        modo
            ? groupCicliByEvent(
                cicli.filter((c) => String(c.open.mode ?? '').trim().toLowerCase() === modo),
                { filtro },
            )
            : eventi
    ), [cicli, filtro, eventi, modo]);
    const tot = useMemo(() => totaliOperazioni(eventiTot), [eventiTot]);
    const fuoriModalita = useMemo(() => (
        modo ? cicli.filter((c) => {
            if (filtro && !filtro(c)) return false;
            const m = String(c.open.mode ?? '').trim().toLowerCase();
            return m !== modo;
        }).length : 0
    ), [cicli, filtro, modo]);

    const toggle = (id: string) => setAperte((prev) => {
        const next = new Set(prev);
        if (!next.delete(id)) next.add(id);
        return next;
    });

    return (
        <SectionCard icon={icona} title={titolo} count={eventi.length} testId={testId} actions={azioni}>
            {/* I TOTALI STANNO QUI: fuori da ogni accordion, sempre visibili.
                Sono la prima cosa che si legge aprendo la pagina. */}
            <TotaliBar tot={tot} modalita={modalita} apertoOra={apertoOra} testId={`${testId}-totali`} />
            {fuoriModalita > 0 && (
                <p className="px-4 py-1.5 text-[11px] text-amber-300/90" data-testid={`${testId}-fuori-modalita`}>
                    {fuoriModalita} {fuoriModalita === 1 ? 'operazione' : 'operazioni'} in un’altra modalità
                    {' '}(il servizio è in {modo.toUpperCase()}): {fuoriModalita === 1 ? 'è' : 'sono'} in tabella
                    {' '}ma NON nei totali qui sopra — paper e live sono contabilità separate.
                </p>
            )}
            {avviso}
            {eventi.length === 0 ? (
                <EmptyState testId={`${testId}-vuoto`}>{vuoto}</EmptyState>
            ) : (
                <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                        <thead>
                            <tr className="text-left text-[10px] uppercase tracking-wide text-slate-500">
                                <th className="w-6" />
                                <th className="px-2 pb-1 font-heading">Partita</th>
                                <th className="px-2 pb-1 text-right font-heading">{unita.molti}</th>
                                <th className="px-2 pb-1 text-right font-heading" title={TIP.totInvestito}>Investito</th>
                                <th className="px-2 pb-1 text-right font-heading" title={TIP.totLiability}>Responsabilità</th>
                                <th className="px-2 pb-1 font-heading">Stato</th>
                                <th className="px-2 pb-1 text-right font-heading">P&amp;L netto</th>
                            </tr>
                        </thead>
                        <tbody>
                            {eventi.map((e) => (
                                <RigaPartita
                                    key={e.event_id}
                                    e={e}
                                    aperta={aperte.has(e.event_id)}
                                    onToggle={() => toggle(e.event_id)}
                                    onApriScheda={onApriScheda}
                                    unita={unita}
                                    lab={etichette}
                                    renderDettaglio={renderDettaglio}
                                />
                            ))}
                        </tbody>
                    </table>
                    <p className="mt-2 px-2 pb-2 text-[10px] text-slate-500">
                        {nota ?? 'Clicca una partita per aprire le operazioni che la compongono.'}
                    </p>
                </div>
            )}
        </SectionCard>
    );
}

export default EventPnlTable;
