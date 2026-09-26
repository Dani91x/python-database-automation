// FIX-A (26/09) - estrae i corpi delle funzioni da un file di migrazione e ne
// stampa md5/lunghezza SENZA \r: si confrontano con
//   select md5(replace(prosrc, E'\r','')) from pg_proc ...
// per sapere quale file e' quello davvero applicato (sola lettura).
// Uso: node corpi.mjs <file.sql> <nome_funzione>
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

const [, , file, fname] = process.argv;
const src = readFileSync(file, 'utf8');
const re = new RegExp(`CREATE OR REPLACE FUNCTION public\\.${fname}\\s*\\(`, 'g');
let m;
let i = 0;
while ((m = re.exec(src))) {
  const start = m.index;
  const tagM = /AS\s+(\$[a-zA-Z_]*\$)/.exec(src.slice(start));
  const tag = tagM[1];
  const bodyStart = start + tagM.index + tagM[0].length;
  const bodyEnd = src.indexOf(tag, bodyStart);
  const body = src.slice(bodyStart, bodyEnd).replace(/\r/g, '');
  const h = createHash('md5').update(body).digest('hex');
  console.log(file, fname, i, 'len', body.length, 'md5', h);
  i++;
}
