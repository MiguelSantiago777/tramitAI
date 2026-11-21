import assert from 'node:assert/strict';
import { test } from 'node:test';

import { mediaContent } from '../src/normalize.js';

const buffer = Buffer.from('%PDF-1.4');

test('documento leva nome e legenda', () => {
  const content = mediaContent({
    kind: 'document',
    buffer,
    mimetype: 'application/pdf',
    fileName: 'procuracao.pdf',
    caption: 'Segue a procuração',
  });
  assert.equal(content.document, buffer);
  assert.equal(content.fileName, 'procuracao.pdf');
  assert.equal(content.caption, 'Segue a procuração');
});

test('áudio sai sem legenda e não como mensagem de voz', () => {
  const content = mediaContent({ kind: 'audio', buffer, mimetype: 'audio/mpeg', caption: 'x' });
  assert.equal(content.audio, buffer);
  assert.equal(content.ptt, false);
  assert.equal('caption' in content, false);
});

test('tipo desconhecido é recusado', () => {
  assert.equal(mediaContent({ kind: 'sticker', buffer }), null);
});
