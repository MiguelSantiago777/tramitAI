import { HttpErrorResponse } from '@angular/common/http';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { Client } from '../client.models';
import { ClientsService } from '../clients.service';
import { ClientForm } from './client-form';

const saved: Client = {
  id: 'c1',
  kind: 'PF',
  name: 'Maria da Silva',
  cpf_cnpj: '52998224725',
  phone: '+5521998765432',
  email: '',
  status: 'ACTIVE',
  notes: '',
  tags: [],
  created_at: '',
  updated_at: '',
};

describe('ClientForm', () => {
  let fixture: ComponentFixture<ClientForm>;
  let api: {
    create: ReturnType<typeof vi.fn>;
    update: ReturnType<typeof vi.fn>;
    tags: ReturnType<typeof vi.fn>;
  };

  beforeEach(async () => {
    api = { create: vi.fn(), update: vi.fn(), tags: vi.fn(() => of([])) };
    await TestBed.configureTestingModule({
      imports: [ClientForm],
      providers: [provideRouter([]), { provide: ClientsService, useValue: api }],
    }).compileComponents();
    fixture = TestBed.createComponent(ClientForm);
    await fixture.whenStable();
  });

  const form = () => fixture.componentInstance.form;
  const text = () => (fixture.nativeElement as HTMLElement).textContent ?? '';

  it('bloqueia CPF inválido sem chamar a API', async () => {
    form().patchValue({ name: 'Maria', cpf_cnpj: '529.982.247-24' });
    fixture.componentInstance.submit();
    await fixture.whenStable();

    expect(api.create).not.toHaveBeenCalled();
    expect(text()).toContain('CPF inválido.');
  });

  it('revalida o documento quando muda de PF para PJ', () => {
    form().patchValue({ cpf_cnpj: '529.982.247-25' });
    expect(form().controls.cpf_cnpj.valid).toBe(true);
    form().controls.kind.setValue('PJ');
    expect(form().controls.cpf_cnpj.hasError('cnpj')).toBe(true);
  });

  it('cria e navega para a página do cliente', async () => {
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    api.create.mockReturnValue(of(saved));
    form().patchValue({ name: 'Maria da Silva', cpf_cnpj: '529.982.247-25', phone: '21998765432' });
    fixture.componentInstance.submit();

    expect(api.create).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Maria da Silva', kind: 'PF', status: 'ACTIVE' }),
    );
    expect(navigate).toHaveBeenCalledWith(['/clientes', 'c1']);
  });

  it('mostra no campo o erro de validação que veio do backend', async () => {
    api.create.mockReturnValue(
      throwError(
        () =>
          new HttpErrorResponse({
            status: 400,
            error: {
              error: {
                code: 'validation_error',
                message: 'Dados inválidos.',
                details: { cpf_cnpj: ['Já existe um cliente com este CPF/CNPJ.'] },
              },
            },
          }),
      ),
    );
    form().patchValue({ name: 'Maria', cpf_cnpj: '529.982.247-25' });
    fixture.componentInstance.submit();
    await fixture.whenStable();

    expect(form().controls.cpf_cnpj.getError('server')).toBe(
      'Já existe um cliente com este CPF/CNPJ.',
    );
    expect(text()).toContain('Já existe um cliente com este CPF/CNPJ.');
  });
});
