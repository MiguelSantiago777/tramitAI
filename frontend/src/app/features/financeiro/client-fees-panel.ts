import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  effect,
  inject,
  input,
  signal,
  untracked,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';

import { toApiError } from '../../core/http/api-error';
import { AgreementDialog } from './agreement-dialog';
import {
  FeeAgreement,
  Installment,
  KIND_LABELS,
  installmentState,
  money,
} from './financeiro.models';
import { FinanceiroService } from './financeiro.service';
import { InstallmentActions } from './installment-actions';

/** Honorários do cliente (ficha 360°): contratos e parcelas com as mesmas ações do financeiro. */
@Component({
  selector: 'app-client-fees-panel',
  imports: [DatePipe, MatButtonModule, InstallmentActions],
  template: `
    <section class="card panel-card">
      <header class="panel-card__header">
        <h2 class="section-title"><span class="icon">payments</span> Honorários</h2>
        <button mat-stroked-button type="button" (click)="newAgreement()">
          <span class="icon btn-icon">add</span>Contrato
        </button>
      </header>
      @if (error(); as message) {
        <p class="error-text" role="alert">{{ message }}</p>
      }
      @for (a of agreements(); track a.id) {
        <article class="agreement" [class.agreement--closed]="a.status !== 'ACTIVE'">
          <div class="agreement__top">
            <strong>{{ a.title }}</strong>
            @if (a.status === 'FINISHED') {
              <span class="badge" data-status="PAID">Quitado</span>
            } @else if (a.status === 'CANCELLED') {
              <span class="badge" data-status="ARCHIVED">Cancelado</span>
            }
          </div>
          <p class="muted small agreement__meta">
            {{ kindLabel(a) }} · total {{ fmt(a.total_amount) }} · pago {{ fmt(a.paid_total) }} · em
            aberto {{ fmt(a.open_total) }}
          </p>
          <ol class="installments">
            @for (i of a.installments; track i.id) {
              <li>
                <span class="mono">{{ i.number }}ª · {{ i.due_date | date: 'dd/MM/yyyy' }}</span>
                <strong class="mono">{{ fmt(i.amount) }}</strong>
                <span class="badge" [attr.data-status]="state(i).code">{{ state(i).label }}</span>
                <app-installment-actions [installment]="i" (changed)="reload()" />
              </li>
            }
          </ol>
        </article>
      } @empty {
        <div class="empty-state">
          <span class="icon">payments</span>
          Nenhum contrato de honorários para este cliente.
        </div>
      }
    </section>
  `,
  styles: `
    .agreement {
      padding: 12px 0;
    }
    .agreement + .agreement {
      border-top: 1px solid var(--mat-sys-outline-variant);
    }
    .agreement--closed {
      opacity: 0.7;
    }
    .agreement__top {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .agreement__meta {
      margin: 2px 0 8px;
    }
    .installments {
      list-style: none;
      padding: 0;
      margin: 0;
    }
    .installments li {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 110px 110px 40px;
      align-items: center;
      gap: 12px;
      padding: 2px 0;
    }
    .installments .badge {
      justify-self: start;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ClientFeesPanel {
  private readonly api = inject(FinanceiroService);
  private readonly dialog = inject(MatDialog);

  readonly clientId = input.required<string>();
  readonly clientName = input('');
  readonly agreements = signal<FeeAgreement[]>([]);
  readonly error = signal<string | null>(null);

  constructor() {
    effect(() => {
      const id = this.clientId();
      untracked(() => this.load(id));
    });
  }

  fmt(value: string): string {
    return money(value);
  }

  kindLabel(a: FeeAgreement): string {
    return KIND_LABELS[a.kind];
  }

  state(i: Installment): { label: string; code: string } {
    return installmentState(i);
  }

  reload(): void {
    this.load(this.clientId());
  }

  newAgreement(): void {
    this.dialog
      .open(AgreementDialog, {
        data: { client: { id: this.clientId(), name: this.clientName() } },
        width: '640px',
        maxWidth: '95vw',
      })
      .afterClosed()
      .subscribe((saved) => saved && this.reload());
  }

  private load(id: string): void {
    this.api.agreements(id).subscribe({
      next: (page) => this.agreements.set(page.results),
      error: (err: unknown) => this.error.set(toApiError(err).message),
    });
  }
}
