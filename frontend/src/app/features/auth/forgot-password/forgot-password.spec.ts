import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { PasswordService } from '../password.service';
import { ForgotPassword } from './forgot-password';

describe('ForgotPassword', () => {
  let fixture: ComponentFixture<ForgotPassword>;
  let requestReset: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    requestReset = vi.fn(() => of(undefined));
    await TestBed.configureTestingModule({
      imports: [ForgotPassword],
      providers: [provideRouter([]), { provide: PasswordService, useValue: { requestReset } }],
    }).compileComponents();
    fixture = TestBed.createComponent(ForgotPassword);
    await fixture.whenStable();
  });

  it('envia o e-mail e confirma sem revelar se a conta existe', async () => {
    fixture.componentInstance.form.setValue({ email: 'ana@escritorio.com' });
    fixture.componentInstance.submit();
    await fixture.whenStable();
    expect(requestReset).toHaveBeenCalledWith('ana@escritorio.com');
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Se houver uma conta com');
  });

  it('não envia com e-mail inválido', () => {
    fixture.componentInstance.form.setValue({ email: 'nao-e-email' });
    fixture.componentInstance.submit();
    expect(requestReset).not.toHaveBeenCalled();
  });
});
