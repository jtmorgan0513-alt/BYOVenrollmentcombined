import http from "http";

const port = parseInt(process.env.PORT || "5000", 10);

const minimalServer = http.createServer((req, res) => {
  if (req.url === "/" || req.url === "/health") {
    res.writeHead(200, { "Content-Type": "text/plain" });
    res.end("OK");
  } else {
    res.writeHead(503, { "Content-Type": "text/plain" });
    res.end("Starting...");
  }
});

minimalServer.listen(port, "0.0.0.0", () => {
  console.log(`[startup] Health check server ready on port ${port}`);
  
  minimalServer.close(() => {
    console.log("[startup] Handing off to main server...");
    require("./index");
  });
});
