import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialog, MatDialogModule } from '@angular/material/dialog';
import { Observable, map } from 'rxjs';

export interface ConfirmData {
  title: string;
  message: string;
  confirmLabel: string;
  /** Botão vermelho (remover, apagar). */
  danger?: boolean;
}

/** Pergunta "tem certeza?" antes de uma ação. */
@Component({
  selector: 'app-confirm-dialog',
  imports: [MatButtonModule, MatDialogModule],
  template: `
    <h2 mat-dialog-title>{{ data.title }}</h2>
    <mat-dialog-content>
      <p class="message">{{ data.message }}</p>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button type="button" [mat-dialog-close]="false">Cancelar</button>
      <button
        mat-flat-button
        type="button"
        [class.danger]="data.danger"
        [mat-dialog-close]="true"
        cdkFocusInitial
      >
        {{ data.confirmLabel }}
      </button>
    </mat-dialog-actions>
  `,
  styles: `
    .message {
      margin: 0;
      white-space: pre-line;
    }
    .danger {
      background: var(--tm-danger);
      color: #fff;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ConfirmDialog {
  readonly data = inject<ConfirmData>(MAT_DIALOG_DATA);
}

/** Abre a confirmação; emite true só se a pessoa confirmar. */
export function confirmAction(dialog: MatDialog, data: ConfirmData): Observable<boolean> {
  return dialog
    .open<ConfirmDialog, ConfirmData, boolean>(ConfirmDialog, { data, maxWidth: '440px' })
    .afterClosed()
    .pipe(map((ok) => ok === true));
}
