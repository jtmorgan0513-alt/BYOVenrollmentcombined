import type { Express, Request, Response } from "express";
import type { Server } from "http";
import { createProxyMiddleware, Options } from "http-proxy-middleware";
import OpenAI from "openai";
import http from "http";

// Streamlit backend health state
let streamlitReady = false;
let streamlitCheckInterval: NodeJS.Timeout | null = null;

// Check if Streamlit backend is ready
async function checkStreamlitHealth(): Promise<boolean> {
  return new Promise((resolve) => {
    const req = http.request(
      {
        hostname: "127.0.0.1",
        port: 8000,
        path: "/_stcore/health",
        method: "GET",
        timeout: 3000,
      },
      (res) => {
        resolve(res.statusCode === 200);
      }
    );
    req.on("error", () => resolve(false));
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
    req.end();
  });
}

// Start keepalive ping to Streamlit backend
function startStreamlitKeepalive() {
  if (streamlitCheckInterval) return;
  
  const checkAndLog = async () => {
    const wasReady = streamlitReady;
    streamlitReady = await checkStreamlitHealth();
    if (!wasReady && streamlitReady) {
      console.log(`${new Date().toLocaleTimeString()} [express] Streamlit backend is ready`);
    } else if (wasReady && !streamlitReady) {
      console.log(`${new Date().toLocaleTimeString()} [express] Streamlit backend went offline`);
    }
  };
  
  // Initial check
  checkAndLog();
  
  // Ping every 30 seconds to keep warm
  streamlitCheckInterval = setInterval(checkAndLog, 30000);
}

// Wait for Streamlit to be ready with retries
async function waitForStreamlit(maxRetries = 10, delayMs = 500): Promise<boolean> {
  for (let i = 0; i < maxRetries; i++) {
    if (await checkStreamlitHealth()) {
      streamlitReady = true;
      return true;
    }
    await new Promise(resolve => setTimeout(resolve, delayMs));
    delayMs = Math.min(delayMs * 1.5, 2000); // Exponential backoff, max 2 seconds
  }
  return false;
}

// the newest OpenAI model is "gpt-5" which was released August 7, 2025. do not change this unless explicitly requested by the user
const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });

// BYOV Program knowledge base for the AI assistant
const BYOV_SYSTEM_PROMPT = `You are a helpful assistant for the Sears Home Services BYOV (Bring Your Own Vehicle) program. You help technicians understand the program benefits, requirements, and enrollment process.

KEY PROGRAM INFORMATION:

MILEAGE RATES:
- California (CA), Washington (WA), and Illinois (IL): $0.70 per mile
- All other states: $0.57 per mile
- Rates are tax-free and paid weekly
- Mileage is tracked from "start pay" punch to "end pay" punch
- First 35 minutes and last 35 minutes of commute to/from home are unpaid and not reimbursed

SIGN-ON BONUS:
- $400 bonus available after 30 days of participation
- Requires completing a feedback survey about the program

VEHICLE REQUIREMENTS:
- Acceptable vehicles: Truck, Van, Car, or SUV
- Preferred: Model year 2005 or newer
- Older vehicles may be eligible with approval - encourage users to ask
- Vehicle must be in good working condition

REQUIRED DOCUMENTS:
- Valid driver's license
- Current vehicle registration
- Current auto insurance meeting state minimums

INSURANCE:
- Technicians maintain their own personal auto insurance (primary coverage)
- Insurance must meet state minimum requirements
- Sears provides excess liability coverage while on company business

RENTAL CAR SUPPORT:
- Up to 5 days per year of rental vehicle coverage
- Applies to unplanned breakdowns of personal vehicle

ENROLLMENT PROCESS:
- Complete the online enrollment form
- Submit required documents (license, registration, insurance)
- Upload vehicle photos
- Sign the policy agreement
- Wait for approval from admin team

GUIDELINES FOR RESPONSES:
- Be friendly, helpful, and concise
- IMPORTANT: Only share the mileage rate for the user's current state. Do NOT compare rates between states or mention that some states have different rates. If the user asks about rates in other states, politely explain that you can only provide rate information for their enrollment state.
- If the user has not selected a state yet, encourage them to select their state on the page to see their specific rate
- If unsure about something, suggest contacting Tyler Morgan at 910-906-3588
- Encourage enrollment by highlighting benefits
- Keep responses focused on the BYOV program - politely redirect off-topic questions`;

