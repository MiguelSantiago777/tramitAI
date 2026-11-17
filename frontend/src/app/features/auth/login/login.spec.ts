import { HttpErrorResponse } from '@angular/common/http';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { AuthService } from '../../../core/auth/auth.service';
import { Login } from './login';

function apiError(status: number, code: string, message: string, details?: object) {
  return new HttpErrorResponse({ status, error: { error: { code, message, details } } });
}

describe('Login', () => {
  let fixture: ComponentFixture<Login>;
  let login: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    login = vi.fn();
    await TestBed.configureTestingModule({
      imports: [Login],
      providers: [provideRouter([]), { provide: AuthService, useValue: { login } }],
    }).compileComponents();
    fixture = TestBed.createComponent(Login);
    await fixture.whenStable();
  });

  const el = () => fixture.nativeElement as HTMLElement;

  async function submitWith(email: string, password: string) {
    fixture.componentInstance.form.patchValue({ email, password });
    fixture.componentInstance.submit();
    await fixture.whenStable();
  }

  it('não chama o backend com formulário inválido', async () => {
    await submitWith('', '');
    expect(login).not.toHaveBeenCalled();
    expect(el().textContent).toContain('Informe o e-mail.');
  });

  it('mostra a mensagem do backend em credenciais inválidas', async () => {
    login.mockReturnValue(
      throwError(() => apiError(401, 'invalid_credentials', 'E-mail ou senha inválidos.')),
    );
    await submitWith('dra@exemplo.test', 'errada');
    expect(el().querySelector('[role="alert"]')?.textContent).toContain(
      'E-mail ou senha inválidos.',
    );
  });

  it('pede o escritório quando o usuário tem mais de um e reenvia com o escolhido', async () => {
    login.mockReturnValueOnce(
      throwError(() =>
        apiError(400, 'tenant_selection_required', 'Escolha o escritório.', {
          tenants: [
            { id: 't1', name: 'Escritório A' },
            { id: 't2', name: 'Escritório B' },
          ],
        }),
      ),
    );
    await submitWith('dra@exemplo.test', 'senha');
    expect(el().querySelector('[data-testid="tenant-select"]')).not.toBeNull();
    expect(fixture.componentInstance.tenants().map((t) => t.id)).toEqual(['t1', 't2']);

    login.mockReturnValueOnce(of({}));
    fixture.componentInstance.form.patchValue({ tenantId: 't2' });
    fixture.componentInstance.submit();
    expect(login).toHaveBeenLastCalledWith('dra@exemplo.test', 'senha', 't2');
  });
});
