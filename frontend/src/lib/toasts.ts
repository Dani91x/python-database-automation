// ============================================================================
// toasts.ts — NOTIFICHE con un formato UNICO per le tre sezioni di trading.
//
// Prima c'erano tre formati di toast di regolazione (Omega "💰 nome / Incassato
// +€x", Safe "💰 nome / +€x · LAY sel", Mike "💰 Regolata / +x,xx € · nome"):
// lo stesso evento deve leggersi sempre allo stesso modo.
//
// Formato: titolo = "💰 <nome>" (vinto) / "⚠️ <nome>" (perso) / "<nome>" (void)
//          descrizione = "<P&L firmato> · <LATO selezione>" (+ "✋ manuale")
// ============================================================================
import { toast } from 'sonner';
import { fmtMoney } from '@/lib/format';
import { sideMeta } from '@/lib/tradeStatus';

export interface SettlementToast {
    /** nome della partita/evento (mai l'id nudo se il nome c'è) */
    name: string;
    /** P&L realizzato in euro; 0 o null = VOID */
    pnl: number | null | undefined;
    side?: string | null;
    selection?: string | null;
    /** true = deciso a mano dall'utente, non dal bot */
    manual?: boolean;
    /** override del testo di stato (es. "VOID") */
    statusLabel?: string | null;
}

/** Costruisce titolo e descrizione (PURO: testato senza sonner). */
export function settlementToastText(t: SettlementToast): { title: string; description: string; tone: 'win' | 'loss' | 'void' } {
    const pnl = Number(t.pnl ?? 0);
    const tone: 'win' | 'loss' | 'void' = pnl > 0 ? 'win' : pnl < 0 ? 'loss' : 'void';
    const tag = t.manual ? '✋ ' : '';
    const icon = tone === 'win' ? '💰 ' : tone === 'loss' ? '⚠️ ' : '';
    const title = `${icon}${tag}${t.name}`;
    const bits: string[] = [tone === 'void' ? (t.statusLabel ?? 'VOID') : fmtMoney(pnl, { signed: true })];
    const sel = [t.side ? sideMeta(t.side).label : null, t.selection?.trim() || null]
        .filter(Boolean).join(' ');
    if (sel) bits.push(sel);
    if (tone === 'void') bits.push(`P&L ${fmtMoney(0)}`);
    return { title, description: bits.join(' · '), tone };
}

/** Notifica di regolazione: UN formato per Omega, Safe e Mike. */
export function toastSettlement(t: SettlementToast): void {
    const { title, description, tone } = settlementToastText(t);
    if (tone === 'win') toast.success(title, { description });
    else if (tone === 'loss') toast.error(title, { description });
    else toast(title, { description });
}
