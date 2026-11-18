import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';

import { toApiError } from '../../core/http/api-error';
import { ClientPicker, ClientRef } from '../../shared/client-picker/client-picker';
import {
  AgreementKind,
  FeeAgreement,
  KIND_LABELS,
  addMonths,
  money,
  parseMoney,
  previewPlan,
} from './financeiro.models';
import { FinanceiroService } from './financeiro.service';

export interface AgreementDialogData {
  client?: ClientRef;
  legal_case_id?: string;
  case_number?: string;
}

function nextMonthIso(): string {
  const now = new Date();
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(
    now.getDate(),
  ).padStart(2, '0')}`;
  return addMonths(today, 1);
}

@Component({
  selector: 'app-agreement-dialog',
  imports: [
    DatePipe,
    ReactiveFormsModule,
    MatButtonModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    ClientPicker,
  ],
  template: `
    <h2 mat-dialog-title>Novo contrato de honorários</h2>
    <mat-dialog-content>
      <form [formGroup]="form" class="dialog-form" id="agreement-form" (ngSubmit)="save()">
        <div class="span-2">
          <app-client-picker [(client)]="client" />
        </div>
        @if (data.case_number) {
          <p class="span-2 muted small">Processo {{ data.case_number }}</p>
        }
        <mat-form-field appearance="outline" class="span-2">
          <mat-label>Descrição</mat-label>
          <input matInput formControlName="title" placeholder="Ex.: Ação trabalhista contra X" />
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>Tipo</mat-label>
          <mat-select formControlName="kind">
            @for (k of kinds; track k[0]) {
              <mat-option [value]="k[0]">{{ k[1] }}</mat-option>
            }
          </mat-select>
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>Valor total (R$)</mat-label>
          <input matInput formControlName="total" inputmode="decimal" placeholder="3.000,00" />
          @if (form.controls.total.touched && !totalValue()) {
            <mat-error>Informe o valor.</mat-error>
          }
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>Entrada (opcional)</mat-label>
          <input matInput formControlName="entry" inputmode="decimal" placeholder="0,00" />
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>{{ entryValue() ? 'Parcelas depois da entrada' : 'Parcelas' }}</mat-label>
          <input matInput type="number" min="1" max="120" formControlName="count" />
        </mat-form-field>
        <mat-form-field appearance="outline" class="span-2">
          <mat-label>{{ entryValue() ? 'Vencimento da entrada' : '1º vencimento' }}</mat-label>
          <input matInput type="date" formControlName="first_due" />
        </mat-form-field>
        <mat-form-field appearance="outline" class="span-2">
          <mat-label>Observações (opcional)</mat-label>
          <textarea matInput rows="2" formControlName="notes"></textarea>
        </mat-form-field>
      </form>

      @if (plan().length) {
        <div class="plan">
          <strong>{{ plan().length }} parcela(s)</strong>
          <ol>
            @for (p of plan().slice(0, 6); track p.number) {
              <li>{{ p.due | date: 'dd/MM/yyyy' }} · {{ fmt(p.amount) }}</li>
            }
            @if (plan().length > 6) {
              <li class="muted">… mais {{ plan().length - 6 }}</li>
            }
          </ol>
        </div>
      }
      @if (error(); as message) {
        <p class="error-text" role="alert">{{ message }}</p>
      }
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button type="button" mat-dialog-close>Fechar</button>
      <button mat-flat-button type="submit" form="agreement-form" [disabled]="busy()">
        Criar contrato
      </button>
    </mat-dialog-actions>
  `,
  styles: `
    .plan {
      margin-top: 8px;
      padding: 10px 14px;
      border-radius: 10px;
      background: var(--mat-sys-surface-container-low);
      font-size: 0.9rem;
    }
    .plan ol {
      margin: 6px 0 0;
      padding-left: 20px;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AgreementDialog {
  readonly data = inject<AgreementDialogData>(MAT_DIALOG_DATA);
  private readonly ref = inject(MatDialogRef<AgreementDialog, FeeAgreement>);
  private readonly api = inject(FinanceiroService);

  readonly kinds = Object.entries(KIND_LABELS) as [AgreementKind, string][];
  readonly client = signal<ClientRef | null>(this.data.client ?? null);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);

  readonly form = inject(NonNullableFormBuilder).group({
    title: ['', Validators.maxLength(200)],
    kind: ['CONTRATUAL' as AgreementKind],
    total: ['', Validators.required],
    entry: [''],
    count: [1, [Validators.required, Validators.min(1), Validators.max(120)]],
    first_due: [nextMonthIso(), Validators.required],
    notes: [''],
  });

  private readonly values = toSignal(this.form.valueChanges, {
    initialValue: this.form.getRawValue(),
  });
  readonly totalValue = computed(() => parseMoney(this.values().total ?? ''));
  readonly entryValue = computed(() => parseMoney(this.values().entry ?? ''));
  readonly plan = computed(() => {
    const v = this.values();
    return previewPlan(
      this.totalValue(),
      Number(v.count ?? 0),
      v.first_due ?? '',
      this.entryValue(),
    );
  });

  fmt(value: number): string {
    return money(value);
  }

  save(): void {
    const client = this.client();
    const total = this.totalValue();
    if (!client) {
      this.error.set('Escolha o cliente.');
      return;
    }
    if (this.form.invalid || !total) {
      this.form.markAllAsTouched();
      return;
    }
    const v = this.form.getRawValue();
    this.busy.set(true);
    this.error.set(null);
    this.api
      .createAgreement({
        client_id: client.id,
        legal_case_id: this.data.legal_case_id ?? null,
        title: v.title.trim(),
        kind: v.kind,
        total_amount: total,
        installments_count: Number(v.count),
        first_due: v.first_due,
        entry_amount: this.entryValue(),
        notes: v.notes,
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
