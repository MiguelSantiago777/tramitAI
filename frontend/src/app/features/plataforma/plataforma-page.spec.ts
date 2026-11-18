import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { PlataformaPage } from './plataforma-page';
import { Office, Overview } from './plataforma.service';

const office: Office = {
  id: 'o1',
  name: 'Souza Advocacia',
  created_at: '2026-11-01T10:00:00Z',
  status: 'TRIAL',
  plan_code: 'escritorio',
  plan_name: 'TramitAI Escritório',
  price: '197.00',
  trial_ends_at: '2026-11-20T10:00:00Z',
  paid_until: null,
  access_until: '2026-11-20T10:00:00Z',
  blocked: false,
  owner_name: 'Bia',
  owner_email: 'bia@souza.adv.br',
  last_payment_at: null,
  checkout_url: '',
};

const overview: Overview = {
  mrr: '394.00',
  offices: 4,
  by_status: { ACTIVE: 2, TRIAL: 1, EXEMPT: 1 },
  conversion: 50,
  trials_ending: [office],
  attention: [],
  revenue_by_month: [{ month: '2026-11-01', total: '394.00' }],
  signups_by_week: [{ week: '2026-11-16', count: 1 }],
};

describe('PlataformaPage', () => {
  it('mostra receita, pagantes e testes acabando', async () => {
    await TestBed.configureTestingModule({
      imports: [PlataformaPage],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    const fixture = TestBed.createComponent(PlataformaPage);
    const http = TestBed.inject(HttpTestingController);
    http.expectOne('/api/v1/platform/plans/').flush([]);
    http.expectOne('/api/v1/platform/overview/').flush(overview);
    await fixture.whenStable();
    const text = ((fixture.nativeElement as HTMLElement).textContent ?? '').replace(/\s+/g, ' ');
    expect(text).toContain('R$ 394,00');
    expect(text).toContain('de 4 no total');
    expect(text).toContain('50% viram pagantes');
    expect(text).toContain('Souza Advocacia');
    expect(text).toContain('Tudo em dia');
  });
});
