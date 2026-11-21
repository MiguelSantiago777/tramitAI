// Conversão das mensagens do Baileys para o formato que o backend do TramitAI entende.
// Funções puras (sem socket): testáveis com node --test.

const STATUS_MAP = {
  0: 'failed', // ERROR
  2: 'sent', // SERVER_ACK
  3: 'delivered', // DELIVERY_ACK
  4: 'read', // READ
  5: 'read', // PLAYED (áudio)
};

/** Desembrulha mensagens temporárias, "ver uma vez" e documento com legenda. */
export function unwrap(message) {
  let current = message;
  for (let i = 0; i < 5 && current; i++) {
    const inner =
      current.ephemeralMessage?.message ??
      current.viewOnceMessage?.message ??
      current.viewOnceMessageV2?.message ??
      current.viewOnceMessageV2Extension?.message ??
      current.documentWithCaptionMessage?.message ??
      current.editedMessage?.message;
    if (!inner) {
      break;
    }
    current = inner;
  }
  return current ?? null;
}

/** Tipo e texto da mensagem. `null` = não é conteúdo de conversa (reação, apagar, sistema). */
export function contentOf(message) {
  const m = unwrap(message);
  if (!m) {
    return null;
  }
  if (typeof m.conversation === 'string') {
    return { type: 'text', text: m.conversation };
  }
  if (m.extendedTextMessage) {
    return { type: 'text', text: m.extendedTextMessage.text ?? '' };
  }
  if (m.imageMessage) {
    return { type: 'image', text: m.imageMessage.caption ?? '' };
  }
  if (m.videoMessage) {
    return { type: 'video', text: m.videoMessage.caption ?? '' };
  }
  if (m.audioMessage) {
    return { type: 'audio', text: '' };
  }
  if (m.documentMessage) {
    return { type: 'document', text: m.documentMessage.caption ?? '' };
  }
  if (m.stickerMessage) {
    return { type: 'sticker', text: '' };
  }
  if (m.locationMessage || m.liveLocationMessage) {
    return { type: 'location', text: '' };
  }
  if (m.contactMessage || m.contactsArrayMessage) {
    return { type: 'other', text: '' };
  }
  // protocolMessage (apagar/editar), reactionMessage, senderKeyDistributionMessage...
  return null;
}

/** Limite de mídia que a ponte baixa (igual ao DOCUMENT_MAX_BYTES do backend). */
export const MAX_MEDIA_BYTES = 25 * 1024 * 1024;

/** Metadados da mídia que vale guardar na pasta do cliente (figurinha não entra). */
export function mediaOf(message) {
  const m = unwrap(message);
  const media = m?.imageMessage ?? m?.videoMessage ?? m?.audioMessage ?? m?.documentMessage;
  if (!media) {
    return null;
  }
  const size = Number(media.fileLength?.toString?.() ?? media.fileLength ?? 0) || 0;
  return {
    mimetype: String(media.mimetype ?? '').slice(0, 100),
    filename: String(m.documentMessage?.fileName ?? '').slice(0, 200),
    size,
  };
}

/** "5521998765432@s.whatsapp.net" → "5521998765432"; "123@lid" → "lid:123". */
export function waIdFromJid(jid) {
  if (!jid || typeof jid !== 'string') {
    return null;
  }
  const [user, server] = jid.split('@');
  const digits = (user ?? '').split(':')[0];
  if (!digits) {
    return null;
  }
  if (server === 's.whatsapp.net') {
    return digits;
  }
  if (server === 'lid') {
    return `lid:${digits}`;
  }
  return null;
}

/** Inverso de waIdFromJid, para enviar. */
export function jidFromWaId(waId) {
  if (waId.startsWith('lid:')) {
    return `${waId.slice(4)}@lid`;
  }
  return `${waId.replace(/\D/g, '')}@s.whatsapp.net`;
}

/** Conversa individual? (descarta grupo, status, canal e broadcast) */
export function isDirectChat(jid) {
  return typeof jid === 'string' && (jid.endsWith('@s.whatsapp.net') || jid.endsWith('@lid'));
}

function toSeconds(value) {
  if (value == null) {
    return Math.floor(Date.now() / 1000);
  }
  if (typeof value === 'number') {
    return value;
  }
  if (typeof value === 'object' && typeof value.toNumber === 'function') {
    return value.toNumber();
  }
  const n = Number(value);
  return Number.isFinite(n) ? n : Math.floor(Date.now() / 1000);
}

/**
 * Mensagem recebida → formato do backend, ou null para ignorar.
 * `resolvePn(lidJid)` devolve o JID com telefone quando o contato chega como LID.
 */
export async function normalizeInbound(msg, resolvePn) {
  const key = msg?.key;
  if (!key || key.fromMe || !isDirectChat(key.remoteJid)) {
    return null;
  }
  const content = contentOf(msg.message);
  if (!content) {
    return null;
  }
  let jid = key.remoteJid;
  if (jid.endsWith('@lid')) {
    const alt = key.remoteJidAlt;
    if (alt && alt.endsWith('@s.whatsapp.net')) {
      jid = alt;
    } else if (resolvePn) {
      jid = (await resolvePn(jid)) ?? jid;
    }
  }
  const from = waIdFromJid(jid);
  if (!from || !key.id) {
    return null;
  }
  const item = {
    id: key.id,
    from,
    name: msg.pushName ?? '',
    timestamp: toSeconds(msg.messageTimestamp),
    type: content.type,
    text: content.text,
  };
  const media = mediaOf(msg.message);
  if (media) {
    item.media = media;
  }
  return item;
}

/** Atualização de status de mensagem ENVIADA por nós → formato do backend, ou null. */
export function normalizeStatus(update) {
  const key = update?.key;
  const status = STATUS_MAP[update?.update?.status];
  if (!key?.fromMe || !key.id || !status || !isDirectChat(key.remoteJid)) {
    return null;
  }
  return { id: key.id, status, timestamp: Math.floor(Date.now() / 1000) };
}

/** Conteúdo do Baileys para enviar um arquivo. Tipo desconhecido: null. */
export function mediaContent({ kind, buffer, mimetype, fileName, caption }) {
  const text = caption || undefined;
  switch (kind) {
    case 'image':
      return { image: buffer, mimetype, caption: text };
    case 'video':
      return { video: buffer, mimetype, caption: text };
    case 'audio':
      // Arquivo de áudio comum, não mensagem de voz; o WhatsApp não aceita legenda em áudio.
      return { audio: buffer, mimetype, ptt: false };
    case 'document':
      return { document: buffer, mimetype, fileName: fileName || 'arquivo', caption: text };
    default:
      return null;
  }
}
