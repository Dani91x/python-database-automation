// ============================================================================
// PartiteChiuseDallUtente.tsx — LE PARTITE CHE HAI CHIUSO TU (Omega, R8).
//
// Ordine dell'utente del 16/09 sera: «se chiudo io (anche fuori dall'app,
// direttamente su Betfair) il bot deve saperlo e NON gestire posizioni che non
// esistono piu'». Quando il servizio se ne accorge marca la partita: da lì in
// poi non apre, non copre e non fa green-up su di essa.
//
// QUESTO STATO NON SCADE: non col passare dei giorni, non a partita finita, non
// al rinfresco della cache eventi. Si toglie SOLO da qui, con «Riprendi», che è
// un gesto dell'utente e resta scritto (`omega_activity`/`evento_ripreso`).
// Senza questo pannello l'unico modo di toglierlo era una query SQL a mano.
//
// L'elenco arriva dalla RPC `omega_eventi_chiusi_dall_utente()`; se la
// migrazione del 16/09 non è applicata la RPC non esiste e l'errore si LEGGE,
// invece di un pannello vuoto che sembrerebbe «nessuna partita chiusa».
// ============================================================================
import { useCallback, useEffect, useState } from 'react';
import { Loader2, Undo2 } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { fmtTime, DASH } from '@/lib/format';
import { comeLabel } from '@/lib/chiusuraUtente';
import { fetchOmegaEventiChiusi, omegaEventoRiprendi, type OmegaEventoChiuso } from '@/lib/omega';

/** Legge il marcatore che il servizio ha scritto in `omega_events.stato_utente`. */
function dettaglio(r: OmegaEventoChiuso): { quando: string | null; come: string | null } {
    const o = (r.stato_utente ?? {}) as Record<string, unknown>;
    const t = (v: unknown) => (v == null || String(v).trim() === '' ? null : String(v).trim());
    return { quando: t(o.quando ?? o.chiuso_at), come: t(o.come ?? o.motivo) };
}

export interface PartiteChiuseDallUtenteProps {
    /** iniezione per i test: di default legge la RPC vera */
    carica?: () => Promise<OmegaEventoChiuso[]>;
    riprendi?: (eventId: string) => Promise<unknown>;
    /** ricarica la pagina dopo un «Riprendi» andato a buon fine */
    onRipreso?: () => void;
}

export function PartiteChiuseDallUtente({
    carica = fetchOmegaEventiChiusi, riprendi = omegaEventoRiprendi, onRipreso,
}: PartiteChiuseDallUtenteProps) {
    const [righe, setRighe] = useState<OmegaEventoChiuso[]>([]);
    const [errore, setErrore] = useState<string | null>(null);
    const [inCorso, setInCorso] = useState<string | null>(null);

    const leggi = useCallback(() => {
        carica()
            .then((r) => { setRighe(r); setErrore(null); })
            .catch((e: unknown) => {
                setRighe([]);
                setErrore(e instanceof Error ? e.message : String(e));
            });
    }, [carica]);

    useEffect(() => { leggi(); }, [leggi]);

    const premi = async (eventId: string) => {
        setInCorso(eventId);
        setErrore(null);
        try {
            await riprendi(eventId);
            leggi();
            onRipreso?.();
        } catch (e) {
            setErrore(e instanceof Error ? e.message : String(e));
        } finally {
            setInCorso(null);
        }
    };

    // niente righe e nessun errore = non c'è niente da dire: non si occupa
    // spazio con un riquadro vuoto.
    if (righe.length === 0 && !errore) return null;

    return (
        <Card className="glass-card border-amber-500/30 p-3" data-testid="omega-chiuse-dall-utente">
            <div className="text-[10px] uppercase tracking-wide text-amber-300/90 mb-1.5">
                Partite che hai chiuso tu — il bot non ci opera più
            </div>

            {errore && (
                <div className="text-[11px] text-orange-300 mb-1.5" data-testid="omega-chiuse-errore">
                    ⛔ elenco non leggibile: {errore}. Finché non si legge, qui non compare nessuna
                    partita — e non vuol dire che non ce ne siano.
                </div>
            )}

            <div className="space-y-1">
                {righe.map((r) => {
                    const d = dettaglio(r);
                    return (
                        <div key={r.event_id}
                            className="flex items-baseline gap-2 text-[11.5px]"
                            data-testid="omega-chiusa-riga" data-event-id={r.event_id}>
                            <span className="text-white/80 truncate max-w-[16rem]">{r.name ?? r.event_id}</span>
                            <span className="text-white/40">{comeLabel(d.come) ?? 'chiusa da te'}</span>
                            <span className="text-white/25 font-mono">
                                {d.quando ? fmtTime(d.quando) : DASH}
                            </span>
                            <Button
                                variant="ghost" size="sm"
                                className="ml-auto h-6 text-[10px] uppercase tracking-wider text-white/70 hover:text-white"
                                onClick={() => void premi(r.event_id)}
                                disabled={inCorso != null}
                                data-testid={`omega-riprendi-${r.event_id}`}
                                title={inCorso != null
                                    ? 'richiesta gia’ in corso: si aspetta la risposta del servizio'
                                    : 'riporta la partita in carico al bot: e’ l’unico modo di togliere lo stato'}
                            >
                                {inCorso === r.event_id
                                    ? <Loader2 className="w-3 h-3 animate-spin" />
                                    : <><Undo2 className="w-3 h-3 mr-1" />Riprendi</>}
                            </Button>
                        </div>
                    );
                })}
            </div>
        </Card>
    );
}

export default PartiteChiuseDallUtente;
