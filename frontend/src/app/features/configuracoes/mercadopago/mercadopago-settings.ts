import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';

import { toApiError } from '../../../core/http/api-error';
import { MercadoPagoStatus } from '../../financeiro/financeiro.models';
import { FinanceiroService } from '../../financeiro/financeiro.service';

/** Conecta a conta do Mercado Pago do escritório (o dinheiro das cobranças cai direto nela). */
@Component({
  selector: 'app-mercadopago-settings',
  imports: [
    ReactiveFormsModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressBarModule,
  ],
  template: `
    <header class="page-header">
      <div>
        <h1>Mercado Pago</h1>
        <p>A conta do escritório que recebe os Pix e links de pagamento dos honorários.</p>
      </div>
    </header>

    @if (error(); as message) {
      <p class="error-text" role="alert">{{ message }}</p>
    }
    @if (loading()) {
      <mat-progress-bar mode="indeterminate" />
    }

    @if (status(); as s) {
      <section class="form-card">
        @if (s.connected) {
          <div class="mp__state">
            <span class="mp__icon"><span class="icon icon--filled">check_circle</span></span>
            <div>
              <h2>Conectado</h2>
              <p class="muted">Conta {{ s.nickname || s.mp_user_id }}</p>
            </div>
            <span class="mp__spacer"></span>
            @if (s.can_manage) {
              <button mat-stroked-button type="button" [disabled]="busy()" (click)="disconnect()">
                Desconectar
              </button>
            }
          </div>
          <p class="muted small mp__note">
            @if (s.webhook_ready) {
              Quando o cliente paga, a parcela recebe baixa sozinha.
            } @else {
              Aviso automático de pagamento indisponível neste ambiente (sem HTTPS). Em produção a
              baixa é automática.
            }
          </p>
        } @else if (s.can_manage) {
          <h2>Conectar a conta do escritório</h2>
          <ol class="plain-list">
            <li>
              Entre em
              <a href="https://www.mercadopago.com.br/developers/panel/app" target="_blank"
                >mercadopago.com.br/developers</a
              >
              com a conta do escritório e crie uma aplicação.
            </li>
            <li>
              Em <strong>Credenciais de produção</strong>, copie o
              <strong>Access Token</strong> (começa com APP_USR-).
            </li>
            <li>
              Cole abaixo. Ele fica guardado cifrado e só serve para criar e consultar cobranças.
            </li>
          </ol>
          <div class="inline-form">
            <mat-form-field appearance="outline" class="grow" subscriptSizing="dynamic">
              <mat-label>Access Token</mat-label>
              <input matInput type="password" autocomplete="off" [formControl]="token" />
            </mat-form-field>
            <button mat-flat-button type="button" [disabled]="busy()" (click)="connect()">
              Conectar
            </button>
          </div>
        } @else {
          <div class="empty-state">
            <span class="icon">account_balance</span>
            O titular do escritório precisa conectar a conta do Mercado Pago.
          </div>
        }
      </section>
    }
  `,
  styles: `
    .mp__state {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 16px;
    }
    .mp__state h2 {
      margin: 0 0 2px;
    }
    .mp__state p {
      margin: 0;
    }
    .mp__icon {
      display: grid;
      place-items: center;
      width: 44px;
      height: 44px;
      border-radius: 12px;
      background: var(--tm-success-soft);
      color: var(--tm-success);
    }
    .mp__spacer {
      flex: 1;
    }
    .mp__note {
      margin: 12px 0 0;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MercadoPagoSettings {
  private readonly api = inject(FinanceiroService);

  readonly status = signal<MercadoPagoStatus | null>(null);
  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly token = new FormControl('', { nonNullable: true, validators: Validators.required });

  constructor() {
    this.api.mercadoPago().subscribe({
      next: (s) => {
        this.loading.set(false);
        this.status.set(s);
      },
      error: (err: unknown) => {
        this.loading.set(false);
        this.error.set(toApiError(err).message);
      },
    });
  }

  connect(): void {
    const token = this.token.value.trim();
    if (!token) {
      this.token.markAsTouched();
      return;
    }
    this.busy.set(true);
    this.error.set(null);
    this.api.connectMercadoPago(token).subscribe({
      next: (s) => {
        this.busy.set(false);
        this.token.reset('');
        this.status.set(s);
      },
      error: (err: unknown) => {
        this.busy.set(false);
        this.error.set(toApiError(err).message);
      },
    });
  }

  disconnect(): void {
    this.busy.set(true);
    this.api.disconnectMercadoPago().subscribe({
      next: (s) => {
        this.busy.set(false);
        this.status.set(s);
      },
      error: (err: unknown) => {
        this.busy.set(false);
        this.error.set(toApiError(err).message);
      },
    });
  }
}
