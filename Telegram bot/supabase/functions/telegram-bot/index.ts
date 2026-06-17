// Web Editor non supporta import relativi non validi
// import "@supabase/functions-js/edge-runtime.d.ts"
import { Bot, webhookCallback, InlineKeyboard } from "https://esm.sh/grammy@1.30.0";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.39.3";
import { evalTotal, evalScore, isTotal, SCORE_MARKETS, type MarketPrice } from "./calc.ts";

console.log("Loading Telegram Bot Edge Function...");

// Map of leagues provided by user
const LEAGUES = {
  135: "🇮🇹 Serie A",
  136: "🇮🇹 Serie B",
  39: "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League",
  140: "🇪🇸 La Liga",
  61: "🇫🇷 Ligue 1",
  78: "🇩🇪 Bundesliga",
  2: "🇪🇺 Champions League",
  3: "🇪🇺 Europa League",
  848: "🇪🇺 Conference League",
} as const;

// Bandiera per league_id (generata da league_names.csv: 209 leghe; fallback ⚽ per sconosciute)
const LEAGUE_FLAG: Record<number, string> = {1:"🌍",2:"🌍",3:"🌍",5:"🌍",10:"🌍",11:"🌍",13:"🌍",14:"🌍",16:"🌍",17:"🌍",32:"🌍",35:"🌍",37:"🌍",39:"🏴󠁧󠁢󠁥󠁮󠁧󠁿",40:"🏴󠁧󠁢󠁥󠁮󠁧󠁿",41:"🏴󠁧󠁢󠁥󠁮󠁧󠁿",42:"🏴󠁧󠁢󠁥󠁮󠁧󠁿",43:"🏴󠁧󠁢󠁥󠁮󠁧󠁿",45:"🏴󠁧󠁢󠁥󠁮󠁧󠁿",46:"🏴󠁧󠁢󠁥󠁮󠁧󠁿",47:"🏴󠁧󠁢󠁥󠁮󠁧󠁿",48:"🏴󠁧󠁢󠁥󠁮󠁧󠁿",50:"🏴󠁧󠁢󠁥󠁮󠁧󠁿",61:"🇫🇷",62:"🇫🇷",66:"🇫🇷",71:"🇧🇷",72:"🇧🇷",73:"🇧🇷",78:"🇩🇪",79:"🇩🇪",80:"🇩🇪",81:"🇩🇪",88:"🇳🇱",89:"🇳🇱",90:"🇳🇱",94:"🇵🇹",95:"🇵🇹",96:"🇵🇹",104:"🇳🇴",105:"🇳🇴",106:"🇵🇱",107:"🇵🇱",108:"🇵🇱",110:"🏴󠁧󠁢󠁷󠁬󠁳󠁿",113:"🇸🇪",114:"🇸🇪",115:"🇸🇪",119:"🇩🇰",120:"🇩🇰",122:"🇩🇰",128:"🇦🇷",129:"🇦🇷",130:"🇦🇷",131:"🇦🇷",135:"🇮🇹",136:"🇮🇹",137:"🇮🇹",138:"🇮🇹",140:"🇪🇸",141:"🇪🇸",142:"🇪🇸",143:"🇪🇸",144:"🇧🇪",145:"🇧🇪",162:"🇨🇷",165:"🇮🇸",167:"🇮🇸",168:"🇮🇸",169:"🇨🇳",172:"🇧🇬",174:"🇧🇬",179:"🏴󠁧󠁢󠁳󠁣󠁴󠁿",180:"🏴󠁧󠁢󠁳󠁣󠁴󠁿",183:"🏴󠁧󠁢󠁳󠁣󠁴󠁿",184:"🏴󠁧󠁢󠁳󠁣󠁴󠁿",186:"🇩🇿",187:"🇩🇿",188:"🇦🇺",197:"🇬🇷",200:"🇲🇦",201:"🇲🇦",202:"🇹🇳",203:"🇹🇷",204:"🇹🇷",205:"🇹🇷",206:"🇹🇷",207:"🇨🇭",208:"🇨🇭",210:"🇭🇷",211:"🇭🇷",218:"🇦🇹",219:"🇦🇹",220:"🇦🇹",233:"🇪🇬",234:"🇭🇳",239:"🇨🇴",240:"🇨🇴",242:"🇪🇨",244:"🇫🇮",245:"🇫🇮",246:"🇫🇮",250:"🇵🇾",253:"🇺🇸",254:"🇺🇸",257:"🇺🇸",262:"🇲🇽",266:"🇨🇱",268:"🇺🇾",271:"🇭🇺",276:"🇰🇪",278:"🇲🇾",281:"🇵🇪",283:"🇷🇴",285:"🇷🇴",286:"🇷🇸",287:"🇷🇸",292:"🇰🇷",293:"🇰🇷",296:"🇹🇭",299:"🇻🇪",304:"🇵🇦",305:"🇶🇦",307:"🇸🇦",314:"🇧🇦",322:"🇯🇲",323:"🇮🇳",326:"🇬🇪",328:"🇪🇪",329:"🇪🇪",330:"🇰🇼",332:"🇸🇰",333:"🇺🇦",334:"🇺🇦",335:"🇺🇦",339:"🇬🇹",342:"🇦🇲",344:"🇧🇴",345:"🇨🇿",346:"🇨🇿",347:"🇨🇿",348:"🇨🇿",357:"🇮🇪",358:"🇮🇪",361:"🇱🇹",362:"🇱🇹",365:"🇱🇻",368:"🇸🇬",373:"🇸🇮",375:"🇸🇮",380:"🇭🇰",382:"🇮🇱",383:"🇮🇱",393:"🇲🇹",408:"🇬🇧",417:"🇧🇭",418:"🇦🇿",419:"🇦🇿",420:"🇦🇿",427:"🇮🇹",429:"🇮🇹",430:"🇮🇹",434:"🇮🇹",435:"🇪🇸",436:"🇪🇸",475:"🇧🇷",476:"🇧🇷",496:"🇮🇱",511:"🇹🇳",525:"🌍",563:"🇸🇪",564:"🇸🇪",592:"🇸🇪",593:"🇸🇪",594:"🇸🇪",595:"🇸🇪",596:"🇸🇪",597:"🇸🇪",612:"🇧🇷",624:"🇧🇷",660:"🇰🇷",664:"🇽🇰",666:"🌍",667:"🌍",680:"🇸🇰",704:"🇮🇹",705:"🇮🇹",714:"🇪🇬",722:"🇲🇽",756:"🇲🇰",848:"🌍",850:"🌍",875:"🇪🇸",876:"🇪🇸",877:"🇪🇸",878:"🇪🇸",886:"🌍",891:"🇮🇹",893:"🌍",928:"🌍",942:"🇮🇹",943:"🇮🇹",976:"🇮🇹",1006:"🇪🇸",1010:"🇨🇿",1128:"🇧🇷",1191:"🌍",1207:"🌍",1220:"🇨🇱"};

