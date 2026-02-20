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
const menuKeyboard = new InlineKeyboard()
  .text(LEAGUES[135], "league_135").text(LEAGUES[136], "league_136").row()
  .text(LEAGUES[39], "league_39").text(LEAGUES[140], "league_140").row()
  .text(LEAGUES[61], "league_61").text(LEAGUES[78], "league_78").row()
  .text(LEAGUES[2], "league_2").text(LEAGUES[3], "league_3").row()
  .text(LEAGUES[848], "league_848");

bot.command("start", (ctx) => {
  return ctx.reply("Bentornato! Seleziona una lega per vedere le previsioni di oggi:", {
    reply_markup: menuKeyboard,
  });
});

bot.command("partite", (ctx) => {
  return ctx.reply("Seleziona una lega per le partite di oggi:", {
    reply_markup: menuKeyboard,
  });
});

// Handle button clicks
bot.on("callback_query:data", async (ctx) => {
  const data = ctx.callbackQuery.data;

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
        await ctx.reply(`Nessuna partita trovata oggi per ${leagueName}.`);
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

      // Helper function to safely parse and format JSON data
      const formatJsonData = (jsonData: any, fallbackMessage: string, isDbAnalysis: boolean = false) => {
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
        const dbAnalysisText = formatJsonData(match.db_json_analisi, "Nessuna informazione aggiuntiva dal database.", true);
        const mlPredictionText = formatJsonData(match.model_predictions_json, "coming soon..");

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
          await ctx.reply(text, { parse_mode: "HTML" });
          console.log(`[BOT] Successfully sent message for ${match.home_team_name} vs ${match.away_team_name}`);
        } catch (telegramErr) {
          // Telegram might throw an error if the HTML is malformed or the message is too long
          console.error(`[TELEGRAM] Failed to send message for match ID ${match.fixture_id}:`, telegramErr);
          // Fallback plain text message
          await ctx.reply(`Errore nell'invio del report per ${match.home_team_name} vs ${match.away_team_name}. Controlla i log di Supabase.`);
        }
      }

    } catch (err) {
      console.error(`[MAIN] Fatal error processing request for league ${leagueName}:`, err);
      if (err instanceof Error) {
        console.error(`[MAIN] Error stack:`, err.stack);
      }
      await ctx.reply(`❌ Si è verificato un errore critico consultando il database per ${leagueName}. Segnala l'orario (${new Date().toISOString()}) per il debug nei log di Supabase.`);
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
