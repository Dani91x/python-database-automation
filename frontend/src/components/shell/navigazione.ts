// ============================================================================
// navigazione — le voci della sidebar del guscio v2 e cosa mostra la testata.
//
// Dati puri, nessuna lettura. Ogni voce porta a una rotta che ESISTE GIA' in
// App.tsx (lo verifica AppShell.test.tsx): il guscio non aggiunge pagine, ne'
// funzioni. Gruppi e nomi come nel prototipo approvato
// (AUDIT_2026-10-01/REDESIGN/prototipo/js/boot.js).
// ============================================================================
import type { LocalSport } from '@/lib/localChannel';

export type SportVoce = 'calcio' | 'tennis' | 'comune';

export type IconaVoce =
    | 'home' | 'radar' | 'cruscotto' | 'omega' | 'scudo' | 'bersaglio' | 'impulso' | 'storico'
    | 'tennis' | 'ladder' | 'bot' | 'griglia' | 'popout' | 'occhio' | 'portafoglio' | 'stella'
    | 'replay' | 'grafico' | 'report' | 'libro' | 'scambio' | 'esci';

export interface VoceNav {
    /** chiave unica della voce (anche data-testid: `shell-voce-<id>`) */
    id: string;
    etichetta: string;
    /** rotta esistente di App.tsx; null per «Esci» (azione) */
    rotta: string | null;
    icona: IconaVoce;
    sport: SportVoce;
    /** la voce apre una finestra a parte (Ladder pop-out), come fa oggi LadderView */
    finestra?: true;
    /** spiegazione al passaggio del mouse */
    nota?: string;
    /** 09/10 (R-5): la voce si vede SOLO con il monitor «Salute» acceso
     *  (MONITOR_SALUTE=1 nel .env alla build, `lib/monitorSalute.ts`); spento = voce assente */
    soloConMonitor?: true;
}

export interface GruppoNav {
    id: string;
    titolo: string | null;
    sport: SportVoce;
    voci: VoceNav[];
}

export const NAV: readonly GruppoNav[] = [
    {
        id: 'inizio', titolo: null, sport: 'comune', voci: [
            { id: 'board', etichetta: 'Programma del giorno', rotta: '/board', icona: 'home', sport: 'comune' },
            { id: 'control-room', etichetta: 'Control Room', rotta: '/control-room', icona: 'radar', sport: 'comune' },
            // 08/10 (W1): la pagina «Cash Out», subito sotto la Control Room
            { id: 'cash-out', etichetta: 'Cash Out', rotta: '/cash-out', icona: 'portafoglio', sport: 'comune' },
        ],
    },
    {
        id: 'calcio', titolo: 'Calcio', sport: 'calcio', voci: [
            { id: 'dashboard', etichetta: 'Cruscotto partite', rotta: '/dashboard', icona: 'cruscotto', sport: 'calcio' },
            { id: 'omega', etichetta: 'Omega', rotta: '/omega', icona: 'omega', sport: 'calcio' },
            { id: 'safe-strategy', etichetta: 'Safe Strategy', rotta: '/safe-strategy', icona: 'scudo', sport: 'calcio' },
            { id: 'mike', etichetta: 'Mike', rotta: '/mike', icona: 'bersaglio', sport: 'calcio' },
            { id: 'segui-live', etichetta: 'Segui live · Scalper', rotta: '/segui-live', icona: 'impulso', sport: 'calcio' },
            { id: 'storico-calcio', etichetta: 'Storico calcio', rotta: '/storico/calcio', icona: 'storico', sport: 'calcio' },
        ],
    },
    {
        id: 'tennis', titolo: 'Tennis', sport: 'tennis', voci: [
            { id: 'tennis', etichetta: 'Dashboard tennis', rotta: '/tennis', icona: 'tennis', sport: 'tennis' },
            { id: 'tennis-terminal', etichetta: 'Tennis Terminal', rotta: '/tennis/terminal', icona: 'ladder', sport: 'tennis' },
            { id: 'tennis-replay', etichetta: 'Replay tennis', rotta: '/tennis/replay', icona: 'replay', sport: 'tennis' },
            {
                id: 'bot-tennis', etichetta: 'Bot tennis', rotta: '/tennis/terminal', icona: 'bot', sport: 'tennis',
                nota: 'I 4 bot tennis stanno nel Tennis Terminal (pannello Bot Tennis)',
            },
            {
                id: 'safe-strategy-tennis', etichetta: 'Safe Strategy · Tennis', rotta: '/safe-strategy', icona: 'scudo', sport: 'tennis',
                nota: 'Safe Strategy: il tennis e\' la scheda «🎾 Tennis» della pagina',
            },
            { id: 'storico-tennis', etichetta: 'Storico tennis', rotta: '/storico/tennis', icona: 'storico', sport: 'tennis' },
        ],
    },
    {
        id: 'trading', titolo: 'Trading', sport: 'comune', voci: [
            { id: 'multi-ladder', etichetta: 'Multi-ladder', rotta: '/multi-ladder', icona: 'griglia', sport: 'comune' },
            {
                id: 'ladder-popout', etichetta: 'Ladder pop-out', rotta: '/ladder-popout', icona: 'popout', sport: 'comune', finestra: true,
                nota: 'Apre la finestra pop-out (560×860). Un mercato si stacca dal bottone «stacca» di ogni ladder',
            },
            { id: 'market-watch', etichetta: 'Market watch', rotta: '/market-watch', icona: 'occhio', sport: 'comune' },
            { id: 'live-pnl', etichetta: 'Live P&L', rotta: '/live-pnl', icona: 'portafoglio', sport: 'comune' },
            { id: 'watchlist', etichetta: 'Watchlist', rotta: '/watchlist', icona: 'stella', sport: 'comune' },
        ],
    },
    {
        id: 'analisi', titolo: 'Analisi', sport: 'comune', voci: [
            { id: 'match-replay', etichetta: 'Match replay', rotta: '/match-replay', icona: 'replay', sport: 'comune' },
            { id: 'analytics', etichetta: 'Analytics', rotta: '/analytics', icona: 'grafico', sport: 'comune' },
            { id: 'report-personale', etichetta: 'Report personale', rotta: '/report-personale', icona: 'report', sport: 'comune' },
            { id: 'trade-journal', etichetta: 'Trade journal', rotta: '/trade-journal', icona: 'libro', sport: 'comune' },
            // 09/10 (T0A): la pagina «Salute» (monitor dei servizi dell'app, sola lettura)
            {
                id: 'salute', etichetta: 'Salute', rotta: '/salute', icona: 'impulso', sport: 'comune',
                nota: 'CPU, memoria, richieste e tempi dei servizi (MONITOR_SALUTE=1)',
                soloConMonitor: true,
            },
        ],
    },
    {
        id: 'account', titolo: 'Account', sport: 'comune', voci: [
            { id: 'select-sport', etichetta: 'Scelta sport', rotta: '/select-sport', icona: 'scambio', sport: 'comune' },
            { id: 'esci', etichetta: 'Esci', rotta: null, icona: 'esci', sport: 'comune' },
        ],
    },
];