const botToken = Deno.env.get("TELEGRAM_BOT_TOKEN");
if (!botToken) {
  throw new Error("TELEGRAM_BOT_TOKEN is not set!");
}

const bot = new Bot(botToken);

// Helper Supabase + range "oggi" (riusa lo stesso pattern degli altri handler)
function getSupabase() {
  const url = Deno.env.get("SUPABASE_URL") ?? Deno.env.get("MY_DB_URL");
  const key = Deno.env.get("SUPABASE_ANON_KEY") ?? Deno.env.get("MY_DB_KEY");
  if (!url || !key) throw new Error("Credenziali Supabase mancanti (SUPABASE_URL / SUPABASE_ANON_KEY)");
  return createClient(url, key);
}
// Range "oggi" calcolato sul giorno solare ITALIANO (Europe/Rome) ma espresso in UTC per la query
// (fixture_date è in UTC). Gestisce l'ora legale (offset ricavato dall'istante reale).
function todayRangeISO() {
  const now = new Date();
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Rome", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).formatToParts(now);
  const g = (t: string) => Number(parts.find((p) => p.type === t)?.value);
  const romeWallNow = Date.UTC(g("year"), g("month") - 1, g("day"), g("hour"), g("minute"), g("second"));
  const offsetMs = romeWallNow - now.getTime();           // +1h o +2h secondo DST
  const startUTC = Date.UTC(g("year"), g("month") - 1, g("day"), 0, 0, 0) - offsetMs;
  const endUTC = startUTC + 24 * 3600 * 1000;
  return { todayStr: new Date(startUTC).toISOString(), tomorrowStr: new Date(endUTC).toISOString() };
}

// Create the main menu keyboard
const mainMenuKeyboard = new InlineKeyboard()
  .text("📅 Partite del giorno", "menu_today").row()
  .text("🎯 HT Sniper", "menu_ht_sniper").row()
  .text("📊 Predictions", "menu_predictions").row()
  .text("🧮 Calcolatore Valore", "menu_calc");

// Create the predictions (leagues) keyboard
const leaguesKeyboard = new InlineKeyboard()
  .text(LEAGUES[135], "league_135").text(LEAGUES[136], "league_136").row()
  .text(LEAGUES[39], "league_39").text(LEAGUES[140], "league_140").row()
  .text(LEAGUES[61], "league_61").text(LEAGUES[78], "league_78").row()
  .text(LEAGUES[2], "league_2").text(LEAGUES[3], "league_3").row()
  .text(LEAGUES[848], "league_848").row()
  .text("🔙 Torna al Menù", "menu_main");

// Back button keyboard for individual reports
const backToMainKeyboard = new InlineKeyboard()
  .text("🔙 Torna al Menù", "menu_main");

// ===================== CALCOLATORE VALORE =====================
const calcMarketKeyboard = new InlineKeyboard()
  .text("Over 1.5", "calc_O15").text("Under 1.5", "calc_U15").text("Over 2.5", "calc_O25").row()
  .text("Under 2.5", "calc_U25").text("Over 3.5", "calc_O35").text("Under 3.5", "calc_U35").row()
  .text("Over 0.5 HT", "calc_HT05").text("Under 0.5 HT", "calc_HT_U05").row()
  .text("1 (Casa)", "calc_H").text("X (Pari)", "calc_D").text("2 (Trasf)", "calc_A").row()
  .text("1X", "calc_DC_1X").text("12", "calc_DC_12").text("X2", "calc_DC_X2").row()
  .text("DNB Casa", "calc_DNB_H").text("DNB Trasf", "calc_DNB_A").row()
  .text("Goal", "calc_BTTS").text("No Goal", "calc_BTTS_NO").row()
  .text("1 HT", "calc_HT_H").text("X HT", "calc_HT_D").text("2 HT", "calc_HT_A").row()
  .text("🔙 Menù", "menu_main");

const MKT_NAMES: Record<string, string> = {
  O15: "Over 1.5", U15: "Under 1.5", O25: "Over 2.5", U25: "Under 2.5", O35: "Over 3.5", U35: "Under 3.5",
  HT05: "Over 0.5 HT", HT_U05: "Under 0.5 HT",
  H: "1 (Casa)", D: "X (Pareggio)", A: "2 (Trasferta)", BTTS: "Goal (BTTS)", BTTS_NO: "No Goal",
  DC_1X: "1X", DC_X2: "X2", DC_12: "12", DNB_H: "Casa (DNB)", DNB_A: "Trasferta (DNB)",
  HT_H: "1 Primo Tempo", HT_D: "X Primo Tempo", HT_A: "2 Primo Tempo",
};

function fmtResult(mp: MarketPrice, title: string): string {
  if (!Number.isFinite(mp.prob) || mp.prob < 1e-6 || mp.prob > 1 - 1e-6)
    return `🧮 ${title}\nMercato già determinato: nessun valore da calcolare.`;
  return `🧮 *${title}*\n` +
    `Probabilità reale: *${(mp.prob * 100).toFixed(1)}%*\n` +
    `Quota FAIR: *${mp.fairOdds.toFixed(2)}*\n` +
    `✅ BACK se quota live ≥ *${mp.minBack.toFixed(2)}*\n` +
    `✅ LAY se quota live ≤ *${mp.maxLay.toFixed(2)}*`;
}

