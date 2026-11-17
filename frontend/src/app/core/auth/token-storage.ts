const ACCESS_KEY = 'tramitai.access';
const REFRESH_KEY = 'tramitai.refresh';

/**
 * Guarda os tokens no localStorage.
 * Pendente antes de produção: mover o refresh para cookie httpOnly (reduz impacto de XSS).
 */
export const tokenStorage = {
  get access(): string | null {
    return read(ACCESS_KEY);
  },
  get refresh(): string | null {
    return read(REFRESH_KEY);
  },
  save(access: string, refresh?: string): void {
    write(ACCESS_KEY, access);
    if (refresh) {
      write(REFRESH_KEY, refresh);
    }
  },
  clear(): void {
    remove(ACCESS_KEY);
    remove(REFRESH_KEY);
  },
};

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Storage bloqueado (modo privado etc.): a sessão vale só enquanto a aba estiver aberta.
  }
}

function remove(key: string): void {
  try {
    localStorage.removeItem(key);
  } catch {
    // idem
  }
}
