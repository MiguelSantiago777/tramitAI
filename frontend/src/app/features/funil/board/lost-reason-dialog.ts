import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';

const COMMON = [
  'Achou caro',
  'Fechou com outro advogado',
  'Desistiu de entrar com ação',
  'Não tinha direito',
  'Parou de responder',
];

/** Pergunta por que a pessoa não contratou (ajuda a melhorar o atendimento). */
@Component({
  selector: 'app-lost-reason-dialog',
  imports: [
    ReactiveFormsModule,
    MatButtonModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
  ],
  template: `
    <h2 mat-dialog-title>Por que não contratou?</h2>
    <mat-dialog-content>
      <div class="chips">
        @for (r of common; track r) {
          <button mat-stroked-button type="button" (click)="reason.setValue(r)">{{ r }}</button>
        }
      </div>
      <mat-form-field appearance="outline" class="full" subscriptSizing="dynamic">
        <mat-label>Motivo</mat-label>
        <input matInput [formControl]="reason" maxlength="255" />
      </mat-form-field>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button type="button" mat-dialog-close>Cancelar</button>
      <button mat-flat-button type="button" [disabled]="reason.invalid" (click)="confirm()">
        Confirmar
      </button>
    </mat-dialog-actions>
  `,
  styles: `
    .chips {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin: 4px 0 12px;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LostReasonDialog {
  private readonly ref = inject(MatDialogRef<LostReasonDialog, string>);
  readonly common = COMMON;
  readonly reason = new FormControl('', {
    nonNullable: true,
    validators: [Validators.required, Validators.pattern(/\S/)],
  });

  confirm(): void {
    this.ref.close(this.reason.value.trim());
  }
}
