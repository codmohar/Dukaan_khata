const http = require("http");
const net = require("net");

const PORT = 4000;

const server = http.createServer((req, res) => {
  const isApi = req.url.startsWith("/api/");
  const targetPort = isApi ? 8000 : 3000;
  const targetPath = isApi ? req.url.replace(/^\/api/, "") : req.url;

  const headers = { ...req.headers, host: `127.0.0.1:${targetPort}` };
  const proxyReq = http.request(
    {
      hostname: "127.0.0.1",
      port: targetPort,
      path: targetPath || "/",
      method: req.method,
      headers,
    },
    (proxyRes) => {
      res.writeHead(proxyRes.statusCode || 500, proxyRes.headers);
      proxyRes.pipe(res, { end: true });
    }
  );

  proxyReq.on("error", (err) => {
    res.writeHead(502, { "Content-Type": "text/plain" });
    res.end("Proxy error: " + err.message);
  });

  req.pipe(proxyReq, { end: true });
});

server.on("upgrade", (req, socket, head) => {
  const isWs = req.url.startsWith("/ws/");
  const targetPort = isWs ? 8000 : 3000;

  const targetSocket = net.connect(targetPort, "127.0.0.1", () => {
    let raw = `${req.method} ${req.url} HTTP/${req.httpVersion}\r\n`;
    for (let i = 0; i < req.rawHeaders.length; i += 2) {
      const k = req.rawHeaders[i];
      const v =
        k.toLowerCase() === "host"
          ? `127.0.0.1:${targetPort}`
          : req.rawHeaders[i + 1];
      raw += `${k}: ${v}\r\n`;
    }
    raw += "\r\n";
    targetSocket.write(raw);
    if (head && head.length) targetSocket.write(head);
    targetSocket.pipe(socket);
    socket.pipe(targetSocket);
  });

  targetSocket.on("error", () => socket.destroy());
  socket.on("error", () => targetSocket.destroy());
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`DukaanAI Unified Proxy listening on http://0.0.0.0:${PORT}`);
});

