// Cópia temporária das mídias recebidas. O Baileys só consegue baixar a mídia com a mensagem
// original em mãos, então baixamos na chegada e o backend busca depois (e manda apagar).
// O que ninguém buscou é apagado sozinho depois de MEDIA_TTL_MS.

import { mkdir, readFile, readdir, rm, stat, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

export const MEDIA_ID = /^[A-Za-z0-9_-]{4,128}$/;
export const MEDIA_TTL_MS = 3 * 24 * 60 * 60 * 1000;

export class MediaStore {
  constructor(dataDir) {
    this.dir = join(dataDir, 'media');
  }

  #paths(session, id) {
    if (!MEDIA_ID.test(id)) {
      throw new Error('invalid media id');
    }
    const folder = join(this.dir, session);
    return { folder, bin: join(folder, `${id}.bin`), meta: join(folder, `${id}.json`) };
  }

  async save(session, id, buffer, meta) {
    const p = this.#paths(session, id);
    await mkdir(p.folder, { recursive: true, mode: 0o700 });
    await writeFile(p.bin, buffer, { mode: 0o600 });
    await writeFile(p.meta, JSON.stringify(meta), { mode: 0o600 });
  }

  /** @returns {Promise<{ buffer: Buffer, meta: any } | null>} */
  async read(session, id) {
    if (!MEDIA_ID.test(id)) {
      return null;
    }
    const p = this.#paths(session, id);
    try {
      const [buffer, meta] = await Promise.all([readFile(p.bin), readFile(p.meta, 'utf8')]);
      return { buffer, meta: JSON.parse(meta) };
    } catch {
      return null;
    }
  }

  async remove(session, id) {
    if (!MEDIA_ID.test(id)) {
      return;
    }
    const p = this.#paths(session, id);
    await Promise.all([rm(p.bin, { force: true }), rm(p.meta, { force: true })]);
  }

  /** Apaga cópias mais velhas que `maxAgeMs`. Devolve quantos arquivos saíram. */
  async purge(maxAgeMs = MEDIA_TTL_MS, now = Date.now()) {
    let removed = 0;
    let sessions = [];
    try {
      sessions = await readdir(this.dir);
    } catch {
      return 0;
    }
    for (const session of sessions) {
      const folder = join(this.dir, session);
      let files = [];
      try {
        files = await readdir(folder);
      } catch {
        continue;
      }
      for (const file of files) {
        const path = join(folder, file);
        try {
          if (now - (await stat(path)).mtimeMs > maxAgeMs) {
            await rm(path, { force: true });
            removed += 1;
          }
        } catch {
          // sumiu no meio: ok
        }
      }
    }
    return removed;
  }
}
