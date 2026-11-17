import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatToolbarModule } from '@angular/material/toolbar';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { ROLE_LABELS } from '../../core/auth/auth.models';
import { AuthService } from '../../core/auth/auth.service';

@Component({
  selector: 'app-shell',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, MatButtonModule, MatToolbarModule],
  template: `
    <mat-toolbar class="shell__bar">
      <a class="shell__brand" routerLink="/">TramitAI</a>
      <nav class="shell__nav" aria-label="Principal">
        @for (link of links; track link.path) {
          <a
            mat-button
            [routerLink]="link.path"
            routerLinkActive="shell__nav--active"
            [routerLinkActiveOptions]="{ exact: link.path === '/' }"
            >{{ link.label }}</a
          >
        }
      </nav>
      <span class="shell__spacer"></span>
      <span class="shell__user">
        {{ session()?.tenant?.name }} · {{ session()?.user?.email }} · {{ roleLabel() }}
      </span>
      <button mat-button type="button" (click)="logout()">Sair</button>
    </mat-toolbar>
    <main class="shell__content">
      <router-outlet />
    </main>
  `,
  styles: `
    .shell__bar {
      gap: 8px;
      overflow-x: auto;
    }
    .shell__brand {
      font-weight: 600;
      color: inherit;
      text-decoration: none;
      margin-right: 8px;
    }
    .shell__nav {
      display: flex;
      gap: 4px;
    }
    .shell__nav--active {
      background: var(--mat-sys-secondary-container);
    }
    .shell__spacer {
      flex: 1;
    }
    .shell__user {
      font: var(--mat-sys-body-small);
      opacity: 0.8;
      white-space: nowrap;
    }
    .shell__content {
      padding: 24px 16px;
      max-width: 1100px;
      margin: 0 auto;
    }
    @media (max-width: 800px) {
      .shell__user {
        display: none;
      }
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Shell {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  readonly links = [
    { path: '/', label: 'Início' },
    { path: '/inbox', label: 'Conversas' },
    { path: '/clientes', label: 'Clientes' },
    { path: '/processos', label: 'Processos' },
    { path: '/configuracoes/termo', label: 'Termo de IA' },
  ];
  readonly session = this.auth.session;
  readonly roleLabel = computed(() => {
    const role = this.session()?.role;
    return role ? ROLE_LABELS[role] : '';
  });

  logout(): void {
    this.auth.logout();
    void this.router.navigate(['/login']);
  }
}
