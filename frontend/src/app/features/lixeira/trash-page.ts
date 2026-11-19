import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Observable } from 'rxjs';

import { AuthService } from '../../core/auth/auth.service';
import { toApiError } from '../../core/http/api-error';
import { confirmAction } from '../../shared/confirm-dialog';
import { TrashItem, TrashService } from './trash.service';

/** Clientes e processos removidos: restaurar ou apagar de vez. */
@Component({
  selector: 'app-trash-page',
  imports: [DatePipe, MatButtonModule, MatProgressBarModule],
  template: `
    <header class="page-header">
      <div>
        <h1>Lixeira</h1>
        <p>
          Clientes e processos removidos ficam aqui por 30 dias e depois são apagados de vez, com os
          documentos e honorários deles.
        </p>
      </div>
    </header>

    @if (loading()) {
      <mat-progress-bar mode="indeterminate" />
    }
    @if (error(); as message) {
      <p class="error-text" role="alert">{{ message }}</p>
    }

    <section class="card list">
      @for (item of items(); track item.kind + item.id) {
        <div class="row">
          <span class="icon kind">{{ item.kind === 'client' ? 'person' : 'gavel' }}</span>
          <div class="who">
            <strong [class.mono]="item.kind === 'case'">{{ item.label }}</strong>
            <div class="muted small">
              {{ item.kind === 'client' ? 'Cliente' : 'Processo' }}
              @if (item.detail) {
                · {{ item.detail }}
              }
              · removido em {{ item.deleted_at | date: 'dd/MM/yyyy' }}
              @if (item.deleted_by_name) {
                por {{ item.deleted_by_name }}
              }
              · apagado de vez em {{ item.purge_at | date: 'dd/MM/yyyy' }}
            </div>
          </div>
          <div class="actions">
            @if (canRestore()) {
              <button mat-stroked-button type="button" [disabled]="busy()" (click)="restore(item)">
                Restaurar
              </button>
            }
            @if (isOwner()) {
              <button
                mat-button
                type="button"
                class="danger"
                [disabled]="busy()"
                (click)="purge(item)"
              >
                Apagar de vez
              </button>
            }
          </div>
        </div>
      } @empty {
        @if (!loading()) {
          <div class="empty-state">
            <span class="icon">delete</span>
            A lixeira está vazia.
          </div>
        }
      }
    </section>
  `,
  styles: `
    .list {
      padding: 6px 16px;
    }
    .row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px 12px;
      align-items: center;
      padding: 12px 0;
    }
    .row + .row {
      border-top: 1px solid var(--mat-sys-outline-variant);
    }
    .kind {
      color: var(--mat-sys-on-surface-variant);
    }
    .who {
      flex: 1;
      min-width: 220px;
    }
    .actions {
      display: flex;
      gap: 6px;
    }
    .danger {
      color: var(--tm-danger);
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TrashPage {
  private readonly api = inject(TrashService);
  private readonly dialog = inject(MatDialog);
  private readonly snackBar = inject(MatSnackBar);
  private readonly auth = inject(AuthService);

  readonly items = signal<TrashItem[]>([]);
  readonly loading = signal(false);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly isOwner = computed(() => this.auth.session()?.role === 'OWNER');
  readonly canRestore = computed(() => this.auth.session()?.role !== 'STAFF');

  constructor() {
    this.load();
  }

  restore(item: TrashItem): void {
    this.run(this.api.restore(item.kind, item.id), `${item.label} voltou para a lista.`);
  }

  purge(item: TrashItem): void {
    confirmAction(this.dialog, {
      title: 'Apagar de vez?',
      message:
        `${item.label} será apagado agora, sem esperar os 30 dias.` +
        (item.kind === 'client'
          ? ' Documentos, honorários e oportunidades do cliente também.'
          : ' Andamentos do processo também.') +
        '\nNão tem como desfazer.',
      confirmLabel: 'Apagar de vez',
      danger: true,
    }).subscribe((ok) => {
      if (ok) {
        this.run(this.api.purge(item.kind, item.id), 'Apagado de vez.');
      }
    });
  }

  private run(request: Observable<void>, message: string): void {
    this.busy.set(true);
    this.error.set(null);
    request.subscribe({
      next: () => {
        this.busy.set(false);
        this.snackBar.open(message, 'OK', { duration: 4000 });
        this.load();
      },
      error: (err: unknown) => {
        this.busy.set(false);
        this.error.set(toApiError(err).message);
      },
    });
  }

  private load(): void {
    this.loading.set(true);
    this.api.list().subscribe({
      next: (items) => {
        this.items.set(items);
        this.loading.set(false);
      },
      error: (err: unknown) => {
        this.loading.set(false);
        this.error.set(toApiError(err).message);
      },
    });
  }
}
