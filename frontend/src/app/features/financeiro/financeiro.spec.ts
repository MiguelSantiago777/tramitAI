import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { AuthService } from '../../core/auth/auth.service';
import { FinancePage } from './finance-page';
import {
  Installment,
  addMonths,
  installmentState,
  money,
  parseMoney,
  previewPlan,
} from './financeiro.models';
import { FinanceiroService } from './financeiro.service';

const open: Installment = {
  id: 'i1',
  agreement_id: 'a1',
  agreement_title: 'Ação trabalhista',
  client_id: 'c1',
  client_name: 'Ana Souza',
  case_number: '',
  number: 1,
  due_date: '2026-11-01',
  amount: '333.34',
  status: 'OPEN',
  is_overdue: true,
  paid_at: null,
  paid_amount: null,
  method: '',
  paid_note: '',
  settled_by_name: '',
  charge_kind: 'PIX',
  has_active_charge: true,
  pix_code: '000201...',
  pix_qr_base64: '',
  payment_url: '',
  charge_expires_at: null,
  last_reminder_on: null,
};

describe('regras do financeiro', () => {
  it('lê valor em reais com vírgula ou ponto', () => {
    expect(parseMoney('1.234,56')).toBe('1234.56');
    expect(parseMoney('R$ 3000')).toBe('3000.00');
    expect(parseMoney('1234.5')).toBe('1234.50');
    expect(parseMoney('0')).toBeNull();
    expect(parseMoney('abc')).toBeNull();
  });

  it('formata em reais', () => {
    expect(money('1234.5').replace(/\s/g, ' ')).toBe('R$ 1.234,50');
  });

  it('parcela igual ao backend: centavos na 1ª e fim de mês ajustado', () => {
    const plan = previewPlan('1000.00', 3, '2026-01-31', null);
    expect(plan.map((p) => p.amount)).toEqual([333.34, 333.33, 333.33]);
    expect(plan.map((p) => p.due)).toEqual(['2026-01-31', '2026-02-28', '2026-03-31']);
    const withEntry = previewPlan('1500', 2, '2026-05-10', '500');
    expect(withEntry.map((p) => [p.number, p.due, p.amount])).toEqual([
      [1, '2026-05-10', 500],
      [2, '2026-06-10', 500],
      [3, '2026-07-10', 500],
    ]);
    expect(previewPlan('100', 2, '2026-01-01', '100')).toEqual([]);
  });

  it('virada de ano', () => {
    expect(addMonths('2026-12-15', 1)).toBe('2027-01-15');
  });

  it('estado da parcela', () => {
    expect(installmentState(open).label).toBe('Atrasada');
    expect(installmentState({ ...open, status: 'PAID' }).label).toBe('Paga');
  });
});

describe('FinancePage', () => {
  let fixture: ComponentFixture<FinancePage>;
  let api: Record<string, ReturnType<typeof vi.fn>>;

  beforeEach(async () => {
    api = {
      summary: vi.fn(() =>
        of({
          month: '2026-11-01',
          received: '500.00',
          expected: '1000.00',
          overdue_total: '333.34',
          overdue_count: 1,
          next_30_days: '0',
          open_total: '333.34',
        }),
      ),
      installments: vi.fn(() => of({ count: 1, next: null, previous: null, results: [open] })),
    };
    await TestBed.configureTestingModule({
      imports: [FinancePage],
      providers: [
        provideRouter([]),
        { provide: FinanceiroService, useValue: api },
        { provide: AuthService, useValue: { session: signal({ role: 'OWNER' }) } },
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(FinancePage);
    await fixture.whenStable();
  });

  const text = () =>
    ((fixture.nativeElement as HTMLElement).textContent ?? '').replace(/\s+/g, ' ');

  it('mostra o resumo do mês e as parcelas em aberto', () => {
    expect(api['installments']).toHaveBeenCalledWith({ status: 'open', q: '' }, 0);
    expect(text()).toContain('1 parcela(s) · ver lista');
    expect(text()).toContain('Ana Souza');
    expect(text()).toContain('Atrasada');
    expect(text()).toContain('Pix gerado');
  });

  it('filtra só as atrasadas pelo card', async () => {
    (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('button.stat')!.click();
    await fixture.whenStable();
    expect(api['installments']).toHaveBeenLastCalledWith({ status: 'overdue', q: '' }, 0);
  });
});
