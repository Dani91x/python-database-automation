// ============================================================================
// MikeEventPnlTable — UNA RIGA PER PARTITA, col netto davanti e il dettaglio
// sotto, da aprire solo se lo vuoi.
//
// Richiesta dell'utente (13/09), testuale: «il P&L deve essere il netto delle
// operazioni di quella partita, con a cascata il dettaglio delle operazioni
// (deve essere nascosto e apribile da me), in verde i risultati positivi e in
// rosso quelli negativi».
//
// Prima la scheda "Operazioni" era un elenco piatto di CICLI, ordinati per ora:
// i due o tre cicli della stessa partita finivano sparsi fra partite diverse, e
// la colonna P&L mostrava il netto del ciclo sull'apertura E il netto della
// singola gamba sulle chiusure — gli stessi euro due volte, a due livelli, senza
// che niente lo dicesse. Chi sommava con gli occhi otteneva il doppio.
//
// Adesso ci sono tre livelli, e a colpo d'occhio se ne vede uno solo:
//   1. PARTITA   il netto che conta, grande e colorato;
//   2. CICLO     ingresso, uscita, quanto ha reso quel ciclo;
//   3. GAMBA     l'ordine vero: ora, lato, selezione, size, quota, esito.
//
// Lo stesso componente serve tre schede — Operazioni, Risultati Pre-Match,
// Risultati Live — perché sono la stessa domanda con un filtro diverso: una
// implementazione sola, un solo posto dove sbagliare.
// ============================================================================
import { useMemo, useState } from 'react';
import { ChevronRight } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { ExitBadge } from '@/components/trading/ExitBadge';
import { SectionCard, EmptyState } from '@/components/trading/EmptyState';
import { fmtMoney, fmtOdds, fmtTime } from '@/lib/format';
import { statusMetaOf, sideMeta } from '@/lib/tradeStatus';
import { exitInfo } from '@/lib/dailyHistory';
import {
    groupMikeTradesByEvent, totaleRisultati, marketLabel, roleLabel, isManualTrade,
    type MikeEventGroup, type MikeTradeGroup, type MikeTrade,
} from '@/lib/mike';

/** verde sopra zero, rosso sotto, grigio a zero. Mai colore su un dato assente. */
export function pnlClass(v: number | null | undefined): string {
    if (v == null) return 'text-slate-400';
    return v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-slate-300';
}

const REGOLATE = new Set(['won', 'lost', 'void']);

/** lordo e commissione stanno nel tooltip: il numero in pagina è sempre il netto */
function pnlTitle(t: MikeTrade): string {
    const meta = t.meta ?? {};
    const gross = Number(meta.pnl_gross);
    const comm = Number(meta.commission_paid);
    const parts: string[] = [];
    if (Number.isFinite(gross)) parts.push(`lordo ${fmtMoney(gross, { signed: true })}`);
    if (Number.isFinite(comm)) parts.push(`commissione ${fmtMoney(comm)}`);
    return parts.length
        ? `${parts.join(' · ')} — in pagina il NETTO`
        : 'P&L netto della commissione';
}

/** prezzo medio pesato delle gambe che aprono / chiudono un ciclo.
 *  Una size o un prezzo non numerici escludono la riga: meglio una media su
 *  meno gambe che una quota `NaN` in faccia al trader. */
function medio(righe: readonly MikeTrade[]): number | null {
    const vive = righe.filter((r) => r.status !== 'error'
        && Number.isFinite(Number(r.size)) && Number(r.size) > 0
        && Number.isFinite(Number(r.price)) && Number(r.price) > 0);
    const tot = vive.reduce((s, r) => s + Number(r.size), 0);
    if (!(tot > 0)) return null;
    const m = vive.reduce((s, r) => s + Number(r.size) * Number(r.price), 0) / tot;
    return Number.isFinite(m) ? m : null;
}

