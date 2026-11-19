import { ChangeDetectionStrategy, Component, computed, inject, input, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Router } from '@angular/router';
import { EMPTY, of, switchMap } from 'rxjs';

import { AuthService } from '../../core/auth/auth.service';
import { toApiError } from '../../core/http/api-error';
import { confirmAction } from '../../shared/confirm-dialog';
import { TrashKind, TrashService } from './trash.service';

/** Botão "Remover" de cliente/processo: confirma, manda para a Lixeira e oferece desfazer. */
@Component({
  selector: 'app-remove-button',
  imports: [MatButtonModule],
  template: `
    @if (allowed()) {
      <button mat-button type="button" class="danger" [disabled]="busy()" (click)="remove()">
        <span class="icon btn-icon">delete</span>Remover
      </button>
    }
  `,
  styles: `
    .danger {
      color: var(--tm-danger);
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RemoveButton {
  private readonly api = inject(TrashService);
  private readonly dialog = inject(MatDialog);
  private readonly snackBar = inject(MatSnackBar);
  private readonly router = inject(Router);
  private readonly auth = inject(AuthService);

  readonly kind = input.required<TrashKind>();
  readonly itemId = input.required<string>();
  readonly label = input<string>('');

  readonly busy = signal(false);
  /** A equipe (STAFF) não remove; o servidor também confere. */
  readonly allowed = computed(() => this.auth.session()?.role !== 'STAFF');

  remove(): void {
    const what = this.kind() === 'client' ? 'cliente' : 'processo';
    confirmAction(this.dialog, {
      title: `Remover ${what}?`,
      message:
        `${this.label() || 'Este ' + what} vai para a Lixeira e some das listas. ` +
        'Dá para restaurar por 30 dias; depois é apagado de vez.',
      confirmLabel: 'Remover',
      danger: true,
    })
      .pipe(switchMap((ok) => (ok ? of(true) : EMPTY)))
      .subscribe(() => this.send(false));
  }

  private send(force: boolean): void {
    this.busy.set(true);
    this.api.remove(this.kind(), this.itemId(), force).subscribe({
      next: () => this.done(),
      error: (err: unknown) => {
        this.busy.set(false);
        const apiError = toApiError(err);
        if (apiError.code === 'has_open_installments') {
          confirmAction(this.dialog, {
            title: 'Parcelas em aberto',
            message: apiError.message,
            confirmLabel: 'Remover mesmo assim',
            danger: true,
          }).subscribe((ok) => ok && this.send(true));
          return;
        }
        this.snackBar.open(apiError.message, 'OK', { duration: 5000 });
      },
    });
  }

  private done(): void {
    const kind = this.kind();
    const id = this.itemId();
    void this.router.navigate([kind === 'client' ? '/clientes' : '/processos']);
    this.snackBar
      .open('Movido para a Lixeira.', 'Desfazer', { duration: 8000 })
      .onAction()
      .pipe(switchMap(() => this.api.restore(kind, id)))
      .subscribe({
        next: () => {
          this.snackBar.open('Restaurado.', 'OK', { duration: 3000 });
          void this.router.navigate([kind === 'client' ? '/clientes' : '/processos', id]);
        },
        error: (err: unknown) =>
          this.snackBar.open(toApiError(err).message, 'OK', { duration: 5000 }),
      });
  }
}
