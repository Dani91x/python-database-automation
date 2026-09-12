// ============================================================================
// LiveConfirmDialog.tsx — dialog UNICO di passaggio a LIVE (soldi veri).
// Titolo, bottoni e colori identici nelle tre sezioni; l'avvertenza specifica
// del bot (coda pesante di Omega, 4 gol di Mike, molte vincite piccole di Safe)
// arriva da `warning`.
//
// Certificazione 12/09 — una conferma LIVE non vale per sempre: se mentre il
// dialog è aperto cambiano le condizioni su cui il trader sta decidendo
// (importo, prezzo, liquidità, parametri del bot), l'OK deve DECADERE. La
// pagina passa `armKey`: una stringa che riassume quelle condizioni; se cambia
// a dialog aperto il bottone si spegne e lo dice. Senza `armKey` il
// comportamento è quello di prima (retro-compatibile).
// ============================================================================
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ShieldAlert } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { T } from '@/lib/tradeStatus';

export function LiveConfirmDialog({
    open, onOpenChange, onConfirm, busy, intro, warning, armKey,
}: {
    open: boolean;
    onOpenChange: (v: boolean) => void;
    onConfirm: () => void;
    busy?: boolean;
    /** cosa comincia a fare il bot con soldi veri */
    intro: ReactNode;
    /** il rischio specifico della struttura di questo bot */
    warning?: ReactNode;
    /**
     * Riassunto delle condizioni su cui si sta decidendo (stake, prezzo,
     * liquidità, parametri): se cambia mentre il dialog è aperto la conferma
     * decade. Omettila se non ci sono numeri in ballo.
     */
    armKey?: string | number | null;
}) {
    // la chiave con cui il dialog è stato APERTO: il confronto è con questa
    const openedWith = useRef<string | number | null | undefined>(armKey);
    const [stale, setStale] = useState(false);

    useEffect(() => {
        if (open) { openedWith.current = armKey; setStale(false); }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open]);

    useEffect(() => {
        if (!open || armKey === undefined) return;
        if (armKey !== openedWith.current) setStale(true);
    }, [open, armKey]);

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
                        {stale && (
                            <span className="block text-red-300" data-testid="live-confirm-stale">
                                Le condizioni sono cambiate da quando hai aperto questa finestra
                                (importo, prezzo o liquidità): la conferma è decaduta. Chiudi,
                                rileggi i numeri e riapri.
                            </span>
                        )}
                    </DialogDescription>
                </DialogHeader>
                <DialogFooter>
                    <Button variant="ghost" onClick={() => onOpenChange(false)} data-testid="live-confirm-cancel">
                        {T.liveConfirmCancel}
                    </Button>
                    <Button
                        variant="destructive"
                        onClick={onConfirm}
                        disabled={busy || stale}
                        data-testid="live-confirm-ok"
                    >
                        {T.liveConfirmOk}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

export default LiveConfirmDialog;
