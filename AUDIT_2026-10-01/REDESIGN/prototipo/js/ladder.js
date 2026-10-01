/* ladder.js - LadderView e GridView ridisegnati (components/live/LadderView.tsx, GridView.tsx).
   Colonne di default "layout v2": L (mio lay) | Lay | Prezzo | Back | B (mio back) | P&L | EV | Trd | PIQ.
   Clic su Back/Lay = ordine al prezzo di quella riga, con conferma (PlaceConfirmDialog) se il 1-CLICK non e' armato. */
(function () {
  'use strict';
  var S = window.S, D = window.D;
  var LS = function (k) { return (S.ui.lad = S.ui.lad || {})[k] || (S.ui.lad[k] = { stake: 5, persist: 'Lapse', liab: 'Stake', oneClick: false, view: 'Ladder', tools: {}, selIdx: 0 }); };

  function selLadder(id, sel, ltp, sport, mine) {
    var rows = D.ladder(ltp, 17, sel.length + ltp * 10);
    var ev = sport === 'calcio';
    var cols = '42px 1fr 52px 1fr 42px 50px' + (ev ? ' 46px' : '') + ' 40px 34px';
    var head = ['L', 'Lay', 'Prezzo', 'Back', 'B', 'P&L'].concat(ev ? ['EV'] : []).concat(['Trd', 'PIQ']);
    var h = '<div class="ladder" style="min-width:360px;flex:1">' +
      '<div class="row" style="padding:7px 9px;justify-content:space-between;background:hsl(var(--glass)/.6)"><b style="font-size:12.5px">' + sel + '</b><span class="row" style="gap:6px">' + (ev ? '<button class="chip sky" style="cursor:pointer" title="Kelly: un clic imposta lo stake, mai invia ordini">K€4,20</button>' : '') + '<span class="foot">Matched <b>€' + Math.round(ltp * 61234).toLocaleString('it-IT') + '</b></span></span></div>' +
      '<div class="row" style="padding:5px 9px;gap:8px;font-size:10.5px;border-top:1px solid hsl(var(--border)/.5)"><span class="mut">WOM</span><span style="flex:1;height:6px;border-radius:99px;background:linear-gradient(90deg,var(--back) 0 58%,var(--lay) 58% 100%);opacity:.75"></span><b>58%</b><button class="iconbtn" style="width:22px;height:22px" title="Auto-center ATTIVO: la vista segue il LTP a ogni update.">⌖</button><button class="iconbtn" style="width:22px;height:22px" title="Price bar navigabile 1.01–1000">↕</button><button class="iconbtn" style="width:22px;height:22px" title="Mini-chart candele del prezzo (LTP)">⌇</button>' + (mine ? '<button class="btn sm" style="color:#d8b4fe;border-color:rgba(168,85,247,.45);background:rgba(168,85,247,.12)" data-act="lad-cashout" title="Cash-out COMPLETO al miglior prezzo: annulla i resting della selezione, poi hedge dalle esposizioni reali">Cash-out +€0,46</button>' : '') + '</div>' +
      '<div style="display:grid;grid-template-columns:' + cols + ';background:hsl(var(--muted));font-size:9px;text-transform:uppercase;letter-spacing:.06em;color:hsl(var(--muted-foreground));font-weight:700">' + head.map(function (x) { return '<div style="padding:3px 4px;text-align:center;' + (x === 'L' || x === 'Lay' ? 'color:var(--lay)' : x === 'Back' || x === 'B' ? 'color:var(--back)' : x === 'P&L' || x === 'EV' ? 'color:#d8b4fe' : '') + '">' + x + '</div>'; }).join('') + '</div><div style="max-height:400px;overflow:auto">';
    rows.forEach(function (r, i) {
      var myL = mine && r.p > ltp && i === 4 ? '<span class="my" style="background:var(--lay-bg);padding:0 3px;border-radius:3px" title="I tuoi LAY non abbinati (clic per annullare)">8</span>' : '';
      var myB = mine && r.p < ltp && i === 11 ? '<span class="my" style="background:var(--back-bg);padding:0 3px;border-radius:3px" title="I tuoi BACK non abbinati">5</span>' : '';
      var pl = mine ? ((ltp - r.p) * 9).toFixed(2) : null;
      var tradeW = Math.min(100, r.traded / 40);
      h += '<div style="display:grid;grid-template-columns:' + cols + ';border-top:1px solid hsl(var(--border)/.45);font-size:11.5px;font-variant-numeric:tabular-nums">' +
        '<div style="text-align:center;padding:3px 2px;color:var(--lay)" data-act="lad-cancel">' + myL + '</div>' +
        '<div class="ly ' + (r.lay ? 'q' : '') + '" style="text-align:center;padding:3px 2px;cursor:pointer;' + (r.lay ? 'background:var(--lay-bg);color:var(--lay);font-weight:700' : '') + '" data-act="lad-place" data-k="' + id + '" data-side="LAY" data-p="' + r.p + '" data-sel="' + sel + '" title="LAY €' + LS(id).stake + ' @ ' + r.p + '">' + (r.lay ? r.lay : '') + '</div>' +
        '<div style="text-align:center;padding:3px 2px;font-weight:800;' + (r.ltp ? 'background:hsl(var(--secondary)/.25);color:hsl(var(--secondary));box-shadow:inset 0 0 0 1px hsl(var(--secondary)/.6)' : 'background:hsl(var(--glass)/.6)') + '" title="' + (r.ltp ? 'Ultimo prezzo tradato (LTP) · clic = ricentra' : 'Clic = ricentra il ladder sul prezzo corrente') + '">' + (r.p >= 100 ? r.p.toFixed(0) : r.p.toFixed(2)) + '</div>' +
        '<div class="bk ' + (r.back ? 'q' : '') + '" style="text-align:center;padding:3px 2px;cursor:pointer;' + (r.back ? 'background:var(--back-bg);color:var(--back);font-weight:700' : '') + '" data-act="lad-place" data-k="' + id + '" data-side="BACK" data-p="' + r.p + '" data-sel="' + sel + '" title="BACK €' + LS(id).stake + ' @ ' + r.p + '">' + (r.back ? r.back : '') + '</div>' +
        '<div style="text-align:center;padding:3px 2px;color:var(--back)">' + myB + '</div>' +
        '<div style="text-align:center;padding:3px 2px;font-size:10.5px;color:' + (pl == null ? 'transparent' : pl > 0 ? 'var(--emerald)' : pl < 0 ? 'var(--lay)' : '#d8b4fe') + '" title="Chiudi QUI: blocca questo importo chiudendo a ' + r.p + '">' + (pl == null ? '·' : (pl > 0 ? '+' : pl < 0 ? '−' : '') + Math.abs(pl).toFixed(2)) + '</div>' +
        (ev ? '<div style="text-align:center;padding:3px 2px;font-size:10.5px;color:#c4b5fd">' + (i === 9 ? 'B0,4' : i === 3 ? 'L0,2' : '·') + '</div>' : '') +
        '<div style="position:relative;padding:3px 2px;text-align:right;font-size:10px;color:hsl(var(--secondary)/.85)"><span style="position:absolute;left:0;top:3px;bottom:3px;width:' + tradeW + '%;background:hsl(var(--secondary)/.15)"></span><span style="position:relative">' + (r.traded > 1000 ? (r.traded / 1000).toFixed(1) + 'k' : r.traded) + '</span></div>' +
        '<div style="text-align:center;padding:3px 2px;font-size:10px" class="mut">' + (myL || myB ? '~120' : '') + '</div></div>';
    });
    h += '</div><div class="row" style="justify-content:space-between;padding:6px 9px;font-size:11px;border-top:1px solid hsl(var(--border))"><span>' + (LS(id).liab === 'Liab' ? 'Resp.' : 'Stake') + ' <b class="gold">€' + LS(id).stake + '</b></span>' + (mine ? '<span title="Net = stake netto della selezione · Exp = esposizione (peggior perdita)">Net <b style="color:var(--back)">€5,00</b> · Exp <b class="ora">€2,40</b></span>' : '') + '</div></div>';
    return h;
  }

  /* o: { id, market, sels:[nomi], ltps:[...], mode:'OFF'|'PAPER'|'LIVE', sport, status, mine:true|false, popout, tennis } */
  S.ladderView = function (o) {
    var st = LS(o.id), mode = o.mode, on = mode !== 'OFF';
    var h = '<section class="panel flat" style="padding:0;position:relative" data-ladder="' + o.id + '">';
    h += '<div class="row" style="padding:9px 12px;background:hsl(var(--glass)/.5);border-bottom:1px solid hsl(var(--border));gap:8px">' + S.icon('ladder', 'gold') + '<b>' + o.market + '</b>' +
      S.chip(mode === 'LIVE' ? '🔴 LIVE' : mode, mode === 'LIVE' ? 'live' : mode === 'PAPER' ? 'paper' : '') + (o.status && o.status !== 'OPEN' ? S.chip(o.status === 'SUSPENDED' ? 'Sospeso' : 'Chiuso', o.status === 'SUSPENDED' ? 'red' : '') : '') +
      '<span class="row" style="margin-left:auto;gap:6px;font-size:11px"><span class="mut">Stake</span><span class="seg">' + [2, 5, 10, 25].map(function (v) { return '<button data-act="lad-stake" data-k="' + o.id + '" data-v="' + v + '" aria-pressed="' + (st.stake === v) + '" style="' + (st.stake === v ? 'background:hsl(var(--secondary));color:#111' : '') + '">' + v + '</button>'; }).join('') + '</span><input class="inp" id="lad-st-' + o.id + '" style="width:52px;height:24px" placeholder="€" title="Stake custom (€)">' +
      (on ? '<span class="seg" title="Cosa fa l’ordine al passaggio in-play">' + ['Keep', 'Lapse', 'Take SP'].map(function (v) { return '<button data-act="lad-persist" data-k="' + o.id + '" data-v="' + v + '" aria-pressed="' + (st.persist === v) + '">' + v + '</button>'; }).join('') + '</span><span class="seg" title="LAY: interpreta l’importo come puntata (Stake) o come responsabilità (Liab)">' + ['Stake', 'Liab'].map(function (v) { return '<button data-act="lad-liab" data-k="' + o.id + '" data-v="' + v + '" aria-pressed="' + (st.liab === v) + '">' + v + '</button>'; }).join('') + '</span>' : '') +
      (o.multi !== false ? '<button class="iconbtn" style="width:26px;height:26px" data-act="toast" data-t="✓ Aggiunto al Multi-ladder (2 ladder)" data-d="Apri /multi-ladder." title="Aggiungi questo mercato al workspace Multi-ladder">' + S.icon('grid') + '</button>' : '') +
      (o.popout !== false ? '<button class="iconbtn" style="width:26px;height:26px" data-go="ladder-popout" title="Stacca questo ladder in una finestra dedicata (multi-monitor)">' + S.icon('popout') + '</button>' : '') +
      (on ? '<button class="btn sm ' + (st.oneClick ? (mode === 'LIVE' ? 'danger' : 'gold') : '') + '" data-act="lad-1click" data-k="' + o.id + '" data-m="' + mode + '" style="font-weight:800">⚡ 1-CLICK' + (st.oneClick ? ' ARMATO' : '') + '</button>' : '') +
      '<button class="btn sm" data-act="lad-cols" title="Colonne">' + S.icon('gear') + ' Colonne</button><span class="seg">' + ['Ladder', 'Grid'].map(function (v) { return '<button data-act="lad-view" data-k="' + o.id + '" data-v="' + v + '" aria-pressed="' + (st.view === v) + '">' + v + '</button>'; }).join('') + '</span></span></div>';
    if (on && !o.tennis) h += '<div class="row" style="padding:6px 12px;gap:6px;font-size:10.5px;background:hsl(var(--background)/.5);border-bottom:1px solid hsl(var(--border))">' +
      [['entry', '◎ Entry'], ['offset', 'Offset 3t ☑ green'], ['stop', 'Stop 5t ☐ trail'], ['chase', '↻ Chase 0t'], ['fok', '⏱ FoK 5s'], ['scala', 'Scala 3× 1t']].map(function (t) { return '<button class="chip" style="cursor:pointer;' + (st.tools[t[0]] ? 'background:hsl(var(--secondary)/.25);border-color:hsl(var(--secondary)/.6);color:hsl(var(--secondary))' : '') + '" data-act="lad-tool" data-k="' + o.id + '" data-v="' + t[0] + '">' + t[1] + '</button>'; }).join('') +
      '<button class="chip" style="margin-left:auto;cursor:pointer" data-act="toast" data-t="Servants (macro 1-9)" data-d="Costruisci una macro e richiamala col suo numero sulla selezione puntata.">✨ Servants (0)</button></div>';
    else if (on) h += '<div class="row" style="padding:6px 12px;gap:6px;font-size:10.5px;border-bottom:1px solid hsl(var(--border))"><button class="chip">Scala 3× 1t</button><button class="chip">✨ Servants (0)</button><span class="foot">tennis: niente Entry/Offset/Stop/Chase/FoK</span></div>';
    if (st.oneClick) h += '<div class="strip ' + (mode === 'LIVE' ? 'live' : 'warn') + '" style="border-radius:0;border-left:0;border-right:0">' + (mode === 'LIVE' ? '1-CLICK REALE ATTIVO — ogni clic piazza/annulla con SOLDI VERI senza conferma.' : '1-CLICK SIMULATO ATTIVO — ogni clic piazza/annulla un ordine paper senza conferma.') + '</div>';
    if (o.esito) h += '<div class="foot pos" style="padding:4px 12px">✓ ' + o.esito + '</div>';
    if (st.view === 'Grid') h += S.gridView(o);
    else h += '<div class="row" style="padding:10px;gap:10px;align-items:flex-start;flex-wrap:nowrap;overflow-x:auto">' + o.sels.map(function (s, i) { return selLadder(o.id + '-' + i, s, o.ltps[i], o.sport, o.mine && i === 0); }).join('') + '</div>';
    h += '<div class="row foot" style="justify-content:space-between;padding:6px 12px;border-top:1px solid hsl(var(--border))"><span>' + (mode === 'OFF' ? 'Sola lettura (modalità OFF) · per operare avvia il runner in PAPER/LIVE' : mode === 'LIVE' ? 'Clic = ordine REALE con conferma e proiezione P&L' : 'Clic = ordine simulato con conferma e proiezione P&L (specchio del vivo)') + '</span><span>Aggiornato: 10:41:23 (canale)</span></div></section>';
    return h;
  };
  S.gridView = function (o) {
    var lv = function (p, k) { return Math.round((p + k * (k ? 0.02 : 0)) * 100) / 100; };
    return '<div class="tbl-w" style="padding:8px"><table class="t"><thead><tr><th>Selezione</th><th>P&L</th><th>LTP</th><th colspan="3" style="text-align:center;color:var(--lay)">Lay</th><th colspan="3" style="text-align:center;color:var(--back)">Back</th><th>Stake</th></tr></thead><tbody>' +
      o.sels.map(function (s, i) {
        var l = o.ltps[i];
        return '<tr><td><b>' + s + '</b><div class="foot">LTP ' + S.odds(l) + '</div></td><td class="foot">' + (o.mine && i === 0 ? '<span class="pos">+€0,46</span><br><span class="pos">+€0,46</span>' : '—') + '</td><td>' + S.spark([l * 1.02, l * 1.01, l, l * 0.99, l], 60, 16) + '</td>' +
          [3, 2, 1].map(function (k) { return '<td><span class="o l" data-act="lad-place" data-k="' + o.id + '" data-side="LAY" data-p="' + (l + k * 0.01).toFixed(2) + '" data-sel="' + s + '">' + S.odds(l + k * 0.01) + '<small>€' + (40 * k) + '</small></span></td>'; }).join('') +
          [0, 1, 2].map(function (k) { return '<td><span class="o b" data-act="lad-place" data-k="' + o.id + '" data-side="BACK" data-p="' + (l - k * 0.01).toFixed(2) + '" data-sel="' + s + '">' + S.odds(l - k * 0.01) + '<small>€' + (60 + 30 * k) + '</small></span></td>'; }).join('') +
          '<td><input class="inp" id="grid-st-' + o.id + i + '" value="2" style="width:52px;height:24px"></td></tr>';
      }).join('') + '</tbody></table><div class="foot" style="padding:6px 2px">book% lay 100,8 · back 99,4</div></div>';
  };
  S.on('lad-stake', function (t) { LS(t.dataset.k).stake = +t.dataset.v; S.rerender(); });
  S.on('lad-persist', function (t) { LS(t.dataset.k).persist = t.dataset.v; S.rerender(); });
  S.on('lad-liab', function (t) { LS(t.dataset.k).liab = t.dataset.v; S.rerender(); });
  S.on('lad-view', function (t) { LS(t.dataset.k).view = t.dataset.v; S.rerender(); });
  S.on('lad-tool', function (t) { var x = LS(t.dataset.k).tools; x[t.dataset.v] = !x[t.dataset.v]; S.rerender(); });
  S.on('lad-cols', function () { S.toast('Colonne · profilo per sport', 'Mostra/nascondi e ordina: Mio LAY, Banco LAY, Quota (fissa), Banco BACK, Mio BACK, P&L, EV, TRD, PIQ. Reset per il layout predefinito.'); });
  S.on('lad-cancel', function () { S.toast('Annulla ordini al livello', 'Con conferma (scade dopo 6 s).'); });
  S.on('lad-cashout', function () { S.toast('Cash-out COMPLETO della selezione', 'Annulla i resting, poi hedge dalle esposizioni reali.'); });
  S.on('lad-1click', function (t) {
    var st = LS(t.dataset.k), live = t.dataset.m === 'LIVE';
    if (st.oneClick) { st.oneClick = false; S.rerender(); return; }
    S.modal({ danger: live, title: live ? '1-CLICK REALE' : '1-CLICK SIMULATO (paper)', body: live ? 'Ogni clic su BACK/LAY o sui tuoi ordini piazzerà/annullerà un ordine con SOLDI VERI SENZA ulteriore conferma. Attivare?' : 'Ogni clic piazzerà/annullerà un ordine SIMULATO senza ulteriore conferma — identico al vivo, ma senza soldi veri. Attivare?', ok: 'Attiva', onOk: function () { st.oneClick = true; S.rerender(); } });
  });
  S.on('lad-place', function (t) {
    var key = t.dataset.k.replace(/-\d+$/, ''), st = LS(t.dataset.k.split('-').length > 2 ? t.dataset.k : key);
    var root = t.closest('[data-ladder]'), mode = root ? (root.querySelector('.chip.live') ? 'LIVE' : root.querySelector('.chip.paper') ? 'PAPER' : 'OFF') : 'PAPER';
    if (mode === 'OFF') { S.toast('Sola lettura: modalità OFF', 'Il clic evidenzia il livello, nessun ordine.'); return; }
    var p = parseFloat(t.dataset.p), side = t.dataset.side, stake = (S.ui.lad[key] || {}).stake || 5;
    var win = side === 'BACK' ? stake * (p - 1) : stake, lose = side === 'BACK' ? -stake : -stake * (p - 1);
    if ((S.ui.lad[key] || {}).oneClick) { S.toast((mode === 'LIVE' ? 'REALE' : 'SIMULATO') + ': ' + side + ' €' + stake + ' @ ' + p, 'Prototipo: nessun ordine inviato.'); return; }
    S.modal({ danger: mode === 'LIVE', title: '🛡 ' + side + ' @ ' + p + ' ' + t.dataset.sel + ' <span class="chip ' + (mode === 'LIVE' ? 'live' : 'paper') + '">' + (mode === 'LIVE' ? 'REALE' : 'SIMULATO') + '</span>',
      body: '<label class="field" for="pc-imp">Importo (€)<input id="pc-imp" value="' + stake + '"></label><div class="grid g2" style="margin-top:8px">' + S.kpi('Se vince', '<span class="' + S.tone(win) + '">' + S.money(win, { signed: true }) + '</span>') + S.kpi('Se perde', '<span class="' + S.tone(lose) + '">' + S.money(lose, { signed: true }) + '</span>') + '</div><p class="foot">Responsabilità: <b>' + S.money(side === 'LAY' ? stake * (p - 1) : stake) + '</b> · persistenza ' + ((S.ui.lad[key] || {}).persist || 'Lapse') + '</p><p class="foot">' + (mode === 'LIVE' ? 'Ordine con SOLDI VERI: verrà inviato a Betfair alla conferma.' : 'Ordine simulato (paper): identico al vivo, ma senza soldi veri.') + '</p>',
      ok: mode === 'LIVE' ? '✓ Conferma REALE' : '✓ Conferma simulato', cancel: '✕ Annulla', onOk: function () { S.toast('✓ ' + side + ' €' + stake + ' @ ' + p, 'Prototipo: nessun ordine inviato.'); } });
  });
})();
