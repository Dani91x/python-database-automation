// ============================================================================
// PosizioniChiuse.tsx - LA SCHEDA DELLE POSIZIONI CHIUSE.
//
// "qui ci andranno tutte le posizioni VINCENTI E PERDENTI, filtrabili
// chiaramente, PNL GLOBALE DELLA POSIZIONE, pnl dettaglio" (utente, 14/09).
//
// 24/09 - RIFATTA su ordine dell'utente: "e' LENTISSIMO nel caricamento, i
// dati sono mischiati per giornata, sono confusionari e il trader non capisce
// assolutamente nulla. IL TRADER DEVE FIDARSI DI QUELLO CHE VEDE."
//
// UNA REGOLA, per calcio e tennis (`lib/posizioniChiuse.ts::raggruppaGiornata`):
//   giornata di REGOLAMENTO (Roma) -> bot -> partita -> ciclo (operazione)
// ogni livello con il suo netto e la sua FONTE (Betfair / stimato / prova).
//
//   - UNA giornata alla volta, scelta qui (oggi di serie). Oggi si vede
//     SUBITO con le righe gia' in memoria; il database si legge una giornata
//     alla volta e il risultato si memorizza (`lib/chiuseGiornata.ts`).
//   - UNA modalita' alla volta: soldi veri OPPURE prova, mai insieme.
//   - Ogni cifra dice da dove viene; ogni riga orfana o a ripiego (bot tennis,
//     reperto B13) lo dichiara.
//   - Il totale della giornata si CONFRONTA con la barra (controprova).
// ============================================================================
import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Card } from '@/components/ui/card';
import { ChevronRight, ChevronDown } from 'lucide-react';
import { EmptyState } from '@/components/trading/EmptyState';
import { StoricoLink } from '@/components/trading/StoricoLink';
import { fmtMoney, fmtOdds, fmtPct, fmtTime, DASH } from '@/lib/format';
import { pnlClass } from '@/lib/tradeStatus';
import { StatoOrdineCompatto } from '@/components/trading/StatoOrdine';
import { BOT_LABEL, type Bot, type Modo } from '@/lib/controlRoom';
import { addDays, dayLabel, isValidDay } from '@/lib/dailyHistory';
import {
    filtraChiuse, fuoriGiornata, raggruppaGiornata, unisciRighe,
    posizioniChiuse, certezzaDiPosizione, gambeAnnullate, sintesiPosizione,
    type PosizioneChiusa, type Esito, type TradeChiudibile, type RiepilogoChiuse,
    type GruppoBot, type GruppoPartita,
} from '@/lib/posizioniChiuse';
import { chiuseGiornata, type ChiuseGiornata } from '@/lib/chiuseGiornata';
import type { ComposizioneObiettivo, RigaComposizione } from '@/lib/composizioneObiettivo';
import type { FontePnl } from '@/lib/eventGroups';
import { eCertezzaVerde, type StatoCertezzaChiusura } from '@/lib/certezzaChiusura';

const CERTEZZA_LABEL: Record<StatoCertezzaChiusura, string> = {
    CHIUSA_CONFERMATA: 'CHIUSA \u00b7 CONFERMATA',
    REGOLATA_DAL_MERCATO: 'REGOLATA DAL MERCATO',
    CHIUSA_PARZIALE: 'PARZIALE \u00b7 ESPOSIZIONE RESIDUA',
    CHIUSURA_IN_ATTESA: 'IN ATTESA DI ABBINAMENTO',
    CHIUSURA_FALLITA: 'CHIUSURA FALLITA \u00b7 ANCORA APERTA',
    NON_VERIFICABILE: 'NON VERIFICABILE',
};

function certezzaCls(stato: StatoCertezzaChiusura): string {
    if (eCertezzaVerde(stato)) return 'bg-emerald-500/20 text-emerald-300 border-emerald-500/50';
    if (stato === 'CHIUSURA_FALLITA') return 'bg-red-500/20 text-red-300 border-red-500/60';
    return 'bg-amber-500/20 text-amber-300 border-amber-500/50'; // parziale/attesa/non verificabile
}

const PUNTO = '\u00b7';
const ALLARME = '\u26a0';

const ESITO_TESTO: Record<Esito, string> = { vinta: 'vinte', persa: 'perse', pari: 'pari' };
const ESITO_UNO: Record<Esito, string> = { vinta: 'vinta', persa: 'persa', pari: 'pari' };
const ESITO_CLS: Record<Esito, string> = {
    vinta: 'text-emerald-400', persa: 'text-red-400', pari: 'text-white/45',
};

/** i bot nell'ordine dei filtri: calcio poi tennis */
const BOT_FILTRO: readonly Bot[] = [
    'omega', 'safe', 'mike', 'tennis_scalper', 'tennis_pro', 'tennis_flb', 'tennis_swing',
];

/** le voci della barra che corrispondono alle posizioni dei bot (niente
 *  manuale sito/app ne' "altro sul conto": non sono posizioni di questa scheda) */
const VOCI_BARRA: readonly RigaComposizione['chiave'][] = [
    'omega', 'safe_calcio', 'safe_tennis', 'mike', 'bot_tennis', 'manuale',
];

