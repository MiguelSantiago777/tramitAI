import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  Injectable,
  computed,
  inject,
  signal,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { Observable } from 'rxjs';

import { toApiError } from '../../../core/http/api-error';
import { formatPhone } from '../../../shared/br';

export type ConnectionStatus =
  'not_configured' | 'qr' | 'connecting' | 'connected' | 'disconnected' | 'bridge_down';

export interface WhatsAppConnection {
  provider: 'CLOUD_API' | 'BAILEYS' | null;
  status: ConnectionStatus;
  phone: string;
  qr: string | null;
  can_manage: boolean;
}

const URL = '/api/v1/whatsapp/connection/';

@Injectable({ providedIn: 'root' })
export class WhatsAppConnectionService {
  private readonly http = inject(HttpClient);

  get(): Observable<WhatsAppConnection> {
    return this.http.get<WhatsAppConnection>(URL);
  }

  connect(): Observable<WhatsAppConnection> {
    return this.http.post<WhatsAppConnection>(URL, {});
  }

  disconnect(): Observable<WhatsAppConnection> {
    return this.http.delete<WhatsAppConnection>(URL);
  }
}

const POLL_MS = 3000;

/** Parear o WhatsApp do escritório lendo o QR Code (WhatsApp Web via ponte). */
@Component({
  selector: 'app-whatsapp-connection',
  imports: [MatButtonModule, MatProgressSpinnerModule],
  templateUrl: './whatsapp-connection.html',
  styleUrl: './whatsapp-connection.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WhatsAppConnectionPage {
  private readonly api = inject(WhatsAppConnectionService);

  readonly state = signal<WhatsAppConnection | null>(null);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly confirmDisconnect = signal(false);
  private timer: ReturnType<typeof setTimeout> | null = null;

  readonly status = computed(() => this.state()?.status ?? null);
  readonly phone = computed(() => {
    const phone = this.state()?.phone;
    return phone ? formatPhone(phone) : '';
  });
  readonly canManage = computed(() => this.state()?.can_manage ?? false);

  constructor() {
    inject(DestroyRef).onDestroy(() => this.stopPolling());
    this.refresh();
  }

  connect(): void {
    this.run(this.api.connect());
  }

  disconnect(): void {
    this.confirmDisconnect.set(false);
    this.run(this.api.disconnect());
  }

  refresh(): void {
    this.api.get().subscribe({
      next: (state) => this.apply(state),
      error: (err: unknown) => this.error.set(toApiError(err).message),
    });
  }

  private run(request: Observable<WhatsAppConnection>): void {
    this.busy.set(true);
    this.error.set(null);
    request.subscribe({
      next: (state) => {
        this.busy.set(false);
        this.apply(state);
      },
      error: (err: unknown) => {
        this.busy.set(false);
        this.error.set(toApiError(err).message);
      },
    });
  }

  private apply(state: WhatsAppConnection): void {
    this.state.set(state);
    this.stopPolling();
    // Enquanto espera a leitura do QR (ou a reconexão), confere de novo sozinho.
    if (state.status === 'qr' || state.status === 'connecting') {
      this.timer = setTimeout(() => this.refresh(), POLL_MS);
    }
  }

  private stopPolling(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }
}
