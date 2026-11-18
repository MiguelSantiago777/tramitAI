import { DatePipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatSnackBar } from '@angular/material/snack-bar';
import { ActivatedRoute, Router } from '@angular/router';

import { toApiError } from '../../core/http/api-error';

export interface GoogleStatus {
  configured: boolean;
  connected: boolean;
  google_email: string;
  needs_reconnect: boolean;
  busy_synced_at: string | null;
}

const URL = '/api/v1/agenda/google/';
const RESULT_MESSAGES: Record<string, string> = {
  conectado: 'Google Agenda conectado.',
  cancelado: 'Conexão com o Google cancelada.',
  expirado: 'O link de conexão expirou. Tente de novo.',
  erro: 'O Google não confirmou a conexão. Tente de novo.',
};

/** Google Agenda da pessoa logada: o que é marcado aqui vai pra lá, e a Lia respeita o ocupado. */
@Component({
  selector: 'app-google-calendar-card',
  imports: [DatePipe, MatButtonModule],
  template: `
    @if (status(); as s) {
      @if (s.configured) {
        <section class="card panel-card google" [class.google--warn]="s.needs_reconnect">
          <span class="google__icon"><span class="icon">calendar_month</span></span>
          <div class="google__text">
            @if (!s.connected) {
              <strong>Conecte seu Google Agenda</strong>
              <span class="muted small">
                O que for marcado aqui aparece no seu Google, e a Lia não oferece horário em que
                você já tem compromisso por lá.
              </span>
            } @else if (s.needs_reconnect) {
              <strong>Reconecte o Google Agenda</strong>
              <span class="muted small">
                A autorização do Google ({{ s.google_email }}) expirou. Enquanto isso, nada é
                enviado para lá.
              </span>
            } @else {
              <strong>Google Agenda conectado</strong>
              <span class="muted small">
                {{ s.google_email }}
                @if (s.busy_synced_at) {
                  · ocupado atualizado às {{ s.busy_synced_at | date: 'HH:mm' }}
                }
              </span>
            }
          </div>
          @if (!s.connected || s.needs_reconnect) {
            <button mat-flat-button type="button" [disabled]="busy()" (click)="connect()">
              {{ s.connected ? 'Reconectar' : 'Conectar' }}
            </button>
          }
          @if (s.connected) {
            <button mat-button type="button" [disabled]="busy()" (click)="disconnect()">
              Desconectar
            </button>
          }
        </section>
      }
    }
  `,
  styles: `
    .google {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 12px 16px;
    }
    .google--warn {
      border-color: var(--tm-warning);
      background: var(--tm-warning-soft);
    }
    .google__icon {
      display: grid;
      place-items: center;
      width: 40px;
      height: 40px;
      border-radius: 12px;
      background: var(--tm-info-soft);
      color: var(--tm-info);
    }
    .google__text {
      display: flex;
      flex-direction: column;
      gap: 2px;
      flex: 1 1 280px;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class GoogleCalendarCard {
  private readonly http = inject(HttpClient);
  private readonly snack = inject(MatSnackBar);
  private readonly router = inject(Router);

  readonly status = signal<GoogleStatus | null>(null);
  readonly busy = signal(false);

  constructor() {
    // Volta do Google: /agenda?google=conectado|cancelado|expirado|erro
    const result = inject(ActivatedRoute).snapshot.queryParamMap.get('google');
    if (result && RESULT_MESSAGES[result]) {
      this.snack.open(RESULT_MESSAGES[result], 'OK', { duration: 5000 });
      void this.router.navigate([], { queryParams: { google: null }, replaceUrl: true });
    }
    this.http.get<GoogleStatus>(URL).subscribe({
      next: (s) => this.status.set(s),
      error: () => this.status.set(null),
    });
  }

  connect(): void {
    this.busy.set(true);
    this.http.post<{ authorization_url: string }>(URL, {}).subscribe({
      next: ({ authorization_url }) => window.location.assign(authorization_url),
      error: (err: unknown) => {
        this.busy.set(false);
        this.snack.open(toApiError(err).message, 'OK', { duration: 6000 });
      },
    });
  }

  disconnect(): void {
    this.busy.set(true);
    this.http.delete<GoogleStatus>(URL).subscribe({
      next: (s) => {
        this.busy.set(false);
        this.status.set(s);
      },
      error: (err: unknown) => {
        this.busy.set(false);
        this.snack.open(toApiError(err).message, 'OK', { duration: 6000 });
      },
    });
  }
}
