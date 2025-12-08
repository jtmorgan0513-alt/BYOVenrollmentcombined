const http = require('http');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const port = parseInt(process.env.PORT || '5000', 10);
const ENROLL_STREAMLIT_PORT = 8000;
const ADMIN_STREAMLIT_PORT = 8080;

// In production, use PRODUCTION_DATABASE_URL if available
if (process.env.REPLIT_DEPLOYMENT && process.env.PRODUCTION_DATABASE_URL) {
  process.env.DATABASE_URL = process.env.PRODUCTION_DATABASE_URL;
  console.log('[production] Using PRODUCTION_DATABASE_URL');
}

let openai = null;
function getOpenAI() {
  if (!openai) {
    try {
      const OpenAI = require('openai');
      openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
    } catch (err) {
      console.error('Failed to load OpenAI:', err.message);
    }
  }
  return openai;
}

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
- IMPORTANT: Only share the mileage rate for the user's current state. Do NOT compare rates between states or mention that some states have different rates.
- If the user has not selected a state yet, encourage them to select their state on the page to see their specific rate
- If unsure about something, suggest contacting Tyler Morgan at 910-906-3588
- Encourage enrollment by highlighting benefits
- Keep responses focused on the BYOV program - politely redirect off-topic questions`;

let enrollStreamlitProcess = null;
let adminStreamlitProcess = null;
let enrollStreamlitRestarts = 0;
let adminStreamlitRestarts = 0;
const MAX_STREAMLIT_RESTARTS = 5;
const RESTART_COOLDOWN_MS = 10000;
const PREWARM_INTERVAL_MS = 30000;

function log(message, source = 'production') {
  const time = new Date().toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  });
  console.log(`${time} [${source}] ${message}`);
}

function startEnrollStreamlit() {
  log('Starting Enrollment Streamlit backend on port 8000...');
  
  const streamlitEnv = {
    ...process.env,
    STREAMLIT_SERVER_HEADLESS: 'true',
    STREAMLIT_SERVER_ENABLE_CORS: 'false',
    STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION: 'false',
    STREAMLIT_BROWSER_GATHER_USAGE_STATS: 'false'
  };
  
  enrollStreamlitProcess = spawn('streamlit', [
    'run',
    'enrollment_app.py',
    '--server.port', String(ENROLL_STREAMLIT_PORT),
    '--server.address', '0.0.0.0',
    '--server.headless', 'true',
    '--server.enableCORS', 'false',
    '--server.enableXsrfProtection', 'false',
    '--server.enableWebsocketCompression', 'false',
    '--server.maxUploadSize', '50',
    '--server.baseUrlPath', '/enroll'
  ], {
    stdio: ['ignore', 'pipe', 'pipe'],
    cwd: process.cwd(),
    env: streamlitEnv
  });

  enrollStreamlitProcess.stdout.on('data', (data) => {
    log(data.toString().trim(), 'enroll-streamlit');
  });

  enrollStreamlitProcess.stderr.on('data', (data) => {
    log(data.toString().trim(), 'enroll-streamlit');
  });

  enrollStreamlitProcess.on('error', (err) => {
    log(`Enrollment Streamlit error: ${err.message}`, 'enroll-streamlit');
  });

  enrollStreamlitProcess.on('exit', (code, signal) => {
    log(`Enrollment Streamlit exited with code ${code}, signal ${signal}`, 'enroll-streamlit');
    if (code !== 0 && enrollStreamlitRestarts < MAX_STREAMLIT_RESTARTS) {
      enrollStreamlitRestarts++;
      log(`Restarting Enrollment Streamlit (attempt ${enrollStreamlitRestarts}/${MAX_STREAMLIT_RESTARTS})...`, 'enroll-streamlit');
      setTimeout(startEnrollStreamlit, RESTART_COOLDOWN_MS);
    } else if (enrollStreamlitRestarts >= MAX_STREAMLIT_RESTARTS) {
      console.error('CRITICAL: Enrollment Streamlit failed after max restart attempts.');
    }
  });
  
  log(`Enrollment Streamlit process started with PID: ${enrollStreamlitProcess.pid}`, 'enroll-streamlit');
}

function startAdminStreamlit() {
  log('Starting Admin Streamlit backend on port 8080...');
  
  const streamlitEnv = {
    ...process.env,
    STREAMLIT_SERVER_HEADLESS: 'true',
    STREAMLIT_SERVER_ENABLE_CORS: 'false',
    STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION: 'false',
    STREAMLIT_BROWSER_GATHER_USAGE_STATS: 'false'
  };
  
  adminStreamlitProcess = spawn('streamlit', [
    'run',
    'admin_app.py',
    '--server.port', String(ADMIN_STREAMLIT_PORT),
    '--server.address', '0.0.0.0',
    '--server.headless', 'true',
    '--server.enableCORS', 'false',
    '--server.enableXsrfProtection', 'false',
    '--server.enableWebsocketCompression', 'false',
    '--server.maxUploadSize', '50',
    '--server.baseUrlPath', '/admin'
  ], {
    stdio: ['ignore', 'pipe', 'pipe'],
    cwd: process.cwd(),
    env: streamlitEnv
  });

  adminStreamlitProcess.stdout.on('data', (data) => {
    log(data.toString().trim(), 'admin-streamlit');
  });

  adminStreamlitProcess.stderr.on('data', (data) => {
    log(data.toString().trim(), 'admin-streamlit');
  });

  adminStreamlitProcess.on('error', (err) => {
    log(`Admin Streamlit error: ${err.message}`, 'admin-streamlit');
  });

  adminStreamlitProcess.on('exit', (code, signal) => {
    log(`Admin Streamlit exited with code ${code}, signal ${signal}`, 'admin-streamlit');
    if (code !== 0 && adminStreamlitRestarts < MAX_STREAMLIT_RESTARTS) {
      adminStreamlitRestarts++;
      log(`Restarting Admin Streamlit (attempt ${adminStreamlitRestarts}/${MAX_STREAMLIT_RESTARTS})...`, 'admin-streamlit');
      setTimeout(startAdminStreamlit, RESTART_COOLDOWN_MS);
    } else if (adminStreamlitRestarts >= MAX_STREAMLIT_RESTARTS) {
      console.error('CRITICAL: Admin Streamlit failed after max restart attempts.');
    }
  });
  
  log(`Admin Streamlit process started with PID: ${adminStreamlitProcess.pid}`, 'admin-streamlit');
}

const loadingPage = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="refresh" content="2">
  <title>BYOV - Starting...</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      background: linear-gradient(135deg, #003366 0%, #001a33 100%);
      color: white;
    }
    .container {
      text-align: center;
      padding: 2rem;
    }
    .logo {
      font-size: 2.5rem;
      font-weight: 700;
      margin-bottom: 1.5rem;
      letter-spacing: 2px;
    }
    .logo span { color: #ffc107; }
    .spinner {
      width: 50px;
      height: 50px;
      border: 4px solid rgba(255,255,255,0.2);
      border-top-color: #ffc107;
      border-radius: 50%;
      animation: spin 1s linear infinite;
      margin: 0 auto 1.5rem;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    h2 {
      font-size: 1.25rem;
      font-weight: 500;
      margin-bottom: 0.5rem;
    }
    p {
      font-size: 0.9rem;
      opacity: 0.8;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="logo">BY<span>O</span>V</div>
    <div class="spinner"></div>
    <h2>Starting Application</h2>
    <p>This page will refresh automatically...</p>
  </div>
</body>
</html>`;

