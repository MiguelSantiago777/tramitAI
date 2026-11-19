import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { Observable } from 'rxjs';

import { toApiError } from '../../../core/http/api-error';
import { TAG_COLORS, Tag, TagColor } from '../../clientes/client.models';
import { ClientsService } from '../../clientes/clients.service';

/** Etiquetas dos clientes (ex.: Trabalhista, VIP, Indicação). */
@Component({
  selector: 'app-tags-page',
  imports: [ReactiveFormsModule, MatButtonModule, MatFormFieldModule, MatInputModule],
  template: `
    <header class="page-header">
      <div>
        <h1>Etiquetas</h1>
        <p>Organize os clientes por área, origem ou o que fizer sentido para o escritório.</p>
      </div>
    </header>

    <form class="card new-tag" (submit)="$event.preventDefault(); create()">
      <mat-form-field appearance="outline" subscriptSizing="dynamic" class="grow">
        <mat-label>Nova etiqueta</mat-label>
        <input matInput [formControl]="name" placeholder="Ex.: Trabalhista" maxlength="40" />
      </mat-form-field>
      <div class="colors" role="radiogroup" aria-label="Cor">
        @for (c of colors; track c) {
          <button
            type="button"
            class="swatch"
            [attr.data-color]="c"
            [class.swatch--on]="color() === c"
            [attr.aria-checked]="color() === c"
            role="radio"
            [attr.aria-label]="c"
            (click)="color.set(c)"
          ></button>
        }
      </div>
      <button mat-flat-button type="submit" [disabled]="busy()">Criar</button>
    </form>

    @if (error(); as message) {
      <p class="error-text" role="alert">{{ message }}</p>
    }

    <section class="card list">
      @for (t of tags(); track t.id) {
        <div class="row">
          <span class="tag-chip" [attr.data-color]="t.color">{{ t.name }}</span>
          <span class="muted small">{{ t.client_count }} cliente(s)</span>
          <span class="spacer"></span>
          <div class="colors">
            @for (c of colors; track c) {
              <button
                type="button"
                class="swatch swatch--small"
                [attr.data-color]="c"
                [class.swatch--on]="t.color === c"
                [attr.aria-label]="'Cor ' + c"
                (click)="recolor(t, c)"
              ></button>
            }
          </div>
          <button mat-button type="button" class="danger" (click)="remove(t)">Apagar</button>
        </div>
      } @empty {
        <div class="empty-state">
          <span class="icon">sell</span>
          Nenhuma etiqueta ainda.
        </div>
      }
    </section>
  `,
  styles: `
    .new-tag {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 12px;
      padding: 16px 20px;
      margin-bottom: 16px;
    }
    .list {
      padding: 6px 16px;
    }
    .row {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 12px;
      padding: 10px 0;
    }
    .row + .row {
      border-top: 1px solid var(--mat-sys-outline-variant);
    }
    .spacer {
      flex: 1;
    }
    .colors {
      display: flex;
      gap: 6px;
    }
    .swatch {
      width: 24px;
      height: 24px;
      border: 2px solid transparent;
      border-radius: 50%;
      background: var(--c);
      cursor: pointer;
    }
    .swatch--small {
      width: 18px;
      height: 18px;
    }
    .swatch--on {
      border-color: var(--mat-sys-on-surface);
      box-shadow: 0 0 0 2px #fff inset;
    }
    .swatch[data-color='indigo'] {
      --c: #4338ca;
    }
    .swatch[data-color='green'] {
      --c: #15803d;
    }
    .swatch[data-color='amber'] {
      --c: #d97706;
    }
    .swatch[data-color='red'] {
      --c: #b91c1c;
    }
    .swatch[data-color='teal'] {
      --c: #0e7490;
    }
    .swatch[data-color='pink'] {
      --c: #be185d;
    }
    .swatch[data-color='slate'] {
      --c: #475569;
    }
    .danger {
      color: var(--tm-danger);
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TagsPage {
  private readonly api = inject(ClientsService);

  readonly colors = TAG_COLORS;
  readonly name = new FormControl('', {
    nonNullable: true,
    validators: [Validators.required, Validators.maxLength(40)],
  });
  readonly color = signal<TagColor>('indigo');
  readonly tags = signal<Tag[]>([]);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);

  constructor() {
    this.load();
  }

  create(): void {
    const name = this.name.value.trim();
    if (!name) {
      return;
    }
    this.run(this.api.createTag({ name, color: this.color() }), () => this.name.reset(''));
  }

  recolor(tag: Tag, color: TagColor): void {
    if (tag.color !== color) {
      this.run(this.api.updateTag(tag.id, { color }));
    }
  }

  remove(tag: Tag): void {
    this.run(this.api.deleteTag(tag.id));
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
    this.api.tags().subscribe({
      next: (list) => this.tags.set(list),
      error: (err: unknown) => this.error.set(toApiError(err).message),
    });
  }
}
