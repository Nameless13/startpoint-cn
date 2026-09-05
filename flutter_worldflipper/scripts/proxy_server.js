#!/usr/bin/env node
/**
 * Flutter Web CORS 代理服务器
 *
 * 解决 Flutter Web 开发时的跨域问题：
 * - 监听本地端口 8888
 * - 将请求转发到远程服务器 100.67.116.109:8088
 * - 在响应中添加 CORS 头
 *
 * 启动方式：
 *   node scripts/proxy_server.js
 *
 * Flutter Web 运行方式：
 *   flutter run -d chrome --dart-define=SERVER_URL=http://localhost:8888
 */

const http = require('http');
const https = require('https');
const url = require('url');

const PROXY_PORT = 8888;
const TARGET_HOST = '100.67.116.109';
const TARGET_PORT = 8088;
const TARGET_PROTOCOL = 'http:';

function addCorsHeaders(res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  res.setHeader('Access-Control-Max-Age', '86400');
}

function proxyRequest(req, res) {
  // 处理 OPTIONS 预检请求
  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
      'Access-Control-Max-Age': '86400',
      'Content-Length': '0',
    });
    res.end();
    return;
  }

  const targetUrl = url.parse(`${TARGET_PROTOCOL}//${TARGET_HOST}:${TARGET_PORT}${req.url}`);

  const options = {
    hostname: targetUrl.hostname,
    port: targetUrl.port,
    path: targetUrl.path,
    method: req.method,
    headers: {
      ...req.headers,
      host: `${TARGET_HOST}:${TARGET_PORT}`,
    },
  };

  const proxyReq = http.request(options, (proxyRes) => {
    res.writeHead(proxyRes.statusCode, proxyRes.headers);
    proxyRes.pipe(res, { end: true });
  });

  proxyReq.on('error', (error) => {
    console.error('[Proxy Error]', error.message);
    res.writeHead(500, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Proxy error', message: error.message }));
  });

  // 复制请求体
  req.pipe(proxyReq, { end: true });
}

const server = http.createServer(proxyRequest);

server.listen(PROXY_PORT, () => {
  console.log(`[Proxy] CORS proxy server running on http://localhost:${PROXY_PORT}`);
  console.log(`[Proxy] Forwarding to ${TARGET_HOST}:${TARGET_PORT}`);
  console.log(`[Proxy] Run Flutter with: flutter run -d chrome --dart-define=SERVER_URL=http://localhost:8888`);
});