// =============================================================== livello 3
function RigaGamba({ t }: { t: MikeTrade }) {
    const st = statusMetaOf(t);
    const side = sideMeta(t.side);
    const uscita = exitInfo(t.meta ?? {});
    const regolata = REGOLATE.has(t.status);
    return (
        <tr className="border-t border-white/5 text-[11px]" data-testid={`gamba-${t.id}`}>
            <td className="py-1 pl-10 pr-2 tabular-nums text-slate-400">{fmtTime(t.placed_at, { seconds: true })}</td>
            <td className="px-2 text-slate-300">
                {roleLabel(t.role)}
                {isManualTrade(t) && <Badge variant="outline" className="ml-1 px-1 py-0 text-[9px]">manuale</Badge>}
            </td>
            <td className="px-2">
                <span className={side.cls}>{side.label}</span>{' '}
                <span className="text-slate-400">{t.selection_name ?? marketLabel(t.market_type)}</span>
            </td>
            <td className="px-2 text-right tabular-nums text-slate-300">{fmtMoney(t.size, { currency: '' })}</td>
            <td className="px-2 text-right tabular-nums text-slate-300">{fmtOdds(t.price)}</td>
            <td className="px-2">
                <span className={st.cls}>{st.label}</span>
                {uscita && <ExitBadge info={uscita} className="ml-1" />}
            </td>
            <td className={`px-2 py-1 text-right tabular-nums font-medium ${pnlClass(regolata ? Number(t.pnl ?? 0) : null)}`}
                title={pnlTitle(t)}>
                {regolata ? fmtMoney(t.pnl, { signed: true }) : '—'}
            </td>
        </tr>
    );
}

// =============================================================== livello 2
function RigheCiclo({ g, n }: { g: MikeTradeGroup; n: number }) {
    const righe = [g.open, ...g.closes];
    const aperture = righe.filter((r) => !r.closes_trade_id);
    const chiusure = righe.filter((r) => r.closes_trade_id);
    const pIn = medio(aperture);
    const pOut = medio(chiusure);
    return (
        <>
            <tr className="border-t border-white/10 bg-white/[0.02] text-[11px]" data-testid={`ciclo-${g.open.id}`}>
                <td className="py-1 pl-6 pr-2 font-heading uppercase tracking-wide text-slate-400">
                    {g.orphan ? 'chiusura orfana' : `ciclo ${n}`}
                </td>
                <td className="px-2 text-slate-400" colSpan={4}>
                    {pIn != null && <>ingresso <span className="tabular-nums text-slate-300">{fmtOdds(pIn)}</span></>}
                    {pOut != null && <> → uscita <span className="tabular-nums text-slate-300">{fmtOdds(pOut)}</span></>}
                    {pIn == null && pOut == null && <span className="italic">nessuna gamba abbinata</span>}
                </td>
                <td className="px-2 text-slate-500">{righe.length} {righe.length === 1 ? 'ordine' : 'ordini'}</td>
                <td className={`px-2 py-1 text-right tabular-nums font-semibold ${pnlClass(g.netPnl)}`}>
                    {g.netPnl == null ? '—' : fmtMoney(g.netPnl, { signed: true })}
                </td>
            </tr>
            {righe
                .slice()
                .sort((a, b) => Date.parse(a.placed_at) - Date.parse(b.placed_at))
                .map((t) => <RigaGamba key={t.id} t={t} />)}
        </>
    );
}

