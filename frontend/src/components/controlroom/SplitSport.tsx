// ============================================================================
// SplitSport.tsx — CALCIO E TENNIS, SEPARATI E LEGGIBILI.
//
// Richiesta dell'utente: «non c'è distinzione tra guadagno del tennis e del
// calcio». Oggi il tennis opera con **soldi veri** e il calcio in **prova**:
// sommarli in un numero solo non è una semplificazione, è una bugia.
//
// DISEGNO — due entità, quindi due identità fisse: ogni sport tiene **sempre**
// lo stesso colore, anche quando uno dei due è a zero (il colore segue
// l'entità, mai il suo rango).
//
// 26/09 (F-2, e2e fase 3): i numeri arrivano dalle STESSE righe della barra e
// delle Posizioni chiuse (`perSportGiornata`, giorno di REGOLAMENTO, tutti i
// bot). Prima venivano da `get_safe_daily.by_sport` (giorno di PIAZZAMENTO,
// sola tabella di Safe): stesso denaro, due giornate diverse sulla pagina.
//
// 30/09 (P2, progetto monitor veritiero §3) — DUE CORSIE FISSE, LIVE sopra e
// PROVA sotto. La tessera aveva UNA «modalita' dello sport» presa dal solo
// Safe: con Mike in LIVE sul calcio scriveva «MODALITA' PAPER», ed era falso.
// Ora ogni bot dello sport e' elencato nella corsia della SUA modalita'
// (`lib/giornataCorsie.ts`), i due numeri stanno ciascuno nella sua corsia e
// non si sommano mai; con un bot LIVE acceso (o una posizione LIVE aperta) la
// tessera lo grida: «SOLDI VERI».
// ============================================================================
import { Card } from '@/components/ui/card';
import { fmtMoney, fmtPct, DASH } from '@/lib/format';
import { pnlClass } from '@/lib/tradeStatus';
import type { DailyBreakdown } from '@/lib/dailyHistory';
import type { CorsieSport, VoceCorsia } from '@/lib/giornataCorsie';
import { MarchioSoldi } from '@/components/controlroom/MarchioSoldi';
import { etichettaArretrati, type ProvaGiornata } from '@/lib/provaGiornata';
import type { ReactNode } from 'react';

/** Identità fissa per sport: il colore segue l'entità, non il rango. */
const SPORT = {
    calcio: { nome: 'Calcio', icona: '⚽', accento: 'text-sky-300', bordo: 'border-sky-400/30', fondo: 'bg-sky-400/[0.06]' },
    tennis: { nome: 'Tennis', icona: '🎾', accento: 'text-secondary', bordo: 'border-secondary/30', fondo: 'bg-secondary/[0.06]' },
} as const;

export type SportKey = keyof typeof SPORT;

export interface SplitSportProps {
    /** sport selezionato: filtra tutto il resto della pagina. `null` = tutti */
    selezionato: SportKey | null;
    /** clic sulla tessera: seleziona, o deseleziona se già selezionata */
    onSeleziona: (s: SportKey | null) => void;
    /** aggregati per sport con i SOLDI VERI; `null` = non letti */
    perSport: Record<string, DailyBreakdown> | null;
    /** Gli stessi aggregati IN PROVA. I due non si sommano mai. */
    perSportPaper?: Record<string, DailyBreakdown> | null;
    /**
     * 30/09 (P2) — i bot di ogni sport divisi per modalita' dichiarata
     * (`corsiePerSport`). `null`/assente = righe dei bot non lette: la
     * tessera lo dice, non inventa una modalita'.
     */
    corsie?: Record<SportKey, CorsieSport> | null;
    /** posizioni aperte per sport, **divise per modalità**: «2 aperte» senza
     *  dire con che soldi non è un'informazione, è un'ambiguità */
    aperte?: Record<SportKey, { live: number; paper: number }>;
    /**
     * 30/09 (P8) — la prova per bot con gli ARRETRATI (partite di giorni
     * precedenti regolate oggi), mostrati sotto la corsia PROVA, a parte.
     * Assente = nessuna riga di arretrati (comportamento di prima).
     */
    prova?: ProvaGiornata | null;
    /**
     * 30/09 (W_G) - la corsia LIVE dal CONTO Betfair (`per_fonte`): calcio =
     * Mike + Omega + Safe calcio + Scalper, tennis = Safe tennis + bot tennis.
     * Assente/null = conto non letto: le righe dei bot (marchio BOT), come prima.
     */
    perSportConto?: Record<SportKey, { pnl: number; ordini: number }> | null;
    /** eta' della lettura del conto (s) per il marchio CONTO */
    contoEtaS?: number | null;
    testId?: string;
}