/** oltre questo numero di operazioni le partite partono chiuse (velocita') */
export const SOGLIA_PARTITE_APERTE = 40;

export type LeggiGiornata = (giorno: string, modo: Modo, forza?: boolean) => Promise<ChiuseGiornata>;

export interface PosizioniChiuseProps {
    /** le righe GREZZE dei bot gia' in memoria (lettura dei 30 s + canali) */
    righe?: readonly TradeChiudibile[];
    /** le posizioni gia' costruite dalle stesse `righe` (il VM le ha): se ci
     *  sono non si ricostruiscono finche' il database non aggiunge righe */
    chiuse?: readonly PosizioneChiusa[];
    /** lo sport scelto in cima alla pagina; null = tutti */
    sport: 'calcio' | 'tennis' | null;
    /** OGGI, 'YYYY-MM-DD' (Europe/Rome): la giornata di partenza */
    giorno: string;
    /** la composizione della barra di giornata (controprova) */
    barra?: ComposizioneObiettivo | null;
    /** lettura di una giornata dal database; di serie `lib/chiuseGiornata` */
    leggiGiornata?: LeggiGiornata;
    testId?: string;
}

interface StatoLettura {
    chiave: string;
    stato: 'attesa' | 'pronto' | 'errore';
    dati: ChiuseGiornata | null;
    errore: string | null;
}

const NIENTE: readonly TradeChiudibile[] = [];