const healthServer = http.createServer((req, res) => {
  if (req.url === '/health') {
    res.writeHead(200, { 'Content-Type': 'text/plain' });
    res.end('OK');
    return;
  }
  res.writeHead(200, { 'Content-Type': 'text/html' });
  res.end(loadingPage);
});

function waitForStreamlit(port, name, maxAttempts = 90, interval = 1000) {
  return new Promise((resolve) => {
    let attempts = 0;
    const check = () => {
      attempts++;
      const req = http.get(`http://127.0.0.1:${port}/_stcore/health`, (res) => {
        if (res.statusCode === 200) {
          log(`${name} Streamlit is ready on port ${port}`);
          resolve(true);
        } else {
          retry();
        }
      });
      req.on('error', () => retry());
      req.setTimeout(2000, () => { req.destroy(); retry(); });
    };
    const retry = () => {
      if (attempts >= maxAttempts) {
        log(`${name} Streamlit not responding after max attempts, continuing anyway`);
        resolve(false);
      } else {
        setTimeout(check, interval);
      }
    };
    setTimeout(check, 2000);
  });
}

function startPrewarmPing() {
  setInterval(() => {
    // Ping enrollment Streamlit
    const enrollReq = http.get(`http://127.0.0.1:${ENROLL_STREAMLIT_PORT}/_stcore/health`, (res) => {
      res.resume();
    });
    enrollReq.on('error', () => {});
    enrollReq.setTimeout(5000, () => enrollReq.destroy());
    
    // Ping admin Streamlit
    const adminReq = http.get(`http://127.0.0.1:${ADMIN_STREAMLIT_PORT}/_stcore/health`, (res) => {
      res.resume();
    });
    adminReq.on('error', () => {});
    adminReq.setTimeout(5000, () => adminReq.destroy());
  }, PREWARM_INTERVAL_MS);
  log(`Streamlit pre-warm ping started (every ${PREWARM_INTERVAL_MS/1000}s)`);
}