export function SplitSport({
    perSport, perSportPaper = null, corsie = null, aperte, prova = null, selezionato, onSeleziona,
    perSportConto = null, contoEtaS,
    testId = 'cr-split-sport',
}: SplitSportProps) {
    return (
        <div className="grid gap-2 sm:grid-cols-2" data-testid={testId}>
            {(Object.keys(SPORT) as SportKey[]).map((k) => (
                <Tessera
                    key={k}
                    sport={k}
                    dato={perSport?.[k] ?? null}
                    datoPaper={perSportPaper?.[k] ?? null}
                    corsie={corsie?.[k] ?? null}
                    aperte={aperte?.[k] ?? { live: 0, paper: 0 }}
                    prova={prova}
                    conto={perSportConto?.[k] ? { ...perSportConto[k], etaS: contoEtaS } : null}
                    letto={perSport != null}
                    scelto={selezionato === k}
                    spento={selezionato != null && selezionato !== k}
                    onClick={() => onSeleziona(selezionato === k ? null : k)}
                />
            ))}
        </div>
    );
}

function Tessera({ sport, dato, datoPaper, corsie, aperte, prova, conto, letto, scelto, spento, onClick }: {
    sport: SportKey;
    dato: DailyBreakdown | null;
    datoPaper: DailyBreakdown | null;
    corsie: CorsieSport | null;
    aperte: { live: number; paper: number };
    prova: ProvaGiornata | null;
    conto: { pnl: number; ordini: number; etaS: number | null | undefined } | null;
    letto: boolean;
    scelto: boolean;
    spento: boolean;
    onClick: () => void;
}) {
    const s = SPORT[sport];
    // SOLDI VERI: un bot LIVE che sta operando, o una posizione LIVE ancora
    // aperta (anche a bot fermo, i soldi sono sul mercato)
    const soldiVeri = (corsie?.liveAcceso ?? false) || aperte.live > 0;
    // la corsia «principale» (quella che porta `cr-sport-<sport>-pnl`, il testid
    // storico) e' la LIVE se nello sport c'e' un bot LIVE o una posizione LIVE
    const principaleLive = soldiVeri || (corsie?.live.length ?? 0) > 0;

    return (
        <Card
            className={`glass-card p-2.5 transition-all ${soldiVeri ? 'border-red-500/50' : s.bordo} ${soldiVeri ? s.fondo : 'bg-white/[0.02]'} ${
                scelto ? 'ring-2 ring-white/50' : spento ? 'opacity-45' : 'hover:brightness-125'
            }`}
            data-testid={`cr-sport-${sport}`}
        >
            {/* la tessera E' il filtro: clic = «mostrami solo questo sport»,
                secondo clic = torna a vedere tutto. Le proposte di chiusura
                restano visibili comunque: un'uscita non si nasconde dietro un
                filtro. */}
            <button
                type="button" onClick={onClick} aria-pressed={scelto}
                data-testid={`cr-filtro-${sport}`}
                className="w-full text-left focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-white/60 rounded"
                title={scelto ? 'mostra di nuovo tutti gli sport' : `mostra solo ${s.nome.toLowerCase()}`}
            >
            <div className="flex items-baseline gap-2">
                <span aria-hidden="true">{s.icona}</span>
                <span className={`text-[12px] font-bold uppercase tracking-wider ${s.accento}`}>{s.nome}</span>
                {soldiVeri && (
                    <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-red-500/25 text-red-200"
                        data-testid={`cr-sport-${sport}-soldi-veri`}
                        title="almeno un bot opera con soldi veri su questo sport, o c'e' una posizione con soldi veri aperta">
                        soldi veri
                    </span>
                )}
                {!letto && <span className="ml-auto text-[10px] text-white/40">giornata non ancora letta</span>}
            </div>

            <Corsia
                sport={sport} tipo="live" voci={corsie?.live ?? null} dato={dato} letto={letto}
                aperte={aperte.live} principale={principaleLive} conto={conto}
            />
            <Corsia
                sport={sport} tipo="prova" voci={corsie?.prova ?? null} dato={datoPaper} letto={letto}
                aperte={aperte.paper} principale={!principaleLive}
            >
                {prova != null && <ArretratiSport sport={sport} prova={prova} />}
            </Corsia>
            {corsie != null && corsie.ignote.length > 0 && (
                <div className="mt-1 text-[10px] text-amber-300/80" data-testid={`cr-sport-${sport}-ignote`}
                    title="il servizio non dichiara con che soldi opera: non si conta ne' come live ne' come prova">
                    modalità non dichiarata: {corsie.ignote.map((v) => `${v.nome}${statoVoce(v)}`).join(' · ')}
                </div>
            )}
            <div className="text-[9.5px] uppercase tracking-wider mt-1.5 text-white/30">
                {scelto ? 'stai vedendo solo questo — clicca per tutti' : 'clicca per vedere solo questo sport'}
            </div>
            </button>
        </Card>
    );
}

