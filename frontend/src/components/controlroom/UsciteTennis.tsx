// ============================================================================
// UsciteTennis.tsx — «USCITE AUTOMATICHE» PER BOT TENNIS, E L'AVVISO PERMANENTE.
//
// «Tutti i bot tennis devono [...] gestire le uscite in automatico o in manuale
// sia in paper che in live» (utente, 25/09).
//
// Un interruttore per bot, accanto alla sua scheda parametri nella plancia:
//   · AUTOMATICHE (di serie, com'era): il bot prende profitto da solo;
//   · MANUALI: il bot non prende profitto da solo; stop e protezioni restano;
//     la posizione la chiude l'utente con «Chiudi» dalla scheda partita.
// Passare a MANUALI si conferma (secondo clic al posto del primo): da lì una
// posizione resta esposta finché qualcuno non la chiude. Tornare ad AUTOMATICHE
// non chiede niente: riduce il rischio.
//
// L'interruttore NON compare quando il servizio non lo dichiara (migrazione
// non applicata: `usciteAutomatiche === null`) né per lo scalper, la cui
// uscita a target è la strategia stessa (sempre automatica, detto in chiaro).
// Lo stato mostrato è quello che RISPONDE il servizio, non quello sperato.
// ============================================================================
import { useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { setTennisBotUscite, type TennisBotKey } from '@/lib/tennis';
import { avvisoUsciteManuali, type AutoTennis } from './tennisAuto';

export interface UsciteTennisProps {
    botKey: TennisBotKey;
    auto: AutoTennis | null | undefined;
    nowMs: number;
    onSaved?: () => void;
    /** iniettabile nei test: di serie la RPC vera */
    scrivi?: (bot: TennisBotKey, automatiche: boolean) => Promise<unknown>;
}

export function UsciteTennis({ botKey, auto, nowMs, onSaved, scrivi }: UsciteTennisProps) {
    const [conferma, setConferma] = useState(false);
    const [occupato, setOccupato] = useState(false);
    const [errore, setErrore] = useState<string | null>(null);
    if (auto == null) return null;
    if (auto.usciteSempreAutomatiche) {
        return (
            <span className="text-[10px] text-white/35" data-testid={`cr-uscite-${botKey}`}
                title="lo scalper chiude con la gamba opposta piazzata insieme all'ingresso: è la strategia">
                uscite: sempre automatiche
            </span>
        );
    }
    if (auto.usciteAutomatiche == null) return null;
    const avviso = avvisoUsciteManuali(auto, nowMs);
    const cambia = async (automatiche: boolean) => {
        setOccupato(true); setErrore(null);
        try {
            // la RPC vera si prende SOLO al clic (i test di pagina sostituiscono
            // `@/lib/tennis` con finti che non la conoscono)
            await (scrivi ?? setTennisBotUscite)(botKey, automatiche);
            setConferma(false);
            onSaved?.();
        } catch (e) {
            setErrore(e instanceof Error ? e.message : String(e));
        } finally {
            setOccupato(false);
        }
    };
    return (
        <span className="flex items-center gap-1.5 flex-wrap" data-testid={`cr-uscite-${botKey}`}>
            {auto.usciteAutomatiche ? (
                conferma ? (
                    <button type="button" disabled={occupato}
                        className="text-[10px] px-1.5 py-0.5 rounded border border-amber-400/60 text-amber-300"
                        data-testid={`cr-uscite-conferma-${botKey}`}
                        onClick={() => void cambia(false)}>
                        conferma: uscite MANUALI (chiudi tu)
                    </button>
                ) : (
                    <button type="button" disabled={occupato}
                        className="text-[10px] px-1.5 py-0.5 rounded border border-white/15 text-white/60"
                        data-testid={`cr-uscite-manuali-${botKey}`}
                        onClick={() => setConferma(true)}>
                        uscite: automatiche
                    </button>
                )
            ) : (
                <button type="button" disabled={occupato}
                    className="text-[10px] px-1.5 py-0.5 rounded border border-amber-400/60 text-amber-300"
                    data-testid={`cr-uscite-automatiche-${botKey}`}
                    onClick={() => void cambia(true)}>
                    uscite: MANUALI (torna automatiche)
                </button>
            )}
            {avviso && (
                <span className="text-[10px] text-amber-300 flex items-center gap-1"
                    data-testid={`cr-uscite-avviso-${botKey}`}>
                    <AlertTriangle className="w-3 h-3 shrink-0" />{avviso}
                </span>
            )}
            {errore && (
                <span className="text-[10px] text-red-300" data-testid={`cr-uscite-errore-${botKey}`}>
                    non salvato: {errore}
                </span>
            )}
        </span>
    );
}

export default UsciteTennis;