export function PosizioniChiuse({
    righe = NIENTE, chiuse, sport, giorno, barra = null, leggiGiornata, testId = 'cr-chiuse',
}: PosizioniChiuseProps) {
    const [giornoScelto, setGiornoScelto] = useState(giorno);
    const [modo, setModo] = useState<Modo>('live');
    const [esito, setEsito] = useState<Esito | 'tutte'>('tutte');
    const [bot, setBot] = useState<Bot | 'tutti'>('tutti');
    const [fonte, setFonte] = useState<'tutte' | 'betfair'>('tutte');
    const [aperte, setAperte] = useState<Record<string, boolean>>({});
    const [dettaglio, setDettaglio] = useState<string | null>(null);
    const [giro, setGiro] = useState(0);

    // la giornata scelta segue "oggi" finche' il trader non ne sceglie un'altra
    const [seguiOggi, setSeguiOggi] = useState(true);
    useEffect(() => { if (seguiOggi) setGiornoScelto(giorno); }, [giorno, seguiOggi]);
    const scegliGiorno = useCallback((g: string) => {
        if (!isValidDay(g)) return;
        const limitato = g > giorno ? giorno : g;
        setGiornoScelto(limitato);
        setSeguiOggi(limitato === giorno);
        setAperte({});
        setDettaglio(null);
    }, [giorno]);

    // -- LA LETTURA DELLA GIORNATA (una alla volta, memorizzata) -------------
    const leggi = useMemo<LeggiGiornata>(
        () => leggiGiornata ?? ((g, m, forza) => chiuseGiornata(g, m, { oggi: giorno, forza })),
        [leggiGiornata, giorno],
    );
    const chiaveLettura = `${giornoScelto}|${modo}`;
    const [lettura, setLettura] = useState<StatoLettura>({ chiave: '', stato: 'attesa', dati: null, errore: null });
    // "rileggi" forza UNA lettura, non tutte quelle che seguono
    const forzaProssima = useRef(false);
    useEffect(() => {
        let vivo = true;
        const forza = forzaProssima.current;
        forzaProssima.current = false;
        setLettura((prec) => ({
            chiave: chiaveLettura, stato: 'attesa',
            dati: prec.chiave === chiaveLettura ? prec.dati : null, errore: null,
        }));
        leggi(giornoScelto, modo, forza).then(
            (dati) => { if (vivo) setLettura({ chiave: chiaveLettura, stato: 'pronto', dati, errore: null }); },
            (e: unknown) => {
                if (vivo) {
                    setLettura({
                        chiave: chiaveLettura, stato: 'errore', dati: null,
                        errore: e instanceof Error ? e.message : String(e),
                    });
                }
            },
        );
        return () => { vivo = false; };
    }, [leggi, giornoScelto, modo, chiaveLettura, giro]);
    const datiDb = lettura.chiave === chiaveLettura ? lettura.dati : null;

    // -- LE POSIZIONI: memoria + giornata letta, costruite UNA volta ---------
    const posizioni = useMemo<readonly PosizioneChiusa[]>(() => {
        if (datiDb && datiDb.righe.length) return posizioniChiuse(unisciRighe(righe, datiDb.righe));
        return chiuse ?? posizioniChiuse(righe);
    }, [righe, chiuse, datiDb]);

    const filtroBase = useMemo(
        () => ({ modo, sport: sport ?? 'tutti' as const }),
        [modo, sport],
    );
    const visibili = useMemo(
        () => filtraChiuse(posizioni, { ...filtroBase, esito, bot, fonte: modo === 'live' ? fonte : 'tutte', giorno: giornoScelto }),
        [posizioni, filtroBase, esito, bot, fonte, modo, giornoScelto],
    );
    const gruppi = useMemo(() => raggruppaGiornata(giornoScelto, visibili), [giornoScelto, visibili]);
    const r = gruppi.riepilogo;
    const fuori = useMemo(
        () => fuoriGiornata(filtraChiuse(posizioni, filtroBase), giornoScelto),
        [posizioni, filtroBase, giornoScelto],
    );
    const daPiazzamento = useMemo(() => visibili.filter((p) => p.giornoDa === 'piazzamento').length, [visibili]);

    // LA CERTEZZA DI CHIUSURA (18/09): riepilogo delle righe visibili, UNA
    // modalita' alla volta per costruzione.
    const riepilogoCert = useMemo(() => {
        if (visibili.length === 0) return null;
        let confermate = 0, conEsposizione = 0, nonVerificabili = 0, esposizioneTotale = 0;
        for (const p of visibili) {
            const c = certezzaDiPosizione(p);
            if (eCertezzaVerde(c.stato)) confermate += 1;
            else if (c.stato === 'NON_VERIFICABILE') nonVerificabili += 1;
            else conEsposizione += 1;
            if (c.esposizione.stake != null && c.esposizione.stake > 0.005) {
                esposizioneTotale = Math.round((esposizioneTotale + c.esposizione.stake) * 100) / 100;
            }
        }
        return { n: visibili.length, confermate, conEsposizione, nonVerificabili, esposizioneTotale };
    }, [visibili]);

    // -- CONTROPROVA CON LA BARRA (oggi, soldi veri, nessun filtro) ----------
    const controprova = useMemo(() => {
        if (!barra || giornoScelto !== giorno || modo !== 'live' || sport != null
            || bot !== 'tutti' || esito !== 'tutte' || fonte !== 'tutte') return null;
        let somma: number | null = null;
        for (const v of barra.righe) {
            if (!VOCI_BARRA.includes(v.chiave) || v.valore == null) continue;
            somma = Math.round(((somma ?? 0) + v.valore) * 100) / 100;
        }
        if (somma == null && r.totale == null) return null;
        const qui = r.totale ?? 0;
        const differenza = Math.round((qui - (somma ?? 0)) * 100) / 100;
        return { barra: somma, qui, differenza };
    }, [barra, giornoScelto, giorno, modo, sport, bot, esito, fonte, r.totale]);

    const apriTutte = visibili.length <= SOGLIA_PARTITE_APERTE;
    const partitaAperta = useCallback(
        (k: string) => aperte[k] ?? apriTutte, [aperte, apriTutte]);
    const toggle = useCallback((k: string) => {
        setAperte((prec) => ({ ...prec, [k]: !(prec[k] ?? apriTutte) }));
    }, [apriTutte]);
    const toggleDettaglio = useCallback((k: string) => {
        setDettaglio((prec) => (prec === k ? null : k));
    }, []);

    const eOggi = giornoScelto === giorno;

    return (
        <Card className="glass-card border-white/10 p-0 overflow-hidden" data-testid={testId}>
            {/* IL RIEPILOGO - descrive le righe qui sotto, non tutto lo storico */}
            <div className="px-3 py-2 border-b border-white/10 flex items-baseline gap-3 flex-wrap">
                <span className="text-[11px] uppercase tracking-wider text-white/60">Posizioni chiuse</span>
                <span
                    className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-primary/15 text-primary"
                    data-testid="cr-chiuse-giornata"
                    title={`giornata ${dayLabel(giornoScelto)} (Europe/Rome), per giorno di REGOLAMENTO`}
                >
                    {eOggi ? 'Oggi' : dayLabel(giornoScelto, { weekday: true })} {PUNTO} {r.n} {r.n === 1 ? 'chiusa' : 'chiuse'}
                </span>
                <span className={`font-mono text-[15px] font-bold tabular-nums ${pnlClass(r.totale)}`}
                    data-testid="cr-chiuse-totale">
                    {r.totale == null ? DASH : fmtMoney(r.totale, { signed: true })}
                </span>
                {r.totale != null && <FonteTag modo={modo} riepilogo={r} testId="cr-chiuse-totale-fonte" />}
                <span className="text-[10.5px] text-white/45 flex items-baseline gap-2">
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

            {/* DI COSA E' FATTO IL TOTALE: reale di Betfair e stimato, separati */}
            {modo === 'live' && r.totale != null && (
                <div className="px-3 py-1 border-b border-white/10 text-[10.5px] text-white/45 flex flex-wrap gap-x-3"
                    data-testid="cr-chiuse-composizione">
                    <span>regolato da Betfair{' '}
                        <b className={`font-mono ${pnlClass(r.reale ?? null)}`} data-testid="cr-chiuse-reale">
                            {r.reale == null ? DASH : fmtMoney(r.reale, { signed: true })}
                        </b>
                    </span>
                    <span>stimato (calcolo del bot, Betfair non ha ancora regolato){' '}
                        <b className={`font-mono ${r.stimato == null ? 'text-white/45' : 'text-amber-300'}`}
                            data-testid="cr-chiuse-stimato">
                            {r.stimato == null ? DASH : fmtMoney(r.stimato, { signed: true })}
                        </b>
                    </span>
                </div>
            )}

            {controprova && (
                <div
                    className={`px-3 py-1 border-b text-[10.5px] ${Math.abs(controprova.differenza) < 0.005
                        ? 'border-white/10 text-emerald-300/80'
                        : 'border-orange-500/30 bg-orange-500/10 text-orange-300'}`}
                    data-testid="cr-chiuse-controprova"
                    data-coincide={Math.abs(controprova.differenza) < 0.005 ? '1' : '0'}
                >
                    {Math.abs(controprova.differenza) < 0.005 ? (
                        <>Controprova con la barra di giornata: <b>coincide</b> ({fmtMoney(controprova.barra, { signed: true })}).</>
                    ) : (
                        <>Controprova con la barra: la barra dice{' '}
                            <b className="font-mono">{fmtMoney(controprova.barra, { signed: true })}</b>, qui{' '}
                            <b className="font-mono">{fmtMoney(controprova.qui, { signed: true })}</b>: differenza{' '}
                            <b className="font-mono" data-testid="cr-chiuse-controprova-diff">
                                {fmtMoney(controprova.differenza, { signed: true })}
                            </b>. Cause tipiche: ordini gia&apos; regolati sul conto Betfair ma non ancora scritti
                            sulla riga del bot, righe fuori dalla finestra letta dalla barra, ordini tennis
                            piazzati ieri e regolati oggi.</>
                    )}
                </div>
            )}

            {/* LA CERTEZZA DI CHIUSURA (18/09): se ci sono esposti o non
                verificabili e' un ALLARME visibile, non una statistica in piu'. */}
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
                                {ALLARME} {riepilogoCert.conEsposizione} con esposizione residua
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

            {/* LA GIORNATA E I FILTRI - si vede sempre quale e' attivo */}
            <div className="px-3 py-2 border-b border-white/10 flex flex-wrap items-center gap-x-4 gap-y-1.5">
                <Gruppo etichetta="giornata">
                    <Pillola attivo={false} onClick={() => scegliGiorno(addDays(giornoScelto, -1))}
                        testId="cr-f-giorno-prima" titolo="la giornata precedente">{'\u25c0'}</Pillola>
                    <input
                        type="date" value={giornoScelto} max={giorno}
                        onChange={(e) => scegliGiorno(e.target.value)}
                        data-testid="cr-f-giorno"
                        aria-label="giornata di regolamento da mostrare"
                        className="text-[10px] px-1.5 py-0.5 rounded border border-white/15 bg-white/[0.03] text-white/80"
                    />
                    <Pillola attivo={false} onClick={() => scegliGiorno(addDays(giornoScelto, 1))}
                        testId="cr-f-giorno-dopo" titolo="la giornata successiva" disabilitato={eOggi}>{'\u25b6'}</Pillola>
                    <Pillola attivo={eOggi} onClick={() => scegliGiorno(giorno)} testId="cr-f-giorno-oggi">oggi</Pillola>
                </Gruppo>

                <Gruppo etichetta="soldi">
                    <Pillola attivo={modo === 'live'} onClick={() => setModo('live')} testId="cr-f-modo-live"
                        titolo="solo operazioni con denaro reale">veri</Pillola>
                    <Pillola attivo={modo === 'paper'} onClick={() => setModo('paper')} testId="cr-f-modo-paper"
                        titolo="solo operazioni simulate: non si sommano MAI ai soldi veri">prova</Pillola>
                </Gruppo>

                {modo === 'live' && (
                    <Gruppo etichetta="P&L">
                        <Pillola attivo={fonte === 'tutte'} onClick={() => setFonte('tutte')} testId="cr-f-fonte-tutte"
                            titolo="regolati da Betfair e stimati (dichiarati)">con stimati</Pillola>
                        <Pillola attivo={fonte === 'betfair'} onClick={() => setFonte('betfair')} testId="cr-f-fonte-betfair"
                            titolo="solo operazioni con il netto gia' regolato da Betfair">solo Betfair</Pillola>
                    </Gruppo>
                )}

                <Gruppo etichetta="esito">
                    <Pillola attivo={esito === 'tutte'} onClick={() => setEsito('tutte')} testId="cr-f-esito-tutte">tutte</Pillola>
                    {(['vinta', 'persa', 'pari'] as Esito[]).map((e) => (
                        <Pillola key={e} attivo={esito === e} onClick={() => setEsito(e)} testId={`cr-f-esito-${e}`}>
                            {ESITO_TESTO[e]}
                        </Pillola>
                    ))}
                </Gruppo>

                <Gruppo etichetta="bot">
                    <Pillola attivo={bot === 'tutti'} onClick={() => setBot('tutti')} testId="cr-f-bot-tutti">tutti</Pillola>
                    {BOT_FILTRO.map((b) => (
                        <Pillola key={b} attivo={bot === b} onClick={() => setBot(b)} testId={`cr-f-bot-${b}`}>
                            {BOT_LABEL[b]}
                        </Pillola>
                    ))}
                </Gruppo>
            </div>

            {/* LA LETTURA DAL DATABASE: in corso, caduta o di ripiego si DICE */}
            <StatoLetturaRiga lettura={lettura} chiave={chiaveLettura} eOggi={eOggi}
                onRileggi={() => { forzaProssima.current = true; setGiro((g) => g + 1); }} />

            {/* le note che il trader deve leggere PRIMA dei numeri */}
            {(r.orfane ?? 0) > 0 && (
                <div className="px-3 py-1 border-b border-white/10 text-[10.5px] text-amber-300"
                    data-testid="cr-chiuse-nota-orfane">
                    {ALLARME} {r.orfane} {r.orfane === 1 ? 'chiusura' : 'chiusure'} senza la sua apertura fra le righe lette:
                    il P&L mostrato e&apos; quello della sola gamba, non il netto dell&apos;operazione.
                </div>
            )}
            {(r.ripiego ?? 0) > 0 && (
                <div className="px-3 py-1 border-b border-white/10 text-[10.5px] text-white/50"
                    data-testid="cr-chiuse-nota-ripiego">
                    Bot tennis: il servizio non scrive quale ordine chiude quale (B13). I loro ordini sono
                    raggruppati per bot, mercato e selezione: il netto del gruppo e&apos; esatto, l&apos;abbinamento
                    ingresso-uscita no.
                </div>
            )}
            {daPiazzamento > 0 && (
                <div className="px-3 py-1 border-b border-white/10 text-[10.5px] text-amber-300"
                    data-testid="cr-chiuse-nota-piazzamento">
                    {daPiazzamento} {daPiazzamento === 1 ? 'operazione' : 'operazioni'} senza ora di regolamento:
                    attribuite al giorno di piazzamento.
                </div>
            )}

            {(fuori.altriGiorni > 0 || fuori.senzaData > 0) && (
                <div className="px-3 py-1.5 border-b border-white/10 text-[10.5px] text-white/45"
                    data-testid="cr-chiuse-fuori-giornata">
                    Qui c&apos;e&apos; solo <b className="text-white/70">{dayLabel(giornoScelto)}</b> (giorno di regolamento).
                    {fuori.altriGiorni > 0 && (
                        <> Altre <b className="text-white/70">{fuori.altriGiorni}</b> posizioni chiuse gia&apos; in memoria
                        sono di altre giornate: sceglile qui sopra o apri lo <b className="text-white/70">Storico</b>.</>
                    )}
                    {fuori.senzaData > 0 && (
                        <> <b className="text-amber-300">{fuori.senzaData}</b> senza nessuna data leggibile:
                        non entrano in nessuna giornata.</>
                    )}
                </div>
            )}

            <div className="max-h-[calc(100vh-300px)] overflow-y-auto">
                {visibili.length === 0 && (
                    <div className="p-3">
                        <EmptyState>
                            {lettura.stato === 'attesa' && lettura.chiave === chiaveLettura && !eOggi
                                ? `Lettura di ${dayLabel(giornoScelto)} in corso...`
                                : posizioni.length === 0 && eOggi
                                    ? 'Nessuna posizione ancora chiusa oggi. Quando una si liquida, compare qui con il suo risultato.'
                                    : fuori.altriGiorni > 0 && eOggi
                                        ? 'Nessuna posizione chiusa OGGI con questi filtri. Le giornate precedenti sono nello Storico.'
                                        : 'Nessuna posizione con questi filtri in questa giornata.'}
                        </EmptyState>
                    </div>
                )}

                {gruppi.bots.map((g) => (
                    <BloccoBot key={g.chiave} gruppo={g} modo={modo}
                        partitaAperta={partitaAperta} onToggle={toggle}
                        dettaglio={dettaglio} onDettaglio={toggleDettaglio} />
                ))}
            </div>
        </Card>
    );
}

