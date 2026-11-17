import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { MatCardModule } from '@angular/material/card';

import { AuthService } from '../../core/auth/auth.service';

@Component({
  selector: 'app-home',
  imports: [MatCardModule],
  template: `
    <h1>Olá, {{ displayName() }}</h1>
    <mat-card appearance="outlined">
      <mat-card-content>
        <p>
          Você está no escritório <strong>{{ session()?.tenant?.name }}</strong>.
        </p>
        <p>Em breve por aqui: clientes, processos, conversas do WhatsApp e fila de aprovação.</p>
      </mat-card-content>
    </mat-card>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Home {
  readonly session = inject(AuthService).session;
  readonly displayName = computed(() => {
    const user = this.session()?.user;
    return user?.full_name || user?.email || '';
  });
}
