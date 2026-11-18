import assert from 'node:assert/strict';
import { test } from 'node:test';

import { isValidBearer, sign } from '../src/backend.js';
import {
  contentOf,
  mediaOf,
  jidFromWaId,
  normalizeInbound,
  normalizeStatus,
  waIdFromJid,
} from '../src/normalize.js';

const base = {
  key: { remoteJid: '5521998765432@s.whatsapp.net', fromMe: false, id: '3EB0ABC' },
  pushName: 'Maria',
  messageTimestamp: 1_763_400_000,
  message: { conversation: 'Oi, tudo bem?' },
};

test('texto simples vira mensagem do backend', async () => {
  assert.deepEqual(await normalizeInbound(base), {
    id: '3EB0ABC',
    from: '5521998765432',
    name: 'Maria',
    timestamp: 1_763_400_000,
    type: 'text',
    text: 'Oi, tudo bem?',
  });
});

test('mensagem temporária e texto estendido são desembrulhados', async () => {
  const msg = {
    ...base,
    message: { ephemeralMessage: { message: { extendedTextMessage: { text: 'Some em 24h' } } } },
  };
  assert.equal((await normalizeInbound(msg)).text, 'Some em 24h');
});

test('mídia traz o tipo e a legenda', () => {
  assert.deepEqual(contentOf({ imageMessage: { caption: 'RG' } }), { type: 'image', text: 'RG' });
  assert.deepEqual(contentOf({ audioMessage: {} }), { type: 'audio', text: '' });
});

test('ignora grupo, status, mensagem própria e reação', async () => {
  const group = { ...base, key: { ...base.key, remoteJid: '1203630@g.us' } };
  const status = { ...base, key: { ...base.key, remoteJid: 'status@broadcast' } };
  const mine = { ...base, key: { ...base.key, fromMe: true } };
  const reaction = { ...base, message: { reactionMessage: { text: '👍' } } };
  for (const msg of [group, status, mine, reaction]) {
    assert.equal(await normalizeInbound(msg), null);
  }
});

test('contato por LID usa o telefone alternativo quando vem na chave', async () => {
  const msg = {
    ...base,
    key: { ...base.key, remoteJid: '98765@lid', remoteJidAlt: '5521998765432@s.whatsapp.net' },
  };
  assert.equal((await normalizeInbound(msg)).from, '5521998765432');
});

test('contato por LID sem telefone tenta o mapeamento e, sem ele, fica como lid:', async () => {
  const msg = { ...base, key: { ...base.key, remoteJid: '98765@lid' } };
  assert.equal(
    (await normalizeInbound(msg, async () => '5521977776666@s.whatsapp.net')).from,
    '5521977776666',
  );
  assert.equal((await normalizeInbound(msg, async () => null)).from, 'lid:98765');
});

test('jid ↔ wa_id', () => {
  assert.equal(waIdFromJid('5521998765432:12@s.whatsapp.net'), '5521998765432');
  assert.equal(jidFromWaId('5521998765432'), '5521998765432@s.whatsapp.net');
  assert.equal(jidFromWaId('lid:98765'), '98765@lid');
});

test('status só de mensagem enviada por nós', () => {
  const key = { remoteJid: '5521998765432@s.whatsapp.net', fromMe: true, id: 'X1' };
  assert.equal(normalizeStatus({ key, update: { status: 3 } }).status, 'delivered');
  assert.equal(normalizeStatus({ key, update: { status: 4 } }).status, 'read');
  assert.equal(normalizeStatus({ key: { ...key, fromMe: false }, update: { status: 4 } }), null);
  assert.equal(normalizeStatus({ key, update: { status: 1 } }), null);
});

test('assinatura e bearer', () => {
  assert.match(sign('{}', 'segredo'), /^sha256=[0-9a-f]{64}$/);
  assert.equal(isValidBearer('Bearer abc', 'abc'), true);
  assert.equal(isValidBearer('Bearer abd', 'abc'), false);
  assert.equal(isValidBearer(undefined, 'abc'), false);
  assert.equal(isValidBearer('Bearer ', ''), false);
});

test('documento traz metadados da mídia para a ponte baixar', async () => {
  const doc = {
    ...base,
    message: {
      documentWithCaptionMessage: {
        message: {
          documentMessage: {
            mimetype: 'application/pdf',
            fileName: 'contracheque.pdf',
            fileLength: 1234,
            caption: 'segue',
          },
        },
      },
    },
  };
  const item = await normalizeInbound(doc);
  assert.equal(item.type, 'document');
  assert.equal(item.text, 'segue');
  assert.deepEqual(item.media, {
    mimetype: 'application/pdf',
    filename: 'contracheque.pdf',
    size: 1234,
  });
});

test('texto e figurinha não têm mídia para guardar', async () => {
  assert.equal((await normalizeInbound(base)).media, undefined);
  assert.equal(mediaOf({ stickerMessage: { mimetype: 'image/webp' } }), null);
});