healthServer.listen(port, '0.0.0.0', async () => {
  log(`Health check ready on port ${port}`);
  startEnrollStreamlit();
  startAdminStreamlit();
  await Promise.all([
    waitForStreamlit(ENROLL_STREAMLIT_PORT, 'Enrollment'),
    waitForStreamlit(ADMIN_STREAMLIT_PORT, 'Admin')
  ]);
  startPrewarmPing();
  loadFullApp();
});

async function loadFullApp() {
  try {
    const express = require('express');
    const { createProxyMiddleware } = require('http-proxy-middleware');

    const app = express();

    app.use(express.json());

    app.get('/health', (_req, res) => {
      res.status(200).send('OK');
    });

    app.post('/api/chat', async (req, res) => {
      try {
        const { messages, state } = req.body;
        
        if (!messages || !Array.isArray(messages)) {
          return res.status(400).json({ error: 'Messages array is required' });
        }

        let systemPrompt = BYOV_SYSTEM_PROMPT;
        if (state && state !== 'OTHER') {
          const rate = ['CA', 'WA', 'IL'].includes(state) ? '$0.70' : '$0.57';
          systemPrompt += `\n\nCURRENT USER CONTEXT: The user is in ${state}. Their mileage rate would be ${rate} per mile.`;
        }

        const openaiMessages = [
          { role: 'system', content: systemPrompt },
          ...messages.map(m => ({
            role: m.role,
            content: m.content
          }))
        ];

        const client = getOpenAI();
        if (!client) {
          return res.status(500).json({ error: 'OpenAI service not available' });
        }
        const response = await client.chat.completions.create({
          model: 'gpt-4o',
          messages: openaiMessages,
          max_tokens: 500
        });

        const assistantMessage = response.choices[0]?.message?.content || "I'm sorry, I couldn't generate a response.";
        res.json({ message: assistantMessage });
      } catch (error) {
        console.error('Chat API error:', error);
        res.status(500).json({ error: 'Failed to get response from AI assistant' });
      }
    });

    // Safe socket utilities to prevent "write after end" errors
    function isSocketAlive(socket) {
      return socket && !socket.destroyed && socket.writable !== false;
    }
    
    function safeSocketWrite(socket, data) {
      try {
        if (isSocketAlive(socket)) {
          socket.write(data);
          return true;
        }
      } catch (err) {
        // Silently ignore write errors on dead sockets
      }
      return false;
    }
    
    function safeSocketEnd(socket) {
      try {
        if (socket && !socket.destroyed) {
          socket.end();
        }
      } catch (err) {
        // Silently ignore
      }
    }
    
    function safeSocketDestroy(socket) {
      try {
        if (socket && !socket.destroyed) {
          socket.destroy();
        }
      } catch (err) {
        // Silently ignore
      }
    }
    
    // Track active WebSocket connections for cleanup
    const activeWsSockets = new Set();
    
    function createStreamlitProxyOptions(targetPort, name) {
      return {
        target: `http://127.0.0.1:${targetPort}`,
        changeOrigin: false,
        ws: true,
        xfwd: true,
        followRedirects: false,
        proxyTimeout: 0,
        timeout: 0,
        onProxyReq: (proxyReq, req) => {
          const host = req.headers.host;
          if (host) {
            proxyReq.setHeader('X-Forwarded-Host', host);
            proxyReq.setHeader('X-Forwarded-Proto', 'https');
            proxyReq.setHeader('X-Real-IP', req.socket.remoteAddress || '127.0.0.1');
          }
        },
        onProxyReqWs: (proxyReq, req, socket) => {
          const host = req.headers.host;
          log(`WebSocket upgrade (${name}): ${req.url}`, 'ws');
          if (host) {
            proxyReq.setHeader('X-Forwarded-Host', host);
            proxyReq.setHeader('X-Forwarded-Proto', 'https');
          }
          
          if (!socket._wsListenersAdded) {
            socket._wsListenersAdded = true;
            socket.setMaxListeners(20);
            activeWsSockets.add(socket);
            
            const cleanup = () => {
              activeWsSockets.delete(socket);
              safeSocketDestroy(socket);
            };
            
            socket.once('error', cleanup);
            socket.once('close', cleanup);
          }
        },
        onError: (err, req, res) => {
          if (err.code !== 'ECONNRESET' && err.code !== 'EPIPE') {
            log(`Proxy error (${name}): ${err.code || err.message}`, 'proxy');
          }
          try {
            if (res && typeof res.writeHead === 'function' && !res.headersSent) {
              res.writeHead(503, { 'Content-Type': 'text/html' });
              res.end(`<!DOCTYPE html>
<html>
<head>
  <title>Loading...</title>
  <meta http-equiv="refresh" content="2">
  <style>
    body { font-family: -apple-system, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; background: #f8fafc; }
    .loading { text-align: center; }
    .spinner { width: 40px; height: 40px; border: 4px solid #e2e8f0; border-top-color: #0d6efd; border-radius: 50%; animation: spin 1s linear infinite; margin: 0 auto 16px; }
    @keyframes spin { to { transform: rotate(360deg); } }
    h2 { color: #334155; margin: 0 0 8px; font-size: 18px; }
    p { color: #64748b; margin: 0; font-size: 14px; }
  </style>
</head>
<body>
  <div class="loading">
    <div class="spinner"></div>
    <h2>Starting Application</h2>
    <p>This page will refresh automatically...</p>
  </div>
</body>
</html>`);
            } else if (res && res.destroyed === false) {
              safeSocketEnd(res);
            }
          } catch (e) {
            // Response already sent or socket closed
          }
        },
        onOpen: (proxySocket) => {
          log(`WebSocket opened to ${name} Streamlit`, 'ws');
          
          if (!proxySocket._wsListenersAdded) {
            proxySocket._wsListenersAdded = true;
            proxySocket.setMaxListeners(20);
            activeWsSockets.add(proxySocket);
            
            const cleanup = () => {
              activeWsSockets.delete(proxySocket);
              safeSocketDestroy(proxySocket);
            };
            
            proxySocket.once('error', cleanup);
            proxySocket.once('close', cleanup);
          }
        },
        onClose: (res, socket, head) => {
          log(`WebSocket closed (${name})`, 'ws');
          activeWsSockets.delete(socket);
          safeSocketDestroy(socket);
        }
      };
    }

    // Create separate proxies for enrollment and admin Streamlit apps
    const enrollProxy = createProxyMiddleware(createStreamlitProxyOptions(ENROLL_STREAMLIT_PORT, 'Enrollment'));
    const adminProxy = createProxyMiddleware(createStreamlitProxyOptions(ADMIN_STREAMLIT_PORT, 'Admin'));
    
    // Mount proxies at their respective paths
    // Streamlit apps are started with baseUrlPath matching these paths
    app.use('/enroll', enrollProxy);
    app.use('/admin', adminProxy);

    const distPath = path.resolve(process.cwd(), 'dist/public');
    if (fs.existsSync(distPath)) {
      app.use(express.static(distPath, {
        maxAge: '1d',
        etag: true
      }));
      app.use('*', (_req, res) => {
        res.sendFile(path.resolve(distPath, 'index.html'));
      });
      log(`Serving static files from ${distPath}`);
    } else {
      log(`Warning: dist/public not found at ${distPath}`);
      app.get('*', (_req, res) => {
        res.send('Landing page not built. Visit /app for Streamlit.');
      });
    }

    const newHttpServer = http.createServer(app);

    newHttpServer.on('upgrade', (req, socket, head) => {
      const url = req.url || '';
      log(`WebSocket upgrade: ${url}`, 'ws');
      
      // Only add listeners once per socket to prevent memory leak
      if (!socket._upgradeListenersAdded) {
        socket._upgradeListenersAdded = true;
        socket.setMaxListeners(20);
        socket.once('error', () => safeSocketDestroy(socket));
        socket.once('close', () => safeSocketDestroy(socket));
      }
      
      try {
        // Route WebSocket traffic to appropriate Streamlit app
        if (url.startsWith('/enroll')) {
          enrollProxy.upgrade(req, socket, head);
        } else if (url.startsWith('/admin')) {
          adminProxy.upgrade(req, socket, head);
        } else {
          log(`WS upgrade not handled: ${url}`, 'ws');
          safeSocketWrite(socket, 'HTTP/1.1 404 Not Found\r\n\r\n');
          safeSocketDestroy(socket);
        }
      } catch (err) {
        log(`WS upgrade exception: ${err.message}`, 'ws');
        safeSocketWrite(socket, 'HTTP/1.1 500 Internal Server Error\r\n\r\n');
        safeSocketDestroy(socket);
      }
    });
    
    healthServer.close(() => {
      newHttpServer.listen(port, '0.0.0.0', () => {
        log(`Full server ready on port ${port}`);
        log(`Landing page: /`);
        log(`Enrollment app: /enroll`);
        log(`Admin dashboard: /admin`);
      });
    });

  } catch (err) {
    console.error('CRITICAL: Failed to load full app:', err);
    console.error('Stack:', err.stack);
    process.exit(1);
  }
}

