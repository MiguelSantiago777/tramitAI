import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { RouterLink } from '@angular/router';

import { toApiError } from '../../../core/http/api-error';
import { AuthLayout } from '../auth-layout/auth-layout';
import { PasswordService } from '../password.service';

@Component({
  selector: 'app-forgot-password',
  imports: [
    AuthLayout,
    RouterLink,
    ReactiveFormsModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
  ],
  template: `
    <app-auth-layout>
      <h1>Esqueci minha senha</h1>
      @if (sent()) {
        <p class="lead">Pronto!</p>
        <p class="auth-ok" role="status">
          Se houver uma conta com <strong>{{ form.controls.email.value }}</strong>, enviamos um link
          para criar uma senha nova. Ele vale por 2 horas. Confira também o spam.
        </p>
      } @else {
        <p class="lead">Informe seu e-mail e mandamos um link para criar uma senha nova.</p>
        <form [formGroup]="form" (ngSubmit)="submit()" class="auth-form" novalidate>
          <mat-form-field appearance="outline">
            <mat-label>E-mail</mat-label>
            <input matInput type="email" formControlName="email" autocomplete="username" />
            @if (form.controls.email.hasError('required')) {
              <mat-error>Informe o e-mail.</mat-error>
            } @else if (form.controls.email.hasError('email')) {
              <mat-error>E-mail inválido.</mat-error>
            }
          </mat-form-field>
          @if (error(); as message) {
            <p class="auth-error" role="alert">{{ message }}</p>
          }
          <button mat-flat-button type="submit" class="auth-submit" [disabled]="busy()">
            Enviar link
          </button>
        </form>
      }
      <div class="auth-links">
        <a routerLink="/login">Voltar para o login</a>
      </div>
    </app-auth-layout>
  `,
  styleUrl: '../auth-form.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ForgotPassword {
  private readonly api = inject(PasswordService);

  readonly form = inject(NonNullableFormBuilder).group({
    email: ['', [Validators.required, Validators.email]],
  });
  readonly busy = signal(false);
  readonly sent = signal(false);
  readonly error = signal<string | null>(null);

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.busy.set(true);
    this.error.set(null);
    this.api.requestReset(this.form.getRawValue().email).subscribe({
      next: () => {
        this.busy.set(false);
        this.sent.set(true);
      },
      error: (err: unknown) => {
        this.busy.set(false);
        this.error.set(toApiError(err).message);
      },
    });
  }
}
