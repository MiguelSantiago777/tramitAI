import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';

import { AuthService } from '../../../core/auth/auth.service';
import { toApiError } from '../../../core/http/api-error';
import { AuthLayout } from '../auth-layout/auth-layout';

/** Cadastro self-service: cria o escritório em teste grátis e já entra. */
@Component({
  selector: 'app-signup',
  imports: [
    AuthLayout,
    RouterLink,
    ReactiveFormsModule,
    MatButtonModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressBarModule,
  ],
  template: `
    <app-auth-layout>
      <h1>Teste grátis por 14 dias</h1>
      <p class="lead">Sem cartão agora. Configure o WhatsApp e veja a Vera trabalhando.</p>

      @if (loading()) {
        <mat-progress-bar mode="indeterminate" />
      }

      <form [formGroup]="form" (ngSubmit)="submit()" class="auth-form" novalidate>
        <mat-form-field appearance="outline">
          <mat-label>Nome do escritório</mat-label>
          <input matInput formControlName="office_name" autocomplete="organization" />
          @if (form.controls.office_name.hasError('required')) {
            <mat-error>Informe o nome do escritório.</mat-error>
          }
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>Seu nome</mat-label>
          <input matInput formControlName="full_name" autocomplete="name" />
          @if (form.controls.full_name.hasError('required')) {
            <mat-error>Informe seu nome.</mat-error>
          }
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>E-mail</mat-label>
          <input matInput type="email" formControlName="email" autocomplete="email" />
          @if (form.controls.email.hasError('required')) {
            <mat-error>Informe o e-mail.</mat-error>
          } @else if (form.controls.email.hasError('email')) {
            <mat-error>E-mail inválido.</mat-error>
          }
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>Senha</mat-label>
          <input matInput type="password" formControlName="password" autocomplete="new-password" />
          <mat-hint>Pelo menos 10 caracteres.</mat-hint>
          @if (form.controls.password.hasError('minlength')) {
            <mat-error>Use pelo menos 10 caracteres.</mat-error>
          }
        </mat-form-field>
        <mat-checkbox formControlName="accept_terms">
          Li e aceito os
          <a routerLink="/termos" target="_blank">termos de uso e a política de privacidade</a>.
        </mat-checkbox>

        @if (error(); as message) {
          <p class="auth-error" role="alert">{{ message }}</p>
        }

        <button mat-flat-button type="submit" class="auth-submit" [disabled]="loading()">
          Criar meu escritório
        </button>
      </form>

      <div class="auth-links">
        <a routerLink="/login">Já tenho conta</a>
      </div>
    </app-auth-layout>
  `,
  styleUrls: ['../auth-form.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Signup {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly form = inject(NonNullableFormBuilder).group({
    office_name: ['', [Validators.required, Validators.maxLength(200)]],
    full_name: ['', [Validators.required, Validators.maxLength(200)]],
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required, Validators.minLength(10)]],
    accept_terms: [false],
  });

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const v = this.form.getRawValue();
    if (!v.accept_terms) {
      this.error.set('Para continuar, aceite os termos de uso.');
      return;
    }
    this.loading.set(true);
    this.error.set(null);
    this.auth
      .signup({ ...v, office_name: v.office_name.trim(), full_name: v.full_name.trim() })
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: () => void this.router.navigateByUrl('/configuracoes/whatsapp'),
        error: (err: unknown) => {
          const apiError = toApiError(err);
          const details = apiError.details as Record<string, string[]> | undefined;
          this.error.set(details?.['password']?.[0] ?? apiError.message);
        },
      });
  }
}
