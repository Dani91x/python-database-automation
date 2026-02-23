// Web Editor non supporta import relativi non validi
// import "@supabase/functions-js/edge-runtime.d.ts"
import { Bot, webhookCallback, InlineKeyboard } from "https://esm.sh/grammy@1.30.0";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.39.3";

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

const botToken = Deno.env.get("TELEGRAM_BOT_TOKEN");
if (!botToken) {
  throw new Error("TELEGRAM_BOT_TOKEN is not set!");
}

const bot = new Bot(botToken);

// Create the main menu keyboard
const mainMenuKeyboard = new InlineKeyboard()
  .text("🎯 HT Sniper", "menu_ht_sniper").row()
  .text("📊 Predictions", "menu_predictions");

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