/** l'etichetta di un gruppo: Safe si divide per sport, come le voci della barra */
function etichettaGruppo(g: GruppoBot): string {
    if (g.bot === 'safe') return `Safe ${g.sport ?? ''}`.trim();
    return BOT_LABEL[g.bot] ?? g.bot;
}

function fonteDiRiepilogo(modo: Modo, r: RiepilogoChiuse): FontePnl | 'misto' {
    if (modo === 'paper') return 'paper';
    if (r.stimato == null) return 'betfair';
    if (r.reale == null) return 'stimato';
    return 'misto';
}

const FONTE_TESTO: Record<FontePnl | 'misto', string> = {
    betfair: 'Betfair', stimato: 'stimato', paper: 'prova', misto: 'Betfair + stimato',
};
const FONTE_CLS: Record<FontePnl | 'misto', string> = {
    betfair: 'text-emerald-300/80', stimato: 'text-amber-300/90', paper: 'text-white/40', misto: 'text-amber-300/90',
};
const FONTE_TITOLO: Record<FontePnl | 'misto', string> = {
    betfair: 'netto regolato da Betfair (profit meno la commissione del mercato)',
    stimato: 'calcolo del bot: Betfair non ha ancora regolato. Diventa il netto di Betfair al regolamento',
    paper: 'simulazione: su Betfair non esiste, e\' sempre il calcolo',
    misto: 'in parte regolato da Betfair e in parte stimato (calcolo del bot)',
};

