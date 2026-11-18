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
    <h1 class="page-title">Mercado Pago</h1>
    <p class="muted">
      Conecte a conta do escritório para gerar Pix e links de pagamento das parcelas. O dinheiro cai
      direto na sua conta; quando o cliente paga, a parcela recebe baixa sozinha.
    </p>

    <section class="card">
      @if (loading()) {
        <mat-progress-bar mode="indeterminate" />
      }
      @if (status(); as s) {
        @if (s.connected) {
          <p class="ok">
            <span class="icon">check_circle</span> Conectado à conta
            <strong>{{ s.nickname || s.mp_user_id }}</strong>.
          </p>
          @if (!s.webhook_ready) {
            <p class="muted small">
              Aviso automático de pagamento indisponível neste ambiente (sem HTTPS). Em produção, a
              baixa é automática.
            </p>
          }
          @if (s.can_manage) {
            <button mat-stroked-button type="button" [disabled]="busy()" (click)="disconnect()">
              Desconectar
            </button>
          }
        } @else if (s.can_manage) {
          <ol class="steps">
            <li>
              Entre em
              <a href="https://www.mercadopago.com.br/developers/panel/app" target="_blank"
                >mercadopago.com.br/developers</a
              >
              com a conta do escritório e crie uma aplicação (tipo "Pagamentos online").
            </li>
            <li>
              Em <strong>Credenciais de produção</strong>, copie o
              <strong>Access Token</strong> (começa com APP_USR-).
            </li>
            <li>
              Cole abaixo. Ele fica guardado cifrado e só é usado para criar e consultar cobranças.
            </li>
          </ol>
          <mat-form-field appearance="outline" class="full">
            <mat-label>Access Token</mat-label>
            <input matInput type="password" autocomplete="off" [formControl]="token" />
          </mat-form-field>
          <button mat-flat-button type="button" [disabled]="busy()" (click)="connect()">
            Conectar
          </button>
        } @else {
          <p>O titular do escritório precisa conectar a conta do Mercado Pago.</p>
        }
      }
      @if (error(); as message) {
        <p class="error-text" role="alert">{{ message }}</p>
      }
    </section>
  `,
  styles: `
    .ok {
      display: flex;
      align-items: center;
      gap: 6px;
      color: var(--tm-success);
    }
    .steps {
      padding-left: 20px;
      line-height: 1.6;
    }
    .full {
      width: 100%;
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
