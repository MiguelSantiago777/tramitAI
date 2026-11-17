import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { RouterLink } from '@angular/router';

import { AuthService } from '../../core/auth/auth.service';
import { toApiError } from '../../core/http/api-error';
import { Dashboard, TenantService } from '../../core/tenant/tenant.service';
import { NOTIFICATION_LABELS } from '../processos/case.models';
import { Draft, ORIGIN_LABELS } from '../aprovacoes/draft.models';
import { DraftsService } from '../aprovacoes/drafts.service';

interface Stat {
  label: string;
  value: number;
  hint: string;
  icon: string;
  link: string;
  tone: 'indigo' | 'amber' | 'teal' | 'slate';
}

@Component({
  selector: 'app-home',
  imports: [DatePipe, RouterLink, MatButtonModule],
  templateUrl: './home.html',
  styleUrl: './home.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Home {
  private readonly tenant = inject(TenantService);
  private readonly draftsApi = inject(DraftsService);
  readonly session = inject(AuthService).session;

  readonly data = signal<Dashboard | null>(null);
  readonly queue = signal<Draft[]>([]);
  readonly error = signal<string | null>(null);
  readonly today = new Date();

  readonly firstName = computed(() => {
    const user = this.session()?.user;
    const name = user?.full_name || user?.email?.split('@')[0] || '';
    return name.split(' ')[0];
  });
  readonly greeting = computed(() => {
    const hour = this.today.getHours();
    return hour < 12 ? 'Bom dia' : hour < 18 ? 'Boa tarde' : 'Boa noite';
  });

  readonly stats = computed<Stat[]>(() => {
    const d = this.data();
    if (!d) {
      return [];
    }
    return [
      {
        label: 'Aguardando aprovação',
        value: d.pending_drafts,
        hint: d.urgent_drafts > 0 ? `${d.urgent_drafts} urgente(s)` : 'Nenhuma urgente',
        icon: 'task_alt',
        link: '/aprovacoes',
        tone: 'amber',
      },
      {
        label: 'Conversas não lidas',
        value: d.unread_conversations,
        hint: `${d.open_conversations} conversa(s) aberta(s)`,
        icon: 'forum',
        link: '/inbox',
        tone: 'indigo',
      },
      {
        label: 'Processos com novidade',
        value: d.cases_with_news,
        hint: `${d.active_cases} processo(s) monitorado(s)`,
        icon: 'gavel',
        link: '/processos',
        tone: 'teal',
      },
      {
        label: 'Clientes ativos',
        value: d.active_clients,
        hint: d.leads > 0 ? `+ ${d.leads} lead(s) novo(s)` : 'Nenhum lead novo',
        icon: 'group',
        link: '/clientes',
        tone: 'slate',
      },
    ];
  });

  constructor() {
    this.tenant.dashboard().subscribe({
      next: (d) => this.data.set(d),
      error: (err: unknown) => this.error.set(toApiError(err).message),
    });
    this.draftsApi.list({ status: 'DRAFT' }, 0, 5).subscribe({
      next: (page) => this.queue.set(page.results),
      error: () => this.queue.set([]),
    });
  }

  originLabel(d: Draft): string {
    return ORIGIN_LABELS[d.origin];
  }

  who(d: Draft): string {
    return d.client_name || d.contact_name || d.phone;
  }

  notificationLabel(value: keyof typeof NOTIFICATION_LABELS): string {
    return NOTIFICATION_LABELS[value];
  }
}
