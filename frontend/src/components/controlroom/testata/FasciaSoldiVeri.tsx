// ============================================================================
// FasciaSoldiVeri.tsx - P3 (30/09): "SOLDI VERI ADESSO" nella testata.
//
// Al posto di "Esposizione 39,15" (somma LORDA per riga, 4 volte il conto) e
// di "Con posizione 3 / 28" (il 28 era il programma dello scanner):
//   * Esposizione del CONTO, con fonte ed eta' (la stessa cifra della card del
//     saldo, stessa regola, stesso segno);
//   * disponibile, se gia' letto;
//   * rischio LIVE secondo i bot (liability netta DICHIARATA dai servizi),
//     marchio BOT; se un bot con posizioni live non la dichiara separata dal
//     paper lo si scrive, e la somma e' "parziale";
//   * scarto conto <-> bot in ambra quando non tornano (calcolo della pagina,
//     marchio STIMA; mai una causa inventata);
//   * partite con posizione LIVE; piccolo e a parte: in prova e programma
//     dello scanner.
// Conto non letto = "-" con "conto non letto", mai 0,00. Ogni cifra in euro
// porta il suo `MarchioSoldi`.
// Solo presentazione: i numeri arrivano da `vm.soldiVeri` (testata/soldiVeri.ts).
// ============================================================================
import { useState, type ReactNode } from 'react';
import { Eye, EyeOff } from 'lucide-react';
import { fmtMoney, DASH } from '@/lib/format';
import { BOT_LABEL } from '@/lib/controlRoom';
import { MarchioSoldi } from '@/components/controlroom/MarchioSoldi';
import type { SoldiVeriTestata } from './soldiVeri';

/** La preferenza dell'occhio del saldo (la STESSA chiave che usava l'occhio di
 *  `SaldoBetfairCard`, che dal 01/10 non e' piu' montata: chi l'aveva nascosto
 *  li' lo ritrova nascosto qui). Default = VISIBILE. */
export const CHIAVE_SALDO_NASCOSTO = 'cr-saldo-nascosto';

export function leggiSaldoNascosto(): boolean {
    try { return window.localStorage.getItem(CHIAVE_SALDO_NASCOSTO) === '1'; } catch { return false; }
}
function scriviSaldoNascosto(v: boolean): void {
    try { window.localStorage.setItem(CHIAVE_SALDO_NASCOSTO, v ? '1' : '0'); } catch { /* preferenza persa, non bloccante */ }
}

/** 01/10: il saldo nascosto si scrive cosi' (solo la cifra del saldo). */
export const SALDO_NASCOSTO = '\u2022\u2022\u2022\u2022';
const PUNTO = ' \u00b7 ';

function Etichetta({ children }: { children: ReactNode }) {
    return <span className="text-[10px] uppercase tracking-wider text-white/40">{children}</span>;
}

