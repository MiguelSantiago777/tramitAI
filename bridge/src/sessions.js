// Sessões do WhatsApp (uma por número de escritório) via Baileys.
//
// Cuidados:
// - Nunca logar conteúdo de mensagem nem telefone (só ids técnicos e contagens).
// - A pasta da sessão é um segredo: dá acesso total ao WhatsApp do escritório.
// - Envio com ritmo humano (digitando..., intervalo mínimo) para reduzir risco de bloqueio.

import { mkdir, readdir, rm } from 'node:fs/promises';
import { join } from 'node:path';

import makeWASocket, {
  Browsers,
  DisconnectReason,
  downloadMediaMessage,
  fetchLatestBaileysVersion,
  jidDecode,
  useMultiFileAuthState,
} from 'baileys';
import QRCode from 'qrcode';

import { MAX_MEDIA_BYTES, jidFromWaId, normalizeInbound, normalizeStatus } from './normalize.js';

export const SESSION_ID = /^[a-z0-9_-]{6,64}$/;

const MIN_SEND_INTERVAL_MS = 2_000;
const TYPING_MIN_MS = 1_000;
const TYPING_MAX_MS = 2_500;

export class SendError extends Error {
  constructor(code, status) {
    super(code);
    this.code = code;
    this.status = status;
  }
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const jitter = (min, max) => min + Math.floor(Math.random() * (max - min));

export class SessionManager {
  /** @param {{ dataDir: string, backend: import('./backend.js').BackendClient, logger: any, media?: import('./media.js').MediaStore }} opts */
  constructor({ dataDir, backend, logger, media }) {
    this.dir = join(dataDir, 'sessions');
    this.backend = backend;
    this.media = media ?? null;
    this.logger = logger;
    /** @type {Map<string, any>} */
    this.sessions = new Map();
    this.version = null;
  }

  /** Reabre as sessões que já estavam pareadas (reinício do container). */
  async restore() {
    await mkdir(this.dir, { recursive: true });
    const ids = (await readdir(this.dir)).filter((id) => SESSION_ID.test(id));
    for (const id of ids) {
      await this.start(id);
    }
    this.logger.info({ count: ids.length }, 'sessões restauradas');
  }

  info(id) {
    const s = this.sessions.get(id);
    if (!s) {
      return { status: 'not_started', qr: null, phone: null };
    }
    return { status: s.status, qr: s.qr, phone: s.phone };
  }

  async start(id) {
    const current = this.sessions.get(id);
    if (current && ['connecting', 'qr', 'open'].includes(current.status)) {
      return this.info(id);
    }
    const session = current ?? {
      id,
      status: 'connecting',
      qr: null,
      phone: null,
      sock: null,
      queue: Promise.resolve(),
      lastSendAt: 0,
      reconnectDelay: 1_000,
      jidCache: new Map(),
    };
    session.status = 'connecting';
    session.qr = null;
    this.sessions.set(id, session);
    await this.#connect(session);
    return this.info(id);
  }

  async logout(id) {
    const s = this.sessions.get(id);
    if (s?.sock) {
      s.stopped = true;
      try {
        await s.sock.logout();
      } catch {
        // já desconectado: segue limpando
      }
    }
    this.sessions.delete(id);
    await rm(join(this.dir, id), { recursive: true, force: true });
    this.#notify(id, 'logged_out', null);
  }

  async #latestVersion() {
    if (!this.version) {
      try {
        const { version } = await fetchLatestBaileysVersion();
        this.version = version;
      } catch {
        this.version = undefined; // usa a versão embutida no Baileys
      }
    }
    return this.version;
  }

  async #connect(session) {
    const folder = join(this.dir, session.id);
    await mkdir(folder, { recursive: true });
    const { state, saveCreds } = await useMultiFileAuthState(folder);
    const version = await this.#latestVersion();