// =============================================================== livello 1
function RigaPartita({ e, aperta, onToggle, onApriScheda }: {
    e: MikeEventGroup; aperta: boolean; onToggle: () => void;
    onApriScheda?: (eventId: string) => void;
}) {
    const nCicli = e.cicli.length;
    const stake = e.cicli.reduce((s, g) => {
        if (g.open.status === 'error') return s;
        const v = Number(g.open.size);
        return s + (Number.isFinite(v) ? v : 0);
    }, 0);
    return (
        <>
            <tr
                className="cursor-pointer border-t border-white/10 transition-colors hover:bg-white/[0.04]"
                onClick={onToggle}
                data-testid={`partita-${e.event_id}`}
            >
                <td className="py-2 pl-2 pr-1 w-6">
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
                        <Badge className="ml-2 border-red-400/50 bg-red-500/20 px-1.5 py-0 text-[9px] text-red-200"
                               title="questa partita ha righe in paper E in live: il netto mescola due mondi">
                            modalità mista
                        </Badge>
                    )}
                </td>
                <td className="px-2 py-2 text-right tabular-nums text-slate-400">
                    {nCicli} {nCicli === 1 ? 'ciclo' : 'cicli'}
                </td>
                <td className="px-2 py-2 text-right tabular-nums text-slate-400" title="capitale impegnato nelle aperture">
                    {stake > 0 ? fmtMoney(stake) : '—'}
                </td>
                <td className="px-2 py-2">
                    {e.apertaAncora ? (
                        <Badge className="border-sky-400/50 bg-sky-500/20 px-1.5 py-0 text-[10px] text-sky-200"
                               title={`${e.righeAperte} ${e.righeAperte === 1 ? 'ordine ancora aperto' : 'ordini ancora aperti'}: il netto qui a destra è PARZIALE`}>
                            ancora aperta
                        </Badge>
                    ) : (
                        <Badge variant="outline" className="px-1.5 py-0 text-[10px] text-slate-400">chiusa</Badge>
                    )}
                </td>
                <td
                    className={`px-2 py-2 text-right tabular-nums text-base font-semibold ${pnlClass(e.netPnl)}`}
                    title={e.apertaAncora
                        ? 'netto delle operazioni GIÀ regolate: la partita non è finita'
                        : 'netto di tutte le operazioni della partita, commissione già tolta'}
                    data-testid={`netto-${e.event_id}`}
                >
                    {e.netPnl == null ? '—' : fmtMoney(e.netPnl, { signed: true })}
                    {e.apertaAncora && e.netPnl != null && <span className="ml-1 text-[10px] text-slate-500">parz.</span>}
                </td>
            </tr>
            {aperta && (
                <tr data-testid={`dettaglio-${e.event_id}`}>
                    <td colSpan={6} className="p-0">
                        <table className="w-full">
                            <tbody>
                                {e.cicli.map((g, i) => (
                                    <RigheCiclo key={g.open.id} g={g} n={e.cicli.length - i} />
                                ))}
                            </tbody>
                        </table>
                    </td>
                </tr>
            )}
        </>
    );
}

// =============================================================== componente
export interface MikeEventPnlTableProps {
    /** cicli già filtrati (giornata, fase…) dal chiamante */
    gruppi: readonly MikeTradeGroup[];
    /** solo i cicli di questa fase; assente = tutte */
    fase?: 'pre' | 'live';
    titolo: string;
    icona?: React.ReactNode;
    /** riga di spiegazione sotto il titolo */
    nota?: React.ReactNode;
    /** mostrato quando non c'è niente */
    vuoto: React.ReactNode;
    /** avviso (per esempio il tetto di righe della RPC) */
    avviso?: React.ReactNode;
    /** clic sul nome della partita: porta alla sua scheda */
    onApriScheda?: (eventId: string) => void;
    testId?: string;
}

export function MikeEventPnlTable({
    gruppi, fase, titolo, icona, nota, vuoto, avviso, onApriScheda,
    testId = 'mike-event-pnl',
}: MikeEventPnlTableProps) {
    const [aperte, setAperte] = useState<Set<string>>(new Set());
    const eventi = useMemo(() => groupMikeTradesByEvent(gruppi, fase), [gruppi, fase]);
    const tot = useMemo(() => totaleRisultati(eventi), [eventi]);

    const toggle = (id: string) => setAperte((prev) => {
        const next = new Set(prev);
        if (!next.delete(id)) next.add(id);
        return next;
    });

    return (
        <SectionCard
            icon={icona}
            title={titolo}
            count={eventi.length}
            testId={testId}
            note={
                eventi.length > 0 ? (
                    <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]">
                        <span className={`tabular-nums text-sm font-semibold ${pnlClass(tot.conRisultato ? tot.netto : null)}`}
                              data-testid={`${testId}-totale`}>
                            {tot.conRisultato ? fmtMoney(tot.netto, { signed: true }) : '—'}
                        </span>
                        <span className="text-slate-400">
                            {tot.conRisultato} {tot.conRisultato === 1 ? 'partita con risultato' : 'partite con risultato'}
                            {' · '}
                            <span className="text-emerald-400">{tot.vinte} in utile</span>
                            {' · '}
                            <span className="text-red-400">{tot.perse} in perdita</span>
                            {tot.aperte > 0 && <> · <span className="text-sky-300">{tot.aperte} ancora aperte</span></>}
                        </span>
                    </span>
                ) : null
            }
        >
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
                                <th className="px-2 pb-1 text-right font-heading">Cicli</th>
                                <th className="px-2 pb-1 text-right font-heading">Impegnato</th>
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
                                />
                            ))}
                        </tbody>
                    </table>
                    <p className="mt-2 text-[10px] text-slate-500">
                        {nota ?? 'Clicca una partita per aprire i suoi cicli e gli ordini che li compongono.'}
                    </p>
                </div>
            )}
        </SectionCard>
    );
}
