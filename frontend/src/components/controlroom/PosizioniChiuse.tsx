// ============================================================================
// PosizioniChiuse.tsx — LA SCHEDA DELLE POSIZIONI CHIUSE.
//
// «qui ci andranno tutte le posizioni VINCENTI E PERDENTI, filtrabili
// chiaramente, PNL GLOBALE DELLA POSIZIONE, pnl dettaglio, voglio il massimo
// livello di personalizzazione e il massimo livello di leggibilità dei dati»
// (utente, 14/09).
//
// DUE NUMERI PER POSIZIONE, e la differenza è tutto il punto:
//   · il **globale** in grande — quanto ha reso l'operazione, apertura e
//     coperture insieme. È l'unico che dice se è andata bene.
//   · il **dettaglio** riga per riga, aprendo — perché su un green-up
//     l'apertura vince e la copertura perde, e chi guarda solo le righe crede
//     di aver sbagliato.
//
// IL RIEPILOGO IN ALTO DESCRIVE QUELLO CHE SI VEDE SOTTO, non tutto il
// resto: un totale che non corrisponde alle righe elencate è il modo più
// rapido di far perdere fiducia a un trader.
//
// SOLO LA GIORNATA DI OGGI (ordine dell'utente, 17/09). Le righe dei tre bot
// arrivano dalle RPC di stato con un semplice `limit` (Omega:
// `get_omega_trades(p_limit=2000)`), quindi contengono anche i giorni passati:
// prima di questa scheda il banco della giornata elencava operazioni di
// settimane prima insieme a quelle di stamattina, e il totale in alto le
// sommava. I giorni precedenti hanno una casa: la dashboard «Storico», a cui
// porta il pulsante qui in testata.
// ============================================================================
import { useMemo, useState } from 'react';
import { Card } from '@/components/ui/card';
import { ChevronRight, ChevronDown } from 'lucide-react';
import { EmptyState } from '@/components/trading/EmptyState';
import { StoricoLink } from '@/components/trading/StoricoLink';
import { fmtMoney, fmtOdds, fmtPct, fmtTime, DASH } from '@/lib/format';
import { pnlClass } from '@/lib/tradeStatus';
import { StatoOrdineCompatto } from '@/components/trading/StatoOrdine';
import { BOT_LABEL, type Bot, type Modo } from '@/lib/controlRoom';
import { dayLabel } from '@/lib/dailyHistory';
import {
    filtraChiuse, riepilogoChiuse, fuoriGiornata,
    certezzaDiPosizione, gambeAnnullate, sintesiPosizione,
    type PosizioneChiusa, type Esito,
} from '@/lib/posizioniChiuse';
import { eCertezzaVerde, type StatoCertezzaChiusura } from '@/lib/certezzaChiusura';

const CERTEZZA_LABEL: Record<StatoCertezzaChiusura, string> = {
    CHIUSA_CONFERMATA: 'CHIUSA · CONFERMATA',
    REGOLATA_DAL_MERCATO: 'REGOLATA DAL MERCATO',
    CHIUSA_PARZIALE: 'PARZIALE · ESPOSIZIONE RESIDUA',
    CHIUSURA_IN_ATTESA: 'IN ATTESA DI ABBINAMENTO',
    CHIUSURA_FALLITA: 'CHIUSURA FALLITA · ANCORA APERTA',
    NON_VERIFICABILE: 'NON VERIFICABILE',
};

function certezzaCls(stato: StatoCertezzaChiusura): string {
    if (eCertezzaVerde(stato)) return 'bg-emerald-500/20 text-emerald-300 border-emerald-500/50';
    if (stato === 'CHIUSURA_FALLITA') return 'bg-red-500/20 text-red-300 border-red-500/60';
    return 'bg-amber-500/20 text-amber-300 border-amber-500/50'; // parziale/attesa/non verificabile
}

const ESITO_TESTO: Record<Esito, string> = { vinta: 'vinte', persa: 'perse', pari: 'pari' };
const ESITO_CLS: Record<Esito, string> = {
    vinta: 'text-emerald-400', persa: 'text-red-400', pari: 'text-white/45',
};