/** LA FONTE DI UNA CIFRA, sempre accanto alla cifra. */
function FonteTag({ fonte, modo, riepilogo, testId }: {
    fonte?: FontePnl; modo?: Modo; riepilogo?: RiepilogoChiuse; testId?: string;
}) {
    const f: FontePnl | 'misto' = fonte ?? (riepilogo && modo ? fonteDiRiepilogo(modo, riepilogo) : 'stimato');
    return (
        <span className={`text-[9px] font-normal uppercase tracking-wider ${FONTE_CLS[f]}`}
            data-testid={testId} data-fonte={f} title={FONTE_TITOLO[f]}>
            {FONTE_TESTO[f]}
        </span>
    );
}

function StatoLetturaRiga({ lettura, chiave, eOggi, onRileggi }: {
    lettura: StatoLettura; chiave: string; eOggi: boolean; onRileggi: () => void;
}) {
    if (lettura.chiave !== chiave) return null;
    if (lettura.stato === 'attesa') {
        return (
            <div className="px-3 py-1 border-b border-white/10 text-[10.5px] text-white/40" data-testid="cr-chiuse-lettura"
                data-stato="attesa">
                {eOggi
                    ? 'Oggi si vede subito dalla memoria; lettura completa della giornata dal database in corso...'
                    : 'Lettura della giornata dal database in corso...'}
            </div>
        );
    }
    if (lettura.stato === 'errore') {
        return (
            <div className="px-3 py-1 border-b border-orange-500/30 bg-orange-500/10 text-[10.5px] text-orange-300"
                data-testid="cr-chiuse-lettura" data-stato="errore" role="alert">
                Lettura della giornata dal database non riuscita: {lettura.errore}.
                {eOggi ? ' Si vedono solo le righe gia\' in memoria.' : ''}{' '}
                <button type="button" className="underline" onClick={onRileggi} data-testid="cr-chiuse-rileggi">rileggi</button>
            </div>
        );
    }
    const avvisi = lettura.dati?.avvisi ?? [];
    return (
        <div className={`px-3 py-1 border-b text-[10.5px] ${avvisi.length
            ? 'border-amber-500/30 bg-amber-500/10 text-amber-300' : 'border-white/10 text-white/35'}`}
            data-testid="cr-chiuse-lettura" data-stato="pronto" data-fonte={lettura.dati?.fonte}>
            {avvisi.length ? avvisi.join(' ') : 'Giornata letta dal database'}
            {lettura.dati?.lettoAlle ? <> alle {fmtTime(lettura.dati.lettoAlle)}</> : null}.{' '}
            <button type="button" className="underline text-white/50 hover:text-white/80" onClick={onRileggi}
                data-testid="cr-chiuse-rileggi">rileggi</button>
        </div>
    );
}

