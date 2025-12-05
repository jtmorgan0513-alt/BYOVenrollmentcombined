import http from "http";

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

const httpServer = http.createServer((req, res) => {
  if (req.url === "/" || req.url === "/health") {
    res.writeHead(200, { "Content-Type": "text/html" });
    res.end("<!DOCTYPE html><html><head><title>BYOV</title></head><body>OK</body></html>");
  } else {
    res.writeHead(503);
    res.end("Loading...");
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

    const newHttpServer = http.createServer(app);
    await registerRoutes(newHttpServer, app);

    if (process.env.NODE_ENV === "production") {
      serveStatic(app);
    } else {
      const { setupVite } = await import("./vite");
      await setupVite(newHttpServer, app);
    }

    httpServer.close(() => {
      newHttpServer.listen(port, "0.0.0.0", () => {
        log(`Full server ready on port ${port}`);
      });
    });

  } catch (err) {
    console.error("Failed to load full app:", err);
  }
}
