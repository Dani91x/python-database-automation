// ============================================================================
// Testata globale del guscio v2 — SOLA LETTURA, nessun comando operativo.
//
// Cosa mostra:
//   - dove sei (gruppo + pagina, dalle voci della sidebar);
//   - lo stato dei canali locali, ma SOLO di quelli che la pagina corrente apre
//     gia' da sola (CANALI_DELLA_PAGINA): useLocalStatus legge il client gia'
//     esistente; chiedere un canale che la pagina non apre ne aprirebbe uno
//     nuovo, e il guscio non deve. Sulle altre pagine l'indicatore non c'e'.
//     Pallino grigio = spento: mai verde finto;
//   - il bottone «Torna alla grafica attuale» (un clic: ui.shell = 'off').
//
// Cosa NON mostra (dichiarato nel referto): ordini LIVE/PROVA per bot e saldo
// CONTO. Oggi li legge solo la Control Room (useControlRoom, SaldoBetfairCard):
// per averli qui servirebbero letture nuove. Restano dove sono, identici.
// ============================================================================
import { useLocation } from 'react-router-dom';
import { Undo2 } from 'lucide-react';
import { useLocalStatus } from '@/lib/localTransport';
import { urlCanale, type LocalSport } from '@/lib/localChannel';
import { cambiaUiShell } from '@/lib/uiShell';
import { CANALI_DELLA_PAGINA, NOME_CANALE, titoloDi } from './navigazione';

function porta(sport: LocalSport): string {
    return urlCanale(sport, null).replace('ws://127.0.0.1:', '');
}

function LedCanale({ sport }: { sport: LocalSport }) {
    const stato = useLocalStatus(sport);
    const acceso = stato === 'connected';
    return (
        <span
            className="flex items-center gap-1.5"
            data-testid={`shell-canale-${sport}`}
            data-stato={acceso ? 'connesso' : 'spento'}
            title={`${NOME_CANALE[sport]} · ws://127.0.0.1:${porta(sport)} · ${acceso ? 'connesso' : 'spento'}`}
        >
            <span className={`ds-led ${acceso ? 'ds-led-on' : 'ds-led-off'}`} aria-hidden="true" />
            {/* il nome si legge da 1536 px in su; sotto resta nel tooltip e per i lettori di schermo */}
            <span className="hidden text-muted-foreground 2xl:inline">{NOME_CANALE[sport]}</span>
            <span className="sr-only">{`${NOME_CANALE[sport]} ${acceso ? 'connesso' : 'spento'}`}</span>
        </span>
    );
}

function Canali({ canali }: { canali: readonly LocalSport[] }) {
    return (
        <div
            className="ds-stat hidden lg:flex"
            data-testid="shell-canali"
            title={`Canali locali che questa pagina usa (ws://127.0.0.1): ${canali.map((s) => `${NOME_CANALE[s]} :${porta(s)}`).join(' · ')}`}
        >
            <span className="text-muted-foreground">Canali</span>
            {canali.map((s) => (
                <LedCanale key={s} sport={s} />
            ))}
        </div>
    );
}

export function TestataGlobale() {
    const { pathname } = useLocation();
    const dove = titoloDi(pathname);
    const canali = CANALI_DELLA_PAGINA[pathname];
    return (
        <header className="ds-topbar" data-testid="shell-testata">
            <div className="flex min-w-[9rem] flex-col">
                {dove?.gruppo && <small className="ds-lbl">{dove.gruppo}</small>}
                <b className="truncate font-display text-[15px] font-bold">{dove?.titolo ?? pathname}</b>
            </div>
            <div className="flex-1" />
            {canali && <Canali key={pathname} canali={canali} />}
            <button
                type="button"
                className="ds-stat hover:border-primary/60 hover:text-foreground"
                data-testid="shell-torna-grafica-attuale"
                title="Torna alla grafica attuale (un clic, ricarica la pagina)"
                onClick={() => cambiaUiShell('off')}
            >
                <Undo2 className="h-3.5 w-3.5" aria-hidden="true" />
                Torna alla grafica attuale
            </button>
        </header>
    );
}
