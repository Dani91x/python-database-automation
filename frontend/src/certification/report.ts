// ============================================================================
// report.ts — raccolta del REPORT della certificazione.
// I test non si limitano a passare/fallire: registrano la riga
// "elemento → valore RPC → valore mostrato → OK/KO" e i findings, e alla fine
// del file la stampano. L'output del runner È il report.
// ============================================================================

export type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO';

export interface CheckRow {
    element: string;
    expected: string;
    shown: string;
    ok: boolean;
}

export interface Finding {
    severity: Severity;
    where: string;
    detail: string;
}

const SEV_ORDER: Severity[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];

export class Report {
    readonly rows: CheckRow[] = [];
    readonly findings: Finding[] = [];
    readonly notes: string[] = [];

    constructor(readonly page: string) {}

    /** registra un confronto e ritorna l'esito (il test fa poi la sua expect) */
    check(element: string, expected: unknown, shown: unknown): boolean {
        const e = String(expected);
        const s = String(shown);
        const ok = e === s;
        this.rows.push({ element, expected: e, shown: s, ok });
        return ok;
    }

    /** registra una riga già giudicata (per i confronti non testuali) */
    mark(element: string, expected: string, shown: string, ok: boolean): boolean {
        this.rows.push({ element, expected, shown, ok });
        return ok;
    }

    finding(severity: Severity, where: string, detail: string): void {
        this.findings.push({ severity, where, detail });
    }

    note(text: string): void {
        this.notes.push(text);
    }

    print(): void {
        // niente rumore quando la suite è skippata (npm test senza CERT_RUN)
        if (this.rows.length === 0 && this.findings.length === 0 && this.notes.length === 0) return;
        const ko = this.rows.filter((r) => !r.ok);
        const lines: string[] = [];
        lines.push('');
        lines.push('='.repeat(100));
        lines.push(`CERTIFICAZIONE — ${this.page}`);
        lines.push('='.repeat(100));
        lines.push(`controlli: ${this.rows.length} · OK ${this.rows.length - ko.length} · KO ${ko.length}`);
        lines.push('');
        lines.push(pad('ELEMENTO', 44) + pad('VALORE RPC/DB', 26) + pad('MOSTRATO', 26) + 'ESITO');
        lines.push('-'.repeat(100));
        for (const r of this.rows) {
            lines.push(pad(r.element, 44) + pad(r.expected, 26) + pad(r.shown, 26) + (r.ok ? 'OK' : 'KO'));
            if (!r.ok && (r.expected.length > 25 || r.shown.length > 25)) {
                lines.push(`    atteso : ${r.expected}`);
                lines.push(`    mostrato: ${r.shown}`);
            }
        }
        if (this.findings.length) {
            lines.push('');
            lines.push('FINDINGS');
            lines.push('-'.repeat(100));
            const sorted = [...this.findings].sort(
                (a, b) => SEV_ORDER.indexOf(a.severity) - SEV_ORDER.indexOf(b.severity),
            );
            for (const f of sorted) lines.push(`[${f.severity}] ${f.where}\n    ${f.detail}`);
        }
        if (this.notes.length) {
            lines.push('');
            lines.push('NOTE');
            lines.push('-'.repeat(100));
            for (const n of this.notes) lines.push(`· ${n}`);
        }
        lines.push('='.repeat(100));
        // stdout diretto: console.error/warn sono spiati dal setup
        process.stdout.write(lines.join('\n') + '\n');
    }
}

function pad(s: string, n: number): string {
    const t = s.length > n - 1 ? `${s.slice(0, n - 2)}…` : s;
    return t + ' '.repeat(Math.max(1, n - t.length));
}

/** testo visibile di un nodo, normalizzato (spazi unici) */
export function text(el: Element | null | undefined): string {
    return (el?.textContent ?? '').replace(/\s+/g, ' ').trim();
}
