// ============================================================================
// ambiente_runner.test.js — TEST DI CONTRATTO dell'ambiente dei runner (04/10).
// Esecuzione: `node --test desktop/ambiente_runner.test.js` (runner di test integrato di Node, nessuna
// installazione: desktop/ non ha un runner di test suo).
//
// Contratto (cantiere tetto tennis, incidente del 04/10):
//   * l'ambiente NON puo' rendere il tennis «solo prova» quando l'installazione e'
//     abilitata al live (`LIVE_ORDER_MODE=LIVE` nel `.env`);
//   * NON puo' renderlo live quando l'installazione non lo e';
//   * `TENNIS_LIVE_ORDER_MODE` scritto vince sempre (ambiente, poi `.env`);
//   * mai OFF di default; un valore illeggibile non sale mai.
// ============================================================================
'use strict';

const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const { tettoTennis, costruisciEnvRunner } = require('./ambiente_runner');

const base = { bootId: 'boot-1', token: 'tok' };
const env = (processEnv, envFile) => costruisciEnvRunner({ processEnv, envFile, ...base });

test('installazione abilitata al live: il tennis NON e\' solo prova', () => {
    assert.strictEqual(env({}, { LIVE_ORDER_MODE: 'LIVE' }).TENNIS_LIVE_ORDER_MODE, 'LIVE');
    assert.strictEqual(env({}, { LIVE_ORDER_MODE: 'live ' }).TENNIS_LIVE_ORDER_MODE, 'LIVE');
    assert.strictEqual(env({ LIVE_ORDER_MODE: 'LIVE' }, {}).TENNIS_LIVE_ORDER_MODE, 'LIVE');
});

test('installazione NON abilitata al live: il tennis non diventa live', () => {
    for (const calcio of ['PAPER', 'OFF', '', 'sconosciuto', undefined]) {
        const e = env({}, calcio === undefined ? {} : { LIVE_ORDER_MODE: calcio });
        assert.strictEqual(e.TENNIS_LIVE_ORDER_MODE, 'PAPER', `calcio=${calcio}`);
    }
});

test('TENNIS_LIVE_ORDER_MODE scritto vince (ambiente, poi .env)', () => {
    assert.strictEqual(tettoTennis({ TENNIS_LIVE_ORDER_MODE: 'PAPER' }, { LIVE_ORDER_MODE: 'LIVE' }), 'PAPER');
    assert.strictEqual(tettoTennis({}, { TENNIS_LIVE_ORDER_MODE: 'PAPER', LIVE_ORDER_MODE: 'LIVE' }), 'PAPER');
    assert.strictEqual(tettoTennis({}, { TENNIS_LIVE_ORDER_MODE: 'LIVE', LIVE_ORDER_MODE: 'PAPER' }), 'LIVE');
    assert.strictEqual(tettoTennis({ TENNIS_LIVE_ORDER_MODE: 'LIVE' }, { TENNIS_LIVE_ORDER_MODE: 'PAPER' }), 'LIVE');
    assert.strictEqual(tettoTennis({ TENNIS_LIVE_ORDER_MODE: 'OFF' }, {}), 'OFF');
});

test('valore scritto ma illeggibile: mai sopra la prova', () => {
    assert.strictEqual(tettoTennis({ TENNIS_LIVE_ORDER_MODE: 'live!' }, { LIVE_ORDER_MODE: 'LIVE' }), 'PAPER');
    assert.strictEqual(tettoTennis({ TENNIS_LIVE_ORDER_MODE: '   ' }, { LIVE_ORDER_MODE: 'LIVE' }), 'LIVE');
});

test('l\'ambiente porta impronta d\'avvio e token, e non copia il .env', () => {
    const e = env({ PATH: 'x' }, { LIVE_ORDER_MODE: 'LIVE', BETFAIR_PASSWORD: 'segreto' });
    assert.strictEqual(e.APP_BOOT_ID, 'boot-1');
    assert.strictEqual(e.LOCAL_CHANNEL_TOKEN, 'tok');
    assert.strictEqual(e.PATH, 'x');
    assert.strictEqual(e.BETFAIR_PASSWORD, undefined);
    assert.strictEqual(e.LIVE_RUNNER_KEEP_ALIVE, '1');
    assert.strictEqual(e.TENNIS_ORDER_POLL_SEC, '0.15');
});

test('main.js usa la funzione pura e non forza piu\' PAPER', () => {
    const src = fs.readFileSync(path.join(__dirname, 'main.js'), 'utf8');
    assert.match(src, /costruisciEnvRunner\(\{/);
    assert.match(src, /envFile: readEnvFile\(path\.join\(repoRoot, '\.env'\)\)/);
    assert.doesNotMatch(src, /TENNIS_LIVE_ORDER_MODE:\s*process\.env\.TENNIS_LIVE_ORDER_MODE\s*\|\|/);
});
