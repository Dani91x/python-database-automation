// sonda_ordini_esito_b17.mjs - E2E FASE 2 (26/09), SOLA LETTURA. Applica le funzioni di PRODUZIONE
// di frontend/src/lib/esitoAbbinamento.ts (bundle esbuild in scratchpad, nessun file del repo toccato)
// alle righe DB degli ordini paper: fase dell'esito (totale/parziale/...), prezzo medio, delta tick
// fra prezzo della riga e prezzo medio abbinato.
// Uso: node sonda_ordini_esito_b17.mjs <bundle esito.mjs> <righe.json>
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
const [, , bundle, righe] = process.argv;
const E = await import(pathToFileURL(bundle).href);
const dati = JSON.parse(readFileSync(righe, 'utf8'));
for (const bot of Object.keys(dati)) {
  for (const r of dati[bot] || []) {
    const g = E.esitoGamba(E.comeRigaOrdine(r));
    const d = E.deltaTick(r.price, g.prezzoMedio, r.side);
    console.log(JSON.stringify({ bot, id: r.id, status: r.status, fase: g.fase, chiesto: g.chiesto,
      abbinato: g.abbinato, residuo: g.residuo, prezzoMedio: g.prezzoMedio, numeriDallaRiga: g.numeriDallaRiga,
      delta_vs_prezzo_riga: d ? E.testoDelta(d) : null }));
  }
}
