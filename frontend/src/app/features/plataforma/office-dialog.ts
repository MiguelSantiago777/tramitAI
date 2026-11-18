import { Clipboard } from '@angular/cdk/clipboard';
import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Observable } from 'rxjs';

import { toApiError } from '../../core/http/api-error';
import { money, parseMoney } from '../financeiro/financeiro.models';
import {
  ACTION_LABELS,
  OfficeDetail,
  PlataformaService,
  PlatformPlan,
  STATUS_BADGE,
  STATUS_LABELS,
} from './plataforma.service';

/** Detalhe do escritório e as ações do dono da plataforma. */
@Component({
  selector: 'app-office-dialog',
  imports: [
    DatePipe,
    ReactiveFormsModule,
    MatButtonModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
  ],
  template: `
    @if (office(); as o) {
      <h2 mat-dialog-title>{{ o.name }}</h2>
      <mat-dialog-content>
        <div class="head">
          <span class="badge" [attr.data-status]="badge(o)">{{ label(o) }}</span>
          <span class="muted small">
            {{ o.owner_name || 'Titular' }} · {{ o.owner_email }} · desde
            {{ o.created_at | date: 'dd/MM/yyyy' }}
          </span>
        </div>

        <dl class="kv">
          <dt>Plano</dt>
          <dd>{{ o.plan_name || '—' }} {{ o.price ? '· ' + fmt(o.price) + '/mês' : '' }}</dd>
          <dt>Teste até</dt>
          <dd>{{ (o.trial_ends_at | date: 'dd/MM/yyyy') || '—' }}</dd>
          <dt>Pago até</dt>
          <dd>{{ (o.paid_until | date: 'dd/MM/yyyy') || '—' }}</dd>
          <dt>Acesso até</dt>
          <dd>
            {{
              (o.access_until | date: 'dd/MM/yyyy') || (o.status === 'EXEMPT' ? 'sem limite' : '—')
            }}
          </dd>
          @if (o.usage; as u) {
            <dt>Uso no mês</dt>
            <dd>
              {{ u.members }} usuário(s) · {{ u.clients }} cliente(s) ·
              {{ u.messages_in }} mensagens recebidas · {{ u.ai_calls }} chamadas da Lia
            </dd>
          }
        </dl>

        <h3>Ações</h3>
        <div class="actions">
          <div class="inline-form">
            <mat-form-field appearance="outline" subscriptSizing="dynamic" class="small-field">
              <mat-label>Dias</mat-label>
              <input matInput type="number" min="1" max="90" [formControl]="days" />
            </mat-form-field>
            <button mat-stroked-button type="button" [disabled]="busy()" (click)="extend()">
              Estender teste
            </button>
          </div>

          <div class="inline-form">
            <mat-form-field appearance="outline" subscriptSizing="dynamic" class="small-field">
              <mat-label>Valor (R$)</mat-label>
              <input matInput [formControl]="amount" inputmode="decimal" />
            </mat-form-field>
            <mat-form-field appearance="outline" subscriptSizing="dynamic" class="small-field">
              <mat-label>Meses</mat-label>
              <input matInput type="number" min="1" max="24" [formControl]="months" />
            </mat-form-field>
            <mat-form-field appearance="outline" subscriptSizing="dynamic" class="grow">
              <mat-label>Observação</mat-label>
              <input matInput [formControl]="note" placeholder="Ex.: Pix direto" />
            </mat-form-field>
            <button mat-stroked-button type="button" [disabled]="busy()" (click)="manual()">
              Lançar pagamento
            </button>
          </div>

          <div class="inline-form">
            <mat-form-field appearance="outline" subscriptSizing="dynamic" class="grow">
              <mat-label>Plano</mat-label>
              <mat-select [formControl]="plan">
                @for (p of data.plans; track p.code) {
                  <mat-option [value]="p.code">{{ p.name }} · {{ fmt(p.price) }}</mat-option>
                }
              </mat-select>
            </mat-form-field>
            <button mat-stroked-button type="button" [disabled]="busy()" (click)="changePlan()">
              Trocar plano
            </button>
          </div>

          <div class="buttons">
            @if (o.status !== 'EXEMPT') {
              <button mat-stroked-button type="button" [disabled]="busy()" (click)="link()">
                Copiar link de pagamento
              </button>
            }
            <button
              mat-stroked-button
              type="button"
              [disabled]="busy()"
              (click)="run('exempt', { exempt: o.status !== 'EXEMPT' })"
            >
              {{ o.status === 'EXEMPT' ? 'Remover isenção' : 'Dar cortesia (isentar)' }}
            </button>
            <button
              mat-button
              type="button"
              [class.dialog-danger]="o.status !== 'SUSPENDED'"
              [disabled]="busy()"
              (click)="run('suspend', { suspended: o.status !== 'SUSPENDED' })"
            >
              {{ o.status === 'SUSPENDED' ? 'Desbloquear' : 'Bloquear acesso' }}
            </button>
          </div>
        </div>
        @if (error(); as message) {
          <p class="error-text" role="alert">{{ message }}</p>
        }

        <h3>Pagamentos</h3>
        <ul class="plain">
          @for (p of o.payments; track p.id) {
            <li>
              {{ p.paid_at | date: 'dd/MM/yyyy' }} · <strong>{{ fmt(p.amount) }}</strong> ·
              {{
                p.source === 'MANUAL'
                  ? 'lançado' + (p.created_by ? ' por ' + p.created_by : '')
                  : 'Mercado Pago'
              }}
              @if (p.status !== 'PAID') {
                · <span class="badge" data-status="OVERDUE">recusado</span>
              }
              @if (p.note) {
                <span class="muted"> · {{ p.note }}</span>
              }
            </li>
          } @empty {
            <li class="muted">Nenhum pagamento ainda.</li>
          }
        </ul>

        <h3>Histórico de ações</h3>
        <ul class="plain">
          @for (h of o.history; track h.at) {
            <li>
              {{ h.at | date: 'dd/MM/yyyy HH:mm' }} · {{ actionLabel(h.action) }}
              <span class="muted">· {{ h.by }}</span>
            </li>
          } @empty {
            <li class="muted">Nenhuma ação ainda.</li>
          }
        </ul>
      </mat-dialog-content>
      <mat-dialog-actions align="end">
        <button mat-button type="button" [mat-dialog-close]="changed">Fechar</button>
      </mat-dialog-actions>
    }
  `,
  styles: `
    .head {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px 12px;
      margin-bottom: 12px;
    }
    .kv {
      display: grid;
      grid-template-columns: 130px minmax(0, 1fr);
      gap: 6px 12px;
      margin: 0 0 8px;
    }
    .kv dt {
      color: var(--mat-sys-on-surface-variant);
    }
    .kv dd {
      margin: 0;
    }
    h3 {
      margin: 20px 0 8px;
      font:
        600 14px / 1.4 Inter,
        system-ui,
        sans-serif;
    }
    .actions {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .actions .inline-form {
      margin-top: 0;
    }
    .small-field {
      width: 120px;
    }
    .buttons {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .plain {
      margin: 0;
      padding-left: 18px;
      line-height: 1.8;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class OfficeDialog {
  readonly data = inject<{ office: OfficeDetail; plans: PlatformPlan[] }>(MAT_DIALOG_DATA);
  private readonly api = inject(PlataformaService);
  private readonly snack = inject(MatSnackBar);
  private readonly clipboard = inject(Clipboard);
  readonly ref = inject(MatDialogRef<OfficeDialog, boolean>);

  readonly office = signal<OfficeDetail>(this.data.office);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  changed = false;

  readonly days = new FormControl(7, { nonNullable: true });
  readonly amount = new FormControl(
    this.data.office.price ? Number(this.data.office.price).toFixed(2).replace('.', ',') : '',
    { nonNullable: true },
  );
  readonly months = new FormControl(1, { nonNullable: true });
  readonly note = new FormControl('', { nonNullable: true });
  readonly plan = new FormControl(this.data.office.plan_code, { nonNullable: true });

  fmt(value: string | number): string {
    return money(value);
  }

  label(o: OfficeDetail): string {
    return STATUS_LABELS[o.status];
  }

  badge(o: OfficeDetail): string {
    return STATUS_BADGE[o.status];
  }

  actionLabel(action: string): string {
    return ACTION_LABELS[action] ?? action;
  }

  extend(): void {
    this.run('extend-trial', { days: Number(this.days.value) });
  }

  manual(): void {
    const amount = parseMoney(this.amount.value);
    if (!amount) {
      this.error.set('Informe o valor recebido.');
      return;
    }
    this.run('manual-payment', {
      amount,
      months: Number(this.months.value),
      note: this.note.value,
    });
  }

  changePlan(): void {
    this.run('plan', { plan_code: this.plan.value });
  }

  link(): void {
    this.busy.set(true);
    this.api.paymentLink(this.office().id).subscribe({
      next: ({ checkout_url }) => {
        this.busy.set(false);
        this.clipboard.copy(checkout_url);
        this.snack.open('Link de pagamento copiado. Mande para o titular.', 'OK', {
          duration: 4000,
        });
      },
      error: (err: unknown) => this.fail(err),
    });
  }

  run(action: string, body: Record<string, unknown>): void {
    this.busy.set(true);
    this.error.set(null);
    this.request(this.api.action(this.office().id, action, body));
  }

  private request(call: Observable<OfficeDetail>): void {
    call.subscribe({
      next: (o) => {
        this.busy.set(false);
        this.office.set(o);
        this.changed = true;
        this.snack.open('Feito.', undefined, { duration: 2000 });
      },
      error: (err: unknown) => this.fail(err),
    });
  }

  private fail(err: unknown): void {
    this.busy.set(false);
    this.error.set(toApiError(err).message);
  }
}
