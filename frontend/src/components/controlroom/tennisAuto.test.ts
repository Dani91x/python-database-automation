// tennisAuto.test.ts — le PAROLE dell'auto-mode tennis (25/09).
//
// Il finto `stats` ha le IDENTICHE chiavi che scrive il ponte Python
// (`tennis_bot_service._stato_auto`): un nome diverso qui certificherebbe una
// pagina che non legge niente (difetto 33 del catalogo).
import { describe, expect, it } from 'vitest';
import { avvisoUsciteManuali, leggiAutoTennis, notaAutoTennis } from './tennisAuto';

/** `stats` come le scrive il ponte, chiave per chiave */
function stats(auto: Record<string, unknown>): Record<string, unknown> {
    return {
        cadenza_battito_s: 15, partite_esposte: 3, stop_ferma_solo_aperture: true,
        motivo_blocco: null, tetto_partite: 5,
        auto: {
            attivo: true, tetto: 5, armate_feed: 2, armate_a_mano: 1, seguite_a_mano: 1,
            in_attesa: 0, feed_letto: true, feed_vivo: true, feed_partite: 7,
            feed_eta_s: 4.2, fonte: 'safe_strategy_scan', origine_ok: true,
            live_in_dry_run: false, uscite_automatiche: true,
            uscite_sempre_automatiche: false, posizioni_aperte_manuali: 0,
            posizione_aperta_dal: null, letto_at: '2026-09-25T10:00:00+00:00',
            ...auto,
        },
    };
}

describe('leggiAutoTennis', () => {
    it('senza stats.auto non inventa niente', () => {
        expect(leggiAutoTennis(null)).toBeNull();
        expect(leggiAutoTennis({ motivo_blocco: null })).toBeNull();
        expect(leggiAutoTennis({ auto: [] })).toBeNull();
    });
    it('legge le chiavi del ponte', () => {
        const a = leggiAutoTennis(stats({}))!;
        expect(a.armateFeed).toBe(2);
        expect(a.armateAMano).toBe(1);
        expect(a.feedPartite).toBe(7);
        expect(a.usciteAutomatiche).toBe(true);
    });
    it('uscite non dichiarate (colonna assente) = null, mai false', () => {
        expect(leggiAutoTennis(stats({ uscite_automatiche: null }))!.usciteAutomatiche).toBeNull();
    });
});

describe('notaAutoTennis — testi esatti', () => {
    it('armato dal feed e a mano, feed vivo con eta e fonte', () => {
        expect(notaAutoTennis(leggiAutoTennis(stats({})))).toBe(
            'armato su 2 partite dal feed (1 seguite a mano) · tetto 5 · '
            + 'feed tennis: 7 partite, scanner 4 s fa (safe_strategy_scan)');
    });
    it('in attesa del runner: lo dice, non dice "parte"', () => {
        expect(notaAutoTennis(leggiAutoTennis(stats({ in_attesa: 2 })))).toBe(
            'armato su 2 partite dal feed (1 seguite a mano) · 2 in attesa del runner · tetto 5 · '
            + 'feed tennis: 7 partite, scanner 4 s fa (safe_strategy_scan)');
    });
    it('feed fermo: scanner muto da N', () => {
        expect(notaAutoTennis(leggiAutoTennis(stats({
            armate_feed: 0, armate_a_mano: 0, feed_vivo: false, feed_eta_s: 125,
        })))).toBe(
            'armato su 0 partite dal feed (0 seguite a mano) · tetto 5 · '
            + 'feed tennis fermo: scanner muto da 2 min (safe_strategy_scan)');
    });
    it('feed non letto', () => {
        expect(notaAutoTennis(leggiAutoTennis(stats({ feed_letto: false, feed_vivo: false }))))
            .toContain('feed tennis non letto (safe_strategy_scan)');
    });
    it('migrazione assente: auto-mode spento, detto', () => {
        expect(notaAutoTennis(leggiAutoTennis(stats({ origine_ok: false, attivo: false }))))
            .toContain('auto-mode spento: migrazione non applicata');
    });
    it('LIVE: dichiara il dry-run per partita', () => {
        expect(notaAutoTennis(leggiAutoTennis(stats({ live_in_dry_run: true }))))
            .toContain('LIVE: le partite nascono in dry-run, nessun ordine reale finché non lo togli per partita');
    });
    it('null senza auto', () => {
        expect(notaAutoTennis(null)).toBeNull();
    });
});

describe('avvisoUsciteManuali — avviso permanente', () => {
    const now = Date.parse('2026-09-25T10:12:00Z');
    it('automatiche: nessun avviso', () => {
        expect(avvisoUsciteManuali(leggiAutoTennis(stats({})), now)).toBeNull();
    });
    it('non dichiarate: nessun avviso', () => {
        expect(avvisoUsciteManuali(leggiAutoTennis(stats({ uscite_automatiche: null })), now)).toBeNull();
    });
    it('scalper: sempre automatiche, nessun avviso', () => {
        expect(avvisoUsciteManuali(leggiAutoTennis(stats({
            uscite_automatiche: false, uscite_sempre_automatiche: true,
        })), now)).toBeNull();
    });
    it('manuali senza posizione: lo dice lo stesso', () => {
        expect(avvisoUsciteManuali(leggiAutoTennis(stats({ uscite_automatiche: false })), now)).toBe(
            'uscite manuali: il bot non prende profitto da solo (stop e protezioni restano attivi)');
    });
    it('manuali con posizione aperta: da quanto', () => {
        expect(avvisoUsciteManuali(leggiAutoTennis(stats({
            uscite_automatiche: false, posizioni_aperte_manuali: 1,
            posizione_aperta_dal: '2026-09-25T10:00:00+00:00',
        })), now)).toBe(
            'uscite manuali: posizione aperta da 12 min — chiudi con «Chiudi» dalla scheda partita');
    });
    it('manuali con piu posizioni: quante', () => {
        expect(avvisoUsciteManuali(leggiAutoTennis(stats({
            uscite_automatiche: false, posizioni_aperte_manuali: 2,
            posizione_aperta_dal: '2026-09-25T10:11:30+00:00',
        })), now)).toBe(
            'uscite manuali: posizione aperta da 30 s (2 posizioni) — chiudi con «Chiudi» dalla scheda partita');
    });
});
