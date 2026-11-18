import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';

import { toApiError } from '../../core/http/api-error';
import { Installment, METHOD_LABELS, PaymentMethod, money, parseMoney } from './financeiro.models';
import { FinanceiroService } from './financeiro.service';

function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(
    d.getDate(),
  ).padStart(2, '0')}`;
}

/** Baixa manual: pagamento recebido fora do Mercado Pago (dinheiro, transferência...). */
@Component({
  selector: 'app-settle-dialog',
  imports: [
    ReactiveFormsModule,
    MatButtonModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
  ],
  template: `
    <h2 mat-dialog-title>Dar baixa na parcela {{ data.number }}</h2>
    <mat-dialog-content>
      <p class="muted">
        {{ data.client_name }} · {{ data.agreement_title }} · {{ fmt(data.amount) }}
      </p>
      <form [formGroup]="form" class="dialog-form" id="settle-form" (ngSubmit)="save()">
        <mat-form-field appearance="outline">
          <mat-label>Forma de pagamento</mat-label>
          <mat-select formControlName="method">
            @for (m of methods; track m[0]) {
              <mat-option [value]="m[0]">{{ m[1] }}</mat-option>
            }
          </mat-select>
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>Data do pagamento</mat-label>
          <input matInput type="date" formControlName="paid_on" />
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>Valor recebido (R$)</mat-label>
          <input matInput formControlName="amount" inputmode="decimal" />
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>Observação (opcional)</mat-label>
          <input matInput formControlName="note" maxlength="255" />
        </mat-form-field>
      </form>
      @if (error(); as message) {
        <p class="error-text" role="alert">{{ message }}</p>
      }
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button type="button" mat-dialog-close>Fechar</button>
      <button mat-flat-button type="submit" form="settle-form" [disabled]="busy()">
        Confirmar pagamento
      </button>
    </mat-dialog-actions>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SettleDialog {
  readonly data = inject<Installment>(MAT_DIALOG_DATA);
  private readonly ref = inject(MatDialogRef<SettleDialog, Installment>);
  private readonly api = inject(FinanceiroService);

  readonly methods = Object.entries(METHOD_LABELS) as [PaymentMethod, string][];
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly form = inject(NonNullableFormBuilder).group({
    method: ['PIX' as PaymentMethod, Validators.required],
    paid_on: [todayIso(), Validators.required],
    amount: [Number(this.data.amount).toFixed(2).replace('.', ',')],
    note: [''],
  });

  fmt(value: string): string {
    return money(value);
  }

  save(): void {
    const v = this.form.getRawValue();
    const amount = parseMoney(v.amount);
    if (!amount) {
      this.error.set('Informe o valor recebido.');
      return;
    }
    this.busy.set(true);
    this.api
      .settle(this.data.id, {
        method: v.method,
        paid_amount: amount,
        // Meio-dia de Brasília: a data não "volta" um dia por fuso.
        paid_at: `${v.paid_on}T12:00:00-03:00`,
        note: v.note,
      })
      .subscribe({
        next: (saved) => this.ref.close(saved),
        error: (err: unknown) => {
          this.busy.set(false);
          this.error.set(toApiError(err).message);
        },
      });
  }
}
