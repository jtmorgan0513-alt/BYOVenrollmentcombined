import http from "http";
import { spawn, ChildProcess } from "child_process";
import path from "path";
import fs from "fs";

const port = parseInt(process.env.PORT || "3000", 10);
const STREAMLIT_PORT = 8000;

let streamlitProcess: ChildProcess | null = null;

function log(message: string, source = "production") {
  const time = new Date().toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
  });
  console.log(`${time} [${source}] ${message}`);
}

function startStreamlit() {
  log("Starting Streamlit backend...");
  streamlitProcess = spawn("streamlit", [
    "run",
    "byov_app.py",
    "--server.port", String(STREAMLIT_PORT),
    "--server.address", "0.0.0.0",
    "--server.headless", "true",
    "--server.enableCORS", "false",
    "--server.enableXsrfProtection", "false"
  ], {
    stdio: ["ignore", "pipe", "pipe"],
    cwd: process.cwd()
  });

  streamlitProcess.stdout?.on("data", (data) => {
    log(data.toString().trim(), "streamlit");
  });

  streamlitProcess.stderr?.on("data", (data) => {
    log(data.toString().trim(), "streamlit");
  });

  streamlitProcess.on("error", (err) => {
    log(`Streamlit error: ${err.message}`, "streamlit");
  });

  streamlitProcess.on("exit", (code) => {
    log(`Streamlit exited with code ${code}`, "streamlit");
    if (code !== 0) {
      setTimeout(startStreamlit, 5000);
    }
  });
}

const healthServer = http.createServer((req, res) => {
  if (req.url === "/health" || req.url === "/") {
    res.writeHead(200, { "Content-Type": "text/plain" });
    res.end("OK");
    return;
  }
  res.writeHead(503);
  res.end("Loading...");
});

healthServer.listen(port, "0.0.0.0", () => {
  log(`Health check ready on port ${port}`);
  startStreamlit();
  loadFullApp();
});

async function loadFullApp() {
  try {
    const express = await import("express");
    const { createProxyMiddleware } = await import("http-proxy-middleware");

    const app = express.default();

    app.get("/health", (_req, res) => {
      res.status(200).send("OK");
    });

    app.use("/app", createProxyMiddleware({
      target: `http://127.0.0.1:${STREAMLIT_PORT}`,
      changeOrigin: true,
      pathRewrite: { "^/app": "" },
      ws: true,
      onError: (err, _req, res) => {
        log(`Proxy error: ${err.message}`, "proxy");
        if (res && typeof res.writeHead === 'function') {
          res.writeHead(502);
          (res as http.ServerResponse).end("Streamlit is starting up...");
        }
      }
    }));

    app.use("/_stcore", createProxyMiddleware({
      target: `http://127.0.0.1:${STREAMLIT_PORT}`,
      changeOrigin: true,
      ws: true
    }));

    app.use("/static", createProxyMiddleware({
      target: `http://127.0.0.1:${STREAMLIT_PORT}`,
      changeOrigin: true
    }));

    const distPath = path.resolve(process.cwd(), "dist/public");
    if (fs.existsSync(distPath)) {
      app.use(express.default.static(distPath, {
        maxAge: "1d",
        etag: true
      }));
      app.use("*", (_req, res) => {
        res.sendFile(path.resolve(distPath, "index.html"));
      });
      log(`Serving static files from ${distPath}`);
    } else {
      log(`Warning: dist/public not found at ${distPath}`);
      app.get("*", (_req, res) => {
        res.send("Landing page not built. Visit /app for Streamlit.");
      });
    }

    const newHttpServer = http.createServer(app);
    
    healthServer.close(() => {
      newHttpServer.listen(port, "0.0.0.0", () => {
        log(`Full server ready on port ${port}`);
        log(`Landing page: /`);
        log(`Streamlit app: /app`);
      });
    });

  } catch (err) {
    console.error("Failed to load full app:", err);
  }
}

process.on("SIGTERM", () => {
  log("Received SIGTERM, shutting down...");
  if (streamlitProcess) {
    streamlitProcess.kill();
  }
  process.exit(0);
});

process.on("SIGINT", () => {
  log("Received SIGINT, shutting down...");
  if (streamlitProcess) {
    streamlitProcess.kill();
  }
  process.exit(0);
});

process.on("uncaughtException", (err) => {
  console.error("[production] Uncaught exception:", err);
});
