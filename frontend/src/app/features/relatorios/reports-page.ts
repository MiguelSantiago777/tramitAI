import { DatePipe, DecimalPipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';

import { toApiError } from '../../core/http/api-error';
import { money } from '../financeiro/financeiro.models';

export interface Overview {
  start: string;
  end: string;
  clients: Record<string, number>;
  funnel: {
    created: number;
    won: number;
    lost: number;
    conversion: number;
    won_value: string;
    open_now: number;
    by_source: Record<string, number>;
    lost_reasons: Record<string, number>;
  };
  whatsapp: Record<string, number>;
  ai: {
    drafts: number;
    ai_drafts: number;
    approved: number;
    rejected: number;
    pending_now: number;
    ai_unedited_pct: number;
  };
  cases: Record<string, number>;
  tasks: Record<string, number>;
  finance: Record<string, string | number>;
  finance_months: { month: string; received: string; expected: string }[];
}

type Period = 'month' | 'last_month' | '90d' | 'custom';

const SOURCE_LABELS: Record<string, string> = {
  WHATSAPP: 'WhatsApp',
  INDICACAO: 'Indicação',
  REDES: 'Redes sociais',
  SITE: 'Site / Google',
  PRESENCIAL: 'Presencial',
  OUTRA: 'Outra',
};

function iso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(
    d.getDate(),
  ).padStart(2, '0')}`;
}

export function periodRange(period: Period, today = new Date()): { start: string; end: string } {
  const y = today.getFullYear();
  const m = today.getMonth();
  if (period === 'last_month') {
    return { start: iso(new Date(y, m - 1, 1)), end: iso(new Date(y, m, 0)) };
  }
  if (period === '90d') {
    const start = new Date(today);
    start.setDate(start.getDate() - 89);
    return { start: iso(start), end: iso(today) };
  }
  return { start: iso(new Date(y, m, 1)), end: iso(today) };
}

@Component({
  selector: 'app-reports-page',
  imports: [
    DatePipe,
    DecimalPipe,
    ReactiveFormsModule,
    MatButtonModule,
    MatButtonToggleModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressBarModule,
  ],
  template: `
    <header class="head">
      <h1 class="page-title">Relatórios</h1>
      <span class="spacer"></span>
      <mat-button-toggle-group [value]="period()" (change)="setPeriod($event.value)">
        <mat-button-toggle value="month">Este mês</mat-button-toggle>
        <mat-button-toggle value="last_month">Mês passado</mat-button-toggle>
        <mat-button-toggle value="90d">90 dias</mat-button-toggle>
        <mat-button-toggle value="custom">Período</mat-button-toggle>
      </mat-button-toggle-group>
    </header>
    @if (period() === 'custom') {
      <div class="custom">
        <mat-form-field appearance="outline" subscriptSizing="dynamic">
          <mat-label>De</mat-label>
          <input matInput type="date" [formControl]="start" />
        </mat-form-field>
        <mat-form-field appearance="outline" subscriptSizing="dynamic">
          <mat-label>Até</mat-label>
          <input matInput type="date" [formControl]="end" />
        </mat-form-field>
        <button mat-flat-button type="button" (click)="load()">Ver</button>
      </div>
    }
    @if (loading()) {
      <mat-progress-bar mode="indeterminate" />
    }
    @if (error(); as message) {
      <p class="error-text" role="alert">{{ message }}</p>
    }

    @if (data(); as d) {
      <p class="muted small">
        {{ d.start | date: 'dd/MM/yyyy' }} a {{ d.end | date: 'dd/MM/yyyy' }}
      </p>
      <section class="grid">
        <article class="card block">
          <h2><span class="icon">view_kanban</span> Novos clientes</h2>
          <dl>
            <dt>Contatos novos no funil</dt>
            <dd>{{ d.funnel.created }}</dd>
            <dt>Contrataram</dt>
            <dd class="good">{{ d.funnel.won }}</dd>
            <dt>Não contrataram</dt>
            <dd>{{ d.funnel.lost }}</dd>
            <dt>Conversão</dt>
            <dd>{{ d.funnel.conversion | number: '1.0-1' }}%</dd>
            <dt>Valor fechado (estimado)</dt>
            <dd>{{ fmt(d.funnel.won_value) }}</dd>
            <dt>Em negociação agora</dt>
            <dd>{{ d.funnel.open_now }}</dd>
          </dl>
          @if (sources().length) {
            <h3>De onde vieram</h3>
            @for (s of sources(); track s.label) {
              <div class="bar">
                <span>{{ s.label }}</span>
                <span class="bar__track"
                  ><span class="bar__fill" [style.width.%]="s.pct"></span
                ></span>
                <strong>{{ s.value }}</strong>
              </div>
            }
          }
        </article>

        <article class="card block">
          <h2><span class="icon">forum</span> WhatsApp e Lia</h2>
          <dl>
            <dt>Mensagens recebidas</dt>
            <dd>{{ d.whatsapp['inbound'] }}</dd>
            <dt>Mensagens enviadas</dt>
            <dd>{{ d.whatsapp['outbound'] }}</dd>
            <dt>Conversas com movimento</dt>
            <dd>{{ d.whatsapp['conversations'] }}</dd>
            <dt>Rascunhos da Lia</dt>
            <dd>{{ d.ai.ai_drafts }}</dd>
            <dt>Aprovados / rejeitados</dt>
            <dd>{{ d.ai.approved }} / {{ d.ai.rejected }}</dd>
            <dt>Texto da Lia enviado sem edição</dt>
            <dd>{{ d.ai.ai_unedited_pct | number: '1.0-1' }}%</dd>
            <dt>Aguardando aprovação agora</dt>
            <dd [class.warn]="d.ai.pending_now > 0">{{ d.ai.pending_now }}</dd>
          </dl>
        </article>

        <article class="card block">
          <h2><span class="icon">gavel</span> Processos e tarefas</h2>
          <dl>
            <dt>Processos ativos</dt>
            <dd>{{ d.cases['active'] }}</dd>
            <dt>Processos novos</dt>
            <dd>{{ d.cases['new'] }}</dd>
            <dt>Andamentos no período</dt>
            <dd>{{ d.cases['movements'] }}</dd>
            <dt>Clientes avisados de andamento</dt>
            <dd>{{ d.cases['notified'] }}</dd>
            <dt>Tarefas concluídas</dt>
            <dd class="good">{{ d.tasks['done'] }}</dd>
            <dt>Tarefas atrasadas agora</dt>
            <dd [class.warn]="d.tasks['overdue_now'] > 0">{{ d.tasks['overdue_now'] }}</dd>
            <dt>Clientes novos / leads</dt>
            <dd>{{ d.clients['new_clients'] }} / {{ d.clients['new_leads'] }}</dd>
          </dl>
        </article>

        <article class="card block">
          <h2><span class="icon">payments</span> Financeiro</h2>
          <dl>
            <dt>Recebido no período</dt>
            <dd class="good">{{ fmt(d.finance['received']) }}</dd>
            <dt>Parcelas pagas (pelo Mercado Pago)</dt>
            <dd>{{ d.finance['received_count'] }} ({{ d.finance['via_mercadopago'] }})</dd>
            <dt>Em atraso agora</dt>
            <dd class="bad">{{ fmt(d.finance['overdue_now']) }}</dd>
            <dt>Total em aberto</dt>
            <dd>{{ fmt(d.finance['open_now']) }}</dd>
          </dl>
          <h3>Recebido x previsto (6 meses)</h3>
          <div class="chart" role="img" aria-label="Recebido e previsto por mês">
            @for (p of months(); track p.month) {
              <div class="chart__col">
                <div class="chart__bars">
                  <span
                    class="chart__bar chart__bar--expected"
                    [style.height.%]="p.expectedPct"
                    [attr.title]="'Previsto ' + fmt(p.expected)"
                  ></span>
                  <span
                    class="chart__bar chart__bar--received"
                    [style.height.%]="p.receivedPct"
                    [attr.title]="'Recebido ' + fmt(p.received)"
                  ></span>
                </div>
                <span class="chart__label">{{ p.month | date: 'MMM' }}</span>
              </div>
            }
          </div>
          <p class="legend small">
            <span class="dot dot--received"></span> Recebido
            <span class="dot dot--expected"></span> Previsto
          </p>
        </article>
      </section>
    }
  `,
  styles: `
    .head {
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
    }
    .spacer {
      flex: 1;
    }
    .custom {
      display: flex;
      gap: 12px;
      align-items: center;
      margin: 12px 0;
      flex-wrap: wrap;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 16px;
    }
    .block h2 {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 1.05rem;
      margin: 0 0 12px;
    }
    .block h3 {
      font-size: 0.9rem;
      margin: 16px 0 8px;
    }
    dl {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 6px 12px;
      margin: 0;
    }
    dt {
      color: var(--mat-sys-on-surface-variant);
    }
    dd {
      margin: 0;
      font-weight: 600;
      text-align: right;
    }
    .good {
      color: var(--tm-success);
    }
    .bad {
      color: var(--tm-danger);
    }
    .warn {
      color: var(--tm-warning);
    }
    .bar {
      display: grid;
      grid-template-columns: 110px 1fr 32px;
      gap: 8px;
      align-items: center;
      font-size: 0.85rem;
      margin-bottom: 4px;
    }
    .bar__track {
      height: 8px;
      border-radius: 4px;
      background: var(--mat-sys-surface-container);
      overflow: hidden;
    }
    .bar__fill {
      display: block;
      height: 100%;
      background: var(--mat-sys-primary);
    }
    .chart {
      display: grid;
      grid-template-columns: repeat(6, 1fr);
      gap: 8px;
      height: 140px;
      align-items: end;
    }
    .chart__col {
      display: grid;
      grid-template-rows: 1fr auto;
      height: 100%;
    }
    .chart__bars {
      display: flex;
      align-items: flex-end;
      justify-content: center;
      gap: 3px;
    }
    .chart__bar {
      width: 12px;
      border-radius: 3px 3px 0 0;
      min-height: 2px;
    }
    .chart__bar--expected {
      background: var(--mat-sys-outline-variant);
    }
    .chart__bar--received {
      background: var(--tm-success);
    }
    .chart__label {
      text-align: center;
      font-size: 0.75rem;
      color: var(--mat-sys-on-surface-variant);
    }
    .legend {
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .dot {
      width: 10px;
      height: 10px;
      border-radius: 2px;
      display: inline-block;
    }
    .dot--received {
      background: var(--tm-success);
    }
    .dot--expected {
      background: var(--mat-sys-outline-variant);
      margin-left: 10px;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ReportsPage {
  private readonly http = inject(HttpClient);

  readonly period = signal<Period>('month');
  readonly data = signal<Overview | null>(null);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly start = new FormControl(periodRange('month').start, { nonNullable: true });
  readonly end = new FormControl(periodRange('month').end, { nonNullable: true });

  readonly sources = computed(() => {
    const bySource = this.data()?.funnel.by_source ?? {};
    const total = Object.values(bySource).reduce((a, b) => a + b, 0);
    return Object.entries(bySource)
      .sort((a, b) => b[1] - a[1])
      .map(([key, value]) => ({
        label: SOURCE_LABELS[key] ?? key,
        value,
        pct: total ? Math.round((100 * value) / total) : 0,
      }));
  });

  readonly months = computed(() => {
    const points = this.data()?.finance_months ?? [];
    const max = Math.max(1, ...points.flatMap((p) => [Number(p.received), Number(p.expected)]));
    return points.map((p) => ({
      ...p,
      // Dia 15 evita o mês "voltar" por fuso ao formatar.
      month: p.month.slice(0, 8) + '15',
      receivedPct: (100 * Number(p.received)) / max,
      expectedPct: (100 * Number(p.expected)) / max,
    }));
  });

  constructor() {
    this.load();
  }

  fmt(value: string | number | undefined): string {
    return money(value ?? 0);
  }

  setPeriod(period: Period): void {
    this.period.set(period);
    if (period !== 'custom') {
      const range = periodRange(period);
      this.start.setValue(range.start);
      this.end.setValue(range.end);
      this.load();
    }
  }

  load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.http
      .get<Overview>('/api/v1/reports/overview/', {
        params: { start: this.start.value, end: this.end.value },
      })
      .subscribe({
        next: (d) => {
          this.loading.set(false);
          this.data.set(d);
        },
        error: (err: unknown) => {
          this.loading.set(false);
          this.error.set(toApiError(err).message);
        },
      });
  }
}
