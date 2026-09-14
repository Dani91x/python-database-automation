// ============================================================================
// AzioniPartita.tsx — I PULSANTI CHE STANNO SU OGNI SCHEDA.
//
// «PER OGNI SCHEDA VOGLIO: pulsanti live video e statistiche, pulsante
// trading, [e] il segui live che avvia la registrazione dell'intero evento.
// OGNI PULSANTE CHE MI MANDA DA ALTRE PARTI DEVE POI PERMETTERMI DI TORNARE
// INDIETRO IN QUELL'ESATTO PUNTO. QUESTI PULSANTI DEVONO ESSERE PRESENTI IN
// OGNI SCHEDA» (utente, 14/09).
//
// ⚠️ CALCIO E TENNIS NON REGISTRANO NELLO STESSO POSTO. È la trappola di
// questa schermata: `set_follow_record` scrive su `live_follow`, che il
// registratore del TENNIS non legge mai — lui guarda `tennis_live_follow`
// (`Betfair/stream/tennis_live/tennis_recorder.py`). Un pulsante unico
// avrebbe acceso una spia verde senza registrare niente. Qui ogni sport usa
// la sua coppia di comandi.
//
// LE STATISTICHE hanno bisogno del `fixture_id` di API-Football, che arriva
// dall'arricchimento di Omega e c'è su circa metà delle partite. Dove manca,
// il pulsante è SPENTO CON LA RAGIONE SCRITTA: un pulsante che non può
// funzionare non deve sembrare funzionante. Sul tennis non esiste proprio, e
// infatti non si mostra.
// ============================================================================
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BarChart3, CircleDot, LineChart, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { BetfairMediaButtons } from '@/components/BetfairMediaButtons';
import { salvaRitorno } from '@/lib/ritorno';
import { followMission, setFollowRecord } from '@/lib/omegaMissions';
import { followTennisEvent, setTennisFollowRecord } from '@/lib/tennis';
import type { PartitaGiornata } from '@/lib/controlRoom';

export interface AzioniPartitaProps {
    p: PartitaGiornata;
    /** la scheda aperta adesso: serve a tornare ESATTAMENTE qui */
    scheda: string;
    /** questa partita sta già registrando? `null` = non lo sappiamo */
    registra?: boolean | null;
    /** avvisa la pagina che lo stato della registrazione è cambiato */
    onRegistrazione?: (eventId: string, attiva: boolean) => void;
    compatto?: boolean;
}

export function AzioniPartita({
    p, scheda, registra = null, onRegistrazione, compatto = true,
}: AzioniPartitaProps) {
    const navigate = useNavigate();
    const [inCorso, setInCorso] = useState(false);
    const [errore, setErrore] = useState<string | null>(null);
    const [recLocale, setRecLocale] = useState<boolean | null>(null);

    const tennis = p.sport === 'tennis';
    const attiva = recLocale ?? registra ?? false;
    const fixtureId = p.extra?.fixtureId ?? null;

    /** Prima di andarsene si segna DOVE si era. Senza questo, «torna indietro»
     *  riporta in cima a una lista di sessanta partite. */
    const segnaPunto = () => salvaRitorno({
        rotta: '/control-room', nome: 'Control Room',
        scheda, eventId: p.event_id,
        scorrimento: typeof window === 'undefined' ? 0 : window.scrollY,
    });

    const apriStatistiche = () => {
        if (fixtureId == null) return;
        segnaPunto();
        navigate(`/dashboard?fixture=${fixtureId}&from=control-room`);
    };

    const apriTrading = () => {
        segnaPunto();
        if (tennis && p.marketId) {
            navigate(`/tennis/terminal?event=${encodeURIComponent(p.event_id)}`
                + `&market=${encodeURIComponent(p.marketId)}&name=Match%20Odds&from=control-room`);
        } else {
            navigate(`/segui-live?event=${encodeURIComponent(p.event_id)}&from=control-room`);
        }
    };

    /** SEGUI LIVE = registra l'intero evento. Due strade, una per sport. */
    const cambiaRegistrazione = async () => {
        setInCorso(true); setErrore(null);
        const vuoi = !attiva;
        try {
            if (tennis) {
                if (!p.marketId) throw new Error('manca il mercato Match Odds di questa partita');
                if (vuoi) await followTennisEvent(p.event_id, p.marketId);
                await setTennisFollowRecord(p.event_id, vuoi);
            } else {
                const [casa, ospite] = dividiNomi(p.nome);
                if (vuoi) {
                    if (p.koMs == null) throw new Error('manca l’orario di inizio: il seguito non si può creare');
                    await followMission(p.event_id, casa, ospite, new Date(p.koMs).toISOString());
                }
                await setFollowRecord(p.event_id, vuoi);
            }
            setRecLocale(vuoi);
            onRegistrazione?.(p.event_id, vuoi);
        } catch (e) {
            setErrore(e instanceof Error ? e.message : String(e));
        } finally { setInCorso(false); }
    };

    const dim = compatto ? 'h-6 px-1.5 text-[10px]' : 'h-7 px-2 text-[11px]';

    return (
        <div className="flex items-center gap-1.5 flex-wrap" data-testid="cr-azioni">
            <BetfairMediaButtons eventId={p.event_id} media={p.media} compact={compatto} />

            {/* STATISTICHE — solo calcio, e solo se la partita è agganciata */}
            {!tennis && (
                <Button
                    type="button" size="sm" variant="outline"
                    disabled={fixtureId == null}
                    onClick={apriStatistiche}
                    data-testid="cr-statistiche"
                    title={fixtureId == null
                        ? 'partita non agganciata ai dati statistici: non c’è una scheda da aprire'
                        : 'apri la scheda statistiche di questa partita'}
                    className={`${dim} uppercase tracking-wider`}
                ><BarChart3 className="w-3 h-3 mr-1" />Statistiche</Button>
            )}

            <Button
                type="button" size="sm" variant="outline"
                onClick={apriTrading}
                data-testid="cr-trading"
                title="apri il terminale di trading su questa partita"
                className={`${dim} uppercase tracking-wider`}
            ><LineChart className="w-3 h-3 mr-1" />Trading</Button>

            <Button
                type="button" size="sm"
                variant={attiva ? 'default' : 'outline'}
                disabled={inCorso}
                onClick={() => void cambiaRegistrazione()}
                data-testid="cr-segui-live"
                title={attiva
                    ? 'sta registrando l’intero evento: clicca per fermare'
                    : 'registra l’intero evento; a fine gara finisce nel Match Replay'}
                className={`${dim} uppercase tracking-wider ${
                    attiva ? 'bg-red-600/80 hover:bg-red-600 text-white' : ''
                }`}
            >
                {inCorso
                    ? <Loader2 className="w-3 h-3 animate-spin" />
                    : <><CircleDot className={`w-3 h-3 mr-1 ${attiva ? 'animate-pulse' : ''}`} />
                        {attiva ? 'REC' : 'Segui live'}</>}
            </Button>

            {errore && (
                <span className="text-[10px] text-orange-300" data-testid="cr-azioni-errore">
                    non registrata: {errore}
                </span>
            )}
        </div>
    );
}

/** «Casa v Ospite» / «Casa – Ospite» → i due nomi. Se non si riesce a
 *  dividere si usa il nome intero come casa: meglio un seguito con un nome
 *  approssimativo che nessun seguito. */
export function dividiNomi(nome: string): [string, string] {
    const m = nome.split(/\s+(?:v|vs|-|–|—)\s+/i);
    if (m.length >= 2) return [m[0].trim(), m.slice(1).join(' ').trim()];
    return [nome.trim(), ''];
}

export default AzioniPartita;
