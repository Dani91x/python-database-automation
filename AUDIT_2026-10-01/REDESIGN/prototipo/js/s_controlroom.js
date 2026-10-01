/* s_controlroom.js - CONTROL ROOM: stessi blocchi, stesso ordine, stessa gerarchia di
   pages/ControlRoom.tsx (inventario A_CONTROL_ROOM.md). Cambia solo la veste.
   Ordine: Testata -> ModeBanner -> [ObiettivoHero | SaldoBetfairCard] -> riga Storico ->
   (Discordanza) -> SplitSport -> PannelloBot -> (ProposteUsciteFlusso) -> (Errore comando) ->
   (Mike resting) -> (Errore fonti) -> BANCO [Tabs | Uscite | Opportunita'] -> Diagnostica -> footer. */
(function () {
  'use strict';
  var S = window.S, D = window.D, C = S.C;
  var M = S.money, mk = S.mk, chip = S.chip;
  var U = function () { return S.ui.cr || (S.ui.cr = { sport: null, scheda: 'live', armed: {}, freno: false, ordini: 'PAPER', uscite: {}, bot: {}, dett: {}, chiuse: { modo: 'live', esito: 'tutte', bot: 'tutti', fonte: 'tutte' }, cond: false }); };
  var hidden = function (v) { return S.hideMoney ? '••••,•• €' : v; };

  /* ---------- dati finti della giornata ---------- */
  var BOTS = [
    ['omega', 'Omega', 'hsl(var(--primary))', 'running', 'PAPER', '3 s'],
    ['safe', 'Safe', 'hsl(var(--secondary))', 'running', 'PAPER', '1 s'],
    ['mike', 'Mike', 'var(--teal)', 'running', 'LIVE', '1 s'],
    ['scalper', 'Scalper calcio', '#c4b5fd', 'stopped', 'PAPER', null],
    ['tennis_scalper', 'Scalper', '#fcd34d', 'running', 'PAPER', '6 s'],
    ['tennis_pro', 'Pro', '#fde68a', 'running', 'PAPER', '6 s'],
    ['tennis_flb', 'FLB', '#fdba74', 'stopped', 'PAPER', null],
    ['tennis_swing', 'Swing', '#fde047', 'stopped', 'PAPER', null]
  ];
  var RIGHE_CALCIO = [
    ['omega', 'Omega', 'running', 'prova', 6.4, 'stake minimo', '2,00', 'auto'],
    ['mike', 'Mike', 'running', 'soldi veri', 8.12, 'stake Under 3.5', '8,00', 'man'],
    ['scalper', 'Scalper calcio', 'stopped', 'prova', null, 'stake', '5,00', 'auto'],
    ['safe-base', 'Safe base', 'running', 'prova', 3.1, 'stake base', '4,00', 'man'],
    ['safe-esatto', 'Safe esatto', 'running', 'prova', -2.2, 'stake esatto', '2,00', 'man'],
    ['safe-punta', 'Safe punta', 'stopped', 'prova', null, 'stake punta', '3,00', 'man'],
    ['safe-model', 'Safe modello', 'running', 'prova', 0.9, null, null, null],
    ['safe-manual', 'Safe a mano', 'running', 'prova', null, null, null, null]
  ];
  var RIGHE_TENNIS = [
    ['safe-tennis', 'Safe tennis', 'running', 'prova', 1.4, 'stake tennis', '3,00', 'man'],
    ['tennis_scalper', 'Scalper tennis', 'running', 'prova', 2.05, 'stake', '5,00', 'auto'],
    ['tennis_pro', 'Pro tennis', 'running', 'prova', -0.8, 'stake', '5,00', 'auto'],
    ['tennis_flb', 'FLB tennis', 'stopped', 'prova', null, 'stake', '5,00', 'auto'],
    ['tennis_swing', 'Swing tennis', 'stopped', 'prova', null, 'stake', '5,00', 'auto']
  ];
  var PARTITE = [
    { id: '34812001', sport: 'calcio', stato: 'live', comp: 'Serie A', casa: 'Inter', osp: 'Torino', min: 58, score: '1-0', q: [[1.38, 1.39], [5.6, 5.7], [11.5, 12]], vol: 1843210, ou: [['U/O 3,5', 1.22, 1.23], ['U/O 4,5', 1.07, 1.08]], live: true, target: 12, pnl: 4.1, prova: 1.3, bots: { mike: 3, omega: 1 }, liab: 26.0, liabProva: 12.4 },
    { id: '34812044', sport: 'calcio', stato: 'live', comp: 'La Liga', casa: 'Real Betis', osp: 'Getafe', min: 31, score: '0-0', q: [[2.02, 2.04], [3.25, 3.3], [5.9, 6]], vol: 512330, ou: [['U/O 3,5', 1.36, 1.37], ['U/O 4,5', 1.12, 1.13]], live: false, target: 12, pnl: null, prova: 2.2, bots: { safe: 2 }, liab: 0, liabProva: 9.0, safeCash: true },
    { id: '34813501', sport: 'tennis', stato: 'live', comp: 'ATP Pechino', casa: 'J. Sinner', osp: 'J. Draper', score: '6-4 2-1', punti: '40 · 15', server: 'J. Sinner', q: [[1.24, 1.25], [5.0, 5.1]], live: false, target: 12, pnl: null, prova: 0.65, bots: { tennis_pro: 2, tennis_scalper: 1 }, liab: 0, liabProva: 5.0 },
    { id: '34812102', sport: 'calcio', stato: 'pre', comp: 'Serie A', casa: 'Bologna', osp: 'Udinese', ko: '10:52', fra: '14 min', q: [[1.83, 1.84], [3.7, 3.75], [4.9, 5]], ou: [['U/O 3,5', 1.29, 1.3], ['U/O 4,5', 1.1, 1.11]], mikePre: true },
    { id: '34812130', sport: 'calcio', stato: 'pre', comp: 'Premier League', casa: 'Brentford', osp: 'Fulham', ko: '11:22', fra: '44 min', q: [[2.3, 2.32], [3.45, 3.5], [3.3, 3.35]], ou: [['U/O 3,5', 1.41, 1.42], ['U/O 4,5', 1.16, 1.17]] },
    { id: '34812177', sport: 'calcio', stato: 'pre', comp: 'Ligue 1', casa: 'Lens', osp: 'Nantes', ko: '11:52', fra: '1 h 14', q: [[1.71, 1.72], [3.9, 3.95], [5.5, 5.6]], ou: [] },
    { id: '34813540', sport: 'tennis', stato: 'pre', comp: 'ATP Pechino', casa: 'L. Musetti', osp: 'T. Fritz', ko: '10:58', fra: '28 min', q: [[2.36, 2.4], [1.7, 1.72]], ou: [] }
  ];

  /* ---------- conferma a due tempi nello stesso punto (400 ms anti doppio clic) ---------- */
  function arm(key, label, armedLabel, cls, armedCls, tid) {
    var u = U(), a = u.armed[key];
    if (a) return '<button class="btn sm ' + (armedCls || 'danger') + '" style="font-weight:800" data-act="cr-ok" data-k="' + key + '" data-testid="' + (tid ? tid + '-conferma' : '') + '">' + armedLabel + '</button><button class="btn sm ghost" data-act="cr-disarm" data-k="' + key + '">annulla</button>';
    return '<button class="btn sm ' + (cls || '') + '" data-act="cr-arm" data-k="' + key + '" data-testid="' + (tid || '') + '">' + label + '</button>';
  }
  S.on('cr-arm', function (t) { U().armed[t.dataset.k] = Date.now(); S.rerender(); });
  S.on('cr-disarm', function (t) { delete U().armed[t.dataset.k]; S.rerender(); });
  S.on('cr-ok', function (t) {
    var u = U(), k = t.dataset.k; if (Date.now() - (u.armed[k] || 0) < 400) return; delete u.armed[k];
    if (k === 'ordini-live') u.ordini = 'LIVE';
    if (k === 'freno-rilascia') { u.armed['freno-2'] = Date.now(); S.rerender(); return; }
    if (k === 'freno-2') u.freno = false;
    if (/^uscite-/.test(k)) u.uscite[k.slice(7)] = 'auto';
    if (/^avvia-live-|^a-live-/.test(k)) { var id = k.replace(/^avvia-live-|^a-live-/, ''); u.bot[id] = { stato: 'running', modo: 'soldi veri' }; }
    S.rerender(); S.toast('Comando inviato — in attesa del servizio', 'Prototipo: nessun ordine reale, nessun comando inviato.');
  });

  /* ======================= 1.1 TESTATA ======================= */
  function testata() {
    var anyLive = BOTS.some(function (b) { return b[4] === 'LIVE'; });
    var h = '<header class="panel flat" data-testid="cr-testata" style="padding:10px 14px;display:flex;flex-direction:column;gap:10px;' + (anyLive ? 'border-color:rgba(249,115,22,.45);background:linear-gradient(180deg,rgba(124,45,18,.22),hsl(var(--card)))' : '') + '">';
    // riga A: identita' + soldi veri + stop
    h += '<div class="row" style="gap:18px;align-items:flex-start">' +
      '<div class="col" style="gap:0"><a class="lbl" data-go="dashboard" href="#dashboard" style="text-decoration:none">AI Terminal</a><b style="font:800 16px var(--f-display);letter-spacing:.02em">CONTROL ROOM</b><span class="foot">1 ottobre 2026</span></div>';
    // FasciaSoldiVeri
    var blk = function (tid, k, v, sub, tone) { return '<div class="col" style="gap:1px;min-width:0" data-testid="' + tid + '"><span class="lbl" style="font-size:9.5px">' + k + '</span><b class="mono ' + (tone || '') + '" style="font-size:14px">' + v + '</b><span class="foot" style="font-size:10px">' + sub + '</span></div>'; };
    h += '<div class="row" data-testid="cr-soldi-veri" style="gap:16px;padding:6px 12px;border-radius:10px;background:hsl(var(--muted)/.6);border:1px solid hsl(var(--border));align-items:flex-start">' +
      blk('cr-esposizione-conto', 'Esposizione conto', hidden(M(D.conto.esposizione)), mk('CONTO') + ' 3 s fa', 'ora') +
      blk('cr-disponibile-conto', 'Disponibile', hidden(M(D.conto.disponibile)), mk('CONTO'), '') +
      blk('cr-rischio-bot', 'Rischio secondo i bot', M(-96.40), mk('BOT') + ' solo LIVE, per partita', '') +
      blk('cr-partite-posizione', 'Posizione LIVE', '1 partita con posizione LIVE (3 gambe)', 'in prova 3 · programma scanner 41', '') + '</div>';
    // StopPerdita
    h += '<div class="col" data-testid="cr-freni" style="gap:2px;font-size:11.5px"><span class="lbl" style="font-size:9.5px">Stop perdita</span>' +
      '<div class="row" data-testid="cr-stop-conto" style="gap:6px">Conto: <b class="mono">−50,00 €</b><span class="mut">oggi</span><b class="mono pos">+23,85 €</b><a data-go="segui-live" href="#segui-live" aria-label="modifica lo stop del conto" title="modifica lo stop del conto">✎</a></div>' +
      '<div class="row" style="gap:10px">' + [['Safe', 'PAPER', '−20,00 €'], ['Mike', 'LIVE', '−30,00 €'], ['Omega', 'PAPER', 'spento']].map(function (x) { return '<span data-testid="cr-stop-' + x[0].toLowerCase() + '">' + x[0] + ' ' + chip(x[1], x[1] === 'LIVE' ? 'live' : '') + ' <b class="mono">' + x[2] + '</b> <a style="cursor:pointer" title="vai alla riga parametri del bot">✎</a></span>'; }).join('') + '</div>' +
      '<span class="foot" data-testid="cr-stop-altri">Tennis, Scalper: stop proprio non pubblicato</span></div>';
    h += '<button class="iconbtn" style="margin-left:auto" data-act="toast" data-t="Ricarica" data-d="Rilettura completa (ogni 30 s comunque)." data-testid="cr-ricarica" title="ricarica">↻</button></div>';
    // riga B: runner + chip bot + feed
    h += '<div class="cr-tb" style="padding-top:8px;border-top:1px solid hsl(var(--border))">' +
       '<div class="col" style="gap:8px">' + ['calcio', 'tennis'].map(function (s) { return '<div class="col" style="gap:0" data-testid="cr-runner' + (s === 'tennis' ? '-tennis' : '') + '" title="ultimo battito 1 s fa"><span class="lbl" style="font-size:9.5px">' + (s === 'calcio' ? 'Runner' : 'Runner tennis') + '</span><b class="mono pos" style="font-size:12.5px">in streaming <span class="mut" style="font-weight:500" data-testid="cr-runner-tetto">· ' + (s === 'calcio' ? 'ordini veri consentiti' : 'solo simulati') + '</span></b><span class="foot mono" style="font-size:9.5px">canale 1 s</span></div>'; }).join('') + '</div>' +
      '<div data-testid="cr-bots" style="display:grid;gap:6px;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));min-width:0">' + BOTS.map(function (b) {
        var run = b[3] === 'running';
        return '<div data-testid="cr-bot-' + b[0] + '" title="' + b[1] + ': ' + (b[4] === 'LIVE' ? 'LIVE' : 'paper') + '" style="padding:4px 8px;border-radius:8px;border:1px solid ' + (b[4] === 'LIVE' ? 'rgba(239,68,68,.45)' : 'hsl(var(--border))') + ';background:hsl(var(--card));min-width:0">' +
          '<div class="row" style="gap:5px;flex-wrap:nowrap"><span class="led ' + (run ? 'on' : 'off') + '"></span><b style="font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:' + b[2] + '">' + b[1] + '</b></div>' +
          '<div class="foot" style="font-size:9.5px">' + (run ? '' : 'FERMO · ') + '<span style="' + (b[4] === 'LIVE' ? 'color:#fca5a5;font-weight:700' : '') + '">' + b[4] + '</span> · ' + (run ? '<span class="pos">aggiornato ' + b[5] + ' fa</span>' : 'fermo: non invia aggiornamenti') + '</div></div>';
      }).join('') + '</div>' +
      '<div class="col" data-testid="cr-feed" style="gap:2px;font-size:11px"><span class="row" style="gap:5px"><span class="led on"></span><span class="mut">Quote dello scanner</span><b class="pos" data-testid="cr-feed-sorgente">stream</b><span class="pos mono">1 s</span></span><span class="pos" data-testid="cr-dati-riassunto">Dati: tempo reale</span>' +
      '<details data-testid="cr-dati-dettaglio"><summary class="foot" style="cursor:pointer">dettaglio</summary><div class="foot mono" style="font-size:10px">· canale locale · stato canale · righe Omega canale 3 s · Safe canale 1 s · Mike canale 1 s · Tennis canale 6 s</div></details></div></div>';
    return h + '</header>';
  }

  /* ======================= 1.2 MODE BANNER ======================= */
  function banner() {
    return '<div class="strip live" role="alert" data-testid="cr-banner-modalita" data-mode="live">' + S.icon('shield') + '<span><b>MODALITÀ LIVE</b> — Ordini REALI su Betfair per: <b>Mike: LIVE</b>. Tutto il resto opera in prova.</span></div>';
  }

  /* ======================= 1.3 ZONA 1 ======================= */
  function obiettivo() {
    var u = U(), goal = u.goal || 12, real = 8.12;
    var edit = u.goalEdit;
    var h = '<section class="panel" data-testid="cr-obiettivo" style="padding:14px 16px;display:flex;flex-direction:column;gap:12px">';
    h += '<div class="row">' + S.icon('target') + '<h3 style="font-size:14px">Obiettivo di oggi</h3><span data-testid="cr-obiettivo-editor">' + (edit
      ? '<span class="row" style="gap:6px"><span class="foot">obiettivo</span><input class="inp" id="cr-goal" style="width:90px;height:26px" value="' + goal + '" aria-label="Nuovo obiettivo di oggi, in euro"><button class="btn sm pri" data-act="cr-goal-ok" title="conferma">✓</button><button class="btn sm" data-act="cr-goal-x" title="annulla">✕</button></span><div class="amb" style="font-size:11px;margin-top:4px">Omega è IN CORSA: il nuovo obiettivo cambia da subito il target per partita che il servizio calcola (letto a ogni ciclo).</div><div class="foot">oggi in vigore: ' + M(goal) + '</div>'
      : '<button class="btn sm ghost" data-act="cr-goal-edit" title="modifica l’obiettivo di oggi">✎</button>') + '</span></div>';
    // DayBar della Control Room
    var pct = Math.min(100, real / goal * 100), aperto = 3.4;
    h += '<div data-testid="cr-giornata" class="panel flat" style="padding:12px 14px"><div class="row" style="justify-content:space-between;align-items:flex-start"><div><b style="font-size:13px">Giornata operativa</b><div class="foot" data-testid="cr-giornata-giorno">giornata operativa <b>1 ottobre 2026</b> (Europe/Rome) — programma dello scanner: 41 partite</div></div>' +
      '<div style="text-align:right"><div class="pos" style="font:800 26px var(--f-display)" data-testid="day-bar-realizzato">' + M(real, { signed: true }) + '<span class="mut" style="font-size:14px"> · ' + Math.round(pct) + ' %</span></div><div class="foot" data-testid="cr-giornata-realizzato-fonte">' + mk('CONTO') + ' 3 s fa · netto di commissione, tutto il conto</div></div></div>' +
      '<div class="row" data-testid="cr-giornata-riga" style="gap:4px 14px;font-size:12px;margin:8px 0">' +
      '<span title="obiettivo di P&L realizzato per la giornata di oggi">Obiettivo di oggi <b class="gold">' + M(goal) + '</b></span>' +
      '<span data-testid="day-bar-counts" class="mut">operazioni regolate oggi <b style="color:hsl(var(--foreground))">4</b> · <b class="pos">3V</b> <b class="neg">1P</b> · <b style="color:var(--back)">1</b> partita con posizione LIVE</span>' +
      '<span>realizzato oggi <b class="pos">' + M(real, { signed: true }) + '</b></span>' +
      '<span data-testid="cr-giornata-aperto">aperto adesso (se chiudo tutto) <b class="pos" data-testid="cr-giornata-aperto-valore">' + M(aperto, { signed: true }) + '</b> ' + mk('STIMA') + ' <span class="foot">su 1 partita</span></span>' +
      '<span data-testid="cr-giornata-rischio">rischio massimo <b class="ora" data-testid="cr-giornata-rischio-valore">' + hidden(M(D.conto.esposizione)) + '</b> ' + mk('CONTO') + '</span>' +
      '<span class="amb" data-testid="day-bar-remaining">resta <b>' + M(goal - real) + '</b></span></div>' +
      '<div role="progressbar" aria-label="Avanzamento obiettivo di oggi" style="position:relative;height:8px;border-radius:99px;background:hsl(var(--muted));overflow:hidden"><i style="position:absolute;left:0;top:0;bottom:0;width:' + pct + '%;background:linear-gradient(90deg,hsl(var(--primary)),hsl(var(--secondary)))"></i><i data-testid="day-bar-aperto-barra" style="position:absolute;top:0;bottom:0;left:' + pct + '%;width:' + Math.min(100 - pct, aperto / goal * 100) + '%;border:1px dashed hsl(var(--secondary));border-left:0"></i></div></div>';
    // Composizione
    var comp = [['omega', 'Omega', null, 'BOT', '—'], ['safe_calcio', 'Safe calcio', null, 'BOT'], ['safe_tennis', 'Safe tennis', null, 'BOT'], ['mike', 'Mike', 8.12, 'CONTO'], ['scalper', 'Scalper calcio', null, 'BOT'], ['bot_tennis', 'Bot tennis (Scalper · Pro · FLB · Swing)', null, 'BOT'], ['manuale', 'Manuale (app + sito Betfair)', 0, 'CONTO'], ['manuale_sito', 'Manuale · sito Betfair', 0, 'CONTO'], ['manuale_app', 'Manuale · app', 0, 'CONTO'], ['altro', 'Altro sul conto Betfair', 0, 'CONTO']];
    h += '<div data-testid="cr-composizione"><div class="row" style="justify-content:space-between"><span class="lbl">composizione — solo soldi veri, entra nell’obiettivo</span><span class="foot" data-testid="cr-composizione-fonte">· realizzato di ogni bot dal conto Betfair (attribuito da Betfair), la parte non ancora regolata stimata dal bot</span></div>' +
      '<div class="grid g2" style="gap:2px 22px;margin-top:6px">' + comp.map(function (c) { return '<div class="row" data-testid="cr-composizione-' + c[0] + '" style="justify-content:space-between;font-size:12px;flex-wrap:nowrap;padding:3px 0;border-bottom:1px solid hsl(var(--border)/.5)"><span class="mut" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' + c[1] + '</span><span class="row" style="gap:5px;flex-wrap:nowrap"><b class="mono ' + S.tone(c[2]) + '">' + (c[2] == null ? '—' : M(c[2], { signed: true })) + '</b>' + (c[0] === 'mike' ? '<span class="foot">· aperto +3,40 €</span>' : '') + mk(c[3]) + '</span></div>'; }).join('') + '</div></div>';
    // Corsia PROVA
    var prova = [['omega', 'Omega', 6.4, 'nessuno'], ['mike', 'Mike', null, 'nessuno'], ['safe_calcio', 'Safe calcio', 1.8, '+1,20 € (2 partite del 30/09)'], ['safe_tennis', 'Safe tennis', 1.4, 'per giorno come lo pubblica il servizio: non separabili'], ['bot_tennis', 'Bot tennis (Scalper · Pro · FLB · Swing)', 1.25, 'nessuno']];
    h += '<div data-testid="cr-composizione-prova" style="border:1px dashed hsl(var(--glass-border));border-radius:10px;padding:10px 12px;opacity:.9"><div class="row">' + chip('in prova (simulato)', 'paper') + '<span class="foot">— mai sommato all’obiettivo; gli arretrati mai sommati a oggi</span></div>' +
      '<div class="tbl-w"><table class="t" style="margin-top:6px"><thead><tr><th>bot</th><th class="r">partite di oggi</th><th>arretrati regolati oggi</th></tr></thead><tbody>' + prova.map(function (p) {
        return '<tr data-testid="cr-prova-' + p[0] + '"><td>' + p[1] + '</td><td class="r" data-testid="cr-prova-' + p[0] + '-oggi">' + (p[0] === 'mike' ? '<span style="color:#fca5a5;opacity:.8">— (ora in LIVE)</span>' : '<span class="' + S.tone(p[2]) + '" style="opacity:.8">' + M(p[2], { signed: true }) + '</span> ' + mk('PROVA')) + '</td><td class="foot" style="white-space:normal" data-testid="cr-prova-' + p[0] + '-arretrati">' + p[3] + '</td></tr>';
      }).join('') + '</tbody></table></div></div>';
    return h + '</section>';
  }
  S.on('cr-goal-edit', function () { U().goalEdit = true; S.rerender(); });
  S.on('cr-goal-x', function () { U().goalEdit = false; S.rerender(); });
  S.on('cr-goal-ok', function () { var v = parseFloat((document.getElementById('cr-goal').value || '').replace(',', '.')); if (!(v > 0)) { S.toast('Obiettivo non valido', 'Scrivi un importo in euro maggiore di zero.'); return; } U().goal = v; U().goalEdit = false; S.rerender(); S.toast('Obiettivo salvato', 'Prototipo: nessuna RPC chiamata.'); });

  function saldo() {
    return '<section class="panel" data-testid="cr-saldo" style="padding:16px"><div class="row" style="justify-content:space-between"><span class="lbl">Saldo conto Betfair</span><button class="btn sm ghost" data-act="hide-money" data-testid="cr-saldo-occhio" aria-pressed="' + S.hideMoney + '" title="' + (S.hideMoney ? 'mostra il saldo' : 'nascondi il saldo') + '">' + S.icon(S.hideMoney ? 'eyeoff' : 'eye') + '</button></div>' +
      '<div style="font:800 30px var(--f-display);margin:6px 0" data-testid="cr-saldo-valore" class="num">' + hidden(M(D.conto.disponibile)) + '</div>' +
      '<div class="row" style="justify-content:space-between;font-size:12.5px"><span class="mut">Esposizione</span><b class="ora mono" data-testid="cr-saldo-esposizione">' + hidden(M(D.conto.esposizione)) + '</b></div>' +
      '<div class="row foot" data-testid="cr-saldo-nota" style="margin-top:10px"><span class="led on"></span>controllato: 3 s fa ' + mk('CONTO') + '</div></section>';
  }

  /* ======================= 1.6 SPLIT SPORT ======================= */
  function split() {
    var u = U();
    var tile = function (s) {
      var sel = u.sport === s, other = u.sport && !sel, live = s === 'calcio';
      return '<section class="panel" data-testid="cr-sport-' + s + '" data-act="cr-sport" data-v="' + s + '" style="cursor:pointer;padding:12px 14px;display:flex;flex-direction:column;gap:8px;' + (live ? 'border-color:rgba(239,68,68,.5);' : '') + (sel ? 'box-shadow:0 0 0 2px hsl(var(--foreground)/.75);' : '') + (other ? 'opacity:.45;' : '') + '">' +
        '<div class="row"><b style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:' + (s === 'calcio' ? 'var(--back)' : 'hsl(var(--secondary))') + '">' + (s === 'calcio' ? '⚽ Calcio' : '🎾 Tennis') + '</b>' + (live ? chip('soldi veri', 'live') : '') + '<button class="btn sm ghost" style="margin-left:auto" data-testid="cr-filtro-' + s + '" aria-pressed="' + sel + '" title="' + (sel ? 'mostra di nuovo tutti gli sport' : 'mostra solo ' + s) + '">' + S.icon('filter') + '</button></div>' +
        '<div data-testid="cr-sport-' + s + '-live" style="padding:8px 10px;border-radius:9px;background:rgba(239,68,68,.07);border:1px solid rgba(239,68,68,.35)"><div class="row" style="font-size:11.5px">' + chip('LIVE', 'live') + '<span data-testid="cr-sport-' + s + '-live-bot">' + (live ? 'Mike' : 'nessun bot in live') + '</span>' + (live ? '<span class="neg" style="margin-left:auto;color:#fca5a5">1 partita con posizione LIVE</span>' : '') + '</div>' +
        '<div class="row" style="margin-top:4px"><b class="' + (live ? 'pos' : 'mut') + '" style="font:800 20px var(--f-display)" data-testid="cr-sport-' + s + '-live-pnl">' + (live ? M(8.12, { signed: true }) : '—') + '</b>' + (live ? mk('CONTO') + '<span class="foot" data-testid="cr-sport-' + s + '-live-conto">1 ordine regolato oggi</span>' : '<span class="foot">nessuna operazione con soldi veri oggi</span>') + '</div></div>' +
        '<div data-testid="cr-sport-' + s + '-prova" style="padding:8px 10px;border-radius:9px;border:1px dashed hsl(var(--glass-border));opacity:.75"><div class="row" style="font-size:11.5px">' + chip('PROVA') + '<span data-testid="cr-sport-' + s + '-prova-bot">' + (live ? 'Omega · Safe base · Safe esatto · Safe modello' : 'Safe tennis · Scalper · Pro') + '</span><span style="margin-left:auto" class="foot">' + (live ? '2 partite' : '1 partita') + ' con posizione in prova</span></div>' +
        '<div class="row" style="margin-top:4px"><span class="foot">partite di oggi</span><b class="pos" style="font:700 16px var(--f-display)" data-testid="cr-sport-' + s + '-prova-pnl">' + M(live ? 10.1 : 2.65, { signed: true }) + '</b>' + mk('PROVA') + '<span class="foot">' + (live ? '9 operazioni · 6 V · 3 P · 67 %' : '4 operazioni · 3 V · 1 P · 75 %') + '</span></div>' +
        '<div class="foot" data-testid="cr-sport-' + s + '-arretrati">' + (live ? 'arretrati regolati oggi <b class="pos">+1,20 €</b> ' + mk('PROVA') + ' (2 partite del 30/09) — fuori dalle cifre di oggi' : 'Safe tennis, bot tennis: per giorno come lo pubblica il servizio (regolamento, o partita se la migrazione del 30/09 è applicata)') + '</div></div>' +
        '<span class="foot">' + (sel ? 'stai vedendo solo questo — clicca per tutti' : 'clicca per vedere solo questo sport') + '</span></section>';
    };
    return '<div class="grid g2" data-testid="cr-split-sport">' + tile('calcio') + tile('tennis') + '</div>';
  }
  S.on('cr-sport', function (t) { var u = U(); u.sport = u.sport === t.dataset.v ? null : t.dataset.v; S.rerender(); });

  /* ======================= 1.7 PANNELLO BOT ======================= */
  function rigaBot(r) {
    var u = U(), id = r[0], ov = u.bot[id] || {};
    var stato = ov.stato || r[2], modo = ov.modo || r[3], run = stato === 'running';
    var usc = u.uscite[id] || r[7];
    var h = '<div data-testid="cr-bot-riga-' + id + '" style="padding:9px 0;border-bottom:1px solid hsl(var(--border)/.6);display:flex;flex-direction:column;gap:6px">';
    h += '<div class="row" style="gap:8px"><b style="width:7.5rem;font-size:11.5px;letter-spacing:.06em;text-transform:uppercase">' + r[1] + '</b>' +
      '<span data-testid="cr-bot-stato-' + id + '">' + chip(run ? 'IN CORSA' : 'FERMO', run ? 'paper' : '') + '</span>' +
      '<span data-testid="cr-bot-modalita-' + id + '">' + chip(modo, modo === 'soldi veri' ? 'live' : '') + '</span>' +
      '<span class="mono foot" title="da quanto è arrivato l’ultimo messaggio dal canale di questo bot">' + (run ? '2 s' : '—') + '</span>' +
      (id === 'scalper' ? '<span class="foot" data-testid="cr-bot-nota-scalper">0 sessioni attive</span>' : '') +
      '<span data-testid="cr-bot-pnl-' + id + '" style="font-size:12px">oggi <b class="mono ' + S.tone(r[4]) + '">' + (r[4] == null ? '—' : M(r[4], { signed: true })) + '</b> ' + (r[4] != null ? mk(modo === 'soldi veri' ? 'CONTO' : 'PROVA') : '') + '</span>' +
      '<span style="margin-left:auto" data-testid="cr-parametri-' + id + '">' + (id === 'safe-model' || id === 'safe-manual' ? '' : '<button class="btn sm" data-act="params" data-bot="' + id + '" data-testid="' + (id === 'mike' ? 'mike-params-trigger' : 'cr-' + id + '-params-trigger') + '">' + S.icon('gear') + ' Parametri</button>') + '</span></div>';
    // uscite
    if (usc) h += '<div class="row" data-testid="cr-uscite-' + id + '" style="font-size:11.5px;padding-left:7.5rem"><span class="mut">uscite:</span><b data-testid="cr-uscite-stato-' + id + '" class="' + (usc === 'man' ? 'amb' : 'pos') + '">' + (usc === 'man' ? 'MANUALI, approvi tu' + (id === 'mike' ? ' · 1 posizione aperta da 12 min' : '') : 'AUTOMATICHE') + '</b>' + (id === 'mike' ? '<span class="foot">(governa solo le uscite in perdita; le uscite in profitto le esegue Mike)</span>' : '') +
      (usc === 'man' ? arm('uscite-' + id, 'passa ad automatiche', 'confermi? passa ad automatiche', '', 'gold', 'cr-uscite-cambia-' + id) : '<button class="btn sm" data-act="cr-uscite-man" data-v="' + id + '" data-testid="cr-uscite-cambia-' + id + '">passa a manuali</button>') + '</div>';
    // importo
    if (r[5]) h += '<div class="row" style="font-size:11.5px;padding-left:7.5rem"><span class="mut">' + r[5] + '</span><input class="inp" id="cr-importo-' + id + '" data-testid="cr-importo-' + id + '-stake" style="width:80px;height:24px" placeholder="' + r[6] + '" inputmode="decimal">' + (id === 'omega' ? '<span class="foot">e’ un minimo, non l’importo di lavoro: Omega dimensiona dall’obiettivo</span>' : '') + (id === 'scalper' ? '<span class="foot">vale per le partite armate da ora: quelle gia’ armate tengono il loro</span>' : '') + '</div>';
    // comandi
    h += '<div class="row" style="padding-left:7.5rem;gap:6px">';
    if (run) {
      h += '<button class="btn sm danger" data-act="cr-ferma" data-v="' + id + '" data-testid="cr-ferma-' + id + '" title="ferma le APERTURE. Le posizioni già aperte restano sorvegliate: coperture, green-up, cash out e regolamento continuano">' + S.icon('stop') + ' ferma</button><span class="foot" data-testid="cr-cosa-ferma-' + id + '">ferma le aperture, non le uscite</span>';
      if (modo === 'soldi veri') h += '<button class="btn sm ghost" data-act="cr-a-paper" data-v="' + id + '" data-testid="cr-a-paper-' + id + '" title="torna a operare in prova: nessun ordine reale">passa a prova</button>';
      else h += arm('a-live-' + id, 'passa a soldi veri', 'confermi? sono soldi veri', 'ghost" style="color:#fca5a5', 'danger', 'cr-a-live-' + id);
    } else {
      if (id === 'scalper') h += '<span class="foot" data-testid="cr-modalita-all-avvio-scalper">prova o soldi veri si scelgono all’avvio: per cambiare, ferma e riavvia</span>';
      h += '<button class="btn sm" data-act="cr-avvia-paper" data-v="' + id + '" data-testid="cr-avvia-paper-' + id + '">' + S.icon('plug') + ' avvia in prova</button>' + arm('avvia-live-' + id, '⚠ avvia con soldi veri', 'confermi? ordini reali su Betfair', 'danger', 'danger', 'cr-avvia-live-' + id);
    }
    if (u.armed['a-live-' + id] || u.armed['avvia-live-' + id]) h += '<span class="neg" style="font-size:11.5px;color:#fca5a5" data-testid="cr-avviso-live-' + id + '">Da qui in poi ' + r[1] + ' manda ordini reali su Betfair.</span>';
    return h + '</div></div>';
  }
  S.on('cr-ferma', function (t) { U().bot[t.dataset.v] = Object.assign({}, U().bot[t.dataset.v], { stato: 'stopped' }); S.rerender(); S.toast('Comando inviato — in attesa del servizio (tipica ~2 s)', 'Fermare spegne le aperture: le posizioni restano sorvegliate.'); });
  S.on('cr-avvia-paper', function (t) { U().bot[t.dataset.v] = { stato: 'running', modo: 'prova' }; S.rerender(); S.toast('Avviato in prova', 'Prototipo: nessun comando inviato.'); });
  S.on('cr-a-paper', function (t) { U().bot[t.dataset.v] = { stato: 'running', modo: 'prova' }; S.rerender(); });
  S.on('cr-uscite-man', function (t) { U().uscite[t.dataset.v] = 'man'; S.rerender(); });

  function pannello() {
    var u = U(), sport = u.sport;
    var h = '<section class="panel" data-testid="cr-pannello-bot"><div class="panel-h"><h3 data-testid="cr-pannello-bot-titolo">' + (sport === 'tennis' ? 'Bot del tennis' : 'Comando dei bot') + '</h3><div class="r"><span class="chip live" data-testid="cr-quanti-live">1 con soldi veri</span><button class="btn sm danger" data-act="cr-ferma-tutti" data-testid="cr-ferma-tutti" title="ferma le aperture di tutti i bot. Non chiude nessuna posizione.">' + S.icon('stop') + ' Ferma tutti</button></div></div><div class="panel-b stack">';
    if (sport === 'tennis') h += '<div class="strip info" data-testid="cr-pannello-bot-nota" style="font-size:11.5px;flex-direction:column;align-items:flex-start;gap:4px"><span><b>Avviando da qui</b> si AGGIUNGE la strategia tennis a <b>3,00 €</b> con entrate automatiche, senza toccare le strategie di calcio già accese; opportunità di modello e ordini manuali <b>vengono messi in prova</b>. Mike e Omega non si toccano. Lo stake torna a 3,00 € a ogni avvio da qui.</span><span class="foot">«Ferma» invece spegne le aperture di <b>tutto Safe</b>, calcio compreso: il servizio è uno solo.</span></div>';
    // Ordini reali / Freno / Mercati
    var lab = function (t) { return '<b style="width:6rem;font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;flex:none">' + t + '</b>'; };
    var om = u.ordini;
    h += '<div class="col" style="gap:8px;padding:10px 12px;border-radius:10px;background:hsl(var(--muted)/.5);border:1px solid hsl(var(--border))">' +
      '<div class="row" data-testid="cr-ordini-reali">' + lab('Ordini reali') + chip(om === 'LIVE' ? 'LIVE - soldi veri' : om === 'OFF' ? 'OFF - nessun ordine' : 'PAPER - prova', om === 'LIVE' ? 'live' : '') + '<span class="foot mono" data-testid="cr-ordini-reali-fonte">canale 1 s</span><span class="foot" data-testid="cr-ordini-reali-tetto">tetto dell’ambiente: LIVE</span><span class="foot" data-testid="cr-ordini-reali-chi">scelto ' + om + ' da utente il 1/10 08:02</span>' +
      '<span class="row" style="margin-left:auto;gap:4px"><button class="btn sm" data-act="cr-ordini" data-v="OFF" data-testid="cr-ordini-reali-off" title="nessun ordine dal ladder, nessun ordine reale dai bot. Le chiusure restano servite.">off</button><button class="btn sm" data-act="cr-ordini" data-v="PAPER" data-testid="cr-ordini-reali-paper" title="ordini simulati: nessun ordine reale">paper</button>' + arm('ordini-live', '⚠ live', 'confermi? ordini reali su Betfair', 'danger', 'danger', 'cr-ordini-reali-live') + '</span>' +
      (u.armed['ordini-live'] ? '<span class="foot neg" style="width:100%;color:#fca5a5" data-testid="cr-ordini-reali-avviso-live">Da qui in poi il ladder e i bot in live mandano ordini reali su Betfair.</span>' : '') + '</div>' +
      '<div class="row" data-testid="cr-freno" style="' + (u.freno ? 'background:rgba(239,68,68,.12);border-radius:8px;padding:4px 6px' : '') + '">' + lab('Freno') + '<b data-testid="cr-freno-stato" class="' + (u.freno ? 'neg' : '') + '">' + (u.freno ? 'TIRATO - nessuna apertura' : 'rilasciato') + '</b><span class="foot mono" data-testid="cr-freno-fonte">canale 1 s</span><span class="row" style="margin-left:auto;gap:4px">' +
      (u.freno ? (u.armed['freno-2'] ? '<button class="btn sm gold" style="font-weight:800" data-act="cr-ok" data-k="freno-2" data-testid="cr-freno-conferma-2">sì, rilascia il freno</button><button class="btn sm ghost" data-act="cr-disarm" data-k="freno-2" data-testid="cr-freno-annulla">annulla</button>' : arm('freno-rilascia', 'rilascia', 'confermi? i bot accesi tornano ad aprire', '', 'gold', 'cr-freno-rilascia'))
        : '<button class="btn sm danger" style="background:rgba(239,68,68,.85);color:#fff" data-act="cr-freno-tira" data-testid="cr-freno-tira" title="ferma OGNI apertura di tutti i bot, live e paper. Le chiusure restano servite.">⛔ tira il freno</button>') + '</span></div>' +
      '<div class="row" data-testid="cr-capacita">' + lab('Mercati') + '<span class="mono" style="font-size:11.5px" data-testid="cr-capacita-numeri" title="mercati seguiti / capacità">38 partite su 41 del feed · 152/200 mercati · 2/2 connessioni</span>' + chip('nessuna partita fuori', 'paper') + '</div></div>';
    // gruppi
    var grp = function (key, title, rows) {
      var open = u['grp_' + key] !== false;
      var liveOn = rows.some(function (r) { return (u.bot[r[0]] || {}).modo === 'soldi veri' || r[3] === 'soldi veri'; });
      return '<div data-testid="cr-pannello-bot-gruppo-' + key + '" style="border:1px solid hsl(var(--border));border-radius:10px"><button class="row" data-act="cr-grp" data-v="' + key + '" data-testid="cr-pannello-bot-gruppo-' + key + '-trigger" style="width:100%;border:0;background:none;padding:10px 12px;cursor:pointer;justify-content:flex-start">' +
        '<span>' + (open ? '▾' : '▸') + '</span><b style="font-size:12px;letter-spacing:.08em">' + title + ' (' + rows.length + ')</b><span class="row" style="gap:3px">' + rows.map(function (r) { var st = (u.bot[r[0]] || {}).stato || r[2]; return '<span class="led ' + (st === 'running' ? 'on' : 'off') + '" title="' + r[1] + ': ' + (st === 'running' ? 'in corsa' : 'fermo') + '"></span>'; }).join('') + '</span>' +
        (liveOn ? chip('soldi veri', 'live') : chip('prova')) + (key === 'calcio' ? '<span class="foot" data-testid="cr-pannello-bot-gruppo-calcio-oggi-live">oggi LIVE <b class="pos">+8,12 €</b></span>' : '') + '<span class="foot" style="opacity:.7">prova <b>' + (key === 'calcio' ? '+8,20 €' : '+2,65 €') + '</b></span></button>' +
        (open ? '<div style="padding:0 12px 4px">' + rows.map(rigaBot).join('') + '</div>' : '') + '</div>';
    };
    if (sport !== 'tennis') h += grp('calcio', 'BOT CALCIO', RIGHE_CALCIO);
    if (sport !== 'calcio') h += grp('tennis', 'BOT TENNIS', RIGHE_TENNIS);
    h += '<p class="foot" style="margin:0">Fermare spegne le <b>aperture</b>: le posizioni già a mercato restano sorvegliate e le puoi chiudere da qui.</p></div></section>';
    return h;
  }
  S.on('cr-grp', function (t) { var u = U(), k = 'grp_' + t.dataset.v; u[k] = u[k] === false; S.rerender(); });
  S.on('cr-ordini', function (t) { U().ordini = t.dataset.v; S.rerender(); });
  S.on('cr-freno-tira', function () { U().freno = true; S.rerender(); S.toast('Freno tirato', 'Nessuna apertura da nessun bot. Le chiusure restano servite.'); });
  S.on('cr-ferma-tutti', function () { var u = U(); RIGHE_CALCIO.concat(RIGHE_TENNIS).forEach(function (r) { u.bot[r[0]] = Object.assign({}, u.bot[r[0]], { stato: 'stopped' }); }); S.rerender(); S.toast('Ferma tutti inviato', 'Freno d’emergenza: nessuna conferma. Non chiude nessuna posizione.'); });

  /* ======================= 1.8 - 1.11 CONDIZIONALI ======================= */
  function condizionali() {
    var u = U();
    var h = '<div class="strip info"><span class="lbl">Prototipo</span><span>mostra i blocchi condizionali (discordanza, uscite flusso, errore comando, Mike resting, errore fonti):</span>' + S.sw(u.cond, 'cr-cond') + '</div>';
    if (!u.cond) return h;
    h += '<div class="strip warn" data-testid="cr-proposte-flusso" style="flex-direction:column;align-items:stretch"><b class="amb">Uscite da approvare (1)</b><div data-testid="cr-proposte-flusso-riga" style="border-left:3px solid #f87171;padding-left:10px"><div data-testid="cr-proposte-flusso-titolo">Pro tennis vorrebbe uscire: <b>stop in perdita</b> · partita 34813501 · deciso 4 s fa</div><div class="mono foot" data-testid="cr-proposte-flusso-ordine">chiude BACK 5,00 € @ 1,26 (100% della posizione)</div><div class="foot" data-testid="cr-proposte-flusso-numeri">se chiudi ora −0,40 € · se tieni: vince +1,20 € / perde −5,00 €</div><div class="row" style="margin-top:4px"><button class="btn sm gold" data-act="toast" data-t="firma inviata: parte al prossimo giro del bot se la condizione vale ancora" data-testid="cr-proposte-flusso-approva">approva uscita</button><span class="foot">oppure chiudi a mano con "Chiudi"</span></div></div></div>';
    h += '<div class="strip" style="border-color:rgba(249,115,22,.5);background:rgba(249,115,22,.08)" data-testid="cr-discordanza"><span><strong>Realizzato live: due conti diversi.</strong> Il conto dice +8,12 €, le righe dei bot +7,60 €. Finché non coincidono, il numero qui sopra è quello calcolato dalla pagina sulle righe dei trade: verifica prima di operarci sopra.</span></div>';
    h += '<div class="strip live" data-testid="cr-errore-comando"><span><strong>Il comando non è andato a buon fine:</strong> timeout del servizio. Lo stato qui sopra è quello che dice il servizio: se non è cambiato, <strong>il bot sta ancora facendo quello che faceva</strong>.</span></div>';
    h += '<div class="strip" style="border-color:rgba(249,115,22,.5);background:rgba(249,115,22,.08);flex-direction:column;align-items:flex-start" data-testid="cr-mike-resting"><b>' + S.icon('shield') + ' Mike: uscita appoggiata SPENTA in live</b><span style="font-size:12px">In live l’uscita torna «a mercato»: Mike esegue una strategia <b>diversa</b> da quella provata in paper, e il ciclo che in demo chiude in profitto lì chiude in perdita.</span><span class="foot" data-testid="cr-mike-resting-modo">Mike è in LIVE adesso: riguarda i soldi veri di questo momento.</span></div>';
    h += '<div class="strip warn" data-testid="cr-errore">get_omega_events non riuscita. I riquadri che dipendono da queste fonti mostrano l’ultimo dato letto, non uno più recente.</div>';
    return h;
  }
  S.on('cr-cond', function () { U().cond = !U().cond; S.rerender(); });

  /* ======================= 2.Q QUOTE ======================= */
  function quote(p, tid) {
    var lab = p.sport === 'calcio' ? ['1', 'X', '2'] : [p.casa, p.osp];
    return '<span class="row" style="gap:6px" data-testid="' + tid + '" title="Match Odds: miglior BACK / miglior LAY di adesso">' + p.q.map(function (x, i) {
      return '<span class="row" style="gap:3px;flex-wrap:nowrap" data-testid="cr-quota-cella"><span class="foot" style="max-width:80px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + lab[i] + '</span><span class="o b" style="min-width:40px;height:22px;cursor:default" data-testid="cr-quota-back">' + S.odds(x[0]) + '</span><span class="o l" style="min-width:40px;height:22px;cursor:default" data-testid="cr-quota-lay">' + S.odds(x[1]) + '</span></span>';
    }).join('') + '</span>';
  }
  function lineeOu(p) {
    if (!p.ou || !p.ou.length) return '';
    return '<div class="row" style="gap:12px" data-testid="cr-calcio-vivo-ou">' + p.ou.map(function (l) { return '<span class="row" style="gap:4px" data-testid="cr-quote-ou-linea"><b class="foot">' + l[0] + '</b><span class="foot">U</span><span class="o b" style="min-width:38px;height:20px;font-size:11px;cursor:default">' + S.odds(l[1]) + '</span><span class="o l" style="min-width:38px;height:20px;font-size:11px;cursor:default">' + S.odds(l[2]) + '</span><span class="foot" data-testid="cr-quote-ou-eta">ultimo cambio: <span class="pos">2 s</span></span></span>'; }).join('') + '</div>';
  }
  function azioni(p) {
    return '<div class="row" data-testid="cr-azioni" style="gap:6px">' + S.media(true) +
      (p.sport === 'calcio' ? '<a class="btn sm" data-go="dashboard" href="#dashboard" data-testid="cr-statistiche">Statistiche</a>' : '') +
      '<a class="btn sm" data-go="' + (p.sport === 'tennis' ? 'tennis-terminal' : 'segui-live') + '" href="#" data-testid="cr-trading">Trading</a>' +
      '<button class="btn sm ' + (p.live ? 'danger' : '') + '" data-act="toast" data-t="' + (p.live ? 'REC attivo' : 'Segui live') + '" data-testid="cr-segui-live">' + (p.live ? '● REC' : 'Segui live') + '</button></div>';
  }

  /* ======================= 2.I RIGA OPERAZIONE ======================= */
  function rigaOp(o) {
    var key = 'chiudi-' + o.id, live = o.live;
    var u = U(), armed = u.armed[key];
    return '<div data-testid="cr-op-riga" style="padding:7px 8px;border-radius:8px;background:hsl(var(--muted)/.45);display:flex;flex-direction:column;gap:4px;font-size:11.5px">' +
      '<div class="row" style="gap:6px">' + chip(o.lato === 'LAY' ? 'banca' : 'punta', o.lato === 'LAY' ? 'rose' : 'sky') + '<b>' + o.sel + '</b><span class="mono">' + S.odds(o.q) + '</span><span class="mono">' + M(o.stake) + '</span>' +
      '<span class="mono foot" data-testid="cr-stato-ordine">chiesto ' + M(o.stake) + ' · abbinato ' + M(o.stake) + ' · residuo 0,00 €</span><span class="ora" data-testid="cr-op-liability">liability ' + M(o.lato === 'LAY' ? o.stake * (o.q - 1) : o.stake) + '</span>' +
      '<span class="mono" data-testid="cr-op-quota-viva">ora B <span style="color:var(--back)">' + S.odds(o.b) + '</span> / L <span style="color:var(--lay)">' + S.odds(o.l) + '</span> <span class="tealc">−2 tick</span></span>' +
      '<span data-testid="cr-op-chiudo-ora">chiudi ora <span class="mono">' + S.odds(o.b) + '</span> <b class="' + S.tone(o.co) + '">' + M(o.co, { signed: true }) + '</b> <span class="foot">ladder al ms</span></span>' +
      '<span class="chip">' + o.regola + '</span>' + chip(live ? 'live' : 'paper', live ? 'amber' : '') + '<span class="foot mono" style="margin-left:auto">' + o.ora + '</span><b class="mut" title="non ancora regolata: nessun risultato certo, non è uno zero">—</b>' +
      '<span data-testid="cr-op-chiudi-box">' + (armed ? '<button class="btn sm gold" style="font-weight:800" data-act="cr-ok" data-k="' + key + '" data-testid="cr-op-chiudi-conferma">Conferma</button><span class="foot" data-testid="cr-op-chiudi-armato">Live, soldi veri: confermi la chiusura? Stima chiudendo ora ' + M(o.co, { signed: true }) + '. <a data-act="cr-disarm" data-k="' + key + '" style="cursor:pointer;text-decoration:underline">annulla</a></span>'
        : '<button class="btn sm teal" data-act="' + (live ? 'cr-arm' : 'toast') + '" data-k="' + key + '" data-t="Chiusura inviata (paper)" data-testid="cr-op-chiudi" title="' + o.cosa + '">Chiudi</button>') + '</span></div>' +
      '<div class="foot" data-testid="cr-op-dettaglio">stato: abbinato · ingresso ' + o.ingr + ' · coperta 0 % · a rischio ' + M(o.lato === 'LAY' ? o.stake * (o.q - 1) : o.stake) + ' · P&L aperto <b class="' + S.tone(o.co) + '">' + M(o.co, { signed: true }) + '</b></div></div>';
  }
  var OPS = {
    '34812001': { mike: [{ id: 'm1', lato: 'LAY', sel: 'Under 3.5 Goals', q: 1.30, stake: 8, b: 1.22, l: 1.23, co: 0.46, regola: 'ingresso Under 3.5', live: true, ora: '09:46', ingr: "4′ 0-0", cosa: 'Mike: chiude l’intera posizione della PARTITA' }, { id: 'm2', lato: 'BACK', sel: 'Over 4.5 Goals', q: 13.5, stake: 0.6, b: 15, l: 16, co: -0.06, regola: 'copertura linea 4.5', live: true, ora: '10:18', ingr: "36′ 1-0", cosa: 'Mike: chiude l’intera posizione della PARTITA' }], omega: [{ id: 'o1', lato: 'LAY', sel: '0 - 0', q: 8.4, stake: 2, b: 990, l: 1000, co: 2, regola: 'risultato esatto 1° tempo', live: false, ora: '09:41', ingr: "pre", cosa: 'Omega: green-up dell’abbinato' }] },
    '34812044': { safe: [{ id: 's1', lato: 'LAY', sel: 'Pareggio', q: 3.3, stake: 4, b: 3.25, l: 3.3, co: 0.06, regola: 'base', live: false, ora: '10:31', ingr: "18′ 0-0", cosa: 'Safe: green-up dell’abbinato' }, { id: 's2', lato: 'BACK', sel: 'Under 2.5 Goals', q: 1.62, stake: 5, b: 1.58, l: 1.6, co: 0.12, regola: 'punta', live: false, ora: '10:34', ingr: "21′ 0-0", cosa: 'Safe: green-up dell’abbinato' }] },
    '34813501': { tennis_pro: [{ id: 't1', lato: 'BACK', sel: 'J. Sinner', q: 1.31, stake: 5, b: 1.24, l: 1.25, co: 0.28, regola: 'tennis', live: false, ora: '10:02', ingr: '6-4 1-1', cosa: 'tennis: chiude la posizione sulla PARTITA, non rientra finché non lo riarmi' }], tennis_scalper: [{ id: 't2', lato: 'LAY', sel: 'J. Draper', q: 5.1, stake: 1, b: 5.0, l: 5.1, co: 0.02, regola: 'tennis', live: false, ora: '10:11', ingr: '6-4 2-0', cosa: 'tennis: chiude la posizione sulla PARTITA' }] }
  };
  var SIG = { omega: 'Ω', safe: 'S', mike: 'M', scalper: 'Sc', tennis_scalper: 'Sc', tennis_pro: 'Pr', tennis_flb: 'Fl', tennis_swing: 'Sw' };
  var BN = { omega: 'Omega', safe: 'Safe', mike: 'Mike', scalper: 'Scalper calcio', tennis_scalper: 'Scalper', tennis_pro: 'Pro', tennis_flb: 'FLB', tennis_swing: 'Swing' };

  /* ======================= 2.J SCHEDA MIKE ======================= */
  function schedaMike() {
    var v = function (k, val, tid) { return '<div data-testid="cr-mike-' + tid + '"><div class="lbl" style="font-size:9.5px">' + k + '</div><div class="mono" style="font-size:11.5px">' + val + '</div></div>'; };
    return '<div class="panel flat" data-testid="cr-mike" style="padding:10px 12px;border-color:rgba(45,212,191,.35)"><div class="row" style="justify-content:space-between"><span class="lbl">Mike — modello e mercato su questa partita</span>' + chip('quote 2 s', 'paper') + '</div>' +
      '<div class="strip live" data-testid="cr-mike-proposta" style="margin:8px 0;flex-direction:column;align-items:flex-start;gap:4px"><b data-testid="cr-mike-proposta-titolo">Mike vorrebbe uscire: cash out della posizione (può chiudere IN PERDITA)</b><span class="mono foot" data-testid="cr-mike-proposta-ordini">copertura BACK 8,42 € @ 1,22 (ora 1,22 / 1,23, al ms)</span><span class="foot" data-testid="cr-mike-proposta-esecuzione">al clic: il bot esce a mercato con la sua macchina d’uscita (prezzi e size di quel momento), come la strategia la vuole</span><span style="font-size:12px" data-testid="cr-mike-proposta-numeri">chiudendo tutta la partita ora <b class="pos">+0,40 €</b> (aggiornata 1 s fa) · alla decisione +0,46 € · deciso 9 s fa · 58′</span><div class="row"><button class="btn sm gold" data-act="toast" data-t="approvazione inviata: parte al prossimo giro del bot" data-testid="cr-mike-proposta-approva">approva uscita</button><span class="foot">oppure chiudi a mano con «Chiudi» di Mike</span></div></div>' +
      '<div class="grid g6" style="gap:8px">' + v('P(4 gol esatti) mercato', '6,1 %', 'p4-mercato') + v('modello', '5,4 %', 'p4-modello') + v('pre-partita', '7,9 %', 'p4-pre') + v('gol attesi', '1,62 · 0,71', 'lambda') + v('Under 3.5', '1,22 / 1,23', 'u35') + v('Over 4.5', '15 / 16', 'o45') + v('Under 4.5', '1,07 / 1,08', 'u45') + v('volume', '84.210 €', 'volume') + v('ingresso', '1,30', 'entry') + v('al fischio', '1,32 · <span class="pos">−1 tick</span>', 'ko') + v('ciclo', '1 · 0 chiusi', 'cicli') + v('Liability aperta (netta)', '<span class="ora">2,40 €</span> ' + mk('BOT'), 'liability') + v('bloccato', '—', 'locked') + v('cash out', '+0,40 € · 5 % / soglia 3 %', 'cashout') + '</div>' +
      '<div class="row foot" style="margin-top:6px" data-testid="cr-mike-per-gol">se finisce con ' + [[1, 0.6], [2, 0.6], [3, 0.6], [4, -2.4], [5, 7.8]].map(function (g) { return '<span data-testid="cr-mike-gol-' + g[0] + '">' + g[0] + ' gol <b class="' + S.tone(g[1]) + '">' + M(g[1], { signed: true }) + '</b></span>'; }).join(' · ') + '</div>' +
      '<div class="foot" data-testid="cr-mike-lambda-fonte">fonte statistiche partita</div></div>';
  }

  /* ======================= 2.L CASH OUT GLOBALE ======================= */
  function cashOutGlobale(p) {
    var u = U(), key = 'cog-' + p.id;
    var liveBlock = p.live ? '<div data-testid="cr-cashout-globale-live" style="padding:8px 10px;border-radius:9px;background:rgba(239,68,68,.06);border:1px solid rgba(239,68,68,.3)"><div class="row"><b style="font-size:12px">Cash out della partita: gambe dei bot (se le chiudo tutte adesso)</b><b class="pos" style="font-size:15px;margin-left:auto" data-testid="cr-cashout-globale-netto">+0,38 €</b><span class="foot">netto commissione</span>' + mk('STIMA') + '</div>' +
      '<div class="foot" data-testid="cr-cashout-globale-commissione">(lordo +0,40 €, commissione 0,02 € sul netto di ogni mercato)</div><div class="amb" style="font-size:11px" data-testid="cr-cashout-globale-solo-bot">solo ordini dei bot: gli ordini fatti dal sito o dall’app Betfair non sono inclusi</div>' +
      '<div class="foot mono" data-testid="cr-cashout-globale-gamba" style="margin-top:4px">Mike · LIVE · banca Under 3.5 Goals 8,00 € @ 1,30 → chiudo punta 8,42 € @ 1,22 · <span class="pos">+0,46 €</span> · ladder al ms · 1 s fa</div>' +
      '<div class="foot" data-testid="cr-cashout-globale-bot-mike">il bot Mike calcola: <b class="pos">+0,40 €</b> ' + mk('BOT') + ' differenza 0,02 € · cause possibili: prezzi letti in istanti diversi</div>' +
      '<div class="row" data-testid="cr-cashout-globale-chiudi-tutte" style="margin-top:6px"><span class="foot" data-testid="cr-cashout-globale-piano">2 gambe di Mike</span>' +
      (u.armed[key] ? '<button class="btn sm gold" style="font-weight:800" data-act="cr-ok" data-k="' + key + '" data-testid="cr-cashout-globale-conferma">Confermo: chiudi tutte le gambe</button><span class="foot" data-testid="cr-cashout-globale-armato">Sono soldi veri: 1 comando a 1 bot. <a data-act="cr-disarm" data-k="' + key + '" style="cursor:pointer;text-decoration:underline">annulla</a></span>' : '<button class="btn sm" style="color:var(--lay);border-color:var(--lay-bd)" data-act="cr-arm" data-k="' + key + '" data-testid="cr-cashout-globale-avvia">Chiudi tutte le gambe dei bot</button>') + '</div></div>'
      : '<div class="foot" data-testid="cr-cashout-globale-live-vuoto">Cash out della partita: nessuna gamba LIVE abbinata su questa partita</div>';
    return '<div data-testid="cr-cashout-globale" class="col" style="gap:6px">' + liveBlock +
      '<div data-testid="cr-cashout-globale-prova" style="padding:8px 10px;border-radius:9px;border:1px dashed hsl(var(--glass-border))"><div class="row"><b style="font-size:12px;color:var(--back)">Prova (simulato, mai sommato ai soldi veri)</b><b class="pos" style="margin-left:auto">' + M(p.prova, { signed: true }) + '</b>' + mk('PROVA') + '</div></div></div>';
  }

  /* ======================= 2.H SCHEDA PARTITA ======================= */
  function schedaPartita(p, scheda) {
    var u = U(), open = u.dett[p.id];
    var bordo = p.live ? 'hsl(var(--primary))' : p.stato === 'live' ? 'hsl(var(--secondary))' : 'hsl(var(--border))';
    var ops = OPS[p.id] || {};
    var bots = p.sport === 'calcio' ? ['omega', 'safe', 'mike', 'scalper'] : ['safe', 'tennis_scalper', 'tennis_pro', 'tennis_flb', 'tennis_swing'];
    var h = '<article class="panel flat" data-testid="cr-partita" data-event-id="' + p.id + '" style="border-left:3px solid ' + bordo + ';padding:10px 12px;display:flex;flex-direction:column;gap:8px">';
    h += '<div class="row" style="gap:8px"><span aria-label="' + p.sport + '">' + (p.sport === 'calcio' ? '⚽' : '🎾') + '</span><div class="match" data-testid="cr-nomi-partita"><b data-testid="cr-nome-squadra">' + p.casa + ' – ' + p.osp + '</b></div>' +
      '<span class="chip gold" title="in gioco"><span class="led live" style="background:hsl(var(--secondary));width:6px;height:6px"></span>' + (p.sport === 'calcio' ? p.min + '′ · ' + p.score : p.score) + '</span>' +
      '<span style="margin-left:auto">' + azioni(p) + '</span></div>';
    if (p.sport === 'calcio') h += '<div class="col" data-testid="cr-calcio-vivo" style="gap:6px"><div class="row" style="gap:10px">' + quote(p, 'cr-calcio-vivo-quote') + '<span class="foot" data-testid="cr-latenza">ultimo cambio: <span class="pos">1 s</span></span><span class="foot" data-testid="cr-calcio-vivo-volume" title="euro già scambiati sul Match Odds">vol. €' + p.vol.toLocaleString('it-IT') + '</span><span class="foot" style="margin-left:auto" data-testid="cr-calcio-vivo-eta-punteggio">punteggio 4 s</span></div>' + lineeOu(p) + '</div>';
    else h += '<div class="row" data-testid="cr-tennis-vivo" style="gap:12px;font-size:12px"><span data-testid="cr-tennis-vivo-punteggio" class="mono"><b class="gold">' + p.casa + ' 40</b> · ' + p.osp + ' 15</span><span data-testid="cr-tennis-vivo-server">servizio <span class="gold">●</span> ' + p.server + '</span>' + quote(p, 'cr-tennis-vivo-quote') + '<span class="foot" data-testid="cr-tennis-vivo-eta-quote">ultimo aggiornamento del runner: <span class="pos">1 s</span></span><span class="foot" style="margin-left:auto" data-testid="cr-tennis-vivo-eta">punteggio 2 s · canale</span></div>';
    if (p.safeCash) {
      var k = 'cos-' + p.id;
      h += '<div class="row" data-testid="cr-cashout-partita" data-chiusa="false">' + (u.armed[k] ? '<button class="btn sm gold" data-act="cr-ok" data-k="' + k + '" data-testid="cr-cashout-partita-conferma">Confermo: chiudi le posizioni di Safe</button><button class="btn sm ghost" data-act="cr-disarm" data-k="' + k + '" data-testid="cr-cashout-partita-annulla">annulla</button>'
        : '<button class="btn sm" style="color:var(--lay);border-color:var(--lay-bd)" data-act="toast" data-t="Cash out Safe (paper): nessuna conferma" data-testid="cr-cashout-partita-avvia" title="chiude TUTTE le posizioni di SAFE su questa partita (non quelle degli altri bot) e gli dice di non fare altro">⊗ Cash out Safe</button>') + '</div>';
    }
    if (Object.keys(ops).length) h += cashOutGlobale(p);
    if (p.sport === 'calcio' && p.live) h += '<div class="foot" data-testid="cr-ordini-conto">Ordini dal sito/app (conto Betfair): nessuno ' + mk('CONTO') + ' <span data-testid="cr-ordini-conto-letto">aperto secondo lo specchio degli ordini interrogato alle 10:41:07</span></div>';
    // metro
    var pct = p.pnl != null ? Math.min(100, Math.max(0, p.pnl / p.target * 100)) : 0;
    h += '<div class="row" style="justify-content:space-between"><span class="foot" data-testid="cr-target">target <b class="gold">' + M(p.target) + '</b></span><span class="row"><b class="' + S.tone(p.pnl) + '" style="font:800 18px var(--f-display)" data-testid="cr-pnl-partita">' + (p.pnl == null ? '—' : M(p.pnl, { signed: true })) + '</b>' + (p.pnl != null ? '<span class="foot">manca ' + M(p.target - p.pnl) + '</span>' : '') + '</span></div>' +
      '<div class="foot" data-testid="cr-pnl-partita-paper" style="text-align:right">in prova <b class="pos">' + M(p.prova, { signed: true }) + '</b> — non entra nel target</div><div class="bar" style="height:4px"><i style="width:' + pct + '%"></i></div>';
    // riga bot di sport
    h += '<div class="row" style="gap:4px">' + bots.map(function (b) {
      var n = (p.bots || {})[b], on = !!n, sel = open === b;
      return '<button data-act="cr-dett" data-e="' + p.id + '" data-b="' + b + '" ' + (on ? '' : 'disabled') + ' data-testid="cr-bot-' + b + '-' + p.id + '" title="' + BN[b] + ': ' + (on ? n + ' operazioni — clicca per il dettaglio' : 'nessuna operazione su questa partita') + '" style="width:28px;height:22px;border-radius:5px;font:700 10.5px var(--f-body);cursor:' + (on ? 'pointer' : 'default') + ';border:1px solid ' + (on ? (sel ? 'hsl(var(--foreground))' : 'hsl(var(--primary)/.6)') : 'hsl(var(--border))') + ';background:' + (on ? 'hsl(var(--primary)/.18)' : 'transparent') + ';color:' + (on ? 'hsl(var(--foreground))' : 'hsl(var(--muted-foreground)/.5)') + '">' + SIG[b] + '</button>';
    }).join('') + (p.liab || p.liabProva ? '<span class="foot" style="margin-left:auto" data-testid="cr-liability-partita">' + (p.live ? '<span data-testid="cr-liability-netta-mike">Liability aperta (netta, Mike) <b class="ora">2,40 €</b> ' + mk('BOT') + '</span> · liability delle righe (lorda) <b class="ora">' + M(p.liab) + '</b> · ' : '') + 'prova (lorda) ' + M(p.liabProva) + '</span>' : '') + '</div>';
    if (open && ops[open]) h += '<div data-testid="cr-dettaglio-bot" class="col" style="gap:6px;padding-top:6px;border-top:1px solid hsl(var(--border))"><b style="font-size:12px">' + BN[open] + ' — operazioni su questa partita</b>' + (open === 'mike' ? schedaMike() : '') + ops[open].map(rigaOp).join('') + '</div>';
    return h + '</article>';
  }
  S.on('cr-dett', function (t) { var u = U(); u.dett[t.dataset.e] = u.dett[t.dataset.e] === t.dataset.b ? null : t.dataset.b; S.rerender(); });

  /* ======================= 2.G SCHEDA PRE-MATCH ======================= */
  function schedaPre(p) {
    var vicino = /^\d+ min$/.test(p.fra) && parseInt(p.fra, 10) <= 15;
    return '<article class="panel flat" data-testid="cr-pre-match" data-event-id="' + p.id + '" style="border-left:3px solid ' + (vicino ? 'hsl(var(--secondary))' : 'hsl(var(--border))') + ';padding:10px 12px;display:flex;flex-direction:column;gap:6px">' +
      '<div class="row"><span class="mono" data-testid="cr-pre-orario">' + p.ko + '</span><b data-testid="cr-nomi-partita">' + p.casa + ' – ' + p.osp + '</b><span class="foot" data-testid="cr-pre-manca" title="quanto manca al fischio d’inizio">⏱ fra ' + p.fra + '</span><span style="margin-left:auto">' + azioni(p) + '</span></div>' +
      '<div class="col" data-testid="cr-pre-quote" style="gap:5px;padding-left:12px"><div class="row">' + quote(p, 'cr-pre-quote-mo') + '<span class="foot" data-testid="cr-pre-latenza">ultimo cambio: <span class="pos">3 s</span></span></div>' + lineeOu(p).replace('cr-calcio-vivo-ou', 'cr-pre-quote-ou') + '</div>' +
      (p.mikePre ? '<div data-testid="cr-pre-operazioni" class="col" style="gap:6px"><div class="foot">Mike ha un ingresso armato al fischio: nessuna operazione ancora a mercato.</div></div>' : '') + '</article>';
  }

  /* ======================= BANCO: ELENCHI ======================= */
  function filtraSport(list) { var s = U().sport; return s ? list.filter(function (p) { return p.sport === s; }) : list; }
  function perCampionato(list, fn) {
    var g = {}; list.forEach(function (p) { (g[p.comp] = g[p.comp] || []).push(p); });
    return Object.keys(g).map(function (c) { return '<section class="col" style="gap:8px"><div class="row" style="justify-content:space-between"><h4 class="lbl" style="font-size:11px">' + c + ' <span class="mono">' + g[c].length + '</span></h4>' + (g[c][0].ko ? '<span class="foot">dalle ' + g[c][0].ko + '</span>' : '') + '</div>' + g[c].map(fn).join('') + '</section>'; }).join('');
  }
  function elenco(stato) {
    var list = filtraSport(PARTITE.filter(function (p) { return p.stato === stato; }));
    var comps = {}; list.forEach(function (p) { comps[p.comp] = 1; });
    return '<div data-testid="cr-elenco-' + stato + '" class="col" style="gap:10px"><div class="row" style="justify-content:space-between"><span class="lbl">' + (stato === 'pre' ? 'Non ancora cominciate' : 'In gioco adesso') + '</span><span class="foot">' + list.length + ' partite in ' + Object.keys(comps).length + ' competizioni</span></div>' +
      (stato === 'live' ? '<div class="foot gold" data-testid="cr-copertura">controllo del gioco: dato presente su 3 partite in gioco su 3 (100%).</div>' : '') +
      (list.length ? perCampionato(list, stato === 'pre' ? schedaPre : function (p) { return schedaPartita(p, 'live'); }) : '<div class="empty">' + (stato === 'pre' ? 'Nessuna partita in attesa: o sono tutte in gioco, o la giornata è finita.' : 'Nessuna partita in gioco adesso. Le prossime sono nella scheda Pre-match.') + '</div>') + '</div>';
  }
  function aperte() {
    var s = U().sport;
    var live = filtraSport(PARTITE.filter(function (p) { return p.live; })), prova = filtraSport(PARTITE.filter(function (p) { return p.stato === 'live' && !p.live; }));
    var h = '<div data-testid="cr-posizioni" class="col" style="gap:10px"><div class="row" style="justify-content:space-between"><b>Posizioni aperte' + (s ? ' · solo ' + s : '') + '</b><span data-testid="cr-aperte-conteggi"><b style="color:#fca5a5">' + live.length + ' LIVE</b> · ' + prova.length + ' prova</span></div>';
    if (live.length) h += '<div class="strip" style="border-color:rgba(249,115,22,.5);background:rgba(249,115,22,.08)" data-testid="cr-aperte-banner-live">' + live.length + ' partita con posizione LIVE · 2 gambe con soldi veri</div>' +
      '<section data-testid="cr-aperte-live" class="col" style="gap:8px"><h4 style="font-size:12px;color:#fca5a5">LIVE: soldi veri <span class="cnt" data-testid="cr-aperte-live-conta">' + live.length + '</span></h4>' + live.map(function (p) { return '<div data-testid="cr-aperta-' + p.id + '" class="col" style="gap:6px"><div class="row" data-testid="cr-aperta-stato-' + p.id + '">' + chip('IN VERDE', 'paper') + '<span class="mono foot" title="caso peggiore fra gli esiti, gambe LIVE dei bot (non i soldi fuori dai bot)">caso peggiore +0,12 €</span></div>' + schedaPartita(p, 'aperte') + '</div>'; }).join('') + '</section>';
    h += '<section data-testid="cr-aperte-prova" class="col" style="gap:8px"><h4 style="font-size:12px" class="mut">PROVA: simulato, mai sommato <span class="cnt" data-testid="cr-aperte-prova-conta">' + prova.length + '</span></h4>' + (prova.length ? prova.map(function (p) { return '<div data-testid="cr-aperta-' + p.id + '">' + schedaPartita(p, 'aperte') + '</div>'; }).join('') : '<div class="empty">Nessuna posizione aperta sul ' + s + '. Clicca di nuovo la tessera per rivedere tutti gli sport.</div>') + '</section>';
    return h + '</div>';
  }

  /* ======================= 2.K POSIZIONI CHIUSE ======================= */
  function chiuse() {
    var f = U().chiuse, veri = f.modo === 'live';
    var pill = function (k, v, l, tid) { return '<button class="chip" style="cursor:pointer;height:22px;' + (f[k] === v ? 'border-color:hsl(var(--primary)/.6);color:hsl(var(--primary));background:hsl(var(--primary)/.1)' : '') + '" aria-pressed="' + (f[k] === v) + '" data-act="cr-ch" data-k="' + k + '" data-v="' + v + '" data-testid="' + tid + '">' + l + '</button>'; };
    var rows = veri ? [['mike', 'Mike', 'Napoli v Lazio (ieri)', 'banca', 'Under 3.5 Goals', 'CHIUSA · CONFERMATA', 'vinta', 8.12, 'conto Betfair', '09:58']] :
      [['omega', 'Omega', 'Atalanta v Genoa', 'banca', '1 - 0', 'REGOLATA DAL MERCATO', 'vinta', 3.6, 'simulato', '09:12'], ['safe', 'Safe calcio', 'Feyenoord v AZ', 'banca', 'Pareggio', 'CHIUSA · CONFERMATA', 'persa', -2.2, 'simulato', '09:40'], ['tennis_pro', 'Pro', 'Gauff v Andreeva', 'punta', 'C. Gauff', 'CHIUSA · CONFERMATA', 'vinta', 1.1, 'simulato', '08:51']];
    if (f.esito !== 'tutte') rows = rows.filter(function (r) { return r[6] === f.esito; });
    if (f.bot !== 'tutti') rows = rows.filter(function (r) { return r[0] === f.bot; });
    var tot = rows.reduce(function (a, r) { return a + r[7]; }, 0);
    var h = '<div data-testid="cr-chiuse" class="col" style="gap:10px"><div class="row"><b>Posizioni chiuse</b>' + chip('Oggi · ' + rows.length + ' chiuse') + '<b class="' + S.tone(tot) + '" style="font-size:15px" data-testid="cr-chiuse-totale">' + M(tot, { signed: true }) + '</b><span class="chip ' + (veri ? 'paper' : '') + '" data-testid="cr-chiuse-totale-fonte">' + (veri ? 'conto Betfair' : 'simulato') + '</span><span class="foot">' + rows.filter(function (r) { return r[6] === 'vinta'; }).length + ' V · ' + rows.filter(function (r) { return r[6] === 'persa'; }).length + ' P</span><span style="margin-left:auto" class="row">' + (veri ? chip('soldi veri', 'live') : '') + C.storicoLink('calcio', true) + '</span></div>';
    if (veri) h += '<div class="foot" data-testid="cr-chiuse-composizione">conto Betfair (regolato) <b class="pos">+8,12 €</b> · <span class="amb">stima del bot (Betfair non ha ancora regolato) 0,00 €</span></div><div class="foot pos" data-testid="cr-chiuse-controprova" data-coincide="true">Controprova con la barra di giornata: <b>coincide</b> (+8,12 €).</div><div class="foot" data-testid="cr-chiuse-certezza"><span class="pos">1 chiusa confermata</span></div>';
    h += '<div class="row" style="gap:12px;font-size:11px"><span class="row" style="gap:4px"><span class="lbl">giornata</span><button class="btn sm" data-testid="cr-f-giorno-prima">◀</button><input class="inp" type="date" id="cr-f-giorno" data-testid="cr-f-giorno" value="2026-10-01" aria-label="giornata di regolamento da mostrare" style="height:24px"><button class="btn sm" data-testid="cr-f-giorno-dopo">▶</button><button class="btn sm" data-testid="cr-f-giorno-oggi">oggi</button></span>' +
      '<span class="row" style="gap:4px"><span class="lbl">soldi</span>' + pill('modo', 'live', 'veri', 'cr-f-modo-live') + pill('modo', 'paper', 'prova', 'cr-f-modo-paper') + '</span>' +
      (veri ? '<span class="row" style="gap:4px"><span class="lbl">P&L</span>' + pill('fonte', 'tutte', 'con stimati', 'cr-f-fonte-tutte') + pill('fonte', 'betfair', 'solo Betfair', 'cr-f-fonte-betfair') + '</span>' : '') +
      '<span class="row" style="gap:4px"><span class="lbl">esito</span>' + [['tutte', 'tutte'], ['vinta', 'vinte'], ['persa', 'perse'], ['pari', 'pari']].map(function (x) { return pill('esito', x[0], x[1], 'cr-f-esito-' + x[0]); }).join('') + '</span>' +
      '<span class="row" style="gap:4px"><span class="lbl">bot</span>' + [['tutti', 'tutti'], ['omega', 'Omega'], ['safe', 'Safe'], ['mike', 'Mike'], ['tennis_scalper', 'Scalper'], ['tennis_pro', 'Pro'], ['tennis_flb', 'FLB'], ['tennis_swing', 'Swing']].map(function (x) { return pill('bot', x[0], x[1], 'cr-f-bot-' + x[0]); }).join('') + '</span></div>' +
      '<div class="foot" data-testid="cr-chiuse-lettura" data-stato="pronto">Giornata letta dal database alle 10:40. <a style="cursor:pointer;text-decoration:underline" data-act="toast" data-t="Rilettura della giornata" data-testid="cr-chiuse-rileggi">rileggi</a></div>';
    if (!rows.length) return h + '<div class="empty">Nessuna posizione chiusa OGGI con questi filtri. Le giornate precedenti sono nello Storico.</div></div>';
    var byBot = {}; rows.forEach(function (r) { (byBot[r[1]] = byBot[r[1]] || []).push(r); });
    h += Object.keys(byBot).map(function (b) {
      var rs = byBot[b], t = rs.reduce(function (a, r) { return a + r[7]; }, 0);
      return '<div data-testid="cr-chiuse-bot-' + rs[0][0] + '" style="border:1px solid hsl(var(--border));border-radius:9px;padding:8px 10px"><div class="row"><b style="font-size:12px;text-transform:uppercase;letter-spacing:.06em">' + b + '</b><span class="foot">' + rs.length + ' operazioni · ' + rs.length + ' partite</span><b class="' + S.tone(t) + '" style="margin-left:auto">' + M(t, { signed: true }) + '</b></div>' +
        rs.map(function (r) { return '<div data-testid="cr-chiuse-partita" style="margin-top:6px;padding:6px 8px;border-radius:7px;background:hsl(var(--muted)/.45)"><div class="row" style="font-size:12px">▾ <b>' + r[2] + '</b><span class="foot">1 operazione</span></div><div class="row" data-testid="cr-chiusa" style="font-size:11.5px;margin-top:4px"><span class="lbl">' + r[1] + '</span>' + chip(r[3], r[3] === 'banca' ? 'rose' : 'sky') + '<span>Match Odds · ' + r[4] + '</span>' + chip(r[5], 'paper') + chip(veri ? 'veri' : 'prova', veri ? 'live' : '') + '<span>' + r[6] + '</span><b class="' + S.tone(r[7]) + '" style="margin-left:auto" title="P&L dell’OPERAZIONE intera: apertura e coperture insieme">' + M(r[7], { signed: true }) + '</b><span class="chip">' + r[8] + '</span><span class="mono foot">' + r[9] + '</span></div><div class="foot" data-testid="cr-chiusa-sintesi">ingresso 3,30 per 4,00 € · chiusura media 2,90 abbinati 4,55 € · entrata 09:21</div></div>'; }).join('') + '</div>';
    }).join('');
    return h + '</div>';
  }
  S.on('cr-ch', function (t) { U().chiuse[t.dataset.k] = t.dataset.v; S.rerender(); });

  /* ======================= COLONNA 2: USCITE ======================= */
  function uscite() {
    var u = U(), sp = u.sport;
    var h = '<section class="panel" data-testid="cr-nastro" style="padding:12px;display:flex;flex-direction:column;gap:10px"><div class="row" style="justify-content:space-between"><span class="lbl">Uscite — decidi tu</span><span class="foot" data-testid="cr-nastro-contatore">2 in attesa · <span class="ora">1 urgente</span></span></div>';
    if (sp) h += '<div class="foot" data-testid="cr-nastro-non-filtrato">Il filtro ' + sp + ' non tocca questo nastro: le uscite compaiono da entrambi gli sport.</div>';
    h += '<label class="row foot" for="cr-slippage">scostamento massimo dal prezzo della proposta <input class="inp" id="cr-slippage" type="number" step="0.5" min="0.5" max="20" value="2" style="width:64px;height:24px"> %</label>';
    // Omega
    h += '<article class="panel flat" data-testid="cr-proposta-omega" style="padding:10px;display:flex;flex-direction:column;gap:6px"><div class="row"><b class="prim" style="font-size:12px">Omega · uscita</b>' + chip('paper') + '<span class="chip" style="color:var(--back)" title="se il punteggio regge, più avanti si bloccherebbe di più">⌛ aspettare può valere di più</span></div><div class="foot">Inter – Torino · 1-0 · 58′</div>' +
      '<div class="row">' + chip('Punta per chiudere', 'sky') + '<b>0 - 0</b><b class="mono" style="margin-left:auto;font-size:16px" data-testid="cr-omega-back-price">990</b></div><div class="foot mono" data-testid="cr-omega-back-size">per 0,02 € · bancata a 8,40 · proposta a 990</div>' +
      '<div class="grid g2" style="gap:6px">' + [['Blocchi adesso', '+1,98 €', 'pos'], ['Tenere vale', '+2,00 €', 'pos'], ['Se il punteggio regge', '+2,00 €', ''], ['Rischio impegnato', '14,80 €', 'ora']].map(function (c) { return '<div class="kpi" style="padding:6px 8px"><div class="k" style="font-size:9.5px">' + c[0] + '</div><div class="v ' + c[2] + '" style="font-size:14px">' + c[1] + '</div></div>'; }).join('') + '</div>' +
      '<div class="foot">Perché: risultato del 1° tempo già deciso</div><div class="foot pos" data-testid="cr-omega-semaforo" data-semaforo="si">uscita ancora valida: sì</div>' +
      '<div class="grid g2" style="gap:6px"><button class="btn pri" style="justify-content:center" data-act="toast" data-t="Chiusura inviata (paper)" data-testid="cr-omega-approva">Chiudi ora</button><button class="btn" style="justify-content:center" data-act="toast" data-t="Proposta ignorata" data-d="Torna alla prossima occasione." data-testid="cr-omega-ignora">Ignora</button></div><p class="foot" style="margin:0">Nessuna chiusura parte da sola: la proposta resta viva finché non decidi. Se la ignori, torna alla prossima occasione.</p></article>';
    // Safe urgente
    var k = 'safe-uscita';
    h += '<article class="panel flat" data-testid="cr-proposta" data-urgente="true" style="padding:10px;display:flex;flex-direction:column;gap:6px;border-color:rgba(249,115,22,.55)"><div class="row"><b class="gold" style="font-size:12px">Safe · uscita base</b>' + chip('paper') + chip('urgente', 'amber') + '</div><div class="foot">Real Betis – Getafe · 0-0</div>' +
      '<div class="row">' + chip('Banca', 'rose') + '<b>Pareggio</b><span class="foot mono" data-testid="cr-proposta-stato-ordine">abbinato 4,00 €</span><b class="mono" style="margin-left:auto;font-size:16px" data-testid="cr-prezzo-vivo">3,25</b></div><div class="foot" data-testid="cr-scostamento">proposta a 3,30 · <span class="pos">1 tick a favore</span> · ladder al ms 1 s</div>' +
      '<div class="grid g2" style="gap:6px">' + [['Da chiudere', '4,00 €', ''], ['Abbinabile ora', '212 €', ''], ['Chiudere adesso', '+0,06 €', 'pos'], ['Tenere', '+4,00 €', 'pos']].map(function (c) { return '<div class="kpi" style="padding:6px 8px"><div class="k" style="font-size:9.5px">' + c[0] + '</div><div class="v ' + c[2] + '" style="font-size:14px">' + c[1] + '</div>' + (c[0] === 'Tenere' ? '<div class="s">se perde: −9,20 €</div>' : '') + '</div>'; }).join('') + '</div>' +
      '<div class="foot">Perché: uscita obbligatoria — minuto limite della strategia · ingresso banca a 3,30 · quote 1 s</div>' +
      '<div class="grid g2" style="gap:6px"><button class="btn pri" style="justify-content:center" data-act="toast" data-t="Chiusura inviata (paper)" data-testid="cr-approva">Chiudi ora</button><button class="btn" style="justify-content:center" data-act="toast" data-t="Proposta ignorata" data-testid="cr-ignora">Ignora</button></div>' +
      '<p class="foot" style="margin:0">' + S.icon('shield') + ' Uscita del manuale: non approvarla ha un costo, non è una scelta neutra.</p></article>';
    return h + '</section>';
  }

  /* ======================= COLONNA 3: OPPORTUNITA' ======================= */
  function opportunita() {
    var sp = U().sport;
    return '<section class="panel" data-testid="cr-opportunita" style="padding:12px;display:flex;flex-direction:column;gap:10px"><div class="row" style="justify-content:space-between"><span class="lbl">Opportunità di modello</span><span class="cnt" data-testid="cr-opportunita-contatore">1</span></div>' +
      (sp ? '<div class="foot" data-testid="cr-opportunita-non-filtrata">Il filtro ' + sp + ' non tocca questa colonna: le opportunità compaiono da entrambi gli sport.</div>' : '') +
      '<article class="panel flat" data-testid="cr-proposta-opp" data-mode="paper" style="padding:10px;display:flex;flex-direction:column;gap:6px"><div class="row"><b class="gold" style="font-size:12px">Safe · opportunità modello</b><span class="chip" data-testid="cr-opp-sport">calcio</span><span class="chip" data-testid="cr-opp-modalita">paper</span></div><div class="foot" data-testid="cr-opp-partita">Real Betis – Getafe · 31′ · 0-0</div>' +
      '<div class="row">' + chip('Punta', 'sky') + '<b data-testid="cr-opp-selezione">Under 2.5 Goals</b><span class="foot" data-testid="cr-opp-mercato">Over/Under 2.5</span><b class="mono" style="margin-left:auto;font-size:16px" data-testid="cr-opp-prezzo-vivo">1,58</b></div>' +
      '<div class="foot mono" data-testid="cr-opp-book">punta 1,58 (340 €) · banca 1,60 (122 €)</div><div class="foot" data-testid="cr-opp-prezzo">proposta a 1,60 (−0,02 · 2 tick · 1,3 %)</div>' +
      '<div class="grid g2" style="gap:6px">' + [['Stake previsto', '3,00 €'], ['Liability', '3,00 €'], ['Abbinabile ora', '340 €'], ['Valore atteso (EV)', '+0,14 €'], ['P modello', '67,9 %'], ['P del mercato', '63,3 %'], ['Vantaggio', '+4,6 pt'], ['Confidenza', 'media']].map(function (c) { return '<div class="kpi" style="padding:6px 8px"><div class="k" style="font-size:9.5px">' + c[0] + '</div><div class="v" style="font-size:13px">' + c[1] + '</div></div>'; }).join('') + '</div>' +
      '<div class="foot pos" data-testid="cr-opp-semaforo" data-semaforo="si">opportunità ancora valida: sì</div><div class="foot" data-testid="cr-opp-rationale">Perché: ritmo basso, xG cumulato 0,4 al 31′</div><div class="foot" data-testid="cr-opp-eta">quote 1 s · partirebbe in <b>PAPER</b></div>' +
      '<div class="grid g2" style="gap:6px"><button class="btn pri" style="justify-content:center" data-act="toast" data-t="Piazzata (paper)" data-testid="cr-opp-piazza">Piazza</button><button class="btn" style="justify-content:center" data-act="toast" data-t="Opportunità rifiutata" data-testid="cr-opp-rifiuta">Rifiuta</button></div><p class="foot" style="margin:0">Se rifiuti, questa opportunità non torna finché resta la stessa. Nessun ordine parte da solo.</p></article></section>';
  }

  /* ======================= BANCO ======================= */
  function banco() {
    var u = U(), sc = u.scheda;
    var pre = filtraSport(PARTITE.filter(function (p) { return p.stato === 'pre'; })).length, live = filtraSport(PARTITE.filter(function (p) { return p.stato === 'live'; })).length;
    var tabs = '<div class="tabs" role="tablist">' + [['pre', 'Pre-match', pre], ['live', 'Live', live], ['aperte', 'Posizioni aperte', null], ['chiuse', 'Posizioni chiuse', 1]].map(function (t) {
      return '<button role="tab" aria-selected="' + (sc === t[0]) + '" data-act="cr-scheda" data-v="' + t[0] + '" data-testid="cr-tab-' + t[0] + '" style="text-transform:uppercase;font-size:11.5px;letter-spacing:.05em">' + t[1] + ' ' + (t[0] === 'aperte' ? '<span class="mono" data-testid="cr-tab-aperte-conta" title="partite con posizione aperta: LIVE (soldi veri) e in prova, mai sommate"><b style="color:#fca5a5">1 LIVE</b> · 2 prova</span>' : '<span class="cnt">' + t[2] + '</span>') + '</button>';
    }).join('') + '</div>';
    var body = sc === 'pre' ? elenco('pre') : sc === 'live' ? elenco('live') : sc === 'aperte' ? aperte() : chiuse();
    return '<div class="cr-banco"><section class="panel" style="min-width:0"><div style="padding:0 12px">' + tabs + '</div><div class="panel-b" style="max-height:calc(100vh - 140px);overflow:auto">' + body + '</div></section><div class="cr-dec">' + uscite() + opportunita() + '</div></div>';
  }
  S.on('cr-scheda', function (t) { U().scheda = t.dataset.v; S.rerender(); });

  /* ======================= 1.13 DIAGNOSTICA ======================= */
  function catena() {
    return '<details data-testid="cr-catena-dettagli" class="panel flat" style="padding:10px 14px"><summary style="cursor:pointer" class="row"><span class="lbl">Da Betfair al tuo schermo</span><b class="mono pos">1,4 s</b><span class="foot">— dettagli ▸</span></summary>' +
      '<div data-testid="cr-catena" class="col" style="gap:6px;margin-top:8px;font-size:12px"><div class="row"><span>Da Betfair al tuo schermo</span><span class="chip">feed 180 ms</span><span class="chip">spinta dai bot 40 ms</span><span class="chip">lettura database —</span><span class="pos" style="margin-left:auto" data-testid="cr-schermo">quello che vedi è vecchio di 1,4 s</span></div>' +
      '<div class="row" data-testid="cr-catena-operazione"><span>Ultima operazione · #8812</span>' + [['segnale', '12 ms'], ['decisione', '4 ms'], ['coda', '150 ms'], ['Betfair', '1.020 ms', 1], ['conferma', '60 ms']].map(function (x) { return '<span class="foot">' + x[0] + ' <b class="mono ' + (x[2] ? 'ora' : '') + '">' + x[1] + '</b></span>'; }).join('') + '<span data-testid="cr-collo" class="foot">più lento: <b>Betfair</b></span><span class="mono foot">nostro / totale 226 ms / 1.246 ms</span></div></div></details>';
  }

  S.CR = { rigaBot: rigaBot, RIGHE_CALCIO: RIGHE_CALCIO, RIGHE_TENNIS: RIGHE_TENNIS, schedaMike: schedaMike, arm: arm };
  S.reg({
    id: 'control-room', title: 'Control Room', group: 'Sorveglianza',
    render: function () {
      return testata() + banner() +
        '<div class="cr-z1">' + obiettivo() + saldo() + '</div>' +
        '<div class="row foot" data-testid="cr-riga-storico">Questa pagina mostra <b style="color:hsl(var(--foreground))">solo la giornata di oggi</b>. I giorni precedenti: ' + C.storicoLink(U().sport || 'entrambi', true) + '</div>' +
        split() + pannello() + condizionali() + banco() + catena() +
        '<p class="foot" data-testid="page-footer">Fonti: esposizione e realizzato con soldi veri dal conto Betfair; righe, posizioni e prova dai servizi dei bot; le cifre calcolate dalla pagina (cash out ai prezzi di adesso, scarto conto/bot, target di ripiego) sono marcate STIMA.</p>';
    }
  });
})();
