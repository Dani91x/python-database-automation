// ============================================================================
// ObiettivoHero.tsx — ZONA 1 «L'OBIETTIVO» (Task 1/2, 18/09).
//
// Un concetto, una rappresentazione (checklist A5 §3.3 regola 1): l'obiettivo
// vive qui, UNA volta sola nella pagina. Contiene:
//   · l'intestazione con l'obiettivo MODIFICABILE (`ObiettivoEditor`);
//   · la `DayBar` già certificata, INVARIATA (nessuna modifica a
//     `components/trading/DayBar.tsx`: qui si aggiunge, non si tocca);
//   · la scomposizione di ciò che erode l'obiettivo (Task 2), sotto, sempre
//     SOLO soldi veri; il paper resta su una riga separata, mai sommato.
// ============================================================================
import { Target } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { DayBar, type DayBarProps } from '@/components/trading/DayBar';
import { ObiettivoEditor } from './ObiettivoEditor';
import { fmtMoney, DASH } from '@/lib/format';
import { pnlClass } from '@/lib/tradeStatus';
import type { ComposizioneObiettivo } from '@/lib/composizioneObiettivo';
import type { ManualeSitoBetfair } from '@/lib/manualeSitoBetfair';
import { etichettaArretrati, type ChiaveProva, type ProvaGiornata, type VoceProva } from '@/lib/provaGiornata';
import { MarchioSoldi } from './MarchioSoldi';
import type { ApertoPerBot } from '@/lib/apertoAdesso';
import type { ComposizioneConto, RigaComposizioneConto } from '@/lib/composizioneConto';
import type { RigaComposizione } from '@/lib/composizioneObiettivo';

export interface ObiettivoHeroProps {
    dayBar: DayBarProps;
    /** 30/09 (P7): anche la composizione ricomposta dal conto (`ComposizioneConto`) */
    composizione: ComposizioneObiettivo | ComposizioneConto;
    manualeSito: ManualeSitoBetfair;
    onSalvaObiettivo: (valore: number) => Promise<void>;
    /** avviso onesto: Omega in corsa → il target del servizio cambia subito */
    avvisoMotore?: string | null;
    /** 30/09 (P8): la corsia PROVA per bot (oggi / arretrati). Assente = riga «in prova» di prima. */
    prova?: ProvaGiornata | null;
    /** 30/09 (P7): eta' in secondi della lettura del conto Betfair (`pnl_reale_oggi.letto_at`); null = ignota */
    contoEtaS?: number | null;
    /** 30/09 (R_G): la modalita' CORRENTE di ogni voce della prova (live = «— (ora in LIVE)» se non ha prova di oggi) */
    modalitaBot?: Partial<Record<ChiaveProva, 'paper' | 'live' | null>> | null;
    // 30/09 (W_G): l'aperto per bot (somma per partita delle sue gambe LIVE)
    apertoPerBot?: Record<string, ApertoPerBot> | null;
    testId?: string;
}

/** 30/09 (P7): da dove viene la cifra della voce (solo se la composizione lo dichiara) */
function fonteDi(r: RigaComposizione): 'conto' | 'bot' | null {
    return (r as RigaComposizioneConto).fonte ?? null;
}

/** 30/09 (W_G): quali bot dell'aperto compongono una voce della composizione */
const BOT_DELLA_VOCE: Partial<Record<string, string[]>> = {
    omega: ['omega'], mike: ['mike'], scalper: ['scalper'],
    safe_calcio: ['safe_calcio'], safe_tennis: ['safe_tennis'],
    bot_tennis: ['tennis_scalper', 'tennis_pro', 'tennis_flb', 'tennis_swing'],
};

/** L'aperto di una voce (somma dei suoi bot); null = nessuna partita LIVE di quei bot. */
function apertoDi(per: Record<string, ApertoPerBot> | null | undefined, chiave: string): ApertoPerBot | null {
    const bots = BOT_DELLA_VOCE[chiave];
    if (!per || !bots) return null;
    let out: ApertoPerBot | null = null;
    for (const b of bots) {
        const v = per[b];
        if (!v) continue;
        out = out ?? { netto: null, partite: 0, nonCalcolabili: 0 };
        if (v.netto != null) out.netto = Math.round(((out.netto ?? 0) + v.netto) * 100) / 100;
        out.partite += v.partite;
        out.nonCalcolabili += v.nonCalcolabili;
    }
    return out;
}

function ApertoVoce({ chiave, a }: { chiave: string; a: ApertoPerBot }) {
    return (
        <span className="text-[10px] ml-1 text-white/50" data-testid={`cr-composizione-${chiave}-aperto`}
            title="aperto adesso: cash out LIVE delle partite di questo bot, per partita, ai prezzi dello scanner (stima)">
            · aperto{' '}
            <span className={a.netto == null ? 'text-white/40' : pnlClass(a.netto)}>
                {a.netto == null ? DASH : fmtMoney(a.netto, { signed: true })}
            </span>
            {a.nonCalcolabili > 0 && <span className="text-amber-300"> + {a.nonCalcolabili} non calcolabili</span>}
        </span>
    );
}