const BloccoBot = memo(function BloccoBot({ gruppo, modo, partitaAperta, onToggle, dettaglio, onDettaglio }: {
    gruppo: GruppoBot; modo: Modo;
    partitaAperta: (k: string) => boolean; onToggle: (k: string) => void;
    dettaglio: string | null; onDettaglio: (k: string) => void;
}) {
    const r = gruppo.riepilogo;
    return (
        <div className="border-b border-white/10" data-testid={`cr-chiuse-bot-${gruppo.chiave}`}>
            <div className="px-3 py-1.5 bg-white/[0.03] flex items-baseline gap-2">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-white/75">{etichettaGruppo(gruppo)}</span>
                <span className="text-[10px] text-white/40">
                    {r.n} {r.n === 1 ? 'operazione' : 'operazioni'} {PUNTO} {gruppo.partite.length} {gruppo.partite.length === 1 ? 'partita' : 'partite'}
                </span>
                <span className="ml-auto flex items-baseline gap-1.5">
                    <span className={`font-mono text-[12.5px] font-bold tabular-nums ${pnlClass(r.totale)}`}
                        data-testid={`cr-chiuse-bot-totale-${gruppo.chiave}`}>
                        {r.totale == null ? DASH : fmtMoney(r.totale, { signed: true })}
                    </span>
                    <FonteTag modo={modo} riepilogo={r} />
                </span>
            </div>
            {gruppo.partite.map((pt) => {
                const k = `${gruppo.chiave}|${pt.chiave}`;
                return (
                    <BloccoPartita key={k} chiave={k} partita={pt} modo={modo}
                        aperta={partitaAperta(k)} onToggle={onToggle}
                        dettaglio={dettaglio} onDettaglio={onDettaglio} />
                );
            })}
        </div>
    );
});