/** « (spento)» / « (non letto)» / «» accanto al nome del bot. */
function statoVoce(v: VoceCorsia): string {
    if (v.acceso === true) return '';
    if (v.acceso === false && v.ultimoModo) return ' (spento · ultimo modo)';
    return v.acceso === false ? ' (spento)' : ' (non letto)';
}

/**
 * 30/09 (P8) — gli ARRETRATI della prova: partite di giorni precedenti
 * regolate oggi (es. al riavvio). Righe a parte, ciascuna con la sua data e
 * l'origine della data; mai dentro il numero di oggi, mai sommate a lui.
 * Arretrati non letti: detto, mai taciuti. Bot per regolamento: detto a schermo.
 */
function ArretratiSport({ sport, prova }: { sport: SportKey; prova: ProvaGiornata }) {
    const gruppi = prova.arretratiPerSport[sport];
    const nonLetti = prova.arretratiNonLetti[sport];
    const regol = prova.perRegolamento[sport];
    if (gruppi.length === 0 && nonLetti.length === 0 && regol.length === 0) return null;
    return (
        <div className="mt-1 space-y-0.5 text-[10px] text-white/45">
            {gruppi.map((g) => (
                <div key={`${g.giorno}|${g.origine}`} className="flex items-baseline gap-1.5 flex-wrap"
                    data-testid={`cr-sport-${sport}-arretrati`}>
                    <span className="text-white/55">arretrati regolati oggi</span>
                    <span className={`font-mono ${pnlClass(g.pnl)} opacity-70`}>{fmtMoney(g.pnl, { signed: true })}</span>
                    <MarchioSoldi fonte="prova" testId={`cr-sport-${sport}-arretrati-fonte`} />
                    <span>({etichettaArretrati(g)})</span>
                    <span className="text-white/30">— fuori dalle cifre di oggi</span>
                </div>
            ))}
            {nonLetti.length > 0 && (
                <div className="text-amber-300/80" data-testid={`cr-sport-${sport}-arretrati-non-letti`}>
                    arretrati di {nonLetti.join(', ')}: non letti
                </div>
            )}
            {regol.length > 0 && (
                <div data-testid={`cr-sport-${sport}-per-regolamento`}>
                    {regol.join(', ')}: per giorno come lo pubblica il servizio (regolamento, o partita se la migrazione del 30/09 e' applicata)
                </div>
            )}
        </div>
    );
}

function Corsia({ sport, tipo, voci, dato, letto, aperte, principale, conto = null, children }: {
    sport: SportKey;
    tipo: 'live' | 'prova';
    voci: VoceCorsia[] | null;
    dato: DailyBreakdown | null;
    letto: boolean;
    aperte: number;
    principale: boolean;
    // W_G: la corsia LIVE dal CONTO (per_fonte), quando letto; null = righe dei bot
    conto?: { pnl: number; ordini: number; etaS: number | null | undefined } | null;
    children?: ReactNode;
}) {
    const live = tipo === 'live';
    const dalConto = live && conto != null;
    // «non ancora letto» e «nessuna operazione» sono due cose diverse: la prima
    // e' un trattino, la seconda uno zero legittimo (26/09, F-3).
    const pnl = dalConto ? conto!.pnl : dato ? dato.pnl : (letto ? 0 : null);
    const esiti = dato ? dato.won + dato.lost : 0;
    const winRate = dato && esiti > 0 ? dato.won / esiti : null;
    // la PROVA non deve somigliare ai soldi veri nemmeno a colpo d'occhio:
    // piu' piccola, attenuata, bordo tratteggiato, sempre SOTTO la LIVE
    const numero = (
        <span className={`font-mono font-bold tabular-nums ${live ? 'text-xl' : 'text-base opacity-70'} ${pnlClass(pnl)}`}
            data-testid={`cr-sport-${sport}-${tipo}-pnl`}>
            {!letto && !dalConto ? DASH : fmtMoney(pnl, { signed: true })}
        </span>
    );
    return (
        <div className={`mt-1.5 rounded px-1.5 py-1 ${live
            ? 'bg-red-500/[0.07] border border-red-500/30'
            : 'bg-transparent border border-dashed border-white/15'}`}
            data-testid={`cr-sport-${sport}-${tipo}`}>
            <div className="flex items-baseline gap-2 flex-wrap">
                <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${
                    live ? 'bg-red-500/20 text-red-300' : 'bg-white/10 text-white/55'}`}
                    title={live ? 'soldi veri: ordini reali su Betfair' : 'simulato sui prezzi veri: mai sommato ai soldi veri'}>
                    {live ? 'LIVE' : 'PROVA'}
                </span>
                <span className="text-[10.5px] text-white/70 min-w-0" data-testid={`cr-sport-${sport}-${tipo}-bot`}>
                    {voci == null ? <span className="text-white/35">bot non letti</span>
                        : voci.length === 0 ? <span className="text-white/35">{live ? 'nessun bot in live' : 'nessun bot in prova'}</span>
                            : voci.map((v, i) => (
                                <span key={v.chiave} className={v.acceso === true ? '' : 'text-white/35'}>
                                    {i > 0 ? ' · ' : ''}{v.nome}{statoVoce(v)}
                                </span>
                            ))}
                </span>
                {aperte > 0 && (
                    <span className={`ml-auto text-[10px] ${live ? 'text-red-300' : 'text-white/35'}`}
                        title={live ? 'posizioni con soldi veri' : 'posizioni simulate'}>
                        {`${aperte} ${aperte === 1 ? 'partita' : 'partite'} con posizione ${live ? 'LIVE' : 'in prova'}`}
                    </span>
                )}
            </div>
            <div className="flex items-baseline gap-2 flex-wrap mt-0.5">
                {!live && <span className="text-[9.5px] uppercase tracking-wider text-white/40">partite di oggi</span>}
                {principale ? <span data-testid={`cr-sport-${sport}-pnl`}>{numero}</span> : numero}
                {/* la FONTE della cifra: LIVE = righe dei bot regolate oggi (la
                    parte regolata e' quella del conto Betfair, il resto e' la
                    chiusura dichiarata dal bot); PROVA = simulato */}
                <MarchioSoldi
                    fonte={dalConto ? 'conto' : live ? 'bot' : 'prova'}
                    etaS={dalConto ? conto!.etaS : undefined}
                    testId={`cr-sport-${sport}-${tipo}-fonte`}
                    dettaglio={dalConto
                        ? 'netto regolato oggi dal conto Betfair (voci dei bot di questo sport)'
                        : live
                        ? 'somma delle operazioni con soldi veri regolate oggi, dalle righe dei bot'
                        : 'operazioni simulate sulle partite di OGGI, regolate oggi: non entra nell\'obiettivo'}
                />
                <span className="text-[10.5px] text-white/45 flex items-baseline gap-2 flex-wrap">
                    {dalConto ? (
                        <span data-testid={`cr-sport-${sport}-live-conto`}>{conto!.ordini > 0
                            ? `${conto!.ordini} ${conto!.ordini === 1 ? 'ordine regolato' : 'ordini regolati'} oggi`
                            : 'nessuna operazione regolata oggi'}</span>
                    ) : !letto ? null : !dato || dato.n === 0 ? (
                        <span>nessuna operazione {live ? 'con soldi veri' : 'in prova'} oggi</span>
                    ) : (
                        <>
                            <span><span className="font-mono text-white/70">{dato.n}</span> {dato.n === 1 ? 'operazione' : 'operazioni'}</span>
                            <span className="text-emerald-400/80 font-mono">{dato.won} V</span>
                            <span className="text-red-400/80 font-mono">{dato.lost} P</span>
                            {winRate != null && (
                                <span title="vinte su vinte+perse">{fmtPct(winRate, 0)}</span>
                            )}
                        </>
                    )}
                </span>
            </div>
            {children}
        </div>
    );
}

export default SplitSport;
