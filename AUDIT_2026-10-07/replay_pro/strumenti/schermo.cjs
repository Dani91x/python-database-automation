// Prova a schermo del replay professionale: pagina VERA montata dal pilota con
// i dati veri (frame dal raw, esito vero del banco). Clic sulle operazioni,
// verifica del salto della timeline, del ladder (ordine evidenziato) e del P&L.
const { chromium } = require('/opt/node22/lib/node_modules/playwright');
const fs = require('fs');
const OUT = process.argv[2];
const BASE = 'http://127.0.0.1:5199/prova_replay_pro.html';
fs.mkdirSync(OUT, { recursive: true });
const esito = [];
const ok = (cond, testo) => { esito.push(`${cond ? 'OK ' : 'KO '} ${testo}`); };

async function apri(page, sport, testoLista) {
    await page.goto(`${BASE}?sport=${sport}`);
    await page.getByText(testoLista).first().click();
    await page.getByText(/Ladder TRAINING|Ladder/).first().waitFor({ timeout: 60000 });
}

(async () => {
    const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
    const page = await browser.newPage({ viewport: { width: 1600, height: 2200 } });
    const errori = [];
    page.on('pageerror', e => errori.push(String(e)));
    // ------------------------------------------------------------ CALCIO
    await apri(page, 'calcio', /Spain/);
    await page.getByRole('button', { name: /Ladder TRAINING/ }).click();
    await page.getByTestId('applica-bot-bot').selectOption('scalper_calcio');
    await page.getByTestId('applica-bot-scenario').selectOption('Scalper - Media Under 2,5');
    await page.getByRole('radio', { name: 'Soldi veri simulati' }).click();
    await page.getByTestId('applica-bot-avvia').click();
    await page.getByTestId('registro-operazioni').waitFor({ timeout: 20000 });
    await page.screenshot({ path: `${OUT}/01_calcio_registro_e_pnl.png`, fullPage: true });
    // clic sul clic RIFIUTATO
    const rif = page.getByTestId('registro-clic-voce').nth(1);
    ok((await rif.textContent()).includes('RIFIUTATO: il ciclo 1 è ancora aperto'), `calcio: clic rifiutato spiegato: ${await rif.textContent()}`);
    // clic su un evento «appoggiata sul book» di una BANCA
    const ev = page.locator('[data-testid="registro-evento"][data-tipo="appoggiato"]').first();
    const ms = Number(await ev.getAttribute('data-ms'));
    await ev.click();
    await page.getByTestId('cursore-esatto').waitFor();
    const cur = await page.getByTestId('cursore-esatto').textContent();
    ok(cur.includes(String(ms % 1000).padStart(3, '0')), `calcio: seek all'istante esatto ${ms}: «${cur}»`);
    const app = page.getByTestId('bot-appoggiato').first();
    await app.waitFor({ timeout: 10000 });
    ok(true, `calcio: sul ladder BANCA appoggiata ${await app.textContent()} @ ${await app.getAttribute('data-quota')} (${await app.getAttribute('data-lato')})`);
    const abb = await page.getByTestId('bot-abbinato').count();
    ok(abb > 0, `calcio: sul ladder ${abb} livelli abbinati del bot`);
    ok((await page.getByTestId('bot-pnl-selezione').count()) > 0, `calcio: P&L del bot sulle selezioni: ${await page.getByTestId('bot-pnl-selezione').first().textContent()}`);
    const ladder = page.locator('[data-testid="bot-pnl-selezione"]').first().locator('xpath=ancestor::div[contains(@class,"rounded-xl")][1]');
    await page.screenshot({ path: `${OUT}/02_calcio_seek_ladder_appoggiata.png`, fullPage: true });
    await ladder.screenshot({ path: `${OUT}/02b_calcio_ladder_dettaglio.png` });
    // clic su un abbinamento totale della banca (chiusura del ciclo)
    const chiusura = page.locator('[data-testid="registro-evento"][data-tipo="abbinato_totale"]').nth(1);
    const ms2 = Number(await chiusura.getAttribute('data-ms'));
    await chiusura.click();
    await page.waitForTimeout(500);
    const conf = await page.getByTestId('confronto-banco').allTextContents();
    ok(conf.every(t => t.startsWith('✓')), `calcio: confronti col banco: ${conf.join(' | ')}`);
    ok((await page.getByTestId('pnl-cicli-al-cursore').textContent()).length > 0, `calcio: P&L cicli al cursore ${await page.getByTestId('pnl-cicli-al-cursore').textContent()} (istante ${ms2})`);
    await page.screenshot({ path: `${OUT}/03_calcio_seek_abbinata_pnl.png`, fullPage: true });
    // ATTIVA ADESSO al cursore: parte SUBITO una richiesta
    const prima = await page.evaluate(() => window.richieste.length);
    await page.getByTestId('applica-bot-attiva-adesso').click();
    await page.waitForTimeout(300);
    const dopo = await page.evaluate(() => window.richieste);
    ok(dopo.length === prima + 1 && Array.isArray(dopo[dopo.length - 1].clic_ms), `calcio: «Attiva adesso» ha mandato SUBITO la richiesta col clic: ${JSON.stringify(dopo[dopo.length - 1])}`);
    await page.screenshot({ path: `${OUT}/04_calcio_attiva_adesso.png`, fullPage: false });
    // ------------------------------------------------------------ TENNIS
    await apri(page, 'tennis', /Barrios|Simakin/);
    await page.getByRole('button', { name: /Ladder/ }).first().click();
    await page.getByTestId('applica-bot-bot').selectOption('tennis_scalper');
    await page.getByTestId('applica-bot-scenario').selectOption("Tennis Scalper - soglie di liquidita' e bande aperte");
    await page.getByTestId('applica-bot-avvia').click();
    await page.getByTestId('registro-operazioni').waitFor({ timeout: 20000 });
    await page.getByRole('radio', { name: 'cronologica' }).click();
    const sp = page.locator('[data-testid="registro-evento"]', { hasText: 'SPOSTATA da 1,01 a 1,69' }).first();
    ok(await sp.count() > 0, 'tennis: il riprezzo di Betfair nel registro («BANCA SPOSTATA da 1,01 a 1,69»)');
    await sp.click();
    await page.getByTestId('cursore-esatto').waitFor();
    await page.waitForTimeout(500);
    const appT = await page.getByTestId('bot-appoggiato').count();
    const abbT = await page.getByTestId('bot-abbinato').count();
    ok(appT + abbT > 0, `tennis: sul ladder ${appT} appoggiati e ${abbT} abbinati del bot all'istante del riprezzo`);
    await page.screenshot({ path: `${OUT}/05_tennis_riprezzo_ladder.png`, fullPage: true });
    ok(errori.length === 0, `errori della pagina: ${errori.length ? errori.join(' / ') : 'nessuno'}`);
    await browser.close();
    fs.writeFileSync(`${OUT}/esito_prova_a_schermo.txt`, esito.join('\n') + '\n');
    console.log(esito.join('\n'));
})().catch(async e => { console.error('ERRORE', e); fs.writeFileSync(`${OUT}/esito_prova_a_schermo.txt`, esito.join('\n') + `\nERRORE ${e}\n`); process.exit(1); });
