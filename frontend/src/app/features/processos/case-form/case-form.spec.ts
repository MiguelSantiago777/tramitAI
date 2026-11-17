import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { TenantService } from '../../../core/tenant/tenant.service';
import { ClientsService } from '../../clientes/clients.service';
import { LegalCase } from '../case.models';
import { CasesService } from '../cases.service';
import { CaseForm } from './case-form';

const existing: LegalCase = {
  id: 'p1',
  cnj_number: '08012343920248190001',
  cnj_formatted: '0801234-39.2024.8.19.0001',
  tribunal: 'TJRJ',
  classe: 'Procedimento Comum',
  assunto: '',
  orgao_julgador: '',
  responsible_id: null,
  responsible_name: '',
  status: 'ACTIVE',
  monitoring_enabled: true,
  last_checked_at: null,
  last_movement_at: null,
  sync_status: 'NEVER',
  sync_error: '',
  pending_movements: 0,
  notes: '',
  clients: [{ client_id: 'c1', client_name: 'Maria da Silva', role: 'AUTHOR' }],
  created_at: '',
  updated_at: '',
};

describe('CaseForm', () => {
  let fixture: ComponentFixture<CaseForm>;
  let cases: {
    get: ReturnType<typeof vi.fn>;
    create: ReturnType<typeof vi.fn>;
    update: ReturnType<typeof vi.fn>;
    movements: ReturnType<typeof vi.fn>;
    check: ReturnType<typeof vi.fn>;
  };

  beforeEach(async () => {
    cases = {
      get: vi.fn(),
      create: vi.fn(),
      update: vi.fn(),
      movements: vi.fn(() => of({ count: 0, next: null, previous: null, results: [] })),
      check: vi.fn(),
    };
    await TestBed.configureTestingModule({
      imports: [CaseForm],
      providers: [
        provideRouter([]),
        { provide: CasesService, useValue: cases },
        { provide: ClientsService, useValue: { list: vi.fn(() => of({ results: [] })) } },
        { provide: TenantService, useValue: { members: () => of([]) } },
      ],
    }).compileComponents();
  });

  async function create(id?: string) {
    fixture = TestBed.createComponent(CaseForm);
    if (id) {
      fixture.componentRef.setInput('id', id);
    }
    await fixture.whenStable();
    return fixture.componentInstance;
  }

  it('bloqueia número CNJ com dígito verificador errado', async () => {
    const component = await create();
    component.form.patchValue({ cnj_number: '0801234-40.2024.8.19.0001' });
    component.submit();
    await fixture.whenStable();

    expect(cases.create).not.toHaveBeenCalled();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Número inválido');
  });

  it('carrega o processo, mantém os clientes e envia só dígitos do CNJ', async () => {
    cases.get.mockReturnValue(of(existing));
    cases.update.mockReturnValue(of(existing));
    const component = await create('p1');

    expect(component.form.controls.cnj_number.value).toBe('0801234-39.2024.8.19.0001');
    expect(component.clientRows.length).toBe(1);

    component.clientRows.at(0).controls.role.setValue('DEFENDANT');
    component.submit();

    expect(cases.update).toHaveBeenCalledWith(
      'p1',
      expect.objectContaining({
        cnj_number: '08012343920248190001',
        clients: [{ client_id: 'c1', role: 'DEFENDANT' }],
      }),
    );
  });

  it('não duplica cliente já vinculado', async () => {
    cases.get.mockReturnValue(of(existing));
    const component = await create('p1');
    const option = { value: { id: 'c1', name: 'Maria da Silva' } };
    component.addClient({ option } as never);
    expect(component.clientRows.length).toBe(1);
  });
});
