import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatSnackBar } from '@angular/material/snack-bar';

import { AuthService } from '../../../core/auth/auth.service';
import { toApiError } from '../../../core/http/api-error';
import { TenantService } from '../../../core/tenant/tenant.service';

/** Configurações do escritório. Alterar: só o titular. */
@Component({
  selector: 'app-office-settings',
  imports: [
    ReactiveFormsModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatSlideToggleModule,
  ],
  template: `
    <header class="page-header">
      <div>
        <h1>Configurações do escritório</h1>
        <p>Como o TramitAI trabalha para o seu escritório.</p>
      </div>
    </header>

    @if (error(); as message) {
      <p class="error-text" role="alert">{{ message }}</p>
    }

    <form class="form-card settings" [formGroup]="form" (ngSubmit)="save()">
      <h2>Escritório</h2>
      <mat-form-field appearance="outline" class="full">
        <mat-label>Nome do escritório</mat-label>
        <input matInput formControlName="tenant_name" />
        <mat-hint>Aparece para os clientes no termo de ciência e nas mensagens.</mat-hint>
      </mat-form-field>

      <h2>Lia (inteligência artificial)</h2>
      <div class="setting">
        <mat-slide-toggle formControlName="ai_triage_enabled">
          Lia escreve rascunhos de resposta e de aviso de andamento
        </mat-slide-toggle>
        <span class="muted small">
          Desligado: as mensagens continuam chegando em Conversas e os avisos de andamento usam um
          texto fixo, sem IA. Nada sai sem aprovação em nenhum caso.
        </span>
      </div>

      <h2>Aprovação de mensagens</h2>
      <div class="setting">
        <mat-slide-toggle formControlName="staff_can_approve">
          Pessoas com papel "Equipe" também podem aprovar mensagens
        </mat-slide-toggle>
        <span class="muted small">
          Titular e advogados sempre podem aprovar. Ligue se a sua secretária deve poder enviar.
        </span>
      </div>

      @if (canEdit()) {
        <div class="form-actions">
          <button mat-flat-button type="submit" [disabled]="busy() || form.pristine">Salvar</button>
        </div>
      } @else {
        <p class="muted small">Só o titular pode alterar estas configurações.</p>
      }
    </form>
  `,
  styles: `
    .settings h2 {
      margin-top: 20px;
    }
    .settings h2:first-of-type {
      margin-top: 4px;
    }
    .setting {
      display: flex;
      flex-direction: column;
      gap: 6px;
      max-width: 640px;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class OfficeSettingsPage {
  private readonly api = inject(TenantService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly session = inject(AuthService).session;
  readonly canEdit = computed(() => this.session()?.role === 'OWNER');

  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly form = inject(NonNullableFormBuilder).group({
    tenant_name: ['', [Validators.required, Validators.maxLength(200)]],
    ai_triage_enabled: [true],
    staff_can_approve: [false],
  });

  constructor() {
    this.api.settings().subscribe({
      next: (s) => {
        this.form.reset({
          tenant_name: s.tenant_name,
          ai_triage_enabled: s.ai_triage_enabled,
          staff_can_approve: s.staff_can_approve,
        });
        if (!this.canEdit()) {
          this.form.disable();
        }
      },
      error: (err: unknown) => this.error.set(toApiError(err).message),
    });
  }

  save(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.busy.set(true);
    this.error.set(null);
    this.api.updateSettings(this.form.getRawValue()).subscribe({
      next: (s) => {
        this.busy.set(false);
        this.form.reset({
          tenant_name: s.tenant_name,
          ai_triage_enabled: s.ai_triage_enabled,
          staff_can_approve: s.staff_can_approve,
        });
        this.snackBar.open('Configurações salvas.', undefined, { duration: 3000 });
      },
      error: (err: unknown) => {
        this.busy.set(false);
        this.error.set(toApiError(err).message);
      },
    });
  }
}
