// Mutazioni temporanee del pannello per la falsificazione (usa: node _mutate.cjs <nome>).
// Legge frontend/src/components/live/DutchingPanel.tsx e lo riscrive mutato; il chiamante
// ripristina dalla copia fedele.
const fs = require('fs');
const p = 'frontend/src/components/live/DutchingPanel.tsx';
let s = fs.readFileSync(p, 'utf8');
const LF = String.fromCharCode(10);
const CRLF = String.fromCharCode(13, 10);
const crlf = s.includes(CRLF);
const fix = (x) => (crlf ? x.split(LF).join(CRLF) : x);
const rep = (a, b) => {
    a = fix(a); b = fix(b);
    if (!s.includes(a)) throw new Error('pattern assente: ' + a.slice(0, 50));
    s = s.replace(a, b);
};
const m = process.argv[2];
if (m === 'A1_opzione') {
    rep('<option value="variable" disabled={side === \'lay\'}>', '<option value="variable">');
} else if (m === 'A1_avviso_e_bottone') {
    rep("{side === 'lay' && calcMode === 'variable' && (\n                    <div", "{false && (\n                    <div");
    rep("|| (side === 'lay' && calcMode === 'variable')\n", '\n');
} else if (m === 'M11_formula_vecchia') {
    rep("const variable = calcMode === 'variable' && validRaws.length > 0", "const variable = false && validRaws.length > 0");
} else if (m === 'pyRound2') {
    rep('return Number(x.toFixed(2));', 'return Math.round(x * 100) / 100;');
    rep('const e = a * 8;', 'const e = 0.5;');
} else if (m === 'tick') {
    rep('const n = Math.floor((2 * x + k) / (2 * k));\n    return (n * stepCents) / 100;', 'return Math.round(price * 100) / 100;');
} else if (m === 'V3') {
    rep('if (res.ok && !(Array.isArray(placedLegs) && placedLegs.length > 0)) {', 'if (false) {');
} else if (m === 'infeasible_invio') {
    rep('|| preview.infeasible != null\n', '\n');
    rep('if (preview.infeasible) return preview.infeasible;', '');
} else {
    throw new Error('mutazione sconosciuta');
}
fs.writeFileSync(p, s);
