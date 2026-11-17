import { HttpErrorResponse } from '@angular/common/http';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { PasswordService } from '../password.service';
import { ResetPassword } from './reset-password';

describe('ResetPassword', () => {
  let fixture: ComponentFixture<ResetPassword>;
  let api: { confirmReset: ReturnType<typeof vi.fn> };

  async function setup(uid?: string, token?: string) {
    api = { confirmReset: vi.fn(() => of(undefined)) };
    await TestBed.configureTestingModule({
      imports: [ResetPassword],
      providers: [provideRouter([]), { provide: PasswordService, useValue: api }],
    }).compileComponents();
    fixture = TestBed.createComponent(ResetPassword);
    if (uid) fixture.componentRef.setInput('uid', uid);
    if (token) fixture.componentRef.setInput('token', token);
    await fixture.whenStable();
  }

  const text = () => (fixture.nativeElement as HTMLElement).textContent ?? '';

  it('sem uid/token avisa que o link está incompleto', async () => {
    await setup();
    expect(text()).toContain('Link incompleto');
  });

  it('não envia se as senhas forem diferentes', async () => {
    await setup('MQ', 'tok');
    fixture.componentInstance.form.setValue({ password: 'senha-forte-1', confirm: 'outra-coisa' });
    fixture.componentInstance.submit();
    await fixture.whenStable();
    expect(api.confirmReset).not.toHaveBeenCalled();
    expect(text()).toContain('As senhas não são iguais');
  });

  it('salva e oferece ir para o login', async () => {
    await setup('MQ', 'tok');
    fixture.componentInstance.form.setValue({
      password: 'senha-forte-1',
      confirm: 'senha-forte-1',
    });
    fixture.componentInstance.submit();
    await fixture.whenStable();
    expect(api.confirmReset).toHaveBeenCalledWith('MQ', 'tok', 'senha-forte-1');
    expect(text()).toContain('Senha alterada');
  });

  it('mostra o erro do link expirado', async () => {
    await setup('MQ', 'tok');
    api.confirmReset.mockReturnValue(
      throwError(
        () =>
          new HttpErrorResponse({
            status: 400,
            error: { error: { code: 'invalid_reset_link', message: 'Link inválido ou expirado.' } },
          }),
      ),
    );
    fixture.componentInstance.form.setValue({
      password: 'senha-forte-1',
      confirm: 'senha-forte-1',
    });
    fixture.componentInstance.submit();
    await fixture.whenStable();
    expect(text()).toContain('Link inválido ou expirado.');
  });
});
