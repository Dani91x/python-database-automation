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
    /**
     * Il REGISTRATORE di questo sport è vivo?
     *
     * ⚠️ REVIEW 15/09 — il pulsante diventava REC rosso appena la RPC
     * rispondeva OK, cioè appena il FLAG era scritto sul database. Ma la
     * registrazione la fa il PROCESSO, non il flag: `live_follow.record` lo
     * legge il runner calcio, `tennis_live_follow.record` quello tennis.
     * Runner fermo = spia rossa e zero registrazione.
     * `null` = non lo sappiamo, e allora si dice «flag acceso» senza
     * promettere che stia registrando.
     */
    registratoreVivo?: boolean | null;
    /** avvisa la pagina che lo stato della registrazione è cambiato */
    onRegistrazione?: (eventId: string, attiva: boolean) => void;
    compatto?: boolean;
}

export function AzioniPartita({
    p, scheda, registra = null, registratoreVivo = null, onRegistrazione, compatto = true,
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

    /**
     * TRADING — porta al terminale di quella partita.
     *
     * ⚠️ REVIEW 15/09, due difetti nello stesso gesto:
     *
     *  1. Sul CALCIO navigava senza creare il seguito. `/segui-live` non lo
     *     crea: arma un'attesa e mostra «Richiesta registrata» con lo
     *     spinner, senza timeout né via d'uscita — una promessa che nessuno
     *     mantiene. Il repo sa già fare la cosa giusta (`MissionPanel`
     *     registra e SOLO DOPO naviga), e `omega_mission_follow` è
     *     idempotente, quindi su una partita già seguita non cambia niente.
     *  2. Sul TENNIS non passava `p1`/`p2`, e il terminale scriveva
     *     «Giocatore 1» e «Giocatore 2» — nell'intestazione, nel titolo,
     *     sulle due colonne della ladder e sul popout degli ordini. Un nome
     *     ignoto stampato come un nome finto. I nomi ce li abbiamo.
     */
    const apriTrading = async () => {
        setInCorso(true); setErrore(null);
        try {
            const [g1, g2] = dividiNomi(p.nome);
            if (tennis && p.marketId) {
                const q = new URLSearchParams({
                    event: p.event_id, market: p.marketId,
                    name: 'Match Odds', from: 'control-room',
                });
                if (g1 && g2) { q.set('p1', g1); q.set('p2', g2); }
                segnaPunto();
                navigate(`/tennis/terminal?${q.toString()}`);
                return;
            }
            // calcio: prima il seguito, poi si naviga. Se fallisce si resta qui
            // e lo si dice, invece di mandare il trader su una schermata che
            // aspetta per sempre.
            if (p.koMs == null) {
                throw new Error('manca l’orario di inizio: il seguito non si può creare');
            }
            await followMission(p.event_id, g1 || p.nome, g2, new Date(p.koMs).toISOString());
            segnaPunto();
            navigate(`/segui-live?event=${encodeURIComponent(p.event_id)}&from=control-room`);
        } catch (e) {
            setErrore(e instanceof Error ? e.message : String(e));
        } finally { setInCorso(false); }
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
                disabled={inCorso}
                onClick={() => void apriTrading()}
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
                    ? (registratoreVivo === false
                        ? 'flag acceso ma il registratore di questo sport è SPENTO: non sta registrando niente'
                        : registratoreVivo === true
                            ? 'sta registrando l’intero evento: clicca per fermare'
                            : 'flag acceso; non sappiamo se il registratore stia ascoltando')
                    : tennis
                        ? 'registra l’intero evento per i laboratori tennis'
                        : 'registra l’intero evento; a fine gara finisce nel Match Replay'}
                className={`${dim} uppercase tracking-wider ${
                    attiva
                        ? registratoreVivo === false
                            ? 'bg-orange-600/70 hover:bg-orange-600 text-white'
                            : 'bg-red-600/80 hover:bg-red-600 text-white'
                        : ''
                }`}
            >
                {inCorso
                    ? <Loader2 className="w-3 h-3 animate-spin" />
                    : <><CircleDot className={`w-3 h-3 mr-1 ${attiva && registratoreVivo !== false ? 'animate-pulse' : ''}`} />
                        {attiva ? (registratoreVivo === false ? 'REC?' : 'REC') : 'Segui live'}</>}
            </Button>

            {/* un flag acceso senza nessuno che ascolti NON è una registrazione */}
            {attiva && registratoreVivo === false && (
                <span className="text-[10px] text-orange-300" data-testid="cr-rec-senza-registratore">
                    registratore {tennis ? 'tennis' : 'calcio'} spento: il flag è acceso ma
                    <strong> non sta registrando</strong>
                </span>
            )}

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
