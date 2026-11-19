import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule } from '@angular/material/dialog';

export interface AccessLinkData {
  url: string;
  kind: 'invite' | 'reset';
  name: string;
  email: string;
  officeName: string;
}

/** Mostra o link de convite / nova senha para o titular copiar ou mandar pelo WhatsApp. */
@Component({
  selector: 'app-access-link-dialog',
  imports: [MatButtonModule, MatDialogModule],
  template: `
    <h2 mat-dialog-title>
      {{ data.kind === 'invite' ? 'Link de convite' : 'Link para nova senha' }}
    </h2>
    <mat-dialog-content>
      <p>
        Mande este link para <strong>{{ data.name || data.email }}</strong>. Com ele a pessoa cria a
        senha e entra com o e-mail <strong>{{ data.email }}</strong>.
      </p>
      <div class="link" data-testid="access-link">{{ data.url }}</div>
      <p class="muted small">
        Vale por 3 dias e só funciona uma vez. Não publique em grupo: quem tiver o link entra como
        essa pessoa.
      </p>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button type="button" mat-dialog-close>Fechar</button>
      <a mat-stroked-button [href]="whatsapp()" target="_blank" rel="noopener noreferrer">
        <span class="icon btn-icon">chat</span>Enviar pelo WhatsApp
      </a>
      <button mat-flat-button type="button" (click)="copy()">
        <span class="icon btn-icon">content_copy</span>{{ copied() ? 'Copiado!' : 'Copiar link' }}
      </button>
    </mat-dialog-actions>
  `,
  styles: `
    .link {
      padding: 10px 12px;
      border: 1px solid var(--mat-sys-outline-variant);
      border-radius: var(--tm-radius);
      background: var(--mat-sys-surface-container-low);
      font:
        13px/1.4 ui-monospace,
        monospace;
      overflow-wrap: anywhere;
      user-select: all;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AccessLinkDialog {
  readonly data = inject<AccessLinkData>(MAT_DIALOG_DATA);
  readonly copied = signal(false);

  readonly whatsapp = computed(() => {
    const first = (this.data.name || '').split(' ')[0];
    const text =
      this.data.kind === 'invite'
        ? `Olá${first ? ', ' + first : ''}! Você foi convidado(a) para a equipe do ` +
          `${this.data.officeName} no TramitAI. Crie sua senha por este link (vale 3 dias): ` +
          `${this.data.url}\nDepois é só entrar com o e-mail ${this.data.email}.`
        : `Olá${first ? ', ' + first : ''}! Para criar uma senha nova no TramitAI, use este ` +
          `link (vale 3 dias): ${this.data.url}`;
    return `https://wa.me/?text=${encodeURIComponent(text)}`;
  });

  copy(): void {
    void navigator.clipboard?.writeText(this.data.url).then(
      () => this.copied.set(true),
      () => this.copied.set(false),
    );
  }
}