function handleCalcTotal(ctx: any) {
  const args = String(ctx.match || "").trim().split(/\s+/).filter(Boolean);
  if (args.length < 4)
    return ctx.reply("Formato: /calc <mercato> <quota_prematch> <minuto> <gol> [quota_opposta]\nEs: `/calc U35 1.30 8 1`", { parse_mode: "Markdown" });
  const market = args[0].toUpperCase();
  const q0 = parseFloat(args[1]), minute = parseFloat(args[2]), goals = parseInt(args[3], 10);
  const qOpp = args[4] ? parseFloat(args[4]) : undefined;
  if (!isTotal(market))
    return ctx.reply(`'${market}' non è un mercato a gol totali. Per 1X2/BTTS usa /scalc.`);
  if (market.startsWith("HT") && minute > 45)
    return ctx.reply("Mercati HT: minuto 0-45 e SOLO i gol del 1° tempo (il primo tempo è finito).");
  if (!Number.isFinite(q0) || q0 <= 1 || !Number.isFinite(minute) || minute < 0 || minute > 130 ||
      !Number.isInteger(goals) || goals < 0)
    return ctx.reply("Numeri non validi (quota>1, minuto 0-130, gol≥0). Es: `/calc U35 1.30 8 1`", { parse_mode: "Markdown" });
  if (qOpp !== undefined && (!Number.isFinite(qOpp) || qOpp <= 1))
    return ctx.reply("Quota opposta non valida (deve essere > 1).");
  try {
    const mp = evalTotal(market, q0, qOpp, minute, goals);
    return ctx.reply(fmtResult(mp, `${MKT_NAMES[market] || market} — ${minute}' / ${goals} gol`), { parse_mode: "Markdown" });
  } catch (e) {
    return ctx.reply(`⚠️ ${(e as Error).message || e}`);
  }
}

function handleCalcScore(ctx: any) {
  const args = String(ctx.match || "").trim().split(/\s+/).filter(Boolean);
  if (args.length < 8)
    return ctx.reply("Formato: /scalc <mercato> <qHome> <qDraw> <qAway> <qOver2.5> <qUnder2.5> <minuto> <golCasa>-<golTrasf>\nEs: `/scalc H 2.10 3.40 3.60 1.90 2.00 30 1-0`", { parse_mode: "Markdown" });
  const market = args[0].toUpperCase();
  const qH = parseFloat(args[1]), qD = parseFloat(args[2]), qA = parseFloat(args[3]);
  const qO = parseFloat(args[4]), qU = parseFloat(args[5]), minute = parseFloat(args[6]);
  const sc = (args[7] || "").split("-");
  const gh = parseInt(sc[0], 10), ga = parseInt(sc[1], 10);
  if (!SCORE_MARKETS.has(market))
    return ctx.reply(`'${market}' non è un mercato 1X2/BTTS supportato. Per i totali usa /calc.`);
  if (![qH, qD, qA, qO, qU].every((x) => Number.isFinite(x) && x > 1) ||
      !Number.isFinite(minute) || minute < 0 || minute > 130 ||
      !Number.isInteger(gh) || gh < 0 || !Number.isInteger(ga) || ga < 0)
    return ctx.reply("Numeri o punteggio non validi (quote>1, minuto 0-130, punteggio es. `1-0`).", { parse_mode: "Markdown" });
  if (market.startsWith("HT_") && minute > 45)
    return ctx.reply("Mercati 1X2 primo tempo: il minuto deve essere 0-45 (primo tempo in corso); le quote restano quelle FT.");
  try {
    const mp = evalScore(market, qH, qD, qA, qO, qU, minute, gh, ga);
    return ctx.reply(fmtResult(mp, `${MKT_NAMES[market] || market} — ${minute}' / ${gh}-${ga}`), { parse_mode: "Markdown" });
  } catch (e) {
    return ctx.reply(`⚠️ ${(e as Error).message || e}`);
  }
}

bot.command("calc", handleCalcTotal);
bot.command("scalc", handleCalcScore);

bot.command("start", (ctx) => {
  return ctx.reply("Bentornato su Alpha Score! 🚀\nScegli cosa vuoi visualizzare oggi:", {
    reply_markup: mainMenuKeyboard,
  });
});

bot.command("partite", (ctx) => {
  return ctx.reply("Scegli un'opzione dal menù principale:", {
    reply_markup: mainMenuKeyboard,
  });
});