export interface PosizioniChiuseProps {
    chiuse: PosizioneChiusa[];
    /** lo sport scelto in cima alla pagina; null = tutti */
    sport: 'calcio' | 'tennis' | null;
    /**
     * LA GIORNATA OPERATIVA da mostrare, 'YYYY-MM-DD' (Europe/Rome).
     * È l'unico giorno che questa scheda elenca: i precedenti stanno nello
     * Storico. Senza questo dato la scheda non filtra (e lo dichiara), invece
     * di indovinare una data da sola.
     */
    giorno: string;
    testId?: string;
}

export function PosizioniChiuse({ chiuse, sport, giorno, testId = 'cr-chiuse' }: PosizioniChiuseProps) {
    const [esito, setEsito] = useState<Esito | 'tutte'>('tutte');
    const [modo, setModo] = useState<Modo | 'tutte'>('live');
    const [bot, setBot] = useState<Bot | 'tutti'>('tutti');
    const [aperta, setAperta] = useState<number | null>(null);

    const righe = useMemo(
        () => filtraChiuse(chiuse, { esito, modo, bot, sport: sport ?? 'tutti', giorno }),
        [chiuse, esito, modo, bot, sport, giorno],
    );
    const r = useMemo(() => riepilogoChiuse(righe), [righe]);

    // LA CERTEZZA DI CHIUSURA (18/09): un giudizio per riga, con LA STESSA
    // funzione usata dopo un'approvazione. Il riepilogo ha senso solo per UNA
    // modalità alla volta (paper e live non si sommano MAI): col filtro
    // «entrambi» si mostra solo il badge di riga, non il totale misto — le
    // righe qui dentro sono comunque già di UNA sola modalità per volta,
    // perché `righe` viene filtrato PRIMA da `filtraChiuse`.
    const certezze = useMemo(() => righe.map((p) => ({ p, c: certezzaDiPosizione(p) })), [righe]);
    const riepilogoCert = useMemo(() => {
        if (modo === 'tutte' || certezze.length === 0) return null;
        let confermate = 0;
        let conEsposizione = 0;
        let nonVerificabili = 0;
        let esposizioneTotale = 0;
        for (const { c } of certezze) {
            if (eCertezzaVerde(c.stato)) confermate += 1;
            else if (c.stato === 'NON_VERIFICABILE') nonVerificabili += 1;
            else conEsposizione += 1;
            if (c.esposizione.stake != null && c.esposizione.stake > 0.005) {
                esposizioneTotale = Math.round((esposizioneTotale + c.esposizione.stake) * 100) / 100;
            }
        }
        return { n: certezze.length, confermate, conEsposizione, nonVerificabili, esposizioneTotale };
    }, [certezze, modo]);
    // quante restano FUORI da oggi: si dice, non si fanno sparire
    const fuori = useMemo(
        () => fuoriGiornata(
            filtraChiuse(chiuse, { sport: sport ?? 'tutti' }), giorno,
        ),
        [chiuse, sport, giorno],
    );

    return (
        <Card className="glass-card border-white/10 p-0 overflow-hidden" data-testid={testId}>
            {/* IL RIEPILOGO — descrive le righe qui sotto, non tutto lo storico */}
            <div className="px-3 py-2 border-b border-white/10 flex items-baseline gap-3 flex-wrap">
                <span className="text-[11px] uppercase tracking-wider text-white/60">Posizioni chiuse</span>
                {/* LA GIORNATA, in chiaro: «Oggi · N chiuse». Un elenco senza
                    data lascia credere che sia tutto quello che esiste. */}
                <span
                    className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-primary/15 text-primary"
                    data-testid="cr-chiuse-giornata"
                    title={`giornata operativa ${dayLabel(giorno)} (Europe/Rome), per giorno di PIAZZAMENTO`}
                >
                    Oggi · {r.n} {r.n === 1 ? 'chiusa' : 'chiuse'}
                </span>
                <span className={`font-mono text-[15px] font-bold tabular-nums ${pnlClass(r.totale)}`}
                    data-testid="cr-chiuse-totale">
                    {r.totale == null ? DASH : fmtMoney(r.totale, { signed: true })}
                </span>
                <span className="text-[10.5px] text-white/45 flex items-baseline gap-2">
                    <span><span className="font-mono text-white/70">{r.n}</span> {r.n === 1 ? 'posizione' : 'posizioni'}</span>
                    <span className="text-emerald-400/80 font-mono">{r.vinte} V</span>
                    <span className="text-red-400/80 font-mono">{r.perse} P</span>
                    {r.pari > 0 && <span className="text-white/40 font-mono">{r.pari} pari</span>}
                    {r.percentualeVinte != null && (
                        <span title="vinte su vinte+perse">{fmtPct(r.percentualeVinte, 0)}</span>
                    )}
                </span>
                <span className="ml-auto flex items-center gap-2">
                    {modo === 'live' && (
                        <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-red-500/20 text-red-300">
                            soldi veri
                        </span>
                    )}
                    <StoricoLink sport={sport} compatto testId="cr-chiuse-storico" />
                </span>
            </div>

            {/* LA CERTEZZA DI CHIUSURA (18/09) — «N chiuse confermate · M con
                esposizione residua (X €) · K non verificabili»: se M o K sono
                > 0 questa riga è un ALLARME visibile, non una statistica in
                più. Solo con UNA modalità scelta (paper e live non si sommano). */}
            {riepilogoCert && riepilogoCert.n > 0 && (() => {
                const allarme = riepilogoCert.conEsposizione > 0 || riepilogoCert.nonVerificabili > 0;
                return (
                    <div
                        className={`px-3 py-1.5 border-b flex items-center gap-3 flex-wrap text-[10.5px] ${
                            allarme ? 'border-orange-500/30 bg-orange-500/10' : 'border-white/10'
                        }`}
                        data-testid="cr-chiuse-certezza"
                        data-allarme={allarme ? '1' : undefined}
                        role={allarme ? 'alert' : undefined}
                    >
                        <span className="text-emerald-300 font-semibold" data-testid="cr-chiuse-certezza-confermate">
                            {riepilogoCert.confermate} {riepilogoCert.confermate === 1 ? 'chiusa confermata' : 'chiuse confermate'}
                        </span>
                        {riepilogoCert.conEsposizione > 0 && (
                            <span className="text-orange-300 font-bold" data-testid="cr-chiuse-certezza-esposte">
                                ⚠ {riepilogoCert.conEsposizione} con esposizione residua
                                {riepilogoCert.esposizioneTotale > 0 && (
                                    <> ({fmtMoney(riepilogoCert.esposizioneTotale)})</>
                                )}
                            </span>
                        )}
                        {riepilogoCert.nonVerificabili > 0 && (
                            <span className="text-amber-300 font-semibold" data-testid="cr-chiuse-certezza-non-verificabili">
                                {riepilogoCert.nonVerificabili} non {riepilogoCert.nonVerificabili === 1 ? 'verificabile' : 'verificabili'}
                            </span>
                        )}
                    </div>
                );
            })()}

            {/* «ce ne sono altre, e so dove sono»: il numero dei giorni
                precedenti non sparisce, diventa un invito allo Storico. */}
            {(fuori.altriGiorni > 0 || fuori.senzaData > 0) && (
                <div className="px-3 py-1.5 border-b border-white/10 text-[10.5px] text-white/45"
                    data-testid="cr-chiuse-fuori-giornata">
                    Qui c&apos;è solo <b className="text-white/70">{dayLabel(giorno)}</b>.
                    {fuori.altriGiorni > 0 && (
                        <> Altre <b className="text-white/70">{fuori.altriGiorni}</b> posizioni chiuse
                        sono di giorni precedenti: si guardano nello <b className="text-white/70">Storico</b>.</>
                    )}
                    {fuori.senzaData > 0 && (
                        <> <b className="text-amber-300">{fuori.senzaData}</b> senza data di piazzamento
                        leggibile: non entrano in nessuna giornata.</>
                    )}
                </div>
            )}

            {/* I FILTRI — «filtrabili chiaramente»: si vede sempre quale è attivo */}
            <div className="px-3 py-2 border-b border-white/10 flex flex-wrap items-center gap-x-4 gap-y-1.5">
                <Gruppo etichetta="esito">
                    <Pillola attivo={esito === 'tutte'} onClick={() => setEsito('tutte')} testId="cr-f-esito-tutte">tutte</Pillola>
                    {(['vinta', 'persa', 'pari'] as Esito[]).map((e) => (
                        <Pillola key={e} attivo={esito === e} onClick={() => setEsito(e)} testId={`cr-f-esito-${e}`}>
                            {ESITO_TESTO[e]}
                        </Pillola>
                    ))}
                </Gruppo>

                <Gruppo etichetta="soldi">
                    <Pillola attivo={modo === 'live'} onClick={() => setModo('live')} testId="cr-f-modo-live"
                        titolo="solo operazioni con denaro reale">veri</Pillola>
                    <Pillola attivo={modo === 'paper'} onClick={() => setModo('paper')} testId="cr-f-modo-paper"
                        titolo="solo operazioni simulate">prova</Pillola>
                    <Pillola attivo={modo === 'tutte'} onClick={() => setModo('tutte')} testId="cr-f-modo-tutte"
                        titolo="ATTENZIONE: mette nella stessa lista soldi veri e simulati; il totale qui sopra li somma">
                        entrambi
                    </Pillola>
                </Gruppo>

                <Gruppo etichetta="bot">
                    <Pillola attivo={bot === 'tutti'} onClick={() => setBot('tutti')} testId="cr-f-bot-tutti">tutti</Pillola>
                    {(['omega', 'safe', 'mike'] as Bot[]).map((b) => (
                        <Pillola key={b} attivo={bot === b} onClick={() => setBot(b)} testId={`cr-f-bot-${b}`}>
                            {BOT_LABEL[b]}
                        </Pillola>
                    ))}
                </Gruppo>
            </div>

            {/* ⚠️ il filtro «entrambi» produce un totale che somma due monete
                diverse: lo si dice, invece di lasciarlo scoprire. */}
            {modo === 'tutte' && r.n > 0 && (
                <div className="px-3 py-1.5 border-b border-orange-500/30 bg-orange-500/10 text-[10.5px] text-orange-300"
                    data-testid="cr-chiuse-avviso-misto">
                    Stai guardando soldi veri e simulati insieme: <strong>il totale qui sopra li somma</strong>.
                    Per un numero su cui ragionare, scegli «veri» o «prova».
                </div>
            )}

            <div className="max-h-[calc(100vh-300px)] overflow-y-auto divide-y divide-white/8">
                {righe.length === 0 && (
                    <div className="p-3">
                        <EmptyState>
                            {chiuse.length === 0
                                ? 'Nessuna posizione ancora chiusa oggi. Quando una si liquida, compare qui con il suo risultato.'
                                : fuori.altriGiorni > 0
                                    ? 'Nessuna posizione chiusa OGGI con questi filtri. Le giornate precedenti sono nello Storico.'
                                    : 'Nessuna posizione con questi filtri. Allargali per rivedere le altre.'}
                        </EmptyState>
                    </div>
                )}

                {certezze.map(({ p, c }) => (
                    <div key={`${p.bot}-${p.id}`} data-testid="cr-chiusa" data-event-id={p.eventId}>
                        <button
                            type="button"
                            onClick={() => setAperta(aperta === p.id ? null : p.id)}
                            aria-expanded={aperta === p.id}
                            data-testid={`cr-chiusa-${p.id}`}
                            className="w-full text-left px-3 py-2 hover:bg-white/[0.03] transition-colors"
                        >
                            <div className="flex items-baseline gap-2">
                                {aperta === p.id
                                    ? <ChevronDown className="w-3 h-3 text-white/30 shrink-0" />
                                    : <ChevronRight className="w-3 h-3 text-white/30 shrink-0" />}
                                <span className="text-[10px]" aria-hidden="true">{p.sport === 'tennis' ? '🎾' : '⚽'}</span>
                                <span className="text-[12px] truncate flex-1 min-w-0">{p.partita}</span>

                                {/* IL BADGE DI CERTEZZA (18/09): verde pieno SOLO per
                                    confermata/regolata, arancione per parziale/attesa/non
                                    verificabile (importo esposto in evidenza), rosso per
                                    fallita — mai un colore come decorazione, sempre un fatto. */}
                                <span
                                    className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border ${certezzaCls(c.stato)}`}
                                    data-testid={`cr-chiusa-certezza-${p.id}`}
                                    data-stato={c.stato}
                                    title={c.motivo}
                                >
                                    {CERTEZZA_LABEL[c.stato]}
                                </span>
                                {c.esposizione.stake != null && c.esposizione.stake > 0.005 && (
                                    <span
                                        className="font-mono text-[10.5px] font-bold text-orange-300 tabular-nums"
                                        data-testid={`cr-chiusa-esposta-${p.id}`}
                                        title="quanto resta esposto a mercato su questa posizione (stake abbinato non ancora compensato)"
                                    >
                                        {fmtMoney(c.esposizione.stake)}
                                    </span>
                                )}

                                <span className={`text-[9px] font-bold uppercase tracking-wider px-1 rounded ${
                                    p.modo === 'live' ? 'bg-red-500/20 text-red-300' : 'bg-white/10 text-white/35'
                                }`}>{p.modo === 'live' ? 'veri' : 'prova'}</span>

                                <span className="text-[9px] uppercase tracking-wider text-white/35">{BOT_LABEL[p.bot]}</span>

                                {/* IL NUMERO CHE CONTA: la posizione INTERA */}
                                <span className={`font-mono text-[14px] font-bold tabular-nums ${ESITO_CLS[p.esito]}`}
                                    data-testid={`cr-chiusa-pnl-${p.id}`}
                                    data-orfana={p.orfana ? 'true' : undefined}
                                    title={p.orfana
                                        ? "CHIUSURA ORFANA: la sua apertura non e' fra le righe lette. Questo e' il P&L della sola gamba di chiusura, non il netto dell'operazione"
                                        : 'P&L della POSIZIONE intera: apertura e coperture insieme'}>
                                    {fmtMoney(p.pnlGlobale, { signed: true })}
                                </span>

                                <span className="text-[9px] text-white/25 font-mono w-10 text-right">
                                    {p.chiusaAt ? fmtTime(p.chiusaAt) : DASH}
                                </span>
                            </div>

                            {/* SINTESI ingresso→chiusura, SEMPRE visibile (18/09): quota e
                                stake d'ingresso, quota MEDIA e stake ABBINATO in chiusura,
                                ora d'ingresso — senza dover aprire il dettaglio. */}
                            {(() => {
                                const s = sintesiPosizione(p);
                                return (
                                    <div
                                        className="pl-6 text-[9.5px] text-white/35 mt-0.5 flex flex-wrap gap-x-2"
                                        data-testid={`cr-chiusa-sintesi-${p.id}`}
                                    >
                                        <span>ingresso <span className="font-mono text-white/55">{fmtOdds(s.ingresso.prezzo)}</span>{' '}
                                            per <span className="font-mono text-white/55">{fmtMoney(s.ingresso.stake)}</span></span>
                                        {s.chiusura != null && (
                                            <span>· chiusura media <span className="font-mono text-white/55">{fmtOdds(s.chiusura.prezzoMedio)}</span>{' '}
                                                abbinati <span className="font-mono text-white/55">{fmtMoney(s.chiusura.stake)}</span></span>
                                        )}
                                        <span>· entrata <span className="font-mono text-white/55">{s.ingresso.at ? fmtTime(s.ingresso.at) : DASH}</span></span>
                                    </div>
                                );
                            })()}

                            {/* UNA GAMBA ANNULLATA (rifiutata/annullata da Betfair) resta
                                visibile SENZA aprire il dettaglio: e' il pezzo di una
                                chiusura a piu' pezzi che non e' andato a mercato. */}
                            {gambeAnnullate(p) > 0 && (
                                <div
                                    className="pl-6 text-[9.5px] text-amber-300 mt-0.5"
                                    data-testid={`cr-chiusa-copertura-incompleta-${p.id}`}
                                >
                                    ⚠ {gambeAnnullate(p)} {gambeAnnullate(p) === 1
                                        ? 'gamba di chiusura annullata'
                                        : 'gambe di chiusura annullate'}: non {gambeAnnullate(p) === 1 ? 'è andata' : 'sono andate'} a mercato.
                                </div>
                            )}

                            {p.righe.length > 1 && aperta !== p.id && (
                                <div className="pl-6 text-[9.5px] text-white/30 mt-0.5">
                                    {p.righe.length} righe — apertura e {p.righe.length - 1}{' '}
                                    {p.righe.length === 2 ? 'copertura' : 'coperture'}: clicca per il dettaglio
                                </div>
                            )}
                        </button>

                        {aperta === p.id && (
                            <div className="px-3 pb-2 pl-6 space-y-1" data-testid={`cr-chiusa-dettaglio-${p.id}`}>
                                {p.righe.map((riga) => (
                                    <div key={riga.id} className="flex items-baseline gap-1.5 text-[11px] flex-wrap">
                                        <span className={`text-[9px] font-bold uppercase tracking-wider px-1 rounded ${
                                            riga.lato === 'lay' ? 'bg-pink-500/15 text-pink-300' : 'bg-sky-500/15 text-sky-300'
                                        }`}>{riga.lato === 'lay' ? 'banca' : 'punta'}</span>
                                        {riga.chiusura && (
                                            <span className="text-[9px] uppercase tracking-wider text-white/35"
                                                title="gamba di copertura: chiude l’apertura qui sopra">copertura</span>
                                        )}
                                        <span className="text-white/70 truncate max-w-[9rem]">{riga.selezione ?? DASH}</span>
                                        <span className="font-mono text-white/55">{fmtOdds(riga.prezzo)}</span>
                                        <span className="font-mono text-white/40">{fmtMoney(riga.size)}</span>
                                        {/* C.12b (16/09) — chiesto / abbinato / residuo: la
                                            Control Room non mostrava ne' l'abbinato ne' il
                                            residuo, e `size` da sola dopo la conferma e'
                                            l'abbinato, non quello che era stato chiesto. */}
                                        <StatoOrdineCompatto riga={riga.ordine} testId="cr-chiusa-stato-ordine" />
                                        {riga.quale && <span className="text-[9px] text-white/25 uppercase">{riga.quale}</span>}
                                        <span className={`ml-auto font-mono ${pnlClass(riga.pnl)}`}>
                                            {riga.pnl == null ? DASH : fmtMoney(riga.pnl, { signed: true })}
                                        </span>
                                    </div>
                                ))}
                                {p.righe.length > 1 && (
                                    <div className="text-[10px] text-white/35 pt-1 border-t border-white/8">
                                        Le righe sopra si compensano: la posizione ha reso{' '}
                                        <span className={`font-mono font-semibold ${ESITO_CLS[p.esito]}`}>
                                            {fmtMoney(p.pnlGlobale, { signed: true })}
                                        </span>.
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                ))}
            </div>
        </Card>
    );
}

function Gruppo({ etichetta, children }: { etichetta: string; children: React.ReactNode }) {
    return (
        <span className="flex items-center gap-1">
            <span className="text-[9.5px] uppercase tracking-wider text-white/30 mr-0.5">{etichetta}</span>
            {children}
        </span>
    );
}

function Pillola({ attivo, onClick, children, testId, titolo }: {
    attivo: boolean; onClick: () => void; children: React.ReactNode;
    testId: string; titolo?: string;
}) {
    return (
        <button
            type="button" onClick={onClick} aria-pressed={attivo} data-testid={testId} title={titolo}
            className={`text-[10px] px-1.5 py-0.5 rounded border transition-colors ${
                attivo
                    ? 'border-primary/60 text-primary bg-primary/10'
                    : 'border-white/15 text-white/45 hover:text-white/80'
            }`}
        >{children}</button>
    );
}

export default PosizioniChiuse;
