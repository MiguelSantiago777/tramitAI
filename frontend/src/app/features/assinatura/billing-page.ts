import { DatePipe, DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSnackBar } from '@angular/material/snack-bar';
import { ActivatedRoute } from '@angular/router';

import { AuthService } from '../../core/auth/auth.service';
import { toApiError } from '../../core/http/api-error';
import { money } from '../financeiro/financeiro.models';
import { Billing, BillingService, Plan } from './billing.service';

@Component({
  selector: 'app-billing-page',
  imports: [
    DatePipe,
    DecimalPipe,
    ReactiveFormsModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressBarModule,
  ],
  template: `
    <header class="page-header">
      <div>
        <h1>Assinatura</h1>
        <p>Plano do TramitAI do seu escritório, pago pelo Mercado Pago.</p>
      </div>
    </header>

    @if (loading()) {
      <mat-progress-bar mode="indeterminate" />
    }
    @if (error(); as message) {
      <p class="error-text" role="alert">{{ message }}</p>
    }

    @if (billing(); as b) {
      <section class="form-card">
        @if (b.exempt) {
          <div class="empty-state">
            <span class="icon">workspace_premium</span>
            Este escritório está isento de assinatura. Nada a fazer aqui.
          </div>
        } @else {
          <div class="bill__head">
            <div>
              <span class="muted small">Plano</span>
              <h2>{{ b.plan_name }} · {{ price(b) }}/mês</h2>
            </div>
            <span class="badge" [attr.data-status]="badge(b)">{{ b.status_label }}</span>
          </div>

          @if (b.blocked) {
            <p class="bill__alert" role="alert">
              O acesso está bloqueado porque
              {{ b.status === 'TRIAL' ? 'o teste grátis' : 'a assinatura' }} venceu. Assine abaixo
              para voltar a usar: seus dados continuam guardados.
            </p>
          } @else if (b.status === 'TRIAL') {
            <p>
              Teste grátis até <strong>{{ b.trial_ends_at | date: 'dd/MM/yyyy' }}</strong> ({{
                b.days_left
              }}
              dia(s)).
            </p>
          } @else if (b.status === 'ACTIVE') {
            <p>
              Assinatura ativa. Próxima cobrança em
              <strong>{{ b.paid_until | date: 'dd/MM/yyyy' }}</strong>, pelo Mercado Pago.
            </p>
          } @else if (b.status === 'PENDING') {
            <p>Assinatura criada, aguardando a confirmação do pagamento no Mercado Pago.</p>
          } @else if (b.status === 'PAST_DUE') {
            <p class="bill__alert">
              O Mercado Pago não conseguiu cobrar. Atualize o cartão no Mercado Pago para evitar o
              bloqueio em {{ b.access_until | date: 'dd/MM/yyyy' }}.
            </p>
          } @else if (b.status === 'CANCELLED') {
            <p>Assinatura cancelada. O acesso vai até {{ b.access_until | date: 'dd/MM/yyyy' }}.</p>
          }

          <div class="usage">
            <div class="usage__item">
              <span class="small">
                Usuários: <strong>{{ b.users_used }}</strong>
                {{ b.users_limit !== null ? 'de ' + b.users_limit : '(sem limite)' }}
              </span>
              @if (b.users_limit !== null) {
                <mat-progress-bar mode="determinate" [value]="pct(b.users_used, b.users_limit)" />
              }
            </div>
            <div class="usage__item">
              <span class="small">
                Mensagens da Lia este mês: <strong>{{ b.ai_used }}</strong>
                {{ b.ai_limit !== null ? 'de ' + b.ai_limit : '(sem limite)' }}
              </span>
              @if (b.ai_limit !== null) {
                <mat-progress-bar
                  mode="determinate"
                  [value]="pct(b.ai_used, b.ai_limit)"
                  [class.usage__bar--full]="b.ai_used >= b.ai_limit"
                />
              }
            </div>
          </div>
          @if (b.ai_limit !== null && b.ai_used >= b.ai_limit) {
            <p class="bill__alert">
              A Lia atingiu o limite do plano neste mês. As mensagens continuam chegando em
              Conversas para a equipe responder; a Lia volta no dia 1º ou ao mudar de plano.
            </p>
          }

          @if (b.can_manage) {
            @if (b.status !== 'ACTIVE') {
              <div class="inline-form">
                <mat-form-field appearance="outline" class="grow">
                  <mat-label>E-mail da sua conta no Mercado Pago</mat-label>
                  <input matInput type="email" [formControl]="email" />
                  <mat-hint>O pagamento é feito com a conta do Mercado Pago deste e-mail.</mat-hint>
                </mat-form-field>
                <button mat-flat-button type="button" [disabled]="busy()" (click)="subscribe()">
                  <span class="icon btn-icon">credit_card</span>Assinar pelo Mercado Pago
                </button>
              </div>
              @if (b.checkout_url) {
                <div class="form-actions">
                  <a mat-button [href]="b.checkout_url">Continuar o pagamento</a>
                  <button mat-button type="button" [disabled]="busy()" (click)="check()">
                    Já paguei, conferir
                  </button>
                </div>
              }
            } @else {
              <div class="form-actions">
                <button
                  mat-button
                  type="button"
                  class="dialog-danger"
                  [disabled]="busy()"
                  (click)="cancel()"
                >
                  Cancelar assinatura
                </button>
              </div>
            }
          } @else {
            <p class="muted small">Só o titular do escritório pode assinar ou cancelar.</p>
          }
        }
      </section>

      @if (!b.exempt && plans().length > 1) {
        <section class="plans">
          @for (p of plans(); track p.code) {
            <article class="card plan" [class.plan--current]="p.code === b.plan_code">
              <header>
                <h3>{{ p.name }}</h3>
                @if (p.code === b.plan_code) {
                  <span class="badge" data-status="PAID">Seu plano</span>
                } @else if (p.code === 'escritorio') {
                  <span class="badge" data-status="OPEN">Mais escolhido</span>
                }
              </header>
              <p class="plan__price">{{ fmt(p.price) }}<span class="muted small">/mês</span></p>
              <ul class="plan__features small">
                <li>
                  {{
                    p.max_users !== null
                      ? 'Até ' + p.max_users + ' usuários'
                      : 'Usuários ilimitados'
                  }}
                </li>
                <li>
                  {{
                    p.monthly_ai_limit !== null
                      ? (p.monthly_ai_limit | number) + ' mensagens da Lia por mês'
                      : 'Lia sem limite'
                  }}
                </li>
                <li>{{ p.description }}</li>
              </ul>
              @if (b.can_manage && p.code !== b.plan_code) {
                <button
                  mat-stroked-button
                  type="button"
                  [disabled]="busy()"
                  (click)="changePlan(p)"
                >
                  Mudar para {{ p.name }}
                </button>
              }
            </article>
          }
        </section>
        @if (b.status === 'ACTIVE') {
          <p class="muted small">
            Ao mudar de plano, a próxima cobrança no Mercado Pago já vem com o valor novo.
          </p>
        }
      }
      @if (b.blocked) {
        <button mat-button type="button" (click)="logout()">
          <span class="icon btn-icon">logout</span>Sair
        </button>
      }
    }
  `,
  styles: `
    .bill__head {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
    }
    .bill__head h2 {
      margin: 2px 0 8px;
    }
    .usage {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
      margin: 8px 0 16px;
    }
    .usage__item {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .usage__bar--full {
      --mat-progress-bar-active-indicator-color: var(--tm-danger);
    }
    .plans {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-top: 16px;
    }
    .plan {
      display: flex;
      flex-direction: column;
      gap: 8px;
      padding: 20px;
    }
    .plan--current {
      outline: 2px solid var(--mat-sys-primary);
    }
    .plan header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
    }
    .plan h3 {
      margin: 0;
    }
    .plan__price {
      margin: 0;
      font-size: 24px;
      font-weight: 700;
    }
    .plan__features {
      flex: 1;
      margin: 0;
      padding-left: 18px;
      color: var(--mat-sys-on-surface-variant);
    }
    @media (max-width: 700px) {
      .usage {
        grid-template-columns: 1fr;
      }
    }
    .bill__alert {
      padding: 10px 14px;
      border-radius: var(--tm-radius-sm);
      background: var(--tm-danger-soft);
      color: var(--tm-danger);
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BillingPage {
  private readonly api = inject(BillingService);
  private readonly auth = inject(AuthService);

  private readonly snack = inject(MatSnackBar);

  readonly billing = signal<Billing | null>(null);
  readonly plans = signal<Plan[]>([]);
  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly email = new FormControl(this.auth.session()?.user.email ?? '', {
    nonNullable: true,
    validators: [Validators.required, Validators.email],
  });

  constructor() {
    // Voltando do checkout do Mercado Pago: confere na hora.
    const returning = inject(ActivatedRoute).snapshot.queryParamMap.has('retorno');
    this.api.plans().subscribe({ next: (p) => this.plans.set(p), error: () => undefined });
    const request = returning ? this.api.refresh() : this.api.load();
    request.subscribe({
      next: (b) => this.show(b),
      error: (err: unknown) => {
        this.loading.set(false);
        this.error.set(toApiError(err).message);
      },
    });
  }

  price(b: Billing): string {
    return money(b.price);
  }

  fmt(value: string): string {
    return money(value);
  }

  pct(used: number, limit: number): number {
    return limit ? Math.min(100, (100 * used) / limit) : 0;
  }

  changePlan(p: Plan): void {
    this.busy.set(true);
    this.error.set(null);
    this.api.changePlan(p.code).subscribe({
      next: (b) => {
        this.busy.set(false);
        this.show(b);
        this.snack.open(`Plano alterado para ${p.name}.`, undefined, { duration: 3000 });
      },
      error: (err: unknown) => {
        this.busy.set(false);
        this.error.set(toApiError(err).message);
      },
    });
  }

  /** Cor do .badge global. */
  badge(b: Billing): string {
    if (b.blocked || b.status === 'PAST_DUE') return 'OVERDUE';
    if (b.status === 'ACTIVE') return 'PAID';
    if (b.status === 'PENDING') return 'PENDING';
    return 'OPEN';
  }

  subscribe(): void {
    if (this.email.invalid) {
      this.email.markAsTouched();
      return;
    }
    this.busy.set(true);
    this.error.set(null);
    this.api.checkout(this.email.value.trim()).subscribe({
      next: ({ checkout_url }) => window.location.assign(checkout_url),
      error: (err: unknown) => {
        this.busy.set(false);
        this.error.set(toApiError(err).message);
      },
    });
  }

  check(): void {
    this.busy.set(true);
    this.api.refresh().subscribe({
      next: (b) => {
        this.busy.set(false);
        this.show(b);
      },
      error: (err: unknown) => {
        this.busy.set(false);
        this.error.set(toApiError(err).message);
      },
    });
  }

  cancel(): void {
    this.busy.set(true);
    this.api.cancel().subscribe({
      next: (b) => {
        this.busy.set(false);
        this.show(b);
      },
      error: (err: unknown) => {
        this.busy.set(false);
        this.error.set(toApiError(err).message);
      },
    });
  }

  logout(): void {
    this.auth.logout();
    window.location.assign('/login');
  }

  private show(b: Billing): void {
    this.loading.set(false);
    this.billing.set(b);
    if (b.payer_email) this.email.setValue(b.payer_email);
  }
}
