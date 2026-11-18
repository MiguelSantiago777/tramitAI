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
        <h1>Financeiro</h1>
        <p>Honorários, parcelas e cobranças por Pix ou link do Mercado Pago.</p>
      </div>
      <div class="actions">
        <a mat-stroked-button routerLink="/configuracoes/financeiro">
          <span class="icon btn-icon">account_balance</span>Mercado Pago
        </a>
        <button mat-flat-button type="button" (click)="newAgreement()">
          <span class="icon btn-icon">add</span>Novo contrato
        </button>
      </div>
    </header>

    <section class="stats" aria-label="Resumo do mês">
      <div class="stat card" data-tone="green">
        <span class="stat__icon"><span class="icon">savings</span></span>
        <span class="stat__value">{{ fmt(summary()?.received) }}</span>
        <span class="stat__label">Recebido no mês</span>
        <span class="stat__hint">Parcelas pagas neste mês</span>
      </div>
      <div class="stat card">
        <span class="stat__icon"><span class="icon">calendar_month</span></span>
        <span class="stat__value">{{ fmt(summary()?.expected) }}</span>
        <span class="stat__label">Previsto no mês</span>
        <span class="stat__hint">Parcelas que vencem neste mês</span>
      </div>
      <button type="button" class="stat card" data-tone="red" (click)="setFilter('overdue')">
        <span class="stat__icon"><span class="icon">warning</span></span>
        <span class="stat__value">{{ fmt(summary()?.overdue_total) }}</span>
        <span class="stat__label">Em atraso</span>
        <span class="stat__hint">{{ summary()?.overdue_count ?? 0 }} parcela(s) · ver lista</span>
      </button>
      <div class="stat card" data-tone="teal">
        <span class="stat__icon"><span class="icon">event_upcoming</span></span>
        <span class="stat__value">{{ fmt(summary()?.next_30_days) }}</span>
        <span class="stat__label">Próximos 30 dias</span>
        <span class="stat__hint">A receber em aberto</span>
      </div>
    </section>

    <div class="filters">
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
      <mat-form-field appearance="outline" class="filters__search" subscriptSizing="dynamic">
        <span matPrefix class="icon search-icon">search</span>
        <mat-label>Buscar</mat-label>
        <input matInput [formControl]="search" placeholder="Cliente ou contrato" />
      </mat-form-field>
    </div>

    @if (loading()) {
      <mat-progress-bar mode="indeterminate" />
    }
    @if (error(); as message) {
      <p class="error-text" role="alert">{{ message }}</p>
    }

    <section class="card">
      <ul class="row-list">
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
              <span class="muted small">{{ i.status === 'PAID' ? 'Pago em' : 'Vencimento' }}</span>
              <span class="mono">{{
                (i.status === 'PAID' ? i.paid_at : i.due_date) | date: 'dd/MM/yyyy'
              }}</span>
            </div>
            <strong class="row__amount mono">{{
              fmt(i.status === 'PAID' ? i.paid_amount : i.amount)
            }}</strong>
            <div class="row__status">
              <span class="badge" [attr.data-status]="state(i).code">{{ state(i).label }}</span>
              @if (i.status === 'PAID' && i.method) {
                <span class="muted small">{{ methodLabel(i) }}</span>
              }
              @if (i.status === 'OPEN' && i.has_active_charge) {
                <span class="muted small">{{
                  i.charge_kind === 'PIX' ? 'Pix gerado' : 'Link gerado'
                }}</span>
              }
            </div>
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
      @if (total() > 25) {
        <mat-paginator
          [length]="total()"
          [pageIndex]="pageIndex()"
          [pageSize]="25"
          [hidePageSize]="true"
          (page)="onPage($event)"
        />
      }
    </section>
  `,
  styles: `
    .stat__value {
      font-size: 26px;
    }
    .actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    .row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 110px 120px 150px 40px;
      gap: 16px;
      align-items: center;
      padding: 12px 0;
    }
    .row__main,
    .row__due,
    .row__status {
      display: flex;
      flex-direction: column;
      gap: 2px;
      min-width: 0;
    }
    .row__status {
      align-items: flex-start;
    }
    .row__client {
      font-weight: 600;
      color: inherit;
      text-decoration: none;
    }
    .row__client:hover {
      color: var(--mat-sys-primary);
    }
    .row__amount {
      text-align: right;
    }
    @media (max-width: 760px) {
      .row {
        grid-template-columns: minmax(0, 1fr) auto 40px;
      }
      .row__due,
      .row__status {
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

  state(i: Installment): { label: string; code: string } {
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