/** 30/09 (P7): la composizione e' stata ricomposta dal conto Betfair */
function dalConto(c: ComposizioneObiettivo): boolean | null {
    const v = (c as ComposizioneConto).dalConto;
    return typeof v === 'boolean' ? v : null;
}

export function ObiettivoHero({
    dayBar, composizione, manualeSito, onSalvaObiettivo, avvisoMotore, prova = null, contoEtaS, modalitaBot = null, apertoPerBot = null, testId = 'cr-obiettivo',
}: ObiettivoHeroProps) {
    return (
        <Card className="glass-card border-white/10 p-0 overflow-hidden" data-testid={testId}>
            <div className="px-4 pt-3 flex items-center gap-2">
                <Target className="w-4 h-4 text-secondary" aria-hidden />
                <span className="text-[13px] text-white/85">Obiettivo di oggi</span>
                <ObiettivoEditor
                    valoreAttuale={dayBar.goal ?? null}
                    onSalva={onSalvaObiettivo}
                    avvisoMotore={avvisoMotore}
                    testId="cr-obiettivo-editor"
                />
            </div>

            <div className="px-2 pt-1">
                <DayBar {...dayBar} testId="cr-giornata" />
            </div>

            <div className="px-4 pb-3 pt-1" data-testid="cr-composizione">
                <div className="text-[10px] uppercase tracking-wider text-white/40 mb-1.5">
                    composizione — solo soldi veri, entra nell&apos;obiettivo
                    {/* 30/09 (P7): da dove vengono le voci dei bot */}
                    {dalConto(composizione) == null ? null : dalConto(composizione) ? (
                        <span className="normal-case tracking-normal text-white/35" data-testid="cr-composizione-fonte">
                            {' '}· realizzato di ogni bot dal conto Betfair (attribuito da Betfair), la parte non ancora regolata stimata dal bot
                        </span>
                    ) : (
                        <span className="normal-case tracking-normal text-amber-300/70" data-testid="cr-composizione-fonte">
                            {' '}· conto Betfair non letto: dalle righe dei bot
                        </span>
                    )}
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-5 gap-y-0.5">
                    {composizione.righe.map((r) => (
                        <div
                            key={r.chiave}
                            className="flex items-baseline justify-between text-[11.5px] py-0.5 border-b border-dashed border-white/5"
                            data-testid={`cr-composizione-${r.chiave}`}
                        >
                            <span className="text-white/55">{r.etichetta}</span>
                            <span className={`font-mono ${r.valore == null ? 'text-white/30' : pnlClass(r.valore)}`}>
                                {r.valore == null ? DASH : fmtMoney(r.valore, { signed: true })}
                                {/* 24/09 - la parte non ancora regolata da Betfair si DICHIARA */}
                                {r.valore != null && r.stimato != null && (
                                    <span className="text-amber-300/70 text-[10px] ml-1"
                                        data-testid={`cr-composizione-${r.chiave}-stimato`}
                                        title="calcolo del bot: Betfair non ha ancora regolato">
                                        {r.stimato === r.valore ? 'stimato' : `di cui stimato ${fmtMoney(r.stimato, { signed: true })}`}
                                    </span>
                                )}
                                {/* 30/09 (W_G) - l'APERTO del bot (somma per partita delle SUE gambe LIVE) */}
                                {apertoDi(apertoPerBot, r.chiave) != null && (
                                    <ApertoVoce chiave={r.chiave} a={apertoDi(apertoPerBot, r.chiave) as ApertoPerBot} />
                                )}
                                {/* 30/09 (P7) - la FONTE della cifra della voce */}
                                {r.valore != null && fonteDi(r) != null && (
                                    <MarchioSoldi fonte={fonteDi(r) === 'conto' ? 'conto' : 'bot'} className="ml-1"
                                        etaS={fonteDi(r) === 'conto' ? contoEtaS : undefined}
                                        dettaglio={fonteDi(r) === 'conto' ? 'solo gli ordini che il conto attribuisce a questa voce' : undefined}
                                        testId={`cr-composizione-${r.chiave}-fonte`} />
                                )}
                            </span>
                        </div>
                    ))}
                </div>

                {/* SITO BETFAIR — punto d'aggancio isolato (Task 2b): oggi
                    sempre assente, mai un contributo alla somma. */}
                {manualeSito.fonte === 'non-disponibile' && (
                    <div className="text-[10px] text-white/30 mt-1" data-testid="cr-manuale-sito-assente">
                        scommesse dal sito Betfair (fuori app): {DASH} — in arrivo, non ancora collegate
                    </div>
                )}

                {prova != null ? (
                    <CorsiaProva prova={prova} modalitaBot={modalitaBot} />
                ) : composizione.provaPaper != null && (
                    <div
                        className="mt-1.5 pt-1.5 border-t border-white/10 flex items-baseline gap-2 text-[11px] text-white/40"
                        data-testid="cr-composizione-prova"
                    >
                        <span className="uppercase tracking-wider text-[9.5px] px-1.5 py-0.5 rounded bg-white/10">in prova</span>
                        <span className={pnlClass(composizione.provaPaper)}>
                            {fmtMoney(composizione.provaPaper, { signed: true })}
                        </span>
                        <span className="text-white/25">— mai sommato all&apos;obiettivo</span>
                    </div>
                )}
            </div>
        </Card>
    );
}

