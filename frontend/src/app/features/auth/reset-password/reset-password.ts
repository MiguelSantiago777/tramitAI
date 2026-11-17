import { ChangeDetectionStrategy, Component, computed, inject, input, signal } from '@angular/core';
import {
  AbstractControl,
  NonNullableFormBuilder,
  ReactiveFormsModule,
  ValidationErrors,
  Validators,
} from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { RouterLink } from '@angular/router';

import { toApiError } from '../../../core/http/api-error';
import { AuthLayout } from '../auth-layout/auth-layout';
import { PasswordService } from '../password.service';

function samePassword(group: AbstractControl): ValidationErrors | null {
  const { password, confirm } = group.value as { password: string; confirm: string };
  return confirm && password !== confirm ? { mismatch: true } : null;
}

/** Abre pelo link do e-mail: /redefinir-senha?uid=...&token=... */
@Component({
  selector: 'app-reset-password',
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
      <h1>{{ invite() ? 'Criar sua senha' : 'Criar senha nova' }}</h1>
      @if (!linkOk()) {
        <p class="auth-error" role="alert">
          Link incompleto. Abra de novo o link do e-mail ou peça outro.
        </p>
        <div class="auth-links"><a routerLink="/esqueci-senha">Pedir novo link</a></div>
      } @else if (done()) {
        <p class="auth-ok" role="status">
          {{
            invite()
              ? 'Senha criada. Bem-vindo(a) à equipe!'
              : 'Senha alterada. Já pode entrar com a senha nova.'
          }}
        </p>
        <a mat-flat-button routerLink="/login" class="auth-submit">Ir para o login</a>
      } @else {
        <p class="lead">Use pelo menos 8 caracteres, misturando letras e números.</p>
        <form [formGroup]="form" (ngSubmit)="submit()" class="auth-form" novalidate>
          <mat-form-field appearance="outline">
            <mat-label>Senha nova</mat-label>
            <input
              matInput
              type="password"
              formControlName="password"
              autocomplete="new-password"
            />
            @if (form.controls.password.hasError('minlength')) {
              <mat-error>Mínimo de 8 caracteres.</mat-error>
            }
          </mat-form-field>
          <mat-form-field appearance="outline">
            <mat-label>Repita a senha</mat-label>
            <input matInput type="password" formControlName="confirm" autocomplete="new-password" />
          </mat-form-field>
          @if (form.hasError('mismatch')) {
            <p class="auth-error" role="alert">As senhas não são iguais.</p>
          }
          @if (error(); as message) {
            <p class="auth-error" role="alert">{{ message }}</p>
          }
          <button mat-flat-button type="submit" class="auth-submit" [disabled]="busy()">
            Salvar senha
          </button>
        </form>
        <div class="auth-links"><a routerLink="/esqueci-senha">Pedir novo link</a></div>
      }
    </app-auth-layout>
  `,
  styleUrl: '../auth-form.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ResetPassword {
  private readonly api = inject(PasswordService);

  readonly uid = input<string>();
  readonly token = input<string>();
  /** `convite=1` no link: pessoa convidada criando a primeira senha. */
  readonly convite = input<string>();
  readonly invite = computed(() => this.convite() === '1');
  readonly linkOk = computed(() => !!this.uid() && !!this.token());

  readonly form = inject(NonNullableFormBuilder).group(
    {
      password: ['', [Validators.required, Validators.minLength(8)]],
      confirm: ['', Validators.required],
    },
    { validators: samePassword },
  );
  readonly busy = signal(false);
  readonly done = signal(false);
  readonly error = signal<string | null>(null);

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.busy.set(true);
    this.error.set(null);
    this.api
      .confirmReset(this.uid() ?? '', this.token() ?? '', this.form.getRawValue().password)
      .subscribe({
        next: () => {
          this.busy.set(false);
          this.done.set(true);
        },
        error: (err: unknown) => {
          this.busy.set(false);
          this.error.set(toApiError(err).message);
        },
      });
  }
}
