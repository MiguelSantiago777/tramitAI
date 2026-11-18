import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { RouterLink } from '@angular/router';
import { debounceTime, distinctUntilChanged } from 'rxjs';

import { toApiError } from '../../core/http/api-error';
import { AgreementDialog } from './agreement-dialog';
import {
  FinanceSummary,
  Installment,
  InstallmentFilter,
  METHOD_LABELS,
  installmentState,
  money,
} from './financeiro.models';
import { FinanceiroService } from './financeiro.service';
import { InstallmentActions } from './installment-actions';

function currentMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

@Component({
  selector: 'app-finance-page',
  imports: [
    DatePipe,
    ReactiveFormsModule,
    RouterLink,
    MatButtonModule,
    MatButtonToggleModule,
    MatFormFieldModule,
    MatInputModule,
    MatPaginatorModule,
    MatProgressBarModule,
    InstallmentActions,
  ],
  template: `
    <header class="page-header">
      <div>
        <h1 class="page-title">Financeiro</h1>
        <p class="muted">Honorários, parcelas e cobranças por Pix ou link do Mercado Pago.</p>
      </div>
      <span class="spacer"></span>
      <a mat-stroked-button routerLink="/configuracoes/financeiro">
        <span class="icon btn-icon">account_balance</span>Mercado Pago
      </a>
      <button mat-flat-button type="button" (click)="newAgreement()">
        <span class="icon btn-icon">add</span>Novo contrato
      </button>
    </header>

    <section class="stats">
      <div class="card stat">
        <span class="stat__label">Recebido no mês</span>
        <strong class="stat__value success">{{ fmt(summary()?.received) }}</strong>
      </div>
      <div class="card stat">
        <span class="stat__label">Previsto no mês</span>
        <strong class="stat__value">{{ fmt(summary()?.expected) }}</strong>
      </div>
      <button type="button" class="card stat stat--action" (click)="setFilter('overdue')">
        <span class="stat__label">Em atraso ({{ summary()?.overdue_count ?? 0 }})</span>
        <strong class="stat__value danger">{{ fmt(summary()?.overdue_total) }}</strong>
      </button>
      <div class="card stat">
        <span class="stat__label">Próximos 30 dias</span>
        <strong class="stat__value">{{ fmt(summary()?.next_30_days) }}</strong>
      </div>
    </section>

    <section class="card">
      <div class="toolbar">
        <mat-button-toggle-group
          [value]="filter()"
          (change)="setFilter($event.value)"
          aria-label="Filtrar parcelas"
        >
          <mat-button-toggle value="open">Em aberto</mat-button-toggle>
          <mat-button-toggle value="overdue">Atrasadas</mat-button-toggle>
          <mat-button-toggle value="paid">Pagas</mat-button-toggle>
          <mat-button-toggle value="">Todas</mat-button-toggle>
        </mat-button-toggle-group>
        <mat-form-field appearance="outline" subscriptSizing="dynamic" class="search">
          <mat-label>Buscar cliente ou contrato</mat-label>
          <input matInput [formControl]="search" />
        </mat-form-field>
      </div>

      @if (loading()) {
        <mat-progress-bar mode="indeterminate" />
      }
      @if (error(); as message) {
        <p class="error-text" role="alert">{{ message }}</p>
      }

      <ul class="rows">
        @for (i of items(); track i.id) {
          <li class="row">
            <div class="row__main">
              <a [routerLink]="['/clientes', i.client_id]" class="row__client">{{
                i.client_name
              }}</a>
              <span class="muted small"
                >{{ i.agreement_title }} · parcela {{ i.number }}
                @if (i.case_number) {
                  · <span class="mono">{{ i.case_number }}</span>
                }
              </span>
            </div>
            <div class="row__due">
              <span class="small muted">{{ i.status === 'PAID' ? 'Pago em' : 'Vence' }}</span>
              <span>{{ (i.status === 'PAID' ? i.paid_at : i.due_date) | date: 'dd/MM/yyyy' }}</span>
            </div>
            <strong class="row__amount">{{
              fmt(i.status === 'PAID' ? i.paid_amount : i.amount)
            }}</strong>
            <span class="pill" [attr.data-tone]="state(i).tone">
              {{ state(i).label }}
              @if (i.status === 'PAID' && i.method) {
                · {{ methodLabel(i) }}
              }
              @if (i.status === 'OPEN' && i.has_active_charge) {
                · {{ i.charge_kind === 'PIX' ? 'Pix gerado' : 'Link gerado' }}
              }
            </span>
            <app-installment-actions [installment]="i" (changed)="onChanged($event)" />
          </li>
        } @empty {
          @if (!loading()) {
            <li class="empty-state">
              <span class="icon">payments</span>
              Nenhuma parcela aqui. Crie um contrato de honorários para começar.
            </li>
          }
        }
      </ul>
      <mat-paginator
        [length]="total()"
        [pageIndex]="pageIndex()"
        [pageSize]="25"
        [hidePageSize]="true"
        (page)="onPage($event)"
      />
    </section>
  `,
  styles: `
    .page-header {
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 16px;
    }
    .spacer {
      flex: 1;
    }
    .stats {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }
    .stat {
      display: grid;
      gap: 4px;
      text-align: left;
      font: inherit;
      color: inherit;
    }
    .stat--action {
      cursor: pointer;
      border: 0;
    }
    .stat__label {
      font-size: 0.85rem;
      color: var(--mat-sys-on-surface-variant);
    }
    .stat__value {
      font-size: 1.4rem;
    }
    .success {
      color: var(--tm-success);
    }
    .danger {
      color: var(--tm-danger);
    }
    .toolbar {
      display: flex;
      gap: 12px;
      align-items: center;
      flex-wrap: wrap;
      margin-bottom: 12px;
    }
    .search {
      flex: 1;
      min-width: 220px;
    }
    .rows {
      list-style: none;
      margin: 0;
      padding: 0;
    }
    .row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 110px 120px 170px 40px;
      gap: 12px;
      align-items: center;
      padding: 10px 0;
      border-top: 1px solid var(--mat-sys-outline-variant);
    }
    .row__main {
      display: grid;
      min-width: 0;
    }
    .row__client {
      font-weight: 600;
      text-decoration: none;
      color: inherit;
    }
    .row__due {
      display: grid;
    }
    .row__amount {
      text-align: right;
    }
    .pill {
      justify-self: start;
      padding: 2px 10px;
      border-radius: 999px;
      font-size: 0.8rem;
      background: var(--tm-neutral-soft);
    }
    .pill[data-tone='success'] {
      background: var(--tm-success-soft);
      color: var(--tm-success);
    }
    .pill[data-tone='danger'] {
      background: var(--tm-danger-soft);
      color: var(--tm-danger);
    }
    .pill[data-tone='info'] {
      background: var(--tm-info-soft);
      color: var(--tm-info);
    }
    @media (max-width: 760px) {
      .row {
        grid-template-columns: 1fr auto 40px;
      }
      .row__due,
      .pill {
        display: none;
      }
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FinancePage {
  private readonly api = inject(FinanceiroService);
  private readonly dialog = inject(MatDialog);

  readonly summary = signal<FinanceSummary | null>(null);
  readonly items = signal<Installment[]>([]);
  readonly total = signal(0);
  readonly pageIndex = signal(0);
  readonly filter = signal<InstallmentFilter>('open');
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly search = new FormControl('', { nonNullable: true });

  constructor() {
    this.search.valueChanges
      .pipe(debounceTime(300), distinctUntilChanged(), takeUntilDestroyed())
      .subscribe(() => {
        this.pageIndex.set(0);
        this.load();
      });
    this.refresh();
  }

  fmt(value: string | null | undefined): string {
    return money(value);
  }

  state(i: Installment): { label: string; tone: string } {
    return installmentState(i);
  }

  methodLabel(i: Installment): string {
    return i.method ? METHOD_LABELS[i.method] : '';
  }

  setFilter(value: InstallmentFilter): void {
    this.filter.set(value);
    this.pageIndex.set(0);
    this.load();
  }

  onPage(event: PageEvent): void {
    this.pageIndex.set(event.pageIndex);
    this.load();
  }

  onChanged(updated: Installment): void {
    this.items.update((list) => list.map((i) => (i.id === updated.id ? updated : i)));
    this.loadSummary();
  }

  newAgreement(): void {
    this.dialog
      .open(AgreementDialog, { data: {}, width: '640px', maxWidth: '95vw' })
      .afterClosed()
      .subscribe((saved) => saved && this.refresh());
  }

  private refresh(): void {
    this.loadSummary();
    this.load();
  }

  private loadSummary(): void {
    this.api.summary(currentMonth()).subscribe({ next: (s) => this.summary.set(s) });
  }

  private load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api
      .installments({ status: this.filter(), q: this.search.value.trim() }, this.pageIndex())
      .subscribe({
        next: (page) => {
          this.loading.set(false);
          this.items.set(page.results);
          this.total.set(page.count);
        },
        error: (err: unknown) => {
          this.loading.set(false);
          this.error.set(toApiError(err).message);
        },
      });
  }
}