// Handle button clicks
bot.on("callback_query:data", async (ctx) => {
  const data = ctx.callbackQuery.data;

  // Navigazione Menù Principale
  if (data === "menu_main") {
    await ctx.answerCallbackQuery();
    return ctx.editMessageText("Bentornato su Alpha Score! 🚀\nScegli cosa vuoi visualizzare oggi:", {
      reply_markup: mainMenuKeyboard,
    });
  }

  // Sottomenù Predictions (Leghe)
  if (data === "menu_predictions") {
    await ctx.answerCallbackQuery();
    return ctx.editMessageText("Seleziona una lega per vedere le previsioni di oggi:", {
      reply_markup: leaguesKeyboard,
    });
  }

  // Calcolatore Valore — menù mercati
  if (data === "menu_calc") {
    await ctx.answerCallbackQuery();
    return ctx.editMessageText(
      "🧮 *Calcolatore Valore (live)*\nScegli il mercato per vedere il formato del comando:",
      { parse_mode: "Markdown", reply_markup: calcMarketKeyboard }
    );
  }

  // Calcolatore Valore — mercato scelto -> mostra il template del comando
  if (data.startsWith("calc_")) {
    await ctx.answerCallbackQuery();
    const mk = data.slice(5);
    const name = MKT_NAMES[mk] || mk;
    let msg: string;
    if (isTotal(mk)) {
      const isHT = mk.startsWith("HT");
      const goalsLabel = isHT ? "<gol_1°tempo>" : "<gol_totali>";
      const note = isHT
        ? `⚠️ Mercato 1° tempo: minuto 0-45 e SOLO i gol del primo tempo.`
        : `(facoltativo: aggiungi la quota OPPOSTA in fondo per il de-vig)`;
      msg = `🧮 *${name}* — mercato a gol totali\n\n` +
        `Scrivi:\n\`/calc ${mk} <quota_prematch> <minuto> ${goalsLabel}\`\n\n` +
        `Esempio:\n\`/calc ${mk} 1.30 8 1\`\n\n${note}`;
    } else {
      const isHT = mk.startsWith("HT_");
      const tipo = isHT ? "1X2 PRIMO TEMPO" : "1X2/BTTS";
      const esempio = isHT ? `/scalc ${mk} 2.10 3.40 3.60 1.90 2.00 30 0-0` : `/scalc ${mk} 2.10 3.40 3.60 1.90 2.00 30 1-0`;
      const htNote = isHT ? `\n\n⚠️ Primo tempo: minuto *0-45* e punteggio del *PRIMO TEMPO*. Le quote 1X2/OU sono quelle FT (di fine partita).` : "";
      msg = `🧮 *${name}* — mercato ${tipo}\n\n` +
        `Scrivi:\n\`/scalc ${mk} <qHome> <qDraw> <qAway> <qOver2.5> <qUnder2.5> <minuto> <golCasa>-<golTrasf>\`\n\n` +
        `Esempio:\n\`${esempio}\`${htNote}`;
    }
    return ctx.reply(msg, { parse_mode: "Markdown", reply_markup: backToMainKeyboard });
  }

  // 📅 Partite del giorno — conteggio + leghe (con bandiera)
  if (data === "menu_today") {
    await ctx.answerCallbackQuery();
    try {
      const supabase = getSupabase();
      const { todayStr, tomorrowStr } = todayRangeISO();
      const { data: rows, error } = await supabase
        .from("fixture_predictions")
        .select("league_id, league_name")
        .gte("fixture_date", todayStr)
        .lt("fixture_date", tomorrowStr);
      if (error) throw error;
      const byLeague = new Map<number, { name: string; count: number }>();
      for (const r of rows || []) {
        const e = byLeague.get(r.league_id) || { name: r.league_name || `Lega ${r.league_id}`, count: 0 };
        e.count++;
        byLeague.set(r.league_id, e);
      }
      const total = (rows || []).length;
      if (total === 0)
        return ctx.editMessageText("📅 Nessuna partita prevista per oggi.", { reply_markup: backToMainKeyboard });
      const kb = new InlineKeyboard();
      const sorted = [...byLeague.entries()].sort((a, b) => a[1].name.localeCompare(b[1].name));
      const MAX_LEAGUE_BTN = 95;                 // sotto il limite Telegram di 100 pulsanti
      const shown = sorted.slice(0, MAX_LEAGUE_BTN);
      shown.forEach(([id, e]) => kb.text(`${LEAGUE_FLAG[id] || "⚽"} ${e.name} (${e.count})`, `today_lg_${id}`).row());
      kb.text("🔙 Menù", "menu_main");
      const extra = sorted.length > MAX_LEAGUE_BTN ? `\n(mostrate le prime ${MAX_LEAGUE_BTN} leghe di ${sorted.length})` : "";
      return ctx.editMessageText(
        `📅 *Partite del giorno*: *${total}* partite in *${byLeague.size}* leghe.\nScegli una lega:${extra}`,
        { parse_mode: "Markdown", reply_markup: kb }
      );
    } catch (e) {
      console.error("[BOT] menu_today error", e);
      return ctx.editMessageText("❌ Errore nel recupero delle partite del giorno.", { reply_markup: backToMainKeyboard });
    }
  }

  // 📅 Partite di una lega oggi (per orario)
  if (data.startsWith("today_lg_")) {
    await ctx.answerCallbackQuery();
    const lid = parseInt(data.slice("today_lg_".length), 10);
    try {
      const supabase = getSupabase();
      const { todayStr, tomorrowStr } = todayRangeISO();
      const { data: ms, error } = await supabase
        .from("fixture_predictions")
        .select("fixture_id, home_team_name, away_team_name, fixture_date, league_name")
        .eq("league_id", lid)
        .gte("fixture_date", todayStr)
        .lt("fixture_date", tomorrowStr)
        .order("fixture_date", { ascending: true });
      if (error) throw error;
      if (!ms || ms.length === 0)
        return ctx.editMessageText("Nessuna partita per questa lega oggi.", {
          reply_markup: new InlineKeyboard().text("🔙 Leghe", "menu_today"),
        });
      const kb = new InlineKeyboard();
      const MAX_MATCH_BTN = 80;                  // sotto il limite Telegram di 100 pulsanti
      const visible = ms.slice(0, MAX_MATCH_BTN);
      for (const m of visible) {
        let t = "--:--";
        try {
          if (m.fixture_date)
            t = new Date(m.fixture_date).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Rome" });
        } catch (_e) { /* orario non disponibile */ }
        const label = `${t}  ${m.home_team_name || "?"} - ${m.away_team_name || "?"}`.slice(0, 60);
        kb.text(label, `today_m_${m.fixture_id}`).row();
      }
      if (ms.length > MAX_MATCH_BTN)
        kb.text(`…altre ${ms.length - MAX_MATCH_BTN} partite (usa la dashboard)`, "menu_today").row();
      kb.text("🔙 Leghe", "menu_today");
      const name = ms[0].league_name || `Lega ${lid}`;
      return ctx.editMessageText(`${LEAGUE_FLAG[lid] || "⚽"} *${name}* — partite di oggi (orario IT):`, {
        parse_mode: "Markdown",
        reply_markup: kb,
      });
    } catch (e) {
      console.error("[BOT] today_lg error", e);
      return ctx.editMessageText("❌ Errore nel recupero delle partite.", {
        reply_markup: new InlineKeyboard().text("🔙 Leghe", "menu_today"),
      });
    }
  }

  // 📅 Scheda partita -> link alla dashboard frontend
  if (data.startsWith("today_m_")) {
    await ctx.answerCallbackQuery();
    const fid = data.slice("today_m_".length);
    const url = `https://python-database-automation.vercel.app/dashboard?fixture=${encodeURIComponent(fid)}`;
    const kb = new InlineKeyboard().url("📊 Apri scheda completa", url);
    return ctx.reply("Ecco la scheda completa della partita 👇", { reply_markup: kb });
  }
  // NB: today_m_ usa reply (non editMessageText) perché i bottoni .url() non sono ammessi nei
  // messaggi modificati; la lista resta visibile per scegliere un'altra partita.

  // HT Sniper Query
  if (data === "menu_ht_sniper") {
    console.log(`[BOT] User requested HT Sniper`);
    await ctx.answerCallbackQuery({ text: `Ricerca segnali Elite HT...` });

    // Configura Supabase
    const supabaseUrl = Deno.env.get("SUPABASE_URL") ?? Deno.env.get("MY_DB_URL");
    const supabaseKey = Deno.env.get("SUPABASE_ANON_KEY") ?? Deno.env.get("MY_DB_KEY");

    if (!supabaseUrl || !supabaseKey) {
      console.error("[BOT] Missing DB credentials!");
      await ctx.reply("Errore di sistema: Credenziali database non trovate nel server.");
      return;
    }

    const supabase = createClient(supabaseUrl, supabaseKey);

    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const todayStr = today.toISOString();

    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomorrowStr = tomorrow.toISOString();

    let waitMsg;
    try {
      waitMsg = await ctx.reply(`🎯 Sto cercando i segnali Elite HT per oggi...`);
    } catch (e) {
      console.error("[BOT] Failed to send wait message", e);
    }

    try {
      // HT Sniper Query
      const { data: matches, error } = await supabase
        .from("fixture_predictions")
        .select(`
          fixture_id,
          home_team_name,
          away_team_name,
          fixture_date,
          ht_predictions
        `)
        .gte("fixture_date", todayStr)
        .lt("fixture_date", tomorrowStr)
        .not("ht_predictions", "is", null)
        .order("fixture_date", { ascending: true });

      if (error) throw error;

      // Filtra solo le Elite in memoria (visto che JSON filter in query è complesso)
      const eliteMatches = (matches || []).filter(m => {
        if (!m.ht_predictions) return false;
        // Supponendo the l'oggetto JSON sia già passato come object
        const ht = typeof m.ht_predictions === 'string' ? JSON.parse(m.ht_predictions) : m.ht_predictions;
        return ht.is_elite === true;
      });

      if (waitMsg) {
        try { await ctx.api.deleteMessage(ctx.chat!.id, waitMsg.message_id); } catch (e) { }
      }

      if (eliteMatches.length === 0) {
        await ctx.reply(`Nessun segnale HT Sniper trovato per oggi.`, { reply_markup: backToMainKeyboard });
        return;
      }

      await ctx.reply(`🎯 <b>HT SNIPER - SEGALI ELITE DI OGGI</b>\nTrovati ${eliteMatches.length} segnali purificati.`, { parse_mode: "HTML" });

      for (const match of eliteMatches) {
        let dateStr = "N/D", timeStr = "N/D";
        if (match.fixture_date) {
          const matchDate = new Date(match.fixture_date);
          dateStr = `${matchDate.getDate().toString().padStart(2, '0')}/${(matchDate.getMonth() + 1).toString().padStart(2, '0')}`;
          timeStr = `${matchDate.getHours().toString().padStart(2, '0')}:${matchDate.getMinutes().toString().padStart(2, '0')}`;
        }

        const ht = typeof match.ht_predictions === 'string' ? JSON.parse(match.ht_predictions) : match.ht_predictions;
        const prob = ht.hybrid_prob ? (ht.hybrid_prob * 100).toFixed(1) : '?';
        const lambda = ht.lambda_1h ? ht.lambda_1h.toFixed(2) : '?';
        const f = ht.details?.freq ? (ht.details.freq * 100).toFixed(0) : '?';
        const p = ht.details?.poisson ? (ht.details.poisson * 100).toFixed(0) : '?';

        const text = `
🎯 <b>HT SNIPER: OVER 0.5 1° TEMPO</b>
<b>🏟 ${match.home_team_name} vs ${match.away_team_name}</b>
⏰ Oggi alle ${timeStr}

📊 <b>Metriche del Modello Ibrido:</b>
✅ <b>Probabilità Globale:</b> ${prob}%
<i>(Calcolata incrociando la frequenza storica con la stima matematica attuale)</i>

✅ <b>Intensità Offensiva (Lambda):</b> ${lambda}
<i>(La forza d'attacco nel 1° tempo. Valori sopra 1.57 indicano alta probensione al gol)</i>

🔍 <b>Analisi Dettagliata:</b> Storicamente questo evento si è verificato nel ${f}% dei match recenti. L'analisi Poisson stima una forza d'attacco attuale pari al ${p}%.
`;
        await ctx.reply(text, { parse_mode: "HTML", reply_markup: backToMainKeyboard });
      }

    } catch (err) {
      console.error(`[HT SNIPER] Error:`, err);
      await ctx.reply(`❌ Errore durante la ricerca HT Sniper.`, { reply_markup: backToMainKeyboard });
    }
    return;
  }

  // Risoluzione League
  if (data.startsWith("league_")) {
    const leagueId = parseInt(data.replace("league_", ""));
    const leagueName = LEAGUES[leagueId as keyof typeof LEAGUES];

    console.log(`[BOT] User requested data for league: ${leagueName} (ID: ${leagueId})`);

    // Mostriamo all'utente che stiamo caricando
    await ctx.answerCallbackQuery({ text: `Ricerca partite per ${leagueName}...` });

    // Configura Supabase (usaimo le variabili di sistema automatiche di Supabase)
    const supabaseUrl = Deno.env.get("SUPABASE_URL") ?? Deno.env.get("MY_DB_URL");
    const supabaseKey = Deno.env.get("SUPABASE_ANON_KEY") ?? Deno.env.get("MY_DB_KEY");

    if (!supabaseUrl || !supabaseKey) {
      console.error("[BOT] Missing DB credentials!");
      await ctx.reply("Errore di sistema: Credenziali database non trovate nel server.");
      return;
    }

    const supabase = createClient(supabaseUrl, supabaseKey);

    // Calcoliamo la data di oggi in formato stringa per la query
    const today = new Date();
    today.setHours(0, 0, 0, 0); // Inizio giornata (UTC)
    const todayStr = today.toISOString();

    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomorrowStr = tomorrow.toISOString();

    console.log(`[BOT] Querying database for dates between ${todayStr} and ${tomorrowStr}`);

    // Inviamo primo messaggio di attesa
    let waitMsg;
    try {
      waitMsg = await ctx.reply(`🔍 Sto cercando le partite di ${leagueName} per oggi...`);
    } catch (e) {
      console.error("[BOT] Failed to send wait message", e);
    }

    try {
      // Query alla tabella fixture_predictions
      console.log(`[DB] Executing query on fixture_predictions for league_id=${leagueId}`);
      const { data: matches, error } = await supabase
        .from("fixture_predictions")
        .select(`
          fixture_id,
          home_team_name,
          away_team_name,
          fixture_date,
          advice,
          goals_home_line,
          goals_away_line,
          db_json_analisi,
          model_predictions_json
        `)
        .eq("league_id", leagueId)
        .gte("fixture_date", todayStr)
        .lt("fixture_date", tomorrowStr)
        .order("fixture_date", { ascending: true });

      if (error) {
        console.error("[DB] Supabase query error:", error.message, error.details, error.hint);
        throw error;
      }

      console.log(`[DB] Query successful. Found ${matches?.length || 0} matches.`);

      // Elimina il messaggio di attesa
      if (waitMsg) {
        try {
          await ctx.api.deleteMessage(ctx.chat!.id, waitMsg.message_id);
        } catch (e) {
          console.error("[BOT] Could not delete wait message", e);
        }
      }

      if (!matches || matches.length === 0) {
        console.log(`[BOT] No matches found for ${leagueName}. Notifying user.`);
        await ctx.reply(`Nessuna partita trovata oggi per ${leagueName}.`, { reply_markup: backToMainKeyboard });
        return;
      }

      // Helper per formattare specificamente l'analisi del database (markets, inputs etc.) in modo "umano" e in italiano
      const formatDbAnalysis = (parsedData: any): string => {
        let output = "";

        if (parsedData.markets) {
          output += `\n📈 <b>Probabilità Matematiche:</b>\n`;
          const m = parsedData.markets;
          if (m['1x2']) {
            output += `   • <b>Esito Finale:</b> 1 (${(m['1x2'].H * 100).toFixed(0)}%) | X (${(m['1x2'].D * 100).toFixed(0)}%) | 2 (${(m['1x2'].A * 100).toFixed(0)}%)\n`;
          }
          if (m.btts) {
            // btts = Both Teams to Score (Gol / No Gol)
            output += `   • <b>Gol/No Gol:</b> Gol (${(m.btts.True * 100).toFixed(0)}%) | No Gol (${(m.btts.False * 100).toFixed(0)}%)\n`;
          }
          if (m.over_2_5) {
            output += `   • <b>Under/Over 2.5:</b> Over (${(m.over_2_5.True * 100).toFixed(0)}%) | Under (${(m.over_2_5.False * 100).toFixed(0)}%)\n`;
          }
          if (m.first_half_over_0_5) {
            // 1st half over 0.5 (Almeno 1 gol nel primo tempo)
            output += `   • <b>Gol 1° Tempo (> 0.5):</b> Si (${(m.first_half_over_0_5.True * 100).toFixed(0)}%) | No (${(m.first_half_over_0_5.False * 100).toFixed(0)}%)\n`;
          }
        }

        if (parsedData.inputs || parsedData.coverage) {
          output += `\n⚙️ <b>Metriche del Modello:</b>\n`;
          if (parsedData.inputs) {
            const i = parsedData.inputs;
            // lambda è concettualmente i gol attesi
            if (i.lambda_home !== undefined && i.lambda_away !== undefined) {
              output += `   • <b>Gol Attesi (Forza Offensiva):</b> Casa ${i.lambda_home.toFixed(2)} | Ospiti ${i.lambda_away.toFixed(2)}\n`;
            }
            // Media campionati
            if (i.league_home_avg !== undefined && i.league_away_avg !== undefined) {
              output += `   • <b>Media Gol Campionato:</b> Casa ${i.league_home_avg.toFixed(2)} | Ospiti ${i.league_away_avg.toFixed(2)}\n`;
            }
          }
          if (parsedData.coverage && parsedData.coverage.xg_used) {
            // partite usate per l'analisi
            const homeGames = parsedData.coverage.xg_used.home || '?';
            const awayGames = parsedData.coverage.xg_used.away || '?';
            output += `   • <b>Storico Dati:</b> Ultime ${homeGames} partite in casa / ${awayGames} in trasferta\n`;
          }
          if (parsedData.model) {
            // Formattiamo il nome del modello in italiano
            const modelName = parsedData.model === 'poisson_xg' ? 'Poisson (su Expected Goals)' : String(parsedData.model).toUpperCase();
            output += `   • <b>Algoritmo:</b> ${modelName}\n`;
          }
        }
        return output.trim();
      };

      // Helper per formattare specificamente le predizioni Machine Learning (AI)
      const formatMlAnalysis = (parsedData: any): string => {
        let output = "";

        if (parsedData.reliability) {
          const rel = parsedData.reliability;
          const rGrade = rel.grade === 'high' ? 'Alta 🟢' : rel.grade === 'medium' ? 'Media 🟡' : 'Bassa 🔴';
          const score = rel.score ? (rel.score * 100).toFixed(0) : '?';
          output += `⚙️ <b>Affidabilità Modello:</b> ${rGrade} (${score}%)\n`;
        }

        if (parsedData.bet_signals && parsedData.bet_signals.length > 0) {
          output += `\n🎯 <b>Segnali di Valore (Value Bets):</b>\n`;
          parsedData.bet_signals.forEach((sig: any) => {
            let act = String(sig.action);
            if (act.includes('Home') || act === 'H') act = '1 (Casa)';
            if (act.includes('Away') || act === 'A') act = '2 (Trasferta)';
            if (act.includes('Draw') || act === 'D') act = 'X (Pareggio)';
            if (act === 'True') act = 'Si / Over';
            if (act === 'False') act = 'No / Under';

            const mProb = sig.model_prob ? (sig.model_prob * 100).toFixed(0) : '?';
            const edge = sig.edge ? (sig.edge * 100).toFixed(1) : '?';

            output += `   🔥 <b>${sig.market}</b>: Punta su <b>${act}</b>\n`;
            output += `      Quota: ${sig.decimal_odds} | Nostra Prob: ${mProb}%\n`;
            output += `      Vantaggio Matematico (Edge): +${edge}%\n`;
            if (sig.kelly_stake) output += `      Puntata Ottimale: ${sig.kelly_stake}€\n`;
          });
        } else {
          output += `\n🎯 <b>Segnali di Valore:</b> Nessuna quota con un reale vantaggio matematico puro trovata sui bookmaker.\n`;
        }

        if (parsedData.targets) {
          output += `\n📊 <b>Predizioni Principali ML (Prob. Nette):</b>\n`;
          const t = parsedData.targets;
          if (t.target_1x2) {
            const h = (t.target_1x2.H !== undefined ? t.target_1x2.H : t.target_1x2.Home || 0) * 100;
            const d = (t.target_1x2.D !== undefined ? t.target_1x2.D : t.target_1x2.Draw || 0) * 100;
            const a = (t.target_1x2.A !== undefined ? t.target_1x2.A : t.target_1x2.Away || 0) * 100;
            if (h > 0) output += `   • <b>Esito Finale:</b> 1 (${h.toFixed(0)}%) | X (${d.toFixed(0)}%) | 2 (${a.toFixed(0)}%)\n`;
          }
          if (t.target_ht_1x2) {
            const h = (t.target_ht_1x2.H !== undefined ? t.target_ht_1x2.H : t.target_ht_1x2.Home || 0) * 100;
            const d = (t.target_ht_1x2.D !== undefined ? t.target_ht_1x2.D : t.target_ht_1x2.Draw || 0) * 100;
            const a = (t.target_ht_1x2.A !== undefined ? t.target_ht_1x2.A : t.target_ht_1x2.Away || 0) * 100;
            if (h > 0) output += `   • <b>Esito 1° Tempo:</b> 1 (${h.toFixed(0)}%) | X (${d.toFixed(0)}%) | 2 (${a.toFixed(0)}%)\n`;
          }
          if (t.target_btts) {
            const y = (t.target_btts.True !== undefined ? t.target_btts.True : t.target_btts.Yes || 0) * 100;
            const n = (t.target_btts.False !== undefined ? t.target_btts.False : t.target_btts.No || 0) * 100;
            if (y > 0) output += `   • <b>Gol/No Gol:</b> Gol (${y.toFixed(0)}%) | No Gol (${n.toFixed(0)}%)\n`;
          }
          if (t.target_over_1_5) {
            const o = (t.target_over_1_5.True !== undefined ? t.target_over_1_5.True : t.target_over_1_5.Over || 0) * 100;
            const u = (t.target_over_1_5.False !== undefined ? t.target_over_1_5.False : t.target_over_1_5.Under || 0) * 100;
            if (o > 0) output += `   • <b>Over 1.5:</b> Over (${o.toFixed(0)}%) | Under (${u.toFixed(0)}%)\n`;
          }
          if (t.target_over_2_5) {
            const o = (t.target_over_2_5.True !== undefined ? t.target_over_2_5.True : t.target_over_2_5.Over || 0) * 100;
            const u = (t.target_over_2_5.False !== undefined ? t.target_over_2_5.False : t.target_over_2_5.Under || 0) * 100;
            if (o > 0) output += `   • <b>Over 2.5:</b> Over (${o.toFixed(0)}%) | Under (${u.toFixed(0)}%)\n`;
          }
          if (t.target_over_3_5) {
            const o = (t.target_over_3_5.True !== undefined ? t.target_over_3_5.True : t.target_over_3_5.Over || 0) * 100;
            const u = (t.target_over_3_5.False !== undefined ? t.target_over_3_5.False : t.target_over_3_5.Under || 0) * 100;
            if (o > 0) output += `   • <b>Over 3.5:</b> Over (${o.toFixed(0)}%) | Under (${u.toFixed(0)}%)\n`;
          }
          if (t.target_home_over_0_5) {
            const o = (t.target_home_over_0_5.True !== undefined ? t.target_home_over_0_5.True : t.target_home_over_0_5.Over || 0) * 100;
            const u = (t.target_home_over_0_5.False !== undefined ? t.target_home_over_0_5.False : t.target_home_over_0_5.Under || 0) * 100;
            if (o > 0) output += `   • <b>Subisce Casa (>0.5):</b> Si (${o.toFixed(0)}%) | No (${u.toFixed(0)}%)\n`;
          }
          if (t.target_away_over_0_5) {
            const o = (t.target_away_over_0_5.True !== undefined ? t.target_away_over_0_5.True : t.target_away_over_0_5.Over || 0) * 100;
            const u = (t.target_away_over_0_5.False !== undefined ? t.target_away_over_0_5.False : t.target_away_over_0_5.Under || 0) * 100;
            if (o > 0) output += `   • <b>Subisce Trasferta (>0.5):</b> Si (${o.toFixed(0)}%) | No (${u.toFixed(0)}%)\n`;
          }
          if (t.target_corners_total) {
            const o = (t.target_corners_total.True !== undefined ? t.target_corners_total.True : t.target_corners_total.Over || 0) * 100;
            const u = (t.target_corners_total.False !== undefined ? t.target_corners_total.False : t.target_corners_total.Under || 0) * 100;
            if (o > 0) output += `   • <b>Calci d'Angolo (>9.5):</b> Over (${o.toFixed(0)}%) | Under (${u.toFixed(0)}%)\n`;
          }
          if (t.target_cards_total) {
            const o = (t.target_cards_total.True !== undefined ? t.target_cards_total.True : t.target_cards_total.Over || 0) * 100;
            const u = (t.target_cards_total.False !== undefined ? t.target_cards_total.False : t.target_cards_total.Under || 0) * 100;
            if (o > 0) output += `   • <b>Cartellini (>4.5):</b> Over (${o.toFixed(0)}%) | Under (${u.toFixed(0)}%)\n`;
          }
        }

        return output.trim();
      };

      // Helper function to safely parse and format JSON data
      const formatJsonData = (jsonData: any, fallbackMessage: string, isDbAnalysis: boolean = false, isMlAnalysis: boolean = false) => {
        if (!jsonData) return `<i>${fallbackMessage}</i>`;
        try {
          // If it's a string, try parsing it
          let parsedData = typeof jsonData === 'string' ? JSON.parse(jsonData) : jsonData;

          // In case the JSON was stringified twice
          if (typeof parsedData === 'string') {
            try { parsedData = JSON.parse(parsedData); } catch (e) { }
          }

          if (typeof parsedData === 'object' && parsedData !== null && Object.keys(parsedData).length > 0) {

            // Format data specifically for DB analisi
            if (isDbAnalysis && (parsedData.markets || parsedData.inputs || parsedData.model)) {
              const humanFormatted = formatDbAnalysis(parsedData);
              if (humanFormatted !== "") return humanFormatted;
            }

            // Format data specifically for ML analisi
            if (isMlAnalysis && (parsedData.bet_signals || parsedData.targets)) {
              const mlFormatted = formatMlAnalysis(parsedData);
              if (mlFormatted !== "") return mlFormatted;
            }

            const keysToIgnore = new Set(["league_id", "fixture_id", "season_year", "generated_at"]);
            let items: string[] = [];

            for (const [key, value] of Object.entries(parsedData)) {
              if (keysToIgnore.has(key.toLowerCase())) continue;

              let valueStr = "";
              if (typeof value === 'object' && value !== null) {
                // Formatta in modo pulito gli oggetti evitando [object Object]
                valueStr = JSON.stringify(value)
                  .replace(/[{}"']/g, '')
                  .replace(/,/g, ', ')
                  .replace(/:/g, ': ');
              } else {
                valueStr = String(value);
              }

              items.push(`▪️ <b>${key.replace(/_/g, ' ').toUpperCase()}</b>: ${valueStr}`);
            }

            // Telegram max message length is 4096. Truncate if too long.
            if (items.length > 20) {
              items = items.slice(0, 20);
              items.push("<i>...altri dati omessi per limiti di testo...</i>");
            }

            return items.length > 0 ? items.join('\n') : `<i>${fallbackMessage}</i>`;
          } else if (typeof parsedData === 'string' && parsedData.trim().length > 0) {
            return parsedData.substring(0, 1000); // Truncate string if it's just plain text
          }
          return `<i>${fallbackMessage}</i>`;
        } catch (parseError) {
          console.error(`[JSON] Parse error for data:`, jsonData, parseError);
          return "<i>Errore di formato nei dati del database.</i>";
        }
      };

      // Invio messaggio per ogni partita
      for (const match of matches) {
        console.log(`[BOT] Formatting match: ${match.home_team_name} vs ${match.away_team_name}`);

        // Formattazione della data/ora
        let dateStr = "N/D";
        let timeStr = "N/D";
        if (match.fixture_date) {
          try {
            const matchDate = new Date(match.fixture_date);
            const day = matchDate.getDate().toString().padStart(2, '0');
            const month = (matchDate.getMonth() + 1).toString().padStart(2, '0');
            dateStr = `${day}/${month}`;
            const hours = matchDate.getHours().toString().padStart(2, '0');
            const minutes = matchDate.getMinutes().toString().padStart(2, '0');
            timeStr = `${hours}:${minutes}`;
          } catch (e) {
            console.error("[DATE] Error parsing date:", match.fixture_date, e);
          }
        }

        // Parse JSON sections safely
        const dbAnalysisText = formatJsonData(match.db_json_analisi, "Nessuna informazione aggiuntiva dal database.", true, false);
        const mlPredictionText = formatJsonData(match.model_predictions_json, "coming soon..", false, true);

        // Safely extract primitive fields handling nulls
        let adviceStr = match.advice ? match.advice : 'N/D';

        // Traduzioni al volo dell'advice in italiano
        adviceStr = adviceStr.replace(/Double chance/i, 'Doppia Chance');
        adviceStr = adviceStr.replace(/or draw/i, 'o Pareggio');
        adviceStr = adviceStr.replace(/Home/i, 'Casa');
        adviceStr = adviceStr.replace(/Away/i, 'Trasferta');
        adviceStr = adviceStr.replace(/Draw/i, 'Pareggio');
        adviceStr = adviceStr.replace(/and/i, 'e');

        const goalsHome = match.goals_home_line !== null && match.goals_home_line !== undefined ? match.goals_home_line : 'N/D';
        const goalsAway = match.goals_away_line !== null && match.goals_away_line !== undefined ? match.goals_away_line : 'N/D';

        const text = `
<b>🏟 ${match.home_team_name || 'Squadra 1'} vs ${match.away_team_name || 'Squadra 2'}</b>

📊 <b>Suggerimento Principale</b>
<b>Data e Ora:</b> ${dateStr} - ${timeStr}
<b>Consiglio:</b> ${adviceStr}
<b>Gol Previsti Casa:</b> ${goalsHome}
<b>Gol Previsti Trasferta:</b> ${goalsAway}

🔍 <b>Analisi Dettagliata (Database)</b>
${dbAnalysisText}

🤖 <b>Analisi Machine Learning (AI)</b>
${mlPredictionText}
`;

        try {
          // Aggiungiamo il bottone back all'ultimo messaggio (o a tutti per praticità)
          await ctx.reply(text, { parse_mode: "HTML", reply_markup: backToMainKeyboard });
          console.log(`[BOT] Successfully sent message for ${match.home_team_name} vs ${match.away_team_name}`);
        } catch (telegramErr) {
          // Telegram might throw an error if the HTML is malformed or the message is too long
          console.error(`[TELEGRAM] Failed to send message for match ID ${match.fixture_id}:`, telegramErr);
          // Fallback plain text message
          await ctx.reply(`Errore nell'invio del report per ${match.home_team_name} vs ${match.away_team_name}.`, { reply_markup: backToMainKeyboard });
        }
      }

    } catch (err) {
      console.error(`[MAIN] Fatal error processing request for league ${leagueName}:`, err);
      if (err instanceof Error) {
        console.error(`[MAIN] Error stack:`, err.stack);
      }
      await ctx.reply(`❌ Si è verificato un errore critico consultando il database per ${leagueName}. Segnala l'orario (${new Date().toISOString()}) per il debug nei log di Supabase.`, { reply_markup: backToMainKeyboard });
    }
  }
});

const handleUpdate = webhookCallback(bot, "std/http");

Deno.serve(async (req) => {
  try {
    const url = new URL(req.url);
    if (req.method !== 'POST') {
      return new Response("Solo POST request ammesse", { status: 405 });
    }

    return await handleUpdate(req);
  } catch (err) {
    console.error(err);
    return new Response("Errore nell'elaborazione del webhook", { status: 500 });
  }
});
