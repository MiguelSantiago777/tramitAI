import { ChangeDetectionStrategy, Component, inject, input } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';

import { DraftDialog, DraftDialogData } from './draft-dialog';

/** "Escrever com a Lia": petição, contrato, procuração… em Word e PDF. */
@Component({
  selector: 'app-draft-button',
  imports: [MatButtonModule],
  template: `
    <button mat-stroked-button type="button" (click)="open()">
      <span class="icon btn-icon">auto_awesome</span>Escrever com a Lia
    </button>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DraftButton {
  private readonly dialog = inject(MatDialog);

  readonly clientId = input<string | null>(null);
  readonly caseId = input<string | null>(null);
  readonly label = input<string>('');

  open(): void {
    this.dialog.open<DraftDialog, DraftDialogData>(DraftDialog, {
      data: { clientId: this.clientId(), caseId: this.caseId(), label: this.label() },
      maxWidth: '640px',
      width: '100%',
    });
  }
}