/**
 * 30/09 (P8) — LA CORSIA PROVA, una riga per bot: «oggi» = partite di OGGI;
 * «arretrati regolati oggi» = partite di giorni precedenti regolate oggi (es.
 * al riavvio), con la data e da dove viene la data. Simulato, MAI sommato
 * all'obiettivo; gli arretrati MAI sommati a oggi. Un dato non letto si dice.
 */
function CorsiaProva({ prova, modalitaBot }: {
    prova: ProvaGiornata; modalitaBot?: Partial<Record<ChiaveProva, 'paper' | 'live' | null>> | null;
}) {
    return (
        <div className="mt-2 pt-1.5 border-t border-dashed border-white/15 text-[11px] text-white/45"
            data-testid="cr-composizione-prova">
            <div className="flex items-baseline gap-2 mb-1">
                <span className="uppercase tracking-wider text-[9.5px] px-1.5 py-0.5 rounded border border-dashed border-white/20 text-white/55">
                    in prova (simulato)
                </span>
                <span className="text-white/30">— mai sommato all&apos;obiettivo; gli arretrati mai sommati a oggi</span>
            </div>
            <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1.4fr)] gap-x-3 gap-y-0.5">
                <span className="text-[9.5px] uppercase tracking-wider text-white/30">bot</span>
                <span className="text-[9.5px] uppercase tracking-wider text-white/30 text-right">partite di oggi</span>
                <span className="text-[9.5px] uppercase tracking-wider text-white/30">arretrati regolati oggi</span>
                {prova.voci.map((v) => (
                    <RigaProvaBot key={v.chiave} v={v} modalita={modalitaBot?.[v.chiave] ?? null} />
                ))}
            </div>
        </div>
    );
}

function RigaProvaBot({ v, modalita }: { v: VoceProva; modalita: 'paper' | 'live' | null }) {
    // 30/09 (R_G): un bot ORA in LIVE senza operazioni in prova di oggi non ha
    // una «prova di oggi» da mostrare: «+0,00 [PROVA]» accanto a un bot che
    // sta usando soldi veri si leggeva come un risultato. Gli arretrati restano.
    const oraLive = modalita === 'live' && (v.oggi == null || v.oggi.operazioni === 0);
    return (
        <>
            <span className="text-white/55 truncate" data-testid={`cr-prova-${v.chiave}`}>{v.etichetta}</span>
            <span className="font-mono text-right" data-testid={`cr-prova-${v.chiave}-oggi`}>
                {oraLive ? <span className="text-white/40">{DASH} <span className="text-red-300/80">(ora in LIVE)</span></span>
                    : v.oggi == null ? <span className="text-white/30">{DASH}</span>
                    : <span className={`${pnlClass(v.oggi.pnl)} opacity-80`}>{fmtMoney(v.oggi.pnl, { signed: true })}</span>}
                {!oraLive && v.oggi != null && <MarchioSoldi fonte="prova" className="ml-1" testId={`cr-prova-${v.chiave}-fonte`} />}
            </span>
            <span data-testid={`cr-prova-${v.chiave}-arretrati`}>
                {v.arretrati == null ? (
                    <span className="text-amber-300/80">{v.nota ?? 'non letti'}</span>
                ) : v.perRegolamento ? (
                    <span className="text-white/35" title="il servizio tennis pubblica una cifra sola per giorno: di regolamento, oppure di partita se la migrazione del 30/09 (get_tennis_bot_daily) e' applicata">per giorno come lo pubblica il servizio: non separabili</span>
                ) : v.arretrati.length === 0 ? (
                    <span className="text-white/30">nessuno</span>
                ) : v.arretrati.map((g) => (
                    <span key={`${g.giorno}|${g.origine}`} className="block">
                        <span className={`font-mono ${pnlClass(g.pnl)} opacity-70`}>{fmtMoney(g.pnl, { signed: true })}</span>
                        <span className="text-white/40"> ({etichettaArretrati(g)})</span>
                    </span>
                ))}
            </span>
        </>
    );
}

export default ObiettivoHero;
