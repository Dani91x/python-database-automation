import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.39.3";
import { Image } from "https://deno.land/x/imagescript@1.2.15/mod.ts";

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
        const alphaScoreLogoUrl = "https://dqbwaocvlzbxfrpacsac.supabase.co/storage/v1/object/public/Loghi/AlphaScore_OFFICIAL_Transparent.png";

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

CENTER LAYOUT & STRICT PROPORTIONS LOCK:
You MUST maintain the exact same proportions and positions for every generated image. Do not change the layout.
1. LEAGUE & DATE (TOP 15%): At the top center, write perfectly the league name "${bestMatch.league_name}" in elegant, spaced-out small caps. Directly below it, write perfectly the match date: "${formattedDate}" in clean, bold typography, followed by the time: "${formattedTime}".
2. LOGOS & TEAM NAMES (UPPER-MIDDLE 30%): In the exact center, place a sleek, glowing "VS". 
   - On the LEFT: seamlessly integrate the exact logo reference: ${homeLogo}. Directly below this left logo, write the name "${bestMatch.home_team_name}" in modern, bold sports typography.
   - On the RIGHT: seamlessly integrate the exact logo reference: ${awayLogo}. Directly below this right logo, write the name "${bestMatch.away_team_name}".
   Both logos MUST have a premium 3D metallic edge or glowing backlight. DO NOT distort them.
3. ANALYTICS CARD (LOWER-MIDDLE 40%): Create an ultra-premium, eye-catching, high-tech glassmorphism analytics card with subtle neon borders. 
   - HEADER: Leave a generous vertical empty space, then write perfectly in bold, glowing white text: "HT Sniper consiglia 👇". 
   - CONTENT: Inside the analytics card itself, write the following text exactly, preserving structure:
"${messageText}"
4. BRANDING (BOTTOM FOOTER 15%): 
   - TEXT FIRST: Write "powered by AlphaScore" cleanly and elegantly directly below the analytics box. Use a very THIN, lightweight, minimalist and wide-tracked font (extra letter spacing).
   - PADDING BELOW TEXT: You absolutely MUST leave the bottom 15% of the poster completely empty and dark. DO NOT put the text at the bottom edge. Create a huge empty black/dark margin at the very bottom.

STRICT VISUAL STYLE LOCK & RULES:
- ABSOLUTELY NO HALLUCINATIONS: Do not hallucinate any random text, logos, shapes, or players not explicitly asked for.
- PERFECT SPACING: Keep equal and generous vertical spacing between the Top text, the Team Logos, the Analytics Card, and the Bottom text.
- The atmospheric lighting MUST be identical to a dark, smoky, cinematic UEFA Champions League premium broadcast.
- PERFECT ALIGNMENT: All elements must be strictly horizontally centered.
- Aspect ratio: 4:5.
- The absolute priority is making the image look like an expensive, highly standardized, official corporate broadcast graphic.`;

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

        let finalImageUrl = generatedImageUrl || "https://dummyimage.com/800x1000/000/fff&text=Immagine+Kie.ai+Fallita";
        let postProdError = null;

        if (kieFinished && generatedImageUrl) {
            try {
                console.log("Inizio post-produzione: applicazione del logo AlphaScore...");

                // 1. Scarica l'immagine generata dall'IA
                const bgRes = await fetch(generatedImageUrl);
                const bgArrayBuffer = await bgRes.arrayBuffer();
                const bgImage = await Image.decode(new Uint8Array(bgArrayBuffer));

                // 2. Scarica il logo AlphaScore
                const logoRes = await fetch(alphaScoreLogoUrl);
                const logoArrayBuffer = await logoRes.arrayBuffer();
                const logoImage = await Image.decode(new Uint8Array(logoArrayBuffer));

                // 3. Ridimensiona il logo (compatto, elegante)
                logoImage.resize(220, Image.RESIZE_AUTO);

                // 4. Calcola le coordinate: esattamente in basso al centro, 
                // con un margine di 30px dal bordo inferiore in modo che stia SOTTO
                // alla scritta "powered by AlphaScore" generata dall'IA.
                const x = Math.floor((bgImage.width - logoImage.width) / 2);
                const y = Math.floor(bgImage.height - logoImage.height - 30);

                // 5. Incolla il logo nudo e crudo sopra lo sfondo originale e intatto (ZERO banner neri aggiunti via codice)
                bgImage.composite(logoImage, x, y);

                // 6. Converti l'immagine finale in formato PNG ad alta qualita
                const finalBuffer = await bgImage.encode(3); // compressione PNG = 3 (veloce e buona)

                // 7. Carica su Supabase Storage (Bucket "Loghi")
                const fileName = `generati/post_${bestMatch.fixture_id}_${Date.now()}.png`;
                const { error: uploadError } = await supabase.storage.from("Loghi").upload(fileName, finalBuffer, {
                    contentType: "image/png",
                    upsert: true
                });

                if (uploadError) {
                    throw uploadError;
                }

                // 8. Ottieni l'URL pubblico finale
                const { data: publicUrlData } = supabase.storage.from("Loghi").getPublicUrl(fileName);
                finalImageUrl = publicUrlData.publicUrl;

                console.log("Post-produzione completata! URL finale:", finalImageUrl);
            } catch (err: any) {
                console.error("Errore durante l'applicazione del logo in post-produzione:", err);
                postProdError = err.message || "Errore sconosciuto";
                // Se fallisce per qualche motivo, ripieghiamo cull'immagine base generata dall'IA
                finalImageUrl = generatedImageUrl;
            }
        }

        // 3. Prepariamo il payload finale, ultra-pulito per Make.com
        const payload = {
            home_team_name: bestMatch.home_team_name,
            away_team_name: bestMatch.away_team_name,
            league_name: bestMatch.league_name,
            fixture_date: bestMatch.fixture_date,
            message_text: messageText,

            // Risultato della magia post-prodotta
            generated_image_url: finalImageUrl,
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
            generatedImageUrl: finalImageUrl,
            payload_to_make: payload,
            post_production_error: postProdError
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
