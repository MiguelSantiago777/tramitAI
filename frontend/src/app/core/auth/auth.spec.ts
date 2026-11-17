import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { LoginResponse } from './auth.models';
import { authInterceptor } from './auth.interceptor';
import { AUTH_URLS, AuthService } from './auth.service';
import { tokenStorage } from './token-storage';

const loginResponse: LoginResponse = {
  access: 'access-1',
  refresh: 'refresh-1',
  session: {
    user: { id: 'u1', email: 'dra@exemplo.test', full_name: 'Dra. Ana', oab_number: '' },
    tenant: { id: 't1', name: 'Escritório A', slug: 'escritorio-a', status: 'ACTIVE' },
    role: 'OWNER',
    can_approve: true,
  },
};

describe('AuthService + authInterceptor', () => {
  let auth: AuthService;
  let http: HttpClient;
  let backend: HttpTestingController;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
        provideRouter([{ path: 'login', children: [] }]),
      ],
    });
    auth = TestBed.inject(AuthService);
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => backend.verify());

  it('login guarda os tokens e a sessão', () => {
    auth.login('dra@exemplo.test', 'senha').subscribe();

    const req = backend.expectOne(AUTH_URLS.login);
    expect(req.request.body).toEqual({
      email: 'dra@exemplo.test',
      password: 'senha',
      tenant_id: null,
    });
    expect(req.request.headers.has('Authorization')).toBe(false);
    req.flush(loginResponse);

    expect(auth.isAuthenticated()).toBe(true);
    expect(auth.session()?.tenant.name).toBe('Escritório A');
    expect(tokenStorage.access).toBe('access-1');
  });

  it('envia o Bearer nas chamadas da API', () => {
    tokenStorage.save('access-1', 'refresh-1');
    http.get('/api/v1/tenant/settings/').subscribe();

    const req = backend.expectOne('/api/v1/tenant/settings/');
    expect(req.request.headers.get('Authorization')).toBe('Bearer access-1');
    req.flush({});
  });

  it('renova o token num 401 e repete a chamada', () => {
    tokenStorage.save('expirado', 'refresh-1');
    let result: unknown;
    http.get('/api/v1/auth/me/').subscribe((body) => (result = body));

    backend.expectOne('/api/v1/auth/me/').flush(null, { status: 401, statusText: 'Unauthorized' });
    backend.expectOne(AUTH_URLS.refresh).flush({ access: 'access-2' });
    const retry = backend.expectOne('/api/v1/auth/me/');
    expect(retry.request.headers.get('Authorization')).toBe('Bearer access-2');
    retry.flush({ ok: true });

    expect(result).toEqual({ ok: true });
    expect(tokenStorage.access).toBe('access-2');
  });

  it('desloga quando o refresh falha', () => {
    tokenStorage.save('expirado', 'refresh-vencido');
    http.get('/api/v1/auth/me/').subscribe({ error: () => undefined });

    backend.expectOne('/api/v1/auth/me/').flush(null, { status: 401, statusText: 'Unauthorized' });
    backend.expectOne(AUTH_URLS.refresh).flush(null, { status: 401, statusText: 'Unauthorized' });

    expect(tokenStorage.access).toBeNull();
    expect(auth.isAuthenticated()).toBe(false);
  });
});
