import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { ActivatedRoute } from '@angular/router';

import { AuthService } from '../../core/auth/auth.service';
import { toApiError } from '../../core/http/api-error';
import { money } from '../financeiro/financeiro.models';
import { Billing, BillingService } from './billing.service';

@Component({
  selector: 'app-billing-page',
  imports: [
    DatePipe,
    ReactiveFormsModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressBarModule,
  ],
  template: `
    <h1 class="page-title">Assinatura</h1>
    @if (loading()) {
      <mat-progress-bar mode="indeterminate" />
    }
    @if (billing(); as b) {
      <section class="card">
        @if (b.exempt) {
          <p>Este escritório está isento de assinatura. Nada a fazer aqui.</p>
        } @else {
          <div class="head">
            <div>
              <span class="muted small">Plano</span>
              <strong class="plan">{{ b.plan_name }} · {{ price(b) }}/mês</strong>
            </div>
            <span class="pill" [attr.data-tone]="tone(b)">{{ b.status_label }}</span>
          </div>

          @if (b.blocked) {
            <p class="alert" role="alert">
              O acesso está bloqueado porque
              {{
                b.status === 'TRIAL'
                  ? 'o teste grátis'
                  : 'a
              assinatura'
              }}
              venceu. Assine abaixo para voltar a usar: seus dados continuam guardados.
            </p>
          } @else if (b.status === 'TRIAL') {
            <p>
              Teste grátis até <strong>{{ b.trial_ends_at | date: 'dd/MM/yyyy' }}</strong> ({{
                b.days_left
              }}
              dia(s)). Assine quando quiser: o primeiro pagamento só libera o mês seguinte depois do
              teste.
            </p>
          } @else if (b.status === 'ACTIVE') {
            <p>
              Assinatura ativa. Próxima cobrança em
              <strong>{{ b.paid_until | date: 'dd/MM/yyyy' }}</strong>, pelo Mercado Pago.
            </p>
          } @else if (b.status === 'PENDING') {
            <p>Assinatura criada, aguardando a confirmação do pagamento no Mercado Pago.</p>
          } @else if (b.status === 'PAST_DUE') {
            <p class="alert">
              O Mercado Pago não conseguiu cobrar. Atualize o cartão no Mercado Pago para evitar o
              bloqueio em {{ b.access_until | date: 'dd/MM/yyyy' }}.
            </p>
          } @else if (b.status === 'CANCELLED') {
            <p>Assinatura cancelada. O acesso vai até {{ b.access_until | date: 'dd/MM/yyyy' }}.</p>
          }

          @if (b.can_manage) {
            @if (b.status !== 'ACTIVE') {
              <div class="checkout">
                <mat-form-field appearance="outline" class="email">
                  <mat-label>E-mail da sua conta no Mercado Pago</mat-label>
                  <input matInput type="email" [formControl]="email" />
                  <mat-hint>O pagamento é feito com a conta do Mercado Pago deste e-mail.</mat-hint>
                </mat-form-field>
                <button mat-flat-button type="button" [disabled]="busy()" (click)="subscribe()">
                  <span class="icon btn-icon">credit_card</span>Assinar pelo Mercado Pago
                </button>
              </div>
              @if (b.checkout_url) {
                <p class="small">
                  Já começou?
                  <a [href]="b.checkout_url" target="_self">Continuar o pagamento</a>
                  ·
                  <button type="button" class="linkish" (click)="check()">
                    Já paguei, conferir
                  </button>
                </p>
              }
            } @else {
              <button
                mat-button
                type="button"
                class="danger"
                [disabled]="busy()"
                (click)="cancel()"
              >
                Cancelar assinatura
              </button>
            }
          } @else {
            <p class="muted">Só o titular do escritório pode assinar ou cancelar.</p>
          }
        }
        @if (error(); as message) {
          <p class="error-text" role="alert">{{ message }}</p>
        }
      </section>
    }
    <p class="muted small">
      <button type="button" class="linkish" (click)="logout()">Sair</button>
    </p>
  `,
  styles: `
    .head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 12px;
    }
    .head > div {
      display: grid;
    }
    .plan {
      font-size: 1.15rem;
    }
    .pill {
      padding: 2px 10px;
      border-radius: 999px;
      background: var(--tm-neutral-soft);
      font-size: 0.85rem;
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
    .alert {
      padding: 10px 14px;
      border-radius: 10px;
      background: var(--tm-danger-soft);
      color: var(--tm-danger);
    }
    .checkout {
      display: flex;
      gap: 12px;
      align-items: flex-start;
      flex-wrap: wrap;
      margin-top: 8px;
    }
    .email {
      flex: 1;
      min-width: 260px;
    }
    .linkish {
      background: none;
      border: 0;
      padding: 0;
      color: var(--mat-sys-primary);
      cursor: pointer;
      font: inherit;
    }
    .danger {
      color: var(--tm-danger);
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BillingPage {
  private readonly api = inject(BillingService);
  private readonly auth = inject(AuthService);

  readonly billing = signal<Billing | null>(null);
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

  tone(b: Billing): string {
    if (b.blocked || b.status === 'PAST_DUE') return 'danger';
    if (b.status === 'ACTIVE') return 'success';
    return 'info';
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
