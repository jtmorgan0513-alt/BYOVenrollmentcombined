import http from "http";
import compression from "compression";
import type { Express } from "express";

const port = parseInt(process.env.PORT || "5000", 10);

function formatTime() {
  return new Date().toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
  });
}

export function log(message: string, source = "express") {
  console.log(`${formatTime()} [${source}] ${message}`);
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

let expressHandler: ((req: http.IncomingMessage, res: http.ServerResponse) => void) | null = null;

const httpServer = http.createServer((req, res) => {
  if (expressHandler) {
    expressHandler(req, res);
  } else if (req.url === "/health") {
    res.writeHead(200, { "Content-Type": "text/plain" });
    res.end("OK");
  } else {
    res.writeHead(200, { "Content-Type": "text/html" });
    res.end(loadingPage);
  }
});

httpServer.listen(port, "0.0.0.0", () => {
  log(`Health check ready on port ${port}`);
  loadFullApp();
});

async function loadFullApp() {
  try {
    const express = await import("express");
    const { registerRoutes } = await import("./routes");
    const { serveStatic } = await import("./static");

    const app = express.default();

    app.use(compression({
      level: 6,
      threshold: 1024,
      filter: (req, res) => {
        if (req.headers['x-no-compression']) {
          return false;
        }
        return compression.filter(req, res);
      }
    }));

    app.get('/health', (_req, res) => {
      res.status(200).send('OK');
    });

    app.use(express.default.json());
    app.use(express.default.urlencoded({ extended: false }));

    app.use((req, res, next) => {
      res.set({
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'
      });
      next();
    });

    await registerRoutes(httpServer, app);

    if (process.env.NODE_ENV === "production") {
      serveStatic(app);
    } else {
      const { setupVite } = await import("./vite");
      await setupVite(httpServer, app);
    }

    expressHandler = app;
    log(`Full server ready on port ${port}`);

  } catch (err) {
    console.error("Failed to load full app:", err);
  }
}