const BloccoPartita = memo(function BloccoPartita({ chiave, partita, modo, aperta, onToggle, dettaglio, onDettaglio }: {
    chiave: string; partita: GruppoPartita; modo: Modo; aperta: boolean; onToggle: (k: string) => void;
    dettaglio: string | null; onDettaglio: (k: string) => void;
}) {
    const r = partita.riepilogo;
    return (
        <div data-testid="cr-chiuse-partita" data-event-id={partita.eventId}>
            <button type="button" onClick={() => onToggle(chiave)} aria-expanded={aperta}
                data-testid={`cr-chiuse-partita-${chiave}`}
                className="w-full text-left px-3 py-1.5 hover:bg-white/[0.03] transition-colors flex items-baseline gap-2">
                {aperta
                    ? <ChevronDown className="w-3 h-3 text-white/30 shrink-0" />
                    : <ChevronRight className="w-3 h-3 text-white/30 shrink-0" />}
                <span className="text-[10px]" aria-hidden="true">{partita.sport === 'tennis' ? '\u{1F3BE}' : '\u26bd'}</span>
                <span className="text-[12px] truncate flex-1 min-w-0">{partita.partita}</span>
                <span className="text-[10px] text-white/40">{r.n} {r.n === 1 ? 'operazione' : 'operazioni'}</span>
                <span className={`font-mono text-[12px] font-semibold tabular-nums ${pnlClass(r.totale)}`}>
                    {r.totale == null ? DASH : fmtMoney(r.totale, { signed: true })}
                </span>
                <FonteTag modo={modo} riepilogo={r} />
            </button>
            {aperta && (
                <div className="divide-y divide-white/8">
                    {partita.cicli.map((p) => {
                        const k = `${p.bot}-${p.id}`;
                        return (
                            <RigaCiclo key={k} p={p} aperta={dettaglio === k} onToggle={() => onDettaglio(k)} />
                        );
                    })}
                </div>
            )}
        </div>
    );
});