    const sock = makeWASocket({
      ...(version ? { version } : {}),
      auth: state,
      logger: this.logger.child({ session: session.id }, { level: 'error' }),
      browser: Browsers.ubuntu('TramitAI'),
      markOnlineOnConnect: false,
      syncFullHistory: false,
      shouldIgnoreJid: (jid) => !(jid.endsWith('@s.whatsapp.net') || jid.endsWith('@lid')),
    });
    session.sock = sock;
    session.stopped = false;

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', async (update) => {
      if (session.sock !== sock) {
        return; // socket antigo
      }
      if (update.qr) {
        session.status = 'qr';
        session.qr = await QRCode.toDataURL(update.qr, { margin: 1, width: 280 });
      }
      if (update.connection === 'open') {
        session.status = 'open';
        session.qr = null;
        session.reconnectDelay = 1_000;
        session.phone = jidDecode(sock.user?.id)?.user ?? null;
        this.logger.info({ session: session.id }, 'sessão conectada');
        this.#notify(session.id, 'open', session.phone);
      }
      if (update.connection === 'close') {
        this.#onClose(session, update.lastDisconnect?.error, state.creds.registered);
      }
    });

    sock.ev.on('messages.upsert', async ({ messages, type }) => {
      if (type !== 'notify') {
        return; // histórico/sincronização: não reprocessar
      }
      const resolvePn = (lid) => sock.signalRepository?.lidMapping?.getPNForLID(lid) ?? null;
      const normalized = [];
      for (const msg of messages) {
        try {
          const item = await normalizeInbound(msg, resolvePn);
          if (item) {
            if (item.media) {
              await this.#keepMedia(session, sock, msg, item);
            }
            normalized.push(item);
          }
        } catch (error) {
          this.logger.warn({ session: session.id, err: error.message }, 'mensagem ignorada');
        }
      }
      if (normalized.length > 0) {
        this.backend.deliver({ session_id: session.id, event: 'messages', messages: normalized });
      }
    });

    sock.ev.on('messages.update', (updates) => {
      const statuses = updates.map(normalizeStatus).filter(Boolean);
      if (statuses.length > 0) {
        this.backend.deliver({ session_id: session.id, event: 'statuses', statuses });
      }
    });
  }

  /** Baixa a mídia agora (depois não dá) e guarda a cópia para o backend buscar. */
  async #keepMedia(session, sock, msg, item) {
    if (!this.media) {
      return;
    }
    if (item.media.size > MAX_MEDIA_BYTES) {
      item.media.error = 'too_large';
      return;
    }
    try {
      const buffer = await downloadMediaMessage(
        msg,
        'buffer',
        {},
        {
          logger: this.logger.child({ session: session.id }, { level: 'error' }),
          reuploadRequest: sock.updateMediaMessage,
        },
      );
      if (buffer.length > MAX_MEDIA_BYTES) {
        item.media.error = 'too_large';
        return;
      }
      await this.media.save(session.id, item.id, buffer, {
        mimetype: item.media.mimetype,
        filename: item.media.filename,
      });
      item.media.size = buffer.length;
    } catch (error) {
      item.media.error = 'download_failed';
      this.logger.warn({ session: session.id, err: error.message }, 'mídia não baixada');
    }
  }

  #onClose(session, error, registered) {
    const code = error?.output?.statusCode;
    session.sock = null;
    if (session.stopped) {
      return;
    }
    if (code === DisconnectReason.loggedOut) {
      // Desconectado pelo celular ("Aparelhos conectados" → sair): precisa parear de novo.
      session.status = 'logged_out';
      session.qr = null;
      this.logger.warn({ session: session.id }, 'sessão encerrada pelo aparelho');
      void rm(join(this.dir, session.id), { recursive: true, force: true });
      this.#notify(session.id, 'logged_out', null);
      return;
    }
    if (!registered && code === DisconnectReason.timedOut) {
      // QR expirou sem ninguém ler: para, até pedirem de novo.
      session.status = 'closed';
      session.qr = null;
      return;
    }
    session.status = 'connecting';
    const delay = code === DisconnectReason.restartRequired ? 0 : session.reconnectDelay;
    session.reconnectDelay = Math.min(session.reconnectDelay * 2, 60_000);
    this.logger.warn({ session: session.id, code, delay }, 'conexão caiu, reconectando');
    if (registered) {
      this.#notify(session.id, 'connecting', session.phone);
    }
    setTimeout(() => {
      if (!session.stopped && this.sessions.get(session.id) === session) {
        void this.#connect(session).catch((err) =>
          this.logger.error({ session: session.id, err: err.message }, 'falha ao reconectar'),
        );
      }
    }, delay).unref();
  }

  #notify(id, status, phone) {
    this.backend.deliver({ session_id: id, event: 'connection', status, phone });
  }

  /** Envia texto em fila por sessão, com ritmo humano. Devolve o id da mensagem. */
  sendText(id, to, text) {
    const session = this.sessions.get(id);
    if (!session || session.status !== 'open' || !session.sock) {
      return Promise.reject(new SendError('not_connected', 409));
    }
    const job = session.queue.then(() => this.#send(session, to, text));
    session.queue = job.catch(() => undefined);
    return job;
  }

  async #send(session, to, text) {
    const sock = session.sock;
    if (!sock || session.status !== 'open') {
      throw new SendError('not_connected', 409);
    }
    const jid = await this.#resolveJid(session, to);
    const wait = session.lastSendAt + MIN_SEND_INTERVAL_MS - Date.now();
    if (wait > 0) {
      await sleep(wait);
    }
    try {
      await sock.sendPresenceUpdate('composing', jid);
      await sleep(jitter(TYPING_MIN_MS, TYPING_MAX_MS));
      await sock.sendPresenceUpdate('paused', jid);
    } catch {
      // presença é cosmética
    }
    const sent = await sock.sendMessage(jid, { text });
    session.lastSendAt = Date.now();
    if (!sent?.key?.id) {
      throw new SendError('uncertain', 502);
    }
    return sent.key.id;
  }

  /** Número → JID real (o WhatsApp decide se o 9º dígito entra). */
  async #resolveJid(session, to) {
    if (to.startsWith('lid:')) {
      return jidFromWaId(to);
    }
    const digits = to.replace(/\D/g, '');
    const cached = session.jidCache.get(digits);
    if (cached) {
      return cached;
    }
    let result;
    try {
      [result] = (await session.sock.onWhatsApp(digits)) ?? [];
    } catch {
      throw new SendError('lookup_failed', 503);
    }
    if (!result?.exists) {
      throw new SendError('not_on_whatsapp', 422);
    }
    session.jidCache.set(digits, result.jid);
    return result.jid;
  }

  async close() {
    for (const s of this.sessions.values()) {
      s.stopped = true;
      s.sock?.end?.(undefined);
    }
  }
}
