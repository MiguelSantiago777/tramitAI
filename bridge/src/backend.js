// Envio de eventos para o backend do TramitAI (webhook assinado com HMAC-SHA256).
// O Baileys não reentrega mensagem: se o backend estiver fora, guardamos em memória e
// tentamos de novo com espera crescente. Nunca logamos o conteúdo.

import { createHmac, timingSafeEqual } from 'node:crypto';

export function sign(body, secret) {
  return 'sha256=' + createHmac('sha256', secret).update(body).digest('hex');
}

export function isValidBearer(header, secret) {
  if (!secret || typeof header !== 'string' || !header.startsWith('Bearer ')) {
    return false;
  }
  const given = Buffer.from(header.slice(7));
  const expected = Buffer.from(secret);
  return given.length === expected.length && timingSafeEqual(given, expected);
}

const MAX_ATTEMPTS = 12; // ~ até 1h de espera acumulada

export class BackendClient {
  constructor({ url, secret, logger, fetchImpl = fetch }) {
    this.url = url;
    this.secret = secret;
    this.logger = logger;
    this.fetch = fetchImpl;
  }

  /** Entrega com retry em segundo plano. Não lança. */
  deliver(event) {
    void this.#attempt(event, 1);
  }

  async #attempt(event, attempt) {
    const body = JSON.stringify(event);
    try {
      const response = await this.fetch(this.url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Bridge-Signature': sign(body, this.secret),
        },
        body,
        signal: AbortSignal.timeout(10_000),
      });
      if (response.ok) {
        return;
      }
      if (response.status >= 400 && response.status < 500 && response.status !== 429) {
        this.logger.error({ status: response.status, kind: event.event }, 'backend recusou o evento');
        return;
      }
      throw new Error(`http ${response.status}`);
    } catch (error) {
      if (attempt >= MAX_ATTEMPTS) {
        this.logger.error({ kind: event.event, session: event.session_id }, 'evento descartado');
        return;
      }
      const delay = Math.min(1000 * 2 ** attempt, 10 * 60_000);
      this.logger.warn(
        { kind: event.event, attempt, err: error.message },
        'backend indisponível, nova tentativa',
      );
      setTimeout(() => void this.#attempt(event, attempt + 1), delay).unref();
    }
  }
}
