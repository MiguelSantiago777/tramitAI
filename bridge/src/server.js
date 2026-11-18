// API interna da ponte WhatsApp. Só o backend fala com ela (rede interna do Docker),
// sempre com `Authorization: Bearer <WHATSAPP_BRIDGE_SECRET>`.
//
//   GET    /health
//   GET    /sessions/:id              → { status, qr, phone }
//   POST   /sessions/:id/start        → { status, qr, phone }
//   DELETE /sessions/:id              → desconecta e apaga a sessão
//   POST   /sessions/:id/messages     { to, text } → { id }
//   GET    /sessions/:id/media/:msgId  → arquivo (Content-Type + X-File-Name)
//   DELETE /sessions/:id/media/:msgId  → apaga a cópia temporária

import { createServer } from 'node:http';

import pino from 'pino';

import { BackendClient, isValidBearer } from './backend.js';
import { MEDIA_TTL_MS, MediaStore } from './media.js';
import { SESSION_ID, SendError, SessionManager } from './sessions.js';

const PORT = Number(process.env.PORT ?? 3100);
const SECRET = process.env.WHATSAPP_BRIDGE_SECRET ?? '';
const WEBHOOK_URL = process.env.BACKEND_WEBHOOK_URL ?? 'http://backend:8000/api/webhooks/bridge/';
const DATA_DIR = process.env.DATA_DIR ?? '/data';
const MAX_BODY = 64 * 1024;

const logger = pino({ level: process.env.LOG_LEVEL ?? 'info' });
if (SECRET.length < 32) {
  logger.fatal('WHATSAPP_BRIDGE_SECRET ausente ou curto (mínimo 32 caracteres)');
  process.exit(1);
}

const backend = new BackendClient({ url: WEBHOOK_URL, secret: SECRET, logger });
const media = new MediaStore(DATA_DIR);
const sessions = new SessionManager({ dataDir: DATA_DIR, backend, logger, media });

function send(res, status, body) {
  const payload = body === undefined ? '' : JSON.stringify(body);
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(payload);
}

async function readJson(req) {
  let size = 0;
  const chunks = [];
  for await (const chunk of req) {
    size += chunk.length;
    if (size > MAX_BODY) {
      throw new SendError('body_too_large', 413);
    }
    chunks.push(chunk);
  }
  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');
  } catch {
    throw new SendError('invalid_json', 400);
  }
}

async function route(req, res) {
  const url = new URL(req.url ?? '/', 'http://bridge');
  if (req.method === 'GET' && url.pathname === '/health') {
    return send(res, 200, { ok: true, sessions: sessions.sessions.size });
  }
  if (!isValidBearer(req.headers.authorization, SECRET)) {
    return send(res, 401, { error: 'unauthorized' });
  }
  const mediaMatch = url.pathname.match(/^\/sessions\/([^/]+)\/media\/([^/]+)$/);
  if (mediaMatch && SESSION_ID.test(mediaMatch[1])) {
    const [, sessionId, mediaId] = mediaMatch;
    if (req.method === 'GET') {
      const found = await media.read(sessionId, mediaId);
      if (!found) {
        return send(res, 404, { error: 'not_found' });
      }
      res.writeHead(200, {
        'Content-Type': found.meta.mimetype || 'application/octet-stream',
        'Content-Length': found.buffer.length,
        'X-File-Name': encodeURIComponent(found.meta.filename || ''),
      });
      return res.end(found.buffer);
    }
    if (req.method === 'DELETE') {
      await media.remove(sessionId, mediaId);
      return send(res, 204);
    }
    return send(res, 405, { error: 'method_not_allowed' });
  }

  const match = url.pathname.match(/^\/sessions\/([^/]+)(\/start|\/messages)?$/);
  if (!match || !SESSION_ID.test(match[1])) {
    return send(res, 404, { error: 'not_found' });
  }
  const [, id, action] = match;

  if (req.method === 'GET' && !action) {
    return send(res, 200, sessions.info(id));
  }
  if (req.method === 'POST' && action === '/start') {
    return send(res, 200, await sessions.start(id));
  }
  if (req.method === 'DELETE' && !action) {
    await sessions.logout(id);
    return send(res, 204);
  }
  if (req.method === 'POST' && action === '/messages') {
    const body = await readJson(req);
    if (typeof body.to !== 'string' || typeof body.text !== 'string' || !body.text.trim()) {
      return send(res, 400, { error: 'invalid_message' });
    }
    const messageId = await sessions.sendText(id, body.to, body.text);
    return send(res, 200, { id: messageId });
  }
  return send(res, 405, { error: 'method_not_allowed' });
}

const server = createServer((req, res) => {
  route(req, res).catch((error) => {
    if (error instanceof SendError) {
      return send(res, error.status, { error: error.code });
    }
    logger.error({ err: error.message }, 'erro inesperado');
    return send(res, 500, { error: 'internal' });
  });
});

await sessions.restore();
// Limpa cópias de mídia que o backend nunca buscou (ex.: backend fora por dias).
setInterval(() => {
  media.purge(MEDIA_TTL_MS).then(
    (removed) => removed && logger.info({ removed }, 'mídias antigas apagadas'),
    () => undefined,
  );
}, 60 * 60 * 1000).unref();
server.listen(PORT, () => logger.info({ port: PORT }, 'ponte WhatsApp no ar'));

for (const signal of ['SIGTERM', 'SIGINT']) {
  process.on(signal, async () => {
    server.close();
    await sessions.close();
    process.exit(0);
  });
}
