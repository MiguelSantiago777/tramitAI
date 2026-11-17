import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { Observable } from 'rxjs';

import { toApiError } from '../../../core/http/api-error';
import { QuickReply } from '../../inbox/inbox.models';
import { InboxService } from '../../inbox/inbox.service';

/** Respostas prontas usadas no WhatsApp (escritas pela equipe, não pela IA). */
@Component({
  selector: 'app-quick-replies-page',
  imports: [ReactiveFormsModule, MatButtonModule, MatFormFieldModule, MatInputModule],
  template: `
    <header class="page-header">
      <div>
        <h1>Respostas prontas</h1>
        <p>
          Textos que a equipe usa no WhatsApp com um clique (botão ⚡ na conversa). Escreva
          <strong>{{ '{' }}nome{{ '}' }}</strong> para colocar o primeiro nome do cliente.
        </p>
      </div>
    </header>

    <form class="form-card" [formGroup]="form" (ngSubmit)="save()">
      <h2>{{ editing() ? 'Editar resposta' : 'Nova resposta' }}</h2>
      <div class="grid">
        <mat-form-field appearance="outline">
          <mat-label>Título</mat-label>
          <input matInput formControlName="title" placeholder="Ex.: Documentos para iniciar" />
        </mat-form-field>
        <mat-form-field appearance="outline" class="body">
          <mat-label>Texto</mat-label>
          <textarea
            matInput
            formControlName="body"
            rows="4"
            placeholder="Olá, {nome}! Para começarmos, envie foto do RG, CPF e comprovante de residência."
          ></textarea>
        </mat-form-field>
      </div>
      <div class="form-actions">
        @if (editing()) {
          <button mat-button type="button" (click)="cancel()">Cancelar</button>
        }
        <button mat-flat-button type="submit" [disabled]="busy()">Salvar</button>
      </div>
    </form>

    @if (error(); as message) {
      <p class="error-text" role="alert">{{ message }}</p>
    }

    <section class="card list">
      @for (r of replies(); track r.id) {
        <div class="row">
          <div class="text">
            <strong>{{ r.title }}</strong>
            <p class="muted small">{{ r.body }}</p>
          </div>
          <button mat-button type="button" (click)="edit(r)">Editar</button>
          <button mat-button type="button" class="danger" (click)="remove(r)">Apagar</button>
        </div>
      } @empty {
        <div class="empty-state">
          <span class="icon">bolt</span>
          Nenhuma resposta pronta ainda.
        </div>
      }
    </section>
  `,
  styles: `
    .grid {
      display: grid;
      grid-template-columns: 280px minmax(0, 1fr);
      gap: 12px;
    }
    @media (max-width: 760px) {
      .grid {
        grid-template-columns: 1fr;
      }
    }
    .list {
      padding: 6px 16px;
    }
    .row {
      display: flex;
      align-items: flex-start;
      gap: 8px;
      padding: 12px 0;
    }
    .row + .row {
      border-top: 1px solid var(--mat-sys-outline-variant);
    }
    .text {
      flex: 1;
      min-width: 0;
    }
    .text p {
      margin: 4px 0 0;
      white-space: pre-wrap;
    }
    .danger {
      color: var(--tm-danger);
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class QuickRepliesPage {
  private readonly api = inject(InboxService);

  readonly replies = signal<QuickReply[]>([]);
  readonly editing = signal<QuickReply | null>(null);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly form = inject(NonNullableFormBuilder).group({
    title: ['', [Validators.required, Validators.maxLength(80)]],
    body: ['', Validators.required],
  });

  constructor() {
    this.load();
  }

  edit(reply: QuickReply): void {
    this.editing.set(reply);
    this.form.setValue({ title: reply.title, body: reply.body });
  }

  cancel(): void {
    this.editing.set(null);
    this.form.reset({ title: '', body: '' });
  }

  save(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const current = this.editing();
    const body = this.form.getRawValue();
    this.run(
      current ? this.api.updateQuickReply(current.id, body) : this.api.createQuickReply(body),
      () => this.cancel(),
    );
  }

  remove(reply: QuickReply): void {
    this.run(this.api.deleteQuickReply(reply.id));
  }

  private run(request: Observable<unknown>, done?: () => void): void {
    this.busy.set(true);
    this.error.set(null);
    request.subscribe({
      next: () => {
        this.busy.set(false);
        done?.();
        this.load();
      },
      error: (err: unknown) => {
        this.busy.set(false);
        this.error.set(toApiError(err).message);
      },
    });
  }

  private load(): void {
    this.api.quickReplies().subscribe({
      next: (list) => this.replies.set(list),
      error: (err: unknown) => this.error.set(toApiError(err).message),
    });
  }
}
