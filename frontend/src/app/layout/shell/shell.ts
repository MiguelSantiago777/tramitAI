import { NgTemplateOutlet } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatPaginatorIntl } from '@angular/material/paginator';
import { MatTooltipModule } from '@angular/material/tooltip';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter, interval, startWith } from 'rxjs';

import { ROLE_LABELS } from '../../core/auth/auth.models';
import { AuthService } from '../../core/auth/auth.service';
import { PtBrPaginatorIntl } from '../../core/i18n/paginator-intl';
import { PendingDraftsCounter } from '../../features/aprovacoes/pending-counter';
import { initialsOf } from '../../shared/initials';

interface NavLink {
  path: string;
  label: string;
  icon: string;
}

@Component({
  selector: 'app-shell',
  imports: [
    NgTemplateOutlet,
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    MatButtonModule,
    MatTooltipModule,
  ],
  // Aqui (e não no app.config) para o paginador não entrar no bundle inicial.
  providers: [{ provide: MatPaginatorIntl, useClass: PtBrPaginatorIntl }],
  templateUrl: './shell.html',
  styleUrl: './shell.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Shell {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly counter = inject(PendingDraftsCounter);

  readonly main: NavLink[] = [
    { path: '/', label: 'Início', icon: 'space_dashboard' },
    { path: '/inbox', label: 'Conversas', icon: 'forum' },
    { path: '/aprovacoes', label: 'Aprovações', icon: 'mark_chat_read' },
    { path: '/tarefas', label: 'Tarefas e prazos', icon: 'task_alt' },
    { path: '/agenda', label: 'Agenda', icon: 'calendar_month' },
  ];
  readonly records: NavLink[] = [
    { path: '/clientes', label: 'Clientes', icon: 'group' },
    { path: '/processos', label: 'Processos', icon: 'gavel' },
  ];
  readonly settings: NavLink[] = [
    { path: '/configuracoes/whatsapp', label: 'WhatsApp', icon: 'smartphone' },
    { path: '/configuracoes/equipe', label: 'Equipe', icon: 'badge' },
    { path: '/configuracoes/escritorio', label: 'Configurações', icon: 'settings' },
    { path: '/configuracoes/termo', label: 'Termo de IA', icon: 'verified_user' },
  ];

  readonly session = this.auth.session;
  readonly pending = this.counter.count;
  /** Menu lateral aberto no celular. */
  readonly menuOpen = signal(false);

  readonly roleLabel = computed(() => {
    const role = this.session()?.role;
    return role ? ROLE_LABELS[role] : '';
  });
  readonly userName = computed(() => {
    const user = this.session()?.user;
    return user?.full_name || user?.email || '';
  });
  readonly initials = computed(() => initialsOf(this.userName()));

  constructor() {
    interval(30_000)
      .pipe(startWith(0), takeUntilDestroyed())
      .subscribe(() => this.counter.refresh());
    this.router.events
      .pipe(
        filter((e) => e instanceof NavigationEnd),
        takeUntilDestroyed(),
      )
      .subscribe(() => this.menuOpen.set(false));
  }

  logout(): void {
    this.auth.logout();
    void this.router.navigate(['/login']);
  }
}
