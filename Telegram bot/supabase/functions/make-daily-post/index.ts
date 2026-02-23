import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.39.3";

const MAKE_WEBHOOK_URL = Deno.env.get("MAKE_WEBHOOK_URL");
const KIE_API_KEY = Deno.env.get("KIE_API_KEY");

serve(async (req) => {
    try {
        if (!MAKE_WEBHOOK_URL) {
            throw new Error("MAKE_WEBHOOK_URL non configurato.");
        }
        if (!KIE_API_KEY) {
            throw new Error("KIE_API_KEY non configurato in Supabase Secrets.");
        }

        const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
        const supabaseKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
        const supabase = createClient(supabaseUrl, supabaseKey);

        const today = new Date();
        today.setUTCHours(0, 0, 0, 0);
        const startOfDay = today.toISOString();

        today.setUTCHours(23, 59, 59, 999);
        const endOfDay = today.toISOString();

        const { data: predictions, error } = await supabase
            .from("fixture_predictions")
            .select(`
        fixture_id,
        league_id,
        league_name,
        fixture_date,
        home_team_id,
        home_team_name,
        away_team_id,
        away_team_name,
        ht_predictions
      `)
            .gte("fixture_date", startOfDay)
            .lte("fixture_date", endOfDay)
            .not("ht_predictions", "is", null);

        if (error) {
            throw error;
        }

        if (!predictions || predictions.length === 0) {
            return new Response(JSON.stringify({ message: "Nessun dato per oggi." }), { headers: { "Content-Type": "application/json" } });
        }

        // Troviamo il "miglior segnale" (quello con hybrid_prob più alta)
        let bestMatch = null;
        let maxProb = -1;

        for (const m of predictions) {
            let ht = m.ht_predictions as any;
            if (typeof ht === 'string') {
                try { ht = JSON.parse(ht); } catch (e) { }
            }

            if (ht && ht.hybrid_prob !== undefined) {
                const prob = parseFloat(ht.hybrid_prob);
                if (prob > maxProb) {
                    maxProb = prob;
                    bestMatch = m;
                }
            }
        }

        if (!bestMatch) {
            return new Response(JSON.stringify({ message: "Nessun segnale valido trovato oggi." }), { headers: { "Content-Type": "application/json" } });
        }

        let bestHt = bestMatch.ht_predictions as any;
        if (typeof bestHt === 'string') {
            try { bestHt = JSON.parse(bestHt); } catch (e) { }
        }

        const hybridProb = (parseFloat(bestHt.hybrid_prob) * 100).toFixed(1);
        const lambda = parseFloat(bestHt.lambda_1h).toFixed(2);
        const freq = (parseFloat(bestHt.details?.freq || 0) * 100).toFixed(0);
        const poisson = (parseFloat(bestHt.details?.poisson || 0) * 100).toFixed(0);

        const homeLogo = `https://media.api-sports.io/football/teams/${bestMatch.home_team_id}.png`;
        const awayLogo = `https://media.api-sports.io/football/teams/${bestMatch.away_team_id}.png`;

        // Formattazione Data e Ora in Italiano (es: 23 FEBBRAIO 2026 - 22:00 (UTC))
        const fDate = new Date(bestMatch.fixture_date);
        const monthNames = ["GENNAIO", "FEBBRAIO", "MARZO", "APRILE", "MAGGIO", "GIUGNO", "LUGLIO", "AGOSTO", "SETTEMBRE", "OTTOBRE", "NOVEMBRE", "DICEMBRE"];
        const day = fDate.getUTCDate();
        const monthName = monthNames[fDate.getUTCMonth()];
        const year = fDate.getUTCFullYear();
        const formattedDate = `${day} ${monthName} ${year}`;
        const formattedTime = `${String(fDate.getUTCHours()).padStart(2, "0")}:${String(fDate.getUTCMinutes()).padStart(2, "0")} (UTC)`;

        // URL del logo AlphaScore Ufficiale (GLOBE VERSION)
        const alphaScoreLogoUrl = "https://files.catbox.moe/zmljo5.png";

        const messageText = `📊 Metriche del Modello Ibrido:
✅ Probabilità Globale: ${hybridProb}%
(Calcolata incrociando la frequenza storica con la stima matematica attuale)

✅ Intensità Offensiva (Lambda): ${lambda}
(La forza d'attacco nel 1° tempo. Valori sopra 1.57 indicano alta propensione al gol)

🔍 Analisi Dettagliata: Storicamente questo evento si è verificato nel ${freq}% dei match recenti. L'analisi Poisson stima una forza d'attacco attuale pari al ${poisson}%.`;

        // COSTRUZIONE PROMPT PER KIE.AI (NANO BANANA PRO)
        const aiPrompt = `Create a MASTERPIECE cinematic football matchday poster. The image must look exactly like an official high-end UEFA Champions League or Nike Football advertisement. 

SCENE & ATMOSPHERE:
A dark, dramatic, ultra-realistic modern football stadium environment at night. Soft atmospheric fog, cinematic spotlights cutting through the darkness, and a subtle glowing gradient in the background matching the primary colors of the two teams: ${bestMatch.home_team_name} and ${bestMatch.away_team_name}. Depth-of-field effect with bokeh lights in the deep background. Ultra-sharp 8k resolution, editorial magazine quality.

CENTER LAYOUT & SUBJECTS:
1. LEAGUE & DATE (TOP CENTER): At the top center, write perfectly the league name "${bestMatch.league_name}" in elegant, spaced-out small caps. Directly below it, write perfectly the match date: "${formattedDate}" in clean, bold typography, followed by the time: "${formattedTime}".
2. LOGOS & TEAM NAMES (CENTER AREA): In the exact center, place a sleek, glowing "VS". 
   - On the LEFT: seamlessly integrate the exact logo reference: ${homeLogo}. Directly below this left logo, write the name "${bestMatch.home_team_name}" in modern, bold sports typography.
   - On the RIGHT: seamlessly integrate the exact logo reference: ${awayLogo}. Directly below this right logo, write the name "${bestMatch.away_team_name}".
   Both logos MUST have a premium 3D metallic edge or glowing backlight. DO NOT distort them.
3. ANALYTICS CARD (LOWER HALF): Create an ultra-premium, eye-catching, high-tech glassmorphism analytics card with subtle neon borders. 
   - HEADER: High above this card (leaving a VERY LARGE vertical gap of empty space), write perfectly in bold, glowing white text: "HT Sniper consiglia 👇". 
   - CONTENT: Inside the analytics card itself, write the following text exactly, preserving structure:
"${messageText}"
4. BRANDING (BOTTOM FOOTER): 
   - TEXT: Very far below the analytics card (leaving a VERY LARGE vertical gap so it's nowhere near the card), write in small, elegant, minimal tracking font: "powered by AlphaScore". 
   - LOGO: Below that text, at the very bottom center of the poster, include the official brand logo using this exact visual reference: ${alphaScoreLogoUrl}.

STRICT VISUAL STYLE LOCK & RULES:
- The atmospheric lighting MUST be identical to a dark, smoky, cinematic UEFA Champions League premium broadcast.
- The typography MUST be perfectly rendered, crisp, using premium modern sans-serif fonts (like bold Montserrat or Bebas Neue).
- PERFECT ALIGNMENT & PADDING: All text must be perfectly centered and aligned. ENFORCE VAST VERTICAL PADDING: There MUST be a massive, clear empty space separating the "HT Sniper consiglia" header from the analytics box. Similarly, there MUST be a massive clear empty space separating the box from the "powered by" footer. 
- The composition must be perfectly symmetrical and balanced.
- Aspect ratio: 4:5.
- NO watermark other than AlphaScore, NO stock photo artifacts, NO random irrelevant players, NO messy text.
- The absolute priority is making the image look like an expensive, official club social media broadcast graphic.`;

        // 1. Iniziamo la task di generazione immagine su Kie.ai
        console.log("Inviando richiesta a Kie.ai (Nano Banana Pro)...");
        const kieRes = await fetch("https://api.kie.ai/api/v1/jobs/createTask", {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${KIE_API_KEY}`,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                model: "nano-banana-pro",
                input: {
                    prompt: aiPrompt,
                    aspect_ratio: "4:5"
                }
            })
        });

        const taskData = await kieRes.json();
        console.log("Kie.ai createTask response:", taskData);

        // Il taskId puo trovarsi in taskData.data.taskId o taskData.taskId a seconda della versione API
        const taskId = taskData?.data?.taskId || taskData?.taskId;

        let generatedImageUrl = null;
        let rawKieResult = null;
        let kieFinished = false;

        if (taskId) {
            console.log(`Task avviato con ID: ${taskId}. Inizio polling (attesa generazione)...`);
            // 2. Facciamo polling per massimo 125 secondi (25 tentativi x 5 secondi)
            for (let i = 0; i < 25; i++) {
                await new Promise(resolve => setTimeout(resolve, 5000)); // Attendi 5s

                try {
                    const pollRes = await fetch(`https://api.kie.ai/api/v1/jobs/recordInfo?taskId=${taskId}`, {
                        headers: { "Authorization": `Bearer ${KIE_API_KEY}` }
                    });
                    const pollData = await pollRes.json();
                    const rawState = pollData?.data?.state || pollData?.state;
                    const state = String(rawState || "").toUpperCase();

                    console.log(`Polling ${i + 1}: stato = ${state}`);

                    if (state === "SUCCESS") {
                        rawKieResult = pollData?.data?.resultJson || pollData?.resultJson;

                        // Parse intelligente dell'output che varia tra le API
                        let parsedResult = typeof rawKieResult === 'string' ? JSON.parse(rawKieResult) : rawKieResult;

                        if (parsedResult?.resultUrls && Array.isArray(parsedResult.resultUrls) && parsedResult.resultUrls.length > 0) {
                            generatedImageUrl = parsedResult.resultUrls[0];
                        } else if (parsedResult?.url) {
                            generatedImageUrl = parsedResult.url;
                        } else if (Array.isArray(parsedResult) && parsedResult[0]?.url) {
                            generatedImageUrl = parsedResult[0].url;
                        } else if (typeof parsedResult === 'string' && parsedResult.startsWith('http')) {
                            generatedImageUrl = parsedResult;
                        } else {
                            // Cerca selvaggiamente un http se il formato e' sconosciuto
                            const stringified = JSON.stringify(parsedResult);
                            const match = stringified.match(/(https?:\/\/[^"]+)/);
                            if (match) generatedImageUrl = match[1];
                        }

                        kieFinished = true;
                        console.log("Immagine generata con successo!", generatedImageUrl);
                        break;
                    } else if (state === "FAIL" || state === "FAILED" || state === "CANCELLED") {
                        console.error("Generazione fallita su Kie.ai", pollData);
                        kieFinished = true;
                        break;
                    }
                } catch (pollErr) {
                    console.error("Errore durante il polling:", pollErr);
                }
            }
        } else {
            console.error("Nessun taskId restituito da Kie.ai, la chiamata potrebbe essere fallita.");
        }

        // 3. Prepariamo il payload finale, ultra-pulito per Make.com
        const payload = {
            home_team_name: bestMatch.home_team_name,
            away_team_name: bestMatch.away_team_name,
            league_name: bestMatch.league_name,
            fixture_date: bestMatch.fixture_date,
            message_text: messageText,

            // Risultato della magia (se e' andata bene)
            generated_image_url: generatedImageUrl || "https://dummyimage.com/800x1000/000/fff&text=Immagine+Kie.ai+Fallita",
            generation_success: kieFinished && !!generatedImageUrl
        };

        // 4. Inviamo tutto a Make.com
        console.log("Inviando pacchetto finale a Make.com...", payload);
        const makeRes = await fetch(MAKE_WEBHOOK_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        if (!makeRes.ok) {
            throw new Error(`Errore dal Webhook di Make.com: ${makeRes.statusText}`);
        }

        return new Response(JSON.stringify({
            success: true,
            sent_match: bestMatch.fixture_id,
            generatedImageUrl: generatedImageUrl,
            payload_to_make: payload
        }), {
            headers: { "Content-Type": "application/json" }
        });

    } catch (err: any) {
        console.error("Errore:", err);
        return new Response(JSON.stringify({ error: err.message }), {
            status: 500,
            headers: { "Content-Type": "application/json" }
        });
    }
});
