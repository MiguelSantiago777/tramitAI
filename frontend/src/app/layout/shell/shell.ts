import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatToolbarModule } from '@angular/material/toolbar';
import { Router, RouterOutlet } from '@angular/router';

import { ROLE_LABELS } from '../../core/auth/auth.models';
import { AuthService } from '../../core/auth/auth.service';

@Component({
  selector: 'app-shell',
  imports: [RouterOutlet, MatButtonModule, MatToolbarModule],
  template: `
    <mat-toolbar class="shell__bar">
      <span class="shell__brand">TramitAI</span>
      <span class="shell__tenant">{{ session()?.tenant?.name }}</span>
      <span class="shell__spacer"></span>
      <span class="shell__user">{{ session()?.user?.email }} · {{ roleLabel() }}</span>
      <button mat-button type="button" (click)="logout()">Sair</button>
    </mat-toolbar>
    <main class="shell__content">
      <router-outlet />
    </main>
  `,
  styles: `
    .shell__bar {
      gap: 16px;
    }
    .shell__brand {
      font-weight: 600;
    }
    .shell__tenant {
      font: var(--mat-sys-body-large);
      opacity: 0.8;
    }
    .shell__spacer {
      flex: 1;
    }
    .shell__user {
      font: var(--mat-sys-body-medium);
    }
    .shell__content {
      padding: 24px 16px;
      max-width: 1100px;
      margin: 0 auto;
    }
    @media (max-width: 600px) {
      .shell__tenant,
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