/** UN CICLO (operazione): apertura + chiusure, con il suo netto e la fonte. */
const RigaCiclo = memo(function RigaCiclo({ p, aperta, onToggle }: {
    p: PosizioneChiusa; aperta: boolean; onToggle: () => void;
}) {
    const c = useMemo(() => certezzaDiPosizione(p), [p]);
    const s = useMemo(() => sintesiPosizione(p), [p]);
    const annullate = useMemo(() => gambeAnnullate(p), [p]);
    return (
        <div data-testid="cr-chiusa" data-event-id={p.eventId} data-bot={p.bot}>
            <button
                type="button"
                onClick={onToggle}
                aria-expanded={aperta}
                data-testid={`cr-chiusa-${p.id}`}
                className="w-full text-left pl-8 pr-3 py-1.5 hover:bg-white/[0.03] transition-colors"
            >
                <div className="flex items-baseline gap-2">
                    {aperta
                        ? <ChevronDown className="w-3 h-3 text-white/30 shrink-0" />
                        : <ChevronRight className="w-3 h-3 text-white/30 shrink-0" />}
                    <span className="text-[9px] uppercase tracking-wider text-white/40">{BOT_LABEL[p.bot]}</span>
                    {p.lato && (
                        <span className={`text-[9px] font-bold uppercase tracking-wider px-1 rounded ${
                            p.lato === 'lay' ? 'bg-pink-500/15 text-pink-300' : 'bg-sky-500/15 text-sky-300'
                        }`}>{p.lato === 'lay' ? 'banca' : 'punta'}</span>
                    )}
                    <span className="text-[11px] text-white/75 truncate flex-1 min-w-0" data-testid={`cr-chiusa-mercato-${p.id}`}>
                        {p.mercato ?? 'mercato non indicato'} {PUNTO} {p.selezione ?? 'selezione non indicata'}
                    </span>

                    {/* IL BADGE DI CERTEZZA (18/09) - mai un colore come
                        decorazione, sempre un fatto. */}
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

                    <span className={`text-[9px] uppercase tracking-wider ${ESITO_CLS[p.esito]}`}>{ESITO_UNO[p.esito]}</span>

                    {/* IL NUMERO CHE CONTA: l'operazione INTERA, con la sua fonte */}
                    <span className={`font-mono text-[13px] font-bold tabular-nums ${ESITO_CLS[p.esito]}`}
                        data-testid={`cr-chiusa-pnl-${p.id}`}
                        data-orfana={p.orfana ? 'true' : undefined}
                        title={p.orfana
                            ? "CHIUSURA ORFANA: la sua apertura non e' fra le righe lette. Questo e' il P&L della sola gamba di chiusura, non il netto dell'operazione"
                            : "P&L dell'OPERAZIONE intera: apertura e coperture insieme"}>
                        {fmtMoney(p.pnlGlobale, { signed: true })}
                    </span>
                    <FonteTag fonte={p.fontePnl ?? (p.modo === 'paper' ? 'paper' : 'stimato')}
                        testId={`cr-chiusa-fonte-${p.id}`} />

                    <span className="text-[9px] text-white/35 font-mono w-10 text-right" title="ora di regolamento">
                        {p.chiusaAt ? fmtTime(p.chiusaAt) : DASH}
                    </span>
                </div>

                {/* SINTESI ingresso -> chiusura, SEMPRE visibile (18/09) */}
                <div
                    className="pl-5 text-[9.5px] text-white/35 mt-0.5 flex flex-wrap gap-x-2"
                    data-testid={`cr-chiusa-sintesi-${p.id}`}
                >
                    <span>ingresso <span className="font-mono text-white/55">{fmtOdds(s.ingresso.prezzo)}</span>{' '}
                        per <span className="font-mono text-white/55">{fmtMoney(s.ingresso.stake)}</span></span>
                    {s.chiusura != null && (
                        <span>{PUNTO} chiusura media <span className="font-mono text-white/55">{fmtOdds(s.chiusura.prezzoMedio)}</span>{' '}
                            abbinati <span className="font-mono text-white/55">{fmtMoney(s.chiusura.stake)}</span></span>
                    )}
                    <span>{PUNTO} entrata <span className="font-mono text-white/55">{s.ingresso.at ? fmtTime(s.ingresso.at) : DASH}</span></span>
                    {p.pnlReale != null && p.pnlStimato != null && (
                        <span>{PUNTO} di cui Betfair <span className="font-mono text-white/55">{fmtMoney(p.pnlReale, { signed: true })}</span>{' '}
                            e stimato <span className="font-mono text-amber-300/80">{fmtMoney(p.pnlStimato, { signed: true })}</span></span>
                    )}
                </div>

                {p.orfana && (
                    <div className="pl-5 text-[9.5px] text-amber-300 mt-0.5" data-testid={`cr-chiusa-orfana-${p.id}`}>
                        {ALLARME} chiusura senza apertura fra le righe lette: P&L della sola gamba, non dell&apos;operazione.
                    </div>
                )}
                {p.legame === 'ripiego' && (
                    <div className="pl-5 text-[9.5px] text-white/45 mt-0.5" data-testid={`cr-chiusa-ripiego-${p.id}`}>
                        legame ingresso-uscita non scritto dal bot (B13): {p.righe.length}{' '}
                        {p.righe.length === 1 ? 'ordine' : 'ordini'} raggruppati per bot, mercato e selezione.
                    </div>
                )}
                {annullate > 0 && (
                    <div
                        className="pl-5 text-[9.5px] text-amber-300 mt-0.5"
                        data-testid={`cr-chiusa-copertura-incompleta-${p.id}`}
                    >
                        {ALLARME} {annullate} {annullate === 1
                            ? 'gamba di chiusura annullata'
                            : 'gambe di chiusura annullate'}: non {annullate === 1 ? '\u00e8 andata' : 'sono andate'} a mercato.
                    </div>
                )}
            </button>

            {aperta && (
                <div className="pl-10 pr-3 pb-2 space-y-1" data-testid={`cr-chiusa-dettaglio-${p.id}`}>
                    {p.righe.map((riga) => (
                        <div key={riga.id} className="flex items-baseline gap-1.5 text-[11px] flex-wrap">
                            <span className={`text-[9px] font-bold uppercase tracking-wider px-1 rounded ${
                                riga.lato === 'lay' ? 'bg-pink-500/15 text-pink-300' : 'bg-sky-500/15 text-sky-300'
                            }`}>{riga.lato === 'lay' ? 'banca' : 'punta'}</span>
                            {riga.chiusura && (
                                <span className="text-[9px] uppercase tracking-wider text-white/35"
                                    title="gamba di copertura: chiude l'apertura qui sopra">copertura</span>
                            )}
                            <span className="text-white/70 truncate max-w-[9rem]">{riga.selezione ?? DASH}</span>
                            <span className="font-mono text-white/55">{fmtOdds(riga.prezzo)}</span>
                            <span className="font-mono text-white/40">{fmtMoney(riga.size)}</span>
                            <StatoOrdineCompatto riga={riga.ordine} testId="cr-chiusa-stato-ordine" />
                            {riga.quale && <span className="text-[9px] text-white/25 uppercase">{riga.quale}</span>}
                            <span className="text-[9px] text-white/30 font-mono">{riga.at ? fmtTime(riga.at) : DASH}</span>
                            <span className={`ml-auto font-mono ${pnlClass(riga.pnl)}`}>
                                {riga.pnl == null ? DASH : fmtMoney(riga.pnl, { signed: true })}
                            </span>
                            {riga.pnl != null && riga.fontePnl && <FonteTag fonte={riga.fontePnl} />}
                        </div>
                    ))}
                    {p.righe.length > 1 && (
                        <div className="text-[10px] text-white/35 pt-1 border-t border-white/8">
                            Le righe sopra si compensano: l&apos;operazione ha reso{' '}
                            <span className={`font-mono font-semibold ${ESITO_CLS[p.esito]}`}>
                                {fmtMoney(p.pnlGlobale, { signed: true })}
                            </span>.
                        </div>
                    )}
                </div>
            )}
        </div>
    );
});

function Gruppo({ etichetta, children }: { etichetta: string; children: React.ReactNode }) {
    return (
        <span className="flex items-center gap-1">
            <span className="text-[9.5px] uppercase tracking-wider text-white/30 mr-0.5">{etichetta}</span>
            {children}
        </span>
    );
}

function Pillola({ attivo, onClick, children, testId, titolo, disabilitato }: {
    attivo: boolean; onClick: () => void; children: React.ReactNode;
    testId: string; titolo?: string; disabilitato?: boolean;
}) {
    return (
        <button
            type="button" onClick={onClick} aria-pressed={attivo} data-testid={testId} title={titolo}
            disabled={disabilitato}
            className={`text-[10px] px-1.5 py-0.5 rounded border transition-colors disabled:opacity-30 ${
                attivo
                    ? 'border-primary/60 text-primary bg-primary/10'
                    : 'border-white/15 text-white/45 hover:text-white/80'
            }`}
        >{children}</button>
    );
}

export default PosizioniChiuse;
