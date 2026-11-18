import { Clipboard } from '@angular/cdk/clipboard';
import { ChangeDetectionStrategy, Component, inject, input, output, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatMenuModule } from '@angular/material/menu';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Observable } from 'rxjs';

import { toApiError } from '../../core/http/api-error';
import { Installment, money } from './financeiro.models';
import { FinanceiroService } from './financeiro.service';
import { SettleDialog } from './settle-dialog';

@Component({
  selector: 'app-pix-dialog',
  imports: [MatButtonModule, MatDialogModule],
  template: `
    <h2 mat-dialog-title>Pix da parcela {{ data.number }}</h2>
    <mat-dialog-content class="pix">
      <p>{{ data.client_name }} · {{ amount }}</p>
      @if (data.pix_qr_base64) {
        <img [src]="'data:image/png;base64,' + data.pix_qr_base64" alt="QR Code do Pix" />
      }
      <label for="pix-code" class="muted small">Pix copia e cola</label>
      <textarea id="pix-code" readonly rows="4">{{ data.pix_code }}</textarea>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button type="button" mat-dialog-close>Fechar</button>
      <button mat-flat-button type="button" (click)="copy()">Copiar código</button>
    </mat-dialog-actions>
  `,
  styles: `
    .pix {
      display: grid;
      gap: 8px;
      justify-items: center;
    }
    img {
      width: 220px;
      height: 220px;
      image-rendering: pixelated;
    }
    textarea {
      width: 100%;
      font:
        12px/1.4 ui-monospace,
        monospace;
      resize: none;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PixDialog {
  readonly data = inject<Installment>(MAT_DIALOG_DATA);
  private readonly clipboard = inject(Clipboard);
  private readonly snack = inject(MatSnackBar);
  readonly amount = money(this.data.amount);

  copy(): void {
    this.clipboard.copy(this.data.pix_code);
    this.snack.open('Código Pix copiado.', 'OK', { duration: 2500 });
  }
}

/** Menu de ações de uma parcela (cobrar, enviar, dar baixa...). Emite a parcela atualizada. */
@Component({
  selector: 'app-installment-actions',
  imports: [MatButtonModule, MatMenuModule],
  template: `
    <button
      mat-icon-button
      type="button"
      [matMenuTriggerFor]="menu"
      [disabled]="busy()"
      [attr.aria-label]="'Ações da parcela ' + installment().number"
    >
      <span class="icon">more_vert</span>
    </button>
    <mat-menu #menu="matMenu">
      @let i = installment();
      @if (i.status === 'OPEN') {
        @if (i.has_active_charge && i.pix_code) {
          <button mat-menu-item type="button" (click)="showPix()">
            <span class="icon menu-icon">qr_code_2</span>Ver Pix
          </button>
        } @else {
          <button mat-menu-item type="button" (click)="charge('PIX')">
            <span class="icon menu-icon">qr_code_2</span>Gerar Pix
          </button>
        }
        @if (i.has_active_charge && i.payment_url && !i.pix_code) {
          <button mat-menu-item type="button" (click)="copyLink()">
            <span class="icon menu-icon">link</span>Copiar link de pagamento
          </button>
        } @else {
          <button mat-menu-item type="button" (click)="charge('LINK')">
            <span class="icon menu-icon">link</span>Gerar link (cartão, boleto, Pix)
          </button>
        }
        <button mat-menu-item type="button" (click)="sendWhatsApp()">
          <span class="icon menu-icon">send</span>Enviar cobrança pelo WhatsApp
        </button>
        <button mat-menu-item type="button" (click)="settle()">
          <span class="icon menu-icon">paid</span>Dar baixa (recebi)
        </button>
        <button mat-menu-item type="button" class="danger" (click)="cancel()">
          <span class="icon menu-icon">block</span>Cancelar parcela
        </button>
      } @else {
        <button mat-menu-item type="button" (click)="reopen()">
          <span class="icon menu-icon">undo</span>Reabrir parcela
        </button>
      }
    </mat-menu>
  `,
  styles: `
    .menu-icon {
      margin-right: 8px;
      vertical-align: middle;
    }
    .danger {
      color: var(--tm-danger);
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InstallmentActions {
  private readonly api = inject(FinanceiroService);
  private readonly dialog = inject(MatDialog);
  private readonly snack = inject(MatSnackBar);
  private readonly clipboard = inject(Clipboard);

  readonly installment = input.required<Installment>();
  readonly changed = output<Installment>();
  readonly busy = signal(false);

  charge(kind: 'PIX' | 'LINK'): void {
    this.run(this.api.charge(this.installment().id, kind), (updated) => {
      if (kind === 'PIX') {
        this.dialog.open(PixDialog, { data: updated, width: '420px', maxWidth: '95vw' });
      } else {
        this.clipboard.copy(updated.payment_url);
        this.snack.open('Link gerado e copiado.', 'OK', { duration: 3000 });
      }
    });
  }

  showPix(): void {
    this.dialog.open(PixDialog, { data: this.installment(), width: '420px', maxWidth: '95vw' });
  }

  copyLink(): void {
    this.clipboard.copy(this.installment().payment_url);
    this.snack.open('Link copiado.', 'OK', { duration: 2500 });
  }

  sendWhatsApp(): void {
    this.busy.set(true);
    this.api.sendWhatsApp(this.installment().id).subscribe({
      next: () => {
        this.busy.set(false);
        this.snack.open('Cobrança enviada pelo WhatsApp.', 'OK', { duration: 3000 });
      },
      error: (err: unknown) => this.fail(err),
    });
  }

  settle(): void {
    this.dialog
      .open(SettleDialog, { data: this.installment(), width: '560px', maxWidth: '95vw' })
      .afterClosed()
      .subscribe((saved?: Installment) => saved && this.changed.emit(saved));
  }

  reopen(): void {
    this.run(this.api.reopen(this.installment().id));
  }

  cancel(): void {
    this.run(this.api.cancel(this.installment().id));
  }

  private run(request: Observable<Installment>, after?: (i: Installment) => void): void {
    this.busy.set(true);
    request.subscribe({
      next: (updated) => {
        this.busy.set(false);
        this.changed.emit(updated);
        after?.(updated);
      },
      error: (err: unknown) => this.fail(err),
    });
  }

  private fail(err: unknown): void {
    this.busy.set(false);
    this.snack.open(toApiError(err).message, 'OK', { duration: 6000 });
  }
}
