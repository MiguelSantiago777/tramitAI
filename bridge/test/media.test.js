import assert from 'node:assert/strict';
import { mkdtemp, rm, utimes } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';

import { MediaStore } from '../src/media.js';

test('guarda, lê, apaga e limpa mídias antigas', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'bridge-media-'));
  try {
    const store = new MediaStore(dir);
    await store.save('sessao-a', '3EB0ABC', Buffer.from('pdf'), {
      mimetype: 'application/pdf',
      filename: 'a.pdf',
    });
    const found = await store.read('sessao-a', '3EB0ABC');
    assert.equal(found.buffer.toString(), 'pdf');
    assert.equal(found.meta.filename, 'a.pdf');

    assert.equal(await store.read('sessao-a', '../../segredo'), null);
    await store.remove('sessao-a', '3EB0ABC');
    assert.equal(await store.read('sessao-a', '3EB0ABC'), null);

    await store.save('sessao-a', 'VELHA1', Buffer.from('x'), { mimetype: 'image/jpeg' });
    const old = new Date(Date.now() - 10 * 24 * 60 * 60 * 1000);
    await utimes(join(dir, 'media', 'sessao-a', 'VELHA1.bin'), old, old);
    await utimes(join(dir, 'media', 'sessao-a', 'VELHA1.json'), old, old);
    assert.equal(await store.purge(), 2);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});
