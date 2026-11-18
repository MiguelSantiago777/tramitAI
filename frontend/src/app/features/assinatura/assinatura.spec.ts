import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { authInterceptor } from '../../core/auth/auth.interceptor';
import { AUTH_URLS, AuthService } from '../../core/auth/auth.service';
import { tokenStorage } from '../../core/auth/token-storage';
import { periodRange } from '../relatorios/reports-page';
import { Billing, billingNotice } from './billing.service';

const base: Billing = {
  status: 'TRIAL',
  status_label: 'Teste grátis',
  plan_name: 'TramitAI Escritório',
  price: '197.00',
  trial_ends_at: null,
  paid_until: null,
  access_until: null,
  days_left: 10,
  blocked: false,
  payer_email: '',
  checkout_url: '',
  can_manage: true,
  exempt: false,
};

describe('aviso da assinatura', () => {
  it('só avisa quando faz sentido', () => {
    expect(billingNotice(base)).toBeNull();
    expect(billingNotice({ ...base, days_left: 3 })).toContain('3 dia');
    expect(billingNotice({ ...base, days_left: 0 })).toContain('hoje');
    expect(billingNotice({ ...base, blocked: true })).toContain('bloqueado');
    expect(billingNotice({ ...base, status: 'PAST_DUE' })).toContain('atrasado');
    expect(billingNotice({ ...base, exempt: true, blocked: true })).toBeNull();
    expect(billingNotice(null)).toBeNull();
  });
});

describe('períodos dos relatórios', () => {
  it('mês atual, mês passado e 90 dias', () => {
    const today = new Date(2026, 10, 18);
    expect(periodRange('month', today)).toEqual({ start: '2026-11-01', end: '2026-11-18' });
    expect(periodRange('last_month', today)).toEqual({ start: '2026-10-01', end: '2026-10-31' });
    expect(periodRange('90d', today)).toEqual({ start: '2026-08-21', end: '2026-11-18' });
  });
});

describe('cadastro e assinatura vencida', () => {
  let auth: AuthService;
  let http: HttpClient;
  let backend: HttpTestingController;
  let router: Router;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
        provideRouter([
          { path: 'assinatura', children: [] },
          { path: 'login', children: [] },
        ]),
      ],
    });
    auth = TestBed.inject(AuthService);
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
  });

  afterEach(() => backend.verify());

  it('cadastro não manda token e já entra', () => {
    tokenStorage.save('velho', 'velho');
    auth
      .signup({
        office_name: 'Souza Advocacia',
        full_name: 'Bia',
        email: 'bia@souza.adv.br',
        password: 'uma-senha-forte',
        accept_terms: true,
      })
      .subscribe();
    const req = backend.expectOne(AUTH_URLS.signup);
    expect(req.request.headers.has('Authorization')).toBe(false);
    req.flush({
      access: 'a1',
      refresh: 'r1',
      session: {
        user: { id: 'u1', email: 'bia@souza.adv.br', full_name: 'Bia', oab_number: '' },
        tenant: { id: 't1', name: 'Souza Advocacia', slug: 'souza', status: 'ACTIVE' },
        role: 'OWNER',
        can_approve: true,
      },
    });
    expect(auth.isAuthenticated()).toBe(true);
    expect(tokenStorage.access).toBe('a1');
  });

  it('402 leva para a página de assinatura', async () => {
    tokenStorage.save('a1', 'r1');
    const navigate = vi.spyOn(router, 'navigate');
    http.get('/api/v1/clients/').subscribe({ error: () => undefined });
    backend
      .expectOne('/api/v1/clients/')
      .flush(
        { error: { code: 'subscription_required', message: 'venceu' } },
        { status: 402, statusText: 'Payment Required' },
      );
    expect(navigate).toHaveBeenCalledWith(['/assinatura']);
  });
});