/** Le rotte rese DENTRO il guscio quando `ui.shell = 'v2'` (brief, punto 2). */
export const ROTTE_NEL_GUSCIO: readonly string[] = [
    '/board', '/control-room', '/cash-out', '/dashboard', '/omega', '/safe-strategy', '/mike', '/segui-live',
    '/multi-ladder', '/market-watch', '/live-pnl', '/storico/calcio', '/storico/tennis', '/tennis',
    '/tennis/terminal', '/tennis/replay', '/trade-journal', '/report-personale', '/watchlist', '/analytics',
    '/match-replay', '/select-sport', '/salute',
];

export type FiltroSport = 'tutti' | 'calcio' | 'tennis';

/** Il filtro della sidebar nasconde SOLO voci di menu: nessun dato cambia. */
export function gruppiVisibili(filtro: FiltroSport, monitorAttivo = false): GruppoNav[] {
    return NAV.filter((g) => {
        if (filtro === 'calcio') return g.sport !== 'tennis';
        if (filtro === 'tennis') return g.sport !== 'calcio';
        return true;
    }).map((g) => ({
        ...g,
        // 09/10 (R-5): a monitor spento la voce «Salute» non c'e' (la rotta resta)
        voci: g.voci.filter((v) => !v.soloConMonitor || monitorAttivo),
    }));
}

/** Titolo e gruppo della pagina per la testata (prima voce che porta alla rotta). */
export function titoloDi(pathname: string): { gruppo: string | null; titolo: string } | null {
    for (const g of NAV) {
        for (const v of g.voci) {
            if (v.rotta === pathname && !v.finestra) return { gruppo: g.titolo, titolo: v.etichetta };
        }
    }
    return null;
}

/**
 * I canali locali che la PAGINA apre gia' da sola appena montata (misurati dalla
 * fotografia, src/fotografia: WebSocket costruiti per pagina con backend vuoto).
 * La testata mostra lo stato SOLO di questi: chiedere lo stato di un altro
 * canale lo aprirebbe (getLocalChannel connette al primo accesso), cioe' una
 * connessione in piu' che il guscio non deve fare. Sulle altre pagine la testata
 * non mostra l'indicatore dei canali (dichiarato nel referto).
 */
export const CANALI_DELLA_PAGINA: Readonly<Record<string, readonly LocalSport[]>> = {
    '/board': ['calcio', 'tennis'],
    '/control-room': ['calcio', 'tennis', 'mike', 'omega', 'safe', 'scanner', 'tennis_bot', 'scalper'],
    // 08/10 (W1): la pagina Cash Out monta lo stesso useControlRoom (stessi 8 canali, verificato dalla fotografia)
    '/cash-out': ['calcio', 'tennis', 'mike', 'omega', 'safe', 'scanner', 'tennis_bot', 'scalper'],
    '/omega': ['omega'],
    '/safe-strategy': ['safe'],
    '/mike': ['mike'],
    '/market-watch': ['calcio', 'tennis'],
    '/live-pnl': ['calcio', 'tennis'],
};

/** Nome leggibile di un canale locale. */
export const NOME_CANALE: Readonly<Record<LocalSport, string>> = {
    calcio: 'Runner calcio',
    tennis: 'Runner tennis',
    mike: 'Mike',
    omega: 'Omega',
    safe: 'Safe Strategy',
    scanner: 'Scanner',
    tennis_bot: 'Bot tennis',
    scalper: 'Scalper calcio',
};