process.on('SIGTERM', () => {
  log('Received SIGTERM, shutting down...');
  if (enrollStreamlitProcess) {
    enrollStreamlitProcess.kill();
  }
  if (adminStreamlitProcess) {
    adminStreamlitProcess.kill();
  }
  process.exit(0);
});

process.on('SIGINT', () => {
  log('Received SIGINT, shutting down...');
  if (enrollStreamlitProcess) {
    enrollStreamlitProcess.kill();
  }
  if (adminStreamlitProcess) {
    adminStreamlitProcess.kill();
  }
  process.exit(0);
});

process.on('uncaughtException', (err) => {
  // Ignore common WebSocket/stream errors that are already handled
  if (err.code === 'ERR_STREAM_WRITE_AFTER_END' ||
      err.code === 'ECONNRESET' ||
      err.code === 'EPIPE' ||
      err.code === 'ERR_STREAM_DESTROYED') {
    log(`Caught and ignored: ${err.code}`, 'error');
    return;
  }
  console.error('[production] Uncaught exception:', err);
});

process.on('unhandledRejection', (reason, promise) => {
  // Ignore common WebSocket/stream errors
  if (reason && (reason.code === 'ERR_STREAM_WRITE_AFTER_END' ||
      reason.code === 'ECONNRESET' ||
      reason.code === 'EPIPE')) {
    return;
  }
  console.error('[production] Unhandled rejection:', reason);
});