export function FasciaSoldiVeri({ s }: { s: SoldiVeriTestata | undefined }) {
    // 01/10 (ordine dell'utente: "voglio la possibilita' di nascondere il
    // saldo"): l'occhio nasconde SOLO la cifra del saldo (Disponibile);
    // esposizione, rischio e stop restano sempre visibili.
    const [nascosto, setNascosto] = useState(leggiSaldoNascosto);
    const cambiaNascosto = () => setNascosto((prima) => { const dopo = !prima; scriviSaldoNascosto(dopo); return dopo; });
    const conto = s?.conto ?? null;
    const letto = conto?.letto === true;
    const rischio = s?.rischioBot ?? null;
    const partite = s?.partite ?? null;

    // --- esposizione del conto
    const valoreConto = !letto || conto?.esposizione == null
        ? DASH : fmtMoney(conto.esposizione);

    // --- rischio dei bot (perdita massima: col segno del conto, cosi' le due
    //     cifre si leggono nello stesso verso)
    const totale = rischio?.totale ?? null;
    const valoreBot = totale == null ? DASH : fmtMoney(totale === 0 ? 0 : -totale);
    const voci = rischio?.voci ?? [];
    const mancanti = voci.filter((v) => v.valore == null);
    const dettaglioBot = voci
        .map((v) => `${BOT_LABEL[v.bot]}: ${v.valore == null
            ? `non inclusa (${v.nota ?? 'non dichiarata'})`
            : `${fmtMoney(v.valore)}${v.aperteLive ? ` su ${v.aperteLive} posizioni LIVE` : ''}${v.nota ? ` - ${v.nota}` : ''}`}`)
        .join('; ');
    const notaBot = (rischio == null || (totale == null && mancanti.length === 0))
        ? 'posizioni non ancora lette'
        : mancanti.length
            ? `stima parziale: manca ${mancanti.map((v) => BOT_LABEL[v.bot]).join(', ')}`
            : 'solo LIVE, per partita';

    // R_T (30/09): un numero stantio (dichiarato dal servizio) si dice A SCHERMO
    const stantii = voci.filter((v) => v.stantio === true && v.valore != null);

    const scarto = s?.scarto ?? null;

    return (
        <div className="flex items-stretch gap-x-5 gap-y-1 flex-wrap" data-testid="cr-soldi-veri">
            <div className="flex flex-col gap-0.5" data-testid="cr-esposizione-conto"
                title={letto
                    ? `rischio massimo del conto adesso, calcolato da Betfair (tutti i mercati: bot, sito e app). ${conto?.messaggio ?? ''}`
                    : 'il saldo del conto Betfair non e\' ancora stato letto'}>
                <Etichetta>Esposizione conto</Etichetta>
                <span className="font-mono text-sm font-semibold tabular-nums text-orange-400"
                    data-testid="cr-esposizione-conto-valore">{valoreConto}</span>
                <span className="flex items-center gap-1 text-[9.5px] leading-tight" data-testid="cr-esposizione-conto-fonte">
                    {letto ? (
                        <>
                            <MarchioSoldi fonte="conto" etaS={conto?.etaS ?? null}
                                testId="cr-esposizione-conto-marchio"
                                dettaglio={conto?.fonte === 'canale'
                                    ? 'eta\' = ultimo controllo del conto (canale locale)'
                                    : 'eta\' = ultimo CAMBIO della riga del database (scritta solo al cambio)'} />
                            {conto?.fonte === 'database' && <span className="text-white/35">ultimo cambio</span>}
                            {conto?.attenzione && <span className="text-orange-300">non verificato di recente</span>}
                        </>
                    ) : (
                        <>
                            <MarchioSoldi fonte="conto" testId="cr-esposizione-conto-marchio" />
                            <span className="text-orange-300">conto non letto</span>
                        </>
                    )}
                </span>
            </div>

            {letto && conto?.disponibile != null && (
                <div className="flex flex-col gap-0.5" data-testid="cr-disponibile-conto" title="saldo giocabile del conto Betfair">
                    <span className="flex items-center gap-1">
                        <Etichetta>Saldo disponibile</Etichetta>
                        <button type="button" onClick={cambiaNascosto} aria-pressed={nascosto}
                            data-testid="cr-saldo-occhio"
                            title={nascosto ? 'mostra il saldo' : 'nascondi il saldo'}
                            aria-label={nascosto ? 'mostra il saldo' : 'nascondi il saldo'}
                            className="text-white/40 hover:text-white/80">
                            {nascosto ? <EyeOff className="w-3 h-3" aria-hidden /> : <Eye className="w-3 h-3" aria-hidden />}
                        </button>
                    </span>
                    {nascosto ? (
                        <button type="button" onClick={cambiaNascosto} data-testid="cr-disponibile-conto-valore"
                            title="saldo nascosto: clicca per mostrare"
                            className="font-mono text-sm font-semibold tabular-nums text-left text-white/60">
                            {SALDO_NASCOSTO}
                        </button>
                    ) : (
                        <span className="font-mono text-sm font-semibold tabular-nums" data-testid="cr-disponibile-conto-valore">
                            {fmtMoney(conto.disponibile)}
                        </span>
                    )}
                    <span className="text-[9.5px] leading-tight"><MarchioSoldi fonte="conto" testId="cr-disponibile-conto-marchio" /></span>
                </div>
            )}

            <div className="flex flex-col gap-0.5" data-testid="cr-rischio-bot"
                title={`perdita massima LIVE secondo i bot (per partita, nettata dal servizio): non e' il conto. ${dettaglioBot}`}>
                <Etichetta>Rischio secondo i bot</Etichetta>
                <span className="font-mono text-sm font-semibold tabular-nums text-white/80"
                    data-testid="cr-rischio-bot-valore">{valoreBot}</span>
                {stantii.length > 0 && (
                    <span className="text-[9.5px] leading-tight text-amber-300" data-testid="cr-rischio-bot-stantio"
                        title={`il servizio dichiara il numero stantio (battito oltre 60 s): ${stantii.map((v) => BOT_LABEL[v.bot]).join(', ')}`}>
                        dato del bot non aggiornato ({stantii.map((v) => BOT_LABEL[v.bot]).join(', ')})
                    </span>
                )}
                <span className="flex items-center gap-1 text-[9.5px] leading-tight">
                    <MarchioSoldi fonte="bot" etaS={s == null ? undefined : s.etaBotS}
                        testId="cr-rischio-bot-marchio"
                        dettaglio="eta' = ultima lettura degli aggregati dei servizi" />
                    <span className={mancanti.length ? 'text-amber-300' : 'text-white/35'}
                        data-testid="cr-rischio-bot-nota">{notaBot}</span>
                </span>
            </div>

            {scarto && (
                <div className="flex flex-col gap-0.5" data-testid="cr-scarto-conto-bot"
                    title="il conto e i bot non dicono la stessa cosa: possono esserci ordini fuori dai bot o bot non allineati. Controlla le posizioni sul conto.">
                    <Etichetta>Conto e bot</Etichetta>
                    <span className="font-mono text-sm font-semibold tabular-nums text-amber-300">
                        NON TORNANO: {fmtMoney(scarto.differenza)}
                    </span>
                    <span className="flex items-center gap-1 text-[9.5px] leading-tight text-amber-300/80">
                        <MarchioSoldi fonte="pagina" testId="cr-scarto-marchio"
                            dettaglio="differenza fra l'esposizione del conto e il rischio dichiarato dai bot" />
                        {scarto.contoPiuAlto ? 'il conto rischia piu\' dei bot' : 'il conto rischia meno dei bot'}
                    </span>
                </div>
            )}

            {/* W_T/P14: ordini del conto fuori dai bot (sito/app), per partita */}
            {s?.ordiniFuori && (
                <div className="flex flex-col gap-0.5" data-testid="cr-ordini-fuori-bot"
                    title="ordini sul conto Betfair non piazzati dai bot (sito, app): i bot non li vedono">
                    <Etichetta>Ordini fuori dai bot</Etichetta>
                    {s.ordiniFuori.letto ? (
                        <span className={`text-[11px] font-mono ${s.ordiniFuori.n + s.ordiniFuori.senzaPartita > 0 ? 'text-amber-300' : 'text-white/50'}`}>
                            partite con ordini fuori dai bot: {s.ordiniFuori.n}
                            {s.ordiniFuori.nomi.length > 0 && ` (${s.ordiniFuori.nomi.join(', ')})`}
                            {s.ordiniFuori.senzaPartita > 0 && ` + ${s.ordiniFuori.senzaPartita} senza partita`}
                        </span>
                    ) : (
                        <span className="text-[10px] text-white/40">
                            ordini del conto: non letti ({s.ordiniFuori.motivo ?? 'motivo ignoto'})
                        </span>
                    )}
                </div>
            )}

            <div className="flex flex-col gap-0.5" data-testid="cr-partite-posizione"
                title="partite distinte con almeno una posizione aperta, secondo le righe dei bot">
                <Etichetta>Posizione LIVE</Etichetta>
                {/* W_T/P15: partite e gambe mai con la stessa parola */}
                <span className="font-mono text-sm font-semibold tabular-nums">
                    {partite == null ? DASH
                        : `${partite.live} ${partite.live === 1 ? 'partita' : 'partite'} con posizione LIVE (${partite.gambeLive ?? DASH} ${partite.gambeLive === 1 ? 'gamba' : 'gambe'})`}
                </span>
                <span className="text-[9.5px] leading-tight text-white/35" data-testid="cr-partite-posizione-nota">
                    {partite == null ? `posizioni non ancora lette${PUNTO}` : (
                        <>
                            {partite.prova > 0 && <>in prova {partite.prova}{PUNTO}</>}
                            {partite.ignota > 0 && (
                                <span className="text-orange-300">modalita' non dichiarata {partite.ignota}{PUNTO}</span>
                            )}
                        </>
                    )}
                    programma scanner {s?.programmaScanner ?? DASH}
                </span>
            </div>
        </div>
    );
}

export default FasciaSoldiVeri;
