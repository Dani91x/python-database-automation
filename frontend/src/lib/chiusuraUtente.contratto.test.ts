// ============================================================================
// chiusuraUtente.contratto.test.ts — IL CONTRATTO SERVIZIO ↔ UI, lato TS.
//
// È il gemello dei due test di contratto Python
// (`Betfair/omega/test_omega_ui_contratto_2026_09_11.py` e
// `Betfair/safe_strategy/tests/test_audit_2026_09_11.py`), che oggi sono
// tornati a MORDERE: le liste `_KIND_IN_ATTESA_DI_UI` e `_IN_ATTESA_DI_PANNELLO`
// non esistono più. Qui si controlla la stessa cosa dal lato del frontend,
// così una regressione si vede anche senza far girare pytest.
//
// I due elenchi qui sotto sono COPIATI dal catalogo del servizio:
//   · Safe  → `tests/test_audit_2026_09_11.test_h16_catalogo_dei_kind_di_attivita`
//             (`chiuso_dall_utente`, `posizione_di_conto`, `riprendi_evento`);
//   · Omega → `omega_service.py` (`chiuso_dall_utente`) + la RPC
//             `omega_evento_riprendi` (`evento_ripreso`);
//   · parametri → `Betfair/omega/omega_config._SPEC` (`conto_every_s`,
//             `strategy_version`, i quindici `v3_*`).
//
// FALSIFICAZIONE (verificata: i test diventano rossi):
//   · togliere `chiuso_dall_utente` da `SAFE_ACTIVITY_EXTRA` → rosso;
//   · togliere `conto_every_s` da `OMEGA_PARAM_GROUPS` → rosso;
//   · mettere in `OMEGA_PARAM_DEFAULTS` `strategy_version: 3` → rosso.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { SAFE_ACTIVITY_EXTRA, safeActivityMeta, safeActivityLine, safeReasonLabel } from '@/components/safestrategy/safeActivity';
import { OMEGA_ACTIVITY_EXTRA, OMEGA_PARAM_KEYS, OMEGA_PARAM_DEFAULTS, activityMeta } from './omega';

const SAFE_KIND_NUOVI = ['chiuso_dall_utente', 'posizione_di_conto', 'riprendi_evento'];
const OMEGA_KIND_NUOVI = ['chiuso_dall_utente', 'evento_ripreso'];

/** i default DICHIARATI dal servizio (`omega_config._SPEC`), chiave per chiave */
const V3_DEFAULT: Record<string, number | string> = {
    conto_every_s: 120,
    strategy_version: 2,
    v3_stake_eur: 1,
    v3_modello: 'gamma_poisson',
    v3_k_minimo: 2,
    v3_empirical_min_n: 200,
    v3_ht_entry_min: 25,
    v3_ht_entry_max: 44,
    v3_ft_entry_min: 55,
    v3_ft_entry_max: 85,
    v3_max_liability_per_leg: 120,
    v3_max_liability_per_match: 240,
    v3_max_open_liability: 2000,
    v3_daily_loss_cap: 400,
    v3_min_lay_liquidity: 1,
    v3_distanza_minima_gol: 1,
    v3_p_max_pct: 2,
    v3_fusione_mercato: 'auto',
};

describe('SAFE — i kind della chiusura dell utente hanno la loro etichetta', () => {
    it('nessuno cade nel traduttore parola per parola', () => {
        for (const k of SAFE_KIND_NUOVI) {
            expect(SAFE_ACTIVITY_EXTRA[k], `kind senza etichetta: ${k}`).toBeTruthy();
            const l = safeActivityMeta(k).label;
            expect(l, `etichetta = chiave inglese per ${k}`).not.toBe(k.toUpperCase().replace(/_/g, ' '));
        }
    });

    it('«chiusa da te» e CRITICO: il bot smette di operare su quella partita', () => {
        expect(SAFE_ACTIVITY_EXTRA.chiuso_dall_utente.critical).toBe(true);
        expect(SAFE_ACTIVITY_EXTRA.posizione_di_conto.critical).toBe(true);
    });

    it('il motivo dei salti («partita_chiusa_dall_utente») e in italiano', () => {
        const t = safeReasonLabel('partita_chiusa_dall_utente') ?? '';
        expect(t).toMatch(/chiusa da te/i);
        expect(t).toMatch(/Riprendi/);
        expect(t).not.toContain('_');
    });

    it('la riga racconta COME e QUANTE righe, non un JSON nudo', () => {
        const riga = safeActivityLine({
            event_id: '35797769', come: 'cashout_event', righe_marcate: 3, mode: 'live',
        });
        expect(riga).toMatch(/cash out globale/i);
        expect(riga).toMatch(/3 righe marcate/);
    });

    it('il VERDETTO della lettura di conto arriva in italiano, e i tre sono diversi', () => {
        const chiusa = safeActivityLine({ verdetto: 'chiusa_dall_utente' });
        const ridotta = safeActivityLine({ verdetto: 'ridotta_dall_utente' });
        const perse = safeActivityLine({ verdetto: 'gambe_non_ritrovate' });
        expect(chiusa).toMatch(/l’hai chiusa tu/);
        expect(ridotta).toMatch(/continua a proteggere/);
        expect(perse).toMatch(/riconciliazione/);
        expect(new Set([chiusa, ridotta, perse]).size).toBe(3);
    });
});

describe('OMEGA — i kind e i parametri nuovi hanno la loro UI', () => {
    it('ogni kind nuovo ha la sua etichetta italiana', () => {
        for (const k of OMEGA_KIND_NUOVI) {
            expect(OMEGA_ACTIVITY_EXTRA[k], `kind senza etichetta: ${k}`).toBeTruthy();
            expect(activityMeta(k).label).not.toBe(k.toUpperCase());
        }
    });

    it('«chiusa da te» e CRITICO anche su Omega', () => {
        expect(OMEGA_ACTIVITY_EXTRA.chiuso_dall_utente.critical).toBe(true);
    });

    it('tutte le chiavi nuove della whitelist hanno un campo nel pannello', () => {
        const mancanti = Object.keys(V3_DEFAULT).filter((k) => !OMEGA_PARAM_KEYS.includes(k));
        expect(mancanti, `chiavi del servizio senza UI: ${mancanti.join(', ')}`).toEqual([]);
    });

    it('nessun campo compare due volte nel pannello', () => {
        const dupes = OMEGA_PARAM_KEYS.filter((k, i) => OMEGA_PARAM_KEYS.indexOf(k) !== i);
        expect(dupes).toEqual([]);
    });

    it('i default della UI sono ESATTAMENTE quelli del servizio', () => {
        const d = OMEGA_PARAM_DEFAULTS as unknown as Record<string, unknown>;
        for (const [k, want] of Object.entries(V3_DEFAULT)) {
            expect(d[k], `default divergente per ${k}`).toBe(want);
        }
    });

    it('v3 resta IN OMBRA: il default della versione e 2, non 3', () => {
        // portarlo a 3 qui cambierebbe il motore che decide gli ingressi con un
        // «Salva» fatto per cambiare altro. Lo switch lo ordina l utente.
        expect(OMEGA_PARAM_DEFAULTS.strategy_version).toBe(2);
    });
});
