import { HttpErrorResponse } from '@angular/common/http';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { CaseMovement, LegalCase } from '../case.models';
import { CasesService } from '../cases.service';
import { CaseMovements } from './case-movements';

const legalCase: LegalCase = {
  id: 'p1',
  cnj_number: '08012343920248190001',
  cnj_formatted: '0801234-39.2024.8.19.0001',
  tribunal: 'TJRJ',
  classe: '',
  assunto: '',
  orgao_julgador: '',
  responsible_id: null,
  responsible_name: '',
  status: 'ACTIVE',
  monitoring_enabled: true,
  last_checked_at: '2026-11-17T09:00:00Z',
  last_movement_at: null,
  sync_status: 'OK',
  sync_error: '',
  pending_movements: 1,
  notes: '',
  clients: [],
  created_at: '',
  updated_at: '',
};

const movements: CaseMovement[] = [
  {
    id: 'm2',
    name: 'Conclusão',
    code: 51,
    complements: [],
    grau: 'G1',
    occurred_at: '2026-11-16T15:00:00Z',
    notification: 'PENDING',
  },
  {
    id: 'm1',
    name: 'Juntada',
    code: 581,
    complements: ['tipo de documento: Petição'],
    grau: 'G1',
    occurred_at: '2024-03-04T13:00:00Z',
    notification: 'BASELINE',
  },
];

describe('CaseMovements', () => {
  let fixture: ComponentFixture<CaseMovements>;
  let api: { movements: ReturnType<typeof vi.fn>; check: ReturnType<typeof vi.fn> };

  async function setup(overrides: Partial<LegalCase> = {}) {
    api = {
      movements: vi.fn(() => of({ count: 2, next: null, previous: null, results: movements })),
      check: vi.fn(() => of(undefined)),
    };
    await TestBed.configureTestingModule({
      imports: [CaseMovements],
      providers: [provideRouter([]), { provide: CasesService, useValue: api }],
    }).compileComponents();
    fixture = TestBed.createComponent(CaseMovements);
    fixture.componentRef.setInput('legalCase', { ...legalCase, ...overrides });
    await fixture.whenStable();
  }

  const text = () => (fixture.nativeElement as HTMLElement).textContent ?? '';
  const checkButton = () =>
    [...(fixture.nativeElement as HTMLElement).querySelectorAll('button')].find((b) =>
      b.textContent?.includes('Verificar agora'),
    );

  it('lista andamentos com a situação do aviso', async () => {
    await setup();
    expect(api.movements).toHaveBeenCalledWith('p1', 0, 20);
    expect(text()).toContain('Conclusão');
    expect(text()).toContain('Aviso aguardando aprovação');
    expect(text()).toContain('tipo de documento: Petição');
    expect(text()).toContain('Histórico');
    expect(text()).toContain('1 andamento(s) novo(s)');
  });

  afterEach(() => vi.useRealTimers());

  it('verificar agora pede a consulta e recarrega depois', async () => {
    await setup();
    vi.useFakeTimers();
    const refreshed = vi.fn();
    fixture.componentInstance.refresh.subscribe(refreshed);
    checkButton()!.click();
    expect(api.check).toHaveBeenCalledWith('p1');
    vi.advanceTimersByTime(5000);
    expect(refreshed).toHaveBeenCalled();
    expect(api.movements).toHaveBeenCalledTimes(2);
  });

  it('mostra o erro de consulta recente', async () => {
    await setup();
    api.check.mockReturnValue(
      throwError(
        () =>
          new HttpErrorResponse({
            status: 429,
            error: {
              error: { code: 'checked_recently', message: 'Tente de novo em alguns minutos.' },
            },
          }),
      ),
    );
    checkButton()!.click();
    await fixture.whenStable();
    expect(text()).toContain('Tente de novo em alguns minutos.');
  });

  it('sem monitoramento, não oferece consulta', async () => {
    await setup({ monitoring_enabled: false });
    expect(checkButton()).toBeUndefined();
    expect(text()).toContain('monitoramento desligado');
  });
});
