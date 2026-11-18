import { DatePipe, DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Observable, debounceTime, distinctUntilChanged } from 'rxjs';

import { toApiError } from '../../core/http/api-error';
import { money, parseMoney } from '../financeiro/financeiro.models';
import { OfficeDialog } from './office-dialog';
import {
  Office,
  OfficeStatus,
  Overview,
  PlataformaService,
  PlatformPayment,
  PlatformPlan,
  STATUS_BADGE,
  STATUS_LABELS,
} from './plataforma.service';

type Tab = 'geral' | 'escritorios' | 'pagamentos' | 'planos';

/** Painel do dono do TramitAI: receita, assinaturas e gestão dos escritórios. */
@Component({
  selector: 'app-plataforma-page',
  imports: [
    DatePipe,
    DecimalPipe,
    ReactiveFormsModule,
    MatButtonModule,
    MatButtonToggleModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressBarModule,
    MatSelectModule,
    MatSlideToggleModule,
  ],
  template: `
    <header class="page-header">
      <div>
        <h1>Painel da plataforma</h1>
        <p>Assinaturas, receita e escritórios do TramitAI. Só você vê esta área.</p>
      </div>
    </header>

    <div class="filters">
      <mat-button-toggle-group [value]="tab()" (change)="setTab($event.value)">
        <mat-button-toggle value="geral">Visão geral</mat-button-toggle>
        <mat-button-toggle value="escritorios">Escritórios</mat-button-toggle>
        <mat-button-toggle value="pagamentos">Pagamentos</mat-button-toggle>
        <mat-button-toggle value="planos">Planos</mat-button-toggle>
      </mat-button-toggle-group>
    </div>

    @if (loading()) {
      <mat-progress-bar mode="indeterminate" />
    }
    @if (error(); as message) {
      <p class="error-text" role="alert">{{ message }}</p>
    }

    @switch (tab()) {
      @case ('geral') {
        @if (overview(); as o) {
          <section class="stats">
            <div class="stat card" data-tone="green">
              <span class="stat__icon"><span class="icon">payments</span></span>
              <span class="stat__value">{{ fmt(o.mrr) }}</span>
              <span class="stat__label">Receita mensal recorrente</span>
              <span class="stat__hint">Assinaturas ativas × preço do plano</span>
            </div>
            <div class="stat card">
              <span class="stat__icon"><span class="icon">domain</span></span>
              <span class="stat__value">{{ o.by_status['ACTIVE'] ?? 0 }}</span>
              <span class="stat__label">Escritórios pagantes</span>
              <span class="stat__hint">de {{ o.offices }} no total</span>
            </div>
            <div class="stat card" data-tone="teal">
              <span class="stat__icon"><span class="icon">hourglass_top</span></span>
              <span class="stat__value">{{ o.by_status['TRIAL'] ?? 0 }}</span>
              <span class="stat__label">Em teste grátis</span>
              <span class="stat__hint">
                @if (o.conversion !== null) {
                  {{ o.conversion | number: '1.0-1' }}% viram pagantes
                } @else {
                  conversão aparece quando os testes terminarem
                }
              </span>
            </div>
            <div class="stat card" data-tone="red">
              <span class="stat__icon"><span class="icon">warning</span></span>
              <span class="stat__value">{{ o.attention.length }}</span>
              <span class="stat__label">Precisam de atenção</span>
              <span class="stat__hint">Atrasados, aguardando ou bloqueados</span>
            </div>
          </section>

          <div class="columns">
            <section class="card panel-card">
              <header class="panel-card__header">
                <h2 class="section-title">
                  <span class="icon">schedule</span> Testes acabando (7 dias)
                </h2>
              </header>
              <ul class="row-list list">
                @for (r of o.trials_ending; track r.id) {
                  <li>
                    <button type="button" class="link-row" (click)="open(r)">
                      <strong>{{ r.name }}</strong>
                      <span class="muted small">
                        {{ r.owner_email }} · termina {{ r.trial_ends_at | date: 'dd/MM' }}
                      </span>
                    </button>
                  </li>
                } @empty {
                  <li class="muted small empty">Nenhum teste terminando nos próximos dias.</li>
                }
              </ul>
            </section>
            <section class="card panel-card">
              <header class="panel-card__header">
                <h2 class="section-title"><span class="icon">priority_high</span> Atenção</h2>
              </header>
              <ul class="row-list list">
                @for (r of o.attention; track r.id) {
                  <li>
                    <button type="button" class="link-row" (click)="open(r)">
                      <strong>{{ r.name }}</strong>
                      <span class="small">
                        <span class="badge" [attr.data-status]="badge(r.status)">{{
                          label(r.status)
                        }}</span>
                        <span class="muted"> {{ r.owner_email }}</span>
                      </span>
                    </button>
                  </li>
                } @empty {
                  <li class="muted small empty">Tudo em dia.</li>
                }
              </ul>
            </section>
            <section class="card panel-card">
              <header class="panel-card__header">
                <h2 class="section-title"><span class="icon">bar_chart</span> Recebido por mês</h2>
              </header>
              <div class="chart">
                @for (m of revenue(); track m.month) {
                  <div class="chart__col" [attr.title]="fmt(m.total)">
                    <span class="chart__value small">{{ short(m.total) }}</span>
                    <span class="chart__bar" [style.height.%]="m.pct"></span>
                    <span class="chart__label">{{ m.month | date: 'MMM' }}</span>
                  </div>
                }
              </div>
            </section>
            <section class="card panel-card">
              <header class="panel-card__header">
                <h2 class="section-title">
                  <span class="icon">person_add</span> Cadastros por semana
                </h2>
              </header>
              <div class="chart">
                @for (w of signups(); track w.week) {
                  <div class="chart__col">
                    <span class="chart__value small">{{ w.count }}</span>
                    <span class="chart__bar chart__bar--alt" [style.height.%]="w.pct"></span>
                    <span class="chart__label">{{ w.week | date: 'dd/MM' }}</span>
                  </div>
                }
              </div>
            </section>
          </div>
        }
      }

      @case ('escritorios') {
        <div class="filters">
          <mat-form-field appearance="outline" class="filters__search" subscriptSizing="dynamic">
            <span matPrefix class="icon search-icon">search</span>
            <mat-label>Buscar</mat-label>
            <input matInput [formControl]="search" placeholder="Nome do escritório ou e-mail" />
          </mat-form-field>
          <mat-form-field appearance="outline" subscriptSizing="dynamic">
            <mat-label>Situação</mat-label>
            <mat-select [formControl]="status">
              <mat-option value="">Todas</mat-option>
              @for (s of statuses; track s[0]) {
                <mat-option [value]="s[0]">{{ s[1] }}</mat-option>
              }
            </mat-select>
          </mat-form-field>
        </div>
        <section class="card">
          <ul class="row-list">
            @for (r of offices(); track r.id) {
              <li>
                <button type="button" class="office" (click)="open(r)">
                  <span class="office__main">
                    <strong>{{ r.name }}</strong>
                    <span class="muted small">{{ r.owner_name }} · {{ r.owner_email }}</span>
                  </span>
                  <span class="office__col">
                    <span class="badge" [attr.data-status]="badge(r.status)">{{
                      label(r.status)
                    }}</span>
                    <span class="muted small">{{ r.plan_name }}</span>
                  </span>
                  <span class="office__col small">
                    @if (r.status === 'TRIAL') {
                      teste até {{ r.trial_ends_at | date: 'dd/MM/yyyy' }}
                    } @else if (r.paid_until) {
                      pago até {{ r.paid_until | date: 'dd/MM/yyyy' }}
                    } @else {
                      <span class="muted">—</span>
                    }
                  </span>
                  @if (r.usage; as u) {
                    <span class="office__col muted small">
                      {{ u.members }} usuários · {{ u.messages_in }} msgs · {{ u.ai_calls }} Lia
                    </span>
                  }
                </button>
              </li>
            } @empty {
              @if (!loading()) {
                <li class="empty-state"><span class="icon">domain</span>Nenhum escritório.</li>
              }
            }
          </ul>
        </section>
      }

      @case ('pagamentos') {
        <section class="card">
          <ul class="row-list">
            @for (p of payments(); track p.id) {
              <li class="payment">
                <span class="mono">{{ p.paid_at | date: 'dd/MM/yyyy' }}</span>
                <strong>{{ p.office_name }}</strong>
                <span class="muted small">
                  {{
                    p.source === 'MANUAL'
                      ? 'Lançado' + (p.created_by ? ' por ' + p.created_by : '')
                      : 'Mercado Pago'
                  }}
                  {{ p.note ? '· ' + p.note : '' }}
                </span>
                <strong class="mono amount">{{ fmt(p.amount) }}</strong>
                <span class="badge" [attr.data-status]="p.status === 'PAID' ? 'PAID' : 'OVERDUE'">{{
                  p.status === 'PAID' ? 'Pago' : 'Recusado'
                }}</span>
              </li>
            } @empty {
              @if (!loading()) {
                <li class="empty-state">
                  <span class="icon">payments</span>Nenhum pagamento ainda.
                </li>
              }
            }
          </ul>
        </section>
      }

      @case ('planos') {
        <section class="card panel-card">
          <header class="panel-card__header">
            <h2 class="section-title"><span class="icon">sell</span> Planos</h2>
            <button mat-stroked-button type="button" (click)="newPlan()">
              <span class="icon btn-icon">add</span>Novo plano
            </button>
          </header>
          @for (p of plans(); track p.code) {
            <form class="plan" (submit)="$event.preventDefault()">
              <mat-form-field appearance="outline" subscriptSizing="dynamic">
                <mat-label>Nome</mat-label>
                <input matInput [value]="p.name" #name />
              </mat-form-field>
              <mat-form-field appearance="outline" subscriptSizing="dynamic" class="plan__price">
                <mat-label>Preço/mês (R$)</mat-label>
                <input matInput [value]="p.price.replace('.', ',')" #price inputmode="decimal" />
              </mat-form-field>
              <mat-form-field appearance="outline" subscriptSizing="dynamic" class="plan__desc">
                <mat-label>Descrição</mat-label>
                <input matInput [value]="p.description" #desc />
              </mat-form-field>
              <mat-slide-toggle [checked]="p.is_active" #active>À venda</mat-slide-toggle>
              <button
                mat-flat-button
                type="button"
                (click)="savePlan(p, name.value, price.value, desc.value, active.checked)"
              >
                Salvar
              </button>
            </form>
          }
          <p class="muted small">
            Mudar o preço vale para assinaturas novas. Quem já assinou continua com o valor
            combinado no Mercado Pago.
          </p>
        </section>
      }
    }
  `,
  styles: `
    .columns {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 0 16px;
    }
    .columns .panel-card {
      margin: 0 0 16px;
    }
    @media (max-width: 1000px) {
      .columns {
        grid-template-columns: 1fr;
      }
    }
    .stat__value {
      font-size: 26px;
    }
    .list {
      padding: 0;
    }
    .empty {
      padding: 8px 0;
    }
    .link-row,
    .office {
      display: flex;
      width: 100%;
      padding: 10px 0;
      border: 0;
      background: none;
      text-align: left;
      font: inherit;
      color: inherit;
      cursor: pointer;
    }
    .link-row {
      flex-direction: column;
      gap: 2px;
    }
    .link-row:hover strong,
    .office:hover strong {
      color: var(--mat-sys-primary);
    }
    .office {
      display: grid;
      grid-template-columns: minmax(0, 2fr) 170px 150px minmax(0, 1.2fr);
      gap: 12px;
      align-items: center;
    }
    .office__main,
    .office__col {
      display: flex;
      flex-direction: column;
      gap: 2px;
      align-items: flex-start;
      min-width: 0;
    }
    .payment {
      display: grid;
      grid-template-columns: 100px minmax(0, 1fr) minmax(0, 1fr) 120px 90px;
      gap: 12px;
      align-items: center;
      padding: 10px 0;
    }
    .amount {
      text-align: right;
    }
    .chart {
      display: flex;
      align-items: flex-end;
      gap: 10px;
      height: 160px;
    }
    .chart__col {
      flex: 1;
      height: 100%;
      display: flex;
      flex-direction: column;
      justify-content: flex-end;
      align-items: center;
      gap: 4px;
    }
    .chart__bar {
      width: 60%;
      min-height: 2px;
      border-radius: 4px 4px 0 0;
      background: var(--tm-success);
    }
    .chart__bar--alt {
      background: var(--mat-sys-primary);
    }
    .chart__label,
    .chart__value {
      color: var(--mat-sys-on-surface-variant);
    }
    .plan {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 12px;
      padding: 8px 0;
      border-top: 1px solid var(--mat-sys-outline-variant);
    }
    .plan__price {
      width: 150px;
    }
    .plan__desc {
      flex: 1 1 260px;
    }
    @media (max-width: 900px) {
      .office,
      .payment {
        grid-template-columns: 1fr;
      }
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PlataformaPage {
  private readonly api = inject(PlataformaService);
  private readonly dialog = inject(MatDialog);
  private readonly snack = inject(MatSnackBar);

  readonly tab = signal<Tab>('geral');
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly overview = signal<Overview | null>(null);
  readonly offices = signal<Office[]>([]);
  readonly payments = signal<PlatformPayment[]>([]);
  readonly plans = signal<PlatformPlan[]>([]);
  readonly search = new FormControl('', { nonNullable: true });
  readonly status = new FormControl<OfficeStatus | ''>('', { nonNullable: true });
  readonly statuses = Object.entries(STATUS_LABELS) as [OfficeStatus, string][];

  readonly revenue = computed(() => {
    const months = this.overview()?.revenue_by_month ?? [];
    const max = Math.max(1, ...months.map((m) => Number(m.total)));
    // Dia 15: o mês não "volta" por fuso ao formatar.
    return months.map((m) => ({
      ...m,
      month: m.month.slice(0, 8) + '15',
      pct: (100 * Number(m.total)) / max,
    }));
  });
  readonly signups = computed(() => {
    const weeks = this.overview()?.signups_by_week ?? [];
    const max = Math.max(1, ...weeks.map((w) => w.count));
    return weeks.map((w) => ({ ...w, week: w.week + 'T12:00:00', pct: (100 * w.count) / max }));
  });

  constructor() {
    this.search.valueChanges
      .pipe(debounceTime(300), distinctUntilChanged(), takeUntilDestroyed())
      .subscribe(() => this.loadOffices());
    this.status.valueChanges.pipe(takeUntilDestroyed()).subscribe(() => this.loadOffices());
    this.api.plans().subscribe({ next: (p) => this.plans.set(p) });
    this.loadOverview();
  }

  fmt(value: string | number): string {
    return money(value);
  }

  short(value: string): string {
    const n = Number(value);
    return n >= 1000 ? `${(n / 1000).toFixed(1).replace('.', ',')} mil` : money(n);
  }

  label(s: OfficeStatus): string {
    return STATUS_LABELS[s];
  }

  badge(s: OfficeStatus): string {
    return STATUS_BADGE[s];
  }

  setTab(tab: Tab): void {
    this.tab.set(tab);
    if (tab === 'geral') this.loadOverview();
    if (tab === 'escritorios') this.loadOffices();
    if (tab === 'pagamentos') this.track(this.api.payments(), (p) => this.payments.set(p));
  }

  open(office: Office): void {
    this.api.office(office.id).subscribe({
      next: (detail) =>
        this.dialog
          .open(OfficeDialog, {
            data: { office: detail, plans: this.plans() },
            width: '760px',
            maxWidth: '95vw',
          })
          .afterClosed()
          .subscribe((changed) => changed && this.setTab(this.tab())),
      error: (err: unknown) => this.error.set(toApiError(err).message),
    });
  }

  newPlan(): void {
    const code = `plano-${this.plans().length + 1}`;
    this.plans.update((list) => [
      ...list,
      {
        id: 0,
        code,
        name: 'Novo plano',
        price: '0.00',
        description: '',
        max_users: null,
        is_active: false,
        sort: list.length,
      },
    ]);
  }

  savePlan(
    p: PlatformPlan,
    name: string,
    price: string,
    description: string,
    active: boolean,
  ): void {
    const value = parseMoney(price);
    if (!value) {
      this.snack.open('Preço inválido.', 'OK', { duration: 3000 });
      return;
    }
    const body: Partial<PlatformPlan> = {
      ...(p.id ? { id: p.id } : { code: p.code, sort: p.sort }),
      name: name.trim(),
      price: value,
      description: description.trim(),
      is_active: active,
    };
    this.api.savePlan(body).subscribe({
      next: (saved) => {
        this.plans.update((list) => list.map((x) => (x.code === saved.code ? saved : x)));
        this.snack.open('Plano salvo.', undefined, { duration: 2500 });
      },
      error: (err: unknown) => this.snack.open(toApiError(err).message, 'OK', { duration: 5000 }),
    });
  }

  private loadOverview(): void {
    this.track(this.api.overview(), (o) => this.overview.set(o));
  }

  private loadOffices(): void {
    this.track(this.api.offices(this.search.value.trim(), this.status.value), (o) =>
      this.offices.set(o),
    );
  }

  private track<T>(request: Observable<T>, done: (value: T) => void): void {
    this.loading.set(true);
    this.error.set(null);
    request.subscribe({
      next: (value) => {
        this.loading.set(false);
        done(value);
      },
      error: (err: unknown) => {
        this.loading.set(false);
        this.error.set(toApiError(err).message);
      },
    });
  }
}
