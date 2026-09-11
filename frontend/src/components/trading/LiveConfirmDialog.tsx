// ============================================================================
// LiveConfirmDialog.tsx — dialog UNICO di passaggio a LIVE (soldi veri).
// Titolo, bottoni e colori identici nelle tre sezioni; l'avvertenza specifica
// del bot (coda pesante di Omega, 4 gol di Mike, molte vincite piccole di Safe)
// arriva da `warning`.
// ============================================================================
import type { ReactNode } from 'react';
import { ShieldAlert } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { T } from '@/lib/tradeStatus';

export function LiveConfirmDialog({ open, onOpenChange, onConfirm, busy, intro, warning }: {
    open: boolean;
    onOpenChange: (v: boolean) => void;
    onConfirm: () => void;
    busy?: boolean;
    /** cosa comincia a fare il bot con soldi veri */
    intro: ReactNode;
    /** il rischio specifico della struttura di questo bot */
    warning?: ReactNode;
}) {
    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="glass-card border-red-500/30" data-testid="live-confirm">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2 text-red-400">
                        <ShieldAlert className="w-5 h-5" aria-hidden />{T.liveConfirmTitle}
                    </DialogTitle>
                    <DialogDescription className="space-y-2 text-sm">
                        <span className="block">{intro}</span>
                        {warning && <span className="block text-orange-300">{warning}</span>}
                    </DialogDescription>
                </DialogHeader>
                <DialogFooter>
                    <Button variant="ghost" onClick={() => onOpenChange(false)}>{T.liveConfirmCancel}</Button>
                    <Button variant="destructive" onClick={onConfirm} disabled={busy} data-testid="live-confirm-ok">
                        {T.liveConfirmOk}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

export default LiveConfirmDialog;