export async function registerRoutes(
  httpServer: Server,
  app: Express
): Promise<Server> {
  // Health check endpoint - responds immediately for deployment health checks
  app.get("/health", (_req: Request, res: Response) => {
    res.status(200).json({ status: "ok", timestamp: new Date().toISOString() });
  });

  // Chat API endpoint for the AI assistant
  app.post("/api/chat", async (req: Request, res: Response) => {
    try {
      const { messages, state } = req.body;
      
      if (!messages || !Array.isArray(messages)) {
        return res.status(400).json({ error: "Messages array is required" });
      }

      // Add state context to the system prompt if provided
      let systemPrompt = BYOV_SYSTEM_PROMPT;
      if (state && state !== "OTHER") {
        const rate = ["CA", "WA", "IL"].includes(state) ? "$0.70" : "$0.57";
        systemPrompt += `\n\nCURRENT USER CONTEXT: The user is in ${state}. Their mileage rate would be ${rate} per mile.`;
      }

      // Format messages for OpenAI
      const openaiMessages = [
        { role: "system" as const, content: systemPrompt },
        ...messages.map((m: { role: string; content: string }) => ({
          role: m.role as "user" | "assistant",
          content: m.content
        }))
      ];

      const response = await openai.chat.completions.create({
        model: "gpt-4o",
        messages: openaiMessages,
        max_tokens: 500
      });

      const assistantMessage = response.choices[0]?.message?.content || "I'm sorry, I couldn't generate a response. Please try again.";
      
      res.json({ message: assistantMessage });
    } catch (error: any) {
      console.error("Chat API error:", error);
      res.status(500).json({ 
        error: "Failed to get response from AI assistant",
        details: error.message 
      });
    }
  });

  // Redirect enrollment to streamlit app with enrollment mode
  app.get("/enroll", (_req: Request, res: Response) => {
    res.redirect("/streamlit/?mode=enroll");
  });
  
  // Redirect admin to streamlit app with admin mode
  app.get("/admin", (_req: Request, res: Response) => {
    res.redirect("/streamlit/?mode=admin");
  });

  // DocuSign confirmation endpoint - redirects to Streamlit confirmation page
  app.get("/confirm-docusign/:token", (req: Request, res: Response) => {
    const { token } = req.params;
    res.redirect(`/streamlit/?mode=confirm_docusign&token=${encodeURIComponent(token)}`);
  });

  // Start the keepalive ping to Streamlit backend
  startStreamlitKeepalive();

  // Proxy configuration for Streamlit app at /streamlit/
  const streamlitProxy = createProxyMiddleware({
    target: "http://127.0.0.1:8000",
    changeOrigin: true,
    ws: true,
    pathRewrite: { "^/streamlit": "" },
    timeout: 60000,
    proxyTimeout: 60000,
    on: {
      error: (err: Error, _req: http.IncomingMessage, res: http.ServerResponse | any) => {
        console.error(`${new Date().toLocaleTimeString()} [proxy] Error:`, err.message);
        if (res && 'writeHead' in res && !res.headersSent) {
          res.writeHead(503, { 'Content-Type': 'text/html' });
          res.end(`
            <!DOCTYPE html>
            <html>
            <head>
              <title>Loading...</title>
              <meta http-equiv="refresh" content="2">
              <style>
                body { font-family: Arial, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #f5f5f5; }
                .loader { text-align: center; }
                .spinner { width: 50px; height: 50px; border: 4px solid #e0e0e0; border-top: 4px solid #003366; border-radius: 50%; animation: spin 1s linear infinite; margin: 0 auto 20px; }
                @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
                h2 { color: #003366; }
                p { color: #666; }
              </style>
            </head>
            <body>
              <div class="loader">
                <div class="spinner"></div>
                <h2>Loading Application...</h2>
                <p>Please wait while we connect you.</p>
              </div>
            </body>
            </html>
          `);
        }
      },
      proxyReq: (_proxyReq: http.ClientRequest, req: http.IncomingMessage) => {
        console.log(`${new Date().toLocaleTimeString()} [proxy] ${req.method} ${req.url}`);
      }
    }
  } as Options);
  
  // Middleware to wait for Streamlit before proxying
  app.use("/streamlit", async (req: Request, res: Response, next) => {
    if (!streamlitReady) {
      console.log(`${new Date().toLocaleTimeString()} [proxy] Streamlit not ready, waiting...`);
      const isReady = await waitForStreamlit(8, 300);
      if (!isReady) {
        return res.status(503).send(`
          <!DOCTYPE html>
          <html>
          <head>
            <title>Loading...</title>
            <meta http-equiv="refresh" content="3">
            <style>
              body { font-family: Arial, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #f5f5f5; }
              .loader { text-align: center; }
              .spinner { width: 50px; height: 50px; border: 4px solid #e0e0e0; border-top: 4px solid #003366; border-radius: 50%; animation: spin 1s linear infinite; margin: 0 auto 20px; }
              @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
              h2 { color: #003366; }
              p { color: #666; }
            </style>
          </head>
          <body>
            <div class="loader">
              <div class="spinner"></div>
              <h2>Starting Application...</h2>
              <p>This may take a moment. The page will refresh automatically.</p>
            </div>
          </body>
          </html>
        `);
      }
    }
    next();
  });
  
  // Proxy all Streamlit routes under /streamlit/
  app.use("/streamlit", streamlitProxy);
  
  // Explicit WebSocket upgrade handler for Streamlit connections
  // This ensures WebSocket handshakes succeed on first load without requiring refresh
  httpServer.on('upgrade', async (req, socket, head) => {
    if (req.url?.startsWith('/streamlit')) {
      // Wait for Streamlit if not ready
      if (!streamlitReady) {
        await waitForStreamlit(5, 200);
      }
      (streamlitProxy as any).upgrade(req, socket, head);
    }
  });

  return httpServer;
}
