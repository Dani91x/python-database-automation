// 08/10 (Replay Tennis, caso vero 35797566): l'elenco dichiara i mercati
// registrati di ogni partita e, se nessun bot tennis ha il suo mercato, lo dice
// col testo del banco. Senza la migrazione (`market_types` assente) l'elenco e'
// quello di prima. Righe con le chiavi vere di list_replays_tennis.
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TennisReplayList } from './TennisReplayList';
import { motivoNessunBotTennis, notaNomeGiocatore, NOTA_NOME_IPS, type TennisReplayItem } from '@/lib/tennisReplay';

function riga(event_id: string, market_types?: string[] | null): TennisReplayItem {
    const r: TennisReplayItem = {
        event_id, competition_name: 'ATP Wimbledon', player1_name: 'A', player2_name: 'B',
        open_date: '2026-07-07T10:00:00+00:00', n_markets: market_types?.length ?? 1,
        n_snapshots: 100, n_score: 10, ts_min: '2026-07-07T10:00:00+00:00',
        ts_max: '2026-07-07T12:00:00+00:00', fonte: 'import',
    };
    if (market_types !== undefined) r.market_types = market_types;
    return r;
}

describe('TennisReplayList - mercati registrati (08/10)', () => {
    it('solo SET_BETTING: mercati elencati e bot non applicabili col motivo', () => {
        render(<TennisReplayList items={[riga('35797566', ['SET_BETTING']), riga('35793960', ['SET_BETTING', 'MATCH_ODDS'])]}
            onSelect={() => undefined} />);
        expect(screen.getByTestId('tennis-replay-mercati-35797566').textContent).toBe('mercati registrati:SET_BETTING');
        expect(screen.getByTestId('tennis-replay-bot-non-applicabili-35797566').textContent).toBe(
            "Applica bot non disponibile: per la partita 35797566 e' registrato solo il SET_BETTING: "
            + "i bot tennis lavorano sul Match Odds, che non e' stato registrato");
        expect(screen.getByTestId('tennis-replay-mercati-35793960').textContent).toBe('mercati registrati:MATCH_ODDSSET_BETTING');
        expect(screen.queryByTestId('tennis-replay-bot-non-applicabili-35793960')).toBeNull();
    });

    it('senza la migrazione (market_types assente): elenco di prima, nessun avviso', () => {
        render(<TennisReplayList items={[riga('35790089')]} onSelect={() => undefined} />);
        expect(screen.queryByTestId('tennis-replay-mercati-35790089')).toBeNull();
        expect(screen.queryByTestId('tennis-replay-bot-non-applicabili-35790089')).toBeNull();
        expect(motivoNessunBotTennis(riga('35790089'))).toBeNull();
    });

    it('nessun mercato registrato: motivo «solo punteggi»', () => {
        expect(motivoNessunBotTennis(riga('35791111', []))).toMatch(/solo punteggi/);
    });
});

// 08/10 (cantiere 14): il nome dall'IPS e' troncato e l'elenco lo dice (tooltip), mai come se fosse intero.
describe('TennisReplayList - nome dall\'IPS, troncato (08/10)', () => {
    it('notaNomeGiocatore: solo la fonte `ips` ha la nota, per il giocatore giusto', () => {
        expect(notaNomeGiocatore({ player1_name: 'ips', player2_name: 'catalogo' }, 1)).toBe(NOTA_NOME_IPS);
        expect(notaNomeGiocatore({ player1_name: 'ips', player2_name: 'catalogo' }, 2)).toBeUndefined();
        for (const f of ['catalogo', 'marketdef', 'evento', 'id', '']) {
            expect(notaNomeGiocatore({ player1_name: f, player2_name: f }, 1)).toBeUndefined();
        }
        expect(notaNomeGiocatore(null, 1)).toBeUndefined();
        expect(notaNomeGiocatore(undefined, 2)).toBeUndefined();
        expect(notaNomeGiocatore({}, 2)).toBeUndefined();
        expect(NOTA_NOME_IPS).toBe("nome dall'IPS, troncato");
    });

    it('l\'elenco mette il tooltip sul solo nome dall\'IPS e nessuna nota senza la migrazione', () => {
        const con = { ...riga('35790089'), player1_name: 'Marcelo Tomas Barrios V', player2_name: 'Ilia Simakin',
            nomi_fonte: { player1_name: 'ips', player2_name: 'catalogo' } };
        const senza = { ...riga('35794049'), player1_name: 'Jannik Sinner', player2_name: 'Alexander Struff' };
        render(<TennisReplayList items={[con, senza]} onSelect={() => undefined} />);
        expect(screen.getByText('Marcelo Tomas Barrios V')).toHaveAttribute('title', "nome dall'IPS, troncato");
        expect(screen.getByText('Ilia Simakin')).not.toHaveAttribute('title');
        expect(screen.getByText('Jannik Sinner')).not.toHaveAttribute('title');
        expect(screen.getByText('Alexander Struff')).not.toHaveAttribute('title');
    });
});
