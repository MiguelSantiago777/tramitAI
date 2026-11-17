import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { Router } from '@angular/router';
import { finalize } from 'rxjs';

import { TenantOption } from '../../../core/auth/auth.models';
import { AuthService } from '../../../core/auth/auth.service';
import { toApiError } from '../../../core/http/api-error';

@Component({
  selector: 'app-login',
  imports: [
    ReactiveFormsModule,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressBarModule,
    MatSelectModule,
  ],
  templateUrl: './login.html',
  styleUrl: './login.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Login {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  readonly form = inject(NonNullableFormBuilder).group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', Validators.required],
    tenantId: [''],
  });

  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  /** Preenchido quando o usuário tem mais de um escritório. */
  readonly tenants = signal<TenantOption[]>([]);

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const { email, password, tenantId } = this.form.getRawValue();
    if (this.tenants().length > 0 && !tenantId) {
      this.error.set('Escolha o escritório.');
      return;
    }

    this.loading.set(true);
    this.error.set(null);
    this.auth
      .login(email, password, tenantId || undefined)
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: () => void this.router.navigateByUrl('/'),
        error: (err: unknown) => {
          const apiError = toApiError(err);
          if (apiError.code === 'tenant_selection_required') {
            this.tenants.set((apiError.details?.['tenants'] as TenantOption[] | undefined) ?? []);
            return;
          }
          this.error.set(apiError.message);
        },
      });
  }
}
