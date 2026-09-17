// ============================================================================
// BarreGiornaliere.tsx — il P&L GIORNO PER GIORNO, a barre.
//
// La curva (`EquityCurve`) dice dove si è arrivati; le barre dicono COME.
// Una curva che sale di 40 € può essere venti giorni da +2 € oppure un giorno
// da +60 € e dieci da −2 €: sono due bot diversi, e sulla curva si somigliano.
//
// SVG puro come `EquityCurve`, per gli stessi motivi: stessa resa in tutte le
// pagine, nessuna libreria da montare in un test, nessun tema da riallineare.
// (`recharts` è in `package.json` e si potrebbe usare — qui NON si usa, per
// non avere due grafici con due estetiche nella stessa dashboard.)
//
// Regole del design system rispettate: denaro solo da `fmtMoney`, colore del
// segno da `pnlClass`/verde-rosso del tema, grafico con `role="img"` e un
// `aria-label` che dice il periodo, il totale e il giorno migliore e peggiore.
// ============================================================================
import { fmtMoney } from '@/lib/format';
import { dayLabel } from '@/lib/dailyHistory';

export interface BarraGiornaliera {
    day: string;
    pnl: number;
    /** dettaglio per bot, mostrato nel tooltip della barra */
    perBot?: Record<string, number>;
}

/** «10 set» per l'asse: le chiavi sono già giornate Europe/Rome, non istanti. */
function etichettaAsse(day: string): string {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(day);
    if (!m) return day;
    const ms = Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
    try {
        return new Intl.DateTimeFormat('it-IT', { timeZone: 'UTC', day: 'numeric', month: 'short' })
            .format(new Date(ms));
    } catch { return day; }
}

export function BarreGiornaliere({
    barre,
    emptyLabel = 'nessuna giornata con operazioni in questo periodo',
    onSelectDay,
    selectedDay = null,
    testId = 'barre-giornaliere',
}: {
    barre: readonly BarraGiornaliera[];
    emptyLabel?: string;
    /** click su una barra = apri il dettaglio di quel giorno */
    onSelectDay?: (day: string) => void;
    selectedDay?: string | null;
    testId?: string;
}) {
    const valide = barre.filter((b) => Number.isFinite(b.pnl));
    if (valide.length === 0) {
        return (
            <div className="text-sm text-muted-foreground py-10 text-center" data-testid={`${testId}-vuoto`}>
                {emptyLabel}
            </div>
        );
    }

    const W = 820, H = 200;
    const pad = { l: 10, r: 60, t: 14, b: 26 };
    const maxAbs = valide.reduce((m, b) => Math.max(m, Math.abs(b.pnl)), 0) || 1;
    const larghezza = (W - pad.l - pad.r) / valide.length;
    const barra = Math.max(2, Math.min(28, larghezza * 0.72));
    const y0 = pad.t + (H - pad.t - pad.b) / 2;
    const altezza = (v: number) => (Math.abs(v) / maxAbs) * ((H - pad.t - pad.b) / 2);

    const totale = Math.round(valide.reduce((s, b) => s + b.pnl, 0) * 100) / 100;
    const migliore = valide.reduce((m, b) => (b.pnl > m.pnl ? b : m), valide[0]);
    const peggiore = valide.reduce((m, b) => (b.pnl < m.pnl ? b : m), valide[0]);
    const aria = `P&L per giornata: ${valide.length} ${valide.length === 1 ? 'giornata' : 'giornate'}, `
        + `totale ${fmtMoney(totale, { signed: true })}; `
        + `migliore ${dayLabel(migliore.day, { year: false })} ${fmtMoney(migliore.pnl, { signed: true })}, `
        + `peggiore ${dayLabel(peggiore.day, { year: false })} ${fmtMoney(peggiore.pnl, { signed: true })}`;

    const dettaglio = (b: BarraGiornaliera): string => {
        const righe = Object.entries(b.perBot ?? {})
            .map(([nome, v]) => `${nome} ${fmtMoney(v, { signed: true })}`);
        return `${dayLabel(b.day, { weekday: true })}: ${fmtMoney(b.pnl, { signed: true })}`
            + (righe.length > 1 ? ` — ${righe.join(' · ')}` : '');
    };

    return (
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto select-none" role="img" aria-label={aria}
            data-testid={testId}>
            <title>{aria}</title>
            {/* riga dello zero: senza, una barra negativa corta sembra positiva */}
            <line x1={pad.l} x2={W - pad.r} y1={y0} y2={y0} stroke="#334155" strokeWidth={1} />
            <text x={W - pad.r + 6} y={y0 + 3} fontSize={10} fill="#94a3b8" className="tabular-nums">
                {fmtMoney(0, { signed: true })}
            </text>
            <text x={W - pad.r + 6} y={pad.t + 8} fontSize={10} fill="#94a3b8" className="tabular-nums">
                {fmtMoney(maxAbs, { signed: true })}
            </text>
            <text x={W - pad.r + 6} y={H - pad.b} fontSize={10} fill="#94a3b8" className="tabular-nums">
                {fmtMoney(-maxAbs, { signed: true })}
            </text>

            {valide.map((b, i) => {
                const x = pad.l + i * larghezza + (larghezza - barra) / 2;
                const h = Math.max(1, altezza(b.pnl));
                const su = b.pnl >= 0;
                const scelta = selectedDay === b.day;
                return (
                    <g key={b.day} data-testid={`barra-${b.day}`}
                        className={onSelectDay ? 'cursor-pointer' : undefined}
                        onClick={onSelectDay ? () => onSelectDay(b.day) : undefined}>
                        <title>{dettaglio(b)}</title>
                        <rect
                            x={x} y={su ? y0 - h : y0} width={barra} height={h}
                            fill={su ? '#34d399' : '#f87171'}
                            opacity={scelta ? 1 : 0.8}
                            stroke={scelta ? '#e2e8f0' : 'none'}
                            strokeWidth={scelta ? 1.5 : 0}
                            rx={1.5}
                        />
                    </g>
                );
            })}

            {/* asse orizzontale: primo e ultimo giorno, come nella curva */}
            <text x={pad.l} y={H - 8} fontSize={10} fill="#94a3b8" textAnchor="start">
                {etichettaAsse(valide[0].day)}
            </text>
            {valide.length > 1 && (
                <text x={W - pad.r} y={H - 8} fontSize={10} fill="#94a3b8" textAnchor="end">
                    {etichettaAsse(valide[valide.length - 1].day)}
                </text>
            )}
        </svg>
    );
}

export default BarreGiornaliere;
